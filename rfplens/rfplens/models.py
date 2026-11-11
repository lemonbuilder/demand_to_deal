"""결과 데이터 형식. 모든 결과는 to_dict()로 JSON 직렬화 가능(웹 API 응답·저장소 공용)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# 판독 상태
OK = '성공'
OK_SHORT = '성공-짧은문서'          # 정상 판독, 원문 자체가 짧음(MIN 미만)
OK_SUBSTITUTE = '성공-대체원문'      # 핵심문서 판독 불가 → 재공고·다른 차수의 동일 유형 문서로 대체
PASS_NOTICE = '통과-공고문판독불가'   # 공고문만 판독 불가, 같은 공고의 핵심문서는 판독됨 → 이상 아님
PASS_DRM = '통과-DRM(Fasoo)'          # Fasoo DRM 암호화 문서 → 정당한 통과(사용자 결정 2026-11-11, 전체 적용)
PASS_ENC = '통과-암호화'               # 암호화 문서(DRM 업체 무관·사용자 암호 hwp·암호화 OOXML/zip/pdf) → 통과, 나머지 자료로 자료화(사용자 결정 2026-11-11)
PASS_CAD = '통과-도면'                 # CAD 도면(DWG·DXF) 비텍스트 자료 → 통과(사용자 결정 2026-11-11)
FAIL = '실패'


@dataclass
class FileResult:
    name: str                       # 최상위 파일명(공고 폴더 기준)
    inner: str | None = None        # 압축·폴더 내부 경로
    ext: str = ''                   # 확장자(참고용; 판독은 매직 바이트 기준)
    kind: str = ''                  # 판별된 실제 형식(hwp, hwpx, pdf, xlsx, xls, drm …)
    method: str = ''                # 판독 방법(hwp-record, pdftotext+ocr(3쪽), lo-xls->xlsx …)
    status: str = ''
    chars: int = 0
    text: str = ''
    error: str | None = None
    seq: int = 0
    doctype: str = ''               # 문서유형(제안요청서/과업지시서/공고문/기타)
    note: str | None = None
    substitute_from: str | None = None

    @property
    def ok(self) -> bool:
        return self.status.startswith('성공')

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict) -> 'FileResult':
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in keys})


@dataclass
class NoticeResult:
    notice_id: str                  # 공고번호
    cid: str = ''                   # 공고번호-차수
    files: list[FileResult] = field(default_factory=list)
    rule_version: str = ''

    def to_dict(self) -> dict[str, Any]:
        # 저장소 호환 키(공고번호) 유지
        return {'공고번호': self.notice_id, 'cid': self.cid, 'rule_version': self.rule_version,
                'files': [f.to_dict() for f in self.files]}

    @classmethod
    def from_dict(cls, d: dict) -> 'NoticeResult':
        return cls(notice_id=d.get('공고번호') or d.get('notice_id'), cid=d.get('cid', ''),
                   rule_version=d.get('rule_version', ''), files=[FileResult.from_dict(f) for f in d['files']])


@dataclass
class Unit:
    unit_id: str
    notice_id: str
    cid: str
    doc_seq: int
    doctype: str
    section_found: int
    section_label: str              # 과업/일반/개요/행정/서식·붙임/서두
    is_title: int
    path: str
    text: str
    chars: int
    dup_in_notice: int

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d['공고번호'] = d.pop('notice_id')
        order = ['unit_id', '공고번호', 'cid', 'doc_seq', 'doctype', 'section_found', 'section_label', 'is_title',
                 'path', 'text', 'chars', 'dup_in_notice']
        return {k: d[k] for k in order}
