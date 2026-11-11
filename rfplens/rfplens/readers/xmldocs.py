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


def read_xlsx_raw(data: bytes):
    """openpyxl이 거부하는 손상 xlsx용: sharedStrings·시트 XML을 직접 읽어 셀 값 나열"""
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        shared = []
        if 'xl/sharedStrings.xml' in names:
            sx = z.read('xl/sharedStrings.xml').decode('utf-8', 'ignore')
            for si in re.findall(r'<si>(.*?)</si>', sx, re.S):
                shared.append(html.unescape(''.join(re.findall(r'<t[^>]*>([^<]*)</t>', si))))
        sheets = sorted((n for n in names if re.match(r'xl/worksheets/sheet\d+\.xml$', n)),
                        key=lambda n: int(re.search(r'(\d+)', n.rsplit('/', 1)[1]).group(1)))
        for n in sheets:
            out.append(f'[시트] {n.rsplit("/", 1)[1][:-4]}')
            xml = z.read(n).decode('utf-8', 'ignore')
            for row in re.findall(r'<row[^>]*>(.*?)</row>', xml, re.S):
                vals = []
                for attrs, inner in re.findall(r'<c([^>]*)>(.*?)</c>', row, re.S):
                    v = re.search(r'<v>([^<]*)</v>', inner)
                    t = re.search(r'<t[^>]*>([^<]*)</t>', inner)
                    if 't="s"' in attrs and v:
                        k = int(v.group(1)); val = shared[k] if k < len(shared) else ''
                    elif t:
                        val = html.unescape(t.group(1))
                    elif v:
                        val = v.group(1)
                    else:
                        continue
                    if val.strip():
                        vals.append(val.strip())
                if vals:
                    out.append(TM + ' | '.join(vals))
    return '\n'.join(out), []


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
