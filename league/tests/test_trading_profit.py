"""Profit is the full real-options record, not a clipped roster or account movement."""
import json
import datetime as dt
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from league.publish import SiteInputs, build_checkpoint
from league.trading_profit import marked_value, snapshot, total

try:
    import numpy as np
except ImportError:
    np = None

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
            db.executescript('CREATE TABLE positions(pid,qty,entry,cash,status,info); CREATE TABLE orders(status); CREATE TABLE kv(key,value);')
            db.executemany('INSERT INTO positions VALUES (?,0,1,2.5,\'closed\',\'{}\')', [(i,) for i in range(200)])
            db.commit()
            before = path.read_bytes()
            self.assertEqual(snapshot(directory, None, at=AT), {'as_of': AT, 'pnl_usd': '500.00'})
            self.assertEqual(path.read_bytes(), before)
            db.execute("INSERT INTO orders VALUES ('unknown')"); db.commit()
            self.assertIsNone(snapshot(directory, None, at=AT)['pnl_usd'])
            db.close()

    def test_persisted_freeze_blocks_profit_without_an_inmemory_book(self):
        with tempfile.TemporaryDirectory() as directory:
            db = sqlite3.connect(Path(directory) / 'live.sqlite')
            db.executescript("CREATE TABLE positions(pid,qty,entry,cash,status,info); CREATE TABLE orders(status); CREATE TABLE kv(key,value);"
                             "INSERT INTO positions VALUES (1,0,1,25,'closed','{}');"
                             "INSERT INTO kv VALUES ('recon','{\"frozen\":\"unknown venue inventory\"}');")
            db.commit(); db.close()
            self.assertIsNone(snapshot(directory, None, at=AT)['pnl_usd'])

    def test_concurrent_fill_is_read_again_whole_and_old_mark_keeps_its_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'live.sqlite'
            db = sqlite3.connect(path)
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript("CREATE TABLE positions(pid,qty,entry,cash,status,info); CREATE TABLE orders(status); CREATE TABLE kv(key,value);"
                             "INSERT INTO positions VALUES (1,2,1,-202,'open','{}');")
            db.commit()
            live = SimpleNamespace(day=object(), book=SimpleNamespace(frozen='', positions={}))
            older = '2026-09-28T14:30:00.000Z'
            with patch('league.trading_profit.marked_value', return_value=(220, older)):
                self.assertEqual(snapshot(directory, live, at=AT), {'as_of': older, 'pnl_usd': '18.00'})
            seen = []
            def concurrent(row, day):
                seen.append(row['qty'])
                if len(seen) == 1:  # a fill lands while the first read copies the marks: that read is thrown away
                    db.execute('UPDATE positions SET qty=1,cash=-83'); db.commit()
                return 110 * row['qty'], AT
            with patch('league.trading_profit.marked_value', side_effect=concurrent):
                self.assertEqual(snapshot(directory, live, at=AT)['pnl_usd'], '27.00', 'the second read, whole: never old quantity with new cash')
            self.assertEqual(seen, [2, 1])
            def always(row, day):
                db.execute('UPDATE positions SET cash=cash-1'); db.commit()
                return 110, AT
            with patch('league.trading_profit.marked_value', side_effect=always):
                self.assertIsNone(snapshot(directory, live, at=AT)['pnl_usd'], 'a book that changes under every read is unknown')
            db.close()

    @unittest.skipIf(np is None, 'the live quote grid requires numpy')
    def test_mark_uses_copied_columns_and_database_quantity_with_real_quote_time(self):
        chain = SimpleNamespace(day=dt.date(2026, 9, 28), open_min=570, generation=1, quote_revision=2,
                                bid=np.array([[1., .4], [1.2, .5]]), ask=np.array([[1.2, .6], [1.4, .7]]),
                                column=lambda symbol: {'long': 0, 'short': 1}.get(symbol, -1))
        row = position(1, '-202', 2, 'open', root='SPY',
                       legs=json.dumps([{'symbol':'long','side':1,'ratio':1}, {'symbol':'short','side':-1,'ratio':1}]))
        value, stamp = marked_value(row, SimpleNamespace(chains={'SPY':chain}))
        self.assertEqual(value, 140)
        self.assertEqual(stamp, '2026-09-28T13:31:00.000Z')
        chain.bid[1,0] = np.nan
        value, stamp = marked_value(row, SimpleNamespace(chains={'SPY':chain}))
        self.assertEqual(value, 120)
        self.assertEqual(stamp, '2026-09-28T13:30:00.000Z')

    @unittest.skipIf(np is None, 'the live quote grid requires numpy')
    def test_quote_update_cannot_mix_old_bids_with_new_asks(self):
        chain = SimpleNamespace(day=dt.date(2026, 9, 28), open_min=570, generation=1, quote_revision=2,
                                bid=np.array([[1.0]]), ask=np.array([[1.2]]), column=lambda symbol: 0)
        row = position(1, '-102', 1, 'open', root='SPY',
                       legs=json.dumps([{'symbol':'long','side':1,'ratio':1}]))
        day = SimpleNamespace(chains={'SPY': chain})
        old_bids = chain.bid
        class UpdatingQuotes:
            def __getitem__(self, index):
                old = old_bids[index].copy()
                chain.ask[0, 0] = 2.2
                chain.quote_revision += 2  # ordinary quote write: the column generation is unchanged
                return old
        chain.bid = UpdatingQuotes()
        self.assertIsNone(marked_value(row, day))
        chain.bid = old_bids
        chain.quote_revision = 5  # the writer has begun, but has not finished this row
        self.assertIsNone(marked_value(row, day))

    def test_the_brokers_fill_times_are_read_to_the_microsecond_whatever_their_precision(self):
        from league.trading_profit import _epoch

        self.assertEqual(_epoch('2026-09-28T14:10:01.312Z'), _epoch('2026-09-28T14:10:01.312000000Z'))
        self.assertAlmostEqual(_epoch('2026-09-28T14:07:11.776268123Z') - _epoch('2026-09-28T14:07:11Z'), 0.776268, places=6)
        self.assertIsNone(_epoch('2026-09-28T14:07:11'), 'a time without a zone is no time')

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
