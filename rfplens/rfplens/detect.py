"""형식 판별 — 확장자가 아니라 파일 내용(매직 바이트)으로 판별한다.
1배치 경험: '.hwpx'인데 실제 hwp(OLE), '.hwp'인데 실제 hwpx(zip), '.hwtx'가 hwpx인 사례 다수.
"""
from __future__ import annotations

import io
import re
import zipfile

OLE_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


def detect(data: bytes) -> str:
    """반환: drm-fasoo | drm-markany | drm | ole | egg | xlsb | odf | cad-dwg | cad-dxf | text | shortcut | encrypted-unknown | hwpx | docx | xlsx | pptx | zip | zip_broken | pdf | hwp3 | image | hml | xml | archive_other | unknown"""
    h = data[:8]
    if b'DRMONE' in data[:64] or b'FasooSecureContainer' in data[:256] or b'Fasoo DRM' in data[:256]:
        return 'drm-fasoo'
    if b'DOCUMENTSAFER' in data[:64] or b'<## MarkAny' in data[:64]:
        return 'drm-markany'
    if b'SCDSA' in data[:16]:
        return 'drm'
    if h.startswith(OLE_MAGIC):
        return 'ole'
    if h.startswith(b'PK\x03\x04') or h.startswith(b'PK\x05\x06'):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
        except Exception:
            return 'zip_broken'
        if any(re.match(r'Contents/section\d+\.xml$', n) for n in names):
            return 'hwpx'
        if 'word/document.xml' in names:
            return 'docx'
        if 'xl/workbook.xml' in names:
            return 'xlsx'
        if 'ppt/presentation.xml' in names:
            return 'pptx'
        if 'xl/workbook.bin' in names:
            return 'xlsb'                  # 엑셀 바이너리 통합문서(zip 컨테이너지만 압축으로 풀면 안 됨)
        if 'mimetype' in names and any(n == 'content.xml' for n in names):
            return 'odf'                   # OpenDocument(odt·ods·odp)
        return 'zip'
    if h.startswith(b'%PDF') or b'%PDF' in data[:1024]:
        return 'pdf'
    if h.startswith(b'HWP Document File'):
        return 'hwp3'
    if h.startswith(b'\x89PNG') or h.startswith(b'\xff\xd8\xff') or h[:4] in (b'GIF8', b'II*\x00', b'MM\x00*') or h.startswith(b'BM'):
        return 'image'
    head = data[:2048].lstrip(b'\xef\xbb\xbf')
    if head.startswith(b'<?xml') or head.startswith(b'<HWPML'):
        return 'hml' if b'HWPML' in data[:4096] else 'xml'
    if h[:4] == b'EGGA':
        return 'egg'
    if h[:4] == b'AC10' or h[:4] == b'AC27':
        return 'cad-dwg'                   # AutoCAD 도면(비텍스트)
    if data[:64].lstrip().startswith(b'0') and b'SECTION' in data[:64] and b'HEADER' in data[:256]:
        return 'cad-dxf'
    if h.startswith(b'Rar!') or h.startswith(b'7z\xbc\xaf'):
        return 'archive_other'
    if h[:4] == b'L\x00\x00\x00' and data[4:8] == b'\x01\x14\x02\x00':
        return 'shortcut'                  # 윈도우 바로가기(.lnk): 문서 내용 없음
    if _is_text(data):
        return 'text'
    if len(data) >= 4096 and _entropy(data[:65536]) > 7.9:
        return 'encrypted-unknown'         # 알려진 형식 표식 없는 고엔트로피 바이너리 = 암호화 파일로 판단
    return 'unknown'


def _entropy(b: bytes) -> float:
    import math
    from collections import Counter
    n = len(b)
    return -sum(v / n * math.log2(v / n) for v in Counter(b).values()) if n else 0.0


def _is_text(data: bytes) -> bool:
    """일반 텍스트(txt·csv 등): UTF-8/UTF-16/CP949로 디코딩되고 제어문자가 거의 없음"""
    head = data[:20000]
    if b'\x00' in head and not head.startswith((b'\xff\xfe', b'\xfe\xff')):
        return False
    for enc in ('utf-8-sig', 'utf-16', 'cp949'):
        try:
            t = head.decode(enc)
        except UnicodeDecodeError:
            continue
        bad = sum(1 for ch in t if ord(ch) < 32 and ch not in '\r\n\t')
        return bad / max(1, len(t)) < 0.01
    return False


def decode_text(data: bytes) -> str:
    for enc in ('utf-8-sig', 'utf-16', 'cp949'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', 'replace')


def ole_has(path: str, stream: str) -> bool:
    import olefile
    o = olefile.OleFileIO(path)
    try:
        return o.exists(stream)
    finally:
        o.close()


def ole_kind(path: str) -> str:
    """OLE 복합문서 세부 형식: hwp | xls | doc | ppt | ole_other"""
    import olefile
    o = olefile.OleFileIO(path)
    try:
        if o.exists('FileHeader'):
            return 'hwp'
        if not o.listdir() and b'HWP Document File' in open(path, 'rb').read():
            return 'hwp'                   # 디렉터리가 깨진 hwp(판독기에서 복구)
        if o.exists('Workbook') or o.exists('Book'):
            return 'xls'
        if o.exists('WordDocument'):
            return 'doc'
        if o.exists('PowerPoint Document'):
            return 'ppt'
        return 'ole_other'
    finally:
        o.close()
