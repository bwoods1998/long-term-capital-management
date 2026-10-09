"""THE DIRECTION LANE across its builders (release D-1, Oct 9, 2026): the joins the integration of the four wiring branches
(cards and architect, researcher, game/screen/incubator, ops and docs) closed, each one where one builder's code reads
what another's writes.

- A direction parent's FORK (league/swarm/tournament.py `fork`) is a direction family (its spec, copied from the parent,
  carries the lane) and its `swarm.born` says so, so the births' quota and the funnel (`dlane.born_counts`, which reads a
  payload without a lane as alpha's) count it in its lane; an alpha fork's event is as before in every mode.
- THE PUBLIC CHECKLIST (league/swarm/progress.py) reads the family's own lane's leakage alarm, as the gate stops that
  lane's looks alone (`evidence.leakage_alarms`): correlated direction passes never show an alpha family's gate as
  paused, and the direction lane's own alarm shows on a direction family's. With `dlane.mode` "off" it is the one count
  over every look, as before.
- THE RESEARCHER'S CARD BRIEF names a direction card's lane while the lane is on (`cards.brief_text` with the settings);
  an alpha card's brief, and every brief while the lane is off, is as before.

Invented stores and figures only: none is from the operator's studies.
"""

from __future__ import annotations

import copy
import json
import unittest

from league.swarm import cards, dlane
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import result
from league.tests.test_swarm_progress import ProgressCase
from league.tests.test_swarm_researcher_dlane import DIRECTION_SPEC
from league.tests.test_swarm_researcher_dlane import Case as ResearcherCase
from league.tests.test_swarm_rounds import RoundCase


def with_mode(settings, mode):
    out = copy.deepcopy(settings)
    out["dlane"] = {**(out.get("dlane") or {}), "mode": mode}
    return out


class ForkLane(RoundCase):
    """A fork's `swarm.born` carries the direction lane for a direction parent, and nothing new for an alpha one."""

    def fork(self, fid, settings, **spec):
        self.family(fid, **spec)
        self.store.add_run(fid, 1, result(f"x-{fid}"), window="train", stress=1.0, purpose="train")
        self.store.set_state(fid, validation_numbers={"mean": 0.05, "t": 2.5, "sharpe_daily": 0.2, "quarters": "4/4"})
        [child] = Tournament(self.store, self.pool, settings).forks([self.store.family(fid)])
        [event] = [e for e in self.store.events_after(0) if e["kind"] == "swarm.born" and e["family"] == child]
        return self.store.family(child), event["payload"]

    def test_a_direction_parents_fork_is_born_in_the_direction_lane(self):
        s = with_mode(self.settings, "gate")
        child, payload = self.fork("dir", s, lane="direction")
        self.assertEqual(child["spec"].get("lane"), "direction", "the spec, copied from the parent, carries the lane")
        self.assertEqual(payload["lane"], "direction")
        self.assertEqual(payload["origin"], "fork")
        self.assertEqual(dlane.born_counts(self.store, 24.0, now=self.clock())["direction"], 1)

    def test_an_alpha_fork_and_every_fork_while_the_lane_is_off_are_as_before(self):
        _, alpha = self.fork("alpha", with_mode(self.settings, "gate"))
        self.assertEqual(set(alpha), {"parent", "mechanism", "structure", "roots", "origin"}, "the release before's keys")
        _, off = self.fork("dir-off", with_mode(self.settings, "off"), lane="direction")
        self.assertNotIn("lane", off, "THE ROLLBACK: nothing is read or written")


class ChecklistAlarmLane(ProgressCase):
    """The public checklist's `gate_paused` follows the family's own lane's leakage alarm."""

    def mode(self, mode):
        (self.root / "swarm.json").write_text(json.dumps({"gym": {
            "image_checkpoint": "sbcp_synthetic_gym", "gate_checkpoint": "sbcp_synthetic_gate"}, "dlane": {"mode": mode}}))

    def looks(self, lane, passed, total=10):
        for i in range(total):
            fid = f"other-{lane}-{i}"
            self.store.add_family({"id": fid, "mechanism": f"An invented {lane} program {i}.", "structure": "long_single",
                                   "roots": ["SPY"], "dte": [7, 21]}, origin="test")
            detail = {"lane": lane, "screen": "S-C" if lane == "direction" else "S-B", "receipt": None}
            self.store.add_look(fid, 1, f"sha-{lane}-{i}", passed=i < passed, p_value=.01, detail=detail)

    def test_correlated_direction_passes_never_pause_an_alpha_familys_gate(self):
        self.family()
        self.looks("direction", 7)  # the direction alarm holds (10 looks, more than 60%); the alpha lane has no look
        self.mode("gate")
        self.assertEqual(self.read()["blocked"], "holdout_pending", "the alpha lane's gate still runs")
        self.mode("off")
        self.assertEqual(self.read()["blocked"], "holdout_pending",
                         "THE ROLLBACK: the one count over the alpha line's looks; S-C direction looks never pause alpha")
        self.looks("alpha", 4)  # the alpha line's own looks (10, more than 30% passed): the one alarm, as before D-1
        self.assertEqual(self.read()["blocked"], "gate_paused")

    def test_a_direction_familys_checklist_reads_the_direction_lanes_alarm(self):
        self.family()
        self.family("dir-family")
        spec = {**self.store.family("dir-family")["spec"], "lane": "direction"}
        self.store._exec("UPDATE families SET spec=? WHERE id=?", (json.dumps(spec), "dir-family"))
        self.assertEqual(dlane.lane_of(None, self.store.family("dir-family"), {"dlane": {"mode": "gate"}}), "direction",
                         "read from the spec alone")
        self.mode("gate")
        self.assertEqual(self.read("dir-family")["blocked"], "holdout_pending")
        self.looks("direction", 7)  # the direction lane's alarm holds; the alpha lane's does not
        self.assertEqual(self.read("dir-family")["blocked"], "gate_paused")
        self.assertEqual(self.read()["blocked"], "holdout_pending")
        self.looks("alpha", 4)  # the alpha lane's own alarm (10 looks, more than 30%) now holds too
        self.assertEqual(self.read()["blocked"], "gate_paused")


class CardBriefLane(ResearcherCase):
    """The researcher hands its settings to the card's brief: a direction card names its lane while the lane is on."""

    def brief(self, mode, card, spec=DIRECTION_SPEC):
        store, researcher, _ = self.make(mode)
        fid = store.add_family({**spec, "id": "carded"}, origin="architect")["id"]
        cards.put(store, fid, card, str(spec["structure"]))
        return researcher.brief(store.family(fid)), cards.brief_text(cards.card_of(store, fid))

    def test_a_direction_card_names_its_lane_in_the_brief_only_while_the_lane_is_on(self):
        card = {"lane": "direction", "mechanism_class": "equity_premium", "hypothesis": "an invented hypothesis"}
        on, _ = self.brief("gate", card)
        self.assertIn("YOUR FAMILY CARD", on)
        self.assertIn("- Lane: DIRECTION (fixed at birth)", on)
        self.assertIn(dlane.ALWAYS_IN_NOTE, on)
        off, plain = self.brief("off", card)
        self.assertIn(plain, off, "THE ROLLBACK: the card's brief is the release before's")
        self.assertNotIn("- Lane:", off)

    def test_an_alpha_cards_brief_is_the_release_befores_with_the_lane_on(self):
        alpha = {k: v for k, v in DIRECTION_SPEC.items() if k != "lane"}
        card = {"mechanism_class": "risk_premium", "hypothesis": "an invented hypothesis"}
        on, plain = self.brief("gate", card, alpha)
        self.assertIn(plain, on)
        self.assertNotIn("- Lane:", on)


if __name__ == "__main__":
    unittest.main()
