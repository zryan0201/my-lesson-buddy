# Local AI drawing polish

[Browser guide](README.md) · [Architecture](../docs/ARCHITECTURE.md)

This feature gently restores image detail while keeping the original drawing available. It uses a pretrained super-resolution model, not a text prompt, keyword transformation, or paid image-generation service. The child compares two versions and chooses which one becomes the lesson character.

## Model and runtime

| Setting | Value |
| --- | --- |
| Model | `Xenova/swin2SR-lightweight-x2-64` |
| Revision | `92a21aca5713f20faf9a87590cdfbdce2e34112c` |
| ONNX file | `onnx/model.onnx`, fp32, 8,078,888 bytes |
| File SHA-256 | `c2abbfe0cc8e685b5e11964970f8ebe3d24072e904fd5545a30ac31ec1e110db` |
| Runtime | Transformers.js 3.8.1; ONNX Runtime Web in a dedicated worker |
| Acceleration | WebGPU when supported, with WebAssembly CPU fallback |
| Tiling | 128×128 core, 16-pixel reflected halo, 160×160 model input |
| Scale | 2× width and height; capped studio input edge 960 pixels |
| Limits | One job per worker, eight-minute timeout; cancel terminates worker |

Primary references: [ONNX model and documented image-to-image pipeline](https://huggingface.co/Xenova/swin2SR-lightweight-x2-64), [original model's intended use and Apache 2.0 license](https://huggingface.co/caidas/swin2SR-lightweight-x2-64), [research code](https://github.com/mv-lab/swin2sr).

Model weights and runtime are downloaded only after a deliberate button click. Browser cache retention is device-dependent. Downloads contact Hugging Face and expose ordinary request metadata to that host; drawing pixels remain on the device. No API key or paid inference is used. A compatible browser needs a secure context, Worker, WebAssembly, and ordinary canvas support. A CPU job can take several minutes; cancellation and the original drawing remain available.

## Preserving authorship

1. Keep the untouched canvas PNG as the source. Reject blank/near-white canvases, unsupported sources, and unbounded pixel buffers before model work.
2. Run restoration in tiles at the original input resolution. Crop reflected halos when stitching the 2× output. Every output pixel belongs to one tile.
3. Compare the learned output with an ordinary 2× interpolation of the original. Clamp the learned RGB residual to ±40 levels per channel, then blend with the child's strength setting (default 60%). Preserve original alpha and near-white paper pixels exactly relative to that interpolation. These constraints limit changes; they do not prove semantic identity.
4. Show labeled original/enhanced previews. Keep the original selected until the child chooses **Use enhanced drawing**. The original canvas is never overwritten by enhancement.
5. Save the selected image through the normal drawing-character pipeline. It moves intact and uses its visible-ink prop anchor in reviewed lessons. This feature does not infer a skeleton, add limbs, generate new costumes, or make a new illustration from a rough sketch.
6. Editing the canvas cancels active work and invalidates the old comparison. Switching creation tabs cancels active inference; leaving character creation releases the worker before worksheet reading. Request IDs and source snapshots block stale results.

The original and bounded full-strength version are retained in the browser draft when storage permits; the strength and selected version are restored without rerunning the model. If storage is full, attempt to retain the original draft and tell the user to save the AI character separately. **Download my original drawing** provides an explicit backup. Saved library entries remain independent of later draft changes. Exporting a character package preserves the selected character, rather than both comparison images.

## Evidence and remaining work

`npm test` includes pixel-exact zero strength, residual/alpha/white constraints, full tile coverage, reflected halos, input rejection, no eager model download, unsupported devices, buffer ownership, job serialization, stale results, cancellation, malformed output, timeout, and failure retry. Client lifecycle tests use mock workers and do not measure visual quality.

An actual CPU model probe on the repository's demo robot produced 192×256 output from a 96×128 input. Actual browser testing enhanced the 720×840 demo canvas to 1440×1680, restored the chosen 80% strength and enhanced selection after reload, verified the original PNG remained identical, exercised cancellation, and saved the enhanced character into a narrated 5+2 popsicle lesson. These are development checks, not evidence of improvement across children's drawings. The pretrained model was developed for image super-resolution, not evaluated here on a child-drawing dataset. Benefits may be subtle on clean/high-resolution lines. Rough sketch redesign, stylistic beautification, and learned animation rigs require separate models and evaluation. The existing caregiver review remains required before a lesson video.
