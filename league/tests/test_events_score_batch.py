"""THE BATCHED SCORE (release 1019i; PREREG-EVL-8's harness plan H1, league/events/score.py's docstring).

A GOLDEN TAPE: one synthetic market (every symbol, print and bar invented) settled twice, by release 1019h's
per-intent path and by the batched pass, into two stores built the same way: the outcome rows, the intents' moves, the
late exits' meta and the prints kept are byte-identical, with a split inside a hold (Alpaca adjusts every bar to today's
basis), a missing daily bar (its intent falls back to its own fetch), a ladder exit, a skip for no auction, a skip at the
limit and a prefetch chunk that fails; the batched pass asks a fraction of the bar requests. Then the order (seating
versions and their controls first), 200 symbols a request, the switch (`events.score_batch`), the parity night's
equality flags (never a value) and the House's pass with the switch on and off.
"""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.events import calendar as C
from league.events import house as H
from league.events import score as SC
from league.events import store as S
from league.events.gw import GatewayError

UTC = dt.timezone.utc
NY = C.NY


def weekdays(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def wall(day, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=NY).astimezone(UTC)


D0, D1, D2 = dt.date(2026, 10, 20), dt.date(2026, 10, 21), dt.date(2026, 10, 22)
PREV = dt.date(2026, 10, 19)


class Tape:
    """Alpaca through the gateway on an invented market: the calendar, SIP trades per symbol (paged) and SIP daily bars
    raw and `adjustment=all`, the adjusted ones on TODAY'S BASIS whatever the request's window (a split's factor applies
    to every bar before it, as the vendor's do). `missing` (symbol, day) has no bar at all; `fail` makes the first bar
    request naming that symbol fail (a 503)."""

    def __init__(self):
        self.trades = {}
        self.raw = {}          # (symbol, day) -> (o, c)
        self.splits = {}       # symbol -> (effective day, ratio): bars before the day divided by the ratio
        self.missing = set()
        self.fail = set()
        self.calls = []

    def get_json(self, path, params=None):
        params = dict(params or {})
        self.calls.append((path, params))
        if path.endswith("/v2/calendar"):
            start, end = dt.date.fromisoformat(params["start"]), dt.date.fromisoformat(params["end"])
            return [{"date": d.isoformat(), "open": "09:30", "close": "16:00"} for d in weekdays(start, end)]
        if path.endswith("/trades"):
            sym = path.split("/stocks/")[1].split("/")[0]
            start, end = S.parse_iso(params["start"]), S.parse_iso(params["end"])
            rows = sorted((t for t in self.trades.get(sym, []) if start <= S.parse_iso(t["t"]) < end), key=lambda t: t["t"])
            off, lim = int(params.get("page_token") or 0), int(params["limit"])
            more = off + lim < len(rows)
            return {"symbol": sym, "trades": rows[off:off + lim], "next_page_token": str(off + lim) if more else None}
        if path.endswith("/v2/stocks/bars"):
            names = params["symbols"].split(",")
            for sym in names:
                if sym in self.fail:
                    self.fail.discard(sym)
                    raise GatewayError(503, "upstream busy")
            start, end = dt.date.fromisoformat(params["start"]), S.parse_iso(params["end"])
            out = {}
            for sym in names:
                got = []
                for (s, day), (o, c) in sorted(self.raw.items()):
                    t = dt.datetime.combine(day, dt.time(4, 0), tzinfo=UTC)
                    if s != sym or day < start or t >= end or (s, day) in self.missing:
                        continue
                    f = 1.0
                    if params["adjustment"] == "all" and sym in self.splits and day < self.splits[sym][0]:
                        f = 1.0 / self.splits[sym][1]
                    got.append({"t": S.iso(t), "o": o * f, "h": o * f, "l": c * f, "c": c * f, "v": 1e6})
                out[sym] = got
            return {"bars": out, "next_page_token": None}
        raise AssertionError(path)

    def bar_requests(self):
        return [p for path, p in self.calls if path.endswith("/v2/stocks/bars")]


class GoldenCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.n = 0

    # -- the invented market -----------------------------------------------------------------------------------------
    def trade(self, tape, moment, sym, x, px, conds):
        tape.trades.setdefault(sym, []).append({"t": moment.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                                                "x": x, "p": px, "s": 100, "c": conds})

    def session(self, tape, st, day, sym, x, open_px=None, close_px=None, bar=True):
        s = C.session(st, day)
        ms = dt.timedelta(milliseconds=1)
        if open_px is not None:
            self.trade(tape, s.open_at + 100 * ms, sym, "D", open_px * 1.01, [" ", "I"])
            self.trade(tape, s.open_at + 500 * ms, sym, x, open_px, [" ", "O"])
            self.trade(tape, s.open_at + 501 * ms, sym, x, open_px, ["Q"])
        if close_px is not None:
            self.trade(tape, s.close_at - dt.timedelta(seconds=3), sym, "D", close_px * 0.99, [" "])
            self.trade(tape, s.close_at + 200 * ms, sym, x, close_px, [" ", "6"])
            self.trade(tape, s.close_at + 201 * ms, sym, x, close_px, ["M"])
        if bar:
            o = open_px if open_px is not None else (close_px or 10.0)
            c = close_px if close_px is not None else o
            tape.raw[(sym, day)] = (o * 1.001, c * 0.999)

    def market(self, tape, st):
        for day in (PREV, D0, D1, D2):
            for bench, base in (("SPY", 600.0), ("IWM", 220.0)):
                k = {PREV: 0, D0: 1, D1: 2, D2: 3}[day]
                self.session(tape, st, day, bench, "P", base + k, base + k + 1.5)
        self.session(tape, st, D0, "AAA", "N", 50.0, 51.0)                    # open -> close, seating version
        self.session(tape, st, D0, "BBB", "Q", 30.0, 29.4)                    # the control
        self.session(tape, st, D0, "CCC", "N", 12.0, 12.2)                    # close -> next open
        self.session(tape, st, D1, "CCC", "N", 12.5, 12.4)
        self.session(tape, st, D0, "LAD", "Q", 40.0, None)                    # no closing print on its exit day
        self.session(tape, st, D1, "LAD", "Q", 40.5, 41.0)                    # ... the next close sells it
        for day, (o, c) in ((D0, (100.0, 101.0)), (D1, (50.6, 50.9)), (D2, (51.0, 51.5))):
            self.session(tape, st, day, "SPL", "N", o, c)                     # a 2:1 split effective D1, held D0 -> D2
        tape.splits["SPL"] = (D1, 2.0)
        self.session(tape, st, D0, "MIS", "N", 20.0, 20.5)                    # its exit day's bar never comes
        tape.missing.add(("MIS", D0))
        self.session(tape, st, D0, "NOA", "N", None, 8.0)                     # no opening print at all: skipped
        self.session(tape, st, D0, "LIM", "N", 70.0, 71.0)                    # above 1.25 x its previous close: limit
        self.session(tape, st, D0, "FLK", "Q", 15.0, 15.3)                    # its prefetch chunk fails once
        for day in (PREV,):
            for sym, px in (("AAA", 49.0), ("BBB", 30.1), ("CCC", 12.1), ("LAD", 39.5), ("SPL", 99.0), ("MIS", 19.8),
                            ("NOA", 8.1), ("LIM", 50.0), ("FLK", 15.1)):
                tape.raw[(sym, day)] = (px, px)

    def intent(self, st, sym, program, version, *, entry=D0, exit_=D0, entry_at="open", exit_at="close",
               exchange="NYSE", prev_close=None, adv=60_000_000.0):
        self.n += 1
        with st.tx() as db:
            db.execute("INSERT OR REPLACE INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench) "
                       "VALUES(?, ?, ?, 'Co', ?, ?, ?, ?)",
                       (entry.isoformat(), sym, f"{self.n:010d}", exchange, prev_close, adv,
                        "IWM" if adv < 50_000_000 else "SPY"))
            db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                       "exit_day, exit_at, mode, status) VALUES(?, ?, ?, ?, ?, '2026-10-20T13:15:00Z', ?, ?, ?, ?, "
                       "'shadow', 'planned')",
                       (program, version, f"8k:{sym.lower()}-{self.n}", sym, f"{self.n:010d}", entry.isoformat(),
                        entry_at, exit_.isoformat(), exit_at))

    def build(self, name):
        """A store and its tape, built the same way every time."""
        self.n = 0
        st = S.Store(Path(self.tmp.name) / name)
        self.addCleanup(st.close)
        tape = Tape()
        C.refresh(st, tape, dt.date(2026, 10, 1), dt.date(2026, 12, 31))
        st.set_meta("equity:2026-10-19", repr(20000.0))
        self.market(tape, st)
        self.intent(st, "AAA", "EVL-ERN-READ-O1", 2, prev_close=49.0)
        self.intent(st, "BBB", "EVL-CTRL-ERN-ALL-O1", 1, exchange="NASDAQ", prev_close=30.1, adv=20_000_000.0)
        self.intent(st, "CCC", "EVL-NEWS-READ-ON", 2, entry_at="close", exit_=D1, exit_at="open", prev_close=12.1)
        self.intent(st, "LAD", "EVL-ERN-READ-O1", 1, exchange="NASDAQ", prev_close=39.5)
        self.intent(st, "SPL", "EVL-ERN-READ-O3", 1, exit_=D2, prev_close=99.0)
        self.intent(st, "MIS", "EVL-8K-READ-O1", 2, prev_close=19.8, adv=8_000_000.0)
        self.intent(st, "NOA", "EVL-NEWS-READ-O1", 2, prev_close=8.1)
        self.intent(st, "LIM", "EVL-8K-READ-O1", 2, prev_close=50.0)
        self.intent(st, "FLK", "EVL-CTRL-8K-ALL-O1", 1, exchange="NASDAQ", prev_close=15.1)
        tape.calls.clear()
        return st, tape

    @staticmethod
    def rows(st, sql):
        return [tuple(repr(v) for v in tuple(r)) for r in st.db.execute(sql)]

    def record(self, st):
        return {"outcomes": self.rows(st, "SELECT * FROM outcomes ORDER BY program, version, event"),
                "intents": self.rows(st, "SELECT * FROM intents ORDER BY program, version, event"),
                "exits": self.rows(st, "SELECT * FROM meta WHERE key LIKE 'exit:%' ORDER BY key"),
                "marks": self.rows(st, "SELECT * FROM marks ORDER BY symbol, day, label")}

    NOW = wall(D2, "16:30")


class TheGoldenTape(GoldenCase):
    def test_byte_identical_outcomes_with_and_without_the_prefetch(self):
        old, old_tape = self.build("old")
        new, new_tape = self.build("new")
        new_tape.fail.add("FLK")
        a = SC.settle(old, old_tape, now=self.NOW, batch=False)
        b = SC.settle(new, new_tape, now=self.NOW, batch=True, parity=False)
        self.assertEqual((a["due"], a["settled"], a["skipped"], a["waiting"]), (9, 7, 2, 0), a)
        self.assertEqual((b["due"], b["settled"], b["skipped"], b["waiting"]), (9, 7, 2, 0), b)
        mine, theirs = self.record(new), self.record(old)
        for part in ("outcomes", "intents", "exits", "marks"):
            self.assertEqual(mine[part], theirs[part], part)
        self.assertEqual(len(mine["outcomes"]), 7)
        self.assertEqual(len(mine["exits"]), 1, "the ladder's later exit is on record")
        # every bar the per-intent path stored is stored the same by the batched pass
        for row in old.db.execute("SELECT * FROM bars"):
            got = new.db.execute("SELECT * FROM bars WHERE symbol=? AND day=? AND adj=?",
                                 (row["symbol"], row["day"], row["adj"])).fetchone()
            self.assertIsNotNone(got, tuple(row))
            self.assertEqual(tuple(got), tuple(row))
        # the split inside the hold applies through each day's ratio of adjusted to raw close, both ways alike
        spl = new.db.execute("SELECT entry_px, exit_px FROM outcomes WHERE event LIKE '8k:spl-%'").fetchone()
        self.assertAlmostEqual(spl["entry_px"], 50.0, places=9)
        self.assertAlmostEqual(spl["exit_px"], 51.5, places=9)
        # the missing bar: its exit day's ratio reads 1.0 on both paths
        mis = new.db.execute("SELECT exit_px FROM outcomes WHERE event LIKE '8k:mis-%'").fetchone()
        self.assertEqual(mis["exit_px"], 20.5)
        # far fewer bar requests: the per-intent path asks two for each intent it settles
        self.assertEqual(len(old_tape.bar_requests()), 2 * 7)
        self.assertEqual(b["prefetch"]["requests"], 2, b["prefetch"])   # the raw chunk (it failed) and the adjusted one
        self.assertFalse(b["prefetch"]["done"])
        self.assertEqual(len(b["prefetch"]["errors"]), 1)
        # THE FALLBACK: with no raw bar prefetched every settled intent fetches its own two, exactly as before
        self.assertEqual(b["requests"]["bars"], 2 + 2 * 7)

    def test_byte_identical_when_every_chunk_is_read(self):
        old, old_tape = self.build("old")
        new, new_tape = self.build("new")
        SC.settle(old, old_tape, now=self.NOW, batch=False)
        b = SC.settle(new, new_tape, now=self.NOW, batch=True, parity=False)
        self.assertEqual(self.record(new), self.record(old))
        self.assertTrue(b["prefetch"]["done"])
        # two prefetch requests (raw, adjusted) and the missing bar's own fallback pair: 4 against 14
        self.assertEqual(len(new_tape.bar_requests()), 2 + 2)
        self.assertEqual(b["requests"]["bars"], 4)
        self.assertEqual(b["prefetch"]["symbols"], 9 + 2, "every intent with a universe row, and both benchmarks")

    def test_prints_are_read_once_per_symbol_day_and_label(self):
        new, tape = self.build("new")
        SC.settle(new, tape, now=self.NOW, batch=True, parity=False)
        reads = [(path, params["start"], params["end"], params.get("page_token")) for path, params in tape.calls
                 if path.endswith("/trades")]
        self.assertTrue(any("/SPY/" in r[0] for r in reads))
        self.assertEqual(len(reads), len(set(reads)), "no window of the tape is read twice")
        before = len(tape.calls)
        again = SC.settle(new, tape, now=self.NOW + dt.timedelta(hours=1), batch=True, parity=False)
        self.assertEqual(again["due"], 0)
        self.assertEqual(len(tape.calls), before, "nothing due: no request at all")

    def test_a_rerun_changes_nothing(self):
        new, tape = self.build("new")
        SC.settle(new, tape, now=self.NOW, batch=True, parity=False)
        first = self.record(new)
        new.db.execute("UPDATE intents SET status='planned' WHERE event LIKE '8k:aaa-%'")   # forced back: settled again
        SC.settle(new, tape, now=self.NOW + dt.timedelta(minutes=5), batch=True, parity=False)
        self.assertEqual(self.record(new)["outcomes"], first["outcomes"], "INSERT OR IGNORE: the first outcome stands")


class TheOrderAndTheRequests(GoldenCase):
    def test_seating_versions_and_their_controls_settle_first(self):
        rows = [{"program": "EVL-ERN-READ-O1", "version": 1, "event": "a"},
                {"program": "EVL-ERN-READ-O3", "version": 1, "event": "b"},
                {"program": "EVL-CTRL-ERN-ALL-O1", "version": 1, "event": "c"},
                {"program": "EVL-ERN-READ-O1", "version": 2, "event": "d"},
                {"program": "EVL-CTRL-8K-ALL-O1", "version": 1, "event": "e"},
                {"program": "EVL-8K-REACT-ON", "version": 1, "event": "f"}]
        self.assertEqual([r["event"] for r in SC.order_due(rows)], ["c", "d", "e", "f", "a", "b"])

    def test_two_hundred_symbols_a_request_and_both_benchmarks(self):
        st = S.Store(Path(self.tmp.name) / "wide")
        self.addCleanup(st.close)
        tape = Tape()
        C.refresh(st, tape, dt.date(2026, 10, 1), dt.date(2026, 12, 31))
        intents = []
        with st.tx() as db:
            for i in range(450):
                sym = f"S{i:03d}"
                db.execute("INSERT INTO universe(day, symbol, cik, exchange, prev_close, adv20, bench) VALUES(?, ?, ?, "
                           "'NYSE', 10.0, 2e7, 'IWM')", (D0.isoformat(), sym, f"{i:010d}"))
                intents.append({"program": "EVL-ERN-READ-O1", "version": 2, "event": f"e{i}", "symbol": sym,
                                "entry_day": D0.isoformat()})
        tape.calls.clear()
        pre = SC.prefetch(st, tape, intents, now=self.NOW)
        asked = tape.bar_requests()
        self.assertEqual(pre.symbols, 452)
        self.assertEqual(len(asked), 2 * 3)                 # 452 symbols: 3 requests of at most 200, raw and adjusted
        self.assertTrue(all(len(p["symbols"].split(",")) <= 200 for p in asked))
        named = {s for p in asked for s in p["symbols"].split(",")}
        self.assertTrue({"SPY", "IWM"} <= named)
        self.assertEqual({p["adjustment"] for p in asked}, {"raw", "all"})
        self.assertEqual({p["start"] for p in asked}, {D0.isoformat()})
        self.assertTrue(all(p["end"] <= S.iso(self.NOW - dt.timedelta(minutes=16)) for p in asked),
                        "sip_end's 16-minute clamp")

    def test_a_bound_stops_the_prefetch_between_chunks(self):
        st, tape = self.build("bound")
        calls = iter([False, True])
        pre = SC.prefetch(st, tape, SC.due(st, self.NOW), now=self.NOW, late=lambda: next(calls, True))
        self.assertFalse(pre.done)
        self.assertEqual(pre.requests, 1)

    def test_the_switch(self):
        self.assertTrue(SC.batch_on({}))
        self.assertTrue(SC.batch_on(None))
        self.assertTrue(SC.batch_on({"score_batch": True}))
        self.assertTrue(SC.batch_on({"score_batch": "off"}), "only false turns it off")
        self.assertFalse(SC.batch_on({"score_batch": False}))

    def test_off_is_release_1019h_path_two_fetches_an_intent_and_due_order(self):
        st, tape = self.build("off")
        expected = [i["event"] for i in SC.due(st, self.NOW)]
        batched = [i["event"] for i in SC.order_due(SC.due(st, self.NOW))]
        seen = []
        real = SC.settle_one

        def spy(store, gw, intent, *, now, prefetched=False):
            seen.append((intent["event"], prefetched))
            return real(store, gw, intent, now=now, prefetched=prefetched)
        with mock.patch.object(SC, "settle_one", spy):
            out = SC.settle(st, tape, now=self.NOW, batch=False)
        self.assertNotIn("prefetch", out)
        self.assertEqual([e for e, _ in seen], expected, "due's own order")
        self.assertNotEqual(expected, batched, "the golden tape's due order is not the batched one: the order is the switch's")
        self.assertTrue(all(p is False for _, p in seen))
        self.assertEqual(len(tape.bar_requests()), 2 * out["settled"])


class TheParityNight(GoldenCase):
    def test_flags_only_and_equal_on_an_honest_tape(self):
        st, tape = self.build("parity")
        with mock.patch.object(SC, "parity_sampled", lambda intent, share=SC.PARITY_SHARE: True):
            out = SC.settle(st, tape, now=self.NOW, batch=True)
        self.assertEqual(out["parity"], {"checked": 7, "equal": 7})
        cols = [r[1] for r in st.db.execute("PRAGMA table_info(score_parity)")]
        self.assertEqual(cols, ["program", "version", "event", "night", "equal", "checked_at"], "no value column")
        self.assertEqual(st.meta(SC.PARITY_FIRST), D2.isoformat())
        self.assertEqual(SC.parity_counts(st, D2), {"checked": 7, "equal": 7})

    def test_a_difference_writes_zero(self):
        st, tape = self.build("differ")
        SC.settle(st, tape, now=self.NOW, batch=True, parity=False)
        intent = dict(st.db.execute("SELECT * FROM intents WHERE event LIKE '8k:aaa-%'").fetchone())
        self.assertEqual(SC.check_parity(st, tape, intent, D2, now=self.NOW), 1)
        st.db.execute("UPDATE outcomes SET r=r+1e-12 WHERE event=?", (intent["event"],))
        self.assertEqual(SC.check_parity(st, tape, intent, D2, now=self.NOW), 0)
        row = dict(st.db.execute("SELECT * FROM score_parity WHERE event=?", (intent["event"],)).fetchone())
        self.assertEqual(row["equal"], 0)
        self.assertNotIn("r", row)

    def test_the_first_night_only_unless_switched(self):
        st, _ = self.build("nights")
        self.assertTrue(SC.parity_due(st, D0))
        SC.note_first_night(st, D0)
        SC.note_first_night(st, D1)
        self.assertEqual(st.meta(SC.PARITY_FIRST), D0.isoformat(), "kept once")
        self.assertTrue(SC.parity_due(st, D0))
        self.assertFalse(SC.parity_due(st, D1))
        self.assertTrue(SC.parity_due(st, D1, {"score_parity": True}))
        self.assertFalse(SC.parity_due(st, D0, {"score_parity": False}))

    def test_the_sample_is_about_five_percent_and_fixed(self):
        rows = [{"program": "EVL-ERN-READ-O1", "version": 2, "event": f"8k:{i}"} for i in range(4000)]
        hits = [r["event"] for r in rows if SC.parity_sampled(r)]
        self.assertTrue(150 <= len(hits) <= 250, len(hits))
        self.assertEqual(hits, [r["event"] for r in rows if SC.parity_sampled(r)])

    def test_no_parity_on_the_per_intent_path(self):
        st, tape = self.build("noparity")
        out = SC.settle(st, tape, now=self.NOW, batch=False, parity=True)
        self.assertNotIn("parity", out)
        self.assertIsNone(st.meta(SC.PARITY_FIRST))


class FakeHouse:
    def __init__(self, at):
        self.at = at.timestamp()

    def clock(self):
        return self.at


class Mono:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += float(s)


class TheHousePass(GoldenCase):
    def lane(self, root, **settings):
        lane = H.EventLane(FakeHouse(self.NOW), root, settings=settings, monotonic=Mono(), sleep=lambda s: None)
        lane.throttle = lambda: None
        return lane

    def run_pass(self, name, **settings):
        st, tape = self.build(name)
        lane = self.lane(st.root, **settings)
        ctx = H.LaneContext(lane, st, H.LaneGateway(tape, lane, None, cut=False), lambda url: b"", lane.now)
        out = lane._score(ctx, lane._mono() + H.SCORE_BUDGET, D2)
        receipt = json.loads(st.db.execute("SELECT summary FROM receipts WHERE job='score' ORDER BY id DESC LIMIT 1"
                                           ).fetchone()[0])
        return st, tape, out, receipt

    def test_on_by_default_identical_rows_fewer_requests_and_the_receipt(self):
        old, old_tape, a, ra = self.run_pass("h-old", score_batch=False)
        new, new_tape, b, rb = self.run_pass("h-new")
        self.assertEqual(self.record(new)["outcomes"], self.record(old)["outcomes"])
        self.assertEqual(self.record(new)["intents"], self.record(old)["intents"])
        self.assertFalse(ra["batched"])
        self.assertNotIn("prefetch", ra)
        self.assertTrue(rb["batched"])
        self.assertEqual(rb["prefetch"]["windows"], 1)
        self.assertEqual((rb["settled"], rb["skipped"]), (7, 2))
        self.assertLess(rb["requests"]["bars"], ra["requests"]["bars"])
        self.assertEqual(ra["requests"]["bars"], 14)
        self.assertIn("seconds", rb)
        self.assertIn("parity", rb, "the first batched night is the parity night")
        self.assertEqual(rb["parity"]["checked"], rb["parity"]["equal"])

    def test_the_parity_switch_off(self):
        _, _, _, receipt = self.run_pass("h-noparity", score_parity=False)
        self.assertNotIn("parity", receipt)


if __name__ == "__main__":
    unittest.main()
