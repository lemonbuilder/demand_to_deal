"""실행 설정 — 외부 도구 경로, 임계값, 임시 폴더. 환경변수(RFPLENS_*)로 덮어쓸 수 있다."""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent


def _which(*names: str) -> str | None:
    for n in names:
        if n and (os.path.isabs(n) and os.path.exists(n)):
            return n
        p = shutil.which(n) if n else None
        if p:
            return p
    return None


@dataclass
class Settings:
    # 외부 도구
    soffice: str | None = field(default_factory=lambda: os.environ.get('RFPLENS_SOFFICE') or _which('soffice', '/opt/homebrew/bin/soffice', '/Applications/LibreOffice.app/Contents/MacOS/soffice'))
    hwp5txt: str | None = field(default_factory=lambda: os.environ.get('RFPLENS_HWP5TXT') or _which('hwp5txt', os.path.expanduser('~/Library/Python/3.12/bin/hwp5txt')))
    pdftotext: str | None = field(default_factory=lambda: _which('pdftotext'))
    pdftoppm: str | None = field(default_factory=lambda: _which('pdftoppm'))
    pdfinfo: str | None = field(default_factory=lambda: _which('pdfinfo'))
    ocr_backend: str = field(default_factory=lambda: os.environ.get('RFPLENS_OCR', 'vision'))   # vision | tesseract | none
    ocr_binary: str = field(default_factory=lambda: os.environ.get('RFPLENS_OCR_BIN', str(PKG_DIR / 'ocr' / 'bin' / 'ocr_vision')))
    tmp_dir: str = field(default_factory=lambda: os.environ.get('RFPLENS_TMP', tempfile.gettempdir()))
    rules_path: str = field(default_factory=lambda: os.environ.get('RFPLENS_RULES', str(PKG_DIR / 'rules' / 'rules_v1.toml')))
    # 판독 임계값
    min_chars: int = 100            # 이보다 짧으면 '성공-짧은문서'
    page_min: int = 20              # pdf 쪽 텍스트(공백 제외)가 이보다 적으면 OCR
    garbage_max: float = 0.3        # 비정상 문자 비율이 이보다 크면 실패 처리
    small_image_bytes: int = 3000   # 내장 이미지 OCR에서 제외할 작은 이미지
    max_zip_depth: int = 4
    pdf_dpi: int = 200
    tool_timeout: int = 300

    @classmethod
    def from_env(cls) -> 'Settings':
        return cls()


DEFAULT = Settings()
