"""판독 결과 정리·품질 검사·상태 판정"""
from __future__ import annotations

import re

from .config import Settings
from .models import FAIL, OK, OK_SHORT

_WEIRD = re.compile(r'[㐀-䶿一-鿿-�]')


def clean(t: str) -> str:
    t = (t or '').encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'replace')
    t = re.sub(r'[ \t ]+', ' ', t)
    return re.sub(r'\n\s*\n+', '\n', t).strip()


def garbage_ratio(t: str) -> float:
    """CJK 한자·사용자정의·대체문자 비율. 바이너리를 텍스트로 잘못 읽으면 급증(예: DRM 파일 → 51%)."""
    s = re.sub(r'\s', '', t)
    if len(s) < 50:
        return 0.0
    return len(_WEIRD.findall(s)) / len(s)


def judge(text: str, error: str | None, method: str, s: Settings) -> tuple[str, str | None]:
    """반환 (status, error)"""
    if not error and garbage_ratio(text) > s.garbage_max:
        error = f'판독 결과 비정상 문자 비율 {garbage_ratio(text):.0%} (방법: {method})'
    if error:
        return FAIL, error
    return (OK if len(text) >= s.min_chars else OK_SHORT), None
