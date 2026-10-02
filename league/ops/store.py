"""`<state>/ops.sqlite`: one receipt row per job occurrence (mode 0600, the House's private file).

    runs(id, job, due_at, started_at, finished_at, status, summary_json, error, pid, attempts)

`status` is `ok`, `failed`, `missed` or `skipped` once the occurrence is settled, and `running` while its child runs.
(job, due_at) is unique: one row per occurrence, started at most `MAX_ATTEMPTS` times (`retry_state`). A run the
House's own restart interrupted (`error` starting `INTERRUPTED`) is started again at once while its grace allows (past
it, `missed`). A run that failed on its own (a gateway or Sail blip, a raising job) is started again `RETRY_AFTER`
seconds after it ended while it can still START inside its grace (past it, it stays `failed`). A job that says it may
not be repeated (`Job.retry` False) is never started twice, even after an interruption.
Only the House process writes here (the runner, on the tick); a job's child writes its result to a file the runner
reads. `kv` keeps the runner's small state (`installed_at`: the first time this House ran jobs, so an older
occurrence is never reported missed).
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import guard
from .schedule import epoch

FILE = "ops.sqlite"
STATUSES = ("ok", "failed", "missed", "skipped")
INTERRUPTED = "interrupted"
#: Three, not two: an updater release launched as its session hold lifts (20:05Z) promotes about when `economics` starts
#: (close + 10) and a rollback inside its ten-minute watch restarts the House again: two interruptions of one run.
MAX_ATTEMPTS = 3
#: How long after a failed run ends before it is started again (a blip passes; a broken job fails fewer times a day).
RETRY_AFTER = 15 * 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL, due_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
    status TEXT NOT NULL, summary_json TEXT, error TEXT, pid INTEGER, attempts INTEGER NOT NULL DEFAULT 0,
    UNIQUE(job, due_at));
CREATE INDEX IF NOT EXISTS runs_due ON runs(due_at);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class OpsStore:
    def __init__(self, root: str | Path):
        self.path = Path(root) / FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        self.db = sqlite3.connect(str(self.path), timeout=2.0, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
            self.db.executescript(SCHEMA)
        except sqlite3.Error:
            self.db.close()  # a torn file or a held lock: the caller decides (`league.ops.attach`)
            raise

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------------ kv
    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return default if row is None else json.loads(row[0])

    def put(self, key: str, value: Any) -> None:
        self.db.execute("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, json.dumps(value, sort_keys=True, default=str)))

    # ------------------------------------------------------------------ runs
    def run(self, job: str, due_at: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM runs WHERE job=? AND due_at=?", (job, due_at)).fetchone()
        return None if row is None else dict(row)

    def settled(self, job: str, due_at: str) -> bool:
        """The occurrence needs nothing more: it has a row, unless an interruption left it retryable."""
        row = self.run(job, due_at)
        return row is not None and not retryable(row)

    def start(self, job: str, due_at: str, started_at: str, pid: int | None = None) -> int:
        """A `running` row (a new one, or the interrupted one again). Its id."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT id FROM runs WHERE job=? AND due_at=?", (job, due_at)).fetchone()
            if row is None:
                cursor = self.db.execute(
                    "INSERT INTO runs(job, due_at, started_at, status, pid, attempts) VALUES(?, ?, ?, 'running', ?, 1)",
                    (job, due_at, started_at, pid))
                return int(cursor.lastrowid)
            self.db.execute("UPDATE runs SET started_at=?, finished_at=NULL, status='running', error=NULL, pid=?, "
                            "attempts=attempts+1 WHERE id=?", (started_at, pid, row[0]))
            return int(row[0])

    def set_pid(self, run_id: int, pid: int) -> None:
        self.db.execute("UPDATE runs SET pid=? WHERE id=?", (int(pid), int(run_id)))

    def finish(self, run_id: int, status: str, finished_at: str, *, summary: Mapping[str, Any] | None = None,
               error: str | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"not a settled status: {status}")
        self.db.execute("UPDATE runs SET status=?, finished_at=?, summary_json=?, error=? WHERE id=?",
                        (status, finished_at, None if summary is None else json.dumps(summary, sort_keys=True, default=str),
                         None if error is None else str(error)[:2000], int(run_id)))

    def record(self, job: str, due_at: str, status: str, at: str, *, summary: Mapping[str, Any] | None = None,
               error: str | None = None) -> bool:
        """A settled row for an occurrence that never ran (`missed`, `skipped`). False when it already had one."""
        if status not in STATUSES:
            raise ValueError(f"not a settled status: {status}")
        cursor = self.db.execute(
            "INSERT OR IGNORE INTO runs(job, due_at, started_at, finished_at, status, summary_json, error, attempts) "
            "VALUES(?, ?, NULL, ?, ?, ?, ?, 0)",
            (job, due_at, at, status, None if summary is None else json.dumps(summary, sort_keys=True, default=str),
             None if error is None else str(error)[:2000]))
        return cursor.rowcount == 1

    def running(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute("SELECT * FROM runs WHERE status='running' ORDER BY id")]

    def last_ok(self, job: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM runs WHERE job=? AND status='ok' ORDER BY finished_at DESC, id DESC LIMIT 1",
                              (job,)).fetchone()
        return None if row is None else dict(row)

    def ok_since(self, job: str, since: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM runs WHERE job=? AND status='ok' AND finished_at>? ORDER BY finished_at", (job, since))]

    def between(self, start: str, end: str) -> list[dict[str, Any]]:
        """Rows due in [start, end)."""
        return [dict(r) for r in self.db.execute("SELECT * FROM runs WHERE due_at>=? AND due_at<? ORDER BY due_at, id",
                                                 (start, end))]


def retryable(row: Mapping[str, Any]) -> bool:
    """A run the House's restart interrupted, with an attempt left."""
    return (row.get("status") == "failed" and str(row.get("error") or "").startswith(INTERRUPTED)
            and int(row.get("attempts") or 0) < MAX_ATTEMPTS)


def retry_state(row: Mapping[str, Any], *, due_at: float, grace: float, now: float, retry: bool = True) -> str:
    """What an occurrence's row asks of the runner at `now`: `settled` (nothing more), `retry` (start it again; an
    interrupted run past its grace becomes `missed`) or `wait` (a failed run inside its grace, before `RETRY_AFTER`).
    A job that may not be repeated (`retry=False`) is settled by its first run, interrupted or not."""
    if not retry:
        return "settled"
    if retryable(row):
        return "retry"
    if (row.get("status") != "failed" or str(row.get("error") or "").startswith(INTERRUPTED)
            or int(row.get("attempts") or 0) >= MAX_ATTEMPTS or now > due_at + grace):
        return "settled"
    ended = epoch(row.get("finished_at"))
    return "wait" if ended is not None and now < ended + RETRY_AFTER else "retry"


def read_runs(root: str | Path, start: str, end: str) -> list[dict[str, Any]]:
    """The rows due in [start, end), read-only (another process: the receipts, the laptop's own reading)."""
    path = Path(root) / FILE
    if not path.exists():
        return []
    return guard.read(path, lambda db: guard.rows(
        db, "SELECT job, due_at, started_at, finished_at, status, summary_json, error, attempts FROM runs "
            "WHERE due_at>=? AND due_at<? ORDER BY due_at, id", (start, end)))


def summaries(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Rows with `summary_json` parsed into `summary`."""
    out = []
    for row in rows:
        row = dict(row)
        raw = row.pop("summary_json", None)
        try:
            row["summary"] = json.loads(raw) if raw else None
        except ValueError:
            row["summary"] = None
        out.append(row)
    return out
