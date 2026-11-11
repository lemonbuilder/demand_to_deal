"""판독 정책 — 판독 불가 파일을 어떻게 다룰지
0) 암호화 문서(DRM 업체 무관, 사용자 암호 hwp, 암호화 OOXML·zip·pdf) → '통과-암호화' (문서유형 무관, 대체 원문 탐색 안 함;
   같은 공고의 나머지 판독 자료로 자료화. 사용자 결정 2026-11-11)
0-1) CAD 도면(DWG·DXF) → '통과-도면'(비텍스트 자료)
0-2) 원본 손상(빈 파일·전부 0)이고 같은 공고의 핵심문서가 판독되면 → '통과-손상원본'(나머지 자료로 자료화)
1) 공고문만 판독 불가이고 같은 공고의 핵심문서(과업지시서·제안요청서)가 판독되면 → '통과-공고문판독불가'(이상 아님)
2) 핵심문서가 판독 불가이면 → 대체 원문 탐색(같은 공고번호 다른 차수 → 같은 수요기관·유사 공고명 재공고)
   찾으면 '성공-대체원문'(출처 기록), 못 찾으면 '실패' 유지
대체 후보 탐색은 호출자가 제공하는 candidate_provider(notice) → [(cid, 폴더경로)] 로 분리해 서비스 환경에 맞게 교체 가능
"""
from __future__ import annotations

import os
from typing import Callable, Iterable

from .models import FAIL, OK_SUBSTITUTE, PASS_CAD, PASS_DAMAGED, PASS_ENC, PASS_NOTICE, NoticeResult
from .quality import clean, garbage_ratio
from .rules import load_rules
from .sections import doctype


def apply_policy(nr: NoticeResult, reader=None,
                 candidate_provider: Callable[[NoticeResult], Iterable[tuple[str, str]]] | None = None) -> list[tuple]:
    """반환: 적용 기록 [(cid, 파일, 조치, 상세)]"""
    R = load_rules()
    log = []
    core_ok = any(f.ok and doctype(f.inner or f.name, R) in R.core_doctypes for f in nr.files)
    for f in nr.files:
        if f.status != FAIL:
            continue
        if f.kind.startswith('cad'):
            f.note = f'원판독 오류: {f.error}'
            f.status, f.error = PASS_CAD, None
            log.append((nr.cid, f.name, '통과', 'CAD 도면(비텍스트 자료)'))
            continue
        if f.kind.startswith(('drm', 'encrypted')):
            f.note = f'원판독 오류: {f.error}'
            f.status, f.error = PASS_ENC, None
            log.append((nr.cid, f.name, '통과', f'암호화 문서({f.kind}) — 나머지 자료로 자료화'))
            continue
        if f.kind == 'empty' and core_ok:
            f.note = f'원판독 오류: {f.error}'
            f.status, f.error = PASS_DAMAGED, None
            log.append((nr.cid, f.name, '통과', '원본 손상(빈 파일) — 같은 공고의 핵심문서로 자료화'))
            continue
        dt = doctype(f.inner or f.name, R)
        if dt not in R.core_doctypes and core_ok:
            f.note = f'원판독 오류: {f.error}'
            f.status, f.error = PASS_NOTICE, None
            log.append((nr.cid, f.name, '통과', '공고문 등 비핵심 문서 판독 불가, 핵심문서 판독됨'))
            continue
        if reader is None or candidate_provider is None:
            log.append((nr.cid, f.name, '실패 유지', '대체 탐색기 없음'))
            continue
        found = None
        for cid2, folder in candidate_provider(nr):
            for fn in sorted(os.listdir(folder)):
                if fn.startswith('.') or doctype(fn, R) != dt:
                    continue
                for r in reader.read_path(os.path.join(folder, fn), fn):
                    if r.ok and r.chars >= reader.s.min_chars and garbage_ratio(r.text) <= reader.s.garbage_max:
                        found = (cid2, fn, r); break
                if found: break
            if found: break
        if found:
            cid2, fn2, r = found
            f.note = f'원판독 오류: {f.error}'
            f.status, f.error, f.method = OK_SUBSTITUTE, None, f'substitute({r.method})'
            f.substitute_from, f.text, f.chars = f'{cid2}/{fn2}', clean(r.text), len(clean(r.text))
            log.append((nr.cid, f.name, '대체원문', f.substitute_from))
        else:
            log.append((nr.cid, f.name, '실패 유지', '대체 원문 없음'))
    return log
