"""Known-value and boundary tests for the pure window volatility helper."""

from datetime import datetime, timedelta, timezone
import math
import unittest

from league.tools.realized_volatility import window_volatility


START = '2026-09-21T12:00:00Z'
END = '2026-09-21T12:15:00Z'


def make_bars(closes, step=300, offset=0):
    origin = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
    return [
        {'t': (origin + timedelta(seconds=offset + index * step)).isoformat(),
         'c': close}
        for index, close in enumerate(closes)
    ]


class WindowVolatilityTests(unittest.TestCase):
    def test_known_positive_returns_are_not_demeaned(self):
        result = window_volatility(make_bars([1, 2, 4, 8]), START, END, 300)
        unit = math.log(2)
        self.assertEqual(result['n_returns'], 3)
        self.assertEqual(result['step_seconds'], 300)
        self.assertAlmostEqual(result['realized_variance'], 3 * unit * unit)
        self.assertAlmostEqual(result['realized_volatility'], math.sqrt(3) * unit)
        self.assertAlmostEqual(result['rms_return'], unit)

    def test_flat_prices_are_zero_not_missing(self):
        result = window_volatility(make_bars([100] * 4), START, END, 300)
        self.assertEqual(result['realized_variance'], 0.0)
        self.assertEqual(result['realized_volatility'], 0.0)
        self.assertEqual(result['rms_return'], 0.0)

    def test_alternating_returns_known_value(self):
        result = window_volatility(
            make_bars([1, 2, 1]), START, '2026-09-21T12:10:00Z', 300)
        self.assertEqual(result['n_returns'], 2)
        self.assertAlmostEqual(result['realized_variance'], 2 * math.log(2) ** 2)

    def test_one_minute_data_has_fifteen_returns(self):
        result = window_volatility(make_bars([1] * 16, step=60), START, END, 60)
        self.assertEqual(result['n_returns'], 15)
        self.assertEqual(result['realized_volatility'], 0.0)

    def test_outside_prices_are_excluded_and_input_is_unchanged(self):
        inside = make_bars([1, 2, 4, 8])
        bars = make_bars([-1], offset=-300) + inside + make_bars([-1], offset=1200)
        snapshot = [dict(bar) for bar in bars]
        self.assertEqual(window_volatility(bars, START, END, 300),
                         window_volatility(inside, START, END, 300))
        self.assertEqual(bars, snapshot)

    def test_equivalent_timezone_offsets(self):
        bars = make_bars([1, 2, 4, 8])
        self.assertEqual(
            window_volatility(bars, START, END, 300),
            window_volatility(bars, '2026-09-21T08:00:00-04:00',
                              '2026-09-21T08:15:00-04:00', 300))

    def test_missing_samples_and_boundaries_return_none(self):
        bars = make_bars([1, 2, 4, 8])
        for incomplete in ([], bars[:1], bars[1:], bars[:-1],
                           [bars[0], bars[2], bars[3]]):
            self.assertIsNone(window_volatility(incomplete, START, END, 300))
        prefix = window_volatility(bars[:2], START, '2026-09-21T12:05:00Z', 300)
        self.assertEqual(prefix['n_returns'], 1)

    def test_off_grid_samples_are_not_bridged(self):
        bars = make_bars([1, 2, 4, 8])
        bars[1]['t'] = '2026-09-21T12:04:00Z'
        self.assertIsNone(window_volatility(bars, START, END, 300))
        self.assertIsNone(window_volatility(make_bars([1, 2, 4, 8]),
                                           START, END, 60))

    def test_duplicate_and_reversed_selected_timestamps_raise(self):
        bars = make_bars([1, 2, 4, 8])
        for bad in (list(reversed(bars)), [bars[0], bars[1], bars[1], bars[3]]):
            with self.assertRaises(ValueError):
                window_volatility(bad, START, END, 300)

    def test_invalid_selected_closes_raise(self):
        for close in (0, -1, True, '2', None, math.inf, -math.inf, math.nan,
                      10 ** 1000):
            with self.subTest(close=close):
                with self.assertRaises(ValueError):
                    window_volatility(make_bars([1, close, 4, 8]), START, END, 300)

    def test_invalid_windows_and_steps_raise(self):
        for step in (0, -1, True, 300.0, '300'):
            with self.assertRaises(ValueError):
                window_volatility([], START, END, step)
        for end in (START, '2026-09-21T11:55:00Z', '2026-09-21T12:14:00Z'):
            with self.assertRaises(ValueError):
                window_volatility([], START, end, 300)

    def test_naive_and_malformed_timestamps_raise(self):
        for stamp in ('2026-09-21T12:00:00', 'not-a-time', None):
            with self.assertRaises(ValueError):
                window_volatility([], stamp, END, 300)
            with self.assertRaises(ValueError):
                window_volatility([{'t': stamp, 'c': 1}], START, END, 300)


if __name__ == '__main__':
    unittest.main()
