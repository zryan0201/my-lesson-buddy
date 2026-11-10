"""Pixel-level regressions for the objects children are asked to count.

These tests build silent synthetic timelines. They render real frames, with no
speech engine, FFmpeg process, or saved video required.
"""

import unittest

import numpy as np
from PIL import Image, ImageFilter

from lesson_video.planner import plan_question
from lesson_video.visuals import render_frame


_SCENE = (140, 221, 971, 455)
_VALUE = (214, 502, 861, 552)


def _timeline(question):
    spec = plan_question(question)
    events, cursor = [], 0.0
    for step in spec["steps"]:
        event = {**step, "start": cursor, "end": cursor + 1.0, "duration": 1.0}
        events.append(event)
        cursor = event["end"] + float(step.get("pause_after", 0.25))
    return spec, events, cursor


def _frame(lesson, event, fraction=0.5):
    spec, events, duration = lesson
    return render_frame(spec, events, event["start"] + event["duration"] * fraction, duration)


def _components(mask):
    """Return areas of connected colored bodies, ignoring tiny edge artifacts."""
    remaining = mask.copy()
    height, width = remaining.shape
    areas = []
    ys, xs = np.nonzero(remaining)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if not remaining[y, x]:
            continue
        remaining[y, x] = False
        pending, area = [(y, x)], 0
        while pending:
            py, px = pending.pop()
            area += 1
            for ny, nx in ((py - 1, px), (py + 1, px), (py, px - 1), (py, px + 1)):
                if 0 <= ny < height and 0 <= nx < width and remaining[ny, nx]:
                    remaining[ny, nx] = False
                    pending.append((ny, nx))
        if area >= 80:
            areas.append(area)
    return areas


def _yellow_bodies(image):
    pixels = np.asarray(image.crop(_SCENE))
    # Faces split the exact-color region of the smallest dots into two pieces.
    # Join gaps up to six pixels; separate bodies are at least 22 pixels apart.
    # The resulting components measure actual visible bodies without trusting
    # their intended positions, count, or the renderer's layout helper.
    gold = np.all(pixels[:, :, :3] == (255, 201, 40), axis=2)
    joined = Image.fromarray(gold.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(7))
    return _components(np.asarray(joined) > 0)


def _faded_warm_pixels(image):
    pixels = np.asarray(image.crop(_SCENE)).astype(int)
    red, green, blue = (pixels[:, :, channel] for channel in range(3))
    return int(np.count_nonzero((red > 230) & (green > 220) & (green < 245)
                                & (blue > 170) & (blue < 220)))


class RenderingTests(unittest.TestCase):
    def test_addition_preserves_all_objects_before_and_after_combining(self):
        for question, total in (("3 + 2", 5), ("5 + 5", 10), ("0 + 1", 1), ("0 + 0", 0)):
            with self.subTest(question=question):
                lesson = _timeline(question)
                events = lesson[1]
                before = next(e for e in events if e["phase"] == "group_b")
                after = next(e for e in events if e["phase"] == "count")
                self.assertEqual(len(_yellow_bodies(_frame(lesson, before))), total)
                self.assertEqual(len(_yellow_bodies(_frame(lesson, after))), total)

    def test_subtraction_visibly_removes_only_the_given_objects_including_zero(self):
        for question, start, remainder in (("5 - 2", 5, 3), ("3 - 3", 3, 0), ("5 - 0", 5, 5), ("0 - 0", 0, 0)):
            with self.subTest(question=question):
                lesson = _timeline(question)
                events = lesson[1]
                before = next(e for e in events if e["phase"] == "group_a")
                action = next(e for e in events if e["phase"] == "action")
                after = next(e for e in events if e["phase"] == "count")
                before_image, action_image, after_image = (_frame(lesson, event) for event in (before, action, after))
                self.assertEqual(len(_yellow_bodies(before_image)), start)
                self.assertEqual(len(_yellow_bodies(action_image)), remainder)
                self.assertEqual(len(_yellow_bodies(after_image)), remainder)
                if start > remainder:
                    self.assertGreater(_faded_warm_pixels(action_image), _faded_warm_pixels(after_image) + 400)

    def test_subtraction_starting_count_has_a_visible_green_selection_ring(self):
        lesson = _timeline("5 - 2")
        plain = next(e for e in lesson[1] if e["phase"] == "group_a" and "active_index" not in e)
        highlighted = next(e for e in lesson[1] if e["phase"] == "group_a" and e.get("active_index") == 0)

        def green_pixels(event):
            pixels = np.asarray(_frame(lesson, event).crop(_SCENE)).astype(int)
            red, green, blue = (pixels[:, :, channel] for channel in range(3))
            return int(np.count_nonzero((green > red + 30) & (green > blue + 5)))

        self.assertGreater(green_pixels(highlighted), green_pixels(plain) + 100)
        self.assertEqual(len(_yellow_bodies(_frame(lesson, highlighted))), 5)

    def test_dense_comparison_keeps_nineteen_equal_size_bodies_visible_during_every_count(self):
        lesson = _timeline("Which is greater, 10 or 9?")
        counts = [e for e in lesson[1] if "active_index" in e]
        self.assertEqual(len(counts), 19)
        for event in counts:
            with self.subTest(step=event["id"]):
                areas = _yellow_bodies(_frame(lesson, event))
                self.assertEqual(len(areas), 19, "A dot was hidden, covered, or merged with another dot.")
                # Counting groups should have the same-sized dots. This also
                # catches a counting badge obscuring a large part of one body.
                self.assertGreater(min(areas), max(areas) * 0.90)

    def test_value_is_hidden_through_the_question_pause_and_changes_at_answer_onset(self):
        for question in ("3 + 2", "5 - 2", "Count 6 dots", "Which is greater, 3 or 5?",
                         "How many sides does a triangle have?"):
            with self.subTest(question=question):
                lesson = _timeline(question)
                spec, events, duration = lesson
                prompt = next(e for e in events if e["phase"] == "question")
                answer = next(e for e in events if e["phase"] == "answer")
                during_question = _frame(lesson, prompt).crop(_VALUE).tobytes()
                during_pause = render_frame(spec, events, prompt["end"] + 1.5, duration).crop(_VALUE).tobytes()
                just_before = render_frame(spec, events, answer["start"] - 0.0001, duration).crop(_VALUE).tobytes()
                at_answer = render_frame(spec, events, answer["start"], duration).crop(_VALUE).tobytes()
                self.assertEqual(during_question, during_pause)
                self.assertEqual(during_pause, just_before)
                self.assertNotEqual(just_before, at_answer)


if __name__ == "__main__":
    unittest.main()
