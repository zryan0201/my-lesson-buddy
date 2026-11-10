"""Start the local Streamlit screen and Flask lesson service together."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser


def _port_available(port):
    with socket.socket() as connection:
        try:
            connection.bind(('127.0.0.1',port))
        except OSError:
            return False
    return True


def main():
    root=Path(__file__).resolve().parent.parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8501,help='Local screen port.')
    parser.add_argument('--api-port',type=int,default=5001,help='Local lesson-service port.')
    parser.add_argument('--storage-dir',type=Path,default=root/'.cache/web_jobs')
    parser.add_argument('--reader',choices=('local-vision','gemini'),
                        default=os.environ.get('LESSON_VISION_READER','local-vision'),
                        help='Worksheet reader: local model by default, or explicitly enabled Gemini API.')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    if args.reader not in ('local-vision','gemini'):
        parser.error('LESSON_VISION_READER must be local-vision or gemini.')
    if not all(1024<=value<=65535 for value in (args.port,args.api_port)) or args.port==args.api_port:
        parser.error('Choose two different ports from 1024 to 65535.')
    packages=('flask','streamlit','mlx_vlm') if args.reader=='local-vision' else ('flask','streamlit')
    for package in packages:
        if importlib.util.find_spec(package) is None:
            parser.error('Activate .venv and run python -m pip install -r requirements-web.txt first.')
    if args.reader=='local-vision':
        from .local_vision import resolve_model_path,LocalVisionError
        try:
            resolve_model_path()
        except LocalVisionError:
            parser.error('The local vision model is missing. Run python -m lesson_video.setup_vision once.')
    else:
        from .gemini_client import configured
        if not configured():
            parser.error('Gemini requires GEMINI_ENABLED=1 and GEMINI_API_KEY on the server. Choose --reader local-vision to keep using the local model.')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        parser.error('FFmpeg and ffprobe must be installed before starting the lesson app.')
    if not shutil.which('say'):
        parser.error('This first local app uses the Mac speech voice. A cloud voice adapter is still needed on Linux.')
    if not all(_port_available(port) for port in (args.port,args.api_port)):
        parser.error('One app port is already in use. Close the existing app or choose --port and --api-port values.')
    logs=root/'output/web_prototype'
    logs.mkdir(parents=True,exist_ok=True)
    processes=[]
    environment=os.environ.copy()
    environment['LESSON_API_URL']=f'http://127.0.0.1:{args.api_port}'
    environment['LESSON_VISION_READER']=args.reader
    environment['PYTHONUNBUFFERED']='1'
    url=f'http://127.0.0.1:{args.port}'
    try:
        with (logs/'api.log').open('a') as api_log,(logs/'screen.log').open('a') as screen_log:
            processes.append(subprocess.Popen([sys.executable,'-m','lesson_video.web_api',
                                                '--port',str(args.api_port),'--storage-dir',str(args.storage_dir)],
                                               cwd=root,env=environment,stdout=api_log,stderr=subprocess.STDOUT,
                                               start_new_session=True))
            deadline=time.monotonic()+30
            while True:
                if processes[0].poll() is not None:
                    raise RuntimeError(f'The lesson service stopped. See {logs/"api.log"}.')
                try:
                    with urlopen(environment['LESSON_API_URL']+'/api/health',timeout=1) as response:
                        if response.status==200:
                            break
                except (URLError,TimeoutError,OSError):
                    pass
                if time.monotonic()>=deadline:
                    raise RuntimeError(f'The lesson service did not start. See {logs/"api.log"}.')
                time.sleep(.2)
            processes.append(subprocess.Popen([sys.executable,'-m','streamlit','run',str(root/'streamlit_app.py'),
                                                '--server.address','127.0.0.1','--server.port',str(args.port),
                                                '--server.headless','true','--browser.gatherUsageStats','false',
                                                '--theme.base','light'],
                                               cwd=root,env=environment,stdout=screen_log,stderr=subprocess.STDOUT,
                                               start_new_session=True))
            deadline=time.monotonic()+30
            while True:
                if processes[1].poll() is not None:
                    raise RuntimeError(f'The lesson screen stopped. See {logs/"screen.log"}.')
                try:
                    with urlopen(url+'/_stcore/health',timeout=1) as response:
                        if response.status==200:
                            break
                except (URLError,TimeoutError,OSError):
                    pass
                if time.monotonic()>=deadline:
                    raise RuntimeError(f'The lesson screen did not start. See {logs/"screen.log"}.')
                time.sleep(.2)
            print(f'Your lesson studio is starting at {url}',flush=True)
            print('Keep this terminal open. Press Control+C here to stop both services.',flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            while all(process.poll() is None for process in processes):
                time.sleep(.5)
            raise RuntimeError(f'A service stopped. Check the logs in {logs}.')
    except KeyboardInterrupt:
        print('\nStopping the lesson studio.',flush=True)
        return 0
    except RuntimeError as error:
        print(str(error),file=sys.stderr)
        return 1
    finally:
        for process in processes:
            try:
                os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:
                pass
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()


if __name__=='__main__':
    raise SystemExit(main())
