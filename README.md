# demand_to_deal

**Space Demand-to-Deal** — 공공 수요(나라장터 RFP)와 우주기술 보유기업(Supply-side)의 기술역량을 연결해
잠재적 사업기회 후보를 발굴하는 프로젝트의 코드 저장소 (KAIST PMBA 현장적용프로젝트 / UALab 개별연구).

## 모듈
| 폴더 | 내용 | 상태 |
|---|---|---|
| [rfplens/](rfplens/) | **RFPLens** — RFP 문서 판독·구조화 엔진(전수 판독, 구간 라벨, 요구사항 단위) | v0.1.0 |
| [service/](service/) | 웹 API 뼈대(FastAPI, RFPLens 호출) | 뼈대 |
| capability/ | 공급측 기업 Capability DB | 예정 |
| matching/ | 수요–기술 매칭·검증 | 예정 |

## 데이터
원문·저장소 결과는 저장소에 넣지 않는다(.gitignore). 현재 위치:
- 원문: `UALab/000_개별연구/2026_001/05_working/260914_pilot02/01_sample/`
- 전수 분석 작업·저장소: `UALab/000_개별연구/2026_001/05_working/261111_census/`
