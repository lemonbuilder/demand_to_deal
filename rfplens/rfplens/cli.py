"""명령줄 인터페이스
  python -m rfplens read <파일|폴더> [--json]           파일 판독 결과 요약(또는 JSON)
  python -m rfplens notice <공고폴더> [--out 결과.json]  공고 1건 판독+구조화
  python -m rfplens batch --targets T.csv --store DIR --batch N [--stage read|structure|all] [--force]
                          [--population P.xlsx --raw-root R1 --raw-root R2]   (대체 원문 탐색용, 선택)
  python -m rfplens verify --targets T.csv --store DIR --batch N [--out 검증.json]
  python -m rfplens build-ocr                           macOS Vision OCR 바이너리 빌드
"""
from __future__ import annotations

import argparse
import functools
import json
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog='rfplens', description='RFPLens: 공공조달 RFP 문서 판독·구조화')
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('read'); a.add_argument('path'); a.add_argument('--json', action='store_true')
    a = sub.add_parser('notice'); a.add_argument('dir'); a.add_argument('--id'); a.add_argument('--out')
    a = sub.add_parser('batch')
    a.add_argument('--targets', required=True); a.add_argument('--store', required=True); a.add_argument('--batch', type=int, required=True)
    a.add_argument('--stage', default='all', choices=['read', 'structure', 'all']); a.add_argument('--force', action='store_true')
    a.add_argument('--workers', type=int, default=7); a.add_argument('--population'); a.add_argument('--raw-root', action='append', default=[])
    a = sub.add_parser('verify')
    a.add_argument('--targets', required=True); a.add_argument('--store', required=True); a.add_argument('--batch', type=int, required=True)
    a.add_argument('--out')
    sub.add_parser('build-ocr')
    args = ap.parse_args(argv)

    if args.cmd == 'read':
        from .api import read_file
        res = read_file(args.path)
        if args.json:
            print(json.dumps([r.to_dict() for r in res], ensure_ascii=False, indent=1))
        else:
            for r in res:
                print(f'{r.status}\t{r.kind}\t{r.method}\t{r.chars}자\t{r.inner or r.name}' + (f'\t{r.error}' if r.error else ''))
    elif args.cmd == 'notice':
        from .api import process_notice
        res = process_notice(args.dir, args.id)
        if args.out:
            json.dump(res, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False)
        n = res['notice']['files']
        print(f"파일 {len(n)} (실패 {sum(f['status'] == '실패' for f in n)}) / 단위 {len(res['units'])}")
    elif args.cmd == 'batch':
        from . import census, pipeline
        group, rows = census.targets(args.targets, args.batch)
        factory = (functools.partial(census.PopulationCandidates, args.population, args.raw_root)
                   if args.population else None)
        if args.stage in ('read', 'all'):
            pipeline.run_read(rows, args.store, group, workers=args.workers, force=args.force, provider_factory=factory)
        if args.stage in ('structure', 'all'):
            pipeline.run_structure(args.store, group, workers=args.workers)
    elif args.cmd == 'verify':
        from . import census
        from .verify import verify_read
        group, rows = census.targets(args.targets, args.batch)
        res = verify_read(args.store, group, rows)
        if args.out:
            json.dump(res, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in res.items()}, ensure_ascii=False, indent=1))
        sys.exit(0 if res['이상없음'] else 1)
    elif args.cmd == 'build-ocr':
        from .ocr import build_vision
        print(build_vision())


if __name__ == '__main__':
    main()
