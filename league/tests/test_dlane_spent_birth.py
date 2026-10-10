"""THE RATION AT BIRTH (Oct 10, 2026; league/swarm/dlane.py `birth_spent`, league/swarm/architect.py `admit`): a DIRECTION card
whose birth would continue a lineage that has spent its one Validation try (or its one holdout look) is refused by the
card checks, named in the next request, and never born. Measured on the House on Oct 10: about half of the lane's births
joined such a lineage (a parent on the slice with the same idea, or a long_single's twins) and the tournament retired them
on `dlane.SPENT_TRY` 15-60 minutes later without a try. So is one whose try a living member claims (the review): one
born earlier in the same pass, or one whose best awaits Validation (its job out too). A fresh idea, a lineage with its
try left, every alpha card and the lane off are born as before.

Every family, mechanism and figure here is invented.
"""

from __future__ import annotations

import unittest

from league.swarm import cards, dlane
from league.swarm.architect import CARD_REFUSALS_KEY
from league.swarm.researcher import awaiting_validation
from league.tests.swarm_fakes import result
from league.tests.test_dlane_births import DIR, DMECH, OFF, TREND, LaneCase, Router
from league.tests.test_swarm_cards import CARD, MECH, proposal

#: A retirement that is no mechanism verdict (IDLE): its row binds no card, so the cards here meet only the ration.
IDLE = ("Retired by the idle rule, a limit on how long a family may research; it is a time limit, not a finding that the "
        "mechanism has no edge")
CODE = "# {fid}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\ndef decide(ctx):\n    return []\n"
OTHER = "Buy a call after three down closes in a row when the index sits above its own 200-day average, held a week."
#: DMECH reworded: the same idea (`same_idea`), not the same text (the architect's `living` check reads its start).
AGAIN = "Hold a cheap call a week to rent the index's drift while implied vol sits calm against its own trailing year."


class SpentBirth(LaneCase):
    def setUp(self):
        super().setUp()
        self.settings["architect"]["require_card"] = True

    def family(self, fid, *, structure="long_single", mechanism=DMECH, lane="direction", parent=None, card=DIR,
               tried=False, status="ok", retire=True):
        """A direction family (carded with `card`) with one version; `tried`: a Validation run at 1.0x of it (`status`);
        `retire`: retired by the idle rule a minute after the last."""
        self.clock.t += 60
        spec = {"id": fid, "mechanism": mechanism, "structure": structure, "roots": ["SPY"], "dte": [4, 10]}
        if lane == "direction":
            spec["lane"] = "direction"
        made = cards.validate(card, structure, roots=["SPY"], settings=self.settings)[0] if card is not None else None
        if made is not None:
            spec["card_sha"] = cards.card_sha(made)
        self.store.add_family(spec, origin="architect", parent=parent)
        if made is not None:
            cards.put(self.store, fid, made, structure)
        v = self.store.add_version(fid, CODE.format(fid=fid), {}, author="r")
        if tried:
            self.store.add_run(fid, v["n"], result(fid, window="validation", status=status), window="validation",
                               stress=1.0, purpose="validation")
        if retire:
            self.assertEqual(self.store.retire_gym(fid, IDLE, floor=0, source="test")["status"], "retired")
        return fid

    def links(self):
        return sorted((r["a"], r["b"]) for r in self.store._all("SELECT a,b FROM lineage_links"))

    def again(self, slug="dir-again", **kw):
        return proposal(slug, card=kw.pop("card", DIR), structure=kw.pop("structure", "long_single"), roots=["SPY"],
                        mechanism=kw.pop("mechanism", DMECH), **kw)

    # ------------------------------------------------------------------------------------------- the refusal
    def test_a_direction_card_continuing_a_spent_lineage_is_refused_named_and_fed_back(self):
        self.family("dir-old", tried=True)
        self.assertEqual(dlane.birth_spent(self.store, ["dir-old"], self.settings),
                         {"spent": "try", "family": "dir-old", "version": 1, "lineage": "dir-old"})
        out = self.arch(Router([self.again()])).run()
        self.assertEqual(out["born"], [])
        self.assertIsNone(self.store.family("dir-again"), "no birth")
        self.assertEqual(self.born(), [])
        self.assertEqual(self.links(), [])
        self.assertEqual((out["card_refused"]["spent_lineage"], out["card_refused"]["rebirth"],
                          out["card_refused"]["incomplete"]), (1, 0, 0))
        why = out["card_refused"]["items"][0]["why"]
        self.assertEqual(why, "this idea continues lineage dir-old, whose one Validation try is spent (dir-old v1): one "
                              "Validation try and one holdout look a direction lineage, and the same idea proposed again "
                              "gets no new one; propose a mechanism-level new idea on another slice or a new mechanism")
        self.assertEqual(self.store.get(CARD_REFUSALS_KEY)["items"][0]["slug"], "dir-again")
        # The next request carries it among the card refusals, the path every other card refusal takes.
        block = self.arch().card_block()
        head = "YOUR LAST PASS'S PROPOSALS REFUSED BY THE CARD CHECKS"
        self.assertIn(head, block)
        self.assertIn(f"- dir-again: {why}", block[block.index(head):])
        # The lane's quota was asked and kept its place: the reserved direction births stay unfilled, not refused.
        self.assertEqual((out["lane_births"], out["lane_refused"]["direction"]), ({"alpha": 0, "direction": 0}, 0))

    def test_what_it_refuses_is_what_the_tournament_would_retire(self):
        """`birth_spent` before the birth reads what `lineage_spent` reads after it, on each lineage shape here."""
        self.family("tried", tried=True)
        self.family("untried")
        self.family("gym-error", tried=True, status="error")
        self.family("looked", tried=True)
        sha = "f" * 64
        self.store.add_look("looked", 1, sha, passed=False, p_value=0.5, detail={})
        self.family("in-flight", retire=False)
        self.store.set_state("in-flight", look_inflight={"sha": "e" * 64, "n": 1})
        for parent, spent in (("tried", "try"), ("untried", None), ("gym-error", None), ("looked", "look"),
                              ("in-flight", "look")):
            got = dlane.birth_spent(self.store, [parent], self.settings)
            self.assertEqual(got and got["spent"], spent, parent)
            child = self.store.add_family({"id": f"{parent}-child", "mechanism": DMECH, "structure": "long_single",
                                           "roots": ["SPY"], "lane": "direction"}, origin="architect", parent=parent)
            after = dlane.lineage_spent(self.store, child, self.settings)
            self.assertEqual(after, {"try": dlane.SPENT_TRY, "look": dlane.SPENT_LOOK, None: None}[spent], parent)
        self.assertEqual(dlane.birth_spent(self.store, ["looked"], self.settings),
                         {"spent": "look", "family": "looked", "version": 1, "lineage": "looked"})
        self.assertEqual(dlane.birth_spent(self.store, ["in-flight"], self.settings),
                         {"spent": "look", "family": "in-flight", "version": 1,
                          "lineage": "in-flight"})
        self.assertIsNone(dlane.birth_spent(self.store, [], self.settings))
        self.assertIsNone(dlane.birth_spent(self.store, ["tried"], {"dlane": OFF}), "the lane off reads nothing")

    def test_a_long_single_whose_twins_link_a_spent_lineage_is_refused(self):
        """The parent's own lineage is clean; the twin the long_single would link holds the spent try."""
        self.family("put-old", structure="long_put", card=None, tried=True)
        self.family("call-new", structure="long_call", card=None)
        self.assertIsNone(dlane.birth_spent(self.store, ["call-new"], self.settings), "the parent alone has its try")
        a = self.arch()
        self.assertEqual(a.admit([self.again()]), [])
        self.assertEqual(a.card_refused[0]["spent"], "try")
        # The lineage named is the one that holds the spent try (the twin's), not the parent's, which still has its own.
        self.assertIn("continues lineage put-old, whose one Validation try is spent (put-old v1)",
                      a.card_refused[0]["why"])
        self.assertEqual(self.links(), [], "a refused card links no lineage")

    def test_a_family_the_architect_may_not_read_is_never_named(self):
        text = dlane.spent_birth_text({"spent": "try", "family": "g-1a2b3c4d", "version": 2}, "g-1a2b3c4d",
                                      frozenset({"g-1a2b3c4d"}))
        self.assertTrue(text.startswith("this idea continues a lineage, whose one Validation try is spent (by an earlier "
                                        "family)"), text)
        self.assertNotIn("g-1a2b3c4d", text)
        text = dlane.spent_birth_text({"spent": "claim", "family": "g-1a2b3c4d", "version": 2, "lineage": "g-1a2b3c4d",
                                       "born": False}, None, frozenset({"g-1a2b3c4d"}))
        self.assertTrue(text.startswith("this idea continues a lineage, whose one Validation try is claimed (by a "
                                        "living family)"), text)
        self.assertNotIn("g-1a2b3c4d", text)
        self.assertFalse(any(ch.isdigit() for ch in dlane.SPENT_BIRTH), "a public reason: no figure")

    # ------------------------------------------------------------------------------------------- a claimed try
    def test_a_second_card_of_one_idea_in_one_pass_is_refused_the_first_claims_the_try(self):
        """The review's race: both continue the dead, untried `dir-old`; born, the second retired on SPENT_TRY once the
        first's Validation run landed (one try a lineage, and the tournament sends one member a round)."""
        self.family("dir-old")
        out = self.arch(Router([self.again("dir-a"), self.again("dir-b", mechanism=AGAIN)])).run()
        self.assertEqual(out["born"], ["dir-a"])
        self.assertIsNone(self.store.family("dir-b"), "no birth")
        self.assertEqual((out["card_refused"]["spent_lineage"], out["card_refused"]["rebirth"]), (1, 0))
        self.assertEqual(out["card_refused"]["items"][0]["why"],
                         "this idea continues lineage dir-old, whose one Validation try is claimed (dir-a, born in the "
                         "same pass): one Validation try and one holdout look a direction lineage, and the same idea "
                         "proposed again gets no new one; propose a mechanism-level new idea on another slice or a new "
                         "mechanism")

    def test_a_truncated_answers_retry_reads_the_first_answers_births(self):
        a = self.arch()
        a.pass_born = []  # as `run` sets it for the pass: its first admit and its retry's
        self.family("dir-old")
        self.assertEqual(a.admit([self.again("dir-a")]), ["dir-a"])
        self.assertEqual(a.admit([self.again("dir-b", mechanism=AGAIN)]), [])
        self.assertEqual((a.card_refused[0]["spent"], a.pass_born), ("claim", ["dir-a"]))
        # A pass's births are its own: a later pass (or a call outside one) reads a living member by its best alone, so
        # `dir-a` without one claims nothing there (it may die without a try; the tournament still retires the loser).
        self.assertEqual(self.arch().admit([self.again("dir-c", mechanism=AGAIN)]), ["dir-c"])

    def test_a_living_member_whose_best_awaits_validation_claims_the_try(self):
        """The review's in-flight try: a living member's best awaits Validation (its job may be out, no run landed)."""
        self.family("dir-old")
        self.family("dir-live", mechanism=AGAIN, parent="dir-old", retire=False)
        self.assertEqual(self.store.family("dir-live")["lineage"], "dir-old")

        def spent():
            return dlane.birth_spent(self.store, ["dir-old"], self.settings, awaiting=awaiting_validation)

        # Still without a best: no claim (it may die without a try).
        self.assertIsNone(spent())
        self.store.update_family("dir-live", best_version=1)
        self.assertEqual(spent(), {"spent": "claim", "family": "dir-live", "version": 1, "lineage": "dir-old",
                                   "born": False})
        self.assertIsNone(dlane.birth_spent(self.store, ["dir-old"], self.settings), "no reader, no such claim")
        a = self.arch()
        self.assertEqual(a.admit([self.again()]), [])
        self.assertIn("continues lineage dir-old, whose one Validation try is claimed (dir-live v1 awaits Validation)",
                      a.card_refused[0]["why"])
        # A best that lost at 1.5x awaits nothing: no claim.
        self.store.set_state("dir-live", robust_failed=[1])
        self.assertIsNone(spent())
        # Its run lands: the try is spent, whatever the claim read.
        self.store.add_run("dir-live", 1, result("dir-live", window="validation"), window="validation", stress=1.0,
                           purpose="validation")
        self.assertEqual(spent(), {"spent": "try", "family": "dir-live", "version": 1, "lineage": "dir-old"})

    # ------------------------------------------------------------------------------------------- what is born
    def test_a_fresh_idea_on_the_slice_is_born_as_a_new_lineage(self):
        self.family("dir-old", tried=True)
        born = self.arch().admit([self.again("dir-fresh", mechanism=OTHER)])
        self.assertEqual(born, ["dir-fresh"])
        fam = self.store.family("dir-fresh")
        self.assertEqual((fam["parent"], fam["lineage"], fam["spec"]["prior_lineage"]), (None, "dir-fresh", "dir-old"))
        self.assertIsNone(dlane.lineage_spent(self.store, fam, self.settings))

    def test_a_lineage_with_its_try_left_is_continued(self):
        self.family("dir-old")  # no Validation run
        self.family("dir-err", mechanism=f"{DMECH} Again.", tried=True, status="error")  # the Gym could not run it
        born = self.arch().admit([self.again()])
        self.assertEqual(born, ["dir-again"])
        fam = self.store.family("dir-again")
        self.assertEqual(fam["parent"], "dir-err", "the newest dead family of the idea on the slice")
        self.assertIsNone(dlane.lineage_spent(self.store, fam, self.settings))
        self.assertTrue(dlane.try_open(self.store, fam, 1, self.settings))

    def test_an_alpha_card_continues_a_tried_lineage_as_before(self):
        self.family("alpha-old", structure="debit_vertical", mechanism=MECH, lane="alpha", card=CARD, tried=True)
        out = self.arch(Router([proposal("alpha-again", card=CARD)])).run()
        self.assertEqual(out["born"], ["alpha-again"])
        self.assertEqual(self.store.family("alpha-again")["parent"], "alpha-old")
        self.assertNotIn("spent_lineage", out["card_refused"])

    def test_the_lane_off_continues_the_spent_lineage_as_before(self):
        self.family("dir-old", card=TREND, tried=True)
        self.settings["dlane"] = dict(OFF)
        out = self.arch(Router([self.again(card=TREND)])).run()
        self.assertEqual(out["born"], ["dir-again"], "`lane` ignored: born as before")
        self.assertEqual(self.store.family("dir-again")["parent"], "dir-old")
        self.assertNotIn("spent_lineage", out["card_refused"])
        self.assertEqual(out["card_refused"]["items"], [])


if __name__ == "__main__":
    unittest.main()
