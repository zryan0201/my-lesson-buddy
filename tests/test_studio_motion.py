"""Joint motion preserves saved designs, reviewed snapshots, and the math area."""
from io import BytesIO
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

from character_studio import assets
from character_studio.motion import design_matches_image, preview_gif, render_motion_frame
from character_studio.parts import catalog, render_design
from lesson_video.characters import render_character_image
from lesson_video.planner import plan_question
from lesson_video.visuals import render_frame
from lesson_video.web_pipeline import LessonPipeline


def _reading():
    return {'question':'What is 5 + 2?', 'spec':plan_question('What is 5 + 2?'),
            'method':'local_pretrained_vision', 'objects':[],
            'image':Image.new('RGB', (520, 98), 'white'), 'image_size':[520, 98],
            'reader':'supplied model evidence', 'source_image':'test.png', 'crop':None,
            'ocr':{'text':'Two pictured groups.', 'lines':[]}, 'diagram':{}}


class JointMotionTests(unittest.TestCase):
    def test_waving_and_celebrating_move_arms_without_resizing_the_head_or_feet(self):
        design = catalog()['presets'][0]['design']
        idle = render_design(design)
        for motion in ('wave', 'celebrate'):
            frame = render_design(design, pose=motion, phase=.25)
            self.assertNotEqual(idle.tobytes(), frame.tobytes())
            for box in ((240, 170, 360, 320), (210, 560, 390, 750), (260, 370, 340, 540)):
                self.assertEqual(idle.crop(box).tobytes(), frame.crop(box).tobytes())
        talking = render_design(design, pose='talk', phase=.25)
        self.assertNotEqual(idle.crop((275, 270, 325, 307)).tobytes(),
                            talking.crop((275, 270, 325, 307)).tobytes())

    def test_all_preset_actions_keep_visible_margins(self):
        for preset in catalog()['presets']:
            for motion in ('idle', 'wave', 'talk', 'celebrate'):
                for phase in (0, .25, .5, .75):
                    frame = render_design(preset['design'], 240, 320, pose=motion, phase=phase)
                    x0, y0, x1, y1 = frame.getbbox()
                    with self.subTest(character=preset['id'], motion=motion, phase=phase):
                        self.assertGreater(x0, 0)
                        self.assertGreater(y0, 0)
                        self.assertLess(x1, 240)
                        self.assertLess(y1, 320)

    def test_invalid_motion_and_unbounded_times_are_rejected(self):
        for value in ('fly', None, {}, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                render_motion_frame({}, value, 0)
        for value in (math.inf, math.nan, '1', True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                render_motion_frame({}, 'wave', value)
            with self.assertRaises(ValueError):
                render_design({}, phase=value)
        with self.assertRaises(ValueError):
            render_motion_frame({}, 'wave', 0, width=100000)

    def test_cached_frames_repeat_safely_and_return_independent_images(self):
        first = render_motion_frame({}, 'wave', .2, 240, 320)
        expected = first.tobytes()
        ImageDraw.Draw(first).rectangle((0, 0, 240, 320), fill='red')
        later = render_motion_frame({}, 'wave', 1600.2, 240, 320)
        self.assertEqual(later.tobytes(), expected)

    def test_design_matching_checks_color_channels_and_preserves_imported_art(self):
        original = render_design({})
        self.assertTrue(design_matches_image({}, original))
        changed = original.copy()
        changed.putpixel((300, 434), (255, 0, 0, 255))
        self.assertFalse(design_matches_image({}, changed))
        self.assertFalse(design_matches_image(None, original))
        self.assertFalse(design_matches_image({}, original.resize((300, 400))))
        # A mismatched imported PNG must produce the identical sticker preview,
        # even when it includes a well-formed editable design in its package.
        self.assertEqual(preview_gif(design={}, image=changed, motion='wave'),
                         preview_gif(image=changed, motion='wave'))

    def test_motion_previews_are_small_animated_gifs(self):
        for motion in ('idle', 'wave', 'talk', 'celebrate'):
            raw = preview_gif(design={}, motion=motion)
            with Image.open(BytesIO(raw)) as gif:
                self.assertEqual(gif.format, 'GIF')
                self.assertEqual(gif.size, (300, 400))
                self.assertGreater(gif.n_frames, 1)
                self.assertLessEqual(gif.n_frames, 12)
                self.assertEqual(gif.info['loop'], 0)
            self.assertLess(len(raw), 2*1024*1024)
        # A space visor blinks its light strip, so even the robot's idle preview
        # remains animated without inventing eyes behind the selected visor.
        with Image.open(BytesIO(preview_gif(design={'eyes':'visor'}))) as gif:
            self.assertGreater(gif.n_frames, 1)


class MotionSnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.library = self.root/'library'
        environment = patch.dict(os.environ, {'CHARACTER_STUDIO_STORAGE':str(self.library),
                                              'LESSON_VISION_READER':'local-vision'})
        environment.start()
        self.addCleanup(environment.stop)
        self.saved = assets.save_character('Nova', 'builder', design={'headwear':'helmet'})
        self.config = {'kind':'studio', 'asset_id':self.saved['id'], 'name':'Nova'}
        self.folder = self.root/'lesson'
        self.folder.mkdir()
        self.input = self.folder/'source.png'
        Image.new('RGB', (520, 98), 'white').save(self.input)

    def analyze(self):
        with patch('lesson_video.worksheet.read_worksheet', return_value=_reading()):
            LessonPipeline().analyze(self.input, self.folder, self.config)
        return json.loads((self.folder/'lesson.json').read_text())

    def test_motion_snapshots_survive_library_removal_and_do_not_read_a_model_twice(self):
        spec = self.analyze()
        snapshot = self.folder/'character_design.json'
        self.assertEqual(spec['character_design'], str(snapshot.resolve()))
        manifest = json.loads((self.folder/'analysis_manifest.json').read_text())
        self.assertIn('character.png', manifest['files'])
        self.assertIn('character_design.json', manifest['files'])
        shutil.rmtree(self.library)
        with patch('character_studio.assets.get_project', side_effect=AssertionError('Library reopened')), \
             patch('character_studio.assets.load_character_image', side_effect=AssertionError('Library reopened')), \
             patch('lesson_video.worksheet.read_worksheet', side_effect=AssertionError('Read twice')), \
             patch('lesson_video.generate.generate') as generate:
            LessonPipeline().render(self.folder, self.config)
            saved = generate.call_args.kwargs['spec']
            still = render_character_image(saved['character'], t=.2,
                                           asset_path=saved['character_image'], design_path=saved['character_design'])
            talking = render_character_image(saved['character'], t=.2, talking=True,
                                             asset_path=saved['character_image'], design_path=saved['character_design'])
        self.assertNotEqual(still.tobytes(), talking.tobytes())

    def test_modified_design_snapshot_is_rejected_before_rendering(self):
        self.analyze()
        snapshot = self.folder/'character_design.json'
        design = json.loads(snapshot.read_text())
        design['primary_color'] = '#FF0000'
        snapshot.write_text(json.dumps(design))
        with patch('lesson_video.generate.generate') as generate, self.assertRaisesRegex(ValueError, 'reviewed lesson changed'):
            LessonPipeline().render(self.folder, self.config)
        generate.assert_not_called()

    def test_legacy_import_with_changed_pixels_falls_back_to_reviewed_sticker(self):
        image_path = assets.character_dir(self.saved['id'])/'image.png'
        image = assets.load_character_image(self.saved['id'])
        ImageDraw.Draw(image).ellipse((290, 420, 320, 450), fill='pink')
        # A portable import can legitimately contain artwork from an older
        # renderer; keep that artwork, even when its design remains editable.
        from character_studio.images import png_bytes
        raw = png_bytes(image)
        project = assets.get_project(self.saved['id'])
        restored = assets._save_artwork('Nova', 'builder', raw, project['design'])
        self.config['asset_id'] = restored['id']
        spec = self.analyze()
        self.assertNotIn('character_design', spec)
        self.assertEqual((self.folder/'character.png').read_bytes(), raw)
        self.assertFalse((self.folder/'character_design.json').exists())

    def test_joint_animation_never_paints_over_worksheet_or_captions(self):
        spec = self.analyze()
        plain = plan_question('5 + 2')
        events, cursor = [], 0
        for step in plain['steps']:
            events.append({**step, 'start':cursor, 'end':cursor+1, 'duration':1})
            cursor += 1+step.get('pause_after', .25)
        for event in events:
            t = event['start']+.3
            original = render_frame(plain, events, t, cursor)
            personalized = render_frame(spec, events, t, cursor)
            for box in ((0, 0, 1040, 720), (0, 625, 1280, 720)):
                self.assertEqual(original.crop(box).tobytes(), personalized.crop(box).tobytes())


if __name__ == '__main__':
    unittest.main()
