"""Persistence: tasks, eval settings and runs.

The school decides which tasks exist, how many episodes, how long each
episode lasts; it all lives in one SQLite file under WORKER_STATE_DIR
(survives container recreation via the state volume).

Effective settings for a run resolve as: run override > task override >
global settings > DEFAULT_SETTINGS.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from worker_agent.config import cfg

DEFAULT_SETTINGS: dict[str, Any] = {
    "eval_rounds": 50,
    "episode_length_s": 60,
    "timeout_sec": 10800,      # 0 = no total-time limit
    "device": "cuda:0",
    "record_video": True,
    "action_horizon": None,    # None = from the checkpoint / per-policy default
}

# Tasks that ship with the simulator package; `--task` takes the gym id
# directly, no config file needed. Schools add their own as .py configs.
BUILTIN_TASKS = {
    "cup_stacking": "HCIS-CupStacking-SingleArm-v0",
    "cutlery_arrangement": "HCIS-CutleryArrangement-SingleArm-v0",
    "toy_blocks_collection": "HCIS-ToyBlocksCollection-SingleArm-v0",
}

# Per-task and per-run overrides of the global settings.
OVERRIDE_KEYS = ("eval_rounds", "episode_length_s")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    name        TEXT PRIMARY KEY,
    gym_id      TEXT,              -- built-in task, or NULL for a config file
    content     TEXT,              -- eval config .py source
    description TEXT,
    overrides   TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    label         TEXT,
    task_name     TEXT NOT NULL,
    status        TEXT NOT NULL,   -- UPLOADING / QUEUED / RUNNING / FINISHED / FAILED
    overrides     TEXT NOT NULL DEFAULT '{}',
    settings      TEXT,            -- effective settings snapshot at start
    zip_name      TEXT,
    zip_size      INTEGER,
    phase         TEXT,
    episode       INTEGER,
    episode_total INTEGER,
    success_rate  REAL,
    policy_type   TEXT,
    duration_sec  REAL,
    error_message TEXT,
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LocalStore:
    def __init__(self) -> None:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(cfg.state_dir / "local.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)
            for name, gym_id in BUILTIN_TASKS.items():
                self._db.execute(
                    "INSERT OR IGNORE INTO tasks (name, gym_id, description, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (name, gym_id, "built-in simulator task", _now()),
                )
            # A run can't still be going after a restart; its Isaac Sim
            # process (or upload) died with the old container.
            self._db.execute(
                "UPDATE runs SET status='FAILED', error_message='worker restarted during run', "
                "phase=NULL, finished_at=? WHERE status IN ('RUNNING', 'UPLOADING')", (_now(),),
            )

    def _q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def _x(self, sql: str, args: tuple = ()) -> int:
        with self._lock, self._db:
            return self._db.execute(sql, args).lastrowid

    # ── Settings ─────────────────────────────────────────────────────
    def get_settings(self) -> dict:
        out = dict(DEFAULT_SETTINGS)
        for row in self._q("SELECT key, value FROM settings"):
            if row["key"] in out:
                out[row["key"]] = json.loads(row["value"])
        return out

    def put_settings(self, values: dict) -> dict:
        with self._lock, self._db:
            for k, v in values.items():
                if k in DEFAULT_SETTINGS:
                    self._db.execute(
                        "INSERT INTO settings (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (k, json.dumps(v)),
                    )
        return self.get_settings()

    # ── Tasks ────────────────────────────────────────────────────────
    @staticmethod
    def _task_out(row: dict, with_content: bool) -> dict:
        row["overrides"] = json.loads(row["overrides"] or "{}")
        row["kind"] = "builtin" if row["gym_id"] else "config"
        if not with_content:
            row.pop("content", None)
        return row

    def list_tasks(self) -> list[dict]:
        return [self._task_out(r, False)
                for r in self._q("SELECT * FROM tasks ORDER BY name")]

    def get_task(self, name: str) -> Optional[dict]:
        rows = self._q("SELECT * FROM tasks WHERE name=?", (name,))
        return self._task_out(rows[0], True) if rows else None

    def put_task(self, name: str, *, gym_id: Optional[str], content: Optional[str],
                 description: Optional[str], overrides: dict) -> dict:
        self._x(
            "INSERT INTO tasks (name, gym_id, content, description, overrides, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET "
            "gym_id=excluded.gym_id, content=excluded.content, "
            "description=excluded.description, overrides=excluded.overrides, "
            "updated_at=excluded.updated_at",
            (name, gym_id, content, description, json.dumps(overrides), _now()),
        )
        return self.get_task(name)

    def delete_task(self, name: str) -> None:
        self._x("DELETE FROM tasks WHERE name=?", (name,))

    # ── Runs ─────────────────────────────────────────────────────────
    @staticmethod
    def _run_out(row: dict) -> dict:
        row["overrides"] = json.loads(row["overrides"] or "{}")
        row["settings"] = json.loads(row["settings"]) if row["settings"] else None
        return row

    def create_run(self, *, task_name: str, label: Optional[str], overrides: dict) -> int:
        return self._x(
            "INSERT INTO runs (task_name, label, status, overrides, created_at) "
            "VALUES (?, ?, 'QUEUED', ?, ?)",
            (task_name, label, json.dumps(overrides), _now()),
        )

    def list_runs(self, limit: int = 200) -> list[dict]:
        return [self._run_out(r)
                for r in self._q("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]

    def get_run(self, rid: int) -> Optional[dict]:
        rows = self._q("SELECT * FROM runs WHERE id=?", (rid,))
        return self._run_out(rows[0]) if rows else None

    def update_run(self, rid: int, **fields) -> None:
        if not fields:
            return
        for k in ("overrides", "settings"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k])
        cols = ", ".join(f"{k}=?" for k in fields)
        self._x(f"UPDATE runs SET {cols} WHERE id=?", (*fields.values(), rid))

    def claim_next_run(self) -> Optional[dict]:
        """Oldest QUEUED run, flipped to RUNNING atomically."""
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT * FROM runs WHERE status='QUEUED' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self._db.execute(
                "UPDATE runs SET status='RUNNING', started_at=?, phase='staging', "
                "episode=NULL, episode_total=NULL, success_rate=NULL, "
                "error_message=NULL, finished_at=NULL WHERE id=?",
                (_now(), row["id"]),
            )
        return self.get_run(row["id"])

    def delete_run(self, rid: int) -> None:
        self._x("DELETE FROM runs WHERE id=?", (rid,))

    def effective_settings(self, task: dict, run_overrides: dict) -> dict:
        s = self.get_settings()
        for src in (task.get("overrides") or {}, run_overrides or {}):
            for k in OVERRIDE_KEYS:
                if src.get(k) not in (None, ""):
                    s[k] = src[k]
        return s


store: Optional[LocalStore] = None


def get_store() -> LocalStore:
    global store
    if store is None:
        store = LocalStore()
    return store
