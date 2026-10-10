"""THE PROBE ROSTER (REDESIGN-1010, Oct 10, 2026): `dlane.roster` in swarm.json seats a few families in the Probe band; a
Candidate past the seats waits with no live row; a Probe family is never hidden; no setting is no roster; a setting that
cannot be read fails closed (the review of PR #523)."""

import json
import time
from pathlib import Path

from league.ops import dlane_report, preopen
from league.swarm import bands
from league.swarm.store import iso
from league.tests.evaluator_fakes import band_proof
from league.tests.test_swarm_store import SPEC, StoreCase

CODE = "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"
T0 = 1_790_400_000.0


def fam(fid, band, banded_at=None, band_since=None, structure="debit_vertical"):
    state = {} if banded_at is None else {"banded_at": banded_at}
    return {"id": fid, "band": band, "band_since": band_since, "structure": structure, "state": state}


class Seating(StoreCase):
    def test_no_roster_hides_nothing(self):
        rows = [fam("a", "probe"), fam("b", "candidate", 10.0), fam("c", "candidate", 20.0)]
        self.assertEqual(bands.waiting(rows, 0), set())

    def test_candidates_take_the_free_seats_in_the_order_they_became_candidates(self):
        rows = [fam("p", "probe"), fam("late", "candidate", 30.0), fam("early", "candidate", 10.0),
                fam("mid", "candidate", 20.0)]
        self.assertEqual(bands.waiting(rows, 2), {"mid", "late"})
        self.assertEqual(bands.seating(rows, 2)["seated"], ["early"])
        self.assertEqual(bands.waiting(rows, 3), {"late"})
        self.assertEqual(bands.waiting(rows, 4), set())

    def test_a_probe_family_is_never_hidden_and_a_full_probe_band_seats_no_candidate(self):
        rows = [fam("p1", "probe"), fam("p2", "probe"), fam("p3", "probe"), fam("c", "candidate", 5.0)]
        self.assertEqual(bands.waiting(rows, 2), {"c"})

    def test_a_candidate_back_from_probe_queues_behind_every_fresh_one(self):
        demoted = fam("d", "candidate", T0, iso(T0 + 3600))
        fresh = fam("f", "candidate", T0 + 10, iso(T0 + 10))
        self.assertEqual(bands.seating([demoted, fresh], 1)["seated"], ["f"])
        self.assertEqual(bands.waiting([demoted, fresh], 1), {"d"}, "it comes back to Probe only into a free seat")
        self.assertEqual(bands.waiting([demoted, fresh], 2), set())
        self.assertEqual(bands.waiting([demoted, fam("p", "probe")], 1), {"d"}, "no seat free: it is hidden")

    def test_a_candidate_that_cannot_trade_real_money_or_has_no_banded_at_holds_no_seat_and_is_shown(self):
        rows = [fam("ic", "candidate", 1.0, structure="iron_condor"), fam("x", "candidate"),
                fam("lc", "candidate", 2.0, structure="long_single")]
        seat = bands.seating(rows, 1)
        self.assertEqual((seat["seated"], seat["waiting"], seat["seatless"]), (["lc"], [], ["ic", "x"]))

    def test_closed_seats_no_new_candidate_and_hides_no_probe(self):
        rows = [fam("p", "probe"), fam("c", "candidate", 5.0)]
        self.assertEqual(bands.waiting(rows, bands.ROSTER_CLOSED), {"c"})


class ReadSeats(StoreCase):
    def setUp(self):
        super().setUp()
        self.root = self.store.root
        bands._roster_good.clear()
        self.addCleanup(bands._roster_good.clear)

    def roster(self, seats):
        (self.root / "swarm.json").write_text(json.dumps({"dlane": {"roster": seats}}))

    def banded(self, fid, band, structure="debit_vertical"):
        self.store.add_family({**SPEC, "id": fid, "structure": structure}, origin="test")
        version = self.store.add_version(fid, CODE, {}, author="test")
        self.store.set_state(fid, banded_version=1, banded_evaluator=band_proof(version), banded_at=self.clock(),
                             typical_by_version={"1": 50})
        self.store.set_band(fid, "candidate", reason="passed its holdout look")
        if band != "candidate":
            self.clock.advance(3600)
            self.store.set_band(fid, band, reason="the money table")
        self.clock.advance(60)

    def families(self, **kw):
        return sorted(r["family"] for r in bands.read(self.root, **kw))

    def test_the_roster_hides_waiting_candidates_from_the_live_path_and_seats_them_as_room_frees(self):
        self.banded("a", "probe")
        self.banded("b", "candidate")
        self.banded("c", "candidate")
        self.assertEqual(self.families(), ["a", "b", "c"], "no swarm.json: no roster")
        self.roster(1)
        self.assertEqual(self.families(), ["a"])
        self.assertEqual(self.families(family="b"), [], "a one-family read applies the same seats")
        self.assertEqual(self.families(family="a"), ["a"])
        self.roster(2)
        self.assertEqual(self.families(), ["a", "b"])
        self.store.retire("a", "the program loss line")
        self.assertEqual(self.families(), ["b", "c"], "a retired Probe family frees its seat")
        self.roster(0)
        self.assertEqual(self.families(), ["b", "c"])

    def test_a_lower_roster_never_hides_a_probe_family(self):
        self.banded("a", "probe")
        self.banded("b", "probe")
        self.banded("c", "candidate")
        self.roster(1)
        self.assertEqual(self.families(), ["a", "b"])
        self.assertEqual(bands.roster(self.root), {"seats": 1, "closed": False, "probe": ["a", "b"], "seated": ["a", "b"],
                                                   "waiting": ["c"], "seatless": []})

    def test_a_demotion_through_the_store_queues_the_family_and_the_report_counts_only_real_seats(self):
        self.banded("a", "probe")
        self.banded("b", "candidate")
        self.store.set_band("a", "candidate", reason="DM1: below its floor")    # back from Probe, an hour after banded_at
        self.roster(1)
        self.assertEqual(self.families(), ["b"], "the fresh Candidate holds the one seat; the demoted one waits")
        self.assertEqual(bands.roster(self.root)["seated"], ["b"])
        self.assertEqual(bands.roster(self.root)["waiting"], ["a"])

    def test_a_sized_family_neither_holds_a_seat_nor_waits(self):
        self.banded("s", "sized")
        self.banded("c", "candidate")
        self.roster(1)
        self.assertEqual(self.families(), ["c", "s"])

    def test_an_unreadable_or_malformed_setting_fails_closed(self):
        self.banded("a", "probe")
        self.banded("b", "candidate")
        self.banded("c", "candidate")
        self.roster(2)
        self.assertEqual(self.families(), ["a", "b"])
        for bad in ('{"dlane": {"roster": 2', '{"dlane": {"roster": "1"}}', '{"dlane": {"roster": true}}',
                    '{"dlane": {"roster": 1.5}}', '{"dlane": {"roster": -1}}', '{"dlane": []}', "[]"):
            (self.root / "swarm.json").write_text(bad)
            self.assertEqual(self.families(), ["a", "b"], f"the last good roster holds: {bad}")
        bands._roster_good.clear()
        (self.root / "swarm.json").write_text('{"dlane": {"roster": "2"}}')
        self.assertEqual(self.families(), ["a"], "no good value read yet: no new seat")
        self.assertTrue(bands.roster(self.root)["closed"])
        (self.root / "swarm.json").write_text(json.dumps({"dlane": {"mode": "gate"}}))
        self.assertEqual(self.families(), ["a", "b", "c"], "no roster key: no roster")

    def test_the_setting_is_a_whole_number_capped_at_50(self):
        self.roster(99)
        self.assertEqual(bands._roster_seats(self.root), 50)
        self.roster(3)
        self.assertEqual(bands._roster_seats(self.root), 3)
        self.assertEqual(bands._roster_seats(Path(self.root) / "nowhere"), 0)

    def test_the_report_is_none_while_the_roster_is_off(self):
        self.banded("a", "probe")
        self.assertIsNone(bands.roster(self.root))

    def test_the_dlane_report_carries_the_roster(self):
        self.banded("a", "probe")
        self.banded("c", "candidate")
        self.assertIsNone(dlane_report.roster_now(self.root))
        self.roster(1)
        self.assertEqual(dlane_report.roster_now(self.root)["waiting"], ["c"])
        self.assertEqual(dlane_report.report(self.root)["roster"]["waiting"], ["c"])

    def test_preopen_check_6_reads_a_waiting_candidate_as_by_design(self):
        self.banded("a", "probe")
        self.banded("c", "candidate")
        self.roster(1)
        h = preopen.collect(self.root, self.root, self.root, None, now=time.time(), config={})
        self.assertEqual(h["bands"]["live_missing_from_read"], [])
        self.assertEqual(h["bands"]["roster"]["waiting"], ["c"])
        self.assertNotIn("live-band families with no band row", json.dumps(preopen.check_bands(h).row()))
