"""Local, reproducible worksheet-data tools; no paid service is used."""
import argparse
import json
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('download')
    sub.add_parser('build')
    p=sub.add_parser('validate');p.add_argument('--manifest',type=Path,default=Path('benchmarks/worksheet_v1/manifest.json'))
    p=sub.add_parser('score')
    p.add_argument('--manifest',type=Path,default=Path('benchmarks/worksheet_v1/manifest.json'))
    p.add_argument('--predictions',type=Path,default=Path('output/worksheet_benchmark/qwen_reading_v1/predictions.jsonl'))
    p.add_argument('--out',type=Path,default=Path('output/worksheet_benchmark/qwen_reading_v1'))
    args=parser.parse_args()
    if args.command=='download':
        from .download import download
        result={'sources':len(download())}
    elif args.command=='build':
        from .build import build
        result={'images':len(build()['cases'])}
    elif args.command=='validate':
        from .scoring import validate_dataset
        result=validate_dataset(json.loads(args.manifest.read_text()),args.manifest.parent)
    else:
        from .scoring import score
        result=score(args.manifest,args.predictions,args.out)['metrics']
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
