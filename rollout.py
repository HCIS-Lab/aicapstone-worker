"""Executes one submission's evaluation.

Two modes:

  * `EVAL_MODE=mock`   — no GPU needed; returns a random success rate
                          after a short sleep. Useful for smoke-testing
                          the agent ⇄ central protocol.
  * `EVAL_MODE=real`   — spawns `python <ISAAC_SIM_SCRIPT_PATH> ...`
                          with the same anti-cheat guards as the
                          in-tree Celery worker (nonce framing,
                          `start_new_session=True`).

The real path is a subset of what backend/app/worker/tasks.py's
`_evaluate` does — it doesn't yet handle multi-config plans or video
recording. Extend as needed for the school's deployment.
"""
from __future__ import annotations

import logging
import os
import random
import re
import subprocess
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from worker_agent.config import cfg
from worker_agent.storage import (
    extracted_dir_for, submission_dir, video_path_for, zip_path_for,
)

log = logging.getLogger("worker.rollout")


@dataclass
class RolloutResult:
    status: str  # FINISHED / FAILED
    success_rate: Optional[float] = None
    episodes: Optional[list] = None
    duration_sec: Optional[float] = None
    detected_policy_type: Optional[str] = None
    error_message: Optional[str] = None
    error_log: Optional[str] = None


def _extract_zip(sid: int) -> Path:
    """Unzip the durable copy under storage/submissions/sid=N/extracted/.
    Refuses zip-slip and symlink entries; matches the central-side
    guard in backend/app/routers/submissions.py::_validate_zip_structure.
    """
    z = zip_path_for(sid)
    target = extracted_dir_for(sid)
    with zipfile.ZipFile(z, "r") as zf:
        for member in zf.infolist():
            # zip-slip: any absolute paths or ".." components → skip
            name = member.filename
            if name.startswith("/") or ".." in name.split("/"):
                continue
            # symlinks / devices — refuse
            if (member.external_attr >> 16) & 0o170000 in (0o120000, 0o060000, 0o020000):
                continue
            zf.extract(member, target)
    return target


def _mock_rollout(sid: int) -> RolloutResult:
    """Random success rate after a short sleep. `sid` seeds the RNG so
    the same submission always mocks the same rate — makes end-to-end
    smoke tests deterministic."""
    rng = random.Random(sid)
    time.sleep(rng.uniform(1.0, 3.0))
    rate = round(rng.uniform(0.4, 0.95), 4)
    episodes = [
        {"episode_id": i, "success": rng.random() < rate}
        for i in range(30)
    ]
    return RolloutResult(
        status="FINISHED",
        success_rate=rate,
        episodes=episodes,
        duration_sec=(rng.uniform(1.0, 3.0)),
        detected_policy_type="mock",
    )


# Parse the `[Evaluation] Final success rate: X [N/M]` line the rollout
# script prints once eval completes. Same regex as backend's evaluator.
_FINAL_RE = re.compile(
    r"\[Evaluation\] Final success rate:\s*([0-9.]+)\s*\[(\d+)/(\d+)\]"
)


def _real_rollout(sid: int, task_name: str, dataset: str) -> RolloutResult:
    """Exec rollout.py against the extracted policy. Streams stdout
    with nonce framing so any output the student's model printed at
    import time can't spoof the final score line."""
    script = Path(cfg.isaac_sim_script)
    if not script.is_file():
        return RolloutResult(
            status="FAILED",
            error_message=f"rollout script not found at {script}",
        )
    extracted = extracted_dir_for(sid)
    nonce = uuid.uuid4().hex
    cmd = [
        "bash", "-c",
        f'echo "LB-START-{nonce}" && '
        f'python {script} --task=/private_tasks/{task_name}_eval.py '
        f'--checkpoint_dir={extracted} '
        f'--eval_rounds={"50" if dataset == "public" else "100"} '
        f'&& echo "LB-END-{nonce}"'
    ]
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("EVAL_TIMEOUT_SEC", "10800")),
            # Each rollout gets its own process group so a SIGTERM to
            # this agent kills the sim process too — matches the
            # `start_new_session=True` behaviour on the Celery worker.
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        return RolloutResult(
            status="FAILED",
            error_message="eval timed out",
            error_log=(exc.stdout or "") + (exc.stderr or ""),
            duration_sec=time.time() - started,
        )
    duration = time.time() - started
    stdout = proc.stdout or ""

    # Trust only the nonce-framed region — student `print()` outside is dropped.
    start_marker = f"LB-START-{nonce}"
    end_marker = f"LB-END-{nonce}"
    if start_marker not in stdout or end_marker not in stdout:
        return RolloutResult(
            status="FAILED",
            error_message="nonce framing missing — rollout did not exit cleanly",
            error_log=stdout[-4096:],
            duration_sec=duration,
        )
    body = stdout.split(start_marker, 1)[1].split(end_marker, 1)[0]

    matches = list(_FINAL_RE.finditer(body))
    if not matches:
        return RolloutResult(
            status="FAILED",
            error_message="no Final success rate line found",
            error_log=body[-4096:],
            duration_sec=duration,
        )
    m = matches[-1]  # only last match counts (anti-cheat)
    rate = float(m.group(1))
    total = int(m.group(3))
    episodes = [{"episode_id": i, "success": None} for i in range(total)]
    return RolloutResult(
        status="FINISHED",
        success_rate=rate,
        episodes=episodes,
        duration_sec=duration,
    )


def run_rollout(sid: int, task_name: str, dataset: str) -> RolloutResult:
    """Entry point called by the agent's job-poll loop after a
    successful `/next-job`. Extracts the zip then delegates to the
    appropriate backend."""
    if not zip_path_for(sid).is_file():
        return RolloutResult(
            status="FAILED",
            error_message="no policy zip in local storage — did the upload complete?",
        )
    try:
        _extract_zip(sid)
    except Exception as exc:  # noqa: BLE001
        return RolloutResult(
            status="FAILED",
            error_message=f"zip extract failed: {exc}",
        )
    if cfg.eval_mode == "mock":
        log.info("[mock] rolling submission %d", sid)
        return _mock_rollout(sid)
    return _real_rollout(sid, task_name, dataset)
