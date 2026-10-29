"""Standalone-mode web UI + JSON API, mounted on the worker's own port.

Everything a school needs without central: define eval tasks (built-in
simulator tasks or their own eval config .py), set eval settings, upload
policy zips, watch the queue / live log, replay videos.

Auth is a single admin password (WORKER_ADMIN_PASSWORD, or generated on
first boot into STATE_DIR/admin_password) exchanged for an HttpOnly
session cookie.
"""
from __future__ import annotations

import ast
import hmac
import logging
import re
import secrets
import shutil
import time
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile,
)
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from worker_agent import local_runner
from worker_agent.config import cfg
from worker_agent.local_store import DEFAULT_SETTINGS, OVERRIDE_KEYS, get_store
from worker_agent.storage import submission_dir, video_path_for, zip_path_for

log = logging.getLogger("worker.ui")

_UI_FILE = Path(__file__).parent / "ui" / "index.html"
_COOKIE = "wa_session"
_SESSION_TTL = 7 * 24 * 3600
_MAX_ZIP = 6 * 1024 * 1024 * 1024
_MAX_TASK_SRC = 1024 * 1024
_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")
_GYM_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$")
# Same rule as central's REQUIRED_FILES check: names anywhere in the zip.
_REQUIRED_FILES = {"config.json", "model.safetensors"}

_sessions: dict[str, float] = {}


def _admin_password() -> str:
    if cfg.admin_password:
        return cfg.admin_password
    p = cfg.state_dir / "admin_password"
    if not p.is_file():
        p.write_text(secrets.token_urlsafe(12))
        p.chmod(0o600)
    return p.read_text().strip()


def announce_password() -> None:
    """Log where the login comes from so the operator can find it."""
    if cfg.admin_password:
        log.info("UI login: password from WORKER_ADMIN_PASSWORD")
    else:
        log.warning("UI login password (generated, stored in %s): %s",
                    cfg.state_dir / "admin_password", _admin_password())


def require_login(request: Request) -> None:
    tok = request.cookies.get(_COOKIE)
    exp = _sessions.get(tok or "")
    if not exp or exp < time.time():
        raise HTTPException(status_code=401, detail="login required")


def _check_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400,
                            detail="task name: letters, digits, _ . - (max 64)")
    return name


def _clean_overrides(raw: Optional[dict]) -> dict:
    out = {}
    for k in OVERRIDE_KEYS:
        v = (raw or {}).get(k)
        if v in (None, ""):
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{k} must be a number")
        if v <= 0:
            raise HTTPException(status_code=400, detail=f"{k} must be > 0")
        out[k] = int(v) if k == "eval_rounds" else v
    return out


class LoginBody(BaseModel):
    password: str


class TaskBody(BaseModel):
    gym_id: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None
    overrides: Optional[dict] = None


def build_router() -> APIRouter:
    r = APIRouter()
    auth = [Depends(require_login)]

    @r.get("/", include_in_schema=False)
    def index():
        return FileResponse(_UI_FILE, media_type="text/html")

    # ── Session ──────────────────────────────────────────────────────
    @r.post("/api/login")
    def login(body: LoginBody, response: Response):
        if not hmac.compare_digest(body.password.encode(), _admin_password().encode()):
            time.sleep(1)  # slow down guessing
            raise HTTPException(status_code=401, detail="wrong password")
        tok = secrets.token_urlsafe(32)
        _sessions[tok] = time.time() + _SESSION_TTL
        response.set_cookie(_COOKIE, tok, max_age=_SESSION_TTL,
                            httponly=True, samesite="strict")
        return {"ok": True}

    @r.post("/api/logout")
    def logout(request: Request, response: Response):
        _sessions.pop(request.cookies.get(_COOKIE, ""), None)
        response.delete_cookie(_COOKIE)
        return {"ok": True}

    @r.get("/api/me", dependencies=auth)
    def me():
        return {"worker_name": cfg.worker_name, "eval_mode": cfg.eval_mode,
                "gpu_id": cfg.gpu_id}

    # ── Settings ─────────────────────────────────────────────────────
    @r.get("/api/settings", dependencies=auth)
    def get_settings():
        return get_store().get_settings()

    @r.put("/api/settings", dependencies=auth)
    def put_settings(body: dict):
        clean = {}
        for k, v in body.items():
            if k not in DEFAULT_SETTINGS:
                continue
            if k == "record_video":
                clean[k] = bool(v)
            elif k == "device":
                if not re.match(r"^(cpu|cuda(:\d+)?)$", str(v)):
                    raise HTTPException(status_code=400, detail="device: cpu, cuda or cuda:N")
                clean[k] = str(v)
            elif k == "action_horizon" and v in (None, ""):
                clean[k] = None
            else:
                try:
                    num = float(v)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"{k} must be a number")
                if num < 0 or (num == 0 and k != "timeout_sec"):
                    raise HTTPException(status_code=400, detail=f"{k} out of range")
                clean[k] = num if k == "episode_length_s" else int(num)
        return get_store().put_settings(clean)

    # ── Tasks ────────────────────────────────────────────────────────
    @r.get("/api/tasks", dependencies=auth)
    def list_tasks():
        return get_store().list_tasks()

    @r.get("/api/tasks/{name}", dependencies=auth)
    def get_task(name: str):
        t = get_store().get_task(name)
        if t is None:
            raise HTTPException(status_code=404, detail="no such task")
        return t

    @r.put("/api/tasks/{name}", dependencies=auth)
    def put_task(name: str, body: TaskBody):
        _check_name(name)
        gym_id = (body.gym_id or "").strip() or None
        content = body.content if body.content and body.content.strip() else None
        if bool(gym_id) == bool(content):
            raise HTTPException(status_code=400,
                                detail="give either a built-in gym id or an eval config .py")
        if gym_id and not _GYM_RE.match(gym_id):
            raise HTTPException(status_code=400, detail="invalid gym id")
        if content:
            if len(content.encode()) > _MAX_TASK_SRC:
                raise HTTPException(status_code=413, detail="config larger than 1 MB")
            try:
                ast.parse(content)
            except SyntaxError as exc:
                raise HTTPException(status_code=400,
                                    detail=f"Python syntax error line {exc.lineno}: {exc.msg}")
        return get_store().put_task(name, gym_id=gym_id, content=content,
                                    description=body.description,
                                    overrides=_clean_overrides(body.overrides))

    @r.delete("/api/tasks/{name}", dependencies=auth)
    def delete_task(name: str):
        get_store().delete_task(name)
        return {"ok": True}

    # ── Runs ─────────────────────────────────────────────────────────
    def _run_or_404(rid: int) -> dict:
        run = get_store().get_run(rid)
        if run is None:
            raise HTTPException(status_code=404, detail="no such run")
        return run

    @r.get("/api/runs", dependencies=auth)
    def list_runs():
        runs = get_store().list_runs()
        for run in runs:
            run["has_video"] = video_path_for(run["id"]).is_file()
            run["has_zip"] = zip_path_for(run["id"]).is_file()
        return {"current": local_runner.current_run(), "runs": runs}

    @r.post("/api/runs", dependencies=auth)
    async def create_run(
        file: UploadFile = File(...),
        task_name: str = Form(...),
        label: str = Form(""),
        eval_rounds: str = Form(""),
        episode_length_s: str = Form(""),
    ):
        store = get_store()
        if store.get_task(task_name) is None:
            raise HTTPException(status_code=400, detail=f"unknown task '{task_name}'")
        overrides = _clean_overrides({"eval_rounds": eval_rounds,
                                      "episode_length_s": episode_length_s})
        rid = store.create_run(task_name=task_name, label=label.strip() or None,
                               overrides=overrides)
        # Not claimable until the zip is in place.
        store.update_run(rid, status="UPLOADING")
        tmp = submission_dir(rid) / "pretrained_model.zip.part"
        total = 0
        try:
            with tmp.open("wb") as out:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > _MAX_ZIP:
                        raise HTTPException(status_code=413, detail="upload exceeds 6 GiB")
                    out.write(chunk)
            try:
                with zipfile.ZipFile(tmp) as zf:
                    names = {n.rsplit("/", 1)[-1] for n in zf.namelist() if not n.endswith("/")}
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="not a zip file")
            missing = _REQUIRED_FILES - names
            if missing:
                raise HTTPException(status_code=400,
                                    detail=f"zip is missing {sorted(missing)}")
        except BaseException:
            store.delete_run(rid)
            shutil.rmtree(submission_dir(rid), ignore_errors=True)
            raise
        tmp.rename(zip_path_for(rid))
        store.update_run(rid, status="QUEUED", zip_name=file.filename, zip_size=total)
        return store.get_run(rid)

    @r.get("/api/runs/{rid}/log", dependencies=auth)
    def run_log(rid: int, tail: int = 300):
        _run_or_404(rid)
        p = local_runner.log_path_for(rid)
        if not p.is_file():
            return PlainTextResponse("")
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        return PlainTextResponse("\n".join(lines[-max(1, min(tail, 5000)):]))

    @r.get("/api/runs/{rid}/video", dependencies=auth)
    def run_video(rid: int):
        _run_or_404(rid)
        p = video_path_for(rid)
        if not p.is_file():
            raise HTTPException(status_code=404, detail="no video for this run")
        return FileResponse(p, media_type="video/mp4")

    @r.post("/api/runs/{rid}/rerun", dependencies=auth)
    def rerun(rid: int):
        run = _run_or_404(rid)
        if run["status"] in ("QUEUED", "RUNNING", "UPLOADING"):
            raise HTTPException(status_code=409, detail="run is not finished")
        if not zip_path_for(rid).is_file():
            raise HTTPException(status_code=410, detail="policy zip is gone")
        video_path_for(rid).unlink(missing_ok=True)
        get_store().update_run(rid, status="QUEUED", phase=None, error_message=None,
                               success_rate=None, finished_at=None)
        return get_store().get_run(rid)

    @r.post("/api/runs/{rid}/cancel", dependencies=auth)
    def cancel(rid: int):
        run = _run_or_404(rid)
        if run["status"] == "QUEUED":
            get_store().update_run(rid, status="FAILED", error_message="cancelled")
            local_runner.cancel(rid)  # in case the loop claimed it meanwhile
        elif not local_runner.cancel(rid):
            raise HTTPException(status_code=409, detail="run is not active")
        return {"ok": True}

    @r.delete("/api/runs/{rid}", dependencies=auth)
    def delete_run(rid: int):
        run = _run_or_404(rid)
        if run["status"] in ("RUNNING", "UPLOADING"):
            raise HTTPException(status_code=409, detail="cancel the run first")
        get_store().delete_run(rid)
        shutil.rmtree(submission_dir(rid), ignore_errors=True)
        return {"ok": True}

    return r
