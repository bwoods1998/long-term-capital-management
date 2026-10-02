"""THE DUPLICATE LOOK (H3a, Oct 1, 2026; league/swarm/gate.py `duplicate_look`).

Every holdout look raises the Holm bar of every later one, and the three looks since the Sept 26 reset covered two
programs (the two Sept 27 looks had identical Train and Validation results). The gate now refuses a look that would repeat
an earlier one, in any family and lineage, before anything else is asked of the version: the same program (`run_sha`),
the same program under its merged PARAMS (the Gym's own run sha), or the same Validation evaluation with the same outcome.
No look row, no try, no review, no sealed read; recorded as the gate's other refusals are, and never with a figure.

The fake Gym here answers by BEHAVIOUR: a program's `# acts like:` line decides its figures, so two programs that differ
only in a comment validate identically, and its code with its PARAMS merged over the defaults is its own run sha, as the
real Gym's is. Every figure is invented."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import re
import unittest
from unittest.mock import patch

from league.swarm.gate import DUPLICATE_STAGE, Gate, duplicate_words, run_sha, validation_identity
from league.swarm.researcher import Researcher
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import result
from league.tests.test_swarm_d2a_sentinel import LITERALS, PATTERN
from league.tests.test_swarm_rounds import SPEC, RoundCase, weak

GYM = importlib.util.find_spec("league.gym") is not None and importlib.util.find_spec("numpy") is not None
DEFAULTS = {"k": 1}
PASS = {"text": json.dumps({"verdict": "pass", "reasons": []})}
#: Validation figures no other code produces (`test_swarm_d2a_sentinel`'s): the D2a test seeds them.
T, MEAN, SHARPE, PNL = 738.6417, 612.9483, 394.7261, 6174.29


def program(acts: str, note: str = "") -> str:
    """A program whose behaviour is `acts` (the fake Gym's figures follow it) and whose code also differs by `note`."""
    return (f"NEEDS = {{'roots': ['SPY']}}\nPARAMS = {{'k': 1}}\n# acts like: {acts}\n# {note}\n"
            "def decide(ctx):\n    if PARAMS['k']:\n        return []\n    return []\n")


class DuplicateCase(RoundCase):
    def setUp(self):
        super().setUp()
        self.engine_code = "engine-code-1"  # the Gym's own code hash, as its results name it
        self.holdout = weak  # a failed look leaves its family in the Gym, so its lineage can be looked at again
        self.sentinels = False
        self.answer = self.gym
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)

    def gym(self, job):
        """The fake Gym: Validation and Train figures follow the program's behaviour; the identity is the Gym's."""
        if job.window == "holdout":
            return self.holdout(job)
        acts = re.search(r"# acts like: (\S+)", job.code).group(1)
        rng = random.Random(f"{acts}|{job.window}|{job.stress}")
        daily = [round(rng.gauss(6.0, 10.0), 4) for _ in range(250)]
        figures = dict(t=T, pnl=PNL, mean=MEAN, sharpe_daily=SHARPE) if self.sentinels else \
            dict(t=4.0, pnl=round(sum(daily), 2), sharpe_daily=round(0.2 + rng.random() / 100, 6))
        out = result(f"{job.family}-v{job.version}", daily=daily, window=job.window, **figures)
        merged = {**DEFAULTS, **(job.params or {})}
        code_sha = hashlib.sha256(job.code.encode()).hexdigest()
        out.update(engine="gym-engine-4", code=self.engine_code, tables="tables-1", fill_model="fills-1", capital=10000.0,
                   stress=job.stress, program_sha=code_sha, params=merged,
                   run_sha=hashlib.sha256((code_sha + json.dumps(merged, sort_keys=True)).encode()).hexdigest())
        return out

    def add(self, fid, acts, *, note="", params=None, structure="iron_condor", code=None):
        """A version of family `fid` (born on `structure` if new) made its best."""
        if self.store.family(fid) is None:
            self.store.add_family({**SPEC, "id": fid, "structure": structure}, origin="seed")
        v = self.store.add_version(fid, code or program(acts, note), params or {}, author="seed")
        self.store.update_family(fid, best_version=v["n"])
        return v

    def validate(self):
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))

    def sha(self, fid, n):
        return run_sha(self.store.version(fid, n))

    def holdout_jobs(self, fid=None, n=None):
        return [j for j in self.pool.jobs if j.window == "holdout" and (fid is None or j.family == fid)
                and (n is None or j.version == n)]

    def duplicate_events(self):
        return [e for e in self.store.events_after(0)
                if e["kind"] == "swarm.gate" and e["payload"].get("action") == "duplicate_look"]

    def looked_first(self, fid="a", acts="calls", **kw):
        """`fid`'s version 1 validated, reviewed, audited and looked at (look #1, failed): the earlier look."""
        self.add(fid, acts, **kw)
        self.validate()
        self.replies = [PASS, PASS]
        out = self.gate.run()
        self.assertEqual(out["looked"], [{"family": fid, "passed": False}])
        self.assertEqual(len(self.store.looks()), 1)
        return self.store.looks()[0]

    def assert_refused(self, fid, n, *, of_look, match, bodies):
        """Refused as a duplicate of look `of_look`: one refusal row, the gate's words, no look, no try, no review."""
        sha = self.sha(fid, n)
        [row] = self.store.refusals(fid)
        self.assertEqual((row["stage"], row["version"]), (DUPLICATE_STAGE, n))
        self.assertIn(f"a duplicate of holdout look #{of_look}", row["reason"])
        state = self.store.family(fid)["state"]
        self.assertFalse(state["gate_ready"], "not gate-ready for this version: never retried every round")
        self.assertEqual(state["gated_sha"], sha)
        self.assertEqual(state["gate_outcome"]["result"], "refused")
        self.assertTrue(state["gate"].startswith(f"fail (the {DUPLICATE_STAGE}: a duplicate of holdout look #{of_look}"))
        self.assertEqual(self.holdout_jobs(fid, n), [], "no sealed read")
        self.assertIsNone(self.store.get(f"look_tries:{sha}"), "no try counted")
        self.assertEqual([x for x in self.store.looks() if (x["family"], x["version"]) == (fid, n)], [], "no look row")
        self.assertEqual(len(self.sail.bodies), bodies, "no review or audit was paid for it")
        [event] = [e for e in self.duplicate_events() if e["family"] == fid]
        self.assertEqual((event["payload"]["of_look"], event["payload"]["match"], event["payload"]["version"]),
                         (of_look, match, n))


class RunShaDuplicates(DuplicateCase):
    def test_the_same_program_in_another_lineage_is_refused_before_any_review_or_sealed_read(self):
        self.add("a", "calls")
        self.add("b", "calls", structure="debit_vertical")  # the same code and params: another lineage, the same program
        self.assertEqual(self.sha("a", 1), self.sha("b", 1))
        self.assertNotEqual(self.store.family("a")["lineage"], self.store.family("b")["lineage"])
        self.validate()
        self.assertTrue(self.store.family("b")["state"]["gate_ready"], "both reached the gate before a's look")
        self.replies = [PASS, PASS]
        with patch.object(Gate, "look", autospec=True, side_effect=Gate.look) as look:
            out = self.gate.run()
        self.assertEqual([c.args[1]["id"] for c in look.call_args_list], ["a"], "the gate never started a look at b")
        self.assertEqual(out["looked"], [{"family": "a", "passed": False}])
        self.assertEqual(out["refused"], ["b"])
        self.assertEqual(len(self.store.looks()), 1, "one look: the Holm bar is raised once")
        self.assert_refused("b", 1, of_look=1, match="run_sha", bodies=2)
        self.assertEqual(self.store.family("b")["band"], "gym")

    def test_a_new_run_sha_in_the_same_lineage_is_looked_at(self):
        self.looked_first()
        v2 = self.add("a", "puts")  # a genuinely different version: other code, other behaviour
        self.validate()
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])
        self.replies = [PASS, PASS]
        out = self.gate.run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": False}])
        self.assertEqual([x["version"] for x in self.store.looks()], [1, v2["n"]])
        self.assertEqual(self.store.refusals("a"), [])
        self.assertEqual(self.duplicate_events(), [])

    def test_the_refusal_is_idempotent_across_tournament_and_gate_rounds(self):
        self.add("a", "calls")
        self.add("b", "calls", structure="debit_vertical")
        self.validate()
        self.replies = [PASS, PASS]
        self.gate.run()
        self.assert_refused("b", 1, of_look=1, match="run_sha", bodies=2)
        jobs = len(self.pool.jobs)
        for _ in range(2):
            self.validate()  # the same image: nothing to validate again
            # A best submitted again is judged from its recorded result: the tournament keeps it off the gate.
            self.store.update_family("b", validated_version=None)
            self.validate()
            self.assertFalse(self.store.family("b")["state"]["gate_ready"])
            out = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
            self.assertEqual((out["looked"], out["refused"], out["waiting"]), ([], [], []))
        self.assertEqual(len(self.store.refusals("b")), 1)
        self.assertEqual(len(self.duplicate_events()), 1)
        self.assertEqual(len(self.pool.jobs), jobs, "no Gym job of any kind")
        self.assertEqual(len(self.sail.bodies), 2)
        self.assertEqual(len(self.store.looks()), 1)

    def test_a_look_still_in_flight_elsewhere_makes_the_repeat_wait_then_it_is_refused(self):
        self.add("a", "calls")
        self.add("b", "calls", structure="debit_vertical")
        self.validate()
        self.pool.slow.add("a")  # a's look is out when b comes up
        self.replies = [PASS, PASS]
        out = self.gate.run()
        self.assertEqual(out["waiting"], ["b"])
        self.assertEqual(self.store.refusals("b"), [])
        self.assertTrue(self.store.family("b")["state"]["gate_ready"], "it waits: a's look may yet be owed")
        self.assertEqual(len(self.sail.bodies), 2, "no review of b meanwhile")
        self.assertEqual(self.holdout_jobs("b"), [])
        job, late = self.pool.landing[0]
        late(weak(job))
        self.assertEqual(len(self.store.looks()), 1)
        self.gate.run()
        self.assert_refused("b", 1, of_look=1, match="run_sha", bodies=2)

    def test_a_versions_own_landed_look_only_closes_its_place(self):
        look = self.looked_first()
        # Its mark lost to a newer validation meanwhile, as a compare-and-set can: the gate is done with it all the same.
        self.store.set_state("a", gated_sha=None, gate_ready=True)
        out = self.gate.run()
        self.assertEqual((out["looked"], out["refused"]), ([], []))
        self.assertEqual(self.store.refusals("a"), [], "its own look is no duplicate: its verdict stands")
        state = self.store.family("a")["state"]
        self.assertEqual((state["gate_ready"], state["gated_sha"]), (False, look["run_sha"]))
        self.assertEqual(state["gate_outcome"]["result"], "failed")
        self.assertEqual(len(self.holdout_jobs()), 1)


class ValidationDuplicates(DuplicateCase):
    def test_a_program_that_differs_only_in_a_comment_is_refused_in_any_lineage(self):
        self.looked_first()
        self.add("c", "calls", note="tidied the comments", structure="debit_vertical")
        self.assertNotEqual(self.sha("c", 1), self.sha("a", 1), "another program to the swarm")
        self.validate()
        self.assertTrue(self.store.family("c")["state"]["gate_ready"])
        out = self.gate.run()
        self.assertEqual(out["refused"], ["c"])
        self.assert_refused("c", 1, of_look=1, match="validation", bodies=2)

    def test_the_same_in_the_looked_familys_own_lineage(self):
        self.looked_first()
        v2 = self.add("a", "calls", note="renamed a helper")
        self.validate()
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])
        out = self.gate.run()
        self.assertEqual(out["refused"], ["a"])
        self.assert_refused("a", v2["n"], of_look=1, match="validation", bodies=2)
        self.assertEqual(len(self.store.looks()), 1)

    def test_an_override_that_restates_a_default_is_the_same_program_under_another_engine_too(self):
        self.looked_first()
        self.add("d", "calls", params={"k": 1}, structure="debit_vertical", code=self.store.version("a", 1)["code"])
        self.assertNotEqual(self.sha("d", 1), self.sha("a", 1), "the swarm's run sha reads the override as written")
        self.engine_code = "engine-code-2"  # a Gym deploy since a's validation: the outcome no longer compares
        self.validate()
        out = self.gate.run()
        self.assertEqual(out["refused"], ["d"])
        self.assert_refused("d", 1, of_look=1, match="program", bodies=2)

    def test_a_genuinely_different_program_is_looked_at(self):
        self.looked_first()
        self.add("e", "puts", structure="debit_vertical")
        self.validate()
        self.replies = [PASS, PASS]
        out = self.gate.run()
        self.assertEqual(out["looked"], [{"family": "e", "passed": False}])
        self.assertEqual(self.duplicate_events(), [])

    def test_a_result_that_names_no_engine_is_never_compared(self):
        """Fail-open on what cannot be said: a result without the Gym's identity (an old or synthetic one) is judged as
        before, however its figures look."""
        self.answer = lambda job: self.holdout(job) if job.window == "holdout" else result(job.name, window=job.window, t=4.0)
        self.looked_first()
        self.add("f", "calls", note="other code", structure="debit_vertical")
        self.validate()
        self.replies = [PASS, PASS]
        out = self.gate.run()
        self.assertEqual(out["looked"], [{"family": "f", "passed": False}])

    def test_a_repeat_that_lands_between_the_check_and_the_mark_starts_no_look(self):
        self.add("a", "calls")
        self.add("c", "calls", note="tidied", structure="debit_vertical")
        self.validate()
        self.replies = [PASS, PASS]
        self.gate.run()  # a looked; c refused
        self.store.set_state("c", gated_sha=None, gate_ready=True)  # as if c's round had read before a's look landed
        fam = self.store.family("c")
        self.assertIsNone(self.gate.look(fam, self.store.version("c", 1), self.sha("c", 1)))
        self.assertEqual(self.holdout_jobs("c"), [])
        self.assertIsNone(self.store.family("c")["state"].get("look_inflight"))


class NoFigures(DuplicateCase):
    def test_the_refusal_carries_no_validation_or_holdout_figure(self):
        self.sentinels = True
        self.looked_first()
        self.add("c", "calls", note="tidied", structure="debit_vertical")
        self.validate()
        self.gate.run()
        state = self.store.family("c")["state"]
        self.assertEqual(state["validation_numbers"]["t"], T, "the sentinels are in the store, there to leak")
        [row] = self.store.refusals("c")
        for where, text in (("the gate's answer", state["gate"]), ("the refusal", row["reason"])):
            self.assertEqual(re.findall(r"\d+", text), ["1"], f"{where}: the earlier look's number and no other figure")
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, background=False)
        fam = self.store.family("c")
        status = researcher.status(fam)
        self.assertIn("a duplicate of holdout look #1", status)
        for where, text in (("status", status), ("brief", researcher.brief(fam))):
            for literal in LITERALS:
                self.assertNotIn(literal, text)
            self.assertIsNone(PATTERN.search(text), f"Researcher.{where} shows a Validation figure")

    def test_every_kind_of_reason_names_only_the_look(self):
        for match in ("run_sha", "program", "validation"):
            words = duplicate_words({"seq": 7, "match": match})
            self.assertEqual(re.findall(r"\d+", words), ["7"])
            self.assertIn("duplicate", words)
            for verdict in ("pass", "fail"):  # nor the earlier look's verdict
                self.assertNotIn(verdict, words)


class TheGymsIdentity(unittest.TestCase):
    """What `validation_identity` reads is what the real Gym's validation view carries."""

    def test_identity_is_hashes_of_the_program_and_of_a_finished_outcome(self):
        base = {"run_sha": "p" * 64, "status": "ok", "engine": "gym-engine-4", "code": "c", "tables": "t", "window": "validation",
                "roots": ["QQQ", "SPY"], "summary": {"trades": 60, "t_daily": 2.5}, "fills": {}, "breakdown": {}}
        ids = dict(validation_identity(base))
        self.assertEqual(ids["program"], "p" * 64)
        self.assertEqual(len(ids["outcome"]), 64)
        same = {**base, "run_sha": "q" * 64, "program": "other", "params": {"k": 2}, "gym_image": "x", "run_id": "r",
                "roots": ["SPY", "QQQ"], "runtime": {"timeouts": 1}}
        self.assertEqual(dict(validation_identity(same))["outcome"], ids["outcome"], "the program's own identity is left out")
        for change in ({"code": "c2"}, {"summary": {"trades": 60, "t_daily": 2.6}}, {"roots": ["SPY"]}):
            self.assertNotEqual(dict(validation_identity({**base, **change}))["outcome"], ids["outcome"], change)
        for unfinished in ({"status": "no_data"}, {"summary": {"trades": 0}}, {"engine": None}, {"code": ""}):
            self.assertNotIn("outcome", dict(validation_identity({**base, **unfinished})), unfinished)
        self.assertEqual(validation_identity(None), frozenset())

    @unittest.skipUnless(GYM, "the Gym's modules")
    def test_the_validation_view_keeps_every_key_the_identity_reads(self):
        from league.gym.results import view
        from league.swarm.gate import VALIDATION_IDENTITY

        full = {key: key for key in VALIDATION_IDENTITY + ("run_sha", "trades", "daily", "worst", "drift")}
        full.update(breakdown={"quarter": {}}, runtime={}, **{"stress_1.5": {"stress": 1.5}})
        kept = view(full, "validation")
        self.assertEqual(sorted(k for k in VALIDATION_IDENTITY + ("run_sha",) if k not in kept), [])
        self.assertNotIn("trades", kept)

    @unittest.skipUnless(GYM, "the Gym's modules")
    def test_an_override_restating_a_default_is_one_program_to_the_gym_and_two_to_the_swarm(self):
        from league.gym.runtime import load_program

        code = program("calls")
        self.assertEqual(load_program(code, params={}).run_sha, load_program(code, params={"k": 1}).run_sha)
        self.assertNotEqual(load_program(code, params={}).run_sha, load_program(code, params={"k": 2}).run_sha)
        sha = hashlib.sha256(code.encode()).hexdigest()
        self.assertNotEqual(run_sha({"sha": sha, "params": {}}), run_sha({"sha": sha, "params": {"k": 1}}))


if __name__ == "__main__":
    unittest.main()
