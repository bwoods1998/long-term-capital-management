"""Adversarial tests of the ladder's evaluator: the code that decides promotion and death.

Every test builds a real `Ledger` in a temp dir and appends the rows a `Book` would write
(`book.stake`, `book.mark`, `book.fill`, `book.settle`), or `eval.block` rows directly when a
statistic has to be exact. Tests marked `expectedFailure` demonstrate bugs; each carries a
`# BUG:` comment with what is wrong and the proposed fix.
"""

from __future__ import annotations

import copy
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from league import stats
from league.constitution import CONSTITUTION
from league.evaluator import Evaluator, block_key
from league.ledger import Ledger

BASE = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
ALPHA = float(CONSTITUTION["ladder"]["alpha"])

WINNER = [1.2, 1.0, -0.4]  # dollars a block on a $200 stake: mean +0.3%, two wins in three
LOSER = [-1.2, -1.0, 0.4]


def at(hours: float = 0, minutes: float = 0, days: float = 0) -> str:
    t = BASE + timedelta(days=days, hours=hours, minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


class EvalCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.db")
        self.ev = Evaluator(self.ledger)
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
             "flow": 0.0, "log_growth": growth, "active": active, "rung": self.ev.rung(agent)},
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

    @unittest.expectedFailure
    def test_re_observation_reports_zero_blocks_added(self):
        # BUG: evaluator.py:187 `added += 1 if entry.seq > last.seq else 0`. The test is meant to
        # tell a new row from an idempotent re-append, but a block row is always written after the
        # last mark of its own block (a block is only finished once a LATER mark exists), so
        # `entry.seq > last.seq` is true for old rows too. `observe` therefore returns the total
        # number of finished blocks on every call, not "how many blocks were added".
        # FIX: take `head = self.ledger.head()[0]` before the loop and count `entry.seq > head`.
        self.stake("a", 200, at(0, 0))
        for hour in range(5):
            self.mark("a", 200 + hour, at(hour, 10))
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 4)
        self.assertEqual(self.ev.observe("a", "paper", "hour"), 0)

    @unittest.expectedFailure
    def test_observe_counts_only_the_new_block_when_one_more_hour_finishes(self):
        # BUG: same defect as above (evaluator.py:187): after one more hour this returns 5, not 1.
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
        mine = [e.payload for e in self.ledger.iter(kinds="eval.block")]
        theirs = [e.payload for e in other.iter(kinds="eval.block")]
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

    def test_a_stake_that_arrives_after_the_first_mark_starts_the_record_one_block_later(self):
        self.mark("a", 0, at(0, 10))  # the book marked an account it had opened but not funded
        self.stake("a", 200, at(0, 20))
        self.mark("a", 200, at(0, 50))
        self.mark("a", 202, at(1, 10))
        self.mark("a", 202, at(2, 10))
        self.ev.observe("a", "paper", "hour")
        blocks = self.ev.blocks("a")
        self.assertEqual([b["key"][-2:] for b in blocks], ["01"])
        self.assertAlmostEqual(blocks[0]["log_growth"], math.log(202 / 200), places=12)

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

    def test_blocks_record_the_rung_they_were_observed_on(self):
        self.stake("a", 200, at(0, 0))
        self.ev.seat("a", 1, "test")
        self.mark("a", 200, at(0, 10))
        self.mark("a", 201, at(1, 10))
        self.ev.observe("a", "paper", "hour")
        self.assertEqual(self.ev.blocks("a")[0]["rung"], 1)

    @unittest.expectedFailure
    def test_observing_the_same_book_after_a_rung_change_does_not_crash(self):
        # BUG (severe): evaluator.py:171-186. `observe` recomputes EVERY finished block on every
        # call and re-appends it under the id `block:{agent}:{book}:{key}` with `"rung":
        # self.rung(agent)` in the payload. Rungs 2 and 3 share the real-money book
        # (house.py `book_of`: rung >= 2 -> REAL_BOOK), so the first `observe` after a 2 -> 3
        # promotion (or a 3 -> 2 demotion) re-appends the old blocks with a different rung, and the
        # ledger raises `LedgerConflict`. `House.judge` calls `observe` first, so from that moment
        # every judge pass of that agent raises: a rung-3 agent can never be looked at, never die
        # on evidence or drawdown, and never be demoted on drift.
        # FIX: skip a block whose id is already on the ledger (`self.ledger.get(id)`) before
        # building the payload, or keep `rung` out of the idempotent payload. Skipping also stops
        # the O(all marks) rewrite on every wake.
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
        self.assertEqual(self.ev.trade_returns("a", "paper"), ([], 0.0))

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
            self.assertEqual(row["alpha_spent"], stats.spend(ALPHA, k))
            growth = [0.006 if i % 2 else -0.001 for i in range(1, row["blocks"] + 1)]
            bounds = stats.mean_bounds(growth, stats.spend(ALPHA, k))
            self.assertAlmostEqual(row["lcb"], bounds["lcb"], places=15)
            self.assertAlmostEqual(row["ucb"], bounds["ucb"], places=15)
        self.assertLess(sum(row["alpha_spent"] for row in looks), ALPHA)

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
        """t is about 2.3 on 30 blocks: past the 5% line (1.70) but not the third look's 0.34% line (2.9)."""
        self.ev.seat("a", 1, "test")
        self.mixed_trades("a")
        growth = [0.01 if i % 2 == 0 else -0.004 for i in range(30)]
        verdict = None
        for i, g in enumerate(growth, start=1):
            self.block("a", g)
            if i in (20, 25, 30):
                verdict = self.ev.judge("a", "paper")
        self.assertGreater(stats.mean_bounds(growth, ALPHA)["lcb"], 0)  # an unspent alpha would promote
        self.assertEqual(verdict.numbers["look"], 3)
        self.assertLess(verdict.numbers["lcb"], 0)
        self.assertEqual(verdict.decision, "hold")

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
        self.assertIsNone(numbers["wilson_lcb"])
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
                                              "log_growth": math.log(trough / 200.0), "active": True, "rung": 1}, agent=agent)
            self.assertEqual(self.ev.judge(agent, "paper").decision, decision, agent)

    def test_the_drawdown_is_measured_from_the_first_blocks_start(self):
        self.ev.seat("a", 1, "test")
        self.ledger.append("eval.block", {"book": "paper", "key": "k1", "start_equity": 200.0, "end_equity": 130.0, "flow": 0.0,
                                          "log_growth": math.log(130 / 200), "active": True, "rung": 1}, agent="a")
        verdict = self.ev.judge("a", "paper")
        self.assertEqual(verdict.decision, "die")
        self.assertAlmostEqual(verdict.numbers["drawdown"], 0.35)

    @unittest.expectedFailure
    def test_taking_part_of_a_stake_back_is_not_a_drawdown(self):
        # BUG: evaluator.py:226-229 builds the drawdown from raw `end_equity`, which includes stake
        # flows, although `log_growth` on the same rows takes them out. `Book.stake` accepts a
        # negative amount ("negative takes it back"), so a House (or owner) that withdraws 40% of a
        # flat agent's stake makes `judge` return `die` for a 40% "drawdown" the agent never had.
        # The mirror is as bad: a deposit hides a real drawdown (200 -> 130 with +100 lent in the
        # same block reads as 200 -> 230).
        # FIX: compute the drawdown on the flow-free wealth index, e.g.
        # `index = [1.0]; index.append(index[-1] * exp(log_growth))` for each row.
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

    @unittest.expectedFailure
    def test_a_deposit_does_not_hide_a_drawdown(self):
        # BUG: the mirror of the test above (evaluator.py:226-229): 200 -> 130 is a 35% loss, but
        # $100 lent in the same block makes end_equity 230 and the breaker sees no drawdown at all.
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
        self.assertLess(fav.numbers["wilson_lcb"], 0)
        self.assertEqual(fav.decision, "hold")
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
        self.assertAlmostEqual(verdict.numbers["wilson_lcb"], expected, places=15)

    def test_fewer_than_ten_closed_trades_holds_and_the_tenth_unlocks(self):
        self.ev.seat("a", 1, "test")
        self.stake("a", 200, at())
        self.trades("a", [2.0, -1.0, 2.0, -1.0, 2.0, -1.0, 2.0, -1.0, 2.0])
        for i in range(1, 31):
            self.block("a", 0.006 if i % 3 else -0.001)
            if i in (20, 25, 30):
                verdict = self.ev.judge("a", "paper")
        self.assertGreater(verdict.numbers["lcb"], 0)
        self.assertEqual(verdict.numbers["trades"], 9)
        self.assertEqual(verdict.decision, "hold")
        self.assertIn("9 closed trades", verdict.reason)
        self.trades("a", [-1.0])
        for _ in range(5):
            self.block("a", 0.006)
        verdict = self.ev.judge("a", "paper")
        self.assertEqual((verdict.numbers["trades"], verdict.decision), (10, "eligible"))

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
        self.assertEqual(verdict.numbers["alpha_spent"], stats.spend(ALPHA, 1))
        self.assertEqual(verdict.numbers["blocks"], 20)
        self.assertEqual(verdict.numbers["trades"], 0)

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
        self.assertEqual(up.decision, "hold")
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
        # Looks start at min(death, promotion) = 4 and come every 2; death waits for 6 active blocks.
        self.assertEqual(decisions, [("hold", 0), ("hold", 0), ("hold", 0), ("hold", 1), ("hold", 1), ("die", 2)])

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
        again = Evaluator(self.ledger)
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
            "blocks": (replay_result([0.012, 0.004, -0.004, 0.008] * 7 + [0.01]), "29 blocks"),
            "oos-blocks": (replay_result(oos_blocks=7), "out-of-sample"),
            "oos-growth": (replay_result(oos_mean=0.0), "out-of-sample"),
            "oos-missing": (replay_result(out_of_sample=None), "out-of-sample"),
            "dsr": (replay_result([0.011, -0.010] * 20), "deflated Sharpe"),
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

    @unittest.expectedFailure
    def test_a_failed_replay_still_counts_as_a_trial_for_the_family(self):
        # BUG (exploitable): evaluator.py:82-88 and :95-98. `family_trials` drops every trial row
        # whose `sharpe` is None, and `record_trial` sets `sharpe = None` for an `ok: False` replay
        # (and for a flat one), then passes `n_trials=len(trials)`. So failed replays are written
        # as `eval.trial` rows but never raise N in the deflated Sharpe: the constitution's "every
        # replay ever run for the family is a trial" does not hold. A strategy can use this:
        # `raise` inside `decide` whenever the run is going badly -> replay.py returns
        # `{"ok": False, "error": "too many errors"}` -> the try is free, and only lucky runs are
        # ever counted.
        # FIX: count N as the number of `eval.trial` rows of the family (plus this one), and pass
        # only the defined Sharpes for the variance:
        # `deflated_sharpe(growth, defined_sharpes, n_trials=rows_for_family + 1)`.
        for i in range(50):
            self.ev.record_trial(f"crasher-{i % 5}", "fam", replay_result(ok=False, error="too many errors"))
        self.assertEqual(self.ledger.count(kinds="eval.trial"), 50)
        verdict = self.ev.record_trial("a", "fam", replay_result(), promote=False)
        self.assertEqual(verdict.numbers["trials"], 51)

    @unittest.expectedFailure
    def test_failed_replays_raise_the_bar(self):
        # BUG: the consequence of the one above. The same replay is judged against a benchmark
        # Sharpe of 0.0 whether it was the family's first try or its fifty-first, so long as the
        # other fifty "failed". With N = 51 and the 1/n variance floor the benchmark would be
        # about 0.36 a block.
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
        for i in range(40):
            self.block("a", 0.006 if i % 2 else 0.0, book="real", start=25.0)
        verdict = self.ev.drift("a", "real")
        self.assertEqual(verdict.decision, "hold")
        self.assertEqual(verdict.numbers["statistic"], verdict.numbers["statistic"])
        self.assertIsNone(verdict.numbers["at"])  # the six bad blocks are outside the 40-block window

    def test_blocks_of_the_other_book_are_not_recent_growth(self):
        self.earn_rung_two()
        for _ in range(6):
            self.block("a", -0.01, book="paper")  # the paper account winding down after the promotion
        self.block("a", 0.003, book="real", start=25.0)
        self.assertEqual(self.ev.drift("a", "real").decision, "hold")

    @unittest.expectedFailure
    def test_rung_three_drifts_against_the_real_money_record_that_earned_it(self):
        # QUESTIONABLE / BUG: evaluator.py:302 takes as "the record that earned the rung" EVERY
        # `eval.block` of the agent before the rung was entered: all books, all earlier rungs. For
        # rung 3 that pools the rung-1 paper record (optimistic fills, by the memo's own account)
        # with the rung-2 real-money record that actually earned the rung; after a 3 -> 2 demotion
        # it also pools in the decayed rung-3 blocks. Here paper showed +1% a block and real money
        # +0.2%: the reference mean comes out near +0.6%, so an agent still doing exactly what
        # earned it rung 3 is demoted for "decay".
        # FIX: build `earned` from blocks with `previous_entered < seq <= entered` (the rung just
        # below), and filter it by the book that rung was judged on.
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


if __name__ == "__main__":
    unittest.main()
