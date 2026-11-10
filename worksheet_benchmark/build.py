"""Build source-backed student-only images, private labels and a review catalogue."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import re
import uuid

import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .curation import ARITHMETIC, IM_TASKS, REASONING_2025, REASONING_2026
from .download import CACHE, ROOT, SOURCES

DESTINATION = ROOT / 'benchmarks/worksheet_v1'
NAMESPACE = uuid.UUID('77ab6c30-84f9-49c2-88ee-048ba06f6734')
SECTION_END = re.compile(r'^(?:IM Commentary|Commentary|Solutions?(?:\s+[0-9: ].*)?|Edit this solution)$', re.I)

def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def lines(page):
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            yield {**line, 'text':''.join(span['text'] for span in line['spans']).strip()}

def render_clip(page, clip):
    if clip.height < 8 or clip.width < 20:
        raise ValueError('A selected source region is empty.')
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
    return Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)

def gov_question_regions(document, *, arithmetic=False):
    regions = {}
    for page_index, page in enumerate(document):
        markers = [line for line in lines(page) if re.fullmatch(r'\d{1,2}', line['text'])
                   and line['bbox'][0] < 65 and 55 < line['bbox'][1] < 760
                   and any(('Bd' in span['font'] or '-Hv' in span['font']) for span in line['spans'])]
        markers.sort(key=lambda line:line['bbox'][1])
        for index, marker in enumerate(markers):
            number = int(marker['text'])
            top = marker['bbox'][1] - 6
            bottom = markers[index+1]['bbox'][1]-25 if index+1 < len(markers) else 780
            marks = [line['bbox'][3] for line in lines(page) if re.fullmatch(r'[12] marks?',line['text'])
                     and top < line['bbox'][1] < bottom]
            if marks:
                bottom = min(bottom, max(marks)+20)
            if arithmetic:
                # Scratch grids are not part of the printed arithmetic question.
                bottom = min(bottom, top+155)
            if number in regions:
                raise ValueError(f'Duplicate source question marker {number}.')
            regions[number] = (page_index, fitz.Rect(28, max(55,top), 567, bottom))
    return regions

def question_text(page, clip):
    # Keep full diagrams in the image, but exclude the left question-number
    # column and right marking labels from partial text-token targets.
    return '\n'.join(line['text'] for line in lines(page)
                     if fitz.Rect(line['bbox']).intersects(clip)
                     and line['bbox'][0] >= 70
                     and not re.fullmatch(r'[12] marks?',line['text']))

def student_task(document):
    parts, text, crops = [], [], []
    active = False
    for page_index, page in enumerate(document):
        page_lines = list(lines(page))
        task = [line for line in page_lines if line['text'] == 'Task']
        if not active:
            if not task:
                continue
            top = task[0]['bbox'][3]+7
            active = True
        else:
            top = 77
        endings = [line['bbox'][1]-5 for line in page_lines
                   if SECTION_END.fullmatch(line['text']) and line['bbox'][1] >= 70]
        for block in page.get_text('blocks'):
            if 'Typeset ' in block[4]:
                endings.append(block[1]-8)
        stop = bool(endings)
        bottom = min([725,*endings])
        if bottom > top+10:
            clip = fitz.Rect(66, top, 544, bottom)
            body = page.get_text('text', clip=clip, sort=True).strip()
            part=render_clip(page,clip)
            # Some student continuations contain only raster diagrams. Test the
            # pixels rather than silently dropping a page with no text layer.
            ink=ImageOps.invert(part.convert('L')).point(lambda value:255 if value>25 else 0).getbbox()
            if ink:
                x0,y0,x1,y1=ink
                part=part.crop((max(0,x0-12),max(0,y0-12),min(part.width,x1+12),min(part.height,y1+12)))
                parts.append(part); text.append(body)
                crops.append({'pdf_page':page_index+1,'crop_points':list(clip)})
        if stop:
            break
    if not parts or not active:
        raise ValueError('No complete student task was located.')
    width=max(part.width for part in parts)
    combined=Image.new('RGB',(width,sum(part.height for part in parts)+16*(len(parts)-1)),'white')
    y=0
    for part in parts:
        combined.paste(part,((width-part.width)//2,y));y+=part.height+16
    return combined, '\n'.join(text), crops

def printed_numbers(text):
    # Partial gold: PDF selectable text only. Diagram/raster numbers may be
    # additional valid predictions; scoring must not count them as false positives.
    clean=re.sub(r'\b[12] marks?\b','',text)
    return re.findall(r'(?<![\d.])\d+(?:\.\d+)?(?![\d.])',clean)

def compose_gold(topic, form, text, *, expression=None, answer=None, context=False):
    source_text = text.translate(str.maketrans({'|':'−','{':'×','}':'÷'}))
    numbers=printed_numbers(source_text)
    if expression:
        numbers=re.findall(r'\d+',expression)
    symbols=sorted(set(re.findall(r'[+*/=<>-]',expression))) if expression else None
    if expression and 'of' in expression:
        symbols=[symbol for symbol in symbols if symbol!='/']  # printed fraction bar is not a division sign
    current={'decision':'reject','reason':'requires_new_lesson_or_question_selection','spec':None}
    if context:
        current['reason']='missing_aural_question_context'
    if expression=='6-2=?':
        current={'decision':'accept','reason':'supported_single_question','spec':{'type':'subtraction','a':6,'b':2}}
    return {'topic':topic,'visual_form':form,'printed_numbers':numbers,
            'numeric_label_scope':'complete_equation' if expression else 'selectable_pdf_text_only; extra diagram numbers are not false positives',
            'expression':expression,'operator_symbols':symbols,'reference_answer':answer,
            'question_text':source_text,'needs_more_context':context,
            'current_app':current,'annotation_source':'official source text, curriculum tags and curator-selected visual form; not model predictions',
            'independent_teacher_review':False}

def save_case(destination, rows, image, source_key, source_file, source_question, gold, crops, *, split, difficulty):
    source=SOURCES[source_key]
    identifier='w_'+uuid.uuid5(NAMESPACE,f'{source_key}:{source_file.name}:{source_question}').hex[:14]
    image=image.convert('RGB')
    if max(image.size)>1600:
        image.thumbnail((1600,1600),Image.Resampling.LANCZOS)
    path=destination/'images'/f'{identifier}.png'
    image.save(path,format='PNG')  # no source PDF metadata, EXIF, titles or labels
    entry={'id':identifier,'image':f'images/{path.name}','sha256':digest(path),
           'width':image.width,'height':image.height,'base_id':identifier,'split':split,
           'source_kind':'web_pdf_excerpt','real_phone_photo':False,'condition':'original_web_render',
           'source':{'key':source_key,'url':source['url'],'landing':source['landing'],
                     'publisher':source['publisher'],'license':source['license'],
                     'native_grade':source['native_grade'],'pdf_member':source_file.name,
                     'pdf_sha256':digest(source_file),'question':str(source_question),'crops':crops},
           'difficulty':difficulty,'expected':gold}
    rows.append(entry)
    return entry

def build(destination=DESTINATION):
    destination=Path(destination);(destination/'images').mkdir(parents=True,exist_ok=True)
    rows=[]
    for source_key,annotations,year in [('sta_2026_reasoning',REASONING_2026,2026),('sta_2025_reasoning',REASONING_2025,2025)]:
        source_file=CACHE/SOURCES[source_key]['file'];document=fitz.open(source_file)
        regions=gov_question_regions(document)
        for question,(topic,form,answer_page) in annotations.items():
            page_index,clip=regions[question];page=document[page_index]
            text=question_text(page,clip)
            gold=compose_gold(topic,form,text)
            gold['answer_reference']={'source_key':f'sta_{year}_marks','url':SOURCES[f'sta_{year}_marks']['url'],
                                      'pdf_page':answer_page,'question':question,'paper':2,
                                      'note':'Source mark-scheme diagram/text; no automated answer equivalence score is claimed.'}
            save_case(destination,rows,render_clip(page,clip),source_key,source_file,question,gold,
                      [{'pdf_page':page_index+1,'crop_points':list(clip)}],
                      split='test' if year==2025 else 'development',
                      difficulty={'level':'introductory' if question<=12 else 'core' if question<=23 else 'stretch',
                                  'basis':'relative source item order; not a calibrated US grade difficulty'})
    source_key='sta_2026_arithmetic';source_file=CACHE/SOURCES[source_key]['file'];document=fitz.open(source_file)
    regions=gov_question_regions(document,arithmetic=True)
    for question,expression,answer,topic in ARITHMETIC:
        page_index,clip=(2,fitz.Rect(74,145,551,230)) if question=='P' else regions[question]
        page=document[page_index];gold=compose_gold(topic,'equation',question_text(page,clip),expression=expression,answer=answer)
        gold['answer_reference']={'source_key':'sta_2026_marks','url':SOURCES['sta_2026_marks']['url'],'pdf_page':9,'question':str(question),'paper':1}
        save_case(destination,rows,render_clip(page,clip),source_key,source_file,question,gold,
                  [{'pdf_page':page_index+1,'crop_points':list(clip)}],split='development',
                  difficulty={'level':'introductory' if question=='P' or question<=8 else 'core' if question<=17 else 'stretch',
                              'basis':'relative source item order; not a calibrated US grade difficulty'})
    # This actual aural practice page contains ladders but no written question.
    # It is a deliberate context-refusal control, not a counting exercise.
    source_key='sta_2026_reasoning';source_file=CACHE/SOURCES[source_key]['file'];document=fitz.open(source_file)
    clip=fitz.Rect(90,105,490,465);page=document[2]
    save_case(destination,rows,render_clip(page,clip),source_key,source_file,'P',
              compose_gold('context_needed','aural_only_illustration',page.get_text('text',clip=clip,sort=True),context=True),
              [{'pdf_page':3,'crop_points':list(clip)}],split='development',
              difficulty={'level':'context_required','basis':'oral question is absent from photographed material'})
    for index,(grade,filename,topic,form) in enumerate(IM_TASKS):
        source_key=f'im_{grade.lower()}';source_file=CACHE/f'im_grade_{grade}'/filename
        document=fitz.open(source_file);image,text,crops=student_task(document)
        gold=compose_gold(topic,form,text)
        gold['answer_reference']={'source_key':source_key,'pdf_member':filename,
                                  'note':'Open or multi-response task. Inspect source commentary/solutions separately; not scored as a single numeric answer.'}
        gold['statement_page_count']=len(crops)
        save_case(destination,rows,image,source_key,source_file,'student_task',gold,crops,
                  split='test' if index in [0,3,7,9,12,15,18] else 'development',
                  difficulty={'level':'unrated','basis':'official source grade retained; no invented difficulty calibration'})
    rows.sort(key=lambda case:case['id'])
    if len(rows)!=100:
        raise ValueError(f'Expected exactly 100 primary source questions, got {len(rows)}.')
    identities={case['id'] for case in rows};hashes={case['sha256'] for case in rows}
    if len(identities)!=100 or len(hashes)!=100:
        raise ValueError('Duplicate identity or identical image in primary corpus.')
    manifest={'schema_version':1,'dataset_id':'worksheet-web-v1','created_at_utc':datetime.now(timezone.utc).isoformat(),
              'purpose':'Label-blind reading evaluation and curriculum coverage discovery, not a training set or learning-outcomes study.',
              'source_population':'80 official England KS1 test items and 20 US K/1/2 Illustrative Mathematics tasks; convenience sample from two publishers.',
              'real_phone_photo_count':0,'annotation_limitations':['Labels are source-backed/curated, not independently double-annotated.',
              'Non-equation numeric labels are partial selectable-text recall targets; raster/diagram counts are not exhaustively labelled.',
              'Official native grade systems are not equated. Most broad tasks exceed the current bounded video renderer.',
              'Open/multi-response tasks retain answer references; no generic exact-answer score is fabricated.',
              'Public source tasks may have been present in model pretraining; not a contamination-free benchmark.'],
              'split_policy':'Whole source PDF is assigned to one split. No page or condition variant may cross splits.',
              'input_policy':'Only inputs.json image bytes and one fixed generic prompt may reach inference. Labels, source filenames, grades, answer references and expected quantities must stay outside model context.',
              'commercial_product_use':False,'cases':rows}
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    public={'schema_version':1,'dataset_id':manifest['dataset_id'],'cases':[{k:case[k] for k in ('id','image','sha256')} for case in rows]}
    (destination/'inputs.json').write_text(json.dumps(public,indent=2)+'\n')
    for split in ['development','test']:
        selected={case['id'] for case in rows if case['split']==split}
        split_inputs={**public,'cases':[case for case in public['cases'] if case['id'] in selected]}
        (destination/f'inputs_{split}.json').write_text(json.dumps(split_inputs,indent=2)+'\n')
    with (destination/'labels.csv').open('w',newline='') as target:
        writer=csv.DictWriter(target,fieldnames=['id','split','topic','visual_form','native_grade','difficulty','source_question','source_url','license','expression','reference_answer','image'])
        writer.writeheader()
        for case in rows:
            writer.writerow({'id':case['id'],'split':case['split'],'topic':case['expected']['topic'],
                'visual_form':case['expected']['visual_form'],'native_grade':case['source']['native_grade'],
                'difficulty':case['difficulty']['level'],'source_question':case['source']['question'],
                'source_url':case['source']['url'],'license':case['source']['license'],
                'expression':case['expected']['expression'],'reference_answer':case['expected']['reference_answer'],'image':case['image']})
    attribution=['Worksheet web corpus: local academic capstone evaluation only. Do not deploy this mixed-license corpus into the commercial child-facing product.',
                 '80 items: Contains material developed by the Standards and Testing Agency for 2025 and 2026 national curriculum assessments and licensed under Open Government Licence v3.0.',
                 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/',
                 '20 tasks: Illustrative Mathematics, CC BY-NC-SA 4.0. Adaptations: student-only cropping, page stitching and rasterization; logos, commentary and solutions excluded from model inputs.',
                 'https://creativecommons.org/licenses/by-nc-sa/4.0/',
                 'Source title, URL/archive member, source SHA256 and original PDF page/crop are retained per case.']
    (destination/'ATTRIBUTION.txt').write_text('\n\n'.join(attribution)+'\n')
    (destination/'README.txt').write_text(Path(__file__).with_name('README.md').read_text())
    summary={'images':len(rows),'distinct_image_hashes':len(hashes),'source_documents':len({case['source']['pdf_sha256'] for case in rows}),
             'topics':dict(Counter(case['expected']['topic'] for case in rows)),
             'forms':dict(Counter(case['expected']['visual_form'] for case in rows)),
             'splits':dict(Counter(case['split'] for case in rows)),
             'native_grades':dict(Counter(case['source']['native_grade'] for case in rows)),
             'real_phone_photos':0,'equations_with_exact_gold':len(ARITHMETIC)}
    (destination/'dataset_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    make_contacts(destination,rows)
    from .review import write_review
    write_review(destination,manifest)
    return manifest

def make_contacts(destination, rows):
    try:font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',16)
    except OSError:font=ImageFont.load_default(size=16)
    for start in range(0,len(rows),20):
        sheet=Image.new('RGB',(1600,1500),'#eef1f5');draw=ImageDraw.Draw(sheet)
        for offset,case in enumerate(rows[start:start+20]):
            x=(offset%4)*400;y=(offset//4)*300
            image=Image.open(destination/case['image']);image.thumbnail((380,245))
            sheet.paste(image,(x+(400-image.width)//2,y+8))
            label=f"{case['id'][-6:]} | {case['expected']['topic']}"
            draw.text((x+10,y+259),label,font=font,fill='#172b49')
            draw.text((x+10,y+278),f"{case['source']['key']} Q{case['source']['question']}",font=font,fill='#52657b')
        sheet.save(destination/f'contact_{start//20+1}.jpg',quality=92)

if __name__=='__main__':
    result=build();print(json.dumps({'dataset':str(DESTINATION),'images':len(result['cases'])}))
