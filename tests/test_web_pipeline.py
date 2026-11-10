"""Reviewed model output must survive the web read/confirm/render boundary."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from lesson_video.characters import validate_character
from lesson_video.planner import plan_question
from lesson_video.web_pipeline import LessonPipeline


def supplied_reading():
    return {'question':'What is 5 + 2?','spec':plan_question('What is 5 + 2?'),
            'method':'local_pretrained_vision','objects':[],
            'image':Image.new('RGB',(520,98),'white'),'image_size':[520,98],
            'reader':'supplied model evidence','source_image':'test.png','crop':None,
            'ocr':{'text':'Two pictured groups.','lines':[]},'diagram':{}}


class WebPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.image=self.folder/'worksheet.png'
        Image.new('RGB',(520,98),'white').save(self.image)
        self.character=validate_character({'kind':'fox','name':'Sunny','accessory':'glasses'})
        self.pipeline=LessonPipeline()

    def analyze(self):
        with patch('lesson_video.worksheet.read_worksheet',return_value=supplied_reading()) as reader:
            review=self.pipeline.analyze(self.image,self.folder,self.character)
        return review,reader

    def test_reads_once_and_passes_the_reviewed_math_and_character_to_renderer(self):
        review,reader=self.analyze()
        self.assertEqual((review['a'],review['b'],review['answer']),(5,2,7))
        reader.assert_called_once_with(self.image,reader='local-vision')
        with patch('lesson_video.worksheet.read_worksheet',side_effect=AssertionError('Read again after review')), \
             patch('lesson_video.generate.generate') as render:
            self.pipeline.render(self.folder,self.character)
        saved=render.call_args.kwargs['spec']
        self.assertEqual((saved['a'],saved['b'],saved['answer']),(5,2,7))
        self.assertEqual(saved['character'],self.character)
        self.assertEqual([step['text'] for step in saved['steps']],[step['text'] for step in review['steps']])

    def test_changed_plan_is_rejected_before_rendering(self):
        self.analyze()
        plan=self.folder/'lesson.json'
        changed=json.loads(plan.read_text());changed['answer']=9
        plan.write_text(json.dumps(changed))
        with patch('lesson_video.generate.generate') as render, self.assertRaisesRegex(ValueError,'reviewed lesson changed'):
            self.pipeline.render(self.folder,self.character)
        render.assert_not_called()

    def test_changed_source_picture_is_rejected_before_rendering(self):
        self.analyze()
        Image.new('RGB',(520,98),'red').save(self.folder/'worksheet_input.png')
        with patch('lesson_video.generate.generate') as render, self.assertRaisesRegex(ValueError,'reviewed lesson changed'):
            self.pipeline.render(self.folder,self.character)
        render.assert_not_called()

    def test_character_choices_cannot_change_a_job_after_review(self):
        self.analyze()
        changed={**self.character,'kind':'bear'}
        with patch('lesson_video.generate.generate') as render, self.assertRaisesRegex(ValueError,'character changed'):
            self.pipeline.render(self.folder,changed)
        render.assert_not_called()

    def test_invalid_character_is_rejected_before_reading_a_model(self):
        with patch('lesson_video.worksheet.read_worksheet') as reader, self.assertRaises(ValueError):
            self.pipeline.analyze(self.image,self.folder,{'path':'/private/not-a-character'})
        reader.assert_not_called()


if __name__=='__main__':
    unittest.main()
