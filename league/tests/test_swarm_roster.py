"""THE PROBE ROSTER (REDESIGN-1010, Oct 10, 2026): `dlane.roster` seats a few families in the Probe band; a Candidate past
the seats waits with no live row; a Probe family is never hidden; 0 (the default) is no roster."""

import json

from league.swarm import bands, dlane
from league.swarm.store import iso
from league.tests.evaluator_fakes import band_proof
from league.tests.test_swarm_store import SPEC, StoreCase

CODE = "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"


def fam(fid, band, banded_at=None, band_since=None):
    state = {} if banded_at is None else {"banded_at": banded_at}
    return {"id": fid, "band": band, "band_since": band_since, "state": state}


class Waiting(StoreCase):
    def test_no_roster_hides_nothing(self):
        rows = [fam("a", "probe"), fam("b", "candidate", 10.0), fam("c", "candidate", 20.0)]
        self.assertEqual(bands.waiting(rows, 0), set())

    def test_candidates_take_the_free_seats_in_the_order_they_became_candidates(self):
        rows = [fam("p", "probe"), fam("late", "candidate", 30.0), fam("early", "candidate", 10.0),
                fam("mid", "candidate", 20.0), fam("s", "sized")]
        self.assertEqual(bands.waiting(rows, 2), {"mid", "late"})
        self.assertEqual(bands.waiting(rows, 3), {"late"})
        self.assertEqual(bands.waiting(rows, 4), set())

    def test_a_probe_family_is_never_hidden_and_a_full_probe_band_seats_no_candidate(self):
        rows = [fam("p1", "probe"), fam("p2", "probe"), fam("p3", "probe"), fam("c", "candidate", 5.0)]
        self.assertEqual(bands.waiting(rows, 2), {"c"}, "a lower roster stops new seats only")

    def test_a_candidate_back_from_probe_takes_no_seat_and_is_shown(self):
        at = 1_790_400_000.0
        demoted = fam("d", "candidate", at, iso(at + 3600))
        fresh = fam("f", "candidate", at + 10, iso(at + 10))
        self.assertEqual(bands.waiting([demoted, fresh], 1), set(), "the demoted family holds no seat")
        self.assertEqual(bands.waiting([demoted, fresh, fam("g", "candidate", at + 20)], 1), {"g"})

    def test_a_candidate_with_no_readable_banded_at_is_shown(self):
        self.assertEqual(bands.waiting([fam("x", "candidate"), fam("p", "probe")], 1), set())


class ReadSeats(StoreCase):
    def setUp(self):
        super().setUp()
        self.root = self.store.root

    def roster(self, seats):
        (self.root / "swarm.json").write_text(json.dumps({"dlane": {"roster": seats}}))

    def banded(self, fid, band):
        self.store.add_family({**SPEC, "id": fid}, origin="test")
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
        self.assertEqual(self.families(), ["a", "b", "c"], "no swarm.json roster: the code's default is no roster")
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
        self.assertEqual(bands.roster(self.root), {"seats": 1, "probe": ["a", "b"], "seated": ["a", "b"], "waiting": ["c"]})

    def test_a_sized_family_neither_holds_a_seat_nor_waits(self):
        self.banded("s", "sized")
        self.banded("c", "candidate")
        self.roster(1)
        self.assertEqual(self.families(), ["c", "s"])

    def test_the_report_is_none_while_the_roster_is_off(self):
        self.banded("a", "probe")
        self.assertIsNone(bands.roster(self.root))


    def test_the_dlane_report_carries_the_roster(self):
        from league.ops import dlane_report

        self.banded("a", "probe")
        self.banded("c", "candidate")
        self.assertIsNone(dlane_report.roster_now(self.root))
        self.roster(1)
        self.assertEqual(dlane_report.roster_now(self.root)["waiting"], ["c"])


class Setting(StoreCase):
    def test_the_roster_is_a_whole_number_from_0_to_50_and_0_by_default(self):
        self.assertEqual(dlane.cfg({})["roster"], 0)
        self.assertEqual(dlane.cfg({"dlane": {"roster": 3}})["roster"], 3)
        for bad in ("3", 2.5, True, None, float("nan")):
            self.assertEqual(dlane.cfg({"dlane": {"roster": bad}})["roster"], 0, bad)
        self.assertEqual(dlane.cfg({"dlane": {"roster": 99}})["roster"], 50)
        self.assertEqual(dlane.cfg({"dlane": {"roster": -4}})["roster"], 0)

