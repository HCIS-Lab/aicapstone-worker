"""Run queue: takes QUEUED runs from the local store one at a time (one
GPU per worker), runs them through rollout.py, and records progress, the
log and the result.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import threading
from datetime import datetime, timezone
from typing import Optional

from worker_agent.local_store import get_store
from worker_agent.rollout import run_rollout, task_config_dir_for
from worker_agent.storage import extracted_dir_for, submission_dir

log = logging.getLogger("worker.local")

# Set by the UI's cancel button for the run currently on the GPU.
_cancel = threading.Event()
_current: Optional[int] = None
_current_lock = threading.Lock()


def log_path_for(rid: int):
    return submission_dir(rid) / "run.log"


def current_run() -> Optional[int]:
    with _current_lock:
        return _current


def cancel(rid: int) -> bool:
    with _current_lock:
        if _current != rid:
            return False
    _cancel.set()
    return True


def _task_config(task: dict) -> dict:
    if task.get("gym_id"):
        return {"gym_id": task["gym_id"]}
    content = task.get("content") or ""
    return {
        "filename": f"{task['name']}_eval.py",
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "content": content,
    }


def _run_one(run: dict) -> None:
    store = get_store()
    rid = run["id"]
    task = store.get_task(run["task_name"])
    if task is None:
        store.update_run(rid, status="FAILED", phase=None,
                         error_message=f"task '{run['task_name']}' no longer exists",
                         finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return
    settings = store.effective_settings(task, run["overrides"])
    store.update_run(rid, settings=settings)
    logf = log_path_for(rid).open("w", encoding="utf-8")

    def _on_progress(**kw) -> None:
        if kw.get("message"):
            logf.write(kw["message"] + "\n")
            logf.flush()
        fields = {k: kw[k] for k in ("phase", "episode", "episode_total") if kw.get(k) is not None}
        if fields:
            store.update_run(rid, **fields)

    try:
        result = run_rollout(
            rid, task["name"], _task_config(task), settings,
            on_progress=_on_progress, cancel_event=_cancel,
        )
        if result.error_log:
            logf.write("\n── tail ──\n" + result.error_log + "\n")
        store.update_run(
            rid, status=result.status, phase=None,
            success_rate=result.success_rate, policy_type=result.detected_policy_type,
            duration_sec=result.duration_sec, error_message=result.error_message,
            finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        log.info("run %d %s rate=%s", rid, result.status, result.success_rate)
    except Exception as exc:  # noqa: BLE001
        log.exception("run %d crashed: %s", rid, exc)
        store.update_run(rid, status="FAILED", phase=None,
                         error_message=f"agent-side exception: {exc}",
                         finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    finally:
        logf.close()
        # Keep the zip (re-run) and the video (replay); drop the unpacked copy.
        shutil.rmtree(extracted_dir_for(rid), ignore_errors=True)
        shutil.rmtree(task_config_dir_for(rid), ignore_errors=True)


def run_loop(stop: threading.Event, poll_sec: float = 3.0) -> None:
    global _current
    store = get_store()
    while not stop.is_set():
        run = store.claim_next_run()
        if run is None:
            stop.wait(poll_sec)
            continue
        _cancel.clear()
        with _current_lock:
            _current = run["id"]
        try:
            _run_one(run)
        finally:
            with _current_lock:
                _current = None
