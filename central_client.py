"""HTTP client to the central control plane.

Owns:
  * one-shot `register` at boot
  * long-lived `machine_jwt` in memory + on-disk state
  * `heartbeat` (every 30s)
  * `next_job` (long-poll for work)
  * `result` (terminal report per submission)

Never raises out of loop paths — callers get `None` on transient
failures + a log line. Fatal errors (invalid JWT, revoked worker) do
raise so the outer supervisor can decide to exit.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx

from worker_agent.config import cfg

log = logging.getLogger("worker.central")


class CentralError(RuntimeError):
    """Non-transient failure from central. Callers should stop retrying."""


class CentralClient:
    def __init__(self) -> None:
        self._machine_jwt: Optional[str] = None
        self._worker_id: Optional[int] = None
        self._client = httpx.Client(
            base_url=cfg.central_api_url,
            timeout=cfg.request_timeout_sec,
        )
        self._load_cached_state()

    # ── State ────────────────────────────────────────────────────────
    def _load_cached_state(self) -> None:
        try:
            if cfg.machine_jwt_path.is_file():
                self._machine_jwt = cfg.machine_jwt_path.read_text().strip() or None
            if cfg.worker_id_path.is_file():
                self._worker_id = int(cfg.worker_id_path.read_text().strip() or "0") or None
        except OSError as exc:
            log.warning("cached state read failed: %s", exc)

    def _persist_state(self) -> None:
        try:
            if self._machine_jwt:
                cfg.machine_jwt_path.write_text(self._machine_jwt)
            if self._worker_id:
                cfg.worker_id_path.write_text(str(self._worker_id))
        except OSError as exc:
            log.warning("state persist failed: %s", exc)

    @property
    def worker_id(self) -> Optional[int]:
        return self._worker_id

    @property
    def authenticated(self) -> bool:
        return self._machine_jwt is not None and self._worker_id is not None

    # ── Auth helper ──────────────────────────────────────────────────
    def _auth_headers(self) -> dict:
        if not self._machine_jwt:
            raise CentralError("no machine_jwt — need to register first")
        return {"Authorization": f"Bearer {self._machine_jwt}"}

    def authed_post(self, path: str, *, json: dict) -> httpx.Response:
        """Public helper — used by server.py's upload endpoint to POST
        `upload-complete` back to central."""
        return self._client.post(path, headers=self._auth_headers(), json=json)

    # ── Register ────────────────────────────────────────────────────
    def register(self) -> None:
        """One-shot: exchange join_token for machine_jwt.

        Idempotent from the operator's POV: if we already have a cached
        JWT that heartbeat says is valid, skip. If cached JWT is stale
        (worker revoked / re-registered elsewhere), central will 401 on
        heartbeat and we'll re-run with the fresh join_token."""
        if not cfg.join_token:
            raise CentralError(
                "WORKER_JOIN_TOKEN not set and no cached JWT — "
                "cannot authenticate to central"
            )
        body = {
            "join_token": cfg.join_token,
            "name": cfg.worker_name,
            "hostname": cfg.hostname,
            "gpu_info": cfg.as_gpu_info(),
            "capabilities": cfg.as_capabilities(),
        }
        try:
            r = self._client.post("/api/workers/register", json=body)
        except httpx.HTTPError as exc:
            raise CentralError(f"register network error: {exc}")
        if r.status_code in (401, 409, 410):
            raise CentralError(f"register refused ({r.status_code}): {r.text}")
        r.raise_for_status()
        data = r.json()
        self._machine_jwt = data["machine_jwt"]
        self._worker_id = data["worker_id"]
        self._persist_state()
        log.info(
            "registered as worker %d (school %s, code=%s)",
            self._worker_id, data["school_id"], data["school_code"],
        )

    # ── Heartbeat ────────────────────────────────────────────────────
    def heartbeat(
        self, *,
        status: str = "ONLINE",
        current_submission_id: Optional[int] = None,
        load_avg: Optional[float] = None,
        gpu_util: Optional[float] = None,
    ) -> Optional[dict]:
        """Regular ping. Returns central's response dict or None on
        transient failure. On JWT rotation, updates the cached JWT
        transparently."""
        try:
            r = self._client.post(
                "/api/workers/heartbeat",
                headers=self._auth_headers(),
                json={
                    "status": status,
                    "current_submission_id": current_submission_id,
                    "load_avg": load_avg,
                    "gpu_util": gpu_util,
                },
            )
        except httpx.HTTPError as exc:
            log.warning("heartbeat network error: %s", exc)
            return None
        if r.status_code == 401:
            # JWT was invalidated (admin revoked, or hash rotated); we
            # need to re-register. Surface the fatal so main() decides.
            self._machine_jwt = None
            self._worker_id = None
            try:
                cfg.machine_jwt_path.unlink()
            except OSError:
                pass
            raise CentralError("heartbeat 401 — machine JWT invalid, need re-register")
        if r.status_code != 200:
            log.warning("heartbeat unexpected %d: %s", r.status_code, r.text[:200])
            return None
        data = r.json()
        if data.get("rotated_machine_jwt"):
            self._machine_jwt = data["rotated_machine_jwt"]
            self._persist_state()
            log.info("machine JWT rotated by central")
        return data

    # ── Next-job ────────────────────────────────────────────────────
    def next_job(self) -> Optional[dict]:
        """Ask central for a job. Returns a dict when work is available,
        None when the queue is empty for our school (agent should back
        off and re-poll)."""
        try:
            r = self._client.post(
                "/api/workers/next-job", headers=self._auth_headers(),
            )
        except httpx.HTTPError as exc:
            log.warning("next-job network error: %s", exc)
            return None
        if r.status_code == 401:
            raise CentralError("next-job 401")
        if r.status_code != 200:
            log.warning("next-job unexpected %d: %s", r.status_code, r.text[:200])
            return None
        data = r.json()
        # Multiplexed shape: a submission has `submission_id`, a
        # config-validation job has `config_id`. If neither, the poll
        # just timed out with nothing to do.
        if not (data.get("submission_id") or data.get("config_id")):
            return None
        return data

    # ── Eval task config ────────────────────────────────────────────
    def get_task_config(self, submission_id: int) -> Optional[dict]:
        """Fetch the eval config for an assigned submission:
        `{task_name, filename, sha256, content}`. Returns None when central
        is too old to serve it (404 on the route) so the caller can fall
        back to a locally mounted /private_tasks; raises on other errors."""
        r = self._client.get(
            f"/api/workers/submissions/{submission_id}/task-config",
            headers=self._auth_headers(),
        )
        if r.status_code == 404 and "no eval config" not in r.text:
            return None
        if r.status_code != 200:
            raise CentralError(f"task-config {r.status_code}: {r.text[:200]}")
        return r.json()

    # ── Eval recording ──────────────────────────────────────────────
    def upload_video(self, submission_id: int, path) -> None:
        """Stream the rollout MP4 to central so admins can replay it.
        Raises on failure; the caller keeps the local file in that case."""
        size = path.stat().st_size

        def _chunks():
            with open(path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk

        r = self._client.post(
            f"/api/workers/submissions/{submission_id}/video",
            headers={**self._auth_headers(), "Content-Type": "video/mp4",
                     "Content-Length": str(size)},
            content=_chunks(),
            timeout=httpx.Timeout(30.0, write=600.0),
        )
        if r.status_code != 200:
            raise CentralError(f"video upload {r.status_code}: {r.text[:200]}")
        log.info("uploaded eval video sid=%d (%d bytes)", submission_id, size)

    # ── Progress (non-terminal) ─────────────────────────────────────
    def report_progress(
        self, submission_id: int, *,
        phase: Optional[str] = None,
        episode: Optional[int] = None,
        episode_total: Optional[int] = None,
        config_index: Optional[int] = None,
        config_total: Optional[int] = None,
        config_name: Optional[str] = None,
        cumulative_success_rate: Optional[float] = None,
        message: Optional[str] = None,
    ) -> None:
        """Fire-and-forget progress ping. Best-effort — a network blip
        just drops the update, we don't want a laggy central to slow the
        eval loop. Central fans this out into Redis so the student's
        status page + admin log stream see it live."""
        body = {
            "phase": phase, "episode": episode, "episode_total": episode_total,
            "config_index": config_index, "config_total": config_total,
            "config_name": config_name,
            "cumulative_success_rate": cumulative_success_rate,
            "message": message,
        }
        # Strip Nones to keep the payload small — endpoint treats missing
        # fields as "unchanged".
        body = {k: v for k, v in body.items() if v is not None}
        if not body:
            return
        try:
            resp = self._client.post(
                f"/api/workers/submissions/{submission_id}/progress",
                headers=self._auth_headers(),
                json=body,
                timeout=3.0,   # tight — we don't want to block the eval on this
            )
            if resp.status_code not in (200, 204):
                log.debug("progress ignored sid=%d code=%d", submission_id, resp.status_code)
        except Exception as exc:
            log.debug("progress post failed sid=%d: %s", submission_id, exc)

    # ── Config validation result ────────────────────────────────────
    def report_config_validation(
        self, config_id: int, *,
        status: str,
        note: Optional[str] = None,
        log_tail: Optional[str] = None,
    ) -> None:
        """Terminal report for a config-validation job. Raises on non-2xx
        so the caller can log — the outer loop already swallows
        exceptions so this won't crash the poll thread."""
        body = {"status": status, "note": note, "log_tail": log_tail}
        r = self._client.post(
            f"/api/workers/config-validations/{config_id}/result",
            headers=self._auth_headers(),
            json=body,
        )
        if r.status_code != 200:
            log.error("config-validation POST failed cid=%d code=%d body=%s",
                      config_id, r.status_code, r.text[:200])
        r.raise_for_status()
        log.info("reported config validation cid=%d status=%s", config_id, status)

    # ── Result ──────────────────────────────────────────────────────
    def report_result(
        self, submission_id: int, *,
        status: str,
        success_rate: Optional[float] = None,
        episodes: Optional[list] = None,
        error_message: Optional[str] = None,
        error_log: Optional[str] = None,
        duration_sec: Optional[float] = None,
        detected_policy_type: Optional[str] = None,
    ) -> None:
        """Terminal report. Raises on non-200 so caller can log +
        potentially re-try. Central is idempotent-ish (rejects a second
        report on the same row), so we don't infinite-loop retry here."""
        body = {
            "status": status,
            "success_rate": success_rate,
            "episodes": episodes,
            "error_message": error_message,
            "error_log": error_log,
            "duration_sec": duration_sec,
            "detected_policy_type": detected_policy_type,
        }
        r = self._client.post(
            f"/api/workers/submissions/{submission_id}/result",
            headers=self._auth_headers(),
            json=body,
        )
        if r.status_code not in (200, 201):
            log.error(
                "result POST failed sid=%d status=%d body=%s",
                submission_id, r.status_code, r.text[:200],
            )
        r.raise_for_status()
        log.info("reported result sid=%d status=%s rate=%s",
                 submission_id, status, success_rate)


# Module-level singleton — the FastAPI upload endpoint + background
# loops share it.
client = CentralClient()
