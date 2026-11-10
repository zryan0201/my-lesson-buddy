# Local narration comparison

All three WAVs speak the same text:

> Hi, math friends! Three plus two equals five. Let us count together.

- `samantha_clear.wav`: Samantha, US English, 145 words per minute.
- `daniel_clear.wav`: Daniel, British English, 140 words per minute.
- `karen_clear.wav`: Karen, Australian English, 145 words per minute.

These use the Mac's installed speech engine. No external service, voice download,
or API key was used. The local voice catalog does not identify these as enhanced
voices, and no separately installed enhanced voice asset was found. Cleaning up
levels, pacing, and competing effects can improve intelligibility; it cannot make
an older synthetic voice sound like a new neural narrator.

Each clip is mono 48 kHz 16-bit PCM WAV, leveled toward -20 dBFS active speech RMS
with a -2 dBFS peak ceiling. The processor trims excess edge silence, retains
internal pauses, and adds a 6 ms boundary fade. No music or counting chimes are
mixed into the voice. Leave answer pauses to the video timeline.

`comparison_manifest.json` records duration, levels, cache keys, and checksums.
All three files passed format, audible-signal, peak, and clipping checks. Reusing
the cache produced byte-for-byte identical output.

## Reuse

From the project root:

```python
from lesson_video.audio import synthesize

clip = synthesize(
    "Four dots take away one dot leaves three dots.",
    "lesson_video/audio_samples/subtraction.wav",
    voice="Samantha",
    rate=145,
)
print(clip["duration"], clip["path"])
```

The engine requires macOS `say`, FFmpeg on PATH, and NumPy. Cached speech works
without contacting the speech service. In this app's restricted sandbox, uncached
speech returned silence; generating the authorized narration required an approved
run with local speech-service access. `synthesize` detects silence and fails rather
than quietly rendering a silent lesson. It does not bypass permissions.

The `.cache` folder stores the finished audio by a hash of text, voice, rate,
macOS version, and processor version. Keeping these files makes future renders
repeatable. Another Mac or voice version may synthesize a different waveform.

To list voices already exposed by the local engine:

```sh
python3 lesson_video/audio.py --voices
```
