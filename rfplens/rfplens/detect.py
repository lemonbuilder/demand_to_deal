"""형식 판별 — 확장자가 아니라 파일 내용(매직 바이트)으로 판별한다.
1배치 경험: '.hwpx'인데 실제 hwp(OLE), '.hwp'인데 실제 hwpx(zip), '.hwtx'가 hwpx인 사례 다수.
"""
from __future__ import annotations

import io
import re
import zipfile

OLE_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


def detect(data: bytes) -> str:
    """반환: drm | ole | hwpx | docx | xlsx | pptx | zip | zip_broken | pdf | hwp3 | image | hml | xml | archive_other | unknown"""
    h = data[:8]
    if (b'DRMONE' in data[:64] or b'<## MarkAny' in data[:64] or b'SCDSA' in data[:16]
            or b'FasooSecureContainer' in data[:256]):
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
    if h.startswith(b'Rar!') or h.startswith(b'7z\xbc\xaf'):
        return 'archive_other'
    return 'unknown'


def ole_kind(path: str) -> str:
    """OLE 복합문서 세부 형식: hwp | xls | doc | ppt | ole_other"""
    import olefile
    o = olefile.OleFileIO(path)
    try:
        if o.exists('FileHeader'):
            return 'hwp'
        if o.exists('Workbook') or o.exists('Book'):
            return 'xls'
        if o.exists('WordDocument'):
            return 'doc'
        if o.exists('PowerPoint Document'):
            return 'ppt'
        return 'ole_other'
    finally:
        o.close()
