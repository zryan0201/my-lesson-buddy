"""Read printed worksheet text locally using macOS Apple Vision.

``recognize_text(path)`` returns text and line confidence/bounding boxes. Boxes
are normalized [x, y, width, height], measured from the top-left of the image
after EXIF orientation. ``image_width`` and ``image_height`` describe that
oriented image. Text is untrusted worksheet content, never executable code.

The first call compiles the bundled Swift helper with Apple's local compiler;
later calls reuse the compiled binary. There are no APIs, model downloads,
credentials, or network requests. OCR is limited to printed English and may
misread handwritten numbers and mathematical signs.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile


SOURCE = Path(__file__).with_name("vision_ocr.swift")
DEFAULT_CACHE = Path(__file__).resolve().parent.parent / ".cache" / "worksheet_ocr"
CACHE_VERSION = "vision-ocr-v1"


class OcrUnavailable(RuntimeError):
    """Apple Vision or its local compiler could not be used."""


def _compiler_binary(cache_dir: Path) -> Path:
    if platform.system() != "Darwin":
        raise OcrUnavailable("Local worksheet OCR requires macOS Apple Vision.")
    compiler = shutil.which("swiftc")
    if not compiler:
        raise OcrUnavailable(
            "Local worksheet OCR needs Apple's Swift compiler. Install the "
            "Xcode Command Line Tools with 'xcode-select --install', then retry."
        )
    try:
        version = subprocess.run(
            [compiler, "--version"], capture_output=True, text=True,
            check=True, timeout=30,
        ).stdout.strip()
        source = SOURCE.read_bytes()
        cache_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(
            source + version.encode() + CACHE_VERSION.encode()
        ).hexdigest()[:20]
        binary = cache_dir / f"worksheet-ocr-{digest}"
        if binary.is_file() and os.access(binary, os.X_OK):
            return binary
        module_cache = cache_dir / "swift_modules"
        module_cache.mkdir(exist_ok=True)
        environment = os.environ.copy()
        environment["CLANG_MODULE_CACHE_PATH"] = str(module_cache)
        environment["SWIFT_MODULECACHE_PATH"] = str(module_cache)
        # The temporary executable and final executable share a filesystem so
        # replacement is atomic, including when two lessons start together.
        with tempfile.TemporaryDirectory(prefix="build-", dir=cache_dir) as work:
            temporary_binary = Path(work) / "worksheet-ocr"
            result = subprocess.run(
                [compiler, str(SOURCE), "-O", "-module-cache-path", str(module_cache),
                 "-o", str(temporary_binary)],
                capture_output=True, text=True, timeout=180, env=environment,
            )
            if result.returncode:
                raise OcrUnavailable(
                    "Apple Vision helper compilation failed. Check the Xcode "
                    "Command Line Tools installation. " + result.stderr.strip()[:2000]
                )
            temporary_binary.replace(binary)
        return binary
    except OcrUnavailable:
        raise
    except (OSError, subprocess.SubprocessError) as error:
        raise OcrUnavailable(f"Could not prepare local Apple Vision OCR: {error}") from error


def recognize_text(
    image_path: str | os.PathLike,
    *,
    cache_dir: str | os.PathLike | None = None,
) -> dict:
    """Return locally recognized text, line confidence and normalized boxes.

    Empty text and an empty line list are valid when no printing is recognized;
    they do not mean the picture contains no mathematical objects. Multiple
    image frames/pages are not supported; only the first image is recognized.
    """
    path = Path(image_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Worksheet image does not exist: {path}")
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Worksheet images must be smaller than 100 MB.")
    cache = Path(cache_dir).expanduser().resolve() if cache_dir else DEFAULT_CACHE
    binary = _compiler_binary(cache)
    try:
        result = subprocess.run(
            [str(binary), str(path)], capture_output=True, text=True, timeout=90,
        )
        if result.returncode:
            message = result.stderr.strip()[:2000] or "Apple Vision text recognition failed."
            if "_GenericObjCError error 0" in message:
                message += (
                    " A restricted automation sandbox can block macOS recognition. "
                    "Try running the same lesson command in your Mac's Terminal."
                )
            raise OcrUnavailable(message)
        output = json.loads(result.stdout)
        if output.get("engine") != "Apple Vision" or not isinstance(output.get("text"), str):
            raise ValueError("Unexpected OCR response.")
        if not isinstance(output.get("lines"), list):
            raise ValueError("Unexpected OCR line list.")
        for dimension in ("image_width", "image_height"):
            if not isinstance(output.get(dimension), int) or output[dimension] <= 0:
                raise ValueError("Unexpected OCR image size.")
        for line in output["lines"]:
            if not isinstance(line.get("text"), str):
                raise ValueError("Unexpected OCR line text.")
            confidence = line.get("confidence")
            if not isinstance(confidence, (float, int)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Unexpected OCR confidence.")
            box = line.get("bbox")
            if not isinstance(box, list) or len(box) != 4 or not all(
                isinstance(value, (float, int)) and math.isfinite(value)
                and -0.001 <= value <= 1.001 for value in box
            ):
                raise ValueError("Unexpected OCR bounding box.")
        return output
    except OcrUnavailable:
        raise
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError) as error:
        raise OcrUnavailable(f"Local Apple Vision OCR failed: {error}") from error
