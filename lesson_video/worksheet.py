"""Interpret one clear worksheet crop with local OCR and geometric evidence.

This is a bounded reader, not general image understanding. Ambiguous pictures
raise WorksheetUnclear before narration or video generation starts.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from .ocr import recognize_text
from .planner import UnsupportedQuestion, plan_question
from .worksheet_objects import analyze_diagram


class WorksheetUnclear(ValueError):
    """The picture does not establish one supported, unambiguous question."""


def _center(item):
    b = item['bbox']
    return b['x']+b['width']/2, b['y']+b['height']/2


def _normalize_text(text):
    return ' '.join(text.replace('−','-').replace('–','-').replace('—','-')
                    .replace('＋','+').replace('＝','=').replace('？','?').split())


def _overlap_object_text(obj, line, size):
    b = obj['bbox']
    x,y,w,h = line['bbox']
    x,y,w,h = x*size[0],y*size[1],w*size[0],h*size[1]
    intersection = max(0,min(b['x']+b['width'],x+w)-max(b['x'],x))*max(0,min(b['y']+b['height'],y+h)-max(b['y'],y))
    # Ignore isolated O/0-like contours only when they belong to a recognized
    # numeric expression or a real word. A row of outlined counters may itself
    # be recognized as 'O O O', which is not reliable evidence of printed text.
    printed = re.search(r'[+\-=0-9]',line['text']) or re.search(r'[A-Za-z]{2}',line['text'])
    return bool(printed and line['confidence']>=.5 and intersection>=b['width']*b['height']*.65)


def _diagram_operands(objects, symbols):
    candidates=[]
    for symbol in symbols:
        if symbol['kind'] not in ('plus','minus'):
            continue
        sx,sy=_center(symbol)
        left=[o for o in objects if _center(o)[0]<sx]
        right=[o for o in objects if _center(o)[0]>sx]
        if not left or not right:
            continue
        # A diagram's operation sits between its groups, within their vertical
        # span. An answer underline or a heading separator is not subtraction.
        y0=min(o['bbox']['y'] for o in objects)
        y1=max(o['bbox']['y']+o['bbox']['height'] for o in objects)
        if sy<y0-12 or sy>y1+12:
            continue
        if any(o['bbox']['x']<sx<o['bbox']['x']+o['bbox']['width'] for o in objects):
            continue
        candidates.append((symbol,len(left),len(right)))
    if len(candidates)>1:
        raise WorksheetUnclear('More than one diagram operation is visible. Crop one question and retry.')
    return candidates[0] if candidates else None


def interpret_evidence(ocr, diagram, size):
    """Combine OCR and picture evidence, never execute worksheet instructions."""
    text=_normalize_text(ocr.get('text',''))
    objects=[o for o in diagram.get('objects',[]) if not o.get('requires_text_check')
             or not any(_overlap_object_text(o,line,size) for line in ocr.get('lines',[]))]
    symbols=diagram.get('symbols',[])
    uncertainty=[r for r in diagram.get('uncertain_regions',[]) if not any(
        _overlap_object_text(r,line,size) for line in ocr.get('lines',[]))]
    if uncertainty:
        raise WorksheetUnclear('Some pictured marks or objects are unclear. Crop a clean single question; overlapping or crossed-out objects need review.')
    if len(objects)>20:
        raise WorksheetUnclear('There are too many pictured objects for one supported question. Crop one exercise.')
    if any('background texture' in w or 'too dense' in w or 'Too many' in w for w in diagram.get('warnings',[])):
        raise WorksheetUnclear('This image is too dense or textured for the local worksheet reader. Crop a clear single question on a light background.')
    sizes=sorted(min(o['bbox']['width'],o['bbox']['height']) for o in objects)
    minimum_side=sizes[len(sizes)//2]*.8 if sizes else min(size)*.04
    unexplained=[r for r in diagram.get('text_candidates',[]) if min(r['bbox']['width'],r['bbox']['height'])>=minimum_side
                 and (objects or r['bbox']['width']*r['bbox']['height']>=size[0]*size[1]*.004)
                 and not any(_overlap_object_text(r,line,size) for line in ocr.get('lines',[]))]
    if unexplained:
        raise WorksheetUnclear('Some substantial pictured marks are not recognized as text or separate objects. Please crop or clarify the diagram.')
    if re.search(r'\d+\s*[×÷*/]\s*\d+',text):
        raise WorksheetUnclear('This worksheet uses multiplication or division. This reader currently supports addition, subtraction, counting, and shapes.')
    if re.search(r'\d+\.\d+',text):
        raise WorksheetUnclear('This reader supports whole numbers from 0 to 10.')
    # A prose heading can end in '?' immediately before a diagram's '+'; it
    # is not a missing operand. Numeric givens distinguish ? + 3 = 5 from
    # 'How many dots altogether?' followed by a pure dot diagram.
    if re.search(r'\d',text) and re.search(r'(?:\?|_+)\s*[+\-]|[+\-]\s*(?:\?|_+)\s*=',text):
        raise WorksheetUnclear('A missing operand needs a different lesson; this reader currently solves an unknown total or remainder.')

    # Extract complete operand pairs, preserving the location of any unknown.
    # Never convert ? + 3 = 5 into the result-unknown question 3 + 5.
    expression=re.compile(r'(?<![\w.])(?P<a>\d{1,2})\s*(?P<op>[+\-])\s*(?P<b>\d{1,2})(?![\d.])(?:\s*=\s*(?P<result>\?|_+|\d{1,2}))?')
    matches=list(expression.finditer(text))
    if len(matches)>1:
        raise WorksheetUnclear('More than one arithmetic question is visible. Crop one question and retry.')
    excluded=[o for o in diagram.get('objects',[]) if o not in objects]
    if not matches and any(_overlap_object_text(o,line,size) and re.fullmatch(r'[0-9\s]+',line['text'].strip())
                           for o in excluded for line in ocr.get('lines',[])):
        raise WorksheetUnclear('An outlined counter could also be a printed digit. The picture needs review so that no objects are silently omitted.')
    diagram_pair=_diagram_operands(objects,symbols) if objects else None
    if matches:
        match=matches[0]
        if any(line['confidence']<.65 and re.search(r'\d',line['text']) for line in ocr.get('lines',[])):
            raise WorksheetUnclear('The printed numbers are not clear enough. Use a sharper worksheet crop.')
        if re.search(r'(?:\?|_+)\s*[+\-]|[+\-]\s*(?:\?|_+)\s*=',text):
            raise WorksheetUnclear('A missing addend or subtrahend needs a different lesson; this reader currently solves an unknown total or remainder.')
        a,b=int(match['a']),int(match['b'])
        outside=text[:match.start()]+' '+text[match.end():]
        outside=re.sub(r'^\s*\d+[.)]\s*','',outside)
        if re.search(r'\d',outside):
            raise WorksheetUnclear('Additional printed numbers are outside the arithmetic question. Crop one clear question without unrelated instructions.')
        question=f"What is {a} {match['op']} {b}?"
        spec=plan_question(question)
        result=match['result']
        if result and result.isdigit() and int(result)!=spec['answer']:
            raise WorksheetUnclear('The printed answer disagrees with the arithmetic. Please review the worksheet instead of generating a lesson.')
        if text.count('+')+text.count('-')>1:
            raise WorksheetUnclear('Additional operation signs are visible. Crop one arithmetic question.')
        if objects:
            if diagram_pair:
                symbol,left,right=diagram_pair
                wanted='plus' if match['op']=='+' else 'minus'
                if symbol['kind']!=wanted or (left,right)!=(a,b):
                    raise WorksheetUnclear('The pictured groups disagree with the printed numbers or operation.')
            elif len(objects) not in ({a+b} if match['op']=='+' else {a,a-b}):
                raise WorksheetUnclear('The pictured objects do not match the printed arithmetic.')
        return {'question':question,'spec':spec,'method':'printed_arithmetic','objects':objects,
                'reason':'A complete printed arithmetic expression was read and its answer checked.'}

    if diagram_pair:
        if re.search(r'\b(?:red|blue|green|yellow|black|white|orange|purple|pink|left|right|top|bottom|big|small|large|crossed|uncrossed|only|except|not)\b',text,re.I):
            raise WorksheetUnclear('This question selects objects by color, size, position, or marks. That counting target needs review or a tighter crop.')
        symbol,a,b=diagram_pair
        # Diagram layout must not override a contradictory written task, even
        # when OCR spelled the numbers out rather than producing digits.
        try:
            written=plan_question(text)
        except UnsupportedQuestion:
            written=None
        expected_type='addition' if symbol['kind']=='plus' else 'subtraction'
        if written and written['type'] in ('addition','subtraction'):
            if (written['type'],written['a'],written['b'])!=(expected_type,a,b):
                raise WorksheetUnclear('The pictured groups disagree with the written arithmetic question.')
        elif written and written['type']=='counting':
            expected_count=a+b if expected_type=='addition' else a-b
            if written['answer']!=expected_count:
                raise WorksheetUnclear('The printed count disagrees with the pictured arithmetic.')
        else:
            numbered_text=re.sub(r'^\s*\d+[.)]\s*','',text)
            if re.search(r'\d',numbered_text):
                raise WorksheetUnclear('Additional printed numbers are outside a complete arithmetic question. Crop one clear question.')
        illustrations=(diagram.get('repeated_illustrations_verified') is True
                       and all(o['shape']=='illustration' for o in objects))
        if not illustrations and any(o['shape']!='circle' for o in objects):
            raise WorksheetUnclear('This arithmetic picture includes mixed or unsupported object shapes. Use a clean dot worksheet or type the question.')
        op='+' if symbol['kind']=='plus' else '-'
        question=f'What is {a} {op} {b}?'
        spec=plan_question(question)
        # Other operation signs through the diagram indicate multiple exercises.
        relevant=[s for s in symbols if s['kind'] in ('plus','minus')
                  and min(_center(o)[0] for o in objects)<_center(s)[0]<max(_center(o)[0] for o in objects)]
        if len(relevant)>1:
            raise WorksheetUnclear('Multiple possible operations are visible between the pictured objects.')
        noun='matching pictures' if illustrations else 'circles'
        return {'question':question,'spec':spec,'method':'illustration_groups' if illustrations else 'dot_groups','objects':objects,
                'reason':f'The groups on either side of the operation contain {a} and {b} {noun}.'}

    if re.search(r'(?:\?|_+)\s*[+\-]|[+\-]\s*(?:\?|_+)\s*=',text):
        raise WorksheetUnclear('The picture contains a missing operand. This reader currently solves an unknown total or remainder.')

    # Named text-only questions can reuse the existing bounded language parser.
    try:
        spec=plan_question(text)
    except UnsupportedQuestion:
        spec=None
    if spec:
        if spec['type']=='counting' and objects and len(objects)!=spec['answer']:
            raise WorksheetUnclear('The printed count disagrees with the number of detected objects.')
        if spec['type']=='shape' and objects:
            if len(objects)!=1 or objects[0]['shape']!=spec['shape']:
                raise WorksheetUnclear('The drawn shape disagrees with the shape named in the question.')
        return {'question':spec['question'],'spec':spec,'method':'printed_question','objects':objects,
                'reason':'The printed question matches a supported lesson format.'}

    if re.search(r'\b(?:red|blue|green|yellow|black|white|orange|purple|pink|left|right|top|bottom|big|small|large|crossed|uncrossed|only|except|not|curved)\b',text,re.I):
        raise WorksheetUnclear('The instructions select a color, size, position, mark, or curved edge that needs a different interpretation. Crop or type the exact supported question.')
    instruction_lines=[_normalize_text(line['text']).lower().strip(' .?!:') for line in ocr.get('lines',[])]
    if not instruction_lines and text:
        instruction_lines=[text.lower().strip(' .?!:')]
    sides_prompt=r'how many(?: straight)? sides(?: does (?:this|the) shape have)?'
    name_prompt=r'(?:what shape is this|name (?:the |this )?shape|identify (?:the |this )?shape)'
    shape_prompt=next((s for s in instruction_lines if re.fullmatch(sides_prompt,s) or re.fullmatch(name_prompt,s)),None)
    if shape_prompt:
        if len(objects)!=1 or objects[0]['shape'] not in ('circle','triangle','square','rectangle'):
            raise WorksheetUnclear('A shape question must show one clearly recognized circle, triangle, square, or rectangle.')
        shape=objects[0]['shape']
        question=f'How many sides does a {shape} have?' if re.fullmatch(sides_prompt,shape_prompt) else f'Show me a {shape}.'
        return {'question':question,'spec':plan_question(question),'method':'drawn_shape','objects':objects,
                'reason':f'One {shape} was recognized, together with a printed shape question.'}

    neutral_count=r'(?:count(?: the)? (?:dots|circles|counters|objects)|how many (?:dots|circles|counters|objects)(?: are there| altogether| in all)?)'
    if any(re.fullmatch(neutral_count,s) for s in instruction_lines):
        if not objects or any(o['shape']!='circle' for o in objects):
            raise WorksheetUnclear('The counting question needs clearly separated circular dots; no reliable dot group was found.')
        if any(s['kind']=='plus' for s in symbols):
            raise WorksheetUnclear('An addition sign is present but the groups cannot be established.')
        diameters=[max(o['bbox']['width'],o['bbox']['height']) for o in objects]
        if max(diameters)>min(diameters)*1.75:
            raise WorksheetUnclear('Very different dot sizes may include decorations. Crop the intended group or type the count instead of choosing a counting target automatically.')
        question=f'Count {len(objects)} dots.'
        return {'question':question,'spec':plan_question(question),'method':'counted_dots','objects':objects,
                'reason':f'The printed counting instruction accompanies {len(objects)} detected circles.'}
    raise WorksheetUnclear('I could not identify one supported question. Crop a clear printed arithmetic problem, dot diagram, or single shape question; otherwise type the question.')


def read_worksheet(path, *, crop=None, ocr_reader=recognize_text, reader='rules', model_path=None):
    if reader not in ('rules','local-vision','gemini'):
        raise ValueError('Choose the local-vision, rules, or optional gemini worksheet reader.')
    source=Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f'Worksheet image not found: {source}')
    if reader=='gemini' and source.stat().st_size>10*1024*1024:
        raise WorksheetUnclear('Use a PNG or JPEG worksheet image no larger than 10 MB for Gemini.')
    try:
        with Image.open(source) as opened:
            if reader=='gemini' and (opened.format not in ('PNG','JPEG')
                    or opened.width*opened.height>20_000_000):
                raise WorksheetUnclear('Use one PNG or JPEG worksheet image no larger than 20 megapixels for Gemini.')
            if getattr(opened,'n_frames',1)>1:
                raise WorksheetUnclear('Use one PNG or JPEG worksheet image, not multiple frames or pages.')
            image=ImageOps.exif_transpose(opened).convert('RGBA')
            white=Image.new('RGBA',image.size,'white')
            white.alpha_composite(image)
            image=white.convert('RGB')
    except (UnidentifiedImageError,OSError) as exc:
        raise WorksheetUnclear('Could not open this picture. Export a single worksheet crop as PNG or JPEG.') from exc
    if min(image.size)<40:
        raise WorksheetUnclear('The worksheet crop is too small to read. Use a clearer image.')
    if crop:
        x,y,w,h=crop
        if min(x,y)<0 or min(w,h)<=0 or x+w>image.width or y+h>image.height:
            raise ValueError('--crop must be X Y WIDTH HEIGHT within the oriented image.')
        image=image.crop((x,y,x+w,y+h))
    if max(image.size)>2200:
        image.thumbnail((2200,2200),Image.Resampling.LANCZOS)
    with tempfile.TemporaryDirectory(prefix='worksheet-local-') as tmp:
        prepared=Path(tmp)/'worksheet.png'
        image.save(prepared)
        if reader in ('local-vision','gemini'):
            if reader=='gemini':
                from .gemini_vision import read_gemini_vision
                interpretation=read_gemini_vision(prepared)
            else:
                from .local_vision import read_local_vision
                interpretation=read_local_vision(prepared,model_path=model_path)
            # Repetition matching is optional artwork extraction, not a gate on
            # the model's understanding or a replacement for its counted groups.
            diagram={'objects':[],'symbols':[],'groups':[],'uncertain_regions':[],
                     'text_candidates':[],'warnings':[]}
            from .worksheet_illustrations import analyze_illustrations
            try:
                artwork=analyze_illustrations(image)
            except ValueError:
                artwork=None
            spec=interpretation['spec']
            if (artwork and spec['type'] in ('addition','subtraction')
                    and (artwork['operation'],artwork['left_count'],artwork['right_count'])
                    ==(spec['type'],spec['a'],spec['b'])):
                diagram=artwork
                interpretation['objects']=artwork['objects']
                interpretation['artwork_source']='Source cutouts independently matched the model counts.'
            else:
                interpretation['artwork_source']='Generic dots represent the pictured objects; model reading is independent of cutout extraction.'
                if spec['type']!='shape':
                    spec['steps'][0]['text']="Let's use dots to stand for the pictured objects."
                    spec['object_label']='dot'
                    spec['object_label_plural']='dots'
            return {**interpretation,'source_image':str(source),'image_size':list(image.size),
                    'crop':list(crop) if crop else None,'diagram':diagram,'image':image,
                    'ocr':{'engine':('Text and image interpreted together by Google Gemini'
                                     if reader=='gemini' else 'Text and image interpreted together by the local vision model'),
                           'text':interpretation['model_interpretation']['task_text'],'lines':[]}}
        ocr=ocr_reader(prepared)
    diagram=analyze_diagram(image)
    try:
        try:
            interpretation=interpret_evidence(ocr,diagram,image.size)
        except (WorksheetUnclear,UnsupportedQuestion) as original_error:
            # A separate matcher may establish repeated illustrations. It must
            # still pass the same wording, operand, and arithmetic checks.
            from .worksheet_illustrations import analyze_illustrations
            try:
                illustrations=analyze_illustrations(image,ocr=ocr,diagram=diagram)
            except ValueError as exc:
                raise WorksheetUnclear(str(exc)) from exc
            if illustrations is None:
                raise original_error
            interpretation=interpret_evidence(ocr,illustrations,image.size)
            diagram=illustrations
    except UnsupportedQuestion as exc:
        raise WorksheetUnclear(str(exc)) from exc
    return {**interpretation,'source_image':str(source),'image_size':list(image.size),'crop':list(crop) if crop else None,
            'ocr':ocr,'diagram':diagram,'reader':'local Apple Vision + geometry and repeated-illustration analysis','image':image}


def save_interpretation(result, out):
    out=Path(out).expanduser().resolve()
    out.mkdir(parents=True,exist_ok=True)
    if result['objects'] and all(obj['shape']=='illustration' for obj in result['objects']):
        from .generate import prepare_object_spec
        sprites=out/'object_sprites'
        sprites.mkdir(exist_ok=True)
        objects=result['objects']
        if result['spec']['type']=='subtraction':
            objects=objects[:result['spec']['a']]
        paths=[]
        for index,obj in enumerate(objects):
            b=obj['bbox'];x,y,w,h=(b[key] for key in ('x','y','width','height'))
            sprite=sprites/f'{index:02d}.png'
            result['image'].crop((x,y,x+w,y+h)).save(sprite)
            paths.append(str(sprite))
        # The model's proposed semantic name remains visible in the review
        # evidence. A small local model may count correctly but misname artwork.
        label,plural='picture','pictures'
        result['spec']=prepare_object_spec({**result['spec'],'object_images':paths,'object_label':label,
                                            'object_label_plural':plural,'visual_source':'worksheet_illustrations'})
    result['image'].save(out/'worksheet_input.png')
    annotated=result['image'].copy()
    d=ImageDraw.Draw(annotated)
    for i,obj in enumerate(result['objects'],1):
        b=obj['bbox'];x,y,w,h=b['x'],b['y'],b['width'],b['height']
        d.rectangle((x-3,y-3,x+w+3,y+h+3),outline='#198474',width=3)
        d.text((x,max(0,y-17)),f"{i}: {obj['shape']}",fill='#155B50')
    annotated.save(out/'worksheet_annotated.png')
    serializable={k:v for k,v in result.items() if k not in ('image','spec')}
    serializable['answer']=result['spec']['answer']
    (out/'worksheet_reading.json').write_text(json.dumps(serializable,indent=2,ensure_ascii=False)+'\n')
    (out/'extracted_text.txt').write_text(result['ocr']['text']+'\n')
    if 'raw_response' in result:
        (out/'model_response.txt').write_text(result['raw_response']+'\n')
        (out/'model_interpretation.json').write_text(json.dumps(result['model_interpretation'],indent=2)+'\n')
    (out/'lesson.json').write_text(json.dumps(result['spec'],indent=2,ensure_ascii=False)+'\n')
    from .explain import explanation_text
    (out/'explanation.txt').write_text(explanation_text(result['spec']))
    return {'question':result['question'],'answer':result['spec']['answer'],'method':result['method'],
            'reading':str(out/'worksheet_reading.json'),'annotated_picture':str(out/'worksheet_annotated.png'),
            'explanation':str(out/'explanation.txt')}
