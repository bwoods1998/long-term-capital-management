"""THE MECHANISM TEST (league/swarm/mechanism.py, release B) and its place in the researcher (league/swarm/researcher.py):
before a carded family's first broad Train replay its program runs with the signal on and with its card's ablation over a
pre-registered sample of Train windows. Shadow mode (the default) records a blind verdict for a sample of families and
runs the broad replay anyway; gate mode makes broad replay and sweeps wait for a pass and retires a card that fails below
the base bound three times. Every arm is a trial; the verdict is recorded on the card; the bound and the pass are the
lineage's. Synthetic programs, a fake Gym and a synthetic Gym store only (no quotes, no real parameters)."""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.swarm import cards, mechanism
from league.swarm import settings as S
from league.swarm.architect import tag_of
from league.swarm.pool import PoolError
from league.tests.swarm_fakes import result
from league.tests.test_swarm_researcher import ResearcherCase

CODE = ('NEEDS = {"roots": ["SPY"], "dte": [0, 5], "cadence": 30}\n'
        'PARAMS = {"signal_on": 1, "threshold": 600}\n\n'
        'def decide(ctx):\n'
        '    if PARAMS["signal_on"] and ctx.minute < PARAMS["threshold"]:\n'
        '        return []\n'
        '    return []\n')
NO_SWITCH = CODE.replace('"signal_on": 1, ', '').replace('PARAMS["signal_on"] and ', '')
BOOL_SWITCH = CODE.replace('"signal_on": 1', '"signal_on": True')

CARD = {"hypothesis": "Liquidity-demanding sellers push the close below value late in the day and patient buyers are paid "
                      "to absorb it over the next session.",
        "mechanism_class": "reversal_liquidity", "inputs": ["underlying_price", "clock"], "holding": "days_1_3",
        "cost": {"hurdle": 0.08, "why": "two half-spreads and fees on a narrow debit vertical"},
        "comparison": "the same debit vertical opened at the same minute every session without the late-selling condition",
        "ablation": {"param": "signal_on", "off": 0},
        "falsification": "signal entries do not beat the comparison's by t 0.75 on the mechanism sample"}
FLAT = {**CARD, "mechanism_class": "volatility_risk_premium", "ablation": {"flat": True},
        "hypothesis": "Index option buyers overpay for protection, so a hedged short premium position is paid for bearing "
                      "variance risk over its holding period."}


def trade_days(window_start: str, n: int, offset: int = 0) -> list[str]:
    """Distinct synthetic day labels inside a window (labels only; the statistic groups by them)."""
    year, month = window_start[:4], window_start[5:7]
    return [f"{year}-{month}-{(offset + i) % 28 + 1:02d}" for i in range(n)]


def trade(i: int, day: str, pnl: float, **context) -> dict:
    """A synthetic trade in the Gym's shape: one debit vertical, 3 days to expiry, at the money, entered at 10:00."""
    return {"id": i, "day": day, "pnl": pnl, "max_loss": 50.0, "fees": 1.0, "type": "debit_vertical", "entry_minute": 600,
            "sessions_held": 1, "legs": [{"strike": 100.0}, {"strike": 102.0}],
            "context": {"dte": 3, "moneyness": 0.0, "spot": 100.0, **context}}


class Sample(unittest.TestCase):
    def test_the_sample_is_pre_registered_inside_the_years_every_root_holds(self):
        w = mechanism.sample_windows()
        self.assertEqual(len(w), 4)
        self.assertEqual(mechanism.windows_id(w), mechanism.windows_id(mechanism.WINDOWS), "the same for every family")
        days = [dt.date.fromisoformat(d) for pair in w for d in pair]
        self.assertTrue(all(S.TRAIN_CORE_START <= d <= S.TRAIN_END for d in days),
                        "2022-2024 only: every image holds every admitted root from 2022-01-03 (review of #446: a 2020 window "
                        "with a root that has no data there fails its whole batch)")
        months = sorted((dt.date.fromisoformat(a) + dt.timedelta(days=k)).month for a, b in w
                        for k in range((dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days + 1)
                        if (dt.date.fromisoformat(a) + dt.timedelta(days=k)).day == 15)
        self.assertEqual(months, list(range(1, 13)), "every calendar month once: all four quarter-ends and a year-end")
        self.assertEqual({dt.date.fromisoformat(a).year for a, _ in w} | {dt.date.fromisoformat(b).year for _, b in w},
                         {2022, 2023, 2024})

    def test_a_hold_the_window_cuts_short_is_not_counted(self):
        self.assertEqual(mechanism.counted_until("2022-04-30", "intraday"), "2022-04-30")
        self.assertEqual(mechanism.counted_until("2022-04-30", "days_11_plus"), "2022-03-31")
        rows = [{"day": "2022-01-31"}, {"day": "2022-02-01"}, {"day": "2022-04-10"}, {"day": "2022-04-29"}]
        self.assertEqual([t["day"] for t in mechanism.counted(rows, "2022-02-01", "2022-04-30", "days_4_10")],
                         ["2022-02-01", "2022-04-10"])
        self.assertEqual(len(mechanism.counted(rows, "2022-02-01", "2022-04-30", "intraday")), 3)


class Statistic(unittest.TestCase):
    def test_welch_passes_a_signal_that_selects_better_entries(self):
        on = {f"d{i}": 0.3 + 0.05 * (i % 3) for i in range(20)}
        off = {**on, **{f"x{i}": -0.1 + 0.05 * (i % 3) for i in range(60)}}
        v = mechanism.compare(on, off)
        self.assertEqual((v["verdict"], v["method"], v["n_on"], v["n_off"]), ("passed", "welch", 20, 60))
        self.assertGreater(v["t"], 5)

    def test_a_signal_no_better_than_its_comparison_fails(self):
        rng = random.Random(3)
        on = {f"d{i}": rng.gauss(0.0, 1.0) for i in range(20)}
        off = {f"x{i}": rng.gauss(0.2, 1.0) for i in range(60)}
        v = mechanism.compare(on, off)
        self.assertEqual(v["verdict"], "failed")
        self.assertIn("passing needs a positive difference", v["why"])

    def test_thin_invalid_and_paired(self):
        self.assertEqual(mechanism.compare({"a": 1.0, "b": 2.0}, {"c": 0.0})["verdict"], "thin")
        flat = mechanism.compare({f"d{i}": 0.1 * i for i in range(10)}, {})
        self.assertEqual(flat["verdict"], "invalid_ablation", "an ablation that did not trade compares nothing")
        on = {f"d{i}": 0.2 + 0.01 * i for i in range(10)}
        off = {d: r - 0.1 - 0.005 * (i % 2) for i, (d, r) in enumerate(on.items())}
        v = mechanism.compare(on, off)
        self.assertEqual((v["verdict"], v["method"]), ("passed", "paired"), "same days: the signal changes what is bought")

    def test_identical_arms_are_an_invalid_ablation_never_a_finding(self):
        on = {f"d{i}": 0.1 * (i % 4) - 0.1 for i in range(12)}
        v = mechanism.compare(on, dict(on))
        self.assertEqual(v["verdict"], "invalid_ablation")
        self.assertIn("changed nothing", v["why"])

    def test_a_flat_comparison_is_against_not_trading(self):
        self.assertEqual(mechanism.compare_flat({f"d{i}": 0.05 + 0.01 * (i % 3) for i in range(12)})["verdict"], "passed")
        loses = mechanism.compare_flat({f"d{i}": -0.05 + 0.01 * (i % 3) for i in range(12)})
        self.assertEqual((loses["verdict"], loses["method"]), ("failed", "flat"))
        self.assertEqual(mechanism.compare_flat({"a": 1.0})["verdict"], "thin")

    def test_day_returns_group_trades_by_entry_day(self):
        got = mechanism.day_returns([{"day": "d1", "pnl": 10.0, "max_loss": 50.0}, {"day": "d1", "pnl": -5.0, "max_loss": 50.0},
                                     {"day": "d2", "pnl": 1.0, "max_loss": 0.0}, {"day": None, "pnl": 1.0, "max_loss": 1.0}])
        self.assertEqual(got, {"d1": 0.05})

    def test_config_falls_back_on_bad_values(self):
        cfg = mechanism.config({"researcher": {"mechanism_test": {"min_t": "x", "enabled": 1, "mode": "bogus", "sample": 7}}})
        self.assertEqual((cfg["min_t"], cfg["enabled"], cfg["mode"], cfg["sample"]), (0.75, True, "shadow", 1.0))
        self.assertEqual(mechanism.config({})["sample"], 0.25, "shadow tests a quarter of carded families by default")
        self.assertEqual(mechanism.config({"researcher": {"mechanism_test": {"mode": "GATE"}}})["mode"], "gate")
        self.assertFalse(mechanism.config({"researcher": {"mechanism_test": False}})["enabled"])
        self.assertEqual(mechanism.config({})["mode"], "shadow", "shadow until House evidence says it may gate")


class Audit(unittest.TestCase):
    def arm(self, n: int = 12, **context) -> dict:
        return mechanism.profile([trade(i, f"d{i}", 1.0, **context) for i in range(n)])

    def test_a_comparison_with_the_signals_profile_passes(self):
        on = self.arm()
        self.assertEqual((on["types"], on["dte"], on["moneyness"], on["width"], on["minute"], on["sessions"]),
                         (["debit_vertical"], 3.0, 0.0, 0.02, 600.0, 1.0))
        self.assertIsNone(mechanism.audit(on, self.arm(n=30, moneyness=0.01)), "a signal may shift its strikes a little")

    def test_a_clock_signal_may_enter_at_other_minutes(self):
        """Review of #446: a last-hour signal's comparison is the same structure entered at other times of day."""
        on = mechanism.profile([{**trade(i, f"d{i}", 1.0), "entry_minute": 900} for i in range(12)])
        off = mechanism.profile([{**trade(i, f"d{i}", 1.0), "entry_minute": 600} for i in range(20)])
        self.assertIn("entry minute", mechanism.audit(on, off))
        self.assertIsNone(mechanism.audit(on, off, skip=mechanism.CLOCK_SKIPS))
        self.assertIn("days to expiry", mechanism.audit(on, self.arm(dte=30), skip=mechanism.CLOCK_SKIPS), "only the minute")

    def test_a_comparison_that_trades_something_else_is_caught(self):
        on = self.arm()
        self.assertIn("days to expiry", mechanism.audit(on, self.arm(dte=30)))
        self.assertIn("moneyness", mechanism.audit(on, self.arm(moneyness=-0.05)))
        other = mechanism.profile([{**trade(i, f"d{i}", 1.0), "type": "iron_condor"} for i in range(12)])
        self.assertIn("never traded the signal's structure", mechanism.audit(on, other))
        late = mechanism.profile([{**trade(i, f"d{i}", 1.0), "entry_minute": 900} for i in range(12)])
        self.assertIn("entry minute", mechanism.audit(on, late))
        wide = mechanism.profile([{**trade(i, f"d{i}", 1.0), "legs": [{"strike": 95.0}, {"strike": 105.0}]} for i in range(12)])
        self.assertIn("width", mechanism.audit(on, wide))
        self.assertIsNone(mechanism.audit(on, {"trades": 0}), "nothing to judge")

    def test_trim_keeps_what_the_test_reads(self):
        full = {**result("x"), "trades": [trade(i, f"2023-05-{i + 1:02d}", 2.0) for i in range(3)],
                "runtime": {"messages": [f"m{i}" for i in range(6)]}}
        kept = mechanism.trim(full)
        self.assertNotIn("daily", kept)
        self.assertEqual(len(kept["runtime"]["messages"]), 4)
        self.assertNotIn("legs", kept["trades"][0])
        self.assertEqual(mechanism.profile(kept["trades"]), mechanism.profile(full["trades"]), "the audit reads either")
        self.assertEqual(mechanism.day_returns(kept["trades"]), mechanism.day_returns(full["trades"]))
        self.assertEqual((kept["run_id"], kept["trials"]), (full["run_id"], full["trials"]))

    def test_the_shadow_sample_is_a_fixed_share_of_family_ids(self):
        ids = [f"family-{i}" for i in range(2000)]
        share = sum(mechanism.in_sample(f, 0.25) for f in ids) / len(ids)
        self.assertTrue(0.22 < share < 0.28, share)
        self.assertEqual([mechanism.in_sample(f, 0.25) for f in ids[:50]], [mechanism.in_sample(f, 0.25) for f in ids[:50]])
        self.assertTrue(all(mechanism.in_sample(f, 1.0) for f in ids[:50]))
        self.assertFalse(any(mechanism.in_sample(f, 0.0) for f in ids[:50]))

    def test_an_arm_the_gym_failed_is_infrastructure_not_a_verdict(self):
        dead = {"status": "error", "reason": "the worker died (exit -9)", "runtime": {"messages": ["the worker died (exit -9)"]}}
        late = {"status": "error", "reason": "the unit timed out after 1800 s and its worker was killed"}
        own = {"status": "error", "reason": "ZeroDivisionError: division by zero"}
        self.assertEqual([mechanism.infrastructure(r) for r in (dead, late, own, {"status": "ok"})], [True, True, False, False])

    def test_calibration_says_what_the_gate_would_have_missed(self):
        rows = [{"verdict": "passed", "eligible": True}] * 3 + [{"verdict": "failed", "eligible": True}] + \
               [{"verdict": "failed", "eligible": False}] * 5 + [{"verdict": "thin", "eligible": False}]
        cal = mechanism.calibration(rows)
        self.assertEqual((cal["tested"], cal["eligible"], cal["missed"], cal["blocked"]), (10, 4, 0.25, 0.7))


class Benchmark(unittest.TestCase):
    """The noise bound's justification (the module docstring's table): the signal on 15% of the sample's days, the
    comparison every other day, no cost drag (the hardest case for a real signal). Fixed seeds: the rates are pinned."""

    def rate(self, t_year: float | None, n_days: int = 252, min_t: float = 0.75, reps: int = 1200, seed: int = 11) -> float:
        rng = random.Random(seed)
        delta = 0.0 if t_year is None else t_year / math.sqrt(252 * 0.15)
        passed = n = 0
        for _ in range(reps):
            on, off = {}, {}
            for d in range(n_days):
                base = rng.gauss(0.0, 1.0)
                if rng.random() < 0.15:
                    on[d] = base + delta
                    off[d] = base + delta  # the comparison trades that day too, the same trade
                else:
                    off[d] = base
            v = mechanism.compare(on, off, min_t=min_t)
            if v["verdict"] in ("passed", "failed"):
                n += 1
                passed += v["verdict"] == "passed"
        return passed / n

    def test_this_sample_cuts_false_passes_and_missed_signals_against_the_first_design(self):
        first_null, first_t2 = self.rate(None, 125, 0.5), self.rate(2.0, 125, 0.5)
        null, t2 = self.rate(None), self.rate(2.0)
        long_null, long_t2 = self.rate(None, 165), self.rate(2.0, 165)
        self.assertLess(null, first_null)
        self.assertLess(null, 0.28, "a signal with no information reaches broad replay about a quarter of the time")
        self.assertGreater(t2, first_t2)
        self.assertGreater(t2, 0.83, "a signal at the validation line's t 2 a year passes most of the time")
        self.assertLess(long_null, 0.28)
        self.assertGreater(long_t2, 0.75, "holds of more than ten sessions count about 165 days")

    def test_retries_rise_and_a_real_signal_after_failed_versions_still_passes(self):
        cfg = mechanism.config({})
        bounds = [mechanism.bound(cfg, k) for k in range(3)]
        self.assertEqual(bounds, [0.75, 1.0, 1.25])
        through = lambda ps: 1 - math.prod(1 - p for p in ps)  # noqa: E731 - three independent tries
        null = [self.rate(None, min_t=b, reps=800) for b in bounds]
        self.assertLess(through(null), 0.5, "retries do not walk a signal with no information through")
        first_design_null = [self.rate(None, 125, b, reps=800) for b in (0.5, 1.0, 1.5)]
        self.assertLess(through(null), through(first_design_null))
        # Review of #446: a real signal arriving as the THIRD version, after two failed versions of the same hypothesis,
        # meets the bound of two failures. The first design passed it 42% of the time.
        third, first_design_third = self.rate(2.0, min_t=bounds[2], reps=800), self.rate(2.0, 125, 1.5, reps=800)
        self.assertLess(first_design_third, 0.5)
        self.assertGreater(third, 0.68)
        self.assertGreater(self.rate(2.0, 165, bounds[2], reps=800), 0.57)


class MechPool:
    """The pool's submit/wait interface with scripted answers: `answer(job)` makes each result, `fail(job)` a PoolError."""

    def __init__(self, answer, fail=None):
        self.jobs = []
        self.answer = answer
        self.fail = fail or (lambda job: None)

    def submit(self, job):
        self.jobs.append(job)
        return job

    def wait(self, job, timeout=None, *, late=None, late_fail=None):
        why = self.fail(job)
        if why:
            raise PoolError(why)
        job.batch = {"wall_seconds": 4.0, "programs_in_batch": 2}
        return self.answer(job)

    def run(self, job, timeout=None, late=None):
        return self.wait(self.submit(job), timeout, late=late)

    def cancel_family(self, fid):
        pass

    def by(self, purpose):
        return [j for j in self.jobs if j.purpose == purpose]


class ResearcherTest(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.settings["population"]["floor"] = 0
        self.shadow()  # every family in the shadow sample here (`sample` has its own test)
        self.fid = self.born("late-sell-rebound", CARD)
        self.edge = 0.4  # the signal's advantage per entry day, in daily return on maximum loss
        self.off_trades = True
        self.off_context: dict = {}
        self.broken = lambda job: False  # an arm the Gym fails for its own reasons (a dead worker)
        self.broken_reason = "the worker died (exit -9)"
        self.probe_trades = 40  # the zero-trade probe's answer (0: no trade in the probe year, so no broad run)
        self.pool = MechPool(self.answer)

    def born(self, fid: str, card: dict, structure: str = "debit_vertical", **kw) -> str:
        spec = {"id": fid, "mechanism": card["hypothesis"], "structure": structure, "roots": ["SPY"], "dte": [0, 5],
                "rejection": "no edge", "card_sha": cards.card_sha(card)}
        fam = self.store.add_family(spec, origin=kw.pop("origin", "architect"), **kw)
        if kw.get("parent") is None:
            cards.put(self.store, fam["id"], card, structure)
        return fam["id"]

    def gate(self, **extra):
        self.settings["researcher"]["mechanism_test"] = {"mode": "gate", **extra}

    def shadow(self, **extra):
        self.settings["researcher"]["mechanism_test"] = {"mode": "shadow", "sample": 1.0, **extra}

    def answer(self, job):
        """Signal on: 6 entry days a window, returning `edge` over the comparison; off: those days and 14 more at 0."""
        if job.purpose == "probe":
            return result(job.name, roots=job.roots, trades=self.probe_trades)
        r = result(job.name, roots=job.roots)
        if job.purpose != "mechanism":
            return r
        if self.broken(job):
            return {"program": job.name, "status": "error", "reason": self.broken_reason, "trials": 0, "summary": {},
                    "trades": [], "runtime": {"messages": [self.broken_reason]}}
        on = bool(job.params.get("signal_on", 1))
        rows = [trade(i, d, (0.1 + self.edge + 0.02 * (i % 3)) * 50.0) for i, d in enumerate(trade_days(job.start, 6))]
        if not on:
            rows = [{**t, "pnl": 5.0 + 1.0 * (t["id"] % 3)} for t in rows] if self.off_trades else []
            if self.off_trades:
                rows += [trade(100 + i, d, (0.1 + 0.02 * (i % 3)) * 50.0) for i, d in enumerate(trade_days(job.start, 14, offset=6))]
            rows = [{**t, "context": {**t["context"], **self.off_context}} for t in rows]
        r["trades"] = rows
        return r

    def run_(self, code=CODE, fid=None, **args):
        out: dict = {"tool_calls": 0}
        view = self.researcher()._gym_run(self.store.family(fid or self.fid), {"code": code, **args}, out, author="synthetic")
        return view, out

    def rows(self, window, fid=None):
        return self.store._all("SELECT * FROM runs WHERE family=? AND window=?", (fid or self.fid, window))

    def purposes(self):
        """The jobs asked of the Gym, robustness runs aside (a new best queues them, as ever)."""
        return [j.purpose for j in self.pool.jobs if j.purpose != "robustness"]

    def evidence(self, fid=None):
        return cards.evidence(self.store, fid or self.fid, kind="mechanism_test")

    def seen(self, view, fid=None) -> str:
        """Everything the researcher can read about the family after a run: the run's view, its status line, its notebook."""
        fam = self.store.family(fid or self.fid)
        notes = [n["text"] for n in self.store.notebook(fid or self.fid, limit=50)]
        return json.dumps(view, default=str) + "\n" + self.researcher().status(fam) + "\n" + "\n".join(notes)

    # ------------------------------------------------------------------ shadow (the default)
    def test_shadow_records_a_blind_verdict_and_never_stops_the_run(self):
        self.edge = -0.05
        view, out = self.run_()
        self.assertEqual(self.purposes(), ["mechanism"] * 8 + ["train"], "the test, then the broad run whatever it said")
        self.assertEqual(view["status"], "ok")
        self.assertEqual(set(view["mechanism_test"]), {"mode", "recorded", "note"})
        self.assertTrue(view["mechanism_test"]["recorded"])
        self.assertIn("withheld", view["mechanism_test"]["note"])
        [ev] = self.evidence()
        self.assertEqual((ev["verdict"], ev["detail"]["mode"], ev["detail"]["bound"], ev["detail"]["blind"],
                          ev["detail"]["exposed"]), ("failed", "shadow", 0.75, True, False))
        self.assertEqual(out["mechanism_test"]["verdict"], "failed", "the cycle's event (the operator's record) carries it")
        self.assertEqual(self.store.family(self.fid)["trials"], 9, "every arm is a trial in shadow too")
        seen = self.seen(view)  # review of #446: the researcher never sees a shadow verdict (the view, the status, the notebook)
        for words in (ev["detail"]["why"], f"t {ev['detail']['t']:+.2f}", "Mechanism test of version", "mechanism_failed",
                      '"verdict"'):
            self.assertNotIn(words, seen)
        self.assertIn("withheld", self.researcher().mechanism_text(self.store.family(self.fid)))
        self.pool.jobs.clear()
        self.run_(params={"threshold": 590})
        self.assertEqual(self.purposes(), ["train"], "one test a family in shadow")
        self.assertFalse(self.store.family(self.fid)["retired_at"])

    def test_a_passing_and_a_failing_shadow_test_look_the_same_to_the_researcher(self):
        self.settings["researcher"]["probe_year"] = 2022
        views = []
        for edge, fid in ((0.4, self.fid), (-0.05, self.born("rebound-b", {**CARD, "hypothesis": CARD["hypothesis"] + " B."}))):
            self.edge = edge
            self.pool.jobs.clear()
            view, _ = self.run_(fid=fid)
            views.append((view["mechanism_test"], self.researcher().mechanism_text(self.store.family(fid)), self.purposes()))
        self.assertEqual([e["verdict"] for f in (self.fid, "rebound-b") for e in self.evidence(f)], ["passed", "failed"])
        self.assertEqual(views[0], views[1], "the same view, status and jobs (the probe runs either way) whatever the verdict")

    def eligible(self, fid):
        """Mark every Train row of a family eligible (its outcome is known: it reached an eligible Train version)."""
        for r in self.store._all("SELECT run_id, summary FROM runs WHERE family=? AND window='train'", (fid,)):
            s = json.loads(r["summary"] or "{}")
            self.store._exec("UPDATE runs SET summary=? WHERE run_id=?", (json.dumps({**s, "train_eligible": True}), r["run_id"]))

    def test_shadow_skips_a_run_that_cannot_take_the_test_and_tests_the_next_before_any_broad_run(self):
        self.settings["researcher"]["probe_year"] = 2022
        self.probe_trades = 0  # no trade in the probe year: the broad run is skipped, so nothing is fitted to Train yet
        view, out = self.run_(code=NO_SWITCH)
        self.assertEqual((view["status"], self.purposes()), ("disqualified", ["probe"]))
        self.assertIn("not in PARAMS", out["mechanism_test"]["skipped"])
        self.assertNotIn("mechanism_test", view)
        self.run_(params={"signal_on": 0})  # a placebo first (review of #446): skipped, never recorded untestable
        self.assertEqual((self.purposes(), self.evidence()), (["probe", "probe"], []))
        self.assertFalse(self.researcher().mechanism_lineage(self.fid)["broad"])
        self.pool.jobs.clear()
        self.probe_trades = 40
        self.run_(params={"threshold": 590})
        self.assertEqual(self.purposes(), ["mechanism"] * 8 + ["probe", "train"],
                         "the first run that can take the test takes it while the family has no broad run")
        [ev] = self.evidence()
        self.assertEqual((ev["verdict"], ev["detail"]["exposed"]), ("passed", False))

    def test_p1_shadow_never_tests_a_program_already_replayed_broadly_on_train(self):
        """Review of #446 (P1): a first version without the switch (or with the signal off) runs broad Train in shadow; a
        later version's test would be on a program already fitted to Train, which the gate would never test, so it is not
        made and never enters the calibration."""
        view, out = self.run_(code=NO_SWITCH)
        self.assertEqual((view["status"], self.purposes()), ("ok", ["train"]))
        self.eligible(self.fid)  # eligible on Train before any test
        self.pool.jobs.clear()
        view, out = self.run_(params={"threshold": 590})
        self.assertEqual((self.purposes(), self.evidence()), (["train"], []), "exposed: no test, no trial")
        self.assertNotIn("mechanism_test", view, "nothing is said: whether broad runs exist reads no verdict")
        self.assertEqual(self.researcher().mechanism_text(self.store.family(self.fid)), "", "no test is promised either")
        placebo = self.born("placebo-first", {**CARD, "hypothesis": CARD["hypothesis"] + " Placebo first."})
        self.pool.jobs.clear()
        self.run_(fid=placebo, params={"signal_on": 0})
        self.run_(fid=placebo, params={"threshold": 590})
        self.assertEqual((self.purposes(), self.evidence(placebo)), (["train", "train"], []))
        self.eligible(placebo)
        self.assertEqual(mechanism.calibration_rows(self.store), [])

    def test_p2_a_fork_of_a_broadly_replayed_card_is_never_tested_in_shadow(self):
        """Review of #446 (P2): a tournament fork reads its parent's card and runs its parent's validated program; the
        lineage already has broad Train runs with that card, so neither mode tests it and only the parent is a row."""
        self.run_()  # the parent: a blind test, then the broad run
        child = self.born("late-sell-rebound-fork", CARD, parent=self.fid, origin="fork")
        lineage = self.researcher().mechanism_lineage(child)
        self.assertEqual((lineage["broad"], lineage["own"]), (True, 0))
        self.pool.jobs.clear()
        self.run_(fid=child)
        self.assertEqual((self.purposes(), self.evidence(child)), (["train"], []))
        self.eligible(self.fid)
        self.eligible(child)
        self.assertEqual([(r["family"], r["verdict"]) for r in mechanism.calibration_rows(self.store)], [(self.fid, "passed")])
        self.gate()
        self.assertIsNone(self.researcher()._mechanism_plan(self.store.family(child), CODE, {"threshold": 580}),
                          "the gate would not test it either")

    def test_a_broad_run_that_lands_while_the_arms_run_marks_the_test_exposed(self):
        """A test that began unexposed but whose lineage's card got a broad Train run before it was recorded (a fork's
        parent, a late result) records `exposed` and is never a calibration row."""
        child = self.born("late-sell-rebound-fork", CARD, parent=self.fid, origin="fork")
        answer = self.answer

        def landing(job):
            if job.family == child and job.purpose == "mechanism" and not self.rows("train"):
                self.store.add_run(self.fid, None, result("parent-late", roots=("SPY",)), window="train", stress=1.0,
                                   purpose="train")
            return answer(job)

        self.pool.answer = landing
        self.run_(fid=child)
        [ev] = self.evidence(child)
        self.assertEqual((ev["detail"]["blind"], ev["detail"]["exposed"]), (True, True))
        self.eligible(child)
        self.assertEqual(mechanism.calibration_rows(self.store), [])
        self.pool.jobs.clear()
        self.run_()
        self.assertEqual((self.purposes(), self.evidence()), (["train"], []), "the parent is exposed now too")

    def test_shadow_tests_only_its_sample(self):
        self.shadow(sample=0.0)
        self.run_()
        self.assertEqual((self.purposes(), self.evidence()), (["train"], []))
        self.assertEqual(self.researcher().mechanism_text(self.store.family(self.fid)), "")
        self.gate(sample=0.0)
        self.fid = self.born("gated", {**CARD, "hypothesis": CARD["hypothesis"] + " Gated."})
        self.pool.jobs.clear()
        self.run_()
        self.assertEqual(self.purposes(), ["mechanism"] * 8 + ["train"], "the gate tests every carded family")

    def test_shadow_calibration_reads_the_first_blind_verdict_and_the_train_outcome(self):
        self.edge = -0.05
        self.run_()
        self.store.retire_gym(self.fid, "Retired by the idle rule", floor=0, source="test")
        self.gate()
        young = self.born("still-researching", {**CARD, "hypothesis": CARD["hypothesis"] + " Still researching."})
        self.run_(fid=young)
        rows = mechanism.calibration_rows(self.store)
        self.assertEqual([(r["family"], r["verdict"]) for r in rows], [(self.fid, "failed")],
                         "a family still researching (no eligible run, not retired) is not counted yet")
        self.assertEqual(mechanism.calibration(rows)["tested"], 1)
        self.store.retire_gym(young, "Retired by the idle rule", floor=0, source="test")
        self.assertEqual([r["family"] for r in mechanism.calibration_rows(self.store)], [self.fid],
                         "a gate verdict was seen and stopped the replay: never a calibration row")

    # ------------------------------------------------------------------ gate
    def test_a_pass_opens_broad_replay_and_every_arm_is_a_trial(self):
        self.gate()
        view, out = self.run_()
        mech = self.pool.by("mechanism")
        w = mechanism.sample_windows()
        self.assertEqual(len(mech), 2 * len(w), "one job a pre-registered window and arm")
        self.assertEqual({(j.split, j.window, j.stress) for j in mech}, {(1, "train", 1.0)})
        self.assertEqual(sorted({(j.start, j.end) for j in mech}), sorted(w))
        self.assertEqual([j.start for j in mech[:2]], [w[0][0]] * 2, "the first window runs first, alone")
        self.assertEqual(sorted({j.params.get("signal_on", 1) for j in mech}), [0, 1])
        self.assertEqual(self.purposes()[-1], "train", "the broad run follows the pass")
        self.assertEqual((view["status"], view["mechanism_test"]["verdict"]), ("ok", "passed"))
        self.assertEqual((len(self.rows("mechanism")), len(self.rows("train"))), (2 * len(w), 1))
        self.assertEqual(self.store.family(self.fid)["trials"], 2 * len(w) + 1, "every arm-window and the broad run: each a trial")
        self.assertEqual(out["mechanism_test"]["box_seconds"], 2.0 * 2 * len(w), "the cost measure: each job's share of its batch")
        [ev] = self.evidence()
        self.assertEqual((ev["verdict"], ev["version"], ev["card_sha"]), ("passed", 1, cards.card_sha(CARD)))
        self.assertEqual(ev["detail"]["profiles"]["on"]["types"], ["debit_vertical"])
        self.assertEqual((ev["detail"]["hurdle"], ev["detail"]["net_positive"]), (0.08, True))
        self.assertTrue(self.researcher().mechanism_passed(self.store.family(self.fid)))
        self.pool.jobs.clear()
        self.run_(params={"threshold": 590})
        self.assertEqual(self.purposes(), ["train"], "once passed, no more tests")
        self.assertIn("passed", self.researcher().mechanism_text(self.store.family(self.fid)))

    def test_arms_are_stored_trimmed(self):
        self.gate()
        self.run_()
        row = self.rows("mechanism")[0]
        kept = self.store.run_result(row["run_id"])
        self.assertNotIn("daily", kept)
        self.assertNotIn("legs", kept["trades"][0])
        self.assertIn("moneyness", kept["trades"][0])
        self.assertIn(json.loads(row["summary"])["arm"], ("on", "off"))

    def test_a_failed_test_blocks_broad_replay_and_three_hard_failures_retire_with_the_mechanism_verdict(self):
        self.gate()
        self.edge = -0.05
        view, out = self.run_()
        self.assertEqual(view["status"], "mechanism_failed")
        self.assertEqual(self.pool.by("train"), [], "no broad replay")
        self.assertEqual(out["trials"], 8)
        self.assertEqual(self.researcher().mechanism_record(self.store.family(self.fid))["failed"], [1])
        self.pool.jobs.clear()
        again, out2 = self.run_()
        self.assertEqual((self.pool.jobs, again.get("already_run")), ([], "the stored result"), "the same test is not run twice")
        self.assertEqual(out2.get("trials", 0), 0)
        self.run_(params={"threshold": 590})
        last, _ = self.run_(params={"threshold": 580})
        self.assertEqual([e["detail"]["bound"] for e in self.evidence()], [0.75, 1.0, 1.25], "the bound rises with each failure")
        fam = self.store.family(self.fid)
        self.assertTrue(fam["retired_at"], "three failed tests below the base bound retire it")
        self.assertIn(mechanism.MARK, fam["retire_reason"])
        self.assertEqual(tag_of(self.store._one("SELECT * FROM graveyard WHERE family=?", (self.fid,)), fam), "MECHANISM")
        self.assertIn("MECHANISM", str(last.get("retired")))

    def test_a_verdict_that_is_not_a_hard_failure_never_retires_a_lineage_member(self):
        """Review of #446 (probe A): the parent's card holds three hard failures; a fork's first test is invalid."""
        self.gate()
        self.edge = -0.05
        self.run_()
        self.run_(params={"threshold": 590})
        self.run_(params={"threshold": 580})
        self.assertTrue(self.store.family(self.fid)["retired_at"])
        child = self.born("late-sell-rebound-child", CARD, parent=self.fid, origin="fork")
        self.off_trades = False
        view, _ = self.run_(fid=child)
        self.assertEqual(([e["verdict"] for e in self.evidence(child)], view["status"]), (["invalid_ablation"], "mechanism_invalid"))
        self.assertFalse(self.store.family(child)["retired_at"], "an untested verdict is never a MECHANISM finding")

    def test_a_rebirth_failed_only_by_its_raised_bound_stays_alive(self):
        """Review of #446 (probe B): a rebirth (a new input, another card) in the dead card's lineage and cell meets the
        bound its hypothesis's failures raised; failing it above the base bound is not a finding, and the dead card's hard
        failures never count toward the rebirth's retirement."""
        self.gate()
        self.edge = -0.05
        self.run_()
        self.run_(params={"threshold": 590})
        self.run_(params={"threshold": 580})
        reborn = {**CARD, "inputs": ["clock", "option_liquidity", "underlying_price"],
                  "hypothesis": CARD["hypothesis"] + " Dealer inventory imbalance decides which rebounds complete."}
        child = self.born("rebound-reborn", reborn, parent=self.fid, origin="architect")
        cards.put(self.store, child, reborn, "debit_vertical")  # born() stores no card when a parent is given
        self.assertEqual(self.researcher().mechanism_lineage(child)["failed"], 3, "the same hypothesis: the bound rises")
        real = mechanism.compare

        def between(on, off, *, min_t=0.75, min_on_days=10, min_off_days=10):
            out = real(on, off, min_t=min_t, min_on_days=min_on_days, min_off_days=min_off_days)
            return mechanism._finish(out, diff=0.01, t=1.0, min_t=min_t, method="welch", what="the comparison's")

        with mock.patch.object(mechanism, "compare", between):
            self.edge = 0.4
            self.run_(fid=child)
        [ev] = self.evidence(child)
        self.assertEqual((ev["verdict"], ev["detail"]["bound"], ev["detail"]["below_base"]), ("failed", 1.5, False))
        self.assertFalse(self.store.family(child)["retired_at"], "failed only by the raised bound: never a finding")
        self.edge = -0.05
        self.run_(fid=child, params={"threshold": 590})
        self.assertEqual(self.researcher().mechanism_lineage(child)["hard"], 1, "only its own card's hard failures")
        self.assertFalse(self.store.family(child)["retired_at"])

    def test_disjoint_inputs_in_the_lineage_do_not_raise_the_bound(self):
        self.gate()
        self.edge = -0.05
        self.run_()
        skew = {**CARD, "inputs": ["iv_skew"], "hypothesis": "Put skew overprices crash protection after calm weeks, so the "
                                                              "wing seller is paid for bearing it through the next sessions."}
        child = self.born("skew-idea", skew, parent=self.fid, origin="architect")
        cards.put(self.store, child, skew, "debit_vertical")
        self.assertEqual(self.researcher().mechanism_lineage(child)["failed"], 0, "another information set: another hypothesis")

    def test_a_lineage_cards_inputs_include_those_its_own_words_name(self):
        """Review of #446 (P4, the lineage side): a lineage family whose card under-declares its inputs (skew only) while
        its hypothesis reads the close is the same hypothesis as ours: its failed test raises our bound."""
        self.gate()
        under = {**CARD, "inputs": ["iv_skew"]}  # the same words as CARD, which name the close and the late-day selling
        parent = self.born("under-declared", under)
        self.edge = -0.05
        self.run_(fid=parent)
        self.assertEqual([e["verdict"] for e in self.evidence(parent)], ["failed"])
        child = self.born("price-only", {**CARD, "inputs": ["underlying_price"]}, parent=parent, origin="architect")
        cards.put(self.store, child, {**CARD, "inputs": ["underlying_price"]}, "debit_vertical")
        self.assertEqual(self.researcher().mechanism_lineage(child)["failed"], 1)

    def test_a_worker_that_died_is_a_gym_error_and_its_arm_is_run_again(self):
        """Review of #446: an arm the Gym failed for its own reasons is never a verdict, and never reused."""
        self.gate()
        self.broken = lambda job: job.params.get("signal_on") == 0 and job.start == mechanism.sample_windows()[0][0]
        view, out = self.run_()
        self.assertEqual((view["status"], self.evidence()), ("gym_error", []))
        self.assertIn("worker died", out["gym_error"])
        self.broken = lambda job: False
        self.pool.jobs.clear()
        view, _ = self.run_()
        self.assertEqual(len([j for j in self.pool.by("mechanism") if j.params.get("signal_on") == 0
                              and j.start == mechanism.sample_windows()[0][0]]), 1, "the errored arm runs again")
        self.assertEqual(view["mechanism_test"]["verdict"], "passed")

    def test_p3_the_same_gym_failure_three_times_in_a_row_is_the_programs(self):
        """Review of #446 (P3): a program that kills its worker every time (a runaway in C code, a segfault) was a Gym error
        at every version for ever in gate mode. The same infrastructure failure three times in a row in the family's tests
        is the program's: the signal arm erred, the test is untestable, and four such versions retire it with the idle
        rule's words."""
        self.gate()
        self.broken = lambda job: job.params.get("signal_on", 1) == 1
        statuses = []
        for k in range(6):
            self.pool.jobs.clear()
            view, out = self.run_(params={"threshold": 600 - k})
            statuses.append(view.get("status"))
            if k == 1:
                rec = self.researcher().mechanism_record(self.store.family(self.fid))
                self.assertEqual((rec["infra"]["kind"], rec["infra"]["n"]), ("the worker died (exit -9)", 2))
        self.assertEqual(statuses, ["gym_error", "gym_error"] + ["mechanism_untestable"] * 4)
        evidence = self.evidence()
        self.assertEqual([e["verdict"] for e in evidence], ["untestable"] * 4)
        self.assertEqual(evidence[0]["detail"]["infrastructure"], {"kind": "the worker died (exit -9)", "in_a_row": 3})
        self.assertIn("3 times in a row", evidence[0]["detail"]["why"])
        self.assertEqual(len(self.pool.by("mechanism")), 2, "the first window only: the others never ran")
        fam = self.store.family(self.fid)
        self.assertTrue(fam["retired_at"])
        self.assertEqual(tag_of(self.store._one("SELECT * FROM graveyard WHERE family=?", (self.fid,)), fam), "IDLE")
        self.assertEqual(self.rows("train"), [], "no broad run in gate mode")

    def test_another_failure_or_a_test_that_ran_starts_the_count_again(self):
        self.gate()
        self.broken = lambda job: job.params.get("signal_on", 1) == 1
        for k, why in enumerate(("the worker died (exit -9)", "the worker died (exit -9)", "the worker died (exit -11)",
                                 "the unit timed out after 1800 s and its worker was killed",
                                 "the unit timed out after 2400 s and its worker was killed")):
            self.broken_reason = why
            view, _ = self.run_(params={"threshold": 600 - k})
            self.assertEqual(view["status"], "gym_error", why)
        rec = self.researcher().mechanism_record(self.store.family(self.fid))
        self.assertEqual((rec["infra"]["kind"], rec["infra"]["n"]), ("the unit timed out", 2), "a timeout's seconds are not its identity")
        self.broken = lambda job: False
        view, _ = self.run_(params={"threshold": 590})
        self.assertEqual(view["mechanism_test"]["verdict"], "passed")
        self.assertNotIn("infra", self.researcher().mechanism_record(self.store.family(self.fid)), "a test that ran ends the run")

    def test_a_shadow_gym_error_is_never_asked_again_once_the_broad_run_exposed_the_program(self):
        """Shadow never stops the broad run, so after a Gym error the family is exposed to Train and its test is not made
        again at later versions (review of #446, P3's shadow half): no core is tied up at every version."""
        self.broken = lambda job: job.params.get("signal_on", 1) == 1
        view, out = self.run_()
        self.assertEqual((view["status"], view["mechanism_test"]["recorded"]), ("ok", False))
        self.assertNotIn("runs again", view["mechanism_test"]["note"])
        self.assertEqual(out["mechanism_test"]["infrastructure"], {"kind": "the worker died (exit -9)", "in_a_row": 1})
        for k in range(3):
            self.pool.jobs.clear()
            view, _ = self.run_(params={"threshold": 590 - k})
            self.assertEqual((view["status"], self.purposes()), ("ok", ["train"]))
        self.assertEqual(self.evidence(), [])

    def test_a_failure_only_the_raised_bound_made_never_counts_toward_retirement(self):
        self.gate(min_t=0.5, step_t=10000.0)  # the second test's bound is out of reach
        self.edge = -0.05
        self.run_()
        self.edge = 0.4
        self.run_(params={"threshold": 590})
        self.run_(params={"threshold": 580})
        verdicts = [(e["verdict"], e["detail"].get("below_base")) for e in self.evidence()]
        self.assertEqual(verdicts, [("failed", True), ("failed", False), ("failed", False)])
        self.assertFalse(self.store.family(self.fid)["retired_at"], "a real signal blocked by a raised bound is not a finding")

    def test_programs_that_cannot_take_the_test_are_refused_before_any_version(self):
        self.gate()
        view, out = self.run_(code=NO_SWITCH)
        self.assertEqual(view["status"], "refused")
        self.assertIn("ablation switch 'signal_on' is not in PARAMS", view["reason"])
        view, _ = self.run_(params={"signal_on": 0})
        self.assertIn("this run has the signal off", view["reason"])
        self.assertEqual((self.pool.jobs, self.store.versions(self.fid)), ([], []))
        self.assertEqual(out["run_refused"], 1)

    def test_a_boolean_switch_gets_a_boolean_ablation(self):
        self.run_(code=BOOL_SWITCH)
        self.assertEqual(sorted({repr(j.params.get("signal_on", True)) for j in self.pool.by("mechanism")}), ["False", "True"])

    def test_an_ablation_that_does_not_trade_stops_after_the_first_window(self):
        self.gate()
        self.off_trades = False
        view, _ = self.run_()
        self.assertEqual(view["status"], "mechanism_invalid")
        self.assertIn("trade the comparison strategy", view["next"])
        self.assertEqual(len(self.pool.by("mechanism")), 2, "the other three windows never ran")
        rec = self.researcher().mechanism_record(self.store.family(self.fid))
        self.assertEqual((rec.get("failed"), rec["untestable"]), (None, [1]))

    def test_an_ablation_that_trades_something_else_is_invalid(self):
        self.gate()
        self.off_context = {"dte": 30}
        view, _ = self.run_()
        self.assertEqual(view["status"], "mechanism_invalid")
        self.assertIn("days to expiry", view["mechanism_test"]["why"])
        [ev] = self.evidence()
        self.assertEqual(ev["detail"]["profiles"]["off"]["dte"], 30.0, "both profiles are kept for a later audit")

    def test_only_a_time_of_day_card_skips_the_entry_minute_check(self):
        """Review of #446: declaring the clock alone skipped the entry-minute audit, and in gate mode the researcher writes
        the ablation. Only a card whose class is calendar_flow or whose hypothesis names a time-of-day condition skips it,
        and the detail records what was skipped."""
        self.gate()
        answer = self.answer

        def later(job):  # the comparison enters five hours after the signal
            r = answer(job)
            if job.purpose == "mechanism" and job.params.get("signal_on") == 0:
                r["trades"] = [{**t, "entry_minute": 900} for t in r["trades"]]
            return r

        self.pool.answer = later
        view, _ = self.run_()  # CARD: "late in the day", with the clock among its inputs
        [ev] = self.evidence()
        self.assertEqual((ev["verdict"], ev["detail"]["audit_skipped"]), ("passed", ["minute"]))
        plain = {**CARD, "hypothesis": "Liquidity-demanding sellers push price below value and patient buyers are paid to "
                                       "absorb it over the next session."}
        self.fid = self.born("clock-declared-only", plain)
        view, _ = self.run_()
        [ev] = self.evidence()
        self.assertEqual((view["status"], ev["detail"]["audit_skipped"]), ("mechanism_invalid", []))
        self.assertIn("entry minute", ev["detail"]["why"])
        self.fid = self.born("calendar-card", {**plain, "mechanism_class": "calendar_flow",
                                               "hypothesis": plain["hypothesis"] + " Calendar."})
        view, _ = self.run_()
        self.assertEqual(self.evidence()[0]["detail"]["audit_skipped"], ["minute"])
        self.assertEqual(mechanism.clock_skips({**CARD, "inputs": ["underlying_price"]}), frozenset(), "no clock input")

    def test_untestable_versions_retire_with_the_idle_words(self):
        self.gate()
        self.off_trades = False
        for k in range(4):
            last, _ = self.run_(params={"threshold": 600 - k})
        fam = self.store.family(self.fid)
        self.assertTrue(fam["retired_at"])
        self.assertIn("time limit, not a finding", fam["retire_reason"])
        self.assertEqual(tag_of(self.store._one("SELECT * FROM graveyard WHERE family=?", (self.fid,)), fam), "IDLE")

    def test_sweeps_wait_for_a_pass_in_gate_mode_only(self):
        def sweep():
            out: dict = {"tool_calls": 0}
            return self.researcher()._gym_sweep(self.store.family(self.fid), {"code": CODE, "variants": [{"threshold": 590},
                                                                                                        {"threshold": 580}]},
                                                out, author="synthetic")
        self.gate()
        self.assertIn("mechanism test has not passed", sweep()["reason"])
        self.assertEqual(self.pool.jobs, [])
        self.shadow()
        self.assertNotIn("mechanism test has not passed", str(sweep().get("reason")))

    def test_a_one_and_a_half_x_run_takes_the_test_first(self):
        self.gate()
        view, _ = self.run_(stress=1.5)
        self.assertEqual(self.purposes(), ["mechanism"] * 8 + ["train"])
        self.assertEqual({j.stress for j in self.pool.by("mechanism")}, {1.0}, "the test is at the normal spread")
        self.assertEqual(self.pool.by("train")[0].stress, 1.5)
        self.edge = -0.05
        self.fid = self.born("late-sell-rebound-2", {**CARD, "hypothesis": CARD["hypothesis"] + " A second family."})
        self.pool.jobs.clear()
        view, _ = self.run_(stress=1.5)
        self.assertEqual((view["status"], self.pool.by("train")), ("mechanism_failed", []),
                         "a 1.5x run is broad replay: it waits for a pass too (review of #446)")

    def test_a_gym_error_keeps_the_landed_arms_and_reuses_them(self):
        self.gate()
        self.pool.fail = lambda job: "the Gym did not answer" if job.params.get("signal_on") == 0 and job.start[5:7] == "05" else None
        view, out = self.run_()
        self.assertEqual(view["status"], "gym_error")
        self.assertEqual(len(self.rows("mechanism")), 7)
        self.pool.fail = lambda job: None
        self.pool.jobs.clear()
        view, _ = self.run_()
        self.assertEqual(len(self.pool.by("mechanism")), 1, "only the arm that never landed runs again")
        self.assertEqual(view["mechanism_test"]["verdict"], "passed")

    def test_missing_data_drops_a_window_and_is_never_a_gym_error(self):
        self.gate()
        first = mechanism.sample_windows()[0][0]
        self.pool.fail = lambda job: "the Gym is missing data: no train days for SPY" if job.start == first else None
        view, out = self.run_()
        self.assertNotIn("gym_error", out)
        self.assertEqual((view["status"], view["mechanism_test"]["verdict"]), ("ok", "passed"), "the other windows decide")
        self.fid = self.born("no-data-anywhere", {**CARD, "hypothesis": CARD["hypothesis"] + " On a root with no data."})
        self.pool.fail = lambda job: "the Gym has no train data for SPY yet (it holds QQQ)"
        view, out = self.run_()
        self.assertNotIn("gym_error", out)
        self.assertEqual(view["status"], "mechanism_untestable", "recorded, not asked again every cycle")
        self.assertEqual(self.evidence()[0]["verdict"], "untestable")

    def test_a_pass_is_the_lineages_and_holds_on_a_new_gym(self):
        self.gate()
        self.pool.image = lambda kind: "img-1"
        self.pool.bundle = lambda: "bundle-1"
        self.run_()
        self.pool.bundle = lambda: "bundle-2"
        self.assertTrue(self.researcher().mechanism_passed(self.store.family(self.fid)),
                        "the test gates the first broad replay only (review of #446)")
        child = self.born("late-sell-rebound-on-qqq", CARD, parent=self.fid, origin="fork")
        self.pool.jobs.clear()
        self.run_(fid=child)
        self.assertEqual(self.purposes(), ["train"], "a fork of a passed hypothesis is not tested again")

    def test_a_forks_bound_counts_its_lineages_failures(self):
        self.gate()
        self.edge = -0.05
        self.run_()
        self.run_(params={"threshold": 590})
        child = self.born("late-sell-rebound-on-qqq", CARD, parent=self.fid, origin="fork")
        self.run_(fid=child)
        self.assertEqual(self.evidence(child)[0]["detail"]["bound"], 1.25, "a fork never resets the count (review of #446)")
        self.assertTrue(self.store.family(child)["retired_at"], "the lineage's third hard failure retires it")
        other = self.born("unrelated-idea", {**CARD, "mechanism_class": "event_premium",
                                             "hypothesis": "A scheduled release's drift is mispriced by the market, so buyers "
                                                           "of the release's direction are paid."}, parent=self.fid)
        cards.put(self.store, other, {**CARD, "mechanism_class": "event_premium"}, "debit_vertical")
        self.assertEqual(self.researcher().mechanism_lineage(other)["failed"], 0, "another cell in the lineage does not count")

    def test_a_flat_card_runs_the_signal_arm_alone(self):
        self.gate()
        self.fid = self.born("hedged-premium", FLAT, structure="iron_condor")
        view, _ = self.run_()
        self.assertEqual(len(self.pool.by("mechanism")), 4)
        self.assertEqual({j.params.get("signal_on", 1) for j in self.pool.by("mechanism")}, {1})
        self.assertEqual((view["status"], view["mechanism_test"]["method"]), ("ok", "flat"))

    def test_a_passed_version_is_not_probed_and_a_test_row_never_hides_the_probe(self):
        self.settings["researcher"]["probe_year"] = 2022
        self.gate()
        self.run_()
        self.assertEqual(self.purposes(), ["mechanism"] * 8 + ["train"], "it traded on the sample: no probe")
        self.shadow()
        self.fid = self.born("shadowed", {**CARD, "hypothesis": CARD["hypothesis"] + " Shadowed."})
        self.pool.jobs.clear()
        self.run_()
        self.assertEqual(self.purposes(), ["mechanism"] * 8 + ["probe", "train"],
                         "a version's mechanism rows are not its Train run: the probe still runs (review of #446), and in "
                         "shadow it runs after a pass too (whether it runs would tell the verdict)")

    def test_a_family_born_before_cards_runs_as_before(self):
        self.fid = self.fam["id"]  # the seed family: no card
        self.run_(code=self.code)
        self.assertEqual(self.purposes(), ["train"])
        self.assertEqual(self.researcher().mechanism_text(self.store.family(self.fid)), "")

    def test_the_test_can_be_switched_off(self):
        self.settings["researcher"]["mechanism_test"] = {"enabled": False}
        self.run_()
        self.assertEqual(self.purposes(), ["train"])

    def test_the_brief_and_status_show_the_card_and_the_test(self):
        r = self.researcher()
        fam = self.store.family(self.fid)
        brief = r.brief(fam)
        self.assertIn("YOUR FAMILY CARD", brief)
        self.assertIn("PARAMS['signal_on'] = 0 must turn your signal into that comparison", brief)
        self.assertIn("shadow mode", r.status(fam))
        self.assertIn("withheld from you", r.status(fam))
        self.gate()
        self.assertIn("Your mechanism test has not passed", self.researcher().status(fam))


try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover - the Gym's requirements (requirements-gym.txt)
    HAVE = False


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class RealGym(unittest.TestCase):
    """A mechanism job through the Gym's own batch runner on a synthetic store: a Train window cut by start and end,
    unsplit, returns trades the test reads (day, pnl, max_loss and the audit's fields), inside the window; and a window
    the store has no data for exits 3, the error the researcher maps to that window's no_data."""

    PROGRAM = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 2], "band": 0.03, "cadence": 15}
PARAMS = {"signal_on": 1}
def decide(ctx):
    out = [{"close": p["id"], "limit": {"mid": 1}, "tif": 10} for p in ctx.positions if p["held_minutes"] > 60]
    wait = 600 if ctx.params["signal_on"] else 570
    if not ctx.positions and not ctx.orders and wait <= ctx.minute < 900:
        out.append({"open": "debit_vertical", "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0},
                    {"side": "short", "right": "C", "rel": 0, "offset": 2.0}], "max_loss": 300, "limit": {"mid": 1}, "tif": 10})
    return out
'''

    @classmethod
    def setUpClass(cls):
        from league.gym import synth
        cls.dir = tempfile.mkdtemp(prefix="gym-mech-")
        cls.days = synth.weekdays(dt.date(2023, 5, 1), 8)  # inside the second pre-registered window
        synth.generate(cls.dir, roots=("SPY",), days=cls.days, strikes_each_side=10, max_dte=4, seed=11)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_a_mechanism_job_returns_the_trades_the_test_reads(self):
        from league.gym import batch as B
        start, end = mechanism.sample_windows()[1]
        doc = B.run_batch([("on", self.PROGRAM, {"signal_on": 1}), ("off", self.PROGRAM, {"signal_on": 0})], store_root=self.dir,
                          window="train", roots=["SPY"], split=1, start=dt.date.fromisoformat(start),
                          end=dt.date.fromisoformat(end), stress_twin=False, workers=1)
        by = {r["program"]: r for r in doc["results"]}
        self.assertEqual({r["status"] for r in by.values()}, {"ok"})
        for arm in ("on", "off"):
            trades = by[arm]["trades"]
            self.assertTrue(trades, arm)
            self.assertTrue(all(start <= t["day"] <= end for t in trades), "days stay inside the window")
            self.assertTrue(all({"day", "pnl", "max_loss", "type", "context"} <= set(t) for t in trades))
            kept = mechanism.trim(by[arm])
            self.assertEqual(mechanism.day_returns(kept["trades"]), mechanism.day_returns(trades))
            self.assertEqual(mechanism.profile(kept["trades"])["types"], ["debit_vertical"])

    def test_a_window_the_store_has_no_data_for_exits_three(self):
        from league.gym import batch as B
        progs = Path(tempfile.mkdtemp(prefix="gym-mech-progs-"))
        self.addCleanup(shutil.rmtree, progs, True)
        (progs / "p.py").write_text(self.PROGRAM)
        start, end = mechanism.sample_windows()[0]  # 2022: this synthetic store holds May 2023 only
        code = B.main(["--programs", str(progs), "--window", "train", "--roots", "SPY", "--store", self.dir,
                       "--out", str(progs / "o.json"), "--start", start, "--end", end])
        self.assertEqual(code, B.EXIT_MISSING)
        self.assertTrue(mechanism.MISSING_DATA.search("the Gym is missing data: no train days for SPY in /data/store"))
        self.assertTrue(mechanism.MISSING_DATA.search("the Gym has no train data for TLT yet (it holds SPY)"))
        self.assertFalse(mechanism.MISSING_DATA.search("the Gym did not answer within 900 s (queue 3)"))


if __name__ == "__main__":
    unittest.main()
