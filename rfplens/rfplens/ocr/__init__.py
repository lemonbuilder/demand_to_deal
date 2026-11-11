"""OCR 엔진 — 교체 가능한 인터페이스
- vision   : macOS Vision(한국어·영어, accurate). 기본값. `rfplens build-ocr`로 바이너리 빌드
- tesseract: 리눅스 서버용(한국어 데이터 kor.traineddata 필요)
- none     : OCR 미사용(필요 시 예외 → 판독 실패로 기록)
엔진 추가: OCRBackend를 상속해 recognize(paths) → [페이지별 텍스트] 구현 후 get_ocr에 등록
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ..config import Settings

HERE = Path(__file__).resolve().parent


class OCRBackend:
    name = 'base'

    def recognize(self, image_paths: list[str]) -> list[str]:
        raise NotImplementedError


class VisionOCR(OCRBackend):
    name = 'vision'

    def __init__(self, binary: str, timeout_per_image: int = 20):
        if not os.path.exists(binary):
            raise RuntimeError(f'Vision OCR 바이너리 없음: {binary} — `python -m rfplens build-ocr` 실행')
        self.binary, self.tpi = binary, timeout_per_image

    def recognize(self, image_paths):
        if not image_paths:
            return []
        r = subprocess.run([self.binary] + list(image_paths), capture_output=True, timeout=60 + self.tpi * len(image_paths))
        out = r.stdout.decode('utf-8', 'ignore').split('\f')
        res = [p.strip() for p in out][:len(image_paths)]
        return ['' if t.startswith('[[OCR_') else t for t in res]


class TesseractOCR(OCRBackend):
    name = 'tesseract'

    def __init__(self, lang: str = 'kor+eng'):
        self.bin = shutil.which('tesseract')
        if not self.bin:
            raise RuntimeError('tesseract 미설치')
        self.lang = lang

    def recognize(self, image_paths):
        res = []
        for p in image_paths:
            r = subprocess.run([self.bin, p, '-', '-l', self.lang], capture_output=True, timeout=120)
            res.append(r.stdout.decode('utf-8', 'ignore').strip())
        return res


class NoOCR(OCRBackend):
    name = 'none'

    def recognize(self, image_paths):
        if image_paths:
            raise RuntimeError('OCR 엔진이 설정되지 않음(RFPLENS_OCR=none)')
        return []


def get_ocr(settings: Settings) -> OCRBackend:
    b = settings.ocr_backend
    if b == 'vision':
        return VisionOCR(settings.ocr_binary)
    if b == 'tesseract':
        return TesseractOCR()
    return NoOCR()


def build_vision(out: str | None = None) -> str:
    """macOS에서 Vision OCR 바이너리 컴파일(swiftc 필요)"""
    out = out or str(HERE / 'bin' / 'ocr_vision')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run(['swiftc', '-O', str(HERE / 'vision.swift'), '-o', out], check=True)
    return out
