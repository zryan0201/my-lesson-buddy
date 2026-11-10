"""Small HTTP client for the local lesson API; it never loads a vision model.

Job access capabilities stay in request headers, not URLs or disk caches.
The server address is administrator configuration, not a user input field.
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlsplit

import requests


class LessonApiError(RuntimeError):
    """A message safe to show in the lesson interface."""

    def __init__(self, message: str, *, code: str = "request_failed"):
        super().__init__(message)
        self.code = code


class LessonApiClient:
    def __init__(self, base_url: str | None = None, *, session=None,
                 timeout: tuple[float, float] = (3.05, 20)):
        self.base_url = (base_url or os.environ.get("LESSON_API_URL", "http://127.0.0.1:5001")).rstrip("/")
        parsed = urlsplit(self.base_url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise LessonApiError("The lesson service address needs to be configured by an adult.", code="configuration")
        self.session = session or requests.Session()
        self.timeout = timeout

    @staticmethod
    def _job_path(job_id: str, suffix: str = "") -> str:
        if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job_id):
            raise LessonApiError("This lesson could not be found. Please start a new lesson.", code="invalid_job")
        return f"/api/jobs/{job_id}{suffix}"

    @staticmethod
    def _authorization(access_token: str) -> dict:
        if (not isinstance(access_token, str) or not access_token
                or not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", access_token)):
            raise LessonApiError("This lesson session has expired. Please start a new lesson.", code="unauthorized")
        return {"Authorization": f"Bearer {access_token}"}

    def _request(self, method: str, path: str, *, binary: bool = False, **kwargs):
        try:
            response = self.session.request(method, self.base_url + path,
                                            timeout=self.timeout, allow_redirects=False, **kwargs)
        except requests.Timeout:
            raise LessonApiError("The lesson service is taking longer to respond. Please try again.", code="timeout") from None
        except requests.ConnectionError:
            raise LessonApiError("The lesson service is not running yet. Ask an adult to start it, then try again.", code="offline") from None
        except requests.RequestException:
            raise LessonApiError("We could not reach the lesson service. Please try again.", code="connection") from None
        if response.status_code in (401, 403, 404):
            raise LessonApiError("This lesson is no longer available in this session. Please start a new lesson.", code="unavailable")
        if response.status_code == 413:
            raise LessonApiError("This picture is too large. Please use a smaller picture.", code="too_large")
        if not 200 <= response.status_code < 300:
            # Never surface HTTP response bodies: they can contain infrastructure
            # details, tracebacks, an HTML proxy page, or paths on the server.
            if response.status_code in (400, 409, 415, 422):
                message = "We could not use this request. Please check your picture and start a new lesson."
            elif response.status_code == 503:
                message = "The lesson maker is busy. Please try again in a moment."
            else:
                message = "Something interrupted the lesson service. Please try again."
            raise LessonApiError(message, code=f"http_{response.status_code}")
        if binary:
            return response.content
        try:
            value = response.json()
        except (ValueError, requests.exceptions.JSONDecodeError):
            raise LessonApiError("The lesson service sent an unexpected response. Please try again.", code="invalid_response") from None
        if not isinstance(value, dict):
            raise LessonApiError("The lesson service sent an unexpected response. Please try again.", code="invalid_response")
        return value

    def create_job(self, image: bytes, filename: str, content_type: str,
                   character: dict, client_request_id: str) -> dict:
        """Submit one explicit read request; the nonce makes retrying safe."""
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1] or "worksheet.png"
        return self._request("POST", "/api/jobs", files={"worksheet": (filename, image, content_type)},
                             data={"character": json.dumps(character, sort_keys=True),
                                   "client_request_id": client_request_id})

    def get_job(self, job_id: str, access_token: str) -> dict:
        return self._request("GET", self._job_path(job_id), headers=self._authorization(access_token))

    def generate(self, job_id: str, access_token: str) -> dict:
        """Generate the already-reviewed snapshot, without rereading its photo."""
        return self._request("POST", self._job_path(job_id, "/generate"),
                             headers=self._authorization(access_token), json={"confirmed": True})

    def get_asset(self, job_id: str, access_token: str, asset: str) -> bytes:
        if asset not in {"video", "poster", "input"}:
            raise ValueError("Unsupported lesson asset.")
        return self._request("GET", self._job_path(job_id, "/" + asset), binary=True,
                             headers=self._authorization(access_token))
