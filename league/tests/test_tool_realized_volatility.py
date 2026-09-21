"""Known-value and point-in-time boundary tests for realized volatility."""

import math
import unittest
from datetime import datetime, timedelta

from league.tools.realized_volatility import realized_volatility


START = '2026-09-21T00:00:00Z'
END = '2026-09-21T00:15:00Z'


def make_bars(minutes, prices, stamp_shift=0):
    base = datetime.fromisoformat('2026-09-21T00:00:00+00:00')
    return [
        {'t': (base + timedelta(minutes=minute + stamp_shift)).isoformat(),
         'c': price}
        for minute, price in zip(minutes, prices)
    ]


def measure(bars, end=END, timestamp_at='end'):
    return realized_volatility(bars, START, end, 300,
                               timestamp_at=timestamp_at)


class TestRealizedVolatility(unittest.TestCase):
    def test_known_log_returns_without_demeaning(self):
        bars = make_bars([0, 5, 10, 15],
                         [100 * math.exp(x) for x in (0, 0.1, 0.2, 0.3)])
        result = measure(bars)
        self.assertAlmostEqual(result['realized_variance'], 0.03, places=12)
        self.assertAlmostEqual(result['realized_volatility'], math.sqrt(0.03),
                               places=12)
        self.assertEqual(result['n_returns'], 3)
        self.assertEqual(result['n_closes'], 4)
        self.assertEqual(result['covered_seconds'], 900)
        self.assertEqual(result['coverage'], 1.0)
        self.assertTrue(result['complete'])
        self.assertEqual(result['last_close_at'], '2026-09-21T00:15:00+00:00')

    def test_reversing_returns(self):
        result = measure(make_bars([0, 5, 10], [100, 200, 100]),
                         end='2026-09-21T00:10:00Z')
        self.assertAlmostEqual(result['realized_variance'],
                               2 * math.log(2) ** 2, places=12)
        self.assertTrue(result['complete'])

    def test_flat_is_zero_but_partial(self):
        result = measure(make_bars([0, 5], [100, 100]))
        self.assertEqual(result['realized_volatility'], 0.0)
        self.assertAlmostEqual(result['coverage'], 1 / 3)
        self.assertFalse(result['complete'])

    def test_empty_and_single_close_are_unknown(self):
        for bars in ([], make_bars([0], [100])):
            with self.subTest(bars=bars):
                result = measure(bars)
                self.assertIsNone(result['realized_variance'])
                self.assertIsNone(result['realized_volatility'])
                self.assertEqual(result['n_returns'], 0)
                self.assertEqual(result['coverage'], 0.0)
                self.assertFalse(result['complete'])
        self.assertIsNone(measure([])['last_close_at'])

    def test_gap_is_not_bridged_or_extrapolated(self):
        result = measure(make_bars([0, 5, 15],
                                  [100, 100 * math.exp(0.1), 1000]))
        self.assertEqual(result['n_returns'], 1)
        self.assertAlmostEqual(result['realized_variance'], 0.01, places=12)
        self.assertEqual(result['covered_seconds'], 300)
        self.assertAlmostEqual(result['coverage'], 1 / 3)
        self.assertFalse(result['complete'])

    def test_irregular_spacing_is_not_a_regular_return(self):
        result = measure(make_bars([0, 4, 10], [100, 200, 300]))
        self.assertEqual(result['n_returns'], 0)
        self.assertIsNone(result['realized_volatility'])

    def test_boundary_anchor_and_price_exclusion(self):
        bars = make_bars([-5, 0, 5, 10, 15],
                         [0, 100, 200, 100, float('nan')])
        result = measure(bars, end='2026-09-21T00:10:00Z')
        expected = measure(make_bars([0, 5, 10], [100, 200, 100]),
                           end='2026-09-21T00:10:00Z')
        self.assertEqual(result, expected)
        self.assertTrue(result['complete'])

    def test_start_and_end_stamps_are_equivalent(self):
        prices = [100, 110, 90, 100]
        end_bars = make_bars([0, 5, 10, 15], prices)
        start_bars = make_bars([0, 5, 10, 15], prices, stamp_shift=-5)
        self.assertEqual(measure(end_bars),
                         measure(start_bars, timestamp_at='start'))

    def test_partial_start_stamped_bar_is_not_visible(self):
        bars = make_bars([0, 5, 10], [100, 200, float('nan')], stamp_shift=-5)
        result = measure(bars, end='2026-09-21T00:07:30Z', timestamp_at='start')
        self.assertEqual(result['n_closes'], 2)
        self.assertEqual(result['n_returns'], 1)
        self.assertAlmostEqual(result['realized_variance'], math.log(2) ** 2)
        self.assertAlmostEqual(result['coverage'], 2 / 3)
        self.assertFalse(result['complete'])

    def test_timezone_normalization(self):
        bars = make_bars([0, 5, 10, 15], [100, 110, 90, 100])
        alternate = realized_volatility(
            bars, '2026-09-21T01:00:00+01:00',
            '2026-09-20T20:15:00-04:00', 300, timestamp_at='end')
        self.assertEqual(measure(bars), alternate)

    def test_invalid_selected_prices(self):
        for bad in (0, -1, float('nan'), float('inf'), True, '100'):
            with self.subTest(price=bad):
                with self.assertRaises(ValueError):
                    measure(make_bars([0, 5], [100, bad]))

    def test_duplicate_and_reversed_timestamps(self):
        for minutes in ([0, 0], [5, 0]):
            with self.subTest(minutes=minutes):
                with self.assertRaises(ValueError):
                    measure(make_bars(minutes, [100, 110]))

    def test_invalid_options_and_times(self):
        defaults = {'bars': [], 'window_start': START, 'as_of': END,
                    'bar_seconds': 300, 'timestamp_at': 'end'}
        invalid = [
            {'bar_seconds': 0}, {'bar_seconds': -1},
            {'bar_seconds': True}, {'bar_seconds': 300.0},
            {'timestamp_at': 'guess'}, {'as_of': START},
            {'as_of': '2026-09-20T23:00:00Z'},
            {'window_start': '2026-09-21T00:00:00'},
            {'as_of': 'not-a-time'},
            {'bars': [{'t': '2026-09-21T00:00:00', 'c': 100}]},
        ]
        for change in invalid:
            with self.subTest(change=change):
                arguments = dict(defaults)
                arguments.update(change)
                with self.assertRaises(ValueError):
                    realized_volatility(**arguments)

    def test_inputs_are_not_mutated(self):
        bars = make_bars([0, 5, 10, 15], [100, 110, 90, 100])
        original = [dict(row) for row in bars]
        measure(bars)
        self.assertEqual(bars, original)
