"""Saved artwork becomes an immutable, bounded guide in reviewed lessons."""
from io import BytesIO, StringIO
from contextlib import redirect_stderr
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

from character_studio.assets import save_character
from lesson_video.characters import draw_character, render_character_image, validate_character
from lesson_video.planner import plan_question
from lesson_video.visuals import render_frame
from lesson_video.web_pipeline import LessonPipeline

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


def _drawing():
    image = Image.new('RGBA', (180, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    d.ellipse((28, 16, 152, 140), fill='#F5A465', outline='#26334B', width=5)
    d.rounded_rectangle((43, 126, 137, 221), radius=25, fill='#8AC9AB', outline='#26334B', width=5)
    d.ellipse((60, 58, 70, 73), fill='#26334B')
    d.ellipse((111, 58, 121, 73), fill='#26334B')
    d.arc((69, 74, 112, 105), 0, 180, fill='#26334B', width=4)
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def _reading():
    return {'question': 'What is 5 + 2?', 'spec': plan_question('What is 5 + 2?'),
            'method': 'local_pretrained_vision', 'objects': [],
            'image': Image.new('RGB', (520, 98), 'white'), 'image_size': [520, 98],
            'reader': 'supplied model evidence', 'source_image': 'test.png', 'crop': None,
            'ocr': {'text': 'Two pictured groups.', 'lines': []}, 'diagram': {}}


class StudioVideoBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = self.root/'library'
        environment = patch.dict(os.environ, {'CHARACTER_STUDIO_STORAGE': str(self.library),
                                              'LESSON_VISION_READER': 'local-vision'})
        environment.start()
        self.addCleanup(environment.stop)
        self.saved = save_character('我的 Buddy', 'drawing', image=_drawing())
        self.config = {'kind': 'studio', 'asset_id': self.saved['id'], 'name': self.saved['name']}
        self.folder = self.root/'lesson'
        self.folder.mkdir()
        self.input = self.folder/'source.png'
        Image.new('RGB', (520, 98), 'white').save(self.input)

    def analyze(self):
        with patch('lesson_video.worksheet.read_worksheet', return_value=_reading()) as reader:
            result = LessonPipeline().analyze(self.input, self.folder, self.config)
        return result, reader

    def test_studio_config_accepts_saved_ids_but_never_file_paths_or_markup(self):
        self.assertEqual(validate_character(self.config), self.config)
        for changes in ({'asset_id': '../character.png'}, {'asset_id': 'A'*32},
                        {'name': '<script>'}, {'name': 'Buddy/file'}, {'name': ''},
                        {'name': 'A'*33}, {'image_path': '/tmp/character.png'}, {'color': '#123456'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_character({**self.config, **changes})

    def test_review_snapshots_artwork_and_does_not_read_the_worksheet_twice(self):
        result, reader = self.analyze()
        reader.assert_called_once_with(self.input, reader='local-vision')
        self.assertEqual(result['answer'], 7)
        snapshot = self.folder/'character.png'
        original = self.library/'characters'/self.saved['id']/'image.png'
        self.assertEqual(snapshot.read_bytes(), original.read_bytes())
        manifest = json.loads((self.folder/'analysis_manifest.json').read_text())
        self.assertIn('character.png', manifest['files'])
        # The source library need not remain present after a reviewed job owns
        # its snapshot; the renderer must use those exact pixels.
        shutil.rmtree(original.parent)
        with patch('character_studio.assets.load_character_image', side_effect=AssertionError('Library reopened')), \
             patch('lesson_video.worksheet.read_worksheet', side_effect=AssertionError('Read twice')), \
             patch('lesson_video.generate.generate') as generate:
            LessonPipeline().render(self.folder, self.config)
            spec = generate.call_args.kwargs['spec']
            preview = render_character_image(spec['character'], asset_path=spec['character_image'])
        self.assertEqual(spec['character_image'], str(snapshot.resolve()))
        self.assertIsNotNone(preview.getbbox())

    def test_changed_artwork_is_rejected_before_rendering(self):
        self.analyze()
        Image.new('RGBA', (600, 800), 'red').save(self.folder/'character.png')
        with patch('lesson_video.generate.generate') as render, self.assertRaisesRegex(ValueError, 'reviewed lesson changed'):
            LessonPipeline().render(self.folder, self.config)
        render.assert_not_called()

    def test_unknown_character_or_wrong_name_is_rejected_before_model_work(self):
        for config in ({**self.config, 'asset_id': '0'*32}, {**self.config, 'name': 'Someone else'}):
            with patch('lesson_video.worksheet.read_worksheet') as reader, self.assertRaises(ValueError):
                LessonPipeline().analyze(self.input, self.folder, config)
            reader.assert_not_called()

    def test_explicit_gemini_reader_is_passed_once_without_running_any_api_in_this_check(self):
        with patch.dict(os.environ, {'LESSON_VISION_READER': 'gemini'}):
            result, reader = self.analyze()
        reader.assert_called_once_with(self.input, reader='gemini')
        self.assertEqual(result['answer'], 7)

    def test_invalid_reader_fails_before_copying_artwork_or_reading_a_model(self):
        with patch.dict(os.environ, {'LESSON_VISION_READER': 'unrecognized-provider'}), \
             patch('lesson_video.worksheet.read_worksheet') as reader, \
             patch('character_studio.assets.snapshot_character') as snapshot, \
             self.assertRaisesRegex(ValueError, 'LESSON_VISION_READER'):
            LessonPipeline().analyze(self.input, self.folder, self.config)
        reader.assert_not_called()
        snapshot.assert_not_called()

    def test_sticker_animation_does_not_invent_a_speaking_mouth_and_stays_in_guide_area(self):
        still = render_character_image(self.config, 210, 420, t=.2)
        speech = render_character_image(self.config, 210, 420, t=.2, talking=True)
        self.assertEqual(still.tobytes(), speech.tobytes())
        moving = render_character_image(self.config, 210, 420, t=.8, celebrate=True)
        self.assertNotEqual(still.tobytes(), moving.tobytes())
        frame = Image.new('RGB', (1280, 720), '#DDEEEE')
        before = frame.copy()
        draw_character(frame, self.config, .8, celebrate=True)
        changed = ImageChops.difference(before, frame).getbbox()
        self.assertGreaterEqual(changed[0], 1040)
        self.assertGreaterEqual(changed[1], 170)
        self.assertLessEqual(changed[2], 1250)
        self.assertLessEqual(changed[3], 590)

    def test_custom_artwork_leaves_math_and_caption_pixels_unchanged(self):
        spec = plan_question('5 + 2')
        events, cursor = [], 0
        for step in spec['steps']:
            events.append({**step, 'start': cursor, 'end': cursor+1, 'duration': 1})
            cursor += 1+step.get('pause_after', .25)
        for event in events:
            t = event['start']+.5
            original = render_frame(spec, events, t, cursor)
            personalized = render_frame({**spec, 'character': copy.deepcopy(self.config)}, events, t, cursor)
            for bounds in ((0, 0, 1040, 720), (0, 625, 1280, 720)):
                self.assertEqual(original.crop(bounds).tobytes(), personalized.crop(bounds).tobytes())

    @unittest.skipIf(AppTest is None, 'Install requirements-web.txt for the lesson interface checks.')
    def test_library_selection_is_preview_only_until_the_read_button_is_clicked(self):
        app_file = Path(__file__).resolve().parents[1]/'streamlit_app.py'
        with patch('lesson_video.web_client.LessonApiClient') as factory:
            client = factory.return_value
            client.create_job.return_value = {'job_id': 'studio_test_job', 'access_token': 'test_token',
                                              'status': 'awaiting_review'}
            client.get_job.return_value = {'job_id': 'studio_test_job', 'status': 'awaiting_review',
                                           'review': {'question': '5 + 2', 'answer': 7, 'steps': []}}
            app = AppTest.from_file(str(app_file)).run(timeout=5)
            app.selectbox(key='friend_kind').select('studio').run(timeout=5)
            self.assertEqual(len(app.exception), 0)
            client.create_job.assert_not_called()
            client.generate.assert_not_called()
            next(button for button in app.button if button.label == 'Read my picture →').click().run(timeout=5)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(client.create_job.call_args.kwargs['character'], self.config)
            self.assertEqual(app.session_state['lesson_job']['character'], self.config)
            client.generate.assert_not_called()

    @unittest.skipIf(AppTest is None, 'Install requirements-web.txt for the lesson interface checks.')
    def test_empty_library_cannot_start_a_lesson(self):
        shutil.rmtree(self.library/'characters')
        app_file = Path(__file__).resolve().parents[1]/'streamlit_app.py'
        with patch('lesson_video.web_client.LessonApiClient') as factory:
            app = AppTest.from_file(str(app_file)).run(timeout=5)
            app.selectbox(key='friend_kind').select('studio').run(timeout=5)
            self.assertEqual(len(app.exception), 0)
            read = next(button for button in app.button if button.label == 'Read my picture →')
            self.assertTrue(read.disabled)
            factory.return_value.create_job.assert_not_called()


class OptionalReaderLauncherTests(unittest.TestCase):
    def test_gemini_requires_enabled_credentials_before_starting_services(self):
        from lesson_video import web
        with patch('sys.argv', ['lesson_video.web', '--reader', 'gemini']), \
             patch('lesson_video.web.importlib.util.find_spec', return_value=object()) as installed, \
             patch('lesson_video.gemini_client.configured', return_value=False), \
             patch('lesson_video.web.subprocess.Popen') as process, \
             redirect_stderr(StringIO()) as output, self.assertRaises(SystemExit) as error:
            web.main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn('GEMINI_ENABLED=1 and GEMINI_API_KEY', output.getvalue())
        self.assertEqual([call.args[0] for call in installed.call_args_list], ['flask', 'streamlit'])
        process.assert_not_called()

    def test_gemini_skips_local_model_preflight_but_still_requires_video_tools(self):
        from lesson_video import web
        with patch('sys.argv', ['lesson_video.web', '--reader', 'gemini']), \
             patch('lesson_video.web.importlib.util.find_spec', return_value=object()) as installed, \
             patch('lesson_video.gemini_client.configured', return_value=True), \
             patch('lesson_video.local_vision.resolve_model_path', side_effect=AssertionError('Local model requested')), \
             patch('lesson_video.web.shutil.which', return_value=None), \
             patch('lesson_video.web.subprocess.Popen') as process, \
             redirect_stderr(StringIO()) as output, self.assertRaises(SystemExit) as error:
            web.main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn('FFmpeg and ffprobe', output.getvalue())
        self.assertNotIn('mlx_vlm', [call.args[0] for call in installed.call_args_list])
        process.assert_not_called()

    def test_invalid_default_reader_is_rejected_without_starting_services(self):
        from lesson_video import web
        with patch.dict(os.environ, {'LESSON_VISION_READER': 'unrecognized-provider'}), \
             patch('sys.argv', ['lesson_video.web']), \
             patch('lesson_video.web.subprocess.Popen') as process, \
             redirect_stderr(StringIO()) as output, self.assertRaises(SystemExit) as error:
            web.main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn('LESSON_VISION_READER', output.getvalue())
        process.assert_not_called()


if __name__ == '__main__':
    unittest.main()
