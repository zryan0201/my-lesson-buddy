"""Post-hoc engineering diagnostic, not a new model run or the strict baseline.

Only lossless number-string / known operator-glyph normalization is allowed.
No labels, expected answers, case-specific rules, or malformed-JSON repair.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from lesson_video.local_vision import parse_model_response
from .reading import parse_reading

VERSION='lossless-number-string-and-operator-glyph-v1'

def normalize_raw(raw):
    data=parse_model_response(raw);changes=[]
    values=data.get('printed_numbers')
    if isinstance(values,list):
        fixed=[]
        for value in values:
            if type(value) in (int,float) and (not isinstance(value,float) or math.isfinite(value)):
                fixed.append(str(value));changes.append('numeric_value_to_string')
            else:fixed.append(value)
        data['printed_numbers']=fixed
    symbols=data.get('operator_symbols')
    if isinstance(symbols,list):
        mapping={'×':'*','÷':'/','−':'-','–':'-'}
        fixed=[]
        for value in symbols:
            normalized=mapping.get(value,value) if isinstance(value,str) else value
            if normalized!=value:changes.append('operator_glyph_to_ascii')
            fixed.append(normalized)
        data['operator_symbols']=fixed
    return parse_reading(json.dumps(data)),sorted(set(changes))

def normalize_run(source,output):
    if source.resolve()==output.resolve():raise ValueError('Never replace the original baseline.')
    output.mkdir(parents=True,exist_ok=True)
    path=source/'predictions.jsonl';digest=hashlib.sha256(path.read_bytes()).hexdigest()
    fingerprint=hashlib.sha256((digest+VERSION).encode()).hexdigest();rows=[];recovered=0
    for line in path.read_text().splitlines():
        row=json.loads(line)
        if row['status']=='invalid_output' and 'Truncated' not in row.get('error',''):
            try:
                reading,changes=normalize_raw(row['raw_response'])
                row={**row,'original_status':'invalid_output','status':'accepted','reading':reading,
                     'normalizations':changes,'original_error':row.get('error')}
                row.pop('error',None)
                recovered+=1
            except (ValueError,TypeError):pass
        row={**row,'original_run_fingerprint':row['run_fingerprint'],'run_fingerprint':fingerprint}
        rows.append(row)
    (output/'predictions.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    meta=json.loads((source/'run.json').read_text())
    meta.update(run_fingerprint=fingerprint,mode='posthoc_engineering_normalization',normalizer=VERSION,
                original_predictions_sha256=digest,original_run=str(source.resolve()),
                new_model_inferences=0,recovered_format_outputs=recovered,labels_used_for_normalization=False)
    (output/'run.json').write_text(json.dumps(meta,indent=2)+'\n')
    return {'recovered_format_outputs':recovered,'cases':len(rows),'new_model_inferences':0}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=Path('output/worksheet_benchmark/qwen_reading_v1'))
    p.add_argument('--out',type=Path,default=Path('output/worksheet_benchmark/qwen_reading_v1_normalized'))
    a=p.parse_args();print(json.dumps(normalize_run(a.source,a.out)))
