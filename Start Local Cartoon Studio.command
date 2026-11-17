#!/bin/zsh
set -euo pipefail
studio_root="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$studio_root"
if [[ ! -x .venv-cartoon/bin/python ]]; then
  print 'Run Setup Local Cartoon Studio.command once, then open this launcher again.'
  exit 1
fi
.venv-cartoon/bin/python -m lesson_video.cartoon_launcher
open 'http://127.0.0.1:8613/'
