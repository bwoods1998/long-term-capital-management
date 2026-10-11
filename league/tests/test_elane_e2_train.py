"""Release E2, THE EQUITY TRAIN (league/swarm/elane_train.py): the bar equity-v1 on the Train years only (2016-19 and
2022-24, one run a span, summed; 2020-21 refused as 2025-26 is), its restart check (STATE: the resets off the span's
start, what a match is, the size two buys may differ by), the record, the minimal equity researcher (write, score, review,
revise, refute, stall) through E1's isolated runner, what a verdict is (the program's own doing, never the House's, whose
failures are counted by kind), the equity review at the first pass, the guard E1's tournament applies (`may_validate`),
the identity a pass is judged under, and the equity Train map. E1's runner, decider kinds, switch and card admission are
fakes as INTERFACES fixes them (league/tests/elane_e2_fakes.py). Every family, program and number here is invented."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from league.swarm import elane_review, elane_train, elane_yield
from league.swarm.elane_train import (BAR, OBJECTIVE, RESERVE_YEARS, TRAIN_FIRST, TRAIN_LABEL, TRAIN_LAST, TRAIN_SPANS,
                                      TRAIN_YEARS, EquityResearcher, closed_cells, combine, may_validate, outside_years,
                                      record_of, restart_check, same_intents, train_map, train_map_text, train_score)
from league.swarm.gate import run_sha
from league.tests import elane_e2_fakes as fx

#: The reviewer's program (finding 1 of the E2 evidence review): it buys only while SPY sits in a band of absolute levels,
#: which does nothing on Train and encodes a remembered later market.
LEVEL_BAND = '''import math

NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}
PARAMS = {"lo": 1234.5, "hi": 1357.9, "share": 0.5}


def decide(ctx):
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
    px = ctx.prices["SPY"]
    if ctx.params["lo"] < px < ctx.params["hi"]:
        out.append({"buy": "SPY", "share": ctx.params["share"], "at": "close"})
    return out
'''


class TheBar(unittest.TestCase):
    def score(self, base=None, stress=None):
        return train_score(base if base is not None else fx.train_result(k=1.0, pnl=180.0),
                           stress if stress is not None else fx.train_result(k=1.5, pnl=120.0))

    def test_a_version_active_in_every_year_with_a_cost_robust_profit_passes(self):
        s = self.score()
        self.assertTrue(s["passed"], s["why"])
        self.assertEqual(s["objective"], OBJECTIVE)
        self.assertEqual(s["active_years"], 7, "the seven Train years: 2016-19 and 2022-24")
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
        flat = fx.year_rows(override={"2023": {"t_daily": None, "trades": 0, "days_traded": 0}})
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

    def test_the_reserve_years_are_refused_whole_as_a_later_year_is(self):
        self.assertEqual((TRAIN_YEARS, RESERVE_YEARS), ((2016, 2017, 2018, 2019, 2022, 2023, 2024), (2020, 2021)))
        for first, last in TRAIN_SPANS:
            self.assertTrue(TRAIN_FIRST <= first <= last <= TRAIN_LAST, "inside E1's Train window")
            self.assertFalse(set(range(first.year, last.year + 1)) & set(RESERVE_YEARS))
        for year in ("2020", "2021", "2025"):
            leaked = fx.year_rows(years=(*fx.TRAIN_YEARS, int(year)))
            s = self.score(fx.train_result(by_year=leaked))
            self.assertEqual(s["fails"], ["WINDOW"], year)
            self.assertEqual((s["years"], s["pnl_10"], s["summary"]), ({}, None, {}), "no figure of it")
        # Any row of a reserve day: a daily row, a trade's exit, a lot's entry, an entry day, a booked dividend, a
        # by-year row of the buy-and-hold or the exposure, the run's own start or end.
        clean = fx.train_result()
        for row in ({"daily": [*clean["daily"], ["2021-06-15", 4.0, 1000.0, 0.3]]},
                    {"trades": [{"id": 1, "day": "2019-12-30", "entry_day": "2019-12-30", "exit_day": "2020-01-02"}]},
                    {"lots": [{"lid": 1, "entry_day": "2021-12-31", "exit_day": "2022-01-04"}]},
                    {"actions": [{"symbol": "SPY", "day": "2020-03-20", "kind": "dividend"}]},
                    {"bh": {"pnl": 50.0, "by_year": {"2019": 6.0, "2020": 7.0}}},
                    {"exposure": {"mean": 0.3, "by_year": {"2021": 0.3}}},
                    {"entry_days": ["2018-05-01", "2021-03-01"]}, {"end": "2020-06-30"}, {"start": "2021-01-04"}):
            s = self.score(fx.train_result() | row)
            self.assertEqual((s["fails"], s["years"], s["pnl_10"]), (["WINDOW"], {}, None), row)
        inside = {"bh": {"pnl": 50.0, "by_year": {"2019": 6.0}}, "exposure": {"mean": 0.3, "by_year": {"2022": 0.3}},
                  "actions": [{"symbol": "SPY", "day": "2019-03-15", "kind": "dividend"}],
                  "lots": [{"lid": 1, "entry_day": "2019-12-30", "exit_day": None}]}
        self.assertTrue(self.score(fx.train_result() | inside)["passed"], "rows of Train days are no leak")
        self.assertEqual(outside_years(clean), [])
        # A span's run is held to its own span: a 2022 row in the 2016-2019 run is outside it.
        first = fx.span_result(clean, *TRAIN_SPANS[0])
        self.assertEqual(outside_years(first, spans=[TRAIN_SPANS[0]]), [])
        self.assertIn("2022", outside_years({**first, "by_year": {**first["by_year"], "2022": {}}}, spans=[TRAIN_SPANS[0]]))

    def test_the_two_spans_are_summed(self):
        whole = fx.train_result(pnl=180.0)
        parts = [fx.span_result(whole, *span) for span in TRAIN_SPANS]
        self.assertEqual([sorted(p["by_year"]) for p in parts], [["2016", "2017", "2018", "2019"], ["2022", "2023", "2024"]])
        summed = combine(parts)
        self.assertEqual(summed["status"], "ok")
        self.assertEqual(sorted(summed["by_year"]), [str(y) for y in TRAIN_YEARS])
        self.assertAlmostEqual(summed["summary"]["pnl"], 180.0, places=2)
        self.assertEqual(summed["summary"]["trades"], 7 * 60)
        self.assertAlmostEqual(summed["bh"]["pnl"], 50.0, places=2)
        pooled = elane_train._daily_t([row[1] for row in whole["daily"]])
        self.assertEqual(summed["summary"]["t_daily"], pooled, "the t of both spans' daily rows together")
        self.assertEqual(outside_years(summed), [])
        # Without daily rows the t is pooled from each run's mean and t (the same samples give the same t).
        xs = [row[1] for row in whole["daily"]]
        halves = [xs[:16], xs[16:]]
        no_daily = [{"status": "ok", "summary": {"days": len(h), "mean_pnl_daily": sum(h) / len(h),
                                                 "t_daily": elane_train._daily_t(h)}} for h in halves]
        self.assertAlmostEqual(combine(no_daily)["summary"]["t_daily"], pooled, places=2)
        self.assertEqual(combine([parts[0], {**parts[1], "status": "disqualified", "reason": "errors"}])["status"],
                         "disqualified")

    def test_the_bar_text_names_rules_only(self):
        text = elane_train.bar_text()
        self.assertIn(TRAIN_LABEL, text)
        self.assertEqual(TRAIN_LABEL, "Train years 2016-19 and 2022-24")
        self.assertIn("3 of the 7 Train years", text)
        self.assertIn("(STATE) run again with its STATE emptied every 20 sessions", text)
        self.assertIn("at least 99% of the sessions", text)
        # What a match is, and the two ways a sound-looking program fails it (told before the first version is written).
        self.assertIn("each buy the same size to six places of its share", text)
        self.assertIn("a decide must work on an empty STATE at any session, lots held or not", text)
        self.assertIn("Never carry a value from session to session and update it in place", text)
        self.assertIn("recompute it from ctx.bars at every call", text)
        system = " ".join(elane_train.RESEARCHER_SYSTEM.split())
        self.assertIn("a decide that raises after a restart is no match", system)
        self.assertIn("recompute it from ctx.bars at every call", system)
        self.assertEqual((BAR["state_every"], BAR["state_first"]), (20, 7))
        self.assertEqual(elane_train.SIZE_TOL, {"share": 1e-06, "usd": 0.01})
        self.assertIn("ONE Validation try", text)
        self.assertNotRegex(text, r"\b20(20|21|25|26)\b")
        self.assertIn(TRAIN_LABEL, elane_train.MAP_LABEL)
        self.assertIn(f"Train runs ({TRAIN_LABEL})", " ".join(elane_train.RESEARCHER_SYSTEM.split()))
        self.assertIn(f"STATE emptied every {BAR['state_every']} sessions", " ".join(elane_train.RESEARCHER_SYSTEM.split()))
        self.assertIn(f"{BAR['state_match']:.0%} of sessions", " ".join(elane_train.RESEARCHER_SYSTEM.split()))


class ResearchCase(unittest.TestCase):
    def setUp(self):
        fx.switch_on(self)
        self.clock = fx.Clock()
        self.store = fx.new_store(self, self.clock)
        self.settings = fx.settings(train_budget=3, train_per_round=5)
        self.answers: list = []
        self.reviews: list = []
        self.router = fx.FakeRouter(self.script)
        self.results = {}
        self.runner = fx.FakeRunner(lambda code, k: self.results.get((code, k)) or fx.train_result(
            k=k, pnl=180.0 if k == 1.0 else 120.0))
        self.researcher = EquityResearcher(self.store, self.router, self.settings, runner=self.runner, clock=self.clock)

    def script(self, call):
        if fx.is_review(call):
            return self.reviews.pop(0) if self.reviews else fx.review_answer("pass", model=call["sail_profile"])
        return self.answers.pop(0) if self.answers else fx.answer([])

    def failing(self, code: str) -> None:
        self.results[(code, 1.0)] = fx.train_result(pnl=50.0)
        self.results[(code, 1.5)] = fx.train_result(k=1.5, pnl=-10.0)

    def program_answer(self, code: str, note: str = "a revision") -> dict:
        return {"text": json.dumps({"program": code, "note": note}), "json": {"program": code, "note": note},
                "route": "sail", "model": "pro_asap", "cost_usd": 0.05}

    def rec(self, fid: str) -> dict:
        return record_of(self.store.family(fid))

    def writes(self) -> list:
        return [c for c in self.router.calls if not fx.is_review(c)]


class TheResearcher(ResearchCase):
    def test_a_passing_first_version_is_reviewed_then_is_the_try(self):
        fam = fx.e2_family(self.store, "overnight-spy", code=fx.program())
        out = self.researcher.run()
        self.assertEqual((out["steps"][0]["passed"], out["steps"][0]["review"]["review"]), (True, "pass"))
        self.assertEqual([(c["k"], c["start"], c["end"]) for c in self.runner.calls],
                         [(k, *span) for k in (1.0, 1.5) for span in TRAIN_SPANS],
                         "the Train spans only (never 2020-21), one run a span, both stresses")
        fam = self.store.family(fam["id"])
        self.assertEqual((fam["best_version"], record_of(fam)["status"], record_of(fam)["passed_version"]), (1, "passed", 1))
        self.assertEqual(self.researcher.queue(), [], "a passing family researches no more")
        runs = self.store.runs(fam["id"], window="train")
        self.assertEqual(sorted(r["stress"] for r in runs), [1.0, 1.0, 1.5, 1.5])
        state = record_of(fam)["versions"]["1"]["state"]
        self.assertEqual((state["sessions"], state["matched"], state["every"]),
                         (2 * fx.STATE_SESSIONS, 2 * fx.STATE_SESSIONS, BAR["state_every"]), "the restart check held")
        self.assertEqual(self.writes(), [], "the architect's program needed no model call")
        # THE REVIEW: two readers on two different models, before the pass is the try; E1's `reviewed` shape.
        readers = [c["sail_profile"] for c in self.router.calls if fx.is_review(c)]
        self.assertEqual(readers, ["pro_balanced", "k3_balanced"])
        state = fam["state"]["review"]
        self.assertEqual((state["sha"], state["verdict"], state["audit"]["verdict"]),
                         (run_sha(self.store.version(fam["id"], 1)), "pass", "pass"))
        self.assertTrue(elane_review.holds(fam["state"], run_sha(self.store.version(fam["id"], 1))))
        self.assertIn("review:sail:pro_balanced", elane_yield.ledger(self.store)["routes"], "booked on its own row")
        # THE GUARD (patch 5): only the pass, and still the pass once validated (a stale Validation is validated again).
        self.assertTrue(may_validate(self.store, fam, 1))
        self.assertFalse(may_validate(self.store, fam, 2))
        self.assertFalse(may_validate(self.store, fam, None))
        self.store.update_family(fam["id"], validated_version=1)
        self.assertTrue(may_validate(self.store, self.store.family(fam["id"]), 1),
                        "E1's next_try re-validates a stale verdict: the guard never blocks it")

    def test_a_new_family_with_no_pass_is_never_validated(self):
        fam = fx.e2_family(self.store, "fresh", code=fx.program())
        self.assertFalse(may_validate(self.store, fam, 1), "E1's next_try would offer v1: the guard refuses it")
        seed = self.store.add_family({"id": "seed-overnight-spy", "mechanism": "The captain's seed: overnight on SPY.",
                                      "structure": "etf", "roots": ["SPY"], "lane": "beta"}, origin="seed")
        self.assertTrue(may_validate(self.store, seed, 1), "a family E2 did not bear is E1's alone")

    def test_the_level_band_program_is_refused_before_it_runs(self):
        self.assertIsNotNone(elane_train.check_code(LEVEL_BAND, ["SPY"]))
        fam = fx.e2_family(self.store, "band")
        self.answers.append(self.program_answer(LEVEL_BAND))
        out = self.researcher.run()
        self.assertIn("equity level rule", out["steps"][0]["refused"])
        self.assertIsNone(self.store.latest_version(fam["id"]), "never stored")
        self.assertEqual(self.runner.calls, [], "never run")
        self.assertIn("equity level rule", self.researcher.brief(self.store.family(fam["id"])))

    def test_a_stored_level_program_fails_the_review_without_a_paid_call(self):
        fam = fx.e2_family(self.store, "stored-band", code=LEVEL_BAND)
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["review"]["fails"], ["REVIEW"])
        self.assertEqual([c for c in self.router.calls if fx.is_review(c)], [], "the level rule needs no model")
        rec = self.rec(fam["id"])
        self.assertIsNone(rec.get("passed_version"))
        self.assertFalse(may_validate(self.store, self.store.family(fam["id"]), 1))

    def test_a_failed_review_is_a_train_failure_and_spends_no_try(self):
        code = fx.program(share=0.45)
        fam = fx.e2_family(self.store, "reviewed-out", code=code)
        self.reviews.append(fx.review_answer("fail", excerpt='ctx.params["share"]', reference="calendar",
                                             reasons=("an invented calendar reconstruction",)))
        out = self.researcher.run()
        self.assertEqual((out["steps"][0]["review"]["fails"], out["steps"][0]["review"]["stage"]), (["REVIEW"], "review"))
        rec = self.rec(fam["id"])
        self.assertEqual((rec["versions"]["1"]["fails"], rec["versions"]["1"]["bar_passed"], rec["status"]),
                         (["REVIEW"], True, "researching"))
        self.assertIsNone(self.store.family(fam["id"])["best_version"])
        self.assertFalse(may_validate(self.store, self.store.family(fam["id"]), 1))
        self.answers.append(self.program_answer(fx.program(share=0.35)))
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["version"], 2)
        self.assertIn("EQUITY REVIEW refused it", self.writes()[0]["user"])
        self.assertIn("an invented calendar reconstruction", self.writes()[0]["user"])
        self.assertEqual(self.rec(fam["id"])["passed_version"], 2)

    def test_an_ungrounded_failure_reads_unclear_and_three_unclear_reads_fail(self):
        fam = fx.e2_family(self.store, "unclear", code=fx.program(share=0.44))
        self.reviews.extend([fx.review_answer("fail", excerpt="not in the file at all"), fx.review_answer("maybe"),
                             fx.review_answer("unclear")])
        for reads in (1, 2):
            out = self.researcher.run()
            self.assertEqual(self.rec(fam["id"])["review"]["unclear"]["review"], reads)
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["fails"], ["REVIEW"])
        self.assertIn("stayed unclear", self.rec(fam["id"])["versions"]["1"]["review"]["reasons"][0])

    def test_the_audit_is_another_model(self):
        settings = fx.settings(train_budget=3, review_routes=["sail:pro_balanced", "sail:pro_asap", "sail:k3_balanced"])
        researcher = EquityResearcher(self.store, self.router, settings, runner=self.runner, clock=self.clock)
        fam = fx.e2_family(self.store, "two-readers", code=fx.program(share=0.43))
        researcher.run()
        readers = [c["sail_profile"] for c in self.router.calls if fx.is_review(c)]
        self.assertEqual(readers, ["pro_balanced", "k3_balanced"], "pro_asap is the reviewer's model: never its audit")
        self.assertEqual(self.rec(fam["id"])["passed_version"], 1)

    def test_no_reviewer_answering_counts_nothing(self):
        from league.swarm.models import ModelError

        fam = fx.e2_family(self.store, "quiet", code=fx.program(share=0.42))
        self.router.script = lambda call: ModelError("busy") if fx.is_review(call) else fx.answer([])
        out = self.researcher.run()
        self.assertIn("no review route answered", out["steps"][0]["review"]["error"])
        rec = self.rec(fam["id"])
        self.assertEqual((rec["review"]["version"], rec["review"].get("unclear")), (1, {}))
        self.router.script = self.script
        self.researcher.run()
        self.assertEqual(self.rec(fam["id"])["passed_version"], 1)

    def test_a_failed_version_is_revised_on_its_birth_route_and_the_revision_passes(self):
        first = fx.program(share=0.4)
        self.failing(first)
        fam = fx.e2_family(self.store, "rev-spy", code=first, route="sail:glm_asap")
        self.researcher.run()
        self.assertEqual(self.rec(fam["id"])["versions"]["1"]["fails"], ["P1", "R1"])
        self.answers.append(self.program_answer(fx.program(share=0.3)))
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["version"], 2)
        self.assertTrue(out["steps"][0]["score"]["passed"])
        call = self.writes()[0]
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
        self.assertEqual(self.rec(fam["id"])["attempts"], 2)
        self.assertIn("PROGRAMS REFUSED BEFORE THEY RAN", self.researcher.brief(self.store.family(fam["id"])))

    def test_a_stop_before_any_judged_version_is_not_accepted(self):
        fam = fx.e2_family(self.store, "stopper")
        stop = {"text": '{"stop": "the effect does not survive the spread"}',
                "json": {"stop": "the effect does not survive the spread"}, "route": "sail", "model": "pro_asap",
                "cost_usd": 0.01}
        self.answers.append(dict(stop))
        out = self.researcher.run()
        self.assertIn("a stop is accepted only once a version was judged", out["steps"][0]["refused"])
        self.assertEqual(self.rec(fam["id"])["status"], "researching")
        code = fx.program(share=0.39)
        self.failing(code)
        self.answers.extend([self.program_answer(code), dict(stop)])
        self.researcher.run()
        self.researcher.run()
        self.assertEqual(self.rec(fam["id"])["status"], "refuted", "after a judged version a stop refutes")

    def test_the_lanes_off_and_the_seeds_untouched(self):
        self.store.add_family({"id": "seed-overnight-spy", "mechanism": "The captain's seed: overnight on SPY.",
                               "structure": "etf", "roots": ["SPY"], "lane": "beta"}, origin="seed")
        self.assertEqual(self.researcher.queue(), [], "E2 never researches a family it did not bear")
        off = EquityResearcher(self.store, self.router, {"elane": {"mode": "off"}}, runner=self.runner, clock=self.clock)
        self.assertFalse(off.due())
        self.assertIn("skipped", off.run())

    def test_a_family_retired_elsewhere_is_closed(self):
        fam = fx.e2_family(self.store, "elsewhere", code=fx.program())
        self.store.retire(fam["id"], "the operator")
        out = self.researcher.run()
        self.assertEqual(out["closed"], [fam["id"]])
        self.assertEqual(self.rec(fam["id"])["status"], "closed")


class WhatAVerdictIs(ResearchCase):
    """Finding 2 of the E2 evidence review (and 8 of the adversarial one): the House's failures never judge a program."""

    def test_no_equity_store_scores_nothing_spends_nothing_and_closes_no_cell(self):
        missing = fx.MissingData("no equity store at /state/equity-daily (no VERSION file)")
        self.runner.answer = lambda code, k: missing
        fams = [fx.e2_family(self.store, f"fam-{i}", code=fx.program(share=0.5 + 0.01 * i),
                             mechanism=f"Invented mechanism number {i}: holders are paid for overnight index risk.")
                for i in range(3)]
        for _ in range(40):
            self.clock.advance(3600)
            self.researcher.run()
        for fam in fams:
            rec = self.rec(fam["id"])
            self.assertEqual((rec["status"], rec["versions"]), ("researching", {}))
            self.assertIsNone(self.store.family(fam["id"])["retired_at"])
            self.assertEqual(rec["infra"]["kind"], "store")
        self.assertEqual(self.router.calls, [], "no model is asked to rewrite a program that never ran")
        self.assertEqual(closed_cells(self.store, self.settings), [])
        self.assertEqual(elane_train.refuted_rows(self.store), [])
        self.runner.answer = lambda code, k: fx.train_result(k=k, pnl=180.0 if k == 1.0 else 120.0)
        self.clock.advance(elane_train.BACKOFF_MAX)
        self.researcher.run()
        self.assertEqual({self.rec(f["id"])["status"] for f in fams}, {"passed"}, "the store came: judged at last")

    def test_the_backoff_grows_and_waits(self):
        fam = fx.e2_family(self.store, "waits", code=fx.program(share=0.38))
        self.runner.answer = lambda code, k: fx.MissingData("no store")
        out = self.researcher.run()
        first = out["steps"][0]["retry_in"]
        self.assertEqual(self.researcher.queue(), [], "inside its backoff")
        self.clock.advance(first)
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["retry_in"], 2 * first)
        self.assertEqual(self.rec(fam["id"])["infra"]["count"], 2)

    def test_a_child_that_fails_one_program_while_others_run_judges_it_run(self):
        bad, good = fx.program(share=0.37), fx.program(share=0.36)
        self.results[(bad, 1.0)] = fx.RunFailed("the decider child failed the run: MemoryError")
        fam = fx.e2_family(self.store, "crasher", code=bad)
        for _ in range(elane_train.DEFAULTS["train_max_errors"] + 1):
            self.clock.advance(elane_train.BACKOFF_MAX)
            self.researcher.run()
        self.assertEqual(self.rec(fam["id"])["versions"], {}, "while no other program's run completes: the House's")
        fx.e2_family(self.store, "healthy", code=good, symbols=("QQQ",))
        self.clock.advance(elane_train.BACKOFF_MAX)
        self.researcher.run()
        self.assertEqual(self.rec(fam["id"])["versions"]["1"]["fails"], ["RUN"], "others ran: the program's fault")

    def test_disqualified_is_dq_and_a_refusal_is_load_and_neither_refutes(self):
        dq, refused = fx.program(share=0.34), fx.program(share=0.33)
        self.results[(dq, 1.0)] = fx.train_result(status="disqualified")
        self.results[(refused, 1.0)] = fx.ProgramRefused("the program does not load: NEEDS is malformed")
        a = fx.e2_family(self.store, "dq", code=dq)
        b = fx.e2_family(self.store, "load", code=refused, symbols=("QQQ",))
        self.researcher.run()
        self.assertEqual(self.rec(a["id"])["versions"]["1"]["fails"], ["DQ"])
        self.assertEqual(self.rec(b["id"])["versions"]["1"]["fails"], ["LOAD"])
        self.assertIn("v1: the program was disqualified", self.researcher.brief(self.store.family(a["id"])))

    def test_a_load_refusal_reaches_its_author_and_a_disqualifications_own_words_never_do(self):
        # The integration review's seal-6: the record dropped every verdict's reason, so an author whose program the
        # child refused to load ("NEEDS history 9999 is above the lane's 504 sessions") revised blind, each LOAD failure
        # spending one of its four Train versions. LOAD's text is the House's own (a program that did not load read no
        # market data). A disqualification's reason carries the program's own exception text, which can hold anything it
        # read (a bar of the reserve it sees as look-back): only counts and the error's class are kept.
        dq, refused, late = fx.program(share=0.34), fx.program(share=0.33), fx.program(share=0.32)
        leak = "25 errors (first: line 12: ValueError: SENTINEL close 412.55 volume 9876543 on the bar)"
        self.results[(dq, 1.0)] = {**fx.train_result(status="disqualified"), "reason": leak}
        self.results[(refused, 1.0)] = fx.ProgramRefused("NEEDS history 9999 is above the lane's 504 sessions")
        self.results[(late, 1.0)] = {**fx.train_result(status="disqualified"),
                                     "reason": "decide used 912 s, over the run's budget of 900 s"}
        a = fx.e2_family(self.store, "dq", code=dq)
        b = fx.e2_family(self.store, "load", code=refused, symbols=("QQQ",))
        c = fx.e2_family(self.store, "late", code=late, symbols=("IWM",))
        self.researcher.run()
        self.assertEqual(self.rec(b["id"])["versions"]["1"]["fails"], ["LOAD"])
        brief = self.researcher.brief(self.store.family(b["id"]))
        self.assertIn("v1: the decider child refused to load the program: NEEDS history 9999 is above the lane's 504 "
                      "sessions.", brief)
        kept = json.dumps(self.rec(a["id"]))
        brief = self.researcher.brief(self.store.family(a["id"]))
        for text in (kept, brief):
            for word in ("SENTINEL", "412.55", "9876543", "on the bar"):
                self.assertNotIn(word, text)
        self.assertIn("v1: the program was disqualified on Train by its own errors or timeouts: 25 errors in decide, the "
                      "first a ValueError at line 12.", brief)
        self.assertIn("its decides ran past the run's time budget", self.researcher.brief(self.store.family(c["id"])))

    def test_a_disqualification_names_counts_a_line_and_a_known_class_only(self):
        said = elane_train.dq_said
        self.assertEqual(said("25 errors (first: line 7: KeyError: 'XLK')"), "25 errors in decide, the first a KeyError at line 7")
        self.assertEqual(said("25 errors (first: line 7: Close412: 412.55)"), "25 errors in decide, the first at line 7")
        self.assertEqual(said("25 errors (first: 412.55: ValueError: x)"), "25 errors in decide, the first a ValueError")
        self.assertEqual(said("25 errors (first: decide ran past 1.00 s)"),
                         "25 errors in decide, the first a decide past its time limit")
        self.assertEqual(said("25 errors (first: 412.55 was the close)"), "25 errors in decide")
        self.assertEqual(said("an invented reason holding 412.55"), "its own errors or timeouts")
        self.assertEqual(said(None), "its own errors or timeouts")
        # A run the child kept failing (RUN): the failure's class, never its text.
        verdict = elane_train.program_fault("RUN", "RunFailed: stderr held 412.55", said="a RunFailed")
        kept = elane_train.compact(verdict, at="2026-10-10T00:00:00Z")
        self.assertNotIn("412.55", json.dumps(kept))
        self.assertTrue(kept["why"].endswith(": a RunFailed"))
        self.assertNotIn("why", elane_train.compact(elane_train.program_fault("DQ", "raw text 412.55"), at="x"))

    def test_a_family_with_no_judged_version_stalls_with_no_graveyard_row(self):
        settings = fx.settings(train_budget=2, train_per_round=5)
        researcher = EquityResearcher(self.store, self.router, settings, runner=self.runner, clock=self.clock)
        codes = [fx.program("XLK", share=s) for s in (0.31, 0.32)]
        for code in codes:
            self.results[(code, 1.0)] = fx.train_result(status="disqualified")
        fams = []
        for i in range(3):
            fams.append(fx.e2_family(self.store, f"st{i}", code=codes[0], lane="equity", agenda="trend",
                                     symbols=("XLK",), mechanism=f"Invented trend idea {i} on one sector."))
        for _ in range(2):
            self.answers.extend([self.program_answer(codes[1]) for _ in fams])
            researcher.run()
        for fam in fams:
            self.assertEqual(self.rec(fam["id"])["status"], "stalled")
            self.assertIsNotNone(self.store.family(fam["id"])["retired_at"])
        self.assertIsNone(self.store._one("SELECT 1 FROM graveyard WHERE family=?", (fams[0]["id"],)))
        self.assertEqual(closed_cells(self.store, settings), [], "a stall closes no cell")
        row = {r["cell"]: r for r in train_map(self.store)}[("equity", "trend", "sectors")]
        self.assertEqual((row["refuted"], row["stalled"]), (0, 3))

    def test_a_result_outside_train_is_never_scored_and_alerts(self):
        code = fx.program(share=0.31)
        self.results[(code, 1.0)] = fx.train_result(by_year=fx.year_rows(years=range(2016, 2027)))
        fam = fx.e2_family(self.store, "leaky", code=code)
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["house"], "window")
        self.assertEqual(self.rec(fam["id"])["versions"], {})
        self.assertEqual(self.store.runs(fam["id"], window="train"), [])
        alerts = [e for e in self.store.events_after(0) if e["kind"] == "swarm.status" and e["payload"].get("alert")]
        self.assertEqual(alerts[0]["payload"]["action"], "elane_train_window")


class TheHousesFailuresByKind(ResearchCase):
    """The A15 review's fifth finding: the House's failures of a version were one count for every kind, so a restart check
    the House interrupted (never the program's) counted toward the RUN verdict, and the restart check's alert fired only
    if the count landed on it. They are counted by kind (`EquityResearcher.house_failure`)."""

    def attempt(self, fid: str) -> dict:
        """One round, then the longest backoff: the family's step."""
        out = self.researcher.run()
        self.clock.advance(elane_train.BACKOFF_MAX)
        return next(s for s in out["steps"] if s.get("family") == fid)

    def judged_meanwhile(self, slug: str, symbol: str) -> None:
        """Another program the child judges through in the next round (it fails P1, so it needs no restart check)."""
        code = fx.program(symbol, share=0.2)
        self.failing(code)
        fx.e2_family(self.store, slug, code=code, symbols=(symbol,), mechanism=f"Invented idea {slug} on {symbol}.")

    def interrupt(self) -> None:
        """The child restarts ten decides into the next restart check (the House's "state")."""
        self.runner.decider.restart_after = self.runner.decider.decides + 10

    def fail_runs(self, code: str, exc: BaseException | None) -> None:
        """The version's Train runs fail with `exc` (None: they run again)."""
        if exc is None:
            self.results.pop((code, 1.0), None)
        else:
            self.results[(code, 1.0)] = exc

    def alerts(self) -> list:
        return [e["payload"]["action"] for e in self.store.events_after(0)
                if e["kind"] == "swarm.status" and e["payload"].get("alert")]

    def test_restart_check_interruptions_never_count_toward_run(self):
        """Two checks the House interrupted, another program judged meanwhile, then ONE failed run: three failures, one
        of them a run's. The version is not judged RUN on the strength of the House's interruptions."""
        code = fx.program(share=0.31)
        fam = fx.e2_family(self.store, "sound", code=code)
        fid = fam["id"]
        self.interrupt()
        self.assertEqual(self.attempt(fid)["house"], "state")
        self.judged_meanwhile("meanwhile-1", "QQQ")
        self.interrupt()
        self.assertEqual(self.attempt(fid)["house"], "state")
        self.fail_runs(code, fx.RunFailed("the decider child failed the run: timed out"))
        step = self.attempt(fid)
        self.assertEqual(step.get("house"), "run", f"one run failure is the House's: {step}")
        rec = self.rec(fid)
        infra = rec["infra"]
        self.assertEqual((rec["versions"], infra["count"], infra["kind"], infra["streak"], infra["kinds"]),
                         ({}, 3, "run", 1, {"state": 2, "run": 1}))
        # RUN is the child failing this version's runs `train_max_errors` times in a row while others are judged.
        self.judged_meanwhile("meanwhile-2", "IWM")
        self.assertEqual(self.attempt(fid).get("house"), "run")
        step = self.attempt(fid)
        self.assertEqual((step.get("passed"), step.get("fails")), (False, ["RUN"]), step)
        self.assertEqual(self.rec(fid)["versions"]["1"]["fails"], ["RUN"])

    def test_a_standing_pass_is_not_withdrawn_by_the_houses_interruptions_and_one_failed_run(self):
        ident = {"now": {"equity": "a" * 64, "engine": "equity-engine-1"}}
        patcher = mock.patch("league.swarm.evaluator.equity_identity", lambda: dict(ident["now"]))
        patcher.start()
        self.addCleanup(patcher.stop)
        code = fx.program(share=0.33)
        fam = fx.e2_family(self.store, "standing", code=code)
        fid = fam["id"]
        self.researcher.run()
        self.assertEqual(self.rec(fid)["passed_version"], 1)
        ident["now"] = {"equity": "b" * 64, "engine": "equity-engine-1"}  # the pass is stale: Train-scored again
        self.interrupt()
        self.assertEqual(self.attempt(fid)["house"], "state")
        self.judged_meanwhile("meanwhile", "QQQ")
        self.interrupt()
        self.assertEqual(self.attempt(fid)["house"], "state")
        self.fail_runs(code, fx.RunFailed("the decider child failed the run: timed out"))
        self.assertEqual(self.attempt(fid).get("house"), "run")
        rec = self.rec(fid)
        self.assertEqual((rec["status"], rec["passed_version"], rec["versions"]["1"]["passed"]), ("passed", 1, True),
                         "the pass stands (stale until it can be judged), never withdrawn as RUN")
        self.assertEqual(self.store.family(fid)["best_version"], 1)
        self.fail_runs(code, None)
        self.assertEqual(self.attempt(fid)["rescored"], "kept")
        self.assertNotIn("infra", self.rec(fid), "a completed judgment clears every count")

    def test_a_row_of_run_failures_broken_by_another_kind_starts_again(self):
        """"In a row": a store being rewritten, or a check the House interrupted (whose attempt ran the version's Train
        runs through), between the child's failures starts the row again, however many came before."""
        code = fx.program(share=0.3)
        fam = fx.e2_family(self.store, "broken-row", code=code)
        fid = fam["id"]
        failed = fx.RunFailed("the decider child failed the run: MemoryError")
        self.fail_runs(code, failed)
        self.assertEqual(self.attempt(fid)["house"], "run")
        self.judged_meanwhile("meanwhile-1", "QQQ")
        self.assertEqual(self.attempt(fid)["house"], "run")
        self.fail_runs(code, fx.MissingData("the equity store is being rewritten"))
        self.assertEqual(self.attempt(fid)["house"], "store")
        self.fail_runs(code, failed)
        step = self.attempt(fid)
        self.assertEqual(step.get("house"), "run", f"the third run failure, not three in a row: {step}")
        infra = self.rec(fid)["infra"]
        self.assertEqual((infra["count"], infra["streak"], infra["kinds"]), (4, 1, {"run": 3, "store": 1}))
        self.assertEqual(self.attempt(fid).get("house"), "run", "two in a row; no other program judged since the first")
        self.judged_meanwhile("meanwhile-2", "IWM")
        step = self.attempt(fid)
        self.assertEqual(step.get("fails"), ["RUN"], "three in a row, another program judged after the first of them")

    def test_the_backoff_doubles_with_every_failure_of_any_kind(self):
        code = fx.program(share=0.29)
        fam = fx.e2_family(self.store, "backoff", code=code)
        delays = []
        for exc in (fx.MissingData("no store"), fx.RunFailed("the child failed"), fx.MissingData("no store")):
            self.fail_runs(code, exc)
            delays.append(self.attempt(fam["id"])["retry_in"])
        self.assertEqual(delays, [delays[0], 2 * delays[0], 4 * delays[0]])

    def test_the_restart_checks_alert_counts_its_own_kind_and_is_sent_once(self):
        """state, state, store, state: the third restart check that could not finish is the alert, though it is the
        version's fourth failure; a fourth and a fifth send no second one; a judgment starts the count again."""
        code = fx.program(share=0.28)
        fam = fx.e2_family(self.store, "unfinished", code=code)
        fid = fam["id"]
        for _ in range(2):
            self.interrupt()
            self.assertEqual(self.attempt(fid)["house"], "state")
        self.assertEqual(self.alerts(), [], "two interruptions are no news")
        self.fail_runs(code, fx.MissingData("the equity store is being rewritten"))
        self.assertEqual(self.attempt(fid)["house"], "store")
        self.fail_runs(code, None)
        self.interrupt()
        self.assertEqual(self.attempt(fid)["house"], "state")
        self.assertEqual(self.alerts(), ["elane_train_state"], "its third unfinished check, whatever failed between")
        infra = self.rec(fid)["infra"]
        self.assertEqual((infra["count"], infra["kinds"], infra["alerted"]), (4, {"state": 3, "store": 1}, ["state"]))
        for _ in range(2):
            self.interrupt()
            self.assertEqual(self.attempt(fid)["house"], "state")
        self.assertEqual(self.alerts(), ["elane_train_state"], "sent once")
        self.attempt(fid)
        self.assertEqual(self.rec(fid)["passed_version"], 1, "judged once the check could finish")
        self.assertNotIn("infra", self.rec(fid))


class TheRestartCheck(ResearchCase):
    """A15: the Train bar's STATE check. The House's decider child restarts on every deploy and a restart empties a
    program's STATE, so a version is run again with its STATE emptied every 20 sessions and must give the uninterrupted
    run's intents on 99% of the sessions (E1's decider kinds faked in this process: a load is a fresh STATE)."""

    def test_a_stateless_program_passes(self):
        fam = fx.e2_family(self.store, "stateless", code=fx.program(share=0.26))
        out = self.researcher.run()
        self.assertEqual((out["steps"][0]["passed"], out["steps"][0]["review"]["review"]), (True, "pass"))
        state = self.rec(fam["id"])["versions"]["1"]["state"]
        self.assertEqual((state["sessions"], state["matched"], state["share"], state["first_miss"], state["disqualified"]),
                         (2 * fx.STATE_SESSIONS, 2 * fx.STATE_SESSIONS, 1.0, None, 0))
        self.assertEqual((state["every"], state["first"], state["failed"], state["sized"], state["size_gap"]),
                         (20, 7, 0, 0, {}))
        decider = self.runner.decider
        # Each span: A loaded once; B loaded with it, then fresh at sessions 7 and 27; every instance dropped at the end.
        self.assertEqual(decider.loads, [f"e2-state:{fam['id']}:{span}:{x}" for span in (0, 1)
                                         for x in ("a", "b0", "b1", "b2")])
        self.assertEqual(decider.instances, {})

    def test_the_resets_are_off_the_spans_start(self):
        """B is emptied `state_first` (7) sessions into a span and every `state_every` (20) after: never on the session
        A starts at, where a counter in either instance reads the same."""
        decider = fx.FakeDecider()
        seen: list[tuple[int, str]] = []
        real = decider.kind

        def kind(kind_, op, payload, **kw):
            seen.append((len(seen), payload["jobs"][1]["key"]))
            return real(kind_, op, payload, **kw)
        decider.kind = kind
        restart_check(decider, fx.program(), {}, name="p", streams=[fx.state_inputs(None, 70)])
        resets = [i for i, key in seen if i == 0 or key != seen[i - 1][1]]
        self.assertEqual(resets, [0, 7, 27, 47, 67])
        self.assertEqual(decider.loads, ["e2-state:p:0:a", *(f"e2-state:p:0:b{n}" for n in range(5))])

    def test_a_program_that_counts_sessions_in_state_fails_state(self):
        settings = fx.settings(train_budget=1, train_per_round=5)
        researcher = EquityResearcher(self.store, self.router, settings, runner=self.runner, clock=self.clock)
        fam = fx.e2_family(self.store, "counter", code=fx.COUNTER)
        out = researcher.run()
        self.assertEqual((out["steps"][0]["passed"], out["steps"][0]["fails"]), (False, ["STATE"]))
        self.assertEqual([c for c in self.router.calls if fx.is_review(c)], [], "no review of a failed version")
        rec = self.rec(fam["id"])
        v1 = rec["versions"]["1"]
        self.assertEqual((v1["fails"], v1["passed"]), (["STATE"], False))
        self.assertLess(v1["state"]["matched"], BAR["state_match"] * v1["state"]["sessions"])
        self.assertEqual(v1["state"]["first_miss"]["span"], 0)
        self.assertTrue(v1["years"], "its Train figures are kept for its brief")
        # STATE judges the program, not the mechanism: the spent budget stalls the family (no graveyard row, no cell).
        self.assertEqual(rec["status"], "stalled")
        self.assertIsNone(self.store._one("SELECT 1 FROM graveyard WHERE family=?", (fam["id"],)))
        self.assertEqual(elane_train.refuted_rows(self.store), [])
        text = elane_train.version_text(1, v1)
        self.assertIn("met Y1, Y2, P1 and R1 but failed STATE", text)
        self.assertIn("(STATE) run again with its STATE emptied every 20 sessions", text)
        self.assertIn(f"matched the uninterrupted run's on {v1['state']['matched']} of {v1['state']['sessions']}", text)

    def test_a_state_failure_is_told_and_a_revision_that_reads_ctx_passes(self):
        fam = fx.e2_family(self.store, "told", code=fx.COUNTER)
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["fails"], ["STATE"])
        self.assertEqual(self.rec(fam["id"])["status"], "researching", "a scored version of the budget, not the end")
        self.answers.append(self.program_answer(fx.CACHE, "holdings from ctx.positions, a cache in STATE"))
        out = self.researcher.run()
        brief = self.writes()[0]["user"]
        self.assertIn("v1: met Y1, Y2, P1 and R1 but failed STATE", brief)
        self.assertIn("Restart check: with STATE emptied every 20 sessions", brief)
        self.assertIn("they first differed on session 1 after a reset", brief)
        self.assertIn("none judged by the bar yet, so a stop is not accepted", brief, "STATE judges no mechanism")
        self.assertEqual((out["steps"][0]["version"], out["steps"][0]["score"]["passed"]), (2, True))
        rec = self.rec(fam["id"])
        self.assertEqual((rec["passed_version"], rec["versions"]["2"]["state"]["matched"]),
                         (2, rec["versions"]["2"]["state"]["sessions"]))

    def test_a_cache_of_values_recomputable_from_ctx_passes(self):
        fam = fx.e2_family(self.store, "cache", code=fx.CACHE)
        out = self.researcher.run()
        self.assertTrue(out["steps"][0]["passed"], out)
        state = self.rec(fam["id"])["versions"]["1"]["state"]
        self.assertEqual(state["matched"], state["sessions"])
        self.assertEqual(self.rec(fam["id"])["passed_version"], 1)

    def test_the_check_counts_every_session_of_both_spans(self):
        decider = fx.FakeDecider()

        def streams():
            return [fx.state_inputs(None), fx.state_inputs(None)]
        for code, held in ((fx.program(), True), (fx.CACHE, True), (fx.COUNTER, False)):
            out = restart_check(decider, code, {}, name="p", streams=streams())
            self.assertEqual((out["sessions"], out["held"], out["every"]), (2 * fx.STATE_SESSIONS, held, 20), code[:40])
        # The counter's clock is a multiple of 7 sessions. Its first reset comes 7 sessions in, where the two clocks still
        # agree; after the next (session 27) its buys come on other sessions: 27, 34 and 41 against 33 and 40.
        out = restart_check(decider, fx.COUNTER, {}, name="p", streams=streams())
        self.assertEqual(out["first_miss"], {"span": 0, "session": 27, "after_reset": 0})
        self.assertEqual(out["matched"], 2 * (fx.STATE_SESSIONS - 5))
        # Reset at every session, a program that only reads ctx still matches; a counter that never resets matches too.
        self.assertTrue(restart_check(decider, fx.CACHE, {}, name="p", streams=streams(), every=1)["held"])
        self.assertTrue(restart_check(decider, fx.COUNTER, {}, name="p", streams=streams(), every=1000, first=1000)["held"])
        self.assertEqual(decider.instances, {})

    def test_a_clock_whose_period_divides_the_reset_period_fails_state(self):
        """The A15 review's first finding: with B's resets counted from the span's first session, a session counter of
        period 2, 4, 5, 10 or 20 (a weekly clock) kept in phase with its reset twin and matched on every session. Live, a
        deploy restarts the clock at any session."""
        decider = fx.FakeDecider()
        sessions = 10 * BAR["state_every"]
        for period in (2, 4, 5, 10, 20, 3, 7, 21):
            out = restart_check(decider, fx.counter(period), {}, name="p", streams=[fx.state_inputs(None, sessions)])
            self.assertFalse(out["held"], (period, out))
            if BAR["state_every"] % period == 0:
                self.assertLess(out["matched"], 0.92 * sessions, f"a clock of {period} misses far more than 1%")
            # The schedule the review found: resets on the span's first session and every 20 after. Kept here as the
            # reason for `state_first`: the periods that divide 20 are blind to it.
            old = restart_check(decider, fx.counter(period), {}, name="p", streams=[fx.state_inputs(None, sessions)],
                                first=0)
            self.assertEqual(old["matched"] == sessions, BAR["state_every"] % period == 0, period)
        self.assertNotEqual(BAR["state_first"] % 2, 0)
        self.assertNotEqual(BAR["state_first"] % 5, 0, "7 shares no factor with 20")
        self.assertLess(BAR["state_first"], BAR["state_every"])

    def test_a_weekly_clock_in_state_fails_the_bar(self):
        settings = fx.settings(train_budget=1, train_per_round=5)
        researcher = EquityResearcher(self.store, self.router, settings, runner=self.runner, clock=self.clock)
        for period in (5, 10, 20):
            fam = fx.e2_family(self.store, f"clock-{period}", code=fx.counter(period),
                               mechanism=f"Invented clock idea of {period} sessions on the index.")
            out = researcher.score(fam, self.store.version(fam["id"], 1))
            self.assertEqual((out["passed"], out["fails"]), (False, ["STATE"]), period)
            rec = self.rec(fam["id"])
            self.assertIsNone(rec.get("passed_version"))
            self.assertFalse(may_validate(self.store, self.store.family(fam["id"]), 1), period)

    def test_a_decide_that_fails_once_state_is_emptied_is_no_match(self):
        """The A15 review's second finding: a decide that raises because STATE was emptied answers nothing, as the
        uninterrupted one often does, so comparing the intents alone passed it at 100%. Live, two failed decides in a row
        exit a program's lots (EQUITY.md)."""
        decider = fx.FakeDecider()
        out = restart_check(decider, fx.PEAK, {}, name="p", streams=[fx.state_inputs(None), fx.state_inputs(None)])
        # B is emptied at sessions 7 and 27 of each span, a lot held at both: its decide raises there, A's does not.
        self.assertEqual((out["sessions"], out["failed"], out["matched"], out["held"], out["disqualified"]),
                         (2 * fx.STATE_SESSIONS, 4, 2 * fx.STATE_SESSIONS - 4, False, 0))
        self.assertEqual(out["first_miss"], {"span": 0, "session": 7, "after_reset": 0})
        # What the intents alone say of those sessions: nothing differs (both answered no order).
        intents = restart_check(decider, fx.PEAK.replace('STATE["peak"] = max(STATE["peak"], px)',
                                                         'STATE["peak"] = max(STATE.get("peak", px), px)'),
                                {}, name="p", streams=[fx.state_inputs(None), fx.state_inputs(None)])
        self.assertEqual((intents["failed"], intents["matched"]), (0, 2 * fx.STATE_SESSIONS), "the same orders, no error")
        # Both decides failing alike is a match (the program fails the same with and without its memory).
        both = restart_check(decider, fx.RAISES, {}, name="p", streams=[fx.state_inputs(None, 10)])
        self.assertEqual((both["failed"], both["matched"], both["held"]), (0, 10, True))
        # Through the bar: STATE, told in the brief.
        fam = fx.e2_family(self.store, "peak", code=fx.PEAK)
        step = self.researcher.run()["steps"][0]
        self.assertEqual((step["passed"], step["fails"]), (False, ["STATE"]))
        v1 = self.rec(fam["id"])["versions"]["1"]
        self.assertEqual((v1["state"]["failed"], v1["state"]["matched"]), (4, 2 * fx.STATE_SESSIONS - 4))
        text = elane_train.version_text(1, v1)
        self.assertIn("on 4 sessions the decide failed (raised, timed out or returned a malformed intent) in one run and "
                      "not in the other (no match)", text)
        self.assertIn("a decide must work on an empty STATE at any session", text)
        self.assertFalse(may_validate(self.store, self.store.family(fam["id"]), 1))

    def test_an_answer_without_its_error_count_is_the_houses(self):
        """Without `stats.errors` a decide that failed cannot be told from one that answered nothing: never a pass."""
        fam = fx.e2_family(self.store, "uncounted", code=fx.program(share=0.17))
        self.runner.decider.counts_errors = False
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["house"], "state")
        self.assertIn("no error count (stats.errors)", out["steps"][0]["why"])
        self.assertEqual(self.rec(fam["id"])["versions"], {})
        self.runner.decider.counts_errors = True
        self.clock.advance(elane_train.BACKOFF_MAX)
        self.researcher.run()
        self.assertEqual(self.rec(fam["id"])["passed_version"], 1)

    def test_the_same_orders_within_a_size(self):
        buy = {"buy": "SPY", "share": 0.25, "at": "close", "tag": ""}
        sell = {"sell": 7, "at": "open", "tag": ""}
        self.assertEqual(same_intents([sell, buy], [dict(sell), dict(buy)]), (True, None))
        self.assertEqual(same_intents([], None), (True, None))
        # The last digits of a size are no memory; the seventh place is.
        self.assertEqual(same_intents([buy], [{**buy, "share": 0.25 + 2.5e-15}]), (True, None))
        self.assertEqual(same_intents([buy], [{**buy, "share": 0.25 + 9e-07}]), (True, None))
        same, gap = same_intents([sell, buy], [sell, {**buy, "share": 0.25004}])
        self.assertEqual((same, list(gap), round(gap["share"], 6)), (False, ["share"], 4e-05))
        usd = {"buy": "SPY", "usd": 100.0, "at": "open", "tag": ""}
        self.assertEqual(same_intents([usd], [{**usd, "usd": 100.004}]), (True, None))
        self.assertEqual(same_intents([usd], [{**usd, "usd": 100.5}])[0], False)
        # Anything else that differs is another order: no size gap is named.
        for other in ([buy], [buy, sell], [sell, {**buy, "buy": "QQQ"}], [sell, {**buy, "at": "open"}],
                      [sell, {**buy, "tag": "n=3"}], [{**sell, "sell": 8}, buy], [sell, usd],
                      [sell, {**buy, "share": 0.3, "at": "open"}], [{"cancel": 1}, buy]):
            self.assertEqual(same_intents([sell, buy], other), (False, None), other)

    def test_a_cache_updated_in_place_passes_on_rounding_alone(self):
        """The A15 review's third finding: a cache holding the value ctx gives, updated in place (the newest term added,
        the oldest dropped), differs from a fresh instance's in the last digits of a buy's size; compared exactly it
        failed STATE on rounding alone. (`fx.CACHE` rebuilds its value at every call: nothing cached is reused there.)"""
        decider = fx.FakeDecider()
        sessions = 10 * BAR["state_every"]
        out = restart_check(decider, fx.INPLACE, {}, name="p", streams=[fx.state_inputs(None, sessions)])
        self.assertEqual((out["matched"], out["held"], out["sized"], out["size_gap"]), (sessions, True, 0, {}))
        # The cache really is reused, and its sizes really differ: compared to the last digit it fails on many sessions.
        with mock.patch.dict(elane_train.SIZE_TOL, {"share": 0.0}):
            exact = restart_check(decider, fx.INPLACE, {}, name="p", streams=[fx.state_inputs(None, sessions)])
        self.assertFalse(exact["held"])
        self.assertGreater(exact["sized"], 0.25 * sessions)
        self.assertEqual(exact["sized"], sessions - exact["matched"], "sizes were all that differed")
        self.assertLess(exact["size_gap"]["share"], 1e-12, "in the last digits only")
        # Through the bar it passes, as its recomputing twin does.
        for slug, code in (("inplace", fx.INPLACE), ("recomputed", fx.RECOMPUTED)):
            fam = fx.e2_family(self.store, slug, code=code, mechanism=f"Invented volatility idea, {slug}.")
            self.researcher.run()
            rec = self.rec(fam["id"])
            self.assertEqual((rec.get("passed_version"), rec["versions"]["1"]["state"]["matched"]),
                             (1, 2 * fx.STATE_SESSIONS), slug)

    def test_a_value_carried_from_session_to_session_fails_state_and_is_told(self):
        """What is NOT a cache: a value that depends on how long ago the instance was loaded (a decayed running sum). Its
        orders are the same and only their sizes differ, far past the last digits: STATE, with the reason in the brief."""
        fam = fx.e2_family(self.store, "carried", code=fx.CARRIED)
        step = self.researcher.run()["steps"][0]
        self.assertEqual((step["passed"], step["fails"]), (False, ["STATE"]))
        state = self.rec(fam["id"])["versions"]["1"]["state"]
        self.assertGreater(state["sized"], 0)
        self.assertEqual(state["sized"], state["sessions"] - state["matched"], "the sizes are all that differed")
        self.assertGreater(state["size_gap"]["share"], 100 * elane_train.SIZE_TOL["share"])
        self.answers.append(self.program_answer(fx.RECOMPUTED, "the sum recomputed from ctx.bars at every call"))
        out = self.researcher.run()
        brief = self.writes()[0]["user"]
        self.assertIn(f"on {state['sized']} sessions the two runs gave the same orders and differed only in a buy's size "
                      f"(by at most {state['size_gap']['share']:.2g} of the sleeve)", brief)
        self.assertIn("recompute it from ctx.bars at every call", brief)
        self.assertEqual((out["steps"][0]["version"], out["steps"][0]["score"]["passed"]), (2, True))

    def test_the_check_runs_only_once_the_rest_of_the_bar_holds(self):
        code = fx.program(share=0.25)
        self.failing(code)
        fx.e2_family(self.store, "fails-p1", code=code)
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["fails"], ["P1", "R1"])
        self.assertEqual(self.runner.decider.decides, 0, "no restart check for a version the bar already failed")

    def test_a_child_that_restarts_during_the_check_is_the_houses(self):
        fam = fx.e2_family(self.store, "restarted", code=fx.program(share=0.24))
        self.runner.decider.restart_after = 10
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["house"], "state")
        self.assertIn("restarted during the restart check", out["steps"][0]["why"])
        rec = self.rec(fam["id"])
        self.assertEqual((rec["versions"], rec["infra"]["kind"]), ({}, "state"), "nothing scored, no budget spent")
        self.assertEqual(self.store.runs(fam["id"], window="train"), [], "no run stored for an unfinished verdict")
        self.assertEqual(self.runner.decider.instances, {}, "every instance dropped")
        self.assertFalse(may_validate(self.store, self.store.family(fam["id"]), 1), "no try without the check")
        self.assertEqual(self.alerts(), [], "one restart of the child is no news")
        self.clock.advance(elane_train.BACKOFF_MAX)
        self.researcher.run()
        self.assertEqual(self.rec(fam["id"])["passed_version"], 1, "judged once the check could finish")

    def alerts(self) -> list:
        return [e["payload"]["action"] for e in self.store.events_after(0)
                if e["kind"] == "swarm.status" and e["payload"].get("alert")]

    def test_an_instance_reloaded_without_a_counted_restart_is_caught(self):
        """E1's decider reloads its instances into a child that died between two requests without counting a restart:
        instance A then has fresh memory too, and a session counter would agree with its reset twin."""
        fam = fx.e2_family(self.store, "reloaded", code=fx.COUNTER)
        decider = self.runner.decider
        decider.reload_after = 2 * 25  # before the span's 26th session, eighteen sessions after B's reset
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["house"], "state")
        self.assertIn("reloaded an instance during the restart check", out["steps"][0]["why"])
        self.assertEqual((decider.restarts, self.rec(fam["id"])["versions"]), (0, {}), "uncounted, and still not scored")
        self.assertEqual(decider.instances, {})
        # Whatever the program: a stateless one's check stops too (the check never guesses what a reload cost).
        with self.assertRaises(elane_train.StateCheckInterrupted):
            decider.reload_after = decider.decides + 2 * 25
            restart_check(decider, fx.program(), {}, name="p", streams=[fx.state_inputs(None)])
        # A reload where every instance is fresh anyway (a span's first session) loses no memory: the check goes on.
        decider.reload_after = decider.decides
        self.assertTrue(restart_check(decider, fx.CACHE, {}, name="p", streams=[fx.state_inputs(None)])["held"])
        self.assertIsNone(decider.reload_after, "the reload happened")

    def test_a_decider_that_cannot_tell_a_reload_never_passes_and_alerts(self):
        """The safe degrade: without the call count in E1's decide answer the check cannot know its instances kept their
        memory, so the version is not scored (the House's), never passed; the third failure in a row is an alert."""
        fam = fx.e2_family(self.store, "untold", code=fx.program(share=0.22))
        self.runner.decider.counts = False
        for n in range(1, elane_train.DEFAULTS["train_max_errors"] + 2):
            out = self.researcher.run()
            self.assertEqual(out["steps"][0]["house"], "state", out)
            self.assertIn("no call count", out["steps"][0]["why"])
            self.assertEqual(self.alerts(), ["elane_train_state"] if n >= elane_train.DEFAULTS["train_max_errors"] else [])
            self.clock.advance(elane_train.BACKOFF_MAX)
        rec = self.rec(fam["id"])
        self.assertEqual((rec["status"], rec["versions"], rec.get("passed_version")), ("researching", {}, None))
        self.assertFalse(may_validate(self.store, self.store.family(fam["id"]), 1))
        self.assertEqual(self.writes(), [], "no model is asked to rewrite a program the House could not check")
        self.assertEqual(self.store.runs(fam["id"], window="train"), [])
        self.runner.decider.counts = True
        self.researcher.run()
        self.assertEqual(self.rec(fam["id"])["passed_version"], 1, "the count came back: judged")

    def test_no_decider_means_no_pass(self):
        fam = fx.e2_family(self.store, "no-decider", code=fx.program(share=0.23))
        self.runner.decider = None
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["house"], "state")
        self.assertIsNone(self.rec(fam["id"]).get("passed_version"), "no pass without its restart check")
        # A decider without E1's kinds at all (an AttributeError) is the House's too.
        self.runner.decider = object()
        self.clock.advance(elane_train.BACKOFF_MAX)
        out = self.researcher.run()
        self.assertEqual((out["steps"][0]["house"], self.rec(fam["id"])["versions"]), ("state", {}))

    def test_no_session_compared_is_no_pass(self):
        decider = fx.FakeDecider()
        for streams in ([], [iter(())], [fx.state_inputs(None), iter(())]):
            with self.assertRaises(elane_train.StateCheckInterrupted):
                restart_check(decider, fx.program(), {}, name="p", streams=streams)
            self.assertEqual(decider.instances, {})
        verdict = elane_train.with_state({"passed": True, "fails": []}, {"sessions": 0, "matched": 0, "held": True})
        self.assertEqual((verdict["passed"], verdict["fails"]), (False, ["STATE"]), "a check of nothing holds nothing")

    def test_a_disqualified_instance_matches_nothing(self):
        """A program that fails every decide answers nothing with and without its memory: two silent instances agree, and
        E1 disqualifies an instance at its `max_errors`-th error. Sessions an instance is disqualified at match nothing."""
        decider = fx.FakeDecider()
        with mock.patch.object(elane_train, "DECIDE_MAX_ERRORS", 3):
            out = restart_check(decider, fx.RAISES, {}, name="p", streams=[fx.state_inputs(None)])
        self.assertEqual((out["sessions"], out["matched"], out["disqualified"], out["held"]),
                         (fx.STATE_SESSIONS, 2, fx.STATE_SESSIONS - 2, False))
        self.assertEqual(out["first_miss"], {"span": 0, "session": 2, "after_reset": 2})
        text = elane_train.restart_text({"state": out})
        self.assertIn(f"on {fx.STATE_SESSIONS - 2} sessions an instance was disqualified by its own errors", text)

    def test_a_child_that_fails_the_check_is_run_only_once_other_programs_are_judged(self):
        """A child that fails the check's decides is judged as a run's failure: the House's, and RUN only once ANOTHER
        program's Train judgment completed after its first failure (its own Train runs, which complete before its check
        every time, prove nothing against its own check)."""
        fam = fx.e2_family(self.store, "check-crasher", code=fx.program(share=0.21))
        decider = self.runner.decider
        decider.fails = fx.DeciderError("the decider did not answer in time; the child was killed")
        tries = elane_train.DEFAULTS["train_max_errors"] + 2
        for i in range(tries):
            out = self.researcher.run()
            self.assertEqual(out["steps"][0]["house"], "run", out)
            if i < tries - 1:
                self.clock.advance(elane_train.BACKOFF_MAX)
        self.assertEqual(self.rec(fam["id"])["versions"], {}, "its own runs completing do not make it RUN")
        self.assertEqual(self.store.runs(fam["id"], window="train"), [])
        # While it waits out its backoff another program is judged through (it fails P1, so it needs no check), and a
        # second program meets the same failing child for the first time.
        other = fx.program("QQQ", share=0.2)
        self.failing(other)
        fx.e2_family(self.store, "judged-meanwhile", code=other, symbols=("QQQ",))
        second = fx.e2_family(self.store, "check-crasher-2", code=fx.program("IWM", share=0.18), symbols=("IWM",))
        self.researcher.run()
        self.assertEqual((self.rec(fam["id"])["versions"], self.rec(second["id"])["infra"]["kind"]), ({}, "run"))
        # The child judged another program after the first one's first failure: the fault is that program's own.
        self.clock.advance(elane_train.BACKOFF_MAX)
        self.researcher.run()
        v1 = self.rec(fam["id"])["versions"]["1"]
        self.assertEqual((v1["fails"], v1["passed"]), (["RUN"], False))
        self.assertNotIn("state", v1, "no restart check finished")
        # That RUN verdict is no judgment the child completed: the second program, which no other program's judgment
        # followed, stays the House's however often its check fails.
        for _ in range(tries):
            self.clock.advance(elane_train.BACKOFF_MAX)
            self.researcher.run()
        rec = self.rec(second["id"])
        self.assertEqual((rec["versions"], rec["infra"]["kind"]), ({}, "run"))
        self.assertGreater(rec["infra"]["count"], elane_train.DEFAULTS["train_max_errors"])


class TheIdentity(ResearchCase):
    """Finding 7 of the adversarial review: a Train pass judged under another equity identity."""

    def setUp(self):
        super().setUp()
        self.ident = {"equity": "a" * 64, "engine": "equity-engine-1"}
        patcher = mock.patch("league.swarm.evaluator.equity_identity", lambda: dict(self.ident))
        patcher.start()
        self.addCleanup(patcher.stop)

    def adopt(self, fid: str) -> None:
        """What E1's `evaluator.adopt_equity` does to an equity family (it clears `review` with the selection keys)."""
        self.ident = {"equity": "b" * 64, "engine": "equity-engine-1"}
        self.store.update_family(fid, best_version=None, validated_version=None)
        self.store.set_state(fid, review=None, gate_ready=False)

    def test_a_pass_under_another_identity_is_scored_again_before_validation(self):
        code = fx.program(share=0.29)
        fam = fx.e2_family(self.store, "moved", code=code)
        self.researcher.run()
        self.assertEqual(self.rec(fam["id"])["versions"]["1"]["identity"]["equity"], "a" * 64)
        self.adopt(fam["id"])
        self.assertFalse(may_validate(self.store, self.store.family(fam["id"]), 1), "stale: not before a new score")
        self.assertEqual([f["id"] for f in self.researcher.queue()], [fam["id"]])
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["rescored"], "kept")
        self.researcher.run()  # the upkeep restores what the adoption cleared
        fam = self.store.family(fam["id"])
        self.assertEqual(fam["best_version"], 1)
        self.assertTrue(may_validate(self.store, fam, 1))
        self.assertEqual(len([c for c in self.router.calls if fx.is_review(c)]), 2, "the same program: no new review")

    def test_a_stale_pass_is_scored_again_with_its_restart_check(self):
        """A pass under another identity is not kept on its Train figures alone: its restart check runs again, and while
        the House cannot finish it the pass stays stale (E1 validates nothing)."""
        fam = fx.e2_family(self.store, "rechecked", code=fx.program(share=0.19))
        self.researcher.run()
        before = self.runner.decider.decides
        self.adopt(fam["id"])
        self.runner.decider.restart_after = before + 10
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["house"], "state")
        rec = self.rec(fam["id"])
        self.assertEqual((rec["status"], rec["versions"]["1"]["identity"]["equity"]), ("passed", "a" * 64), "still stale")
        self.assertFalse(may_validate(self.store, self.store.family(fam["id"]), 1))
        self.clock.advance(elane_train.BACKOFF_MAX)
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["rescored"], "kept")
        self.assertGreater(self.runner.decider.decides, before + 4 * fx.STATE_SESSIONS, "the check ran again, whole")
        self.assertEqual(self.rec(fam["id"])["versions"]["1"]["state"]["matched"], 2 * fx.STATE_SESSIONS)
        # A pass whose program no longer keeps its intents (here: the child's answers differ) is withdrawn with STATE.
        self.ident = {"equity": "c" * 64, "engine": "equity-engine-1"}
        real = elane_train.restart_check
        with mock.patch.object(elane_train, "restart_check",
                               lambda *a, **kw: {**real(*a, **kw), "matched": 0, "share": 0.0, "held": False}):
            out = self.researcher.run()
        self.assertEqual((out["steps"][0]["rescored"], out["steps"][0]["fails"]), ("withdrawn", ["STATE"]))
        self.assertIsNone(self.rec(fam["id"]).get("passed_version"))

    def test_a_pass_that_fails_under_the_new_identity_is_withdrawn(self):
        code = fx.program(share=0.28)
        fam = fx.e2_family(self.store, "withdrawn", code=code)
        self.researcher.run()
        self.adopt(fam["id"])
        self.failing(code)
        out = self.researcher.run()
        self.assertEqual(out["steps"][0]["rescored"], "withdrawn")
        rec = self.rec(fam["id"])
        self.assertEqual((rec["status"], rec.get("passed_version"), rec["versions"]["1"]["fails"]),
                         ("researching", None, ["P1", "R1"]))
        self.assertFalse(may_validate(self.store, self.store.family(fam["id"]), 1))

    def test_a_pass_already_tried_is_left_to_e1(self):
        fam = fx.e2_family(self.store, "tried", code=fx.program(share=0.27))
        self.researcher.run()
        self.store.add_run(fam["id"], 1, {"run_id": "val-1", "status": "ok", "trials": 1, "summary": {}},
                           window="validation", stress=1.0, purpose="validation")
        self.adopt(fam["id"])
        self.assertEqual(self.researcher.queue(), [], "its try is taken: E1 validates it again, never E2's Train")
        self.researcher.run()
        self.assertTrue(may_validate(self.store, self.store.family(fam["id"]), 1))


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

    def test_a_refutation_with_no_judged_version_closes_nothing(self):
        for i in range(3):
            fx.e2_family(self.store, f"run{i}", lane="beta", agenda="overnight", symbols=("SPY",),
                         record={"status": "refuted", "versions": {"1": {"passed": False, "fails": ["RUN"]}},
                                 "refuted": {"at": f"2026-10-1{i}T00:00:00Z", "codes": ["RUN"], "versions": 1, "why": "x"}})
        row = {r["cell"]: r for r in train_map(self.store)}[("beta", "overnight", "index")]
        self.assertEqual((row["refuted"], row["stalled"]), (0, 3))
        self.assertEqual(closed_cells(self.store, self.settings), [])
        self.assertEqual(elane_train.refuted_rows(self.store), [])


if __name__ == "__main__":
    unittest.main()
