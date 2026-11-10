"""Conservative, local geometry reader for clean K–2 worksheet diagrams.

This is a shape detector, not an OCR system or a general image understanding
model. It accepts a light worksheet background and separated, regular circles,
triangles, squares, and rectangles. Its output is evidence for the worksheet
reader; the caller must reconcile it with OCR and the question's wording.

``analyze_diagram(image)`` returns JSON-compatible dictionaries with source-image
pixel coordinates. ``objects`` contains recognized shapes. ``uncertain_regions``
contains colored or substantial diagram marks which cannot safely be counted.
``text_candidates`` preserves other dark components for OCR. A single horizontal
line is an ambiguous minus/answer blank; it must be interpreted from layout.
Outlined shapes additionally need OCR exclusion, since a printed O and an
outlined circle can have exactly the same geometry, including in colored text.

Only Pillow and NumPy are used. No model download, network access, or API call
is made by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageOps


def bbox_dict(x: int, y: int, width: int, height: int) -> dict[str, int]:
    """Return the public source-pixel bbox format (xywh, not xyxy)."""
    return {"x": int(x), "y": int(y), "width": int(width), "height": int(height)}


@dataclass
class _Component:
    x: int
    y: int
    w: int
    h: int
    area: int
    runs: list[tuple[int, int, int]]

    def mask(self) -> np.ndarray:
        result = np.zeros((self.h, self.w), dtype=bool)
        for y, left, right in self.runs:
            result[y - self.y, left - self.x:right - self.x + 1] = True
        return result


def _components(mask: np.ndarray, limit: int = 2500) -> list[_Component]:
    """Label 8-connected foreground through row runs, avoiding per-pixel BFS."""
    parents: list[int] = []
    rows: list[tuple[int, int, int, int]] = []
    previous: list[tuple[int, int, int]] = []

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for y, row in enumerate(mask):
        changes = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1) - 1
        current = []
        previous_index = 0
        for left, right in zip(starts.tolist(), ends.tolist()):
            label = len(parents)
            parents.append(label)
            while previous_index < len(previous) and previous[previous_index][1] < left - 1:
                previous_index += 1
            p = previous_index
            while p < len(previous) and previous[p][0] <= right + 1:
                a, b = find(label), find(previous[p][2])
                if a != b:
                    parents[a] = b
                p += 1
            current.append((left, right, label))
            rows.append((y, left, right, label))
        previous = current
        # Highly textured images must not consume unbounded time or memory.
        if len(rows) > 150000:
            raise ValueError("Too many marks for a clean worksheet diagram.")

    buckets: dict[int, list[tuple[int, int, int]]] = {}
    for y, left, right, label in rows:
        buckets.setdefault(find(label), []).append((y, left, right))
    if len(buckets) > limit:
        raise ValueError("Too many separate marks for a clean worksheet diagram.")
    result = []
    for runs in buckets.values():
        left = min(r[1] for r in runs)
        right = max(r[2] for r in runs)
        top, bottom = runs[0][0], runs[-1][0]
        result.append(_Component(left, top, right-left+1, bottom-top+1,
                                 sum(r[2]-r[1]+1 for r in runs), runs))
    return result


def _filled(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Fill closed outline holes and count meaningful enclosed components."""
    padded = np.pad(mask.astype(np.uint8) * 255, 1)
    # fromarray may expose a read-only buffer; floodfill needs owned pixels.
    raster = Image.fromarray(padded, mode="L").copy()
    ImageDraw.floodfill(raster, (0, 0), 128)
    exterior = np.asarray(raster)[1:-1, 1:-1]
    holes = exterior == 0
    minimum = max(4, int(mask.size * 0.008))
    hole_count = sum(c.area >= minimum for c in _components(holes, limit=500))
    return exterior != 128, hole_count


def _hull(mask: np.ndarray) -> list[tuple[int, int]]:
    points = []
    for y, row in enumerate(mask):
        x = np.flatnonzero(row)
        if len(x):
            points.extend(((int(x[0]), y), (int(x[-1]), y)))
    ordered = sorted(set(points))
    if len(ordered) < 3:
        return ordered

    def cross(o: tuple[int, int], a: tuple[int, int], b: tuple[int, int]) -> int:
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])

    lower: list[tuple[int, int]] = []
    upper: list[tuple[int, int]] = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _distance(point: tuple[int, int], a: tuple[int, int], b: tuple[int, int]) -> float:
    denominator = math.hypot(b[0]-a[0], b[1]-a[1])
    if denominator == 0:
        return math.hypot(point[0]-a[0], point[1]-a[1])
    return abs((b[1]-a[1])*point[0] - (b[0]-a[0])*point[1]
               + b[0]*a[1] - b[1]*a[0]) / denominator


def _corners(hull: list[tuple[int, int]], tolerance: float) -> list[tuple[int, int]]:
    simplified = hull.copy()
    while len(simplified) > 3:
        distances = [_distance(p, simplified[i-1], simplified[(i+1) % len(simplified)])
                     for i, p in enumerate(simplified)]
        smallest = min(distances)
        if smallest > tolerance:
            break
        simplified.pop(distances.index(smallest))
    return simplified


def _shape(mask: np.ndarray) -> tuple[str, float, bool]:
    h, w = mask.shape
    if min(w, h) < 10 or max(w, h) / min(w, h) > 4.0:
        return "unknown", 0.0, False
    filled, holes = _filled(mask)
    outline = mask.sum() / max(int(filled.sum()), 1) < .70
    if holes > 1:
        return "unknown", 0.0, outline
    hull = _hull(filled)
    if len(hull) < 3:
        return "unknown", 0.0, outline
    hull_image = Image.new("1", (w, h))
    ImageDraw.Draw(hull_image).polygon(hull, fill=1)
    hull_mask = np.asarray(hull_image, dtype=bool)
    solidity = filled.sum() / max(int(hull_mask.sum()), 1)
    if solidity < .94:
        # Touching counters and many letters form a concave silhouette.
        return "unknown", 0.0, outline
    aspect = w / h
    yy, xx = np.mgrid[:h, :w]
    ideal_circle = (((xx-(w-1)/2) / (w/2))**2
                    + ((yy-(h-1)/2) / (h/2))**2) <= 1.0
    iou = (filled & ideal_circle).sum() / max(int((filled | ideal_circle).sum()), 1)
    # A circle needs close-to-equal axes; ordinary printed zeros are narrower.
    if .86 <= aspect <= 1.16 and iou >= .915:
        return "circle", round(float(min(.99, .89 + (iou-.915)*1.15)), 3), outline
    corners = _corners(hull, max(1.0, math.hypot(w, h) * .025))
    polygon = Image.new("1", (w, h))
    ImageDraw.Draw(polygon).polygon(corners, fill=1)
    polygon_mask = np.asarray(polygon, dtype=bool)
    polygon_iou = (filled & polygon_mask).sum() / max(int((filled | polygon_mask).sum()), 1)
    if len(corners) == 3 and polygon_iou >= .94:
        if min(w, h) >= 16:
            return "triangle", round(float(min(.98, .88+(polygon_iou-.94))), 3), outline
    if len(corners) == 4 and polygon_iou >= .955:
        angles_ok = True
        side_lengths = []
        for i, vertex in enumerate(corners):
            before, after = corners[i-1], corners[(i+1) % 4]
            va = np.array(before, float) - vertex
            vb = np.array(after, float) - vertex
            denominator = float(np.linalg.norm(va) * np.linalg.norm(vb))
            if denominator == 0 or abs(float(va @ vb) / denominator) > .14:
                angles_ok = False
            side_lengths.append(float(np.linalg.norm(vb)))
        if angles_ok and min(side_lengths) >= 12:
            ratio = max(side_lengths) / min(side_lengths)
            name = "square" if ratio <= 1.13 else "rectangle"
            return name, round(float(min(.99, .91+(polygon_iou-.955))), 3), outline
    return "unknown", 0.0, outline


def _plus(mask: np.ndarray) -> float:
    h, w = mask.shape
    if min(h, w) < 8 or not .65 <= w/h <= 1.55:
        return 0.0
    horizontal = np.flatnonzero(mask.sum(axis=1) >= .85*w)
    vertical = np.flatnonzero(mask.sum(axis=0) >= .85*h)
    if not len(horizontal) or not len(vertical):
        return 0.0
    if len(horizontal) > .4*h or len(vertical) > .4*w:
        return 0.0
    if not (.28*h <= horizontal.mean() <= .72*h
            and .28*w <= vertical.mean() <= .72*w):
        return 0.0
    ideal = np.zeros_like(mask)
    ideal[horizontal[0]:horizontal[-1]+1] = True
    ideal[:, vertical[0]:vertical[-1]+1] = True
    iou = (mask & ideal).sum() / max(int((mask | ideal).sum()), 1)
    return round(float(iou), 3) if iou >= .86 else 0.0


def _public_bbox(component: _Component, scale: float, original: tuple[int, int]) -> dict[str, int]:
    x, y = round(component.x / scale), round(component.y / scale)
    right = min(original[0], round((component.x+component.w) / scale))
    bottom = min(original[1], round((component.y+component.h) / scale))
    return bbox_dict(x, y, max(1, right-x), max(1, bottom-y))


def _union_bbox(boxes: list[dict[str, int]]) -> dict[str, int]:
    x = min(b["x"] for b in boxes)
    y = min(b["y"] for b in boxes)
    right = max(b["x"]+b["width"] for b in boxes)
    bottom = max(b["y"]+b["height"] for b in boxes)
    return bbox_dict(x, y, right-x, bottom-y)


def _group_objects(objects: list[dict[str, Any]], symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group counters by separators and obvious large spatial gaps only."""
    if not objects:
        return []
    median = float(np.median([max(o["bbox"]["width"], o["bbox"]["height"]) for o in objects]))
    # Arithmetic symbols are separators only if their vertical position lies
    # inside the diagram band; blanks underneath do not divide a counter group.
    top = min(o["bbox"]["y"] for o in objects)
    bottom = max(o["bbox"]["y"]+o["bbox"]["height"] for o in objects)
    cuts = sorted(s["bbox"]["x"]+s["bbox"]["width"]/2 for s in symbols
                  if top <= s["bbox"]["y"]+s["bbox"]["height"]/2 <= bottom)
    partitions: dict[int, list[int]] = {}
    for index, obj in enumerate(objects):
        center = obj["bbox"]["x"]+obj["bbox"]["width"]/2
        partition = sum(center > cut for cut in cuts)
        partitions.setdefault(partition, []).append(index)
    groups = []
    for indices in partitions.values():
        ordered = sorted(indices, key=lambda i: objects[i]["bbox"]["x"])
        chunks = [[]]
        last_right = None
        for index in ordered:
            box = objects[index]["bbox"]
            if last_right is not None and box["x"]-last_right > median * 2.0:
                chunks.append([])
            chunks[-1].append(index)
            last_right = max(last_right or 0, box["x"]+box["width"])
        for chunk in chunks:
            groups.append({"object_indices": chunk, "count": len(chunk),
                           "bbox": _union_bbox([objects[i]["bbox"] for i in chunk])})
    return sorted(groups, key=lambda g: (g["bbox"]["y"], g["bbox"]["x"]))


def analyze_diagram(image: Image.Image) -> dict[str, Any]:
    """Detect separated worksheet primitives, retaining uncertainty evidence.

    The result does not itself establish that a worksheet asks for counting or
    addition. Interpretation belongs to the caller after OCR reconciliation.
    All bboxes use the original, EXIF-oriented image's pixel coordinate system.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("analyze_diagram expects a Pillow Image.")
    source = ImageOps.exif_transpose(image).convert("RGBA")
    white = Image.new("RGBA", source.size, "white")
    white.alpha_composite(source)
    source = white.convert("RGB")
    original = source.size
    result: dict[str, Any] = {
        "objects": [], "symbols": [], "groups": [], "uncertain_regions": [],
        "text_candidates": [], "warnings": [], "confidence": 0.0,
        "image_width": original[0], "image_height": original[1],
    }
    if min(original) < 25:
        result["warnings"].append("Image is too small to count diagram objects reliably.")
        return result
    scale = min(1.0, 1600/max(original))
    if scale < 1:
        source = source.resize((round(original[0]*scale), round(original[1]*scale)), Image.Resampling.LANCZOS)
    rgb = np.asarray(source, dtype=np.int16)
    low, high = rgb.min(axis=2), rgb.max(axis=2)
    light = low >= 210
    if float(light.mean()) < .64:
        result["warnings"].append("Use a clean, cropped worksheet on a light background; this image has too much background texture or ink.")
        return result
    chromatic = (high-low >= 40) & (low < 215) & (high > 95)
    dark = high < 165
    mask = chromatic | dark
    if float(mask.mean()) > .34:
        result["warnings"].append("The picture is too dense to distinguish separated worksheet objects safely.")
        return result
    try:
        components = _components(mask)
    except ValueError as exc:
        result["warnings"].append(str(exc))
        return result
    bars: list[tuple[_Component, dict[str, Any]]] = []
    for component in components:
        if component.area < 5 or max(component.w, component.h) < 5:
            continue
        component_mask = component.mask()
        box = _public_bbox(component, scale, original)
        crop_color = chromatic[component.y:component.y+component.h, component.x:component.x+component.w]
        colorful = (crop_color & component_mask).sum() > max(3, component.area*.18)
        touching_edge = (component.x <= 0 or component.y <= 0
                         or component.x+component.w >= mask.shape[1]
                         or component.y+component.h >= mask.shape[0])
        fill_ratio = component.area / (component.w*component.h)
        if not colorful and component.w >= 8 and component.h/component.w <= .25 and fill_ratio >= .72:
            bars.append((component, {"kind": "minus", "bbox": box, "confidence": .72,
                                     "ambiguous": True, "note": "Could also be an answer underline."}))
            continue
        if not colorful:
            plus_confidence = _plus(component_mask)
            if plus_confidence:
                result["symbols"].append({"kind": "plus", "bbox": box,
                                          "confidence": plus_confidence})
                continue
        shape, confidence, outlined = _shape(component_mask)
        if shape != "unknown" and not touching_edge:
            if colorful:
                pixels = rgb[component.y:component.y+component.h, component.x:component.x+component.w][component_mask]
                median_color = np.median(pixels, axis=0).astype(int).tolist()
            else:
                median_color = [0, 0, 0]
            result["objects"].append({"shape": shape, "bbox": box,
                                      "confidence": confidence, "outlined": bool(outlined),
                                      "color": "#"+"".join(f"{c:02x}" for c in median_color),
                                      "requires_text_check": bool(outlined)})
        elif colorful:
            reason = ("Colored mark touches the crop edge; a complete object is required."
                      if touching_edge else "Colored mark is not one separated regular shape; objects may touch or overlap.")
            result["uncertain_regions"].append({"bbox": box, "reason": reason})
        else:
            result["text_candidates"].append({"bbox": box, "reason": "Dark mark retained for OCR; not confidently a diagram shape."})

    used_bars: set[int] = set()
    for index, (first, public_first) in enumerate(bars):
        if index in used_bars:
            continue
        matches = []
        for other_index, (second, _) in enumerate(bars):
            if other_index <= index or other_index in used_bars:
                continue
            max_width = max(first.w, second.w)
            center_gap = abs(first.y+first.h/2 - second.y-second.h/2)
            if (min(first.w, second.w)/max_width >= .78
                    and abs(first.x-second.x) <= max(3, max_width*.16)
                    and max(first.h, second.h)*1.3 <= center_gap <= max_width*.75
                    and center_gap >= max_width*.10):
                matches.append((center_gap, other_index))
        if matches:
            _, matched = min(matches)
            used_bars.update((index, matched))
            result["symbols"].append({"kind": "equals", "bbox": _union_bbox([public_first["bbox"], bars[matched][1]["bbox"]]),
                                      "confidence": .94})
        else:
            result["symbols"].append(public_first)
    result["objects"].sort(key=lambda o: (o["bbox"]["x"], o["bbox"]["y"]))
    result["symbols"].sort(key=lambda s: (s["bbox"]["x"], s["bbox"]["y"]))
    result["groups"] = _group_objects(result["objects"], result["symbols"])
    if len(result["objects"]) > 10:
        result["warnings"].append("More than 10 diagram objects were found; this exceeds the current lesson range.")
    if any(o["requires_text_check"] for o in result["objects"]):
        result["warnings"].append("Exclude OCR letters and digits before using outlined shapes as counters.")
    if result["uncertain_regions"]:
        result["warnings"].append("Some colored marks could not be safely recognized; do not infer a total count.")
    if result["objects"] and not result["uncertain_regions"] and len(result["objects"]) <= 10:
        result["confidence"] = round(min(o["confidence"] for o in result["objects"]), 3)
    return result
