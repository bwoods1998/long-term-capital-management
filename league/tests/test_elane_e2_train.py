"""Release E2, THE EQUITY TRAIN (league/swarm/elane_train.py): the bar equity-v1 on the Train window only, the record, the
minimal equity researcher (write, score, revise, refute) through E1's isolated runner, the version E1's tournament
validates, and the equity Train map. E1's runner, switch and card admission are fakes as INTERFACES fixes them
(league/tests/elane_e2_fakes.py). Every family, program and number here is invented."""

from __future__ import annotations

import json
import unittest

from league.swarm import elane_train
from league.swarm.elane_train import (BAR, OBJECTIVE, TRAIN_FIRST, TRAIN_LAST, EquityResearcher, awaiting_validation,
                                      closed_cells, record_of, train_map, train_map_text, train_score)
from league.tests import elane_e2_fakes as fx


class TheBar(unittest.TestCase):
    def score(self, base=None, stress=None):
        return train_score(base if base is not None else fx.train_result(k=1.0, pnl=180.0),
                           stress if stress is not None else fx.train_result(k=1.5, pnl=120.0))

    def test_a_version_active_in_every_year_with_a_cost_robust_profit_passes(self):
        s = self.score()
        self.assertTrue(s["passed"], s["why"])
        self.assertEqual(s["objective"], OBJECTIVE)
        self.assertEqual(s["active_years"], 9)
        self.assertEqual(s["fails"], [])
        self.assertAlmostEqual(s["beside"]["drift_share"], 50.0 / 180.0, places=4)  # beside, never a bar

    def test_y1_fewer_than_three_active_years(self):
        thin = fx.year_rows(trades=10, override={"2018": {"trades": 45, "days_traded": 25},
                                                 "2019": {"trades": 45, "days_traded": 25}})
        s = self.score(fx.train_result(by_year=thin))
        self.assertEqual(s["fails"], ["Y1"])
        self.assertEqual(s["active_years"], 2)
        rows = fx.year_rows(trades=10, override={y: {"trades": 45, "days_traded": 25} for y in ("2017", "2018", "2019")})
        self.assertTrue(self.score(fx.train_result(by_year=rows))["passed"], "three active years are enough")
        few_days = fx.year_rows(days=BAR["year_min_days"] - 1)
        self.assertIn("Y1", self.score(fx.train_result(by_year=few_days))["fails"], "40 lots on too few entry days")

    def test_y2_any_year_below_the_t_floor_and_a_flat_year_reads_zero(self):
        bad = fx.year_rows(override={"2022": {"t_daily": -1.2}})
        self.assertEqual(self.score(fx.train_result(by_year=bad))["fails"], ["Y2"])
        edge = fx.year_rows(override={"2022": {"t_daily": -1.0}})
        self.assertTrue(self.score(fx.train_result(by_year=edge))["passed"], "-1.0 itself is not below the floor")
        flat = fx.year_rows(override={"2020": {"t_daily": None, "trades": 0, "days_traded": 0}})
        self.assertTrue(self.score(fx.train_result(by_year=flat))["passed"])

    def test_p1_and_r1_at_the_stress(self):
        self.assertEqual(self.score(stress=fx.train_result(k=1.5, pnl=0.0))["fails"], ["P1", "R1"])
        self.assertEqual(self.score(stress=fx.train_result(k=1.5, pnl=80.0))["fails"], ["R1"], "under half the 1.0x P&L")
        self.assertTrue(self.score(stress=fx.train_result(k=1.5, pnl=90.0))["passed"], "exactly half passes")
        self.assertIn("R1", self.score(base=fx.train_result(pnl=-5.0), stress=fx.train_result(k=1.5, pnl=1.0))["fails"])

    def test_a_result_outside_train_is_refused_whole_and_shows_no_figure(self):
        leaked = fx.year_rows(years=range(2016, 2026))
        s = self.score(fx.train_result(by_year=leaked))
        self.assertEqual(s["fails"], ["WINDOW"])
        self.assertEqual((s["years"], s["pnl_10"], s["summary"]), ({}, None, {}))
        self.assertEqual(self.score(fx.train_result(end="2025-03-31"))["fails"], ["WINDOW"])
        self.assertEqual(self.score(stress=fx.train_result(k=1.5, start="2015-06-01"))["fails"], ["WINDOW"])

    def test_a_run_that_did_not_complete(self):
        self.assertEqual(self.score(fx.train_result(status="error"))["fails"], ["RUN"])

    def test_the_bar_text_names_rules_only(self):
        text = elane_train.bar_text()
        self.assertIn("2016-2024", text)
        self.assertIn("ONE Validation try", text)
        self.assertNotRegex(text, r"\b20(25|26)\b")


class ResearchCase(unittest.TestCase):
    def setUp(self):
        fx.switch_on(self)
        self.clock = fx.Clock()
        self.store = fx.new_store(self, self.clock)
        self.settings = fx.settings(train_budget=3, train_per_round=5)
        self.answers: list = []
        self.router = fx.FakeRouter(lambda call: self.answers.pop(0) if self.answers else fx.answer([]))
        self.results = {}
        self.runner = fx.FakeRunner(lambda code, k: self.results.get((code, k)) or fx.train_result(
            k=k, pnl=180.0 if k == 1.0 else 120.0))
        self.researcher = EquityResearcher(self.store, self.router, self.settings, runner=self.runner, clock=self.clock)

    def failing(self, code: str) -> None:
        self.results[(code, 1.0)] = fx.train_result(pnl=50.0)
        self.results[(code, 1.5)] = fx.train_result(k=1.5, pnl=-10.0)

    def program_answer(self, code: str, note: str = "a revision") -> dict:
        return {"text": json.dumps({"program": code, "note": note}), "json": {"program": code, "note": note},
                "route": "sail", "model": "pro_asap", "cost_usd": 0.05}


class TheResearcher(ResearchCase):
    def test_a_passing_first_version_awaits_validation_and_research_ends(self):
        fam = fx.e2_family(self.store, "overnight-spy", code=fx.program())
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["passed"], True)
        self.assertEqual([(c["k"], c["start"], c["end"]) for c in self.runner.calls],
                         [(1.0, TRAIN_FIRST, TRAIN_LAST), (1.5, TRAIN_FIRST, TRAIN_LAST)], "Train only, both stresses")
        fam = self.store.family(fam["id"])
        self.assertEqual((fam["best_version"], record_of(fam)["status"], record_of(fam)["passed_version"]), (1, "passed", 1))
        self.assertEqual(awaiting_validation(fam), 1)
        self.assertEqual(self.researcher.queue(), [], "a passing family researches no more")
        runs = self.store.runs(fam["id"], window="train")
        self.assertEqual(sorted(r["stress"] for r in runs), [1.0, 1.5])
        self.store.update_family(fam["id"], validated_version=1)
        self.assertIsNone(awaiting_validation(self.store.family(fam["id"])), "validated once")
        self.assertEqual(self.router.calls, [], "the architect's program needed no model call")

    def test_a_failed_version_is_revised_on_its_birth_route_and_the_revision_passes(self):
        first = fx.program(share=0.4)
        self.failing(first)
        fam = fx.e2_family(self.store, "rev-spy", code=first, route="sail:glm_asap")
        self.researcher.run()
        self.assertEqual(record_of(self.store.family(fam["id"]))["versions"]["1"]["fails"], ["P1", "R1"])
        self.answers.append(self.program_answer(fx.program(share=0.3)))
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["version"], 2)
        self.assertTrue(out["steps"][0]["score"]["passed"])
        call = self.router.calls[0]
        self.assertEqual((call["sail_profile"], call["claude"], call["openai_model"]), ("glm_asap", False, None))
        self.assertIn("YOUR VERSIONS ON TRAIN", call["user"])
        self.assertIn("v1: failed P1, R1", call["user"])
        self.assertIn("NEEDS", call["system"], "the contract rides in the system prompt")
        self.assertEqual(self.store.family(fam["id"])["best_version"], 2)

    def test_a_spent_budget_refutes_on_train_with_a_train_only_lesson(self):
        codes = [fx.program(share=s) for s in (0.41, 0.42, 0.43)]
        for code in codes:
            self.failing(code)
        fam = fx.e2_family(self.store, "dead-spy", code=codes[0])
        self.researcher.run()
        for code in codes[1:]:
            self.answers.append(self.program_answer(code))
            self.researcher.run()
        fam = self.store.family(fam["id"])
        rec = record_of(fam)
        self.assertEqual(rec["status"], "refuted")
        self.assertEqual(rec["refuted"]["codes"], ["P1", "R1"])
        self.assertIsNotNone(fam["retired_at"])
        lesson = self.store._one("SELECT lesson FROM graveyard WHERE family=?", (fam["id"],))["lesson"]
        self.assertTrue(lesson.startswith("REFUTED on Train"))
        self.assertNotRegex(lesson, r"[Vv]alidation|holdout|look|\b202[56]\b")
        self.assertEqual([r["id"] for r in elane_train.refuted_rows(self.store)], [fam["id"]])

    def test_a_refused_program_is_recorded_and_never_stored(self):
        fam = fx.e2_family(self.store, "bad-code")
        self.answers.append(self.program_answer("import os\n" + fx.program()))
        out = self.researcher.run()
        self.assertIn("refused by the code rules", out["steps"][0]["refused"])
        self.assertIsNone(self.store.latest_version(fam["id"]))
        self.answers.append(self.program_answer(fx.program("QQQ")))
        out = self.researcher.run()
        self.assertIn("outside the family's symbols", out["steps"][0]["refused"])
        rec = record_of(self.store.family(fam["id"]))
        self.assertEqual(rec["attempts"], 2)
        self.assertIn("PROGRAMS REFUSED BEFORE THEY RAN", self.researcher.brief(self.store.family(fam["id"])))

    def test_a_researcher_that_stops_refutes_the_family(self):
        fam = fx.e2_family(self.store, "stopper")
        self.answers.append({"text": '{"stop": "the effect does not survive the spread on Train"}',
                             "json": {"stop": "the effect does not survive the spread on Train"}, "route": "sail",
                             "model": "pro_asap", "cost_usd": 0.01})
        self.researcher.run()
        self.assertEqual(record_of(self.store.family(fam["id"]))["status"], "refuted")

    def test_a_run_error_is_retried_then_read_as_run(self):
        code = fx.program(share=0.33)
        self.results[(code, 1.0)] = RuntimeError("child died")
        fam = fx.e2_family(self.store, "flaky", code=code)
        for _ in range(elane_train.DEFAULTS["train_max_errors"] - 1):
            out = self.researcher.run()
            self.assertIn("error", out["steps"][0])
            self.assertEqual(record_of(self.store.family(fam["id"]))["versions"], {})
        self.researcher.run()
        self.assertEqual(record_of(self.store.family(fam["id"]))["versions"]["1"]["fails"], ["RUN"])

    def test_a_result_outside_train_is_never_stored(self):
        code = fx.program(share=0.31)
        self.results[(code, 1.0)] = fx.train_result(by_year=fx.year_rows(years=range(2016, 2027)))
        fam = fx.e2_family(self.store, "leaky", code=code)
        self.researcher.run()
        self.assertEqual(record_of(self.store.family(fam["id"]))["versions"]["1"]["fails"], ["WINDOW"])
        self.assertEqual(self.store.runs(fam["id"], window="train"), [])

    def test_the_lanes_off_and_the_seeds_untouched(self):
        seed = self.store.add_family({"id": "seed-overnight-spy", "mechanism": "The captain's seed: overnight on SPY.",
                                      "structure": "etf", "roots": ["SPY"], "lane": "beta"}, origin="seed")
        self.assertEqual(self.researcher.queue(), [], "E2 never researches a family it did not bear")
        self.assertIsNone(awaiting_validation(seed))
        off = EquityResearcher(self.store, self.router, {"elane": {"mode": "off"}}, runner=self.runner, clock=self.clock)
        self.assertFalse(off.due())
        self.assertIn("skipped", off.run())

    def test_a_family_retired_elsewhere_is_closed(self):
        fam = fx.e2_family(self.store, "elsewhere", code=fx.program())
        self.store.retire(fam["id"], "the operator")
        out = self.researcher.run()
        self.assertEqual(out["closed"], [fam["id"]])
        self.assertEqual(record_of(self.store.family(fam["id"]))["status"], "closed")


class TheMap(ResearchCase):
    def test_cells_count_births_passes_refutations_and_close(self):
        fx.e2_family(self.store, "a", record={"status": "passed", "passed_version": 1,
                                              "versions": {"1": {"passed": True, "score": 2.04, "fails": []}}})
        for i in range(3):
            fx.e2_family(self.store, f"r{i}", lane="equity", agenda="trend", symbols=("XLK", "XLF"),
                         record={"status": "refuted", "versions": {"1": {"passed": False, "fails": ["Y2"]}},
                                 "refuted": {"at": f"2026-10-1{i}T00:00:00Z", "codes": ["Y2"], "versions": 1, "why": "x"}})
        rows = {r["cell"]: r for r in train_map(self.store)}
        self.assertEqual(rows[("beta", "overnight", "index")]["passed"], 1)
        self.assertEqual(rows[("equity", "trend", "sectors")]["refuted"], 3)
        self.assertEqual(closed_cells(self.store, self.settings), [("equity", "trend", "sectors")])
        text = train_map_text(self.store, self.settings)
        self.assertIn("in-sample", text)
        self.assertIn("beta / overnight / index: births 1, scored 1, passed 1 (best t 2.0)", text)
        self.assertIn("CLOSED", text)


if __name__ == "__main__":
    unittest.main()
