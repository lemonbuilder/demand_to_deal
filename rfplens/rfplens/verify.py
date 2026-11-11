"""판독 검증 — (1) 원본 폴더 파일이 모두 기록됐는지 (2) 이상(실패·부분판독) 0인지 (3) 상태·형식·방법 분포"""
from __future__ import annotations

import collections
import os

from .models import FAIL, OK_SHORT
from .store import Store


def verify_read(store_root: str, group: str, rows) -> dict:
    """rows: [(공고번호, cid, 폴더)]"""
    st = Store(store_root)
    status, kind, meth = collections.Counter(), collections.Counter(), collections.Counter()
    missing_notice, missing_file, fails, partial, short, passed, subst = [], [], [], [], [], [], []
    for no, cid, doc_dir in rows:
        p = st.s1_path(group, no)
        if not os.path.exists(p):
            missing_notice.append(no); continue
        nr = st.load_s1(group, no)
        recorded = {f.name for f in nr.files}
        for fn in sorted(os.listdir(doc_dir)):
            if not fn.startswith('.') and fn not in recorded:
                missing_file.append((no, fn))
        for f in nr.files:
            status[f.status] += 1; kind[f.kind] += 1
            meth[f.method.split('(')[0].split('+')[0]] += 1
            if '+ocr' in f.method or f.method.startswith('ocr'):
                meth['(OCR 사용)'] += 1
            if f.status == FAIL:
                fails.append((no, f.name, f.inner, f.error))
            if 'hwp5txt' in f.method:
                partial.append((no, f.name, f.method))
            if f.status == OK_SHORT:
                short.append((no, f.name, f.inner, f.chars, f.text[:120]))
            if f.status.startswith('통과'):
                passed.append((no, f.name, f.note))
            if f.substitute_from:
                subst.append((no, f.name, f.substitute_from))
    return {'그룹': group, '대상공고': len(list(rows)), '기록없는공고': missing_notice, '기록누락파일': missing_file,
            '상태': dict(status), '형식': dict(kind), '판독방법': dict(meth), '실패': fails, '부분판독(표제외)': partial,
            '짧은문서': short, '통과(공고문판독불가)': passed, '대체원문': subst,
            '이상없음': not (missing_notice or missing_file or fails or partial)}
