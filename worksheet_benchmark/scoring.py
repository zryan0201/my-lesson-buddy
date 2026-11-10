"""Conservative, source-scoped metrics. Labels never reach the prediction call."""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from .reading import TOPICS, parse_reading

def numeric_tokens(values):
    # Unify an inline fraction such as '1/2' with two vertically printed tokens.
    # Do not convert spelled-out numbers or infer quantities from objects.
    return Counter(token for value in values if isinstance(value,str)
                   for token in re.findall(r'(?<![\d.])\d+(?:\.\d+)?(?![\d.])',value))

def canonical_expression(value):
    if not isinstance(value,str):return None
    value=value.lower().strip().translate(str.maketrans({'−':'-','–':'-','×':'*','÷':'/'}))
    value=re.sub(r'\s+','',value);value=re.sub(r'_+|□|\[\s*\]','?',value)
    if '=' in value:
        pieces=value.split('=')
        if len(pieces)!=2:return None
        if pieces[0]=='?' and '?' not in pieces[1]:value=pieces[1]+'=?'
    return value

def validate_dataset(manifest, root):
    rows=manifest['cases'];ids=set();hashes=set();groups={};issues=[]
    for case in rows:
        key=case['id'];path=(root/case['image']).resolve()
        if not path.is_relative_to(root.resolve()):raise ValueError('Dataset image escapes its directory.')
        if key in ids:raise ValueError('Duplicate case ID.')
        ids.add(key)
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if actual!=case['sha256']:raise ValueError('Changed input bytes: '+key)
        if actual in hashes:raise ValueError('Duplicate image bytes in primary corpus.')
        hashes.add(actual)
        group=case['source']['pdf_sha256']
        if group in groups and groups[group]!=case['split']:raise ValueError('Source PDF crosses dataset splits.')
        groups[group]=case['split']
        stress=manifest['dataset_id']=='worksheet-stress-v1'
        if case['source_kind']!=('synthetic_derivative' if stress else 'web_pdf_excerpt') or case['real_phone_photo'] is not False:raise ValueError('Source provenance mismatch.')
        if stress and (case['split']!='development' or case['base_id']==case['id'] or not case.get('transformation',{}).get('deterministic')):
            raise ValueError('Stress images must preserve their development base and explicit synthetic provenance.')
        if case['expected']['topic'] not in TOPICS:raise ValueError('Unknown gold topic.')
        if case['expected']['independent_teacher_review'] is not False:issues.append('Review status changed; update dataset audit metadata.')
    return {'cases':len(rows),'unique_ids':len(ids),'unique_images':len(hashes),'source_documents':len(groups),'split_leakage':False,'real_phone_photos':0,'notes':issues}

def score_case(case,prediction):
    expected=case['expected'];status=prediction.get('status','missing')
    accepted=status=='accepted';reading=prediction.get('reading') or {}
    topic=accepted and reading.get('topic')==expected['topic']
    required=numeric_tokens(expected.get('printed_numbers') or [])
    observed=numeric_tokens(reading.get('printed_numbers',[])) if accepted else Counter()
    hits=sum((required&observed).values());total=sum(required.values())
    expression_ok=canonical_expression(reading.get('expression'))==canonical_expression(expected['expression']) if accepted and expected.get('expression') else False
    expected_symbols=expected.get('operator_symbols')
    symbol_ok=set(reading.get('operator_symbols',[]))==set(expected_symbols) if accepted and expected_symbols is not None else False
    semantic = bool(topic and expression_ok) if expected.get('expression') else None
    return {'id':case['id'],'status':status,'topic_correct':bool(topic),'numeric_hits':hits,'numeric_targets':total,
            'expression_scored':expected.get('expression') is not None,'expression_correct':bool(expression_ok),
            'operator_scored':expected_symbols is not None,'operator_correct':bool(symbol_ok),
            'exact_equation_reading':semantic,'requires_context':expected['needs_more_context'],
            'context_refusal_correct':bool(accepted and reading.get('needs_more_context') is True) if expected['needs_more_context'] else None,
            'topic':expected['topic'],'split':case['split'],'visual_form':expected['visual_form'],
            'seconds':prediction.get('seconds'), 'prediction':prediction}

def summarize(rows,expected_total):
    done=[row for row in rows if row['status']!='missing'];counts=Counter(row['status'] for row in rows)
    equations=[row for row in rows if row['expression_scored']];operators=[row for row in rows if row['operator_scored']]
    numeric_total=sum(row['numeric_targets'] for row in rows);numeric_hits=sum(row['numeric_hits'] for row in rows)
    return {'expected_cases':expected_total,'completed_cases':len(done),'status_counts':dict(counts),
            'topic_accuracy':{'correct':sum(row['topic_correct'] for row in rows),'total':len(rows)},
            'printed_number_recall':{'matched_tokens':numeric_hits,'labelled_tokens':numeric_total,'scope':'Text-layer targets on non-equations are partial. Extra predicted diagram numbers are not penalized. This is not an operand/object-count accuracy.'},
            'source_expression_accuracy':{'correct':sum(row['expression_correct'] for row in equations),'total':len(equations)},
            'operator_set_accuracy':{'correct':sum(row['operator_correct'] for row in operators),'total':len(operators)},
            'exact_equation_reading':{'correct':sum(row['exact_equation_reading'] is True for row in equations),'total':len(equations)},
            'runtime_errors':counts.get('runtime_error',0),'invalid_outputs':counts.get('invalid_output',0),
            'missing_predictions':counts.get('missing',0),
            'required_context_detection':{'correct':sum(row['context_refusal_correct'] is True for row in rows),'total':sum(row['requires_context'] for row in rows)},
            'full_task_understanding_accuracy':None,
            'full_task_understanding_note':'Not established by topic or numeric recall. Open tasks retain source text/answer references for human review; current-app support is a separate label.'}

def score(manifest_path:Path,predictions_path:Path,output:Path):
    manifest=json.loads(manifest_path.read_text());audit=validate_dataset(manifest,manifest_path.parent)
    predictions=[]
    for line in predictions_path.read_text().splitlines():
        if line.strip():predictions.append(json.loads(line))
    fingerprints={p.get('run_fingerprint') for p in predictions}
    if len(fingerprints)>1 or predictions and (None in fingerprints or '' in fingerprints):
        raise ValueError('Mixed or missing run fingerprints; model/prompt runs cannot be combined.')
    meta_path=predictions_path.with_name('run.json')
    metadata=json.loads(meta_path.read_text()) if meta_path.exists() else None
    if metadata and predictions and fingerprints!={metadata['run_fingerprint']}:
        raise ValueError('Prediction fingerprint does not match run metadata.')
    cases_by_id={case['id']:case for case in manifest['cases']};ids=set(cases_by_id);mapping={}
    for prediction in predictions:
        identifier=prediction.get('id')
        if identifier not in ids or identifier in mapping:raise ValueError('Unknown or duplicate prediction case ID.')
        if prediction.get('status') not in ['accepted','explicit_reject','invalid_output','runtime_error','cancelled']:raise ValueError('Unsupported prediction status.')
        if prediction['status']=='accepted':parse_reading(json.dumps(prediction.get('reading')))
        case=next(case for case in manifest['cases'] if case['id']==identifier)
        if prediction.get('image_sha256')!=case['sha256']:raise ValueError('Prediction does not identify the exact evaluated image bytes.')
        mapping[identifier]=prediction
    rows=[score_case(case,mapping.get(case['id'],{'status':'missing'})) for case in manifest['cases']]
    report={'schema_version':1,'dataset_id':manifest['dataset_id'],'dataset_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'run_metadata':metadata,'prediction_file_sha256':hashlib.sha256(predictions_path.read_bytes()).hexdigest(),
            'data_audit':audit,'metrics':summarize(rows,len(rows)),
            'splits':{split:summarize([row for row in rows if row['split']==split],sum(row['split']==split for row in rows)) for split in ['development','test']},
            'topics':{topic:summarize([row for row in rows if row['topic']==topic],sum(row['topic']==topic for row in rows)) for topic in sorted({row['topic'] for row in rows})},
            'conditions':{condition:summarize([row for row in rows if cases_by_id[row['id']]['condition']==condition],sum(c['condition']==condition for c in manifest['cases'])) for condition in sorted({c['condition'] for c in manifest['cases']})},
            'limitations':manifest['annotation_limitations'],'cases':rows}
    output.mkdir(parents=True,exist_ok=True)
    (output/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    from .report import write_report
    write_report(report,manifest,manifest_path.parent,output)
    return report
