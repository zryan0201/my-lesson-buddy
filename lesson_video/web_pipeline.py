"""Adapt the checked local generator to the app's read/review/render jobs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class LessonPipeline:
    """Read once, then render exactly the lesson presented for review."""

    def analyze(self, image_path, job_dir, character):
        from .characters import validate_character
        from .worksheet import read_worksheet, save_interpretation

        reader=os.environ.get('LESSON_VISION_READER','local-vision')
        if reader not in ('local-vision','gemini'):
            raise ValueError('Choose local-vision or gemini for LESSON_VISION_READER before starting a lesson.')
        folder=Path(job_dir).resolve()
        config=validate_character(character)
        character_path=None
        design_path=None
        if config['kind']=='studio':
            from character_studio.assets import get_project, snapshot_character
            from character_studio.motion import design_matches_image
            from PIL import Image
            project=get_project(config['asset_id'])
            metadata=project['character']
            if config['name']!=metadata['name']:
                raise ValueError('The saved character name changed. Please choose your character again.')
            folder.mkdir(parents=True,exist_ok=True)
            character_path=folder/'character.png'
            snapshot_character(config['asset_id'],character_path)
            with Image.open(character_path) as saved:
                can_animate=design_matches_image(project['design'],saved)
            if can_animate:
                design_path=folder/'character_design.json'
                design_path.write_text(json.dumps(project['design'],ensure_ascii=False,sort_keys=True,
                                                  indent=2)+'\n',encoding='utf-8')
        reading=read_worksheet(image_path,reader=reader)
        reading['spec']['character']=config
        if character_path is not None:
            reading['spec']['character_image']=str(character_path)
        if design_path is not None:
            reading['spec']['character_design']=str(design_path)
        save_interpretation(reading,folder)
        spec=reading['spec']
        protected=[folder/'lesson.json',folder/'worksheet_input.png']
        if character_path is not None:
            protected.append(character_path)
        if design_path is not None:
            protected.append(design_path)
        protected.extend(Path(path) for path in spec.get('object_images',[]))
        checks={}
        for path in protected:
            relative=path.resolve().relative_to(folder)
            checks[str(relative)]=_digest(path)
        (folder/'analysis_manifest.json').write_text(json.dumps({'files':checks,'character':config},indent=2)+'\n')
        return {'question':spec['question'],'type':spec['type'],'a':spec.get('a'),'b':spec.get('b'),
                'answer':spec['answer'],'object_label':spec.get('object_label','dot'),
                'steps':[{key:step[key] for key in ('phase','text','pause_after') if key in step}
                         for step in spec['steps']],
                'warnings':['Check the question and pictured quantities before making the video.'],
                'reader':reading['reader']}

    def render(self, job_dir, character):
        from .characters import validate_character
        from .generate import generate

        folder=Path(job_dir).resolve()
        manifest=json.loads((folder/'analysis_manifest.json').read_text())
        config=validate_character(character)
        if config!=manifest['character']:
            raise ValueError('The character changed after review. Please start a new lesson.')
        for relative,expected in manifest['files'].items():
            path=(folder/relative).resolve()
            if not path.is_relative_to(folder) or not path.is_file() or _digest(path)!=expected:
                raise ValueError('The reviewed lesson changed. Please read the worksheet again.')
        spec=json.loads((folder/'lesson.json').read_text())
        if spec.get('character')!=config:
            raise ValueError('The saved character does not match the reviewed lesson.')
        if config['kind']=='studio':
            # Render from the hashed lesson snapshot even if the library entry
            # has since disappeared. Never resolve the original asset again.
            expected=str(folder/'character.png')
            if (spec.get('character_image')!=expected
                    or 'character.png' not in manifest['files']):
                raise ValueError('The reviewed character snapshot is missing. Please start a new lesson.')
            design=spec.get('character_design')
            if design is not None and (design!=str(folder/'character_design.json')
                                      or 'character_design.json' not in manifest['files']):
                raise ValueError('The reviewed character design is missing. Please start a new lesson.')
        generate(spec['question'],folder,spec=spec)
        return {'video':'lesson.mp4','poster':'poster.png'}
