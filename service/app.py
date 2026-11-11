"""demand_to_deal 웹 API 뼈대 (RFPLens 사용)
실행:  pip install -e ../rfplens[service]  →  uvicorn app:app --reload  (service 폴더에서)
엔드포인트
  GET  /health
  POST /v1/read        파일 1개 업로드 → 판독 결과(FileResult 목록)
  POST /v1/notice      한 공고의 파일 여러 개 업로드 → 판독 + 정책 + 구조화(문서유형·구간 라벨·요구사항 단위)
주의: OCR(Vision)은 macOS 전용. 리눅스 서버는 RFPLENS_OCR=tesseract 와 kor 데이터 설치.
"""
from __future__ import annotations

from fastapi import FastAPI, File, Form, UploadFile

import rfplens

app = FastAPI(title='demand_to_deal · RFPLens API', version=rfplens.__version__)


@app.get('/health')
def health():
    return {'status': 'ok', 'rfplens': rfplens.__version__}


@app.post('/v1/read')
async def read(file: UploadFile = File(...)):
    data = await file.read()
    return [r.to_dict() for r in rfplens.read_bytes(data, file.filename)]


@app.post('/v1/notice')
async def notice(files: list[UploadFile] = File(...), notice_id: str = Form('upload'), include_text: bool = Form(False)):
    payload = [(f.filename, await f.read()) for f in files]
    nr = rfplens.read_uploads(payload, notice_id)
    s2, s3, units = rfplens.structure_notice(nr)
    files_out = []
    for f in nr.files:
        d = f.to_dict()
        if not include_text:
            d.pop('text', None)
        files_out.append(d)
    return {'notice_id': notice_id, 'files': files_out, 'doctypes': s2, 'units': [u.to_row() for u in units]}
