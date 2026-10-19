"""Settling the event lane's intents (league.events.score) against PREREG-EVL-1 section 5, on a synthetic tape."""

import datetime as dt
import json
import tempfile
import unittest

from league.events import calendar as C
from league.events import score as SCO
from league.events import store as S
from league.events.gw import GatewayError

UTC = dt.timezone.utc
HOLIDAYS = {dt.date(2026, 11, 26)}


def weekdays(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in HOLIDAYS:
            yield d
        d += dt.timedelta(days=1)


class FakeAlpaca:
    """Alpaca through the gateway: the calendar, SIP trades per symbol (paged), SIP daily bars (raw and adjusted) and
    the account. Prices are made up."""

    def __init__(self):
        self.trades = {}  # symbol -> [trade]
        self.bars = {}    # (symbol, day, adj) -> {o, c}
        self.equity = "20000.0"
        self.calls = []
        self.broken = False

    def get_json(self, path, params=None):
        params = dict(params or {})
        self.calls.append((path, params))
        if path.endswith("/v2/calendar"):
            start, end = dt.date.fromisoformat(params["start"]), dt.date.fromisoformat(params["end"])
            return [{"date": d.isoformat(), "open": "09:30", "close": "16:00"} for d in weekdays(start, end)]
        if path.endswith("/trades"):
            if self.broken:
                raise GatewayError(503, "upstream down")
            sym = path.split("/stocks/")[1].split("/")[0]
            start, end = S.parse_iso(params["start"]), S.parse_iso(params["end"])
            rows = sorted((t for t in self.trades.get(sym, []) if start <= S.parse_iso(t["t"]) < end),
                          key=lambda t: t["t"])
            off, lim = int(params.get("page_token") or 0), int(params["limit"])
            more = off + lim < len(rows)
            return {"symbol": sym, "trades": rows[off:off + lim], "next_page_token": str(off + lim) if more else None}
        if path.endswith("/v2/stocks/bars"):
            start, end = dt.date.fromisoformat(params["start"]), S.parse_iso(params["end"])
            out = {}
            for sym in params["symbols"].split(","):
                got = []
                for (s, day, adj), bar in sorted(self.bars.items()):
                    t = dt.datetime.combine(day, dt.time(4, 0), tzinfo=UTC)
                    if s == sym and adj == params["adjustment"] and start <= day and t < end:
                        got.append({"t": S.iso(t), "o": bar["o"], "h": bar["o"], "l": bar["c"], "c": bar["c"], "v": 1e6})
                out[sym] = got
            return {"bars": out, "next_page_token": None}
        if path.endswith("/v2/account"):
            return {"equity": self.equity}
        raise AssertionError(path)

    def trade_calls(self, sym):
        return [p for path, p in self.calls if path.endswith(f"/stocks/{sym}/trades")]


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        self.gw = FakeAlpaca()
        C.refresh(self.st, self.gw, dt.date(2026, 10, 1), dt.date(2026, 12, 31))
        self.d0 = C.session(self.st, dt.date(2026, 10, 20))  # Tuesday; the previous session is Monday Oct 19
        self.n = 0

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    # -- the synthetic tape ------------------------------------------------------------------------------------------
    def at(self, moment, sym, x, px, conds):
        self.gw.trades.setdefault(sym, []).append({"t": moment.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                                                   "x": x, "p": px, "s": 100, "c": conds})

    def tape(self, session, sym, x, open_px=None, close_px=None, *, official_only=False, bar=None, adj=None):
        """One session of a stock's tape: another venue trades first and prints its own opening cross, then the listing
        exchange's cross (`O`) with its official record (`Q`); at the close its `6` with `M`; trades in between and
        after. `official_only` leaves out the O and 6 prints (the Q and M records stand)."""
        o, c = session.open_at, session.close_at
        ms = dt.timedelta(milliseconds=1)
        if open_px is not None:
            other = "Z" if x != "Z" else "N"
            self.at(o + 100 * ms, sym, "D", open_px * 1.01, [" ", "I"])
            self.at(o + 200 * ms, sym, other, open_px * 0.97, [" ", "O"])  # not the listing exchange: never counts
            if not official_only:
                self.at(o + 500 * ms, sym, x, open_px, [" ", "O"])
            self.at(o + 501 * ms, sym, x, open_px * (1.002 if official_only else 1.0), ["Q"])
            self.at(o + dt.timedelta(hours=3), sym, "D", open_px, [" "])
        if close_px is not None:
            self.at(c - dt.timedelta(seconds=3), sym, "D", close_px * 0.99, [" "])
            if not official_only:
                self.at(c + 200 * ms, sym, x, close_px, [" ", "6"])
            self.at(c + 201 * ms, sym, x, close_px * (0.998 if official_only else 1.0), ["M"])
            self.at(c + dt.timedelta(minutes=1), sym, "D", close_px * 1.02, [" ", "T"])
        if bar is not None:
            raw = {"o": bar[0], "c": bar[1]}
            self.gw.bars[(sym, session.day, "raw")] = raw
            self.gw.bars[(sym, session.day, "all")] = adj or raw

    def spy(self, session, open_px=600.0, close_px=603.0):
        self.tape(session, "SPY", "P", open_px, close_px, bar=(open_px, close_px))

    def intent(self, sym="XYZ", *, entry=None, exit_=None, entry_at="open", exit_at="close", exchange="NYSE",
               prev_close=49.0, adv=50_000_000.0, bench="SPY", universe=True, program="EVL-ERN-READ-O1"):
        self.n += 1
        entry, exit_ = entry or self.d0.day, exit_ or self.d0.day
        with self.st.tx() as db:
            if universe:
                db.execute("INSERT OR REPLACE INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench) "
                           "VALUES(?, ?, ?, 'Co', ?, ?, ?, ?)",
                           (entry.isoformat(), sym, f"{self.n:010d}", exchange, prev_close, adv, bench))
            db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                       "exit_day, exit_at, mode, status) VALUES(?, 1, ?, ?, ?, '2026-10-20T13:15:00Z', ?, ?, ?, ?, "
                       "'shadow', 'planned')",
                       (program, f"8k:{self.n}", sym, f"{self.n:010d}", entry.isoformat(), entry_at, exit_.isoformat(),
                        exit_at))
        return f"8k:{self.n}"

    def outcome(self, event):
        row = self.st.db.execute("SELECT * FROM outcomes WHERE event=?", (event,)).fetchone()
        return None if row is None else dict(row)

    def status(self, event):
        return self.st.db.execute("SELECT status, why FROM intents WHERE event=?", (event,)).fetchone()

    def after(self, session, minutes=30):
        return session.close_at + dt.timedelta(minutes=minutes)

    def equity(self, day, value):
        self.st.set_meta(f"equity:{day.isoformat()}", repr(value))

    # -- tests -------------------------------------------------------------------------------------------------------
    def test_open_to_close_on_the_listing_exchanges_crosses_with_the_cost_allowance(self):
        self.equity(dt.date(2026, 10, 19), 20000.0)
        self.tape(self.d0, "XYZ", "N", 50.0, 51.0, bar=(50.1, 51.05))
        self.spy(self.d0)
        ev = self.intent()
        out = SCO.settle(self.st, self.gw, now=self.after(self.d0))
        self.assertEqual((out["due"], out["settled"]), (1, 1), out)
        o = self.outcome(ev)
        self.assertEqual((o["entry_px"], o["exit_px"], o["bench_entry"], o["bench_exit"]), (50.0, 51.0, 600.0, 603.0))
        self.assertAlmostEqual(o["cost_entry_bp"], 5.6, places=12)  # 0.5 + 5 + $0.01 / $1,000
        self.assertAlmostEqual(o["cost_exit_bp"], 5.7, places=12)   # + $0.01 / $1,000 more on the sale
        r = 51.0 * (1 - o["cost_exit_bp"] / 1e4) / (50.0 * (1 + o["cost_entry_bp"] / 1e4)) - 1
        self.assertEqual(o["r"], r)
        self.assertEqual(o["b"], 603.0 / 600.0 - 1)
        self.assertEqual(o["a"], o["r"] - o["b"])
        self.assertEqual((o["tradable"], o["status"], o["bench"]), (1, "settled", "SPY"))
        self.assertEqual(self.status(ev)["status"], "exited")
        marks = {r["label"]: dict(r) for r in self.st.db.execute("SELECT * FROM marks WHERE symbol='XYZ'")}
        self.assertEqual((marks["open"]["px"], marks["open"]["source"]), (50.0, "sip:N:O"))
        self.assertEqual((marks["close"]["px"], marks["close"]["source"]), (51.0, "sip:N:6"))
        bar = self.st.db.execute("SELECT o, c FROM bars WHERE symbol='XYZ' AND adj='raw' AND day='2026-10-20'").fetchone()
        self.assertEqual((bar["o"], bar["c"]), (50.1, 51.05))  # the bar beside the prints: the gap is on record

    def test_tradable_is_one_and_a_quarter_previous_closes_within_a_tenth_of_equity(self):
        self.equity(dt.date(2026, 10, 16), 4500.0)  # the latest record before the previous session stands in
        self.spy(self.d0)
        for sym, prev in (("AAA", 380.0), ("BBB", 350.0)):
            self.tape(self.d0, sym, "Q", 300.0, 301.0, bar=(300.0, 301.0))
            self.intent(sym, exchange="NASDAQ", prev_close=prev)
        SCO.settle(self.st, self.gw, now=self.after(self.d0))
        got = dict(self.st.db.execute("SELECT i.symbol, o.tradable FROM outcomes o JOIN intents i USING(event)").fetchall())
        self.assertEqual(got, {"AAA": 0, "BBB": 1})  # 1.25 x 380 = 475 > 450; 1.25 x 350 = 437.5 <= 450

    def test_no_equity_on_record_leaves_the_fees_out_and_tradability_unknown(self):
        self.tape(self.d0, "XYZ", "N", 50.0, 51.0, bar=(50.0, 51.0))
        self.tape(self.d0, "THIN", "A", 20.0, 20.5, bar=(20.0, 20.5))
        self.spy(self.d0)
        ev, thin = self.intent(), self.intent("THIN", exchange="AMEX", adv=5_000_000.0)
        SCO.settle(self.st, self.gw, now=self.after(self.d0))
        o, t = self.outcome(ev), self.outcome(thin)
        self.assertEqual((o["cost_entry_bp"], o["cost_exit_bp"], o["tradable"]), (5.5, 5.5, None))
        self.assertEqual((t["cost_entry_bp"], t["entry_px"]), (10.5, 20.0))  # ADV under $10M: 10 bp of impact

    def test_the_official_records_stand_in_when_the_listing_exchange_printed_no_cross(self):
        self.tape(self.d0, "XYZ", "N", 50.0, 51.0, official_only=True, bar=(50.0, 51.0))
        self.spy(self.d0)
        ev = self.intent()
        SCO.settle(self.st, self.gw, now=self.after(self.d0))
        o = self.outcome(ev)
        self.assertEqual((o["entry_px"], o["exit_px"]), (50.0 * 1.002, 51.0 * 0.998))
        sources = dict(self.st.db.execute("SELECT label, source FROM marks WHERE symbol='XYZ'").fetchall())
        self.assertEqual(sources, {"open": "sip:N:Q", "close": "sip:N:M"})

    def test_no_auction_print_at_entry_skips_the_event(self):
        self.at(self.d0.open_at + dt.timedelta(seconds=2), "XYZ", "D", 50.0, [" "])  # trades elsewhere, no cross
        self.spy(self.d0)
        ev = self.intent()
        out = SCO.settle(self.st, self.gw, now=self.after(self.d0))
        self.assertEqual(out["skipped"], 1)
        self.assertEqual(self.status(ev)["status"], "skipped:no-auction")
        self.assertIsNone(self.outcome(ev))

    def test_nothing_is_due_until_16_minutes_after_the_close_and_an_unreadable_tape_waits(self):
        self.tape(self.d0, "XYZ", "N", 50.0, None, bar=(50.0, 51.0))  # no closing print (yet)
        self.spy(self.d0)
        ev = self.intent()
        self.assertEqual(SCO.settle(self.st, self.gw, now=self.after(self.d0, 15))["due"], 0)
        out = SCO.settle(self.st, self.gw, now=self.after(self.d0, 17))
        self.assertEqual((out["due"], out["waiting"]), (1, 1))
        self.assertIn("tape not complete", out["waits"][0])
        self.assertEqual(self.status(ev)["status"], "planned")

    def test_a_missing_exit_print_exits_at_the_next_sessions_closing_cross(self):
        d1 = C.session(self.st, dt.date(2026, 10, 21))
        self.tape(self.d0, "XYZ", "N", 50.0, None, bar=(50.0, 50.5))
        self.tape(d1, "XYZ", "N", None, 52.0, bar=(51.0, 52.0))
        self.spy(self.d0)
        self.spy(d1, 603.0, 606.0)
        ev = self.intent()
        out = SCO.settle(self.st, self.gw, now=self.after(self.d0))
        self.assertIn("not on the tape yet", out["waits"][0])
        out = SCO.settle(self.st, self.gw, now=self.after(d1))
        self.assertEqual(out["settled"], 1, out)
        o = self.outcome(ev)
        self.assertEqual((o["exit_px"], o["bench_exit"]), (52.0, 606.0))
        self.assertEqual(json.loads(self.st.meta(f"exit:EVL-ERN-READ-O1:1:{ev}")),
                         {"day": "2026-10-21", "kind": "close", "planned": "2026-10-20"})
        self.assertEqual(tuple(self.status(ev)), ("exited", "exit close 2026-10-21"))

    def test_none_within_five_sessions_exits_at_the_next_sessions_first_trade(self):
        later = C.sessions(self.st, dt.date(2026, 10, 21), dt.date(2026, 12, 31))
        self.tape(self.d0, "XYZ", "N", 50.0, None, bar=(50.0, 50.0))
        sixth = later[5]  # the 6th session after the exit day
        self.at(sixth.open_at + dt.timedelta(hours=2), "XYZ", "D", 30.0, [" "])
        self.gw.bars[("XYZ", sixth.day, "raw")] = self.gw.bars[("XYZ", sixth.day, "all")] = {"o": 30.0, "c": 31.0}
        self.spy(self.d0)
        self.spy(sixth, 590.0, 591.0)
        ev = self.intent()
        out = SCO.settle(self.st, self.gw, now=self.after(sixth))
        self.assertEqual(out["settled"], 1, out)
        o = self.outcome(ev)
        self.assertEqual((o["exit_px"], o["bench_exit"]), (30.0, 590.0))  # the benchmark at that session's opening cross
        self.assertEqual(json.loads(self.st.meta(f"exit:EVL-ERN-READ-O1:1:{ev}"))["kind"], "first")

    def test_no_trade_for_twenty_sessions_exits_at_zero(self):
        later = C.sessions(self.st, dt.date(2026, 10, 21), dt.date(2026, 12, 31))
        self.tape(self.d0, "XYZ", "N", 50.0, None, bar=(50.0, 50.0))
        self.spy(self.d0)
        self.spy(later[19], 580.0, 585.0)
        ev = self.intent()
        out = SCO.settle(self.st, self.gw, now=self.after(later[19]))
        self.assertEqual(out["settled"], 1, out)
        o = self.outcome(ev)
        self.assertEqual((o["exit_px"], o["r"], o["bench_exit"]), (0.0, -1.0, 585.0))
        self.assertEqual(json.loads(self.st.meta(f"exit:EVL-ERN-READ-O1:1:{ev}"))["day"], later[19].day.isoformat())

    def test_a_split_inside_the_hold_applies_through_the_adjusted_to_raw_close(self):
        d1 = C.session(self.st, dt.date(2026, 10, 21))
        # C1: the close of day 0 to the close of the next session; a 2-for-1 split goes effective on day 1.
        self.tape(self.d0, "XYZ", "N", None, 100.0, bar=(99.0, 100.0), adj={"o": 49.5, "c": 50.0})
        self.tape(d1, "XYZ", "N", None, 51.0, bar=(50.5, 51.0))
        self.spy(self.d0)
        self.spy(d1, 603.0, 606.0)
        ev = self.intent(entry=self.d0.day, exit_=d1.day, entry_at="close", program="EVL-ERN-REACT-C1")
        SCO.settle(self.st, self.gw, now=self.after(d1))
        o = self.outcome(ev)
        self.assertEqual((o["entry_px"], o["exit_px"], o["bench_entry"], o["bench_exit"]), (50.0, 51.0, 603.0, 606.0))
        self.assertAlmostEqual(o["r"], 51.0 * (1 - 5.5e-4) / (50.0 * (1 + 5.5e-4)) - 1, places=15)

    def test_settling_is_idempotent_and_each_print_is_read_from_the_tape_once(self):
        self.spy(self.d0)
        events = []
        for sym in ("AAA", "BBB", "CCC"):
            self.tape(self.d0, sym, "Q", 10.0, 10.5, bar=(10.0, 10.5))
            events.append(self.intent(sym, exchange="NASDAQ"))
        out = SCO.settle(self.st, self.gw, now=self.after(self.d0))
        self.assertEqual(out["settled"], 3)
        self.assertEqual(len(self.gw.trade_calls("SPY")), 2)  # its open and its close, once for all three
        before = [self.outcome(e) for e in events]
        calls = len(self.gw.calls)
        again = SCO.settle(self.st, self.gw, now=self.after(self.d0, 120))
        self.assertEqual((again["due"], len(self.gw.calls)), (0, calls))
        self.assertEqual([self.outcome(e) for e in events], before)

    def test_a_benchmark_print_missing_on_a_readable_tape_falls_back_to_its_bar_a_session_later(self):
        d1 = C.session(self.st, dt.date(2026, 10, 21))
        self.tape(self.d0, "XYZ", "N", 50.0, 51.0, bar=(50.0, 51.0))
        self.gw.bars[("SPY", self.d0.day, "raw")] = self.gw.bars[("SPY", self.d0.day, "all")] = {"o": 600.5, "c": 603.0}
        self.at(self.d0.close_at + dt.timedelta(milliseconds=200), "SPY", "P", 603.0, [" ", "6"])  # a close, no open
        ev = self.intent()
        out = SCO.settle(self.st, self.gw, now=self.after(self.d0))
        self.assertIn("a session's wait", out["waits"][0])
        SCO.settle(self.st, self.gw, now=self.after(d1))
        self.assertEqual(self.outcome(ev)["bench_entry"], 600.5)
        src = self.st.db.execute("SELECT source FROM marks WHERE symbol='SPY' AND label='open'").fetchone()[0]
        self.assertEqual(src, "bar-fallback")

    def test_a_failed_fetch_is_reported_and_the_intent_waits(self):
        self.gw.broken = True
        ev = self.intent()
        out = SCO.settle(self.st, self.gw, now=self.after(self.d0))
        self.assertEqual(out["waiting"], 1)
        self.assertIn("GatewayError", out["errors"][0])
        self.assertEqual(self.status(ev)["status"], "planned")

    def test_an_intent_without_its_universe_row_is_skipped(self):
        ev = self.intent(universe=False)
        SCO.settle(self.st, self.gw, now=self.after(self.d0))
        self.assertEqual(self.status(ev)["status"], "skipped:no-universe-row")

    def test_record_equity_keeps_the_equity_at_each_sessions_close(self):
        self.gw.equity = "21000.5"
        self.assertEqual(SCO.record_equity(self.st, self.gw, now=self.after(self.d0, -60)),
                         {"skipped": "no closed session on 2026-10-20"})  # before the close
        got = SCO.record_equity(self.st, self.gw, now=self.after(self.d0, 270))  # 20:30 ET Tuesday
        self.assertEqual((got, self.st.meta("equity:2026-10-20")), ({"day": "2026-10-20", "equity": 21000.5}, "21000.5"))
        self.assertEqual(self.st.meta("equity:2026-10-20:at"), "2026-10-21T00:30:00Z")
        self.gw.equity = "1.0"
        self.assertEqual(SCO.record_equity(self.st, self.gw, now=self.after(self.d0, 300)), {"kept": "21000.5"})
        self.assertEqual(SCO.record_equity(self.st, self.gw, now=self.after(self.d0, 300), overwrite=True)["equity"], 1.0)
        saturday = dt.datetime(2026, 10, 24, 15, 0, tzinfo=UTC)
        self.assertIn("skipped", SCO.record_equity(self.st, self.gw, now=saturday))
        # The ":at" stamp is no equity record; a day without a record reads the latest earlier one.
        self.assertEqual(SCO.equity_on(self.st, dt.date(2026, 10, 22)), 1.0)
        self.assertIsNone(SCO.equity_on(self.st, dt.date(2026, 10, 19)))

    def test_the_cli_equity_command_is_this_record(self):
        import inspect
        from league.events import __main__ as M
        self.assertIn("SC.record_equity(st, gw", inspect.getsource(M.main))   # one recorder, the score module's
        self.gw.equity = "15000.25"
        SCO.record_equity(self.st, self.gw, now=self.after(self.d0, 270))
        self.assertEqual(SCO.equity_on(self.st, self.d0.day), 15000.25)
        self.assertEqual(SCO.record_equity(self.st, self.gw, now=self.after(self.d0, 280)), {"kept": "15000.25"})

if __name__ == "__main__":
    unittest.main()
