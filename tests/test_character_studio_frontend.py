"""Behavior checks for the browser drawing tools without third-party test dependencies."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CharacterStudioFrontendTests(unittest.TestCase):
    def test_static_controls_match_script_references(self):
        html = (ROOT / 'character_studio/static/index.html').read_text()
        javascript = (ROOT / 'character_studio/static/studio.js').read_text()
        actual = set(re.findall(r'\bid="([^"]+)"', html))
        references = set(re.findall(r'\$\("([^"]+)"\)', javascript))
        self.assertEqual(references - actual, set(), 'Script references a missing control')
        self.assertEqual(len(re.findall(r'\bid="([^"]+)"', html)), len(actual), 'Duplicate element IDs')

    @unittest.skipUnless(shutil.which('node'), 'Node.js is optional for frontend behavior checks')
    def test_drawing_and_handoff_behaviors(self):
        result = subprocess.run(
            ['node', '--test', 'tests/character_studio_frontend.test.cjs'],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
