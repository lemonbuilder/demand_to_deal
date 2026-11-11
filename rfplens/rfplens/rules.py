"""규칙 파일(TOML) 로드·컴파일"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import DEFAULT


def _alt(v) -> str:
    return '|'.join(v) if isinstance(v, list) else v


@dataclass
class Rules:
    version: str
    table_mark: str
    doctype_order: list
    doctype_re: dict
    doctype_default: str
    core_doctypes: list
    key_max: int
    body_max: int
    bare_key_max: int
    sentence_end: re.Pattern
    toc_max: int
    toc: re.Pattern
    marker: re.Pattern
    task: re.Pattern
    context: re.Pattern
    admin: re.Pattern
    attachment: re.Pattern
    constraint: re.Pattern
    labels: dict
    rank_map: dict
    rank_default: float
    unit_min: int
    unit_max: int
    head_max: int

    def rank(self, marker_type: str) -> float:
        return self.rank_map.get(marker_type, self.rank_default)


@lru_cache(maxsize=8)
def load_rules(path: str | None = None) -> Rules:
    p = Path(path or DEFAULT.rules_path)
    r = tomllib.loads(p.read_text(encoding='utf-8'))
    dt = r['doctype']
    h = r['heading']
    k = r['keywords']
    rk = dict(r['rank'])
    symbols = rk.pop('symbols', {})
    default = rk.pop('default', 8)
    rank_map = {kk: float(v) for kk, v in rk.items()}
    rank_map.update({f'sym:{s}': float(v) for s, v in symbols.items()})
    return Rules(
        version=r['version'],
        table_mark=r['text']['table_mark'],
        doctype_order=dt['order'],
        doctype_re={t: re.compile(dt[t], re.I) for t in dt['order']},
        doctype_default=dt['default'],
        core_doctypes=dt['core'],
        key_max=h['key_max'], body_max=h['body_max'], bare_key_max=h['bare_key_max'],
        sentence_end=re.compile(h['sentence_end']),
        toc_max=h['toc_max'], toc=re.compile(h['toc']),
        marker=re.compile(r'^\s*(?P<m>' + _alt(h['marker']) + r')\s*'),
        task=re.compile(_alt(k['task'])), context=re.compile(_alt(k['context'])), admin=re.compile(_alt(k['admin'])),
        attachment=re.compile(k['attachment']), constraint=re.compile(_alt(k['constraint'])),
        labels=r['labels'], rank_map=rank_map, rank_default=float(default),
        unit_min=r['units']['min_chars'], unit_max=r['units']['max_chars'], head_max=r['units']['head_max'],
    )
