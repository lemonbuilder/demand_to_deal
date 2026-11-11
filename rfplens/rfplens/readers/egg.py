"""EGG(알집, ESTsoft) 압축 해제 — 공개 형식 사양 기반 최소 구현
지원: 비분할·비솔리드 아카이브, 압축 Store(0)·Deflate(1)·Bzip2(2)·LZMA(4)
미지원(예외): AZO(3, 비공개), 솔리드·분할, 암호화(→ 암호화 통과 정책 대상)
구조: EGG 헤더('EGGA') → [파일 헤더(0x0A8590E3) + 부가필드… END] → [블록 헤더(0x02B50C13) + 데이터]… → END
"""
from __future__ import annotations

import bz2
import lzma
import struct
import zlib

SIG_EGG = 0x41474745
SIG_FILE = 0x0A8590E3
SIG_BLOCK = 0x02B50C13
SIG_END = 0x08E28222
SIG_FILENAME = 0x0A8591AC
SIG_ENCRYPT = 0x08D1470F
SIG_SOLID = 0x24E5A060
SIG_SPLIT = 0x24F5A262


class EggError(Exception):
    pass


class EggEncrypted(EggError):
    pass


def _u(fmt, data, i):
    return struct.unpack_from(fmt, data, i)[0]


def _extra(data, i):
    """부가 필드: sig(4) flag(1) size(2|4) payload"""
    sig = _u('<I', data, i); flag = data[i + 4]
    if flag & 1:
        size = _u('<I', data, i + 5); j = i + 9
    else:
        size = _u('<H', data, i + 5); j = i + 7
    return sig, flag, data[j:j + size], j + size


def _decompress(method, payload, usize):
    if method == 0:
        return payload
    if method == 1:
        return zlib.decompressobj(-15).decompress(payload)
    if method == 2:
        return bz2.decompress(payload)
    if method == 4:
        # EGG LZMA: [버전 2B][props 크기 2B][props 5B] + 원시 스트림
        props = payload[4:9]
        d = props[0]; lc, rem = d % 9, d // 9; lp, pb = rem % 5, rem // 5
        dict_size = _u('<I', props, 1)
        f = [{'id': lzma.FILTER_LZMA1, 'dict_size': dict_size, 'lc': lc, 'lp': lp, 'pb': pb}]
        return lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=f).decompress(payload[9:], max_length=usize)
    raise EggError(f'지원하지 않는 EGG 압축 방식({method}: AZO 등)')


def extract(data: bytes) -> list[tuple[str, bytes]]:
    """반환: [(경로명, 내용)]"""
    if _u('<I', data, 0) != SIG_EGG:
        raise EggError('EGG 헤더 아님')
    i = 4 + 2 + 4 + 4
    while _u('<I', data, i) != SIG_END:            # EGG 헤더 부가 필드
        sig, flag, payload, i = _extra(data, i)
        if sig in (SIG_SOLID, SIG_SPLIT):
            raise EggError('솔리드·분할 EGG 미지원')
    i += 4
    files, cur = [], None
    n = len(data)
    while i + 4 <= n:
        sig = _u('<I', data, i)
        if sig == SIG_FILE:
            i += 4 + 4 + 8
            cur = {'name': '', 'chunks': [], 'enc': False}
            while _u('<I', data, i) != SIG_END:
                s2, flag, payload, i = _extra(data, i)
                if s2 == SIG_FILENAME:
                    k = 0
                    enc = 'utf-8'
                    if flag & 0x08:                    # 지역 인코딩(코드페이지) 사용
                        cp = _u('<H', payload, 0); k = 2
                        enc = 'cp949' if cp in (949, 0) else f'cp{cp}'
                    if flag & 0x10:                    # 상위 폴더 ID
                        k += 4
                    cur['name'] = payload[k:].decode(enc, 'replace')
                elif s2 == SIG_ENCRYPT:
                    cur['enc'] = True
            i += 4
            files.append(cur)
        elif sig == SIG_BLOCK:
            method = data[i + 4]
            usize = _u('<I', data, i + 6); csize = _u('<I', data, i + 10)
            j = i + 4 + 1 + 1 + 4 + 4 + 4
            if _u('<I', data, j) != SIG_END:
                raise EggError('블록 헤더 이상')
            j += 4
            if cur is None:
                raise EggError('파일 헤더 없는 블록')
            cur['chunks'].append((method, data[j:j + csize], usize))
            i = j + csize
        elif sig == SIG_END:
            break
        else:                                          # 주석 등 기타 필드 건너뜀
            _, _, _, i = _extra(data, i)
    out = []
    for f in files:
        if f['enc']:
            raise EggEncrypted('암호가 걸린 EGG 항목')
        out.append((f['name'], b''.join(_decompress(m, p, u) for m, p, u in f['chunks'])))
    return out
