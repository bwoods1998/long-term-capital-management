"""The equity book's ORDER PATH after the E1 review (`league/equity/live.py`; findings money-4, ops-5, money-9, amend-5,
money-7, ops-7, ops-10, ops-12, money-6), on the book tests' harness (league/tests/test_equity_book.py: an in-memory
venue with Alpaca's documented stock-order shapes and invented prices; money's and core's functions stubbed at their
interface).

- THE OWNER'S COMMANDS: `python3 -m league.live --flatten-equity "<why>"` and `--clear-equity-freeze "<why>"` write a
  key-value; the book's minute acts on it once, in the House's own thread, and records who and why.

No price here is a market's."""

import contextlib
import datetime as dt
import io
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from league.equity import live as L
from league.live import __main__ as owner
from league.tests import test_equity_book as T

SUNDAY = dt.date(2026, 10, 11)
MONDAY, TUESDAY, FRIDAY = T.MONDAY, T.TUESDAY, T.FRIDAY


def command(root: Path, *args: str) -> dict:
    """The owner's command against the state at `root` (its report is printed to the owner's terminal: swallowed)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return owner.main(["--root", str(root), *args])


class TheOwnersCommands(T.BookTest):
    """money-4, ops-5, money-9: the rollback's step 3 and the corporate-action freeze each had no way to be run."""

    def test_the_key_names_are_the_books(self):
        self.assertEqual((owner.EQUITY_FLATTEN, owner.EQUITY_CLEAR_FREEZE), (L.OWNER_FLATTEN, L.OWNER_CLEAR_FREEZE))

    def test_flatten_is_run_by_the_books_own_minute(self):
        h = self.harness()
        inst = h.instance()
        old, young = h.lot(inst, "SPY", "0.5", "590"), h.lot(inst, "QQQ", "0.5", "490", opened=MONDAY)
        h.clock.set(T.at(MONDAY, 12, 0))
        shown = command(self.root, "--flatten-equity", "the  rollback of E1")
        ask = shown["equity"]["pending_owner_actions"][L.OWNER_FLATTEN]
        self.assertEqual((ask["why"], ask["by"]), ("the rollback of E1", "the owner (python -m league.live)"))
        self.assertEqual(h.venue.sent, [], "the command itself sends nothing: it writes a key-value")
        self.assertEqual(h.intents(kind="house_exit"), [])
        out = h.tick(12, 1)
        self.assertEqual(out["flatten"], 2)
        self.assertIsNone(h.state.get(L.OWNER_FLATTEN), "done once, its key deleted")
        self.assertEqual(h.book._lot(old.lid).reason, "flatten")           # sold this minute, through the normal path
        self.assertEqual(h.book._lot(young.lid).status, "open")            # min hold: tomorrow's open
        self.assertTrue(all(b["type"] == "limit" for b in h.venue.sent))    # never a market order
        [(_, said)] = [e for e in h.events if e[0] == "equity.flatten"]
        self.assertEqual(said["lots"], 2)
        self.assertIn("the owner (python -m league.live): the rollback of E1", said["why"])
        self.assertTrue(any("flatten" in text and "2 lots" in text for _, text in h.alerts))
        self.assertNotIn("flatten", h.tick(12, 2))
        self.assertEqual(len(h.intents(kind="house_exit")), 2, "each lot queued once")
        self.assertEqual(command(self.root, "--status")["equity"]["pending_owner_actions"], {})
        h.tick(16, 0)
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual(h.book._lot(young.lid).reason, "flatten")

    def test_flatten_on_a_closed_day_queues_the_next_open(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        h.clock.set(T.at(SUNDAY, 15, 0))
        command(self.root, "--flatten-equity", "before Monday")
        self.assertEqual(h.tick(15, 1, day=SUNDAY)["flatten"], 1)
        [exit_] = h.intents(kind="house_exit")
        self.assertEqual((exit_.exec_day, exit_.at, exit_.tag, exit_.lid), ("2026-10-12", "open", "flatten", lot.lid))
        self.assertEqual(h.venue.sent, [])
        h.tick(9, 31)
        self.assertEqual(h.book._lot(lot.lid).status, "closed")

    def test_the_corporate_action_freeze_is_cleared_and_recorded(self):
        h = self.harness()
        h.lot(h.instance("fam-a"), "SPY", "1", "590")
        buy = h.intent(h.instance("fam-b"), "buy", symbol="QQQ", share="0.2")
        h.venue.held["SPY"] = D("0.4")                                      # and a mismatch of the book's own
        h.state.put("eq_freeze", {"why": "DIVFEE on SPY: a type the book does not book", "at": 1.0, "activity": "a-1"})
        h.tick(9, 31)
        h.tick(9, 32)
        self.assertEqual(h.venue.sent, [])
        self.assertIn("DIVFEE on SPY", h.get_intent(buy.iid).why)
        command(self.root, "--clear-equity-freeze", "booked by hand: a fee of the ADR")
        out = h.tick(9, 33)
        self.assertTrue(out["freeze_cleared"])
        self.assertIsNone(h.state.get("eq_freeze"))
        self.assertIsNone(h.state.get(L.OWNER_CLEAR_FREEZE))
        self.assertIn("SPY: the account holds 0.4", h.book.frozen, "the reconciliation's own freeze is not the owner's")
        self.assertNotIn("DIVFEE", h.book.frozen)
        said = [p for kind, p in h.events if kind == "equity.freeze" and p.get("cleared") == "eq_freeze"]
        self.assertEqual(len(said), 1)
        self.assertIn("the owner (python -m league.live): booked by hand: a fee of the ADR", said[0]["by"])
        self.assertIn("DIVFEE on SPY", said[0]["why"])
        self.assertEqual((said[0]["frozen"], said[0]["activity"]), (True, "a-1"))
        self.assertEqual(h.venue.sent, [])
        h.venue.held["SPY"] = D("1")
        h.tick(9, 34)
        h.tick(9, 35)                                                       # two clean readings lift the other one
        self.assertEqual([b["side"] for b in h.venue.sent], ["buy"], "the opens go again once nothing freezes them")

    def test_clearing_lifts_the_block_in_the_same_minute(self):
        h = self.harness()
        h.intent(h.instance(), "buy", symbol="QQQ", share="0.2")
        h.state.put("eq_freeze", {"why": "a rename of SPY", "at": 1.0})
        h.tick(9, 31)
        command(self.root, "--clear-equity-freeze", "reviewed")
        h.tick(9, 32)
        self.assertEqual([b["side"] for b in h.venue.sent], ["buy"])

    def test_a_clear_with_nothing_frozen_only_spends_its_key(self):
        h = self.harness()
        command(self.root, "--clear-equity-freeze", "nothing to clear")
        self.assertIs(h.tick(9, 31)["freeze_cleared"], False)
        self.assertIsNone(h.state.get(L.OWNER_CLEAR_FREEZE))
        self.assertEqual([e for e in h.events if e[0] == "equity.freeze"], [])

    def test_a_reason_is_required(self):
        h = self.harness()
        for flag in ("--flatten-equity", "--clear-equity-freeze"):
            with self.subTest(flag=flag), self.assertRaises(SystemExit):
                command(self.root, flag, "   ")
        self.assertIsNone(h.state.get(L.OWNER_FLATTEN))
        self.assertIsNone(h.state.get(L.OWNER_CLEAR_FREEZE))

    def test_a_flatten_that_fails_is_tried_again_and_never_stops_the_clear(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        h.state.put("eq_freeze", {"why": "a rename of SPY", "at": 1.0})
        h.state.put(L.OWNER_FLATTEN, {"why": "the rollback", "at": 1.0, "by": "the owner"})
        h.state.put(L.OWNER_CLEAR_FREEZE, {"why": "reviewed", "at": 1.0, "by": "the owner"})
        with mock.patch.object(L.EquityBook, "flatten", side_effect=RuntimeError("boom")):
            out = h.tick(9, 31)
        self.assertTrue(any(L.OWNER_FLATTEN in e for e in out["errors"]))
        self.assertIsNotNone(h.state.get(L.OWNER_FLATTEN), "kept: tried again next minute")
        self.assertIsNone(h.state.get("eq_freeze"))
        self.assertEqual(h.tick(9, 32)["flatten"], 1)
        self.assertEqual(h.book._lot(lot.lid).reason, "flatten")


if __name__ == "__main__":
    unittest.main()
