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

// ---------- Element refs ----------

const submitBtn = document.getElementById("submit");
const filepathInput = document.getElementById("filepath");
const fileInput = document.getElementById("file-input");
const chooseBtn = document.getElementById("choose-file");
const dropZone = document.getElementById("drop-zone");
const fileHint = document.getElementById("file-hint");

const themeSel = document.getElementById("theme");
const modelSel = document.getElementById("model");
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

// ---------- State ----------

let pendingFile = null;
let configCache = null;
let draftConfig = null; // edited copy while modal is open

// ---------- Bootstrap ----------

bootstrap();

async function bootstrap() {
  await refreshConfig();
  if (!hasAnyKey(configCache)) {
    openSettings();
  }
}

async function refreshConfig() {
  const res = await fetch("/config");
  configCache = await res.json();
  populateDropdowns(configCache);
}

function hasAnyKey(config) {
  if (!config) return false;
  const providers = config.providers || {};
  return Object.values(providers).some((p) => p && p.has_key);
}

function populateDropdowns(config) {
  // Themes
  themeSel.innerHTML = "";
  for (const t of config.themes || []) {
    const opt = document.createElement("option");
    opt.value = t.id;
    opt.textContent = t.label || t.id;
    if (t.default) opt.selected = true;
    themeSel.appendChild(opt);
  }
  // Models
  modelSel.innerHTML = "";
  for (const m of config.models || []) {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.label || m.id;
    if (m.default) opt.selected = true;
    modelSel.appendChild(opt);
  }
  // Width default
  const defaultWidth = (config.defaults && config.defaults.width) || 1600;
  if (!widthInput.value) widthInput.value = defaultWidth;
}

// ---------- File picker / drag-drop ----------

chooseBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) setPendingFile(fileInput.files[0]);
});

filepathInput.addEventListener("input", () => {
  if (filepathInput.value && !filepathInput.value.startsWith("[file:")) {
    clearPendingFile();
  }
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
}

function clearPendingFile() {
  pendingFile = null;
  fileInput.value = "";
  fileHint.hidden = true;
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

// ---------- Submit ----------

submitBtn.addEventListener("click", runJob);
filepathInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") runJob();
});

async function runJob() {
  const filepath = filepathInput.value.trim();
  if (!pendingFile && !filepath) return;
  if (!pendingFile && filepath.startsWith("[file:")) return;

  const theme = themeSel.value;
  const model = modelSel.value;
  const width = parseInt(widthInput.value, 10);
  const root = document.getElementById("root").value.trim() || null;

  resetUi();
  setSubmitting(true);

  let resp;
  try {
    if (pendingFile) {
      const fd = new FormData();
      fd.append("file", pendingFile);
      fd.append("theme", theme);
      fd.append("model", model);
      fd.append("width", width);
      if (root) fd.append("root", root);
      resp = await fetch("/upload", { method: "POST", body: fd });
    } else {
      resp = await fetch("/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filepath, theme, model, width, root }),
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
  Object.keys(STEP_LABELS).forEach((evt) => {
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
    previewIframe.src = `/preview/${jobId}/output.html`;
    previewIframe.addEventListener("load", () => {
      previewOverlay.classList.add("hidden");
    }, { once: true });
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
  if (evtKey === "extracting_tree" && data.model) return data.model;
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
    api_key_value: "",
  });
  renderSettings();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !settingsModal.hidden) closeSettings();
});

function openSettings() {
  draftConfig = JSON.parse(JSON.stringify(configCache));
  // Add an api_key_value field per provider for editing — initially blank since
  // we never sent the real key down. Empty string on save means "leave alone".
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
  const knownProviders = ["gemini", "anthropic", "openai"];
  const providers = draftConfig.providers || (draftConfig.providers = {});
  for (const name of knownProviders) {
    if (!providers[name]) {
      providers[name] = { has_key: false, api_key_value: "" };
    }
  }
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
    input.dataset.provider = name;
    input.addEventListener("input", () => {
      provider.api_key_value = input.value;
    });
    row.appendChild(input);

    providerRows.appendChild(row);
  }

  // Models
  modelTableBody.innerHTML = "";
  const models = draftConfig.models || (draftConfig.models = []);
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
    const provSel = document.createElement("select");
    for (const name of Object.keys(draftConfig.providers || {})) {
      const o = document.createElement("option");
      o.value = name;
      o.textContent = name;
      if (m.provider === name) o.selected = true;
      provSel.appendChild(o);
    }
    provSel.addEventListener("change", () => { m.provider = provSel.value; });
    tdProvider.appendChild(provSel);
    tr.appendChild(tdProvider);

    const tdDefault = document.createElement("td");
    const defaultInput = document.createElement("input");
    defaultInput.type = "checkbox";
    defaultInput.checked = !!m.default;
    defaultInput.addEventListener("change", () => {
      // exclusive default
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

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

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
    // Empty string when the provider already had a saved key means "keep it".
    // Empty string when there's no saved key sends an empty (and stays empty).
    if (value || !provider.has_key) {
      payload.providers[name] = { api_key: value };
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
      const text = await res.text();
      alert(`Save failed: HTTP ${res.status}\n${text}`);
    } else {
      configCache = await res.json();
      populateDropdowns(configCache);
      closeSettings();
    }
  } catch (err) {
    alert(`Save failed: ${err.message}`);
  } finally {
    saveSettingsBtn.disabled = false;
    saveSettingsBtn.textContent = "Save";
  }
}
