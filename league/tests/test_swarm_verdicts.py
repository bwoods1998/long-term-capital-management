"""R11-1 and R11-4's swarm rule (Sept 29, 2026): an idle-rule death is filed under the verdict of its Train record (DRIFT,
STRESS, THIN, EXHAUSTED; IDLE only for the untested), the digest and the strategist read those verdicts, a family that
holds with a Train record behind it is offered `retire` (SELF-REFUTED), the one-time graveyard migration re-heads the
rows already buried, and a validation that met six checks holds its family out of the dormancy clause until the
operator clears it."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from league.swarm import architect as arch
from league.swarm import public
from league.swarm.architect import SEAL_KEY, GraveyardDigest, parse_lesson, tag_of
from league.swarm.researcher import (IDLE_CAUSE, SCREENED, SELF_REFUTED, VERDICT_WORDS, extension_held, idle_cause, idle_dead,
                                     train_record)
from league.swarm.store import SwarmStore, dumps
from league.swarm.strategist import Strategist
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import result
from league.tests.test_swarm_graveyard_digest import IDLE_REASON, Graves, StoreCase, lesson
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import RoundCase, strong, weak
from scripts import extension_hold, graveyard_verdicts

DORMANT = "It made no new Gym evaluation in its last 12 cycles (only stored results, holds and refused runs)"


def train_row(store, fid, n, *, trades, eligible):
    store.add_run(fid, n, {"run_id": f"r-{fid}-{n}-{trades}-{eligible}", "status": "ok", "trials": 1,
                           "summary": {"trades": trades, "train_eligible": eligible}}, window="train", stress=1.0, purpose="train")


class Records(RoundCase):
    """`train_record`: what the family's Train runs showed (Train figures only)."""

    def test_each_screen(self):
        cases = {
            "scored": ({"best_train": -0.2}, {}, None),
            "drift": ({}, {"drift_failed": {"3": "t 0.4", "5": "t 0.1"}, "robust_failed": [3, 5, 7]}, None),
            "drift ": ({}, {"robust_failed": [2], "robust_why": {"2": "fails the drift screen: t 0.3"}}, None),
            "stress": ({}, {"robust_failed": [2, 4], "drift_failed": {"6": "t 0.2"},
                            "robust_why": {"2": "lost money on Train at 1.5x the half-spread",
                                           "4": "lost money on Train at 1.5x the half-spread"}}, None),
            "unresolved": ({}, {"robust_failed": [2], "robust_why": {"2": "its 1.5x run failed 3 times"}}, None),
            "unresolved ": ({}, {"robust_failed": [2]}, None),
            "thin": ({}, {}, (12, False)),
            "untested": ({}, {}, (0, False)),
            "untested ": ({}, {}, None),
        }
        for screen, (fields, state, run) in cases.items():
            fid = f"f-{screen.strip()}-{len(screen)}"
            self.family(fid)
            if fields:
                self.store.update_family(fid, **fields)
            if state:
                self.store.set_state(fid, **state)
            if run is not None:
                train_row(self.store, fid, 1, trades=run[0], eligible=run[1])
            self.assertEqual(train_record(self.store, self.store.family(fid))["screen"], screen.strip(), screen)
        self.family("ties")
        self.store.set_state("ties", robust_failed=[1, 2], drift_failed={"1": "t 0"})
        self.assertEqual(train_record(self.store, self.store.family("ties"))["screen"], "drift", "a tie reads as drift")

    def test_eligible_from_the_state_or_a_row(self):
        self.family("a")
        self.assertFalse(train_record(self.store, self.store.family("a"))["eligible"])
        train_row(self.store, "a", 1, trades=80, eligible=True)
        record = train_record(self.store, self.store.family("a"))
        self.assertEqual((record["screen"], record["eligible"]), ("thin", True), "eligible once, no version stands now")
        self.family("b")
        self.store.set_state("b", train_candidates=[[0.4, 1, "run-x"]])
        self.assertTrue(train_record(self.store, self.store.family("b"))["eligible"])

    def test_the_words_and_their_public_sentence(self):
        self.assertEqual(idle_cause("untested"), IDLE_CAUSE)
        for screen, words in VERDICT_WORDS.items():
            cause = idle_cause(screen)
            self.assertEqual(cause, f"{SCREENED}. {words}")
            self.assertNotIn("not a finding", cause)
            self.assertEqual(public.note_text(f"{DORMANT}. {cause}"), f"{SCREENED}.", "no figure reaches the public cause")


class Tags(StoreCase):
    def test_each_verdict_tags_its_row_and_its_boilerplate_is_stripped(self):
        for screen, tag in {"drift": "DRIFT", "stress": "STRESS", "thin": "THIN", "scored": "EXHAUSTED"}.items():
            reason = f"{DORMANT}. {idle_cause(screen)}"
            self.assertEqual(tag_of({"family": "x", "lesson": ""}, {"retire_reason": reason}), tag)
            gone = lesson(reason, train="None", val="never validated", notes=("Refuted: the fade loses.",))
            self.assertEqual(tag_of({"family": "gone", "lesson": gone}, None), tag, "a row whose family row is gone")
            p = parse_lesson({"family": "a", "lesson": gone, "structure": "long_call", "roots": '["SPY"]'},
                             {"retire_reason": reason})
            self.assertNotIn("Idle verdict", p["verdict"] + " ".join(p["notes"]), "the tag says it")
            self.assertNotIn("screened", p["verdict"])
            self.assertEqual(p["notes"][0], "Refuted: the fade loses.")
        self.assertEqual(tag_of({"family": "x", "lesson": ""}, {"retire_reason": IDLE_REASON}), "IDLE", "the untested keep IDLE")
        self.assertEqual(tag_of({"family": "x", "lesson": ""}, {"retire_reason": f"{SELF_REFUTED}: costs win."}), "SELF-REFUTED")
        self.assertEqual(tag_of({"family": "x", "lesson": ""}, {"retire_reason": "The mechanism is refuted"}), "REFUTED")

    def test_the_header_says_the_verdicts_are_tested_and_the_format_moved(self):
        self.assertEqual(arch.DIGEST_FORMAT, 5, "4 for R11-1's verdicts, 5 for release B's MECHANISM tag")
        for words in ("DRIFT = its eligible versions failed the drift screen", "THIN = it traded", "EXHAUSTED =",
                      "SELF-REFUTED =", "TESTED findings", "Only IDLE = never traded on Train: untested", "MECHANISM ="):
            self.assertIn(words, arch.DIGEST_HEADER)
        self.store.put(SEAL_KEY, {"format": 2, "tokens": 100000, "tail_share": 0.15, "through": ["", ""], "sha": "x",
                                  "level": 0, "op_scale": None})
        self.graves.bury("a")
        self.assertEqual(GraveyardDigest(self.store, self.settings).snapshot().resealed, "the format or the budget changed")

    def test_the_ladder_shortens_verdict_rows_as_it_shortened_idle_rows_and_names_them(self):
        for i in range(12):
            screen = ("drift", "stress", "thin", "untested")[i % 4]
            reason = f"{DORMANT}. {idle_cause(screen)}"
            self.graves.bury(f"v-{i}", reason=reason, train="None", val="never validated")
        rows = GraveyardDigest(self.store, self.settings).rows()
        self.assertEqual(sorted({p["tag"] for p in rows}), ["DRIFT", "IDLE", "STRESS", "THIN"])
        text = arch._render(rows, 2, 0.3)
        for name in ("DRIFT, failed the drift screen on Train, debit_vertical (3): v-0, v-4, v-8",
                     "STRESS, lost at 1.5x the half-spread on Train, debit_vertical (3)",
                     "THIN, too few trades in a Train year, debit_vertical (3)",
                     "IDLE, never an eligible Train version, debit_vertical (3)"):
            self.assertIn(name, text)
        self.assertIn("v-0 [debit_vertical SPY] DRIFT v12/40t train None val never: ", arch._render(rows, 1, 0.3),
                      "level 1: one line each, its verdict on it")
        # The same rows filed as the old IDLE rows take about the same room at every level: the ladder does not move.
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        store = SwarmStore(Path(other.name))
        self.addCleanup(store.close)
        graves = Graves(store)
        for i in range(12):
            graves.bury(f"v-{i}", reason=IDLE_REASON, train="None", val="never validated")
        before = GraveyardDigest(store, self.settings).rows()
        for level in (0, 1, 2, 3, arch.LIST_LEVEL):
            self.assertLess(abs(len(arch._render(rows, level, 0.3)) - len(arch._render(before, level, 0.3))), 400, level)


class IdleDeaths(RoundCase):
    """The tournament files each idle death under its Train record's verdict."""

    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=8, floor=0)
        self.settings["researcher"]["dormant_cycles"] = 12

    def test_dormancy_deaths_carry_their_verdicts(self):
        for fid in ("drifty", "thin", "never"):
            self.family(fid)
            self.store.update_family(fid, validated_version=1)  # nothing awaits validation
            self.store.set_state(fid, dormant_cycles=12)
        self.store.set_state("drifty", robust_failed=[1], drift_failed={"1": "t 0.2"})
        train_row(self.store, "thin", 1, trades=9, eligible=False)
        out = Tournament(self.store, self.pool, self.settings, clock=self.clock).idle_pass()
        why = {r["family"]: r["why"] for r in out["retired"]}
        self.assertEqual(why["drifty"], f"{DORMANT}. {idle_cause('drift')}")
        self.assertEqual(why["thin"], f"{DORMANT}. {idle_cause('thin')}")
        self.assertEqual(why["never"], f"{DORMANT}. {IDLE_CAUSE}")
        tags = {p["id"]: p["tag"] for p in GraveyardDigest(self.store, self.settings).rows()}
        self.assertEqual(tags, {"drifty": "DRIFT", "thin": "THIN", "never": "IDLE"})
        causes = sorted(e["payload"]["cause"] for e in self.store.events_after(0) if e["kind"] == "swarm.retired")
        self.assertEqual(causes, sorted([IDLE_CAUSE, f"{SCREENED}.", f"{SCREENED}."]))


class TheStrategistReadsTheScreen(RoundCase):
    def test_since_section_rows_carry_the_screen(self):
        self.settings["architect"]["agenda_locked"] = "1. THE VERIFIER: fixed."
        for fid in ("a", "b"):
            self.store.add_family({"id": fid, "mechanism": "A mechanism long enough to be a family's.", "structure": "long_call",
                                   "roots": ["TLT"], "dte": [1, 5]}, origin="architect")
        self.store.update_family("a", best_train=0.3)
        train_row(self.store, "b", 1, trades=4, eligible=False)
        s = Strategist(self.store, self.router, self.settings, clock=self.clock)
        rows = s._since_section({"accepted": False}, self.store.families())["families"]
        self.assertEqual({r["family"]: r["screen"] for r in rows}, {"a": "scored", "b": "thin"})
        self.assertTrue(all("eligible_train_version" not in r for r in rows))
        self.assertIn("are TESTED findings; only IDLE (never traded on Train) is untested", s.system())
        self.assertIn("screen, what its Train record showed", s.packet())


class HoldOffer(ResearcherCase):
    """THE HOLD OFFER: three holds in a row offer `retire` on the family's REVISE turn, whatever its trial count (F1; with
    `researcher.retire_hold_untested` false, only with an eligible Train run or ten trials behind it, as before), down to
    `population.floor`; its lesson is SELF-REFUTED."""

    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=50, floor=0)  # below the start: the old rule would never offer it
        self.pool.answer = lambda job: result(job.name, roots=job.roots, trades=10)  # traded, never eligible
        self.cancelled = []
        self.pool.cancel_family = self.cancelled.append
        self.fid = self.fam["id"]

    def held(self, streak, trials=0):
        self.store.set_state(self.fid, hold_streak=streak)
        if trials:
            self.store.update_family(self.fid, trials=trials)
        return self.store.family(self.fid)

    def test_offered_after_three_holds_whatever_the_trial_count(self):
        """F1 (Oct 3): six of the eight living families had 3 to 9 trials, no eligible Train run and notes that said
        "holding for retirement"; the offer no longer asks for the Train record."""
        self.assertIs(self.settings["researcher"]["retire_hold_untested"], True, "the default")
        self.researcher().cycle(self.fid)  # the starter: one ineligible run
        r = self.researcher()
        self.assertFalse(r.hold_offer(self.held(2, trials=40)), "two holds")
        self.assertTrue(r.hold_offer(self.held(3, trials=1)), "three holds, one trial, no eligible run: offered")
        self.assertTrue(r.can_retire(self.store.family(self.fid)))
        self.settings["researcher"]["retire_hold_cycles"] = 0
        self.assertFalse(r.hold_offer(self.store.family(self.fid)), "0 turns it off")
        self.settings["researcher"]["retire_hold_cycles"] = 3
        self.store.set_state(self.fid, validation_version=1, extension_hold={"version": 1, "checks": "6/8", "at": "x"})
        self.assertFalse(r.hold_offer(self.store.family(self.fid)), "a near-miss waits for its extension result")
        self.store.set_state(self.fid, extension_hold=None)
        self.store.update_family(self.fid, band="candidate")
        self.assertFalse(r.hold_offer(self.store.family(self.fid)), "the Gym band only")
        self.store.update_family(self.fid, band="gym")
        self.steps = [{"calls": [("retire", {"reason": "The Gym's data cannot locate the signal: nothing to test."})]}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual([t["name"] for t in self.sail.bodies[-1]["tools"]], ["gym_run", "gym_sweep", "retire"])
        self.assertIn("held 3 cycles in a row. If your notes say", self.sail.bodies[-1]["input"][-1]["content"])
        self.assertTrue(out["retired"], "the retire it asked for is honoured")

    def test_offered_after_three_holds_with_ten_trials_or_an_eligible_run(self):
        self.settings["researcher"]["retire_hold_untested"] = False  # the offer as it was before F1
        self.researcher().cycle(self.fid)  # the starter: one ineligible run
        r = self.researcher()
        self.assertFalse(r.hold_offer(self.held(2, trials=40)), "two holds")
        self.assertFalse(r.hold_offer(self.held(3, trials=1)), "three holds, one trial, no eligible run")
        self.assertTrue(r.hold_offer(self.held(3, trials=10)))
        self.assertTrue(r.can_retire(self.store.family(self.fid)))
        self.assertEqual(r.retire_floor(self.store.family(self.fid)), 0, "the floor, not the start")
        self.store.update_family(self.fid, trials=1)
        train_row(self.store, self.fid, 1, trades=90, eligible=True)
        self.assertTrue(r.hold_offer(self.store.family(self.fid)), "an eligible run behind it")
        self.settings["researcher"]["retire_hold_cycles"] = 0
        self.assertFalse(r.hold_offer(self.store.family(self.fid)), "0 turns it off")
        self.settings["researcher"]["retire_hold_cycles"] = 3
        self.store.set_state(self.fid, validation_version=1, extension_hold={"version": 1, "checks": "6/8", "at": "x"})
        self.assertFalse(r.hold_offer(self.store.family(self.fid)), "a near-miss waits for its extension result")
        self.store.set_state(self.fid, extension_hold=None)
        self.assertTrue(r.hold_offer(self.store.family(self.fid)))
        self.store.update_family(self.fid, band="candidate")
        self.assertFalse(r.hold_offer(self.store.family(self.fid)), "the Gym band only")

    def test_the_revise_turn_offers_retire_and_the_lesson_is_self_refuted(self):
        self.researcher().cycle(self.fid)
        self.held(3, trials=12)
        reason = "Refuted: the signal never beat the drift in any year."
        self.steps = [{"calls": [("retire", {"reason": reason})]}, {"text": "done"}]
        out = self.researcher().cycle(self.fid)
        tools = [t["name"] for t in self.sail.bodies[-1]["tools"]]
        self.assertEqual(tools, ["gym_run", "gym_sweep", "retire"], "REVISE offers retire to a holding family")
        self.assertIn("held 3 cycles in a row. If your notes say its mechanism is refuted or exhausted",
                      self.sail.bodies[-1]["input"][-1]["content"])
        self.assertTrue(out["retired"])
        self.assertEqual(self.cancelled, [self.fid])
        fam = self.store.family(self.fid)
        self.assertEqual(fam["retire_reason"], f"{SELF_REFUTED}: {reason}")
        [row] = GraveyardDigest(self.store, self.settings).rows()
        self.assertEqual(row["tag"], "SELF-REFUTED")
        self.assertIn("never beat the drift", self.store.graveyard()[0]["lesson"])

    def test_without_the_offer_the_revise_turn_stays_a_revision(self):
        self.researcher().cycle(self.fid)
        self.settings["researcher"]["retire_min_trials"] = 0  # isolate the legacy hold-count offer
        self.held(1, trials=12)
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "Nothing new."})]}]
        self.researcher().cycle(self.fid)
        self.assertEqual([t["name"] for t in self.sail.bodies[-1]["tools"]], ["gym_run", "gym_sweep"])


class Migration(StoreCase):
    """scripts/graveyard_verdicts.py: re-head the rows already buried, from the same `train_record`."""

    def bury_idle(self, fid, *, state=None, trades=None):
        reason = f"{DORMANT}. {IDLE_CAUSE}"
        self.graves.bury(fid, reason=reason, train="None", val="never validated", notes=("Refuted; waiting for retire.",))
        if state:
            self.store._exec("UPDATE families SET state=? WHERE id=?", (dumps(state), fid))
        if trades is not None:
            train_row(self.store, fid, 1, trades=trades, eligible=False)

    def run_script(self, *args):
        return graveyard_verdicts.main(["--state", str(self.root), *args])

    def test_dry_run_apply_idempotence_and_rollback(self):
        self.bury_idle("drifty", state={"robust_failed": [2], "drift_failed": {"2": "t 0.1"}})
        self.bury_idle("thin", trades=9)
        self.bury_idle("never")
        self.graves.bury("refuted-one")
        self.store.put(SEAL_KEY, {"format": 3, "sha": "old"})
        dry = self.run_script()
        self.assertEqual((dry["mode"], dry["to_change"], dry["by_screen"]), ("dry run", 2, {"drift": 1, "thin": 1}))
        self.assertEqual(dry["read"]["screen: untested"], 1)
        self.assertEqual(dry["digest_before"]["tags"]["IDLE"], 3)
        self.assertEqual(dry["digest_after"]["tags"], {"DRIFT": 1, "THIN": 1, "IDLE": 1, "REFUTED": 1})
        self.assertEqual(self.store.get(SEAL_KEY), {"format": 3, "sha": "old"}, "a dry run writes nothing")
        applied = self.run_script("--apply")
        self.assertEqual(applied["applied"], {"lessons": 2, "reasons": 2, "changed_since_read": 0})
        self.assertEqual(applied["tags_after"], {"DRIFT": 1, "THIN": 1, "IDLE": 1, "REFUTED": 1})
        self.assertEqual(self.store.get(SEAL_KEY), {}, "the digest reseals once")
        backup = Path(applied["backup"])
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        lesson_now = next(g for g in self.store.graveyard(limit=10) if g["family"] == "drifty")["lesson"]
        self.assertIn(f"{DORMANT}. {idle_cause('drift')}. Tried", lesson_now, "only the head changed")
        self.assertIn("Refuted; waiting for retire.", lesson_now, "the researcher's verdict note stays")
        self.assertEqual(self.store.family("drifty")["retire_reason"], f"{DORMANT}. {idle_cause('drift')}")
        self.assertEqual(self.run_script("--apply")["to_change"], 0, "a second apply changes nothing")
        back = self.run_script("--rollback", str(backup), "--apply")
        self.assertEqual((back["lessons"], back["reasons"]), (2, 2))
        self.assertEqual(back["tags_after"]["IDLE"], 3)
        self.assertEqual(self.store.family("thin")["retire_reason"], f"{DORMANT}. {IDLE_CAUSE}")


class ExtensionHold(RoundCase):
    """R11-4's swarm rule: a validation that met six of the checks holds the family out of the dormancy clause until the
    operator clears it; never again for the same version."""

    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=8, floor=0)
        self.settings["researcher"]["dormant_cycles"] = 12

    def validated(self, fid="a"):
        self.family(fid)
        Tournament(self.store, self.pool, self.settings, clock=self.clock).validate(self.store.families(alive=True))
        return self.store.family(fid)

    def test_six_checks_set_the_hold_and_the_dormancy_clause_waits(self):
        fam = self.validated()
        hold = fam["state"]["extension_hold"]
        self.assertEqual((hold["version"], hold["checks"]), (1, "8/8"))
        self.assertTrue(extension_held(fam))
        self.store.set_state("a", dormant_cycles=40, gate_ready=False)
        self.assertIsNone(idle_dead(self.store.family("a"), self.settings), "exempt while held")
        report = extension_hold.main(["--state", str(self.root), "--clear", "a"])
        self.assertEqual(report["mode"], "dry run")
        self.assertTrue(extension_held(self.store.family("a")), "a dry run clears nothing")
        extension_hold.main(["--state", str(self.root), "--clear", "a", "--apply"])
        fam = self.store.family("a")
        self.assertFalse(extension_held(fam))
        self.assertEqual(fam["state"]["extension_cleared"]["version"], 1)
        self.assertIn("made no new Gym evaluation in its last 40 cycles", idle_dead(fam, self.settings))
        Tournament(self.store, self.pool, self.settings, clock=self.clock).judge("a", 1, strong(self.pool.jobs[0]),
                                                                                  record=False)
        self.assertFalse(extension_held(self.store.family("a")), "never held again for the same version")

    def test_below_six_checks_or_off_no_hold(self):
        self.answer = weak
        self.assertNotIn("extension_hold", self.validated("w")["state"])
        self.answer = strong
        self.settings["researcher"]["extension_hold_checks"] = 0
        self.assertNotIn("extension_hold", self.validated("s")["state"], "0 turns the rule off")

    def test_a_later_validation_of_another_version_ends_it_and_seed_finds_the_unheld(self):
        fam = self.validated()
        self.assertTrue(extension_held(fam))
        self.store.set_state("a", validation_version=2)
        self.assertFalse(extension_held(self.store.family("a")), "the hold is for the version its latest validation judged")
        self.store.set_state("a", validation_version=1, extension_hold=None, extension_versions=[])
        listed = extension_hold.main(["--state", str(self.root)])
        self.assertEqual([r["family"] for r in listed["never_held"]], ["a"])
        extension_hold.main(["--state", str(self.root), "--seed", "--apply"])
        self.assertTrue(extension_held(self.store.family("a")))
        self.assertEqual(json.loads(json.dumps(extension_hold.main(["--state", str(self.root)])["held"]))[0]["family"], "a")
