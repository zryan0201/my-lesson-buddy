"""Original, interchangeable character artwork drawn locally with Pillow.

The design is data: a name, a fixed set of parts, and four colors. No uploaded
path or executable is interpreted here. Every piece shares the same attachment
points so a child can mix a creature's ears with a robot's armor or a hero's cape.
"""
from __future__ import annotations

import copy
import math
import re
import unicodedata

from PIL import Image, ImageDraw


INK = "#293650"
WHITE = "#FFFFFF"
_SIZE = (600, 800)
_NAME_MAX = 32
_DEFAULTS = {
    "version": 1,
    "name": "Spark",
    "body_type": "kid",
    "head_shape": "round",
    "eyes": "friendly",
    "headwear": "none",
    "chest": "star",
    "back": "cape",
    "gloves": "none",
    "boots": "round",
    "primary_color": "#647CDE",
    "secondary_color": "#55C6BC",
    "accent_color": "#FFD36E",
    "skin_color": "#F4BE99",
}
_OPTIONS = {
    "body_type": (("kid", "Little hero"), ("robot", "Robot"), ("creature", "Creature")),
    "head_shape": (("round", "Round"), ("angular", "Angular")),
    "eyes": (("round", "Bright eyes"), ("visor", "Space visor"), ("friendly", "Happy eyes")),
    "headwear": (("none", "No headwear"), ("web_mask", "Web mask"),
                 ("helmet", "Explorer helmet"), ("ears", "Creature ears"),
                 ("antenna", "Antenna")),
    "chest": (("none", "No badge"), ("star", "Star"), ("bolt", "Lightning"),
              ("gem", "Crystal"), ("reactor", "Power core")),
    "back": (("none", "No back piece"), ("cape", "Cape"), ("wings", "Wings")),
    "gloves": (("none", "Simple hands"), ("gauntlets", "Power gloves")),
    "boots": (("round", "Round boots"), ("armored", "Armor boots")),
}
_PRESETS = (
    ("star_explorer", "Star Explorer", {
        "name": "Nova", "body_type": "kid", "head_shape": "angular",
        "headwear": "helmet", "chest": "star", "back": "cape",
        "gloves": "gauntlets", "boots": "armored", "primary_color": "#568ADA",
        "secondary_color": "#EE7B7B", "accent_color": "#FFD36E",
    }),
    ("bolt_builder", "Bolt Builder", {
        "name": "Bolt", "body_type": "robot", "eyes": "visor", "headwear": "antenna",
        "chest": "bolt", "back": "none", "gloves": "gauntlets", "boots": "armored",
        "primary_color": "#F4AD64", "secondary_color": "#54B6B5",
        "accent_color": "#FFE390",
    }),
    ("moon_fox", "Moon Fox", {
        "name": "Luna", "body_type": "creature", "eyes": "round", "headwear": "ears",
        "chest": "gem", "back": "cape", "primary_color": "#B49ADD",
        "secondary_color": "#65BFB7", "accent_color": "#F4B783",
    }),
    ("wing_wonder", "Wing Wonder", {
        "name": "Wisp", "body_type": "kid", "headwear": "web_mask", "eyes": "round",
        "chest": "reactor", "back": "wings", "gloves": "gauntlets",
        "primary_color": "#D98BAB", "secondary_color": "#6DC7CC",
        "accent_color": "#FFDE8A", "skin_color": "#A96E52",
    }),
)


def validate_design(value: dict) -> dict:
    """Return a new complete design, with normalized colors and Unicode name.

    Names accept letters and numbers from any writing system, combining marks,
    spaces, apostrophes and hyphens. Control characters, markup, and paths are
    rejected rather than being hidden by trimming or HTML escaping.
    """
    if not isinstance(value, dict):
        raise ValueError("Character design must be an object.")
    if any(not isinstance(key, str) for key in value) or set(value) - set(_DEFAULTS):
        raise ValueError("Character design contains an unknown option.")
    result = {**_DEFAULTS, **value}
    if type(result["version"]) is not int or result["version"] != 1:
        raise ValueError("Choose a supported character design version.")
    for field, choices in _OPTIONS.items():
        if not isinstance(result[field], str) or result[field] not in {v for v, _ in choices}:
            raise ValueError(f"Choose a supported {field.replace('_', ' ')}.")
    for field in ("primary_color", "secondary_color", "accent_color", "skin_color"):
        color = result[field]
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
            raise ValueError("Character colors use six-digit hex colors, such as #647CDE.")
        result[field] = color.upper()
    name = result["name"]
    if not isinstance(name, str):
        raise ValueError("Give your character a name using 1–32 letters or numbers.")
    name = unicodedata.normalize("NFC", name)
    allowed_punctuation = {" ", "'", "’", "-"}
    if any(unicodedata.category(ch)[0] not in {"L", "N", "M"}
           and ch not in allowed_punctuation and unicodedata.category(ch) != "Zs"
           for ch in name):
        raise ValueError("Names can contain letters, numbers, spaces, apostrophes, and hyphens.")
    name = " ".join(name.split())
    if not 1 <= len(name) <= _NAME_MAX or not any(unicodedata.category(ch)[0] in {"L", "N"}
                                               for ch in name):
        raise ValueError("Give your character a name using 1–32 letters or numbers.")
    result["name"] = name
    return result


def catalog() -> dict:
    """Return independent JSON-friendly options and four original starting looks."""
    return {
        "version": 1,
        "name_max_length": _NAME_MAX,
        "defaults": dict(_DEFAULTS),
        "options": {field: [{"value": value, "label": label} for value, label in choices]
                    for field, choices in _OPTIONS.items()},
        "presets": [{"id": ident, "name": name, "design": validate_design(copy.deepcopy(design))}
                    for ident, name, design in _PRESETS],
        "colors": ["#647CDE", "#55C6BC", "#FFD36E", "#EE7B7B", "#B49ADD", "#D98BAB",
                   "#568ADA", "#F4AD64", "#A7CE8A", "#F4BE99", "#A96E52", "#6A4538"],
    }


def _rgb(color):
    return tuple(int(color[i:i+2], 16) for i in (1, 3, 5))


def _light(color, amount=.4):
    return tuple(round(c + (255-c)*amount) for c in _rgb(color))


def _dark(color, amount=.16):
    return tuple(round(c*(1-amount)) for c in _rgb(color))


class _Canvas:
    """A fixed attachment grid, drawn at 2× resolution for smooth small sprites."""
    def __init__(self):
        self.image = Image.new("RGBA", (1200, 1600), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)

    @staticmethod
    def _box(box):
        return tuple(round(v*2) for v in box)

    def ellipse(self, box, fill, outline=INK, width=5):
        self.draw.ellipse(self._box(box), fill=fill, outline=outline, width=round(width*2))

    def rounded(self, box, radius, fill, outline=INK, width=5):
        self.draw.rounded_rectangle(self._box(box), round(radius*2), fill=fill,
                                    outline=outline, width=round(width*2))

    def polygon(self, points, fill, outline=INK, width=5):
        self.draw.polygon([(round(x*2), round(y*2)) for x, y in points],
                          fill=fill, outline=outline, width=round(width*2))

    def line(self, points, fill=INK, width=5):
        self.draw.line([(round(x*2), round(y*2)) for x, y in points], fill=fill,
                       width=round(width*2), joint="curve")

    def arc(self, box, start, end, fill=INK, width=5):
        self.draw.arc(self._box(box), start, end, fill=fill, width=round(width*2))

    def pill(self, points, color, width):
        """An outlined tube with truly round ends and elbows."""
        self.line(points, INK, width+10)
        for x, y in points:
            r = (width+10)/2
            self.ellipse((x-r, y-r, x+r, y+r), INK, None)
        self.line(points, color, width)
        for x, y in points:
            r = width/2
            self.ellipse((x-r, y-r, x+r, y+r), color, None)


def _curve(start, control1, control2, end, steps=20):
    points = []
    for i in range(steps+1):
        t = i/steps
        u = 1-t
        points.append((u*u*u*start[0] + 3*u*u*t*control1[0] + 3*u*t*t*control2[0] + t*t*t*end[0],
                       u*u*u*start[1] + 3*u*u*t*control1[1] + 3*u*t*t*control2[1] + t*t*t*end[1]))
    return points


def _mirror(points):
    return [(600-x, y) for x, y in points]


def _back(c, d):
    secondary, accent = d["secondary_color"], d["accent_color"]
    if d["back"] == "cape":
        cape = [(248, 331), (352, 331)]
        cape += _curve((352, 331), (391, 402), (399, 540), (435, 649))
        cape += [(365, 627), (300, 658), (235, 627), (165, 649)]
        cape += _curve((165, 649), (201, 540), (209, 402), (248, 331))
        c.polygon(cape, secondary)
        c.polygon([(259, 350), (245, 617), (187, 633), (221, 459)], _light(secondary, .18), None)
        c.polygon([(341, 350), (355, 617), (413, 633), (379, 459)], _dark(secondary, .12), None)
        c.line([(262, 379), (242, 603)], _light(secondary, .45), 4)
        c.line([(338, 379), (358, 603)], _dark(secondary, .23), 4)
    elif d["back"] == "wings":
        wing = _curve((247, 356), (207, 288), (129, 225), (45, 248))
        wing += _curve((45, 248), (44, 345), (83, 448), (180, 511))
        wing += _curve((180, 511), (220, 493), (245, 440), (247, 356))
        for points in (wing, _mirror(wing)):
            c.polygon(points, _light(secondary, .32))
        for index, coords in enumerate((
                [(61, 267), (105, 295), (172, 403), (139, 403), (85, 337)],
                [(94, 276), (132, 292), (206, 411), (178, 437), (135, 356)],
                [(134, 292), (166, 316), (225, 397), (208, 455), (188, 398)])):
            color = _light(secondary, .55-index*.09)
            for points in (coords, _mirror(coords)):
                c.polygon(points, color, _light(secondary, .05), 3)
        for x in (220, 380):
            c.ellipse((x-17, 385, x+17, 419), accent, INK, 4)


def _legs(c, d):
    primary, secondary, accent = d["primary_color"], d["secondary_color"], d["accent_color"]
    for side in (-1, 1):
        x = 300+side*45
        c.pill([(x, 526), (x+side*5, 679)], primary, 55)
        if d["body_type"] == "robot":
            c.rounded((x-31, 580, x+31, 622), 14, _light(secondary, .18))
            for y in (590, 601, 612):
                c.line([(x-14, y), (x+14, y)], _dark(secondary, .1), 3)
        else:
            c.line([(x-10, 558), (x-13, 625)], _light(primary, .34), 7)
        if d["boots"] == "round":
            c.rounded((x-35, 660, x+35, 721), 18, secondary)
            c.rounded((x-44, 691, x+40, 739), 20, secondary)
            c.rounded((x-44, 724, x+40, 741), 8, _dark(secondary, .22), INK, 4)
            c.line([(x-19, 681), (x+19, 681)], accent, 8)
            c.line([(x-26, 704), (x+9, 704)], _light(secondary, .52), 5)
        else:
            c.polygon([(x-31, 650), (x+29, 650), (x+35, 691), (x+45, 705),
                       (x+45, 738), (x-43, 738), (x-43, 704), (x-34, 688)], secondary)
            c.polygon([(x-21, 658), (x+19, 658), (x+25, 684), (x-24, 684)], accent, INK, 3)
            c.line([(x-31, 708), (x+34, 708)], _light(secondary, .45), 5)
            c.line([(x-38, 729), (x+39, 729)], INK, 5)


def _arms(c, d):
    primary, secondary, accent = d["primary_color"], d["secondary_color"], d["accent_color"]
    hand_color = d["skin_color"] if d["body_type"] == "kid" else primary
    for side in (-1, 1):
        points = [(300+side*76, 373), (300+side*119, 423), (300+side*130, 483)]
        c.pill(points, primary, 47)
        x = 300+side*130
        if d["body_type"] == "robot":
            c.ellipse((x-21, 426, x+21, 468), secondary)
            c.ellipse((x-9, 438, x+9, 456), accent, INK, 3)
        else:
            c.line([(300+side*110, 421), (300+side*121, 462)], _light(primary, .32), 7)
        if d["gloves"] == "gauntlets":
            c.rounded((x-30, 465, x+30, 526), 19, secondary)
            c.rounded((x-33, 462, x+33, 480), 7, accent, INK, 4)
            c.line([(x-12, 494), (x+12, 494)], _light(secondary, .5), 5)
            c.ellipse((x-side*32-10, 483, x-side*32+10, 507), secondary, INK, 4)
        else:
            c.rounded((x-24, 478, x+24, 526), 18, hand_color)
            c.ellipse((x-side*24-9, 488, x-side*24+9, 509), hand_color, INK, 4)
            c.line([(x+side*5, 510), (x+side*14, 510)], _dark(hand_color, .22), 3)


def _moving_hand(c, d, side, center, angle):
    """Turn the original hand or glove with its forearm, around the wrist."""
    hand = _Canvas()
    hand.image = Image.new('RGBA', (240, 300), (0, 0, 0, 0))
    hand.draw = ImageDraw.Draw(hand.image)
    x, y = 60, 60
    primary, secondary, accent = d['primary_color'], d['secondary_color'], d['accent_color']
    color = d['skin_color'] if d['body_type'] == 'kid' else primary
    if d['gloves'] == 'gauntlets':
        hand.rounded((x-30, y-18, x+30, y+43), 19, secondary)
        hand.rounded((x-33, y-21, x+33, y-3), 7, accent, INK, 4)
        hand.line([(x-12, y+11), (x+12, y+11)], _light(secondary, .5), 5)
        hand.ellipse((x-side*32-10, y, x-side*32+10, y+24), secondary, INK, 4)
    else:
        hand.rounded((x-24, y-5, x+24, y+43), 18, color)
        hand.ellipse((x-side*24-9, y+5, x-side*24+9, y+26), color, INK, 4)
        hand.line([(x+side*5, y+27), (x+side*14, y+27)], _dark(color, .22), 3)
    # All hand pixels lie inside a square centered on the wrist, so rotation
    # cannot clip fingers. The anchor stays in the same place after rotation.
    tile = Image.new('RGBA', (360, 360), (0, 0, 0, 0))
    tile.alpha_composite(hand.image, (60, 60))
    tile = tile.rotate(angle, Image.Resampling.BICUBIC, center=(180, 180))
    c.image.alpha_composite(tile, (round(center[0]*2-180), round(center[1]*2-180)))


def _posed_arms(c, d, pose, phase):
    if pose == 'idle':
        _arms(c, d)
        return
    swing = math.sin(phase*math.tau)
    for side in (-1, 1):
        shoulder = (300+side*76, 373)
        if pose == 'celebrate':
            elbow = (300+side*126, 318)
            wrist = (300+side*(155+6*swing), 236+9*swing)
        elif pose == 'wave' and side == 1:
            elbow = (462, 341)
            wrist = (461+17*swing, 250)
        elif pose == 'talk':
            elbow = (300+side*122, 425)
            wrist = (300+side*(140+5*swing), 468-8*swing)
        else:
            elbow = (300+side*119, 423)
            wrist = (300+side*130, 483)
        c.pill([shoulder, elbow, wrist], d['primary_color'], 47)
        if d['body_type'] == 'robot':
            x, y = elbow
            c.ellipse((x-21, y-21, x+21, y+21), d['secondary_color'])
            c.ellipse((x-9, y-9, x+9, y+9), d['accent_color'], INK, 3)
        else:
            vx, vy = wrist[0]-elbow[0], wrist[1]-elbow[1]
            c.line([(elbow[0]-side*5, elbow[1]+4),
                    (elbow[0]+vx*.65-side*5, elbow[1]+vy*.65)],
                   _light(d['primary_color'], .32), 7)
        angle = 90-math.degrees(math.atan2(wrist[1]-elbow[1], wrist[0]-elbow[0]))
        _moving_hand(c, d, side, wrist, angle)


def _torso(c, d):
    primary, secondary, accent = d["primary_color"], d["secondary_color"], d["accent_color"]
    neck = d["skin_color"] if d["body_type"] == "kid" else primary
    c.rounded((270, 312, 330, 370), 18, neck)
    if d["body_type"] == "robot":
        c.rounded((210, 344, 390, 553), 36, primary)
        c.rounded((230, 369, 370, 517), 24, _light(primary, .42), INK, 4)
        for x in (229, 371):
            c.ellipse((x-6, 356, x+6, 368), accent, INK, 3)
            c.ellipse((x-6, 529, x+6, 541), accent, INK, 3)
        c.rounded((272, 509, 328, 526), 6, secondary, INK, 3)
        for x in (285, 300, 315):
            c.line([(x, 514), (x, 520)], _light(secondary, .7), 3)
    elif d["body_type"] == "creature":
        c.ellipse((204, 337, 396, 568), primary)
        c.ellipse((230, 366, 370, 543), _light(primary, .62), None)
        c.arc((233, 498, 367, 552), 15, 165, _light(primary, .3), 5)
    else:
        c.rounded((217, 342, 383, 555), 51, primary)
        c.polygon([(225, 391), (249, 403), (256, 506), (229, 515)], _dark(primary, .12), None)
        c.polygon([(375, 391), (351, 403), (344, 506), (371, 515)], _dark(primary, .12), None)
        c.arc((239, 346, 361, 427), 25, 155, _light(primary, .36), 5)
    # Shared collar, shoulder caps, and belt make all parts fit all body types.
    for side in (-1, 1):
        x = 300+side*78
        c.ellipse((x-29, 351, x+29, 401), secondary)
        c.arc((x-20, 358, x+20, 390), 190, 305, _light(secondary, .5), 4)
    c.rounded((256, 341, 344, 361), 9, secondary, INK, 4)
    c.rounded((222, 512, 378, 539), 10, secondary)
    c.rounded((281, 509, 319, 542), 7, accent, INK, 4)
    c.line([(290, 519), (310, 519)], _light(accent, .45), 3)


def _badge(c, d):
    kind, accent = d["chest"], d["accent_color"]
    if kind == "none":
        return
    cx, cy = 300, 434
    if kind == "star":
        points = []
        for index in range(10):
            angle = -math.pi/2+index*math.pi/5
            r = 35 if index % 2 == 0 else 16
            points.append((cx+math.cos(angle)*r, cy+math.sin(angle)*r))
        c.polygon(points, accent, INK, 4)
        c.line([(300, 410), (296, 428), (281, 435)], _light(accent, .65), 4)
    elif kind == "bolt":
        c.polygon([(302, 396), (276, 439), (297, 439), (289, 472),
                   (327, 424), (305, 424), (319, 396)], accent, INK, 4)
        c.line([(308, 405), (292, 430)], _light(accent, .6), 4)
    elif kind == "gem":
        c.polygon([(284, 402), (316, 402), (335, 425), (300, 469), (265, 425)], accent, INK, 4)
        c.line([(284, 404), (279, 425), (300, 463), (321, 425), (316, 404)], _dark(accent, .18), 3)
        c.line([(270, 425), (330, 425)], _dark(accent, .18), 3)
        c.polygon([(287, 408), (309, 408), (300, 425), (279, 425)], _light(accent, .58), None)
    else:
        c.ellipse((263, 397, 337, 471), d["secondary_color"], INK, 4)
        c.ellipse((272, 406, 328, 462), accent, INK, 4)
        c.ellipse((282, 416, 318, 452), _light(accent, .73), None)
        c.line([(284, 425), (300, 443), (316, 425)], _dark(accent, .15), 4)


def _head_shape(c, d, color, inset=0, outline=INK, width=6):
    if d["head_shape"] == "round":
        c.rounded((176+inset, 123+inset, 424-inset, 338-inset), 85-inset*.3,
                  color, outline, width)
    else:
        c.polygon([(227+inset*.3, 123+inset), (373-inset*.3, 123+inset),
                   (424-inset, 174+inset*.3), (418-inset, 276-inset*.3),
                   (370-inset*.3, 338-inset), (230+inset*.3, 338-inset),
                   (182+inset, 276-inset*.3), (176+inset, 174+inset*.3)], color, outline, width)


def _head_back(c, d):
    primary, accent = d["primary_color"], d["accent_color"]
    if d["headwear"] == "ears":
        points = [(182, 181), (174, 65), (244, 135)]
        inside = [(191, 149), (188, 92), (221, 135)]
        for outside, inner in ((points, inside), (_mirror(points), _mirror(inside))):
            c.polygon(outside, primary)
            c.polygon(inner, _light(accent, .26), None)
    elif d["headwear"] == "antenna":
        for side in (-1, 1):
            start, tip = (300+side*49, 143), (300+side*71, 78)
            c.pill([start, tip], d["secondary_color"], 12)
            c.ellipse((tip[0]-16, 51, tip[0]+16, 83), accent, INK, 4)
            c.ellipse((tip[0]-8, 57, tip[0], 65), _light(accent, .68), None)
    ear_color = d["skin_color"] if d["body_type"] == "kid" else primary
    for x in (178, 422):
        if d["body_type"] == "robot":
            c.rounded((x-21, 196, x+21, 254), 13, d["secondary_color"])
            c.line([(x-5, 208), (x-5, 241)], _light(d["secondary_color"], .45), 4)
        else:
            c.ellipse((x-18, 209, x+18, 259), ear_color)
            c.arc((x-9, 222, x+9, 246), 110, 260, _dark(ear_color, .16), 3)


def _head(c, d, pose='idle', phase=0):
    primary, secondary, accent = d["primary_color"], d["secondary_color"], d["accent_color"]
    skin = d["skin_color"]
    face = skin if d["body_type"] == "kid" else primary
    _head_shape(c, d, face)
    mask = d["headwear"] == "web_mask"
    helmet = d["headwear"] == "helmet"
    if mask:
        # A generic woven mask leaves the emblem independent of the face piece.
        _head_shape(c, d, primary)
        web = _light(primary, .52)
        for points in ([(300, 129), (300, 206)], [(219, 145), (268, 202)],
                       [(381, 145), (332, 202)], [(181, 207), (235, 222)],
                       [(419, 207), (365, 222)], [(194, 288), (237, 263)],
                       [(406, 288), (363, 263)], [(259, 331), (275, 283)],
                       [(341, 331), (325, 283)]):
            c.line(points, web, 3)
        c.arc((221, 139, 379, 228), 185, 355, web, 3)
        c.arc((193, 160, 407, 272), 185, 355, web, 3)
        c.arc((212, 231, 388, 319), 5, 175, web, 3)
    elif d["body_type"] == "robot":
        _head_shape(c, d, _light(primary, .75), inset=18, outline=INK, width=4)
        for x in (207, 393):
            c.ellipse((x-6, 155, x+6, 167), accent, INK, 2)
    elif d["body_type"] == "creature":
        c.ellipse((226, 248, 374, 328), _light(primary, .64), None)
    else:
        # A little scalloped hairline gives an uncovered kid a finished silhouette.
        c.polygon([(186, 192), (194, 153), (230, 129), (369, 129), (401, 150),
                   (414, 188), (382, 169), (362, 186), (331, 161), (300, 180),
                   (271, 161), (242, 183), (217, 173)], _dark(secondary, .25), INK, 4)
    if helmet:
        # A big open face keeps every choice of eyes legible.
        _head_shape(c, d, secondary)
        c.rounded((195, 166, 405, 316), 58, face, INK, 5)
        if d["body_type"] == "robot":
            c.rounded((206, 178, 394, 305), 50, _light(primary, .76), None)
        c.polygon([(242, 132), (358, 132), (346, 163), (254, 163)], accent, INK, 4)
        c.line([(216, 151), (231, 143)], _light(secondary, .54), 6)
        for x in (183, 417):
            c.ellipse((x-16, 228, x+16, 272), accent, INK, 4)
            c.line([(x, 240), (x, 257)], _dark(accent, .15), 4)
    _eyes(c, d, blink=phase > .80)
    # Always a welcoming smile, even when children mix masks and visors.
    if d["body_type"] == "creature" and not mask and not helmet:
        c.rounded((288, 261, 312, 278), 8, INK, None)
        c.line([(300, 276), (300, 288)], INK, 3)
    elif d["body_type"] == "kid" and not mask:
        c.arc((291, 249, 309, 265), 0, 165, _dark(skin, .2), 3)
    if pose == 'talk' and math.sin(phase*math.tau*2) > -.25:
        opening = 13+4*math.sin(phase*math.tau*2)
        c.ellipse((281, 279, 319, 286+opening), INK, None)
        c.ellipse((287, 287+opening-5, 313, 286+opening), '#EA97A5', None)
    else:
        c.arc((277, 269, 323, 303), 8, 172, INK, 5)
    if not mask and d["eyes"] != "visor":
        blush = _light(accent, .25) if d["body_type"] != "kid" else "#E99B96"
        for x in (231, 369):
            c.ellipse((x-13, 263, x+13, 276), blush, None)


def _eyes(c, d, blink=False):
    eyes = d["eyes"]
    if eyes == "visor":
        c.rounded((209, 201, 391, 254), 25, INK, INK, 4)
        c.rounded((218, 208, 382, 245), 18, "#78DDE2", None)
        if blink:
            c.line([(240, 226), (360, 226)], '#D9FFFF', 4)
            return
        c.line([(238, 215), (269, 215)], "#D9FFFF", 7)
        c.line([(278, 215), (291, 215)], "#D9FFFF", 7)
        c.line([(346, 217), (364, 237)], "#A9F1EF", 7)
        return
    for x in (252, 348):
        if blink:
            c.arc((x-20, 220, x+20, 240), 8, 172, INK, 6)
            continue
        if eyes == "round":
            c.ellipse((x-21, 202, x+21, 254), WHITE, INK, 4)
            c.ellipse((x-10, 215, x+10, 246), INK, None)
            c.ellipse((x-5, 219, x+2, 227), WHITE, None)
        else:
            c.arc((x-21, 214, x+21, 250), 190, 350, INK, 7)
            c.line([(x-16, 215), (x-12, 211)], INK, 4)


def render_design(config: dict, width: int = 600, height: int = 800, *,
                  pose: str = 'idle', phase: float = 0) -> Image.Image:
    """Render a complete original character on a transparent RGBA canvas.

    The full silhouette is contained within the requested size with a clear
    margin, even with wide wings or tall antennae. Nonstandard aspect ratios
    receive transparent letterboxing instead of stretching the character.
    """
    design = validate_design(config)
    if pose not in ('idle', 'wave', 'talk', 'celebrate'):
        raise ValueError('Choose idle, wave, talk, or celebrate for character motion.')
    if isinstance(phase, bool) or not isinstance(phase, (int, float)) or not math.isfinite(phase):
        raise ValueError('Character animation phase must be finite.')
    phase = phase % 1
    if (type(width) is not int or type(height) is not int
            or not 64 <= width <= 2048 or not 64 <= height <= 2048):
        raise ValueError("Character previews must be 64–2048 pixels on each side.")
    c = _Canvas()
    _back(c, design)
    _legs(c, design)
    _posed_arms(c, design, pose, phase)
    _torso(c, design)
    _badge(c, design)
    _head_back(c, design)
    _head(c, design, pose, phase)
    fit = min(width/_SIZE[0], height/_SIZE[1])
    size = (max(1, round(_SIZE[0]*fit)), max(1, round(_SIZE[1]*fit)))
    sprite = c.image.resize(size, Image.Resampling.LANCZOS)
    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    result.alpha_composite(sprite, ((width-size[0])//2, (height-size[1])//2))
    return result
