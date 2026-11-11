"""외부 도구를 쓰는 판독기: pdf(pdftotext + 무텍스트 쪽 OCR), LibreOffice 변환, hwp5txt"""
from __future__ import annotations

import os
import re
import subprocess

from ..config import Settings


def run(cmd, timeout=300) -> str:
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return r.stdout.decode('utf-8', 'ignore')


def read_pdf(path: str, tmpdir: str, ocr, s: Settings):
    """pdftotext로 쪽별 텍스트 → 공백 제외 page_min 미만인 쪽만 렌더링(dpi) 후 OCR. 반환 (text, OCR 쪽수)"""
    txt = run([s.pdftotext, '-q', '-enc', 'UTF-8', path, '-'])
    pages = txt.split('\f')
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    if not pages:
        try:
            n = int(re.search(r'Pages:\s+(\d+)', run([s.pdfinfo, path])).group(1))
        except Exception:
            n = 0
        pages = [''] * n
    need = [i for i, p in enumerate(pages) if len(re.sub(r'\s', '', p)) < s.page_min]
    for k in range(0, len(need), 10):
        chunk = need[k:k + 10]
        imgs = []
        for i in chunk:
            pre = os.path.join(tmpdir, f'pg{i + 1}')
            subprocess.run([s.pdftoppm, '-r', str(s.pdf_dpi), '-png', '-singlefile', '-f', str(i + 1), '-l', str(i + 1), path, pre],
                           capture_output=True, timeout=120)
            imgs.append(pre + '.png')
        res = ocr.recognize([p for p in imgs if os.path.exists(p)])
        for i, t in zip(chunk, res):
            if t:
                pages[i] = t
    return '\n'.join(pages), len(need)


def lo_convert(path: str, target: str, tmpdir: str, s: Settings) -> str:
    """LibreOffice headless 변환. 프로세스별 프로필 사용(병렬 실행 충돌 방지). 반환: 변환 파일 경로"""
    if not s.soffice:
        raise RuntimeError('LibreOffice(soffice) 미설치')
    prof = os.path.join(s.tmp_dir, f'lo_profile_{os.getpid()}')
    outdir = os.path.join(tmpdir, f'lo{abs(hash(path)) % 10**8}')
    os.makedirs(outdir, exist_ok=True)
    subprocess.run([s.soffice, f'-env:UserInstallation=file://{prof}', '--headless', '--convert-to', target, '--outdir', outdir, path],
                   capture_output=True, timeout=s.tool_timeout)
    outs = [os.path.join(outdir, f) for f in os.listdir(outdir)]
    if not outs:
        raise RuntimeError('LibreOffice 변환 실패')
    return outs[0]


def hwp5txt(path: str, s: Settings) -> str:
    if not s.hwp5txt:
        raise RuntimeError('hwp5txt 미설치')
    return run([s.hwp5txt, path])
