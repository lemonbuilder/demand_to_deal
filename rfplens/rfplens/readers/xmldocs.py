"""XML 기반 문서 판독: hwpx, docx, xlsx, pptx, hml(HWPML)
반환: (text, 내장 이미지 bytes 목록)
"""
from __future__ import annotations

import html
import io
import re
import zipfile

from ..constants import IMG_RE, TABLE_MARK as TM

_HWPX_TOKEN = re.compile(r'<hp:tbl\b[^>]*>|</hp:tbl>|</hp:p>|<hp:t>([^<]*)</hp:t>|<hp:t/>|<hp:lineBreak/>')


def read_hwpx(data: bytes):
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        secs = sorted((n for n in z.namelist() if re.match(r'Contents/section\d+\.xml$', n)),
                      key=lambda n: int(re.search(r'(\d+)', n).group(1)))
        for n in secs:
            xml = z.read(n).decode('utf-8', 'ignore')
            stack, cur = [], []
            for m in _HWPX_TOKEN.finditer(xml):
                tok = m.group(0)
                if tok.startswith('<hp:tbl'):
                    r = re.search(r'rowCnt="(\d+)"', tok); c = re.search(r'colCnt="(\d+)"', tok)
                    stack.append((int(r.group(1)) if r else 1) * (int(c.group(1)) if c else 1) > 2)
                elif tok == '</hp:tbl>':
                    if stack:
                        stack.pop()
                elif tok == '</hp:p>':
                    t = html.unescape(''.join(cur)).strip(); cur = []
                    if t:
                        out.append((TM if any(stack) else '') + t)
                elif m.group(1) is not None:
                    cur.append(m.group(1))
        imgs = [z.read(n) for n in z.namelist() if n.startswith('BinData/') and IMG_RE.search(n)]
    return '\n'.join(out), imgs


def read_docx(data: bytes):
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read('word/document.xml').decode('utf-8', 'ignore')
        imgs = [z.read(n) for n in z.namelist() if n.startswith('word/media/') and IMG_RE.search(n)]
    depth = 0
    for m in re.finditer(r'<w:tbl>|</w:tbl>|<w:p[ >].*?</w:p>', xml, re.S):
        tok = m.group(0)
        if tok == '<w:tbl>':
            depth += 1; continue
        if tok == '</w:tbl>':
            depth -= 1; continue
        t = html.unescape(''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', tok))).strip()
        if t:
            out.append((TM if depth > 0 else '') + t)
    return '\n'.join(out), imgs


def read_xlsx(data: bytes):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows = []
    for ws in wb.worksheets:
        rows.append(f'[시트] {ws.title}')
        for r in ws.iter_rows(values_only=True):
            v = [str(c).strip() for c in r if c is not None and str(c).strip()]
            if v:
                rows.append(TM + ' | '.join(v))
    return '\n'.join(rows), []


def read_pptx(data: bytes):
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        slides = sorted((n for n in z.namelist() if re.match(r'ppt/slides/slide\d+\.xml$', n)),
                        key=lambda n: int(re.search(r'(\d+)', n).group(1)))
        for i, n in enumerate(slides, 1):
            xml = z.read(n).decode('utf-8', 'ignore')
            out.append(f'[슬라이드 {i}]')
            for p in re.findall(r'<a:p>.*?</a:p>', xml, re.S):
                t = html.unescape(''.join(re.findall(r'<a:t>([^<]*)</a:t>', p))).strip()
                if t:
                    out.append(t)
        imgs = [z.read(n) for n in z.namelist() if n.startswith('ppt/media/') and IMG_RE.search(n)]
    return '\n'.join(out), imgs


def read_hml(data: bytes):
    xml = data.decode('utf-8', 'ignore')
    xml = re.sub(r'</P>', '\n', xml)
    return html.unescape(re.sub(r'<[^>]+>', '', xml)), []
