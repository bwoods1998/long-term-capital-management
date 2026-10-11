"""Release E3, package B (league/ops/forward_shadow.py): the nightly recompute of every registered program on its own
forward days. The seals T6 (`NoDayBeforeItsCodeExisted`, `TheSealedDaysNeedTheCapability`), D3's rows against the
screen's own accounting, D4's checkpoints (golden values, the one-day lag, the checkpoint of record, the final one),
the bars hash on every new row and the history-0 first decision, a restated day as data, whose failure a failure is
(the House's, the data's, the child's, the program's own), the budget and the order, the quiet window, a killed night
resumed, a new engine label, the controls' rows and the job.

Every store here is `league.equity.synth`'s (geometric Brownian motion on the true NYSE calendar, never market data);
every program, registry row and number is invented. The runs go through E1's real engine in an `InlineDecider`.

THE FAKES. Package B is built beside four others, so what it calls of them is faked here to the contract
(league/ops/E3_INTERFACES.md), each fake a reference reading of its stub's docstring:
- ALWAYS faked (another package's behaviour, never this file's subject): `forward_register.sync` (A) and
  `forward_twins.begin`, `on_run`, `finish` (D): recorders, so a test says what they did that night;
- faked ONLY WHILE THE REAL ONE IS STILL STEP 0's STUB (`is_stub`; `install`): the `forward_db` functions (A), the two
  `forward_stats` functions the checkpoints read (C) and the control draw (A). Once those packages land, the same
  tests run on the real functions.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import shutil
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence
from unittest import mock

import numpy as np

from league.equity import EQUITY_ENGINE_VERSION, config, results, runner, schedule, screen, synth
from league.equity import ctx as eq_ctx
from league.equity.program import load_program, parse_needs
from league.equity.store import (STORE_DIR, EquityStore, StoreRefused, from_ordinal, mint_equity_gate_capability,
                                 ordinal, write_store)
from league.live.decider import Decider, DeciderError, InlineDecider
from league.ops import forward_controls, forward_db, forward_register, forward_shadow, forward_stats, forward_twins
from league.ops.context import Context

# ------------------------------------------------------------------------------------------------- the synthetic days
SYMBOLS = ("SPY", "QQQ", "IWM", "DIA")
START, END = dt.date(2026, 6, 1), dt.date(2027, 3, 31)
#: D1's first forward day, computed as the contract computes it (never a literal date).
T0 = schedule.next_session(config.LOOK_CAP)
#: The session before it (the look cap's own): the close a program in from the first forward day decides at.
BEFORE = schedule.previous_session(T0)


def _forward(n: int) -> list[dt.date]:
    out = [T0]
    while len(out) < n:
        out.append(schedule.next_session(out[-1]))
    return out


#: The first forward days (FWD[0] is `T0`).
FWD = _forward(70)
RECORD: dict[str, Any] = {"elane": {"forward": {"mode": "record"}}}


def evening(day: dt.date) -> float:
    """18:30 New York time on `day`: when the job runs (after the daily store, outside the quiet window)."""
    return dt.datetime.combine(day, dt.time(18, 30), schedule.NY).timestamp()


def write_night(root: Path, through: dt.date, *, gaps: Mapping[str, Sequence[dt.date]] | None = None,
                gate: bool = True, dividends: Mapping[str, Sequence[tuple[dt.date, float]]] | None = None) -> Path:
    """The House's store as the daily job left it the evening of `through` (the same synthetic path every night; a
    dividend is in its adjusted prices from its ex-day's fetch on)."""
    return synth.synthetic_store(Path(root) / STORE_DIR, symbols=SYMBOLS, start=START, end=END, seed=7, gate=gate,
                                 as_of=through, gaps=gaps, dividends=dividends)


def rewrite(root: Path, change: Any) -> None:
    """Write the store again with `change(symbol, arrays, days)` applied to every symbol's columns."""
    store_root = Path(root) / STORE_DIR
    manifest = json.loads((store_root / "manifest.json").read_text())
    with np.load(store_root / "calendar.npz") as cal:
        calendar = [(from_ordinal(int(d)), bool(e)) for d, e in zip(cal["days"], cal["early"])]
    series: dict[str, dict[str, Any]] = {}
    for sym in manifest["symbols"]:
        with np.load(store_root / "bars" / f"{sym}.npz") as npz:
            arrays = {name: npz[name].copy() for name in npz.files}
        days = [from_ordinal(int(d)) for d in arrays["days"]]
        change(sym, arrays, days)
        series[sym] = {"days": days, **{name: arrays[name].tolist() for name in arrays if name != "days"}}
    write_store(store_root, calendar=calendar, series=series,
                classes={s: row["class"] for s, row in manifest["symbols"].items()},
                fetched_through=dt.date.fromisoformat(manifest["fetched_through"]), source="synthetic", gate=True)


def perturb(root: Path, symbol: str, day: dt.date, factor: float) -> None:
    """Rewrite the store with `symbol`'s close of `day` moved (raw and adjusted): a vendor's correction."""
    def change(sym: str, arrays: dict[str, Any], days: list[dt.date]) -> None:
        if sym == symbol:
            for column in ("raw_c", "all_c"):
                arrays[column][days.index(day)] = round(float(arrays[column][days.index(day)]) * factor, 4)

    rewrite(root, change)


def cents(root: Path) -> None:
    """Rewrite the store with every price rounded to the cent, as the vendor's adjustment=all series is (THE BARS
    HASH, league/ops/forward_db.py)."""
    def change(sym: str, arrays: dict[str, Any], days: list[dt.date]) -> None:
        for column in arrays:
            if column.startswith(("raw_", "all_")) and column != "raw_v":
                arrays[column] = np.round(arrays[column], 2)

    rewrite(root, change)


def gated(root: Path) -> EquityStore:
    store_root = Path(root) / STORE_DIR
    return EquityStore(store_root, gate=mint_equity_gate_capability(store_root, "a test's"))


# ------------------------------------------------------------------------------------------------------- the programs
ALWAYS = '''NEEDS = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 60}
PARAMS = {}


def decide(ctx):
    if ctx.positions:
        return []
    return [{"buy": "SPY", "share": 0.5, "at": "open"}]
'''
#: The same with no history: its first decision must still fall at `first_close`.
HISTORY_0 = ALWAYS.replace('"history": 5', '"history": 0')
#: Buys only once it reads its full history (NEEDS history + 1 sessions, as the live book hands it at every close).
WAITS = '''NEEDS = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 60}
PARAMS = {}


def decide(ctx):
    if len(ctx.bars["SPY"].close) < 6 or ctx.positions:
        return []
    return [{"buy": "SPY", "share": 0.5, "at": "open"}]
'''
#: In and out every few sessions, at the close and at the open: entries and exits on many days.
FLIPPER = '''NEEDS = {"symbols": ["SPY", "QQQ"], "history": 3, "max_hold_sessions": 5}
PARAMS = {}


def decide(ctx):
    out = []
    for lot in ctx.positions:
        if lot["held_sessions"] >= 1:
            out.append({"sell": lot["id"], "at": "open"})
    if not ctx.positions:
        out.append({"buy": "QQQ", "share": 0.3, "at": "close"})
    return out
'''
#: Buys at its FIRST call only: if STATE outlived a run, a second recompute would not buy.
STATE = '''NEEDS = {"symbols": ["SPY"], "history": 0, "max_hold_sessions": 3}
PARAMS = {}
CALLS = [0]


def decide(ctx):
    CALLS[0] += 1
    if CALLS[0] == 1:
        return [{"buy": "SPY", "share": 0.4, "at": "close"}]
    return []
'''
#: Raises at every call: disqualified at its 25th error.
BROKEN = '''NEEDS = {"symbols": ["SPY"], "history": 1, "max_hold_sessions": 5}
PARAMS = {}


def decide(ctx):
    return 1 // 0
'''
ON_DIA = ALWAYS.replace('"SPY"', '"DIA"')
#: Does not pass the safety check: the child refuses to load it.
REFUSED = "import os\n" + ALWAYS


# --------------------------------------------------------------------------------------------------------- the fakes
def is_stub(fn: Any) -> bool:
    """Whether a contract function is still step 0's stub (its body raises `NotImplementedError`)."""
    code = getattr(fn, "__code__", None)
    return code is not None and "NotImplementedError" in code.co_names


def fake_cfg(settings: Any) -> dict[str, Any]:
    out = dict(forward_db.DEFAULTS)
    raw = settings.get("elane") if isinstance(settings, Mapping) else None
    raw = raw.get("forward") if isinstance(raw, Mapping) else None
    if not isinstance(raw, Mapping):
        return out
    if raw.get("mode") in forward_db.MODES:
        out["mode"] = raw["mode"]
    for key, (low, high) in forward_db.BOUNDS.items():
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            out[key] = type(forward_db.DEFAULTS[key])(min(high, max(low, value)))
    for key in ("fill_minutes", "twins"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    return out


def fake_mode(settings: Any) -> str:
    return forward_db.cfg(settings)["mode"]


def fake_t0() -> dt.date:
    return schedule.next_session(config.LOOK_CAP)


def fake_fwd_engine() -> str:
    return EQUITY_ENGINE_VERSION + "+" + "0" * 12 + "+" + forward_db.FWD_SERIES


def fake_event(db: sqlite3.Connection, kind: str, *, pid: int | None = None, day: str | None = None,
               payload: Mapping[str, Any] | None = None, at: float, once: str | None = None) -> int:
    body = dict(payload or {})
    if once is not None:
        for row in db.execute("SELECT payload FROM fwd_events WHERE kind=? AND pid IS ? AND day IS ?",
                              (kind, pid, day)).fetchall():
            if json.loads(row[0]).get("once") == once:
                return 0
        body["once"] = once
    cursor = db.execute("INSERT INTO fwd_events(at, kind, pid, day, payload) VALUES (?,?,?,?,?)",
                        (float(at), kind, pid, day, json.dumps(body, sort_keys=True)))
    return int(cursor.lastrowid)


def fake_events(db: sqlite3.Connection, kind: str, *, pid: int | None = None, since: float | None = None
                ) -> list[dict[str, Any]]:
    out = []
    for row in db.execute("SELECT seq, at, kind, pid, day, payload FROM fwd_events WHERE kind=? ORDER BY seq",
                          (kind,)).fetchall():
        if (pid is None or row[3] == pid) and (since is None or row[1] >= since):
            out.append({"seq": row[0], "at": row[1], "kind": row[2], "pid": row[3], "day": row[4],
                        "payload": json.loads(row[5])})
    return out


def fake_kv_first(db: sqlite3.Connection, key: str, value: Any) -> bool:
    if db.execute("SELECT 1 FROM fwd_kv WHERE key=?", (key,)).fetchone() is not None:
        return False
    db.execute("INSERT INTO fwd_kv(key, value) VALUES (?,?)", (key, json.dumps(value)))
    return True


def fake_open_db(root: str | Path, *, readonly: bool = False) -> sqlite3.Connection:
    from league.ops import guard

    path = Path(root) / forward_db.DB
    if readonly:
        return guard.connect_ro(path)
    db = sqlite3.connect(path)
    path.chmod(0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(forward_db.SCHEMA)
    if forward_db.kv_first(db, "fgs_prereg", forward_db.FGS_SHA):
        forward_db.event(db, "prereg", payload={"why": "the forward screen's shape, pinned", "sha": forward_db.FGS_SHA,
                                                "fgs": forward_db.FGS}, at=0.0, once="fgs")
    db.commit()
    return db


def fake_row_hash(prev_hash: str, row: Mapping[str, Any]) -> str:
    return hashlib.sha256((prev_hash + "\n" + results.canonical({k: row[k] for k in forward_db.HASHED}) + "\n" +
                           hashlib.sha256(row["code"].encode()).hexdigest()).encode()).hexdigest()


def fake_verify_chain(db: sqlite3.Connection) -> dict[str, Any]:
    prev, rows = forward_db.GENESIS, 0
    for row in db.execute("SELECT * FROM fwd_registry ORDER BY pid").fetchall():
        rows += 1
        if row["prev_hash"] != prev or row["row_hash"] != forward_db.row_hash(prev, dict(row)):
            return {"ok": False, "rows": db.execute("SELECT COUNT(*) FROM fwd_registry").fetchone()[0],
                    "head": forward_db.head(db), "first_bad": row["pid"]}
        prev = row["row_hash"]
    return {"ok": True, "rows": rows, "head": prev, "first_bad": None}


def fake_head(db: sqlite3.Connection) -> str:
    row = db.execute("SELECT row_hash FROM fwd_registry ORDER BY pid DESC LIMIT 1").fetchone()
    return forward_db.GENESIS if row is None else str(row[0])


def fake_engine_id(db: sqlite3.Connection, label: str, *, at: float) -> tuple[int, bool]:
    row = db.execute("SELECT id FROM fwd_engines WHERE label=?", (label,)).fetchone()
    if row is not None:
        return int(row[0]), False
    return int(db.execute("INSERT INTO fwd_engines(label, at) VALUES (?,?)", (label, float(at))).lastrowid), True


def fake_engine_now(db: sqlite3.Connection) -> int | None:
    row = db.execute("SELECT MAX(id) FROM fwd_engines").fetchone()
    return None if row is None or row[0] is None else int(row[0])


def fake_engine_label(db: sqlite3.Connection, id: int) -> str | None:  # noqa: A002 - the contract's name
    row = db.execute("SELECT label FROM fwd_engines WHERE id=?", (id,)).fetchone()
    return None if row is None else str(row[0])


def _as_program(row: Any) -> forward_db.Program:
    return forward_db.Program(
        pid=int(row["pid"]), key=row["key"], family=row["family"], version=row["version"], lane=row["lane"],
        reason=row["reason"], ugroup=row["ugroup"], lineage=row["lineage"], code=row["code"],
        params=json.loads(row["params"]), needs=json.loads(row["needs"]), program_sha=row["program_sha"],
        run_sha=row["run_sha"], created_at=float(row["created_at"]),
        first_close=dt.date.fromisoformat(row["first_close"]), first_day=dt.date.fromisoformat(row["first_day"]),
        route=row["route"], alpha_f=row["alpha_f"])


def fake_active(db: sqlite3.Connection, pid: int) -> bool:
    latest = {row[0]: row[1] for row in db.execute(
        "SELECT tag, MAX(at) FROM fwd_tags WHERE pid=? AND tag IN ('stopped', 'resumed') GROUP BY tag", (pid,))}
    return "stopped" not in latest or ("resumed" in latest and latest["resumed"] >= latest["stopped"])


def fake_programs(db: sqlite3.Connection, *, reasons: Sequence[str] | None = None, active: bool = True
                  ) -> list[forward_db.Program]:
    out = []
    for row in db.execute("SELECT * FROM fwd_registry ORDER BY pid").fetchall():
        if reasons is not None and row["reason"] not in reasons:
            continue
        if active and not forward_db.active(db, int(row["pid"])):
            continue
        out.append(_as_program(row))
    return out


def fake_suspect(db: sqlite3.Connection, pid: int) -> bool:
    last = db.execute("SELECT MAX(day) FROM fwd_days WHERE pid=?", (pid,)).fetchone()[0]
    return any(last is None or str(row[0]) >= str(last)
               for row in db.execute("SELECT value FROM fwd_tags WHERE pid=? AND tag='suspect'", (pid,)).fetchall())


def fake_tag(db: sqlite3.Connection, pid: int, tag: str, value: str = "", *, at: float) -> bool:
    if db.execute("SELECT 1 FROM fwd_tags WHERE pid=? AND tag=? AND value=?", (pid, tag, value)).fetchone():
        return False
    db.execute("INSERT INTO fwd_tags(pid, tag, value, at) VALUES (?,?,?,?)", (pid, tag, value, float(at)))
    return True


def fake_counted_days(db: sqlite3.Connection, pid: int, *, engine: int | None = None) -> list[dict[str, Any]]:
    engine = forward_db.engine_now(db) if engine is None else engine
    marked = {row[0] for row in db.execute("SELECT day FROM fwd_events WHERE kind='audit_mismatch' AND pid=?", (pid,))}
    rows = db.execute("SELECT * FROM fwd_days WHERE pid=? AND engine=? AND status='ok' ORDER BY day",
                      (pid, engine)).fetchall()
    return [dict(row) for row in rows if row["day"] not in marked]


def fake_stored_days(db: sqlite3.Connection, pid: int, *, engine: int | None = None) -> int:
    engine = forward_db.engine_now(db) if engine is None else engine
    return int(db.execute("SELECT COUNT(*) FROM fwd_days WHERE pid=? AND engine=?", (pid, engine)).fetchone()[0])


def t_of(values: Sequence[float]) -> float | None:
    """D4's t by hand: mean(x) / sd(x, ddof 1) * sqrt(n), every sum exact; None when sd < 1e-12."""
    xs = [float(v) for v in values]
    n = len(xs)
    if n < 2 or not all(math.isfinite(v) for v in xs):
        return None
    mean = math.fsum(xs) / n
    sd = math.sqrt(math.fsum((v - mean) ** 2 for v in xs) / (n - 1))
    return None if sd < 1e-12 else mean / sd * math.sqrt(n)


def _betacf(a: float, b: float, x: float) -> float:
    """The continued fraction of the regularized incomplete beta function (Lentz's method)."""
    tiny = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        for num in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
                    -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1.0 + num * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + num / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-15:
            break
    return h


def fake_p_one_sided(t: float | None, n: int) -> float | None:
    if t is None or n < 2:
        return None
    df = n - 1.0
    x = df / (df + t * t)
    a, b = df / 2.0, 0.5
    if x <= 0.0 or x >= 1.0:
        tail = 0.0 if x <= 0.0 else 1.0
    else:
        front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
        tail = front * _betacf(a, b, x) / a if x < (a + 1.0) / (a + b + 2.0) else \
            1.0 - front * _betacf(b, a, 1.0 - x) / b
    return 0.5 * tail if t >= 0 else 1.0 - 0.5 * tail


def fake_spec(group: str, n: int, symbols: Sequence[str]) -> dict[str, Any]:
    return {"control": forward_controls.VERSION, "group": group, "n": int(n),
            "f": forward_controls.F_GRID[int(n) // 10], "symbols": list(symbols)}


def fake_control_lots(spec: Mapping[str, Any], sessions: Sequence[dt.date], *, k: float = 1.0) -> list[dict[str, Any]]:
    """A stand-in for A's draw while it is a stub (NOT D5's draw): a lot every sixth session, held three, a pure
    function of the spec and the sessions; `hs` filled as the contract says for k 1.5 and k 0.0."""
    symbols, n = list(spec["symbols"]), int(spec["n"])
    lots = []
    for seq, i in enumerate(range(n % 3, len(sessions) - 1, 6)):
        sym = symbols[(seq + n) % len(symbols)]
        entry, leave = i + 1, i + 4
        hs = None if k == 1.0 else (0.0 if k == 0.0 else k * config.half_spread(sym))
        lots.append({"lid": seq + 1, "symbol": sym, "class": config.class_of(sym), "weight": 0.25,
                     "entry_day": sessions[entry], "entry_at": "open" if seq % 2 == 0 else "close",
                     "exit_day": sessions[leave] if leave < len(sessions) else None, "exit_at": "open", "hs": hs})
    return lots


def fake_cost_free(lots0: Sequence[Mapping[str, Any]], bars: Any, *, capital: Any) -> Any:
    series = screen.series(lots0, bars, universe=list(bars.symbols), capital=capital)
    r0 = np.array(series.r, dtype=np.float64)
    where = {int(d): i for i, d in enumerate(bars.days)}
    e0 = float(capital)
    for lot in lots0:
        if lot.get("exit_day") is None:
            continue
        entry, leave = where[ordinal(lot["entry_day"])], where[ordinal(lot["exit_day"])]
        price = float(bars.adj[lot["symbol"]][entry, 0 if lot["entry_at"] == "open" else 3])
        weight = float(lot["weight"])
        r0[leave - int(bars.first)] += float(config.sell_fees(
            Decimal(str(weight)) * Decimal(str(capital)), Decimal(str(weight * e0 / price)))) / e0
    return r0


#: module -> {name: its fake}; `install` patches a name only while the real one is a stub.
FAKES: dict[Any, dict[str, Any]] = {
    forward_db: {"cfg": fake_cfg, "mode": fake_mode, "t0": fake_t0, "fwd_engine": fake_fwd_engine,
                 "open_db": fake_open_db, "row_hash": fake_row_hash, "verify_chain": fake_verify_chain,
                 "head": fake_head, "event": fake_event, "events": fake_events, "kv_first": fake_kv_first,
                 "engine_id": fake_engine_id, "engine_now": fake_engine_now, "engine_label": fake_engine_label,
                 "programs": fake_programs, "active": fake_active, "suspect": fake_suspect, "tag": fake_tag,
                 "counted_days": fake_counted_days, "stored_days": fake_stored_days},
    forward_stats: {"t_stat": t_of, "p_one_sided": fake_p_one_sided},
    forward_controls: {"spec": fake_spec, "control_lots": fake_control_lots, "cost_free": fake_cost_free},
}


def install(case: unittest.TestCase) -> None:
    """Patch, for one test, every contract function that is still a stub with its fake (THE FAKES)."""
    for module, fakes in FAKES.items():
        for name, fake in fakes.items():
            if is_stub(getattr(module, name)):
                patcher = mock.patch.object(module, name, fake)
                patcher.start()
                case.addCleanup(patcher.stop)


# ------------------------------------------------------------------------------------------------------- the registry
def memory_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(forward_db.SCHEMA)
    return db


def _append(db: sqlite3.Connection, row: dict[str, Any]) -> int:
    """One invented registry row with its chain link (the registry's own job is A's; these rows are a test's)."""
    row["pid"] = int(db.execute("SELECT COALESCE(MAX(pid), 0) + 1 FROM fwd_registry").fetchone()[0])
    row["prev_hash"] = forward_db.head(db)
    row["row_hash"] = forward_db.row_hash(row["prev_hash"], row)
    names = list(row)
    db.execute(f"INSERT INTO fwd_registry({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
               [row[name] for name in names])
    db.commit()
    return row["pid"]


def register(db: sqlite3.Connection, key: str, code: str, *, first_close: dt.date, reason: str = "train_pass",
             needs: Mapping[str, Any] | None = None, first_day: dt.date | None = None) -> int:
    """An invented program row: it existed an hour before the close of `first_close` (D2); its pid."""
    family, _, version = key.partition("@")
    needs = dict(needs) if needs is not None else load_program(code, name=key).needs.as_dict()
    created = schedule.moments(first_close).close_at - 3600.0
    return _append(db, {
        "key": key, "family": family, "version": int(version or 1), "lane": "equity", "reason": reason,
        "ugroup": "index", "lineage": f"equity:{family}", "code": code, "params": results.canonical({}),
        "needs": results.canonical(needs), "program_sha": hashlib.sha256(code.encode()).hexdigest(),
        "run_sha": hashlib.sha256((code + "{}").encode()).hexdigest(), "author": "a test", "created_at": created,
        "evidence": "registry", "first_close": first_close.isoformat(),
        "first_day": (first_day or schedule.next_session(first_close)).isoformat(), "registered_at": created,
        "route": forward_db.E3_ROUTE, "alpha_f": forward_db.E3_ALPHA_F})


def register_control(db: sqlite3.Connection, group: str, n: int, symbols: Sequence[str], *, first_close: dt.date
                     ) -> int:
    """An invented control row as the contract shapes one (league/ops/forward_register.py)."""
    code = results.canonical(forward_controls.spec(group, n, list(symbols)))
    sha = hashlib.sha256(code.encode()).hexdigest()
    created = schedule.moments(first_close).close_at - 3600.0
    return _append(db, {
        "key": f"control:{group}:{n}", "family": None, "version": None, "lane": "control", "reason": "control",
        "ugroup": group, "lineage": f"control:{group}:{n}", "code": code, "params": "{}",
        "needs": results.canonical({"symbols": list(symbols), "history": 1, "max_hold_sessions": 20}),
        "program_sha": sha, "run_sha": sha, "author": "house", "created_at": created, "evidence": "registry",
        "first_close": first_close.isoformat(), "first_day": schedule.next_session(first_close).isoformat(),
        "registered_at": created, "route": forward_db.CONTROL_ROUTE, "alpha_f": forward_db.CONTROL_ALPHA_F})


# -------------------------------------------------------------------------------------------------------- the deciders
class Killed(BaseException):
    """The job's process dying mid-night (a test's)."""


class Ticking(InlineDecider):
    """E1's `InlineDecider` with a test's hands on it: every "run" costs `cost` seconds of the case's clock and is
    recorded; a run of a program in `broken` fails as a killed child does (`DeciderError`); one in `kill` ends the
    process; `closed` counts its `close` calls."""

    def __init__(self, case: Any, cost: float = 0.0, *, broken: Sequence[str] = (), kill: Sequence[str] = ()):
        super().__init__()
        self.case, self.cost, self.broken, self.kill = case, float(cost), set(broken), set(kill)
        self.runs: list[tuple[str, float]] = []
        self.closed = 0

    def kind(self, kind: str, op: str, payload: Mapping[str, Any], *, budget_seconds: float | None = None) -> dict:
        if op == "run":
            name = str(payload["name"])
            self.runs.append((name, float(payload["k"])))
            self.case.t += self.cost
            if name in self.kill:
                raise Killed(name)
            if name in self.broken:
                self.restarts += 1
                raise DeciderError("the decider exited; the child was killed (a test's)")
        return super().kind(kind, op, payload, budget_seconds=budget_seconds)

    def close(self) -> None:
        self.closed += 1


class Dead:
    """A decider that cannot start: the House's (league/live/decider.py refuses a child off a root House)."""

    def __init__(self) -> None:
        self.closed = 0

    def ping(self) -> dict:
        raise DeciderError("the production decider requires a network namespace under its separate uid")

    def kind(self, *args: Any, **kwargs: Any) -> dict:
        raise DeciderError("no child")

    def close(self) -> None:
        self.closed += 1


# ------------------------------------------------------------------------------------------------------------ the case
class Case(unittest.TestCase):
    """A state root with a synthetic store, an in-memory forward store, a clock a test moves, and the two other
    packages a night calls recorded (THE FAKES)."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="eqe3-shadow-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        install(self)
        self.db = memory_db()
        self.addCleanup(self.db.close)
        self.t = evening(FWD[0])
        self.synced: list[float] = []
        self.on_sync: Any = None
        self.twins: dict[str, Any] = {"begin": [], "on_run": [], "finish": [], "order": []}
        self.twins_raise = False
        for module, name, fake in ((forward_register, "sync", self._sync), (forward_twins, "begin", self._begin),
                                   (forward_twins, "on_run", self._on_run), (forward_twins, "finish", self._finish)):
            patcher = mock.patch.object(module, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    # A's and D's, recorded.
    def _sync(self, root: Any, db: sqlite3.Connection, *, now: float, settings: Any) -> dict[str, Any]:
        self.synced.append(now)
        if self.on_sync is not None:
            self.on_sync(db)
        return {"registered": 0, "controls": 0, "tagged": 0, "stopped": 0, "suspect": 0, "skipped": [],
                "chain": {"ok": True, "rows": 0, "head": forward_db.head(db), "first_bad": None}}

    def _begin(self, root: Any, db: sqlite3.Connection, shadow: Any, *, now: float) -> dict[str, Any]:
        self.twins["order"].append("begin")
        self.twins["begin"].append(shadow)
        if self.twins_raise:
            raise RuntimeError("the twins failed (a test's)")
        return {"days": 0, "rows": 0}

    def _on_run(self, db: sqlite3.Connection, run: Any, *, now: float, settings: Any) -> int:
        self.twins["order"].append("on_run")
        stored = db.execute("SELECT COUNT(*) FROM fwd_days WHERE pid=?", (run.program.pid,)).fetchone()[0]
        self.twins["on_run"].append((run.program.pid, int(stored), type(run).__name__))
        if self.twins_raise:
            raise RuntimeError("the twins failed (a test's)")
        return 1

    def _finish(self, root: Any, db: sqlite3.Connection, shadow: Any, *, now: float) -> dict[str, Any]:
        self.twins["order"].append("finish")
        self.twins["finish"].append(shadow)
        if self.twins_raise:
            raise RuntimeError("the twins failed (a test's)")
        return {"instances": 0, "twins": 0, "disagreed": 0, "lots": 0, "interrupted": 0, "live_bars": 0}

    def clock(self) -> float:
        return self.t

    def shadow(self, through: dt.date, *, decider: Any = None, settings: Any = RECORD, fresh: Any = None,
               gaps: Any = None, write: bool = True) -> forward_shadow.Shadow:
        """The night of `through`: the store as the daily job left it (`write` False: as a test left it), the clock
        at that evening."""
        if write:
            write_night(self.root, through, gaps=gaps)
        self.t = max(self.t, evening(through))
        return forward_shadow.Shadow(self.root, self.db, decider=decider or InlineDecider(), settings=settings,
                                     clock=self.clock, fresh=fresh)

    def night(self, through: dt.date, **kwargs: Any) -> dict[str, Any]:
        return self.shadow(through, **kwargs).night()

    def program(self, pid: int) -> forward_db.Program:
        return next(p for p in forward_db.programs(self.db, active=False) if p.pid == pid)

    def rows(self, pid: int | None = None, *, engine: int | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM fwd_days WHERE 1=1", []
        for column, value in (("pid", pid), ("engine", engine)):
            if value is not None:
                sql, args = sql + f" AND {column}=?", [*args, value]
        return [dict(row) for row in self.db.execute(sql + " ORDER BY pid, engine, day", args).fetchall()]

    def checks(self, pid: int) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute("SELECT * FROM fwd_checks WHERE pid=? ORDER BY at, n, engine",
                                                     (pid,)).fetchall()]

    def events(self, kind: str, pid: int | None = None) -> list[dict[str, Any]]:
        return forward_db.events(self.db, kind, pid=pid)

    def count(self, table: str) -> int:
        return int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def hash_at(self, bars: Any, index: int, needs: Mapping[str, Any]) -> str:
        """THE BARS HASH of the decision at session `index` of `bars`, made here from E1's own inputs."""
        return forward_db.bars_hash(eq_ctx.inputs_from_bars(bars, index, needs=parse_needs(needs), cash=0.0,
                                                            equity=0.0, budget=0.0, caps={}, params={}))


def iso(days: Sequence[dt.date]) -> list[str]:
    return [d.isoformat() for d in days]


# ================================================================================================================ T6
class NoDayBeforeItsCodeExisted(Case):
    """T6, D2: a program first decides at the close of `first_close`, has no fill, mark or P&L before `first_day`,
    and no forward day is before `t0()`."""

    def test_the_first_row_is_first_day_and_the_first_decision_is_at_first_close(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=FWD[2])
        self.night(FWD[6])
        rows = self.rows(pid)
        self.assertEqual([row["day"] for row in rows], iso(FWD[3:7]))
        # Decided at the close of first_close, filled at first_day's open: the one entry is on the first row.
        self.assertEqual([row["entries"] for row in rows], [1, 0, 0, 0])
        self.assertGreater(rows[0]["w"], 0.0)
        # The decision behind first_day's orders read the bars through first_close and nothing later: its hash is
        # the one a store that ENDS at first_close gives.
        early = Path(tempfile.mkdtemp(prefix="eqe3-early-"))
        self.addCleanup(shutil.rmtree, early, True)
        write_night(early, FWD[2])
        needs = self.program(pid).needs
        bars = gated(early).bars(["SPY"], "forward", history=needs["history"], start=FWD[2])
        self.assertEqual(bars.day(bars.n - 1), FWD[2])
        self.assertEqual(rows[0]["bars"], self.hash_at(bars, bars.n - 1, needs))
        # And it is what the LIVE book reads at that close (E1's `inputs_from_fetch` on the fetch of that evening):
        # the same bars hash, so a twin's first decision can be told from a live one only by its bars.
        fetched = {adjustment: {"SPY": synth.bar_rows(bars, "SPY", bars.n - 1, adjustment=adjustment)}
                   for adjustment in ("raw", "all")}
        live = eq_ctx.inputs_from_fetch(fetched["raw"], fetched["all"], day=FWD[2], needs=parse_needs(needs),
                                        cash=0.0, equity=0.0, budget=0.0, caps={}, params={})
        self.assertEqual(len(live.days), needs["history"] + 1)
        self.assertEqual(rows[0]["bars"], forward_db.bars_hash(live))

    def test_a_program_that_waits_for_its_full_history_decides_at_first_close(self):
        # E1's Gym hands a run's first decision the sessions its slice holds before the run. With NEEDS history
        # sessions there, that decision would read one bar fewer than the live book does and this program would buy a
        # session late, in the shadow only.
        pid = register(self.db, "waits@1", WAITS, first_close=FWD[2])
        shadow = self.shadow(FWD[6])
        bars = shadow.slice(self.program(pid))
        self.assertEqual((bars.first, bars.day(bars.first - 1), bars.day(bars.first)), (6, FWD[2], FWD[3]))
        shadow.night()
        self.assertEqual([row["entries"] for row in self.rows(pid)], [1, 0, 0, 0])

    def test_nothing_is_computed_before_the_code_existed(self):
        pid = register(self.db, "late@1", ALWAYS, first_close=FWD[4])
        for through in FWD[2:5]:                      # before it existed, and the night of its first decision
            shadow = self.shadow(through)
            self.assertIsNone(shadow.slice(self.program(pid)))
            self.assertEqual(shadow.due(), [])
            receipt = shadow.night()
            self.assertEqual((receipt["programs"], receipt["new_days"], receipt["stale"]), (0, 0, 0))
        self.assertEqual(self.rows(pid), [])
        self.night(FWD[5])
        self.assertEqual([row["day"] for row in self.rows(pid)], iso(FWD[5:6]))

    def test_no_day_before_the_first_forward_day_whatever_a_registry_row_says(self):
        # A row that claims a first day inside the look's span (before t0) is refused as the data's: never a row.
        bad = register(self.db, "early@1", ALWAYS, first_close=schedule.previous_session(BEFORE))
        good = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        self.assertLess(self.program(bad).first_day, T0)
        shadow = self.shadow(FWD[3])
        with self.assertRaises(ValueError):
            shadow.slice(self.program(bad))
        with self.assertRaises(ValueError):
            shadow.run_from(self.program(good), BEFORE)
        receipt = shadow.night()
        self.assertEqual(self.rows(bad), [])
        self.assertEqual((receipt["programs"], receipt["data_failed"]), (1, 1))
        self.assertEqual([row["day"] for row in self.rows(good)], iso(FWD[:4]))
        self.assertEqual(min(row["day"] for row in self.rows()), T0.isoformat())
        failed = self.events("data_failed", bad)
        self.assertEqual([(e["day"], e["payload"]["class"]) for e in failed], [(FWD[3].isoformat(), "ValueError")])
        self.assertEqual(self.count("fwd_tags"), 0)

    def test_a_history_of_0_does_not_move_the_first_decision(self):
        pid = register(self.db, "zero@1", HISTORY_0, first_close=FWD[1])
        shadow = self.shadow(FWD[5])
        program = self.program(pid)
        self.assertEqual(program.needs["history"], 0)
        bars = shadow.slice(program)
        # One session before the run's first, the close the program first decides at.
        self.assertEqual((bars.first, bars.day(0), bars.day(1)), (1, FWD[1], FWD[2]))
        shadow.night()
        rows = self.rows(pid)
        self.assertEqual([row["day"] for row in rows], iso(FWD[2:6]))
        self.assertEqual([row["entries"] for row in rows], [1, 0, 0, 0])
        # The ctx is NEEDS' own, one session of bars, whatever the slice carries.
        self.assertEqual(rows[1]["bars"], self.hash_at(bars, 1, program.needs))
        self.assertNotEqual(rows[1]["bars"], self.hash_at(bars, 1, {**program.needs, "history": 1}))

    def test_a_slice_with_no_session_to_decide_at_is_refused(self):
        # A store whose calendar starts at the program's first day holds no close for its first decision.
        pid = register(self.db, "always@1", ALWAYS, first_close=FWD[2])
        synth.synthetic_store(self.root / STORE_DIR, symbols=SYMBOLS, start=FWD[3], end=END, seed=7, gate=True,
                              as_of=FWD[6])
        shadow = self.shadow(FWD[6], write=False)
        with self.assertRaises(ValueError):
            shadow.slice(self.program(pid))
        receipt = shadow.night()
        self.assertEqual((receipt["programs"], receipt["data_failed"], self.rows(pid)), (0, 1, []))

    def test_every_new_row_carries_the_bars_hash_of_the_decision_before_it(self):
        pid = register(self.db, "flip@1", FLIPPER, first_close=FWD[0])
        shadow = self.shadow(FWD[8])
        shadow.night()
        program = self.program(pid)
        bars = shadow.slice(program)
        rows = self.rows(pid)
        self.assertEqual(len(rows), 8)
        for i, row in enumerate(rows):
            self.assertRegex(row["bars"], r"^[0-9a-f]{16}$")
            self.assertEqual(row["bars"], self.hash_at(bars, bars.first + i - 1, program.needs), row["day"])
        self.assertEqual(len({row["bars"] for row in rows}), len(rows))


class TheSealedDaysNeedTheCapability(Case):
    """T6: a forward slice without an `EquityGateCapability` raises `StoreRefused`; the shadow holds one."""

    def test_a_forward_slice_without_the_capability_is_refused(self):
        write_night(self.root, FWD[3])
        plain = EquityStore(self.root / STORE_DIR)
        with self.assertRaises(StoreRefused):
            plain.bars(["SPY"], "forward", history=1, start=T0)
        with self.assertRaises(StoreRefused):
            plain.sessions("forward")
        self.assertEqual(gated(self.root).bars(["SPY"], "forward", history=1, start=T0).day(1), T0)

    def test_the_shadow_opens_its_store_with_the_gates_capability(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        with mock.patch.object(forward_shadow, "mint_equity_gate_capability",
                               wraps=mint_equity_gate_capability) as mint:
            shadow = self.shadow(FWD[3])
        self.assertEqual(mint.call_args.args, (self.root / STORE_DIR, forward_shadow.GATE_REASON))
        self.assertTrue(shadow.store.gate)
        self.assertEqual(shadow.through, FWD[3])
        self.assertEqual(shadow.slice(self.program(pid)).window, "forward")

    def test_a_store_without_the_gates_mark_runs_nothing(self):
        register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        write_night(self.root, FWD[3], gate=False)
        with self.assertRaises(StoreRefused):
            forward_shadow.Shadow(self.root, self.db, decider=InlineDecider(), settings=RECORD, clock=self.clock)
        self.assertEqual((self.count("fwd_days"), self.count("fwd_runs"), self.count("fwd_events")), (0, 0, 0))


# ============================================================================================================ the rows
class TwoNights(Case):
    def test_two_nights_give_identical_rows_and_no_restated(self):
        pids = [register(self.db, "always@1", ALWAYS, first_close=BEFORE),
                register(self.db, "state@1", STATE, first_close=FWD[0]),
                register(self.db, "flip@1", FLIPPER, first_close=FWD[1])]
        first = self.night(FWD[5])
        self.assertEqual((first["programs"], first["new_days"], first["sessions"]), (3, 6 + 5 + 4, 15))
        before = self.rows()
        second = self.night(FWD[6])
        self.assertEqual((second["programs"], second["new_days"], second["restated"]), (3, 3, 0))
        self.assertEqual(second["sessions"], 7 + 6 + 5)        # recomputed whole, every night
        self.assertEqual([row for row in self.rows() if row["day"] <= FWD[5].isoformat()], before)
        self.assertEqual(self.events("restated"), [])
        self.assertEqual([len(self.rows(pid)) for pid in pids], [7, 6, 5])
        self.assertEqual(self.count("fwd_runs"), 2)

    def test_state_is_rebuilt_at_every_run(self):
        # The program buys at its FIRST call only. A STATE that outlived a run would leave the k 1.5 run, and every
        # later night's recompute, without that buy: another r15, a restated day.
        pid = register(self.db, "state@1", STATE, first_close=FWD[0])
        for through in FWD[3:6]:
            self.night(through)
        rows = self.rows(pid)
        self.assertEqual([row["entries"] for row in rows], [1, 0, 0, 0, 0])
        self.assertLess(rows[0]["r15"], rows[0]["r"])          # a close entry pays its half-spread, 1.5 times in r15
        self.assertLess(rows[0]["r"], 0.0)
        self.assertEqual(self.events("restated"), [])

    def test_a_row_is_the_screens_series_of_the_run(self):
        # D3 against E1's own entry point and the screen's own accounting, made here apart from the job.
        pid = register(self.db, "flip@1", FLIPPER, first_close=FWD[0])
        shadow = self.shadow(FWD[12])
        shadow.night()
        program = self.program(pid)
        bars = shadow.slice(program)
        base = runner.run_bars(FLIPPER, {}, bars, name=program.key, k=config.K_BASE)
        stress = runner.run_bars(FLIPPER, {}, bars, name=program.key, k=config.K_STRESS)
        s = screen.series(base["lots"], bars, universe=["SPY", "QQQ"], capital=base["capital"])
        s15 = screen.series(stress["lots"], bars, universe=["SPY", "QQQ"], capital=stress["capital"])
        rows = self.rows(pid)
        self.assertEqual([row["day"] for row in rows], iso(FWD[1:13]))
        for i, row in enumerate(rows):
            self.assertEqual((row["r"], row["w"], row["b"], row["r15"]),
                             (float(s.r[i]), float(s.w[i]), float(s.b[i]), float(s15.r[i])), row["day"])
            self.assertEqual(row["entries"], sum(1 for lot in base["lots"] if lot["entry_day"] == row["day"]))
            self.assertEqual(row["exits"], int(s.exits[i]))
            self.assertEqual((row["status"], row["engine"], row["r0"]), ("ok", shadow.engine, None))
        self.assertGreater(sum(row["entries"] for row in rows), 1)
        self.assertGreater(sum(row["exits"] for row in rows), 1)
        self.assertTrue(any(row["r15"] < row["r"] for row in rows))

    def test_run_from_starts_flat_at_another_first_day(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        shadow = self.shadow(FWD[6])
        program = self.program(pid)
        run = shadow.run_from(program, FWD[3])
        self.assertIsInstance(run, forward_db.ShadowRun)
        self.assertIs(run.program, program)
        self.assertEqual([from_ordinal(int(d)) for d in run.series.days], FWD[3:7])
        self.assertEqual((run.bars.day(run.bars.first), run.result["status"]), (FWD[3], "ok"))
        self.assertEqual([lot["entry_day"] for lot in run.result["lots"]], [FWD[3].isoformat()])
        self.assertEqual(shadow.run_from(program, FWD[3], k=config.K_STRESS).result["k"], config.K_STRESS)
        self.assertIsNone(shadow.run_from(program, FWD[7]))
        self.assertEqual(self.count("fwd_days"), 0)            # a twin run writes no row

    def test_official_is_the_stores_raw_open_or_close(self):
        shadow = self.shadow(FWD[6], gaps={"DIA": [FWD[2]]})
        bars = shadow.store.bars(["SPY"], "forward", history=0, start=FWD[2], end=FWD[2])
        self.assertEqual(shadow.official("SPY", FWD[2], "open"), float(bars.raw["SPY"][0, 0]))
        self.assertEqual(shadow.official("spy", FWD[2].isoformat(), "close"), float(bars.raw["SPY"][0, 3]))
        self.assertNotEqual(shadow.official("SPY", FWD[2], "open"), shadow.official("SPY", FWD[2], "close"))
        self.assertIsNone(shadow.official("DIA", FWD[2], "open"))          # no bar that session
        self.assertIsNone(shadow.official("AAPL", FWD[2], "open"))         # not in the store
        self.assertIsNone(shadow.official("SPY", FWD[7], "close"))         # after the store's last day
        weekend = next(FWD[0] + dt.timedelta(days=k) for k in range(1, 8)
                       if not schedule.is_session(FWD[0] + dt.timedelta(days=k)))
        self.assertLess(weekend, FWD[6])
        self.assertIsNone(shadow.official("SPY", weekend, "close"))        # not a session
        with self.assertRaises(ValueError):
            shadow.official("SPY", FWD[2], "noon")


class Restated(Case):
    def test_a_moved_bar_is_one_event_a_value_and_the_row_stays(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        self.night(FWD[4])
        stored = {row["day"]: (row["r"], row["w"], row["at"]) for row in self.rows(pid)}
        moved, after = FWD[4].isoformat(), FWD[5].isoformat()
        # The vendor corrects the last stored close. Three later nights: ONE event.
        for k, through in enumerate(FWD[5:8]):
            write_night(self.root, through)
            perturb(self.root, "SPY", FWD[4], 1.01)
            receipt = self.shadow(through, write=False).night()
            self.assertEqual(receipt["restated"], 1 if k == 0 else 0, through)
            self.assertEqual(receipt["programs"], 1)           # data, never an error: the night goes on
        (event,) = self.events("restated", pid)
        self.assertEqual({k: event["payload"][k] for k in ("days", "first", "last", "moved", "same", "bars", "night")},
                         {"days": 1, "first": moved, "last": moved, "moved": 0, "same": 1, "bars": "same",
                          "night": FWD[5].isoformat()})
        self.assertEqual(event["day"], moved)
        rows = {row["day"]: (row["r"], row["w"], row["at"]) for row in self.rows(pid)}
        self.assertEqual({day: rows[day] for day in stored}, stored)          # the first write stands
        # A second, different value: a second event. The day after was stored from the first correction, so it is
        # restated too, and the decision behind it read another close: its bars moved. One event holds both days.
        write_night(self.root, FWD[8])
        perturb(self.root, "SPY", FWD[4], 1.02)
        receipt = self.shadow(FWD[8], write=False).night()
        self.assertEqual(receipt["restated"], 1)
        events = self.events("restated", pid)
        self.assertEqual([e["day"] for e in events], [moved, moved])
        self.assertEqual({k: events[1]["payload"][k] for k in ("days", "first", "last", "moved", "same", "bars")},
                         {"days": 2, "first": moved, "last": after, "moved": 1, "same": 1, "bars": "same"})
        self.assertEqual(len({e["payload"]["once"] for e in events}), 2)
        self.assertEqual(
            {row["day"]: (row["r"], row["w"], row["at"]) for row in self.rows(pid) if row["day"] in stored}, stored)
        for event in events:                                   # a payload holds no figure
            self.assertFalse([v for v in event["payload"].values() if isinstance(v, float)])
        self.assertEqual(self.count("fwd_runs"), 5)

    def test_an_ex_day_under_the_vendors_cents_is_one_event_a_holder_not_one_a_day(self):
        # THE BARS HASH's fact, on the stored returns: the vendor rounds adjustment=all to cents and rescales the
        # whole adjusted history at a dividend, so on the ex-day nearly every stored day of a holder moves past TOL.
        holder = register(self.db, "always@1", ALWAYS, first_close=BEFORE)             # half a sleeve of SPY
        other = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)               # trades QQQ only
        dividend = {"SPY": [(FWD[11], 1.5)]}
        receipts = []
        for through in FWD[10:14]:                             # the night before, the ex-day, two nights after
            write_night(self.root, through, dividends=dividend)
            cents(self.root)
            receipts.append(self.shadow(through, write=False).night())
        self.assertEqual([r["restated"] for r in receipts], [0, 1, 0, 0])
        self.assertEqual([r["programs"] for r in receipts], [2, 2, 2, 2])
        (event,) = self.events("restated")
        payload = event["payload"]
        self.assertEqual((event["pid"], payload["bars"], payload["same"], payload["night"]),
                         (holder, "moved", 0, FWD[11].isoformat()))
        self.assertGreaterEqual(payload["days"], 6)            # most of its eleven stored days, in ONE event
        self.assertEqual(payload["moved"], payload["days"])
        self.assertLessEqual(FWD[0].isoformat(), payload["first"])
        self.assertLessEqual(payload["last"], FWD[10].isoformat())
        self.assertEqual((len(self.rows(holder)), len(self.rows(other))), (14, 14))

    def test_a_difference_inside_the_tolerance_is_not_restated(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        self.night(FWD[4])
        write_night(self.root, FWD[5])
        perturb(self.root, "SPY", FWD[4], 1.0000004)           # under TOL of r on half a sleeve
        self.assertEqual(self.shadow(FWD[5], write=False).night()["restated"], 0)
        self.assertEqual(self.events("restated", pid), [])


class Checkpoints(Case):
    def test_the_statistics_are_d4s_formulas_and_the_row_waits_a_day(self):
        pid = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        first = self.night(FWD[19])
        # Twenty counted days, the twentieth the store's last: its morning audit has not run.
        self.assertEqual((len(self.rows(pid)), first["checks"], self.checks(pid)), (20, 0, []))
        second = self.night(FWD[20])
        self.assertEqual(second["checks"], 1)
        self.assertEqual(self.night(FWD[21])["checks"], 0)
        (check,) = self.checks(pid)
        rows = self.rows(pid)[:20]
        r, w, b = ([row[name] for row in rows] for name in ("r", "w", "b"))
        x = [ri - wi * bi for ri, wi, bi in zip(r, w, b)]      # the daily excess, NOT screen.excess
        self.assertEqual((check["n"], check["day"], check["final"], check["engine"]),
                         (20, FWD[19].isoformat(), 0, rows[0]["engine"]))
        self.assertAlmostEqual(check["t_r"], t_of(r), places=9)
        self.assertAlmostEqual(check["t_x"], t_of(x), places=9)
        self.assertAlmostEqual(check["sum_r"], math.fsum(r), places=15)
        self.assertAlmostEqual(check["sum_r15"], math.fsum(row["r15"] for row in rows), places=15)
        self.assertAlmostEqual(check["mean_w"], math.fsum(w) / 20, places=15)
        self.assertAlmostEqual(check["p_x"], forward_stats.p_one_sided(check["t_x"], 20), places=12)
        self.assertTrue(0.0 < check["p_x"] < 1.0)
        self.assertEqual((check["t_x0"], check["p_x0"]), (None, None))         # a control's only
        self.assertNotAlmostEqual(check["t_x"], check["t_r"], places=6)
        self.assertEqual(check["at"], evening(FWD[20]))

    def test_golden_values(self):
        # Four invented days, by hand: r 1%, 3%, 1%, 3%; exposure a half; the benchmark 1% a day. mean(r) = 0.02,
        # sd = sqrt(4e-4 / 3), t_r = 2 sqrt(3); x = r - 0.005, t_x = 1.5 sqrt(3); with 3 degrees of freedom the
        # upper tail of t is 1/2 - (u / (1 + u^2) + atan(u)) / pi at u = t / sqrt(3).
        pid = register(self.db, "golden@1", ALWAYS, first_close=BEFORE)
        flat = register(self.db, "flat@1", ALWAYS, first_close=BEFORE)
        shadow = self.shadow(FWD[10])
        for who, series in ((pid, (0.01, 0.03, 0.01, 0.03)), (flat, (0.01, 0.01, 0.01, 0.01))):
            for day, value in zip(FWD, series):
                self.db.execute(
                    "INSERT INTO fwd_days(pid, day, engine, r, w, b, r15, entries, exits, status, at, bars) "
                    "VALUES (?,?,?,?,?,?,?,0,0,'ok',?,?)",
                    (who, day.isoformat(), shadow.engine, value, 0.5, 0.01, value - 0.001, self.t, "0" * 16))
            forward_db.tag(self.db, who, "stopped", f"cap:{FWD[3].isoformat()}", at=self.t)
        self.assertEqual(shadow.finals(), 2)
        (check,) = self.checks(pid)
        self.assertEqual((check["n"], check["day"], check["final"]), (4, FWD[3].isoformat(), 1))
        self.assertAlmostEqual(check["t_r"], 2.0 * math.sqrt(3.0), places=9)
        self.assertAlmostEqual(check["t_x"], 1.5 * math.sqrt(3.0), places=9)
        self.assertAlmostEqual(check["sum_r"], 0.08, places=15)
        self.assertAlmostEqual(check["sum_r15"], 0.076, places=15)
        self.assertAlmostEqual(check["mean_w"], 0.5, places=15)
        self.assertAlmostEqual(check["p_x"], 0.5 - (1.5 / 3.25 + math.atan(1.5)) / math.pi, places=6)
        (none,) = self.checks(flat)                            # no variance: no t, no p
        self.assertEqual((none["t_r"], none["t_x"], none["p_x"]), (None, None, None))
        self.assertAlmostEqual(none["sum_r"], 0.04, places=15)

    def test_an_audit_mark_leaves_the_counted_days(self):
        pid = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        self.night(FWD[19])
        forward_db.event(self.db, "audit_mismatch", pid=pid, day=FWD[7].isoformat(), at=self.t, once="audit",
                         payload={"why": "a test's mark", "symbol": "SPY"})
        # Twenty-one stored, twenty counted, the twentieth the store's last day: the row waits one more night.
        self.assertEqual(self.night(FWD[20])["checks"], 0)
        self.assertEqual(self.night(FWD[21])["checks"], 1)
        (check,) = self.checks(pid)
        counted = [row for row in self.rows(pid) if row["day"] != FWD[7].isoformat()][:20]
        self.assertEqual((check["n"], check["day"]), (20, FWD[20].isoformat()))
        self.assertAlmostEqual(check["sum_r"], math.fsum(row["r"] for row in counted), places=15)
        self.assertEqual(len(self.rows(pid)), 22)              # the marked row stays

    def test_the_grid_goes_on_every_250_after_250(self):
        self.assertEqual(list(forward_shadow._grid(19)), [])
        self.assertEqual(list(forward_shadow._grid(260)), [20, 60, 120, 250])
        self.assertEqual(list(forward_shadow._grid(1000)), [20, 60, 120, 250, 500, 750, 1000])
        self.assertEqual(forward_db.CHECKPOINTS + (500,), tuple(forward_shadow._grid(600)))


class Finals(Case):
    def test_a_stopped_programs_final_checkpoint_is_written_once(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        other = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        self.night(FWD[6])
        forward_db.tag(self.db, pid, "stopped", f"cap:{FWD[6].isoformat()}", at=self.t)
        # The job again that same night: its last day is the store's last, whose morning audit has not run.
        self.assertEqual(self.shadow(FWD[6], write=False).night()["finals"], 0)
        first = self.night(FWD[7])
        self.assertEqual((first["finals"], first["programs"]), (1, 1))        # a stopped program is not run
        self.assertEqual(self.night(FWD[8])["finals"], 0)
        (check,) = self.checks(pid)
        rows = self.rows(pid)
        self.assertEqual((check["n"], check["final"], check["day"], len(rows)), (7, 1, FWD[6].isoformat(), 7))
        self.assertAlmostEqual(check["sum_r"], math.fsum(row["r"] for row in rows), places=15)
        self.assertAlmostEqual(check["t_r"], t_of([row["r"] for row in rows]), places=9)
        self.assertEqual(self.checks(other), [])               # an active program has none

    def test_one_stopped_on_the_grid_keeps_its_row(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        self.night(FWD[19])
        self.night(FWD[20])                                    # the row of n = 20 is written
        forward_db.event(self.db, "audit_mismatch", pid=pid, day=FWD[20].isoformat(), at=self.t, once="audit",
                         payload={"why": "a test's mark"})     # twenty counted days again
        forward_db.tag(self.db, pid, "stopped", f"cap:{FWD[20].isoformat()}", at=self.t)
        self.assertEqual(self.night(FWD[21])["finals"], 0)
        self.assertEqual([(c["n"], c["final"]) for c in self.checks(pid)], [(20, 0)])

    def test_a_resumed_program_is_run_again_and_has_no_final(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        self.night(FWD[4])
        forward_db.tag(self.db, pid, "stopped", f"cap:{FWD[4].isoformat()}", at=self.t)
        forward_db.tag(self.db, pid, "resumed", f"{self.t + 60.0}|a test's undo", at=self.t + 60.0)
        receipt = self.night(FWD[6])
        self.assertEqual((receipt["finals"], receipt["programs"], receipt["new_days"]), (0, 1, 2))
        self.assertEqual((self.checks(pid), len(self.rows(pid))), ([], 7))     # every day the stop left out is filled

    def test_one_with_fewer_than_two_counted_days_has_none(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        self.night(FWD[0])
        forward_db.tag(self.db, pid, "stopped", f"cap:{FWD[0].isoformat()}", at=self.t)
        self.assertEqual(self.night(FWD[1])["finals"], 0)
        self.assertEqual(self.checks(pid), [])


class Disqualified(Case):
    def test_its_rows_are_stored_not_counted_and_its_event_is_once_a_night(self):
        pid = register(self.db, "broken@1", BROKEN, first_close=BEFORE)
        good = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        first = self.night(FWD[26])
        again = self.shadow(FWD[26], write=False).night()      # the runner starts the job again: nothing is due
        second = self.night(FWD[27])
        self.assertEqual([r["disqualified"] for r in (first, again, second)], [1, 0, 1])
        rows = self.rows(pid)
        self.assertEqual((len(rows), {row["status"] for row in rows}), (28, {"disqualified"}))
        self.assertEqual(forward_db.counted_days(self.db, pid, engine=rows[0]["engine"]), [])
        self.assertEqual(self.checks(pid), [])
        self.assertEqual([e["day"] for e in self.events("run_disqualified", pid)], iso(FWD[26:28]))
        self.assertEqual(self.events("run_disqualified", good), [])
        self.assertEqual(len(self.checks(good)), 1)
        self.assertEqual(self.count("fwd_tags"), 0)            # the stop is the registry's, from the events
        self.assertEqual(self.events("run_failed"), [])
        # Written twice in one night (a retry after a write the store refused): still one event, no second row.
        shadow = self.shadow(FWD[28])
        run, result15 = shadow.run_program(self.program(pid))
        self.assertEqual(shadow.write(run, result15), {"new_days": 1, "restated": 0, "checks": 0})
        self.t += 60.0
        self.assertEqual(shadow.write(run, result15), {"new_days": 0, "restated": 0, "checks": 0})
        self.assertEqual([e["day"] for e in self.events("run_disqualified", pid)], iso(FWD[26:29]))


# ======================================================================================================== whose failure
class WhoseFailure(Case):
    def test_three_nights_with_a_decider_that_cannot_start(self):
        register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        for through in FWD[2:5]:
            with self.assertRaises(forward_shadow.NightFailed):
                self.night(through, decider=Dead())
        self.t += 1800.0
        with self.assertRaises(forward_shadow.NightFailed):   # the same night again, later: no second event
            self.shadow(FWD[4], write=False, decider=Dead()).night()
        self.assertEqual([e["day"] for e in self.events("night_failed")], iso(FWD[2:5]))
        self.assertIn("DeciderError", self.events("night_failed")[0]["payload"]["why"])
        self.assertEqual(self.events("run_failed") + self.events("data_failed"), [])
        self.assertEqual([self.count(t) for t in ("fwd_runs", "fwd_tags", "fwd_days", "fwd_checks")], [0, 0, 0, 0])
        self.assertEqual((self.synced, self.twins["order"]), ([], []))        # nothing at all ran past the preflight

    def test_a_canary_that_does_not_run_ok_fails_the_night(self):
        register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        with self.assertRaises(forward_shadow.NightFailed):
            self.night(FWD[2], decider=Ticking(self, broken=("forward-canary",)))
        refusing = Ticking(self)
        refusing.kind = lambda *a, **k: {"ok": False, "error": "the child cannot import its runtime"}
        with self.assertRaises(forward_shadow.NightFailed) as raised:
            self.shadow(FWD[3], decider=refusing).night()
        self.assertIn("RunFailed", str(raised.exception))
        # A child that answers its ping "not ok", and a canary the child ran to another status than "ok".
        deaf = Ticking(self)
        deaf.ping = lambda: {"ok": False}
        with self.assertRaises(forward_shadow.NightFailed) as raised:
            self.shadow(FWD[4], decider=deaf).night()
        self.assertIn("ping", str(raised.exception))
        self.assertEqual(deaf.runs, [])                        # nothing is asked of a child that does not answer
        odd = Ticking(self)
        odd.kind = lambda *a, **k: {"ok": True, "result": {"status": "disqualified", "lots": [], "capital": "1000"}}
        with self.assertRaises(forward_shadow.NightFailed) as raised:
            self.shadow(FWD[5], decider=odd).night()
        self.assertIn("disqualified", str(raised.exception))
        self.assertEqual([e["day"] for e in self.events("night_failed")], iso(FWD[2:6]))
        self.assertEqual((self.count("fwd_runs"), self.count("fwd_days"), self.synced), (0, 0, []))

    def test_the_canary_runs_through_the_same_child_op_over_the_last_five_forward_days(self):
        decider = Ticking(self)
        seen = []
        real = decider.kind

        def kind(kind, op, payload, *, budget_seconds=None):
            seen.append((kind, op, payload["name"], payload["bars"], budget_seconds))
            return real(kind, op, payload, budget_seconds=budget_seconds)

        decider.kind = kind
        self.shadow(FWD[7], decider=decider).preflight()
        ((kind_, op, name, bars, budget),) = seen
        self.assertEqual((kind_, op, name, budget), ("equity", "run", "forward-canary", 120.0))
        self.assertEqual((bars.symbols, bars.first), (("SPY",), 1))
        self.assertEqual([bars.day(i) for i in range(bars.first, bars.n)], FWD[3:8])
        seen.clear()
        self.shadow(FWD[1], decider=decider).preflight()       # two forward days in the store: both, none before t0
        self.assertEqual([seen[0][3].day(i) for i in range(1, seen[0][3].n)], FWD[:2])
        self.assertEqual(self.events("night_failed"), [])

    def test_a_missing_bar_is_the_datas_and_the_days_fill_when_it_returns(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        self.night(FWD[2])
        gap = {"SPY": [FWD[3]]}
        for through in FWD[4:6]:
            receipt = self.night(through, gaps=gap)
            self.assertEqual((receipt["programs"], receipt["data_failed"], receipt["errors"]), (0, 1, 0))
        self.shadow(FWD[5], gaps=gap).night()                  # the same night again: no second event
        events = self.events("data_failed", pid)
        self.assertEqual([(e["day"], e["payload"]["class"], e["payload"]["symbol"]) for e in events],
                         [(d, "ValueError", "SPY") for d in iso(FWD[4:6])])
        self.assertEqual(len(self.rows(pid)), 3)               # no row those nights
        self.assertEqual((self.count("fwd_tags"), self.events("run_failed")), (0, []))
        receipt = self.night(FWD[6])                           # the bar is back: every day is filled
        self.assertEqual((receipt["programs"], receipt["new_days"], receipt["data_failed"]), (1, 4, 0))
        self.assertEqual([row["day"] for row in self.rows(pid)], iso(FWD[:7]))
        self.assertEqual(len(self.events("data_failed", pid)), 2)

    def test_a_store_rewritten_under_the_night_is_that_programs_data_failed(self):
        on_spy = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        on_qqq = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        shadow = self.shadow(FWD[3])
        path = self.root / STORE_DIR / "bars" / "QQQ.npz"      # not read yet: the canary and the first program read SPY
        path.write_bytes(path.read_bytes()[:-8] + b"rewrites")
        receipt = shadow.night()
        self.assertEqual((receipt["programs"], receipt["data_failed"], receipt["errors"], receipt["retried"]),
                         (1, 1, 0, 0))
        (event,) = self.events("data_failed", on_qqq)
        self.assertEqual((event["payload"]["class"], event["payload"]["symbol"]), ("MissingData", "QQQ"))
        self.assertEqual((len(self.rows(on_spy)), self.rows(on_qqq), self.count("fwd_tags")), (4, [], 0))
        self.assertEqual(self.night(FWD[4])["new_days"], 1 + 5)                # the store is whole again

    def test_a_symbol_with_no_bar_in_the_run_is_the_datas(self):
        pid = register(self.db, "dia@1", ON_DIA, first_close=BEFORE)
        receipt = self.night(FWD[3], gaps={"DIA": FWD[:4]})
        self.assertEqual((receipt["programs"], receipt["data_failed"], receipt["retried"]), (0, 1, 0))
        (event,) = self.events("data_failed", pid)
        self.assertEqual((event["payload"]["class"], event["payload"]["symbol"]), ("MissingData", "DIA"))
        self.assertEqual(self.rows(pid), [])

    def test_one_that_fails_twice_while_another_completes_gets_run_failed(self):
        good = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        bad = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        made: list[Ticking] = []

        def fresh() -> Ticking:
            made.append(Ticking(self, broken=("flip@1",)))
            return made[-1]

        receipt = self.night(FWD[3], decider=Ticking(self, broken=("flip@1",)), fresh=fresh)
        self.assertEqual((receipt["programs"], receipt["errors"], receipt["retried"], receipt["stale"]), (1, 1, 1, 0))
        (event,) = self.events("run_failed", bad)
        self.assertEqual((event["day"], event["payload"]["class"], event["payload"]["completed"]),
                         (FWD[3].isoformat(), "DeciderError", 1))
        self.assertEqual([d.runs for d in made], [[("flip@1", 1.0)]])         # again, alone, in a fresh child
        self.assertEqual((len(self.rows(good)), self.rows(bad)), (4, []))
        self.assertEqual((self.count("fwd_tags"), self.events("run_failed", good)), (0, []))
        # The same night again (the runner's retry): the event is written once a (pid, night).
        self.t += 900.0
        self.shadow(FWD[3], write=False, decider=Ticking(self, broken=("flip@1",)), fresh=fresh).night()
        self.assertEqual(len(self.events("run_failed")), 1)
        row = dict(self.db.execute("SELECT * FROM fwd_runs ORDER BY run").fetchall()[0])
        self.assertEqual((row["programs"], row["errors"], row["stale"], row["budget_hit"]), (1, 1, 0, 0))

    def test_another_start_of_the_job_that_night_counts_what_the_first_completed(self):
        # The first start is killed before its retry; the second finds only the failing program due. Another
        # program's run DID complete that night: the event is written.
        good = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        bad = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        control = register_control(self.db, "index", 40, SYMBOLS, first_close=BEFORE)
        with self.assertRaises(Killed):
            self.night(FWD[3], decider=Ticking(self, kill=("flip@1",)))
        self.assertEqual((len(self.rows(good)), len(self.rows(control)), self.rows(bad)), (4, 4, []))
        receipt = self.shadow(FWD[3], write=False, decider=Ticking(self, broken=("flip@1",)),
                              fresh=lambda: Ticking(self, broken=("flip@1",))).night()
        self.assertEqual((receipt["programs"], receipt["errors"], receipt["retried"]), (0, 1, 1))
        (event,) = self.events("run_failed", bad)
        self.assertEqual(event["payload"]["completed"], 1)     # the program, never the control's rows

    def test_a_controls_rows_are_nobodys_completed_run(self):
        bad = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        register_control(self.db, "index", 40, SYMBOLS, first_close=BEFORE)
        receipt = self.night(FWD[3], decider=Ticking(self, broken=("flip@1",)),
                             fresh=lambda: Ticking(self, broken=("flip@1",)))
        self.assertEqual((receipt["controls"]["rows"], receipt["errors"]), (4, 1))
        self.assertEqual(self.events("run_failed", bad), [])

    def test_one_that_fails_when_none_completes_gets_nothing(self):
        register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        everyone = ("always@1", "flip@1")
        receipt = self.night(FWD[3], decider=Ticking(self, broken=everyone),
                             fresh=lambda: Ticking(self, broken=everyone))
        self.assertEqual((receipt["programs"], receipt["errors"], receipt["retried"]), (0, 2, 2))
        self.assertEqual(self.events("run_failed"), [])
        self.assertEqual((self.count("fwd_days"), self.count("fwd_tags"), self.count("fwd_runs")), (0, 0, 1))

    def test_a_fresh_child_that_does_not_ping_writes_nothing(self):
        register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        bad = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        for night, fresh in ((FWD[3], Dead), (FWD[4], None)):  # no child to retry in, or no retry at all
            receipt = self.night(night, decider=Ticking(self, broken=("flip@1",)), fresh=fresh)
            self.assertEqual((receipt["programs"], receipt["errors"], receipt["retried"]), (1, 1, 0))
        self.assertEqual((self.events("run_failed"), self.rows(bad)), ([], []))

    def test_one_that_completes_at_the_retry_is_written_as_any_other(self):
        good = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        flaky = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        shadow = self.shadow(FWD[3], decider=Ticking(self, broken=("flip@1",)), fresh=lambda: Ticking(self))
        receipt = shadow.night()
        self.assertEqual((receipt["programs"], receipt["errors"], receipt["retried"]), (2, 0, 1))
        self.assertEqual((len(self.rows(good)), len(self.rows(flaky))), (4, 4))
        self.assertEqual(self.events("run_failed"), [])
        self.assertEqual([pid for pid, _, _ in self.twins["on_run"]], [good, flaky])
        self.assertEqual(shadow.decider.broken, set())         # the twins' runs go to the child that answers

    def test_a_program_the_child_refuses_is_the_childs(self):
        register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        bad = register(self.db, "refused@1", REFUSED, first_close=BEFORE,
                       needs={"symbols": ["SPY"], "history": 5, "max_hold_sessions": 60})
        receipt = self.night(FWD[3], fresh=InlineDecider)
        self.assertEqual((receipt["programs"], receipt["errors"], receipt["retried"], receipt["data_failed"]),
                         (1, 1, 1, 0))
        self.assertEqual([e["payload"]["class"] for e in self.events("run_failed", bad)], ["RunFailed"])

    def test_a_write_the_forward_store_refuses_marks_nobody(self):
        bad = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        good = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        real = forward_shadow.Shadow._put

        def put(shadow, pid, days, **kwargs):
            if pid == bad:
                raise sqlite3.OperationalError("database or disk is full")
            return real(shadow, pid, days, **kwargs)

        with mock.patch.object(forward_shadow.Shadow, "_put", put):
            receipt = self.night(FWD[3], fresh=InlineDecider)
        self.assertEqual((receipt["programs"], receipt["errors"], receipt["retried"]), (1, 1, 0))
        self.assertEqual(self.events("run_failed") + self.events("data_failed"), [])
        self.assertEqual((self.rows(bad), len(self.rows(good)), self.count("fwd_tags")), ([], 4, 0))
        self.assertEqual(self.night(FWD[4])["new_days"], 5 + 1)               # the next night fills it

    def test_a_program_is_one_transaction(self):
        # The checkpoint's arithmetic fails after the days were inserted: none of that program's rows stays.
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        with mock.patch.object(forward_stats, "t_stat", side_effect=RuntimeError("a meter's bug")):
            receipt = self.night(FWD[20])
        self.assertEqual((receipt["programs"], receipt["errors"], receipt["new_days"]), (0, 1, 0))
        self.assertEqual((self.rows(pid), self.checks(pid), self.events("run_failed")), ([], [], []))
        receipt = self.night(FWD[21])
        self.assertEqual((receipt["programs"], receipt["new_days"], receipt["checks"]), (1, 22, 1))

    def test_a_result_that_does_not_fit_its_bars_has_no_rows(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        shadow = self.shadow(FWD[3])
        run, result15 = shadow.run_program(self.program(pid))
        odd = forward_db.ShadowRun(program=run.program, result={**run.result, "status": "error"}, bars=run.bars,
                                   series=run.series)
        short = forward_db.ShadowRun(program=run.program, result=run.result, bars=run.bars,
                                     series=screen.series(run.result["lots"], run.bars, universe=["SPY"],
                                                          capital=run.result["capital"], last=run.bars.n - 2))
        lost = {**result15, "lots": [{**result15["lots"][0], "entry_day": "2031-01-02"}]}
        for bad_run, bad_15 in ((odd, result15), (short, result15), (run, lost)):
            with self.assertRaises(ValueError):
                shadow.write(bad_run, bad_15)
        self.assertEqual((self.rows(pid), self.count("fwd_events") - len(self.events("engine_moved"))), ([], 0))
        self.assertEqual(shadow.write(run, result15)["new_days"], 4)

    def test_the_registry_or_the_twins_failing_loses_no_day(self):
        pids = [register(self.db, "always@1", ALWAYS, first_close=BEFORE),
                register(self.db, "flip@1", FLIPPER, first_close=BEFORE)]
        self.twins_raise = True

        def broken(db):
            raise sqlite3.OperationalError("database is locked")

        self.on_sync = broken
        receipt = self.night(FWD[3])
        self.assertEqual((receipt["programs"], receipt["new_days"], receipt["errors"]), (2, 8, 0))
        self.assertEqual([len(self.rows(pid)) for pid in pids], [4, 4])
        self.assertEqual(receipt["register"], {"error": "OperationalError"})
        self.assertEqual((receipt["twins"]["begin"], receipt["twins"]["finish"], receipt["twins"]["errors"]),
                         ({"error": "RuntimeError"}, {"error": "RuntimeError"}, 4))
        self.assertEqual(self.count("fwd_runs"), 1)


# ============================================================================================== the night's own rules
class TheNight(Case):
    def test_it_calls_the_others_in_order_and_writes_one_run_row(self):
        pids = [register(self.db, "always@1", ALWAYS, first_close=BEFORE),
                register(self.db, "flip@1", FLIPPER, first_close=FWD[0])]
        decider = Ticking(self, 2.0)
        shadow = self.shadow(FWD[3], decider=decider)
        began = self.t
        receipt = shadow.night()
        self.assertEqual(len(self.synced), 1)
        self.assertEqual(self.twins["order"], ["begin", "on_run", "on_run", "finish"])
        self.assertEqual(self.twins["begin"] + self.twins["finish"], [shadow, shadow])
        # After each write: the program's days are stored when the twins read its run.
        self.assertEqual(self.twins["on_run"], [(pids[0], 4, "ShadowRun"), (pids[1], 3, "ShadowRun")])
        self.assertEqual(decider.runs, [("forward-canary", 1.0), ("always@1", 1.0), ("always@1", 1.5),
                                        ("flip@1", 1.0), ("flip@1", 1.5)])
        (row,) = [dict(r) for r in self.db.execute("SELECT * FROM fwd_runs").fetchall()]
        self.assertEqual((row["job"], row["through"], row["engine"], row["programs"], row["sessions"]),
                         ("forward_shadow", FWD[3].isoformat(), shadow.engine, 2, 7))
        self.assertEqual((row["errors"], row["stale"], row["budget_hit"], row["head"]),
                         (0, 0, 0, forward_db.head(self.db)))
        self.assertEqual((row["started"], row["finished"], row["seconds"]), (began, began + 10.0, 10.0))
        self.assertEqual(set(receipt), {"through", "engine", "programs", "sessions", "new_days", "restated", "checks",
                                        "stale", "errors", "data_failed", "disqualified", "retried", "budget_hit",
                                        "seconds", "controls", "twins", "head", "finals", "register"})
        self.assertEqual((receipt["through"], receipt["engine"], receipt["seconds"], receipt["head"]),
                         (FWD[3].isoformat(), shadow.engine, 10.0, row["head"]))
        self.assertEqual(receipt["twins"], {"begin": {"days": 0, "rows": 0}, "rows": 2, "errors": 0,
                                            "finish": {"instances": 0, "twins": 0, "disagreed": 0, "lots": 0,
                                                       "interrupted": 0, "live_bars": 0}})
        self.assertEqual(receipt["register"]["chain_ok"], True)

    def test_the_receipt_and_every_event_hold_counts_never_a_figure(self):
        register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        register(self.db, "dia@1", ON_DIA, first_close=BEFORE)
        register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        register_control(self.db, "index", 40, SYMBOLS, first_close=BEFORE)
        receipt = self.night(FWD[3], decider=Ticking(self, broken=("flip@1",)),
                             fresh=lambda: Ticking(self, broken=("flip@1",)), gaps={"DIA": FWD[:4]})

        def figures(value: Any, path: str = "") -> list[str]:
            if isinstance(value, Mapping):
                return [hit for k, v in value.items() for hit in figures(v, f"{path}.{k}")]
            if isinstance(value, (list, tuple)):
                return [hit for v in value for hit in figures(v, path)]
            return [path] if isinstance(value, float) else []

        self.assertEqual(figures(receipt), [".seconds"])
        kinds = {row[0] for row in self.db.execute("SELECT DISTINCT kind FROM fwd_events")}
        self.assertLessEqual({"engine_moved", "data_failed", "run_failed"}, kinds)
        for kind in kinds:
            self.assertEqual(forward_db.EVENT_KINDS[kind], "B", kind)
            for event in self.events(kind):
                self.assertEqual(figures(event["payload"]), [], kind)
                self.assertNotRegex(json.dumps(event["payload"]), r"\d+\.\d+", kind)
                self.assertIn("why", event["payload"])

    def test_a_night_killed_after_one_program_resumes_with_no_duplicate(self):
        first = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        second = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        with self.assertRaises(Killed):
            self.night(FWD[3], decider=Ticking(self, kill=("flip@1",)))
        stored = self.rows(first)
        self.assertEqual((len(stored), self.rows(second), self.count("fwd_runs")), (4, [], 0))
        self.t += 600.0
        receipt = self.shadow(FWD[3], write=False).night()     # the job is started again
        self.assertEqual((receipt["programs"], receipt["new_days"], receipt["restated"]), (1, 4, 0))
        self.assertEqual(self.rows(first), stored)             # skipped: written through the night already
        self.assertEqual((len(self.rows(second)), self.count("fwd_days"), self.count("fwd_runs")), (4, 8, 1))
        self.assertEqual([pid for pid, _, _ in self.twins["on_run"]], [first, second])

    def test_the_order_is_live_then_passers_and_seeds_then_failers_then_suspects(self):
        failed = register(self.db, "fail@1", ALWAYS, first_close=BEFORE, reason="train_fail")
        passed = register(self.db, "pass@1", ALWAYS, first_close=BEFORE)
        seed = register(self.db, "seed@1", ALWAYS, first_close=BEFORE, reason="seed")
        tagged = register(self.db, "tagged@1", ALWAYS, first_close=BEFORE, reason="train_fail")
        live = register(self.db, "live@1", ALWAYS, first_close=BEFORE, reason="live")
        suspect = register(self.db, "suspect@1", ALWAYS, first_close=BEFORE)
        stopped = register(self.db, "stopped@1", ALWAYS, first_close=BEFORE)
        later = register(self.db, "later@1", ALWAYS, first_close=FWD[1])
        control = register_control(self.db, "index", 40, SYMBOLS, first_close=BEFORE)
        self.assertEqual(self.night(FWD[0])["programs"], 7)
        forward_db.tag(self.db, tagged, "live", "tagged@1:r", at=self.t)
        forward_db.tag(self.db, suspect, "suspect", FWD[0].isoformat(), at=self.t)
        forward_db.tag(self.db, stopped, "stopped", f"cap:{FWD[0].isoformat()}", at=self.t)
        shadow = self.shadow(FWD[1])
        due = [p.pid for p in shadow.due()]
        self.assertEqual(due, [tagged, live, passed, seed, failed, suspect])
        self.assertNotIn(control, due)                         # a control is run in the parent, never due
        self.assertNotIn(later, due)                           # its first day is after the night
        shadow.night()
        self.assertEqual([pid for pid, _, _ in self.twins["on_run"]][7:], due)
        self.assertEqual(self.shadow(FWD[1], write=False).due(), [])           # written through the night

    def test_the_budget_leaves_the_rest_stale_and_they_go_first_the_next_night(self):
        pids = [register(self.db, f"p{i}@1", ALWAYS, first_close=BEFORE) for i in range(3)]
        settings = {"elane": {"forward": {"mode": "record", "cpu_seconds_night": 60}}}
        receipt = self.night(FWD[2], decider=Ticking(self, 25.0), settings=settings)
        # The canary 25 s, the first program's two runs 50 s: 75 of the night's 60.
        self.assertEqual((receipt["programs"], receipt["stale"], receipt["budget_hit"], receipt["seconds"]),
                         (1, 2, 1, 75.0))
        (event,) = self.events("budget_hit")
        self.assertEqual((event["day"], event["pid"], event["payload"]["stale"]), (FWD[2].isoformat(), None, 2))
        row = dict(self.db.execute("SELECT * FROM fwd_runs").fetchone())
        self.assertEqual((row["programs"], row["stale"], row["budget_hit"], row["seconds"]), (1, 2, 1, 75.0))
        # The job again the same night: one more program; the event is written once a night.
        receipt = self.shadow(FWD[2], write=False, decider=Ticking(self, 25.0), settings=settings).night()
        self.assertEqual((receipt["programs"], receipt["stale"]), (1, 1))
        self.assertEqual(len(self.events("budget_hit")), 1)
        self.assertEqual([len(self.rows(pid)) for pid in pids], [3, 3, 0])
        # The next night the one left stale goes first.
        shadow = self.shadow(FWD[3], decider=Ticking(self, 25.0), settings=settings)
        self.assertEqual([p.pid for p in shadow.due()], [pids[2], pids[0], pids[1]])
        shadow.night()
        self.assertEqual([len(self.rows(pid)) for pid in pids], [3, 3, 4])
        self.assertEqual([e["day"] for e in self.events("budget_hit")], iso(FWD[2:4]))
        self.assertEqual((self.count("fwd_tags"), self.events("run_failed")), (0, []))

    def test_the_retry_stops_at_the_budget_too(self):
        register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        bad = register(self.db, "flip@1", FLIPPER, first_close=BEFORE)
        settings = {"elane": {"forward": {"mode": "record", "cpu_seconds_night": 60}}}
        made: list[Ticking] = []

        def fresh() -> Ticking:
            made.append(Ticking(self, 25.0, broken=("flip@1",)))
            return made[-1]

        # 42 s spent already; the canary 5 s, one program 10 s, the other's failed run 5 s: 62 of 60 before the retry.
        decider = Ticking(self, 5.0, broken=("flip@1",))
        shadow = self.shadow(FWD[3], decider=decider, settings=settings, fresh=fresh)
        shadow.spent = 42.0
        receipt = shadow.night()
        self.assertEqual((receipt["programs"], receipt["retried"], receipt["stale"], receipt["errors"]), (1, 0, 1, 0))
        self.assertEqual((made[0].runs, self.events("run_failed", bad)), ([], []))
        self.assertEqual(len(self.events("budget_hit")), 1)

    def test_no_program_starts_within_300_s_of_the_next_0900(self):
        register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        shadow = self.shadow(FWD[2])
        morning = dt.datetime.combine(FWD[3], dt.time(9, 0), schedule.NY).timestamp()
        self.t = morning - 300.0                               # the job retried in the morning, too late
        receipt = shadow.night()
        self.assertEqual((receipt["programs"], receipt["stale"], receipt["budget_hit"]), (0, 1, 1))
        self.t = morning - 301.0
        receipt = self.shadow(FWD[2], write=False).night()
        self.assertEqual((receipt["programs"], receipt["stale"], receipt["budget_hit"]), (1, 0, 0))

    def test_the_quiet_window(self):
        def at(day: dt.date, hour: int, minute: int, second: int = 0) -> float:
            return dt.datetime.combine(day, dt.time(hour, minute, second), schedule.NY).timestamp()

        session = FWD[1]
        self.assertEqual([forward_shadow.quiet(at(session, *hm)) for hm in ((8, 59, 59), (9, 0), (12, 0), (17, 29, 59),
                                                                           (17, 30), (18, 35), (23, 0))],
                         [False, True, True, True, False, False, False])
        day = FWD[0]
        closed = []
        while len(closed) < 2:                                 # a weekend day, and the first weekday holiday
            day += dt.timedelta(days=1)
            if not schedule.is_session(day) and (day.weekday() >= 5) == (not closed):
                closed.append(day)
        self.assertEqual([forward_shadow.quiet(at(d, 12, 0)) for d in closed], [False, False])
        half = next(d for d in FWD if schedule.moments(d).early)
        self.assertTrue(forward_shadow.quiet(at(half, 15, 0)))                 # a half day is a session
        self.assertEqual(forward_shadow.QUIET, ((9, 0), (17, 30)))


class EngineMoved(Case):
    def test_a_new_label_is_one_event_a_full_new_series_and_the_old_rows_stay(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        one, two = (EQUITY_ENGINE_VERSION + f"+{tag * 12}+" + forward_db.FWD_SERIES for tag in "ab")
        with mock.patch.object(forward_db, "fwd_engine", lambda: one):
            self.night(FWD[20])
            first = self.night(FWD[21])
        old = self.rows(pid, engine=first["engine"])
        self.assertEqual((len(old), len(self.rows(pid)), len(self.checks(pid))), (22, 22, 1))
        with mock.patch.object(forward_db, "fwd_engine", lambda: two):
            moved = self.night(FWD[22])
            after = self.night(FWD[23])
        self.assertNotEqual(moved["engine"], first["engine"])
        self.assertEqual((after["engine"], moved["new_days"], after["new_days"]), (moved["engine"], 23, 1))
        # One event for the move, written once; the whole history again under the new id; the old rows as they were.
        events = [e for e in self.events("engine_moved") if e["payload"]["to"] == two]
        self.assertEqual([(e["payload"]["from"], e["payload"]["engine"], e["pid"]) for e in events],
                         [(one, moved["engine"], None)])
        self.assertEqual(len(self.events("engine_moved")), 2)  # and one when the first label opened the record
        self.assertEqual(self.rows(pid, engine=first["engine"]), old)
        new = self.rows(pid, engine=moved["engine"])
        self.assertEqual([row["day"] for row in new], iso(FWD[:24]))
        self.assertEqual([(row["r"], row["w"], row["bars"]) for row in new[:22]],
                         [(row["r"], row["w"], row["bars"]) for row in old])
        self.assertEqual(self.events("restated"), [])
        # THE CHECKPOINT OF RECORD for (pid, 20) is the row written first, whatever engine recomputed it later.
        checks = self.checks(pid)
        self.assertEqual([(c["n"], c["engine"]) for c in checks], [(20, first["engine"]), (20, moved["engine"])])
        self.assertLess(checks[0]["at"], checks[1]["at"])
        self.assertEqual(forward_db.engine_label(self.db, moved["engine"]), two)

    def test_a_program_stopped_before_the_move_keeps_its_old_series_and_gets_its_final(self):
        pid = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        one, two = (EQUITY_ENGINE_VERSION + f"+{tag * 12}+" + forward_db.FWD_SERIES for tag in "ab")
        with mock.patch.object(forward_db, "fwd_engine", lambda: one):
            first = self.night(FWD[5])
        forward_db.tag(self.db, pid, "stopped", f"cap:{FWD[5].isoformat()}", at=self.t)
        with mock.patch.object(forward_db, "fwd_engine", lambda: two):
            moved = self.night(FWD[6])
        self.assertEqual((moved["finals"], moved["programs"], len(self.rows(pid))), (1, 0, 6))
        self.assertEqual([(c["n"], c["final"], c["engine"]) for c in self.checks(pid)], [(6, 1, first["engine"])])


class Controls(Case):
    def test_a_controls_rows_carry_its_cost_free_series_and_no_bars_hash(self):
        first = register_control(self.db, "index", 40, SYMBOLS, first_close=BEFORE)
        second = register_control(self.db, "index", 45, SYMBOLS, first_close=FWD[2])
        decider = Ticking(self)
        shadow = self.shadow(FWD[21], decider=decider)
        out = shadow.controls()
        self.assertEqual((out["groups"], out["rows"], out["errors"], out["checks"]), (1, 22 + 19, 0, 1))
        self.assertEqual(decider.runs, [])                     # in the parent: no child
        spec = json.loads(self.program(first).code)
        bars = shadow.store.bars(list(SYMBOLS), "forward", history=1, start=T0)
        sessions = [bars.day(i) for i in range(bars.first - 1, bars.n)]
        self.assertEqual(sessions[:2], [BEFORE, T0])           # S[0] is first_close
        lots = {k: forward_controls.control_lots(spec, sessions, k=k) for k in (1.0, 1.5, 0.0)}
        s = screen.series(lots[1.0], bars, universe=list(SYMBOLS), capital=config.SLEEVE_USD)
        s15 = screen.series(lots[1.5], bars, universe=list(SYMBOLS), capital=config.SLEEVE_USD)
        r0 = forward_controls.cost_free(lots[0.0], bars, capital=config.SLEEVE_USD)
        rows = self.rows(first)
        self.assertEqual([row["day"] for row in rows], iso(FWD[:22]))
        for i, row in enumerate(rows):
            self.assertEqual((row["r"], row["w"], row["b"], row["r15"], row["r0"]),
                             (float(s.r[i]), float(s.w[i]), float(s.b[i]), float(s15.r[i]), float(r0[i])))
            self.assertEqual((row["bars"], row["status"], row["exits"]), (None, "ok", int(s.exits[i])))
            self.assertLessEqual(row["r"], row["r0"] + 1e-12)  # costs only subtract
        self.assertTrue(any(row["w"] > 0 for row in rows))
        self.assertEqual(sum(row["entries"] for row in rows), len(lots[1.0]))
        self.assertEqual(len(self.rows(second)), 19)
        # Its checkpoint: D4's statistics, and the cost-free ones beside them (D5, D8).
        (check,) = self.checks(first)
        x0 = [row["r0"] - row["w"] * row["b"] for row in rows[:20]]
        self.assertEqual((check["n"], check["day"], check["final"]), (20, FWD[19].isoformat(), 0))
        for got, want in ((check["t_x0"], t_of(x0)), (check["t_r"], t_of([row["r"] for row in rows[:20]]))):
            self.assertIsNotNone(want)
            self.assertAlmostEqual(got, want, places=9)
        self.assertAlmostEqual(check["p_x0"], forward_stats.p_one_sided(check["t_x0"], 20), places=12)
        # Written through the night: a second call writes nothing.
        again = shadow.controls()
        self.assertEqual((again["rows"], again["checks"], again["groups"]), (0, 0, 1))
        self.assertEqual(self.events("restated"), [])

    def test_a_control_with_a_missing_bar_is_the_datas_and_the_others_go_on(self):
        on_dia = register_control(self.db, "defensive", 40, ("DIA",), first_close=BEFORE)
        on_spy = register_control(self.db, "index", 40, ("SPY",), first_close=BEFORE)
        program = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        receipt = self.night(FWD[14], gaps={"DIA": FWD[4:13]})
        self.assertEqual((receipt["controls"]["rows"], receipt["controls"]["errors"], receipt["controls"]["groups"]),
                         (15, 1, 2))
        self.assertEqual((self.rows(on_dia), len(self.rows(on_spy)), len(self.rows(program))), ([], 15, 15))
        (event,) = self.events("data_failed", on_dia)
        self.assertEqual((event["day"], event["payload"]["symbol"]), (FWD[14].isoformat(), "DIA"))
        self.assertEqual((receipt["programs"], receipt["data_failed"], self.count("fwd_tags")), (1, 0, 0))

    def test_a_control_draw_that_raises_costs_the_programs_nothing(self):
        register_control(self.db, "index", 40, SYMBOLS, first_close=BEFORE)
        program = register(self.db, "always@1", ALWAYS, first_close=BEFORE)
        with mock.patch.object(forward_controls, "control_lots", side_effect=RuntimeError("a draw's bug")):
            receipt = self.night(FWD[3])
        self.assertEqual((receipt["controls"]["errors"], receipt["controls"]["rows"], receipt["programs"]), (1, 0, 1))
        self.assertEqual((len(self.rows(program)), self.events("data_failed")), (4, []))


# ============================================================================================================= the job
class TheJob(Case):
    def setUp(self) -> None:
        super().setUp()
        self.made: list[Any] = []
        self.factory: Any = lambda root: Ticking(self)
        self.real_decider = forward_shadow._decider
        patcher = mock.patch.object(forward_shadow, "_decider", lambda root: self._make(root))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make(self, root: Path) -> Any:
        self.made.append(self.factory(root))
        return self.made[-1]

    def settings(self, **forward: Any) -> None:
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"forward": forward}}))

    def ctx(self) -> Context:
        return Context("forward_shadow", root=self.root, due_at=self.t, clock=self.clock, config={}, settings_value={})

    def book(self) -> sqlite3.Connection:
        db = forward_db.open_db(self.root)
        self.addCleanup(db.close)
        return db

    def test_it_skips_when_off_when_quiet_and_with_no_forward_day(self):
        self.settings(mode="off")
        write_night(self.root, FWD[2])
        self.assertEqual(forward_shadow.run(self.ctx())["why"], "elane.forward.mode is off")
        self.settings(mode="record")
        self.t = dt.datetime.combine(FWD[3], dt.time(12, 0), schedule.NY).timestamp()
        self.assertEqual(forward_shadow.run(self.ctx())["status"], "skipped")
        self.assertIn("09:00-17:30", forward_shadow.run(self.ctx())["why"])
        self.t = evening(FWD[3])
        write_night(self.root, BEFORE)                         # the look cap's day is the store's last
        skipped = forward_shadow.run(self.ctx())
        self.assertEqual((skipped["status"], BEFORE.isoformat() in skipped["why"]), ("skipped", True))
        shutil.rmtree(self.root / STORE_DIR)
        self.assertEqual(forward_shadow.run(self.ctx())["status"], "skipped")
        # A release without the forward store's package (its functions still step 0's stubs): skipped, never a crash.
        write_night(self.root, FWD[3])
        with mock.patch.object(forward_db, "mode", side_effect=NotImplementedError("A: league/ops/forward_db.py mode")):
            skipped = forward_shadow.run(self.ctx())
        self.assertEqual((skipped["status"], "not in this release" in skipped["why"]), ("skipped", True))
        self.assertEqual((self.made, (self.root / forward_db.DB).exists()), ([], False))

    def test_a_night(self):
        self.settings(mode="record")
        db = self.book()
        pid = register(db, "always@1", ALWAYS, first_close=BEFORE)
        write_night(self.root, FWD[3])
        self.t = evening(FWD[3])
        receipt = forward_shadow.run(self.ctx())
        self.assertEqual((receipt.get("status"), receipt["through"], receipt["programs"], receipt["new_days"]),
                         (None, FWD[3].isoformat(), 1, 4))
        self.assertEqual(db.execute("SELECT COUNT(*) FROM fwd_days WHERE pid=?", (pid,)).fetchone()[0], 4)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM fwd_runs").fetchone()[0], 1)
        self.assertEqual([d.closed for d in self.made], [1])   # its own child, closed in `finally`
        json.dumps(receipt)                                    # a receipt is plain JSON

    def test_the_jobs_child_is_its_own_decider_with_its_own_log(self):
        child = self.real_decider(self.root)
        self.addCleanup(child.close)
        self.assertIsInstance(child, Decider)
        self.assertEqual(Path(child.log), self.root / forward_shadow.DECIDER_LOG)
        self.assertIsNone(child.proc)                          # nothing starts before the first request

    def test_a_preflight_failure_is_a_failed_receipt_and_marks_nobody(self):
        self.settings(mode="record")
        db = self.book()
        register(db, "always@1", ALWAYS, first_close=BEFORE)
        write_night(self.root, FWD[3])
        self.t = evening(FWD[3])
        self.factory = lambda root: Dead()
        receipt = forward_shadow.run(self.ctx())
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("nobody was run or marked", receipt["error"])
        self.assertEqual([e["day"] for e in forward_db.events(db, "night_failed")], [FWD[3].isoformat()])
        self.assertEqual([db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                          for t in ("fwd_runs", "fwd_days", "fwd_tags")], [0, 0, 0])
        self.assertEqual([d.closed for d in self.made], [1])

    def test_the_retry_gets_a_new_child_and_the_old_one_is_closed_first(self):
        self.settings(mode="record")
        db = self.book()
        register(db, "always@1", ALWAYS, first_close=BEFORE)
        flaky = register(db, "flip@1", FLIPPER, first_close=BEFORE)
        write_night(self.root, FWD[3])
        self.t = evening(FWD[3])
        closed_before: list[int] = []

        def factory(root: Path) -> Ticking:
            closed_before.append(sum(d.closed for d in self.made))
            return Ticking(self, broken=() if self.made else ("flip@1",))

        self.factory = factory
        receipt = forward_shadow.run(self.ctx())
        self.assertEqual((receipt["programs"], receipt["retried"], receipt["errors"]), (2, 1, 0))
        self.assertEqual((len(self.made), closed_before, [d.closed for d in self.made]), (2, [0, 1], [1, 1]))
        self.assertEqual(db.execute("SELECT COUNT(*) FROM fwd_days WHERE pid=?", (flaky,)).fetchone()[0], 4)

    def test_a_store_being_rewritten_is_a_failed_receipt(self):
        self.settings(mode="record")
        write_night(self.root, FWD[3])
        self.t = evening(FWD[3])
        (self.root / STORE_DIR / "calendar.npz").write_bytes(b"half a file")
        receipt = forward_shadow.run(self.ctx())
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("MissingData", receipt["error"])
        write_night(self.root, FWD[3], gate=False)             # and one that is not the House's own
        receipt = forward_shadow.run(self.ctx())
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("StoreRefused", receipt["error"])


if __name__ == "__main__":
    unittest.main()
