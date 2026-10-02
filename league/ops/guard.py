"""Read-only SQLite for the House's jobs (`league/ops/`), and the habits that keep an extract from hurting the House.

Extracted from the operator's laptop tools (the pre-open checks and the close economics, Sept 28-Oct 2, 2026) and the
House OOM of Oct 2 07:38Z (an extract that held a cursor open while it wrote files, beside the live minute):

- `connect_ro(path)`: a `mode=ro` URI, and `immutable=1` as well for a WAL database nobody has open (no `-wal`/`-shm`
  beside it: plain `mode=ro` would create them); `PRAGMA query_only`; rows as `sqlite3.Row`. A live WAL database (its
  `-wal` and `-shm` present) is opened plain `mode=ro`, so it reads the writer's newest commits under the normal locks.
- `readonly()`: while it is entered, EVERY `sqlite3.connect` in the process (the release's own readers included)
  is refused unless it is a `mode=ro` URI or an in-memory database, and gets the same `immutable=1` rule. A job's
  child process enters it around a read of the House's state (`economics`, `preopen`).
- `read(path, fn)`: open, run `fn(db)` (which must return plain lists/dicts, never a cursor), close; only then may
  the caller touch files. `ids(db, sql)` fetches a column into a list and closes its cursor; `batched(db, sql, ids)`
  reads rows for many ids in bounded `IN (...)` batches.
"""
from __future__ import annotations

import contextlib
import os
import sqlite3
import threading
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

#: How many ids one `IN (...)` read carries (SQLite's default variable limit is 32766 on 3.32+, 999 before).
BATCH = 500
_MEMORY = (":memory:", "file::memory:")
_real_connect = sqlite3.connect
_guard_lock = threading.Lock()
_guard_depth = 0


def is_wal(path: str | Path) -> bool:
    """The database file's header says WAL (byte 18 is 2)."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(20)
        return len(head) >= 20 and head[18] == 2
    except OSError:
        return False


def idle_wal(path: str | Path) -> bool:
    """A WAL database with no `-wal`/`-shm` beside it: no writer has it open, and `mode=ro` alone would create them."""
    path = str(path)
    return is_wal(path) and not (os.path.exists(path + "-wal") and os.path.exists(path + "-shm"))


def ro_uri(path: str | Path) -> str:
    """The `file:` URI that opens `path` read-only (and immutable when it is an idle WAL database)."""
    resolved = Path(path).resolve()
    uri = resolved.as_uri() + "?mode=ro"
    if idle_wal(resolved):
        uri += "&immutable=1"
    return uri


def connect_ro(path: str | Path, *, timeout: float = 5.0) -> sqlite3.Connection:
    """A read-only connection to an existing database (`sqlite3.OperationalError` when it does not exist)."""
    if not Path(path).exists():
        raise sqlite3.OperationalError(f"unable to open database file: {path} does not exist")
    db = _real_connect(ro_uri(path), uri=True, timeout=timeout, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def read(path: str | Path, fn: Callable[[sqlite3.Connection], Any], *, timeout: float = 5.0) -> Any:
    """`fn(db)` in one read transaction on a read-only connection, closed before this returns. `fn` must return
    materialized values (lists, dicts, numbers), never a cursor or a Row iterator."""
    db = connect_ro(path, timeout=timeout)
    try:
        db.execute("BEGIN")
        value = fn(db)
        db.rollback()
        return value
    finally:
        db.close()


def ids(db: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[Any]:
    """The first column of every row, fetched into a list; the cursor is closed before this returns."""
    cursor = db.execute(sql, tuple(params))
    try:
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()


def rows(db: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    """Every row as a dict, fetched into a list; the cursor is closed before this returns."""
    cursor = db.execute(sql, tuple(params))
    try:
        names = [d[0] for d in cursor.description or ()]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def batched(db: sqlite3.Connection, sql: str, keys: Iterable[Any], *, size: int = BATCH,
            params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    """Rows for many keys, `size` at a time: `sql` holds one `{marks}` where the `?, ?, ...` list goes, after
    `params`. Each batch's cursor is closed before the next is read."""
    keys = list(keys)
    out: list[dict[str, Any]] = []
    for start in range(0, len(keys), max(1, int(size))):
        chunk = keys[start:start + max(1, int(size))]
        out.extend(rows(db, sql.format(marks=", ".join("?" * len(chunk))), [*params, *chunk]))
    return out


def _guarded(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
    text = str(database)
    if text in _MEMORY:
        return _real_connect(database, *args, **kwargs)
    if not (kwargs.get("uri") and text.startswith("file:")):
        raise PermissionError(f"read-only: refused a writable SQLite open of {text}")
    head, _, query = text[5:].partition("?")
    params = dict(urllib.parse.parse_qsl(query))
    if params.get("mode") != "ro":
        raise PermissionError(f"read-only: refused a writable SQLite open of {text}")
    path = urllib.parse.unquote(head[2:] if head.startswith("//") else head)
    if params.get("immutable") != "1" and idle_wal(path):
        text += "&immutable=1"
    return _real_connect(text, *args, **kwargs)


@contextlib.contextmanager
def readonly() -> Iterator[None]:
    """Refuse every writable `sqlite3.connect` in this process while entered (nests; restores the real one after)."""
    global _guard_depth
    with _guard_lock:
        _guard_depth += 1
        sqlite3.connect = _guarded  # type: ignore[assignment]
    try:
        yield
    finally:
        with _guard_lock:
            _guard_depth -= 1
            if _guard_depth == 0:
                sqlite3.connect = _real_connect  # type: ignore[assignment]
