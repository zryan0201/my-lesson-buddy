"""Build hosted speech clips once; visitors need no Mac, API key, or speech service.

Run from the repository with `.venv-speech/bin/python web_site/scripts/build_narration.py`.
Only the bounded, authored K–2 phrases below reach the installed speech engine.
MP3s and an exact timing/text manifest are saved as ordinary public Site assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lesson_video.audio import synthesize

WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten')


def authored_phrases():
    result = {
        'hello': "Let's learn together. Take your time and count with me.",
        'look-groups': 'Look at the two groups of pictures. We will put them together.',
        'look-take': 'Look at the pictures. We will take some away.',
        'look-count': 'How many pictures do you see? Let us count them together.',
        'look-shape': 'Let us explore a shape and count its straight sides.',
        'remaining': 'Now let us count the pictures that are left.',
        'turn-add': 'How many pictures are there altogether? It is your turn.',
        'turn-sub': 'How many pictures are left? It is your turn.',
        'turn-count': 'How many pictures did you count? It is your turn.',
        'turn-shape': 'How many straight sides does this shape have? It is your turn.',
        'look-shape-name': 'Let us look closely at the outline of a shape.',
        'turn-name': 'What shape is this? It is your turn.',
        'celebrate': 'Great counting and thinking. You did it!',
        'shape-circle': 'This is a circle. It is round, with no corners and no straight sides.',
        'shape-triangle': 'This is a triangle. Let us count its straight sides.',
        'shape-square': 'This is a square. It has four equal straight sides.',
        'shape-rectangle': 'This is a rectangle. Its opposite sides are the same length.',
        'answer-circle': 'A circle has zero straight sides.',
        'answer-triangle': 'A triangle has three straight sides.',
        'answer-square': 'A square has four straight sides.',
        'answer-rectangle': 'A rectangle has four straight sides.',
        'feature-circle': 'It is round, with no corners and no straight sides.',
        'feature-triangle': 'It has three straight sides and three corners.',
        'feature-square': 'It has four equal straight sides and four corners.',
        'feature-rectangle': 'It has four straight sides and four corners. Its opposite sides are the same length.',
        'answer-name-circle': 'This is a circle.',
        'answer-name-triangle': 'This is a triangle.',
        'answer-name-square': 'This is a square.',
        'answer-name-rectangle': 'This is a rectangle.',
        'story-intro': "Welcome to Starlight Garden. Let us help our buddy on a little adventure.",
        'story-add-goal': 'Our buddy is collecting stars for a starlight picnic. Let us fill the wagon together.',
        'story-sub-goal': 'Our buddy has stars to share with a garden friend. Let us see how many stay in the wagon.',
        'story-count-goal': 'Our buddy is exploring the garden. Let us visit each star and count it just once.',
        'story-shape-goal': 'A shape gate is waiting in the garden. Follow our buddy along each straight side.',
        'story-shape-name-goal': 'A garden gate is waiting for its shape name. Follow our buddy around the outline.',
        'story-remaining': 'Look inside our wagon. How many stars did our buddy keep?',
        'story-turn-add': 'How many stars are in the wagon altogether? Help our buddy find the answer.',
        'story-turn-sub': 'How many stars are still in the wagon? Help our buddy find the answer.',
        'story-turn-count': 'Our buddy visited every star. How many stars are in the garden?',
        'story-turn-shape': 'How many straight sides did our buddy follow? It is your turn.',
        'story-turn-name': 'Can you name the shape to open the garden gate? It is your turn.',
        'story-celebrate': 'You helped our buddy finish the adventure. Great counting and thinking!',
        'object-story-intro': 'Welcome to our garden. Let us help our buddy on a little adventure.',
        'object-add-goal': 'Our buddy is collecting the pictures from your worksheet for a picnic. Let us fill the wagon together.',
        'object-sub-goal': 'Our buddy has pictures from your worksheet to share with a friend. Watch what stays in the wagon.',
        'object-count-goal': 'Our buddy is exploring the garden. Let us visit each worksheet picture and count it just once.',
        'object-remaining': 'Look inside our wagon. How many worksheet pictures did our buddy keep?',
        'object-turn-add': 'How many worksheet pictures are in the wagon altogether? Help our buddy find the answer.',
        'object-turn-sub': 'How many worksheet pictures are still in the wagon? Help our buddy find the answer.',
        'object-turn-count': 'Our buddy visited every worksheet picture. How many pictures are in the garden?',
    }
    result.update({
        'adventure-garden-intro': 'Welcome to Garden Picnic. Let us help our buddy on a little adventure.',
        'adventure-workshop-intro': 'Welcome to Maker Workshop. Our buddy has a little mission for us.',
        'adventure-ocean-intro': 'Welcome to Ocean Discovery. Let us explore and think with our buddy.',
        'adventure-moon-intro': 'Welcome to Moon Station. Our buddy is ready for a counting adventure.',
        'adventure-add-goal': 'Our buddy is collecting stars. Let us fill the wagon together.',
        'adventure-sub-goal': 'Our buddy has stars to share with a friend. Watch how many stay in the wagon.',
        'adventure-count-goal': 'Let us explore the trail. Visit each star and count it just once.',
        'adventure-shape-goal': 'A shape gate is waiting. Follow our buddy along each straight side.',
        'adventure-shape-name-goal': 'A gate is waiting for its shape name. Follow our buddy around the outline.',
        'adventure-turn-count': 'Our buddy visited every star. How many stars did we find?',
        'adventure-turn-name': 'Can you name the shape to open the gate? It is your turn.',
        'adventure-object-add-goal': 'Our buddy is collecting pictures from your worksheet. Let us fill the wagon together.',
        'adventure-object-count-goal': 'Let us explore the trail. Visit each worksheet picture and count it just once.',
        'adventure-object-turn-count': 'Our buddy visited every worksheet picture. How many pictures did we find?',
    })
    for number, word in enumerate(WORDS):
        result[f'number-{number}'] = word.capitalize() + '.'
        result[f'first-{number}'] = ('We start with no pictures.' if number == 0 else
            f'We start with {word} picture' + ('.' if number == 1 else 's.'))
        result[f'add-{number}'] = ('Now we add no more pictures.' if number == 0 else
            f'Now we add {word} more picture' + ('.' if number == 1 else 's.'))
        result[f'take-{number}'] = ('We take away no pictures.' if number == 0 else
            f'Take away {word} picture' + ('.' if number == 1 else 's.'))
        result[f'on-{number}'] = f'We counted {word}. Now keep counting from there.'
        result[f'answer-count-{number}'] = ('There are no pictures. The count is zero.' if number == 0 else
            f'There ' + ('is ' if number == 1 else 'are ') + word + (' picture.' if number == 1 else ' pictures.'))
        result[f'story-first-{number}'] = ('Our buddy starts with an empty wagon. There are zero stars.' if number == 0 else
            f'Our buddy starts with {word} star' + (' in the wagon.' if number == 1 else 's in the wagon.'))
        result[f'story-collect-{number}'] = ('There are no more stars to bring. The wagon stays as it is.' if number == 0 else
            f'Our buddy will bring {word} more star' + ('. Count on as it joins the wagon.' if number == 1 else 's. Count on as each star joins the wagon.'))
        result[f'story-give-{number}'] = ('We share no stars this time. All the stars stay in the wagon.' if number == 0 else
            f'Our buddy will give {word} star' + (' to a friend. Watch it leave the wagon.' if number == 1 else 's to a friend. Watch them leave the wagon one at a time.'))
        result[f'story-answer-count-{number}'] = ('There are no stars in this garden yet. Zero means none.' if number == 0 else
            f'Our buddy found {word} star' + (' in the garden.' if number == 1 else 's in the garden.'))
        result[f'adventure-answer-count-{number}'] = ('There are no stars here. Zero means none.' if number == 0 else
            f'Our buddy found {word} star' + ('.' if number == 1 else 's.'))
    for a in range(11):
        for b in range(11):
            if a + b <= 10:
                result[f'answer-add-{a}-{b}'] = f'{WORDS[a].capitalize()} plus {WORDS[b]} equals {WORDS[a+b]}.'
            if b <= a:
                result[f'answer-sub-{a}-{b}'] = f'{WORDS[a].capitalize()} minus {WORDS[b]} equals {WORDS[a-b]}.'
    # Conversational prompts retain the same mathematical facts and answer order.
    # No voice instruction, emotion label or sound effect becomes spoken text.
    for key, text in list(result.items()):
        result[key] = text.replace('Let us', "Let's").replace('let us', "let's")
    result.update({
        'hello': "Hi, math explorers! Ready to discover something together?",
        'adventure-garden-intro': "Hey, explorer! Welcome to Garden Picnic. Your buddy could use a hand!",
        'adventure-workshop-intro': "Hi, maker! Welcome to Maker Workshop. Let's help your buddy with a little mission.",
        'adventure-ocean-intro': "Ready to dive in? Welcome to Ocean Discovery! Let's explore with your buddy.",
        'adventure-moon-intro': "Ready for a mission? Welcome to Moon Station! Let's explore with your buddy.",
        'adventure-add-goal': "Your buddy is collecting stars. Can you help fill the wagon?",
        'adventure-sub-goal': "Let's share some stars with a friend! Keep an eye on what's left in the wagon.",
        'adventure-count-goal': "Let's follow the trail! Point to each star and count it just once.",
        'adventure-shape-goal': "Look, a shape gate! Follow your buddy along each straight side.",
        'adventure-shape-name-goal': "There's a mystery gate! Let's explore its outline and find its shape name.",
        'adventure-turn-count': "We visited every star! How many did we find? Take your time.",
        'adventure-turn-name': "What shape will open this gate? It's your turn!",
        'adventure-object-add-goal': "Look at the pictures from your worksheet! Let's help your buddy fill the wagon.",
        'adventure-object-count-goal': "Let's explore! Point to each worksheet picture and count it just once.",
        'adventure-object-turn-count': "We visited every picture! How many did we find? Take your time.",
        'story-turn-add': "How many stars are in the wagon now? What do you think?",
        'story-turn-sub': "How many stars are left in the wagon? Take your time.",
        'object-turn-add': "How many worksheet pictures are in the wagon now? What do you think?",
        'object-turn-sub': "How many worksheet pictures are left in the wagon? Take your time.",
        'story-celebrate': "You did it! You helped your buddy finish the adventure. Great thinking!",
    })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=['kokoro', 'macos'], default='kokoro')
    parser.add_argument('--voice', help='Kokoro voice ID, or an installed Mac voice name')
    parser.add_argument('--model-dir', type=Path, default=ROOT / '.cache/kokoro')
    args = parser.parse_args()
    destination = ROOT / 'web_site/dist/audio'
    destination.mkdir(parents=True, exist_ok=True)
    working = ROOT / '.cache/hosted_narration'
    working.mkdir(parents=True, exist_ok=True)
    prior_path = destination / 'manifest.json'
    prior = json.loads(prior_path.read_text()) if prior_path.exists() else {}
    progress_path = working / f'{args.engine}-progress.json'
    if progress_path.exists():
        prior.update(json.loads(progress_path.read_text()))
    narrator = None
    if args.engine == 'kokoro':
        try:
            from lesson_video.neural_audio import NeuralNarrator, phrase_speed
            narrator = NeuralNarrator(args.model_dir, working / 'neural_cache', args.voice or 'af_heart')
        except ImportError as error:
            raise SystemExit('Install requirements-speech.txt in .venv-speech, then run its Python. ' + str(error))
    clips = {}
    for index, (key, text) in enumerate(authored_phrases().items()):
        count = int(key.split('-')[1]) if key.startswith('number-') else None
        voice = args.voice or ('af_heart' if narrator else 'Samantha')
        speed = phrase_speed(key) if narrator else None
        fingerprint = narrator.fingerprint(text, speed, sequence_index=count) if narrator else hashlib.sha256((voice + '-145-v2:' + text).encode()).hexdigest()
        # Immutable file URLs keep a cached old narrator from playing against a
        # newly measured scene duration after a website update.
        mp3 = destination / f'{key}.{fingerprint[:12]}.mp3'
        if mp3.is_file() and prior.get(key, {}).get('fingerprint') == fingerprint:
            clips[key] = prior[key]
            continue
        wav = working / f'{key}.wav'
        metadata = narrator.synthesize(text, wav, speed=speed, count=count) if narrator else synthesize(text, wav, voice, 145, cache_dir=working / 'speech_cache')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(wav),
            '-ar', '24000', '-ac', '1', '-c:a', 'libmp3lame', '-b:a', '64k', str(mp3)], check=True)
        duration = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
            'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(mp3)]))
        clips[key] = {'file': mp3.name, 'text': text, 'duration': round(duration, 6),
            'fingerprint': fingerprint, 'bytes': mp3.stat().st_size,
            'voice': voice, 'rate': None if narrator else 145, 'speed': speed,
            'engine': metadata.get('engine', 'macOS say'), 'peak_dbfs': metadata['peak_dbfs'],
            'clipped_samples': metadata['clipped_samples'],
            'count_source': 'timed continuous count performance' if narrator and count is not None else None}
        # Save incrementally so an interrupted build resumes without re-synthesizing.
        progress_path.write_text(json.dumps({**prior, **clips}, indent=2) + '\n')
        if index % 20 == 0:
            print(f'Prepared {index + 1} hosted narration clips.', flush=True)
    payload = json.dumps(clips, ensure_ascii=False, separators=(',', ':'))
    temporary = destination / 'manifest.json.tmp'
    temporary.write_text(json.dumps(clips, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(prior_path)
    temporary = destination / 'manifest.js.tmp'
    temporary.write_text('/* Authored local narration, generated once at build time. */\nexport const AUDIO = Object.freeze(' + payload + ');\n')
    temporary.replace(destination / 'manifest.js')
    report = {'clips': len(clips), 'bytes': sum(x['bytes'] for x in clips.values()),
        'engine_at_build': f'Kokoro-82M ONNX local CPU, {voice}, phrase-specific speed 0.82–0.94' if narrator else f'macOS {voice} 145 wpm',
        'runtime': 'Static MP3 assets decoded to PCM by WebAudio; no speech API calls',
        'paid_api_requests': 0, 'visitor_model_download_for_voice': False,
        'provenance': narrator.engine if narrator else {'engine':'macOS say', 'voice':voice}}
    (destination / 'build_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
