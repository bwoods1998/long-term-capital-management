"""The watch (`scripts/floor_watch.py`) reads what it says it reads.

Sept 24, 2026 (the close-the-gaps run, workstream B and L3): `--since` was compared as text with
the ledger's `at`, an ISO stamp with `T`; sqlite's `datetime('now', '-1 hour')` yields a space
instead, and since a space sorts before `T` that admitted the whole day. The newest hourly yield
row was looked up as `"what": "yield"` with a space, which the ledger's canonical JSON never
writes, so the watch never printed a yield row. These tests run the box snippet itself against a
throwaway state directory.

The watch shows the seat market by evidence (S1-S4 of the close-the-gaps run, Sept 24, 2026).

`scripts/floor_watch.py` runs a read-only snippet on the House box and prints what the owner's plan asks to
be watched. The review of #245 found the seat line carried only the waiters and the displaceable count: the
seats holding no evidence (`seats_holding_none`), the desks' evidence clocks the grace follows, why a class
of waiter (the retained candidates too) was last refused a seat, and the House-sent sales stopped after three
identical refusals reached no operator. The snippet runs here against a state directory built for the test.
"""


from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from league.ledger import Ledger
from league.tests.fakes import Clock
from scripts import floor_watch


class TheSinceStamp(unittest.TestCase):
    def test_a_space_separated_stamp_becomes_the_ledgers_iso_form(self):
        self.assertEqual(floor_watch.normalize_since("2026-09-24 00:42:00"), "2026-09-24T00:42:00")
        self.assertEqual(floor_watch.normalize_since("2026-09-24T00:42:00"), "2026-09-24T00:42:00")
        self.assertEqual(floor_watch.normalize_since("2026-09-24T00:42:00.123Z"), "2026-09-24T00:42:00")
        self.assertEqual(floor_watch.normalize_since("2026-09-24T02:42:00+02:00"), "2026-09-24T00:42:00")
        self.assertEqual(floor_watch.normalize_since("2026-09-24"), "2026-09-24T00:00:00")

    def test_what_is_not_a_time_is_refused(self):
        for bad in ("yesterday", "", "2026-13-01T00:00:00", "now-1h"):
            with self.assertRaises(argparse.ArgumentTypeError, msg=bad):
                floor_watch.normalize_since(bad)

    def test_the_space_form_would_have_admitted_the_whole_day(self):
        # The defect itself: string order, which is what the snippet's `at >= ?` compares.
        late_in_the_day = "2026-09-24T00:05:00.000Z"
        self.assertTrue(late_in_the_day >= "2026-09-24 23:00:00", "the raw space form admits a row from before it")
        self.assertFalse(late_in_the_day >= floor_watch.normalize_since("2026-09-24 23:00:00"))

    def test_the_command_line_normalizes_it(self):
        parser = floor_watch.parser()
        self.assertEqual(parser.parse_args(["--since", "2026-09-24 00:42:00"]).since, "2026-09-24T00:42:00")
        with self.assertRaises(SystemExit):
            parser.parse_args(["--since", "not a time"])


class TheBoxSnippet(unittest.TestCase):
    def test_current_stores_are_read_without_private_programs_or_quote_inputs(self):
        from league.swarm.store import SwarmStore
        from league.live.state import LiveState
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ledger = Ledger(root/'ledger.sqlite')
            try:
                ledger.append('ops.budget',{'what':'sail','spent_usd':'1.25'})
                ledger.append('ops.alert',{'level':'warning','text':'synthetic worker test'})
            finally: ledger.close()
            swarm = SwarmStore(root)
            swarm.add_family({'id':'synthetic','mechanism':'PRIVATE_MECHANISM is a synthetic hypothesis for a test only.','structure':'debit_vertical','roots':['SPY']},origin='test')
            swarm.add_spend('openai',.1)
            swarm.close()
            live = LiveState(root/'live.sqlite');live.put('recon',{'frozen':'synthetic mismatch'});live.put('paper_proof',{'status':'open_sent','day':'2026-09-28'});live.close()
            (root/'programs'/'secret.py').write_text('PRIVATE_PARAMETERS = 12345')
            (root/'health.json').write_text(json.dumps({'at':'2026-09-28T13:30:00Z','real_money':False}))
            before = {p: p.read_bytes() for p in root.glob('*.sqlite')}
            run = subprocess.run([sys.executable,'-c',floor_watch.BOX_SNIPPET,'2000-01-01T00:00:00',str(root)],capture_output=True,text=True,check=True)
            out = json.loads(run.stdout)
            self.assertEqual(out['swarm.sqlite']['bands'],{'gym':1})
            self.assertEqual(out['ledger.sqlite']['sail_meter_usd_since'],1.25)
            self.assertTrue(out['live.sqlite']['reconciliation_frozen'])
            self.assertEqual(out['live.sqlite']['paper_route']['status'],'open_sent')
            self.assertNotIn('PRIVATE',run.stdout)
            self.assertEqual(before,{p:p.read_bytes() for p in before})
            self.assertIn('Live inventory',floor_watch.render(out,{},{}))

    def test_missing_or_corrupt_state_is_explicit_and_creates_no_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'live.sqlite').write_bytes(b'broken')
            run=subprocess.run([sys.executable,'-c',floor_watch.BOX_SNIPPET,'2000-01-01T00:00:00',str(root)],capture_output=True,text=True,check=True)
            out=json.loads(run.stdout)
            self.assertIsNone(out['swarm.sqlite'])
            self.assertIn('error',out['live.sqlite'])
            self.assertFalse((root/'swarm.sqlite').exists())
