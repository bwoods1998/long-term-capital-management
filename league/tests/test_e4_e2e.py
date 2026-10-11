"""THE PANEL LANE END TO END (release E4, integration): one bred panel program from its birth to the Done meter, through
every package's real code, with only the model router, the venue and its market data faked.

The path (league/xs/E4_INTERFACES.md's packages, in order):
1. the data: a synthetic point-in-time universe and panel store (C's `league.xs.synth.planted_panel`: C's writers, a
   test salt, 60 made-up members with yearly churn on 11 sector funds, a planted reversal edge), as package A's two jobs
   leave them on the House; the nightly I6 (A's `equity_panel.i6_check`) on the fake venue's bars, its verdict written
   into the manifest as the job writes it;
2. birth: E2's equity pass (`Architect.equity_pass`) shows the PANEL block and bears the architect's panel proposal
   through G's `elane_xs.admit`: structure "panel", lane "equity", no root, its card and its first program;
3. Train: E2's researcher forwards the family to `elane_xs.step`: the Train bar equity-xs-v1 on D's panel runner in a
   REAL decider child PROCESS (the decider's "panel" kind; C's store, ctx and program: the program sees salted slots,
   never a ticker), 200 matched placebos a run, the restart check, the style reading (the captain's A22 (1)), then the
   equity review and its audit under the panel rubric on two models (A22 (3));
4. Validation: `elane.validate` forwards to `elane_xs.validate`: E's pre-check on the residual, both Train series
   kept (the pre-registration's duty of the House);
5. the one sealed look: `elane.look` forwards to `elane_xs.look` under the screen XS1 with a FAKE receipt pinned (E's
   fixture, landed as the real one lands: the file and its pin): E's exact floor, the look run with 999 matched
   placebos under E1's capability, `screen.verdict` and the receipt's sentence; the family becomes a Candidate proven
   on the xs identity (E's `adopt_xs` proof, G's `bands.current_xs_evaluator`);
6. the seat: the lane's effective mode is "live" only with the universe deploy in force, the I6 held and the twin
   marker written; the EquityBook reads the swarm's panel row, seats the Candidate at Probe and makes it an instance of
   kind "panel" (H's patch 12);
7. a live week through E1's EquityBook and H's adapter, sized by MONEY'S REAL RULES: Friday's decision (five names),
   Monday's open (five limit buys), four hold days (no program code runs), Friday's rotation decision, and the next
   Monday's open (five sales, then five buys), every morning's audit of the bars a decision read;
8. the readers: B's replay twin of every closed lot at the panel's own half-spread, the Done meter and H's panel lines
   in the direction report, XS1's sentence beside every live panel trade;
9. the way back: what stops the lane overnight holds the morning's entries; the lane's mode put down one step
   retires the seated program on the lane's own word, and its lots leave at the next open; a switch file that cannot
   be read retires nobody.

WHAT THE TEST WRITES IN ANOTHER PACKAGE'S PLACE, and only that: the contamination probe's permit with the panel strata
(package B's patch 18: the probe's job writes it, league/ops/contam_xs.py; no model is asked here, and
league/tests/test_contam_xs.py holds the job), and the twin marker (package J's, on release E3: owed). Without
either the lane stops where its rule says (no look; no live seat); `TheLaneStopsWhereItsRuleSays` holds both.

The market is synthetic (no figure here is a market result): the store's prices are seeded pseudo-random walks with a
planted edge strong enough that the program passes its look, and the six sessions after the store's last are invented
here. The money table is the constitution's own with ONE change: its stock universe also lists the panel's made-up
tickers (what the universe release R-E4b does for the real ones); no bound, share, weight or cap is another's."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import pickle
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from typing import Any, Iterator, Mapping
from unittest import mock
from zoneinfo import ZoneInfo

try:
    import numpy as np
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.equity import LANES
    from league.equity import live as L
    from league.equity import store as ES
    from league.equity.families import EquityFamilies
    from league.live import decider as DEC
    from league.live import money as M
    from league.live import real as R
    from league.live.paper import STOCK_BUY_KEY, STOCK_BUY_WITNESSES, STOCK_SELL_KEY, STOCK_WITNESSES, StockPaperProof
    from league.live.state import LiveState
    from league.ops import dlane_report as DR
    from league.ops import equity_panel as EP
    from league.ops import forward_db, forward_register, forward_xs
    from league.ops import twins as TW
    from league.swarm import bands, elane, elane_folds, elane_xs
    from league.swarm import settings as settings_mod
    from league.swarm.architect import Architect
    from league.swarm.elane_train import EquityResearcher
    from league.swarm.gate import Gate, run_sha
    from league.swarm.store import SwarmStore
    from league.swarm.tournament import Tournament
    from league.tests import REAL_POLICY_PATH
    from league.tests.elane_e2_fakes import FakeRouter, answer, review_answer
    from league.tests.test_equity_book import Clock, Market, Venue, at, iso
    from league.tests.test_xs_book import as_the_client
    from league.xs import book as xbook
    from league.xs import config as xconfig
    from league.xs import identity as xidentity
    from league.xs import runner as xrunner
    from league.xs import screen as xscreen
    from league.xs import store as xstore
    from league.xs import synth

NY = ZoneInfo("America/New_York")
SLUG = "rev-week"
SUNDAY = dt.date(2026, 10, 11)
#: The store's last session, then the six invented ones: a week, and the Monday and Tuesday after it.
FRIDAY = dt.date(2026, 10, 9)
WEEK = tuple(dt.date(2026, 10, d) for d in (12, 13, 14, 15, 16))
NEXT_MONDAY, NEXT_TUESDAY, NEXT_WEDNESDAY = dt.date(2026, 10, 19), dt.date(2026, 10, 20), dt.date(2026, 10, 21)
E = D("2229")
#: The synthetic panel (invented): names ranked by last week's loss earn `edge_year` more than their cell-mates.
PANEL = {"edge_year": 1.0, "signal": "reversal", "n_assets": 60}
FAKE_RECEIPT = Path(__file__).resolve().parent / "fixtures" / "equity_screen_xs_fake.json"
#: What the captain's set_swarm.py would write on the House for the lane to trade: every switch of the path.
SWITCHES = {"elane": {"mode": "gate", "birth_share": 0.25, "panel": {"mode": "live"}}, "dlane": {"mode": "gate"}}
ROUTE = "sail:pro_asap"

#: The architect's program: each week the five names that fell most over the last five sessions, at equal weights.
PROGRAM = '''import math

NEEDS = {"panel": "sp500", "history": 20, "max_names": 5, "rebalance": "weekly", "weekday": 0, "max_hold_sessions": 30}
PARAMS = {"back": 5}


def decide(ctx):
    back = int(ctx.params["back"])
    scored = []
    for row in range(ctx.n):
        total = 0.0
        ok = True
        for value in ctx.ret[row][-back:]:
            v = float(value)
            if v != v:
                ok = False
                break
            total += v
        if ok:
            scored.append((total, int(ctx.ids[row])))
    scored.sort()
    picked = [slot for _, slot in scored[:5]]
    if len(picked) < 5:
        return {"hold": True}
    return {"target": {slot: 0.2 for slot in picked}, "at": "open"}
'''

CARD = {"lane": "equity", "structure": "panel", "panel": "sp500", "max_names": 5, "rebalance": "weekly", "weekday": 0,
        "hypothesis": "Liquidity providers are paid to absorb a week's selling in single names, and the names that "
                      "fell most against their sector rebound (an invented test card; Lehmann 1990).",
        "mechanism_class": "reversal_liquidity", "inputs": ["underlying_price", "cross_asset"], "holding": "days_4_10",
        "cost": {"hurdle": 0.0006, "why": "two half-spreads and the sell fees on a liquid large-cap name"},
        "comparison": "matched random portfolios from the same cells on the same days",
        "falsification": "the residual's sum at or below zero at 1.5x the half-spread over the seen Train years"}
PROPOSAL = {"slug": SLUG, "lane": "equity", "structure": "panel", "panel": "sp500", "agenda": "xs_reversal",
            "max_names": 5, "rebalance": "weekly", "weekday": 0,
            "mechanism": "Liquidity providers are paid to absorb a week of selling in single names: the losers of a week "
                         "against their sector rebound over the next.",
            "rejection": "the residual at or below zero at 1.5x the half-spread",
            "sketch": "rank the week's losers and hold the five worst for a week", "card": CARD, "program": PROGRAM}


def strings(value: Any, depth: int = 0) -> Iterator[str]:
    """Every str inside a message to the decider's child (keys and values, through containers, dataclasses and plain
    objects), and an AssertionError for an array that could carry one (a str or object dtype)."""
    if depth > 12:
        raise AssertionError("a message nested deeper than any the decider sends")
    if isinstance(value, str):
        yield value
    elif isinstance(value, bytes):
        return
    elif isinstance(value, np.ndarray):
        assert value.dtype.kind in "biuf", f"an array of dtype {value.dtype} could carry a name"
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from strings(key, depth + 1)
            yield from strings(item, depth + 1)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from strings(item, depth + 1)
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            yield from strings(getattr(value, field.name), depth + 1)
    elif hasattr(value, "__dict__"):
        yield from strings(vars(value), depth + 1)


class _Recording:
    """A decider that keeps what it sends its child (`messages`: each as the child unpickles it)."""

    def _ask(self, message: Any, deadline: float) -> dict:
        self.messages.append(pickle.loads(pickle.dumps(message)))
        return super()._ask(message, deadline)  # type: ignore[misc]


if HAVE:
    class ChildProcess(_Recording, DEC.Decider):
        """The decider's child as a real process, as the swarm's panel evidence child is on the House (off a root
        House it runs unisolated, which a test may ask for), its hash seed pinned as `elane_xs.runner` pins it."""

        hash_seed = elane.EVIDENCE_HASH_SEED

        def __init__(self) -> None:
            super().__init__(python=sys.executable, allow_unisolated=True)
            self.messages: list[Any] = []

    class InProcess(_Recording, DEC.InlineDecider):
        """The live book's decider, in this process (the child's own handler, its pickle and JSON round trips)."""

        def __init__(self) -> None:
            super().__init__()
            self.messages: list[Any] = []

    class PanelMarket(Market):
        """The fake venue's market data over the panel store's own bars and the sessions invented after them: SIP
        snapshots a half-spread either side of the session's official open (before noon) or close, and 1Day bars the
        venue serves once a session has closed. EVERY ANSWER IS HANDED AS THE HOUSE'S VENUE CLIENT HANDS IT
        (`as_the_client`: the venue's JSON bytes decoded by `ltcm.adapters.decode`, every price a Decimal and never a
        float), so every reader on the live path, the panel's and the book's, is held to the rows it really gets
        (the review's regress-1: with floats here the whole week passed while the real rows placed no bar)."""

        HALF_SPREAD = D("0.0003")

        def __init__(self, clock: Clock, rows: dict[str, dict[str, list[dict]]]):
            super().__init__(clock)
            self.bar_rows = rows

        def official(self, symbol: str, day: dt.date, point: str) -> D:
            for row in reversed(self.bar_rows["raw"][symbol]):
                if row["t"][:10] == day.isoformat():
                    return D(str(row["o" if point == "open" else "c"]))
                if row["t"][:10] < day.isoformat():
                    return D(str(row["c"]))
            raise KeyError(symbol)

        def quote(self, symbol: str) -> tuple[D, D]:
            moment = dt.datetime.fromtimestamp(self.clock(), NY)
            px = self.official(symbol, moment.date(), "open" if moment.hour < 12 else "close")
            return (px * (1 - self.HALF_SPREAD)).quantize(D("0.01")), (px * (1 + self.HALF_SPREAD)).quantize(D("0.01"))

        def stocks(self, symbols):
            self.calls += 1
            out = {}
            for symbol in symbols:
                bid, ask = self.quote(symbol)
                stamp = iso(self.clock() - 1)
                out[symbol] = {"latestQuote": {"bp": float(bid), "ap": float(ask), "t": stamp},
                               "latestTrade": {"p": float((bid + ask) / 2), "t": stamp}}
            return as_the_client(out)

        def served(self) -> str:
            """The last session whose 1Day bar the venue serves now: today's from the close on."""
            moment = dt.datetime.fromtimestamp(self.clock(), NY)
            return (moment.date() if moment.hour >= 16 else moment.date() - dt.timedelta(days=1)).isoformat()

        def bars(self, symbols, *, timeframe, start, end=None, adjustment="raw"):
            self.bar_calls.append((tuple(symbols), timeframe, start, end, adjustment))
            last = self.served()
            return as_the_client({s: [dict(r) for r in self.bar_rows[adjustment].get(s, [])
                                      if start[:10] <= r["t"][:10] <= last and (end is None or r["t"][:10] < end[:10])]
                                  for s in symbols})

        def extend(self, day: dt.date, move) -> None:
            """One invented session for every symbol, on the cent grid (so the adjusted row is the raw one: no event
            follows the store's last day): it opens a tenth of a percent above the last close and closes `move(symbol)`
            above its open."""
            for symbol, rows in self.bar_rows["raw"].items():
                last = rows[-1]
                o = round(last["c"] * 1.001, 2)
                c = round(o * (1.0 + move(symbol)), 2)
                row = {"t": synth._stamp(day), "o": o, "h": round(max(o, c) * 1.001, 2),
                       "l": round(min(o, c) * 0.999, 2), "c": c, "v": last["v"]}
                rows.append(dict(row))
                self.bar_rows["all"][symbol].append(dict(row))

    class Gateway:
        """The gateway's bars route over the same market, as the data job's nightly I6 asks it (the venue's `end` day
        is inclusive there, as E1's data job reads it). Its numbers are floats, as the ops jobs' own gateway reader
        hands them (league/ops/context.py `Gateway`: plain json.loads), where the live book's client hands Decimals:
        the nightly I6 here compares the one with the other, as on the House."""

        def __init__(self, market: "PanelMarket"):
            self.market, self.requests = market, []

        def get(self, path: str, params=None):
            assert path == EP.BARS, path
            params = dict(params or {})
            self.requests.append(params)
            last = min(self.market.served(), params["end"][:10])
            rows = self.market.bar_rows[params["adjustment"]]
            return {"bars": {s: [dict(r) for r in rows.get(s, []) if params["start"][:10] <= r["t"][:10] <= last]
                             for s in params["symbols"].split(",")}, "next_page_token": None}


@unittest.skipUnless(HAVE, "numpy not installed")
class ThePanelLaneEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.root.mkdir()
        # A RELEASE AS THE HOUSE READS IT: the committed policy.json with the FAKE receipt landed as the real one lands
        # (the file at docs/benchmarks/equity_screen_xs_1.json and `screen.pin` of it in elane.screens.equity_xs).
        self.repo = Path(self.tmp.name) / "release"
        (self.repo / "docs" / "benchmarks").mkdir(parents=True)
        shutil.copyfile(FAKE_RECEIPT, self.repo / xscreen.RECEIPT_PATH)
        policy = json.loads(REAL_POLICY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(policy["elane"]["panel"]["mode"], "off", "the lane ships off")
        policy["elane"]["screens"]["equity_xs"] = xscreen.pin(self.repo / xscreen.RECEIPT_PATH)
        (self.repo / "policy.json").write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
        for patcher in (mock.patch.object(settings_mod, "POLICY_PATH", self.repo / "policy.json"),
                        mock.patch.object(elane, "REPO", self.repo)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.forget)
        self.clock = Clock(at(SUNDAY, 12, 0))                       # Sunday Oct 11: the deploy, the research, the look
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.store_root = synth.planted_panel(self.root / elane_xs.STORE_DIR, gate=True, live_from=dt.date(2026, 9, 1),
                                              **PANEL)
        self.switch(SWITCHES)
        self.router = FakeRouter(self.model)
        self.proposals: list[dict] = []
        self.child = ChildProcess()
        self.addCleanup(self.child.close)
        self.runner = xrunner.Isolated(self.child, self.store_root, nice=None)
        self.universe = xstore.Universe(self.store_root)
        self.tickers = {symbol for asset in json.loads((self.store_root / "universe" / "assets.json").read_text())
                        .values() for symbol in [asset["symbol"], *(row[0] for row in asset["spells"])]
                        if symbol not in xconfig.REF}
        self.assertGreater(len(self.tickers), 60, "the members, and the names that joined and left")

    # ------------------------------------------------------------------------------------------------ the fixtures
    @staticmethod
    def forget() -> None:
        """Drop what `elane_xs` remembers of a state root between its reads (the mode, the files): a test changes a
        switch or a file and reads again at once."""
        with elane_xs._cache_lock:
            elane_xs._mode_cache.clear()
            elane_xs._json_cache.clear()

    def switch(self, layer: Mapping[str, Any]) -> dict:
        """The box's swarm.json (the captain's switches), and the settings the House then reads."""
        (self.root / "swarm.json").write_text(json.dumps(layer), encoding="utf-8")
        self.forget()
        self.settings = settings_mod.load(self.root)
        return self.settings

    def model(self, call: Mapping[str, Any]) -> dict:
        """The model router, scripted: the architect's answer to the equity pass, and a passing equity review and
        audit, each from its own model."""
        key = str(call.get("key") or "")
        if ":births:" in key:
            rows, self.proposals = self.proposals, []
            return answer(rows)
        return review_answer("pass", model="k3_balanced" if ":audit:" in key else "pro_balanced")

    def manifest(self, **facts: Any) -> dict:
        """panel/PANEL_MANIFEST.json with `facts` written over it, as the panel job writes its own facts each night."""
        path = self.store_root / "panel" / "PANEL_MANIFEST.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc.update(facts)
        path.write_text(json.dumps(doc), encoding="utf-8")
        self.forget()
        return doc

    def twin_marker(self, through: dt.date) -> None:
        """PACKAGE J'S FILE (owed after release E3), written here as its nightly run will: ids and days only."""
        (self.store_root / xbook.TWINS_FILE).write_text(json.dumps(
            {"version": xbook.TWINS_VERSION, "through": through.isoformat(), "at": "2026-10-10T01:00:00Z",
             "instances": {}}), encoding="utf-8")
        self.forget()

    def probe_file(self) -> None:
        """THE PROBE'S PERMIT with the panel strata (package B's patch 18 writes it from the probe's job:
        league/ops/contam_xs.py), written here in its shape: for the birth route, two words a stratum and era on
        P4-P6, no count and no rate."""
        cell = {"readable": True, "recalled": False}
        row = {"model": "fake-model", "at": "2026-10-10T00:20:00Z",
               "cells": {s: {"2016-24": dict(cell), "2025": dict(cell)} for s in elane_xs.PROBE_STRATA}}
        (self.root / elane_xs.PROBE_FILE).write_text(json.dumps({"version": elane_xs.PROBE_VERSION,
                                                                 "routes": {ROUTE: row}}), encoding="utf-8")
        self.forget()

    def market(self) -> "PanelMarket":
        """The fake venue's market: every asset's bars as the panel store holds them (read as the store's writer
        reads them back: the venue knows its own prices), the last 300 sessions."""
        panel = EP.load_panel(self.store_root)
        days = np.array([ES.ordinal(d) for d in panel.days], dtype=np.int32)
        keep = slice(len(panel.days) - 300, len(panel.days))
        rows: dict[str, dict[str, list[dict]]] = {"raw": {}, "all": {}}
        for col, aid in enumerate(panel.aids):
            try:
                symbol = self.universe.symbol(aid, FRIDAY)
            except KeyError:
                continue
            for name in rows:
                rows[name][symbol] = synth.bar_rows(days[keep], np.asarray(panel.raw[keep, col]),
                                                    np.asarray(panel.adj[keep, col]), adjustment=name)
        return PanelMarket(self.clock, rows)

    # ------------------------------------------------------------------------------------------- the swarm's part
    def born(self) -> dict:
        """2. E2's equity pass bears the architect's panel proposal."""
        self.proposals = [dict(PROPOSAL)]
        self.clock.set(self.clock() + 7200)
        out = Architect(self.store, self.router, self.settings, clock=self.clock).equity_pass()
        self.assertEqual((out["born"], out["refused"]["count"], out["panel"]), ([SLUG], 0, {"want": 1, "born": 1}), out)
        request = self.router.calls[-1]["user"]
        for part in ('THE PANEL (structure "panel", lane equity)', "THE PANEL AGENDA", "THE PANEL TRAIN BAR (equity-xs-v1)",
                     "THE PANEL CONTRACT"):
            self.assertIn(part, request)
        fam = self.store.family(SLUG)
        self.assertEqual((fam["structure"], fam["roots"], fam["band"], fam["spec"]["lane"], fam["spec"]["agenda"]),
                         ("panel", [], "gym", "equity", "xs_reversal"))
        self.assertEqual(self.store.latest_version(SLUG)["n"], 1)
        # THE HIDDEN YEAR is release E3's fold (`elane_folds`), merged under this lane and recording in the committed
        # policy (`elane.memory.mode` "record"): the family is born with one of the panel's six Train years held out,
        # drawn by its cell as `elane_xs.assign` says (the first family of its cell), and its bar reads the other five.
        cell = elane_xs.cell_of("equity", "xs_reversal", "sp500")
        self.assertEqual(elane_folds.mode(self.settings), "record")
        self.assertEqual(fam["spec"]["hidden_year"],
                         xconfig.TRAIN_YEARS[elane_folds.cell_hash(cell) % len(xconfig.TRAIN_YEARS)])
        self.assertEqual(elane_xs.hidden_year_of(fam), fam["spec"]["hidden_year"])
        self.assertEqual(fam["spec"]["gid"], elane_folds.GID0)
        return fam

    def trained(self) -> dict:
        """3. The Train bar in the decider's child, then the review and the audit under the panel rubric."""
        researcher = EquityResearcher(self.store, self.router, self.settings, root=self.root, clock=self.clock)
        researcher.xs_runner = self.runner
        out = researcher.step(self.store.family(SLUG))
        self.assertTrue(out["passed"], out)
        self.assertEqual(out["review"], {"family": SLUG, "version": 1, "passed": True, "review": "pass"})
        rec = elane_xs.record_of(self.store.family(SLUG))
        self.assertEqual((rec["status"], rec["passed_version"]), ("passed", 1))
        entry = rec["versions"]["1"]
        self.assertEqual((entry["verdict"], entry["fails"]), ("pass", []))
        self.assertEqual(entry["facts"]["rules"], {rule: True for rule in ("XA0", "XH1", "XP1", "XR1", "XT1", "XY1")})
        # The bar read the five years the family may see; its hidden year went to the sealed out-of-fold row, after
        # the verdict, and nowhere else (release E3's fold under this lane).
        hidden = elane_xs.hidden_year_of(self.store.family(SLUG))
        self.assertEqual(entry["facts"]["seen_years"], len(xconfig.TRAIN_YEARS) - 1)
        self.assertIn(hidden, xconfig.TRAIN_YEARS)
        oof = self.store.family(SLUG)["state"][elane_xs.OOF_KEY]["1"]
        self.assertEqual(sorted(oof), ["1", "1.5"], "one hidden run at each cost multiple")
        for row in oof.values():
            self.assertEqual((row["status"], sorted(row)), ("ok", ["days", "status", "sum_x", "t_x"]))
            self.assertGreater(row["days"], 240, "the hidden year's own sessions")
        self.assertNotIn(elane_xs.OOF_KEY, json.dumps(rec), "the record a generator's views are built from holds none of it")
        # THE RESTART CHECK asked the program again from fresh memory and met the same targets (it keeps no state).
        self.assertEqual((entry["state"]["matched"], entry["state"]["share"]), (entry["state"]["calls"], 1.0))
        # A22 (1): the House's own reading of its Train holdings' loadings; this program tilts to none of the four.
        self.assertEqual((entry["style"]["open"], entry["style"]["tilts"]), (False, []))
        self.assertGreater(entry["style"]["lots"], entry["style"]["rule"]["min_lots"])
        self.assertGreater(elane_xs.cpu_spent(self.store, self.clock()), 0, "the day's panel CPU is booked")
        # A22 (3): the review and its audit ran under the PANEL rubric, on two different models.
        asked = [str(c.get("key")) for c in self.router.calls]
        self.assertEqual([k.split(":")[3] for k in asked if k.startswith("swarm:elane:xs:")], ["review", "audit"], asked)
        review = self.store.family(SLUG)["state"]["review"]
        self.assertEqual((review["objective"], review["rubric"]), (elane_xs.REVIEW_OBJECTIVE, elane_xs.rubric_sha()))
        return rec

    def the_forward_record_passes_it_by(self) -> None:
        """Release E3's registry beside this lane, the real job's `sync` on this store: a scored panel version is NOT
        in the forward record. E3 registers the versions of E2's own Train record, of structure "etf" or "stock"; a
        panel version's forward row, its nightly shadow and its twin are PACKAGE J's (league/ops/forward_xs.py: owed,
        every function a stub). The registry neither registers nor refuses it, nothing fails and the hash chain holds:
        the two releases run side by side, and until J lands a scored panel program is recorded by its own lane and
        not shadowed. THE DAY J LANDS THIS READS ONE ROW, and this test is J's to change."""
        self.assertNotIn("panel", forward_register.STRUCTURES)
        db = forward_db.open_db(self.root)
        self.addCleanup(db.close)
        for _ in range(2):
            out = forward_register.sync(self.root, db, now=self.clock(), settings=self.settings)
            self.assertEqual((out["registered"], out["skipped"], out["chain"]["ok"], out["chain"]["rows"]),
                             (0, [], True, 0), out)
        with self.assertRaises(NotImplementedError):
            forward_xs.scored(self.store)

    def validated(self) -> dict:
        """4. The one Validation try."""
        tournament = Tournament(self.store, None, self.settings, clock=self.clock)
        tournament.xs_runner = self.runner
        fam = self.store.family(SLUG)
        got = elane.validate(tournament, fam, self.store.version(SLUG, 1))
        self.assertEqual({k: got[k] for k in ("passed", "entered", "screen", "lane", "structure")},
                         {"passed": True, "entered": True, "screen": "XS1", "lane": "equity", "structure": "panel"})
        state = self.store.family(SLUG)["state"]
        self.assertTrue(state["gate_ready"])
        self.assertTrue(state[elane_xs.PRECHECK_KEY]["passed"])
        # THE HOUSE'S DUTY (the pre-registration's lineage rule): BOTH Train series of a program that reached the
        # pre-check are kept, the residual and the universe excess, a figure a Train session of both segments.
        x, u = state[elane_xs.TRAIN_X_KEY], state[elane_xs.TRAIN_U_KEY]
        self.assertEqual(x["days"], u["days"])
        self.assertGreater(len(x["days"]), 1400)
        self.assertEqual({ES.from_ordinal(d).year for d in x["days"]}, set(xconfig.TRAIN_YEARS))
        self.assertGreater(state[elane.SIGMA_KEY]["1"], 0)
        return state

    def looked(self) -> dict:
        """5. The one sealed look under XS1."""
        gate = Gate(self.store, None, None, self.settings, clock=self.clock)
        gate.xs_runner = self.runner
        version = self.store.version(SLUG, 1)
        sha = run_sha(version)
        self.assertTrue(elane.look(gate, self.store.family(SLUG), version, sha))
        fam = self.store.family(SLUG)
        self.assertEqual(fam["band"], "candidate")
        look = fam["state"][elane_xs.LOOK_KEY]
        verdict = look["verdict"]
        pinned, why = elane_xs.receipt()
        self.assertIsNone(why)
        self.assertEqual((look["passed"], look["seat"], look["n_cell"]), (True, elane_xs.SEAT_CANDIDATE, 0), look)
        self.assertEqual(verdict["screen"], "XS1")
        # THE RULE'S LEGS, every threshold the pinned receipt's (never a figure of this test): the holdout t of the
        # residual at or above max(c_XS, own floor + margin), and the program ahead of the matched placebos.
        floor = fam["state"][elane_xs.FLOOR_KEY]["1"]
        self.assertTrue(floor["eligible"])
        self.assertEqual(round(verdict["c_used"] * 100),
                         max(round(pinned.c_XS * 100), round((verdict["c_p"] + pinned.c_margin) * 100)))
        self.assertEqual((floor["c_used"], floor["c_p"]), (verdict["c_used"], verdict["c_p"]))
        self.assertGreaterEqual(verdict["t_H"], verdict["c_used"])
        self.assertEqual(verdict["n_placebo"], pinned.placebo_draws)
        self.assertLessEqual(verdict["p_plac"], pinned.alpha_plac)
        self.assertNotIn("{", look["beside"], "every placeholder of the receipt's sentence is filled")
        detail = self.store.looks()[-1]["detail"]
        self.assertEqual((detail["screen"], detail["receipt"]), ("XS1", pinned.receipt_sha256))
        # A CANDIDATE PROVEN ON THE XS IDENTITY of the running files, and on nothing of the equity identity.
        self.assertEqual(fam["state"]["banded_evaluator"], {"engine": xidentity.xs_identity()["engine"],
                                                            "xs_sha256": xidentity.xs_fingerprint(), "run_sha": sha})
        self.assertTrue(bands.equity_proof_current(fam["state"], version))
        return fam

    # --------------------------------------------------------------------------------------------------- the test
    def test_a_bred_panel_program_from_birth_to_the_done_meter(self):
        market = self.market()
        gateway = Gateway(market)
        # 1. THE NIGHTLY I6 of the store's last session, on the venue's own bars (package A's check; no live decision
        # yet): the bars agree within the vendor's cents and the two ctx are the same bytes. Its verdict goes into the
        # manifest as the job writes it; until it holds, the lane cannot be "live".
        self.assertEqual(elane_xs.live_ready(self.root, self.settings)[0], False)
        i6 = EP.i6_check(self.store_root, gateway, FRIDAY)
        self.assertEqual((i6["equal"], i6["bytes_equal"], i6["source"], i6["mismatch"], i6["why"]),
                         (True, True, "fetch", 0, None), i6)
        self.assertGreater(i6["columns"], 60)
        self.manifest(i6=i6)
        self.probe_file()
        self.assertEqual(elane_xs.mode(self.settings, self.root), "gate", "no twin marker yet: live reads as gate")

        self.born()
        self.trained()
        self.the_forward_record_passes_it_by()
        self.validated()
        self.looked()
        # NO NAME REACHED THE EVIDENCE CHILD, and none is in what the swarm keeps of the program's runs.
        ops = [m[2] for m in self.child.messages if m[0] == "kind" and m[1] == "panel"]
        self.assertTrue({"needs", "run"} <= set(ops), ops)
        self.assertFalse(self.tickers & {s for m in self.child.messages for s in strings(m)})
        kept = json.dumps([self.store.runs(SLUG), self.store.family(SLUG)["state"]], default=str)
        self.assertEqual([t for t in sorted(self.tickers) if f'"{t}"' in kept], [])

        # ---------------------------------------------------------------------------- 6. the seat
        venue = Venue(market, self.clock, cash=str(E))
        state = LiveState(self.root / "live.sqlite", clock=self.clock)
        self.addCleanup(state.close)
        for key, witnesses in ((STOCK_BUY_KEY, STOCK_BUY_WITNESSES), (STOCK_SELL_KEY, STOCK_WITNESSES)):
            state.put(key, {"schema": 1, "status": "passed", **{k: True for k in witnesses}})   # its own tests prove it
        real = M.Table.from_constitution()
        self.assertFalse(self.tickers & set(real.equity.universe), "no made-up ticker is the constitution's")
        table = dataclasses.replace(real, equity=dataclasses.replace(
            real.equity, universe={**real.equity.universe, **{s: "stock" for s in sorted(self.tickers)}}))
        self.assertEqual((table.equity.position_share["stock"], table.equity.open_risk_weight["stock"],
                          table.equity.probe_sleeve_share), (D("0.20"), D("0.40"), D("0.50")), "the constitution's own")
        events, alerts = [], []
        decider = InProcess()
        book = L.EquityBook(state, venue, market, table, EquityFamilies(self.root), decider=decider,
                            stock_proof=StockPaperProof(state, None, clock=self.clock), sizing_equity=lambda: E,
                            root=self.root, clock=self.clock, record=lambda kind, payload, agent=None:
                            events.append((kind, payload)), alert=lambda level, text: alerts.append((level, text)))

        def tick(day, hh, mm, ss=3):
            self.clock.set(at(day, hh, mm, ss))
            out = book.tick(self.clock(), account_row=venue.account(), positions=None, open_orders=None,
                            real_block=lambda opening=True: None, killed=lambda: False)
            self.assertFalse(out.get("errors"), out)
            return out

        def evening(day):
            """A session's evening: the panel's bars from 16:20, the decide at 16:30."""
            out = {}
            for mm in (20, 21, 30):
                out = tick(day, 16, mm)
            return out

        def lots(status=None):
            found = [L.Lot.of(r) for r in state.rows("SELECT * FROM eq_lots ORDER BY lid")]
            return [lot for lot in found if status is None or lot.status == status]

        def rebalance(day):
            [row] = state.rows("SELECT * FROM eq_rebalances WHERE decided_day=?", (day.isoformat(),))
            return row

        # WITHOUT THE TWIN MARKER a Candidate holds no seat: mode "live" reads as "gate" (package J is owed).
        tick(SUNDAY, 12, 30)
        self.assertEqual((self.store.family(SLUG)["band"], state.rows("SELECT id FROM eq_instances")), ("candidate", []))
        self.assertEqual(market.bar_calls, [], "and with no panel instance the book fetched nothing")
        self.twin_marker(FRIDAY)
        self.assertEqual((elane_xs.mode(self.settings, self.root), elane_xs.live_ready(self.root, self.settings)),
                         ("live", (True, None)))
        [row] = [r for r in bands.read(self.root, lanes=LANES) if r["family"] == SLUG]
        self.assertEqual((row["structure"], row["lane"], row["band"], row["symbols"]), ("panel", "equity", "candidate", []))
        self.assertEqual(row["beside"], self.store.family(SLUG)["state"][elane_xs.LOOK_KEY]["beside"])

        # Friday's close, decided on the Sunday deploy: the band decision seats the Candidate at Probe, the instance is
        # of kind "panel", and its first rebalance buys five names at Monday's open.
        out = tick(SUNDAY, 13, 0)
        self.assertEqual(self.store.family(SLUG)["band"], "probe", out)
        inst = L.instance_key(SLUG, 1)
        [instance] = state.rows("SELECT id, kind, band FROM eq_instances")
        self.assertEqual((instance["id"], instance["kind"], instance["band"]), (inst, "panel", "probe"))
        first = rebalance(FRIDAY)
        self.assertEqual((first["exec_day"], first["at"], first["called"], first["n_names"], first["n_sells"],
                          first["n_buys"], first["n_skipped"], first["status"]),
                         (WEEK[0].isoformat(), "open", 1, 5, 0, 5, 0, "planned"))
        # THE WHOLE BASKET IS SCALED TO THE ROOM (the review's spec-2): at the Probe sleeve of 0.50 x E a full sleeve of
        # stocks is 0.40 x $1,114.50 = $445.80 of open risk, above the $400 window, so the decision's budget is what a
        # full basket fits: $400 / 0.40 = $1,000, and every name is a fifth of THAT.
        sleeve = table.equity.probe_sleeve_share * E
        window = table.probe_loss_budget
        budget = window / table.equity.open_risk_weight["stock"]
        self.assertLess(budget, sleeve)
        self.assertEqual(D(first["budget"]), budget)
        basket = sorted(symbol for symbol, _ in json.loads(first["targets"]))
        self.assertTrue(set(basket) <= self.tickers and len(basket) == 5, basket)
        planned = state.rows("SELECT * FROM eq_intents ORDER BY iid")
        self.assertEqual(sorted(i["symbol"] for i in planned), basket)
        self.assertEqual({(i["kind"], i["at"], i["usd"], i["exec_day"], i["tag"]) for i in planned},
                         {("buy", "open", str((D("0.2") * budget).quantize(D("0.01"))), WEEK[0].isoformat(), xbook.TAG)})
        # THE BARS THAT DECISION READ ARE KEPT, and the nightly I6 now reads them against the store by the book's own
        # rule: the live decision's ctx is the Gym's.
        self.assertTrue((self.store_root / xbook.LIVE_BARS_DIR / f"{FRIDAY.isoformat()}.npz").exists())
        again = EP.i6_check(self.store_root, gateway, FRIDAY, live=self.root / "live.sqlite")
        self.assertEqual((again["equal"], again["source"], again["live"]), (True, "kept", {inst: True}), again)

        # ---------------------------------------------------------------------------- 7. a live week
        # Monday's open: five limit buys through E1's order path, sized by money's own rules. FIVE WHOLE LOTS, each a
        # fifth of the scaled budget ($200): together they fill the $400 window, where a stock's open risk weighs
        # 0.40, and none is cut (before the fix: four lots of $222.90 and the fifth cut to $108.40 by the budget).
        market.extend(WEEK[0], lambda symbol: 0.001)
        tick(WEEK[0], 8, 31)
        self.assertEqual((rebalance(FRIDAY)["audit"], venue.sent), ("ok", []))
        # WHAT STOPS THE LANE OVERNIGHT STOPS THE MORNING'S ENTRIES: the night's I6 did not hold, so the lane is not
        # live and the swarm gives the program no row: the buys planned on Friday's close are held at the send, minute
        # after minute, and nobody is retired on it before the day's own band sync. The I6 holds again (the job's next
        # run) inside the entry window: they go.
        self.manifest(i6={**i6, "equal": False})
        self.assertEqual(elane_xs.mode(self.settings, self.root), "gate")
        self.assertEqual([r for r in bands.read(self.root, lanes=LANES) if r["family"] == SLUG], [])
        tick(WEEK[0], 9, 30, 33)
        tick(WEEK[0], 9, 31)
        self.assertEqual(venue.sent, [], "no open while the lane is not live")
        held_why = {i["why"] for i in state.rows("SELECT why FROM eq_intents WHERE status='planned'")}
        self.assertEqual(len(held_why), 1)
        self.assertIn("holds no seat now", held_why.pop())
        self.assertIsNone(state.rows("SELECT retired_at FROM eq_instances")[0]["retired_at"])
        self.manifest(i6=again)
        tick(WEEK[0], 9, 32)
        tick(WEEK[0], 9, 33)
        bought = lots()
        self.assertEqual(sorted(lot.symbol for lot in bought), basket)
        self.assertEqual({(b["side"], b["type"], b["time_in_force"]) for b in venue.sent}, {("buy", "limit", "day")})
        self.assertEqual({(lot.status, lot.entry_at, lot.opened_day, lot.probe, lot.klass, lot.tag) for lot in bought},
                         {("open", "open", WEEK[0].isoformat(), True, "stock", xbook.TAG)})
        name = D("0.2") * budget
        for lot in bought:
            self.assertLessEqual(lot.entry_notional, name)
            self.assertLessEqual(lot.entry_notional, D("0.2") * sleeve, "the sleeve's own name cap")
            self.assertLessEqual(lot.entry_notional, table.equity.position_share["stock"] * E, "a stock: 20% of equity")
            self.assertEqual(lot.entry_px, market.quote(lot.symbol)[1], "a marketable limit filled at the ask")
        whole = [lot for lot in bought if lot.entry_notional > name - 1]
        self.assertEqual(len(whole), 5, [str(lot.entry_notional) for lot in bought])
        _, _, _, at_risk, _ = R.probe_figures(state.rows, day=WEEK[0].isoformat(), table=table)
        invested = sum((lot.qty * lot.entry_px for lot in bought), D(0))
        self.assertEqual(at_risk, table.equity.open_risk_weight["stock"] * invested, "one budget, stocks at 0.40")
        self.assertLessEqual(at_risk, window)
        self.assertGreater(at_risk, window - 2, "the whole basket took the window, a fifth a name")
        self.assertLessEqual(invested, table.equity.invested_share * E)
        self.assertEqual([o for o in state.rows("SELECT why FROM eq_orders") if "budget" in (o["why"] or "")], [],
                         "no order was cut by the budget")

        # Four hold days: the bars are read, kept and audited, the lots marked, NO program code runs, nothing trades.
        held = set(basket)
        losers = sorted(s for _, s in self.universe.members(FRIDAY) if s not in held and s not in synth.PAIR)[:5]
        order = {symbol: k for k, symbol in enumerate(sorted(market.bar_rows["raw"]))}

        def move(symbol):
            """The invented week: what the program holds rises, five other members fall, everything else is flat."""
            if symbol in held:
                return 0.015
            if symbol in losers:
                return -0.015
            return 0.0005 + 0.0001 * (order[symbol] % 7)

        sent = len(decider.messages)
        evening(WEEK[0])
        for day in WEEK[1:]:
            market.extend(day, move)
            tick(day, 8, 31)
            tick(day, 9, 30, 33)
            if day is not WEEK[-1]:
                evening(day)
        self.assertEqual(len(venue.sent), 5, "a hold day sends nothing")
        for day in WEEK[:-1]:
            row = rebalance(day)
            self.assertEqual((row["called"], row["status"], row["n_sells"], row["n_buys"], row["audit"]),
                             (0, "hold", 0, 0, "ok"), dict(row))
        jobs = [job for m in decider.messages[sent:] if m[0] == "kind" and m[2] == "decide" for job in m[3]["jobs"]]
        self.assertEqual([job["called"] for job in jobs], [False] * 4, "the child is asked each close, the program is not")
        self.assertTrue(all(lot.mark is not None for lot in lots("open")), "B15: a panel lot is marked at each close")

        # Friday's decision: the program is asked again and rotates out of everything it holds.
        out = evening(WEEK[-1])
        self.assertEqual(out["decided"], [f"{inst}: 10"], out)
        second = rebalance(WEEK[-1])
        self.assertEqual((second["called"], second["status"], second["n_sells"], second["n_buys"], second["n_skipped"],
                          second["exec_day"]), (1, "planned", 5, 5, 0, NEXT_MONDAY.isoformat()))
        self.assertEqual(sorted(symbol for symbol, _ in json.loads(second["targets"])), losers)

        # The next Monday's open: five sales (never in the session a lot was bought), then five buys, each a fifth of
        # that decision's budget; the closed lots are exported to the forward record.
        market.extend(NEXT_MONDAY, lambda symbol: 0.001)
        tick(NEXT_MONDAY, 8, 31)
        tick(NEXT_MONDAY, 9, 30, 33)
        tick(NEXT_MONDAY, 9, 31)
        self.assertEqual([b["side"] for b in venue.sent], ["buy"] * 5 + ["sell"] * 5 + ["buy"] * 5)
        closed = lots("closed")
        self.assertEqual(sorted(lot.symbol for lot in closed), basket)
        for lot in closed:
            self.assertEqual((lot.exit_at, lot.exit_day, lot.reason), ("open", NEXT_MONDAY.isoformat(), "program"))
            self.assertEqual(lot.exit_px, market.quote(lot.symbol)[0], "sold at the bid")
            self.assertEqual(lot.cash, lot.opened_qty * lot.exit_px - lot.entry_notional - lot.fees + lot.div)
            self.assertGreater(lot.cash, 0, "the invented week rose under it")
            self.assertEqual(venue.held[lot.symbol], D(0))
        self.assertEqual(sorted(lot.symbol for lot in lots("open")), losers)
        self.assertEqual(sorted(r["trade_id"] for r in self.store.forward(SLUG)), sorted(f"eq-{lot.lid}" for lot in closed))
        _, _, _, at_risk, _ = R.probe_figures(state.rows, day=NEXT_MONDAY.isoformat(), table=table)
        self.assertLessEqual(at_risk, window)
        # THE PARENT KNOWS THE NAMES, THE CHILD NEVER DOES: no message of the live week carried a ticker.
        self.assertEqual(len([m for m in decider.messages if m[0] == "kind" and m[2] == "decide"]), 6, "a decide a close")
        self.assertFalse(self.tickers & {s for m in decider.messages for s in strings(m)})
        self.assertEqual([a for a in alerts if a[0] == "error"], [])

        # ---------------------------------------------------------------------------- 8. the readers
        evening(NEXT_MONDAY)                                     # the exit day's bars kept
        market.extend(NEXT_TUESDAY, lambda symbol: 0.001)
        tick(NEXT_TUESDAY, 8, 31)                                # and audited the next morning
        now = at(NEXT_TUESDAY, 12, 0)
        judged = TW.equity_round(self.root, now=now, store=self.store)
        self.assertEqual((judged["closed"], judged["judged"], judged["pending"]), (5, {"priced": 5}, 0), judged)
        twins = TW.equity_records(self.store)
        for lot in closed:
            twin = twins[f"eq:{lot.lid}"]
            self.assertEqual((twin["final"], twin["hs_source"]), (True, "panel"), twin)
            self.assertEqual((D(str(twin["entry_official"])), D(str(twin["exit_official"]))),
                             (market.official(lot.symbol, WEEK[0], "open"), market.official(lot.symbol, NEXT_MONDAY, "open")))
            self.assertLess(abs(twin["gap_bp"]), 15, twin)

        report = DR.report(self.root, settings=self.settings, now=now)
        done = report["done"]
        self.assertEqual((done["all"]["running"]["closes"], done["all"]["running"]["programs"],
                          done["all"]["running"]["replay_coverage"]), (5, 1, {"matched": 5, "closes": 5, "share": 1.0}))
        sentence = self.store.family(SLUG)["state"][elane_xs.LOOK_KEY]["beside"]
        rows = {c["pid"]: c for c in done["all"]["closes"]}
        for lot in closed:
            row = rows[f"eq:{lot.lid}"]
            self.assertEqual((row["lane"], row["label"], row["seeded"]), ("equity", xbook.LABEL, False))
            self.assertEqual(D(str(row["pnl_usd"])), lot.cash.quantize(D("0.01")))
            # THE HOUSE'S DUTY: XS1's sentence, as its receipt fixes it, beside EVERY live panel trade.
            self.assertEqual((row["fp"]["screen"], row["fp"]["beside"], row["fp"]["passed"]), ("XS1", sentence, True))
        panel = report["equity"]["panel"]["programs"][inst]
        self.assertEqual((panel["label"], panel["closed_lots"], panel["open_lots"], panel["close_dates"]),
                         (xbook.LABEL, 5, 5, 1), panel)
        self.assertEqual(D(str(panel["pnl_usd"])), sum((lot.cash for lot in closed), D(0)).quantize(D("0.01")))
        self.assertIsNone(panel["date_t"], "five lots closed on one date are ONE observation: no t of one date")
        self.assertEqual((panel["decisions"], panel["audits"]), ({"planned": 2, "hold": 5}, {"ok": 7}))
        self.assertEqual(panel["xs1"]["beside"], sentence)
        self.assertIsNone(panel["residual_x"], "the forward record's (package J): owed, never invented")

        # ---------------------------------------------------------------------------- 9. the way back
        # A swarm.json caught mid-write says nothing: the lane cannot be READ, so the book retires nobody on it (a
        # retirement sells), and with no row it opens nothing either.
        (self.root / "swarm.json").write_text('{"elane": {"mode": "ga', encoding="utf-8")
        self.forget()
        self.assertEqual(elane_xs.seat_standing(self.root)[0], None)
        evening(NEXT_TUESDAY)
        self.assertIsNone(state.rows("SELECT retired_at FROM eq_instances")[0]["retired_at"])
        self.assertEqual(len(lots("open")), 5)
        self.assertEqual(len(venue.sent), 15)
        # THE LANE'S MODE ONE STEP DOWN ("gate", the rollback of "live"): the swarm gives the seated program no row,
        # and on the lane's own word the book retires its instance: it decides no more and its lots leave at the next
        # open by E1's rule. Nothing is bought again. The family's band in the store is not moved.
        self.switch({**SWITCHES, "elane": {**SWITCHES["elane"], "panel": {"mode": "gate"}}})
        self.assertEqual(elane_xs.mode(self.settings, self.root), "gate")
        live, why = elane_xs.seat_standing(self.root)
        self.assertEqual((live, why), (False, 'the panel lane is not live (its mode reads "gate"): elane.panel.mode is set so'))
        self.assertEqual([r for r in bands.read(self.root, lanes=LANES) if r["family"] == SLUG], [])
        market.extend(NEXT_WEDNESDAY, lambda symbol: 0.001)
        tick(NEXT_WEDNESDAY, 8, 31)
        tick(NEXT_WEDNESDAY, 9, 30, 33)
        self.assertEqual(len(venue.sent), 15, "the sync that retires is the day's decision's own")
        asked = len(decider.messages)
        evening(NEXT_WEDNESDAY)
        [instance] = state.rows("SELECT retired_at, why, band FROM eq_instances")
        self.assertIsNotNone(instance["retired_at"])
        self.assertEqual((instance["why"], instance["band"]), (f"demoted: {why}", "candidate"))
        self.assertEqual([m for m in decider.messages[asked:] if m[0] == "kind" and m[2] == "decide"], [],
                         "a retired program is asked nothing")
        self.assertIn(("warning", f"equity: {inst} is demoted: {why}: it decides no more and its lots exit at the next "
                                  "open"), alerts)
        self.assertEqual(self.store.family(SLUG)["band"], "probe")
        thursday = dt.date(2026, 10, 22)
        market.extend(thursday, lambda symbol: 0.001)
        tick(thursday, 8, 31)
        tick(thursday, 9, 30, 33)
        tick(thursday, 9, 31)
        self.assertEqual([b["side"] for b in venue.sent[15:]], ["sell"] * 5, "five exits and no buy")
        self.assertEqual(lots("open"), [])
        self.assertEqual({(lot.exit_day, lot.reason) for lot in lots("closed")},
                         {(NEXT_MONDAY.isoformat(), "program"), (thursday.isoformat(), "demoted")})
        self.assertEqual(sum(venue.held.values(), D(0)), D(0))
        self.assertEqual([a for a in alerts if a[0] == "error"], [])
        # The switch back up: the lane is live again and the swarm's row is back (the book's own rule then runs the
        # same instance again).
        self.switch(SWITCHES)
        self.assertEqual(elane_xs.seat_standing(self.root), (True, ""))
        self.assertEqual([r["band"] for r in bands.read(self.root, lanes=LANES) if r["family"] == SLUG], ["probe"])


if __name__ == "__main__":
    unittest.main()
