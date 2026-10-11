"""THE SEAT RULE (release E5-A; the captain's A24; `equity_money.probe.seat`): "activity-1-free", with "first-come" as
the rollback.

- `TheRow`: the block is a row of the money table (its bounds, its choices, the digest it moved), its reader is
  league/equity/bands.py `seat_settings` (never league/live/money.py), and the rule's words in the report and the
  operator's page carry the row's own figures.
- `TheRanks`, `TheVectors`: the rank is deterministic and total; the conformance vectors
  (league/tests/fixtures/equity_seat_vectors.json) through the pure plan, `bands.seat_plan`.
- `K`: the two counts. A close day by the lots' size and exit day alone; a lot of EXACTLY the floor, built through the
  real engine, counts; the look writes the counts beside itself; a program that passed before the release gets them
  once from unsealed runs, and no sealed figure is read or printed.
- `TheBook`: the real `EquityBook` on invented programs and a fake venue: the free seat, the idle seat and each
  "asked" case, two rare traders that do not rotate, the return into a free seat, EDM1 on a waiting program, the
  fall-through, a restart, and that no path sells a lot or makes a trading program exit-only.
- `FirstCome`: the rollback value reproduces release E5-S's behaviour on a recorded sequence, entry for entry.
- `TheDeployNight`: the state the base leaves (six seats first come, five seated, one a rare trader), this release
  applied on it, the backfill, the ranks, and the idle seat ten sessions on.

Everything is invented (programs, prices, K): no figure here is a market's, an account's or a real program's."""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import json
import random
import re
import tempfile
import unittest
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
from unittest import mock

from league.constitution import (CONSTITUTION, EQUITY_MONEY_BOUNDS, EQUITY_MONEY_CHOICES, PINNED_DIGEST, digest,
                                 equity_money_problems, money_digest)
from league.equity import bands as B
from league.equity import config
from league.equity import live as L
from league.equity import schedule as S
from league.equity import sizing as Z
from league.equity.families import EquityFamilies
from league.live import money as M
from league.swarm import bands as swarm_bands
from league.swarm import elane
from league.tests import equity_design as X
from league.tests import equity_seat_sequence as Q
from league.tests import test_equity_book as T

try:
    import numpy  # noqa: F401 - the Gym's dependency: the engine, the store and the screen need it

    HAVE = True
except ImportError:  # pragma: no cover - the repository's own tests install it
    HAVE = False

#: The real functions `T.BookTest` stubs at their interface (read at import, before any test patches them).
REAL_SIZE, REAL_AVAILABLE, REAL_NEXT_BAND, REAL_SIZED_SHARE = Z.size_entry, M.available_cash, B.next_band, B.sized_sleeve_share
FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO = Path(__file__).resolve().parents[2]
SUNDAY, FRIDAY, MONDAY = dt.date(2026, 10, 11), T.FRIDAY, T.MONDAY
E = D("2229")
ETFS = ("SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV")
SETTINGS = B.SeatSettings(B.ACTIVITY_FREE, D("0.25"), 10)
ON = {"elane": {"mode": "gate"}, "dlane": {"mode": "gate"}}


def sessions(first: dt.date, n: int) -> list[dt.date]:
    """`n` sessions from `first` (a session itself, or the first one after it)."""
    out, d = [], first
    while len(out) < n:
        if S.is_session(d):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def counts(k_validation: int, k_train: int | None = None, train_sessions: int = 1750) -> dict:
    """A row's two counts (`seat_activity`) whose K is min(k_validation, k_train x 250 / train_sessions); with no
    Train-era count given, one that leaves the Validation count as K."""
    k_train = (k_validation * train_sessions + 249) // 250 if k_train is None else k_train
    return {"validation": {"close_days": int(k_validation), "sessions": 250},
            "train": {"close_days": int(k_train), "sessions": int(train_sessions)}}


def facts(family: str, k=None, passed=0.0, **more) -> B.SeatFacts:
    k = None if k is None else (Fraction(*k) if isinstance(k, (list, tuple)) else Fraction(k))
    return B.SeatFacts(family=family, k=k, passed_at=passed, **more)


# =============================================================================================== the money table's row
class TheRow(unittest.TestCase):
    def test_the_block_is_the_rule_as_registered(self):
        seat = CONSTITUTION["equity_money"]["probe"]["seat"]
        self.assertEqual(seat, {"rule": "activity-1-free", "k_floor": "0.25", "idle_sessions": 10})
        self.assertEqual(equity_money_problems(), [])
        self.assertEqual(B.seat_settings(), B.SeatSettings("activity-1-free", D("0.25"), 10))
        self.assertFalse(B.seat_settings().first_come)
        self.assertEqual(EQUITY_MONEY_CHOICES["probe.seat.rule"], B.SEAT_RULES, "the reader's values are the table's")
        self.assertEqual(B.SEAT_RULES, ("activity-1-free", "first-come"))
        self.assertNotIn("activity-1", B.SEAT_RULES, "OUTRANKING IS NOT ADOPTED: it is no value of the row")
        self.assertEqual(EQUITY_MONEY_BOUNDS["probe.seat.k_floor"], ("0.25", "0.25"), "one value: a new floor is a new rule")
        self.assertEqual(EQUITY_MONEY_BOUNDS["probe.seat.idle_sessions"], ("10", "60"), "the loose end is A24's ten")
        self.assertEqual((B.K_TOLERANCE, B.K_PER_SESSIONS), (D("0.0005"), 250))

    def test_each_row_inside_its_bound_and_refused_past_it(self):
        def problems(**rows):
            c = copy.deepcopy(CONSTITUTION)
            c["equity_money"]["probe"]["seat"].update(rows)
            return equity_money_problems(c)

        self.assertEqual(problems(rule="first-come"), [], "the rollback value is a row of the table")
        for rule in ("activity-1", "first come", "FIRST-COME", "", None, 1):
            self.assertTrue(any("probe.seat.rule" in p for p in problems(rule=rule)), rule)
        for floor in ("0.10", "0.24", "0.26", "0", "1", "x"):
            self.assertTrue(any("probe.seat.k_floor" in p for p in problems(k_floor=floor)), floor)
        for ok in (10, 20, 60):
            self.assertEqual(problems(idle_sessions=ok), [], ok)
        for bad in (9, 0, 61, 10.0, "ten", True, None):
            self.assertTrue(any("probe.seat.idle_sessions" in p for p in problems(idle_sessions=bad)), bad)
        gone = copy.deepcopy(CONSTITUTION)
        del gone["equity_money"]["probe"]["seat"]
        self.assertTrue(any("probe.seat" in p for p in equity_money_problems(gone)), "a table without the block is refused")
        with self.assertRaises(ValueError):
            M.EquityTable.from_constitution(gone)

    def test_the_reader_is_not_the_hashed_table_and_fails_to_first_come(self):
        """`league/live/money.py` is inside the options execution fingerprint: it does not learn the block. Its
        `EquityTable` is built with the block present and carries nothing of it; the reader is `bands.seat_settings`,
        which reads a block it cannot read as "first-come" (the rollback value moves nobody by a rule it cannot state)."""
        table = M.EquityTable.from_constitution()
        self.assertFalse(any("seat" in f.name or "idle" in f.name for f in dataclasses.fields(table)))
        self.assertNotIn("probe.seat", Path(M.__file__).read_text(encoding="utf-8"))
        self.assertNotIn('["seat"]', Path(M.__file__).read_text(encoding="utf-8"))
        gone = X.without_seat()
        self.assertEqual(B.seat_settings(gone), B.SEAT_FALLBACK)
        self.assertTrue(B.SEAT_FALLBACK.first_come)
        for rows in ({"rule": "activity-1"}, {"k_floor": "nan"}, {"k_floor": "0"}, {"idle_sessions": 0},
                     {"idle_sessions": True}, {"idle_sessions": "10"}):
            c = copy.deepcopy(CONSTITUTION)
            c["equity_money"]["probe"]["seat"].update(rows)
            self.assertEqual(B.seat_settings(c), B.SEAT_FALLBACK, rows)
        with X.seat_rule("first-come"):
            self.assertTrue(B.seat_settings().first_come)

    def test_the_block_moved_the_money_digest_once_and_every_row_of_it_is_a_money_rule(self):
        """THE IDS: the money digest (and `PINNED_DIGEST`) moved with the block, and with nothing else: the table with
        the block left out is release E5-S's, to the last hex. Each of the block's rows moves the digest by itself,
        "first-come" included, so the standing grant re-ratifies on the release and on its rollback."""
        pair = X.in_force()
        self.assertEqual((money_digest(), digest()), X.DIGESTS[pair])
        self.assertEqual(digest(), PINNED_DIGEST)
        bare = X.without_seat()
        self.assertEqual((money_digest(bare), digest(bare)), X.DIGESTS_E5S[pair], "before the block: release E5-S")
        seen = {money_digest()}
        for rows in ({"rule": "first-come"}, {"idle_sessions": 20}, {"k_floor": "0.250"}):
            c = copy.deepcopy(CONSTITUTION)
            c["equity_money"]["probe"]["seat"].update(rows)
            self.assertNotIn(money_digest(c), seen, rows)
            self.assertNotEqual(money_digest(c), X.DIGESTS_E5S[pair][0], "the rollback is a digest of its own, not E5-S's")
            seen.add(money_digest(c))

    def test_the_rules_words_carry_the_rows_figures_and_are_in_the_operators_page(self):
        from league.ops import dlane_report as R

        seat = CONSTITUTION["equity_money"]["probe"]["seat"]
        rule = R.A24_SEAT_RULE
        self.assertIn(f"\"{seat['rule']}\"", rule)
        self.assertIn("\"first-come\"", rule)
        self.assertIn(f"at least {seat['k_floor']} of its sleeve (read as {seat['k_floor']} minus {B.K_TOLERANCE}", rule)
        self.assertIn(f"per {B.K_PER_SESSIONS} sessions", rule)
        self.assertIn(f"for {seat['idle_sessions']} seated sessions", rule)
        for words in ("the smaller of its Validation close days and its Train-era close days", "earlier look pass",
                      "then the family id", "reads no P&L and no sealed window", "never printed in public text",
                      "keeps its seat while nobody waits", "when an unflagged program waits",
                      "instrument cap, the invested cap or cash does not count as asked",
                      "returns only into a free seat, by the same rank, with no new look",
                      "outranking is not adopted", "EDM1 covers waiting programs too",
                      "never a forced or hand-placed trade", "no lot is ever sold by it"):
            self.assertIn(words, rule)
        for words in ("closes concentrate in frequent traders", "weaker evidence of skill",
                      "a daily slice of a quarter sleeve can buy rank", "a slow, non-idle incumbent keeps its seat"):
            self.assertIn(words, R.A24_SEAT_COSTS)
        self.assertEqual((R.SEAT_RULE["id"], R.SEAT_RULE["registered"], R.SEAT_RULE["outranking"]),
                         ("A24", "2026-10-11T13:42Z", "not adopted"))
        page = re.sub(r"\s+", " ", (REPO / "docs" / "operations.md").read_text(encoding="utf-8"))
        for sentence in (R.A24_SEAT_RULE, R.A24_SEAT_COSTS):
            self.assertIn(sentence, page)
        self.assertEqual(swarm_bands.SEAT_PLAN_KEY, L.SEAT_KEY, "the swarm reads the book's own key")


# =========================================================================================================== the ranks
class TheRanks(unittest.TestCase):
    def test_a_thousand_shuffles_give_one_order(self):
        rng = random.Random(24)
        pool = [facts(f"p{i:02d}", rng.choice([None, 0, 3, 3, 40, 40, 199, (41 * 250, 205)]), rng.choice([1.0, 2.0, 2.0, 7.5]),
                      flagged=rng.random() < 0.25, seeded=rng.random() < 0.3) for i in range(24)]
        want = [p.family for p in B.seat_order(pool)]
        self.assertEqual(len(set(B.seat_key(p) for p in pool)), len(pool), "the key is total: no two programs tie")
        for _ in range(1000):
            rng.shuffle(pool)
            self.assertEqual([p.family for p in B.seat_order(pool)], want)
        holders = [dataclasses.replace(p, flagged=False, flat=True, seated_sessions=20, seat_day=f"2026-10-{1 + i % 9:02d}")
                   for i, p in enumerate(pool[:9])]
        one = B.seat_yielder(holders).family
        for _ in range(200):
            rng.shuffle(holders)
            self.assertEqual(B.seat_yielder(holders).family, one)
            self.assertEqual(B.seat_plan(holders, pool[9:], seats=9, settings=SETTINGS),
                             B.seat_plan(list(reversed(holders)), list(reversed(pool[9:])), seats=9, settings=SETTINGS)
                             | {"idle": B.seat_plan(holders, pool[9:], seats=9, settings=SETTINGS)["idle"]})

    def test_the_order_and_its_ties(self):
        order = [p.family for p in B.seat_order([
            facts("flagged-high", 240, 0.0, flagged=True), facts("unread", None, 0.0), facts("low", 1, 0.0),
            facts("tie-b", 50, 5.0), facts("tie-a", 50, 5.0), facts("tie-early", 50, 4.0), facts("high", 51, 99.0),
            facts("no-time", 50, None), facts("seeded", 50, 4.5, seeded=True)])]
        self.assertEqual(order, ["high", "tie-early", "seeded", "tie-a", "tie-b", "no-time", "low", "unread", "flagged-high"])
        # No priority by origin: a seeded program sorts exactly as a bred one of the same K and pass time would.
        self.assertEqual(B.seat_key(facts("x", 50, 4.5, seeded=True)), B.seat_key(facts("x", 50, 4.5, seeded=False)))

    def test_k_is_exact_and_the_smaller_of_the_two(self):
        self.assertEqual(B.seat_k(counts(120, 700, 1750)), Fraction(100), "the Train era's 700 in 1750 are 100 a 250")
        self.assertEqual(B.seat_k(counts(90, 700, 1750)), Fraction(90), "the Validation year's count is the smaller")
        self.assertEqual(B.seat_k(counts(250, 41, 205)), Fraction(50))
        self.assertEqual(B.seat_k(counts(250, 1, 3)), Fraction(250, 3), "a Fraction: never a rounded float")
        self.assertEqual(B.seat_k(counts(0, 0, 1750)), Fraction(0))
        for bad in (None, {}, {"validation": {"close_days": 3}}, counts(3, 3, 0), {**counts(3), "train": {"close_days": 1.5, "sessions": 9}},
                    {"validation": {"close_days": True, "sessions": 250}, "train": {"close_days": 1, "sessions": 9}},
                    {"validation": {"close_days": -1, "sessions": 250}, "train": {"close_days": 1, "sessions": 9}}, "k", 7):
            self.assertIsNone(B.seat_k(bad), bad)

    def test_the_idle_test_is_three_conditions(self):
        base = dict(seated_sessions=10, quiet_sessions=None, flat=True)
        self.assertTrue(B.seat_idle(facts("p", 1, **base), SETTINGS))
        self.assertTrue(B.seat_idle(facts("p", 1, **{**base, "quiet_sessions": 10}), SETTINGS))
        for change in ({"seated_sessions": 9}, {"quiet_sessions": 9}, {"quiet_sessions": 0}, {"flat": False}):
            self.assertFalse(B.seat_idle(facts("p", 1, **{**base, **change}), SETTINGS), change)
        longer = B.SeatSettings(B.ACTIVITY_FREE, D("0.25"), 20)
        self.assertFalse(B.seat_idle(facts("p", 1, **base), longer), "a longer clock only makes a yield rarer")
        self.assertIsNone(B.seat_yielder([]))


class TheVectors(unittest.TestCase):
    def test_every_conformance_vector(self):
        doc = json.loads((FIXTURES / "equity_seat_vectors.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(doc["vectors"]), 28)
        names = [v["name"] for v in doc["vectors"]]
        self.assertEqual(len(set(names)), len(names))
        for v in doc["vectors"]:
            with self.subTest(v["name"]):
                s = v["settings"]
                settings = B.SeatSettings(s["rule"], D(s["k_floor"]), int(s["idle_sessions"]))
                holders = [facts(h["family"], h["k"], h["passed_at"], seeded=h["seeded"], seat_day=h["seat_day"],
                                 seated_sessions=h["seated_sessions"], quiet_sessions=h["quiet_sessions"], flat=h["flat"])
                           for h in v["holders"]]
                waiting = [facts(w["family"], w["k"], w["passed_at"], flagged=w["flagged"], seeded=w["seeded"])
                           for w in v["waiting"]]
                plan = B.seat_plan(holders, waiting, seats=v["seats"], settings=settings, late=v["late"],
                                   yielded_today=v["yielded_today"])
                self.assertEqual(plan, v["expect"])
                # What no plan ever says: a seated program that is not flat leaves; more seated than there are seats.
                not_flat = {h["family"] for h in v["holders"] if not h["flat"]}
                self.assertNotIn(plan["yields"], not_flat)
                self.assertLessEqual(len(plan["seat"]), max(0, v["seats"] - len(holders) + (1 if plan["yields"] else 0)))
                if plan["yields"]:
                    self.assertIn(plan["yields"], plan["idle"])
                    self.assertEqual(plan["seat"][0], plan["for"], "the program it yields to takes the seat")

    def test_no_arrival_however_ranked_unseats_a_program_that_is_not_idle(self):
        """A property over random books: a holder that holds a lot, or asked inside the clock, or is inside its first
        ten seated sessions, is never the one that yields; at most one program yields; and nobody yields unless an
        unflagged program waits."""
        rng = random.Random(1011)
        for _ in range(3000):
            seats = rng.randint(0, 6)
            holders = [facts(f"h{i}", rng.choice([None, 0, 5, 100, 250]), float(i), flat=rng.random() < 0.6,
                             seated_sessions=rng.randint(0, 25), quiet_sessions=rng.choice([None, 0, 3, 9, 10, 30]),
                             seat_day=f"2026-09-{1 + i:02d}") for i in range(rng.randint(0, 7))]
            waiting = [facts(f"w{i}", rng.choice([None, 0, 5, 100, 250]), float(10 + i), flagged=rng.random() < 0.4)
                       for i in range(rng.randint(0, 4))]
            plan = B.seat_plan(holders, waiting, seats=seats, settings=SETTINGS, late=rng.random() < 0.2,
                               yielded_today=rng.random() < 0.2)
            by = {h.family: h for h in holders}
            if plan["yields"] is not None:
                goes = by[plan["yields"]]
                self.assertTrue(goes.flat and goes.seated_sessions >= 10
                                and (goes.quiet_sessions is None or goes.quiet_sessions >= 10))
                self.assertTrue(any(not w.flagged for w in waiting))
                self.assertLessEqual(len(holders), seats)
            self.assertLessEqual(len(holders) - (1 if plan["yields"] else 0) + len(plan["seat"]), max(seats, len(holders)))
            self.assertEqual(sorted(plan["queue"]), sorted([w.family for w in waiting] + ([plan["yields"]] if plan["yields"] else [])))


# =================================================================================================================== K
class K(unittest.TestCase):
    def test_a_close_day_by_size_and_exit_day_alone(self):
        """The study's own vector (EQDONE-3, its test U7): 0.25 counts, 0.2494 does not, 0.2495 does, four lots of 0.075
        on one day do, three do not, a lot still open counts nowhere."""
        lots = [{"exit_day": "d5", "weight": 0.25}, {"exit_day": "d6", "weight": 0.2494}, {"exit_day": "d7", "weight": 0.2495},
                {"exit_day": None, "weight": 0.4}] + [{"exit_day": "d9", "weight": 0.075}] * 4 + \
               [{"exit_day": "d10", "weight": 0.075}] * 3
        self.assertEqual(B.close_days(lots, floor=D("0.25")), 3)
        # Splitting a lot does not change K; neither does anything else a lot's row carries (a price, a return, a P&L).
        whole = [{"exit_day": "d1", "weight": 0.5}]
        split = [{"exit_day": "d1", "weight": 0.1}] * 5
        self.assertEqual(B.close_days(whole, floor=D("0.25")), B.close_days(split, floor=D("0.25")))
        dressed = [{**lot, "entry_px": 1.0, "exit_px": 9e9, "net": -1e9, "return": 7.0, "fees": 3.0} for lot in lots]
        self.assertEqual(B.close_days(dressed, floor=D("0.25")), 3, "it reads the weight and the exit day and nothing else")
        self.assertEqual(B.close_days([], floor=D("0.25")), 0)
        for bad in ("0.3", None, True, float("nan")):
            with self.assertRaises(ValueError):
                B.close_days([{"exit_day": "d", "weight": bad}], floor=D("0.25"))

    def test_the_counts_of_a_look(self):
        ok = {"status": "ok", "lots": [{"exit_day": "a", "weight": 0.3}, {"exit_day": "b", "weight": 0.3}], "daily": [0] * 250}
        train = [{"status": "ok", "lots": [{"exit_day": "c", "weight": 0.3}], "daily": [0] * 1000},
                 {"status": "no_data", "lots": [], "daily": []},
                 {"status": "ok", "lots": [{"exit_day": "d", "weight": 0.3}, {"exit_day": "e", "weight": 0.1}], "daily": [0] * 750}]
        got = B.seat_counts(ok, train, floor=D("0.25"))
        self.assertEqual(got, {"floor": "0.25", "validation": {"close_days": 2, "sessions": 250},
                               "train": {"close_days": 2, "sessions": 1750}})
        self.assertEqual(B.seat_k(got), Fraction(2 * 250, 1750))
        with self.assertRaises(ValueError):
            B.seat_counts({**ok, "status": "disqualified"}, train, floor=D("0.25"))
        with self.assertRaises(ValueError):
            B.seat_counts(ok, [{**train[0], "status": "disqualified"}], floor=D("0.25"))
        self.assertIsNone(B.seat_k(B.seat_counts(ok, [train[1]], floor=D("0.25"))), "no Train-era session: unreadable")
        self.assertEqual(B.run_sessions({"summary": {"days": 7}}), 7)

    @unittest.skipUnless(HAVE, "numpy not installed")
    def test_a_lot_of_exactly_the_floor_counts_built_through_the_real_engine(self):
        """THE FLOOR'S TOLERANCE (the review's A4): a program that buys a share of exactly 0.25 of its sleeve fills a
        hair under it (the share count is floored to millionths, the weight rounded to eight places), so "at least
        0.25" alone would count none of its days. Through the real engine on an invented market: every lot weighs
        under 0.25 and above 0.2495, and every day it closes counts; the same program at 0.2494 counts none; at 0.26
        every day counts too; and two lots of an eighth closed on one day count as one day."""
        from league.equity import synth
        from league.equity.runner import run_bars
        from league.equity.store import EquityStore

        with tempfile.TemporaryDirectory() as tmp:
            root = synth.synthetic_store(Path(tmp) / "daily", seed=5, drift=0.2, vol=0.15)
            store = EquityStore(root)

            def run(share: float, symbols=("SPY",)):
                code = (f"NEEDS = {{'symbols': {list(symbols)!r}, 'history': 2}}\nPARAMS = {{}}\n\n\n"
                        "def decide(ctx):\n"
                        "    if ctx.positions:\n"
                        "        return [{'sell': lot['id'], 'at': 'open'} for lot in ctx.positions]\n"
                        f"    return [{{'buy': s, 'share': {share!r}, 'at': 'open'}} for s in ctx.symbols]\n")
                return run_bars(code, {}, store.bars(list(symbols), "validation", history=2), name="floor")

            exact = run(0.25)
            self.assertEqual(exact["status"], "ok")
            closed = [lot for lot in exact["lots"] if lot["exit_day"] is not None]
            self.assertGreater(len(closed), 100)
            self.assertTrue(all(0.2495 <= lot["weight"] < 0.25 for lot in closed),
                            "a share of exactly the floor fills a hair under it")
            days = len({lot["exit_day"] for lot in closed})
            self.assertEqual(B.close_days(exact["lots"], floor=D("0.25")), days, "every one of its close days counts")
            self.assertEqual(sum(1 for lot in closed if D(repr(lot["weight"])) >= D("0.25")), 0,
                             "without the tolerance none would")
            self.assertEqual(B.close_days(run(0.2494)["lots"], floor=D("0.25")), 0, "under the floor less the tolerance")
            above = run(0.26)
            self.assertEqual(B.close_days(above["lots"], floor=D("0.25")),
                             len({lot["exit_day"] for lot in above["lots"] if lot["exit_day"] is not None}))
            two = run(0.125, symbols=("SPY", "QQQ"))
            both = [lot for lot in two["lots"] if lot["exit_day"] is not None]
            self.assertTrue(all(lot["weight"] < 0.2495 for lot in both), "neither lot alone reaches the floor")
            self.assertEqual(B.close_days(two["lots"], floor=D("0.25")), len({lot["exit_day"] for lot in both}),
                             "the lots closed on one day are summed")
            self.assertEqual(B.run_sessions(exact), 250, "Validation is calendar 2025's 250 sessions")


@unittest.skipUnless(HAVE, "numpy not installed")
class TheLookKeepsTheCounts(unittest.TestCase):
    """The real pipeline on an invented market (as league/tests/test_equity_e2e.py): a seed is born, validated and
    looked at through the real isolated runner; K's two counts land beside the look; a program that passed before the
    release gets them from `seat_backfill`."""

    def setUp(self):
        from league.equity import synth
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider
        from league.swarm import settings as settings_mod
        from league.swarm.store import SwarmStore
        from league.tests import REAL_POLICY_PATH

        patcher = mock.patch.object(settings_mod, "POLICY_PATH", REAL_POLICY_PATH)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = T.Clock(T.at(SUNDAY, 12, 0))
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.store_root = synth.synthetic_store(self.root / elane.STORE_DIR, gate=True, seed=11, drift=0.9, vol=0.10)
        self.runner = Isolated(InlineDecider(), self.store_root)
        elane._seat_failed.clear()
        self.addCleanup(elane._seat_failed.clear)

    def passed(self) -> tuple[dict, dict, str]:
        from league.swarm.gate import Gate, run_sha
        from league.swarm.tournament import Tournament

        elane.birth_seeds(self.store, ON)
        tournament = Tournament(self.store, None, ON, clock=self.clock)
        tournament.equity_runner = self.runner
        ahead = self.store.family("seed-overnight-qqq")
        elane.validate(tournament, ahead, self.store.version(ahead["id"], ahead["best_version"]))
        fam = self.store.family("seed-overnight-spy")
        version = self.store.version(fam["id"], fam["best_version"])
        self.assertTrue(elane.validate(tournament, fam, version)["entered"])
        self.gate = Gate(self.store, None, None, ON, clock=self.clock)
        self.gate.equity_runner = self.runner
        sha = run_sha(version)
        self.assertTrue(elane.look(self.gate, self.store.family(fam["id"]), version, sha))
        return self.store.family(fam["id"]), version, sha

    def events(self, kind: str | None = None) -> list[dict]:
        return [e for e in self.store.events_after(0, limit=100000) if kind is None or e["kind"] == kind]

    def by_hand(self, version: dict) -> dict:
        validation = self.runner.validation(version["code"], dict(version.get("params") or {}), name="by-hand").result
        train = [run.result for run in self.runner.segments(version["code"], dict(version.get("params") or {}), name="by-hand")]
        return B.seat_counts(validation, train, floor=D("0.25"))

    def test_the_look_writes_the_two_counts_beside_itself_once(self):
        fam, version, sha = self.passed()
        held = fam["state"][elane.SEAT_KEY]
        want = self.by_hand(version)
        self.assertEqual({k: held[k] for k in ("floor", "validation", "train")}, want)
        self.assertEqual((held["version"], held["run_sha"], held["source"], held["validation_run"]), (1, sha, "look", "look"))
        self.assertEqual(want["validation"]["sessions"], 250)
        self.assertGreater(want["train"]["sessions"], 1700, "the Train-era spans: 2016-19 and 2022-24")
        self.assertGreater(want["validation"]["close_days"], 100, "the overnight seed closes a half-sleeve lot most days")
        self.assertEqual(elane.seat_activity(fam["state"], 1, sha), {"validation": want["validation"], "train": want["train"]})
        self.assertIsNone(elane.seat_activity(fam["state"], 2, sha), "another version: its own counts, not these")
        self.assertIsNone(elane.seat_activity(fam["state"], 1, "x" * 64))
        # The book's row carries them (and the pass time); the default read does not.
        [row] = swarm_bands.read(self.root, lanes=elane.LANES, waiting=True)
        self.assertEqual((row["family"], row["seat"], row["seat_activity"], row["passed_at"]),
                         ("seed-overnight-spy", "queue", {"validation": want["validation"], "train": want["train"]},
                          fam["state"]["banded_at"]))
        [plain] = swarm_bands.read(self.root, lanes=elane.LANES)
        self.assertEqual(set(row) - set(plain), {"passed_at", "seat_activity"})
        self.assertEqual({k: v for k, v in row.items() if k in plain and k != "seat"},
                         {k: v for k, v in plain.items() if k != "seat"})
        self.assertEqual(plain["seat"], "seated")
        # Nothing public says K: the look's public event carries no count, and no view of the family does.
        events = [e for e in self.events("swarm.gate") if e["payload"].get("action") == "look"]
        self.assertEqual(events[-1]["payload"]["_seat"], held)
        self.assertFalse(any("close_days" in json.dumps({k: v for k, v in e["payload"].items() if not k.startswith("_")})
                             for e in self.events()))
        self.assertNotIn("close_days", json.dumps(elane.view(fam, lane="beta")))
        # Written once: nothing rewrites it (the backfill finds nothing owed).
        self.assertEqual(elane.seat_backfill(self.gate), [])
        self.assertEqual(self.store.family(fam["id"])["state"][elane.SEAT_KEY], held)

    def test_a_program_that_passed_before_the_release_gets_them_once_and_nothing_sealed_is_read(self):
        from league.equity import runner as runner_mod
        from league.equity import store as store_mod

        fam, version, sha = self.passed()
        want = self.by_hand(version)
        state = dict(fam["state"])
        self.store.set_state(fam["id"], **{elane.SEAT_KEY: None})          # as release E5-S's look left it: no counts
        self.assertIsNone(elane.seat_activity(self.store.family(fam["id"])["state"], 1, sha))
        windows: list[str] = []
        real_bars, real_span = store_mod.EquityStore.bars, store_mod.EquityStore.span

        def bars(store, symbols, window, **kw):
            windows.append(str(window))
            return real_bars(store, symbols, window, **kw)

        def span(store, symbols, first, last, **kw):
            windows.append(f"{first}..{last}")
            return real_span(store, symbols, first, last, **kw)

        sealed = mock.Mock(side_effect=AssertionError("the backfill never takes a look"))
        with mock.patch.object(store_mod.EquityStore, "bars", bars), mock.patch.object(store_mod.EquityStore, "span", span), \
                mock.patch.object(store_mod, "mint_equity_gate_capability", sealed), \
                mock.patch.object(runner_mod.Isolated, "look", sealed):
            self.assertEqual(elane.seat_backfill(self.gate), [fam["id"]])
            held = self.store.family(fam["id"])["state"][elane.SEAT_KEY]
            self.assertEqual({k: held[k] for k in ("floor", "validation", "train")}, want, "the same counts as the look's")
            self.assertEqual((held["source"], held["validation_run"]), ("backfill", "stored"),
                             "the Validation count is the STORED run's: the one the look reproduced")
            self.assertEqual(windows, [f"{a}..{b}" for a, b in config.TRAIN_ERA_SEGMENTS],
                             "only the Train-era spans were run again: the Validation run was read from its file")
            self.assertEqual(elane.seat_backfill(self.gate), [], "once")
            # The stored file gone: the Validation run is made again (the unsealed 2025 window), the same counts.
            self.store.set_state(fam["id"], **{elane.SEAT_KEY: None})
            for row in self.store.version_runs(fam["id"], 1, window="validation"):
                (self.root / row["path"]).unlink()
            windows.clear()
            self.assertEqual(elane.seat_backfill(self.gate), [fam["id"]])
            again = self.store.family(fam["id"])["state"][elane.SEAT_KEY]
            self.assertEqual(({k: again[k] for k in ("floor", "validation", "train")}, again["validation_run"]),
                             (want, "rerun"))
            self.assertEqual(windows, ["validation", *[f"{a}..{b}" for a, b in config.TRAIN_ERA_SEGMENTS]])
        sealed.assert_not_called()
        self.assertFalse(any(w in config.SEALED or "2026" in w for w in windows), "no sealed window")
        # No look, no try, no trial, no band move, and nothing of the look's own record is touched.
        after = self.store.family(fam["id"])
        self.assertEqual(after["band"], "candidate")
        self.assertEqual({k: v for k, v in after["state"].items() if k != elane.SEAT_KEY},
                         {k: v for k, v in state.items() if k != elane.SEAT_KEY})
        self.assertEqual(len(self.store.looks()), 1)
        public = [{k: v for k, v in e["payload"].items() if not k.startswith("_")}
                  for e in self.events("swarm.gate") if e["payload"].get("action") == "seat_counts"]
        self.assertEqual([(p["source"], p["validation_run"]) for p in public], [("backfill", "stored"), ("backfill", "rerun")])
        self.assertNotIn("close_days", json.dumps(public), "the counts ride a private key only")

    def test_counts_that_cannot_be_made_rank_last_are_said_once_and_tried_again_hourly(self):
        fam, version, sha = self.passed()
        self.store.set_state(fam["id"], **{elane.SEAT_KEY: None})
        with mock.patch.object(type(self.runner), "segments", side_effect=RuntimeError("the child is down")):
            self.assertEqual(elane.seat_backfill(self.gate), [])
            self.assertEqual(elane.seat_backfill(self.gate), [], "not tried again inside the hour")
        said = [e["payload"] for e in self.events("swarm.status")
                if e["payload"].get("action") == "equity_seat_counts_failed"]
        self.assertEqual(len(said), 1)
        self.assertTrue(said[0]["alert"])
        self.assertIn("ranks after every program whose counts can be read", said[0]["text"])
        [row] = swarm_bands.read(self.root, lanes=elane.LANES, waiting=True)
        self.assertIsNone(row["seat_activity"])
        self.assertIsNone(B.seat_k(row["seat_activity"]))
        self.assertEqual(elane.seat_backfill(self.gate), [], "the runner is back, but the hour has not passed")
        self.clock.set(self.clock() + elane.SEAT_RETRY_SECONDS + 1)
        self.assertEqual(elane.seat_backfill(self.gate), [fam["id"]])
        # The gate's equity round is where the House calls it.
        self.store.set_state(fam["id"], **{elane.SEAT_KEY: None})
        out: dict = {"looked": [], "held": []}
        self.gate.equity_round(out)
        self.assertEqual(out.get("seat_counts"), [fam["id"]])
        self.assertTrue(elane.seat_recorded(self.store.family(fam["id"])["state"], 1, sha))


if __name__ == "__main__":
    unittest.main()
