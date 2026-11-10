"""Run with python -m character_studio; no model is needed to draw or build."""
import argparse
from pathlib import Path
import webbrowser

from werkzeug.serving import make_server

from .app import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8601)
    parser.add_argument('--storage-dir', type=Path)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a port from 1024 to 65535.')
    # The default store is shared with the lesson app. For a custom store set
    # CHARACTER_STUDIO_STORAGE in both apps, or pass this option to this server.
    server = make_server('127.0.0.1', args.port, create_app(args.storage_dir), threaded=True)
    url = f'http://127.0.0.1:{args.port}'
    print(f'Character Studio is ready at {url}', flush=True)
    print('Keep this terminal open. Press Control+C to stop the studio.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopping Character Studio.', flush=True)
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
