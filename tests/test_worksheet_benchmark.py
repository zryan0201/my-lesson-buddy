"""Data, split and scoring boundaries; these do not prove model accuracy."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from worksheet_benchmark.reading import TOPICS, PROMPT, parse_reading
from worksheet_benchmark.run import load_inputs, run
from worksheet_benchmark.scoring import canonical_expression, numeric_tokens, score_case, score, summarize, validate_dataset
from worksheet_benchmark.normalize import normalize_raw
from worksheet_benchmark.object_counts import parse_counts, COUNT_PROMPT

ROOT=Path(__file__).resolve().parents[1]

def reading(**changes):
    value={'topic':'addition','printed_numbers':['9','7'],'operator_symbols':['+','='],
           'expression':'9+7=?','needs_more_context':False,'task_summary':'Add the two printed numbers.'}
    value.update(changes);return value

def case():
    return {'id':'sample','split':'test','expected':{'topic':'addition','printed_numbers':['9','7'],
            'expression':'9+7=?','operator_symbols':['+','='],'needs_more_context':False,'visual_form':'equation'}}

class ScoringBoundaries(unittest.TestCase):
    def test_object_counts_are_not_inferred_from_answers_and_reject_bad_schema(self):
        raw={'objects':[{'label':'orange','count':16}],'uncertain':False}
        self.assertEqual(parse_counts(json.dumps(raw))['objects'][0]['count'],16)
        self.assertNotIn('orange',COUNT_PROMPT);self.assertNotIn('21',COUNT_PROMPT)
        for value in [dict(raw,objects={'label':'orange','count':16}),dict(raw,objects=[{'label':'orange','count':True}]),dict(raw,objects=[{'label':'orange','count':-1}])]:
            with self.subTest(value=value),self.assertRaises(ValueError):parse_counts(json.dumps(value))
    def test_does_not_reward_solution_instead_of_transcription(self):
        value=score_case(case(),{'status':'accepted','reading':reading(expression='9+7=16')})
        self.assertTrue(value['topic_correct']);self.assertFalse(value['expression_correct'])
        self.assertFalse(value['exact_equation_reading'])

    def test_unknown_operand_position_and_equation_orientation(self):
        self.assertEqual(canonical_expression('? = 37 + 51'),canonical_expression('37+51=□'))
        self.assertNotEqual(canonical_expression('18-?=6'),canonical_expression('18-6=?'))

    def test_errors_and_missing_stay_in_denominator(self):
        values=[score_case(case(),{'status':status}) for status in ['runtime_error','invalid_output','missing','explicit_reject']]
        result=summarize(values,4)
        self.assertEqual(result['topic_accuracy'],{'correct':0,'total':4})
        self.assertEqual(result['source_expression_accuracy'],{'correct':0,'total':4})
        self.assertEqual(result['completed_cases'],3)
        self.assertEqual(result['missing_predictions'],1)

    def test_numeric_recall_is_multiset_partial_not_object_count(self):
        self.assertEqual(numeric_tokens(['1/2','50p','3.5']),numeric_tokens(['1','2','50','3.5']))
        row=score_case(case(),{'status':'accepted','reading':reading(printed_numbers=['9','9','999'])})
        self.assertEqual((row['numeric_hits'],row['numeric_targets']),(1,2))

    def test_runtime_error_is_not_a_correct_context_refusal(self):
        c=case();c['expected']['needs_more_context']=True;c['expected']['topic']='context_needed'
        row=score_case(c,{'status':'runtime_error','reading':reading(needs_more_context=True)})
        self.assertFalse(row['context_refusal_correct'])

    def test_schema_rejects_invented_keys_duplicate_keys_and_bad_types(self):
        for payload in [dict(reading(),answer=16),reading(topic='astronomy'),reading(needs_more_context=1),reading(printed_numbers=[9]),reading(operator_symbols=['plus'])]:
            with self.subTest(payload=payload),self.assertRaises((ValueError,TypeError)):
                parse_reading(json.dumps(payload))
        with self.assertRaises(ValueError):parse_reading('{"topic":"addition","topic":"time"}')
        self.assertEqual(parse_reading(json.dumps(reading(topic='number_line')))['topic'],'number_line')

    def test_engineering_normalization_is_lossless_and_does_not_repair_json(self):
        value=reading(printed_numbers=[80,10],operator_symbols=['÷','='],expression='80÷10=?')
        result,changes=normalize_raw(json.dumps(value))
        self.assertEqual(result['printed_numbers'],['80','10']);self.assertEqual(result['operator_symbols'],['/','='])
        self.assertEqual(result['expression'],'80÷10=?');self.assertEqual(len(changes),2)
        for raw in [str(value),json.dumps(reading(printed_numbers=[True])),json.dumps(dict(value,answer=8))]:
            with self.subTest(raw=raw),self.assertRaises((ValueError,TypeError)):normalize_raw(raw)

class CorpusIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'benchmarks/worksheet_v1';cls.manifest=json.loads((cls.folder/'manifest.json').read_text())

    def test_100_unique_images_grouped_by_source_with_native_grades(self):
        result=validate_dataset(self.manifest,self.folder)
        self.assertEqual(result['cases'],100);self.assertEqual(result['unique_images'],100)
        self.assertFalse(result['split_leakage']);self.assertEqual(result['real_phone_photos'],0)
        rows=self.manifest['cases']
        self.assertEqual(sum(c['source']['key'].startswith('sta_') for c in rows),80)
        self.assertEqual(sum(c['source']['native_grade']=='US Kindergarten' for c in rows),8)
        self.assertEqual(sum(c['source']['native_grade']=='US Grade 1' for c in rows),6)
        self.assertEqual(sum(c['source']['native_grade']=='US Grade 2' for c in rows),6)
        self.assertTrue({c['expected']['topic'] for c in rows}.issubset(TOPICS))

    def test_blind_inputs_contain_no_labels_and_splits_are_disjoint(self):
        data=load_inputs(self.folder/'inputs.json')
        self.assertTrue(all(set(c)=={'id','image','sha256'} for c in data['cases']))
        dev=load_inputs(self.folder/'inputs_development.json');test=load_inputs(self.folder/'inputs_test.json')
        self.assertEqual((len(dev['cases']),len(test['cases'])),(67,33))
        self.assertFalse({c['id'] for c in dev['cases']}&{c['id'] for c in test['cases']})

    def test_no_solution_pages_and_diagram_only_continuation_retained(self):
        for c in self.manifest['cases']:
            self.assertNotIn('IM Commentary',c['expected']['question_text'])
            self.assertNotIn('Edit this solution',c['expected']['question_text'])
        polygon=next(c for c in self.manifest['cases'] if c['source']['pdf_member']=='2.G.A.1_Polygons.pdf')
        self.assertEqual([c['pdf_page'] for c in polygon['source']['crops']],[1,2])
        practice=next(c for c in self.manifest['cases'] if c['source']['key']=='sta_2026_arithmetic' and c['source']['question']=='P')
        self.assertIn('6',practice['expected']['question_text'])
        self.assertIn('2',practice['expected']['question_text'])

    def test_tampering_split_leaks_and_paths_fail(self):
        for change in ['hash','path','split']:
            m=copy.deepcopy(self.manifest)
            if change=='hash':m['cases'][0]['sha256']='0'*64
            elif change=='path':m['cases'][0]['image']='../../README.md'
            else:
                group=m['cases'][0]['source']['pdf_sha256']
                second=next(c for c in m['cases'][1:] if c['source']['pdf_sha256']==group)
                second['split']='development' if second['split']=='test' else 'test'
            with self.subTest(change=change),self.assertRaises(ValueError):validate_dataset(m,self.folder)

    def test_predictions_must_identify_exact_pixels_and_unique_case(self):
        c=self.manifest['cases'][0]
        row={'id':c['id'],'image_sha256':c['sha256'],'status':'accepted','reading':reading(),'run_fingerprint':'a'*64}
        for rows in [[dict(row,image_sha256='changed')],[row,row],[dict(row,id='unknown')]]:
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'predictions.jsonl';path.write_text('\n'.join(json.dumps(x) for x in rows))
                with self.assertRaises(ValueError):score(self.folder/'manifest.json',path,Path(temp))

    def test_stress_cases_are_paired_synthetic_and_do_not_leak_into_test(self):
        folder=self.folder/'stress';m=json.loads((folder/'manifest.json').read_text())
        self.assertEqual(validate_dataset(m,folder)['cases'],30)
        self.assertEqual(len({c['base_id'] for c in m['cases']}),10)
        self.assertEqual({c['split'] for c in m['cases']},{'development'})
        primary={c['id']:c for c in self.manifest['cases']}
        for c in m['cases']:
            self.assertEqual(c['expected']['expression'],primary[c['base_id']]['expected']['expression'])
            self.assertFalse(c['transformation']['handwriting_is_real'])

    def test_count_targets_are_explicitly_partial_and_pixel_bound(self):
        labels=json.loads((self.folder/'object_counts.json').read_text())
        self.assertEqual(len(labels['cases']),8);self.assertEqual(sum(len(c['targets']) for c in labels['cases']),9)
        primary={c['id']:c for c in self.manifest['cases']}
        for c in labels['cases']:
            self.assertEqual(c['image_sha256'],primary[c['id']]['sha256'])
            self.assertFalse(c['independent_teacher_review'])
        oranges=next(t for c in labels['cases'] for t in c['targets'] if t['label']=='visible oranges')
        self.assertEqual(oranges['count'],21)

    def test_runner_passes_only_pixels_to_model_and_resumes(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);image=folder/'image.png';image.write_bytes(b'not needed by mock')
            data={'dataset_id':'mock','cases':[{'id':'blind','image':'image.png','sha256':hashlib.sha256(image.read_bytes()).hexdigest()}]}
            inputs=folder/'inputs.json';inputs.write_text(json.dumps(data));out=folder/'out'
            with patch('worksheet_benchmark.run.LocalReadingProbe') as model:
                model.return_value.metadata={'prompt_sha256':'fixed'}
                model.return_value.predict.return_value={'status':'accepted','reading':reading()}
                run(inputs,out);run(inputs,out)
                model.return_value.predict.assert_called_once_with(image.resolve())
                model.return_value.metadata={'prompt_sha256':'changed'}
                with self.assertRaises(ValueError):run(inputs,out)
            data['cases'][0]['expected_answer']=16;inputs.write_text(json.dumps(data))
            with self.assertRaises(ValueError):load_inputs(inputs)

if __name__=='__main__':unittest.main()
