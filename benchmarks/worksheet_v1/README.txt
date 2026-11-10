# Worksheet Reading Lab

This is a local evaluation module. It does not change, train, or publish the child-facing Lesson Buddy app.

## What is included

- **100 unique source task images**, selected from 23 PDFs: 80 England KS1 assessment items and 20 US Kindergarten/Grade 1/Grade 2 Illustrative Mathematics tasks. Native curriculum grades remain separate. They are not 100 photographs or 100 independent documents.
- **22 curator-assigned content topics**: arithmetic and missing numbers, comparison, counting, place value, fractions, measurement, time, money, data, patterns, sorting, odd/even, arrays, equal sharing, number lines, geometry, word problems, and missing-context controls.
- Equations, grayscale cartoons, colored drawings, button photographs, base-ten diagrams, clocks, coins, bar charts, tally tables, pictograms, shaded shapes, activity instructions, and multi-part questions.
- **30 extra synthetic stress images**, paired to 10 development arithmetic items: perspective, shadow/blur, and rendered handwriting imitation. No real child handwriting or phone-photo generalization is established.
- Source URLs, archive members, source file hashes, original PDF pages/crops, native grades, licenses, answer references and annotation limitations.

The whole-source-PDF split is **67 development / 33 test**. Do not tune prompts on the test labels. This first baseline evaluates both splits; it is a baseline, not an untouched final certification set. Public tasks may have appeared in pretraining. A second teacher has not independently verified the annotations.

## Open the review pages

Open `benchmarks/worksheet_v1/index.html` directly in a browser. It works offline, lets an adult filter topics/grades/splits, and shows source images alongside labels and official answer references. It deliberately contains labels; **never send this page to a model**.

After an evaluation, open `output/worksheet_benchmark/qwen_reading_v1/report.html` to inspect outputs and mismatches. Results are not a claim about the web app's SmolVLM reader. The experimental local broad-reading probe uses the locally cached Qwen3-VL 4B model.

## Rebuild and test in VS Code

Open this project folder, then use **Terminal → New Terminal**. On this Mac:

```bash
.venv-benchmark/bin/python -m worksheet_benchmark download
.venv-benchmark/bin/python -m worksheet_benchmark build
.venv-benchmark/bin/python -m worksheet_benchmark.variants
.venv-benchmark/bin/python -m worksheet_benchmark.object_counts build
.venv-benchmark/bin/python -m worksheet_benchmark validate
.venv-benchmark/bin/python -m unittest tests.test_worksheet_benchmark -v
```

The download command fetches only the curated sources in `sources.json`, rather than crawling sites. Rebuilding data uses `requirements-benchmark.txt` (Pillow, NumPy, PyMuPDF). On a fresh Mac create an environment with Python 3.12, then install that file. The contact sheets use Arial when available; the handwriting imitation uses the Mac Marker Felt font and drawn mathematical symbols. Font files are not redistributed.

Run the already installed local model using the original MLX environment:

```bash
.venv/bin/python -m worksheet_benchmark.run --inputs benchmarks/worksheet_v1/inputs.json --out output/worksheet_benchmark/qwen_reading_v1
.venv-benchmark/bin/python -m worksheet_benchmark score
```

Use `--limit 3` for a small smoke run; running the same command again without a limit resumes. A model/prompt/input-hash change requires a new output folder. Missing/invalid/runtime-error results remain in the denominator. The local model requires a compatible Apple Silicon GPU and the already downloaded weights; the runner does not call a paid API or download a model.

Evaluate the separate stress set:

```bash
.venv/bin/python -m worksheet_benchmark.run --inputs benchmarks/worksheet_v1/stress/inputs.json --out output/worksheet_benchmark/qwen_stress_v1
.venv-benchmark/bin/python -m worksheet_benchmark score --manifest benchmarks/worksheet_v1/stress/manifest.json --predictions output/worksheet_benchmark/qwen_stress_v1/predictions.jsonl --out output/worksheet_benchmark/qwen_stress_v1
```

## What the scores mean

1. **Topic label match**: agreement with a curator's single main topic. Some multi-step tasks legitimately span topics; inspect mismatches rather than assuming the model is wrong.
2. **Literal equation transcription**, on 26 manually transcribed equation items: operands, operator and unknown position must be preserved. Solving a blank does not earn transcription credit. Reversing `?=37+51` to `37+51=?` is allowed; moving an unknown operand is not.
3. **Printed operator set**, on the same equation subset. A fraction bar is not counted as a printed division sign.
4. **Partial printed-number token recall**: non-equation labels come from selectable PDF text. Diagram-only numbers may be absent from the targets. Additional valid diagram numbers are not false positives. This does **not** measure object counts, exhaustive OCR, or arithmetic reasoning accuracy.
5. **Context detection**, including an intentionally incomplete aural-question illustration. Runtime errors and malformed JSON are not correct refusals.

Open-ended answers, task summaries, object counts, diagram relationships and complete task understanding need human review. The current video renderer's narrow supported range is a separate label. Reading a multiplication or money task does not make the renderer able to teach it.

The strict baseline retains valid JSON that violates the response schema as a format failure. This deliberately exposes interface reliability as well as perception. Raw outputs are saved so future normalization or prompt changes can be evaluated transparently, without silently rewriting the baseline.

An explicitly separate engineering diagnostic can normalize JSON number values into strings and known mathematical operator glyphs into ASCII. It uses only original output, never labels, and does not repair malformed JSON:

```bash
.venv-benchmark/bin/python -m worksheet_benchmark.normalize
.venv-benchmark/bin/python -m worksheet_benchmark score --predictions output/worksheet_benchmark/qwen_reading_v1_normalized/predictions.jsonl --out output/worksheet_benchmark/qwen_reading_v1_normalized
```

## Visible-object-count subset

Eight of the same 100 source pictures have nine curator-counted target categories (bears, pencils, toy cars, visible oranges, cat stickers, smiley/star stickers, purses and clocks). This is a small partial target-category audit, not exhaustive object labels for all 100 pictures. A different fixed, generic prompt asks the model to count visible objects, without receiving the target names or counts. Label aliases are used only after inference. The orange target is 21 visible oranges; the original task's hidden-oranges answer is a different question.

```bash
.venv/bin/python -m worksheet_benchmark.object_counts run
.venv-benchmark/bin/python -m worksheet_benchmark.object_counts score
.venv-benchmark/bin/python -m worksheet_benchmark.object_counts normalize
.venv-benchmark/bin/python -m worksheet_benchmark.object_counts score --out output/worksheet_benchmark/qwen_object_counts_v1_normalized
```

Count normalization only wraps a singleton object record into a list; it is separately reported and does not invent omitted categories or change counts. Strict results and raw outputs are preserved. Current strict category/count target matches are 2/9; the singleton-format diagnostic matches 7/9. The model returned 16 for 21 visible oranges and omitted the star sticker target. These source labels and synonym choices still need independent review.

The shared [results overview](../output/worksheet_benchmark/index.html) links the strict, normalized and synthetic-condition reports. Rebuild it after completing all runs using `python -m worksheet_benchmark.summary`.

## Labels and model separation

`inputs*.json` contains only opaque ID, image path and pixel SHA256. The reader receives **only image bytes plus one generic frozen prompt**. Curation files, labels, solutions, original filenames, grades and answer references never reach inference. The model output is parsed as data and never executed. Tests check path escapes, changed pixels, duplicate IDs, source-group leakage, unknown positions, and error denominators.

## Source/use boundary

The 20 Illustrative Mathematics tasks are CC BY-NC-SA 4.0; STA material is recorded with its OGL attribution and copyright references. Student task crops omit teacher solution/commentary sections, while retaining student-facing worked examples where present. The corpus is for local **noncommercial academic evaluation**. It has not been deployed to the public child-facing website. Keep `ATTRIBUTION.txt`, per-case provenance and source notices with copies and adaptations.

Next data work: independent teacher review, exhaustive diagram/object-count labels on a smaller task subset, more publishers, genuine consented phone captures, and a fresh held-out set before fine-tuning. Collecting these examples does not make a pretrained model learn automatically.
