"""The move sensor (J1, docs/goals/LTCM_JEV_SENSES.md): will this Kalshi midpoint move soon, recorded point in time.

Why (Sept 25, 2026). On markets from events never seen in training, the semantic lab's eight fixed
Jev questions lifted the AUC for "the midpoint moves at all" from a numeric model's 0.609 / 0.616 /
0.659 to 0.766 / 0.757 / 0.749 at 5 / 15 / 60 minutes, with no gain on direction
(docs/design/2026-09-22-jev-sensor.md). A maker needs to know when a price is about to move so it is
not picked off. An options seller needs to judge realized volatility against implied. Direction is
not what this predicts.

Every `interval_seconds` (300) the House runs `MoveSensor.run` as its `jev:move` background job:

1. It reads the `markets:` snapshots the House recorded (`recordings.sqlite`, read-only) past its own
   cursor. The first run only sets the cursor at the newest snapshot. Nothing is back-filled, and
   rows from before the recorder existed are unavailable.
2. It keeps its own minute quotes (`move_quotes`, first quote in a minute wins, as in the lab's
   `semantic_quotes`). These supply the outcomes and each state's earlier quotes.
3. It dedupes the markets shown and takes at most `max_markets_per_cycle` of them, never-recorded
   markets first, then the one recorded longest ago, ties to the most recently shown. For each it
   builds the lab's state exactly (`semantic_lab.market_state`). In one request it asks Jev the
   model's per-market questions (cached per market text and question set, so they are bought once
   per contract), its per-state questions, and two recorded-only questions (`moves_15m`,
   `moves_60m`). The recorded-only answers are kept for the post-ship evaluation and never enter
   the model. Only the first `allowance` markets are asked: the move budget is paced over the rest
   of the UTC day (`_allowance`), so it lasts through US hours and leaves the gate its share of the
   dollar pool.
4. It writes one row per observation: numeric features, answers, `move_p5/15/60` from the frozen
   model (`jev_move_model.json`), and the numeric-only model's p on the same row. `recorded_at` is
   when the row was written. A consumer or replay at time T may see only rows with
   `recorded_at <= T` (`latest`). A row whose answers could not be bought (cap, breaker, outage,
   pacing) is still written: the Jev fields and move_p are null, numeric_p is present, and `why`
   says why.

Rules:
- Jev is a label source only. Nothing here places an order, changes a money rule, promotes or
  spends beyond the Sensor's caps (`league/jev.py`).
- A placeholder model (`move-v0-placeholder`) counts as no Jev model: move_p stays null. So does a
  model file naming a feature this module cannot compute; that raises an alert once and leaves the
  numeric-only p.
- The feature is not served to strategies here. `latest` is the future `ctx["feeds"]["move"]`
  read. Before a strategy relies on it, `evaluate` (held-out rows after a cutoff, event-clustered
  bootstrap) must show AUC >= 0.70 for "moves at all" on post-ship events.

    python -m league.jev_features evaluate --store /workspace/state/jev-features.sqlite --cutoff 2026-09-26T00:00:00Z [--json]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
import shutil
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .ledger import canonical
from .semantic_lab import FEATURES, QUESTION_GUARD, finite, market_state, point, questions

PURPOSE = "move"
MODEL_PATH = Path(__file__).with_name("jev_move_model.json")
#: A model file with this version is a placeholder: no Jev model, numeric-only p (Sept 25, 2026).
PLACEHOLDER = "move-v0-placeholder"
HORIZONS = (5, 15, 60)
#: Asked with every observation and recorded for the post-ship evaluation. No model uses them:
#: the lab never asked them, so no coefficient for them was fitted on development data.
RECORDED_ONLY = {
    "moves_15m": "Will this contract's quoted midpoint change within the next 15 minutes?" + QUESTION_GUARD,
    "moves_60m": "Will this contract's quoted midpoint change within the next 60 minutes?" + QUESTION_GUARD,
}
#: The lab's question texts, exactly (`semantic_lab.questions('market')`), so answers are comparable.
LAB_QUESTIONS = {name: q["instructions"] for name, q in questions("market").items()}
#: Used when the model file cannot say: questions about the contract's own text once per market,
#: questions about quotes, peers and context per observation.
DEFAULT_PER_MARKET = ("continuous_threshold", "relative_return", "discrete_event", "ambiguous_settlement")
DEFAULT_PER_STATE = ("related_exposure", "missing_catalyst_context", "fragile_liquidity", "recent_reversal")
#: A market's text that does not move with its quote: what its per-market answers are cached by.
STATIC_FIELDS = ("market", "series", "title", "subtitle", "rules_primary", "rules_secondary", "strike", "close_time")
#: A lab-sized state measured $0.000107 a call (Sept 20-22: $13.67 for 128,179 labels); the pace
#: assumes this until today's own move calls say otherwise.
DEFAULT_CALL_USD = Decimal("0.0001")
MIN_FREE_BYTES = 512 * 1024 * 1024  # as the lab: do not buy labels whose rows cannot be kept
SHIP_AUC = 0.70


# --------------------------------------------------------------------------- numeric features
def _mid(quote: Mapping[str, Any]) -> float:
    return (float(quote["bid"]) + float(quote["ask"])) / 2


def _drift(state: Mapping[str, Any], index: int) -> float:
    earlier = [q for q in state.get("earlier_quotes") or () if finite(q.get("bid")) and finite(q.get("ask"))]
    return _mid(point(state["market"])) - _mid(earlier[index]) if earlier else 0.0


def _log_oi(state: Mapping[str, Any]) -> float:
    oi = state["market"].get("open_interest")
    return math.log1p(max(0, oi)) / 15 if finite(oi) else 0.0


def _hours(state: Mapping[str, Any]) -> float:
    hours = state["market"].get("hours_to_close")
    return min(max(hours, 0), 48) / 48 if finite(hours) else 1.0


#: Every numeric feature a model file may name: (definition, value from the lab state). The first
#: five are scripts/jev_lab_eval/evaluate.py `build`'s (executable mode). `drift_oldest` is the
#: state's own drift: the lab's fresh rows (75% of them) took `earlier_quotes[0]`, the OLDEST of up
#: to four, where its stale rows took the newest quote before entry.
NUMERIC: dict[str, tuple[str, Callable[[Mapping[str, Any]], float]]] = {
    "mid": ("(yes_bid + yes_ask) / 2 of the observed quote", lambda s: point(s["market"])["mid"]),
    "spread": ("yes_ask - yes_bid of the observed quote", lambda s: point(s["market"])["ask"] - point(s["market"])["bid"]),
    "log_oi": ("log1p(max(0, open_interest)) / 15; 0 if open_interest is missing", _log_oi),
    "hours": ("min(max(hours_to_close, 0), 48) / 48; 1 if hours_to_close is missing", _hours),
    "drift": ("mid minus the mid of the newest earlier minute quote in the state; 0 if none", lambda s: _drift(s, -1)),
    "drift_oldest": ("mid minus the mid of the oldest earlier minute quote in the state (of up to 4); 0 if none",
                     lambda s: _drift(s, 0)),
}


def numeric_features(state: Mapping[str, Any]) -> dict[str, float]:
    """Every registered numeric feature of a lab state whose quote is valid (`point`)."""
    return {name: float(read(state)) for name, (_, read) in NUMERIC.items()}


# --------------------------------------------------------------------------- the frozen model
def logistic(block: Mapping[str, Any], values: Mapping[str, float | None]) -> float | None:
    """p = 1 / (1 + exp(-clip(w0 + sum w_i (x_i - mean_i) / sd_i, -30, 30))); None if an input is missing."""
    score = block["weights"][0]
    for name, mean, sd, weight in zip(block["features"], block["mean"], block["sd"], block["weights"][1:]):
        value = values.get(name)
        if value is None or not math.isfinite(value):
            return None
        score += weight * (value - mean) / sd
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, score))))


def _block(raw: Any, allowed: set[str], where: str) -> dict[str, Any]:
    """One horizon's fitted block, checked: known features, matching lengths, finite numbers, sd > 0."""
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: not an object")
    features = raw.get("features")
    if not isinstance(features, list) or not all(isinstance(f, str) for f in features) or len(set(features)) != len(features):
        raise ValueError(f"{where}: features must be distinct names")
    unknown = [f for f in features if f not in allowed]
    if unknown:
        raise ValueError(f"{where}: unknown feature {unknown[0]!r}")
    numbers = {key: raw.get(key) for key in ("mean", "sd", "weights")}
    for key, value in numbers.items():
        size = len(features) + (1 if key == "weights" else 0)
        if (not isinstance(value, list) or len(value) != size
                or not all(type(v) in (int, float) and math.isfinite(v) for v in value)):
            raise ValueError(f"{where}: {key} must be {size} finite numbers")
    if any(sd <= 0 for sd in numbers["sd"]):
        raise ValueError(f"{where}: every sd must be positive")
    return {"features": features, "mean": [float(v) for v in numbers["mean"]], "sd": [float(v) for v in numbers["sd"]],
            "weights": [float(v) for v in numbers["weights"]], "dev_auc": raw.get("dev_auc"),
            "dev_auc_numeric": raw.get("dev_auc_numeric")}


class MoveModel:
    """The frozen move model (`jev_move_model.json`). Loading never raises: what cannot be used is
    listed in `problems`, and the rest still works (a bad Jev block leaves the numeric-only p)."""

    def __init__(self, data: Any, *, source: str = ""):
        self.source = source
        self.problems: list[str] = []
        data = data if isinstance(data, dict) else {}
        self.version = str(data.get("version") or "unknown")
        self.placeholder = self.version == PLACEHOLDER or bool((data.get("fitted_on") or {}).get("placeholder"))
        self.per_market, self.per_state = list(DEFAULT_PER_MARKET), list(DEFAULT_PER_STATE)
        self.jev: dict[int, dict[str, Any]] | None = None
        self.numeric: dict[int, dict[str, Any]] | None = None
        numeric = set(NUMERIC)
        try:
            declared = [row["name"] for row in data.get("numeric") or ()]
            unknown = [name for name in declared if name not in numeric]
            if unknown:
                raise ValueError(f"numeric: unknown feature {unknown[0]!r}")
            self.numeric = {h: _block((data.get("numeric_only") or {}).get(str(h)), numeric, f"numeric_only.{h}")
                            for h in HORIZONS}
        except (ValueError, KeyError, TypeError) as exc:
            self.problems.append(f"numeric-only model refused: {exc}")
        try:
            asked = data.get("questions") or {}
            per_market, per_state = list(asked.get("per_market") or ()), list(asked.get("per_state") or ())
            unknown = [name for name in per_market + per_state if name not in FEATURES]
            if unknown or set(per_market) & set(per_state) or len(set(per_market + per_state)) != len(per_market + per_state):
                raise ValueError(f"questions must be distinct lab questions (unknown: {unknown[:1]})")
            if per_market or per_state:
                self.per_market, self.per_state = per_market, per_state
            allowed = numeric | set(per_market) | set(per_state)
            self.jev = {h: _block((data.get("horizons") or {}).get(str(h)), allowed, f"horizons.{h}") for h in HORIZONS}
        except (ValueError, KeyError, TypeError) as exc:
            self.problems.append(f"Jev model refused: {exc}")
            self.jev = None

    @classmethod
    def load(cls, path: str | Path) -> "MoveModel":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            model = cls({}, source=str(path))
            model.problems = [f"model file unreadable: {type(exc).__name__}: {str(exc)[:120]}"]
            model.numeric = model.jev = None
            return model
        return cls(data, source=str(path))

    @property
    def ready(self) -> bool:
        """A fitted Jev model: move_p can be computed."""
        return self.jev is not None and not self.placeholder

    @property
    def why_not(self) -> str:
        if self.placeholder:
            return f"placeholder model {self.version}: no Jev model yet"
        return next((p for p in self.problems if p.startswith(("Jev model", "model file"))), "")

    def move_p(self, values: Mapping[str, float | None]) -> dict[int, float | None]:
        return {h: logistic(self.jev[h], values) if self.ready else None for h in HORIZONS}

    def numeric_p(self, values: Mapping[str, float | None]) -> dict[int, float | None]:
        return {h: logistic(self.numeric[h], values) if self.numeric is not None else None for h in HORIZONS}


# --------------------------------------------------------------------------- helpers
def event_of(market: str) -> str:
    """The event a Kalshi ticker belongs to: the ticker minus its last '-' segment (the lab's rule)."""
    return market.rsplit("-", 1)[0]


CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("crypto", ("KXBTC", "KXETH", "KXSOL", "KXXRP", "KXDOGE", "KXSHIB", "KXADA", "KXBNB", "KXAVAX", "KXLTC", "KXLINK",
                "KXHYPE", "KXCRYPTO", "BTC", "ETH")),
    ("weather", ("KXHIGH", "KXLOW", "KXRAIN", "KXSNOW", "KXTEMP", "KXHURR", "KXTORNADO", "KXWIND", "KXHEAT", "KXWEATHER",
                 "KXCLIMATE", "HIGH")),
    ("finance", ("KXINX", "KXNASDAQ", "KXSPX", "KXDOW", "KXFED", "KXCPI", "KXPCE", "KXGDP", "KXPAYROLL", "KXJOBS", "KXUNRATE",
                 "KXWTI", "KXBRENT", "KXGOLD", "KXSILVER", "KXDIESEL", "KXAAAGAS", "KXGAS", "KXNATGAS", "KXOIL", "KXCOPPER",
                 "KXEURUSD", "KXUSDJPY", "KXGBPUSD", "KXTNOTE", "KXTREAS", "KX10Y", "KX2Y", "KXMORTGAGE", "INX", "NASDAQ")),
    ("sports", ("KXNFL", "KXNBA", "KXMLB", "KXNHL", "KXNCAA", "KXWNBA", "KXEPL", "KXMLS", "KXUFC", "KXATP", "KXWTA", "KXPGA",
                "KXF1", "KXNASCAR", "KXUCL", "KXLALIGA", "KXSERIEA", "KXBUNDESLIGA", "KXLIGUE", "KXEFL", "KXLIGA", "KXLOL",
                "KXCS2", "KXDOTA", "KXVALORANT", "KXT20", "KXIPL", "KXBOXING", "KXTENNIS", "KXGOLF", "KXSOCCER", "KXARG",
                "KXMVE", "KXCFB", "KXCBB", "KXUEFA", "KXFIFA")),
)


def category(series: str | None, market: str = "") -> str:
    """A coarse desk for the evaluation's breakdown, from the series prefix (else the ticker's)."""
    name = str(series or market.split("-", 1)[0]).upper()
    for label, prefixes in CATEGORIES:
        if name.startswith(prefixes):
            return label
    if any(word in name for word in ("GAME", "MATCH", "FIGHT", "SPREAD", "TOTAL")):
        return "sports"
    return "other"


def _digest(value: Any, size: int = 16) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()[:size]


def _iso(moment: float | None) -> str | None:
    if moment is None:
        return None
    return datetime.fromtimestamp(float(moment), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(text: str) -> float:
    """An ISO timestamp (Z or offset; a bare date is midnight UTC) or epoch seconds."""
    try:
        return float(text)
    except ValueError:
        moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.timestamp()


SCHEMA = """
CREATE TABLE IF NOT EXISTS move_meta(name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS move_quotes(market TEXT NOT NULL, minute INTEGER NOT NULL, bid REAL NOT NULL, ask REAL NOT NULL,
    PRIMARY KEY(market, minute)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS move_rows(id INTEGER PRIMARY KEY, market TEXT NOT NULL, event TEXT NOT NULL, series TEXT,
    observed REAL NOT NULL, minute INTEGER NOT NULL, bid REAL NOT NULL, ask REAL NOT NULL, numeric TEXT NOT NULL,
    answers TEXT, move_p5 REAL, move_p15 REAL, move_p60 REAL, numeric_p5 REAL, numeric_p15 REAL, numeric_p60 REAL,
    model_version TEXT NOT NULL, snapshot INTEGER NOT NULL, recorded_at REAL NOT NULL, why TEXT,
    UNIQUE(market, snapshot, observed));  -- a replaced recordings store numbers its snapshots from 1 again
CREATE INDEX IF NOT EXISTS move_rows_market ON move_rows(market, recorded_at);
CREATE INDEX IF NOT EXISTS move_rows_observed ON move_rows(observed);
CREATE TABLE IF NOT EXISTS move_markets(market TEXT PRIMARY KEY, last_row REAL NOT NULL, last_jev REAL);
"""


@contextmanager
def _connect(path: Path, *, readonly: bool = False):
    if readonly:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    else:
        db = sqlite3.connect(path, timeout=30)
    try:
        if not readonly:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
        yield db
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- the recorder
class MoveSensor:
    """J1's recorder: point-in-time move features for every Kalshi market the House shows."""

    def __init__(self, root: str | Path, sensor: Any, *, clock: Callable[[], float] = time.time,
                 alert: Callable[[str, str], Any] | None = None, settings: Mapping[str, Any] | None = None,
                 model_path: str | Path | None = None, recordings: str | Path | None = None):
        self.root = Path(root)
        self.sensor, self.clock = sensor, clock
        self._alert = alert
        s = dict(settings or {})
        self.interval = float(s.get("interval_seconds", 300))
        self.max_markets = max(1, int(s.get("max_markets_per_cycle", 150)))
        self.retention_days = float(s.get("retention_days", 30))
        self.max_snapshots = max(1, int(s.get("max_snapshots_per_cycle", 1000)))
        self.workers = max(1, int(s.get("workers", 4)))
        self.max_seconds = float(s.get("max_seconds_per_cycle", 150))
        self.usd_share = Decimal(str(s["daily_usd_share"])) if s.get("daily_usd_share") is not None else None
        self.recordings = Path(recordings) if recordings is not None else self.root / "recordings.sqlite"
        self.path = self.root / "jev-features.sqlite"
        self.model = MoveModel.load(s.get("model_path") or model_path or MODEL_PATH)
        for problem in self.model.problems:
            self.alert("warning", f"jev move model ({self.model.source}): {problem}")
        per_market = {name: LAB_QUESTIONS[name] for name in self.model.per_market}
        per_state = {**{name: LAB_QUESTIONS[name] for name in self.model.per_state}, **RECORDED_ONLY}
        self.per_market, self.per_state = per_market, per_state
        self.questions = {**per_market, **per_state}
        # The question-set versions are in the cache keys: a changed text is a new question.
        self._market_version, self._state_version = _digest(per_market, 10), _digest(per_state, 10)
        self._run_lock = threading.Lock()
        self._last_run = 0.0
        self._last_prune = 0.0
        self._last_error = ""
        self.root.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)
        self._stats: dict[str, Any] = {}
        self._refresh_stats(None)

    # ------------------------------------------------------------------ plumbing
    def _db(self, *, readonly: bool = False):
        return _connect(self.path, readonly=readonly)

    def alert(self, level: str, text: str) -> None:
        if self._alert is not None:
            try:
                self._alert(level, text)
            except Exception:  # noqa: BLE001 - an alert that fails must not stop the recorder
                pass

    def _meta(self, db: sqlite3.Connection, name: str) -> str | None:
        row = db.execute("SELECT value FROM move_meta WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _set(db: sqlite3.Connection, **values: Any) -> None:
        db.executemany("INSERT INTO move_meta VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                       [(name, str(value)) for name, value in values.items()])

    def due(self) -> bool:
        return self.clock() - self._last_run >= self.interval

    # ------------------------------------------------------------------ the cycle
    def run(self) -> dict[str, Any] | None:
        """One cycle. A failure is an alert and None, never an exception into the House."""
        if not self._run_lock.acquire(blocking=False):
            return None
        started, began = self.clock(), time.perf_counter()
        self._last_run = started
        cycle: dict[str, Any] | None = None
        try:
            cycle = self._cycle(started)
            self._last_error = ""
        except Exception as exc:  # noqa: BLE001 - the recorder is informational; the House goes on
            text = f"jev move sensor cycle failed ({type(exc).__name__}: {str(exc)[:160]})"
            if text != self._last_error:
                self.alert("warning", text)
            self._last_error = text
            cycle = {"refusal": text}
        finally:
            try:
                if cycle is not None:
                    cycle.update(at=started, seconds=round(time.perf_counter() - began, 3))
                self._refresh_stats(cycle)
            except Exception:  # noqa: BLE001
                pass
            self._run_lock.release()
        return None if self._last_error else cycle

    def _cycle(self, now: float) -> dict[str, Any]:
        if shutil.disk_usage(self.root).free < MIN_FREE_BYTES:
            return {"rows": 0, "refusal": "less than 512 MB free: no labels whose rows cannot be kept"}
        read = self._read_snapshots(now)
        if isinstance(read, str):
            return {"rows": 0, "note": read}
        cursor, snapshots, skipped, bad = read
        shown = self._record_quotes(snapshots)
        cycle: dict[str, Any] = {"snapshots": len(snapshots), "skipped_snapshots": skipped, "bad_snapshots": bad,
                                 "markets_shown": len(shown)}
        rows, jev_rows, refusal, receipt = self._observe(shown, now) if shown else ([], 0, "", {})
        with self._db() as db:
            recorded_at = self.clock()
            db.executemany(
                "INSERT OR IGNORE INTO move_rows(market,event,series,observed,minute,bid,ask,numeric,answers,move_p5,move_p15,"
                "move_p60,numeric_p5,numeric_p15,numeric_p60,model_version,snapshot,recorded_at,why) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [(*row[:17], recorded_at, row[17]) for row in rows])
            db.executemany("INSERT INTO move_markets VALUES(?,?,?) ON CONFLICT(market) DO UPDATE SET last_row=excluded.last_row, "
                           "last_jev=COALESCE(excluded.last_jev, move_markets.last_jev)",
                           [(row[0], row[3], row[3] if row[8] is not None else None) for row in rows])
            day = time.strftime("%Y-%m-%d", time.gmtime(now))
            tally = json.loads(self._meta(db, "today") or "{}")
            if tally.get("day") != day:
                tally = {"day": day, "calls": 0, "bought": 0, "cost_usd": "0", "rows": 0, "jev_rows": 0}
            tally.update(calls=tally["calls"] + int(receipt.get("calls") or 0),
                         bought=tally["bought"] + int(receipt.get("bought") or 0),
                         cost_usd=format(Decimal(tally["cost_usd"]) + Decimal(str(receipt.get("cost") or 0)), "f"),
                         rows=tally["rows"] + len(rows), jev_rows=tally["jev_rows"] + jev_rows)
            self._set(db, cursor=cursor, today=canonical(tally))
        cycle.update(rows=len(rows), jev_rows=jev_rows, calls=int(receipt.get("calls") or 0),
                     cost_usd=format(Decimal(str(receipt.get("cost") or 0)), "f"))
        if refusal:
            cycle["refusal"] = refusal
        if now - self._last_prune >= 3600:
            self._last_prune = now
            cycle["pruned"] = self.prune(now)
        return cycle

    def _read_snapshots(self, now: float) -> str | tuple[int, list[tuple[int, float, list[dict[str, Any]]]], int, int]:
        """New `markets:` snapshots past the cursor, oldest first, at most `max_snapshots` (the
        newest: an older backlog is stale for a point-in-time feature). The first sight of the
        recordings sets the cursor at their newest snapshot and reads nothing."""
        if not self.recordings.exists():
            return "no market recordings yet"
        source = sqlite3.connect(self.recordings.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
        try:
            newest = int(source.execute("SELECT COALESCE(MAX(id),0) FROM snapshots").fetchone()[0])
            with self._db() as db:
                cursor = self._meta(db, "cursor")
                if cursor is None or newest < int(cursor):
                    # First run, or a replaced recordings store: start at its newest snapshot. No back-fill.
                    note = "started" if cursor is None else "recordings replaced"
                    self._set(db, cursor=newest, **({"started_at": now, "started_cursor": newest} if cursor is None else {}))
                    return f"{note}: cursor at snapshot {newest}, nothing earlier is read"
            cursor = int(cursor)
            found = source.execute("SELECT id, received, payload FROM snapshots WHERE id>? AND source LIKE 'markets:%' "
                                   "ORDER BY id DESC LIMIT ?", (cursor, self.max_snapshots)).fetchall()
            skipped = 0
            if len(found) == self.max_snapshots:
                skipped = int(source.execute("SELECT COUNT(*) FROM snapshots WHERE id>? AND id<? AND source LIKE 'markets:%'",
                                             (cursor, found[-1][0])).fetchone()[0])
        finally:
            source.close()
        snapshots, bad = [], 0
        for ident, received, payload in reversed(found):
            try:
                markets = json.loads(gzip.decompress(payload))
            except (OSError, ValueError, EOFError):
                bad += 1
                continue
            valid = [m for m in markets if isinstance(m, dict) and isinstance(m.get("market"), str) and point(m)] \
                if isinstance(markets, list) else []
            if valid:
                snapshots.append((int(ident), float(received), valid))
        return max([newest, *(int(row[0]) for row in found)]), snapshots, skipped, bad

    def _record_quotes(self, snapshots) -> dict[str, tuple[int, float, dict[str, Any], list[dict[str, Any]]]]:
        """Minute quotes of every valid market shown (first in a minute wins), and each market's
        latest appearance: (snapshot id, received, market row, that snapshot's valid rows)."""
        shown: dict[str, tuple[int, float, dict[str, Any], list[dict[str, Any]]]] = {}
        quotes = []
        for ident, received, valid in snapshots:
            bucket = int(received // 60) * 60
            for m in valid:
                q = point(m)
                quotes.append((m["market"], bucket, q["bid"], q["ask"]))
                shown[m["market"]] = (ident, received, m, valid)
        with self._db() as db:
            db.executemany("INSERT OR IGNORE INTO move_quotes VALUES(?,?,?,?)", quotes)
        return shown

    def _allowance(self, now: float) -> int:
        """Markets Jev may be asked about this cycle: the move budget left today, spread evenly over
        the cycles left in the UTC day. Without a pace the cap bound by mid-morning UTC and US hours
        ran numeric-only. The budget is the tighter of the Sensor's call headroom and a dollar share of
        the daily pool (`daily_usd_share`, else the move call cap's share of all calls): the gate,
        triage, links and exposure keep theirs."""
        left = int(self.sensor.headroom(PURPOSE))
        share = self.usd_share
        cap = getattr(self.sensor, "purpose_calls", {}).get(PURPOSE)
        if share is None and cap is not None and getattr(self.sensor, "daily_calls", 0):
            share = Decimal(self.sensor.daily_usd) * Decimal(int(cap)) / Decimal(int(self.sensor.daily_calls))
        if share is not None:
            spent, calls = Decimal(self.sensor.spent_today(PURPOSE)), int(self.sensor.calls_today(PURPOSE))
            per_call = spent / calls if calls >= 20 else DEFAULT_CALL_USD
            left = min(left, max(0, int((share - spent) / max(per_call, Decimal("0.000001")))))
        cycles = max(1, math.ceil(((int(now // 86400) + 1) * 86400 - now) / max(1.0, self.interval)))
        return max(0, math.ceil(left / cycles))

    def _observe(self, shown, now: float) -> tuple[list[tuple], int, str, dict[str, Any]]:
        """Rows for the chosen markets. Returns (rows, rows with Jev answers, refusal, receipt)."""
        names = list(shown)
        history: dict[str, tuple[float, float | None]] = {}
        with self._db() as db:
            for start in range(0, len(names), 500):
                chunk = names[start:start + 500]
                history.update({m: (r, j) for m, r, j in db.execute(
                    f"SELECT market, last_row, last_jev FROM move_markets WHERE market IN ({','.join('?' * len(chunk))})", chunk)})
            # Never-recorded first, then the market recorded longest ago; ties to the most recently shown.
            chosen = sorted(names, key=lambda m: (history.get(m, (0.0, None))[0], -shown[m][1], m))[:self.max_markets]
            states = {}
            for market in chosen:
                ident, received, m, valid = shown[market]
                bucket = int(received // 60) * 60
                prior = [{"observed": float(o), "bid": b, "ask": a} for o, b, a in db.execute(
                    "SELECT minute, bid, ask FROM move_quotes WHERE market=? AND minute<? ORDER BY minute DESC LIMIT 4",
                    (market, bucket))][::-1]
                states[market] = market_state(m, valid, bucket, prior)
        allowance = self._allowance(now)
        # Jev's turn goes round the same way, by when a market last had answers.
        asked = sorted(chosen, key=lambda m: ((history.get(m) or (0.0, None))[1] or 0.0, -shown[m][1], m))[:allowance]
        results: dict[str, tuple[dict[str, float | None] | None, str]] = {}
        receipt: dict[str, Any] = {"calls": 0, "cost": Decimal(0), "bought": 0}
        lock = threading.Lock()
        deadline = time.monotonic() + self.max_seconds

        def ask(market: str) -> None:
            if time.monotonic() > deadline:
                results[market] = (None, "the cycle's time budget is spent")
                return
            state, m = states[market], shown[market][2]
            static = _digest({k: m[k] for k in STATIC_FIELDS if k in m})
            keys = {name: f"move:m:{self._market_version}:{market}:{static}:{name}" for name in self.per_market}
            mine: dict[str, Any] = {}
            try:
                answers = self.sensor.ask_state(PURPOSE, f"move:s:{self._state_version}:{_digest(state, 32)}", state,
                                                self.questions, receipt=mine, keys=keys)
            except Exception as exc:  # noqa: BLE001 - one market's failure is that row's null, not the cycle's
                answers, mine = {}, {"refused": f"{type(exc).__name__}: {str(exc)[:80]}"}
            with lock:
                receipt["calls"] += int(mine.get("calls") or 0)
                receipt["cost"] += Decimal(str(mine.get("cost") or 0))
                receipt["bought"] += int(mine.get("bought") or 0)
            results[market] = (answers, str(mine.get("refused") or ""))

        if asked:
            with ThreadPoolExecutor(max_workers=min(self.workers, len(asked))) as pool:
                list(pool.map(ask, asked))
        rows, with_jev, refusal = [], 0, ""
        for market in chosen:
            ident, received, m, _ = shown[market]
            state = states[market]
            numeric = numeric_features(state)
            answers, why = results.get(market, (None, "paced: this cycle's share of today's move budget is spent"))
            answers = dict(answers or {})
            complete = bool(answers) and all(answers.get(name) is not None for name in self.questions)
            values: dict[str, float | None] = {**numeric, **{k: v for k, v in answers.items() if k in FEATURES}}
            move, base = self.model.move_p(values), self.model.numeric_p(numeric)
            reasons = []
            if not self.model.ready:
                reasons.append(self.model.why_not or "no Jev model")
            if not complete:
                reasons.append(f"jev: {why or 'no answer'}")
                refusal = refusal or f"jev: {why or 'no answer'}"
            if any(v is not None for v in answers.values()):
                with_jev += 1
            q = point(m)
            rows.append((market, event_of(market), m.get("series"), received, int(received // 60) * 60, q["bid"], q["ask"],
                         canonical({k: round(v, 6) for k, v in numeric.items()}),
                         canonical({k: (round(v, 6) if v is not None else None) for k, v in answers.items()})
                         if any(v is not None for v in answers.values()) else None,
                         *(None if move[h] is None else round(move[h], 6) for h in HORIZONS),
                         *(None if base[h] is None else round(base[h], 6) for h in HORIZONS),
                         self.model.version, ident, "; ".join(reasons) or None))
        return rows, with_jev, refusal, receipt

    def prune(self, now: float | None = None) -> dict[str, int]:
        """Keep `retention_days` of quotes, rows and markets; drop this sensor's cached Jev answers
        once they cannot recur (a state's after a day, a market's text after the retention)."""
        now = self.clock() if now is None else now
        cutoff = now - self.retention_days * 86400
        with self._db() as db:
            out = {"quotes": db.execute("DELETE FROM move_quotes WHERE minute<?", (cutoff,)).rowcount,
                   "rows": db.execute("DELETE FROM move_rows WHERE observed<?", (cutoff,)).rowcount,
                   "markets": db.execute("DELETE FROM move_markets WHERE last_row<?", (cutoff,)).rowcount}
        forget = getattr(self.sensor, "forget", None)
        if callable(forget):
            out["answers"] = int(forget("move:s:", now - 86400)) + int(forget("move:m:", cutoff))
        return out

    # ------------------------------------------------------------------ reads
    def latest(self, market: str, at: float) -> dict[str, Any] | None:
        """The newest row for `market` that existed at `at` (recorded_at <= at): what a live wake
        or a replay at `at` may read. `age_seconds` is how old its observation is at `at`."""
        with self._db(readonly=True) as db:
            row = db.execute("SELECT move_p5, move_p15, move_p60, model_version, observed FROM move_rows "
                             "WHERE market=? AND recorded_at<=? ORDER BY recorded_at DESC, id DESC LIMIT 1",
                             (market, float(at))).fetchone()
        if row is None:
            return None
        return {"move_p5": row[0], "move_p15": row[1], "move_p60": row[2], "model_version": row[3],
                "age_seconds": round(float(at) - float(row[4]), 3)}

    def evaluate(self, cutoff: float, horizons: Sequence[int] = HORIZONS, **kw: Any) -> dict[str, Any]:
        return evaluate(self.path, cutoff, horizons, **kw)

    def _refresh_stats(self, cycle: dict[str, Any] | None) -> None:
        """Counted once a cycle, in the background job, so health.json never waits on the store."""
        with self._db() as db:
            rows = db.execute("SELECT COUNT(*) FROM move_rows").fetchone()[0]
            markets = db.execute("SELECT COUNT(*) FROM move_markets").fetchone()[0]
            today = json.loads(self._meta(db, "today") or "{}")
            started_at, cursor = self._meta(db, "started_at"), self._meta(db, "cursor")
        day = time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
        if today.get("day") != day:
            today = {"day": day, "calls": 0, "bought": 0, "cost_usd": "0", "rows": 0, "jev_rows": 0}
        last = dict(cycle or self._stats.get("last_cycle") or {})
        self._stats = {"model_version": self.model.version, "model_ready": self.model.ready,
                       "model_problems": list(self.model.problems), "rows": int(rows), "markets": int(markets),
                       "started_at": _iso(float(started_at)) if started_at else None,
                       "cursor": int(cursor) if cursor is not None else None, "today": today,
                       "labels_bought_today": int(today.get("bought") or 0),
                       "last_cycle_at": _iso(last.get("at")), "last_cycle_seconds": last.get("seconds"),
                       "last_cycle": {k: v for k, v in last.items() if k not in ("at", "seconds")},
                       "refusal": last.get("refusal"), "interval_seconds": self.interval,
                       "max_markets_per_cycle": self.max_markets,
                       "authority": "labels only: no order, promotion, spending or merge authority"}

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)


# --------------------------------------------------------------------------- evaluation
class _Ranked:
    """Scores sorted once into tie groups of event indices, so a bootstrap resample's AUC is one
    weighted pass (events drawn with replacement are weights), not a sort per resample."""

    def __init__(self, scores: Sequence[float], labels: Sequence[int], events: Sequence[int]):
        order = sorted(range(len(scores)), key=scores.__getitem__)
        self.groups: list[tuple[list[int], list[int]]] = []
        last = None
        for i in order:
            if last is None or scores[i] != last:
                self.groups.append(([], []))
                last = scores[i]
            self.groups[-1][0 if labels[i] else 1].append(events[i])

    def auc(self, weights: Sequence[int] | None = None) -> float | None:
        below = numerator = positives = negatives = 0.0
        for pos, neg in self.groups:
            p = len(pos) if weights is None else sum(weights[e] for e in pos)
            n = len(neg) if weights is None else sum(weights[e] for e in neg)
            numerator += p * (below + 0.5 * n)
            below += n
            positives += p
            negatives += n
        return numerator / (positives * negatives) if positives and negatives else None


def _quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def auc_with_interval(scores: Sequence[float], labels: Sequence[int], events: Sequence[str], *,
                      reps: int = 200, seed: int = 7) -> dict[str, Any]:
    """AUC (ties averaged) with a 95% event-clustered bootstrap interval (events resampled with replacement)."""
    index = {e: n for n, e in enumerate(dict.fromkeys(events))}
    ranked = _Ranked(scores, labels, [index[e] for e in events])
    point_estimate = ranked.auc()
    out: dict[str, Any] = {"auc": None if point_estimate is None else round(point_estimate, 4), "ci95": None,
                           "rows": len(scores), "events": len(index)}
    if point_estimate is None or len(index) < 2 or reps <= 0:
        return out
    rng, size, draws = random.Random(seed), len(index), []
    for _ in range(reps):
        weights = [0] * size
        for pick in rng.choices(range(size), k=size):
            weights[pick] += 1
        value = ranked.auc(weights)
        if value is not None:
            draws.append(value)
    if draws:
        out["ci95"] = [round(_quantile(draws, 0.025), 4), round(_quantile(draws, 0.975), 4)]
    return out


def evaluate(store: str | Path, cutoff: float, horizons: Iterable[int] = HORIZONS, *, reps: int = 200,
             seed: int = 7) -> dict[str, Any]:
    """Held-out evaluation of recorded rows observed at or after `cutoff`, read-only.

    Outcome: the market's first own minute quote in [observed + h, observed + h + 10 min]. "Moves at
    all": |that mid - the row's mid| > 1e-9 (the lab's target). Rows without an outcome quote are
    left out. For each horizon, overall and per coarse category, it reports rows, events, the base
    rate and the AUC of move_p, of numeric_p and of the recorded-only `moves_*` answers, each on the
    rows where it exists, with a seeded 95% event-clustered bootstrap interval. Entry is the
    observation. A consumer reads a row at `recorded_at` (up to one cycle later), so a live
    strategy sees a slightly shorter horizon than measured here."""
    path = Path(store)
    horizons = [int(h) for h in horizons]
    with _connect(path, readonly=True) as db:
        rows = db.execute("SELECT market, event, series, observed, bid, ask, answers, move_p5, move_p15, move_p60, "
                          "numeric_p5, numeric_p15, numeric_p60, model_version FROM move_rows WHERE observed>=? "
                          "ORDER BY observed, id", (float(cutoff),)).fetchall()
        outcomes: dict[int, list[int | None]] = {}
        for h in horizons:
            found = []
            for market, _, _, observed, bid, ask, *_ in rows:
                quote = db.execute("SELECT bid, ask FROM move_quotes WHERE market=? AND minute>=? AND minute<=? "
                                   "ORDER BY minute LIMIT 1", (market, observed + 60 * h, observed + 60 * h + 600)).fetchone()
                found.append(None if quote is None else int(abs((quote[0] + quote[1]) / 2 - (bid + ask) / 2) > 1e-9))
            outcomes[h] = found
    models = sorted({row[13] for row in rows})
    report: dict[str, Any] = {"store": str(path), "cutoff": _iso(cutoff), "rows_after_cutoff": len(rows),
                              "model_versions": models, "target": "the quoted midpoint moves at all (|change| > 1e-9)",
                              "ship_rule": f"move_p's held-out AUC >= {SHIP_AUC} on post-ship events", "horizons": {}}
    column = {5: 7, 15: 8, 60: 9}
    for h in horizons:
        kept = [(row, y) for row, y in zip(rows, outcomes[h]) if y is not None]

        def block(subset: list[tuple[tuple, int]]) -> dict[str, Any]:
            scores: dict[str, list[tuple[float, int, str]]] = {"move_p": [], "numeric_p": [], **{k: [] for k in RECORDED_ONLY}}
            for row, y in subset:
                if h in column and row[column[h]] is not None:
                    scores["move_p"].append((row[column[h]], y, row[1]))
                if h in column and row[column[h] + 3] is not None:
                    scores["numeric_p"].append((row[column[h] + 3], y, row[1]))
                answers = json.loads(row[6]) if row[6] else {}
                for name in RECORDED_ONLY:
                    if answers.get(name) is not None:
                        scores[name].append((float(answers[name]), y, row[1]))
            out = {"rows": len(subset), "events": len({row[1] for row, _ in subset}),
                   "base_rate": round(sum(y for _, y in subset) / len(subset), 4) if subset else None, "auc": {}}
            for name, triples in scores.items():
                if triples:
                    s, ys, es = zip(*triples)
                    out["auc"][name] = auc_with_interval(s, ys, es, reps=reps, seed=seed)
                else:
                    out["auc"][name] = {"auc": None, "ci95": None, "rows": 0, "events": 0}
            return out

        overall = block(kept)
        move_auc = overall["auc"]["move_p"]["auc"]
        overall["meets_ship_rule"] = None if move_auc is None else move_auc >= SHIP_AUC
        by: dict[str, list[tuple[tuple, int]]] = {}
        for row, y in kept:
            by.setdefault(category(row[2], row[0]), []).append((row, y))
        report["horizons"][str(h)] = {"overall": overall, "by_category": {k: block(v) for k, v in sorted(by.items())}}
    return report


def _print(report: Mapping[str, Any], out: Any) -> None:
    print(f"{report['store']}: {report['rows_after_cutoff']} rows observed at or after {report['cutoff']} "
          f"(models {', '.join(report['model_versions']) or 'none'}); {report['ship_rule']}", file=out)

    def cell(entry: Mapping[str, Any]) -> str:
        if entry["auc"] is None:
            return "-"
        ci = entry["ci95"]
        return f"{entry['auc']:.3f}" + (f" [{ci[0]:.3f},{ci[1]:.3f}]" if ci else "") + f" n={entry['rows']}"

    for h, found in report["horizons"].items():
        print(f"\n{h} min", file=out)
        for label, entry in [("overall", found["overall"]), *found["by_category"].items()]:
            aucs = "  ".join(f"{name}={cell(value)}" for name, value in entry["auc"].items())
            print(f"  {label:9s} rows={entry['rows']} events={entry['events']} base={entry['base_rate']}  {aucs}", file=out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m league.jev_features", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    ev = commands.add_parser("evaluate", help="held-out AUC of the recorded move feature (read-only)")
    ev.add_argument("--store", required=True, help="jev-features.sqlite (opened read-only)")
    ev.add_argument("--cutoff", required=True, help="ISO time (or epoch seconds): only rows observed at or after it")
    ev.add_argument("--horizons", default="5,15,60")
    ev.add_argument("--reps", type=int, default=200, help="bootstrap resamples")
    ev.add_argument("--seed", type=int, default=7)
    ev.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = evaluate(args.store, parse_time(args.cutoff), [int(h) for h in args.horizons.split(",") if h.strip()],
                      reps=args.reps, seed=args.seed)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print(report, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
