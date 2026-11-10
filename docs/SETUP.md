# Run My Lesson Buddy

[Project overview](../README.md) · [Architecture](ARCHITECTURE.md) · [Evaluation](EVALUATION.md)

Choose the setup that matches your goal. The hosted website needs no installation; local development requires the corresponding environment.

## Try the hosted website

Open [My Lesson Buddy](https://my-lesson-buddy-studio.leftcloak4.chatgpt.site), create a character, and choose an included question or enter one manually. Check the lesson with an adult, then play or download the explanation.

Automatic picture reading is optional. It needs a compatible WebGPU device and downloads about 264 MB of model weights, plus runtime files, on first use. Manual entry and examples remain available when automatic reading fails. Keep the tab visible while recording a video.

## Get the project in VS Code

```sh
git clone https://github.com/zryan0201/my-lesson-buddy.git
cd my-lesson-buddy
```

Open this folder in VS Code and select **Terminal → New Terminal**. Run the commands below from the repository root unless a guide explicitly changes directories.

## Develop the browser website

Install Node/npm and Python for the static server, then run:

```sh
cd web_site
npm ci
npm test
npm run build
python3 -m http.server 8610 --bind 127.0.0.1 --directory dist
```

Open **http://127.0.0.1:8610/**. Keep this terminal open during local testing; **Control+C** stops the server. The published website runs independently of it.

This route uses checked-in narration clips and builds the browser libraries. It does not require the Python lesson environment or a vision API key. See the [browser guide](../web_site/README.md) for the full workflow and export behavior.

## Python lesson app on an Apple silicon Mac

The local picture-reading pipeline was tested with macOS, an M4 Pro with 24 GB memory, Python 3.13.9, and MLX-VLM 0.7.9. Its Linux, Windows, and other GPU configurations are not verified. Install FFmpeg and ffprobe and ensure both are on your PATH.

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-web.txt
python -m lesson_video.setup_vision
python -m lesson_video.web
```

The explicit setup step downloads the vision model once, approximately 3.1 GB. Normal worksheet reading uses cached weights and does not download a model. Allow additional space for dependencies.

The launcher starts both the Streamlit screen and the Flask lesson service. Open **http://127.0.0.1:8501/** and keep the terminal open. **Control+C** stops both services and their active speech/encoding processes.

For later sessions:

```sh
source .venv/bin/activate
python -m lesson_video.web
```

To avoid occupied ports, use `python -m lesson_video.web --port 8502 --api-port 5002`. If selecting a VS Code Python interpreter, choose this project's `.venv/bin/python`.

The exact tested environment is recorded in `requirements-web.lock.txt`. To reproduce those versions, install that lockfile in place of `requirements-web.txt` with a compatible Python version.

## Character Studio by itself

This route needs no vision model. From the repository root:

```sh
python3 -m venv .venv-character
source .venv-character/bin/activate
python -m pip install -r requirements-character.txt
python -m character_studio
```

Open **http://127.0.0.1:8601/**. If the full Python lesson environment is already installed, activate `.venv` instead and run the last command. See the [studio guide](../character_studio/README.md) to connect a saved character to a lesson.

## Text lessons without a vision model

On a Mac with FFmpeg and an installed system voice, create a minimal environment:

```sh
python3 -m venv .venv-text
source .venv-text/bin/activate
python -m pip install -r requirements.txt
python -m lesson_video "What is 4 + 3?" --out output/text_lesson
open output/text_lesson/lesson.mp4
```

The default command-line voice is macOS Samantha. Text parsing uses supported patterns; it does not call an LLM. For an explanation without audio/video, use `python -m lesson_video.explain "What is 4 + 3?" --out output/explanation_check`.

## Evaluate worksheet reading

Saved results and images are already in the repository. Read the [evaluation summary](EVALUATION.md) first; no model is needed to inspect them. The [benchmark guide](../worksheet_benchmark/README.md) explains its separate build/scoring environment and local-model runs.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `localhost` refuses the connection | Start the matching local server and keep its terminal open; hosted links do not require it. |
| Python cannot find a package | Activate the environment for that route and install its requirements. |
| The local model is missing | Run `python -m lesson_video.setup_vision` explicitly in the vision environment. |
| FFmpeg or a system voice is unavailable | Verify the Mac prerequisites; use the browser edition for its prerecorded narration. |
| Browser reading is unavailable or wrong | Use manual question entry and compare the result with the source picture. |
| A character is absent from the Python lesson app | Use the same project/library location and refresh the character library. |
| An HTML result shows source code on GitHub | Clone/download the repository and open the HTML file locally. |

API keys are not required for the normal workflows. The [optional Gemini guide](OPTIONAL_GEMINI.md) describes the separate, disabled-by-default provider integration.
