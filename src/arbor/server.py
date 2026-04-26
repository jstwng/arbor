"""FastAPI portal with SSE live status tracker."""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .config import (
    default_model_id,
    default_theme_id,
    load_config,
    public_config,
    save_config,
)
from .depth import clamp_layers, normalize_tree, suggest_layers
from .extract import extract_tree
from .layout import compute_layout
from .render import render_html, render_png_via_playwright, render_svg

PKG_ROOT = Path(__file__).parent
STATIC_DIR = PKG_ROOT / "static"
JOBS_ROOT = Path.home() / ".cache" / "mindbranches"
JOBS_ROOT.mkdir(parents=True, exist_ok=True)

# Single mutable config dict held on the app. Updated in-place when the user
# saves changes via POST /config so background pipeline runs see the new values.
APP_CONFIG: dict[str, Any] = {}


@dataclass
class Job:
    job_id: str
    out_dir: Path
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    loop: asyncio.AbstractEventLoop | None = None
    done: bool = False


JOBS: dict[str, Job] = {}


class ConvertRequest(BaseModel):
    filepath: str
    theme: str | None = None
    model: str | None = None
    root: str | None = None
    width: int | None = None
    layers: int | None = None  # 2..5; None means auto-suggest from file size


class ConfigUpdate(BaseModel):
    providers: dict[str, dict[str, str]] | None = None
    models: list[dict[str, Any]] | None = None
    themes: list[dict[str, Any]] | None = None
    defaults: dict[str, Any] | None = None


def _put_event(job: Job, event: str, payload: dict[str, Any] | None = None) -> None:
    if job.loop is None:
        return
    item = {"event": event, "data": json.dumps(payload or {})}
    asyncio.run_coroutine_threadsafe(job.queue.put(item), job.loop)


def _resolve_request(req: ConvertRequest) -> tuple[str, str, int]:
    theme = req.theme or default_theme_id(APP_CONFIG)
    model = req.model or default_model_id(APP_CONFIG)
    width = req.width or APP_CONFIG.get("defaults", {}).get("width", 1600)
    return theme, model, width


def _strip_wrapping_quotes(s: str) -> str:
    """Drop one matching pair of leading/trailing single or double quotes.

    macOS Finder's "Copy as Pathname" wraps the path in shell-style single
    quotes; the input field receives them verbatim. Strip them so the user
    doesn't have to.
    """
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _run_pipeline(job: Job, req: ConvertRequest) -> None:
    try:
        path = Path(_strip_wrapping_quotes(req.filepath)).expanduser()
        if not path.exists():
            _put_event(
                job,
                "error",
                {"step": "reading_file", "message": f"File not found: {path}"},
            )
            return

        size = path.stat().st_size
        _put_event(job, "reading_file", {"path": str(path), "size_bytes": size})
        prose = path.read_text().strip()
        if not prose:
            _put_event(
                job,
                "error",
                {"step": "reading_file", "message": "Input file is empty."},
            )
            return

        theme, model, width = _resolve_request(req)
        layers = clamp_layers(req.layers, suggest_layers(len(prose.encode("utf-8"))))

        _put_event(job, "extracting_tree", {"model": model, "layers": layers})
        tree = extract_tree(
            prose,
            root_override=req.root,
            model_id=model,
            config=APP_CONFIG,
            layers=layers,
        )
        tree = normalize_tree(tree)
        _put_event(job, "tree_ready", {"tree": tree})

        _put_event(job, "computing_layout", {"theme": theme, "width": width})
        layout = compute_layout(tree, width=width, theme=theme)

        _put_event(job, "rendering_svg", {})
        svg = render_svg(layout)
        (job.out_dir / "tree.json").write_text(json.dumps(tree, indent=2))
        (job.out_dir / "output.svg").write_text(svg)

        _put_event(job, "wrapping_html", {})
        html = render_html(svg, bg=layout.bg)
        (job.out_dir / "output.html").write_text(html)

        _put_event(
            job,
            "preview_ready",
            {"bg": layout.bg, "width": layout.width, "height": layout.height},
        )

        _put_event(job, "screenshotting_png", {"estimate_seconds": 2})
        render_png_via_playwright(
            job.out_dir / "output.html",
            job.out_dir / "output.png",
            viewport_width=layout.width,
            viewport_height=layout.height,
        )

        _put_event(
            job,
            "done",
            {"outputs": ["tree.json", "output.svg", "output.html", "output.png"]},
        )
    except Exception as exc:
        _put_event(
            job,
            "error",
            {"step": "unknown", "message": f"{type(exc).__name__}: {exc}"},
        )
    finally:
        _put_event(job, "_end", {})


def create_app() -> FastAPI:
    APP_CONFIG.clear()
    APP_CONFIG.update(load_config())

    app = FastAPI(title="MindBranches Portal")

    # Local-dev tool: never cache portal HTML/CSS/JS so iterating on the
    # frontend doesn't get masked by a stale browser cache.
    @app.middleware("http")
    async def no_cache_static(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/static"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.get("/", response_class=HTMLResponse)
    async def root() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "index.html").read_text())

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/config")
    async def get_config_endpoint() -> dict[str, Any]:
        return public_config(APP_CONFIG)

    @app.post("/config")
    async def post_config_endpoint(update: ConfigUpdate) -> dict[str, Any]:
        if update.providers is not None:
            providers = APP_CONFIG.setdefault("providers", {})
            for name, payload in update.providers.items():
                provider = providers.setdefault(name, {})
                if "api_key" in payload:
                    provider["api_key"] = payload["api_key"].strip()
        if update.models is not None:
            APP_CONFIG["models"] = update.models
        if update.themes is not None:
            APP_CONFIG["themes"] = update.themes
        if update.defaults is not None:
            APP_CONFIG.setdefault("defaults", {}).update(update.defaults)
        save_config(APP_CONFIG)
        return public_config(APP_CONFIG)

    @app.post("/convert")
    async def convert(req: ConvertRequest) -> dict[str, str]:
        job_id = uuid.uuid4().hex[:12]
        out_dir = JOBS_ROOT / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        job = Job(job_id=job_id, out_dir=out_dir, loop=loop)
        JOBS[job_id] = job
        threading.Thread(
            target=_run_pipeline, args=(job, req), daemon=True
        ).start()
        return {"job_id": job_id}

    @app.post("/upload")
    async def upload(
        file: UploadFile = File(...),
        theme: str | None = Form(None),
        model: str | None = Form(None),
        root: str | None = Form(None),
        width: int | None = Form(None),
        layers: int | None = Form(None),
    ) -> dict[str, str]:
        job_id = uuid.uuid4().hex[:12]
        out_dir = JOBS_ROOT / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        input_path = out_dir / "input.txt"
        content = await file.read()
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large (>5 MB).")
        input_path.write_bytes(content)

        loop = asyncio.get_running_loop()
        job = Job(job_id=job_id, out_dir=out_dir, loop=loop)
        JOBS[job_id] = job
        req = ConvertRequest(
            filepath=str(input_path),
            theme=theme,
            model=model,
            root=root,
            width=width,
            layers=layers,
        )
        threading.Thread(
            target=_run_pipeline, args=(job, req), daemon=True
        ).start()
        return {"job_id": job_id}

    @app.get("/status/{job_id}")
    async def status(job_id: str) -> EventSourceResponse:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Unknown job {job_id}")

        async def gen():
            while True:
                item = await job.queue.get()
                if item["event"] == "_end":
                    job.done = True
                    break
                yield item

        return EventSourceResponse(gen())

    @app.get("/download/{job_id}/{filename}")
    async def download(job_id: str, filename: str) -> FileResponse:
        if filename not in {"tree.json", "output.svg", "output.html", "output.png"}:
            raise HTTPException(status_code=404)
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404)
        path = job.out_dir / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Not yet ready: {filename}")
        return FileResponse(path, filename=filename)

    @app.get("/preview/{job_id}/output.html")
    async def preview(job_id: str) -> FileResponse:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404)
        path = job.out_dir / "output.html"
        if not path.exists():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="text/html")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(prog="mindbranches-portal")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    import uvicorn

    print(f"\nMindBranches portal: http://{args.host}:{args.port}\n", flush=True)
    uvicorn.run(
        "mindbranches.server:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        log_level="warning",
    )
