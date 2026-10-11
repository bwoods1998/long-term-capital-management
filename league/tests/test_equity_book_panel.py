"""A panel program through E1's EquityBook (release E4, package H's patch 12 to `league/equity/live.py` and `kinds.py`;
E4-SPEC 10.2's B1-B15 less B7 and B12), against the book tests' in-memory venue (league/tests/test_equity_book.py) with
REAL sizing, fees and available cash (money's own rules decide what a basket may buy).

The tests are named for the faults they hold: TheCloseRotation (B7: E1's fix held for a basket), TheCutBuyWaits (B8),
TheLateCatchUp (B9), TheStandingTarget (D10 (4)), TheLateBar (B13), TheMismatchCancels (B11), PanelLotsAreMarked (B15),
AHeldNameThatLeftKeepsItsColumn (B6, B14), APanelAnswerThatFailedCountsOnce (B2, and the captain's A17).

THE PATCH IS ONE: this module is skipped whole while `league.equity.kinds.BOOKS` is absent (the book cannot run a panel
instance at all then), and `ThePatchIsWhole` FAILS a tree that has `BOOKS["panel"]` without B8 and B9: no panel instance
may exist in a tree that lacks them.

Other packages are stubbed AT THEIR INTERFACE: package C's universe, ids and ctx constructors are test_xs_book's doubles;
package D's decider child (the "panel" kind's "decide": the KEEP rule, the standing target's buys, the ineligible lots) is
`Child` below, written from the contract's words (league/xs/E4_INTERFACES.md, league/xs/engine.py's docstring). Every
price is invented."""

import datetime as dt
import hashlib
import inspect
import json
import os
import sqlite3
import tempfile
import unittest
from decimal import ROUND_DOWN, Decimal as D
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity import config
from league.equity import kinds as K
from league.equity import live as L
from league.equity import schedule as S
from league.equity import store as ES
from league.equity.store import STORE_DIR
from league.tests import test_equity_book as T
from league.tests import test_xs_book as XB
from league.xs import book as adapter

APPLIED = hasattr(K, "BOOKS")
THURSDAY, FRIDAY, MONDAY, TUESDAY, WEDNESDAY = (dt.date(2026, 10, 8), T.FRIDAY, T.MONDAY, T.TUESDAY, T.WEDNESDAY)
FAMILY, KEY = "xs-reversal", "xs-reversal@1:r"
NAMES = XB.names(30)
NEEDS = {"panel": "sp500", "history": 60, "max_names": 8, "rebalance": "weekly", "weekday": 0, "max_hold_sessions": 30}
REF = 12


def panel_row(family=FAMILY, *, band="probe", version=1):
    return {"family": family, "band": band, "lane": "equity", "structure": "panel", "symbols": [], "seeded": False,
            "holdout_passed": True, "validation_passed": True, "version": version, "code": T.CODE, "params": {},
            "run_sha": "r1", "validation_r_sd": None}


def tape_day(day: dt.date) -> int:
    return ES.ordinal(day) - ES.ordinal(dt.date(2025, 1, 2))


class Market(T.Market):
    """The book tests' market, with a tape for any symbol (test_xs_book's): quotes four cents wide around the tape's
    price of the clock's day, 1Day bars from the same tape."""

    def __init__(self, clock):
        super().__init__(clock)
        self.tape = XB.Market()

    def close(self, symbol: str, day: dt.date) -> D:
        return D(str(self.tape.moved.get((symbol, day.isoformat()), self.tape.price(symbol, tape_day(day)))))

    def quote(self, symbol: str):
        if symbol in self.quotes:
            return self.quotes[symbol]
        day = S.ny_day(self.clock())
        while not S.is_session(day):
            day -= dt.timedelta(days=1)
        px = self.close(symbol, day)
        return px - D("0.02"), px + D("0.02")

    def stocks(self, symbols):
        self.calls += 1
        out = {}
        for s in symbols:
            bid, ask = self.quote(s)
            t = T.iso(self.clock() - 1)
            out[s] = {"latestQuote": {"bp": float(bid), "ap": float(ask), "t": t},
                      "latestTrade": {"p": float((bid + ask) / 2), "t": t}}
        return out

    def bars(self, symbols, *, timeframe, start, end=None, adjustment="raw"):
        self.bar_calls.append((tuple(symbols), timeframe, start, end, adjustment))
        return self.tape.bars(symbols, timeframe=timeframe, start=start, end=end, adjustment=adjustment)


class Child(T.Decider):
    """The decider at its interface, for both kinds: the book's own (the book tests' double) and "panel" (package D's
    child as its contract says): `ineligible` on EVERY job from the decision's own arrays; on a called day the program's
    target planned by THE KEEP RULE (a held slot in the target is kept, one absent is sold whole, one not held is bought
    as one lot of w x budget); on every other close the standing target's buys and no program code. It answers JSON (a
    target's keys are strings)."""

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.plans: dict = {}            # key -> {"symbols": {SYM: w}, "at"} (None or absent: a hold); or E1's intents
        self.seen: list[dict] = []
        self.asked: list[tuple[str, list[str]]] = []
        self.program_fails: set[str] = set()
        self.lost: set[str] = set()
        self.no_ctx: set[str] = set()
        self.calls: dict[str, int] = {}

    def slot(self, key: str, symbol: str) -> int:
        universe = XB.Universe(self.root)
        aid = next(a for a, spells in universe.spells.items() if spells[-1][0] == symbol)
        return int(XB.ids_for([aid], XB.run_salt(XB.SALT, key), table=universe.table())[0])

    def kind_load(self, kind, key, payload, *, budget_seconds=None):
        if kind != "panel":
            return super().kind_load(kind, key, payload, budget_seconds=budget_seconds)
        self.loads.append((key, dict(payload)))
        if key in self.refuse:
            raise ValueError("the program did not load")
        return {"needs": dict(self.needs.get(key, NEEDS)), "sha": "s" * 64, "run_sha": "r" * 64, "params": {}}

    def kind(self, kind, op, payload, *, budget_seconds=None):
        self.asked.append((kind, [job["key"] for job in payload["jobs"]]))
        if kind != "panel":
            return super().kind(kind, op, payload, budget_seconds=budget_seconds)
        assert op == "decide"
        if self.fail:
            raise RuntimeError("the decider failed")
        return {"ok": True, "results": {job["key"]: self.answer(job) for job in payload["jobs"]}}

    def answer(self, job: dict) -> dict:
        key, inp = job["key"], job["inputs"]
        if key in self.lost:
            return {"missing": True, "failed": True}
        if key in self.no_ctx:
            return {"error": "the ctx could not be built", "failed": True}
        raw = np.asarray(inp.raw)
        valid = np.isfinite(raw[-1, :, 3]) & (raw[-1, :, 4] > 0) & np.isfinite(raw[-2, :, 3])
        elig = np.asarray(inp.elig0, dtype=bool) & valid
        slot_of = {inp.ref + k: int(i) for k, i in enumerate(np.asarray(inp.ids).tolist())}
        candidates = {slot_of[c] for c in slot_of if elig[c]}
        held = {slot_of[p["col"]]: p["lid"] for p in inp.positions}
        self.seen.append({"key": key, "called": job["called"], "standing": job.get("standing"), "inputs": inp,
                          "slots": dict(slot_of)})
        out = {"hold": True, "target": None, "at": None, "orders": [], "rejects": [],
               "ineligible": sorted(p["lid"] for p in inp.positions if not elig[p["col"]]),
               "stats": {"calls": self.calls.get(key, 0)}, "failed": False,
               "ctx_sha": hashlib.sha256(repr((key, int(inp.days[-1]), inp.cash, inp.positions)).encode()).hexdigest()}

        def buys(target, at, skip=()):
            orders, rejects = [], []
            for slot, w in sorted(target.items(), key=lambda kv: (-kv[1], kv[0])):
                if slot in held or slot in skip or slot not in candidates:
                    continue
                usd = (D(str(w)) * D(str(inp.budget))).quantize(D("0.01"), rounding=ROUND_DOWN)
                if usd < 10:
                    rejects.append("under the minimum order")
                else:
                    orders.append({"buy_id": slot, "usd": str(usd), "at": at})
            return orders, rejects

        if job["called"]:
            self.calls[key] = self.calls.get(key, 0) + 1
            out["stats"] = {"calls": self.calls[key]}
            plan = self.plans.get(key)
            if key in self.program_fails:
                out.update(failed=True, why="its decide raised")
            elif plan:
                target = {self.slot(key, s): w for s, w in plan["symbols"].items()}
                if set(target) <= candidates:
                    sells = [{"sell": lid, "at": plan["at"]} for slot, lid in sorted(held.items(), key=lambda kv: kv[1])
                             if slot not in target]
                    orders, rejects = buys(target, plan["at"])
                    out.update(hold=False, target=target, at=plan["at"], orders=sells + orders, rejects=rejects)
                else:
                    out["rejects"] = ["a target names a slot that is not in ctx.ids"]
        elif job.get("standing"):
            standing = job["standing"]
            orders, rejects = buys({int(k): w for k, w in standing["target"].items()}, standing["at"],
                                   skip=set(standing["exited"]))
            out.update(at=standing["at"], orders=orders, rejects=rejects)
        return json.loads(json.dumps(out))


class Harness(T.Harness):
    def __init__(self, root: Path, *, rows=None, E: str = "2229"):
        self.dir = root
        self.child = Child(root / STORE_DIR)
        table = T.equity_table(universe={**config.UNIVERSE, **{s: "stock" for s in NAMES}})
        super().__init__(root, cash=E, E=E, table=table, rows=[panel_row()] if rows is None else rows)
        self.market = Market(self.clock)
        self.venue = T.Venue(self.market, self.clock, cash=E)
        self.decider = self.child
        self.book = self.new_book()
        self.state.put("eq_decide", {"day": THURSDAY.isoformat(), "status": "done"})
        self.inst = L.Instance(KEY, FAMILY, 1, "equity", "r1", T.CODE, {}, "probe", False, 30, created_at=self.clock(),
                               kind="panel")
        self.book._save_instance(self.inst)

    def new_book(self) -> L.EquityBook:
        return L.EquityBook(self.state, self.venue, self.market, self.table, self.families, decider=self.decider,
                            stock_proof=self.proof, sizing_equity=lambda: self.E, options_book=self.options,
                            root=self.dir, clock=self.clock,
                            record=lambda kind, payload, agent=None: self.events.append((kind, payload)),
                            alert=lambda level, text: self.alerts.append((level, text)))

    # ---------------------------------------------------------------- fixtures
    def seed(self, symbol: str, usd: str = "111.45", *, opened: dt.date = THURSDAY, at_day: dt.date = FRIDAY) -> L.Lot:
        """An open lot of the panel instance worth `usd` at `at_day`'s close."""
        px = self.market.close(symbol, at_day)
        qty = (D(usd) / px).quantize(D("1e-9"))
        lot = L.Lot(self.book._next("eq_lots", "lid"), KEY, FAMILY, 1, "equity", symbol, "stock", qty, qty, px, D(usd),
                    "open", opened_at=T.at(opened, 9, 32), opened_day=opened.isoformat(), cash=-D(usd), probe=True,
                    tag="xs")
        self.book._save_lot(lot)
        self.venue.held[symbol] = self.venue.held.get(symbol, D(0)) + qty
        return lot

    def planned(self, day: dt.date, symbols, *, at_: str = "open") -> None:
        """A called decision of `day` already on the table: its target stands."""
        row = adapter.rebalance_row(
            instance=KEY, family=FAMILY, version=1, decided_day=day.isoformat(),
            exec_day=S.next_session(day).isoformat(), at=at_, called=True, targets=[[s, 0.2] for s in symbols],
            standing=False, intents=[], skipped=[], equity="557.25", budget="557.25", cols=None, ctx_sha="c" * 64,
            bars_sha=None, fetch={}, status="planned", why=None, now=self.clock())
        self.state.upsert("eq_rebalances", row, "instance, decided_day")

    def plan(self, symbols, at_: str = "open") -> None:
        self.child.plans[KEY] = {"symbols": {s: 0.2 for s in symbols}, "at": at_}

    def decide(self, day: dt.date, *, minutes=(20, 21, 30)) -> dict:
        """The evening of `day`: the bars from 16:20, the decide at 16:30."""
        out = {}
        for mm in minutes:
            out = self.tick(16, mm, day=day)
        return out

    def run(self, day: dt.date, *minutes) -> None:
        for hh, mm in minutes:
            self.tick(hh, mm, day=day)

    # ---------------------------------------------------------------- readings
    def rebalance(self, day: dt.date) -> dict | None:
        rows = self.state.rows("SELECT * FROM eq_rebalances WHERE instance=? AND decided_day=?", (KEY, day.isoformat()))
        return rows[0] if rows else None

    def instance_now(self) -> L.Instance:
        return self.book._instance(KEY)

    def held(self) -> list[str]:
        return sorted(lot.symbol for lot in self.book._lots(instance=KEY))

    def sent(self, side: str) -> list[dict]:
        return [b for b in self.venue.sent if b["side"] == side]

    def panel_intents(self, **where) -> list[L.Intent]:
        return [i for i in self.intents(**where) if i.instance == KEY]

    def said(self, part: str) -> list[tuple[str, str]]:
        return [a for a in self.alerts if part in a[1]]


@unittest.skipUnless(APPLIED, "package H's patch 12 is not applied to league/equity (league/swarm/e4_patches/H.md)")
class PanelCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.universe = XB.Universe.make(self.root / STORE_DIR, NAMES)
        self.addCleanup(XB.UNIVERSES.pop, str(self.root / STORE_DIR), None)
        patch = XB.fixtures()
        patch.__enter__()
        self.addCleanup(patch.__exit__, None, None, None)
        self.h = Harness(self.root)
        self.addCleanup(self.h.state.close)

    def basket(self, symbols=("N000", "N001", "N002", "N003", "N004"), **kw):
        return [self.h.seed(s, **kw) for s in symbols]

    def usd(self, body: dict) -> D:
        return D(body["qty"]) * D(body["limit_price"])


# ------------------------------------------------------------------------------------------------------------ the patch
@unittest.skipUnless(APPLIED, "package H's patch 12 is not applied to league/equity (league/swarm/e4_patches/H.md)")
class ThePatchIsWhole(unittest.TestCase):
    def test_no_panel_path_without_b8_and_b9(self):
        self.assertEqual(K.BOOKS, {"panel": "league.xs.book"})
        self.assertIs(K.book_for("panel"), adapter)
        self.assertIsNone(K.book_for("equity"))
        self.assertIsNone(K.book_for(None))
        self.assertEqual([K.kind_of(s) for s in ("panel", "etf", "stock", None)], ["panel", "equity", "equity", "equity"])
        self.assertIn("sizing cut", inspect.getsource(L.EquityBook._work_entry), "B8: a cut buy waits for its own sale")
        self.assertIn("entry_until", inspect.getsource(L.EquityBook._panel_record), "B9: a late rebalance plans nothing")
        for name in ("_panel_bars", "_panel_job", "_panel_ineligible", "_panel_audit", "_panel_record_of", "_decide_counts"):
            self.assertTrue(hasattr(L.EquityBook, name), name)

    def test_the_kind_column_is_the_adapters_words_and_an_old_state_gains_it(self):
        self.assertEqual((L.INSTANCE_KIND, L.INSTANCE_KIND_DDL), (adapter.INSTANCE_KIND_COLUMN, adapter.INSTANCE_KIND_DDL))
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            db = sqlite3.connect(str(Path(tmp) / "live.sqlite"))
            for statement in L.SCHEMA.split(";"):
                if statement.strip():
                    db.execute(statement)
            db.execute("INSERT INTO eq_instances (id, family, version, lane, run_sha, code, params, band, max_hold, "
                       "created_at) VALUES ('seed@1:r', 'seed', 1, 'beta', 'r', 'c', '{}', 'probe', 20, 1.0)")
            db.commit()
            db.close()
            for _ in range(2):                                     # the second start finds the column and adds none
                h = T.Harness(Path(tmp))
                self.addCleanup(h.state.close)
            old = h.book._instance("seed@1:r")
            self.assertEqual(old.kind, "equity")
            self.assertEqual(old.row()["kind"], "equity")
            self.assertEqual(h.state.rows("SELECT COUNT(*) AS n FROM eq_rebalances")[0]["n"], 0, "the adapter's table")

    def test_the_kinds_module_names_no_module_of_the_panel_package(self):
        source = Path(K.__file__).read_text()
        self.assertNotIn("import league.xs", source)
        self.assertNotIn("from ..xs", source)
        self.assertNotIn("league.xs", "".join(line for line in Path(L.__file__).read_text().splitlines()
                                               if line.lstrip().startswith(("import ", "from "))))


class NoPanelNoWork(PanelCase):
    """With no instance of the panel kind nothing of the panel runs: no fetch, no file, no row."""

    def test_an_etf_only_book_reads_nothing_of_the_panel(self):
        h = Harness(Path(tempfile.mkdtemp(dir=self.root)), rows=[T.family_row()])
        self.addCleanup(h.state.close)
        h.state.execute("DELETE FROM eq_instances")
        h.child.plans[L.instance_key("seed-overnight-spy", 1)] = [{"buy": "SPY", "share": 1.0, "at": "close"}]
        with mock.patch.object(adapter, "columns", side_effect=AssertionError("the panel was asked")), \
                mock.patch.object(adapter, "fetch", side_effect=AssertionError("the panel fetched")):
            out = h.decide(FRIDAY)
            h.run(MONDAY, (8, 31), (9, 26), (9, 31))
        self.assertEqual(out["decided"], ["seed-overnight-spy@1:r: 1"])
        self.assertEqual(h.child.asked, [("equity", ["seed-overnight-spy@1:r"])])
        self.assertEqual(h.book._instance("seed-overnight-spy@1:r").kind, "equity")
        self.assertFalse((h.dir / STORE_DIR / adapter.LIVE_BARS_DIR).exists())
        self.assertEqual(h.state.rows("SELECT COUNT(*) AS n FROM eq_rebalances")[0]["n"], 0)
        self.assertEqual({symbols for symbols, *_ in h.market.bar_calls}, {("SPY",)}, "only the book's own read")
        self.assertEqual(h.book._panel, {})

    def test_an_adapter_that_cannot_be_imported_fails_only_its_own_kind(self):
        with mock.patch.object(K, "book_for", side_effect=ImportError("no numpy here")):
            h = Harness(Path(tempfile.mkdtemp(dir=self.root)), rows=[T.family_row(), panel_row()])
            self.addCleanup(h.state.close)
            h.child.plans[L.instance_key("seed-overnight-spy", 1)] = [{"buy": "SPY", "share": 1.0, "at": "close"}]
            out = h.decide(FRIDAY)
        self.assertEqual(out["decided"], ["seed-overnight-spy@1:r: 1"], "the book's own programs go on")
        self.assertIn("the panel adapter cannot be imported", out["decide_failed"][KEY])
        self.assertEqual(h.instance_now().failed_decides, 1, "its schedule cannot be read: counted, as before")

    def test_both_kinds_are_asked_each_by_its_own_child(self):
        h = Harness(Path(tempfile.mkdtemp(dir=self.root)), rows=[T.family_row(), panel_row()])
        self.addCleanup(h.state.close)
        XB.UNIVERSES[str(h.dir / STORE_DIR)] = self.universe
        h.child.plans[L.instance_key("seed-overnight-spy", 1)] = [{"buy": "SPY", "share": 1.0, "at": "close"}]
        h.plan(["N010", "N011", "N012", "N013", "N014"])
        out = h.decide(FRIDAY)
        self.assertEqual(sorted(out["decided"]), ["seed-overnight-spy@1:r: 1", f"{KEY}: 5"])
        self.assertEqual(h.child.asked, [("equity", ["seed-overnight-spy@1:r"]), ("panel", [KEY])])
        self.assertEqual([key for key, _ in h.child.loads if key == KEY], [KEY])
        self.assertEqual(h.state.get("eq_decide")["instances"], sorted(["seed-overnight-spy@1:r", KEY]))


# ------------------------------------------------------------------------------------------------------ B1-B5, a decide
class ACalledDecision(PanelCase):
    def test_a_rebalance_becomes_intents_and_one_row(self):
        h = self.h
        self.basket(("N000", "N001"))
        h.plan(["N000", "N010", "N011", "N012", "N013"])
        out = h.decide(FRIDAY)
        self.assertEqual(out["decided"], [f"{KEY}: 5"])
        intents = h.panel_intents()
        self.assertEqual([(i.kind, i.symbol, i.at, i.tag, i.status) for i in intents],
                         [("sell", "N001", "open", "xs", "planned")] +
                         [("buy", s, "open", "xs", "planned") for s in sorted(
                             ["N010", "N011", "N012", "N013"], key=lambda s: h.child.slot(KEY, s))])
        self.assertEqual({i.usd for i in intents if i.kind == "buy"}, {D("111.45")}, "0.20 of a 0.25 x E sleeve")
        self.assertEqual({i.exec_day for i in intents}, {MONDAY.isoformat()})
        row = h.rebalance(FRIDAY)
        self.assertEqual((row["status"], row["called"], row["standing"], row["at"], row["exec_day"]),
                         ("planned", 1, 0, "open", MONDAY.isoformat()))
        self.assertEqual((row["n_names"], row["n_sells"], row["n_buys"], row["n_skipped"]), (5, 1, 4, 0))
        self.assertEqual(json.loads(row["targets"]), [[s, 0.2] for s in ("N000", "N010", "N011", "N012", "N013")])
        self.assertEqual((row["budget"], row["extra"], row["audit"]), ("557.25", "[]", None))
        self.assertEqual({i.bars_sha for i in intents}, {row["bars_sha"]})
        self.assertEqual({i.ctx_sha for i in intents}, {row["ctx_sha"]})
        fetch = json.loads(row["fetch"])
        self.assertEqual((fetch["calls"], fetch["symbols"], fetch["missing"], fetch["late"]), (4, 42, 0, False))
        inst = h.instance_now()
        self.assertEqual((inst.kind, inst.last_decided_day, inst.failed_decides, inst.max_hold), ("panel", "2026-10-09", 0, 30))
        events = [p for k, p in h.events if k == "equity.rebalance"]
        self.assertEqual(events, [{"instance": KEY, "day": "2026-10-09", "exec_day": "2026-10-12", "at": "open",
                                   "called": True, "standing": False, "names": 5, "sells": 1, "buys": 4, "skipped": 0,
                                   "status": "planned"}])
        self.assertEqual(h.state.get("eq_decide")["instances"], [KEY])

    def test_the_job_is_the_adapters_and_the_bars_are_kept(self):
        h = self.h
        self.basket(("N000",))
        h.plan(["N000", "N010", "N011", "N012", "N013"])
        h.decide(FRIDAY)
        seen = h.child.seen[-1]
        self.assertEqual((seen["called"], seen["standing"]), (True, None))
        inp = seen["inputs"]
        self.assertEqual((inp.budget, inp.max_names, inp.history), (557.25, 8, 60))
        self.assertAlmostEqual(inp.cash, 557.25 - 111.45, places=4)
        self.assertEqual(int(inp.days[-1]), ES.ordinal(FRIDAY))
        kept = adapter.kept(self.root / STORE_DIR, FRIDAY)
        self.assertIsNotNone(kept, "the bytes a decision read are kept")
        self.assertEqual(json.loads(h.rebalance(FRIDAY)["fetch"])["sha"], adapter.bars_sha(kept[1], kept[0]))
        self.assertEqual(len([c for c in h.market.bar_calls if len(c[0]) > 1]), 4, "ONE chunked fetch: 42 columns, raw and all")
        h.run(FRIDAY, (16, 31), (16, 32))
        self.assertEqual(len([c for c in h.market.bar_calls if len(c[0]) > 1]), 4, "decided once, fetched once")
        self.assertEqual(len(h.child.seen), 1)

    def test_a_hold_and_a_buy_outside_the_universe(self):
        h = self.h
        h.decide(FRIDAY)
        row = h.rebalance(FRIDAY)
        self.assertEqual((row["status"], row["called"], row["n_names"], row["targets"]), ("hold", 1, 0, "[]"))
        self.assertEqual(h.panel_intents(), [])
        # A candidate the constitution's list lacks is refused by the book's own check (the adapter never plans one:
        # D4's tradable row; this is the wall behind it).
        table = T.equity_table(universe={**config.UNIVERSE, **{s: "stock" for s in NAMES if s != "N010"}})
        h.table = __import__("dataclasses").replace(h.table, equity=table)
        h.book = h.new_book()
        h.state.execute("UPDATE eq_instances SET last_decided_day=NULL")
        h.state.put("eq_decide", {"day": THURSDAY.isoformat(), "status": "done"})
        h.plan(["N010", "N011", "N012", "N013", "N014"])
        h.decide(FRIDAY, minutes=(40,))
        refused = h.panel_intents(status="refused")
        self.assertEqual([i.symbol for i in refused], ["N010"])
        self.assertEqual(len(h.panel_intents(status="planned")), 4)


# -------------------------------------------------------------------------------------------------------------- B7
class TheCloseRotation(PanelCase):
    """A target at the close replacing 3 of 5 names: the 3 buys go after the 3 sales, each whole, none refused."""

    def setUp(self):
        super().setUp()
        self.basket()
        self.h.plan(["N000", "N001", "N010", "N011", "N012"], "close")
        self.h.decide(FRIDAY)

    def test_the_buys_wait_for_the_sales(self):
        h = self.h
        self.assertEqual(sorted((i.kind, i.symbol, i.at) for i in h.panel_intents()),
                         sorted([("sell", s, "close") for s in ("N002", "N003", "N004")] +
                                [("buy", s, "close") for s in ("N010", "N011", "N012")]))
        h.run(MONDAY, (8, 31), (9, 26), (9, 31), (9, 33), (12, 0))
        self.assertEqual(h.venue.sent, [], "a close target waits for the close")
        h.venue.fill = "none"
        h.tick(15, 55)
        self.assertEqual(sorted(b["symbol"] for b in h.sent("sell")), ["N002", "N003", "N004"])
        self.assertEqual(h.sent("buy"), [], "the sleeve is full until a sale fills")
        h.venue.fill = "cross"
        h.tick(15, 56)
        buys = h.sent("buy")
        self.assertEqual(sorted(b["symbol"] for b in buys), ["N010", "N011", "N012"])
        for body in buys:
            self.assertGreater(self.usd(body), D("111.40"), "each buy whole: a fifth of the sleeve")
            self.assertLessEqual(self.usd(body), D("111.45"))
        self.assertEqual(h.held(), ["N000", "N001", "N010", "N011", "N012"])
        h.tick(15, 57)
        self.assertEqual({i.status for i in h.panel_intents()}, {"done"}, "none refused, none missed")
        self.assertEqual({(lot.entry_at, lot.opened_day) for lot in h.book._lots(instance=KEY) if lot.symbol > "N009"},
                         {("close", MONDAY.isoformat())})

    def test_in_one_minute_when_the_sales_fill_at_once(self):
        h = self.h
        h.run(MONDAY, (9, 26), (15, 55))
        self.assertEqual([b["side"] for b in h.venue.sent], ["sell"] * 3 + ["buy"] * 3, "exits first, then entries")
        self.assertEqual(h.held(), ["N000", "N001", "N010", "N011", "N012"])
        h.tick(15, 56)
        self.assertEqual({i.status for i in h.panel_intents()}, {"done"})
        self.assertEqual(len(h.venue.sent), 6)


# -------------------------------------------------------------------------------------------------------------- B8
class TheCutBuyWaits(PanelCase):
    """An open-window sale that fills at 09:36 with $40 idle in the sleeve: its $111 buy waits and goes whole."""

    def setUp(self):
        super().setUp()
        self.basket(("N000", "N001", "N002", "N003"))
        self.h.seed("N004", "71.45")                                  # $40 of the $557.25 sleeve is idle
        self.h.plan(["N000", "N001", "N002", "N004", "N010"])         # N003 out, N010 in
        self.h.decide(FRIDAY)

    def test_never_at_forty_dollars(self):
        h = self.h
        h.venue.fill = "none"
        h.run(MONDAY, (9, 26), (9, 31))
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent], [("sell", "N003")])
        for minute in (33, 34, 35):
            h.tick(9, minute)
            self.assertEqual(h.sent("buy"), [], "sized to $40 while its own sale works: it waits")
            buy = h.panel_intents(kind="buy")[0]
            self.assertEqual(buy.status, "planned")
            self.assertIn("sizing cut (sleeve_cash)", buy.why)
            self.assertIn("1 exit(s) of its own program", buy.why)
        h.venue.fill = "cross"
        h.tick(9, 36)
        buys = h.sent("buy")
        self.assertEqual([b["symbol"] for b in buys], ["N010"])
        self.assertGreater(self.usd(buys[0]), D("111.40"), "whole, once its sale filled")
        self.assertEqual(h.held(), ["N000", "N001", "N002", "N004", "N010"])
        h.tick(9, 37)
        self.assertEqual(h.panel_intents(kind="buy")[0].status, "done")
        self.assertEqual(len(h.sent("buy")), 1, "one order, never a second for the rest")

    def test_a_sale_that_never_fills_leaves_the_buy_missed_not_cut(self):
        h = self.h
        h.venue.fill = "none"
        h.run(MONDAY, (9, 26), (9, 31), (9, 33), (9, 40), (9, 44), (9, 45))
        self.assertEqual(h.sent("buy"), [])
        buy = h.panel_intents(kind="buy")[0]
        self.assertEqual(buy.status, "missed")
        self.assertIn("sizing cut", buy.why)

    def test_a_buy_sized_in_full_goes_at_once(self):
        h = self.h
        h.state.execute("DELETE FROM eq_lots WHERE symbol='N002'")     # $151 idle: the buy fits beside the sale
        del h.venue.held["N002"]
        h.venue.fill = "none"
        h.run(MONDAY, (9, 26), (9, 31), (9, 33))
        self.assertEqual([b["symbol"] for b in h.sent("buy")], ["N010"])
        self.assertGreater(self.usd(h.sent("buy")[0]), D("111.40"))

    def test_another_programs_sale_holds_no_buy_back(self):
        h = self.h
        other = h.instance("seed-overnight-spy")
        lot = h.lot(other, "SPY", "0.1", "600")
        h.intent(other, "sell", symbol="SPY", lid=lot.lid)
        h.state.execute("DELETE FROM eq_intents WHERE kind='sell' AND instance=?", (KEY,))
        h.venue.fill = "none"
        h.run(MONDAY, (9, 26), (9, 31), (9, 33))
        cut = h.sent("buy")
        self.assertEqual([b["symbol"] for b in cut], ["N010"], "no exit of its OWN program is due: the cut is final, as E1's")
        self.assertLess(self.usd(cut[0]), D("41"))

    def test_an_etf_rotation_waits_the_same_way(self):
        """B8 changes the book for EVERY instance (E4-SPEC decision 27): an ETF program's buy cut by its own sale waits
        too. The seeds have no sale in a buy's window: nothing changes for them."""
        h = self.h
        h.state.execute("DELETE FROM eq_intents")
        h.state.execute("DELETE FROM eq_lots")
        h.venue.held.clear()
        seed = h.instance("seed-overnight-spy")
        lot = h.lot(seed, "SPY", "0.8", "600")                      # $480 of its $557.25 sleeve
        h.intent(seed, "sell", symbol="SPY", lid=lot.lid)
        buy = h.intent(seed, "buy", symbol="QQQ", share="0.5")    # $278.62: an ETF's half of the sleeve
        h.venue.fill = "none"
        h.run(MONDAY, (9, 26), (9, 31), (9, 33))
        self.assertEqual(h.sent("buy"), [])
        self.assertIn("sizing cut (sleeve_cash)", h.get_intent(buy.iid).why)
        h.venue.fill = "cross"
        h.tick(9, 34)
        self.assertEqual([b["symbol"] for b in h.sent("buy")], ["QQQ"])
        self.assertGreater(self.usd(h.sent("buy")[0]), D("278"), "whole, never the $77 the sleeve had free")


# -------------------------------------------------------------------------------------------------------------- B9
class TheLateCatchUp(PanelCase):
    """A decide recorded at 10:00 ET plans nothing at the open, and the next close's standing target buys."""

    def setUp(self):
        super().setUp()
        self.basket(("N000", "N001", "N002", "N003"))
        self.h.planned(dt.date(2026, 10, 2), ["N000", "N001", "N002", "N003", "N010"])
        self.h.plan(["N000", "N001", "N020", "N021", "N022"])

    def test_an_open_target_recorded_late_plans_nothing(self):
        h = self.h
        out = h.tick(10, 0, day=MONDAY)                                # the House was down since Friday's close
        self.assertEqual(h.panel_intents(), [], "its sells would go all day and its buys were already missed")
        row = h.rebalance(FRIDAY)
        self.assertEqual((row["status"], row["called"], row["n_sells"], row["n_buys"]), ("late", 1, 0, 0))
        self.assertIn("after the open window's entry cut-off", row["why"])
        self.assertIn(KEY, out["decide_failed"])
        inst = h.instance_now()
        self.assertEqual((inst.failed_decides, inst.last_decided_day), (1, FRIDAY.isoformat()), "a failed decide, spent")
        self.assertEqual(len(h.said("after the open window's entry cut-off")), 1)
        self.assertEqual(h.venue.sent, [])
        h.tick(10, 1, day=MONDAY)
        self.assertEqual(len(h.child.seen), 1, "asked once")
        # Monday's close, a hold day: the standing target is the one BEFORE the late one, and its missing name is bought.
        h.decide(MONDAY)
        seen = h.child.seen[-1]
        self.assertFalse(seen["called"])
        self.assertEqual(set(seen["standing"]["target"]), {h.child.slot(KEY, s) for s in ("N000", "N001", "N002", "N003", "N010")})
        self.assertEqual([(i.kind, i.symbol, i.exec_day, i.usd) for i in h.panel_intents()],
                         [("buy", "N010", TUESDAY.isoformat(), D("111.45"))])
        row = h.rebalance(MONDAY)
        self.assertEqual((row["status"], row["called"], row["standing"], row["n_buys"]), ("hold", 0, 1, 1))
        self.assertEqual(h.instance_now().failed_decides, 1, "a hold day neither counts nor resets (A17)")
        h.run(TUESDAY, (9, 26), (9, 31), (9, 33))
        self.assertEqual(h.held(), ["N000", "N001", "N002", "N003", "N010"])

    def test_a_close_target_recorded_late_is_planned_as_usual(self):
        h = self.h
        h.plan(["N000", "N001", "N020", "N021", "N022"], "close")
        h.tick(10, 0, day=MONDAY)
        row = h.rebalance(FRIDAY)
        self.assertEqual((row["status"], row["n_sells"], row["n_buys"]), ("planned", 2, 3))
        self.assertEqual(h.instance_now().failed_decides, 0)
        h.run(MONDAY, (15, 55))
        self.assertEqual(h.held(), ["N000", "N001", "N020", "N021", "N022"])

    def test_with_the_lane_at_exits_only_the_days_decision_waits_for_the_panels_bars(self):
        h = self.h
        h.table = __import__("dataclasses").replace(h.table, equity=__import__("dataclasses").replace(
            h.table.equity, enabled=False))
        h.book = h.new_book()
        h.market.tape.absent = {("N000", FRIDAY.isoformat())}       # a held name's bar is late
        h.decide(FRIDAY)
        self.assertEqual(h.state.get("eq_decide")["day"], THURSDAY.isoformat(), "no seating pass runs at exits only")
        h.market.tape.absent = set()
        h.tick(16, 31, day=FRIDAY)
        self.assertEqual(h.state.get("eq_decide")["instances"], [KEY])

    def test_a_decide_before_the_cut_off_is_not_late(self):
        h = self.h
        h.tick(9, 40, day=MONDAY)
        self.assertEqual(h.rebalance(FRIDAY)["status"], "planned")
        self.assertEqual(len(h.panel_intents()), 5)

    def test_a_late_standing_target_plans_nothing_and_counts_nothing(self):
        h = self.h
        h.state.put("eq_decide", {"day": FRIDAY.isoformat(), "status": "done"})
        h.tick(10, 0, day=TUESDAY)                                    # Monday's (a hold day's) decide, recorded late
        row = h.rebalance(MONDAY)
        self.assertEqual((row["status"], row["called"], row["n_buys"]), ("late", 0, 0))
        self.assertEqual(h.panel_intents(), [])
        self.assertEqual(h.instance_now().failed_decides, 0)

    def test_the_houses_own_exits_are_planned_as_ever(self):
        h = self.h
        self.universe.end("N003", FRIDAY)                             # a held name left the index
        h.tick(10, 0, day=MONDAY)
        self.assertEqual([(i.kind, i.symbol, i.tag, i.at) for i in h.panel_intents()],
                         [("house_exit", "N003", "ineligible", "open")])
        self.assertEqual(h.rebalance(FRIDAY)["status"], "late")
        h.tick(10, 1, day=MONDAY)
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent], [("sell", "N003")])


# ---------------------------------------------------------------------------------------------------------- D10 (4)
class TheStandingTarget(PanelCase):
    """A buy the venue refused is planned again the next session, and never a second time once held."""

    def setUp(self):
        super().setUp()
        self.h.plan(["N010", "N011", "N012", "N013", "N014"])
        self.h.decide(FRIDAY)

    def test_a_refused_buy_is_planned_again_until_it_is_held(self):
        h = self.h
        h.venue.on_submit = lambda body: setattr(h.venue, "submit_mode", "reject" if body["symbol"] == "N012" else "ok")
        h.run(MONDAY, (9, 26), (9, 31), (9, 33), (9, 34))
        self.assertEqual(h.held(), ["N010", "N011", "N013", "N014"])
        self.assertEqual([i.status for i in h.panel_intents(symbol="N012")], ["missed"])
        h.venue.on_submit = None
        h.venue.submit_mode = "ok"
        h.decide(MONDAY)
        seen = h.child.seen[-1]
        self.assertEqual((seen["called"], seen["standing"]["at"], seen["standing"]["exited"]), (False, "open", []))
        again = h.panel_intents(decided_day=MONDAY.isoformat())
        self.assertEqual([(i.kind, i.symbol, i.usd, i.status) for i in again], [("buy", "N012", D("111.45"), "planned")])
        row = h.rebalance(MONDAY)
        self.assertEqual((row["status"], row["called"], row["standing"], row["n_buys"], row["n_names"]), ("hold", 0, 1, 1, 5))
        self.assertEqual(len(h.child.seen), 2)
        self.assertEqual(h.child.calls, {KEY: 1}, "no program code on a hold day")
        h.run(TUESDAY, (9, 26), (9, 31), (9, 33))
        self.assertEqual(h.held(), ["N010", "N011", "N012", "N013", "N014"])
        h.decide(TUESDAY)
        self.assertIsNone(h.child.seen[-1]["standing"], "every name is held: nothing stands")
        self.assertEqual(h.panel_intents(decided_day=TUESDAY.isoformat()), [])
        row = h.rebalance(TUESDAY)
        self.assertEqual((row["status"], row["standing"], row["n_buys"]), ("hold", 0, 0))

    def test_the_program_reads_why_at_its_next_call(self):
        h = self.h
        h.venue.on_submit = lambda body: setattr(h.venue, "submit_mode", "reject" if body["symbol"] == "N012" else "ok")
        h.run(MONDAY, (9, 26), (9, 31), (9, 33), (9, 34))
        for day in (MONDAY, TUESDAY, WEDNESDAY, dt.date(2026, 10, 15), dt.date(2026, 10, 16)):
            h.decide(day)
        last = h.child.seen[-1]
        self.assertTrue(last["called"], "Friday's close: the next rebalance")
        self.assertTrue([r for r in last["inputs"].rejects if "rejected buy" in r], last["inputs"].rejects)
        self.assertEqual(h.child.calls, {KEY: 2})

    def test_a_name_the_house_exited_is_not_bought_back(self):
        h = self.h
        h.run(MONDAY, (9, 26), (9, 31), (9, 33))
        self.assertEqual(len(h.held()), 5)
        self.universe.end("N012", TUESDAY)                          # it leaves the index: no member two sessions on
        h.decide(MONDAY)
        self.assertEqual([(i.kind, i.symbol, i.tag) for i in h.panel_intents(decided_day=MONDAY.isoformat())],
                         [("house_exit", "N012", "ineligible")])
        h.run(TUESDAY, (9, 26), (9, 31))
        self.assertEqual(h.held(), ["N010", "N011", "N013", "N014"])
        self.universe.spells[next(a for a, s in self.universe.spells.items() if s[-1][0] == "N012")][-1] = \
            ("N012", dt.date(2016, 1, 4), None)                      # and is back: still not bought under that target
        h.decide(TUESDAY)
        self.assertEqual(h.panel_intents(decided_day=TUESDAY.isoformat()), [])
        self.assertIsNone(h.child.seen[-1]["standing"])


# ------------------------------------------------------------------------------------------------------------- B13
class TheLateBar(PanelCase):
    """A held name's bar served at 18:10 is used by the seating pass; one never served is ineligible at the last ask."""

    def setUp(self):
        super().setUp()
        self.basket(at_day=MONDAY)
        self.h.planned(FRIDAY, ["N000", "N001", "N002", "N003", "N004"])
        self.h.state.put("eq_decide", {"day": FRIDAY.isoformat(), "status": "done"})
        self.h.state.execute("UPDATE eq_instances SET last_decided_day=?", (FRIDAY.isoformat(),))
        self.h.market.tape.absent = {("N002", MONDAY.isoformat())}

    def test_a_bar_served_that_evening_is_simply_used(self):
        h = self.h
        out = h.decide(MONDAY)
        self.assertIn("waiting for 1 of the panel's bars", out["panel_bars"])
        self.assertEqual(h.child.seen, [], "a held name's bar is waited for")
        h.run(MONDAY, (16, 31), (16, 45), (16, 59))
        self.assertEqual(h.child.seen, [])
        self.assertEqual(h.said("hold day"), [])
        self.assertEqual(h.state.get("eq_decide")["day"], FRIDAY.isoformat(), "the book's own read waits for a lot's bar too")
        h.tick(17, 1, day=MONDAY)                                     # the grace is over: the House could not ask
        self.assertEqual(h.state.get("eq_decide")["instances"], [], "the day's decision is recorded; the panel is not in it")
        self.assertEqual(h.rebalance(MONDAY)["status"], "failed")
        self.assertEqual([level for level, _ in h.said("could not be asked on the hold day")], ["warning"])
        self.assertEqual(h.instance_now().failed_decides, 0, "A17: a hold day's fetch failure counts toward no exit")
        h.tick(17, 2, day=MONDAY)                                     # the seating pass's first ask of the same close
        calls = len(h.market.bar_calls)
        h.run(MONDAY, (17, 3), (17, 6), (17, 11))
        self.assertEqual(len(h.market.bar_calls), calls, "then asked again every ten minutes, not every minute")
        h.tick(17, 12, day=MONDAY)
        self.assertGreater(len(h.market.bar_calls), calls)
        h.market.tape.absent = set()                                  # 18:10: the bar is served
        h.run(MONDAY, (18, 10), (18, 21))
        row = h.rebalance(MONDAY)
        self.assertEqual((row["status"], row["called"]), ("hold", 0), "the later ask of the same close writes over the failure")
        self.assertEqual(json.loads(row["fetch"])["missing"], 0)
        self.assertEqual(len(h.child.seen), 1)
        self.assertEqual(h.panel_intents(), [], "never a sale of a lot the replay keeps")
        self.assertEqual(h.instance_now().last_decided_day, MONDAY.isoformat())
        self.assertEqual(len(h.said("could not be asked on the hold day")), 1, "said once a day")
        self.assertNotIn(KEY, h.state.get("eq_hold_failed"))
        self.assertIn(KEY, h.state.get("eq_decide")["instances"])
        n002 = next(lot for lot in h.book._lots(instance=KEY) if lot.symbol == "N002")
        self.assertEqual(n002.mark, h.market.close("N002", MONDAY))

    def test_a_bar_never_served_is_read_as_no_bar_at_the_last_ask(self):
        h = self.h
        h.decide(MONDAY)
        h.run(MONDAY, (17, 1), (19, 0), (22, 0))
        h.run(TUESDAY, (2, 0), (8, 0), (8, 45), (9, 5))
        self.assertEqual(h.child.seen, [], "seventeen hours of asking")
        self.assertEqual(h.rebalance(MONDAY)["status"], "failed")
        h.tick(9, 16, day=TUESDAY)                                   # the last ask before the pre-open
        row = h.rebalance(MONDAY)
        self.assertEqual(row["status"], "hold")
        fetch = json.loads(row["fetch"])
        self.assertEqual((fetch["missing"], fetch["late"]), (1, True))
        self.assertEqual([(i.kind, i.symbol, i.tag, i.exec_day, i.at) for i in h.panel_intents()],
                         [("house_exit", "N002", "ineligible", TUESDAY.isoformat(), "open")],
                         "as the Gym reads a store with no bar: not eligible, out at the open")
        self.assertEqual(len(h.said("late and incomplete at the last ask")), 1)
        self.assertEqual(h.instance_now().failed_decides, 0)
        self.assertIsNone(row["audit"], "recorded after 08:30: no morning re-read, and the report counts it")
        h.run(TUESDAY, (9, 26), (9, 31))
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent], [("sell", "N002")])
        self.assertEqual(h.held(), ["N000", "N001", "N003", "N004"])

    def test_two_names_that_are_not_held_do_not_block_the_decide(self):
        h = self.h
        h.market.tape.absent = {("N020", MONDAY.isoformat()), ("N021", MONDAY.isoformat())}
        h.decide(MONDAY)
        self.assertEqual(len(h.child.seen), 1)
        self.assertEqual(json.loads(h.rebalance(MONDAY)["fetch"])["missing"], 2)
        self.assertEqual(h.panel_intents(), [])

    def test_three_missing_names_fail_a_called_decide_once_and_the_seating_pass_asks_again(self):
        h = self.h
        h.state.put("eq_decide", {"day": THURSDAY.isoformat(), "status": "done"})
        h.state.execute("UPDATE eq_instances SET last_decided_day=NULL")
        h.state.execute("DELETE FROM eq_rebalances")
        h.market.tape.absent = {(s, FRIDAY.isoformat()) for s in ("N020", "N021", "N022")}
        h.plan(["N000", "N001", "N002", "N003", "N010"])
        h.decide(FRIDAY)
        h.run(FRIDAY, (17, 1), (17, 12), (17, 23))
        self.assertEqual(h.instance_now().failed_decides, 1, "a rebalance day's failure counts, once a session")
        self.assertEqual((h.rebalance(FRIDAY)["status"], h.rebalance(FRIDAY)["called"]), ("failed", 1))
        self.assertEqual(h.said("hold day"), [])
        h.market.tape.absent = set()
        h.tick(17, 34, day=FRIDAY)
        self.assertEqual(h.rebalance(FRIDAY)["status"], "planned")
        self.assertEqual(h.instance_now().failed_decides, 0, "succeeding it zeroes the count, as any called decide does")
        self.assertEqual(len(h.panel_intents()), 2)


# ------------------------------------------------------------------------------------------------------------- B11
class TheMismatchCancels(PanelCase):
    """The bars a panel decision read are kept and read again at 08:30."""

    def setUp(self):
        super().setUp()
        self.basket(at_day=MONDAY)
        h = self.h
        h.planned(FRIDAY, ["N000", "N001", "N002", "N003", "N004", "N010"])
        h.state.put("eq_decide", {"day": FRIDAY.isoformat(), "status": "done"})
        h.state.execute("UPDATE eq_instances SET last_decided_day=?", (FRIDAY.isoformat(),))
        self.universe.end("N003", MONDAY)                           # a held name left: the House plans it out
        h.decide(MONDAY)                                            # a hold day: N010 stands to be bought
        self.assertEqual(sorted((i.kind, i.symbol) for i in h.panel_intents()),
                         [("buy", "N010"), ("house_exit", "N003")])

    def statuses(self):
        return {(i.kind, i.symbol): i.status for i in self.h.panel_intents()}

    def test_the_same_bars_are_ok_and_a_late_volume_is_a_note(self):
        h = self.h
        h.market.tape.volume_drift = 4321
        out = h.tick(8, 31, day=TUESDAY)
        self.assertEqual(h.rebalance(MONDAY)["audit"], "ok")
        self.assertIn("volumes", out["panel_bars_volume"])
        self.assertEqual(set(self.statuses().values()), {"planned"})
        self.assertEqual([p for k, p in h.events if k == "equity.bars_audit" and p.get("panel")],
                         [{"day": MONDAY.isoformat(), "panel": True, "symbols": 42, "mismatch": 0, "volume": 42, "late": 0,
                           "ok": 1, "hit": 0, "unread": 0}])
        calls = len(h.market.bar_calls)
        h.tick(8, 32, day=TUESDAY)
        self.assertEqual(len(h.market.bar_calls), calls, "read again once")

    def test_a_price_that_differs_cancels_the_buys_of_that_decision(self):
        h = self.h
        h.market.tape.moved = {("N020", "2026-09-15"): 7.77}        # a member's bar reads differently in the morning
        h.tick(8, 31, day=TUESDAY)
        self.assertEqual(h.rebalance(MONDAY)["audit"], "mismatch")
        self.assertEqual(self.statuses(), {("buy", "N010"): "canceled", ("house_exit", "N003"): "planned"},
                         "its buys are cancelled; an exit of a name whose bars agree stands")
        self.assertEqual([level for level, _ in h.said("read differ when read again")], ["error"])
        self.assertEqual(h.instance_now().failed_decides, 0, "a hold day's row counts toward no exit (A17)")
        h.run(TUESDAY, (9, 26), (9, 31), (9, 33))
        self.assertEqual(h.sent("buy"), [])
        h.decide(TUESDAY)
        self.assertIsNotNone(h.child.seen[-1]["standing"], "Friday's target still stands: the hold day's row never did")

    def test_the_exit_of_a_name_whose_own_bars_differ_is_cancelled_too(self):
        h = self.h
        h.market.tape.moved = {("N003", "2026-09-15"): 7.77}
        h.tick(8, 31, day=TUESDAY)
        self.assertEqual(self.statuses(), {("buy", "N010"): "canceled", ("house_exit", "N003"): "canceled"})
        self.assertIn("N003", h.held(), "the lot stays; the next close judges it again")
        h.run(TUESDAY, (9, 26), (9, 31))
        self.assertEqual(h.venue.sent, [])
        h.market.tape.moved = {}
        h.decide(TUESDAY)
        self.assertEqual(sorted((i.kind, i.symbol, i.status) for i in h.panel_intents(decided_day=TUESDAY.isoformat())),
                         [("buy", "N010", "planned"), ("house_exit", "N003", "planned")])

    def test_a_called_decision_that_differs_is_one_failed_decide_and_never_stands(self):
        h = self.h
        h.state.execute("DELETE FROM eq_rebalances WHERE decided_day=?", (MONDAY.isoformat(),))
        h.state.execute("UPDATE eq_rebalances SET bars_sha='b', fetch=?, created_at=?",
                        (json.dumps({"sha": json.loads(self.sha())}), T.at(FRIDAY, 16, 30)))
        h.state.execute("UPDATE eq_instances SET last_decided_day=?", (MONDAY.isoformat(),))
        h.state.execute("UPDATE eq_rebalances SET decided_day=?, exec_day=?", (MONDAY.isoformat(), TUESDAY.isoformat()))
        h.market.tape.moved = {("N020", "2026-09-15"): 7.77}
        h.tick(8, 31, day=TUESDAY)
        self.assertEqual(h.rebalance(MONDAY)["audit"], "mismatch")
        self.assertEqual(h.instance_now().failed_decides, 1, "a rebalance day's mismatch is a failed decide, once")
        h.tick(8, 32, day=TUESDAY)
        self.assertEqual(h.instance_now().failed_decides, 1)
        self.assertIsNone(adapter.standing(h.book._rebalances(KEY), self.cols(), h.book._lots(instance=KEY), TUESDAY))

    def sha(self) -> str:
        kept = adapter.kept(self.root / STORE_DIR, MONDAY)
        return json.dumps(adapter.bars_sha(kept[1], kept[0]))

    def cols(self):
        return adapter.columns(self.root / STORE_DIR, KEY, TUESDAY, held={"N003": THURSDAY.isoformat()})

    def test_unread_by_the_pre_open_is_a_warning_and_nothing_else(self):
        h = self.h
        h.market.tape.fail_at = len(h.market.tape.calls) + 1
        h.tick(8, 31, day=TUESDAY)
        self.assertIsNone(h.rebalance(MONDAY)["audit"])
        h.market.tape.fail_at = len(h.market.tape.calls) + 1
        h.tick(9, 26, day=TUESDAY)
        self.assertEqual(h.rebalance(MONDAY)["audit"], "unread")
        self.assertEqual([level for level, _ in h.said("were not read again")], ["warning"])
        self.assertEqual(set(self.statuses().values()), {"planned"})

    def test_no_kept_file_or_another_fetch_than_the_one_read_is_unread(self):
        h = self.h
        (self.root / STORE_DIR / adapter.LIVE_BARS_DIR / f"{MONDAY.isoformat()}.npz").unlink()
        h.tick(8, 31, day=TUESDAY)
        self.assertEqual(h.rebalance(MONDAY)["audit"], "unread")
        self.assertIn("no kept fetch", h.said("were not read again")[0][1])

    def test_the_books_own_audit_never_charges_a_panel_program(self):
        h = self.h
        h.market.tape.volume_drift = 0
        with mock.patch.object(L.EquityBook, "_panel_audit", side_effect=RuntimeError("boom")):
            hit = h.book._mismatch(MONDAY.isoformat(), ["N003"], h.clock())
        self.assertEqual(hit, [], "its bars are judged by its own audit, never by the lots' read")
        self.assertEqual(set(self.statuses().values()), {"planned"})
        with mock.patch.object(L.EquityBook, "_panel_audit", side_effect=RuntimeError("boom")):
            out = h.tick(8, 31, day=TUESDAY)
        self.assertTrue([e for e in out["errors"] if e.startswith("panel audit")], "its trouble is said")
        self.assertEqual((h.state.get("eq_decision") or {}).get("audit"), "ok", "and the book's own audit goes on")


# ------------------------------------------------------------------------------------------------------------- B15
class PanelLotsAreMarked(PanelCase):
    def setUp(self):
        super().setUp()
        self.lots = self.basket(at_day=THURSDAY)
        self.h.planned(dt.date(2026, 10, 2), ["N000", "N001", "N002", "N003", "N004"])

    def test_every_open_lot_is_marked_at_the_days_raw_close_on_a_day_only_panel_programs_decide(self):
        h = self.h
        self.assertEqual({lot.mark for lot in h.book._lots(instance=KEY)}, {None})
        h.plan(["N000", "N001", "N002", "N003", "N004"])
        h.decide(FRIDAY)
        lots = h.book._lots(instance=KEY)
        for lot in lots:
            self.assertEqual(lot.mark, h.market.close(lot.symbol, FRIDAY), lot.symbol)
            self.assertEqual(lot.marked_at, T.at(FRIDAY, 16, 30))
        value = sum((lot.qty * h.market.close(lot.symbol, FRIDAY) for lot in lots), D(0))
        figures = L.probe_figures(h.state.rows, weights={"etf": D("0.20"), "stock": D("0.40")})
        self.assertEqual(figures.open_risk, D("0.40") * value, "the loss budget's open risk reads the mark")
        self.assertEqual(figures.programs, 1, "one slot a program, however many lots")
        self.assertEqual(L.invested(h.state.rows), value)
        self.assertAlmostEqual(h.child.seen[-1]["inputs"].equity, max(float(value), 557.25), places=6)
        self.assertEqual([round(p["value"], 6) for p in h.child.seen[-1]["inputs"].positions],
                         [round(float(lot.qty * lot.mark), 6) for lot in lots], "the ctx is built after the marks")

    def test_a_hold_day_marks_them_too_and_a_late_decide_never_marks_a_lot_bought_since(self):
        h = self.h
        h.state.put("eq_decide", {"day": FRIDAY.isoformat(), "status": "done"})
        new = h.seed("N010", opened=TUESDAY, at_day=TUESDAY)
        h.tick(10, 0, day=TUESDAY)                                   # Monday's decide, late
        marks = {lot.symbol: lot.mark for lot in h.book._lots(instance=KEY)}
        self.assertIsNone(marks["N010"], "bought since Monday's close: no price from before it was bought")
        self.assertEqual(marks["N000"], h.market.close("N000", MONDAY))
        self.assertIsNone(h.book._lot(new.lid).marked_at)


# -------------------------------------------------------------------------------------------------------- B6, B14
class AHeldNameThatLeftKeepsItsColumn(PanelCase):
    def setUp(self):
        super().setUp()
        self.basket(at_day=MONDAY)
        h = self.h
        h.planned(dt.date(2026, 10, 2), ["N000", "N001", "N002", "N003", "N004"])
        h.plan(["N000", "N001", "N002", "N003", "N004"])
        h.decide(FRIDAY)
        self.friday = h.child.seen[-1]

    def col(self, seen, symbol):
        lid = next(lot.lid for lot in self.h.book._lots(instance=KEY, open_only=False) if lot.symbol == symbol)
        return next(p["col"] for p in seen["inputs"].positions if p["lid"] == lid)

    def test_its_column_its_id_its_mark_and_its_exit(self):
        h = self.h
        self.universe.end("N003", MONDAY)                           # no member from Monday on
        h.decide(MONDAY)
        monday = h.child.seen[-1]
        row = h.rebalance(MONDAY)
        self.assertEqual(json.loads(row["extra"]), ["N003"], "what rebuilds the decision's columns")
        self.assertEqual(monday["slots"][self.col(monday, "N003")], self.friday["slots"][self.col(self.friday, "N003")],
                         "the id its lot was bought under")
        self.assertFalse(monday["inputs"].elig0[self.col(monday, "N003")], "never a candidate")
        self.assertEqual(len(monday["inputs"].positions), 5)
        n003 = next(lot for lot in h.book._lots(instance=KEY) if lot.symbol == "N003")
        self.assertEqual(n003.mark, h.market.close("N003", MONDAY), "a name that left is still marked at its close")
        exits = h.panel_intents(kind="house_exit")
        self.assertEqual([(i.symbol, i.tag, i.at, i.exec_day, i.lid) for i in exits],
                         [("N003", "ineligible", "open", TUESDAY.isoformat(), n003.lid)])
        self.assertIn("not eligible at the close of 2026-10-12", exits[0].why)
        h.decide(MONDAY, minutes=(31, 32))
        self.assertEqual(len(h.panel_intents(kind="house_exit")), 1, "planned once")
        h.run(TUESDAY, (9, 26), (9, 31))
        closed = h.book._lot(n003.lid)
        self.assertEqual((closed.status, closed.reason, closed.exit_at), ("closed", "ineligible", "open"))
        # It keeps a column until the program has read its close: the next CALLED ctx names it, tagged for what it was.
        for day in (TUESDAY, WEDNESDAY, dt.date(2026, 10, 15)):
            h.decide(day)
            self.assertEqual(json.loads(h.rebalance(day)["extra"]), ["N003"])
        h.decide(dt.date(2026, 10, 16))
        last = h.child.seen[-1]
        self.assertTrue(last["called"])
        self.assertEqual([(c["lid"], c["reason"], c["tag"]) for c in last["inputs"].closed],
                         [(n003.lid, "house", "ineligible")])
        h.decide(dt.date(2026, 10, 19))
        self.assertEqual(json.loads(h.rebalance(dt.date(2026, 10, 19))["extra"]), [], "read: its column is gone")

    def test_the_house_exit_at_the_open_displaces_the_programs_close_sell(self):
        h = self.h
        h.state.execute("UPDATE eq_instances SET last_decided_day=NULL")
        h.state.execute("DELETE FROM eq_rebalances WHERE decided_day=?", (FRIDAY.isoformat(),))
        h.state.put("eq_decide", {"day": THURSDAY.isoformat(), "status": "done"})
        self.universe.end("N003", FRIDAY)
        h.book._panel = {}                                            # (the day's columns are built once a day)
        h.plan(["N000", "N001", "N002", "N004", "N010"], "close")    # the program sells N003 at the close itself
        h.decide(FRIDAY, minutes=(40,))
        got = {(i.kind, i.symbol): (i.status, i.at) for i in h.panel_intents()}
        self.assertEqual(got[("sell", "N003")][0], "refused", "the Gym sells a lot the House exits at the open")
        self.assertEqual(got[("house_exit", "N003")], ("planned", "open"))
        self.assertEqual(got[("buy", "N010")], ("planned", "close"))
        self.assertIn("leaves at the open by the House's rule (ineligible", h.panel_intents(kind="sell")[0].why)

    def test_the_programs_own_open_sell_stands(self):
        h = self.h
        h.state.execute("UPDATE eq_instances SET last_decided_day=NULL")
        h.state.execute("DELETE FROM eq_rebalances WHERE decided_day=?", (FRIDAY.isoformat(),))
        h.state.put("eq_decide", {"day": THURSDAY.isoformat(), "status": "done"})
        self.universe.end("N003", FRIDAY)
        h.book._panel = {}
        h.plan(["N000", "N001", "N002", "N004", "N010"], "open")
        h.decide(FRIDAY, minutes=(40,))
        self.assertEqual([(i.kind, i.status) for i in h.panel_intents(symbol="N003")], [("sell", "planned")])

    def test_a_lid_of_another_program_is_never_exited(self):
        h = self.h
        other = h.instance("seed-overnight-spy")
        spy = h.lot(other, "SPY", "0.1", "600")
        n = h.book._panel_ineligible(h.instance_now(), MONDAY, {"ineligible": [spy.lid, 9999, "x", None]}, adapter)
        self.assertEqual(n, 0)
        self.assertEqual(h.intents(kind="house_exit"), [])


# -------------------------------------------------------------------------------------------------------------- B2
class APanelAnswerThatFailedCountsOnce(PanelCase):
    """The panel answer's `failed`, `missing` and `error` are read exactly as the equity kind's: one failed decide a
    session, in E1's two kinds. And the captain's A17 for a hold day."""

    def setUp(self):
        super().setUp()
        self.basket(at_day=FRIDAY)
        self.h.planned(dt.date(2026, 10, 2), ["N000", "N001", "N002", "N003", "N004"])
        self.h.plan(["N000", "N001", "N002", "N003", "N010"])

    def test_the_program_failed_the_session_is_spent(self):
        h = self.h
        h.child.program_fails = {KEY}
        out = h.decide(FRIDAY)
        self.assertIn("its own decide failed: its decide raised", out["decide_failed"][KEY])
        inst = h.instance_now()
        self.assertEqual((inst.failed_decides, inst.last_decided_day), (1, FRIDAY.isoformat()))
        row = h.rebalance(FRIDAY)
        self.assertEqual((row["status"], row["called"], bool(row["ctx_sha"])), ("failed", 1, True))
        h.run(FRIDAY, (16, 31), (16, 45), (17, 30))
        self.assertEqual(h.child.calls, {KEY: 1}, "asked once: as the Gym, a failed call is a spent session")
        self.assertEqual(h.instance_now().failed_decides, 1)
        self.assertEqual(h.panel_intents(), [])
        self.assertEqual(h.state.get("eq_decide")["instances"], [KEY])

    def test_the_house_could_not_ask_once_a_session_and_asks_again(self):
        h = self.h
        for attr in ("lost", "no_ctx"):
            with self.subTest(attr):
                h.state.execute("UPDATE eq_instances SET last_decided_day=NULL, failed_decides=0")
                h.state.put("eq_failed", {})
                h.state.put("eq_decide", {"day": THURSDAY.isoformat(), "status": "done"})
                h.book._seat_tried = float("-inf")
                setattr(h.child, attr, {KEY})
                loads = len(h.child.loads)
                h.decide(FRIDAY)
                self.assertEqual(h.instance_now().failed_decides, 1)
                self.assertIsNone(h.instance_now().last_decided_day, "not spent: it may be asked again for the same close")
                h.run(FRIDAY, (16, 31), (16, 35))
                self.assertEqual(h.instance_now().failed_decides, 1, "one failed decide a session")
                setattr(h.child, attr, set())
                h.tick(16, 41, day=FRIDAY)
                inst = h.instance_now()
                self.assertEqual((inst.failed_decides, inst.last_decided_day), (0, FRIDAY.isoformat()))
                self.assertEqual(h.rebalance(FRIDAY)["status"], "planned")
                if attr == "lost":
                    self.assertGreater(len(h.child.loads), loads, "the child lost its runner: loaded again")
                h.state.execute("DELETE FROM eq_intents")
                h.state.execute("DELETE FROM eq_rebalances WHERE decided_day=?", (FRIDAY.isoformat(),))

    def test_the_decider_failing_fails_every_job_of_its_kind_once(self):
        h = self.h
        h.child.fail = True
        out = h.decide(FRIDAY)
        self.assertIn("the decider: RuntimeError", out["decide_failed"][KEY])
        self.assertEqual(h.instance_now().failed_decides, 1)

    def test_two_failed_rebalance_days_exit_its_lots_and_hold_days_between_do_not_reset_the_count(self):
        h = self.h
        h.child.program_fails = {KEY}
        h.decide(FRIDAY)
        self.assertEqual(h.panel_intents(kind="house_exit"), [])
        h.child.program_fails = set()
        for day in (MONDAY, TUESDAY, WEDNESDAY, dt.date(2026, 10, 15)):
            h.decide(day)
            self.assertEqual(h.instance_now().failed_decides, 1, "a hold day that was asked does not reset it")
        h.child.program_fails = {KEY}
        h.decide(dt.date(2026, 10, 16))
        self.assertEqual(h.instance_now().failed_decides, 2)
        exits = h.panel_intents(kind="house_exit")
        self.assertEqual(sorted(i.symbol for i in exits), ["N000", "N001", "N002", "N003", "N004"])
        self.assertEqual({i.tag for i in exits}, {"house"})
        self.assertEqual([level for level, _ in h.said("failed 2 called decides in a row")], ["error"])

    def test_a_hold_day_the_house_could_not_ask_counts_toward_no_exit(self):
        h = self.h
        h.decide(FRIDAY)
        h.child.fail = True
        for n, day in enumerate((MONDAY, TUESDAY), start=1):
            h.run(day, (9, 26), (9, 31), (9, 33), (9, 34))
            h.decide(day)
            self.assertEqual(h.instance_now().failed_decides, 0, "A17")
            self.assertEqual(h.state.get("eq_hold_failed")[KEY], {"day": day.isoformat(), "run": n})
            self.assertEqual(h.rebalance(day)["status"], "failed")
        self.assertEqual([level for level, _ in h.said("could not be asked on the hold day")], ["warning", "error"],
                         "critical on the second in a row")
        self.assertEqual(h.panel_intents(kind="house_exit"), [], "nothing is sold")
        self.assertEqual(h.held(), ["N000", "N001", "N002", "N003", "N010"])

    def test_its_max_hold_exits_still_run_on_a_hold_day_that_failed(self):
        h = self.h
        h.child.needs[KEY] = {**NEEDS, "max_hold_sessions": 5}
        h.decide(FRIDAY)
        h.run(MONDAY, (9, 26), (9, 31), (9, 33), (9, 34))
        h.state.execute("UPDATE eq_lots SET opened_day='2026-10-05' WHERE opened_day=?", (THURSDAY.isoformat(),))
        h.child.fail = True
        h.decide(MONDAY)
        self.assertEqual(h.rebalance(MONDAY)["status"], "failed")
        self.assertEqual(h.instance_now().failed_decides, 0)
        exits = h.panel_intents(kind="house_exit")
        self.assertEqual({i.tag for i in exits}, {"max_hold"}, "held 5 sessions by Tuesday's open")
        self.assertEqual(sorted(i.symbol for i in exits), ["N000", "N001", "N002", "N003"], "N010 was bought today")

    def test_a_day_the_house_never_decided_counts_only_a_rebalance_day(self):
        h = self.h
        h.book._decide_failed(MONDAY, h.clock(), "no decide ran before the next session's close window")
        self.assertEqual(h.instance_now().failed_decides, 0, "Monday was a hold day")
        h.book._decide_failed(FRIDAY, h.clock(), "no decide ran before the next session's close window")
        self.assertEqual(h.instance_now().failed_decides, 1)


# ------------------------------------------------------------------------------------------------------------- B10
class TheBandRulesReadByDate(PanelCase):
    def closed(self, lid, symbol, exit_day, cash, opened="2026-10-06"):
        lot = L.Lot(lid, KEY, FAMILY, 1, "equity", symbol, "stock", qty=D(0), opened_qty=D(1), entry_px=D("111.45"),
                    entry_notional=D("111.45"), entry_at="open", opened_at=float(lid), opened_day=opened,
                    status=L.LOT_CLOSED, exit_px=D("110"), exit_at="open", exit_day=exit_day, closed_at=100.0 + lid,
                    cash=D(cash), probe=True)
        self.h.book._save_lot(lot)

    def test_a_panel_instances_record_is_one_observation_a_close_date(self):
        h = self.h
        for k in range(1, 6):
            self.closed(k, f"N00{k}", "2026-10-13", "-3.34")
        for k in range(6, 11):
            self.closed(k, f"N01{k - 6}", "2026-10-20", "-3.34", opened="2026-10-13")
        twins = {f"eq:{k}": {"status": "priced", "gap_bp": -22.0} for k in range(1, 6)}
        with mock.patch.object(type(h.families), "twins", lambda self: twins, create=True):
            record = h.book._record_of(FAMILY, 1, {**panel_row(), "validation_r_sd": 0.04}, refetch=True)
        self.assertEqual(record.n, 2)
        self.assertEqual(record.returns, (float(D("-16.70") / D("557.25")),) * 2)
        self.assertEqual(record.twin_gaps_bp, (-22.0,))
        self.assertEqual((record.pnl, record.realized_net, record.validation_r_sd), (D("-33.40"), D("-33.40"), 0.04))
        self.assertIsNone(record.bh_pnl, "not read before the record holds the dates sizing up needs")
        self.assertFalse([c for c in h.market.bar_calls if c[0] == ("SPY",)], "and SPY is not fetched before then")
        from league.equity import bands as B

        self.assertIsNone(B.edm1(record, h.table.equity), "by lot both EDM1 legs would fire")

    def test_the_buy_and_hold_is_one_spy_fetch_once_sizing_up_needs_it(self):
        h = self.h
        h.table = __import__("dataclasses").replace(h.table, equity=__import__("dataclasses").replace(
            h.table.equity, sized_min_trades=2))
        h.book = h.new_book()
        self.closed(1, "N001", "2026-10-13", "1")
        self.closed(2, "N002", "2026-10-20", "2", opened="2026-10-13")
        record = h.book._record_of(FAMILY, 1, panel_row(), refetch=True)
        spy = [c for c in h.market.bar_calls if c[0] == ("SPY",)]
        self.assertEqual(spy, [(("SPY",), "1Day", "2026-10-05", "2026-10-21", "all")], "ONE fetch, one basis")
        closes = adapter.spy_closes(h.market, dt.date(2026, 10, 5), dt.date(2026, 10, 20))
        self.assertEqual(record.bh_pnl, D("111.45") * (closes["2026-10-13"] / closes["2026-10-05"] - 1)
                         + D("111.45") * (closes["2026-10-20"] / closes["2026-10-12"] - 1))
        self.assertIsNone(h.book._record_of(FAMILY, 1, panel_row()).bh_pnl, "a sizing at send time never reads the vendor")

    def test_no_adapter_no_record_and_no_band_moves(self):
        h = self.h
        h.book._adapters["panel"] = None
        with self.assertRaises(RuntimeError):
            h.book._record_of(FAMILY, 1, panel_row())
        out: dict = {}
        self.assertTrue(h.book._sync_instances(h.clock(), FRIDAY, out))
        self.assertEqual(h.families.rows[FAMILY]["band"], "probe", "no move on a rule that cannot be read")
        self.assertEqual(h.book._sleeve_share(h.instance_now()), D("0.25"))


if __name__ == "__main__":
    unittest.main()
