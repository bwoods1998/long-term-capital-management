"""Quote-free operator economics must never turn missing inventory or funding into profit."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from league.ledger import Ledger
from league.swarm.store import SwarmStore
from scripts.economics import build


class Economics(unittest.TestCase):
    def test_missing_state_is_unknown_and_never_created(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'absent'
            result = build(root)
            self.assertIsNone(result['trading']['pnl_usd'])
            self.assertIsNone(result['net_after_all_inputs_usd'])
            self.assertFalse(root.exists())

    def test_ledger_proof_is_required_for_zero_and_a_real_fill_removes_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ledger = Ledger(root / 'ledger.sqlite')
            try:
                ledger.append('floor.mark', {'equity': '5481.63', 'cash': '5481.63'})
                ledger.append('book.fill', {'real_money': False, 'instrument': {'asset_class': 'option'}})
                self.assertEqual(build(root)['trading']['pnl_usd'], '0.00')
                ledger.append('book.fill', {'real_money': True, 'instrument': {'asset_class': 'option'}})
                self.assertIsNone(build(root)['trading']['pnl_usd'])
            finally:
                ledger.close()

    def test_all_closed_cash_is_counted_readonly_and_cost_sources_stay_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ledger = Ledger(root / 'ledger.sqlite')
            ledger.append('ops.budget', {'what': 'sail', 'spent_usd': '1.25'})
            ledger.close()
            swarm = SwarmStore(root)
            swarm.add_spend('sail_boxes', .9)
            swarm.add_spend('openai', .1)
            swarm.close()
            path = root / 'live.sqlite'
            db = sqlite3.connect(path)
            db.executescript('CREATE TABLE positions(pid,qty,cash,status,info);'
                             'CREATE TABLE orders(status); CREATE TABLE kv(key,value);')
            db.executemany("INSERT INTO positions VALUES (?,0,'2.50','closed','{}')", [(i,) for i in range(200)])
            db.commit()
            before = path.read_bytes()
            result = build(root)
            self.assertEqual(result['trading']['pnl_usd'], '500.00')
            self.assertEqual(result['attributed_spend_usd'], {'sail_boxes': .9, 'openai': .1})
            self.assertEqual(result['sail_meter_usd'], 1.25)
            self.assertIsNone(result['net_after_all_inputs_usd'])
            self.assertEqual(path.read_bytes(), before)
            db.execute("INSERT INTO positions VALUES (201,1,'-202','open','{}')")
            db.commit()
            self.assertIsNone(build(root)['trading']['pnl_usd'], 'the CLI has no current marks')
            db.execute("UPDATE positions SET status='closed',qty=0")
            db.execute('INSERT INTO kv VALUES (?,?)', ('recon', json.dumps({'frozen': 'unmatched position'})))
            db.commit()
            self.assertIsNone(build(root)['trading']['pnl_usd'])
            db.close()
