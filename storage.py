"""Worker-local filesystem layout.

Layout under `WORKER_STORAGE_ROOT`::

    runs/
        sid=<run_id>/
            pretrained_model.zip     ← the upload
            extracted/               ← unzip target for eval (removed after)
            task_config/             ← eval config .py for this run (removed after)
            eval_video.mp4           ← recorder output
            run.log                  ← rollout output
"""
from __future__ import annotations

import shutil
from pathlib import Path

from worker_agent.config import cfg


def submission_dir(sid: int) -> Path:
    d = cfg.storage_root / "runs" / f"sid={sid}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def zip_path_for(sid: int) -> Path:
    return submission_dir(sid) / "pretrained_model.zip"


def extracted_dir_for(sid: int) -> Path:
    d = submission_dir(sid) / "extracted"
    d.mkdir(parents=True, exist_ok=True)
    return d


def video_path_for(sid: int) -> Path:
    return submission_dir(sid) / "eval_video.mp4"


def rm_submission_dir(sid: int) -> None:
    """Best-effort — a broken permission won't stop the pipeline."""
    d = submission_dir(sid)
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)
