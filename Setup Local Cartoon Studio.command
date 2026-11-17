#!/bin/zsh
set -euo pipefail
studio_root="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$studio_root"
if ! command -v uv >/dev/null; then
  print 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/'
  exit 1
fi
print 'Installing the local runtime and downloading about 3.5 GB of pinned model files.'
if [[ ! -x .venv-cartoon/bin/python ]]; then
  UV_CACHE_DIR=.cache/uv uv venv .venv-cartoon --python 3.12
fi
UV_CACHE_DIR=.cache/uv uv pip install --python .venv-cartoon/bin/python -r requirements-cartoon.lock.txt
HF_HUB_DISABLE_TELEMETRY=1 .venv-cartoon/bin/python -m lesson_video.cartoon_setup --download
print 'Setup complete. Open Start Local Cartoon Studio.command.'
