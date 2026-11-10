"""Independent offline checks of the lesson plans' mathematical explanations.

The expected values below use ordinary arithmetic and a separate shape table;
they do not import the planner's parsing patterns, number words, or builders.
``build_audit_report()`` returns an inspectable JSON-compatible audit record.
"""

import json
import re
import unittest

from lesson_video.planner import UnsupportedQuestion, plan_question


NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
WORD_VALUES = {word: value for value, word in enumerate(NUMBER_WORDS)}
NUMBER_PATTERN = r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten)\b"
SHAPES = {"circle": 0, "triangle": 3, "square": 4, "rectangle": 4}


def numeric_cases():
    for a in range(11):
        for b in range(11):
            if a + b <= 10:
                yield {"question": f"What is {a} + {b}?", "type": "addition", "a": a, "b": b, "answer": a + b}
            if a >= b:
                yield {"question": f"What is {a} - {b}?", "type": "subtraction", "a": a, "b": b, "answer": a - b}
            for mode, wording in (("greater", f"Which is greater, {a} or {b}?"),
                                  ("less", f"Which is smaller, {a} or {b}?"),
                                  ("compare", f"Compare {a} and {b}.")):
                if a == b:
                    answer = "equal"
                elif mode == "compare":
                    answer = f"{a} {'>' if a > b else '<'} {b}"
                else:
                    answer = max(a, b) if mode == "greater" else min(a, b)
                yield {"question": wording, "type": "comparison", "a": a, "b": b,
                       "answer": answer, "comparison_mode": mode}
    for n in range(11):
        yield {"question": f"Count {n} dots.", "type": "counting", "a": n, "b": None, "answer": n}


def shape_cases():
    for shape, sides in SHAPES.items():
        yield {"question": f"How many sides does a {shape} have?", "type": "shape", "a": None, "b": None,
               "answer": sides, "shape": shape, "shape_task": "sides"}
        yield {"question": f"Show me a {shape}.", "type": "shape", "a": None, "b": None,
               "answer": shape, "shape": shape, "shape_task": "name"}


def domain_rejection_cases():
    for a in range(11):
        for b in range(11):
            if a + b > 10:
                yield f"What is {a} + {b}?"
            if b > a:
                yield f"What is {a} - {b}?"


def _numbers(text):
    return [WORD_VALUES[word] for word in re.findall(NUMBER_PATTERN, text.lower())]


def explanation_issues(spec, expected):
    """Return independent mathematical, sequencing, and timing violations."""
    issues = []

    def require(condition, message):
        if not condition:
            issues.append(message)

    for field in ("type", "a", "b", "answer", "shape", "shape_task", "comparison_mode"):
        if field in expected:
            require(spec.get(field) == expected[field], f"{field}: expected {expected[field]!r}, got {spec.get(field)!r}")
    require(spec.get("question") == expected["question"], "Original question was changed.")
    require(json.loads(json.dumps(spec)) == spec, "The lesson cannot be preserved as plain JSON.")
    steps = spec.get("steps", [])
    prompt_indexes = [i for i, step in enumerate(steps) if step.get("phase") == "question"]
    answer_indexes = [i for i, step in enumerate(steps) if step.get("phase") == "answer"]
    require(len(prompt_indexes) == 1, "There must be one student response prompt.")
    require(len(answer_indexes) == 1, "There must be one answer reveal.")
    if len(prompt_indexes) == len(answer_indexes) == 1:
        prompt_index, answer_index = prompt_indexes[0], answer_indexes[0]
        require(prompt_index < answer_index, "The answer reveal occurs before the response prompt.")
        require(answer_index == prompt_index + 1, "An unrelated step interrupts the response pause.")
        require(steps[prompt_index].get("pause_after") == 3, "The response prompt must declare three seconds of silence.")
        require(steps[answer_index].get("value") == expected["answer"], "Answer reveal value disagrees with the correct answer.")
        answer_text = steps[answer_index].get("text", "")
    else:
        answer_text = ""

    highlighted = [step for step in steps if "active_index" in step]
    for step in highlighted:
        index, number = step["active_index"], step.get("number")
        require(isinstance(index, int) and 0 <= index < 10, f"Highlight index out of the 0–9 domain: {index!r}.")
        require(isinstance(number, int) and 1 <= number <= 10, f"Spoken counting number out of the 1–10 domain: {number!r}.")
        require(number == index + 1, f"Highlight {index!r} and spoken count {number!r} refer to different objects.")
        require(_numbers(step.get("text", "")) == [number], "A highlighted object does not have its matching spoken count.")
    require(len({step.get("id") for step in steps}) == len(steps), "Step IDs are not unique.")

    def sequence(phase, context, cardinality):
        counts = [step for step in highlighted if step.get("phase") == phase and step.get("value") == context]
        require([step["active_index"] for step in counts] == list(range(cardinality)),
                f"{context} highlights do not count each of the {cardinality} objects exactly once.")
        if cardinality == 0:
            require(any(step.get("phase") == phase and step.get("value") == context
                        and 0 in _numbers(step.get("text", "")) for step in steps),
                    f"An empty {context} group is not explicitly explained as zero.")
        return len(counts)

    kind, a, b, answer = expected["type"], expected["a"], expected["b"], expected["answer"]
    expected_highlights = 0
    if kind in ("addition", "subtraction", "comparison"):
        expected_highlights += sequence("group_a", "a", a)
    if kind in ("addition", "comparison"):
        expected_highlights += sequence("group_b", "b", b)
    if kind in ("addition", "subtraction", "counting"):
        expected_highlights += sequence("count", "remaining" if kind == "subtraction" else "total", answer)
        require(_numbers(answer_text) == [answer], "Final cardinality narration does not state the correct count.")
    if kind in ("addition", "subtraction"):
        equality = [step for step in steps if step.get("phase") == "equality"]
        require(len(equality) == 1, "Arithmetic must have one explicit concluding equation.")
        if equality:
            equality_text = equality[0].get("text", "").lower()
            require(_numbers(equality_text) == [a, b, answer], "Concluding equation changes an operand or gives a wrong result.")
            require((" plus " if kind == "addition" else " minus ") in equality_text and " equals " in equality_text,
                    "Concluding equation describes the wrong arithmetic operation.")
        action = [step for step in steps if step.get("phase") == "action"]
        require(len(action) == 1, "Arithmetic needs one clear combine/remove action.")
        if action:
            require(action[0].get("value") == ("combine" if kind == "addition" else "remove"),
                    "The visual action contradicts the mathematical operation.")
            if kind == "subtraction":
                require(action[0].get("number") == b and _numbers(action[0].get("text", "")) == [b],
                        "The take-away narration removes a different number than the question.")
    elif kind == "comparison":
        mode = expected["comparison_mode"]
        if a == b:
            require(_numbers(answer_text) == [a] and "equal" in answer_text.lower(), "Equal groups are described as unequal.")
        else:
            left = a if mode == "compare" else answer
            right = b if mode == "compare" else (b if answer == a else a)
            require(_numbers(answer_text) == [left, right], "Comparison narration names the wrong pair or reverses its answer.")
            relation = "greater than" if left > right else "less than"
            require(relation in answer_text.lower(), "Spoken greater/less relationship is mathematically false.")
    elif kind == "shape":
        shape, task = expected["shape"], expected["shape_task"]
        sides = SHAPES[shape]
        if sides:
            expected_highlights += sequence("count", "sides", sides)
        else:
            require(not highlighted, "A circle must not highlight nonexistent straight sides.")
            all_text = " ".join(step.get("text", "").lower() for step in steps)
            require("curved edge" in all_text and "no straight sides" in all_text,
                    "The circle explanation must distinguish its curved edge from straight sides.")
        if task == "sides":
            require(_numbers(answer_text) == [sides] and "straight sides" in answer_text.lower(),
                    "Shape answer does not explain its correct number of straight sides.")
        else:
            require(shape in answer_text.lower(), "Shape recognition answer names the wrong shape.")
    require(expected_highlights == len(highlighted), "Unexpected highlights refer to another group, phase, or nonexistent object.")
    return issues


# A semantic expectation is independent of whether this deliberately small
# parser currently recognizes the wording. Unrecognized ordinary paraphrases
# are coverage gaps, while unsafe/ambiguous requests are expected rejections.
TEACHER_PARAPHRASES = [
    ("What's 2 plus 3?", {"type": "addition", "a": 2, "b": 3, "answer": 5}),
    ("Add 2 to 3.", {"type": "addition", "a": 2, "b": 3, "answer": 5}),
    ("What is the sum of three and four?", {"type": "addition", "a": 3, "b": 4, "answer": 7}),
    ("Mia has 5 apples and gets 2 more. How many apples does Mia have now?", {"type": "addition", "a": 5, "b": 2, "answer": 7}),
    ("There are 2 apples and 3 apples. How many apples are there altogether?", {"type": "addition", "a": 2, "b": 3, "answer": 5}),
    ("If I have 3 apples and get 2 more, how many do I have?", {"type": "addition", "a": 3, "b": 2, "answer": 5}),
    ("What is 3 added to 2?", {"type": "addition", "a": 3, "b": 2, "answer": 5}),
    ("There are 2 red apples and 3 green apples. How many apples are there in all?", {"type": "addition", "a": 2, "b": 3, "answer": 5}),
    ("Subtract 2 from 7.", {"type": "subtraction", "a": 7, "b": 2, "answer": 5}),
    ("Mia has 5 apples and gives away 2. How many are left?", {"type": "subtraction", "a": 5, "b": 2, "answer": 3}),
    ("Sam has 8 balloons and loses 3 balloons. How many balloons remain?", {"type": "subtraction", "a": 8, "b": 3, "answer": 5}),
    ("Take 2 away from 7.", {"type": "subtraction", "a": 7, "b": 2, "answer": 5}),
    ("Five take away two.", {"type": "subtraction", "a": 5, "b": 2, "answer": 3}),
    ("If I have five apples and eat two, how many are left?", {"type": "subtraction", "a": 5, "b": 2, "answer": 3}),
    ("What is the difference between 2 and 5?", {"type": "subtraction", "a": 5, "b": 2, "answer": 3}),
    ("Count the 6 dots.", {"type": "counting", "a": 6, "b": None, "answer": 6}),
    ("Count up to six.", {"type": "counting", "a": 6, "b": None, "answer": 6}),
    ("Please count 6 dots.", {"type": "counting", "a": 6, "b": None, "answer": 6}),
    ("How many dots are in a group of 6?", {"type": "counting", "a": 6, "b": None, "answer": 6}),
    ("Which number is larger, ten or zero?", {"type": "comparison", "a": 10, "b": 0, "answer": 10, "comparison_mode": "greater"}),
    ("Which is smaller, 3 or 5?", {"type": "comparison", "a": 3, "b": 5, "answer": 3, "comparison_mode": "less"}),
    ("Which is greater, 5 or 5?", {"type": "comparison", "a": 5, "b": 5, "answer": "equal", "comparison_mode": "greater"}),
    ("Compare 3 and 5.", {"type": "comparison", "a": 3, "b": 5, "answer": "3 < 5", "comparison_mode": "compare"}),
    ("Which group has more, 3 or 5?", {"type": "comparison", "a": 3, "b": 5, "answer": 5, "comparison_mode": "greater"}),
    ("Which number is fewer, 3 or 5?", {"type": "comparison", "a": 3, "b": 5, "answer": 3, "comparison_mode": "less"}),
    ("How many sides are on a triangle?", {"type": "shape", "a": None, "b": None, "answer": 3, "shape": "triangle", "shape_task": "sides"}),
    ("How many straight sides does a circle have?", {"type": "shape", "a": None, "b": None, "answer": 0, "shape": "circle", "shape_task": "sides"}),
    ("Teach me about a square.", {"type": "shape", "a": None, "b": None, "answer": "square", "shape": "square", "shape_task": "name"}),
    ("What shape has three straight sides?", {"type": "shape", "a": None, "b": None, "answer": "triangle", "shape": "triangle", "shape_task": "name"}),
    ("What shape has no straight sides?", None),
    ("How many corners does a triangle have?", None),
    ("What shape has four straight sides?", None),
    ("What is 4 times 3?", None),
    ("What is 2 + 3 + 4?", None),
    ("Mia has 5 apples and gives away 2. How many apples did she start with?", None),
    ("What is 4 + 3? Then solve 2 + 2.", None),
    ("Count the dots in this picture.", None),
    ("Show me a pentagon.", None),
    ("Count 12 dots.", None),
]


def _audit_case(expected):
    try:
        spec = plan_question(expected["question"])
    except Exception as exc:
        return {"question": expected["question"], "type": expected["type"], "expected_answer": expected["answer"],
                "status": "failed", "issues": [f"{type(exc).__name__}: {exc}"]}
    issues = explanation_issues(spec, expected)
    return {"question": expected["question"], "type": expected["type"], "a": expected["a"], "b": expected["b"],
            "expected_answer": expected["answer"], "actual_answer": spec["answer"],
            "comparison_mode": spec.get("comparison_mode"), "shape": spec.get("shape"), "shape_task": spec.get("shape_task"),
            "final_narration": next(step["text"] for step in spec["steps"] if step["phase"] == "answer"),
            "equality_narration": next((step["text"] for step in spec["steps"] if step["phase"] == "equality"), None),
            "status": "failed" if issues else "passed", "issues": issues}


def build_audit_report():
    cases = [_audit_case(case) for case in [*numeric_cases(), *shape_cases()]]
    rejections = []
    for question in domain_rejection_cases():
        try:
            result = plan_question(question)
        except UnsupportedQuestion as exc:
            rejections.append({"question": question, "status": "rejected_as_required", "error": str(exc)})
        except Exception as exc:
            rejections.append({"question": question, "status": "failed_unexpected_exception", "error": f"{type(exc).__name__}: {exc}"})
        else:
            rejections.append({"question": question, "status": "failed_accepted", "actual_answer": result["answer"]})
    paraphrases = []
    for question, meaning in TEACHER_PARAPHRASES:
        try:
            result = plan_question(question)
        except UnsupportedQuestion as exc:
            paraphrases.append({"question": question, "actual_outcome": "rejected", "error": str(exc),
                               "interpretation": "coverage_gap" if meaning else "appropriate_scope_or_ambiguity_rejection",
                               "expected_meaning": meaning})
        except Exception as exc:
            paraphrases.append({"question": question, "actual_outcome": "unexpected_exception", "error": f"{type(exc).__name__}: {exc}"})
        else:
            issues = explanation_issues(result, {**meaning, "question": question}) if meaning else ["Accepted a question marked outside this audit's supported, unambiguous scope."]
            if question == "What shape has no straight sides?":
                issues = ["Ambiguous shape inference: a circle and an oval both have no straight sides; the question alone does not identify a circle."]
            paraphrases.append({"question": question, "actual_outcome": "accepted", "actual_type": result["type"],
                               "actual_answer": result["answer"], "expected_meaning": meaning, "issues": issues})
    failures = [case for case in cases if case["status"] != "passed"]
    domain_failures = [case for case in rejections if case["status"] != "rejected_as_required"]
    paraphrase_failures = [case for case in paraphrases if case.get("issues") or case["actual_outcome"] == "unexpected_exception"]
    ambiguity_probe = next(case for case in paraphrases if case["question"] == "What shape has no straight sides?")
    return {
        "audit": "Independent offline K–2 lesson explanation audit",
        "scope": {"numeric_values": list(range(11)), "addition_constraint": "a + b <= 10", "subtraction_constraint": "a >= b",
                  "comparison_modes": ["greater", "less", "compare"], "shape_tasks": ["sides", "name"]},
        "summary": {"total_probe_executions": len(cases) + len(rejections) + len(paraphrases),
                    "unique_question_texts": len({case["question"] for case in cases + rejections + paraphrases}),
                    "valid_lessons_checked": len(cases), "numeric_lessons_checked": sum(case["type"] != "shape" for case in cases),
                    "shape_lessons_checked": sum(case["type"] == "shape" for case in cases),
                    "valid_lessons_by_type": {kind: sum(case["type"] == kind for case in cases) for kind in ("addition", "subtraction", "counting", "comparison", "shape")},
                    "valid_lesson_failures": len(failures), "out_of_domain_arithmetic_probes": len(rejections), "domain_rejection_failures": len(domain_failures),
                    "teacher_paraphrases_probed": len(paraphrases), "teacher_paraphrases_accepted": sum(case["actual_outcome"] == "accepted" for case in paraphrases),
                    "teacher_paraphrases_rejected": sum(case["actual_outcome"] == "rejected" for case in paraphrases),
                    "ordinary_paraphrase_coverage_gaps": sum(case.get("interpretation") == "coverage_gap" for case in paraphrases),
                    "accepted_paraphrase_explanation_or_safety_failures": len(paraphrase_failures), "unit_test_methods": 7},
        "checks": ["independent numeric answers", "operands and final equation agree with the input", "counting cardinality",
                   "greater/less/equal narration", "straight sides versus curved edges", "every object or side highlighted exactly once",
                   "no highlight outside its group's domain", "matching spoken count and highlighted object", "one prompt followed by a declared three-second pause and answer"],
        "limitations": ["This audit inspects generated lesson plans, text, and declared pause timing; it does not listen to audio or inspect the exported video.",
                        "Plain-language coverage is bounded by deterministic patterns; ordinary rejected paraphrases are recorded as coverage gaps, not successful lessons.",
                        "Rejected 'difference between 2 and 5' is a wording limitation: the mathematical distance is 3, while this parser treats the order as subtraction and rejects a negative result.",
                        "'What shape has no straight sides?' must be rejected as ambiguous: a circle and an oval both fit. A regression checks the current outcome explicitly.",
                        "Circle questions are answered using straight sides; the narration explicitly distinguishes the circle's curved edge."],
        "review_findings": [{"finding": "The initial parser inferred circle from no straight sides, although an oval also fits.",
                             "initial_observed_outcome": "accepted_as_circle", "current_observed_outcome": ambiguity_probe["actual_outcome"],
                             "resolved": ambiguity_probe["actual_outcome"] == "rejected",
                             "resolution": "Parent reviewer removed the ambiguous circle inference; named circle questions remain supported."}],
        "failures": failures + domain_failures + paraphrase_failures,
        "valid_lesson_results": cases, "out_of_domain_results": rejections, "teacher_paraphrase_results": paraphrases,
    }


class ExplanationTests(unittest.TestCase):
    def check_cases(self, cases):
        for expected in cases:
            with self.subTest(question=expected["question"]):
                self.assertEqual(explanation_issues(plan_question(expected["question"]), expected), [])

    def test_all_valid_addition_combinations(self):
        self.check_cases(case for case in numeric_cases() if case["type"] == "addition")

    def test_all_valid_subtraction_combinations(self):
        self.check_cases(case for case in numeric_cases() if case["type"] == "subtraction")

    def test_all_counting_cardinalities(self):
        self.check_cases(case for case in numeric_cases() if case["type"] == "counting")

    def test_all_pairs_for_greater_less_and_comparison(self):
        self.check_cases(case for case in numeric_cases() if case["type"] == "comparison")

    def test_all_eight_shape_tasks(self):
        self.check_cases(shape_cases())

    def test_all_out_of_domain_arithmetic_combinations_are_rejected(self):
        for question in domain_rejection_cases():
            with self.subTest(question=question):
                with self.assertRaises(UnsupportedQuestion):
                    plan_question(question)

    def test_accepted_teacher_paraphrases_keep_their_meaning_and_unsafe_ones_are_rejected(self):
        for question, meaning in TEACHER_PARAPHRASES:
            with self.subTest(question=question):
                try:
                    spec = plan_question(question)
                except UnsupportedQuestion:
                    continue  # Coverage gaps are recorded explicitly in the audit.
                self.assertIsNotNone(meaning, "An ambiguous shape was guessed: a circle and an oval both have no straight sides."
                                     if question == "What shape has no straight sides?" else "An ambiguous or unsupported request was guessed.")
                self.assertEqual(explanation_issues(spec, {**meaning, "question": question}), [])


if __name__ == "__main__":
    unittest.main()
