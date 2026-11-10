const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function studio(width = 12, height = 10) {
  const elements = new Map();
  const handlers = new Map();
  let pixels = new Uint8ClampedArray(width * height * 4).fill(255);
  let version = 0;
  const strokes = [];
  const context = {
    save() {}, restore() {}, setTransform() {}, beginPath() {}, moveTo() {}, rect() {}, ellipse() {}, arc() {}, lineTo() {},
    stroke() { version += 1; strokes.push([this.strokeStyle, this.lineWidth]); },
    fill() { version += 1; }, fillRect() { pixels.fill(255); version += 1; },
    getImageData() { return { data: pixels.slice(), width, height }; },
    putImageData(image) { pixels = image.data.slice(); version += 1; },
  };
  function element(id = '') {
    if (elements.has(id)) return elements.get(id);
    const item = {
      id, isConnected: true, open: false, value: id === 'brush-size' ? '10' : '', checked: false, hidden: false,
      children: [], style: { setProperty() {} }, dataset: {},
      classList: { toggle() {} }, setAttribute() {}, removeAttribute() {},
      append(...children) { this.children.push(...children); }, replaceChildren(...children) { this.children = children; },
      addEventListener(name, callback) { handlers.set(`${id}:${name}`, callback); },
      removeEventListener(name, callback) { if (handlers.get(`${id}:${name}`) === callback) handlers.delete(`${id}:${name}`); },
      showModal() { this.open = true; },
      close() { this.open = false; const callback = handlers.get(`${id}:close`); if (callback) callback(); },
      focus() { document.activeElement = this; },
      getContext() { return context; }, width, height,
      getBoundingClientRect() { return { left: 0, top: 0, width, height }; },
      setPointerCapture(pointerId) { this.pointerId = pointerId; },
      hasPointerCapture(pointerId) { return this.pointerId === pointerId; },
      releasePointerCapture() { this.pointerId = null; },
      toDataURL() { return `data:image/png;base64,${version}`; },
    };
    elements.set(id, item);
    return item;
  }
  const document = {
    getElementById: element, createElement: () => element(Symbol()), createTextNode: (text) => text,
    addEventListener(name, callback) { handlers.set(`document:${name}`, callback); },
  };
  const sandbox = {
    document, console, Uint8Array, Uint32Array, Uint8ClampedArray, URL, AbortController,
    setTimeout() { return 1; }, clearTimeout() {},
    window: { location: { origin: 'http://127.0.0.1:8601' }, addEventListener() {} },
    localStorage: { setItem() {}, getItem() { return null; } },
  };
  const source = fs.readFileSync(path.join(__dirname, '../character_studio/static/studio.js'), 'utf8')
    .replace('  init();\n})();', '  globalThis.testing = {state, floodFill, startStroke, moveStroke, endStroke, pushHistory, setTool, setMirror, connectEvents, lessonUrl, confirmAction};\n})();');
  vm.runInNewContext(source, sandbox);
  return { ...sandbox.testing, elements, handlers, context, strokes, document, element,
    pixels: () => pixels,
    setPixels(data) { pixels = new Uint8ClampedArray(data); },
  };
}

function pointer(x, y, pointerId = 1, type = 'pointerdown') {
  return { clientX: x, clientY: y, pointerId, pointerType: 'mouse', button: 0, type, preventDefault() {} };
}

test('fill stays within closed borders and a second matching fill is a no-op', () => {
  const app = studio(7, 7);
  const pixels = app.pixels().slice();
  for (let y = 1; y < 6; y += 1) for (let x = 1; x < 6; x += 1) {
    if (x === 1 || x === 5 || y === 1 || y === 5) {
      const index = (y * 7 + x) * 4;
      pixels.set([0, 0, 0, 255], index);
    }
  }
  app.setPixels(pixels);
  app.state.ink = '#E77676';
  assert.equal(app.floodFill({ x: 3, y: 3 }), true);
  assert.deepEqual(Array.from(app.pixels().slice((3 * 7 + 3) * 4, (3 * 7 + 3) * 4 + 4)), [231, 118, 118, 255]);
  assert.deepEqual(Array.from(app.pixels().slice(0, 4)), [255, 255, 255, 255]);
  assert.equal(app.floodFill({ x: 3, y: 3 }), false);
});

test('full-size fill is iterative and covers all 604800 pixels', () => {
  const app = studio(720, 840);
  app.state.ink = '#363249';
  assert.equal(app.floodFill({ x: 719, y: 839 }), true);
  const pixels = app.pixels();
  assert.deepEqual(Array.from(pixels.slice(0, 4)), [54, 50, 73, 255]);
  assert.deepEqual(Array.from(pixels.slice(-4)), [54, 50, 73, 255]);
});

test('one shape gesture with many previews commits exactly one history entry', () => {
  const app = studio();
  app.pushHistory();
  app.setTool('rectangle');
  app.startStroke(pointer(1, 1));
  for (let i = 2; i < 10; i += 1) app.moveStroke(pointer(i, i, 1, 'pointermove'));
  assert.equal(app.state.history.length, 1);
  app.endStroke(pointer(9, 9, 1, 'pointerup'));
  assert.equal(app.state.history.length, 2);
  assert.equal(app.state.hasDrawing, true);
});

test('second touch is ignored and a cancelled gesture restores the previous pixels', () => {
  const app = studio();
  app.pushHistory();
  const original = Array.from(app.pixels());
  app.setTool('fill');
  app.startStroke(pointer(2, 2));
  assert.equal(app.state.pointerId, 1);
  app.startStroke(pointer(5, 5, 2));
  app.endStroke(pointer(5, 5, 2, 'pointerup'));
  assert.equal(app.state.drawing, true);
  app.endStroke(pointer(2, 2, 1, 'pointercancel'));
  assert.deepEqual(Array.from(app.pixels()), original);
  assert.equal(app.state.history.length, 1);
  assert.equal(app.state.hasDrawing, false);
});

test('mirrored brush paints a pair while history remains bounded', () => {
  const app = studio();
  app.setMirror(true);
  app.startStroke(pointer(1, 2));
  assert.equal(app.strokes.length, 0); // A stationary brush paints two filled dots.
  app.moveStroke(pointer(4, 5, 1, 'pointermove'));
  assert.equal(app.strokes.length, 2);
  app.endStroke(pointer(4, 5, 1, 'pointerup'));
  for (let index = 0; index < 40; index += 1) {
    app.context.stroke();
    app.pushHistory();
  }
  assert.equal(app.state.history.length, 24);
  assert.equal(app.state.historyIndex, 23);
});

test('keyboard undo leaves text editing shortcuts alone', () => {
  const app = studio();
  app.connectEvents();
  let prevented = false;
  const callback = app.handlers.get('document:keydown');
  callback({ ctrlKey: true, key: 'z', target: { closest: () => ({ tagName: 'INPUT' }) }, preventDefault() { prevented = true; } });
  assert.equal(prevented, false);
  callback({ ctrlKey: true, key: 'z', target: { closest: () => null }, preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
});

test('lesson handoff encodes a public character ID and rejects invalid IDs', () => {
  const app = studio();
  assert.equal(app.lessonUrl('abc-123'), 'http://127.0.0.1:8501/?character=abc-123');
  assert.throws(() => app.lessonUrl('../private'));
});


test('in-page confirmation starts with Cancel and restores focus after Continue', async () => {
  const app = studio();
  const trigger = app.element('edit-character-copy');
  trigger.focus();
  const decision = app.confirmAction('Keep the original safe?', { title: 'Open a copy?', confirmLabel: 'Open the copy' });
  assert.equal(app.element('confirm-action-dialog').open, true);
  assert.equal(app.document.activeElement.id, 'confirm-action-cancel');
  assert.equal(app.element('confirm-action-title').textContent, 'Open a copy?');
  assert.equal(app.element('confirm-action-continue').textContent, 'Open the copy');
  app.handlers.get('confirm-action-continue:click')();
  assert.equal(await decision, true);
  assert.equal(app.element('confirm-action-dialog').open, false);
  assert.equal(app.document.activeElement, trigger);
});

test('Escape cancels in-page confirmation and duplicate decisions cannot open over it', async () => {
  const app = studio();
  const decision = app.confirmAction('Replace this drawing?');
  assert.equal(await app.confirmAction('A second request'), false);
  let prevented = false;
  app.handlers.get('confirm-action-dialog:cancel')({ preventDefault() { prevented = true; } });
  assert.equal(await decision, false);
  assert.equal(prevented, true);
  assert.equal(app.element('confirm-action-dialog').open, false);
});

test('cancelling Clear preserves the drawing and continuing makes one undo entry', async () => {
  const app = studio();
  app.connectEvents();
  app.state.hasDrawing = true;
  app.pushHistory();
  const clear = app.handlers.get('clear-drawing:click');
  const cancelled = clear();
  app.handlers.get('confirm-action-cancel:click')();
  await cancelled;
  assert.equal(app.state.hasDrawing, true);
  assert.equal(app.state.history.length, 1);
  const accepted = clear();
  app.handlers.get('confirm-action-continue:click')();
  await accepted;
  assert.equal(app.state.hasDrawing, false);
  assert.equal(app.state.history.length, 2);
});

test('drawing shortcuts do not change the canvas while a confirmation is open', async () => {
  const app = studio();
  app.connectEvents();
  const decision = app.confirmAction('Continue?');
  let prevented = false;
  app.handlers.get('document:keydown')({ ctrlKey: true, key: 'z', target: { closest: () => null }, preventDefault() { prevented = true; } });
  assert.equal(prevented, false);
  app.handlers.get('confirm-action-cancel:click')();
  assert.equal(await decision, false);
});
