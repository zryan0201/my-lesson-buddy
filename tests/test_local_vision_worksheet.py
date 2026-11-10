"""The learned image route must not depend on a hand-coded object category."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from lesson_video.local_vision import validate_interpretation
from lesson_video.worksheet import read_worksheet, save_interpretation

ROOT=Path(__file__).resolve().parents[1]


def model_result(a=5,b=2,label='jar',plural='jars'):
    payload={'status':'ready','exercise_count':1,'task_type':'addition',
             'a':a,'b':b,'unknown_operand':False,'printed_answer':None,
             'object_label':label,'object_label_plural':plural,'shape':None,'shape_task':None,
             'task_text':'Two groups separated by a plus and followed by an equals sign.',
             'uncertainty':False,'reason':'Supplied model evidence for an offline integration test.'}
    return {**validate_interpretation(payload),'raw_response':json.dumps(payload),
            'extraction':payload,'reader':'supplied model evidence'}


class LearnedWorksheetIntegrationTests(unittest.TestCase):
    def test_neural_route_counts_from_model_without_calling_the_ocr_rules(self):
        ocr=Mock(side_effect=AssertionError('Legacy OCR must not decide the learned reading.'))
        with patch('lesson_video.local_vision.read_local_vision',return_value=model_result()) as model:
            result=read_worksheet(ROOT/'examples/worksheets/user_popsicle_addition.png',
                                  reader='local-vision',ocr_reader=ocr)
        model.assert_called_once()
        ocr.assert_not_called()
        self.assertEqual(result['method'],'local_pretrained_vision')
        self.assertEqual((result['spec']['a'],result['spec']['b'],result['spec']['answer']),(5,2,7))
        self.assertEqual(len(result['objects']),7)

    def test_missing_graphic_cutouts_do_not_reject_an_unseen_object_category(self):
        with patch('lesson_video.local_vision.read_local_vision',return_value=model_result(2,4,'toy car','toy cars')), \
             patch('lesson_video.worksheet_illustrations.analyze_illustrations',return_value=None):
            result=read_worksheet(ROOT/'examples/vision_eval/case_04.png',reader='local-vision')
        self.assertEqual(result['spec']['answer'],6)
        self.assertEqual(result['objects'],[])
        self.assertIn('dots to stand for',result['spec']['steps'][0]['text'])
        self.assertEqual(result['model_interpretation']['object_label'],'toy car')

    def test_review_keeps_model_name_but_video_does_not_assert_an_unverified_label(self):
        with patch('lesson_video.local_vision.read_local_vision',return_value=model_result()):
            result=read_worksheet(ROOT/'examples/worksheets/user_popsicle_addition.png',reader='local-vision')
        with tempfile.TemporaryDirectory() as temporary:
            report=save_interpretation(result,temporary)
            spec=json.loads((Path(temporary)/'lesson.json').read_text())
            evidence=json.loads((Path(temporary)/'model_interpretation.json').read_text())
            self.assertEqual(evidence['object_label'],'jar')
            self.assertEqual(spec['object_label'],'picture')
            self.assertIn('seven pictures',Path(report['explanation']).read_text())
            self.assertNotIn('jars',Path(report['explanation']).read_text())
            self.assertEqual(len(spec['object_images']),7)


if __name__=='__main__':
    raise SystemExit(unittest.main())
