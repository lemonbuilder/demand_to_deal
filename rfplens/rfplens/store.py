"""저장소 형식(모델·분석방법과 무관한 영구 저장)
<root>/
  s1_text/<그룹>/<공고번호>.json.gz           판독 결과(NoticeResult)
  s2_doctype/<그룹>.csv                        파일별 문서유형
  s3_sections/<rules버전>/<그룹>/<공고번호>.json.gz   줄별 구간 라벨·제약 발췌
  s4_units/<rules버전>/<그룹>.csv.gz             요구사항 단위
그룹: 배치 단위 이름(예: 2025-01). 규칙이 바뀌면 rules 버전 폴더로 분리 보존.
※ 1배치 저장 결과(s3-v2/s4-v2)와 동일 구조. rules-v1 == s3-v2/s4-v2 규칙.
"""
from __future__ import annotations

import gzip
import json
import os

import pandas as pd

from .models import NoticeResult

S3_DIR_FOR = {'rules-v1': 's3-v2'}   # 기존 저장소 폴더명 호환
S4_DIR_FOR = {'rules-v1': 's4-v2'}


class Store:
    def __init__(self, root: str):
        self.root = root

    def s1_path(self, group, notice_id):
        return os.path.join(self.root, 's1_text', group, f'{notice_id}.json.gz')

    def s3_dir(self, rules_version, group):
        return os.path.join(self.root, 's3_sections', S3_DIR_FOR.get(rules_version, rules_version), group)

    def s4_path(self, rules_version, group):
        return os.path.join(self.root, 's4_units', S4_DIR_FOR.get(rules_version, rules_version), f'{group}.csv.gz')

    def s2_path(self, group):
        return os.path.join(self.root, 's2_doctype', f'{group}.csv')

    @staticmethod
    def write_json_gz(path, obj):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with gzip.open(path + '.tmp', 'wt', encoding='utf-8') as g:
            json.dump(obj, g, ensure_ascii=False)
        os.replace(path + '.tmp', path)

    @staticmethod
    def read_json_gz(path):
        with gzip.open(path, 'rt', encoding='utf-8') as g:
            return json.load(g)

    def save_s1(self, group, nr: NoticeResult):
        self.write_json_gz(self.s1_path(group, nr.notice_id), nr.to_dict())

    def load_s1(self, group, notice_id) -> NoticeResult:
        return NoticeResult.from_dict(self.read_json_gz(self.s1_path(group, notice_id)))

    def list_s1(self, group):
        d = os.path.join(self.root, 's1_text', group)
        return sorted(f[:-8] for f in os.listdir(d) if f.endswith('.json.gz')) if os.path.isdir(d) else []

    def save_tables(self, group, rules_version, s2rows, unit_rows):
        os.makedirs(os.path.dirname(self.s2_path(group)), exist_ok=True)
        pd.DataFrame(s2rows).sort_values(['공고번호', 'seq']).to_csv(self.s2_path(group), index=False, encoding='utf-8-sig')
        p = self.s4_path(rules_version, group)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        pd.DataFrame(unit_rows).sort_values('unit_id').to_csv(p, index=False, encoding='utf-8-sig', compression='gzip')
