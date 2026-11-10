# Optional Gemini integration

[Project overview](../README.md) · [Setup](SETUP.md) · [Character Studio](../character_studio/README.md)

The normal browser and local workflows require no provider API key. The Python project also contains optional Gemini drawing-edit and worksheet-reading adapters, disabled by default.

**Integration status:** transport and validation behavior have mocked tests. No live Gemini request was made during development. The configured model IDs are implementation defaults, not verified promises of current account access or provider availability.

## Choose the workflow

| Workflow | What happens | Access needed |
| --- | --- | --- |
| Local drawing polish | Clean lines/background locally; preview before applying. | No Gemini access. |
| Manual Gemini app makeover | Export a drawing, edit it in your own Gemini app, then import a chosen result. | Your own app access. |
| Automatic drawing edit | The Python studio sends a reviewed drawing to Google's API. | Separately configured API access and explicit image enablement. |
| API worksheet reading | Google proposes a reading; the existing Python validator computes the math. | Separately configured API access and reader selection. |

A student-app subscription does not establish API access, quota, or included paid usage. Check the chosen model and your project's terms before enabling calls. This repository does not promise free API usage.

## Manual app workflow

In the Python studio, expand **AI beautify with Gemini**:

1. Download the original drawing PNG.
2. Open Gemini in your own account, attach the drawing, and use the provided makeover request.
3. Download a result you choose and import it using **Bring a drawing**.
4. Save the character and select it for a lesson.

This workflow performs no automatic API request. The original remains available.

## Configure the optional Python connector

Use an API key from your own project. Keep it out of chat, browser code, exported packages, and source control. In **zsh**, enter it without echoing or putting the value in a command:

```sh
read -s "GEMINI_API_KEY?Gemini API key (hidden): "
export GEMINI_API_KEY
export GEMINI_ENABLED=1
```

Choose a provider-supported model that is available to your project. Model configuration is read from these environment variables:

| Setting | Code location |
| --- | --- |
| `GEMINI_IMAGE_MODEL` | `character_studio/gemini_makeover.py` |
| `GEMINI_VISION_MODEL` | `lesson_video/gemini_vision.py` |
| Fixed transport endpoint | `lesson_video/gemini_client.py` |

For drawing edits, also set `GEMINI_IMAGE_ENABLED=1`, then start `python -m character_studio`. Each image request requires the studio's adult confirmation. A result is previewed for acceptance; failed or rejected generation leaves the original intact. Requests do not retry automatically.

For worksheet reading, explicitly select the adapter:

```sh
python -m lesson_video.web --reader gemini
```

Or inspect one picture before rendering:

```sh
python -m lesson_video --image examples/worksheets/user_popsicle_addition.png --reader gemini --inspect-only --out output/gemini_picture_check
```

Starting normally without `--reader gemini` retains the local reader. Narration and video rendering remain local; these adapters do not use a Google video-generation API.

## Data and review boundary

Enabling these adapters changes where the selected image is processed: it is sent to Google. The transport uses a fixed HTTPS endpoint, server-side credentials, bounded request/response sizes, and metadata-free image encoding. Its `store:false` setting does not override the provider's account-level data terms. Adult review and the existing supported lesson range still apply.

Official provider references: [API key setup](https://aistudio.google.com/apikey), [API pricing](https://ai.google.dev/gemini-api/docs/pricing), [image generation/editing](https://ai.google.dev/gemini-api/docs/image-generation), [image understanding](https://ai.google.dev/gemini-api/docs/image-understanding), and [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview).
