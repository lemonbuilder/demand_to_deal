"""HWP 5.x 판독 — BodyText(일반) / ViewText(배포용, AES-128 해독) 본문 레코드를 문서 순서대로 읽는다.
- 표 셀 안 문단도 같은 스트림에 있으므로 함께 추출(hwp5txt는 표를 '<표>'로만 출력해 누락됨)
- 칸 3개 이상 표의 셀 문단에는 TABLE_MARK 접두
- 암호 설정 문서(사용자 암호)는 예외
"""
from __future__ import annotations

import re
import struct
import zlib

import olefile

from ..constants import IMG_RE, TABLE_MARK

PARA_TEXT = 67      # HWPTAG_BEGIN(16) + 51
CTRL_HEADER = 71    # 16 + 55
TABLE = 77          # 16 + 61
DIST_DOC_DATA = 28  # 16 + 12
CHAR_CTRL = {0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31}   # 1 wchar 제어문자, 나머지 0~31은 8 wchar


def _records(data: bytes):
    i, n = 0, len(data)
    while i + 4 <= n:
        h = struct.unpack_from('<I', data, i)[0]; i += 4
        tag, level, size = h & 0x3FF, (h >> 10) & 0x3FF, (h >> 20) & 0xFFF
        if size == 0xFFF:
            size = struct.unpack_from('<I', data, i)[0]; i += 4
        yield tag, level, data[i:i + size]
        i += size


def _para_text(b: bytes) -> str:
    out, i, n = [], 0, len(b) // 2
    while i < n:
        c = struct.unpack_from('<H', b, i * 2)[0]
        if c < 32:
            if c in CHAR_CTRL:
                if c in (10, 13):
                    out.append('\n')
                elif c in (24, 30, 31):
                    out.append(' ')
                i += 1
            else:
                if c == 9:
                    out.append('\t')
                i += 8
        else:
            out.append(chr(c)); i += 1
    return ''.join(out)


def _msvc_rand(seed: int):
    state = seed & 0xFFFFFFFF
    while True:
        state = (state * 214013 + 2531011) & 0xFFFFFFFF
        yield (state >> 16) & 0x7FFF


def decrypt_distribution_stream(raw: bytes) -> bytes:
    """배포용 문서 ViewText/SectionN: 첫 레코드(DISTRIBUTE_DOC_DATA 256B)에서 AES-128 키 도출 후 복호화"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    h = struct.unpack_from('<I', raw, 0)[0]
    tag, size = h & 0x3FF, (h >> 20) & 0xFFF
    if tag != DIST_DOC_DATA or size != 256:
        raise ValueError('배포용 문서 헤더 이상')
    data = raw[4:4 + 256]
    seed = struct.unpack_from('<I', data, 0)[0]
    rnd = _msvc_rand(seed)
    mask, i = bytearray(256), 0
    while i < 256:
        a = next(rnd) & 0xFF
        n = (next(rnd) & 0x0F) + 1
        for _ in range(n):
            if i < 256:
                mask[i] = a; i += 1
    dec = bytes(d ^ m for d, m in zip(data, mask))
    off = (seed & 0x0F) + 4
    key = dec[off:off + 16]
    body = raw[4 + 256:]
    body = body[:len(body) - len(body) % 16]
    c = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return c.update(body) + c.finalize()


def hwp_text(path: str) -> str:
    ole = olefile.OleFileIO(path)
    try:
        hdr = ole.openstream('FileHeader').read()
        props = struct.unpack_from('<I', hdr, 36)[0]
        compressed, distributed = bool(props & 1), bool(props & 4)
        if props & 2:
            raise ValueError('암호 설정 문서')
        top = 'ViewText' if distributed else 'BodyText'
        secs = sorted((e for e in ole.listdir() if len(e) == 2 and e[0] == top),
                      key=lambda e: int(e[1].replace('Section', '')))
        paras = []
        for e in secs:
            data = ole.openstream(e).read()
            if distributed:
                data = decrypt_distribution_stream(data)
            if compressed:
                data = zlib.decompressobj(-15).decompress(data)
            stack = []  # [(level, is_multi_cell_table)]
            for tag, level, body in _records(data):
                while stack and level <= stack[-1][0]:
                    stack.pop()
                if tag == CTRL_HEADER and body[:4] == b' lbt':      # 표 컨트롤
                    stack.append([level, None])
                elif tag == TABLE and stack and stack[-1][1] is None and len(body) >= 8:
                    rows, cols = struct.unpack_from('<HH', body, 4)
                    stack[-1][1] = rows * cols > 2
                elif tag == PARA_TEXT:
                    t = _para_text(body).strip()
                    if t:
                        in_table = any(b for _, b in stack)
                        paras.append((TABLE_MARK if in_table else '') + t.replace('\n', '\n' + TABLE_MARK if in_table else '\n'))
        txt = '\n'.join(paras)
        return txt.encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'replace')
    finally:
        ole.close()


def hwp_password_protected(path: str) -> bool:
    """FileHeader 속성 bit1: 사용자 암호 설정 문서"""
    ole = olefile.OleFileIO(path)
    try:
        props = struct.unpack_from('<I', ole.openstream('FileHeader').read(), 36)[0]
        return bool(props & 2)
    finally:
        ole.close()


def hwp_images(path: str) -> list[bytes]:
    """BinData 내장 이미지(압축 시 해제)"""
    o = olefile.OleFileIO(path); imgs = []
    try:
        for e in o.listdir():
            if len(e) == 2 and e[0] == 'BinData' and IMG_RE.search(e[1]):
                b = o.openstream(e).read()
                try:
                    b = zlib.decompressobj(-15).decompress(b) or b
                except Exception:
                    pass
                imgs.append(b)
    finally:
        o.close()
    return imgs
