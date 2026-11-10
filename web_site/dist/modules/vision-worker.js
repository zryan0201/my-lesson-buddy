/** Actual pretrained image-to-text inference, not worksheet-specific heuristics. */
import {
  AutoProcessor,
  AutoModelForVision2Seq,
  InterruptableStoppingCriteria,
  TextStreamer,
  env,
  load_image,
} from '../vendor/transformers.js';
import { VISION_SETTINGS, VISION_PROMPT, validateImageDataURL } from './reader.js';

env.allowLocalModels = false;
env.useBrowserCache = true;
env.backends.onnx.wasm.wasmPaths = new URL('../vendor/ort/', import.meta.url).href;
env.backends.onnx.wasm.numThreads = 1;
env.backends.onnx.wasm.proxy = false;

let modelPromise = null;
let busy = false;
let activeId = null;
const stopping = new InterruptableStoppingCriteria();

function progress(id, stage, event = {}) {
  const value = { id, type: 'progress', stage };
  for (const key of ['progress', 'loaded', 'total']) if (Number.isFinite(event[key])) value[key] = event[key];
  self.postMessage(value);
}

async function getModel(id) {
  if (!modelPromise) {
    const options = { revision: VISION_SETTINGS.revision, progress_callback: (event) => progress(activeId || id, 'loading', event) };
    modelPromise = Promise.all([
      AutoProcessor.from_pretrained(VISION_SETTINGS.modelId, options),
      AutoModelForVision2Seq.from_pretrained(VISION_SETTINGS.modelId, {
        ...options,
        dtype: VISION_SETTINGS.dtype,
        device: VISION_SETTINGS.device,
      }),
    ]).catch((error) => { modelPromise = null; throw error; });
  }
  return modelPromise;
}

async function readImage(id, imageDataURL) {
  const [processor, model] = await getModel(id);
  const image = await load_image(validateImageDataURL(imageDataURL));
  const messages = [{ role: 'user', content: [
    { type: 'image' },
    { type: 'text', text: VISION_PROMPT },
  ] }];
  const text = processor.apply_chat_template(messages, { add_generation_prompt: true });
  const inputs = await processor(text, [image], { do_image_splitting: false });
  progress(id, 'reading');
  stopping.reset();
  let streamed = '';
  let lastProgress = 0;
  const streamer = new TextStreamer(processor.tokenizer, {
    skip_prompt: true,
    skip_special_tokens: true,
    callback_function: (part) => {
      if (typeof part === 'string' && streamed.length < 12000) streamed += part;
      if (performance.now() - lastProgress > 700) { progress(id, 'reading'); lastProgress = performance.now(); }
    },
  });
  const result = await model.generate({
    ...inputs,
    max_new_tokens: VISION_SETTINGS.maxNewTokens,
    do_sample: false,
    repetition_penalty: 1.1,
    // Returning sequences only lets Transformers.js dispose final GPU KV buffers.
    // Every worksheet starts with new inputs; no conversational cache is retained.
    return_dict_in_generate: false,
    stopping_criteria: stopping,
    streamer,
  });
  const sequences = result.sequences || result;
  let raw = streamed;
  if (typeof sequences?.tolist === 'function' && Array.isArray(inputs.input_ids?.dims)) {
    const sequence = sequences.tolist()[0];
    const length = inputs.input_ids.dims[inputs.input_ids.dims.length - 1];
    if (Array.isArray(sequence) && Number.isInteger(length)) raw = processor.tokenizer.decode(sequence.slice(length).map(Number), { skip_special_tokens: true });
  }
  if (typeof raw !== 'string' || !raw.trim() || raw.length > 12000) throw new Error('Invalid model response');
  self.postMessage({ type: 'result', id, raw });
}

self.addEventListener('message', async ({ data }) => {
  if (!data || typeof data.id !== 'string' || !/^read-\d+$/.test(data.id)) return;
  if (data.type === 'cancel' && data.id === activeId) { stopping.interrupt(); return; }
  if (data.type !== 'read') return;
  const { id, imageDataURL } = data;
  if (busy) { self.postMessage({ type: 'error', id, code: 'BUSY' }); return; }
  busy = true;
  activeId = id;
  try {
    validateImageDataURL(imageDataURL);
    await readImage(id, imageDataURL);
  } catch {
    // Do not post library exceptions, remote response bodies, or image data.
    self.postMessage({ type: 'error', id, code: 'UNAVAILABLE' });
  } finally {
    busy = false;
    activeId = null;
  }
});
