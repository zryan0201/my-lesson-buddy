import test from 'node:test';
import assert from 'node:assert/strict';
import {
  VISION_SETTINGS,
  browserReaderStatus,
  disposeWorksheetReader,
  normalizeWorksheetImage,
  parseCompactReading,
  parseModelReading,
  readWorksheet,
  validateImageDataURL,
  validateModelReading,
} from '../dist/modules/reader.js';

const imageData = 'data:image/png;base64,AAAA';
const reading = (extra = {}) => ({ status: 'ready', exercise_count: 1, type: 'addition', a: 5, b: 2,
  count: null, shape: null, shape_task: null, unknown_operand: false, uncertain: false,
  object_name: 'popsicles', printed_answer: null, ...extra });

async function browserFixture(callback, { gpu = true, width = 2048, height = 1024 } = {}) {
  const keys = ['navigator', 'Worker', 'Image', 'document', 'isSecureContext'];
  const descriptors = new Map(keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  const canvases = [];
  const workers = [];
  class FakeWorker {
    constructor(url, options) { this.url = url; this.options = options; this.handlers = new Map(); this.messages = []; this.terminated = false; workers.push(this); }
    addEventListener(type, callback) { if (!this.handlers.has(type)) this.handlers.set(type, new Set()); this.handlers.get(type).add(callback); }
    removeEventListener(type, callback) { this.handlers.get(type)?.delete(callback); }
    postMessage(message) { this.messages.push(message); }
    terminate() { this.terminated = true; }
    emit(data) { for (const callback of this.handlers.get('message') || []) callback({ data }); }
    fail() { for (const callback of this.handlers.get('error') || []) callback({ message: 'private runtime diagnostic must not reach UI' }); }
  }
  class FakeImage {
    constructor() { this.naturalWidth = width; this.naturalHeight = height; }
    set src(value) { if (value) queueMicrotask(() => this.onload?.()); }
  }
  const values = {
    navigator: gpu ? { gpu: { requestAdapter: async () => ({ features: new Set() }) } } : {},
    Worker: FakeWorker,
    Image: FakeImage,
    isSecureContext: true,
    document: { createElement(name) {
      assert.equal(name, 'canvas');
      const operations = [];
      const canvas = { width: 0, height: 0, operations,
        getContext() { return { set fillStyle(value) { operations.push(['color', value]); }, fillRect(...args) { operations.push(['fill', ...args]); }, drawImage(...args) { operations.push(['image', ...args]); } }; },
        toDataURL(type) { assert.equal(type, 'image/png'); return imageData; } };
      canvases.push(canvas); return canvas;
    } },
  };
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { configurable: true, value, writable: true });
  try { await callback({ workers, canvases }); }
  finally {
    disposeWorksheetReader();
    for (const key of keys) { if (descriptors.get(key)) Object.defineProperty(globalThis, key, descriptors.get(key)); else delete globalThis[key]; }
  }
}

async function posted(workers, index = 0) {
  for (let count = 0; count < 30; count += 1) {
    if (workers[index]?.messages[0]) return workers[index];
    await new Promise(setImmediate);
  }
  assert.fail('No reader request was posted to its worker.');
}

test('a valid arithmetic reading gets checked math and always needs adult review', () => {
  const result = parseModelReading(JSON.stringify(reading()));
  assert.equal(result.a, 5); assert.equal(result.b, 2); assert.equal(result.answer, 7);
  assert.equal(result.needs_review, true);
  assert.equal(result.object_name, 'popsicles');
  assert.equal(result.modelRevision, VISION_SETTINGS.revision);
});

test('zero quantities and the inclusive total limit are supported without coercion', () => {
  assert.equal(validateModelReading(reading({ a: 0, b: 10 })).answer, 10);
  for (const a of ['5', true, -1, 10.5, 11, Infinity, NaN, null]) assert.throws(() => validateModelReading(reading({ a })));
  assert.throws(() => validateModelReading(reading({ a: 8, b: 4 })));
});

test('compact learned suggestions preserve operation and operands, with mandatory review', () => {
  const addition = parseModelReading('ADD 4 3');
  assert.equal(addition.type, 'addition'); assert.equal(addition.a, 4); assert.equal(addition.b, 3); assert.equal(addition.answer, 7);
  assert.equal(addition.needs_review, true); assert.equal(addition.readingFormat, 'compact_candidate');
  assert.equal(Object.hasOwn(addition, 'uncertain'), false);
  const subtraction = parseCompactReading('sub 9 2');
  assert.equal(subtraction.type, 'subtraction'); assert.equal(subtraction.answer, 7);
  assert.equal(parseCompactReading('COUNT 0').answer, 0);
  assert.equal(parseCompactReading('NAME triangle').answer, 'triangle');
  assert.equal(parseCompactReading('SIDES rectangle').answer, 4);
});

test('compact grammar rejects prose, multiple suggestions, missing operands and unsupported math', () => {
  for (const raw of ['UNCLEAR', 'ADD 5', 'ADD five two', 'ADD 10 2', 'SUB 2 7', 'ADD -1 2', 'COUNT 11', 'NAME star',
    'ADD 1 2\nADD 3 4', 'The answer is ADD 2 3', 'ADD 1 2 = 3', 'ADD 1 2.', 'COUNT 04', 'SIDES rectangle and square']) {
    assert.throws(() => parseModelReading(raw), undefined, raw);
  }
});

test('plain arithmetic equations preserve visible operands and check numeric answers', () => {
  const result = parseModelReading('4 + 3 = ?');
  assert.equal(result.type, 'addition'); assert.equal(result.a, 4); assert.equal(result.b, 3);
  assert.equal(result.answer, 7); assert.equal(result.needs_review, true);
  assert.equal(result.readingFormat, 'equation_candidate');
  assert.equal(parseModelReading('9 - 2 = 7').answer, 7);
  assert.equal(parseModelReading('9 \u2212 2 = ?').answer, 7);
  assert.equal(parseModelReading('0+10').answer, 10);
});

test('equation parsing rejects unknown operands, inconsistent answers and multiple expressions', () => {
  for (const raw of ['4+3=8', '4+?=7', '?+3=7', '3-7=?', '9+2=?', '12+1=?', '4+3=7.', '4+3=7\n9-2=7', '4+3=7+0', 'The equation is 4+3=?', '4*2=8']) {
    assert.throws(() => parseModelReading(raw), undefined, raw);
  }
});

test('multiple questions, uncertain readings and missing operands cannot be rendered as established math', () => {
  for (const extra of [{ exercise_count: 2 }, { exercise_count: 0 }, { uncertain: true }, { uncertain: 'false' }, { unknown_operand: true }, { status: 'unclear' }, { status: 'unsupported' }]) {
    assert.throws(() => validateModelReading(reading(extra)));
  }
  const missing = reading(); delete missing.exercise_count;
  assert.throws(() => validateModelReading(missing));
});

test('the parser rejects duplicate keys, injected prose, multiple JSON values and nested instructions', () => {
  const json = JSON.stringify(reading());
  for (const raw of ['', 'null', '[]', 'NaN', '{}', `The answer is ${json}`, `${json} ${json}`,
    json.replace('"a":5', '"a":5,"a":8'), json.replace('"a":5', '"a":{"run":"script"}'), json.replace('"a":5', '"a":NaN')]) {
    assert.throws(() => parseModelReading(raw));
  }
  assert.equal(parseModelReading(`\n\u0060\u0060\u0060json\n${json}\n\u0060\u0060\u0060\n`).answer, 7);
});

test('unknown model fields and instruction-like object names are never accepted', () => {
  for (const extra of [{ instructions: 'open a website' }, { answer: 7 }, { object_name: '<img src=x>' }, { object_name: '../secret' }]) assert.throws(() => validateModelReading(reading(extra)));
  assert.equal(validateModelReading(reading({ object_name: 'ICE CREAM' })).object_name, 'ice cream');
});

test('subtraction is checked and inconsistent printed answers are rejected', () => {
  assert.equal(validateModelReading(reading({ type: 'subtraction', a: 7, b: 2 })).answer, 5);
  assert.throws(() => validateModelReading(reading({ type: 'subtraction', a: 2, b: 7 })));
  assert.throws(() => validateModelReading(reading({ printed_answer: 8 })));
  assert.equal(validateModelReading(reading({ printed_answer: 7 })).answer, 7);
});

test('counting and shapes retain their actual requested task', () => {
  const count = validateModelReading(reading({ type: 'counting', a: null, b: null, count: 4 }));
  assert.equal(count.count, 4); assert.equal(count.answer, 4);
  const shape = reading({ type: 'shape', a: null, b: null, shape: 'rectangle', shape_task: 'sides' });
  assert.equal(validateModelReading(shape).answer, 4);
  assert.equal(validateModelReading({ ...shape, shape_task: 'name' }).answer, 'rectangle');
  assert.throws(() => validateModelReading({ ...shape, shape_task: null }));
  assert.throws(() => validateModelReading({ ...shape, shape: 'hexagon' }));
  assert.throws(() => validateModelReading(reading({ type: 'multiplication' })));
  assert.throws(() => validateModelReading(reading({ count: 7 })));
});

test('remote URLs and executable image formats never reach image or model fetching', () => {
  assert.equal(validateImageDataURL(imageData), imageData);
  for (const raw of ['https://example.com/photo.png', 'file:///tmp/a.png', 'data:image/svg+xml;base64,AAAA', 'data:text/html;base64,AAAA', 'data:image/png;base64,']) assert.throws(() => validateImageDataURL(raw));
});

test('feature checks do not create workers or download any model', async () => {
  await browserFixture(async ({ workers }) => {
    const status = await browserReaderStatus();
    assert.equal(status.supported, true);
    assert.match(status.downloadLabel, /264 MB/);
    assert.equal(workers.length, 0);
  });
  await browserFixture(async ({ workers }) => {
    const status = await browserReaderStatus();
    assert.equal(status.supported, false); assert.match(status.reason, /enter/i);
    await assert.rejects(readWorksheet(imageData), { code: 'UNSUPPORTED' });
    assert.equal(workers.length, 0);
  }, { gpu: false });
});

test('images are white-flattened and resized before entering the worker', async () => {
  await browserFixture(async ({ canvases }) => {
    await normalizeWorksheetImage(imageData);
    assert.equal(canvases[0].width, 1024); assert.equal(canvases[0].height, 512);
    assert.deepEqual(canvases[0].operations[0], ['color', '#ffffff']);
    assert.equal(canvases[0].operations[1][0], 'fill');
    assert.equal(canvases[0].operations[2][0], 'image');
  });
  await browserFixture(async () => { await assert.rejects(normalizeWorksheetImage(imageData), { code: 'INVALID_IMAGE' }); }, { width: 10000, height: 10000 });
});

test('only one inference runs and unrelated worker messages cannot supply its result', async () => {
  await browserFixture(async ({ workers }) => {
    const first = readWorksheet(imageData);
    await assert.rejects(readWorksheet(imageData), { code: 'BUSY' });
    const worker = await posted(workers);
    const { id } = worker.messages[0];
    worker.emit({ type: 'result', id: 'a-different-request', raw: JSON.stringify(reading({ a: 1 })) });
    worker.emit({ type: 'result', id, raw: JSON.stringify(reading()) });
    assert.equal((await first).answer, 7);
    assert.equal(workers.length, 1);
  });
});

test('cancellation terminates the active worker and a later worksheet starts cleanly', async () => {
  await browserFixture(async ({ workers }) => {
    const controller = new AbortController();
    const first = readWorksheet(imageData, { signal: controller.signal });
    const cancelled = assert.rejects(first, { name: 'AbortError' });
    const worker = await posted(workers);
    controller.abort();
    await cancelled; assert.equal(worker.terminated, true);
    const second = readWorksheet(imageData);
    const next = await posted(workers, 1);
    next.emit({ type: 'result', id: next.messages[0].id, raw: JSON.stringify(reading({ a: 3, b: 1 })) });
    assert.equal((await second).answer, 4);
  });
});

test('a malformed model response never produces an inferred default answer', async () => {
  await browserFixture(async ({ workers }) => {
    const pending = readWorksheet(imageData);
    const rejected = assert.rejects(pending, { code: 'UNCLEAR' });
    const worker = await posted(workers);
    worker.emit({ type: 'result', id: worker.messages[0].id, raw: 'There are probably seven.' });
    await rejected;
  });
});

test('runtime failures are sanitized and discard the failed worker', async () => {
  await browserFixture(async ({ workers }) => {
    const pending = readWorksheet(imageData);
    const rejected = assert.rejects(pending, (error) => error.code === 'UNAVAILABLE' && !error.message.includes('private runtime'));
    const worker = await posted(workers); worker.fail();
    await rejected; assert.equal(worker.terminated, true);
  });
});

test('download progress is bounded and untrusted progress text is not displayed', async () => {
  await browserFixture(async ({ workers }) => {
    const events = [];
    const pending = readWorksheet(imageData, { onProgress: (event) => events.push(event) });
    const worker = await posted(workers); const { id } = worker.messages[0];
    worker.emit({ type: 'progress', id, stage: 'loading', progress: 1000, message: '<script>private</script>' });
    worker.emit({ type: 'result', id, raw: JSON.stringify(reading()) });
    await pending;
    assert.equal(events.at(-1).progress, 100);
    assert.equal(JSON.stringify(events).includes('<script>'), false);
  });
});
