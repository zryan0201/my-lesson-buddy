"""Review-first UI behavior, with no model, speech, API, or network calls.

Install requirements-web.txt to run these checks. A form's checkbox and submit
are changed in one AppTest run, matching the browser's batched form submission.
"""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"


@unittest.skipIf(AppTest is None, "Install requirements-web.txt for the web interface checks.")
class StreamlitAppTests(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("lesson_video.web_client.LessonApiClient")
        self.client = self.patcher.start().return_value
        self.addCleanup(self.patcher.stop)
        self.job_id = "test_job_0123456789"
        self.token = "test_capability_0123456789"
        self.server_job = {
            "job_id": self.job_id,
            "status": "awaiting_review",
            "review": {"question": "What is 5 + 2?", "answer": 7,
                       "steps": [{"text": "Count five, then two more."}]},
        }
        self.client.create_job.return_value = {
            "job_id": self.job_id, "status": "awaiting_review", "access_token": self.token,
        }
        self.client.get_job.side_effect = lambda *args: copy.deepcopy(self.server_job)

        def generate(*args):
            self.server_job["status"] = "queued"
            return copy.deepcopy(self.server_job)

        self.client.generate.side_effect = generate
        self.app = AppTest.from_file(str(APP)).run(timeout=5)
        self.assert_no_exception()

    def assert_no_exception(self):
        self.assertEqual(len(self.app.exception), 0, [item.message for item in self.app.exception])

    def button(self, label):
        return next(button for button in self.app.button if button.label == label)

    def read_picture(self):
        self.button("Read my picture →").click().run(timeout=5)
        self.assert_no_exception()

    def test_character_preview_changes_never_submit_or_read_a_picture(self):
        self.app.selectbox(key="friend_kind").select("fox").run()
        self.app.selectbox(key="friend_accessory").select("cap").run()
        self.app.text_input(key="friend_name").input("Sunny").run()
        self.assert_no_exception()
        self.client.create_job.assert_not_called()
        self.client.get_job.assert_not_called()
        self.client.generate.assert_not_called()

    def test_upload_uses_a_frozen_character_and_does_not_resubmit_on_rerun(self):
        self.app.selectbox(key="friend_kind").select("fox").run()
        self.app.selectbox(key="friend_accessory").select("cap").run()
        self.read_picture()
        self.client.create_job.assert_called_once()
        submitted = self.client.create_job.call_args.kwargs
        self.assertEqual(submitted["character"]["kind"], "fox")
        self.assertEqual(submitted["character"]["accessory"], "cap")
        self.assertGreater(len(submitted["image"]), 0)
        self.assertGreaterEqual(len(submitted["client_request_id"]), 16)

        self.app.selectbox(key="friend_kind").select("bear").run()
        self.app.selectbox(key="friend_accessory").select("glasses").run()
        self.assert_no_exception()
        snapshot = self.app.session_state["lesson_job"]
        self.assertEqual(snapshot["character"]["kind"], "fox")
        self.assertEqual(snapshot["character"]["accessory"], "cap")
        self.assertEqual(snapshot["access_token"], self.token)
        self.assertTrue(self.button("Read my picture →").disabled)
        self.client.create_job.assert_called_once()
        self.client.generate.assert_not_called()
        self.assertTrue(all(call.args == (self.job_id, self.token)
                            for call in self.client.get_job.call_args_list))

    def test_adult_confirmation_is_required_and_video_is_submitted_once(self):
        self.read_picture()
        self.button("Make my video →").click().run()
        self.client.generate.assert_not_called()
        self.assertTrue(any("grown-up needs to check" in item.value for item in self.app.warning))

        # Streamlit forms send both values together when the submit is clicked.
        self.app.checkbox(key=f"review_confirmed_{self.job_id}").check()
        self.button("Make my video →").click().run()
        self.client.generate.assert_called_once_with(self.job_id, self.token)
        self.assertEqual(self.app.session_state["last_job"]["status"], "queued")
        self.app.run()
        self.app.selectbox(key="friend_kind").select("bear").run()
        self.assert_no_exception()
        self.client.generate.assert_called_once()
        self.client.create_job.assert_called_once()
        self.assertEqual(len(self.app.checkbox), 0)

    def test_invalid_character_name_is_graceful_and_cannot_be_submitted(self):
        self.app.text_input(key="friend_name").input("<unsafe name>").run()
        self.assert_no_exception()
        self.assertTrue(self.button("Read my picture →").disabled)
        self.assertTrue(any("Give your friend a name" in item.value for item in self.app.warning))
        self.client.create_job.assert_not_called()
        self.app.text_input(key="friend_name").input("   ").run()
        self.assert_no_exception()
        self.assertFalse(self.button("Read my picture →").disabled)
        self.read_picture()
        self.assertEqual(self.client.create_job.call_args.kwargs["character"]["name"], "Buddy")


if __name__ == "__main__":
    unittest.main()
