"""나라장터 전수 분석 어댑터(현장적용프로젝트 2025 전수 데이터용)
- 대상 목록: census_targets.csv (공고번호, cid, batch, batch_ym, doc_dir, in_scope …)
- 대체 원문 후보: population_master.xlsx 기반(같은 공고번호 다른 차수 → 같은 수요기관·유사 공고명)
"""
from __future__ import annotations

import os
import re

import pandas as pd


def targets(targets_csv: str, batch: int):
    t = pd.read_csv(targets_csv)
    t = t[(t.batch == batch) & (t.in_scope)]
    return t.batch_ym.iloc[0], [(r.공고번호, r.cid, r.doc_dir) for r in t.itertuples()]


def _toks(s):
    return set(re.findall(r'[가-힣A-Za-z0-9]{2,}', str(s)))


class PopulationCandidates:
    """policy.apply_policy용 candidate_provider: 재공고·다른 차수 폴더 후보(공고일이 가까운 순)"""

    def __init__(self, population_xlsx: str, raw_roots: list[str]):
        self.xlsx, self.roots, self._pop = population_xlsx, raw_roots, None   # 판독 불가가 있을 때만 지연 로드

    @property
    def pop(self):
        if self._pop is None:
            pop = pd.read_excel(self.xlsx, usecols=['공고번호', '공고차수', '공고명', '수요기관', '공고일'])
            pop['cid'] = pop['공고번호'].astype(str) + '-' + pd.to_numeric(pop['공고차수'], errors='coerce').fillna(0).astype(int).astype(str).str.zfill(3)
            self._pop = pop
        return self._pop

    def _folders(self, cid):
        out = []
        for r in self.roots:
            for m in os.listdir(r):
                p = os.path.join(r, m, cid)
                if os.path.isdir(p):
                    out.append(p)
        return out

    def __call__(self, nr):
        pop = self.pop
        me = pop[pop.cid == nr.cid]
        if me.empty:
            return []
        me = me.iloc[0]
        a = _toks(me.공고명)

        def similar(n):
            b = _toks(n)
            return bool(a and b) and (a <= b or b <= a or len(a & b) / len(a | b) >= 0.6)
        same_no = pop[(pop.공고번호 == nr.notice_id) & (pop.cid != nr.cid)]
        rel = pop[(pop.수요기관 == me.수요기관) & (pop.공고번호 != nr.notice_id) & pop.공고명.map(similar)]
        c = pd.concat([same_no.assign(pri=0), rel.assign(pri=1)])
        c = c.assign(gap=(pd.to_datetime(c.공고일) - pd.to_datetime(me.공고일)).abs()).sort_values(['pri', 'gap'])
        for r in c.itertuples():
            for f in self._folders(r.cid):
                yield r.cid, f
