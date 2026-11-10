"""Synthetic geometry regression checks, not a real-photo accuracy benchmark."""

import json
import unittest

from PIL import Image, ImageDraw

from lesson_video.worksheet_objects import analyze_diagram
from lesson_video.worksheet import WorksheetUnclear, interpret_evidence


def sheet(size=(500, 180), mode="RGB"):
    return Image.new(mode, size, (0, 0, 0, 0) if mode == "RGBA" else "white")


class WorksheetObjectsTests(unittest.TestCase):
    def test_counters_remain_separate_from_math_signs_and_answer_blanks(self):
        image = sheet((540, 100))
        draw = ImageDraw.Draw(image)
        for x, y in [(40, 65), (62, 31), (87, 65), (198, 48), (247, 48)]:
            draw.ellipse((x-15, y-15, x+15, y+15), fill="#ffc000")
        draw.line((135, 48, 153, 48), fill="black", width=3)
        draw.line((144, 39, 144, 57), fill="black", width=3)
        draw.line((457, 43, 477, 43), fill="black", width=2)
        draw.line((457, 51, 477, 51), fill="black", width=2)
        draw.line((295, 85, 327, 85), fill="#888888", width=2)
        draw.line((397, 85, 429, 85), fill="#888888", width=2)
        result = analyze_diagram(image)
        self.assertEqual([o["shape"] for o in result["objects"]], ["circle"]*5)
        self.assertEqual([g["count"] for g in result["groups"]], [3, 2])
        self.assertEqual([s["kind"] for s in result["symbols"]],
                         ["plus", "minus", "minus", "equals"])
        self.assertTrue(all(s["ambiguous"] for s in result["symbols"] if s["kind"] == "minus"))
        self.assertEqual(result["uncertain_regions"], [])
        json.dumps(result)  # Every evidence field must remain serializable.

    def test_black_filled_and_outlined_circles_keep_glyph_check_evidence(self):
        for outlined in (False, True):
            with self.subTest(outlined=outlined):
                image = sheet()
                draw = ImageDraw.Draw(image)
                for x in (70, 220, 370):
                    for y in (55, 130):
                        if outlined:
                            draw.ellipse((x-20, y-20, x+20, y+20), outline="black", width=3)
                        else:
                            draw.ellipse((x-20, y-20, x+20, y+20), fill="black")
                result = analyze_diagram(image)
                self.assertEqual(len(result["objects"]), 6)
                self.assertTrue(all(o["shape"] == "circle" for o in result["objects"]))
                self.assertTrue(all(o["requires_text_check"] == outlined for o in result["objects"]))

    def test_outline_shapes_are_filled_before_geometry_is_classified(self):
        for shape in ("triangle", "square", "rectangle"):
            with self.subTest(shape=shape):
                image = sheet((250, 180))
                draw = ImageDraw.Draw(image)
                if shape == "triangle":
                    draw.polygon([(125, 25), (65, 150), (185, 150)], outline="black", width=4)
                elif shape == "square":
                    draw.rectangle((65, 25, 190, 150), outline="black", width=4)
                else:
                    draw.rectangle((25, 45, 225, 135), outline="black", width=4)
                result = analyze_diagram(image)
                self.assertEqual([o["shape"] for o in result["objects"]], [shape])

    def test_overlap_and_incomplete_crop_are_not_reported_as_counters(self):
        for cropped in (False, True):
            with self.subTest(cropped=cropped):
                image = sheet((300, 160))
                draw = ImageDraw.Draw(image)
                if cropped:
                    draw.ellipse((-20, 40, 50, 110), fill="red")
                else:
                    draw.ellipse((50, 40, 120, 110), fill="blue")
                    draw.ellipse((102, 40, 172, 110), fill="blue")
                result = analyze_diagram(image)
                self.assertEqual(result["objects"], [])
                self.assertTrue(result["uncertain_regions"])
                self.assertEqual(result["confidence"], 0)

    def test_dark_unknown_marks_are_preserved_for_ocr_reconciliation(self):
        image = sheet((360, 160))
        draw = ImageDraw.Draw(image)
        # A connected, open 5-like glyph is not a circle or polygon object.
        draw.line([(85, 35), (35, 35), (35, 75), (80, 75), (85, 120), (35, 120)], fill="black", width=6)
        draw.line((150, 75, 175, 75), fill="black", width=3)
        draw.line([(230, 40), (275, 40), (275, 65), (230, 115), (280, 115)], fill="black", width=6)
        result = analyze_diagram(image)
        self.assertEqual(result["objects"], [])
        self.assertGreaterEqual(len(result["text_candidates"]), 2)

    def test_transparent_background_is_composited_and_evidence_uses_source_pixels(self):
        image = sheet((2000, 800), mode="RGBA")
        ImageDraw.Draw(image).ellipse((500, 200, 700, 400), fill=(255, 0, 0, 255))
        result = analyze_diagram(image)
        self.assertEqual(len(result["objects"]), 1)
        obj = result["objects"][0]
        self.assertEqual(obj["shape"], "circle")
        for key, expected in {"x": 500, "y": 200, "width": 201, "height": 201}.items():
            self.assertAlmostEqual(obj["bbox"][key], expected, delta=2)
        self.assertEqual((result["image_width"], result["image_height"]), (2000, 800))

    def test_dark_background_is_declined_instead_of_becoming_a_shape(self):
        result = analyze_diagram(Image.new("RGB", (300, 200), "#53646e"))
        self.assertEqual(result["objects"], [])
        self.assertEqual(result["confidence"], 0)
        self.assertTrue(result["warnings"])

    def test_count_limit_retains_evidence_but_does_not_claim_confidence(self):
        image = sheet((550, 180))
        draw = ImageDraw.Draw(image)
        for y in (50, 125):
            for x in (50, 130, 210, 290, 370, 450):
                draw.ellipse((x-15, y-15, x+15, y+15), fill="red")
        result = analyze_diagram(image)
        self.assertEqual(len(result["objects"]), 12)
        self.assertEqual(result["confidence"], 0)
        self.assertTrue(any("More than 10" in warning for warning in result["warnings"]))


class WorksheetInterpretationSafetyTests(unittest.TestCase):
    """Synthetic OCR evidence reproduces ambiguity, rather than OCR quality."""

    size = (500, 180)

    def printed(self, text):
        return {"text": text, "lines": [{"text": text, "confidence": 1.0,
                                         "bbox": [.05, .01, .9, .12]}]}

    def dots(self, positions=(30, 70, 240, 280, 320)):
        return [{"shape": "circle", "confidence": .99, "requires_text_check": False,
                 "bbox": {"x": x, "y": 100, "width": 25, "height": 25}}
                for x in positions]

    def test_missing_operand_does_not_become_total_unknown_when_dot_groups_exist(self):
        evidence = {"objects": self.dots(), "symbols": [{"kind": "plus",
                    "bbox": {"x": 150, "y": 102, "width": 20, "height": 20}}]}
        for text in ("? + 3 = 5", "___ + 3 = 5", "2 + ? = 5"):
            with self.subTest(text=text):
                with self.assertRaises(WorksheetUnclear):
                    interpret_evidence(self.printed(text), evidence, self.size)

    def test_named_shape_does_not_hide_an_unrecognized_drawing(self):
        evidence = {"objects": [], "symbols": [], "text_candidates": [{
            "bbox": {"x": 150, "y": 60, "width": 180, "height": 90},
            "reason": "unrecognized dark drawing"}]}
        with self.assertRaises(WorksheetUnclear):
            interpret_evidence(self.printed("How many sides does a square have?"), evidence, self.size)
        # A text-only supported question still establishes its own target.
        result = interpret_evidence(self.printed("How many sides does a square have?"),
                                    {"objects": [], "symbols": []}, self.size)
        self.assertEqual(result["spec"]["answer"], 4)

    def test_color_and_position_targets_are_not_collapsed_to_all_dots(self):
        evidence = {"objects": self.dots(), "symbols": []}
        for text in ("Count the red dots.", "How many dots are on the left?",
                     "Count only the big dots.", "Do not count the blue dots."):
            with self.subTest(text=text):
                with self.assertRaises(WorksheetUnclear):
                    interpret_evidence(self.printed(text), evidence, self.size)

    def test_curved_side_question_is_not_rewritten_as_straight_side_count(self):
        with self.assertRaises(WorksheetUnclear):
            interpret_evidence(self.printed("How many curved sides does a circle have?"),
                               {"objects": self.dots((120,)), "symbols": []}, self.size)

    def test_white_margins_do_not_hide_unknown_marks_beside_clear_counters(self):
        evidence = {"objects": self.dots(), "symbols": [], "text_candidates": [{
            "bbox": {"x": 300, "y": 400, "width": 50, "height": 25},
            "reason": "two connected black counters"}]}
        with self.assertRaises(WorksheetUnclear):
            interpret_evidence(self.printed("Count the dots."), evidence, (1000, 1000))

    def test_second_instruction_line_cannot_change_the_counting_target_silently(self):
        text = "Count the dots.\nOnly the red ones."
        ocr = self.printed(text)
        ocr["lines"] = [{"text": line, "confidence": 1., "bbox": [.05, .01+i*.12, .9, .1]}
                        for i, line in enumerate(text.splitlines())]
        with self.assertRaises(WorksheetUnclear):
            interpret_evidence(ocr, {"objects": self.dots(), "symbols": []}, self.size)


if __name__ == "__main__":
    unittest.main()
