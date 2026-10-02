"""THE TRAIN KILL TESTS (LTCM v3, league/swarm/killtests.py): coverage of every Train year the roots had data, positive
after dropping each year's five best trades, the placebo beaten every covered year and the control ablation worse; applied
where Train eligibility is decided (league/swarm/researcher.py) and before validation (league/swarm/tournament.py). Invented
Train figures only."""

from __future__ import annotations

import copy
import unittest

from league.swarm import cards, evidence, killtests
from league.swarm.researcher import Researcher, kill_tests_passed
from league.tests.swarm_fakes import result
from league.tests.test_swarm_drift import QueueingPool
from league.tests.test_swarm_researcher import ResearcherCase

YEARS = ("2022", "2023", "2024")


def year_trades(year: str, n: int, pnl: float, *, best: tuple[float, ...] = ()) -> list[dict]:
    rows = [{"day": f"{year}-03-{(i % 28) + 1:02d}", "pnl": pnl, "max_loss": 60.0} for i in range(n - len(best))]
    return rows + [{"day": f"{year}-06-{i + 1:02d}", "pnl": b, "max_loss": 60.0} for i, b in enumerate(best)]


def train(name: str = "p", *, years=YEARS, n: int = 60, days: int = 30, pnl: float = 5.0, mean=0.01, best=None, rows=None,
          roots=("SPY",), status: str = "ok") -> dict:
    """An invented Train result: each year `n` trades on `days` days of `pnl` each (and a year's `best` trades), a mean daily
    return on max loss (`mean`: one for all, or by year), and per-year rows whose `roots` say which roots had data."""
    r = result(name, roots=roots, status=status)
    trades, by_year = [], {}
    for y in years:
        extra = (best or {}).get(y, ())
        mine = year_trades(y, n, pnl, best=extra)
        trades += mine
        row = {"trades": n, "days": 252, "days_traded": days, "pnl": round(sum(t["pnl"] for t in mine), 2), "t_daily": 2.0,
               "mean_return_on_max_loss_daily": mean.get(y) if isinstance(mean, dict) else mean, "quarters_positive": "4/4",
               "quarter_pnl": {f"{y}Q{q}": 10.0 for q in range(1, 5)}, "roots": list(roots)}
        row.update((rows or {}).get(y, {}))
        by_year[y] = row
    r.update(by_year=by_year, trades=trades)
    r["summary"]["pnl"] = round(sum(t["pnl"] for t in trades), 2)
    return r


class Own(unittest.TestCase):
    def test_a_clean_result_passes(self):
        out = killtests.own(train(), first_year=2022)
        self.assertEqual((out["passed"], out["why_not"]), (True, None))
        self.assertEqual(set(out["tests"]), {killtests.COVERAGE, killtests.TOP_TRADES})

    def test_coverage_counts_every_year_its_roots_had_data_where_the_train_score_skips_one(self):
        partial = train(years=("2020", "2021", "2022", "2023", "2024"), roots=("SPY", "AAPL"),
                        rows={"2020": {"trades": 8, "days_traded": 6, "roots": ["SPY"]}, "2021": {"roots": ["SPY"]}})
        partial["needs"] = {"roots": ["SPY", "AAPL"]}
        score = evidence.train_score(partial, first_year=2020)
        self.assertTrue(score["eligible"], "the Train score skips 2020-21: AAPL had no data there")
        self.assertNotIn("2020", score["years"])
        out = killtests.own(partial, first_year=2020)
        self.assertFalse(out["passed"])
        self.assertTrue(out["why_not"].startswith("kill test coverage: its roots had data in 2020 and it made 8 trades on 6 "
                                                  "days there"), out["why_not"])
        dark = train(years=("2021", "2022", "2023", "2024"), rows={"2021": {"trades": 0, "days_traded": 0, "roots": []}})
        self.assertTrue(killtests.own(dark, first_year=2021)["passed"], "a year with no data for its roots is not covered")
        self.assertTrue(killtests.own(partial, first_year=2022)["passed"], "years before the running span are not Train")

    def test_each_year_must_stay_positive_without_its_five_best_trades(self):
        lucky = train(pnl=-1.0, best={"2023": (90.0, 80.0, 70.0, 60.0, 50.0)})
        out = killtests.own(lucky, first_year=2022)
        self.assertEqual(out["tests"][killtests.COVERAGE], {"ok": True})
        self.assertTrue(out["why_not"].startswith("kill test top_trades: 2022 is not positive without its 5 best trades"),
                        out["why_not"])
        self.assertFalse(killtests.own({**train(), "trades": []}, first_year=2022)["passed"], "no trade list: not checkable")


class Against(unittest.TestCase):
    def figs(self, **kw):
        return killtests.figures(train(**kw), first_year=2022)

    def test_the_placebo_must_be_beaten_every_year_and_earn_less_in_all(self):
        signal = self.figs(mean=0.02, pnl=6.0)
        self.assertTrue(killtests.against(signal, self.figs(mean=0.01, pnl=5.0), years=YEARS)["passed"])
        one_year = self.figs(mean={"2022": 0.01, "2023": 0.03, "2024": 0.01}, pnl=5.0)
        out = killtests.against(signal, one_year, years=YEARS)
        self.assertTrue(out["why_not"].startswith("kill test placebo: in 2023 its mean daily return on maximum loss 0.02 does "
                                                  "not beat its placebo's 0.03"), out["why_not"])
        richer = self.figs(mean=0.01, pnl=9.0)
        out = killtests.against(signal, richer, years=YEARS)
        self.assertEqual(out["tests"][killtests.PLACEBO], {"ok": True})
        self.assertTrue(out["why_not"].startswith("kill test ablation: its Train P&L 1080.0 is not above"), out["why_not"])
        silent = {"by_year": {}, "pnl": 0.0}
        self.assertTrue(killtests.against(signal, silent, years=YEARS)["passed"], "a placebo with no trade earned nothing")

    def test_a_flat_cards_baseline_is_zero(self):
        self.assertTrue(killtests.against(self.figs(mean=0.01), None, years=YEARS)["passed"])
        out = killtests.against(self.figs(mean={"2022": 0.01, "2023": -0.002, "2024": 0.01}), None, years=YEARS)
        self.assertIn("in 2023", out["why_not"])
        self.assertIn("zero (a flat card's comparison is not trading)", out["why_not"])
        self.assertFalse(killtests.against(self.figs(pnl=-1.0, mean=0.01), None, years=YEARS)["tests"][killtests.ABLATION]["ok"])

    def test_the_placebo_params_are_the_cards_ablation(self):
        card = {"ablation": {"param": "signal_on", "off": 0}}
        self.assertEqual(killtests.placebo_params(card, {"vrp_min": 1.3}), {"vrp_min": 1.3, "signal_on": 0})
        self.assertIsNone(killtests.placebo_params({"ablation": {"flat": True}}, {}))
        self.assertIsNone(killtests.placebo_params(None, {}))
        self.assertFalse(killtests.enabled({"researcher": {"kill_tests": "yes"}}), "only JSON true")


CARD = {"hypothesis": "Index option sellers are paid for bearing variance risk: implied volatility sits above the variance "
                      "that follows, and a condor collects the gap on calm sessions.",
        "mechanism_class": "volatility_risk_premium", "inputs": ["implied_vol", "realized_vol"], "holding": "days_4_10",
        "cost": {"hurdle": 0.1, "why": "four half-spreads and fees on a narrow condor"},
        "comparison": "the same condor opened every session at the same minute without the rich-volatility condition",
        "falsification": "the signal's entries do not beat the comparison's in every Train year"}


class Researchers(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.settings["researcher"]["kill_tests"] = True
        self.settings["researcher"]["mechanism_test"] = False
        self.answer = lambda job: train(job.name, roots=job.roots, mean=0.02, pnl=6.0)
        self.pool = QueueingPool(lambda job: self.answer(job))
        self.fid = self.fam["id"]

    def carded(self, card=CARD) -> None:
        valid, errors = cards.validate(card, "iron_condor")
        self.assertEqual(errors, [])
        cards.put(self.store, self.fid, valid, "iron_condor")

    def placebo_jobs(self):
        return [j for j in self.pool.queued if j.params.get("signal_on") == 0]

    def test_an_eligible_run_that_fails_its_own_tests_is_not_eligible_and_says_which(self):
        self.answer = lambda job: train(job.name, roots=job.roots, pnl=-1.0, best={"2022": (90.0,) * 5})
        self.researcher().cycle(self.fid)
        fam = self.store.family(self.fid)
        self.assertIsNone(fam["state"].get("best_train_version"), "never the family's best")
        [row] = [r for r in self.store.runs(self.fid, window="train") if r.get("purpose") == "train"]
        self.assertFalse(row["summary"]["train_eligible"])
        self.assertTrue(row["summary"]["train_why"].startswith("kill test top_trades: 2022"), row["summary"]["train_why"])
        self.assertEqual(self.pool.queued, [], "nothing to make robust")
        self.settings["researcher"]["kill_tests"] = False
        self.assertTrue(self.researcher()._robust_of(train(pnl=-1.0, best={"2022": (90.0,) * 5}))["eligible"], "off: as before")

    def test_a_carded_best_runs_its_placebo_and_passes_when_it_beats_it(self):
        self.carded()
        researcher = self.researcher()
        researcher.cycle(self.fid)
        [job] = self.placebo_jobs()
        self.assertEqual((job.version, job.window, job.stress, job.purpose), (1, "train", 1.0, "robustness"))
        labels = [j.params.get("signal_on") for j in self.pool.queued]
        self.assertEqual(len(self.pool.queued), 3, "1.5x, the mid and the placebo")
        self.assertEqual(labels.count(0), 1)
        fam = self.store.family(self.fid)
        self.assertIsNone(kill_tests_passed(self.store, fam, 1, self.settings), "owed: the tournament waits")
        self.assertIn("placebo run", researcher.status(fam))
        trials = fam["trials"]
        job.late(train("placebo", mean=0.01, pnl=5.0))
        fam = self.store.family(self.fid)
        self.assertEqual(fam["trials"], trials + 1, "the placebo run is a trial")
        row = fam["state"]["robustness"]["1"][killtests.LABEL]
        self.assertEqual((row["status"], row["kill"]["passed"]), ("ok", True))
        self.assertIs(kill_tests_passed(self.store, fam, 1, self.settings), True)
        [stored] = self.store.runs(self.fid, window=killtests.LABEL)
        self.assertEqual((stored["purpose"], stored["version"]), (killtests.LABEL, 1))
        self.assertNotIn("eval_key", stored["summary"], "never read back as the version's own run")
        self.assertEqual(fam["state"]["best_train_version"], 1)
        self.assertEqual(len(self.placebo_jobs()), 1, "once a version")
        researcher.ensure_robustness(fam)
        self.assertEqual(len(self.placebo_jobs()), 1)

    def test_the_incubator_does_not_mark_a_version_whose_placebo_is_owed(self):
        from league.swarm import incubator

        self.carded()
        self.researcher().cycle(self.fid)
        [stressed] = [j for j in self.pool.queued if j.stress == evidence.STRESS]
        stressed.late(train("hot", pnl=4.0))
        fam = self.store.family(self.fid)
        mark, why, drop = incubator.mark_of(self.store, fam, 1, self.settings, evaluator={}, objective=None)
        self.assertEqual((mark, why, drop), (None, "its placebo kill tests are owed", False))

    def test_a_version_its_placebo_beats_is_demoted_with_the_named_test(self):
        self.carded()
        self.researcher().cycle(self.fid)
        [job] = self.placebo_jobs()
        job.late(train("placebo", mean={"2022": 0.01, "2023": 0.05, "2024": 0.01}, pnl=5.0))
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["robust_failed"], [1])
        self.assertTrue(fam["state"]["robust_why"]["1"].startswith("kill test placebo: in 2023"), fam["state"]["robust_why"])
        self.assertIs(kill_tests_passed(self.store, fam, 1, self.settings), False)
        self.assertIsNone(fam["state"]["best_train_version"])

    def test_a_placebo_the_program_cannot_run_is_a_verdict_not_a_retry(self):
        self.carded()
        self.researcher().cycle(self.fid)
        [job] = self.placebo_jobs()
        job.late({**train("placebo"), "status": "disqualified", "reason": "the program raised with its signal off"})
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["robust_failed"], [1])
        self.assertIn("ended disqualified", fam["state"]["robust_why"]["1"])
        self.assertEqual(fam["state"]["robustness"]["1"]["failures"], {}, "no attempt spent: the program answered")

    def test_a_flat_card_is_judged_at_once_against_zero(self):
        self.carded({**CARD, "ablation": {"flat": True}})
        self.researcher().cycle(self.fid)
        self.assertEqual(self.placebo_jobs(), [])
        self.assertEqual(len(self.pool.queued), 2, "no placebo run")
        fam = self.store.family(self.fid)
        row = fam["state"]["robustness"]["1"][killtests.LABEL]
        self.assertEqual((row["flat"], row["kill"]["passed"]), (True, True))
        self.assertIs(kill_tests_passed(self.store, fam, 1, self.settings), True)

    def test_a_flat_card_that_loses_a_year_is_demoted(self):
        self.carded({**CARD, "ablation": {"flat": True}})
        self.answer = lambda job: train(job.name, roots=job.roots, mean={"2022": 0.01, "2023": -0.01, "2024": 0.01}, pnl=6.0)
        self.researcher().cycle(self.fid)
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["robust_failed"], [1])
        self.assertIn("zero (a flat card's comparison is not trading)", fam["state"]["robust_why"]["1"])

    def test_off_or_uncarded_nothing_changes(self):
        self.researcher().cycle(self.fid)  # kill tests on, no card: no placebo and nothing to wait for
        self.assertEqual(self.placebo_jobs(), [])
        self.assertIs(kill_tests_passed(self.store, self.store.family(self.fid), 1, self.settings), True)
        self.carded()
        off = copy.deepcopy(self.settings)
        off["researcher"]["kill_tests"] = False
        self.assertIs(kill_tests_passed(self.store, self.store.family(self.fid), 1, off), True)
        self.assertIn(killtests.LABEL, self.researcher().robust_labels(self.store.family(self.fid), 1))
        plain = Researcher(self.store, self.router, self.pool, off, clock=self.clock, background=False)
        self.assertNotIn(killtests.LABEL, plain.robust_labels(self.store.family(self.fid), 1))


if __name__ == "__main__":
    unittest.main()
