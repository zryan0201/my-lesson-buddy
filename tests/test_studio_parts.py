"""Validate the modular art contract and visible interchangeable parts."""
import json
import unittest

import numpy as np
from PIL import ImageChops

from character_studio.parts import catalog, render_design, validate_design


class StudioPartsTests(unittest.TestCase):
    def test_catalog_is_json_friendly_and_independent(self):
        first = catalog()
        json.dumps(first)
        self.assertEqual(first["version"], 1)
        self.assertEqual(first["name_max_length"], 32)
        self.assertEqual(len(first["presets"]), 4)
        for item in first["presets"]:
            self.assertEqual(validate_design(item["design"]), item["design"])
        first["defaults"]["name"] = "Changed"
        first["presets"][0]["design"]["name"] = "Changed"
        first["options"]["body_type"].clear()
        second = catalog()
        self.assertEqual(second["defaults"]["name"], "Spark")
        self.assertEqual(second["presets"][0]["design"]["name"], "Nova")
        self.assertEqual(len(second["options"]["body_type"]), 3)

    def test_normalization_supports_names_from_different_writing_systems(self):
        original = {"name": "  小星星  7  ", "primary_color": "#abcdef"}
        design = validate_design(original)
        self.assertEqual(design["name"], "小星星 7")
        self.assertEqual(design["primary_color"], "#ABCDEF")
        self.assertEqual(design["body_type"], "kid")
        self.assertEqual(original["primary_color"], "#abcdef")
        self.assertEqual(validate_design({"name": "E\u0301toile d’Or"})["name"], "Étoile d’Or")
        self.assertEqual(validate_design({"name": "نجمة"})["name"], "نجمة")
        self.assertEqual(validate_design({"name": "A"*32})["name"], "A"*32)

    def test_untrusted_values_and_paths_are_rejected(self):
        invalid = [None, [], "robot", True, {True: "kid"}, {"image": "/tmp/picture.png"},
                   {"version": 2}, {"version": True}, {"version": 1.0},
                   {"body_type": "dragon"}, {"eyes": []}, {"back": True},
                   {"name": "<script>"}, {"name": "../Spark"}, {"name": "a/b"},
                   {"name": "a\\b"}, {"name": "a\n"}, {"name": "\u202eKid"},
                   {"name": "Kid\u200b"}, {"name": "✨"}, {"name": "---"},
                   {"name": ""}, {"name": " "}, {"name": "A"*33}, {"name": False},
                   {"primary_color": "red"}, {"accent_color": "#1234"},
                   {"skin_color": "#000000FF"}, {"secondary_color": [1, 2, 3]}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_design(value)

    def test_complete_design_has_transparent_edges_and_full_body(self):
        sprite = render_design({})
        self.assertEqual(sprite.mode, "RGBA")
        self.assertEqual(sprite.size, (600, 800))
        box = sprite.getbbox()
        self.assertGreater(box[0], 0)
        self.assertGreater(box[1], 0)
        self.assertLess(box[2], 600)
        self.assertLess(box[3], 800)
        self.assertLess(box[1], 160)
        self.assertGreater(box[3], 730)
        alpha = np.asarray(sprite)[:, :, 3]
        self.assertGreater(np.count_nonzero(alpha == 255), 100000)
        self.assertTrue(np.all(alpha[0, :] == 0))
        self.assertTrue(np.all(alpha[-1, :] == 0))
        self.assertTrue(np.all(alpha[:, 0] == 0))
        self.assertTrue(np.all(alpha[:, -1] == 0))

    def test_each_part_option_changes_visible_artwork(self):
        choices = catalog()["options"]
        base_config = {"back": "none", "chest": "none", "eyes": "round"}
        base = np.asarray(render_design(base_config, 300, 400))
        defaults = validate_design(base_config)
        for field, options in choices.items():
            for option in options:
                value = option["value"]
                if value == defaults[field]:
                    continue
                changed = np.asarray(render_design({**base_config, field: value}, 300, 400))
                count = np.count_nonzero(np.any(base != changed, axis=2))
                with self.subTest(field=field, value=value):
                    self.assertGreater(count, 100)

    def test_all_four_colors_affect_the_character(self):
        config = {"body_type": "kid", "headwear": "none", "eyes": "round"}
        original = render_design(config, 300, 400)
        for field in ("primary_color", "secondary_color", "accent_color", "skin_color"):
            changed = render_design({**config, field: "#24A5B7"}, 300, 400)
            difference = ImageChops.difference(original, changed).convert("RGB")
            with self.subTest(field=field):
                self.assertIsNotNone(difference.getbbox())
                self.assertGreater(np.count_nonzero(np.any(np.asarray(difference) != 0, axis=2)), 300)

    def test_body_types_are_distinct_with_every_headwear_and_back_piece(self):
        for headwear in ("none", "web_mask", "helmet", "ears", "antenna"):
            for back in ("none", "cape", "wings"):
                versions = []
                for body_type in ("kid", "robot", "creature"):
                    sprite = render_design({"body_type": body_type, "headwear": headwear,
                                            "back": back, "gloves": "gauntlets",
                                            "boots": "armored"}, 240, 320)
                    box = sprite.getbbox()
                    with self.subTest(headwear=headwear, back=back, body_type=body_type):
                        self.assertGreater(box[0], 0)
                        self.assertGreater(box[1], 0)
                        self.assertLess(box[2], 240)
                        self.assertLess(box[3], 320)
                    versions.append(sprite.tobytes())
                self.assertEqual(len(set(versions)), 3)

    def test_sizing_is_bounded_and_character_is_not_stretched(self):
        for width, height in ((600, 800), (300, 400), (800, 400), (180, 700), (64, 64)):
            sprite = render_design({"back": "wings", "headwear": "antenna"}, width, height)
            self.assertEqual(sprite.size, (width, height))
            box = sprite.getbbox()
            self.assertGreater(box[0], 0)
            self.assertGreater(box[1], 0)
            self.assertLess(box[2], width)
            self.assertLess(box[3], height)
        for width, height in ((True, 800), (600, 1.2), (0, 800), (800, 2049), (-5, 100)):
            with self.subTest(width=width, height=height), self.assertRaises(ValueError):
                render_design({}, width, height)

    def test_rendering_is_repeatable_and_does_not_mutate_the_design(self):
        design = {"name": "Sunny", "headwear": "ears", "back": "wings"}
        original = dict(design)
        first = render_design(design, 240, 320)
        second = render_design(design, 240, 320)
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(design, original)


if __name__ == "__main__":
    unittest.main()
