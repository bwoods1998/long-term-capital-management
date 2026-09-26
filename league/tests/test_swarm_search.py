"""The swarm's search as the sprint re-tuned it (Sept 26, 2026): the robust Train objective and its one-time migration,
robustness runs at the pool's lowest priority, Validation seen only as pass or fail and a count (the owner's decision
D2a), pooled roots, the architect's agenda, the bandit's top ten on the stronger profile, reseeds, and the Gym's per-year
block. Every program and result here is invented."""

from __future__ import annotations

import json

from league.gym import results as R
from league.swarm import diagnostics
from league.swarm.architect import SYSTEM, Architect
from league.swarm.pool import ROBUSTNESS_PRIORITY, GymJob
from league.swarm.researcher import OBJECTIVE, migrate_objective, needs_of, needs_roots, with_roots
from league.swarm.seeds import SEEDS, family_spec, program_for
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import result
from league.tests.test_swarm_loop import LoopCase
from league.tests.test_swarm_pool import PoolCase
from league.tests.test_swarm_researcher import FakePool, ResearcherCase, calls_in
from league.tests.test_swarm_rounds import RoundCase


def yearly(name="p", roots=("SPY",), t=(2.0, 2.5, 3.0), trades=(60, 60, 60), days=(30, 30, 30), quarters="12/12", pnl=500.0,
           status="ok", stress=1.0):
    """An invented Train result with the Gym's per-year block (2022-2024)."""
    r = result(name, roots=tuple(roots), quarters=quarters, pnl=pnl, status=status)
    r["stress"] = stress
    r["by_year"] = {str(2022 + i): {"trades": trades[i], "days": 252, "days_traded": days[i], "pnl": pnl / 3,
                                     "t_daily": t[i], "mean_return_on_max_loss_daily": 0.01, "quarters_positive": "4/4"}
                    for i in range(3)}
    return r


class QueueingPool(FakePool):
    """The researcher's fake pool with `submit`: robustness jobs wait here until a test lands them."""

    def __init__(self, answer=None):
        super().__init__(answer)
        self.queued: list[GymJob] = []

    def submit(self, job):
        self.queued.append(job)
        return job

    def land(self, job, answer):
        job.late(answer)


class RobustObjective(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.shape: dict = {}
        self.pool = QueueingPool(lambda job: yearly(job.name, roots=job.roots, **self.shape))

    def run_params(self, params, **shape):
        self.shape = shape
        self.steps = [{"calls": [("gym_run", {"params": params})]}, {"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        return json.loads(calls_in(self.sail.bodies[-1])[-1]["output"])

    def test_the_best_is_the_worst_year_and_an_ineligible_version_never_becomes_it(self):
        self.researcher().cycle(self.fam["id"])  # the starter: eligible, worst year t 2.0, every quarter positive
        fam = self.store.family(self.fam["id"])
        self.assertEqual((fam["best_train"], fam["best_version"], fam["state"]["best_train_version"]), (2.0, 1, 1))
        view = self.run_params({"vrp_min": 1.3}, t=(9.0, 9.0, 9.0), trades=(60, 12, 60))
        self.assertFalse(view["train_score"]["eligible"])
        self.assertIn("every Train year", view["train_score"]["why_not_eligible"])
        self.assertEqual(self.store.family(self.fam["id"])["best_train"], 2.0, "a sparse year keeps a version out")
        view = self.run_params({"vrp_min": 1.35}, t=(2.6, 2.8, 2.7), quarters="9/12")
        self.assertNotIn("new_best_train_score", view, "2.6 x 9/12 of quarters is below the best's 2.0")
        view = self.run_params({"vrp_min": 1.4}, t=(2.6, 2.8, 2.7))
        self.assertEqual((view["new_best_train_score"], view["train_score"]["worst_year"]), (2.6, "2022"))
        fam = self.store.family(self.fam["id"])
        self.assertEqual(fam["state"]["best_train_version"], 4)
        self.assertEqual([c[1] for c in fam["state"]["train_candidates"]], [4, 1, 3])

    def test_a_new_best_queues_two_robustness_runs_at_the_lowest_priority(self):
        researcher = self.researcher()
        researcher.cycle(self.fam["id"])
        jobs = [(j.version, j.window, j.stress, j.purpose, j.priority) for j in self.pool.queued]
        self.assertEqual(jobs, [(1, "train", 1.5, "robustness", ROBUSTNESS_PRIORITY), (1, "train", 0.0, "robustness", ROBUSTNESS_PRIORITY)])
        self.shape = {"t": (1.0, 1.0, 1.0)}
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"text": "ok"}]
        researcher.cycle(self.fam["id"])
        self.assertEqual(len(self.pool.queued), 2, "no new best, no robustness run")
        self.steps = [{"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        self.assertEqual(len(self.pool.queued), 4, "a restarted process queues the best's missing robustness again")

    def test_robustness_counts_as_trials_reaches_the_status_and_a_loss_at_stress_demotes(self):
        researcher = self.researcher()
        researcher.cycle(self.fam["id"])
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.4}})]}, {"text": "ok"}]
        self.shape = {"t": (2.6, 2.8, 2.7)}
        researcher.cycle(self.fam["id"])
        self.assertEqual(self.store.family(self.fam["id"])["state"]["best_train_version"], 2)
        stress, mid = [j for j in self.pool.queued if j.version == 2]
        trials = self.store.family(self.fam["id"])["trials"]
        self.pool.land(mid, yearly("mid", pnl=900.0, stress=0.0))
        self.pool.land(stress, yearly("stressed", pnl=-40.0, stress=1.5))
        fam = self.store.family(self.fam["id"])
        self.assertEqual(fam["trials"], trials + 2, "robustness runs are trials")
        self.assertEqual((fam["state"]["best_train_version"], fam["best_train"], fam["state"]["robust_failed"]), (1, 2.0, [2]),
                         "the next eligible candidate takes the place of a version that loses at 1.5x")
        rows = fam["state"]["robustness"]["2"]
        self.assertEqual((rows["mid"]["pnl"], rows["stress_1.5"]["pnl"]), (900.0, -40.0))
        self.assertEqual(set(rows["mid"]["by_year"]), {"2022", "2023", "2024"})
        self.assertIn("lost money on Train at 1.5x", researcher.status(fam))
        self.assertEqual([e["payload"]["action"] for e in self.store.events_after(0) if e["kind"] == "swarm.robustness"], ["demoted"])
        self.assertEqual({r["purpose"] for r in self.store.runs(self.fam["id"], window="train")}, {"train", "robustness"})
        # The failed version run again (same code and parameters) never becomes the best again.
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.4}})]}, {"text": "ok"}]
        researcher.cycle(self.fam["id"])
        self.assertEqual(self.store.family(self.fam["id"])["state"]["best_train_version"], 1)
        # The best's own robustness, once it lands, shows in the status block.
        v1 = [j for j in self.pool.queued if j.version == 1]
        for job in v1[:2]:
            self.pool.land(job, yearly("ok", pnl=300.0, stress=job.stress))
        self.assertIn("Robustness of your best (version 1", researcher.status(self.store.family(self.fam["id"])))

    def test_submit_takes_only_an_eligible_run_of_a_version_that_held_at_stress(self):
        self.researcher().cycle(self.fam["id"])
        sparse = self.run_params({"vrp_min": 1.3}, trades=(60, 12, 60))
        self.steps = [{"calls": [("submit", {"run_id": sparse["run_id"]})]}, {"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        outputs = [json.loads(i["output"]) for i in calls_in(self.sail.bodies[-1])]
        self.assertTrue(any("cannot be your best" in str(o.get("error")) for o in outputs), outputs)
        self.assertEqual(self.store.family(self.fam["id"])["best_version"], 1)
        steady = self.run_params({"vrp_min": 1.5}, t=(1.0, 1.1, 1.2))
        self.steps = [{"calls": [("submit", {"run_id": steady["run_id"]})]}, {"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        self.assertEqual(self.store.family(self.fam["id"])["best_version"], 3, "an eligible run below the best may be submitted")
        self.store.set_state(self.fam["id"], robust_failed=[3])
        ok, why = self.researcher().eligible_run(self.fam, self.store.run(steady["run_id"]))
        self.assertFalse(ok)
        self.assertIn("1.5x", why)

    def test_the_migration_rescores_kept_runs_keeps_the_old_selection_and_runs_once(self):
        fid = self.fam["id"]
        v1 = self.store.add_version(fid, "# v1\nNEEDS = {'roots': ['SPY']}\n", {}, author="t")
        v2 = self.store.add_version(fid, "# v2\nNEEDS = {'roots': ['SPY']}\n", {}, author="t")
        self.store.add_run(fid, v1["n"], yearly("old-sparse", t=(9.0, 0.1, 0.1), trades=(80, 10, 10)), window="train", stress=1.0,
                           purpose="train")
        self.store.add_run(fid, v2["n"], yearly("steady", t=(1.4, 1.5, 1.6)), window="train", stress=1.0, purpose="train")
        self.store.update_family(fid, best_train=9.9, best_version=v1["n"], stall=4)
        self.store.set_state(fid, best_train_version=v1["n"], best_train_run="old-run")
        other = self.store.add_family({**family_spec(SEEDS[1])}, origin="seed")["id"]
        self.store.update_family(other, best_train=3.3, best_version=None)
        out = migrate_objective(self.store)
        self.assertEqual(out, {"migrated": 2, "with_best": 1})
        fam = self.store.family(fid)
        self.assertEqual((fam["best_train"], fam["best_version"], fam["state"]["best_train_version"], fam["stall"]), (1.4, v2["n"], v2["n"], 0))
        self.assertEqual((fam["state"]["legacy_best"]["best_train"], fam["state"]["legacy_best"]["best_version"]), (9.9, v1["n"]))
        empty = self.store.family(other)
        self.assertEqual((empty["best_train"], empty["best_version"], empty["state"]["legacy_best"]["best_train"]), (None, None, 3.3))
        self.assertEqual(self.store.get("train_objective"), OBJECTIVE)
        self.assertEqual(migrate_objective(self.store), {"migrated": 0, "with_best": 0}, "once per store")


class Robustness(PoolCase):
    def robustness(self, family="r"):
        return GymJob(family=family, version=1, code="NEEDS = {}", params={}, window="train", roots=("SPY",), stress=1.5,
                      purpose="robustness", priority=ROBUSTNESS_PRIORITY)

    def test_robustness_waits_behind_every_other_job_and_leaves_a_box_free(self):
        pool = self.pool(batch_programs=1)
        box = self.ready_box(pool)
        other = self.ready_box(pool)
        pool.submit(self.robustness())
        pool.submit(GymJob(family="t", version=1, code="NEEDS = {}", params={}, window="train", roots=("SPY",), priority=0.0))
        pool.submit(GymJob(family="v", version=1, code="NEEDS = {}", params={}, window="validation", roots=("SPY",), priority=1.0))
        self.assertEqual([j.family for j in pool._take(box)], ["v"])
        self.assertEqual([j.family for j in pool._take(box)], ["t"], "a researcher's run before any robustness run")
        other.state = "busy"
        self.assertEqual(pool._take(box), [], "the last free box stays free for the inner loop")
        other.state = "asleep"
        self.assertEqual([j.purpose for j in pool._take(box)], ["robustness"])

    def test_a_robustness_run_never_rides_in_a_researchers_batch(self):
        pool = self.pool(batch_programs=4)
        box = self.ready_box(pool)
        self.ready_box(pool)
        pool.submit(self.robustness("r"))
        pool.submit(GymJob(family="s", version=1, code="NEEDS = {}", params={}, window="train", roots=("SPY",), stress=1.5,
                           priority=0.2))  # a researcher's own run at 1.5x: the same settings as the robustness run
        self.clock.advance(9)
        self.assertEqual([j.family for j in pool._take(box)], ["s"])
        self.assertEqual([j.family for j in pool._take(box)], ["r"])

    def test_a_robustness_job_neither_supersedes_nor_is_superseded_by_a_research_run(self):
        pool = self.pool()
        robust = pool.submit(self.robustness("f"))
        pool.submit(GymJob(family="f", version=2, code="NEEDS = {}", params={}, window="train", roots=("SPY",)))
        self.assertFalse(robust.done.is_set())
        self.assertEqual(pool.queued(), 2)


class ValidationFeedback(RoundCase):
    """D2a: Validation reaches a researcher or the architect only as pass or fail and a count of checks passed."""

    LEGACY = ('iron_condor on SPY: The mechanism failed. Tried 9 versions over 44 lineage trials; best Train score 1.7; best '
              'validation {"checks_not_met":["dsr","t"],"line_met":false,"mean_return_on_max_loss":0.0123,"quarters_positive":"3/4",'
              '"t":1.234}. Last notes: wings too narrow')

    def line(self, passed=False):
        checks = {k: True for k in ("status_ok", "trades", "days", "mean_positive", "quarters", "stress")}
        checks.update(t=passed, dsr=passed)
        return {"passed": passed, "checks": checks, "numbers": {"mean": 0.0123, "t": 1.234, "dsr": 0.4321, "trades": 173}}

    def test_a_pre_d2_lesson_loses_its_validation_numbers_wherever_a_model_reads_it(self):
        self.family("dead")
        self.store.retire("dead", "synthetic")
        self.store.bury("dead", self.LEGACY)
        text = diagnostics.scrub(self.LEGACY)
        self.assertIn("best validation: line not met. Last notes: wings too narrow", text)
        cut = diagnostics.scrub(self.LEGACY[:220])
        for leak in ("0.0123", "1.234", "checks_not_met", '"t"'):
            self.assertNotIn(leak, text)
            self.assertNotIn(leak, cut, "a length cut that took the closing brace still hides the numbers")
            self.assertNotIn(leak, Architect(self.store, self.router, self.settings, clock=self.clock).prompt())

    def test_a_new_lesson_carries_the_verdict_and_count_only(self):
        self.family("a")
        self.store.set_state("a", validation_line=self.line(), validation_view={"t": 1.234})
        self.store.retire_gym("a", "Costs won.", floor=0, source="tournament")
        lesson = self.store.graveyard()[0]["lesson"]
        self.assertIn("best validation: did not meet the validation line (6 of 8 checks passed)", lesson)
        self.assertNotIn("1.234", lesson)

    def test_the_architect_sees_a_count_of_checks_never_a_validation_number(self):
        self.family("a")
        self.store.set_state("a", validation_line=self.line(), validation_numbers={"mean": 0.0123, "t": 1.234})
        self.store.put("leaderboard", {"board": [{"family": "a", "band": "gym", "structure": "iron_condor", "roots": ["SPY"],
                                                  "validation": {"mean": 0.0123, "t": 1.234}, "share": 1.0}]})
        prompt = Architect(self.store, self.router, self.settings, clock=self.clock).prompt()
        living = json.loads(prompt.split("(leaderboard):\n", 1)[1].split("\n\nTHE GRAVEYARD", 1)[0])
        self.assertEqual(living[0]["validation"], {"line_met": False, "checks_passed": 6, "checks": 8})
        for leak in ("0.0123", "1.234"):
            self.assertNotIn(leak, prompt)

    def test_a_forks_first_note_carries_no_validation_number(self):
        self.family("a")
        self.store.set_state("a", validation_numbers={"mean": 0.05, "t": 2.345, "sharpe_daily": 0.2, "quarters": "4/4"})
        [child] = Tournament(self.store, self.pool, self.settings).forks(self.store.families(alive=True))
        self.assertNotIn("2.345", " ".join(n["text"] for n in self.store.notebook(child)))


class ArchitectRootsAndAgenda(RoundCase):
    def architect(self):
        return Architect(self.store, self.router, self.settings, clock=self.clock)

    def test_the_architect_admits_up_to_five_pooled_roots_of_the_admitted_list(self):
        rows = [{"slug": "pooled", "mechanism": "The same afternoon drift shows up across the index ETFs on different days.",
                 "structure": "debit_vertical", "roots": ["spy", "QQQ", "IWM", "TSLA", "SPXW", "SPY", "XSP"], "dte": [0, 2]},
                {"slug": "one", "mechanism": "A single root keeps working exactly as it did before the sprint began.",
                 "structure": "long_call", "roots": "QQQ", "dte": [0, 2]}]
        born = self.architect().admit(rows)
        self.assertEqual([self.store.family(f)["roots"] for f in born], [["SPY", "QQQ", "IWM", "SPXW", "XSP"], ["QQQ"]])

    def test_the_request_prices_xsp_and_states_the_d2_line_and_the_worst_year(self):
        self.assertIn("$0.50 a contract", SYSTEM)
        self.assertIn(">= 50 trades on >= 25", SYSTEM)
        self.assertIn("WORST Train year", SYSTEM)
        self.assertIn("one to five", SYSTEM)

    def test_the_operators_agenda_closes_the_request_and_is_trimmed(self):
        self.family("a")
        self.assertNotIn("AGENDA", self.architect().prompt())
        self.settings["architect"]["agenda"] = "  Pool SPY and QQQ debit verticals.\nTry multi-day holds.  "
        prompt = self.architect().prompt()
        self.assertTrue(prompt.endswith("\n\nTHE OPERATOR'S RESEARCH AGENDA:\nPool SPY and QQQ debit verticals.\nTry multi-day holds."))
        self.settings["architect"]["agenda"] = "x" * 5000
        tail = self.architect().prompt().split("THE OPERATOR'S RESEARCH AGENDA:\n", 1)[1]
        self.assertEqual(len(tail), 4000)


class TopTen(ResearcherCase):
    def test_the_bandits_top_ten_think_on_the_stronger_profile_inside_the_pace(self):
        self.researcher().cycle(self.fam["id"])
        for i in range(3):
            other = self.store.add_family({**family_spec(self.spec), "id": f"other-{i}"}, origin="seed")
            self.store.update_family(other["id"], weight=0.1)
        self.store.update_family(self.fam["id"], weight=0.5)
        self.settings["researcher"]["top_families"] = 1
        self.steps = [{"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        body = self.sail.bodies[-1]
        self.assertEqual((body["model"], body["reasoning"]["effort"]), ("deepseek-ai/DeepSeek-V4-Pro-0813", "low"))
        self.store.update_family(self.fam["id"], weight=0.05)  # out of the top one
        self.steps = [{"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        self.assertEqual((self.sail.bodies[-1]["model"], self.sail.bodies[-1]["reasoning"]["effort"]),
                         ("deepseek-ai/DeepSeek-V4-Flash-0731", "minimal"))
        self.store.update_family(self.fam["id"], weight=0.5)
        r = self.researcher()
        r.pace = lambda: True  # at the swarm's hourly pace: every cycle on the ordinary profile
        self.steps = [{"text": "ok"}]
        r.cycle(self.fam["id"])
        self.assertEqual(self.sail.bodies[-1]["model"], "deepseek-ai/DeepSeek-V4-Flash-0731")


class Reseed(LoopCase):
    def test_reseeds_found_seeds_on_untried_roots_join_their_founders_lineage_and_stay_off_by_default(self):
        sw = self.swarm()
        sw.seed()
        for fam in self.store.families(alive=True)[:10]:
            self.store.retire(fam["id"], "synthetic")
        self.assertEqual(sw.reseed(), [], "off unless population.reseed_max is set")
        sw.settings["population"]["reseed_max"] = 4
        born = sw.reseed()
        self.assertEqual(len(born), 4)
        for fid in born:
            fam = self.store.family(fid)
            founder = self.store.family(fam["parent"])
            self.assertEqual((fam["origin"], fam["mechanism"], fam["lineage"]), ("reseed", founder["mechanism"], founder["lineage"]))
            self.assertNotIn("XSP", fam["roots"])
            self.assertNotIn(fam["roots"][0], founder["roots"])
            self.assertEqual(needs_of(program_for(fam["spec"])[0])["roots"], fam["roots"], "the starter trades the new root")
        sw.settings["population"]["reseed_max"] = 50
        sw.reseed()
        self.assertEqual(len(self.store.families(alive=True)), 48, "never past the start")


class RootsHelpers(RoundCase):
    def test_needs_roots_and_with_roots(self):
        code = "import math\nNEEDS = {'roots': ['spy', 'SPY', 'qqq'], 'dte': [0, 2]}\nPARAMS = {}\n"
        self.assertEqual(needs_roots(code), ("SPY", "QQQ"))
        self.assertEqual(needs_roots("PARAMS = {}", ["IWM"]), ("IWM",))
        widened = with_roots(code, ["SPY", "QQQ", "IWM"])
        self.assertEqual(needs_of(widened), {"roots": ["SPY", "QQQ", "IWM"], "dte": [0, 2]})
        self.assertTrue(widened.startswith("import math\n") and widened.endswith("PARAMS = {}\n"))
        self.assertIsNone(with_roots("NEEDS = make()\n", ["SPY"]))


class GymYears(RoundCase):
    def test_the_gyms_per_year_block_and_traded_day_moments(self):
        daily = [[f"{y}-{m:02d}-10", 1.0 if m % 2 else -0.5, 0.0] for y in (2022, 2023) for m in range(1, 13)]
        trades = [{"day": d[0], "pnl": 3.0 if i % 3 else -2.0, "max_loss": 50.0} for i, d in enumerate(daily) if i % 4]
        years = R.by_year(trades, daily)
        self.assertEqual(set(years), {"2022", "2023"})
        self.assertEqual((years["2022"]["days"], years["2022"]["trades"]), (12, sum(1 for t in trades if t["day"].startswith("2022"))))
        self.assertEqual(years["2022"]["quarters_positive"], "2/4")
        self.assertEqual(R.by_year([], [["2024-01-02", 0.0, 0.0]])["2024"]["t_daily"], None, "a year without a trade is kept")
        summary = R.summarize([{**t, "return_on_max_loss": t["pnl"] / 50.0, "fees": 0.0} for t in trades], daily, 10000.0)
        self.assertIn("skew_traded", summary)
        self.assertIn("kurt_traded", summary)
        self.assertNotIn("by_year", R.view({"summary": {}, "by_year": years, "breakdown": {}}, "validation"),
                         "no year leaves a validation run")

