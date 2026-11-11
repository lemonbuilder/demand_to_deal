# RFPLens

공공조달 RFP 문서(공고문·과업지시서·제안요청서 등) **판독·구조화 엔진** — demand_to_deal 프로젝트 모듈.
hwp(배포용 포함)·hwpx·pdf(스캔 OCR)·doc/docx·xls/xlsx·ppt/pptx·이미지·zip(중첩)·폴더를 빠짐없이 읽고,
내용을 지우지 않은 채 구간 라벨(과업/일반/개요/행정/서식·붙임/서두)과 요구사항 단위로 구조화한다.

## 설치
```bash
pip install -e .                 # 기본
pip install -e .[service]        # 웹 API(FastAPI)까지
python -m rfplens build-ocr      # macOS: Vision OCR 바이너리 빌드(swiftc)
```
시스템 프로그램: poppler(pdftotext·pdftoppm·pdfinfo), LibreOffice(soffice). 리눅스 OCR: tesseract + kor (`RFPLENS_OCR=tesseract`)

## 사용
```python
import rfplens
files = rfplens.read_file('과업지시서.hwp')                  # [FileResult]
nr = rfplens.read_notice('/data/R25BK00588704-000', 'R25BK00588704')
doctypes, sections, units = rfplens.structure_notice(nr)     # units: [Unit(section_label, path, text …)]
result = rfplens.process_notice('/data/공고폴더')             # 판독+구조화 JSON
```
```bash
python -m rfplens read 파일.hwp
python -m rfplens notice 공고폴더 --out 결과.json
python -m rfplens batch --targets census_targets.csv --store 10_store --batch 1 \
       --population population_master.xlsx --raw-root …/raw_documents --raw-root …/raw_documents_excluded
python -m rfplens verify --targets census_targets.csv --store 10_store --batch 1
```

## 시험
```bash
python -m unittest discover -s tests            # 합성 파일 시험
RFPLENS_SAMPLE_ROOT=…/01_sample python -m unittest discover -s tests   # + 1배치 실제 특이 사례
```

설계·알고리즘·1배치 교훈: [docs/설계서.md](docs/설계서.md) · 규칙: [rfplens/rules/rules_v1.toml](rfplens/rules/rules_v1.toml)
