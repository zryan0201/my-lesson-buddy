"""Explicit local model download; ordinary app startup never downloads weights."""
import argparse
import os
from .cartoon_makeover import download_models, model_status, DEFAULT_CACHE


def main():
    parser = argparse.ArgumentParser(description='Prepare the local cartoon makeover model (~3.5 GB).')
    parser.add_argument('--download', action='store_true', help='Download pinned models, including the safety checker.')
    args = parser.parse_args()
    if args.download:
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        download_models()
    status = model_status(); print(status['message']); print('Cache:', DEFAULT_CACHE)
    if status['ready']:
        print('Start: python -m lesson_video.cartoon_web --port 8613')
    return 0 if status['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
