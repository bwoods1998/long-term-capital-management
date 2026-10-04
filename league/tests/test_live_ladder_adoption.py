"""THE FORWARD LADDER ACROSS AN EVALUATOR ADOPTION (Oct 3, 2026): what a release that changes league/live alone carries
over, and what it never does.

L0, THE VALIDATION LINE (`bands.validation_passed`; read by the ladder's bridge at a checkpoint and by THE LADDER'S
BELT before a promotion), is Gym evidence ON THE GYM IN FORCE: the same image and bundle. A league/live-only adoption
keeps the family's validation line (`evaluator.adopt`), and the one-time restoration gives back a line the release
before that rule cleared: either satisfies L0. An adoption that changes the Gym clears the line, and L0 waits for a
validation on the new Gym.

That is all a kept validation does. A promotion still needs the ladder's own evidence under the NEW fingerprint: a
practice cohort frozen under the new practice evaluator, its own record, its own receipt, and the pre-filter's answer.
And with execution tuition retired on this tree, no Gym-band row comes of a kept or restored validation at all.

THE FAST LANE ACROSS AN ADOPTION (release F1, Oct 3, 2026: the gate's sealed look is the route to Probe). A SPENT LOOK
STAYS SPENT across a league/live-only adoption, and across the release before the rule followed by the restoration: a
failed look (its row, the gate's mark, the lineage's ration, nothing taken up again); a passed look whose band returned
to the Gym (no row, no second look: a look-earned band does not survive a league/live release until a later release
gives it back on the same look). A version reviewed but not yet looked at owes its review again and then gets its ONE
look.

The swarm's side is the real store, tournament, gate and adoption (`LiveOnlyCase`); the House's side is its practice
record and the ladder's session end through the real bridge. The fast lane's classes run the tree's OWN switches
(`SHIPPED`: the sealed look on, tuition off). The ladder's classes run THE LADDER'S OWN MODE (`LADDERS_OWN`: sealed
looks off, evidence v3's own gate, where the pre-filter reads and the belt can let a promotion through)."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from league.live import ladder as L
from league.live import observe as O
from league.live.families import SwarmFamilies
from league.live.observe import ObserveStore
from league.swarm import bands, evidence, gate
from league.swarm.evaluator import ARCHIVE_KEY, KEY, adopt
from league.swarm.gate import run_sha
from league.tests.evaluator_fakes import adopt_as_v3a, reviewed, seed_current_run
from league.tests.swarm_fakes import result
from league.tests.test_live_ladder import HAVE, pattern, record, rules, sessions
from league.tests.test_swarm_evaluator import LiveOnlyCase, adoptions
from league.tests.test_swarm_rounds import strong, weak

#: The two route switches as this tree ships them, read at import (before any test's patch); and the ladder's own mode.
SHIPPED = {"league.swarm.gate.SEALED_LOOKS": gate.SEALED_LOOKS, "league.swarm.bands.TUITION_ROWS": bands.TUITION_ROWS}
LADDERS_OWN = {"league.swarm.gate.SEALED_LOOKS": False, "league.swarm.bands.TUITION_ROWS": False}
NOT_MET = "its version has not met the Validation line on the Gym in force"
PASS = {"text": json.dumps({"verdict": "pass", "reasons": []})}


def practice_evaluator(identity: dict) -> str:
    """The House's practice evaluator under a release: "<Gym bundle>:<fill model version>:<execution fingerprint>"
    (`league/live/step.py`)."""
    return f"{identity['bundle']}:fills-1:{identity['execution']}"


@unittest.skipUnless(HAVE, "numpy not installed")
class AdoptionCase(LiveOnlyCase):
    """A swarm on a named Gym under release A's league/live, and the House's practice record and ladder on the same
    state directory. `release(identity)` is a release's first start: the swarm adopts its identity, the House's
    practice evaluator names it, and the code's own execution fingerprint is its. `SWITCHES`: the two route switches
    the class runs under (the tree's own unless a class says the ladder's own mode)."""

    SWITCHES = SHIPPED

    def setUp(self):
        super().setUp()
        for name, value in self.SWITCHES.items():
            switch = patch(name, value)
            switch.start()
            self.addCleanup(switch.stop)
        self.now = [1_790_000_000.0]
        self.observe = ObserveStore(self.root, clock=lambda: self.now[0])
        self.addCleanup(self.observe.close)
        self.families = SwarmFamilies(self.root)          # the House's own connection to the swarm's store
        self.addCleanup(lambda: self.families._store.close() if self.families._store is not None else None)
        self.events, self.alerts = [], []
        self.live = SimpleNamespace(observe_store=self.observe, families=self.families, clock=lambda: self.now[0],
                                    record=lambda kind, payload, agent=None: self.events.append((kind, payload)),
                                    alert=lambda level, text: self.alerts.append(text))
        self.ladder = L.Ladder(self.live)
        self.bridge = self.ladder.bridge
        self.assertIsInstance(self.bridge, L.SwarmBridge)
        self.days = sessions("2026-10-05", 140)
        self.fingerprint = None
        self.release(self.release_a)

    def running(self, identity: dict) -> None:
        """The code that runs is `identity`'s league/live: its execution fingerprint is the code's own."""
        if self.fingerprint is not None:
            self.fingerprint.stop()
        self.fingerprint = patch("league.swarm.evaluator.execution_fingerprint", return_value=identity["execution"])
        self.fingerprint.start()
        self.addCleanup(self.fingerprint.stop)

    def release(self, identity: dict) -> dict:
        """A release's first start (the class docstring): what the swarm's adoption returned."""
        self.running(identity)
        out = adopt(self.store, identity)
        self.observe.evaluator = practice_evaluator(identity)
        return out

    def sha(self, fid: str, n: int = 1) -> str:
        return run_sha(self.store.version(fid, n))

    def l0(self, fid: str, n: int = 1) -> tuple:
        """L0 as its readers give it: (the Validation line's verdict, the same from the ladder's bridge, what THE
        LADDER'S BELT refuses the program for)."""
        read = bands.validation_passed(self.store.family(fid)["state"], n, self.store.get(KEY))
        return read, self.bridge.validation(fid, n), bands.ladder_refusal(self.root, family=fid, version=n,
                                                                          run_sha=self.sha(fid, n))

    # ------------------------------------------------------------------ the House's side
    def pins(self, day: str) -> list[str]:
        """The first pins of `day`'s session: every program the practice league offers that holds no slot is frozen.
        The families frozen."""
        frozen = []
        for row in self.observe.cohort_candidates(bands.observe(self.root), day=day, in_session=True):
            if not row.get("practice_frozen"):
                self.observe.freeze(row, day=day)
                frozen.append(row["family"])
        return frozen

    def practised(self, fid: str, days: list[str], returns: list[list[float]], *, account: str) -> None:
        """The cohort's record so far: its program closes on `account` under the running practice evaluator, and its
        practice row from its first day."""
        db = self.observe._connect()
        for r in record(days, returns):
            db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, "
                       "body, exit_day, reason, forced, evaluator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (f"{fid}@1:o", account, fid, 1, f"{account}-{r['trade_id']}", r["exit_day"], r["pnl"], r["max_loss"],
                        1.0, json.dumps(r["body"]), r["exit_day"], "program", 0, self.observe.evaluator))
        db.execute("INSERT OR REPLACE INTO practice(family, version, tier, capital, first_at, first_day, last_at, last_day, "
                   "sessions, account) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (fid, 1, "validated", 10000.0, 1.0, days[0], 2.0, days[-1], len(days), account))

    def night(self, day: str, *, binding: bool = True) -> dict:
        """The session's end of `day`: every cohort has practised each session from its first day through it."""
        db = self.observe._connect()
        for fid, first in db.execute("SELECT family, first_day FROM practice").fetchall():
            if first <= day:
                db.execute("UPDATE practice SET sessions=?, last_day=? WHERE family=?",
                           (len(L.sessions_between(first, day)), day, fid))
        with patch.object(L.Rules, "from_constitution", return_value=rules(binding=binding)):
            return self.ladder.end_of_day(day)

    def gate_reads(self, fid: str) -> dict:
        """The gate's free read of the holdout the House asked for, judged on the gate's own line and written by the
        gate's own writer: the line's figures (a pass)."""
        sha = self.sha(fid)
        ask = (self.store.get(L.PREFILTER_REQUESTS) or {})[sha]
        line = evidence.prefilter_line(result(fid, window="holdout", pnl=120.0), level=gate.prefilter_level(),
                                       seed=gate.PREFILTER_SEED + sha)
        gate.Gate._prefilter_write(SimpleNamespace(store=self.store, clock=lambda: 1.0), sha, ask, {}, status="done",
                                   line=line, ran_bundle=ask["bundle"], ran_image=self.IMAGE)
        self.assertTrue(line["passed"])
        return line

    def receipts(self, fid: str) -> list[dict]:
        keys = ("id", "day", "verdict", "checkpoint", "stats")
        rows = self.observe._connect().execute(
            f"SELECT {', '.join(keys)} FROM ladder_decisions WHERE family=? ORDER BY id", (fid,)).fetchall()
        return [{**dict(zip(keys, r)), "stats": json.loads(r[-1])} for r in rows]

    def cohort(self, fid: str) -> tuple:
        return self.observe._connect().execute("SELECT status, reason, first_day, evaluator, entrant FROM cohorts WHERE "
                                               "family=?", (fid,)).fetchone()

    def band(self, fid: str) -> str:
        return self.store.family(fid)["band"]


class L0IsGymEvidenceOnTheGymInForce(AdoptionCase):
    SWITCHES = LADDERS_OWN   # L0 as the ladder's belt reads it where the ladder can promote

    # (a) a kept line and a restored line each give L0 True
    def test_a_line_a_league_live_only_adoption_kept_or_gave_back_meets_l0(self):
        """Four families the tournament validated under release A (the line met). Two hold the tournament's record of
        that verdict; two hold their line alone (a validation from before each verdict's record was kept). The release
        before the rule (`adopt_as_v3a`) clears every line; the next league/live-only adoption gives each back
        (RESTORED), and the one after keeps it (KEPT). L0 is met wherever the line, or the record, says the version
        met the line on the Gym in force."""
        for fid in ("v", "w", "line-only", "line-alone"):
            self.validated(fid)
        for fid in ("line-only", "line-alone"):
            self.store.set_state(fid, validation_verdicts=None)
        every = ("v", "w", "line-only", "line-alone")
        for fid in every:
            self.assertEqual(self.l0(fid), (True, True, None), fid)

        # The release before the rule: a league/live-only adoption that archived and cleared every line.
        self.clock.advance(3600)
        self.running(self.release_b)
        adopt_as_v3a(self.store, self.release_b)
        for fid in every:
            state = self.store.family(fid)["state"]
            self.assertEqual((state["validation_line"], state[ARCHIVE_KEY]["validation_line"]["passed"]), (None, True))
        for fid in ("v", "w"):
            self.assertEqual(self.l0(fid), (True, True, None),
                             "the tournament's record of the verdict was judged on the Gym in force: it stands")
        for fid in ("line-only", "line-alone"):
            self.assertEqual(self.l0(fid), (None, None, NOT_MET), "the line was all it held, and that release cleared it")

        # RESTORED: the next league/live-only adoption gives the line back, and it meets L0 as it did.
        self.clock.advance(3600)
        out = self.release(self.release_c)
        self.assertEqual((out["gym_changed"], sorted(out["restored"])), (False, sorted(every)))
        for fid in every:
            state = self.store.family(fid)["state"]
            self.assertEqual((state["validation_version"], state["validation_line"]["passed"], state["validation_image"],
                              state["validation_bundle"]), (1, True, self.IMAGE, self.bundle), fid)
            self.assertIn("validation_line", adoptions(self.store, fid)[-1]["restored"]["keys"])
            self.assertEqual(self.l0(fid), (True, True, None), f"{fid}: a restored line meets L0")

        # KEPT: a league/live-only adoption under the rule keeps the line, and it meets L0 as it did.
        fresh = self.validated("fresh")                       # validated under release C itself
        self.assertEqual(self.store.family("fresh")["state"]["validation_verdicts"]["1"]["evaluator"], self.release_c)
        self.validated("fresh-line-only")
        self.store.set_state("fresh-line-only", validation_verdicts=None)
        out = self.release(self.release_d)
        self.assertEqual((out["gym_changed"], out["restored"]), (False, {}))
        for fid in (*every, "fresh", "fresh-line-only"):
            self.assertIsNone(adoptions(self.store, fid)[-1]["restored"])
            self.assertIn("validation_line", adoptions(self.store, fid)[-1]["kept"])
            self.assertEqual(self.l0(fid), (True, True, None), f"{fid}: a kept line meets L0")
        self.assertEqual(self.sha("fresh"), fresh)

    def test_l0_reads_a_verdict_judged_on_the_gym_in_force_and_no_other(self):
        """`bands.validation_passed`, reading by reading. A verdict judged under an identity that differs from the
        store's by the execution fingerprint alone is the version's verdict, a failure as much as a pass; one judged
        on another image or bundle is none. The family's own line counts when it names the image and bundle in force."""
        now = {"image": "image", "bundle": "bundle", "execution": "this release's league/live"}
        before = {**now, "execution": "an earlier release's league/live"}
        elsewhere = ({**now, "image": "another image"}, {**now, "bundle": "another bundle"}, None, "an identity as text")

        def read(current=now, **state):
            return bands.validation_passed(state, 1, current)

        def verdict(passed, evaluator):
            return {"1": {"passed": passed, "at": "2026-10-01T00:00:00Z", "evaluator": evaluator}}

        line = {"validation_version": 1, "validation_image": "image", "validation_bundle": "bundle"}
        for passed in (True, False):
            with self.subTest(passed=passed):
                for judged in (now, before):
                    self.assertIs(read(validation_verdicts=verdict(passed, judged)), passed, "the record, on the Gym in force")
                for judged in elsewhere:
                    self.assertIsNone(read(validation_verdicts=verdict(passed, judged)), "the record, on another Gym")
                self.assertIs(read(**line, validation_line={"passed": passed}), passed, "the line, on the Gym in force")
                for change in ({"validation_image": "another image"}, {"validation_bundle": "another bundle"},
                               {"validation_image": None}, {"validation_bundle": None}, {"validation_version": 2}):
                    self.assertIsNone(read(**{**line, **change}, validation_line={"passed": passed}), change)
                # The record is the version's LATEST verdict: it is read before a line that an adoption gave back.
                self.assertIs(read(**line, validation_line={"passed": not passed},
                                   validation_verdicts=verdict(passed, before)), passed)
                # A record judged on another Gym says nothing; the line, on the Gym in force, does.
                self.assertIs(read(**line, validation_line={"passed": passed},
                                   validation_verdicts=verdict(not passed, elsewhere[0])), passed)
        # A store that never adopted an identity (the identity-less test pools) has no Gym to compare with.
        self.assertIs(read(None, validation_version=1, validation_line={"passed": True}), True)
        self.assertIs(read(None, validation_verdicts=verdict(False, None)), False)
        self.assertIsNone(read(None, validation_verdicts=verdict(True, now)), "judged under an identity the store never held")
        # An identity that cannot be read answers for no line (fail-closed), and only for a record judged under itself.
        for unread in ("an identity as text", {"image": "image"}, {"bundle": "bundle"}, {}, 7):
            self.assertIsNone(read(unread, **line, validation_line={"passed": True}), unread)
        self.assertIs(read("E2", validation_verdicts=verdict(True, "E2")), True)
        self.assertIsNone(read("E2", validation_verdicts=verdict(True, "E1")))
        for state in (None, "text", 7):
            self.assertIsNone(bands.validation_passed(state, 1, now))

    # (d) a Gym-changing adoption still clears the line, and L0 waits
    def test_an_adoption_that_changes_the_gym_clears_the_line_and_l0_waits_for_a_validation_on_the_new_gym(self):
        """A new Gym image leaves the bundle and the execution fingerprint as they were, so the House's practice
        evaluator does not change and the cohort practises on. Its version's validation was judged on the old image:
        the adoption clears the line, the tournament's record of it names another Gym, and a checkpoint that meets
        every forward line is latched WAITING for a Validation verdict. Only a validation on the new Gym meets L0."""
        self.validated("v")
        self.assertEqual(self.pins(self.days[0]), ["v"])
        self.practised("v", self.days[:60], pattern(60), account="a")
        self.assertEqual(self.l0("v"), (True, True, None))

        new = "a new Gym image"
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": new}}))
        self.pool.image = lambda kind="gym": new
        self.answer = lambda job: {**strong(job), "gym_image": new, "gym_bundle": self.bundle}
        evaluator = self.observe.evaluator
        out = self.release({**self.release_a, "image": new})
        self.assertEqual((out["gym_changed"], self.observe.evaluator), (True, evaluator), "the Gym changed; practice did not")
        state = self.store.family("v")["state"]
        self.assertEqual((state["validation_line"], state["validation_version"]), (None, None), "the line is cleared")
        self.assertEqual(state["validation_verdicts"]["1"]["evaluator"]["image"], self.IMAGE, "its record names the old Gym")
        self.assertEqual(self.l0("v"), (None, None, NOT_MET))

        self.assertEqual(self.night(self.days[39])["verdicts"], {"await_validation": 1})
        [receipt] = self.receipts("v")
        latch = self.observe.ladder_state("v", 1)["latch"]
        self.assertEqual((receipt["checkpoint"], latch["waits"], self.store.get(L.PREFILTER_REQUESTS)), (40, "validation", None),
                         "it met every forward line, and it waits: nothing is asked of the gate on it")
        self.assertEqual(self.band("v"), "gym")

        # The Gym's own verdict on the new image: research runs the version on Train again (no validation is bought
        # with another Gym's Train evidence), and the tournament validates it.
        self.store.update_family("v", best_version=1)
        self.assertEqual(self.tournament.validate([self.store.family("v")])["waiting_robustness"], ["v"])
        self.assertEqual(self.l0("v"), (None, None, NOT_MET), "still waiting")
        train = seed_current_run(self.store, "v", 1, window="train")
        self.store.update_family("v", best_train=1.2)
        self.store.set_state("v", best_train_run=train["run_id"], best_train_version=1)
        self.assertTrue(self.tournament.validate([self.store.family("v")])["judged"]["v"]["passed"])
        self.assertEqual(self.store.family("v")["state"]["validation_image"], new)
        self.assertEqual(self.l0("v"), (True, True, None))
        self.assertEqual(self.night(self.days[40])["waiting"], 1)
        self.assertEqual((self.observe.ladder_state("v", 1)["latch"]["waits"], set(self.store.get(L.PREFILTER_REQUESTS))),
                         ("prefilter", {self.sha("v")}), "L0 met on the new Gym: the pre-filter is asked for")

    def test_a_gym_that_comes_back_finds_the_verdicts_that_were_judged_on_it(self):
        """THE ONE CORNER of "an adoption that changes the Gym clears the line and L0 waits", pinned as the code reads it
        (`bands.validation_passed`; the reading is open to a stricter ruling). The Gym goes from image A to another and
        back to A, under a later league/live: two adoptions that change the Gym. Each clears every family's line, and
        no validation is made in between. On the other image L0 waits for every version. Back on A, a version whose
        verdict the tournament recorded on A is read by that record, a failure as much as a pass: "a validation on the
        Gym in force" is one made on its image and bundle, whenever it was made. A family that held its line alone has
        nothing left to read, and waits. Should L0 have to wait after every adoption that changes the Gym, the record
        must count only when it is newer than the family's newest such adoption, and this test fails by design."""
        self.validated("passed")
        self.validated("line-only")
        self.store.set_state("line-only", validation_verdicts=None)
        self.with_train_best("failed")
        self.answer = lambda job: {**weak(job), "gym_image": self.IMAGE, "gym_bundle": self.bundle}
        self.assertIs(self.tournament.validate([self.store.family("failed")])["judged"]["failed"]["passed"], False)
        every = ("passed", "line-only", "failed")
        self.assertEqual([self.l0(fid)[:2] for fid in every], [(True, True), (True, True), (False, False)])
        records = {fid: self.store.family(fid)["state"].get("validation_verdicts") for fid in every}
        self.assertEqual({fid: (r or {}).get("1", {}).get("evaluator") for fid, r in records.items()},
                         {"passed": self.release_a, "line-only": None, "failed": self.release_a})

        other = "another Gym image"
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": other}}))
        out = self.release({**self.release_a, "image": other})
        self.assertEqual(out["gym_changed"], True)
        for fid in every:
            state = self.store.family(fid)["state"]
            self.assertEqual((state["validation_line"], state["validation_version"]), (None, None), "its line is cleared")
            self.assertEqual(self.l0(fid), (None, None, NOT_MET), f"{fid}: on the other Gym L0 waits")

        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": self.IMAGE}}))
        back = {**self.release_a, "execution": "a later release's league/live"}
        out = self.release(back)
        self.assertEqual((out["gym_changed"], out["restored"]), (True, {}), "a Gym change again, and nothing is given back")
        for fid in every:
            state = self.store.family(fid)["state"]
            self.assertEqual((state["validation_line"], state["validation_version"], state.get("validation_verdicts")),
                             (None, None, records[fid]), "no line, and no validation made since: the record is as it was")
        self.assertEqual(self.l0("passed"), (True, True, None), "judged on the image and bundle in force: it stands")
        self.assertEqual(self.l0("failed")[:2], (False, False), "and so does a failure")
        self.assertEqual(self.l0("line-only"), (None, None, NOT_MET), "its line was all it held: it waits")
        # It is L0 alone: no order and no practice row follow from the record (the selection was cleared with the line).
        self.assertEqual((bands.read(self.root), bands.observe(self.root)), ([], []))


class AKeptValidationAlonePromotesNothing(AdoptionCase):
    SWITCHES = LADDERS_OWN   # the ladder binds in this test's table, and its own gate makes the pre-filter's read

    # (b) a promotion still needs a cohort and its receipt under the new fingerprint, and the pre-filter
    def test_a_promotion_needs_a_cohort_and_its_receipt_under_the_new_fingerprint_and_the_prefilter(self):
        """The ladder BINDS in this test's table. Two validated families practise under release A. `latched` meets
        every line at its first checkpoint and the gate's read of its holdout passes; `open` is twenty sessions into its
        window with a winning record. Then a release changes league/live alone.

        Both validations are kept, and L0 is met for both. Neither is promoted on it: the record `latched` was judged
        on is another practice evaluator's, its latch is final and it never practises again under this version; `open`
        starts again as a NEW cohort and a NEW entrant with an empty record. Only that cohort's own checkpoint, under
        the new fingerprint, then the pre-filter's answer, promote it: by a receipt of its own, with a proof that pins
        the new fingerprint."""
        days = self.days
        for fid in ("latched", "open"):
            self.validated(fid)
        self.assertEqual(self.pins(days[0]), ["latched", "open"])
        self.observe._connect().execute("UPDATE cohorts SET first_day=? WHERE family='open'", (days[20],))
        self.practised("latched", days[:60], pattern(60), account="a")
        self.practised("open", days[20:40], pattern(20), account="a")
        one = practice_evaluator(self.release_a)
        self.assertEqual(self.night(days[39])["verdicts"], {"await_prefilter": 1})
        self.gate_reads("latched")

        # THE RELEASE: league/live alone. The swarm keeps both validations; the House's practice evaluator is new.
        out = self.release(self.release_b)
        two = practice_evaluator(self.release_b)
        self.assertEqual((out["gym_changed"], out["restored"], two != one), (False, {}, True))
        for fid in ("latched", "open"):
            self.assertEqual(self.l0(fid), (True, True, None), f"{fid}: its kept validation meets L0")

        # 1. The answer session under the new evaluator: the latch, its passed pre-filter and the kept validation are
        #    all there, and nothing is promoted: no cohort under the new practice evaluator exists.
        out = self.night(days[40])
        self.assertEqual((out["binding"], out["judged"], out["verdicts"], out["waiting"]), (True, 0, {}, 0))
        self.assertEqual(([r["verdict"] for r in self.receipts("latched")], self.receipts("open")), (["await_prefilter"], []))
        self.assertEqual((self.band("latched"), self.band("open"), bands.read(self.root)), ("gym", "gym", []))

        # 2. The next session's pins: the latched cohort's verdict was final, so it ends for good; the interrupted one
        #    is frozen again, a new cohort and a new entrant, with none of the old cohort's closes.
        self.assertEqual(self.pins(days[41]), ["open"])
        self.assertEqual(self.cohort("latched")[:2], ("complete", O.EVALUATOR_CHANGED_FINAL))
        with self.assertRaises(ValueError):
            self.observe.freeze(bands.observe(self.root, family="latched")[0], day=days[41])
        status, reason, first, evaluator, entrant = self.cohort("open")
        self.assertEqual((status, reason, first, evaluator), ("active", None, days[41], two))
        mine = [e for e in self.observe.entrants(since="2026-01-01") if e["family"] == "open"]
        self.assertEqual([(e["evaluator"], e["entered_day"], e["p_value"], e["p_checkpoint"]) for e in mine],
                         [(one, days[0], None, None), (two, days[41], None, None)], "two trials; neither judged yet")
        self.assertEqual(entrant, mine[-1]["id"])
        self.assertEqual(self.observe.ladder_rows("open", 1, evaluator=two, first_day=days[41], through=days[139]),
                         (None, []), "an empty record: its own closes alone, and it has none")

        # 3. It practises under the new fingerprint. Before its checkpoint nothing is judged, whatever its validation.
        self.practised("open", days[41:101], pattern(60), account="b")
        out = self.night(days[50])
        self.assertEqual((out["practising"], out["judged"], out["verdicts"], self.band("open")), (1, 0, {}, "gym"))

        # 4. Its own first checkpoint, at its fortieth session under the new evaluator: every forward line met on its
        #    own closes, L0 met by the kept validation (it does not wait for one), and the gate is asked.
        self.assertEqual(self.night(days[80])["verdicts"], {"await_prefilter": 1})
        [latch] = self.receipts("open")
        self.assertEqual((latch["checkpoint"], latch["day"], latch["stats"]["closes"], latch["stats"]["sessions"]),
                         (40, days[80], 80, 40), "forty sessions of its own account's closes: none of the old cohort's")
        self.assertEqual(self.store.get(L.PREFILTER_REQUESTS)[self.sha("open")]["day"], days[80])
        self.assertEqual((self.band("open"), bands.read(self.root)), ("gym", []), "met L0 and every line: not promoted yet")

        # 5. Without the pre-filter's answer it waits; with it, it is promoted, by this cohort's own receipt.
        out = self.night(days[81])
        self.assertEqual((out["waiting"], out["verdicts"], self.band("open")), (1, {}, "gym"))
        self.gate_reads("open")
        self.assertEqual(self.night(days[82])["verdicts"], {"promoted": 1})
        receipt = self.receipts("open")[-1]
        self.assertEqual((receipt["verdict"], receipt["day"], receipt["stats"]["latch"]["receipt"]),
                         ("promote", days[82], latch["id"]))
        proof = self.store.family("open")["state"]["banded_evaluator"]
        self.assertEqual((self.band("open"), proof["route"], proof["receipt"], proof["execution_sha256"],
                          proof["practice_evaluator"]),
                         ("probe", "ladder", receipt["id"], self.release_b["execution"], two),
                         "its proof pins the NEW fingerprint and names the new cohort's practice evaluator and receipt")
        self.assertTrue(bands.ladder_receipt(self.root, family="open", version=1, run_sha=self.sha("open"),
                                             receipt=receipt["id"]))
        [row] = bands.read(self.root)
        self.assertEqual((row["family"], row["band"], row["run_sha"]), ("open", "probe", self.sha("open")))
        self.assertEqual(self.cohort("open")[0], "promoted")
        self.assertEqual((self.band("latched"), [r["verdict"] for r in self.receipts("latched")]), ("gym", ["await_prefilter"]),
                         "the cohort judged under the earlier fingerprint was never promoted")

        # And that proof is the new fingerprint's alone: the next league/live change ends it, validation kept or not.
        out = self.release(self.release_c)
        self.assertEqual((out["returned"], self.band("open"), bands.read(self.root)), (["open"], "gym", []))
        self.assertEqual(self.l0("open")[:2], (True, True))


class NoTuitionRowComesOfIt(AdoptionCase):
    # (c) with tuition retired on this tree, neither a live-only adoption nor a restoration yields a Gym-band row
    def gym_rows(self, **kw) -> list[tuple]:
        return [(r["family"], r["version"]) for r in bands.read(self.root, **kw) if r["band"] == "gym"]

    def test_the_switches_as_shipped(self):
        self.assertEqual(SHIPPED, {"league.swarm.gate.SEALED_LOOKS": True, "league.swarm.bands.TUITION_ROWS": False})
        self.assertEqual((gate.SEALED_LOOKS, bands.TUITION_ROWS), (True, False), "this class reads the tree's own switches")

    def test_neither_a_league_live_only_adoption_nor_a_restoration_yields_a_gym_band_row(self):
        """Execution tuition stays retired on this tree (`bands.TUITION_ROWS` off). Two validated families whose review
        and audit passed: on the retired route each had a tuition row (`read(tuition=True)`, that route's own read).
        `bands.read()` gives the live path no Gym-band row for either, before a league/live-only adoption, after one
        that keeps their validation, after the release before the rule cleared it, and after the restoration gave it
        back: a kept or restored validation opens no real-order route. The one route is the look: the gate reads each
        restored program again (a passing review is never given back), and only a passed look gives a row, a
        Candidate's."""
        self.assertIs(bands.TUITION_ROWS, False, "this test reads the tree's own switch")
        shas = {fid: self.validated(fid) for fid in ("v", "w")}
        for fid, sha in shas.items():
            self.assertEqual(self.store.family(fid)["state"]["review"], reviewed(sha))
        self.assertEqual(self.gym_rows(tuition=True), [("v", 1), ("w", 1)], "the retired route's own read: a row each")
        self.assertEqual((self.gym_rows(), bands.read(self.root)), ([], []), "the live path's read: none")

        self.release(self.release_b)                                   # a league/live-only adoption: KEPT
        for fid in shas:  # the store's line, the ladder's bridge, and the belt (shipped: the look is the route)
            self.assertEqual(self.l0(fid), (True, True, bands.BELT_LOOK_ROUTE))
        self.assertEqual((self.gym_rows(), bands.read(self.root), self.gym_rows(tuition=True)), ([], [], []),
                         "none on the live path's read; and the retired route's own gives none either (the review went)")

        self.clock.advance(3600)
        self.running(self.release_c)
        adopt_as_v3a(self.store, self.release_c)                      # the release before the rule: cleared
        self.assertEqual((self.gym_rows(), bands.read(self.root), self.gym_rows(tuition=True)), ([], [], []))

        self.clock.advance(3600)
        out = self.release(self.release_d)                             # the next league/live-only adoption: RESTORED
        self.assertEqual(sorted(out["restored"]), ["v", "w"])
        for fid in shas:
            self.assertEqual(self.l0(fid), (True, True, bands.BELT_LOOK_ROUTE))
            self.assertIsNone(self.store.family(fid)["state"]["review"])
        self.assertEqual((self.gym_rows(), bands.read(self.root), self.gym_rows(tuition=True)), ([], [], []))
        self.assertEqual([(r["family"], r["tier"], r["observe"]) for r in self.practice()],
                         [("v", "validated", True), ("w", "validated", True)], "practice, shadow only, is all that follows")
        # THE FAST LANE: the restored families are at the gate with no review, so the gate reads each program again
        # before anything else. Readers that reach no verdict open no look, and no row follows from the reading.
        reads = len(self.sail.bodies) + len(self.asked)
        out = gate.Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.assertEqual((out["practice"], out["looked"], self.store.looks()), ([], [], []))
        self.assertEqual(len(self.sail.bodies) + len(self.asked) - reads, 2, "each family's program is read again")
        self.assertEqual((self.gym_rows(), bands.read(self.root), self.gym_rows(tuition=True)), ([], [], []))
        # Both readers pass: one look each, and a pass is a Candidate (a band row, never a Gym-band row).
        self.replies = [PASS] * 4
        self.clock.advance(600)
        out = gate.Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.assertEqual(sorted((x["family"], x["passed"]) for x in out["looked"]), [("v", True), ("w", True)])
        self.assertEqual((len(self.store.looks()), self.gym_rows()), (2, []))
        self.assertEqual(sorted((r["family"], r["band"], r["holdout_passed"], r["run_sha"]) for r in bands.read(self.root)),
                         [("v", "candidate", True, shas["v"]), ("w", "candidate", True, shas["w"])])


class ASpentLookStaysSpent(AdoptionCase):
    """THE FAST LANE ACROSS AN ADOPTION, under the tree's own switches (the module docstring)."""

    def gate(self) -> dict:
        self.clock.advance(600)
        return gate.Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()

    def reads(self) -> int:
        return len(self.sail.bodies) + len(self.asked)

    def holdout_jobs(self) -> int:
        return len([j for j in self.pool.jobs if j.window == "holdout"])

    def looked(self, fid: str, *, holdout) -> str:
        """A validated family taken through the gate's review, audit and its one look, whose holdout answers `holdout`:
        its run sha."""
        self.with_train_best(fid)
        self.assertTrue(self.tournament.validate([self.store.family(fid)])["judged"][fid]["passed"])
        base = self.answer
        self.answer = lambda job: ({**holdout(job), "gym_image": self.IMAGE, "gym_bundle": self.bundle}
                                   if job.window == "holdout" else base(job))
        self.replies = [PASS, PASS]
        out = self.gate()
        self.answer = base
        self.assertEqual([x["family"] for x in out["looked"]], [fid])
        return self.sha(fid)

    def nothing_is_taken_up_again(self, fid: str, sha: str, *, looks: int) -> None:
        """Rounds after an adoption: the tournament readies nothing of it, the gate reads nothing and looks at nothing,
        and its look, the gate's mark and the lineage's ration stand."""
        reads, jobs = self.reads(), self.holdout_jobs()
        for _ in range(2):
            self.tournament.validate(self.store.families(alive=True))
            self.replies = [PASS] * 4   # a reading would pass, and so would a look: neither is made
            out = self.gate()
            self.assertEqual((out["looked"], out["refused"], out["look_held"]), ([], [], []))
        state = self.store.family(fid)["state"]
        self.assertEqual((self.reads() - reads, self.holdout_jobs() - jobs), (0, 0), "no review, no audit, no sealed read")
        self.assertEqual((len(self.store.looks()), self.store.looked(sha), self.store.lineage_looks(fid, include_inflight=True)),
                         (looks, True, 1), "its one look: spent, and counted once in its lineage's ration")
        self.assertEqual((state["gated_sha"], state["gate_ready"], state.get("review")), (sha, False, None))
        self.assertEqual((self.band(fid), bands.read(self.root)), ("gym", []))

    def test_a_failed_look_stays_spent_across_a_league_live_only_adoption(self):
        sha = self.looked("f", holdout=weak)
        before = self.store.looks()
        self.assertEqual((before[0]["passed"], self.store.family("f")["state"]["gate_outcome"]["result"]), (0, "failed"))
        out = self.release(self.release_b)
        self.assertEqual((out["gym_changed"], out["returned"], self.store.looks()), (False, [], before))
        state = self.store.family("f")["state"]
        self.assertEqual((state["gate_outcome"]["result"], sha in state["incubator_barred"]), ("failed", True))
        self.nothing_is_taken_up_again("f", sha, looks=1)
        self.assertEqual(self.store.looks(), before, "Holm's count is the looks made: the same rows, the same p-values")

    def test_a_passed_looks_band_returns_and_its_program_gets_no_second_look(self):
        """A look-earned band does not survive a league/live release (its proof pins the execution fingerprint), and its
        program gets no second look: the named next step (the band given back on the same look after a fresh review)
        must ship before the first such release that follows the first band."""
        sha = self.looked("p", holdout=strong)
        [row] = bands.read(self.root)
        self.assertEqual((self.band("p"), row["band"], row["holdout_passed"], row["run_sha"]), ("candidate", "candidate", True, sha))
        out = self.release(self.release_b)
        self.assertEqual((out["gym_changed"], out["returned"], self.band("p"), bands.read(self.root)), (False, ["p"], "gym", []))
        self.assertEqual(self.store.family("p")["state"]["gate_outcome"]["result"], "passed", "the gate's record of it stands")
        self.nothing_is_taken_up_again("p", sha, looks=1)
        self.assertEqual([(r["family"], r["tier"]) for r in self.practice()], [("p", "validated")],
                         "its program practises again, shadow only: no real order follows")

    def test_the_same_across_the_release_before_the_rule_and_the_restoration(self):
        failed = self.looked("f", holdout=weak)
        passed = self.looked("p", holdout=strong)
        self.assertEqual((len(self.store.looks()), self.band("p")), (2, "candidate"))
        self.clock.advance(3600)
        self.running(self.release_b)
        adopt_as_v3a(self.store, self.release_b)             # the Oct 3 release: archive and clear
        self.assertEqual((self.band("p"), bands.read(self.root)), ("gym", []))
        self.clock.advance(3600)
        out = self.release(self.release_c)                   # the one-time restoration
        self.assertEqual(sorted(out["restored"]), ["f", "p"])
        for fid, sha in (("f", failed), ("p", passed)):
            self.nothing_is_taken_up_again(fid, sha, looks=2)

    def test_a_reviewed_version_not_yet_looked_at_is_asked_again_and_gets_its_one_look(self):
        """Reviewed and audited (a pass) and waiting for the gate image when league/live changes. Its passing review is
        the live route's fact: cleared. Its gate place is kept, so the gate takes it up, asks the review and the audit
        again, and only then makes its one look. (Sail's request key names the contract, the family, the stage and the
        version, none of which a league/live change moves: the answer Sail already gave is read again, no new call.)"""
        self.with_train_best("v")
        self.assertTrue(self.tournament.validate([self.store.family("v")])["judged"]["v"]["passed"])
        sha = self.sha("v")
        self.settings["gym"]["gate_checkpoint"] = None       # no look can be made yet
        self.replies = [PASS, PASS]
        self.assertEqual(self.gate()["waiting"], ["v"])
        review = self.store.family("v")["state"]["review"]
        self.assertEqual((review["sha"], review["verdict"], review["audit"]["verdict"], self.reads()), (sha, "pass", "pass", 2))

        out = self.release(self.release_b)
        state = self.store.family("v")["state"]
        self.assertEqual((out["gym_changed"], state["review"], state["gate_ready"], state.get("gated_sha")),
                         (False, None, True, None), "the review went; its place stands; the gate is not done with it")
        self.assertEqual((self.store.looks(), bands.read(self.root)), ([], []))

        asked = []
        real_review, real_audit = gate.Gate.review, gate.Gate.audit
        self.settings["gym"]["gate_checkpoint"] = "sbcp_gate"
        with patch.object(gate.Gate, "review", lambda g, fam, version, **kw: asked.append("review") or real_review(g, fam, version, **kw)), \
                patch.object(gate.Gate, "audit", lambda g, fam, version, **kw: asked.append("audit") or real_audit(g, fam, version, **kw)):
            out = self.gate()
        self.assertEqual((asked, out["looked"]), (["review", "audit"], [{"family": "v", "passed": True}]),
                         "asked again, both readers, and then its one look")
        self.assertEqual(self.reads(), 2, "Sail's stored answers serve the same question: no new model call")
        review = self.store.family("v")["state"]["review"]
        self.assertEqual((review["sha"], review["verdict"], review["audit"]["verdict"]), (sha, "pass", "pass"))
        [row] = bands.read(self.root)
        self.assertEqual((self.band("v"), row["band"], row["run_sha"], len(self.store.looks()), self.holdout_jobs()),
                         ("candidate", "candidate", sha, 1, 1))
        proof = self.store.family("v")["state"]["banded_evaluator"]
        self.assertEqual(proof["execution_sha256"], self.release_b["execution"], "its proof pins the NEW fingerprint")
        for _ in range(2):
            self.assertEqual(self.gate()["looked"], [])
        self.assertEqual((len(self.store.looks()), self.holdout_jobs()), (1, 1), "one look, for good")

    def test_a_paid_reader_reads_the_program_anew(self):
        """The same, on the plan's paid route (the OpenAI month has room): the review and the audit are bought again."""
        self.month.value = 100
        self.frontier_text = json.dumps({"verdict": "pass"})
        self.with_train_best("v")
        self.assertTrue(self.tournament.validate([self.store.family("v")])["judged"]["v"]["passed"])
        self.settings["gym"]["gate_checkpoint"] = None
        self.assertEqual(self.gate()["waiting"], ["v"])
        self.assertEqual([a["model"] for a in self.asked], ["gpt-6-sol", "gpt-6-astra"])
        self.release(self.release_b)
        self.settings["gym"]["gate_checkpoint"] = "sbcp_gate"
        self.assertEqual(self.gate()["looked"], [{"family": "v", "passed": True}])
        self.assertEqual(([a["model"] for a in self.asked], self.sail.bodies, len(self.store.looks())),
                         (["gpt-6-sol", "gpt-6-astra"] * 2, [], 1), "read anew by both paid readers, then one look")


if __name__ == "__main__":
    unittest.main()
