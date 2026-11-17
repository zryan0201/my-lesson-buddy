"""Offline contract checks. Real-model development examples are separate evidence."""
import base64
from io import BytesIO
import json
from pathlib import Path
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw
from lesson_video.cartoon_makeover import (CartoonRuntime, CartoonError, CartoonCancelled,
    validate_options, prepare_reference, preserve_palette, palette_colors, fidelity_checks, model_status, finish_cartoon)
from lesson_video.cartoon_web import create_app


def drawing():
    im = Image.new('RGB', (200, 260), 'white'); draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((45, 15, 155, 120), radius=10, fill='#78c8be', outline='#344058', width=5)
    draw.rectangle((65, 135, 135, 200), fill='#a494df', outline='#344058', width=5)
    draw.line((70, 200, 65, 245), fill='#344058', width=5); draw.line((130, 200, 135, 245), fill='#344058', width=5)
    buf = BytesIO(); im.save(buf, format='PNG'); return buf.getvalue()


class CartoonCoreTests(unittest.TestCase):
    def test_options_are_bounded_and_do_not_accept_hidden_model_settings(self):
        self.assertEqual(validate_options().style, 'soft3d')
        for value in [{'unknown': 3}, {'seed': True}, {'seed': -1}, {'style': []}, {'strength': {}},
                      {'idea': 'person@example.com'}, {'idea': 'x'*241}, {'idea': 'a nude person'}]:
            with self.subTest(value=value), self.assertRaises(CartoonError): validate_options(value)

    def test_reference_and_edge_guides_are_derived_without_mutating_the_source(self):
        raw = drawing(); old = bytes(raw); reference, edges = prepare_reference(raw)
        self.assertEqual(reference.size, (384, 512)); self.assertEqual(edges.size, reference.size)
        self.assertEqual(raw, old); self.assertTrue(palette_colors(reference))

    def test_palette_alignment_uses_source_colors_and_keeps_white(self):
        reference, _ = prepare_reference(drawing())
        candidate = reference.copy(); aligned = preserve_palette(candidate, reference)
        self.assertEqual(aligned.getpixel((0, 0)), (255, 255, 255)); self.assertEqual(aligned.size, reference.size)
        self.assertLessEqual(len(palette_colors(aligned)), 6)

    def test_fidelity_checks_reject_empty_output_and_border_filling(self):
        reference, _ = prepare_reference(drawing())
        self.assertTrue(fidelity_checks(reference, reference)['passed'])
        self.assertFalse(fidelity_checks(reference, Image.new('RGB', reference.size, 'white'))['passed'])
        self.assertFalse(fidelity_checks(reference, Image.new('RGB', reference.size, 'black'))['passed'])

    def test_missing_cache_does_not_trigger_a_download(self):
        with patch('lesson_video.cartoon_makeover.DEFAULT_CACHE', Path('/tmp/no-cartoon-model')):
            self.assertFalse(model_status(Path('/tmp/no-cartoon-model'))['ready'])

    def test_cartoon_cutout_keeps_enclosed_white_details_and_a_transparent_border(self):
        im=Image.new('RGB',(100,140),'white');draw=ImageDraw.Draw(im)
        draw.rectangle((25,20,75,120),fill='white',outline='#334455',width=4)
        out=finish_cartoon(im)
        self.assertEqual(out.size,(600,800));self.assertEqual(out.getpixel((0,0))[3],0)
        self.assertGreater(out.getpixel((300,400))[3],240)

    def test_safety_rejection_and_cancellation_never_return_an_image(self):
        runtime = CartoonRuntime(); image, _ = prepare_reference(drawing())
        class Tokenizer:
            def __call__(self, *args, **kwargs): return SimpleNamespace(input_ids=[])
            def decode(self, ids): return 'a friendly robot'
        class Pipe:
            tokenizer = Tokenizer()
            def __call__(self, **kwargs): return SimpleNamespace(images=[image], nsfw_content_detected=[True])
        runtime.pipe = Pipe(); runtime.device = 'cpu'
        with self.assertRaisesRegex(CartoonError, 'safety check'): runtime.generate(drawing())
        with self.assertRaises(CartoonCancelled): runtime.generate(drawing(), cancelled=lambda: True)
        self.assertFalse(runtime.lock.locked())


class FakeRuntime:
    def __init__(self, block=False): self.started = threading.Event(); self.release = threading.Event(); self.block = block
    def generate(self, raw, options, *, progress, cancelled):
        self.started.set(); progress('generating', 50)
        if self.block: self.release.wait(3)
        if cancelled(): raise CartoonCancelled('Cancelled')
        image, _ = prepare_reference(raw)
        return image, {'safety_checker_passed': True, 'checks': {'passed': True}}


class CartoonWebTests(unittest.TestCase):
    def setUp(self):
        self.runtime = FakeRuntime(); self.app = create_app(self.runtime); self.client = self.app.test_client()
        self.headers = {'X-Lesson-Buddy-Local': '1'}
        self.payload = {'image': 'data:image/png;base64,'+base64.b64encode(drawing()).decode(), 'options': {}}
    def submit(self):
        response = self.client.post('/api/cartoon/jobs', json=self.payload, headers=self.headers)
        self.assertEqual(response.status_code, 202); return response.get_json()
    def ready(self, job):
        headers = {'Authorization': 'Bearer '+job['token']}
        for _ in range(100):
            r = self.client.get('/api/cartoon/jobs/'+job['id'], headers=headers).get_json()
            if r['state'] not in ('queued', 'running'): return r, headers
            time.sleep(.01)
        self.fail('Fake job did not finish')

    def test_local_host_origin_and_custom_header_boundaries(self):
        self.assertEqual(self.client.get('/api/cartoon/status', headers={'Host':'evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/cartoon/jobs', json=self.payload).status_code, 403)
        self.assertEqual(self.client.post('/api/cartoon/jobs', json=self.payload, headers={**self.headers,'Origin':'https://evil.example'}).status_code, 403)
        response = self.client.get('/api/cartoon/status'); self.assertNotIn('Access-Control-Allow-Origin', response.headers)

    def test_job_tokens_protect_status_and_result_and_source_hash_is_retained(self):
        job = self.submit(); result, headers = self.ready(job)
        self.assertEqual(result['state'], 'ready'); self.assertEqual(result['source_sha256'], job['source_sha256'])
        self.assertEqual(self.client.get('/api/cartoon/jobs/'+job['id']).status_code, 404)
        image = self.client.get('/api/cartoon/jobs/'+job['id']+'/image', headers=headers)
        self.assertEqual(image.status_code, 200); self.assertEqual(image.mimetype, 'image/png')
        self.assertEqual(Image.open(BytesIO(image.data)).size, (600, 800)); self.assertNotIn('token', result)

    def test_one_job_and_cancellation_preserve_no_late_result(self):
        self.runtime.block = True; job = self.submit(); self.runtime.started.wait(1)
        self.assertEqual(self.client.post('/api/cartoon/jobs', json=self.payload, headers=self.headers).status_code, 409)
        headers = {**self.headers, 'Authorization':'Bearer '+job['token']}
        self.assertEqual(self.client.delete('/api/cartoon/jobs/'+job['id'], headers=headers).status_code, 200)
        self.runtime.release.set(); result, _ = self.ready(job)
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(self.client.get('/api/cartoon/jobs/'+job['id']+'/image', headers=headers).status_code, 404)

    def test_remote_or_executable_sources_and_extra_options_are_rejected(self):
        for image in ['https://example.com/drawing.png', 'data:image/svg+xml;base64,abc', 'data:image/png;base64,!!!']:
            with self.subTest(image=image):
                r=self.client.post('/api/cartoon/jobs',json={**self.payload,'image':image},headers=self.headers)
                self.assertEqual(r.status_code,400)
        self.assertEqual(self.client.post('/api/cartoon/jobs',json={**self.payload,'options':{'model':'evil'}},headers=self.headers).status_code,400)


if __name__ == '__main__': unittest.main()
