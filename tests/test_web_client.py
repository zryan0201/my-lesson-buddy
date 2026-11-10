"""The web client keeps job capabilities private and retries requests explicitly."""
import json
import unittest
from unittest.mock import Mock

import requests

from lesson_video.web_client import LessonApiClient, LessonApiError


class WebClientTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.response = self.session.request.return_value
        self.response.status_code = 200
        self.response.json.return_value = {"job_id": "safe-job", "status": "reading"}
        self.client = LessonApiClient(session=self.session)
        self.token = "session_capability_0123456789"

    def test_upload_sends_picture_and_character_snapshot_only_on_explicit_call(self):
        self.session.request.assert_not_called()
        config = {"kind": "fox", "color": "#123456", "accessory": "cap"}
        self.client.create_job(b"image bytes", "../worksheet.png", "image/png", config, "nonce_1234567890123456")
        args, kwargs = self.session.request.call_args
        self.assertEqual(args, ("POST", "http://127.0.0.1:5001/api/jobs"))
        self.assertEqual(kwargs["files"], {"worksheet": ("worksheet.png", b"image bytes", "image/png")})
        self.assertEqual(json.loads(kwargs["data"]["character"]), config)
        self.assertEqual(kwargs["data"]["client_request_id"], "nonce_1234567890123456")
        self.assertEqual(kwargs["timeout"], (3.05, 20))
        self.assertFalse(kwargs["allow_redirects"])

    def test_all_existing_job_requests_use_authorization_header_and_no_url_secret(self):
        self.response.content = b"mp4"
        self.client.get_job("safe-job", self.token)
        self.client.generate("safe-job", self.token)
        self.assertEqual(self.client.get_asset("safe-job", self.token, "video"), b"mp4")
        for args, kwargs in self.session.request.call_args_list:
            self.assertNotIn(self.token, args[1])
            self.assertEqual(kwargs["headers"], {"Authorization": f"Bearer {self.token}"})
            self.assertFalse(kwargs["allow_redirects"])
        generate = self.session.request.call_args_list[1]
        self.assertEqual(generate.kwargs["json"], {"confirmed": True})
        self.assertNotIn("files", generate.kwargs)
        self.assertNotIn("character", generate.kwargs["json"])

    def test_same_idempotency_nonce_can_be_reused_after_timeout(self):
        self.session.request.side_effect = [requests.Timeout("sensitive URL"), self.response]
        params = (b"picture", "worksheet.png", "image/png", {"kind": "robot"}, "same_nonce_0123456789")
        with self.assertRaises(LessonApiError) as caught:
            self.client.create_job(*params)
        self.assertEqual(caught.exception.code, "timeout")
        self.assertNotIn("sensitive", str(caught.exception))
        self.client.create_job(*params)
        self.assertEqual(self.session.request.call_count, 2)
        self.assertEqual(self.session.request.call_args_list[0], self.session.request.call_args_list[1])

    def test_connectivity_errors_are_friendly_and_do_not_echo_request_secrets(self):
        for error, code in ((requests.ConnectionError("secret"), "offline"),
                            (requests.Timeout("secret"), "timeout"),
                            (requests.RequestException("secret"), "connection")):
            self.session.request.side_effect = error
            with self.subTest(code=code), self.assertRaises(LessonApiError) as caught:
                self.client.get_job("safe-job", self.token)
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn("secret", str(caught.exception))

    def test_http_and_invalid_json_responses_are_not_rendered_as_html_or_tracebacks(self):
        for status in (302, 400, 401, 403, 404, 409, 413, 422, 500, 503):
            self.response.status_code = status
            self.response.text = "private server path and secret token"
            with self.subTest(status=status), self.assertRaises(LessonApiError) as caught:
                self.client.get_job("safe-job", self.token)
            self.assertNotIn("secret", str(caught.exception))
        self.response.status_code = 200
        self.response.json.side_effect = ValueError("private response")
        with self.assertRaises(LessonApiError) as caught:
            self.client.get_job("safe-job", self.token)
        self.assertEqual(caught.exception.code, "invalid_response")

    def test_job_path_and_asset_inputs_cannot_escape_job_endpoints(self):
        for job in ("../../secret", "x?token=secret", "x/video", ""):
            with self.subTest(job=job), self.assertRaises(LessonApiError):
                self.client.get_job(job, self.token)
        with self.assertRaises(ValueError):
            self.client.get_asset("safe-job", self.token, "../secret")
        with self.assertRaises(LessonApiError):
            self.client.get_job("safe-job", "bad\nHeader")
        self.session.request.assert_not_called()

    def test_credentials_and_query_tokens_are_rejected_in_server_configuration(self):
        for url in ("file:///tmp/api", "http://user:password@localhost", "https://example.com?token=secret"):
            with self.subTest(url=url), self.assertRaises(LessonApiError):
                LessonApiClient(url)


if __name__ == "__main__":
    unittest.main()
