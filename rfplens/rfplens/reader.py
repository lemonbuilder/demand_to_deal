"""문서 리더(디스패처) — 어떤 파일·압축·폴더든 끝까지 읽는다.
처리 순서
  1. 매직 바이트로 실제 형식 판별(detect)
  2. 형식별 판독기: hwp(본문 레코드·배포용 해독) → 실패 시 hwp5txt → LibreOffice
     hwpx/docx/xlsx/pptx/hml(XML) · 구형 xls/doc/ppt(LibreOffice 변환) · pdf(무텍스트 쪽 OCR) · 이미지(OCR)
     zip(내부 파일명 cp949 복원, 최대 깊이까지 재귀) · 폴더(재귀) · 미상 형식(LibreOffice 텍스트 변환)
  3. 텍스트가 짧고 내장 이미지가 있으면 내장 이미지 OCR
  4. 품질 검사(깨진 문자) 후 상태 판정
"""
from __future__ import annotations

import os
import re
import tempfile
import zipfile

from . import detect as D
from .config import DEFAULT, Settings
from .models import FileResult
from .ocr import get_ocr
from .quality import clean, judge
from .readers import external as X
from .readers import hwp as H
from .readers import xmldocs as XD


class Reader:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or DEFAULT
        self._ocr = None

    @property
    def ocr(self):
        if self._ocr is None:
            self._ocr = get_ocr(self.s)
        return self._ocr

    # ---------- 공개 API ----------
    def read_path(self, path: str, name: str | None = None) -> list[FileResult]:
        """파일·폴더 1개를 읽어 FileResult 목록 반환(압축·폴더는 내부 파일마다 1개)"""
        name = name or os.path.basename(path.rstrip('/'))
        ext = name.rsplit('.', 1)[-1].lower() if ('.' in name and not os.path.isdir(path)) else ''
        out = []
        with tempfile.TemporaryDirectory(dir=self.s.tmp_dir) as tmp:
            for inner, kind, method, text, err in self._read_any(path, name, tmp, 0):
                text = clean(text)
                status, err = judge(text, err, method, self.s)
                out.append(FileResult(name=name, inner=inner, ext=ext, kind=kind, method=method, status=status,
                                      chars=len(text), text=text, error=err or None))
        return out

    def read_bytes(self, data: bytes, name: str) -> list[FileResult]:
        """업로드 파일(bytes) 판독 — 웹 API용"""
        with tempfile.TemporaryDirectory(dir=self.s.tmp_dir) as tmp:
            p = os.path.join(tmp, 'upload_' + re.sub(r'[/\\]', '_', name)[-80:])
            with open(p, 'wb') as w:
                w.write(data)
            return self.read_path(p, name)

    # ---------- 내부 ----------
    def _ocr_blobs(self, blobs, tmpdir):
        paths = []
        for i, b in enumerate(blobs):
            if len(b) < self.s.small_image_bytes:
                continue
            p = os.path.join(tmpdir, f'img{i}.bin')
            with open(p, 'wb') as w:
                w.write(b)
            paths.append(p)
        txts = []
        for k in range(0, len(paths), 20):
            txts += self.ocr.recognize(paths[k:k + 20])
        return '\n'.join(t for t in txts if t)

    def _read_any(self, path, name, tmpdir, depth):
        """반환: [(inner_name, kind, method, text, error)]"""
        s = self.s
        if os.path.isdir(path):
            res = []
            for fn in sorted(os.listdir(path)):
                if fn.startswith('.'):
                    continue
                for n, *rest in self._read_any(os.path.join(path, fn), fn, tmpdir, depth + 1):
                    res.append((f'{name}/{n}' if n else f'{name}/{fn}', *rest))
            return res
        with open(path, 'rb') as f:
            data = f.read()
        kind = D.detect(data)
        try:
            if kind == 'ole':
                try:
                    kind = D.ole_kind(path)
                except Exception:          # 손상 OLE(불완전 섹터 등) → LibreOffice 텍스트 변환 시도
                    kind = 'ole_broken'
            if kind == 'hwp' and H.hwp_password_protected(path):
                kind = 'encrypted-hwp'
                raise PermissionError('사용자 암호가 설정된 hwp — 원문 판독 불가')
            if kind == 'ole_other' and D.ole_has(path, 'EncryptedPackage'):
                kind = 'encrypted-ooxml'
                raise PermissionError('암호화된 오피스 문서 — 원문 판독 불가')
            if kind == 'hwp':
                try:
                    text, method = H.hwp_text(path), 'hwp-record'
                except Exception:
                    text, method = X.hwp5txt(path, s), 'hwp5txt(표 제외)'
                    if len(text.strip()) < s.min_chars:
                        text = open(X.lo_convert(path, 'txt:Text (encoded):UTF8', tmpdir, s), encoding='utf-8', errors='ignore').read()
                        method = 'lo-txt'
                imgs = H.hwp_images(path) if len(re.sub(r'\s', '', text)) < s.min_chars else []
            elif kind == 'hwpx':
                (text, imgs), method = XD.read_hwpx(data), 'hwpx-xml'
            elif kind == 'docx':
                (text, imgs), method = XD.read_docx(data), 'docx-xml'
            elif kind == 'xlsx':
                try:
                    (text, imgs), method = XD.read_xlsx(data), 'xlsx'
                except Exception:            # 손상 xlsx: LibreOffice 재저장 → XML 직접 판독
                    try:
                        (text, imgs), method = XD.read_xlsx(open(X.lo_convert(path, 'xlsx', tmpdir, s), 'rb').read()), 'lo-xlsx->xlsx'
                    except Exception:
                        (text, imgs), method = XD.read_xlsx_raw(data), 'xlsx-rawxml'
            elif kind == 'pptx':
                (text, imgs), method = XD.read_pptx(data), 'pptx-xml'
            elif kind in ('xls', 'doc', 'ppt'):
                tgt = {'xls': 'xlsx', 'doc': 'docx', 'ppt': 'pptx'}[kind]
                d2 = open(X.lo_convert(path, tgt, tmpdir, s), 'rb').read()
                text, imgs = {'xlsx': XD.read_xlsx, 'docx': XD.read_docx, 'pptx': XD.read_pptx}[tgt](d2)
                method = f'lo-{kind}->{tgt}'
            elif kind in ('hml', 'xml'):
                (text, imgs), method = XD.read_hml(data), 'xml'
            elif kind == 'pdf':
                if X.pdf_user_password(path, s):
                    kind = 'encrypted-pdf'
                    raise PermissionError('열기 암호가 설정된 pdf — 원문 판독 불가')
                text, n_ocr = X.read_pdf(path, tmpdir, self.ocr, s)
                imgs, method = [], 'pdftotext' + (f'+ocr({n_ocr}쪽)' if n_ocr else '')
            elif kind == 'image':
                res = self.ocr.recognize([path])
                text, imgs, method = (res[0] if res else ''), [], 'ocr-image'
            elif kind == 'zip':
                return self._read_zip(path, name, tmpdir, depth)
            elif kind.startswith('drm'):
                vendor = {'drm-fasoo': 'Fasoo ', 'drm-markany': 'MarkAny '}.get(kind, '')
                raise PermissionError(f'{vendor}DRM 암호화 문서(복호화 키 없음) — 원문 판독 불가')
            else:  # hwp3, ole_other, unknown, zip_broken, archive_other
                out = X.lo_convert(path, 'txt:Text (encoded):UTF8', tmpdir, s)
                text, imgs, method = open(out, encoding='utf-8', errors='ignore').read(), [], f'lo-txt({kind})'
            if len(re.sub(r'\s', '', text)) < s.min_chars and imgs:
                o = self._ocr_blobs(imgs, tmpdir)
                if o:
                    text, method = (text + '\n' + o).strip(), method + '+ocr-내장이미지'
            return [(None, kind, method, text, '')]
        except Exception as e:
            return [(None, kind, 'error', '', f'{type(e).__name__}: {str(e)[:200]}')]

    def _read_zip(self, path, name, tmpdir, depth):
        sub = os.path.join(tmpdir, f'z{depth}_{abs(hash((path, name))) % 10**8}')
        os.makedirs(sub, exist_ok=True)
        res = []
        with zipfile.ZipFile(path) as z:
            for k, info in enumerate(z.infolist()):
                if info.is_dir():
                    continue
                iname = info.filename
                if not (info.flag_bits & 0x800):          # UTF-8 플래그 없으면 cp949 파일명 복원
                    try:
                        iname = iname.encode('cp437').decode('cp949')
                    except Exception:
                        pass
                tp = os.path.join(sub, f'f{k}_{os.path.basename(iname)[-60:]}')
                if info.flag_bits & 0x1:              # 암호 걸린 압축 항목
                    res.append((iname, 'encrypted-zip', 'error', '', '암호가 걸린 압축 항목 — 원문 판독 불가'))
                    continue
                with open(tp, 'wb') as w:
                    w.write(z.read(info))
                if depth >= self.s.max_zip_depth:
                    res.append((iname, 'zip', 'depth-limit', '', f'압축 중첩 {self.s.max_zip_depth}단계 초과'))
                    continue
                for n, *rest in self._read_any(tp, iname, tmpdir, depth + 1):
                    res.append((f'{iname}/{n}' if n else iname, *rest))
        return res
