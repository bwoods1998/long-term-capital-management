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

import contextlib
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
from league.equity import ctx as C
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
#: Core's fee and ctx constructors, which `T.BookTest` also stubs for the book's tests: the real engine needs its own.
REAL_CORE = ((config, "sell_fees", config.sell_fees), (C, "inputs_from_fetch", C.inputs_from_fetch),
             (C, "lot_row", C.lot_row), (C, "closed_row", C.closed_row))
FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO = Path(__file__).resolve().parents[2]
SUNDAY, FRIDAY, MONDAY = dt.date(2026, 10, 11), T.FRIDAY, T.MONDAY
E = D("2229")
ETFS = ("SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV")
SETTINGS = B.SeatSettings(B.ACTIVITY_FREE, D("0.25"), 10)
ON = {"elane": {"mode": "gate"}, "dlane": {"mode": "gate"}}


@contextlib.contextmanager
def real_engine():
    """Core's real functions for the body (a run of the real engine inside a test whose book stubs them)."""
    with contextlib.ExitStack() as stack:
        for target, name, value in REAL_CORE:
            stack.enter_context(mock.patch.object(target, name, value))
        yield


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
        for sentence in (R.A24_SEAT_RULE, R.A24_SEAT_COSTS, R.A30_SEAT_AMENDMENT):
            self.assertIn(sentence, page)
        # A30 amended A24 before the rule was live: its three points and what it left as it was, in the words the
        # captain registered, beside A24's own (which are unchanged).
        amended = R.A30_SEAT_AMENDMENT
        for words in ("a free seat is filled before the idle test", "would still wait once every free seat is filled",
                      "measured under that slower order", "does not run while the House refuses every open",
                      "paused, the kill switch, a stop, a freeze, the grant not ratified, the paper proof's BUY stage "
                      "not passed", "left out of every program's idle count and of its seated-session count",
                      "A lost buy is not flat", "no seat change ends in a House sale",
                      "a daily quarter-sleeve slice buys rank and immunity from the idle rule"):
            self.assertIn(words, amended)
        self.assertEqual((R.SEAT_RULE["amended"]["id"], R.SEAT_RULE["amended"]["registered"],
                          R.SEAT_RULE["amended"]["text"]), ("A30", "2026-10-11T20:47Z", amended))
        self.assertEqual(swarm_bands.SEAT_PLAN_KEY, L.SEAT_KEY, "the swarm reads the book's own key")

    def test_the_readers_new_keyword_shadows_nothing_of_the_options_read(self):
        """The swarm's `read` grew one keyword for the book (`queued`). It is not named `waiting`: that is this
        module's own function, which the OPTIONS read calls to hide the Candidates waiting for a `dlane.roster` seat
        (a parameter of that name made the options read fail whenever the roster was on; league/tests/
        test_swarm_roster.py holds the read itself)."""
        import inspect

        for fn in (swarm_bands.read, swarm_bands._read_equity):
            names = set(inspect.signature(fn).parameters)
            self.assertIn("queued", names)
            self.assertFalse(names & {n for n in dir(swarm_bands) if callable(getattr(swarm_bands, n))},
                             f"{fn.__name__}: a parameter shadows a function of the module")
        self.assertTrue(callable(swarm_bands.waiting))


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
        self.assertGreaterEqual(len(doc["vectors"]), 31)
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
                    self.assertEqual(plan["seat"][-1], plan["for"], "the program it yields to takes the seat it frees")
                    self.assertEqual(len(plan["seat"]), v["seats"] - len(holders) + 1, "after every free seat is filled")

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
                free = seats - len(holders)
                self.assertGreaterEqual(free, 0)
                left = B.seat_order(waiting)[free:]
                self.assertTrue(any(not w.flagged for w in left), "an unflagged program is left waiting after the free seats")
                self.assertEqual(plan["for"], next(w.family for w in left if not w.flagged))
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
        [row] = swarm_bands.read(self.root, lanes=elane.LANES, queued=True)
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
        [row] = swarm_bands.read(self.root, lanes=elane.LANES, queued=True)
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


# ============================================================================================================ the book
class SeatCase(T.BookTest):
    """The book's harness (league/tests/test_equity_book.py) with money's and the swarm's REAL functions put back
    (`size_entry`, `available_cash`, `next_band`, `sized_sleeve_share`), at E = $2,229 and the account all cash."""

    def setUp(self):
        super().setUp()
        for target, name, value in ((Z, "size_entry", REAL_SIZE), (M, "available_cash", REAL_AVAILABLE),
                                    (B, "next_band", REAL_NEXT_BAND), (B, "sized_sleeve_share", REAL_SIZED_SHARE)):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def fresh(self) -> Path:
        return Path(tempfile.mkdtemp(dir=self.root))

    def floor(self, **kw) -> "Floor":
        return Floor(self, **kw)

    def assert_nothing_was_ever_forced(self, f: "Floor", *, own_sells: int = 0) -> None:
        """What the seat rule may never do, read off the whole run: no exit of the House's for a seat (every program
        here declares a hold longer than the run, so the House plans none at all), no sale but a program's own, and no
        program refused a buy because of its seat."""
        h = f.h
        self.assertEqual(h.intents(kind="house_exit"), [], "the House planned an exit")
        sells = [body for body in h.venue.sent if body["side"] == "sell"]
        self.assertEqual(len(sells), own_sells, "a sale that no program asked for")
        self.assertEqual(len(h.intents(kind="sell")), own_sells)
        self.assertFalse([i.why for i in h.intents() if "seat" in (i.why or "")], "an intent refused for a seat")
        for inst in h.book._instances():
            if str(inst.why).startswith(L.YIELDED):
                self.assertEqual(h.book._lots(instance=inst.id), [], f"{inst.id} yielded while it held a lot")


class Floor:
    """A House for the seat tests: `seats` seats at A20's sleeve, the rule in force, invented programs that the fake
    decider plays (a program plans what the test tells it to), sessions from Monday Oct 12, 2026. `roster`: the
    swarm's seat count (None: the table's alone)."""

    def __init__(self, case: SeatCase, *, seats: int = 3, sleeve: str = "0.50", roster: int | None = None):
        self.case = case
        self.h = h = T.Harness(case.fresh(), cash=str(E), E=str(E), table=X.table_at(seats, sleeve).equity)
        case.addCleanup(h.state.close)
        h.families.roster = roster
        h.market.quotes.update({"XLK": (D("249.90"), D("250.10")), "XLF": (D("49.99"), D("50.01"))})
        self.days = sessions(MONDAY, 60)
        for symbol in ETFS[:6]:
            self.bars(symbol)

    def bars(self, symbol: str, n: int = 90) -> None:
        """Invented 1Day bars of `symbol` through the floor's last day, stamped at each session's own New York
        midnight (the harness's own `make_bars` stamps 04:00Z the year round, which is the day before once daylight
        time ends on Nov 1)."""
        mid = float(sum(self.h.market.quote(symbol)) / 2)
        days, d = [], self.days[-1]
        while len(days) < n:
            if S.is_session(d):
                days.append(d)
            d -= dt.timedelta(days=1)
        raw, adj = [], []
        for i, day in enumerate(sorted(days)):
            c = round(mid + 0.02 * i, 2)
            stamp = dt.datetime(day.year, day.month, day.day, tzinfo=T.NY).astimezone(dt.timezone.utc)
            row = {"t": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": c - 0.5, "h": c + 1.0, "l": c - 1.0, "c": c,
                   "v": 1000000 + i}
            raw.append(row)
            adj.append({**row, **{k: round(row[k] * 0.99, 4) for k in ("o", "h", "l", "c")}})
        self.h.market.bar_rows["raw"][symbol], self.h.market.bar_rows["all"][symbol] = raw, adj

    def key(self, family: str) -> str:
        return L.instance_key(family, 1)

    def add(self, family: str, symbol: str = "SPY", *, k: int | None = None, passed: float = 0.0, band: str = "candidate",
            seeded: bool = False, activity: dict | None = None) -> None:
        row = T.family_row(family, band=band, symbols=(symbol,))
        row.update(seeded=seeded, passed_at=passed, seat_activity=activity if activity is not None else
                   (None if k is None else counts(k)))
        self.h.families.rows[family] = row
        self.h.decider.needs[self.key(family)] = {"symbols": [symbol], "history": 5, "max_hold_sessions": 60}

    def plan(self, family: str, *intents: dict) -> None:
        self.h.decider.plans[self.key(family)] = list(intents)

    def session(self, n: int, *, windows: bool = True, before_open=None) -> dict:
        """Session `n` (0: Monday Oct 12): its open window, then its decision (16:21 the band sync and the bars, 16:31
        the decide, 16:32 the seating pass). Returns the decision minutes' summaries merged."""
        day = self.days[n]
        if before_open is not None:
            before_open()
        if windows:
            for hh, mm in ((9, 31), (9, 33)):
                self.h.tick(hh, mm, day=day)
        out = {}
        for hh, mm in ((16, 21), (16, 31), (16, 32)):
            out.update({k: v for k, v in self.h.tick(hh, mm, day=day).items() if k not in out or k in ("seats", "decided")})
        return out

    def run(self, first: int, last: int, **kw) -> None:
        for n in range(first, last + 1):
            self.session(n, **kw)

    def band(self, family: str) -> str:
        return str(self.h.families.rows[family]["band"])

    def seats(self) -> dict:
        return self.h.book.seats()

    def holders(self) -> list[str]:
        return [x["family"] for x in self.seats()["holders"]]

    def waiting(self) -> list[tuple]:
        return [(w["family"], w["rank"], w["flagged"]) for w in self.seats()["waiting"]]

    def events(self, kind: str = "equity.seat") -> list[dict]:
        return [payload for k, payload in self.h.events if k == kind]

    def inst(self, family: str) -> L.Instance:
        return self.h.book._instance(self.key(family))

    def loss(self, usd: str, n: int) -> L.Lot:
        """A closed Probe lot of a program long gone, its net at -`usd`, on session `n`: a realized loss in the shared
        budget's window and nothing else (it is no family's and holds nothing)."""
        h = self.h
        gone = L.Instance("gone@1:r", "gone", 1, "beta", "r0", T.CODE, {}, "candidate", False, 20, created_at=1.0,
                          retired_at=2.0, why="retired: long ago")
        h.book._save_instance(gone)
        lot = h.lot(gone, "DIA", "1", "450", opened=FRIDAY)
        h.venue.held["DIA"] -= D("1")
        lot.status, lot.qty, lot.cash, lot.exit_day, lot.closed_at = "closed", D(0), -D(usd), self.days[n].isoformat(), \
            T.at(self.days[n], 9, 30)
        lot.exit_px, lot.exit_at, lot.reason = D("449"), "open", "program"
        h.book._save_lot(lot)
        return lot


class TheBook(SeatCase):
    # ---------------------------------------------------------------------------------------------- the free seat
    def test_a_free_seat_goes_to_the_best_ranked_waiting_program(self):
        """Three seats, five passers. K decides (not the pass time, not the id, not the order of the rows); the two
        left wait in rank order, and the plan says so in positions, never in K."""
        f = self.floor()
        f.add("e-early-low", "SPY", k=10, passed=1.0)
        f.add("d-late-high", "QQQ", k=200, passed=5.0)
        f.add("c-mid", "IWM", k=90, passed=2.0)
        f.add("b-tie-later", "DIA", k=90, passed=3.0)
        f.add("a-unread", "XLK", k=None, passed=0.0)
        out = f.session(0)
        self.assertEqual(sorted(f.holders()), ["b-tie-later", "c-mid", "d-late-high"])
        self.assertEqual(f.waiting(), [("e-early-low", 1, False), ("a-unread", 2, False)],
                         "the unread one last, though it passed first and its id sorts first")
        self.assertEqual([(e["action"], e["family"], e["rank"]) for e in f.events()],
                         [("seated", "d-late-high", 1), ("seated", "c-mid", 2), ("seated", "b-tie-later", 3)])
        self.assertEqual({f.band(x) for x in f.holders()}, {"probe"})
        self.assertEqual((f.band("e-early-low"), f.band("a-unread")), ("candidate", "candidate"))
        self.assertIsNone(f.inst("e-early-low"), "a waiting program has no instance, so no intent and no order")
        self.assertIn("equity seats (activity-1-free, 3 of 3)", out["seats"])
        self.assertIn("waiting: e-early-low (1), a-unread (2)", out["seats"])
        # A seat frees (the swarm retires a seated family): the best-ranked waiting program takes it, in the same sync.
        f.h.families.rows["c-mid"]["band"] = "retired"
        f.session(1)
        self.assertEqual(sorted(f.holders()), ["b-tie-later", "d-late-high", "e-early-low"])
        self.assertEqual(f.waiting(), [("a-unread", 1, False)])
        self.assertEqual(f.seats()["last"]["family"], "e-early-low")
        self.assert_nothing_was_ever_forced(f)

    def test_the_plan_and_every_public_word_carry_positions_and_never_k(self):
        f = self.floor()
        for i, family in enumerate(("p1", "p2", "p3", "p4", "p5")):
            f.add(family, ETFS[i], activity={"validation": {"close_days": 137 + i, "sessions": 250},
                                             "train": {"close_days": 1211 + i, "sessions": 1759}}, passed=float(i))
        f.run(0, 1)
        health = f.h.book.health()
        text = json.dumps([health, [p for _, p in f.h.events], f.h.alerts], default=str)
        for word in ("close_days", "seat_activity", "1759", "1211", "1215", '"k"', "_k"):
            self.assertNotIn(word, text)
        plan = health["seats"]
        self.assertEqual(set(plan["holders"][0]), {"family", "version", "band", "seeded", "since", "seated_sessions",
                                                   "quiet_sessions", "left_out", "flat", "idle"})
        self.assertEqual(plan["left_out"], [], "no session was left out of the idle clock")
        self.assertEqual(set(plan["waiting"][0]), {"family", "version", "rank", "seeded", "flagged", "ranked"})
        self.assertEqual((plan["rule"], plan["seats"], plan["idle_sessions"], plan["order"]),
                         ("activity-1-free", 3, 10, "the book's plan (equity_money.probe.seat)"))
        self.assertEqual([w["rank"] for w in plan["waiting"]], [1, 2])

    # ---------------------------------------------------------------------------------------------- the idle seat
    def rare(self, *, waits: bool = True, **floor) -> Floor:
        """Three seats: `busy-1` and `busy-2` each buy a lot of SPY at session 1 and hold it; `rare` is seated and
        plans nothing. `late` (unflagged, a low K) waits from session 0 when `waits`."""
        f = self.floor(**floor)
        f.add("busy-1", "SPY", k=200, passed=1.0)
        f.add("busy-2", "SPY", k=150, passed=2.0)
        f.add("rare", "QQQ", k=100, passed=3.0)
        if waits:
            f.add("late", "IWM", k=1, passed=9.0)
        for family in ("busy-1", "busy-2"):
            f.plan(family, {"buy": "SPY", "share": 0.5, "at": "open"})
        f.session(0)
        for family in ("busy-1", "busy-2"):
            f.plan(family)
        self.assertEqual(sorted(f.holders()), ["busy-1", "busy-2", "rare"])
        return f

    def test_an_idle_seat_yields_at_ten_seated_sessions_and_only_then(self):
        f = self.rare()
        f.run(1, 9)
        self.assertEqual(len(f.h.lots(open_only=True)), 2, "the two busy programs hold their lots")
        nine = {x["family"]: x for x in f.seats()["holders"]}["rare"]
        self.assertEqual((nine["seated_sessions"], nine["flat"], nine["idle"], nine["quiet_sessions"]), (9, True, False, None))
        self.assertEqual(f.band("rare"), "probe", "nine seated sessions: not yet")
        out = f.session(10)
        self.assertEqual(sorted(f.holders()), ["busy-1", "busy-2", "late"], "the waiting program takes the seat in the same sync")
        self.assertEqual(f.waiting(), [("rare", 1, True)], "it waits, flagged idle")
        self.assertEqual((f.band("rare"), f.band("late")), ("candidate", "probe"))
        self.assertNotIn(f.key("rare"), f.h.state.get("eq_sticky") or {}, "a yield is never sticky")
        inst = f.inst("rare")
        self.assertTrue(inst.retired_at is not None and inst.why.startswith("yielded: it yields its idle seat"), inst.why)
        self.assertEqual([(e["action"], e["family"], e.get("for")) for e in f.events()[-2:]],
                         [("yielded", "rare", "late"), ("seated", "late", None)])
        self.assertIn("late waits unflagged", f.events()[-2]["why"])
        [alert] = [text for level, text in f.h.alerts if "yields its idle seat" in text]
        self.assertIn("it holds no lot, so nothing is sold", alert)
        self.assertEqual(f.seats()["idle"], {"rare": {"day": f.days[10].isoformat(),
                                                      "why": "it yielded an idle seat and waits for a free one"}})
        self.assertEqual((f.seats()["last"]["action"], f.seats()["last"]["family"]), ("seated", "late"))
        self.assertIn("late seated 0 sessions", out["seats"])
        self.assertIn("waiting: rare (1, idle-flagged)", out["seats"])
        # `late` is decided for the same close, and the busy programs were never touched.
        self.assertEqual(f.inst("late").last_decided_day, f.days[10].isoformat())
        self.assertEqual({f.inst(x).retired_at for x in ("busy-1", "busy-2")}, {None})
        self.assert_nothing_was_ever_forced(f)

    def test_it_keeps_its_seat_while_nobody_waits_and_yields_at_once_when_someone_does(self):
        f = self.rare(waits=False)
        f.run(1, 14)
        rare = {x["family"]: x for x in f.seats()["holders"]}["rare"]
        self.assertEqual((rare["idle"], rare["seated_sessions"]), (True, 14), "flagged idle, and it keeps its seat")
        self.assertEqual((f.band("rare"), f.events()[3:]), ("probe", []), "nobody waits: nothing moves")
        f.add("late", "IWM", k=1, passed=9.0)                  # a program passes its look now
        f.session(15)
        self.assertEqual(sorted(f.holders()), ["busy-1", "busy-2", "late"], "at the next decision: at once")
        self.assertEqual(f.waiting(), [("rare", 1, True)])
        self.assert_nothing_was_ever_forced(f)

    def test_the_seating_pass_never_yields(self):
        """A program that passes its look between two decisions waits for the next decision's sync: the seating pass
        (every minute) fills FREE seats only."""
        f = self.rare(waits=False)
        f.run(1, 12)
        f.add("late", "IWM", k=1, passed=9.0)
        for mm in (33, 34, 35):
            f.h.tick(16, mm, day=f.days[12])
        self.assertEqual(f.band("rare"), "probe")
        self.assertEqual(f.waiting(), [("late", 1, False)], "the plan shows it waiting, first in line")
        f.h.tick(9, 31, day=f.days[13])
        self.assertEqual(f.band("rare"), "probe")
        f.session(13, windows=False)
        self.assertEqual((f.band("rare"), f.band("late")), ("candidate", "probe"))

    def asked(self, name: str) -> tuple[Floor, list[str]]:
        """`rare` (seated at session 0, with `late` waiting) plans ONE buy at session 2's decision, which session 3's
        open window works under the condition `name`. Returns the floor after session 3 and what the book wrote of
        the buy (its intent's reason, its orders' statuses and reasons)."""
        f = self.rare()
        f.run(1, 2)
        h = f.h
        symbol = "SPY" if name == "instrument" else "QQQ"
        if name == "instrument":
            h.decider.needs[f.key("rare")] = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 60}
            h.book._loaded.pop(f.key("rare"), None)
        # Session 2 is decided: the buy is written as that decision would have written it, one planned intent for
        # session 3's open.
        h.intent(f.inst("rare"), "buy", symbol=symbol, share="0.5", at_="open", exec_day=f.days[3], decided=f.days[2])
        risk = L.probe_figures(h.state.rows, weights={"etf": D("0.20"), "stock": D("0.40")}).open_risk
        lot = None
        if name == "budget refused":
            lot = f.loss("400", 3)
        elif name == "budget cut under the minimum":
            lot = f.loss(str(D("400") - risk - D("1")), 3)
        elif name == "budget cut and the gateway refuses":
            lot = f.loss(str(D("400") - risk - D("20")), 3)
            h.venue.submit_mode = "gateway"
        elif name == "invested":
            h.options.book_loss = E
        elif name == "cash":
            self.cash, h.venue.cash = h.venue.cash, D("30")
        elif name == "gateway refused":
            h.venue.submit_mode = "gateway"
        elif name == "venue rejected":
            h.venue.submit_mode = "reject"
        for hh, mm in ((9, 31), (9, 33)):
            h.tick(hh, mm, day=f.days[3])
        h.venue.submit_mode, h.options.book_loss = "ok", D(0)
        if name == "cash":
            h.venue.cash = self.cash
        if lot is not None:
            h.state.execute("DELETE FROM eq_lots WHERE lid=?", (lot.lid,))
        mine = f.key("rare")
        wrote = [i.why for i in h.intents(instance=mine, kind="buy")] + \
                [f"{o.status}: {o.why}" for o in h.orders() if o.instance == mine]
        for hh, mm in ((16, 21), (16, 31), (16, 32)):
            h.tick(hh, mm, day=f.days[3])
        return f, wrote

    def test_what_counts_as_asked_and_what_does_not(self):
        """A24 item 3, each case through the real sizing and the real order path. ASKED (the seat is kept until ten
        sessions after it): a buy that reached the venue (filled; rejected by the venue itself), and one the LOSS
        BUDGET refused, cut under the minimum order, or cut (even when the gateway then refused the cut order). NOT
        ASKED (the seat yields at ten seated sessions, as if nothing had been tried): a buy refused by the
        instrument cap, the invested cap or cash, and one the gateway refused before the venue."""
        cases = {
            "filled": (True, "filled", None),
            "venue rejected": (True, "the rejected buy", "rejected: entry (intent"),
            "budget refused": (True, "sizing (budget): refused: the shared loss budget has", None),
            "budget cut under the minimum": (True, "sizing (min_order): skipped", None),
            "budget cut and the gateway refuses": (True, "the refused buy", "refused: entry (budget:"),
            "instrument": (False, "sizing (", None),
            "invested": (False, "sizing (invested): refused", None),
            "cash": (False, "sizing (cash): refused", None),
            "gateway refused": (False, "the refused buy", "refused: entry (intent"),
        }
        for name, (asked, intent_says, order_says) in cases.items():
            with self.subTest(name):
                f, wrote = self.asked(name)
                self.assertIn(intent_says, wrote[0], wrote)
                if order_says:
                    self.assertTrue(any(w.startswith(order_says) for w in wrote[1:]), wrote)
                if name == "instrument":
                    self.assertIn("SPY may hold", wrote[0])
                    self.assertFalse(L._budget_asked(wrote[0]))
                if name == "budget cut under the minimum":
                    self.assertIn(L.BUDGET_WORDS, wrote[0], "the skipped entry names the cap that cut it")
                    self.assertTrue(L._budget_asked(wrote[0]))
                last = f.h.book._last_ask(f.key("rare"))
                self.assertEqual(last, f.days[3].isoformat() if asked else None, name)
                sold = 0
                if name == "filled":                           # it sells its lot itself at session 4, and is flat again
                    [lot] = f.h.book._lots(instance=f.key("rare"))
                    f.h.intent(f.inst("rare"), "sell", symbol=lot.symbol, lid=lot.lid, at_="open", exec_day=f.days[4],
                               decided=f.days[3])
                    sold = 1
                f.run(4, 10)
                self.assertTrue(f.h.book._flat(f.key("rare")) or f.band("rare") != "probe")
                if asked:
                    self.assertEqual(f.band("rare"), "probe", f"{name}: it asked at session 3, so it is not idle at 10")
                    held = {x["family"]: x for x in f.seats()["holders"]}["rare"]
                    self.assertEqual((held["quiet_sessions"], held["idle"]), (7, False))
                    f.run(11, 12)
                    self.assertEqual(f.band("rare"), "probe", "nine sessions since it asked")
                    f.session(13)
                    self.assertEqual((f.band("rare"), f.band("late")), ("candidate", "probe"), "ten since: it yields")
                else:
                    self.assertEqual((f.band("rare"), f.band("late")), ("candidate", "probe"),
                                     f"{name}: not asked, so idle at ten seated sessions")
                self.assert_nothing_was_ever_forced(f, own_sells=sold)

    def test_the_budgets_words_are_the_sizing_rules_own(self):
        """`BUDGET_WORDS` is how a buy cut under the minimum order names the loss budget: held to the real
        `size_entry`, and to no other cap's words."""
        base = dict(symbol="SPY", klass="etf", share=D("0.5"), usd=None, limit_price=D("100"), E=E,
                    sleeve_equity=D("1000"), sleeve_free_cash=D("1000"), sleeve_symbol_value=D(0),
                    position_share=D("0.5"), account_symbol_value=D(0), invested_now=D(0), invested_share=D(1),
                    available_cash=D("2000"), cash=D("2000"), any_short=False, budget_room=D("400"), weight=D("0.20"),
                    min_order_usd=D("10"))
        cut = REAL_SIZE(Z.SizingInputs(**{**base, "budget_room": D("1")}))
        self.assertEqual(cut.binding, "min_order")
        self.assertIn(L.BUDGET_WORDS, cut.reason)
        self.assertTrue(L._budget_asked(f"sizing ({cut.binding}): {cut.reason}"))
        refused = REAL_SIZE(Z.SizingInputs(**{**base, "budget_room": D("0")}))
        self.assertTrue(L._budget_asked(f"the entry cut-off passed (last: sizing ({refused.binding}): {refused.reason})"))
        for other in ({"account_symbol_value": D("1114")}, {"invested_now": E - D("5")}, {"available_cash": D("5")},
                      {"sleeve_free_cash": D("5")}, {"sleeve_symbol_value": D("499")}):
            got = REAL_SIZE(Z.SizingInputs(**{**base, **other}))
            self.assertEqual(got.usd, 0, other)
            self.assertNotIn(L.BUDGET_WORDS, got.reason, other)
            self.assertFalse(L._budget_asked(f"sizing ({got.binding}): {got.reason}"), other)

    def test_a_program_that_is_not_flat_is_never_idle(self):
        """Each way of not being flat, alone: an open lot, a working order, a planned intent. None yields, however
        long it has been seated and however well the waiting program ranks."""
        for what in ("lot", "working order", "planned intent"):
            with self.subTest(what):
                f = self.rare()
                h = f.h
                f.run(1, 9)
                inst = f.inst("rare")
                h.clock.set(T.at(f.days[10], 16, 20, 50))
                if what == "lot":                              # a lot of its own, held (bought long ago: not an ask)
                    h.lot(inst, "QQQ", "0.5", "500", opened=FRIDAY)
                elif what == "working order":                  # an order being sent this very minute
                    h.book._save_order(L.Order(900, "lq-test-900", inst.id, "rare", "sell", "QQQ", "etf", "open", D("1"),
                                               D("1"), 10, "pending", h.clock(), FRIDAY.isoformat()))
                else:                                          # an intent of its own still to execute
                    h.intent(inst, "sell", symbol="QQQ", lid=None, at_="close", exec_day=f.days[59], decided=f.days[2])
                self.assertFalse(h.book._flat(inst.id))
                self.assertIsNone(h.book._last_ask(inst.id), "nothing here is an asked buy: only flatness holds the seat")
                h.tick(16, 21, day=f.days[10])
                self.assertEqual((f.band("rare"), f.band("late")), ("probe", "candidate"), what)
                held = {x["family"]: x for x in f.seats()["holders"]}["rare"]
                self.assertEqual((held["seated_sessions"], held["flat"], held["idle"]), (10, False, False))
                self.assertIsNone(f.inst("rare").retired_at)

    def test_the_yield_is_one_transaction_that_finds_it_flat_or_does_nothing(self):
        """THE STRUCTURAL CHECK (the review's A9): the retirement happens only inside the state transaction that found
        the instance flat. Flat when the plan was made and not flat when the transaction looks: no band move, no
        retirement, no flag, and the seat is kept. And a row that changed under the plan yields nothing either."""
        f = self.rare()
        f.run(1, 9)
        calls = {"n": 0}
        real = L.EquityBook._flat

        def flat(book, key):
            calls["n"] += 1
            return real(book, key) if not (key == f.key("rare") and calls["n"] > 3) else False

        # (The plan asks once for each holder: three calls. The fourth is the transaction's own.)
        with mock.patch.object(L.EquityBook, "_flat", flat):
            f.session(10)
        self.assertEqual((f.band("rare"), f.band("late")), ("probe", "candidate"))
        self.assertIsNone(f.inst("rare").retired_at)
        self.assertEqual(f.seats().get("idle"), {})
        self.assertEqual([e["action"] for e in f.events()], ["seated"] * 3)
        with mock.patch.object(f.h.families, "confirm_band", return_value=False):
            f.session(11)
        self.assertEqual((f.band("rare"), f.inst("rare").retired_at), ("probe", None), "the row changed: no yield")
        f.session(12)
        self.assertEqual((f.band("rare"), f.band("late")), ("candidate", "probe"), "and then, flat and confirmed, it yields")
        self.assert_nothing_was_ever_forced(f)

    def test_one_yield_a_decision_day(self):
        """Two idle seats and two programs waiting: one yields at a decision, the other at the next; and a band sync
        that runs again on the same day (it does, every minute, while a family's standing cannot be read) yields
        nothing more."""
        f = self.floor()
        f.add("busy", "SPY", k=200, passed=1.0)
        f.add("rare-hi", "QQQ", k=100, passed=2.0)
        f.add("rare-lo", "IWM", k=50, passed=3.0)
        f.add("late-1", "DIA", k=2, passed=8.0)
        f.add("late-2", "XLK", k=1, passed=9.0)
        f.plan("busy", {"buy": "SPY", "share": 0.5, "at": "open"})
        f.session(0)
        f.plan("busy")
        f.run(1, 9)
        day = f.days[10]
        f.h.tick(16, 21, day=day)
        self.assertEqual((f.band("rare-lo"), f.band("rare-hi")), ("candidate", "probe"), "the lowest K yields first")
        self.assertEqual(sorted(f.holders()), ["busy", "late-1", "rare-hi"])
        f.h.state.execute("DELETE FROM kv WHERE key='eq_synced'")           # the same day's sync runs again
        f.h.tick(16, 22, day=day)
        self.assertEqual(f.band("rare-hi"), "probe", "one yield a decision day")
        self.assertEqual(f.seats()["yield_day"], day.isoformat())
        f.h.tick(16, 31, day=day)
        f.session(11)
        self.assertEqual(sorted(f.holders()), ["busy", "late-1", "late-2"])
        self.assertEqual(f.waiting(), [("rare-hi", 1, True), ("rare-lo", 2, True)], "flagged, in rank order")
        self.assert_nothing_was_ever_forced(f)

    def test_two_rare_traders_do_not_rotate(self):
        """One seat (the swarm's roster at one), two programs that never trade. The first yields to the second at ten
        sessions; the second is then idle itself, but only an idle-flagged program waits, so it keeps the seat, for as
        long as nobody unflagged arrives. When one does it yields at the next decision. The flagged ones come back
        only into a free seat, by rank."""
        f = self.floor(roster=1)
        f.add("rare-1", "SPY", k=100, passed=1.0)
        f.add("rare-2", "QQQ", k=50, passed=2.0)
        f.run(0, 9)
        self.assertEqual(f.holders(), ["rare-1"])
        f.session(10)
        self.assertEqual((f.holders(), f.waiting()), (["rare-2"], [("rare-1", 1, True)]))
        f.run(11, 34)
        held = f.seats()["holders"][0]
        self.assertEqual((held["family"], held["idle"], held["seated_sessions"]), ("rare-2", True, 24))
        self.assertEqual([e["action"] for e in f.events()], ["seated", "yielded", "seated"],
                         "twenty-four sessions on: no rotation")
        f.add("trader", "IWM", k=3, passed=30.0)
        f.plan("trader", {"buy": "IWM", "share": 0.5, "at": "open"})
        f.session(35)
        f.plan("trader")
        self.assertEqual(f.holders(), ["trader"])
        self.assertEqual(f.waiting(), [("rare-1", 1, True), ("rare-2", 2, True)])
        f.run(36, 47)
        self.assertEqual(f.holders(), ["trader"], "it holds a lot: never idle, never unseated")
        # Two more seats open (the swarm's roster back at three): the flagged programs return, by rank, with no look.
        f.h.families.roster = 3
        f.session(48, windows=False)
        self.assertEqual(sorted(f.holders()), ["rare-1", "rare-2", "trader"])
        self.assertEqual([(e["action"], e["family"], e["rank"]) for e in f.events()[-2:]],
                         [("returned", "rare-1", 1), ("returned", "rare-2", 2)])
        self.assertIn("with no new look", f.events()[-1]["why"])
        self.assertEqual(f.seats()["idle"], {}, "seated again: the flag is cleared")
        back = {x["family"]: x for x in f.seats()["holders"]}["rare-1"]
        self.assertEqual((back["since"], back["seated_sessions"]), (f.days[48].isoformat(), 0), "its clock starts again")
        inst = f.inst("rare-1")
        self.assertEqual((inst.retired_at, inst.band, inst.id), (None, "probe", f.key("rare-1")), "the same instance key")
        self.assert_nothing_was_ever_forced(f)

    def test_a_yielded_program_returns_in_the_seating_pass_and_is_asked_for_the_same_close(self):
        f = self.rare()
        f.run(1, 10)
        self.assertEqual(f.waiting(), [("rare", 1, True)])
        f.h.families.rows["busy-1"]["band"] = "retired"                    # the swarm retires a seated family...
        f.session(11)
        # ...whose lot leaves by the House's own rule for a retired program (A8.5), not by the seat rule; the free
        # seat goes to the only waiting program, the flagged one, in that same sync.
        self.assertEqual(sorted(f.holders()), ["busy-2", "late", "rare"])
        self.assertEqual(f.inst("rare").last_decided_day, f.days[11].isoformat())
        self.assertEqual([i.tag for i in f.h.intents(kind="house_exit")], ["retired"])
        self.assertEqual(f.h.intents(kind="house_exit")[0].instance, f.key("busy-1"))
        # The same return in the seating pass (a seat that frees between two decisions).
        g = self.rare(seats=4, roster=3)
        g.run(1, 10)
        self.assertEqual(g.waiting(), [("rare", 1, True)])
        g.h.families.roster = 4                                          # a fourth seat, mid-evening
        g.h.tick(16, 40, day=g.days[10])
        self.assertEqual(sorted(g.holders()), ["busy-1", "busy-2", "late", "rare"])
        inst = g.inst("rare")
        self.assertEqual((inst.retired_at, inst.band, inst.last_decided_day), (None, "probe", g.days[10].isoformat()))
        self.assertEqual(g.events()[-1]["action"], "returned")

    # ---------------------------------------------------------------------- nobody trading is stopped; nothing is sold
    def test_no_arrival_stops_a_program_that_trades(self):
        """NO OUTRANKING, on the book: three seated programs of low K, each trading; a program of far higher K passes
        its look and waits for twenty sessions. Nobody yields, nobody is made exit-only (the seated programs' later
        buys are sized and sent like any other), and the House sells nothing."""
        f = self.floor()
        for i, family in enumerate(("slow-1", "slow-2", "slow-3")):
            f.add(family, ETFS[i], k=1 + i, passed=float(i))
            f.plan(family, {"buy": ETFS[i], "share": 0.2, "at": "open"})
        f.session(0)
        f.add("fast", "DIA", k=250, passed=50.0)
        f.run(1, 20)
        self.assertEqual(sorted(f.holders()), ["slow-1", "slow-2", "slow-3"])
        self.assertEqual(f.waiting(), [("fast", 1, False)])
        self.assertEqual([e["action"] for e in f.events()], ["seated"] * 3)
        buys = [body for body in f.h.venue.sent if body["side"] == "buy"]
        self.assertGreaterEqual(len(buys), 6, "they went on buying, session after session")
        self.assertEqual({i.status for i in f.h.intents(kind="buy") if i.exec_day > f.days[5].isoformat()
                          and i.exec_day <= f.days[20].isoformat()} - {"done", "refused"}, set())
        self.assertFalse([i.why for i in f.h.intents(kind="buy") if "not at Probe" in (i.why or "")])
        self.assertEqual({f.inst(x).retired_at for x in ("slow-1", "slow-2", "slow-3")}, {None})
        self.assertIsNone(f.inst("fast"))
        self.assert_nothing_was_ever_forced(f)

    def test_a_long_run_of_random_programs_never_sells_for_a_seat(self):
        """A property: sixty sessions, eight programs passing at random times with random K, each trading at random
        (or never), three seats. Whatever happens: no exit of the House's, no sale but a program's own, every yielded
        instance flat when it yielded and ever after, at most one yield a decision day, never more seated than
        seats, and a program that holds a lot never loses its seat."""
        for seed in (3, 24):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                f = self.floor()
                arrive = sorted((rng.randint(0, 30), f"p{i}") for i in range(8))
                style = {name: rng.choice(["never", "never", "holds", "weekly"]) for _, name in arrive}
                sold = 0
                for n in range(0, 56):
                    for at, name in arrive:
                        if at == n:
                            f.add(name, ETFS[int(name[1:]) % 6], k=rng.choice([None, 0, 5, 80, 240]), passed=float(n))
                    before = {x["family"] for x in (f.seats() or {}).get("holders", [])}
                    lots_before = {lot.family for lot in f.h.lots(open_only=True)}
                    for name in before:
                        symbol = f.h.families.rows[name]["symbols"][0]
                        mine = f.h.book._lots(instance=f.key(name))
                        if style[name] == "holds" and not mine and rng.random() < 0.5:
                            f.plan(name, {"buy": symbol, "share": 0.3, "at": "open"})
                        elif style[name] == "weekly" and n % 5 == 0 and not mine:
                            f.plan(name, {"buy": symbol, "share": 0.3, "at": "close"})
                        elif style[name] == "weekly" and mine and n % 5 == 2 and not f.h.book._exit_pending(mine[0].lid):
                            f.plan(name, {"sell": mine[0].lid, "at": "open"})
                            sold += 1
                        else:
                            f.plan(name)
                    f.session(n)
                    after = {x["family"] for x in f.seats()["holders"]}
                    self.assertLessEqual(len(after), 3)
                    self.assertTrue(lots_before & before <= after, "a program holding a lot lost its seat")
                    yields = [e for e in f.events() if e["action"] == "yielded" and e["day"] == f.days[n].isoformat()]
                    self.assertLessEqual(len(yields), 1)
                real_sells = len([i for i in f.h.intents(kind="sell") if i.status != "refused"])
                self.assertEqual(f.h.intents(kind="house_exit"), [])
                self.assertEqual(len([b for b in f.h.venue.sent if b["side"] == "sell"]), real_sells)
                for inst in f.h.book._instances():
                    if str(inst.why).startswith(L.YIELDED):
                        self.assertEqual(f.h.book._lots(instance=inst.id), [])

    # --------------------------------------------------------------------------- EDM1 while waiting; the fall-through
    def test_edm1_covers_a_waiting_program_and_the_seat_falls_through(self):
        """A waiting program with a real record whose realized net stands at the program loss line (a record by hand,
        as its own closes would have left it). At the day's decision EDM1 names it WHILE IT WAITS: it is marked
        sticky, never takes a seat again under this version, and the seat that frees goes to the next waiting
        program in the same sync. In the seating pass (which runs no EDM1 pass of its own) the band rule says the
        same at the seating itself, and the seat falls through to the next program there too."""
        f = self.floor()
        f.add("busy-1", "SPY", k=200, passed=1.0)
        f.add("busy-2", "QQQ", k=150, passed=2.0)
        f.add("busy-3", "IWM", k=120, passed=3.0)
        f.add("lost", "DIA", k=100, passed=4.0)
        f.add("next", "XLK", k=1, passed=9.0)
        for i, family in enumerate(("busy-1", "busy-2", "busy-3")):
            f.plan(family, {"buy": ETFS[i], "share": 0.3, "at": "open"})
        f.session(0)
        for family in ("busy-1", "busy-2", "busy-3"):
            f.plan(family)
        f.session(1)
        self.assertEqual(f.waiting(), [("lost", 1, False), ("next", 2, False)])

        def record(family: str, n: int) -> None:
            gone = L.Instance(f.key(family), family, 1, "beta", "r1", T.CODE, {}, "candidate", False, 20, created_at=1.0,
                              retired_at=2.0, why="demoted: long ago")
            lot = f.h.lot(gone, "DIA", "1", "450", opened=FRIDAY)
            f.h.venue.held["DIA"] -= D("1")
            lot.status, lot.qty, lot.cash, lot.exit_day, lot.closed_at = "closed", D(0), D("-300"), f.days[n].isoformat(), 5.0
            f.h.book._save_lot(lot)

        record("lost", 1)
        f.h.families.rows["busy-1"]["band"] = "retired"                    # a seat frees
        f.session(2, windows=False)
        self.assertTrue(f.h.state.get("eq_sticky")[f.key("lost")].startswith("EDM1: EDM1: its realized Probe net"))
        self.assertEqual(sorted(f.holders()), ["busy-2", "busy-3", "next"], "the seat went to the next waiting program")
        self.assertEqual((f.band("lost"), f.waiting(), f.seats()["sticky"]), ("candidate", [], ["lost"]))
        self.assertEqual([(e["action"], e["family"]) for e in f.events()[-2:]], [("waiting_demoted", "lost"), ("seated", "next")])
        self.assertTrue(any("waited for a seat and is demoted" in text for _, text in f.h.alerts))
        # The seating pass: `third` ranks first and its record trips EDM1 at its seating; `fourth` takes the seat.
        f.add("third", "XLF", k=50, passed=20.0)
        f.add("fourth", "DIA", k=0, passed=21.0)
        record("third", 2)
        f.h.families.rows["busy-2"]["band"] = "retired"
        f.h.tick(16, 40, day=f.days[2])
        self.assertEqual(sorted(f.holders()), ["busy-3", "fourth", "next"])
        self.assertEqual(f.seats()["sticky"], ["lost", "third"])
        self.assertEqual([(e["action"], e["family"]) for e in f.events()[-2:]],
                         [("waiting_demoted", "third"), ("seated", "fourth")],
                         "the same record as the day's own pass (league/tests/test_equity_seats_a30.py)")
        f.h.families.rows["busy-3"]["band"] = "retired"
        f.run(3, 5)
        self.assertEqual(({f.band("lost"), f.band("third")}, sorted(f.holders())), ({"candidate"}, ["fourth", "next"]),
                         "a seat is free and neither returns")

    def test_a_seating_that_does_not_take_falls_through_in_the_same_sync(self):
        f = self.floor()
        f.add("first", "SPY", k=200, passed=1.0)
        f.add("second", "QQQ", k=100, passed=2.0)
        f.add("third", "IWM", k=50, passed=3.0)
        f.add("fourth", "DIA", k=10, passed=4.0)
        real = f.h.families.confirm_band

        def confirm(expected, band, reason):
            return False if expected["family"] == "first" else real(expected, band, reason)

        with mock.patch.object(f.h.families, "confirm_band", confirm):
            out = f.session(0)
            self.assertEqual(sorted(f.holders()), ["fourth", "second", "third"], "three seats, filled past the one that failed")
            self.assertEqual(f.waiting(), [("first", 1, False)], "still first in line")
            self.assertIn("first: the row changed; no move", out.get("bands", []) + f.h.book._last.get("bands", []))
            over = [e for e in f.events() if e["action"] == "passed_over"]
            self.assertEqual([(e["family"], e["rank"]) for e in over], [("first", 1)], "said once a day, not each minute")
            self.assertIn("the seat goes to the next waiting program", over[0]["why"])
        # The band rule saying no (EDM1 at the seating itself) falls through the same way, and marks it sticky.
        g = self.floor()
        g.add("first", "SPY", k=200, passed=1.0)
        g.add("second", "QQQ", k=100, passed=2.0)

        def next_band(row, record, table, *, seat_free, sticky=None):
            if row["family"] == "first":
                return "candidate", "EDM1: EDM1: its fills ran below their replay twins"
            return REAL_NEXT_BAND(row, record, table, seat_free=seat_free, sticky=sticky)

        with mock.patch.object(B, "next_band", next_band):
            g.session(0)
        self.assertEqual((g.holders(), g.waiting(), g.seats()["sticky"]), (["second"], [], ["first"]))

    def test_an_unreadable_store_or_a_closed_roster_moves_no_seat(self):
        f = self.rare()
        f.run(1, 9)
        f.h.families.last_error = "OperationalError: database is locked"
        before = copy.deepcopy(f.seats())
        f.session(10)
        self.assertEqual({k: v for k, v in f.seats().items()}, before, "an unreadable store: the plan stands, nothing moves")
        f.h.families.last_error = ""
        f.h.families.roster = 0                                  # the swarm's roster cannot be read: no new seat
        f.session(11)
        self.assertEqual((f.band("rare"), f.band("late"), f.seats()["seats"]), ("probe", "candidate", 0),
                         "no yield into a seat nobody could take")
        f.h.families.roster = None
        f.session(12)
        self.assertEqual((f.band("rare"), f.band("late")), ("candidate", "probe"))

    def test_the_seat_rules_own_trouble_never_stops_the_days_decision(self):
        """A seat mark the book cannot read (a day that is no date): the seat rule's pass fails, is recorded, moves
        no seat, and the day's decision runs all the same: the seated programs are asked, nobody is retired and
        nothing is sold. (A decision that did not run would count as a failed decide, and two of those exit a
        program's lots: the seat rule must never be a way there.)"""
        f = self.rare()
        f.run(1, 3)
        since = f.h.state.get("eq_band_since")
        since[f.key("rare")] = {"band": "probe", "day": "not-a-day"}
        f.h.state.put("eq_band_since", since)
        events = len(f.events())
        out = f.session(4)
        self.assertTrue(any(e.startswith("seats: ") for e in f.h.book._last.get("errors", []) + out.get("errors", [])))
        self.assertEqual(len(f.events()), events, "no seat changed hands")
        day = f.days[4].isoformat()
        self.assertEqual(f.h.state.get("eq_decide")["day"], day)
        self.assertEqual(sorted(f.h.state.get("eq_decide")["instances"]), sorted(f.key(x) for x in ("busy-1", "busy-2", "rare")))
        self.assertEqual({f.inst(x).last_decided_day for x in ("busy-1", "busy-2", "rare")}, {day})
        self.assertEqual({f.inst(x).failed_decides for x in ("busy-1", "busy-2", "rare")}, {0})
        self.assert_nothing_was_ever_forced(f)

    def test_a_restart_keeps_the_plan_and_the_flags(self):
        f = self.rare()
        f.run(1, 10)
        plan = copy.deepcopy(f.seats())
        f.h.book = f.h.new_book()                                # the House starts again: the same state, a new book
        self.assertEqual(f.seats(), plan)
        f.run(11, 13)
        self.assertEqual((f.holders(), f.waiting()), (plan and sorted(["busy-1", "busy-2", "late"]), [("rare", 1, True)]))
        self.assertEqual([e["action"] for e in f.events() if e["action"] != "seated"], ["yielded"])

    # ----------------------------------------------------------------------------------------------- the report
    def test_the_report_says_who_holds_each_seat_and_which_the_seeds_hold(self):
        from league.ops import dlane_report as R

        f = self.floor()
        f.add("seed-a", "SPY", k=200, passed=1.0, seeded=True)
        f.add("bred-b", "QQQ", k=150, passed=2.0)
        f.add("seed-c", "IWM", k=100, passed=3.0, seeded=True)
        f.add("bred-d", "DIA", k=1, passed=9.0)
        f.plan("seed-a", {"buy": "SPY", "share": 0.5, "at": "open"})
        f.plan("bred-b", {"buy": "QQQ", "share": 0.5, "at": "open"})
        f.session(0)
        f.plan("seed-a")
        f.plan("bred-b")
        f.run(1, 2)
        book = R.read_book(f.h.state.path if hasattr(f.h.state, "path") else Path(f.h.state.db_path))
        seats = R.equity_seats(None, book, {"seed-a", "seed-c"})
        self.assertEqual((seats["rule"], seats["seats"], seats["as_of"]), ("activity-1-free", 3, f.days[2].isoformat()))
        self.assertEqual([(x["family"], x["seeded"]) for x in seats["holders"]],
                         [("bred-b", False), ("seed-a", True), ("seed-c", True)])
        self.assertEqual(seats["seeded_seats"], ["seed-a", "seed-c"])
        self.assertEqual(seats["seeded_statement"],
                         "3 of 3 seats are held; programs seeded by the captain's build agents hold 2 of them: seed-a, "
                         "seed-c. Seeded and bred programs follow the same seat rule.")
        self.assertEqual(seats["waiting"], [{"family": "bred-d", "rank": 1, "seeded": False, "flagged": False}])
        self.assertEqual(seats["preregistered"], R.SEAT_RULE)
        f.run(3, 10)                                             # the idle seeded program yields to the bred one
        seats = R.equity_seats(None, R.read_book(Path(f.h.state.db_path) if hasattr(f.h.state, "db_path") else f.h.state.path),
                               {"seed-a", "seed-c"})
        self.assertEqual(seats["seeded_seats"], ["seed-a"])
        self.assertEqual((seats["idle_flagged"], seats["waiting"]),
                         (["seed-c"], [{"family": "seed-c", "rank": 1, "seeded": True, "flagged": True}]))
        self.assertEqual((seats["last_change"]["action"], seats["last_change"]["family"]), ("seated", "bred-d"))
        self.assertNotIn("close_days", json.dumps(seats))
        # A book that has written no plan: its live instances, and it says so.
        bare = R.equity_seats(None, {"eq_instances": [{"family": "x", "version": 1, "band": "probe", "seeded": 1,
                                                       "retired_at": None}], "seat_plan": None}, set())
        self.assertEqual((bare["seeded_seats"], bare["rule"]), (["x"], None))
        self.assertIn("no seat plan yet", bare["why"])


# ========================================================================================================== first come
class FirstCome(SeatCase):
    def test_first_come_is_the_behaviour_before_the_rule_on_a_recorded_sequence(self):
        """THE ROLLBACK VALUE IS THE BEHAVIOUR IT REPLACED. The script of league/tests/equity_seat_sequence.py (the real
        book over the real swarm store and reader: three seats, five passers, an EDM1 demotion, a swarm retirement,
        the seating pass) was run on release E5-S (e36c7e39) and its record kept; with the rule "first-come" this
        tree gives that record, entry for entry: every minute's summary and rows, every instance, intent, order and
        lot, the families' bands, the book's memory, every ledger record, every alert, every order sent."""
        want = json.loads((FIXTURES / "equity_seat_first_come.json").read_text(encoding="utf-8"))
        with X.seat_rule("first-come"):
            got = json.loads(json.dumps(Q.run(self.fresh()), sort_keys=True))
        self.assertEqual(sorted(got), sorted(want))
        # RELEASE E4's ONE COLUMN ON THESE ROWS (`eq_instances.kind`, league/equity/live.py `INSTANCE_KIND_DDL`): the
        # record was written before it. It is held to what it must be for a share program, "equity" on every row,
        # and left out of the comparison (as league/tests/equity_week.py `main_shape` does for the recorded weeks).
        for row in got["tables"]["eq_instances"]:
            self.assertEqual(row.pop("kind"), "equity", row["id"])
        # RELEASE R2's TWO COLUMNS ON THE ORDERS (`eq_orders.tif` and `.otype`, league/equity/live.py
        # `ORDER_COLUMNS_DDL`): "day" and "limit" on every share program's order, left out the same way.
        for row in got["tables"]["eq_orders"]:
            self.assertEqual((row.pop("tif"), row.pop("otype")), ("day", "limit"), row.get("eid"))
        for part in want:
            self.assertEqual(got[part], want[part], part)
        self.assertEqual(got["errors"], [])
        self.assertFalse([kind for kind, _ in got["events"] if kind == "equity.seat"], "first come writes no seat record")

    def test_the_same_script_under_the_rule_in_force(self):
        """The same week under "activity-1-free": none of the five has the rule's counts, so they rank by pass time and
        the same programs hold the same seats at the end; what differs is the rule's own doing: the waiting programs
        are read (they have rows), and a freed seat is refilled in the SAME sync (the fall-through), not a minute on."""
        want = json.loads((FIXTURES / "equity_seat_first_come.json").read_text(encoding="utf-8"))
        got = json.loads(json.dumps(Q.run(self.fresh()), sort_keys=True))
        self.assertEqual(got["families"], want["families"])
        self.assertEqual(got["sent"], want["sent"], "the same orders")
        self.assertEqual(got["alerts"], want["alerts"])
        self.assertEqual(got["errors"], [])
        self.assertEqual([(p["action"], p["family"]) for kind, p in got["events"] if kind == "equity.seat"],
                         [("seated", "m-first"), ("seated", "z-second"), ("seated", "a-third"), ("seated", "k-fourth"),
                          ("seated", "b-fifth")])
        monday = next(t for t in got["ticks"] if t["day"] == "2026-10-12" and t["at"] == "16:21")
        self.assertIn("k-fourth:probe", monday["rows"], "seated in the sync that demoted a-third")

    def test_first_come_never_yields_and_ranks_nobody(self):
        """On the book alone: under "first-come" an idle seat never yields, the waiting are not ranked by the book
        (its plan says the swarm's roster orders them), and a higher K buys nothing."""
        with X.seat_rule("first-come"):
            f = self.floor()
            f.add("a-first", "SPY", k=1, passed=1.0)
            f.add("b-second", "QQQ", k=2, passed=2.0)
            f.add("c-third", "IWM", k=3, passed=3.0)
            f.add("d-fast", "DIA", k=250, passed=4.0)
            f.run(0, 14)
            self.assertEqual(f.holders(), ["a-first", "b-second", "c-third"], "the rows' own order: first come")
            plan = f.seats()
            self.assertEqual((plan["rule"], plan["waiting"], plan["order"]),
                             ("first-come", None, "by pass time: the swarm's roster (first come)"))
            self.assertEqual(f.events(), [])
            self.assertEqual(f.band("d-fast"), "candidate")
            self.assertFalse([text for _, text in f.h.alerts if "yield" in text])

    def test_the_rollback_with_a_yielded_program_waiting_unseats_nobody(self):
        """The rule in force, a yield, then the release whose rule is "first-come": nobody is unseated, nothing is
        sold, the program that yielded stays a waiting Candidate (its flag is simply not read), and when a seat is
        free it runs again under its own instance key."""
        f = self.floor()
        f.add("busy-1", "SPY", k=200, passed=1.0)
        f.add("busy-2", "QQQ", k=150, passed=2.0)
        f.add("rare", "IWM", k=100, passed=3.0)
        f.add("late", "DIA", k=1, passed=9.0)
        f.plan("busy-1", {"buy": "SPY", "share": 0.5, "at": "open"})
        f.plan("busy-2", {"buy": "QQQ", "share": 0.5, "at": "open"})
        f.session(0)
        f.plan("busy-1")
        f.plan("busy-2")
        f.run(1, 10)
        self.assertEqual(f.waiting(), [("rare", 1, True)])
        with X.seat_rule("first-come"):
            f.h.book = f.h.new_book()
            moves = len(f.h.families.moves)
            f.run(11, 13)
            self.assertEqual(len(f.h.families.moves), moves, "no band moved at the rollback")
            self.assertEqual(sorted(f.holders()), ["busy-1", "busy-2", "late"])
            self.assertEqual((f.band("rare"), f.seats()["rule"], f.seats()["waiting"]), ("candidate", "first-come", None))
            f.h.families.rows["late"]["band"] = "retired"
            f.run(14, 15)
            self.assertEqual(sorted(f.holders()), ["busy-1", "busy-2", "rare"])
            inst = f.inst("rare")
            self.assertEqual((inst.retired_at, inst.band), (None, "probe"))
        self.assertEqual(f.h.intents(kind="house_exit"), [])
        self.assertEqual([b for b in f.h.venue.sent if b["side"] == "sell"], [])


# ==================================================================================================== the deploy night
#: Invented programs for the deploy night, as the House's engine reads them. A program's NEEDS name one ETF.
OVERNIGHT = ("NEEDS = {{'symbols': ['{symbol}'], 'history': 2, 'max_hold_sessions': 60}}\nPARAMS = {{}}\n\n\n"
             "def decide(ctx):\n"
             "    out = [{{'sell': lot['id'], 'at': 'open'}} for lot in ctx.positions]\n"
             "    out.append({{'buy': '{symbol}', 'share': 0.5, 'at': 'close'}})\n"
             "    return out\n# {fid}\n")
SWING = ("NEEDS = {{'symbols': ['{symbol}'], 'history': 2, 'max_hold_sessions': 60}}\nPARAMS = {{}}\n\n\n"
         "def decide(ctx):\n"
         "    if ctx.positions:\n"
         "        return [{{'sell': lot['id'], 'at': 'open'}} for lot in ctx.positions if int(lot['held_sessions']) >= {hold}]\n"
         "    return [{{'buy': '{symbol}', 'share': {share}, 'at': 'open'}}]\n# {fid}\n")
REVERSAL = ("NEEDS = {{'symbols': ['{symbol}'], 'history': 3, 'max_hold_sessions': 60}}\nPARAMS = {{}}\n\n\n"
            "def decide(ctx):\n"
            "    if ctx.positions:\n"
            "        return [{{'sell': lot['id'], 'at': 'open'}} for lot in ctx.positions if int(lot['held_sessions']) >= 2]\n"
            "    close = ctx.bars['{symbol}'].close\n"
            "    if len(close) >= 2 and float(close[-2]) > 0 and float(close[-1]) / float(close[-2]) - 1.0 <= -0.03:\n"
            "        return [{{'buy': '{symbol}', 'share': 0.5, 'at': 'open'}}]\n"
            "    return []\n# {fid}\n")
#: THE BOOK THE BASE LEAVES: (family, its ETF, its program, seeded), in the order their looks passed. Six seats, first
#: come: these five are seated; one is a rare reversal trader.
SEATED = (("seed-overnight", "SPY", OVERNIGHT, {}, True), ("bred-swing", "QQQ", SWING, {"hold": 2, "share": 0.5}, False),
          ("seed-reversal", "IWM", REVERSAL, {}, True), ("bred-slice", "DIA", SWING, {"hold": 0, "share": 0.25}, False),
          ("bred-overnight", "QQQ", OVERNIGHT, {}, False))
#: The programs that pass their looks after the release, in the order they pass.
LATER = (("late-sixth", "IWM", SWING, {"hold": 4, "share": 0.5}), ("late-slow", "DIA", SWING, {"hold": 20, "share": 0.5}),
         ("late-fast", "SPY", SWING, {"hold": 0, "share": 0.5}))


@unittest.skipUnless(HAVE, "numpy not installed")
class TheDeployNight(SeatCase):
    """THE STATE THAT WILL EXIST, AND THIS RELEASE APPLIED TO IT. Release E5-S runs six seats first come: five programs
    passed their looks and are seated (two of them seeded, one a rare reversal trader), four hold a lot. The real
    swarm store and its real reader, the real book and a fake venue, the real runner on an invented market for the
    backfill; the programs' live decisions are played by the fake decider."""

    def setUp(self):
        super().setUp()
        from league.equity import synth
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock as SwarmClock

        self.state_root = self.fresh()
        self.store = SwarmStore(self.state_root, clock=SwarmClock())
        self.addCleanup(self.store.close)
        # An invented market of ordinary prices (a share stays in the hundreds of dollars over the decade).
        self.store_root = synth.synthetic_store(self.state_root / elane.STORE_DIR, gate=True, seed=11, drift=0.06, vol=0.15)
        self.runner = Isolated(InlineDecider(), self.store_root)
        elane._seat_failed.clear()
        self.addCleanup(elane._seat_failed.clear)
        self.codes: dict[str, str] = {}

    # ------------------------------------------------------------------------------------------------ the swarm
    def passes(self, fid: str, symbol: str, template: str, params: dict, *, at: float, seeded: bool = False,
               stored: bool = True, counted: bool = False) -> None:
        """A family whose look passed, as release E5-S's own `elane.look` left it: banded on its version 1 under the
        equity identity in force, its Validation recorded (and its run kept in full, unless `stored` is False: a
        file that is gone), a look record with no seat counts. `counted`: a look taken AFTER this release, which
        writes the counts itself."""
        from league.swarm import evaluator
        from league.swarm.gate import run_sha

        code = template.format(symbol=symbol, fid=fid, **params)
        self.codes[fid] = code
        spec = {"id": fid, "mechanism": f"An invented program on {symbol}, long only (MARKET BETA).", "structure": "etf",
                "roots": [symbol], "symbols": [symbol], "lane": "beta", **({"seeded": True} if seeded else {})}
        self.store.add_family(spec, origin="seed")
        version = self.store.add_version(fid, code, {}, author="test")
        sha = run_sha(version)
        with real_engine():
            validation = self.runner.validation(code, {}, name=fid, k=config.K_BASE)
            segments = self.runner.segments(code, {}, name=fid) if counted else []
        self.assertEqual(validation.result["status"], "ok", fid)
        if stored:
            self.store.add_run(fid, 1, dict(validation.result), window="validation", stress=config.K_BASE,
                               purpose="validation")
        identity = evaluator.equity_identity()
        seat = {}
        if counted:
            seat = {elane.SEAT_KEY: elane._seat_record(self.store, 1, sha, validation.result, segments, source="look",
                                                       validation_run="look")}
        self.store.set_state(fid, banded_version=1, banded_at=float(self.store.clock()) + at, validation_version=1,
                             banded_evaluator={"engine": identity["engine"], "equity_sha256": identity["equity"],
                                               "run_sha": sha},
                             **{elane.VALIDATION_KEY: {"version": 1, "passed": True, "status": "ok", "stale": False,
                                                       "result_sha": validation.result["result_sha"]},
                                elane.LOOK_KEY: {"version": 1, "at": self.store.now(), "beside": "S2 (an invented look)",
                                                 "verdict": {"passed": True, "screen": "S2"}, "activity": None}, **seat})
        self.store.set_band(fid, "candidate", reason="passed its sealed look")

    def k_by_hand(self, fid: str) -> Fraction:
        code = self.codes[fid]
        with real_engine():
            return B.seat_k(B.seat_counts(self.runner.validation(code, {}, name=fid).result,
                                          [r.result for r in self.runner.segments(code, {}, name=fid)], floor=D("0.25")))

    # ------------------------------------------------------------------------------------------------ the House
    def house(self) -> T.Harness:
        # THE DESIGN TONIGHT'S RELEASE SETS, stated (no test assumes the pair in force): six seats at a quarter of E,
        # on the table's side and on the swarm's roster.
        patcher = mock.patch.dict(elane.DEFAULTS, {"roster": 6})
        patcher.start()
        self.addCleanup(patcher.stop)
        h = T.Harness(self.state_root, cash=str(E), E=str(E), table=X.table_at(6, "0.25").equity)
        self.addCleanup(h.state.close)
        h.families = EquityFamilies(self.state_root)
        self.addCleanup(lambda: h.families._store is not None and h.families._store.close())
        h.book = h.new_book()
        self.days = sessions(MONDAY, 14)
        fake = Floor.__new__(Floor)
        fake.h, fake.days = h, self.days
        for symbol in ETFS[:4]:
            Floor.bars(fake, symbol, n=60)
        for fid, symbol, *_ in (*SEATED, *LATER):
            h.decider.needs[L.instance_key(fid, 1)] = {"symbols": [symbol], "history": 5, "max_hold_sessions": 60}
        h.state.execute("DELETE FROM kv WHERE key='eq_decide'")
        return h

    def snapshot(self, h: T.Harness) -> dict:
        return {"instances": [dict(r) for r in h.state.rows("SELECT * FROM eq_instances ORDER BY id")],
                "intents": [dict(r) for r in h.state.rows("SELECT * FROM eq_intents ORDER BY iid")],
                "lots": [{k: v for k, v in dict(r).items() if k not in ("mark", "marked_at")}
                         for r in h.state.rows("SELECT * FROM eq_lots ORDER BY lid")],
                "orders": len(h.state.rows("SELECT eid FROM eq_orders")),
                "bands": {fid: self.store.family(fid)["band"] for fid, *_ in SEATED},
                "since": h.state.get("eq_band_since"), "sticky": h.state.get("eq_sticky"), "sent": len(h.venue.sent)}

    def the_base(self) -> T.Harness:
        """Release E5-S on Sunday and Monday morning: six seats, first come. The five are seated in the order they
        passed and asked for Friday's close; four buy a lot at Monday's open; the reversal trader plans nothing."""
        for i, (fid, symbol, template, params, seeded) in enumerate(SEATED):
            self.passes(fid, symbol, template, params, at=float(i), seeded=seeded, stored=fid != "bred-slice")
        with X.seat_rule("first-come"):
            h = self.house()
            self.key = {fid: L.instance_key(fid, 1) for fid, *_ in (*SEATED, *LATER)}
            for fid, symbol, *_ in SEATED:
                if fid != "seed-reversal":
                    h.decider.plans[self.key[fid]] = [{"buy": symbol, "share": 0.5, "at": "open"}]
            for hh, mm in ((14, 0), (14, 1), (14, 2)):
                h.tick(hh, mm, day=SUNDAY)
            h.decider.plans.clear()
            for hh, mm in ((9, 31), (9, 33)):
                h.tick(hh, mm, day=MONDAY)
            self.assertEqual(h.book.seats()["rule"], "first-come")
        self.assertEqual({fid: self.store.family(fid)["band"] for fid, *_ in SEATED}, {fid: "probe" for fid, *_ in SEATED})
        self.assertEqual(sorted(lot.family for lot in h.lots(open_only=True)),
                         ["bred-overnight", "bred-slice", "bred-swing", "seed-overnight"])
        self.assertEqual({v["day"] for v in h.state.get("eq_band_since").values()}, {FRIDAY.isoformat()},
                         "seated for Friday's close: the seat's own day")
        self.assertFalse(any(elane.SEAT_KEY in (self.store.family(fid)["state"] or {}) for fid, *_ in SEATED),
                         "the base's looks kept no seat counts")
        return h

    def decision(self, h: T.Harness, n: int, *, windows: bool = True) -> dict:
        day = self.days[n]
        if windows:
            for hh, mm in ((9, 31), (9, 33)):
                h.tick(hh, mm, day=day)
        out = {}
        for hh, mm in ((16, 21), (16, 31), (16, 32)):
            out.update(h.tick(hh, mm, day=day))
        return out

    def test_the_release_on_the_state_the_base_leaves(self):
        from league.swarm.gate import Gate

        h = self.the_base()
        before = self.snapshot(h)
        # ---- THE DEPLOY (Monday, midday): the same state, this release's book, the rule in force.
        self.assertEqual(B.seat_settings().rule, "activity-1-free")
        h.book = h.new_book()
        out = h.tick(12, 0, day=MONDAY)                      # the first band sync on the release (the seating pass)
        self.assertEqual(self.snapshot(h), before, "NOBODY IS UNSEATED AT THE DEPLOY: no band, instance, intent, lot or "
                                                   "order moved")
        self.assertNotIn("errors", out)
        self.assertEqual([e for kind, e in h.events if kind == "equity.seat"], [], "no seat changed hands")
        self.assertFalse([e for kind, e in h.events if kind == "equity.instance" and e.get("retired")])
        plan = h.book.seats()
        self.assertEqual((plan["rule"], plan["seats"], len(plan["holders"]), plan["waiting"]), ("activity-1-free", 6, 5, []))
        self.assertEqual({x["since"] for x in plan["holders"]}, {FRIDAY.isoformat()}, "each seat keeps its own day")
        self.assertEqual(sorted(x["family"] for x in plan["holders"] if x["seeded"]), ["seed-overnight", "seed-reversal"])
        # Before the swarm's round has run, no program has its counts: every one of them ranks as unreadable, and
        # nothing depends on it (nobody waits; nobody is unseated by a rank).
        self.assertTrue(all(r["seat_activity"] is None for r in h.families.read()))

        # ---- THE BACKFILL (the swarm's next equity round): K's two counts for every passed program, seated or not.
        gate = Gate(self.store, None, None, ON, clock=self.store.clock)
        gate.equity_runner = self.runner
        from league.equity import runner as runner_mod
        from league.equity import store as store_mod

        sealed = mock.Mock(side_effect=AssertionError("the backfill never takes a look"))
        with real_engine(), mock.patch.object(store_mod, "mint_equity_gate_capability", sealed), \
                mock.patch.object(runner_mod.Isolated, "look", sealed):
            round_out: dict = {"looked": [], "held": []}
            gate.equity_round(round_out)
        sealed.assert_not_called()
        self.assertEqual(sorted(round_out["seat_counts"]), sorted(fid for fid, *_ in SEATED))
        k = {}
        for fid, *_ in SEATED:
            held = self.store.family(fid)["state"][elane.SEAT_KEY]
            self.assertEqual((held["source"], held["validation_run"]),
                             ("backfill", "rerun" if fid == "bred-slice" else "stored"), fid)
            k[fid] = B.seat_k(held)
            self.assertEqual(k[fid], self.k_by_hand(fid), fid)
        self.assertEqual(self.snapshot(h)["bands"], before["bands"], "a count is no band move")
        self.assertEqual(len(self.store.looks()), 0, "and no look")
        rows = {r["family"]: r for r in h.families.read()}
        self.assertEqual({fid: B.seat_k(rows[fid]["seat_activity"]) for fid in k}, k, "the book's rows carry them")
        # THE RANKS ARE AS THE RULE SAYS: the two overnight programs close a half-sleeve lot nearly every session;
        # the slice of exactly a quarter sleeve counts (every other session); the reversal trader is the rarest.
        self.assertGreater(k["seed-overnight"], 200)
        self.assertGreater(k["bred-overnight"], 200)
        self.assertGreater(k["bred-slice"], 100, "a lot of exactly the floor counts")
        self.assertLess(k["bred-slice"], k["seed-overnight"])
        self.assertEqual(min(k, key=k.get), "seed-reversal")
        self.assertLess(k["seed-reversal"], 25)

        # ---- Monday's decision on the release, then the week: nobody is unseated; the later passers arrive.
        self.decision(h, 0, windows=False)
        self.assertEqual(sorted(x["family"] for x in h.book.seats()["holders"]), sorted(fid for fid, *_ in SEATED))
        for i, (fid, symbol, template, params) in enumerate(LATER):
            self.passes(fid, symbol, template, params, at=100.0 + i, counted=True)      # their looks write their counts
            k[fid] = self.k_by_hand(fid)
            self.assertEqual(B.seat_k(self.store.family(fid)["state"][elane.SEAT_KEY]), k[fid])
        self.assertGreater(k["late-fast"], k["late-slow"], "the one that passed LAST trades far more often")
        h.decider.plans[self.key["late-sixth"]] = [{"buy": "IWM", "share": 0.5, "at": "open"}]
        self.decision(h, 1)
        h.decider.plans.clear()
        plan = h.book.seats()
        # The sixth seat was FREE: it went to the best-ranked of the three that waited, not to the first that passed.
        best = max(("late-sixth", "late-slow", "late-fast"), key=lambda fid: k[fid])
        self.assertEqual(best, "late-fast")
        self.assertEqual(sorted(x["family"] for x in plan["holders"]), sorted([*(fid for fid, *_ in SEATED), "late-fast"]))
        rest = sorted(("late-sixth", "late-slow"), key=lambda fid: (-k[fid], fid))
        self.assertEqual([(w["family"], w["rank"], w["flagged"]) for w in plan["waiting"]],
                         [(rest[0], 1, False), (rest[1], 2, False)])
        self.assertIsNone(h.book._instance(self.key[rest[0]]), "a waiting program has no instance")
        # A seated program trades on as before: bred-swing sells its lot itself on Wednesday and buys again on Thursday.
        [lot] = h.book._lots(instance=self.key["bred-swing"])
        h.decider.plans[self.key["bred-swing"]] = [{"sell": lot.lid, "at": "open"}]
        self.decision(h, 2)
        h.decider.plans[self.key["bred-swing"]] = [{"buy": "QQQ", "share": 0.5, "at": "open"}]
        self.decision(h, 3)
        h.decider.plans.clear()
        for n in range(4, 9):
            self.decision(h, n)
        self.assertEqual(self.days[8], dt.date(2026, 10, 22))
        rare = {x["family"]: x for x in h.book.seats()["holders"]}["seed-reversal"]
        self.assertEqual((rare["seated_sessions"], rare["flat"], rare["idle"], rare["quiet_sessions"]), (9, True, False, None),
                         "nine sessions of its seat: it keeps it, though two programs wait")
        self.assertEqual([e["action"] for kind, e in h.events if kind == "equity.seat"], ["seated"])

        # ---- TEN SESSIONS OF ITS SEAT (Friday Oct 23): the idle reversal trader yields to the best-ranked waiting one.
        out = self.decision(h, 9)
        plan = h.book.seats()
        self.assertEqual(sorted(x["family"] for x in plan["holders"]),
                         sorted([fid for fid, *_ in SEATED if fid != "seed-reversal"] + ["late-fast", rest[0]]))
        self.assertEqual([(w["family"], w["rank"], w["flagged"]) for w in plan["waiting"]],
                         [(rest[1], 1, False), ("seed-reversal", 2, True)])
        self.assertEqual((self.store.family("seed-reversal")["band"], self.store.family(rest[0])["band"]), ("candidate", "probe"))
        inst = h.book._instance(self.key["seed-reversal"])
        self.assertTrue(inst.retired_at is not None and inst.why.startswith("yielded:"), inst.why)
        self.assertNotIn(self.key["seed-reversal"], h.state.get("eq_sticky") or {})
        self.assertEqual([(e["action"], e["family"], e.get("for")) for kind, e in h.events if kind == "equity.seat"][-2:],
                         [("yielded", "seed-reversal", rest[0]), ("seated", rest[0], None)])
        self.assertEqual(sorted(x["family"] for x in plan["holders"] if x["seeded"]), ["seed-overnight"],
                         "the report's line: the seeds now hold one seat")
        self.assertIn("seed-overnight (seeded) seated 10 sessions", out["seats"])
        # The swarm's roster reports the book's own plan (one source), and says its own lists are by pass time.
        roster = swarm_bands.roster(self.state_root, lanes=elane.LANES)
        self.assertEqual((roster["rule"], roster["plan"]["waiting"], roster["waiting"]),
                         ("activity-1-free", plan["waiting"], sorted([rest[1], "seed-reversal"])))
        self.assertIn("NOT who is next", roster["order"])
        # ---- NOTHING WAS EVER FORCED: the only sale of the fortnight is bred-swing's own.
        self.assertEqual(h.intents(kind="house_exit"), [])
        self.assertEqual([(i.instance, i.status) for i in h.intents(kind="sell")], [(self.key["bred-swing"], "done")])
        self.assertEqual(len([b for b in h.venue.sent if b["side"] == "sell"]), 1)
        self.assertEqual(sorted(lot.family for lot in h.lots(open_only=True)),
                         ["bred-overnight", "bred-slice", "bred-swing", "seed-overnight"])
        self.assertEqual(h.book._lots(instance=self.key["seed-reversal"], open_only=False), [], "it never held a lot")
        text = json.dumps([h.book.health(), [e for _, e in h.events], h.alerts], default=str)
        self.assertNotIn("close_days", text)
        self.assertNotIn("seat_activity", text)

    def test_ten_sessions_on_the_idle_trader_keeps_its_seat_when_nobody_unflagged_waits(self):
        """The same deploy with no later passer: six seats, five held. The reversal trader is idle from Friday Oct 23
        and KEEPS its seat (the plan says idle); nothing moves for three more sessions. A program then passes: there
        is a free seat, so it takes that one, and the idle trader still keeps its own. Only when all six are held and
        one more waits does it yield."""
        from league.swarm.gate import Gate

        h = self.the_base()
        h.book = h.new_book()
        gate = Gate(self.store, None, None, ON, clock=self.store.clock)
        gate.equity_runner = self.runner
        with real_engine():
            gate.equity_round({"looked": [], "held": []})
        for n in range(0, 12):
            self.decision(h, n, windows=False)
        self.assertEqual(self.days[11], dt.date(2026, 10, 27))
        plan = h.book.seats()
        rare = {x["family"]: x for x in plan["holders"]}["seed-reversal"]
        self.assertEqual((rare["idle"], rare["seated_sessions"], len(plan["holders"]), plan["waiting"]), (True, 12, 5, []))
        self.assertEqual([e for kind, e in h.events if kind == "equity.seat"], [], "nobody waits: no seat changed hands")
        self.passes("late-sixth", "IWM", SWING, {"hold": 4, "share": 0.5}, at=100.0, counted=True)
        self.decision(h, 12, windows=False)
        plan = h.book.seats()
        self.assertEqual(len(plan["holders"]), 6)
        self.assertEqual(self.store.family("seed-reversal")["band"], "probe", "a seat was free: nobody had to yield")
        self.passes("late-slow", "DIA", SWING, {"hold": 20, "share": 0.5}, at=101.0, counted=True)
        self.decision(h, 13, windows=False)
        self.assertEqual((self.store.family("seed-reversal")["band"], self.store.family("late-slow")["band"]),
                         ("candidate", "probe"), "six held and one unflagged program waiting: the idle seat yields at once")
        self.assertEqual(h.intents(kind="house_exit"), [])
        self.assertEqual([b for b in h.venue.sent if b["side"] == "sell"], [])


# (release 1019l, the owner's goal V3: these mechanisms on release 1019i's money table, league/tests/v2_walls.py;
# the V3 rows' own effects are league/tests/test_v3_walls.py's)
from league.tests.v2_walls import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
