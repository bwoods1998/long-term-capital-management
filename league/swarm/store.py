"""The swarm's store: one SQLite file in the state root, and the programs beside it.

    <root>/swarm.sqlite            families, versions, runs, notebooks, graveyard, looks, forward,
                                   events, spend, boxes, conversations, key-values
    <root>/programs/<family>/      v<n>-<sha12>.py (and .json: its PARAMS overrides), one per version
    <root>/swarm-runs/<id>.json.gz every Gym result in full (trades and daily series: licensed-data
                                   derivatives, so never in git and never on the site)

Nothing here is ever committed: the repository is public and programs are fitted to licensed data.

TRIALS. Every Gym evaluation is a trial (`add_run` counts the result's own `trials`), per family and in
total; a family's LINEAGE count is what it inherited at its fork plus its own, and so are its holdout
looks (`lineage_trials`, `lineage_looks`). Nothing ever lowers a count.

EVENTS. `event(kind, family, payload)` appends a row the House mirrors into its ledger (`hook.py`),
all of kind `swarm.*`: the public ones the site's tape reads (`swarm.born`, `swarm.retired`, `swarm.band`,
`swarm.note`) and private ones (cycles, tournaments, the gate, the pool, the guard). Never the House's own
`agent.*` or `eval.*` kinds: its roster and evaluator read those. The table is append-only.

One connection under one lock, WAL, so the House can read (and write the forward records of shadow and
real trades, `add_forward`) from its own process. Standard library only.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import DB_NAME, PROGRAMS_DIR, RUNS_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS families (
    id TEXT PRIMARY KEY,
    lineage TEXT NOT NULL,
    parent TEXT,
    origin TEXT NOT NULL,
    mechanism TEXT NOT NULL,
    structure TEXT NOT NULL,
    roots TEXT NOT NULL,
    spec TEXT NOT NULL,
    born_at TEXT NOT NULL,
    retired_at TEXT,
    retire_reason TEXT,
    band TEXT NOT NULL DEFAULT 'gym',
    band_since TEXT,
    best_version INTEGER,
    best_train REAL,
    validated_version INTEGER,
    best_validation REAL,
    trials INTEGER NOT NULL DEFAULT 0,
    inherited_trials INTEGER NOT NULL DEFAULT 0,
    inherited_looks INTEGER NOT NULL DEFAULT 0,
    revisions INTEGER NOT NULL DEFAULT 0,
    cycles INTEGER NOT NULL DEFAULT 0,
    stall INTEGER NOT NULL DEFAULT 0,
    rewrites INTEGER NOT NULL DEFAULT 0,
    since_val_revisions INTEGER NOT NULL DEFAULT 0,
    since_val_trials INTEGER NOT NULL DEFAULT 0,
    validations INTEGER NOT NULL DEFAULT 0,
    weight REAL,
    spent_usd REAL NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS versions (
    family TEXT NOT NULL,
    n INTEGER NOT NULL,
    sha TEXT NOT NULL,
    params TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    author TEXT NOT NULL,
    note TEXT,
    PRIMARY KEY (family, n)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    version INTEGER,
    window TEXT NOT NULL,
    stress REAL NOT NULL,
    purpose TEXT NOT NULL,
    at TEXT NOT NULL,
    status TEXT NOT NULL,
    trials INTEGER NOT NULL,
    program_years REAL NOT NULL DEFAULT 0,
    summary TEXT,
    path TEXT
);
CREATE INDEX IF NOT EXISTS runs_family ON runs(family, at);
CREATE TABLE IF NOT EXISTS notebook (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    family TEXT NOT NULL,
    at TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS notebook_family ON notebook(family, seq);
CREATE TABLE IF NOT EXISTS graveyard (
    family TEXT PRIMARY KEY,
    at TEXT NOT NULL,
    mechanism TEXT NOT NULL,
    structure TEXT NOT NULL,
    roots TEXT NOT NULL,
    lesson TEXT NOT NULL,
    best TEXT
);
CREATE TABLE IF NOT EXISTS looks (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    family TEXT NOT NULL,
    lineage TEXT NOT NULL,
    version INTEGER NOT NULL,
    run_sha TEXT NOT NULL UNIQUE,
    at TEXT NOT NULL,
    passed INTEGER NOT NULL,
    p_value REAL,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS refusals (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    family TEXT NOT NULL,
    version INTEGER,
    at TEXT NOT NULL,
    stage TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forward (
    family TEXT NOT NULL,
    source TEXT NOT NULL,
    trade_id TEXT NOT NULL,
    day TEXT NOT NULL,
    pnl REAL NOT NULL,
    max_loss REAL NOT NULL,
    at TEXT NOT NULL,
    version INTEGER,
    PRIMARY KEY (family, source, trade_id)
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    family TEXT,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind, at);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
    BEGIN SELECT RAISE(ABORT, 'swarm events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
    BEGIN SELECT RAISE(ABORT, 'swarm events are append-only'); END;
CREATE TABLE IF NOT EXISTS spend (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    epoch REAL NOT NULL,
    kind TEXT NOT NULL,
    family TEXT,
    usd REAL NOT NULL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS spend_kind ON spend(kind, epoch);
CREATE TABLE IF NOT EXISTS boxes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    version TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used REAL NOT NULL,
    busy_seconds REAL NOT NULL DEFAULT 0,
    jobs INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS convo (
    family TEXT PRIMARY KEY,
    items TEXT NOT NULL,
    pending TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

ALIVE = ("gym", "candidate", "probe", "sized")
BANDS = ("gym", "candidate", "probe", "sized", "retired")
STRUCTURES = ("long_call", "long_put", "debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly",
              "long_butterfly", "long_straddle", "long_strangle", "calendar", "diagonal")
#: The five types that close in one order (the venue refuses one-order closes of the others).
CLOSEABLE = ("debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly", "long_butterfly")
_SLUG = re.compile(r"^[a-z0-9-]{1,40}$")


def iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def slugify(text: Any, *, limit: int = 36) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    out = re.sub(r"-{2,}", "-", out)[:limit].strip("-")
    return out or "family"


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def loads(text: Any, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def code_sha(code: str) -> str:
    return hashlib.sha256(str(code).encode("utf-8")).hexdigest()


class SwarmStore:
    """The swarm's durable state (the module docstring)."""

    def __init__(self, root: str | Path, *, clock: Any = time.time, readonly: bool = False):
        self.root = Path(root)
        self.clock = clock
        self.readonly = readonly
        self.path = self.root / DB_NAME
        self.programs = self.root / PROGRAMS_DIR
        self.runs_dir = self.root / RUNS_DIR
        self._lock = threading.RLock()
        if readonly:
            self._db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False, timeout=5,
                                       isolation_level=None)
        else:
            self.root.mkdir(parents=True, exist_ok=True)
            self.programs.mkdir(exist_ok=True)
            self.runs_dir.mkdir(exist_ok=True)
            self._db = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30, isolation_level=None)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.executescript(SCHEMA)
            columns = {r[1] for r in self._db.execute("PRAGMA table_info(forward)")}
            if "version" not in columns:  # a store made before forward rows carried their program version
                self._db.execute("ALTER TABLE forward ADD COLUMN version INTEGER")
        self._db.row_factory = sqlite3.Row

    # ------------------------------------------------------------------ plumbing
    def now(self) -> str:
        return iso(self.clock())

    def _all(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, tuple(params)).fetchall()]

    def _one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(sql, tuple(params)).fetchone()
        return dict(row) if row is not None else None

    def _exec(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._db.execute(sql, tuple(params))

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------ key-values
    def get(self, key: str, default: Any = None) -> Any:
        row = self._one("SELECT value FROM kv WHERE key=?", (key,))
        return loads(row["value"], default) if row else default

    def put(self, key: str, value: Any) -> None:
        self._exec("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, dumps(value)))

    # ------------------------------------------------------------------ families
    @staticmethod
    def _family(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        row["roots"] = loads(row["roots"], [])
        row["spec"] = loads(row["spec"], {})
        row["state"] = loads(row["state"], {})
        return row

    def unique_id(self, base: str) -> str:
        stem = slugify(base)
        candidate, n = stem, 1
        while self._one("SELECT 1 FROM families WHERE id=?", (candidate,)) is not None:
            n += 1
            candidate = f"{stem[:36 - len(str(n)) - 1]}-{n}"
        return candidate

    def add_family(self, spec: Mapping[str, Any], *, origin: str, parent: str | None = None) -> dict[str, Any]:
        """A new family from `spec` (id or slug, mechanism, structure, roots, dte, rejection, ...). A fork
        (`parent`) starts with its parent's LINEAGE trial count and holdout looks."""
        if spec.get("structure") not in STRUCTURES:
            raise ValueError(f"unknown structure {spec.get('structure')!r}")
        roots = [str(r).upper() for r in (spec.get("roots") or []) if str(r).strip()]
        if not roots:
            raise ValueError("a family names at least one root")
        mechanism = " ".join(str(spec.get("mechanism") or "").split())
        if len(mechanism) < 20:
            raise ValueError("a family's mechanism is a sentence saying why it should make money")
        with self._lock:
            fid = self.unique_id(spec.get("id") or spec.get("slug") or mechanism)
            lineage, inherited_trials, inherited_looks = fid, 0, 0
            if parent:
                mother = self.family(parent)
                if mother is None:
                    raise ValueError(f"no parent family {parent}")
                lineage = mother["lineage"]
                inherited_trials = self.lineage_trials(parent)
                inherited_looks = self.lineage_looks(parent)
            body = {k: v for k, v in dict(spec).items() if k not in ("id", "slug")}
            body["roots"] = roots
            now = self.now()
            self._exec(
                "INSERT INTO families(id, lineage, parent, origin, mechanism, structure, roots, spec, born_at, band, band_since,"
                " inherited_trials, inherited_looks) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fid, lineage, parent, origin, mechanism, spec["structure"], dumps(roots), dumps(body), now, "gym", now,
                 inherited_trials, inherited_looks))
        return self.family(fid)  # type: ignore[return-value]

    def family(self, fid: str) -> dict[str, Any] | None:
        return self._family(self._one("SELECT * FROM families WHERE id=?", (fid,)))

    def families(self, *, alive: bool | None = None) -> list[dict[str, Any]]:
        if alive is None:
            rows = self._all("SELECT * FROM families ORDER BY born_at, id")
        elif alive:
            rows = self._all("SELECT * FROM families WHERE retired_at IS NULL ORDER BY born_at, id")
        else:
            rows = self._all("SELECT * FROM families WHERE retired_at IS NOT NULL ORDER BY retired_at, id")
        return [self._family(r) for r in rows]  # type: ignore[misc]

    def update_family(self, fid: str, **fields: Any) -> None:
        if not fields:
            return
        cols = []
        values = []
        for key, value in fields.items():
            if key in ("roots", "spec", "state"):
                value = dumps(value)
            cols.append(f"{key}=?")
            values.append(value)
        self._exec(f"UPDATE families SET {', '.join(cols)} WHERE id=?", (*values, fid))

    def bump(self, fid: str, **deltas: float) -> None:
        """Add to counters (never lowers one unless the delta says so)."""
        if deltas:
            self._exec(f"UPDATE families SET {', '.join(f'{k}={k}+?' for k in deltas)} WHERE id=?", (*deltas.values(), fid))

    def set_state(self, fid: str, **values: Any) -> dict[str, Any]:
        with self._lock:
            fam = self.family(fid) or {}
            state = dict(fam.get("state") or {})
            state.update(values)
            self.update_family(fid, state=state)
            return state

    def set_band(self, fid: str, band: str, *, reason: str) -> str | None:
        """Move a family's band; the move is a `swarm.band` event (the site's news). Returns the old band."""
        if band not in BANDS:
            raise ValueError(band)
        with self._lock:
            fam = self.family(fid)
            if fam is None or fam["band"] == band:
                return None
            self.update_family(fid, band=band, band_since=self.now())
            self.event("swarm.band", fid, {"band_from": fam["band"], "band_to": band, "reason": reason})
            return fam["band"]

    def retire(self, fid: str, reason: str) -> bool:
        with self._lock:
            fam = self.family(fid)
            if fam is None or fam["retired_at"]:
                return False
            self.update_family(fid, retired_at=self.now(), retire_reason=reason, band="retired", band_since=self.now())
            self.event("swarm.retired", fid, {"cause": reason, "band_from": fam["band"]})
            return True

    def lineage_trials(self, fid: str) -> int:
        fam = self._one("SELECT trials, inherited_trials FROM families WHERE id=?", (fid,))
        return int(fam["trials"] + fam["inherited_trials"]) if fam else 0

    def lineage_looks(self, fid: str) -> int:
        fam = self._one("SELECT inherited_looks FROM families WHERE id=?", (fid,))
        own = self._one("SELECT COUNT(*) AS n FROM looks WHERE family=?", (fid,))
        return int((fam["inherited_looks"] if fam else 0) + (own["n"] if own else 0))

    def lineage_trial_sharpes(self, fid: str, *, window: str = "train", limit: int = 5000) -> list[float]:
        """Daily Sharpe of every recorded trial in the family's lineage (for the deflated Sharpe)."""
        fam = self.family(fid)
        if fam is None:
            return []
        rows = self._all("SELECT r.summary FROM runs r JOIN families f ON f.id=r.family WHERE f.lineage=? AND r.window=?"
                         " AND r.trials>0 ORDER BY r.at DESC LIMIT ?", (fam["lineage"], window, limit))
        out = []
        for r in rows:
            s = loads(r["summary"], {}) or {}
            v = s.get("sharpe_daily")
            if isinstance(v, (int, float)):
                out.append(float(v))
        return out

    # ------------------------------------------------------------------ programs
    def add_version(self, fid: str, code: str, params: Mapping[str, Any] | None, *, author: str, note: str = "") -> dict[str, Any]:
        """Store a program version (or return the existing one with the same code and parameters)."""
        sha = code_sha(code)
        params = dict(params or {})
        with self._lock:
            for v in self._all("SELECT * FROM versions WHERE family=? AND sha=?", (fid, sha)):
                if loads(v["params"], {}) == params:
                    return self.version(fid, v["n"])  # type: ignore[return-value]
            last = self._one("SELECT MAX(n) AS n FROM versions WHERE family=?", (fid,))
            n = int((last or {}).get("n") or 0) + 1
            folder = self.programs / fid
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"v{n}-{sha[:12]}.py"
            path.write_text(code)
            (folder / f"v{n}-{sha[:12]}.json").write_text(dumps(params))
            self._exec("INSERT INTO versions(family, n, sha, params, path, created_at, author, note) VALUES(?,?,?,?,?,?,?,?)",
                       (fid, n, sha, dumps(params), str(path.relative_to(self.root)), self.now(), author, str(note or "")[:500]))
            self.bump(fid, revisions=1, stall=1, since_val_revisions=1)
        return self.version(fid, n)  # type: ignore[return-value]

    def version(self, fid: str, n: int | None) -> dict[str, Any] | None:
        if n is None:
            return None
        row = self._one("SELECT * FROM versions WHERE family=? AND n=?", (fid, int(n)))
        if row is None:
            return None
        row["params"] = loads(row["params"], {})
        try:
            row["code"] = (self.root / row["path"]).read_text()
        except OSError:
            row["code"] = None
        return row

    def latest_version(self, fid: str) -> dict[str, Any] | None:
        row = self._one("SELECT MAX(n) AS n FROM versions WHERE family=?", (fid,))
        return self.version(fid, row["n"]) if row and row["n"] else None

    def versions(self, fid: str) -> list[dict[str, Any]]:
        rows = self._all("SELECT family, n, sha, params, created_at, author, note FROM versions WHERE family=? ORDER BY n", (fid,))
        for r in rows:
            r["params"] = loads(r["params"], {})
        return rows

    # ------------------------------------------------------------------ runs
    def add_run(self, fid: str, version: int | None, result: Mapping[str, Any], *, window: str, stress: float, purpose: str,
                program_years: float = 0.0) -> dict[str, Any]:
        """Record one Gym result (every result is a trial when its `trials` says so) and keep it in full. The same
        evaluation run again (same code, parameters, data and settings: the same `run_id`) is stored once and still
        counted: every evaluation the Gym makes is a trial."""
        run_id = str(result.get("run_id") or code_sha(dumps(result))[:24])
        trials = int(result.get("trials", 0) or 0)
        status = str(result.get("status") or "unknown")
        summary = dict(result.get("summary") or {})
        if status == "refused":
            summary = {"reason": result.get("reason")}
        with self._lock:
            mine = f"{run_id}-{fid}"[:64]
            existing = self._one("SELECT * FROM runs WHERE (run_id=? OR run_id=?) AND family=?", (run_id, mine, fid))
            if existing is not None:
                if trials:
                    self._exec("UPDATE runs SET trials=trials+?, program_years=program_years+? WHERE run_id=?",
                               (trials, float(program_years), existing["run_id"]))
                    self.bump(fid, trials=trials, since_val_trials=trials)
                return self._one("SELECT * FROM runs WHERE run_id=?", (existing["run_id"],))  # type: ignore[return-value]
            if self._one("SELECT 1 FROM runs WHERE run_id=?", (run_id,)) is not None:
                run_id = mine
            path = self.runs_dir / f"{run_id}.json.gz"
            path.write_bytes(gzip.compress(dumps(result).encode("utf-8"), compresslevel=5))
            self._exec("INSERT INTO runs(run_id, family, version, window, stress, purpose, at, status, trials, program_years, summary, path)"
                       " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (run_id, fid, version, window, float(stress), purpose, self.now(), status, trials, float(program_years),
                        dumps(summary), str(path.relative_to(self.root))))
            if trials:
                self.bump(fid, trials=trials, since_val_trials=trials)
            if window == "train":
                self.prune_runs(fid)
        return self._one("SELECT * FROM runs WHERE run_id=?", (run_id,))  # type: ignore[return-value]

    #: Full Train results kept per family (the newest, plus its best and submitted runs): a three-year result is ~100-400 KB
    #: compressed and a researcher makes one a minute, which would fill the House box's disk in days. The summary row stays.
    KEEP_FULL_TRAIN_RUNS = 6

    def prune_runs(self, fid: str) -> int:
        fam = self.family(fid) or {}
        state = fam.get("state") or {}
        keep = {state.get("best_train_run"), state.get("submitted_run")}
        rows = self._all("SELECT run_id, path FROM runs WHERE family=? AND window='train' AND path IS NOT NULL ORDER BY at DESC, rowid DESC",
                         (fid,))
        n = 0
        for row in rows[self.KEEP_FULL_TRAIN_RUNS:]:
            if row["run_id"] in keep:
                continue
            try:
                (self.root / row["path"]).unlink()
            except OSError:
                pass
            self._exec("UPDATE runs SET path=NULL WHERE run_id=?", (row["run_id"],))
            n += 1
        return n

    def run(self, run_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM runs WHERE run_id=?", (run_id,))
        if row is not None:
            row["summary"] = loads(row["summary"], {})
        return row

    def run_result(self, run_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT path FROM runs WHERE run_id=?", (run_id,))
        if row is None or not row["path"]:
            return None
        try:
            return json.loads(gzip.decompress((self.root / row["path"]).read_bytes()))
        except (OSError, ValueError):
            return None

    def runs(self, fid: str, *, window: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if window:
            rows = self._all("SELECT * FROM runs WHERE family=? AND window=? ORDER BY at DESC, rowid DESC LIMIT ?", (fid, window, limit))
        else:
            rows = self._all("SELECT * FROM runs WHERE family=? ORDER BY at DESC, rowid DESC LIMIT ?", (fid, limit))
        for r in rows:
            r["summary"] = loads(r["summary"], {})
        return rows

    def totals(self) -> dict[str, Any]:
        row = self._one("SELECT COALESCE(SUM(trials),0) AS trials, COALESCE(SUM(program_years),0) AS years, COUNT(*) AS runs FROM runs")
        alive = self._one("SELECT COUNT(*) AS n FROM families WHERE retired_at IS NULL")
        dead = self._one("SELECT COUNT(*) AS n FROM families WHERE retired_at IS NOT NULL")
        looks = self._one("SELECT COUNT(*) AS n, COALESCE(SUM(passed),0) AS passed FROM looks")
        return {"trials": int(row["trials"]), "market_years": float(row["years"]), "runs": int(row["runs"]),
                "families_alive": int(alive["n"]), "families_retired": int(dead["n"]),
                "holdout_looks": int(looks["n"]), "holdout_passes": int(looks["passed"])}

    # ------------------------------------------------------------------ notebook and graveyard
    def note(self, fid: str, text: str) -> int:
        text = str(text or "").strip()[:4000]
        if not text:
            return 0
        cur = self._exec("INSERT INTO notebook(family, at, text) VALUES(?,?,?)", (fid, self.now(), text))
        return int(cur.lastrowid or 0)

    def notebook(self, fid: str, *, limit: int = 30) -> list[dict[str, Any]]:
        rows = self._all("SELECT seq, at, text FROM notebook WHERE family=? ORDER BY seq DESC LIMIT ?", (fid, limit))
        return list(reversed(rows))

    def bury(self, fid: str, lesson: str, best: Mapping[str, Any] | None = None) -> None:
        fam = self.family(fid)
        if fam is None:
            return
        self._exec("INSERT OR REPLACE INTO graveyard(family, at, mechanism, structure, roots, lesson, best) VALUES(?,?,?,?,?,?,?)",
                   (fid, self.now(), fam["mechanism"], fam["structure"], dumps(fam["roots"]), str(lesson)[:3000], dumps(best or {})))

    def graveyard(self, query: str = "", *, limit: int = 8) -> list[dict[str, Any]]:
        rows = self._all("SELECT * FROM graveyard ORDER BY at DESC")
        words = [w for w in re.findall(r"[a-z0-9]+", str(query or "").lower()) if len(w) > 2]
        if words:
            def score(r: dict[str, Any]) -> int:
                text = f"{r['mechanism']} {r['structure']} {r['roots']} {r['lesson']}".lower()
                return sum(text.count(w) for w in words)
            rows = [r for r in sorted(rows, key=score, reverse=True) if score(r) > 0]
        out = []
        for r in rows[:limit]:
            r["roots"] = loads(r["roots"], [])
            r["best"] = loads(r["best"], {})
            out.append(r)
        return out

    # ------------------------------------------------------------------ the gate's records
    def add_look(self, fid: str, version: int, run_sha: str, *, passed: bool, p_value: float | None, detail: Mapping[str, Any]) -> int:
        fam = self.family(fid)
        cur = self._exec("INSERT INTO looks(family, lineage, version, run_sha, at, passed, p_value, detail) VALUES(?,?,?,?,?,?,?,?)",
                         (fid, fam["lineage"] if fam else fid, int(version), run_sha, self.now(), 1 if passed else 0, p_value, dumps(detail)))
        return int(cur.lastrowid or 0)

    def looks(self) -> list[dict[str, Any]]:
        rows = self._all("SELECT * FROM looks ORDER BY seq")
        for r in rows:
            r["detail"] = loads(r["detail"], {})
        return rows

    def looked(self, run_sha: str) -> bool:
        return self._one("SELECT 1 FROM looks WHERE run_sha=?", (run_sha,)) is not None

    def refuse(self, fid: str, version: int | None, stage: str, reason: str) -> None:
        self._exec("INSERT INTO refusals(family, version, at, stage, reason) VALUES(?,?,?,?,?)",
                   (fid, version, self.now(), stage, str(reason)[:2000]))

    def refusals(self, fid: str | None = None) -> list[dict[str, Any]]:
        if fid:
            return self._all("SELECT * FROM refusals WHERE family=? ORDER BY seq", (fid,))
        return self._all("SELECT * FROM refusals ORDER BY seq")

    # ------------------------------------------------------------------ forward records
    def add_forward(self, fid: str, source: str, trades: Iterable[Mapping[str, Any]], *, version: int | None = None) -> int:
        """Forward trades (nightly replays here; shadow and real from the live path), each once by id, each with the
        program VERSION that made it (a trade's own `version`, else `version`): a new version starts its own record."""
        if source not in ("nightly", "shadow", "real"):
            raise ValueError(source)
        n = 0
        with self._lock:
            for t in trades:
                v = t.get("version", version)
                cur = self._exec("INSERT OR IGNORE INTO forward(family, source, trade_id, day, pnl, max_loss, at, version)"
                                 " VALUES(?,?,?,?,?,?,?,?)",
                                 (fid, source, str(t["id"]), str(t.get("day") or ""), float(t["pnl"]), float(t.get("max_loss") or 0.0),
                                  self.now(), None if v is None else int(v)))
                n += cur.rowcount or 0
        return n

    def replace_forward(self, fid: str, source: str, trades: Iterable[Mapping[str, Any]], *, version: int) -> int:
        """One version's record from one source anew (the nightly replay reruns every forward day: its latest good run
        is the record). Other versions' and sources' rows are untouched."""
        with self._lock:
            self._exec("DELETE FROM forward WHERE family=? AND source=? AND version=?", (fid, source, int(version)))
            return self.add_forward(fid, source, trades, version=version)

    def forward(self, fid: str, *, version: int | None = None) -> list[dict[str, Any]]:
        if version is None:
            return self._all("SELECT * FROM forward WHERE family=? ORDER BY day, trade_id", (fid,))
        return self._all("SELECT * FROM forward WHERE family=? AND version=? ORDER BY day, trade_id", (fid, int(version)))

    # ------------------------------------------------------------------ events and spend
    def event(self, kind: str, family: str | None, payload: Mapping[str, Any]) -> int:
        cur = self._exec("INSERT INTO events(at, kind, family, payload) VALUES(?,?,?,?)", (self.now(), kind, family, dumps(payload)))
        return int(cur.lastrowid or 0)

    def events_after(self, seq: int, *, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._all("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?", (int(seq), int(limit)))
        for r in rows:
            r["payload"] = loads(r["payload"], {})
        return rows

    def add_spend(self, kind: str, usd: float, *, family: str | None = None, detail: Mapping[str, Any] | None = None) -> None:
        if not usd:
            return
        now = self.clock()
        self._exec("INSERT INTO spend(at, epoch, kind, family, usd, detail) VALUES(?,?,?,?,?,?)",
                   (iso(now), now, kind, family, float(usd), dumps(detail or {})))
        if family:
            self.bump(family, spent_usd=float(usd))

    def spent(self, kinds: Sequence[str] | None = None, *, since: float | None = None) -> float:
        sql, params = "SELECT COALESCE(SUM(usd),0) AS usd FROM spend WHERE 1=1", []
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            params += list(kinds)
        if since is not None:
            sql += " AND epoch>=?"
            params.append(float(since))
        row = self._one(sql, params)
        return float(row["usd"]) if row else 0.0

    # ------------------------------------------------------------------ boxes
    def upsert_box(self, box: str, *, kind: str, version: str, state: str, detail: Mapping[str, Any] | None = None) -> None:
        now = self.clock()
        self._exec("INSERT INTO boxes(id, kind, version, state, created_at, last_used, detail) VALUES(?,?,?,?,?,?,?)"
                   " ON CONFLICT(id) DO UPDATE SET state=excluded.state, version=excluded.version, detail=excluded.detail",
                   (box, kind, version, state, iso(now), now, dumps(detail or {})))

    def box_used(self, box: str, seconds: float, *, jobs: int = 1) -> None:
        self._exec("UPDATE boxes SET last_used=?, busy_seconds=busy_seconds+?, jobs=jobs+? WHERE id=?", (self.clock(), float(seconds), int(jobs), box))

    def set_box_state(self, box: str, state: str) -> None:
        self._exec("UPDATE boxes SET state=? WHERE id=?", (state, box))

    def boxes(self, *, kind: str | None = None, live: bool = True) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM boxes WHERE 1=1", []
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        if live:
            sql += " AND state NOT IN ('terminated','failed')"
        rows = self._all(sql + " ORDER BY created_at, id", params)
        for r in rows:
            r["detail"] = loads(r["detail"], {})
        return rows

    # ------------------------------------------------------------------ conversations
    def convo(self, fid: str) -> tuple[list[dict[str, Any]], Any]:
        row = self._one("SELECT items, pending FROM convo WHERE family=?", (fid,))
        if row is None:
            return [], None
        return loads(row["items"], []), loads(row["pending"], None)

    def save_convo(self, fid: str, items: list[dict[str, Any]], pending: Any = None) -> None:
        self._exec("INSERT INTO convo(family, items, pending, updated_at) VALUES(?,?,?,?) ON CONFLICT(family) DO UPDATE SET"
                   " items=excluded.items, pending=excluded.pending, updated_at=excluded.updated_at",
                   (fid, dumps(items), dumps(pending) if pending is not None else None, self.now()))


__all__ = ["SwarmStore", "ALIVE", "BANDS", "STRUCTURES", "CLOSEABLE", "slugify", "code_sha", "dumps", "loads", "iso"]
