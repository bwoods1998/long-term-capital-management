"""The equity book's reader of the swarm (`league/equity/families.py`): equity-lane rows with EDM1's sigma, the forward
record, band writes confirmed against the row they were judged on, the twins record, an unreadable store reading as
no rows with its reason, and the in-memory double.

`bands.read(root, lanes=...)` is the swarm package's (league/equity/INTERFACES.md 8.3); these tests stand in for it at
that interface, over a real `SwarmStore`."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.equity import LANES
from league.equity import families as F
from league.swarm.store import SwarmStore

MECH = "Buy the index at the close and sell it at the next open: the overnight drift."


def row(family="seed-overnight-spy", *, band="candidate", version=1, run_sha="r1", lane="beta", **extra):
    return {"family": family, "band": band, "lane": lane, "structure": "etf", "symbols": ["SPY"], "seeded": True,
            "holdout_passed": True, "validation_passed": True, "version": version, "code": "def decide(ctx):\n    return []\n",
            "params": {}, "run_sha": run_sha, **extra}


class SigmaTests(unittest.TestCase):
    def test_validation_r_sd(self):
        self.assertEqual(F.validation_r_sd({"validation_r_sd_by_version": {"2": 0.4}}, 2), 0.4)
        self.assertEqual(F.validation_r_sd({"validation_r_sd": 0.3, "validation_version": 2}, 2), 0.3)
        self.assertIsNone(F.validation_r_sd({"validation_r_sd": 0.3, "validation_version": 1}, 2))
        for bad in (0, -1.0, float("nan"), "0.2", True):
            self.assertIsNone(F.validation_r_sd({"validation_r_sd_by_version": {"1": bad}}, 1))
        self.assertIsNone(F.validation_r_sd(None, 1))


class StoreBacked(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = SwarmStore(self.root)
        fam = self.store.add_family({"id": "seed-overnight-spy", "mechanism": MECH, "structure": "etf",
                                     "roots": ["SPY"], "lane": "beta"}, origin="seed")
        self.fid = fam["id"]
        self.store.set_band(self.fid, "candidate", reason="passed its look")
        self.store.set_state(self.fid, banded_version=1, validation_r_sd_by_version={"1": 0.25})
        self.rows = [row(self.fid), row("an-options-family", lane=None)]
        self.families = F.EquityFamilies(self.root)

        self.asked: list[dict] = []

        def fake_read(root, *, family=None, lanes=None, strict=False, **more):
            self.assertEqual(lanes, LANES)
            self.assertTrue(strict, "the book's reader must tell an unreadable store from one with no row")
            self.asked.append(dict(more))
            out = [dict(r) for r in self.rows if family is None or r["family"] == family]
            for r in out:
                r["band"] = (self.store.family(r["family"]) or {}).get("band", r["band"])
            return out

        patcher = mock.patch("league.swarm.bands.read", fake_read)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_read_keeps_the_equity_lanes_with_their_sigma(self):
        rows = self.families.read()
        self.assertEqual([r["family"] for r in rows], [self.fid])
        self.assertEqual(rows[0]["validation_r_sd"], 0.25)
        self.assertEqual(self.families.last_error, "")

    def test_the_seat_rule_decides_whether_the_waiting_candidates_are_read(self):
        """THE SEAT RULE (release E5-A): under the rule in force the book ranks the waiting Candidates itself, so its
        reader asks the swarm's for them (`waiting=True`); under "first-come" (the rollback) the call is release
        E5-S's, argument for argument, and the swarm's own queue hides them."""
        from league.equity import bands as B
        from league.tests.equity_design import seat_rule

        self.assertEqual(B.seat_settings().rule, B.ACTIVITY_FREE, "the rule in force")
        self.families.read()
        self.assertEqual(self.asked[-1], {"waiting": True})
        with seat_rule("first-come"):
            self.families.read()
            self.assertEqual(self.asked[-1], {}, "first come: the read is the one before the seat rule")
            expected = self.families.read()[0]
            self.assertTrue(self.families.confirm_band(expected, "probe", "a seat is free"))
            self.assertEqual(self.asked[-1], {}, "and so is the read inside the band's confirmation")

    def test_the_roster_seats_fail_closed(self):
        """`seats()`: the swarm's roster (`elane.roster_seats`); 0 when it is closed or cannot be read."""
        from league.swarm import elane

        with mock.patch.object(elane, "roster_seats", return_value=4):
            self.assertEqual(self.families.seats(), 4)
        with mock.patch.object(elane, "roster_seats", return_value=elane.ROSTER_CLOSED):
            self.assertEqual(self.families.seats(), 0, "an unreadable roster seats nobody new")
        with mock.patch.object(elane, "roster_seats", side_effect=OSError("no file")):
            self.assertEqual(self.families.seats(), 0)
        self.assertIsNone(F.MemoryEquityFamilies().seats(), "a reader with no word of the roster: the table's count")
        self.assertEqual(F.MemoryEquityFamilies(seats=2).seats(), 2)

    def test_an_unreadable_store_reads_as_no_rows_and_says_why(self):
        with mock.patch("league.swarm.bands.read", side_effect=TypeError("read() got an unexpected keyword 'lanes'")):
            self.assertEqual(self.families.read(), [])
        self.assertIn("TypeError", self.families.last_error)
        self.families.read()
        self.assertEqual(self.families.last_error, "")

    def test_forward_rows_once_by_id(self):
        trade = {"id": "eq-1", "version": 1, "day": "2026-10-13", "pnl": 1.25, "max_loss": 250.0}
        self.assertEqual(self.families.add_forward(self.fid, "real", [trade]), 1)
        self.assertEqual(self.families.add_forward(self.fid, "real", [trade]), 0)
        rows = self.families.forward_rows(self.fid)
        self.assertEqual([(r["trade_id"], r["pnl"], r["max_loss"], r["version"]) for r in rows], [("eq-1", 1.25, 250.0, 1)])

    def test_confirm_band_moves_it_and_records_the_promotion(self):
        expected = self.families.read()[0]
        self.assertTrue(self.families.confirm_band(expected, "probe", "a seat is free"))
        fam = self.store.family(self.fid)
        self.assertEqual(fam["band"], "probe")
        self.assertIsNotNone(fam["state"].get("live_promoted_at"))
        # The same band again is a confirmation, not a move.
        self.assertTrue(self.families.confirm_band(self.families.read()[0], "probe", "unchanged"))

    def test_confirm_band_refuses_a_row_that_changed(self):
        expected = self.families.read()[0]
        self.rows[0]["run_sha"] = "r2"                             # a new program under the same version: refused
        self.assertFalse(self.families.confirm_band(expected, "probe", "x"))
        self.rows[0]["run_sha"] = "r1"
        self.store.set_state(self.fid, validation_r_sd_by_version={"1": 0.5})
        self.assertFalse(self.families.confirm_band(expected, "probe", "x"))   # sigma changed under it
        self.store.set_state(self.fid, validation_r_sd_by_version={"1": 0.25})
        self.store.set_band(self.fid, "gym", reason="the swarm took it back")
        self.assertFalse(self.families.confirm_band(expected, "probe", "x"))
        self.assertEqual(self.store.family(self.fid)["band"], "gym")

    def test_confirm_band_moves_only_between_the_books_bands(self):
        expected = self.families.read()[0]
        self.assertFalse(self.families.confirm_band(expected, "gym", "x"))
        self.assertFalse(self.families.confirm_band(expected, "retired", "x"))

    def test_set_band(self):
        self.families.set_band(self.fid, "probe", "by hand")
        self.assertEqual(self.store.family(self.fid)["band"], "probe")

    def test_twins(self):
        self.assertEqual(self.families.twins(), {})
        self.store.put(F.TWINS_KEY, {"eq:1": {"status": "priced", "gap_bp": 3.5, "final": True}})
        self.assertEqual(self.families.twins()["eq:1"]["gap_bp"], 3.5)


class MemoryTests(unittest.TestCase):
    def test_the_same_api_in_memory(self):
        mem = F.MemoryEquityFamilies([row(band="probe"), row("gone", band="retired")])
        rows = mem.read()
        self.assertEqual([r["family"] for r in rows], ["seed-overnight-spy"])
        rows[0]["band"] = "sized"                                  # a copy: the store is untouched
        self.assertEqual(mem.read()[0]["band"], "probe")
        self.assertEqual(mem.add_forward("seed-overnight-spy", "real", [{"id": "eq-1", "pnl": 1.0}]), 1)
        self.assertEqual(mem.add_forward("seed-overnight-spy", "real", [{"id": "eq-1", "pnl": 1.0}]), 0)
        self.assertEqual(mem.forward_rows("seed-overnight-spy")[0]["source"], "real")
        with self.assertRaises(ValueError):
            mem.add_forward("seed-overnight-spy", "gym", [])
        self.assertTrue(mem.confirm_band(mem.read()[0], "sized", "sized up"))
        self.assertEqual(mem.moves, [("seed-overnight-spy", "sized", "sized up")])
        self.assertFalse(mem.confirm_band(row(band="probe"), "candidate", "stale row"))
        mem.last_error = "unreadable"
        self.assertEqual(mem.read(), [])
        mem.twin_rows["eq:3"] = {"status": "priced", "gap_bp": 1.0}
        self.assertEqual(mem.twins()["eq:3"]["gap_bp"], 1.0)


if __name__ == "__main__":
    unittest.main()
