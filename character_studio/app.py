"""Loopback-only HTTP interface for an independent character-authoring module."""
from __future__ import annotations

from io import BytesIO
from functools import lru_cache
import json
import logging
from pathlib import Path
import threading
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

from . import assets
from .images import MAX_UPLOAD_BYTES, png_bytes, polish_drawing


LOG = logging.getLogger(__name__)


def create_app(storage_dir=None):
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES + 64*1024
    image_lock = threading.Lock()

    @app.before_request
    def local_requests_only():
        if request.host.split(':', 1)[0] not in ('127.0.0.1', 'localhost'):
            return jsonify(error='Open Character Studio on localhost.'), 403
        origin = request.headers.get('Origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in ('http', 'https') or parsed.netloc != request.host:
                return jsonify(error='Use the Character Studio page to save or edit a character.'), 403

    @app.after_request
    def private_response(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
        )
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {400:'This request could not be read.', 404:'This character could not be found.',
                    413:'Choose a drawing or character package smaller than 8 MB.'}
        return jsonify(error=messages.get(error.code, 'This request could not be completed.')), error.code

    @app.errorhandler(ValueError)
    def input_error(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(Exception)
    def unexpected_error(error):
        # Log no request bodies, image data, or credentials.
        LOG.error('Character Studio request failed: %s', type(error).__name__)
        return jsonify(error='The studio could not finish that action. Your drawing is still here.'), 500

    def file_bytes(allowed_fields=()):
        if (set(request.files) != {'image'} or len(request.files.getlist('image')) != 1
                or set(request.form) - set(allowed_fields)
                or any(len(request.form.getlist(key)) != 1 for key in request.form)):
            raise ValueError('Choose one drawing and the displayed options.')
        raw = request.files['image'].read(MAX_UPLOAD_BYTES+1)
        if len(raw) > MAX_UPLOAD_BYTES:
            raise ValueError('Choose a PNG or JPEG smaller than 8 MB.')
        return raw

    def image_response(image):
        return send_file(BytesIO(png_bytes(image)), mimetype='image/png')

    @lru_cache(maxsize=24)
    def motion_bytes(character_id, motion, image_hash, design_json):
        # Immutable character ID and artwork/design hashes make this a bounded
        # cache of previews, never a source of mutable editing state.
        from .motion import preview_gif
        image = assets.load_character_image(character_id, storage_dir)
        design = json.loads(design_json) if design_json else None
        return preview_gif(design=design, image=image, motion=motion)

    @app.get('/')
    def home():
        return app.send_static_file('index.html')

    @app.get('/api/health')
    def health():
        return jsonify(status='ok', module='character-studio', mode='local-prototype')

    @app.get('/api/catalog')
    def catalog():
        from .parts import catalog
        return jsonify(catalog())

    @app.post('/api/preview')
    def preview():
        from .parts import render_design
        value = request.get_json()
        return image_response(render_design(value))

    @app.post('/api/polish')
    def polish():
        return image_response(polish_drawing(file_bytes()))

    @app.get('/api/ai-status')
    def ai_status():
        from .gemini_makeover import status
        return jsonify(status())

    @app.post('/api/beautify')
    def beautify():
        from .gemini_makeover import beautify, status
        from lesson_video.gemini_client import GeminiError
        raw = file_bytes(('style', 'confirmed'))
        if request.form.get('confirmed') != 'true':
            return jsonify(error='A grown-up must confirm sending this drawing to Google Gemini.'), 400
        if not status()['enabled']:
            return jsonify(error=status()['message']), 503
        if not image_lock.acquire(blocking=False):
            return jsonify(error='A Gemini makeover is already running. Please wait for it to finish.'), 409
        try:
            return image_response(beautify(raw, request.form.get('style', 'storybook')))
        except GeminiError as error:
            return jsonify(error=str(error)), 502
        finally:
            image_lock.release()

    @app.get('/api/characters')
    def characters():
        return jsonify(characters=assets.list_characters(storage_dir))

    @app.post('/api/import')
    def import_package():
        if (set(request.files) != {'package'} or len(request.files.getlist('package')) != 1
                or request.form):
            raise ValueError('Choose one exported character package to bring back.')
        raw = request.files['package'].read(MAX_UPLOAD_BYTES+1)
        if len(raw) > MAX_UPLOAD_BYTES:
            raise ValueError('Choose a character package smaller than 8 MB.')
        return jsonify(assets.import_character(raw, root=storage_dir)), 201

    @app.get('/api/characters/<character_id>/project')
    def character_project(character_id):
        try:
            project = assets.get_project(character_id, storage_dir)
        except ValueError:
            return jsonify(error='This character could not be found.'), 404
        return jsonify(project)

    @app.post('/api/characters/<character_id>/duplicate')
    def duplicate(character_id):
        value = request.get_json()
        if not isinstance(value, dict) or set(value) - {'name'}:
            raise ValueError('Choose a name for the new character copy.')
        return jsonify(assets.duplicate_character(character_id, name=value.get('name'), root=storage_dir)), 201

    @app.get('/api/characters/<character_id>/motion')
    def motion_preview(character_id):
        if set(request.args) - {'motion'} or len(request.args.getlist('motion')) > 1:
            raise ValueError('Choose one character motion.')
        motion = request.args.get('motion', 'idle')
        if motion not in ('idle', 'wave', 'talk', 'celebrate'):
            raise ValueError('Choose idle, wave, talk, or celebrate.')
        try:
            project = assets.get_project(character_id, storage_dir)
            raw = motion_bytes(character_id, motion, project['character']['sha256'],
                               json.dumps(project['design'], sort_keys=True) if project['design'] else '')
        except ValueError:
            return jsonify(error='This character preview could not be opened.'), 404
        return send_file(BytesIO(raw), mimetype='image/gif')

    @app.post('/api/characters')
    def save():
        if any(len(request.form.getlist(key)) != 1 for key in request.form):
            raise ValueError('Choose one name and one design to save.')
        if set(request.form) - {'name', 'source', 'design'}:
            raise ValueError('Save a drawing or the displayed character parts.')
        source = request.form.get('source')
        if source == 'builder':
            if request.files:
                raise ValueError('Save the parts design without an uploaded image.')
            design = json.loads(request.form.get('design', '{}'))
            if not isinstance(design, dict):
                raise ValueError('Choose character parts from the studio.')
            metadata = assets.save_character(request.form.get('name'), source, design=design, root=storage_dir)
        elif source == 'drawing':
            raw = file_bytes(('name', 'source'))
            metadata = assets.save_character(request.form.get('name'), source, image=raw, root=storage_dir)
        else:
            raise ValueError('Choose a drawing or a character made from parts.')
        return jsonify(metadata), 201

    @app.get('/api/characters/<character_id>/image')
    def image(character_id):
        try:
            sprite = assets.load_character_image(character_id, storage_dir)
        except ValueError:
            return jsonify(error='This character could not be found.'), 404
        return image_response(sprite)

    @app.get('/api/characters/<character_id>/package')
    def package(character_id):
        try:
            raw = assets.export_character(character_id, storage_dir)
        except ValueError:
            return jsonify(error='This character could not be found.'), 404
        return send_file(BytesIO(raw), mimetype='application/zip', as_attachment=True,
                         download_name=f'character-{character_id[:8]}.character.zip')

    return app
