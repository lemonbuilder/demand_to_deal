"""RFPLens 회귀 시험 (표준 라이브러리 unittest)
실행: cd rfplens && python -m unittest discover -s tests -v
- 합성 파일 시험: 항상 실행
- 실제 사례 시험: 환경변수 RFPLENS_SAMPLE_ROOT(…/01_sample) 가 있을 때만(1배치 특이 사례)
"""
import io
import os
import tempfile
import unittest
import zipfile

from rfplens.detect import detect
from rfplens.models import FAIL, OK, PASS_NOTICE, FileResult, NoticeResult
from rfplens.policy import apply_policy
from rfplens.quality import garbage_ratio
from rfplens.reader import Reader
from rfplens.rules import load_rules
from rfplens.sections import doctype, sectionize
from rfplens.units import structure_notice


def make_hwpx(paras, table=None) -> bytes:
    """paras: 일반 문단, table: [[셀..]] (rowCnt×colCnt)"""
    body = ''.join(f'<hp:p><hp:run><hp:t>{p}</hp:t></hp:run></hp:p>' for p in paras)
    if table:
        cells = ''.join(f'<hp:tc><hp:p><hp:run><hp:t>{c}</hp:t></hp:run></hp:p></hp:tc>' for row in table for c in row)
        body += f'<hp:p><hp:run><hp:tbl rowCnt="{len(table)}" colCnt="{len(table[0])}">{cells}</hp:tbl></hp:run></hp:p>'
    xml = f'<?xml version="1.0" encoding="UTF-8"?><hs:sec xmlns:hp="x" xmlns:hs="y">{body}</hs:sec>'
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('mimetype', 'application/hwp+zip')
        z.writestr('Contents/section0.xml', xml)
    return b.getvalue()


TASK_DOC = ['과 업 지 시 서', '1. 과업명 : 시험 용역', '2. 과업의 범위', '가. 현황 조사 및 분석을 실시한다',
            '나. 위성영상 기반 변화탐지 결과를 제출한다', '3. 계약 일반사항', '가. 계약상대자는 보안서약서를 제출하여야 한다',
            '4. 성과품', '가. 최종보고서 10부']


class TestDetectAndRead(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rd = Reader()

    def tearDown(self):
        self.tmp.cleanup()

    def w(self, name, data):
        p = os.path.join(self.tmp.name, name)
        with open(p, 'wb') as f:
            f.write(data)
        return p

    def test_hwpx_and_table_mark(self):
        p = self.w('과업지시서.hwpx', make_hwpx(TASK_DOC, [['구분', '내용'], ['조사', '현황'], ['분석', '결과']]))
        r = self.rd.read_path(p)[0]
        self.assertEqual((r.kind, r.status), ('hwpx', OK))
        self.assertIn('│조사', r.text)          # 칸 3개 이상 표 셀 표시

    def test_misnamed_extension(self):
        """확장자는 .hwp 지만 실제 hwpx → 내용으로 판별"""
        p = self.w('과업지시서.hwp', make_hwpx(TASK_DOC))
        r = self.rd.read_path(p)[0]
        self.assertEqual(r.kind, 'hwpx'); self.assertTrue(r.ok)

    def test_nested_zip_cp949(self):
        class LegacyInfo(zipfile.ZipInfo):      # 한국어 윈도우 압축기처럼 cp949 파일명 + UTF-8 플래그 없음
            def _encodeFilenameFlags(self):
                return self.filename.encode('cp949'), self.flag_bits
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, 'w') as z:
            z.writestr(LegacyInfo('과업지시서.hwpx'), make_hwpx(TASK_DOC))
        outer = io.BytesIO()
        with zipfile.ZipFile(outer, 'w') as z:
            z.writestr('inner.zip', inner.getvalue())
        res = self.rd.read_path(self.w('묶음.zip', outer.getvalue()))
        self.assertEqual(len(res), 1)
        self.assertTrue(res[0].inner.endswith('과업지시서.hwpx'))
        self.assertTrue(res[0].ok)

    def test_folder(self):
        d = os.path.join(self.tmp.name, '풀린폴더'); os.makedirs(d)
        with open(os.path.join(d, 'a.hwpx'), 'wb') as f:
            f.write(make_hwpx(TASK_DOC))
        res = self.rd.read_path(d)
        self.assertEqual(len(res), 1); self.assertTrue(res[0].ok)

    def test_drm_detected_as_failure(self):
        r = self.rd.read_path(self.w('공고문.hwp', b'\x9b DRMONE  This Document is encrypted' + b'\x00' * 200))[0]
        self.assertEqual((r.kind, r.status), ('drm', FAIL))

    def test_xlsx(self):
        import openpyxl
        wb = openpyxl.Workbook(); wb.active.append(['품명', '수량']); wb.active.append(['측량', 3])
        b = io.BytesIO(); wb.save(b)
        r = self.rd.read_path(self.w('내역서.xlsx', b.getvalue()))[0]
        self.assertEqual(r.kind, 'xlsx'); self.assertIn('측량 | 3', r.text)

    def test_detect_magic(self):
        self.assertEqual(detect(b'%PDF-1.7 xxx'), 'pdf')
        self.assertEqual(detect(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\x00' * 8), 'ole')
        self.assertEqual(detect(b'\x89PNG\r\n\x1a\n'), 'image')


class TestQualityPolicy(unittest.TestCase):
    def test_garbage(self):
        self.assertGreater(garbage_ratio('鬠䑒䵏久周楳潣畭敮琠楳湣特灴敤湤牯瑥捴敤礠䙡獯漠䑒䴠' * 3), 0.3)
        self.assertEqual(garbage_ratio('과업의 범위는 다음과 같다. ' * 10), 0.0)

    def test_notice_policy_pass(self):
        nr = NoticeResult('N1', 'N1-000', [
            FileResult(name='1_공고문.hwp', kind='drm', status=FAIL, error='DRM', seq=1),
            FileResult(name='2_과업지시서.hwp', kind='hwp', status=OK, text='가' * 200, chars=200, seq=2)])
        apply_policy(nr)
        self.assertEqual(nr.files[0].status, PASS_NOTICE)

    def test_core_failure_stays(self):
        nr = NoticeResult('N2', 'N2-000', [FileResult(name='2_과업지시서.hwp', kind='drm', status=FAIL, error='DRM', seq=1)])
        apply_policy(nr)
        self.assertEqual(nr.files[0].status, FAIL)


class TestStructure(unittest.TestCase):
    def test_doctype(self):
        R = load_rules()
        self.assertEqual(doctype('3_제안요청서(과업 포함).hwp', R), '제안요청서')
        self.assertEqual(doctype('2_과업내용서.hwp', R), '과업지시서')
        self.assertEqual(doctype('발주설계서.xlsx', R), '기타')

    def test_labels_no_drop(self):
        lines, found = sectionize('\n'.join(TASK_DOC))
        self.assertTrue(found)
        labels = {b: m for m, _, b, _ in lines}
        self.assertEqual(labels['현황 조사 및 분석을 실시한다'], 'TASK')
        self.assertEqual(labels['계약상대자는 보안서약서를 제출하여야 한다'], 'EXCL')
        nr = NoticeResult('N3', 'N3-000', [FileResult(name='과업지시서.hwpx', status=OK, text='\n'.join(TASK_DOC), chars=999, seq=1)])
        _, _, units = structure_notice(nr)
        joined = ' '.join(u.text for u in units)
        for line in TASK_DOC[1:]:                       # 제외 없이 모든 내용 보존
            body = line.split(' ', 1)[1] if line[0].isdigit() or line[0] in '가나' else line
            self.assertIn(body.split(':')[0].strip(), joined)
        self.assertIn('행정', {u.section_label for u in units})


@unittest.skipUnless(os.environ.get('RFPLENS_SAMPLE_ROOT'), '실제 사례 경로(RFPLENS_SAMPLE_ROOT) 없음')
class TestBatch1Cases(unittest.TestCase):
    """1배치(2025-01)에서 발견한 특이 사례 회귀 시험"""
    CASES = [  # (폴더, 파일명 일부, 기대 kind, 기대 method 접두, 최소 글자수)
        ('R25BK00606650-000', '제안요청서', 'hwp', 'hwp-record', 100000),   # 배포용 hwp(표 포함 해독)
        ('R25BK00583104-000', '과업지시서', 'pdf', 'pdftotext+ocr', 2000),  # 스캔 pdf
        ('R25BK00558553-000', '과업지시서', 'xls', 'lo-xls->xlsx', 5000),   # 구형 xls
        ('R25BK00596920-000', '과업지시서', 'hwp', 'hwp-record', 3000),     # .hwpx 확장자의 hwp
        ('R25BK00580217-000', '제안요청서', 'hwp', 'hwp-record', 70),       # 원문 자체가 짧은 문서
    ]

    def test_cases(self):
        root = os.environ['RFPLENS_SAMPLE_ROOT']
        rd = Reader()
        for folder, part, kind, method, minc in self.CASES:
            d = os.path.join(root, 'raw_documents_excluded', '2025-01', folder)
            fn = [f for f in os.listdir(d) if part in f][0]
            r = rd.read_path(os.path.join(d, fn))[0]
            with self.subTest(folder=folder):
                self.assertEqual(r.kind, kind); self.assertTrue(r.method.startswith(method)); self.assertGreaterEqual(r.chars, minc)
                self.assertTrue(r.ok)


if __name__ == '__main__':
    unittest.main()
