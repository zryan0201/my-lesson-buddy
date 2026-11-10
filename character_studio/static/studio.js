/* Character Studio uses only local browser tools and the local Flask API. */
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const canvas = $("drawing-canvas");
  const context = canvas.getContext("2d", { willReadFrequently: true });
  const DRAFT_KEY = "lesson-buddy-character-studio-v1";
  const MAX_DRAFT_IMAGE = 2400000;
  const MAX_HISTORY = 24;
  const COLORS = ["#363249", "#E77676", "#E9B45C", "#6DAB87", "#6AA3C4", "#9A82BB"];
  const FIELD_LABELS = {
    body_type: ["Body", "◉"], head_shape: ["Face shape", "◯"],
    eyes: ["Eyes", "◌"], headwear: ["Head & mask", "♧"],
    chest: ["Chest symbol", "✦"], back: ["Cape & wings", "⋈"],
    gloves: ["Hands & gloves", "◒"], boots: ["Boots", "⌑"],
  };
  const COLOR_LABELS = {
    primary_color: "Main color", secondary_color: "Second color",
    accent_color: "Little details", skin_color: "Face color",
  };
  const state = {
    mode: "draw", catalog: null, design: null, ink: COLORS[0], tool: "pen", mirror: false, dirty: false,
    drawing: false, pointerId: null, hasDrawing: false, history: [], historyIndex: -1,
    revision: 0, saving: false, polishing: false, loadingImage: false,
    previewUrl: null, previewSequence: 0, presetUrls: [],
    polishOriginal: null, polishResult: null, library: [], selectedId: null,
    aiEnabled: false, beautifying: false, polishRevision: null, importing: false, libraryBusy: false,
    motionUrl: null, motionSequence: 0,
  };
  let draftTimer;
  let previewTimer;
  let toastTimer;
  let lastPoint = null;
  let gesture = null;
  let pendingConfirmation = null;
  const DRAW_TOOLS = ["pen", "eraser", "line", "rectangle", "circle", "fill"];

  function notify(message, error = false) {
    const toast = $("toast");
    toast.textContent = message;
    toast.classList.toggle("error", error);
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, error ? 6500 : 4000);
  }

  function confirmAction(message, { title = "Ready to try something new?", confirmLabel = "Continue" } = {}) {
    // Keep decisions in the page so touch, keyboard, and assistive tools all use
    // the same visible controls. Cancel is the initial and Escape choice.
    if (pendingConfirmation) return Promise.resolve(false);
    const dialog = $("confirm-action-dialog");
    const cancel = $("confirm-action-cancel");
    const accept = $("confirm-action-continue");
    const previousFocus = document.activeElement;
    $("confirm-action-title").textContent = title;
    $("confirm-action-message").textContent = message;
    accept.textContent = confirmLabel;
    return new Promise((resolve) => {
      let settled = false;
      const finish = (confirmed) => {
        if (settled) return;
        settled = true;
        cancel.removeEventListener("click", onCancelButton);
        accept.removeEventListener("click", onContinue);
        dialog.removeEventListener("cancel", onEscape);
        dialog.removeEventListener("close", onClose);
        pendingConfirmation = null;
        if (dialog.open) dialog.close();
        if (previousFocus?.isConnected && typeof previousFocus.focus === "function") previousFocus.focus({ preventScroll: true });
        resolve(Boolean(confirmed));
      };
      const onCancelButton = () => finish(false);
      const onContinue = () => finish(true);
      const onEscape = (event) => { event.preventDefault(); finish(false); };
      const onClose = () => finish(false);
      pendingConfirmation = { cancel: onCancelButton };
      cancel.addEventListener("click", onCancelButton);
      accept.addEventListener("click", onContinue);
      dialog.addEventListener("cancel", onEscape);
      dialog.addEventListener("close", onClose);
      try {
        dialog.showModal();
        cancel.focus({ preventScroll: true });
      } catch (_) { finish(false); }
    });
  }

  function setStatus(message = "") { $("global-status").textContent = message; }

  async function api(path, options = {}, timeoutMs = 30000) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(path, {
        ...options, signal: controller.signal, credentials: "same-origin",
        redirect: "error", cache: "no-store",
      });
      if (!response.ok) {
        let message = "We could not finish that step. Please try again.";
        try {
          const body = await response.json();
          if (typeof body.error === "string") message = body.error;
          else if (typeof body.message === "string") message = body.message;
        } catch (_) { /* Keep the friendly fallback for non-JSON errors. */ }
        throw new Error(message);
      }
      return response;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("That step took a little too long. Please try again.");
      if (error instanceof TypeError) throw new Error("The local studio is not responding. Keep its terminal open and try again.");
      throw error;
    } finally { clearTimeout(timeout); }
  }

  function assetUrl(url) {
    const resolved = new URL(url, window.location.origin);
    if (resolved.origin !== window.location.origin || !resolved.pathname.startsWith("/api/characters/")) {
      throw new Error("The studio returned an unexpected character link.");
    }
    return resolved.href;
  }

  function characterName() { return $("character-name").value.trim(); }

  function updateName() {
    const name = characterName();
    $("preview-name").textContent = name || "my friend";
    $("name-counter").textContent = `${Array.from($("character-name").value).length} / ${state.catalog?.name_max_length || 32}`;
    if (state.design) state.design.name = name || "My Buddy";
    refreshSaveButton();
  }

  function refreshSaveButton() {
    const ready = state.mode === "build" ? Boolean(state.design && state.catalog) : state.hasDrawing;
    $("save-character").disabled = !ready || !characterName() || state.saving || state.loadingImage;
    $("polish-drawing").disabled = !state.hasDrawing || state.polishing || state.beautifying || state.loadingImage;
    $("beautify-drawing").disabled = !state.aiEnabled || !state.hasDrawing || state.beautifying || state.polishing || state.loadingImage || !$("ai-consent").checked;
    if (state.hasDrawing) {
      $("manual-download-drawing").href = canvas.toDataURL("image/png");
      $("manual-download-drawing").setAttribute("aria-disabled", "false");
    } else {
      $("manual-download-drawing").removeAttribute("href");
      $("manual-download-drawing").setAttribute("aria-disabled", "true");
    }
    $("save-help").textContent = state.saving ? "Saving a new character to your collection…" :
      !characterName() ? "Add a name and create your character to save it." :
      !ready ? "Make a few marks and bring your character to life." :
      "Save a new character. Your earlier characters stay safe.";
  }

  function edited({ preview = true } = {}) {
    state.revision += 1;
    state.dirty = true;
    $("saved-result").hidden = true;
    if (preview) updatePreview();
    refreshSaveButton();
    scheduleDraft();
  }

  function switchMode(mode, { persist = true } = {}) {
    state.mode = mode;
    for (const candidate of ["draw", "build"]) {
      const active = candidate === mode;
      $(`tab-${candidate}`).setAttribute("aria-selected", String(active));
      $(`tab-${candidate}`).tabIndex = active ? 0 : -1;
      $(`panel-${candidate}`).hidden = !active;
    }
    $("saved-result").hidden = true;
    updatePreview();
    refreshSaveButton();
    if (persist) scheduleDraft();
  }

  function scheduleDraft() {
    clearTimeout(draftTimer);
    draftTimer = setTimeout(saveDraft, 350);
  }

  function saveDraft() {
    try {
      const image = state.hasDrawing ? canvas.toDataURL("image/png") : null;
      if (image && image.length > MAX_DRAFT_IMAGE) {
        $("draft-status").textContent = "Save this character to keep a large drawing";
        return;
      }
      localStorage.setItem(DRAFT_KEY, JSON.stringify({
        version: 1, mode: state.mode, name: $("character-name").value,
        design: state.design, image, ink: state.ink, original: state.polishOriginal, mirror: state.mirror,
      }));
      $("draft-status").replaceChildren();
      const dot = document.createElement("span");
      dot.className = "status-dot";
      dot.setAttribute("aria-hidden", "true");
      $("draft-status").append(dot, document.createTextNode("Draft saved on this device"));
    } catch (_) {
      $("draft-status").textContent = "Use Save my character to keep your work";
    }
  }

  function getDraft() {
    try {
      const text = localStorage.getItem(DRAFT_KEY);
      if (!text || text.length > MAX_DRAFT_IMAGE * 2 + 12000) return null;
      const draft = JSON.parse(text);
      return draft && draft.version === 1 ? draft : null;
    } catch (_) { return null; }
  }

  function fillWhite() {
    context.save();
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.fillStyle = "#FFFFFF";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.restore();
  }

  function pushHistory() {
    const image = canvas.toDataURL("image/png");
    if (state.history[state.historyIndex]?.image === image) return;
    state.history.splice(state.historyIndex + 1);
    state.history.push({ image, hasDrawing: state.hasDrawing });
    if (state.history.length > MAX_HISTORY) state.history.shift();
    state.historyIndex = state.history.length - 1;
    updateHistoryTools();
  }

  function updateHistoryTools() {
    $("undo-drawing").disabled = state.historyIndex <= 0 || state.loadingImage;
    $("redo-drawing").disabled = state.historyIndex >= state.history.length - 1 || state.loadingImage;
    $("canvas-hint").hidden = state.hasDrawing;
  }

  function loadImage(source, { fit = false } = {}) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => {
        fillWhite();
        if (fit) {
          const margin = 25;
          const scale = Math.min((canvas.width - margin * 2) / image.width, (canvas.height - margin * 2) / image.height);
          const width = image.width * scale;
          const height = image.height * scale;
          context.drawImage(image, (canvas.width - width) / 2, (canvas.height - height) / 2, width, height);
        } else { context.drawImage(image, 0, 0, canvas.width, canvas.height); }
        resolve();
      };
      image.onerror = () => reject(new Error("We could not open that drawing. Try a PNG or JPEG picture."));
      image.src = source;
    });
  }

  async function moveHistory(offset) {
    if (state.loadingImage || state.drawing) return;
    const index = state.historyIndex + offset;
    if (index < 0 || index >= state.history.length) return;
    state.loadingImage = true;
    refreshSaveButton();
    updateHistoryTools();
    try {
      const entry = state.history[index];
      await loadImage(entry.image);
      state.historyIndex = index;
      state.hasDrawing = entry.hasDrawing;
      edited();
    } catch (error) { notify(error.message, true); }
    finally {
      state.loadingImage = false;
      updateHistoryTools();
      refreshSaveButton();
    }
  }

  function point(event) {
    const bounds = canvas.getBoundingClientRect();
    return { x: Math.max(0, Math.min(canvas.width - 1, (event.clientX - bounds.left) * canvas.width / bounds.width)),
      y: Math.max(0, Math.min(canvas.height - 1, (event.clientY - bounds.top) * canvas.height / bounds.height)) };
  }

  function paintStroke(from, to) {
    context.save();
    context.strokeStyle = state.tool === "eraser" ? "#FFFFFF" : state.ink;
    context.fillStyle = context.strokeStyle;
    context.lineWidth = Number($("brush-size").value) * (state.tool === "eraser" ? 2.2 : 1);
    context.lineCap = "round";
    context.lineJoin = "round";
    context.beginPath();
    if (from.x === to.x && from.y === to.y) {
      context.arc(to.x, to.y, context.lineWidth / 2, 0, Math.PI * 2);
      context.fill();
    } else {
      context.moveTo(from.x, from.y);
      context.lineTo(to.x, to.y);
      context.stroke();
    }
    context.restore();
  }

  function mirrored(pointValue) { return { x: canvas.width - 1 - pointValue.x, y: pointValue.y }; }

  function stroke(from, to) {
    paintStroke(from, to);
    if (state.mirror) paintStroke(mirrored(from), mirrored(to));
  }

  function paintShape(from, to) {
    context.save();
    context.strokeStyle = state.ink;
    context.lineWidth = Number($("brush-size").value);
    context.lineCap = "round";
    context.lineJoin = "round";
    context.beginPath();
    if (state.tool === "line") {
      context.moveTo(from.x, from.y);
      context.lineTo(to.x, to.y);
    } else if (state.tool === "rectangle") {
      context.rect(Math.min(from.x, to.x), Math.min(from.y, to.y), Math.max(1, Math.abs(to.x - from.x)), Math.max(1, Math.abs(to.y - from.y)));
    } else {
      context.ellipse((from.x + to.x) / 2, (from.y + to.y) / 2, Math.max(.5, Math.abs(to.x - from.x) / 2), Math.max(.5, Math.abs(to.y - from.y) / 2), 0, 0, Math.PI * 2);
    }
    context.stroke();
    context.restore();
  }

  function previewShape(to) {
    context.putImageData(gesture.before, 0, 0);
    paintShape(gesture.start, to);
    if (state.mirror) paintShape(mirrored(gesture.start), mirrored(to));
  }

  // A bounded queue visits each canvas pixel at most once; it never recurses.
  function floodFill(at) {
    const image = context.getImageData(0, 0, canvas.width, canvas.height);
    const pixels = image.data;
    const width = image.width;
    const height = image.height;
    const start = Math.floor(at.y) * width + Math.floor(at.x);
    const source = Array.from(pixels.slice(start * 4, start * 4 + 4));
    const color = state.ink.match(/[0-9a-f]{2}/gi).map((value) => parseInt(value, 16)).concat(255);
    const tolerance = 24;
    if (source.every((value, index) => Math.abs(value - color[index]) <= tolerance)) return false;
    const seen = new Uint8Array(width * height);
    const queue = new Uint32Array(width * height);
    let tail = 1;
    queue[0] = start;
    seen[start] = 1;
    const enqueue = (pixel) => {
      if (seen[pixel]) return;
      seen[pixel] = 1;
      const index = pixel * 4;
      if (source.every((value, channel) => Math.abs(value - pixels[index + channel]) <= tolerance)) queue[tail++] = pixel;
    };
    for (let head = 0; head < tail; head += 1) {
      const pixel = queue[head];
      const index = pixel * 4;
      for (let channel = 0; channel < 4; channel += 1) pixels[index + channel] = color[channel];
      const x = pixel % width;
      const y = Math.floor(pixel / width);
      if (x > 0) enqueue(pixel - 1);
      if (x + 1 < width) enqueue(pixel + 1);
      if (y > 0) enqueue(pixel - width);
      if (y + 1 < height) enqueue(pixel + width);
    }
    context.putImageData(image, 0, 0);
    return true;
  }

  function startStroke(event) {
    if (state.loadingImage || state.drawing || (event.pointerType === "mouse" && event.button !== 0)) return;
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    state.drawing = true;
    state.pointerId = event.pointerId;
    lastPoint = point(event);
    gesture = { before: context.getImageData(0, 0, canvas.width, canvas.height), start: lastPoint, hadDrawing: state.hasDrawing, changed: true };
    if (state.tool === "fill") {
      gesture.changed = floodFill(lastPoint);
      if (state.mirror) gesture.changed = floodFill(mirrored(lastPoint)) || gesture.changed;
    } else if (["pen", "eraser"].includes(state.tool)) stroke(lastPoint, lastPoint);
    else previewShape(lastPoint);
    $("canvas-hint").hidden = true;
  }

  function moveStroke(event) {
    if (!state.drawing || event.pointerId !== state.pointerId || state.tool === "fill") return;
    event.preventDefault();
    if (["line", "rectangle", "circle"].includes(state.tool)) {
      lastPoint = point(event);
      previewShape(lastPoint);
      return;
    }
    const events = typeof event.getCoalescedEvents === "function" ? event.getCoalescedEvents() : [event];
    for (const item of events.length ? events : [event]) {
      const next = point(item);
      stroke(lastPoint, next);
      lastPoint = next;
    }
  }

  function endStroke(event) {
    if (!state.drawing || (event && event.pointerId !== state.pointerId)) return;
    const pointerId = state.pointerId;
    const cancelled = event?.type === "pointercancel";
    if (event?.type === "pointerup" && ["line", "rectangle", "circle"].includes(state.tool)) previewShape(point(event));
    state.drawing = false;
    state.pointerId = null;
    if (canvas.hasPointerCapture(pointerId)) canvas.releasePointerCapture(pointerId);
    if (cancelled) context.putImageData(gesture.before, 0, 0);
    else if (gesture.changed) {
      state.hasDrawing = true;
      pushHistory();
      edited();
    }
    lastPoint = null;
    gesture = null;
    updateHistoryTools();
  }

  function setTool(tool) {
    if (state.drawing || !DRAW_TOOLS.includes(tool)) return;
    state.tool = tool;
    for (const candidate of DRAW_TOOLS) {
      $(`tool-${candidate}`).classList.toggle("is-active", tool === candidate);
      $(`tool-${candidate}`).setAttribute("aria-pressed", String(tool === candidate));
    }
    $("drawing-tool-help").textContent = {
      pen: "Draw with your finger, mouse, or stylus.", eraser: "Rub over marks to erase them.",
      line: "Drag to draw a straight line.", rectangle: "Drag from one corner to the other.",
      circle: "Drag to make a circle or oval.", fill: "Tap inside a closed shape to color it.",
    }[tool];
  }

  function setMirror(enabled) {
    if (state.drawing) return;
    state.mirror = Boolean(enabled);
    $("mirror-drawing").classList.toggle("is-active", state.mirror);
    $("mirror-drawing").setAttribute("aria-pressed", String(state.mirror));
    $("mirror-guide").hidden = !state.mirror;
    scheduleDraft();
  }

  function setInk(color) {
    state.ink = color;
    $("ink-color").value = color;
    if (state.tool === "eraser") setTool("pen");
    for (const button of $("ink-palette").children) {
      const active = button.dataset.color.toUpperCase() === color.toUpperCase();
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    }
    scheduleDraft();
  }

  function makePalette() {
    COLORS.forEach((color, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "color-swatch";
      button.style.setProperty("--swatch", color);
      button.dataset.color = color;
      button.setAttribute("aria-label", ["Charcoal", "Coral", "Golden yellow", "Leaf green", "Sky blue", "Lavender"][index]);
      button.addEventListener("click", () => setInk(color));
      $("ink-palette").append(button);
    });
    setInk(state.ink);
  }

  function applyDesign(design) {
    const merged = { ...state.catalog.defaults };
    for (const [key, options] of Object.entries(state.catalog.options)) {
      const values = options.map((option) => typeof option === "string" ? option : option.value);
      if (values.includes(design?.[key])) merged[key] = design[key];
    }
    for (const key of Object.keys(COLOR_LABELS)) {
      if (/^#[0-9a-f]{6}$/i.test(design?.[key] || "")) merged[key] = design[key];
    }
    merged.name = characterName() || "My Buddy";
    state.design = merged;
    for (const key of Object.keys(FIELD_LABELS)) if ($(`part-${key}`)) $(`part-${key}`).value = state.design[key];
    for (const key of Object.keys(COLOR_LABELS)) if ($(`color-${key}`)) $(`color-${key}`).value = state.design[key];
    updatePresetSelection();
  }

  function updatePresetSelection() {
    for (const button of $("preset-grid").children) {
      const preset = state.catalog.presets.find((item) => item.id === button.dataset.preset);
      const active = preset && Object.keys({ ...FIELD_LABELS, ...COLOR_LABELS }).every((key) => preset.design[key] === state.design[key]);
      button.classList.toggle("is-active", Boolean(active));
      button.setAttribute("aria-pressed", String(Boolean(active)));
    }
  }

  function createBuilderControls() {
    $("part-controls").replaceChildren();
    for (const [field, [label, icon]] of Object.entries(FIELD_LABELS)) {
      const options = state.catalog.options[field];
      if (!Array.isArray(options)) continue;
      const wrapper = document.createElement("div");
      wrapper.className = "part-field";
      const title = document.createElement("label");
      title.htmlFor = `part-${field}`;
      const symbol = document.createElement("span");
      symbol.setAttribute("aria-hidden", "true");
      symbol.textContent = icon;
      title.append(symbol, document.createTextNode(label));
      const select = document.createElement("select");
      select.id = `part-${field}`;
      options.forEach((option) => {
        const node = document.createElement("option");
        node.value = typeof option === "string" ? option : option.value;
        node.textContent = typeof option === "string" ? option : option.label;
        select.append(node);
      });
      select.value = state.design[field];
      select.addEventListener("change", () => {
        state.design[field] = select.value;
        updatePresetSelection();
        edited();
      });
      wrapper.append(title, select);
      $("part-controls").append(wrapper);
    }
    $("builder-colors").replaceChildren();
    for (const [field, label] of Object.entries(COLOR_LABELS)) {
      const wrapper = document.createElement("label");
      wrapper.className = "builder-color";
      const input = document.createElement("input");
      input.type = "color";
      input.id = `color-${field}`;
      input.value = state.design[field];
      input.setAttribute("aria-label", label);
      input.addEventListener("input", () => {
        state.design[field] = input.value;
        updatePresetSelection();
        edited();
      });
      const text = document.createElement("span");
      text.textContent = label;
      wrapper.append(input, text);
      $("builder-colors").append(wrapper);
    }
    $("preset-grid").replaceChildren();
    for (const preset of state.catalog.presets) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "preset-card";
      button.dataset.preset = preset.id;
      const image = document.createElement("img");
      image.alt = "";
      const label = document.createElement("span");
      label.textContent = preset.name;
      button.append(image, label);
      button.addEventListener("click", () => {
        applyDesign(preset.design);
        edited();
      });
      $("preset-grid").append(button);
      renderDesign(preset.design).then((url) => {
        state.presetUrls.push(url);
        image.src = url;
      }).catch(() => { image.alt = "Character preview unavailable"; });
    }
    updatePresetSelection();
  }

  async function renderDesign(design) {
    const response = await api("/api/preview", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(design),
    });
    return URL.createObjectURL(await response.blob());
  }

  function setPreview(source) {
    $("character-preview").src = source;
    $("character-preview").hidden = false;
    $("preview-empty").hidden = true;
  }

  function updatePreview() {
    clearTimeout(previewTimer);
    const sequence = ++state.previewSequence;
    $("preview-loading").hidden = true;
    if (state.mode === "draw") {
      if (state.hasDrawing) setPreview(canvas.toDataURL("image/png"));
      else { $("character-preview").hidden = true; $("preview-empty").hidden = false; }
      return;
    }
    if (!state.design) return;
    $("preview-loading").hidden = false;
    previewTimer = setTimeout(async () => {
      try {
        const url = await renderDesign({ ...state.design });
        if (sequence !== state.previewSequence || state.mode !== "build") { URL.revokeObjectURL(url); return; }
        if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
        state.previewUrl = url;
        setPreview(url);
      } catch (error) {
        if (sequence === state.previewSequence) notify(error.message, true);
      } finally {
        if (sequence === state.previewSequence) $("preview-loading").hidden = true;
      }
    }, 140);
  }

  async function importDrawing(file) {
    if (!file) return;
    if (!["image/png", "image/jpeg"].includes(file.type)) { notify("Choose a PNG or JPEG picture for your drawing.", true); return; }
    if (file.size > 8 * 1024 * 1024) { notify("That picture is a little large. Try one smaller than 8 MB.", true); return; }
    if (state.hasDrawing && !await confirmAction("Replace this drawing with your picture? You can use Undo to bring it back.", { title: "Bring in this drawing?", confirmLabel: "Replace drawing" })) return;
    const url = URL.createObjectURL(file);
    state.loadingImage = true;
    refreshSaveButton();
    try {
      await loadImage(url, { fit: true });
      state.hasDrawing = true;
      $("polish-comparison").hidden = true;
      pushHistory();
      edited();
      notify("Your picture is on the canvas. Add anything you imagine.");
    } catch (error) { notify(error.message, true); }
    finally { URL.revokeObjectURL(url); state.loadingImage = false; refreshSaveButton(); updateHistoryTools(); }
  }

  function canvasBlob() {
    return new Promise((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("We could not prepare your drawing. Please try again.")), "image/png"));
  }

  async function polishDrawing() {
    if (!state.hasDrawing || state.polishing) return;
    const original = canvas.toDataURL("image/png");
    const revision = state.revision;
    state.polishing = true;
    $("polish-drawing").textContent = "Cleaning gently…";
    refreshSaveButton();
    try {
      const form = new FormData();
      form.append("image", await canvasBlob(), "drawing.png");
      const response = await api("/api/polish", { method: "POST", body: form });
      const blob = await response.blob();
      const result = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("We could not prepare the polished preview."));
        reader.readAsDataURL(blob);
      });
      state.polishResult = result;
      state.polishRevision = revision;
      showComparison(original, result, false);
      notify("Compare both versions. Your original has not changed.");
    } catch (error) { notify(error.message, true); }
    finally { state.polishing = false; $("polish-drawing").textContent = "Preview polish ✦"; refreshSaveButton(); }
  }

  async function usePolished() {
    if (!state.polishResult) return;
    if (state.polishRevision !== state.revision && !await confirmAction("You have changed your drawing since this preview. Replace the canvas with this version? You can still Undo.", { title: "Use this new version?", confirmLabel: "Use this version" })) return;
    state.loadingImage = true;
    refreshSaveButton();
    try {
      await loadImage(state.polishResult, { fit: true });
      state.hasDrawing = true;
      pushHistory();
      edited();
      $("polish-comparison").hidden = true;
      notify("New version added. Your original is still available to download.");
    } catch (error) { notify(error.message, true); }
    finally { state.loadingImage = false; refreshSaveButton(); updateHistoryTools(); }
  }

  function showComparison(original, result, ai) {
    $("original-preview").src = original;
    $("polished-preview").src = result;
    $("polished-preview").alt = ai ? "Character illustration returned by Google Gemini" : "Drawing after local cleanup";
    $("polished-caption").textContent = ai ? "Gemini’s interpretation" : "Gently polished";
    $("use-polished").textContent = ai ? "Use this version" : "Use polished version";
    preserveOriginal(original);
    $("download-original").href = state.polishOriginal;
    $("polish-comparison").hidden = false;
    $("polish-comparison").scrollIntoView({ block: "nearest", behavior: "smooth" });
    scheduleDraft();
  }

  function preserveOriginal(original) {
    if (!state.polishOriginal) state.polishOriginal = original;
    $("download-drawing-backup").href = state.polishOriginal;
    $("drawing-backup").hidden = false;
  }

  async function refreshAiStatus() {
    try {
      const response = await api("/api/ai-status");
      const status = await response.json();
      state.aiEnabled = Boolean(status.enabled && status.key_configured && status.image_enabled);
      $("ai-enabled-controls").hidden = !state.aiEnabled;
      $("ai-unavailable").hidden = state.aiEnabled;
      $("ai-feature-tag").textContent = state.aiEnabled ? "Optional · grown-up choice" : "Optional · adult setup";
      $("ai-status-message").textContent = state.aiEnabled
        ? "Gemini can turn your sketch into an illustrated character. A grown-up chooses when to send it. Your original stays safe."
        : "Gemini can redraw your sketch. An adult must configure API access; student app subscriptions do not guarantee free API images.";
    } catch (_) { /* Optional AI must not prevent local drawing or building. */ }
    refreshSaveButton();
  }

  async function beautifyDrawing() {
    if ($("beautify-drawing").disabled || !$("ai-consent").checked) return;
    const original = canvas.toDataURL("image/png");
    const revision = state.revision;
    state.beautifying = true;
    $("beautify-drawing").textContent = "Gemini is imagining…";
    refreshSaveButton();
    try {
      const form = new FormData();
      form.append("image", await canvasBlob(), "my-drawing.png");
      form.append("style", $("ai-style").value);
      form.append("confirmed", "true");
      const response = await api("/api/beautify", { method: "POST", body: form }, 180000);
      const blob = await response.blob();
      const result = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("We could not open the AI illustration."));
        reader.readAsDataURL(blob);
      });
      state.polishResult = result;
      state.polishRevision = revision;
      showComparison(original, result, true);
      notify("Gemini’s version is ready to compare. You decide what to keep.");
    } catch (error) { notify(error.message, true); }
    finally {
      state.beautifying = false;
      $("ai-consent").checked = false;
      $("beautify-drawing").textContent = "Ask Gemini for a makeover ✦";
      refreshSaveButton();
    }
  }

  async function saveCharacter() {
    if ($("save-character").disabled || state.saving) return;
    const name = characterName();
    const source = state.mode === "build" ? "builder" : "drawing";
    const revision = state.revision;
    state.saving = true;
    $("save-character").textContent = "Saving your character…";
    refreshSaveButton();
    try {
      const form = new FormData();
      form.append("name", name);
      form.append("source", source);
      if (source === "builder") form.append("design", JSON.stringify({ ...state.design, name }));
      else form.append("image", await canvasBlob(), "my-character.png");
      const response = await api("/api/characters", { method: "POST", body: form });
      const character = await response.json();
      const imageUrl = assetUrl(character.urls.image);
      const packageUrl = assetUrl(character.urls.package);
      $("saved-use-lesson").href = lessonUrl(character.id);
      $("download-image").href = imageUrl;
      $("download-package").href = packageUrl;
      $("saved-result-title").textContent = `${character.name} is ready!`;
      $("saved-result").hidden = revision !== state.revision;
      state.selectedId = character.id;
      if (revision === state.revision) state.dirty = false;
      await refreshLibrary({ silent: true });
      notify(`${character.name} is saved. Your new buddy is ready for a lesson!`);
      saveDraft();
    } catch (error) { notify(error.message, true); }
    finally {
      state.saving = false;
      $("save-character").replaceChildren();
      const spark = document.createElement("span");
      spark.textContent = "✦";
      spark.setAttribute("aria-hidden", "true");
      $("save-character").append(spark, document.createTextNode(" Save my character"));
      refreshSaveButton();
    }
  }

  function lessonUrl(id) {
    if (!/^[a-zA-Z0-9_-]{1,100}$/.test(id)) throw new Error("This character could not be selected. Try refreshing your collection.");
    const url = new URL("http://127.0.0.1:8501/");
    url.searchParams.set("character", id);
    return url.href;
  }

  function currentCharacter() { return state.library.find((character) => character.id === state.selectedId); }

  function resetMotion() {
    state.motionSequence += 1;
    if (state.motionUrl) URL.revokeObjectURL(state.motionUrl);
    state.motionUrl = null;
    $("motion-status").textContent = "";
    $("preview-motion").disabled = false;
  }

  function showCharacter(character) {
    try {
      resetMotion();
      state.selectedId = character.id;
      renderLibrary();
      $("dialog-character-name").textContent = character.name;
      $("dialog-character-image").src = assetUrl(character.urls.image);
      $("dialog-character-image").alt = character.name;
      $("dialog-character-description").textContent = character.source === "builder" ? "An original character, built one little part at a time." : "A one-of-a-kind character, drawn with imagination.";
      $("dialog-download-image").href = assetUrl(character.urls.image);
      $("dialog-download-package").href = assetUrl(character.urls.package);
      $("dialog-use-lesson").href = lessonUrl(character.id);
      $("edit-character-copy").disabled = state.libraryBusy;
      $("duplicate-character").disabled = state.libraryBusy;
      if (!$("saved-character-dialog").open) $("saved-character-dialog").showModal();
    } catch (error) { notify(error.message, true); }
  }

  async function previewMotion() {
    const character = currentCharacter();
    if (!character || $("preview-motion").disabled) return;
    const sequence = ++state.motionSequence;
    $("preview-motion").disabled = true;
    $("motion-status").textContent = "Your buddy is getting ready…";
    try {
      const path = `/api/characters/${encodeURIComponent(character.id)}/motion?motion=${encodeURIComponent($("character-motion").value)}`;
      const response = await api(path, {}, 60000);
      const url = URL.createObjectURL(await response.blob());
      if (sequence !== state.motionSequence || !$("saved-character-dialog").open) { URL.revokeObjectURL(url); return; }
      if (state.motionUrl) URL.revokeObjectURL(state.motionUrl);
      state.motionUrl = url;
      $("dialog-character-image").src = url;
      $("motion-status").textContent = character.source === "builder" ? "Ready for a learning adventure!" : "Your drawing moves as a whole character. Its original lines stay yours.";
    } catch (error) { if (sequence === state.motionSequence) $("motion-status").textContent = error.message; }
    finally { if (sequence === state.motionSequence) $("preview-motion").disabled = false; }
  }

  async function importPackage(file) {
    if (!file || state.importing) return;
    if (!/\.zip$/i.test(file.name) || file.size > 8 * 1024 * 1024) {
      notify("Choose a Character Studio .character.zip package smaller than 8 MB.", true);
      return;
    }
    state.importing = true;
    $("package-upload").disabled = true;
    try {
      const form = new FormData();
      form.append("package", file, file.name);
      const response = await api("/api/import", { method: "POST", body: form });
      const character = await response.json();
      state.selectedId = character.id;
      $("library-search").value = "";
      await refreshLibrary({ silent: true });
      showCharacter(character);
      notify(`${character.name} has joined your collection. Your current draft is safe.`);
    } catch (error) { notify(error.message, true); }
    finally { state.importing = false; $("package-upload").disabled = false; }
  }

  async function duplicateCharacter() {
    const character = currentCharacter();
    if (!character || state.libraryBusy) return;
    state.libraryBusy = true;
    $("duplicate-character").disabled = true;
    $("edit-character-copy").disabled = true;
    try {
      const response = await api(`/api/characters/${encodeURIComponent(character.id)}/duplicate`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
      });
      const copy = await response.json();
      state.selectedId = copy.id;
      $("library-search").value = "";
      await refreshLibrary({ silent: true });
      showCharacter(copy);
      notify(`${copy.name} is saved as a new character. The first one stays safe.`);
    } catch (error) { notify(error.message, true); }
    finally {
      state.libraryBusy = false;
      $("duplicate-character").disabled = false;
      $("edit-character-copy").disabled = false;
    }
  }

  async function editCharacterCopy() {
    const character = currentCharacter();
    if (!character || state.libraryBusy) return;
    if (state.dirty && !await confirmAction("Open a copy to edit? Save your current draft first if you want it in your collection. Drawings can also be brought back with Undo.", { title: "Open a copy to edit?", confirmLabel: "Open the copy" })) return;
    state.libraryBusy = true;
    state.loadingImage = true;
    $("edit-character-copy").disabled = true;
    $("duplicate-character").disabled = true;
    refreshSaveButton();
    try {
      const response = await api(`/api/characters/${encodeURIComponent(character.id)}/project`);
      const project = await response.json();
      if (!project.character || project.character.id !== character.id) throw new Error("We could not open that character. Please refresh your collection.");
      if (project.design && state.catalog) {
        $("character-name").value = character.name;
        applyDesign(project.design);
        switchMode("build");
      } else {
        if (state.hasDrawing) preserveOriginal(canvas.toDataURL("image/png"));
        const imageResponse = await api(new URL(assetUrl(project.character.urls.image)).pathname);
        const imageUrl = URL.createObjectURL(await imageResponse.blob());
        try { await loadImage(imageUrl, { fit: true }); }
        finally { URL.revokeObjectURL(imageUrl); }
        state.hasDrawing = true;
        pushHistory();
        $("character-name").value = character.name;
        $("polish-comparison").hidden = true;
        switchMode("draw");
      }
      updateName();
      edited();
      $("saved-character-dialog").close();
      $("studio").scrollIntoView({ behavior: "smooth", block: "start" });
      notify(`You are editing a copy of ${character.name}. Save it to make a new character.`);
    } catch (error) { notify(error.message, true); }
    finally {
      state.libraryBusy = false;
      state.loadingImage = false;
      $("edit-character-copy").disabled = false;
      $("duplicate-character").disabled = false;
      refreshSaveButton();
      updateHistoryTools();
    }
  }

  function renderLibrary() {
    const library = $("character-library");
    const search = $("library-search").value.trim().toLocaleLowerCase();
    const characters = state.library.filter((character) => character.name.toLocaleLowerCase().includes(search));
    $("library-count").textContent = state.library.length ? `${characters.length} of ${state.library.length}` : "";
    library.replaceChildren();
    if (!characters.length) {
      const empty = document.createElement("div");
      empty.className = "library-empty";
      const title = document.createElement("h3");
      title.textContent = search ? "No buddies with that name yet." : "Your story starts here.";
      const detail = document.createElement("p");
      detail.textContent = search ? "Try a different name or clear your search." : "Save a character or import a Character Studio package to build your cast.";
      empty.append(title, detail);
      library.append(empty);
      return;
    }
    characters.forEach((character) => {
      const card = document.createElement("article");
      card.className = "library-card";
      card.classList.toggle("is-selected", character.id === state.selectedId);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "library-card-select";
      button.setAttribute("aria-label", `Preview ${character.name}`);
      const image = document.createElement("img");
      image.src = assetUrl(character.urls.image);
      image.alt = "";
      image.loading = "lazy";
      const name = document.createElement("strong");
      name.textContent = character.name;
      const source = document.createElement("small");
      source.textContent = character.source === "builder" ? "Mixed & matched by you" : "Drawn with imagination";
      button.append(image, name, source);
      button.addEventListener("click", () => showCharacter(character));
      const links = document.createElement("div");
      links.className = "library-card-links";
      const use = document.createElement("a");
      use.className = "library-use";
      use.textContent = "Use in a lesson ↗";
      use.href = lessonUrl(character.id);
      use.setAttribute("aria-label", `Use ${character.name} in a lesson`);
      links.append(use);
      for (const [label, key] of [["PNG ↓", "image"], ["Package ↓", "package"]]) {
        const link = document.createElement("a");
        link.textContent = label;
        link.href = assetUrl(character.urls[key]);
        link.download = "";
        link.setAttribute("aria-label", `Download ${character.name} ${key === "image" ? "PNG" : "character package"}`);
        links.append(link);
      }
      card.append(button, links);
      if (character.id === state.selectedId) {
        const selected = document.createElement("span");
        selected.className = "library-selected-badge";
        selected.setAttribute("aria-hidden", "true");
        selected.textContent = "✓";
        card.append(selected);
      }
      library.append(card);
    });
  }

  async function refreshLibrary({ silent = false } = {}) {
    $("refresh-library").disabled = true;
    try {
      const response = await api("/api/characters");
      const body = await response.json();
      state.library = Array.isArray(body.characters) ? body.characters : [];
      renderLibrary();
    } catch (error) { if (!silent) notify(error.message, true); }
    finally { $("refresh-library").disabled = false; }
  }

  function connectEvents() {
    for (const mode of ["draw", "build"]) {
      $(`tab-${mode}`).addEventListener("click", () => switchMode(mode));
      $(`tab-${mode}`).addEventListener("keydown", (event) => {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          const next = event.key === "Home" ? "draw" : event.key === "End" ? "build" : mode === "draw" ? "build" : "draw";
          switchMode(next);
          $(`tab-${next}`).focus();
        }
      });
    }
    $("character-name").addEventListener("input", () => { updateName(); edited({ preview: false }); });
    $("ink-color").addEventListener("input", (event) => setInk(event.target.value));
    $("brush-size").addEventListener("input", (event) => { $("brush-size-value").textContent = event.target.value; });
    for (const tool of DRAW_TOOLS) $(`tool-${tool}`).addEventListener("click", () => setTool(tool));
    $("mirror-drawing").addEventListener("click", () => setMirror(!state.mirror));
    canvas.addEventListener("pointerdown", startStroke);
    canvas.addEventListener("pointermove", moveStroke);
    canvas.addEventListener("pointerup", endStroke);
    canvas.addEventListener("pointercancel", endStroke);
    canvas.addEventListener("lostpointercapture", endStroke);
    document.addEventListener("keydown", (event) => {
      if (state.mode !== "draw" || $("confirm-action-dialog").open || $("saved-character-dialog").open || !(event.ctrlKey || event.metaKey) || event.altKey || event.defaultPrevented) return;
      if (event.target.closest("input,textarea,select,[contenteditable]:not([contenteditable='false'])")) return;
      const key = event.key.toLowerCase();
      if (key === "z" || key === "y") {
        event.preventDefault();
        moveHistory(key === "y" || event.shiftKey ? 1 : -1);
      }
    });
    $("undo-drawing").addEventListener("click", () => moveHistory(-1));
    $("redo-drawing").addEventListener("click", () => moveHistory(1));
    $("clear-drawing").addEventListener("click", async () => {
      if (!state.hasDrawing || !await confirmAction("Start with a fresh canvas? You can still use Undo to bring this drawing back.", { title: "Start a fresh drawing?", confirmLabel: "Clear the canvas" })) return;
      fillWhite();
      state.hasDrawing = false;
      $("polish-comparison").hidden = true;
      pushHistory();
      edited();
    });
    $("drawing-upload").addEventListener("change", (event) => {
      importDrawing(event.target.files[0]);
      event.target.value = "";
    });
    $("polish-drawing").addEventListener("click", polishDrawing);
    $("ai-consent").addEventListener("change", refreshSaveButton);
    $("beautify-drawing").addEventListener("click", beautifyDrawing);
    $("copy-makeover-prompt").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText($("makeover-prompt").value);
        $("copy-prompt-status").textContent = "Copied! Paste it in Gemini.";
      } catch (_) {
        $("makeover-prompt").focus();
        $("makeover-prompt").select();
        $("copy-prompt-status").textContent = "Select and copy the request above.";
      }
    });
    $("keep-original").addEventListener("click", () => { $("polish-comparison").hidden = true; notify("Your drawing stays just the way you made it."); });
    $("use-polished").addEventListener("click", usePolished);
    $("save-character").addEventListener("click", saveCharacter);
    $("refresh-library").addEventListener("click", () => refreshLibrary());
    $("library-search").addEventListener("input", renderLibrary);
    $("package-upload").addEventListener("change", (event) => {
      importPackage(event.target.files[0]);
      event.target.value = "";
    });
    $("edit-character-copy").addEventListener("click", editCharacterCopy);
    $("duplicate-character").addEventListener("click", duplicateCharacter);
    $("preview-motion").addEventListener("click", previewMotion);
    $("saved-character-dialog").addEventListener("close", resetMotion);
    $("close-character-dialog").addEventListener("click", () => $("saved-character-dialog").close());
    $("saved-character-dialog").addEventListener("click", (event) => {
      if (event.target !== $("saved-character-dialog")) return;
      const rect = event.target.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close();
    });
    window.addEventListener("pagehide", saveDraft);
  }

  async function init() {
    fillWhite();
    pushHistory();
    connectEvents();
    makePalette();
    const draft = getDraft();
    if (draft && typeof draft.name === "string") $("character-name").value = draft.name.slice(0, 32);
    if (draft && /^#[0-9a-f]{6}$/i.test(draft.ink || "")) setInk(draft.ink);
    updateName();
    if (draft?.mirror) setMirror(true);
    if (typeof draft?.original === "string" && draft.original.length <= MAX_DRAFT_IMAGE && draft.original.startsWith("data:image/png;base64,")) preserveOriginal(draft.original);
    if (draft?.image && typeof draft.image === "string" && draft.image.length <= MAX_DRAFT_IMAGE && draft.image.startsWith("data:image/png;base64,")) {
      try {
        state.loadingImage = true;
        await loadImage(draft.image);
        state.hasDrawing = true;
        state.dirty = true;
        pushHistory();
      } catch (_) { /* A damaged local draft must not block the studio. */ }
      finally { state.loadingImage = false; }
    }
    updatePreview();
    refreshSaveButton();
    refreshLibrary({ silent: true });
    refreshAiStatus();
    try {
      const response = await api("/api/catalog");
      state.catalog = await response.json();
      if (!state.catalog.defaults || !state.catalog.options || !Array.isArray(state.catalog.presets)) throw new Error("The character parts could not load. Please refresh the studio.");
      $("character-name").maxLength = state.catalog.name_max_length || 32;
      applyDesign(draft?.design || state.catalog.defaults);
      if (draft?.design || draft?.name) state.dirty = true;
      createBuilderControls();
      updateName();
      switchMode(draft?.mode === "build" ? "build" : "draw", { persist: false });
      setStatus();
    } catch (error) {
      setStatus(`${error.message} You can still draw and save a character.`);
      $("tab-build").disabled = true;
      switchMode("draw", { persist: false });
    }
    updateHistoryTools();
  }

  init();
})();
