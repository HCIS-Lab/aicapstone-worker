"""Worker configuration.

All settings come from environment variables so a school operator can
deploy this image with `docker compose` without editing any source. See
`.env.example` in this directory for the full list. Eval parameters
(episodes, episode length, …) are not here — they are edited in the UI
and stored in the local database (local_store.py).
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Optional


class WorkerConfig:
    """Read once at boot; changes need a container restart."""

    def __init__(self) -> None:
        # Shown in the UI header.
        self.worker_name: str = os.getenv("WORKER_NAME") or socket.gethostname()

        # Login for the UI. Empty → generated on first boot and stored in
        # STATE_DIR/admin_password (see local_ui._admin_password).
        self.admin_password: Optional[str] = os.getenv("WORKER_ADMIN_PASSWORD") or None

        # ── Local storage ─────────────────────────────────────────────
        # Policy zips, logs and videos.
        self.storage_root: Path = Path(os.getenv(
            "WORKER_STORAGE_ROOT", "/var/lib/worker-agent/storage"
        ))
        # Tasks / settings / run history (local.db) + generated password.
        # Kept separate from storage_root so wiping uploads keeps them.
        self.state_dir: Path = Path(os.getenv(
            "WORKER_STATE_DIR", "/var/lib/worker-agent/state"
        ))

        # ── GPU / runtime ─────────────────────────────────────────────
        self.gpu_id: str = os.getenv("GPU_ID", "0")
        self.isaac_sim_script: str = os.getenv(
            "ISAAC_SIM_SCRIPT_PATH", "/workspace/aicapstone/scripts/rollout.py"
        )
        # `mock` = don't call rollout.py, just return a random score (UI
        # smoke test without a GPU). `real` = run Isaac Sim.
        self.eval_mode: str = os.getenv("EVAL_MODE", "real").lower()

        # HTTP listen port inside the container.
        self.port: int = int(os.getenv("WORKER_PORT", "8080"))

    def check_or_die(self) -> None:
        """Bad config exits immediately so ops sees the problem."""
        if self.eval_mode not in ("real", "mock"):
            print(f"FATAL: EVAL_MODE must be 'real' or 'mock' (got {self.eval_mode!r})",
                  file=sys.stderr)
            sys.exit(1)
        try:
            self.storage_root.mkdir(parents=True, exist_ok=True)
            self.state_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"FATAL: cannot create storage dirs: {exc}", file=sys.stderr)
            sys.exit(1)


cfg = WorkerConfig()
