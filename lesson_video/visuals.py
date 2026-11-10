"""Responsive cartoon scenes driven by a lesson plan and speech timing."""
import math
import os
import textwrap
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .characters import draw_character

W, H = 1280, 720
INK = '#26334B'
TEAL = '#287D74'
PURPLE = '#7460C6'
GOLD = '#FFC928'


@lru_cache(maxsize=40)
def font(size):
    candidates = [os.environ.get('LESSON_VIDEO_FONT', ''),
                  '/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf',
                  '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                  'DejaVuSans-Bold.ttf']
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, int(size))
        except OSError:
            pass
    raise RuntimeError('No usable font. Set LESSON_VIDEO_FONT to a .ttf file.')


def text(d, xy, value, size=34, fill=INK, max_width=None):
    value = str(value)
    while max_width and size > 18 and d.textbbox((0, 0), value, font=font(size))[2] > max_width:
        size -= 1
    d.text(xy, value, font=font(size), fill=fill, anchor='mm')


def pill(d, xy, value, fill='#FFF0B3', color=INK, size=26, width=260):
    x, y = xy
    d.rounded_rectangle((x-width/2, y-24, x+width/2, y+24), radius=24, fill=fill)
    text(d, (x, y-1), value, size, color, width-24)


@lru_cache(maxsize=1)
def background():
    im = Image.new('RGB', (W, H), '#ECF7EF')
    d = ImageDraw.Draw(im)
    d.ellipse((-150, -200, 250, 190), fill='#E3EFE6')
    d.ellipse((1100, -80, 1460, 250), fill='#E2F0E9')
    d.rectangle((0, 592, W, H), fill='#D8ECE0')
    d.rounded_rectangle((61, 148, 1031, 604), radius=28, fill='#D1E0D7')
    d.rounded_rectangle((52, 139, 1022, 595), radius=28, fill='white', outline='#D7E6DB', width=2)
    d.rounded_rectangle((53, 626, 1227, 708), radius=18, fill='white')
    return im


@lru_cache(maxsize=2)
def dot_sprite(active=False):
    # Draw at double resolution so circles and small faces stay smooth.
    im = Image.new('RGBA', (264, 288))
    d = ImageDraw.Draw(im)
    x, y, r = 132, 126, 88
    if active:
        d.ellipse((15, 9, 249, 243), fill='#FFF0AE', outline='#2C9E8D', width=8)
    d.ellipse((47, 252, 217, 276), fill='#DFE6D3')
    for side in [-1, 1]:
        d.line([(x+side*80, y+17), (x+side*109, y+5), (x+side*121, y-15)], fill='#9B7717', width=7)
        d.line([(x+side*32, y+72), (x+side*43, y+108), (x+side*68, y+108)], fill='#9B7717', width=8)
    d.ellipse((x-r, y-r, x+r, y+r), fill=GOLD, outline='#C18B13', width=5)
    d.ellipse((x-60, y-66, x-18, y-42), fill='#FFE685')
    for dx in [-28, 28]:
        d.ellipse((x+dx-7, y-16, x+dx+7, y+6), fill=INK)
    d.ellipse((x-62, y+15, x-38, y+30), fill='#F2A85A')
    d.ellipse((x+38, y+15, x+62, y+30), fill='#F2A85A')
    d.arc((x-26, y-2, x+26, y+40), 0, 180, fill=INK, width=6)
    return im


@lru_cache(maxsize=24)
def resized_dot(radius, active):
    scale = radius/88
    return dot_sprite(active).resize((round(264*scale), round(288*scale)), Image.Resampling.LANCZOS)


def draw_dot(im, xy, radius, active=False, number=None, faded=False):
    x, y = xy
    sprite = resized_dot(int(radius), active)
    if faded:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel('A').point(lambda a: int(a*.20)))
    im.paste(sprite, (round(x-radius*1.5), round(y-radius*126/88)), sprite)
    if number is not None:
        pill(ImageDraw.Draw(im), (x, y-radius-24), str(number), TEAL, 'white', 27, 47)


@lru_cache(maxsize=48)
def object_artwork(path):
    """Load a source patch once, removing only white connected to its border."""
    with Image.open(path) as source:
        sprite = source.convert('RGBA')
    pixels = sprite.load()
    width, height = sprite.size
    border = [(x, y) for x in range(width) for y in (0, height-1)]
    border += [(x, y) for y in range(height) for x in (0, width-1)]
    pending, seen = border, set()
    while pending:
        x, y = pending.pop()
        if (x, y) in seen:
            continue
        seen.add((x, y))
        red, green, blue, alpha = pixels[x, y]
        if alpha and min(red, green, blue) < 245:
            continue
        pixels[x, y] = (red, green, blue, 0)
        for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in seen:
                pending.append((nx, ny))
    bounds = sprite.getbbox()
    if bounds is None:
        raise ValueError('An extracted worksheet object picture contains no visible artwork.')
    return sprite.crop(bounds)


@lru_cache(maxsize=256)
def resized_object(path, radius, faded=False):
    sprite = object_artwork(path)
    limit = max(1, round(radius*2.15))
    scale = min(limit/sprite.width, limit/sprite.height)
    sprite = sprite.resize((max(1, round(sprite.width*scale)), max(1, round(sprite.height*scale))),
                           Image.Resampling.LANCZOS)
    if faded:
        sprite.putalpha(sprite.getchannel('A').point(lambda alpha: int(alpha*.20)))
    return sprite


def draw_object(im, spec, index, xy, radius, active=False, number=None, faded=False):
    if 'object_images' not in spec:
        return draw_dot(im, xy, radius, active, number, faded)
    x, y = xy
    sprite = resized_object(spec['object_images'][index], int(radius), faded)
    if active:
        ImageDraw.Draw(im).rounded_rectangle((round(x-radius*1.37), round(y-radius*1.37),
                                              round(x+radius*1.37), round(y+radius*1.37)),
                                             radius=max(5, round(radius*.40)),
                                             fill='#FFF0AE', outline='#2C9E8D', width=3)
    im.paste(sprite, (round(x-sprite.width/2), round(y-sprite.height/2)), sprite)
    if number is not None:
        pill(ImageDraw.Draw(im), (x, y-radius-24), str(number), TEAL, 'white', 27, 47)


def object_name(spec, number):
    singular = spec.get('object_label', 'dot')
    return singular if number == 1 else spec.get('object_label_plural', singular+'s')


def positions(n, bounds, grid_size=None):
    x0, y0, x1, y1 = bounds
    if n == 0:
        return [], 30
    layout_n = grid_size or n
    cols = min(layout_n, (5 if layout_n==10 else 3) if x1-x0 < 450 else 5)
    rows = math.ceil(layout_n/cols)
    cell_w, cell_h = (x1-x0)/cols, (y1-y0)/rows
    radius = int(min(42, cell_w/3.1, cell_h/3.0))
    pts = []
    for i in range(n):
        row, col = divmod(i, cols)
        count_in_row = cols if grid_size else min(cols, n-row*cols)
        left = (x0+x1)/2 - cell_w*(count_in_row-1)/2
        pts.append((left+col*cell_w, y0+(row+.5)*cell_h))
    return pts, radius


def guide(d, t, talking=False, celebrate=False):
    x, y = 1140, 392 + 3*math.sin(t*2)
    d.ellipse((1080, 550, 1210, 566), fill='#D5E5D8')
    for side in [-1, 1]:
        hand_y = y-94 if celebrate else y+12+side*math.sin(t*3)*10
        d.line([(x+side*40, y-22), (x+side*68, y-44 if celebrate else y+6), (x+side*86, hand_y)], fill=INK, width=5)
        d.ellipse((x+side*86-7, hand_y-7, x+side*86+7, hand_y+7), fill='#FFF7E4', outline=INK, width=2)
        d.line([(x+side*25, y+80), (x+side*40, 548), (x+side*57, 548)], fill=INK, width=6)
    d.rounded_rectangle((x-43, y-134, x+43, y+83), radius=12, fill=PURPLE, outline=INK, width=3)
    d.rounded_rectangle((x-23, y-121, x-9, y+65), radius=6, fill='#9E8AE5')
    d.rounded_rectangle((x-43, y-151, x+43, y-113), radius=12, fill='#EDA4B4', outline=INK, width=3)
    d.rectangle((x-43, y-115, x+43, y-92), fill='#D6D9E1', outline=INK, width=3)
    d.polygon([(x-43, y+80), (x+43, y+80), (x, y+133)], fill='#F4D5AE', outline=INK, width=3)
    d.polygon([(x-12, y+117), (x+12, y+117), (x, y+133)], fill=INK)
    for dx in [-17, 17]:
        d.ellipse((x+dx-6, y-55, x+dx+6, y-34), fill='white')
        d.ellipse((x+dx-2, y-49, x+dx+3, y-35), fill=INK)
    if talking and math.sin(t*17)>0:
        d.ellipse((x-10, y-24, x+10, y-5), fill=INK)
        d.ellipse((x-6, y-12, x+6, y-5), fill='#F0ABB1')
    else:
        d.arc((x-15, y-33, x+15, y-8), 0, 180, fill=INK, width=3)


def caption(d, value):
    # Wrap by actual pixel width, keeping all words visible.
    words = value.split()
    lines, current = [], ''
    for word in words:
        candidate = (current+' '+word).strip()
        if d.textbbox((0, 0), candidate, font=font(28))[2] > 1115 and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines)>2:
        # Step text is validated to keep narration short; this is a visual fallback.
        text(d, (640, 666), value, 26, max_width=1115)
    elif len(lines)==1:
        text(d, (640, 666), lines[0], 28)
    elif lines:
        text(d, (640, 646), lines[0], 28)
        text(d, (640, 682), lines[1], 28)


def shape_scene(d, spec, ev):
    name = spec['shape']
    poly = {'triangle': [(537, 230), (380, 437), (694, 437)],
            'square': [(427, 230), (647, 230), (647, 450), (427, 450)],
            'rectangle': [(367, 255), (707, 255), (707, 425), (367, 425)]}
    if name == 'circle':
        d.ellipse((422, 220, 652, 450), fill='#FFD95E', outline='#BD8E16', width=5)
    else:
        points = poly[name]
        d.polygon(points, fill='#FFD95E', outline='#BD8E16', width=5)
        if 'active_index' in ev:
            side = ev['active_index']
            p, q = points[side], points[(side+1)%len(points)]
            d.line([p, q], fill=TEAL, width=12)
            mid = ((p[0]+q[0])/2, (p[1]+q[1])/2)
            pill(d, mid, str(ev.get('number', side+1)), TEAL, 'white', 27, 48)
    # A quiet face makes each shape a character without adding counting objects.
    for x in [512, 562]:
        d.ellipse((x-5, 326, x+5, 340), fill=INK)
    d.arc((519, 338, 555, 365), 0, 180, fill=INK, width=4)


def render_frame(spec, events, t, duration):
    im = background().copy()
    d = ImageDraw.Draw(im)
    ev = events[0]
    for item in events:
        if item['start'] <= t:
            ev = item
        else:
            break
    phase = ev['phase']
    kind = spec['type']
    shown_answer = any(e['phase']=='answer' and e['start']<=t for e in events)
    speech = ev['start'] <= t < ev['end']
    question_pause = phase=='question' and t>=ev['end']
    title = {'intro': spec['title'], 'group_a': 'Count the first group', 'group_b': 'Count the next group',
             'action': 'Put them together' if kind=='addition' else 'Take some away',
             'count': 'Count them all', 'question': 'Your turn!', 'answer': 'You found it!',
             'equality': 'Same amount', 'celebration': 'You did it!'}[phase]
    if kind == 'shape':
        if phase in ['action', 'count']:
            title = 'Count the straight sides' if spec['shape']!='circle' else 'Look at the curved edge'
    elif kind == 'subtraction' and phase=='count':
        title = 'Count what is left'
    text(d, (537, 72), title, 46, max_width=960)
    pill(d, (1137, 72), {'addition':'ADD', 'subtraction':'SUBTRACT', 'counting':'COUNT', 'comparison':'COMPARE', 'shape':'SHAPES'}[kind], '#E4DDF6', PURPLE, 19, 190)
    if spec.get('character'):
        draw_character(im, spec['character'], t, speech, phase=='celebration',
                       phase in ('group_a', 'group_b', 'action', 'count'),
                       asset_path=spec.get('character_image'),
                       design_path=spec.get('character_design'))
    else:
        guide(d, t, speech, phase=='celebration')
    a, b = spec.get('a') or 0, spec.get('b') or 0
    active = ev.get('active_index')
    if kind=='shape':
        shape_scene(d, spec, ev)
        label = '?'
        if shown_answer:
            label = f"{spec['answer']} straight sides" if spec.get('shape_task')=='sides' else spec['shape'].capitalize()
        elif phase=='question':
            label = 'How many straight sides?' if spec.get('shape_task')=='sides' else 'What shape is this?'
        else:
            label = 'Look carefully!'
        pill(d, (537, 525), label, '#EEF5F1', TEAL, 30, 540)
    else:
        action = next((e for e in events if e['phase']=='action'), None)
        action_done = action is not None and t>=action['end']
        groups = kind=='comparison' or (kind=='addition' and (action is None or t<action['start']))
        if groups:
            d.rounded_rectangle((142, 221, 490, 449), radius=24, fill='#E8F4EE')
            d.rounded_rectangle((622, 221, 970, 449), radius=24, fill='#F0EAFB')
            layouts = [(context, n, bounds, *positions(n, bounds, max(a,b) if kind=='comparison' else None))
                       for context, n, bounds in [('a', a, (170, 236, 462, 430)), ('b', b, (650, 236, 942, 430))]]
            common_radius = min(item[-1] for item in layouts)
            for context, n, bounds, pts, radius in layouts:
                radius = common_radius
                if n==0:
                    text(d, ((bounds[0]+bounds[2])/2, 330), f'0 {object_name(spec, 0)}', 32, TEAL)
                for i, point in enumerate(pts):
                    selected = phase==f'group_{context}' and active==i
                    draw_object(im, spec, i+(a if context=='b' else 0), point, radius, selected,
                                ev.get('number') if selected and max(a,b)<=3 else None)
            d = ImageDraw.Draw(im)
            if kind=='addition':
                text(d, (553, 330), '+', 64, TEAL)
        else:
            n = a+b if kind=='addition' else a
            pts, radius = positions(n, (173, 246, 901, 441))
            d.rounded_rectangle((142, 221, 970, 454), radius=24, fill='#F2F8ED')
            keep = a-b if kind=='subtraction' else n
            source_points = None
            if kind=='addition' and not action_done and action is not None:
                pa, ra = positions(a, (170, 236, 462, 430))
                pb, rb = positions(b, (650, 236, 942, 430))
                source_points = pa+pb
                fraction = min(1, max(0, (t-action['start'])/max(.4, action['duration']-.1)))
                fraction = fraction*fraction*(3-2*fraction)
                source_radius = min(ra,rb)
            for i, point in enumerate(pts):
                draw_radius = radius
                if source_points:
                    source = source_points[i]
                    point = (source[0]+(point[0]-source[0])*fraction, source[1]+(point[1]-source[1])*fraction)
                    draw_radius = round(source_radius+(radius-source_radius)*fraction)
                removed = kind=='subtraction' and action is not None and t>=action['start'] and i>=keep
                if removed and action_done:
                    continue
                if removed:
                    fraction = min(1, max(0, (t-action['start'])/max(.4, action['duration'])))
                    point = (point[0]+fraction*22, point[1]-fraction*18)
                selected = (phase=='count' or kind=='subtraction' and phase=='group_a') and active==i
                draw_object(im, spec, i, point, draw_radius, selected,
                            ev.get('number') if selected and n<=5 else None, removed)
                if removed:
                    dd = ImageDraw.Draw(im)
                    x, y = point
                    dd.line([(x-radius*.7,y-radius*.7),(x+radius*.7,y+radius*.7)], fill='#BF6B61', width=4)
                    dd.line([(x+radius*.7,y-radius*.7),(x-radius*.7,y+radius*.7)], fill='#BF6B61', width=4)
            d = ImageDraw.Draw(im)
            if (kind=='subtraction' and keep==0 and action_done) or n==0:
                empty = f'No {object_name(spec, 0)}' + (' left' if kind=='subtraction' else '')
                text(d, (537, 342), empty, 39, TEAL)
        if kind in ['addition','subtraction']:
            expression = f"{a} {'+' if kind=='addition' else '-'} {b} = {spec['answer'] if shown_answer else '?'}"
        elif kind=='counting':
            expression = f"{spec['answer'] if shown_answer else '?'} {object_name(spec, spec['answer'] if shown_answer else 0)}"
        else:
            sign = '>' if a>b else '<' if a<b else '='
            expression = f"{a} {sign if shown_answer else '?'} {b}"
        pill(d, (537, 527), expression, '#F2F5FA', TEAL if shown_answer else INK, 54, 640)
        if shown_answer:
            if kind in ['addition','counting']:
                banner = f"{spec['answer']} {object_name(spec, spec['answer'])} in all"
            elif kind=='subtraction':
                banner = f"{spec['answer']} {object_name(spec, spec['answer'])} left"
            elif spec['answer']=='equal':
                banner = 'Both groups are equal'
            elif spec.get('comparison_mode')=='compare':
                banner = 'Compare the groups'
            else:
                banner = f"{spec['answer']} is {'smaller' if spec.get('comparison_mode')=='less' else 'greater'}"
            pill(d, (537, 186), banner, width=380)
    if phase=='celebration':
        for i in range(21):
            x = 96 + (i*137)%902
            y = 160 + (t*65+i*47)%300
            color = ['#B399E3','#E89496','#67B8A7'][i%3]
            d.rounded_rectangle((x-3,y-4,x+3,y+4), radius=2, fill=color)
    caption(d, 'Take a moment to think...' if question_pause else ev['text'] if speech else '')
    d.line([(52, 613), (1022, 613)], fill='#C6DFD0', width=3)
    d.line([(52, 613), (52+970*min(1,t/duration), 613)], fill=TEAL, width=3)
    return im
