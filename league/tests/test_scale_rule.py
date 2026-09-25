"""K5, the scale rule (league/grants.py, league/live_trading.py): version 2 of the owner's live grant, switched off.

Against disposable state only: a fixture board in the live board's shape, a ledger written here, a campaign database
activated here. Nothing reads the box, a venue or the gateway.
"""
from decimal import Decimal, ROUND_DOWN
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import time
from unittest import TestCase
from unittest.mock import patch

from league import grants
from league.campaigns import CampaignBudget, CampaignClosed
from league.constitution import CONSTITUTION
from league.grants import Day, build_days, capacity_used, evaluate, replay, scale_tranches, supported_multiple
from league.ledger import Ledger, canonical
from league import live_trading
from league.live_trading import grant_version, policy, ratify_version, render_scale_report, scale_report
from league.tests.test_phase1 import PhaseCase

REPO = Path(__file__).resolve().parents[2]
DAY = 86400.0
TODAY = '2026-09-25'
NOW = grants.midnight(TODAY) + 6 * 3600 + 3 * 60 + 51  # the T0 board, 06:03:51Z Sept 25
#: The live grant's capital (floor($1,017.75 / $10) = 101 seats, `policy`): Alpaca $500, Kalshi $517.75.
LIVE_CAPITAL = {'alpaca': '500.00', 'kalshi': '517.75'}
#: The proven sports family's capacity on the board at T0 (Sept 25, 2026).
CAPACITY = {'size_usd': 6.0, 'fill_rate_at_size': 1.0, 'markets_per_day': 19.349, 'settlements_per_day': 5.047,
            'usd_per_day': 31.6974, 'binds': False}
BLOCK = scale_tranches()


def stamp(t):
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(t)) + '.000Z'


def family(state='proven', members=1, stake='30', capacity=None, name='sports-central-run-under', venue='kalshi'):
    """A family's row as `families.row_of` writes it (the board's `families` entry and the `family.record` payload)."""
    return {'family': name, 'venue': venue, 'unit': 'at_risk', 'state': state, 'since': '2026-09-24T02:00:00.000Z',
            'n': 26, 'n_eff': 20.1, 'mean_log': 0.12, 'bound': 0.092, 'loss_gate': None, 'proven': state != 'unproven',
            'edge_per_dollar': 0.27, 'real': {'n': 12, 'mean_log': 0.1, 'bound': 0.093, 'loss_gate': None, 'honest_bound': 0.093,
                                              'entry': None},
            'maker': {'n': 20, 'bound': 0.05, 'positive': True}, 'taker': {'n': 0, 'bound': None, 'positive': False},
            'blocks': {}, 'members': 4, 'members_living': 3, 'members_real': members, 'stake_usd': stake,
            'capacity': dict(CAPACITY if capacity is None else capacity), 'swing': None}


def board(families=None, kalshi=('546.83', '109.23'), alpaca=('500', '230.94')):
    """The live board's shape (`Allocator._publish_board`): envelope, families = {venue: {family: record}}, agents, throttle."""
    families = {'kalshi': {'sports-central-run-under': family(),
                           'weather-favorites': family('unproven', 3, '10', {'size_usd': 2.0, 'fill_rate_at_size': 0.8},
                                                       name='weather-favorites')}} if families is None else families
    for rows in families.values():
        for row in rows.values():
            row.pop('family', None)
            row.pop('venue', None)
            row['swing_clock'] = None
    return {'enabled': True, 'at': stamp(NOW), 'bands': {}, 'moves': [],
            'envelope': {'kalshi': {'capital_usd': kalshi[0], 'committed_usd': kalshi[1]},
                         'alpaca': {'capital_usd': alpaca[0], 'committed_usd': alpaca[1]}},
            'throttle': {'active': False, 'floor_pnl_usd': '10.75', 'envelope_usd': '1017.75'},
            'families': families,
            'agents': {'meriwether-h2d625d': {'band': 'bunt', 'stake_usd': '16.62', 'equity_usd': '19.01', 'target_usd': '30',
                                              'venue': 'kalshi', 'family': 'sports-central-run-under', 'family_state': 'proven',
                                              'family_bound': 0.093, 'family_n': 26,
                                              'capacity': {'usd_per_day': 31.6974, 'binds': False}, 'stake_limit': None}}}


def write_ledger(path, *, family_rows, pnl, envelope=lambda t: {'kalshi': '546.83', 'alpaca': '500'},
                 equity=lambda t: {'kalshi': '560.00', 'alpaca': '505.00'}, start=None, end=NOW, step=3600.0):
    """Hourly `alloc.board`, `book.mark` (real books: `pnl(t)` = {venue: {account: (equity, staked)}}) and `floor.mark`
    rows from `start` to `end`, and the `family.record` rows [(t, row)], in time order as the House appends them."""
    ledger = Ledger(path)
    rows = [(t, 'family.record', {**row, 'at': stamp(t)}) for t, row in family_rows]
    t = grants.midnight('2026-09-21') if start is None else start
    while t <= end:
        rows.append((t, 'alloc.board', {'agents': {}, 'throttle': False,
                                         'envelope': {v: {'capital_usd': c, 'committed_usd': '100'} for v, c in envelope(t).items()}}))
        for venue, accounts in pnl(t).items():
            for account, (value, staked) in accounts.items():
                rows.append((t, 'book.mark', {'book': venue, 'equity': str(value), 'staked': str(staked), 'real_money': True,
                                              'cash': str(value), 'realized': '0', 'fees': '0', 'holdings': 0, '_agent': account}))
        rows.append((t, 'book.mark', {'book': 'kalshi-shadow', 'equity': '999', 'staked': '0', 'real_money': False,
                                      'cash': '999', 'realized': '0', 'fees': '0', 'holdings': 0, '_agent': 'practice'}))
        rows.append((t, 'floor.mark', {'venues': [{'venue': v, 'equity': e, 'cash': e, 'as_of': stamp(t)} for v, e in equity(t).items()],
                                       'as_of': stamp(t)}))
        t += step
    for t, kind, payload in sorted(rows, key=lambda r: r[0]):
        agent = payload.pop('_agent', 'house')
        ledger.append(kind, payload, agent=agent, at=stamp(t))
    ledger.close()


def rising(per_day='2', venue='kalshi'):
    """The venue's real P&L rising `per_day` from Sept 21: one account up, one flat."""
    base = grants.midnight('2026-09-21')
    return lambda t: {venue: {'a1': (Decimal('30') + Decimal(per_day) * Decimal(str((t - base) / DAY)).quantize(Decimal('.01')),
                                     Decimal('30')), 'a2': (Decimal('10'), Decimal('10'))}}


class CapacityArithmetic(TestCase):
    def test_the_supported_multiple_is_the_largest_size_before_fills_halve(self):
        cases = [({'fill_rate_at_size': 1.0}, 1),  # no curve beyond the measured size: 1x, never assumed larger
                 ({'fill_rate_at_size': None}, 0), ({}, 0), ({'fill_rate_at_size': 0.0}, 0),
                 ({'fill_rate_at_size': 1.0, 'fill_curve': {'2': 0.9, '4': 0.4}}, 2),
                 ({'fill_rate_at_size': 1.0, 'fill_rate_at_2x': 0.8, 'fill_rate_at_4x': 0.5}, 4),  # exactly half holds
                 ({'fill_rate_at_size': 1.0, 'fill_curve': {'2x': 0.6, '4x': 0.35}}, 2),  # halved against 1x in two steps
                 ({'fill_rate_at_size': 0.5, 'fill_curve': {'2': 1.0, '4': 0.45}}, 2),  # halved against the step before
                 ({'fill_rate_at_size': 1.0, 'fill_curve': {'4': 0.9}}, 1),  # 2x never measured: the walk stops there
                 ({'fill_rate_at_size': 1.0, 'fill_curve': [{'multiple': 2, 'fill_rate': 1.0}, {'multiple': 4, 'fill_rate': 1.0},
                                                            {'multiple': 8, 'fill_rate': 0.9}]}, 8)]
        for capacity, expected in cases:
            with self.subTest(capacity=capacity):
                self.assertEqual(supported_multiple(capacity, '0.5'), expected)

    def test_capacity_used_is_members_on_real_money_times_stake_times_the_multiple_for_proven_families_only(self):
        rows = {'a': family(members=1), 'b': family('swing', 2, '45', {'fill_rate_at_size': 0.9, 'fill_curve': {'2': 0.85}}),
                'c': family('unproven', 9, '10'), 'd': family('proven', 0, '30'), 'e': family('proven', 2, '30', {'fill_rate_at_size': None})}
        total, lines = capacity_used(rows, '0.5')
        self.assertEqual(total, Decimal('30') + Decimal('180'))  # 1 x $30 x 1 + 2 x $45 x 2; unproven, memberless, unmeasured: $0
        self.assertEqual([(line['family'], line['usd'], line['multiple']) for line in lines],
                         [('b', '180.00', 2), ('a', '30.00', 1), ('d', '0.00', 1), ('e', '0.00', 0)])

    def test_the_t0_board_uses_five_and_a_half_percent_of_the_kalshi_envelope(self):
        total, _ = capacity_used(board()['families']['kalshi'], BLOCK['fills_halve_ratio'])
        self.assertEqual(total, Decimal('30.00'))
        self.assertEqual(f"{total / Decimal('546.83'):.4f}", '0.0549')


def day(name, capacity='400', envelope='546.83', readings=24, pnl='1'):
    return Day(name, Decimal(capacity), None if envelope is None else Decimal(envelope), readings,
               None if pnl is None else Decimal(pnl))


def days(**over):
    """The three days before TODAY, passing unless a day is overridden ({day: Day | None})."""
    out = {name: day(name) for name in grants.window_of(TODAY)}
    for name, value in over.items():
        name = name.replace('_', '-')[1:]
        if value is None:
            out.pop(name, None)
        else:
            out[name] = value
    return out


class Tranches(TestCase):
    def test_a_tranche_is_the_smaller_of_the_deposit_left_and_half_the_envelope(self):
        for funded, tranche, to_work in [('1546.83', '273.41', '0.00'),  # $1,000 deposited: half the envelope enters
                                         ('646.83', '100.00', '173.41'),  # $100 deposited: all of it, and $173.41 more would work
                                         ('820.24', '273.41', '0.00'), ('546.84', '0.01', '273.40')]:
            with self.subTest(funded=funded):
                result = evaluate(BLOCK, days(), today=TODAY, envelope='546.83', funded=funded)
                self.assertTrue(result['unlock'])
                self.assertEqual((result['tranche_usd'], result['deposit_to_work_usd']), (tranche, to_work))
                self.assertEqual(result['full_tranche_usd'], str((Decimal('546.83') / 2).quantize(Decimal('.01'), ROUND_DOWN)))
                self.assertEqual(result['fails'], [])

    def test_no_deposit_unlocks_nothing_and_names_the_deposit_that_would_work(self):
        for funded, to_work in (('546.83', '273.41'), ('400', '273.41'), (None, None)):
            with self.subTest(funded=funded):
                result = evaluate(BLOCK, days(), today=TODAY, envelope='546.83', funded=funded)
                self.assertTrue(result['evidence'])
                self.assertFalse(result['unlock'])
                self.assertEqual(result['tranche_usd'], '0.00')
                self.assertEqual([f['condition'] for f in result['fails']], ['deposit'])
                # Unread equity names no deposit (review of #313): the account may already hold one.
                self.assertEqual(result['deposit_to_work_usd'], to_work)

    def test_capacity_failing_alone_on_one_day_blocks_the_tranche_with_its_number(self):
        result = evaluate(BLOCK, days(_2026_09_23=day('2026-09-23', capacity='382.77')), today=TODAY, envelope='546.83',
                          funded='2000')
        self.assertFalse(result['unlock'])
        self.assertEqual(len(result['fails']), 1)
        fail = result['fails'][0]
        self.assertEqual((fail['condition'], fail['day'], fail['capacity_usd'], fail['envelope_usd']),
                         ('capacity', '2026-09-23', '382.77', '546.83'))
        self.assertLess(fail['share'], 0.70)
        self.assertEqual((result['capacity_needed_usd'], result['capacity_gap_usd']), ('382.78', '0.01'))
        self.assertEqual(result['deposit_to_work_usd'], '0.00')
        # 70% exactly holds.
        self.assertTrue(evaluate(BLOCK, days(_2026_09_23=day('2026-09-23', capacity='382.781')), today=TODAY,
                                 envelope='546.83', funded='2000')['unlock'])

    def test_a_day_is_judged_against_the_larger_of_its_envelope_and_the_envelope_now(self):
        bigger_then = days(_2026_09_22=day('2026-09-22', capacity='400', envelope='600'))
        result = evaluate(BLOCK, bigger_then, today=TODAY, envelope='546.83', funded='2000')
        self.assertEqual([(f['day'], f['envelope_usd']) for f in result['fails']], [('2026-09-22', '600')])
        bigger_now = evaluate(BLOCK, days(), today=TODAY, envelope='600', funded='2000')
        self.assertEqual([f['day'] for f in bigger_now['fails']], grants.window_of(TODAY))

    def test_pnl_failing_alone_blocks_the_tranche_with_its_number(self):
        for pnls, total in [(('1', '1', '-2'), '0'), (('5', '-3', '-2.01'), '-0.01')]:
            window = {name: day(name, pnl=p) for name, p in zip(grants.window_of(TODAY), pnls)}
            with self.subTest(pnls=pnls):
                result = evaluate(BLOCK, window, today=TODAY, envelope='546.83', funded='2000')
                self.assertFalse(result['unlock'])
                self.assertEqual([(f['condition'], f['pnl_usd']) for f in result['fails']], [('pnl', total)])
        unmeasured = evaluate(BLOCK, days(_2026_09_24=day('2026-09-24', pnl=None)), today=TODAY, envelope='546.83', funded='2000')
        self.assertEqual([(f['condition'], f['pnl_usd']) for f in unmeasured['fails']], [('pnl', None)])

    def test_the_window_is_exactly_the_three_complete_utc_days_before_today(self):
        self.assertEqual(grants.window_of(TODAY), ['2026-09-22', '2026-09-23', '2026-09-24'])
        outside = {**days(), '2026-09-21': day('2026-09-21', capacity='0', pnl='-100'),
                   TODAY: day(TODAY, capacity='0', pnl='-100')}  # four days ago and today do not count
        self.assertTrue(evaluate(BLOCK, outside, today=TODAY, envelope='546.83', funded='2000')['unlock'])
        for missing in grants.window_of(TODAY):  # three CONSECUTIVE days: a day without a reading breaks the run
            with self.subTest(missing=missing):
                gap = days(**{'_' + missing.replace('-', '_'): None})
                result = evaluate(BLOCK, gap, today=TODAY, envelope='546.83', funded='2000')
                self.assertFalse(result['unlock'])
                self.assertIn(f'no allocator reading on {missing}', [f['text'] for f in result['fails']])
        unread = evaluate(BLOCK, days(_2026_09_23=day('2026-09-23', readings=0)), today=TODAY, envelope='546.83', funded='2000')
        self.assertEqual([f['text'] for f in unread['fails']], ['no allocator reading on 2026-09-23'])
        tomorrow = evaluate(BLOCK, days(), today='2026-09-26', envelope='546.83', funded='2000')
        self.assertIn('no allocator reading on 2026-09-25', [f['text'] for f in tomorrow['fails']])


class Days(TestCase):
    def test_a_day_counts_its_lowest_capacity_and_its_pnl_from_the_marks(self):
        start = grants.midnight('2026-09-23')
        rows = [(start - DAY, family(members=13)), (start + 3600, family(members=2)), (start + 7200, family(members=14)),
                (start + 9000, family(members=1, name='other'))]
        envelopes = [(start + h * 3600.0, Decimal('546.83')) for h in range(48)]
        pnl = [(start - 60, Decimal('4')), (start + 3600, Decimal('9')), (start + DAY - 60, Decimal('6')), (start + DAY + 60, Decimal('1'))]
        out = build_days('kalshi', family_rows=rows, envelopes=envelopes, pnl=pnl, first_day='2026-09-23', last_day='2026-09-24',
                         ratio='0.5')
        self.assertEqual(out['2026-09-23'].capacity_usd, Decimal('60'))  # 13 members at the start, 2 for an hour: $60
        self.assertEqual(out['2026-09-24'].capacity_usd, Decimal('450'))  # 14 + the other family's 1, all day
        self.assertEqual((out['2026-09-23'].readings, out['2026-09-23'].envelope_usd), (24, Decimal('546.83')))
        self.assertEqual(out['2026-09-23'].pnl_usd, Decimal('2'))  # 6 at the day's last pass less 4 before it
        self.assertEqual(out['2026-09-24'].pnl_usd, Decimal('-5'))
        self.assertIsNone(build_days('kalshi', family_rows=rows, envelopes=envelopes, pnl=pnl[2:], first_day='2026-09-23',
                                     last_day='2026-09-23', ratio='0.5')['2026-09-23'].pnl_usd)  # no pass before the day
        # A day with the allocator's readings and no mark pass inside it is unmeasured, never $0 (review of #313).
        dark = build_days('kalshi', family_rows=rows, envelopes=envelopes, pnl=[pnl[0], pnl[3]], first_day='2026-09-23',
                          last_day='2026-09-24', ratio='0.5')
        self.assertEqual((dark['2026-09-23'].readings, dark['2026-09-23'].pnl_usd), (24, None))
        self.assertEqual(dark['2026-09-24'].pnl_usd, Decimal('-3'))  # 1 at 00:01Z Sept 24 less 4 before Sept 23
        lit = Day('2026-09-23', Decimal('400'), Decimal('546.83'), 24, dark['2026-09-23'].pnl_usd)  # capacity passing
        result = evaluate(BLOCK, days(_2026_09_23=lit), today=TODAY, envelope='546.83', funded='2000')
        self.assertEqual([(f['condition'], f['pnl_usd']) for f in result['fails']], [('pnl', None)])

    def test_losses_count_in_full_realized_and_marked_on_every_real_account(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        cut = grants.midnight('2026-09-24') + 12 * 3600

        def pnl(t):  # a1 realizes +$10 on the 22nd; a2's open position is marked down $15 on the 24th; the rest flat
            a1 = Decimal('40') if t >= grants.midnight('2026-09-22') + 3600 else Decimal('30')
            a2 = Decimal('5') if t >= cut else Decimal('20')
            return {'kalshi': {'a1': (a1, Decimal('30')), 'a2': (a2, Decimal('20'))}, 'alpaca': {'b1': (Decimal('25'), Decimal('25'))}}
        write_ledger(root / 'ledger.sqlite', family_rows=[(grants.midnight('2026-09-21'), family(members=14))], pnl=pnl,
                     equity=lambda t: {'kalshi': '1546.83', 'alpaca': '500'})
        shown = scale_report(root, now=NOW, board_path=self.write_board(root))
        kalshi = shown['venues']['kalshi']
        self.assertEqual([d['pnl_usd'] for d in kalshi['days'][:3]], ['10', '0', '-15'])
        self.assertEqual(kalshi['window_pnl_usd'], '-5')
        self.assertEqual([f['condition'] for f in kalshi['decision']['fails']], ['pnl'])  # capacity passed: 14 x $30 = $420
        self.assertEqual(kalshi['decision']['fails'][0]['pnl_usd'], '-5')

    def write_board(self, root, value=None):
        path = Path(root) / 'allocator-board.json'
        path.write_text(json.dumps(board() if value is None else value), encoding='utf-8')
        return path


class Relock(TestCase):
    def test_a_tranche_stays_until_real_pnl_since_its_unlock_falls_below_the_throttle_line_times_its_size(self):
        ratified = grants.midnight('2026-09-25') + 3600
        window = {**days(), **{n: day(n) for n in ('2026-09-25', '2026-09-26', '2026-09-27')}}
        base = [(grants.midnight('2026-09-21') + h * 3600.0, Decimal('546.83')) for h in range(24 * 9)]
        funded = [(grants.midnight('2026-09-21'), Decimal('1546.83'))]
        for drop, relocked in (('-82.03', True), ('-82.02', False), ('-82.00', False)):  # -0.30 x $273.41 = -$82.023
            pnl = [(grants.midnight('2026-09-21') + h * 3600.0, Decimal('10')) for h in range(24 * 4 + 1)]
            pnl += [(ratified + 7200, Decimal('10') + Decimal(drop)), (ratified + 10800, Decimal('50'))]
            with self.subTest(drop=drop):
                state = replay(BLOCK, window, pnl=pnl, funded=funded, envelopes=base, ratified_at=ratified,
                               now=ratified + 6 * 3600)
                first = state['tranches'][0]
                self.assertEqual((first['usd'], first['unlocked_at']), ('273.41', '2026-09-25T01:00:00Z'))
                self.assertEqual(first['relocked_at'] is not None, relocked)
                self.assertEqual(state['unlocked_usd'], '0.00' if relocked else '273.41')
                self.assertEqual(first['relock_line_usd'], '-82.023')

    def test_a_withdrawn_tranche_needs_a_whole_window_after_its_withdrawal(self):
        ratified = grants.midnight('2026-09-25') + 3600
        window = {n: day(n) for n in ('2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25', '2026-09-26', '2026-09-27',
                                      '2026-09-28', '2026-09-29')}
        base = [(grants.midnight('2026-09-21') + h * 3600.0, Decimal('546.83')) for h in range(24 * 10)]
        pnl = [(grants.midnight('2026-09-21') + h * 3600.0, Decimal('10')) for h in range(24 * 4 + 1)]
        pnl += [(ratified + 7200, Decimal('-90')), (ratified + 10800, Decimal('100'))]  # withdrawn on the 25th, then recovered
        state = replay(BLOCK, window, pnl=pnl, funded=[(grants.midnight('2026-09-21'), Decimal('1546.83'))], envelopes=base,
                       ratified_at=ratified, now=grants.midnight('2026-09-29') + 60)
        self.assertEqual([(t['unlocked_at'], t['relocked_at']) for t in state['tranches']],
                         [('2026-09-25T01:00:00Z', '2026-09-25T03:00:00Z'), ('2026-09-29T00:00:00Z', None)])
        self.assertEqual([d['unlock'] for d in state['decisions']], [True, False, False, False, True])
        self.assertIn('withdrawn on 2026-09-25', state['decisions'][1]['fails'][0]['text'])

    def test_the_next_tranche_is_judged_against_the_enlarged_envelope_and_never_exceeds_the_equity(self):
        ratified = grants.midnight('2026-09-25') + 3600
        rich = {n: day(n, capacity='2000') for n in ('2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25', '2026-09-26')}
        base = [(grants.midnight('2026-09-21') + h * 3600.0, Decimal('546.83')) for h in range(24 * 7)]
        pnl = [(grants.midnight('2026-09-21') + h * 3600.0, Decimal(h) / 10) for h in range(24 * 7)]
        funded = [(grants.midnight('2026-09-21'), Decimal('1500'))]
        state = replay(BLOCK, rich, pnl=pnl, funded=funded, envelopes=base, ratified_at=ratified,
                       now=grants.midnight('2026-09-27') + 60)
        self.assertEqual([t['usd'] for t in state['tranches']], ['273.41', '410.12', '269.64'])  # the last: $1,500 less $1,230.36
        self.assertEqual(state['unlocked_usd'], '953.17')  # $1,500 - $546.83: the equity, and no more
        modest = {n: day(n, capacity='400') for n in rich}
        state = replay(BLOCK, modest, pnl=pnl, funded=funded, envelopes=base, ratified_at=ratified,
                       now=grants.midnight('2026-09-27') + 60)
        self.assertEqual([t['usd'] for t in state['tranches']], ['273.41'])  # $400 is 49% of $820.24: the second waits
        self.assertIn('capacity used 48.8% < 70% on 2026-09-24', [f['text'].split(' ($')[0] for f in state['decisions'][-1]['fails']])
        poorer = replay(BLOCK, rich, pnl=pnl, funded=[(grants.midnight('2026-09-21'), Decimal('1500')),
                                                         (ratified + 7200, Decimal('600'))],
                        envelopes=base, ratified_at=ratified, now=ratified + 3 * 3600)
        self.assertEqual(poorer['unlocked_usd'], '53.17')  # the owner withdrew: the tranche shrinks to the equity above the base


# ------------------------------------------------------------------ the grant: version 1 pinned, version 2 switched off
#: main's `league/live_trading.py` before the scale rule, byte for byte (review of #313: the pin compares against MAIN'S
#: function, not a copy that could be edited to match). Its git blob id is the proof: `git rev-parse
#: 19c3771:league/live_trading.py` (and 80dd26d's, the same blob) prints MAIN_BLOB, and the test recomputes it.
MAIN_BLOB = '03973f92222ccfaeab9a5c7947b7ea16e21bf840'
MAIN_FILE = Path(__file__).resolve().parent / 'fixtures' / 'live_trading_main_03973f9.py.txt'


def main_module():
    data = MAIN_FILE.read_bytes()
    if hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest() != MAIN_BLOB:
        raise AssertionError(f'{MAIN_FILE.name} is not main\'s league/live_trading.py (blob {MAIN_BLOB})')
    namespace = {'__name__': 'league._live_trading_main', '__package__': 'league'}
    exec(compile(data, str(MAIN_FILE), 'exec'), namespace)  # its imports are relative to league, as on main
    return namespace


def golden_v1(venue_capital):
    """`policy` as main has it (MAIN_BLOB), run as main's own code."""
    return main_module()['policy'](venue_capital)


#: The money rules on the day of the pin (Sept 25, 2026, digest 535a7f15): what `policy` reads of them.
PIN_MONEY_DIGEST = '535a7f15fbcf5b39c61f1e3569d8b1dcef06084dc4ac06d545dd4bf55a71ce9d'
PIN_CONSTITUTION = {'rungs': {'2': {'stake_usd': 60}, '3': {'kelly_fraction': 1.0}},
                    'allocator': {'enabled': True, 'bunt_usd': {'kalshi': '30', 'alpaca': '25'},
                                  'probe_bunt_usd': {'kalshi': '10', 'alpaca': '25'}, 'max_share_of_venue': 0.6,
                                  'throttle': {'halve_below': -0.3, 'restore_above': -0.15},
                                  'family_swing': {'capacity_fill_ratio': '0.5'}}}
#: sha256 of the canonical JSON of the active grant's policy (earned-live-20260921: Alpaca $500, Kalshi $517.75).
ACTIVE_GRANT_DIGEST = '4c8e26075b386c5b34465cc5164e58abcec1ff18c69fae68c406234906fc33db'


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class GrantPin(TestCase):
    def test_the_golden_is_mains_file_by_its_git_blob_id(self):
        data = MAIN_FILE.read_bytes()
        self.assertEqual(hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest(), MAIN_BLOB)
        self.assertIn(b'def policy(venue_capital):', data)
        # Where the repository's objects are at hand, git agrees (a shallow CI checkout has no history: the id suffices).
        import subprocess
        try:
            shown = subprocess.run(['git', '-C', str(REPO), 'cat-file', 'blob', MAIN_BLOB], capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            shown = None
        if shown is not None and shown.returncode == 0:
            self.assertEqual(shown.stdout, data)

    def test_version_one_is_byte_for_byte_the_policy_before_the_scale_rule(self):
        for capital in (LIVE_CAPITAL, {'alpaca': '500', 'kalshi': '500'}, {'alpaca': '125.999', 'kalshi': '9000'},
                        {'alpaca': '0', 'kalshi': '30'}):
            with self.subTest(capital=capital):
                self.assertEqual(canonical(policy(capital)), canonical(golden_v1(capital)))
                self.assertEqual(canonical(policy(capital, version=1)), canonical(golden_v1(capital)))
        with patch.dict(CONSTITUTION['allocator'], {'enabled': False}):  # the allocator's rollback path too
            self.assertEqual(canonical(policy(LIVE_CAPITAL)), canonical(golden_v1(LIVE_CAPITAL)))

    def test_the_active_grants_digest_is_pinned(self):
        with patch('league.constitution.CONSTITUTION', PIN_CONSTITUTION), \
                patch('league.constitution.money_digest', return_value=PIN_MONEY_DIGEST):
            self.assertEqual(sha(golden_v1(LIVE_CAPITAL)), ACTIVE_GRANT_DIGEST)  # main's own function gives the pin
            self.assertEqual(sha(policy(LIVE_CAPITAL)), ACTIVE_GRANT_DIGEST)
        from league.constitution import money_digest
        if money_digest() != PIN_MONEY_DIGEST:
            self.skipTest('the money rules moved since the pin (a ratified promotion); the frozen rules above still pin version 1')
        self.assertEqual(sha(policy(LIVE_CAPITAL)), ACTIVE_GRANT_DIGEST)

    def test_version_two_differs_only_by_the_scale_rule(self):
        one, two = policy(LIVE_CAPITAL), policy(LIVE_CAPITAL, version=2)
        self.assertNotEqual(sha(one), sha(two))
        self.assertEqual(two['version'], 2)
        self.assertEqual(set(two) - set(one), {'scale_tranches'})
        self.assertEqual({k for k in one if one[k] != two[k]}, {'version', 'capital_source'})
        self.assertEqual(two['scale_tranches'], {**BLOCK})
        self.assertEqual((two['scale_tranches']['tranche_share'], two['scale_tranches']['min_capacity_share'],
                          two['scale_tranches']['window_days'], two['scale_tranches']['relock_share']), ('0.5', '0.70', 3, '-0.3'))
        with self.assertRaises(ValueError):
            policy(LIVE_CAPITAL, version=3)

    def test_the_relock_line_is_the_throttles_and_moving_it_moves_version_two(self):
        before = policy(LIVE_CAPITAL, version=2)
        with patch.dict(CONSTITUTION['allocator'], {'throttle': {'halve_below': -0.2, 'restore_above': -0.1}}):
            self.assertEqual(policy(LIVE_CAPITAL, version=2)['scale_tranches']['relock_share'], '-0.2')
            self.assertNotEqual(policy(LIVE_CAPITAL, version=2), before)


class Ratification(PhaseCase):
    def grant(self):
        from league.tests.test_live_trading import research_policy
        guard = self.budget()
        burst = guard.activate_burst('original-night', research_policy())
        self.now[0] = burst['ends'] + 3600
        live = guard.activate_live_trading('earned-live-20260921', LIVE_CAPITAL)
        self.assertTrue(live['active'])
        return guard

    def version(self, guard):
        return grant_version(guard.db, now=guard.clock())

    def test_nothing_reads_version_two_until_the_owner_ratifies_it(self):
        guard = self.grant()
        stored = guard.db.execute('SELECT policy FROM live_trading').fetchone()[0]
        self.assertEqual(stored, canonical(policy(LIVE_CAPITAL)))
        with patch('league.grants.scale_tranches', side_effect=AssertionError('the runtime read version 2')):
            live = guard.live_trading()  # what the House, the allocator and the book read
            self.assertTrue(live['active'] and guard.allows_live(2) and guard.allows_live(3) and guard.running())
            self.assertEqual(guard.live_authorization()['policy'], policy(LIVE_CAPITAL))
            self.assertEqual(live['policy']['version'], 1)
        shown = self.version(guard)
        self.assertEqual((shown['version'], shown['scale_policy'], shown['why_off']), (1, None, 'the owner never ratified version 2'))
        guard.ratify_live_trading('earned-live-20260921')  # a run's re-ratify after a promotion: version 1 stays
        self.assertEqual(self.version(guard)['version'], 1)
        self.assertEqual(guard.db.execute('SELECT policy FROM live_trading').fetchone()[0], stored)

    def test_the_owners_ratification_switches_version_two_on_and_version_one_switches_it_off(self):
        guard = self.grant()
        before = guard.live_trading()
        shown = ratify_version(guard, 'earned-live-20260921', 2)
        self.assertEqual(shown['version'], 2)
        self.assertEqual(shown['scale_policy'], policy(LIVE_CAPITAL, version=2))
        self.assertEqual(shown['ratified']['digest'], shown['proposed_digest'])
        self.assertEqual(guard.live_trading(), before)  # the stored grant and its checks are untouched
        self.assertEqual(ratify_version(guard, 'earned-live-20260921', 2)['version'], 2)
        self.assertEqual(guard.db.execute('SELECT COUNT(*) FROM live_grant_versions').fetchone()[0], 1)  # a retry adds no row
        off = ratify_version(guard, 'earned-live-20260921', 1)
        self.assertEqual((off['version'], off['why_off']), (1, 'the owner ratified version 1 last'))
        for ident, version, error in [('someone-else', 2, CampaignClosed), ('earned-live-20260921', 3, ValueError)]:
            with self.subTest(ident=ident, version=version), self.assertRaises(error):
                ratify_version(guard, ident, version)
        guard.revoke_live_trading()
        with self.assertRaises(CampaignClosed):
            ratify_version(guard, 'earned-live-20260921', 2)
        self.assertEqual(self.version(guard)['why_off'], 'the grant is not active')

    def test_a_moved_money_rule_switches_version_two_off_until_the_owner_ratifies_again(self):
        guard = self.grant()
        ratify_version(guard, 'earned-live-20260921', 2)
        with patch.dict(CONSTITUTION['allocator'], {'throttle': {'halve_below': -0.4, 'restore_above': -0.2}}):
            self.assertFalse(guard.live_trading()['active'])
            self.assertEqual(self.version(guard)['version'], 1)
            guard.ratify_live_trading('earned-live-20260921')  # the run's re-ratify: version 1 again, version 2 stays off
            self.assertTrue(guard.live_trading()['active'])
            shown = self.version(guard)
            self.assertEqual(shown['version'], 1)
            self.assertIn('moved', shown['why_off'])
            self.assertEqual(ratify_version(guard, 'earned-live-20260921', 2)['version'], 2)  # only the owner
            self.assertEqual(self.version(guard)['scale_policy']['scale_tranches']['relock_share'], '-0.4')

    def test_the_owner_cli_ratifies_a_version_and_its_report_says_which(self):
        self.now[0] = time.time() - 30 * DAY  # the CLI's guard reads the wall clock: the grant starts before it
        self.grant()
        from league.tests.test_phase1 import policy as campaign_policy
        out = io.StringIO()
        with patch('league.campaigns.load_policy', return_value=campaign_policy()), patch('sys.stdout', out):
            live_trading.main(['--root', str(self.root), '--ratify', 'earned-live-20260921', '--grant-version', '2'])
        shown = json.loads(out.getvalue())
        self.assertTrue(shown['live_trading']['active'])
        self.assertEqual(shown['grant_version']['version'], 2)
        self.assertNotIn('scale_policy', shown['grant_version'])
        with self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
            live_trading.main(['--root', str(self.root), '--grant-version', '2'])


# ------------------------------------------------------------------ the report
class ScaleReport(PhaseCase):
    def fixture(self, value=None, *, ledger=None):
        path = self.root / 'allocator-board.json'
        path.write_text(json.dumps(board() if value is None else value), encoding='utf-8')
        if ledger:
            write_ledger(self.root / 'ledger.sqlite', **ledger)
        return path

    def test_the_t0_board_alone(self):
        self.fixture()
        shown = scale_report(self.root, now=NOW)
        kalshi, alpaca = shown['venues']['kalshi'], shown['venues']['alpaca']
        self.assertEqual((kalshi['envelope_usd'], kalshi['committed_usd'], kalshi['capacity_used_usd']), ('546.83', '109.23', '30.00'))
        self.assertAlmostEqual(kalshi['capacity_share_today'], 30 / 546.83)
        self.assertEqual([(f['family'], f['members_real'], f['stake_usd'], f['multiple'], f['usd']) for f in kalshi['families']],
                         [('sports-central-run-under', 1, '30', 1, '30.00')])
        self.assertEqual(kalshi['families_not_proven'], 1)
        self.assertEqual((alpaca['envelope_usd'], alpaca['committed_usd'], alpaca['capacity_used_usd']), ('500', '230.94', '0.00'))
        self.assertFalse(kalshi['decision']['unlock'])
        self.assertEqual(kalshi['capacity_gap_today_usd'], '352.78')
        self.assertIn('no ledger', shown['history']['ledger'])
        self.assertIn('keeps no history', shown['history']['board'])
        self.assertEqual(shown['grant']['why_off'], f"no campaign database at {self.root / 'campaigns.sqlite'}")
        self.assertEqual(shown['ratify'], 'python scripts/live_trading.py --ratify <grant-id> --grant-version 2')

    def test_the_t0_board_with_three_days_of_ledger_text_and_json(self):
        start = grants.midnight('2026-09-21')
        self.fixture(ledger={'family_rows': [(start + 1800, family(members=1)),
                                             (start + 1900, family('unproven', 3, '10', name='weather-favorites'))],
                             'pnl': rising(), 'equity': lambda t: {'kalshi': '560.20', 'alpaca': '498.00'}})
        out = io.StringIO()
        with patch('sys.stdout', out), patch('league.live_trading.time.time', return_value=NOW):
            live_trading.main(['--root', str(self.root), '--scale-report', '--json'])
        shown = json.loads(out.getvalue())
        kalshi = shown['venues']['kalshi']
        self.assertEqual([(d['day'], d['capacity_used_usd'], d['readings'], d['pnl_usd']) for d in kalshi['days']],
                         [('2026-09-22', '30.00', 24, '2.00'), ('2026-09-23', '30.00', 24, '2.00'), ('2026-09-24', '30.00', 24, '2.00'),
                          ('2026-09-25', '30.00', 7, '0.58')])
        self.assertEqual(kalshi['window_pnl_usd'], '6.00')
        self.assertEqual((kalshi['funded_usd'], kalshi['deposit_left_usd']), ('560.20', '13.37'))
        self.assertEqual(kalshi['funded_basis'], 'floor.mark at 2026-09-25T06:00:00Z')
        self.assertEqual([f['condition'] for f in kalshi['decision']['fails']], ['capacity'] * 3)  # P&L passes, capacity does not
        self.assertEqual(shown['history']['ledger']['rows']['family.record'], 2)
        text = io.StringIO()
        with patch('sys.stdout', text), patch('league.live_trading.time.time', return_value=NOW):
            live_trading.main(['--root', str(self.root), '--scale-report'])
        text = text.getvalue()
        for line in ('envelope $546.83 (base $546.83 + tranches $0.00); committed $109.23 (20.0%)',
                     'sports-central-run-under (proven): 1 x $30.00 x 1 = $30.00',
                     "capacity used today (the board's families): $30.00 = 5.5% of the envelope",
                     '2026-09-24: capacity $30.00 = 5.5% (lowest of 24 readings); real P&L $2.00',
                     'real P&L over 2026-09-22..2026-09-24: $6.00',
                     'TODAY: no tranche. capacity used 5.5% < 70% on 2026-09-22',
                     "deposit that would put it to work: $0.00 (none until proven capacity reaches $382.78 on 3 straight UTC days, "
                     "$352.78 more than today's $30.00",
                     'python scripts/live_trading.py --ratify <grant-id> --grant-version 2'):
            self.assertIn(line, text)
        self.assertEqual(text.strip(), render_scale_report(scale_report(self.root, now=NOW)).strip())

    def test_evidence_that_passes_names_the_tranche_and_the_deposit(self):
        start = grants.midnight('2026-09-21')
        many = family(members=13)  # 13 x $30 = $390 = 71.3% of $546.83
        value = board({'kalshi': {'sports-central-run-under': dict(many)}})
        self.fixture(value, ledger={'family_rows': [(start + 1800, many)], 'pnl': rising(),
                                    'equity': lambda t: {'kalshi': '746.83', 'alpaca': '500'}})
        shown = scale_report(self.root, now=NOW)
        decision = shown['venues']['kalshi']['decision']
        self.assertTrue(decision['unlock'])
        self.assertEqual((decision['tranche_usd'], decision['deposit_left_usd'], decision['deposit_to_work_usd']),
                         ('200.00', '200.00', '73.41'))
        text = render_scale_report(shown)
        self.assertIn('TODAY: the evidence unlocks a tranche of $200.00 (full tranche $273.41).', text)
        self.assertIn('deposit that would put it to work: $73.41', text)
        funded = scale_report(self.root, now=NOW, funded={'kalshi': '2000'})['venues']['kalshi']
        self.assertEqual((funded['funded_basis'], funded['decision']['tranche_usd']), ('given (--funded)', '273.41'))

    def test_a_ratified_version_two_replays_its_tranches_from_the_ratification(self):
        from league.tests.test_live_trading import research_policy
        start = grants.midnight('2026-09-21')
        many = family(members=13)
        self.fixture(board({'kalshi': {'sports-central-run-under': dict(many)}}),
                     ledger={'family_rows': [(start + 1800, many)], 'pnl': rising(),
                             'equity': lambda t: {'kalshi': '1546.83', 'alpaca': '500'}})
        self.now[0] = start
        guard = self.budget()
        burst = guard.activate_burst('original-night', research_policy())
        self.now[0] = max(burst['ends'] + 3600, grants.midnight('2026-09-24') + 12 * 3600)
        guard.activate_live_trading('earned-live-20260921', LIVE_CAPITAL)
        ratify_version(guard, 'earned-live-20260921', 2)
        ratified = self.now[0]
        shown = scale_report(self.root, now=NOW)
        self.assertEqual((shown['grant']['version'], shown['grant']['id']), (2, 'earned-live-20260921'))
        kalshi = shown['venues']['kalshi']
        self.assertEqual(shown['venues']['kalshi']['decision']['at'], '2026-09-25T00:00:00Z')
        # At the ratification (Sept 24, 12:00Z) the window was Sept 21-23, and Sept 21 had no proven family until 00:30Z
        # and no mark pass before it: no tranche. At 00:00Z Sept 25 the window is Sept 22-24, and each day passes.
        self.assertEqual([(d['at'], d['unlock']) for d in kalshi['decisions']],
                         [('2026-09-24T12:00:00Z', False), ('2026-09-25T00:00:00Z', True)])
        self.assertEqual(kalshi['decisions'][0]['fails'], ['capacity used 0.0% < 70% on 2026-09-21 ($0.00 of $546.83)',
                                                           "the venue's real P&L is unmeasured on 2026-09-21"])
        self.assertEqual(ratified, grants.midnight('2026-09-24') + 12 * 3600)
        self.assertEqual([t['unlocked_at'] for t in kalshi['tranches']], ['2026-09-25T00:00:00Z'])
        self.assertEqual((kalshi['unlocked_usd'], kalshi['envelope_usd']), ('273.41', '820.24'))
        self.assertIn('Version 2 (scale_tranches) is RATIFIED', render_scale_report(shown))
        self.assertEqual(shown['ratify'], 'python scripts/live_trading.py --ratify earned-live-20260921 --grant-version 2')

    def test_the_report_writes_nothing(self):
        start = grants.midnight('2026-09-21')
        path = self.fixture(ledger={'family_rows': [(start + 1800, family())], 'pnl': rising()})
        from league.tests.test_live_trading import research_policy
        guard = self.budget()
        burst = guard.activate_burst('original-night', research_policy())
        self.now[0] = burst['ends'] + 3600
        guard.activate_live_trading('earned-live-20260921', LIVE_CAPITAL)
        guard.close()
        files = [path, self.root / 'ledger.sqlite', self.root / 'campaigns.sqlite']
        before = {p: p.read_bytes() for p in files}
        scale_report(self.root, now=NOW)
        self.assertEqual({p: p.read_bytes() for p in files}, before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.suffix == '.sqlite'), ['campaigns.sqlite', 'ledger.sqlite'])


def k2_row(name='sports-central-run-under', estimate=(.96, .94, .91, .90), floor=(.80, .70, .50, .30), halves='>256x'):
    """One family of the K2 study's JSON (`scripts/kalshi_capacity.py --json`, origin/k2/capacity 1d8a1fb)."""
    return {'family': name, 'state': 'proven', 'proven': True, 'n': 26, 'mean_log': 0.12, 'stake_usd': '30', 'size_usd': 6.0,
            'edge_per_dollar': 0.27, 'edge_basis': 'board', 'markets_per_day': 19.3, 'halves_at': halves, 'halves_at_floor': '4.6x',
            'curve': {f'{k}x': {'size_usd': 6.0 * k, 'fill_rate': e, 'fill_floor': f, 'maker_fill': e, 'taker_fill': None,
                                'usd_per_day': None if e is None else round(19.3 * e * k * 6 * .27, 2), 'stake_usd': 30.0 * k, 'members': 3,
                                'envelope_usd': 90.0 * k} for k, e, f in zip((1, 2, 4, 8), estimate, floor)}}


def k2_study(*rows):
    return {'since': '2026-09-18T06:00:00Z', 'until': '2026-09-25T06:00:00Z', 'box_now': '2026-09-25T06:10:00Z',
            'envelope': {'capital_usd': '546.83', 'committed_usd': '109.23'}, 'families': list(rows), 'totals': {}}


class CapacityStudy(PhaseCase):
    def test_the_k2_curve_gives_m_star_as_the_smaller_of_its_estimate_and_floor(self):
        curves = grants.study_curves(k2_study(k2_row(), k2_row('no-curve', (None, None, None, None), (None,) * 4),
                                              {'family': 'empty', 'curve': {}}))
        self.assertEqual(sorted(curves), ['sports-central-run-under'])  # a study without a 1x rate leaves the board's record
        line = grants.family_capacity('sports-central-run-under', family(members=1), '0.5', curves)
        self.assertEqual((line['multiple'], line['usd'], line['multiple_basis']),
                         (4, '120.00', 'K2 capacity study (the smaller of its estimate and floor)'))  # estimate 8x; floor halves at 8x
        wide = grants.study_curves(k2_study(k2_row(floor=(.80, .78, .75, .70))))
        self.assertEqual(grants.family_capacity('sports-central-run-under', family(), '0.5', wide)['multiple'], 8)
        fallback = grants.family_capacity('other', family(name='other'), '0.5', curves)
        self.assertEqual((fallback['multiple'], fallback['multiple_basis']), (1, 'board capacity record'))

    def test_the_report_reads_the_study_for_kalshi_and_says_so(self):
        path = self.root / 'allocator-board.json'
        path.write_text(json.dumps(board()), encoding='utf-8')
        study_path = self.root / 'k2.json'
        study_path.write_text(json.dumps(k2_study(k2_row(floor=(.80, .78, .75, .70)))), encoding='utf-8')
        out = io.StringIO()
        with patch('sys.stdout', out), patch('league.live_trading.time.time', return_value=NOW):
            live_trading.main(['--root', str(self.root), '--scale-report', '--json', '--capacity-json', str(study_path)])
        shown = json.loads(out.getvalue())
        kalshi = shown['venues']['kalshi']
        # The rule's reading is the family records' (1 x $30 x 1); K2's curve is a what-if beside it (1 x $30 x 8).
        self.assertEqual((kalshi['capacity_used_usd'], kalshi['families'][0]['multiple']), ('30.00', 1))
        what_if = kalshi['what_if_study']
        self.assertEqual((what_if['capacity_used_usd'], what_if['families'][0]['multiple'], what_if['unlock']), ('240.00', 8, False))
        self.assertEqual(what_if['families'][0]['multiple_basis'], 'K2 capacity study (the smaller of its estimate and floor)')
        self.assertIn("K2's capacity study", shown['history']['curves'])
        self.assertIn('WHAT-IF', shown['history']['curves'])
        text = render_scale_report(shown)
        self.assertIn("WHAT-IF on K2's curves (the rule does not read the study; it never decides a tranche or a deposit here):", text)
        self.assertIn('sports-central-run-under: 1 x $30.00 x 8 = $240.00  [curve 2x 0.94, 4x 0.91, 8x 0.90', text)
        self.assertIn('m* from the board capacity record: fill 1.00 at 1x', text)
        self.assertIn('never unlocks a tranche alone', text)
        self.assertIn('edge +0.27', text)
        without = scale_report(self.root, now=NOW)['venues']['kalshi']
        self.assertEqual((without['capacity_used_usd'], without['families'][0]['multiple_basis']), ('30.00', 'board capacity record'))

    def test_capacity_alone_never_unlocks_a_tranche(self):
        start = grants.midnight('2026-09-21')
        many = family(members=13)  # 13 x $30 x 8 = $3,120: 570% of the envelope
        path = self.root / 'allocator-board.json'
        path.write_text(json.dumps(board({'kalshi': {'sports-central-run-under': dict(many)}})), encoding='utf-8')
        falling = lambda t: {'kalshi': {'a1': (Decimal('30') - Decimal(str((t - start) / DAY)).quantize(Decimal('.01')), Decimal('30'))}}
        write_ledger(self.root / 'ledger.sqlite', family_rows=[(start + 1800, many)], pnl=falling,
                     equity=lambda t: {'kalshi': '5000', 'alpaca': '500'})
        study = live_trading.capacity_study(k2_study(k2_row(floor=(.80, .78, .75, .70))), 'k2.json')
        kalshi = scale_report(self.root, now=NOW, study=study)['venues']['kalshi']
        self.assertEqual(kalshi['days'][0]['capacity_used_usd'], '390.00')  # 71.3% on the records: capacity passes
        self.assertEqual(kalshi['what_if_study']['capacity_used_usd'], '3120.00')
        self.assertFalse(kalshi['decision']['unlock'])
        self.assertEqual([(f['condition'], f['pnl_usd']) for f in kalshi['decision']['fails']], [('pnl', '-3.00')])
        self.assertFalse(kalshi['what_if_study']['unlock'])


class OwnerScript(TestCase):
    def test_the_scale_report_runs_on_the_box_read_only_and_on_a_copied_state_dir_locally(self):
        from scripts.live_trading import main as owner_command
        result = type('R', (), {'stdout': 'report', 'check': lambda self: None})()
        with patch('scripts.live_trading.client') as api, patch('scripts.live_trading.read_state', return_value={'box_id': 'fake'}), \
                patch('sys.stdout', new_callable=io.StringIO):
            api.return_value.exec.return_value = result
            owner_command(['--scale-report', '--json', '--funded', 'kalshi=1046.83'])
            self.assertEqual(api.return_value.exec.call_count, 1)  # no restart
            command = api.return_value.exec.call_args.args[1]
            self.assertEqual(command[-5:], ['--root', '/workspace/state', '--scale-report', '--json', '--funded=kalshi=1046.83'])
            api.return_value.exec.return_value = type('R', (), {'stdout': json.dumps({'live_trading': {'active': True}}),
                                                               'check': lambda self: None})()
            owner_command(['--ratify', 'earned-live-20260921', '--grant-version', '2'])
            ratify = api.return_value.exec.call_args_list[1].args[1]
            self.assertEqual(ratify[-4:], ['--ratify', 'earned-live-20260921', '--grant-version', '2'])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        Path(tmp.name, 'allocator-board.json').write_text(json.dumps(board()), encoding='utf-8')
        out = io.StringIO()
        with patch('scripts.live_trading.client', side_effect=AssertionError('no box')), patch('sys.stdout', out):
            owner_command(['--scale-report', '--root', tmp.name, '--json'])
        self.assertEqual(json.loads(out.getvalue())['venues']['kalshi']['capacity_used_usd'], '30.00')
        study = Path(tmp.name, 'k2.json')
        study.write_text(json.dumps(k2_study(k2_row())), encoding='utf-8')
        out = io.StringIO()
        with patch('scripts.live_trading.client', side_effect=AssertionError('no box')), patch('sys.stdout', out):
            owner_command(['--scale-report', '--root', tmp.name, '--json', '--capacity-json', str(study)])
        self.assertEqual(json.loads(out.getvalue())['venues']['kalshi']['what_if_study']['families'][0]['multiple'], 4)
        with patch('scripts.live_trading.client') as api, patch('scripts.live_trading.read_state', return_value={'box_id': 'fake'}), \
                patch('sys.stdout', new_callable=io.StringIO):
            api.return_value.exec.return_value = result
            owner_command(['--scale-report', '--capacity-json', str(study)])
            sent = api.return_value.exec.call_args.args[1][-1]
        self.assertTrue(sent.startswith('--capacity-curves='))
        reduced = json.loads(sent.split('=', 1)[1])
        self.assertEqual((reduced['reduced'], sorted(reduced['families'])), ('k5', ['sports-central-run-under']))
        self.assertEqual(live_trading.capacity_study(reduced, 'x'), reduced)
        for wrong in (['--grant-version', '2'], ['--json'], ['--ratify', 'x', '--scale-report'], ['--capacity-json', str(study)]):
            with self.subTest(wrong=wrong), self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
                owner_command(wrong)


class ScaleNeverBreaksTheGrant(PhaseCase):
    def test_a_failing_scale_rule_reads_as_off_and_leaves_the_owners_report_whole(self):
        guard = Ratification.grant(self)
        with patch('league.grants.scale_tranches', side_effect=KeyError('halve_below')):
            shown = live_trading.report(guard)
            self.assertTrue(shown['live_trading']['active'])
            self.assertEqual((shown['grant_version']['version'], shown['grant_version']['proposed_digest']), (1, None))
        with patch('league.live_trading.grant_version', side_effect=RuntimeError('boom')):
            self.assertIn('RuntimeError', live_trading.report(guard)['grant_version']['error'])


class NothingElseReadsIt(TestCase):
    def test_no_module_but_the_grant_and_its_owner_command_names_the_scale_rule(self):
        """Switched off in code as well as in state: the House, the allocator, the book and every other module name
        neither version 2 nor its reader, so a ratification changes the report alone until its wiring is reviewed."""
        names = re.compile(r'scale_tranches|grant_version|live_grant_versions|scale_state|scale_unlocked|base_envelope|'
                           r'ratify_version|SCALE_VERSION|policy\([^)]*version\s*=')
        allowed = {'league/grants.py', 'league/live_trading.py', 'scripts/live_trading.py'}
        found = []
        for path in [*REPO.glob('league/**/*.py'), *REPO.glob('scripts/**/*.py'), *REPO.glob('ltcm/**/*.py')]:
            rel = path.relative_to(REPO).as_posix()
            if rel in allowed or rel.startswith('league/tests/'):
                continue
            if names.search(path.read_text(encoding='utf-8', errors='replace')):
                found.append(rel)
        self.assertEqual(found, [])


# ------------------------------------------------------------------ the adversarial review of #313 (Sept 25, 2026)
ID = 'earned-live-20260921'


class ReratificationKeepsWithdrawals(TestCase):
    """A routine re-ratification (every money-rule change switches version 2 off until the owner ratifies it again) used to
    restart the replay: a tranche withdrawn at 03:00Z was unlocked again at 06:00Z on the same window of days that
    preceded the loss. The grant's earlier version-2 intervals are replayed first."""

    def setUp(self):
        self.window = {n: day(n) for n in ('2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25', '2026-09-26', '2026-09-27',
                                           '2026-09-28', '2026-09-29')}
        self.base = [(grants.midnight('2026-09-21') + h * 3600.0, Decimal('546.83')) for h in range(24 * 10)]
        self.funded = [(grants.midnight('2026-09-21'), Decimal('1546.83'))]
        self.r1 = grants.midnight('2026-09-25') + 3600

    def pnl(self, *moves):
        out = [(grants.midnight('2026-09-21') + h * 3600.0, Decimal('10')) for h in range(24 * 4 + 1)]
        return out + [(self.r1 + dt, Decimal(v)) for dt, v in moves]

    def test_a_withdrawal_in_an_earlier_interval_holds_the_next_tranche_a_whole_window(self):
        pnl = self.pnl((7200, '-90'))  # withdrawn at 03:00Z
        alone = replay(BLOCK, self.window, pnl=pnl, funded=self.funded, envelopes=self.base, ratified_at=self.r1 + 5 * 3600,
                       now=self.r1 + 6 * 3600)
        self.assertEqual(alone['unlocked_usd'], '273.41')  # the defect, as it stood: the re-ratification forgot the loss
        state = replay(BLOCK, self.window, pnl=pnl, funded=self.funded, envelopes=self.base, ratified_at=self.r1 + 5 * 3600,
                       now=grants.midnight('2026-09-29') + 60, earlier=[(self.r1, self.r1 + 3 * 3600)])
        self.assertEqual([(t['unlocked_at'], t['relocked_at']) for t in state['tranches']],
                         [('2026-09-25T01:00:00Z', '2026-09-25T03:00:00Z'), ('2026-09-29T00:00:00Z', None)])
        self.assertEqual([(d['at'], d['unlock']) for d in state['decisions']],
                         [('2026-09-25T01:00:00Z', True), ('2026-09-25T06:00:00Z', False), ('2026-09-26T00:00:00Z', False),
                          ('2026-09-27T00:00:00Z', False), ('2026-09-28T00:00:00Z', False), ('2026-09-29T00:00:00Z', True)])
        self.assertIn('withdrawn on 2026-09-25', state['decisions'][1]['fails'][0]['text'])

    def test_a_tranche_live_when_version_two_went_off_ends_and_its_line_is_watched_until_the_next_ratification(self):
        earlier = [(self.r1, self.r1 + 3600)]  # a money rule moved at 02:00Z
        gap_loss = replay(BLOCK, self.window, pnl=self.pnl((7200, '-90')), funded=self.funded, envelopes=self.base,
                          ratified_at=self.r1 + 5 * 3600, now=self.r1 + 6 * 3600, earlier=earlier)
        first = gap_loss['tranches'][0]
        self.assertEqual((first['switched_off_at'], first['relocked_at']), ('2026-09-25T02:00:00Z', '2026-09-25T03:00:00Z'))
        self.assertEqual((len(gap_loss['tranches']), gap_loss['unlocked_usd']), (1, '0.00'))  # the loss in the gap holds it
        calm = replay(BLOCK, self.window, pnl=self.pnl((7200, '5')), funded=self.funded, envelopes=self.base,
                      ratified_at=self.r1 + 5 * 3600, now=self.r1 + 6 * 3600, earlier=earlier)
        self.assertEqual([(t['switched_off_at'], t['relocked_at']) for t in calm['tranches']],
                         [('2026-09-25T02:00:00Z', None), (None, None)])  # ended, not restored; the rule re-earned it
        self.assertEqual(calm['unlocked_usd'], '273.41')
        self.assertIsNone(calm['tranches'][0]['pnl_since_usd'])
        later = replay(BLOCK, self.window, pnl=self.pnl((5 * 3600 + 60, '-90')), funded=self.funded, envelopes=self.base,
                       ratified_at=self.r1 + 5 * 3600, now=self.r1 + 6 * 3600, earlier=earlier)
        self.assertEqual([t['relocked_at'] for t in later['tranches']], [None, '2026-09-25T06:01:00Z'])  # only the live one


class ReviewRatification(PhaseCase):
    grant = Ratification.grant

    def test_the_grant_carries_its_earlier_version_two_intervals_into_the_report(self):
        start = grants.midnight('2026-09-20')
        many = family(members=13)  # $390 = 71.3% of $546.83

        def pnl(t):  # +$2 a day, then -$100 at 03:00Z Sept 24
            value = Decimal('30') + Decimal(2) * Decimal(str((t - start) / DAY)).quantize(Decimal('.01'))
            return {'kalshi': {'a1': (value - (100 if t >= grants.midnight('2026-09-24') + 3 * 3600 else 0), Decimal('30'))}}
        board_path = self.root / 'allocator-board.json'
        board_path.write_text(json.dumps(board({'kalshi': {'sports-central-run-under': dict(many)}})), encoding='utf-8')
        write_ledger(self.root / 'ledger.sqlite', family_rows=[(start - DAY, many)], pnl=pnl, start=start,
                     equity=lambda t: {'kalshi': '1546.83', 'alpaca': '500'})
        from league.tests.test_live_trading import research_policy
        self.now[0] = start
        guard = self.budget()
        burst = guard.activate_burst('original-night', research_policy())
        self.assertLess(burst['ends'], grants.midnight('2026-09-24'))
        self.now[0] = grants.midnight('2026-09-24') + 3600
        guard.activate_live_trading(ID, LIVE_CAPITAL)
        ratify_version(guard, ID, 2)  # 01:00Z: the window Sept 21-23 passes; a tranche unlocks
        first = scale_report(self.root, now=grants.midnight('2026-09-24') + 2 * 3600)['venues']['kalshi']
        self.assertEqual([t['unlocked_at'] for t in first['tranches']], ['2026-09-24T01:00:00Z'])
        with patch.dict(CONSTITUTION['allocator'], {'throttle': {'halve_below': -0.4, 'restore_above': -0.2}}):
            self.now[0] = grants.midnight('2026-09-24') + 4 * 3600
            guard.ratify_live_trading(ID)  # a run's re-pin after a promotion: version 2 goes off
            self.now[0] = grants.midnight('2026-09-24') + 5 * 3600
            shown = ratify_version(guard, ID, 2)  # the owner switches it on again
            self.assertEqual([x[:2] for x in shown['earlier']],
                             [[grants.midnight('2026-09-24') + 3600, grants.midnight('2026-09-24') + 4 * 3600]])
            self.assertEqual(shown['earlier'][0][2]['relock_share'], '-0.3')  # the block ratified then
            again = scale_report(self.root, now=grants.midnight('2026-09-24') + 6 * 3600)['venues']['kalshi']
        # -$100 crosses the line ratified THEN, -0.30 x $273.41 = -$82.02, at 03:00Z (not the moved -0.40 x $273.41 =
        # -$109.36): the re-ratification at 05:00Z keeps the withdrawal, and the window Sept 21-23 -- the days before the
        # loss -- unlocks nothing again.
        self.assertEqual([(t['relocked_at'], t['switched_off_at']) for t in again['tranches']], [('2026-09-24T03:00:00Z', None)])
        self.assertEqual([(d['at'], d['unlock']) for d in again['decisions']],
                         [('2026-09-24T01:00:00Z', True), ('2026-09-24T05:00:00Z', False)])
        self.assertIn('a tranche was withdrawn on 2026-09-24', again['decisions'][1]['fails'][0])
        self.assertEqual(again['unlocked_usd'], '0.00')
        self.assertEqual(again['tranches'][0]['relock_line_usd'], '-82.023')

    def test_a_fault_in_the_scale_rule_fails_the_owners_ratify_before_anything_is_written(self):
        guard = self.grant()
        stored = guard.db.execute('SELECT policy FROM live_trading').fetchone()[0]
        with patch.dict(CONSTITUTION['allocator'], {'throttle': {'halve_below': -0.4, 'restore_above': -0.2}}), \
                patch('league.grants.scale_tranches', side_effect=KeyError('boom')), self.assertRaises(KeyError):
            ratify_version(guard, ID, 2)
        self.assertEqual(guard.db.execute('SELECT policy FROM live_trading').fetchone()[0], stored)  # no re-pin
        self.assertEqual(guard.db.execute('SELECT COUNT(*) FROM live_ratifications').fetchone()[0], 0)
        self.assertIsNone(guard.db.execute("SELECT name FROM sqlite_master WHERE name='live_grant_versions'").fetchone())


class ReportOnTheRulesReading(PhaseCase):
    def fixture(self, members, **ledger):
        start = grants.midnight('2026-09-21')
        row = family(members=members)
        (self.root / 'allocator-board.json').write_text(json.dumps(board({'kalshi': {'sports-central-run-under': dict(row)}})),
                                                        encoding='utf-8')
        write_ledger(self.root / 'ledger.sqlite', family_rows=[(start - DAY, row)], pnl=rising(), start=start - DAY,
                     **({'equity': lambda t: {'kalshi': '1546.83', 'alpaca': '500'}} | ledger))

    def test_k2s_curves_never_decide_the_tranche_or_the_deposit(self):
        self.fixture(2)  # 2 x $30 x 1 = $60 on the records (11.0%); x 8 on K2's curves = $480 (87.8%)
        study = live_trading.capacity_study(k2_study(k2_row(floor=(.80, .78, .75, .70))), 'k2.json')
        shown = scale_report(self.root, now=NOW, study=study)
        kalshi = shown['venues']['kalshi']
        self.assertFalse(kalshi['decision']['unlock'])
        self.assertEqual({f['condition'] for f in kalshi['decision']['fails']}, {'capacity'})
        self.assertEqual((kalshi['what_if_study']['unlock'], kalshi['what_if_study']['tranche_usd']), (True, '273.41'))
        text = render_scale_report(shown)
        self.assertIn('TODAY: no tranche. capacity used 11.0% < 70% on 2026-09-22', text)
        self.assertIn('deposit that would put it to work: $0.00 (none until proven capacity reaches $382.78', text)
        self.assertIn('on those curves the evidence would unlock $273.41.', text)
        self.assertNotIn('TODAY: the evidence unlocks', text)

    def test_unread_equity_names_no_deposit(self):
        self.fixture(13, equity=lambda t: {})
        text = render_scale_report(scale_report(self.root, now=NOW))
        self.assertIn('TODAY: no tranche. the account equity is unread (no floor.mark).', text)
        self.assertIn('deposit that would put it to work: n/a (the account equity is unread: no deposit is named)', text)

    def test_an_incomplete_last_mark_pass_is_left_out(self):
        self.fixture(13)
        ledger = Ledger(self.root / 'ledger.sqlite')
        ledger.append('book.mark', {'book': 'kalshi', 'equity': '-500', 'staked': '30', 'real_money': True, 'cash': '0',
                                    'realized': '0', 'fees': '0', 'holdings': 0}, agent='a1', at=stamp(NOW + 30))
        ledger.close()
        rows = live_trading._LedgerRows(self.root / 'ledger.sqlite')
        try:
            series = rows.pnl(['kalshi'], NOW - DAY, NOW + 60)['kalshi']
        finally:
            rows.close()
        self.assertEqual(series[-1][0], grants.midnight(TODAY) + 6 * 3600)  # the 06:00Z pass: one of two rows at 06:00:30 is not P
        self.assertEqual(scale_report(self.root, now=NOW + 60)['venues']['kalshi']['pnl_window_to_now_usd'],
                         scale_report(self.root, now=NOW)['venues']['kalshi']['pnl_window_to_now_usd'])

    def test_a_tranche_the_allocator_records_is_never_read_as_base(self):
        self.assertEqual(live_trading.base_envelope({'capital_usd': '820.24', 'unlocked_usd': '273.41'}), Decimal('546.83'))
        self.assertEqual(live_trading.base_envelope({'capital_usd': '546.83'}), Decimal('546.83'))
        self.assertIsNone(live_trading.base_envelope({'committed_usd': '1'}))
        value = board({'kalshi': {'sports-central-run-under': family(members=13)}}, kalshi=('820.24', '109.23'))
        value['envelope']['kalshi']['unlocked_usd'] = '273.41'
        (self.root / 'allocator-board.json').write_text(json.dumps(value), encoding='utf-8')
        kalshi = scale_report(self.root, now=NOW)['venues']['kalshi']
        self.assertEqual((kalshi['base_envelope_usd'], kalshi['envelope_usd']), ('546.83', '546.83'))

    def test_funded_must_be_a_venue_and_a_finite_amount(self):
        self.fixture(1)
        for wrong in ('kalshi=NaN', 'kalshi=Infinity', 'kalshi=-1', 'kalhsi=100', 'kalshi'):
            with self.subTest(wrong=wrong), self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
                live_trading.main(['--root', str(self.root), '--scale-report', '--funded', wrong])


class AllocatorLine(PhaseCase):
    """`scale_unlocked`, the one reading the allocator's line is to take (forward-first's `Allocator.grant_capital`, after
    its Deploy B): $0 and no read while version 2 is not in force, $0 on any failure, else the ratified rule's tranches."""

    def setUp(self):
        super().setUp()
        live_trading._UNLOCKED_CACHE.clear()
        self.addCleanup(live_trading._UNLOCKED_CACHE.clear)

    def ratified(self, *, version):
        from league.tests.test_live_trading import research_policy
        start = grants.midnight('2026-09-21')
        many = family(members=13)
        (self.root / 'allocator-board.json').write_text(json.dumps(board({'kalshi': {'sports-central-run-under': dict(many)}})),
                                                        encoding='utf-8')
        write_ledger(self.root / 'ledger.sqlite', family_rows=[(start + 1800, many)], pnl=rising(),
                     equity=lambda t: {'kalshi': '1546.83', 'alpaca': '500'})
        self.now[0] = start
        guard = self.budget()
        burst = guard.activate_burst('original-night', research_policy())
        self.now[0] = max(burst['ends'] + 3600, grants.midnight('2026-09-24') + 12 * 3600)
        guard.activate_live_trading(ID, LIVE_CAPITAL)
        if version:
            ratify_version(guard, ID, version)
        guard.close()

    def test_unratified_the_line_adds_nothing_and_reads_nothing(self):
        self.ratified(version=None)
        with patch('league.live_trading.scale_state') as state:
            self.assertEqual(live_trading.scale_unlocked(self.root, 'kalshi', now=NOW), Decimal(0))
        state.assert_not_called()
        guard = self.budget()
        ratify_version(guard, ID, 2)
        ratify_version(guard, ID, 1)  # switched off again
        guard.close()
        live_trading._UNLOCKED_CACHE.clear()
        with patch('league.live_trading.scale_state') as state:
            self.assertEqual(live_trading.scale_unlocked(self.root, 'kalshi', now=NOW), Decimal(0))
        state.assert_not_called()

    def test_ratified_it_is_the_rules_tranche_and_any_failure_is_zero(self):
        self.ratified(version=2)
        unlocked = live_trading.scale_unlocked(self.root, 'kalshi', now=NOW)
        self.assertEqual(unlocked, Decimal('273.41'))
        self.assertEqual(unlocked, Decimal(scale_report(self.root, now=NOW)['venues']['kalshi']['unlocked_usd']))
        self.assertEqual(live_trading.scale_unlocked(self.root, 'alpaca', now=NOW), Decimal(0))
        with patch('league.live_trading.scale_state', side_effect=AssertionError('cached')):
            self.assertEqual(live_trading.scale_unlocked(self.root, 'kalshi', now=NOW + 299), Decimal('273.41'))
        for fault in (RuntimeError('boom'), KeyError('venues'), sqlite3_error()):
            live_trading._UNLOCKED_CACHE.clear()
            with self.subTest(fault=fault), patch('league.live_trading.scale_state', side_effect=fault) as state:
                self.assertEqual(live_trading.scale_unlocked(self.root, 'kalshi', now=NOW), Decimal(0))
                self.assertEqual(live_trading.scale_unlocked(self.root, 'kalshi', now=NOW + 1), Decimal(0))
                self.assertEqual(state.call_count, 1)  # a failing read is remembered, never retried on every envelope call
        live_trading._UNLOCKED_CACHE.clear()
        with patch('league.live_trading.scale_state', return_value={'venues': {'kalshi': {'unlocked_usd': 'NaN'}}}):
            self.assertEqual(live_trading.scale_unlocked(self.root, 'kalshi', now=NOW), Decimal(0))
        live_trading._UNLOCKED_CACHE.clear()
        (self.root / 'ledger.sqlite').rename(self.root / 'ledger.moved')
        (self.root / 'allocator-board.json').unlink()
        self.assertEqual(live_trading.scale_unlocked(self.root, 'kalshi', now=NOW), Decimal(0))  # no board: $0, not a guess


def sqlite3_error():
    import sqlite3
    return sqlite3.OperationalError('database is locked')


class GrantsAreProtected(TestCase):
    def test_the_scale_rules_arithmetic_changes_only_by_the_owners_deploy(self):
        from league.ci import FORBIDDEN
        self.assertIn('league/grants.py', FORBIDDEN)
        self.assertIn('league/live_trading.py', FORBIDDEN)
