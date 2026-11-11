"""두 저장소(기존 스크립트 결과 vs RFPLens 결과)의 판독·단위 일치 비교 — 이식 검증용
실행: python -m tools.compare_store <기존 store> <새 store> <그룹(예: 2025-01)>
비교: s1 파일별 (status, kind, method, chars, text) / s4-v2 단위(unit_id, label, text)
"""
import gzip
import json
import os
import sys

import pandas as pd


def main(a, b, g):
    da, db = os.path.join(a, 's1_text', g), os.path.join(b, 's1_text', g)
    ids = sorted(f for f in os.listdir(da) if f.endswith('.json.gz'))
    diff, nfile = [], 0
    for f in ids:
        x = json.load(gzip.open(os.path.join(da, f), 'rt'))
        pb = os.path.join(db, f)
        if not os.path.exists(pb):
            diff.append((f, '새 저장소에 없음')); continue
        y = json.load(gzip.open(pb, 'rt'))
        if len(x['files']) != len(y['files']):
            diff.append((f, f"파일 수 {len(x['files'])}→{len(y['files'])}")); continue
        for fx, fy in zip(x['files'], y['files']):
            nfile += 1
            for k in ('name', 'inner', 'status', 'kind', 'method', 'chars', 'text'):
                if fx.get(k) != fy.get(k):
                    diff.append((f, fx['name'], k, str(fx.get(k))[:60], str(fy.get(k))[:60])); break
    print(f's1: 공고 {len(ids)} 파일 {nfile} 불일치 {len(diff)}')
    for d in diff[:20]:
        print('  ', d)
    ua = pd.read_csv(os.path.join(a, 's4_units', 's4-v2', f'{g}.csv.gz'))
    ub = pd.read_csv(os.path.join(b, 's4_units', 's4-v2', f'{g}.csv.gz'))
    m = ua.merge(ub, on='unit_id', how='outer', suffixes=('_a', '_b'), indicator=True)
    only_a, only_b = (m._merge == 'left_only').sum(), (m._merge == 'right_only').sum()
    both = m[m._merge == 'both']
    neq = both[(both.text_a != both.text_b) | (both.section_label_a != both.section_label_b)]
    print(f's4: 기존 {len(ua)} 새 {len(ub)} 기존에만 {only_a} 새에만 {only_b} 내용불일치 {len(neq)}')
    if only_a or only_b:
        print('  기존에만 공고:', sorted(m[m._merge == 'left_only']['공고번호_a'].dropna().unique())[:10])
        print('  새에만 공고:', sorted(m[m._merge == 'right_only']['공고번호_b'].dropna().unique())[:10])


if __name__ == '__main__':
    main(*sys.argv[1:4])
