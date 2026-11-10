# My Lesson Buddy · unified hosted website

One website combines **Create a buddy → Bring a question → Check together → Watch & discover**. Visitors do not need Python, a terminal, a local server, an API key, or Ryan’s laptop.

Public Site address: **https://my-lesson-buddy-studio.leftcloak4.chatgpt.site**. Public access was explicitly approved by the user; preserve that audience for updates. The Site identity is retained in `.openai/hosting.json`; reuse it for updates.

## What runs where

- Sites hosts the HTML, JavaScript, original artwork, browser runtime, and prerecorded narration.
- Each visitor draws, builds, saves characters, reads pictures, and renders/records lessons in their own browser. There is no localhost connection, tunnel, Python backend, or runtime paid API.
- Character collections and drafts are device/browser-local. They are not shared publicly or synced across devices. Download a `.character.zip` package to keep or move a character. Imports retain original artwork; editing its parts makes a new picture.
- Worksheet and drawing images are not sent to our server or a vision API. Only the optional AI model/runtime are fetched, from the site and the official Hugging Face model repository.
- The optional pretrained SmolVLM-256M reader requires WebGPU. It downloads approximately 264 MB of Q4 model weights plus runtime/tokenizer files on first use and may take several minutes. It is smaller and less accurate than the local Mac Qwen3-VL4B reader. Failed/unclear readings become manual entry, never a fabricated default answer. See `READER_NOTES.md` for its pinned revision and measured limits.
- Adult review is required before preparing a lesson. The selected question and character are copied into an immutable lesson plan; rendering never asks the model to read the worksheet again.
- 317 hosted MP3 clips provide actual narration, including the four adventure worlds and their story actions. The browser routes their decoded audio to speakers and the exported video. Visitors do not need macOS `say`, a microphone, or a speech API.
- The current narration is generated at build time with the local Kokoro-82M neural voice `af_heart`. Conversational prompts use small pacing changes for openings, questions, answers and celebrations. Counting words come from one continuous counting performance, separated using the model's phoneme timings. Immutable audio filenames prevent a cached previous voice from playing against a new scene duration. The same measured audio timeline still drives playback and downloaded video. This is synthetic narration; naturalness has not been measured in a child listening study.
- Canvas + MediaRecorder produce a real narrated video. MP4 is used only when the visitor’s browser actually supports it; otherwise the file is WebM. Keep the tab visible during recording. Unsupported recording browsers can still play the lesson. Video files are downloaded, not permanently hosted.

## Supported lessons

Addition, subtraction, and counting with whole-number quantities 0–10 (addition totals through 10; no negative subtraction), plus naming or counting straight sides of circles, triangles, squares, and rectangles. For arithmetic and counting, the browser first tries to extract the original worksheet objects and uses those exact cutouts in the story. It does not redraw the objects. If automatic separation is uncertain, the adult can select one complete object to repeat, or explicitly choose story stars.

The four included examples have explicit authored question data; choosing an example is not evidence that AI recognized it. Clicking the optional AI reader performs actual model inference, including on examples. All readings can be corrected before review. This is a supervised prototype, not a measured classroom-accuracy or learning-outcomes claim.

## Characters act inside the explanation

Four adventure worlds make the selected character an actor in the math:

- **Addition:** start with the reviewed first group in a wagon, then fetch, carry, and deposit each new star. The next count is spoken after the star arrives.
- **Subtraction:** carry each star to a friend’s basket. The wagon and the gift basket remain distinct; only the wagon’s remainder answers the question.
- **Counting:** visit and point to one star at a time, with one count per item.
- **Shapes:** trace a shape gate and count its straight sides, or inspect its outline and name it after the response pause. A circle never receives invented straight sides.

With original worksheet objects selected, the same stories use the actual cutouts, generic picture narration, and matching mission text. Each individual cutout keeps its stable identity through pickup, transfer, and delivery. Original artwork keeps its aspect ratio and count labels do not cover it.

Characters walk, point, carry, give, think, and speak during actions. Moving props track the actual hand anchors of parts characters. Original drawings participate through whole-character movement with an anchor beside their visible artwork, including narrow or off-center drawings. A small magic ribbon connects their carrying action; the engine never invents their limbs or replaces their artwork.

The adult review shows the story mission, the mathematical steps, and three optional storyboard moments before playback. The story preserves the reviewed operands and operation. It is an authored, deterministic action plan, not an unlimited AI film generator; the optional worksheet model is not asked to invent story facts. Original cutouts or the explicitly selected star representation are shown on review. No personal pictures are uploaded.

Scene state partitions tokens into home, source, moving, and delivered sets. Tests check conservation throughout transfers, actor motion, shape tracing, and zero cases. Per-scene speech offsets align count words with completed actions. The same scene/timing plan drives playback, seeking, and recorded video.

## Different questions, different little adventures

**Garden Picnic**, **Maker Workshop**, **Ocean Discovery**, and **Moon Station** have distinct scenery, palettes, story missions, and opening narration. During adult review, **Story world** can suggest a world from the question or select a specific world. Automatic suggestions avoid the last prepared world when another lesson is prepared; only that world ID is saved locally. Question facts, original object cutouts and stable token identities stay consistent across worlds. The frozen presentation settings are retained for seeking, playback and video export.

Characters are larger and greet, carry, point and celebrate. Slow camera movement, restrained background motion and a small arrival highlight make completed mathematical actions visible. **Gentle motion** stops the camera and ambient animation and suppresses celebration effects while keeping the movements that explain the question. It defaults to the device's reduced-motion preference. The thinking pause freezes background motion. These are design choices intended to offer visual variety; reduced fatigue or improved learning has not yet been measured with children.

Open `/adventures.html` to compare four working, narrated examples and download their videos. Garden Picnic uses the seven original popsicle cutouts; the other three examples clearly use story representations. This gallery uses the same player and recorder as the main studio.

## Match the worksheet objects

Choose a picture and check its quantities, then click **Check our lesson**. **The same little pictures** previews the exact objects your buddy will move. Confirm the cutouts together before making the video. The included original popsicle worksheet automatically produces seven separate popsicles in the reviewed 5+2 lesson.

For a new image that cannot be separated, choose **Choose one object**, drag around one complete picture (or use the percentage position fields), and click **Use this picture**. Review explicitly states that this single original crop will be repeated for the lesson quantities. **Find separate objects** retries full extraction; **Use story stars instead** is an explicit fallback. Changing the worksheet or question invalidates the prior object choice and adult confirmation.

Automatic extraction is a conservative local image-processing step for separated repeated colored artwork on a light background. It uses visual components and repetition, without a list of object names. It declines ambiguous counts, mixed artwork, clipped objects, detached parts, black text and noisy backgrounds; it is not a general learned segmenter or a new accuracy claim for the experimental worksheet reader. Manual cropping works for other artwork after adult review. Shape lessons keep the existing geometry gate. All crops, previews, and video rendering stay in the visitor’s browser.

## Photograph a worksheet

**Take a photo** or **Add a picture** now prepares the photograph before reading or extracting its objects: detect the paper boundary, crop and straighten perspective, then reduce uneven lighting and soft shadows. The original is retained. Use **Prepared worksheet / Original photo** to compare, **Adjust paper edges** to drag the four corners or enter their positions, and **Use original photo** to restore the source. Shadow reduction can be turned off. Every correction starts from the retained original, so repeated adjustments do not repeatedly resample an already-corrected picture. Changing the prepared picture clears any old question/object approval.

Photograph one complete question on white or pale paper, keep every paper corner visible against a distinguishable background, and use even light. Ambiguous or clipped paper is kept unchanged with a manual-corner prompt. Very dark or uncertain lighting is left conservative with a brighter-photo/retake message. The pipeline cannot recover objects hidden by fingers, glare, clipping or overlap. Existing supported math, manual correction and adult review still apply.

**Try a photo example** is explicitly a simulated photo of the original 5+2 popsicle worksheet. Automated pixel tests cover perspective, mild rotation, gradients and soft shadows, retaining seven popsicles or five dots. Severe low-light and missing-edge cases do not invent objects. These reproducible synthetic conditions are not a measured real-phone accuracy benchmark. A real-photo evaluation remains future work. All preparation runs locally in the browser, with no API or model download. The fixture check script is `node scripts/check_photo_fixtures.mjs`; outputs are written under the parent `output/photo_worksheets/` directory.

## Develop or update

From this `web_site` directory:

```sh
npm ci
npm test
npm run build
python3 -m http.server 8610 --bind 127.0.0.1 --directory dist
```

The temporary preview uses `http://127.0.0.1:8610/`. The published website does not need this server. `npm run build` copies the official browser-only Transformers.js distribution and its matching ONNX runtime, bundles the ZIP library, and checks every hosted narration asset. Dependencies and the model revision are pinned. The Node-only image dependency is patched via `overrides` and is never shipped to visitors.

Publication uses the Sites source workflow: push this source, package the corresponding static `dist` output, save the returned source commit and archive, then deploy the saved version. The user requested a link other people can try, so the intended audience is **public**, with no visitor sign-in. Do not publish `.cache`, user drawings, credentials, `node_modules`, or other project folders.

The existing Python Character Studio and Lesson Buddy remain available separately in the parent project. This browser implementation is an additional hosted experience; it does not remove or overwrite the Mac app.

Narration regeneration is optional and build-time only. From the parent project directory:

```sh
python3 -m venv .venv-speech
.venv-speech/bin/python -m pip install -r requirements-speech.txt
.venv-speech/bin/python scripts/setup_neural_voice.py
.venv-speech/bin/python web_site/scripts/build_narration.py
```

The setup downloads approximately 354 MB of pinned model and voice assets once, verifies their published SHA256 digests, and keeps them outside the website in `.cache/kokoro`. FFmpeg must be installed. Subsequent synthesis runs offline on the developer's CPU. Ordinary website builds use the checked-in MP3s; visitors download neither a voice model nor Python dependencies. There is no paid speech API. `--engine macos --voice Samantha` retains the system-voice build option. `scripts/compare_neural_voice.py --with-classic` generates a same-text listening comparison on a Mac. The earlier Mac narration assets are retained for comparison and rollback; only the current manifest is used in lessons.
