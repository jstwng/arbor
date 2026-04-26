// ---------- Custom dropdown ----------
//
// Replaces native <select> so the OPEN menu is fully styleable. Returns a
// container element with .getValue() / .setValue() / .setOptions() handles.

function createDropdown({ options, value, onChange, size = "normal", placeholder = "" }) {
  const root = document.createElement("div");
  root.className = "dropdown" + (size === "compact" ? " dropdown-compact" : "");
  root.dataset.open = "false";

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "dropdown-trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");

  const valueSpan = document.createElement("span");
  valueSpan.className = "dropdown-value";
  trigger.appendChild(valueSpan);

  const panel = document.createElement("ul");
  panel.className = "dropdown-panel";
  panel.setAttribute("role", "listbox");

  let currentOptions = options.slice();
  let currentValue = value;

  function render() {
    const sel = currentOptions.find((o) => o.value === currentValue);
    valueSpan.textContent = sel ? sel.label : (placeholder || "");
    valueSpan.style.color = sel ? "" : "var(--muted)";
    panel.innerHTML = "";
    currentOptions.forEach((opt) => {
      const li = document.createElement("li");
      li.className = "dropdown-option";
      li.setAttribute("role", "option");
      li.dataset.value = opt.value;
      li.setAttribute("aria-selected", String(opt.value === currentValue));
      li.textContent = opt.label;
      li.addEventListener("mousedown", (e) => {
        // mousedown so we beat the document-level click-outside listener
        e.preventDefault();
        e.stopPropagation();
        setValue(opt.value);
        close();
      });
      panel.appendChild(li);
    });
  }

  function setValue(v) {
    currentValue = v;
    render();
    if (onChange) onChange(v);
  }

  function open() {
    closeAllDropdowns();
    root.dataset.open = "true";
    trigger.setAttribute("aria-expanded", "true");
  }
  function close() {
    root.dataset.open = "false";
    trigger.setAttribute("aria-expanded", "false");
  }
  function toggle() {
    if (root.dataset.open === "true") close();
    else open();
  }

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle();
  });

  trigger.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
      e.preventDefault();
      open();
      const sel = panel.querySelector('[aria-selected="true"]') || panel.querySelector(".dropdown-option");
      if (sel) sel.focus();
    } else if (e.key === "Escape") {
      close();
    }
  });

  root.appendChild(trigger);
  root.appendChild(panel);
  render();

  root.getValue = () => currentValue;
  root.setValue = setValue;
  root.setOptions = (opts, keepValue = true) => {
    currentOptions = opts.slice();
    if (!keepValue || !currentOptions.find((o) => o.value === currentValue)) {
      const def = currentOptions.find((o) => o.default) || currentOptions[0];
      currentValue = def ? def.value : null;
    }
    render();
  };

  return root;
}

document.addEventListener("click", () => closeAllDropdowns());
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeAllDropdowns();
});

function closeAllDropdowns() {
  document.querySelectorAll('.dropdown[data-open="true"]').forEach((d) => {
    d.dataset.open = "false";
    const t = d.querySelector(".dropdown-trigger");
    if (t) t.setAttribute("aria-expanded", "false");
  });
}

// ---------- App state ----------

const STEP_LABELS = {
  queued: "Queued",
  reading_file: "Reading file",
  extracting_tree: "Calling model to extract tree",
  tree_ready: "Tree ready",
  computing_layout: "Computing layout",
  rendering_svg: "Rendering SVG",
  wrapping_html: "Wrapping HTML",
  preview_ready: "Preview ready",
  screenshotting_png: "Snapshotting PNG",
  done: "Done",
  error: "Error",
};

const submitBtn = document.getElementById("submit");
const filepathInput = document.getElementById("filepath");
const fileInput = document.getElementById("file-input");
const chooseBtn = document.getElementById("choose-file");
const dropZone = document.getElementById("drop-zone");
const fileHint = document.getElementById("file-hint");
const widthInput = document.getElementById("width");

const previewSection = document.getElementById("preview");
const previewIframe = document.getElementById("preview-iframe");
const previewOverlay = document.getElementById("preview-overlay");
const overlayLabel = previewOverlay.querySelector(".overlay-label");

const statusSection = document.getElementById("status");
const trail = document.getElementById("status-trail");
const downloadsSection = document.getElementById("downloads");
const downloadRow = document.getElementById("download-row");
const errorSection = document.getElementById("error");
const errorMsg = document.getElementById("error-message");

const settingsModal = document.getElementById("settings-modal");
const settingsBackdrop = document.getElementById("settings-backdrop");
const openSettingsBtn = document.getElementById("open-settings");
const closeSettingsBtn = document.getElementById("close-settings");
const cancelSettingsBtn = document.getElementById("cancel-settings");
const saveSettingsBtn = document.getElementById("save-settings");
const providerRows = document.getElementById("provider-rows");
const modelTableBody = document.querySelector("#model-table tbody");
const addModelBtn = document.getElementById("add-model");
const defaultWidthInput = document.getElementById("default-width");

const themeHost = document.getElementById("theme-host");
const modelHost = document.getElementById("model-host");
const layersHost = document.getElementById("layers-host");
const layersHint = document.getElementById("layers-hint");

let pendingFile = null;
let configCache = null;
let draftConfig = null;
let themeDropdown = null;
let modelDropdown = null;
let layersDropdown = null;
let lastTypedPathSize = null;  // bytes of the typed file, for auto-hint

// Mirror of depth.suggest_layers in Python -- keep both in sync.
function suggestLayers(byteCount) {
  if (byteCount < 1500) return 2;
  if (byteCount < 8000) return 3;
  if (byteCount < 50000) return 4;
  return 5;
}

const LAYER_OPTIONS = [
  { value: "auto", label: "Auto" },
  { value: "2",    label: "2 layers" },
  { value: "3",    label: "3 layers" },
  { value: "4",    label: "4 layers" },
  { value: "5",    label: "5 layers" },
];

// ---------- Bootstrap ----------

bootstrap();

async function bootstrap() {
  await refreshConfig();
  if (!hasAnyKey(configCache)) openSettings();
}

async function refreshConfig() {
  const res = await fetch("/config");
  configCache = await res.json();
  populateMainDropdowns(configCache);
}

function hasAnyKey(config) {
  if (!config) return false;
  const providers = config.providers || {};
  return Object.values(providers).some((p) => p && p.has_key);
}

function populateMainDropdowns(config) {
  const themes = (config.themes || []).map((t) => ({
    value: t.id,
    label: t.label || t.id,
    default: !!t.default,
  }));
  const models = (config.models || []).map((m) => ({
    value: m.id,
    label: m.label || m.id,
    default: !!m.default,
  }));

  const themeDefault = (themes.find((t) => t.default) || themes[0] || {}).value;
  const modelDefault = (models.find((m) => m.default) || models[0] || {}).value;

  if (!themeDropdown) {
    themeDropdown = createDropdown({ options: themes, value: themeDefault });
    themeHost.appendChild(themeDropdown);
  } else {
    themeDropdown.setOptions(themes);
  }

  if (!modelDropdown) {
    modelDropdown = createDropdown({ options: models, value: modelDefault });
    modelHost.appendChild(modelDropdown);
  } else {
    modelDropdown.setOptions(models);
  }

  if (!layersDropdown) {
    layersDropdown = createDropdown({ options: LAYER_OPTIONS, value: "auto" });
    layersHost.appendChild(layersDropdown);
  }

  const defaultWidth = (config.defaults && config.defaults.width) || 1600;
  if (!widthInput.value) widthInput.value = defaultWidth;
}

function updateLayersHint(byteCount) {
  if (byteCount == null) {
    layersHint.textContent = "";
    return;
  }
  const suggested = suggestLayers(byteCount);
  layersHint.textContent = `auto: ${suggested}`;
}

// ---------- File picker / drag-drop ----------

chooseBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) setPendingFile(fileInput.files[0]);
});

filepathInput.addEventListener("input", () => {
  if (filepathInput.value && !filepathInput.value.startsWith("[file:")) clearPendingFile();
});

["dragenter", "dragover"].forEach((evt) => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.add("drag-hover");
  });
});

["dragleave", "drop"].forEach((evt) => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove("drag-hover");
  });
});

dropZone.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length) setPendingFile(e.dataTransfer.files[0]);
});

window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

function setPendingFile(file) {
  pendingFile = file;
  filepathInput.value = `[file: ${file.name}]`;
  fileHint.hidden = false;
  fileHint.textContent = `Holding "${file.name}" -- ${formatBytes(file.size)}. Will be uploaded when you click Generate.`;
  updateLayersHint(file.size);
}

function clearPendingFile() {
  pendingFile = null;
  fileInput.value = "";
  fileHint.hidden = true;
  updateLayersHint(lastTypedPathSize);
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

// macOS "Copy as Pathname" wraps the path in shell-style single quotes;
// some shells use double quotes. Drop a single matching pair on submit.
function stripWrappingQuotes(s) {
  if (s.length >= 2) {
    const a = s[0], b = s[s.length - 1];
    if ((a === "'" && b === "'") || (a === '"' && b === '"')) {
      return s.slice(1, -1);
    }
  }
  return s;
}

// ---------- Submit ----------

submitBtn.addEventListener("click", runJob);
filepathInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") runJob();
});

async function runJob() {
  const filepath = stripWrappingQuotes(filepathInput.value.trim());
  if (!pendingFile && !filepath) return;
  if (!pendingFile && filepath.startsWith("[file:")) return;

  const theme = themeDropdown ? themeDropdown.getValue() : null;
  const model = modelDropdown ? modelDropdown.getValue() : null;
  const layersVal = layersDropdown ? layersDropdown.getValue() : "auto";
  const layers = (layersVal && layersVal !== "auto") ? parseInt(layersVal, 10) : null;
  const width = parseInt(widthInput.value, 10);
  const root = document.getElementById("root").value.trim() || null;

  resetUi();
  setSubmitting(true);

  let resp;
  try {
    if (pendingFile) {
      const fd = new FormData();
      fd.append("file", pendingFile);
      if (theme) fd.append("theme", theme);
      if (model) fd.append("model", model);
      fd.append("width", width);
      if (root) fd.append("root", root);
      if (layers != null) fd.append("layers", String(layers));
      resp = await fetch("/upload", { method: "POST", body: fd });
    } else {
      resp = await fetch("/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filepath, theme, model, width, root, layers }),
      });
    }
  } catch (err) {
    showError(`Network error: ${err.message}`);
    return;
  }

  if (!resp.ok) {
    showError(`HTTP ${resp.status}: ${await resp.text()}`);
    return;
  }
  const { job_id } = await resp.json();

  showPreviewSkeleton();

  const es = new EventSource(`/status/${job_id}`);
  const ALL_EVENTS = Object.keys(STEP_LABELS).concat(["branch_partial", "tree_complete", "validation_retry"]);
  ALL_EVENTS.forEach((evt) => {
    es.addEventListener(evt, (e) => handleEvent(evt, e, job_id, es));
  });
  es.addEventListener("error", () => {
    es.close();
    setSubmitting(false);
  });
}

function resetUi() {
  statusSection.hidden = false;
  trail.innerHTML = "";
  downloadsSection.hidden = true;
  downloadRow.innerHTML = "";
  errorSection.hidden = true;
  errorMsg.textContent = "";
  previewSection.hidden = true;
  previewIframe.removeAttribute("src");
  previewOverlay.classList.remove("hidden");
  overlayLabel.textContent = "Building diagram...";
}

function showPreviewSkeleton() {
  previewSection.hidden = false;
  previewOverlay.classList.remove("hidden");
  overlayLabel.textContent = "Building diagram...";
}

function setSubmitting(on) {
  submitBtn.disabled = on;
  submitBtn.textContent = on ? "Generating..." : "Generate";
}

function handleEvent(evt, e, jobId, es) {
  let data = {};
  try { data = JSON.parse(e.data || "{}"); } catch (_) {}

  if (evt === "error") {
    showError(`${data.step || "error"}: ${data.message || JSON.stringify(data)}`);
    es.close();
    setSubmitting(false);
    return;
  }

  appendStep(evt, STEP_LABELS[evt] || evt, data);

  if (evt === "extracting_tree") overlayLabel.textContent = "Calling model...";
  else if (evt === "computing_layout") overlayLabel.textContent = "Computing layout...";
  else if (evt === "rendering_svg") overlayLabel.textContent = "Rendering SVG...";
  else if (evt === "preview_ready") {
    if (data.width && data.height) {
      const previewFrame = document.getElementById("preview-frame");
      previewFrame.style.aspectRatio = `${data.width} / ${data.height}`;
    }
    const url = data.url || `/preview/${jobId}/output.html`;
    previewIframe.src = url;
    previewIframe.addEventListener("load", () => {
      previewOverlay.classList.add("hidden");
    }, { once: true });
  } else if (evt === "branch_partial") {
    if (previewIframe.contentWindow) {
      previewIframe.contentWindow.postMessage({ type: "branch_partial", data: data }, "*");
    }
  } else if (evt === "tree_complete") {
    if (previewIframe.contentWindow) {
      previewIframe.contentWindow.postMessage({ type: "tree_complete", data: data }, "*");
    }
  } else if (evt === "screenshotting_png") {
    overlayLabel.textContent = "Snapshotting PNG...";
  }

  if (evt === "done") {
    populateDownloads(jobId, data.outputs || []);
    previewOverlay.classList.add("hidden");
    es.close();
    setSubmitting(false);
  }
}

function appendStep(evtKey, label, data) {
  const last = trail.lastElementChild;
  if (last && !last.classList.contains("done")) last.classList.add("completed");

  const li = document.createElement("li");
  li.classList.add("step", "active");
  if (evtKey === "done") li.classList.add("done");

  const labelEl = document.createElement("span");
  labelEl.className = "step-label";
  labelEl.textContent = label;
  li.appendChild(labelEl);

  const detail = stepDetail(evtKey, data);
  if (detail) {
    const summary = document.createElement("span");
    summary.className = "step-detail";
    summary.textContent = detail;
    li.appendChild(summary);
  }

  trail.appendChild(li);
}

function stepDetail(evtKey, data) {
  if (evtKey === "tree_ready" && data.tree) {
    const branchCount = (data.tree.branches || []).length;
    return `root: "${data.tree.root}" -- ${branchCount} branch${branchCount === 1 ? "" : "es"}`;
  }
  if (evtKey === "reading_file" && data.size_bytes != null) return `${data.size_bytes} bytes`;
  if (evtKey === "computing_layout" && data.theme) return `${data.theme}, ${data.width}px`;
  if (evtKey === "extracting_tree" && data.model) {
    return data.layers ? `${data.model} -- ${data.layers} layers` : data.model;
  }
  return null;
}

function populateDownloads(jobId, files) {
  downloadsSection.hidden = false;
  downloadRow.innerHTML = "";

  const open = document.createElement("a");
  open.href = `/preview/${jobId}/output.html`;
  open.textContent = "open in new tab";
  open.classList.add("chip", "primary");
  open.target = "_blank";
  downloadRow.appendChild(open);

  files.forEach((name) => {
    const a = document.createElement("a");
    a.href = `/download/${jobId}/${name}`;
    a.textContent = name;
    a.classList.add("chip");
    a.download = name;
    downloadRow.appendChild(a);
  });
}

function showError(msg) {
  errorSection.hidden = false;
  errorMsg.textContent = msg;
  setSubmitting(false);
}

// ---------- Settings modal ----------

openSettingsBtn.addEventListener("click", openSettings);
closeSettingsBtn.addEventListener("click", closeSettings);
cancelSettingsBtn.addEventListener("click", closeSettings);
settingsBackdrop.addEventListener("click", closeSettings);
saveSettingsBtn.addEventListener("click", saveSettings);
addModelBtn.addEventListener("click", () => {
  draftConfig.models.push({
    id: "",
    label: "",
    provider: defaultProviderName(draftConfig),
    default: false,
  });
  renderSettings();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !settingsModal.hidden) closeSettings();
});

function openSettings() {
  draftConfig = JSON.parse(JSON.stringify(configCache));
  for (const name of Object.keys(draftConfig.providers || {})) {
    draftConfig.providers[name].api_key_value = "";
  }
  renderSettings();
  settingsModal.hidden = false;
}

function closeSettings() {
  settingsModal.hidden = true;
  draftConfig = null;
}

function renderSettings() {
  // Providers
  providerRows.innerHTML = "";
  const providers = draftConfig.providers || (draftConfig.providers = {});
  if (!providers.gemini) providers.gemini = { has_key: false, api_key_value: "" };
  for (const [name, provider] of Object.entries(providers)) {
    const row = document.createElement("div");
    row.className = "provider-row";

    const lbl = document.createElement("label");
    lbl.textContent = capitalize(name);
    row.appendChild(lbl);

    const input = document.createElement("input");
    input.type = "password";
    input.placeholder = provider.has_key ? "(saved -- leave blank to keep)" : "paste your API key";
    input.value = provider.api_key_value || "";
    input.addEventListener("input", () => { provider.api_key_value = input.value; });
    row.appendChild(input);

    if (name === "openai_compat") {
      const urlInput = document.createElement("input");
      urlInput.type = "text";
      urlInput.placeholder = "http://localhost:11434/v1";
      urlInput.value = provider.base_url || "";
      urlInput.addEventListener("input", () => { provider.base_url = urlInput.value; });
      row.appendChild(urlInput);
    }

    providerRows.appendChild(row);
  }

  // Models
  modelTableBody.innerHTML = "";
  const models = draftConfig.models || (draftConfig.models = []);
  const providerOptions = Object.keys(draftConfig.providers || {}).map((n) => ({ value: n, label: n }));

  models.forEach((m, idx) => {
    const tr = document.createElement("tr");

    const tdLabel = document.createElement("td");
    const labelInput = document.createElement("input");
    labelInput.type = "text";
    labelInput.value = m.label || "";
    labelInput.placeholder = "Display label";
    labelInput.addEventListener("input", () => { m.label = labelInput.value; });
    tdLabel.appendChild(labelInput);
    tr.appendChild(tdLabel);

    const tdId = document.createElement("td");
    const idInput = document.createElement("input");
    idInput.type = "text";
    idInput.value = m.id || "";
    idInput.placeholder = "model id (e.g. gemini-2.5-flash)";
    idInput.addEventListener("input", () => { m.id = idInput.value; });
    tdId.appendChild(idInput);
    tr.appendChild(tdId);

    const tdProvider = document.createElement("td");
    const provDropdown = createDropdown({
      options: providerOptions,
      value: m.provider || (providerOptions[0] && providerOptions[0].value),
      onChange: (v) => { m.provider = v; },
      size: "compact",
    });
    tdProvider.appendChild(provDropdown);
    tr.appendChild(tdProvider);

    const tdDefault = document.createElement("td");
    const defaultInput = document.createElement("input");
    defaultInput.type = "checkbox";
    defaultInput.checked = !!m.default;
    defaultInput.addEventListener("change", () => {
      models.forEach((o) => { o.default = false; });
      m.default = defaultInput.checked;
      renderSettings();
    });
    tdDefault.appendChild(defaultInput);
    tr.appendChild(tdDefault);

    const tdDel = document.createElement("td");
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "row-delete";
    delBtn.textContent = "x";
    delBtn.title = "Remove model";
    delBtn.addEventListener("click", () => {
      models.splice(idx, 1);
      renderSettings();
    });
    tdDel.appendChild(delBtn);
    tr.appendChild(tdDel);

    modelTableBody.appendChild(tr);
  });

  // Defaults
  const w = (draftConfig.defaults && draftConfig.defaults.width) || 1600;
  defaultWidthInput.value = w;
}

function defaultProviderName(config) {
  const provs = Object.keys(config.providers || {});
  return provs[0] || "gemini";
}

function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

async function saveSettings() {
  const payload = {
    providers: {},
    models: (draftConfig.models || [])
      .filter((m) => m.id && m.id.trim())
      .map((m) => ({
        id: m.id.trim(),
        label: (m.label || m.id).trim(),
        provider: m.provider,
        default: !!m.default,
      })),
    themes: draftConfig.themes,
    defaults: { width: parseInt(defaultWidthInput.value, 10) || 1600 },
  };
  for (const [name, provider] of Object.entries(draftConfig.providers || {})) {
    const value = (provider.api_key_value || "").trim();
    if (value || !provider.has_key) {
      payload.providers[name] = { api_key: value };
    }
    if (name === "openai_compat" && provider.base_url !== undefined) {
      if (!payload.providers[name]) payload.providers[name] = {};
      payload.providers[name].base_url = (provider.base_url || "").trim();
    }
  }
  saveSettingsBtn.disabled = true;
  saveSettingsBtn.textContent = "Saving...";
  try {
    const res = await fetch("/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      alert(`Save failed: HTTP ${res.status}\n${await res.text()}`);
    } else {
      configCache = await res.json();
      populateMainDropdowns(configCache);
      closeSettings();
    }
  } catch (err) {
    alert(`Save failed: ${err.message}`);
  } finally {
    saveSettingsBtn.disabled = false;
    saveSettingsBtn.textContent = "Save";
  }
}
