#!/bin/zsh
set -euo pipefail
studio_root="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$studio_root"
.venv-cartoon/bin/python -m lesson_video.cartoon_launcher --stop
