"""Local Kokoro narration, with verified weights and reusable phrase audio.

No network requests are made by this module. Download the two pinned assets
with scripts/setup_neural_voice.py once, then synthesis is entirely offline.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import wave

import numpy as np

from .audio import SAMPLE_RATE, _finish_speech, _read_wav

MODEL_FILES = {
    'kokoro-v1.0.onnx': 'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a',
    'voices-v1.0.bin': 'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d',
}
MODEL_RELEASE = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1'
WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten')


def verify_models(directory: Path) -> None:
    for name, expected in MODEL_FILES.items():
        path = directory / name
        if not path.is_file():
            raise RuntimeError(f'Missing local voice asset {name}; run scripts/setup_neural_voice.py first.')
        with path.open('rb') as source:
            actual = hashlib.file_digest(source, 'sha256').hexdigest()
        if actual != expected:
            raise RuntimeError(f'Voice asset checksum mismatch: {name}. Download the pinned release again.')


def phrase_speed(key: str) -> float:
    """Small, authored pacing changes; no pitch shifting or accelerated playback."""
    if key.startswith('number-'):
        return .82
    if 'celebrate' in key:
        return .94
    if 'intro' in key or key == 'hello':
        return .90
    if 'turn' in key or key.startswith('answer-'):
        return .82
    return .86


class NeuralNarrator:
    def __init__(self, model_dir: Path, cache_dir: Path, voice: str = 'af_heart'):
        verify_models(model_dir)
        import onnxruntime as rt
        from kokoro_onnx import Kokoro
        options = rt.SessionOptions()
        options.intra_op_num_threads = 4
        rt.disable_telemetry_events()
        session = rt.InferenceSession(str(model_dir / 'kokoro-v1.0.onnx'),
                                     sess_options=options, providers=['CPUExecutionProvider'])
        self.model = Kokoro.from_session(session, str(model_dir / 'voices-v1.0.bin'))
        if voice not in self.model.voices:
            raise ValueError('Choose an installed Kokoro voice.')
        self.voice = voice
        self.cache = cache_dir
        self.cache.mkdir(parents=True, exist_ok=True)
        self.engine = {'engine': 'Kokoro-82M ONNX local CPU', 'voice': voice, 'language': 'en-us',
                       'model_sha256': MODEL_FILES['kokoro-v1.0.onnx'],
                       'voices_sha256': MODEL_FILES['voices-v1.0.bin'],
                       'kokoro_onnx': importlib.metadata.version('kokoro-onnx'),
                       'cache_version': 'natural-narration-v1'}
        self.counts = None

    def fingerprint(self, text: str, speed: float, *, sequence_index: int | None = None) -> str:
        settings = {**self.engine, 'text': text, 'speed': speed, 'sequence_index': sequence_index}
        return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()

    def _count_sequence(self):
        # One connected counting performance gives the short numbers context.
        # Model phoneme timings, not guessed silence cuts, isolate each word.
        text = '. '.join(word.capitalize() for word in WORDS) + '.'
        audio, rate, timings = self.model.create_timed(text, voice=self.voice,
            speed=.82, lang='en-us', sentence_pause=.28, clause_pause=.1)
        stops = [timing.end for timing in timings if timing.phoneme == '.']
        if len(stops) != len(WORDS):
            raise RuntimeError('The counting performance did not return eleven verified word boundaries.')
        bounds = [0.0, *stops]
        self.counts = [(audio[round(bounds[i]*rate):round(bounds[i+1]*rate)], rate)
                       for i in range(len(WORDS))]

    def synthesize(self, text: str, output_path: Path, *, speed: float = .86,
                   count: int | None = None) -> dict:
        if not isinstance(text, str) or not text.strip() or len(text) > 10000 or '[[' in text or ']]' in text:
            raise ValueError('Use a nonempty, plain narration phrase.')
        if not .7 <= speed <= 1.15:
            raise ValueError('Choose a child-friendly voice speed between 0.7 and 1.15.')
        if count is not None and (type(count) is not int or not 0 <= count <= 10 or
                                  text.lower().strip() != WORDS[count] + '.'):
            raise ValueError('A counting clip must contain exactly its checked number word.')
        if count is not None:
            speed = .82
        output_path = Path(output_path)
        if output_path.suffix.lower() != '.wav':
            raise ValueError('Neural narration output must be a WAV file.')
        key = self.fingerprint(text, speed, sequence_index=count)
        cached, sidecar = self.cache / f'{key}.wav', self.cache / f'{key}.json'
        metadata = None
        if cached.is_file() and sidecar.is_file():
            try:
                candidate = json.loads(sidecar.read_text())
                samples = _read_wav(cached)
                if candidate['cache_key'] == key and len(samples) == candidate['frames']:
                    metadata = candidate
            except (OSError, ValueError, KeyError, wave.Error):
                pass
        cache_hit = metadata is not None
        if metadata is None:
            if count is not None:
                if self.counts is None:
                    self._count_sequence()
                samples, rate = self.counts[count]
            else:
                samples, rate = self.model.create(text, voice=self.voice, speed=speed,
                    lang='en-us', sentence_pause=.26, clause_pause=.12)
            result = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error',
                '-f', 'f32le', '-ar', str(rate), '-ac', '1', '-i', 'pipe:0',
                '-f', 'f64le', '-ar', str(SAMPLE_RATE), '-ac', '1', 'pipe:1'],
                input=np.asarray(samples, dtype='<f4').tobytes(), capture_output=True, check=True)
            pcm, stats = _finish_speech(np.frombuffer(result.stdout, dtype='<f8'))
            metadata = {**self.engine, **stats, 'text': text, 'speed': speed,
                        'sequence_index': count, 'cache_key': key}
            temporary = cached.with_suffix('.tmp.wav')
            with wave.open(str(temporary), 'wb') as target:
                target.setnchannels(1); target.setsampwidth(2); target.setframerate(SAMPLE_RATE)
                target.writeframes(pcm.tobytes())
            os.replace(temporary, cached)
            sidecar.write_text(json.dumps(metadata, indent=2) + '\n')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.resolve() != cached.resolve():
            import shutil
            shutil.copyfile(cached, output_path)
        return {**metadata, 'path': str(output_path), 'cache_hit': cache_hit}
