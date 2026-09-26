"""The diagnostician (league/swarm/diagnostician.py): who is eligible, what it sees (Train in full, Validation only as a
verdict and a count, D2a), how a rewrite becomes a version authored "diagnostician" through the researcher's own safety
check and Train run, when a retirement is honored, and its budgets. The real router, the real Claude client over a fake
opener, the real Researcher over a scripted Sail and a fake Gym."""

from __future__ import annotations

import io
import json
import unittest
import urllib.error
from decimal import Decimal

from league.claude import Claude
from league.swarm.diagnostician import SCHEMA, Diagnostician, withheld
from league.tests.test_claude import message
from league.tests.test_frontier import GATEWAY, FakeOpener
from league.tests.test_swarm_loop import LoopCase
from league.tests.test_swarm_researcher import GYM, ResearcherCase
from league.tests.swarm_fakes import result

#: Validation's figures and check names: none of them may reach the diagnostician.
SECRET_T, SECRET_MEAN, SECRET_DSR = 3.14159, 0.0123456, 0.271828
CHECKS_6_OF_8 = {"status_ok": True, "trades": True, "days": False, "mean_positive": True, "t": False, "dsr": True,
                 "quarters": True, "stress": True}


class FakeClaudeMeter:
    def __init__(self, remaining):
        self.value = remaining

    def remaining(self):
        return None if self.value is None else Decimal(str(self.value))


def reply(decision="rewrite", *, program="", note="Enter only after a calm open.", lesson="", cost="0.412000"):
    return message(json.dumps({"decision": decision, "diagnosis": "Losses cluster on trend days.", "note": note,
                               "program": program, "lesson": lesson}), cost=cost)


class DiagnosticianCase(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.claude = FakeOpener()
        self.meter = FakeClaudeMeter(100)
        self.router.claude_factory = lambda model: Claude(GATEWAY, lambda: "synthetic", model=model, opener=self.claude)
        self.router.claude_meter = self.meter
        self.fid = self.fam["id"]
        self.researcher_obj = self.researcher()
        self.researcher_obj.cycle(self.fid)  # the starter: version 1 and its Train run
        self.stuck(self.fid)

    def stuck(self, fid, *, validations=2, checks=CHECKS_6_OF_8, passed=False):
        self.store.update_family(fid, validations=validations, best_version=1)
        self.store.set_state(fid, validation_line={"passed": passed, "checks": checks,
                                                   "numbers": {"t": SECRET_T, "mean": SECRET_MEAN, "dsr": SECRET_DSR}},
                             validation_view={"mean_return_on_max_loss": SECRET_MEAN, "t": SECRET_T, "line_met": passed,
                                              "checks_not_met": sorted(k for k, ok in checks.items() if not ok)},
                             validation_numbers={"mean": SECRET_MEAN, "t": SECRET_T})

    def diagnostician(self, **kw):
        return Diagnostician(self.store, self.router, self.settings, pool=self.pool, researcher=self.researcher_obj,
                             contract="THE CONTRACT BODY", clock=self.clock, **kw)

    def best_code(self):
        return self.store.version(self.fid, 1)["code"]

    def rewritten(self):
        return self.best_code().replace("def pick_dte(chain, lo, hi):",
                                        "def calm(under):\n    return len(under.prices) > 30\n\n\ndef pick_dte(chain, lo, hi):")

    def events(self):
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.diagnostician"]


class Eligibility(DiagnosticianCase):
    def test_stuck_or_near_miss_families_are_eligible_once_per_six_hours_and_only_on_new_evidence(self):
        d = self.diagnostician()
        self.assertIsNotNone(d.eligible(self.store.family(self.fid)))
        one_of_five = {**CHECKS_6_OF_8, "dsr": False}  # 5 of 8
        cases = [(dict(validations=1, checks=one_of_five), False), (dict(validations=1, checks=CHECKS_6_OF_8), True),
                 (dict(validations=2, checks={k: False for k in CHECKS_6_OF_8}), True),
                 (dict(validations=3, checks={k: True for k in CHECKS_6_OF_8}, passed=True), False)]
        for kwargs, expected in cases:
            self.stuck(self.fid, **kwargs)
            self.assertEqual(d.eligible(self.store.family(self.fid)) is not None, expected, kwargs)
        self.stuck(self.fid)
        self.store.set_state(self.fid, diagnosed_at=self.clock(), diagnosed_validations=2)
        self.assertIsNone(d.eligible(self.store.family(self.fid)), "within six hours")
        self.clock.advance(6 * 3600 + 1)
        self.assertIsNone(d.eligible(self.store.family(self.fid)), "no new validation since the last diagnosis")
        self.store.update_family(self.fid, validations=3)
        self.assertIsNotNone(d.eligible(self.store.family(self.fid)))
        self.store.set_state(self.fid, rewrite_ready={"code": "x", "profile": "pro_asap"})
        self.assertIsNone(d.eligible(self.store.family(self.fid)), "a queued rewrite runs first")
        self.store.set_state(self.fid, rewrite_ready=None)
        self.store.set_band(self.fid, "candidate", reason="test")
        self.assertIsNone(d.eligible(self.store.family(self.fid)), "only Gym families")

    def test_a_family_never_validated_is_not_eligible_and_near_misses_go_first(self):
        other = self.store.add_family({**self.fam["spec"], "id": "fresh"}, origin="seed")
        d = self.diagnostician()
        self.assertIsNone(d.eligible(self.store.family(other["id"])))
        self.stuck(other["id"], validations=5, checks={**CHECKS_6_OF_8, "stress": False, "quarters": False})
        self.stuck(self.fid, validations=2)
        self.assertEqual([f["id"] for f, _ in d.candidates()], [self.fid, other["id"]], "6 of 8 before 4 of 8")


class WhatItSees(DiagnosticianCase):
    def test_train_in_full_validation_only_as_a_verdict_and_a_count(self):
        # A robustness run of the same version, a lesson carrying another family's validation figures, and a notebook.
        self.store.add_run(self.fid, 1, result("stress", daily=[1.0] * 250, pnl=250.0), window="train", stress=1.5, purpose="train")
        self.store.note(self.fid, f"My validation t was {SECRET_T}; dsr failed.")
        dead = self.store.add_family({**self.fam["spec"], "id": "condor-dead"}, origin="seed")
        self.store.set_state(dead["id"], validation_view={"t": 2.71828, "checks_not_met": ["mean_positive"]})
        self.store.retire_gym(dead["id"], "its trial-adjusted evidence fell below the line (deflated Sharpe probability 0.0314)",
                              floor=0, source="tournament")
        d = self.diagnostician()
        fam = self.store.family(self.fid)
        packet = d.packet(fam, d.eligible(fam))
        self.assertIn("VALIDATION: not passed; 6 of 8 checks passed on the latest; 2 validations so far.", packet)
        for secret in (str(SECRET_T), str(SECRET_MEAN), str(SECRET_DSR), "2.71828", "0.0314", "checks_not_met", "mean_positive",
                       "status_ok", "line_met", "dsr", "My validation"):
            self.assertNotIn(secret, packet, secret)
        self.assertIn("def pick_dte(chain, lo, hi):", packet, "the best program in full")
        for section in ('"by_train_year"', '"weekday"', '"fills"', "ROBUSTNESS", '"stress": 1.5', "LESSONS OF RETIRED FAMILIES",
                        "[withheld]", "condor"):
            self.assertIn(section, packet, section)
        self.assertIn('"by_train_year": {"2024": {"days": 250', packet, "P&L by Train year, from Train's own daily series")

    def test_withheld_cuts_validation_json_and_masks_numbers(self):
        text = 'iron_condor on SPY: stalled. Tried 12 versions; best validation {"t": 1.9, "x": [1, 2]}. Last notes: fine'
        self.assertEqual(withheld(text), "iron_condor on SPY: stalled. Tried # versions; best validation [withheld]. Last notes: fine")
        self.assertEqual(withheld("best validation null; t 2.5e-3"), "best validation [withheld]; t #")


class Rewrites(DiagnosticianCase):
    def test_a_rewrite_becomes_a_version_authored_by_the_diagnostician_through_the_researchers_own_run(self):
        self.claude.script = [reply(program=f"```python\n{self.rewritten()}\n```")]
        out = self.diagnostician().run()
        self.assertEqual(out["diagnosed"], [{"family": self.fid, "outcome": "rewrite", "cost_usd": 0.412}])
        body, headers = self.claude.body(), self.claude.headers()
        self.assertEqual((body["model"], body["output_config"]["effort"]), ("claude-opus-5-5", "high"))
        self.assertEqual(body["output_config"]["format"], {"type": "json_schema", "schema": SCHEMA})
        self.assertTrue(body["system"][0]["text"].endswith("THE CONTRACT BODY"))
        self.assertEqual((headers["x-ltcm-role"], headers["x-ltcm-agent"]), ("diagnostician", "swarm-diagnostician"))
        ready = self.store.family(self.fid)["state"]["rewrite_ready"]
        self.assertEqual((ready["profile"], ready["code"]), ("diagnostician", self.rewritten()))
        [event] = self.events()
        self.assertEqual((event["outcome"], event["route"], event["cost_usd"], event["checks_met"]), ("rewrite", "claude", 0.412, "6/8"))
        self.assertAlmostEqual(self.router.claude_spent(role="diagnostician"), 0.412)
        self.assertEqual(self.sail.bodies, [], "no Sail call: the diagnostician is Claude's")
        # The researcher's next cycle runs it: the safety check, a Train run, a new version authored "diagnostician".
        jobs = len(self.pool.jobs)
        self.steps = [{"text": "I will read the rewrite's run next cycle."}]
        self.researcher_obj.cycle(self.fid)
        latest = self.store.latest_version(self.fid)
        self.assertEqual((latest["n"], latest["author"], latest["code"]), (2, "diagnostician", self.rewritten()))
        self.assertEqual(len(self.pool.jobs), jobs + 1)
        self.assertEqual(self.pool.jobs[-1].window, "train")
        self.assertIsNone(self.store.family(self.fid)["state"]["rewrite_ready"])

    def test_without_structured_outputs_the_json_is_read_from_the_text(self):
        self.settings["diagnostician"]["structured"] = False
        self.claude.script = [message("My diagnosis follows.\n" + json.dumps({"decision": "rewrite", "diagnosis": "d", "note": "n",
                                                                               "program": self.rewritten(), "lesson": ""}))]
        self.assertEqual(self.diagnostician().run()["diagnosed"][0]["outcome"], "rewrite")
        self.assertNotIn("format", self.claude.body()["output_config"])

    def test_a_parameter_only_rewrite_another_root_or_no_program_is_not_run(self):
        params_only = self.code.replace("'vrp_min': 1.2", "'vrp_min': 1.6")  # the starter's NEEDS in another key order, too
        self.assertNotEqual(params_only, self.best_code())
        other_root = self.rewritten().replace("'roots': ['SPY']", "'roots': ['SPY', 'QQQ']")
        self.assertIn("QQQ", other_root)
        for program, reason in ((params_only, "only parameters changed"), (other_root, "QQQ"), ("", "no program")):
            with self.subTest(reason=reason):
                self.setUp()
                self.claude.script = [reply(program=program)]
                self.diagnostician().run()
                [event] = self.events()
                self.assertEqual(event["outcome"], "rejected")
                self.assertIn(reason, event["reason"])
                state = self.store.family(self.fid)["state"]
                self.assertIsNone(state.get("rewrite_ready"))
                self.assertTrue(state.get("diagnosed_at"), "a rejected rewrite still spends the family's six hours")
                self.assertIn("rewrite was not run", self.store.notebook(self.fid)[-1]["text"])

    def test_no_stall_rewrite_starts_while_the_call_is_out_and_one_in_flight_is_not_overwritten(self):
        seen = []

        def opener(request, timeout=None):
            fam = self.store.family(self.fid)
            self.store.update_family(self.fid, stall=10)
            seen.append(self.researcher_obj.request_rewrite(fam, {}))
            return reply(program=self.rewritten())

        self.claude = opener
        self.diagnostician().run()
        self.assertEqual(seen, [False], "the researcher's stall rewrite waits for the diagnostician")
        self.assertEqual(self.store.family(self.fid)["state"]["rewrite_ready"]["profile"], "diagnostician")
        self.assertNotIn(self.fid, self.researcher_obj._rewriting, "the claim is released")
        self.researcher_obj._rewriting[self.fid] = object()  # a Sail rewrite already in flight
        self.assertEqual(self.diagnostician().diagnose(self.store.family(self.fid), {"validations": 3, "met": 6, "total": 8})["outcome"],
                         "skipped")

    @unittest.skipUnless(GYM, "the Gym's safety check")
    def test_a_rewrite_the_safety_check_refuses_is_not_run(self):
        self.claude.script = [reply(program=self.rewritten() + "\nYEAR = 2025\n")]
        self.diagnostician().run()
        [event] = self.events()
        self.assertEqual(event["outcome"], "rejected")
        self.assertIn("safety check", event["reason"])


class Retirement(DiagnosticianCase):
    def test_a_retirement_is_honored_only_above_the_start_population(self):
        lesson = "Selling short-dated wings pays the spread twice for a premium the fills eat."
        self.claude.script = [reply("retire", lesson=lesson)]
        self.diagnostician().run()
        self.assertIsNone(self.store.family(self.fid)["retired_at"], "one family alive, 48 to start: a note, not a retirement")
        self.assertEqual(self.events()[-1]["outcome"], "retire_noted")
        self.assertIn(lesson, self.store.notebook(self.fid)[-1]["text"])

        self.settings["population"].update(start=1, floor=0)
        self.store.add_family({**self.fam["spec"], "id": "sibling"}, origin="seed")
        self.store.update_family(self.fid, validations=3)
        self.clock.advance(6 * 3600 + 1)
        self.claude.script = [reply("retire", lesson=lesson)]
        self.diagnostician().run()
        self.assertEqual(self.events()[-1]["outcome"], "retired")
        self.assertEqual(self.store.family(self.fid)["band"], "retired")
        self.assertIn(lesson, self.store.graveyard("wings")[0]["lesson"])


class Budgets(DiagnosticianCase):
    def test_the_day_budget_and_claudes_room_stop_it_before_any_call(self):
        self.store.add_spend("claude", 14.9, detail={"role": "diagnostician"})
        out = self.diagnostician().run()
        self.assertIn("day's diagnostician budget", out["skipped"])
        self.assertEqual(self.claude.calls, [])
        self.clock.advance(86401)  # yesterday's spend no longer counts
        self.store.add_spend("claude", 50.0, detail={"role": "architect"})  # other roles' spend is not the diagnostician's
        self.meter.value = 5.2  # but the funded total above its $5 reserve cannot hold the call
        self.assertIn("no room", self.diagnostician().run()["skipped"])
        self.assertEqual(self.claude.calls, [])
        self.meter.value = 100
        self.claude.script = [reply(program=self.rewritten())]
        self.assertEqual(self.diagnostician().run()["diagnosed"][0]["outcome"], "rewrite")

    def test_without_claude_nothing_is_asked_of_anyone(self):
        self.router.claude_factory = None
        self.assertEqual(self.diagnostician().run(), {"skipped": "Claude is not configured for the diagnostician"})
        self.settings["claude"]["roles"] = ["architect"]
        self.router.claude_factory = lambda model: Claude(GATEWAY, lambda: "synthetic", model=model, opener=self.claude)
        self.assertIn("skipped", self.diagnostician().run())
        self.assertEqual((self.claude.calls, self.sail.bodies), ([], []))

    def test_a_failed_call_is_asked_again_after_half_an_hour_and_disabled_means_never(self):
        refusal = urllib.error.HTTPError(GATEWAY, 402, "funded", {}, io.BytesIO(b'{"cap": "claude_funded"}'))
        self.addCleanup(refusal.close)
        self.claude.script = [refusal]
        out = self.diagnostician().run()
        self.assertEqual(out["diagnosed"][0]["outcome"], "error")
        self.assertEqual(self.store.spent(["claude"]), 0, "the gateway's refusal released the hold")
        d = self.diagnostician()
        self.assertIsNone(d.eligible(self.store.family(self.fid)))
        self.clock.advance(1801)
        self.assertIsNotNone(d.eligible(self.store.family(self.fid)))
        self.assertTrue(d.due())
        self.settings["diagnostician"]["enabled"] = False
        self.assertFalse(d.due())


class Scheduling(LoopCase):
    def test_the_loop_runs_the_diagnostician_round_and_reports_claude_spend(self):
        sw = self.swarm()
        calls = []
        sw.diagnostician.run = lambda: calls.append(1) or {"eligible": 0}
        sw.step()
        for thread in list(sw.rounds.values()):
            thread.join(10)
        self.assertEqual(calls, [1])
        self.assertIn("claude", sw.status()["spend_last_hour"])


if __name__ == "__main__":
    unittest.main()
