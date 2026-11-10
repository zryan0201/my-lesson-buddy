"""Loopback-only Flask API for worksheet review and background generation.

Run ``python -m lesson_video.web_api``. One executor deliberately serializes
model/renderer calls. This local prototype is not a public hosting setup.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
import re
import threading

from flask import Flask, jsonify, request, send_file
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException

from .characters import validate_character
from .job_store import JobStore, RequestConflict


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
NONCE_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")
JOB_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
LOG = logging.getLogger(__name__)


def _normalized_upload(raw):
    if not raw:
        raise ValueError("Choose a PNG or JPEG worksheet picture.")
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in ("PNG", "JPEG"):
                raise ValueError("Use a PNG or JPEG picture.")
            if getattr(source, "n_frames", 1) != 1:
                raise ValueError("Use one still PNG or JPEG picture, rather than an animation.")
            if min(source.size) < 40:
                raise ValueError("This picture is too small. Use a clearer picture of one complete question.")
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("This picture is too large. Crop it to one question first.")
            source.verify()
        with Image.open(BytesIO(raw)) as source:
            oriented = ImageOps.exif_transpose(source)
            if oriented.width * oriented.height > MAX_IMAGE_PIXELS:
                raise ValueError("This picture is too large. Crop it to one question first.")
            rgba = oriented.convert("RGBA")
            result = Image.new("RGB", rgba.size, "white")
            result.paste(rgba, mask=rgba.getchannel("A"))
            output = BytesIO()
            result.save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
        raise ValueError("This picture could not be opened. Choose a clear PNG or JPEG.") from exc


def _public_review(value):
    """Return just teaching content, never source files or internal model output."""
    if not isinstance(value, dict):
        raise ValueError("The worksheet reader did not return a review.")
    allowed = ("question", "type", "a", "b", "answer", "shape", "object_label", "object_label_plural", "warnings", "reader")
    result = {key: value[key] for key in allowed if key in value}
    # Rendering controls and any sprite paths stay in the saved pipeline plan.
    steps = value.get("steps", [])
    result["steps"] = [{"text": step["text"]} if isinstance(step, dict) else {"text": step}
                       for step in steps if isinstance(step, str) or
                       (isinstance(step, dict) and isinstance(step.get("text"), str))]
    result["narration"] = [step["text"] for step in result["steps"]]
    if not isinstance(result.get("question"), str) or not result["question"].strip():
        raise ValueError("The worksheet reader did not return a question.")
    # Reject custom pipeline mistakes before persisting public data.
    json.dumps(result, allow_nan=False)
    return result


class JobManager:
    def __init__(self, store, pipeline):
        self.store = store
        self.pipeline = pipeline
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lesson-generator")
        self.closed = False
        self._lock = threading.Lock()

    def submit(self, function, job_id):
        with self._lock:
            if self.closed:
                raise RuntimeError("The lesson server is stopping.")
            return self.executor.submit(function, job_id)

    def shutdown(self, wait=True):
        with self._lock:
            self.closed = True
        self.executor.shutdown(wait=wait, cancel_futures=True)

    def analyze(self, job_id):
        if not self.store.transition(job_id, "queued_read", "reading"):
            return
        try:
            job = self.store.get(job_id)
            directory = self.store.job_dir(job_id)
            review = _public_review(self.pipeline.analyze(directory / "worksheet.png", directory, job["character"]))
            # A durable snapshot is written before the confirmable state appears.
            temporary = directory / "review.json.tmp"
            temporary.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
            temporary.replace(directory / "review.json")
            self.store.transition(job_id, "reading", "awaiting_review", review=review)
        except Exception:
            LOG.exception("Worksheet reading failed for job %s", job_id)
            self.store.transition(job_id, "reading", "failed",
                                  error="The worksheet could not be read. Try a clear picture of one complete, supported math question.")

    def render(self, job_id):
        if not self.store.transition(job_id, "queued", "rendering"):
            return
        try:
            job = self.store.get(job_id)
            directory = self.store.job_dir(job_id)
            self.pipeline.render(directory, job["character"])
            if not (directory / "lesson.mp4").is_file():
                raise RuntimeError("The renderer did not save a video.")
            self.store.transition(job_id, "rendering", "completed")
        except Exception:
            LOG.exception("Video generation failed for job %s", job_id)
            self.store.transition(job_id, "rendering", "failed",
                                  error="The lesson video could not be created. Check the server setup, then upload the picture again to retry.")


def create_app(storage_dir=None, pipeline=None):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES, JSON_SORT_KEYS=False)
    if pipeline is None:
        from .web_pipeline import LessonPipeline
        pipeline = LessonPipeline()
    store = JobStore(storage_dir or Path("output") / "web_jobs")
    store.recover_interrupted()
    manager = JobManager(store, pipeline)
    app.extensions["lesson_jobs"] = manager
    app.extensions["lesson_store"] = store

    def authorized_job(job_id):
        if not JOB_PATTERN.fullmatch(job_id):
            return None
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header[7:]
        if not token or len(token) > 128 or not token.isascii():
            return None
        return store.get(job_id, token)

    def public_job(job, include_token=False):
        job_id = job["id"]
        value = {"job_id": job_id, "status": job["status"], "character": job["character"],
                 "review": job["review"], "error": job["error"],
                 "created_at": job["created_at"], "updated_at": job["updated_at"],
                 "urls": {kind: f"/api/jobs/{job_id}/{kind}" for kind in ("input", "poster", "video")}}
        if include_token:
            value["access_token"] = job["access_token"]
        return value

    @app.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(HTTPException)
    def http_error(exc):
        messages = {413: "This upload is too large. Use a PNG or JPEG smaller than 10 MB.",
                    404: "This lesson was not found.", 405: "This request method is not supported.",
                    400: "This request could not be read."}
        return jsonify(error=messages.get(exc.code, "The request could not be completed.")), exc.code

    @app.errorhandler(Exception)
    def unexpected_error(exc):
        LOG.exception("The local lesson API could not complete a request")
        return jsonify(error="The server could not complete this request."), 500

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", mode="local-prototype")

    @app.post("/api/jobs")
    def create_job():
        # Reject unexpected control fields; web input cannot select models/paths/commands.
        if (set(request.form) - {"character", "client_request_id"} or set(request.files) != {"worksheet"}
                or any(len(request.form.getlist(key)) != 1 for key in request.form)
                or len(request.files.getlist("worksheet")) != 1):
            return jsonify(error="Upload one image with character settings and a request ID."), 400
        nonce = request.form.get("client_request_id", "")
        if not NONCE_PATTERN.fullmatch(nonce):
            return jsonify(error="Provide a fresh upload request ID."), 400
        try:
            character = validate_character(json.loads(request.form.get("character", "{}")))
            image_bytes = _normalized_upload(request.files["worksheet"].read(MAX_UPLOAD_BYTES + 1))
        except (ValueError, TypeError) as exc:
            # Validator/image decoder errors are bounded, user-directed messages.
            message = str(exc) if not isinstance(exc, json.JSONDecodeError) else "Character settings must be valid JSON."
            return jsonify(error=message), 400
        fingerprint = hashlib.sha256(image_bytes + b"\0" + json.dumps(character, sort_keys=True).encode()).hexdigest()
        try:
            job, created = store.create(nonce, fingerprint, character)
        except RequestConflict as exc:
            return jsonify(error=str(exc)), 409
        if created:
            directory = store.job_dir(job["id"])
            try:
                directory.mkdir(mode=0o700)
                (directory / "worksheet.png").write_bytes(image_bytes)
                manager.submit(manager.analyze, job["id"])
            except Exception:
                store.transition(job["id"], "queued_read", "failed",
                                 error="The server could not save this upload. Please try again.")
                raise
        return jsonify(public_job(store.get(job["id"]), include_token=True)), 202 if created else 200

    @app.get("/api/jobs/<job_id>")
    def get_job(job_id):
        job = authorized_job(job_id)
        if job is None:
            return jsonify(error="This lesson was not found."), 404
        return jsonify(public_job(job))

    @app.post("/api/jobs/<job_id>/generate")
    def generate_job(job_id):
        job = authorized_job(job_id)
        if job is None:
            return jsonify(error="This lesson was not found."), 404
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {"confirmed"} or body.get("confirmed") is not True:
            return jsonify(error="Confirm the displayed question and explanation before generating."), 400
        if store.transition(job_id, "awaiting_review", "queued"):
            try:
                manager.submit(manager.render, job_id)
            except Exception:
                store.transition(job_id, "queued", "failed", error="The lesson server stopped. Restart it and upload again.")
                raise
        else:
            job = store.get(job_id)
            if job["status"] not in ("queued", "rendering", "completed"):
                return jsonify(error="This lesson is not ready to generate. Wait for its reading or upload again."), 409
        return jsonify(public_job(store.get(job_id))), 202

    def job_file(job_id, kind):
        job = authorized_job(job_id)
        if job is None:
            return jsonify(error="This lesson was not found."), 404
        if kind != "input" and job["status"] != "completed":
            return jsonify(error="This lesson file is not ready."), 404
        filename, mimetype = {"input": ("worksheet.png", "image/png"),
                              "poster": ("poster.png", "image/png"),
                              "video": ("lesson.mp4", "video/mp4")}[kind]
        path = store.job_dir(job_id) / filename
        if not path.is_file():
            return jsonify(error="This lesson file is not available."), 404
        return send_file(path, mimetype=mimetype, conditional=True, download_name=filename)

    @app.get("/api/jobs/<job_id>/input")
    def input_file(job_id):
        return job_file(job_id, "input")

    @app.get("/api/jobs/<job_id>/poster")
    def poster_file(job_id):
        return job_file(job_id, "poster")

    @app.get("/api/jobs/<job_id>/video")
    def video_file(job_id):
        return job_file(job_id, "video")

    return app


def main():
    parser = argparse.ArgumentParser(description="Run the local lesson review/generation API.")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--storage", "--storage-dir", dest="storage", type=Path, default=Path("output/web_jobs"))
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port between 1024 and 65535.")
    app = create_app(storage_dir=args.storage)
    try:
        app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)
    finally:
        app.extensions["lesson_jobs"].shutdown()


if __name__ == "__main__":
    main()
