# Legacy macOS narration comparison

[Python lesson guide](../README.md) · [Current browser narration](../../web_site/README.md#regenerate-narration-or-deploy)

This folder retains metadata from an earlier comparison of installed macOS voices. The current browser website uses prerecorded Kokoro narration; the Python lesson generator defaults to macOS Samantha.

## What is recorded

The three historical clips used the same text:

> Hi, math friends! Three plus two equals five. Let us count together.

| Voice | Locale | Rate |
| --- | --- | --- |
| Samantha | US English | 145 words/minute. |
| Daniel | British English | 140 words/minute. |
| Karen | Australian English | 145 words/minute. |

`comparison_manifest.json` records the durations, levels, cache keys, and hashes from that run. The generated WAVs are excluded from version control. These measurements describe format and signal checks, not a listening study or a claim that a particular voice is available on every Mac.

The processing target was mono 48 kHz, 16-bit PCM, with normalized active speech, a peak ceiling, trimmed edge silence, and boundary fades. Answer pauses belong to the video timeline; no music or counting chimes are mixed into these voice samples.

## Generate a local sample

Use a Mac with the requested installed voice, FFmpeg, NumPy, and the project's [Python environment](../../docs/SETUP.md). From the repository root:

```python
from lesson_video.audio import synthesize

clip = synthesize(
    "Four dots take away one dot leaves three dots.",
    "output/audio_comparison/subtraction.wav",
    voice="Samantha",
    rate=145,
)
print(clip["duration"], clip["path"])
```

List installed voices with `python -m lesson_video.audio --voices`. Synthesis uses the local speech service; a denied service or silent output raises an error. A cache key includes the text, voice, rate, macOS version, and processor version. Different Macs or voice versions can produce different waveforms. No external speech API is required.
