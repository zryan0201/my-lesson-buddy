/** Optional, experimental vision reading in the visitor's browser.
 * No model, runtime, worker or worksheet request starts when this module is imported.
 * The UI must explain the download and invoke readWorksheet only after a deliberate click.
 */
export const VISION_SETTINGS = Object.freeze({
  modelId: 'HuggingFaceTB/SmolVLM-256M-Instruct',
  revision: '7e3e67edbbed1bf9888184d9df282b700a323964',
  transformersVersion: '3.8.1',
  dtype: 'q4',
  device: 'webgpu',
  weightBytes: 263889326,
  maxImageEdge: 1024,
  maxImagePixels: 20000000,
  maxEncodedBytes: 14 * 1024 * 1024,
  maxNewTokens: 48,
  timeoutMs: 8 * 60 * 1000,
});

export const VISION_PROMPT = `Read the single math question in this picture. For arithmetic, write only the equation with numbers and ? for a blank answer. For counting, write COUNT then the quantity. For shapes, write NAME or SIDES then the shape. If unclear, an operand is missing, or there are multiple questions, write UNCLEAR.`;

export class WorksheetReaderError extends Error {
  constructor(message, code = 'UNAVAILABLE') {
    super(message);
    this.name = 'WorksheetReaderError';
    this.code = code;
  }
}

const MODEL_LABEL = 'Experimental browser AI · SmolVLM 256M';
const DOWNLOAD_LABEL = 'About 264 MB of model weights, plus browser runtime and tokenizer files. The first use can take several minutes.';
const REVIEW_MESSAGE = 'The small browser model could not establish one clear supported question. Check the picture and enter the question yourself.';
let worker = null;
let activeRequest = null;
let nextRequestId = 0;

function readerError(message = REVIEW_MESSAGE, code = 'UNCLEAR') {
  return new WorksheetReaderError(message, code);
}

function abortError() {
  const error = new Error('Worksheet reading was cancelled.');
  error.name = 'AbortError';
  return error;
}

/** Capability check only: does not fetch the library or model. */
export async function browserReaderStatus() {
  const base = { supported: false, modelLabel: MODEL_LABEL, downloadLabel: DOWNLOAD_LABEL };
  if (globalThis.isSecureContext === false) {
    return { ...base, reason: 'Browser AI needs a secure HTTPS page. You can still enter the worksheet question yourself.' };
  }
  if (typeof globalThis.Worker !== 'function' || !globalThis.navigator?.gpu?.requestAdapter) {
    return { ...base, reason: 'This browser does not offer WebGPU for the optional AI reader. You can still enter the worksheet question yourself.' };
  }
  try {
    const adapter = await globalThis.navigator.gpu.requestAdapter();
    if (!adapter) return { ...base, reason: 'No compatible browser graphics adapter is available. You can still enter the worksheet question yourself.' };
    return { ...base, supported: true, reason: 'The optional reader runs on this device. Always check its interpretation before making a lesson.' };
  } catch {
    return { ...base, reason: 'Browser AI is unavailable on this device. You can still enter the worksheet question yourself.' };
  }
}

/** Strict flat JSON keeps duplicate keys and instruction-like extra fields out. */
function parseFlatObject(text) {
  let position = 0;
  const whitespace = () => { while (/\s/.test(text[position] || '') && position < text.length) position += 1; };
  function stringValue() {
    const start = position;
    if (text[position] !== '"') throw readerError();
    position += 1;
    let escaped = false;
    while (position < text.length) {
      const character = text[position++];
      if (escaped) { escaped = false; continue; }
      if (character === '\\') { escaped = true; continue; }
      if (character === '"') {
        try { return JSON.parse(text.slice(start, position)); } catch { throw readerError(); }
      }
    }
    throw readerError();
  }
  function primitiveValue() {
    if (text[position] === '"') return stringValue();
    const start = position;
    while (position < text.length && !/[,}\s]/.test(text[position])) position += 1;
    const raw = text.slice(start, position);
    if (!raw || raw.includes('{') || raw.includes('[')) throw readerError();
    try {
      const value = JSON.parse(raw);
      if (typeof value === 'object' && value !== null) throw readerError();
      return value;
    } catch { throw readerError(); }
  }
  whitespace();
  if (text[position++] !== '{') throw readerError();
  const result = Object.create(null);
  const seen = new Set();
  whitespace();
  if (text[position] === '}') { position += 1; whitespace(); if (position !== text.length) throw readerError(); return result; }
  while (position < text.length) {
    whitespace();
    const key = stringValue();
    if (seen.has(key)) throw readerError();
    seen.add(key);
    whitespace();
    if (text[position++] !== ':') throw readerError();
    whitespace();
    result[key] = primitiveValue();
    whitespace();
    const separator = text[position++];
    if (separator === '}') { whitespace(); if (position !== text.length) throw readerError(); return result; }
    if (separator !== ',') throw readerError();
  }
  throw readerError();
}

export function parseModelReading(raw) {
  if (typeof raw !== 'string' || !raw.trim() || raw.length > 12000) throw readerError();
  let text = raw.trim();
  const fenced = /^```(?:json)?\s*\n?([\s\S]*?)\n?```$/i.exec(text);
  if (fenced) text = fenced[1].trim();
  if (!text.startsWith('{')) return parseCompactReading(text);
  return validateModelReading(parseFlatObject(text));
}

function candidate(value, format) {
  return { ...value, needs_review: true, reader: MODEL_LABEL, modelId: VISION_SETTINGS.modelId,
    modelRevision: VISION_SETTINGS.revision, readingFormat: format };
}

/** A tiny VLM can suggest a short candidate without a complex metadata schema.
 * This grammar makes no claim that confidence, exercise count or image accuracy
 * has been independently verified. The visitor must review every suggestion.
 */
export function parseCompactReading(text) {
  if (typeof text !== 'string' || !text.trim() || text.length > 100) throw readerError();
  const clean = text.trim();
  const equation = /^(10|[0-9])[ \t]*([+\u2212-])[ \t]*(10|[0-9])(?:[ \t]*=[ \t]*(\?|10|[0-9]))?$/.exec(clean);
  if (equation) {
    const type = equation[2] === '+' ? 'addition' : 'subtraction';
    const a = quantity(Number(equation[1]));
    const b = quantity(Number(equation[3]));
    const answer = type === 'addition' ? a + b : a - b;
    if (answer < 0 || answer > 10) throw readerError();
    if (equation[4] !== undefined && equation[4] !== '?' && quantity(Number(equation[4])) !== answer) throw readerError();
    return candidate({ type, a, b, answer }, 'equation_candidate');
  }
  const arithmetic = /^(ADD|SUB)[ \t]+(10|[0-9])[ \t]+(10|[0-9])$/i.exec(clean);
  if (arithmetic) {
    const type = arithmetic[1].toUpperCase() === 'ADD' ? 'addition' : 'subtraction';
    const a = quantity(Number(arithmetic[2]));
    const b = quantity(Number(arithmetic[3]));
    const answer = type === 'addition' ? a + b : a - b;
    if (answer < 0 || answer > 10) throw readerError();
    return candidate({ type, a, b, answer }, 'compact_candidate');
  }
  const counting = /^COUNT[ \t]+(10|[0-9])$/i.exec(clean);
  if (counting) {
    const count = quantity(Number(counting[1]));
    return candidate({ type: 'counting', count, answer: count }, 'compact_candidate');
  }
  const shape = /^(NAME|SIDES)[ \t]+(circle|triangle|square|rectangle)$/i.exec(clean);
  if (shape) {
    const shapeName = shape[2].toLowerCase();
    const task = shape[1].toUpperCase() === 'NAME' ? 'name' : 'sides';
    const answer = task === 'name' ? shapeName : { circle: 0, triangle: 3, square: 4, rectangle: 4 }[shapeName];
    return candidate({ type: 'shape', shape: shapeName, shape_task: task, answer }, 'compact_candidate');
  }
  throw readerError();
}

function quantity(value) {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0 || value > 10) throw readerError();
  return value;
}

export function validateModelReading(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw readerError();
  const allowed = new Set(['status', 'exercise_count', 'type', 'a', 'b', 'count', 'shape', 'shape_task', 'unknown_operand', 'uncertain', 'object_name', 'printed_answer']);
  if (Object.keys(value).some((key) => !allowed.has(key))) throw readerError();
  if (['status', 'exercise_count', 'type', 'unknown_operand', 'uncertain'].some((key) => !Object.hasOwn(value, key)) || value.status !== 'ready' || value.exercise_count !== 1 || value.unknown_operand !== false || value.uncertain !== false) throw readerError();
  const empty = (...fields) => fields.every((key) => value[key] === undefined || value[key] === null);
  const result = candidate({ type: value.type }, 'structured_json');
  if (value.type === 'addition' || value.type === 'subtraction') {
    if (!empty('count', 'shape', 'shape_task')) throw readerError();
    result.a = quantity(value.a);
    result.b = quantity(value.b);
    result.answer = value.type === 'addition' ? result.a + result.b : result.a - result.b;
    if (result.answer < 0 || result.answer > 10) throw readerError();
  } else if (value.type === 'counting') {
    if (!empty('a', 'b', 'shape', 'shape_task')) throw readerError();
    result.count = quantity(value.count);
    result.answer = result.count;
  } else if (value.type === 'shape') {
    if (!empty('a', 'b', 'count') || !['circle', 'triangle', 'square', 'rectangle'].includes(value.shape) || !['name', 'sides'].includes(value.shape_task)) throw readerError();
    result.shape = value.shape;
    result.shape_task = value.shape_task;
    result.answer = value.shape_task === 'name' ? value.shape : { circle: 0, triangle: 3, square: 4, rectangle: 4 }[value.shape];
  } else {
    throw readerError();
  }
  if (value.printed_answer !== undefined && value.printed_answer !== null) {
    if (quantity(value.printed_answer) !== result.answer) throw readerError();
  }
  if (value.object_name !== undefined && value.object_name !== null) {
    if (typeof value.object_name !== 'string' || !/^[a-z]+(?:[ -][a-z]+){0,4}$/i.test(value.object_name) || value.object_name.length > 48) throw readerError();
    result.object_name = value.object_name.toLowerCase();
  }
  return result;
}

export function validateImageDataURL(value) {
  if (typeof value !== 'string' || value.length > VISION_SETTINGS.maxEncodedBytes || !/^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(value)) {
    throw readerError('Choose a PNG, JPEG, or WebP worksheet picture smaller than 10 MB.', 'INVALID_IMAGE');
  }
  return value;
}

export async function normalizeWorksheetImage(imageDataURL, { signal } = {}) {
  validateImageDataURL(imageDataURL);
  if (signal?.aborted) throw abortError();
  if (typeof globalThis.Image !== 'function' || !globalThis.document?.createElement) throw readerError('Image reading is unavailable in this browser. Enter the worksheet question yourself.');
  const image = await new Promise((resolve, reject) => {
    const candidate = new Image();
    const cleanup = () => { candidate.onload = null; candidate.onerror = null; signal?.removeEventListener('abort', aborted); };
    const aborted = () => { cleanup(); candidate.src = ''; reject(abortError()); };
    candidate.onload = () => { cleanup(); resolve(candidate); };
    candidate.onerror = () => { cleanup(); reject(readerError('This worksheet picture could not be opened. Choose another PNG or JPEG.', 'INVALID_IMAGE')); };
    signal?.addEventListener('abort', aborted, { once: true });
    candidate.src = imageDataURL;
  });
  if (signal?.aborted) throw abortError();
  const width = image.naturalWidth;
  const height = image.naturalHeight;
  if (Math.min(width, height) < 32 || width * height > VISION_SETTINGS.maxImagePixels) throw readerError('Crop one clear worksheet question, at least 32 pixels on each side and no more than 20 megapixels.', 'INVALID_IMAGE');
  const scale = Math.min(1, VISION_SETTINGS.maxImageEdge / Math.max(width, height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const context = canvas.getContext('2d');
  if (!context) throw readerError('This browser could not prepare the image. Enter the worksheet question yourself.');
  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/png');
}

function emitProgress(callback, event) {
  if (typeof callback !== 'function') return;
  try { callback(event); } catch { /* A display callback must not break a GPU job. */ }
}

export function disposeWorksheetReader() {
  if (activeRequest) activeRequest.cancel();
  if (worker) worker.terminate();
  worker = null;
}

/** One active inference; cancelling terminates its worker, including any download. */
export async function readWorksheet(imageDataURL, { onProgress, signal } = {}) {
  if (activeRequest) throw readerError('A worksheet is already being read. Wait for it or cancel it first.', 'BUSY');
  if (signal?.aborted) throw abortError();
  validateImageDataURL(imageDataURL);
  const request = { cancelled: false, cancel() { this.cancelled = true; } };
  activeRequest = request;
  try {
    const status = await browserReaderStatus();
    if (!status.supported) throw readerError(status.reason, 'UNSUPPORTED');
    if (signal?.aborted || request.cancelled) throw abortError();
    emitProgress(onProgress, { stage: 'preparing', message: 'Preparing one worksheet question on this device…' });
    const normalized = await normalizeWorksheetImage(imageDataURL, { signal });
    if (signal?.aborted || request.cancelled) throw abortError();
    if (!worker) worker = new Worker(new URL('./vision-worker.js', import.meta.url), { type: 'module', name: 'worksheet-reader' });
    const currentWorker = worker;
    const id = `read-${++nextRequestId}`;
    return await new Promise((resolve, reject) => {
      let finished = false;
      const cleanup = () => {
        clearTimeout(timeout);
        signal?.removeEventListener('abort', cancelled);
        currentWorker.removeEventListener('message', message);
        currentWorker.removeEventListener('error', failed);
        currentWorker.removeEventListener('messageerror', failed);
      };
      const settle = (error, result, terminate = false) => {
        if (finished) return;
        finished = true;
        cleanup();
        if (terminate) { currentWorker.terminate(); if (worker === currentWorker) worker = null; }
        if (error) reject(error); else resolve(result);
      };
      const cancelled = () => settle(abortError(), undefined, true);
      request.cancel = cancelled;
      const failed = () => settle(readerError('Browser AI could not start or ran out of resources. You can still enter the worksheet question yourself.', 'UNAVAILABLE'), undefined, true);
      const message = ({ data }) => {
        if (!data || data.id !== id) return;
        if (data.type === 'progress') {
          const event = { stage: ['loading', 'reading'].includes(data.stage) ? data.stage : 'loading', message: data.stage === 'reading' ? 'The experimental browser model is reading the picture…' : 'Downloading or preparing the browser model…' };
          if (Number.isFinite(data.progress)) event.progress = Math.min(100, Math.max(0, data.progress));
          if (Number.isFinite(data.loaded) && data.loaded >= 0) event.loaded = data.loaded;
          if (Number.isFinite(data.total) && data.total > 0) event.total = data.total;
          emitProgress(onProgress, event);
        } else if (data.type === 'result') {
          try { settle(null, parseModelReading(data.raw)); } catch (error) { settle(error); }
        } else if (data.type === 'error') {
          settle(readerError('The experimental browser reader could not finish. Check the picture and enter the question yourself.', 'UNAVAILABLE'), undefined, true);
        }
      };
      const timeout = setTimeout(() => settle(readerError('The browser reader took too long. You can enter the question yourself or retry with a clearer crop.', 'TIMEOUT'), undefined, true), VISION_SETTINGS.timeoutMs);
      currentWorker.addEventListener('message', message);
      currentWorker.addEventListener('error', failed);
      currentWorker.addEventListener('messageerror', failed);
      signal?.addEventListener('abort', cancelled, { once: true });
      if (signal?.aborted) { cancelled(); return; }
      emitProgress(onProgress, { stage: 'loading', message: DOWNLOAD_LABEL });
      currentWorker.postMessage({ type: 'read', id, imageDataURL: normalized });
    });
  } finally {
    if (activeRequest === request) activeRequest = null;
  }
}
