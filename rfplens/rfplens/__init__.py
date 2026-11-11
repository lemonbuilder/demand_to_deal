"""RFPLens — 공공조달 RFP 문서 판독·구조화 엔진 (demand_to_deal 프로젝트)

    import rfplens
    files = rfplens.read_file('과업지시서.hwp')            # 판독
    nr = rfplens.read_notice('/path/공고폴더', '공고번호')   # 공고 단위 판독 + 정책
    s2, s3, units = rfplens.structure_notice(nr)           # 문서유형·구간 라벨·요구사항 단위
"""
__version__ = '0.1.0'

from .api import process_notice, read_bytes, read_file, read_notice, read_uploads, structure_notice  # noqa: E402,F401
from .config import Settings  # noqa: E402,F401
