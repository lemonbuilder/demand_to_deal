"""파이프라인 — 공고 1건 처리와 배치 병렬 실행
공고 1건: 폴더의 모든 파일 판독(read) → 정책 적용(policy) → 구조화(structure: 문서유형·구간 라벨·단위)
"""
from __future__ import annotations

import os
import time
from multiprocessing import Pool
from typing import Callable, Iterable

from .config import DEFAULT, Settings
from .models import NoticeResult
from .policy import apply_policy
from .reader import Reader
from .rules import load_rules
from .store import Store
from .units import structure_notice


def read_notice(doc_dir: str, notice_id: str, cid: str = '', settings: Settings | None = None,
                candidate_provider: Callable | None = None) -> NoticeResult:
    """공고 폴더 판독(+정책). 폴더 안 숨김 파일 제외 모든 파일·하위 폴더·압축 내부까지."""
    rd = Reader(settings)
    files = []
    for fn in sorted(os.listdir(doc_dir)):
        if fn.startswith('.'):
            continue
        files += rd.read_path(os.path.join(doc_dir, fn), fn)
    for i, f in enumerate(files, 1):
        f.seq = i
    nr = NoticeResult(notice_id=notice_id, cid=cid or notice_id, files=files, rule_version='s1-v2')
    apply_policy(nr, rd, candidate_provider)
    return nr


# ---------- 배치 실행(멀티프로세스) ----------
_CTX = {}


def _init(settings, store_root, group, force, provider_factory):
    _CTX.update(settings=settings, store=Store(store_root), group=group, force=force,
                provider=provider_factory() if provider_factory else None)


def _job_read(row):
    notice_id, cid, doc_dir = row
    st, g = _CTX['store'], _CTX['group']
    p = st.s1_path(g, notice_id)
    if os.path.exists(p) and not _CTX['force']:
        return notice_id, 'skip'
    nr = read_notice(doc_dir, notice_id, cid, _CTX['settings'], _CTX['provider'])
    st.save_s1(g, nr)
    return notice_id, 'done'


def _job_structure(notice_id):
    st, g = _CTX['store'], _CTX['group']
    R = load_rules(_CTX['settings'].rules_path)
    nr = st.load_s1(g, notice_id)
    s2rows, s3, units = structure_notice(nr, R)
    st.write_json_gz(os.path.join(st.s3_dir(R.version, g), f'{notice_id}.json.gz'), s3)
    return s2rows, [u.to_row() for u in units]


def run_read(rows: Iterable[tuple[str, str, str]], store_root: str, group: str, settings: Settings | None = None,
             workers: int = 7, force: bool = False, provider_factory: Callable | None = None, log=print):
    """rows: [(공고번호, cid, 폴더)] → s1 저장"""
    rows = list(rows); t0 = time.time(); n = 0
    with Pool(workers, initializer=_init, initargs=(settings or DEFAULT, store_root, group, force, provider_factory)) as pool:
        for _ in pool.imap_unordered(_job_read, rows, chunksize=4):
            n += 1
            if n % 1000 == 0:
                log(f'read {n}/{len(rows)} {time.time()-t0:.0f}s')
    log(f'read 완료 {n}/{len(rows)} {time.time()-t0:.0f}s')


def run_structure(store_root: str, group: str, settings: Settings | None = None, workers: int = 7, log=print):
    """s1 저장분 → s2/s3/s4 저장"""
    st = Store(store_root); s = settings or DEFAULT
    R = load_rules(s.rules_path)
    ids = st.list_s1(group); t0 = time.time(); all2, all4 = [], []
    with Pool(workers, initializer=_init, initargs=(s, store_root, group, False, None)) as pool:
        for s2rows, rows in pool.imap_unordered(_job_structure, ids, chunksize=8):
            all2 += s2rows; all4 += rows
    st.save_tables(group, R.version, all2, all4)
    log(f'structure 완료 공고 {len(ids)} 파일 {len(all2)} 단위 {len(all4)} {time.time()-t0:.0f}s')
