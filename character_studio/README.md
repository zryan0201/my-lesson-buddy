# Character Studio

[Project overview](../README.md) · [Installation](../docs/SETUP.md#character-studio-by-itself) · [Use in a lesson](#use-a-saved-character-in-a-lesson) · [Optional Gemini](../docs/OPTIONAL_GEMINI.md)

Create an original character by drawing or combining modular parts. This standalone Python studio runs without a vision model, API key, or paid service. The [combined browser website](../web_site/README.md) includes its own character tools.

## Start the studio

From the repository root, after installing the [local dependencies](../docs/SETUP.md):

```sh
source .venv/bin/activate
python -m character_studio
```

Open **http://127.0.0.1:8601/**. Keep the terminal open; **Control+C** stops the studio. Use `--port 8602` if the default port is occupied. A standalone `.venv-character` environment is also supported; the full lesson environment already includes the studio's dependencies.

## Choose how to create

| Mode | Tools | Result |
| --- | --- | --- |
| **Draw it** | Brush, eraser, line, rectangle, circle, fill, mirror, image import, undo/redo. | The child's original artwork. |
| **Build it** | Body, face, eyes, mask/helmet/ears/antenna, symbol, cape/wings, gloves, boots, four colors, and four starters. | Editable original parts and a rendered character. |
| **Preview polish** | Local line/background cleanup with an original/result preview. | Optional cleanup, applied only if chosen; not AI generation. |

Drawing supports a mouse, touch, or stylus. Undo works with Command/Ctrl+Z; redo works with Command/Ctrl+Shift+Z or Ctrl+Y. Applying local polish remains undoable, and the original stays downloadable. Dark/textured paper may need additional preparation.

The browser saves drafts when storage is available. Confirmations protect clearing, replacement, and opening an existing character. Browser drafts and undo history are conveniences, not backups; save or export important work.

## Save, edit, and share

Name the character and click **Save my character**. Each save makes a new library entry. **Find a buddy** searches the collection; selecting one opens its preview.

| Control | Behavior |
| --- | --- |
| **Edit a copy** | Reopen its parts or artwork; saving creates a new character and preserves the original. |
| **Make a twin** | Save an identical new entry without replacing the draft. |
| **Character package** | Export a `.character.zip` containing the PNG, editable parts when available, and a README. |
| **Import a character** | Validate and restore a package under 8 MB as a new entry. |
| **Download PNG** | Save the finished image; use a package to retain editable parts. |
| **See me move** | Preview a selected wave, explaining, or celebration action locally. |

Uploads accept PNG/JPEG under 8 MB and up to 12 million pixels. Saved artwork is 600 × 800 RGBA. Character names allow 1–32 supported letters/numbers, spaces, apostrophes, and hyphens, including non-English letters. Imported packages are data, not executable projects.

## Use a saved character in a lesson

Keep the studio running. In a second terminal at the same repository root:

```sh
source .venv/bin/activate
python -m lesson_video.web
```

1. Save a character in the studio.
2. Click **Use in my lesson** to open **http://127.0.0.1:8501/** with it selected.
3. Add a worksheet and click **Read my picture**.
4. Review the question with an adult and choose **Make my video**.

Alternatively, select **Studio library** in the lesson app's **Choose a friend** control. **Refresh my character library** updates a collection changed by the studio. If using another lesson-app port, open that address directly and choose from the library.

The service snapshots the character PNG and compatible parts design into the job. Hashes protect the reviewed math, picture, character, and artwork. Editing the library later does not change a reviewed lesson.

## How characters move

Compatible parts designs wave, blink, move their arms, open their mouths, and celebrate using authored action loops. Drawings and older/mismatched imports move intact through gentle tilting, bobbing, and effects. Older packages retain their saved appearance; editing their parts creates a new version with the current renderer.

Automatic drawing rigs and sound-by-sound lip sync remain future work. Animation previews do not generate a lesson or contact an AI service.

## Storage and optional integrations

The default library is `.cache/character_studio/characters/`. Both Python apps must use the same project copy or the same absolute `CHARACTER_STUDIO_STORAGE` value. The studio also accepts `--storage-dir`; the lesson app still needs the matching environment variable. Python libraries and browser-site collections are separate.

Local polish requires no AI. The manual Gemini-app makeover and optional API adapter are described in the [Gemini integration guide](../docs/OPTIONAL_GEMINI.md). API connectors are disabled by default and have no verified live-provider run in this project.

## Implementation map

| Files | Responsibility |
| --- | --- |
| `parts.py`, `motion.py` | Validated parts, jointed artwork, and action previews. |
| `images.py` | Bounded drawing import and local cleanup. |
| `assets.py` | Immutable library entries, copies, snapshots, and package import/export. |
| `app.py`, `static/` | Local Flask API and browser editor. |
| `gemini_makeover.py` | Optional image-editing adapter. |
| `../lesson_video/characters.py`, `web_pipeline.py` | Lesson character rendering and snapshot integration. |

Run the offline suite from the repository root with `python -m unittest discover -s tests -q`. It does not call Google or download a model. Real-child drawing evaluation and usability studies remain future work.
