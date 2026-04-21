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

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .extract import extract_tree
from .layout import compute_layout
from .render import render_html, render_png_via_playwright, render_svg

PKG_ROOT = Path(__file__).parent
STATIC_DIR = PKG_ROOT / "static"
JOBS_ROOT = Path.home() / ".cache" / "mindbranches"
JOBS_ROOT.mkdir(parents=True, exist_ok=True)


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
    theme: str = "cream"
    model: str = "flash"
    root: str | None = None
    width: int = 1600


def _put_event(job: Job, event: str, payload: dict[str, Any] | None = None) -> None:
    if job.loop is None:
        return
    item = {"event": event, "data": json.dumps(payload or {})}
    asyncio.run_coroutine_threadsafe(job.queue.put(item), job.loop)


def _run_pipeline(job: Job, req: ConvertRequest) -> None:
    try:
        path = Path(req.filepath).expanduser()
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

        _put_event(job, "extracting_tree", {"model": req.model})
        tree = extract_tree(prose, root_override=req.root, model=req.model)
        _put_event(job, "tree_ready", {"tree": tree})

        _put_event(job, "computing_layout", {"theme": req.theme, "width": req.width})
        layout = compute_layout(tree, width=req.width, theme=req.theme)

        _put_event(job, "rendering_svg", {})
        svg = render_svg(layout)
        (job.out_dir / "tree.json").write_text(json.dumps(tree, indent=2))
        (job.out_dir / "output.svg").write_text(svg)

        _put_event(job, "wrapping_html", {})
        html = render_html(svg, bg=layout.bg)
        (job.out_dir / "output.html").write_text(html)

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
    load_dotenv()
    app = FastAPI(title="MindBranches Portal")

    @app.get("/", response_class=HTMLResponse)
    async def root() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "index.html").read_text())

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
