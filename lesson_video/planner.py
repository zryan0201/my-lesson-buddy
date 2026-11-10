"""Small, deterministic question planner for local K–2 lesson videos.

``plan_question(text)`` returns a JSON-serializable lesson dictionary. Parsing is
deliberately limited to complete, documented patterns: this is not a general
question-answering model. An unsupported or ambiguous request raises
``UnsupportedQuestion`` before any video is rendered.

Run ``python -m lesson_video.planner 'What is 4 + 3?'`` to inspect a lesson.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any


class UnsupportedQuestion(ValueError):
    """The question cannot safely be expressed by this lesson vocabulary."""


_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
_NUMBER = r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|[0-9]{1,2})"
_NAME = r"[a-z][a-z'-]{0,24}"
_ITEM = r"[a-z]{2,24}"
_SHAPE = r"(?:circle|triangle|square|rectangle)"
_SIDE_COUNTS = {"circle": 0, "triangle": 3, "square": 4, "rectangle": 4}

# Every pattern must match the entire question. In particular, extracting the
# first two numbers from arbitrary prose would silently answer other questions.
_ADDITION_PATTERNS = (
    rf"(?:(?:what is|what's|how much is|calculate|solve)\s+)?(?P<a>{_NUMBER})\s*(?:\+|plus)\s*(?P<b>{_NUMBER})(?:\s*=\s*\??)?",
    rf"add\s+(?P<a>{_NUMBER})\s+(?:and|to)\s+(?P<b>{_NUMBER})",
    rf"(?:what is\s+)?the sum of\s+(?P<a>{_NUMBER})\s+and\s+(?P<b>{_NUMBER})",
    rf"(?P<name>{_NAME}) has\s+(?P<a>{_NUMBER})\s+(?P<item>{_ITEM})\s+and\s+(?:gets|receives|finds|buys)\s+(?P<b>{_NUMBER})\s+(?:more(?:\s+(?P=item))?|(?P=item))\s*[.!]\s*how many\s+(?:(?P=item)\s+)?(?:does\s+(?:(?P=name)|she|he|they)\s+have now|are there (?:now|altogether|in all))",
    rf"there are\s+(?P<a>{_NUMBER})\s+(?P<item>{_ITEM})\s+and\s+(?P<b>{_NUMBER})\s+(?:more\s+)?(?P=item)\s*[.!]\s*how many\s+(?:(?P=item)\s+)?are there\s+(?:altogether|in all)",
)
_SUBTRACTION_PATTERNS = (
    rf"(?:(?:what is|what's|how much is|calculate|solve)\s+)?(?P<a>{_NUMBER})\s*(?:-|minus)\s*(?P<b>{_NUMBER})(?:\s*=\s*\??)?",
    rf"subtract\s+(?P<b>{_NUMBER})\s+from\s+(?P<a>{_NUMBER})",
    rf"(?:what is\s+)?the difference between\s+(?P<a>{_NUMBER})\s+and\s+(?P<b>{_NUMBER})",
    rf"(?P<name>{_NAME}) has\s+(?P<a>{_NUMBER})\s+(?P<item>{_ITEM})\s+and\s+(?:gives away|loses|takes away)\s+(?P<b>{_NUMBER})(?:\s+(?P=item))?\s*[.!]\s*how many\s+(?:(?P=item)\s+)?(?:are left|remain|does\s+(?:(?P=name)|she|he|they)\s+have left)",
)
_COUNT_PATTERNS = (
    rf"count\s+(?:the\s+)?(?P<a>{_NUMBER})\s+(?:dots?|counters?|objects?)",
    rf"count\s+(?:up\s+)?to\s+(?P<a>{_NUMBER})",
)
_COMPARISON_PATTERNS = (
    rf"which\s+(?:number\s+)?is\s+(?P<mode>greater|bigger|larger|less|smaller)\s*,?\s*(?P<a>{_NUMBER})\s+(?:or|and)\s+(?P<b>{_NUMBER})",
    rf"compare\s+(?P<a>{_NUMBER})\s+and\s+(?P<b>{_NUMBER})",
)
_SHAPE_SIDE_PATTERNS = (
    rf"how many\s+(?:straight\s+)?sides\s+does\s+(?:a\s+|the\s+)?(?P<shape>{_SHAPE})\s+have",
    rf"how many\s+(?:straight\s+)?sides\s+are\s+(?:on|in)\s+(?:a\s+|the\s+)?(?P<shape>{_SHAPE})",
)
_SHAPE_NAME_PATTERNS = (
    rf"(?:show(?: me)?|identify|teach me about)\s+(?:a\s+|the\s+)?(?P<shape>{_SHAPE})",
    rf"what is\s+(?:a\s+)?(?P<shape>{_SHAPE})",
)

_HELP = (
    "Try a supported question such as 'What is 4 + 3?', "
    "'Mia has 5 apples and gives away 2. How many are left?', "
    "'Count 6 dots.', 'Which is greater, 3 or 5?', "
    "or 'How many sides does a triangle have?'. "
    "Use whole numbers from 0 to 10; addition totals must be at most 10, "
    "and subtraction must not go below zero."
)


def _number(token: str) -> int:
    value = _WORDS.index(token) if token in _WORDS else int(token)
    if not 0 <= value <= 10:
        raise UnsupportedQuestion("Numbers must be whole numbers from 0 to 10. " + _HELP)
    return value


def _normalize(question: str) -> str:
    if not isinstance(question, str) or not question.strip():
        raise UnsupportedQuestion("Please provide one nonempty question. " + _HELP)
    if len(question) > 500:
        raise UnsupportedQuestion("Please provide one short question at a time. " + _HELP)
    value = question.lower().replace("−", "-").replace("’", "'")
    return re.sub(r"\s+", " ", value).strip().rstrip(".!? ")


def _match(patterns: tuple[str, ...], question: str) -> re.Match[str] | None:
    for pattern in patterns:
        result = re.fullmatch(pattern, question)
        if result:
            return result
    return None


def _new_spec(kind: str, question: str, a: int | None, b: int | None,
              answer: int | str, title: str, **extras: Any) -> dict[str, Any]:
    return {
        "type": kind,
        "question": question.strip(),
        "a": a,
        "b": b,
        "answer": answer,
        "title": title,
        "steps": [],
        **extras,
    }


def _step(spec: dict[str, Any], phase: str, text: str, **extras: Any) -> None:
    spec["steps"].append({
        "id": f"{spec['type']}_{len(spec['steps']) + 1:02d}",
        "text": text,
        "phase": phase,
        **extras,
    })


def _count_group(spec: dict[str, Any], phase: str, size: int, value: str) -> None:
    if size == 0:
        _step(spec, phase, "There are zero dots in this group.", number=0, value=value)
    else:
        for index in range(size):
            _step(spec, phase, f"{_WORDS[index + 1].capitalize()}.",
                  active_index=index, number=index + 1, value=value)


def _finish(spec: dict[str, Any], prompt: str, answer_text: str,
            equality: str | None = None) -> dict[str, Any]:
    _step(spec, "question", prompt, pause_after=3)
    _step(spec, "answer", answer_text, value=spec["answer"])
    if equality:
        _step(spec, "equality", equality, value=spec["answer"])
    _step(spec, "celebration", "Great counting and thinking!")
    return spec


def _arithmetic(kind: str, question: str, a: int, b: int) -> dict[str, Any]:
    if kind == "addition":
        if a + b > 10:
            raise UnsupportedQuestion("This counting video supports addition totals up to 10. " + _HELP)
        answer = a + b
        spec = _new_spec(kind, question, a, b, answer, "Let's Add!")
        _step(spec, "intro", "Let's add two groups of dots.")
        _step(spec, "group_a", "Count the first group.", number=a, value="a")
        _count_group(spec, "group_a", a, "a")
        _step(spec, "group_b", "Now count the second group.", number=b, value="b")
        _count_group(spec, "group_b", b, "b")
        _step(spec, "action", "Plus means put the groups together.", value="combine")
        _step(spec, "count", "Let's count all the dots.", value="total")
        _count_group(spec, "count", answer, "total")
        return _finish(spec, "How many dots are there altogether? Your turn!",
                       f"There {'is' if answer == 1 else 'are'} {_WORDS[answer]} {'dot' if answer == 1 else 'dots'} altogether!",
                       f"{_WORDS[a].capitalize()} plus {_WORDS[b]} equals {_WORDS[answer]}.")

    if b > a:
        raise UnsupportedQuestion("This lesson cannot take away more dots than it starts with. " + _HELP)
    answer = a - b
    spec = _new_spec(kind, question, a, b, answer, "Let's Subtract!")
    _step(spec, "intro", "Let's take away some dots.")
    _step(spec, "group_a", "Count the dots we start with.", number=a, value="a")
    _count_group(spec, "group_a", a, "a")
    text = ("We take away zero dots. All the dots stay." if b == 0 else
            f"Take away {_WORDS[b]} {'dot' if b == 1 else 'dots'}.")
    _step(spec, "action", text, number=b, value="remove")
    _step(spec, "count", "Now count the dots that are left.", value="remaining")
    _count_group(spec, "count", answer, "remaining")
    return _finish(spec, "How many dots are left? Your turn!",
                   f"{_WORDS[answer].capitalize()} {'dot is' if answer == 1 else 'dots are'} left!",
                   f"{_WORDS[a].capitalize()} minus {_WORDS[b]} equals {_WORDS[answer]}.")


def _counting(question: str, size: int) -> dict[str, Any]:
    spec = _new_spec("counting", question, size, None, size, "Let's Count!")
    _step(spec, "intro", "Let's find out how many dots there are.")
    _step(spec, "group_a", "This group is empty." if size == 0 else "Point to each dot as we count.", number=size, value="a")
    _count_group(spec, "count", size, "total")
    return _finish(spec, "How many dots did you count? Your turn!",
                   f"There {'is' if size == 1 else 'are'} {_WORDS[size]} {'dot' if size == 1 else 'dots'}!")


def _comparison(question: str, a: int, b: int, mode: str) -> dict[str, Any]:
    if a == b:
        answer: int | str = "equal"
        final = f"Both groups have {_WORDS[a]} {'dot' if a == 1 else 'dots'}. They are equal!"
    elif mode == "compare":
        symbol = ">" if a > b else "<"
        answer = f"{a} {symbol} {b}"
        relation = "greater than" if a > b else "less than"
        final = f"{_WORDS[a].capitalize()} is {relation} {_WORDS[b]}."
    else:
        answer = max(a, b) if mode == "greater" else min(a, b)
        other = min(a, b) if mode == "greater" else max(a, b)
        relation = "greater than" if mode == "greater" else "less than"
        final = f"{_WORDS[answer].capitalize()} is {relation} {_WORDS[other]}!"
    spec = _new_spec("comparison", question, a, b, answer, "Let's Compare!", comparison_mode=mode)
    _step(spec, "intro", "Let's compare two groups of dots.")
    _step(spec, "group_a", "Count the first group.", number=a, value="a")
    _count_group(spec, "group_a", a, "a")
    _step(spec, "group_b", "Count the second group.", number=b, value="b")
    _count_group(spec, "group_b", b, "b")
    prompt = ("How do the two groups compare? Your turn!" if mode == "compare" else
              f"Which number is {'greater' if mode == 'greater' else 'smaller'}? Your turn!")
    return _finish(spec, prompt, final)


def _shape_lesson(question: str, shape: str, task: str) -> dict[str, Any]:
    sides = _SIDE_COUNTS[shape]
    spec = _new_spec("shape", question, None, None, sides if task == "sides" else shape,
                     f"Meet the {shape.capitalize()}!", shape=shape, shape_task=task)
    _step(spec, "intro", f"Let's look closely at this {shape}.", value=shape)
    if sides == 0:
        _step(spec, "action", "A circle has one continuous curved edge. It has no straight sides.", value="curve", number=0)
    else:
        _step(spec, "action", "A side is a straight edge. Let's count each side once.", value="sides")
        for index in range(sides):
            _step(spec, "count", f"{_WORDS[index + 1].capitalize()}.",
                  active_index=index, number=index + 1, value="sides")
    if task == "sides":
        return _finish(spec, "How many straight sides does it have? Your turn!",
                       f"A {shape} has {_WORDS[sides]} straight sides!" if sides else
                       "A circle has zero straight sides!")
    if shape == "square":
        _step(spec, "action", "Its four sides are the same length, and it has four square corners.", value="properties")
    elif shape == "rectangle":
        _step(spec, "action", "A rectangle has four square corners. Its opposite sides are the same length.", value="properties")
    return _finish(spec, "What shape is this? Your turn!", f"It's a {shape}!")


def plan_question(question: str) -> dict[str, Any]:
    """Return one bounded lesson spec or raise :class:`UnsupportedQuestion`.

    Supported lesson ``type`` values are ``addition``, ``subtraction``,
    ``counting``, ``comparison``, and ``shape``. Counts and operands range from
    zero through ten. No network, LLM, random state, audio, or rendering is used.

    All steps have ``id``, ``text``, and ``phase``. ``active_index`` is zero-based;
    zero-sized groups never contain one. ``number`` is the spoken counting
    number (or a displayed group size). ``value`` identifies ``a``/``b`` groups,
    ``total``/``remaining`` counts, a named action, or the final answer.
    ``pause_after`` is seconds of silence after the step's narration.
    """
    normalized = _normalize(question)
    for kind, patterns in (("addition", _ADDITION_PATTERNS), ("subtraction", _SUBTRACTION_PATTERNS)):
        match = _match(patterns, normalized)
        if match:
            return _arithmetic(kind, question, _number(match["a"]), _number(match["b"]))
    match = _match(_COUNT_PATTERNS, normalized)
    if match:
        return _counting(question, _number(match["a"]))
    match = _match(_COMPARISON_PATTERNS, normalized)
    if match:
        mode = match.groupdict().get("mode") or "compare"
        mode = "greater" if mode in ("greater", "bigger", "larger") else "less" if mode in ("less", "smaller") else "compare"
        return _comparison(question, _number(match["a"]), _number(match["b"]), mode)
    match = _match(_SHAPE_SIDE_PATTERNS, normalized)
    if match:
        return _shape_lesson(question, match["shape"], "sides")
    match = _match(_SHAPE_NAME_PATTERNS, normalized)
    if match:
        return _shape_lesson(question, match["shape"], "name")
    # A triangle is determined by three straight sides. Four sides alone cannot
    # distinguish a square from a rectangle, and no straight sides could mean
    # a circle, an oval, or another curved shape, so do not guess those names.
    if re.fullmatch(r"what shape has (?:3|three) (?:straight )?sides", normalized):
        return _shape_lesson(question, "triangle", "name")
    raise UnsupportedQuestion("I could not safely understand this as one supported K–2 question. " + _HELP)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="One supported K–2 question")
    args = parser.parse_args()
    try:
        spec = plan_question(args.question)
    except UnsupportedQuestion as exc:
        parser.error(str(exc))
    print(json.dumps(spec, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
