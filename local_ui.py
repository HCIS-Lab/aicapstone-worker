"""Web UI + JSON API, served on the worker's own port.

Everything a school needs: define eval tasks (built-in
simulator tasks or their own eval config .py), set eval settings, upload
policy zips, watch the queue / live log, replay videos.

The UI is the Vue app in frontend/, built into ui/ by the Docker build
(`npm run build`); this module serves it with an SPA fallback so deep
links like /runs/12 load index.html.

Two roles share one login form, exchanged for an HttpOnly session cookie:
  * admin — username `admin`, password WORKER_ADMIN_PASSWORD (or generated
    on first boot into STATE_DIR/admin_password). Everything.
  * group — student accounts the admin creates. Submit to their assigned
    task within the daily quota, see their own runs (no log, video or
    settings) and the leaderboard.
"""
from __future__ import annotations

import ast
import hashlib
import hmac
import logging
import re
import secrets
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile,
)
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from worker_agent import local_runner
from worker_agent.config import cfg
from worker_agent.local_store import DEFAULT_SETTINGS, OVERRIDE_KEYS, get_store
from worker_agent.storage import submission_dir, video_path_for, zip_path_for

log = logging.getLogger("worker.ui")

_UI_DIR = Path(__file__).parent / "ui"
_COOKIE = "wa_session"
_SESSION_TTL = 7 * 24 * 3600
_MAX_ZIP = 6 * 1024 * 1024 * 1024
_MAX_TASK_SRC = 1024 * 1024
_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")
_GYM_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$")
_USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$")
_ADMIN_USER = "admin"
_PBKDF2_ITERS = 200_000
# Required policy files, matched by name anywhere in the zip.
_REQUIRED_FILES = {"config.json", "model.safetensors"}
# Fields of a run a group may see. Logs, videos and the settings snapshot
# stay admin-only: the log can echo task internals.
_GROUP_RUN_FIELDS = (
    "id", "task_name", "status", "phase", "episode", "episode_total",
    "success_rate", "policy_type", "duration_sec", "error_message",
    "created_at", "started_at", "finished_at", "zip_name", "zip_size",
    "queue_position", "owner",
)


@dataclass(frozen=True)
class Principal:
    username: str
    user_id: Optional[int]  # None = admin

    @property
    def is_admin(self) -> bool:
        return self.user_id is None


_sessions: dict[str, tuple[float, Principal]] = {}


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


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _PBKDF2_ITERS)
    return f"pbkdf2_sha256${_PBKDF2_ITERS}${salt.hex()}${dk.hex()}"


def _verify_password(pw: str, stored: str) -> bool:
    try:
        _, iters, salt, want = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(iters))
    except ValueError:
        return False
    return hmac.compare_digest(dk.hex(), want)


def _drop_sessions(user_id: int) -> None:
    for tok, (_, p) in list(_sessions.items()):
        if p.user_id == user_id:
            _sessions.pop(tok, None)


def current_user(request: Request) -> Principal:
    entry = _sessions.get(request.cookies.get(_COOKIE) or "")
    if not entry or entry[0] < time.time():
        raise HTTPException(status_code=401, detail="login required")
    return entry[1]


def require_admin(user: Principal = Depends(current_user)) -> Principal:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    return user


def _quota_window_start() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")


def _group_stats(user_id: int) -> dict:
    store = get_store()
    quota = int(store.get_settings().get("daily_quota") or 0)
    used = store.submissions_since(user_id, _quota_window_start())
    best, rank, total = None, None, 0
    u = store.get_user(user_id)
    for board in store.leaderboard():
        if u and u["assigned_task"] not in (None, board["task"]):
            continue
        for e in board["rows"]:
            if e["user_id"] == user_id and e["success_rate"] is not None and (
                    best is None or e["success_rate"] > best):
                best, rank, total = e["success_rate"], e["rank"], len(board["rows"])
    return {"daily_quota": quota, "submissions_today": used,
            "remaining": None if quota == 0 else max(0, quota - used),
            "best_score": best, "rank": rank, "total_groups": total}


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
    username: str = _ADMIN_USER
    password: str


class UserBody(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    assigned_task: Optional[str] = None


class TaskBody(BaseModel):
    gym_id: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None
    overrides: Optional[dict] = None


def _with_file_flags(runs: list[dict]) -> list[dict]:
    """Add has_video / has_zip and, for QUEUED runs, the queue position
    (the run loop claims the lowest id first)."""
    queued = sorted(r["id"] for r in get_store().list_runs() if r["status"] == "QUEUED")
    for run in runs:
        run["has_video"] = video_path_for(run["id"]).is_file()
        run["has_zip"] = zip_path_for(run["id"]).is_file()
        run["queue_position"] = (queued.index(run["id"]) + 1
                                 if run["status"] == "QUEUED" else None)
    return runs


def mount_ui(app) -> None:
    """Serve the built Vue app. Call after all API routes are registered:
    the catch-all returns index.html for any other GET."""
    index = _UI_DIR / "index.html"
    if (_UI_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_UI_DIR / "assets"), name="ui-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        f = (_UI_DIR / path).resolve()
        if path and f.is_file() and f.is_relative_to(_UI_DIR.resolve()):
            return FileResponse(f)
        if not index.is_file():
            return PlainTextResponse(
                "UI not built: run `npm ci && npm run build` in frontend/ "
                "and copy dist/ to ui/ (the Docker build does this).", status_code=503)
        return FileResponse(index, media_type="text/html",
                            headers={"Cache-Control": "no-cache"})


def _group_view(run: dict) -> dict:
    return {k: run.get(k) for k in _GROUP_RUN_FIELDS}


def build_router() -> APIRouter:
    r = APIRouter()
    auth = [Depends(require_admin)]

    # ── Session ──────────────────────────────────────────────────────
    @r.post("/api/login")
    def login(body: LoginBody, response: Response):
        name = body.username.strip()
        principal = None
        if name.lower() == _ADMIN_USER:
            if hmac.compare_digest(body.password.encode(), _admin_password().encode()):
                principal = Principal(_ADMIN_USER, None)
        else:
            u = get_store().get_user_auth(name)
            if u and _verify_password(body.password, u["password_hash"]):
                principal = Principal(u["username"], u["id"])
        if principal is None:
            time.sleep(1)  # slow down guessing
            raise HTTPException(status_code=401, detail="wrong name or password")
        tok = secrets.token_urlsafe(32)
        _sessions[tok] = (time.time() + _SESSION_TTL, principal)
        response.set_cookie(_COOKIE, tok, max_age=_SESSION_TTL,
                            httponly=True, samesite="strict")
        return {"ok": True, "username": principal.username, "is_admin": principal.is_admin}

    @r.post("/api/logout")
    def logout(request: Request, response: Response):
        _sessions.pop(request.cookies.get(_COOKIE, ""), None)
        response.delete_cookie(_COOKIE)
        return {"ok": True}

    @r.get("/api/me")
    def me(user: Principal = Depends(current_user)):
        out = {"username": user.username, "is_admin": user.is_admin,
               "worker_name": cfg.worker_name, "eval_mode": cfg.eval_mode}
        if user.is_admin:
            out["gpu_id"] = cfg.gpu_id
        else:
            u = get_store().get_user(user.user_id)
            if u is None:  # deleted while logged in
                raise HTTPException(status_code=401, detail="account removed")
            out["assigned_task"] = u["assigned_task"]
        return out

    @r.get("/api/me/stats")
    def my_stats(user: Principal = Depends(current_user)):
        if user.is_admin:
            raise HTTPException(status_code=404, detail="admins have no group stats")
        return _group_stats(user.user_id)

    @r.get("/api/leaderboard")
    def leaderboard(user: Principal = Depends(current_user)):
        boards = get_store().leaderboard()
        for b in boards:
            for e in b["rows"]:
                # Groups open only their own runs.
                e["mine"] = e["user_id"] == user.user_id
                if not (user.is_admin or e["mine"]):
                    e["run_id"] = None
                e.pop("user_id")
        return boards

    # ── Groups (student accounts) ────────────────────────────────────
    def _task_or_none(name: Optional[str]) -> Optional[str]:
        name = (name or "").strip() or None
        if name and get_store().get_task(name) is None:
            raise HTTPException(status_code=400, detail=f"unknown task '{name}'")
        return name

    def _check_password(pw: str) -> str:
        if len(pw) < 6:
            raise HTTPException(status_code=400, detail="password: at least 6 characters")
        return pw

    @r.get("/api/users", dependencies=auth)
    def list_users():
        store = get_store()
        since = _quota_window_start()
        runs = store.list_runs(limit=100000)
        out = []
        for u in store.list_users():
            mine = [x for x in runs if x["user_id"] == u["id"]]
            scores = [x["success_rate"] for x in mine
                      if x["status"] == "FINISHED" and x["success_rate"] is not None]
            out.append({**u, "submissions": len(mine),
                        "submissions_today": store.submissions_since(u["id"], since),
                        "best_score": max(scores, default=None),
                        "last_submission": mine[0]["created_at"] if mine else None})
        return out

    @r.post("/api/users", dependencies=auth)
    def create_user(body: UserBody):
        name = (body.username or "").strip()
        if not _USER_RE.match(name) or name.lower() == _ADMIN_USER:
            raise HTTPException(status_code=400,
                                detail="group name: letters, digits, space _ . - (max 40), not 'admin'")
        store = get_store()
        if store.get_user_auth(name):
            raise HTTPException(status_code=409, detail=f"'{name}' already exists")
        pw = _check_password(body.password) if body.password else secrets.token_urlsafe(8)
        uid = store.create_user(name, hash_password(pw), _task_or_none(body.assigned_task))
        # The only time the password is returned; it is stored hashed.
        return {**store.get_user(uid), "password": pw}

    @r.put("/api/users/{uid}", dependencies=auth)
    def update_user(uid: int, body: UserBody):
        store = get_store()
        if store.get_user(uid) is None:
            raise HTTPException(status_code=404, detail="no such group")
        fields = {}
        if "assigned_task" in body.model_fields_set:
            fields["assigned_task"] = _task_or_none(body.assigned_task)
        if body.password:
            fields["password_hash"] = hash_password(_check_password(body.password))
            _drop_sessions(uid)
        store.update_user(uid, **fields)
        return store.get_user(uid)

    @r.delete("/api/users/{uid}", dependencies=auth)
    def delete_user(uid: int):
        # Their runs stay (with the owner name) for the record.
        get_store().delete_user(uid)
        _drop_sessions(uid)
        return {"ok": True}

    # ── Settings ─────────────────────────────────────────────────────
    @r.get("/api/settings", dependencies=auth)
    def get_settings():
        return get_store().get_settings()

    @r.get("/api/settings/defaults", dependencies=auth)
    def get_default_settings():
        return DEFAULT_SETTINGS

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
                if num < 0 or (num == 0 and k not in ("timeout_sec", "daily_quota")):
                    raise HTTPException(status_code=400, detail=f"{k} out of range")
                clean[k] = num if k == "episode_length_s" else int(num)
        return get_store().put_settings(clean)

    # ── Tasks ────────────────────────────────────────────────────────
    @r.get("/api/tasks")
    def list_tasks(user: Principal = Depends(current_user)):
        tasks = get_store().list_tasks()
        if not user.is_admin:
            tasks = [{k: t[k] for k in ("name", "description", "kind")} for t in tasks]
        return tasks

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

    @r.get("/api/runs")
    def list_runs(user: Principal = Depends(current_user)):
        if user.is_admin:
            runs = _with_file_flags(get_store().list_runs())
            return {"current": local_runner.current_run(), "runs": runs}
        runs = _with_file_flags(get_store().list_runs(user_id=user.user_id))
        return {"runs": [_group_view(x) for x in runs]}

    @r.get("/api/runs/{rid}")
    def get_run(rid: int, user: Principal = Depends(current_user)):
        run = _run_or_404(rid)
        if not user.is_admin and run["user_id"] != user.user_id:
            raise HTTPException(status_code=404, detail="no such run")
        run = _with_file_flags([run])[0]
        return run if user.is_admin else _group_view(run)

    @r.post("/api/runs")
    async def create_run(
        file: UploadFile = File(...),
        task_name: str = Form(...),
        label: str = Form(""),
        eval_rounds: str = Form(""),
        episode_length_s: str = Form(""),
        user: Principal = Depends(current_user),
    ):
        store = get_store()
        if store.get_task(task_name) is None:
            raise HTTPException(status_code=400, detail=f"unknown task '{task_name}'")
        if user.is_admin:
            overrides = _clean_overrides({"eval_rounds": eval_rounds,
                                          "episode_length_s": episode_length_s})
        else:
            u = store.get_user(user.user_id)
            if u is None:
                raise HTTPException(status_code=401, detail="account removed")
            if u["assigned_task"] and task_name != u["assigned_task"]:
                raise HTTPException(status_code=403,
                                    detail=f"your group is assigned to '{u['assigned_task']}'")
            stats = _group_stats(user.user_id)
            if stats["remaining"] == 0:
                raise HTTPException(status_code=429,
                                    detail=f"daily quota used ({stats['daily_quota']} per 24 h)")
            overrides, label = {}, ""  # groups can't change how they are graded
        rid = store.create_run(task_name=task_name, label=label.strip() or None,
                               overrides=overrides, user_id=user.user_id,
                               owner=user.username)
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
        run = store.get_run(rid)
        return run if user.is_admin else _group_view(run)

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
