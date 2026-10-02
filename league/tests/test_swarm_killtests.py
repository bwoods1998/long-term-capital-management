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


def year_trades(year: str, n: int, pnl: float, *, best: tuple[float, ...] = (), shape=None) -> list[dict]:
    rows = [{"day": f"{year}-03-{(i % 28) + 1:02d}", "pnl": pnl, "max_loss": 60.0} for i in range(n - len(best))]
    rows += [{"day": f"{year}-06-{i + 1:02d}", "pnl": b, "max_loss": 60.0} for i, b in enumerate(best)]
    return [{**t, **(shape or {})} for t in rows]


def train(name: str = "p", *, years=YEARS, n: int = 60, days: int = 30, pnl: float = 5.0, mean=0.01, best=None, rows=None,
          roots=("SPY",), status: str = "ok", shape=None) -> dict:
    """An invented Train result: each year `n` trades on `days` days of `pnl` each (and a year's `best` trades), a mean daily
    return on max loss (`mean`: one for all, or by year), and per-year rows whose `roots` say which roots had data.
    `shape`: fields every trade carries (its type, `context.dte`, ...: the trade profile the placebo audit reads)."""
    r = result(name, roots=roots, status=status)
    trades, by_year = [], {}
    for y in years:
        extra = (best or {}).get(y, ())
        mine = year_trades(y, n, pnl, best=extra, shape=shape)
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

    def test_coverage_reads_the_train_scores_years(self):
        """Review of B23: coverage counted a 2020-21 year when ANY root had data, so a mixed-root program (SPY plus a name
        whose chains start in 2022: dispersion's constituents, a name leader) that cannot compute its signal before 2022
        failed coverage on Train 2020-2024 for ever. It reads the Train score's years: a pre-2022 year only when every root
        the program needs had data."""
        mixed = train(years=("2020", "2021", "2022", "2023", "2024"), roots=("SPY", "AAPL"),
                      rows={"2020": {"trades": 0, "days_traded": 0, "roots": ["SPY"]},
                            "2021": {"trades": 0, "days_traded": 0, "roots": ["SPY"]}})
        mixed["trades"] = [t for t in mixed["trades"] if t["day"] >= "2022"]
        mixed["needs"] = {"roots": ["SPY", "AAPL"]}
        score = evidence.train_score(mixed, first_year=2020)
        self.assertTrue(score["eligible"], "the Train score skips 2020-21: AAPL had no data there")
        self.assertEqual(list(killtests.covered(mixed, first_year=2020)), ["2022", "2023", "2024"])
        self.assertTrue(killtests.own(mixed, first_year=2020)["passed"], "no Train year it could trade is short")
        solo = train(years=("2020", "2021", "2022", "2023", "2024"),
                     rows={"2020": {"trades": 8, "days_traded": 6, "roots": ["SPY"]}})
        out = killtests.own(solo, first_year=2020)
        self.assertTrue(out["why_not"].startswith("kill test coverage: its roots had data in 2020 and it made 8 trades on 6 "
                                                  "days there"), out["why_not"])
        both = train(years=("2020", "2021", "2022", "2023", "2024"), roots=("SPY", "AAPL"),
                     rows={"2021": {"trades": 3, "days_traded": 3, "roots": ["SPY", "AAPL"]}})
        self.assertIn("in 2021", killtests.own(both, first_year=2020)["why_not"], "every root had data: the year counts")
        dark = train(years=("2021", "2022", "2023", "2024"), rows={"2021": {"trades": 0, "days_traded": 0, "roots": []}})
        self.assertTrue(killtests.own(dark, first_year=2021)["passed"], "a year with no data for its roots is not covered")
        self.assertTrue(killtests.own(solo, first_year=2022)["passed"], "years before the running span are not Train")

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

    def test_a_placebo_that_makes_no_trade_is_no_comparison(self):
        """Review of B23: an ablation that turns the program off (`if not signal_on: return []`) made the placebo test
        'mean above zero' and the ablation test 'P&L above zero'. A placebo must trade in every covered year the version
        traded in."""
        signal = self.figs(mean=0.02, pnl=6.0)
        silent = {"by_year": {}, "pnl": 0.0}
        out = killtests.against(signal, silent, years=YEARS)
        self.assertFalse(out["passed"])
        self.assertTrue(out["why_not"].startswith("kill test placebo: in 2022 its placebo made no trade"), out["why_not"])
        gap = self.figs(mean=0.01, pnl=5.0)
        gap["by_year"]["2024"] = {"mean": None, "pnl": 0.0, "trades": 0}
        self.assertIn("in 2024 its placebo made no trade", killtests.against(signal, gap, years=YEARS)["why_not"])

    def test_a_placebo_on_another_structure_tenor_or_strike_is_no_comparison(self):
        """Review of B23: the researcher writes the off arm, so it could enter deliberately badly; the trade profiles must
        match (`mechanism.audit`, as the pre-birth mechanism test audits its ablation)."""
        fly = {"type": "long_butterfly", "context": {"dte": 2, "moneyness": 0.0}, "entry_minute": 600, "sessions_held": 1}
        mine = killtests.profile(train(shape=fly))
        same = killtests.profile(train(shape={**fly, "context": {"dte": 1, "moneyness": 0.005}}))
        far = killtests.profile(train(shape={**fly, "context": {"dte": 25, "moneyness": 0.0}}))
        wide = killtests.profile(train(shape={**fly, "context": {"dte": 2, "moneyness": -0.08}}))
        other = killtests.profile(train(shape={**fly, "type": "iron_condor"}))
        self.assertIsNone(killtests.comparison(mine, same, {}))
        self.assertIn("days to expiry 25", killtests.comparison(mine, far, {}))
        self.assertIn("moneyness", killtests.comparison(mine, wide, {}))
        self.assertIn("never traded the signal's structure (long_butterfly", killtests.comparison(mine, other, {}))
        self.assertIsNone(killtests.comparison(None, far, {}), "no trade list: nothing to audit")
        signal = self.figs(mean=0.02, pnl=6.0)
        out = killtests.against(signal, self.figs(mean=0.01, pnl=5.0), years=YEARS,
                                mismatch=killtests.comparison(mine, far, {}))
        self.assertTrue(out["why_not"].startswith("kill test placebo: its placebo is not the signal's comparison: its median "
                                                  "days to expiry 25"), out["why_not"])
        self.assertTrue(killtests.against(signal, None, years=YEARS, mismatch="ignored")["passed"], "a flat card: no run")

    def test_the_placebo_is_kept_small_under_its_own_run_id(self):
        full = train("placebo")
        small = killtests.compact(full)
        self.assertNotIn("trades", small)
        self.assertNotIn("daily", small)
        self.assertEqual(small["by_year"], evidence.years_of(full))
        self.assertEqual(killtests.figures(small, first_year=2022)["by_year"], killtests.figures(full, first_year=2022)["by_year"])
        self.assertEqual(killtests.scoped_id("abc"), "abc-placebo")
        self.assertIsNone(killtests.scoped_id(None))

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
        self.assertEqual((mark, why, drop), (None, "its Train kill tests are owed", False))

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

    def test_the_placebo_row_is_small_and_never_answers_a_train_run(self):
        """Review of B23: placebo results were stored whole under a window the store never prunes (tens of MB a day), and
        under the Gym's run_id, which a Train run of the same program and params shares (add_run then answered the Train
        run with the placebo's row)."""
        self.carded()
        self.researcher().cycle(self.fid)
        [job] = self.placebo_jobs()
        job.late({**train("placebo", mean=0.01, pnl=5.0), "run_id": "gym-shared"})
        [stored] = self.store.runs(self.fid, window=killtests.LABEL)
        self.assertEqual(stored["run_id"], "gym-shared-placebo")
        kept = self.store.run_result(stored["run_id"])
        self.assertNotIn("trades", kept)
        self.assertNotIn("daily", kept)
        self.assertIn("2023", kept["by_year"])
        fam = self.store.family(self.fid)
        self.assertIs(kill_tests_passed(self.store, fam, 1, self.settings), True)
        again = self.store.add_run(self.fid, 2, {**train("again"), "run_id": "gym-shared"}, window="train", stress=1.0,
                                   purpose="train")
        self.assertEqual((again["window"], again["version"]), ("train", 2), "a Train row of its own, never the placebo's")

    def test_a_placebo_that_makes_no_trade_demotes_the_version(self):
        self.carded()
        self.researcher().cycle(self.fid)
        [job] = self.placebo_jobs()
        job.late(train("placebo", n=0, mean=None, pnl=0.0))
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["robust_failed"], [1])
        self.assertIn("its placebo made no trade", fam["state"]["robust_why"]["1"])

    def test_a_placebo_on_another_tenor_demotes_the_version(self):
        shape = {"type": "iron_condor", "context": {"dte": 7, "moneyness": 0.0}, "entry_minute": 600, "sessions_held": 3}
        self.answer = lambda job: train(job.name, roots=job.roots, mean=0.02, pnl=6.0, shape=shape)
        self.carded()
        self.researcher().cycle(self.fid)
        [job] = self.placebo_jobs()
        job.late(train("placebo", mean=0.001, pnl=1.0, shape={**shape, "context": {"dte": 40, "moneyness": 0.0}}))
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["robust_failed"], [1])
        self.assertIn("is not the signal's comparison: its median days to expiry 40", fam["state"]["robust_why"]["1"])

    def test_the_placebo_tests_never_need_the_versions_full_result_again(self):
        """Review of B23: a version whose own Train result was pruned before its placebo landed failed the tests ('run it
        again', which NO DUPLICATE RUNS answers from the store). Its "own" row keeps what they read."""
        self.carded()
        researcher = self.researcher()
        researcher.cycle(self.fid)
        own = self.store.family(self.fid)["state"]["robustness"]["1"][killtests.OWN]
        self.assertEqual(set(own), {"status", "kill", "figures", "years", "profile"})
        self.assertTrue(own["kill"]["passed"])
        self.store._exec("UPDATE runs SET path=NULL WHERE family=?", (self.fid,))
        self.assertIsNone(researcher.version_result(self.store.family(self.fid), 1))
        [job] = self.placebo_jobs()
        job.late(train("placebo", mean=0.01, pnl=5.0))
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"].get("robust_failed") or [], [])
        self.assertIs(kill_tests_passed(self.store, fam, 1, self.settings), True)

    def test_an_own_row_without_figures_and_no_result_is_run_again_not_failed(self):
        self.carded()
        researcher = self.researcher()
        researcher.cycle(self.fid)
        rows = dict(self.store.family(self.fid)["state"]["robustness"])
        rows["1"] = {**rows["1"], killtests.OWN: {"status": "ok", "kill": {"passed": True}}}
        self.store.set_state(self.fid, robustness=rows)
        self.store._exec("UPDATE runs SET path=NULL WHERE family=?", (self.fid,))
        [job] = self.placebo_jobs()
        job.late(train("placebo", mean=0.01, pnl=5.0))
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"].get("robust_failed") or [], [], "owed, never failed, over a storage matter")
        self.assertIsNone(kill_tests_passed(self.store, fam, 1, self.settings))
        before = len(self.pool.queued)
        researcher.ensure_robustness(fam)
        [rerun] = self.pool.queued[before:]
        self.assertEqual((rerun.stress, rerun.params.get("signal_on")), (1.0, None))
        rerun.late(train(rerun.name, roots=rerun.roots, mean=0.02, pnl=6.0))
        fam = self.store.family(self.fid)
        self.assertTrue(fam["state"]["robustness"]["1"][killtests.LABEL]["kill"]["passed"])
        self.assertIs(kill_tests_passed(self.store, fam, 1, self.settings), True)

    def lucky_best_before_the_switch(self):
        """A best chosen with the kill tests off: eligible under the Train score, lives on five trades of 2022."""
        self.settings["researcher"]["kill_tests"] = False
        self.answer = lambda job: train(job.name, roots=job.roots, pnl=-1.0, best={"2022": (90.0,) * 5})
        self.researcher().cycle(self.fid)
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["best_train_version"], 1)
        [row] = [r for r in self.store.runs(self.fid, window="train") if r.get("purpose") == "train"]
        self.assertTrue(row["summary"]["train_eligible"])
        self.assertNotIn("train_kill", row["summary"])
        self.settings["researcher"]["kill_tests"] = True
        return fam, row

    def test_a_best_chosen_before_the_switch_is_held_to_the_tests(self):
        """Review of B23: a stored row's `train_eligible` was trusted and the tournament only asked for the placebo, so the
        living population's bests (chosen before the switch) and any older eligible row a researcher submitted skipped the
        tests."""
        fam, row = self.lucky_best_before_the_switch()
        researcher = self.researcher()
        self.assertIsNone(kill_tests_passed(self.store, fam, 1, self.settings), "owed: the tournament waits")
        ok, why = researcher.eligible_run(fam, row)
        self.assertFalse(ok)
        self.assertTrue(why.startswith("kill test top_trades: 2022"), why)
        researcher.ensure_robustness(fam)
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["robust_failed"], [1])
        self.assertTrue(fam["state"]["robust_why"]["1"].startswith("kill test top_trades"), fam["state"]["robust_why"])
        self.assertIs(kill_tests_passed(self.store, fam, 1, self.settings), False)

    def test_a_pruned_best_from_before_the_switch_is_run_again_and_scored(self):
        fam, row = self.lucky_best_before_the_switch()
        self.store._exec("UPDATE runs SET path=NULL WHERE family=?", (self.fid,))
        researcher = self.researcher()
        ok, why = researcher.eligible_run(fam, row)
        self.assertFalse(ok)
        self.assertIn("scored before the Train kill tests", why)
        self.assertIsNone(researcher._reusable(self.store.run(row["run_id"]), stress=1.0), "asked again, it runs again")
        before = len(self.pool.queued)
        researcher.ensure_robustness(fam)
        [own] = [j for j in self.pool.queued[before:] if j.stress == 1.0]
        own.late({**train(own.name, roots=own.roots, pnl=-1.0, best={"2022": (90.0,) * 5}), "run_id": row["run_id"]})
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["robust_failed"], [1])
        self.assertIs(kill_tests_passed(self.store, fam, 1, self.settings), False)
        rescored = self.store.run(row["run_id"])["summary"]
        self.assertEqual((rescored["train_eligible"], rescored["train_kill"]), (False, False), "its row says so now")

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
