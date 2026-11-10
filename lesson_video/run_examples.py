"""Generate the included end-to-end examples and a summary of their checks."""
import argparse
import json
from pathlib import Path

from .generate import generate
from .planner import plan_question


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='output/lesson_video_tests')
    parser.add_argument('--examples', type=Path, default=Path(__file__).with_name('examples.json'))
    parser.add_argument('--voice', default='Samantha')
    parser.add_argument('--rate', type=int, default=145)
    parser.add_argument('--prepare-only', action='store_true', help='Create narration and preview images without encoding MP4s.')
    args = parser.parse_args()
    rows = json.loads(args.examples.read_text())
    # Check every expected answer before doing expensive work.
    for row in rows:
        plan = plan_question(row['question'])
        if (plan['type'], plan['answer']) != (row['expected_type'], row['expected_answer']):
            raise RuntimeError(f"Unexpected plan for {row['id']}")
    reports = []
    for row in rows:
        print(f"\n{row['id']}: {row['question']}", flush=True)
        report = generate(row['question'], Path(args.out)/row['id'], args.voice, args.rate, preview_only=args.prepare_only)
        reports.append({**row,**report})
    target = Path(args.out)/('preview_summary.json' if args.prepare_only else 'test_summary.json')
    target.write_text(json.dumps({'examples':reports,'passed':len(reports),'mode':'previews' if args.prepare_only else 'full videos'},indent=2)+'\n')
    print(f'Completed {len(reports)} examples. Summary: {target}',flush=True)


if __name__=='__main__':
    main()
