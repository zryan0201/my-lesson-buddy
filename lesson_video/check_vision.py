"""Run a small, labeled local-model evaluation without showing it the labels."""
import argparse
import json
from pathlib import Path
import time

from .local_vision import LocalVisionError, MODEL_ID, read_local_vision


def main():
    root=Path(__file__).resolve().parent.parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=root/'tests/vision_eval_manifest.json')
    parser.add_argument('--out',type=Path,default=root/'output/local_vision_evaluation')
    parser.add_argument('--vision-model',type=Path)
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text())
    args.out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for case in manifest['cases']:
        start=time.monotonic()
        try:
            # Only the image and generic extraction prompt reach the model.
            reading=read_local_vision(root/case['image'],args.vision_model)
            spec=reading['spec']
            actual={'decision':'accept','type':spec['type'],'a':spec.get('a'),
                    'b':spec.get('b'),'answer':spec['answer']}
            (args.out/f"{case['id']}_model_response.txt").write_text(reading['raw_response']+'\n')
            (args.out/f"{case['id']}_interpretation.json").write_text(json.dumps(reading['extraction'],indent=2)+'\n')
        except LocalVisionError as error:
            actual={'decision':'reject','reason':str(error)}
        expected=case['expected']
        passed=actual['decision']==expected['decision']
        if passed and expected['decision']=='accept':
            passed=all(actual.get(key)==expected[key] for key in ('type','a','b','answer') if key in expected)
        row={'id':case['id'],'image':case['image'],'expected':expected,'actual':actual,
             'passed':passed,'seconds':round(time.monotonic()-start,2)}
        cases.append(row)
        report={'model':MODEL_ID,'paid_api_used':False,'labels_in_prompt':False,
                'caveat':'One actual upload and six synthetic examples; this small smoke test does not establish real-world accuracy.',
                'passed':sum(row['passed'] for row in cases),
                'completed':len(cases),'total':len(manifest['cases']),'cases':cases}
        (args.out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
        print(f"{'PASS' if passed else 'FAIL'} {case['id']}: {actual}",flush=True)
    return 0 if all(case['passed'] for case in cases) else 1


if __name__=='__main__':
    raise SystemExit(main())
