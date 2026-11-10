"""Optional, explicitly enabled transport to Google's Gemini Interactions API.

No request is made simply because a key exists. The application must also set
GEMINI_ENABLED=1. Credentials and provider error bodies never become user-facing
errors, and a request is never retried automatically (usage may be billable).
"""
from __future__ import annotations

import json
import os
import re
import time


ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
MAX_REQUEST_BYTES = 20 * 1024 * 1024
_TIMEOUT = (10, 180)
_MAX_DOWNLOAD_SECONDS = 240


class GeminiError(ValueError):
    """A sanitized setup, transport, or response error from optional Gemini."""


def configured() -> bool:
    """Whether an operator explicitly enabled Gemini and provided a key."""
    return os.environ.get("GEMINI_ENABLED") == "1" and bool(os.environ.get("GEMINI_API_KEY", "").strip())


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field.")
        result[key] = value
    return result


def _no_constant(_):
    raise ValueError("Nonstandard JSON number.")


def request_interaction(model, inputs, *, response_format=None) -> dict:
    """Make exactly one bounded, stateless request to a fixed Google endpoint.

    ``inputs`` is Gemini's text or content-list input. Optional response_format
    is passed as structured JSON so text/image callers can share this transport.
    No SDK, API-key file, remote image URL, or model download is required here.
    """
    if not configured():
        raise GeminiError("Gemini is off. Configure GEMINI_API_KEY and explicitly set GEMINI_ENABLED=1 to use it.")
    key = os.environ["GEMINI_API_KEY"].strip()
    if len(key) > 512 or not key.isascii() or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in key):
        raise GeminiError("The Gemini API key configuration is invalid. Update it securely outside the app.")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model):
        raise GeminiError("Choose a valid Gemini model identifier.")
    if not ((isinstance(inputs, str) and inputs.strip()) or
            (isinstance(inputs, list) and inputs and all(isinstance(part, dict) for part in inputs))):
        raise GeminiError("Gemini input must be text or a nonempty list of content objects.")
    if response_format is not None and not isinstance(response_format, (dict, list)):
        raise GeminiError("Gemini response settings must be structured JSON.")
    body = {"model": model, "store": False, "input": inputs}
    if response_format is not None:
        body["response_format"] = response_format
    try:
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError):
        raise GeminiError("Gemini input must contain valid JSON data.") from None
    if len(encoded) > MAX_REQUEST_BYTES:
        raise GeminiError("This Gemini request is too large. Use a smaller image.")
    try:
        import requests
    except ImportError:
        raise GeminiError("Install the project's web requirements to enable optional Gemini requests.") from None
    response = None
    try:
        # requests.post uses zero automatic retries. Disallow redirects so the
        # credential cannot be forwarded to a destination chosen by a response.
        response = requests.post(
            ENDPOINT, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            data=encoded, timeout=_TIMEOUT, allow_redirects=False, stream=True,
        )
        code = response.status_code
        if code != 200:
            if code in (401, 403):
                message = "Gemini access was denied. Check the key and model access in your Google account."
            elif code == 429:
                message = "Gemini's usage or rate limit was reached. Check your Google account before trying again."
            elif 300 <= code < 400:
                message = "Gemini returned a redirect, which this app does not follow."
            elif code >= 500:
                message = "Gemini is temporarily unavailable. No automatic retry was made."
            else:
                message = "Gemini rejected this request. Check the selected model and account settings."
            # Deliberately do not read, interpolate, or log the provider body.
            raise GeminiError(message)
        declared = response.headers.get("Content-Length")
        if declared is not None:
            try:
                declared = int(declared)
            except (TypeError, ValueError):
                raise GeminiError("Gemini returned an unreadable response size.") from None
            if declared < 0 or declared > MAX_RESPONSE_BYTES:
                raise GeminiError("Gemini returned an oversized response.")
        chunks, size, started = [], 0, time.monotonic()
        for chunk in response.iter_content(chunk_size=65536):
            if time.monotonic()-started > _MAX_DOWNLOAD_SECONDS:
                raise GeminiError("Gemini's response took too long. No automatic retry was made.")
            if not chunk:
                continue
            if not isinstance(chunk, bytes):
                raise GeminiError("Gemini returned an unreadable response.")
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise GeminiError("Gemini returned an oversized response.")
            chunks.append(chunk)
        try:
            result = json.loads(b"".join(chunks).decode("utf-8"),
                                object_pairs_hook=_json_pairs, parse_constant=_no_constant)
        except (UnicodeError, ValueError, RecursionError):
            raise GeminiError("Gemini returned invalid response JSON.") from None
        if not isinstance(result, dict):
            raise GeminiError("Gemini did not return one interaction object.")
        return result
    except requests.exceptions.RequestException:
        # Exceptions may contain URLs, proxy credentials, or request headers.
        raise GeminiError("Could not reach Gemini. Check the connection. No automatic retry was made.") from None
    finally:
        if response is not None:
            response.close()
