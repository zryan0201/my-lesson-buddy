"""Run the real local picture reader on hand-labeled synthetic worksheets."""
import argparse
import json
from pathlib import Path

from .worksheet import read_worksheet,save_interpretation,WorksheetUnclear


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=Path(__file__).resolve().parent.parent/'examples'/'worksheets'/'labels.json')
    parser.add_argument('--out',type=Path,default=Path('output/worksheet_reader/fixture_checks'))
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text())
    rows=[]
    for case in manifest['cases']:
        expected=case['expected']
        try:
            result=read_worksheet(args.manifest.parent/case['image'])
            save_interpretation(result,args.out/case['id'])
            actual={'status':'accept','lesson_type':result['spec']['type'],'answer':result['spec']['answer'],
                    'a':result['spec'].get('a'),'b':result['spec'].get('b'),'question':result['question']}
            if result['spec'].get('shape'):
                actual.update(shape=result['spec']['shape'],shape_task=result['spec']['shape_task'])
            passed=expected['status']=='accept' and all(actual.get(k)==expected[k] for k in ('lesson_type','answer','a','b','shape','shape_task') if k in expected)
        except WorksheetUnclear as exc:
            actual={'status':'reject','reason':str(exc)}
            passed=expected['status']=='reject'
        except Exception as exc:
            actual={'status':'error','reason':f'{type(exc).__name__}: {exc}'}
            passed=False
        rows.append({'id':case['id'],'expected':expected,'actual':actual,'passed':passed})
        print(f"{'PASS' if passed else 'FAIL'} {case['id']}: {actual}",flush=True)
    report={'synthetic':True,'real_photo_accuracy':'not measured','reader':'actual local Apple Vision OCR + diagram analysis',
            'passed':sum(r['passed'] for r in rows),'total':len(rows),'cases':rows}
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['passed']==report['total'] else 1


if __name__=='__main__':
    raise SystemExit(main())
