"""Real local inference checks; run in .venv-speech after voice setup."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np
from lesson_video.neural_audio import MODEL_FILES, NeuralNarrator, WORDS, verify_models

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / '.cache/kokoro'
AVAILABLE = bool(importlib.util.find_spec('kokoro_onnx')) and all((ASSETS / name).is_file() for name in MODEL_FILES)


class AssetValidation(unittest.TestCase):
    def test_changed_model_is_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'kokoro-v1.0.onnx').write_bytes(b'not the pinned model')
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                verify_models(Path(folder))


@unittest.skipUnless(AVAILABLE, 'Optional pinned local voice assets and requirements-speech.txt are needed.')
class RealNeuralAudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temporary.name)
        cls.narrator = NeuralNarrator(ASSETS, cls.folder / 'cache')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def check_audio(self, path, metadata):
        with wave.open(str(path), 'rb') as audio:
            self.assertEqual((audio.getframerate(), audio.getnchannels(), audio.getsampwidth()), (48000, 1, 2))
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2')
        self.assertEqual(len(samples), metadata['frames'])
        self.assertGreater(float(np.sqrt(np.mean(samples.astype(float) ** 2))), 50)
        self.assertGreater(metadata['duration'], .1)
        self.assertEqual(metadata['clipped_samples'], 0)
        self.assertLessEqual(metadata['peak_dbfs'], -1.99)

    def test_actual_phrase_is_audible_and_repeated_output_is_cached_identically(self):
        text = "Let's help our buddy! What do you think?"
        first, second = self.folder / 'first.wav', self.folder / 'second.wav'
        initial = self.narrator.synthesize(text, first)
        repeated = self.narrator.synthesize(text, second)
        self.check_audio(first, initial)
        self.assertTrue(repeated['cache_hit'])
        self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), hashlib.sha256(second.read_bytes()).hexdigest())

    def test_all_count_words_have_real_timed_audio_without_clipping(self):
        for number, word in enumerate(WORDS):
            target = self.folder / f'number-{number}.wav'
            clip = self.narrator.synthesize(word.capitalize() + '.', target, speed=.82, count=number)
            self.check_audio(target, clip)
            self.assertEqual(clip['sequence_index'], number)
            self.assertEqual(clip['text'].lower(), word + '.')
            self.assertLess(clip['duration'], 2.0)

    def test_count_label_cannot_disagree_with_requested_word(self):
        for text, count in [('Seven.', 6), ('One. Two.', 1), ('Zero.', -1), ('Ten.', True)]:
            with self.assertRaises(ValueError):
                self.narrator.synthesize(text, self.folder / 'invalid.wav', count=count)
        self.assertFalse((self.folder / 'invalid.wav').exists())

    def test_invalid_cache_metadata_is_recovered(self):
        text = 'Look closely at the wagon.'
        first = self.narrator.synthesize(text, self.folder / 'recovery.wav')
        sidecar = self.folder / 'cache' / f"{first['cache_key']}.json"
        altered = json.loads(sidecar.read_text()); altered['frames'] = -1
        sidecar.write_text(json.dumps(altered))
        repaired = self.narrator.synthesize(text, self.folder / 'recovery.wav')
        self.assertFalse(repaired['cache_hit'])
        self.check_audio(self.folder / 'recovery.wav', repaired)


if __name__ == '__main__':
    unittest.main()
