"""Inspect the current lesson explanation without speech, APIs, or video tools."""
import argparse
import json
import sys
from pathlib import Path

from .planner import UnsupportedQuestion, plan_question


def explanation_text(spec):
    lines = [f"Question: {spec['question']}", f"Answer: {spec['answer']}", '',
             'Generated narration (in teaching order):', '']
    for index, step in enumerate(spec['steps'], 1):
        lines.append(f"{index}. {step['text']}")
        if step.get('pause_after'):
            lines.append(f"   [Pause for {step['pause_after']} seconds.]")
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('question', help='One supported K–2 math question.')
    parser.add_argument('--out', default='output/explanation_check', help='Folder for lesson.json and explanation.txt.')
    args = parser.parse_args()
    try:
        spec = plan_question(args.question)
    except UnsupportedQuestion as exc:
        print(f'Cannot explain this question yet: {exc}', file=sys.stderr)
        return 2
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    narration = explanation_text(spec)
    (out/'lesson.json').write_text(json.dumps(spec,indent=2,ensure_ascii=False)+'\n')
    (out/'explanation.txt').write_text(narration)
    print(narration)
    print(f"Saved explanation: {out/'explanation.txt'}")
    return 0


if __name__=='__main__':
    raise SystemExit(main())
