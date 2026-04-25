const STEPS = {
  queued: "Queued",
  reading_file: "Reading file",
  extracting_tree: "Calling Gemini to extract tree",
  tree_ready: "Tree ready",
  computing_layout: "Computing layout",
  rendering_svg: "Rendering SVG",
  wrapping_html: "Wrapping HTML",
  preview_ready: "Preview ready",
  screenshotting_png: "Screenshotting PNG",
  done: "Done",
  error: "Error",
};

const submitBtn = document.getElementById("submit");
const filepathInput = document.getElementById("filepath");
const fileInput = document.getElementById("file-input");
const chooseBtn = document.getElementById("choose-file");
const dropZone = document.getElementById("drop-zone");
const fileHint = document.getElementById("file-hint");

const previewSection = document.getElementById("preview");
const previewFrame = document.getElementById("preview-frame");
const previewIframe = document.getElementById("preview-iframe");
const previewOverlay = document.getElementById("preview-overlay");
const overlayLabel = previewOverlay.querySelector(".overlay-label");

const statusSection = document.getElementById("status");
const trail = document.getElementById("status-trail");
const downloadsSection = document.getElementById("downloads");
const downloadRow = document.getElementById("download-row");
const errorSection = document.getElementById("error");
const errorMsg = document.getElementById("error-message");

let pendingFile = null;

// File picker / drag-drop wiring

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

// Block global page-level drops so dropping outside the zone doesn't navigate
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

function setPendingFile(file) {
  pendingFile = file;
  filepathInput.value = `[file: ${file.name}]`;
  fileHint.hidden = false;
  fileHint.textContent = `Holding "${file.name}" -- ${formatBytes(file.size)}. Will be uploaded to the server when you click Generate.`;
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

// Submit

submitBtn.addEventListener("click", runJob);
filepathInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") runJob();
});

async function runJob() {
  const filepath = filepathInput.value.trim();
  if (!pendingFile && !filepath) return;
  if (!pendingFile && filepath.startsWith("[file:")) return;

  const theme = document.getElementById("theme").value;
  const model = document.getElementById("model").value;
  const width = parseInt(document.getElementById("width").value, 10);
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
  Object.keys(STEPS).forEach((evt) => {
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
    const msg = `${data.step || "error"}: ${data.message || JSON.stringify(data)}`;
    showError(msg);
    es.close();
    setSubmitting(false);
    return;
  }

  appendStep(evt, STEPS[evt] || evt, data);

  if (evt === "extracting_tree") {
    overlayLabel.textContent = "Calling Gemini...";
  } else if (evt === "computing_layout") {
    overlayLabel.textContent = "Computing layout...";
  } else if (evt === "rendering_svg") {
    overlayLabel.textContent = "Rendering SVG...";
  } else if (evt === "preview_ready") {
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
  if (last && !last.classList.contains("done")) {
    last.classList.add("completed");
  }

  const li = document.createElement("li");
  li.classList.add("step", "active");
  if (evtKey === "done") li.classList.add("done");

  const labelEl = document.createElement("span");
  labelEl.className = "step-label";
  labelEl.textContent = label;
  li.appendChild(labelEl);

  if (evtKey === "tree_ready" && data.tree) {
    const summary = document.createElement("span");
    summary.className = "step-detail";
    const branchCount = (data.tree.branches || []).length;
    summary.textContent = `root: "${data.tree.root}" -- ${branchCount} branch${branchCount === 1 ? "" : "es"}`;
    li.appendChild(summary);
  } else if (evtKey === "reading_file" && data.size_bytes != null) {
    const summary = document.createElement("span");
    summary.className = "step-detail";
    summary.textContent = `${data.size_bytes} bytes`;
    li.appendChild(summary);
  } else if (evtKey === "computing_layout" && data.theme) {
    const summary = document.createElement("span");
    summary.className = "step-detail";
    summary.textContent = `${data.theme}, ${data.width}px`;
    li.appendChild(summary);
  }

  trail.appendChild(li);
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
