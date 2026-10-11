"""Release E3, T11: THE WHOLE NIGHT. The real modules together, on one House state, from a Train scoring to a Done
checkpoint (league/ops/E3_INTERFACES.md; the integrator's test, the one E3 test that fakes no E3 module):

  E2's own `EquityResearcher.score` on E1's own runner (`Isolated` on an `InlineDecider`) scores two families born
  with a hidden year  ->  the `swarm.elane` "scored" event and the memory tables  ->  the `forward_register` job writes
  each a hash-chained registry row dated by its event, and the controls  ->  the store grows a session a night  ->  the
  `forward_shadow` job recomputes every program and control on its own forward days in ITS OWN decider instance  ->
  the `forward_report` job's meters and report, the funnel's counts  ->  the live book's closed lots get E1's twin
  record, their fill-gap parts and their intents' twin rows  ->  the Done meter's checkpoint carries A14 as
  `forward_twins.a14_reading` reads it  ->  THE SEALS HOLD: what the three equity generators read is byte for byte
  what they read before any of it was recorded, and no E3 job wrote a row of the swarm store.

`WithEveryModeOff`: the rollback switches (swarm.json `elane.forward.mode`, `elane.memory.mode`, `elane.contam.mode`
"off"). Nothing of E3 runs or spends: every job is a skipped receipt that touches no gateway, no model route and no
decider child and writes no store; a birth gets no hidden year and a scoring makes no hidden run and no memory row;
the reports carry no forward alarm. What has no switch is said too: the release receipts (the stall job's read-back
of what a deploy declared) still list, in their own store, and spend nothing; A14 is then unmeasured and does not hold.

WHAT IS SYNTHETIC HERE (never a fake of an E3 module): the market (`league.equity.synth`, invented prices), the model
routes (a scripted router: no test calls a model), the venue's minute bars (`Venue`, the gateway's bars route answered
from the synthetic store) and the live book (E1's own schema, written row by row as an instance that decided and
filled exactly as E1's engine does on the same bars: league/tests/test_forward_twins.py `Book`, `record`,
`decide_loop`). Every family, program, price and number is invented; nothing here is a market result."""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import shutil
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity import config, engine, schedule, screen, synth
from league.equity.runner import Isolated
from league.equity.store import STORE_DIR, EquityStore, from_ordinal, mint_equity_gate_capability
from league.live.decider import InlineDecider
from league.ops import dlane_report, fill_minutes, forward_audit, forward_db, forward_register, forward_report
from league.ops import forward_shadow, forward_stats, forward_twins, funnel, registry, release_receipts, twins
from league.ops.context import Context, read_json
from league.ops.store import OpsStore
from league.swarm import elane_folds, elane_train
from league.swarm import settings as swarm_settings
from league.swarm.architect import Architect
from league.swarm.elane_train import EquityResearcher
from league.swarm.store import SwarmStore
from league.tests import elane_e2_fakes as fx
from league.tests import elane_e3_fakes as e3
from league.tests import test_forward_twins as book_fx
from league.tests.test_elane_memory_seal import reviewing_router, views

SYMBOLS = ("SPY", "QQQ", "IWM", "DIA")
#: The invented market of league/tests/test_elane_memory_seal.py: it pays the overnight hold every year, so the
#: fixture's program meets the whole Train bar.
MARKET = {"seed": 5, "drift": 0.8, "vol": 0.04}
#: The nights the House runs (the first is the day the two versions are scored).
NIGHTS = 22
#: The venue's send-minute bars against the official price, in bp: the open's minute above it, the close's below.
MINUTE_BP = {"open": 4.0, "close": -2.0}
#: The two programs: `e3.CARRIES` on SPY (the BETA lane) and the same rule on QQQ (the EQUITY lane), each a lot held
#: over one night; their families' hidden years.
PROGRAMS = {"carries": (e3.CARRIES, "beta", "overnight", ("SPY",), 2018),
            "carries-q": (e3.CARRIES.replace('"SPY"', '"QQQ"'), "equity", "reversal", ("QQQ",), 2023)}
HISTORY = e3.CARRIES_HISTORY
#: The live lots' ids, by registry key (the twin run's lot ids above these).
LID_BASE = {"carries@1": 100, "carries-q@1": 500}
#: What the House's swarm.json holds: the lanes on, a small control group (the policy ships 50), no probe (no test
#: calls a model; `WithEveryModeOff` and league/tests/test_contam_probe.py hold the probe).
SETTINGS = {"elane": {"mode": "gate", "universe": list(SYMBOLS), "structures": ["etf"], "birth_share": 0.25,
                      "e2": {"train_budget": 3, "train_per_round": 5},
                      "forward": {"mode": "record", "controls_per_group": 5}, "memory": {"mode": "record"},
                      "contam": {"mode": "off"}},
            "dlane": {"mode": "gate"}}
OFF = {"elane": {"mode": "gate", "universe": list(SYMBOLS), "structures": ["etf"], "birth_share": 0.25,
                 "forward": {"mode": "off"}, "memory": {"mode": "off"}, "contam": {"mode": "off"}},
       "dlane": {"mode": "gate"}}
#: The forward store's tables an E3 job writes.
FORWARD_TABLES = ("fwd_registry", "fwd_tags", "fwd_days", "fwd_ll", "fwd_checks", "fwd_events", "fwd_runs", "fwd_cey",
                  "fwd_meter", "fwd_groups", "fwd_fillgap", "fwd_lotgap", "fwd_twins", "fwd_part")
#: Words only E3's own stores and reports hold: none may reach a generator.
E3_WORDS = ("fwd_", "forward.sqlite", "forward-report", "mem_contrib", "mem_series", "hidden_year", "contamination",
            "release-receipts", "equity-fill-minutes")


def at(day: dt.date | str, hour: int, minute: int = 0) -> float:
    """The epoch of a New York wall-clock time."""
    day = day if isinstance(day, dt.date) else dt.date.fromisoformat(day)
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=schedule.NY).timestamp()


def schedule_iso(epoch: float) -> str:
    """An epoch as the ops jobs write a time (`league.ops.schedule.iso`)."""
    from league.ops import schedule as ops_schedule

    return ops_schedule.iso(epoch)


def forward_sessions(n: int) -> list[dt.date]:
    """The first `n` forward days (D1: from `forward_db.t0()`)."""
    days = [forward_db.t0()]
    while len(days) < n:
        days.append(schedule.next_session(days[-1]))
    return days


class Clock:
    def __init__(self, t: float):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t


class Venue:
    """A SYNTHETIC VENUE for the minutes job (the gateway's bars route; no gateway is contacted): one 1Min bar a minute
    of the asked window for every asked symbol the synthetic store holds, each price the store's official open (the
    open's window) or close (the close's) moved by `MINUTE_BP`."""

    def __init__(self, store_root: Path):
        self.store = EquityStore(store_root, gate=mint_equity_gate_capability(store_root, "t11-venue"))
        self.held = set(self.store.symbols())
        self.calls: list[dict] = []

    def official(self, symbol: str, day: dt.date, at_: str) -> float:
        bars = self.store.bars([symbol], "forward", history=0, start=day, end=day)
        return float(engine.official(bars, symbol, int(bars.first), at_))

    def get(self, path: str, params: dict) -> dict:
        self.calls.append({"path": path, **params})
        start = dt.datetime.fromisoformat(params["start"].replace("Z", "+00:00"))
        end = dt.datetime.fromisoformat(params["end"].replace("Z", "+00:00"))
        day = start.astimezone(schedule.NY).date()
        at_ = "open" if params["start"] == fill_minutes.windows(day)[0][0] else "close"
        bars = {}
        for symbol in (s for s in params["symbols"].split(",") if s in self.held):
            px = round(self.official(symbol, day, at_) * (1.0 + MINUTE_BP[at_] / 1e4), 6)
            rows, t = [], start
            while t <= end:
                rows.append({"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": px, "h": px, "l": px, "c": px, "v": 100,
                             "vw": px, "n": 5})
                t += dt.timedelta(minutes=1)
            bars[symbol] = rows
        return {"bars": bars, "next_page_token": None}


class Untouchable:
    """A gateway, a Sail client or a router that nothing may touch: any use is the test's failure."""

    def __init__(self, name: str):
        object.__setattr__(self, "_name", name)

    def __getattr__(self, item: str):
        raise AssertionError(f"{object.__getattribute__(self, '_name')} was touched ({item})")


def write_market(root: Path, *, end: dt.date, as_of: dt.date | None = None) -> Path:
    """The invented market's gated store under the state root, fetched through `as_of` (written whole, as the daily
    store job writes it)."""
    path = root / STORE_DIR
    if path.exists():
        shutil.rmtree(path)
    return synth.synthetic_store(path, symbols=SYMBOLS, end=end, gate=True, as_of=as_of, **MARKET)


def research_every_day(store: SwarmStore, root: Path, clock: Clock, first: dt.date, last: dt.date) -> None:
    """Research ran every UTC day from `first` to `last` (the Done rule's item 7, as league/tests/test_dlane_report.py
    `steady` writes it): a birth, a Gym run and a Validation a day, the day's budget and stall receipts."""
    store.add_family({"id": "busy", "mechanism": "a mechanism sentence long enough for the store",
                      "structure": "long_single", "roots": ["SPY"]}, origin="architect")
    ops = OpsStore(root)
    keep, day = clock.t, first
    try:
        while day <= last:
            clock.t = dt.datetime(day.year, day.month, day.day, 12, tzinfo=dt.timezone.utc).timestamp()
            store.event("swarm.born", "busy", {"lane": "alpha"})
            for window in ("train", "validation"):
                store.add_run("busy", 1, {"run_id": f"{day}-{window}", "status": "ok", "trials": 1}, window=window,
                              stress=1.0, purpose=window, prune=False)
            ops.record("budget", f"{day}T00:30:00Z", "ok", f"{day}T00:31:00Z",
                       summary={"meters": {"sail": {"limited_by": "ceiling"}, "claude": {"limited_by": "ceiling"}}})
            ops.record("stall", f"{day}T00:20:00Z", "ok", f"{day}T00:20:30Z", summary={"checks": {}})
            day += dt.timedelta(days=1)
    finally:
        clock.t = keep
        ops.close()


def swarm_rows(store: SwarmStore) -> dict[str, list[dict]]:
    """Every row of the swarm store but E1's own twin records (the kv `equity_twins` the `equity_twins` job keeps)."""
    out = e3.dump(store)
    for name, rows in out.items():
        out[name] = [row for row in rows if row.get("key") != twins.EQUITY_TWINS_KEY]
    return out


def dlane(root: Path, settings: dict, now: float, **kw) -> dict:
    """The dlane report as its job writes it at `now`. The forward report's section is read against the wall clock
    (`forward_report.read_section` takes no `now`), so the wall clock is `now` here: on the House the two are one."""
    with mock.patch.object(forward_report.time, "time", lambda: now):
        return dlane_report.report(root, settings=settings, now=now, **kw)


def forward_counts(db: sqlite3.Connection) -> dict[str, int]:
    return {table: int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in FORWARD_TABLES}


class World:
    """ONE HOUSE, built once: the scoring, the registry, `NIGHTS` evenings and mornings, then the Done meter's report.

    `fwd`: the forward days; the versions are scored on `fwd[1]` at 10:00 New York time, so each program first
    decides at that day's close and its first forward day is `fwd[2]`. The live book holds one instance a program,
    created inside the decide step of `fwd[1]`. ONE DISAGREEMENT, AS DATA: on `self.odd` the SPY instance's live
    decision was made on bars a cent away from the store's (the vendor's rounding of another fetch) and recorded no
    intent."""

    def __init__(self, base: Path):
        self.base = base
        self.root = base / "state"
        self.release = base / "release"
        self.root.mkdir()
        self.release.mkdir()
        self.fwd = forward_sessions(NIGHTS + 4)
        self.scored_at = at(self.fwd[1], 10)
        self.clock = Clock(self.scored_at)
        self.alerts: list[tuple[str, str, str]] = []
        self.receipts: dict[str, dict[str, dict]] = {}
        self.children: list[InlineDecider] = []
        self.odd = self.fwd[6].isoformat()
        (self.root / "swarm.json").write_text(json.dumps(SETTINGS))
        self.settings = swarm_settings.load(self.root, config={})
        # The whole invented market, apart (what the venue and the live book's fills come from), and the House's own
        # store as it stood the morning the versions were scored.
        self.whole = synth.synthetic_store(base / "whole" / STORE_DIR, symbols=SYMBOLS, end=self.fwd[-1], gate=True,
                                           as_of=self.fwd[NIGHTS], **MARKET)
        self.venue = Venue(self.whole)
        write_market(self.root, end=self.fwd[-1], as_of=self.fwd[0])
        self._swarm()
        self.before = self.generator_views()
        self.rows_before = swarm_rows(self.store)
        self.registered = self.job("forward_register", forward_register, at(self.fwd[1], 10, 25))
        self._book()
        for i in range(1, NIGHTS + 1):
            self._evening(self.fwd[i])
            self._morning(self.fwd[i])
        self.now = at(schedule.next_session(self.fwd[NIGHTS]), 9, 10)
        self.clock.t = self.now
        self.report = dlane(self.root, self.settings, self.now)
        self.after = self.generator_views()
        self.rows_after = swarm_rows(self.store)

    def close(self) -> None:
        self.store.close()
        self.book.close()

    # ----------------------------------------------------------------------------------------------------- the swarm
    def _swarm(self) -> None:
        """The swarm's side, whole, before any E3 job: research every day, two families born with a hidden year, each
        v1 scored by E2's own researcher on E1's own runner, both seated at Probe."""
        self.store = SwarmStore(self.root, clock=self.clock)
        research_every_day(self.store, self.root, self.clock, dt.date(2026, 9, 30), self.fwd[-1])
        for fid, (code, lane, agenda, symbols, hidden) in PROGRAMS.items():
            e3.hidden_family(self.store, fid, hidden, lane=lane, agenda=agenda, symbols=symbols, code=code,
                             mechanism=f"Invented {agenda} idea {fid}: holders are paid for one night's index risk.")
        self.runner = Isolated(InlineDecider(), self.root / STORE_DIR)
        researcher = EquityResearcher(self.store, reviewing_router(), self.settings, runner=self.runner,
                                      clock=self.clock)
        for fid in PROGRAMS:
            researcher.score(self.store.family(fid), self.store.version(fid, 1))
            self.store.set_band(fid, "probe", reason="fixture")

    def generator_views(self) -> dict:
        """What the architect, each family's researcher and the route chooser read (league/tests/
        test_elane_memory_seal.py `views`), at the instant the versions were scored."""
        keep, self.clock.t = self.clock.t, self.scored_at
        try:
            return views(self.store, self.clock, self.settings)
        finally:
            self.clock.t = keep

    # ------------------------------------------------------------------------------------------------------ the jobs
    def job(self, name: str, module, t: float, **kw) -> dict:
        """One run of an E3 job as the ops runner starts it; its alerts are kept."""
        self.clock.t = t
        ctx = Context(name, root=self.root, due_at=t, base=self.base, release=self.release, config={}, clock=self.clock,
                      sail=Untouchable("the Sail client"), **{"gateway": Untouchable("the gateway"), **kw})
        receipt = module.run(ctx)
        self.alerts.extend((name, a["level"], a["text"]) for a in ctx.alerts)
        return receipt

    def own_child(self, root: Path) -> InlineDecider:
        """What the shadow job starts for itself (`forward_shadow._decider`; an `InlineDecider` in tests only)."""
        self.children.append(InlineDecider())
        return self.children[-1]

    # ------------------------------------------------------------------------------------------------- the live book
    def _book(self) -> None:
        """One live instance a registered program, created inside the decide step of `fwd[1]`, that decided and filled
        exactly as E1's engine does on the same bars: its lots (at the engine's own prices, quantities and fees) and
        the intents of every decision, from the program's run on the whole market through the REAL shadow."""
        self.book = book_fx.Book(self.root / "live.sqlite")
        self.instances: dict[str, str] = {}
        db = forward_db.open_db(self.root)
        try:
            probe = forward_shadow.Shadow(self.base / "whole", db, decider=InlineDecider(), settings=self.settings,
                                          clock=lambda: at(self.fwd[NIGHTS], 18, 35))
            for key, base in LID_BASE.items():
                program = forward_db.program(db, key)
                iid = self.book.instance(key, program.code, created=at(self.fwd[1], 16, 25), run_sha=program.run_sha)
                run = probe.run_from(program, self.fwd[2])
                lots = {int(lot["lid"]): lot for lot in run.result["lots"]}
                for lid, lot in lots.items():
                    self.book.lot(base + lid, iid, lot["symbol"], lot["entry_day"], lot["entry_at"],
                                  exit_day=lot["exit_day"], exit_at=lot["exit_at"], **self._money(lot))
                for day, intents, held in book_fx.decide_loop(InlineDecider(), run):
                    book_fx.record(self.book, iid, day, intents, held, set(program.needs["symbols"]), lots, base=base)
                self.instances[key] = iid
            self.wide = probe.store.bars(["QQQ", "SPY"], "forward", history=40, end=self.fwd[NIGHTS])
        finally:
            db.close()
        self.book.db.execute("DELETE FROM eq_intents WHERE instance=? AND decided_day=?",
                             (self.instances["carries@1"], self.odd))
        self.book.db.commit()

    @staticmethod
    def _money(lot: dict) -> dict:
        """A closed engine lot's money as the book keeps it (Decimal strings): the same quantity, prices and fees, its
        net cash, and the venue's fees marked posted."""
        if not lot.get("exit_day"):
            return {}
        qty, entry, exit_ = (Decimal(str(lot[k])) for k in ("qty", "entry_px", "exit_px"))
        fees, div = Decimal(str(lot.get("fees") or 0)), Decimal(str(lot.get("div") or 0))
        notional = (qty * entry).quantize(Decimal("0.000001"))
        cash = (qty * exit_ - notional - fees + div).quantize(Decimal("0.000001"))
        return {"qty": str(qty), "opened_qty": str(qty), "entry_px": str(entry), "entry_notional": str(notional),
                "exit_px": str(exit_), "fees": str(fees), "div": str(div), "cash": str(cash), "probe": 1,
                "info": json.dumps({"fee_basis": "broker"})}

    # ----------------------------------------------------------------------------------------------------- one night
    def _evening(self, night: dt.date) -> None:
        iso = night.isoformat()
        write_market(self.root, end=self.fwd[-1], as_of=night)                       # the daily store, a session more
        bump = ("SPY", schedule.previous_session(night).isoformat(), 0.01) if iso == self.odd else None
        self.book.bars(self.wide, iso, ["QQQ", "SPY"], history=HISTORY, bump=bump)    # the live decide, 16:20
        for iid in self.instances.values():
            self.book.decided(iid, iso)
        out = self.receipts.setdefault(iso, {})
        out["fill_minutes"] = self.job("fill_minutes", fill_minutes, at(night, 16, 45), gateway=self.venue)
        out["forward_register"] = self.job("forward_register", forward_register, at(night, 17, 25))
        with mock.patch.object(forward_shadow, "_decider", self.own_child):
            out["forward_shadow"] = self.job("forward_shadow", forward_shadow, at(night, 18, 35))
        out["forward_report"] = self.job("forward_report", forward_report, at(night, 18, 50))

    def _morning(self, night: dt.date) -> None:
        """The next session's morning: the book's audit found every bar as it was, E1's twins are judged, the forward
        record's morning marks and chain check run."""
        morning = schedule.next_session(night)
        self.book.db.execute("UPDATE eq_bars SET audit='ok'")
        self.book.db.commit()
        self.clock.t = at(morning, 8, 50)
        out = self.receipts[night.isoformat()]
        out["equity_twins"] = twins.equity_round(self.root, now=self.clock.t, store=self.store)
        out["forward_audit"] = self.job("forward_audit", forward_audit, at(morning, 9, 5))


class TheWholeNight(unittest.TestCase):
    """T11 (the module docstring): one House, read from every side."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="e3-whole-night-")
        cls.w = World(Path(cls.tmp.name))
        cls.db = forward_db.open_db(cls.w.root, readonly=True)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.w.close()
        cls.tmp.cleanup()

    def rows(self, sql: str, *args) -> list[dict]:
        return [dict(row) for row in self.db.execute(sql, args).fetchall()]

    def program(self, key: str):
        return forward_db.program(self.db, key)

    def cp(self, n: int = 30) -> dict:
        return next(c for c in self.w.report["done"]["all"]["checkpoints"] if c["at_close"] == n)

    def scored(self) -> list[dict]:
        """The swarm's scored events (E2's own kind, `pass` "scored"), in order."""
        return [e for e in self.w.store.events_after(0)
                if e["kind"] == "swarm.elane" and e["payload"].get("pass") == "scored"]

    # ------------------------------------------------------------------------------------- the scoring and the event
    def test_e2_scores_each_version_on_its_seen_years_and_says_so_once(self):
        w = self.w
        scored = self.scored()
        self.assertEqual([(e["family"], e["payload"]["version"]) for e in scored], [(fid, 1) for fid in PROGRAMS])
        for event, (fid, (code, _lane, _agenda, _symbols, hidden)) in zip(scored, PROGRAMS.items()):
            v1 = elane_train.record_of(w.store.family(fid))["versions"]["1"]
            self.assertEqual(sorted(v1["years"]), [str(y) for y in elane_folds.WORK_YEARS if y != hidden],
                             "the bar read six seen years, never the hidden one")
            self.assertIsNotNone(v1["pnl_10"], "judged on the bar")
            self.assertEqual(event["payload"]["bar_passed"], bool(v1.get("bar_passed") or v1["passed"]))
            self.assertEqual((event["payload"]["judged"], event["payload"]["sha"]),
                             (True, w.store.version(fid, 1)["sha"]))
        # The memory tables: the seen facts of each, and the hidden year's own runs at both k, sealed.
        self.assertEqual([(r["family"], r["hidden_year"]) for r in e3.table(w.store, "mem_seen")],
                         sorted((fid, spec[4]) for fid, spec in PROGRAMS.items()))
        self.assertEqual(sorted((r["family"], r["year"], r["k"]) for r in e3.table(w.store, "mem_contrib")),
                         sorted((fid, spec[4], k) for fid, spec in PROGRAMS.items() for k in (1.0, 1.5)))
        hidden_runs = [r for r in w.store._all("SELECT * FROM runs WHERE family IN ('carries', 'carries-q')")]
        self.assertEqual(len(hidden_runs), sum(2 * len(elane_folds.seen_spans(spec[4])) for spec in PROGRAMS.values()),
                         "the stored runs are the seen runs: the hidden run is kept nowhere but the sealed tables")

    # ------------------------------------------------------------------------------------------------- the registry
    def test_the_registry_row_is_dated_by_its_event_and_chained(self):
        w = self.w
        self.assertEqual({k: w.registered[k] for k in ("registered", "controls", "skipped", "chain_ok")},
                         {"registered": 2, "controls": 5, "skipped": 0, "chain_ok": True})
        events = {e["family"]: e for e in self.scored()}
        rows = self.rows("SELECT * FROM fwd_registry ORDER BY pid")
        programs = [row for row in rows if row["reason"] != "control"]
        self.assertEqual([row["key"] for row in programs], ["carries@1", "carries-q@1"])
        for row in programs:
            fid = row["family"]
            v1 = elane_train.record_of(w.store.family(fid))["versions"]["1"]
            self.assertEqual(row["reason"], "train_pass" if (v1.get("bar_passed") or v1["passed"]) else "train_fail")
            self.assertEqual(row["evidence"], f"event:{events[fid]['seq']}", "its time is the scored event's")
            self.assertEqual(row["created_at"], w.scored_at)
            # D2: scored at 10:00 on fwd[1], it first decides at that close and has no day before fwd[2].
            self.assertEqual((row["first_close"], row["first_day"]), (w.fwd[1].isoformat(), w.fwd[2].isoformat()))
            self.assertEqual((row["route"], row["alpha_f"]), (forward_db.E3_ROUTE, forward_db.E3_ALPHA_F))
            self.assertEqual((row["lane"], row["ugroup"]), (PROGRAMS[fid][1], "index"))
            self.assertEqual(row["code"], PROGRAMS[fid][0])
        controls = [row for row in rows if row["reason"] == "control"]
        self.assertEqual([(row["key"], row["route"], row["alpha_f"]) for row in controls],
                         [(f"control:index:{n}", "none", "0") for n in range(5)])
        # The chain: each row's hash is its own content on the row before it, from the genesis.
        prev = forward_db.GENESIS
        for row in rows:
            self.assertEqual((row["prev_hash"], row["row_hash"]), (prev, forward_db.row_hash(prev, row)))
            prev = row["row_hash"]
        self.assertEqual(forward_db.verify_chain(self.db), {"ok": True, "rows": 7, "head": prev, "first_bad": None})
        self.assertEqual(forward_db.kv_get(self.db, "fgs_prereg"), forward_db.FGS_SHA, "the screen's shape, pinned")

    def test_a_tampered_alpha_breaks_the_chain(self):
        copy = Path(self.w.base) / "tampered"
        copy.mkdir(exist_ok=True)
        with contextlib.closing(sqlite3.connect(copy / forward_db.DB)) as target:
            self.db.backup(target)
            target.execute("DROP TRIGGER fwd_registry_no_update")
            target.execute("UPDATE fwd_registry SET alpha_f='0.12' WHERE key='carries@1'")
            target.commit()
        tampered = forward_db.open_db(copy, readonly=True)
        try:
            self.assertEqual({k: v for k, v in forward_db.verify_chain(tampered).items() if k in ("ok", "first_bad")},
                             {"ok": False, "first_bad": 1})
        finally:
            tampered.close()

    def test_the_tags_are_what_the_swarm_and_the_book_learned_later(self):
        tags = {(row["pid"], row["tag"], row["value"]) for row in self.rows("SELECT pid, tag, value FROM fwd_tags")}
        live = {(self.program(key).pid, "live", iid) for key, iid in self.w.instances.items()}
        self.assertLessEqual(live, tags, "each live instance tags its registry row")
        # E2's review after the bar (it refuses a program that sizes from the sleeve's dollars, as this fixture does on
        # purpose; passed or refused, the bar was met and the row is a passer's) is a tag too, never the row's reason.
        self.assertEqual({(pid, tag) for pid, tag, _ in tags if tag != "live"},
                         {(self.program(f"{fid}@1").pid,
                           "review_pass" if elane_train.record_of(self.w.store.family(fid))["versions"]["1"]["passed"]
                           else "review_fail") for fid in PROGRAMS})
        self.assertEqual(self.rows("SELECT * FROM fwd_tags WHERE tag IN ('stopped', 'suspect', 'resumed')"), [])

    # --------------------------------------------------------------------------------------------------- the shadow
    def test_two_more_sessions_give_each_program_its_two_forward_days_and_no_day_before(self):
        w = self.w
        first, second, third = (w.receipts[w.fwd[i].isoformat()]["forward_shadow"] for i in (1, 2, 3))
        # The night of the scoring the store ends at the first close: the programs have no forward day yet.
        self.assertEqual((first["programs"], first["new_days"], first["errors"]), (0, 0, 0))
        self.assertEqual((second["programs"], second["new_days"], second["sessions"]), (2, 2, 2))
        self.assertEqual((third["programs"], third["new_days"], third["sessions"]), (2, 2, 4), "recomputed whole")
        for key in LID_BASE:
            stored = self.rows("SELECT day FROM fwd_days WHERE pid=? ORDER BY day", self.program(key).pid)
            self.assertEqual([r["day"] for r in stored], [d.isoformat() for d in w.fwd[2:NIGHTS + 1]])
        self.assertEqual(self.db.execute("SELECT MIN(day) FROM fwd_days").fetchone()[0], w.fwd[2].isoformat())
        for night, jobs in w.receipts.items():
            shadow = jobs["forward_shadow"]
            self.assertNotIn("status", shadow, (night, shadow))
            self.assertEqual((shadow["errors"], shadow["data_failed"], shadow["house"], shadow["stale"]), (0, 0, 0, 0),
                             night)
        self.assertEqual(self.rows("SELECT * FROM fwd_events WHERE kind IN ('night_failed', 'run_failed', "
                                   "'data_failed', 'restated', 'run_disqualified', 'budget_hit', 'chain_broken')"), [])
        self.assertEqual(len(self.rows("SELECT * FROM fwd_runs")), NIGHTS)

    def test_the_shadow_ran_in_its_own_decider_instance(self):
        w = self.w
        self.assertGreaterEqual(len(w.children), NIGHTS, "a child of its own every night")
        self.assertEqual(len({id(child) for child in w.children}), len(w.children))
        self.assertNotIn(id(w.runner.decider), {id(child) for child in w.children},
                         "never the decider the swarm's researcher scored on")

    def test_a_stored_day_is_the_screens_series_of_e1s_engine_on_those_days(self):
        # D3, read back with a decider and a store of the test's own: the same run, the same series, the same rows.
        w = self.w
        store_root = w.root / STORE_DIR
        store = EquityStore(store_root, gate=mint_equity_gate_capability(store_root, "t11-check"))
        for key in LID_BASE:
            program = self.program(key)
            bars = store.bars(program.needs["symbols"], "forward", history=program.needs["history"],
                              start=program.first_day)
            self.assertEqual(int(bars.first), program.needs["history"] + 1, "history + 1 sessions before its first")
            series = {}
            for k in (config.K_BASE, config.K_STRESS):
                result = InlineDecider().kind("equity", "run", {"code": program.code, "params": program.params,
                                                                "name": program.key, "bars": bars, "k": k,
                                                                "capital": None}, budget_seconds=120.0)["result"]
                self.assertEqual(result["status"], "ok")
                series[k] = screen.series(result["lots"], bars, universe=list(program.needs["symbols"]),
                                          capital=result["capital"])
            base, stress = series[config.K_BASE], series[config.K_STRESS]
            stored = self.rows("SELECT * FROM fwd_days WHERE pid=? AND engine=? ORDER BY day", program.pid,
                               forward_db.engine_now(self.db))
            self.assertEqual([r["day"] for r in stored], [from_ordinal(int(d)).isoformat() for d in base.days])
            for name, want in (("r", base.r), ("w", base.w), ("b", base.b), ("r15", stress.r)):
                np.testing.assert_allclose([r[name] for r in stored], want, rtol=0, atol=1e-12, err_msg=f"{key} {name}")
            self.assertEqual({r["status"] for r in stored}, {"ok"})
            self.assertTrue(all(r["r0"] is None for r in stored), "a program has no cost-free series")
            # BINDING FACT 1: every shadow decision's bars hash is on its row.
            self.assertTrue(all(isinstance(r["bars"], str) and r["bars"] for r in stored), "each decision's bars hash")
            self.assertGreater(sum(r["entries"] for r in stored), 10, "it trades")

    def test_the_controls_are_recomputed_beside_them_cost_free_series_and_all(self):
        w = self.w
        controls = self.rows("SELECT pid, first_day FROM fwd_registry WHERE reason='control' ORDER BY pid")
        self.assertEqual(len(controls), 5)
        for control in controls:
            stored = self.rows("SELECT * FROM fwd_days WHERE pid=? ORDER BY day", control["pid"])
            self.assertEqual([r["day"] for r in stored],
                             [d.isoformat() for d in w.fwd[:NIGHTS + 1] if d.isoformat() >= control["first_day"]])
            self.assertTrue(all(r["r0"] is not None and r["r"] <= r["r0"] + 1e-12 for r in stored), "costs subtract")
            self.assertTrue(all(r["bars"] is None for r in stored), "a control reads no bar and decides nothing")
        self.assertEqual(self.rows("SELECT tag FROM fwd_tags WHERE pid IN (SELECT pid FROM fwd_registry WHERE "
                                   "reason='control')"), [], "a control is never tagged")

    def test_the_checkpoints_are_recorded_a_night_after_their_last_day_and_judge_nothing(self):
        checks = self.rows("SELECT c.*, g.reason FROM fwd_checks c JOIN fwd_registry g ON g.pid=c.pid ORDER BY c.pid")
        self.assertEqual([(c["pid"], c["n"], c["final"]) for c in checks], [(pid, 20, 0) for pid in range(1, 8)])
        for check in checks:
            counted = forward_db.counted_days(self.db, check["pid"])
            self.assertEqual(check["day"], counted[19]["day"], "over its first 20 counted days")
            written = dt.datetime.fromtimestamp(check["at"], schedule.NY).date().isoformat()
            self.assertGreater(written, check["day"], "written the night after: its morning audit had run")
            xs = [row["r"] - row["w"] * row["b"] for row in counted[:20]]
            self.assertAlmostEqual(check["sum_r"], float(np.sum([row["r"] for row in counted[:20]])), places=12)
            if check["t_x"] is not None:
                want = float(np.mean(xs) / np.std(xs, ddof=1) * np.sqrt(20))
                self.assertAlmostEqual(check["t_x"], want, places=9)
            if check["reason"] == "control":      # its cost-free excess beside (a control that never traded has no t)
                self.assertEqual((check["t_x0"] is None, check["p_x0"] is None), (check["t_x"] is None,) * 2)
            else:
                self.assertEqual((check["t_x0"], check["p_x0"]), (None, None), "a program has no cost-free series")
                self.assertAlmostEqual(check["p_x"], forward_stats.p_one_sided(check["t_x"], 20), places=12)
        self.assertEqual(self.rows("SELECT * FROM fwd_events WHERE kind IN ('stopped', 'suspect')"), [],
                         "E3 writes no verdict and stopped nobody")

    def test_the_morning_job_verified_the_chain_and_marked_nobody(self):
        audits = [jobs["forward_audit"] for jobs in self.w.receipts.values()]
        self.assertEqual([(a["chain_ok"], a["marked"], a["marks"]) for a in audits], [(True, 0, "ok")] * NIGHTS)
        self.assertEqual(len(self.rows("SELECT * FROM fwd_events WHERE kind='chain_ok'")), NIGHTS)
        self.assertEqual(self.rows("SELECT * FROM fwd_events WHERE kind='audit_mismatch'"), [])

    # ------------------------------------------------------------------------------------- the meters and the report
    def test_the_meters_have_a_row_a_forward_day_first_write_standing(self):
        w = self.w
        days = [d.isoformat() for d in w.fwd[:NIGHTS + 1]]
        for table in ("fwd_cey", "fwd_meter"):
            self.assertEqual([r["day"] for r in self.rows(f"SELECT day FROM {table} ORDER BY day")], days, table)
        cey = self.rows("SELECT * FROM fwd_cey ORDER BY day")
        self.assertEqual([c["members"] for c in cey][-1], 2, "one representative a lineage, the controls outside")
        totals = [c["cey_total"] for c in cey]
        self.assertEqual(totals, sorted(totals), "clean evidence only accrues")
        self.assertEqual({c["neff"] for c in cey if c["n_w"] < forward_db.NEFF_MIN_DAYS}, {0.0})
        self.assertGreater(totals[-1], 0.0)
        self.assertLessEqual(max(c["neff"] for c in cey), 2.0)
        meter = self.rows("SELECT * FROM fwd_meter ORDER BY day")[-1]
        self.assertEqual((meter["m"], meter["controls_m"]), (2, 5), "each with its 20-session checkpoint")
        self.assertLessEqual(meter["by_"], meter["bh"])
        groups = {(g["day"], g["grp"]): g for g in self.rows("SELECT * FROM fwd_groups")}
        last = days[-1]
        self.assertEqual((groups[(last, "train_pass")]["n"], groups[(last, "control:index")]["n"]), (2, 5))
        self.assertIsNotNone(groups[(last, "control:index")]["mean_x0"])
        # Each forward day's meters were written by one run of the job and by no later one (the receipts say how many
        # days each run wrote; the first run also wrote the day before the first night).
        wrote = [jobs["forward_report"]["days"] for jobs in w.receipts.values()]
        self.assertEqual((sum(wrote), wrote[1:]), (len(days), [1] * (NIGHTS - 1)))

    def test_the_report_file_the_dlane_section_and_the_funnel_read_them(self):
        w = self.w
        doc = read_json(w.root / forward_report.FILE, None)
        self.assertEqual(sorted(doc), sorted(forward_report.SECTION_KEYS))
        self.assertEqual((doc["mode"], doc["t0"], doc["through"]),
                         ("record", w.fwd[0].isoformat(), w.fwd[NIGHTS].isoformat()))
        self.assertEqual([key for key in doc if isinstance(doc[key], dict) and "error" in doc[key]], [], "all read")
        self.assertEqual(doc["alarms"], [])
        # The dlane report carries that section as the job last wrote it, and no forward alarm on a healthy House.
        self.assertEqual(w.report["forward_record"], doc)
        self.assertEqual([a["id"] for a in w.report["alarms"] if a["id"][:2] in ("FW", "RR", "CP", "MM")], [])
        rows = funnel.window(w.root, at(w.fwd[0], 0), w.now)
        self.assertNotIn("forward_record", rows["errors"])
        counts = rows["forward_record"]
        self.assertEqual(set(counts), set(forward_report.FUNNEL_KEYS))
        self.assertTrue(all(type(v) is int for v in counts.values()), counts)
        sessions = len(self.rows("SELECT 1 FROM fwd_days d JOIN fwd_registry g ON g.pid=d.pid WHERE "
                                 "g.reason != 'control' AND d.engine=?", forward_db.engine_now(self.db)))
        self.assertEqual({k: counts[k] for k in ("registered", "lineages", "controls", "program_sessions", "stale",
                                                 "errors", "checkpoints", "oof_seen", "oof_rows")},
                         {"registered": 2, "lineages": 2, "controls": 5, "program_sessions": sessions, "stale": 0,
                          "errors": 0, "checkpoints": 2, "oof_seen": 2, "oof_rows": 4})
        # The receipts the release declares name metrics this funnel carries, as numbers.
        declared = release_receipts.declarations(Path(forward_db.__file__).resolve().parents[2])
        self.assertEqual([d["id"] for d in declared], ["E3-forward", "E3-oof"])
        for declaration in declared:
            self.assertGreater(release_receipts.metric(rows, declaration["metric"]), 0, declaration["id"])

    # ------------------------------------------------------------------------------------------ the fills, the twins
    def test_the_minutes_job_fetched_each_forward_day_once_and_the_timing_table_reads_them(self):
        w = self.w
        days = [d.isoformat() for d in w.fwd[:NIGHTS + 1]]
        written = [day for jobs in w.receipts.values() for day in jobs["fill_minutes"]["days"]]
        self.assertEqual(written, days, "each forward day once; the first run's backfill fetched the day before it")
        self.assertEqual(len(w.venue.calls), 2 * len(days), "two requests a session")
        self.assertEqual({(call["timeframe"], call["adjustment"], call["feed"]) for call in w.venue.calls},
                         {("1Min", "raw", "sip")})
        self.assertEqual(fill_minutes.days_on_disk(w.root), days)
        gap = self.rows("SELECT * FROM fwd_fillgap WHERE day=? ORDER BY symbol, at", days[-1])
        self.assertEqual([(g["symbol"], g["at"]) for g in gap],
                         [(symbol, at_) for symbol in sorted(SYMBOLS) for at_ in ("close", "open")])
        for row in gap:
            self.assertAlmostEqual(row["drift_bp"], MINUTE_BP[row["at"]], places=3)
            self.assertEqual(row["field"], "vw")
        # The live-like re-price of every stored program day, first order in the lots' notional.
        for key in LID_BASE:
            pid = self.program(key).pid
            self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_ll WHERE pid=?", (pid,)).fetchone()[0],
                             self.db.execute("SELECT COUNT(*) FROM fwd_days WHERE pid=?", (pid,)).fetchone()[0])
        self.assertEqual(self.rows("SELECT * FROM fwd_events WHERE kind='no_minute'"), [])

    def test_a_closed_live_lot_gets_its_twin_and_its_fill_gap_parts(self):
        w = self.w
        records = twins.equity_records(w.store)
        closed = [int(r[0]) for r in w.book.db.execute("SELECT lid FROM eq_lots WHERE status='closed' ORDER BY lid")]
        self.assertGreaterEqual(len(closed), 36)
        priced = [lid for lid in closed if (records.get(f"eq:{lid}") or {}).get("status") == "priced"]
        self.assertEqual(priced, closed, "E1's own round judged every closed lot")
        gaps = {g["lid"]: g for g in self.rows("SELECT * FROM fwd_lotgap")}
        # Every closed lot whose twin was final by the last night has its row (the last morning's twins land after it).
        last_evening = dt.datetime.fromtimestamp(at(w.fwd[NIGHTS], 18, 35), dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(sorted(gaps), [lid for lid in closed if records[f"eq:{lid}"]["judged_at"] < last_evening])
        self.assertGreaterEqual(len(gaps), 30)
        for lid, gap in gaps.items():
            record = records[f"eq:{lid}"]
            self.assertEqual((record["final"], record["status"]), (True, "priced"))
            # D11: the fills were the engine's own, so each side slipped by the model's half-spread and no more.
            self.assertAlmostEqual(gap["entry_slip_bp"], gap["model_bp"], places=2)
            self.assertAlmostEqual(gap["exit_slip_bp"], gap["model_bp"], places=2)
            self.assertAlmostEqual(gap["side_gap_bp"], 0.0, places=2)
            self.assertAlmostEqual(gap["twin_gap_bp"], record["gap_bp"], places=6)
            # Timing + execution = slip, on each side; the venue's minute was 2 bp under the close it bought at and
            # 4 bp over the open it sold at (cost-positive: both read as timing in its favour).
            self.assertAlmostEqual(gap["timing_entry_bp"] + gap["exec_entry_bp"], gap["entry_slip_bp"], places=3)
            self.assertAlmostEqual(gap["timing_exit_bp"] + gap["exec_exit_bp"], gap["exit_slip_bp"], places=3)
            self.assertAlmostEqual(gap["timing_entry_bp"], MINUTE_BP["close"], places=2)
            self.assertAlmostEqual(gap["timing_exit_bp"], -MINUTE_BP["open"], places=2)
            self.assertEqual(gap["pid"], self.program(gap["instance"][:-2]).pid)

    def test_the_twins_agree_session_by_session_on_the_same_bars(self):
        w = self.w
        for key, iid in w.instances.items():
            rows = self.rows("SELECT * FROM fwd_twins WHERE instance=? ORDER BY day", iid)
            # From the instance's first decision (the close of fwd[1]); a session's row waits for the next close.
            self.assertEqual([r["day"] for r in rows], [d.isoformat() for d in w.fwd[1:NIGHTS]])
            odd = [r for r in rows if r["agree"] != 1]
            if key == "carries@1":
                # BINDING FACT 1: the live decision of that session was made on bars a cent away and differed. It is
                # one counted row with its cause, never an error.
                self.assertEqual([(r["day"], r["agree"], r["cause"]) for r in odd], [(w.odd, 0, "bars")])
                self.assertNotEqual(odd[0]["live_bars"], odd[0]["shadow_bars"])
                self.assertEqual(json.loads(odd[0]["live_keys"]), [])
                self.assertNotEqual(json.loads(odd[0]["shadow_keys"]), [])
            else:
                self.assertEqual(odd, [])
            same = [r for r in rows if r["agree"] == 1]
            self.assertTrue(all(r["live_bars"] == r["shadow_bars"] and r["cause"] is None for r in same))
            self.assertTrue(all(json.loads(r["live_keys"]) for r in same[1:]), "it sells and buys every session")
            part = self.rows("SELECT * FROM fwd_part WHERE instance=? ORDER BY through", iid)[-1]
            self.assertEqual((part["missed"], part["extra"]), (0, 0))
            self.assertGreaterEqual(part["matched"], 18)
        finishes = [jobs["forward_shadow"]["twins"]["finish"] for jobs in w.receipts.values()]
        self.assertEqual(sum(f["disagreed"] for f in finishes), 1)
        self.assertEqual(sum(f["failed"] + f["interrupted"] + f["unregistered"] + f["mismatched"] for f in finishes), 0)
        self.assertEqual(self.rows("SELECT * FROM fwd_events WHERE kind IN ('twin_interrupted', 'twin_unregistered', "
                                   "'twin_sha_mismatch')"), [])

    # --------------------------------------------------------------------------------------------- the Done meter
    def test_the_done_checkpoint_carries_a14_as_the_real_reader_reads_it(self):
        w = self.w
        done = w.report["done"]["all"]
        self.assertGreaterEqual(done["running"]["closes"], 36)
        cp = self.cp(30)
        counted = [c for c in done["closes"]][:30]
        self.assertTrue(all(c["pid"].startswith("eq:") for c in counted), "thirty equity closes of two programs")
        a14 = cp["a14"]
        self.assertEqual((a14["applies"], a14["holds"], a14["final"], a14["why"]), (True, True, True, None))
        self.assertEqual({k: a14["gap"][k] for k in ("closes", "priced", "unpriced", "pending", "bound_bp", "ok")},
                         {"closes": 30, "priced": 30, "unpriced": 0, "pending": 0, "bound_bp": 15.0, "ok": True})
        self.assertLess(abs(a14["gap"]["mean_gap_bp"]), 0.5)
        intents = a14["intents"]
        self.assertEqual((intents["instances"], intents["missing"], intents["unreadable"], intents["disagreed"]),
                         (2, 0, 0, 1))
        self.assertEqual(intents["causes"], {"bars": 1, "program": 0, "unknown": 0})
        self.assertEqual((intents["agreed"], intents["ok"]), (intents["sessions"] - 1, True))
        self.assertGreaterEqual(intents["share"], forward_db.A14_AGREE)
        # It is `forward_twins.a14_reading` of exactly those closes, with E1's own fill-gap half beside it.
        mine = self._counted()[:30]
        self.assertEqual([c["pid"] for c in mine], [c["pid"] for c in counted])
        reading = forward_twins.a14_reading(w.root, mine)
        self.assertEqual({k: a14[k] for k in ("gap", "intents", "by_instance")},
                         {k: reading[k] for k in ("gap", "intents", "by_instance")})
        self.assertEqual((a14["fill_gap_ok"], a14["consistent"]), (True, True))
        # And the checkpoint reads it: item 4 is the pinned rule's own measure AND A14.
        self.assertEqual((cp["items"]["4"], cp["consistent_ok"]), (True, True))
        self.assertEqual((cp["final"], cp["final_why"]), (True, None))
        self.assertNotIn("A14", cp["why"] or "")
        self.assertEqual(w.report["done"]["preregistered"]["status"], dlane_report.PREREGISTERED["status"])
        self.assertIn("computed since release E3", w.report["done"]["preregistered"]["status"])
        # The Done claim itself rests on it: with A14 read and final, the checkpoint's reading is final too.
        self.assertEqual((cp["holds"], cp["items"]), (True, {"3": True, "4": True, "7": True}))
        self.assertTrue(done["holds"])

    def _counted(self) -> list[dict]:
        """The Done meter's counted closes as it reads them from the book (league/ops/dlane_report.py)."""
        cursor = self.w.book.db.execute("SELECT * FROM eq_lots ORDER BY lid")
        names = [column[0] for column in cursor.description]
        return dlane_report.equity_closes([dict(zip(names, row)) for row in cursor.fetchall()], since=0.0)

    def test_without_the_forward_store_the_dlane_report_is_whole_and_a14_is_not_held(self):
        w = self.w
        moved = w.base / "set-aside"
        moved.mkdir(exist_ok=True)
        names = [p.name for p in w.root.iterdir() if p.name.startswith(forward_db.DB)]
        self.db.close()
        try:
            for name in names:
                shutil.move(str(w.root / name), str(moved / name))
            out = dlane(w.root, w.settings, w.now)
            carried = dlane(w.root, w.settings, w.now, previous=w.report)
        finally:
            for name in names:
                shutil.move(str(moved / name), str(w.root / name))
            type(self).db = forward_db.open_db(w.root, readonly=True)
        self.assertEqual(set(out), set(w.report), "the report is written whole")
        cp = next(c for c in out["done"]["all"]["checkpoints"] if c["at_close"] == 30)
        self.assertEqual((cp["a14"]["applies"], cp["a14"]["holds"], cp["a14"]["final"]), (True, False, False))
        self.assertEqual((cp["holds"], cp["items"]["4"], cp["consistent_ok"], cp["final"]), (False,) * 4)
        self.assertIn("A14 (live fills consistent with their replay)", cp["why"])
        self.assertFalse(out["done"]["all"]["holds"], "unmeasured, no Done claim")
        self.assertNotIn("A8", [a["id"] for a in out["alarms"]])
        # PL1 and K5 are untouched, and so is everything of the reading A14 does not read.
        self.assertEqual((out["program_loss"], out["k5"]), (w.report["program_loss"], w.report["k5"]))
        same = ("at_close", "closes", "programs", "net_usd", "by_program", "research_247", "by_route", "bh")
        self.assertEqual({k: cp[k] for k in same}, {k: self.cp(30)[k] for k in same})
        self.assertEqual(out["done"]["all"]["running"], w.report["done"]["all"]["running"])
        # A FINAL reading is frozen: the report that had read it carries it as it was.
        frozen = next(c for c in carried["done"]["all"]["checkpoints"] if c["at_close"] == 30)
        self.assertEqual({k: v for k, v in frozen.items() if k != "frozen"}, self.cp(30))

    # ---------------------------------------------------------------------------------------------------- the seals
    def test_no_generator_view_changed_byte_for_byte(self):
        w = self.w
        self.assertEqual(sorted(w.before), ["briefs", "choice", "map", "system", "user"])
        self.assertEqual(sorted(w.before["briefs"]), sorted(PROGRAMS))
        for name in w.before:
            self.assertEqual(json.dumps(w.after[name], sort_keys=True).encode(),
                             json.dumps(w.before[name], sort_keys=True).encode(), name)
        text = json.dumps(w.after, sort_keys=True)
        for word in E3_WORDS:
            self.assertNotIn(word, text, f"{word!r} reached a generator")
        for year in {str(spec[4]) for spec in PROGRAMS.values()}:
            for fid, brief in w.after["briefs"].items():
                if str(PROGRAMS[fid][4]) == year:
                    self.assertNotIn(year, brief, "a brief names no held-out year")
        self.assertTrue(all(elane_folds.BRIEF_NOTE in brief for brief in w.after["briefs"].values()))

    def test_no_e3_job_wrote_a_row_of_the_swarm_store(self):
        w = self.w
        self.assertEqual(sorted(w.rows_after), sorted(w.rows_before), "no table added")
        for table in w.rows_before:
            self.assertEqual(w.rows_after[table], w.rows_before[table], table)
        self.assertGreater(len(twins.equity_records(w.store)), 30, "but E1's own job wrote its twin records there")

    def test_the_forward_record_really_holds_all_of_it(self):
        # The other half of the seal: there was something to leak.
        self.assertEqual([table for table, n in forward_counts(self.db).items() if n == 0], [], "every table has rows")
        for name in (forward_db.DB, forward_report.FILE, fill_minutes.DIR):
            self.assertTrue((self.w.root / name).exists(), name)
        self.assertGreater(len(e3.table(self.w.store, "mem_series")), 0)

    def test_nothing_e3_writes_lies_under_the_release_and_every_alert_is_counts_and_dates(self):
        w = self.w
        self.assertEqual([p for p in w.release.rglob("*")], [], "nothing E3 writes lies under the release directory")
        self.assertEqual(w.alerts, [], "a healthy House raises no alert from an E3 job")
        # A report read days after the jobs stopped says so (FW1), in ids, counts and dates only.
        later = at(w.fwd[NIGHTS + 3], 12)
        stale = forward_report.alarms(w.root, now=later, settings=w.settings)
        self.assertEqual([a["id"] for a in stale], ["FW1"])
        self.assertTrue(all(forward_report.text_ok(a["text"]) and a["level"] == "warning" for a in stale))
        out = dlane(w.root, w.settings, later)
        self.assertIn("FW1", [a["id"] for a in out["alarms"]], "it rides the dlane report, which the stall job mails")
        self.assertIsNone(out["forward_record"], "a stale section is not shown as today's")


class WithEveryModeOff(unittest.TestCase):
    """The rollback (swarm.json: the three modes "off"): nothing of E3 runs or spends."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="e3-off-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "state"
        self.root.mkdir()
        self.release = self.base / "release"
        self.release.mkdir()
        (self.root / "swarm.json").write_text(json.dumps(OFF))
        self.fwd = forward_sessions(6)
        self.clock = Clock(at(self.fwd[3], 18, 35))
        write_market(self.root, end=self.fwd[-1], as_of=self.fwd[3])
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = swarm_settings.load(self.root, config={})

    def test_the_policy_ships_the_three_at_record_and_swarm_json_turns_each_off(self):
        # The committed policy (these tests read an empty one: league/tests/__init__.py).
        from league.ops import contam_probe
        from league.tests import REAL_POLICY_PATH

        shipped = swarm_settings.load(None, config={}, policy=json.loads(REAL_POLICY_PATH.read_text()))
        self.assertEqual((forward_db.mode(shipped), elane_folds.mode(shipped), contam_probe.mode(shipped)),
                         ("record", "record", "record"))
        self.assertEqual(shipped["_policy"]["state"], "ok")

        off = self.settings
        self.assertEqual((forward_db.mode(off), elane_folds.mode(off), contam_probe.mode(off)), ("off", "off", "off"))
        # A settings object with no E3 block at all is off too (the code defaults).
        self.assertEqual((forward_db.mode({}), elane_folds.mode({}), contam_probe.mode({})), ("off", "off", "off"))

    def test_every_e3_job_is_a_skipped_receipt_that_touches_nothing(self):
        import importlib

        jobs = [job for job in registry.JOBS if job.owner.startswith("E3 ")]
        self.assertEqual([job.name for job in jobs], ["forward_register", "fill_minutes", "forward_shadow",
                                                      "forward_report", "forward_audit", "contam_probe"])
        # A live book and a scored version exist, so every job has something it would do were it on.
        book = book_fx.Book(self.root / "live.sqlite")
        self.addCleanup(book.close)
        book.instance("carries@1", e3.CARRIES, created=at(self.fwd[1], 16, 25))
        e3.hidden_family(self.store, "carries", None, code=e3.CARRIES)
        self.store.event("swarm.elane", "carries", {"pass": "scored", "version": 1, "bar_passed": True, "fails": [],
                                                    "sha": self.store.version("carries", 1)["sha"], "judged": True})
        before = swarm_rows(self.store)
        files = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        receipts = {}
        with mock.patch("league.swarm.models.build_router", side_effect=AssertionError("a model route was built")), \
                mock.patch.object(forward_shadow, "_decider", side_effect=AssertionError("a child was started")):
            for when in (at(self.fwd[3], 18, 35), at(self.fwd[4], 9, 5)):          # an evening and a morning
                self.clock.t = when
                for job in jobs:
                    ctx = Context(job.name, root=self.root, due_at=when, base=self.base, release=self.release,
                                  config={}, clock=self.clock, gateway=Untouchable("the gateway"),
                                  sail=Untouchable("the Sail client"))
                    receipts[job.name] = importlib.import_module(job.module).run(ctx)
                    self.assertEqual(ctx.alerts, [], job.name)
        self.assertEqual({name: receipt.get("status") for name, receipt in receipts.items()},
                         {job.name: "skipped" for job in jobs})
        self.assertTrue(all("off" in receipt["why"] for receipt in receipts.values()), receipts)
        # Nothing written but the report job's own "off" note; nothing spent or recorded in the swarm store.
        after = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        self.assertEqual(sorted(set(after) - set(files)), [forward_report.FILE])
        doc = read_json(self.root / forward_report.FILE, None)
        self.assertEqual((sorted(doc), doc["mode"], doc["alarms"]), (sorted(forward_report.OFF_KEYS), "off", []))
        self.assertEqual((doc["memory"]["contrib"], doc["contamination"], doc["receipts"]), (0, None, []),
                         "no forward part; what has another switch is read (the memory's counts) and has nothing to say")
        self.assertEqual(swarm_rows(self.store), before)
        for name in (forward_db.DB, fill_minutes.DIR, "contamination.json", "forward-decider.log"):
            self.assertFalse((self.root / name).exists(), name)

    def test_the_release_receipts_have_no_switch_and_only_list(self):
        # The one part of E3 that runs whatever the modes say (the spec gives it no switch: it is the stall job's
        # read-back of what a deploy declared). It reads the funnel and keeps its own small store; it spends nothing,
        # contacts nobody and writes no row of the swarm store or the forward record. With the forward record off its
        # two metrics stay at zero, and after their week the receipts read "flat": listed, never reverted.
        repo = Path(forward_db.__file__).resolve().parents[2]
        before = swarm_rows(self.store)
        now = self.clock()
        first = release_receipts.step(self.root, self.base, repo, now=now)
        self.assertEqual((first["declared"], first["read"], first["unread"], first["errors"]),
                         (["E3-forward", "E3-oof"], [], [], []))
        week = max(d["window_hours"] for d in release_receipts.declarations(repo)) * 3600.0
        later = release_receipts.step(self.root, self.base, repo, now=now + week + 3600.0)
        self.assertEqual((later["declared"], later["errors"]), ([], []))
        self.assertEqual(sorted((r["id"], r["verdict"]) for r in later["read"]),
                         [("E3-forward", "flat"), ("E3-oof", "flat")])
        self.assertEqual(swarm_rows(self.store), before)
        self.assertTrue((self.root / release_receipts.DB).exists())
        self.assertFalse((self.root / forward_db.DB).exists())

    def test_a_birth_gets_no_hidden_year_and_a_scoring_makes_no_hidden_run(self):
        settings = e3.settings("off")
        rows = [fx.proposal("born-off", lane="beta", agenda="overnight", symbols=("SPY",), code=fx.program("SPY"),
                            mechanism="Invented overnight idea: index holders are paid for risk they cannot trade.")]
        answers = [fx.answer(rows)]
        router = fx.FakeRouter(lambda call: answers.pop(0) if answers else fx.answer([]))
        for i in range(60):
            self.store.event("swarm.born", f"opt-{i}", {"structure": "debit_vertical", "roots": ["SPY"]})
        with mock.patch("league.swarm.architect.same_idea", lambda a, b: False):
            born = Architect(self.store, router, settings, clock=self.clock).equity_pass()["born"]
        self.assertEqual(len(born), 1, self.store.get("elane_e2_last"))
        fam = self.store.family(born[0])
        self.assertEqual({k: fam["spec"][k] for k in elane_folds.FALLBACK}, elane_folds.FALLBACK)
        self.assertEqual(elane_folds.seen_spans(elane_folds.hidden_year(fam)), elane_train.TRAIN_SPANS)
        runner = e3.InventedMarket()
        with mock.patch.object(elane_train, "state_inputs", fx.state_inputs):
            EquityResearcher(self.store, reviewing_router(), settings, runner=runner,
                             clock=self.clock).score(fam, self.store.version(fam["id"], 1))
        self.assertEqual(runner.calls, [(k, *span) for k in (1.0, 1.5) for span in elane_train.TRAIN_SPANS],
                         "E2's own two spans at each k: no seen stretch, no hidden run")
        self.assertIsNotNone(elane_train.record_of(self.store.family(fam["id"]))["versions"]["1"]["pnl_10"])
        for table in ("mem_seen", "mem_contrib", "mem_series"):
            self.assertEqual(e3.table(self.store, table), [], table)
        brief = EquityResearcher(self.store, reviewing_router(), settings, runner=runner,
                                 clock=self.clock).brief(self.store.family(fam["id"]))
        self.assertNotIn(elane_folds.BRIEF_NOTE, brief)

    def test_the_reports_carry_no_forward_alarm_and_the_funnel_reads_zeros(self):
        now = self.clock()
        self.assertEqual(forward_report.alarms(self.root, now=now, settings=self.settings), [])
        out = dlane(self.root, self.settings, now)
        self.assertEqual([a["id"] for a in out["alarms"] if a["id"][:2] in ("FW", "RR", "CP", "MM")], [])
        self.assertIsNone(out["forward_record"], "no report was written: nothing to show")
        # The switch was turned off an hour after a report that carried a warning: the alarm does not outlive it.
        row = {"id": "FW2", "level": "warning", "new": True,
               "text": "FW2 stale: programs were left stale two nights running"}
        (self.root / forward_report.FILE).write_text(json.dumps({"at": schedule_iso(now - 3600.0), "mode": "record",
                                                                  "alarms": [row]}))
        on = {**self.settings, "elane": {**self.settings["elane"], "forward": {"mode": "record"}}}
        self.assertEqual([a["id"] for a in forward_report.alarms(self.root, now=now, settings=on)], ["FW2"])
        self.assertEqual(forward_report.alarms(self.root, now=now, settings=self.settings), [])
        out = dlane(self.root, self.settings, now)
        self.assertEqual([a["id"] for a in out["alarms"] if a["id"][:2] in ("FW", "RR", "CP", "MM")], [])
        (self.root / forward_report.FILE).unlink()
        counts = funnel.window(self.root, now - 86400.0, now)["forward_record"]
        self.assertEqual(set(counts.values()), {0})
        self.assertFalse((self.root / forward_db.DB).exists(), "reading the record creates no store")
        # A14 itself has no switch: with the record off it is unmeasured, and unmeasured never holds (the stated cost).
        reading = dlane_report.a14_of(self.store, [{"equity": True, "pid": "eq:1", "instance": "carries@1:r",
                                                    "day": self.fwd[3].isoformat()}])
        self.assertEqual((reading["applies"], reading["holds"], reading["final"]), (True, False, False))
        self.assertEqual(dlane_report.a14_of(self.store, [{"equity": False, "pid": 1}])["holds"], True)


if __name__ == "__main__":
    unittest.main()
