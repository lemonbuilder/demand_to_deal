"""구조화 1: 문서유형 판별, 제목 판별·위계, 구간 모드 부여(내용 라벨링)
구간 모드: TASK(과업) / NEUTRAL(행정·개요 뒤 일반 제목) / CTX(개요) / EXCL(행정) / HARD(붙임·서식 이후) / NONE(첫 제목 전)
- 어떤 줄도 지우지 않는다(목차 줄도 NONE 등 현재 모드로 남김: rules-v1에서는 v1 호환을 위해 목차 줄을 'toc' 표시 후 유지)
"""
from __future__ import annotations

import re

from .rules import Rules, load_rules


def norm(s: str) -> str:
    return re.sub(r'\s+', '', s)


def doctype(name: str, R: Rules | None = None) -> str:
    R = R or load_rules()
    n = name or ''
    for t in R.doctype_order:
        if R.doctype_re[t].search(n):
            return t
    return R.doctype_default


def split_marker(line: str, R: Rules):
    m = R.marker.match(line)
    if not m or m.end() == 0:
        return '', line.strip()
    return m.group('m').strip(), line[m.end():].strip()


def is_heading(marker: str, body: str, R: Rules) -> bool:
    key = re.split(r'[:：]', body)[0].strip()
    if len(body) == 0 or len(key) > R.key_max or len(body) > R.body_max:
        return False
    if not marker and len(norm(key)) > R.bare_key_max:
        return False
    if R.sentence_end.search(body):
        return False
    return True


def heading_class(body: str, R: Rules):
    key = norm(re.split(r'[:：]', body)[0])
    if not key:
        return None
    if R.admin.search(key):
        return 'EXCL'
    if R.task.search(key):
        return 'TASK'
    if R.context.search(key):
        return 'CTX'
    return None


def marker_type(m: str):
    if not m: return None
    if re.match(r'제\s*\d', m): return 'chap'
    if re.match(r'[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX]', m): return 'roman'
    if re.match(r'\d+\s*[.]\s*\d', m): return 'num_sub'
    if re.match(r'\d+\s*[.]$', m): return 'num_dot'
    if re.match(r'\(\s*\d', m): return 'num_pp'
    if re.match(r'\d+\s*\)', m): return 'num_p'
    if re.match(r'[가-하]\s*[.]$', m): return 'han_dot'
    if re.match(r'\(\s*[가-하]', m): return 'han_pp'
    if re.match(r'[가-하]\s*\)', m): return 'han_p'
    if re.match(r'[①-⑳]', m): return 'circ'
    if re.match(r'[㉠-㉭]', m): return 'circ_han'
    if re.match(r'[a-z]', m): return 'alpha'
    if re.match(r'[-\U000f0000-\U000fffff]', m): return 'pua'
    if re.match(r'[➊-➓⑴-⒇]', m): return 'circ'
    return 'sym:' + m[0]


def sectionize(text: str, R: Rules | None = None, keep_toc: bool = False):
    """줄별 (mode, marker, body, switched) 목록과 과업 제목 발견 여부 반환.
    계층 반영: TASK 구간 안의 하위 제목은 모드 유지. 비TASK 구간에서 같거나 상위 수준 일반 제목이면 NEUTRAL 복귀.
    keep_toc=False: rules-v1(1배치 저장 결과)과 동일하게 목차 줄을 건너뜀."""
    R = R or load_rules()
    TM = R.table_mark
    mode, task_lvl, cur_lvl = 'NONE', None, None
    out, found_task = [], False
    for raw in text.split('\n'):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(TM):  # 표 셀: 제목 판별 없이 현재 모드로 포함
            body = line.lstrip(TM).strip()
            if body:
                out.append((mode, '', body, False))
            continue
        marker, body = split_marker(line, R)
        if len(body) <= R.toc_max and R.toc.search(body) and re.search(r'[가-힣]', body):
            if keep_toc:
                out.append((mode, marker, body, False))
            continue
        head = is_heading(marker, body, R)
        cls = heading_class(body, R) if head else None
        mt = marker_type(marker)
        lvl = (-1 if head else None) if mt is None else R.rank(mt)
        switched = False
        if head:
            if mode == 'TASK' and cls != 'TASK' and lvl is not None and task_lvl is not None and lvl > task_lvl:
                pass
            elif cls == 'TASK':
                if mode != 'TASK' or task_lvl is None or (lvl is not None and lvl < task_lvl):
                    task_lvl = lvl
                mode, found_task, switched = 'TASK', True, True
            elif cls == 'EXCL':
                mode = 'HARD' if R.attachment.search(body) else ('HARD' if mode == 'HARD' else 'EXCL')
                cur_lvl, task_lvl, switched = lvl, None, True
            elif cls == 'CTX':
                if mode != 'HARD':
                    mode, cur_lvl, task_lvl, switched = 'CTX', lvl, None, True
            else:
                if mode in ('EXCL', 'CTX') and lvl is not None and cur_lvl is not None and lvl <= cur_lvl:
                    mode, cur_lvl, switched = 'NEUTRAL', lvl, True
        out.append((mode, marker, body, switched))
    return out, found_task


def constraint_text(text: str, R: Rules | None = None, cap: int = 3000) -> str:
    """참가자격·계약방법 등 제약 구간 발췌(공고문·RFP 공통)"""
    R = R or load_rules()
    TM = R.table_mark
    keep, on = [], False
    for raw in text.split('\n'):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(TM):
            if on:
                keep.append(line.lstrip(TM).strip())
            continue
        marker, body = split_marker(line, R)
        if is_heading(marker, body, R):
            on = bool(R.constraint.search(norm(body))) or (on and not heading_class(body, R))
        if on:
            keep.append(line)
    return '\n'.join(keep)[:cap]
