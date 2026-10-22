"""THE BATCHED SCORE (release 1019i; PREREG-EVL-8's harness plan H1, league/events/score.py's docstring).

A GOLDEN TAPE: one synthetic market (every symbol, print and bar invented) settled twice, by release 1019h's
per-intent path and by the batched pass, into two stores built the same way: the outcome rows, the intents' moves, the
late exits' meta and the prints kept are byte-identical, with a split inside a hold (Alpaca adjusts every bar to today's
basis), a missing daily bar (its intent falls back to its own fetch), a ladder exit, a skip for no auction, a skip at the
limit and a prefetch chunk that fails; the batched pass asks a fraction of the bar requests. THE `bars` TABLE ends each
pass exactly as under release 1019h, in both directions (release 1019i's review: the prefetch is a cache of the pass,
never the store), over two nights with a split between them, so Done's fill gaps (league/events/done.py `_enrich`)
never move. Then the order (seating versions and their controls first), 200 symbols a request, the switch
(`events.score_batch`), the parity night's equality flags (never a value; computed in memory BEFORE anything is
written, on intents the cache served, writing no bar), a FLAG 0 THAT FAILS CLOSED on a vendor whose adjustment
depends on the request's end (the latch: every intent by the per-intent path until the captain clears it), and the
House's pass with the switch on and off.
"""

import datetime as dt
import io
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
from league.tests.evl6_fakes import on_1019h

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
        #: symbol -> (effective day, factor): adjusted bars before the day divided by the factor ONLY when the request
        #: ends after it (a vendor whose adjustment depends on the request's END: the case the golden fake cannot be)
        self.basis = {}

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
                    if params["adjustment"] == "all" and sym in self.basis and day < self.basis[sym][0] and \
                            end > dt.datetime.combine(self.basis[sym][0], dt.time(4, 0), tzinfo=UTC):
                        f /= self.basis[sym][1]
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
                "marks": self.rows(st, "SELECT * FROM marks ORDER BY symbol, day, label"),
                "bars": self.rows(st, "SELECT * FROM bars ORDER BY symbol, day, adj")}

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
        for part in ("outcomes", "intents", "exits", "marks", "bars"):
            self.assertEqual(mine[part], theirs[part], part)
        self.assertEqual(len(mine["outcomes"]), 7)
        self.assertEqual(len(mine["exits"]), 1, "the ladder's later exit is on record")
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
        # THE `bars` TABLE IN BOTH DIRECTIONS (release 1019i's review): the batched pass stores no bar the per-intent
        # path does not (none of a skipped intent's symbol, none outside an intent's own [entry, exit] window, none
        # of a day before every intent's entry), and overwrites none it leaves alone
        self.assertEqual(self.record(new)["bars"], self.record(old)["bars"])
        self.assertIsNone(new.db.execute("SELECT 1 FROM bars WHERE symbol IN ('NOA', 'LIM')").fetchone(),
                          "an intent skipped before the bar step stores no bar")
        self.assertIsNone(new.db.execute("SELECT 1 FROM bars WHERE day=? AND symbol='AAA'", (PREV.isoformat(),)
                                         ).fetchone(), "no bar of a day outside the intent's own window")
        self.assertEqual(b["prefetch"]["served"], 6, "every settled intent but the missing bar's")
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


# (release 1019j's assembly: a mechanism test written on release 1019h's seats; PREREG-EVL-6 moved every seat to a new
# version, so it runs on that table, as league/tests/test_events_book.py's do)
@on_1019h
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
        old, old_tape = self.build("parity-old")
        with mock.patch.object(SC, "parity_sampled", lambda intent, share=SC.PARITY_SHARE: True):
            out = SC.settle(st, tape, now=self.NOW, batch=True)
        SC.settle(old, old_tape, now=self.NOW, batch=False)
        # every intent sampled; the six the cache served are checked (the missing bar's fell back to its own two
        # fetches: the per-intent path compared with itself is no test of the batched one, so it has no flag), and the
        # two skipped before any bar have nothing batched to compare
        self.assertEqual(out["parity"], {"sampled": 9, "checked": 6, "equal": 6})
        self.assertNotIn("latched", out)
        flagged = {r[0].split("-")[0] for r in st.db.execute("SELECT event FROM score_parity")}
        self.assertEqual(flagged, {"8k:aaa", "8k:bbb", "8k:ccc", "8k:lad", "8k:spl", "8k:flk"})
        cols = [r[1] for r in st.db.execute("PRAGMA table_info(score_parity)")]
        self.assertEqual(cols, ["program", "version", "event", "night", "equal", "checked_at"], "no value column")
        self.assertEqual(st.meta(SC.PARITY_FIRST), D2.isoformat())
        self.assertEqual(SC.parity_counts(st, D2), {"checked": 6, "equal": 6})
        self.assertEqual(self.record(st), self.record(old), "the parity night writes what release 1019h writes")

    def test_the_check_writes_no_bar_and_settles_nothing(self):
        st, tape = self.build("dry")
        intents = SC.order_due(SC.due(st, self.NOW))
        pre = SC.prefetch(st, tape, intents, now=self.NOW)
        before = self.record(st)
        with mock.patch.object(SC, "parity_sampled", lambda intent, share=SC.PARITY_SHARE: True):
            got = SC.parity_window(st, tape, intents, pre, D2, now=self.NOW)
        after = self.record(st)
        self.assertEqual(got["checked"], 6)
        self.assertEqual(after["bars"], before["bars"], "neither path of the check writes a bar")
        self.assertEqual(after["bars"], [], "nothing was in `bars` and nothing is: the prefetch is the pass's cache")
        self.assertEqual((after["outcomes"], after["intents"]), (before["outcomes"], before["intents"]),
                         "nothing is settled by the check: it runs before any of the window settles")

    def test_a_difference_writes_zero_and_latches(self):
        st, tape = self.build("differ")
        intents = SC.order_due(SC.due(st, self.NOW))
        pre = SC.prefetch(st, tape, intents, now=self.NOW)
        intent = next(i for i in intents if i["event"].startswith("8k:aaa-"))
        self.assertEqual(SC.check_parity(st, tape, intent, D2, now=self.NOW, prefetched=pre), 1)
        self.assertIsNone(SC.latched(st))
        real = SC.Narrow.read

        def off(self_, *a, **k):
            ratio = real(self_, *a, **k)
            return lambda sym, day: ratio(sym, day) * (1.0 + 1e-12)
        with mock.patch.object(SC.Narrow, "read", off):
            self.assertEqual(SC.check_parity(st, tape, intent, D2, now=self.NOW, prefetched=pre), 0)
        row = dict(st.db.execute("SELECT * FROM score_parity WHERE event=?", (intent["event"],)).fetchone())
        self.assertEqual(row["equal"], 0)
        self.assertNotIn("r", row)
        held = SC.latched(st)
        self.assertEqual((held["night"], held["program"], held["version"], held["event"]),
                         (D2.isoformat(), "EVL-ERN-READ-O1", 2, intent["event"]))
        self.assertEqual(set(held), {"night", "program", "version", "event", "at"}, "identifiers and a time, no value")

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


class TheParityNightIsTheFirstThatTests(GoldenCase):
    """THE PARITY NIGHT IS THE FIRST NIGHT A FLAG IS WRITTEN (release 1019i's fix round): a first batched night that
    tested nothing batched (its prefetch failed, so every intent settled by its own two fetches; or its 5% sample held
    no intent the cache served) must not use up the parity night, or the batched path would settle every later night
    unchecked while the report showed no difference."""

    def only(self, events):
        return lambda intent, share=SC.PARITY_SHARE: any(str(intent["event"]).startswith(e) for e in events)

    def test_a_failed_prefetch_tests_nothing_and_the_next_night_is_the_parity_night(self):
        st, tape = self.build("pf-failed")
        tape.fail.add("AAA")        # the raw chunk fails: the cache serves no intent, each fetches its own two
        with mock.patch.object(SC, "parity_sampled", lambda intent, share=SC.PARITY_SHARE: True):
            out = SC.settle(st, tape, now=self.NOW, batch=True)
        self.assertTrue(out["batched"])
        self.assertEqual(out["settled"], 7)
        self.assertEqual(out["prefetch"]["served"], 0)
        self.assertEqual(out["parity"], {"sampled": 9, "checked": 0, "equal": 0})
        self.assertIsNone(st.meta(SC.PARITY_FIRST), "nothing batched was tested: this was no parity night")
        later = self.NOW + dt.timedelta(days=1)
        self.assertTrue(SC.parity_due(st, later.astimezone(NY).date()))
        # the next night the cache serves its intent: the check runs (unforced), and that night is the parity night
        self.intent(st, "SPL", "EVL-ERN-READ-O3", 1, entry=D2, exit_=D2, prev_close=51.0)
        with mock.patch.object(SC, "parity_sampled", lambda intent, share=SC.PARITY_SHARE: True):
            nxt = SC.settle(st, tape, now=later, batch=True)
        self.assertEqual(nxt["parity"], {"sampled": 1, "checked": 1, "equal": 1})
        self.assertEqual(st.meta(SC.PARITY_FIRST), later.astimezone(NY).date().isoformat())
        self.assertFalse(SC.parity_due(st, later.astimezone(NY).date() + dt.timedelta(days=1)))

    def test_a_sample_the_cache_served_none_of_is_no_parity_night(self):
        st, tape = self.build("pf-unserved")
        with mock.patch.object(SC, "parity_sampled", self.only(["8k:mis-", "8k:noa-"])):
            out = SC.settle(st, tape, now=self.NOW, batch=True)
        self.assertEqual(out["prefetch"]["served"], 6)
        self.assertEqual(out["parity"], {"sampled": 2, "checked": 0, "equal": 0},
                         "the missing bar's intent fell back and the other skipped before any bar")
        self.assertIsNone(st.meta(SC.PARITY_FIRST))
        self.assertTrue(SC.parity_due(st, D2 + dt.timedelta(days=1)))

    def test_the_first_flag_keeps_its_night(self):
        st, tape = self.build("pf-flag")
        with mock.patch.object(SC, "parity_sampled", self.only(["8k:aaa-"])):
            out = SC.settle(st, tape, now=self.NOW, batch=True)
        self.assertEqual(out["parity"], {"sampled": 1, "checked": 1, "equal": 1})
        self.assertEqual(st.meta(SC.PARITY_FIRST), D2.isoformat())
        self.assertTrue(SC.parity_due(st, D2), "every pass of that night checks")
        self.assertFalse(SC.parity_due(st, D2 + dt.timedelta(days=1)))

    def test_the_houses_pass_keeps_the_rule(self):
        st, tape = self.build("pf-house")
        lane = H.EventLane(FakeHouse(self.NOW), st.root, settings={}, monotonic=Mono(), sleep=lambda s: None)
        lane.throttle = lambda: None
        ctx = H.LaneContext(lane, st, H.LaneGateway(tape, lane, None, cut=False), lambda url: b"", lane.now)
        with mock.patch.object(SC, "parity_sampled", self.only(["8k:mis-", "8k:noa-"])):
            out = lane._score(ctx, lane._mono() + H.SCORE_BUDGET, D2)
        self.assertTrue(out["batched"])
        self.assertEqual(out["prefetch"]["served"], 6)
        self.assertEqual(out["parity"], {"sampled": 2, "checked": 0, "equal": 0})
        self.assertIsNone(st.meta(SC.PARITY_FIRST), "the House's pass tested nothing batched either")
        self.assertTrue(SC.parity_due(st, D2 + dt.timedelta(days=1), lane.settings))


class TheEndDependentVendor(GoldenCase):
    """THE PARITY NIGHT FAILS CLOSED (release 1019i's review): a vendor whose adjusted bars depend on the request's END
    (SPY's factor 1.01 effective D1, applied only to a window that reaches past it) is the one case the batched and
    per-intent paths can differ. The sampled intent AAA (D0 to D0, on SPY) disagrees; the check runs before anything
    is written, latches, and the whole pass settles by the per-intent path: SPL (D0 to D2, on SPY, NOT sampled) settles
    exactly as under release 1019h, never on a mix of two bases."""

    def sampled(self, events):
        return lambda intent, share=SC.PARITY_SHARE: any(str(intent["event"]).startswith(e) for e in events)

    def build_basis(self, name):
        st, tape = self.build(name)
        tape.basis["SPY"] = (D1, 1.01)
        return st, tape

    def test_a_difference_latches_and_the_pass_is_release_1019h(self):
        old, old_tape = self.build_basis("e-old")
        SC.settle(old, old_tape, now=self.NOW, batch=False)
        bare, bare_tape = self.build_basis("e-bare")
        SC.settle(bare, bare_tape, now=self.NOW, batch=True, parity=False)
        aaa = "SELECT bench_entry, b FROM outcomes WHERE event LIKE '8k:aaa-%'"
        self.assertNotEqual(tuple(bare.db.execute(aaa).fetchone()), tuple(old.db.execute(aaa).fetchone()),
                            "this vendor is the case parity exists for: unchecked, the batched path differs")
        new, new_tape = self.build_basis("e-new")
        with mock.patch.object(SC, "parity_sampled", self.sampled(["8k:aaa-"])):
            out = SC.settle(new, new_tape, now=self.NOW, batch=True)
        spl = "SELECT b, bench_entry, bench_exit FROM outcomes WHERE event LIKE '8k:spl-%'"
        self.assertEqual(tuple(new.db.execute(spl).fetchone()), tuple(old.db.execute(spl).fetchone()),
                         "the unsampled intent on the same benchmark: release 1019h's value, not a mix of bases")
        mine, theirs = self.record(new), self.record(old)
        for part in ("outcomes", "intents", "exits", "marks", "bars"):
            self.assertEqual(mine[part], theirs[part], part)
        self.assertEqual(out["parity"], {"sampled": 1, "checked": 1, "equal": 0})
        self.assertTrue(out["latched"])
        self.assertEqual(out["prefetch"]["served"], 0, "after the latch no intent settles from the cache")
        self.assertEqual(SC.parity_counts(new, D2), {"checked": 1, "equal": 0})

    def test_the_latch_holds_every_later_pass_until_the_captain_clears_it(self):
        st, tape = self.build_basis("latch")
        with mock.patch.object(SC, "parity_sampled", self.sampled(["8k:aaa-"])):
            SC.settle(st, tape, now=self.NOW, batch=True)
        self.assertIsNotNone(SC.latched(st))
        # a later pass, the switch on and the parity night over: still the per-intent path, nothing prefetched
        self.intent(st, "SPL", "EVL-ERN-READ-O3", 1, entry=D2, exit_=D2, prev_close=51.0)
        later = self.NOW + dt.timedelta(days=1)
        tape.calls.clear()
        out = SC.settle(st, tape, now=later, batch=True, parity=False)
        self.assertFalse(out["batched"])
        self.assertTrue(out["latched"])
        self.assertNotIn("prefetch", out)
        self.assertEqual(out["settled"], 1)
        self.assertEqual(len(tape.bar_requests()), 2, "its own two fetches")
        self.assertFalse(SC.parity_due(st, later.astimezone(NY).date()), "the latch's night was the parity night")
        held = SC.unlatch(st)
        self.assertEqual(held["event"].split("-")[0], "8k:aaa")
        self.assertIsNone(SC.latched(st))
        self.assertTrue(SC.parity_due(st, later.astimezone(NY).date()),
                        "cleared, the batched path is checked again on its next night")
        self.assertIsNone(SC.unlatch(st), "nothing to clear")
        self.intent(st, "AAA", "EVL-ERN-READ-O1", 2, entry=D2, exit_=D2, prev_close=50.0)
        again = SC.settle(st, tape, now=later + dt.timedelta(hours=1), batch=True, parity=False)
        self.assertTrue(again["batched"])
        self.assertIn("prefetch", again)

    def test_the_cli_clears_it(self):
        from league.events import __main__ as M

        st, _ = self.build("cli")
        SC.latch(st, D2, {"program": "EVL-ERN-READ-O1", "version": 2, "event": "8k:x"}, self.NOW)
        st.close()
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            self.assertEqual(M.main(["--state", str(Path(self.tmp.name) / "cli"), "score-unlatch"]), 0)
        said = json.loads(out.getvalue())
        self.assertEqual(said["cleared"]["event"], "8k:x")
        with S.Store(Path(self.tmp.name) / "cli") as again:
            self.assertIsNone(SC.latched(again))


class TwoNights(GoldenCase):
    """A CORPORATE ACTION BETWEEN TWO NIGHTS (release 1019i's review, its first major): night 1 settles a real buy of
    XYZ (D0 to D0) with its real fill at the print; a 2:1 split of XYZ takes effect D2; night 2 settles a new XYZ
    intent (D2 to D2) and another symbol's D0 to D2 intent, so the union window starts at D0. The batched night must
    leave XYZ's D0 bars as the per-intent path does (it never fetches them), so Done's fill gap of the night-1 event
    (league/events/done.py `_enrich`, item 4.7, through `_ratio`) does not move."""

    def two_nights(self, name, batch):
        self.n = 0
        st = S.Store(Path(self.tmp.name) / name)
        self.addCleanup(st.close)
        tape = Tape()
        C.refresh(st, tape, dt.date(2026, 10, 1), dt.date(2026, 12, 31))
        st.set_meta("equity:2026-10-19", repr(20000.0))
        for day in (PREV, D0, D1, D2):
            k = {PREV: 0, D0: 1, D1: 2, D2: 3}[day]
            for bench, base in (("SPY", 600.0), ("IWM", 220.0)):
                self.session(tape, st, day, bench, "P", base + k, base + k + 1.5)
            # XYZ trades about half its price from D2 on (the split): its prints and raw bars are raw
            self.session(tape, st, day, "XYZ", "N", *((80.0 + k, 80.5 + k) if day < D2 else (41.5, 41.75)))
            self.session(tape, st, day, "OTH", "N", 30.0 + k, 30.2 + k)
        tape.raw[("XYZ", PREV)] = (79.0, 79.0)
        tape.raw[("OTH", PREV)] = (29.0, 29.0)
        self.intent(st, "XYZ", "EVL-ERN-READ-O1", 2, prev_close=79.0)
        night1 = SC.settle(st, tape, now=wall(D0, "16:30"), batch=batch, parity=False)
        self.assertEqual(night1["settled"], 1)
        event = st.db.execute("SELECT event FROM intents WHERE symbol='XYZ'").fetchone()[0]
        with st.tx() as db:     # the real buy, filled at the opening print (an invented fill)
            db.execute("INSERT INTO real_fills(program, version, event, side, qty, price, fee, filled_at, band) VALUES("
                       "'EVL-ERN-READ-O1', 2, ?, 'buy', 2, 81.0, 0, ?, 'probe')", (event, S.iso(wall(D0, "09:30"))))
        before = self.gap(st, event)
        tape.splits["XYZ"] = (D2, 2.0)      # a 2:1 split effective D2: the vendor re-bases every earlier adjusted bar
        self.intent(st, "XYZ", "EVL-ERN-READ-O1", 2, entry=D2, exit_=D2, prev_close=81.4)
        self.intent(st, "OTH", "EVL-NEWS-READ-O1", 2, entry=D0, exit_=D2, prev_close=29.0)
        night2 = SC.settle(st, tape, now=wall(D2, "16:30"), batch=batch, parity=False)
        self.assertEqual(night2["settled"], 2, night2)
        return st, event, before, night2

    def gap(self, st, event):
        from league.events import done as DN

        r = st.db.execute("SELECT r FROM outcomes WHERE event=?", (event,)).fetchone()[0]
        return DN._enrich(st, "EVL-ERN-READ-O1", 2, [{"event": event, "r": r}])[0]["entry_gap_bp"]

    def test_dones_fill_gap_never_moves(self):
        from league.events import done as DN

        old, event, old_before, _ = self.two_nights("n-old", False)
        new, _, new_before, night2 = self.two_nights("n-new", True)
        self.assertEqual(night2["prefetch"]["first"], D0.isoformat(), "the union window reaches back to D0")
        self.assertEqual(old_before, 0.0)
        self.assertEqual(new_before, 0.0)
        self.assertEqual(self.gap(old, event), 0.0, "release 1019h's path never fetches XYZ's D0 bars again")
        self.assertEqual(self.gap(new, event), 0.0, "nor does the batched one: Done's item 4.7 reads the same gap")
        self.assertEqual(DN._ratio(new, "XYZ", D0.isoformat()), DN._ratio(old, "XYZ", D0.isoformat()))
        self.assertEqual(self.record(new), self.record(old), "every outcome, mark and bar the same, both ways")


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

    def test_a_flag_zero_on_the_house_latches_and_settles_as_release_1019h(self):
        old, old_tape = self.build("h-e-old")
        old_tape.basis["SPY"] = (D1, 1.01)
        SC.settle(old, old_tape, now=self.NOW, batch=False)
        st, tape = self.build("h-e-new")
        tape.basis["SPY"] = (D1, 1.01)
        lane = self.lane(st.root)
        ctx = H.LaneContext(lane, st, H.LaneGateway(tape, lane, None, cut=False), lambda url: b"", lane.now)
        with mock.patch.object(SC, "parity_sampled", lambda i, share=SC.PARITY_SHARE: str(i["event"]).startswith("8k:aaa")):
            out = lane._score(ctx, lane._mono() + H.SCORE_BUDGET, D2)
        self.assertEqual(out["parity"], {"sampled": 1, "checked": 1, "equal": 0})
        self.assertTrue(out["latched"])
        self.assertEqual(out["prefetch"]["served"], 0)
        for part in ("outcomes", "intents", "bars"):
            self.assertEqual(self.record(st)[part], self.record(old)[part], part)
        self.assertEqual(lane._warnings, 1, "the latch is warned")
        # the next night's pass: the per-intent path, whatever the switch says
        nxt = lane._score(ctx, lane._mono() + H.SCORE_BUDGET, D2 + dt.timedelta(days=1))
        self.assertFalse(nxt["batched"])
        self.assertTrue(nxt["latched"])


if __name__ == "__main__":
    unittest.main()
