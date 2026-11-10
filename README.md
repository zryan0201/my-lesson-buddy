# My Lesson Buddy

**Turn a math question into a visual explanation starring a character a child creates.**

My Lesson Buddy is a supervised K–2 learning prototype. Children draw or build a buddy, bring a worksheet or number question, and watch their character collect, carry, share, or count objects to explain the math. A grown-up checks the lesson before playback.

[Try the live demo](https://my-lesson-buddy-studio.leftcloak4.chatgpt.site) · [Run locally](docs/SETUP.md) · [Technical architecture](docs/ARCHITECTURE.md) · [Evaluation results](docs/EVALUATION.md)

## The learning experience

**Create a buddy → Bring a question → Check together → Watch the explanation**

1. **Create.** Draw an original character, or customize a character using modular parts, colors, clothes, and accessories.
2. **Bring a question.** Upload or photograph one worksheet exercise, choose an example, or enter the numbers manually. Automatic reading is optional and experimental.
3. **Check together.** An adult confirms the operation, quantities, answer, character, and visual representation.
4. **Watch and explore.** The character performs the mathematical actions in a narrated story. Children can replay the explanation or download the video.

For `4 + 3`, a buddy can carry three objects into an existing group of four, then count the seven objects together. Worksheet pictures can become the story props when they can be separated clearly. Pure number questions can use story stars to make the quantities visible.

## What makes the prototype distinctive

| Feature | What it adds |
| --- | --- |
| Characters participate in the math | The child's buddy collects, carries, gives, points, and traces during the explanation. |
| A connection to the original worksheet | Reviewed object cutouts can preserve the same popsicles, dots, or other artwork from the question. |
| Four story worlds | Garden Picnic, Maker Workshop, Ocean Discovery, and Moon Station provide different settings around the same mathematical steps. |
| An explicit review step | Adults check the interpretation and representation before a lesson is prepared. |
| Local processing in the hosted experience | Pictures, characters, optional reading, and video recording are handled in the visitor's browser. |

These are implemented design features. Their effect on engagement, visual fatigue, or learning outcomes has not been measured with children.

## What works today

| Lesson | Current teaching range |
| --- | --- |
| Addition | Whole numbers from 0–10; the total is at most 10. |
| Subtraction | Whole numbers from 0–10; the result cannot be negative. |
| Counting | Quantities from 0–10. |
| Basic shapes | Name a circle, triangle, square, or rectangle, or count its straight sides. |

Broader worksheet topics are represented in the research dataset. Teaching regrouping, two-digit arithmetic, fractions, time, money, and multiplication/division requires additional lesson logic. A successful reading alone does not add a new teaching capability.

## Choose how to try it

| Your goal | Start here | Requirements |
| --- | --- | --- |
| Try the full experience | [Live website](https://my-lesson-buddy-studio.leftcloak4.chatgpt.site) | A compatible browser; no local server or API key. |
| Develop the combined website | [Browser development guide](web_site/README.md) | Node/npm and a local static server. |
| Run the Python lesson app | [Local setup](docs/SETUP.md#python-lesson-app-on-an-apple-silicon-mac) | An Apple silicon Mac, Python, FFmpeg, and cached vision weights for picture reading. |
| Work on character creation | [Character Studio](character_studio/README.md) | Python dependencies; no vision model required. |
| Generate a video from text | [Command-line lesson guide](lesson_video/README.md) | Python, FFmpeg, and an installed macOS voice. |
| Inspect reading quality | [Evaluation summary](docs/EVALUATION.md) | Results can be read on GitHub; interactive HTML reports open after download. |

The hosted website and the Python apps are separate implementations. Their readers, narration, storage, and video formats differ; see the [architecture guide](docs/ARCHITECTURE.md).

## Technical approach

The pipeline reads a question, validates a bounded lesson, computes the answer in code, and freezes the reviewed plan. The renderer then follows authored actions and narration timing. A model does not invent the mathematical answer or freely generate the film.

| Component | Implementation |
| --- | --- |
| Hosted picture reader | Experimental SmolVLM-256M through Transformers.js and WebGPU. |
| Local Mac picture reader | Cached Qwen3-VL-4B-Instruct-4bit through MLX-VLM. |
| Math and story planning | Validated quantities, computed answers, and deterministic scene actions. |
| Hosted narration | Prerecorded Kokoro-82M narration with measured scene timing. |
| Video export | Browser Canvas/MediaRecorder, or the Python renderer with FFmpeg. |

Read [architecture and review boundaries](docs/ARCHITECTURE.md) or the [browser reader's technical notes](web_site/READER_NOTES.md) for implementation details.

## Evaluation: evidence and limits

The reading lab contains **100 web-source task images across 22 topics**, plus **30 synthetic variants of 10 development questions**. A separate object-count audit reuses eight pictures with nine labeled target groups.

| Local broad-reading measure | Strict output | After limited format normalization |
| --- | --- | --- |
| Main-topic label match | 59 / 100 | 67 / 100 |
| Complete equation transcription | 16 / 26 | 18 / 26 |
| Visible object category and count match | 2 / 9 targets | 7 / 9 targets |

Normalization reuses the original responses; it changes allowed output formatting and does not rerun the model or supply answers. These are separate checks, not an overall recognition score. They do not measure the hosted browser reader. The corpus contains **zero real phone photographs**, and its labels still need independent teacher review.

[Read the findings and failure cases](docs/EVALUATION.md) · [Reproduce the benchmark](worksheet_benchmark/README.md)

## Repository map

| Path | Purpose |
| --- | --- |
| [`web_site/`](web_site/README.md) | Combined browser app, story engine, narration assets, and browser tests. |
| [`character_studio/`](character_studio/README.md) | Local drawing canvas, parts builder, character library, and package import/export. |
| [`lesson_video/`](lesson_video/README.md) | Python reading, planning, narration, rendering, and local web service. |
| [`worksheet_benchmark/`](worksheet_benchmark/README.md) | Dataset construction, model adapters, scoring, and report generation. |
| [`benchmarks/worksheet_v1/`](benchmarks/worksheet_v1/) | Source-backed images, labels, provenance, and review catalogue. |
| [`output/worksheet_benchmark/`](output/worksheet_benchmark/) | Saved baseline predictions, metrics, and HTML reports. |
| [`tests/`](tests/) and [`examples/`](examples/) | Python checks and demonstration fixtures. |
| [`docs/`](docs/) | Setup, architecture, evaluation, and optional integration guides. |

## Next development priorities

1. Improve missing-context detection and the consistency of reader outputs.
2. Independently review labels and add genuine phone photos and handwriting.
3. Extend teaching scenes with ten-frames, making ten, and place-value representations.
4. Evaluate broader teaching strategies and child usability before making outcome claims.

New uploads do not automatically retrain the models. Fine-tuning and broader lesson support are separate development steps.

For publication scope and licensing, see [public repository contents](PUBLICATION.md) and [third-party notices](THIRD_PARTY_NOTICES.md). The worksheet corpus retains its source-specific noncommercial academic-use terms.
