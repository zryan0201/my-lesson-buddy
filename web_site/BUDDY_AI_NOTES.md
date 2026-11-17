# Describe my buddy: local text-to-parts AI

[Browser guide](README.md) · [Architecture](../docs/ARCHITECTURE.md)

Children can describe a character, inspect a proposed combination, accept it into the parts builder, edit it, then save and use it in a reviewed lesson. This browser feature uses a real pretrained language model. It does not call a paid API, synthesize a new raster image, or beautify drawings.

## Reproducible model configuration

| Setting | Value |
| --- | --- |
| Model | `onnx-community/Qwen3-0.6B-ONNX` |
| Pinned revision | `79346d370dfae34801d26993fda9ae2372900fd0` |
| Weights | `q4f16`, 569,789,750 bytes |
| First-use download | About 580 MB including tokenizer files, plus runtime |
| Runtime | Transformers.js 3.8.1 / ONNX Runtime Web; dedicated WebGPU worker |
| Device requirements | Secure context, Worker, WebGPU adapter with `shader-f16` |
| Generation | Thinking disabled, deterministic decoding, 240-token limit |
| Input/job limits | 3–320 characters, one active job, eight-minute timeout |

Sources: [ONNX model card](https://huggingface.co/onnx-community/Qwen3-0.6B-ONNX), [original Qwen model and Apache 2.0 license](https://huggingface.co/Qwen/Qwen3-0.6B), [Transformers.js dtypes](https://huggingface.co/docs/transformers.js/guides/dtypes).

No model downloads begin on page load or tab selection. A deliberate generation click starts the download. Browser caching can avoid subsequent downloads, subject to browser storage policies; first use still requires an internet connection. Downloads contact Hugging Face, exposing ordinary request metadata to that host. Character descriptions and pictures are not sent with those requests. No account, API key, or inference fee is needed.

## Contract and lifecycle

1. Validate length and obvious email, phone, URL, and unsuitable-keyword patterns locally. Treat the description as untrusted data.
2. Apply a fixed prompt and examples in a dedicated worker. The pinned ONNX runtime uses Uint16 storage for half tensors, so the worker disables the newer native `Float16Array` global for compatibility; the application window is untouched.
3. Constrain each generated token to a trie of the ordered JSON fields and allowed values. The neural model chooses values; it cannot invent keys, free-form prose, code, URLs, or executable output.
4. Independently reject malformed JSON, duplicate/unknown/missing fields, and unsupported parts or colors. Normalize through the existing character contract.
5. Preview separately from the current character. **Use these parts** copies the proposal into the ordinary editable builder, retaining the child's chosen name and face color. Saving creates a normal character package with the existing joints and prop anchors.
6. Cancel on request or when leaving creation. Ignore stale request IDs, terminate failed/timed-out workers, and release the model before worksheet inference. No drawing, character package, or worksheet is passed to the language-model worker.

There are eight parts fields and three palette fields. The current catalogue has kid, robot, and creature bodies, existing head/eye/accessory options, and fourteen named colors. “Cat” maps to the creature/ears combination rather than a newly drawn cat. Unsupported concepts are approximated; the user must check the result.

## Verification and limits

Run `npm test` from this directory. The character AI tests cover token grammar and logits masking, strict parsing, existing lesson object invariants, no eager download, device fallbacks, cancellation races, stale results, timeouts, and sanitized failures. Worker lifecycle tests use a mock worker; they are not model-quality measurements.

Development also ran six constrained proposals through the actual pinned model on CPU: all returned valid editable records, but one little-hero request missed requested parts. The system prompt was clarified afterward. These small development probes are not an accuracy benchmark. The real browser WebGPU flow was also exercised: generate a purple winged robot, accept it, edit boots/name, save it, and use it in the narrated 5+2 popsicle lesson.

English descriptions are the tested initial path. Broader language, device, accessibility, and child-usability testing remains open. Constrained output restricts what can be rendered; it does not establish semantic understanding or comprehensive child-content moderation. Keyword input checks are basic and can miss obfuscations or other languages. This remains a caregiver-supervised prototype. Build it and Draw it work when local AI is unsupported, fails, or is cancelled.
