"""Portable projects are editable data; restoring them never overwrites artwork."""
from io import BytesIO
import hashlib
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
import warnings
from unittest.mock import patch
import zipfile

from PIL import Image, ImageDraw

from character_studio import assets
from character_studio.images import png_bytes
from character_studio.parts import validate_design


def drawing():
    image = Image.new('RGBA', (120, 160))
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 10, 100, 90), fill='#59B7B1')
    draw.rounded_rectangle((30, 80, 90, 145), radius=12, fill='#AD9BDF')
    return png_bytes(image)


def package(manifest, image, *, extras=(), manifest_bytes=None):
    output = BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('character.json', json.dumps(manifest).encode() if manifest_bytes is None else manifest_bytes)
        archive.writestr('character.png', image)
        for name, value in extras:
            archive.writestr(name, value)
    return output.getvalue()


class StudioLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.character = assets.save_character('小星 Buddy', 'drawing', image=drawing(), root=self.root)
        self.original_folder = assets.character_dir(self.character['id'], self.root)
        self.original_bytes = (self.original_folder/'image.png').read_bytes()
        self.manifest = json.loads((self.original_folder/'meta.json').read_text())

    def restore(self, manifest=None, image=None, **kwargs):
        raw = package(self.manifest if manifest is None else manifest,
                      self.original_bytes if image is None else image, **kwargs)
        return assets.import_character(raw, self.root)

    def test_drawing_export_restore_keeps_exact_pixels_and_makes_fresh_id(self):
        restored = assets.import_character(assets.export_character(self.character['id'], self.root), self.root)
        self.assertNotEqual(restored['id'], self.character['id'])
        self.assertEqual(restored['name'], self.character['name'])
        self.assertEqual(restored['sha256'], self.character['sha256'])
        self.assertEqual((assets.character_dir(restored['id'], self.root)/'image.png').read_bytes(), self.original_bytes)
        self.assertEqual(assets.get_project(restored['id'], self.root), {'character':restored, 'design':None})
        self.assertNotIn(str(self.root), json.dumps(assets.get_project(restored['id'], self.root)))

    def test_old_id_is_data_and_never_used_as_an_output_path(self):
        restored = self.restore({**self.manifest, 'id':'../../outside', 'created_at':'old timestamp'})
        self.assertRegex(restored['id'], r'^[a-f0-9]{32}$')
        self.assertNotEqual(restored['created_at'], 'old timestamp')
        self.assertTrue(assets.character_dir(restored['id'], self.root).is_dir())

    def test_builder_project_can_be_reopened_edited_and_saved_without_replacing_original(self):
        original = assets.save_character('Nova', 'builder', design={'headwear':'helmet', 'back':'wings'}, root=self.root)
        source = assets.character_dir(original['id'], self.root)
        before = {path.name:path.read_bytes() for path in source.iterdir()}
        restored = assets.import_character(assets.export_character(original['id'], self.root), self.root)
        project = assets.get_project(restored['id'], self.root)
        self.assertEqual(project['design'], validate_design({'name':'Nova', 'headwear':'helmet', 'back':'wings'}))
        project['design']['headwear'] = 'ears'
        edited = assets.save_character('New Nova', 'builder', design=project['design'], root=self.root)
        self.assertNotEqual(edited['sha256'], original['sha256'])
        self.assertEqual(assets.get_project(restored['id'], self.root)['design']['headwear'], 'helmet')
        self.assertEqual({path.name:path.read_bytes() for path in source.iterdir()}, before)

    def test_restoring_valid_builder_artwork_does_not_rerender_or_change_its_saved_look(self):
        manifest = {**self.manifest, 'source':'builder', 'design':validate_design({'name':self.character['name']})}
        # The pixels can come from an earlier renderer. They are verified data,
        # not a claim that the installed renderer produced them.
        with patch('character_studio.parts.render_design', side_effect=AssertionError('Unexpected rerender')):
            restored = self.restore(manifest)
        self.assertEqual(restored['sha256'], self.character['sha256'])
        self.assertEqual(assets.get_project(restored['id'], self.root)['design'], manifest['design'])

    def test_duplicate_drawing_keeps_artwork_and_original_metadata_unchanged(self):
        before = (self.original_folder/'meta.json').read_bytes()
        copied = assets.duplicate_character(self.character['id'], 'New Friend', root=self.root)
        self.assertEqual(copied['name'], 'New Friend')
        self.assertNotEqual(copied['id'], self.character['id'])
        self.assertEqual(copied['sha256'], self.character['sha256'])
        self.assertEqual((self.original_folder/'meta.json').read_bytes(), before)
        self.assertEqual(assets.get_project(copied['id'], self.root)['design'], None)

    def test_duplicate_builder_changes_only_name_and_identity(self):
        original = assets.save_character('Nova', 'builder', design={'headwear':'antenna'}, root=self.root)
        original_project = assets.get_project(original['id'], self.root)
        copied = assets.duplicate_character(original['id'], 'Nova Two', self.root)
        self.assertEqual(copied['sha256'], original['sha256'])
        self.assertEqual(assets.get_project(copied['id'], self.root)['design'],
                         {**original_project['design'], 'name':'Nova Two'})
        self.assertEqual(assets.get_project(original['id'], self.root), original_project)
        again = assets.duplicate_character(original['id'], root=self.root)
        self.assertEqual(again['name'], original['name'])

    def test_invalid_duplicate_name_or_id_never_creates_an_entry(self):
        for name in ('', '<script>', '../New', 'A'*33):
            with self.subTest(name=name), self.assertRaises(ValueError):
                assets.duplicate_character(self.character['id'], name, self.root)
        with self.assertRaises(ValueError):
            assets.get_project('../../outside', self.root)
        self.assertEqual(len(assets.list_characters(self.root)), 1)

    def test_invalid_zip_and_oversized_archive_are_rejected(self):
        for raw in (b'', b'not zip', bytearray(b'not zip'), b'x'*(assets.MAX_PACKAGE_BYTES+1)):
            with self.subTest(kind=type(raw).__name__, size=len(raw)), self.assertRaises(ValueError):
                assets.import_character(raw, self.root)

    def test_unknown_traversal_and_directory_members_are_rejected(self):
        for name in ('../outside', '/tmp/outside', 'nested/character.json', 'README.txt/', 'script.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.restore(extras=((name, b'data'),))

    def test_missing_required_member_is_rejected(self):
        output = BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('character.json', json.dumps(self.manifest))
        with self.assertRaises(ValueError):
            assets.import_character(output.getvalue(), self.root)

    def test_duplicate_member_is_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            raw = package(self.manifest, self.original_bytes, extras=(('character.png', self.original_bytes),))
        with self.assertRaises(ValueError):
            assets.import_character(raw, self.root)

    def test_symlink_and_other_nonregular_members_are_rejected(self):
        for file_type in (stat.S_IFLNK, stat.S_IFDIR, stat.S_IFIFO):
            info = zipfile.ZipInfo('README.txt')
            info.create_system = 3
            info.external_attr = (file_type | 0o644) << 16
            with self.subTest(file_type=file_type), self.assertRaises(ValueError):
                self.restore(extras=((info, b'../outside'),))

    def test_encrypted_member_is_rejected(self):
        raw = bytearray(package(self.manifest, self.original_bytes))
        # Set the encryption bit in both the first local header and central
        # directory entry; no decryption or password prompt should be attempted.
        for signature, offset in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
            index = raw.index(signature)+offset
            flags = struct.unpack_from('<H', raw, index)[0]
            struct.pack_into('<H', raw, index, flags | 1)
        with self.assertRaises(ValueError):
            assets.import_character(bytes(raw), self.root)

    def test_unsupported_compression_is_rejected(self):
        output = BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_BZIP2) as archive:
            archive.writestr('character.json', json.dumps(self.manifest))
            archive.writestr('character.png', self.original_bytes)
        with self.assertRaises(ValueError):
            assets.import_character(output.getvalue(), self.root)

    def test_exact_manifest_limit_is_accepted_and_one_byte_over_is_rejected(self):
        manifest = json.dumps(self.manifest).encode()
        raw = manifest+b' '*(assets.MAX_MANIFEST_BYTES-len(manifest))
        self.assertEqual(self.restore(manifest_bytes=raw)['sha256'], self.character['sha256'])
        with self.assertRaises(ValueError):
            self.restore(manifest_bytes=raw+b' ')

    def test_uncompressed_image_and_total_package_limits_are_checked_before_decode(self):
        image = b'0'*(assets.MAX_UPLOAD_BYTES+1)
        with patch('character_studio.assets._package_artwork', side_effect=AssertionError('Decoded oversized image')):
            with self.assertRaises(ValueError):
                self.restore(image=image)
            with self.assertRaises(ValueError):
                self.restore(extras=(('README.txt', b'0'*assets.MAX_PACKAGE_CONTENT_BYTES),))

    def test_corrupt_crc_never_saves_an_entry(self):
        output = BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as archive:
            archive.writestr('character.json', json.dumps(self.manifest))
            archive.writestr('character.png', self.original_bytes)
        raw = bytearray(output.getvalue())
        index = raw.index(self.original_bytes)
        raw[index+50] ^= 1
        with self.assertRaises(ValueError):
            assets.import_character(bytes(raw), self.root)
        self.assertEqual(len(assets.list_characters(self.root)), 1)

    def test_manifest_requires_supported_version_source_name_and_no_unknown_fields(self):
        changes = ({'version':True}, {'version':2}, {'source':'script'}, {'source':[]},
                   {'name':'../friend'}, {'name':'  Friend  '}, {'name':''}, {'run':'anything'})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.restore({**self.manifest, **change})

    def test_duplicate_json_fields_and_nonfinite_constants_are_rejected(self):
        raw = json.dumps(self.manifest).encode()
        for malformed in (b'[]', b'{', b'\xff', b'{"version":1,"version":1}',
                          b'{"version":NaN}', raw[:-1]+b',"sha256":"'+self.manifest['sha256'].encode()+b'"}'):
            with self.subTest(raw=malformed[:50]), self.assertRaises(ValueError):
                self.restore(manifest_bytes=malformed)

    def test_image_hash_must_match_and_use_canonical_sha256(self):
        for digest in ('0'*64, self.manifest['sha256'].upper(), None, []) :
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                self.restore({**self.manifest, 'sha256':digest})

    def test_image_must_be_nonempty_single_frame_rgba_png_at_saved_size(self):
        image_values = [png_bytes(Image.new('RGBA', (599, 800), '#8866CC')),
                        png_bytes(Image.new('RGB', (600, 800), '#8866CC')),
                        png_bytes(Image.new('RGBA', (600, 800))), b'bad image']
        jpeg = BytesIO()
        Image.new('RGB', (600, 800), 'blue').save(jpeg, 'JPEG')
        image_values.append(jpeg.getvalue())
        animation = BytesIO()
        Image.new('RGBA', (600, 800), 'red').save(animation, 'PNG', save_all=True,
                 append_images=[Image.new('RGBA', (600, 800), 'blue')])
        image_values.append(animation.getvalue())
        for raw in image_values:
            manifest = {**self.manifest, 'sha256':hashlib.sha256(raw).hexdigest()}
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                self.restore(manifest, raw)

    def test_drawing_cannot_smuggle_design_and_builder_requires_complete_canonical_parts(self):
        design = validate_design({'name':self.character['name']})
        invalid = [self.manifest | {'design':design},
                   self.manifest | {'source':'builder', 'design':None},
                   self.manifest | {'source':'builder', 'design':{}},
                   self.manifest | {'source':'builder', 'design':design | {'name':'Other'}},
                   self.manifest | {'source':'builder', 'design':design | {'primary_color':'#aabbcc'}},
                   self.manifest | {'source':'builder', 'design':design | {'script':'oops'}}]
        for manifest in invalid:
            with self.subTest(design=manifest['design']), self.assertRaises(ValueError):
                self.restore(manifest)

    def test_get_project_rejects_changed_parts_without_touching_original_image(self):
        original = assets.save_character('Nova', 'builder', root=self.root)
        folder = assets.character_dir(original['id'], self.root)
        manifest = json.loads((folder/'meta.json').read_text())
        manifest['design']['path'] = '../outside'
        (folder/'meta.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            assets.get_project(original['id'], self.root)
        self.assertEqual(hashlib.sha256((folder/'image.png').read_bytes()).hexdigest(), original['sha256'])


if __name__ == '__main__':
    unittest.main()
