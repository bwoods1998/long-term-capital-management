"""Release E2.1, THE START CHECK of the equity Train bar (league/swarm/elane_train.py `start_check`): a program's
decisions must not depend on when its run started. Each Train span is run again from 61 and 127 decision sessions in
(every run starting flat) and a later run's orders are held to the run from the span's first session: once it has
warmed up, and before that wherever the two runs show the same book.

Three layers, as the restart check's tests: the rule on invented ctx streams (what is compared, what matches, the two
shares a later run must reach, what stops the check); the bar on the fakes (the record, the brief, START as the
program's fault and never the mechanism's, the House's failures, a pass judged before the check existed, the cost in
runs); and E1's own runner, engine, ctx builder and decider over synthetic stores (the programs that must pass, the
profit lock in the spellings the static rule cannot see, the clocks, the sizes, a child killed mid-check, the seconds
it takes). Every family, program, market and number here is invented."""

from __future__ import annotations

import datetime as dt
import json
import re
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest import mock

from league.swarm import elane, elane_train
from league.swarm.elane_train import (BAR, TRAIN_SPANS, StartCheckInterrupted, StartRun, later_runs, may_validate,
                                      same_book, start_check, start_orders, start_plan, start_text, with_start)
from league.tests import elane_e2_fakes as fx
from league.tests.test_elane_e2_review import STATE_KEPT, WEIGHT_LOCK
from league.tests.test_elane_e2_train import ResearchCase

E1 = callable(getattr(elane, "next_try", None)) and callable(getattr(elane, "reviewed", None))
FIRST = TRAIN_SPANS[0][0]
SHIFTS = tuple(BAR["start_shifts"])


# ----------------------------------------------------------------------------------------------------------- the plan
class ThePlan(unittest.TestCase):
    def test_the_rules_are_the_bars_constants(self):
        self.assertEqual((SHIFTS, BAR["start_warm"], BAR["start_min"], BAR["start_match"], BAR["start_active"],
                          BAR["start_sized"]), ((61, 127), 20, 120, 0.99, 0.95, 0))
        for shift in SHIFTS:  # two different primes: no clock's period divides both
            self.assertTrue(all(shift % p for p in range(2, shift)), shift)
        self.assertNotEqual(*SHIFTS)

    def test_the_warm_up_is_the_longer_of_history_and_the_maximum_hold_and_twenty_more(self):
        self.assertEqual(start_plan(1005, 2, 2)["warm"], 22)
        self.assertEqual(start_plan(1005, 2, 60)["warm"], 80)
        self.assertEqual(start_plan(1005, 252, 20)["warm"], 272)

    def test_a_span_too_short_for_a_shift_goes_without_it_and_says_so(self):
        plan = start_plan(300, 30, 3)
        self.assertEqual((plan["warm"], plan["shifts"], plan["skipped"]), (50, [61, 127], []))
        plan = start_plan(300, 60, 3)  # 300 - 127 - 80 = 93 warmed-up sessions: under the 120 a shift needs
        self.assertEqual((plan["warm"], plan["shifts"]), (80, [61]))
        self.assertEqual([s["shift"] for s in plan["skipped"]], [127])
        self.assertIn("leaves 93 sessions after its warm-up of 80; 120 are needed", plan["skipped"][0]["why"])
        plan = start_plan(300, 200, 3)
        self.assertEqual((plan["shifts"], [s["shift"] for s in plan["skipped"]]), ([], [61, 127]))
        self.assertEqual(start_plan(61 + 22 + 120, 2, 2)["shifts"], [61], "exactly enough for the first shift")
        self.assertEqual(start_plan(61 + 22 + 119, 2, 2)["shifts"], [])

    def test_on_the_train_spans_the_first_shift_fits_every_program_the_contract_allows(self):
        """The Train spans have 1,006 and 753 sessions (E1's calendar): 1,005 decision sessions where the store has no
        session before the span (2016), 753 where it has (2022)."""
        from league.equity import config
        from league.equity.store import nyse_sessions

        sessions = [len(nyse_sessions(first, last)) for first, last in TRAIN_SPANS]
        self.assertEqual(sessions, [1006, 753])
        decisions = (sessions[0] - 1, sessions[1])
        worst = (config.MAX_HISTORY, config.MAX_HOLD_CAP)
        self.assertEqual([start_plan(n, *worst)["shifts"] for n in decisions], [[61, 127], [61]],
                         "the longest look-back the contract allows: the 127-session start does not fit 2022-24")
        self.assertEqual(start_plan(decisions[1], 486, 60)["shifts"], [61, 127])
        self.assertEqual(start_plan(decisions[1], 487, 60)["shifts"], [61])
        for history in (0, 2, 63, 252):
            self.assertEqual([start_plan(n, history, 20)["shifts"] for n in decisions], [[61, 127], [61, 127]])


# ----------------------------------------------------------------------------------------------------------- what matches
class WhatMatches(unittest.TestCase):
    LOTS = {"positions": [{"id": 7, "symbol": "SPY"}, {"id": 9, "symbol": "QQQ"}]}

    def test_an_order_is_its_kind_symbol_fill_point_and_size_never_its_tag(self):
        orders = start_orders([{"sell": 9, "at": "open", "tag": "exit-1"},
                               {"buy": "SPY", "share": 0.5, "at": "close", "tag": "f0.001234"},
                               {"buy": "IWM", "usd": 250.0}, {"cancel": 3}], self.LOTS)
        self.assertEqual(orders, [{"sell": "QQQ", "at": "open"}, {"buy": "SPY", "at": "close", "share": 0.5},
                                  {"buy": "IWM", "at": "open", "usd": 250.0}, {"cancel": True}])

    def test_a_sell_names_its_lots_symbol_for_two_runs_number_their_lots_apart(self):
        mine = start_orders([{"sell": 7, "at": "open"}], self.LOTS)
        yours = start_orders([{"sell": 412, "at": "open"}], {"positions": [{"id": 412, "symbol": "SPY"}]})
        self.assertEqual(mine, yours)
        self.assertEqual(elane_train.same_intents(mine, yours), (True, None))
        other = start_orders([{"sell": 9, "at": "open"}], self.LOTS)
        self.assertEqual(elane_train.same_intents(mine, other), (False, None), "another symbol's lot")
        unheld = start_orders([{"sell": 99, "at": "open"}], self.LOTS)
        self.assertEqual(unheld, [{"sell": "a lot it does not hold", "at": "open"}])
        self.assertEqual(elane_train.same_intents(mine, unheld), (False, None))

    def test_sizes_agree_within_the_restart_checks_tolerance(self):
        def buy(**size: Any) -> list:
            return start_orders([{"buy": "SPY", "at": "close", **size}], {})
        self.assertEqual(elane_train.same_intents(buy(share=0.5), buy(share=0.5 + 4e-7)), (True, None))
        same, gaps = elane_train.same_intents(buy(share=0.5), buy(share=0.02))
        self.assertEqual((same, round(gaps["share"], 6)), (False, 0.48))
        self.assertEqual(elane_train.same_intents(buy(usd=400.08), buy(usd=400.085)), (True, None))
        same, gaps = elane_train.same_intents(buy(usd=400.08), buy(usd=398.44))
        self.assertEqual((same, round(gaps["usd"], 2)), (False, 1.64))
        self.assertEqual(elane_train.same_intents(buy(share=0.5), buy(usd=500.0)), (False, None), "a share against dollars")

    def test_what_two_runs_asked_is_told_in_a_closed_vocabulary(self):
        """A record and a brief say what the two runs asked where they first differed. A program chooses its symbols'
        text, its sizes and its tags, and it reads the reserve's bars as look-back: only an order's kind, a symbol of
        the run's own NEEDS, the two fill points and a size to two significant digits are ever said."""
        inputs = {"symbols": ["SPY", "QQQ"], "positions": [{"id": 7, "symbol": "SPY"}]}
        orders = start_orders([{"sell": 7, "at": "open", "tag": "close 2021-12-31 was 475.31"},
                               {"buy": "QQQ", "share": 0.123456, "at": "close"},
                               {"buy": "THE CLOSE WAS 475.31", "usd": 475.31, "at": "next week"},
                               {"sell": 99}, {"cancel": 4}], inputs)
        text = elane_train._orders_text(orders, inputs)
        self.assertEqual(text, "sell SPY at the open; buy QQQ 0.12 of the sleeve at the close; buy a symbol outside its "
                               "NEEDS about $480; and 2 more")
        self.assertNotIn("475", text)
        self.assertEqual(elane_train._orders_text(orders[3:], inputs), "sell a lot it does not hold at the open; "
                                                                       "cancel an order")
        self.assertEqual(elane_train._orders_text([], inputs), "nothing")
        self.assertEqual(elane_train._orders_text(start_orders([{"buy": "SPY", "usd": 1234.56}], inputs), inputs),
                         "buy SPY about $1,200 at the open")

    def test_the_same_book_is_the_lots_the_house_shows_less_what_the_runs_standing_sets(self):
        def book(**change: Any) -> dict:
            lot = {"id": 3, "symbol": "SPY", "class": "etf", "qty": 1.25, "entry": 400.04, "mark": 402.5, "value": 503.13,
                   "pnl": 3.08, "held_sessions": 2, "at": "close", "tag": "f"}
            shut = {"id": 2, "symbol": "SPY", "qty": 1.25, "entry": 398.0, "exit": 399.5, "net": 1.86, "held_sessions": 1,
                    "reason": "program", "tag": "f"}
            lot.update({k[4:]: v for k, v in change.items() if k.startswith("lot_")})
            shut.update({k[5:]: v for k, v in change.items() if k.startswith("shut_")})
            return {"positions": [lot], "closed": [shut], "orders": []}
        base = book()
        # What a run's own standing sets: ids, quantities, dollars, and the program's own words.
        for own in ({"lot_id": 77}, {"lot_qty": 0.05}, {"lot_value": 20.13}, {"lot_pnl": 0.12}, {"lot_tag": "s0.031"},
                    {"shut_id": 76}, {"shut_qty": 0.05}, {"shut_net": 0.07}, {"shut_tag": "s"}):
            self.assertTrue(same_book(base, book(**own)), own)
        # What the House shows of the market and the lot itself.
        for other in ({"lot_symbol": "QQQ"}, {"lot_held_sessions": 3}, {"lot_entry": 401.0}, {"lot_mark": 402.6},
                      {"lot_at": "open"}, {"shut_reason": "max_hold"}, {"shut_exit": 399.6}, {"shut_held_sessions": 2}):
            self.assertFalse(same_book(base, book(**other)), other)
        self.assertFalse(same_book(base, {"positions": [], "closed": base["closed"], "orders": []}))
        self.assertFalse(same_book(base, {"positions": base["positions"], "closed": [], "orders": []}))
        self.assertTrue(same_book({"positions": [], "closed": [], "orders": []}, {"positions": (), "closed": ()}))


# ----------------------------------------------------------------------------------------------------------- the rule
#: An invented program that does what its ctx's `flag` says (the invented stream sets it a run and a session), so a
#: test places each difference between two runs exactly. Its tags differ from run to run on every session.
FLAGGED = '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}
PARAMS = {"share": 0.5}


def decide(ctx):
    flag = ctx.flag
    if flag == "raise":
        raise ValueError("an invented failure")
    if flag == "quiet":
        return []
    out = [{"sell": lot["id"], "at": "open", "tag": "lot %d" % lot["id"]} for lot in ctx.positions]
    if flag == "sells":
        return out
    buy = {"buy": "SPY", "share": ctx.params["share"], "at": "close", "tag": "age %d" % ctx.age}
    if flag == "small":
        buy["share"] = 0.02
    elif flag == "near":
        buy["share"] = ctx.params["share"] + 4e-07
    elif flag == "usd":
        buy = {"buy": "SPY", "usd": 500.0, "at": "close"}
    elif flag == "open":
        buy["at"] = "open"
    elif flag == "other":
        buy["buy"] = "QQQ"
    elif flag == "first":
        return [buy] + out
    out.append(buy)
    return out
'''
SESSIONS = 300
#: Every differing session on record (a record names a later run's first `START_MISSES` only).
ALL_MISSES = mock.patch.object(elane_train, "START_MISSES", 10_000)


def invented(offset: int, *, flags: Callable[[int, int, int], str] | None = None,
             lots: Callable[[int, int, int], bool] | None = None, sessions: int = SESSIONS, history: int = 2,
             max_hold: int = 2, days: int | None = None) -> StartRun:
    """One run of an invented span as the start check reads it: its first decision `offset` sessions into the span,
    `sessions` the span's decision sessions. `flags(i, age, offset)` is what the program is told at span session `i`
    (the run's own `age` sessions after its first decision); `lots(i, age, offset)` whether the run holds a lot then
    (default: every odd session, whatever the run), or the lot's entry price when it is a number (another lot than the
    other runs hold). A lot's id is counted from the run's start."""
    def stream() -> Any:
        for i in range(offset, sessions):
            age = i - offset
            held = lots(i, age, offset) if lots is not None else bool(i % 2)
            entry = float(held) if isinstance(held, float) else 100.0 + i
            lot = {"id": 1 + age, "symbol": "SPY", "class": "etf", "qty": 1.0, "entry": entry, "mark": 101.0 + i,
                   "value": 101.0 + i, "pnl": 1.0, "held_sessions": 1, "at": "close", "tag": f"run {offset}"}
            yield {"symbols": ["SPY"], "positions": [lot] if held else [], "orders": [], "closed": [], "rejects": [],
                   "cash": 500.0, "equity": 1000.0 + age, "budget": 1000.0, "caps": {"SPY": 500.0}, "age": age,
                   "flag": flags(i, age, offset) if flags is not None else ""}
    count = sessions - offset if days is None else days
    return StartRun([FIRST + dt.timedelta(days=offset + k) for k in range(count)], stream(), history, max_hold)


def span(**kw: Any) -> dict[str, Any]:
    """An invented span's three runs for `start_check`: from its first session, and from each shift."""
    return {"base": invented(0, **kw), "later": [(shift, invented(shift, **kw)) for shift in SHIFTS], "skipped": []}


class TheRule(unittest.TestCase):
    """`start_check` on invented streams through the fakes' decider kinds: with a warm-up of 22 (the program's NEEDS)
    the run started 61 sessions into the 300 has 239 decisions, 217 of them warmed up, and the one started 127 in has
    173 and 151."""

    def check(self, *spans: dict, code: str = FLAGGED) -> dict:
        self.decider = fx.FakeDecider()
        out = start_check(self.decider, code, {}, name="p", spans=list(spans))
        self.assertEqual(self.decider.instances, {}, "every instance dropped")
        return out

    def rows(self, out: dict) -> list:
        return [(r["span"], r["shift"], r["sessions"], r["early"], r["matched"], r["held"]) for r in out["runs"]]

    def test_a_program_that_decides_alike_matches_everywhere_and_the_record_says_what_was_compared(self):
        out = self.check(span())
        self.assertEqual(self.rows(out), [(0, 61, 239, 22, 239, True), (0, 127, 173, 22, 173, True)])
        self.assertEqual((out["sessions"], out["matched"], out["share"], out["held"], out["first_miss"]),
                         (412, 412, 1.0, True, None))
        self.assertEqual((out["need"], out["active_need"], out["warm"], out["shifts"], out["skipped"]),
                         (0.99, 0.95, 22, [61, 127], []))
        self.assertEqual((out["active"], out["active_matched"], out["active_share"]), (412, 412, 1.0),
                         "this program asks an order on every session")
        self.assertEqual((out["disqualified"], out["failed"], out["sized"], out["resized"], out["size_gap"]),
                         (0, 0, 0, 0, {}))
        # One instance a run, loaded once and never reset: each decided on every session of its own run.
        self.assertEqual(self.decider.loads, ["e2-start:p:0:a", "e2-start:p:0:s61", "e2-start:p:0:s127"])
        self.assertEqual(self.decider.decides, 300 + 239 + 173)
        # The tags differed on every session and the lots' ids on every session a lot was held: neither is compared.

    def test_two_spans_are_two_sets_of_runs(self):
        out = self.check(span(), span())
        self.assertEqual([(r[0], r[1]) for r in self.rows(out)], [(0, 61), (0, 127), (1, 61), (1, 127)])
        self.assertEqual(out["sessions"], 824)
        self.assertEqual(self.decider.loads[3:], ["e2-start:p:1:a", "e2-start:p:1:s61", "e2-start:p:1:s127"])

    def test_before_its_warm_up_ends_a_later_run_is_compared_only_where_the_book_is_the_same(self):
        """The run from the span's start holds a lot on every odd session; a later run holds none in its own first ten
        sessions. There the two books differ on the odd sessions (run A holds a lot the fresh run does not) and are
        the same on the even ones (both hold none); from the later run's tenth session on they are the same."""
        def lots(i: int, age: int, offset: int) -> bool:
            return bool(i % 2) and (offset == 0 or age >= 10)
        out = self.check(span(lots=lots))
        self.assertEqual(self.rows(out), [(0, 61, 234, 17, 234, True), (0, 127, 168, 17, 168, True)],
                         "five of each run's first ten sessions are left out: the books differ")
        # What the fresh run asks where the books differ is its own business: it is not held to run A there.
        def differs_where_books_do(i: int, age: int, offset: int) -> str:
            return "small" if offset and age < 10 and i % 2 else ""
        out = self.check(span(lots=lots, flags=differs_where_books_do))
        self.assertEqual((out["held"], out["matched"], out["sessions"]), (True, 402, 402))
        # Where the books are the same it is held to run A from its first decision, warm-up or not.
        def differs_where_books_agree(i: int, age: int, offset: int) -> str:
            return "small" if offset and age < 10 and not i % 2 else ""
        out = self.check(span(lots=lots, flags=differs_where_books_agree))
        self.assertEqual(self.rows(out), [(0, 61, 234, 17, 229, False), (0, 127, 168, 17, 163, False)])
        self.assertEqual(out["runs"][0]["misses"], [1, 3, 5, 7, 9], "counted from the later run's own first decision")

    def test_once_warmed_up_every_session_is_compared_whatever_the_books(self):
        """A later run whose book never agrees with run A's (a hold counted from its own start) is not compared before
        its warm-up ends, and on every session after it."""
        def lots(i: int, age: int, offset: int) -> bool:
            return bool(age % 2)  # a lot on every other session of the run's OWN age: 61 and 127 are odd
        def flags(i: int, age: int, offset: int) -> str:
            return "" if age % 2 else "quiet"
        out = self.check(span(lots=lots, flags=flags))
        self.assertEqual(self.rows(out), [(0, 61, 217, 0, 0, False), (0, 127, 151, 0, 0, False)])
        self.assertEqual(out["runs"][0]["misses"], [22, 23, 24, 25, 26, 27],
                         "its first warmed-up sessions (a record names six, and counts the rest)")
        self.assertEqual(elane_train.START_MISSES, 6)
        self.assertEqual(out["first_miss"], {"span": 0, "shift": 61, "session": 22, "what": "orders",
                                             "base": "sell SPY at the open; buy SPY 0.5 of the sleeve at the close",
                                             "later": "nothing"})

    def test_every_later_run_must_reach_the_share_and_the_lowest_is_the_one_read(self):
        def at(*ages: int) -> Callable[[int, int, int], str]:  # another fill point: other orders
            return lambda i, age, offset: "open" if offset == 61 and age in ages else ""
        out = self.check(span(flags=at(30, 40)))
        self.assertEqual(self.rows(out), [(0, 61, 239, 22, 237, True), (0, 127, 173, 22, 173, True)])
        self.assertEqual((out["held"], out["share"], out["sized"], out["resized"]), (True, 0.9916, 0, 0),
                         "two of 239 sessions: inside the 1%")
        self.assertEqual(out["first_miss"]["session"], 30, "what differed is on record even when the run holds")
        out = self.check(span(flags=at(30, 40, 50)))
        self.assertEqual(self.rows(out), [(0, 61, 239, 22, 236, False), (0, 127, 173, 22, 173, True)])
        self.assertEqual((out["held"], out["share"], out["matched"], out["sessions"]), (False, 0.9874, 409, 412),
                         "three of 239 is over 1% of that run, though all the runs together match 99.3%")
        self.assertEqual(out["first_miss"], {"span": 0, "shift": 61, "session": 30, "what": "orders",
                                             "base": "sell SPY at the open; buy SPY 0.5 of the sleeve at the close",
                                             "later": "sell SPY at the open; buy SPY 0.5 of the sleeve at the open"})
        self.assertEqual(out["runs"][0]["misses"], [30, 40, 50])

    def test_the_same_lots_and_the_same_orders_in_another_size_are_never_allowed(self):
        """ONE session on which a later run shows the same book as the run from the span's start, asks the same orders
        and asks another size fails it, however high its shares: with the same bars, calendar, lots and orders, the
        size was taken from how the run stands."""
        once = span(flags=lambda i, age, offset: "small" if offset == 61 and age == 40 else "")
        out = self.check(once)
        row = out["runs"][0]
        self.assertEqual((row["matched"], row["share"], row["active_share"]), (238, 0.9958, 0.9958), "inside both shares")
        self.assertEqual((row["sized"], row["resized"], row["held"], out["held"]), (1, 1, False, False))
        self.assertEqual((out["resized"], out["size_gap"], out["first_miss"]["what"]), (1, {"share": 0.48}, "size"))
        self.assertIn("on 1 of them the two runs held the same lots too, and no such session is allowed",
                      start_text({"start": out}))
        with mock.patch.dict(BAR, {"start_sized": 1}):
            self.assertTrue(self.check(span(flags=lambda i, age, offset: "small" if offset == 61 and age == 40 else ""))
                            ["held"], "the rule is one constant")
        # Where the two runs hold OTHER lots (after the warm-up every session is compared, whatever the books), a
        # size that differs is one differing session like any other: inside the shares it is allowed.
        def other_lot(i: int, age: int, offset: int) -> Any:
            return 55.5 if offset == 61 and age == 40 else bool(i % 2)
        out = self.check(span(flags=lambda i, age, offset: "small" if offset == 61 and age == 40 else "", lots=other_lot))
        row = out["runs"][0]
        self.assertEqual((row["sized"], row["resized"], row["matched"], row["held"]), (1, 0, 238, True))

    def test_a_program_that_asks_on_few_sessions_is_read_on_those_too(self):
        """A program that trades one session in twenty: the run started 61 sessions in asks an order on 11 of its 239
        sessions. Two of them differing are 0.8% of its sessions and 18% of its trades."""
        def sparse(*differ: int) -> Callable[[int, int, int], str]:
            def flags(i: int, age: int, offset: int) -> str:
                if i % 20:
                    return "quiet"
                return "open" if offset == 61 and i in differ else ""  # another fill point: other orders
            return flags
        out = self.check(span(flags=sparse()))
        self.assertEqual((out["held"], out["sessions"], out["active"], out["active_matched"]), (True, 412, 19, 19))
        out = self.check(span(flags=sparse(100, 120)))
        row = out["runs"][0]
        self.assertEqual((row["sessions"], row["matched"], row["share"]), (239, 237, 0.9916))
        self.assertEqual((row["active"], row["active_matched"], row["active_share"], row["held"]), (11, 9, 0.8182, False))
        self.assertEqual((out["held"], out["share"], out["active_share"]), (False, 0.9916, 0.8182))
        # The share of ALL sessions alone would have passed it (the rule the active share was added to).
        with mock.patch.dict(BAR, {"start_active": 0.0}):
            self.assertTrue(self.check(span(flags=sparse(100, 120)))["held"])

    def test_what_differs_and_what_does_not(self):
        told = {30: "near", 32: "usd", 34: "open", 36: "other", 38: "first", 40: "sells", 42: "raise", 44: "quiet",
                46: "small"}
        with ALL_MISSES:
            out = self.check(span(flags=lambda i, age, offset: told.get(age, "") if offset == 61 else ""))
        row = out["runs"][0]
        self.assertEqual(row["misses"], [32, 34, 36, 38, 40, 42, 44, 46],
                         "a size within the tolerance is the same size; the rest are other orders")
        self.assertEqual((row["failed"], row["sized"], row["resized"], row["disqualified"]), (1, 1, 1, 0))
        self.assertEqual(out["first_miss"]["what"], "orders")
        self.assertEqual(out["first_miss"]["later"], "sell SPY at the open; buy SPY about $500 at the close")
        # 38 is an even age of the run started on an odd session: a lot is held, so the order of the orders shows.

    def test_a_decide_that_fails_in_both_runs_alike_is_a_match(self):
        out = self.check(span(flags=lambda i, age, offset: "raise" if i in (150, 200) else ""))
        self.assertEqual((out["held"], out["matched"], out["failed"]), (True, 412, 0))
        out = self.check(span(flags=lambda i, age, offset: "raise" if i == 150 and offset == 0 else ""))
        self.assertEqual((out["failed"], [r["matched"] for r in out["runs"]]), (2, [238, 172]),
                         "run A's failure is no match for either later run")
        self.assertEqual(out["first_miss"]["what"], "failed")

    def test_a_disqualified_instance_matches_nothing(self):
        with mock.patch.object(elane_train, "DECIDE_MAX_ERRORS", 3):
            out = self.check(span(flags=lambda i, age, offset: "raise" if offset == 61 and age >= 30 else ""))
        row = out["runs"][0]
        self.assertEqual((row["failed"], row["disqualified"], row["matched"], row["held"]), (2, 207, 30, False))
        self.assertEqual(out["runs"][1]["matched"], 173, "the other later run is its own instance")

    def test_a_later_run_that_does_not_share_its_spans_sessions_stops_the_check(self):
        good = span()
        cases = {
            "it starts on another session than its shift": {**good, "later": [(61, invented(62))]},
            "its sessions are not the span's": {**good, "later": [(61, StartRun(
                [FIRST + dt.timedelta(days=61 + 2 * k) for k in range(239)], invented(61).inputs, 2, 2))]},
            "it ends before the span does": {**good, "later": [(61, invented(61, sessions=SESSIONS - 1))]},
            "its ctx stream is shorter than its sessions": {**good, "later": [(61, invented(61, sessions=250, days=239))]},
            "its ctx stream is longer than its sessions": {**good, "later": [(61, invented(61, sessions=301, days=239))]},
            "the base run's stream is shorter than its sessions": {**good, "base": invented(0, sessions=280, days=300)},
            "the base run's stream is longer than its sessions": {**good, "base": invented(0, sessions=310, days=300)},
            "too few warmed-up sessions": {"base": invented(0, history=60), "later": [(127, invented(127, history=60))]},
            "a shift of nothing": {**good, "later": [(0, invented(0))]},
        }
        for name, row in cases.items():
            with self.subTest(name):
                decider = fx.FakeDecider()
                with self.assertRaises(StartCheckInterrupted):
                    start_check(decider, FLAGGED, {}, name="p", spans=[{**span(), **row}])
                self.assertEqual(decider.instances, {}, "every instance dropped")

    def test_no_later_run_at_all_is_never_a_pass(self):
        skipped = [{"shift": s, "why": "an invented reason"} for s in SHIFTS]
        for spans in ([], [{"base": invented(0), "later": [], "skipped": skipped}]):
            decider = fx.FakeDecider()
            with self.assertRaisesRegex(StartCheckInterrupted, "no Train span is long enough"):
                start_check(decider, FLAGGED, {}, name="p", spans=spans)
            self.assertEqual((decider.loads, decider.instances), ([], {}))
        # A span that fits nothing beside one that does: the check runs on the one, and says what was left out.
        out = self.check({"base": invented(0), "later": [], "skipped": skipped}, span())
        self.assertEqual(([(r["span"], r["shift"]) for r in out["runs"]], out["held"]), ([(1, 61), (1, 127)], True))
        self.assertEqual(out["skipped"], [{"span": 0, **s} for s in skipped])
        verdict = with_start({"passed": True, "fails": []}, {"sessions": 0, "matched": 0, "held": True})
        self.assertEqual((verdict["passed"], verdict["fails"]), (False, ["START"]), "a check of nothing holds nothing")

    def test_a_child_that_restarts_reloads_or_cannot_be_counted_stops_the_check(self):
        """NEVER A SILENT PASS, the restart check's reader: a restart the decider counted, an instance it reloaded
        without counting one (run A then has fresh memory too), and an answer without its call or error count."""
        def broken(change: Callable[[fx.FakeDecider], None], words: str) -> None:
            decider = fx.FakeDecider()
            change(decider)
            with self.assertRaisesRegex(StartCheckInterrupted, words):
                start_check(decider, FLAGGED, {}, name="p", spans=[span()])
            self.assertEqual(decider.instances, {}, "every instance dropped")
        broken(lambda d: setattr(d, "restart_after", 200), "restarted during the start check")
        broken(lambda d: setattr(d, "reload_after", 200), "reloaded an instance during the start check")
        broken(lambda d: setattr(d, "counts", False), "no call count")
        broken(lambda d: setattr(d, "counts_errors", False), "no error count")
        self.assertTrue(issubclass(StartCheckInterrupted, elane_train.StateCheckInterrupted),
                        "the House's, handled as the restart check's interruption is")
        # A child that fails a decide passes through as the decider's own error (judged as a run's failure is).
        decider = fx.FakeDecider()
        decider.fails = fx.DeciderError("the decider exited")
        with self.assertRaises(fx.DeciderError):
            start_check(decider, FLAGGED, {}, name="p", spans=[span()])
        self.assertEqual(decider.instances, {})


# ----------------------------------------------------------------------------------------------------------- the bar on the fakes
#: A profit lock, invented, in the plainest spelling (the static rule refuses this one; the fakes' stream stands for the
#: spellings it cannot see, which E1's engine runs below): a token size once the run is 3% ahead of its capital. On the
#: fakes' start stream a run is that far ahead 60 sessions after ITS start.
LOCK = '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}
PARAMS = {"share": 0.5, "lock": 0.03, "small": 0.02}


def decide(ctx):
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
    ahead = ctx.equity / ctx.budget - 1.0
    share = ctx.params["small"] if ahead >= ctx.params["lock"] else ctx.params["share"]
    out.append({"buy": "SPY", "share": share, "at": "close"})
    return out
'''
#: The restart check's decides on the fakes (two instances, 45 sessions, two spans) and the start check's (three runs
#: of 300, 239 and 173 decisions, two spans).
STATE_DECIDES = 2 * 2 * fx.STATE_SESSIONS
START_DECIDES = 2 * (300 + 239 + 173)


class TheBarOnTheFakes(ResearchCase):
    def alerts(self) -> list:
        return [e["payload"]["action"] for e in self.store.events_after(0)
                if e["kind"] == "swarm.status" and e["payload"].get("alert")]

    def test_a_passing_version_carries_its_start_check(self):
        fam = fx.e2_family(self.store, "blind", code=fx.program(share=0.27))
        out = self.researcher.run()
        self.assertEqual((out["steps"][0]["passed"], out["steps"][0]["review"]["review"]), (True, "pass"))
        v1 = self.rec(fam["id"])["versions"]["1"]
        start = v1["start"]
        self.assertEqual((start["sessions"], start["matched"], start["share"], start["first_miss"]), (824, 824, 1.0, None))
        self.assertEqual((start["need"], start["active_need"], start["warm"], start["shifts"], start["skipped"]),
                         (0.99, 0.95, 22, [61, 127], []))
        self.assertEqual([(r["span"], r["shift"], r["sessions"], r["matched"], r["held"]) for r in start["runs"]],
                         [(0, 61, 239, 239, True), (0, 127, 173, 173, True), (1, 61, 239, 239, True),
                          (1, 127, 173, 173, True)])
        self.assertEqual(sorted(start), sorted(elane_train.START_KEYS))
        self.assertIn("state", v1, "the restart check's counts stay beside it")
        text = elane_train.version_text(1, v1)
        self.assertIn("Start check: run again from 61 and 127 sessions into each Train span (every run starts flat), its "
                      "orders matched the run from the span's start on 824 of 824 compared sessions", text)
        self.assertNotIn("never from how the run stands", text, "a passing version needs no advice")
        self.assertTrue(may_validate(self.store, self.store.family(fam["id"]), 1))

    def test_the_later_runs_start_the_session_after_the_base_runs_decision_and_end_with_the_span(self):
        fx.e2_family(self.store, "runs", code=fx.program(share=0.26))
        self.researcher.run()
        later = self.runner.later_calls()
        # The fakes' sessions are consecutive days from a span's first; its first decision is at its first session.
        self.assertEqual([(c["start"], c["end"], c["k"]) for c in later],
                         [(first + dt.timedelta(days=shift + 1), last, 1.0) for first, last in TRAIN_SPANS
                          for shift in SHIFTS])
        self.assertEqual(self.store.runs("runs", window="train").__len__(), 4, "the later runs are stored as no run")
        self.assertEqual(sorted(r["stress"] for r in self.store.runs("runs", window="train")), [1.0, 1.0, 1.5, 1.5])

    def test_the_cost_in_runs_and_decides_of_a_version_that_reaches_the_check(self):
        """THE COST, stated: a version that meets Y1-R1 and STATE is run four more times (two later starts a span, at
        1.0x) and decided again on every session of each of its six runs. One that fails the bar before costs none."""
        fx.e2_family(self.store, "cost", code=fx.program(share=0.25))
        self.researcher.run()
        self.assertEqual((len(self.runner.base_calls()), len(self.runner.later_calls())), (4, 4))
        self.assertEqual(self.runner.decider.decides, STATE_DECIDES + START_DECIDES)
        self.assertEqual(self.runner.decider.instances, {})
        failing = fx.program("QQQ", share=0.24)
        self.failing(failing)
        runner = fx.FakeRunner(self.runner.answer)
        fx.e2_family(self.store, "fails-p1", code=failing, symbols=("QQQ",))
        elane_train.EquityResearcher(self.store, self.router, self.settings, runner=runner, clock=self.clock).run()
        self.assertEqual((len(runner.calls), runner.decider.decides), (4, 0), "no check for a version the bar failed")
        # One that fails STATE never reaches the start check either.
        runner = fx.FakeRunner(self.runner.answer)
        fx.e2_family(self.store, "counter", code=fx.COUNTER, symbols=("IWM",))
        elane_train.EquityResearcher(self.store, self.router, self.settings, runner=runner, clock=self.clock).run()
        self.assertEqual(self.rec("counter")["versions"]["1"]["fails"], ["STATE"])
        self.assertEqual((len(runner.calls), runner.decider.decides), (4, STATE_DECIDES))
        self.assertNotIn("start", self.rec("counter")["versions"]["1"])

    def test_a_profit_lock_fails_start_and_its_author_is_told_which_sessions_and_why(self):
        fam = fx.e2_family(self.store, "locks", code=LOCK)
        fid = fam["id"]
        out = self.researcher.run()
        step = out["steps"][0]
        self.assertEqual((step["passed"], step["fails"]), (False, ["START"]), step)
        rec = self.rec(fid)
        v1 = rec["versions"]["1"]
        self.assertEqual((v1["passed"], v1["fails"], rec.get("passed_version"), rec["status"]),
                         (False, ["START"], None, "researching"))
        # Each later run is unlocked for its own first 60 sessions while the run from the span's start is locked.
        self.assertEqual([(r["span"], r["shift"], r["sessions"], r["matched"], r["held"]) for r in v1["start"]["runs"]],
                         [(0, 61, 239, 179, False), (0, 127, 173, 113, False), (1, 61, 239, 179, False),
                          (1, 127, 173, 113, False)])
        self.assertEqual((v1["start"]["share"], v1["start"]["sized"], v1["start"]["resized"], v1["start"]["size_gap"]),
                         (round(113 / 173, 4), 240, 240, {"share": 0.48}))
        self.assertEqual(v1["start"]["first_miss"],
                         {"span": 0, "shift": 61, "session": 0, "what": "size",
                          "base": "sell SPY at the open; buy SPY 0.02 of the sleeve at the close",
                          "later": "sell SPY at the open; buy SPY 0.5 of the sleeve at the close"})
        self.assertEqual(v1["start"]["runs"][0]["misses"], list(range(elane_train.START_MISSES)))
        # It met the rest of the bar: its Train figures and its restart check stay on record, and its runs are stored.
        self.assertEqual((v1["state"]["matched"], v1["active_years"]), (v1["state"]["sessions"], 7))
        self.assertGreater(v1["pnl_15"], 0)
        self.assertEqual(len(self.store.runs(fid, window="train")), 4)
        # The program's fault, like STATE: no review is asked, no Validation try is spent, nothing is said of the
        # mechanism.
        self.assertEqual([c for c in self.router.calls if fx.is_review(c)], [])
        self.assertFalse(may_validate(self.store, self.store.family(fid), 1))
        self.assertFalse(elane_train.tried(self.store, fid, 1))
        self.assertEqual(elane_train.judged(rec), 0)
        self.assertNotIn("START", elane_train.JUDGED)
        self.assertIsNotNone(self.store.get(elane_train.TRAIN_OK_KEY), "the child judged a program through")
        # What its author reads next.
        brief = " ".join(self.researcher.brief(self.store.family(fid)).split())
        self.assertIn("v1: met Y1, Y2, P1, R1 and STATE but failed START.", brief)
        self.assertIn("(START) run again from later starts (61 and 127 sessions into a Train span", brief)
        self.assertIn("the lowest of the 4 later runs matched 65.3% of its sessions (99.0% needed of each)", brief)
        self.assertIn("the run started 61 sessions into span 1 matched 179 of 239 (179 of 239 with an order) and "
                      "differed on its sessions 1, 2, 3, 4, 5, 6 and 54 more", brief)
        self.assertIn("2 more later runs fell short too", brief)
        self.assertIn("(sessions are counted from a later run's own first decision)", brief)
        self.assertIn("first differed (its session 1), the two runs asked the same orders in different sizes: the run "
                      "from the span's start asked [sell SPY at the open; buy SPY 0.02 of the sleeve at the close], the "
                      "later run asked [sell SPY at the open; buy SPY 0.5 of the sleeve at the close].", brief)
        self.assertIn("only a buy's size differed (by at most 0.48 of the sleeve); on 240 of them the two runs held the "
                      "same lots too, and no such session is allowed", brief)
        self.assertIn("NEVER from how the run stands: not ctx.equity, ctx.cash or ctx.caps", brief)
        self.assertIn("decide from ctx's bars, its calendar fields and each lot's own facts", brief)
        # A record of counts, sessions counted from a run's own start and the program's own orders: never a day.
        self.assertNotRegex(json.dumps(v1["start"]), r"\b(19|20)\d\d\b")
        # Its revision keeps nothing of the run's standing and passes.
        self.answers.append(self.program_answer(fx.program(share=0.23)))
        self.researcher.run()
        rec = self.rec(fid)
        self.assertEqual((rec["passed_version"], rec["status"], rec["versions"]["2"]["start"]["share"]), (2, "passed", 1.0))

    def test_a_family_whose_versions_only_failed_start_is_stalled_never_refuted(self):
        self.settings["elane"]["e2"]["train_budget"] = 1
        fam = fx.e2_family(self.store, "only-start", code=LOCK)
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["retired"], {"family": fam["id"], "stalled": ["START"]})
        rec = self.rec(fam["id"])
        self.assertEqual((rec["status"], rec["stalled"]["codes"]), ("stalled", ["START"]))
        self.assertEqual(self.store._all("SELECT family FROM graveyard"), [], "no graveyard row: nothing said of the idea")
        row = elane_train.train_map(self.store)[0]
        self.assertEqual((row["scored"], row["passed"], row["refuted"], row["stalled"]), (1, 0, 0, 1))
        self.assertEqual(elane_train.closed_cells(self.store, self.settings), [])

    def test_a_clock_counted_from_the_runs_first_decision_fails_and_two_primes_leave_no_period_in_phase(self):
        """The restart check fails a session counter kept in STATE before the start check sees it; the start check on
        its own refuses it too, whatever its period: a clock of 7 is out of phase with both later runs, and one of 61
        sessions, in phase with the run started 61 in, is out of phase with the one started 127 in."""
        def check(code: str) -> dict:
            runner = fx.FakeRunner()
            runs = [runner.train(code, {}, name="p", start=first, end=last) for first, last in TRAIN_SPANS]
            return start_check(runner.decider, code, {}, name="p",
                               spans=later_runs(runner, code, {}, name="p", runs=runs))
        out = check(fx.counter(7))
        self.assertEqual(([r["held"] for r in out["runs"]], out["held"]), ([False] * 4, False))
        out = check(fx.counter(61))
        self.assertEqual([(r["shift"], r["matched"] == r["sessions"], r["held"]) for r in out["runs"]],
                         [(61, True, True), (127, False, False)] * 2)
        self.assertFalse(out["held"])
        out = check(fx.counter(127))
        self.assertEqual([r["held"] for r in out["runs"]], [False, True] * 2)
        self.assertTrue(check(fx.CACHE)["held"], "a cache of what ctx gives again is no clock")

    def test_a_shift_that_does_not_fit_is_left_out_and_said(self):
        code = fx.program(share=0.22).replace('"history": 2', '"history": 60')  # a warm-up of 80: 127 does not fit 300
        fam = fx.e2_family(self.store, "long-look", code=code)
        out = self.researcher.run()
        self.assertTrue(out["steps"][0]["passed"], out)
        start = self.rec(fam["id"])["versions"]["1"]["start"]
        self.assertEqual((start["warm"], [(r["span"], r["shift"]) for r in start["runs"]]), (80, [(0, 61), (1, 61)]))
        self.assertEqual([(s["span"], s["shift"]) for s in start["skipped"]], [(0, 127), (1, 127)])
        self.assertEqual(len(self.runner.later_calls()), 2)
        self.assertIn("(2 later starts did not fit a span after the warm-up and were not run)",
                      start_text({"start": start}))
        # A program whose warm-up leaves no later start anywhere cannot be checked: never a pass.
        code = fx.program(share=0.21).replace('"history": 2', '"history": 200')
        fam = fx.e2_family(self.store, "longest-look", code=code, symbols=("QQQ",))
        out = self.researcher.run()
        step = next(s for s in out["steps"] if s["family"] == fam["id"])
        self.assertEqual(step.get("house"), "start", step)
        self.assertIn("no Train span is long enough for a later start", step["why"])
        self.assertEqual(self.rec(fam["id"])["versions"], {})

    def test_a_check_the_house_interrupts_is_not_scored_and_its_third_is_an_alert_once(self):
        """A child that restarts (or is reloaded) during the start check, after the restart check finished: the
        House's. Nothing is scored, no run is stored, no model is asked; the version is judged once the check can
        finish; the third unfinished check since it was last judged is an alert, sent once."""
        fam = fx.e2_family(self.store, "interrupted", code=fx.program(share=0.2))
        fid = fam["id"]
        decider = self.runner.decider
        words = {"restart_after": "restarted during the start check", "reload_after": "reloaded an instance during the "
                                                                                      "start check"}
        for n, knob in enumerate(("restart_after", "reload_after", "restart_after", "reload_after"), start=1):
            setattr(decider, knob, decider.decides + STATE_DECIDES + 100)  # past the restart check, inside this one
            out = self.researcher.run()
            step = out["steps"][0]
            self.assertEqual(step.get("house"), "start", step)
            self.assertIn(words[knob], step["why"])
            self.assertEqual(decider.instances, {}, "every instance dropped")
            self.assertEqual(self.alerts(), ["elane_train_start"] if n >= 3 else [])
            self.clock.advance(elane_train.BACKOFF_MAX)
        rec = self.rec(fid)
        self.assertEqual((rec["versions"], rec["infra"]["kind"], rec["infra"]["kinds"], rec["infra"]["alerted"]),
                         ({}, "start", {"start": 4}, ["start"]))
        self.assertEqual(self.store.runs(fid, window="train"), [], "no run stored for an unfinished verdict")
        self.assertEqual(self.writes(), [], "no model is asked to rewrite a program the House could not check")
        self.assertFalse(may_validate(self.store, self.store.family(fid), 1))
        self.assertIsNone(self.store.get(elane_train.TRAIN_OK_KEY), "an unfinished check proves no child sound")
        event = next(e for e in self.store.events_after(0) if e["payload"].get("action") == "elane_train_start")
        self.assertIn("start check (START) could not finish 3 times", event["payload"]["text"])
        self.researcher.run()
        rec = self.rec(fid)
        self.assertEqual((rec["passed_version"], "infra" in rec), (1, False), "judged once the check could finish")

    def test_a_child_that_fails_a_later_run_or_a_decide_is_judged_as_a_runs_failure(self):
        code = fx.program(share=0.19)
        fam = fx.e2_family(self.store, "later-fails", code=code)
        self.runner.later = lambda c, k: fx.RunFailed("the decider child failed the run: timed out")
        out = self.researcher.run()
        self.assertEqual(out["steps"][0].get("house"), "run", out)
        self.assertEqual((self.rec(fam["id"])["versions"], self.store.runs(fam["id"], window="train")), ({}, []))
        self.runner.later = None
        self.runner.decider.fails = None
        self.clock.advance(elane_train.BACKOFF_MAX)
        decider = self.runner.decider
        real = decider.kind

        def fails_in_the_start_check(kind: str, op: str, payload: Any, **kw: Any) -> dict:
            if any(str(job["key"]).startswith("e2-start:") for job in payload.get("jobs") or ()):
                raise fx.DeciderError("the decider did not answer in time; the child was killed")
            return real(kind, op, payload, **kw)
        with mock.patch.object(decider, "kind", fails_in_the_start_check):
            out = self.researcher.run()
        self.assertEqual(out["steps"][0].get("house"), "run", out)
        self.assertEqual(decider.instances, {})
        self.assertEqual(self.rec(fam["id"])["infra"]["kinds"], {"run": 2})
        self.clock.advance(elane_train.BACKOFF_MAX)
        self.researcher.run()
        self.assertEqual(self.rec(fam["id"])["passed_version"], 1)

    def test_a_later_run_that_is_no_result_or_leaves_its_span_stops_the_check(self):
        cases = {"ended no_data": fx.train_result(status="no_data"),
                 "carried a day outside its span": fx.train_result(by_year=fx.year_rows(years=(*fx.TRAIN_YEARS, 2021)))}
        for i, (words, result) in enumerate(cases.items()):
            with self.subTest(words):
                fam = fx.e2_family(self.store, f"later-{i}", code=fx.program(share=0.18 - i / 100),
                                   symbols=(("SPY",), ("QQQ",))[i], mechanism=f"Invented overnight idea number {i}.")
                runner = fx.FakeRunner()
                runner.later = lambda c, k, result=result: result
                researcher = elane_train.EquityResearcher(self.store, self.router, self.settings, runner=runner,
                                                          clock=self.clock)
                out = researcher.score(self.store.family(fam["id"]), self.store.version(fam["id"], 1))
                self.assertEqual(out.get("house"), "start", out)
                self.assertIn(words, out["why"])
                self.assertEqual((self.rec(fam["id"])["versions"], runner.decider.instances), ({}, {}))

    def test_a_pass_judged_before_the_check_existed_is_scored_again_before_its_try(self):
        """A verdict with no `start` record was judged before START was part of the bar: such a pass is not current
        until its version has had its Validation try, so E1's tournament does not validate it; the next round scores
        it again. Passed, it stands with its start check on record; failed, the pass is withdrawn."""
        ident = {"equity": "a" * 64, "engine": "equity-engine-1"}
        patcher = mock.patch("league.swarm.evaluator.equity_identity", lambda: dict(ident))
        patcher.start()
        self.addCleanup(patcher.stop)
        old = {"status": "passed", "passed_version": 1,
               "versions": {"1": {"passed": True, "fails": [], "score": 1.7, "identity": dict(ident),
                                  "state": {"sessions": 90, "matched": 90}}}}
        for slug, code, symbol in (("old-blind", fx.program(share=0.17), "SPY"), ("old-lock", LOCK, "QQQ")):
            fx.e2_family(self.store, slug, code=code, record=old, symbols=(symbol,),
                         mechanism=f"Invented idea {slug} judged before the start check.")
            fx.reviewed(self.store, slug)
            self.store.update_family(slug, best_version=1, best_train=1.7)
            fam = self.store.family(slug)
            self.assertFalse(elane_train.pass_current(self.store, fam), "no start check on record")
            self.assertFalse(may_validate(self.store, fam, 1))
        self.assertEqual(sorted(f["id"] for f in self.researcher.queue()), ["old-blind", "old-lock"])
        out = self.researcher.run()
        steps = {s["family"]: s for s in out["steps"]}
        self.assertEqual(steps["old-blind"]["rescored"], "kept")
        fam = self.store.family("old-blind")
        self.assertEqual(self.rec("old-blind")["versions"]["1"]["start"]["share"], 1.0)
        self.assertTrue(elane_train.pass_current(self.store, fam))
        self.assertTrue(may_validate(self.store, fam, 1), "its review stands: the program is the same")
        self.assertEqual((steps["old-lock"]["rescored"], steps["old-lock"]["fails"]), ("withdrawn", ["START"]))
        rec = self.rec("old-lock")
        self.assertEqual((rec["status"], rec["passed_version"], rec["versions"]["1"]["fails"]),
                         ("researching", None, ["START"]))
        self.assertIsNone(self.store.family("old-lock")["best_version"])
        self.assertFalse(may_validate(self.store, self.store.family("old-lock"), 1))
        # A pass whose version already had its try is E1's from there, start check or not.
        fx.e2_family(self.store, "old-tried", code=fx.program("IWM", share=0.16), record=old, symbols=("IWM",),
                     mechanism="Invented idea judged and tried before the start check.")
        self.store.add_run("old-tried", 1, {"run_id": "val-old", "status": "ok", "trials": 1, "summary": {}},
                           window="validation", stress=1.0, purpose="validation")
        self.assertTrue(elane_train.pass_current(self.store, self.store.family("old-tried")))
        self.assertEqual([f["id"] for f in self.researcher.queue()], ["old-lock"],
                         "the withdrawn pass researches again; the tried one and the kept one have no step")

    def test_the_bar_and_the_researchers_prompt_say_the_rule_before_a_program_is_written(self):
        text = " ".join(elane_train.bar_text().split())
        self.assertIn("(START) each Train span run again from 61 and 127 sessions in, every run starting flat, the "
                      "program's orders (each order's kind, symbol and fill point, each buy's size; tags apart) match the "
                      "run from the span's start on at least 99% of each later run's sessions (and on at least 95% of "
                      "those on which either run asked an order)", text)
        self.assertIn("20 sessions more) and before that wherever the two runs hold the same lots; and where the two "
                      "runs hold the same lots and ask the same orders, never in another size.", text)
        system = " ".join(elane_train.RESEARCHER_SYSTEM.split())
        for said in (text, system):
            self.assertIn("never from how", said.replace("NEVER", "never"))
            self.assertIn("max-hold exit", said)
            self.assertIn("constant share of the sleeve", said)
        self.assertNotRegex(text, r"\b20(20|21|25|26)\b")
        self.assertIn("THE START RULE (part of the bar)", system)
        self.assertIn("never differ in size alone while the two runs hold the same lots", system)
        self.assertIn("START", elane_train.FAILS)
        self.assertIn("its decisions depend on when its run started", elane_train.FAILS["START"])
        self.assertEqual(start_text({}), "")
        self.assertEqual(start_text({"start": {"sessions": 0}}), "")


# ----------------------------------------------------------------------------------------------------------- on E1's own code
#: A trend holder: long while the close is above its ten-session average, flat below it. The House sells its lot at the
#: maximum hold (5 sessions) and the program buys again at the next decision while the trend holds.
TREND = '''import math

NEEDS = {"symbols": ["SPY"], "history": 12, "max_hold_sessions": 5}
PARAMS = {"look": 10, "share": 0.5}


def decide(ctx):
    close = ctx.bars["SPY"].close
    look = ctx.params["look"]
    if len(close) <= look:
        return []
    up = float(close[-1]) > sum(float(x) for x in close[-look:]) / look
    if not up:
        return [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
    if not ctx.positions:
        return [{"buy": "SPY", "share": ctx.params["share"], "at": "open"}]
    return []
'''
#: A stop and a target on each lot's own return (mark over entry), entered after a down close.
STOP = '''import math

NEEDS = {"symbols": ["SPY"], "history": 3, "max_hold_sessions": 6}
PARAMS = {"share": 0.5, "stop": 0.01, "take": 0.015, "drop": 0.008}


def decide(ctx):
    out = []
    for lot in ctx.positions:
        own = lot["mark"] / lot["entry"] - 1.0
        if own <= -ctx.params["stop"] or own >= ctx.params["take"]:
            out.append({"sell": lot["id"], "at": "open"})
    close = ctx.bars["SPY"].close
    if not ctx.positions and len(close) > 1 and float(close[-1]) / float(close[-2]) - 1.0 <= -ctx.params["drop"]:
        out.append({"buy": "SPY", "share": ctx.params["share"], "at": "open"})
    return out
'''
#: A program that waits five sessions after its own last exit before it enters again (a count kept in STATE). A later
#: run starts with no wait behind it, so it may enter where the run from the span's start still waits: it differs on a
#: session or two and then trades as that run does.
WAIT = '''import math

NEEDS = {"symbols": ["SPY"], "history": 3, "max_hold_sessions": 4}
PARAMS = {"share": 0.5, "wait": 5, "drop": 0.004}
STATE = {}


def decide(ctx):
    if ctx.closed:
        STATE["wait"] = ctx.params["wait"]
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions if lot["held_sessions"] >= 1]
    wait = STATE.get("wait", 0)
    if wait > 0:
        STATE["wait"] = wait - 1
        return out
    close = ctx.bars["SPY"].close
    if not ctx.positions and len(close) > 1 and float(close[-1]) / float(close[-2]) - 1.0 <= -ctx.params["drop"]:
        out.append({"buy": "SPY", "share": ctx.params["share"], "at": "open"})
    return out
'''
#: THE PROFIT LOCK IN THE SPELLINGS THE STATIC RULE CANNOT SEE (league/swarm/ELANE_E2.md; the verification's attack
#: programs, their rules word for word), on a base that is blind to its run's start: one lot a week, bought at the open
#: after the week's last close (`ctx.weekday` 4) and sold by the House's maximum hold, so the program is flat at the next
#: such close with the lot it just closed in `ctx.closed`. With no lock (`ahead = 0.0`) the base passes START.
LOCK_HEAD = '''import math
import numpy as np

NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 4}
PARAMS = {"share": 0.5, "lock": 0.01, "small": 0.02}
STATE = {}
'''
LOCK_TAIL = '''    small = ahead >= ctx.params["lock"]
    return [{"buy": "SPY", "share": ctx.params["small"] if small else ctx.params["share"], "at": "open",
             "tag": "s" if small else "f"}]
'''
SMALL_TAIL = '''    return [{"buy": "SPY", "share": ctx.params["small"] if small else ctx.params["share"], "at": "open",
             "tag": "s" if small else "f"}]
'''


def weekly(body: str, tail: str = LOCK_TAIL) -> str:
    lines = "".join(f"    {line}\n" for line in body.strip("\n").split("\n"))
    return (LOCK_HEAD + "\n\ndef decide(ctx):\n    if ctx.positions or ctx.weekday != 4:\n        return []\n" + lines
            + tail)


WEEKLY_PLAIN = weekly("ahead = 0.0")
WEEKLY_LOCKS = {
    "the sleeve's dollars through .real (A01)": weekly("ahead = ctx.equity.real / ctx.budget.real - 1.0"),
    "argmax of the bar and the equity (A02)": weekly(
        'small = int(np.argmax([(1.0 + ctx.params["lock"]) * ctx.budget, ctx.equity])) == 1', SMALL_TAIL),
    "equity and budget as counts, len(range(int())) (A04)": weekly(
        'e = len(range(int(ctx.equity * 100.0)))\nb = len(range(int(ctx.budget * 100.0)))\nahead = e / b - 1.0'),
    "equity against a copy of the caps, dict(ctx.caps) (A05)": weekly(
        'cap = dict(ctx.caps)["SPY"]\nahead = ctx.equity / (2.0 * cap) - 1.0'),
    "a closed lot's fields by position, list(lot.values()) (A06b)": weekly('''
small = False
for lot in ctx.closed:
    row = list(lot.values())
    asked = ctx.params["small"] if lot["tag"] == "s" else ctx.params["share"]
    small = ctx.cash * asked >= (1.0 + ctx.params["lock"]) * row[2] * row[3]''', SMALL_TAIL),
    "a unit-free running value carried in a lot's tag (A10)": LOCK_HEAD + '''

def decide(ctx):
    if ctx.positions or ctx.weekday != 4:
        return []
    acc = 0.0
    for lot in ctx.closed:
        asked = ctx.params["small"] if lot["tag"][:1] == "s" else ctx.params["share"]
        acc = float(lot["tag"][1:]) + asked * (lot["exit"] / lot["entry"] - 1.0)
    small = acc >= ctx.params["lock"]
    return [{"buy": "SPY", "share": ctx.params["small"] if small else ctx.params["share"], "at": "open",
             "tag": ("s" if small else "f") + f"{acc:.6f}"}]
''',
}
#: THE WEIGHT LOCK (the test module's `WEIGHT_LOCK`, its rule word for word: a lot's weight in the sleeve against the
#: lot's own return) on a start-blind base: one lot a week, sold at the open and bought again at the close of the
#: session after `ctx.weekday` 3. `%(rule)s` False is the same program with no lock.
WEEKLY_WEIGHT = '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 12}
PARAMS = {"share": 0.5, "lock": 0.01, "small": 0.02}


def decide(ctx):
    if ctx.weekday != 3:
        return []
    out = []
    small = False
    for lot in ctx.positions:
        asked = ctx.params["small"] if lot["tag"] == "s" else ctx.params["share"]
        own = lot["mark"] / lot["entry"]
        small = %(rule)s
        out.append({"sell": lot["id"], "at": "open"})
    out.append({"buy": "SPY", "share": ctx.params["small"] if small else ctx.params["share"], "at": "close",
                "tag": "s" if small else "f"})
    return out
'''
WEIGHT_LOCKED = WEEKLY_WEIGHT % {"rule": 'asked * own / (lot["value"] / ctx.equity) >= 1.0 + ctx.params["lock"]'}
WEIGHT_PLAIN = WEEKLY_WEIGHT % {"rule": "False"}
#: A clock with no memory: the House numbers a run's lots from one, so a lot's id counts the run's own trades. Every
#: seventh lot is the full size.
LOT_CLOCK = '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}
PARAMS = {"every": 7, "share": 0.5, "small": 0.1}


def decide(ctx):
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
    last = max([lot["id"] for lot in ctx.positions], default=0)
    big = last % ctx.params["every"] == 0
    out.append({"buy": "SPY", "share": ctx.params["share"] if big else ctx.params["small"], "at": "close"})
    return out
'''
#: A size from the run's cumulative P&L: dollars worked out from the sleeve's equity now.
PNL_SIZED = '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}
PARAMS = {"part": 0.4}


def decide(ctx):
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
    out.append({"buy": "SPY", "usd": round(ctx.params["part"] * ctx.equity, 2), "at": "close"})
    return out
'''
#: A lock that LATCHES (a label in the lot's tag keeps it locked for good) in a program that declares the longest
#: look-back the contract allows and reads none of it: its later runs are warmed up only 524 sessions in.
LATCH = '''NEEDS = {"symbols": ["SPY"], "history": 504, "max_hold_sessions": 2}
PARAMS = {"share": 0.5, "lock": 0.01, "small": 0.02}


def decide(ctx):
    out = []
    locked = False
    for lot in ctx.positions:
        out.append({"sell": lot["id"], "at": "open"})
        if lot["tag"] == "s":
            locked = True
    if ctx.equity / ctx.budget - 1.0 >= ctx.params["lock"]:
        locked = True
    out.append({"buy": "SPY", "share": ctx.params["small"] if locked else ctx.params["share"], "at": "open",
                "tag": "s" if locked else "f"})
    return out
'''
#: A lock that changes WHETHER the program trades, never how much: every session until its run is 1% ahead, then only
#: after the week's first close. What the check does not catch (`test_what_the_check_does_not_catch`).
SKIPS = '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}
PARAMS = {"share": 0.5, "lock": 0.01}


def decide(ctx):
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
    ahead = ctx.equity / ctx.budget - 1.0 >= ctx.params["lock"]
    if not ahead or ctx.weekday == 0:
        out.append({"buy": "SPY", "share": ctx.params["share"], "at": "open"})
    return out
'''
#: A program that trades once a month (bought at the open after the month's last close, sold at the open after its
#: fifteenth session), with a lock and without.
MONTHLY = '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 30}
PARAMS = {"share": 0.5, "lock": 0.01, "small": 0.02}


def decide(ctx):
    if ctx.positions:
        if ctx.session_of_month == 15:
            return [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
        return []
    if ctx.sessions_to_month_end != 0:
        return []
    small = %(rule)s
    return [{"buy": "SPY", "share": ctx.params["small"] if small else ctx.params["share"], "at": "open"}]
'''
MONTHLY_LOCKED = MONTHLY % {"rule": 'ctx.equity / ctx.budget - 1.0 >= ctx.params["lock"]'}
MONTHLY_PLAIN = MONTHLY % {"rule": "False"}


@unittest.skipUnless(E1, "E1's equity lanes are not in this tree (the E2 branch's skeleton)")
class StartOnE1(unittest.TestCase):
    """THE START CHECK ON E1'S OWN CODE: E1's isolated runner over its synthetic stores (invented prices), its engine,
    its ctx builder and its decider kinds in this process (`InlineDecider`) and in a real child (`Decider`), over the
    Train spans themselves (1,006 and 753 sessions)."""

    @classmethod
    def setUpClass(cls):
        from league.equity import synth

        cls.tmp = tempfile.TemporaryDirectory()
        end = dt.date(2024, 12, 31)
        # A plain invented market, a flat one (no drift: what a program earns there is luck), and the four index ETFs.
        cls.plain = synth.synthetic_store(Path(cls.tmp.name) / "plain" / elane.STORE_DIR, symbols=("SPY",), end=end,
                                          seed=5, drift=0.05, vol=0.15)
        cls.flat = synth.synthetic_store(Path(cls.tmp.name) / "flat" / elane.STORE_DIR, symbols=("SPY",), end=end,
                                         seed=0, drift=0.0, vol=0.18)
        cls.four = synth.synthetic_store(Path(cls.tmp.name) / "four" / elane.STORE_DIR,
                                         symbols=("SPY", "QQQ", "IWM", "DIA"), end=end, seed=0, drift=0.0, vol=0.18)
        # An invented market that pays the overnight hold every year (the restart check's tests' own): a program that
        # holds it meets Y1-R1, so the researcher's own score reaches the two checks.
        cls.paying = synth.synthetic_store(Path(cls.tmp.name) / "paying" / elane.STORE_DIR, symbols=("SPY",), end=end,
                                           seed=5, drift=0.8, vol=0.04)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check(self, code: str, root: Any = None, *, decider: Any = None) -> dict:
        from league.equity import config
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider

        runner = Isolated(decider if decider is not None else InlineDecider(), root or self.plain)
        runs = [runner.train(code, {}, name="p", start=first, end=last, k=config.K_BASE) for first, last in TRAIN_SPANS]
        for run in runs:
            self.assertEqual(run.result["status"], "ok")
        self.runs = runs
        out = start_check(runner.decider, code, {}, name="p", spans=later_runs(runner, code, {}, name="p", runs=runs))
        self.assertEqual(runner.decider.kind_loaded, {}, "every instance dropped")
        return out

    def assert_passes(self, out: dict, *, exactly: bool = True) -> None:
        self.assertTrue(out["held"], out)
        self.assertEqual([(r["span"], r["shift"]) for r in out["runs"]], [(0, 61), (0, 127), (1, 61), (1, 127)])
        self.assertTrue(all(r["sessions"] - r["early"] >= BAR["start_min"] for r in out["runs"]))
        if exactly:
            self.assertEqual((out["matched"], out["first_miss"]), (out["sessions"], None), out)

    def assert_fails(self, out: dict) -> None:
        self.assertFalse(out["held"], out)
        self.assertTrue(any(not r["held"] for r in out["runs"]))
        self.assertIsNotNone(out["first_miss"])
        verdict = with_start({"passed": True, "fails": []}, out)
        self.assertEqual((verdict["passed"], verdict["fails"]), (False, ["START"]))

    # ------------------------------------------------------------------ what passes
    def test_a_stateless_overnight_program_passes_from_its_second_session(self):
        out = self.check(fx.program())
        self.assert_passes(out)
        runs = self.runs
        decisions = [run.bars.n - max(run.bars.first - 1, 0) - 1 for run in runs]
        self.assertEqual(decisions, [1005, 753], "2016's span has no session before it in the store; 2022's has")
        # Warm-up 22. A later run's first two decisions are left out (the run from the span's start holds, and then has
        # just sold, a lot the fresh run never had); from its third it shows the same book and is compared.
        self.assertEqual([(r["sessions"], r["early"]) for r in out["runs"]],
                         [(n - shift - 2, 20) for n in decisions for shift in SHIFTS])
        self.assertEqual(out["active"], out["sessions"], "it asks an order every session")

    def test_a_trend_holder_that_buys_again_after_its_maximum_hold_passes(self):
        out = self.check(TREND)
        self.assert_passes(out)
        reasons = {lot["reason"] for run in self.runs for lot in run.result["lots"]}
        self.assertLessEqual({"max_hold", "program"}, reasons, "the House sold lots at the maximum hold, the program others")
        again = sum(1 for run in self.runs for lot in run.result["lots"] if lot["reason"] == "max_hold")
        self.assertGreater(again, 20, "and the program bought again after them")
        self.assertGreater(out["active"], 400)

    def test_a_stop_on_each_lots_own_return_passes(self):
        out = self.check(STOP)
        self.assert_passes(out)
        held = {lot["held_sessions"] for run in self.runs for lot in run.result["lots"]}
        self.assertGreater(len(held), 3, "lots left at their stop, their target and the maximum hold")

    def test_a_program_that_waits_after_its_own_last_exit_falls_in_step_again(self):
        out = self.check(WAIT)
        self.assert_passes(out, exactly=False)
        misses = [k for r in out["runs"] for k in r["misses"]]
        self.assertTrue(0 < len(misses) <= 6, out)
        self.assertLess(max(misses), 40, "only near a later run's start: the run from the span's start was still waiting")
        self.assertGreaterEqual(out["share"], 0.995)
        self.assertGreaterEqual(out["active_share"], 0.97)

    def test_the_three_seeded_programs_pass(self):
        from league.swarm import seeds

        self.assertEqual([spec["id"] for spec in seeds.EQUITY_SEEDS],
                         ["seed-overnight-qqq", "seed-reversal-index", "seed-overnight-spy"])
        for spec in seeds.EQUITY_SEEDS:
            with self.subTest(spec["id"]):
                code, params = seeds.equity_program_for(spec)
                self.assertEqual(params, {})
                out = self.check(code, self.four)
                self.assert_passes(out)
                self.assertGreater(sum(len(run.result["lots"]) for run in self.runs), 100, "it really traded")

    # ------------------------------------------------------------------ the profit lock
    def test_the_profit_lock_fails_in_every_spelling_the_static_rule_cannot_see(self):
        base = self.check(WEEKLY_PLAIN, self.flat)
        self.assert_passes(base)
        self.assertIsNone(elane_train.check_code(WEEKLY_PLAIN, ["SPY"]))
        lots = sum(len(run.result["lots"]) for run in self.runs)
        self.assertGreater(lots, 280, "a lot a week")
        for name, code in WEEKLY_LOCKS.items():
            with self.subTest(name):
                self.assertIsNone(elane_train.check_code(code, ["SPY"]), "the static rule passes it")
                out = self.check(code, self.flat)
                self.assert_fails(out)
                token = sum(1 for run in self.runs for lot in run.result["lots"]
                            if float(lot["qty"]) * float(lot["entry_px"]) < 100.0)
                self.assertTrue(0 < token < lots, "it trades the token size once ahead, the full size before")
                self.assertIn(out["first_miss"]["what"], ("size",), "the same orders, another size")
                self.assertIn("0.02 of the sleeve", out["first_miss"]["base"] + out["first_miss"]["later"])
                self.assertGreater(out["sized"], 5)
                self.assertEqual(out["resized"], out["sized"], "and the same lots every time: flat, a lot just closed")

    def test_the_weight_lock_fails_and_its_twin_with_no_lock_passes(self):
        self.assert_passes(self.check(WEIGHT_PLAIN, self.flat))
        self.assertIsNone(elane_train.check_code(WEIGHT_LOCKED, ["SPY"]), "open by design: an honest weight cap reads alike")
        self.assertIn('asked * own / (lot["value"] / ctx.equity) >= 1.0 + ctx.params["lock"]', WEIGHT_LOCK,
                      "the test module's rule, word for word")
        out = self.check(WEIGHT_LOCKED, self.flat)
        self.assert_fails(out)
        self.assertGreater(out["sized"], 50)
        self.assertEqual(out["resized"], out["sized"])
        self.assertLess(out["active_share"], 0.5)

    def test_the_verifiers_own_programs_fail_as_written(self):
        """`WEIGHT_LOCK` and `STATE_KEPT` as the review's tests hold them (the restart check passes the first and
        fails the second). As written they also count their holds from the run's first session (a lot is bought again
        the moment the last one is sold), so a later run never shows the same book and differs on most sessions."""
        for name, code in (("WEIGHT_LOCK", WEIGHT_LOCK), ("STATE_KEPT", STATE_KEPT)):
            with self.subTest(name):
                self.assertIsNone(elane_train.check_code(code, ["SPY"]))
                out = self.check(code, self.flat)
                self.assert_fails(out)
                self.assertEqual([r["held"] for r in out["runs"]], [False] * 4)
                self.assertLess(out["share"], 0.7)
        state = elane_train.restart_check(self.check_decider(), WEIGHT_LOCK, {}, name="p",
                                          streams=[elane_train.state_inputs(run) for run in self.weight_runs()])
        self.assertTrue(state["held"], "the restart check passes the weight lock: START is what refuses it")

    def check_decider(self) -> Any:
        from league.live.decider import InlineDecider

        return InlineDecider()

    def weight_runs(self) -> list:
        from league.equity import config
        from league.equity.runner import Isolated

        runner = Isolated(self.check_decider(), self.flat)
        return [runner.train(WEIGHT_LOCK, {}, name="p", start=first, end=last, k=config.K_BASE)
                for first, last in TRAIN_SPANS]

    # ------------------------------------------------------------------ clocks and sizes
    def test_a_program_that_trades_every_nth_session_from_its_first_trade_fails(self):
        out = self.check(fx.counter(7))  # a count of its own decides, kept in STATE
        self.assert_fails(out)
        self.assertEqual([r["held"] for r in out["runs"]], [False] * 4)
        self.assertIsNone(elane_train.check_code(LOT_CLOCK, ["SPY"]))
        out = self.check(LOT_CLOCK)  # the same clock with no memory: the House's own numbering of the run's lots
        self.assert_fails(out)
        self.assertEqual(out["first_miss"]["what"], "size")
        self.assertLess(out["share"], 0.8, "two sessions in seven differ")
        state = elane_train.restart_check(self.check_decider(), LOT_CLOCK, {}, name="p",
                                          streams=[elane_train.state_inputs(run) for run in self.runs])
        self.assertEqual(state["matched"], state["sessions"], "nothing in STATE: the restart check cannot see this clock")

    def test_a_program_that_sizes_by_its_runs_cumulative_pnl_fails(self):
        self.assertIsNone(elane_train.check_code(PNL_SIZED, ["SPY"]), "a size proportional to the sleeve is no level")
        out = self.check(PNL_SIZED)
        self.assert_fails(out)
        self.assertEqual((out["matched"], out["sized"], out["resized"]), (0, out["sessions"], out["sessions"]),
                         "every session: the same lots, the same orders, another size")
        self.assertGreater(out["size_gap"]["usd"], 1.0)
        text = start_text({"start": out})
        self.assertIn("only a buy's size differed", text)
        self.assertIn("size a buy by a constant share of the sleeve, never by dollars worked out from ctx.equity", text)
        self.assertNotRegex(text, r"\b(19|20)\d\d-\d\d", "no day reaches the brief")

    # ------------------------------------------------------------------ why the two additions to the plain rule
    def test_a_lock_cannot_hide_in_a_warm_up_its_program_chose(self):
        """`LATCH` declares 504 sessions of look-back and reads none: its later runs are warmed up 524 sessions in. It
        locks for good soon after any start, so every difference from the run that started earlier lies before that.
        Compared only once warmed up, it matched everywhere; held to that run wherever the two show the same book,
        its first sessions are compared and it fails."""
        with ALL_MISSES:
            out = self.check(LATCH)
        self.assertEqual(out["warm"], 524)
        self.assertEqual([(r["span"], r["shift"]) for r in out["runs"]], [(0, 61), (0, 127), (1, 61)])
        self.assertEqual([(s["span"], s["shift"]) for s in out["skipped"]], [(1, 127)], "it fits 2022-24 once only")
        self.assert_fails(out)
        self.assertTrue(all(len(r["misses"]) == r["sessions"] - r["matched"] for r in out["runs"]), "all on record")
        late = [k for r in out["runs"] for k in r["misses"] if k >= out["warm"]]
        self.assertEqual(late, [], "nothing differs once a later run is warmed up")
        self.assertTrue(all(r["early"] > 500 for r in out["runs"]), "the same book from a later run's third session")
        with mock.patch.object(elane_train, "same_book", lambda a, b: False):
            blind = self.check(LATCH)
        self.assertTrue(blind["held"], "the rule without the same-book sessions passes it")
        self.assertEqual(blind["matched"], blind["sessions"])

    def test_a_lock_on_a_program_that_trades_once_a_month_is_read_on_its_trades(self):
        self.assert_passes(self.check(MONTHLY_PLAIN))
        out = self.check(MONTHLY_LOCKED)
        self.assert_fails(out)
        self.assertGreater(out["resized"], 0, "the same lots, the same orders, another size")
        self.assertLess(out["active"], 0.12 * out["sessions"], "it asks an order on few sessions")
        # THE SHARE OF ITS TRADES, apart from the size rule (which refuses this lock by itself): a later run differs
        # on under 1% of its sessions and over 5% of its trades, and the share of all sessions alone passes it.
        with mock.patch.dict(BAR, {"start_sized": 10 ** 6}):
            shares = self.check(MONTHLY_LOCKED)
            hidden = [r for r in shares["runs"] if not r["held"] and r["share"] >= BAR["start_match"]]
            self.assertTrue(hidden, shares)
            with mock.patch.dict(BAR, {"start_active": 0.0}):
                sessions_only = self.check(MONTHLY_LOCKED)
        self.assertGreater(sum(r["held"] for r in sessions_only["runs"]), sum(r["held"] for r in shares["runs"]))

    def test_a_lock_that_closes_within_days_of_every_start_is_refused_by_its_sizes(self):
        """On a market that pays every session a run is 1% ahead within days of its start, so `LATCH` (here with no
        long look-back) differs from the run that started earlier on a handful of a later run's first sessions: well
        inside the two shares. Each of those sessions shows the same lots and the same orders in another size."""
        code = LATCH.replace('"history": 504', '"history": 2')
        with ALL_MISSES:
            out = self.check(code, self.paying)
        self.assert_fails(out)
        self.assertTrue(all(r["share"] >= BAR["start_match"] and r["active_share"] >= BAR["start_active"]
                            for r in out["runs"]), "the two shares alone pass every later run")
        self.assertTrue(all(0 < r["resized"] == r["sessions"] - r["matched"] <= 9 for r in out["runs"]), out)
        self.assertLess(max(k for r in out["runs"] for k in r["misses"]), 15, "a later run's first sessions")
        lots = [lot for run in self.runs for lot in run.result["lots"]]
        token = [lot for lot in lots if float(lot["qty"]) * float(lot["entry_px"]) < 100.0]
        self.assertGreater(len(token), 0.97 * len(lots), "on Train it is a token-size program")
        with mock.patch.dict(BAR, {"start_sized": 10 ** 6}):
            self.assertTrue(self.check(code, self.paying)["held"], "the rule without the size rule passes it")

    def test_what_the_check_does_not_catch(self):
        """Stated, and held here so that it stays stated: (1) a lock no Train run ever reaches never changed an order;
        (2) a lock that changes WHETHER the program trades, never how much, and closes within days of every start:
        while it is open the fresh run holds lots the earlier run does not (the books differ, so before the warm-up
        ends nothing is compared), and once warmed up both are locked."""
        never = LATCH.replace('"history": 504', '"history": 2').replace('"lock": 0.01', '"lock": 5.0')
        out = self.check(never, self.paying)
        self.assert_passes(out)
        token = [lot for run in self.runs for lot in run.result["lots"] if float(lot["qty"]) * float(lot["entry_px"]) < 100.0]
        self.assertEqual(token, [], "no run was ever five times its capital ahead: the lock never closed")
        with ALL_MISSES:
            out = self.check(SKIPS, self.paying)
        self.assertTrue(out["held"], out)
        self.assertEqual((out["sized"], out["resized"]), (0, 0), "it never asks another size")
        misses = [k for r in out["runs"] for k in r["misses"]]
        self.assertLessEqual(len(misses), 4, "a session or two where a later run is flat in its first days")
        per_week = [len(run.result["lots"]) / (len(run.result["daily"]) / 5.0) for run in self.runs]
        self.assertTrue(all(0.8 < x < 1.3 for x in per_week), "locked, it trades once a week: a lot a session before")

    # ------------------------------------------------------------------ the House's side, and the cost
    def test_a_child_that_dies_mid_check_is_the_houses_on_e1s_decider(self):
        """E1's real decider child, killed between two requests of the start check: E1 starts it again and reloads
        its instances with fresh memory. The check catches it (by an instance's call count, or by `restarts`): the
        House's, never a pass; and the child is sound again for the next check."""
        import os
        import signal
        import sys

        from league.equity import config
        from league.equity.runner import Isolated
        from league.live.decider import Decider

        decider = Decider(python=sys.executable, allow_unisolated=True)
        self.addCleanup(decider.close)
        runner = Isolated(decider, self.plain)
        code = fx.program()
        runs = [runner.train(code, {}, name="p", start=first, end=last, k=config.K_BASE) for first, last in TRAIN_SPANS]
        whole = start_check(decider, code, {}, name="p", spans=later_runs(runner, code, {}, name="p", runs=runs))
        self.assertTrue(whole["held"], "the stateless program passes in the real child too")
        self.assertEqual(decider.kind_loaded, {})

        def killed(rows: list, after: int) -> list:
            def stream(inner: Any) -> Any:
                for i, inputs in enumerate(inner):
                    if i == after:
                        proc = decider.proc
                        os.kill(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=30)
                        for pipe in (proc.stdin, proc.stdout):
                            pipe.close()
                    yield inputs
            base = rows[0]["base"]
            return [{**rows[0], "base": StartRun(base.days, stream(base.inputs), base.history, base.max_hold)}, *rows[1:]]
        with self.assertRaises(StartCheckInterrupted) as caught:
            start_check(decider, code, {}, name="p",
                        spans=killed(later_runs(runner, code, {}, name="p", runs=runs), 200))
        self.assertIsInstance(caught.exception, elane_train.StateCheckInterrupted)
        self.assertRegex(str(caught.exception), "reloaded an instance|restarted during the start check")
        self.assertEqual(decider.kind_loaded, {}, "every instance dropped")
        again = start_check(decider, code, {}, name="p", spans=later_runs(runner, code, {}, name="p", runs=runs))
        self.assertEqual((again["sessions"], again["matched"]), (whole["sessions"], whole["matched"]))

    def test_the_bar_judges_a_version_through_the_start_check_on_e1s_runner_and_what_it_costs(self):
        """The researcher's own score on E1's runner (a market that pays the overnight hold, so the stateless program
        meets Y1-R1 and STATE). THE COST of a version that reaches the check, stated and measured: four more Train runs
        (the bar's own are four) and one decide a session of each of its six 1.0x runs."""
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider
        from league.swarm.elane_train import EquityResearcher

        root = self.paying
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        router = fx.FakeRouter(lambda call: fx.review_answer("pass", model=call["sail_profile"]) if fx.is_review(call)
                               else fx.answer([]))
        settings = fx.settings(train_budget=3, train_per_round=5)

        class Counting(Isolated):
            trains: list = []
            seconds = 0.0

            def train(self, *args: Any, **kw: Any) -> Any:
                began = time.perf_counter()
                try:
                    return super().train(*args, **kw)
                finally:
                    Counting.trains.append((kw.get("start"), kw.get("k")))
                    Counting.seconds += time.perf_counter() - began

        class CountingDecider(InlineDecider):
            jobs: dict = {}

            def kind(self, kind: str, op: str, payload: Any, **kw: Any) -> dict:
                if op == "decide":
                    for job in payload.get("jobs") or ():
                        check = str(job["key"]).split(":")[0]
                        CountingDecider.jobs[check] = CountingDecider.jobs.get(check, 0) + 1
                return super().kind(kind, op, payload, **kw)

        with mock.patch.object(elane, "on", lambda s: True):
            runner = Counting(CountingDecider(), root)
            researcher = EquityResearcher(store, router, settings, runner=runner, clock=clock)
            fam = fx.e2_family(store, "e1-start", code=fx.program())
            began = time.perf_counter()
            with mock.patch.object(elane_train, "start_check", wraps=start_check) as checked:
                out = researcher.score(fam, store.version(fam["id"], 1))
            whole = time.perf_counter() - began
            rec = elane_train.record_of(store.family(fam["id"]))
            v1 = rec["versions"]["1"]
            self.assertEqual((v1["fails"], v1["passed"], rec["passed_version"]), ([], True, 1), out)
            self.assertEqual(checked.call_count, 1)
            base = [(start, k) for start, k in Counting.trains if any(start == first for first, _ in TRAIN_SPANS)]
            later = [(start, k) for start, k in Counting.trains if all(start != first for first, _ in TRAIN_SPANS)]
            self.assertEqual((len(base), len(later), {k for _, k in later}), (4, 4, {1.0}))
            start = v1["start"]
            self.assertEqual((start["matched"], start["share"], start["skipped"]), (start["sessions"], 1.0, []))
            self.assertEqual([(r["span"], r["shift"], r["sessions"]) for r in start["runs"]],
                             [(0, 61, 942), (0, 127, 876), (1, 61, 690), (1, 127, 624)])
            self.assertEqual(sorted(r["stress"] for r in store.runs(fam["id"], window="train")), [1.0, 1.0, 1.5, 1.5])
            self.assertEqual(runner.decider.kind_loaded, {})
            # The decides the two checks made: the restart check's two instances a session, and the start check's one
            # a session of each run (1,005 and 753 from a span's first session, and each later run's).
            self.assertEqual(CountingDecider.jobs, {"e2-state": 2 * (1005 + 753),
                                                    "e2-start": (1005 + 944 + 878) + (753 + 692 + 626)})
            self.assertEqual(CountingDecider.jobs["e2-start"], 4898)
            # Seconds on the machine that runs this test, kept loose: the whole judgment of one version.
            self.assertLess(whole, 300.0, f"judging one version took {whole:.1f} s ({Counting.seconds:.1f} s in its 8 runs)")
            # A profit lock that earns the same way on this market meets Y1-R1 and STATE; START alone fails it. (This
            # market pays every session, so a run is 10% ahead some sixty sessions after its own start: the lock of 1%
            # would close within a session or two of every start, which is what the check does not catch.)
            code = LATCH.replace('"history": 504', '"history": 2').replace('"lock": 0.01', '"lock": 0.1')
            lock = fx.e2_family(store, "e1-lock", code=code, symbols=("SPY",),
                                mechanism="Invented overnight idea with a latch on the run's own standing.")
            researcher.score(lock, store.version(lock["id"], 1))
            rec = elane_train.record_of(store.family(lock["id"]))
            v1 = rec["versions"]["1"]
            self.assertEqual((v1["fails"], v1["passed"], rec.get("passed_version")), (["START"], False, None))
            self.assertGreaterEqual(v1["active_years"], BAR["min_active_years"])
            self.assertEqual(v1["state"]["matched"], v1["state"]["sessions"], "the restart check passes it")
            self.assertFalse(may_validate(store, store.family(lock["id"]), 1))
            self.assertIn("failed START", elane_train.version_text(1, v1))


class NoDayInTheWords(unittest.TestCase):
    def test_a_failed_checks_words_name_sessions_counted_from_a_runs_start_never_a_day(self):
        decider = fx.FakeDecider()
        out = start_check(decider, FLAGGED, {}, name="p",
                          spans=[span(flags=lambda i, age, offset: "small" if offset and age < 40 else "")])
        text = start_text({"start": {k: out[k] for k in elane_train.START_KEYS}})
        self.assertIn("differed on its sessions 1, 2, 3, 4, 5, 6 and 34 more", text)
        self.assertFalse(re.search(r"\b(19|20)\d\d\b", text), text)
        self.assertFalse(re.search(r"\b(19|20)\d\d\b", json.dumps({k: out[k] for k in elane_train.START_KEYS})))


if __name__ == "__main__":
    unittest.main()
