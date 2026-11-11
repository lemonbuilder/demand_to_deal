"""앱·웹 서비스에서 쓰는 공개 함수"""
from __future__ import annotations

import os
import tempfile

from .config import DEFAULT, Settings
from .models import FileResult, NoticeResult, Unit
from .pipeline import read_notice as _read_notice
from .policy import apply_policy
from .reader import Reader
from .rules import load_rules
from .units import structure_notice as _structure


def read_file(path: str, settings: Settings | None = None) -> list[FileResult]:
    """파일(또는 폴더·압축) 1개 판독"""
    return Reader(settings).read_path(path)


def read_bytes(data: bytes, filename: str, settings: Settings | None = None) -> list[FileResult]:
    """업로드된 파일 내용 판독"""
    return Reader(settings).read_bytes(data, filename)


def read_notice(doc_dir: str, notice_id: str | None = None, cid: str = '', settings: Settings | None = None) -> NoticeResult:
    """공고 폴더(공고문·과업지시서·제안요청서 등) 판독 + 정책 적용"""
    return _read_notice(doc_dir, notice_id or os.path.basename(doc_dir.rstrip('/')), cid, settings)


def read_uploads(files: list[tuple[str, bytes]], notice_id: str = 'upload', settings: Settings | None = None) -> NoticeResult:
    """업로드 파일 묶음(한 공고) 판독 — 웹 API용"""
    with tempfile.TemporaryDirectory(dir=(settings or DEFAULT).tmp_dir) as d:
        for name, data in files:
            with open(os.path.join(d, os.path.basename(name)), 'wb') as w:
                w.write(data)
        return _read_notice(d, notice_id, notice_id, settings)


def structure_notice(nr: NoticeResult, settings: Settings | None = None) -> tuple[list[dict], dict, list[Unit]]:
    """판독 결과 → (문서유형 표, 구간 라벨 정보, 요구사항 단위)"""
    return _structure(nr, load_rules((settings or DEFAULT).rules_path))


def process_notice(doc_dir: str, notice_id: str | None = None, settings: Settings | None = None) -> dict:
    """판독 + 구조화 한 번에. JSON 직렬화 가능한 dict 반환"""
    nr = read_notice(doc_dir, notice_id, settings=settings)
    s2, s3, units = structure_notice(nr, settings)
    return {'notice': nr.to_dict(), 'doctypes': s2, 'sections': s3, 'units': [u.to_row() for u in units]}


__all__ = ['read_file', 'read_bytes', 'read_notice', 'read_uploads', 'structure_notice', 'process_notice', 'apply_policy']
