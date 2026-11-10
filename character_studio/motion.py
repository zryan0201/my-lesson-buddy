"""Small offline motion loops shared by the studio and lesson renderer.

Only modular designs have known joints. Uploaded drawings stay intact and move
as a whole sticker; this module never guesses a child's eyes, mouth, or limbs.
"""
from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import json
import math

from PIL import Image, ImageChops, ImageDraw, ImageOps

from .parts import render_design, validate_design


MOTIONS = ('idle', 'wave', 'talk', 'celebrate')
_FRAME_COUNT = 16


def _motion(value):
    if not isinstance(value, str) or value not in MOTIONS:
        raise ValueError('Choose idle, wave, talk, or celebrate for character motion.')
    return value


def _dimensions(width, height):
    if (type(width) is not int or type(height) is not int
            or not 64 <= width <= 2048 or not 64 <= height <= 2048):
        raise ValueError('Character previews must be 64–2048 pixels on each side.')


@lru_cache(maxsize=160)
def _render_bin(canonical, motion, frame, width, height):
    return render_design(json.loads(canonical), width, height,
                         pose=motion, phase=frame/_FRAME_COUNT)


def render_motion_frame(design, motion, t, width=600, height=800):
    """Return a fresh RGBA frame; cached poses never grow with video duration.

    Ten distinct poses each second keep joint movement smooth while limiting
    expensive supersampled artwork to sixteen poses per character and action.
    A copy prevents a caller from painting over a cached frame.
    """
    canonical = json.dumps(validate_design(design), sort_keys=True, separators=(',', ':'))
    _motion(motion)
    _dimensions(width, height)
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
        raise ValueError('Character animation time must be finite.')
    frame = math.floor((t % 1.6)*10+1e-8) % _FRAME_COUNT
    return _render_bin(canonical, motion, frame, width, height).copy()


def design_matches_image(design, image):
    """Animate joints only when they recreate the saved artwork exactly.

    Portable imports preserve their PNG even across renderer versions. A
    matching design can use joints; an older or mismatched PNG remains a sticker.
    Comparing decoded pixels avoids depending on PNG encoder versions.
    """
    if design is None or not isinstance(image, Image.Image):
        return False
    try:
        expected = render_design(design)
        original = image.convert('RGBA')
        if expected.size != original.size:
            return False
        # getbbox on RGBA alone only examines the alpha channel in Pillow.
        return ImageChops.difference(expected, original).getbbox(alpha_only=False) is None
    except (TypeError, ValueError):
        return False


def _sticker_frame(image, motion, t, width, height):
    source = image.convert('RGBA')
    bounds = source.getbbox()
    if bounds is None:
        raise ValueError('Save a character with some visible artwork first.')
    source = ImageOps.contain(source.crop(bounds), (round(width*.8), round(height*.8)),
                              Image.Resampling.LANCZOS)
    phase = t*math.tau/1.6
    angle = math.sin(phase)*(3 if motion == 'celebrate' else 1.3)
    source = source.rotate(angle, Image.Resampling.BICUBIC, expand=True)
    bob = round(math.sin(phase)*(height*.018 if motion == 'celebrate' else height*.008))
    frame = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    frame.alpha_composite(source, ((width-source.width)//2, (height-source.height)//2+bob))
    return frame


def preview_gif(*, design=None, image=None, motion='idle'):
    """Create a bounded, twelve-frame 300×400 preview entirely on this device.

    If both a design and saved image are supplied, the pixels must match before
    joints can move. A drawing has gentle sticker motion for every action.
    """
    _motion(motion)
    if image is not None and not isinstance(image, Image.Image):
        raise ValueError('A motion preview needs a saved character picture.')
    use_design = design is not None and (image is None or design_matches_image(design, image))
    if use_design:
        design = validate_design(design)
    elif image is None:
        raise ValueError('Choose a character design or saved picture for the preview.')
    frames = []
    for index in range(12):
        t = index*1.6/12
        sprite = (render_motion_frame(design, motion, t, 300, 400) if use_design
                  else _sticker_frame(image, motion, t, 300, 400))
        frame = Image.new('RGB', (300, 400), '#F7F3EA')
        draw = ImageDraw.Draw(frame)
        draw.ellipse((80, 366, 220, 379), fill='#E3E7DC')
        frame.paste(sprite, (0, 0), sprite)
        frames.append(frame)
    output = BytesIO()
    frames[0].save(output, format='GIF', save_all=True, append_images=frames[1:],
                   loop=0, duration=130, disposal=2, optimize=False)
    return output.getvalue()
