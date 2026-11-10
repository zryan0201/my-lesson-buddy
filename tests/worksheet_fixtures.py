"""Generate hand-labeled synthetic worksheet fixtures with Pillow only.

Run ``python3 tests/worksheet_fixtures.py`` from any directory. The default
destination is ``examples/worksheets`` in this repository. These clean,
deliberately bounded examples test a reader contract; they are not validation
data for photographs, handwriting, or arbitrary school worksheets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


WIDTH, HEIGHT = 1200, 680
INK = "#151B25"
ROOT = Path(__file__).resolve().parents[1]
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
)


def font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    raise RuntimeError("A scalable Arial or DejaVu Sans font is required.")


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    return image, ImageDraw.Draw(image)


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str,
         size: int = 56, color: str = INK) -> None:
    draw.text(xy, value, font=font(size), anchor="mm", fill=color)


def heading(draw: ImageDraw.ImageDraw, value: str) -> None:
    text(draw, (WIDTH // 2, 80), value, 46)


def circle(draw: ImageDraw.ImageDraw, xy: tuple[int, int], radius: int = 38,
           fill: str | None = "#F4BD00", outline: str | None = None,
           width: int = 6) -> None:
    x, y = xy
    draw.ellipse((x-radius, y-radius, x+radius, y+radius),
                 fill=fill, outline=outline, width=width)


def accept(lesson_type: str, question: str, answer: int | str,
           a: int | None = None, b: int | None = None,
           unknown: str = "result", **extras: str) -> dict:
    return {
        "status": "accept",
        "lesson_type": lesson_type,
        "canonical_question": question,
        "a": a,
        "b": b,
        "unknown": unknown,
        "answer": answer,
        **extras,
    }


def reject(reason_code: str, reason: str) -> dict:
    return {"status": "reject", "reason_code": reason_code, "reason": reason}


def generate(destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    cases = []

    def save(case_id: str, image: Image.Image, description: str,
             expected: dict, observations: dict | None = None) -> None:
        filename = case_id + ".png"
        path = destination / filename
        image.save(path, format="PNG", optimize=False)
        case = {
            "id": case_id,
            "image": filename,
            "description": description,
            "size": list(image.size),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "expected": expected,
        }
        if observations:
            case["observations"] = observations
        cases.append(case)

    image, draw = canvas()
    heading(draw, "Solve.")
    text(draw, (600, 340), "4 + 3 = ?", 100)
    save("01_numeric_addition", image, "One printed addition equation, unknown result.",
         accept("addition", "What is 4 + 3?", 7, 4, 3))

    image, draw = canvas()
    heading(draw, "Find the answer.")
    # A centered subtraction dash is deliberately different from a low blank.
    text(draw, (600, 340), "8 - 3 = ?", 100)
    save("02_numeric_subtraction", image, "One subtraction equation with a centered minus sign.",
         accept("subtraction", "What is 8 - 3?", 5, 8, 3))

    image, draw = canvas()
    heading(draw, "How many dots altogether?")
    for point in [(180, 245), (120, 355), (240, 355)]:
        circle(draw, point, fill="#F2BE00")
    for point in [(625, 300), (755, 300)]:
        circle(draw, point, fill="#F2BE00")
    text(draw, (425, 300), "+", 86)
    text(draw, (900, 300), "=", 86)
    text(draw, (1050, 300), "?", 86)
    save("03_yellow_dot_addition", image,
         "Three filled yellow circles in a triangle, plus two horizontally arranged circles.",
         accept("addition", "What is 3 + 2?", 5, 3, 2),
         {"left_objects": 3, "right_objects": 2, "object_style": "filled_yellow_circles"})

    image, draw = canvas()
    heading(draw, "Add the groups.")
    for point in [(180, 240), (180, 365)]:
        circle(draw, point, fill=None, outline="#166B93")
    for point in [(630, 240), (755, 240), (630, 365), (755, 365)]:
        circle(draw, point, fill=None, outline="#166B93")
    text(draw, (425, 300), "+", 86)
    text(draw, (900, 300), "=", 86)
    text(draw, (1050, 300), "?", 86)
    save("04_outlined_dot_addition", image,
         "Two vertically arranged blue outlines plus four blue outlines in a square layout.",
         accept("addition", "What is 2 + 4?", 6, 2, 4),
         {"left_objects": 2, "right_objects": 4, "object_style": "outlined_blue_circles"})

    image, draw = canvas()
    heading(draw, "Count the dots.")
    for y in [245, 430]:
        for x in [300, 600, 900]:
            circle(draw, (x, y), radius=43, fill="#D73642")
    text(draw, (600, 585), "There are ____ dots.", 48)
    save("05_count_red_circles", image, "Six red circles in two rows with an explicit counting instruction.",
         accept("counting", "Count 6 dots.", 6, 6, unknown="count"))

    image, draw = canvas()
    heading(draw, "How many straight sides?")
    draw.polygon([(600, 185), (400, 465), (800, 465)],
                 fill="#FFD45E", outline=INK, width=5)
    text(draw, (600, 585), "____ sides", 48)
    save("06_triangle_sides", image, "A single triangle and an explicit straight-side-count question.",
         accept("shape", "How many straight sides does a triangle have?", 3,
                unknown="side_count", shape="triangle", shape_task="sides"))

    image, draw = canvas()
    heading(draw, "What shape is this?")
    draw.rectangle((440, 185, 760, 505), outline="#2856A4", width=8)
    draw.line([(400, 600), (800, 600)], fill=INK, width=3)
    save("07_outlined_square_name", image, "One outlined blue square and a shape-name question.",
         accept("shape", "Identify a square.", "square", unknown="shape_name",
                shape="square", shape_task="name"))

    image, draw = canvas()
    heading(draw, "What shape is this?")
    draw.rectangle((330, 235, 870, 475), fill="#66C9D1", outline=INK, width=5)
    draw.line([(400, 600), (800, 600)], fill=INK, width=3)
    save("08_filled_rectangle_name", image,
         "One filled cyan non-square rectangle and a shape-name question.",
         accept("shape", "Identify a rectangle.", "rectangle", unknown="shape_name",
                shape="rectangle", shape_task="name"))

    image, draw = canvas()
    heading(draw, "Solve each problem.")
    text(draw, (600, 255), "1.   4 + 3 = ?", 82)
    draw.line([(130, 350), (1070, 350)], fill="#BFC4CA", width=2)
    text(draw, (600, 460), "2.   8 - 3 = ?", 82)
    save("09_multiple_questions", image, "Two distinct arithmetic questions in one uncropped worksheet.",
         reject("multiple_questions", "Require the user to crop or select one question; do not silently choose one."))

    image, draw = canvas()
    rng = random.Random(417)
    for _ in range(95):
        x, y = rng.randint(100, 1100), rng.randint(150, 550)
        r = rng.randint(2, 13)
        shade = rng.randint(237, 250)
        draw.ellipse((x-r, y-r, x+r, y+r), fill=(shade, shade, shade))
    text(draw, (600, 340), "4 + 3 = ?", 82, "#F0F0F0")
    image = image.filter(ImageFilter.GaussianBlur(19))
    save("10_unreadable_near_blank", image, "Very faint, heavily blurred marks; no confidently readable problem.",
         reject("unreadable", "No reliable question is visible. Do not infer digits from noise or supply a default problem."))

    image, draw = canvas()
    heading(draw, "Count the dots.")
    # Unscoped dot decorations deliberately resemble the exercise's counters.
    for point in [(80, 70), (1120, 70), (80, 590), (1120, 590)]:
        circle(draw, point, radius=16, fill="#E5AC20")
    for y in [250, 420]:
        for x in [300, 600, 900]:
            circle(draw, (x, y), radius=40, fill="#C63F54")
    text(draw, (600, 585), "____", 50)
    save("11_unscoped_decorative_dots", image,
         "Six large red counters and four small yellow decorative dots without a target-size/color scope.",
         reject("ambiguous_count_target", "This bounded reader must not decide which dots are decoration. Require a tighter crop or an explicit color/size target."),
         {"large_red_objects": 6, "small_yellow_objects": 4,
          "note": "Conservative reader-policy rejection; this is not a claim that counting every visible dot is mathematically invalid."})

    image, draw = canvas()
    heading(draw, "How many?")
    points = [(200, 320), (400, 320), (600, 320), (800, 320), (1000, 320)]
    for point in points:
        circle(draw, point, radius=43, fill="#69AD7A")
    for x, y in points[-2:]:
        draw.line([(x-51, y-51), (x+51, y+51)], fill="#2B2B2B", width=8)
        draw.line([(x+51, y-51), (x-51, y+51)], fill="#2B2B2B", width=8)
    draw.line([(430, 575), (770, 575)], fill=INK, width=3)
    save("12_crossouts_without_instruction", image,
         "Five circles, two crossed out, and an unspecific question; no subtraction caption or equation.",
         reject("ambiguous_crossouts", "Crosses alone do not establish whether to count originals, remaining objects, or marked objects."),
         {"original_objects": 5, "crossed_out_objects": 2})

    image, draw = canvas()
    heading(draw, "Fill in the blank.")
    text(draw, (510, 340), "0 + 4 =", 100)
    draw.line([(825, 386), (1050, 386)], fill=INK, width=5)
    save("13_zero_operand_blank_result", image,
         "A supported zero operand with a low result blank; the blank is not a minus sign.",
         accept("addition", "What is 0 + 4?", 4, 0, 4))

    image, draw = canvas()
    heading(draw, "Solve.")
    text(draw, (600, 340), "8 + 5 = ?", 100)
    save("14_total_above_supported_limit", image, "Readable operands individually in range, but total exceeds ten.",
         reject("out_of_range_total", "Eight plus five is thirteen, outside the supported total of at most ten."),
         {"a": 8, "b": 5, "mathematical_answer": 13})

    image, draw = canvas()
    heading(draw, "Fill in the missing number.")
    text(draw, (315, 340), "4 +", 100)
    draw.line([(445, 386), (680, 386)], fill=INK, width=5)
    text(draw, (850, 340), "= 7", 100)
    save("15_missing_addend", image, "The second addend is unknown; seven is the given total.",
         reject("unsupported_unknown_location", "Do not rewrite 4 + blank = 7 as 4 + 7 = ?. Missing-addend lessons are outside the result-unknown contract."),
         {"given_first_addend": 4, "given_total": 7, "mathematical_missing_addend": 3})

    image, draw = canvas()
    heading(draw, "Check this number sentence.")
    text(draw, (600, 340), "4 + 3 = 8", 100)
    save("16_inconsistent_printed_answer", image,
         "A completed equation whose printed answer disagrees with its operands.",
         reject("inconsistent_printed_answer", "Do not ignore, overwrite, or read eight as another operand. This requires a correction/explain-the-error workflow."),
         {"a": 4, "b": 3, "printed_answer": 8, "mathematical_answer": 7})

    manifest = {
        "schema_version": 1,
        "fixture_set": "bounded_worksheet_reader_synthetic_v1",
        "synthetic": True,
        "generator": "tests/worksheet_fixtures.py",
        "limitations": [
            "Hand-labeled synthetic clean images, not a representative real-worksheet or real-photo benchmark.",
            "Accept/reject labels describe a deliberately conservative single-question, result-unknown reader contract.",
            "The decorative-dot case is a conservative scoping-policy check, not a uniquely determined mathematical answer.",
            "Rendering is deterministic for the selected installed font; image bytes can differ on hosts using a different font.",
        ],
        "expected_schema": {
            "accept": ["status", "lesson_type", "canonical_question", "a", "b", "unknown", "answer"],
            "accept_shape_extra": ["shape", "shape_task"],
            "reject": ["status", "reason_code", "reason"],
            "image_path": "Resolve each case.image relative to this labels.json file.",
        },
        "cases": cases,
    }
    (destination / "labels.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "worksheets")
    args = parser.parse_args()
    destination = args.out.expanduser().resolve()
    manifest = generate(destination)
    accepted = sum(case["expected"]["status"] == "accept" for case in manifest["cases"])
    print(json.dumps({"manifest": str(destination / "labels.json"),
                      "fixtures": len(manifest["cases"]), "accept": accepted,
                      "reject": len(manifest["cases"]) - accepted}, indent=2))


if __name__ == "__main__":
    main()
