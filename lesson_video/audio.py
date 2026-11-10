"""Repeatable local narration for lesson videos (macOS ``say`` + FFmpeg).

``synthesize(text, output_path, voice="Samantha", rate=145)`` writes a mono,
48 kHz, signed 16-bit PCM WAV and returns a metadata dictionary.  It does not
add music or sound effects.  No network, API keys, or model download is used.

Speech quality is limited by the voice installed on the Mac.  The cache makes
repeated renders byte-for-byte repeatable on this computer; another macOS or
voice version can synthesize different waveforms from the same text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import wave

import numpy as np


SAMPLE_RATE = 48_000
CACHE_VERSION = "local-speech-v2-20261019"
DEFAULT_CACHE = Path(__file__).resolve().parent / "audio_samples" / ".cache"
TARGET_ACTIVE_RMS_DBFS = -20.0
PEAK_CEILING_DBFS = -2.0


def installed_voices() -> list[dict[str, str]]:
    """Return the voices exposed by this Mac, without downloading voices."""
    executable = shutil.which("say")
    if not executable:
        raise RuntimeError("Local narration requires macOS and its 'say' command.")
    result = subprocess.run(
        [executable, "-v", "?"], capture_output=True, text=True, check=True
    )
    voices = []
    for line in result.stdout.splitlines():
        match = re.match(r"^(.*?)\s+([a-z]{2}_[A-Za-z0-9]+)\s+#\s*(.*)$", line)
        if match:
            voices.append({"name": match[1].strip(), "locale": match[2], "example": match[3]})
    return voices


def _db(value: float) -> float | None:
    return round(20 * math.log10(value), 3) if value > 0 else None


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise ValueError(f"Expected 48 kHz mono 16-bit PCM WAV: {path}")
        return np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float64) / 32768.0


def _finish_speech(samples: np.ndarray) -> tuple[np.ndarray, dict]:
    """Trim only edge silence; level active speech with transparent peak headroom."""
    if samples.size == 0 or np.max(np.abs(samples)) < 0.001:
        raise RuntimeError("The speech engine produced no audible narration.")

    window = SAMPLE_RATE // 100  # 10 ms prevents a single quiet sample defining a cut.
    padded = np.pad(samples, (0, (-len(samples)) % window))
    energy = np.sqrt(np.mean(padded.reshape(-1, window) ** 2, axis=1))
    threshold = max(10 ** (-48 / 20), float(energy.max()) * 10 ** (-38 / 20))
    active = np.flatnonzero(energy >= threshold)
    if not len(active):
        raise RuntimeError("The speech engine produced only silence.")

    original_frames = len(samples)
    start = max(0, int(active[0]) * window - round(0.08 * SAMPLE_RATE))
    stop = min(len(samples), (int(active[-1]) + 1) * window + round(0.18 * SAMPLE_RATE))
    samples = samples[start:stop].copy()

    # Estimate level from voiced 10 ms windows.  Pauses should not cause a
    # sentence to be amplified more than a short counting word.
    padded = np.pad(samples, (0, (-len(samples)) % window))
    windows = padded.reshape(-1, window)
    rms_windows = np.sqrt(np.mean(windows ** 2, axis=1))
    voiced = windows[rms_windows >= threshold]
    active_rms = float(np.sqrt(np.mean(voiced ** 2)))
    peak = float(np.max(np.abs(samples)))
    gain = min(
        10 ** (TARGET_ACTIVE_RMS_DBFS / 20) / active_rms,
        10 ** (PEAK_CEILING_DBFS / 20) / peak,
        10 ** (12 / 20),
    )
    samples *= gain

    # A 6 ms fade only removes discontinuities at the file boundaries.
    fade_length = min(round(0.006 * SAMPLE_RATE), len(samples) // 2)
    if fade_length:
        ramp = np.linspace(0, 1, fade_length)
        samples[:fade_length] *= ramp
        samples[-fade_length:] *= ramp[::-1]

    if not np.isfinite(samples).all() or np.max(np.abs(samples)) >= 1:
        raise RuntimeError("Narration normalization failed its clipping check.")
    pcm = np.rint(samples * 32767).astype("<i2")
    measured = pcm.astype(np.float64) / 32768.0
    stats = {
        "duration": round(len(pcm) / SAMPLE_RATE, 6),
        "frames": len(pcm),
        "sample_rate": SAMPLE_RATE,
        "channels": 1,
        "sample_width": 2,
        "peak_dbfs": _db(float(np.max(np.abs(measured)))),
        "rms_dbfs": _db(float(np.sqrt(np.mean(measured ** 2)))),
        "active_rms_dbfs": _db(active_rms * gain),
        "gain_db": _db(gain),
        "trimmed_head_seconds": round(start / SAMPLE_RATE, 6),
        "trimmed_tail_seconds": round((original_frames - stop) / SAMPLE_RATE, 6),
        "clipped_samples": int(np.count_nonzero(np.abs(pcm.astype(np.int32)) >= 32767)),
    }
    return pcm, stats


def synthesize(
    text: str,
    output_path: str | os.PathLike,
    voice: str = "Samantha",
    rate: int = 145,
    *,
    cache_dir: str | os.PathLike | None = None,
) -> dict:
    """Create clean local speech and return duration, file, voice and level metadata.

    Required runtime: macOS ``say``, FFmpeg on PATH, and NumPy. ``cache_dir``
    optionally selects a writable cache.  ``voice`` must name an installed voice;
    unavailable voices fail clearly instead of silently changing the narrator.
    The caller chooses the timeline pauses; this function preserves speech pauses
    and only trims excess silence at the two edges of a clip.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Narration text must be a nonempty string.")
    text = " ".join(text.split())
    if "[[" in text or "]]" in text:
        raise ValueError("Use plain narration text, without macOS speech control markup.")
    if len(text) > 10_000:
        raise ValueError("Narration clips must contain at most 10,000 characters.")
    if isinstance(rate, bool) or not isinstance(rate, int) or not 80 <= rate <= 300:
        raise ValueError("Speech rate must be an integer from 80 to 300 words per minute.")
    if not isinstance(voice, str) or not voice.strip():
        raise ValueError("Voice must be an installed macOS voice name.")

    output = Path(output_path).expanduser().resolve()
    if output.suffix.lower() != ".wav":
        raise ValueError("Narration output must use the .wav extension.")
    settings = {
        "text": text, "voice": voice, "rate": rate,
        "engine": "macOS say", "macos_version": platform.mac_ver()[0],
        "cache_version": CACHE_VERSION,
    }
    key = hashlib.sha256(json.dumps(settings, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    cache = Path(cache_dir).expanduser().resolve() if cache_dir else DEFAULT_CACHE
    cache.mkdir(parents=True, exist_ok=True)
    cached_wav, cached_json = cache / f"{key}.wav", cache / f"{key}.json"
    cache_hit = False
    metadata = None
    if cached_wav.exists() and cached_json.exists():
        try:
            metadata = json.loads(cached_json.read_text())
            samples = _read_wav(cached_wav)
            if len(samples) != metadata["frames"] or metadata["cache_key"] != key:
                raise ValueError("Mismatched cached narration.")
            cache_hit = True
        except (ValueError, KeyError, OSError, wave.Error):
            metadata = None

    if metadata is None:
        say = shutil.which("say")
        ffmpeg = shutil.which("ffmpeg")
        if not say or platform.system() != "Darwin":
            raise RuntimeError("Local narration requires macOS and the 'say' command.")
        if not ffmpeg:
            raise RuntimeError("FFmpeg is required on PATH to convert local speech to WAV.")
        names = {item["name"] for item in installed_voices()}
        if voice not in names:
            raise ValueError(f"Voice {voice!r} is not installed; use installed_voices() to choose one.")

        with tempfile.TemporaryDirectory(prefix="speech-", dir=cache) as temporary:
            temp = Path(temporary)
            script = temp / "narration.txt"
            script.write_text(text, encoding="utf-8")
            result = subprocess.run(
                [say, "-v", voice, "-r", str(rate), "-o", str(temp / "raw.aiff"), "-f", str(script)],
                capture_output=True, text=True,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()
                raise RuntimeError(
                    "macOS speech generation failed. If this is a restricted sandbox, "
                    "run the same authorized narration step with speech-service access. "
                    f"Engine output: {detail}"
                )
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(temp / "raw.aiff"),
                 "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(temp / "raw.wav")],
                capture_output=True, text=True, check=True,
            )
            pcm, stats = _finish_speech(_read_wav(temp / "raw.wav"))
            ready = temp / "ready.wav"
            with wave.open(str(ready), "wb") as destination:
                destination.setnchannels(1)
                destination.setsampwidth(2)
                destination.setframerate(SAMPLE_RATE)
                destination.writeframes(pcm.tobytes())
            metadata = {**settings, **stats, "cache_key": key}
            sidecar = temp / "ready.json"
            sidecar.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
            os.replace(ready, cached_wav)
            os.replace(sidecar, cached_json)

    output.parent.mkdir(parents=True, exist_ok=True)
    if output != cached_wav:
        shutil.copyfile(cached_wav, output)
    return {**metadata, "path": str(output), "filename": output.name, "cache_hit": cache_hit}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="?", help="Plain narration text")
    parser.add_argument("output", nargs="?", type=Path, help="Output .wav path")
    parser.add_argument("--voice", default="Samantha")
    parser.add_argument("--rate", type=int, default=145)
    parser.add_argument("--voices", action="store_true", help="List available local voices")
    args = parser.parse_args()
    if args.voices:
        print(json.dumps(installed_voices(), indent=2, ensure_ascii=False))
    elif not args.text or not args.output:
        parser.error("Provide narration text and an output .wav path, or --voices.")
    else:
        print(json.dumps(synthesize(args.text, args.output, args.voice, args.rate), indent=2))
