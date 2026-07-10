"""FastAPI HTTP surface the Worker Agent exposes.

Students' browsers hit these URLs directly — central issued them a
presigned URL like `https://gpu-01.school-x.tw/upload/<token>`. The
agent verifies the token via `storage.redeem_token()` then commits the
bytes to its own local disk.

Endpoints:
  * `POST /upload/{token}` — receive one submission's zip
  * `GET  /download/{token}` — serve a stored zip (or video) back
  * `GET  /health` — liveness probe for the school's monitoring

CORS: permissive (`*`) because central issues URLs to whichever school
domain the student's browser will connect from — the agent doesn't
know the origin ahead of time. The presigned token is the only real
guard.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from worker_agent.central_client import client
from worker_agent.config import cfg
from worker_agent.storage import (
    compute_policy_id, compute_zip_hash, redeem_token, submission_dir,
    video_path_for, zip_path_for,
)

log = logging.getLogger("worker.server")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Capstone Worker Agent",
        version="1.0.0",
        docs_url="/docs" if cfg.eval_mode == "mock" else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,  # no cookies expected; presigned URL owns auth
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "worker_id": client.worker_id,
            "authenticated": client.authenticated,
            "storage_root": str(cfg.storage_root),
        }

    @app.post("/upload/{token}")
    async def upload_submission(
        token: str,
        request: Request,
        file: UploadFile = File(...),
    ):
        """Receive the student's zip, hash it as it lands, then tell
        central the upload is complete + hand over the policy_sha256.

        `submission_id` embedded in the token record via storage.redeem
        — for TOFU tokens, we accept the file but flag the mismatch."""
        record = redeem_token(token)
        if record is None:
            raise HTTPException(status_code=401, detail="invalid, expired, or already-redeemed token")

        sid_from_token = record.get("submission_id")
        # Read submission id from a form field if the token record didn't
        # have one (TOFU path). Central always includes it in the URL
        # query for its own accounting; here we accept it as form data.
        form = await request.form()
        sid_form = form.get("submission_id")
        try:
            sid = int(sid_from_token or sid_form or 0)
        except (TypeError, ValueError):
            sid = 0
        if sid <= 0:
            raise HTTPException(status_code=400, detail="submission_id missing")

        # Stream to disk. bounded at 6 GB matching central MAX_ZIP_BYTES.
        MAX = 6 * 1024 * 1024 * 1024
        tmp_path = submission_dir(sid) / "pretrained_model.zip.part"
        final = zip_path_for(sid)
        total = 0
        with tmp_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX:
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="upload exceeds 6 GiB")
                out.write(chunk)
        tmp_path.rename(final)

        # Verify + tell central.
        zip_sha = compute_zip_hash(final)
        policy_sha = compute_policy_id(final)
        if policy_sha is None:
            raise HTTPException(status_code=400, detail="zip did not contain the required policy files")

        upload_complete_body = {
            "upload_token": token,
            "size_bytes": total,
            "policy_sha256": policy_sha,
            "zip_sha256": zip_sha,
            "local_reference": {
                "worker_id": client.worker_id,
                "path": str(final),
                "size_bytes": total,
                "uploaded_at": None,  # central stamps its own timestamp
                "sha256": zip_sha,
            },
        }
        # POST via central_client's authed HTTP client.
        r = client.authed_post(
            f"/api/submissions/{sid}/upload-complete",
            json=upload_complete_body,
        )
        if r.status_code not in (200, 201):
            log.error("upload-complete rejected by central: %d %s",
                      r.status_code, r.text[:200])
            raise HTTPException(status_code=502, detail=f"central rejected upload: {r.text[:200]}")
        return JSONResponse({
            "submission_id": sid,
            "size_bytes": total,
            "policy_sha256": policy_sha,
        })

    @app.get("/download/{token}")
    def download_submission(token: str):
        record = redeem_token(token)
        if record is None:
            raise HTTPException(status_code=401, detail="invalid, expired, or already-redeemed token")
        sid = record.get("submission_id") or 0
        if sid <= 0:
            raise HTTPException(status_code=400, detail="submission_id missing from token")
        path = zip_path_for(int(sid))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="archive not on this worker")
        return FileResponse(
            path,
            filename=f"submission_{sid}_pretrained_model.zip",
            media_type="application/zip",
        )

    @app.get("/video/{token}")
    def download_video(token: str):
        record = redeem_token(token)
        if record is None:
            raise HTTPException(status_code=401, detail="invalid token")
        sid = record.get("submission_id") or 0
        if sid <= 0:
            raise HTTPException(status_code=400, detail="submission_id missing")
        path = video_path_for(int(sid))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="no video for this submission")
        return FileResponse(path, media_type="video/mp4")

    return app


app = create_app()
