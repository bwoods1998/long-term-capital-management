"""Adversarial tests of the ladder's evaluator: the code that decides promotion and death.

Every test builds a real `Ledger` in a temp dir and appends the rows a `Book` would write
(`book.stake`, `book.mark`, `book.fill`, `book.settle`), or `eval.block` rows directly when a
statistic has to be exact. A test that begins with a `# Regression:` note pins a bug this file
found: the note says what was wrong once and what the code does now.
"""

from __future__ import annotations

import copy
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from league import stats
from league.constitution import CONSTITUTION
from league.evaluator import Evaluator, block_key
from league.ledger import Ledger

BASE = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
ALPHA = float(CONSTITUTION["ladder"]["alpha"])


def before_swing(constitution):
    """The constitution as it stood before the owner's swing-and-bunt revision (Sept 23, 2026 ~03:10
    UTC). The mechanics tests below were written against these numbers; the mechanics did not
    change with them, and `SwingAndBunt` tests the new values against the real constitution."""
    c = copy.deepcopy(constitution)
    ladder = c["ladder"]
    ladder["promotion_alpha"] = ladder["alpha"]
    ladder["look_every_active_blocks"] = 5
    ladder["micro"]["min_active_blocks"] = 5
    ladder["family"].update(alpha=0.05, min_member_active_blocks=10)
    ladder["death"]["max_drawdown"] = 0.30
    ladder["paper"].update(min_active_blocks=4, min_active_blocks_day=2, max_drawdown=0.15)
    ladder["replay"].pop("min_oos_growth", None)
    c["rungs"]["3"].update(kelly_fraction=0.5, max_share_of_venue=0.4)
    return c


#: The real constitution of Sept 23, 2026 before the swing-and-bunt revision.
PRE_SWING = before_swing(CONSTITUTION)

#: The confidence bound is the gate out of the micro rung. These tests of the bound seat their
#: agents on paper (as they did when paper used it too), under a constitution whose paper gate is
#: the bound as well: the rule under test is the same code at either rung.
BOUND = copy.deepcopy(PRE_SWING)
BOUND["ladder"].pop("completed_exposures")  # isolate the original single-route statistical tests
BOUND["ladder"]["micro"]["min_active_blocks"] = 30
BOUND["ladder"]["paper"] = {"gate": "bound", "min_active_blocks": 30}
BOUND["ladder"]["min_closed_trades"] = 5
BOUND["ladder"]["paper_death"] = {"min_active_blocks": 10, "max_loss": 0.10, "unprofitable_blocks": 30}
#: The Sept 21, 2026 replay gate the rung-0 mechanics tests were written against. The owner took the
#: deflated Sharpe off the paper gate on Sept 22 (see `ReplaySept22`); the deflation machinery stays.
BOUND["ladder"]["replay"] = {"min_trades": 20, "min_blocks": 20, "min_deflated_sharpe": 0.5, "min_oos_blocks": 8}

#: The Sept 21, 2026 fast-lane values these mechanics tests were written against. The owner moved
#: the numbers on Sept 22 (see `Sept22Values`); the mechanics under test did not change.
FAST_LANE = copy.deepcopy(PRE_SWING)
FAST_LANE["ladder"]["paper"] = {"gate": "screen", "min_active_blocks": 6, "min_active_blocks_day": 2, "max_drawdown": 0.15}
FAST_LANE["ladder"]["min_closed_trades"] = 5
FAST_LANE["ladder"]["paper_death"] = {"min_active_blocks": 10, "max_loss": 0.10, "unprofitable_blocks": 30}

WINNER = [1.2, 1.0, -0.4]  # dollars a block on a $200 stake: mean +0.3%, two wins in three
LOSER = [-1.2, -1.0, 0.4]


def at(hours: float = 0, minutes: float = 0, days: float = 0) -> str:
    t = BASE + timedelta(days=days, hours=hours, minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


class EvalCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.db")
        self.ev = Evaluator(self.ledger, constitution=BOUND)
        self._keys = 0
        self._equity: dict[tuple[str, str], float] = {}

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    # ---------------------------------------------------------------- the rows a Book writes
    def stake(self, agent, usd, when, book="paper"):
        return self.ledger.append("book.stake", {"book": book, "usd": str(usd), "note": "", "real_money": False}, agent=agent, at=when)

    def mark(self, agent, equity, when, holdings=0, book="paper"):
        return self.ledger.append(
            "book.mark",
            {"book": book, "equity": f"{equity:.2f}", "cash": f"{equity:.2f}", "staked": "200", "realized": "0.00",
             "fees": "0.00", "holdings": holdings, "real_money": False},
            agent=agent, at=when,
        )

    def buy(self, agent, cost, when, book="paper", source="venue"):
        return self.ledger.append(
            "book.fill",
            {"book": book, "source": source, "side": "buy", "realized": None, "quantity": "1", "price": str(cost),
             "cash_delta": f"{-cost:.2f}", "position_delta": "1", "real_money": False},
            agent=agent, at=when,
        )

    def sell(self, agent, realized, when, book="paper", source="venue"):
        return self.ledger.append(
            "book.fill",
            {"book": book, "source": source, "side": "sell", "realized": f"{realized:.2f}", "quantity": "1", "price": "1",
             "cash_delta": "1.00", "position_delta": "-1", "real_money": False},
            agent=agent, at=when,
        )

    def settle(self, agent, pnl, when, book="paper"):
        return self.ledger.append(
            "book.settle",
            {"book": book, "result": "yes", "quantity": "1", "cost": "0.95", "payout": "1.00", "pnl": f"{pnl:.2f}", "real_money": False},
            agent=agent, at=when,
        )

    # ------------------------------------------------------------- shortcuts for judge tests
    def block(self, agent, growth, *, active=True, book="paper", start=200.0):
        """One finished `eval.block` row, written directly so the growth is exact."""
        self._keys += 1
        begin = self._equity.get((agent, book), start)
        end = begin * math.exp(growth)
        self._equity[(agent, book)] = end
        return self.ledger.append(
            "eval.block",
            {"book": book, "key": f"k{self._keys:05d}", "horizon": "hour", "start_equity": begin, "end_equity": end,
             "flow": 0.0, "log_growth": growth, "active": active},
            agent=agent,
        )

    def trades(self, agent, pnls, *, book="paper", cost=50.0):
        for pnl in pnls:
            self.buy(agent, cost, at(), book)
            self.sell(agent, pnl, at(), book)

    def mixed_trades(self, agent, n=12, book="paper"):
        """`n` closed trades, half of them losers: not a lopsided record."""
        self.trades(agent, [2.0 if i % 2 == 0 else -1.0 for i in range(n)], book=book)

    def live(self, agent, pnls, *, book="paper", stake=200.0, start_hour=0, stop_on=("die", "eligible"), ev=None):
        """What the House does each wake: trade, mark, observe, judge. One hour block per pnl."""
        ev = ev or self.ev
        equity = self._equity.get((agent, book), stake)
        verdicts = []
        for i, pnl in enumerate(pnls):
            hour = start_hour + i
            ledger = ev.ledger
            ledger.append("book.fill", {"book": book, "source": "venue", "side": "buy", "realized": None, "cash_delta": "-50.00"}, agent=agent, at=at(hour, 5))
            ledger.append("book.fill", {"book": book, "source": "venue", "side": "sell", "realized": f"{pnl:.2f}", "cash_delta": f"{50 + pnl:.2f}"}, agent=agent, at=at(hour, 40))
            equity += pnl
            ledger.append("book.mark", {"book": book, "equity": f"{equity:.2f}", "holdings": 0}, agent=agent, at=at(hour, 50))
            ev.observe(agent, book, "hour")
            verdicts.append(ev.judge(agent, book))
            if verdicts[-1].decision in stop_on:
                break
        self._equity[(agent, book)] = equity
        return verdicts

    def rows(self, kind, agent=None):
        return list(self.ledger.iter(kinds=kind, agent=agent))

    def looks(self, agent):
        return [e.payload for e in self.rows("eval.verdict", agent) if e.payload.get("decision") == "look"]


# =================================================================================================
# observe: marks and stakes -> eval.block rows
# =================================================================================================
class ObserveBlocks(EvalCase):
    def test_block_key(self):
        self.assertEqual(block_key("2026-09-20T13:05:00.000Z", "hour"), "2026-09-20T13")
        self.assertEqual(block_key("2026-09-20T13:05:00.000Z", "day"), "2026-09-20")

    def test_hour_blocks_start_from_the_stake_and_end_on_the_last_mark_of_the_block(self):
        self.stake("a", 200, at(0, 0))
        self.mark("a", 201, at(0, 10))
        self.mark("a", 202, at(0, 50))
        self.mark("a", 204, at(1, 10))
        self.mark("a", 203, at(2, 10))
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 2)
        blocks = self.ev.blocks("a")
        self.assertEqual([b["key"] for b in blocks], ["2026-09-20T00", "2026-09-20T01"])
        self.assertEqual((blocks[0]["start_equity"], blocks[0]["end_equity"], blocks[0]["flow"]), (200.0, 202.0, 0.0))
        self.assertAlmostEqual(blocks[0]["log_growth"], math.log(202 / 200), places=12)
        self.assertEqual((blocks[1]["start_equity"], blocks[1]["end_equity"]), (202.0, 204.0))
        self.assertAlmostEqual(blocks[1]["log_growth"], math.log(204 / 202), places=12)
        self.assertEqual(blocks[0]["horizon"], "hour")
        self.assertEqual(blocks[0]["book"], "paper")

    def test_the_last_block_is_unfinished_until_a_mark_exists_in_a_later_block(self):
        self.stake("a", 200, at(0, 0))
        self.mark("a", 201, at(0, 10))
        self.mark("a", 202, at(0, 50))
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 0)
        self.assertEqual(self.ev.blocks("a"), [])
        self.mark("a", 203, at(1, 1))
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 1)
        self.assertEqual(len(self.ev.blocks("a")), 1)

    def test_a_gap_of_empty_hours_makes_no_blocks_and_growth_spans_the_gap(self):
        self.stake("a", 200, at(0, 0))
        self.mark("a", 200, at(0, 30))
        self.mark("a", 210, at(5, 30))  # nothing marked from 01:00 to 04:59
        self.mark("a", 210, at(6, 30))
        self.ev.observe("a", "paper", "hour")
        blocks = self.ev.blocks("a")
        self.assertEqual([b["key"][-2:] for b in blocks], ["00", "05"])
        self.assertAlmostEqual(blocks[1]["log_growth"], math.log(210 / 200), places=12)

    def test_day_blocks(self):
        self.stake("a", 200, at(0, 0))
        for day, equities in enumerate(([201, 203], [202, 206], [207])):
            for i, equity in enumerate(equities):
                self.mark("a", equity, at(9 + 5 * i, 0, days=day))
        self.assertEqual(self.ev.observe("a", "paper", "day"), 2)
        blocks = self.ev.blocks("a")
        self.assertEqual([b["key"] for b in blocks], ["2026-09-20", "2026-09-21"])
        self.assertAlmostEqual(blocks[0]["log_growth"], math.log(203 / 200), places=12)
        self.assertAlmostEqual(blocks[1]["log_growth"], math.log(206 / 203), places=12)
        self.assertEqual(blocks[1]["horizon"], "day")

    def test_the_same_marks_make_more_blocks_by_the_hour_than_by_the_day(self):
        self.stake("a", 200, at(0, 0))
        self.stake("b", 200, at(0, 0))
        for agent in ("a", "b"):
            for hour in range(0, 30, 2):
                self.mark(agent, 200 + hour, at(hour, 5))
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 14)
        self.assertEqual(self.ev.observe("b", "paper", "day"), 1)

    def test_a_stake_added_mid_block_is_not_growth(self):
        self.stake("a", 200, at(0, 0))
        self.mark("a", 200, at(0, 30))
        self.mark("a", 200, at(1, 10))
        self.stake("a", 100, at(1, 20))
        self.mark("a", 305, at(1, 50))  # the agent made $5; the other $100 was lent to it
        self.mark("a", 305, at(2, 10))
        self.ev.observe("a", "paper", "hour")
        block = self.ev.blocks("a")[1]
        self.assertEqual(block["flow"], 100.0)
        self.assertAlmostEqual(block["log_growth"], math.log(205 / 200), places=12)

    def test_a_stake_withdrawn_mid_block_is_not_a_loss(self):
        self.stake("a", 200, at(0, 0))
        self.mark("a", 200, at(0, 30))
        self.mark("a", 200, at(1, 10))
        self.stake("a", -50, at(1, 20))
        self.mark("a", 152, at(1, 50))  # +$2 of trading, -$50 taken back
        self.mark("a", 152, at(2, 10))
        self.ev.observe("a", "paper", "hour")
        block = self.ev.blocks("a")[1]
        self.assertEqual(block["flow"], -50.0)
        self.assertAlmostEqual(block["log_growth"], math.log(202 / 200), places=12)
        self.assertGreater(block["log_growth"], 0)

    def test_a_stake_between_two_blocks_belongs_to_the_later_block(self):
        self.stake("a", 200, at(0, 0))
        self.mark("a", 200, at(0, 50))
        self.stake("a", 40, at(0, 55))  # after hour 0's last mark, before hour 1's first
        self.mark("a", 240, at(1, 5))
        self.mark("a", 240, at(2, 5))
        self.ev.observe("a", "paper", "hour")
        first, second = self.ev.blocks("a")
        self.assertEqual(first["flow"], 0.0)
        self.assertAlmostEqual(first["log_growth"], 0.0, places=12)
        self.assertEqual(second["flow"], 40.0)
        self.assertAlmostEqual(second["log_growth"], 0.0, places=12)

    def test_a_second_stake_inside_the_first_block_is_a_flow_not_the_start(self):
        self.stake("a", 200, at(0, 0))
        self.mark("a", 200, at(0, 10))
        self.stake("a", 50, at(0, 20))
        self.mark("a", 251, at(0, 50))
        self.mark("a", 251, at(1, 10))
        self.ev.observe("a", "paper", "hour")
        block = self.ev.blocks("a")[0]
        self.assertEqual((block["start_equity"], block["flow"]), (200.0, 50.0))
        self.assertAlmostEqual(block["log_growth"], math.log(201 / 200), places=12)

    def test_two_stakes_before_the_first_mark_are_both_the_start(self):
        self.stake("a", 150, at(0, 0))
        self.stake("a", 50, at(0, 1))
        self.mark("a", 202, at(0, 10))
        self.mark("a", 202, at(1, 10))
        self.ev.observe("a", "paper", "hour")
        self.assertEqual(self.ev.blocks("a")[0]["start_equity"], 200.0)

    def test_re_observation_writes_no_duplicate_blocks(self):
        self.stake("a", 200, at(0, 0))
        for hour in range(5):
            self.mark("a", 200 + hour, at(hour, 10))
        self.ev.observe("a", "paper", "hour")
        before = [(e.seq, e.payload) for e in self.rows("eval.block", "a")]
        for _ in range(3):
            self.ev.observe("a", "paper", "hour")
        after = [(e.seq, e.payload) for e in self.rows("eval.block", "a")]
        self.assertEqual(len(before), 4)
        self.assertEqual(before, after)
        self.assertEqual(self.ledger.verify(), self.ledger.count())

    def test_re_observation_reports_zero_blocks_added(self):
        # Regression: `observe` once counted `entry.seq > last.seq`, which is true for rows already on the
        # ledger too, so it returned every finished block on every call. It now skips recorded keys and
        # counts only the rows it writes.
        self.stake("a", 200, at(0, 0))
        for hour in range(5):
            self.mark("a", 200 + hour, at(hour, 10))
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 4)
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 0)

    def test_observe_counts_only_the_new_block_when_one_more_hour_finishes(self):
        # Regression: the same defect; this used to return 5.
        self.stake("a", 200, at(0, 0))
        for hour in range(5):
            self.mark("a", 200 + hour, at(hour, 10))
        self.ev.observe("a", "paper", "hour")
        self.mark("a", 206, at(5, 10))
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 1)

    def test_incremental_observation_equals_one_observation_at_the_end(self):
        other_dir = tempfile.TemporaryDirectory()
        self.addCleanup(other_dir.cleanup)
        other = Ledger(Path(other_dir.name) / "ledger.db")
        self.addCleanup(other.close)
        for ledger, incremental in ((self.ledger, True), (other, False)):
            ev = Evaluator(ledger)
            ledger.append("book.stake", {"book": "paper", "usd": "200"}, agent="a", at=at(0, 0))
            for hour in range(8):
                ledger.append("book.mark", {"book": "paper", "equity": f"{200 + hour * 0.7:.2f}", "holdings": hour % 2}, agent="a", at=at(hour, 10))
                if hour == 3:
                    ledger.append("book.stake", {"book": "paper", "usd": "25"}, agent="a", at=at(hour, 30))
                if incremental:
                    ev.observe("a", "paper", "hour")
            ev.observe("a", "paper", "hour")
        def economic(ledger):
            # Ledger positions differ between the two runs (blocks are interleaved with marks in
            # one and not the other); everything economic about a block must not.
            return [{k: v for k, v in e.payload.items() if k not in ("first_mark_seq", "last_mark_seq")} for e in ledger.iter(kinds="eval.block")]

        mine, theirs = economic(self.ledger), economic(other)
        self.assertEqual(len(mine), 7)
        self.assertEqual(mine, theirs)

    def test_active_means_holding_something_or_a_fill_or_settlement_in_the_block(self):
        self.stake("a", 200, at(0, 0))
        self.mark("a", 200, at(0, 10))  # hour 0: idle
        self.mark("a", 200, at(1, 10), holdings=1)  # hour 1: holding at one of its marks
        self.mark("a", 200, at(1, 50), holdings=0)
        self.buy("a", 10, at(2, 5))  # hour 2: a fill, flat at the mark
        self.mark("a", 200, at(2, 10))
        self.settle("a", 0.05, at(3, 5))  # hour 3: a settlement
        self.mark("a", 200, at(3, 10))
        self.mark("a", 200, at(4, 10))  # hour 4: idle again
        self.mark("a", 200, at(5, 10))
        self.ev.observe("a", "paper", "hour")
        self.assertEqual([b["active"] for b in self.ev.blocks("a")], [False, True, True, True, False])

    def test_another_agents_or_another_books_fill_does_not_make_a_block_active(self):
        self.stake("a", 200, at(0, 0))
        self.buy("b", 10, at(0, 5))
        self.buy("a", 10, at(0, 6), book="real")
        self.mark("a", 200, at(0, 10))
        self.mark("a", 200, at(1, 10))
        self.ev.observe("a", "paper", "hour")
        self.assertEqual([b["active"] for b in self.ev.blocks("a")], [False])

    def test_books_are_kept_apart(self):
        self.stake("a", 200, at(0, 0), book="paper")
        self.stake("a", 25, at(0, 0), book="real")
        for hour in range(3):
            self.mark("a", 201 + hour, at(hour, 10), book="paper")
            self.mark("a", 24 - hour, at(hour, 11), book="real")
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 2)
        self.assertEqual(self.ev.observe("a", "real", "hour"), 2)
        paper = self.ev.blocks("a", book="paper")
        real = self.ev.blocks("a", book="real")
        self.assertEqual([(b["start_equity"], b["end_equity"]) for b in paper], [(200.0, 201.0), (201.0, 202.0)])
        self.assertEqual([(b["start_equity"], b["end_equity"]) for b in real], [(25.0, 24.0), (24.0, 23.0)])
        self.assertTrue(all(b["log_growth"] < 0 for b in real))
        self.assertEqual(len(self.ev.blocks("a")), 4)

    def test_agents_are_kept_apart(self):
        self.stake("a", 200, at(0, 0))
        self.stake("b", 100, at(0, 0))
        for hour in range(3):
            self.mark("a", 201 + hour, at(hour, 10))
            self.mark("b", 99 - hour, at(hour, 10))
        self.ev.observe("a", "paper", "hour")
        self.assertEqual(self.ev.blocks("b"), [])
        self.ev.observe("b", "paper", "hour")
        self.assertEqual([(b["start_equity"], b["end_equity"]) for b in self.ev.blocks("b")], [(100.0, 99.0), (99.0, 98.0)])

    def test_marks_without_a_stake_make_no_blocks_and_do_not_divide_by_zero(self):
        for hour in range(4):
            self.mark("a", 0, at(hour, 10))
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 0)
        self.assertEqual(self.ev.blocks("a"), [])
        self.ev.seat("a", 1, "test")
        verdict = self.ev.judge("a", "paper")
        self.assertEqual(verdict.decision, "hold")
        self.assertEqual(self.ev.trade_returns("a", "paper"), ([], 0.0))

    def test_no_marks_at_all(self):
        self.stake("a", 200, at(0, 0))
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 0)

    def test_a_stake_that_arrives_after_the_first_mark_counts_from_the_stake(self):
        self.mark("a", 0, at(0, 10))  # the book marked an account it had opened but not funded
        self.stake("a", 200, at(0, 20))
        self.mark("a", 200, at(0, 50))
        self.mark("a", 202, at(1, 10))
        self.mark("a", 202, at(2, 10))
        self.ev.observe("a", "paper", "hour")
        blocks = self.ev.blocks("a")
        # Sept 22, 2026: the block the stake landed in counts, from the stake (meriwether-32's first
        # funded day had been dropped from its paper record).
        self.assertEqual([b["key"][-2:] for b in blocks], ["00", "01"])
        self.assertAlmostEqual(blocks[0]["log_growth"], 0.0, places=12)
        self.assertAlmostEqual(blocks[1]["log_growth"], math.log(202 / 200), places=12)

    def test_an_account_that_goes_to_zero_is_ruin_once_and_then_silence(self):
        self.stake("a", 200, at(0, 0))
        self.mark("a", 200, at(0, 10))
        self.mark("a", 0, at(1, 10))
        self.mark("a", 0, at(2, 10))
        self.mark("a", 0, at(3, 10))
        self.ev.observe("a", "paper", "hour")
        blocks = self.ev.blocks("a")
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[1]["log_growth"], stats.RUIN)
        self.assertTrue(all(math.isfinite(b["log_growth"]) for b in blocks))

    def test_blocks_record_the_marks_that_made_them(self):
        """A block belongs to the rung the agent was on when the block happened, so it carries
        the ledger position of its first mark (not the rung it was written under)."""
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        self.mark("a", 200, at(0, 10))
        self.mark("a", 201, at(1, 10))
        self.ev.observe("a", "paper", "hour")
        block = self.ev.blocks("a")[0]
        self.assertNotIn("rung", block)
        self.assertLessEqual(block["first_mark_seq"], block["last_mark_seq"])
        self.assertEqual(self.ev.blocks("a", since_seq=block["first_mark_seq"]), [])

    def test_observing_the_same_book_after_a_rung_change_does_not_crash(self):
        # Regression: `observe` once re-appended every block with `"rung": self.rung(agent)` in its
        # idempotent payload. Rungs 2 and 3 share the real-money book, so the first observation after a
        # 2 -> 3 promotion raised `LedgerConflict` and the agent could never be judged again. Blocks now
        # carry their mark positions instead of a rung, and a recorded key is never rewritten.
        self.stake("a", 25, at(0, 0), book="real")
        self.ev.seat("a", 2, "test")
        for hour in range(4):
            self.mark("a", 25 + hour * 0.1, at(hour, 10), holdings=1, book="real")
        self.ev.observe("a", "real", "hour")
        self.ev.promote("a", 3, "test")
        self.mark("a", 25.5, at(4, 10), holdings=1, book="real")
        self.ev.observe("a", "real", "hour")  # raises LedgerConflict
        self.assertEqual(len(self.ev.blocks("a", book="real")), 4)


# =================================================================================================
# trade_returns
# =================================================================================================
class TradeReturns(EvalCase):
    def test_returns_are_fractions_of_the_stake_and_risk_is_the_average_buy(self):
        self.stake("a", 200, at())
        self.buy("a", 50, at())
        self.sell("a", 2.0, at())
        self.buy("a", 30, at(), source="cross")
        self.sell("a", -1.0, at())
        self.settle("a", 0.5, at())
        returns, risk = self.ev.trade_returns("a", "paper")
        self.assertEqual(returns, [0.01, -0.005, 0.0025])
        self.assertAlmostEqual(risk, (50 / 200 + 30 / 200) / 2)

    def test_dust_other_books_and_other_agents_are_not_trades(self):
        self.stake("a", 200, at())
        self.sell("a", 5.0, at(), source="dust")
        self.sell("a", 5.0, at(), book="real")
        self.sell("b", 5.0, at())
        self.buy("a", 40, at(), source="dust")
        self.assertEqual(self.ev.trade_returns("a", "paper"), ([], 1.0))  # no entry seen: all of it is assumed at risk

    def test_a_scratch_trade_is_a_closed_trade(self):
        self.stake("a", 200, at())
        self.sell("a", 0.0, at())
        self.assertEqual(self.ev.trade_returns("a", "paper")[0], [0.0])

    def test_only_trades_after_since_seq(self):
        self.stake("a", 200, at())
        self.buy("a", 50, at())
        cut = self.sell("a", 2.0, at()).seq
        self.buy("a", 20, at())
        self.sell("a", -2.0, at())
        returns, risk = self.ev.trade_returns("a", "paper", since_seq=cut)
        self.assertEqual(returns, [-0.01])
        self.assertAlmostEqual(risk, 0.1)

    def test_no_stake_or_a_stake_fully_withdrawn_gives_nothing(self):
        self.sell("a", 2.0, at())
        self.assertEqual(self.ev.trade_returns("a", "paper"), ([], 0.0))
        self.stake("a", 200, at())
        self.stake("a", -200, at())
        self.assertEqual(self.ev.trade_returns("a", "paper"), ([], 0.0))


# =================================================================================================
# judge
# =================================================================================================
class Judge(EvalCase):
    def test_rung_zero_is_not_judged_here(self):
        verdict = self.ev.judge("a", "paper")
        self.assertEqual((verdict.decision, verdict.rung), ("hold", 0))
        self.assertEqual(self.rows("eval.verdict"), [])

    def test_no_look_before_twenty_active_blocks_and_idle_blocks_do_not_count(self):
        self.ev.seat("a", 1, "test")
        for i in range(40):
            self.block("a", 0.003 if i % 2 else -0.001, active=i < 19)
        verdict = self.ev.judge("a", "paper")
        self.assertEqual(verdict.decision, "hold")
        self.assertEqual(verdict.numbers["active_blocks"], 19)
        self.assertEqual(verdict.numbers["blocks"], 40)
        self.assertIn("next look is at 20", verdict.reason)
        self.assertEqual(self.looks("a"), [])

    def test_looks_happen_at_20_25_30_active_blocks_and_each_spends_its_own_alpha(self):
        self.ev.seat("a", 1, "test")
        self.mixed_trades("a")
        looked_at = []
        for i in range(1, 33):
            self.block("a", 0.006 if i % 2 else -0.001)
            verdict = self.ev.judge("a", "paper")
            if "look" in verdict.numbers:
                looked_at.append((i, verdict.numbers["look"]))
            elif i >= 20:
                next_look = 5 * (i // 5) + 5
                self.assertIn(f"next look is at {next_look}", verdict.reason)
        self.assertEqual(looked_at, [(20, 1), (25, 2), (30, 3)])
        looks = self.looks("a")
        self.assertEqual([row["active_blocks"] for row in looks], [20, 25, 30])
        for k, row in enumerate(looks, start=1):
            # Death is tested at every look and spends its own series. Promotion cannot happen
            # before 30 active blocks, so the looks at 20 and 25 spend none of ITS alpha: the look
            # at 30 is promotion's first, with the largest share.
            self.assertEqual((row["tested_death"], row["alpha_death"]), (True, stats.spend(ALPHA, k)))
            self.assertEqual((row["tested_promotion"], row["alpha_spent"]), ((True, stats.spend(ALPHA, 1)) if k == 3 else (False, None)))
            growth = [0.006 if i % 2 else -0.001 for i in range(1, row["blocks"] + 1)]
            self.assertAlmostEqual(row["lcb"], stats.mean_bounds(growth, stats.spend(ALPHA, 1))["lcb"], places=15)
            self.assertAlmostEqual(row["ucb"], stats.mean_bounds(growth, stats.spend(ALPHA, k))["ucb"], places=15)
        self.assertLess(sum(row["alpha_death"] for row in looks), ALPHA)
        self.assertLess(sum(row["alpha_spent"] or 0 for row in looks), ALPHA)

    def test_a_late_first_look_moves_the_cadence_with_it(self):
        self.ev.seat("a", 1, "test")
        for i in range(23):
            self.block("a", 0.006 if i % 2 else -0.001)
        self.assertEqual(self.ev.judge("a", "paper").numbers.get("look"), 1)
        for i in range(4):
            self.block("a", 0.006)
            self.assertNotIn("look", self.ev.judge("a", "paper").numbers)  # 24..27: next look is at 28
        self.block("a", 0.006)
        self.assertEqual(self.ev.judge("a", "paper").numbers.get("look"), 2)

    def test_judging_twice_without_new_blocks_does_not_spend_a_second_look(self):
        self.ev.seat("a", 1, "test")
        for i in range(20):
            self.block("a", 0.006 if i % 2 else -0.001)
        self.assertEqual(self.ev.judge("a", "paper").numbers.get("look"), 1)
        for _ in range(3):
            self.assertEqual(self.ev.judge("a", "paper").decision, "hold")
        self.assertEqual(len(self.looks("a")), 1)

    def test_alpha_spending_decides_a_record_that_full_alpha_would_pass(self):
        """t is about 1.9 on 30 blocks: past the 5% line (1.70) but not the 3.04% line of promotion's first look (1.95)."""
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        self.mixed_trades("a")
        growth = [0.01 if i % 2 == 0 else -0.0048 for i in range(30)]
        verdict = None
        for i, g in enumerate(growth, start=1):
            self.block("a", g)
            if i in (20, 25, 30):
                verdict = self.ev.judge("a", "paper")
        self.assertGreater(stats.mean_bounds(growth, ALPHA)["lcb"], 0)  # an unspent alpha would promote
        self.assertEqual((verdict.numbers["look"], verdict.numbers["alpha_spent"]), (3, stats.spend(ALPHA, 1)))
        self.assertLess(verdict.numbers["lcb"], 0)
        self.assertEqual(verdict.numbers["trades"], 12)  # enough trades: it is the bound that holds it
        self.assertEqual((verdict.decision, verdict.reason), ("hold", "the evidence does not decide yet"))

    def test_a_steady_profitable_agent_becomes_eligible_at_thirty_active_blocks(self):
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        verdicts = self.live("a", WINNER * 14)
        decisions = [v.decision for v in verdicts]
        self.assertEqual(decisions[-1], "eligible")
        self.assertEqual(len(verdicts), 31)  # 31 marks finish 30 blocks
        self.assertEqual(set(decisions[:-1]), {"hold"})
        numbers = verdicts[-1].numbers
        self.assertEqual((numbers["look"], numbers["active_blocks"], numbers["trades"]), (3, 30, 31))
        self.assertGreater(numbers["lcb"], 0)
        self.assertFalse(numbers["lopsided"])
        self.assertIsNone(numbers["loss_gate_lcb"])
        self.assertLess(numbers["drawdown"], 0.01)

    def test_eligible_is_not_promotion(self):
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        self.assertEqual(self.live("a", WINNER * 14)[-1].decision, "eligible")
        self.assertEqual(self.ev.rung("a"), 1)
        decisions = [e.payload["decision"] for e in self.rows("eval.verdict", "a")]
        self.assertEqual(decisions, ["seat", "look", "look", "look"])

    def test_a_steady_loser_dies_at_the_first_look(self):
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        verdicts = self.live("a", LOSER * 14)
        self.assertEqual(verdicts[-1].decision, "die")
        self.assertEqual(len(verdicts), 21)
        self.assertEqual(verdicts[-1].numbers["look"], 1)
        self.assertLess(verdicts[-1].numbers["ucb"], 0)
        self.assertLess(verdicts[-1].numbers["drawdown"], 0.30)  # killed by the bound, not the breaker
        self.assertIn("upper bound", verdicts[-1].reason)
        rows = [e.payload for e in self.rows("eval.verdict", "a")]
        self.assertEqual([r["decision"] for r in rows], ["seat", "look", "die"])
        self.assertEqual(rows[-1]["rung"], 1)
        self.assertEqual(self.ev.rung("a"), 1)  # the evaluator says so; the House does the killing

    def test_a_drawdown_past_thirty_percent_kills_at_once(self):
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        self.mark("a", 200, at(0, 10))
        self.mark("a", 210, at(1, 10))
        self.mark("a", 146, at(2, 10))  # 30.5% below the 210 peak
        self.mark("a", 146, at(3, 10))
        self.ev.observe("a", "paper", "hour")
        verdict = self.ev.judge("a", "paper")
        self.assertEqual(verdict.decision, "die")
        self.assertIn("drawdown", verdict.reason)
        self.assertAlmostEqual(verdict.numbers["drawdown"], 64 / 210)
        self.assertEqual(self.looks("a"), [])  # the breaker needs no look and spends no alpha
        self.assertEqual(self.rows("eval.verdict", "a")[-1].payload["decision"], "die")

    def test_the_drawdown_limit_is_inclusive_and_just_under_it_lives(self):
        for agent, trough, decision in (("at", 140.0, "die"), ("under", 140.5, "hold")):
            self.ev.seat(agent, 1, "test")
            self.ledger.append("eval.block", {"book": "paper", "key": "k1", "start_equity": 200.0, "end_equity": trough, "flow": 0.0,
                                              "log_growth": math.log(trough / 200.0), "active": True}, agent=agent)
            self.assertEqual(self.ev.judge(agent, "paper").decision, decision, agent)

    def test_the_drawdown_is_measured_from_the_first_blocks_start(self):
        self.ev.seat("a", 1, "test")
        self.ledger.append("eval.block", {"book": "paper", "key": "k1", "start_equity": 200.0, "end_equity": 130.0, "flow": 0.0,
                                          "log_growth": math.log(130 / 200), "active": True}, agent="a")
        verdict = self.ev.judge("a", "paper")
        self.assertEqual(verdict.decision, "die")
        self.assertAlmostEqual(verdict.numbers["drawdown"], 0.35)

    def test_taking_part_of_a_stake_back_is_not_a_drawdown(self):
        # Regression: the drawdown was once read from raw `end_equity`, so the House taking back 40% of
        # a flat agent's stake was a 40% "drawdown" and a death. It is now the drawdown of the wealth
        # index built from the blocks' log growth, which has the stake flows taken out.
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        self.mark("a", 200, at(0, 10))
        self.mark("a", 201, at(1, 10))
        self.stake("a", -80, at(1, 30))
        self.mark("a", 121, at(1, 50))
        self.mark("a", 121, at(2, 10))
        self.ev.observe("a", "paper", "hour")
        self.assertTrue(all(b["log_growth"] >= 0 for b in self.ev.blocks("a")))  # it never lost a cent
        verdict = self.ev.judge("a", "paper")
        self.assertEqual(verdict.decision, "hold")

    def test_a_deposit_does_not_hide_a_drawdown(self):
        # Regression: the mirror of the test above. 200 -> 130 with $100 lent in the same block once
        # read as 200 -> 230 and no drawdown.
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        self.mark("a", 200, at(0, 10))
        self.mark("a", 200, at(1, 10))
        self.stake("a", 100, at(1, 30))
        self.mark("a", 230, at(1, 50))
        self.mark("a", 230, at(2, 10))
        self.ev.observe("a", "paper", "hour")
        self.assertAlmostEqual(self.ev.blocks("a")[1]["log_growth"], math.log(130 / 200))
        self.assertEqual(self.ev.judge("a", "paper").decision, "die")

    def test_a_few_clean_wins_are_not_eligible_though_the_t_bound_is_positive(self):
        self.ev.seat("fav", 1, "test")
        self.ev.seat("mix", 1, "test")
        self.stake("fav", 200, at())
        self.stake("mix", 200, at())
        self.trades("fav", [1.0] * 12, cost=90.0)  # twelve small wins, $90 at risk each time, no loss yet
        self.trades("mix", [3.0, 3.0, -1.0] * 4, cost=90.0)
        verdicts = {}
        for agent in ("fav", "mix"):
            for i in range(1, 31):
                self.block(agent, 0.006 if i % 3 else -0.001)
                if i in (20, 25, 30):
                    verdicts[agent] = self.ev.judge(agent, "paper")
        fav, mix = verdicts["fav"], verdicts["mix"]
        self.assertEqual(fav.numbers["lcb"], mix.numbers["lcb"])
        self.assertGreater(fav.numbers["lcb"], 0)
        self.assertTrue(fav.numbers["lopsided"])
        self.assertLess(fav.numbers["loss_gate_lcb"], 0)
        self.assertEqual(fav.numbers["trades"], 12)  # past the minimum: only the exact-bound gate is in its way
        self.assertEqual((fav.decision, fav.reason), ("hold", "the evidence does not decide yet"))
        self.assertFalse(mix.numbers["lopsided"])
        self.assertEqual(mix.decision, "eligible")  # the same blocks with an honest mix of trades pass

    def test_the_lopsided_gate_uses_the_spent_alpha_and_the_measured_risk(self):
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        self.trades("a", [1.0] * 12, cost=90.0)
        for i in range(1, 21):
            self.block("a", 0.006 if i % 3 else -0.001)
        verdict = self.ev.judge("a", "paper")
        expected = stats.lopsided_growth_lcb([1.0 / 200] * 12, 90.0 / 200, stats.spend(ALPHA, 1))
        self.assertAlmostEqual(verdict.numbers["loss_gate_lcb"], expected, places=15)

    def test_fewer_than_ten_closed_trades_holds_and_the_tenth_unlocks(self):
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        self.trades("a", [2.0, -1.0, 2.0, -1.0])  # the fast lane (Sept 21, 2026): five closed trades, not ten
        for i in range(1, 31):
            self.block("a", 0.006 if i % 3 else -0.001)
            if i in (20, 25, 30):
                verdict = self.ev.judge("a", "paper")
        self.assertGreater(verdict.numbers["lcb"], 0)
        self.assertEqual(verdict.numbers["trades"], 4)
        self.assertEqual(verdict.decision, "hold")
        self.assertIn("4 closed trades", verdict.reason)
        self.trades("a", [-1.0])
        for _ in range(5):
            self.block("a", 0.006)
        verdict = self.ev.judge("a", "paper")
        self.assertEqual((verdict.numbers["trades"], verdict.decision), (5, "eligible"))

    def test_trades_from_before_the_rung_do_not_count_toward_the_minimum(self):
        self.stake("a", 200, at())
        self.mixed_trades("a", 12)
        self.ev.seat("a", 1, "test")
        for i in range(1, 31):
            self.block("a", 0.006 if i % 3 else -0.001)
            if i in (20, 25, 30):
                verdict = self.ev.judge("a", "paper")
        self.assertEqual((verdict.numbers["trades"], verdict.decision), (0, "hold"))

    def test_growth_without_variance_holds(self):
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        self.mixed_trades("a")
        for i in range(1, 31):
            self.block("a", 0.004)
            if i in (20, 25, 30):
                verdict = self.ev.judge("a", "paper")
        self.assertEqual(verdict.numbers["sd"], 0.0)
        self.assertGreater(verdict.numbers["lcb"], 0)
        self.assertEqual(verdict.decision, "hold")

    def test_an_idle_agent_whose_growth_is_all_zero_is_never_looked_at(self):
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        for hour in range(40):
            self.mark("a", 200, at(hour, 10))
        self.ev.observe("a", "paper", "hour")
        verdict = self.ev.judge("a", "paper")
        self.assertEqual((verdict.decision, verdict.numbers["active_blocks"], verdict.numbers["blocks"]), ("hold", 0, 39))
        self.assertEqual(self.looks("a"), [])

    def test_blocks_trades_and_looks_of_an_earlier_rung_do_not_leak_in(self):
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        self.mixed_trades("a", 12)
        for i in range(25):
            self.block("a", 0.006 if i % 3 else -0.001)
            self.ev.judge("a", "paper")
        self.assertEqual(len(self.looks("a")), 2)
        self.ev.promote("a", 2, "test")
        for i in range(3):
            self.block("a", -0.02)  # same book name on purpose: only the sequence number separates them
        verdict = self.ev.judge("a", "paper")
        self.assertEqual((verdict.rung, verdict.decision), (2, "hold"))
        self.assertEqual((verdict.numbers["blocks"], verdict.numbers["active_blocks"]), (3, 3))
        for i in range(17):
            self.block("a", 0.004 if i % 2 else -0.002)
        verdict = self.ev.judge("a", "paper")
        self.assertEqual(verdict.numbers["look"], 1)  # the first look of THIS rung, with a full alpha share
        self.assertEqual(verdict.numbers["alpha_death"], stats.spend(ALPHA, 1))
        self.assertIsNone(verdict.numbers["alpha_spent"])  # 20 blocks: it could only have died
        self.assertEqual(verdict.numbers["blocks"], 20)
        self.assertEqual(verdict.numbers["trades"], 0)

    def test_a_backlog_of_blocks_from_the_time_on_another_rung_is_not_judged_on_this_one(self):
        # Regression: a block once belonged to a rung by when its ROW was written. The paper book is not
        # observed while an agent is on rung 2, so after a demotion its whole backlog was written at
        # once and judged as the new rung-1 record: a paper settlement loss taken during the stay on
        # real money killed the agent on its return. A block now carries `first_mark_seq`, and
        # `blocks(since_seq)` keeps those that BEGAN after the rung was entered.
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        for hour in range(3):
            self.mark("a", 200, at(hour, 10))
        self.ev.observe("a", "paper", "hour")
        self.ev.promote("a", 2, "test")
        self.mark("a", 200, at(3, 10), holdings=1)  # still holding a paper contract to settlement
        self.settle("a", -70.0, at(4, 5))  # it settles against the agent while it is on rung 2
        self.mark("a", 130, at(4, 10))
        self.mark("a", 130, at(5, 10))
        self.ev.demote("a", "drift on the real book")
        self.mark("a", 130, at(6, 10))
        self.mark("a", 130, at(7, 10))
        self.ev.observe("a", "paper", "hour")
        verdict = self.ev.judge("a", "paper")
        self.assertLessEqual(verdict.numbers["blocks"], 2)  # hours 5 and 6 at most: the rung was entered in hour 5
        self.assertEqual(verdict.decision, "hold")

    def test_a_lopsided_record_with_no_measured_risk_is_not_waved_through(self):
        # Regression: `trade_returns` once reported a risk of 0.0 when no buy had been seen since the
        # rung began (contracts carried in and settling later), which made the worst case of the
        # lopsided gate a loss of nothing, so any all-win record passed. No entry seen now means all of
        # the stake is assumed at risk.
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        for _ in range(12):
            self.settle("a", 0.5, at())  # twelve favourites came in; the buys were before this rung
        for i in range(1, 31):
            self.block("a", 0.006 if i % 3 else -0.001)
            if i in (20, 25, 30):
                verdict = self.ev.judge("a", "paper")
        self.assertTrue(verdict.numbers["lopsided"])
        self.assertNotEqual(verdict.decision, "eligible")

    def test_a_drawdown_on_an_earlier_rung_does_not_kill_on_this_one(self):
        self.ev.seat("a", 1, "test")
        self.block("a", math.log(0.6))
        self.assertEqual(self.ev.judge("a", "paper").decision, "die")
        self.ev.seat("a", 1, "a second life, for the test")
        self.block("a", 0.001)
        self.assertEqual(self.ev.judge("a", "paper").decision, "hold")

    def test_rung_three_can_die_but_is_never_eligible(self):
        self.ev.seat("up", 3, "test")
        self.ev.seat("down", 3, "test")
        self.stake("up", 25, at(), book="real")
        self.trades("up", [0.2, -0.1] * 6, book="real", cost=5.0)
        for i in range(1, 31):
            self.block("up", 0.006 if i % 3 else -0.001, book="real", start=25.0)
            self.block("down", -0.006 if i % 3 else 0.001, book="real", start=25.0)
            if i in (20, 25, 30):
                up = self.ev.judge("up", "real")
                down = self.ev.judge("down", "real") if i == 20 else down
        self.assertGreater(up.numbers["lcb"], 0)
        self.assertEqual((up.numbers["trades"], up.numbers["active_blocks"]), (12, 30))
        self.assertEqual((up.decision, up.reason), ("hold", "the evidence does not decide yet"))  # there is no rung 4
        self.assertEqual(down.decision, "die")

    def test_a_custom_constitution_is_honoured(self):
        rules = copy.deepcopy(CONSTITUTION)
        rules["ladder"].update(look_every_active_blocks=2, min_closed_trades=2)
        rules["ladder"]["paper"]["min_active_blocks"] = 4
        rules["ladder"]["death"]["min_active_blocks"] = 6
        ev = Evaluator(self.ledger, constitution=rules)
        ev.seat("a", 1, "test")
        decisions = []
        for i in range(1, 7):
            self.block("a", -0.006 if i % 2 else -0.0055)  # so steady a loss that even look 1's bound is below zero
            decisions.append((ev.judge("a", "paper").decision, len(self.looks("a"))))
        # Looks start at min(death, promotion) = 4. Below the death threshold a look runs only the
        # SCREEN, which spends no alpha, so it is not rationed and happens every block; the every-2
        # rationing applies from 6, where the statistical death test begins to cost something.
        self.assertEqual(decisions, [("hold", 0), ("hold", 0), ("hold", 0), ("hold", 1), ("hold", 2), ("die", 3)])

    def test_judging_is_deterministic(self):
        def run(path):
            ledger = Ledger(path)
            ev = Evaluator(ledger)
            ledger.append("book.stake", {"book": "paper", "usd": "200"}, agent="w", at=at(0, 0))
            ledger.append("book.stake", {"book": "paper", "usd": "200"}, agent="l", at=at(0, 0))
            ev.seat("w", 1, "test")
            ev.seat("l", 1, "test")
            self._equity.clear()
            out = [(v.decision, v.reason, v.numbers) for v in self.live("w", WINNER * 14, ev=ev)]
            self._equity.clear()
            out += [(v.decision, v.reason, v.numbers) for v in self.live("l", LOSER * 14, ev=ev)]
            rows = [(e.kind, e.agent, e.payload) for e in ledger.iter(kinds=("eval.block", "eval.verdict"))]
            ledger.close()
            return out, rows

        first = run(Path(self.dir.name) / "one.db")
        second = run(Path(self.dir.name) / "two.db")
        self.assertEqual(first, second)
        self.assertEqual(first[0][-1][0], "die")

    def test_judging_the_same_ledger_again_from_a_fresh_evaluator_agrees(self):
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        self.live("a", WINNER * 9)  # 27 marks: looks at 20 and 25 are on the ledger
        again = Evaluator(self.ledger, constitution=self.ev.c)
        self.assertEqual(again.rung("a"), 1)
        self.assertEqual(again.blocks("a"), self.ev.blocks("a"))
        first, second = self.ev.judge("a", "paper"), again.judge("a", "paper")
        self.assertEqual((first.decision, first.reason, first.numbers), (second.decision, second.reason, second.numbers))


# =================================================================================================
# rung 0: replay trials
# =================================================================================================
def replay_result(growth=None, *, ok=True, trades=25, oos_blocks=12, oos_mean=0.004, **more):
    growth = [0.012, 0.004, -0.004, 0.008] * 10 if growth is None else growth
    result = {
        "ok": ok, "blocks": [{"key": f"b{i}", "log_growth": g, "active": True} for i, g in enumerate(growth)], "trades": trades,
        "out_of_sample": {"blocks": oos_blocks, "mean_log_growth": oos_mean}, "code_sha256": "c0de", "params": {"n": 3},
        "return_pct": 12.5, "max_drawdown": 0.04, "fees_usd": 1.25,
    }
    result.update(more)
    return result


class ReplaySept22(EvalCase):
    """The owner's Sept 22, 2026 paper gate: enough trades to judge and positive out-of-sample growth."""

    def setUp(self):
        super().setUp()
        self.ev = Evaluator(self.ledger, constitution=CONSTITUTION)

    def test_a_long_line_no_longer_deflates_a_paper_seat_away(self):
        for i, value in enumerate(-1.0 + 2.0 * i / 198 for i in range(199)):
            self.ledger.append("eval.trial", {"family": "crowded", "sharpe": value, "passed": False}, agent=f"cousin-{i % 7}")
        late = self.ev.record_trial("latecomer", "crowded", replay_result())
        self.assertEqual((late.decision, late.numbers["trials"]), ("promote", 200))

    def test_ten_trades_and_positive_out_of_sample_growth_are_still_required(self):
        self.assertEqual(self.ev.record_trial("ten", "a", replay_result(trades=10)).decision, "promote")
        nine = self.ev.record_trial("nine", "b", replay_result(trades=9))
        self.assertEqual(nine.decision, "hold")
        self.assertIn("9 closed trades, 10 needed", nine.reason)
        flat = self.ev.record_trial("flat", "c", replay_result(oos_mean=0.0))
        self.assertEqual(flat.decision, "hold")
        self.assertIn("out-of-sample", flat.reason)

    def test_the_revision_leaves_the_money_rules_and_the_live_grant_alone(self):
        # Pinned to d715ae7a... when written; the Sept 23, 2026 money revision (the settled lane and
        # audit-after) re-pinned the money rules, so the property is tested rather than the value:
        # the replay gate is risk-free, and moving it never touches the money digest.
        import copy

        from league.constitution import money_digest
        moved = copy.deepcopy(CONSTITUTION)
        moved["ladder"]["replay"] = {"min_trades": 20, "min_blocks": 20, "min_deflated_sharpe": 0.5, "min_oos_blocks": 8}
        self.assertEqual(money_digest(moved), money_digest())


class ReplayTrials(EvalCase):
    def seed_trials(self, family, sharpes, agent_prefix="cousin"):
        for i, value in enumerate(sharpes):
            self.ledger.append("eval.trial", {"family": family, "sharpe": value, "passed": False}, agent=f"{agent_prefix}-{i % 7}")

    def test_a_good_first_replay_is_promoted_to_paper(self):
        verdict = self.ev.record_trial("a", "fam", replay_result(), tape_id="tape-1")
        self.assertEqual((verdict.decision, verdict.rung), ("promote", 1))
        self.assertEqual(self.ev.rung("a"), 1)
        trial = self.rows("eval.trial", "a")[0].payload
        self.assertTrue(trial["passed"])
        self.assertEqual(trial["reasons"], [])
        self.assertEqual((trial["family"], trial["tape"], trial["trials"], trial["blocks"], trial["trades"]), ("fam", "tape-1", 1, 40, 25))
        self.assertEqual((trial["code_sha256"], trial["params"], trial["fees_usd"]), ("c0de", {"n": 3}, 1.25))
        self.assertAlmostEqual(trial["sharpe"], stats.sharpe([0.012, 0.004, -0.004, 0.008] * 10))
        self.assertEqual(trial["benchmark_sharpe"], 0.0)  # one trial is not a selection
        self.assertGreater(trial["deflated_sharpe"], 0.9)
        promote = self.rows("eval.verdict", "a")[-1].payload
        self.assertEqual((promote["decision"], promote["from_rung"], promote["to_rung"]), ("promote", 0, 1))

    def test_each_threshold_is_a_reason_to_hold(self):
        cases = {
            "trades": (replay_result(trades=19), "19 closed trades"),
            "blocks": (replay_result([0.012, 0.004, -0.004, 0.008] * 4 + [0.01, 0.01, 0.01]), "19 blocks"),
            "oos-blocks": (replay_result(oos_blocks=7), "out-of-sample"),
            "oos-growth": (replay_result(oos_mean=0.0), "out-of-sample"),
            "oos-missing": (replay_result(out_of_sample=None), "out-of-sample"),
            "dsr": (replay_result([0.010, -0.011] * 20), "deflated Sharpe"),
            "flat": (replay_result([0.0] * 40), "deflated Sharpe undefined"),
        }
        for agent, (result, needle) in cases.items():
            verdict = self.ev.record_trial(agent, f"fam-{agent}", result)
            self.assertEqual(verdict.decision, "hold", agent)
            self.assertIn(needle, verdict.reason, agent)
            self.assertEqual(self.ev.rung(agent), 0, agent)
            self.assertFalse(self.rows("eval.trial", agent)[0].payload["passed"], agent)

    def test_the_thresholds_are_inclusive_at_their_minimum(self):
        growth = ([0.012, 0.004, -0.004, 0.008] * 8)[:30]
        verdict = self.ev.record_trial("a", "fam", replay_result(growth, trades=20, oos_blocks=8, oos_mean=1e-9))
        self.assertEqual(verdict.decision, "promote")

    def test_the_same_result_passes_as_the_first_trial_and_fails_as_the_two_hundredth(self):
        first = self.ev.record_trial("pioneer", "fresh", replay_result())
        self.assertEqual(first.decision, "promote")
        spread = [-1.0 + 2.0 * i / 198 for i in range(199)]  # what two hundred unskilled variants look like
        self.seed_trials("crowded", spread)
        late = self.ev.record_trial("latecomer", "crowded", replay_result())
        self.assertEqual(late.decision, "hold")
        self.assertEqual(late.numbers["trials"], 200)
        self.assertEqual(late.numbers["sharpe"], first.numbers["sharpe"])
        self.assertGreater(late.numbers["benchmark_sharpe"], late.numbers["sharpe"])
        self.assertLess(late.numbers["deflated_sharpe"], 0.9)
        self.assertIn("against 200 trials", late.reason)
        self.assertEqual(self.ev.rung("latecomer"), 0)

    def test_trials_are_pooled_by_family_across_agents_and_not_across_families(self):
        self.seed_trials("crowded", [-1.0 + 2.0 * i / 198 for i in range(199)])
        self.assertEqual(len(self.ev.family_trials("crowded")), 199)
        self.assertEqual(self.ev.family_trials("quiet"), [])
        verdict = self.ev.record_trial("loner", "quiet", replay_result())
        self.assertEqual((verdict.decision, verdict.numbers["trials"]), ("promote", 1))

    def test_a_candidate_is_deflated_by_its_own_line_not_by_its_cousins(self):
        # Measured Sept 19, 2026: six sports founders shared one family, so their six founding
        # replays spent the family's whole trial budget and every agent then refused to experiment.
        # What a deflated Sharpe corrects for is picking the best of several tries at ONE idea.
        self.seed_trials("sports", [0.1] * 6)
        self.assertEqual(len(self.ev.family_trials("sports")), 6)
        self.assertEqual(len(self.ev.family_trials("sports", ["newcomer"])), 0)
        good = replay_result([0.012, 0.004, -0.004, 0.008] * 10)
        cousin_blind = self.ev.record_trial("newcomer", "sports", good, promote=False, lineage=["newcomer"])
        self.assertEqual(cousin_blind.numbers["trials"], 1)
        # Its own tries still count, and its child inherits them: there is no way to start again.
        for i in range(3):
            self.ev.record_trial("newcomer", "sports", good, promote=False, lineage=["newcomer"])
        child = self.ev.record_trial("child", "sports", good, promote=False, lineage=["child", "newcomer"])
        self.assertEqual(child.numbers["trials"], 5)  # the parent's four, and its own
        self.assertLess(child.numbers["deflated_sharpe"], cousin_blind.numbers["deflated_sharpe"])

    def test_every_trial_raises_the_bar_for_the_next(self):
        benchmarks = []
        for i in range(6):
            verdict = self.ev.record_trial(f"agent-{i}", "fam", replay_result([0.012 + 0.002 * i, 0.004, -0.004 - 0.002 * i, 0.008] * 10), promote=False)
            benchmarks.append(verdict.numbers["benchmark_sharpe"])
            self.assertEqual(verdict.numbers["trials"], i + 1)
        self.assertEqual(benchmarks[0], 0.0)
        self.assertEqual(benchmarks, sorted(benchmarks))
        self.assertGreater(benchmarks[-1], benchmarks[1])

    def test_promote_false_never_promotes_but_is_still_a_counted_trial(self):
        verdict = self.ev.record_trial("a", "fam", replay_result(), promote=False)
        self.assertEqual((verdict.decision, verdict.rung), ("hold", 0))
        self.assertTrue(verdict.numbers["passed"])
        self.assertEqual(self.ev.rung("a"), 0)
        self.assertEqual(self.rows("eval.verdict", "a"), [])
        self.assertEqual(len(self.ev.family_trials("fam")), 1)
        second = self.ev.record_trial("a", "fam", replay_result(), promote=False)
        self.assertEqual(second.numbers["trials"], 2)

    def test_an_agent_already_above_replay_is_not_promoted_again(self):
        self.ev.seat("a", 2, "test")
        verdict = self.ev.record_trial("a", "fam", replay_result())
        self.assertEqual((verdict.decision, verdict.rung), ("hold", 2))
        self.assertEqual(self.ev.rung("a"), 2)

    def test_a_failed_replay_is_recorded_and_never_passes(self):
        verdict = self.ev.record_trial("a", "fam", replay_result(ok=False, error="too many errors"))
        self.assertEqual(verdict.decision, "hold")
        self.assertIn("the replay failed: too many errors", verdict.reason)
        trial = self.rows("eval.trial", "a")[0].payload
        self.assertEqual((trial["passed"], trial["sharpe"], trial["deflated_sharpe"]), (False, None, None))
        self.assertEqual(self.ev.rung("a"), 0)

    def test_a_failed_replay_still_counts_as_a_trial_for_the_family(self):
        # Regression: `family_trials` once dropped trials without a Sharpe ratio, so a failed (or flat)
        # replay never raised N in the deflated Sharpe, and a strategy that raised whenever a run went
        # badly got its tries for free. Every `eval.trial` row of the family now counts toward N; only
        # the defined Sharpes feed the variance.
        for i in range(50):
            self.ev.record_trial(f"crasher-{i % 5}", "fam", replay_result(ok=False, error="too many errors"))
        self.assertEqual(self.ledger.count(kinds="eval.trial"), 50)
        verdict = self.ev.record_trial("a", "fam", replay_result(), promote=False)
        self.assertEqual(verdict.numbers["trials"], 51)

    def test_failed_replays_raise_the_bar(self):
        # Regression: the consequence of the one above. The benchmark after fifty failed tries was once 0.0.
        for i in range(50):
            self.ev.record_trial(f"crasher-{i % 5}", "fam", replay_result(ok=False, error="too many errors"))
        verdict = self.ev.record_trial("a", "fam", replay_result(), promote=False)
        self.assertGreater(verdict.numbers["benchmark_sharpe"], 0.0)

    def test_a_malformed_result_does_not_raise(self):
        for i, result in enumerate(({}, {"ok": True}, {"ok": True, "blocks": [], "trades": None, "out_of_sample": {}})):
            verdict = self.ev.record_trial(f"a{i}", "fam", result)
            self.assertEqual(verdict.decision, "hold")


# =================================================================================================
# seat, promote, demote
# =================================================================================================
class Rungs(EvalCase):
    def test_an_unknown_agent_is_on_rung_zero(self):
        self.assertEqual(self.ev.rung("nobody"), 0)
        self.assertEqual(self.ev._rung_entered("nobody"), 0)

    def test_the_sequence_of_a_career(self):
        self.ev.seat("a", 1, "test")
        seated = self.rows("eval.verdict", "a")[-1].seq
        self.assertEqual((self.ev.rung("a"), self.ev._rung_entered("a")), (1, seated))
        up = self.ev.promote("a", 2, "audit passed", {"lcb": 0.001})
        self.assertEqual((up.decision, up.rung, up.numbers), ("promote", 2, {"lcb": 0.001}))
        promoted = self.rows("eval.verdict", "a")[-1]
        self.assertEqual((promoted.payload["from_rung"], promoted.payload["to_rung"], promoted.payload["lcb"]), (1, 2, 0.001))
        self.assertEqual((self.ev.rung("a"), self.ev._rung_entered("a")), (2, promoted.seq))
        self.ev.promote("a", 3, "scaled")
        self.assertEqual(self.ev.rung("a"), 3)
        down = self.ev.demote("a", "drift")
        self.assertEqual((down.decision, down.rung), ("demote", 2))
        demoted = self.rows("eval.verdict", "a")[-1]
        self.assertEqual((demoted.payload["from_rung"], demoted.payload["to_rung"]), (3, 2))
        self.assertEqual((self.ev.rung("a"), self.ev._rung_entered("a")), (2, demoted.seq))
        self.ev.demote("a", "drift again")
        self.assertEqual(self.ev.rung("a"), 1)

    def test_a_promotion_moves_exactly_one_rung(self):
        self.ev.seat("a", 1, "test")
        for target in (0, 1, 3, 4):
            with self.assertRaises(ValueError):
                self.ev.promote("a", target, "skip")
        self.assertEqual(self.ev.rung("a"), 1)
        with self.assertRaises(ValueError):
            self.ev.promote("fresh", 2, "skip")

    def test_nothing_is_demoted_below_paper(self):
        for agent, rung in (("zero", None), ("one", 1)):
            if rung:
                self.ev.seat(agent, rung, "test")
            with self.assertRaises(ValueError):
                self.ev.demote(agent, "no")

    def test_looks_deaths_and_other_agents_rows_do_not_move_a_rung(self):
        self.ev.seat("a", 2, "test")
        entered = self.ev._rung_entered("a")
        self.ledger.append("eval.verdict", {"decision": "look", "rung": 2, "to_rung": 9}, agent="a")
        self.ledger.append("eval.verdict", {"decision": "die", "rung": 2}, agent="a")
        self.ev.seat("b", 3, "test")
        self.assertEqual((self.ev.rung("a"), self.ev._rung_entered("a")), (2, entered))
        self.assertEqual(self.ev.rung("b"), 3)

    def test_the_rung_survives_a_restart(self):
        self.ev.seat("a", 1, "test")
        self.ev.promote("a", 2, "test")
        self.assertEqual(Evaluator(self.ledger).rung("a"), 2)

    def test_the_latest_move_is_folded_once_and_then_from_the_new_verdicts_only(self):
        """Sept 24, 2026 (R6-perf): `rung` and `_rung_entered` read every verdict of the agent on every call
        (150,000 rows parsed a tick on a copy of the 17:27Z snapshot). The latest move is now folded from the
        verdicts after the last one read; it answers as the per-agent scan did, and another writer's verdict
        on the same ledger counts at once."""
        def scanned(agent):  # the answer as it was read before: the agent's verdicts, newest first
            for entry in reversed(self.ledger.read(kinds="eval.verdict", agent=agent, limit=10_000, newest=True)):
                if entry.payload.get("decision") in ("promote", "demote", "seat"):
                    return int(entry.payload["to_rung"]), entry.seq
            return 0, 0

        self.ev.seat("a", 1, "test")
        self.ev.seat("b", 1, "test")
        for _ in range(3):
            self.ledger.append("eval.verdict", {"decision": "look", "rung": 1}, agent="a")
        self.assertEqual((self.ev.rung("a"), self.ev._rung_entered("a")), scanned("a"))
        other = Evaluator(self.ledger, constitution=BOUND)  # another thread's evaluator on the same ledger
        other.promote("a", 2, "passed")
        self.ledger.append("eval.verdict", {"decision": "look", "rung": 2, "to_rung": 9}, agent="a")
        other.seat("c", 1, "test")
        with patch.object(self.ledger, "read", wraps=self.ledger.read) as read:
            answers = {agent: (self.ev.rung(agent), self.ev._rung_entered(agent)) for agent in ("a", "b", "c", "nobody")}
        self.assertEqual(answers, {agent: scanned(agent) for agent in answers})
        self.assertEqual(answers["a"][0], 2)
        self.assertTrue(read.call_args_list)
        self.assertTrue(all(call.kwargs.get("agent") is None and call.kwargs.get("after", 0) > 0 for call in read.call_args_list),
                        "only the verdicts after the last one folded are read")


# =================================================================================================
# drift
# =================================================================================================
class Drift(EvalCase):
    def earn_rung_two(self, agent="a"):
        self.ev.seat(agent, 1, "test")
        for i in range(30):
            self.block(agent, 0.006 if i % 2 else 0.0)  # mean +0.3%, sd about 0.3%
        self.ev.promote(agent, 2, "test")

    def test_drift_is_not_watched_below_real_money(self):
        self.ev.seat("a", 1, "test")
        verdict = self.ev.drift("a", "paper")
        self.assertEqual(verdict.decision, "hold")
        self.assertEqual(self.rows("eval.drift"), [])

    def test_a_sustained_fall_raises_the_alarm_and_demotes(self):
        self.earn_rung_two()
        for _ in range(4):
            self.block("a", -0.005, book="real", start=25.0)
        verdict = self.ev.drift("a", "real")
        self.assertEqual((verdict.decision, verdict.rung), ("demote", 1))
        self.assertTrue(verdict.numbers["alarm"])
        self.assertAlmostEqual(verdict.numbers["reference_mean"], 0.003)
        self.assertEqual(self.ev.rung("a"), 1)
        drift_row = self.rows("eval.drift", "a")[-1].payload
        self.assertEqual((drift_row["rung"], drift_row["book"], drift_row["alarm"]), (2, "real", True))
        last = self.rows("eval.verdict", "a")[-1].payload
        self.assertEqual((last["decision"], last["from_rung"], last["to_rung"]), ("demote", 2, 1))

    def test_growth_like_the_record_holds(self):
        self.earn_rung_two()
        for i in range(30):
            self.block("a", 0.006 if i % 2 else 0.0, book="real", start=25.0)
        verdict = self.ev.drift("a", "real")
        self.assertEqual((verdict.decision, verdict.reason), ("hold", "no decay"))
        self.assertFalse(verdict.numbers["alarm"])
        self.assertEqual(self.ev.rung("a"), 2)
        self.assertEqual(len(self.rows("eval.drift", "a")), 1)

    def test_one_bad_block_is_forgiven(self):
        self.earn_rung_two()
        self.block("a", -0.006, book="real", start=25.0)
        self.assertEqual(self.ev.drift("a", "real").decision, "hold")

    def test_without_a_reference_record_there_is_nothing_to_drift_from(self):
        self.ev.seat("a", 2, "test")
        for _ in range(10):
            self.block("a", -0.01, book="real", start=25.0)
        verdict = self.ev.drift("a", "real")
        self.assertEqual(verdict.decision, "hold")
        self.assertIn("no reference", verdict.reason)
        self.assertEqual(self.ev.rung("a"), 2)

    def test_no_recent_blocks_or_a_flat_reference_holds(self):
        self.earn_rung_two("fresh")
        self.assertEqual(self.ev.drift("fresh", "real").decision, "hold")
        self.ev.seat("flat", 1, "test")
        for _ in range(30):
            self.block("flat", 0.002)
        self.ev.promote("flat", 2, "test")
        for _ in range(10):
            self.block("flat", -0.01, book="real", start=25.0)
        self.assertEqual(self.ev.drift("flat", "real").decision, "hold")

    def test_only_the_window_of_recent_blocks_is_read_and_a_recovery_clears_the_alarm(self):
        self.earn_rung_two()
        for _ in range(6):
            self.block("a", -0.01, book="real", start=25.0)  # an alarm, were it read now
        window = int(self.ev.ladder["drift"]["window_blocks"])
        for i in range(window):
            self.block("a", 0.006 if i % 2 else 0.0, book="real", start=25.0)
        verdict = self.ev.drift("a", "real")
        self.assertEqual(verdict.decision, "hold")
        self.assertEqual(verdict.numbers["statistic"], verdict.numbers["statistic"])
        self.assertIsNone(verdict.numbers["at"])  # the six bad blocks are outside the window of recent blocks

    def test_blocks_of_the_other_book_are_not_recent_growth(self):
        self.earn_rung_two()
        for _ in range(6):
            self.block("a", -0.01, book="paper")  # the paper account winding down after the promotion
        self.block("a", 0.003, book="real", start=25.0)
        self.assertEqual(self.ev.drift("a", "real").decision, "hold")

    def climb_to_three_with_a_flat_paper_account_in_the_window(self, agent="a"):
        """Rung 2 was earned on paper and rung 3 on the real book (+0.4% a block, steadily), while
        the wound-down paper account went on being marked, flat and idle, inside the same stay."""
        self.ev.seat(agent, 1, "test")
        for i in range(30):
            self.block(agent, 0.013 if i % 2 else 0.007)
        self.ev.promote(agent, 2, "test")
        for i in range(30):
            self.block(agent, 0.005 if i % 2 else 0.003, book="real", start=25.0)
            self.block(agent, 0.0, book="paper", active=False)
            self.block(agent, 0.0, book="paper", active=False)
        self.ev.promote(agent, 3, "test")

    def test_the_record_that_earned_a_rung_is_the_record_of_one_book(self):
        # Regression: `_record_below` once took every block that began inside the stay, whatever
        # its book, so a wound-down paper account (still marked, flat) diluted the real-money
        # record: here the reference would have been +0.13% with twice the sd instead of +0.4%.
        # It now keeps the one book the stay was traded on (the book with the active blocks).
        self.climb_to_three_with_a_flat_paper_account_in_the_window()
        record = self.ev._record_below("a", 3)
        self.assertEqual({row["book"] for row in record}, {"real"})
        self.assertEqual(len(record), 30)
        for i in range(10):
            self.block("a", 0.005 if i % 2 else 0.003, book="real", start=25.0)
        verdict = self.ev.drift("a", "real")
        self.assertEqual(verdict.decision, "hold")
        self.assertAlmostEqual(verdict.numbers["reference_mean"], 0.004)
        self.assertAlmostEqual(verdict.numbers["reference_sd"], stats.mean_bounds([0.003, 0.005] * 15, 0.5)["sd"])

    def test_a_flat_account_elsewhere_does_not_blunt_the_drift_alarm(self):
        # Regression: the consequence of the dilution above. A fall from +0.4% to +0.1% a block is
        # 2.5 sd a step against the real record, and was under the slack against the diluted one.
        self.climb_to_three_with_a_flat_paper_account_in_the_window()
        for _ in range(4):
            self.block("a", 0.001, book="real", start=25.0)
        verdict = self.ev.drift("a", "real")
        self.assertEqual((verdict.decision, verdict.rung), ("demote", 2))
        self.assertTrue(verdict.numbers["alarm"])

    def test_the_record_below_is_the_latest_stay_there_and_empty_when_there_was_none(self):
        self.assertEqual(self.ev._record_below("nobody", 2), [])
        self.ev.seat("a", 2, "straight to real money, for the test")
        self.assertEqual(self.ev._record_below("a", 2), [])
        self.ev.seat("b", 1, "test")
        for _ in range(3):
            self.block("b", 0.01)
        self.ev.promote("b", 2, "test")
        self.ev.demote("b", "drift")
        for _ in range(5):
            self.block("b", 0.002)
        self.ev.promote("b", 2, "test")
        self.assertEqual([row["log_growth"] for row in self.ev._record_below("b", 2)], [0.002] * 5)  # the second stay on paper only

    def test_rung_three_drifts_against_the_real_money_record_that_earned_it(self):
        # Regression: the drift reference was once EVERY earlier block of the agent, all books and all
        # rungs, so rung 3 was measured against the optimistic paper record pooled with the real one
        # (a reference mean of +0.6% here, and a demotion for "decay" that never happened). It is now
        # the agent's latest stay on the rung just below (`_record_below`).
        self.ev.seat("a", 1, "test")
        for i in range(30):
            self.block("a", 0.013 if i % 2 else 0.007)
        self.ev.promote("a", 2, "test")
        for i in range(30):
            self.block("a", 0.003 if i % 2 else 0.001, book="real", start=25.0)
        self.ev.promote("a", 3, "test")
        for i in range(30):
            self.block("a", 0.003 if i % 2 else 0.001, book="real", start=25.0)  # exactly the record that earned rung 3
        verdict = self.ev.drift("a", "real")
        self.assertAlmostEqual(verdict.numbers["reference_mean"], 0.002)
        self.assertEqual(verdict.decision, "hold")


# =================================================================================================
# a real Book writing the rows
# =================================================================================================
class WithARealBook(unittest.TestCase):
    """The hand-written rows above must be what a `Book` really writes: drive one and read it."""

    def setUp(self):
        from league.tests.fakes import Clock, FakeBroker

        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.db", clock=self.clock)
        self.ev = Evaluator(self.ledger, clock=self.clock)
        self.FakeBroker = FakeBroker
        self.n = 0

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def book(self, venue, family, cash="100000"):
        from league.book import Book, Limits
        from league.fees import Fees

        self.broker = self.FakeBroker(venue, cash=cash, family=family)
        book = Book(venue, self.broker, self.ledger, fees=Fees(family), real_money=False, clock=self.clock)
        book.limits["a"] = Limits(Decimal("100"), Decimal("75"))
        book.stake("a", "200")
        self.ev.seat("a", 1, "test")
        return book

    def order(self, book, instrument, side, quantity):
        from league.book import Intent
        from league.tests.fakes import iso

        self.n += 1
        (outcome,) = book.submit([Intent.new(agent="a", instrument=instrument, side=side, quantity=Decimal(quantity), reason="test",
                                             created_at=iso(self.clock), nonce=str(self.n))])
        self.assertEqual(outcome.status, "filled")

    def hour(self):
        from league.tests.fakes import iso

        self.clock.advance(3600)
        self.broker.clock_iso = iso(self.clock)

    def test_an_equity_round_trip_with_a_top_up(self):
        from ltcm.broker import Instrument

        spy = Instrument("equity", "SPY", "alpaca-paper")
        book = self.book("alpaca-paper", "alpaca")
        self.broker.set_quote(spy, "100.00", "100.10")
        self.order(book, spy, "buy", "0.5")  # pays the ask: $50.05 for something worth $50.00 at the bid
        equity = [book.mark()["a"]]
        self.hour()
        self.broker.set_quote(spy, "101.00", "101.10")
        self.order(book, spy, "sell", "0.5")
        equity.append(book.mark()["a"])
        self.hour()
        book.stake("a", "50")  # the House lends more: not growth
        equity.append(book.mark()["a"])
        self.hour()
        equity.append(book.mark()["a"])
        self.assertEqual([str(e) for e in equity], ["199.95000000", "200.45000000", "250.45000000", "250.45000000"])
        self.assertEqual(self.ev.observe("a", "alpaca-paper", "hour"), 3)
        first, second, third = self.ev.blocks("a", book="alpaca-paper")
        self.assertEqual((first["start_equity"], first["end_equity"], first["active"]), (200.0, 199.95, True))
        self.assertAlmostEqual(first["log_growth"], math.log(199.95 / 200), places=12)
        self.assertAlmostEqual(second["log_growth"], math.log(200.45 / 199.95), places=12)
        self.assertTrue(second["active"])  # flat at the mark, but it sold inside the hour
        self.assertEqual((third["flow"], third["active"]), (50.0, False))
        self.assertAlmostEqual(third["log_growth"], 0.0, places=12)
        returns, risk = self.ev.trade_returns("a", "alpaca-paper")
        self.assertEqual(len(returns), 1)
        self.assertAlmostEqual(returns[0], 0.45 / 250)  # against everything staked, top-up included
        self.assertAlmostEqual(risk, 50.05 / 250)
        self.assertEqual(self.ev.judge("a", "alpaca-paper").decision, "hold")

    def test_a_kalshi_favourite_held_to_settlement(self):
        from ltcm.broker import Instrument

        ticker = "KXBTCD-26SEP2017-T80999"
        yes = Instrument("event", ticker, "kalshi-shadow", market_id=ticker, right="yes")
        book = self.book("kalshi-shadow", "kalshi", cash="1000")
        self.broker.set_quote(yes, "0.94", "0.95")
        self.order(book, yes, "buy", "10")
        book.mark()
        self.hour()
        self.assertEqual(book.settle(ticker, "yes"), 1)
        book.mark()
        self.hour()
        book.mark()
        self.assertEqual(self.ev.observe("a", "kalshi-shadow", "hour"), 2)
        first, second = self.ev.blocks("a")
        self.assertTrue(first["active"])  # holding ten contracts at the mark
        self.assertTrue(second["active"])  # nothing held at the mark, but the settlement fell in the hour
        self.assertGreater(second["log_growth"], 0)
        returns, risk = self.ev.trade_returns("a", "kalshi-shadow")
        self.assertEqual(len(returns), 1)
        self.assertGreater(returns[0], 0)
        self.assertAlmostEqual(returns[0], float(book.account("a").realized) / 200)
        self.assertAlmostEqual(risk, (9.5 + float(book.account("a").fees)) / 200, places=6)

    def test_a_rebuilt_book_and_a_second_observation_change_nothing(self):
        from ltcm.broker import Instrument

        spy = Instrument("equity", "SPY", "alpaca-paper")
        book = self.book("alpaca-paper", "alpaca")
        self.broker.set_quote(spy, "100.00", "100.10")
        for _ in range(4):
            self.order(book, spy, "buy", "0.1")
            book.mark()
            self.hour()
        self.ev.observe("a", "alpaca-paper", "hour")
        rows = [(e.seq, e.payload) for e in self.ledger.iter(kinds="eval.block")]
        Evaluator(self.ledger).observe("a", "alpaca-paper", "hour")
        self.assertEqual(rows, [(e.seq, e.payload) for e in self.ledger.iter(kinds="eval.block")])
        self.assertEqual(self.ledger.verify(), self.ledger.count())


# =================================================================================================
# The paper screen (the constitution as it stands), and the family's pooled record
# =================================================================================================
class Screen(EvalCase):
    """Paper to micro-real is a screen, not a bound: what it lets through is capped in dollars."""

    def setUp(self):
        super().setUp()
        self.ev = Evaluator(self.ledger, constitution=FAST_LANE)
        self.assertEqual(FAST_LANE["ladder"]["paper"],
                         {"gate": "screen", "min_active_blocks": 6, "min_active_blocks_day": 2, "max_drawdown": 0.15})

    def run_blocks(self, growth, *, trades=12, judge_at=None):
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        self.mixed_trades("a", n=trades)
        verdict = None
        for i, g in enumerate(growth, start=1):
            self.block("a", g)
            if judge_at is None or i in judge_at:
                verdict = self.ev.judge("a", "paper")
        return verdict

    def test_a_modest_record_no_bound_would_pass_is_eligible_at_fifteen_active_blocks(self):
        growth = [0.004 if i % 2 == 0 else -0.003 for i in range(15)]  # t is about 0.5: nowhere near any bound
        self.assertLess(stats.mean_bounds(growth, ALPHA)["lcb"], 0)
        verdict = self.run_blocks(growth)
        self.assertEqual(verdict.decision, "eligible")
        self.assertIn("cleared the screen", verdict.reason)
        self.assertEqual((verdict.numbers["active_blocks"], verdict.numbers["trades"]), (15, 12))

    def test_the_screen_counts_independent_closed_trades(self):
        """D4 (Sept 24, 2026): the closed trades that gate a promotion are INDEPENDENT ones
        (`independent_closed`: one an event on the event books), while the statistics still read every
        trade. Review of #224: the gate reading `len(returns)` again passed every other test."""
        growth = [0.004 if i % 2 == 0 else -0.003 for i in range(15)]
        with patch.object(Evaluator, "independent_closed", return_value=4) as independent:
            verdict = self.run_blocks(growth)
        self.assertEqual(verdict.decision, "hold")
        self.assertEqual(verdict.reason, "4 closed trades; 5 needed before any promotion")
        self.assertEqual(verdict.numbers["trades"], 12)  # the statistics saw every trade
        self.assertTrue(independent.called)

    def test_the_screen_spends_no_alpha(self):
        verdict = self.run_blocks([0.004 if i % 2 == 0 else -0.003 for i in range(15)])
        self.assertEqual((verdict.numbers["tested_promotion"], verdict.numbers["alpha_spent"]), (False, None))
        self.assertEqual((verdict.numbers["tested_death"], verdict.numbers["alpha_death"]), (False, None))

    def test_no_look_before_fifteen_active_blocks(self):
        verdict = self.run_blocks([0.004] * 5)
        self.assertEqual(verdict.decision, "hold")
        self.assertIn("next look is at 6", verdict.reason)
        self.assertEqual(self.looks("a"), [])

    def test_growth_at_or_below_zero_does_not_clear_it(self):
        growth = [0.004 if i % 2 == 0 else -0.0047 for i in range(15)]  # eight small wins, seven slightly larger losses
        self.assertLess(sum(growth), 0)
        verdict = self.run_blocks(growth, judge_at=(15,))
        self.assertEqual(verdict.decision, "hold")
        self.assertIn("growth is not above zero", verdict.reason)

    def test_a_drawdown_of_fifteen_percent_does_not_clear_it_though_growth_is_positive(self):
        growth = [0.10, 0.10, -0.17] + [0.002] * 12  # up 20%, then down 16% from the peak, still up overall
        verdict = self.run_blocks(growth, judge_at=(15,))
        self.assertGreater(sum(growth), 0)
        self.assertEqual(verdict.decision, "hold")
        self.assertIn("drawdown", verdict.reason)

    def test_fewer_than_ten_closed_trades_holds(self):
        verdict = self.run_blocks([0.004] * 15, trades=4)
        self.assertEqual(verdict.decision, "hold")
        self.assertIn("4 closed trades", verdict.reason)

    def test_paper_still_kills(self):
        verdict = self.run_blocks([-0.004 if i % 3 else 0.001 for i in range(20)])
        self.assertEqual((verdict.decision, verdict.reason), ("die", "the upper bound on its growth is below zero"))
        self.assertEqual(self.looks("a")[-1]["alpha_death"], stats.spend(ALPHA / 2, 1))  # block and episode routes share death alpha; the look at 15 could not kill, so spent none

    def test_a_thirty_percent_drawdown_kills_on_paper(self):
        verdict = self.run_blocks([-0.2, -0.2])
        self.assertEqual(verdict.decision, "die")

    def test_ten_percent_down_on_paper_dies_after_ten_blocks(self):
        """Owner revision, Sept 21, 2026: a clear paper loser gives up the seat."""
        verdict = self.run_blocks([-0.0112] * 9)
        self.assertNotEqual(verdict.decision, "die")  # nine blocks: not yet judged, however bad
        verdict = self.run_blocks([-0.0112] * 10)
        self.assertEqual(verdict.decision, "die")
        self.assertIn("on paper after 10 active blocks", verdict.reason)

    def test_unprofitable_after_thirty_paper_blocks_dies(self):
        growth = [0.004 if i % 2 == 0 else -0.0042 for i in range(30)]  # a slow bleed, never 10% down
        self.assertLess(sum(growth), 0)
        verdict = self.run_blocks(growth)
        self.assertEqual(verdict.decision, "die")
        self.assertIn("not profitable on paper after 30", verdict.reason)

    def test_a_small_winner_lives_on_paper(self):
        verdict = self.run_blocks([0.004 if i % 2 == 0 else -0.0039 for i in range(30)], trades=9)
        self.assertNotEqual(verdict.decision, "die")

    def test_a_daily_strategy_clears_the_screen_on_five_blocks_not_fifteen(self):
        # A block is a calendar day for a daily strategy: fifteen of them is longer than the whole
        # expedition, so no daily agent could ever reach real money inside one.
        growth = [0.004, -0.003]  # the fast lane (Sept 21, 2026): two daily blocks, six hourly
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        self.mixed_trades("a", n=12)
        for g in growth:
            self.block("a", g)
            verdict = self.ev.judge("a", "paper", horizon="day")
        self.assertEqual(verdict.decision, "eligible")
        self.assertIn("2 active day blocks", verdict.reason)
        self.assertEqual(self.ev._gate_blocks(1, "day"), 2)
        self.assertEqual(self.ev._gate_blocks(1, "hour"), 6)

    def test_an_hourly_strategy_is_not_let_through_on_five(self):
        verdict = self.run_blocks([0.004 if i % 2 == 0 else -0.003 for i in range(5)])
        self.assertEqual(verdict.decision, "hold")
        self.assertIn("next look is at 6", verdict.reason)

    def test_the_conventional_micro_route_requires_five_blocks_of_either_kind(self):
        self.assertEqual((self.ev._gate_blocks(2, "day"), self.ev._gate_blocks(2, "hour")), (5, 5))

    def test_the_micro_rung_is_still_the_bound(self):
        self.ev.seat("a", 2, "test")
        self.stake("a", 25, at(), book="real")
        self.trades("a", [0.2, -0.1] * 6, book="real", cost=5.0)
        modest = [0.004 if i % 2 == 0 else -0.003 for i in range(30)]
        for i, g in enumerate(modest, start=1):
            self.block("a", g, book="real", start=25.0)
            if i in (20, 25, 30):
                verdict = self.ev.judge("a", "real")
        self.assertEqual((verdict.decision, verdict.reason), ("hold", "the evidence does not decide yet"))
        self.assertEqual((verdict.numbers["tested_promotion"], verdict.numbers["alpha_spent"]), (True, stats.spend(ALPHA / 2, 3)))

    def test_a_look_row_from_before_the_tests_were_told_apart_counts_against_both(self):
        self.ev.seat("a", 2, "test")
        self.ledger.append("eval.verdict", {"decision": "look", "rung": 2, "active_blocks": 20, "look": 1, "alpha_spent": stats.spend(ALPHA, 1)}, agent="a")
        self.stake("a", 25, at(), book="real")
        self.trades("a", [0.2, -0.1] * 6, book="real", cost=5.0)
        for i in range(30):
            self.block("a", 0.004 if i % 2 == 0 else -0.003, book="real", start=25.0)
        numbers = self.ev.judge("a", "real").numbers
        self.assertEqual((numbers["alpha_spent"], numbers["alpha_death"]), (stats.spend(ALPHA / 2, 2), stats.spend(ALPHA / 2, 2)))


class Sept22Values(EvalCase):
    """The owner's Sept 22, 2026 dynamism revision, against the constitution as it stood before the
    swing-and-bunt revision: two active days or four active hours, three closed trades, growth above
    zero and the drawdown screen."""

    def setUp(self):
        super().setUp()
        self.ev = Evaluator(self.ledger, constitution=PRE_SWING)

    run_blocks = Screen.run_blocks

    def test_a_daily_strategy_is_screened_after_two_active_days_and_three_closed_trades(self):
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        self.mixed_trades("a", n=3)
        for g in (0.004, -0.001):
            self.block("a", g)
            verdict = self.ev.judge("a", "paper", horizon="day")
        self.assertEqual(verdict.decision, "eligible", verdict.reason)
        self.assertEqual((self.ev._gate_blocks(1, "day"), self.ev._gate_blocks(1, "hour")), (2, 4))

    def test_an_hourly_strategy_needs_four_active_hours(self):
        self.assertEqual(self.run_blocks([0.004, -0.003, 0.004]).decision, "hold")
        self.setUp()
        self.assertEqual(self.run_blocks([0.004, -0.003, 0.004, 0.001]).decision, "eligible")

    def test_losing_on_the_day_still_holds_and_two_closed_trades_are_not_enough(self):
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        self.mixed_trades("a", n=3)
        for g in (-0.004, 0.001):
            self.block("a", g)
        self.assertEqual(self.ev.judge("a", "paper", horizon="day").decision, "hold")
        self.setUp()
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        self.mixed_trades("a", n=2)
        for g in (0.004, -0.001):
            self.block("a", g)
        self.assertEqual(self.ev.judge("a", "paper", horizon="day").decision, "hold")


class Sept23Values(EvalCase):
    """The owner's first Sept 23, 2026 revision, against the constitution as it stood before the
    swing-and-bunt revision of the same night: an event-contract agent with three settled trades is
    screened after one finished day; the screen counts the block in progress; and the screen's own
    "next look" is the look it really takes."""

    def setUp(self):
        super().setUp()
        self.ev = Evaluator(self.ledger, constitution=PRE_SWING)

    def seated(self, book):
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at(), book=book)
        self.buy("a", 50.0, at(), book)

    def test_three_settled_trades_on_an_event_book_screen_a_daily_agent_after_one_day(self):
        self.seated("kalshi-shadow")
        for pnl in (2.0, -0.5, 1.0):
            self.settle("a", pnl, at(), book="kalshi-shadow")
        self.block("a", 0.006, book="kalshi-shadow")
        verdict = self.ev.judge("a", "kalshi-shadow", horizon="day")
        self.assertEqual(verdict.decision, "eligible", verdict.reason)
        self.assertEqual(verdict.numbers["settled_trades"], 3)

    def test_without_three_settlements_the_daily_screen_still_waits_for_two_days_and_says_so(self):
        self.seated("kalshi-shadow")
        self.settle("a", 2.0, at(), book="kalshi-shadow")
        self.sell("a", 1.0, at(), book="kalshi-shadow")
        self.sell("a", 1.0, at(), book="kalshi-shadow")
        self.block("a", 0.006, book="kalshi-shadow")
        verdict = self.ev.judge("a", "kalshi-shadow", horizon="day")
        self.assertEqual(verdict.decision, "hold")
        self.assertIn("the next look is at 2 (or 1 once 3 trades have settled on this rung; 1 so far)", verdict.reason)

    def test_the_settled_lane_is_for_event_contracts_and_daily_agents_only(self):
        self.seated("alpaca-paper")
        self.mixed_trades("a", n=4, book="alpaca-paper")
        self.block("a", 0.006, book="alpaca-paper")
        self.assertEqual(self.ev.judge("a", "alpaca-paper", horizon="day").decision, "hold")
        self.assertIsNone(self.ev._settled_lane("a", "kalshi-shadow", 1, "hour", 0))
        self.assertIsNone(self.ev._settled_lane("a", "kalshi-shadow", 2, "day", 0))

    def test_a_loss_in_the_block_in_progress_holds_a_screen_the_finished_days_would_pass(self):
        """Regression: hawkins, Sept 22, 2026 -- finished days +1.4%, that morning's settlements -$15.50."""
        self.seated("kalshi-shadow")
        for pnl in (2.0, -0.5, 1.0):
            self.settle("a", pnl, at(), book="kalshi-shadow")
        self.block("a", 0.004, book="kalshi-shadow")
        self.block("a", 0.003, book="kalshi-shadow")
        end = 200.0 * math.exp(0.007)
        self.ledger.append("book.mark", {"book": "kalshi-shadow", "equity": f"{end - 15.5:.2f}", "cash": "0", "staked": "200",
                                         "holdings": 1, "real_money": False}, agent="a")
        verdict = self.ev.judge("a", "kalshi-shadow", horizon="day")
        self.assertEqual(verdict.decision, "hold")
        self.assertIn("once the block in progress is counted", verdict.reason)
        self.assertLess(verdict.numbers["unfinished_log_growth"], -0.07)

    def test_a_gain_in_the_block_in_progress_does_not_hold_it(self):
        self.seated("kalshi-shadow")
        for pnl in (2.0, -0.5, 1.0):
            self.settle("a", pnl, at(), book="kalshi-shadow")
        self.block("a", 0.004, book="kalshi-shadow")
        self.ledger.append("book.mark", {"book": "kalshi-shadow", "equity": "205.00", "cash": "0", "staked": "200",
                                         "holdings": 1, "real_money": False}, agent="a")
        self.assertEqual(self.ev.judge("a", "kalshi-shadow", horizon="day").decision, "eligible")

    def test_the_screen_says_the_look_it_really_takes(self):
        self.seated("alpaca-paper")
        self.block("a", 0.004, book="alpaca-paper")
        self.assertIn("the next look is at 2", self.ev.judge("a", "alpaca-paper", horizon="day").reason)
        self.assertIn("the next look is at 4", self.ev.judge("a", "alpaca-paper", horizon="hour").reason)


class SwingAndBunt(EvalCase):
    """The owner's swing-and-bunt revision (Sept 23, 2026 ~03:10 UTC), against the REAL
    constitution: bunts are cheap and fast; swings are earned, and death keeps its own budget."""

    def setUp(self):
        super().setUp()
        self.ev = Evaluator(self.ledger)  # the real constitution

    run_blocks = Screen.run_blocks

    def test_the_screen_is_three_hours_or_one_day(self):
        self.assertEqual((self.ev._gate_blocks(1, "day"), self.ev._gate_blocks(1, "hour")), (1, 3))
        self.assertEqual(self.run_blocks([0.004, -0.003]).decision, "hold")
        self.setUp()
        self.assertEqual(self.run_blocks([0.004, -0.003, 0.004]).decision, "eligible")

    def test_one_finished_day_screens_a_daily_agent(self):
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        self.mixed_trades("a", n=3)
        self.block("a", 0.004)
        verdict = self.ev.judge("a", "paper", horizon="day")
        self.assertEqual(verdict.decision, "eligible", verdict.reason)

    def test_a_volatile_winner_clears_a_screen_the_old_limit_held(self):
        growth = [0.10, 0.10, -0.22] + [0.03] * 3  # up 22%, then down 20% from the peak, up overall
        verdict = self.run_blocks(growth, judge_at=(6,))
        self.assertGreater(sum(growth), 0)
        self.assertGreater(verdict.numbers["recent_drawdown"], 0.15)
        self.assertEqual(verdict.decision, "eligible", verdict.reason)

    def test_promotion_spends_its_own_budget_and_death_keeps_alpha(self):
        ladder = self.ev.ladder
        self.assertGreater(ladder["promotion_alpha"], ladder["alpha"])
        self.ev.seat("a", 2, "test")
        self.stake("a", 60, at(), book="real")
        self.mixed_trades("a", n=12, book="real")
        for i in range(ladder["death"]["min_active_blocks"]):
            self.block("a", 0.004 if i % 2 == 0 else -0.003, book="real", start=60.0)
        self.ev.judge("a", "real")
        look = [e.payload for e in self.ledger.iter(kinds="eval.verdict", agent="a") if e.payload.get("decision") == "look"][-1]
        share = ladder["completed_exposures"]["promotion_alpha_share"]
        self.assertTrue(look["tested_promotion"] and look["tested_death"])
        self.assertAlmostEqual(look["alpha_spent"], stats.spend(ladder["promotion_alpha"] * (1 - share), 1))
        self.assertAlmostEqual(look["alpha_death"], stats.spend(ladder["alpha"] * (1 - share), 1))

    def test_the_first_bound_on_real_money_is_read_after_three_active_blocks(self):
        self.ev.seat("a", 2, "test")
        self.stake("a", 60, at(), book="real")
        self.mixed_trades("a", n=12, book="real")
        for g in (0.004, 0.003):
            self.block("a", g, book="real", start=60.0)
        self.assertIn("the next look is at 3", self.ev.judge("a", "real").reason)
        self.block("a", 0.004, book="real", start=60.0)
        self.ev.judge("a", "real")
        looks = [e.payload for e in self.ledger.iter(kinds="eval.verdict", agent="a") if e.payload.get("decision") == "look"]
        self.assertEqual(len(looks), 1)
        self.assertTrue(looks[0]["tested_promotion"])

    def test_the_oos_floor_admits_near_breakeven_trading_but_not_a_program_that_sat_out(self):
        base = {"ok": True, "trades": 12, "blocks": [{"log_growth": 0.001 * (i % 3 - 1)} for i in range(20)]}

        def oos_reasons(oos):
            reasons = self.ev._replay_reasons("fam", {**base, "out_of_sample": oos}, None)[1]
            return [r for r in reasons if "out-of-sample" in r or "out of sample" in r]

        self.assertEqual(oos_reasons({"blocks": 8, "mean_log_growth": -0.0003, "active_blocks": 5}), [])
        self.assertEqual(oos_reasons({"blocks": 8, "mean_log_growth": 0.0, "active_blocks": 0}),
                         ["it did not trade out of sample: no out-of-sample block was active"])
        self.assertEqual(oos_reasons({"blocks": 8, "mean_log_growth": 0.0}),
                         ["it did not trade out of sample: no out-of-sample block was active"])
        self.assertEqual(oos_reasons({"blocks": 8, "mean_log_growth": -0.0006, "active_blocks": 5}),
                         ["out-of-sample growth is not above -0.050% a block"])
        self.assertEqual(len(oos_reasons({"blocks": 7, "mean_log_growth": 0.01, "active_blocks": 7})), 1)

    def test_a_swing_inside_the_death_limit_lives(self):
        self.assertEqual(self.ev.ladder["death"]["max_drawdown"], 0.40)
        self.ev.seat("a", 2, "test")
        self.stake("a", 60, at(), book="real")
        for g in (0.2, math.log(0.7)):  # up 22%, then down 30% from the peak: ordinary luck at full Kelly
            self.block("a", g, book="real", start=60.0)
        self.assertNotEqual(self.ev.judge("a", "real").decision, "die")
        self.block("a", math.log(0.85), book="real", start=60.0)  # now down 40.5% from the peak
        self.assertEqual(self.ev.judge("a", "real").decision, "die")


class Family(EvalCase):
    """A small edge is proved across a family before it is proved in any one member. Written against
    the family rule before the swing-and-bunt revision (alpha 0.05, members of 10 active blocks)."""

    def setUp(self):
        super().setUp()
        self.ev = Evaluator(self.ledger, constitution=PRE_SWING)
        self.hours = 0

    def member(self, name, growth, *, pnls=(0.2, -0.1) * 6):
        self.ev.seat(name, 2, "test")
        self.stake(name, 25, at(), book="real")
        self.trades(name, list(pnls), book="real", cost=5.0)
        for i, g in enumerate(growth):
            self.ledger.append(
                "eval.block",
                {"book": "real", "key": f"2026-09-20T{i:03d}", "horizon": "hour", "start_equity": 25.0, "end_equity": 25.0 * math.exp(g),
                 "flow": 0.0, "log_growth": g, "active": True},
                agent=name,
            )

    #: Three members with the same small edge and independent noise: none decisive alone.
    NOISE = {
        "a": [0.012, -0.010, 0.011, -0.006, 0.002, 0.009, -0.011, 0.010, -0.004, 0.003],
        "b": [-0.009, 0.012, -0.007, 0.010, 0.004, -0.010, 0.013, -0.006, 0.008, 0.001],
        "c": [0.003, 0.004, 0.002, 0.001, 0.002, 0.006, 0.003, 0.002, 0.001, 0.004],
    }

    def series(self, name):
        return [self.NOISE[name][i % 10] for i in range(30)]

    def test_one_agent_alone_is_held_and_the_family_carries_it(self):
        for name in "abc":
            self.member(name, self.series(name))
        alone = self.ev.judge("a", "real")
        self.assertEqual((alone.decision, alone.reason), ("hold", "the evidence does not decide yet"))
        self.assertGreater(alone.numbers["mean"], 0)
        self.assertLess(alone.numbers["lcb"], 0)
        self.ledger.append("eval.verdict", {"decision": "promote", "from_rung": 1, "to_rung": 2, "reason": "again"}, agent="b")  # b looks afresh
        for name in "b":
            self.member(name, self.series(name))
        pooled = self.ev.judge("b", "real", peers=["a", "c"], family="favorites")
        self.assertEqual(pooled.decision, "eligible")
        self.assertEqual((pooled.numbers["via"], pooled.numbers["family_members"]), ("family", 3))
        self.assertGreater(pooled.numbers["family_lcb"], 0)
        looks = [e.payload for e in self.rows("eval.verdict", "house") if e.payload["decision"] == "family-look"]
        self.assertEqual([(row["family"], row["look"], row["alpha_spent"]) for row in looks], [("favorites", 1, stats.spend(ALPHA, 1))])

    def test_the_pooled_series_is_one_observation_a_block_not_one_a_member(self):
        for name in "abc":
            self.member(name, self.series(name))
        series, trades, risk, counted = self.ev.family_record(["a", "b", "c"], "real")
        self.assertEqual((len(series), counted, len(trades)), (30, 3, 36))
        self.assertAlmostEqual(series[0], (0.012 - 0.009 + 0.003) / 3, places=12)

    def test_a_member_with_a_losing_record_of_its_own_is_never_carried(self):
        self.member("a", self.series("a"))
        self.member("c", self.series("c"))
        self.member("loser", [-x for x in self.series("a")])
        verdict = self.ev.judge("loser", "real", peers=["a", "c"], family="favorites")
        self.assertNotEqual(verdict.decision, "eligible")
        self.assertEqual([e for e in self.rows("eval.verdict", "house")], [])  # the family was not even looked at

    def test_one_member_is_not_a_family(self):
        self.member("a", self.series("a"))
        self.member("thin", self.series("c")[:5])  # under ten active blocks: it does not count
        verdict = self.ev.judge("a", "real", peers=["thin"], family="favorites")
        self.assertEqual(verdict.decision, "hold")

    def test_short_lived_members_contribute_every_outcome_before_they_qualify(self):
        # Regression: excluding members below the ten-block threshold erased the whole loss of
        # an agent killed early. The threshold counts mature members; it does not censor returns.
        for name in "abc":
            self.member(name, self.series(name))
        self.member("early-loss", [-1.0], pnls=(-15.0,))
        self.member("new-winner", [0.006], pnls=(0.15,))
        self.ledger.append("agent.died", {"cause": "evidence"}, agent="early-loss")
        series, trades, _, counted = self.ev.family_record(["a", "b", "c", "early-loss", "new-winner"], "real")
        self.assertEqual(counted, 3)
        self.assertEqual(len(trades), 38)
        self.assertAlmostEqual(series[0], (0.012 - 0.009 + 0.003 - 1.0 + 0.006) / 5, places=12)
        self.assertAlmostEqual(series[1], (0.004 + 0.012 - 0.010) / 3, places=12)
        self.assertLess(sum(series), 0)
        self.assertNotEqual(self.ev.judge("a", "real", peers=["b", "c", "early-loss", "new-winner"], family="favorites").decision,
                            "eligible")

    def test_sweeping_a_dead_members_account_cannot_erase_its_trades(self):
        # Regression: death does not write a rung change. Its last stay had no upper bound, so
        # trade_returns used the post-sweep net stake and lost a profitable dead member's trades.
        self.member("a", self.series("a"))
        before = self.ev.family_record(["a"], "real")
        self.stake("a", -25.6, at(), book="real")
        self.ledger.append("agent.died", {"cause": "credits"}, agent="a")
        after = self.ev.family_record(["a"], "real")
        self.assertEqual(after, before)
        self.assertEqual(len(after[1]), 12)

    def test_sweeping_a_losing_members_account_cannot_amplify_its_trade_returns(self):
        # A losing account retains a positive net stake after sweeping; using that residue used
        # to turn a $2 loss on $25 into a 100% trade loss and a 250% entry risk.
        self.member("a", self.series("a"), pnls=(-2.0,))
        before = self.ev.family_record(["a"], "real")
        self.stake("a", -23.0, at(), book="real")
        self.ledger.append("agent.died", {"cause": "credits"}, agent="a")
        after = self.ev.family_record(["a"], "real")
        self.assertEqual(after, before)
        self.assertEqual(after[1], [-2.0 / 25.0])
        self.assertEqual(after[2], 5.0 / 25.0)

    def test_paper_blocks_are_not_pooled(self):
        self.member("a", self.series("a"))
        self.ev.seat("paper-only", 1, "test")
        for i in range(30):
            self.ledger.append("eval.block", {"book": "real", "key": f"2026-09-20T{i:03d}", "horizon": "hour", "log_growth": 0.05, "active": True}, agent="paper-only")
        series, _, _, counted = self.ev.family_record(["a", "paper-only"], "real")
        self.assertEqual(counted, 1)
        self.assertAlmostEqual(series[0], 0.012, places=12)

    def test_a_lopsided_family_must_clear_the_loss_gate_too(self):
        for name in "abc":
            self.member(name, self.series(name), pnls=(0.05,) * 12)  # every trade a small win: one unseen loss is assumed
        verdict = self.ev.judge("a", "real", peers=["b", "c"], family="favorites")
        self.assertEqual(verdict.decision, "hold")
        look = [e.payload for e in self.rows("eval.verdict", "house")][-1]
        self.assertTrue(look["lopsided"])
        self.assertLess(look["loss_gate_lcb"], 0)

    def test_the_family_is_looked_at_once_per_five_new_blocks(self):
        for name in "abc":
            self.member(name, self.series(name), pnls=(0.05,) * 12)
        for _ in range(3):
            self.ev.judge("a", "real", peers=["b", "c"], family="favorites")
            self.ledger.append("eval.verdict", {"decision": "promote", "from_rung": 1, "to_rung": 2, "reason": "again"}, agent="a")
            self.member("a", self.series("a"), pnls=(0.05,) * 12)
        self.assertEqual(len([e for e in self.rows("eval.verdict", "house")]), 1)

    def test_a_finished_stay_is_measured_against_what_was_lent_not_what_is_left(self):
        self.ev.seat("a", 2, "test")
        self.stake("a", 25, at(), book="real")
        self.trades("a", [1.0, -0.5], book="real", cost=5.0)
        end = self.ledger.append("eval.verdict", {"decision": "demote", "from_rung": 2, "to_rung": 1, "reason": "test"}, agent="a").seq
        self.stake("a", -24, at(), book="real")  # the House swept the account
        self.trades("a", [9.0], book="real")  # and a later trade is not part of the stay
        returns, _ = self.ev.trade_returns("a", "real", until_seq=end)
        self.assertEqual(returns, [1.0 / 25, -0.5 / 25])


if __name__ == "__main__":
    unittest.main()


class TheScreensDrawdownIsRecent(unittest.TestCase):
    """A lifetime high-water mark never falls. One bad afternoon early in a stay would have barred
    an agent from real money for the rest of it, whatever it did afterwards -- and an agent that
    drew down between the screen's 15% and death's 30% could then be neither promoted nor killed,
    for ever. Found by the stall audit, Sept 20, 2026."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite")
        self.evaluator = Evaluator(self.ledger)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def blocks(self, agent, growths, *, book="kalshi-shadow"):
        for n, g in enumerate(growths):
            self.ledger.append("eval.block", {"agent": agent, "log_growth": g, "active": True, "book": book,
                                              "block": f"b{n}", "horizon": "hour"}, agent=agent)

    def test_a_bad_afternoon_early_does_not_bar_an_agent_for_ever(self):
        self.evaluator.seat("a1", 1, "test")
        window = int(self.evaluator.ladder["screen_drawdown_blocks"])
        self.blocks("a1", [-0.18])                      # a 16.5% hole on the first block
        self.blocks("a1", [0.02] * (window + 6))        # then a long, steady climb out of it
        for n in range(12):                             # and the closed trades the screen wants
            self.ledger.append("book.fill", {"book": "kalshi-shadow", "realized": "0.40", "quantity": "1", "price": "0.9",
                                             "instrument": {"market_id": f"M{n}", "asset_class": "event"}}, agent="a1")
        self.ledger.append("book.stake", {"book": "kalshi-shadow", "usd": "200"}, agent="a1")
        verdict = self.evaluator.judge("a1", "kalshi-shadow", horizon="hour")
        self.assertGreaterEqual(verdict.numbers["drawdown"], 0.15)      # its life still records the hole
        self.assertLess(verdict.numbers["recent_drawdown"], 0.15)       # its recent record does not
        self.assertEqual(verdict.decision, "eligible", verdict.reason)
        self.assertIn("over its last", verdict.reason)

    def test_death_still_reads_the_whole_stay(self):
        limit = float(self.evaluator.ladder["death"]["max_drawdown"])  # 40% since swing and bunt (30% before)
        self.evaluator.seat("a2", 1, "test")
        self.blocks("a2", [math.log(1 - limit - 0.03)] + [0.01] * 60)
        verdict = self.evaluator.judge("a2", "kalshi-shadow", horizon="hour")
        self.assertEqual(verdict.decision, "die")
        self.assertIn(f"past the {limit:.0%} limit", verdict.reason)


class AFreeCheckIsNotRationed(unittest.TestCase):
    """hilibrand-2 cleared every screen condition but cumulative growth at its first look on Sept
    20, 2026 -- fifteen active blocks, sixteen closed trades, a 4.2% drawdown against a 15% bar --
    and was 0.35% of one block's growth short. Rationed one look in five, it would not have been
    looked at again for five hours, for a check that counts blocks and reads two numbers."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite")
        self.evaluator = Evaluator(self.ledger, constitution=FAST_LANE)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def block(self, agent, growth, n):
        self.ledger.append("eval.block", {"agent": agent, "log_growth": growth, "active": True,
                                          "book": "kalshi-shadow", "block": f"b{n}"}, agent=agent)

    def test_a_screen_is_looked_at_every_block_and_spends_nothing(self):
        self.evaluator.seat("a1", 1, "test")
        self.ledger.append("book.stake", {"book": "kalshi-shadow", "usd": "200"}, agent="a1")
        for n in range(12):
            self.ledger.append("book.fill", {"book": "kalshi-shadow", "realized": "-0.20", "quantity": "1", "price": "0.9",
                                             "instrument": {"market_id": f"M{n}", "asset_class": "event"}}, agent="a1")
        for n in range(16):
            self.block("a1", -0.0002, n)
            self.evaluator.judge("a1", "kalshi-shadow", horizon="hour")
        looks = [e.payload for e in self.ledger.iter(kinds="eval.verdict", agent="a1") if e.payload.get("decision") == "look"]
        self.assertGreater(len(looks), 1, "a free check must not wait five blocks between looks")
        self.assertTrue(all(row["tested_promotion"] is False for row in looks))  # and none of them spent alpha
        self.assertTrue(all(row["tested_death"] is False for row in looks))

    def test_screen_can_qualify_between_death_looks_without_spending_alpha(self):
        self.evaluator.seat("a1", 1, "test")
        self.ledger.append("book.stake", {"book": "kalshi-shadow", "usd": "200"}, agent="a1")
        for n in range(12):
            self.ledger.append("book.settle", {"book": "kalshi-shadow", "pnl": "0.10",
                "instrument": {"market_id": f"M{n}"}}, agent="a1")
        for n in range(20):
            self.block("a1", 0.001 if n % 2 else -0.0012, n)
        self.assertEqual(self.evaluator.judge("a1", "kalshi-shadow").decision, "hold")
        first = self.ledger.last("eval.verdict", agent="a1").payload
        self.assertTrue(first["tested_death"])
        self.block("a1", 0.003, 20)
        verdict = self.evaluator.judge("a1", "kalshi-shadow")
        self.assertEqual(verdict.decision, "eligible")
        self.assertFalse(verdict.numbers["tested_death"])
        self.assertFalse(verdict.numbers["tested_promotion"])
        self.assertIsNone(verdict.numbers["alpha_death"])
        for n in range(21, 25):
            self.block("a1", 0.0001, n)
            verdict = self.evaluator.judge("a1", "kalshi-shadow")
        self.assertTrue(verdict.numbers["tested_death"])
        self.assertAlmostEqual(verdict.numbers["alpha_death"], first["alpha_death"] / 4)

    def test_statistical_death_still_runs_when_due_on_a_screen_rung(self):
        self.evaluator.seat("a1", 1, "test")
        for n in range(20):
            self.block("a1", -0.001 if n % 2 else -0.0012, n)
        verdict = self.evaluator.judge("a1", "kalshi-shadow")
        self.assertEqual(verdict.decision, "die")
        self.assertTrue(verdict.numbers["tested_death"])
