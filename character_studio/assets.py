"""Immutable local characters and a small portable, non-executable file format."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import stat
import unicodedata
import uuid
import zipfile
import zlib

from PIL import Image, UnidentifiedImageError

from .images import normalize_image, png_bytes, MAX_UPLOAD_BYTES


ID_PATTERN = re.compile(r'[a-f0-9]{32}\Z')
DEFAULT_STORAGE = Path(__file__).resolve().parent.parent/'.cache/character_studio'
MAX_PACKAGE_BYTES = 8 * 1024 * 1024
MAX_PACKAGE_CONTENT_BYTES = 12 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
_PACKAGE_MEMBERS = {'character.json', 'character.png', 'README.txt'}
_MANIFEST_FIELDS = {'version', 'id', 'name', 'source', 'created_at', 'sha256', 'design'}


def storage_root(root=None):
    return Path(root or os.environ.get('CHARACTER_STUDIO_STORAGE') or DEFAULT_STORAGE).resolve()


def normalize_name(value):
    if not isinstance(value, str):
        raise ValueError('Give your character a short name.')
    value = ' '.join(unicodedata.normalize('NFC', value).split())
    if (not 1 <= len(value) <= 32 or not value[0].isalnum()
            or any(not (char.isalnum() or char in " '-") for char in value)):
        raise ValueError('Use 1–32 letters, numbers, spaces, apostrophes, or hyphens for the name.')
    return value


def character_dir(character_id, root=None):
    if not isinstance(character_id, str) or not ID_PATTERN.fullmatch(character_id):
        raise ValueError('This character could not be found.')
    return storage_root(root)/'characters'/character_id


def _public(metadata):
    value = {key: metadata[key] for key in ('id', 'name', 'source', 'created_at', 'sha256')}
    value['urls'] = {'image':f'/api/characters/{value["id"]}/image',
                     'package':f'/api/characters/{value["id"]}/package'}
    return value


def _save_artwork(name, source, raw, design, root=None):
    """Publish a new entry without modifying any existing character.

    Callers validate the artwork before reaching this helper. In particular,
    restoring a package keeps its original PNG bytes even if a newer renderer
    would draw the same editable parts a little differently.
    """
    character_id = uuid.uuid4().hex
    folder = character_dir(character_id, root)
    folder.mkdir(parents=True, mode=0o700)
    metadata = {'version':1, 'id':character_id, 'name':name, 'source':source,
                'created_at':datetime.now(timezone.utc).isoformat(),
                'sha256':hashlib.sha256(raw).hexdigest(), 'design':design}
    try:
        (folder/'image.png').write_bytes(raw)
        temporary = folder/'meta.json.tmp'
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        temporary.replace(folder/'meta.json')
    except Exception:
        # An interrupted unpublished save never becomes a library entry.
        shutil.rmtree(folder)
        raise
    return _public(metadata)


def save_character(name, source, *, design=None, image=None, root=None):
    name = normalize_name(name)
    if source == 'builder':
        from .parts import render_design, validate_design
        design = validate_design({**(design or {}), 'name':name})
        sprite = render_design(design)
    elif source == 'drawing':
        if design is not None:
            raise ValueError('Save either a drawing or a parts design.')
        sprite = normalize_image(image)
    else:
        raise ValueError('Choose a drawing or a character made from parts.')
    raw = png_bytes(sprite)
    return _save_artwork(name, source, raw, design, root)


def get_character(character_id, root=None):
    folder = character_dir(character_id, root)
    try:
        metadata = json.loads((folder/'meta.json').read_text())
        name = normalize_name(metadata['name'])
        raw = (folder/'image.png').read_bytes()
        if (metadata['version'] != 1 or metadata['id'] != character_id or name != metadata['name']
                or metadata['source'] not in ('builder', 'drawing')
                or len(raw) > MAX_UPLOAD_BYTES
                or hashlib.sha256(raw).hexdigest() != metadata['sha256']):
            raise ValueError('The saved character changed. Save a new copy in Character Studio.')
        return _public(metadata)
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('This character could not be found. Save it again in Character Studio.') from exc


def _canonical_design(value, name, source):
    if source == 'drawing':
        if value is not None:
            raise ValueError('A saved drawing cannot contain character parts.')
        return None
    from .parts import validate_design
    if not isinstance(value, dict):
        raise ValueError('The saved character parts could not be read.')
    design = validate_design(value)
    # Portable projects record complete, normalized data, not instructions or
    # unknown future fields. Do not silently repair a mismatched saved project.
    if design != value or design['name'] != name:
        raise ValueError('The saved character parts do not match this character.')
    return design


def get_project(character_id, root=None):
    """Return editable data and public metadata, never local filesystem paths."""
    character = get_character(character_id, root)
    try:
        metadata = json.loads((character_dir(character_id, root)/'meta.json').read_text(encoding='utf-8'))
        design = _canonical_design(metadata.get('design'), character['name'], character['source'])
    except (OSError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('The saved project could not be opened. Save a new copy in Character Studio.') from exc
    return {'character':character, 'design':design}


def duplicate_character(character_id, name=None, root=None):
    """Create a new library entry while preserving the original artwork exactly."""
    project = get_project(character_id, root)
    name = normalize_name(project['character']['name'] if name is None else name)
    design = project['design']
    if design is not None:
        design = {**design, 'name':name}
    raw = (character_dir(character_id, root)/'image.png').read_bytes()
    if hashlib.sha256(raw).hexdigest() != project['character']['sha256']:
        raise ValueError('This character changed before it could be copied.')
    return _save_artwork(name, project['character']['source'], raw, design, root)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('The character package contains duplicate project fields.')
        result[key] = value
    return result


def _invalid_json_constant(value):
    raise ValueError('The character package contains an unsupported project value.')


def _package_artwork(raw):
    """Decode a single exact-size PNG without rescaling or removing its paper."""
    try:
        with Image.open(BytesIO(raw)) as image:
            if (image.format != 'PNG' or image.size != (600, 800) or image.mode != 'RGBA'
                    or getattr(image, 'n_frames', 1) != 1):
                raise ValueError('A character package needs one 600 by 800 transparent PNG.')
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            image.load()
            if image.getchannel('A').getbbox() is None:
                raise ValueError('The character package contains an empty drawing.')
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError('The character picture in this package could not be opened.') from exc


def import_character(raw, root=None):
    """Restore a bounded data-only package to a fresh immutable library entry.

    Files are read in memory and never extracted to paths supplied by a ZIP.
    The old ID and timestamp are intentionally discarded. A validated editable
    parts design is retained alongside the package's exact original artwork.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_PACKAGE_BYTES:
        raise ValueError('Choose a character ZIP package smaller than 8 MB.')
    contents = {}
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (len(names) != len(set(names)) or not {'character.json', 'character.png'} <= set(names)
                    or set(names) - _PACKAGE_MEMBERS):
                raise ValueError('A character package contains only character.json, character.png, and an optional README.txt.')
            total = 0
            for info in infos:
                file_kind = stat.S_IFMT(info.external_attr >> 16)
                if (info.is_dir() or info.flag_bits & 1
                        or file_kind not in (0, stat.S_IFREG)
                        or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise ValueError('The character package contains an unsupported file.')
                limit = (MAX_MANIFEST_BYTES if info.filename == 'character.json'
                         else MAX_UPLOAD_BYTES if info.filename == 'character.png'
                         else MAX_PACKAGE_CONTENT_BYTES)
                total += info.file_size
                if info.file_size > limit or total > MAX_PACKAGE_CONTENT_BYTES:
                    raise ValueError('The character package expands beyond the allowed size.')
            for info in infos:
                with archive.open(info) as member:
                    content = member.read(info.file_size + 1)
                if len(content) != info.file_size:
                    raise ValueError('The character package contains an incomplete file.')
                if info.filename != 'README.txt':
                    contents[info.filename] = content
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, NotImplementedError,
            RuntimeError, zlib.error) as exc:
        raise ValueError('This character ZIP package could not be opened.') from exc
    try:
        manifest = json.loads(contents['character.json'].decode('utf-8'),
                              object_pairs_hook=_json_object, parse_constant=_invalid_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('The character project in this package could not be read.') from exc
    if (not isinstance(manifest, dict) or set(manifest) - _MANIFEST_FIELDS
            or type(manifest.get('version')) is not int or manifest['version'] != 1
            or manifest.get('source') not in ('builder', 'drawing')):
        raise ValueError('Choose a supported version 1 Character Studio package.')
    name = normalize_name(manifest.get('name'))
    if name != manifest['name']:
        raise ValueError('The character package needs a valid saved name.')
    digest = manifest.get('sha256')
    if (not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest)
            or hashlib.sha256(contents['character.png']).hexdigest() != digest):
        raise ValueError('The character picture does not match its saved package.')
    design = _canonical_design(manifest.get('design'), name, manifest['source'])
    _package_artwork(contents['character.png'])
    return _save_artwork(name, manifest['source'], contents['character.png'], design, root)


def list_characters(root=None):
    directory = storage_root(root)/'characters'
    results = []
    if directory.is_dir():
        for folder in directory.iterdir():
            if folder.is_dir() and ID_PATTERN.fullmatch(folder.name):
                try:
                    results.append(get_character(folder.name, root))
                except ValueError:
                    continue
    return sorted(results, key=lambda value:value['created_at'], reverse=True)


def load_character_image(character_id, root=None):
    get_character(character_id, root)
    with Image.open(character_dir(character_id, root)/'image.png') as image:
        if image.format != 'PNG' or image.size != (600, 800):
            raise ValueError('This character picture is not in the saved format.')
        return image.convert('RGBA')


def snapshot_character(character_id, destination, root=None):
    metadata = get_character(character_id, root)
    # The normalized PNG is the complete immutable artwork used by the video.
    raw = (character_dir(character_id, root)/'image.png').read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata['sha256']:
        raise ValueError('This character changed before it could be copied.')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return metadata


def export_character(character_id, root=None):
    metadata = get_character(character_id, root)
    folder = character_dir(character_id, root)
    manifest = json.loads((folder/'meta.json').read_text())
    output = BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('character.json', json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        archive.writestr('character.png', (folder/'image.png').read_bytes())
        archive.writestr('README.txt', 'My Lesson Buddy Character Studio\n'
                         'character.png is a transparent sticker. character.json records the parts and name.\n'
                         'The files contain no executable code. Original saved characters are immutable.\n')
    return output.getvalue()
