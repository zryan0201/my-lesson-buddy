"""Character settings, visible personalization, and worksheet isolation."""
import unittest

import numpy as np
from PIL import Image, ImageChops

from lesson_video.characters import (
    character_catalog, draw_character, render_character_image, validate_character,
)
from lesson_video.planner import plan_question
from lesson_video.visuals import render_frame


def _image(**choices):
    return render_character_image(choices, width=300, height=500)


class CharacterTests(unittest.TestCase):
    def test_options_are_independent_and_settings_are_normalized(self):
        config = {"name": "  Blue Buddy  ", "color": "#abcdef"}
        normalized = validate_character(config)
        self.assertEqual(normalized["color"], "#ABCDEF")
        self.assertEqual(normalized["name"], "Blue Buddy")
        self.assertEqual(normalized["kind"], "robot")
        self.assertEqual(config["name"], "  Blue Buddy  ")
        catalog = character_catalog()
        catalog["default"]["name"] = "Changed"
        catalog["kinds"].clear()
        self.assertEqual(character_catalog()["default"]["name"], "Buddy")
        self.assertEqual(len(character_catalog()["kinds"]), 3)

    def test_untrusted_options_cannot_request_files_or_inject_markup(self):
        invalid = [None, [], "robot", True, {"unknown": "x"}, {"image": "/tmp/picture.png"},
                   {"kind": True}, {"kind": "pencil"}, {"outfit": []}, {"outfit": "jacket"},
                   {"accessory": "../cap"}, {"name": "<script>"}, {"name": "a/b"},
                   {"name": "../Buddy"}, {"name": "Buddy\\hat"}, {"name": "A"*25},
                   {"name": ""}, {"name": False}, {"name": "Hello\nthere"},
                   {"color": True}, {"color": "red"}, {"color": "#12345"},
                   {"outfit_color": [1, 2, 3]}, {1: "robot"}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_character(value)

    def test_base_shapes_and_color_choices_are_visibly_distinct(self):
        fingerprints = set()
        for kind in ("robot", "fox", "bear"):
            first = _image(kind=kind, color="#167BC2")
            second = _image(kind=kind, color="#E56B65")
            pixels = np.asarray(first)
            self.assertEqual(first.mode, "RGBA")
            self.assertGreater(np.count_nonzero(np.all(pixels[:, :, :3] == (22, 123, 194), axis=2)), 2500)
            changed = np.any(np.asarray(first) != np.asarray(second), axis=2)
            self.assertGreater(np.count_nonzero(changed), 5000)
            fingerprints.add(first.tobytes())
        self.assertEqual(len(fingerprints), 3)

    def test_clothes_and_accessories_are_visible_on_every_base(self):
        for kind in ("robot", "fox", "bear"):
            bare = _image(kind=kind, outfit="none", accessory="none")
            for outfit in ("shirt", "overalls"):
                dressed = _image(kind=kind, outfit=outfit, outfit_color="#FA3174")
                pink = np.all(np.asarray(dressed)[:, :, :3] == (250, 49, 116), axis=2)
                self.assertGreater(np.count_nonzero(pink), 2500)
                self.assertIsNotNone(ImageChops.difference(bare, dressed).getbbox())
            for accessory in ("cap", "glasses", "bow"):
                accessorized = _image(kind=kind, outfit="none", accessory=accessory)
                diff = np.any(np.asarray(bare) != np.asarray(accessorized), axis=2)
                self.assertGreater(np.count_nonzero(diff), 800, (kind, accessory))

    def test_mouth_blink_point_and_celebration_animate(self):
        for kind in ("robot", "fox", "bear"):
            config = {"kind": kind}
            still = render_character_image(config, 300, 500)
            for mode in ({"talking": True}, {"pointing": True}, {"celebrate": True}, {"t": 3.99}):
                animated = render_character_image(config, 300, 500, **mode)
                self.assertNotEqual(still.tobytes(), animated.tobytes(), (kind, mode))

    def test_every_pose_fits_the_guide_area_and_leaves_transparent_margins(self):
        for kind in ("robot", "fox", "bear"):
            for accessory in ("none", "cap", "glasses", "bow"):
                for celebrate, pointing in ((False, False), (False, True), (True, False)):
                    sprite = render_character_image({"kind": kind, "accessory": accessory}, 210, 420,
                                                    t=.25, celebrate=celebrate, pointing=pointing)
                    box = sprite.getbbox()
                    self.assertGreater(box[0], 0)
                    self.assertLess(box[2], 210)
                    self.assertGreater(box[1], 0)
                    self.assertLess(box[3], 420)
                    frame = Image.new("RGB", (1280, 720), "#DDEEEE")
                    before = frame.copy()
                    draw_character(frame, {"kind": kind, "accessory": accessory}, .25,
                                   celebrate=celebrate, pointing=pointing)
                    changed = ImageChops.difference(before, frame).getbbox()
                    self.assertGreaterEqual(changed[0], 1040)
                    self.assertGreaterEqual(changed[1], 170)
                    self.assertLessEqual(changed[2], 1250)
                    self.assertLessEqual(changed[3], 590)

    def test_custom_guides_leave_all_math_pixels_unchanged(self):
        for question in ("5 + 2", "8 - 3", "Count 6 dots", "How many sides does a triangle have?"):
            spec = plan_question(question)
            events, cursor = [], 0.0
            for step in spec["steps"]:
                events.append({**step, "start": cursor, "end": cursor+1, "duration": 1})
                cursor += 1+step.get("pause_after", .25)
            for event in events:
                t = event["start"]+.5
                original = render_frame(spec, events, t, cursor)
                for kind in ("robot", "fox", "bear"):
                    personalized = render_frame({**spec, "character": {"kind": kind}}, events, t, cursor)
                    self.assertEqual(original.crop((0, 0, 1040, 720)).tobytes(),
                                     personalized.crop((0, 0, 1040, 720)).tobytes())
                    self.assertEqual(original.crop((0, 625, 1280, 720)).tobytes(),
                                     personalized.crop((0, 625, 1280, 720)).tobytes())


if __name__ == "__main__":
    unittest.main()
