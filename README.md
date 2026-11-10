# My Lesson Buddy · K–2 worksheet-to-cartoon studio

## Worksheet Reading Lab (local research)

The new [evaluation module](worksheet_benchmark/README.md) contains 100 web-source task images across 22 content topics, 30 explicitly synthetic stress variants, source-backed labels and repeatable local-model runs. Open [the results overview](output/worksheet_benchmark/index.html) or [the image/label catalogue](benchmarks/worksheet_v1/index.html). The first broad-reading and small visible-object-count baselines are complete. This is not a training run, a real-phone benchmark, or a score for the hosted browser reader; the public app is unchanged.

## Combined hosted website

The new `web_site/` directory combines character creation, worksheet entry/optional browser AI reading, adult review, and narrated video playback/download in one website. Hosting serves the app and its narration; visitors process their own pictures and render videos in their browsers, without a local terminal or Ryan’s laptop. Character collections stay separate in each visitor’s browser. See [hosted website instructions](web_site/README.md) for the configured address, supported devices, first-use model download, video formats, and deployment status requirements.

Open the public [My Lesson Buddy website](https://my-lesson-buddy-studio.leftcloak4.chatgpt.site). Its Starlight Garden stories put the child’s character inside the math: collecting stars for addition, sharing them for subtraction, visiting each item to count, or tracing a shape gate. Adult review includes a mission and storyboard preview. This character-led story upgrade is implemented in the hosted browser edition; `web_site/README.md` explains how to preview that edition in VS Code.

The hosted edition now uses the worksheet’s original object cutouts for arithmetic and counting when they can be separated clearly. The original popsicle example shows the character carrying the same popsicles. For other pictures, an adult can select one complete object to repeat; the review page previews the exact cutouts and explains how they will be used. Story stars remain an explicit fallback.

Uploaded or camera photographs now pass through local paper-edge detection, perspective correction and shadow reduction before object extraction. Visitors can compare the original and prepared photo, adjust all four corners, disable shadow reduction or restore the original. **Try a photo example** demonstrates the full character/video flow using a clearly labeled simulated worksheet photograph. Real-phone accuracy has not yet been benchmarked.

The Python apps described below remain the local Mac version.

Turn a worksheet picture or supported text question into a narrated math cartoon. The default image reader now uses **Qwen3-VL-4B-Instruct-4bit**, a pretrained vision-language model running locally with MLX. Python validates its structured reading and computes the answer; the existing cartoon renderer creates the explanation.

The model uses visual features learned during pretraining. It does **not** retrain itself on each upload. Fine-tuning on labeled classroom worksheets would be a separate future project. Default operation uses no cloud inference or paid audio. An optional, explicitly enabled Gemini connector is now available; it requires separate API access and is off by default.

## New: separate Character Studio

Run `python -m character_studio` in the activated project environment to open **http://127.0.0.1:8601**. Draw with a mouse/stylus/touch using brushes, an eraser, straight lines, shapes, fill, and mirror drawing. Or combine masks, helmets, wings, capes, badges, gloves, boots, and colors. Browser drafts, undo/redo, and in-page confirmations help protect work while children experiment.

Save a character, search the collection by name, reopen **Edit a copy**, or **Make a twin**. Download a `.character.zip` package and use **Import a character** to restore its exact picture and editable parts as a new entry. Earlier saved characters stay intact. Save or download important work; browser drafts are not backups.

Open a saved character and click **See me move** to preview its actions. Compatible parts characters wave, blink, move their arms, and open their mouths during lesson explanations. Drawings and older or mismatched imports move intact as gently animated pictures, preserving their original features. These are simple action loops; automatic drawing rigs and sound-by-sound lip sync remain future work.

With the lesson app running, click **Use in my lesson** to open **http://127.0.0.1:8501** with the character selected. You can also select **Studio library** in the lesson app's friend chooser. Character selection alone does not read a worksheet or start rendering; the normal read, adult review, and generate steps still apply.

The studio includes local drawing cleanup and a manual export-to-Gemini-app workflow for existing student subscriptions. An optional automatic Gemini image-editing connector and Gemini worksheet reader are implemented but disabled until an adult configures API access. A student subscription does not establish free image API usage. See [Character Studio instructions](character_studio/README.md) for setup, the video connection, Gemini options, and current limits.

## Run the connected app in VS Code

Open `/Users/ryanzhang/Desktop/Capstone_Video Generation` in VS Code and choose **Terminal → New Terminal**. Run:

```sh
source .venv/bin/activate
python -m lesson_video.web
```

The launcher starts the Streamlit screen and Flask lesson service together, then opens **http://127.0.0.1:8501**. Keep that terminal open; **Control+C** stops both services, including their active speech/encoding processes. If the page is already open, refresh it after restarting. Port conflicts can be avoided with `--port 8502 --api-port 5002`.

1. Choose a robot, fox, or bear and customize its name, colors, clothes, and accessories. Or choose **Studio library** to use a character you drew or built; a studio **Use in my lesson** link selects it for you.
2. Try the included popsicle picture, upload a PNG/JPEG, or use the camera. Keep one complete exercise in the image. Camera access requires browser permission and may depend on the browser.
3. Click **Read my picture**. The local vision model reads the worksheet; Python validates the task and calculates the answer.
4. A teacher or grown-up checks the picture, question, quantities, answer, and optional lesson script, then checks the confirmation box and clicks **Make my video**.
5. Watch the narrated cartoon in the page or download the MP4.

Changing character controls only changes the preview. Each reading saves its own picture, character, and lesson plan. Generation uses that reviewed plan without asking the model to interpret the picture again. If a reading is wrong, start a new lesson with a clearer or cropped image; editing the interpretation is future work.

This is a **local, supervised prototype**, with a connected frontend and backend. It has no cloud deployment or child accounts. The service listens only on this computer and uses per-job access tokens. These are not a replacement for production authentication. Reading and rendering run one job at a time so they do not compete for the local GPU. Status survives browser refresh and backend restart, but the current screen does not yet have a history/recovery page; refreshing the screen can lose its active job link. Keep the page open until the video finishes.

App files and uploaded pictures stay in `.cache/web_jobs/` until you remove them. Logs are in `output/web_prototype/`. Model weights use the shared Hugging Face cache. The app uses no paid API or cloud inference.

For a fresh compatible Apple silicon Mac environment, install FFmpeg separately, then:

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-web.txt
python -m lesson_video.setup_vision
python -m lesson_video.web
```

The exact tested package versions are also saved in `requirements-web.lock.txt`. The current voice uses macOS `say`; a Linux/cloud voice adapter is still needed before cloud deployment. A production deployment also needs shared storage, a durable work queue, authentication, and deployment-specific GPU tests. The current Flask development server is only for local use.

## Run the command-line generator

Open this folder and choose **Terminal → New Terminal**. The Desktop project has a `.venv` with the local vision dependencies installed. Run:

```sh
source .venv/bin/activate
python -m lesson_video --image "examples/worksheets/user_popsicle_addition.png" --out output/popsicle_lesson
open "output/popsicle_lesson/lesson.mp4"
```

For another picture, replace the path after `--image`. Use a new output folder to keep previous results. Crop to one complete exercise when possible. The model can understand varied illustrations without a programmed list of object categories; the lesson types are still bounded to addition, subtraction, counting, and basic shapes.

To inspect the reading before making audio or video:

```sh
python -m lesson_video --image "examples/vision_eval/case_04.png" --inspect-only --out output/picture_check
open "output/picture_check/model_interpretation.json"
open "output/picture_check/explanation.txt"
```

Each successful picture run saves `worksheet_input.png`, `worksheet_annotated.png`, `worksheet_reading.json`, `model_response.txt`, `model_interpretation.json`, `lesson.json`, and `explanation.txt`. Video runs also save `lesson.mp4`, `narration.wav`, captions, a transcript, a poster, and verification results. A run replaces files in its chosen output directory.

Optional crop coordinates are **X Y WIDTH HEIGHT**, measured after image orientation:

```sh
python -m lesson_video --image "worksheet.png" --crop 0 10 520 80 --out output/cropped_lesson
```

## Install on another Apple silicon Mac

Tested here with an M4 Pro, 24 GB memory, Python 3.13.9, and MLX-VLM 0.7.9. The local model download is approximately 3.1 GB; allow additional room for Python dependencies. This project's tested setup uses Apple silicon and macOS. Linux GPU/CPU compatibility is not verified for this pipeline. FFmpeg and ffprobe must be on PATH to render videos.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-vision.txt
python -m lesson_video.setup_vision
```

`setup_vision` explicitly downloads the public model once to the shared Hugging Face cache. Normal picture reading uses cached files only and refuses to download a model. Pictures are processed on this computer. Both project copies on this Mac reuse the same cached weights. Model weights and `.venv` are excluded from the source ZIP.

The exact package versions used for this run are recorded in `requirements-vision.lock.txt`. To reproduce that environment with compatible Python, install that file instead of `requirements-vision.txt`.

## What the learned reader does

1. The model receives the worksheet image and a generic extraction instruction. Evaluation answers are never included in its prompt.
2. It proposes the task, visible group counts, a possible object name, and an uncertainty state.
3. Python checks the schema, integer range, number of exercises, unknown-operand status, and any printed answer. Python computes the arithmetic.
4. The renderer builds the counting demonstration, a three-second response pause, and the answer.

Matching source cutouts may be reused as artwork when their independently extracted counts agree with the model. This step is optional graphics extraction: a picture is not rejected merely because its object category has no geometric detector. Otherwise, dots stand for the pictured objects, and narration states that representation.

A small vision model can count correctly but name artwork incorrectly. In the actual uploaded example it proposed “jars” for the artwork the user called popsicles. That proposed name is preserved in the review evidence; the cutout video uses the neutral word “pictures.”

## Text questions still work

Text lessons need only `requirements.txt`, FFmpeg, and an installed macOS voice:

```sh
python -m lesson_video "What is 4 + 3?" --out output/text_lesson
python -m lesson_video "Mia has 5 apples and gives away 2. How many are left?" --out output/subtraction
python -m lesson_video "Count 6 dots." --out output/counting
python -m lesson_video "Which is greater, 3 or 5?" --out output/comparison
python -m lesson_video "How many sides does a triangle have?" --out output/shape
```

The explanation-only text command needs no audio/video dependencies:

```sh
python -m lesson_video.explain "What is 4 + 3?" --out output/explanation_check
```

Text parsing uses documented patterns rather than a language model. Whole-number operands are 0–10; addition totals must be at most 10 and subtraction cannot go below zero. Shape lessons cover circle, triangle, square, and rectangle. The vision reader can encounter other object appearances, but cannot invent new lesson types or teaching scenes.

## Checks and measured limits

```sh
python -m unittest discover -s tests -v
python -m lesson_video.check_vision --out output/local_vision_evaluation
```

The unit tests validate arithmetic, failure cases, model-output contracts, image processing, and rendered object counts without downloading or running a model. The separate model evaluation runs real offline inference on **seven development examples**: the actual user upload, five positive cases total with varied artwork, and two cases that should reject multiple questions or a missing operand. This small set is not a classroom accuracy benchmark. Its labels live in `tests/vision_eval_manifest.json` and stay outside model prompts.

The legacy OCR/geometric reader is still available explicitly:

```sh
python -m lesson_video --image "examples/worksheets/03_yellow_dot_addition.png" --reader rules --inspect-only --out output/rules_check
python -m lesson_video.check_worksheets
```

Those 16 synthetic fixtures assess the legacy reader, not learned-model accuracy. The original yellow-dot attachment expired; `user_popsicle_addition.png` is an actual later upload retained in the project.

## Narration and further work

Narration uses the Mac's installed `say` voice, consistent volume, edge fades, and clear pauses. Default Samantha speaks at 145 words per minute. To change it:

```sh
python -m lesson_video "What is 5 - 2?" --voice Karen --rate 140 --out output/another_voice
python -m lesson_video.audio --voices
```

A restricted automation sandbox can block local speech, Apple Vision, or GPU access. Normal Mac Terminal execution uses those local services directly. No paid voice generation is configured.

The model can make counting, wording, and object-recognition errors even when its JSON is valid. The app requires an adult review before rendering. The current checks do not prove that visual counts are correct. More real labeled worksheets, an editable teacher review step, and separate measurements of counting and explanation quality are needed. Fine-tuning or model replacement can then be evaluated against a held-out set rather than adding one rule per object. Learning outcomes have not been tested.

References: [Qwen3-VL model](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct), [MLX quantized checkpoint](https://huggingface.co/mlx-community/Qwen3-VL-4B-Instruct-4bit), [MLX-VLM](https://github.com/Blaizzy/mlx-vlm), [fine-tuning explained](https://huggingface.co/docs/transformers/main/training).
