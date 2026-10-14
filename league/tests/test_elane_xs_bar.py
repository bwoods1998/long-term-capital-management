"""THE PANEL TRAIN BAR, equity-xs-v1 (release E4; league/swarm/elane_xs.py `train_score_xs`, `state_check`, `score`,
`step`): each rule's formula at its boundary (XA0, XT1, XY1, XH1, XP1, XR1), the seen spans (one run a span, the
hidden year cut out), WINDOW, the restart check by CALL (resets after calls 3, 10, 13, 20, ... so no counter stays in
phase), what a version's judgment runs, records, seals and says, the House's failures against the program's, the
hidden run after the verdict, the style reading kept whatever the bar said, and the researcher's step (write, the
review under the panel rubric, the retirement REFUTED or STALLED). league.xs is faked at its interfaces
(league/tests/elane_xs_fakes.py); every program and number is invented."""

from __future__ import annotations

import datetime as dt
import gzip
import json
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from league.equity import config as econfig
from league.swarm import elane_review, elane_train, elane_xs
from league.tests import elane_xs_fakes as F
from league.tests.elane_e2_fakes import FakeRouter, review_answer
from league.xs import config as xconfig
from league.xs import placebo as xplacebo
from league.xs import results as xresults

SEGMENTS = xconfig.TRAIN_SEGMENTS
ALL = list(xconfig.TRAIN_YEARS)


def result(span, *, status="ok", **over):
    """A minimal seen-span result: its span's own start, end and year rows, nothing else."""
    first, last = span
    out = {"status": status, "window": "train", "start": first.isoformat(), "end": last.isoformat(),
           "by_year": {str(y): {} for y in range(first.year, last.year + 1)}, "daily": [], "placebo": {"spans": {}}}
    out.update(over)
    return out


def reading(*, sum_x, t_x, years=None, days=1255, invested=1255, rebalances=250, **more):
    """A pooled reading as `league.xs.results.pooled` gives it."""
    return {"summary": {"sum_x": sum_x, "t_x": t_x, "days": days, "invested_days": invested, "rebalances": rebalances,
                        **more},
            "by_year": {str(y): {"sum_x": v, "days": 251} for y, v in (years or {}).items()}}


class TheBarCase(unittest.TestCase):
    """`train_score_xs` on designed pooled readings (base, stress, half 0, half 1, in the order the bar reads them)."""

    hidden = 2018

    def judge(self, *, base=None, stress=None, halves=(0.3, 0.2), placebo=None, hidden="default", years_ok=ALL):
        spans = elane_xs.run_spans(self.hidden if hidden == "default" else hidden, years_ok)
        seen = [y for a, b in spans for y in range(a.year, b.year + 1)]
        base = base or reading(sum_x=0.6, t_x=3.0, years={y: 0.12 for y in seen})
        stress = stress or reading(sum_x=0.5, t_x=2.5, years={y: 0.10 for y in seen})
        readings = [base, stress, reading(sum_x=halves[0], t_x=1.0), reading(sum_x=halves[1], t_x=1.0)]
        placebo = [0.0] * 200 if placebo is None else placebo
        runs = {"spans": spans, "base": [result(s) for s in spans], "stress": [result(s) for s in spans],
                "halves": {0: [result(s) for s in spans], 1: [result(s) for s in spans]}}
        with mock.patch.object(xresults, "pooled", side_effect=readings), \
                mock.patch.object(xplacebo, "stat", return_value=placebo):
            return elane_xs.train_score_xs(runs, years_ok=years_ok)


class TheRules(TheBarCase):
    def test_a_version_that_meets_every_rule_passes_and_is_judged(self):
        out = self.judge()
        self.assertTrue(out["passed"])
        self.assertEqual((out["fails"], out["judged"], out["score"]), ([], True, 3.0))
        self.assertEqual(out["facts"]["rules"], {code: True for code in ("XA0", *elane_xs.JUDGED_XS)})

    def test_xt1_reads_the_t_at_one_and_a_half_times_the_spread_against_two(self):
        years = {y: 0.1 for y in (2017, 2019, 2022, 2023, 2024)}
        at = self.judge(stress=reading(sum_x=0.5, t_x=elane_xs.BAR_XS["t_min"], years=years))
        below = self.judge(stress=reading(sum_x=0.5, t_x=1.9999, years=years))
        undefined = self.judge(stress=reading(sum_x=0.5, t_x=None, years=years))
        self.assertTrue(at["passed"], "a t exactly at the bar passes")
        self.assertEqual(below["fails"], ["XT1"])
        self.assertIn("XT1", undefined["fails"], "an undefined t fails")
        self.assertFalse(undefined["facts"]["rules"]["XP1"], "and ranks above no placebo")

    def test_xy1_asks_four_of_five_seen_years_and_one_in_each_segment(self):
        def stress(positive):
            return reading(sum_x=0.5, t_x=2.5, years={y: (0.1 if y in positive else -0.1)
                                                      for y in (2017, 2019, 2022, 2023, 2024)})
        self.assertTrue(self.judge(stress=stress({2017, 2022, 2023, 2024}))["passed"], "four of the five seen years")
        three = self.judge(stress=stress({2017, 2022, 2023}))
        self.assertEqual(three["fails"], ["XY1"])
        self.assertEqual((three["facts"]["years_positive"], three["facts"]["years_needed"], three["facts"]["seen_years"]),
                         (3, 4, 5))
        zero = self.judge(stress=reading(sum_x=0.5, t_x=2.5, years={2017: 0.0, 2019: 0.1, 2022: 0.1, 2023: 0.1,
                                                                    2024: 0.1}))
        self.assertTrue(zero["passed"], "four years above zero; a year at exactly zero is not one of them")
        self.assertEqual(zero["facts"]["years_positive"], 4)

    def test_xy1_with_no_hidden_year_asks_four_of_six(self):
        def stress(positive):
            return reading(sum_x=0.5, t_x=2.5, years={y: (0.1 if y in positive else -0.1) for y in ALL})
        self.assertTrue(self.judge(hidden=None, stress=stress({2017, 2018, 2022, 2023}))["passed"])
        self.assertEqual(self.judge(hidden=None, stress=stress({2017, 2022, 2023}))["fails"], ["XY1"])
        one_segment = self.judge(hidden=None, stress=stress({2022, 2023, 2024, 2021}))
        self.assertEqual(one_segment["fails"], ["XY1"], "three years, and none in the first segment")
        lopsided = self.judge(hidden=None, stress=reading(sum_x=0.5, t_x=2.5, years={
            2017: -0.1, 2018: -0.1, 2019: -0.1, 2022: 0.1, 2023: 0.1, 2024: 0.1}))
        self.assertEqual(lopsided["fails"], ["XY1"])

    def test_xy1_needs_a_positive_year_in_each_segment_that_holds_a_seen_year(self):
        # With five or six seen years, enough positive years always reach both segments; the segment clause binds
        # when a segment holds few seen years. 2017 dropped for coverage and 2019 hidden: four seen years, three
        # needed, and all three positive ones in the second segment.
        four = reading(sum_x=0.5, t_x=2.5, years={2018: -0.1, 2022: 0.1, 2023: 0.1, 2024: 0.1})
        self.assertEqual(self.judge(hidden=2019, years_ok=[2018, 2019, 2022, 2023, 2024], stress=four)["fails"], ["XY1"],
                         "the first segment holds a seen year and none of its years is positive")
        both = reading(sum_x=0.5, t_x=2.5, years={2018: 0.1, 2022: 0.1, 2023: 0.1, 2024: -0.1})
        self.assertTrue(self.judge(hidden=2019, years_ok=[2018, 2019, 2022, 2023, 2024], stress=both)["passed"],
                        "three of four (the ceiling of two thirds), one in each segment")

    def test_xh1_asks_both_asset_halves(self):
        self.assertTrue(self.judge(halves=(0.001, 0.001))["passed"])
        self.assertEqual(self.judge(halves=(0.3, 0.0))["fails"], ["XH1"], "a half at exactly zero is not above it")
        self.assertEqual(self.judge(halves=(-0.1, 0.4))["fails"], ["XH1"])

    def test_xp1_ranks_the_t_at_or_above_ninety_five_percent_of_the_placebos_in_integers(self):
        # 200 placebos: at most 10 may sit at or above the program's t (2.5 here).
        def placebo(above):
            return [2.5] * above + [0.0] * (200 - above)
        at = self.judge(placebo=placebo(10))
        self.assertTrue(at["passed"])
        self.assertEqual(at["sealed"]["placebo"], {"draws": 200, "count": 10, "allowed": 10, "rank": 0.95,
                                                   "identity_share": None})
        self.assertEqual(self.judge(placebo=placebo(11))["fails"], ["XP1"])
        nan = float("nan")
        self.assertTrue(self.judge(placebo=[nan] * 150 + [0.0] * 50)["passed"], "an undefined placebo t is not above")
        self.assertEqual(self.judge(placebo=[])["fails"], ["XP1"], "no placebo, no rank")

    def test_xr1_asks_a_positive_sum_and_half_of_it_at_the_stress(self):
        years = {y: 0.1 for y in (2017, 2019, 2022, 2023, 2024)}
        self.assertTrue(self.judge(base=reading(sum_x=0.6, t_x=3.0), stress=reading(sum_x=0.3, t_x=2.5, years=years))
                        ["passed"], "exactly half")
        self.assertEqual(self.judge(base=reading(sum_x=0.6, t_x=3.0),
                                    stress=reading(sum_x=0.2999, t_x=2.5, years=years))["fails"], ["XR1"])
        self.assertEqual(self.judge(base=reading(sum_x=0.0, t_x=0.0),
                                    stress=reading(sum_x=0.3, t_x=2.5, years=years))["fails"], ["XR1"],
                         "the 1.0x sum must be above zero")

    def test_xa0_is_the_programs_and_judges_nothing_else(self):
        idle = self.judge(base=reading(sum_x=-1.0, t_x=-3.0, rebalances=39),
                          stress=reading(sum_x=-1.0, t_x=-3.0), halves=(-1.0, -1.0), placebo=[9.0] * 200)
        self.assertEqual((idle["fails"], idle["judged"], idle["passed"]), (["XA0"], False, False))
        out = self.judge(base=reading(sum_x=0.6, t_x=3.0, days=1000, invested=499, rebalances=40))
        self.assertEqual(out["fails"], ["XA0"], "invested on fewer than half the sessions")
        self.assertTrue(self.judge(base=reading(sum_x=0.6, t_x=3.0, days=1000, invested=500, rebalances=40))["passed"])

    def test_every_judged_fail_is_named_and_the_family_can_be_refuted_on_it(self):
        out = self.judge(base=reading(sum_x=-0.1, t_x=-0.5), stress=reading(sum_x=-0.2, t_x=-0.9, years={}),
                         halves=(-0.1, -0.1), placebo=[5.0] * 200)
        self.assertEqual(out["fails"], list(elane_xs.JUDGED_XS))
        self.assertTrue(out["judged"])
        for code in out["fails"]:
            self.assertIn(elane_xs.FAILS_XS[code], out["why"])

    def test_the_facts_name_no_calendar_year_and_carry_no_sealed_figure(self):
        out = self.judge()
        text = json.dumps(out["facts"])
        for year in (*xconfig.TRAIN_YEARS, *xconfig.HISTORY_YEARS, 2020):
            self.assertNotIn(str(year), text, "a fact that named the seen years would name the hidden one")
        self.assertEqual(len(out["facts"]["years"]), 5, "the seen years, counted in time order")
        self.assertNotIn("halves", text)
        self.assertNotIn("placebo", text)
        self.assertNotIn("rank", text)
        self.assertEqual(out["sealed"]["halves"], {"sum_x": [0.3, 0.2]})

    def test_a_pass_that_fails_at_a_full_haircut_is_flagged_never_failed(self):
        years = {y: 0.1 for y in (2017, 2019, 2022, 2023, 2024)}
        out = self.judge(stress=reading(sum_x=0.5, t_x=2.5, years=years, sum_x_h1=-0.01, sum_x_h0=0.6))
        self.assertTrue(out["passed"])
        self.assertEqual(out["flags"], [elane_xs.FLAG_SURVIVORSHIP])
        self.assertEqual(self.judge(stress=reading(sum_x=0.5, t_x=2.5, years=years, sum_x_h1=0.2))["flags"], [])

    def test_a_result_outside_its_span_is_window_and_a_run_that_did_not_end_ok_is_run(self):
        spans = elane_xs.run_spans(2018, ALL)
        runs = {"spans": spans, "base": [result(s) for s in spans], "stress": [result(s) for s in spans],
                "halves": {0: [result(s) for s in spans], 1: [result(s) for s in spans]}}
        runs["stress"][1] = result(spans[1], daily=[["2018-06-01", 0, 0, 0, 0, 0, 0, 0, False, 1000.0]])
        out = elane_xs.train_score_xs(runs, years_ok=ALL)
        self.assertEqual((out["fails"], out["facts"], out["judged"]), (["WINDOW"], {}, False))
        runs["stress"][1] = result(spans[1], status="no_data")
        self.assertEqual(elane_xs.train_score_xs(runs, years_ok=ALL)["fails"], ["RUN"])
        with self.assertRaises(ValueError):
            elane_xs.train_score_xs({**runs, "base": runs["base"][:1]}, years_ok=ALL)

    def test_the_bars_figures_are_e1s_and_the_specs(self):
        self.assertEqual((elane_xs.K_BASE, elane_xs.K_STRESS), (econfig.K_BASE, econfig.K_STRESS))
        self.assertEqual(elane_xs.BAR_XS, {"min_rebalances": 40, "min_invested": 0.5, "t_min": 2.0, "year_share": 2 / 3,
                                           "placebo_rank": 0.95, "cost_ratio": 0.5, "state_resets": (3, 7),
                                           "state_match": 0.99})
        self.assertEqual(elane_xs.JUDGED_XS, ("XT1", "XY1", "XH1", "XP1", "XR1"))
        self.assertEqual(elane_xs.OBJECTIVE, "equity-xs-v1")


class TheSeenSpans(unittest.TestCase):
    def test_no_hidden_year_is_the_two_whole_segments(self):
        self.assertEqual(elane_xs.seen_spans(None), tuple(SEGMENTS))

    def test_a_hidden_year_is_cut_out_of_its_segment(self):
        d = dt.date
        self.assertEqual(elane_xs.seen_spans(2018), ((d(2017, 1, 3), d(2017, 12, 31)), (d(2019, 1, 1), d(2019, 12, 31)),
                                                     SEGMENTS[1]))
        self.assertEqual(elane_xs.seen_spans(2017), ((d(2018, 1, 1), d(2019, 12, 31)), SEGMENTS[1]))
        self.assertEqual(elane_xs.seen_spans(2024), (SEGMENTS[0], (d(2022, 1, 3), d(2023, 12, 31))))
        self.assertEqual(elane_xs.seen_spans(2023), (SEGMENTS[0], (d(2022, 1, 3), d(2022, 12, 31)),
                                                     (d(2024, 1, 1), d(2024, 12, 31))))

    def test_no_seen_span_holds_a_session_of_the_hidden_year_the_reserve_or_a_history_year(self):
        for hidden in (None, *xconfig.TRAIN_YEARS):
            spans = elane_xs.seen_spans(hidden)
            for first, last in spans:
                self.assertTrue(any(a <= first and last <= b for a, b in SEGMENTS), "inside ONE Train segment")
                years = set(range(first.year, last.year + 1))
                self.assertFalse(years & {hidden, 2016, 2020, 2021})
            seen = sorted(y for first, last in spans for y in range(first.year, last.year + 1))
            self.assertEqual(seen, sorted(set(xconfig.TRAIN_YEARS) - {hidden}))

    def test_the_hidden_span_is_the_hidden_years_own_sessions(self):
        self.assertEqual(elane_xs.hidden_span(2017), (dt.date(2017, 1, 3), dt.date(2017, 12, 31)))
        self.assertEqual(elane_xs.hidden_span(2023), (dt.date(2023, 1, 1), dt.date(2023, 12, 31)))
        for year in (2016, 2020, 2021, 2025):
            with self.assertRaises(ValueError):
                elane_xs.hidden_span(year)

    def test_a_year_the_store_does_not_cover_is_cut_out_as_a_hidden_year_is(self):
        spans = elane_xs.run_spans(2018, [2017, 2018, 2019, 2022, 2024])
        self.assertEqual([(a.year, b.year) for a, b in spans], [(2017, 2017), (2019, 2019), (2022, 2022), (2024, 2024)])
        self.assertEqual(elane_xs.run_spans(None, []), ())

    def test_the_window_rule_reads_run_days_and_never_a_decision_day(self):
        span = (dt.date(2019, 1, 1), dt.date(2019, 12, 31))
        inside = result(span, lots=[{"decided_day": "2018-12-31", "entry_day": "2019-01-02", "exit_day": "2019-02-01"}],
                        picks=[{"decided": "2018-12-31", "exec": "2019-01-02"}])
        self.assertEqual(elane_xs.outside(inside, span), [], "a span's first decision is taken at the close before it")
        for leak in ({"daily": [["2018-12-31", 0, 0, 0, 0, 0, 0, 0, False, 1000.0]]},
                     {"lots": [{"entry_day": "2019-12-31", "exit_day": "2020-01-02"}]},
                     {"picks": [{"decided": "2019-12-31", "exec": "2020-01-02"}]},
                     {"by_year": {"2018": {}, "2019": {}}}, {"start": "2018-12-31"}, {"window": "validation"}):
            self.assertTrue(elane_xs.outside(result(span, **leak), span), leak)
        whole = (dt.date(2016, 1, 4), dt.date(2019, 12, 31))
        self.assertTrue(elane_xs.outside(result(whole, daily=[["2016-03-01", 0, 0, 0, 0, 0, 0, 0, False, 1000.0]]),
                                         whole), "a 2016 day is history only, whatever span is named")


class TheRestartCheck(unittest.TestCase):
    """`state_check`: instance B is loaded fresh after calls 3, 10, 13, 20, 23, 30 (gaps of 3 and 7)."""

    def setUp(self):
        self.world = F.switch_on(self)
        self.decider = self.world.runner.decider

    def run_of(self, code):
        return self.world.runner.train(code, {}, name="p", start=dt.date(2019, 1, 1), end=dt.date(2019, 12, 31),
                                       k=1.5, calls=True)

    def check(self, code, spans=1):
        return elane_xs.state_check(self.decider, code, {}, name="fam", runs=[self.run_of(code)] * spans)

    def test_the_resets_fall_after_calls_3_10_13_20_23_30(self):
        self.assertEqual([i for i in range(45) if elane_xs._reset_due(i)], [3, 10, 13, 20, 23, 30, 33, 40, 43])
        out = self.check(F.good())
        self.assertEqual((out["calls"], out["matched"], out["held"], out["first_miss"]), (F.STATE_CALLS, F.STATE_CALLS,
                                                                                         True, None))
        fresh = [key for key in self.decider.loads if ":b" in key]
        self.assertEqual(len(fresh), 1 + len([i for i in range(F.STATE_CALLS) if elane_xs._reset_due(i)]))
        self.assertEqual(self.decider.instances, {}, "every instance is dropped at the end")

    def test_a_counter_of_any_period_falls_out_of_phase(self):
        # A reset every 20 SESSIONS from the span's start (the first draft) left a weekly program exactly four calls
        # between resets, so counters of period 2 and 4 matched on every call. Gaps of 3 and 7 calls leave none.
        for every in (2, 3, 4, 5, 7, 10):
            out = self.check(F.counter(every))
            self.assertFalse(out["held"], f"a call counter of period {every} passed the restart check")
            self.assertLess(out["share"], 0.99)
            self.assertIsNotNone(out["first_miss"])

    def test_a_program_that_reads_only_ctx_holds(self):
        out = self.check(F.good(), spans=3)
        self.assertEqual((out["calls"], out["share"], out["held"]), (3 * F.STATE_CALLS, 1.0, True))

    def test_a_decide_that_fails_on_an_empty_state_is_no_match(self):
        code = F.program(edge=0.001, body=F.NEEDS_STATE_BODY, state="STATE = {}")
        out = self.check(code)
        self.assertFalse(out["held"])
        self.assertGreater(out["failed"], 0, "one decide raised and the other did not")
        self.assertEqual(out["first_miss"]["call"], 3, "the first call after the first fresh load")

    def test_two_instances_that_both_fail_agree_but_a_disqualified_one_matches_nothing(self):
        out = self.check(F.program(edge=0.001, body=F.RAISES_BODY))
        self.assertGreater(out["disqualified"], 0)
        self.assertFalse(out["held"], "25 errors disqualify the uninterrupted instance: no match from there on")

    def test_a_match_is_the_fill_point_the_ids_and_every_weight_within_a_millionth(self):
        same = elane_xs.same_targets
        a = {"hold": False, "at": "open", "target": {"7": 0.2, "9": 0.2}}
        self.assertTrue(same(a, {"hold": False, "at": "open", "target": {7: 0.2 + 5e-7, 9: 0.2}}), "JSON's string keys")
        self.assertFalse(same(a, {"hold": False, "at": "open", "target": {"7": 0.2 + 2e-6, "9": 0.2}}))
        self.assertFalse(same(a, {"hold": False, "at": "close", "target": {"7": 0.2, "9": 0.2}}))
        self.assertFalse(same(a, {"hold": False, "at": "open", "target": {"7": 0.2, "8": 0.2}}))
        self.assertFalse(same(a, {"hold": True, "target": None}))
        self.assertTrue(same({"hold": True, "target": None}, {"hold": True, "target": None}))
        self.assertFalse(same({"hold": False, "at": "open", "target": {}}, {"hold": True, "target": None}),
                         "a target of no name sells everything; a hold keeps it")

    def test_never_a_silent_pass(self):
        code = F.good()
        self.decider.restart_after = 10
        with self.assertRaises(elane_train.StateCheckInterrupted):
            self.check(code)
        self.decider.restart_after, self.decider.reload_after = None, 12
        with self.assertRaisesRegex(elane_train.StateCheckInterrupted, "reloaded"):
            self.check(code)
        self.decider.reload_after, self.decider.counts = None, False
        with self.assertRaisesRegex(elane_train.StateCheckInterrupted, "call count"):
            self.check(code)
        self.decider.counts = True
        with self.assertRaises(elane_train.StateCheckInterrupted):
            elane_xs.state_check(None, code, {}, name="fam", runs=[self.run_of(code)])
        with mock.patch.object(F.xrunner, "state_stream", lambda run: iter(())):
            with self.assertRaises(elane_train.StateCheckInterrupted):
                self.check(code)
        self.assertEqual(self.decider.instances, {}, "an interrupted check drops its instances too")

    def test_a_failed_check_keeps_the_train_facts_and_fails_state(self):
        verdict = {"passed": True, "fails": [], "facts": {"k10": {}}, "why": None}
        held = elane_xs.with_state(verdict, {"calls": 100, "matched": 99, "share": 0.99, "held": True})
        self.assertTrue(held["passed"])
        lost = elane_xs.with_state(verdict, {"calls": 100, "matched": 98, "share": 0.98, "held": False})
        self.assertEqual((lost["passed"], lost["fails"], lost["facts"]), (False, ["STATE"], {"k10": {}}))
        self.assertFalse(elane_xs.with_state(verdict, {"calls": 0, "matched": 0, "held": True})["passed"])


class ScoreCase(unittest.TestCase):
    def setUp(self):
        self.world = F.switch_on(self)
        self.store = F.new_store(self)
        F.ready(self.store.root)
        self.settings = F.settings("train")
        self.router = FakeRouter(lambda call: review_answer("pass", model="k3_balanced" if "audit" in call["key"]
                                                            else "pro_balanced"))
        self.owner = F.owner(self.store, self.world, self.settings, router=self.router)

    def family(self, slug="rev-a", code=None, **kw):
        return F.panel_family(self.store, slug, code=code if code is not None else F.good(), **kw)

    def score(self, fam, **kw):
        return elane_xs.score(self.owner, self.store.family(fam["id"]), self.store.latest_version(fam["id"]), **kw)

    def record(self, fam):
        return elane_xs.record_of(self.store.family(fam["id"]))

    def events(self, kind):
        return [e for e in self.store.events_after(0, limit=5000) if e["kind"] == kind]


class TheJudgment(ScoreCase):
    def test_a_version_runs_four_runs_a_seen_span_and_the_hidden_year_only_after_its_verdict(self):
        fam = self.family(hidden=2018)
        out = self.score(fam)
        self.assertTrue(out["passed"])
        calls = self.world.runner.calls
        seen = [c for c in calls[:12]]
        self.assertEqual(sorted({(c["start"].year, c["end"].year) for c in seen}), [(2017, 2017), (2019, 2019),
                                                                                  (2022, 2024)])
        for i in range(0, 12, 4):
            a, b, h0, h1 = seen[i:i + 4]
            self.assertEqual((a["k"], a["half"], a["placebos"], a["calls"], a["style"]), (1.0, None, 0, False, True))
            self.assertEqual((b["k"], b["half"], b["placebos"], b["calls"], b["style"]), (1.5, None, 200, True, False))
            self.assertEqual([(h["k"], h["half"], h["placebos"]) for h in (h0, h1)], [(1.5, 0, 0), (1.5, 1, 0)])
        self.assertTrue(all(c["start"].year != 2018 and c["end"].year != 2018 for c in seen))
        hidden = calls[12:]
        self.assertEqual([(c["start"], c["end"], c["k"]) for c in hidden],
                         [(dt.date(2018, 1, 1), dt.date(2018, 12, 31), 1.0), (dt.date(2018, 1, 1),
                                                                             dt.date(2018, 12, 31), 1.5)])
        state = self.store.family(fam["id"])["state"]
        self.assertEqual(sorted(state[elane_xs.OOF_KEY]["1"]), ["1", "1.5"])
        self.assertEqual(sorted(state[elane_xs.OOF_KEY]["1"]["1"]), ["days", "status", "sum_x", "t_x"])

    def test_a_family_with_no_hidden_year_runs_the_two_segments_and_no_hidden_run(self):
        fam = self.family(hidden=None)
        self.score(fam)
        self.assertEqual(len(self.world.runner.calls), 8)
        self.assertNotIn(elane_xs.OOF_KEY, self.store.family(fam["id"])["state"])

    def test_the_record_keeps_the_verdict_and_the_sealed_figures_go_to_their_own_keys(self):
        fam = self.family(hidden=2023)
        self.score(fam)
        entry = self.record(fam)["versions"]["1"]
        self.assertEqual((entry["n"], entry["verdict"], entry["passed"], entry["fails"], entry["objective"]),
                         (1, "pass", True, [], "equity-xs-v1"))
        self.assertEqual(entry["identity"], {"xs": self.world.xs_sha, "engine": "xs-engine-1"})
        self.assertEqual(entry["state"]["calls"], 3 * F.STATE_CALLS)
        self.assertEqual(entry[elane_xs.STYLE_FIELD]["open"], False)
        text = json.dumps(self.record(fam))
        for word in ("halves", "placebo", "identity_share", "rank", "2023", "hidden"):
            self.assertNotIn(word, text)
        state = self.store.family(fam["id"])["state"]
        self.assertEqual(sorted(state[elane_xs.HALVES_KEY]["1"]), ["sum_x"])
        self.assertEqual(state[elane_xs.PLACEBO_KEY]["1"]["draws"], 200)
        for key in (elane_xs.TRAIN_X_KEY, elane_xs.TRAIN_U_KEY, elane_xs.PRECHECK_KEY, elane_xs.LOOK_KEY):
            self.assertNotIn(key, state, "kept from the pre-check on, never at Train")

    def test_the_stored_runs_are_the_seen_spans_train_views_and_never_a_half_or_the_hidden_year(self):
        fam = self.family(hidden=2018)
        self.score(fam)
        rows = self.store._all("SELECT run_id, \"window\", stress, purpose FROM runs WHERE family=?", (fam["id"],))
        self.assertEqual(sorted((r["window"], r["stress"]) for r in rows), sorted([("train", 1.0)] * 3 + [("train", 1.5)] * 3))
        for row in rows:
            kept = self.store.run_result(row["run_id"])
            self.assertEqual(sorted(kept), ["by_year", "end", "k", "pick_counts", "run_id", "runtime", "start", "status",
                                            "summary", "trials", "window"])
            self.assertFalse(str(kept["start"]).startswith("2018"))
            self.assertNotIn("daily", kept)
            self.assertNotIn("placebo", kept)

    def test_the_scored_event_is_e2s_own_kind_once_a_version(self):
        fam = self.family()
        self.score(fam)
        self.score(fam)
        scored = [e["payload"] for e in self.events("swarm.elane") if e["payload"].get("pass") == "scored"]
        self.assertEqual(len(scored), 1)
        version = self.store.latest_version(fam["id"])
        self.assertEqual(scored[0], {"pass": "scored", "version": 1, "sha": version["sha"], "bar_passed": True,
                                     "fails": [], "objective": "equity-xs-v1", "judged": True, "structure": "panel"})
        said = [e["payload"] for e in self.events("swarm.status") if e["payload"].get("action") == "elane_xs_train"]
        self.assertEqual(said, [{"action": "elane_xs_train", "version": 1, "structure": "panel", "passed": True,
                                 "fails": []}])

    def test_a_flat_program_fails_the_judged_rules_and_no_review_is_asked(self):
        fam = self.family(code=F.flat())
        out = self.score(fam)
        self.assertFalse(out["passed"])
        self.assertTrue(set(out["fails"]) & set(elane_xs.JUDGED_XS))
        self.assertNotIn("XA0", out["fails"])
        self.assertEqual(self.router.calls, [])
        self.assertNotIn("review", self.record(fam))

    def test_the_style_reading_is_kept_whatever_the_bar_said(self):
        fam = self.family(code=F.flat(style={"size": 0.6, "vol": -0.5}))
        self.score(fam)
        style = self.record(fam)["versions"]["1"][elane_xs.STYLE_FIELD]
        self.assertTrue(style["open"])
        self.assertEqual(style["tilts"], [["size", 1], ["vol", -1]])
        self.assertEqual(elane_xs.style_of(self.store.family(fam["id"]))["open"], True)
        missing = self.family("rev-b", code=F.good(style="missing"))
        self.score(missing)
        self.assertEqual(self.record(missing)["versions"]["1"][elane_xs.STYLE_FIELD]["why"], "unmeasured",
                         "a run that carried no style block reads unmeasured, which is open")

    def test_a_program_its_own_errors_ended_is_dq_and_judged_on_nothing(self):
        fam = self.family(code=F.good(status="disqualified"))
        out = self.score(fam)
        self.assertEqual(out["fails"], ["DQ"])
        entry = self.record(fam)["versions"]["1"]
        self.assertEqual((entry["facts"], entry.get(elane_xs.STYLE_FIELD)), ({}, None))
        self.assertEqual(elane_xs.judged(self.record(fam)), 0)

    def test_a_refused_load_is_the_programs_and_a_failed_child_is_the_houses_until_others_are_judged(self):
        class ProgramRefused(ValueError):
            pass

        class RunFailed(RuntimeError):
            pass

        fam = self.family()
        self.world.runner.fail["train"] = ProgramRefused("NEEDS names another panel")
        self.assertEqual(self.score(fam)["fails"], ["LOAD"])
        other = self.family("rev-b")
        self.world.runner.fail["train"] = RunFailed("the child died")
        clock = self.store.clock
        for expected in (1, 2):
            out = self.score(other)
            self.assertEqual((out["house"], self.record(other)["infra"]["streak"]), ("run", expected))
            self.assertNotIn("1", self.record(other)["versions"], "nothing scored, no budget spent")
            clock.advance(10)
        self.store.put(elane_xs.TRAIN_OK_KEY, clock())  # another program's judgment completed meanwhile
        clock.advance(10)
        self.assertEqual(self.score(other)["fails"], ["RUN"], "the third failure in a row, with the child sound")

    def test_a_result_outside_its_span_is_refused_whole_and_alerted(self):
        fam = self.family(code=F.good(leak_day="2020-03-02"))
        out = self.score(fam)
        self.assertEqual(out["house"], "window")
        self.assertEqual(self.record(fam)["versions"], {})
        self.assertEqual(self.store._all("SELECT 1 FROM runs WHERE family=?", (fam["id"],)), [])
        alerts = [e["payload"] for e in self.events("swarm.status") if e["payload"].get("action") == "elane_xs_window"]
        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0]["alert"])

    def test_an_interrupted_restart_check_is_the_houses_and_never_a_pass(self):
        fam = self.family()
        self.world.runner.decider.restart_after = 5
        out = self.score(fam)
        self.assertEqual(out["house"], "state")
        self.assertEqual(self.record(fam)["versions"], {})
        self.assertIsNone(self.store.get(elane_xs.TRAIN_OK_KEY), "a check the child failed proves no child sound")

    def test_a_program_with_a_call_counter_fails_state_and_keeps_its_facts(self):
        fam = self.family(code=F.counter(4))
        out = self.score(fam)
        self.assertEqual(out["fails"], ["STATE"])
        entry = self.record(fam)["versions"]["1"]
        self.assertTrue(entry["facts"]["rules"]["XT1"])
        self.assertLess(entry["state"]["share"], 0.99)
        self.assertEqual(elane_xs.judged(self.record(fam)), 0, "STATE judges the program, not the mechanism")

    def test_no_run_starts_while_the_quiet_rule_or_the_days_cpu_says_no(self):
        fam = self.family()
        self.world.quiet = "inside 600 s of the 15:50 ET wall"
        out = self.score(fam)
        self.assertEqual(out["skipped"], "inside 600 s of the 15:50 ET wall")
        self.assertEqual((self.world.runner.calls, self.record(fam)["versions"]), ([], {}))
        self.assertEqual(self.world.quiet_asked[-1][1], 600.0, "asked with the run budget, not with zero")
        self.assertEqual(set(self.world.quiet_sessions), {True},
                         "a panel run's wall is the whole session (one core): every question says so")
        self.world.quiet = None
        self.store.put(elane_xs.CPU_KEY, {elane_xs._utc_day(self.store.clock()): 14400.0})
        self.assertIn("CPU is spent", self.score(fam)["skipped"])
        self.assertEqual(self.world.runner.calls, [])

    def test_the_days_cpu_spent_before_noon_three_days_running_is_one_warning(self):
        day = 86400.0
        base = 1_790_380_800.0  # 2026-09-26T00:00:00Z
        self.assertEqual(elane_xs._utc_day(base), "2026-09-26")

        def spend(now):
            self.store.put(elane_xs.CPU_KEY, {elane_xs._utc_day(now): 14400.0})
            return elane_xs.may_run(self.store, self.settings, now)

        def alerts():
            return [e["payload"] for e in self.events("swarm.status") if e["payload"].get("action") == "elane_xs_cpu"]

        for back in (2, 1):
            self.assertIn("CPU is spent", spend(base - back * day + 6 * 3600))
        self.assertEqual(alerts(), [], "two early days are not three")
        spend(base + 13 * 3600)
        self.assertEqual(alerts(), [], "spent after noon is the budget doing its work")
        spend(base + 6 * 3600)
        spend(base + 7 * 3600)
        self.assertEqual(len(alerts()), 1, "three days running: one warning, once a day")
        self.assertTrue(alerts()[0]["alert"])
        zero = F.settings("train", cpu_seconds_day=0)
        self.assertIn("CPU is spent", elane_xs.may_run(self.store, zero, base + 5 * day + 3600))
        self.assertEqual(len(alerts()), 1, "a budget of zero is a switch, never an alarm")

    def test_the_quiet_rule_is_asked_before_each_run(self):
        fam = self.family(hidden=None)
        asked = []

        def quiet(now, need, *, session=False):
            asked.append(need)
            return "a wall is near" if len(asked) == 6 else None

        with mock.patch.object(F.xconfig, "quiet", quiet):
            out = self.score(fam)
        self.assertEqual(out["skipped"], "a wall is near")
        self.assertEqual(len(self.world.runner.calls), 5, "five runs started; the sixth was held and nothing is scored")
        self.assertEqual(self.record(fam)["versions"], {})

    def test_a_quiet_rule_that_is_not_built_starts_nothing(self):
        def stub(now, need, *, session=False):
            raise NotImplementedError("league.xs.config is a Step 0 stub")

        with mock.patch.object(F.xconfig, "quiet", stub):
            self.assertIn("cannot be read", elane_xs.may_run(self.store, self.settings, self.store.clock()))
            self.assertIn("skipped", self.score(self.family()))
        self.assertEqual(self.world.runner.calls, [])

    def test_every_runs_seconds_are_booked_to_the_utc_day(self):
        fam = self.family(hidden=None)
        with mock.patch.object(elane_xs.time, "monotonic", side_effect=iter(range(0, 10_000, 5))):
            self.score(fam)
        self.assertEqual(elane_xs.cpu_spent(self.store, self.store.clock()), 5.0 * 8)
        elane_xs.book_cpu(self.store, -3.0, self.store.clock())
        elane_xs.book_cpu(self.store, float("nan"), self.store.clock())
        self.assertEqual(elane_xs.cpu_spent(self.store, self.store.clock()), 40.0)
        self.assertEqual(elane_xs.cpu_spent(self.store, self.store.clock() + 86400.0), 0.0, "the next UTC day is whole")

    def test_a_verdict_under_sampled_spreads_carries_no_flag_and_one_under_few_does(self):
        self.score(self.family())
        F.write_manifest(self.store.root, hs_share=0.5)
        fam = self.family("rev-b")
        self.score(fam)
        self.assertEqual(self.record(fam)["versions"]["1"]["flags"], [elane_xs.FLAG_COSTS])
        self.assertEqual(self.record(self.store.family("rev-a"))["versions"]["1"]["flags"], [])

    def test_a_store_with_no_covered_train_year_scores_nothing(self):
        F.write_manifest(self.store.root, train_years_ok=[])
        out = self.score(self.family())
        self.assertEqual(out["house"], "store")
        self.assertEqual(self.world.runner.calls, [])

    def test_a_step_that_must_wait_goes_to_the_back_of_the_queue(self):
        fam = self.family()
        before = self.record(fam).get("last_at")
        self.store.clock.advance(60)
        self.world.quiet = "a wall is near"
        out = elane_xs.step(self.owner, self.store.family(fam["id"]))
        self.assertEqual(out, {"family": fam["id"], "skipped": "a wall is near"})
        rec = self.record(fam)
        self.assertNotEqual(rec["last_at"], before, "the least recently worked family is asked first")
        self.assertEqual((rec["status"], rec["versions"]), ("researching", {}))

    def test_with_the_lane_off_nothing_runs(self):
        fam = self.family()
        for settings in (F.settings("off"), F.settings("train", lane="off")):
            owner = F.owner(self.store, self.world, settings, router=self.router)
            out = elane_xs.score(owner, fam, self.store.latest_version(fam["id"]))
            self.assertIn("closed", out["skipped"])
            self.assertIn("closed", elane_xs.step(owner, fam)["skipped"])
        self.assertEqual((self.world.runner.calls, self.router.calls), ([], []))
        self.assertEqual(self.world.quiet_asked, [])


class TheHousesClock(ScoreCase):
    """THE CLOCK RULE (`elane_xs.steady`; the ship check's major): a decide's limit is a second of WALL time and the
    House's box stands still for longer, so a run whose runtime shows a decide timeout is made again and never read.
    A program that times out the same way in every run of the bound is too slow, and reads so with the measured
    seconds; timeouts that do not repeat are the House's, and nothing is judged."""

    @staticmethod
    def a_run(timeouts, calls=250, seconds=25.0):
        return SimpleNamespace(result={"status": "ok", "runtime": {"calls": calls, "errors": timeouts,
                                                                   "timeouts": timeouts, "decide_seconds": seconds}})

    def test_the_first_run_with_no_timeout_is_the_one_read(self):
        made = []

        def make(script):
            runs = iter(script)

            def one():
                made.append(next(runs))
                return made[-1]
            return one

        clean = self.a_run(0)
        self.assertIs(elane_xs.steady(make([clean])), clean)
        self.assertEqual(len(made), 1, "a clean run is made once")
        del made[:]
        self.assertIs(elane_xs.steady(make([self.a_run(1), self.a_run(2), clean])), clean)
        self.assertEqual(len(made), elane_xs.CLOCK_RUNS, "at most the bound")
        self.assertEqual(elane_xs.clock_of({"runtime": {"calls": 10, "timeouts": 2, "decide_seconds": 4.0}}),
                         {"calls": 10, "timeouts": 2, "seconds": 4.0, "mean": 0.4})
        self.assertEqual(elane_xs.clock_of({})["timeouts"], 0, "a result that carries no runtime shows none")
        self.assertEqual(elane_xs.clock_of(None)["timeouts"], 0)

    def test_timeouts_that_repeat_are_the_programs_and_the_refusal_says_the_measured_seconds(self):
        for script in ([7, 7, 7], [130, 121, 127], [1, 1, 1]):
            with self.assertRaises(elane_xs.TooSlow, msg=script) as raised:
                runs = iter([self.a_run(n, seconds=212.5) for n in script])
                elane_xs.steady(lambda: next(runs), what="span (2019-01-02..2019-12-31, base)")
            said = str(raised.exception)
            self.assertIn("decide ran past 1.00 s of wall time in each of 3 runs", said)
            self.assertIn(f"{script[0]} of 250, {script[1]} of 250, {script[2]} of 250 calls", said)
            self.assertIn("the last run's decides took 212.5 s in all, 0.85 s a call on average", said)

    def test_timeouts_that_do_not_repeat_are_the_houses_clock(self):
        for script in ([1, 2, 1], [3, 1, 2], [12, 1, 1]):      # (12 of 250 is under 5%: one run's bad minute)
            with self.assertRaises(elane_xs.ClockUnsteady, msg=script):
                runs = iter([self.a_run(n) for n in script])
                elane_xs.steady(lambda: next(runs))
        with self.assertRaises(KeyError):
            elane_xs.steady(lambda: {}["a run the child failed passes through"])

    def test_a_judgment_is_made_on_the_run_that_showed_no_timeout(self):
        plain = self.family("rev-plain", code=F.good())
        lost = self.family("rev-lost", code=F.good(clock=[2, 0, 0, 1]))      # its 1st and 4th runs lost decides
        self.score(plain)
        calls = len(self.world.runner.calls)
        out = self.score(lost)
        self.assertEqual((out["passed"], out["fails"]), (True, []))
        self.assertEqual(len(self.world.runner.calls) - calls, calls + 2, "the two runs were made again, once each")
        a, b = self.record(plain)["versions"]["1"], self.record(lost)["versions"]["1"]
        self.assertEqual((b["facts"], b["score"], b["state"]), (a["facts"], a["score"], a["state"]),
                         "the verdict is the clean runs': what a lost decide did to a run was read by nobody")
        stored = self.store.runs(lost["id"])
        self.assertEqual(len(stored), len(self.store.runs(plain["id"])))
        kept = [json.loads(gzip.decompress((self.store.root / r["path"]).read_bytes())) for r in stored]
        self.assertEqual({k["runtime"]["timeouts"] for k in kept}, {0}, "no stored run lost a decide")
        self.assertNotIn("infra", self.record(lost))

    def test_a_program_truly_too_slow_reads_a_refusal_with_the_measured_seconds(self):
        fam = self.family(code=F.good(clock=[9] * 40, clock_calls=250, clock_seconds=231.0))
        out = self.score(fam)
        self.assertEqual((out["passed"], out["fails"]), (False, ["SLOW"]))
        self.assertEqual(len(self.world.runner.calls), elane_xs.CLOCK_RUNS, "the first leg, three times, and no further")
        entry = self.record(fam)["versions"]["1"]
        self.assertEqual((entry["fails"], entry["facts"], entry["passed"]), (["SLOW"], {}, False))
        self.assertEqual(elane_xs.judged(self.record(fam)), 0, "it judges the program, never the mechanism")
        text = elane_xs.version_text(1, entry)
        self.assertIn(elane_xs.PROGRAM_FAILS["SLOW"], text)
        self.assertIn("decide ran past 1.00 s of wall time in each of 3 runs", text)
        self.assertIn("9 of 250, 9 of 250, 9 of 250 calls", text)
        self.assertIn("231.0 s in all, 0.92 s a call on average", text)
        self.assertEqual(self.store._all("SELECT 1 FROM runs WHERE family=?", (fam["id"],)), [], "no run of it is kept")
        scored = [e["payload"] for e in self.events("swarm.elane") if e["payload"].get("pass") == "scored"]
        self.assertEqual([(e["bar_passed"], e["fails"], e["judged"]) for e in scored], [(False, ["SLOW"], False)])
        brief = elane_xs.brief(self.owner, self.store.family(fam["id"]))
        self.assertIn("v1: the program's decide is too slow for the House", brief, "its author reads it")
        self.assertIn("231.0 s in all, 0.92 s a call on average", brief)

    def test_timeouts_that_do_not_repeat_judge_nothing_and_are_told_once(self):
        fam = self.family(code=F.good(clock=[1, 2, 1] * 20))
        tell = elane_train.cfg(self.settings)["train_max_errors"]
        for attempt in range(1, tell + 2):
            out = self.score(fam)
            self.assertEqual(out["house"], "clock")
            self.assertIn("the House's clock, not the program", out["why"])
            self.assertEqual(self.record(fam)["versions"], {}, "nothing scored, no budget spent, no verdict")
            self.assertEqual(self.record(fam)["infra"]["kinds"], {"clock": attempt})
            self.store.clock.advance(10)
        self.assertEqual(self.store._all("SELECT 1 FROM runs WHERE family=?", (fam["id"],)), [])
        alerts = [e["payload"] for e in self.events("swarm.status") if e["payload"].get("action") == "elane_xs_clock"]
        self.assertEqual(len(alerts), 1, "once, at the bound, and not again")
        self.assertTrue(alerts[0]["alert"])
        self.assertEqual([e for e in self.events("swarm.elane") if e["payload"].get("pass") == "scored"], [])

    def test_a_timeout_inside_the_restart_check_is_the_houses_and_never_a_mismatch(self):
        fam = self.family()
        self.world.runner.decider.timeout_at = 8
        out = self.score(fam)
        self.assertEqual(out["house"], "state")
        self.assertIn("ran past 1.00 s of wall time during the restart check", out["why"])
        self.assertEqual(self.record(fam)["versions"], {})
        self.world.runner.decider.timeout_at = None
        self.store.clock.advance(elane_xs.BACKOFF_MAX)
        self.assertTrue(self.score(fam)["passed"], "asked again on a steady clock it is judged")

    def test_the_hidden_run_keeps_no_row_of_a_run_that_lost_decides(self):
        """The bar's runs of a version with a hidden year: 3 spans x 4 legs. Then its two hidden runs."""
        steady = self.family("rev-steady", code=F.good(clock=[0] * 12 + [1, 0, 0]), hidden=2018)
        self.score(steady)
        oof = self.store.family(steady["id"])["state"][elane_xs.OOF_KEY]["1"]
        self.assertEqual(sorted(oof), ["1", "1.5"], "the first hidden run was made again and both are kept")
        slow = self.family("rev-slowhid", code=F.good(clock=[0] * 12 + [4] * 9), hidden=2018)
        self.assertTrue(self.score(slow)["passed"], "the verdict was recorded before the hidden run")
        self.assertNotIn(elane_xs.OOF_KEY, self.store.family(slow["id"])["state"], "and no out-of-fold row of such a run")


class TheJudgmentsMemory(unittest.TestCase):
    """ONE STORE A JUDGMENT, and the restart check's slice cut again (`one_store`, `slicer`, `bar_runs`; the ship
    check's major and the rehearsal's measurement): on the REAL panel store, runner and decider kind (a small
    synthetic panel, invented prices), no double of league.xs."""

    @classmethod
    def setUpClass(cls):
        import shutil
        import tempfile
        from pathlib import Path

        from league.live import decider as D
        from league.tests.test_xs_runner import REAL
        from league.xs import runner as xrunner
        from league.xs import synth

        cls.tmp = tempfile.mkdtemp()
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.root = synth.synthetic_panel(Path(cls.tmp) / "equity-daily", n_assets=40, seed=11, churn=0.10, gate=True)
        cls.code = REAL
        cls.decider = D.InlineDecider()
        cls.iso = xrunner.Isolated(cls.decider, cls.root, nice=None)
        cls.span = (dt.date(2022, 1, 3), dt.date(2022, 12, 30))

    def opened(self):
        """The runner with its store opens counted: (the context to hold it in, the list of stores opened)."""
        from league.xs import store as xstore

        stores = []
        plain = xstore.PanelStore

        def counting(root, gate=None):
            stores.append(plain(root, gate=gate))
            return stores[-1]

        return mock.patch.object(xstore, "PanelStore", counting), stores

    def test_the_runner_opens_the_store_for_every_run_and_a_judgment_opens_it_once(self):
        first, last = self.span
        counted, stores = self.opened()
        with counted:
            for k in (1.0, 1.5):
                self.iso.train(self.code, None, name="p", start=first, end=last, k=k)
            self.assertEqual(len(stores), 2, "as the runner is: a store a run")
            del stores[:]
            with elane_xs.one_store(self.iso) as held:
                self.assertIs(held, self.iso)
                a = self.iso.train(self.code, None, name="p", start=first, end=last, k=1.0)
                b = self.iso.train(self.code, None, name="p", start=first, end=last, k=1.5, half=0)
                self.iso.validation(self.code, None, name="p")
                self.assertEqual(len(stores), 1, "one store for the judgment's ungated runs")
                with elane_xs.one_store(self.iso):       # (a judgment inside a chunk's store adds none)
                    self.iso.train(self.code, None, name="p", start=first, end=last, k=1.0)
                self.assertEqual(len(stores), 1)
            self.assertNotIn("_store", vars(self.iso), "the runner is as it was afterwards")
            self.iso.train(self.code, None, name="p", start=first, end=last, k=1.0)
            self.assertEqual(len(stores), 2)
        again = self.iso.train(self.code, None, name="p", start=first, end=last, k=1.0)
        self.assertEqual((a.result["result_sha"], b.result["half"]), (again.result["result_sha"], 0),
                         "a run on the kept store is the run on a store of its own")

    def test_a_gated_run_never_reads_the_kept_store(self):
        from league.equity.store import mint_equity_gate_capability

        gate = mint_equity_gate_capability(self.root, "the one look")
        counted, stores = self.opened()
        with counted, elane_xs.one_store(self.iso):
            self.iso.train(self.code, None, name="p", start=self.span[0], end=self.span[1])
            self.iso.look(self.code, None, name="p", gate=gate, placebos=5, seed=3)
            self.iso.look(self.code, None, name="p", gate=gate, placebos=5, seed=3)
        self.assertEqual(len(stores), 3, "the sealed window's store is opened for its run and never kept")

    def test_a_double_of_the_runner_is_left_as_it_is(self):
        double = F.FakeRunner()
        with elane_xs.one_store(double) as held:
            self.assertIs(held, double)
        self.assertIsNone(elane_xs.slicer(double, self.code, {}, name="p"), "and its k 1.5 runs are kept whole")

    def test_the_slice_cut_again_is_the_runs_own_and_the_restart_check_reads_it(self):
        from league.xs import runner as xrunner

        first, last = self.span
        run = self.iso.train(self.code, None, name="p", start=first, end=last, k=1.5, placebos=5, calls=True)
        cut = elane_xs.slicer(self.iso, self.code, None, name="p")
        again = cut(first, last)
        self.assertEqual(again.run_key, run.slice.run_key)
        self.assertEqual(again.bars.dither_key, run.slice.bars.dither_key)
        for name in ("days", "early", "raw", "adj", "elig0", "ids", "exit", "hs", "sector_perm"):
            self.assertTrue(np.array_equal(getattr(again.bars, name), getattr(run.slice.bars, name), equal_nan=True), name)
        self.assertTrue(np.array_equal(again.aids, run.slice.aids))
        # A k 1.5 run kept WITHOUT its slice gives the restart check the same stream, call for call...
        kept = elane_xs._Kept(run.result, lambda: cut(first, last))
        whole, lazy = list(xrunner.state_stream(run)), list(xrunner.state_stream(kept))
        self.assertGreater(len(whole), 30)
        self.assertEqual(len(lazy), len(whole), "every call's ctx was rebuilt and held to the sha the run recorded")
        # ...and A SLICE THAT IS NOT THE RUN'S IS REFUSED, never read: the stream holds every rebuilt ctx to the sha
        # the run recorded for that call.
        other = elane_xs._Kept(run.result, lambda: cut(dt.date(2023, 1, 3), dt.date(2023, 12, 29)))
        with self.assertRaises(xrunner.RunFailed):
            list(xrunner.state_stream(other))

    def test_the_bars_runs_keep_results_and_the_stress_runs_come_without_their_slices(self):
        made = []

        def run_one(**kw):
            made.append(self.iso.train(self.code, None, name="p", **kw))
            return made[-1]

        spans = (self.span, (dt.date(2023, 1, 3), dt.date(2023, 12, 29)))
        with elane_xs.one_store(self.iso):
            parts, stress = elane_xs.bar_runs(run_one, spans, placebos=5,
                                              again=elane_xs.slicer(self.iso, self.code, None, name="p"))
            self.assertEqual({leg: len(rs) for leg, rs in parts.items()}, {"base": 2, "stress": 2, 0: 2, 1: 2})
            self.assertEqual([type(run).__name__ for run in stress], ["_Kept", "_Kept"])
            self.assertEqual([run.result["result_sha"] for run in stress], [r["result_sha"] for r in parts["stress"]])
            self.assertNotIn("slice", vars(stress[0]), "no slice is held: it is cut when it is read")
            check = elane_xs.state_check(self.decider, self.code, None, name="p", runs=stress)
        self.assertGreater(check["calls"], 60)
        self.assertEqual(check["resets"], list(elane_xs.BAR_XS["state_resets"]))
        whole = elane_xs.state_check(self.decider, self.code, None, name="p",
                                     runs=[made[1], made[5]])       # (the same two k 1.5 runs, kept whole)
        self.assertEqual({k: check[k] for k in ("calls", "matched", "disqualified", "failed", "first_miss")},
                         {k: whole[k] for k in ("calls", "matched", "disqualified", "failed", "first_miss")},
                         "the restart check on the slices cut again is the check on the runs kept whole")


class TheReviewAndTheStep(ScoreCase):
    def test_a_bar_pass_is_reviewed_by_two_models_under_the_panel_rubric_and_becomes_the_try(self):
        fam = self.family()
        out = self.score(fam)
        self.assertEqual(out["review"]["review"], "pass")
        rec = self.record(fam)
        self.assertEqual((rec["status"], rec["passed_version"]), ("passed", 1))
        self.assertEqual([c["key"].split(":")[3] for c in self.router.calls], ["review", "audit"])
        for call in self.router.calls:
            self.assertTrue(call["system"].startswith(elane_xs.REVIEW_SYSTEM))
            for line in elane_xs.REVIEW_XS:
                self.assertIn(line, call["system"])
            self.assertIn(self.store.latest_version(fam["id"])["code"], call["user"])
            self.assertNotIn("SPY", call["user"].split("```")[0], "a panel family names no symbol")
        state = self.store.family(fam["id"])["state"]
        held = state[elane_review.STATE_REVIEW]
        self.assertEqual((held["objective"], held["source"], held["rubric"]),
                         (elane_xs.REVIEW_OBJECTIVE, "elane_xs", elane_xs.rubric_sha()))
        self.assertNotEqual(held["route"], held["audit"]["route"], "two different readers")
        self.assertNotEqual(elane_review.model_of(held["route"]), elane_review.model_of(held["audit"]["route"]))
        self.assertEqual(self.store.family(fam["id"])["best_version"], 1)

    def test_the_rubric_names_what_a22_asks_and_cites_e2s_references(self):
        rubric = " ".join(elane_xs.REVIEW_XS)
        for words in ("embedded return table", "calendar recognition", "ctx.ids", "calendar period", "price level"):
            self.assertIn(words, rubric)
        self.assertEqual(len(elane_xs.REVIEW_REFERENCES), len(elane_xs.REVIEW_XS))
        self.assertLessEqual(set(elane_xs.REVIEW_REFERENCES) | {"fills"}, set(elane_review.FACTS),
                             "a failure cites a reference E2's `grounded` knows, or it reads unclear")
        self.assertNotIn("event_calendar", elane_xs.INPUTS, "a panel program's ctx offers no event flag")
        for text in (elane_xs.RESEARCHER_SYSTEM, elane_xs.bar_text(), elane_xs.CONTRACT_FALLBACK):
            self.assertNotIn("ctx.events", text)

    def test_a_review_failure_is_a_train_failure_of_the_version_and_spends_no_try(self):
        code = F.good()
        excerpt = "ids = [int(i) for i in ctx.ids[:ctx.params[\"names\"]]]"
        self.router.script = lambda call: review_answer("fail", excerpt=excerpt, reference="context",
                                                        reasons=("it orders the slots by their ids",))
        fam = self.family(code=code)
        out = self.score(fam)
        self.assertEqual(out["review"]["fails"], ["REVIEW"])
        entry = self.record(fam)["versions"]["1"]
        self.assertEqual((entry["passed"], entry["verdict"], entry["bar_passed"], entry["fails"]),
                         (False, "fail", True, ["REVIEW"]))
        self.assertIsNone(self.record(fam).get("passed_version"))
        self.assertNotIn(elane_review.STATE_REVIEW, self.store.family(fam["id"])["state"])
        self.assertIn("REVIEW", elane_xs.version_text(1, entry))

    def test_the_step_scores_writes_and_retires(self):
        fam = self.family(code=F.flat())
        first = elane_xs.step(self.owner, self.store.family(fam["id"]))
        self.assertFalse(first["passed"])
        self.router.script = lambda call: {"text": "", "json": {"program": F.flat(seed=len(self.router.calls)),
                                                                "note": "another try"},
                                           "route": "sail", "model": "pro_asap", "cost_usd": 0.05}
        written = elane_xs.step(self.owner, self.store.family(fam["id"]))
        self.assertEqual((written["version"], written["route"]), (2, F.ROUTE))
        brief = self.router.calls[-1]
        self.assertTrue(brief["system"].startswith(elane_xs.RESEARCHER_SYSTEM))
        self.assertIn("YOUR VERSIONS ON TRAIN", brief["user"])
        for _ in range(2):
            last = elane_xs.step(self.owner, self.store.family(fam["id"]))
        self.assertIn("retired", last["score"])
        rec = self.record(fam)
        self.assertEqual((rec["status"], len(rec["versions"]), rec["attempts"]), ("refuted", 4, 3))
        retired = self.store.family(fam["id"])
        self.assertTrue(retired["retired_at"])
        self.assertIn("REFUTED on Train (equity-xs-v1)", retired["retire_reason"])
        grave = self.store._all("SELECT lesson FROM graveyard WHERE family=?", (fam["id"],))
        self.assertIn("panel sp500", grave[0]["lesson"])

    def test_a_family_no_version_of_which_the_bar_judged_is_stalled_never_refuted(self):
        fam = self.family(code=F.good(status="disqualified"))
        elane_xs.step(self.owner, self.store.family(fam["id"]))
        out = elane_xs.finish(self.owner, self.store.family(fam["id"]), "its Train budget is spent")
        self.assertEqual(out, {"family": fam["id"], "stalled": ["DQ"]})
        self.assertEqual(self.store._all("SELECT 1 FROM graveyard WHERE family=?", (fam["id"],)), [])
        self.assertEqual(elane_xs.closed_cells(self.store, self.settings), [])

    def test_a_program_that_does_not_fit_the_family_is_refused_before_it_runs(self):
        fam = self.store.family(self.family()["id"])
        check = lambda code: elane_xs.check_code(code, fam, self.settings)  # noqa: E731
        self.assertIsNone(check(F.good()))
        self.assertIn("schedule", check(F.good(rebalance="monthly")))
        self.assertIn("max_names", check(F.good(names=8)))
        self.assertIn("weekday", check(F.good(weekday=2)))
        self.assertIn("literal dict", check(F.good().replace("NEEDS = {", "NEEDS = dict(panel=\"sp500\") or {")))
        self.assertIn("code rules", check("import os\n" + F.good()))
        self.assertIn("never a symbol", check(F.good().replace("'panel': 'sp500'", "'panel': 'sp500', 'symbols': ['SPY']")))

    def test_a_stop_before_the_bar_judged_anything_is_not_accepted(self):
        fam = self.family(code=F.good(status="disqualified"))
        elane_xs.step(self.owner, self.store.family(fam["id"]))
        self.router.script = lambda call: {"text": "", "json": {"stop": "nothing works"}, "route": "sail",
                                           "model": "pro_asap", "cost_usd": 0.01}
        out = elane_xs.step(self.owner, self.store.family(fam["id"]))
        self.assertIn("a stop is accepted only once", out["refused"])
        self.assertFalse(self.store.family(fam["id"])["retired_at"])

    def test_the_brief_holds_train_facts_only_and_never_the_hidden_year(self):
        fam = self.family(hidden=2022)
        self.score(fam)
        text = elane_xs.brief(self.owner, self.store.family(fam["id"]))
        self.assertIn(elane_xs.HIDDEN_NOTE, text)
        self.assertNotIn("2022", text.replace("2022-24", ""))
        state = self.store.family(fam["id"])["state"]
        for sealed in ("placebo rank", "identity_share", "hidden_year", *(
                str(x) for x in state[elane_xs.HALVES_KEY]["1"]["sum_x"]), str(state[elane_xs.OOF_KEY]["1"]["1"]["sum_x"])):
            self.assertNotIn(sealed, text)
        self.assertIn("Style reading", text)
        facts = elane_xs.train_facts(self.store.family(fam["id"]))
        self.assertTrue(facts["held_out"])
        self.assertNotIn("hidden_year", json.dumps(facts))
        self.assertNotIn("loadings", json.dumps(facts), "which names it held on size is never shown: the tilt's name is")

    def test_a_stale_pass_is_scored_again_and_withdrawn_when_it_no_longer_holds(self):
        fam = self.family()
        self.score(fam)
        self.assertTrue(elane_xs.pass_current(self.store, self.store.family(fam["id"])))
        self.assertEqual(elane_xs.step(self.owner, self.store.family(fam["id"])), {"family": fam["id"],
                                                                                 "skipped": "its pass stands"})
        self.world.xs_sha = "d" * 64  # an xs evidence module changed
        self.assertFalse(elane_xs.pass_current(self.store, self.store.family(fam["id"])))
        kept = elane_xs.step(self.owner, self.store.family(fam["id"]))
        self.assertEqual(kept["rescored"], "kept")
        entry = self.record(fam)["versions"]["1"]
        self.assertEqual((entry["identity"]["xs"], entry["rescored_from"]["xs"]), ("d" * 64, "c" * 64))
        self.world.xs_sha = "e" * 64
        version = self.store.latest_version(fam["id"])
        # the same program now earns nothing (an invented change of the engine's arithmetic)
        original = F.FakeRunner._result

        def worse(runner, code, params, **kw):
            return original(runner, code, {**dict(params or {}), "edge": 0.0}, **kw)

        with mock.patch.object(F.FakeRunner, "_result", worse):
            out = elane_xs.score(self.owner, self.store.family(fam["id"]), version, rescore=True)
        self.assertEqual(out["rescored"], "withdrawn")
        rec = self.record(fam)
        self.assertEqual((rec["status"], rec["passed_version"]), ("researching", None))
        self.assertNotIn("passed_review", rec)
        self.assertIsNone(self.store.family(fam["id"])["best_version"])
        self.assertIsNone(self.store.family(fam["id"])["state"].get(elane_review.STATE_REVIEW))

    def test_a_pass_under_provisional_costs_is_scored_again_once_the_spreads_are_sampled(self):
        F.write_manifest(self.store.root, hs_share=0.5)
        fam = self.family()
        self.score(fam)
        self.assertTrue(elane_xs.pass_current(self.store, self.store.family(fam["id"])), "nothing better to score at yet")
        F.write_manifest(self.store.root, hs_share=0.95)
        self.assertFalse(elane_xs.pass_current(self.store, self.store.family(fam["id"])))
        self.assertEqual(elane_xs.step(self.owner, self.store.family(fam["id"]))["rescored"], "kept")
        self.assertEqual(self.record(fam)["versions"]["1"]["flags"], [])
        self.assertTrue(elane_xs.pass_current(self.store, self.store.family(fam["id"])))


@unittest.skipUnless(F.PATCHED, F.HOLDS.format(n=7))
class E2sResearcherForwardsAPanelFamily(ScoreCase):
    """Patch 7: `EquityResearcher.step`, `score`, `brief`, `review_step` and `restart` forward a panel family, and the
    record's readers (`record_of`, `_update`, `pass_current`, `may_validate`) read the panel's own record."""

    def researcher(self):
        from league.swarm.elane_train import EquityResearcher

        r = EquityResearcher(self.store, self.router, self.settings, root=self.store.root, clock=self.store.clock)
        r.xs_runner = self.world.runner
        return r

    def test_a_round_scores_and_reviews_a_panel_family_under_its_own_record(self):
        fam = self.family()
        r = self.researcher()
        self.assertTrue(r.due())
        out = r.run()
        self.assertEqual(out["steps"][0]["passed"], True)
        state = self.store.family(fam["id"])["state"]
        self.assertEqual(state[elane_xs.STATE_KEY]["status"], "passed")
        self.assertNotIn(elane_train.STATE_KEY, state, "E2's own key is never written for a panel family")
        self.assertEqual(elane_train.record_of(self.store.family(fam["id"])), elane_xs.record_of(self.store.family(fam["id"])))
        self.assertEqual(elane_train.passed_version(self.store.family(fam["id"])), 1)
        self.assertTrue(r.idle() or not r.queue(), "a pass that stands asks for no further step")
        self.assertEqual(r.brief(self.store.family(fam["id"])), elane_xs.brief(r, self.store.family(fam["id"])))

    def test_a_panel_family_that_cannot_move_takes_no_place_in_the_round(self):
        from league.tests.elane_e2_fakes import e2_family

        fam = self.family()
        e2_family(self.store, "etf-a", code=None)
        r = self.researcher()
        self.assertEqual(sorted(f["id"] for f in r.queue()), ["etf-a", fam["id"]])
        F.panel_family(self.store, "mom-a", agenda="xs_momentum", code=F.good(tag="m"))
        self.world.quiet = "a wall is near"
        self.world.quiet_asked.clear()
        self.assertEqual([f["id"] for f in r.queue()], ["etf-a"], "the ETF family's research is not slowed")
        self.assertEqual(len(self.world.quiet_asked), 1, "asked once a round, not once a family")
        self.world.quiet = None
        r.settings = F.settings("off")
        self.assertEqual([f["id"] for f in r.queue()], ["etf-a"], "a closed panel lane (the rollback) the same")
        self.assertEqual(elane_xs.blocked(r), "the panel lane is closed (elane.panel.mode)")

    def test_the_restart_check_of_a_panel_family_is_the_panels_own(self):
        fam = self.family()
        r = self.researcher()
        code = self.store.latest_version(fam["id"])["code"]
        run = self.world.runner.train(code, {}, name=fam["id"], start=dt.date(2019, 1, 1), end=dt.date(2019, 12, 31),
                                      k=1.5, calls=True)
        out = r.restart(fam["id"], code, {}, [run])
        self.assertEqual((out["calls"], out["held"], out["resets"]), (F.STATE_CALLS, True, [3, 7]),
                         "by CALL, through the panel kind (the fake decider refuses any other kind)")

    def test_e2s_maps_never_count_a_panel_family(self):
        fam = self.family()
        self.score(fam)
        self.assertEqual(elane_train.train_map(self.store), [])
        self.assertEqual(elane_train.refuted_rows(self.store), [])
        self.assertEqual(elane_train.closed_cells(self.store, self.settings), [])
        self.assertEqual(elane_train.train_map_text(self.store, self.settings),
                         elane_xs.train_map_text(self.store, self.settings))
        self.assertIn("PANEL TRAIN MAP", elane_train.train_map_text(self.store, self.settings))
        self.assertEqual(elane_train.train_map_text(self.store, F.settings("off")), "",
                         "with the panel lane closed E2's map says nothing of the panel")
        from league.swarm import elane_births, elane_yield

        self.assertEqual(elane_births.researching(self.store), 0)
        self.assertEqual(elane_yield.train_counts(self.store, elane_train.STATE_KEY)[F.ROUTE],
                         {"families": 1, "train_scored": 1, "train_passes": 1})

    def test_the_guard_reads_the_panel_record_and_the_mode(self):
        fam = self.family()
        self.score(fam)
        self.assertFalse(elane_train.may_validate(self.store, self.store.family(fam["id"]), 1),
                         "the settings on disk say off: no Validation try")
        (F.Path(self.store.root) / "swarm.json").write_text(json.dumps({"elane": {"mode": "gate",
                                                                                  "panel": {"mode": "gate"}}}))
        with elane_xs._cache_lock:
            elane_xs._mode_cache.clear()
        self.assertTrue(elane_train.may_validate(self.store, self.store.family(fam["id"]), 1))
        self.assertFalse(elane_train.may_validate(self.store, self.store.family(fam["id"]), 2), "only its pass")
        F.write_manifest(self.store.root, live_from="2026-09-01", hs_share=0.5)
        self.assertFalse(elane_train.may_validate(self.store, self.store.family(fam["id"]), 1),
                         "provisional costs: the mode reads train, and a pass takes no try")


if __name__ == "__main__":
    unittest.main()
