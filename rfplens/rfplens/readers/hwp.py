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


class _Streams:
    """hwp 스트림 접근: 정상 OLE는 olefile, 디렉터리가 깨진 OLE는 원시 섹터에서 디렉터리 항목을 찾아 복구"""

    def __init__(self, path):
        self.ole = olefile.OleFileIO(path)
        self.map = None
        if not self.ole.exists('FileHeader'):
            self.map = _recover_directory(path, self.ole)
            if 'FileHeader' not in self.map:
                self.ole.close()
                raise ValueError('hwp FileHeader 없음(복구 불가)')

    def read(self, entry):
        if self.map is None:
            return self.ole.openstream(entry).read()
        return self.map[entry[-1] if isinstance(entry, list) else entry]

    def sections(self, top):
        if self.map is None:
            return sorted((e for e in self.ole.listdir() if len(e) == 2 and e[0] == top),
                          key=lambda e: int(e[1].replace('Section', '')))
        return [[top, n] for n in sorted((k for k in self.map if k.startswith('Section')), key=lambda k: int(k[7:]))]

    def close(self):
        self.ole.close()


def _recover_directory(path, ole) -> dict:
    """원시 바이트에서 128B 디렉터리 항목 탐색 → 루트(미니스트림)와 각 스트림을 FAT/미니스트림에서 읽음.
    미니FAT이 없으면 미니 섹터가 연속이라고 가정(1배치 이후 2025-11 사례: 헤더의 디렉터리 시작 섹터 오류)."""
    data = open(path, 'rb').read()
    ss = ole.sectorsize
    ents = {}
    root = None
    for off in range(512, len(data) - 127, 128):
        e = data[off:off + 128]
        nl = struct.unpack_from('<H', e, 64)[0]; typ = e[66]
        if not (2 <= nl <= 64 and typ in (1, 2, 5)):
            continue
        try:
            name = e[:nl - 2].decode('utf-16-le')
        except UnicodeDecodeError:
            continue
        if not name.isprintable():
            continue
        start, size = struct.unpack_from('<IQ', e, 116)
        if typ == 5:
            if size > 0:
                root = (start, size)
        elif typ == 2 and name not in ents:
            ents[name] = (start, size)

    def fat_read(start, size):
        out, sect, guard = bytearray(), start, 0
        while sect < 0xFFFFFFFA and len(out) < size and guard < 1_000_000:
            out += data[512 + sect * ss: 512 + (sect + 1) * ss]
            sect = ole.fat[sect] if sect < len(ole.fat) else 0xFFFFFFFE
            guard += 1
        if len(out) < size:                     # FAT 연결이 끊김 → 연속 섹터로 가정
            out = data[512 + start * ss: 512 + start * ss + size]
        return bytes(out[:size])

    mini = fat_read(*root) if root else b''
    res = {}
    for name, (start, size) in ents.items():
        if size >= ole.minisectorcutoff:
            res[name] = fat_read(start, size)
        else:
            res[name] = mini[start * ole.minisectorsize: start * ole.minisectorsize + size]
    return res


def hwp_text(path: str) -> str:
    st = _Streams(path)
    try:
        hdr = st.read('FileHeader')
        props = struct.unpack_from('<I', hdr, 36)[0]
        compressed, distributed = bool(props & 1), bool(props & 4)
        if props & 2:
            raise ValueError('암호 설정 문서')
        top = 'ViewText' if distributed else 'BodyText'
        paras = []
        for e in st.sections(top):
            data = st.read(e)
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
        st.close()


def hwp_password_protected(path: str) -> bool:
    """FileHeader 속성 bit1: 사용자 암호 설정 문서"""
    st = _Streams(path)
    try:
        props = struct.unpack_from('<I', st.read('FileHeader'), 36)[0]
        return bool(props & 2)
    finally:
        st.close()


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
