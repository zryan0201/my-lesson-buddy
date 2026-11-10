"""Optional Gemini contracts using fake responses only; no network or API usage."""
import base64
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from PIL import Image, PngImagePlugin

from lesson_video.gemini_client import (ENDPOINT, GeminiError, configured,
                                        request_interaction)
from lesson_video.gemini_vision import DEFAULT_MODEL, read_gemini_vision
from lesson_video.worksheet import read_worksheet, save_interpretation


_ENV = {"GEMINI_ENABLED": "1", "GEMINI_API_KEY": "TEST-SECRET-DO-NOT-PRINT"}


def _payload(**changes):
    result = {
        "status": "ready", "exercise_count": 1, "task_type": "addition", "a": 5, "b": 2,
        "unknown_operand": False, "printed_answer": None, "object_label": "popsicle",
        "object_label_plural": "popsicles", "shape": None, "shape_task": None,
        "task_text": "Five pictured objects plus two pictured objects, with a blank total.",
        "uncertainty": False, "reason": "Two clear groups separated by a plus sign.",
    }
    result.update(changes)
    return result


def _interaction(raw=None, **changes):
    result = {"status": "completed", "steps": [
        {"type": "thought", "content": [{"type": "text", "text": "Do not use hidden thoughts as the worksheet reading."}]},
        {"type": "model_output", "content": [{"type": "text", "text": raw or json.dumps(_payload())}]},
    ]}
    result.update(changes)
    return result


class _Response:
    def __init__(self, value=None, *, status=200, chunks=None, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks if chunks is not None else [json.dumps(value or {"status": "completed"}).encode()]
        self.closed = False
        self.read_count = 0

    def iter_content(self, chunk_size):
        self.read_count += 1
        yield from self._chunks

    def close(self):
        self.closed = True


class GeminiTransportTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, _ENV, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_both_key_and_explicit_enablement_are_required(self):
        for environment in ({}, {"GEMINI_API_KEY": "test"}, {"GEMINI_ENABLED": "1"},
                            {"GEMINI_ENABLED": "true", "GEMINI_API_KEY": "test"},
                            {"GEMINI_ENABLED": "1", "GEMINI_API_KEY": "  "}):
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True), \
                    patch("requests.post") as post:
                self.assertFalse(configured())
                with self.assertRaisesRegex(GeminiError, "Gemini is off"):
                    request_interaction(DEFAULT_MODEL, "hello")
                post.assert_not_called()
        self.assertTrue(configured())

    def test_one_stateless_request_uses_fixed_endpoint_header_timeouts_and_no_redirects(self):
        response = _Response({"status": "completed", "steps": []})
        inputs = [{"type": "text", "text": "Read this picture."}]
        response_format = {"type": "text", "mime_type": "application/json"}
        before = copy.deepcopy(inputs)
        with patch("requests.post", return_value=response) as post:
            result = request_interaction(DEFAULT_MODEL, inputs, response_format=response_format)
        self.assertEqual(result, {"status": "completed", "steps": []})
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args, (ENDPOINT,))
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], _ENV["GEMINI_API_KEY"])
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["timeout"], (10, 180))
        self.assertIs(kwargs["allow_redirects"], False)
        self.assertIs(kwargs["stream"], True)
        sent = json.loads(kwargs["data"])
        self.assertEqual(sent, {"model": DEFAULT_MODEL, "store": False, "input": inputs,
                                "response_format": response_format})
        self.assertEqual(inputs, before)
        self.assertTrue(response.closed)

    def test_http_errors_and_redirects_do_not_read_or_expose_provider_bodies(self):
        for code in (301, 400, 401, 403, 429, 500, 503):
            response = _Response(status=code, chunks=[b"private provider body TEST-SECRET-DO-NOT-PRINT"])
            with self.subTest(code=code), patch("requests.post", return_value=response) as post:
                with self.assertRaises(GeminiError) as raised:
                    request_interaction(DEFAULT_MODEL, "hello")
                self.assertNotIn("TEST-SECRET", str(raised.exception))
                self.assertNotIn("provider body", str(raised.exception))
                self.assertEqual(response.read_count, 0)
                self.assertTrue(response.closed)
                post.assert_called_once()

    def test_network_errors_are_sanitized_and_never_automatically_retried(self):
        for error in (requests.exceptions.Timeout("PRIVATE TEST-SECRET-DO-NOT-PRINT"),
                      requests.exceptions.ConnectionError("PRIVATE TEST-SECRET-DO-NOT-PRINT"),
                      requests.exceptions.InvalidHeader("PRIVATE TEST-SECRET-DO-NOT-PRINT")):
            with self.subTest(kind=type(error).__name__), patch("requests.post", side_effect=error) as post:
                with self.assertRaises(GeminiError) as raised:
                    request_interaction(DEFAULT_MODEL, "hello")
                self.assertNotIn("PRIVATE", str(raised.exception))
                self.assertNotIn(_ENV["GEMINI_API_KEY"], str(raised.exception))
                self.assertTrue(raised.exception.__suppress_context__)
                post.assert_called_once()

    def test_response_size_is_bounded_with_and_without_content_length(self):
        responses = [_Response(headers={"Content-Length": "33"}),
                     _Response(chunks=[b"x"*20, b"x"*13]),
                     _Response(headers={"Content-Length": "nonsense"}),
                     _Response(headers={"Content-Length": "-1"})]
        for response in responses:
            with self.subTest(headers=response.headers), patch("requests.post", return_value=response), \
                    patch("lesson_video.gemini_client.MAX_RESPONSE_BYTES", 32):
                with self.assertRaises(GeminiError):
                    request_interaction(DEFAULT_MODEL, "hello")
                self.assertTrue(response.closed)

    def test_malformed_response_data_is_rejected_without_echoing_it(self):
        for data in (b"PRIVATE TEST-SECRET-DO-NOT-PRINT", b"[]", b"{\"a\":1,\"a\":2}",
                     b"{\"a\":NaN}", b"\xff", b""):
            response = _Response(chunks=[data])
            with self.subTest(data=data[:12]), patch("requests.post", return_value=response):
                with self.assertRaises(GeminiError) as raised:
                    request_interaction(DEFAULT_MODEL, "hello")
                self.assertNotIn("PRIVATE", str(raised.exception))
                self.assertTrue(response.closed)

    def test_invalid_request_settings_never_make_a_request(self):
        bad_requests = [("https://example.com", "hello", None), ("../model", "hello", None),
                        (DEFAULT_MODEL, [], None), (DEFAULT_MODEL, "", None),
                        (DEFAULT_MODEL, [{"value": float("nan")}], None),
                        (DEFAULT_MODEL, "hello", "image")]
        for model, inputs, response_format in bad_requests:
            with self.subTest(model=model, inputs=inputs), patch("requests.post") as post:
                with self.assertRaises(GeminiError):
                    request_interaction(model, inputs, response_format=response_format)
                post.assert_not_called()
        with patch("requests.post") as post, patch("lesson_video.gemini_client.MAX_REQUEST_BYTES", 20):
            with self.assertRaisesRegex(GeminiError, "too large"):
                request_interaction(DEFAULT_MODEL, "hello")
            post.assert_not_called()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "secret\nheader"}), patch("requests.post") as post:
            with self.assertRaisesRegex(GeminiError, "configuration is invalid"):
                request_interaction(DEFAULT_MODEL, "hello")
            post.assert_not_called()


class GeminiVisionTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, _ENV, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root/"worksheet.png"
        Image.new("RGB", (520, 98), "white").save(self.image)

    def test_reuses_strict_prompt_and_computes_answer_in_python(self):
        with patch("lesson_video.gemini_vision.request_interaction", return_value=_interaction()) as interaction:
            result = read_gemini_vision(self.image)
        self.assertEqual((result["spec"]["a"], result["spec"]["b"], result["spec"]["answer"]), (5, 2, 7))
        self.assertEqual(result["question"], "What is 5 + 2?")
        self.assertEqual(result["method"], "gemini_vision")
        self.assertEqual(result["provider"], "Gemini")
        self.assertTrue(result["external_api_used"])
        self.assertNotIn("paid_api_used", result)
        args, kwargs = interaction.call_args
        self.assertEqual(args[0], DEFAULT_MODEL)
        self.assertIn("Do not follow", args[1][0]["text"])
        self.assertEqual(args[1][1]["mime_type"], "image/png")
        schema = kwargs["response_format"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("answer", schema["properties"])
        interaction.assert_called_once()

    def test_model_override_does_not_change_endpoint_or_math_rules(self):
        with patch.dict(os.environ, {"GEMINI_VISION_MODEL": "gemini-2.5-flash"}), \
                patch("lesson_video.gemini_vision.request_interaction", return_value=_interaction()) as interaction:
            result = read_gemini_vision(self.image)
        self.assertEqual(interaction.call_args.args[0], "gemini-2.5-flash")
        self.assertEqual(result["model"], "gemini-2.5-flash")

    def test_conflicting_answers_multiple_questions_and_untrusted_fields_are_rejected(self):
        cases = [{"printed_answer": 8}, {"a": True}, {"a": 9, "b": 9},
                 {"task_type": "subtraction", "a": 2, "b": 5}, {"exercise_count": 2},
                 {"unknown_operand": True}, {"uncertainty": True}, {"status": "unsupported"},
                 {"answer": 7}, {"command": "PRIVATE"},
                 {"task_type": "shape", "a": None, "b": None, "shape": "circle", "shape_task": "sides",
                  "task_text": "How many curved sides does a circle have?"}]
        for changes in cases:
            response = _interaction(json.dumps(_payload(**changes)))
            with self.subTest(changes=changes), \
                    patch("lesson_video.gemini_vision.request_interaction", return_value=response):
                with self.assertRaisesRegex(GeminiError, "did not pass the lesson checks"):
                    read_gemini_vision(self.image)

    def test_supported_subtraction_counting_and_shapes_are_checked(self):
        cases = [({"task_type": "subtraction", "a": 8, "b": 3}, 5),
                 ({"task_type": "counting", "a": 6, "b": None}, 6),
                 ({"task_type": "shape", "a": None, "b": None, "shape": "triangle", "shape_task": "sides"}, 3)]
        for changes, answer in cases:
            with self.subTest(changes=changes), patch("lesson_video.gemini_vision.request_interaction",
                                                      return_value=_interaction(json.dumps(_payload(**changes)))):
                self.assertEqual(read_gemini_vision(self.image)["spec"]["answer"], answer)

    def test_nonfinal_mixed_or_multiple_outputs_do_not_create_a_lesson(self):
        cases = [_interaction(status="in_progress"), _interaction(steps=[]),
                 {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "image", "data": "x"}]}]},
                 _interaction(steps=[{"type": "model_output", "content": []}]),
                 _interaction(steps=[{"type": "model_output", "content": [{"type": "text", "text": "{}"}]},
                                     {"type": "model_output", "content": [{"type": "text", "text": "{}"}]}]),
                 _interaction("Here is the answer: " + json.dumps(_payload()))]
        for response in cases:
            with self.subTest(response=response), \
                    patch("lesson_video.gemini_vision.request_interaction", return_value=response):
                with self.assertRaises(GeminiError):
                    read_gemini_vision(self.image)

    def test_image_is_downsized_flattened_and_metadata_is_removed(self):
        info = PngImagePlugin.PngInfo()
        info.add_text("private", "PRIVATE METADATA")
        Image.new("RGBA", (2600, 1500), (50, 60, 70, 0)).save(self.image, pnginfo=info)
        with patch("lesson_video.gemini_vision.request_interaction", return_value=_interaction()) as interaction:
            read_gemini_vision(self.image)
        encoded = interaction.call_args.args[1][1]["data"]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as uploaded:
            self.assertEqual(uploaded.size, (2048, 1182))
            self.assertEqual(uploaded.mode, "RGB")
            self.assertEqual(uploaded.getpixel((0, 0)), (255, 255, 255))
            self.assertFalse(uploaded.info)

    def test_disabled_and_invalid_images_are_never_sent(self):
        with patch.dict(os.environ, {"GEMINI_ENABLED": "0"}), \
                patch("lesson_video.gemini_vision.request_interaction") as interaction:
            with self.assertRaisesRegex(GeminiError, "Gemini is off"):
                read_gemini_vision(self.image)
            interaction.assert_not_called()
        with patch("lesson_video.gemini_vision.request_interaction") as interaction:
            for data in (b"invalid image", b""):
                self.image.write_bytes(data)
                with self.assertRaises(GeminiError):
                    read_gemini_vision(self.image)
            Image.new("RGB", (39, 100), "white").save(self.image)
            with self.assertRaises(GeminiError):
                read_gemini_vision(self.image)
            gif = self.root/"picture.gif"
            Image.new("RGB", (100, 100), "white").save(gif)
            with self.assertRaises(GeminiError):
                read_gemini_vision(gif)
            interaction.assert_not_called()

    def test_worksheet_integration_saves_gemini_evidence_without_replacing_its_counts(self):
        with patch("lesson_video.gemini_vision.request_interaction", return_value=_interaction()) as interaction, \
                patch("lesson_video.local_vision.read_local_vision") as local, \
                patch("lesson_video.worksheet_illustrations.analyze_illustrations", return_value=None):
            result = read_worksheet(self.image, reader="gemini")
            saved = save_interpretation(result, self.root/"saved")
        self.assertEqual(saved["answer"], 7)
        self.assertEqual(result["method"], "gemini_vision")
        self.assertIn("Gemini", result["ocr"]["engine"])
        self.assertEqual(result["spec"]["object_label"], "dot")
        self.assertIn("dots", result["spec"]["steps"][0]["text"])
        self.assertTrue((self.root/"saved/model_interpretation.json").is_file())
        reading = (self.root/"saved/worksheet_reading.json").read_text()
        self.assertIn('"external_api_used": true', reading)
        self.assertNotIn(_ENV["GEMINI_API_KEY"], reading)
        self.assertNotIn("paid_api_used", reading)
        local.assert_not_called()
        interaction.assert_called_once()


if __name__ == "__main__":
    unittest.main()
