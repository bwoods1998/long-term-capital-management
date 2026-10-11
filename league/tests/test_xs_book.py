"""The live panel adapter (`league/xs/book.py`, package H of release E4): a day's columns, the chunked fetch, when a
fetch may be decided on, the kept bars and their audit, the decide's job, the standing target, and the live rules by
close date. Seals X8 (`TheSaltNeverLeaves`) and X15 (`TheLiveRulesAreByDate`).

Other packages' functions are stubbed AT THEIR INTERFACE, as the book's own tests do (league/tests/test_equity_book.py):
package C's universe, ids, dither key, `rows_to_arrays`, `inputs_from_arrays` and `decision_due` are the doubles below,
written from their contract's words (league/xs/E4_INTERFACES.md; the stubs' docstrings); their own packages test them.
`fixtures()` installs them. Every price here is invented; no symbol is a market's."""

import datetime as dt
import hashlib
import math
import os
import pickle
import stat
import tempfile
import unittest
from contextlib import contextmanager
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity import bands as B
from league.equity import live as L
from league.equity import schedule as S
from league.equity import store as ES
from league.tests import test_equity_book as T
from league.xs import book, config
from league.xs import ctx as X
from league.xs import program as P
from league.xs import store as XS

DAY = dt.date(2026, 10, 13)            # a Tuesday
PREV = dt.date(2026, 10, 12)
SALT = bytes(range(32))
UNIVERSES: dict[str, "Universe"] = {}


# --------------------------------------------------------------------------- package C at its interface (test doubles)
class Universe:
    """`league.xs.store.Universe` at its interface: spells {aid: [(symbol, start, end | None)]}, a tradable set."""

    def __init__(self, root):
        other = UNIVERSES[str(root)]
        self.spells, self.allowed, self.asked = other.spells, other.allowed, other.asked

    @classmethod
    def make(cls, root, names, *, start=dt.date(2016, 1, 4)):
        self = object.__new__(cls)
        self.spells = {100 + k: [(name, start, None)] for k, name in enumerate(names)}
        self.allowed, self.asked = None, []
        UNIVERSES[str(root)] = self
        return self

    def end(self, symbol, day):
        aid = next(a for a, spells in self.spells.items() if spells[-1][0] == symbol)
        name, start, _ = self.spells[aid][-1]
        self.spells[aid][-1] = (name, start, day)

    def members(self, day):
        self.asked.append(day)
        return [(aid, name) for aid, spells in sorted(self.spells.items())
                for name, start, end in spells if start <= day and (end is None or day < end)]

    def aid(self, symbol, day):
        for aid, spells in self.spells.items():
            for name, start, end in spells:
                if name == symbol and start <= day and (end is None or day < end):
                    return aid
        raise KeyError(symbol)

    def tradable(self, day):
        return {name for _, name in self.members(day)} if self.allowed is None else set(self.allowed)

    def table(self):
        return np.array(sorted(self.spells), dtype=np.int32)


def run_salt(salt, run_key):
    return hashlib.sha256(salt + b"|" + str(run_key).encode()).digest()


def ids_for(aids, key, *, table):
    """D8 as its stub says it: 31 bits of sha256(run_salt | b"|id|" | str(aid)), a collision settled over the table."""
    taken, given = set(), {}
    for aid in sorted(int(a) for a in table):
        digest = hashlib.sha256(key + b"|id|" + str(aid).encode()).digest()
        for at in range(0, 28, 4):
            value = int.from_bytes(digest[at:at + 4], "big") >> 1
            if value not in taken:
                break
        taken.add(value)
        given[aid] = value
    return np.array([given[int(a)] for a in aids], dtype=np.int32)


def rows_to_arrays_counting(raw_rows, all_rows, *, day, columns, count=None):
    """`rows_to_arrays` below with the real one's count of the rows on a day that is no session (a weekend's)."""
    weekend = [r for rows in raw_rows.values() for r in rows if dt.date.fromisoformat(r["t"][:10]).weekday() > 4]
    if count is not None:
        count["dropped"] = int(count.get("dropped") or 0) + len(weekend)
    keep = {s: [r for r in rows if r not in weekend] for s, rows in raw_rows.items()}
    return rows_to_arrays(keep, all_rows, day=day, columns=columns)


def rows_to_arrays(raw_rows, all_rows, *, day, columns, count=None):
    """The venue's rows as arrays over the sessions the chunk itself carries (never the whole window: the adapter
    places a chunk by session)."""
    days = sorted({r["t"][:10] for rows in raw_rows.values() for r in rows if r["t"][:10] <= day.isoformat()})
    raw = np.full((len(days), len(columns), 5), np.nan)
    adj = np.full((len(days), len(columns), 4), np.nan)
    where = {d: k for k, d in enumerate(days)}
    for j, symbol in enumerate(columns):
        for r in raw_rows.get(symbol) or []:
            if r["t"][:10] in where:
                raw[where[r["t"][:10]], j] = [r[k] for k in "ohlcv"]
        for r in all_rows.get(symbol) or []:
            if r["t"][:10] in where:
                adj[where[r["t"][:10]], j] = [r[k] for k in "ohlc"]
    return np.array([ES.ordinal(dt.date.fromisoformat(d)) for d in days], dtype=np.int32), raw, adj


def inputs_from_arrays(days, raw, adj, *, day, elig0, ids, dither_key, sector_perm, needs, positions=(), closed=(),
                       rejects=(), cash, equity, budget, params):
    if not np.isfinite(raw[-1, config.MARKET_COLUMN, 3]) or int(days[-1]) != ES.ordinal(day):
        raise ValueError("SPY has no bar of the day")
    return X.Inputs(days=days, raw=raw, adj=adj, elig0=elig0, ref=len(config.REF), ids=ids, dither_key=dither_key,
                    sector_perm=sector_perm, history=needs.history, max_names=needs.max_names,
                    trading_days=np.zeros(0, dtype=np.int32), early=np.zeros(0, dtype=bool), positions=tuple(positions),
                    closed=tuple(closed), rejects=tuple(rejects), cash=cash, equity=equity, budget=budget, params=params)


def decision_due(t, rule, weekday=0):
    """D9: the program is called at the close of t iff the next session is a rebalance session."""
    u = S.next_session(t)
    if rule == "monthly":
        return u.month != t.month
    week = [d for d, _ in ES.nyse_sessions(u - dt.timedelta(days=u.weekday()), u + dt.timedelta(days=6 - u.weekday()))
            if d.isocalendar()[:2] == u.isocalendar()[:2] and d.weekday() >= weekday]
    return bool(week) and week[0] == u


@contextmanager
def fixtures():
    """Package C's names the adapter calls, each replaced by its double."""
    with mock.patch.object(XS, "Universe", Universe), mock.patch.object(XS, "read_salt", lambda root: SALT), \
            mock.patch.object(XS, "run_salt", run_salt), mock.patch.object(XS, "ids_for", ids_for), \
            mock.patch.object(XS, "dither_key", lambda key: hashlib.sha256(key + b"|dither|").digest()), \
            mock.patch.object(XS, "sector_perm", lambda key: np.argsort(np.frombuffer(key[:11], dtype=np.uint8),
                                                                        kind="stable").astype(np.int8)), \
            mock.patch.object(X, "rows_to_arrays", rows_to_arrays), \
            mock.patch.object(X, "inputs_from_arrays", inputs_from_arrays), \
            mock.patch.object(config, "decision_due", decision_due):
        yield


class Market:
    """1Day bars of invented prices for any symbol: a cent grid, a vendor that rounds adjustment=all to the cent.
    `absent`: (symbol, ISO day) served no bar; `moved`: {(symbol, ISO day): raw close} read differently."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.absent: set[tuple[str, str]] = set()
        self.moved: dict[tuple[str, str], float] = {}
        self.volume_drift = 0
        self.fail_at: int | None = None
        self.on_call = None

    def price(self, symbol, k):
        base = 20.0 + (int(hashlib.sha256(symbol.encode()).hexdigest()[:6], 16) % 40000) / 100.0
        return round(base * (1 + 0.0004 * k) + 0.01 * (k % 7), 2)

    def bars(self, symbols, *, timeframe, start, end=None, adjustment="raw"):
        self.calls.append((tuple(symbols), start, end, adjustment))
        if self.on_call is not None:
            self.on_call()
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            raise RuntimeError("the gateway timed out")
        first, last = dt.date.fromisoformat(start), dt.date.fromisoformat(end) - dt.timedelta(days=1)
        out = {}
        for symbol in symbols:
            rows = []
            for d, _ in ES.nyse_sessions(first, last):
                iso = d.isoformat()
                if (symbol, iso) in self.absent:
                    continue
                k = ES.ordinal(d) - ES.ordinal(dt.date(2025, 1, 2))
                c = self.moved.get((symbol, iso), self.price(symbol, k))
                row = {"t": f"{iso}T04:00:00Z", "o": round(c - 0.11, 2), "h": round(c + 0.5, 2), "l": round(c - 0.6, 2),
                       "c": c, "v": 100000 + 13 * k + (self.volume_drift if d == last else 0)}
                if adjustment == "all":
                    row = {**row, **{f: round(row[f] * 0.98, 2) for f in "ohlc"}}
                rows.append(row)
            out[symbol] = rows
        return out


def names(n, prefix="N"):
    return [f"{prefix}{k:03d}" for k in range(n)]


def lot(lid, symbol, *, instance="fam@1:r", opened="2026-10-06", qty="2", entry="50", status=L.LOT_OPEN, exit_day=None,
        cash="0", reason=None, probe=True, mark=None, tag="xs", closed_at=None):
    qty, entry = D(qty), D(entry)
    return L.Lot(lid, instance, "fam", 1, "equity", symbol, "stock", qty=qty if status != L.LOT_CLOSED else D(0),
                 opened_qty=qty, entry_px=entry, entry_notional=qty * entry, entry_at="open", opened_at=0.0,
                 opened_day=opened, status=status, exit_day=exit_day, cash=D(cash), reason=reason, probe=probe,
                 mark=None if mark is None else D(mark), tag=tag, closed_at=closed_at)


NEEDS = {"panel": "sp500", "history": 60, "max_names": 8, "rebalance": "weekly", "weekday": 0, "max_hold_sessions": 30}


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.universe = Universe.make(self.root, names(30))
        self.addCleanup(UNIVERSES.pop, str(self.root), None)
        self.market = Market()
        patch = fixtures()
        patch.__enter__()
        self.addCleanup(patch.__exit__, None, None, None)

    def fetched(self, cols, day=DAY):
        return book.fetch(self.market, cols, day)


# ----------------------------------------------------------------------------------------------------------- columns
class TheColumns(Case):
    def test_ref_first_then_the_members_in_ascending_id(self):
        cols = book.columns(self.root, "fam@1:r", DAY, held=())
        self.assertEqual(cols.symbols[:12], config.REF)
        self.assertEqual(sorted(cols.symbols[12:]), names(30))
        self.assertEqual(cols.ids.tolist(), sorted(cols.ids.tolist()))
        self.assertEqual(len(set(cols.ids.tolist())), 30)
        self.assertEqual(cols.aids[:12].tolist(), list(range(1, 13)))
        self.assertEqual([self.universe.aid(s, DAY) for s in cols.symbols[12:]], cols.aids[12:].tolist())
        self.assertFalse(cols.elig0[:12].any(), "REF is never a candidate")
        self.assertTrue(cols.elig0[12:].all())
        self.assertEqual(cols.extra, ())
        self.assertEqual(len(cols.dither_key), 32)

    def test_another_run_key_gives_other_ids_and_another_order(self):
        a, b = book.columns(self.root, "fam@1:r", DAY, held=()), book.columns(self.root, "other@1:r", DAY, held=())
        self.assertNotEqual(a.ids.tolist(), b.ids.tolist())
        self.assertNotEqual(a.symbols, b.symbols)
        self.assertNotEqual(a.dither_key, b.dither_key)
        self.assertEqual(book.slots(a).keys(), book.slots(b).keys())

    def test_a_held_name_that_left_keeps_its_column_and_its_id(self):
        before = book.slots(book.columns(self.root, "fam@1:r", PREV, held=()))
        self.universe.end("N007", DAY)                          # it left the index: no member today
        self.universe.spells[900] = [("NEW", DAY, None)]        # and a name joined
        cols = book.columns(self.root, "fam@1:r", DAY, held={"N007": "2026-10-06"})
        after = book.slots(cols)
        self.assertEqual(cols.extra, ("N007",))
        self.assertEqual(after["N007"], before["N007"], "the id its lot was bought under")
        self.assertEqual({s: i for s, i in after.items() if s != "NEW"}, before, "a membership change moves no id")
        self.assertFalse(cols.elig0[cols.symbols.index("N007")], "a name that left is never a candidate")
        self.assertTrue(cols.elig0[cols.symbols.index("NEW")])
        self.assertEqual(cols.ids.tolist(), sorted(cols.ids.tolist()), "the extra column sits in id order too")
        self.assertNotIn("N007", book.columns(self.root, "fam@1:r", DAY, held=()).symbols)

    def test_a_ticker_change_inside_a_held_lot_keeps_its_column(self):
        """The review's live-8. E1 books the venue's NC activity onto the lot (its symbol is the new one, its
        `info.renamed_from` the old) the day it posts; the membership job reads the new ticker days later. Until
        then the lot's symbol was "no asset of the panel's universe": every decide refused, the lot judged by
        nothing."""
        before = book.columns(self.root, "fam@1:r", DAY, held={"N007": "2026-10-06"})
        with self.assertRaises(book.ColumnsRefused):
            book.columns(self.root, "fam@1:r", DAY, held={"N7NEW": "2026-10-06"})
        with self.assertRaises(book.ColumnsRefused, msg="a rename that names nothing the universe knows is refused too"):
            book.columns(self.root, "fam@1:r", DAY, held={"N7NEW": "2026-10-06"}, renamed={"N7NEW": "ZZZZ"})
        cols = book.columns(self.root, "fam@1:r", DAY, held={"N7NEW": "2026-10-06"}, renamed={"N7NEW": "N007"})
        self.assertNotIn("N007", cols.symbols)
        self.assertEqual(book.slots(cols)["N7NEW"], book.slots(before)["N007"], "the slot its lot was bought under")
        self.assertEqual({s: i for s, i in book.slots(cols).items() if s != "N7NEW"},
                         {s: i for s, i in book.slots(before).items() if s != "N007"}, "no other id moves")
        self.assertEqual((cols.extra, len(cols.symbols)), ((), len(before.symbols)), "the asset's own member column")
        self.assertFalse(cols.elig0[cols.symbols.index("N7NEW")],
                         "the new ticker is not on the constitution's list: no candidate, and the House exits the lot")
        self.assertEqual(cols.ids.tolist(), sorted(cols.ids.tolist()))
        # THE NAME HAS LEFT THE INDEX too: a column of its own, by the ticker it was bought under.
        self.universe.end("N007", DAY)
        gone = book.columns(self.root, "fam@1:r", DAY, held={"N7NEW": "2026-10-06"}, renamed={"N7NEW": "N007"})
        self.assertEqual((gone.extra, book.slots(gone)["N7NEW"]), (("N7NEW",), book.slots(before)["N007"]))
        # ONCE THE UNIVERSE HAS READ THE CHANGE the lot's symbol is a member's and the old one is nobody's.
        self.universe.spells[107] = [("N007", dt.date(2016, 1, 4), dt.date(2026, 10, 8)), ("N7NEW", dt.date(2026, 10, 8), None)]
        known = book.columns(self.root, "fam@1:r", DAY, held={"N7NEW": "2026-10-06"}, renamed={"N7NEW": "N007"})
        self.assertEqual((known.extra, book.slots(known)["N7NEW"]), ((), book.slots(before)["N007"]))

    def test_a_held_symbol_no_asset_traded_under_is_refused(self):
        with self.assertRaises(book.ColumnsRefused):
            book.columns(self.root, "fam@1:r", DAY, held=["ZZZZ"])
        with self.assertRaises(book.ColumnsRefused):
            book.columns(self.root, "fam@1:r", DAY, held={"ZZZZ": "2026-10-06"})
        self.universe.end("N007", DAY)
        with self.assertRaises(book.ColumnsRefused, msg="no day it was bought on: it cannot be found once it left"):
            book.columns(self.root, "fam@1:r", DAY, held=["N007"])
        self.assertIn("N006", book.columns(self.root, "fam@1:r", DAY, held=["N006"]).symbols, "a member needs none")

    def test_membership_is_read_two_sessions_ahead_and_the_tradable_list_is_asked(self):
        self.universe.end("N003", dt.date(2026, 10, 15))         # a member on the 13th and the 14th, gone on the 15th
        self.universe.allowed = set(names(30)) - {"N004"}
        cols = book.columns(self.root, "fam@1:r", DAY, held=())
        self.assertFalse(cols.elig0[cols.symbols.index("N003")])
        self.assertFalse(cols.elig0[cols.symbols.index("N004")], "not on the constitution's list: no candidate")
        self.assertEqual(int(cols.elig0.sum()), 28)
        self.assertIn("N003", cols.symbols)
        self.assertEqual(self.universe.asked.count(dt.date(2026, 10, 15)), 1)

    def test_the_union_names_no_run(self):
        a = book.columns(self.root, "fam@1:r", DAY, held=())
        self.universe.end("N007", DAY)
        b = book.columns(self.root, "other@1:r", DAY, held={"N007": "2026-10-06"})
        both = book.union([a, b])
        self.assertEqual(both.symbols[:12], config.REF)
        self.assertEqual(list(both.symbols[12:]), sorted(set(a.symbols[12:]) | {"N007"}))
        self.assertEqual((both.ids.size, both.aids.size, both.dither_key), (0, 0, b""))
        self.assertEqual(both.extra, ("N007",))
        self.assertTrue(both.elig0[both.symbols.index("N007")], "a candidate for the instance that still lists it")
        fetched = self.fetched(both)
        mine = book.view(fetched, both.symbols, b)
        self.assertEqual(mine.raw.shape[1], len(b.symbols))
        k, u = b.symbols.index("N011"), both.symbols.index("N011")
        np.testing.assert_array_equal(mine.raw[:, k], fetched.raw[:, u])
        with self.assertRaises(KeyError):
            book.view(fetched, both.symbols[:-1], b)

    def test_the_decision_days(self):
        self.assertTrue(book.called(dt.date(2026, 10, 9), NEEDS), "Friday's close: Monday opens the week")
        self.assertFalse(book.called(DAY, NEEDS))
        self.assertTrue(book.called(dt.date(2026, 10, 30), {**NEEDS, "rebalance": "monthly"}))
        self.assertFalse(book.called(dt.date(2026, 10, 9), {**NEEDS, "rebalance": "monthly"}))
        self.assertEqual(book.needs_of(NEEDS), P.Needs("sp500", 60, 8, "weekly", 0, 30))


# --------------------------------------------------------------------------------------------------------- the fetch
class TheChunkedFetch(Case):
    def setUp(self):
        super().setUp()
        Universe.make(self.root, names(90))
        self.cols = book.columns(self.root, "fam@1:r", DAY, held=())

    def test_a_chunk_is_one_page_and_the_dicts_go_before_the_next(self):
        fetched = self.fetched(self.cols)
        sizes = [len(c[0]) for c in self.market.calls]
        self.assertEqual(sizes, [39, 39, 39, 39, 24, 24], "102 columns: three chunks, raw then all")
        self.assertLessEqual(max(sizes) * config.DERIVE_SESSIONS, 10000, "a chunk is one page of the venue")
        self.assertEqual([c[3] for c in self.market.calls], ["raw", "all"] * 3)
        sessions = book.sessions_through(DAY)
        self.assertEqual(len(sessions), config.DERIVE_SESSIONS)
        self.assertEqual(self.market.calls[0][1:3], (sessions[0].isoformat(), "2026-10-14"))
        self.assertEqual(fetched.days.tolist(), [ES.ordinal(d) for d in sessions])
        self.assertEqual((fetched.raw.shape, fetched.all.shape), ((253, 102, 5), (253, 102, 4)))
        self.assertEqual({k: fetched.meta[k] for k in ("calls", "symbols", "late")},
                         {"calls": 6, "symbols": 102, "late": False})
        k = self.cols.symbols.index("N050")
        row = self.market.bars(["N050"], timeframe="1Day", start=DAY.isoformat(), end="2026-10-14")["N050"][0]
        self.assertEqual(fetched.raw[-1, k].tolist(), [row[f] for f in "ohlcv"])
        self.assertEqual(fetched.all[-1, k, 3], round(row["c"] * 0.98, 2))

    def test_at_most_twenty_seconds_of_calls_a_tick_and_it_keeps_its_place(self):
        clock = {"t": 1000.0}
        self.market.on_call = lambda: clock.__setitem__("t", clock["t"] + 6.0)
        progress: dict = {}
        ticks = 0
        while True:
            ticks += 1
            clock["t"] += 60.0
            fetched = book.fetch(self.market, self.cols, DAY, progress=progress, now=lambda: clock["t"])
            if fetched is not None:
                break
            self.assertLess(ticks, 5)
        self.assertEqual(ticks, 2, "12 s a chunk: two chunks in the first tick, the third in the next")
        self.assertEqual(len(self.market.calls), 6, "no chunk was asked twice")
        np.testing.assert_array_equal(fetched.raw, self.fetched(self.cols).raw)
        self.assertEqual(fetched.meta["seconds"], 36.0)

    def test_a_call_that_fails_is_asked_again_from_its_own_chunk(self):
        progress: dict = {}
        self.market.fail_at = 4
        with self.assertRaises(RuntimeError):
            book.fetch(self.market, self.cols, DAY, progress=progress)
        self.assertEqual(progress["next"], 39)
        fetched = book.fetch(self.market, self.cols, DAY, progress=progress)
        self.assertEqual([len(c[0]) for c in self.market.calls], [39, 39, 39, 39, 39, 39, 24, 24])
        self.assertFalse(np.isnan(fetched.raw[-1, :, 3]).any())

    def test_a_name_with_no_bar_is_nan_and_another_day_starts_over(self):
        gone = self.cols.symbols[40]
        self.market.absent = {(gone, DAY.isoformat()), (gone, PREV.isoformat())}
        progress: dict = {}
        fetched = book.fetch(self.market, self.cols, DAY, progress=progress)
        self.assertTrue(np.isnan(fetched.raw[-2:, 40]).all() and np.isnan(fetched.all[-2:, 40]).all())
        self.assertFalse(np.isnan(fetched.raw[-3, 40]).any())
        self.assertFalse(np.isnan(np.delete(fetched.raw, 40, axis=1)).any())
        again = book.fetch(self.market, self.cols, PREV, progress=progress)
        self.assertEqual(int(again.days[-1]), ES.ordinal(PREV))
        self.assertEqual(len(self.market.calls), 12)


class WhenAFetchMayBeDecidedOn(Case):
    """B13."""

    def setUp(self):
        super().setUp()
        self.cols = book.columns(self.root, "fam@1:r", DAY, held=())
        self.held = [lot(1, "N005")]

    def verdict(self, *absent, last_ask=False, lots=None):
        self.market.absent |= {(s, DAY.isoformat()) for s in absent}
        fetched = self.fetched(self.cols)
        return book.complete(fetched, self.cols, self.held if lots is None else lots, last_ask=last_ask)

    def test_every_bar_served(self):
        self.assertEqual(self.verdict(), (True, []))

    def test_spy_is_never_done_without(self):
        self.assertEqual(self.verdict("SPY"), (False, ["SPY"]))
        self.assertEqual(self.verdict("SPY", last_ask=True)[0], False)

    def test_two_names_that_are_not_held_do_not_block_a_rebalance(self):
        ok, missing = self.verdict("N001", "N002")
        self.assertTrue(ok)
        self.assertEqual(sorted(missing), ["N001", "N002"])

    def test_three_missing_names_wait_even_at_the_last_ask(self):
        self.assertFalse(self.verdict("N001", "N002", "N003")[0])
        self.assertFalse(self.verdict("N001", "N002", "N003", last_ask=True)[0])

    def test_a_held_name_waits_for_its_bar_until_the_last_ask(self):
        self.assertEqual(self.verdict("N005"), (False, ["N005"]))
        self.assertEqual(self.verdict("N005", last_ask=True), (True, ["N005"]),
                         "seventeen hours on it is read as the Gym reads no bar")

    def test_a_held_name_that_left_the_index_is_watched_too(self):
        self.universe.end("N005", DAY)
        self.cols = book.columns(self.root, "fam@1:r", DAY, held={"N005": "2026-10-06"})
        self.assertEqual(self.verdict("N005"), (False, ["N005"]))
        self.assertEqual(self.verdict("N005", lots=[lot(1, "N005", status=L.LOT_CLOSED, exit_day=DAY.isoformat())])[0],
                         True, "a lot closed today holds nothing")

    def test_a_name_with_no_bar_yesterday_is_not_missing_and_a_flat_bar_is_served(self):
        self.market.absent = {("N009", PREV.isoformat())}
        self.assertEqual(self.verdict("N009"), (True, []))
        fetched = self.fetched(self.cols)
        k = self.cols.symbols.index("N010")
        fetched.raw[-1, k] = [fetched.raw[-2, k, 3]] * 4 + [0.0]          # the vendor's flat bar of a halted name
        self.assertEqual(book.complete(fetched, self.cols, self.held)[1], [])

    def test_no_candidate_no_watch(self):
        self.universe.allowed = set(names(30)) - {"N001", "N002", "N003"}
        self.cols = book.columns(self.root, "fam@1:r", DAY, held=())
        self.assertEqual(self.verdict("N001", "N002", "N003"), (True, []))


class TheKeptFetch(Case):
    """B11."""

    def setUp(self):
        super().setUp()
        self.cols = book.columns(self.root, "fam@1:r", DAY, held=())
        self.got = self.fetched(self.cols)

    def test_kept_as_read_and_private(self):
        path = book.keep(self.root, DAY, self.got, self.cols.symbols)
        self.assertEqual(path, self.root / "live-bars" / "2026-10-13.npz")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        symbols, again = book.kept(self.root, DAY)
        self.assertEqual(symbols, self.cols.symbols)
        for name in ("days", "raw", "all"):
            np.testing.assert_array_equal(getattr(again, name), getattr(self.got, name))
        self.assertEqual(again.meta["fetched_at"], self.got.meta["fetched_at"])
        self.assertEqual(book.bars_sha(again, symbols), book.bars_sha(self.got, self.cols))
        self.assertIsNone(book.kept(self.root, PREV))
        self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_five_sessions_are_kept(self):
        day, days = DAY, []
        for _ in range(7):
            days.append(day)
            book.keep(self.root, day, self.got, self.cols.symbols)
            day = S.previous_session(day)
        kept = sorted(p.stem for p in (self.root / "live-bars").glob("*.npz"))
        self.assertEqual(kept, sorted(d.isoformat() for d in days[:book.KEEP_SESSIONS]))

    def test_a_file_that_cannot_be_read_is_no_file(self):
        path = book.keep(self.root, DAY, self.got, self.cols.symbols)
        path.write_bytes(b"not an archive")
        self.assertIsNone(book.kept(self.root, DAY))
        with self.assertRaises(ValueError):
            book.keep(self.root, DAY, self.got, self.cols.symbols[:-1])

    def test_the_sha_names_the_bars_a_decision_read(self):
        sha = book.bars_sha(self.got, self.cols)
        self.assertEqual(sha, book.bars_sha(self.fetched(self.cols), self.cols))
        self.market.absent = {("N004", DAY.isoformat())}
        absent = self.fetched(self.cols)
        self.assertEqual(book.bars_sha(absent, self.cols), book.bars_sha(self.fetched(self.cols), self.cols),
                         "a missing bar hashes the same on every read")
        self.assertNotEqual(book.bars_sha(absent, self.cols), sha)
        moved = book.Fetched(self.got.days, self.got.raw.copy(), self.got.all.copy(), self.got.meta)
        moved.all[5, 20, 1] += 0.01
        self.assertNotEqual(book.bars_sha(moved, self.cols), sha, "an adjusted price is in the as-of prices")
        self.assertNotEqual(book.bars_sha(self.got, self.cols.symbols[::-1]), sha)


class TheSameBars(Case):
    """B11's comparison, by E1's own verdict."""

    def setUp(self):
        super().setUp()
        self.cols = book.columns(self.root, "fam@1:r", DAY, held=())
        self.old = self.fetched(self.cols)

    def same(self, **over):
        return book.same(self.old, self.fetched(self.cols), self.cols, verdict=L._bars_verdict, **over)

    def test_the_same_read_is_the_same(self):
        self.assertEqual(self.same(), {"mismatch": [], "volume": [], "late": []})

    def test_a_volume_that_went_on_counting_is_a_note(self):
        self.market.volume_drift = 5000
        got = self.same()
        self.assertEqual(got["mismatch"], [])
        self.assertEqual(sorted(got["volume"]), sorted(self.cols.symbols))

    def test_a_price_that_differs_is_a_mismatch_by_e1s_verdict(self):
        self.market.moved = {("N003", "2026-09-15"): 7.77}
        asked = []

        def verdict(*args):
            asked.append(args[4])
            return L._bars_verdict(*args)

        got = book.same(self.old, self.fetched(self.cols), self.cols, verdict=verdict)
        self.assertEqual(got, {"mismatch": ["N003"], "volume": [], "late": []})
        self.assertEqual(asked, [DAY.isoformat()], "only a column whose prices differ is handed to it")

    def test_the_tolerance_is_e1s_own(self):
        again = self.fetched(self.cols)
        k = self.cols.symbols.index("N003")
        again.all[:, k, :] = np.round(again.all[:, k, :] * 0.5, 4)        # a later split restated the whole series
        self.assertEqual(book.same(self.old, again, self.cols, verdict=L._bars_verdict)["mismatch"], [],
                         "the as-of prices agree within the vendor's rounding: E1's rule says ok")
        self.assertEqual(book.same(self.old, again, self.cols, verdict=lambda *a: "mismatch")["mismatch"], ["N003"],
                         "the verdict is the caller's, never the adapter's")

    def test_a_bar_served_late_is_late_and_a_bar_withdrawn_is_a_mismatch(self):
        self.market.absent = {("N006", DAY.isoformat())}
        self.old = self.fetched(self.cols)
        self.market.absent = set()
        self.assertEqual(self.same(), {"mismatch": [], "volume": [], "late": ["N006"]})
        self.old = self.fetched(self.cols)
        self.market.absent = {("N006", DAY.isoformat())}
        self.assertEqual(self.same()["mismatch"], ["N006"])

    def test_a_name_with_no_bar_of_the_day_is_compared_at_its_last_bar(self):
        self.market.absent = {("N006", DAY.isoformat()), ("N007", DAY.isoformat())}
        self.old = self.fetched(self.cols)
        self.market.volume_drift = 9
        self.market.moved = {("N007", "2026-09-15"): 7.77}
        got = self.same()
        self.assertEqual(got["mismatch"], ["N007"])
        self.assertNotIn("N006", got["mismatch"] + got["late"])

    def test_another_window_is_all_mismatch(self):
        got = book.same(self.old, self.fetched(self.cols, PREV), self.cols, verdict=L._bars_verdict)
        self.assertEqual(got["mismatch"], list(self.cols.symbols))


class TheClassOfTheMonth(Case):
    """D4's class pairs, read from the fetch."""

    def setUp(self):
        super().setUp()
        Universe.make(self.root, ["GOOG", "GOOGL", "FOXA", *names(10)])
        self.cols = book.columns(self.root, "fam@1:r", DAY, held=())
        self.got = self.fetched(self.cols)
        self.g, self.gl = self.cols.symbols.index("GOOG"), self.cols.symbols.index("GOOGL")
        self.first = int(np.searchsorted(self.got.days, ES.ordinal(dt.date(2026, 10, 1))))

    def test_the_higher_median_dollar_volume_before_the_month_is_the_class(self):
        self.got.raw[:, self.g, 4], self.got.raw[:, self.gl, 4] = 1000.0, 5000.0
        self.got.raw[:, self.g, 3] = self.got.raw[:, self.gl, 3] = 100.0
        elig = book.eligible(self.cols, self.got, DAY)
        self.assertEqual((bool(elig[self.g]), bool(elig[self.gl])), (False, True))
        self.assertEqual(int(elig.sum()), int(self.cols.elig0.sum()) - 1, "one class a company; FOXA alone stays")
        self.assertTrue(self.cols.elig0[self.g], "the columns' own flags are not written")

    def test_the_month_keeps_its_choice_whatever_this_month_trades(self):
        self.got.raw[:, self.g, 3] = self.got.raw[:, self.gl, 3] = 100.0
        self.got.raw[:self.first, self.g, 4], self.got.raw[:self.first, self.gl, 4] = 9000.0, 5000.0
        self.got.raw[self.first:, self.g, 4], self.got.raw[self.first:, self.gl, 4] = 1.0, 9e9
        elig = book.eligible(self.cols, self.got, DAY)
        self.assertEqual((bool(elig[self.g]), bool(elig[self.gl])), (True, False))
        self.got.raw[:self.first - config.CLASS_SESSIONS, self.gl, 4] = 9e12     # older than the 63 sessions: unread
        self.assertTrue(book.eligible(self.cols, self.got, DAY)[self.g])

    def test_a_tie_goes_to_the_lower_aid(self):
        self.got.raw[:, self.g, 3:] = self.got.raw[:, self.gl, 3:] = 100.0
        elig = book.eligible(self.cols, self.got, DAY)
        self.assertEqual((bool(elig[self.g]), bool(elig[self.gl])), (True, False))
        self.assertLess(self.cols.aids[self.g], self.cols.aids[self.gl])


# ----------------------------------------------------------------------------------------------------- the decide's job
class TheJob(Case):
    def setUp(self):
        super().setUp()
        self.universe.end("N007", DAY)
        self.lots = [lot(1, "N005", mark="55"), lot(2, "N007", qty="3", entry="20")]
        self.closed = [lot(3, "N009", status=L.LOT_CLOSED, exit_day="2026-10-12", cash="4", reason="ineligible"),
                       lot(4, "N010", status=L.LOT_CLOSED, exit_day="2026-10-12", cash="-2", reason="program", tag="mine")]
        self.cols = book.columns(self.root, "fam@1:r", DAY, held={"N005": "2026-10-06", "N007": "2026-10-06"})
        self.got = self.fetched(self.cols)
        self.ids = book.slots(self.cols)

    def inputs(self, **over):
        args = dict(day=DAY, needs=NEEDS, lots=self.lots, closed=self.closed, rejects=["budget"], cash=D("390"),
                    equity=D("560"), budget=D("557.25"), params={"k": 5})
        return book.inputs(self.cols, self.got, **{**args, **over})

    def test_a_row_names_a_column_never_a_symbol(self):
        inp = self.inputs()
        self.assertEqual([p["col"] for p in inp.positions],
                         [self.cols.symbols.index("N005"), self.cols.symbols.index("N007")])
        self.assertEqual(inp.positions[0], {"lid": 1, "col": inp.positions[0]["col"], "qty": 2.0, "value": 110.0,
                                            "entry_value": 100.0, "held_sessions": 5, "at": "open", "tag": ""},
                         "the House's own tag of its intents (`TAG`) never reaches a program: the Gym's lots carry none")
        self.assertEqual(inp.positions[1]["value"], 60.0, "never marked: its entry price")
        self.assertEqual(inp.closed[0], {"lid": 3, "col": self.cols.symbols.index("N009"), "net_ret": 0.04,
                                         "held_sessions": 4, "reason": "house", "tag": "ineligible"})
        self.assertEqual((inp.closed[1]["reason"], inp.closed[1]["tag"], inp.closed[1]["net_ret"]),
                         ("program", "mine", -0.02))
        sold = self.inputs(closed=[lot(5, "N010", status=L.LOT_CLOSED, exit_day="2026-10-12", reason="program")])
        self.assertEqual(sold.closed[0]["tag"], "", "nor on a lot its own sale closed")
        self.assertEqual((inp.history, inp.max_names, inp.ref), (60, 8, 12))
        self.assertEqual((inp.cash, inp.equity, inp.budget, inp.rejects), (390.0, 560.0, 557.25, ("budget",)))
        self.assertEqual(inp.ids.tolist(), self.cols.ids.tolist())
        self.assertFalse(inp.elig0[self.cols.symbols.index("N007")])
        self.assertIs(inp.dither_key, self.cols.dither_key)

    def test_a_lot_with_no_column_is_the_houses_failure(self):
        with self.assertRaises(book.ColumnsRefused):
            self.inputs(lots=[lot(9, "ZZZZ")])
        self.assertEqual(len(self.inputs(closed=[lot(9, "ZZZZ", status=L.LOT_CLOSED, exit_day="2026-10-12")]).closed), 0)

    def test_the_child_cannot_be_asked_without_spy(self):
        self.market.absent = {("SPY", DAY.isoformat())}
        self.got = self.fetched(self.cols)
        with self.assertRaises(ValueError):
            self.inputs()

    def test_every_open_lot_is_marked_at_the_days_raw_close(self):
        marks = book.marks(self.got, self.cols, self.lots + self.closed, DAY)
        self.assertEqual(set(marks), {1, 2}, "a closed lot has no mark")
        for lid, symbol in ((1, "N005"), (2, "N007")):
            close = self.got.raw[-1, self.cols.symbols.index(symbol), 3]
            self.assertEqual(marks[lid], D(repr(float(close))))
            self.assertEqual(marks[lid], marks[lid].quantize(D("0.01")), "the tape's own cent")
        late = [lot(5, "N005", opened="2026-10-14")]
        self.assertEqual(book.marks(self.got, self.cols, late, DAY), {}, "never a lot bought since the close")
        self.market.absent = {("N005", DAY.isoformat())}
        self.assertEqual(set(book.marks(self.fetched(self.cols), self.cols, self.lots, DAY)), {2})
        self.assertEqual(book.marks(self.got, self.cols, self.lots, PREV), {}, "another day's fetch marks nothing")

    def test_the_childs_orders_become_e1_intents(self):
        answer = {"orders": [{"sell": 2, "at": "open"}, {"buy_id": str(self.ids["N011"]), "usd": "111.459", "at": "open"},
                             {"buy_id": self.ids["N012"], "usd": 111.45, "at": "close"},
                             {"buy_id": self.ids["N007"], "usd": "50", "at": "open"}, {"buy_id": 5, "usd": "50", "at": "open"},
                             {"sell": 77, "at": "open"}, {"buy_id": self.ids["N013"], "usd": "0", "at": "open"},
                             {"buy_id": self.ids["N014"], "usd": "20", "at": "noon"}, "junk", {"hold": True}],
                  "rejects": ["under the minimum order"]}
        self.assertEqual(book.intents(answer, self.cols, self.lots),
                         [{"sell": 2, "at": "open", "tag": "xs"}, {"buy": "N011", "usd": "111.45", "at": "open", "tag": "xs"},
                          {"buy": "N012", "usd": "111.45", "at": "close", "tag": "xs"}])
        left = book.skipped(answer, self.cols, self.lots)
        self.assertEqual(left[0], ["", "under the minimum order"])
        self.assertEqual([s for s, _ in left[1:]], ["N007", "", "", "N013", "", "", ""])
        self.assertEqual(book.intents({"hold": True}, self.cols, self.lots), [])
        many = {"orders": [{"buy_id": i, "usd": "20", "at": "open"} for i in self.cols.ids.tolist()] * 2}
        self.assertLessEqual(len(book.intents(many, self.cols, self.lots)), book.MAX_INTENTS)

    def test_a_target_is_kept_by_symbol_on_the_house(self):
        target = {str(self.ids["N012"]): 0.2, self.ids["N011"]: 0.125, 5: 0.2}
        self.assertEqual(book.target_pairs(target, self.cols), [["N011", 0.125], ["N012", 0.2]])
        self.assertEqual(book.target_pairs(None, self.cols), [])

    def row(self, **over):
        base = dict(instance="fam@1:r", family="fam", version=1, decided_day="2026-10-09", exec_day="2026-10-12",
                    at="open", called=True, targets=[["N005", 0.2], ["N011", 0.2], ["N012", 0.2]], standing=False,
                    intents=[{"buy": "N011", "usd": "111.45", "at": "open", "tag": "xs"}, {"sell": 2, "at": "open"}],
                    skipped=[["", "why"]], equity=D("557.25"), budget="557.25", cols=self.cols, ctx_sha="c" * 64,
                    bars_sha="b" * 64, fetch={"calls": 28, "seconds": 9.5, "symbols": 515, "missing": 0, "late": False,
                                              "sha": "u" * 64, "fetched_at": 1.0}, status="planned", why=None, now=5.0)
        return book.rebalance_row(**{**base, **over})

    def test_the_rebalance_row_is_the_tables(self):
        import sqlite3

        row = self.row()
        self.assertEqual(tuple(row), book.REBALANCE_COLUMNS)
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript(book.SCHEMA)
        db.execute(f"INSERT INTO eq_rebalances ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", tuple(row.values()))
        self.assertEqual((row["n_names"], row["n_sells"], row["n_buys"], row["n_skipped"], row["called"], row["standing"]),
                         (3, 1, 1, 1, 1, 0))
        self.assertEqual((row["equity"], row["budget"], row["extra"]), ("557.25", "557.25", '["N007"]'))
        self.assertNotIn("fetched_at", row["fetch"])
        with self.assertRaises(ValueError):
            self.row(status="done")
        self.assertEqual(self.row(cols=None, equity=None, status="failed", why="x" * 900)["extra"], "[]")
        self.assertEqual(len(self.row(why="x" * 900)["why"]), 400)

    def test_the_event_holds_counts_and_verdicts_only(self):
        event = book.event(self.row())
        self.assertEqual(event, {"instance": "fam@1:r", "day": "2026-10-09", "exec_day": "2026-10-12", "at": "open",
                                 "called": True, "standing": False, "names": 3, "sells": 1, "buys": 1, "skipped": 1,
                                 "status": "planned"})
        self.assertFalse([s for s in self.cols.symbols if s in repr(event)])


class TheStandingTarget(Case):
    """D10 (4), the parent's half."""

    def setUp(self):
        super().setUp()
        self.cols = book.columns(self.root, "fam@1:r", DAY, held=())
        self.ids = book.slots(self.cols)
        self.rows = [self.row("2026-10-02", [["N001", 0.2]]),
                     self.row("2026-10-09", [["N005", 0.2], ["N011", 0.2], ["N012", 0.25]], at="close"),
                     self.row("2026-10-12", [["N020", 0.2]], called=0, standing=1)]
        self.lots = [lot(1, "N005")]

    @staticmethod
    def row(day, targets, *, called=1, status="planned", standing=0, at="open", ctx_sha="c" * 64):
        import json

        return {"decided_day": day, "called": called, "status": status, "standing": standing, "at": at,
                "targets": json.dumps(targets), "ctx_sha": ctx_sha}

    def standing(self, **over):
        return book.standing(self.rows, self.cols, self.lots, DAY, **over)

    def test_the_last_called_planned_row_stands(self):
        got = self.standing()
        self.assertEqual(got, {"target": {self.ids["N005"]: 0.2, self.ids["N011"]: 0.2, self.ids["N012"]: 0.25},
                               "at": "close", "exited": []})

    def test_a_hold_a_failure_and_a_late_decide_leave_it_standing(self):
        for status in ("hold", "failed", "late"):
            self.rows.append(self.row("2026-10-12", [["N029", 0.2]], status=status))
            self.assertEqual(set(self.standing()["target"]), {self.ids[s] for s in ("N005", "N011", "N012")}, status)
            self.rows.pop()

    def test_a_target_made_on_bars_that_did_not_hold_never_stands(self):
        self.rows.append({**self.row("2026-10-12", [["N029", 0.2]]), "audit": "mismatch"})
        self.assertNotIn(self.ids["N029"], self.standing()["target"])
        self.rows[-1]["audit"] = "ok"
        self.assertEqual(set(self.standing()["target"]), {self.ids["N029"]})

    def test_a_later_target_replaces_it_and_an_empty_one_stands_for_cash(self):
        self.rows.append(self.row("2026-10-12", [["N029", 0.2]]))
        self.assertEqual(set(self.standing()["target"]), {self.ids["N029"]})
        self.rows[-1] = self.row("2026-10-12", [])
        self.assertIsNone(self.standing())

    def test_todays_own_row_never_stands_for_today(self):
        self.rows.append(self.row(DAY.isoformat(), [["N029", 0.2]]))
        self.assertNotIn(self.ids["N029"], self.standing()["target"])

    def test_nothing_stands_when_every_name_is_held_or_working(self):
        self.lots = [lot(1, "N005"), lot(2, "N011"), lot(3, "N012")]
        self.assertIsNone(self.standing())
        self.lots = [lot(1, "N005"), lot(2, "N011")]
        self.assertIsNone(self.standing(pending=["N012"]), "a buy still working is not planned twice")
        got = book.standing(self.rows, self.cols, [lot(1, "N005")], DAY, pending=["N012"])
        self.assertEqual(set(got["target"]), {self.ids["N005"], self.ids["N011"]})
        self.assertIsNone(book.standing([], self.cols, self.lots, DAY))

    def test_a_name_the_house_exited_since_is_not_bought_back(self):
        self.lots = [lot(1, "N005"), lot(2, "N011", status=L.LOT_CLOSED, exit_day="2026-10-12", reason="max_hold"),
                     lot(3, "N012", status=L.LOT_CLOSED, exit_day="2026-10-09", reason="ineligible")]
        got = self.standing()
        self.assertEqual(got["exited"], [self.ids["N011"]], "N012 was exited before the target was set: it may return")
        self.lots[2] = lot(3, "N012", status=L.LOT_CLOSED, exit_day="2026-10-12", reason="program")
        self.assertEqual(self.standing()["exited"], [self.ids["N011"]], "the program's own sale is no House exit")
        self.lots = [lot(1, "N005"), lot(2, "N011", status=L.LOT_CLOSED, exit_day="2026-10-12", reason="ineligible"),
                     lot(3, "N012", status=L.LOT_CLOSED, exit_day="2026-10-12", reason="house")]
        self.assertIsNone(self.standing(), "held or exited: nothing left to buy")

    def test_a_name_with_no_column_today_is_left_out(self):
        self.rows[1] = self.row("2026-10-09", [["GONE", 0.2], ["N011", 0.2]])
        self.assertEqual(set(self.standing()["target"]), {self.ids["N011"]})

    def test_the_last_call_is_the_last_day_the_program_saw_a_ctx(self):
        self.assertEqual(book.last_called(self.rows), "2026-10-09")
        self.rows.append(self.row("2026-10-12", [], status="failed", ctx_sha=None))
        self.assertEqual(book.last_called(self.rows), "2026-10-09", "the House could not ask: nothing was seen")
        self.assertEqual(book.last_called(self.rows, before="2026-10-09"), "2026-10-02")
        self.assertEqual(book.last_called([]), "")


# ------------------------------------------------------------------------------------------------------------- X8
class TheSaltNeverLeaves(Case):
    """Seal X8, the live side: nothing the adapter sends, records or publishes holds the House salt, an aid, an
    aid-to-id map or a symbol of a panel run; the dither key reaches the child and nothing a program reads."""

    def setUp(self):
        super().setUp()
        self.universe.end("N007", DAY)
        self.cols = book.columns(self.root, "fam@1:r", DAY, held={"N007": "2026-10-06"})
        self.got = self.fetched(self.cols)
        self.lots = [lot(1, "N005"), lot(2, "N007")]
        self.job = book.inputs(self.cols, self.got, day=DAY, needs=NEEDS, lots=self.lots, closed=[], rejects=[],
                               cash=1.0, equity=2.0, budget=3.0, params={})
        self.key = run_salt(SALT, "fam@1:r")

    def strings(self, value, out=None):
        out = [] if out is None else out
        if isinstance(value, (str, bytes)):
            out.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                self.strings(v, out)
        elif isinstance(value, (list, tuple)):
            for v in value:
                self.strings(v, out)
        elif hasattr(value, "__dataclass_fields__"):
            for name in value.__dataclass_fields__:
                self.strings(getattr(value, name), out)
        return out

    def test_the_decider_payload_holds_no_name_no_aid_and_no_salt(self):
        payload = {"jobs": [{"key": "fam@1:r", "inputs": self.job, "called": False,
                             "standing": book.standing([TheStandingTarget.row("2026-10-09", [["N011", 0.2]])],
                                                       self.cols, self.lots, DAY)}]}
        blob = pickle.dumps(payload)
        for secret in (SALT, self.key):
            self.assertNotIn(secret, blob)
        for symbol in self.cols.symbols:
            self.assertNotIn(symbol.encode(), blob, symbol)
        texts = self.strings(payload["jobs"][0]["inputs"]) + self.strings(payload["jobs"][0]["standing"])
        self.assertEqual({t for t in texts if isinstance(t, str)}, {"open", ""},
                         "the only words in a job are a fill point and a lot's tag (the Gym's: none on a held lot)")
        self.assertEqual([t for t in texts if isinstance(t, bytes)], [self.cols.dither_key])
        ints = {a.tobytes() for a in vars(self.job).values() if isinstance(a, np.ndarray) and a.dtype.kind == "i"}
        self.assertNotIn(self.cols.aids.tobytes(), ints)
        self.assertNotIn(self.cols.aids[12:].tobytes(), ints)
        self.assertEqual([f for f in X.Inputs.__dataclass_fields__ if "aid" in f or "symbol" in f or "salt" in f], [])

    def test_the_dither_key_reaches_the_child_and_no_program(self):
        self.assertEqual(self.job.dither_key, hashlib.sha256(self.key + b"|dither|").digest())
        self.assertNotIn("dither_key", X.XsCtx.__slots__)
        self.assertFalse([s for s in X.XsCtx.__slots__ if "salt" in s or "aid" in s or "symbol" in s or "date" in s])

    def test_what_is_recorded_and_published_holds_no_id_and_no_secret(self):
        ids = book.slots(self.cols)
        answer = {"orders": [{"sell": 2, "at": "open"}, {"buy_id": ids["N011"], "usd": "111", "at": "open"}],
                  "target": {str(ids["N011"]): 0.2, str(ids["N005"]): 0.2}}
        intents = book.intents(answer, self.cols, self.lots)
        row = book.rebalance_row(instance="fam@1:r", family="fam", version=1, decided_day=DAY.isoformat(),
                                 exec_day="2026-10-14", at="open", called=True,
                                 targets=book.target_pairs(answer["target"], self.cols), standing=False, intents=intents,
                                 skipped=book.skipped(answer, self.cols, self.lots), equity=1, budget=1, cols=self.cols,
                                 ctx_sha="c" * 64, bars_sha=book.bars_sha(self.got, self.cols),
                                 fetch={**self.got.meta, "sha": "u" * 64}, status="planned", why=None, now=1.0)
        told = repr((row, intents, book.event(row))).encode()
        for value in (ids["N011"], ids["N005"], ids["N007"]):
            self.assertNotIn(str(value).encode(), told, "an id is a run's secret name: the House records the symbol")
        for secret in (SALT, self.key, self.cols.dither_key, SALT.hex().encode(), self.key.hex().encode(),
                       self.cols.dither_key.hex().encode()):
            self.assertNotIn(secret, told)
        self.assertFalse([s for s in self.cols.symbols if s in repr(book.event(row))], "an event names no symbol")

    def test_the_kept_file_is_bars_and_symbols_only(self):
        path = book.keep(self.root, DAY, self.got, self.cols.symbols)
        blob = path.read_bytes()
        for secret in (SALT, self.key, self.cols.dither_key, self.cols.ids.tobytes(), self.cols.aids[12:].tobytes()):
            self.assertNotIn(secret, blob)
        with np.load(path, allow_pickle=False) as data:
            self.assertEqual(sorted(data.files), ["all", "days", "fetched_at", "raw", "symbols"])

    def test_the_fetch_asks_the_venue_for_symbols_and_days_only(self):
        for call in self.market.calls:
            self.assertEqual(len(call), 4)
            self.assertFalse(set(call[0]) - set(self.cols.symbols))
        self.assertNotIn(SALT.hex(), repr(self.market.calls))


# ------------------------------------------------------------------------------------------------------------ X15
def closed(lid, symbol, exit_day, cash, *, notional="100", opened="2026-10-06", probe=True):
    return lot(lid, symbol, qty="1", entry=notional, opened=opened, status=L.LOT_CLOSED, exit_day=exit_day, cash=cash,
               reason="program", probe=probe, closed_at=float(lid))


class TheRecordByCloseDate(unittest.TestCase):
    """E4-SPEC 10.5: one observation a close date."""

    def setUp(self):
        self.lots = [closed(1, "AAA", "2026-10-13", "2"), closed(2, "BBB", "2026-10-13", "-1"),
                     closed(3, "CCC", "2026-10-13", "4", notional="200", probe=False),
                     closed(4, "DDD", "2026-10-20", "-3", notional="150", opened="2026-10-13"),
                     closed(5, "EEE", "2026-10-20", "-3", notional="150", opened="2026-10-13", probe=False),
                     closed(6, "FFF", "2026-10-20", "1", opened="2026-10-13", probe=False),
                     lot(7, "GGG")]
        self.twins = {"eq:1": {"status": "priced", "gap_bp": -10.0}, "eq:2": {"status": "priced", "gap_bp": 2},
                      "eq:3": {"status": "no_bar", "gap_bp": -500.0}, "eq:4": {"status": "priced", "gap_bp": float("nan")},
                      "eq:5": {"status": "priced", "gap_bp": True}, "eq:6": None}

    def test_the_golden_six_lots_on_two_dates(self):
        rec = book.date_record(self.lots, self.twins, None)
        self.assertEqual(rec["dates"], ("2026-10-13", "2026-10-20"))
        self.assertEqual(rec["n"], 2)
        self.assertEqual(rec["returns"], (0.0125, -0.0125), "5 / 400 and -5 / 400: summed cash over summed notional")
        self.assertEqual(rec["twin_gaps_bp"], (-4.0,), "(100 x -10 + 100 x 2) / 200; a date with no priced twin gives none")
        self.assertEqual((rec["pnl"], rec["realized_net"]), (D("0"), D("-2")))
        self.assertIsNone(rec["bh_pnl"], "no SPY series: not read before sizing up needs it")
        by_row = book.date_record([x.row() for x in self.lots], self.twins, None)
        self.assertEqual(by_row, rec, "a lot's row reads as the lot")

    def test_an_open_lot_and_a_lot_with_no_notional_are_no_observation(self):
        self.assertEqual(book.date_record([lot(7, "GGG")], {}, None)["n"], 0)
        zero = closed(8, "HHH", "2026-10-21", "0", notional="0")
        self.assertEqual(book.date_record(self.lots + [zero], self.twins, None)["n"], 2)

    def test_the_buy_and_hold_is_spy_on_one_basis_across_a_dividend(self):
        # ONE fetch after the dividend: every close before the ex-date (the 13th) is restated, to the vendor's cent.
        spy = {"2026-10-05": D("498.51"), "2026-10-12": D("501.50"), "2026-10-13": D("505.00"), "2026-10-20": D("510.05")}
        rec = book.date_record(self.lots, self.twins, spy)
        by_hand = D("400") * (D("505.00") / D("498.51") - 1) + D("400") * (D("510.05") / D("501.50") - 1)
        self.assertEqual(rec["bh_pnl"], by_hand)
        self.assertEqual(rec["bh_pnl"].quantize(D("0.0001")), D("12.0271"))
        raw_only = D("400") * (D("505.00") / D("500.00") - 1)
        self.assertGreater(by_hand - D("400") * (D("510.05") / D("501.50") - 1), raw_only,
                           "the raw close before the ex-date would lose the dividend")
        self.assertIsNone(book.date_record(self.lots, self.twins, {**spy, "2026-10-12": None})["bh_pnl"])
        del spy["2026-10-20"]
        self.assertIsNone(book.date_record(self.lots, self.twins, spy)["bh_pnl"], "a missing close prices nothing")
        self.assertEqual(book.date_record([], {}, spy)["bh_pnl"], D("0"))

    def test_the_one_fetch_and_its_span(self):
        self.assertEqual(book.spy_span(self.lots), (dt.date(2026, 10, 5), dt.date(2026, 10, 20)))
        self.assertIsNone(book.spy_span([lot(7, "GGG")]))
        market = Market()
        closes = book.spy_closes(market, *book.spy_span(self.lots))
        self.assertEqual(market.calls, [(("SPY",), "2026-10-05", "2026-10-21", "all")], "ONE fetch, adjustment=all")
        self.assertEqual(len(closes), 12)
        self.assertTrue(all(isinstance(v, D) for v in closes.values()))
        self.assertIsNotNone(book.date_record(self.lots, self.twins, closes)["bh_pnl"])
        market.fail_at = 2
        self.assertEqual(book.spy_closes(market, dt.date(2026, 10, 5), dt.date(2026, 10, 20)), {})

    def test_the_date_clustered_t(self):
        self.assertIsNone(book.date_t([0.01]))
        self.assertIsNone(book.date_t([0.01, 0.01, 0.01]), "no spread: no t")
        values = [0.02, -0.01, 0.03, 0.0]
        mean = math.fsum(values) / 4
        sd = math.sqrt(math.fsum((v - mean) ** 2 for v in values) / 3)
        self.assertEqual(book.date_t(values), mean / sd * 2.0)

    def test_the_cost_is_said_in_words(self):
        text = book.cost_sentence(min_dates=10, loss_usd="-300", sleeve_usd="557.25")
        for part in ("10th close date", "10 weeks", "10 months", "-$300", "54% of its $557.25 sleeve",
                     "a backstop, not a tight leash", "kill switch"):
            self.assertIn(part, text)
        self.assertNotIn("%", book.cost_sentence(min_dates=10, loss_usd="-300"))


class TheLiveRulesAreByDate(unittest.TestCase):
    """Seal X15. E4-SPEC 10.5's three scenarios on E1's OWN `edm1` and `sized_up`, unchanged: read by lot each rule
    fires on a basket; read by close date none does. And an ETF program's record is what E1 builds today."""

    def setUp(self):
        self.table = T.equity_table()

    def records(self, lots, twins=None, *, sd=None, spy=None, probe_sessions=30):
        """(by lot, as E1's `_record_of` reads a version's closes; by date, as the panel's is fed)."""
        twins = twins or {}
        gaps = tuple(float(twins[f"eq:{x.lid}"]["gap_bp"]) for x in lots if f"eq:{x.lid}" in twins)
        pnl = sum((x.cash for x in lots), D(0))
        by_lot = B.EquityRecord(n=len(lots), returns=tuple(float(x.cash / x.entry_notional) for x in lots), pnl=pnl,
                                bh_pnl=D("0"), probe_sessions=probe_sessions, realized_net=pnl, twin_gaps_bp=gaps,
                                validation_r_sd=sd)
        rec = book.date_record(lots, twins, spy)
        by_date = B.EquityRecord(n=rec["n"], returns=rec["returns"], pnl=rec["pnl"],
                                 bh_pnl=rec["bh_pnl"] if spy is not None else D("0"), probe_sessions=probe_sessions,
                                 realized_net=rec["realized_net"], twin_gaps_bp=rec["twin_gaps_bp"], validation_r_sd=sd)
        return by_lot, by_date

    def test_one_dates_fill_gap_is_not_five_twins(self):
        lots = [closed(k, f"N{k}", "2026-10-13", "0.50", notional="111.45") for k in range(1, 6)]
        twins = {f"eq:{k}": {"status": "priced", "gap_bp": -22.0} for k in range(1, 6)}
        by_lot, by_date = self.records(lots, twins)
        self.assertIn("below their replay twins", B.edm1(by_lot, self.table) or "")
        self.assertEqual(by_date.twin_gaps_bp, (-22.0,), "five copies of ONE date's fill gap are one gap")
        self.assertIsNone(B.edm1(by_date, self.table))

    def test_two_losing_months_are_two_observations_not_ten(self):
        lots = [closed(k, f"N{k}", "2026-10-30" if k <= 5 else "2026-11-30", "-3.34", notional="111.45",
                       opened="2026-10-01" if k <= 5 else "2026-11-02") for k in range(1, 11)]
        by_lot, by_date = self.records(lots, sd=0.04)
        self.assertEqual((by_lot.n, by_date.n), (10, 2))
        self.assertIn("EDM1: its 10 real closes", B.edm1(by_lot, self.table) or "", "demoted on the market's two months")
        self.assertIsNone(B.edm1(by_date, self.table), "ten lots on two dates are two observations: under min_trades")
        self.assertAlmostEqual(by_date.returns[0], -3.34 / 111.45, places=12)

    def test_four_dates_in_a_rally_do_not_size_up(self):
        lots = [closed(4 * w + k, f"N{k}", f"2026-10-{6 + 7 * w:02d}", str(D("1.5") + D("0.3") * k), notional="111.45",
                       opened="2026-09-25") for w in range(4) for k in range(1, 6)]
        by_lot, by_date = self.records(lots)
        up, why = B.sized_up(by_lot, self.table)
        self.assertTrue(up, why)
        self.assertEqual((by_lot.n, by_date.n), (20, 4))
        up, why = B.sized_up(by_date, self.table)
        self.assertFalse(up)
        self.assertIn("4 real closes, under the 20 sizing up needs", why)
        self.assertEqual(by_lot.pnl, by_date.pnl, "dollars are dollars either way")

    def test_the_loss_line_counts_lots_in_dollars_either_way(self):
        lots = [closed(k, f"N{k}", "2026-10-13", "-61", notional="111.45") for k in range(1, 6)]
        by_lot, by_date = self.records(lots)
        for record in (by_lot, by_date):
            self.assertIn("program loss line", B.edm1(record, self.table) or "")

    def test_an_etf_instances_record_is_what_e1_builds_today(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            h = T.Harness(Path(tmp), rows=[T.family_row()])
            self.addCleanup(h.state.close)
            key = L.instance_key("seed-overnight-spy", 1)
            lots = [L.Lot(k, key, "seed-overnight-spy", 1, "beta", "SPY", "etf", qty=D(0), opened_qty=D(1),
                          entry_px=D("600"), entry_notional=D("600"), entry_at="close", opened_at=float(k),
                          opened_day="2026-10-12", status=L.LOT_CLOSED, exit_px=D("601"), exit_at="open",
                          exit_day="2026-10-13", closed_at=100.0 + k, cash=D(cash), probe=True)
                    for k, cash in ((1, "1.50"), (2, "-0.75"), (3, "3.00"))]
            for x in lots:
                h.book._save_lot(x)
            h.families.twin_rows = {"eq:1": {"status": "priced", "gap_bp": -3.0}, "eq:3": {"status": "priced", "gap_bp": 1.0}}
            with mock.patch.object(type(h.families), "twins", lambda self: self.twin_rows, create=True):
                record = h.book._record_of("seed-overnight-spy", 1, {**T.family_row(), "validation_r_sd": 0.011})
            self.assertEqual(record, B.EquityRecord(
                n=3, returns=(1.5 / 600, -0.75 / 600, 3.0 / 600), pnl=D("3.75"), bh_pnl=None, probe_sessions=0,
                realized_net=D("3.75"), twin_gaps_bp=(-3.0, 1.0), validation_r_sd=0.011),
                "three lots closed on ONE date are three observations for an ETF program, as E1 reads them")


class TheCaptainsA17(unittest.TestCase):
    def test_a_hold_days_failure_counts_toward_no_exit(self):
        self.assertIs(book.HOLD_DAY_FAILS_EXIT, False)
        self.assertEqual((book.KIND, book.TAG, book.INELIGIBLE, book.LABEL), ("panel", "xs", "ineligible", "EQUITY (PANEL)"))
        self.assertEqual(book.MAX_INTENTS, config.MAX_ORDERS)
        self.assertEqual(book.INSTANCE_KIND_COLUMN, "kind")


if __name__ == "__main__":
    unittest.main()
