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
4. THE CAPTAIN'S A34 (release U): no sealed Validation try and no XS1 look for a panel program, under the captain's
   switches as the box would hold them ("gate" and above, `look_rule` "xs1"): `elane.try_open` is False, the
   tournament has no try for it, `elane.look` holds before any run, nothing spent and nothing retired;
5. the forward pass: a FWD1-R pass of case N, written in the forward screen's place (its permit file and its verdict's
   sentence: league/ops/forward_screen.py writes both, league/tests/test_forward_screen.py holds the job), made eligible
   by `elane_forward.step` in the gate's equity round and seated by the PANEL POOL (`elane_xs.forward_seats`, the same
   round) only once the lane is live: a Candidate of the pool proven on the xs identity in force (G's
   `bands.current_xs_evaluator`), its forward seat recorded in the transaction that moves its band;
6. the seat: the lane's effective mode is "live" only with the universe deploy in force, the I6 held and the twin
   marker written; the EquityBook reads the swarm's panel row, seats the Candidate at Probe and makes it an instance of
   kind "panel" (H's patch 12);
7. a live week through E1's EquityBook and H's adapter, sized by MONEY'S REAL RULES: Friday's decision (five names),
   Monday's open (five limit buys), four hold days (no program code runs), Friday's rotation decision, and the next
   Monday's open (five sales, then five buys), every morning's audit of the bars a decision read;
8. the readers: B's replay twin of every closed lot at the panel's own half-spread, the Done meter and H's panel lines
   in the direction report, FWD1-R's sentence (with A34's two) beside every live panel trade;
9. the way back: what stops the lane overnight holds the morning's entries; the lane's mode put down one step
   retires the seated program on the lane's own word, and its lots leave at the next open; a switch file that cannot
   be read retires nobody.

`ThePanelLaneEndToEnd.test_the_historical_route_as_built_seats_nobody_under_a34` keeps the route A34 retired on the
same real code, as a record: Validation and the one sealed look under XS1 (E's pre-check, E's exact floor, the look
run with 999 matched placebos under E1's capability, `screen.verdict`, the receipt's sentence), opened for that test
alone (`elane_xs.A34_FORWARD_ONLY` False); the Candidate the look makes holds no seat once A34 is the House's again.

WHAT THE TEST WRITES IN ANOTHER PACKAGE'S PLACE, and only that: the FWD1-R permit file and its pass's verdict row (the
forward screen's job writes both, league/ops/forward_screen.py; no forward night is run here), the contamination probe's permit with the panel strata
(package B's patch 18: its writer is league/ops/contam_xs.py, the plan the probe can be handed; no model is asked
here, and league/tests/test_contam_xs.py holds the probe with it), and the twin marker (package J's panel night writes
it, league/ops/forward_xs.py; no forward night runs in this test, so it is written here with that module's own writer:
league/tests/test_forward_xs_twin.py holds the night itself). Without either the lane stops where its rule says (no
look; no live seat); `TheLaneStopsWhereItsRuleSays` holds both.

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
from decimal import ROUND_DOWN, Decimal as D
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
    from league.ops import forward_screen as FS
    from league.ops import fwd1_rule as R1
    from league.ops import forward_db, forward_register, forward_xs
    from league.ops import twins as TW
    from league.swarm import bands, elane, elane_folds, elane_xs
    from league.swarm import elane_forward as EF
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
#: The captain's switches on the box. `look_rule` "xs1": XS1 as built, which A34 holds like every other value (the
#: policy ships "hold"); `elane.fwd1.seats` "on": the forward screen's seat path, the panel's one way to a seat.
SWITCHES = {"elane": {"mode": "gate", "birth_share": 0.25, "panel": {"mode": "live", "look_rule": "xs1"},
                      "fwd1": {"mode": "record", "seats": "on"}},
            "dlane": {"mode": "gate"}}
#: The FWD1-R pass (invented figures: no forward night runs here): checkpoint 5 of the record's forward sessions.
FORWARD = {"k": 5, "start": "2026-10-16", "t": 2.5, "c_used": 2.06, "g_bp": 3.0, "pnl": 12.0}
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
        """PACKAGE J'S FILE, written here in its panel night's place with that module's own writer: ids and days
        only."""
        forward_xs.write_marker(self.store_root, {}, through=through.isoformat(), at="2026-10-10T01:00:00Z")
        self.forget()

    def probe_file(self) -> None:
        """THE PROBE'S PERMIT with the panel strata (package B's patch 18: league/ops/contam_xs.py is its writer),
        written here in its shape: for the birth route, two words a stratum and era on P4-P6, no count and no
        rate."""
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

    def the_forward_record_registers_it(self) -> None:
        """Release E3's registry beside this lane, the real job's `sync` on this store: THE SCORED PANEL VERSION IS IN
        THE FORWARD RECORD (package J, league/ops/forward_xs.py). E3's own reader still takes the versions of E2's
        Train record, of structure "etf" or "stock"; the panel's reader hands the registry the version this lane's
        own bar judged, with the time of the scored event `elane_xs.score` wrote, its NEEDS, the route "XS1" and
        alpha 0.03 in its hashed row. One row, once; the hash chain holds. Its nightly shadow and its twin are that
        module's panel night (league/tests/test_forward_xs.py, test_forward_xs_twin.py)."""
        self.assertNotIn("panel", forward_register.STRUCTURES)
        db = forward_db.open_db(self.root)
        self.addCleanup(db.close)
        for n, registered in enumerate((1, 0)):
            out = forward_register.sync(self.root, db, now=self.clock(), settings=self.settings)
            self.assertEqual((out["registered"], out["skipped"], out["chain"]["ok"], out["chain"]["rows"]),
                             (registered, [], True, 1), (n, out))
        row = dict(db.execute("SELECT * FROM fwd_registry").fetchone())
        self.assertEqual((row["key"], row["lane"], row["reason"], row["ugroup"], row["route"], row["alpha_f"]),
                         (f"{SLUG}@1", "equity", "train_pass", "panel:sp500", "XS1", "0.03"))
        self.assertTrue(row["evidence"].startswith("event:"), "dated by the scored event the lane's own bar wrote")
        self.assertEqual(json.loads(row["needs"])["panel"], "sp500")
        self.assertEqual([r["key"] for r in forward_xs.scored(self.store)], [f"{SLUG}@1"])

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

    def held_by_a34(self) -> None:
        """4. THE CAPTAIN'S A34: under the captain's switches (the lane "live", `look_rule` "xs1") a panel program takes
        no sealed Validation try and no look; nothing is run, spent or retired."""
        self.assertIs(elane_xs.A34_FORWARD_ONLY, True, "the House's value")
        fam, version = self.store.family(SLUG), self.store.version(SLUG, 1)
        self.assertFalse(elane.try_open(self.store, fam, 1, self.settings))
        self.assertIsNone(elane.next_try(self.store, fam, self.settings), "the tournament has no try for it")
        tournament = Tournament(self.store, None, self.settings, clock=self.clock)
        tournament.xs_runner = self.runner
        self.assertEqual(elane.validate(tournament, fam, version)["refused"], elane_xs.A34_HOLD)
        gate = Gate(self.store, None, None, self.settings, clock=self.clock)
        gate.xs_runner = self.runner
        self.assertIsNone(elane.look(gate, fam, version, run_sha(version)))
        self.assertEqual(elane_xs.look_held(self.settings), elane_xs.A34_HOLD)
        state = self.store.family(SLUG)["state"]
        self.assertEqual((self.store.looks(), elane.lineage_tries(self.store, SLUG)), ([], []), "nothing spent")
        self.assertNotIn(elane_xs.PRECHECK_KEY, state)
        self.assertIsNone(elane_xs.lineage_spent(self.store, self.store.family(SLUG), self.settings))
        self.assertEqual(self.store.family(SLUG)["band"], "gym")

    def forward_passed(self) -> str:
        """5. A FWD1-R PASS of case N, in the forward screen's place (its permit file and its verdict's sentence, as
        league/ops/forward_screen.py writes them; invented figures, the rule's own words), made eligible by the gate's
        equity round; with the lane not yet live the panel pool leaves it waiting in the Gym band. The lineage."""
        from league.ops import forward_db, forward_xs

        policy = json.loads((self.repo / "policy.json").read_text(encoding="utf-8"))
        rule, why = R1.rule(policy)
        self.assertIsNone(why)
        fam, version = self.store.family(SLUG), self.store.version(SLUG, 1)
        lineage = EF.lineage_of(self.store, fam)
        db = forward_db.open_db(self.root)
        self.addCleanup(db.close)
        label = forward_xs.engine_label(db, forward_db.fwd_engine())
        self.assertIn("+xs.", label, "the registry holds a panel row: the label names the xs identity")
        pid = int(db.execute("SELECT pid FROM fwd_registry").fetchone()[0])
        figures = dict(typ="PANEL", case="N", k=FORWARD["k"], start=FORWARD["start"], c_used_value=FORWARD["c_used"],
                       k_own=None, observed=1, judged=1, expected=0.11)
        self.words = R1.words(rule, **figures)
        beside = R1.beside(rule, t=FORWARD["t"], g_bp=FORWARD["g_bp"], pnl=FORWARD["pnl"], drift=None, **figures)
        fs = FS.open_store(self.root)
        try:
            fs.execute("INSERT INTO fwd1_verdicts(lineage, pid, verdict, k, day, c_used, why, beside, words, at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)", (lineage, pid, "pass", FORWARD["k"], "2026-10-09",
                                                       FORWARD["c_used"], None, beside, self.words, self.clock()))
            fs.commit()
        finally:
            fs.close()
        row = {"status": "pass", "type": "PANEL", "case": "N", "cell": elane_xs.cell_text(elane_xs.family_cell(fam)),
               "family": SLUG, "version": 1, "run_sha": run_sha(version), "k": FORWARD["k"], "weak": True,
               "engine": label, "words": self.words}
        (self.root / FS.PERMITS).write_text(json.dumps({"version": EF.PERMITS_VERSION, "screen": R1.SCREEN,
                                                        "receipt": rule.receipt_sha256, "start": FORWARD["start"],
                                                        "at": "2026-10-11T11:00:00Z", "lineages": {lineage: row}}),
                                            encoding="utf-8")
        out = self.gate_round()
        self.assertEqual(out["forward"]["eligible"], [SLUG], out)
        self.assertIn("not live", out["forward_panel"]["waits"][SLUG], out)
        held = self.store.family(SLUG)["state"][EF.STATE_KEY]
        self.assertEqual((held["eligible"], held["seated"], held["case"]), (True, False, "N"))
        self.assertEqual(self.store.family(SLUG)["band"], "gym")
        return lineage

    def gate_round(self) -> dict:
        """The gate's equity round as the swarm's loop runs it (league/swarm/gate.py `equity_round`)."""
        gate = Gate(self.store, None, None, self.settings, clock=self.clock)
        gate.xs_runner = self.runner
        out: dict = {"held": [], "looked": []}
        gate.equity_round(out)
        return out

    def seated_by_the_pool(self) -> dict:
        """6. The lane is live: the next equity round's panel pool seats the pass (a Candidate proven on the xs
        identity in force, the forward seat recorded with the band move)."""
        out = self.gate_round()
        self.assertEqual(out["forward_panel"], {"seated": [SLUG], "waits": {}}, out)
        fam, version = self.store.family(SLUG), self.store.version(SLUG, 1)
        sha = run_sha(version)
        self.assertEqual(fam["band"], "candidate")
        self.assertEqual(fam["state"]["banded_evaluator"], {"engine": xidentity.xs_identity()["engine"],
                                                            "xs_sha256": xidentity.xs_fingerprint(), "run_sha": sha})
        self.assertTrue(bands.equity_proof_current(fam["state"], version))
        self.assertTrue(elane_xs.forward_seated(fam))
        self.assertEqual(self.gate_round().get("forward_panel"), {"seated": [], "waits": {}}, "once")
        return fam

    # --------------------------------------------------------------------------------------------------- the test
    def test_the_historical_route_as_built_seats_nobody_under_a34(self):
        """THE RECORD OF THE ROUTE A34 RETIRED, on the same real code: Validation and the one sealed look under XS1
        (opened for this test alone), whose Candidate holds no seat, no row and no instance once A34 is the House's
        again, live lane and all."""
        self.manifest(i6=EP.i6_check(self.store_root, Gateway(self.market()), FRIDAY))
        self.probe_file()
        self.born()
        self.trained()
        with mock.patch.object(elane_xs, "A34_FORWARD_ONLY", False):
            self.validated()
            self.looked()
        self.twin_marker(FRIDAY)
        self.assertEqual(elane_xs.mode(self.settings, self.root), "live")
        roster = bands.roster(self.root, lanes=LANES)
        self.assertIn(SLUG, roster["seatless"])
        self.assertEqual(roster["seatless_why"][SLUG], elane_xs.A34_SEATLESS)
        self.assertEqual([r for r in bands.read(self.root, lanes=LANES, queued=True) if r["family"] == SLUG], [])
        self.assertEqual(self.gate_round().get("forward_panel"), {"seated": [], "waits": {}},
                         "no forward pass: the pool has nothing to seat")
        self.assertEqual(self.store.family(SLUG)["band"], "candidate", "its band is the look's; it holds no seat")

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
        self.the_forward_record_registers_it()
        self.held_by_a34()
        lineage = self.forward_passed()
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
        # The equity opens on (A10.2; the old lanes' stop's rollback, the row alone): the seat and its buys below are
        # the machinery the stop leaves idle (league/tests/test_equity_opens_off.py holds the stop on the table in force).
        self.assertFalse(real.equity.enabled, "the old lanes are exits only (PREREG-EVL-1 section 8)")
        table = dataclasses.replace(real, equity=dataclasses.replace(
            real.equity, enabled=True, universe={**real.equity.universe, **{s: "stock" for s in sorted(self.tickers)}}))
        # THE SEATS AND THE SLEEVE ARE TWO NUMBERS (release E5-S): the pair in force is read, never assumed, and every
        # size below is computed from the table's rows.
        # (Release R2: the goal's 10% a name, `position_share.stock` 0.20 -> 0.10; a basket's names sit far under it.)
        self.assertEqual((table.equity.position_share["stock"], table.equity.open_risk_weight["stock"]),
                         (D("0.10"), D("0.40")), "the constitution's own")
        from league.tests.equity_design import in_force

        self.assertEqual(table.equity.probe_sleeve_share, D(in_force()[1]))
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

        # WITHOUT THE TWIN MARKER no forward pass takes a seat: mode "live" reads as "gate" (no panel night wrote one),
        # so the pool leaves the eligible pass in the Gym band and the book has no panel row.
        tick(SUNDAY, 12, 30)
        self.assertEqual((self.store.family(SLUG)["band"], state.rows("SELECT id FROM eq_instances")), ("gym", []))
        self.assertEqual(market.bar_calls, [], "and with no panel instance the book fetched nothing")
        self.twin_marker(FRIDAY)
        self.assertEqual((elane_xs.mode(self.settings, self.root), elane_xs.live_ready(self.root, self.settings)),
                         ("live", (True, None)))
        self.seated_by_the_pool()
        [row] = [r for r in bands.read(self.root, lanes=LANES) if r["family"] == SLUG]
        self.assertEqual((row["structure"], row["lane"], row["band"], row["symbols"]), ("panel", "equity", "candidate", []))
        self.assertEqual(row["beside"], self.words, "the forward pass's words beside its row (it took no look)")

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
        # THE WHOLE BASKET IS SCALED TO THE ROOM (the review's spec-2): the decision's budget is the smaller of the
        # sleeve and what a FULL basket fits in the $400 window, $400 / 0.40 = $1,000, and every name is a fifth of
        # THAT. SINCE STEP TWO THE SLEEVE IS THE PANEL ROW'S (`equity_money.panel.sleeve_share`, 0.10 x E = $222.90
        # at $2,229: $89.16 of open risk), never the Probe sleeve, so the sleeve is the smaller. (Before it a panel
        # program took the Probe sleeve; at A20's 0.50 x E, $445.80 of open risk, the window was the smaller and the
        # budget the $1,000: league/tests/test_equity_book_panel.py `TheWholeBasketIsScaledToTheRoom` holds that case
        # on its own table.)
        from league.equity.bands import panel_settings

        sleeve = panel_settings().sleeve_share * E
        window = table.probe_loss_budget
        budget = min(sleeve, window / table.equity.open_risk_weight["stock"]).quantize(D("0.01"), rounding=ROUND_DOWN)
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
        # fifth of the decision's budget held to the name's cap, and none is cut by the budget: together they are the
        # budget's open risk at a stock's 0.40 (before release R2 the whole panel sleeve's, $89.16 of a $222.90 sleeve; the
        # whole $400 window at A20's Probe sleeve, where before the fix four lots of $222.90 were bought and the fifth cut
        # to $108.40 by the budget). SINCE RELEASE R2 a stock's name cap is `position_share.stock` 0.10 (the goal's 10% a
        # name; 0.20 before it), of E and of the program's own sleeve as the Gym holds it: each fifth ($44.58) is cut to a
        # tenth of the sleeve ($22.29), half the sleeve's open risk.
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
        cap = table.equity.position_share["stock"]
        name = min(D("0.2") * budget, cap * sleeve)
        self.assertEqual(name, cap * sleeve, "the name's cap binds a fifth of the budget (release R2)")
        for lot in bought:
            self.assertLessEqual(lot.entry_notional, name)
            self.assertLessEqual(lot.entry_notional, cap * sleeve, "the sleeve's own name cap")
            self.assertLessEqual(lot.entry_notional, cap * E, "a stock: 10% of equity")
            self.assertEqual(lot.entry_px, market.quote(lot.symbol)[1], "a marketable limit filled at the ask")
        whole = [lot for lot in bought if lot.entry_notional > name - 1]
        self.assertEqual(len(whole), 5, [str(lot.entry_notional) for lot in bought])
        _, _, _, at_risk, _ = R.probe_figures(state.rows, day=WEEK[0].isoformat(), table=table)
        invested = sum((lot.qty * lot.entry_px for lot in bought), D(0))
        self.assertEqual(at_risk, table.equity.open_risk_weight["stock"] * invested, "one budget, stocks at 0.40")
        self.assertLessEqual(at_risk, window)
        self.assertGreater(at_risk, table.equity.open_risk_weight["stock"] * 5 * name - 2,
                           "the whole basket is the budget's open risk, the name's cap a name")
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
        # Done counts a panel program's lots closed on one date as ONE close (release E4 step two, `done_counts`): the
        # basket's five lots sold at one open are one count, the five lots beside it.
        self.assertEqual((done["all"]["running"]["closes"], done["all"]["running"]["lots"],
                          done["all"]["running"]["programs"], done["all"]["running"]["replay_coverage"]),
                         (1, 5, 1, {"matched": 5, "closes": 5, "share": 1.0}))
        sentence = FS.beside_for(self.root, lineage)
        self.assertIn(R1.A34_MEMORY, sentence, "A34 (5): why there is no historical look")
        rows = {c["pid"]: c for c in done["all"]["closes"]}
        for lot in closed:
            row = rows[f"eq:{lot.lid}"]
            self.assertEqual((row["lane"], row["label"], row["seeded"]), ("equity", xbook.LABEL, False))
            self.assertEqual(D(str(row["pnl_usd"])), lot.cash.quantize(D("0.01")))
            # THE HOUSE'S DUTY: the forward pass's sentence, with A34's two, beside EVERY live panel trade.
            self.assertEqual((row["fp"]["screen"], row["fp"]["beside"], row["fp"]["panel"]), ("FWD1-R", sentence, True))
        panel = report["equity"]["panel"]["programs"][inst]
        self.assertEqual((panel["label"], panel["closed_lots"], panel["open_lots"], panel["close_dates"]),
                         (xbook.LABEL, 5, 5, 1), panel)
        self.assertEqual(D(str(panel["pnl_usd"])), sum((lot.cash for lot in closed), D(0)).quantize(D("0.01")))
        self.assertIsNone(panel["date_t"], "five lots closed on one date are ONE observation: no t of one date")
        self.assertEqual((panel["decisions"], panel["audits"]), ({"planned": 2, "hold": 5}, {"ok": 7}))
        self.assertEqual((panel["xs1"]["screen"], panel["xs1"]["beside"]), ("FWD1-R", sentence))
        self.assertIsNone(panel["residual_x"], "the forward record's (package J): it holds no twin row of this "
                                               "instance (no panel night ran here), and none is invented")
        self.assertEqual(panel["owed"], DR.PANEL_OWED)

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
