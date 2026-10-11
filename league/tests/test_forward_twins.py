"""Release E3, package D: league/ops/forward_twins.py: the timing table, the live-like re-price (D10), the fill gap of
a closed live lot (D11), intent agreement between a live instance and its twin (D12), and what the bars hash adds: a
disagreement is a counted row with its cause, never an error.

Everything here is synthetic: the market is `league.equity.synth`'s store, the programs and the live book are
invented, the minute bars are made up. FAKES, each written to its stub's docstring (league/ops/E3_INTERFACES.md):
- of package A's `forward_db` functions this module calls (`cfg`, `t0`, `engine_now`, `event`, `events`, `program`,
  `open_db`): `install` patches them in; the store itself is the real `forward_db.SCHEMA` in memory;
- of package B's `forward_shadow.Shadow` (`Shadow` here: `store`, `through`, `official`, `run_from`, with the
  constructor's `decider` and `settings` under those names), running E1's REAL engine through a real `InlineDecider`;
- of the live book: `Book` writes `league.equity.live.SCHEMA`'s own tables, and `record` writes the `eq_intents` rows
  E1's `_record_intents` writes for a decide's intents.
The A14 reading is in league/tests/test_forward_a14.py."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import math
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity import config, engine, schedule, screen, synth
from league.equity.store import EquityStore, mint_equity_gate_capability, ordinal
from league.live.decider import InlineDecider
from league.ops import fill_minutes, forward_db, forward_twins, guard, twins
from league.swarm import elane_train

NY = schedule.NY
T0 = dt.date(2026, 10, 12)
D1, D2, D3, D4 = "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15"
STORE_START, STORE_END = dt.date(2026, 6, 1), dt.date(2026, 11, 20)
SETTINGS = {"elane": {"forward": {"mode": "record"}}}


# ------------------------------------------------------------------------------------------- fakes of package A's names
def fake_cfg(settings):
    """A FAKE of `forward_db.cfg` (its stub's docstring): every key of `DEFAULTS`, a malformed value its default, an
    unreadable block the defaults (mode "off")."""
    out = dict(forward_db.DEFAULTS)
    try:
        items = dict(settings["elane"]["forward"]).items()
    except Exception:  # noqa: BLE001
        return out
    for key, value in items:
        if key == "mode" and value in forward_db.MODES:
            out[key] = value
        elif key in ("fill_minutes", "twins") and isinstance(value, bool):
            out[key] = value
    return out


def fake_t0():
    return schedule.next_session(config.LOOK_CAP)


def fake_engine_now(db):
    return db.execute("SELECT MAX(id) FROM fwd_engines").fetchone()[0]


def fake_event(db, kind, *, pid=None, day=None, payload=None, at, once=None):
    """A FAKE of `forward_db.event`: one row; with `once`, only when no row of that kind, pid and day carries the same
    `once` in its payload (then 0)."""
    assert kind in forward_db.EVENT_KINDS, kind
    body = dict(payload or {})
    if once is not None:
        assert kind in forward_db.ONCE_KINDS, kind
        for row in db.execute("SELECT payload FROM fwd_events WHERE kind=? AND pid IS ? AND day IS ?", (kind, pid, day)):
            if json.loads(row[0]).get("once") == once:
                return 0
        body["once"] = once
    cursor = db.execute("INSERT INTO fwd_events(at, kind, pid, day, payload) VALUES(?,?,?,?,?)",
                        (float(at), kind, pid, day, json.dumps(body, sort_keys=True)))
    return int(cursor.lastrowid)


def fake_events(db, kind, *, pid=None, since=None):
    rows = db.execute("SELECT seq, at, kind, pid, day, payload FROM fwd_events WHERE kind=? ORDER BY seq", (kind,))
    return [{"seq": r[0], "at": r[1], "kind": r[2], "pid": r[3], "day": r[4], "payload": json.loads(r[5])}
            for r in rows if (pid is None or r[3] == pid) and (since is None or r[1] >= since)]


def fake_program(db, key):
    row = db.execute("SELECT * FROM fwd_registry WHERE key=?", (key,)).fetchone()
    if row is None:
        return None
    return forward_db.Program(
        row["pid"], row["key"], row["family"], row["version"], row["lane"], row["reason"], row["ugroup"],
        row["lineage"], row["code"], json.loads(row["params"]), json.loads(row["needs"]), row["program_sha"],
        row["run_sha"], row["created_at"], dt.date.fromisoformat(row["first_close"]),
        dt.date.fromisoformat(row["first_day"]), row["route"], row["alpha_f"])


def fake_open_db(root, *, readonly=False):
    """A FAKE of `forward_db.open_db`: read-only is `guard.connect_ro` (it raises when the file is absent); writable
    creates the file with the real schema."""
    path = Path(root) / forward_db.DB
    if readonly:
        return guard.connect_ro(path)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(forward_db.SCHEMA)
    return db


FAKES = {"cfg": fake_cfg, "t0": fake_t0, "engine_now": fake_engine_now, "event": fake_event, "events": fake_events,
         "program": fake_program, "open_db": fake_open_db}


def install(case: unittest.TestCase) -> None:
    for name, fake in FAKES.items():
        patch = mock.patch.object(forward_db, name, fake)
        patch.start()
        case.addCleanup(patch.stop)


def memory(case: unittest.TestCase) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    case.addCleanup(db.close)
    db.row_factory = sqlite3.Row
    db.executescript(forward_db.SCHEMA)
    db.execute("INSERT INTO fwd_engines(label, at) VALUES('fake-engine+0+fwd-1', 1.0)")
    return db


def register(db, key: str, code: str, *, run_sha: str = "run-sha-1", params=None, reason: str = "live") -> int:
    """One `fwd_registry` row, written with SQL (package A's writer is a stub here); its pid."""
    needs = elane_train.needs_literal(code) or {"symbols": ["SPY"], "history": 1, "max_hold_sessions": 5}
    pid = (db.execute("SELECT COALESCE(MAX(pid), 0) FROM fwd_registry").fetchone()[0]) + 1
    family, version = key.split("@")
    db.execute("INSERT INTO fwd_registry(pid, key, family, version, lane, reason, ugroup, lineage, code, params, needs, "
               "program_sha, run_sha, author, created_at, evidence, first_close, first_day, registered_at, route, "
               "alpha_f, prev_hash, row_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (pid, key, family, int(version), "beta", reason, "index", f"beta:{family}", code,
                json.dumps(params or {}), json.dumps(needs), hashlib.sha256(code.encode()).hexdigest(), run_sha,
                "fake-author", 0.0, "registry", "2026-10-09", "2026-10-12", 0.0, "S2", "0.03", "p", f"h{pid}"))
    db.commit()
    return pid


def at(day, hour: int, minute: int = 0) -> float:
    day = day if isinstance(day, dt.date) else dt.date.fromisoformat(day)
    return dt.datetime.combine(day, dt.time(hour, minute), NY).timestamp()


def events(db, kind: str) -> list[dict]:
    return fake_events(db, kind)


# ------------------------------------------------------------------------------------------------------- the programs
OVERNIGHT = '''NEEDS = {"symbols": ["SPY"], "history": 3, "max_hold_sessions": 5}
PARAMS = {}


def decide(ctx):
    out = [{"sell": p["id"], "at": "open"} for p in ctx.positions]
    out.append({"buy": "SPY", "share": 0.4, "at": "close"})
    return out
'''
#: Reads its whole look-back: a ctx one session short answers nothing.
REVERSAL = '''NEEDS = {"symbols": ["QQQ", "SPY"], "history": 2, "max_hold_sessions": 5}
PARAMS = {}


def decide(ctx):
    out = []
    for p in ctx.positions:
        if p["held_sessions"] >= 1:
            out.append({"sell": p["id"], "at": "open"})
    r = ctx.bars["QQQ"].ret
    if len(r) > 2 and r[-1] < 0 and r[-2] < 0.02 and not ctx.positions:
        out.append({"buy": "QQQ", "share": 0.3, "at": "open"})
    return out
'''
#: Keeps a clock in STATE: a reloaded instance starts it again.
CLOCK = '''NEEDS = {"symbols": ["SPY"], "history": 1, "max_hold_sessions": 5}
PARAMS = {}
STATE = {"n": 0}


def decide(ctx):
    STATE["n"] += 1
    out = [{"sell": p["id"], "at": "open"} for p in ctx.positions]
    if STATE["n"] % 3 == 1:
        out.append({"buy": "SPY", "share": 0.3, "at": "close"})
    return out
'''
#: The same junk every session beside its real intents: a sell of a lot nobody holds, a buy outside NEEDS, a cancel.
JUNK = '''NEEDS = {"symbols": ["SPY"], "history": 1, "max_hold_sessions": 5}
PARAMS = {}


def decide(ctx):
    out = [{"sell": 999, "at": "open"}, {"buy": "IWM", "share": 0.1}, {"cancel": 7}]
    out += [{"sell": p["id"], "at": "open"} for p in ctx.positions]
    out.append({"buy": "SPY", "share": 0.4, "at": "close"})
    return out
'''
#: Buys once and holds: for the split.
HOLD = '''NEEDS = {"symbols": ["QQQ"], "history": 1, "max_hold_sessions": 30}
PARAMS = {}


def decide(ctx):
    return [] if ctx.positions or ctx.closed else [{"buy": "QQQ", "share": 0.4, "at": "open"}]
'''


# ------------------------------------------------------------------------------------------------ a fake of B's Shadow
class Shadow:
    """A FAKE of package B's `forward_shadow.Shadow`, to its stub's docstring: `store` (the `EquityStore` opened with
    the capability), `through`, `official` (the store's raw open or close) and `run_from` (D3's run started flat at a
    first day: E1's engine through the decider child's "run" op, `screen.series` of its lots), with the constructor's
    `decider` and `settings`. `lookback`: the history sessions its slice carries before the first day (default NEEDS'
    history + 1: the first decision then reads what the live decision read)."""

    def __init__(self, store_root, *, through, decider=None, settings=SETTINGS, lookback=None):
        self.store = EquityStore(store_root, gate=mint_equity_gate_capability(store_root, "forward-shadow"))
        self.through = through if isinstance(through, dt.date) else dt.date.fromisoformat(through)
        self.decider = decider if decider is not None else InlineDecider()
        self.settings = settings
        self.lookback = lookback or (lambda needs: int(needs.get("history") or 0) + 1)
        self.runs: list[tuple[str, str]] = []

    def official(self, symbol, day, at_):
        day = day if isinstance(day, dt.date) else dt.date.fromisoformat(day)
        if day > self.through:
            return None
        bars = self.store.bars([symbol], "forward", history=0, start=day, end=day)
        return engine.official(bars, symbol, bars.first, at_) if bars.n > bars.first else None

    def slice(self, program, *, first_day=None):
        first_day = first_day or program.first_day
        if first_day > self.through:
            return None
        return self.store.bars(program.needs["symbols"], "forward", history=self.lookback(program.needs),
                               start=first_day, end=self.through)

    def run_from(self, program, first_day, *, k=1.0):
        self.runs.append((program.key, first_day.isoformat()))
        bars = self.slice(program, first_day=first_day)
        if bars is None:
            return None
        answer = self.decider.kind("equity", "run", {"code": program.code, "params": program.params,
                                                     "name": program.key, "bars": bars, "k": k, "capital": None},
                                   budget_seconds=120.0)
        result = answer["result"]
        series = screen.series(result["lots"], bars, universe=list(program.needs["symbols"]), capital=result["capital"])
        return forward_db.ShadowRun(program, result, bars, series)


# ---------------------------------------------------------------------------------------------- a fake of the live book
class Book:
    """A synthetic live book: `league.equity.live.SCHEMA`'s tables and the House state's `kv`, written row by row."""

    def __init__(self, path: Path):
        from league.equity.live import SCHEMA

        self.path = path
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self.db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.commit()
        self.iid = 0

    def close(self):
        self.db.close()

    def instance(self, key: str, code: str, *, created: float, run_sha: str = "run-sha-1", retired: float | None = None,
                 decided: str | None = None) -> str:
        family, version = key.split("@")
        self.db.execute("INSERT OR REPLACE INTO eq_instances(id, family, version, lane, run_sha, code, params, band, "
                        "seeded, max_hold, failed_decides, last_decided_day, created_at, retired_at, why) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (key + ":r", family, int(version), "beta", run_sha, code, "{}", "probe", 0, 5, 0, decided,
                         created, retired, ""))
        self.db.commit()
        return key + ":r"

    def lot(self, lid: int, instance: str, symbol: str, opened_day: str, entry_at: str, *, exit_day: str | None = None,
            exit_at: str | None = None, **money) -> None:
        row = {"lid": lid, "instance": instance, "family": instance.split("@")[0], "version": 1, "lane": "beta",
               "symbol": symbol, "class": "etf", "qty": "1", "opened_qty": "1", "entry_px": "100", "entry_notional": "100",
               "entry_at": entry_at, "fees": "0", "div": "0", "opened_at": at(opened_day, 9, 31),
               "opened_day": opened_day, "status": "closed" if exit_day else "open", "exit_px": "100" if exit_day else None,
               "exit_at": exit_at, "exit_day": exit_day, "closed_at": at(exit_day, 9, 31) if exit_day else None,
               "cash": "0", **money}
        self.db.execute(f"INSERT OR REPLACE INTO eq_lots({', '.join(row)}) VALUES({', '.join('?' * len(row))})",
                        tuple(row.values()))
        self.db.commit()

    def intent(self, instance: str, day: str, kind: str, *, at_: str = "open", symbol: str | None = None,
               lid: int | None = None, status: str = "planned") -> None:
        self.iid += 1
        self.db.execute("INSERT INTO eq_intents(iid, instance, family, version, decided_day, exec_day, at, kind, symbol, "
                        "lid, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (self.iid, instance, instance.split("@")[0], 1, day,
                         schedule.next_session(day).isoformat(), at_, kind, symbol, lid, status, 0.0, 0.0))
        self.db.commit()

    def put(self, key: str, value) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES(?, ?)", (key, json.dumps(value)))
        self.db.commit()

    def decided(self, instance: str, day: str) -> None:
        self.db.execute("UPDATE eq_instances SET last_decided_day=? WHERE id=?", (day, instance))
        self.db.commit()

    def bars(self, slice_, day: str, symbols, *, history: int, bump: tuple[str, str, float] | None = None) -> None:
        """The rows the book's `_fetch_bars` writes for the decision of `day` (raw and all through it, from its
        `start`), with the decision's kv; `bump` (symbol, day, cents) moves one adjusted close, as a vendor's rounding
        of a later fetch does."""
        t = [ordinal(dt.date.fromisoformat(day)) == int(d) for d in slice_.days].index(True)
        start = (dt.date.fromisoformat(day) - dt.timedelta(days=int(history * 1.5) + 14)).isoformat()
        shas = {}
        for symbol in symbols:
            for name in ("raw", "all"):
                sha = hashlib.sha256(f"{day}|{symbol}|{name}".encode()).hexdigest()
                shas.setdefault(symbol, {})[name] = sha
                for row in synth.bar_rows(slice_, symbol, t, adjustment=name):
                    d = dt.datetime.fromisoformat(row["t"].replace("Z", "+00:00")).astimezone(NY).date().isoformat()
                    if d < start:
                        continue
                    close = row["c"] + (bump[2] if bump and name == "all" and (symbol, d) == bump[:2] else 0.0)
                    self.db.execute("INSERT OR REPLACE INTO eq_bars(day, symbol, adjustment, o, h, l, c, v, fetched_at, "
                                    "sha, audit) VALUES(?,?,?,?,?,?,?,?,?,?,NULL)",
                                    (d, symbol, name, str(row["o"]), str(row["h"]), str(row["l"]), str(close),
                                     str(row["v"]), 0.0, sha))
        self.put("eq_decision", {"day": day, "start": start, "end": day, "symbols": sorted(symbols), "shas": shas,
                                 "audit": None, "fetched_at": 0.0})


def decide_loop(decider, run, *, reload_at: int | None = None) -> list[tuple[str, list, set[int]]]:
    """[(decision day, the program's intents as the child answers them, the lot ids it held)] of one instance asked
    every decision of `run` (the live side of a fixture). `reload_at`: the instance is dropped and loaded again before
    that decision (what a deploy does to the live child: fresh STATE)."""
    key = f"fixture-live:{run.program.key}"
    payload = {"code": run.program.code, "params": run.program.params, "name": run.program.key, "timeout": 1.0,
               "max_errors": 25}
    decider.kind_load("equity", key, payload)
    out = []
    try:
        for i, inputs in enumerate(elane_train.state_inputs(run)):
            if reload_at is not None and i == reload_at:
                decider.kind_drop("equity", key)
                decider.kind_load("equity", key, payload)
            answer = decider.kind("equity", "decide", {"jobs": [{"key": key, "inputs": inputs}]})
            day = (dt.date(1970, 1, 1) + dt.timedelta(days=int(inputs.days[-1]))).isoformat()
            out.append((day, answer["results"][key]["intents"], {int(p["id"]) for p in inputs.positions}))
    finally:
        decider.kind_drop("equity", key)
    return out


def record(book: Book, instance: str, day: str, intents, held: set[int], needs, lots: dict[int, dict], *,
           base: int = 100) -> None:
    """The `eq_intents` rows league/equity/live.py `_record_intents` writes for one decide's intents (a fixture of
    E1's rule: a malformed or refused intent is a "buy" row with no symbol, a buy outside NEEDS a "buy" row with its
    symbol, a sell of an unknown lot a "sell" row with no lid, a cancel a "cancel" row)."""
    selling: set[int] = set()
    for raw in list(intents)[:config.MAX_INTENTS]:
        if not isinstance(raw, dict):
            book.intent(instance, day, "buy", status="refused")
            continue
        at_ = raw.get("at", "open")
        if at_ not in ("open", "close"):
            book.intent(instance, day, "buy", status="refused")
        elif "buy" in raw:
            symbol = str(raw.get("buy") or "").upper()
            book.intent(instance, day, "buy", at_=at_, symbol=symbol or None,
                        status="planned" if symbol in needs else "refused")
        elif "sell" in raw:
            try:
                lid = int(raw.get("sell"))
            except (TypeError, ValueError):
                lid = -1
            if lid not in held:
                book.intent(instance, day, "sell", at_=at_, status="refused")
            else:
                book.intent(instance, day, "sell", at_=at_, symbol=lots[lid]["symbol"], lid=base + lid,
                            status="refused" if lid in selling else "planned")
                selling.add(lid)
        elif "cancel" in raw:
            book.intent(instance, day, "cancel", status="refused")
        else:
            book.intent(instance, day, "buy", status="refused")


def mirror(book: Book, instance: str, run, decided: list[tuple[str, list, set[int]]], *, base: int = 100,
           until: str | None = None, skip: set[str] = frozenset()) -> None:
    """The live book of an instance that decided and filled exactly as `run` did: its lots (ids `base` + the run's)
    and its intents of every decision day up to `until`, less the days in `skip` (a decide that failed)."""
    lots = {int(lot["lid"]): lot for lot in run.result["lots"]}
    for lid, lot in lots.items():
        if until is None or lot["entry_day"] <= schedule.next_session(until).isoformat():
            book.lot(base + lid, instance, lot["symbol"], lot["entry_day"], lot["entry_at"], exit_day=lot["exit_day"],
                     exit_at=lot["exit_at"])
    needs = set(run.program.needs["symbols"])
    for day, intents, held in decided:
        if (until is None or day <= until) and day not in skip:
            record(book, instance, day, intents, held, needs, lots, base=base)


class WithAStore(unittest.TestCase):
    """A synthetic gated store through `STORE_END` (built once a class), a forward store in memory, the fakes in."""

    SPLITS: dict = {}

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.state = Path(cls._tmp.name) / "state"
        cls.state.mkdir()
        cls.store_root = synth.synthetic_store(cls.state / "equity-daily", symbols=("SPY", "QQQ", "IWM"),
                                               start=STORE_START, end=STORE_END, gate=True, splits=cls.SPLITS)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        install(self)
        self.db = memory(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.decider = InlineDecider()

    def shadow(self, through, **kw) -> Shadow:
        kw.setdefault("decider", self.decider)
        return Shadow(self.store_root, through=through, **kw)

    def book(self) -> Book:
        book = Book(self.root / forward_twins.LIVE_DB)
        self.addCleanup(book.close)
        return book

    def night(self, through: str, **kw) -> dict:
        """The end of the forward night that closed `through` (18:35 ET), on a fresh fake of B's Shadow."""
        return forward_twins.finish(self.root, self.db, self.shadow(through, **kw), now=at(through, 18, 35))

    def twin_rows(self, instance: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM fwd_twins" + (" WHERE instance=?" if instance else "") + " ORDER BY instance, day"
        return list(self.db.execute(sql, (instance,) if instance else ()))

    def live_instance(self, key: str, code: str, *, through: str = "2026-10-30", first: str = D1, reload_at=None,
                      mirror_until: str | None = None, skip=frozenset(), **instance):
        """A registered program, its live instance created in the decide step of `first`, and a book that decided
        and filled as its twin does through `through`. (the book, the instance id, the pid, the twin's run)."""
        pid = register(self.db, key, code)
        book = self.book()
        iid = book.instance(key, code, created=at(first, 16, 25), **instance)
        run = self.shadow(through).run_from(fake_program(self.db, key), schedule.next_session(first))
        decided = decide_loop(self.decider, run, reload_at=reload_at)
        mirror(book, iid, run, decided, until=mirror_until, skip=skip)
        return book, iid, pid, run


# ============================================================================================ D12: the one key rule
class TheKeyRule(unittest.TestCase):
    """`keys_of`: BOTH SIDES READ THE SAME RULE."""

    HELD = {3: {"symbol": "SPY", "entry_day": D1}, 4: {"symbol": "QQQ", "entry_day": D2}}

    def keys(self, intents, held=None, needs=("SPY", "QQQ")):
        return forward_twins.keys_of(intents, needs=needs, held=self.HELD if held is None else held)

    def test_a_buy_and_a_sell_and_their_fill_points(self):
        self.assertEqual(self.keys([{"buy": "SPY", "share": 0.5}, {"buy": "QQQ", "usd": 100.0, "at": "close"},
                                    {"sell": 3, "at": "close"}, {"sell": 4}]),
                         ["B|SPY|open", "B|QQQ|close", f"S|SPY|close|{D1}", f"S|QQQ|open|{D2}"])

    def test_a_buy_is_kept_whatever_its_size_says(self):
        self.assertEqual(self.keys([{"buy": "SPY"}, {"buy": "spy ", "share": 7}, {"buy": "SPY", "usd": -1, "share": 2}]),
                         ["B|SPY|open"] * 3)

    def test_what_is_dropped(self):
        junk = ["not a dict", None, 7, {"buy": "IWM", "share": 0.1}, {"buy": "", "share": 0.1}, {"buy": None},
                {"sell": 999}, {"sell": "3"}, {"sell": None}, {"sell": 3.5}, {"sell": True}, {"cancel": 7},
                {"cancel": 3, "at": "open"}, {"buy": "SPY", "at": "noon"}, {"sell": 3, "at": "moc"}, {"hold": "SPY"}, {}]
        self.assertEqual(self.keys(junk), [])
        self.assertEqual(self.keys(junk + [{"buy": "SPY", "share": 0.2}]), ["B|SPY|open"])

    def test_a_second_sell_of_the_same_lot_is_kept_too(self):
        self.assertEqual(self.keys([{"sell": 3}, {"sell": 3}]), [f"S|SPY|open|{D1}"] * 2)

    def test_a_sell_is_kept_only_for_a_lot_that_side_holds(self):
        self.assertEqual(self.keys([{"sell": 3}], held={}), [])
        self.assertEqual(self.keys([{"sell": 3.0}]), [f"S|SPY|open|{D1}"], "a whole number names the lot")

    def test_only_the_first_max_intents_count(self):
        many = [{"buy": "SPY", "share": 0.01}] * (config.MAX_INTENTS + 5)
        self.assertEqual(len(self.keys(many)), config.MAX_INTENTS)
        late = [{"cancel": 1}] * config.MAX_INTENTS + [{"buy": "SPY", "share": 0.1}]
        self.assertEqual(self.keys(late), [], "an intent past the cap is not read, on either side")

    def test_what_is_not_a_list_of_intents(self):
        self.assertEqual(self.keys(None), [])
        self.assertEqual(self.keys("buy SPY"), [])
        self.assertEqual(self.keys({"buy": "SPY", "share": 0.5}), ["B|SPY|open"], "one dict is one intent")

    def test_the_same_junk_intents_on_both_sides_agree(self):
        junk = [{"sell": 999}, {"buy": "IWM", "share": 0.1}, {"cancel": 7}, "x", {"buy": "SPY", "at": "noon"}]
        real = [{"sell": 3, "at": "open"}, {"buy": "SPY", "share": 0.4, "at": "close"}]
        live = self.keys(junk + real)
        shadow = self.keys(real + junk, held={9: {"symbol": "SPY", "entry_day": D1}} | {})   # another book's lot ids
        self.assertEqual(live, [f"S|SPY|open|{D1}", "B|SPY|close"])
        shadow = forward_twins.keys_of([{"sell": 9, "at": "open"}, {"buy": "SPY", "share": 0.4, "at": "close"}] + junk,
                                       needs=("SPY", "QQQ"), held={9: {"symbol": "SPY", "entry_day": D1}})
        self.assertTrue(forward_twins.agree(live, shadow), "a lot is named by its symbol and entry day, never its id")
        self.assertTrue(forward_twins.agree(self.keys(junk), forward_twins.keys_of([], needs=("SPY",), held={})))

    def test_agree_is_a_multisets_equality(self):
        a = forward_twins.agree
        self.assertTrue(a([], []))
        self.assertTrue(a(["B|SPY|open", "S|SPY|open|d"], ["S|SPY|open|d", "B|SPY|open"]), "order is not read")
        self.assertFalse(a(["B|SPY|open"], ["B|SPY|open", "B|SPY|open"]), "a count is")
        self.assertFalse(a([], ["B|SPY|open"]))
        self.assertFalse(a(["B|SPY|open"], ["B|SPY|close"]))

    def test_cause(self):
        c = forward_twins.cause
        self.assertEqual([c(True, "a", "b"), c(None, "a", "b")], [None, None])
        self.assertEqual(c(False, "aaaa", "bbbb"), "bars")
        self.assertEqual(c(False, "aaaa", "aaaa"), "program")
        self.assertEqual([c(False, None, "aaaa"), c(False, "aaaa", None), c(False, "", "aaaa")], ["unknown"] * 3)
        self.assertEqual({c(False, "a", "b"), c(False, "a", "a"), c(False, None, "a")}, set(forward_db.CAUSES))

    def test_participation(self):
        twin = [{"symbol": "SPY", "entry_day": D2, "entry_at": "close"}, {"symbol": "SPY", "entry_day": D3, "entry_at": "close"},
                {"symbol": "QQQ", "entry_day": D3, "entry_at": "open"}]
        live = [{"symbol": "SPY", "opened_day": D2, "entry_at": "close"}, {"symbol": "QQQ", "opened_day": D3, "entry_at": "open"},
                {"symbol": "QQQ", "opened_day": D4, "entry_at": "open"}]
        self.assertEqual(forward_twins.participation(live, twin),
                         {"matched": 2, "missed": 1, "extra": 1, "rate": 0.5})
        self.assertEqual(forward_twins.participation([], []), {"matched": 0, "missed": 0, "extra": 0, "rate": None})
        same = [{"symbol": "SPY", "entry_day": D2, "entry_at": "close"}] * 2
        self.assertEqual(forward_twins.participation(same[:1], same)["missed"], 1, "two lots of one key are two lots")
        self.assertEqual(forward_twins.participation(same, same)["rate"], 1.0)
        other = [{"symbol": "SPY", "entry_day": D2, "entry_at": "open"}]
        self.assertEqual(forward_twins.participation(other, same[:1]),
                         {"matched": 0, "missed": 1, "extra": 1, "rate": 0.0}, "the fill point is part of the key")


class TheFirstSession(unittest.TestCase):
    """D12's `d_first`: the latest session whose 16:20 bars moment is at or before the instance's creation."""

    def first(self, moment: float) -> str:
        return forward_twins.d_first({"created_at": moment}).isoformat()

    def test_1625_and_0800_the_next_morning_name_the_same_session(self):
        self.assertEqual(self.first(at(D2, 16, 25)), D2)
        self.assertEqual(self.first(at(D3, 8, 0)), D2, "a catch-up decide the next morning is that session's")
        self.assertEqual(self.first(at(D3, 15, 59)), D2)
        self.assertEqual(self.first(at(D2, 16, 20)), D2, "the bars moment itself")
        self.assertEqual(self.first(at(D2, 16, 19)), D1, "before the bars moment the last decision session is the one before")

    def test_a_weekend_and_a_half_day(self):
        self.assertEqual(self.first(at("2026-10-17", 12, 0)), "2026-10-16", "Saturday: Friday's session")
        self.assertEqual(self.first(at("2026-10-19", 9, 0)), "2026-10-16", "Monday before its bars: Friday's")
        self.assertEqual(self.first(at("2026-11-27", 13, 20)), "2026-11-27", "a half day's bars come at 13:20")
        self.assertEqual(self.first(at("2026-11-27", 13, 19)), "2026-11-25", "Thanksgiving is not a session")

    def test_it_is_the_books_own_rule(self):
        # league/equity/live.py `_last_closed`, with the design's offsets (the constitution's are held equal to them
        # in league/tests/test_fill_minutes.py).
        for moment in (at(D2, 16, 25), at(D3, 8, 0), at("2026-10-17", 12, 0), at("2026-11-27", 13, 30)):
            d = schedule.ny_day(moment)
            while not ((m := schedule.moments(d)) is not None and m.bars_at <= moment):
                d -= dt.timedelta(days=1)
            self.assertEqual(forward_twins.d_first({"created_at": moment}), d)

    def test_retired(self):
        self.assertIsNone(forward_twins.d_retired({"created_at": 1.0, "retired_at": None}))
        self.assertEqual(forward_twins.d_retired({"retired_at": at(D3, 16, 22)}).isoformat(), D3)
        self.assertEqual(forward_twins.registry_key("fake-family@3:r"), "fake-family@3")
        self.assertEqual(forward_twins.registry_key("fake-family@3"), "fake-family@3")


# =============================================================================================== D10: the live-like price
def golden_run(pid: int = 7):
    """A hand-made shadow run of three sessions on a $1,000 sleeve: lot 1 bought at D1's open and sold at D3's open,
    lot 2 bought at D2's close and still open."""
    days = np.array([ordinal(dt.date.fromisoformat(d)) for d in (D1, D2, D3)], dtype=np.int32)
    series = screen.Series(days=days, r=np.array([0.001, -0.002, 0.003]), w=np.array([0.25, 0.5, 0.5]),
                           b=np.zeros(3), exits=np.array([0, 0, 1]), invested=np.array([True, True, True]))
    lots = [{"lid": 1, "symbol": "SPY", "weight": 0.5, "qty": 5.0, "entry_day": D1, "entry_at": "open", "exit_day": D3,
             "exit_at": "open", "exit_px": 101.0},
            {"lid": 2, "symbol": "QQQ", "weight": 0.25, "qty": 2.5, "entry_day": D2, "entry_at": "close", "exit_day": None,
             "exit_at": None, "exit_px": None}]
    program = forward_db.Program(pid, "fake-golden@1", "fake-golden", 1, "beta", "train_pass", "index", "beta:fake-golden",
                                 "NEEDS = {}", {}, {"symbols": ["SPY", "QQQ"], "history": 1, "max_hold_sessions": 5},
                                 "sha", "run", 0.0, dt.date(2026, 10, 9), T0, "S2", "0.03")
    return forward_db.ShadowRun(program, {"capital": "1000", "status": "ok", "lots": lots}, None, series)


GOLDEN_DRIFT = {(D1, "SPY", "open"): 4.0, (D2, "QQQ", "close"): -2.0, (D3, "SPY", "open"): 6.0}


class TheLiveLikeSeries(unittest.TestCase):
    """D10: pnl_ll(d) = r(d) x capital - sum of N_e x delta_e over the lots entered on d + sum of N_x x delta_x over
    the lots exited on d; r_ll = pnl_ll / capital."""

    def setUp(self):
        install(self)
        self.db = memory(self)

    def gaps(self, drift=GOLDEN_DRIFT):
        self.db.executemany("INSERT OR IGNORE INTO fwd_fillgap(day, symbol, at, official, livelike, drift_bp, bar, field) "
                            "VALUES(?,?,?,100.0,100.0,?,'t','vw')", [(*key, bp) for key, bp in drift.items()])
        self.db.commit()

    def test_the_golden_two_lot_run_by_hand(self):
        out = forward_twins.livelike_series(golden_run(), lambda d, s, a: GOLDEN_DRIFT.get((d, s, a)))
        # D1: a buy of 0.5 x 1000 at a price 4 bp above the official open costs 500 x 0.0004 = 0.20 of 1.00.
        self.assertAlmostEqual(out[D1], (1.00 - 0.20) / 1000.0, places=15)
        # D2: a buy of 0.25 x 1000 at a close 2 bp BELOW the official one gains 250 x 0.0002 = 0.05.
        self.assertAlmostEqual(out[D2], (-2.00 + 0.05) / 1000.0, places=15)
        # D3: a sale of 5 shares at 101 (505) at a price 6 bp above the official open gains 505 x 0.0006 = 0.303.
        self.assertAlmostEqual(out[D3], (3.00 + 0.303) / 1000.0, places=15)
        self.assertEqual(sorted(out), [D1, D2, D3])

    def test_no_drift_is_the_official_series(self):
        out = forward_twins.livelike_series(golden_run(), lambda d, s, a: 0.0)
        self.assertEqual([out[d] for d in (D1, D2, D3)], [0.001, -0.002, 0.003])

    def test_a_day_with_a_needed_drift_missing_is_none_and_only_that_day(self):
        drift = {k: v for k, v in GOLDEN_DRIFT.items() if k[0] != D2}
        out = forward_twins.livelike_series(golden_run(), lambda d, s, a: drift.get((d, s, a)))
        self.assertIsNone(out[D2])
        self.assertIsNotNone(out[D1])
        self.assertIsNotNone(out[D3])
        asked = []
        forward_twins.livelike_series(golden_run(), lambda d, s, a: asked.append((d, s, a)) or 0.0)
        self.assertEqual(sorted(asked), sorted(GOLDEN_DRIFT), "a drift is asked only at a lot's own fills")

    def test_on_run_writes_the_days_that_have_none(self):
        self.gaps()
        self.assertEqual(forward_twins.on_run(self.db, golden_run(), now=10.0, settings=SETTINGS), 3)
        rows = {r["day"]: r for r in self.db.execute("SELECT * FROM fwd_ll")}
        self.assertEqual(sorted(rows), [D1, D2, D3])
        self.assertAlmostEqual(rows[D3]["r_ll"], 0.003303, places=15)
        self.assertEqual((rows[D1]["pid"], rows[D1]["engine"], rows[D1]["at"]), (7, 1, 10.0))
        self.assertEqual(forward_twins.on_run(self.db, golden_run(), now=11.0, settings=SETTINGS), 0, "a second night")
        self.assertEqual(self.db.execute("SELECT COUNT(*), MAX(at) FROM fwd_ll").fetchone()[:], (3, 10.0))
        self.assertEqual(events(self.db, "no_minute"), [])

    def test_a_missing_minute_is_one_event_over_three_nights_and_the_row_comes_with_the_minute(self):
        self.gaps({k: v for k, v in GOLDEN_DRIFT.items() if k[0] != D2})
        for night in (1.0, 2.0, 3.0):
            written = forward_twins.on_run(self.db, golden_run(), now=night, settings=SETTINGS)
            self.assertEqual(written, 2 if night == 1.0 else 0)
        self.assertEqual([r["day"] for r in self.db.execute("SELECT day FROM fwd_ll ORDER BY day")], [D1, D3])
        found = events(self.db, "no_minute")
        self.assertEqual([(e["pid"], e["day"], e["at"]) for e in found], [(7, D2, 1.0)], "once a (pid, day)")
        self.assertEqual(found[0]["payload"]["symbols"], ["QQQ"])
        self.assertIn("why", found[0]["payload"])
        self.gaps()                                    # the minutes job's backfill fetched the day: its row is written
        self.assertEqual(forward_twins.on_run(self.db, golden_run(), now=4.0, settings=SETTINGS), 1)
        self.assertAlmostEqual(self.db.execute("SELECT r_ll FROM fwd_ll WHERE day=?", (D2,)).fetchone()[0], -0.00195,
                               places=15)
        self.assertEqual(len(events(self.db, "no_minute")), 1)

    def test_nothing_is_written_with_fill_minutes_false(self):
        off = {"elane": {"forward": {"mode": "record", "fill_minutes": False}}}
        self.assertEqual(forward_twins.on_run(self.db, golden_run(), now=1.0, settings=off), 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_ll").fetchone()[0], 0)
        self.assertEqual(events(self.db, "no_minute"), [], "no missing-minute event either")
        for unread in (None, {}, {"elane": {"forward": {"mode": "off"}}}, {"elane": {"forward": {"fill_minutes": True}}}):
            self.assertEqual(forward_twins.on_run(self.db, golden_run(), now=1.0, settings=unread), 0)
        self.assertEqual(events(self.db, "no_minute"), [], "with the forward mode off nothing is written at all")
        with mock.patch.object(forward_db, "cfg", side_effect=NotImplementedError("A: not landed")):
            self.assertEqual(forward_twins.on_run(self.db, golden_run(), now=1.0, settings=SETTINGS), 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_ll").fetchone()[0], 0)

    def test_another_pid_and_another_engine_have_their_own_rows(self):
        self.gaps()
        forward_twins.on_run(self.db, golden_run(7), now=1.0, settings=SETTINGS)
        forward_twins.on_run(self.db, golden_run(8), now=1.0, settings=SETTINGS)
        self.db.execute("INSERT INTO fwd_engines(label, at) VALUES('fake-engine+1+fwd-1', 2.0)")
        self.assertEqual(forward_twins.on_run(self.db, golden_run(7), now=2.0, settings=SETTINGS), 3)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_ll").fetchone()[0], 9)

    def stored(self, engine: int, days, *, pid: int = 7, at_: float) -> None:
        """The `fwd_days` rows the shadow's write leaves for a run's days (package B's writer; SQL here)."""
        self.db.executemany("INSERT INTO fwd_days(pid, day, engine, r, w, b, entries, exits, status, at) "
                            "VALUES(?,?,?,0.0,0.0,0.0,0,0,'ok',?)", [(pid, day, engine, at_) for day in days])
        self.db.commit()

    def test_the_re_price_stays_with_the_series_the_shadow_wrote(self):
        # An engine label that CAME BACK (a rollback restores a label that has its id): the night writes the run under
        # the old id 1 while the newer id 2 exists. The re-price goes under 1, never under an id the run was not
        # written under.
        self.gaps()
        self.db.execute("INSERT INTO fwd_engines(label, at) VALUES('fake-engine+1+fwd-1', 2.0)")
        self.assertEqual(fake_engine_now(self.db), 2)
        self.stored(2, (D1, D2), at_=2.0)               # the abandoned label's rows: it never saw D3
        self.stored(1, (D1, D2, D3), at_=3.0)           # tonight's
        self.stored(2, (D1, D2, D3), pid=8, at_=3.0)    # another program's rows name nothing for this one
        self.assertEqual(forward_twins.on_run(self.db, golden_run(), now=3.0, settings=SETTINGS), 3)
        self.assertEqual([tuple(r) for r in self.db.execute("SELECT DISTINCT pid, engine FROM fwd_ll")], [(7, 1)])
        self.assertEqual(forward_twins.on_run(self.db, golden_run(), now=3.5, settings=SETTINGS), 0, "written once")
        # The same night run again under the newer label (a deploy between two runs of it): the newest row of the
        # run's last day names the engine.
        self.stored(2, (D3,), at_=4.0)
        self.assertEqual(forward_twins.on_run(self.db, golden_run(), now=4.0, settings=SETTINGS), 3)
        self.assertEqual([tuple(r) for r in self.db.execute("SELECT engine, COUNT(*) FROM fwd_ll WHERE pid=7 "
                                                            "GROUP BY engine ORDER BY engine")], [(1, 3), (2, 3)])

    def test_a_missing_minute_is_still_one_event_whatever_engine_the_run_is_under(self):
        self.gaps({k: v for k, v in GOLDEN_DRIFT.items() if k[0] != D2})
        self.db.execute("INSERT INTO fwd_engines(label, at) VALUES('fake-engine+1+fwd-1', 2.0)")
        self.stored(1, (D1, D2, D3), at_=1.0)
        self.assertEqual(forward_twins.on_run(self.db, golden_run(), now=1.0, settings=SETTINGS), 2)
        self.stored(2, (D1, D2, D3), at_=2.0)           # the label moved: the whole history is written again
        self.assertEqual(forward_twins.on_run(self.db, golden_run(), now=2.0, settings=SETTINGS), 2)
        self.assertEqual(len(events(self.db, "no_minute")), 1, "once a (pid, day), not once an engine")


class TheTimingTable(WithAStore):
    """`begin`: one `fwd_fillgap` row a (day, symbol, at) for every store symbol, from the day's minutes file."""

    def minutes(self, day: str, *, shadow=None, skip=(), bp=None, field="vw"):
        shadow = shadow or self.shadow(STORE_END)
        bp = bp or {"open": 5.0, "close": -3.0}
        rows = {}
        for symbol in shadow.store.symbols():
            rows[symbol] = []
            for at_ in ("open", "close"):
                if (symbol, at_) in skip:
                    continue
                price = shadow.official(symbol, day, at_) * (1.0 + bp[at_] / 1e4)
                stamp = fill_minutes.bar_start(day, at_).strftime(fill_minutes.STAMP)
                rows[symbol].append([stamp, price, price, price, price, 100.0, price if field == "vw" else None, 3])
        fill_minutes.write_day(self.root, day, rows, fetched_at=1.0)

    def test_every_store_symbol_and_both_fill_points(self):
        shadow = self.shadow(D2)
        self.minutes(D1)
        self.minutes(D2)
        self.assertEqual(forward_twins.begin(self.root, self.db, shadow, now=5.0), {"days": 2, "rows": 12})
        rows = list(self.db.execute("SELECT * FROM fwd_fillgap ORDER BY day, symbol, at"))
        self.assertEqual({(r["day"], r["symbol"], r["at"]) for r in rows},
                         {(d, s, a) for d in (D1, D2) for s in ("SPY", "QQQ", "IWM") for a in ("open", "close")})
        for row in rows:
            official = shadow.official(row["symbol"], row["day"], row["at"])
            self.assertEqual(row["official"], official)
            self.assertAlmostEqual(row["drift_bp"], (row["livelike"] / official - 1.0) * 1e4, places=9)
            self.assertAlmostEqual(row["drift_bp"], 5.0 if row["at"] == "open" else -3.0, places=6)
            self.assertEqual(row["field"], "vw")
        self.assertEqual({r["bar"] for r in rows if r["day"] == D1}, {"2026-10-12T13:31:00Z", "2026-10-12T19:55:00Z"})

    def test_a_second_night_writes_nothing_again(self):
        shadow = self.shadow(D1)
        self.minutes(D1)
        self.assertEqual(forward_twins.begin(self.root, self.db, shadow, now=5.0)["rows"], 6)
        self.assertEqual(forward_twins.begin(self.root, self.db, shadow, now=6.0), {"days": 0, "rows": 0})

    def test_only_forward_days_the_store_has_closed(self):
        self.minutes("2026-10-09")                      # the look cap: a file that should never exist is not read
        self.minutes(D1)
        self.minutes(D2)                                # the minutes came at 16:45; the store has not closed that day
        self.assertEqual(forward_twins.begin(self.root, self.db, self.shadow(D1), now=5.0), {"days": 1, "rows": 6})
        self.assertEqual({r[0] for r in self.db.execute("SELECT day FROM fwd_fillgap")}, {D1})
        self.assertEqual(forward_twins.begin(self.root, self.db, self.shadow(D2), now=6.0), {"days": 1, "rows": 6})

    def test_a_symbol_without_its_minute_has_no_row_and_the_fallback_names_its_field(self):
        self.minutes(D1, skip={("IWM", "close")}, field="hlc3")
        self.assertEqual(forward_twins.begin(self.root, self.db, self.shadow(D1), now=5.0)["rows"], 5)
        self.assertEqual({r[0] for r in self.db.execute("SELECT field FROM fwd_fillgap")}, {"hlc3"})
        self.assertIsNone(self.db.execute("SELECT 1 FROM fwd_fillgap WHERE symbol='IWM' AND at='close'").fetchone())

    def test_a_recent_day_that_lacks_a_row_is_read_again(self):
        self.minutes(D1, skip={("IWM", "close")})
        shadow = self.shadow(D1)
        self.assertEqual(forward_twins.begin(self.root, self.db, shadow, now=5.0)["rows"], 5)
        self.minutes(D1)                                # (a fixture: the file is written once on the House)
        self.assertEqual(forward_twins.begin(self.root, self.db, shadow, now=6.0), {"days": 1, "rows": 1})

    def test_nothing_is_written_with_fill_minutes_false(self):
        self.minutes(D1)
        for off in ({"elane": {"forward": {"mode": "record", "fill_minutes": False}}},
                    {"elane": {"forward": {"mode": "off"}}}, None):
            self.assertEqual(forward_twins.begin(self.root, self.db, self.shadow(D1, settings=off), now=5.0),
                             {"days": 0, "rows": 0})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_fillgap").fetchone()[0], 0)

    def test_the_table_feeds_the_re_price_of_a_real_run(self):
        # E1's engine on the synthetic store, the timing table from invented minutes, then D10 by hand for one day.
        register(self.db, "fake-overnight@1", OVERNIGHT)
        program = dataclasses.replace(fake_program(self.db, "fake-overnight@1"), first_day=T0)
        shadow = self.shadow(D4)
        for day in (D1, D2, D3, D4):
            self.minutes(day, shadow=shadow)
        forward_twins.begin(self.root, self.db, shadow, now=5.0)
        run = shadow.run_from(program, T0)
        self.assertEqual(forward_twins.on_run(self.db, run, now=6.0, settings=SETTINGS), 4)
        capital = float(run.result["capital"])
        by_day = {r["day"]: r["r_ll"] for r in self.db.execute("SELECT day, r_ll FROM fwd_ll")}
        days = [(dt.date(1970, 1, 1) + dt.timedelta(days=int(d))).isoformat() for d in run.series.days]
        for i, day in enumerate(days):
            pnl = float(run.series.r[i]) * capital
            for lot in run.result["lots"]:
                if lot["entry_day"] == day:           # bought at the close, 3 bp under the official close
                    pnl -= lot["weight"] * capital * (-3.0 / 1e4)
                if lot["exit_day"] == day:            # sold at the open, 5 bp over the official open
                    pnl += lot["qty"] * lot["exit_px"] * (5.0 / 1e4)
            self.assertAlmostEqual(by_day[day], pnl / capital, places=12, msg=day)
        self.assertGreater(len(run.result["lots"]), 2)


# ================================================================================================= D11: the fill gap
def closed_lot(*, entry_px: str, exit_px: str, qty: str = "0.5", fees: str = "0.02", div: str = "0", lid: int = 1,
               symbol: str = "SPY", entry_at: str = "open", exit_at: str = "close", opened_day: str = D2,
               exit_day: str = D4, instance: str = "fake-overnight@1:r") -> dict:
    """A closed `eq_lots` row whose cash is what its prices, fees and dividends make."""
    q, e, x = Decimal(qty), Decimal(entry_px), Decimal(exit_px)
    notional = q * e
    cash = q * x - Decimal(fees) + Decimal(div) - notional
    return {"lid": lid, "instance": instance, "family": instance.split("@")[0], "version": 1, "lane": "beta",
            "symbol": symbol, "class": "etf", "qty": qty, "opened_qty": qty, "entry_px": entry_px,
            "entry_notional": str(notional), "entry_at": entry_at, "fees": fees, "div": div, "opened_day": opened_day,
            "status": "closed", "exit_px": exit_px, "exit_at": exit_at, "exit_day": exit_day,
            "closed_at": at(exit_day, 15, 56), "cash": str(cash), "opened_at": at(opened_day, 9, 31)}


def official_bars(entry: float, leave: float, *, opened_day: str = D2, exit_day: str = D4) -> dict:
    """E1's `eq_bars` raw rows of a lot's entry and exit days: the official open and close both the given price."""
    row = lambda p: {"o": str(p), "h": str(p + 1), "l": str(p - 1), "c": str(p), "v": "1000", "audit": "ok",  # noqa: E731
                     "sha": "x"}
    return {opened_day: row(entry), exit_day: row(leave)}


class TheFillGap(unittest.TestCase):
    """D11 on E1's own twin record (`league.ops.twins.equity_twin`): slip = timing + execution, cost-positive."""

    def twin(self, lot, entry=100.0, leave=102.0):
        rec = twins.equity_twin(lot, official_bars(entry, leave, opened_day=lot["opened_day"], exit_day=lot["exit_day"]),
                                k=1.0, settled=True, at=1.0)
        self.assertEqual((rec["status"], rec["final"]), ("priced", True))
        return rec

    def test_timing_plus_execution_is_the_slip_on_both_sides(self):
        lot = closed_lot(entry_px="100.05", exit_px="101.90")
        rec = self.twin(lot)
        gap = forward_twins.lot_gap(lot, rec, 100.03, 101.95)
        self.assertEqual((gap["entry_slip_bp"], gap["exit_slip_bp"]), (rec["entry_slip_bp"], rec["exit_slip_bp"]))
        self.assertAlmostEqual(gap["timing_entry_bp"] + gap["exec_entry_bp"], gap["entry_slip_bp"], places=9)
        self.assertAlmostEqual(gap["timing_exit_bp"] + gap["exec_exit_bp"], gap["exit_slip_bp"], places=9)
        # By hand: the buy paid 100.05 against an official 100.00 (5 bp); the minute after the send traded at 100.03
        # (3 bp of it is timing, 2 bp execution). The sale got 101.90 against 102.00 (9.80 bp); the minute traded at
        # 101.95 (4.902 bp timing, 4.898 bp execution).
        self.assertAlmostEqual(gap["entry_slip_bp"], 5.0, places=2)
        self.assertAlmostEqual(gap["timing_entry_bp"], 3.0, places=4)
        self.assertAlmostEqual(gap["exec_entry_bp"], 2.0, places=2)
        self.assertAlmostEqual(gap["exit_slip_bp"], (1 - 101.90 / 102.0) * 1e4, places=2)
        self.assertAlmostEqual(gap["timing_exit_bp"], (1 - 101.95 / 102.0) * 1e4, places=4)

    def test_the_signs_are_cost_positive(self):
        worse = closed_lot(entry_px="100.05", exit_px="101.90")       # a buy that paid more, a sale that got less
        gap = forward_twins.lot_gap(worse, self.twin(worse), 100.03, 101.95)
        for key in ("entry_slip_bp", "exit_slip_bp", "timing_entry_bp", "timing_exit_bp", "exec_entry_bp", "exec_exit_bp"):
            self.assertGreater(gap[key], 0.0, key)
        self.assertGreater(gap["side_gap_bp"], 0.0, "worse than the model, a side")
        self.assertLess(gap["twin_gap_bp"], 0.0, "E1's gap is live minus twin: negative when the fills did worse")
        better = closed_lot(entry_px="99.95", exit_px="102.10")       # a buy that paid less, a sale that got more
        gap = forward_twins.lot_gap(better, self.twin(better), 99.98, 102.04)
        for key in ("entry_slip_bp", "exit_slip_bp", "timing_entry_bp", "timing_exit_bp", "side_gap_bp"):
            self.assertLess(gap[key], 0.0, key)
        self.assertGreater(gap["twin_gap_bp"], 0.0)

    def test_the_model_and_the_side_gap(self):
        lot = closed_lot(entry_px="100.05", exit_px="101.90")
        rec = self.twin(lot)
        gap = forward_twins.lot_gap(lot, rec, None, None)
        self.assertEqual(gap["model_bp"], rec["k"] * rec["hs_bp"])
        self.assertEqual(gap["model_bp"], 1.0, "SPY's half-spread at k 1.0")
        self.assertAlmostEqual(gap["side_gap_bp"], ((gap["entry_slip_bp"] - 1.0) + (gap["exit_slip_bp"] - 1.0)) / 2.0, places=4)
        self.assertEqual(gap["twin_gap_bp"], rec["gap_bp"])

    def test_the_side_gap_is_about_minus_e1s_gap_within_half_a_bp(self):
        # (The two differ in second order: a slip of s bp a side leaves about s x s / 10,000 bp between them.)
        for entry_px, exit_px in (("100.05", "101.90"), ("100.00", "102.00"), ("99.95", "102.10"), ("100.10", "101.92")):
            lot = closed_lot(entry_px=entry_px, exit_px=exit_px, qty="2.5", fees="0.02")
            rec = self.twin(lot)
            gap = forward_twins.lot_gap(lot, rec, None, None)
            self.assertLessEqual(abs(gap["side_gap_bp"] + gap["twin_gap_bp"]), 0.5, (entry_px, exit_px))

    def test_a_missing_minute_leaves_that_sides_timing_and_execution_none(self):
        lot = closed_lot(entry_px="100.05", exit_px="101.90")
        rec = self.twin(lot)
        gap = forward_twins.lot_gap(lot, rec, None, 101.95)
        self.assertEqual((gap["timing_entry_bp"], gap["exec_entry_bp"]), (None, None))
        self.assertIsNotNone(gap["timing_exit_bp"])
        self.assertIsNotNone(gap["side_gap_bp"], "the slips and the side gap need no minute")
        gap = forward_twins.lot_gap(lot, rec, 100.03, None)
        self.assertEqual((gap["timing_exit_bp"], gap["exec_exit_bp"]), (None, None))
        self.assertEqual(sorted(gap), sorted(("model_bp", "entry_slip_bp", "exit_slip_bp", "timing_entry_bp",
                                              "timing_exit_bp", "exec_entry_bp", "exec_exit_bp", "side_gap_bp",
                                              "twin_gap_bp")))

    def test_a_record_without_its_model_reads_the_symbols_own_half_spread(self):
        lot = closed_lot(entry_px="100.05", exit_px="101.90", symbol="TLT")
        rec = {**self.twin(lot), "hs_bp": None, "k": None}
        self.assertEqual(forward_twins.lot_gap(lot, rec, None, None)["model_bp"], 5.0)
        with self.assertRaises(ValueError):
            forward_twins.lot_gap({"symbol": "FAKE"}, {"hs_bp": None}, None, None)


class TheLotRows(WithAStore):
    """`finish` writes one `fwd_lotgap` row for every closed live lot with a final priced E1 twin."""

    def setUp(self):
        super().setUp()
        self.pid = register(self.db, "fake-overnight@1", OVERNIGHT)
        self.live = self.book()
        self.iid = self.live.instance("fake-overnight@1", OVERNIGHT, created=at(D1, 16, 25), retired=at(D1, 16, 26))
        self.records: dict = {}

    def lot(self, lid: int, *, final=True, status="priced", **kw) -> dict:
        lot = closed_lot(lid=lid, entry_px="100.05", exit_px="101.90", **kw)
        self.live.lot(lid, self.iid, lot["symbol"], lot["opened_day"], lot["entry_at"], exit_day=lot["exit_day"],
                      exit_at=lot["exit_at"], qty=lot["qty"], opened_qty=lot["qty"], entry_px=lot["entry_px"],
                      entry_notional=lot["entry_notional"], exit_px=lot["exit_px"], fees=lot["fees"], cash=lot["cash"])
        rec = twins.equity_twin(lot, official_bars(100.0, 102.0, opened_day=lot["opened_day"], exit_day=lot["exit_day"]),
                                k=1.0, settled=True, at=1.0)
        self.records[rec["key"]] = {**rec, "final": final, "status": status}
        db = sqlite3.connect(self.root / forward_twins.SWARM_DB)
        db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES(?, ?)", (twins.EQUITY_TWINS_KEY, json.dumps(self.records)))
        db.commit()
        db.close()
        return lot

    def minutes(self, day: str, prices: dict) -> None:
        rows = {"SPY": [[fill_minutes.bar_start(day, at_).strftime(fill_minutes.STAMP), p, p, p, p, 10.0, p, 1]
                        for at_, p in prices.items()]}
        fill_minutes.write_day(self.root, day, rows, fetched_at=1.0)

    def finish(self, through=D4, **kw):
        return forward_twins.finish(self.root, self.db, self.shadow(through, **kw), now=9.0)

    def test_a_closed_lot_with_a_final_priced_twin_gets_its_row_once(self):
        self.lot(1)
        self.minutes(D2, {"open": 100.03})
        self.minutes(D4, {"close": 101.95})
        out = self.finish()
        self.assertEqual((out["lots"], out["failed"]), (1, 0))
        row = self.db.execute("SELECT * FROM fwd_lotgap").fetchone()
        self.assertEqual((row["lid"], row["instance"], row["pid"], row["symbol"], row["opened_day"], row["exit_day"],
                          row["entry_at"], row["exit_at"], row["at"]),
                         (1, self.iid, self.pid, "SPY", D2, D4, "open", "close", 9.0))
        self.assertAlmostEqual(row["timing_entry_bp"], 3.0, places=4)
        self.assertAlmostEqual(row["timing_entry_bp"] + row["exec_entry_bp"], row["entry_slip_bp"], places=9)
        self.assertAlmostEqual(row["timing_exit_bp"] + row["exec_exit_bp"], row["exit_slip_bp"], places=9)
        self.assertEqual((row["model_bp"], row["twin_gap_bp"]), (1.0, self.records["eq:1"]["gap_bp"]))
        self.assertEqual(self.finish()["lots"], 0, "a lot's row is written once")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_lotgap").fetchone()[0], 1)

    def test_a_twin_that_is_not_final_or_not_priced_writes_nothing(self):
        self.lot(1, final=False)
        self.lot(2, status="no_bar")
        self.minutes(D2, {"open": 100.03})
        self.minutes(D4, {"close": 101.95})
        self.assertEqual(self.finish()["lots"], 0)
        self.records["eq:1"]["final"] = True
        self.lot(3)                                      # (rewrites the kv with lot 1 now final)
        self.assertEqual(self.finish()["lots"], 2)
        self.assertEqual([r[0] for r in self.db.execute("SELECT lid FROM fwd_lotgap ORDER BY lid")], [1, 3])

    def test_with_fill_minutes_false_the_row_has_its_slips_and_no_timing(self):
        self.lot(1)
        self.minutes(D2, {"open": 100.03})
        self.minutes(D4, {"close": 101.95})
        off = {"elane": {"forward": {"mode": "record", "fill_minutes": False}}}
        self.assertEqual(self.finish(settings=off)["lots"], 1)
        row = self.db.execute("SELECT * FROM fwd_lotgap").fetchone()
        self.assertEqual((row["timing_entry_bp"], row["exec_entry_bp"], row["timing_exit_bp"], row["exec_exit_bp"]),
                         (None, None, None, None))
        self.assertIsNotNone(row["side_gap_bp"])

    def test_the_row_waits_while_the_minutes_may_still_come_then_is_written_without_them(self):
        self.lot(1)
        self.minutes(D2, {"open": 100.03})               # the exit day's file has not been fetched yet
        self.assertEqual(self.finish(D4)["lots"], 0, "inside the backfill's reach: the row waits")
        self.assertEqual(self.finish("2026-10-28")["lots"], 0, "ten sessions back from Oct 28 is Oct 15")
        self.assertEqual(self.finish("2026-10-29")["lots"], 1, "past the backfill's reach: written once, as it is")
        row = self.db.execute("SELECT * FROM fwd_lotgap").fetchone()
        self.assertIsNotNone(row["timing_entry_bp"])
        self.assertEqual((row["timing_exit_bp"], row["exec_exit_bp"]), (None, None))

    def test_a_symbol_with_no_bar_in_a_fetched_minute_is_written_at_once(self):
        self.lot(1)
        self.minutes(D2, {"open": 100.03})
        self.minutes(D4, {"open": 50.0})                 # the file is there; the close send's minute has no SPY bar
        self.assertEqual(self.finish()["lots"], 1)
        self.assertIsNone(self.db.execute("SELECT timing_exit_bp FROM fwd_lotgap").fetchone()[0])

    def test_no_swarm_store_and_no_live_book(self):
        self.lot(1)
        (self.root / forward_twins.SWARM_DB).unlink()
        out = self.finish()
        self.assertEqual((out["lots"], out["failed"]), (0, 0))
        self.live.close()
        (self.root / forward_twins.LIVE_DB).unlink()
        out = self.finish()
        self.assertEqual(out["skipped"], "no live book")
        self.assertEqual({out[k] for k in forward_twins.FINISH_KEYS}, {0})


# ============================================================================================= D12: the twins' rows
class TheTwins(WithAStore):
    """`finish` on a book that decided and filled as its twin does, and on books that did not."""

    def test_a_book_that_decided_as_its_twin_agrees_every_session(self):
        book, iid, pid, run = self.live_instance("fake-overnight@1", OVERNIGHT)
        out = self.night("2026-10-23")
        rows = self.twin_rows()
        self.assertEqual([r["day"] for r in rows], forward_twins._sessions(T0, dt.date(2026, 10, 22)))
        self.assertEqual({(r["instance"], r["pid"], r["agree"], r["why"], r["cause"]) for r in rows},
                         {(iid, pid, 1, None, None)})
        self.assertEqual((out["instances"], out["twins"], out["disagreed"], out["interrupted"], out["failed"]),
                         (1, 9, 0, 0, 0))
        self.assertEqual(json.loads(rows[0]["shadow_keys"]), ["B|SPY|close"], "the twin starts flat at the first decision")
        self.assertEqual(json.loads(rows[1]["live_keys"]), ["S|SPY|open|2026-10-13", "B|SPY|close"])
        self.assertEqual(rows[1]["live_keys"], rows[1]["shadow_keys"])
        self.assertTrue(all(len(r["shadow_bars"]) == forward_db.BARS_HEX for r in rows))
        self.assertEqual({r["live_bars"] for r in rows}, {None}, "no night took the live decisions' bars")

    def test_the_twin_starts_flat_at_the_session_after_the_first_decision(self):
        book, iid, pid, run = self.live_instance("fake-overnight@1", OVERNIGHT, first=D3)
        shadow = self.shadow("2026-10-20")
        forward_twins.finish(self.root, self.db, shadow, now=1.0)
        self.assertEqual(shadow.runs, [("fake-overnight@1", D4)], "started at next_session(d_first)")
        rows = self.twin_rows()
        self.assertEqual(rows[0]["day"], D3, "the first row is the instance's first decision session")
        self.assertEqual(min(lot["entry_day"] for lot in run.result["lots"]), D4)
        self.assertEqual(json.loads(rows[0]["shadow_keys"]), ["B|SPY|close"], "no lot to sell: the twin holds nothing")

    def test_rows_lag_one_session_and_each_night_adds_the_next(self):
        self.live_instance("fake-overnight@1", OVERNIGHT)
        self.assertEqual(self.night(D1)["twins"], 0, "the first decision's session has not closed its next session")
        self.assertEqual(self.twin_rows(), [])
        self.assertEqual(self.night(D2)["twins"], 1)
        self.assertEqual([r["day"] for r in self.twin_rows()], [D1])
        self.assertEqual(self.night(D2)["twins"], 0, "the same night again writes nothing")
        self.assertEqual(self.night(D4)["twins"], 2)
        self.assertEqual([r["day"] for r in self.twin_rows()], [D1, D2, D3])
        self.assertEqual([tuple(r) for r in self.db.execute("SELECT instance, through FROM fwd_part ORDER BY through")],
                         [("fake-overnight@1:r", D2), ("fake-overnight@1:r", D4)])

    def test_a_row_is_written_once_and_never_rewritten(self):
        book, iid, pid, run = self.live_instance("fake-overnight@1", OVERNIGHT)
        self.night(D4)
        before = [tuple(r) for r in self.twin_rows()]
        book.db.execute("DELETE FROM eq_intents")        # the book changes afterwards: the rows written stand
        book.db.commit()
        self.night("2026-10-16")
        self.assertEqual([tuple(r) for r in self.twin_rows()][:3], before)

    def test_the_same_junk_on_both_sides_agrees_through_the_real_child(self):
        # The child hands both sides a sell of lot 999, a buy outside NEEDS and a cancel every session; the book records
        # them as E1 does (a sell with no lid, a buy with its symbol, a cancel row): dropped on both sides.
        book, iid, pid, run = self.live_instance("fake-junk@1", JUNK)
        kinds = {tuple(r) for r in book.db.execute("SELECT kind, symbol, lid IS NULL, status FROM eq_intents")}
        self.assertTrue({("sell", None, 1, "refused"), ("buy", "IWM", 1, "refused"), ("cancel", None, 1, "refused")} <= kinds)
        self.night("2026-10-23")
        rows = self.twin_rows()
        self.assertEqual({r["agree"] for r in rows}, {1})
        self.assertEqual(json.loads(rows[2]["live_keys"]), ["S|SPY|open|2026-10-14", "B|SPY|close"])
        self.assertEqual(len(rows), 9)

    def test_an_empty_live_session_against_an_empty_and_a_non_empty_shadow(self):
        # The clock program buys on every third decide: its twin's other sessions are empty or hold one sale.
        book, iid, pid, run = self.live_instance("fake-clock@1", CLOCK, skip={D3, D4})
        self.night("2026-10-23")
        rows = {r["day"]: r for r in self.twin_rows()}
        self.assertEqual((rows[D3]["shadow_keys"], rows[D3]["live_keys"], rows[D3]["agree"]), ("[]", "[]", 1),
                         "two empty sessions agree")
        self.assertEqual(json.loads(rows[D4]["shadow_keys"]), ["B|SPY|close"])
        self.assertEqual((rows[D4]["live_keys"], rows[D4]["agree"], rows[D4]["cause"]), ("[]", 0, "unknown"),
                         "a decide that failed left no intent: counted, its cause not known")
        self.assertEqual(sum(1 for r in rows.values() if r["agree"] == 0), 1)

    def test_a_state_losing_program_disagrees_after_a_reload(self):
        # A deploy reloads the live child at the fifth decision: its clock starts again, the twin's goes on.
        book, iid, pid, run = self.live_instance("fake-clock@1", CLOCK, reload_at=4)
        out = self.night("2026-10-23")
        rows = self.twin_rows()
        self.assertEqual([r["agree"] for r in rows[:4]], [1, 1, 1, 1])
        self.assertEqual((rows[4]["agree"], json.loads(rows[4]["live_keys"]), json.loads(rows[4]["shadow_keys"])),
                         (0, ["S|SPY|open|2026-10-16", "B|SPY|close"], ["S|SPY|open|2026-10-16"]),
                         "the reloaded clock buys again; the twin's does not")
        self.assertEqual(out["disagreed"], sum(1 for r in rows if r["agree"] == 0))
        self.assertGreater(out["disagreed"], 0)
        self.assertEqual({r["cause"] for r in rows if r["agree"] == 0}, {"unknown"})
        self.assertEqual(out["failed"], 0, "a disagreement is data, never an error")

    def test_a_stateless_program_agrees_through_the_same_reload(self):
        self.live_instance("fake-overnight@1", OVERNIGHT, reload_at=3)
        self.assertEqual(self.night("2026-10-23")["disagreed"], 0)

    def test_participation_with_a_missed_and_an_extra_lot(self):
        book, iid, pid, run = self.live_instance("fake-overnight@1", OVERNIGHT)
        book.db.execute("DELETE FROM eq_lots WHERE opened_day=?", (D3,))            # an entry the windows missed
        book.db.commit()
        book.lot(900, iid, "QQQ", D4, "open")                                       # a lot the twin never bought
        book.lot(901, iid, "SPY", "2026-10-21", "close")                            # after `through`: not counted yet
        self.night("2026-10-16")
        part = self.db.execute("SELECT * FROM fwd_part").fetchone()
        twin_entries = [lot for lot in run.result["lots"] if lot["entry_day"] <= "2026-10-16"]
        self.assertEqual(len(twin_entries), 4)
        self.assertEqual((part["instance"], part["through"], part["pid"], part["matched"], part["missed"], part["extra"]),
                         (iid, "2026-10-16", pid, 3, 1, 1))

    def test_a_registry_sha_that_differs_is_an_event_and_no_twin(self):
        book, iid, pid, run = self.live_instance("fake-overnight@1", OVERNIGHT, run_sha="another-run-sha")
        for through in (D3, D4, "2026-10-16"):
            out = self.night(through)
            self.assertEqual((out["mismatched"], out["twins"]), (1, 0))
        self.assertEqual(self.twin_rows(), [])
        found = events(self.db, "twin_sha_mismatch")
        self.assertEqual([(e["pid"], e["payload"]["instance"]) for e in found], [(pid, iid)], "once an instance")

    def test_an_instance_that_is_not_registered_is_an_event_and_no_twin(self):
        book = self.book()
        iid = book.instance("fake-unknown@2", OVERNIGHT, created=at(D1, 16, 25))
        for through in (D3, D4):
            out = self.night(through)
            self.assertEqual((out["unregistered"], out["twins"]), (1, 0))
        found = events(self.db, "twin_unregistered")
        self.assertEqual([(e["pid"], e["payload"]["instance"]) for e in found], [(None, iid)], "once an instance")

    def test_one_instances_failure_never_costs_another_its_rows(self):
        self.live_instance("fake-overnight@1", OVERNIGHT)
        register(self.db, "fake-broken@1", OVERNIGHT)
        book = Book(self.root / forward_twins.LIVE_DB)
        self.addCleanup(book.close)
        book.instance("fake-broken@1", OVERNIGHT, created=at(D1, 16, 25))
        shadow = self.shadow(D4)
        real = shadow.run_from

        def run_from(program, first_day, **kw):
            if program.key == "fake-broken@1":
                raise ValueError("fake: a held symbol has no price that session")
            return real(program, first_day, **kw)

        shadow.run_from = run_from
        out = forward_twins.finish(self.root, self.db, shadow, now=1.0)
        self.assertEqual((out["instances"], out["failed"], out["twins"]), (2, 1, 3))
        self.assertEqual(out["errors"], ["fake-broken@1:r: ValueError"])
        self.assertEqual({r["instance"] for r in self.twin_rows()}, {"fake-overnight@1:r"})

    def test_twins_false_and_the_mode_off_skip(self):
        self.live_instance("fake-overnight@1", OVERNIGHT)
        for off in ({"elane": {"forward": {"mode": "record", "twins": False}}}, {"elane": {"forward": {"mode": "off"}}},
                    None):
            out = self.night(D4, settings=off)
            self.assertIn("twins", out["skipped"])
            self.assertEqual(self.twin_rows(), [])
            self.assertEqual({out[k] for k in forward_twins.FINISH_KEYS}, {0})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_events").fetchone()[0], 0)

    def test_a_child_that_fails_the_twins_run_is_an_interruption_and_a_data_error_is_not(self):
        from league.equity.runner import RunFailed
        from league.live.decider import DeciderError

        book, iid, pid, run = self.live_instance("fake-overnight@1", OVERNIGHT)
        for error, interrupted, failed in ((RunFailed("fake: the child timed out"), 1, 0),
                                           (DeciderError("fake: the child was killed"), 1, 0),
                                           (ValueError("fake: a held symbol has no price"), 0, 1)):
            shadow = self.shadow(D4)
            shadow.run_from = mock.Mock(side_effect=error)
            out = forward_twins.finish(self.root, self.db, shadow, now=1.0)
            self.assertEqual((out["interrupted"], out["failed"], out["twins"]), (interrupted, failed, 0), error)
        found = events(self.db, "twin_interrupted")
        self.assertEqual([(e["day"], e["payload"]["instance"]) for e in found], [(D4, iid)], "once a night")
        self.assertEqual(self.night(D4)["twins"], 3, "the next try writes every session")

    def test_a_shadow_without_the_settings_attribute_reads_the_swarms(self):
        self.live_instance("fake-overnight@1", OVERNIGHT)
        shadow = self.shadow(D4)
        del shadow.settings
        with mock.patch("league.swarm.settings.load", return_value=SETTINGS) as load:
            out = forward_twins.finish(self.root, self.db, shadow, now=1.0)
        load.assert_called_once_with(self.root)
        self.assertEqual(out["twins"], 3)


class TheLiveSide(WithAStore):
    """`live_intents`: D12's live rule on the book's own `eq_intents` rows, through the one key rule."""

    def setUp(self):
        super().setUp()
        self.live = self.book()
        self.iid = self.live.instance("fake-overnight@1", OVERNIGHT, created=at(D1, 16, 25))
        self.live.lot(11, self.iid, "SPY", D2, "close", exit_day=D3, exit_at="open")
        self.live.lot(12, self.iid, "QQQ", D3, "open")

    def keys(self, needs=("SPY", "QQQ")):
        return forward_twins.live_intents(self.live.path, self.iid, needs=needs)

    def test_a_buy_in_needs_and_a_sell_of_a_lot_through_its_row(self):
        self.live.intent(self.iid, D1, "buy", at_="close", symbol="SPY")
        self.live.intent(self.iid, D2, "sell", at_="open", symbol="SPY", lid=11)
        self.live.intent(self.iid, D2, "buy", symbol="QQQ", status="missed")
        self.assertEqual(self.keys(), {D1: ["B|SPY|close"], D2: [f"S|SPY|open|{D2}", "B|QQQ|open"]})

    def test_a_rows_status_is_not_read(self):
        for status in ("planned", "sent", "filled", "refused", "missed", "canceled"):
            self.live.intent(self.iid, D1, "buy", symbol="SPY", status=status)
        self.assertEqual(self.keys(), {D1: ["B|SPY|open"] * 6})

    def test_what_the_book_records_and_the_rule_drops(self):
        self.live.intent(self.iid, D2, "buy", status="refused")                              # a malformed intent
        self.live.intent(self.iid, D2, "buy", symbol="IWM", status="refused")                # a buy outside NEEDS
        self.live.intent(self.iid, D2, "sell", status="refused")                             # a sell of an unknown lot
        self.live.intent(self.iid, D2, "cancel", status="refused")
        self.live.intent(self.iid, D2, "cancel", symbol="SPY", lid=11, status="done")        # a cancel that worked
        self.live.intent(self.iid, D2, "house_exit", symbol="SPY", lid=11)                   # the House's own exit rule
        self.assertEqual(self.keys(), {D2: []}, "a decided session with no kept row is the empty set")
        self.assertEqual(self.keys(needs=("SPY", "QQQ", "IWM")), {D2: ["B|IWM|open"]})

    def test_a_second_sell_of_the_same_lot_is_kept_too(self):
        self.live.intent(self.iid, D2, "sell", symbol="SPY", lid=11)
        self.live.intent(self.iid, D2, "sell", at_="close", symbol="SPY", lid=11, status="refused")
        self.assertEqual(self.keys(), {D2: [f"S|SPY|open|{D2}", f"S|SPY|close|{D2}"]})

    def test_a_house_exit_alone_is_no_decision_of_the_program(self):
        self.live.intent(self.iid, D3, "house_exit", symbol="QQQ", lid=12)
        self.assertEqual(self.keys(), {}, "the House's exit is not an intent: that day has no row to read")

    def test_another_instances_rows_and_a_sell_whose_lot_row_is_gone(self):
        other = self.live.instance("fake-other@1", OVERNIGHT, created=at(D1, 16, 25))
        self.live.intent(other, D1, "buy", symbol="SPY")
        self.live.intent(self.iid, D1, "sell", symbol="SPY", lid=999)                        # no such lot row
        self.assertEqual(self.keys(), {D1: []})
        self.assertEqual(forward_twins.live_intents(self.live.path, other, needs=("SPY",)), {D1: ["B|SPY|open"]})

    def test_a_book_from_before_the_share_lane(self):
        old = self.root / "old-live.sqlite"
        db = sqlite3.connect(old)
        db.execute("CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.commit()
        db.close()
        self.assertEqual(forward_twins.live_intents(old, self.iid, needs=("SPY",)), {})
        self.assertEqual(forward_twins.read_book(old), {"instances": [], "lots": {}, "intents": {}, "decision_day": None})
        self.assertIsNone(forward_twins.live_bars(old, self.iid, D1, needs={"symbols": ["SPY"], "history": 1}))

    def test_the_book_as_the_night_reads_it(self):
        self.live.intent(self.iid, D1, "buy", at_="close", symbol="SPY")
        self.live.intent(self.iid, D2, "house_exit", symbol="SPY", lid=11)
        self.live.put("eq_decision", {"day": D2, "start": D1, "shas": {}})
        book = forward_twins.read_book(self.live.path)
        self.assertEqual([i["id"] for i in book["instances"]], [self.iid])
        self.assertEqual([lot["lid"] for lot in book["lots"][self.iid]], [11, 12])
        self.assertEqual([(r["decided_day"], r["kind"]) for r in book["intents"][self.iid]], [(D1, "buy")])
        self.assertEqual(book["decision_day"], D2)

    def test_the_twins_keys_are_the_fills_its_own_run_made(self):
        # The decide loop on E2's ctx stream asks what the engine's own run was asked: every kept buy is a lot bought
        # in the next session, every kept sell a lot sold in it.
        register(self.db, "fake-reversal@1", REVERSAL)
        run = self.shadow("2026-10-30").run_from(fake_program(self.db, "fake-reversal@1"), schedule.next_session(T0))
        keys = forward_twins.shadow_intents(self.decider, run)
        bought = {(schedule.next_session(d).isoformat(), k.split("|")[1], k.split("|")[2])
                  for d, ks in keys.items() for k in ks if k.startswith("B|")}
        sold = {(schedule.next_session(d).isoformat(), k.split("|")[1], k.split("|")[3])
                for d, ks in keys.items() for k in ks if k.startswith("S|")}
        lots = run.result["lots"]
        self.assertEqual(bought, {(lot["entry_day"], lot["symbol"], lot["entry_at"]) for lot in lots})
        self.assertEqual(sold, {(lot["exit_day"], lot["symbol"], lot["entry_day"]) for lot in lots if lot["exit_day"]})
        self.assertGreater(len(lots), 3)


class NeverASilentReload(WithAStore):
    """A twin whose decides were interrupted writes no row that night, one event, and is tried again the next."""

    class Restarting(InlineDecider):
        """A decider whose child 'restarts' at its n-th decide (every instance reloaded with fresh memory)."""

        def __init__(self, at_decide: int):
            super().__init__()
            self.at_decide, self.decides = at_decide, 0

        def kind(self, kind, op, payload, **kw):
            if op == "decide":
                self.decides += 1
                if self.decides == self.at_decide:
                    self.restarts += 1
            return super().kind(kind, op, payload, **kw)

    class Reloading(InlineDecider):
        """A decider that silently drops and reloads the asked instance before its n-th decide and counts no restart."""

        def __init__(self, at_decide: int):
            super().__init__()
            self.at_decide, self.decides = at_decide, 0

        def kind(self, kind, op, payload, **kw):
            if op == "decide":
                self.decides += 1
                if self.decides == self.at_decide:
                    key = payload["jobs"][0]["key"]
                    body = dict(self.kind_loaded[(kind, key)])
                    self._ask(("kind", kind, "drop", {"key": key}), 5.0)
                    self._ask(("kind", kind, "load", body), 5.0)
            return super().kind(kind, op, payload, **kw)

    def run_of(self, code=CLOCK):
        register(self.db, "fake-clock@1", code)
        return self.shadow("2026-10-23").run_from(fake_program(self.db, "fake-clock@1"), schedule.next_session(T0))

    def test_a_restart_counted_by_the_decider_interrupts(self):
        with self.assertRaises(forward_twins.TwinInterrupted):
            forward_twins.shadow_intents(self.Restarting(4), self.run_of())

    def test_a_reload_the_decider_did_not_count_is_caught_by_the_call_count(self):
        decider = self.Reloading(4)
        with self.assertRaises(forward_twins.TwinInterrupted) as raised:
            forward_twins.shadow_intents(decider, self.run_of())
        self.assertIn("reloaded", str(raised.exception))
        self.assertEqual(decider.kind_loaded, {}, "the instance is dropped in the finally")

    def test_a_decide_that_raises_a_missing_instance_and_a_ctx_error_interrupt(self):
        run = self.run_of()

        class Failing(InlineDecider):
            def kind(self, kind, op, payload, **kw):
                raise RuntimeError("fake: the child was killed")

        class Answering(InlineDecider):
            def __init__(self, row):
                super().__init__()
                self.row = row

            def kind(self, kind, op, payload, **kw):
                return {"ok": True, "results": {payload["jobs"][0]["key"]: self.row}}

        for decider in (Failing(), Answering({"intents": [], "stats": None, "missing": True}),
                        Answering({"intents": [], "stats": {"calls": 1}, "error": "ctx: fake"}),
                        Answering({"intents": [], "stats": {}}), Answering({"intents": [], "stats": {"calls": True}}),
                        Answering(None), None):
            with self.assertRaises(forward_twins.TwinInterrupted, msg=repr(decider)):
                forward_twins.shadow_intents(decider, run)

    def test_a_program_that_does_not_load_interrupts(self):
        run = self.run_of()
        broken = dataclasses.replace(run, program=dataclasses.replace(run.program, code="def decide(ctx):\n    return []\n"))
        with self.assertRaises(forward_twins.TwinInterrupted):
            forward_twins.shadow_intents(InlineDecider(), broken)

    def test_an_uninterrupted_twin_answers_every_decision_and_drops_its_instance(self):
        decider = InlineDecider()
        run = self.run_of()
        out = forward_twins.shadow_intents(decider, run)
        self.assertEqual(sorted(out), forward_twins._sessions(T0, dt.date(2026, 10, 22)))
        self.assertEqual(decider.kind_loaded, {})
        self.assertEqual(sorted(forward_twins.shadow_bars(run)), sorted(out), "the bars hashes need no child")
        self.assertEqual([k for k in out.values() if k][0], ["B|SPY|close"])

    def test_a_disqualified_twin_answers_nothing_and_is_not_an_interruption(self):
        failing = CLOCK.replace('    STATE["n"] += 1\n', '    STATE["n"] += 1\n    if STATE["n"] > 2:\n        return 1 // 0\n')
        register(self.db, "fake-failing@1", failing)
        run = self.shadow(STORE_END).run_from(fake_program(self.db, "fake-failing@1"), schedule.next_session(T0))
        self.assertEqual(run.result["status"], "disqualified")
        out = forward_twins.shadow_intents(InlineDecider(), run)
        self.assertEqual(sorted(out), forward_twins._sessions(T0, schedule.previous_session(STORE_END)))
        self.assertEqual([keys for keys in out.values() if keys], [["B|SPY|close"], ["S|SPY|open|2026-10-13"]],
                         "its two good decides, then errors until it is disqualified, then nothing")

    def test_the_night_writes_no_row_one_event_and_tries_again_the_next(self):
        book, iid, pid, run = self.live_instance("fake-overnight@1", OVERNIGHT)
        register(self.db, "fake-clock@1", CLOCK)
        other = book.instance("fake-clock@1", CLOCK, created=at(D1, 16, 25))
        # The night's decides: the engine's "run" ops are not decides; the first twin asked is fake-clock's (ids sort).
        out = self.night(D4, decider=self.Restarting(2))
        self.assertEqual((out["interrupted"], out["failed"]), (1, 0))
        self.assertEqual({r["instance"] for r in self.twin_rows()}, {iid}, "the other instance's rows are written")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_part WHERE instance=?", (other,)).fetchone()[0], 0)
        found = events(self.db, "twin_interrupted")
        self.assertEqual([(e["pid"], e["day"], e["payload"]["instance"]) for e in found], [(pid + 1, D4, other)])
        self.assertIn("restarted", found[0]["payload"]["why"])
        out = self.night("2026-10-16")                   # the next night, an uninterrupted child: every session at once
        self.assertEqual(out["interrupted"], 0)
        self.assertEqual([r["day"] for r in self.twin_rows(other)], [D1, D2, D3, D4])
        self.assertEqual(len(events(self.db, "twin_interrupted")), 1)

    def test_two_interrupted_nights_are_two_events_one_a_night(self):
        book, iid, pid, run = self.live_instance("fake-overnight@1", OVERNIGHT)
        for through in (D4, D4, "2026-10-16"):
            self.assertEqual(self.night(through, decider=self.Restarting(1))["interrupted"], 1)
        self.assertEqual([e["day"] for e in events(self.db, "twin_interrupted")], [D4, "2026-10-16"])
        self.assertEqual(self.twin_rows(), [])


class TheBarsOfADecision(WithAStore):
    """THE BARS HASH: the twin's and the live decision's as-of bars, and a disagreement's cause."""

    def setUp(self):
        super().setUp()
        self.wide = self.shadow(STORE_END).store.bars(["QQQ", "SPY"], "forward", history=40, end=dt.date(2026, 10, 30))

    def test_the_live_hash_is_the_twins_when_both_read_the_same_bars(self):
        book, iid, pid, run = self.live_instance("fake-reversal@1", REVERSAL)
        mine = forward_twins.shadow_bars(run)
        for day in (D1, D3, "2026-10-22"):
            book.bars(self.wide, day, ["QQQ", "SPY"], history=2)
            book.decided(iid, day)
            found = forward_twins.live_bars(book.path, iid, day, needs=run.program.needs)
            self.assertEqual(found, mine[day], day)
            self.assertRegex(found, r"^[0-9a-f]{16}$")

    def test_an_adjusted_price_a_cent_away_moves_the_live_hash(self):
        book, iid, pid, run = self.live_instance("fake-reversal@1", REVERSAL)
        book.bars(self.wide, D3, ["QQQ", "SPY"], history=2, bump=("QQQ", D2, 0.01))
        book.decided(iid, D3)
        found = forward_twins.live_bars(book.path, iid, D3, needs=run.program.needs)
        self.assertIsNotNone(found)
        self.assertNotEqual(found, forward_twins.shadow_bars(run)[D3])

    def test_the_hash_is_not_known_once_the_book_no_longer_holds_that_decisions_bars(self):
        book, iid, pid, run = self.live_instance("fake-reversal@1", REVERSAL)
        needs = run.program.needs
        book.bars(self.wide, D3, ["QQQ", "SPY"], history=2)
        self.assertIsNone(forward_twins.live_bars(book.path, iid, D3, needs=needs), "the instance did not decide that day")
        book.decided(iid, D3)
        self.assertIsNotNone(forward_twins.live_bars(book.path, iid, D3, needs=needs))
        self.assertIsNone(forward_twins.live_bars(book.path, iid, D2, needs=needs), "the decision names another day")
        self.assertIsNone(forward_twins.live_bars(book.path, "fake-other@1:r", D3, needs=needs))
        book.bars(self.wide, D4, ["QQQ", "SPY"], history=2)          # the next session's decide fetched the series again
        self.assertIsNone(forward_twins.live_bars(book.path, iid, D3, needs=needs))
        book.decided(iid, D4)
        book.db.execute("UPDATE eq_bars SET sha='another fetch' WHERE day=? AND symbol='QQQ' AND adjustment='all'", (D3,))
        book.db.commit()
        self.assertIsNone(forward_twins.live_bars(book.path, iid, D4, needs=needs), "a row another fetch wrote")
        self.assertIsNone(forward_twins.live_bars(self.root / "no-book.sqlite", iid, D4, needs=needs))
        self.assertIsNone(forward_twins.live_bars(book.path, iid, D4, needs={"symbols": ["IWM"], "history": 2}),
                          "a symbol the decision did not fetch")

    def nights(self, book, iid, days, *, bump=None, bumped=()):
        """Night after night: the book's decide of that day (its bars as fetched), then the forward night."""
        outs = []
        for day in days:
            book.bars(self.wide, day, ["QQQ", "SPY"], history=2, bump=bump if day in bumped else None)
            book.decided(iid, day)
            outs.append(forward_twins.finish(self.root, self.db, self.shadow(day), now=at(day, 18, 35)))
        return outs

    def test_the_night_of_a_decision_keeps_its_hash_and_the_row_reads_it_a_night_later(self):
        book, iid, pid, run = self.live_instance("fake-reversal@1", REVERSAL)
        days = forward_twins._sessions(T0, dt.date(2026, 10, 20))
        outs = self.nights(book, iid, days)
        self.assertEqual([o["live_bars"] for o in outs], [1] * len(days), "one a night")
        kept = events(self.db, "live_bars")
        self.assertEqual([(e["pid"], e["day"], e["payload"]["instance"]) for e in kept], [(pid, d, iid) for d in days])
        rows = self.twin_rows()
        self.assertEqual([r["day"] for r in rows], days[:-1])
        self.assertEqual({r["agree"] for r in rows}, {1})
        self.assertTrue(all(r["live_bars"] == r["shadow_bars"] for r in rows), "the same bars on both sides")
        self.assertEqual({r["cause"] for r in rows}, {None}, "a cause is a disagreement's alone")
        again = forward_twins.finish(self.root, self.db, self.shadow(days[-1]), now=1.0)
        self.assertEqual(again["live_bars"], 0, "once an (instance, day)")

    def test_a_disagreement_on_other_bars_is_counted_with_the_cause_bars(self):
        # The live book decided D3 on bars a cent away from the store's, and its decision differed: one counted row.
        book, iid, pid, run = self.live_instance("fake-reversal@1", REVERSAL)
        book.db.execute("DELETE FROM eq_intents WHERE decided_day=?", (D3,))
        book.db.commit()
        self.assertEqual(json.loads(json.dumps(forward_twins.shadow_intents(self.decider, run)[D3])), ["S|QQQ|open|2026-10-13"])
        outs = self.nights(book, iid, [D1, D2, D3, D4, "2026-10-16"], bump=("QQQ", D2, 0.01), bumped={D3})
        rows = {r["day"]: r for r in self.twin_rows()}
        self.assertEqual((rows[D3]["agree"], rows[D3]["cause"]), (0, "bars"))
        self.assertNotEqual(rows[D3]["live_bars"], rows[D3]["shadow_bars"])
        self.assertEqual(sum(o["disagreed"] for o in outs), 1)
        self.assertEqual(sum(o["failed"] + o["interrupted"] for o in outs), 0, "never an error")
        self.assertEqual([rows[d]["agree"] for d in (D1, D2, D4)], [1, 1, 1])

    def test_a_disagreement_on_the_same_bars_is_the_programs(self):
        book, iid, pid, run = self.live_instance("fake-reversal@1", REVERSAL)
        book.db.execute("DELETE FROM eq_intents WHERE decided_day=?", (D3,))
        book.db.commit()
        self.nights(book, iid, [D1, D2, D3, D4])
        row = {r["day"]: r for r in self.twin_rows()}[D3]
        self.assertEqual((row["agree"], row["cause"]), (0, "program"))
        self.assertEqual(row["live_bars"], row["shadow_bars"])

    def test_sessions_that_agree_on_other_bars_are_rows_with_both_hashes_and_no_cause(self):
        book, iid, pid, run = self.live_instance("fake-reversal@1", REVERSAL)
        self.nights(book, iid, [D1, D2, D3, D4], bump=("SPY", D1, 0.01), bumped={D2})
        row = {r["day"]: r for r in self.twin_rows()}[D2]
        self.assertEqual((row["agree"], row["cause"]), (1, None))
        self.assertNotEqual(row["live_bars"], row["shadow_bars"], "the rounding moved the bars and not the intent")

    def test_a_slice_one_session_short_makes_the_first_decision_read_other_bars(self):
        # E1's Gym gives a run's FIRST decision the slice's history sessions and nothing before them: with a slice of
        # NEEDS' history (not history + 1) the twin's first ctx is one row short of the live one. The hash says so.
        book, iid, pid, run = self.live_instance("fake-reversal@1", REVERSAL)
        short = self.shadow("2026-10-30", lookback=lambda needs: max(int(needs["history"]), 1))
        thin = short.run_from(fake_program(self.db, "fake-reversal@1"), schedule.next_session(T0))
        full, cut = forward_twins.shadow_bars(run), forward_twins.shadow_bars(thin)
        self.assertNotEqual(cut[D1], full[D1])
        self.assertEqual({d: cut[d] for d in cut if d > D1}, {d: full[d] for d in full if d > D1})
        book.bars(self.wide, D1, ["QQQ", "SPY"], history=2)
        book.decided(iid, D1)
        self.assertEqual(forward_twins.live_bars(book.path, iid, D1, needs=run.program.needs), full[D1])


class WhatCannotBeRead(WithAStore):
    """UNREADABLE sessions: a split during a hold, and the sessions from an instance's retirement on."""

    SPLITS = {"QQQ": [(dt.date(2026, 10, 20), 2.0)]}

    def test_the_split_sessions_of_a_run(self):
        register(self.db, "fake-hold@1", HOLD)
        run = self.shadow("2026-10-30").run_from(fake_program(self.db, "fake-hold@1"), schedule.next_session(T0))
        self.assertEqual([(a["kind"], a["day"]) for a in run.result["actions"]], [("split", "2026-10-20")])
        lot = run.result["lots"][0]
        self.assertEqual((lot["entry_day"], lot["exit_day"]), (D2, None))
        self.assertEqual(sorted(forward_twins.split_sessions(run)),
                         forward_twins._sessions(dt.date(2026, 10, 13), dt.date(2026, 10, 19)),
                         "the decision days the lot is held at, before the split's day")

    def test_a_lot_sold_before_the_split_or_bought_after_it_is_readable(self):
        days = np.array([ordinal(dt.date.fromisoformat(d)) for d in forward_twins._sessions(T0, dt.date(2026, 10, 23))],
                        dtype=np.int32)
        bars = type("B", (), {"days": days})()
        lots = [{"lid": 1, "symbol": "QQQ", "entry_day": D2, "exit_day": "2026-10-19"},          # sold the day before
                {"lid": 2, "symbol": "QQQ", "entry_day": "2026-10-20", "exit_day": None},          # bought on the split day
                {"lid": 3, "symbol": "SPY", "entry_day": D2, "exit_day": None}]                    # another symbol
        result = {"lots": lots, "actions": [{"symbol": "QQQ", "day": "2026-10-20", "kind": "split", "factor": "2:1"},
                                            {"symbol": "SPY", "day": "2026-10-16", "kind": "dividend", "per_share": 1.0}]}
        run = forward_db.ShadowRun(None, result, bars, None)
        self.assertEqual(forward_twins.split_sessions(run), set())
        lots.append({"lid": 4, "symbol": "QQQ", "entry_day": D4, "exit_day": "2026-10-20"})         # sold ON the split day
        self.assertEqual(sorted(forward_twins.split_sessions(run)), [D4, "2026-10-16", "2026-10-19"])

    def test_a_split_during_a_hold_gives_null_rows(self):
        book, iid, pid, run = self.live_instance("fake-hold@1", HOLD)
        out = forward_twins.finish(self.root, self.db, self.shadow("2026-10-23"), now=1.0)
        rows = {r["day"]: r for r in self.twin_rows()}
        split = forward_twins._sessions(dt.date(2026, 10, 13), dt.date(2026, 10, 19))
        self.assertEqual({d: (rows[d]["agree"], rows[d]["why"], rows[d]["cause"]) for d in split},
                         {d: (None, "split", None) for d in split})
        self.assertEqual({rows[d]["agree"] for d in rows if d not in split}, {1})
        self.assertEqual((out["twins"], out["unreadable"], out["disagreed"]), (9, 5, 0))
        self.assertIn("split", forward_twins.UNREADABLE)

    def retire(self, key="fake-overnight@1", *, retired=("2026-10-20", 16, 22)):
        """An instance retired in the decide step of Oct 20: it decided through Oct 19, the House sold its last lot at
        Oct 21's open; its twin goes on trading."""
        book, iid, pid, run = self.live_instance(key, OVERNIGHT, retired=at(*retired), mirror_until="2026-10-19")
        book.db.execute("DELETE FROM eq_lots WHERE opened_day>?", ("2026-10-20",))
        book.db.commit()
        return book, iid, pid, run

    def test_the_sessions_from_a_retirement_on_are_unreadable_never_a_disagreement(self):
        book, iid, pid, run = self.retire()
        self.assertEqual(book.db.execute("SELECT MAX(exit_day), MIN(status) FROM eq_lots").fetchone(),
                         ("2026-10-21", "closed"))
        out = forward_twins.finish(self.root, self.db, self.shadow("2026-10-23"), now=1.0)
        rows = self.twin_rows()
        self.assertEqual([r["day"] for r in rows], forward_twins._sessions(T0, dt.date(2026, 10, 20)),
                         "through the session before its last lot closed, and no further")
        self.assertEqual({r["agree"] for r in rows[:-1]}, {1})
        last = rows[-1]
        self.assertEqual((last["day"], last["agree"], last["why"], last["cause"]), ("2026-10-20", None, "retired", None))
        self.assertEqual(last["live_keys"], "[]", "the book asked the program nothing that session")
        self.assertNotEqual(last["shadow_keys"], "[]", "its twin, which nobody retired, went on")
        self.assertEqual((out["twins"], out["unreadable"], out["disagreed"]), (7, 1, 0))
        self.assertIn("retired", forward_twins.UNREADABLE)

    def test_a_retired_instance_whose_rows_are_written_has_no_twin_run_again(self):
        self.retire()
        first = self.shadow("2026-10-23")
        forward_twins.finish(self.root, self.db, first, now=1.0)
        self.assertEqual(len(first.runs), 1)
        for through in ("2026-10-26", "2026-10-30"):
            later = self.shadow(through)
            out = forward_twins.finish(self.root, self.db, later, now=2.0)
            self.assertEqual((later.runs, out["twins"]), ([], 0), "nothing it will ever need is missing")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_twins").fetchone()[0], 7)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_part").fetchone()[0], 1)

    def test_a_retired_instance_still_holding_a_lot_waits_for_its_exit(self):
        book, iid, pid, run = self.retire()
        book.db.execute("UPDATE eq_lots SET status='open', exit_day=NULL WHERE exit_day='2026-10-21'")
        book.db.commit()
        forward_twins.finish(self.root, self.db, self.shadow("2026-10-23"), now=1.0)
        rows = self.twin_rows()
        self.assertEqual(rows[-1]["day"], "2026-10-22", "an open lot's exit day is not known: every session so far")
        self.assertEqual([r["why"] for r in rows[-3:]], ["retired"] * 3)
        later = self.shadow("2026-10-26")
        forward_twins.finish(self.root, self.db, later, now=2.0)
        self.assertEqual(len(later.runs), 1, "it is still run while a lot is open")

    def test_the_participation_of_a_retired_instance_stops_at_its_retirement(self):
        book, iid, pid, run = self.retire()
        forward_twins.finish(self.root, self.db, self.shadow("2026-10-23"), now=1.0)
        part = self.db.execute("SELECT matched, missed, extra FROM fwd_part").fetchone()
        entries = [lot for lot in run.result["lots"] if lot["entry_day"] <= "2026-10-20"]
        self.assertEqual(tuple(part), (len(entries), 0, 0), "the twin's later lots are not the live instance's misses")

    def test_an_instance_retired_before_it_decided_writes_nothing(self):
        register(self.db, "fake-overnight@1", OVERNIGHT)
        book = self.book()
        book.instance("fake-overnight@1", OVERNIGHT, created=at(D1, 16, 25), retired=at(D1, 16, 26))
        shadow = self.shadow("2026-10-23")
        out = forward_twins.finish(self.root, self.db, shadow, now=1.0)
        self.assertEqual((out["twins"], shadow.runs), (0, []))


class TheSeals(WithAStore):
    def test_no_event_or_receipt_of_the_twins_holds_a_price_or_a_return(self):
        book, iid, pid, run = self.live_instance("fake-clock@1", CLOCK, reload_at=4)
        out = forward_twins.finish(self.root, self.db, self.shadow("2026-10-23", decider=NeverASilentReload.Restarting(99)),
                                   now=1.0)
        forward_twins.on_run(self.db, golden_run(), now=1.0, settings=SETTINGS)
        text = json.dumps(out) + json.dumps([dict(r) for r in self.db.execute("SELECT kind, payload FROM fwd_events")])
        self.assertNotRegex(text, r"\d\.\d", "ids, counts and dates only")
        self.assertTrue(all(isinstance(out[k], int) for k in forward_twins.FINISH_KEYS))

    def test_the_module_writes_only_its_own_tables_and_events(self):
        mine = {t for t, writer in forward_db.WRITERS.items() if writer == "D"}
        self.assertEqual(mine, {"fwd_ll", "fwd_fillgap", "fwd_lotgap", "fwd_twins", "fwd_part"})
        source = Path(forward_twins.__file__).read_text()
        for table in forward_db.TABLES:
            written = f"INTO {table}(" in source
            self.assertEqual(written, table in mine, table)
        self.assertNotIn("UPDATE ", source)
        self.assertNotIn("DELETE ", source)
        kinds = {k for k, package in forward_db.EVENT_KINDS.items() if package == "D"}
        self.assertEqual(kinds, {"no_minute", "twin_unregistered", "twin_sha_mismatch", "twin_interrupted", "live_bars"})
        for kind in kinds:
            self.assertIn(f'"{kind}"', source, kind)
            self.assertIn(kind, forward_db.ONCE_KINDS)

    def test_the_book_and_the_swarm_store_are_opened_read_only(self):
        book, iid, pid, run = self.live_instance("fake-overnight@1", OVERNIGHT)
        book.close()
        before = (self.root / forward_twins.LIVE_DB).read_bytes()
        with guard.readonly():                           # every writable sqlite3.connect in the process is refused
            out = forward_twins.finish(self.root, self.db, self.shadow(D4), now=1.0)
        self.assertEqual((out["twins"], out["failed"]), (3, 0))
        self.assertEqual((self.root / forward_twins.LIVE_DB).read_bytes(), before)

    def test_every_statistic_is_summed_exactly(self):
        # Python 3.11's built-in sum is not exact; the live-like series adds its terms with math.fsum.
        run = golden_run()
        lots = [{"lid": i, "symbol": "SPY", "weight": 0.1, "qty": 1.0, "entry_day": D1, "entry_at": "open",
                 "exit_day": None, "exit_at": None, "exit_px": None} for i in range(10)]
        run = dataclasses.replace(run, result={**run.result, "lots": lots})
        out = forward_twins.livelike_series(run, lambda d, s, a: 1.0)
        self.assertEqual(out[D1], (0.001 * 1000.0 + math.fsum([-0.1 * 1000.0 * 1.0 / 1e4] * 10)) / 1000.0)


if __name__ == "__main__":
    unittest.main()
