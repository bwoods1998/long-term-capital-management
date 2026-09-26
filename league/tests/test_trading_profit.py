"""Profit is the full real-options record, not a clipped roster or account movement."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from league.publish import SiteInputs, build_checkpoint
from league.trading_profit import snapshot, total

AT = '2026-09-28T15:00:00.000Z'


def position(pid, cash, qty=0, status='closed', **extra):
    return dict(pid=pid, cash=cash, qty=qty, status=status, info='{}', **extra)


class TradingProfitTest(unittest.TestCase):
    def test_empty_real_record_is_zero_and_retired_history_is_not_clipped(self):
        self.assertEqual(total([], {}), '0.00')
        self.assertEqual(total([position(i, '2.15') for i in range(200)], {}), '430.00')

    def test_remaining_value_plus_all_cash_includes_fees_and_partial_closes(self):
        # Two units bought for 200 plus 2 fees; one closed for 120 less 1 fee.
        # Remaining one is marked at 110. Total -83+110=27, not just the last unit's gain.
        rows = [position(1, '-83.00', 1, 'open'), position(2, '-5.25')]
        self.assertEqual(total(rows, {1: '110.00'}), '21.75')
        self.assertEqual(total([position(1, '98.00', 1, 'open')], {1: '-90.00'}), '8.00')

    def test_unpriced_broken_inconsistent_and_nonfinite_records_are_unknown(self):
        cases = [position(1, 1, 1, 'open'), position(1, 1, 0, 'unpriced_close'),
                 position(1, 1, 1, 'closed'), position(1, 'NaN')]
        for row in cases:
            self.assertIsNone(total([row], {}))
        row = position(1, 2, 1, 'open'); row['info'] = json.dumps({'broken': 'one leg missing'})
        self.assertIsNone(total([row], {1: 100}))
        self.assertIsNone(total([position(1, 2, 1, 'open')], {1: 'Infinity'}))

    def test_readonly_snapshot_zero_before_live_and_preserves_all_closed_history(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(snapshot(directory, None, at=AT)['pnl_usd'])
            self.assertEqual(snapshot(directory, None, at=AT, never_traded=True)['pnl_usd'], '0.00')
            path = Path(directory) / 'live.sqlite'
            db = sqlite3.connect(path)
            db.executescript('CREATE TABLE positions(pid,qty,entry,cash,status,info); CREATE TABLE orders(status);')
            db.executemany('INSERT INTO positions VALUES (?,0,1,2.5,\'closed\',\'{}\')', [(i,) for i in range(200)])
            db.commit()
            before = path.read_bytes()
            self.assertEqual(snapshot(directory, None, at=AT), {'as_of': AT, 'pnl_usd': '500.00'})
            self.assertEqual(path.read_bytes(), before)
            db.execute("INSERT INTO orders VALUES ('unknown')"); db.commit()
            self.assertIsNone(snapshot(directory, None, at=AT)['pnl_usd'])
            db.close()

    def test_existing_corrupt_state_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'live.sqlite').write_bytes(b'not a database')
            self.assertIsNone(snapshot(directory, None, at=AT)['pnl_usd'])

    def test_publisher_exposes_only_aggregate_and_timestamp(self):
        body = build_checkpoint(SiteInputs(trading={'as_of': AT, 'pnl_usd': '-12.34', 'quote': 3.14}), AT)
        self.assertEqual(body['trading'], {'as_of': AT, 'pnl_usd': '-12.34'})
        self.assertNotIn('trading', build_checkpoint(SiteInputs(), AT))
        body = build_checkpoint(SiteInputs(trading={'as_of': AT, 'pnl_usd': float('nan')}), AT)
        self.assertIsNone(body['trading']['pnl_usd'])


if __name__ == '__main__':
    unittest.main()
