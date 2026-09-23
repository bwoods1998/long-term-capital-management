"""Adversarial checks for evidence that can arrive faster than a wall-clock block.

All cash movements are synthetic ledger entries. No broker or provider is contacted.
"""
import math
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from league.episodes import completed
from league.evaluator import Evaluator
from league.ledger import Ledger
from league import stats
from league.constitution import CONSTITUTION
from league.tests.fakes import Clock

#: Promotion's error budget and the completed-exposure route's share of it (0.20 and 0.10 since the
#: owner's swing-and-bunt revision of Sept 23, 2026; 0.05 and 0.025 before).
FULL = CONSTITUTION['ladder'].get('promotion_alpha', CONSTITUTION['ladder']['alpha'])
HALF = FULL * CONSTITUTION['ladder']['completed_exposures']['promotion_alpha_share']


class Episodes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.ledger = Ledger(Path(self.tmp.name) / 'ledger.sqlite', clock=self.clock)
        self.addCleanup(self.ledger.close)
        self.ev = Evaluator(self.ledger)
        self.ev.seat('a', 2, 'test micro')
        self.cash = Decimal('25')
        self.stake = Decimal('25')
        self.add('book.stake', {'usd': '25'})

    def add(self, kind, p, *, book='real', agent='a'):
        self.clock.advance(1)
        return self.ledger.append(kind, {'book': book, **p}, agent=agent)

    def fill(self, side, cash, quantity, *, symbol='BTC/USD', flat=None, **kw):
        self.cash += Decimal(str(cash))
        return self.add('book.fill', {'instrument': {'symbol': symbol}, 'side': side,
            'source': 'venue', 'cash_delta': str(cash), 'position_delta': str(quantity),
            'quantity': str(abs(Decimal(str(quantity)))), 'flat': flat, **kw})

    def mark(self, *, equity=None, holdings=0):
        return self.add('book.mark', {'equity': str(self.cash if equity is None else equity),
                                      'staked': str(self.stake), 'holdings': holdings})

    def roundtrip(self, pnl, *, mark=True):
        self.fill('buy', '-5.01', 1)
        self.fill('sell', Decimal('5.01') + Decimal(str(pnl)), -1, flat=True)
        if mark:
            self.mark()

    def record(self, pnls):
        for pnl in pnls:
            self.roundtrip(pnl)

    def test_cash_fees_and_compounding_match_actual_flat_equity(self):
        self.record(['.10', '-.05', '.20'])
        rows = completed(self.ledger, 'a', 'real')
        self.assertEqual(len(rows), 3)
        self.assertAlmostEqual(math.exp(sum(r['log_growth'] for r in rows)), float(self.cash / 25))
        self.assertAlmostEqual(rows[0]['return'], .1 / 25)
        self.assertAlmostEqual(rows[1]['return'], -.05 / 25.1)
        self.assertAlmostEqual(rows[0]['risk_fraction'], 5.01 / 25)

    def test_repair_restarts_evidence_cadence_without_refunding_statistical_allowances(self):
        self.add('eval.verdict', {'decision': 'episode-look', 'rung': 2, 'episodes': 100,
                                 'tested_promotion': True, 'tested_death': True})
        correction = self.add('book.fill_correction', {'cash_delta': '0'})
        self.record(['.15', '.10', '-.01'] * 4)
        self.ev.judge('a', 'real')
        looks = [e for e in self.ledger.iter(kinds='eval.verdict', agent='a')
                 if e.payload.get('decision') == 'episode-look']
        self.assertEqual(len(looks), 2)
        self.assertGreater(looks[-1].seq, correction.seq)
        self.assertEqual(looks[-1].payload['look'], 2)
        self.assertEqual(looks[-1].payload['episodes'], 12)
        budget = self.ev._episode_allowance('a', self.ev._rung_entered('a'), 'promotion')
        self.assertAlmostEqual(looks[-1].payload['alpha_spent'], stats.spend(budget, 2))

    def test_overlapping_positions_and_partial_exits_are_one_exposure(self):
        self.fill('buy', -5, 2)
        self.fill('buy', -5, 2, symbol='ETH/USD')
        for symbol in ('BTC/USD', 'ETH/USD'):
            self.fill('sell', 3, -1, symbol=symbol, flat=False)
            self.assertEqual(completed(self.ledger, 'a', 'real'), [])
        self.fill('sell', 3, -1, flat=True)
        self.assertEqual(completed(self.ledger, 'a', 'real'), [])
        self.fill('sell', 3, -1, symbol='ETH/USD', flat=True)
        rows = completed(self.ledger, 'a', 'real')
        self.assertEqual((len(rows), rows[0]['trades']), (1, 2))
        self.assertAlmostEqual(rows[0]['return'], 2 / 25)

    def test_settlement_and_dust_writeoff_keep_losses(self):
        self.fill('buy', -5, 1)
        self.add('book.settle', {'instrument': {'symbol': 'BTC/USD'}, 'payout': '0', 'quantity': '1'})
        self.fill('buy', -5, 1)
        self.fill('sell', 0, -1, source='dust')
        rows = completed(self.ledger, 'a', 'real')
        self.assertEqual(len(rows), 2)
        self.assertLess(rows[0]['return'], 0)
        self.assertLess(rows[1]['return'], 0)

    def test_deposit_does_not_mint_profit_and_withdrawal_does_not_shrink_risk(self):
        self.fill('buy', -5, 1)
        self.add('book.stake', {'usd': '25'})
        self.add('book.stake', {'usd': '-20'})
        self.fill('sell', 6, -1, flat=True)
        row = completed(self.ledger, 'a', 'real')[0]
        self.assertAlmostEqual(row['return'], 1 / 50)
        self.assertAlmostEqual(row['risk_fraction'], 5 / 50)

    def test_carried_positions_and_future_rows_do_not_leak_across_rungs(self):
        first = self.fill('buy', -5, 1)
        boundary = self.ledger.head()[0]
        self.fill('sell', 6, -1, flat=True)
        self.assertEqual(completed(self.ledger, 'a', 'real', since_seq=boundary), [])
        self.assertEqual(completed(self.ledger, 'a', 'real', until_seq=first.seq), [])
        self.roundtrip('.1')
        cut = self.ledger.head()[0]
        self.roundtrip('.2')
        rows = completed(self.ledger, 'a', 'real', since_seq=boundary, until_seq=cut)
        self.assertEqual(len(rows), 1)
        self.assertLessEqual(rows[0]['last_seq'], cut)
        self.assertEqual(completed(self.ledger, 'a', 'other'), [])
        self.assertEqual(completed(self.ledger, 'other', 'real'), [])

    def test_malformed_flat_or_nonfinite_records_cannot_be_repaired_by_winners(self):
        self.fill('buy', -5, 2)
        self.fill('sell', 6, -1, flat=True)  # actually leaves a share: corrupt source data
        self.record(['.1'] * 12)
        self.assertEqual(completed(self.ledger, 'a', 'real'), [])
        self.add('book.stake', {'usd': 'NaN'})
        self.record(['.1'] * 12)
        self.assertEqual(completed(self.ledger, 'a', 'real'), [])

    def test_ten_complete_exposures_can_qualify_without_any_hourly_block(self):
        self.record(['.15'] * 7 + ['-.01'] * 3)
        verdict = self.ev.judge('a', 'real')
        self.assertEqual(verdict.decision, 'eligible', verdict)
        self.assertEqual((verdict.numbers['episodes'], verdict.numbers['active_blocks']), (10, 0))
        self.assertGreater(verdict.numbers['lcb'], 0)
        self.assertEqual(verdict.numbers['alpha_spent'], stats.spend(HALF, 1))
        self.assertEqual(self.ev.rung('a'), 2)  # evaluator qualifies; House owns admission

    def test_losing_and_lopsided_controls_do_not_scale(self):
        self.record(['.001'] * 10)
        verdict = self.ev.judge('a', 'real')
        self.assertEqual(verdict.decision, 'hold')
        look = [e.payload for e in self.ledger.iter(kinds='eval.verdict', agent='a')
                if e.payload.get('decision') == 'episode-look'][-1]
        self.assertTrue(look['lopsided'])
        self.assertLess(look['loss_gate_lcb'], 0)

    def test_negative_evidence_can_kill_without_waiting_for_twenty_hours(self):
        self.record(['-.15'] * 7 + ['.01'] * 3)
        verdict = self.ev.judge('a', 'real')
        self.assertEqual(verdict.decision, 'die', verdict)
        self.assertEqual(verdict.numbers['active_blocks'], 0)

    def test_a_large_completed_loss_dies_before_ten_exposures_or_one_hour(self):
        self.fill('buy', -10, 1)
        self.fill('sell', 0, -1, flat=True)
        self.mark()
        verdict = self.ev.judge('a', 'real')
        self.assertEqual(verdict.decision, 'die', verdict)
        self.assertEqual(verdict.numbers['episodes'], 1)

    def test_zero_growth_is_not_a_winner(self):
        self.record(['0'] * 10)
        self.assertEqual(self.ev.judge('a', 'real').decision, 'hold')

    def test_repeat_reads_do_not_buy_more_looks_and_next_five_share_the_budget(self):
        self.record(['.001'] * 10)
        for _ in range(10):
            self.ev.judge('a', 'real')
        self.record(['.001'] * 5)
        self.ev.judge('a', 'real')
        looks = [e.payload for e in self.ledger.iter(kinds='eval.verdict', agent='a')
                 if e.payload.get('decision') == 'episode-look']
        self.assertEqual(len(looks), 2)
        self.assertEqual([r['alpha_spent'] for r in looks], [stats.spend(HALF, k) for k in (1, 2)])
        self.assertLess(sum(r['alpha_spent'] for r in looks), HALF)

    def test_legacy_full_alpha_looks_do_not_get_a_second_error_budget(self):
        self.add('eval.verdict', {'decision': 'look', 'rung': 2, 'active_blocks': 30,
                                 'alpha_spent': stats.spend(FULL, 1)})
        self.record(['.15'] * 7 + ['-.01'] * 3)
        self.ev.judge('a', 'real')
        budget = self.ev._episode_allowance('a', self.ev._rung_entered('a'), 'promotion')
        self.assertAlmostEqual(budget, HALF - stats.spend(HALF, 1))
        # Already spent + the entire remaining block series + the new episode series <= the budget.
        total = stats.spend(FULL, 1) + (HALF - stats.spend(HALF, 1)) + budget
        self.assertAlmostEqual(total, FULL)

    def test_open_loser_stale_mark_or_unmarked_fill_cannot_hide_behind_closed_winners(self):
        self.record(['.15'] * 7 + ['-.01'] * 3)
        self.fill('buy', -5, 1)
        self.assertEqual(self.ev.judge('a', 'real').decision, 'hold')
        self.mark(equity=20, holdings=1)
        self.assertEqual(self.ev.judge('a', 'real').decision, 'hold')

    def test_paper_screen_needs_ten_and_a_current_flat_profitable_mark(self):
        self.ev.demote('a', 'paper screen test')
        self.record(['.02', '-.01'] * 4 + ['.02'])
        self.assertEqual(self.ev.judge('a', 'real').decision, 'hold')
        self.roundtrip('.02', mark=False)
        self.assertEqual(self.ev.judge('a', 'real').decision, 'hold')
        self.mark()
        verdict = self.ev.judge('a', 'real')
        self.assertEqual(verdict.decision, 'eligible', verdict)
        self.assertIsNone(verdict.numbers['alpha_spent'])
        self.assertEqual(verdict.numbers['via'], 'completed_exposures')

    def test_fast_promotion_has_fast_drift_detection_with_no_hourly_reference(self):
        self.record(['.15'] * 7 + ['-.01'] * 3)
        verdict = self.ev.judge('a', 'real')
        self.assertEqual(verdict.decision, 'eligible')
        self.ev.promote('a', 3, verdict.reason, verdict.numbers)
        self.record(['-.20'] * 5)
        drift = self.ev.drift('a', 'real')
        self.assertEqual(drift.decision, 'demote', drift)
        self.assertEqual(drift.numbers['reference_episodes'], 10)
        self.assertEqual(drift.numbers['recent_episodes'], 5)


if __name__ == '__main__':
    unittest.main()
