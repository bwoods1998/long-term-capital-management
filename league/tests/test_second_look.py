"""A failing reconcile is read once more before it is called a mismatch (Sept 23, 2026: a fill in
flight on the practice account rolled Deploy B back)."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from league.house import SECOND_LOOK_SECONDS, reconcile_with_second_look


class _Book:
    def __init__(self, results, working=1):
        self.results = list(results)
        self.polls = 0
        self.slept = []
        self.reconciles = 0
        self.working = working
        self._unreconciled = 0

    def reconcile(self):
        self.reconciles += 1
        result = self.results.pop(0)
        self._unreconciled = 0 if result.ok else self._unreconciled + 1
        return result

    def open_orders(self):
        return [object()] * self.working

    def poll(self):
        self.polls += 1

    def sleep(self, seconds):
        self.slept.append(seconds)


OK = SimpleNamespace(ok=True, detail="", position_diffs={}, cash_diff="0")
MISMATCH = SimpleNamespace(ok=False, detail="cash differs by 40.0116; positions differ: crypto:LINKUSD:alpaca-paper -3.262934654",
                           position_diffs={"crypto:LINKUSD:alpaca-paper": "-3.262934654"}, cash_diff="40.0116")


class SecondLook(unittest.TestCase):
    def test_a_fill_in_flight_is_read_again_and_passes(self):
        book = _Book([MISMATCH, OK])
        result = reconcile_with_second_look(book)
        self.assertTrue(result.ok)
        self.assertEqual((book.reconciles, book.polls, book.slept), (2, 1, [SECOND_LOOK_SECONDS]))

    def test_a_mismatch_that_stays_is_returned(self):
        book = _Book([MISMATCH, MISMATCH])
        result = reconcile_with_second_look(book)
        self.assertFalse(result.ok)
        self.assertEqual(book.reconciles, 2)

    def test_with_no_order_working_the_mismatch_stands_on_one_reading(self):
        book = _Book([MISMATCH, OK], working=0)
        self.assertFalse(reconcile_with_second_look(book).ok)
        self.assertEqual((book.reconciles, book.polls), (1, 0))

    def test_the_second_look_counts_once_toward_a_practice_books_adoption(self):
        book = _Book([MISMATCH, MISMATCH])
        reconcile_with_second_look(book)
        self.assertEqual(book._unreconciled, 1)

    def test_a_clean_reconcile_is_read_once(self):
        book = _Book([OK])
        self.assertTrue(reconcile_with_second_look(book).ok)
        self.assertEqual((book.reconciles, book.polls, book.slept), (1, 0, []))


if __name__ == "__main__":
    unittest.main()
