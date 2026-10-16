"""C1 (A45): THE SPAN BUY-AND-HOLD IN EACH DONE CHECKPOINT (league/ops/dlane_report.py `span_bh`; the rule itself in
league/equity/live.py `span_bh`, `b10_bh` and `refused_days`): each checkpoint's `by_program` row of a share program
carries `span_bh`, one entry a program version among the checkpoint's first K counts, read from the House's own bar
store (`eq_bars`, adjustment=all, one fetch) and open note (`eq_open_note`).

- THE RULE is the House's `_bh_pnl` with the scaling plan's one change (its 2.4): the sessions the House blocked the
  program from opening, while it held nothing in the symbol, are taken out of the span, which splits there. With no
  such session it is `_bh_pnl` to the Decimal (`TheRule`). A panel program's is B10, `date_record`'s.
- IN THE REPORT (`TheCheckpointCarriesIt`): one symbol, two symbols, a blocked run that splits the span, a panel
  program, a close missing (priced False, never a figure), the field frozen with its checkpoint, and every other key
  of the Done reading exactly as without it.
- THE PRODUCER AND THE CONSUMER AGREE (`TheScriptsChecks`): the scaling plan's script reads the field, checks it and
  rebuilds its figure; its own checks are copied below word for word and run on these reports. Where the script itself
  is at hand (`LTCM_SCALING_SCRIPT`: its path; its sha256 must be the pinned one) `TheScriptItself` runs it whole.

Every price, notional, close and day is invented."""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import tempfile
import types
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from league.equity import live as L
from league.equity import schedule as S
from league.live.state import LiveState
from league.swarm import dlane
from league.tests.test_dlane_report import ny
from league.tests.test_dlane_report_a14 import A14Fixture, R
from league.tests.test_equity_twins import add_tables, lot, put_lot

#: Invented adjustment=all closes, one fetch each.
SPY = {"2026-10-08": "600.00", "2026-10-09": "601.00", "2026-10-12": "603.00", "2026-10-13": "602.00",
       "2026-10-14": "609.00", "2026-10-15": "607.00", "2026-10-16": "606.00", "2026-10-19": "610.00"}
QQQ = {"2026-10-09": "498.00", "2026-10-12": "500.00", "2026-10-13": "505.00", "2026-10-14": "503.00",
       "2026-10-15": "508.00", "2026-10-16": "511.00", "2026-10-19": "509.00"}
#: F1's open note: Oct 14 refused in its open window and clear in its close window (a program could still open, and
#: `p-a` did), Oct 15 refused in every window (no program could open).
NOTE_F1 = {"2026-10-14": {"open": {"clear": False, "why": "the House is paused"}, "close": {"clear": True}},
           "2026-10-15": {"open": {"clear": False, "why": "the House is paused"},
                          "close": {"clear": False, "why": "the House is paused"}}}
#: The plan's script, pinned (its sha256): `TheScriptItself` runs it only when it is this one.
SCRIPT_SHA256 = "367a784d5d22d1501e6d320dd96a038a416aadaffc8bfef2972a90ba3555ede7"


def series(prices: dict, sha: str = "fetch-1") -> dict:
    """{day: (close, series sha)}, the shape `span_bh` reads the bar store in."""
    return {day: (close, sha) for day, close in prices.items()}


def leg(symbol: str, opened: str, exit_day: str, notional: str = "100") -> dict:
    return {"symbol": symbol, "opened_day": opened, "exit_day": exit_day, "entry_notional": notional}


# ================================================================================================== the rule
class TheRule(unittest.TestCase):
    """league/equity/live.py: `span_bh` is `_bh_pnl` but for the split; `b10_bh` is `date_record`'s B10."""

    def book(self, lots: list[dict], bars: dict[str, dict]) -> tuple[list, types.SimpleNamespace]:
        """`lots` and `bars` in a real book's tables, read back as the book reads them; a stand-in `self` for
        `EquityBook._bh_pnl` (its state, and no vendor: `_closes_again` reads nothing)."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = LiveState(Path(tmp.name) / "live.sqlite")
        self.addCleanup(state.close)
        add_tables(state)
        for i, x in enumerate(lots, 1):
            put_lot(state, lot(i, symbol=x["symbol"], opened_day=x["opened_day"], exit_day=x["exit_day"],
                               notional=x["entry_notional"]))
        for symbol, rows in bars.items():
            for day, (close, sha) in rows.items():
                state.execute("INSERT INTO eq_bars(day, symbol, adjustment, c, fetched_at, sha) VALUES(?,?,?,?,0,?)",
                              (day, symbol, "all", close, sha))
        read = [L.Lot.of(r) for r in state.rows("SELECT * FROM eq_lots ORDER BY lid")]
        return read, types.SimpleNamespace(state=state, _closes_again=lambda *a: {})

    def test_one_symbol_runs_from_the_close_before_the_first_entry_to_the_last_exit_and_is_bh_pnl(self):
        lots = [leg("SPY", "2026-10-12", "2026-10-13"), leg("SPY", "2026-10-15", "2026-10-16", "250"),
                leg("SPY", "2026-10-16", "2026-10-19", "40.5")]
        read, me = self.book(lots, {"SPY": series(SPY)})
        got = L.span_bh(read, {"SPY": series(SPY)})
        self.assertTrue(got["priced"], got["why"])
        self.assertEqual(got["usd"], L.EquityBook._bh_pnl(me, read), "to the Decimal")
        spy = got["symbols"]["SPY"]
        self.assertEqual((spy["before"], spy["last"]), ("2026-10-09", "2026-10-19"))
        self.assertEqual(spy["sessions"], S.sessions_between("2026-10-09", "2026-10-19"))
        self.assertEqual((spy["sessions"], spy["sessions_used"], spy["segments"]), (6, 6, [["2026-10-12", "2026-10-19"]]))
        self.assertEqual(set(spy["closes"]), {"2026-10-09", "2026-10-19"}, "one segment: its two ends")
        held = D(100) * 1 + D(250) * 1 + D("40.5") * 1                 # each lot held one session of the span
        self.assertEqual(spy["exposure"], held / 6)
        self.assertEqual(spy["usd"], held / 6 * (D("610.00") / D("601.00") - 1))
        self.assertEqual(spy["sha"], "fetch-1")
        # The same lots read from `eq_lots` rows (the report's way) or as Lots (the book's) give the one figure.
        self.assertEqual(L.span_bh(lots, {"SPY": series(SPY)})["usd"], got["usd"])

    def test_two_symbols_each_have_their_own_span_and_the_figure_is_their_sum(self):
        lots = [leg("SPY", "2026-10-13", "2026-10-14", "50"), leg("SPY", "2026-10-13", "2026-10-15", "50"),
                leg("QQQ", "2026-10-14", "2026-10-16", "75"), leg("QQQ", "2026-10-15", "2026-10-19", "25")]
        bars = {"SPY": series(SPY), "QQQ": series(QQQ, "fetch-2")}
        read, me = self.book(lots, bars)
        got = L.span_bh(read, bars)
        self.assertEqual(got["usd"], L.EquityBook._bh_pnl(me, read))
        spy, qqq = got["symbols"]["SPY"], got["symbols"]["QQQ"]
        self.assertEqual((spy["before"], spy["last"], spy["sessions"]), ("2026-10-12", "2026-10-15", 3))
        self.assertEqual((qqq["before"], qqq["last"], qqq["sessions"]), ("2026-10-13", "2026-10-19", 4))
        self.assertEqual((spy["sha"], qqq["sha"]), ("fetch-1", "fetch-2"), "a basis a symbol: one fetch each")
        self.assertEqual(spy["exposure"], (D(50) * 1 + D(50) * 2) / 3)
        self.assertEqual(qqq["exposure"], (D(75) * 2 + D(25) * 2) / 4)
        self.assertEqual(got["usd"], spy["usd"] + qqq["usd"])

    def test_a_blocked_run_held_empty_splits_the_span_and_a_blocked_session_held_does_not(self):
        lots = [leg("SPY", "2026-10-12", "2026-10-13"), leg("SPY", "2026-10-15", "2026-10-16"),
                leg("SPY", "2026-10-16", "2026-10-19")]
        bars = {"SPY": series(SPY)}
        whole = L.span_bh(lots, bars)
        # Oct 14 (held nothing) is taken out: two segments, the same held dollar-sessions over 5 sessions, not 6.
        got = L.span_bh(lots, bars, blocked={"2026-10-14"})
        spy = got["symbols"]["SPY"]
        self.assertEqual((spy["sessions"], spy["sessions_used"]), (6, 5))
        self.assertEqual(spy["segments"], [["2026-10-12", "2026-10-13"], ["2026-10-15", "2026-10-19"]])
        self.assertEqual(set(spy["closes"]), {"2026-10-09", "2026-10-13", "2026-10-14", "2026-10-19"})
        mean = D(300) / 5
        self.assertEqual(spy["exposure"], mean)
        self.assertEqual(got["usd"], mean * (D("602.00") / D("601.00") - 1) + mean * (D("610.00") / D("609.00") - 1))
        self.assertNotEqual(got["usd"], whole["usd"])
        # Oct 13 and Oct 16 are held: blocked or not, they stay; so does a day outside the span.
        held = L.span_bh(lots, bars, blocked={"2026-10-13", "2026-10-16", "2026-10-20"})
        self.assertEqual(held["usd"], whole["usd"])
        self.assertEqual(held["symbols"]["SPY"]["segments"], [["2026-10-12", "2026-10-19"]])
        # Oct 12 to Oct 15 (three sessions in a row) as one run.
        run = L.span_bh(lots, bars, blocked={"2026-10-14", "2026-10-15"})["symbols"]["SPY"]
        self.assertEqual(run["segments"], [["2026-10-12", "2026-10-13"], ["2026-10-16", "2026-10-19"]])

    def test_b10_is_date_records_spy_benchmark(self):
        from league.xs import book as xs_book

        lots = [{**leg("AAPL", "2026-10-13", "2026-10-15", "27.5"), "lid": 1, "closed_at": 3.0},
                {**leg("MSFT", "2026-10-13", "2026-10-15", "30"), "lid": 2, "closed_at": 4.0},
                {**leg("AAPL", "2026-10-16", "2026-10-19", "12.25"), "lid": 3, "closed_at": 5.0}]
        got = L.b10_bh(lots, series(SPY))
        self.assertTrue(got["priced"], got["why"])
        rows = [{**x, "status": "closed", "cash": "0", "probe": 1} for x in lots]
        record = xs_book.date_record(rows, {}, {d: D(c) for d, c in SPY.items()})
        self.assertEqual(got["usd"], record["bh_pnl"], "to the Decimal")
        self.assertEqual(set(got["closes"]), {"2026-10-12", "2026-10-15", "2026-10-19"})
        from league.xs import config as xs_config

        self.assertEqual(L.B10_SYMBOL, xs_config.REF[xs_config.MARKET_COLUMN])

    def test_unreadable_is_priced_false_with_why_never_a_figure(self):
        lots = [leg("SPY", "2026-10-12", "2026-10-13")]
        missing = {d: c for d, c in SPY.items() if d != "2026-10-09"}
        for got, words in ((L.span_bh(lots, {"SPY": series(missing)}), "2026-10-09"),
                           (L.span_bh(lots, {}), "no adjustment=all close"),
                           (L.span_bh(lots, {"SPY": {**series(SPY), "2026-10-13": ("602", "fetch-2")}}),
                            "not from one fetch"),
                           (L.span_bh(lots, {"SPY": {**series(SPY), "2026-10-09": ("0", "fetch-1")}}), "positive"),
                           (L.span_bh([leg("SPY", "2026-10-12", "2026-10-13", "0")], {"SPY": series(SPY)}),
                            "notional"),
                           (L.b10_bh(lots, series(missing)), "2026-10-09"),
                           (L.b10_bh([leg("AAPL", "", "2026-10-13")], series(SPY)), "entry day")):
            self.assertFalse(got["priced"])
            self.assertIsNone(got["usd"])
            self.assertIn(words, got["why"])

    def test_a_close_or_a_figure_a_float_cannot_hold_is_priced_false(self):
        """F6 of the review: a Decimal holds 1e400, a float (the report's JSON) does not: never Infinity."""
        lots = [leg("SPY", "2026-10-12", "2026-10-13")]
        huge = {**series(SPY), "2026-10-13": ("1e400", "fetch-1")}
        apart = {**series(SPY), "2026-10-09": ("1e-200", "fetch-1"), "2026-10-13": ("1e200", "fetch-1")}
        for got, words in ((L.span_bh(lots, {"SPY": huge}), "finite"),
                           (L.span_bh(lots, {"SPY": apart}), "float's range"),
                           (L.span_bh([leg("SPY", "2026-10-12", "2026-10-13", "1e400")], {"SPY": series(SPY)}),
                            "float's range"),
                           (L.b10_bh(lots, huge), "finite"),
                           (L.b10_bh(lots, apart), "float's range")):
            self.assertEqual((got["priced"], got["usd"]), (False, None))
            self.assertIn(words, got["why"])

    def test_the_open_note_is_read_by_one_rule(self):
        note = {"2026-10-13": {"open": {"clear": False, "why": "the House is paused"}, "close": {"clear": True}},
                "2026-10-14": {"open": {"clear": True}, "close": {"clear": True}},
                "2026-10-15": {"close": {"clear": False, "why": "the gateway's kill switch is engaged"}},
                "2026-10-16": {"open": {"clear": False, "why": "the House is paused"},
                               "close": {"clear": False, "why": "the House is paused"}},
                "2026-10-19": {"open": {"clear": False}, "close": "not a window"},
                "not a day": {"open": {"clear": False}}}
        self.assertEqual(L.refused_days(note), {"2026-10-13": "open window: the House is paused",
                                                "2026-10-15": "close window: the gateway's kill switch is engaged",
                                                "2026-10-16": "open window: the House is paused",
                                                "2026-10-19": "open window: refused"})
        self.assertEqual(L.refused_days(None), {})
        me = types.SimpleNamespace(state=types.SimpleNamespace(get=lambda key, default=None: note))
        self.assertEqual(L.EquityBook._refused_days(me), L.refused_days(note), "the book's reader is the same rule")
        # C1's blocked sessions: EVERY window the note names refused. Oct 13's close was clear: a program could open.
        self.assertEqual(sorted(L.shut_days(note)), ["2026-10-15", "2026-10-16"])
        self.assertEqual((L.shut_days(None), L.shut_days({"2026-10-20": {}})), ({}, {}))
        self.assertEqual((R.OPEN_NOTE_KEY, R.SPAN_BASIS), (L.OPEN_NOTE_KEY, L.SPAN_BASIS))

    def test_the_entry_days_left_out_are_every_entry_day_of_the_versions_lots_in_the_book(self):
        """F1's second half: not only the counted lots' entry days, so a lot that closes after the K-th count cannot
        make a session blocked at K and not at a later checkpoint."""
        def closed(lid, opened, exit_day, version=1):
            return {"equity": True, "family": "p", "version": version, "symbol": "SPY", "opened_day": opened,
                    "day": exit_day, "notional": D("100"), "closed_at": float(lid), "lid": lid, "panel": False}

        def row(lid, opened, version=1, status="closed"):
            return {"lid": lid, "instance": f"p@{version}:r", "family": "p", "version": version, "symbol": "SPY",
                    "opened_day": opened, "status": status}

        counted = [closed(1, "2026-10-12", "2026-10-13"), closed(2, "2026-10-16", "2026-10-19")]
        book = {"bars": [{"day": d, "symbol": "SPY", "c": c, "sha": "f"} for d, c in SPY.items()], "spy": [],
                "open_note": {d: NOTE_F1["2026-10-15"] for d in ("2026-10-14", "2026-10-15")}}
        bare = R.span_bh(counted, {**book, "lots": []})["p"][0]["blocked"]
        self.assertEqual(bare, [["2026-10-14", "2026-10-15"]])
        # A lot of this version opened on Oct 14 (still open, or closed after these counts) leaves Oct 14 out; another
        # version's lot does not.
        for lots, want in (([row(3, "2026-10-14", status="open")], [["2026-10-15", "2026-10-15"]]),
                           ([row(3, "2026-10-14", version=2)], bare)):
            self.assertEqual(R.span_bh(counted, {**book, "lots": lots})["p"][0]["blocked"], want)

    def test_the_reports_reader_never_raises_and_names_what_it_could_not_read(self):
        """F7 of the review: every read of the book is inside the reader's guard; nothing reaches the meter."""
        from league.equity import bands as EB

        counted = [{"equity": True, "family": "p", "version": 1, "symbol": "SPY", "opened_day": "2026-10-12",
                    "day": "2026-10-13", "notional": D("100"), "closed_at": 1.0, "lid": 1, "panel": False}]
        good = {"bars": [{"day": d, "symbol": "SPY", "c": c, "sha": "f"} for d, c in SPY.items()], "spy": [],
                "open_note": {}, "lots": []}
        self.assertTrue(R.span_bh(counted, good)["p"][0]["priced"])
        for name, book, patcher in (("bars not rows", {**good, "bars": [1, 2]}, None),
                                    ("lots not rows", {**good, "lots": ["x"]}, None),
                                    ("the seat rule raises", good,
                                     mock.patch.object(EB, "seat_settings", side_effect=RuntimeError("boom"))),
                                    ("the note's reader raises", good,
                                     mock.patch.object(L, "shut_days", side_effect=KeyError("x")))):
            with patcher or contextlib.nullcontext():
                entry, = R.span_bh(counted, book)["p"]
            self.assertEqual((entry["priced"], entry["usd"]), (False, None), name)
            self.assertIn("could not be read", entry["why"], name)
        self.assertEqual(R.span_bh([None, 3], good), {}, "closes that name no program: no entry")


# ================================================================================================== in the report
class SpanFixture(A14Fixture):
    """Thirty equity closes of two programs whose checkpoint holds and is final (A14 scripted, as `A14Fixture`), with
    the bar store's adjustment=all closes and, where a test says so, the House's open note."""

    def setUp(self):
        super().setUp()
        self.bars("SPY", SPY)
        self.bars("QQQ", QQQ, sha="fetch-2")

    def bars(self, symbol: str, prices: dict, *, sha: str = "fetch-1") -> None:
        for day, close in prices.items():
            self.live.upsert("eq_bars", {"day": day, "symbol": symbol, "adjustment": "all", "o": close, "h": close,
                                         "l": close, "c": close, "v": "1000", "fetched_at": 0.0, "sha": sha,
                                         "audit": None}, "day, symbol, adjustment")

    def lot_of(self, family: str, symbol: str, opened: str, exit_day: str, *, notional: str, lane: str,
               i: int, tag: str = "", klass: str = "etf") -> None:
        lid = self.eq_close(family, symbol=symbol, klass=klass, day=opened, exit_day=exit_day, notional=notional,
                            cash="1.00", lane=lane, posted=True, closed_at=ny(exit_day, 15, 56) + i)
        if tag:
            self.live.db.execute("UPDATE eq_lots SET tag=? WHERE lid=?", (tag, lid))
        self.twin(lid, live_r=0.01, twin_r=0.0105, notional=float(notional), bh=0.5)

    def one(self, n: int = 15) -> None:
        """`p-one`: SPY only, n lots, a third each of Oct 12-13, Oct 15-16 and Oct 16-19, $100 each."""
        self.eq_family("p-one")
        days = [("2026-10-12", "2026-10-13"), ("2026-10-15", "2026-10-16"), ("2026-10-16", "2026-10-19")]
        for i in range(n):
            self.lot_of("p-one", "SPY", *days[i * 3 // n], notional="100", lane="beta", i=i)

    def two(self, n: int = 15) -> None:
        """`p-two`: SPY Oct 13-14 and QQQ Oct 14-16, $50 each."""
        self.eq_family("p-two", lane="equity")
        for i in range(n):
            symbol, days = ("SPY", ("2026-10-13", "2026-10-14")) if i < n // 2 else ("QQQ", ("2026-10-14", "2026-10-16"))
            self.lot_of("p-two", symbol, *days, notional="50", lane="equity", i=100 + i)

    def panel(self, dates: int = 5) -> None:
        """`xs-p`: a panel program, two stock lots (AAPL, MSFT) a close date: `dates` Done counts."""
        spec = {"id": "xs-p", "mechanism": "a published cross-sectional prior long enough for the store",
                "structure": "stock", "roots": ["AAPL"], "lane": "equity"}
        self.store.add_family(spec, origin="architect")
        self.store.set_band("xs-p", "probe", reason="fixture")
        pairs = [("2026-10-12", "2026-10-13"), ("2026-10-13", "2026-10-14"), ("2026-10-14", "2026-10-15"),
                 ("2026-10-15", "2026-10-16"), ("2026-10-16", "2026-10-19")][:dates]
        for j, (opened, exit_day) in enumerate(pairs):
            for k, symbol in enumerate(("AAPL", "MSFT")):
                self.lot_of("xs-p", symbol, opened, exit_day, notional="27.50", lane="equity", i=200 + 2 * j + k,
                            tag=R.PANEL_TAG, klass="stock")

    def build(self) -> None:
        self.one()
        self.two()
        self.steady()

    def forty(self) -> None:
        """Forty counts (F1 of the review): `p-a` (SPY) closes 10 lots Oct 12-13 and, from the 30th count, 10 lots Oct
        16-19; the lot it opened on Oct 14 (the House refused that session's open window, its close window was clear)
        closes 40th, after them all. `p-b` (QQQ) closes 19 lots Oct 12-13. Oct 15 is refused in every window."""
        self.eq_family("p-a")
        self.eq_family("p-b", lane="equity")
        for i in range(10):
            self.lot_of("p-a", "SPY", "2026-10-12", "2026-10-13", notional="100", lane="beta", i=i)
        for i in range(19):
            self.lot_of("p-b", "QQQ", "2026-10-12", "2026-10-13", notional="50", lane="equity", i=20 + i)
        for i in range(10):
            self.lot_of("p-a", "SPY", "2026-10-16", "2026-10-19", notional="100", lane="beta", i=50 + i)
        self.lot_of("p-a", "SPY", "2026-10-14", "2026-10-19", notional="100", lane="beta", i=999)
        self.live.put(R.OPEN_NOTE_KEY, NOTE_F1)
        self.steady()

    def checkpoint(self, out: dict) -> dict:
        """The checkpoint over every one of the thirty counts. Since the owner's change (A50, Oct 16, 2026) thirty counts
        are four checkpoints, the 15th, 20th, 25th and 30th (one, the 30th, before): each carries its own span_bh."""
        cps = out["done"]["all"]["checkpoints"]
        self.assertEqual([c["at_close"] for c in cps], [15, 20, 25, 30])
        return cps[-1]

    @staticmethod
    def spans(cp: dict) -> dict:
        return {p["family"]: p.get("span_bh") for p in cp["by_program"]}


class TheCheckpointCarriesIt(SpanFixture):
    def test_one_symbol_and_two_symbols_each_carry_their_span_in_the_checkpoints_row(self):
        self.build()
        out = self.report()
        cp = self.checkpoint(out)
        self.assertEqual((cp["holds"], cp["final"]), (True, True))
        spans = self.spans(cp)
        self.assertEqual(sorted(spans), ["p-one", "p-two"])
        one, = spans["p-one"]
        self.assertEqual({k: one[k] for k in ("version", "priced", "why", "basis", "blocked", "spy", "lots")},
                         {"version": 1, "priced": True, "why": None, "basis": "adjustment=all", "blocked": [],
                          "spy": None, "lots": 15})
        spy = one["symbols"]["SPY"]
        self.assertEqual({k: spy[k] for k in ("before", "last", "sessions", "sessions_used", "segments",
                                              "close_before", "close_last", "sha")},
                         {"before": "2026-10-09", "last": "2026-10-19", "sessions": 6, "sessions_used": 6,
                          "segments": [["2026-10-12", "2026-10-19"]], "close_before": 601.0, "close_last": 610.0,
                          "sha": "fetch-1"})
        self.assertEqual(spy["closes"], {"2026-10-09": 601.0, "2026-10-19": 610.0})
        self.assertEqual(spy["exposure_usd"], 250.0, "15 lots of $100 held one session each, over 6 sessions")
        self.assertEqual(one["usd"], round(250 * (610 / 601 - 1), 2))
        self.assertEqual(one["usd"], spy["usd"])
        two, = spans["p-two"]
        self.assertEqual(sorted(two["symbols"]), ["QQQ", "SPY"])
        self.assertEqual((two["symbols"]["SPY"]["before"], two["symbols"]["SPY"]["last"]), ("2026-10-12", "2026-10-14"))
        self.assertEqual((two["symbols"]["QQQ"]["before"], two["symbols"]["QQQ"]["last"]), ("2026-10-13", "2026-10-16"))
        self.assertAlmostEqual(two["usd"], two["symbols"]["SPY"]["usd"] + two["symbols"]["QQQ"]["usd"], delta=0.011)
        self.assertIn("open note", one["blocked_from"])
        # The running figures (never a reading) carry none.
        self.assertTrue(all("span_bh" not in p for p in out["done"]["all"]["running"]["by_program"]))

    def test_a_blocked_run_splits_the_span_and_an_entry_day_is_never_blocked(self):
        self.build()
        self.live.put(R.OPEN_NOTE_KEY, {
            "2026-10-12": {"open": {"clear": False, "why": "the House is paused"}},   # p-one opened lots that day
            "2026-10-14": {"open": {"clear": False, "why": "the House is paused"}},   # held empty by p-one
            "2026-10-15": {"close": {"clear": True}}})
        spans = self.spans(self.checkpoint(self.report()))
        one, = spans["p-one"]
        self.assertTrue(one["priced"], one["why"])
        self.assertEqual(one["blocked"], [["2026-10-14", "2026-10-14"]])
        spy = one["symbols"]["SPY"]
        self.assertEqual((spy["sessions"], spy["sessions_used"]), (6, 5))
        self.assertEqual(spy["segments"], [["2026-10-12", "2026-10-13"], ["2026-10-15", "2026-10-19"]])
        self.assertEqual(spy["closes"], {"2026-10-09": 601.0, "2026-10-13": 602.0, "2026-10-14": 609.0,
                                         "2026-10-19": 610.0})
        self.assertEqual(spy["exposure_usd"], 300.0)
        self.assertEqual(one["usd"], round(300 * (602 / 601 - 1) + 300 * (610 / 609 - 1), 2))
        # p-two opened QQQ lots on Oct 14: that session did not block it, so nothing is listed and nothing is split.
        two, = spans["p-two"]
        self.assertEqual(two["blocked"], [])
        self.assertEqual({s: x["sessions_used"] == x["sessions"] for s, x in two["symbols"].items()},
                         {"QQQ": True, "SPY": True})

    def test_a_panel_program_carries_b10_from_the_spy_closes(self):
        self.one()
        self.two(10)
        self.panel()
        self.steady()
        cp = self.checkpoint(self.report())
        xs, = self.spans(cp)["xs-p"]
        self.assertTrue(xs["priced"], xs["why"])
        self.assertEqual((xs["symbols"], xs["blocked"], xs["lots"]), ({}, [], 10))
        self.assertEqual(xs["blocked_from"], R.SPAN_B10)
        self.assertEqual(xs["spy"]["closes"], {d: float(SPY[d]) for d in
                                               ("2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15",
                                                "2026-10-16", "2026-10-19")})
        expected = sum(2 * 27.5 * (float(SPY[x]) / float(SPY[b]) - 1) for b, x in (
            ("2026-10-09", "2026-10-13"), ("2026-10-12", "2026-10-14"), ("2026-10-13", "2026-10-15"),
            ("2026-10-14", "2026-10-16"), ("2026-10-15", "2026-10-19")))
        self.assertEqual(xs["usd"], round(expected, 2))
        self.assertEqual(xs["spy"]["usd"], xs["usd"])

    def test_a_missing_close_is_priced_false_and_the_reading_does_not_move(self):
        self.build()
        whole = self.report()
        self.live.db.execute("DELETE FROM eq_bars WHERE symbol='SPY' AND day='2026-10-09'")
        out = self.report()
        cp, was = self.checkpoint(out), self.checkpoint(whole)
        one, = self.spans(cp)["p-one"]
        self.assertEqual((one["priced"], one["usd"], one["symbols"]), (False, None, {}))
        self.assertIn("SPY", one["why"])
        self.assertIn("2026-10-09", one["why"])
        self.assertTrue(self.spans(cp)["p-two"][0]["priced"], "p-two's span starts after it")
        self.assertEqual({k: v for k, v in cp.items() if k != "by_program"},
                         {k: v for k, v in was.items() if k != "by_program"})
        # An open note that cannot be read, or the seat rule first-come (the House keeps no note): priced False.
        self.live.put(R.OPEN_NOTE_KEY, ["not", "a", "note"])
        one, = self.spans(self.checkpoint(self.report()))["p-two"]
        self.assertEqual((one["priced"], one["usd"]), (False, None))
        self.assertIn("cannot be read", one["why"])
        self.live.put(R.OPEN_NOTE_KEY, {})
        from league.equity import bands as EB

        with mock.patch.object(EB, "seat_settings", return_value=EB.SEAT_FALLBACK):
            one, = self.spans(self.checkpoint(self.report()))["p-two"]
        self.assertEqual((one["priced"], one["usd"]), (False, None))
        self.assertIn("first-come", one["why"])

    def test_the_field_is_frozen_with_its_checkpoint(self):
        self.build()
        first = self.report()
        span = self.spans(self.checkpoint(first))
        self.assertTrue(self.checkpoint(first)["final"])
        # A later fetch rewrites the closes (a dividend's adjustment, a new sha): a new reading would differ ...
        self.bars("SPY", {d: f"{float(c) - 1.5:.2f}" for d, c in SPY.items()}, sha="fetch-9")
        fresh = self.spans(self.checkpoint(self.report()))
        self.assertNotEqual(fresh["p-one"], span["p-one"])
        # ... but the report that follows the one that read it final carries it as it was: never recomputed.
        second = self.report(previous=first)
        cp = self.checkpoint(second)
        self.assertTrue(cp["frozen"])
        self.assertEqual(self.spans(cp), span)
        self.assertEqual(self.spans(self.checkpoint(self.report(previous=second))), span)

    def test_no_done_rule_count_or_reading_moves(self):
        self.build()
        self.live.put(R.OPEN_NOTE_KEY, {"2026-10-14": {"open": {"clear": False, "why": "the House is paused"}}})
        out = self.report()
        with mock.patch.object(R, "span_bh", return_value={}):
            bare = self.report()
        self.assertEqual(out["rule"], bare["rule"])
        self.assertEqual(out["rule"]["sha256"], dlane.DONE["rule_sha256"])
        for meter in ("all", "screen"):
            got, was = out["done"][meter], bare["done"][meter]
            self.assertEqual({k: v for k, v in got.items() if k != "checkpoints" and k != "latest"},
                             {k: v for k, v in was.items() if k != "checkpoints" and k != "latest"})
            strip = [{**cp, "by_program": [{k: v for k, v in p.items() if k != "span_bh"} for p in cp["by_program"]]}
                     for cp in got["checkpoints"]]
            self.assertEqual(strip, was["checkpoints"], "span_bh is the one key added")
            self.assertTrue(any("span_bh" in p for cp in got["checkpoints"] for p in cp["by_program"]))
        self.assertEqual(out["done"]["without_seeded"]["all"]["holds"], bare["done"]["without_seeded"]["all"]["holds"])


    def test_a_versions_blocked_list_is_the_same_at_every_checkpoint(self):
        """F1 of the review: the House's `refused_days` reads ONE refused window as a refused session, and C1 left out
        only the counted lots' entry days, so Oct 14 (refused at the open, clear at the close, and `p-a` opened a lot
        at it that closes after the 30th count) was blocked at K=30 and not at K=40: no one ledger could pass both.
        Now a session is blocked only when every window was refused, less every entry day of the version's lots in
        the book."""
        self.forty()
        out = self.report()
        cps = {cp["at_close"]: cp for cp in out["done"]["all"]["checkpoints"]}
        # A50's checkpoints (the 15th count, then every 5th; the 30th and the 40th before): C1 at each of them. At the
        # 15th, 20th and 25th count `p-a`'s span ends Oct 13, so Oct 15 lies outside it and none is listed.
        self.assertEqual(sorted(cps), [15, 20, 25, 30, 35, 40])
        for k in (15, 20, 25):
            early, = self.spans(cps[k])["p-a"]
            self.assertEqual((early["priced"], early["blocked"]), (True, []), (k, early["why"]))
        a30, = self.spans(cps[30])["p-a"]
        a40, = self.spans(cps[40])["p-a"]
        self.assertTrue(a30["priced"] and a40["priced"], (a30["why"], a40["why"]))
        self.assertIn("2026-10-14", L.refused_days(NOTE_F1), "the idle clock's reading: refused")
        self.assertEqual(a30["blocked"], [["2026-10-15", "2026-10-15"]])
        self.assertEqual(a40["blocked"], a30["blocked"], "the same list at K=30 and K=40")
        # Oct 15 is held empty at K=30, so the span splits there; at K=40 the Oct 14 lot holds it, so nothing splits.
        self.assertEqual(a30["symbols"]["SPY"]["segments"],
                         [["2026-10-12", "2026-10-14"], ["2026-10-16", "2026-10-19"]])
        self.assertEqual(a40["symbols"]["SPY"]["segments"], [["2026-10-12", "2026-10-19"]])
        self.assertEqual([e["blocked"] for e in self.spans(cps[30])["p-b"] + self.spans(cps[40])["p-b"]], [[], []])

    def test_no_figure_a_float_cannot_hold_reaches_the_report(self):
        """F6 of the review: a close of 1e400 is a Decimal and Infinity in JSON; it gives priced False and a why."""
        self.build()
        self.bars("SPY", {"2026-10-19": "1e400"})
        out = self.report()
        one, = self.spans(self.checkpoint(out))["p-one"]
        self.assertEqual((one["priced"], one["usd"], one["symbols"]), (False, None, {}))
        self.assertIn("finite", one["why"])
        json.dumps(out, allow_nan=False)                     # raises on an Infinity anywhere in the report

    def test_the_book_is_read_for_spy_and_the_symbols_of_programs_that_are_no_panels(self):
        """F8 of the review: B10 reads SPY alone, so a basket's names' closes are not read."""
        self.one()
        self.two(10)
        self.panel()
        self.bars("AAPL", {d: "230.00" for d in SPY}, sha="fetch-3")
        self.bars("MSFT", {d: "420.00" for d in SPY}, sha="fetch-4")
        self.bars("IWM", {d: "220.00" for d in SPY}, sha="fetch-5")      # no closed lot holds it
        book = R.read_book(self.root / R.LIVE_DB)
        self.assertEqual(sorted({r["symbol"] for r in book["bars"]}), ["QQQ", "SPY"])
        self.assertEqual({r["sha"] for r in book["bars"] if r["symbol"] == "SPY"}, {"fetch-1"})


# ================================================================================================== the consumer
# THE PLAN'S SCRIPT'S OWN SPAN CHECKS, COPIED: the scaling plan's script (A45; sha256 367a784d5d22d150..., pinned with
# the plan) `span_entry`, `closes_from_entry`, the benchmark lines of `share_stat` and `panel_stat`, `blocked_sessions`
# and the usd check of `_share_program_stat`, word for word but for the calendar, which is the House's here
# (league/equity/schedule.py; `TheScriptItself` holds the two calendars equal where the script is at hand).
CLOSES_BASIS = "adjustment=all"


def _d(x) -> dt.date:
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x)[:10])


def previous_session(d) -> dt.date:
    return S.previous_session(_d(d))


def sessions_between(a, b) -> int:
    return S.sessions_between(_d(a), _d(b))


def sessions_in(a, b) -> list:
    out, d = [], _d(a)
    while d < _d(b):
        d += dt.timedelta(days=1)
        if S.is_session(d):
            out.append(d)
    return out


def _num(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if math.isfinite(v) else None


def span_entry(cp: dict, family: str, version):
    for bp in cp.get("by_program") or []:
        if not isinstance(bp, dict) or str(bp.get("family")) != family or not bp.get("span_bh"):
            continue
        entries = bp["span_bh"] if isinstance(bp["span_bh"], list) else [bp["span_bh"]]
        for en in entries:
            if isinstance(en, dict) and en.get("version") in (None, version):
                return en
    return None


def closes_from_entry(en: dict, lots: list) -> tuple:
    if en.get("priced") is False:
        return None, None, f"span_bh is not priced ({en.get('why')})"
    if en.get("basis") not in (None, CLOSES_BASIS):
        return None, None, f"span_bh basis {en.get('basis')!r} is not {CLOSES_BASIS}"
    syms = en.get("symbols") or {}
    if isinstance(syms, list):
        syms = {str(x.get("symbol")): x for x in syms if isinstance(x, dict)}
    out = {}
    panel = bool(lots and lots[0].get("panel"))
    for s in sorted({l["sym"] for l in lots}) if not panel else []:
        e = syms.get(s)
        if not isinstance(e, dict):
            return None, None, f"span_bh has no entry for {s}"
        mine = [l for l in lots if l["sym"] == s]
        before = previous_session(min(l["o"] for l in mine)).isoformat()
        last = max(l["x"] for l in mine).isoformat()
        if str(e.get("before"))[:10] != before:
            return None, None, f"span_bh {s}: before {e.get('before')} is not the session before the first entry"
        if str(e.get("last"))[:10] != last:
            return None, None, f"span_bh {s}: last {e.get('last')} is not the last exit day {last}"
        if e.get("sessions") is not None and int(e["sessions"]) != max(1, sessions_between(before, last)):
            return None, None, f"span_bh {s}: sessions {e.get('sessions')} is not the calendar's count"
        c0, c1 = _num(e.get("close_before")), _num(e.get("close_last"))
        if not c0 or not c1:
            return None, None, f"span_bh {s}: a close is missing"
        cl = {str(k)[:10]: v for k, v in (e.get("closes") or {}).items()} if isinstance(e.get("closes"), dict) else {}
        out[s] = {**cl, before: c0, last: c1}
    spy = None
    if isinstance(en.get("spy"), dict):
        sp = en["spy"]
        spy = {str(k)[:10]: v for k, v in (sp.get("closes") or {}).items()} if isinstance(sp.get("closes"), dict) else {}
        c0, c1 = _num(sp.get("close_before")), _num(sp.get("close_last"))
        if c0 and c1:
            spy.update({str(sp.get("before"))[:10]: c0, str(sp.get("last"))[:10]: c1})
    return out, spy, None


def share_d(lots: list, closes: dict, blocked=frozenset()):
    """`share_stat`'s D (its lines, from `idx_by_sym` to `D += d_s`): (D, None) or (None, why)."""
    from collections import defaultdict

    idx_by_sym = defaultdict(list)
    for i, l in enumerate(lots):
        idx_by_sym[l["sym"]].append(i)
    D_ = 0.0
    for s, idx in sorted(idx_by_sym.items()):
        mine = [lots[i] for i in idx]
        before = previous_session(min(l["o"] for l in mine))
        last = max(l["x"] for l in mine)
        days = sessions_in(before, last)
        e = {d: 0.0 for d in days}
        weights = []
        for l in mine:
            held = sessions_in(l["o"], l["x"]) or [l["x"]]
            for d in held:
                if d in e:
                    e[d] += l["N"]
            weights.append(l["N"] * max(1, len(held)))
        keep = [d for d in days if not (d in blocked and e[d] == 0.0)] or list(days) or [last]
        pos = {d: i for i, d in enumerate(days)}
        segs = []
        for d in keep:
            if segs and d in pos and segs[-1][-1] in pos and pos[d] == pos[segs[-1][-1]] + 1:
                segs[-1].append(d)
            else:
                segs.append([d])
        ebar = sum(weights) / max(1, len(keep))
        cs = closes.get(s) or {}
        d_s = 0.0
        for seg in segs:
            b0 = previous_session(seg[0]).isoformat()
            c0, c1 = _num(cs.get(b0)), _num(cs.get(seg[-1].isoformat()))
            if not c0 or not c1 or c0 <= 0:
                return None, f"span buy-and-hold unpriced: no adjustment=all close of {s} on {b0} and {seg[-1]}"
            d_s += ebar * (c1 / c0 - 1.0)
        D_ += d_s
    return D_, None


def panel_d(lots: list, spy: dict | None):
    """`panel_stat`'s D (its lines, from `D, d_alloc` to `D += d`): (D, None) or (None, why)."""
    if not spy:
        return None, "no SPY closes for the panel's B10 benchmark (span_bh.spy or --closes SPY)"
    D_ = 0.0
    for l in lots:
        b0 = previous_session(l["o"]).isoformat()
        c0, c1 = _num(spy.get(b0)), _num(spy.get(l["x"].isoformat()))
        if not c0 or not c1 or c0 <= 0:
            return None, f"B10 unpriced: no adjustment=all SPY close on {b0} and {l['x']}"
        D_ += l["N"] * (c1 / c0 - 1.0)
    return D_, None


def blocked_sessions(blocked: list, key: str) -> frozenset:
    fam = key.split("|")[1] if "|" in key else key
    out = set()
    for b in blocked:
        if b["program"] in ("*", key, fam):
            out.update(d for d in sessions_in(previous_session(b["from"]), b["to"]))
    return frozenset(out)


def numbered(rows: list, eqmap: dict) -> list:
    """The script's `numbered` (Done's counts: a panel program's lots of one NY day are one count), as copied above."""
    seen, out = {}, []
    for r in rows:
        if r.get("label") == "EQUITY (PANEL)":
            key = ("panel", str(r.get("family")), str((eqmap.get(str(r.get("pid"))) or {}).get("day"))[:10])
        else:
            key = ("close", str(r.get("pid")))
        if key not in seen:
            seen[key] = len(seen) + 1
        out.append(seen[key])
    return out


def script_check(report: dict, family: str, version: int, ledger_blocked: list | None = None,
                 at: int | None = None) -> tuple:
    """The script's path for one share program at the checkpoint of `at` counts (the latest when None): (span check
    ok, why). Its lots are joined as `_lots_of` joins them (`done.all.closes` with `equity.closes` by pid), over that
    checkpoint's window (the closes of its first K counts)."""
    rep = json.loads(json.dumps(report))                      # the file the script reads: JSON, nothing else
    cps = rep["done"]["all"]["checkpoints"]
    cp = cps[-1] if at is None else next(c for c in cps if c["at_close"] == at)
    eqmap = {str(e["pid"]): e for e in rep["equity"]["closes"]}
    rows = rep["done"]["all"]["closes"]
    lots = []
    for r, n in zip(rows, numbered(rows, eqmap)):
        e = eqmap.get(str(r["pid"]))
        if n > cp["at_close"] or r["family"] != family or not e or e.get("version") != version:
            continue
        lots.append({"pid": r["pid"], "sym": str(e["symbol"]), "N": _num(e["notional_usd"]), "o": _d(e["opened_day"]),
                     "x": _d(e["day"]), "panel": r.get("label") == "EQUITY (PANEL)"})
    en = span_entry(cp, family, version)
    if en is None:
        return False, "no entry"
    cl, spy_cl, why = closes_from_entry(en, lots)
    if why:
        return False, why
    key = f"eq|{family}|v{version}"
    D_, why = panel_d(lots, spy_cl) if lots[0]["panel"] else share_d(lots, cl, blocked_sessions(ledger_blocked or [], key))
    if why:
        return False, why
    ok = abs(_num(en["usd"]) - D_) <= 0.02 + 0.01 * len(lots)
    return ok, None if ok else "span_bh usd does not match the rebuilt benchmark"


class TheScriptsChecks(SpanFixture):
    def test_the_scripts_checks_hold_on_one_and_two_symbols_and_a_panel(self):
        self.one()
        self.two(10)
        self.panel()
        self.steady()
        out = self.report()
        for family in ("p-one", "p-two", "xs-p"):
            self.assertEqual(script_check(out, family, 1), (True, None), family)

    def test_a_split_holds_only_with_the_same_blocked_sessions_in_the_ledger(self):
        """THE ONE PLACE THE TWO DIFFER: the script reads the blocked sessions from the captain's ledger, never from
        this field, and rebuilds the figure with them. So the ledger must carry each entry's `blocked`, program by
        program: without it the rebuilt figure is unsplit and the check fails closed."""
        self.build()
        self.live.put(R.OPEN_NOTE_KEY, {"2026-10-14": {"open": {"clear": False, "why": "the House is paused"}}})
        out = self.report()
        one, = self.spans(self.checkpoint(out))["p-one"]
        ledger = [{"program": "eq|p-one|v1", "from": a, "to": z, "why": "House blocked (C1)"} for a, z in one["blocked"]]
        self.assertEqual(script_check(out, "p-one", 1, ledger), (True, None))
        self.assertEqual(script_check(out, "p-one", 1), (False, "span_bh usd does not match the rebuilt benchmark"))
        self.assertEqual(script_check(out, "p-two", 1, ledger), (True, None), "another program's block is not its")

    def test_one_ledger_passes_every_checkpoint_of_a_version(self):
        self.forty()
        out = self.report()
        blocked = {tuple(r) for cp in out["done"]["all"]["checkpoints"] for e in self.spans(cp)["p-a"]
                   for r in e["blocked"]}
        ledger = [{"program": "eq|p-a|v1", "from": a, "to": z, "why": "House blocked (C1)"} for a, z in sorted(blocked)]
        self.assertEqual(ledger[0]["from"], "2026-10-15")
        # Every one of the owner's checkpoints (A50: the 15th count, then every 5th; 30 and 40 before).
        for k in (15, 20, 25, 30, 35, 40):
            self.assertEqual(script_check(out, "p-a", 1, ledger, at=k), (True, None), k)
            self.assertEqual(script_check(out, "p-b", 1, ledger, at=k), (True, None), k)
        # A ledger on the idle clock's reading (one refused window enough) would hold Oct 14 too: it fails closed where
        # the span holds Oct 14 (from the 30th count; before it `p-a`'s span ends Oct 13).
        old = ledger + [{"program": "eq|p-a|v1", "from": "2026-10-14", "to": "2026-10-14", "why": "one window"}]
        self.assertEqual([script_check(out, "p-a", 1, old, at=k)[0] for k in (30, 40)], [False, False])

    def test_a_tampered_or_unpriced_field_fails_the_scripts_checks(self):
        self.build()
        out = self.report()
        cp = self.checkpoint(out)
        row = next(p for p in cp["by_program"] if p["family"] == "p-one")
        row["span_bh"][0]["symbols"]["SPY"]["before"] = "2026-10-08"
        self.assertIn("before", script_check(out, "p-one", 1)[1])
        row["span_bh"][0]["priced"] = False
        self.assertIn("not priced", script_check(out, "p-one", 1)[1])


@unittest.skipUnless(os.environ.get("LTCM_SCALING_SCRIPT"), "the scaling plan's script is not at hand "
                                                           "(LTCM_SCALING_SCRIPT: its path)")
class TheScriptItself(SpanFixture):
    """The plan's script run whole on these reports (`run`: its gate, its window, its span checks), when it is the pinned
    one; and its calendar against the House's."""

    #: THE OWNER'S CHANGE OF THE DONE RULE (A50, Oct 16, 2026): the pinned plan (scale30k-v1, A45) gates on the Oct 9
    #: rule, its sha 0d007696 and its checkpoints 30, 40, ...; the owner's are 15, 20, 25, ... under sha 9693fe00. Until
    #: the plan is re-pinned for them it refuses every report this release writes, printing no figure: the tests that run
    #: it whole are skipped, saying so, and `test_the_pinned_plan_refuses_the_owners_checkpoints` holds the refusal.
    OWED = ("the pinned plan (scale30k-v1, A45) reads the Oct 9 rule's checkpoints (30, 40, ...; sha 0d007696), not the "
            "owner's (A50: 15, 20, ...): its re-pin is owed before it can read a checkpoint")

    @classmethod
    def setUpClass(cls):
        path = Path(os.environ["LTCM_SCALING_SCRIPT"]).expanduser()
        if hashlib.sha256(path.read_bytes()).hexdigest() != SCRIPT_SHA256:
            raise unittest.SkipTest("the script at LTCM_SCALING_SCRIPT is not the pinned one")
        spec = importlib.util.spec_from_file_location("scaling_script", path)
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)
        cls.on_this_rule = ((cls.script.FIRST_CHECKPOINT, cls.script.CHECKPOINT_EVERY, cls.script.RULE_SHA256)
                            == (dlane.DONE["first_checkpoint"], dlane.DONE["checkpoint_every"], dlane.DONE["rule_sha256"]))

    def setUp(self):
        super().setUp()
        if not self.on_this_rule and self._testMethodName not in ("test_its_calendar_is_the_houses",
                                                                  "test_the_pinned_plan_refuses_the_owners_checkpoints"):
            self.skipTest(self.OWED)

    def test_the_pinned_plan_refuses_the_owners_checkpoints(self):
        if self.on_this_rule:
            self.skipTest("the plan at hand is pinned to the rule in force")
        self.build()
        code, got = self.script.run(json.loads(json.dumps(self.report())), n_boot=20, horizons=(20,))
        self.assertEqual(code, 2, got.get("why"))
        self.assertIn("30, 40, 50", got.get("why") or "", "it names its own grid, and prints no figure")
        self.assertFalse(got.get("qualification"))

    def run_script(self, out: dict, ledger: dict | None = None) -> dict:
        code, got = self.script.run(json.loads(json.dumps(out)), ledger=ledger, n_boot=20, horizons=(20,))
        self.assertEqual(code, 0, got.get("why"))
        return {r["family"]: r for r in got["qualification"]}

    def test_its_calendar_is_the_houses(self):
        day = dt.date(2024, 1, 1)
        while day <= dt.date(2030, 12, 31):
            self.assertEqual(self.script.is_session(day), S.is_session(day), day)
            day += dt.timedelta(days=1)

    def test_it_reads_the_field_from_the_report_and_its_checks_hold(self):
        self.one()
        self.two(10)
        self.panel()
        self.steady()
        rows = self.run_script(self.report())
        for family in ("p-one", "p-two", "xs-p"):
            self.assertEqual((rows[family]["span_source"], rows[family]["span_check_ok"]), ("report", True), family)

    def test_one_ledger_passes_every_checkpoint_in_the_script_itself(self):
        self.forty()
        out = json.loads(json.dumps(self.report()))
        blocked = {tuple(r) for cp in out["done"]["all"]["checkpoints"] for p in cp["by_program"]
                   if p["family"] == "p-a" for e in p["span_bh"] for r in e["blocked"]}
        lv = self.script.ledger_view({"blocked": [{"program": "eq|p-a|v1", "from": a, "to": z, "why": "C1"}
                                                  for a, z in sorted(blocked)]})
        rows = out["done"]["all"]["closes"]
        eqmap = {str(e["pid"]): e for e in out["equity"]["closes"]}
        nums = self.script.numbered(rows, eqmap)
        for cp in self.script.gate(out):
            stats, _, _ = self.script.stats_at(cp, rows, nums, eqmap, None, None,
                                               lambda key: self.script.blocked_sessions(lv, key))
            for key in ("eq|p-a|v1", "eq|p-b|v1"):
                self.assertEqual((stats[key]["span_source"], stats[key]["span_check_ok"]), ("report", True),
                                 (cp["at_close"], key, stats[key].get("why")))

    def test_a_split_holds_with_the_ledgers_blocked_sessions_and_fails_closed_without(self):
        self.build()
        self.live.put(R.OPEN_NOTE_KEY, {"2026-10-14": {"open": {"clear": False, "why": "the House is paused"}}})
        out = self.report()
        one, = self.spans(self.checkpoint(out))["p-one"]
        blocked = [{"program": "eq|p-one|v1", "from": a, "to": z, "why": "House blocked (C1)"} for a, z in one["blocked"]]
        self.assertTrue(self.run_script(out, {"blocked": blocked})["p-one"]["span_check_ok"])
        bare = self.run_script(out)["p-one"]
        self.assertEqual((bare["span_check_ok"], bare["qualified"]), (False, False))


if __name__ == "__main__":
    unittest.main()
