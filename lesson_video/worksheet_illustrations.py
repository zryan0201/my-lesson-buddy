"""Conservative local counting of repeated, separated colored illustrations.

This recognizes repetition and arithmetic layout, not the meaning of an icon.
It deliberately declines mixed artwork, touching/disconnected parts, and whole
worksheet pages. All returned boxes use original image pixels. No model, API,
credentials, or downloaded assets are used.
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from .worksheet_objects import _components, _filled, _plus, bbox_dict


def _box(component):
    return bbox_dict(component.x, component.y, component.w, component.h)


def _center(component):
    return component.x + component.w / 2, component.y + component.h / 2


def _union(components):
    x, y = min(c.x for c in components), min(c.y for c in components)
    right = max(c.x + c.w for c in components)
    bottom = max(c.y + c.h for c in components)
    return bbox_dict(x, y, right-x, bottom-y)


def _equals_pairs(components, colorful):
    """Find two aligned dark bars, including thick rasterized equals signs."""
    bars = [i for i, c in enumerate(components)
            if not colorful[i] and c.w >= 8 and c.h/c.w <= .38
            and c.area/(c.w*c.h) >= .72]
    pairs = []
    for position, i in enumerate(bars):
        a = components[i]
        for j in bars[position+1:]:
            b = components[j]
            width = max(a.w, b.w)
            gap = abs(_center(a)[1] - _center(b)[1])
            if (min(a.w, b.w)/width >= .8
                    and abs(a.x-b.x) <= max(2, width*.12)
                    and max(a.h, b.h)*1.3 <= gap <= width*.85):
                pairs.append((i, j))
    return pairs


def _possible_join(mask):
    """Decline a deep internal vertical seam, typical of touching counters.

    This is intentionally a conservative rejection, not an object separator.
    Several silhouettes are therefore unsupported even when a person can name
    them. Splitting a connected blob and claiming a count would be less safe.
    """
    h, w = mask.shape
    if w < 16:
        return False
    columns = mask.sum(axis=0)
    for x in range(max(3, int(w*.22)), min(w-3, int(w*.78))):
        left, right = columns[:x], columns[x+1:]
        if (columns[x] < .48*min(left.max(), right.max())
                and left.sum() > .22*mask.sum()
                and right.sum() > .22*mask.sum()):
            return True
    return False


def _ocr_covers(component, ocr, size):
    for line in (ocr or {}).get("lines", []):
        if line.get("confidence", 0) < .65:
            continue
        text = line.get("text", "").strip()
        # Bare arithmetic marks can come from the diagram's operation, and
        # must never certify unrelated dark illustration parts as printing.
        if not re.search(r"[A-Za-z]{2}|[0-9]", text):
            continue
        x, y, w, h = line.get("bbox", (0, 0, 0, 0))
        x, w, y, h = x*size[0], w*size[0], y*size[1], h*size[1]
        # OCR boxes are fallible evidence. A page-sized or implausibly wide
        # box cannot establish that a much smaller dark component is a glyph.
        printed_characters = max(1, len(re.sub(r"\s", "", text)))
        if (not .55*component.h <= h <= 2.25*component.h
                or w > max(2*component.w, 2*h*printed_characters)):
            continue
        intersection = max(0, min(x+w, component.x+component.w)-max(x, component.x)) * max(0, min(y+h, component.y+component.h)-max(y, component.y))
        if intersection >= component.w*component.h*.65:
            return True
    return False


def analyze_illustrations(
    image: Image.Image, ocr: dict | None = None, diagram: dict | None = None,
) -> dict[str, Any] | None:
    """Return one repeated-illustration arithmetic row, or decline it.

    ``None`` means this image has no candidate colored arithmetic row.
    ``ValueError`` means a candidate exists but is ambiguous. A caller must
    reconcile returned evidence with all OCR instructions/numbers before using
    the ``question``. ``diagram`` is accepted for integration convenience; the
    signs are independently checked at source resolution because thick equals
    bars may not satisfy the stricter primitive geometry classifier.

    Supported rows have at least one complete icon on either side of a single
    plus/minus, followed by an equals sign. Icons must have matching appearance,
    size, and vertical alignment. Only small crop-edge fragments wholly outside
    this row may be ignored, with explicit evidence in ``ignored_regions``.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("analyze_illustrations expects a Pillow Image.")
    source = ImageOps.exif_transpose(image).convert("RGBA")
    flat = Image.new("RGBA", source.size, "white")
    flat.alpha_composite(source)
    source = flat.convert("RGB")
    rgb = np.asarray(source, dtype=np.int16)
    low, high = rgb.min(axis=2), rgb.max(axis=2)
    if (low >= 210).mean() < .64:
        return None
    chromatic = (high-low >= 40) & (low < 215) & (high > 95)
    mask = chromatic | (high < 165)
    if mask.mean() > .34:
        return None
    components = [c for c in _components(mask) if c.area >= 5]
    colorful = [int((chromatic[c.y:c.y+c.h, c.x:c.x+c.w] & c.mask()).sum())
                >= max(4, c.area*.18) for c in components]
    art_indices = [i for i, c in enumerate(components)
                   if colorful[i] and min(c.w, c.h) >= 10 and c.area >= 50]
    if not art_indices:
        return None
    plus_indices = [i for i, c in enumerate(components)
                    if not colorful[i] and _plus(c.mask())]
    equals_pairs = _equals_pairs(components, colorful)
    equals_members = {i for pair in equals_pairs for i in pair}
    minus_indices = [i for i, c in enumerate(components)
                     if i not in equals_members and not colorful[i]
                     and c.w >= 8 and c.h/c.w <= .25
                     and c.area/(c.w*c.h) >= .72]
    if not plus_indices and not minus_indices:
        return None

    candidates = []
    for sign_index in plus_indices + minus_indices:
        sign = components[sign_index]
        sx, sy = _center(sign)
        row = [i for i in art_indices
               if components[i].y <= sy <= components[i].y+components[i].h]
        if not row:
            continue
        equal = []
        for pair in equals_pairs:
            box = _union([components[i] for i in pair])
            if (box["x"] > sx and abs(box["y"]+box["height"]/2-sy)
                    <= max(4, float(np.median([components[i].h for i in row]))*.22)):
                equal.append(pair)
        if len(equal) != 1:
            raise ValueError("A repeated-artwork row needs one clear equals sign after its two groups.")
        pair = equal[0]
        ex = min(components[i].x for i in pair)
        left = [i for i in row if components[i].x+components[i].w < sign.x]
        right = [i for i in row if components[i].x > sign.x+sign.w
                 and components[i].x+components[i].w < ex]
        if not left or not right or set(left+right) != set(row):
            raise ValueError("Both pictured groups must be complete, separated, and before the equals sign.")
        candidates.append((sign_index, pair, left, right))
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValueError("More than one illustrated arithmetic row is visible. Crop one question.")
    sign_index, equal_pair, left, right = candidates[0]
    indices = sorted(left+right, key=lambda i: components[i].x)
    icons = [components[i] for i in indices]
    heights = np.array([c.h for c in icons], dtype=float)
    widths = np.array([c.w for c in icons], dtype=float)
    median_height = float(np.median(heights))
    if max(heights)/min(heights) > 1.22 or max(widths)/min(widths) > 1.22:
        raise ValueError("The pictured objects differ in size or may be touching; the count needs review.")
    centers = [_center(c)[1] for c in icons]
    if max(centers)-min(centers) > median_height*.20:
        raise ValueError("The pictured objects are not aligned in one clear arithmetic row.")
    if any(c.x == 0 or c.y == 0 or c.x+c.w >= source.width
           or c.y+c.h >= source.height for c in icons):
        raise ValueError("A pictured object touches the crop edge. Include the complete objects.")
    for a, b in zip(icons, icons[1:]):
        if b.x-a.x-a.w < 2:
            raise ValueError("The objects are too close to distinguish separate illustrations safely.")
    if any(_possible_join(c.mask()) for c in icons):
        raise ValueError("An illustration may contain touching objects; use separated complete pictures.")

    silhouettes, colors = [], []
    for c in icons:
        silhouettes.append(np.asarray(Image.fromarray(c.mask()).resize((40, 40), Image.Resampling.NEAREST), dtype=bool))
        colors.append(np.asarray(source.crop((c.x, c.y, c.x+c.w, c.y+c.h))
                                 .resize((40, 40), Image.Resampling.BILINEAR), dtype=float)/255)
    minimum_iou, maximum_color_error = 1., 0.
    for i in range(len(icons)):
        for j in range(i):
            iou = float((silhouettes[i] & silhouettes[j]).sum()/max(1, (silhouettes[i] | silhouettes[j]).sum()))
            error = float(np.abs(colors[i]-colors[j]).mean())
            minimum_iou, maximum_color_error = min(minimum_iou, iou), max(maximum_color_error, error)
    if minimum_iou < .80 or maximum_color_error > .12:
        raise ValueError("The pictured objects do not have matching artwork; mixed or unclear illustrations need review.")

    used = set(indices) | {sign_index, *equal_pair}
    top, bottom = min(c.y for c in icons), max(c.y+c.h for c in icons)
    equal_right = max(components[i].x+components[i].w for i in equal_pair)
    ignored, answers, text_regions = [], [], []
    for i, c in enumerate(components):
        if i in used:
            continue
        edge = c.x == 0 or c.y == 0 or c.x+c.w >= source.width or c.y+c.h >= source.height
        outside = c.y+c.h < top or c.y > bottom
        if outside and edge and c.h <= median_height*.35:
            ignored.append({"bbox": _box(c), "reason": "Small incomplete neighboring-row fragment at the crop edge, wholly outside the arithmetic row."})
            continue
        # A single blank, dark, closed outline after '=' is an answer field.
        if (not colorful[i] and c.x > equal_right
                and min(c.w, c.h) >= 15 and .55 <= c.w/c.h <= 1.8
                and abs(_center(c)[1]-np.median(centers)) <= median_height*.25
                and c.area/(c.w*c.h) < .4):
            filled, holes = _filled(c.mask())
            if holes == 1 and filled.mean() >= .78:
                answers.append({"bbox": _box(c), "reason": "Blank outlined answer field after the equals sign."})
                continue
        if not colorful[i] and _ocr_covers(c, ocr, source.size):
            text_regions.append({"bbox": _box(c), "reason": "Mark covered by OCR; caller must reconcile the printed instruction."})
            continue
        raise ValueError("Additional marks or disconnected illustration parts are visible. Crop one clean arithmetic question.")
    if len(answers) > 1:
        raise ValueError("Multiple possible answer fields are visible. Crop one arithmetic question.")
    a, b = len(left), len(right)
    addition = sign_index in plus_indices
    if a > 10 or b > 10 or (addition and a+b > 10) or (not addition and b > a):
        raise ValueError("The illustrated arithmetic is outside the supported nonnegative 0–10 lesson range.")
    sign = "+" if addition else "-"
    confidence = round(min(.97, minimum_iou, 1-maximum_color_error), 3)
    objects = [{"shape": "illustration", "bbox": _box(c), "confidence": confidence,
                "requires_text_check": False, "outlined": False,
                "evidence": "One separated colored component matching the other complete illustrations."}
               for c in icons]
    symbols = [{"kind": "plus" if addition else "minus", "bbox": _box(components[sign_index]), "confidence": .94},
               {"kind": "equals", "bbox": _union([components[i] for i in equal_pair]), "confidence": .94}]
    groups = []
    for side in (left, right):
        object_indices = [indices.index(i) for i in side]
        groups.append({"object_indices": object_indices, "count": len(side),
                       "bbox": _union([components[i] for i in side])})
    return {"objects": objects, "symbols": symbols, "groups": groups,
            "repeated_illustrations_verified": True,
            "uncertain_regions": [], "text_candidates": text_regions,
            "operation": "addition" if addition else "subtraction",
            "left_count": a, "right_count": b, "question": f"What is {a} {sign} {b}?",
            "row_bbox": _union(icons+[components[sign_index]]+[components[i] for i in equal_pair]),
            "ignored_regions": ignored, "answer_regions": answers,
            "similarity": {"minimum_silhouette_iou": round(minimum_iou, 4),
                           "maximum_normalized_color_error": round(maximum_color_error, 4)},
            "confidence": confidence,
            "warnings": ["Object identity is not inferred; this count uses repeated matching artwork."]
                        + (["Small incomplete neighboring-row fragments were excluded outside the arithmetic row."] if ignored else []),
            "image_width": source.width, "image_height": source.height}
