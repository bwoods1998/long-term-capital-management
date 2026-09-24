"""Promotion on proof (the close-the-gaps run, Sept 24, 2026; docs/goals/LTCM_CLOSE_THE_GAPS.md D4, P1-P3).

The evidence on record: the allocator's nine promotions to real money (08:28Z Sept 23 to 00:17Z Sept
24) all ran unproven mechanisms and settled -$18.62 on 16 settlements, 0 positive; four were demoted
after one loss; and meriwether-h7d7702 was promoted twice on strikes stacked on the same games. So:
settlements count once per EVENT (D4), a first real stake is a PROBE unless the agent's family has a
proven pooled record (P1), one early loss on a probe is not a demotion (P2), and the book's entry
rules read the constitution's keys (P3's keys; `league/book.py` implements them).
"""

import math
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league import allocator, evaluator
from league.allocator import Evidence, bunt_ready
from league.constitution import CONSTITUTION
from league.evaluator import Evaluator, event_key
from league.ledger import Ledger
from league.tests.fakes import Clock

D = Decimal
P = allocator._params


def ev(**kw):
    base = dict(agent="a", venue="kalshi", rung=1, w_paper=1.0, w_real=1.0, e=1.0, paper_trades=0, paper_settled=0,
                real_trades=0, real_pnl=0.0, real_drawdown=0.0, haircut_log=0.0, real_seen=False)
    base.update(kw)
    return Evidence(**base)


class LedgerCase(unittest.TestCase):
    """A bare ledger with the rows a Book writes, by ticker."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.house = SimpleNamespace(ledger=self.ledger)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    @staticmethod
    def inst(ticker, right="no", venue="kalshi-shadow"):
        if venue.startswith("alpaca"):
            return {"asset_class": "crypto", "symbol": ticker, "venue": venue, "market_id": None, "multiplier": "1"}
        return {"asset_class": "event", "symbol": ticker, "venue": venue, "market_id": ticker, "right": right, "multiplier": "1"}

    def stake(self, usd, agent="a", book="kalshi-shadow"):
        self.ledger.append("book.stake", {"book": book, "usd": str(usd), "note": "t", "real_money": book in ("kalshi", "alpaca")},
                           agent=agent)

    def buy(self, ticker, quantity, price, agent="a", book="kalshi-shadow", liquidity="taker"):
        cost = D(str(quantity)) * D(str(price))
        self.ledger.append("book.fill", {"book": book, "source": "venue", "side": "buy", "realized": None, "flat": None,
                                         "instrument": self.inst(ticker, venue=book), "quantity": str(quantity),
                                         "price": str(price), "cash_delta": str(-cost), "liquidity": liquidity}, agent=agent)

    def sell(self, ticker, realized, agent="a", book="kalshi-shadow", flat=True, liquidity="taker"):
        self.ledger.append("book.fill", {"book": book, "source": "venue", "side": "sell", "realized": str(realized),
                                         "flat": flat, "instrument": self.inst(ticker, venue=book), "quantity": "1",
                                         "price": "1", "cash_delta": "1", "liquidity": liquidity}, agent=agent)

    def settle(self, ticker, pnl, agent="a", book="kalshi-shadow"):
        self.ledger.append("book.settle", {"book": book, "instrument": self.inst(ticker, venue=book), "pnl": str(pnl),
                                           "cost": "1", "payout": "1", "quantity": "1", "result": "no"}, agent=agent)


#: meriwether-h7d7702's practice record at its promotion of 00:39:48Z Sept 24, 2026 (the T0 snapshot,
#: seq 308404-379415): NO at strikes 7, 8 and 9 of two MLB totals, every one a taker, six settlements.
MERIWETHER_BUYS = [("KXMLBTOTAL-26SEP231310WSHDET-7", 25, "0.37"), ("KXMLBTOTAL-26SEP231310WSHDET-8", 19, "0.50"),
                   ("KXMLBTOTAL-26SEP231310WSHDET-9", 16, "0.58"), ("KXMLBTOTAL-26SEP231545MINSF-7", 25, "0.37"),
                   ("KXMLBTOTAL-26SEP231545MINSF-8", 20, "0.48"), ("KXMLBTOTAL-26SEP231545MINSF-9", 17, "0.57")]
MERIWETHER_SETTLES = [("KXMLBTOTAL-26SEP231310WSHDET-7", "15.546"), ("KXMLBTOTAL-26SEP231310WSHDET-8", "9.3337"),
                      ("KXMLBTOTAL-26SEP231310WSHDET-9", "6.5835"), ("KXMLBTOTAL-26SEP231545MINSF-7", "15.546"),
                      ("KXMLBTOTAL-26SEP231545MINSF-8", "10.2252"), ("KXMLBTOTAL-26SEP231545MINSF-9", "7.1641")]


class IndependentSettlements(LedgerCase):
    """D4: on the event books a closed trade and a settlement count once per EVENT."""

    def test_the_event_of_a_kalshi_market(self):
        self.assertEqual(event_key({"market_id": "KXMLBTOTAL-26SEP231840MILPHI-6"}), "KXMLBTOTAL-26SEP231840MILPHI")
        self.assertEqual(event_key({"market_id": "KXBTCD-26SEP2401-T62999.99"}), "KXBTCD-26SEP2401")
        self.assertEqual(event_key({"market_id": "KXHIGHNY-26SEP24-B72.5"}), "KXHIGHNY-26SEP24")
        self.assertEqual(event_key({"market_id": "KXETH15M-26SEP232145-45"}), "KXETH15M-26SEP232145")
        # A player prop names the game, then the player: one game is one event (Kalshi's event
        # ticker, and the House's own tapes: `league/tapes.py`), never one event per player.
        self.assertEqual(event_key({"market_id": "KXMLBHIT-26SEP222140LAAATH-LAAMTROUT27-4"}), "KXMLBHIT-26SEP222140LAAATH")
        self.assertEqual(event_key({"market_id": "kxhighny-26sep24-b72.5"}), "KXHIGHNY-26SEP24")
        self.assertEqual(event_key({"symbol": "KXRAIN-26SEP19-MIA"}), "KXRAIN-26SEP19")
        # An explicit event on the instrument wins; a bare name is its own event; nothing is nothing.
        self.assertEqual(event_key({"market_id": "KXA-1-2", "event_ticker": "KXA-EVENT"}), "KXA-EVENT")
        self.assertEqual(event_key({"market_id": "M7"}), "M7")
        self.assertIsNone(event_key({}))
        self.assertIsNone(event_key(None))

    def test_three_strikes_of_one_game_are_one_settlement_and_two_games_are_two(self):
        for strike in ("6", "7", "8"):
            self.settle(f"KXMLBTOTAL-26SEP231840MILPHI-{strike}", "1")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (1, 1))
        for strike in ("7", "8", "9", "10"):
            self.settle(f"KXMLBTOTAL-26SEP231835TORBALG2-{strike}", "1")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (2, 2))
        with patch.dict(CONSTITUTION["allocator"], {"independent_settlements": "trade"}):  # the old count, by the key
            self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (7, 7))

    def test_a_flat_sale_counts_toward_its_event(self):
        self.sell("KXBTCD-26SEP2401-T62999.99", "0.40")
        self.settle("KXBTCD-26SEP2401-T63249.99", "0.10")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (1, 1))
        self.sell("KXBTCD-26SEP2402-T62999.99", "0.40", flat=False)  # a partial sale closes nothing
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (1, 1))
        self.sell("KXBTCD-26SEP2402-T62999.99", "0.40")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (2, 1))

    def test_the_real_book_counts_the_same_way_and_a_stay_counts_from_its_start(self):
        self.settle("KXHIGHNY-26SEP24-B72.5", "1", book="kalshi")
        self.settle("KXHIGHNY-26SEP24-B74.5", "1", book="kalshi")
        start = self.ledger.head()[0]
        self.settle("KXHIGHMIA-26SEP24-B90.5", "1", book="kalshi")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi"), (2, 2))
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi", since_seq=start), (1, 1))

    def test_alpaca_counts_every_closed_trade(self):
        for _ in range(3):
            self.sell("BTC/USD", "0.40", book="alpaca-paper")
        self.assertEqual(allocator.closed_trades(self.house, "a", "alpaca-paper"), (3, 0))

    def test_a_closed_row_without_a_market_counts_alone(self):
        for _ in range(3):
            self.ledger.append("book.settle", {"book": "kalshi-shadow", "pnl": "1"}, agent="a")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (3, 3))

    def test_meriwether_h7d7702s_stacked_record_does_not_reach_the_bunt_line(self):
        """Promoted at 00:39:48Z Sept 24, 2026 "E 1.1303 ... on 6 closed trades": two games."""
        self.stake(200)
        for ticker, quantity, price in MERIWETHER_BUYS:
            self.buy(ticker, quantity, price)
        for ticker, pnl in MERIWETHER_SETTLES:
            self.settle(ticker, pnl)
        trades, settled = allocator.closed_trades(self.house, "a", "kalshi-shadow")
        self.assertEqual((trades, settled), (2, 2))
        p = P()
        self.assertFalse(bunt_ready(ev(e=1.1303, paper_trades=trades, paper_settled=settled), p))
        with patch.dict(CONSTITUTION["allocator"], {"independent_settlements": "trade"}):
            trades, settled = allocator.closed_trades(self.house, "a", "kalshi-shadow")
            self.assertEqual((trades, settled), (6, 6))
            self.assertTrue(bunt_ready(ev(e=1.1303, paper_trades=trades, paper_settled=settled), P()))
        # Its first promotion, 20:07:05Z Sept 23, "E 1.0973 ... on 3 closed trades", was ONE game.
        self.assertEqual(len({event_key({"market_id": t}) for t, _ in MERIWETHER_SETTLES[:3]}), 1)


class EvaluatorCountsEvents(LedgerCase):
    """The old ladder's gates (`enabled: False`, the rollback) count the same way."""

    def test_the_settled_lane_counts_one_settlement_an_event(self):
        ev_ = Evaluator(self.ledger, clock=self.clock)
        for strike in ("7", "8", "9"):
            self.settle(f"KXMLBTOTAL-26SEP231310WSHDET-{strike}", "1")
        lane = ev_._settled_lane("a", "kalshi-shadow", 1, "day", 0)
        self.assertEqual((lane["settled"], lane["open"]), (1, False))
        self.settle("KXMLBTOTAL-26SEP231545MINSF-7", "1")
        self.settle("KXHIGHNY-26SEP24-B72.5", "1")
        lane = ev_._settled_lane("a", "kalshi-shadow", 1, "day", 0)
        self.assertEqual((lane["settled"], lane["open"]), (3, True))

    def test_the_screens_closed_trade_count_is_independent(self):
        ev_ = Evaluator(self.ledger, clock=self.clock)
        self.stake(200)
        for strike in ("7", "8", "9"):
            self.buy(f"KXMLBTOTAL-26SEP231310WSHDET-{strike}", 10, "0.4")
            self.settle(f"KXMLBTOTAL-26SEP231310WSHDET-{strike}", "5")
        self.assertEqual(ev_.independent_closed("a", "kalshi-shadow"), 1)
        self.assertEqual(len(ev_.trade_returns("a", "kalshi-shadow")[0]), 3)  # the statistics still see three trades
        with patch.dict(CONSTITUTION["allocator"], {"independent_settlements": "trade"}):
            self.assertEqual(Evaluator(self.ledger, clock=self.clock).independent_closed("a", "kalshi-shadow"), 3)


class MoneySet(unittest.TestCase):
    """Every key of Deploy A's money set carries a row of the plan's closed table, inside its bounds."""

    def setUp(self):
        self.r = CONSTITUTION["allocator"]

    def test_independent_settlements_are_counted_per_event(self):
        self.assertEqual(self.r["independent_settlements"], "event")

    def test_one_event_holds_at_most_a_quarter_of_a_real_stake(self):
        self.assertEqual(self.r["max_event_share"], "0.25")
        self.assertTrue(D("0.2") <= D(self.r["max_event_share"]) <= D("0.5"))

    def test_an_unproven_familys_first_real_stake_is_a_probe(self):
        probe, bunt = self.r["probe_bunt_usd"], self.r["bunt_usd"]
        self.assertEqual(probe, {"kalshi": "10", "alpaca": "25"})
        self.assertTrue(D("5") <= D(probe["kalshi"]) <= D("15"))
        self.assertTrue(D("20") <= D(probe["alpaca"]) <= D("25"))
        # A proven family's bunt is unchanged and never smaller than a probe.
        self.assertEqual(bunt, {"kalshi": "30", "alpaca": "25"})
        self.assertTrue(D("30") <= D(bunt["kalshi"]) <= D("60") and D("25") <= D(bunt["alpaca"]) <= D("60"))
        self.assertTrue(all(D(probe[v]) <= D(bunt[v]) for v in probe))
        # Alpaca takes no crypto order under $10, and the book refuses an order over half an account.
        self.assertGreaterEqual(D(probe["alpaca"]) / 2, D(self.r["venue_minimum_usd"]["alpaca"]))
        self.assertEqual(self.r["option_bunt_usd"], "80")  # one contract cannot be cut smaller

    def test_a_family_is_proven_by_its_pooled_record(self):
        rule = self.r["family_proven"]
        self.assertEqual(rule, {"min_independent_settlements": 10, "practice_weight": "0.5", "real_weight": "1",
                                "confidence": "0.8"})
        self.assertTrue(10 <= rule["min_independent_settlements"] <= 20)

    def test_the_one_loss_trial_and_the_event_position_share(self):
        self.assertEqual(self.r["hysteresis_after_settled"], 3)
        self.assertTrue(0 <= self.r["hysteresis_after_settled"] <= 5)
        self.assertEqual(self.r["position_share_event"], "0.2")
        self.assertTrue(D("0.15") <= D(self.r["position_share_event"]) <= D("0.5"))
        self.assertEqual(self.r["position_share"], 0.5)  # Alpaca keeps its half
        self.assertEqual(self.r["real_drawdown_demote"], 0.35)  # the stay drawdown always applies, unchanged

    def test_the_book_side_keys(self):
        self.assertEqual(self.r["longshot_floor_real"], "0.30")
        self.assertTrue(D("0.15") <= D(self.r["longshot_floor_real"]) <= D("0.35"))
        self.assertEqual(self.r["real_entry_liquidity"], "maker_unless_family_taker_positive")

    def test_the_lines_that_may_only_rise_did_not_fall(self):
        self.assertGreaterEqual(self.r["bunt_at"], 1.01)
        self.assertGreaterEqual(self.r["bunt_min_trades"], 5)
        self.assertGreaterEqual(self.r["bunt_min_settled"], 3)
        self.assertGreaterEqual(self.r["swing_min_real_trades"], 8)


if __name__ == "__main__":
    unittest.main()
