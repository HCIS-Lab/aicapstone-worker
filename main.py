"""Worker entry point.

Two things run at the same time:

  1. FastAPI HTTP server on `WORKER_PORT` (default 8080) — the school's
     UI + JSON API (server.py / local_ui.py).
  2. Background thread draining the local run queue onto the GPU
     (local_runner.py).

Usage::

    # docker (see Dockerfile.real)
    uvicorn worker_agent.main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import logging
import threading

from worker_agent import local_runner
from worker_agent.config import cfg
from worker_agent.local_store import get_store
from worker_agent.local_ui import announce_password
from worker_agent.server import app

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("worker.main")

_stop_flag = threading.Event()
_threads: list[threading.Thread] = []


# Idempotency guard: `python -m worker_agent.main` imports this module
# twice (as __main__ and as worker_agent.main) and both copies register
# on the SAME `app` from server.py, which would start two run loops on
# one GPU. The flag lives on the app; a module global exists once per copy.
@app.on_event("startup")
def _startup():
    if getattr(app.state, "agent_started", False):
        log.info("startup already ran — skipping duplicate start")
        return
    app.state.agent_started = True

    cfg.check_or_die()
    get_store()
    announce_password()
    t = threading.Thread(target=local_runner.run_loop, args=(_stop_flag,),
                         name="local_run_loop", daemon=True)
    t.start()
    _threads.append(t)
    log.info("worker up on port %d (mode=%s) — open the UI at /", cfg.port, cfg.eval_mode)


@app.on_event("shutdown")
def _shutdown():
    log.info("shutdown requested; draining loops")
    _stop_flag.set()
    for t in _threads:
        t.join(timeout=5)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("worker_agent.main:app", host="0.0.0.0", port=cfg.port, log_level="info")
