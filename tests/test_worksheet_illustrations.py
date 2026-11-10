"""Repeated-artwork checks are synthetic regressions, not image accuracy rates."""
import json
from pathlib import Path
import unittest

from PIL import Image, ImageDraw

from lesson_video.worksheet_illustrations import analyze_illustrations


def icon(kind="icepop", size=(34, 48)):
    result = Image.new("RGB", (68, 96), "white")
    draw = ImageDraw.Draw(result)
    if kind == "icepop":
        draw.rounded_rectangle((5, 4, 62, 91), radius=17, fill="#ef8900")
        draw.rounded_rectangle((12, 4, 27, 58), radius=6, fill="#ffdd34")
        draw.rounded_rectangle((36, 4, 53, 70), radius=6, fill="#ffcc22")
        draw.ellipse((17, 68, 29, 80), fill="#ffe162")
    elif kind == "apple":
        draw.ellipse((7, 24, 41, 87), fill="#d93029")
        draw.ellipse((27, 24, 61, 87), fill="#d93029")
        draw.rectangle((31, 13, 37, 35), fill="#78411c")
        draw.ellipse((35, 8, 58, 24), fill="#4a8b26")
        draw.ellipse((17, 34, 24, 53), fill="#f26960")
    else:
        raise ValueError(kind)
    # Trim the white border so size changes correspond to actual objects.
    return result.resize(size, Image.Resampling.NEAREST)


def arithmetic(left=3, right=2, *, kind="icepop", operation="+", answer=True,
               size_variation=False):
    canvas = Image.new("RGB", (620, 160), "white")
    draw = ImageDraw.Draw(canvas)
    positions = []
    x = 20
    for index in range(left):
        size = (35, 50) if size_variation and index % 2 else (34, 48)
        canvas.paste(icon(kind, size), (x, 50))
        positions.append((x, 50))
        x += 43
    sign_x = x+6
    draw.line((sign_x, 73, sign_x+18, 73), fill="black", width=3)
    if operation == "+":
        draw.line((sign_x+9, 64, sign_x+9, 82), fill="black", width=3)
    x = sign_x+36
    for _ in range(right):
        canvas.paste(icon(kind), (x, 50))
        positions.append((x, 50))
        x += 43
    eq_x = x+3
    draw.line((eq_x, 69, eq_x+18, 69), fill="black", width=3)
    draw.line((eq_x, 77, eq_x+18, 77), fill="black", width=3)
    if answer:
        draw.rounded_rectangle((eq_x+35, 49, eq_x+78, 96), radius=6,
                               outline="black", width=2)
    return canvas, positions, (sign_x, eq_x)


class RepeatedIllustrationTests(unittest.TestCase):
    def test_counts_repeated_multicolor_art_on_both_sides_of_a_plus(self):
        image, _, _ = arithmetic()
        result = analyze_illustrations(image)
        self.assertEqual((result["left_count"], result["right_count"]), (3, 2))
        self.assertEqual(result["question"], "What is 3 + 2?")
        self.assertEqual(len(result["objects"]), 5)
        self.assertEqual(len(result["answer_regions"]), 1)
        self.assertTrue(result["repeated_illustrations_verified"])
        self.assertTrue(all(o["shape"] == "illustration" for o in result["objects"]))
        self.assertEqual(result["uncertain_regions"], [])
        json.dumps(result)

    def test_different_connected_artwork_is_counted_without_a_semantic_label(self):
        image, _, _ = arithmetic(2, 1, kind="apple")
        result = analyze_illustrations(image)
        self.assertEqual(result["question"], "What is 2 + 1?")
        self.assertNotIn("apple", json.dumps(result))

    def test_small_size_variation_and_translation_preserve_source_boxes(self):
        image, _, _ = arithmetic(3, 2, size_variation=True)
        canvas = Image.new("RGB", (700, 200), "white")
        canvas.paste(image, (30, 20))
        original = analyze_illustrations(image)
        result = analyze_illustrations(canvas)
        self.assertEqual(result["question"], original["question"])
        for before, after in zip(original["objects"], result["objects"]):
            self.assertEqual(after["bbox"]["x"], before["bbox"]["x"]+30)
            self.assertEqual(after["bbox"]["y"], before["bbox"]["y"]+20)

    def test_minus_is_validated_as_an_operation_between_two_matching_groups(self):
        image, _, _ = arithmetic(4, 2, operation="-")
        result = analyze_illustrations(image)
        self.assertEqual(result["question"], "What is 4 - 2?")
        self.assertEqual(result["operation"], "subtraction")

    def test_partial_crop_edge_neighbors_are_retained_as_explicit_ignored_evidence(self):
        image, _, _ = arithmetic()
        draw = ImageDraw.Draw(image)
        draw.ellipse((250, -25, 285, 3), fill="green")
        draw.line((300, 159, 328, 159), fill="#df8700", width=2)
        result = analyze_illustrations(image)
        self.assertEqual(result["question"], "What is 3 + 2?")
        self.assertEqual(len(result["ignored_regions"]), 2)

    def test_user_uploaded_rounded_icons_and_thick_equals_sign(self):
        path = Path(__file__).resolve().parents[1]/"examples/worksheets/user_popsicle_addition.png"
        if not path.exists():
            self.skipTest("User photograph is not present in this source distribution.")
        with Image.open(path) as image:
            result = analyze_illustrations(image)
        self.assertEqual(result["question"], "What is 5 + 2?")
        self.assertEqual(len(result["objects"]), 7)
        self.assertEqual(len(result["ignored_regions"]), 4)
        self.assertEqual(len(result["answer_regions"]), 1)

    def test_user_uploaded_picture_counts_are_stable_after_resizing(self):
        path = Path(__file__).resolve().parents[1]/"examples/worksheets/user_popsicle_addition.png"
        if not path.exists():
            self.skipTest("User photograph is not present in this source distribution.")
        with Image.open(path) as original:
            for scale in (1.5, 2.):
                with self.subTest(scale=scale):
                    image = original.resize((round(original.width*scale),
                                             round(original.height*scale)),
                                            Image.Resampling.LANCZOS)
                    result = analyze_illustrations(image)
                    self.assertEqual((result["left_count"], result["right_count"]), (5, 2))
                    self.assertEqual(len(result["objects"]), 7)

    def test_mixed_artwork_is_declined_instead_of_assigned_the_same_name(self):
        image, positions, _ = arithmetic()
        image.paste(icon("apple"), positions[-1])
        with self.assertRaisesRegex(ValueError, "matching artwork"):
            analyze_illustrations(image)

    def test_missing_group_and_missing_equals_are_declined(self):
        for left, right in ((0, 2), (3, 0)):
            with self.subTest(groups=(left, right)):
                image, _, _ = arithmetic(left, right)
                with self.assertRaises(ValueError):
                    analyze_illustrations(image)
        image, _, (_, eq_x) = arithmetic()
        ImageDraw.Draw(image).rectangle((eq_x-1, 65, eq_x+20, 80), fill="white")
        with self.assertRaisesRegex(ValueError, "equals"):
            analyze_illustrations(image)

    def test_detached_illustration_parts_are_not_silently_omitted(self):
        image, positions, _ = arithmetic()
        draw = ImageDraw.Draw(image)
        for x, _ in positions:
            draw.rectangle((x+13, 104, x+19, 120), fill="#8b521b")
        with self.assertRaisesRegex(ValueError, "disconnected"):
            analyze_illustrations(image)

    def test_bare_math_ocr_and_giant_word_boxes_cannot_hide_dark_parts(self):
        image, positions, _ = arithmetic()
        draw = ImageDraw.Draw(image)
        for x, _ in positions:
            draw.rectangle((x+13, 104, x+19, 120), fill="black")
        for text in ("+", "=", "Count the objects"):
            with self.subTest(text=text):
                oversized = {"lines": [{"text": text, "confidence": .99,
                                         "bbox": [0., 0., 1., 1.]}]}
                with self.assertRaisesRegex(ValueError, "disconnected"):
                    analyze_illustrations(image, oversized)
        # A tight '+' OCR box over a detached part still is not printed text.
        tight_math = {"lines": [{"text": "+", "confidence": .99,
                                  "bbox": [(x+13)/image.width, 104/image.height,
                                           7/image.width, 17/image.height]}
                                 for x, _ in positions]}
        with self.assertRaisesRegex(ValueError, "disconnected"):
            analyze_illustrations(image, tight_math)

    def test_touching_artwork_is_not_split_or_counted_as_one(self):
        image, positions, _ = arithmetic()
        draw = ImageDraw.Draw(image)
        first, second = positions[:2]
        draw.rectangle((first[0]+29, 68, second[0]+7, 75), fill="#ef8900")
        with self.assertRaisesRegex(ValueError, "size|touching"):
            analyze_illustrations(image)

    def test_uniform_touching_pairs_are_declined_despite_matching_repetition(self):
        image, positions, _ = arithmetic()
        draw = ImageDraw.Draw(image)
        # Every repeated blob is actually two joined miniatures. Similar size
        # and appearance alone cannot establish the intended count.
        for x, y in positions:
            draw.rectangle((x, y, x+33, y+47), fill="white")
            draw.ellipse((x+2, y+8, x+17, y+39), fill="#eb9600")
            draw.ellipse((x+19, y+8, x+34, y+39), fill="#eb9600")
            draw.line((x+15, y+25, x+21, y+25), fill="#eb9600", width=3)
        with self.assertRaisesRegex(ValueError, "touching"):
            analyze_illustrations(image)

    def test_full_neighboring_row_and_other_substantial_marks_are_declined(self):
        for placement in ((350, 0), (530, 50)):
            with self.subTest(placement=placement):
                image, _, _ = arithmetic()
                image.paste(icon(), placement)
                with self.assertRaises(ValueError):
                    analyze_illustrations(image)

    def test_ocr_cannot_hide_an_unscoped_extra_colored_object(self):
        image, _, _ = arithmetic()
        image.paste(icon(), (350, 0))
        misleading = {"lines": [{"text": "O", "confidence": 1.,
                         "bbox": [350/620, 0., 34/620, 48/160]}]}
        with self.assertRaises(ValueError):
            analyze_illustrations(image, misleading)

    def test_two_complete_arithmetic_rows_are_declined(self):
        row, _, _ = arithmetic()
        image = Image.new("RGB", (620, 320), "white")
        image.paste(row, (0, 0))
        image.paste(row, (0, 160))
        with self.assertRaisesRegex(ValueError, "More than one"):
            analyze_illustrations(image)

    def test_filled_or_marked_answer_field_is_not_mistaken_for_an_icon(self):
        image, _, (_, eq_x) = arithmetic()
        ImageDraw.Draw(image).ellipse((eq_x+45, 60, eq_x+65, 85), fill="blue")
        with self.assertRaises(ValueError):
            analyze_illustrations(image)

    def test_over_limit_and_negative_result_are_declined(self):
        for left, right, operation in ((5, 6, "+"), (1, 3, "-")):
            with self.subTest(problem=(left, right, operation)):
                image, _, _ = arithmetic(left, right, operation=operation)
                with self.assertRaisesRegex(ValueError, "0–10"):
                    analyze_illustrations(image)

    def test_white_or_dark_images_do_not_claim_illustration_evidence(self):
        for color in ("white", "#304030"):
            self.assertIsNone(analyze_illustrations(Image.new("RGB", (500, 200), color)))


if __name__ == "__main__":
    unittest.main()
