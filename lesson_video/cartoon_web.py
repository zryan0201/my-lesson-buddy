"""Serve the combined studio with an optional same-origin local cartoon worker."""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
from io import BytesIO
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException
from character_studio.images import MAX_UPLOAD_BYTES, normalize_image, png_bytes
from .cartoon_makeover import CartoonRuntime, CartoonError, CartoonCancelled, model_status, validate_options, finish_cartoon

STATIC = Path(__file__).resolve().parents[1] / 'web_site/dist'


class CartoonJobs:
    def __init__(self, runtime=None, clock=time.monotonic):
        self.runtime = runtime or CartoonRuntime(); self.clock = clock
        self.jobs = {}; self.lock = threading.Lock()

    def start(self, raw, options):
        options = validate_options(options)
        # Decode and bound inputs before acquiring a costly model worker.
        normalize_image(raw)
        with self.lock:
            for key, old in list(self.jobs.items()):
                if old['state'] not in ('queued', 'running') and self.clock()-old['updated'] > 30*60:
                    del self.jobs[key]
            if any(j['state'] in ('queued', 'running') for j in self.jobs.values()):
                raise CartoonError('A local makeover is already running. Wait for it to finish or cancel it.')
            if len(self.jobs) >= 8:
                oldest = min(self.jobs, key=lambda key: self.jobs[key]['updated']); del self.jobs[oldest]
            job_id, token = secrets.token_hex(16), secrets.token_urlsafe(24)
            job = {'id': job_id, 'token': token, 'state': 'queued', 'stage': 'loading', 'progress': 0,
                   'updated': self.clock(), 'cancel': threading.Event(), 'source_sha256': hashlib.sha256(raw).hexdigest()}
            self.jobs[job_id] = job
        thread = threading.Thread(target=self._work, args=(job, raw, options), daemon=True, name='local-cartoon')
        thread.start()
        return {**self.public(job), 'token': token}

    def _work(self, job, raw, options):
        def progress(stage, fraction):
            with self.lock:
                job.update(state='running', stage=stage, progress=max(0, min(100, fraction)), updated=self.clock())
        try:
            image, evidence = self.runtime.generate(raw, options.__dict__, progress=progress, cancelled=job['cancel'].is_set)
            result = png_bytes(finish_cartoon(image))
            with self.lock:
                if job['cancel'].is_set():
                    job.update(state='cancelled', updated=self.clock())
                else:
                    job.update(state='ready', stage='ready', progress=100, result=result,
                               evidence=evidence, updated=self.clock())
        except CartoonCancelled:
            with self.lock: job.update(state='cancelled', updated=self.clock())
        except CartoonError as error:
            with self.lock: job.update(state='error', error=str(error), updated=self.clock())
        except Exception:
            # No model stack traces, input descriptions, pixels, or paths in the response.
            with self.lock: job.update(state='error', error='Local cartoon generation could not finish. Your original is safe.', updated=self.clock())

    @staticmethod
    def public(job):
        return {key: job[key] for key in ('id', 'state', 'stage', 'progress', 'source_sha256', 'error', 'evidence') if key in job}

    def lookup(self, job_id, token):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or not token or not hmac.compare_digest(token, job['token']):
                return None
            return job


def create_app(runtime=None):
    app = Flask(__name__, static_folder=None); app.config['MAX_CONTENT_LENGTH'] = 12*1024*1024
    jobs = CartoonJobs(runtime); app.extensions['cartoon_jobs'] = jobs

    @app.before_request
    def local_only():
        if request.host.split(':', 1)[0] not in ('127.0.0.1', 'localhost') or request.remote_addr not in (None, '127.0.0.1', '::1'):
            return jsonify(error='Open this studio on localhost.'), 403
        origin = request.headers.get('Origin')
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme != 'http' or parsed.netloc != request.host:
                return jsonify(error='Use the local studio page for this action.'), 403
        if request.path.startswith('/api/cartoon/') and request.method in ('POST', 'DELETE'):
            if request.headers.get('X-Lesson-Buddy-Local') != '1':
                return jsonify(error='Use the local studio controls.'), 403

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error='This local request could not be completed.'), error.code

    @app.errorhandler(ValueError)
    def input_error(error):
        return jsonify(error=str(error)), 400

    @app.get('/api/cartoon/status')
    def status():
        value = model_status() if runtime is None else {'ready': True, 'local_only': True}
        return jsonify(value)

    @app.post('/api/cartoon/jobs')
    def start():
        value = request.get_json()
        if not isinstance(value, dict) or set(value) != {'image', 'options'}:
            raise CartoonError('Choose one drawing and the displayed options.')
        image = value['image']
        if not isinstance(image, str) or len(image) > 11*1024*1024 or not re.fullmatch(r'data:image/(?:png|jpeg);base64,[A-Za-z0-9+/]+=*', image):
            raise CartoonError('Choose a bounded PNG or JPEG drawing.')
        try: raw = base64.b64decode(image.split(',', 1)[1], validate=True)
        except ValueError as error: raise CartoonError('This drawing could not open.') from error
        if len(raw) > MAX_UPLOAD_BYTES:
            raise CartoonError('Choose a drawing smaller than 8 MB.')
        if runtime is None and not model_status()['ready']:
            return jsonify(error=model_status()['message']), 503
        try: return jsonify(jobs.start(raw, value['options'])), 202
        except CartoonError as error:
            if 'already running' in str(error): return jsonify(error=str(error)), 409
            raise

    def authorized(job_id):
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        job = jobs.lookup(job_id, token)
        return job

    @app.get('/api/cartoon/jobs/<job_id>')
    def job_status(job_id):
        job = authorized(job_id)
        return (jsonify(jobs.public(job)), 200) if job else (jsonify(error='This local job could not be found.'), 404)

    @app.delete('/api/cartoon/jobs/<job_id>')
    def cancel(job_id):
        job = authorized(job_id)
        if not job: return jsonify(error='This local job could not be found.'), 404
        job['cancel'].set()
        with jobs.lock:
            job.pop('result', None)
            if job['state'] not in ('queued', 'running'): job['state'] = 'cancelled'
        return jsonify(state='cancelling')

    @app.get('/api/cartoon/jobs/<job_id>/image')
    def image(job_id):
        job = authorized(job_id)
        if not job or job['state'] != 'ready' or job['cancel'].is_set() or 'result' not in job:
            return jsonify(error='The reviewed cartoon preview is not available.'), 404
        return send_file(BytesIO(job['result']), mimetype='image/png')

    @app.get('/')
    def home(): return send_from_directory(STATIC, 'index.html')

    @app.get('/<path:filename>')
    def static_file(filename):
        if filename.startswith('api/'): return jsonify(error='Unknown local endpoint.'), 404
        return send_from_directory(STATIC, filename)

    return app


def main():
    parser = argparse.ArgumentParser(description='Combined Lesson Buddy studio with local cartoon AI.')
    parser.add_argument('--port', type=int, default=8613)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('Choose a port between 1024 and 65535.')
    print(f'Local cartoon studio: http://127.0.0.1:{args.port}/', flush=True)
    create_app().run(host='127.0.0.1', port=args.port, threaded=True, use_reloader=False)


if __name__ == '__main__': main()
