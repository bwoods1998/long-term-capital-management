"""THE MECHANISM TEST (league/swarm/mechanism.py, release B) and its place in the researcher (league/swarm/researcher.py):
before a carded family's first broad Train replay its program runs with the signal on and with its card's ablation over a
pre-registered sample of Train windows; broad replay and sweeps wait for a pass; every arm is a trial; the verdict is
recorded on the card; repeated failures retire the family with the MECHANISM verdict. Synthetic programs and a fake Gym
only (no quotes, no real parameters)."""

from __future__ import annotations

import math
import random
import unittest

from league.swarm import cards, mechanism
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
        "falsification": "signal entries do not beat the comparison's by t 0.5 on the mechanism sample"}


def trade_days(window_start: str, n: int, offset: int = 0) -> list[str]:
    """Distinct synthetic day labels inside a window (labels only; the statistic groups by them)."""
    year, month = window_start[:4], window_start[5:7]
    return [f"{year}-{month}-{(offset + i) % 28 + 1:02d}" for i in range(n)]


class Statistic(unittest.TestCase):
    def test_windows_are_pre_registered(self):
        self.assertEqual(mechanism.sample_windows(2020, 2024),
                         [("2020-01-15", "2020-02-18"), ("2021-04-15", "2021-05-19"), ("2022-07-15", "2022-08-18"),
                          ("2023-10-15", "2023-11-18"), ("2024-01-15", "2024-02-18")])
        self.assertEqual(len(mechanism.sample_windows(2022, 2024)), 3)
        long = mechanism.sample_windows(2017, 2024)
        self.assertEqual([w[0][:4] for w in long], ["2017", "2019", "2021", "2022", "2024"], "evenly spaced, first and last")
        self.assertEqual(mechanism.windows_id(long), mechanism.windows_id(mechanism.sample_windows(2017, 2024)))

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

    def test_day_returns_group_trades_by_entry_day(self):
        got = mechanism.day_returns([{"day": "d1", "pnl": 10.0, "max_loss": 50.0}, {"day": "d1", "pnl": -5.0, "max_loss": 50.0},
                                     {"day": "d2", "pnl": 1.0, "max_loss": 0.0}, {"day": None, "pnl": 1.0, "max_loss": 1.0}])
        self.assertEqual(got, {"d1": 0.05})

    def test_config_falls_back_on_bad_values(self):
        cfg = mechanism.config({"researcher": {"mechanism_test": {"min_t": "x", "enabled": 1, "window_days": 999}}})
        self.assertEqual((cfg["min_t"], cfg["enabled"], cfg["window_days"]), (0.5, True, 120))
        self.assertFalse(mechanism.config({"researcher": {"mechanism_test": False}})["enabled"])


class Benchmark(unittest.TestCase):
    """The noise bound's justification (the module docstring): ~125 sample days, the signal on 15% of them, the comparison
    every other day, no cost drag (the hardest case for a real signal). Fixed seeds: the rates are pinned."""

    def rate(self, t_year: float | None, reps: int = 1500, seed: int = 11, min_t: float = 0.5) -> float:
        rng = random.Random(seed)
        delta = 0.0 if t_year is None else t_year / math.sqrt(252 * 0.15)
        passed = n = 0
        for _ in range(reps):
            on, off = {}, {}
            for d in range(125):
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

    def test_false_passes_are_cut_and_real_signals_mostly_pass(self):
        null, t2, t3 = self.rate(None), self.rate(2.0), self.rate(3.0)
        self.assertLess(null, 0.36, "a signal with no information reaches broad replay about a third of the time")
        self.assertGreater(t2, 0.70, "a signal at the validation line's t 2 a year passes most of the time")
        self.assertGreater(t3, 0.86)

    def test_the_bound_rises_with_each_failed_version(self):
        cfg = mechanism.config({})
        self.assertEqual([mechanism.bound(cfg, k) for k in range(3)], [0.5, 1.0, 1.5])
        null = [self.rate(None, reps=800, min_t=mechanism.bound(cfg, k)) for k in range(3)]
        real = [self.rate(2.0, reps=800, min_t=mechanism.bound(cfg, k)) for k in range(3)]
        through = lambda ps: 1 - math.prod(1 - p for p in ps)  # noqa: E731 - three independent tries
        self.assertLess(through(null), 0.55, "retries do not walk a signal with no information through")
        self.assertGreater(through(real), 0.9)


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
        spec = {"id": "late-sell-rebound", "mechanism": CARD["hypothesis"], "structure": "debit_vertical", "roots": ["SPY"],
                "dte": [0, 5], "rejection": "no edge", "card_sha": cards.card_sha(CARD)}
        self.carded = self.store.add_family(spec, origin="architect")
        cards.put(self.store, self.carded["id"], CARD, "debit_vertical")
        self.fid = self.carded["id"]
        self.edge = 0.4  # the signal's advantage per entry day, in daily return on maximum loss
        self.off_trades = True
        self.pool = MechPool(self.answer)

    def answer(self, job):
        """Signal on: 6 entry days a window, returning `edge` over the comparison; off: those days and 14 more at 0."""
        r = result(job.name, roots=job.roots)
        if job.purpose != "mechanism":
            return r
        on = bool(job.params.get("signal_on", 1))
        days = trade_days(job.start, 6)
        rows = [{"id": i, "day": d, "pnl": (0.1 + self.edge + 0.02 * (i % 3)) * 50.0, "max_loss": 50.0, "fees": 1.0}
                for i, d in enumerate(days)]
        if not on:
            rows = [{**t, "pnl": 5.0 + 1.0 * (t["id"] % 3)} for t in rows] if self.off_trades else []
            if self.off_trades:
                rows += [{"id": 100 + i, "day": d, "pnl": (0.1 + 0.02 * (i % 3)) * 50.0, "max_loss": 50.0, "fees": 1.0}
                         for i, d in enumerate(trade_days(job.start, 14, offset=6))]
        r["trades"] = rows
        return r

    def run_(self, code=CODE, **args):
        out: dict = {"tool_calls": 0}
        view = self.researcher()._gym_run(self.store.family(self.fid), {"code": code, **args}, out, author="synthetic")
        return view, out

    def rows(self, window):
        return self.store._all("SELECT * FROM runs WHERE family=? AND window=?", (self.fid, window))

    def purposes(self):
        """The jobs asked of the Gym, robustness runs aside (a new best queues them, as ever)."""
        return [j.purpose for j in self.pool.jobs if j.purpose != "robustness"]

    def windows(self):
        return mechanism.sample_windows(self.researcher().train_first_year(), 2024)

    def test_a_pass_opens_broad_replay_and_every_arm_is_a_trial(self):
        view, out = self.run_()
        mech = self.pool.by("mechanism")
        w = self.windows()
        self.assertEqual(len(mech), 2 * len(w), "one job a pre-registered window and arm")
        self.assertEqual({(j.split, j.window, j.stress) for j in mech}, {(1, "train", 1.0)})
        self.assertEqual(sorted({(j.start, j.end) for j in mech}), sorted(w))
        self.assertEqual(sorted({j.params.get("signal_on", 1) for j in mech}), [0, 1])
        self.assertEqual([j.purpose for j in self.pool.jobs if j.purpose != "robustness"][-1], "train",
                         "the broad run follows the pass")
        self.assertEqual((view["status"], view["mechanism_test"]["verdict"]), ("ok", "passed"))
        self.assertEqual((len(self.rows("mechanism")), len(self.rows("train"))), (2 * len(w), 1))
        self.assertEqual(self.store.family(self.fid)["trials"], 2 * len(w) + 1, "every arm-window and the broad run: each a trial")
        self.assertEqual(out["mechanism_test"]["box_seconds"], 2.0 * 2 * len(w), "the cost measure: each job's share of its batch")
        [ev] = cards.evidence(self.store, self.fid, kind="mechanism_test")
        self.assertEqual((ev["verdict"], ev["version"], ev["card_sha"]), ("passed", 1, cards.card_sha(CARD)))
        self.assertTrue(self.researcher().mechanism_passed(self.store.family(self.fid)))
        self.pool.jobs.clear()
        self.run_(params={"threshold": 590})
        self.assertEqual(self.purposes(), ["train"], "once passed, no more tests")
        self.assertIn("passed", self.researcher().mechanism_text(self.store.family(self.fid)))

    def test_a_failed_test_skips_broad_replay_and_three_retire_with_the_mechanism_verdict(self):
        self.edge = -0.05
        view, out = self.run_()
        self.assertEqual(view["status"], "mechanism_failed")
        self.assertEqual(self.pool.by("train"), [], "no broad replay")
        self.assertEqual(out["trials"], 2 * len(self.windows()))
        self.assertEqual(self.researcher().mechanism_record(self.store.family(self.fid))["failed"], [1])
        self.pool.jobs.clear()
        again, out2 = self.run_()
        self.assertEqual((self.pool.jobs, again.get("already_run")), ([], "the stored result"), "the same test is not run twice")
        self.assertEqual(out2.get("trials", 0), 0)
        self.run_(params={"threshold": 590})
        last, out3 = self.run_(params={"threshold": 580})
        fam = self.store.family(self.fid)
        self.assertTrue(fam["retired_at"], "three failed versions retire it")
        self.assertIn(mechanism.MARK, fam["retire_reason"])
        self.assertEqual(tag_of(self.store._one("SELECT * FROM graveyard WHERE family=?", (self.fid,)), fam), "MECHANISM")
        self.assertIn("MECHANISM", str(last.get("retired")))
        self.assertIn("MECHANISM", cards.MECHANISM_VERDICTS)

    def test_programs_that_cannot_take_the_test_are_refused_before_any_version(self):
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

    def test_an_ablation_that_does_not_trade_is_invalid_not_a_finding(self):
        self.off_trades = False
        view, _ = self.run_()
        self.assertEqual(view["status"], "mechanism_invalid")
        self.assertIn("trade the comparison strategy", view["next"])
        rec = self.researcher().mechanism_record(self.store.family(self.fid))
        self.assertEqual((rec.get("failed"), rec["untestable"]), (None, [1]))

    def test_sweeps_wait_for_a_pass(self):
        out: dict = {"tool_calls": 0}
        view = self.researcher()._gym_sweep(self.store.family(self.fid), {"code": CODE, "variants": [{"threshold": 590},
                                                                                                    {"threshold": 580}]},
                                            out, author="synthetic")
        self.assertIn("mechanism test has not passed", view["reason"])
        self.assertEqual(self.pool.jobs, [])

    def test_a_gym_error_keeps_the_landed_arms_and_reuses_them(self):
        self.pool.fail = lambda job: "the Gym did not answer" if job.params.get("signal_on") == 0 and job.start[5:7] == "04" else None
        view, out = self.run_()
        self.assertEqual(view["status"], "gym_error")
        self.assertEqual(len(self.rows("mechanism")), 2 * len(self.windows()) - 1)
        self.pool.fail = lambda job: None
        self.pool.jobs.clear()
        view, _ = self.run_()
        self.assertEqual(len(self.pool.by("mechanism")), 1, "only the arm that never landed runs again")
        self.assertEqual(view["mechanism_test"]["verdict"], "passed")

    def test_a_new_evaluator_asks_for_the_test_again(self):
        self.pool.image = lambda kind: "img-1"
        self.pool.bundle = lambda: "bundle-1"
        self.run_()
        self.assertTrue(self.researcher().mechanism_passed(self.store.family(self.fid)))
        self.pool.bundle = lambda: "bundle-2"
        self.assertFalse(self.researcher().mechanism_passed(self.store.family(self.fid)), "a pass is never carried across Gyms")

    def test_a_family_born_before_cards_runs_as_before(self):
        self.fid = self.fam["id"]  # the seed family: no card
        view, _ = self.run_(code=self.code)
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
        self.assertIn("Your mechanism test has not passed", r.status(fam))


if __name__ == "__main__":
    unittest.main()
