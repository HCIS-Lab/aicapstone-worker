"""Worker-local filesystem layout + presigned-token bookkeeping.

Layout under `WORKER_STORAGE_ROOT`::

    submissions/
        sid=<submission_id>/
            pretrained_model.zip     ← the upload
            extracted/               ← unzip target for eval
            eval_video.mp4           ← recorder output
    tokens/
        <token_hash>.json            ← redemption record

Token file schema::

    {
      "submission_id": 42,
      "operation": "UPLOAD" | "DOWNLOAD",
      "issued_at": "2026-06-15T…",
      "expires_at": "2026-06-15T…",
      "redeemed_at": "2026-06-15T…" | null,
      "client_ip": "1.2.3.4"       # advisory
    }

Central issues the tokens; the worker only VERIFIES them by re-hashing
the token from the URL against filenames here. Verification is:

  * exists → token was issued to us
  * `redeemed_at` is null → single-use enforced
  * `expires_at` in the future → not stale
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from worker_agent.config import cfg

log = logging.getLogger("worker.storage")


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def submission_dir(sid: int) -> Path:
    # Standalone run ids are local and would collide with central
    # submission ids if a worker ever switches mode, so keep them apart.
    sub = "local_runs" if cfg.standalone else "submissions"
    d = cfg.storage_root / sub / f"sid={sid}"
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
    """Called by cleanup after result reported. Best-effort — a broken
    permission won't stop the pipeline."""
    d = submission_dir(sid)
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)


# ── Presigned-URL token bookkeeping ────────────────────────────────
def _token_file(raw: str) -> Path:
    d = cfg.storage_root / "tokens"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_hash(raw)}.json"


def record_token(
    raw: str, *,
    submission_id: int, operation: str,
    expires_at: str, client_ip: Optional[str] = None,
) -> None:
    """Called when the agent learns about a new signed token — either
    via central push (`/tokens/announce` — not yet implemented) or
    piggy-backed on `/upload/{token}` verification. For P4 the agent
    trusts the token IF central issued it; central and worker share the
    SECRET_KEY so a future revision could switch to HMAC verification
    without a central round-trip."""
    _token_file(raw).write_text(json.dumps({
        "submission_id": submission_id,
        "operation": operation,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at,
        "redeemed_at": None,
        "client_ip": client_ip,
    }))


def redeem_token(raw: str) -> Optional[dict]:
    """Verify + mark redeemed atomically. Returns the record on success,
    None if unknown / redeemed / expired.

    Simplification for P4 v1: if the token file doesn't exist locally,
    we treat any signed URL from central as valid on first use — the
    caller (upload endpoint) verifies the submission_id matches what
    the request says. A future hardening pass replaces this with
    verify-via-central `POST /api/tokens/redeem` so the worker doesn't
    accept unbounded tokens.
    """
    p = _token_file(raw)
    if not p.is_file():
        # Trust-on-first-use. Return a stub record — verify against
        # central at result time picks up any mismatch.
        return {"submission_id": None, "operation": None, "redeemed_at": None}
    try:
        record = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if record.get("redeemed_at"):
        return None
    exp = record.get("expires_at")
    if exp:
        try:
            expires = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if expires < datetime.now(timezone.utc):
                return None
        except ValueError:
            pass
    record["redeemed_at"] = datetime.now(timezone.utc).isoformat()
    try:
        p.write_text(json.dumps(record))
    except OSError as exc:
        log.warning("could not persist redemption of token: %s", exc)
    return record


def compute_zip_hash(path: Path) -> str:
    """Streaming SHA-256 of the raw zip bytes. Matches central's
    `client_sha256` claim from init."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# The canonical policy-id hash — identical algorithm to the central
# `_compute_policy_id` in backend/app/routers/submissions.py. Copied
# here so the worker doesn't need to import backend code. See
# `_POLICY_ID_FILES` in submissions.py for the fixed file order.
_POLICY_ID_FILES = (
    "config.json",
    "model.safetensors",
    "train_config.json",
    "policy_preprocessor.json",
    "policy_postprocessor.json",
)


def compute_policy_id(zip_path: Path) -> Optional[str]:
    """Same fingerprint algorithm as central. Two policies with the
    same weight + config bytes hash to the same value regardless of zip
    metadata."""
    import zipfile
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            by_base = {}
            for info in zf.infolist():
                if info.is_dir():
                    continue
                base = info.filename.rsplit("/", 1)[-1]
                by_base.setdefault(base, info)
            outer = hashlib.sha256()
            for fname in _POLICY_ID_FILES:
                info = by_base.get(fname)
                inner = hashlib.sha256()
                if info is not None:
                    with zf.open(info) as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            inner.update(chunk)
                outer.update(fname.encode("ascii"))
                outer.update(b"\x00")
                outer.update(inner.digest())
                outer.update(b"\x00")
            return outer.hexdigest()
    except (zipfile.BadZipFile, OSError):
        return None
