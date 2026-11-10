"""Turn a supported text question into a narrated cartoon MP4."""
import argparse
import copy
import json
import math
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

from .planner import plan_question, UnsupportedQuestion
from .visuals import render_frame


def prepare_object_spec(spec):
    """Preserve a validated picture lesson and describe its artwork truthfully.

    The worksheet reader supplies one extracted sprite per rendered object, in
    first-group then second-group order. Its geometry/count checks remain the
    source of the math; this helper does not infer a semantic object name.
    """
    prepared = copy.deepcopy(spec)
    if 'object_images' not in prepared:
        return prepared
    kind = prepared['type']
    if kind not in ('addition', 'subtraction', 'counting', 'comparison'):
        raise ValueError('Extracted picture sprites require a counting or arithmetic lesson.')
    images = prepared['object_images']
    if not isinstance(images, list):
        raise ValueError('The extracted object pictures must be a list.')
    required = prepared['a'] + (prepared['b'] if kind in ('addition', 'comparison') else 0)
    if len(images) != required:
        raise ValueError(f'This lesson needs exactly {required} extracted object pictures; got {len(images)}.')
    paths = [Path(path).expanduser().resolve() for path in images]
    if any(not path.is_file() for path in paths):
        raise ValueError('An extracted worksheet object picture is missing.')
    prepared['object_images'] = [str(path) for path in paths]
    singular = prepared.get('object_label', 'picture')
    plural = prepared.get('object_label_plural', singular + 's')
    if not all(isinstance(value, str) and len(value)<=64 and re.fullmatch(r'[a-z]+(?:[ -][a-z]+){0,3}', value)
               for value in (singular, plural)):
        raise ValueError('Object labels must be simple lowercase words.')
    prepared['object_label'], prepared['object_label_plural'] = singular, plural

    def replace_dots(value):
        def replace(match):
            replacement = plural if match.group().lower() == 'dots' else singular
            return replacement.capitalize() if match.group()[0].isupper() else replacement
        return re.sub(r'\bdots?\b', replace, value, flags=re.IGNORECASE)

    prepared['title'] = replace_dots(prepared['title'])
    for step in prepared['steps']:
        step['text'] = replace_dots(step['text'])
    return prepared


def stamp(sec):
    value = round(sec*1000)
    return f'{value//3600000:02}:{value//60000%60:02}:{value//1000%60:02},{value%1000:03}'


def make_timeline(spec, out, voice, rate):
    from .audio import synthesize
    audio_dir = out/'audio'
    audio_dir.mkdir(parents=True, exist_ok=True)
    events, cursor = [], .6
    for index, step in enumerate(spec['steps']):
        path = audio_dir/f'{index:02d}.wav'
        metadata = synthesize(step['text'], path, voice=voice, rate=rate)
        event = {**step, **metadata, 'start':cursor, 'end':cursor+metadata['duration']}
        events.append(event)
        # Allow each count to be heard before moving the highlight.
        gap = float(step.get('pause_after', .45 if 'active_index' in step else .3))
        cursor = event['end'] + gap
        print(f"  Speech {index+1}/{len(spec['steps'])}: {step['text']}", flush=True)
    return events, math.ceil((cursor+1)*24)/24


def mix_audio(events, duration, output_path):
    sr = 48000
    samples = np.zeros(math.ceil(duration*sr), dtype=np.float32)
    for ev in events:
        with wave.open(str(ev['path']), 'rb') as wav:
            if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth()) != (sr,1,2):
                raise RuntimeError('Narration must be 48 kHz mono PCM16.')
            clip = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(np.float32)/32768
        start = round(ev['start']*sr)
        samples[start:start+len(clip)] += clip
    peak = float(np.max(np.abs(samples)))
    # No music or chimes mask numbers; final export applies gentle loudness normalization.
    if peak>.88:
        samples *= .88/peak
    with wave.open(str(output_path), 'wb') as wav:
        wav.setframerate(sr); wav.setnchannels(1); wav.setsampwidth(2)
        wav.writeframes((samples*32767).astype('<i2').tobytes())
    return {'peak_dbfs':round(20*math.log10(max(float(np.max(np.abs(samples))),1e-8)),2),
            'rms_dbfs':round(20*math.log10(max(float(np.sqrt(np.mean(samples**2))),1e-8)),2)}


def verify_video(path):
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
    video = next(s for s in probe['streams'] if s['codec_type']=='video')
    audio = next(s for s in probe['streams'] if s['codec_type']=='audio')
    if (video['width'],video['height']) != (1280,720) or int(audio['sample_rate'])!=48000:
        raise RuntimeError('Unexpected export dimensions or audio format.')
    subprocess.run(['ffmpeg','-hide_banner','-v','error','-i',str(path),'-map','0:v:0','-map','0:a:0','-f','null','-'],check=True)
    return {'duration':float(probe['format']['duration']), 'size_bytes':int(probe['format']['size']),
            'resolution':[video['width'],video['height']], 'audio_sample_rate':int(audio['sample_rate']),
            'decode':'passed'}


def generate(question, out, voice='Samantha', rate=145, preview_only=False, plan_only=False, *, spec=None):
    # Validate before creating directories or invoking any speech service.
    spec = prepare_object_spec(plan_question(question) if spec is None else spec)
    out = Path(out).expanduser().resolve()
    out.mkdir(parents=True,exist_ok=True)
    (out/'lesson.json').write_text(json.dumps(spec,indent=2,ensure_ascii=False)+'\n')
    if plan_only:
        return {'plan':str(out/'lesson.json'), 'type':spec['type'], 'answer':spec['answer']}
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise RuntimeError('Install FFmpeg, including ffprobe, and put it on PATH.')
    events, duration = make_timeline(spec,out,voice,rate)
    (out/'timeline.json').write_text(json.dumps({'events':events,'duration':duration},indent=2,ensure_ascii=False)+'\n')
    srt = [f"{i}\n{stamp(e['start'])} --> {stamp(e['end'])}\n{e['text']}\n" for i,e in enumerate(events,1)]
    (out/'captions.srt').write_text('\n'.join(srt))
    (out/'transcript.txt').write_text('\n'.join(e['text'] for e in events)+'\n')
    audio_stats = mix_audio(events,duration,out/'narration.wav')
    answer = next(e for e in events if e['phase']=='answer')
    render_frame(spec,events,answer['start']+.3,duration).save(out/'poster.png')
    snapshot_events = [events[0]] + [e for e in events if 'active_index' in e][:2] + [e for e in events if e['phase'] in ['action','question','answer','equality']]
    from PIL import Image
    sheet = Image.new('RGB',(1280,360*math.ceil(len(snapshot_events)/2)),'white')
    for i,e in enumerate(snapshot_events):
        im = render_frame(spec,events,e['start']+min(.3,e['duration']/2),duration).resize((640,360))
        sheet.paste(im,((i%2)*640,(i//2)*360))
    sheet.save(out/'contact_sheet.jpg',quality=90)
    if preview_only:
        return {'type':spec['type'],'answer':spec['answer'],'poster':str(out/'poster.png'),'duration':duration}
    frames = round(duration*24)
    silent = out/'animation.mp4'
    encoder = subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1280x720','-r','24','-i','-','-an','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p',str(silent)],stdin=subprocess.PIPE)
    try:
        for frame in range(frames):
            encoder.stdin.write(render_frame(spec,events,frame/24,duration).tobytes())
            if frame%(24*10)==0:
                print(f'  Rendering {frame/24:.0f}/{duration:.1f} seconds',flush=True)
        encoder.stdin.close()
        if encoder.wait()!=0:
            raise RuntimeError('Video encoder failed.')
    except BaseException:
        encoder.kill(); encoder.wait()
        raise
    final = out/'lesson.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(silent),'-i',str(out/'narration.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','160k','-af','loudnorm=I=-17:TP=-2:LRA=7','-ar','48000','-movflags','+faststart',str(final)],check=True)
    report = {'question':question,'type':spec['type'],'answer':spec['answer'],'video':str(final),
              'voice':voice,'rate':rate,'audio_mix':audio_stats,**verify_video(final)}
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    silent.unlink()
    return report


def main():
    parser = argparse.ArgumentParser(description='Create a local narrated cartoon from a supported K–2 text question or worksheet picture.')
    parser.add_argument('question',nargs='?',help='For example: What is 4 + 3?')
    parser.add_argument('--image',type=Path,help='Read one clear worksheet PNG/JPEG before generating the lesson.')
    parser.add_argument('--reader',choices=('local-vision','rules','gemini'),default='local-vision',
                        help='Worksheet reader: local vision (default), legacy rules, or optional Gemini (requires explicit setup).')
    parser.add_argument('--vision-model',type=Path,help='Optional already downloaded local vision model directory.')
    parser.add_argument('--crop',type=int,nargs=4,metavar=('X','Y','WIDTH','HEIGHT'),help='Optional single-question crop in oriented image pixels.')
    parser.add_argument('--inspect-only',action='store_true',help='Read a worksheet and save its explanation/annotated picture without audio or video.')
    parser.add_argument('--out',default='output/my_lesson')
    parser.add_argument('--voice',default='Samantha')
    parser.add_argument('--rate',type=int,default=145)
    parser.add_argument('--plan-only',action='store_true',help='Parse and write lesson.json without audio or video.')
    parser.add_argument('--preview-only',action='store_true',help='Generate speech, poster, and contact sheet without an MP4.')
    args = parser.parse_args()
    if bool(args.question)==bool(args.image):
        parser.error('Provide either a quoted text question or --image PATH.')
    if (args.crop or args.inspect_only) and not args.image:
        parser.error('--crop and --inspect-only require --image.')
    if not 90 <= args.rate <= 220:
        parser.error('--rate must be between 90 and 220 words per minute.')
    try:
        if args.image:
            from .worksheet import read_worksheet,save_interpretation
            reading=read_worksheet(args.image,crop=args.crop,reader=args.reader,model_path=args.vision_model)
            result=save_interpretation(reading,args.out)
            print(f"Read worksheet: {reading['question']} Answer: {reading['spec']['answer']}",flush=True)
            if not args.inspect_only:
                result.update(generate(reading['question'],args.out,args.voice,args.rate,args.preview_only,args.plan_only,spec=reading['spec']))
        else:
            result = generate(args.question,args.out,args.voice,args.rate,args.preview_only,args.plan_only)
    except (UnsupportedQuestion, ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f'Could not generate this lesson: {exc}',file=sys.stderr)
        return 2
    print(json.dumps(result,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
