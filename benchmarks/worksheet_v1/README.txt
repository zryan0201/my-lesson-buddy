# Worksheet Reading Lab

[Project overview](../README.md) · [Results and limitations](../docs/EVALUATION.md) · [Application architecture](../docs/ARCHITECTURE.md)

A reproducible local evaluation toolkit for unfamiliar worksheet images. It builds a source-backed corpus, runs model probes without supplying labels, and produces per-case reports. It does not train a model or change the hosted application.

## Start with the saved evidence

No model is needed to inspect the existing results. Clone/download the repository, then open:

| Local file | Contents |
| --- | --- |
| `output/worksheet_benchmark/index.html` | Results overview and links to every baseline. |
| `benchmarks/worksheet_v1/index.html` | Filterable source images, annotations, and answer references. |
| `output/worksheet_benchmark/qwen_reading_v1/report.html` | Strict broad-reading outputs and mismatches. |
| `output/worksheet_benchmark/qwen_reading_v1_normalized/report.html` | Separate format-normalization diagnostic. |

GitHub shows HTML source rather than running these pages. The [evaluation guide](../docs/EVALUATION.md) presents the key results directly on GitHub. The label catalogue is for human review; never pass it to a model.

## Dataset and evaluation scope

| Set | Images | Independent source questions | Scope |
| --- | --- | --- | --- |
| Primary corpus | 100 | 100 curated task items from 23 PDFs | 22 content topics; 67 development / 33 test. |
| Synthetic stress set | 30 | Reuses 10 development questions | Perspective, shadow/blur, and simulated handwriting font. |
| Visible-count audit | Reuses 8 primary images | Reuses those same 8 items | Nine partially labeled object categories. |

The primary sources are 80 England KS1 test/practice items and 20 US K/1/2 Illustrative Mathematics tasks. Native curriculum grades remain separate. Images include equations, illustrations, button photographs, coins, clocks, shapes, number lines, charts, tables, and activity instructions.

The corpus has **zero real phone photographs** and no real child handwriting. Source PDFs stay in one split, including any derived variants. The first baseline inspected both splits; use a fresh held-out set after development informed by these results. Public tasks may have appeared in pretraining, and annotations are not independently double-reviewed by teachers.

## 1. Prepare the data/scoring environment

Run commands from the **repository root**. On the tested Mac setup:

```sh
python3.12 -m venv .venv-benchmark
.venv-benchmark/bin/python -m pip install -r requirements-benchmark.txt
.venv-benchmark/bin/python -m worksheet_benchmark validate
.venv-benchmark/bin/python -m unittest tests.test_worksheet_benchmark -v
```

This environment needs Pillow, NumPy, and PyMuPDF. It does not run the vision model. Building contact sheets uses Arial when available; handwriting imitation uses the Mac Marker Felt font and drawn math symbols. Font files are not distributed.

## 2. Rebuild data when needed

The checked-in corpus is ready to inspect. To reconstruct it from the curated public sources:

```sh
.venv-benchmark/bin/python -m worksheet_benchmark download
.venv-benchmark/bin/python -m worksheet_benchmark build
.venv-benchmark/bin/python -m worksheet_benchmark.variants
.venv-benchmark/bin/python -m worksheet_benchmark.object_counts build
.venv-benchmark/bin/python -m worksheet_benchmark validate
```

Downloading uses the enumerated URLs in `sources.json`, not a site crawler. Source URLs, archive members, PDF hashes/pages/crops, licenses, native grades, and answer references are recorded. Teacher solutions/commentary are omitted from model images; student-facing worked examples may remain.

## 3. Run a new local reading evaluation

Install the [Mac vision environment](../docs/SETUP.md#python-lesson-app-on-an-apple-silicon-mac) and explicitly download its model once. Use `.venv` for inference and `.venv-benchmark` for scoring. Choose a **new output directory** to preserve the published baselines:

```sh
.venv/bin/python -m worksheet_benchmark.run --inputs benchmarks/worksheet_v1/inputs.json --out output/worksheet_benchmark/my_reading_run
.venv-benchmark/bin/python -m worksheet_benchmark score --predictions output/worksheet_benchmark/my_reading_run/predictions.jsonl --out output/worksheet_benchmark/my_reading_run
```

Add `--limit 3` for a smoke run. Repeating the same command without a limit resumes. A changed model, prompt, or input hash requires another output directory. Missing results, malformed output, and runtime errors stay in the denominator. Inference needs the local Apple Silicon GPU and cached weights; it does not use a paid API or download a model.

The optional formatting diagnostic reuses the saved outputs:

```sh
.venv-benchmark/bin/python -m worksheet_benchmark.normalize --source output/worksheet_benchmark/my_reading_run --out output/worksheet_benchmark/my_reading_run_normalized
.venv-benchmark/bin/python -m worksheet_benchmark score --predictions output/worksheet_benchmark/my_reading_run_normalized/predictions.jsonl --out output/worksheet_benchmark/my_reading_run_normalized
```

It only normalizes number-string and known operator-glyph formatting. It does not repair malformed JSON, supply labels, change meanings, or run inference again. Keep it separate from strict results.

## 4. Evaluate the additional probes

### Synthetic conditions

```sh
.venv/bin/python -m worksheet_benchmark.run --inputs benchmarks/worksheet_v1/stress/inputs.json --out output/worksheet_benchmark/my_stress_run
.venv-benchmark/bin/python -m worksheet_benchmark score --manifest benchmarks/worksheet_v1/stress/manifest.json --predictions output/worksheet_benchmark/my_stress_run/predictions.jsonl --out output/worksheet_benchmark/my_stress_run
```

Compare transformed views with the **same 10 originals**, not with the 100-image overall rate. Variants retain their base IDs and development split. See the saved paired comparison in `output/worksheet_benchmark/paired_robustness.csv`.

### Visible-object counts

```sh
.venv/bin/python -m worksheet_benchmark.object_counts run --out output/worksheet_benchmark/my_count_run
.venv-benchmark/bin/python -m worksheet_benchmark.object_counts score --out output/worksheet_benchmark/my_count_run
.venv-benchmark/bin/python -m worksheet_benchmark.object_counts normalize --source output/worksheet_benchmark/my_count_run --out output/worksheet_benchmark/my_count_run_normalized
.venv-benchmark/bin/python -m worksheet_benchmark.object_counts score --out output/worksheet_benchmark/my_count_run_normalized
```

This probe receives a generic visible-count prompt without target names or counts. The nine annotated categories cover bears, pencils, toy cars, oranges, cat stickers, smiley/star stickers, purses, and clocks. Evaluation aliases are applied only after inference. Extra unlabelled categories are not false positives.

The orange target is **21 visible oranges**, distinct from the source task's hidden-oranges answer. Object normalization only wraps a singleton group into a list; it cannot invent an omitted category or change a count. These partial labels and synonyms still need independent review.

## How scoring works

| Measure | Boundary |
| --- | --- |
| Main-topic match | One curator-assigned label; multi-topic disagreements need review. |
| Complete equation transcription | 26 exact labels; preserve operands, operator, and unknown position. An invented answer does not earn credit. |
| Printed operator set | Same equation subset; a fraction bar is not counted as a printed division sign. |
| Printed-number recall | Partial selectable-PDF-text targets; not exhaustive OCR or object counts. Extra diagram numbers are not penalized. |
| Context detection | An incomplete aural-question control; an error is not a correct refusal. |
| Visible category/count match | Nine partial targets across eight reused images; not full question-answer accuracy. |

Open-ended answers, task summaries, clock readings, diagram relationships, and complete understanding need human scoring. Current video support is a separate label; reading money or multiplication does not make the renderer able to teach it.

## Files and isolation

| Files | Role |
| --- | --- |
| `inputs*.json` | Opaque IDs, image paths, and pixel hashes only. |
| `manifest.json`, `labels.csv`, `object_counts.json` | Human/evaluation annotations, provenance, and answer references. |
| `reading.py`, `run.py` | Frozen broad-reading prompt, strict parsing, hash-bound inference/resume. |
| `scoring.py`, `normalize.py`, `object_counts.py` | Separate scoring and explicit diagnostic transformations. |
| `summary.py`, `report.py`, `review.py` | Results overview, per-case reports, and label-review UI. |

The model receives only image pixels and one fixed generic prompt. Source filenames, grades, labels, and answers stay outside its context. Model output is treated as data. Tests check path escapes, tampered pixels, duplicate IDs, source-split leakage, unknown positions, and error denominators.

The delivered overview is tied to the named published baseline folders. Rebuild it with `python -m worksheet_benchmark.summary` only after those runs are complete; custom runs have their own per-case reports. `python -m worksheet_benchmark.package` packages data/results without weights or environments.

## Source terms and next steps

Preserve `benchmarks/worksheet_v1/ATTRIBUTION.txt` and all per-case provenance. Illustrative Mathematics tasks and adaptations retain CC BY-NC-SA 4.0 terms; STA material retains its OGL attribution. The mixed corpus is for **noncommercial academic evaluation**, separate from the child-facing website.

Next: independently review annotations, add more complete object/diagram labels and consented phone captures, and create a new holdout before tuning. Collecting worksheets does not automatically retrain a pretrained model.
