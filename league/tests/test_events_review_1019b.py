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

from league.equity import schedule as ES
from league.events import bands as BA
from league.events import book as EB
from league.events import calendar as C
from league.events import house as H
from league.events import screen as SC
from league.events import store as S
from league.tests import test_events_book as TB
from league.tests.test_events_book import CIK, DAY, PRIOR, EventTest, V2, earnings, iso
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

    def test_a_failed_batch_is_not_read_again_name_by_name(self):
        h = self.harness()
        self.articles(h)
        calls = self.minute_market(h, fail=True)
        h.lane.decided(DAY, "open")
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)
        self.assertEqual(len(calls), 1, "one batched attempt, no read an article or a name after it")
        self.assertEqual([r for r in h.event_intents("buy") if r["program"] == "EVL-NEWS-REACT-ON"], [])

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
        acc = "0000000001-26-000402"
        self.sec.add(acc, "0000000001", "2026-10-20 08:10:00")
        real = self.sec.__call__
        asked = []

        def broken(url):
            if url.endswith(f"{acc}-index.htm"):
                asked.append(url)
                from league.events.gw import GatewayError
                raise GatewayError(503, "SEC")
            return real(url)
        self.lane._sec_base = broken
        with self.store() as st:
            for d in ("2026-10-15", "2026-10-16", "2026-10-19"):
                st.set_meta(f"evl:backfill:{d}", "done")
        self.at(et("2026-10-20", "08:12"))
        self.turn()
        for _ in range(H.FETCH_TRIES + 3):
            self.clock.advance(121)
            self.turn()
        self.assertEqual(len(asked), H.FETCH_TRIES, "tried FETCH_TRIES passes in all, then left to the backfill")


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


if __name__ == "__main__":
    unittest.main()
