"""Paired synthetic stress images, never called real phone/child handwriting."""
import copy
import hashlib
import json
from pathlib import Path
import re
import uuid

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from .build import DESTINATION, NAMESPACE, make_contacts

def perspective(image):
    image=ImageOps.expand(image,border=35,fill='white')
    w,h=image.size
    target=[(23,5),(w-9,25),(w-33,h-9),(5,h-25)]
    source=[(0,0),(w,0),(w,h),(0,h)]
    a=[];b=[]
    for (x,y),(u,v) in zip(target,source):
        a.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]]);b.extend([u,v])
    coefficients=np.linalg.solve(np.array(a),np.array(b))
    return image.transform(image.size,Image.Transform.PERSPECTIVE,coefficients,Image.Resampling.BICUBIC,fillcolor='white')

def shadow_blur(image):
    pixels=np.asarray(image).astype(float)
    y,x=np.mgrid[0:image.height,0:image.width]
    shade=.46+.54*(x/max(1,image.width-1))
    shade=shade*(.92+.08*y/max(1,image.height-1))
    return Image.fromarray(np.uint8(np.clip(pixels*shade[:,:,None],0,255))).filter(ImageFilter.GaussianBlur(.8))

def handwriting(expression):
    # Rendered font imitation, not handwriting captured from a child.
    font=ImageFont.truetype('/System/Library/Fonts/MarkerFelt.ttc',68)
    image=Image.new('RGB',(1100,230),'#fffdf7');draw=ImageDraw.Draw(image)
    x=48
    for token in re.findall(r'\d+|[?+*/=\-]',expression):
        if token=='?':
            draw.rounded_rectangle((x,65,x+100,149),radius=3,outline='#526a86',width=3)
            x+=125
        elif token in ('*','/'):
            if token=='*':
                draw.line((x+4,91,x+38,128),fill='#24334c',width=5)
                draw.line((x+38,90,x+5,129),fill='#24334c',width=5)
            else:
                draw.line((x+1,109,x+43,110),fill='#24334c',width=5)
                draw.ellipse((x+18,87,x+26,95),fill='#24334c')
                draw.ellipse((x+18,125,x+26,133),fill='#24334c')
            x+=65
        else:
            text=token
            draw.text((x,65),text,font=font,fill='#24334c')
            x+=draw.textlength(text,font=font)+23
    return image

def build_variants(destination=DESTINATION):
    destination=Path(destination);manifest=json.loads((destination/'manifest.json').read_text())
    chosen={'P','1','2','4','6','14','19','21','23','24'}
    bases=[c for c in manifest['cases'] if c['source']['key']=='sta_2026_arithmetic' and c['source']['question'] in chosen]
    assert len(bases)==10
    folder=destination/'stress';(folder/'images').mkdir(parents=True,exist_ok=True);rows=[]
    for base in bases:
        original=Image.open(destination/base['image']).convert('RGB')
        for condition,render in [('synthetic_perspective',lambda:perspective(original)),
                                 ('synthetic_shadow_blur',lambda:shadow_blur(original)),
                                 ('simulated_handwriting_font',lambda:handwriting(base['expected']['expression']))]:
            row=copy.deepcopy(base)
            identifier='v_'+uuid.uuid5(NAMESPACE,base['id']+':'+condition).hex[:14]
            image=render();path=folder/'images'/f'{identifier}.png';image.save(path)
            row.update(id=identifier,image='images/'+path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       width=image.width,height=image.height,base_id=base['id'],condition=condition,
                       source_kind='synthetic_derivative',real_phone_photo=False)
            row['transformation']={'deterministic':True,'implementation':'worksheet_benchmark.variants',
                                   'base_image_sha256':base['sha256'],'handwriting_is_real':False}
            rows.append(row)
    rows.sort(key=lambda c:c['id'])
    result={**manifest,'dataset_id':'worksheet-stress-v1','cases':rows,'source_population':'30 synthetic conditions derived from 10 development arithmetic items; no new independent questions.',
            'annotation_limitations':manifest['annotation_limitations']+['All stress variants are development-only, synthetic and paired to 10 original questions. Not real phone/handwriting generalization.']}
    (folder/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (folder/'inputs.json').write_text(json.dumps({'dataset_id':result['dataset_id'],'schema_version':1,
        'cases':[{k:c[k] for k in ['id','image','sha256']} for c in rows]},indent=2)+'\n')
    make_contacts(folder,rows)
    return result

if __name__=='__main__':print(json.dumps({'stress_images':len(build_variants()['cases']),'independent_base_questions':10,'real_phone_photos':0}))
