"""Start/stop the loopback studio independently of an open terminal."""
from pathlib import Path
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8613/'
PID_FILE = ROOT / '.cache/cartoon-studio.pid'
LOG_FILE = ROOT / '.cache/cartoon-studio.log'


def running():
    try:
        with urlopen(URL+'api/cartoon/status', timeout=1) as response:
            return json.load(response).get('local_only') is True
    except Exception:
        return False


def start():
    if running(): return URL
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ); env['HF_HUB_DISABLE_TELEMETRY'] = '1'
    with LOG_FILE.open('ab') as log:
        process = subprocess.Popen([sys.executable, '-m', 'lesson_video.cartoon_web', '--port', '8613'],
                      cwd=ROOT, env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    PID_FILE.write_text(str(process.pid))
    for _ in range(50):
        if running(): return URL
        if process.poll() is not None: break
        time.sleep(.2)
    raise RuntimeError('The studio could not start. Check .cache/cartoon-studio.log or whether port 8613 is in use.')


def stop():
    if not PID_FILE.is_file(): return False
    try: pid = int(PID_FILE.read_text().strip())
    except ValueError: return False
    if pid <= 1: return False
    command = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True).stdout.strip()
    if str(ROOT / '.venv-cartoon') not in command or not command.endswith('-m lesson_video.cartoon_web --port 8613'):
        return False
    os.kill(pid, signal.SIGTERM); PID_FILE.unlink(missing_ok=True); return True


def main():
    parser = argparse.ArgumentParser(description='Run the local cartoon studio in the background.')
    parser.add_argument('--stop', action='store_true'); args = parser.parse_args()
    if args.stop:
        print('Local cartoon studio stopped.' if stop() else 'No launcher-owned studio was found.'); return
    print(start())


if __name__ == '__main__': main()
