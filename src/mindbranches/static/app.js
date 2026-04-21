const STEPS = {
  queued: "Queued",
  reading_file: "Reading file",
  extracting_tree: "Calling Claude to extract tree",
  tree_ready: "Tree ready",
  computing_layout: "Computing layout",
  rendering_svg: "Rendering SVG",
  wrapping_html: "Wrapping HTML",
  screenshotting_png: "Screenshotting PNG",
  done: "Done",
  error: "Error",
};

const submitBtn = document.getElementById("submit");
const statusSection = document.getElementById("status");
const trail = document.getElementById("status-trail");
const downloadsSection = document.getElementById("downloads");
const downloadRow = document.getElementById("download-row");
const errorSection = document.getElementById("error");
const errorMsg = document.getElementById("error-message");

submitBtn.addEventListener("click", runJob);
document.getElementById("filepath").addEventListener("keydown", (e) => {
  if (e.key === "Enter") runJob();
});

async function runJob() {
  const filepath = document.getElementById("filepath").value.trim();
  if (!filepath) return;

  const theme = document.getElementById("theme").value;
  const model = document.getElementById("model").value;
  const width = parseInt(document.getElementById("width").value, 10);
  const root = document.getElementById("root").value.trim() || null;

  resetUi();
  setSubmitting(true);

  let resp;
  try {
    resp = await fetch("/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filepath, theme, model, width, root }),
    });
  } catch (err) {
    showError(`Network error: ${err.message}`);
    return;
  }

  if (!resp.ok) {
    showError(`HTTP ${resp.status}: ${await resp.text()}`);
    return;
  }
  const { job_id } = await resp.json();

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

  if (evt === "done") {
    populateDownloads(jobId, data.outputs || []);
    es.close();
    setSubmitting(false);
  }
}

function appendStep(evtKey, label, data) {
  // Mark the previous step as completed
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

  const preview = document.createElement("a");
  preview.href = `/preview/${jobId}/output.html`;
  preview.textContent = "preview in browser";
  preview.classList.add("chip", "primary");
  preview.target = "_blank";
  downloadRow.appendChild(preview);

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
