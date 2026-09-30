"""FAMILY CARDS (league/swarm/cards.py, release B): the schema, immutable storage, the legacy cell reading and the
card-based rebirth refusal, and the architect's use of them (league/swarm/architect.py `admit`, its request). Synthetic
families, mechanisms and lessons only."""

from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from league.swarm import cards, mechanism
from league.swarm import settings as S
from league.swarm.architect import CARD_REFUSALS_KEY, SYSTEM, Architect, tag_of
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock

CARD = {"hypothesis": "Liquidity-demanding sellers push the close below value late in the day and patient buyers are paid "
                      "to absorb it over the next session.",
        "mechanism_class": "Reversal-Liquidity", "inputs": ["underlying_price", "clock"], "holding": "days_1_3",
        "cost": {"hurdle": 0.08, "why": "two half-spreads and fees on a narrow debit vertical"},
        "comparison": "the same debit vertical opened at the same minute every session without the late-selling condition",
        "falsification": "signal entries do not beat the comparison's by t 0.5 on the mechanism sample"}
MECH = "Late-day liquidity-demanding selling pushes the close below value and it rebounds over the next session on SPY."


def proposal(slug: str, card=CARD, **kw) -> dict:
    return {"slug": slug, "mechanism": kw.pop("mechanism", MECH), "structure": kw.pop("structure", "debit_vertical"),
            "roots": kw.pop("roots", ["SPY"]), "dte": [0, 5], "rejection": "no edge", "card": card, **kw}


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.settings["population"].update(start=4, ceiling=40, floor=0)

    def arch(self) -> Architect:
        return Architect(self.store, None, self.settings, clock=self.clock)

    def bury(self, fid: str, card=None, *, reason: str, structure="debit_vertical", mechanism=MECH, roots=("SPY",)):
        """A dead family (carded when `card` is given), retired with `reason`."""
        spec = {"id": fid, "mechanism": mechanism, "structure": structure, "roots": list(roots), "dte": [0, 5]}
        if card is not None:
            spec["card_sha"] = cards.card_sha(card)
        fam = self.store.add_family(spec, origin="architect")
        if card is not None:
            cards.put(self.store, fam["id"], card, structure)
        got = self.store.retire_gym(fam["id"], reason, floor=0, source="test")
        self.assertEqual(got["status"], "retired")
        return fam["id"]


class Schema(unittest.TestCase):
    def test_a_complete_card_is_canonical(self):
        card, errors = cards.validate(CARD)
        self.assertEqual(errors, [])
        self.assertEqual((card["mechanism_class"], card["inputs"], card["ablation"]),
                         ("reversal_liquidity", ["clock", "underlying_price"], {"param": "signal_on", "off": 0}))
        again, _ = cards.validate({**CARD, "inputs": ["clock", "underlying_price", "clock"]})
        self.assertEqual(cards.card_sha(card), cards.card_sha(again), "order and repeats do not change the card")
        self.assertEqual(cards.key_text(cards.key_of(card, "long_call")), "reversal_liquidity / directional / days_1_3 / "
                                                                            "clock+underlying_price")

    def test_every_missing_or_invalid_field_is_named(self):
        card, errors = cards.validate({"mechanism_class": "luck", "inputs": ["tea_leaves"], "holding": "forever",
                                       "cost": {"hurdle": 3, "why": "x"}, "ablation": {"param": "1x", "off": None},
                                       "falsification": "it would be bad if it did not work out as hoped by all of us"})
        self.assertIsNone(card)
        text = " | ".join(errors)
        for field in ("hypothesis", "mechanism_class", "inputs", "holding", "cost.hurdle", "cost.why", "comparison", "ablation",
                      "falsification: name a concrete result"):
            self.assertIn(field, text)
        self.assertEqual(cards.validate(None)[1][0][:13], "card: missing")

    def test_rebirth_needs_a_row_a_difference_and_evidence(self):
        self.assertIn("rebirth", " ".join(cards.validate({**CARD, "rebirth": {"row": "x"}})[1]))
        card, errors = cards.validate({**CARD, "rebirth": {"row": "dead-1", "different": "d" * 50, "evidence": "e" * 50}})
        self.assertEqual((errors, card["rebirth"]["row"]), ([], "dead-1"))

    def test_inputs_written_as_text_are_read(self):
        card, errors = cards.validate({**CARD, "inputs": "underlying_price, Clock"})
        self.assertEqual((errors, card["inputs"]), ([], ["clock", "underlying_price"]))

    def test_the_ablation_value_keeps_a_whole_number_whole(self):
        card, _ = cards.validate({**CARD, "ablation": {"param": "use_signal", "off": 0.0}})
        self.assertEqual(card["ablation"], {"param": "use_signal", "off": 0})


class Storage(Case):
    def test_a_card_is_immutable_and_a_fork_reads_its_parents(self):
        card, _ = cards.validate(CARD)
        fam = self.store.add_family({"id": "a", "mechanism": MECH, "structure": "debit_vertical", "roots": ["SPY"],
                                     "card_sha": cards.card_sha(card)}, origin="architect")
        sha = cards.put(self.store, fam["id"], card, "debit_vertical")
        got = cards.card_of(self.store, "a")
        self.assertEqual((got["sha"], got["own"], got["card"]), (sha, True, card))
        for sql in ("UPDATE family_cards SET card='{}'", "DELETE FROM family_cards"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.store._exec(sql)
        with self.assertRaises(sqlite3.IntegrityError):
            cards.put(self.store, "a", {**card, "holding": "intraday"}, "debit_vertical")
        child = self.store.add_family({**dict(self.store.family("a")["spec"]), "id": "a-on-qqq", "roots": ["SPY", "QQQ"]},
                                      origin="fork", parent="a")
        fork = cards.card_of(self.store, child["id"])
        self.assertEqual((fork["sha"], fork["own"], fork["family"]), (sha, False, "a"))
        self.assertIsNone(cards.card_of(self.store, "nobody"))

    def test_evidence_is_append_only(self):
        cards.add_evidence(self.store, "a", "sha", 1, "mechanism_test", "failed", {"t": -1.0})
        cards.add_evidence(self.store, "a", "sha", 2, "mechanism_test", "passed", {"t": 1.0})
        self.assertEqual([r["verdict"] for r in cards.evidence(self.store, "a")], ["failed", "passed"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._exec("UPDATE card_evidence SET verdict='passed'")

    def test_making_the_tables_never_commits_a_callers_transaction(self):
        fresh = SwarmStore(Path(self.dir.name) / "fresh", clock=self.clock)
        self.addCleanup(fresh.close)
        with self.assertRaises(RuntimeError):
            with fresh.atomic():
                fresh.put("probe", 1)
                cards.ensure(fresh)
                raise RuntimeError("roll back")
        self.assertIsNone(fresh.get("probe"), "the table DDL ran inside the caller's transaction, which rolled back whole")
        fresh.add_family({"id": "b", "mechanism": MECH, "structure": "debit_vertical", "roots": ["SPY"]}, origin="architect")
        cards.put(fresh, "b", cards.validate(CARD)[0], "debit_vertical")  # the rolled-back tables are made again
        self.assertEqual(cards.card_of(fresh, "b")["family"], "b")

    def test_a_read_only_store_reads_what_a_writer_made(self):
        card, _ = cards.validate(CARD)
        self.store.add_family({"id": "a", "mechanism": MECH, "structure": "debit_vertical", "roots": ["SPY"]}, origin="architect")
        cards.put(self.store, "a", card, "debit_vertical")
        reader = SwarmStore(Path(self.dir.name), readonly=True)
        self.addCleanup(reader.close)
        self.assertEqual(cards.card_of(reader, "a")["card"], card)
        empty = SwarmStore(Path(self.dir.name) / "empty", clock=self.clock)
        empty.close()
        reader2 = SwarmStore(Path(self.dir.name) / "empty", readonly=True)
        self.addCleanup(reader2.close)
        self.assertIsNone(cards.card_of(reader2, "a"))


class LegacyCells(unittest.TestCase):
    def test_a_legacy_mechanism_is_read_into_a_cell(self):
        key = cards.infer_key("Oversold closes rebound over the next session as forced selling ends.", "long_call", [0, 5])
        self.assertEqual(key, {"class": "reversal_liquidity", "inputs": None, "family": "directional", "holding": "days_1_3"})
        event = cards.infer_key("The front expiry is rich before FOMC and CPI releases.", "calendar", [1, 30])
        self.assertEqual((event["class"], event["family"], event["holding"]), ("event_premium", "time_spread", "days_11_plus"))
        self.assertEqual(cards.infer_key("Pays when it pays.", "iron_condor", [0, 1]), None)
        self.assertEqual(cards.infer_key("A trend that persists.", "long_put", [0, 1])["holding"], "days_1_3", "from the dte")

    def test_legacy_rows_match_without_inputs(self):
        new = cards.key_of(cards.validate(CARD)[0], "long_call")
        self.assertTrue(cards.matches(new, {"class": "reversal_liquidity", "family": "directional", "holding": "days_1_3",
                                            "inputs": None}))
        self.assertTrue(cards.matches(new, {**new, "inputs": ["clock", "share_volume", "underlying_price"]}))
        self.assertFalse(cards.matches(new, {**new, "inputs": ["underlying_price"]}), "a new input is a new information set")
        self.assertFalse(cards.matches(new, {**new, "holding": "intraday"}))


class Rebirth(Case):
    def test_a_card_in_a_refuted_cell_needs_a_valid_rebirth(self):
        card, _ = cards.validate(CARD)
        dead = self.bury("rebound-old", card, reason=mechanism.MECHANISM_CAUSE.format(n=3))
        self.bury("rebound-idle", card, reason="Retired by the idle rule, a limit on how long a family may research; it is a "
                                                 "time limit, not a finding that the mechanism has no edge")
        index = cards.RebirthIndex(self.store, self.settings)
        self.assertEqual([r["row"] for r in index.rows], [dead], "only mechanism verdicts count, never an untested death")
        refused = index.check(card, "long_put", MECH)
        self.assertFalse(refused["ok"])
        self.assertEqual((refused["row"], refused["tag"]), (dead, "MECHANISM"))
        self.assertIn("needs card.rebirth", refused["reason"])
        self.assertIn("Mechanism verdict MECHANISM", refused["lesson"])
        self.assertTrue(index.check({**card, "inputs": ["clock", "share_volume", "underlying_price"]}, "debit_vertical")["ok"],
                        "a new input is outside the dead card's cell")
        self.assertTrue(index.check(card, "iron_condor")["ok"], "another structure family is another cell")
        restated = {**card, "rebirth": {"row": dead, "different": "the same late day selling and rebound now on QQQ calls "
                                                                  "with a wider strike and two weeks", "evidence": "e" * 50}}
        self.assertIn("restates", index.check(restated, "debit_vertical", MECH)["reason"])
        wrong = {**card, "rebirth": {"row": "someone-else", "different": "d" * 50, "evidence": "e" * 50}}
        self.assertIn("not one of the rows", index.check(wrong, "debit_vertical")["reason"])
        good = {**card, "rebirth": {"row": dead, "different": "conditions on dealer inventory imbalance measured from quote "
                                                              "size asymmetry, which the dead family never read",
                                    "evidence": "its lesson shows entries lost only on days quote sizes were balanced"}}
        self.assertTrue(index.check(good, "debit_vertical", MECH)["ok"])
        index.note_birth(good)
        index.note_birth(good)
        self.assertIn("already backed 2", index.check(good, "debit_vertical", MECH)["reason"])
        self.assertTrue(any(line.startswith("reversal_liquidity / directional / days_1_3: 1 rows (1 carded)")
                            for line in index.cells()))

    def test_a_legacy_row_is_read_by_its_text(self):
        self.bury("old-dip", reason="The dip-bounce mechanism is conclusively refuted on every root tested",
                  mechanism="Oversold closes rebound over the next session as forced selling ends.", structure="long_call")
        index = cards.RebirthIndex(self.store, self.settings)
        [row] = index.rows
        self.assertEqual((row["tag"], row["legacy"], row["key"]["class"]), ("REFUTED", True, "reversal_liquidity"))
        self.assertFalse(index.check(cards.validate(CARD)[0], "debit_vertical")["ok"])


class TheArchitect(Case):
    def test_a_proposal_without_a_complete_card_is_not_born(self):
        a = self.arch()
        born = a.admit([proposal("no-card", card=None), proposal("half", card={"hypothesis": CARD["hypothesis"]}),
                        proposal("whole")])
        self.assertEqual(born, ["whole"])
        self.assertEqual([r["slug"] for r in a.card_refused], ["no-card", "half"])
        self.assertIn("mechanism_class", a.card_refused[1]["why"])
        fam = self.store.family("whole")
        self.assertEqual(fam["spec"]["card_sha"], cards.card_of(self.store, "whole")["sha"])
        born_event = [e for e in self.store.events_after(0) if e["kind"] == "swarm.born"][-1]
        self.assertEqual((born_event["payload"]["card"]["class"], born_event["payload"]["card"]["rebirth"]),
                         ("reversal_liquidity", None))

    def test_cards_can_be_left_optional(self):
        self.settings["architect"] = {**self.settings.get("architect", {}), "require_card": False}
        self.assertEqual(self.arch().admit([proposal("legacy", card=None)]), ["legacy"])
        self.assertIsNone(cards.card_of(self.store, "legacy"))
        self.assertNotIn("FAMILY CARD VOCABULARY", self.arch().card_block())

    def test_a_refuted_cell_is_refused_until_a_rebirth_names_its_row_and_continues_its_lineage(self):
        card, _ = cards.validate(CARD)
        dead = self.bury("rebound-old", card, reason=mechanism.MECHANISM_CAUSE.format(n=3))
        a = self.arch()
        self.assertEqual(a.admit([proposal("rebound-new", mechanism="Sellers overshoot late; the next session repairs "
                                                                   "the dislocation on the index ETF.")]), [])
        [refusal] = a.card_refused
        self.assertEqual((refusal["row"], refusal["matched"]), (dead, 1))
        a.store.put(CARD_REFUSALS_KEY, {"at": "t", "items": a.card_refused})
        block = a.card_block()
        for text in ("FAMILY CARD VOCABULARY", "REFUTED CELLS", "reversal_liquidity / directional / days_1_3",
                     "YOUR LAST PASS'S PROPOSALS REFUSED", f"Lesson of {dead}"):
            self.assertIn(text, block)
        reborn = {**CARD, "rebirth": {"row": dead, "different": "conditions on dealer inventory imbalance measured from quote "
                                                                  "size asymmetry, which the dead family never read",
                                      "evidence": "its lesson shows entries lost only on days quote sizes were balanced"}}
        born = a.admit([proposal("rebound-new", card=reborn, mechanism="Dealer inventory imbalance after late selling "
                                                                        "predicts which rebounds complete next session.")])
        self.assertEqual(born, ["rebound-new"])
        born_event = [e for e in self.store.events_after(0) if e["kind"] == "swarm.born"][-1]
        self.assertEqual((born_event["payload"]["card"]["rebirth"], born_event["payload"]["card"]["text_cell"]["rows"]), (dead, 1),
                         "the birth records the cell its own text reads as, for the audit")
        fam = self.store.family("rebound-new")
        self.assertEqual(fam["parent"], dead, "a rebirth on the row's own slice continues its lineage: no fresh count")
        self.assertIn("Mechanism verdict MECHANISM", fam["spec"]["lessons"][0], "it is born with the lesson it re-enters")
        self.settings["architect"] = {**self.settings.get("architect", {}), "card_rebirth": "off"}
        self.assertEqual(self.arch().admit([proposal("rebound-free", mechanism="Another late-day selling rebound on the "
                                                                             "ETF, with the refusal switched off.")]),
                         ["rebound-free"])

    def test_the_system_prompt_and_tags_know_the_card(self):
        self.assertIn('"card": {"hypothesis"', SYSTEM)
        self.assertIn("REFUTED CELL", SYSTEM)
        fam = {"retire_reason": mechanism.MECHANISM_CAUSE.format(n=3)}
        self.assertEqual(tag_of({"family": "x", "lesson": ""}, fam), "MECHANISM")
        untestable = {"retire_reason": mechanism.UNTESTABLE_CAUSE.format(n=4)}
        self.assertEqual(tag_of({"family": "x", "lesson": ""}, untestable), "IDLE", "untestable is untested, not a finding")
        from league.swarm import public
        self.assertEqual(public.note_text(mechanism.MECHANISM_CAUSE.format(n=3)),
                         "Retired after its signal failed the pre-registered mechanism tests against the comparison its card "
                         "declared.", "the site publishes the plain first sentence")


if __name__ == "__main__":
    unittest.main()
