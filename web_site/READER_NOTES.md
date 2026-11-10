# Experimental browser worksheet reader

The unified Site can make a real, optional pretrained-model request entirely in the visitor's browser. This is a different, substantially smaller model than the Mac prototype's Qwen3-VL 4B. No comparable worksheet accuracy is claimed.

## Pinned sources

- JavaScript: `@huggingface/transformers` **3.8.1**, verified in the npm registry. The official SmolVLM browser example uses the same `AutoProcessor`, `AutoModelForVision2Seq`, `TextStreamer`, `load_image`, and `InterruptableStoppingCriteria` interfaces with Transformers.js 3.7.1.
- Model: `HuggingFaceTB/SmolVLM-256M-Instruct`, immutable revision **7e3e67edbbed1bf9888184d9df282b700a323964**.
- ONNX dtype: `q4`; execution provider: `webgpu`.
- The three q4 weight files total **263,889,326 bytes**: decoder 86,562,901; token embeddings 113,541,438; vision encoder 63,784,987. Runtime, tokenizer and configuration files add to the first-use download. “About 264 MB of model weights, plus runtime” is the notice; do not describe this as a tiny instant download.
- Npm 3.8.1 pins ONNX Runtime Web `1.22.0-dev.20250409-89f8206ba4`. The Site build must copy its matching `ort-wasm*.wasm` and `ort-wasm*.mjs` files to `dist/vendor/ort/`, and emit the browser Transformer exports at `dist/vendor/transformers.js`.

Official references inspected:

- [Official browser example source](https://github.com/huggingface/transformers.js-examples/tree/main/smolvlm-webgpu)
- [Official published WebGPU demonstration](https://huggingface.co/spaces/HuggingFaceTB/SmolVLM-256M-Instruct-WebGPU/tree/main)
- [Pinned model files](https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct/tree/7e3e67edbbed1bf9888184d9df282b700a323964)
- [Transformers.js documentation](https://huggingface.co/docs/transformers.js/en/index)
- [Published npm package metadata](https://registry.npmjs.org/@huggingface%2ftransformers/3.8.1)

## UI contract

`browserReaderStatus()` checks secure context, worker support, and a WebGPU adapter. It does not import the heavy vendor library, construct a worker, download a model, or send a worksheet anywhere.

Only call `readWorksheet(dataURL, { onProgress, signal })` after a deliberate user action with the first-use download notice visible. Keep manual question entry and correction available on every device. A successful interpretation **always** has `needs_review: true`. Do not automatically generate from model output.

Result fields are `type`, arithmetic `a`/`b`, counting `count`, or `shape` plus `shape_task` (`name` or `sides`). `answer` is computed in JavaScript after strict validation. Optional `object_name` is a bounded plain label. The model cannot choose scripts, paths, URLs, hosting options, voice settings or renderer controls.

Progress callbacks receive `{stage, message, progress?, loaded?, total?}`. Stage is `preparing`, `loading`, or `reading`. Download percentages are per-file progress events, not a guaranteed overall ETA. Display `message` as text. Cancellation terminates the active worker, so a canceled download or GPU job cannot return a result into a later worksheet. Calls are serialized per page. A later successful call reuses the loaded model; `disposeWorksheetReader()` frees its worker when no longer needed.

Images must be data URLs for PNG, JPEG, or WebP, under the encoded size limit, at most 20 megapixels and at least 32 pixels on each side. Before inference, the browser removes metadata by flattening onto a white canvas and re-encoding PNG with a maximum edge of 1024 pixels. The processor uses one image without patch splitting to bound memory. This can lose detail in dense or multi-question sheets; crop one clear exercise.

Worksheet pixels remain on the visitor's device. The browser fetches public, revision-pinned model files from Hugging Face and the local Site runtime; it does not call a paid inference endpoint or upload the image to the Site server. The first model-file download is still an ordinary external network request. Browser cache retention is controlled by the browser and may be evicted. WebGPU support and available GPU memory vary, including on phones.

## Validation and honest limits

The model receives a short natural instruction to write the pictured arithmetic equation, using `?` for a blank answer, or `COUNT` with the quantity, `NAME`/`SIDES` with the shape, or `UNCLEAR`. It is not asked to construct a large JSON object or copy literal operand placeholders. Generation is capped at 48 new tokens. No actual worksheet's quantities or example answers appear in the prompt.

The parser accepts only a complete numeric addition/subtraction expression, optionally with `= ?` or a consistent numeric answer, or the compact `ADD a b`, `SUB a b`, `COUNT n`, `NAME shape`, or `SIDES shape` compatibility formats. Prose, multiple lines, malformed output, unsupported shapes, missing operands and out-of-range or negative results are rejected. It never guesses missing counts. Numeric equation answers are recomputed and a mismatched model-written answer is rejected.

These equation or compact suggestions are untrusted candidates, **not** assertions of model confidence or independently verified exercise count. Every suggestion requires comparison with the photograph and adult correction. The browser parser cannot prove that the model noticed multiple questions, an unknown operand, a different symbol, or an incorrect printed answer that it omitted from the text. A `readingFormat: equation_candidate` or `compact_candidate` result does not invent those metadata assertions.

For compatibility, the parser also accepts the earlier single flat structured JSON object, optionally fenced as JSON. That path additionally rejects duplicate keys, multiple objects, surrounding prose, unexpected fields, nested objects, multiple exercises, uncertain readings and mismatched printed answers when the model provides the corresponding required metadata. Addition totals and all quantities are bounded to 0–10; subtraction cannot be negative.

These checks establish a supported internal lesson and consistent math. They **do not establish that the model counted the photograph correctly**. The adult still needs to compare the interpretation with the worksheet. A 256M model may fail to produce the requested JSON, miscount repeated art, or miss a sign; failures lead to manual review/correction, not an invented default problem.

The Node tests verify validation, image preparation boundaries, no download during feature checks, request isolation, cancellation, failure messages and progress handling with a mocked worker. They do not constitute a model-accuracy test or proof of real WebGPU inference. Record real browser inference results separately before making a broader recognition claim.

## Live browser smoke test, November 2, 2026

Actual WebGPU inference loaded the pinned model and ran on the included, previously labeled popsicle picture (5 + 2). Three prompt formats were tried without providing its counts to the model. All returned malformed or irrelevant text, which was rejected. The final short natural prompt returned “The number 7 is not present.” No valid automatic interpretation was established. The UI retained the authored example and offered manual entry; it did not turn the model text into a default answer. These results are a concrete current limitation, not a photo-accuracy benchmark. Browser-native character creation, adult-reviewed example/manual lesson generation, and actual narrated video export were tested separately.
