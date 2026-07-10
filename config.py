"""Worker Agent configuration.

All settings come from environment variables so a school operator can
deploy this image with `docker run -e ...` or `docker-compose` without
editing any source. See `.env.example` in this directory for the full
list plus recommended values.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


class WorkerConfig:
    """Everything the agent needs to run. Read once at boot; loops
    re-check periodically for CENTRAL_API_URL changes but static values
    (WORKER_NAME, GPU_ID) require a container restart to change.
    """

    def __init__(self) -> None:
        # ── Central control plane ─────────────────────────────────────
        # Public URL of the central FastAPI backend (frontend Caddy or
        # direct 8001 for dev).
        self.central_api_url: str = os.getenv(
            "CENTRAL_API_URL", "http://localhost:8001"
        ).rstrip("/")

        # ── Identity ──────────────────────────────────────────────────
        # WORKER_JOIN_TOKEN is required on first boot ONLY. After a
        # successful /register we cache the returned machine JWT in
        # STATE_DIR/machine_jwt so subsequent restarts skip registration.
        self.join_token: Optional[str] = os.getenv("WORKER_JOIN_TOKEN") or None
        # Friendly name shown in the admin Workers tab. Falls back to
        # hostname so a fresh container that forgot to set it isn't
        # anonymous.
        import socket
        self.worker_name: str = os.getenv("WORKER_NAME") or socket.gethostname()
        self.hostname: str = socket.gethostname()
        # What public URL do students' browsers hit for /upload/{token}?
        # Central issues presigned URLs pointing here. If this Agent is
        # behind a reverse proxy, set PUBLIC_URL to the external hostname.
        self.public_url: str = os.getenv(
            "WORKER_PUBLIC_URL",
            f"http://{self.hostname}:{int(os.getenv('WORKER_PORT', '8080'))}",
        ).rstrip("/")

        # ── Local storage ─────────────────────────────────────────────
        self.storage_root: Path = Path(os.getenv(
            "WORKER_STORAGE_ROOT", "/var/lib/worker-agent/storage"
        ))
        # Small state dir for the cached machine JWT + registration
        # metadata. Kept separate from storage_root so a "wipe storage"
        # op doesn't accidentally unregister the agent.
        self.state_dir: Path = Path(os.getenv(
            "WORKER_STATE_DIR", "/var/lib/worker-agent/state"
        ))

        # ── GPU / runtime ─────────────────────────────────────────────
        # For the mock rollout this is advisory only; the real Isaac Sim
        # rollout reads CUDA_VISIBLE_DEVICES.
        self.gpu_id: str = os.getenv("GPU_ID", "0")
        self.isaac_sim_script: str = os.getenv(
            "ISAAC_SIM_SCRIPT_PATH", "/aicapstone/scripts/rollout.py"
        )
        # `mock` = don't call rollout.py, just return a random score.
        # `real` = exec rollout.py in a subprocess. `mock` is useful for
        # smoke-testing the agent against a dev central without a GPU.
        self.eval_mode: str = os.getenv("EVAL_MODE", "mock").lower()

        # ── Loop tuning ───────────────────────────────────────────────
        self.heartbeat_interval_sec: int = int(
            os.getenv("HEARTBEAT_INTERVAL_SEC", "30")
        )
        self.job_poll_interval_sec: int = int(
            os.getenv("JOB_POLL_INTERVAL_SEC", "10")
        )
        # HTTP timeouts against central. Long enough that transient
        # slowness doesn't blip us to OFFLINE, short enough that a truly
        # dead central is noticed quickly.
        self.request_timeout_sec: int = int(
            os.getenv("REQUEST_TIMEOUT_SEC", "30")
        )
        # HTTP listen port for our own upload/download server.
        self.port: int = int(os.getenv("WORKER_PORT", "8080"))

        # ── Capabilities blob (advertised at register) ────────────────
        # Anything JSON-encodable. Central stores it verbatim on the
        # Worker row + returns it in admin listings.
        self.max_concurrent_evals: int = int(
            os.getenv("MAX_CONCURRENT_EVALS", "1")
        )
        self.allowed_task_keys: list[str] = [
            k.strip() for k in os.getenv("ALLOWED_TASK_KEYS", "").split(",") if k.strip()
        ]

    def as_capabilities(self) -> dict:
        """The `capabilities` JSON dict we advertise at register time."""
        return {
            "public_url": self.public_url,
            "max_concurrent_evals": self.max_concurrent_evals,
            "allowed_task_keys": self.allowed_task_keys or None,
            "eval_mode": self.eval_mode,
        }

    def as_gpu_info(self) -> dict:
        return {
            "gpu_id": self.gpu_id,
            "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES") or self.gpu_id,
        }

    def check_or_die(self) -> None:
        """Fail-fast validation identical in spirit to backend/app/config.py
        SECRET_KEY validator — bad config exits immediately so ops sees
        the problem instead of an agent that "works" but never registers."""
        if not self.central_api_url:
            print("FATAL: CENTRAL_API_URL is not set", file=sys.stderr)
            sys.exit(1)
        try:
            self.storage_root.mkdir(parents=True, exist_ok=True)
            self.state_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"FATAL: cannot create storage dirs: {exc}", file=sys.stderr)
            sys.exit(1)
        # No join token AND no cached machine_jwt = we can't authenticate
        # against central at all. Check inside main() so cached JWT paths
        # can prove out this branch.

    @property
    def machine_jwt_path(self) -> Path:
        return self.state_dir / "machine_jwt"

    @property
    def worker_id_path(self) -> Path:
        return self.state_dir / "worker_id"


cfg = WorkerConfig()
