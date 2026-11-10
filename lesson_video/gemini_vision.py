"""Read a worksheet with opt-in Gemini, then check all lesson math locally."""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .gemini_client import GeminiError, configured, request_interaction
from .local_vision import (LocalVisionError, VISION_PROMPT, parse_model_response,
                           validate_interpretation)


DEFAULT_MODEL = "gemini-3.8-flash"
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_IMAGE_PIXELS = 20_000_000
_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["ready", "unclear", "unsupported"]},
        "exercise_count": {"type": "integer"},
        "task_type": {"type": "string", "enum": ["addition", "subtraction", "counting", "shape"]},
        "a": {"type": ["integer", "null"]},
        "b": {"type": ["integer", "null"]},
        "unknown_operand": {"type": "boolean"},
        "printed_answer": {"type": ["integer", "null"]},
        "object_label": {"type": "string"},
        "object_label_plural": {"type": "string"},
        "shape": {"type": ["string", "null"]},
        "shape_task": {"type": ["string", "null"]},
        "task_text": {"type": "string"},
        "uncertainty": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["status", "exercise_count", "task_type", "a", "b", "unknown_operand",
                 "printed_answer", "object_label", "object_label_plural", "shape", "shape_task",
                 "task_text", "uncertainty", "reason"],
}


def _image_input(image_path):
    source = Path(image_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Worksheet image not found: {source}")
    if not 0 < source.stat().st_size <= _MAX_IMAGE_BYTES:
        raise GeminiError("Use a PNG or JPEG worksheet image no larger than 10 MB.")
    try:
        with Image.open(source) as opened:
            if opened.format not in ("PNG", "JPEG") or getattr(opened, "n_frames", 1) != 1:
                raise GeminiError("Use one PNG or JPEG worksheet image, with no animation or multiple pages.")
            if min(opened.size) < 40 or opened.width*opened.height > _MAX_IMAGE_PIXELS:
                raise GeminiError("Use a clear worksheet image with sides of at least 40 pixels and at most 20 megapixels.")
            image = ImageOps.exif_transpose(opened).convert("RGBA")
            image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            white = Image.new("RGBA", image.size, "white")
            white.alpha_composite(image)
            image = white.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise GeminiError("Could not open this worksheet. Export one clear PNG or JPEG image.") from None
    data = io.BytesIO()
    # New image encoding intentionally excludes EXIF location and other metadata.
    image.save(data, format="PNG")
    return {"type": "image", "mime_type": "image/png",
            "data": base64.b64encode(data.getvalue()).decode("ascii")}


def _output_text(interaction):
    if not isinstance(interaction, dict) or interaction.get("status") not in (None, "completed"):
        raise GeminiError("Gemini did not complete the worksheet reading. Review the picture and try again.")
    steps = interaction.get("steps")
    if not isinstance(steps, list):
        raise GeminiError("Gemini returned no worksheet interpretation.")
    outputs = [step for step in steps if isinstance(step, dict) and step.get("type") == "model_output"]
    if len(outputs) != 1:
        raise GeminiError("Gemini did not return one final worksheet interpretation.")
    content = outputs[0].get("content")
    if not isinstance(content, list) or not content:
        raise GeminiError("Gemini returned no worksheet interpretation.")
    pieces = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "text" or not isinstance(part.get("text"), str):
            raise GeminiError("Gemini returned an unexpected worksheet response type.")
        pieces.append(part["text"])
    raw = "".join(pieces)
    if not raw.strip() or len(raw) > 30000:
        raise GeminiError("Gemini returned an empty or oversized worksheet interpretation.")
    return raw


def read_gemini_vision(image_path):
    """Send one normalized image only when explicitly enabled, with no retries.

    Gemini describes the visible problem. The same strict validator used for
    the local model rejects ambiguity and computes the answer in Python. Raw
    model text is retained for the adult review evidence, never executed.
    """
    if not configured():
        raise GeminiError("Gemini is off. Configure GEMINI_API_KEY and explicitly set GEMINI_ENABLED=1 to use it.")
    model = os.environ.get("GEMINI_VISION_MODEL", DEFAULT_MODEL)
    image = _image_input(image_path)
    interaction = request_interaction(
        model, [{"type": "text", "text": VISION_PROMPT}, image],
        response_format={"type": "text", "mime_type": "application/json", "schema": _SCHEMA},
    )
    raw = _output_text(interaction)
    try:
        extraction = parse_model_response(raw)
        checked = validate_interpretation(extraction)
    except LocalVisionError:
        # Validator errors may include untrusted model reasons. Keep those in
        # review evidence only after a successful validated interpretation.
        raise GeminiError("Gemini's worksheet reading did not pass the lesson checks. Crop one clear supported K–2 question and try again.") from None
    return {**checked, "method": "gemini_vision", "extraction": extraction,
            "raw_response": raw, "model": model, "provider": "Gemini",
            "finish_reason": "completed", "reader": "Google Gemini cloud vision model",
            "external_api_used": True}
