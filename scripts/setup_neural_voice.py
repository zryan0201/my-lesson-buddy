"""Download the pinned public Kokoro assets; no speech is sent to a service."""
import hashlib
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lesson_video.neural_audio import MODEL_FILES, MODEL_RELEASE

def main():
    target = ROOT / '.cache/kokoro'
    target.mkdir(parents=True, exist_ok=True)
    for name, digest in MODEL_FILES.items():
        path = target / name
        if path.exists():
            with path.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() == digest:
                    print(f'{name}: verified', flush=True)
                    continue
        partial = path.with_suffix(path.suffix + '.partial')
        request = urllib.request.Request(f'{MODEL_RELEASE}/{name}', headers={'User-Agent':'LessonBuddyVoiceSetup/1'})
        with urllib.request.urlopen(request, timeout=60) as source, partial.open('wb') as output:
            while block := source.read(1024*1024):
                output.write(block)
        with partial.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                raise RuntimeError(f'Checksum mismatch for {name}; the current model was not replaced.')
        partial.replace(path)
        print(f'{name}: downloaded and verified', flush=True)

if __name__ == '__main__':
    main()
