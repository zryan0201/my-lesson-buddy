"""The character module works offline and never sends AI requests by accident."""
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image, ImageDraw

from character_studio.app import create_app
from character_studio import assets
from character_studio.images import normalize_image, png_bytes, polish_drawing


def sketch():
    image=Image.new('RGB',(360,480),'white')
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((95,40,265,200),radius=30,fill='#74C7BE',outline='#26334B',width=7)
    draw.ellipse((130,95,153,124),fill='white',outline='black',width=3)
    draw.ellipse((205,95,228,124),fill='white',outline='black',width=3)
    draw.arc((154,125,205,170),0,180,fill='black',width=4)
    draw.rectangle((120,220,240,355),fill='#A99AE7',outline='#26334B',width=7)
    for start,end in [((115,230),(60,310)),((245,230),(300,310)),((145,355),(135,430)),((215,355),(225,430))]:
        draw.line((start,end),fill='#26334B',width=11)
    return png_bytes(image)


class ImageTests(unittest.TestCase):
    def test_paper_is_removed_but_enclosed_white_eyes_remain(self):
        result=normalize_image(sketch())
        self.assertEqual(result.size,(600,800))
        self.assertEqual(result.getpixel((0,0))[3],0)
        self.assertTrue(any(r>245 and g>245 and b>245 and a>245 for r,g,b,a in result.getdata()))

    def test_blank_and_invalid_drawing_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_image(png_bytes(Image.new('RGB',(100,100),'white')))
        with self.assertRaises(ValueError):
            normalize_image(b'not a drawing')

    def test_polish_preserves_nonempty_transparent_sticker(self):
        result=polish_drawing(sketch())
        self.assertEqual(result.mode,'RGBA')
        self.assertEqual(result.getpixel((0,0))[3],0)
        self.assertIsNotNone(result.getbbox())


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)

    def test_each_save_is_an_immutable_character(self):
        first=assets.save_character('小熊 7','drawing',image=sketch(),root=self.root)
        second=assets.save_character('小熊 7','drawing',image=sketch(),root=self.root)
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(len(assets.list_characters(self.root)),2)
        self.assertEqual(assets.load_character_image(first['id'],self.root).size,(600,800))
        self.assertNotIn(str(self.root),json.dumps(first))

    def test_package_contains_only_portable_data(self):
        item=assets.save_character('Nova','builder',design={'headwear':'helmet','back':'wings'},root=self.root)
        with zipfile.ZipFile(BytesIO(assets.export_character(item['id'],self.root))) as archive:
            self.assertEqual(set(archive.namelist()),{'character.json','character.png','README.txt'})
            self.assertEqual(json.loads(archive.read('character.json'))['name'],'Nova')
            self.assertTrue(archive.read('character.png').startswith(b'\x89PNG'))

    def test_tampering_and_path_ids_are_rejected(self):
        item=assets.save_character('Buddy','drawing',image=sketch(),root=self.root)
        (assets.character_dir(item['id'],self.root)/'image.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            assets.get_character(item['id'],self.root)
        self.assertEqual(assets.list_characters(self.root),[])
        with self.assertRaises(ValueError):
            assets.get_character('../../private',self.root)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.app=create_app(self.temporary.name)
        self.client=self.app.test_client()

    def save_drawing(self):
        return self.client.post('/api/characters',data={'name':'Doodle','source':'drawing',
                                   'image':(BytesIO(sketch()),'my-picture.png')})

    def test_builder_save_library_and_exports(self):
        response=self.client.post('/api/characters',data={'name':'Nova','source':'builder',
                                   'design':json.dumps({'headwear':'web_mask','chest':'reactor','back':'wings'})})
        self.assertEqual(response.status_code,201,response.json)
        item=response.json
        self.assertEqual(self.client.get('/api/characters').json['characters'][0]['id'],item['id'])
        image=self.client.get(item['urls']['image'])
        self.assertEqual(image.mimetype,'image/png')
        self.assertEqual(image.headers['Cache-Control'],'no-store')
        self.assertEqual(self.client.get(item['urls']['package']).mimetype,'application/zip')

    def test_drawing_save_and_polish_are_offline(self):
        with patch('requests.post',side_effect=AssertionError('No API call expected')):
            self.assertEqual(self.save_drawing().status_code,201)
            result=self.client.post('/api/polish',data={'image':(BytesIO(sketch()),'drawing.png')})
            self.assertEqual(result.mimetype,'image/png')

    def test_foreign_origin_and_dns_rebinding_host_are_rejected(self):
        result=self.client.post('/api/preview',json={},headers={'Origin':'https://other.example'})
        self.assertEqual(result.status_code,403)
        self.assertEqual(self.client.get('/api/characters',headers={'Host':'other.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/preview',json={},headers={'Origin':'http://localhost'}).status_code,200)

    def test_bad_upload_and_unknown_design_cannot_save(self):
        self.assertEqual(self.client.post('/api/characters',data={'name':'Bad','source':'drawing',
                               'image':(BytesIO(b'bad bytes'),'bad.png')}).status_code,400)
        self.assertEqual(self.client.post('/api/preview',json={'path':'/tmp/nope'}).status_code,400)
        self.assertEqual(self.client.get('/api/characters').json['characters'],[])

    def test_gemini_requires_enable_flags_and_adult_confirmation(self):
        with patch.dict(os.environ,{},clear=True),patch('requests.post',side_effect=AssertionError('No API call expected')):
            self.assertFalse(self.client.get('/api/ai-status').json['enabled'])
            missing=self.client.post('/api/beautify',data={'image':(BytesIO(sketch()),'drawing.png')})
            self.assertEqual(missing.status_code,400)
            disabled=self.client.post('/api/beautify',data={'confirmed':'true','image':(BytesIO(sketch()),'drawing.png')})
            self.assertEqual(disabled.status_code,503)

    def test_confirmed_makeover_returns_preview_without_saving_or_replacing_drawing(self):
        with patch('character_studio.gemini_makeover.status',return_value={'enabled':True}), \
             patch('character_studio.gemini_makeover.beautify',return_value=normalize_image(sketch())) as fake:
            result=self.client.post('/api/beautify',data={'confirmed':'true','style':'comic',
                                  'image':(BytesIO(sketch()),'drawing.png')})
            self.assertEqual(result.mimetype,'image/png')
            self.assertEqual(fake.call_args.args[1],'comic')
            self.assertEqual(self.client.get('/api/characters').json['characters'],[])


class GeminiMakeoverTests(unittest.TestCase):
    def test_actual_adapter_decodes_only_final_image_and_does_not_save(self):
        import base64
        from character_studio.gemini_makeover import beautify
        response={'status':'completed','steps':[{'type':'thought','content':[]},
                  {'type':'model_output','content':[{'type':'image','mime_type':'image/png',
                    'data':base64.b64encode(sketch()).decode('ascii')}]}]}
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test-only','GEMINI_ENABLED':'1','GEMINI_IMAGE_ENABLED':'1'}), \
             patch('character_studio.gemini_makeover.request_interaction',return_value=response) as request:
            result=beautify(sketch(),'comic')
        self.assertEqual(result.size,(600,800))
        request.assert_called_once()
        self.assertEqual(request.call_args.kwargs['response_format']['type'],'image')

    def test_text_refusal_and_incomplete_generation_cannot_replace_original(self):
        from character_studio.gemini_makeover import beautify
        from lesson_video.gemini_client import GeminiError
        for response in [{'status':'in_progress','steps':[]},
                         {'status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':'No image.'}]}]}]:
            with patch.dict(os.environ,{'GEMINI_API_KEY':'test-only','GEMINI_ENABLED':'1','GEMINI_IMAGE_ENABLED':'1'}), \
                 patch('character_studio.gemini_makeover.request_interaction',return_value=response):
                with self.assertRaises(GeminiError):
                    beautify(sketch())


if __name__=='__main__':
    unittest.main()
