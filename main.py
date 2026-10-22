"""Worker Agent entry point — glues everything together.

Two things run at the same time:

  1. FastAPI HTTP server on `WORKER_PORT` (default 8080) — handles
     `/upload/{token}` etc. from student browsers + central.
  2. Background thread that runs heartbeat + job-poll loops.

Both are supervised by a single asyncio event loop so a hard crash in
either brings down the container (docker/k8s restart policy kicks in).

Usage::

    # local dev
    python -m worker_agent.main

    # docker
    uvicorn worker_agent.main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import logging
import signal
import threading
import time
from typing import Optional

from worker_agent.central_client import CentralError, client
from worker_agent.config import cfg
from worker_agent.rollout import run_rollout
from worker_agent.server import app
from worker_agent.storage import rm_submission_dir

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("worker.main")

# Flipped by SIGTERM handler so background loops know to drain + exit.
_stop_flag = threading.Event()


def _bootstrap_auth() -> None:
    """Register at boot if we don't already have a cached JWT.

    Wraps the register call with an exponential backoff so a central
    that's still coming up doesn't kill the container. Give up after
    ~5 minutes — at that point ops needs to look at the logs anyway.
    """
    if client.authenticated:
        log.info("using cached machine JWT (worker id=%s)", client.worker_id)
        return
    delay = 2
    for attempt in range(1, 8):
        try:
            client.register()
            return
        except CentralError as exc:
            log.warning("register attempt %d failed: %s", attempt, exc)
            if _stop_flag.wait(delay):
                return
            delay = min(delay * 2, 60)
    log.error("register never succeeded — check WORKER_JOIN_TOKEN + CENTRAL_API_URL")
    _stop_flag.set()


# ── Background loops ────────────────────────────────────────────────
_current_submission: Optional[int] = None
_current_submission_lock = threading.Lock()


def _report_status_for_heartbeat() -> tuple[str, Optional[int]]:
    """Return (status, current_submission_id) that we send to central.

    ONLINE when idle, BUSY when a rollout is executing. Ignores worker
    max_concurrent_evals for now — we run one at a time.
    """
    with _current_submission_lock:
        sid = _current_submission
    return ("BUSY" if sid else "ONLINE"), sid


def heartbeat_loop() -> None:
    while not _stop_flag.is_set():
        try:
            status, sid = _report_status_for_heartbeat()
            resp = client.heartbeat(status=status, current_submission_id=sid)
            if resp and resp.get("server_ordered_status") in ("MAINTENANCE", "REVOKED"):
                log.warning(
                    "central ordered status=%s — draining and exiting",
                    resp["server_ordered_status"],
                )
                _stop_flag.set()
                break
        except CentralError as exc:
            log.error("heartbeat fatal: %s", exc)
            # Try to re-register — if the operator rotated the token,
            # WORKER_JOIN_TOKEN in env still holds and the cached JWT
            # was already cleared inside heartbeat().
            _bootstrap_auth()
        _stop_flag.wait(cfg.heartbeat_interval_sec)


def _handle_job(job: dict) -> None:
    """One end-to-end job cycle: mark busy → rollout → report → cleanup."""
    global _current_submission
    sid = job["submission_id"]
    with _current_submission_lock:
        _current_submission = sid
    try:
        log.info("starting rollout sid=%d task=%s dataset=%s",
                 sid, job.get("task_name"), job.get("dataset"))
        # Bridge rollout progress → central so students see live episode
        # ticks + log lines instead of an opaque RUNNING badge.
        def _on_progress(**kwargs):
            try:
                client.report_progress(sid, **kwargs)
            except Exception:
                pass   # best-effort, do NOT slow the eval loop
        # Eval configs are served by central per job instead of being
        # baked into the image, so every school grades with the same
        # version. None = older central; rollout falls back to /private_tasks.
        task_config = client.get_task_config(sid) if cfg.eval_mode == "real" else None
        result = run_rollout(
            sid, job.get("task_name") or "", job.get("dataset") or "public",
            on_progress=_on_progress, task_config=task_config,
        )
        log.info("rollout finished sid=%d status=%s rate=%s",
                 sid, result.status, result.success_rate)
        client.report_result(
            sid,
            status=result.status,
            success_rate=result.success_rate,
            episodes=result.episodes,
            error_message=result.error_message,
            error_log=result.error_log,
            duration_sec=result.duration_sec,
            detected_policy_type=result.detected_policy_type,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("job crashed sid=%d: %s", sid, exc)
        # Best-effort terminal notice so central doesn't leave the row
        # stuck in ASSIGNED. Admin can still override manually.
        try:
            client.report_result(
                sid, status="FAILED",
                error_message=f"agent-side exception: {exc}",
            )
        except Exception:
            pass
    finally:
        with _current_submission_lock:
            _current_submission = None
        # Cleanup: drop the extracted dir but KEEP the zip in case
        # admin wants to re-run. The central `delete_zip_after_eval`
        # setting is what actually drives durable deletion — for P4
        # dist storage this happens via a separate central-issued
        # `/api/workers/.../rm` call (not implemented in v1).
        try:
            # Only remove the `extracted/` dir, not the whole submission dir.
            from worker_agent.storage import extracted_dir_for
            import shutil
            edir = extracted_dir_for(sid)
            if edir.is_dir():
                shutil.rmtree(edir, ignore_errors=True)
            from worker_agent.rollout import task_config_dir_for
            shutil.rmtree(task_config_dir_for(sid), ignore_errors=True)
        except Exception:
            pass


def _handle_config_validation(job: dict) -> None:
    """Central asked us to dry-load a task config in Isaac Sim.

    MVP behavior:
      * If EVAL_MODE == 'mock' or the sim script isn't present, we do a
        cheap Python syntax check and report `skipped`.
      * If real mode + script exists, we `exec` the config content in an
        isolated scope with `__task_cfg` conventions — matches how the
        rollout script imports task configs. Report `load_ok` /
        `load_failed` based on whether it runs cleanly.
    """
    import ast
    cid = job["config_id"]
    src = job.get("config_file_content") or ""
    log.info("validating config #%d (%d bytes)", cid, len(src))
    status = "skipped"
    note = ""
    log_tail = ""
    try:
        ast.parse(src)   # cheap Python syntax check — first line of defence
    except SyntaxError as exc:
        status = "load_failed"
        note = f"Python syntax error: {exc}"
        client.report_config_validation(cid, status=status, note=note)
        return

    if cfg.eval_mode != "real":
        status = "skipped"
        note = "worker is in mock mode — reported syntax-check only"
    else:
        # Attempt to import the config into a sandbox scope. Doesn't cover
        # the Isaac Sim import chain, but catches most typos.
        scope = {"__name__": "__validate__"}
        try:
            exec(compile(src, f"config-{cid}", "exec"), scope, scope)
            status = "load_ok"
            note = "exec succeeded outside Isaac Sim"
        except Exception as exc:
            status = "load_failed"
            note = f"exec raised: {type(exc).__name__}: {exc}"
            import traceback
            log_tail = traceback.format_exc()[-8000:]
    try:
        client.report_config_validation(cid, status=status, note=note, log_tail=log_tail or None)
    except Exception as exc:
        log.exception("failed to report config validation result: %s", exc)


def job_poll_loop() -> None:
    while not _stop_flag.is_set():
        try:
            job = client.next_job()
            if job:
                # /next-job now multiplexes two job types. Legacy responses
                # without job_type fall back to the submission branch so
                # older central deployments keep working.
                jt = job.get("job_type") or "submission"
                if jt == "config_validation":
                    _handle_config_validation(job)
                else:
                    _handle_job(job)
                continue  # try immediately for more — queue drained fast
        except CentralError as exc:
            log.error("next-job fatal: %s", exc)
            _bootstrap_auth()
        _stop_flag.wait(cfg.job_poll_interval_sec)


# ── Uvicorn hooks ───────────────────────────────────────────────────
_threads: list[threading.Thread] = []


# Idempotency guard: some launch patterns (`python -m worker_agent.main`
# followed by uvicorn re-importing the same module as "worker_agent.main")
# fire `_startup` twice, doubling every background thread — heartbeat
# lands twice per interval AND the job-poll loop grabs two submissions at
# once. Keep this flag module-level so ANY startup path only spawns once.
_startup_done = False


@app.on_event("startup")
def _startup():
    global _startup_done
    if _startup_done:
        log.info("startup already ran — skipping duplicate registration")
        return
    _startup_done = True

    cfg.check_or_die()
    _bootstrap_auth()
    if _stop_flag.is_set():
        # bootstrap failed → don't spawn loops
        return
    for target in (heartbeat_loop, job_poll_loop):
        t = threading.Thread(target=target, name=target.__name__, daemon=True)
        t.start()
        _threads.append(t)
    log.info("worker agent up on port %d (worker_id=%s, mode=%s)",
             cfg.port, client.worker_id, cfg.eval_mode)


@app.on_event("shutdown")
def _shutdown():
    log.info("shutdown requested; draining loops")
    _stop_flag.set()
    for t in _threads:
        t.join(timeout=5)


# ── Signal handlers for `python -m worker_agent.main` ───────────────
def _install_signal_handlers():
    def _handler(signum, _frame):
        log.info("received signal %d — exiting", signum)
        _stop_flag.set()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            # Not running in the main thread (uvicorn will handle it itself).
            pass


if __name__ == "__main__":
    import uvicorn
    _install_signal_handlers()
    uvicorn.run(
        "worker_agent.main:app",
        host="0.0.0.0",
        port=cfg.port,
        log_level="info",
    )
