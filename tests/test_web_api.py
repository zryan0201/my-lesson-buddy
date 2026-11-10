"""API lifecycle and capability tests, with no speech/model/encoding calls."""

from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest

from PIL import Image

from lesson_video.web_api import MAX_UPLOAD_BYTES, create_app


def picture(color="orange", mode="RGB", format="PNG"):
    result = BytesIO()
    Image.new(mode, (90, 50), color).save(result, format=format)
    return result.getvalue()


class SavedPlanPipeline:
    def __init__(self):
        self.analyze_calls = 0
        self.render_calls = 0
        self.started = threading.Event()
        self.release = None
        self.fail = False
        self.rendered_plan = None

    def analyze(self, image_path, job_dir, character):
        self.analyze_calls += 1
        with Image.open(image_path) as image:
            assert image.format == "PNG"
            assert image.mode == "RGB"
        if self.fail:
            raise RuntimeError("Private model path /private/internal/model is unavailable.")
        review = {"question": "What is 5 + 2?", "type": "addition", "a": 5, "b": 2,
                  "answer": 7, "steps": [{"text": "Count five pictures."}, {"text": "Five plus two equals seven."}],
                  "object_images": ["/private/internal/sprite.png"], "reader": "stub"}
        (job_dir / "lesson.json").write_text(json.dumps(review))
        return review

    def render(self, job_dir, character):
        self.render_calls += 1
        self.started.set()
        if self.release:
            if not self.release.wait(timeout=5):
                raise RuntimeError("Test rendering barrier timed out.")
        self.rendered_plan = json.loads((job_dir / "lesson.json").read_text())
        (job_dir / "lesson.mp4").write_bytes(b"test-video")
        Image.new("RGB", (8, 8), "blue").save(job_dir / "poster.png")
        return {"video": str(job_dir / "lesson.mp4")}


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.pipeline = SavedPlanPipeline()
        self.app = create_app(self.temp.name, self.pipeline)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.apps = [self.app]

    def tearDown(self):
        if self.pipeline.release:
            self.pipeline.release.set()
        for app in self.apps:
            app.extensions["lesson_jobs"].shutdown()
        self.temp.cleanup()

    def drain(self, app=None):
        (app or self.app).extensions["lesson_jobs"].executor.submit(lambda: None).result(timeout=5)

    def upload(self, nonce="a_fresh_request_1234", raw=None, character=None, **other):
        data = {"worksheet": (BytesIO(picture() if raw is None else raw), "../../ignored.png"),
                "client_request_id": nonce, "character": json.dumps(character or {}), **other}
        return self.client.post("/api/jobs", data=data)

    @staticmethod
    def headers(job):
        return {"Authorization": "Bearer " + job["access_token"]}

    def get(self, job):
        return self.client.get("/api/jobs/" + job["job_id"], headers=self.headers(job))

    def generate(self, job, body=None):
        return self.client.post("/api/jobs/" + job["job_id"] + "/generate",
                                headers=self.headers(job), json={"confirmed": True} if body is None else body)

    def test_review_gate_preserves_reading_and_plan(self):
        response = self.upload()
        self.assertEqual(response.status_code, 202)
        job = response.get_json()
        self.drain()
        reviewed = self.get(job).get_json()
        self.assertEqual(reviewed["status"], "awaiting_review")
        self.assertEqual(reviewed["review"]["answer"], 7)
        self.assertEqual(reviewed["review"]["narration"][0], "Count five pictures.")
        self.assertNotIn("object_images", reviewed["review"])
        self.assertNotIn("access_token", reviewed)
        self.assertNotIn("/private", json.dumps(reviewed))
        self.assertEqual(self.pipeline.render_calls, 0)
        self.assertEqual(self.generate(job, {"confirmed": False}).status_code, 400)
        self.assertEqual(self.generate(job, {"confirmed": "true"}).status_code, 400)
        self.assertEqual(self.generate(job, {"confirmed": True, "a": 9}).status_code, 400)
        self.assertEqual(self.generate(job).status_code, 202)
        self.drain()
        self.assertEqual(self.get(job).get_json()["status"], "completed")
        self.assertEqual(self.pipeline.analyze_calls, 1)
        self.assertEqual(self.pipeline.rendered_plan["answer"], 7)
        video = self.client.get(job["urls"]["video"], headers=self.headers(job))
        self.assertEqual(video.data, b"test-video")
        self.assertEqual(video.headers["Cache-Control"], "no-store")
        video.close()

    def test_job_capabilities_isolate_images_and_all_routes(self):
        first = self.upload().get_json()
        second = self.upload(nonce="another_request_5678").get_json()
        self.drain()
        base = "/api/jobs/" + first["job_id"]
        for suffix in ("", "/input", "/poster", "/video"):
            self.assertEqual(self.client.get(base + suffix).status_code, 404)
            self.assertEqual(self.client.get(base + suffix, headers=self.headers(second)).status_code, 404)
        self.assertEqual(self.client.post(base + "/generate", json={"confirmed": True},
                                         headers=self.headers(second)).status_code, 404)
        image_response = self.client.get(first["urls"]["input"], headers=self.headers(first))
        self.assertEqual(image_response.status_code, 200)
        image_response.close()
        self.assertEqual(self.client.get(base, headers={"Authorization": "Bearer é"}).status_code, 404)
        self.assertEqual(self.client.get(first["urls"]["video"], headers=self.headers(first)).status_code, 404)
        self.assertNotIn("Access-Control-Allow-Origin", self.get(first).headers)

    def test_duplicate_uploads_are_idempotent_and_changed_payload_conflicts(self):
        first = self.upload().get_json()
        duplicate = self.upload()
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(first["job_id"], duplicate.get_json()["job_id"])
        self.assertEqual(first["access_token"], duplicate.get_json()["access_token"])
        self.assertEqual(self.upload(raw=picture("red")).status_code, 409)
        self.assertEqual(self.upload(character={"kind": "fox"}).status_code, 409)
        self.drain()
        self.assertEqual(self.pipeline.analyze_calls, 1)

    def test_repeated_generate_clicks_queue_only_one_render(self):
        job = self.upload().get_json()
        self.drain()
        self.pipeline.release = threading.Event()
        self.assertEqual(self.generate(job).status_code, 202)
        self.assertTrue(self.pipeline.started.wait(timeout=5))
        self.assertEqual(self.generate(job).status_code, 202)
        self.assertEqual(self.generate(job).status_code, 202)
        self.pipeline.release.set()
        self.drain()
        self.assertEqual(self.generate(job).status_code, 202)
        self.drain()
        self.assertEqual(self.pipeline.render_calls, 1)
        self.assertEqual(self.pipeline.analyze_calls, 1)

    def test_browser_or_server_restart_keeps_review_and_confirmed_inputs(self):
        job = self.upload().get_json()
        self.drain()
        self.app.extensions["lesson_jobs"].shutdown()
        replacement = SavedPlanPipeline()
        next_app = create_app(self.temp.name, replacement)
        self.apps.append(next_app)
        client = next_app.test_client()
        response = client.get("/api/jobs/" + job["job_id"], headers=self.headers(job))
        self.assertEqual(response.get_json()["status"], "awaiting_review")
        client.post("/api/jobs/" + job["job_id"] + "/generate", headers=self.headers(job), json={"confirmed": True})
        self.drain(next_app)
        self.assertEqual(replacement.analyze_calls, 0)
        self.assertEqual(replacement.rendered_plan["a"], 5)
        self.assertEqual(replacement.rendered_plan["answer"], 7)

    def test_interrupted_work_becomes_actionable_failed_job(self):
        self.app.extensions["lesson_jobs"].shutdown()
        store = self.app.extensions["lesson_store"]
        job, _ = store.create("restart_request_1234", "hash", {})
        next_app = create_app(self.temp.name, SavedPlanPipeline())
        self.apps.append(next_app)
        recovered = next_app.extensions["lesson_store"].get(job["id"])
        self.assertEqual(recovered["status"], "failed")
        self.assertIn("restarted", recovered["error"])

    def test_invalid_uploads_do_not_reach_model(self):
        for raw in (b"not an image", picture(format="GIF"), b""):
            with self.subTest(raw=raw[:10]):
                self.assertEqual(self.upload(raw=raw).status_code, 400)
        self.assertEqual(self.upload(character={"kind": "dinosaur"}).status_code, 400)
        self.assertEqual(self.upload(character={"model_path": "/tmp/custom"}).status_code, 400)
        self.assertEqual(self.upload(nonce="short").status_code, 400)
        self.assertEqual(self.upload(vision_model="/tmp/custom").status_code, 400)
        self.assertEqual(self.pipeline.analyze_calls, 0)

    def test_upload_size_and_pixel_limits(self):
        self.app.config["MAX_CONTENT_LENGTH"] = 300
        self.assertEqual(self.upload(raw=b"x" * 400).status_code, 413)
        self.app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
        import unittest.mock
        with unittest.mock.patch("lesson_video.web_api.MAX_IMAGE_PIXELS", 200):
            self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(self.pipeline.analyze_calls, 0)

    def test_animated_and_tiny_pictures_are_rejected_before_model(self):
        animation = BytesIO()
        first = Image.new("RGB", (80, 80), "red")
        second = Image.new("RGB", (80, 80), "blue")
        first.save(animation, format="PNG", save_all=True, append_images=[second], duration=100, loop=0)
        self.assertEqual(self.upload(raw=animation.getvalue()).status_code, 400)
        tiny = BytesIO()
        Image.new("RGB", (20, 20), "white").save(tiny, format="PNG")
        self.assertEqual(self.upload(raw=tiny.getvalue()).status_code, 400)
        self.assertEqual(self.pipeline.analyze_calls, 0)

    def test_duplicate_multipart_controls_are_rejected(self):
        from werkzeug.datastructures import MultiDict
        duplicate_files = MultiDict([
            ("worksheet", (BytesIO(picture()), "one.png")),
            ("worksheet", (BytesIO(picture()), "two.png")),
            ("client_request_id", "duplicate_files_1234"),
        ])
        self.assertEqual(self.client.post("/api/jobs", data=duplicate_files).status_code, 400)
        duplicate_fields = MultiDict([
            ("worksheet", (BytesIO(picture()), "one.png")),
            ("client_request_id", "duplicate_fields_1234"),
            ("character", "{}"), ("character", '{"kind":"fox"}'),
        ])
        self.assertEqual(self.client.post("/api/jobs", data=duplicate_fields).status_code, 400)
        self.assertEqual(self.pipeline.analyze_calls, 0)

    def test_transparency_is_flattened_and_filename_never_used(self):
        job = self.upload(raw=picture((255, 0, 0, 0), mode="RGBA")).get_json()
        self.drain()
        directory = self.app.extensions["lesson_store"].job_dir(job["job_id"])
        with Image.open(directory / "worksheet.png") as image:
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
        self.assertFalse((Path(self.temp.name) / "ignored.png").exists())

    def test_pipeline_failure_does_not_expose_trace_or_paths(self):
        self.pipeline.fail = True
        with self.assertLogs("lesson_video.web_api", level="ERROR"):
            job = self.upload().get_json()
            self.drain()
        result = self.get(job).get_json()
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("/private", json.dumps(result))
        self.assertNotIn("Traceback", json.dumps(result))
        self.assertEqual(self.generate(job).status_code, 409)


if __name__ == "__main__":
    unittest.main()
