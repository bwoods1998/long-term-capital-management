"""Production startup ordering against FakeBroker only; no venue or model requests."""
import json
import unittest
from unittest.mock import patch

from league.tests import test_ladder as ladder_cases
from league.tests.fakes import FakeBroker
from ltcm.broker import VenueUnavailable


class StartupAccountingTests(unittest.TestCase):
    def fixture(self):
        f = ladder_cases.LadderTest()
        f.setUp()
        self.addCleanup(f.tearDown)
        return f

    def test_live_books_are_reconciled_before_the_first_health_publication(self):
        f = self.fixture()
        book = f.house.books['alpaca']
        self.assertIsNone(book.frozen)
        self.assertIsNotNone(book.venue_cash)
        rows = [e for e in f.house.ledger.iter(kinds='book.reconciled') if e.payload.get('book') == 'alpaca']
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].payload['ok'])
        health = json.loads((f.house.root / 'health.json').read_text())
        self.assertGreaterEqual(health['ledger_seq'], rows[0].seq)

    def test_startup_outage_is_visible_and_later_reconciliation_recovers_without_approval(self):
        original = FakeBroker.balance
        def unavailable(broker):
            if broker.venue == 'alpaca':
                raise VenueUnavailable('temporary read outage')
            return original(broker)
        with patch.object(FakeBroker, 'balance', unavailable):
            f = self.fixture()
            self.assertEqual(f.house.books['alpaca'].frozen, 'awaiting startup reconciliation')
            health = json.loads((f.house.root / 'health.json').read_text())
            self.assertEqual(health['books']['alpaca']['frozen'], 'awaiting startup reconciliation')
        f.house.tick()
        self.assertIsNone(f.house.books['alpaca'].frozen)


if __name__ == '__main__':
    unittest.main()
