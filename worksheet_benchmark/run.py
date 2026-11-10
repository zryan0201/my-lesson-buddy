"""Resumable label-blind local-model benchmark. Model outputs never execute code."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from .reading import LocalReadingProbe

def load_inputs(inputs_path):
    data=json.loads(inputs_path.read_text());root=inputs_path.parent.resolve()
    identities=set()
    for case in data['cases']:
        if set(case)!= {'id','image','sha256'}:
            raise ValueError('Inference input must contain IDs, image paths and image hashes only, never labels.')
        if case['id'] in identities:raise ValueError('Duplicate input case ID.')
        identities.add(case['id'])
        path=(root/case['image']).resolve()
        if not path.is_relative_to(root):raise ValueError('Image escapes the input directory.')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=case['sha256']:raise ValueError('Input image changed: '+case['id'])
    return data

def run(inputs_path,output,model_path=None,limit=None,*,probe_factory=None):
    data=load_inputs(inputs_path);cases=data['cases'];root=inputs_path.parent.resolve()
    if limit is not None and limit<1:raise ValueError('Limit must be positive.')
    output.mkdir(parents=True,exist_ok=True)
    probe=(probe_factory or LocalReadingProbe)(model_path)
    meta={**probe.metadata,'dataset_id':data['dataset_id'],'inputs_sha256':hashlib.sha256(inputs_path.read_bytes()).hexdigest()}
    key=hashlib.sha256(json.dumps(meta,sort_keys=True).encode()).hexdigest()
    metadata_path=output/'run.json';prediction_path=output/'predictions.jsonl'
    done={}
    if metadata_path.exists():
        old=json.loads(metadata_path.read_text())
        if old.get('run_fingerprint')!=key:raise ValueError('This output belongs to another dataset/model/prompt. Choose a new output folder.')
        for line in prediction_path.read_text().splitlines() if prediction_path.exists() else []:
            value=json.loads(line)
            if value['id'] in done:raise ValueError('Duplicate saved prediction.')
            done[value['id']]=value
    started_at=old['started_at_utc'] if metadata_path.exists() else datetime.now(timezone.utc).isoformat()
    if not set(done).issubset({case['id'] for case in cases}):raise ValueError('Saved output contains unknown case IDs.')
    metadata_path.write_text(json.dumps({**meta,'run_fingerprint':key,'started_at_utc':started_at,'expected_cases':len(cases)},indent=2)+'\n')
    processed=0
    with prediction_path.open('a') as stream:
        for case in cases:
            path=(root/case['image']).resolve()
            if not path.is_relative_to(root):raise ValueError('Image escapes the input directory.')
            actual=hashlib.sha256(path.read_bytes()).hexdigest()
            if actual!=case['sha256']:raise ValueError('Input image changed: '+case['id'])
            if case['id'] in done:
                if done[case['id']]['image_sha256']!=actual:raise ValueError('Saved prediction belongs to different pixels.')
                continue
            if limit is not None and processed>=limit:break
            started=time.monotonic()
            # Strict adapter boundary: no case metadata or answer is passed.
            prediction=probe.predict(path)
            row={'id':case['id'],'image_sha256':actual,'run_fingerprint':key,'seconds':round(time.monotonic()-started,3),**prediction}
            stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
            processed+=1;done[case['id']]=row
            print(json.dumps({'completed':len(done),'total':len(cases),'id':case['id'],'status':row['status'],'seconds':row['seconds']}),flush=True)
    return {'completed':len(done),'expected':len(cases),'predictions':str(prediction_path)}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,default=Path('benchmarks/worksheet_v1/inputs.json'))
    parser.add_argument('--out',type=Path,default=Path('output/worksheet_benchmark/qwen_reading_v1'))
    parser.add_argument('--model-path',type=Path)
    parser.add_argument('--limit',type=int)
    args=parser.parse_args();print(json.dumps(run(args.inputs,args.out,args.model_path,args.limit)))
