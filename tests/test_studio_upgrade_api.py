"""Round-trip and handoff behavior across the independent studio and lessons."""
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from character_studio.app import create_app
from character_studio.assets import save_character

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest=None


class StudioUpgradeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.client=create_app(self.root/'first').test_client()
        response=self.client.post('/api/characters',data={'name':'Webwing','source':'builder',
                 'design':json.dumps({'headwear':'web_mask','back':'wings','chest':'reactor'})})
        self.assertEqual(response.status_code,201)
        self.saved=response.json

    def test_export_import_reopens_the_original_parts_and_keeps_exact_artwork(self):
        package=self.client.get(self.saved['urls']['package']).data
        other=create_app(self.root/'second').test_client()
        result=other.post('/api/import',data={'package':(BytesIO(package),'saved.character.zip')})
        self.assertEqual(result.status_code,201,result.json)
        imported=result.json
        self.assertNotEqual(imported['id'],self.saved['id'])
        self.assertEqual(other.get(imported['urls']['image']).data,self.client.get(self.saved['urls']['image']).data)
        project=other.get(f'/api/characters/{imported["id"]}/project').json
        self.assertEqual(project['design']['headwear'],'web_mask')
        self.assertEqual(project['design']['back'],'wings')
        self.assertNotIn(str(self.root),json.dumps(project))

    def test_duplicate_renames_new_copy_and_leaves_saved_source_unchanged(self):
        result=self.client.post(f'/api/characters/{self.saved["id"]}/duplicate',json={'name':'Twin Nova'})
        self.assertEqual(result.status_code,201,result.json)
        duplicate=result.json
        self.assertNotEqual(duplicate['id'],self.saved['id'])
        self.assertEqual(duplicate['name'],'Twin Nova')
        project=self.client.get(f'/api/characters/{duplicate["id"]}/project').json
        self.assertEqual(project['design']['name'],'Twin Nova')
        self.assertEqual(self.client.get(f'/api/characters/{self.saved["id"]}/project').json['character']['name'],'Webwing')

    def test_import_and_duplicate_reject_wrong_requests_without_creating_entries(self):
        self.assertEqual(self.client.post('/api/import',data={'image':(BytesIO(b'bad'),'x.zip')}).status_code,400)
        self.assertEqual(self.client.post('/api/import',data={'package':(BytesIO(b'bad'),'x.zip')}).status_code,400)
        self.assertEqual(self.client.post(f'/api/characters/{self.saved["id"]}/duplicate',json={'path':'/tmp/x'}).status_code,400)
        self.assertEqual(len(self.client.get('/api/characters').json['characters']),1)

    def test_motion_is_an_offline_preview_and_never_saves_or_calls_ai(self):
        with patch('requests.post',side_effect=AssertionError('No AI calls in a motion preview')):
            response=self.client.get(f'/api/characters/{self.saved["id"]}/motion?motion=wave')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.mimetype,'image/gif')
        with Image.open(BytesIO(response.data)) as image:
            self.assertGreater(image.n_frames,1)
            self.assertEqual(image.size,(300,400))
        self.assertEqual(len(self.client.get('/api/characters').json['characters']),1)
        self.assertEqual(self.client.get(f'/api/characters/{self.saved["id"]}/motion?motion=unsupported').status_code,400)
        self.assertEqual(self.client.get(f'/api/characters/{self.saved["id"]}/motion?motion=wave&motion=talk').status_code,400)


@unittest.skipIf(AppTest is None,'Install web requirements for the lesson screen checks.')
class StudioHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        environment=patch.dict(os.environ,{'CHARACTER_STUDIO_STORAGE':str(Path(self.temp.name)/'library')})
        environment.start(); self.addCleanup(environment.stop)
        self.saved=save_character('Link Buddy','builder',design={'back':'wings'})
        self.patcher=patch('lesson_video.web_client.LessonApiClient')
        self.client=self.patcher.start().return_value
        self.addCleanup(self.patcher.stop)
        self.client.get_job.return_value={'job_id':'existing_job','status':'awaiting_review',
                                         'review':{'question':'5 + 2','answer':7,'steps':[]}}
        self.app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py')).run(timeout=5)

    def test_studio_link_selects_saved_character_without_reading_or_generating(self):
        self.app.query_params['character']=self.saved['id']
        self.app.run(timeout=5)
        self.assertEqual(len(self.app.exception),0)
        self.assertEqual(self.app.selectbox(key='friend_kind').value,'studio')
        self.assertEqual(self.app.selectbox(key='studio_character_id').value,self.saved['id'])
        self.client.create_job.assert_not_called()
        self.client.generate.assert_not_called()
        self.assertNotIn('character',self.app.query_params)

    def test_bad_link_shows_friendly_warning_and_never_accesses_a_job(self):
        self.app.query_params['character']='../../private/file'
        self.app.run(timeout=5)
        self.assertEqual(len(self.app.exception),0)
        self.assertTrue(any('could not be opened' in item.value for item in self.app.warning))
        self.client.create_job.assert_not_called()
        self.client.get_job.assert_not_called()

    def test_link_does_not_replace_the_character_or_picture_in_a_current_lesson(self):
        picture=(Path(__file__).resolve().parents[1]/'examples/worksheets/user_popsicle_addition.png').read_bytes()
        original={'job_id':'existing_job','access_token':'example_token_0123456789',
                  'character':{'kind':'robot','name':'Original'},'picture':picture}
        self.app.session_state['lesson_job']=original
        self.app.query_params['character']=self.saved['id']
        self.app.run(timeout=5)
        self.assertEqual(len(self.app.exception),0)
        self.assertEqual(self.app.session_state['lesson_job'],original)
        self.client.create_job.assert_not_called()
        self.client.generate.assert_not_called()


if __name__=='__main__':
    unittest.main()
