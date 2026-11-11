"""구조화 2: 요구사항 단위 분할 — 전 문서·전 내용을 단위로 만들고 구간 라벨 부여(제외 없음)"""
from __future__ import annotations

import re

from .models import NoticeResult, Unit
from .rules import Rules, load_rules
from .sections import constraint_text, doctype, marker_type, norm, sectionize

DOC_PRIORITY = {'과업지시서': 0, '제안요청서': 1, '공고문': 2, '기타': 3}


def split_long(text: str, R: Rules):
    if len(text) <= R.unit_max:
        return [text]
    parts, cur = [], ''
    for s in re.split(r'(?<=다\.)\s+|(?<=[.;])\s+(?=[가-힣A-Z(])', text):
        if len(cur) + len(s) > R.unit_max and cur:
            parts.append(cur.strip()); cur = s
        else:
            cur = (cur + ' ' + s).strip()
    if cur:
        parts.append(cur.strip())
    out = []
    for p in parts:
        while len(p) > R.unit_max:
            out.append(p[:R.unit_max]); p = p[R.unit_max:]
        out.append(p)
    return out


def build_units(lines, R: Rules):
    """lines: sectionize 결과 [(mode, marker, body, is_head)]. 반환 [(label, path, text, is_title)]"""
    stack, items = [], []
    for mode, marker, body, is_head in lines:
        mt = marker_type(marker)
        if mt is None and is_head:
            mt = 'bare_head'
        if mt is None:
            if items and items[-1]['mode'] == mode:
                items[-1]['text'] += ' ' + body
            else:
                items.append({'path': [t for _, t in stack], 'text': body, 'lvl': 99, 'mode': mode})
            continue
        lvl = -1 if mt == 'bare_head' else R.rank(mt)
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        items.append({'path': [t for _, t in stack], 'text': body, 'lvl': lvl, 'mode': mode})
        stack.append((lvl, body[:R.head_max]))
    units = []
    for i, it in enumerate(items):
        nxt = items[i + 1] if i + 1 < len(items) else None
        is_title = (nxt is not None and nxt['lvl'] > it['lvl'] and nxt['lvl'] != 99 and len(it['text']) <= R.head_max
                    and nxt['mode'] == it['mode'])
        units.append({'path': ' > '.join(it['path']), 'text': it['text'].strip(), 'mode': it['mode'], 'title': is_title})
    merged = []
    for u in units:
        if merged and len(u['text']) < R.unit_min and merged[-1]['mode'] == u['mode'] and not u['title'] and not merged[-1]['title']:
            merged[-1]['text'] += ' ' + u['text']
        else:
            merged.append(u)
    final = []
    for u in merged:
        if not u['text']:
            continue
        for part in split_long(u['text'], R):
            final.append((R.labels[u['mode']], u['path'], part, int(u['title'])))
    return final


def structure_notice(nr: NoticeResult, R: Rules | None = None):
    """공고 판독 결과 → (문서유형 표 rows, 구간 정보 dict, Unit 목록)"""
    R = R or load_rules()
    no, cid = nr.notice_id, nr.cid
    s2rows, docs, units, seen = [], [], [], set()
    files = sorted(nr.files, key=lambda f: (DOC_PRIORITY.get(doctype(f.inner or f.name, R), 9), f.seq))
    for f in files:
        dt = doctype(f.inner or f.name, R)
        f.doctype = dt
        s2rows.append({'공고번호': no, 'cid': cid, 'seq': f.seq, 'name': f.name, 'inner': f.inner or '', 'ext': f.ext,
                       'kind': f.kind, 'method': f.method, 's1_status': f.status, 'chars': f.chars, 'doctype': dt,
                       'substitute_from': f.substitute_from or ''})
        if not f.ok or not f.text:
            continue
        lines, found = sectionize(f.text, R)
        lab_chars = {}
        for mode, m, b, h in lines:
            lab_chars[R.labels[mode]] = lab_chars.get(R.labels[mode], 0) + len(b)
        docs.append({'seq': f.seq, 'doctype': dt, 'name': f.inner or f.name, 'section_found': found, 'doc_chars': f.chars,
                     'label_chars': lab_chars, 'constraints': constraint_text(f.text, R),
                     'lines': [[R.labels[mode], m, b, int(h)] for mode, m, b, h in lines]})
        k = 0
        for label, path, text, is_title in build_units(lines, R):
            key = norm(text)
            dup = key in seen
            seen.add(key)
            k += 1
            units.append(Unit(unit_id=f'{cid}_{f.seq:02d}_{k:04d}', notice_id=no, cid=cid, doc_seq=f.seq, doctype=dt,
                              section_found=int(found), section_label=label, is_title=is_title, path=path, text=text,
                              chars=len(text), dup_in_notice=int(dup)))
    s3 = {'공고번호': no, 'cid': cid, 'rule_version': R.version, 'docs': docs}
    return s2rows, s3, units
