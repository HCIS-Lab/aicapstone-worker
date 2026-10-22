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
import signal
import subprocess
import threading
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


def _mock_rollout(sid: int, on_progress=None) -> RolloutResult:
    """Random success rate after a short sleep. `sid` seeds the RNG so
    the same submission always mocks the same rate — makes end-to-end
    smoke tests deterministic.

    If `on_progress` is provided (callable), we call it every N episodes
    so the smoke test path also exercises the live-progress pipeline.
    """
    rng = random.Random(sid)
    total_eps = 30
    episodes = []
    ok = 0
    if on_progress:
        try: on_progress(phase="staging", message="[mock] warming up")
        except Exception: pass
    for i in range(total_eps):
        # spread the fake work across ~2s total so students see a
        # progress bar move rather than a single FINISHED flash
        time.sleep(0.06)
        success = rng.random() < 0.75
        episodes.append({"episode_id": i, "success": success})
        if success:
            ok += 1
        if on_progress and (i % 3 == 2 or i == total_eps - 1):
            try:
                on_progress(
                    phase="evaluating",
                    episode=i + 1, episode_total=total_eps,
                    cumulative_success_rate=round(ok / (i + 1), 4),
                    message=f"[mock] episode {i+1}/{total_eps} → {'ok' if success else 'fail'}",
                )
            except Exception:
                pass
    rate = round(ok / total_eps, 4)
    if on_progress:
        try: on_progress(phase="cleanup", message=f"[mock] final rate {rate:.3f}")
        except Exception: pass
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


# Per-policy defaults for --policy_action_horizon; must match the
# central-side `ACTION_HORIZON_DEFAULTS` in
# backend/app/evaluation/evaluator.py.
_ACTION_HORIZON_DEFAULTS = {
    "lerobot-diffusion": 8, "smolvla": 8, "groot": 8, "XVLA": 8,
    "multi_task_dit": 8, "wall_x": 8,
    "pi0": 50, "pi0_fast": 50, "pi05": 50, "act": 50,
}


def _detect_policy_type(extracted: Path) -> Optional[str]:
    """Read the policy_type from the standard checkpoint JSONs.

    Order:
      1. config.json → `policy_type` / `type` / `model_type` / `policy`
      2. train_config.json → same keys
      3. None (caller decides how to bail)
    Kept small on purpose — the full tokenizer + path-heuristic mess
    lives in the central evaluator; this fallback covers the ~90 % case
    where the trainer writes the type explicitly.
    """
    import json as _json
    keys = ("policy_type", "type", "model_type", "policy", "name")
    for fname in ("config.json", "train_config.json"):
        p = extracted / fname
        if not p.is_file():
            continue
        try:
            with p.open() as f:
                blob = _json.load(f)
        except Exception:
            continue
        if not isinstance(blob, dict):
            continue
        for k in keys:
            v = blob.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _resolve_action_horizon(policy_type: str, extracted: Path) -> int:
    """Pull `n_action_steps` from train_config.json if the trainer set
    it explicitly; otherwise use the per-policy default; otherwise 1."""
    import json as _json
    for fname in ("train_config.json", "config.json"):
        p = extracted / fname
        if not p.is_file():
            continue
        try:
            with p.open() as f:
                blob = _json.load(f)
        except Exception:
            continue
        if isinstance(blob, dict):
            v = blob.get("n_action_steps")
            if isinstance(v, int) and v > 0:
                return v
    return _ACTION_HORIZON_DEFAULTS.get(policy_type, 1)


def task_config_dir_for(sid: int) -> Path:
    # Own directory, NOT inside extracted/: rollout.py puts the config's
    # parent on sys.path, which must never contain student files.
    return submission_dir(sid) / "task_config"


def _resolve_task_file(sid: int, task_name: str, task_config: Optional[dict]) -> Optional[Path]:
    """Write the centrally served eval config to disk, or fall back to a
    locally mounted /private_tasks (older central / single-host dev)."""
    if task_config and task_config.get("content"):
        d = task_config_dir_for(sid)
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{task_name}_eval.py"
        f.write_text(task_config["content"], encoding="utf-8")
        f.chmod(0o600)
        log.info("task config %s from central (sha256 %s)",
                 task_config.get("filename"), str(task_config.get("sha256", ""))[:12])
        return f
    local = Path(f"/private_tasks/{task_name}_eval.py")
    return local if local.is_file() else None


def _real_rollout(sid: int, task_name: str, dataset: str, on_progress=None,
                  task_config: Optional[dict] = None) -> RolloutResult:
    """Exec rollout.py against the extracted policy.

    Command shape matches the central `EVAL_CMD_TEMPLATE`:
      python <script> --task=... --policy_type=... --policy_checkpoint_path=...
                      --policy_action_horizon=N --device=cuda:0 --headless
                      --enable_cameras --eval_rounds=50|100 --episode_length_s=N
                      --video_out=<path>

    Output is nonce-framed so import-time `print()` from the student's
    model can't spoof the final score line.
    """
    script = Path(cfg.isaac_sim_script)
    if not script.is_file():
        return RolloutResult(
            status="FAILED",
            error_message=f"rollout script not found at {script}",
        )
    extracted = extracted_dir_for(sid)
    task_file = _resolve_task_file(sid, task_name, task_config)
    if task_file is None:
        return RolloutResult(
            status="FAILED",
            error_message=f"no eval config for task '{task_name}' (central did not serve one)",
        )

    policy_type = _detect_policy_type(extracted)
    if not policy_type:
        return RolloutResult(
            status="FAILED",
            error_message=(
                "could not detect policy_type from checkpoint — expected a "
                "'policy_type'/'type'/'model_type' key in config.json or "
                "train_config.json"
            ),
        )
    action_horizon = _resolve_action_horizon(policy_type, extracted)
    eval_rounds = "50" if dataset == "public" else "100"
    episode_length_s = os.getenv("EVAL_EPISODE_LENGTH_S", "").strip() or "60"
    device = os.getenv("EVAL_DEVICE", "").strip() or "cuda:0"

    nonce = uuid.uuid4().hex
    inner_cmd = (
        f'python {script} '
        f'--task={task_file} '
        f'--policy_type={policy_type} '
        f'--policy_checkpoint_path={extracted} '
        f'--policy_action_horizon={action_horizon} '
        f'--device={device} '
        f'--headless '
        f'--enable_cameras '
        f'--eval_rounds={eval_rounds} '
        f'--episode_length_s={episode_length_s}'
    )
    cmd = [
        "bash", "-c",
        f'echo "LB-START-{nonce}"; '
        f'{inner_cmd}; '
        f'rc=$?; '
        f'echo "LB-END-{nonce}"; '
        f'exit $rc'
    ]
    started = time.time()
    # Flip status to RUNNING the moment we kick off Isaac Sim.
    if on_progress:
        try:
            on_progress(
                phase="loading_sim",
                episode_total=int(eval_rounds),
                message=f"[worker] launching Isaac Sim (policy={policy_type}, "
                        f"eval_rounds={eval_rounds})",
            )
        except Exception:
            pass

    # ── Streaming subprocess ────────────────────────────────────────
    # `subprocess.run(capture_output=True)` buffers everything in memory
    # and returns only once the child exits — nothing reaches the /ws/logs
    # stream while Isaac Sim is booting. Switch to Popen with merged
    # stderr → stdout, read line-by-line in the main thread, and forward
    # each line to `on_progress(message=line)` so the browser Watch modal
    # and the per-episode progress bar both come alive.
    _EP_RE = re.compile(r"\[Evaluation\]\s+Evaluating\s+episode\s+(\d+)", re.IGNORECASE)
    ep_total = int(eval_rounds)
    stdout_chunks: list[str] = []
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,   # merge so ordering is preserved for the log stream
        text=True,
        bufsize=1,                  # line-buffered
        start_new_session=True,
    )
    timeout_sec = int(os.getenv("EVAL_TIMEOUT_SEC", "10800"))
    timeout_at = started + timeout_sec
    timed_out = False

    def _kill_group(sig: int) -> None:
        # `cmd` is `bash -c "...; python rollout.py ..."` in its own session,
        # so signalling only `proc` leaves Isaac Sim running on the GPU.
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    # Rollout can go many minutes without printing, so the line loop below
    # can't be relied on to notice the deadline; kill from a timer instead.
    watchdog = threading.Timer(timeout_sec, _kill_group, args=(signal.SIGKILL,))
    watchdog.daemon = True
    watchdog.start()
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            stdout_chunks.append(raw)
            # Forward every line to the live log stream. Best-effort —
            # network hiccups shouldn't break the rollout.
            if on_progress and line:
                try:
                    kwargs: dict = {"message": line[-1024:]}
                    # Parse `[Evaluation] Evaluating episode N` markers
                    # to drive the per-episode progress bar.
                    m = _EP_RE.search(line)
                    if m:
                        kwargs["phase"] = "evaluating"
                        kwargs["episode"] = int(m.group(1))
                        kwargs["episode_total"] = ep_total
                    on_progress(**kwargs)
                except Exception:
                    pass
            if time.time() > timeout_at:
                timed_out = True
                break
    finally:
        watchdog.cancel()
        if proc.poll() is None:
            _kill_group(signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _kill_group(signal.SIGKILL)
    proc.wait()
    if time.time() > timeout_at:
        timed_out = True
    duration = time.time() - started
    stdout = "".join(stdout_chunks)
    combined = stdout.strip()
    if timed_out:
        return RolloutResult(
            status="FAILED",
            error_message="eval timed out",
            error_log=combined[-8192:],
            duration_sec=duration,
            detected_policy_type=policy_type,
        )

    # Trust only the nonce-framed region — student `print()` outside is dropped.
    start_marker = f"LB-START-{nonce}"
    end_marker = f"LB-END-{nonce}"
    if start_marker not in stdout or end_marker not in stdout:
        return RolloutResult(
            status="FAILED",
            error_message=(
                f"nonce framing missing — rollout did not exit cleanly "
                f"(exit_code={proc.returncode})"
            ),
            error_log=combined[-8192:],
            duration_sec=duration,
            detected_policy_type=policy_type,
        )
    body = stdout.split(start_marker, 1)[1].split(end_marker, 1)[0]

    matches = list(_FINAL_RE.finditer(body))
    if not matches:
        return RolloutResult(
            status="FAILED",
            error_message="no Final success rate line found",
            error_log=combined[-8192:],
            duration_sec=duration,
            detected_policy_type=policy_type,
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
        detected_policy_type=policy_type,
    )


def run_rollout(sid: int, task_name: str, dataset: str, on_progress=None,
                task_config: Optional[dict] = None) -> RolloutResult:
    """Entry point called by the agent's job-poll loop after a
    successful `/next-job`. Extracts the zip then delegates to the
    appropriate backend.

    `on_progress(**kwargs)` — if provided, called with the same fields
    accepted by CentralClient.report_progress. Currently wired for mock
    mode; real mode's subprocess still finalises before we hear anything,
    so per-episode progress requires the sim script to emit episode
    markers we can grep. (See _real_rollout — extension point.)
    """
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
        return _mock_rollout(sid, on_progress=on_progress)
    return _real_rollout(sid, task_name, dataset, on_progress=on_progress,
                         task_config=task_config)
