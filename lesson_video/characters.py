"""Friendly, configurable cartoon guides drawn locally with Pillow.

Character settings contain colors and controlled choices only. They never name
an image, font, executable, or other file supplied by an upload.
"""
from __future__ import annotations

import math
import json
import os
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


INK = "#26334B"
CREAM = "#FFF6E4"
DEFAULT_CHARACTER = {
    "kind": "robot", "name": "Buddy", "color": "#65B9D8",
    "outfit": "overalls", "outfit_color": "#7966CB", "accessory": "none",
}
_CHOICES = {
    "kind": ("robot", "fox", "bear"),
    "outfit": ("overalls", "shirt", "none"),
    "accessory": ("none", "cap", "glasses", "bow"),
}


def validate_character(value: dict) -> dict:
    """Return complete normalized settings, rejecting unknown or unsafe input."""
    if not isinstance(value, dict):
        raise ValueError("Character settings must be an object.")
    if value.get("kind") == "studio":
        if set(value) != {"kind", "asset_id", "name"}:
            raise ValueError("A studio character needs its saved character ID and name.")
        asset_id = value["asset_id"]
        if not isinstance(asset_id, str) or not re.fullmatch(r"[0-9a-f]{32}", asset_id):
            raise ValueError("Choose a saved character from the Character Studio.")
        from character_studio.assets import normalize_name
        name = normalize_name(value["name"])
        return {"kind": "studio", "asset_id": asset_id, "name": name}
    if any(not isinstance(key, str) for key in value) or set(value) - set(DEFAULT_CHARACTER):
        raise ValueError("Character settings contain an unknown option.")
    result = {**DEFAULT_CHARACTER, **value}
    for key in _CHOICES:
        if not isinstance(result[key], str) or result[key] not in _CHOICES[key]:
            raise ValueError(f"Choose a supported character {key.replace('_', ' ')}.")
    for key in ("color", "outfit_color"):
        if not isinstance(result[key], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", result[key]):
            raise ValueError("Character colors must use six-digit hex colors, such as #65B9D8.")
        result[key] = result[key].upper()
    name = result["name"]
    if not isinstance(name, str):
        raise ValueError("Give your character a short name.")
    name = re.sub(r" +", " ", name.strip())
    if not 1 <= len(name) <= 24 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 '\-]*", name):
        raise ValueError("Character names use 1–24 letters, numbers, spaces, apostrophes, or hyphens.")
    result["name"] = name
    return result


def character_catalog() -> dict:
    """JSON-friendly options for a frontend; each call returns independent data."""
    return {
        "default": dict(DEFAULT_CHARACTER),
        "kinds": list(_CHOICES["kind"]),
        "outfits": list(_CHOICES["outfit"]),
        "accessories": list(_CHOICES["accessory"]),
        "colors": ["#65B9D8", "#F5AA65", "#C99B7A", "#83C8A3", "#AFA0E2", "#EB8DA5"],
        "name_max_length": 24,
    }


@lru_cache(maxsize=20)
def _font(size):
    for path in (os.environ.get("LESSON_VIDEO_FONT", ""),
                 "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
        if path:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


def _lighten(color, fraction=.45):
    rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
    return tuple(round(c + (255-c)*fraction) for c in rgb)


class _Canvas:
    """Draw in a 300 × 500 coordinate system at double resolution."""
    def __init__(self):
        self.image = Image.new("RGBA", (600, 1000), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.image)

    def ellipse(self, box, fill, outline=INK, width=3):
        self.d.ellipse(tuple(round(x*2) for x in box), fill=fill, outline=outline, width=width*2)

    def rounded(self, box, radius, fill, outline=INK, width=3):
        self.d.rounded_rectangle(tuple(round(x*2) for x in box), radius=radius*2,
                                 fill=fill, outline=outline, width=width*2)

    def polygon(self, points, fill, outline=INK, width=3):
        self.d.polygon([(round(x*2), round(y*2)) for x, y in points], fill=fill,
                       outline=outline, width=width*2)

    def line(self, points, fill=INK, width=3):
        self.d.line([(round(x*2), round(y*2)) for x, y in points], fill=fill,
                    width=width*2, joint="curve")

    def arc(self, box, start, end, fill=INK, width=3):
        self.d.arc(tuple(round(x*2) for x in box), start, end, fill=fill, width=width*2)


def _limbs(c, color, body_y, celebrate, pointing, t):
    # Arms and legs sit behind the torso. Pointing stays inside the guide area.
    for side in (-1, 1):
        shoulder = (150+side*57, body_y+20)
        if celebrate:
            elbow, hand = (150+side*83, body_y-33), (150+side*107, body_y-77)
        elif pointing and side == -1:
            elbow, hand = (61, body_y+13), (26, body_y-1)
        else:
            elbow, hand = (150+side*83, body_y+53), (150+side*91, body_y+74+3*math.sin(t*3))
        c.line([shoulder, elbow, hand], INK, 17)
        c.line([shoulder, elbow, hand], color, 11)
        c.ellipse((hand[0]-10, hand[1]-10, hand[0]+10, hand[1]+10), color)
        if pointing and side == -1 and not celebrate:
            c.line([(hand[0]-3, hand[1]-4), (hand[0]-14, hand[1]-9)], INK, 7)
            c.line([(hand[0]-3, hand[1]-4), (hand[0]-14, hand[1]-9)], color, 3)
        hip_x = 150+side*30
        c.rounded((hip_x-14, body_y+108, hip_x+14, 442), 12, color)
        c.rounded((hip_x-22, 433, hip_x+23, 457), 10, INK)
        c.line([(hip_x-12, 446), (hip_x+12, 446)], "#718097", 3)


def _outfit(c, settings, top):
    color, style = settings["outfit_color"], settings["outfit"]
    if style == "none":
        return
    if style == "shirt":
        c.rounded((91, top+4, 209, top+91), 19, color)
        c.ellipse((127, top-6, 173, top+17), settings["color"])
        # A single stitched star reads clearly even in a small preview.
        points = []
        for i in range(10):
            angle = -math.pi/2+i*math.pi/5
            r = 17 if i % 2 == 0 else 8
            points.append((150+math.cos(angle)*r, top+50+math.sin(angle)*r))
        c.polygon(points, "#FFF0A5", None)
    else:
        c.rounded((94, top+48, 206, top+125), 18, color)
        for x in (108, 180):
            c.rounded((x, top+4, x+13, top+73), 5, color)
            c.ellipse((x+2, top+54, x+11, top+63), "#FFE192", None)
        c.rounded((128, top+72, 172, top+103), 6, _lighten(color, .18), "#FFFFFF", 1)


def _eyes(c, left, right, y, blink, robot=False):
    for x in (left, right):
        if blink:
            c.arc((x-10, y-5, x+10, y+4), 10, 170, INK, 4)
        elif robot:
            c.rounded((x-11, y-15, x+11, y+10), 8, INK, None)
            c.ellipse((x-6, y-10, x-1, y-4), "#D9F7FF", None)
        else:
            c.ellipse((x-9, y-13, x+9, y+10), INK, None)
            c.ellipse((x-5, y-9, x, y-4), "white", None)


def _mouth(c, y, talking, t):
    if talking and math.sin(t*16) > -.25:
        opening = 9+3*math.sin(t*16)
        c.ellipse((136, y-5, 164, y+opening+6), INK, None)
        c.ellipse((141, y+opening-1, 159, y+opening+5), "#EA97A5", None)
    else:
        c.arc((132, y-16, 168, y+8), 5, 175, INK, 3)


def _accessory(c, settings, eye_y, top):
    choice = settings["accessory"]
    if choice == "glasses":
        for x in (116, 184):
            c.rounded((x-25, eye_y-24, x+25, eye_y+20), 13, None, INK, 6)
        c.line([(141, eye_y-7), (159, eye_y-7)], INK, 5)
        c.line([(91, eye_y-8), (77, eye_y-13)], INK, 4)
        c.line([(209, eye_y-8), (223, eye_y-13)], INK, 4)
    elif choice == "cap":
        c.rounded((93, top-12, 207, top+22), 19, "#EF8E77")
        c.rounded((132, top+15, 229, top+30), 6, "#D46F62")
        c.ellipse((145, top-19, 157, top-8), "#FFE3A9")
        c.line([(150, top-10), (150, top+12)], "#F9C5A9", 3)
    elif choice == "bow":
        # A hair bow leaves the clothing choice independently visible.
        cx, cy = 207, top+9
        c.polygon([(cx-2, cy), (cx-34, cy-20), (cx-34, cy+20)], "#E77EA7")
        c.polygon([(cx+2, cy), (cx+32, cy-20), (cx+32, cy+20)], "#E77EA7")
        c.ellipse((cx-9, cy-9, cx+9, cy+9), "#FFD681")


def _draw(settings, t, talking, celebrate, pointing):
    c = _Canvas()
    color, kind = settings["color"], settings["kind"]
    bob = math.sin(t*2.5)*2
    # A constant shadow anchors all three guides without introducing worksheet objects.
    c.ellipse((76, 451, 224, 468), (32, 73, 59, 32), None)
    top = 272+bob
    _limbs(c, color, top, celebrate, pointing, t)
    c.rounded((90, top, 210, top+128), 34, color)
    if kind == "bear":
        c.ellipse((118, top+27, 182, top+114), _lighten(color), None)
    _outfit(c, settings, top)

    blink = t % 4.1 > 3.93
    if kind == "robot":
        c.line([(150, 111+bob), (150, 76+bob)], INK, 5)
        c.ellipse((137, 52+bob, 163, 78+bob), "#FFC866")
        for side in (-1, 1):
            cx = 150+side*86
            c.rounded((cx-12, 164+bob, cx+12, 215+bob), 9, _lighten(color, .25))
        c.rounded((70, 109+bob, 230, 266+bob), 33, color)
        c.rounded((89, 135+bob, 211, 242+bob), 22, _lighten(color, .77))
        eye_y, accessory_top = 180+bob, 112+bob
        _eyes(c, 116, 184, eye_y, blink, True)
        _mouth(c, 217+bob, talking, t)
        for x in (96, 204):
            c.ellipse((x-6, 223+bob, x+6, 233+bob), "#EEA0AA", None)
    elif kind == "fox":
        c.polygon([(72, 170+bob), (65, 71+bob), (129, 118+bob)], color)
        c.polygon([(171, 118+bob), (235, 71+bob), (228, 170+bob)], color)
        c.polygon([(80, 139+bob), (77, 94+bob), (107, 121+bob)], "#F7C2A9", None)
        c.polygon([(193, 121+bob), (223, 94+bob), (220, 139+bob)], "#F7C2A9", None)
        c.rounded((69, 118+bob, 231, 268+bob), 54, color)
        c.polygon([(76, 190+bob), (111, 197+bob), (150, 240+bob), (189, 197+bob),
                   (224, 190+bob), (213, 250+bob), (150, 281+bob), (87, 250+bob)], CREAM, None)
        eye_y, accessory_top = 178+bob, 120+bob
        _eyes(c, 116, 184, eye_y, blink)
        c.rounded((138, 217+bob, 162, 233+bob), 8, INK, None)
        _mouth(c, 249+bob, talking, t)
    else:
        for x in (86, 214):
            c.ellipse((x-31, 89+bob, x+31, 151+bob), color)
            c.ellipse((x-17, 103+bob, x+17, 138+bob), _lighten(color, .52), None)
        c.ellipse((66, 113+bob, 234, 280+bob), color)
        c.ellipse((111, 204+bob, 189, 270+bob), CREAM, None)
        eye_y, accessory_top = 183+bob, 117+bob
        _eyes(c, 116, 184, eye_y, blink)
        c.rounded((138, 215+bob, 162, 233+bob), 8, INK, None)
        _mouth(c, 250+bob, talking, t)
        for x in (89, 211):
            c.ellipse((x-10, 211+bob, x+10, 223+bob), "#EA9D9A", None)
    _accessory(c, settings, eye_y, accessory_top)

    c.rounded((26, 474, 274, 499), 12, (255, 255, 255, 235), None)
    font_size = 29
    while font_size > 16 and c.d.textbbox((0, 0), settings["name"], font=_font(font_size))[2] > 450:
        font_size -= 1
    c.d.text((300, 972), settings["name"], fill=INK, font=_font(font_size), anchor="mm")
    return c.image


@lru_cache(maxsize=24)
def _studio_library_image(asset_id):
    from character_studio.assets import load_character_image
    return load_character_image(asset_id).convert("RGBA")


@lru_cache(maxsize=24)
def _studio_snapshot_image(path, modified, size):
    # The pipeline supplies a verified, per-lesson snapshot. It is never a path
    # from character settings or an HTTP request.
    with Image.open(path) as opened:
        return opened.convert("RGBA")


@lru_cache(maxsize=24)
def _studio_snapshot_design(path, modified, size):
    from character_studio.parts import validate_design
    return validate_design(json.loads(Path(path).read_text(encoding='utf-8')))


def _draw_studio(settings, t, talking, celebrate, pointing, asset_path, design_path):
    c = _Canvas()
    c.ellipse((65, 443, 235, 459), (32, 73, 59, 32), None)
    if design_path is not None:
        # Joint positions come only from the reviewed per-lesson design file.
        # Keep the full attachment grid fixed so waving never resizes the body.
        from character_studio.motion import render_motion_frame
        path = Path(design_path)
        info = path.stat()
        design = _studio_snapshot_design(str(path.resolve()), info.st_mtime_ns, info.st_size)
        motion = 'celebrate' if celebrate else 'talk' if talking else 'wave' if pointing else 'idle'
        source = render_motion_frame(design, motion, t)
        c.image.alpha_composite(source, (0, 140))
    else:
        if asset_path is None:
            original = _studio_library_image(settings["asset_id"])
        else:
            path = Path(asset_path)
            info = path.stat()
            original = _studio_snapshot_image(str(path.resolve()), info.st_mtime_ns, info.st_size)
        bounds = original.getbbox()
        if bounds is None:
            raise ValueError("The saved character has no visible artwork.")
        source = ImageOps.contain(original.crop(bounds), (490, 740), Image.Resampling.LANCZOS)
        # Drawings and legacy imports move intact; never invent their features.
        angle = math.sin(t * 2.4) * (3 if celebrate else 1.2)
        if pointing:
            angle -= 1.5
        source = source.rotate(angle, Image.Resampling.BICUBIC, expand=True)
        bob = round(math.sin(t * 2.7) * (10 if celebrate else 5))
        c.image.alpha_composite(source, ((600-source.width)//2, 140+(740-source.height)//2+bob))
    if celebrate:
        for cx, cy, radius in ((40, 105, 10), (263, 169, 8), (44, 347, 7), (255, 374, 10)):
            pulse = .85 + .15 * math.sin(t * 5)
            r = radius * pulse
            c.polygon([(cx, cy-r), (cx+r*.28, cy-r*.28), (cx+r, cy),
                       (cx+r*.28, cy+r*.28), (cx, cy+r), (cx-r*.28, cy+r*.28),
                       (cx-r, cy), (cx-r*.28, cy-r*.28)], "#FFD56E", None)
    c.rounded((26, 474, 274, 499), 12, (255, 255, 255, 235), None)
    font_size = 29
    while font_size > 12 and c.d.textbbox((0, 0), settings["name"], font=_font(font_size))[2] > 450:
        font_size -= 1
    c.d.text((300, 972), settings["name"], fill=INK, font=_font(font_size), anchor="mm")
    return c.image


def render_character_image(config, width=300, height=400, t=0, talking=False,
                           celebrate=False, pointing=False, *, asset_path=None, design_path=None):
    """Return a transparent RGBA preview, with the same artwork as the video."""
    settings = validate_character(config)
    if (not isinstance(width, int) or isinstance(width, bool) or not isinstance(height, int)
            or isinstance(height, bool) or not 32 <= width <= 1600 or not 32 <= height <= 1600):
        raise ValueError("Character preview dimensions must be between 32 and 1600 pixels.")
    if not isinstance(t, (int, float)) or not math.isfinite(t):
        raise ValueError("Character animation time must be finite.")
    source = (_draw_studio(settings, t, talking, celebrate, pointing, asset_path, design_path)
              if settings["kind"] == "studio" else _draw(settings, t, talking, celebrate, pointing))
    scale = min(width/source.width, height/source.height)
    source = source.resize((max(1, round(source.width*scale)), max(1, round(source.height*scale))),
                           Image.Resampling.LANCZOS)
    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    result.alpha_composite(source, ((width-source.width)//2, (height-source.height)//2))
    return result


def draw_character(im, config, t, talking=False, celebrate=False, pointing=False, *,
                   asset_path=None, design_path=None):
    """Place a guide strictly to the right of the worksheet and above captions."""
    sprite = render_character_image(config, 210, 420, t, talking, celebrate, pointing,
                                    asset_path=asset_path, design_path=design_path)
    im.paste(sprite, (1040, 170), sprite)
