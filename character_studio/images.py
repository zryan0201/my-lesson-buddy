"""Bounded, local image preparation; this is cleanup, not generative AI."""
from __future__ import annotations

from collections import deque
from io import BytesIO

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError


MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 12_000_000
SIZE = (600, 800)


def png_bytes(image):
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def _remove_paper(image):
    """Clear near-white paper connected to the edge, preserving enclosed white."""
    image = image.copy()
    pixels = image.load()
    width, height = image.size
    pending = deque((x, y) for x in range(width) for y in (0, height-1))
    pending.extend((x, y) for y in range(height) for x in (0, width-1))
    seen = bytearray(width*height)
    while pending:
        x, y = pending.popleft()
        index = y*width+x
        if seen[index]:
            continue
        seen[index] = 1
        red, green, blue, alpha = pixels[x, y]
        if alpha and min(red, green, blue) < 242:
            continue
        pixels[x, y] = (red, green, blue, 0)
        if x:
            pending.append((x-1, y))
        if x+1 < width:
            pending.append((x+1, y))
        if y:
            pending.append((x, y-1))
        if y+1 < height:
            pending.append((x, y+1))
    return image


def normalize_image(raw, *, remove_paper=True):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError('Choose one PNG or JPEG smaller than 8 MB.')
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in ('PNG', 'JPEG') or getattr(source, 'n_frames', 1) != 1:
                raise ValueError('Choose a still PNG or JPEG drawing.')
            if min(source.size) < 24 or source.width*source.height > MAX_PIXELS:
                raise ValueError('Choose a clearer drawing with no more than 12 million pixels.')
            source.verify()
        with Image.open(BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert('RGBA')
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError('This picture could not be opened. Choose another PNG or JPEG.') from exc
    image.thumbnail((1200, 1600), Image.Resampling.LANCZOS)
    if remove_paper:
        image = _remove_paper(image)
    # Ignore a few nearly transparent antialiasing pixels when finding the drawing.
    bounds = image.getchannel('A').point(lambda alpha: 255 if alpha > 24 else 0).getbbox()
    if bounds is None:
        raise ValueError('Draw a character first, then save it.')
    image = image.crop(bounds)
    image.thumbnail((540, 700), Image.Resampling.LANCZOS)
    # Small uploads can still be enlarged to a useful sticker size.
    scale = min(540/image.width, 700/image.height)
    if scale > 1:
        image = image.resize((round(image.width*scale), round(image.height*scale)), Image.Resampling.LANCZOS)
    result = Image.new('RGBA', SIZE)
    result.alpha_composite(image, ((SIZE[0]-image.width)//2, (SIZE[1]-image.height)//2))
    return result


def polish_drawing(raw):
    """Smooth the uploaded drawing and lift its colors without inventing artwork."""
    image = normalize_image(raw)
    alpha = image.getchannel('A')
    white = Image.new('RGBA', image.size, 'white')
    white.alpha_composite(image)
    colors = white.convert('RGB').filter(ImageFilter.UnsharpMask(radius=1, percent=90, threshold=4))
    result = colors.convert('RGBA')
    result.putalpha(alpha.filter(ImageFilter.SMOOTH))
    return result
