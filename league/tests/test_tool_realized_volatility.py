'''Known-value and point-in-time boundary tests for the volatility helper.'''

import json
import math
import unittest

from league.tools.realized_volatility import window_realized_volatility


TIMES = (
    '2026-09-21T00:00:00Z',
    '2026-09-21T00:01:00Z',
    '2026-09-21T00:02:00Z',
)
START = TIMES[0]
END = TIMES[-1]


def sample(prices=(100.0, 200.0, 100.0)):
    return [{'t': stamp, 'c': price} for stamp, price in zip(TIMES, prices)]


def estimate(rows, start=START, end=END, as_of=END, bar_seconds=60,
             timestamp_at='close'):
    return window_realized_volatility(
        rows, start, end, as_of, bar_seconds, timestamp_at=timestamp_at,
    )


class TestWindowRealizedVolatility(unittest.TestCase):
    def test_known_log_returns(self):
        result = estimate(sample())
        self.assertEqual(result['status'], 'ok')
        self.assertAlmostEqual(result['variance'], 2 * math.log(2) ** 2)
        self.assertAlmostEqual(result['volatility'], math.sqrt(2) * math.log(2))
        self.assertEqual(result['n_closes'], 3)
        self.assertEqual(result['span_seconds'], 120)
        self.assertTrue(result['complete'])

    def test_constant_prices_are_zero_not_missing(self):
        result = estimate(sample((100, 100, 100)))
        self.assertEqual(result['variance'], 0.0)
        self.assertEqual(result['volatility'], 0.0)
        self.assertTrue(result['complete'])

    def test_empty_and_single_close_are_insufficient(self):
        for rows in ([], sample((100,))):
            with self.subTest(rows=rows):
                result = estimate(rows)
                self.assertEqual(result['status'], 'insufficient')
                self.assertIsNone(result['variance'])
                self.assertIsNone(result['volatility'])
                self.assertFalse(result['complete'])
        self.assertIsNone(estimate([])['first_close_at'])

    def test_future_prices_are_not_read(self):
        rows = sample((100, 200, -1))
        result = estimate(rows, as_of='2026-09-21T00:01:30Z')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['n_closes'], 2)
        self.assertAlmostEqual(result['variance'], math.log(2) ** 2)
        self.assertEqual(result['last_close_at'], '2026-09-21T00:01:00+00:00')
        self.assertFalse(result['complete'])

    def test_as_of_before_start(self):
        result = estimate(sample(), as_of='2026-09-20T23:59:59Z')
        self.assertEqual(result['n_closes'], 0)
        self.assertEqual(result['status'], 'insufficient')

    def test_no_return_bridges_window_start(self):
        rows = [{'t': '2026-09-20T23:59:00Z', 'c': 1}] + sample()
        self.assertEqual(estimate(rows), estimate(sample()))
        partial = estimate(sample(), start=TIMES[1])
        self.assertAlmostEqual(partial['variance'], math.log(2) ** 2)
        self.assertEqual(partial['n_closes'], 2)
        self.assertTrue(partial['complete'])

    def test_window_end_caps_late_as_of(self):
        rows = sample() + [{'t': '2026-09-21T00:03:00Z', 'c': -1}]
        result = estimate(rows, as_of='2026-09-21T01:00:00Z')
        self.assertEqual(result, estimate(sample()))

    def test_open_stamps_match_equivalent_close_stamps(self):
        rows = [
            {'t': '2026-09-20T23:59:00Z', 'c': 100},
            {'t': '2026-09-21T00:00:00Z', 'c': 200},
            {'t': '2026-09-21T00:01:00Z', 'c': 100},
        ]
        self.assertEqual(estimate(rows, timestamp_at='open'), estimate(sample()))
        partial = estimate(rows, timestamp_at='open',
                           as_of='2026-09-21T00:01:59Z')
        self.assertEqual(partial['n_closes'], 2)
        self.assertAlmostEqual(partial['variance'], math.log(2) ** 2)
        self.assertFalse(partial['complete'])

    def test_missing_interval_is_not_interpolated(self):
        rows = [sample()[0], sample()[2]]
        result = estimate(rows)
        self.assertEqual(result['status'], 'gapped')
        self.assertIsNone(result['variance'])
        self.assertIsNone(result['volatility'])
        self.assertFalse(result['complete'])

    def test_missing_boundary_is_partial(self):
        result = estimate(sample()[1:])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['span_seconds'], 60)
        self.assertFalse(result['complete'])

    def test_duplicate_and_reversed_timestamps_rejected(self):
        for rows in ([sample()[0], sample()[0]], list(reversed(sample()))):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    estimate(rows)

    def test_timezone_offsets_are_equivalent(self):
        result = estimate(
            sample(), start='2026-09-20T20:00:00-04:00',
            end='2026-09-20T20:02:00-04:00',
            as_of='2026-09-20T20:02:00-04:00',
        )
        self.assertEqual(result, estimate(sample()))

    def test_invalid_times_and_window_rejected(self):
        with self.assertRaises(ValueError):
            estimate(sample(), start='2026-09-21T00:00:00')
        with self.assertRaises(ValueError):
            estimate(sample(), as_of='2026-09-21T00:02:00')
        with self.assertRaises(ValueError):
            estimate([{'t': '2026-09-21T00:00:00', 'c': 100}])
        with self.assertRaises(ValueError):
            estimate(sample(), end=START)
        with self.assertRaises(ValueError):
            estimate(sample(), start=END, end=START)
        with self.assertRaises(ValueError):
            estimate(sample(), timestamp_at='unknown')

    def test_invalid_steps_rejected(self):
        for seconds in (0, -60, 1.5, True):
            with self.subTest(seconds=seconds):
                with self.assertRaises(ValueError):
                    estimate(sample(), bar_seconds=seconds)

    def test_invalid_selected_prices_rejected(self):
        for price in (0, -1, True, '100', None,
                      float('nan'), float('inf'), -float('inf')):
            with self.subTest(price=price):
                with self.assertRaises(ValueError):
                    estimate(sample((100, price, 100)))

    def test_inputs_preserved_and_output_json_compatible(self):
        rows = sample()
        original = json.loads(json.dumps(rows))
        result = estimate(rows)
        self.assertEqual(rows, original)
        self.assertEqual(result, estimate(rows))
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
