"""RELEASE 1019b's THREE REVIEWS (the money path, the House, the judges): each fix held by a test that failed on the
release as integrated (a2c0c794). Synthetic data only: every price, filing, article and fill here is invented."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sqlite3
import stat
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from league.equity import live as L
from league.equity import schedule as ES
from league.events import bands as BA
from league.events import book as EB
from league.events import calendar as C
from league.events import house as H
from league.events import run as R
from league.events import screen as SC
from league.events import store as S
from league.events import universe as U
from league.tests import test_events_book as TB
from league.tests.test_events_book import CIK, DAY, NEXT, PRIOR, EventTest, V2, earnings, iso
from league.tests.test_events_house import LaneCase, et
from league.tests.test_events_run import FakeGateway as CalendarGateway
from league.tests.test_events_screen import final_record

REPO = Path(__file__).resolve().parents[2]


# ======================================================================================================== the money path
class TwoProgramsOneNameOneAuction(EventTest):
    """PREREG-EVL-1 sections 5 and 6: each position exits at its own scheduled auction. Two programs may hold one name
    (one position per issuer is a per-program rule); both lots due at one close are both sold in that cross."""

    def test_both_lots_of_one_name_are_sold_at_their_close_and_both_fills_go_back_to_the_lane(self):
        h = self.harness()
        # A mid-session earnings 8-K on PRIOR: C1's day 0 is PRIOR (in at PRIOR's close, out at DAY's close), and the
        # same 8-K is in READ-O1's open window of DAY (in at DAY's open, out at DAY's close).
        h.lane.filing("m-1", CIK, accepted=iso(PRIOR, 12, 0), received=iso(PRIOR, 12, 1))
        h.lane.verdict("m-1", 3, answered=iso(PRIOR, 12, 5))
        h.lane.universe(PRIOR, "ACME", CIK, 16.0)
        h.lane.universe(DAY, "ACME", CIK, 16.8)
        h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('ACME', ?, 'raw', 16, "
                             "16, 16, 16.0, 1e6, 'x')", (ES.previous_session(PRIOR).isoformat(),))
        h.lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('ACME', ?, '1530', "
                             "16.8, 'x', 'sip-1min', 'x')", (PRIOR.isoformat(),))
        self.ready(h, PRIOR)
        self.ready(h, DAY)
        h.symbol("ACME", last=16.8)
        h.venue.prints[("ACME", PRIOR.isoformat(), "close")] = D("16.90")
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("17.00")
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("17.10")
        for hh, mm in ((15, 46), (15, 47), (16, 1), (16, 3)):
            h.tick(hh, mm, day=PRIOR)
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
            h.tick(hh, mm, day=DAY)
        held = [lot for lot in h.lots() if lot.status != "closed"]
        self.assertEqual(sorted(lot.family for lot in held), ["EVL-ERN-REACT-C1", "EVL-ERN-READ-O1"])
        self.assertEqual({lot.symbol for lot in held}, {"ACME"})
        for hh, mm in ((15, 46), (15, 47), (15, 48), (16, 1), (16, 3)):
            h.tick(hh, mm, day=DAY)
        sells = [b for b in h.bodies() if b["side"] == "sell"]
        self.assertEqual([(b["symbol"], b["time_in_force"], b["type"]) for b in sells], [("ACME", "cls", "market")] * 2)
        self.assertEqual(sum(int(b["qty"]) for b in sells), sum(int(lot.opened_qty) for lot in held))
        self.assertEqual({lot.status for lot in h.lots()}, {"closed"}, "both sold in DAY's closing cross")
        self.assertEqual([r["status"] for r in h.event_intents("sell")], ["done", "done"])
        sold = {(r["program"], r["side"]) for r in h.lane.fills()}
        self.assertIn(("EVL-ERN-REACT-C1", "sell"), sold)
        self.assertIn(("EVL-ERN-READ-O1", "sell"), sold)

    def test_a_working_buy_of_the_name_still_stops_a_sale(self):
        """Only the book's own SALES at the same auction are passed over: any other working order on the symbol (here a
        buy) still stops the sale, one working order a symbol."""
        h = self.harness()
        book = h.book
        with h.state.transaction():
            h.state.execute("INSERT INTO eq_orders(eid, client_id, instance, family, side, symbol, class, at, qty, limit_px, "
                            "collar_bp, status, placed_at, day, updated_at, tif, otype) VALUES(1, 'c1', 'x', 'f', 'buy', "
                            "'ACME', 'stock', 'close', '1', '20', 0, 'working', 0, ?, 0, 'cls', 'limit')",
                            (DAY.isoformat(),))
            h.state.execute("INSERT INTO eq_orders(eid, client_id, instance, family, side, symbol, class, at, qty, limit_px, "
                            "collar_bp, status, placed_at, day, updated_at, tif, otype) VALUES(2, 'c2', 'x', 'f', 'sell', "
                            "'BETA', 'stock', 'close', '1', '0', 0, 'working', 0, ?, 0, 'cls', 'market')",
                            (DAY.isoformat(),))
        h.venue.book = []
        self.assertIn("one order a symbol", book._symbol_busy("ACME", auction_sale=(DAY.isoformat(), "cls")) or "")
        self.assertIsNone(book._symbol_busy("BETA", auction_sale=(DAY.isoformat(), "cls")))
        self.assertIn("one order a symbol", book._symbol_busy("BETA", auction_sale=(DAY.isoformat(), "opg")) or "")
        self.assertIn("one order a symbol", book._symbol_busy("BETA") or "")


class TheDayCountReservesOnceAnExit(EventTest):
    """The equity day's order count keeps room for the exits of the lots held, but an event lot's exit is one auction
    order (one, never two), and none once it is sent: counted twice, a day's open-entry lots sold at the close left the
    close's own entries no room."""

    def test_twenty_open_entry_lots_sold_at_the_close_leave_room_for_that_closes_entries(self):
        h = self.harness()
        n = 0
        for prefix, items in (("E", ("2.02",)), ("K", ("8.01",))):
            for i in range(8):
                n += 1
                sym = f"{prefix}{i:03d}"
                earnings(h.lane, f"{prefix.lower()}-{i}", f"{n + 100:010d}", sym, prev_close=1.0, items=items)
                h.symbol(sym, last=1.0)
                h.venue.prints[(sym, DAY.isoformat(), "open")] = D("1.00")
                h.venue.prints[(sym, DAY.isoformat(), "close")] = D("1.01")
        for i in range(4):
            n += 1
            cik, sym = f"{n + 100:010d}", f"I{i:03d}"
            h.lane.insider_buy(f"f-{i}", cik, accepted=iso(PRIOR, 17, 0), usd=60000)
            h.lane.st.db.execute("UPDATE filings SET received_at=? WHERE accession=?", (iso(PRIOR, 17, 1), f"f-{i}"))
            h.lane.universe(DAY, sym, cik, 1.0)
            h.symbol(sym, last=1.0)
            h.venue.prints[(sym, DAY.isoformat(), "open")] = D("1.00")
            h.venue.prints[(sym, DAY.isoformat(), "close")] = D("1.01")
        h.lane.filing("c-1", "0000009999", accepted=iso(DAY, 11, 0), received=iso(DAY, 11, 1))
        h.lane.universe(DAY, "CEEE", "0000009999", 1.0)
        h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('CEEE', ?, 'raw', 1, 1, "
                             "1, 1.0, 1e6, 'x')", (PRIOR.isoformat(),))
        h.lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('CEEE', ?, '1530', "
                             "1.05, 'x', 'sip-1min', 'x')", (DAY.isoformat(),))
        h.symbol("CEEE", last=1.05)
        h.venue.prints[("CEEE", DAY.isoformat(), "close")] = D("1.05")
        self.ready(h)
        for hh, mm in ((9, 15), (9, 16), (9, 17), (9, 31), (9, 33), (15, 46), (15, 47), (15, 48), (16, 1), (16, 3)):
            h.tick(hh, mm, day=DAY)
        opens = [b for b in h.bodies() if b["side"] == "buy" and b["time_in_force"] == "opg"]
        sells = [b for b in h.bodies() if b["side"] == "sell"]
        self.assertEqual((len(opens), len(sells)), (20, 20))
        c1 = [(r["status"], r["why"]) for r in h.event_intents("buy") if r["program"] == "EVL-ERN-REACT-C1"]
        self.assertEqual([s for s, _ in c1], ["done"], c1)
        self.assertIn(("buy", "cls"), [(b["side"], b["time_in_force"]) for b in h.bodies()])

    def test_the_reserve_is_one_an_unsent_event_exit_none_once_sent_and_two_for_an_old_lane_lot(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.ready(h)
        h.symbol("ACME", last=17.0)
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("17.00")
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("17.50")
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
            h.tick(hh, mm)
        [lot] = h.lots()
        self.assertEqual(h.book._exit_reserve(DAY.isoformat()), 1, "its market-on-close sale, one order")
        h.tick(15, 46)
        h.tick(15, 47)
        self.assertEqual([b["time_in_force"] for b in h.bodies() if b["side"] == "sell"], ["cls"])
        self.assertEqual(h.book._exit_reserve(DAY.isoformat()), 0, "its sale is sent: in the day's count already")
        old = h.instance("seed-overnight-spy")
        h.lot(old, "SPY", "0.5", "590")
        self.assertEqual(h.book._exit_reserve(DAY.isoformat()), 2, "an old lane's lot: its sale and a cancel")


class TheListIsSentAgain(EventTest):
    def test_a_gateway_that_lost_the_days_list_is_sent_it_again(self):
        """A 403 `stock_eligible` (the gateway holds no list of the day: lost or replaced) clears the book's note of the
        list it sent, so the next minute publishes it again before the buy goes again."""
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.ready(h)
        h.symbol("ACME", last=17.0)
        h.tick(9, 15)
        self.assertEqual(len(h.venue.client.lists), 1)
        h.venue.gateway_refuses = "stock_eligible"
        h.tick(9, 16)
        h.tick(9, 17)
        self.assertGreaterEqual(len(h.venue.client.lists), 2, "published again after the gateway said it holds none")
        h.venue.gateway_refuses = None
        h.tick(9, 18)
        self.assertIn(("buy", "opg"), [(b["side"], b["time_in_force"]) for b in h.bodies() if not h.venue.gateway_refuses])


# ============================================================================================================ the House
class TheCloseDecisionReadsEachNameOnce(EventTest):
    """PREREG-EVL-2's day news brings hundreds of articles to a close decision: the book reads each name's T29 minute
    once, all the day's names in batched requests, never one read an article."""

    def minute_market(self, h, *, close: float = 17.0, fail: bool = False) -> list[tuple]:
        real = h.market.bars
        calls: list[tuple] = []

        def bars(symbols, *, timeframe, start, end=None, adjustment="raw"):
            if timeframe != "1Min":
                return real(symbols, timeframe=timeframe, start=start, end=end, adjustment=adjustment)
            calls.append((tuple(symbols), start, end))
            if fail:
                raise RuntimeError("HTTP 429 too many requests")
            t = S.iso(EB.t29(C.session(h.lane.st, DAY)))
            return {s: [{"t": t, "o": close, "h": close, "l": close, "c": close, "v": 100}] for s in symbols}
        h.market.bars = bars
        return calls

    def articles(self, h, issuers: int = 10, per: int = 4) -> int:
        n = 0
        for i in range(issuers):
            symbol, cik = f"S{i:02d}X", f"00000001{i:02d}"
            h.lane.universe(DAY, symbol, cik, 16.0)
            h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES(?, ?, 'raw', 16, "
                                 "16, 16, 16.0, 1e6, 'x')", (symbol, PRIOR.isoformat()))
            h.symbol(symbol, last=17.0)
            for k in range(per):
                n += 1
                h.lane.article(f"n-{n}", symbol, knowable=iso(DAY, 10 + k, 5))
        return n

    def test_forty_articles_of_ten_names_are_one_batched_read_and_the_reaction_is_taken(self):
        h = self.harness()
        n = self.articles(h)
        calls = self.minute_market(h)
        h.lane.decided(DAY, "open")
        for hh, mm in ((9, 15), (9, 16), (15, 46)):
            h.tick(hh, mm)
        out = h.tick(15, 47)
        self.assertIn("event_decide", out, out)
        self.assertEqual(n, 40)
        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(len(calls[0][0]), 10, "every name of the day's universe, in one request")
        planned = [r for r in h.event_intents("buy") if r["program"] == "EVL-NEWS-REACT-ON"]
        self.assertTrue(planned, "17.00 / 16.00 = 1.0625 >= 1.04: NEWS-REACT-ON takes the names")

    def test_a_failed_batch_is_read_again_once_never_name_by_name(self):
        """(Release 1019b's second review: a failed request is sent again once. The third review: one that fails twice
        leaves its names unread, and the decision is made with what was read: no REACT row of those names is taken,
        and the summary and the minute's `errors` say why.)"""
        h = self.harness()
        self.articles(h)
        calls = self.minute_market(h, fail=True)
        h.lane.decided(DAY, "open")
        for hh, mm in ((9, 15), (9, 16), (15, 46)):
            h.tick(hh, mm)
        out = h.tick(15, 47)
        self.assertEqual(len(calls), 2, "one batched request and one retry of it, no read an article or a name after it")
        self.assertEqual({len(c[0]) for c in calls}, {10}, "both batched: every name of the day's universe")
        self.assertEqual([r for r in h.event_intents("buy") if r["program"] == "EVL-NEWS-REACT-ON"], [])
        [row] = h.state.rows("SELECT status, summary FROM eq_event_decisions WHERE day=? AND at='close'",
                             (DAY.isoformat(),))
        self.assertEqual(row["status"], "done")
        self.assertIn("HTTP 429", json.loads(row["summary"])["errors"][0])
        self.assertTrue(any("T29 minutes" in e for e in out.get("errors", [])), out)

    def test_the_reader_reads_a_name_and_a_base_once(self):
        root = Path(self.root)
        lane = TB.Lane(root)
        self.addCleanup(lane.st.close)
        lane.universe(DAY, "AAA", "0000000001", 10.0)
        lane.universe(DAY, "BBB", "0000000002", 10.0)
        lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('BBB', ?, '1530', "
                           "11.0, 'x', 'sip-1min', 'x')", (DAY.isoformat(),))
        ro = EB.open_lane(root)
        self.addCleanup(ro.close)
        many, one, daily = [], [], []
        ratio = EB.reaction_reader(ro, DAY, daily=lambda s, d: daily.append((s, d)) or 10.0,
                                   minutes=lambda s, ses: one.append(s) or 12.0,
                                   minutes_many=lambda names, ses: many.append(list(names)) or {"AAA": 10.5})
        row = {"id": "x", "knowable_at": iso(DAY, 10, 0)}
        for _ in range(5):
            self.assertAlmostEqual(ratio(row, {"symbol": "AAA"}), 1.05)
            self.assertAlmostEqual(ratio(row, {"symbol": "BBB"}), 1.10, msg="the lane's own mark")
        self.assertEqual(many, [["AAA"]], "the names with no mark, once")
        self.assertEqual(one, [])
        self.assertEqual(len(daily), 2, "one base a (name, day)")
        self.assertAlmostEqual(ratio(row, {"symbol": "ZZZ"}), 1.2, msg="a name outside the universe: read alone")
        self.assertEqual(one, ["ZZZ"])


class AnExitNeverWaitsOnTheLane(EventTest):
    def test_a_lane_read_error_in_the_close_decision_still_sends_the_market_on_close_sale(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.ready(h)
        h.symbol("ACME", last=17.0, sd=0.02)
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("17.00")
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("17.50")
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
            h.tick(hh, mm)
        [lot] = h.lots()
        self.assertEqual(lot.status, "open")
        with mock.patch.object(EB, "decided", side_effect=sqlite3.OperationalError("database is locked")):
            outs = [h.tick(hh, mm) for hh, mm in ((15, 46), (15, 47), (15, 48))]
        self.assertTrue(all(any("event decide close" in e for e in o.get("errors", [])) for o in outs), outs)
        self.assertEqual([(b["side"], b["time_in_force"]) for b in h.bodies() if b["side"] == "sell"], [("sell", "cls")])
        h.tick(16, 1)
        h.tick(16, 3)
        [lot] = h.lots()
        self.assertEqual(lot.status, "closed", "sold at its own close")
        self.assertNotIn("rung", json.dumps(lot.info.get("evl_exit") or {}).replace('"rung": 0', ""))

    def test_a_failing_finish_never_stops_the_decision_or_the_sends(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.ready(h)
        h.symbol("ACME", last=17.0)
        with mock.patch.object(type(h.book), "_event_finish", side_effect=RuntimeError("broken")):
            h.tick(9, 15)
            out = h.tick(9, 16)
        self.assertTrue(any("event finish" in e for e in out.get("errors", [])), out)
        self.assertIn(("buy", "opg"), [(b["side"], b["time_in_force"]) for b in h.bodies()])


class ACutLaneDecisionIsNotDecided(unittest.TestCase):
    def test_only_an_ok_or_pending_receipt_is_the_lanes_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            lane = TB.Lane(Path(tmp))
            try:
                ro = EB.open_lane(Path(tmp))
                for status, want in (("running", False), ("cut", False), ("failed", False), ("pending", True),
                                     ("ok", True)):
                    lane.st.db.execute("DELETE FROM receipts")
                    rid = lane.st.start_receipt(f"decide-open:{DAY.isoformat()}")
                    if status != "running":
                        lane.st.finish_receipt(rid, status, {})
                    self.assertIs(EB.decided(ro, DAY, "open"), want, status)
                ro.close()
            finally:
                lane.st.close()


class AFailedFetchIsFetchedAgain(LaneCase):
    """One transient SEC error on an 8-K's index page: the next record pass fetches it, before its live decision."""

    def test_a_transient_sec_error_is_retried_by_the_next_pass(self):
        acc = "0000000001-26-000401"
        self.sec.add(acc, "0000000001", "2026-10-20 08:10:00")
        real = self.sec.__call__
        state = {"failed": 0, "asked": 0}

        def flaky(url):
            if url.endswith(f"{acc}-index.htm"):
                state["asked"] += 1
                if state["failed"] == 0:
                    state["failed"] += 1
                    from league.events.gw import GatewayError
                    raise GatewayError(503, "SEC")
            return real(url)
        self.lane._sec_base = flaky
        with self.store() as st:
            for d in ("2026-10-15", "2026-10-16", "2026-10-19"):
                st.set_meta(f"evl:backfill:{d}", "done")
        self.at(et("2026-10-20", "08:12"))
        self.assertEqual(self.turn()["task"], "record")
        with self.store() as st:
            status = st.db.execute("SELECT status FROM filings WHERE accession=?", (acc,)).fetchone()[0]
        self.assertTrue(status.startswith("failed:"), status)
        for _ in range(3):
            self.clock.advance(121)
            self.turn()
        with self.store() as st:
            status = st.db.execute("SELECT status FROM filings WHERE accession=?", (acc,)).fetchone()[0]
        self.assertEqual(status, "fetched")
        self.assertEqual(state["asked"], 2, "asked again once, then fetched")
        self.at(et("2026-10-20", "09:16"))
        last = self.turn()
        while last.get("task") != "decide-open":
            last = self.turn()
        with self.store() as st:
            n = st.db.execute("SELECT COUNT(*) FROM intents WHERE event=?", (f"8k:{acc}",)).fetchone()[0]
        self.assertGreater(n, 0, "the event reached its live decision")

    def test_a_filing_that_keeps_failing_is_left_to_the_backfill(self):
        """(Release 1019b's second review: the tries are spaced from the first failure, 2, 4, 8, 16 and 32 minutes, so
        an SEC outage of half an hour still finds the filing before its live decision; FETCH_TRIES in all.)"""
        acc = "0000000001-26-000402"
        self.sec.add(acc, "0000000001", "2026-10-20 08:10:00")
        real = self.sec.__call__
        asked = []

        def broken(url):
            if url.endswith(f"{acc}-index.htm"):
                asked.append(self.clock_dt())
                from league.events.gw import GatewayError
                raise GatewayError(503, "SEC")
            return real(url)
        self.lane._sec_base = broken
        with self.store() as st:
            for d in ("2026-10-15", "2026-10-16", "2026-10-19"):
                st.set_meta(f"evl:backfill:{d}", "done")
        self.at(et("2026-10-20", "08:12"))
        self.turn()
        while self.clock_dt() < et("2026-10-20", "09:05"):
            self.clock.advance(121)
            self.turn()
        self.assertEqual(len(asked), H.FETCH_TRIES, "FETCH_TRIES tries in all, then left to the backfill")
        offsets = [(t - asked[0]).total_seconds() / 60 for t in asked[1:]]
        for got, want in zip(offsets, (2, 4, 8, 16, 32)):
            self.assertGreaterEqual(got, want)
            self.assertLess(got, want + 3, "at the first record pass it is due")

    def test_an_sec_outage_of_a_quarter_hour_still_reaches_the_live_decision(self):
        acc = "0000000001-26-000403"
        self.sec.add(acc, "0000000001", "2026-10-20 08:10:00")
        real = self.sec.__call__
        asked = []

        def flaky(url):
            if url.endswith(f"{acc}-index.htm"):
                asked.append(self.clock_dt())
                if self.clock_dt() < et("2026-10-20", "08:25"):
                    from league.events.gw import GatewayError
                    raise GatewayError(503, "SEC")
            return real(url)
        self.lane._sec_base = flaky
        with self.store() as st:
            for d in ("2026-10-15", "2026-10-16", "2026-10-19"):
                st.set_meta(f"evl:backfill:{d}", "done")
        self.at(et("2026-10-20", "08:12"))
        self.turn()
        while self.clock_dt() < et("2026-10-20", "09:10"):
            self.clock.advance(121)
            self.turn()
        with self.store() as st:
            status = st.db.execute("SELECT status FROM filings WHERE accession=?", (acc,)).fetchone()[0]
        self.assertEqual(status, "fetched")
        self.assertLess(len(asked), H.FETCH_TRIES, "fetched before the tries ran out")
        self.at(et("2026-10-20", "09:16"))
        last = self.turn()
        while last.get("task") != "decide-open":
            last = self.turn()
        with self.store() as st:
            n = st.db.execute("SELECT COUNT(*) FROM intents WHERE event=? AND why IS NULL", (f"8k:{acc}",)).fetchone()[0]
        self.assertGreater(n, 0, "decided live")


class TheRecordPassCountsBesideAFailedFeed(LaneCase):
    def test_a_failed_feed_and_a_retried_row_of_its_form_never_break_the_pass(self):
        """SEC's 8-K feed fails (its counts hold the error) in the pass that retries a failed 8-K: the pass is `ok`."""
        acc = "0000000001-26-000404"
        self.sec.add(acc, "0000000001", "2026-10-20 08:10:00")
        real = self.sec.__call__
        state = {"feed_down": False, "doc_down": True}

        def flaky(url):
            from league.events.gw import GatewayError
            if "action=getcurrent" in url and "type=8-K" in url and state["feed_down"]:
                raise GatewayError(503, "SEC getcurrent")
            if url.endswith(f"{acc}-index.htm") and state["doc_down"]:
                raise GatewayError(503, "SEC")
            return real(url)
        self.lane._sec_base = flaky
        with self.store() as st:
            for d in ("2026-10-15", "2026-10-16", "2026-10-19"):
                st.set_meta(f"evl:backfill:{d}", "done")
        self.at(et("2026-10-20", "08:12"))
        first = self.turn()
        self.assertEqual((first["task"], first["status"]), ("record", "ok"), first)
        state["feed_down"] = True
        self.clock.advance(121)
        second = self.turn()
        self.assertEqual((second["task"], second["status"]), ("record", "ok"), second)
        receipt = self.receipts("record")[-1]
        body = json.loads(receipt["summary"])
        self.assertIn("error", body["8-K"])
        self.assertEqual((body["8-K"]["retried"], body["8-K"]["failed"]), (1, 1))
        state.update(feed_down=False, doc_down=False)
        self.clock.advance(121)
        self.turn()
        self.clock.advance(121)
        self.turn()
        with self.store() as st:
            status = st.db.execute("SELECT status FROM filings WHERE accession=?", (acc,)).fetchone()[0]
        self.assertEqual(status, "fetched", "the next passes go on: no backoff of the whole record task")


class ACutThenFailingDecisionWaitsAsAFailedOne(LaneCase):
    """A decision this lane cut once (`_cut`) whose next runs raise: the receipt's status is read first, so it waits as
    a failed one (DECIDE_RETRY while live, STALE_RETRY after), and `_decide` forgets the cut when a run raises."""

    def run_turns(self, cut: bool) -> list:
        from league.events import run as R

        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-19 17:00:00")
        if cut:
            self.lane._cut.add(("open", dt.date(2026, 10, 20)))
        real = R.decide_open

        def decide_open(ctx, day, *, backfill_run=False, ask_only=False):
            if not ask_only:
                ctx.store.start_receipt(f"decide-open:{day}", now=ctx.now())
                raise RuntimeError("a bug in this session's data")
            return real(ctx, day, backfill_run=backfill_run, ask_only=ask_only)
        tasks = []
        with mock.patch.object(R, "decide_open", decide_open):
            self.at(et("2026-10-20", "09:40"))
            for _ in range(20):
                tasks.append(self.turn().get("task"))
                self.clock.advance(60)
        return tasks

    def test_cut_once_then_failing_runs_as_often_as_failing_alone(self):
        with_cut = self.run_turns(True)
        self.assertEqual(self.lane._cut, set(), "the cut is forgotten once a run raises")
        self.assertLessEqual(with_cut.count("decide-open"), 3, with_cut)
        self.assertIn("record", with_cut)



class AFailedLiveDecisionIsTriedAgainLive(LaneCase):
    def test_one_transient_failure_is_retried_a_minute_later_and_stays_live(self):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-19 17:00:00")
        self.mark_recorded(et("2026-10-20", "09:15"))
        from league.events.gw import GatewayError
        real_get = self.gw.get_json
        state = {"n": 0}

        def flaky(path, params=None):
            if path.endswith("/v2/stocks/bars") and state["n"] == 0:
                state["n"] += 1
                raise GatewayError(429, "too many requests")
            return real_get(path, params)
        self.gw.get_json = flaky
        self.at(et("2026-10-20", "09:16"))
        last = self.turn()
        self.assertEqual((last["task"], last["status"]), ("decide-open", "failed"))
        self.assertEqual(self.receipts("decide-open:2026-10-20")[-1]["status"], "failed")
        self.at(et("2026-10-20", "09:17"))
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "decide-open")
        self.assertEqual(self.receipts("decide-open:2026-10-20")[-1]["status"], "ok")
        with self.store() as st:
            row = st.db.execute("SELECT why FROM intents WHERE program='EVL-ERN-READ-O1' AND version=2").fetchone()
        self.assertIsNotNone(row)
        self.assertIsNone(row["why"], "decided live, not as a backfill")


class TheMigrationRefusesWhenSystemdCannotAnswer(unittest.TestCase):
    def test_a_failing_systemctl_reads_as_running(self):
        spec = importlib.util.spec_from_file_location("evl_migrate_1019b", REPO / "scripts" / "evl_migrate.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "systemctl"
            fake.write_text("#!/bin/sh\necho 'Failed to connect to bus: No medium found' >&2\nexit 1\n")
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            with mock.patch.dict("os.environ", {"PATH": f"{d}:/usr/bin:/bin"}):
                running = mod.desktop_timers_running()
        self.assertEqual(len(running), 1)
        self.assertIn("failed with status 1", running[0])


# ============================================================================================================ the judges
class LooksOnAFinalRecord(unittest.TestCase):
    """PREREG-EVL-3 section 3 (looks in order, at most one at a session close, no other look) and PREREG-EVL-1
    section 7 (late data delays the computation, never its as-of date): a look is computed once its close is final for
    the program, and a look on record is never derived again from a record that grew since."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        C.refresh(self.st, CalendarGateway({}), dt.date(2026, 10, 1), dt.date(2027, 3, 31))
        self.days = [s.day for s in C.sessions(self.st, dt.date(2026, 10, 20), dt.date(2027, 3, 31))]
        self.n = 0

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def settle(self, program, version, per_day, days, a_of):
        for d in days:
            for _ in range(per_day):
                ev = f"syn:{program}:{version}:{self.n}"
                a = a_of(self.n)
                self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, "
                                   "entry_at, exit_day, exit_at, rank_key, mode, status, why) VALUES(?, ?, ?, 'S', ?, 'z', "
                                   "?, 'open', ?, 'close', NULL, 'shadow', 'exited', NULL)",
                                   (program, version, ev, f"{self.n:010d}", d.isoformat(), d.isoformat()))
                self.st.db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, bench, bench_entry, "
                                   "bench_exit, cost_entry_bp, cost_exit_bp, r, b, a, tradable, settled_at, status) "
                                   "VALUES(?, ?, ?, 10, 10, 'SPY', 1, 1, 5, 5, ?, 0, ?, 1, 'z', 'settled')",
                                   (program, version, ev, a, a))
                self.n += 1

    def receipt(self, kind, day, status, summary=None):
        rid = self.st.start_receipt(f"decide-{kind}:{day.isoformat()}")
        self.st.finish_receipt(rid, status, summary or {})

    def test_the_finality_rules_name_the_house_constants(self):
        self.assertEqual(SC.FINAL_SESSIONS, H.REDECIDE_SESSIONS)
        self.assertEqual(SC.FINAL_LOOKBACK, H.LOOKBACK)
        self.assertEqual(SC.FINAL_BACKFILL_WEEKDAYS, H.BACKFILL_WEEKDAYS)

    def test_late_events_never_make_a_second_look_at_a_close_already_looked_at(self):
        p = "EVL-INS-BUY-O1"
        self.settle(p, 2, 7, self.days[:8], lambda i: 0.001 * (1 if i % 3 else -1))    # 56 by session 8 (8 blocks)
        self.settle(p, 2, 40, self.days[8:9], lambda i: 0.001 * (1 if i % 3 else -1))   # 96 at session 9
        now = final_record(self.st, self.days[11])
        first = SC.run(self.st, self.days[11], draws=999, now=now)
        self.assertEqual([(w["k"], w["merged"]) for w in first["written"]], [(1, [2])])  # look 1 = looks 1 and 2
        self.assertEqual(SC.look_detail(self.st, p, 2, 1)["merged"], [2], "the merged looks are on record")
        self.settle(p, 2, 5, self.days[7:8], lambda i: 0.001)                            # late events of session 8
        second = SC.run(self.st, self.days[12], draws=999, now=final_record(self.st, self.days[12]))
        self.assertEqual(second["written"], [])
        ats = [r["at"] for r in SC.look_rows(self.st, p, 2)]
        self.assertEqual(len(ats), 1, ats)
        self.assertEqual(SC.next_look_v2(self.st, p, 2, self.days[12])["k"], 3, "look 3 next: 2 was merged into 1")
        self.settle(p, 2, 40, self.days[12:13], lambda i: 0.001 * (1 if i % 3 else -1))  # 141 >= 135 at session 13
        third = SC.run(self.st, self.days[15], draws=999, now=final_record(self.st, self.days[15]))
        self.assertEqual([(w["k"], w["merged"]) for w in third["written"]], [(3, [])])
        looked = {r["k"]: r["at"] for r in SC.look_rows(self.st, p, 2)}
        self.assertGreater(looked[3], looked[1])

    def test_a_look_waits_while_a_covered_session_waits_on_its_programs_verdicts(self):
        p, ctl = "EVL-ERN-READ-O1", "EVL-CTRL-ERN-ALL-O1"
        self.settle(p, 2, 10, self.days[:3] + self.days[4:9], lambda i: 0.002)   # 80 settled, 8 blocks; day 4 missing
        self.settle(ctl, 1, 12, self.days[:9], lambda i: 0.0)
        now = final_record(self.st, self.days[12])
        self.receipt("open", self.days[3], "pending", {"pending": {f"{p}@v2": 3}})   # waiting on 3 verdicts
        out = SC.run(self.st, self.days[12], draws=999, now=now)
        self.assertEqual([w for w in out["written"] if w["program"] == p], [])
        why = [w["why"] for w in out["waiting"] if w["program"] == p]
        self.assertTrue(why and f"the open decision of {self.days[3].isoformat()} is pending" in why[0], why)
        self.assertEqual(BA.bands(self.st)[(p, 2)], "learning")
        # pending only on ANOTHER program's verdicts: this program's session is decided
        self.receipt("open", self.days[3], "pending", {"pending": {"EVL-8K-READ-O1@v2": 2}})
        out = SC.run(self.st, self.days[12], draws=999, now=now)
        self.assertEqual([(w["program"], w["k"]) for w in out["written"]], [(p, 1)])

    def test_a_look_waits_for_the_redecision_window_a_missed_decision_and_the_backfill(self):
        p = "EVL-INS-BUY-O1"
        self.settle(p, 2, 10, self.days[:8], lambda i: 0.01)                    # look 1 due at days[7]
        now = final_record(self.st, self.days[9])
        out = SC.run(self.st, self.days[9], draws=999, now=now)
        self.assertEqual(out["written"], [])
        self.assertIn("re-decision window", out["waiting"][0]["why"])
        now = final_record(self.st, self.days[10])
        self.st.db.execute("DELETE FROM receipts WHERE job=?", (f"decide-open:{self.days[2].isoformat()}",))
        out = SC.run(self.st, self.days[10], draws=999, now=now)
        self.assertEqual(out["written"], [])
        self.assertIn(f"the open decision of {self.days[2].isoformat()} is not made", out["waiting"][0]["why"])
        self.receipt("open", self.days[2], "ok")
        self.st.db.execute("DELETE FROM meta WHERE key=?", (f"evl:backfill:{self.days[7].isoformat()}",))
        out = SC.run(self.st, self.days[10], draws=999, now=now)
        self.assertEqual(out["written"], [])
        self.assertIn(f"backfill of {self.days[7].isoformat()}", out["waiting"][0]["why"])
        self.st.set_meta(f"evl:backfill:{self.days[7].isoformat()}", "done")
        out = SC.run(self.st, self.days[10], draws=999, now=now)
        self.assertEqual([(w["program"], w["k"], w["band"]) for w in out["written"]], [(p, 1, "probe")])
        self.assertEqual(SC.look_rows(self.st, p, 2)[0]["at"][:10], self.days[7].isoformat())

    def test_a_version_one_look_waits_for_a_final_close_too(self):
        p = "EVL-ERN-REACT-C1"
        for j in range(20):
            for _ in range(6):
                ev = f"v1:{self.n}"
                self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, "
                                   "entry_at, exit_day, exit_at, mode, status) VALUES(?, 1, ?, 'S', ?, 'z', ?, 'close', ?, "
                                   "'close', 'shadow', 'exited')", (p, ev, f"{self.n % 300:010d}",
                                                                    self.days[j].isoformat(), self.days[j + 1].isoformat()))
                self.st.db.execute("INSERT INTO outcomes(program, version, event, r, b, a, tradable, settled_at, status) "
                                   "VALUES(?, 1, ?, 0.0045, 0.0005, 0.004, 1, 'z', 'settled')", (p, ev))
                self.n += 1
        now = final_record(self.st, self.days[25])
        self.receipt("close", self.days[4], "running")
        out = SC.run(self.st, self.days[25], draws=999, now=now)
        self.assertEqual([w for w in out["written"] if w["program"] == p], [])
        self.assertIn(f"the close decision of {self.days[4].isoformat()} is running",
                      [w["why"] for w in out["waiting"] if w["program"] == p][0])
        self.receipt("close", self.days[4], "ok")
        out = SC.run(self.st, self.days[25], draws=999, now=now)
        self.assertEqual([w["k"] for w in out["written"] if w["program"] == p], [1, 2, 3])

    def test_a_band_move_is_written_with_its_look_or_not_at_all(self):
        p = "EVL-ERN-REACT-ON"
        self.settle(p, 2, 10, self.days[:8], lambda i: -0.01)     # every block -1%: look 1 retires it
        now = final_record(self.st, self.days[10])
        with mock.patch.object(BA, "set_band", side_effect=sqlite3.OperationalError("database is locked")):
            out = SC.run(self.st, self.days[10], draws=999, now=now)
        self.assertEqual([(e["program"], e["version"]) for e in out["errors"]], [(p, 2)])
        self.assertEqual(SC.look_rows(self.st, p, 2), [], "no look without its band move")
        self.assertIsNone(SC.look_detail(self.st, p, 2, 1))
        self.assertEqual(BA.bands(self.st)[(p, 2)], "learning")
        again = SC.run(self.st, self.days[10], draws=999, now=now)
        self.assertEqual([(w["program"], w["k"], w["band"]) for w in again["written"]], [(p, 1, "retired")])
        self.assertTrue(SC.look_detail(self.st, p, 2, 1)["retirement"]["retire"])
        self.assertEqual(BA.bands(self.st)[(p, 2)], "retired")

    def test_one_programs_failure_is_its_own(self):
        self.settle("EVL-INS-BUY-O1", 2, 10, self.days[:8], lambda i: 0.01)
        self.settle("EVL-ERN-REACT-ON", 2, 10, self.days[:8], lambda i: -0.01)
        now = final_record(self.st, self.days[10])
        real = SC._run_v2

        def broken(store, program, version, today, **kw):
            if program == "EVL-ERN-REACT-ON":
                raise RuntimeError("broken")
            return real(store, program, version, today, **kw)
        with mock.patch.object(SC, "_run_v2", side_effect=broken):
            out = SC.run(self.st, self.days[10], draws=999, now=now)
        self.assertEqual([w["program"] for w in out["written"]], ["EVL-INS-BUY-O1"])
        self.assertEqual([e["program"] for e in out["errors"]], ["EVL-ERN-REACT-ON"])


class TheHousesScreenAlwaysReviews(LaneCase):
    def test_the_band_review_runs_when_a_look_fails(self):
        with self.store() as st:
            ctx = H.LaneContext(self.lane, st, H.LaneGateway(self.gw, self.lane, None, cut=False), self.sec,
                                self.lane.now)
            self.at(et("2026-10-20", "20:50"))
            with mock.patch.object(SC, "run", return_value={"written": [], "waiting": [], "errors": [
                    {"program": "EVL-INS-BUY-O1", "version": 2, "error": "RuntimeError: broken"}]}), \
                    mock.patch.object(BA, "review", return_value=[]) as review:
                out = self.lane._screen(ctx, None)
            self.assertEqual(review.call_count, 1)
            self.assertEqual(out["_status"], "partial")
            row = st.db.execute("SELECT status FROM receipts WHERE job='screen' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(row["status"], "partial")
            with mock.patch.object(SC, "run", side_effect=RuntimeError("store")), \
                    mock.patch.object(BA, "review", return_value=[]) as review:
                out = self.lane._screen(ctx, None)
            self.assertEqual(review.call_count, 1)
            self.assertEqual(out["_status"], "partial")


class TheWallHoldsTheLanesRuleInputs(unittest.TestCase):
    def test_the_rule_inputs_are_behind_the_wall_and_the_scheduler_is_not(self):
        from league import ci

        for path in ("league/events/universe.py", "league/events/calendar.py", "league/events/edgar.py",
                     "league/events/news.py", "league/events/run.py", "league/events/store.py"):
            self.assertTrue(ci.guard([path], None), path)
        # Release 1019c: the scheduler holds the lane's verdicts to the budget's allowance, so it joined the wall (D4).
        for path in ("league/events/gw.py", "league/events/report.py"):
            self.assertEqual(ci.guard([path], None), [], path)



# ======================================================================================== the second review: the money
def c1_event(h, i: int, *, base: str = "C", react: float = 1.05, day=DAY, cik_base: int = 500, adv20: float = 5e6) -> str:
    """A mid-session earnings 8-K on `day` (EVL-ERN-REACT-C1's and EVL-ERN-REACT-ON's day 0 = `day`), its T29 mark
    `react` x the previous raw SIP close (1.00). Invented."""
    cik, sym = f"{i + cik_base:010d}", f"{base}{i:03d}"
    h.lane.filing(f"{base.lower()}-{i}", cik, accepted=iso(day, 11, 0), received=iso(day, 11, 1))
    h.lane.universe(day, sym, cik, 1.0, adv20=adv20)
    prev = ES.previous_session(day)
    h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES(?, ?, 'raw', 1, 1, 1, 1.0, "
                         "1e6, 'x')", (sym, prev.isoformat()))
    h.lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, '1530', ?, 'x', "
                         "'sip-1min', 'x')", (sym, day.isoformat(), react))
    h.symbol(sym, last=react)
    h.venue.prints[(sym, day.isoformat(), "close")] = D(str(react))
    return sym


def by_program(rows) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["program"], []).append(r["symbol"])
    return out


class RoomIsGivenInRoomsOrder(EventTest):
    """PREREG-EVL-3 section 2: every TRADABLE version 2 event that fits the walls is entered, up to each program's open
    positions; ROOM goes Sized, Probe, learning, then the tables' order, within a program its own ranking; one name at
    one auction goes to the earlier program (PREREG-EVL-1 section 8). Each program takes its own ranked picks whose name
    no earlier program was GIVEN, until its room is full (`book.allocate`)."""

    def test_react_on_takes_the_c1_events_c1_had_no_room_for(self):
        h = self.harness()
        syms = [c1_event(h, i, react=1.05 + i * 0.001) for i in range(12)]
        self.ready(h)
        for hh, mm in ((15, 46), (15, 47), (15, 48)):
            h.tick(hh, mm)
        got = by_program(h.event_intents("buy"))
        self.assertEqual(sorted(got["EVL-ERN-REACT-C1"]), sorted(syms[4:]), "C1's top 8 by reaction")
        self.assertEqual(sorted(got["EVL-ERN-REACT-ON"]), sorted(syms[:4]), "the 4 C1 had no room for go to REACT-ON")
        summary = json.loads(h.state.rows("SELECT summary FROM eq_event_decisions WHERE at='close'")[0]["summary"])
        self.assertEqual(summary["programs"]["EVL-ERN-REACT-ON"]["skipped"], {"name_given": 8})
        sent = [b for b in h.bodies() if b["side"] == "buy" and b["time_in_force"] == "cls"]
        self.assertEqual(len(sent), 12, "all twelve fit every wall: all twelve go")

    def test_guide_takes_the_read_events_read_had_no_room_for(self):
        h = self.harness()
        for i in range(12):
            sym, cik = f"G{i:03d}", f"{i + 700:010d}"
            h.lane.filing(f"g-{i}", cik, accepted=iso(PRIOR, 16, 30), received=iso(PRIOR, 16, 31))
            h.lane.verdict(f"g-{i}", 3, answered=iso(PRIOR, 16, 35), guidance="raised")
            h.lane.universe(DAY, sym, cik, 1.0, adv20=5e6 + i)
            h.symbol(sym, last=1.0)
        self.ready(h)
        for hh, mm in ((9, 15), (9, 16), (9, 17)):
            h.tick(hh, mm)
        got = by_program(h.event_intents("buy"))
        self.assertEqual((len(got["EVL-ERN-READ-O1"]), len(got["EVL-ERN-GUIDE-O1"])), (8, 4))
        self.assertFalse(set(got["EVL-ERN-READ-O1"]) & set(got["EVL-ERN-GUIDE-O1"]), "one name at one auction")
        self.assertEqual(sorted(got["EVL-ERN-READ-O1"]), [f"G{i:03d}" for i in range(4, 12)], "by score, then ADV")

    def test_a_probe_program_is_given_its_names_before_an_earlier_row_at_learning(self):
        h = self.harness()
        h.lane.band("EVL-ERN-REACT-ON", "probe")
        syms = [c1_event(h, i, react=1.05 + i * 0.001) for i in range(10)]
        self.ready(h)
        for hh, mm in ((15, 46), (15, 47)):
            h.tick(hh, mm)
        got = by_program(h.event_intents("buy"))
        self.assertEqual(sorted(got["EVL-ERN-REACT-ON"]), sorted(syms[4:]), "Probe first: its 6 best")
        self.assertEqual(sorted(got["EVL-ERN-REACT-C1"]), sorted(syms[:4]), "C1 at learning: the other 4")


class APickNoShareFitsTakesNoSlot(EventTest):
    """PREREG-EVL-3 section 2: an event no whole share fits by price is skipped (the shadow keeps it); its program's
    limit is on open POSITIONS, so such a pick never takes a slot of the room (`EquityBook._event_gate`)."""

    def test_eight_dear_names_ranked_first_leave_the_room_to_the_two_that_fit(self):
        h = self.harness()
        for i in range(10):
            sym, cik = f"R{i:03d}", f"{i + 800:010d}"
            dear = i < 8
            h.lane.filing(f"r-{i}", cik, accepted=iso(PRIOR, 16, 30), received=iso(PRIOR, 16, 31))
            h.lane.verdict(f"r-{i}", 3, answered=iso(PRIOR, 16, 35))
            h.lane.universe(DAY, sym, cik, 200.0 if dear else 10.0, adv20=(9e8 - i * 1e6) if dear else 2e6 + i)
            h.symbol(sym, last=200.0 if dear else 10.0)
            h.venue.prints[(sym, DAY.isoformat(), "open")] = D("200.00" if dear else "10.00")
        self.ready(h)
        for hh, mm in ((9, 15), (9, 16), (9, 17), (9, 31), (9, 33)):
            h.tick(hh, mm)
        sent = sorted((b["symbol"], b["qty"]) for b in h.bodies() if b["side"] == "buy")
        self.assertEqual(sent, [("R008", "3"), ("R009", "3")], "the two that fit: 3 shares at $12.50, 2% of $2,000")
        self.assertEqual(sorted(r["status"] for r in h.event_intents("buy")), ["done", "done"])
        summary = json.loads(h.state.rows("SELECT summary FROM eq_event_decisions WHERE at='open'")[0]["summary"])
        self.assertEqual(summary["programs"]["EVL-ERN-READ-O1"]["skipped"], {"name_wall": 8},
                         "limit $250 is above 10% of E: not TRADABLE, so no slot")
        self.assertEqual(summary["programs"]["EVL-ERN-READ-O1"]["planned"], 2)

    def test_the_gate_agrees_with_the_sizing_at_every_price_and_band(self):
        """`_event_gate` (at the decision) and `_size_event` (at the send) read the same figures: for a name held nowhere,
        across prices around 2%, 5% and 10% of E at learning, Probe and Sized, the gate skips exactly the picks the
        sizing would refuse for want of a whole share."""
        from league.equity import live as L

        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.ready(h)
        h.symbol("ACME", last=17.0)
        h.tick(9, 15)
        s = EB.settings()
        gate, why = h.book._event_gate(DAY.isoformat(), "open", s, EB)
        self.assertEqual(why, "")
        inst = h.book._instance(L.instance_key("EVL-ERN-READ-O1", 2))
        for band in ("learning", "probe", "sized"):
            inst.band = band
            for prev in ("2.00", "31.99", "32.00", "32.01", "79.99", "80.00", "80.01", "159.99", "160.00", "160.01",
                         "250.00"):
                pick = EB.Pick("EVL-ERN-READ-O1", 2, "8k:x", "ZZZZ", "0000009999", 3.0, 1e6, D(prev), "t")
                limit = EB.limit_price(D(prev), s.limit_ratio)
                intent = L.Intent(10_000, inst.id, inst.family, 2, DAY.isoformat(), DAY.isoformat(), "open", "buy",
                                  "planned", symbol="ZZZZ")
                sized = h.book._size_event(intent, inst, {"weight": "0.10"}, limit, DAY.isoformat(), s)
                self.assertIsNotNone(sized)
                with self.subTest(band=band, limit=str(limit)):
                    self.assertEqual(gate(band, pick) is not None, sized[0] < 1, (gate(band, pick), sized))


class AnExitNeverWaitsOnAnEntry(EventTest):
    """No buy of a name goes in the cross where an event lot of it is sold: a sale planned at the auction skips the
    name's picks at the decision (they take no slot), and a buy intent already planned waits while the sale is
    unfinished, so a sale the gateway refused for a reading (424, 409: sent again next minute) is never held by a buy."""

    def overnight(self, h):
        """NEWS-REACT-ON holds ACME from PRIOR's close (out at DAY's open); READ-O1 wants ACME at DAY's open."""
        prev2 = ES.previous_session(PRIOR)
        h.lane.universe(PRIOR, "ACME", CIK, 16.0)
        h.lane.article("n-1", "ACME", knowable=iso(PRIOR, 11, 0))
        h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('ACME', ?, 'raw', 16, "
                             "16, 16, 16.0, 1e6, 'x')", (prev2.isoformat(),))
        h.lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('ACME', ?, '1530', "
                             "16.8, 'x', 'sip-1min', 'x')", (PRIOR.isoformat(),))
        earnings(h.lane, "a-1", CIK, "ACME", prev_close=16.8)
        self.ready(h, PRIOR)
        self.ready(h, DAY)
        h.symbol("ACME", last=16.8)
        h.venue.prints[("ACME", PRIOR.isoformat(), "close")] = D("16.90")
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("17.00")
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("17.10")
        for hh, mm in ((15, 46), (15, 47), (16, 1), (16, 3)):
            h.tick(hh, mm, day=PRIOR)
        [lot] = h.lots()
        self.assertEqual((lot.family, lot.info["evl_exit"]["day"], lot.info["evl_exit"]["at"]),
                         ("EVL-NEWS-REACT-ON", DAY.isoformat(), "open"))

    def test_a_sale_refused_once_for_a_reading_goes_again_and_the_names_buy_is_never_planned(self):
        from league.live.venue import Submitted

        h = self.harness()
        self.overnight(h)
        real_submit = h.venue.submit
        refused = []

        def submit(body, *, exit):
            if body["side"] == "sell" and not refused:
                refused.append(body)
                h.venue.sent.append(dict(body))
                return Submitted(False, {"error": "positions unread", "cap": "positions"}, "HTTP 424", status=424)
            return real_submit(body, exit=exit)
        h.venue.submit = submit
        for hh, mm in ((9, 15), (9, 16), (9, 17), (9, 18), (9, 26), (9, 31), (9, 33)):
            h.tick(hh, mm, day=DAY)
        self.assertEqual([r["status"] for r in h.event_intents("sell")], ["done"], "sold at its own open")
        self.assertEqual([r for r in h.event_intents("buy") if r["day"] == DAY.isoformat()], [])
        summary = json.loads(h.state.rows("SELECT summary FROM eq_event_decisions WHERE day=? AND at='open'",
                                          (DAY.isoformat(),))[0]["summary"])
        self.assertEqual(summary["programs"]["EVL-ERN-READ-O1"]["skipped"], {"sale": 1})
        self.assertEqual(len([b for b in h.bodies() if b["side"] == "sell"]), 2, "refused once, then sent again")

    def test_a_buy_planned_before_a_sale_of_its_name_waits_while_the_sale_is_unfinished(self):
        """The decision plans the exits first, so this is the send's own guard: a sale of the name at the auction
        planned AFTER the buy (here by hand) holds the buy, never the other way round."""
        h = self.harness()
        self.overnight(h)
        [lot] = h.lots()
        plan = dict(lot.info["evl_exit"])
        lot.info["evl_exit"] = {**plan, "day": NEXT.isoformat()}          # out of this decision's way
        h.book._save_lot(lot)
        h.tick(9, 15, day=DAY)
        [buy] = [r for r in h.event_intents("buy") if r["day"] == DAY.isoformat()]
        self.assertEqual((buy["program"], buy["symbol"]), ("EVL-ERN-READ-O1", "ACME"))
        [lot] = h.lots()
        lot.info["evl_exit"] = plan                                       # its sale at this open, planned now
        h.book._save_lot(lot)
        self.assertEqual(h.book._event_exits(ES.event_moments(DAY), "open", EB), 1)
        for mm in (16, 17, 26):
            h.tick(9, mm, day=DAY)
        self.assertEqual([(b["side"], b["symbol"]) for b in h.bodies() if b["side"] == "sell"], [("sell", "ACME")],
                         "the sale goes")
        self.assertEqual([b for b in h.bodies() if b["side"] == "buy" and b["time_in_force"] == "opg"], [],
                         "no buy of the name in the cross that sells it")
        why = [r["why"] for r in h.event_intents("buy") if r["iid"] == buy["iid"]][0]
        self.assertIn("a sale of ACME is planned or working at this open auction", why)
        h.tick(9, 31, day=DAY)
        h.tick(9, 33, day=DAY)
        self.assertEqual([r["status"] for r in h.event_intents("sell")], ["done"], "sold at its own open")
        self.assertEqual([r["status"] for r in h.event_intents("buy") if r["iid"] == buy["iid"]], ["missed"])


class TheCloseDecisionIsMadeAgainAfterAFailedRead(EventTest):
    """The close decision's batched T29 read: a failed request is sent again once (the second review); when the retry
    fails too, the names stay unread and the decision is made with what was read: only the REACT rows of the unread
    names are dropped (the third review)."""

    def news_day(self, h, *, fails: int) -> dict:
        for i in range(5):
            symbol, cik = f"S{i:02d}X", f"00000001{i:02d}"
            h.lane.universe(DAY, symbol, cik, 16.0)
            h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES(?, ?, 'raw', 16, "
                                 "16, 16, 16.0, 1e6, 'x')", (symbol, PRIOR.isoformat()))
            h.symbol(symbol, last=17.0)
            h.lane.article(f"n-{i}", symbol, knowable=iso(DAY, 10, 5))
        real = h.market.bars
        state = {"n": 0}
        session = C.session(h.lane.st, DAY)

        def bars(symbols, *, timeframe, start, end=None, adjustment="raw"):
            if timeframe != "1Min":
                return real(symbols, timeframe=timeframe, start=start, end=end, adjustment=adjustment)
            state["n"] += 1
            if state["n"] <= fails:
                raise RuntimeError("market data bars 1Min: HTTP 429 too many requests")
            t = S.iso(EB.t29(session))
            return {s: [{"t": t, "o": 17.0, "h": 17.0, "l": 17.0, "c": 17.0, "v": 100}] for s in symbols}
        h.market.bars = bars
        h.lane.decided(DAY, "open")
        return state

    def test_one_failed_request_is_read_again_in_the_same_minute(self):
        h = self.harness()
        state = self.news_day(h, fails=1)
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)
        self.assertEqual(state["n"], 2)
        took = [r["symbol"] for r in h.event_intents("buy") if r["program"] == "EVL-NEWS-REACT-ON"]
        self.assertEqual(len(took), 5, "17.00 / 16.00 = 1.0625 >= 1.04: all five taken at 15:47")

    def test_a_read_that_fails_twice_drops_only_the_react_rows_and_the_decision_is_made(self):
        """(Release 1019b's third review: A T29 BATCH FAILURE DROPS ONLY THE REACT ROWS' PICKS. The request and its one
        retry fail: the decision is made at once with what was read, NEWS-REACT-ON takes nothing it could not read,
        and the decision is not made again.)"""
        h = self.harness()
        state = self.news_day(h, fails=2)
        for hh, mm in ((9, 15), (9, 16), (15, 46)):
            h.tick(hh, mm)
        out = h.tick(15, 47)
        self.assertEqual(state["n"], 2, "the request and its one retry")
        self.assertEqual([r for r in h.event_intents("buy") if r["program"] == "EVL-NEWS-REACT-ON"], [])
        [row] = h.state.rows("SELECT status, summary FROM eq_event_decisions WHERE day=? AND at='close'",
                             (DAY.isoformat(),))
        self.assertEqual(row["status"], "done")
        summary = json.loads(row["summary"])
        self.assertIn("HTTP 429", summary["errors"][0])
        self.assertIn("REACT row", summary["t29"])
        self.assertTrue(any("event decide close" in e and "T29" in e for e in out.get("errors", [])), out)
        h.tick(15, 48)
        self.assertEqual(state["n"], 2, "made once: nothing is read again")
        self.assertEqual([r for r in h.event_intents("buy") if r["program"] == "EVL-NEWS-REACT-ON"], [])



# ======================================================================================= the second review: the judges
class UntradableOnTheHouse(LaneCase):
    """PREREG-EVL-1 section 2: a LIVE decision reads Alpaca's `status=active` and `tradable: true`; a BACKFILLED one
    `status=all`. Eligibility is decided once per (entry session, CIK), by the rule that made it, and kept whether
    eligible or not: the House's hourly re-decision (a backfill) never judges again a CIK the live decision judged, and a
    row only the backfill rule made never serves a live decision, `book.picks` or `book.eligible`. AAA is listed on
    NASDAQ, active, but Alpaca says `tradable: false`."""

    def setUp(self):
        super().setUp()
        real = self.gw.get_json

        def get_json(path, params=None):
            rows = real(path, params)
            if path.endswith("/v2/assets"):
                rows = [dict(r, tradable=False) if r["symbol"] == "AAA" else r for r in rows]
            return rows
        self.gw.get_json = get_json
        self.lane = self.new_lane(redecide=True)

    def intents(self, day):
        with self.store() as st:
            return sorted((r["program"], r["version"], r["symbol"], r["entry_at"], r["why"]) for r in st.db.execute(
                "SELECT * FROM intents WHERE entry_day=? AND status='planned'", (day,)))

    def results(self, day, cik):
        with self.store() as st:
            return {r["rule"]: r["eligible"] for r in st.db.execute(
                "SELECT rule, eligible FROM eligibility WHERE day=? AND cik=?", (day, cik))}

    def turns(self, n=6):
        for _ in range(n):
            last = self.turn()
            if not last or last.get("task") not in ("decide-open", "decide-close", "verdicts", "record"):
                break

    def test_the_hourly_redecision_never_admits_the_name_the_live_decision_refused(self):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-20 07:05:00")   # AAA, open window of Tue
        self.fetched_8k("0000000002-26-000102", "0000000002", "2026-10-20 07:06:00")   # BBB (tradable), same window
        self.at(et("2026-10-20", "09:16"))
        self.mark_recorded()
        last = self.turn()
        self.assertEqual((last["task"], last["status"]), ("decide-open", "ok"))
        self.assertFalse([x for x in self.intents("2026-10-20") if x[2] == "AAA"])
        self.assertEqual(self.results("2026-10-20", "0000000001"), {"live": 0}, "the live rule's result, kept")
        self.at(et("2026-10-20", "10:20"))                                             # the hourly re-decision
        self.mark_recorded()
        self.turns()
        with self.store() as st:
            redecided = st.db.execute("SELECT COUNT(*) FROM receipts WHERE job='decide-open:2026-10-20'").fetchone()[0]
            self.assertEqual(EB.eligible(st, dt.date(2026, 10, 20)), ["BBB"])
        self.assertGreaterEqual(redecided, 2, "the open was decided again")
        self.assertEqual([x for x in self.intents("2026-10-20") if x[2] == "AAA"], [])
        self.assertEqual(self.results("2026-10-20", "0000000001"), {"live": 0}, "never judged again")

    def test_the_live_close_decision_never_takes_the_name(self):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-20 07:05:00")   # AAA, open window of Tue
        self.fetched_8k("0000000001-26-000103", "0000000001", "2026-10-20 12:00:00")   # AAA earnings, C1's day 0 = Tue
        self.at(et("2026-10-20", "09:16"))
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "decide-open")
        self.at(et("2026-10-20", "10:20"))
        self.mark_recorded()
        self.turns()
        self.at(et("2026-10-20", "15:47"))                                             # Tuesday's LIVE close decision
        self.mark_recorded()
        for _ in range(4):
            last = self.turn()
            if last.get("task") == "decide-close":
                break
        self.assertEqual(last.get("task"), "decide-close")
        self.assertEqual([x for x in self.intents("2026-10-20") if x[3] == "close" and x[2] == "AAA"], [])

    def test_real_money_never_picks_the_name(self):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-20 07:05:00")
        self.fetched_8k("0000000001-26-000103", "0000000001", "2026-10-20 12:00:00")
        self.at(et("2026-10-20", "09:16"))
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "decide-open")
        self.at(et("2026-10-20", "10:20"))
        self.mark_recorded()
        self.turns()
        lane = EB.Lane(EB.lane_path(self.root.parent))
        try:
            picks = EB.picks(lane, EB.program_of("EVL-ERN-REACT-C1", 2), dt.date(2026, 10, 20),
                             decided_at=et("2026-10-20", "15:46"), reaction=lambda row, uni: 1.05)
            self.assertEqual([p.symbol for p in picks], [])
            self.assertEqual(EB.eligible(lane, dt.date(2026, 10, 20)), [])
        finally:
            lane.close()

    def test_a_late_event_is_judged_by_the_backfill_rule_and_again_by_the_live_rule_for_a_live_decision(self):
        """A CIK first seen by the hourly re-decision (an event stored after the live open) is judged under the backfill
        rule (status=all: AAA eligible); that row serves the shadow's re-decisions, never real money; the session's live
        close decision checks it again under the live rule (tradable: false, ineligible) and does not take it."""
        self.fetched_8k("0000000002-26-000102", "0000000002", "2026-10-20 07:06:00")   # BBB, before the live open
        self.at(et("2026-10-20", "09:16"))
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "decide-open")
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-20 07:05:00",   # AAA, stored late (10:00 ET):
                        items=("8.01",))                                                # 8K-READ-O1's, not C1's
        with self.store() as st:
            st.db.execute("UPDATE filings SET received_at=? WHERE accession='0000000001-26-000101'",
                          (S.iso(et("2026-10-20", "10:00")),))
        self.at(et("2026-10-20", "10:20"))
        self.mark_recorded()
        self.turns()
        self.assertEqual(self.results("2026-10-20", "0000000001"), {"backfill": 1})
        self.assertIn(("EVL-CTRL-8K-ALL-O1", 1, "AAA", "open", "backfill"), self.intents("2026-10-20"),
                      "the late event decided by the backfill rule (PREREG-EVL-1 section 3: an outage removes nothing)")
        with self.store() as st:
            self.assertEqual(EB.eligible(st, dt.date(2026, 10, 20)), ["BBB"], "never on real money's list")
        self.fetched_8k("0000000001-26-000103", "0000000001", "2026-10-20 12:00:00")   # AAA earnings, close window
        self.at(et("2026-10-20", "15:47"))
        self.mark_recorded()
        for _ in range(4):
            if self.turn().get("task") == "decide-close":
                break
        self.assertEqual(self.results("2026-10-20", "0000000001"), {"backfill": 1, "live": 0})
        self.assertEqual([x for x in self.intents("2026-10-20") if x[3] == "close" and x[2] == "AAA"], [])


class EligibilityOnceASessionInTheLanesOwnRun(unittest.TestCase):
    """league/events/run.py alone: a live decision, then the same session decided again as a backfill."""

    def setUp(self):
        from league.tests import test_events_run as TR

        self.TR = TR
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        self.now = dt.datetime(2026, 10, 19, 13, 15, tzinfo=dt.timezone.utc)
        self.gw = Untradable({"AAA": 3, "BBB": 1})
        C.refresh(self.st, self.gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
        self.st.set_meta("tickers@2026-10-19T01:05:00Z", self.st.put_document(TR.sec_pages("x/company_tickers.json"), "t"))
        from league.events import programs as P

        self.P = P
        self._pinned = P.REGISTERED_AT
        P.REGISTERED_AT = "2026-10-19T01:00:00Z"

    def tearDown(self):
        self.P.REGISTERED_AT = self._pinned
        self.st.close()
        self.tmp.cleanup()

    def record(self, acc, cik):
        from league.events import edgar as E

        entry = {"form": "8-K", "cik": cik, "accession": acc, "company": "Co", "items": ["2.02"], "accepted_at": None,
                 "index_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"}
        self.assertEqual(E.record_filing(self.st, self.TR.sec_pages, entry, source="current", now=self.now), "fetched")

    def test_a_redecision_reads_the_live_result_and_judges_nothing_again(self):
        from league.events import run as R

        self.record("0000000001-26-000001", "0000000001")
        live = R.Context(self.st, self.gw, self.TR.sec_pages, now=lambda: self.now)
        out = R.decide_open(live, dt.date(2026, 10, 19))
        self.assertEqual(out["EVL-CTRL-ERN-ALL-O1"]["planned"], 0, "AAA is not tradable: the live rule refuses it")
        asked = len(self.gw.asset_calls)
        later = self.now + dt.timedelta(hours=1)
        again = R.Context(self.st, self.gw, self.TR.sec_pages, now=lambda: later)
        R.decide_open(again, dt.date(2026, 10, 19), backfill_run=True)
        rows = [dict(r) for r in self.st.db.execute("SELECT program, version, symbol FROM intents WHERE status='planned'")]
        self.assertEqual(rows, [], "the live session's shadow record does not change")
        self.assertEqual(len(self.gw.asset_calls), asked, "nothing judged again: no asset list asked for")
        self.assertEqual([tuple(r) for r in self.st.db.execute("SELECT cik, rule, eligible FROM eligibility")],
                         [("0000000001", "live", 0)])

    def test_two_results_read_eligible_only_when_neither_refuses(self):
        row = {"symbol": "AAA", "cik": "1"}
        self.assertIsNone(U.combined({"live": None, "backfill": row}))
        self.assertIsNone(U.combined({"backfill": None, "live": row}))
        self.assertIs(U.combined({"backfill": row, "live": dict(row, adv20=2)})["adv20"], 2, "the live rule's row")
        self.assertIs(U.combined({"backfill": row}), row)
        self.assertIsNone(U.combined({}))

    def test_an_empty_asset_list_decides_no_eligibility(self):
        from league.events import run as R

        self.record("0000000001-26-000001", "0000000001")
        self.gw.empty = True
        ctx = R.Context(self.st, self.gw, self.TR.sec_pages, now=lambda: self.now)
        with self.assertRaises(RuntimeError):
            R.decide_open(ctx, dt.date(2026, 10, 19))
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM eligibility").fetchone()[0], 0, "no result kept")


class Untradable:
    """league/tests/test_events_run.py's gateway with AAA listed on NASDAQ, active, `tradable: false` (its closing print
    on NASDAQ the session before)."""

    def __init__(self, scores):
        from league.tests import test_events_run as TR

        self.inner = TR.FakeGateway(scores)
        self.asset_calls: list[dict] = []
        self.empty = False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def get_json(self, path, params=None):
        if path.endswith("/v2/assets"):
            self.asset_calls.append(dict(params or {}))
            if self.empty:
                return []
            return [{"symbol": "AAA", "status": "active", "tradable": False, "class": "us_equity", "exchange": "NASDAQ"},
                    {"symbol": "BBB", "status": "active", "tradable": True, "class": "us_equity", "exchange": "NASDAQ"}]
        if "/trades" in path:
            return {"trades": [{"t": params["start"], "p": 20.0, "s": 100, "x": "Q", "c": ["6"]}], "next_page_token": None}
        return self.inner.get_json(path, params)


class TheStoreFromBeforeTheTableIsMigrated(unittest.TestCase):
    """A store from before `eligibility` (the House's copy of the desktop's): each universe row gets "eligible" under the
    rule of its session's FIRST decision receipt (live when it started within 10 minutes of its time, else backfill);
    meta `ELIGIBILITY_FROM` is the first session after the last decided one; a re-decision of such a session does not
    judge again a CIK its live run saw (its events stored before that run): ineligible, as that run found."""

    def setUp(self):
        from league.tests import test_events_run as TR

        self.TR = TR
        self.tmp = tempfile.TemporaryDirectory()
        st = S.Store(self.tmp.name)
        C.refresh(st, TR.FakeGateway({}), dt.date(2026, 8, 1), dt.date(2026, 12, 31))
        st.db.execute("DROP TABLE eligibility")
        st.db.execute("DELETE FROM meta WHERE key=?", (S.ELIGIBILITY_FROM,))
        for day, sym, cik in (("2026-10-19", "AAA", "0000000001"), ("2026-10-19", "BBB", "0000000002"),
                              ("2026-10-16", "AAA", "0000000001")):
            st.db.execute("INSERT INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench) VALUES(?, ?, "
                          "?, 'x', 'NASDAQ', 20, 2e7, 'IWM')", (day, sym, cik))
        for job, started, status in (("decide-open:2026-10-19", "2026-10-19T13:16:05Z", "ok"),       # live (09:16 ET)
                                     ("decide-open:2026-10-19", "2026-10-19T14:40:00Z", "ok"),       # the hourly one
                                     ("decide-close:2026-10-19", "2026-10-19T19:47:02Z", "ok"),
                                     ("decide-open:2026-10-16", "2026-10-16T15:00:00Z", "ok")):      # a catch-up
            st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES(?, ?, ?, ?, '{}')",
                          (job, started, started, status))
        st.close()
        self.st = S.Store(self.tmp.name)

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def test_each_row_takes_its_sessions_first_decisions_rule(self):
        got = sorted(tuple(r) for r in self.st.db.execute("SELECT day, cik, rule, eligible, symbol FROM eligibility"))
        self.assertEqual(got, [("2026-10-16", "0000000001", "backfill", 1, "AAA"),
                               ("2026-10-19", "0000000001", "live", 1, "AAA"),
                               ("2026-10-19", "0000000002", "live", 1, "BBB")])
        self.assertEqual(self.st.meta(S.ELIGIBILITY_FROM), "2026-10-20")
        self.st.close()
        self.st = S.Store(self.tmp.name)                               # once: a second open changes nothing
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM eligibility").fetchone()[0], 3)

    def test_a_redecision_of_a_session_from_before_the_table_trusts_what_its_live_run_saw(self):
        seen = {"0000000003": "2026-10-19T12:00:00Z",          # stored before the live open (13:16:05Z): it saw it
                "0000000004": "2026-10-19T14:00:00Z"}          # stored after it: never judged
        self.assertEqual(U.seen_live(self.st, dt.date(2026, 10, 19), "open", seen), {"0000000003"})
        self.assertEqual(U.seen_live(self.st, dt.date(2026, 10, 20), "open", seen), set(), "a session after the table")
        self.assertEqual(U.seen_live(self.st, dt.date(2026, 10, 16), "open", seen), set(), "no live run of it")



class TheReachIsTheJudges(unittest.TestCase):
    """The House takes its re-decision reach from the protected judge (league/events/screen.py, behind the wall): one
    definition; and a House that reached further would only delay a look (`screen._reach`), never move one earlier."""

    setUp, tearDown, settle = LooksOnAFinalRecord.setUp, LooksOnAFinalRecord.tearDown, LooksOnAFinalRecord.settle

    def test_the_house_and_the_cli_take_the_judges_reach(self):
        from league.events import __main__ as CLI

        self.assertIs(H.REDECIDE_SESSIONS, SC.FINAL_SESSIONS)
        self.assertIs(H.LOOKBACK, SC.FINAL_LOOKBACK)
        self.assertIs(H.BACKFILL_WEEKDAYS, SC.FINAL_BACKFILL_WEEKDAYS)
        self.assertIs(CLI.REDECIDE_SESSIONS, SC.FINAL_SESSIONS)
        source = (REPO / "league" / "events" / "house.py").read_text(encoding="utf-8")
        for name, judge in (("REDECIDE_SESSIONS", "SN.FINAL_SESSIONS"), ("LOOKBACK", "SN.FINAL_LOOKBACK"),
                            ("BACKFILL_WEEKDAYS", "SN.FINAL_BACKFILL_WEEKDAYS")):
            self.assertEqual([line for line in source.splitlines() if line.startswith(f"{name} =")],
                             [f"{name} = {judge}"], "defined once, in the judge")

    def test_a_house_that_reaches_further_only_delays_the_look(self):
        p = "EVL-INS-BUY-O1"
        self.settle(p, 2, 10, self.days[:8], lambda i: 0.01)
        now = final_record(self.st, self.days[10])
        with mock.patch.object(H, "REDECIDE_SESSIONS", 4):
            out = SC.run(self.st, self.days[10], draws=999, now=now)
        self.assertEqual(out["written"], [], "the House would still decide days[7] again")
        self.assertIn("re-decision window", out["waiting"][0]["why"])
        out = SC.run(self.st, self.days[10], draws=999, now=now)
        self.assertEqual([(w["program"], w["k"]) for w in out["written"]], [(p, 1)])


class ADemotedProgramReturnsToProbe(unittest.TestCase):
    """PREREG-EVL-3 section 2: a demoted program "returns to Probe at its next passed look". The demotion windows count
    the current Probe stay (its events bought after its latest move to Probe); so does Sized (the third review)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        C.refresh(self.st, CalendarGateway({}), dt.date(2026, 10, 1), dt.date(2027, 3, 31))
        self.n = 0

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def fills(self, program, day, n, sell_px):
        for _ in range(n):
            ev = f"real:{self.n}"
            self.n += 1
            self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                               "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, 2, ?, 'S', ?, 'z', ?, 'open', ?, "
                               "'close', NULL, 'shadow', 'exited', NULL)",
                               (program, ev, f"{self.n:010d}", day.isoformat(), day.isoformat()))
            BA.record_fill(self.st, program=program, version=2, event=ev, side="buy", qty=10, price=10.0, fee=0.0,
                           filled_at=f"{day.isoformat()}T13:30:00Z", band="probe")
            BA.record_fill(self.st, program=program, version=2, event=ev, side="sell", qty=10, price=sell_px, fee=0.0,
                           filled_at=f"{day.isoformat()}T20:00:00Z", band="probe")

    def test_demoted_then_a_passed_look_and_it_stays_probe_through_that_nights_review(self):
        p = "EVL-INS-BUY-O1"
        utc = dt.timezone.utc
        BA.set_band(self.st, p, 2, "probe", since="2026-10-20T20:00:00Z", why="look 1 passed",
                    now=dt.datetime(2026, 10, 21, 1, 0, tzinfo=utc))
        self.fills(p, dt.date(2026, 10, 22), 50, 9.65)                     # 50 x -$3.50 = -$175 < -$150
        moved = BA.review(self.st, now=dt.datetime(2026, 10, 23, 1, 0, tzinfo=utc))
        self.assertEqual([c["band"] for c in moved], ["learning"])
        BA.on_look(self.st, {"program": p, "version": 2, "k": 2, "held": 1, "passed": 1, "at": "2026-11-02T21:00:00Z",
                             "retirement": {"retire": False}}, now=dt.datetime(2026, 11, 5, 1, 0, tzinfo=utc))
        self.assertEqual(BA.bands(self.st)[(p, 2)], "probe")
        self.assertEqual(BA.review(self.st, now=dt.datetime(2026, 11, 5, 1, 5, tzinfo=utc)), [],
                         "the same night's review: the stay that was demoted is not this one")
        self.assertEqual(BA.bands(self.st)[(p, 2)], "probe")
        self.fills(p, dt.date(2026, 11, 5), 50, 9.65)                      # the new stay loses as much
        moved = BA.review(self.st, now=dt.datetime(2026, 11, 6, 1, 0, tzinfo=utc))
        self.assertEqual([c["band"] for c in moved], ["learning"], "its own stay's events demote it")

    def test_sized_counts_the_current_probe_stay(self):
        """(Release 1019b's third review: Sized's count and bound are over the current Probe stay, as demotion's are.)"""
        p = "EVL-INS-BUY-O1"
        utc = dt.timezone.utc
        BA.set_band(self.st, p, 2, "probe", since="2026-10-20T20:00:00Z", why="look", now=dt.datetime(2026, 10, 21, tzinfo=utc))
        self.fills(p, dt.date(2026, 10, 22), 10, 10.05)
        seen = []
        with mock.patch.object(BA, "probe_since", return_value=dt.datetime(2030, 1, 1, tzinfo=utc)), \
                mock.patch.object(BA, "SIZED_MIN", 10), \
                mock.patch.object(SC, "sized_bound", side_effect=lambda events: seen.append(len(events)) or {
                    "ok": True, "session": {"lower": 0.001}}):
            moved = BA.review(self.st, now=dt.datetime(2026, 10, 23, tzinfo=utc))
        self.assertEqual(moved, [], "no event of the current stay: not Sized")
        self.assertEqual(seen, [])
        with mock.patch.object(BA, "SIZED_MIN", 10), \
                mock.patch.object(SC, "sized_bound", side_effect=lambda events: seen.append(len(events)) or {
                    "ok": True, "session": {"lower": 0.001}}):
            moved = BA.review(self.st, now=dt.datetime(2026, 10, 23, tzinfo=utc))
        self.assertEqual([c["band"] for c in moved], ["sized"], "the stay's own 10 events")
        self.assertEqual(seen, [10])



# ============================================================================================ the third review: the House
def _minute_at(h, hh: int, mm: int, ss: int = 3) -> dict:
    """The House's minute hh:mm:ss, or later when the one before ran past it (the House's clock never goes back)."""
    h.clock.set(max(TB.at(DAY, hh, mm, ss), h.clock()))
    return h.book.tick(h.clock(), account_row=h.venue.account(), positions=None, open_orders=None,
                       real_block=lambda opening=True: h.blocked, killed=lambda: h.kill)


def _close_day(h, *, names: int) -> None:
    """DAY with: a READ-O1 (version 2) lot bought at the open and due out at the close (market-on-close); a score-3
    day-news article of NEWS (EVL-NEWS-READ-ON's pick at the close: it reads no T29 minute); a day-news article of S00X
    (EVL-NEWS-REACT-ON's, which reads its T29 minute); and `names` live names in the day's universe in all."""
    earnings(h.lane, "a-1", CIK, "ACME")
    h.lane.intent(TB.V2("EVL-ERN-READ-O1"), "8k:a-1", "ACME", CIK, DAY, DAY)
    h.lane.decided(DAY, "open")
    h.symbol("ACME", last=17.0, sd=0.02)
    h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("17.00")
    h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("17.50")
    h.lane.universe(DAY, "NEWS", "0000000700", 16.0)
    h.symbol("NEWS", last=16.5)
    h.lane.article("n-read", "NEWS", knowable=iso(DAY, 10, 5))
    h.lane.verdict("n-read", 3, answered=iso(DAY, 10, 6), news=True)
    h.lane.universe(DAY, "S00X", "0000000900", 16.0)
    h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('S00X', ?, 'raw', 16, 16, "
                         "16, 16.0, 1e6, 'x')", (PRIOR.isoformat(),))
    h.symbol("S00X", last=17.0)
    h.lane.article("n-react", "S00X", knowable=iso(DAY, 10, 5))
    for i in range(names - 3):
        h.lane.universe(DAY, f"N{i:03d}", f"{5000 + i:010d}", 16.0)


def _hanging_minutes(h, seconds: float = 20.0) -> list[tuple[float, int]]:
    """Alpaca's 1Min bars hang: each request runs `seconds` into the client's timeout, then raises."""
    calls: list[tuple[float, int]] = []
    real = h.market.bars

    def bars(symbols, *, timeframe, start, end=None, adjustment="raw"):
        if timeframe != "1Min":
            return real(symbols, timeframe=timeframe, start=start, end=end, adjustment=adjustment)
        calls.append((h.clock(), len(list(symbols))))
        h.clock.set(h.clock() + seconds)
        raise TimeoutError("market data bars 1Min: timed out")
    h.market.bars = bars
    return calls


def _sent_at(h) -> list[tuple[float, str, str, str]]:
    """(wall clock, side, symbol, time in force) of every order the venue was sent, as it was sent."""
    log: list[tuple[float, str, str, str]] = []
    real = h.venue.submit

    def submit(body, *, exit):
        log.append((h.clock(), body["side"], body["symbol"], body["time_in_force"]))
        return real(body, exit=exit)
    h.venue.submit = submit
    return log


class TheSalesGoBeforeTheDecision(EventTest):
    """Release 1019b's third review (House, major): the close decision reads every live name's T29 minute, 200 names a
    request, and `_send` judges the 15:49 cut-off on the wall clock. With 450 live names and Alpaca's 1Min bars hanging
    to the client's timeout, the sales of the auction went only after the decision returned, past the cut-off: every
    event lot due out at that close missed its market-on-close sale. Now each auction's SALES go first, then its
    decision, then its BUYS; and the T29 reads are bounded by the window (never again after a timeout, none started in
    its last minute)."""

    def open_then_close(self, h, *, names: int = 450) -> list[tuple[float, int]]:
        _close_day(h, names=names)
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33), (15, 46)):
            h.tick(hh, mm)
        [lot] = [lot for lot in h.lots() if lot.status != "closed"]
        self.assertEqual(lot.info["evl_exit"], {"day": DAY.isoformat(), "at": "close", "rung": 0})
        self.assertEqual([r["status"] for r in h.event_intents("sell")], ["planned"], "planned at 15:46")
        h.lane.decided(DAY, "close")
        return _hanging_minutes(h)

    def test_450_names_hanging_every_due_sale_is_sent_before_the_cut_off(self):
        h = self.harness()
        calls = self.open_then_close(h)
        sent = _sent_at(h)
        _minute_at(h, 15, 47)
        cut = TB.at(DAY, 15, 49, 0)
        sales = [(t, sym) for t, side, sym, tif in sent if side == "sell"]
        self.assertEqual([sym for _, sym in sales], ["ACME"], "the market-on-close sale of the lot due out")
        self.assertLess(sales[0][0], calls[0][0] + 1e-6, "sent before the decision's first T29 request")
        self.assertLess(sales[0][0], cut)
        self.assertEqual([n for _, n in calls], [200, 200, 50], "three chunks, none sent again after its timeout")
        self.assertTrue(all(t < TB.at(DAY, 15, 48, 0) for t, _ in calls), "every request before the last minute")
        [row] = h.state.rows("SELECT status, summary FROM eq_event_decisions WHERE day=? AND at='close'",
                             (DAY.isoformat(),))
        self.assertEqual(row["status"], "done", "made with what was read")
        self.assertIn("TimeoutError", json.loads(row["summary"])["errors"][0])
        buys = [(t, sym, tif) for t, side, sym, tif in sent if side == "buy"]
        self.assertEqual([(sym, tif) for _, sym, tif in buys], [("NEWS", "cls")], "NEWS-READ-ON's buy goes; no REACT row")
        self.assertLess(buys[0][0], cut, "before the cut-off")
        self.assertEqual([r["status"] for r in h.event_intents("sell")], ["sent"])

    def test_a_150_name_day_reads_one_chunk_and_sends_the_sale_first_too(self):
        h = self.harness()
        calls = self.open_then_close(h, names=150)
        sent = _sent_at(h)
        _minute_at(h, 15, 47)
        self.assertEqual([n for _, n in calls], [150])
        self.assertEqual([(side, sym) for _, side, sym, _ in sent], [("sell", "ACME"), ("buy", "NEWS")])

    def test_no_t29_request_starts_in_the_windows_last_minute(self):
        """A decision whose reads begin at 15:47:30: the first two chunks run to 15:48:10, and the third is never
        started (the window's last minute began at 15:48:00); the decision is made with what was read at 15:48:10 and
        NEWS-READ-ON's buy goes before 15:49."""
        h = self.harness()
        calls = self.open_then_close(h)
        sent = _sent_at(h)
        _minute_at(h, 15, 47, 30)
        self.assertEqual([n for _, n in calls], [200, 200])
        [row] = h.state.rows("SELECT status, summary FROM eq_event_decisions WHERE day=? AND at='close'",
                             (DAY.isoformat(),))
        self.assertEqual(row["status"], "done")
        self.assertTrue(any("last minute" in e for e in json.loads(row["summary"])["errors"]), row["summary"])
        self.assertEqual([(side, sym) for _, side, sym, _ in sent], [("sell", "ACME"), ("buy", "NEWS")])
        self.assertTrue(all(t < TB.at(DAY, 15, 49, 0) for t, *_ in sent))

    def test_a_decision_first_made_in_the_last_minute_reads_no_t29_minute(self):
        """The House's first minute inside the close window is 15:48 (it was down at 15:46 and 15:47): the exits due are
        planned and sold first, the decision reads no T29 minute (the window's last minute), and takes every pick that
        needs none."""
        h = self.harness()
        _close_day(h, names=10)
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
            h.tick(hh, mm)
        h.lane.decided(DAY, "close")
        calls = _hanging_minutes(h)
        sent = _sent_at(h)
        _minute_at(h, 15, 48)
        self.assertEqual(calls, [])
        self.assertEqual([(side, sym) for _, side, sym, _ in sent], [("sell", "ACME"), ("buy", "NEWS")])

    def test_a_request_that_did_not_time_out_is_sent_again_once_before_the_last_minute(self):
        h = self.harness()
        _close_day(h, names=10)
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33), (15, 46)):
            h.tick(hh, mm)
        h.lane.decided(DAY, "close")
        calls: list[float] = []
        real = h.market.bars

        def bars(symbols, *, timeframe, start, end=None, adjustment="raw"):
            if timeframe != "1Min":
                return real(symbols, timeframe=timeframe, start=start, end=end, adjustment=adjustment)
            calls.append(h.clock())
            raise RuntimeError("market data bars 1Min: HTTP 503")
        h.market.bars = bars
        _minute_at(h, 15, 47)
        self.assertEqual(len(calls), 2, "a 503 is sent again once")
        self.assertFalse(L._timed_out(RuntimeError("HTTP 503")))
        self.assertTrue(L._timed_out(TimeoutError("x")))
        wrapped = RuntimeError("GET bars failed")
        wrapped.__cause__ = OSError("The read operation timed out")
        self.assertTrue(L._timed_out(wrapped), "a timeout a transport error wraps")


class AT29FailureDropsOnlyTheReactRows(EventTest):
    """Release 1019b's third review (money and House, minor): when the batched T29 read fails, the decision is made with
    what was read: a REACT row of an unread name is not taken, every other close-entry program's picks go
    (EVL-NEWS-READ-ON reads no T29 minute), and the summary says why."""

    def test_news_read_on_buys_with_the_t29_minutes_down(self):
        h = self.harness()
        _close_day(h, names=5)
        h.lane.decided(DAY, "open")
        real = h.market.bars

        def bars(symbols, *, timeframe, start, end=None, adjustment="raw"):
            if timeframe != "1Min":
                return real(symbols, timeframe=timeframe, start=start, end=end, adjustment=adjustment)
            raise RuntimeError("market data bars 1Min: HTTP 503")
        h.market.bars = bars
        self.ready(h)
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33), (15, 46), (15, 47)):
            h.tick(hh, mm)
        took = [(r["program"], r["symbol"]) for r in h.event_intents("buy") if r["at"] == "close"]
        self.assertEqual(took, [("EVL-NEWS-READ-ON", "NEWS")])
        [row] = h.state.rows("SELECT status, summary FROM eq_event_decisions WHERE day=? AND at='close'",
                             (DAY.isoformat(),))
        self.assertEqual(row["status"], "done")
        summary = json.loads(row["summary"])
        self.assertIn("HTTP 503", summary["errors"][0])
        self.assertEqual(summary["programs"]["EVL-NEWS-REACT-ON"].get("planned", 0), 0)
        sent = [(b["symbol"], b["side"], b["time_in_force"]) for b in h.bodies() if b["time_in_force"] == "cls"]
        self.assertIn(("NEWS", "buy", "cls"), sent)
        self.assertIn(("ACME", "sell", "cls"), sent)



# =========================================================================================== the third review: the judges
class DemotedFromSizedEarnsSizedAgainOnItsNewStay(unittest.TestCase):
    """Release 1019b's third review (judges, minor): Sized counted every Probe+ event while demotion counted the current
    Probe stay, so a Sized program demoted on its last 50 events and returned to Probe at its next passed look was moved
    straight back to SIZED (10% a position) by the same night's review, on the events of the stay that got it demoted.
    Sized now counts the current Probe stay too (the reading that trades less)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        C.refresh(self.st, CalendarGateway({}), dt.date(2026, 10, 1), dt.date(2027, 6, 30))
        self.days = [s.day for s in C.sessions(self.st, dt.date(2026, 10, 20), dt.date(2027, 6, 30))]
        self.n = 0

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def fills(self, program, day, n, sell_px, band):
        for _ in range(n):
            ev = f"real:{self.n}"
            self.n += 1
            self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                               "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, 2, ?, 'S', ?, 'z', ?, 'open', ?, "
                               "'close', NULL, 'shadow', 'exited', NULL)",
                               (program, ev, f"{self.n:010d}", day.isoformat(), day.isoformat()))
            BA.record_fill(self.st, program=program, version=2, event=ev, side="buy", qty=10, price=10.0, fee=0.0,
                           filled_at=f"{day.isoformat()}T13:30:00Z", band=band)
            BA.record_fill(self.st, program=program, version=2, event=ev, side="sell", qty=10, price=sell_px, fee=0.0,
                           filled_at=f"{day.isoformat()}T20:00:00Z", band=band)

    def test_returned_to_probe_it_stays_probe_until_its_new_stay_earns_sized(self):
        p, utc = "EVL-INS-BUY-O1", dt.timezone.utc
        BA.set_band(self.st, p, 2, "probe", since="2026-10-20T20:00:00Z", why="look 1",
                    now=dt.datetime(2026, 10, 21, tzinfo=utc))
        for i, d in enumerate(self.days[2:42]):                              # 200 Probe events over 40 sessions
            self.fills(p, d, 5, 10.20 if i % 5 else 9.95, "probe")
        moved = BA.review(self.st, now=dt.datetime(2026, 12, 20, tzinfo=utc))
        self.assertEqual([c["band"] for c in moved], ["sized"])
        for d in self.days[42:52]:                                           # 50 Sized events, -$3.50 each: -$175
            self.fills(p, d, 5, 9.65, "sized")
        moved = BA.review(self.st, now=dt.datetime(2027, 1, 10, tzinfo=utc))
        self.assertEqual([c["band"] for c in moved], ["learning"])
        BA.on_look(self.st, {"program": p, "version": 2, "k": 5, "held": 1, "passed": 1, "at": "2027-01-20T21:00:00Z",
                             "retirement": {"retire": False}}, now=dt.datetime(2027, 1, 25, 1, 0, tzinfo=utc))
        self.assertEqual(BA.bands(self.st)[(p, 2)], "probe")
        moved = BA.review(self.st, now=dt.datetime(2027, 1, 25, 1, 5, tzinfo=utc))   # the same night's review
        self.assertEqual(moved, [], "Probe: the demoted stay's events never make it Sized again")
        self.assertEqual(BA.bands(self.st)[(p, 2)], "probe")
        later = [d for d in self.days if d > dt.date(2027, 1, 25)]
        for i, d in enumerate(later[:40]):                                   # its new stay: 200 Probe events
            self.fills(p, d, 5, 10.20 if i % 5 else 9.95, "probe")
        moved = BA.review(self.st, now=dt.datetime(2027, 4, 1, tzinfo=utc))
        self.assertEqual([c["band"] for c in moved], ["sized"], "its new stay earns Sized")


class MarkedStore(unittest.TestCase):
    """The desktop's store (from before `eligibility`) migrated at the House's first open of it. Monday Oct 19 was
    decided LIVE on the desktop (open 13:16:05Z, close 19:46:30Z), whose A67 hotfix marks each CIK the live rule refused
    as meta `elig-no:<day>:<cik>` = "live". AAA is listed on NASDAQ, active, `tradable: false` (the live rule refuses it,
    the backfill rule takes it); BBB is tradable."""

    DAY = dt.date(2026, 10, 19)

    def setUp(self):
        from league.events import programs as P
        from league.tests import test_events_run as TR

        self.TR, self.P = TR, P
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        self.gw = Untradable({"AAA": 3, "BBB": 3})
        C.refresh(self.st, self.gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
        self.st.set_meta("tickers@2026-10-19T01:05:00Z", self.st.put_document(TR.sec_pages("x/company_tickers.json"), "t"))
        self._pinned = P.REGISTERED_AT
        P.REGISTERED_AT = "2026-10-19T01:00:00Z"
        self.fail_index: set[str] = set()
        self.accepted: dict[str, tuple[str, str]] = {}

    def tearDown(self):
        self.P.REGISTERED_AT = self._pinned
        self.st.close()
        self.tmp.cleanup()

    def sec(self, url):
        if url.endswith("-index.htm"):
            acc = url.rsplit("/", 1)[1].replace("-index.htm", "")
            if acc in self.fail_index:
                raise RuntimeError("HTTP 503: SEC")
            if acc in self.accepted:
                accepted, items = self.accepted[acc]
                return (f'<div class="infoHead">Accepted</div><div class="info">{accepted}</div>'
                        f'<div class="infoHead">Items</div><div class="info">{items}</div>'
                        f'<table><tr><td>1</td><td>press release</td><td><a href="/Archives/x/{acc}/ex99.htm">ex99.htm'
                        f'</a></td><td>EX-99.1</td><td>100</td></tr></table>').encode()
        if url.endswith("ex99.htm"):        # (each filing's own document, as on EDGAR: documents are kept by content)
            return self.TR.sec_pages(url).replace(b"</body>", f"<p>{url}</p></body>".encode())
        return self.TR.sec_pages(url)

    def ctx(self, when):
        return R.Context(self.st, self.gw, self.sec, now=lambda: S.parse_iso(when))

    def file(self, acc, cik, accepted_et, items, when):
        from league.events import edgar as E

        self.accepted[acc] = (accepted_et, items)
        entry = {"form": "8-K", "cik": cik, "accession": acc, "company": "Co", "items": [], "accepted_at": None,
                 "index_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"}
        return E.record_filing(self.st, self.sec, entry, source="current", now=S.parse_iso(when))

    def migrate(self, markers=()):
        """The desktop's store as evl_migrate.py copies it: no `eligibility` rows, no `ELIGIBILITY_FROM`, the A67
        markers; then the House's first open of it (`_migrate`)."""
        self.st.db.execute("DELETE FROM eligibility")
        self.st.db.execute("DELETE FROM meta WHERE key=?", (S.ELIGIBILITY_FROM,))
        for cik in markers:
            self.st.set_meta(f"elig-no:{self.DAY.isoformat()}:{cik}", "live")
        self.st.close()
        self.st = S.Store(self.tmp.name)
        self.assertEqual(self.st.meta(S.ELIGIBILITY_FROM), "2026-10-20")

    def results(self, cik):
        return {r["rule"]: r["eligible"] for r in self.st.db.execute(
            "SELECT rule, eligible FROM eligibility WHERE day=? AND cik=?", (self.DAY.isoformat(), cik))}

    def planned(self, symbol, at):
        return sorted((r["program"], r["version"], r["why"]) for r in self.st.db.execute(
            "SELECT * FROM intents WHERE entry_day=? AND symbol=? AND entry_at=? AND status='planned'",
            (self.DAY.isoformat(), symbol, at)))


class TheDesktopsLiveRefusalsSurviveTheMigration(MarkedStore):
    """Release 1019b's third review (judges, major): the migration keeps each marker as a live refusal, so a refusal of
    the desktop's live OPEN holds at a backfill re-decision of either kind (A67: "a CIK the live rule rejected for an
    entry session stays rejected for that session")."""

    def test_the_migration_keeps_each_marker_as_a_live_refusal(self):
        self.st.db.execute("INSERT INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench) VALUES("
                           "'2026-10-19', 'BBB', '0000000002', 'x', 'NASDAQ', 20, 2e7, 'IWM')")
        self.st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES("
                           "'decide-open:2026-10-19', '2026-10-19T13:24:51Z', '2026-10-19T13:27:01Z', 'ok', '{}')")
        self.st.set_meta("elig-no:2026-10-19:0000000009", "something else")      # not the hotfix's mark: not kept
        self.st.set_meta("elig-no:not-a-day:0000000008", "live")
        self.migrate(markers=["0000000001", "0000000003"])
        got = sorted(tuple(r) for r in self.st.db.execute("SELECT day, cik, rule, eligible, symbol, decided_at FROM "
                                                          "eligibility"))
        self.assertEqual(got, [("2026-10-19", "0000000001", "live", 0, None, "migrated"),
                               ("2026-10-19", "0000000002", "live", 1, "BBB", "migrated"),
                               ("2026-10-19", "0000000003", "live", 0, None, "migrated")])
        self.assertTrue(S.has_markers(self.st.db, "2026-10-19"))
        self.assertFalse(S.has_markers(self.st.db, "2026-10-16"))

    def test_a_marker_refuses_at_a_close_redecision(self):
        """AAA (tradable: false) was refused by Monday's live open (its marker). Its earnings 8-K of 12:00 ET and a
        day-news article are stored on Tuesday (the daily-index backfill): the hourly re-decision of Monday's CLOSE
        (a backfill) never admits it."""
        self.assertEqual(self.file("0000000001-26-000011", "0000000001", "2026-10-19 07:05:00", "Item 8.01: Other",
                                   "2026-10-19T11:06:00Z"), "fetched")
        R.decide_open(self.ctx("2026-10-19T13:16:05Z"), self.DAY)
        R.decide_close(self.ctx("2026-10-19T19:46:30Z"), self.DAY)
        self.migrate(markers=["0000000001"])
        self.assertEqual(self.results("0000000001"), {"live": 0})
        self.assertEqual(self.file("0000000001-26-000012", "0000000001", "2026-10-19 12:00:00", "Item 2.02: Results",
                                   "2026-10-20T11:10:00Z"), "fetched")
        self.st.db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, headline, "
                           "summary, symbols, live) VALUES('n1', '2026-10-19T17:00:00Z', NULL, '2026-10-20T11:12:00Z', "
                           "'2026-10-19T17:02:00Z', 'x', 'AAA news', 's', '[\"AAA\"]', 0)")
        R.decide_close(self.ctx("2026-10-20T14:20:00Z"), self.DAY, backfill_run=True)
        self.assertEqual((self.results("0000000001"), self.planned("AAA", "close")), ({"live": 0}, []))

    def test_a_marker_refuses_at_an_open_redecision(self):
        """A marked CIK whose open-window 8-K is first stored after the live open (BBB, tradable, so either rule would
        take it): the hourly re-decision of the OPEN keeps the desktop's live refusal."""
        R.decide_open(self.ctx("2026-10-19T13:16:05Z"), self.DAY)
        R.decide_close(self.ctx("2026-10-19T19:46:30Z"), self.DAY)
        self.migrate(markers=["0000000002"])
        self.assertEqual(self.file("0000000002-26-000021", "0000000002", "2026-10-19 07:10:00", "Item 2.02: Results",
                                   "2026-10-20T11:12:00Z"), "fetched")
        R.decide_open(self.ctx("2026-10-20T14:20:00Z"), self.DAY, backfill_run=True)
        self.assertEqual((self.results("0000000002"), self.planned("BBB", "open")), ({"live": 0}, []))

    def test_a_day_with_markers_reads_nothing_more_from_seen_live(self):
        """BBB's 8-K was LISTED before the live open (11:12Z) but its fetch failed (an SEC 503) and it was fetched on
        Tuesday: the live run never saw it, and Monday's markers (another CIK's) are its exact refusals, so the
        re-decision judges BBB by the backfill rule and the shadow keeps its event."""
        self.fail_index.add("0000000002-26-000031")
        got = self.file("0000000002-26-000031", "0000000002", "2026-10-19 07:10:00", "Item 2.02: Results",
                        "2026-10-19T11:12:00Z")
        self.assertTrue(got.startswith("failed:"), got)
        self.fail_index.clear()
        R.decide_open(self.ctx("2026-10-19T13:16:05Z"), self.DAY)
        R.decide_close(self.ctx("2026-10-19T19:46:30Z"), self.DAY)
        self.migrate(markers=["0000000009"])
        self.assertEqual(self.file("0000000002-26-000031", "0000000002", "2026-10-19 07:10:00", "Item 2.02: Results",
                                   "2026-10-20T11:12:00Z"), "fetched")
        self.assertEqual(U.seen_live(self.st, self.DAY, "open", {"0000000002": "2026-10-19T11:12:00Z"}), set(),
                         "a day with markers: they are its refusals")
        R.decide_open(self.ctx("2026-10-20T14:20:00Z"), self.DAY, backfill_run=True)
        self.assertEqual(self.results("0000000002"), {"backfill": 1})
        self.assertIn(("EVL-CTRL-ERN-ALL-O1", 1, "backfill"), self.planned("BBB", "open"))


class AMarkerlessLegacyDay(MarkedStore):
    """A session from before the table WITHOUT markers (decided live before the hotfix): `seen_live` reads a CIK with
    no result as a live refusal when this decision's first event of it was FETCHED before the session's first finished
    live decision of either kind; a filing only LISTED before it was never seen by it."""

    def test_fetched_before_the_live_run_is_its_refusal_listed_before_and_fetched_after_is_not(self):
        self.fail_index.add("0000000002-26-000041")
        self.assertTrue(self.file("0000000002-26-000041", "0000000002", "2026-10-19 07:10:00", "Item 2.02: Results",
                                  "2026-10-19T11:12:00Z").startswith("failed:"))
        self.fail_index.clear()
        self.assertEqual(self.file("0000000001-26-000042", "0000000001", "2026-10-19 07:05:00", "Item 2.02: Results",
                                   "2026-10-19T11:06:00Z"), "fetched")
        R.decide_open(self.ctx("2026-10-19T13:16:05Z"), self.DAY)                    # LIVE open: AAA refused
        self.migrate(markers=[])
        self.assertEqual(self.results("0000000001"), {}, "no marker: the refusal was never kept")
        self.assertEqual(self.file("0000000002-26-000041", "0000000002", "2026-10-19 07:10:00", "Item 2.02: Results",
                                   "2026-10-20T11:12:00Z"), "fetched")
        row = self.st.db.execute("SELECT received_at FROM filings WHERE accession='0000000002-26-000041'").fetchone()
        self.assertEqual(row["received_at"], "2026-10-19T11:12:00Z", "the listing time")
        self.assertEqual(R._first_fetched(self.st, [dict(r) for r in self.st.db.execute(
            "SELECT * FROM filings WHERE accession='0000000002-26-000041'")]), {"0000000002": "2026-10-20T11:12:00Z"})
        R.decide_open(self.ctx("2026-10-20T14:20:00Z"), self.DAY, backfill_run=True)
        self.assertEqual(self.results("0000000001"), {"live": 0}, "fetched before the live open: as it found")
        self.assertEqual(self.planned("AAA", "open"), [])
        self.assertEqual(self.results("0000000002"), {"backfill": 1}, "fetched after it: judged as a late event")
        self.assertIn(("EVL-CTRL-ERN-ALL-O1", 1, "backfill"), self.planned("BBB", "open"))

    def test_the_first_finished_live_run_of_either_kind(self):
        self.st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES("
                           "'decide-close:2026-10-19', '2026-10-19T19:47:02Z', '2026-10-19T19:48:00Z', 'ok', '{}')")
        self.st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES("
                           "'decide-open:2026-10-19', '2026-10-19T13:20:00Z', '2026-10-19T13:21:00Z', 'failed', '{}')")
        self.migrate(markers=[])
        seen = {"0000000003": "2026-10-19T17:00:00Z", "0000000004": "2026-10-19T19:50:00Z"}
        self.assertEqual(U.seen_live(self.st, self.DAY, "open", seen), {"0000000003"}, "the live close: the only one")
        self.st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES("
                           "'decide-open:2026-10-19', '2026-10-19T13:24:51Z', '2026-10-19T13:27:01Z', 'ok', '{}')")
        self.assertEqual(U.seen_live(self.st, self.DAY, "close", seen), set(), "the live open is the first: 13:24:51Z")
        self.assertEqual(U.seen_live(self.st, self.DAY, "close", {"0000000005": "2026-10-19T13:00:00Z"}),
                         {"0000000005"})


class TheHousesLiveRuleIsTheJudges(unittest.TestCase):
    """Release 1019b's third review (judges, minor): each run's live-or-backfill rule fixes its session's eligibility
    for good, so the choice is the protected judge's (league/events/run.py `LIVE_WITHIN`, `live_run`, behind
    league/ci.py's wall), and the House's lane and the CLI take it from there."""

    def test_one_definition_in_the_judge(self):
        from league import ci
        from league.events import __main__ as CLI

        self.assertIs(H.LIVE_WITHIN, R.LIVE_WITHIN)
        self.assertEqual(R.LIVE_WITHIN, dt.timedelta(minutes=10))
        self.assertTrue(ci.guard(["league/events/run.py"], None))
        source = (REPO / "league" / "events" / "house.py").read_text(encoding="utf-8")
        self.assertEqual([line for line in source.splitlines() if line.startswith("LIVE_WITHIN =")],
                         ["LIVE_WITHIN = R.LIVE_WITHIN"])
        self.assertNotIn("+ LIVE_WITHIN", source)
        self.assertNotIn("<= LIVE_WITHIN", source)
        self.assertIn("R.live_run(", (REPO / "league" / "events" / "__main__.py").read_text(encoding="utf-8"))
        self.assertTrue(CLI.R is R)
        t = dt.datetime(2026, 10, 20, 13, 15, tzinfo=dt.timezone.utc)
        self.assertTrue(R.live_run(t, t - dt.timedelta(hours=2)), "verdicts asked ahead read the live rule")
        self.assertTrue(R.live_run(t, t + dt.timedelta(minutes=10)))
        self.assertFalse(R.live_run(t, t + dt.timedelta(minutes=10, seconds=1)))



# ======================================================================================= the third review: House minors
class AnEmptyAssetListIsNeverKept(LaneCase):
    """Release 1019b's third review (House and judges, minor): `run.eligibility` decides nothing on an empty asset list
    (it raises), but the lane kept whatever Alpaca answered for ASSETS_TTL (30 minutes): one empty answer failed every
    live open run of the session until LIVE_WITHIN was gone, and the open was then decided as a BACKFILL (no live
    result: no real open entry that session). An empty answer is never kept: the next turn asks again."""

    def test_one_empty_answer_and_the_open_is_still_decided_live(self):
        self.fetched_8k("0000000002-26-000102", "0000000002", "2026-10-20 07:06:00")   # BBB, open window of Tue
        real = self.gw.get_json
        answers = {"n": 0}

        def get_json(path, params=None):
            if path.endswith("/v2/assets") and (params or {}).get("status") == "active":
                answers["n"] += 1
                if answers["n"] == 1:
                    return []                                   # one empty answer (a transient)
            return real(path, params)
        self.gw.get_json = get_json
        statuses = []
        for minute in range(16, 31):
            self.at(et("2026-10-20", f"09:{minute:02d}"))
            self.mark_recorded()
            last = self.turn()
            if last.get("task") == "decide-open":
                statuses.append((minute, last.get("status")))
        self.assertEqual(statuses[0], (16, "failed"), "the empty answer: nothing decided on it")
        self.assertEqual(statuses[1], (17, "ok"), "asked again a minute later, and decided live")
        self.assertGreaterEqual(answers["n"], 2)
        with self.store() as st:
            rules = sorted({r[0] for r in st.db.execute("SELECT rule FROM eligibility WHERE day='2026-10-20'")})
            whys = {r[0] for r in st.db.execute("SELECT why FROM intents WHERE entry_day='2026-10-20'")}
        self.assertEqual(rules, ["live"])
        self.assertEqual(whys, {None}, "live decisions (a backfill's intents say 'backfill')")

    def test_a_list_is_kept_for_its_ttl(self):
        calls = []
        real = self.gw.get_json

        def get_json(path, params=None):
            if path.endswith("/v2/assets"):
                calls.append(dict(params or {}))
            return real(path, params)
        self.gw.get_json = get_json
        self.lane.assets(self.gw, "active")
        self.lane.assets(self.gw, "active")
        self.assertEqual(len(calls), 1, "a list with names is kept")
        self.gw.get_json = lambda path, params=None: [] if path.endswith("/v2/assets") else real(path, params)
        self.lane._asset_cache.clear()
        self.assertEqual(self.lane.assets(self.gw, "active"), {})
        self.assertNotIn("active", self.lane._asset_cache, "an empty answer is never kept")


class TheVerdictStepNeverFailsTheRecordPass(LaneCase):
    """Release 1019b's third review (House, minor): the record pass's verdict step caught only LaneDeadline, so an Alpaca
    outage in the eligibility it reads (or an empty asset list) failed the whole record pass, and FAIL_BACKOFF then cut
    EDGAR's and the news' polling from every 2 minutes to every 10. The step now catches any failure (a warning), the
    pass ends ok, and the decision's verdicts wait out VERDICT_BACKOFF by themselves."""

    def run_morning(self, *, assets_empty: bool):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-20 06:30:00")
        real = self.gw.get_json

        def get_json(path, params=None):
            if path.endswith("/v2/assets") and assets_empty:
                return []
            if path.endswith("/v2/stocks/bars") and not assets_empty:
                from league.events.gw import GatewayError
                raise GatewayError(500, "bars down")
            return real(path, params)
        self.gw.get_json = get_json
        with self.store() as st:
            for d in ("2026-10-15", "2026-10-16", "2026-10-19"):
                st.set_meta(f"evl:backfill:{d}", "done")
        self.at(et("2026-10-20", "08:00"))
        while self.clock_dt() < et("2026-10-20", "08:30"):
            self.turn()
            self.clock.advance(60)
            self.mono.advance(60)
        return [(r["started_at"][11:16], r["status"], json.loads(r["summary"] or "{}")) for r in self.receipts("record")]

    def test_bars_down(self):
        recs = self.run_morning(assets_empty=False)
        self.assertGreaterEqual(len(recs), 14, "a record pass every 2 minutes")
        self.assertEqual({status for _, status, _ in recs}, {"ok"})
        steps = [v for _, _, summary in recs for v in summary.get("verdicts") or []]
        self.assertTrue(any("GatewayError" in str(v.get("error")) for v in steps), steps[:3])
        self.assertTrue(any("verdict step" in text for level, text in self.house.alerts if level == "warning"))

    def test_assets_empty(self):
        recs = self.run_morning(assets_empty=True)
        self.assertGreaterEqual(len(recs), 14, "a record pass every 2 minutes")
        self.assertEqual({status for _, status, _ in recs}, {"ok"})


if __name__ == "__main__":
    unittest.main()
