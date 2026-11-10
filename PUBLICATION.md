# Public repository contents

The repository includes:

- `web_site/`: the combined browser website, narration assets and tests;
- `character_studio/`: the local drawing and character-parts studio;
- `lesson_video/`: local worksheet reading, lesson planning, narration and rendering;
- `worksheet_benchmark/`, `benchmarks/worksheet_v1/` and `output/worksheet_benchmark/`: academic evaluation tools, source-backed data and first baseline results;
- example fixtures, pinned dependency files and automated tests.

Local virtual environments, downloaded models, caches, `node_modules`, hosting identity files, credentials, generated videos, presentations, user character libraries and benchmark ZIP exports remain outside version control. The website's nested development Git metadata is not part of this repository; the actual website files are included as ordinary source files.

Start with the [main README](README.md). Use [setup options](docs/SETUP.md) to choose a runtime, [architecture](docs/ARCHITECTURE.md) to understand the pipeline, or [evaluation](docs/EVALUATION.md) to assess the evidence. Module guides cover the [browser website](web_site/README.md), [Character Studio](character_studio/README.md), [Python lesson generator](lesson_video/README.md), and [benchmark](worksheet_benchmark/README.md).

The hosted demo is linked from the main README. Publishing source to GitHub does not redeploy that website. HTML research reports run after cloning/downloading the repository; GitHub displays their source.

Preserve [third-party notices](THIRD_PARTY_NOTICES.md) and the worksheet corpus's attribution and use restrictions when copying or sharing material.
