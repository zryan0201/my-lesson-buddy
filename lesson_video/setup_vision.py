"""Explicit, one-time download of the public local worksheet vision model."""
import json

from .local_vision import MODEL_ID


def main():
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise SystemExit('Activate .venv and install requirements-vision.txt first.')
    print(f'Downloading {MODEL_ID} (about 3 GB) to the shared local model cache.',flush=True)
    # Download the full snapshot: newer Hub versions require its metadata too
    # before allowing local_files_only=True. No image is sent to the Hub.
    path=snapshot_download(repo_id=MODEL_ID,max_workers=4)
    print(json.dumps({'model':MODEL_ID,'local_directory':str(path),
                      'setup_complete':True,'api_key_required':False},indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
