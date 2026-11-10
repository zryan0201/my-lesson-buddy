"""Integration checks on a real uploaded worksheet; OCR is supplied offline."""
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from lesson_video.worksheet import WorksheetUnclear, read_worksheet, save_interpretation


INPUT = Path(__file__).resolve().parents[1]/'examples/worksheets/user_popsicle_addition.png'


def supplied_ocr(text='+'):
    return {'engine':'supplied test text, not OCR accuracy', 'text':text,
            'lines':[{'text':text,'confidence':1.0,'bbox':[0,.01,1,.12]}],
            'image_width':520,'image_height':98}


class IllustrationWorksheetTests(unittest.TestCase):
    def test_uploaded_artwork_establishes_five_plus_two_without_typed_operands(self):
        reading=read_worksheet(INPUT,ocr_reader=lambda _:supplied_ocr())
        self.assertEqual(reading['method'],'illustration_groups')
        self.assertEqual((reading['spec']['a'],reading['spec']['b'],reading['spec']['answer']),(5,2,7))
        self.assertEqual(len(reading['objects']),7)
        self.assertTrue(all(o['shape']=='illustration' for o in reading['objects']))
        self.assertTrue(reading['diagram']['repeated_illustrations_verified'])

    def test_wrong_printed_operands_are_not_overridden_by_a_visual_guess(self):
        with self.assertRaisesRegex(WorksheetUnclear,'disagree'):
            read_worksheet(INPUT,ocr_reader=lambda _:supplied_ocr('6 + 1 = ?'))

    def test_wrong_printed_answer_stops_before_video_creation(self):
        with self.assertRaisesRegex(WorksheetUnclear,'printed answer disagrees'):
            read_worksheet(INPUT,ocr_reader=lambda _:supplied_ocr('5 + 2 = 8'))

    def test_conflicting_count_instruction_is_not_overridden_by_diagram_layout(self):
        for text in ('Count 4 objects.','Count four objects.'):
            with self.subTest(text=text), self.assertRaisesRegex(WorksheetUnclear,'printed count disagrees'):
                read_worksheet(INPUT,ocr_reader=lambda _:supplied_ocr(text))

    def test_written_arithmetic_must_agree_with_each_operand_not_just_the_sum(self):
        with self.assertRaisesRegex(WorksheetUnclear,'disagree'):
            read_worksheet(INPUT,ocr_reader=lambda _:supplied_ocr('What is three plus four?'))

    def test_unexplained_printed_number_is_not_silently_ignored(self):
        with self.assertRaisesRegex(WorksheetUnclear,'Additional printed numbers'):
            read_worksheet(INPUT,ocr_reader=lambda _:supplied_ocr('Total 9'))

    def test_missing_addend_is_not_reinterpreted_as_unknown_total(self):
        with self.assertRaises(WorksheetUnclear):
            read_worksheet(INPUT,ocr_reader=lambda _:supplied_ocr('? + 2 = 7'))

    def test_selective_counting_wording_still_requires_review(self):
        with self.assertRaisesRegex(WorksheetUnclear,'color|size|position|marks'):
            read_worksheet(INPUT,ocr_reader=lambda _:supplied_ocr('Count only the yellow pictures.'))

    def test_saved_cutouts_and_narration_preserve_the_actual_source_objects(self):
        reading=read_worksheet(INPUT,ocr_reader=lambda _:supplied_ocr())
        with tempfile.TemporaryDirectory() as temporary:
            report=save_interpretation(reading,temporary)
            spec=json.loads((Path(temporary)/'lesson.json').read_text())
            self.assertEqual(len(spec['object_images']),7)
            self.assertEqual(spec['object_label'],'picture')
            self.assertEqual(spec['answer'],7)
            self.assertIn('pictures',Path(report['explanation']).read_text())
            self.assertNotIn('dots',Path(report['explanation']).read_text())
            for index,path in enumerate(spec['object_images']):
                b=reading['objects'][index]['bbox']
                expected=reading['image'].crop((b['x'],b['y'],b['x']+b['width'],b['y']+b['height']))
                with Image.open(path) as cutout:
                    self.assertEqual(cutout.convert('RGB').tobytes(),expected.tobytes())
            self.assertFalse(list(Path(temporary).glob('*.wav')))
            self.assertFalse(list(Path(temporary).glob('*.mp4')))


if __name__=='__main__':
    unittest.main()
