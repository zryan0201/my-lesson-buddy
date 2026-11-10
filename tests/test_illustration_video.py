"""Real rendered pixels must keep the worksheet artwork and its object count."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from lesson_video.generate import generate, prepare_object_spec
from lesson_video.planner import plan_question
from lesson_video.visuals import object_artwork, render_frame, resized_object


BLUE = (24, 71, 220)
PINK = (220, 23, 137)


def _body_count(image, color):
    # Count source-color bodies from pixels rather than trusting layout indexes.
    pixels = np.asarray(image.crop((140, 221, 971, 455)))
    remaining = np.all(pixels[:, :, :3] == color, axis=2)
    height, width = remaining.shape
    counts = 0
    for y, x in zip(*np.nonzero(remaining)):
        if not remaining[y, x]:
            continue
        pending, area = [(int(y), int(x))], 0
        remaining[y, x] = False
        while pending:
            py, px = pending.pop()
            area += 1
            for ny, nx in ((py-1, px), (py+1, px), (py, px-1), (py, px+1)):
                if 0 <= ny < height and 0 <= nx < width and remaining[ny, nx]:
                    remaining[ny, nx] = False
                    pending.append((ny, nx))
        counts += area >= 70
    return counts


class IllustrationVideoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = []
        for index in range(7):
            image = Image.new('RGB', (50, 70), 'white')
            drawing = ImageDraw.Draw(image)
            color = BLUE if index < 5 else PINK
            drawing.rectangle((21, 48, 28, 62), fill='#BA8743')
            drawing.rounded_rectangle((9, 5, 40, 50), radius=8, fill=color)
            drawing.rectangle((20, 16, 27, 23), fill='white')
            path = self.root/f'picture_{index}.png'
            image.save(path)
            self.paths.append(str(path))

    def _lesson(self, question='5 + 2'):
        spec = plan_question(question)
        required = spec['a'] + (spec['b'] if spec['type'] in ('addition', 'comparison') else 0)
        spec['object_images'] = self.paths[:required]
        spec = prepare_object_spec(spec)
        events, cursor = [], 0.
        for step in spec['steps']:
            event = {**step, 'start': cursor, 'end': cursor+1., 'duration': 1.}
            events.append(event)
            cursor = event['end'] + step.get('pause_after', .25)
        return spec, events, cursor

    def test_five_plus_two_retains_each_extracted_picture_while_counting_and_combining(self):
        spec, events, duration = self._lesson()
        for phase in ('intro', 'group_a', 'group_b', 'count', 'question', 'answer', 'equality'):
            event = next(item for item in events if item['phase'] == phase)
            with self.subTest(phase=phase):
                frame = render_frame(spec, events, event['start']+.5, duration)
                self.assertEqual(_body_count(frame, BLUE), 5)
                self.assertEqual(_body_count(frame, PINK), 2)
                self.assertFalse(np.any(np.all(np.asarray(frame.crop((140, 221, 971, 455))) ==
                                              (255, 201, 40), axis=2)), 'The dot bodies returned.')
        self.assertEqual(spec['answer'], 7)
        self.assertIn('seven pictures', next(e['text'] for e in events if e['phase']=='answer'))

    def test_source_artwork_has_a_highlight_during_each_count(self):
        spec, events, duration = self._lesson()
        count = next(item for item in events if item['phase']=='count' and 'active_index' in item)
        plain = {**count}
        plain.pop('active_index')
        normal_events = [plain if item is count else item for item in events]
        normal = render_frame(spec, normal_events, plain['start']+.5, duration)
        active = render_frame(spec, events, count['start']+.5, duration)
        def green(frame):
            pixels = np.asarray(frame.crop((140, 221, 971, 455))).astype(int)
            return int(np.count_nonzero((pixels[:, :, 1] > pixels[:, :, 0]+30) &
                                        (pixels[:, :, 1] > pixels[:, :, 2]+5)))
        self.assertGreater(green(active), green(normal)+150)
        self.assertEqual((_body_count(active, BLUE), _body_count(active, PINK)), (5, 2))

    def test_subtraction_reuses_only_starting_objects_and_removes_correct_count(self):
        spec, events, duration = self._lesson('5 - 2')
        first = next(item for item in events if item['phase']=='group_a')
        last = next(item for item in events if item['phase']=='answer')
        before = render_frame(spec, events, first['start']+.5, duration)
        after = render_frame(spec, events, last['start']+.5, duration)
        self.assertEqual(_body_count(before, BLUE), 5)
        self.assertEqual(_body_count(after, BLUE), 3)
        self.assertIn('pictures are left', last['text'])

    def test_preserves_white_inside_the_art_and_loads_each_file_once(self):
        object_artwork.cache_clear()
        resized_object.cache_clear()
        with patch('lesson_video.visuals.Image.open', wraps=Image.open) as opened:
            artwork = object_artwork(self.paths[0])
            resized_object(self.paths[0], 30)
            resized_object(self.paths[0], 40)
            object_artwork(self.paths[0])
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(artwork.getpixel((15, 13)), (255, 255, 255, 255))
        self.assertEqual(artwork.getpixel((0, 0))[3], 0)

    def test_preparing_a_lesson_is_idempotent_and_does_not_mutate_it(self):
        original = plan_question('5 + 2')
        original['object_images'] = self.paths
        before = copy.deepcopy(original)
        prepared = prepare_object_spec(original)
        self.assertEqual(original, before)
        self.assertEqual(prepare_object_spec(prepared), prepared)
        self.assertFalse(any('dots' in step['text'] for step in prepared['steps']))

    def test_generation_keeps_supplied_picture_spec_instead_of_replanning_as_dots(self):
        spec, _, _ = self._lesson()
        with patch('lesson_video.generate.plan_question', side_effect=AssertionError('Reparsed picture question')):
            report = generate(spec['question'], self.root/'plan', plan_only=True, spec=spec)
        saved = json.loads(Path(report['plan']).read_text())
        self.assertEqual(saved['object_images'], spec['object_images'])
        self.assertEqual(saved['steps'], spec['steps'])
        self.assertEqual(saved['answer'], 7)

    def test_incomplete_sprite_set_fails_before_writing_or_audio(self):
        spec = plan_question('5 + 2')
        spec['object_images'] = self.paths[:6]
        target = self.root/'must_not_be_created'
        with self.assertRaisesRegex(ValueError, 'exactly 7'):
            generate(spec['question'], target, plan_only=True, spec=spec)
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
