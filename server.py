"""FastAPI app: `/health` plus the school's UI and JSON API (local_ui.py)."""
from __future__ import annotations

from fastapi import FastAPI

from worker_agent.config import cfg
from worker_agent.local_ui import build_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Eval Worker",
        version="2.0.0",
        docs_url="/docs" if cfg.eval_mode == "mock" else None,
        redoc_url=None,
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "eval_mode": cfg.eval_mode,
                "storage_root": str(cfg.storage_root)}

    app.include_router(build_router())
    return app


app = create_app()
