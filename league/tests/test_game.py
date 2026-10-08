"""THE LEARNING GAME v1 (league/swarm/game.py): folds and arms, the fitness, the look ladder and its retries, the CONFIRM
discipline (the sealed accessor, the read budgets, decisions blind to the CONFIRM year), reproduction and its caps,
the game's retirement rules, the graveyard quarantine and what agents see, the operator's metrics, and the CI wall. Then
the integration: the tournament in "gate" mode and main's round played byte for byte by control and legacy families
(`Golden`, against league/tests/game_golden.json), the allocation's blind rows, the leak tests (every researcher-facing
output, the import wall, the architect's and the strategist's inputs unmoved by the game arm, the agenda's years), the
quarantine for every reader, and the operator's report and its dry run. Synthetic stores and invented results only; the
pools are fakes that record what they are asked to run."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import io
import json
import math
import random
import re
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from league import ci
from league.gym.results import _t_of
from league.swarm import allocation, canary, cards
from league.swarm import game
from league.swarm import researcher as researcher_mod
from league.swarm import settings as S
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests import game_golden
from league.tests.swarm_fakes import Clock, result

DAY = 86400.0
MECHANISM = "Index calls after a low close rebound into the next session's open, a debit vertical."


def on(**over):
    """Settings with the game on (mode "gate", every new lineage in the game arm unless `arm_fraction` says otherwise)."""
    block = {"enabled": True, "mode": "gate", "arm_fraction": 1.0, **over}
    return {"game": block, "population": {"ceiling": 96, "floor": 0}}


def year_rows(f, *, trades=60, days_traded=30, roots=("SPY",), t_net=10.0):
    """(by_year row, drift row) of one hidden year whose F is `f` (t_alpha; t_net is 10 unless given), or an ineligible
    year (no trades) when `f` is None."""
    by = {"trades": trades if f is not None else 0, "days": 250, "days_traded": days_traded if f is not None else 0,
          "pnl": 1000.0, "t_daily": 1.0, "quarters_positive": "4/4", "quarter_pnl": {}, "roots": list(roots)}
    # Sums of squares that give these t's (`results._t_of`): t_net over pnl 1000 and t_alpha over alpha 500, 250 days.
    pnl, n = 1000.0, 250
    alpha = 0.0 if not f else 500.0 if f > 0 else -500.0
    var, var_alpha = (pnl / n / t_net) ** 2 * n, (alpha / n / f) ** 2 * n if f else 100.0
    drift = {"days": n, "held_days": 100, "pnl": pnl, "alpha": alpha / n, "alpha_usd": alpha, "t": f, "beta": 10.0,
             "drift_usd": pnl - alpha, "sum_sq": var_alpha * (n - 1) + alpha * alpha / n, "sum_pp": var * (n - 1) + pnl * pnl / n,
             "root_days": {r: 250 for r in roots}}
    return by, drift


def hidden(f2020, f2021, *, status="ok", roots=("SPY",), **kw):
    """An invented hidden run (2020-21 at 1.5x) with F `f2020` and `f2021` (None: an ineligible year)."""
    out = {"status": status, "roots": list(roots), "summary": {"pnl": 10.0, "days": 504}, "by_year": {}, "train_from": game.HIDDEN[0],
           "drift": {"basis": "held-hours", "years": {}, "pooled": {"days": 500, "held_days": 200, "pnl": 2000.0, "alpha": 0.0,
                                                                    "alpha_usd": 0.0, "beta": 0.0, "drift_usd": 0.0, "t": None}}}
    for year, f in (("2020", f2020), ("2021", f2021)):
        out["by_year"][year], out["drift"]["years"][year] = year_rows(f, roots=roots, **kw)
    return out


def seen_run(pnl=50.0):
    """A 1.5x seen run (2022-24) as `robust_landed` hands it to the game."""
    years = {}
    for y in ("2022", "2023", "2024"):
        _, row = year_rows(1.5)
        years[y] = row
    return {"status": "ok", "summary": {"pnl": pnl}, "train_from": game.SEEN_FROM,
            "drift": {"basis": "held-hours", "years": years, "pooled": {"days": 750, "t": 2.0}}}


class FakePool:
    def __init__(self):
        self.jobs = []

    def submit(self, job):
        self.jobs.append(job)
        return job


class GameCase(unittest.TestCase):
    settings = on()

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.pool = FakePool()
        self.settings = copy.deepcopy(type(self).settings)
        self.researcher = types.SimpleNamespace(store=self.store, settings=self.settings, pool=self.pool, clock=self.clock)
        self.t0 = game.t0(self.store, self.settings)
        self.clock.advance(60)
        self.tags = 0
        game._inflight.clear()

    # ------------------------------------------------------------------ fixtures
    def family(self, fid, *, roots=("SPY",), parent=None, origin="architect", **spec):
        return self.store.add_family({"id": fid, "mechanism": MECHANISM, "structure": "debit_vertical", "roots": list(roots),
                                      **spec}, origin=origin, parent=parent)

    def version(self, fid, code=None, params=None):
        self.tags += 1
        code = code or f"NEEDS = {{'roots': ['SPY']}}\nTAG = {self.tags}\n"
        return self.store.add_version(fid, code, params or {"k": self.tags}, author="test")

    def best(self, fid, score, *, code=None, params=None):
        """A new best by Train score: a version, its eligible Train run over the seen span, the family's best."""
        v = self.version(fid, code, params)
        run = self.store.add_run(fid, v["n"], {"run_id": f"r-{fid}-{v['n']}-{self.tags}", "status": "ok", "trials": 1,
                                               "summary": {"train_score": score, "train_eligible": True,
                                                           "train_from": game.SEEN_FROM}},
                                 window="train", stress=1.0, purpose="train")
        self.store.update_family(fid, best_train=score)
        self.store.set_state(fid, best_train_version=v["n"], best_train_run=run["run_id"])
        return v["n"]

    def look(self, fid, score, *, pnl=50.0, code=None):
        n = self.best(fid, score, code=code)
        return n, game.maybe_look(self.researcher, fid, n, seen_run(pnl))

    def job_of(self, seq):
        mine = [j for j in self.pool.jobs if j.late is not None and j.version is not None]
        for j in reversed(mine):
            row = self.store._one("SELECT family, version FROM game_looks WHERE seq=?", (seq,))
            if row and j.family == row["family"] and j.version == row["version"]:
                return j
        raise AssertionError(f"no job for look {seq}")

    def land(self, seq, f_sel, f_conf, **kw):
        """The look's hidden run lands with F `f_sel` on its SELECT year and `f_conf` on its CONFIRM year."""
        select = self.store._one("SELECT select_year FROM game_looks WHERE seq=?", (seq,))["select_year"]
        figures = {select: f_sel, 2021 if select == 2020 else 2020: f_conf}
        self.job_of(seq).late(hidden(figures[2020], figures[2021], **kw))

    def plant(self, fam, f_sel, f_conf, *, confirm=None, read_f=None, role="ladder", side=None):
        """A landed look written directly (its CONFIRM read as given, or none): what `landed` would leave."""
        c = game.cfg(self.settings)
        v = self.version(fam["id"])
        with self.store.atomic():
            seq = game._record_look(self.store, fam, side or game.arm(self.store, fam, self.settings), role, v, c, seen_score=1.0)
        select, other = game.fold(fam["lineage"])

        def fig(f):
            return {"eligible": f is not None, "trades": 60, "days_traded": 30, "t_net": 10.0, "t_alpha": f, "F": f, "why": None}

        game._result(self.store, seq, "ok", {str(select): fig(f_sel), str(other): fig(f_conf)}, game.tier_of(f_sel, c["c_select"]))
        if confirm is not None:
            self.store._exec("INSERT INTO game_confirms(look_seq, at, f_confirm, confirmed) VALUES(?,?,?,?)",
                             (seq, self.store.now(), f_conf if read_f is None else read_f, 1 if confirm else 0))
        return seq

    def named(self, select_year, *, prefix="fam", skip=()):
        """A family id whose lineage's SELECT year is `select_year`."""
        for i in range(1000):
            name = f"{prefix}-{i}"
            if name not in skip and game.fold(name)[0] == select_year and self.store.family(name) is None:
                return name
        raise AssertionError("no such name")


# ------------------------------------------------------------------------------------------------ 1. folds and arms
class FoldsAndArms(GameCase):
    def test_the_hashes_are_the_specs_and_split_evenly(self):
        for lineage in ("a", "condor-vrp", "g-0123abcd"):
            even = hashlib.sha256(("ltcm-game-v1\0" + lineage).encode()).digest()[0] % 2 == 0
            self.assertEqual(game.fold(lineage), (2020, 2021) if even else (2021, 2020))
            self.assertEqual(game.fold(lineage), game.fold(lineage))
        lineages = [f"lineage-{i}" for i in range(10000)]
        self.assertAlmostEqual(sum(game.fold(x)[0] == 2020 for x in lineages) / 10000, 0.5, delta=0.015)
        for fraction in (0.5, 0.3):
            settings = on(arm_fraction=fraction)
            fams = [{"id": x, "lineage": x, "born_at": self.store.now(), "roots": ["SPY"]} for x in lineages]
            share = sum(game.arm(self.store, f, settings) == "game" for f in fams) / 10000
            self.assertAlmostEqual(share, fraction, delta=0.015)
            self.assertTrue(all(game.arm(self.store, f, settings) in game.ARMS for f in fams[:50]))
            self.assertEqual(game.arm(self.store, fams[7], settings) == "game",
                             canary.in_arm("ltcm-game-v1", "game-v1", fams[7]["lineage"], fraction))

    def test_a_child_has_its_parents_fold_and_arm(self):
        settings = on(arm_fraction=0.5)
        for i in range(12):
            mother = self.family(f"mother-{i}")
            child = self.family(f"child-{i}", parent=mother["id"])
            self.assertEqual(child["lineage"], mother["lineage"])
            self.assertEqual(game.fold(child["lineage"]), game.fold(mother["lineage"]))
            self.assertEqual(game.arm(self.store, child, settings), game.arm(self.store, mother, settings))

    def test_legacy_born_before_t0_a_root_outside_the_core_five_the_game_off_or_no_t0(self):
        new = self.family("new-one")
        self.assertEqual(game.arm(self.store, new, self.settings), "game")
        early = dict(new, born_at="2026-01-01T00:00:00Z")
        self.assertIsNone(game.arm(self.store, early, self.settings))
        self.assertIsNone(game.arm(self.store, self.family("pooled", roots=("SPY", "TSLA")), self.settings))
        self.assertIsNone(game.arm(self.store, new, {"game": {"enabled": "yes", "mode": "gate"}}), "a malformed switch is off")
        self.assertIsNone(game.arm(self.store, new, {}))
        bare = SwarmStore(Path(self.dir.name) / "bare", clock=self.clock)
        self.addCleanup(bare.close)
        self.assertIsNone(game.arm(bare, new, self.settings), "no T0 written: nobody plays")

    def test_t0_is_written_once_at_the_first_start_with_the_game_on(self):
        self.assertEqual(self.store.get(game.T0_KEY), self.t0)
        self.clock.advance(DAY)
        self.assertEqual(game.t0(self.store, self.settings), self.t0)
        bare = SwarmStore(Path(self.dir.name) / "bare", clock=self.clock)
        self.addCleanup(bare.close)
        self.assertIsNone(game.t0(bare, {}), "the game off: never written")
        self.assertIsNone(game.t0(bare))

    def test_settings_bounds_and_malformed_values(self):
        c = game.cfg({"game": {"enabled": True, "mode": "loud", "arm_fraction": 0, "eta": 3, "looks": 9, "c_select": 0.5,
                               "c_confirm": "x", "confirms_lineage": 7, "children_per_day": 100, "children_per_round": 60,
                               "hidden": ["2019-01-02", "2021-12-31"], "seen_from": "soon", "roots": "SPY"}})
        self.assertEqual((c["mode"], c["arm_fraction"], c["eta"], c["looks"], c["c_select"], c["c_confirm"]),
                         ("shadow", 0.5, 1.0, 6, 1.0, 1.28))
        self.assertEqual((c["confirms_lineage"], c["children_per_day"], c["children_per_round"]), (3, 48, 48))
        self.assertEqual((c["hidden"], c["seen_from"], c["roots"]), (list(game.HIDDEN), game.SEEN_FROM, list(game.CORE)))
        self.assertEqual(game.cfg({"game": {"seen_from": "2020-01-02"}})["seen_from"], game.SEEN_FROM,
                         "the seen span never reaches back into the hidden years")
        self.assertEqual(game.cfg({"game": {"hidden": ["2020-03-02", "2021-06-30"]}})["hidden"], ["2020-03-02", "2021-06-30"])
        self.assertFalse(game.cfg(None)["enabled"])
        self.assertEqual(game.cfg({"game": {"arm_fraction": 2}})["arm_fraction"], 1.0)
        self.assertIsNone(game.birth_roots({}))
        self.assertEqual(game.birth_roots(self.settings), list(game.CORE))
        self.assertEqual(game.cfg({"game": json.loads((Path(ci.REPO) / "league" / "swarm" / "policy.json").read_text())["game"]}),
                         {**game.cfg({"game": {**game.DEFAULTS}}), "enabled": True, "mode": "gate"},
                         "the committed block is the defaults, switched on in gate mode")


# ------------------------------------------------------------------------------------------------ 2. fitness
class Fitness(unittest.TestCase):
    def test_t_net_is_the_gyms_t_t_alpha_the_drift_t_and_f_their_min(self):
        r = hidden(0.8, 2.5)
        row = r["drift"]["years"]["2020"]
        row.update(pnl=321.0, sum_pp=9000.0, days=240)
        out = game.fitness(r, 2020)
        self.assertEqual(out["t_net"], _t_of(321.0, 9000.0, 240, 9000.0))
        self.assertEqual(out["t_alpha"], 0.8)
        self.assertEqual(out["F"], min(out["t_net"], 0.8))
        self.assertTrue(out["eligible"])
        binding = hidden(0.8, 25.0)
        self.assertAlmostEqual(game.fitness(binding, "2021")["F"], 10.0, places=9, msg="t_net binds a drift earner's F")

    def test_each_shortfall_makes_the_year_ineligible_and_minus_infinity(self):
        cases = {"trades": hidden(2.0, 2.0, trades=39), "days": hidden(2.0, 2.0, days_traded=19)}
        missing = hidden(2.0, 2.0, roots=("SPY", "QQQ"))
        missing["by_year"]["2020"]["roots"] = ["SPY"]
        cases["root"] = missing
        null = hidden(2.0, 2.0)
        null["drift"]["years"]["2020"]["t"] = None
        cases["t"] = null
        for name, r in cases.items():
            out = game.fitness(r, 2020)
            self.assertFalse(out["eligible"], name)
            self.assertEqual(out["F"], float("-inf"), name)
            self.assertTrue(out["why"], name)
        self.assertTrue(game.fitness(hidden(2.0, 2.0, trades=40, days_traded=20), 2020)["eligible"], "40 on 20 is enough")
        self.assertFalse(game.fitness(hidden(2.0, 2.0, status="error"), 2020)["eligible"])
        self.assertEqual([game.tier_of(f, 1.28) for f in (1.28, 1.27, 0.0, -0.1, None, float("-inf"))],
                         ["PASS", "ALIVE", "ALIVE", "FAIL", "FAIL", "FAIL"])

    def test_seen_f_is_the_pooled_f_over_the_seen_years_per_year(self):
        r = seen_run()
        rows = r["drift"]["years"].values()
        pp, sq = sum(x["sum_pp"] for x in rows), sum(x["sum_sq"] for x in rows)
        expected = min(_t_of(3000.0, pp, 750, pp), _t_of(1500.0, sq, 750, pp)) / math.sqrt(3)
        self.assertAlmostEqual(game.seen_fitness(r["drift"]), expected, places=12)
        self.assertAlmostEqual(expected, 1.5, places=2, msg="three years at t 1.5 each pool to about 1.5 a year")
        r["drift"]["years"]["2021"] = dict(r["drift"]["years"]["2022"], alpha_usd=-1e6)
        self.assertAlmostEqual(game.seen_fitness(r["drift"]), expected, places=12, msg="a year before the seen span is left out")
        self.assertIsNone(game.seen_fitness(None))


# ------------------------------------------------------------------------------------------------ 3. the ladder
class Ladder(GameCase):
    def test_the_first_eligible_best_opens_look_one_and_eta_gates_the_next(self):
        fam = self.family("ladder-a")
        n, out = self.look("ladder-a", 1.0)
        self.assertIsNotNone(out["look"])
        [job] = self.pool.jobs
        self.assertEqual((job.window, job.purpose, job.start, job.end, job.stress, job.roots, job.version),
                         ("train", "private", "2020-01-02", "2021-12-31", 1.5, ("SPY",), n))
        events = [e for e in self.store.events_after(0) if e["kind"] == "swarm.game"]
        self.assertEqual([e["payload"] for e in events], [{"family": fam["id"], "version": n, "look": "queued"}])
        trials, runs = self.store.family("ladder-a")["trials"], len(self.store.runs("ladder-a", limit=500))
        self.land(out["look"], -0.5, 0.2)
        self.assertEqual((self.store.family("ladder-a")["trials"], len(self.store.runs("ladder-a", limit=500))), (trials, runs),
                         "a hidden run is never a run row, a trial or anything a researcher can read")
        self.assertEqual(game._rows(self.store, "seq=?", (out["look"],))[0]["tier"], "FAIL")
        _, refused = self.look("ladder-a", 1.4)
        self.assertEqual(refused["look"], None)
        self.assertIn("eta", refused["why"])
        _, second = self.look("ladder-a", 1.5)
        self.assertIsNotNone(second["look"], "a gain of exactly eta is enough")
        self.assertEqual(game.looks_used(self.store, fam), 2)

    def test_the_looks_cap_and_one_look_in_flight(self):
        self.settings["game"]["looks"] = 2
        self.family("ladder-b")
        _, first = self.look("ladder-b", 1.0)
        _, busy = self.look("ladder-b", 3.0)
        self.assertIn("in flight", busy["why"])
        self.land(first["look"], 0.1, 0.1)
        _, second = self.look("ladder-b", 3.0)
        self.land(second["look"], 0.1, 0.1)
        _, spent = self.look("ladder-b", 9.0)
        self.assertIn("spent", spent["why"])

    def test_no_look_without_a_profitable_15x_seen_run_or_off_the_best(self):
        self.family("ladder-c")
        _, lost = self.look("ladder-c", 1.0, pnl=-1.0)
        self.assertIn("1.5x", lost["why"])
        n = self.best("ladder-c", 2.0)
        self.store.set_state("ladder-c", robust_failed=[n])
        self.assertIn("1.5x", game.maybe_look(self.researcher, "ladder-c", n, seen_run())["why"])
        m = self.best("ladder-c", 2.0)
        self.assertIn("best", game.maybe_look(self.researcher, "ladder-c", m - 1, seen_run())["why"])
        self.assertEqual(self.pool.jobs, [])

    def test_the_same_program_is_never_looked_at_twice_in_its_lineage(self):
        mother = self.family("ladder-d")
        code = "NEEDS = {'roots': ['SPY']}\nSIGNAL = 1\n"
        _, first = self.look("ladder-d", 1.0, code=code)
        self.land(first["look"], 0.5, 0.5)
        child = self.family("ladder-d-child", parent=mother["id"])
        _, copy_ = self.look(child["id"], 5.0, code=code)
        self.assertIn("lineage", copy_["why"], "a child's unchanged copy of its parent's program is never looked at")
        _, own = self.look(child["id"], 5.0)
        self.assertIsNotNone(own["look"], "its own program is")

    def test_a_failed_job_is_retried_after_2h_at_most_3_times_and_does_not_count(self):
        fam = self.family("ladder-e")
        _, out = self.look("ladder-e", 1.0)
        seq = out["look"]
        for attempt in range(3):
            if attempt == 0:
                self.job_of(seq).late(hidden(2.0, 2.0, status="error"))  # a run that did not complete: an attempt
            else:
                self.job_of(seq).late_fail("the box failed")
            self.assertEqual(game.requeue_stale(self.store, self.settings, self.pool), {"requeued": 0, "failed": 0, "cancelled": 0})
            self.clock.advance(2 * 3600 + 1)
            out = game.requeue_stale(self.store, self.settings, self.pool)
            self.assertEqual(out, {"requeued": 1, "failed": 0, "cancelled": 0} if attempt < 2 else
                             {"requeued": 0, "failed": 1, "cancelled": 0}, attempt)
        self.assertEqual(len(self.pool.jobs), 3)
        [row] = game._rows(self.store, "seq=?", (seq,))
        self.assertEqual((row["status"], row["attempts"]), ("failed", 3))
        self.assertEqual(game.looks_used(self.store, fam), 0, "a failed look does not count against the four")
        _, again = self.look("ladder-e", 1.1)
        self.assertIsNotNone(again["look"], "no look in flight: the next best is looked at")

    def test_a_look_lost_to_a_restart_is_queued_again_and_one_in_the_pool_is_not(self):
        self.family("ladder-f")
        _, out = self.look("ladder-f", 1.0)
        self.clock.advance(3 * 3600)
        self.assertEqual(game.requeue_stale(self.store, self.settings, self.pool)["requeued"], 0, "still in this process's pool")
        game._inflight.clear()  # a restart
        self.assertEqual(game.requeue_stale(self.store, self.settings, self.pool)["requeued"], 1)
        self.land(out["look"], 1.0, 1.0)
        self.assertEqual(game._rows(self.store, "seq=?", (out["look"],))[0]["status"], "ok")
        self.store.retire("ladder-f", "test")
        self.assertEqual(game.requeue_stale(self.store, self.settings, self.pool)["cancelled"], 0, "a landed look stays landed")

    def test_the_game_off_a_legacy_family_or_a_span_with_hidden_days_makes_no_look(self):
        self.family("ladder-g")
        n = self.best("ladder-g", 1.0)
        self.assertIsNone(game.maybe_look(types.SimpleNamespace(store=self.store, settings={}, pool=self.pool), "ladder-g", n,
                                          seen_run()))
        self.family("ladder-h", roots=("SPY", "NVDA"))
        self.assertIsNone(game.maybe_look(self.researcher, "ladder-h", self.best("ladder-h", 1.0), seen_run()))
        self.store.put("train_objective", "worst-train-year-v1@2020-01-02")
        self.assertIn("span", game.maybe_look(self.researcher, "ladder-g", n, seen_run())["why"])
        self.assertEqual(self.pool.jobs, [])
        self.assertIsNone(game.maybe_look(None, "x", 1, {}), "never raises")


class ThroughThePool(GameCase):
    def test_a_look_runs_as_a_private_batch_on_the_2020_image_and_lands(self):
        from league.swarm.pool import Box, GymPool
        from league.tests.swarm_fakes import FakeDriver, FakeSail
        from league.tests.test_swarm_pool import settings as pool_settings

        settings = pool_settings(allow_earlier_image=True)
        settings.update(on())
        self.researcher.settings = settings
        calls = []
        answer = lambda name, code, params, window, stress, roots: hidden(2.0, 2.0)  # noqa: E731
        pool = GymPool(self.store, FakeSail(), settings, clock=self.clock, threaded=False)
        box = Box("sb_00000001-ffff-ffff-ffff-ffffffffffff", "gym", str(pool.image("gym")), "ready",
                  driver=FakeDriver(None, "x", calls=calls, answer=answer, train_first="2020-01-02"), roots=game.CORE,
                  last_used=self.clock(), train_first="2020-01-02")
        pool.boxes[box.id] = box
        self.researcher.pool = pool
        fam = self.family("pool-a")
        _, out = self.look("pool-a", 1.0)
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertEqual((calls[-1]["window"], calls[-1]["start"], calls[-1]["end"], calls[-1]["stress"]),
                         ("train", "2020-01-02", "2021-12-31", 1.5))
        [row] = game._rows(self.store, "seq=?", (out["look"],), confirms=True)
        self.assertEqual((row["status"], row["tier"], game.confirm_view(row)["confirmed"]), ("ok", "PASS", True))
        self.assertEqual(game.candidate(self.store, fam), row["version"])
        self.assertEqual(game._inflight, {})


# ------------------------------------------------------------------------------------------------ 4. CONFIRM discipline
class Confirm(GameCase):
    def test_confirm_view_raises_without_its_read(self):
        fam = self.family("conf-a")
        seq = self.plant(fam, 2.0, 2.0)
        [row] = game._rows(self.store, "seq=?", (seq,), confirms=True)
        with self.assertRaises(game.Sealed):
            game.confirm_view(row)
        self.assertEqual(game.select_view(row)["F"], 2.0)
        read = self.plant(fam, 2.0, 1.9, confirm=True)
        [row] = game._rows(self.store, "seq=?", (read,))
        with self.assertRaises(game.Sealed):
            game.confirm_view(row)  # read without the confirm table: never
        [row] = game._rows(self.store, "seq=?", (read,), confirms=True)
        self.assertEqual(game.confirm_view(row), {"year": game.fold(fam["lineage"])[1], "F": 1.9, "confirmed": True})

    def test_a_pass_reads_the_confirm_year_once_at_most_twice_a_family_and_three_times_a_lineage(self):
        mother = self.family("conf-b")
        seqs = []
        for score in (1.0, 2.0, 3.0):
            _, out = self.look("conf-b", score)
            self.land(out["look"], 2.0, 1.5)
            seqs.append(out["look"])
        reads = self.store._all("SELECT look_seq, confirmed FROM game_confirms ORDER BY seq")
        self.assertEqual([(r["look_seq"], r["confirmed"]) for r in reads], [(seqs[0], 1), (seqs[1], 1)])
        self.assertEqual(game.candidate(self.store, mother), self.store._one("SELECT version FROM game_looks WHERE seq=?",
                                                                             (seqs[1],))["version"])
        child = self.family("conf-b-child", parent=mother["id"])
        for score in (1.0, 2.0):
            _, out = self.look(child["id"], score)
            self.land(out["look"], 2.0, 0.5)
        self.assertEqual(len(self.store._all("SELECT 1 FROM game_confirms")), 3, "the lineage reads three in all")
        self.assertIsNone(game.candidate(self.store, child), "its one read failed")

    def test_alive_fail_and_shadow_mode_and_control_read_nothing(self):
        self.family("conf-c")
        _, out = self.look("conf-c", 1.0)
        self.land(out["look"], 1.0, 3.0)
        self.assertEqual(self.store._all("SELECT * FROM game_confirms"), [], "ALIVE reads nothing")
        self.settings["game"]["mode"] = "shadow"
        _, out = self.look("conf-c", 2.0)
        self.land(out["look"], 3.0, 3.0)
        self.assertEqual(self.store._all("SELECT * FROM game_confirms"), [], "shadow reads nothing")
        self.assertEqual(game._rows(self.store, "seq=?", (out["look"],))[0]["tier"], "PASS", "but the tier is recorded")

    def test_decisions_are_blind_to_the_confirm_years_figures(self):
        """The property test: two stores alike but for the CONFIRM-year figures of their looks (permuted; the gate's reads
        the same) give the same parents, children, retirements and allocation."""
        for trial in range(4):
            outs = []
            for permute in (False, True):
                case = _Twin("runTest")
                case.setUp()
                try:
                    outs.append(case.random_store(random.Random(trial), permute))
                finally:
                    case.doCleanups()
            self.assertEqual(outs[0], outs[1], trial)
            self.assertTrue(outs[0]["parents"], "the property is tested on stores with parents")


class _Twin(GameCase):
    def runTest(self):  # pragma: no cover - a fixture, run by `Confirm`
        pass

    def random_store(self, rng, permute):
        self.settings["game"].update(looks=3, parent_min_looks=5)
        fams = [self.family(f"twin-{i}") for i in range(8)]
        planted = []
        for fam in fams:
            for _ in range(rng.randint(1, 4)):
                f_sel = rng.choice([None, round(rng.uniform(-1, 3), 3)])
                f_conf = round(rng.uniform(-1, 3), 3)
                read = rng.choice([None, None, True, False]) if f_sel is not None and f_sel >= 1.28 else None
                planted.append([fam, f_sel, f_conf, read])
        confs = [p[2] for p in planted]
        if permute:
            rng2 = random.Random(99)
            rng2.shuffle(confs)
        for p, f_conf in zip(planted, confs):
            self.plant(p[0], p[1], f_conf, confirm=p[3], read_f=p[2])  # the gate's reads are the same in both
        found = game.parents(self.store, self.settings)
        reasons = {f["id"]: game.retire_reason(self.store, self.store.family(f["id"]), self.settings) for f in fams}
        born = game.reproduce(self.store, self.settings)
        kids = [(k, self.store.family(k)["spec"].get("game_directive"), self.store.family(k)["spec"].get("game_donor"))
                for k in born]
        for i, fam in enumerate(fams[:4]):  # validated families: the allocation reads its rows, blind to the game arm's t
            self.store.update_family(fam["id"], validations=1)
            self.store.set_state(fam["id"], validation_numbers={"mean": 0.01, "t": 0.5 + i, "sharpe_daily": 0.1, "quarters": "3/4"})
        shares, _ = allocation.allocate_from_store(self.store, self.store.families(alive=True), self.settings, now=self.clock())
        return {"parents": found, "reasons": reasons, "born": kids, "shares": shares}


# ------------------------------------------------------------------------------------------------ 5 (units). the tournament's reads
class TournamentReads(GameCase):
    def test_candidate_validation_tries_and_the_robustness_bypass(self):
        fam = self.family("tour-a")
        self.assertIsNone(game.candidate(self.store, fam))
        _, out = self.look("tour-a", 1.0)
        n = self.store._one("SELECT version FROM game_looks WHERE seq=?", (out["look"],))["version"]
        self.assertTrue(game.seen_robust_ok(self.store, fam, n))
        self.assertFalse(game.seen_robust_ok(self.store, fam, n + 1))
        self.assertEqual(game.look_seen_run(self.store, fam, n), self.store.family("tour-a")["state"]["best_train_run"])
        self.land(out["look"], 2.0, 2.0)
        self.assertEqual(game.candidate(self.store, fam), n)
        self.assertEqual(game.validations_left(self.store, fam, self.settings), 2)
        for v in (n, n, n + 1):
            self.store.add_run("tour-a", v, {"run_id": f"val-{v}-{self.tags}", "status": "ok", "trials": 1, "summary": {}},
                               window="validation", stress=1.0, purpose="validation")
            self.tags += 1
        self.assertEqual(game.validations_left(self.store, fam, self.settings), 0, "two versions validated: two tries")
        control = self.family("tour-b")
        self.assertFalse(game.seen_robust_ok(self.store, control, 1))


# ------------------------------------------------------------------------------------------------ 9. reproduction
class Reproduction(GameCase):
    def test_parents_bootstrap_rule_then_the_top_decile_of_the_window(self):
        fams = [self.family(f"par-{i}") for i in range(6)]
        for fam, f in zip(fams, (1.2, 0.99, 1.0, -0.5, None, 0.4)):
            self.plant(fam, f, 0.0)
        self.assertEqual([p["family"] for p in game.parents(self.store, self.settings)], ["par-0", "par-2"],
                         "under 30 looks: F of at least 1.0")
        more = [self.family(f"many-{i}") for i in range(30)]
        for i, fam in enumerate(more):
            self.plant(fam, 0.05 * i, 0.0)  # 0 .. 1.45
        # 36 looks: the top decile is the best ceil(3.6) = 4 (1.45, 1.4, 1.35 and 1.3); par-0's 1.2 no longer qualifies.
        top = [p["family"] for p in game.parents(self.store, self.settings)]
        self.assertEqual(top, ["many-29", "many-28", "many-27", "many-26"])
        self.clock.advance(73 * 3600)
        self.assertEqual(game.parents(self.store, self.settings), [], "looks older than the window count for nothing")

    def test_a_child_is_its_parents_program_card_and_lineage_with_a_neutral_id_and_a_directive(self):
        mother = self.family("breed-a")
        cards.put(self.store, mother["id"], {"hypothesis": "who pays and why", "mechanism_class": "x"}, "debit_vertical")
        seq = self.plant(mother, 2.0, 0.0)
        looked = self.store.version(mother["id"], self.store._one("SELECT version FROM game_looks WHERE seq=?", (seq,))["version"])
        self.version(mother["id"])  # a later version: the child gets the looked one
        self.settings["game"]["crossover_share"] = 0.0
        [first] = game.reproduce(self.store, self.settings)
        child = self.store.family(first)
        self.assertRegex(child["id"], r"^g-[0-9a-f]{8}$")
        self.assertEqual((child["lineage"], child["parent"], child["origin"]), (mother["lineage"], mother["id"], "game"))
        v1 = self.store.version(first, 1)
        self.assertEqual((v1["code"], v1["params"]), (looked["code"], looked["params"]))
        own = cards.card_of(self.store, first)
        self.assertTrue(own["own"])
        self.assertEqual(own["card"], cards.card_of(self.store, mother["id"])["card"])
        h = int.from_bytes(hashlib.sha256(mother["id"].encode()).digest()[:8], "big")
        self.assertEqual(child["spec"]["game_directive"], h % 6)
        self.assertIn(game.CHILD_NOTE, self.store.notebook(first)[-1]["text"])
        self.assertIn(game.DIRECTIVES[h % 6], game.brief_text(self.store, child, self.settings))
        self.assertEqual(game.reproduce(self.store, self.settings), [], "the parent's cooldown")
        self.clock.advance(6 * 3600 + 1)
        self.plant(mother, 2.0, 0.0)  # a fresh look in the window
        [second] = game.reproduce(self.store, self.settings)
        self.assertEqual(self.store.family(second)["spec"]["game_directive"], (h + 1) % 6, "the next sibling's directive")
        self.assertEqual(game.fold(self.store.family(second)["lineage"]), game.fold(mother["lineage"]))
        self.assertEqual(self.store._one("SELECT generation FROM game_looks WHERE seq=?",
                                         (self.plant(self.store.family(second), 0.1, 0.1),))["generation"], 1)

    def test_crossover_takes_a_donor_of_the_same_fold_group_another_lineage_and_a_short_program(self):
        self.settings["game"]["crossover_share"] = 1.0
        year = 2020
        used = set()

        def name(prefix, fold=year):
            n = self.named(fold, prefix=prefix, skip=used)
            used.add(n)
            return n

        signal = self.family(name("sig"))
        self.plant(signal, 3.0, 0.0)
        good = self.family(name("donor"))
        self.plant(good, 1.5, 0.0)
        other_fold = self.family(name("far", 2021))
        self.plant(other_fold, 2.9, 0.0)
        long_ = self.family(name("long"))
        v = self.store.add_version(long_["id"], "NEEDS = {'roots': ['SPY']}\n" + "#" * 7000, {}, author="test")
        with self.store.atomic():
            seq = game._record_look(self.store, long_, "game", "ladder", v, game.cfg(self.settings), seen_score=1.0)
        game._result(self.store, seq, "ok", {"2020": {"eligible": True, "F": 2.8}, "2021": {"eligible": True, "F": 0.0}}, "PASS")
        born = game.reproduce(self.store, self.settings)
        kids = {self.store.family(k)["parent"]: self.store.family(k) for k in born}
        donor = kids[signal["id"]]["spec"]["game_donor"]
        self.assertEqual(donor["family"], good["id"], "the only donor of its fold group, another lineage, at most 6,000 chars")
        self.assertEqual(kids[signal["id"]]["lineage"], signal["lineage"], "the signal parent's lineage only")
        self.assertNotIn("game_directive", kids[signal["id"]]["spec"])
        self.assertIn("donor's program", game.brief_text(self.store, kids[signal["id"]], self.settings))
        self.assertIn("game_directive", kids[other_fold["id"]]["spec"], "no donor in its fold group: it mutates")
        self.assertEqual(self.store._one("SELECT op FROM game_children WHERE child=?", (kids[signal["id"]]["id"],))["op"],
                         "crossover")

    def test_the_parent_round_day_and_ceiling_caps(self):
        fams = [self.family(f"cap-{i}") for i in range(8)]
        for fam in fams:
            self.plant(fam, 2.0, 0.0)
        self.assertEqual(len(game.reproduce(self.store, self.settings)), 4, "four a round")
        self.settings["game"]["children_per_day"] = 6
        self.assertEqual(len(game.reproduce(self.store, self.settings)), 2, "six in 24 hours")
        self.assertEqual(game.reproduce(self.store, self.settings), [])
        self.settings["game"]["children_per_day"] = 24
        self.clock.advance(7 * 3600)
        for fam in fams:
            self.plant(fam, 2.0, 0.0)
        alive = len(self.store.families(alive=True))
        self.settings["population"]["ceiling"] = alive + 1
        self.assertEqual(len(game.reproduce(self.store, self.settings)), 1, "the population ceiling")
        self.settings["population"]["ceiling"] = 96
        mother = self.family("cap-mother")
        for _ in range(4):
            self.clock.advance(7 * 3600)
            self.plant(mother, 9.0, 0.0)
            game.reproduce(self.store, self.settings)
        kids = self.store._all("SELECT child FROM game_children WHERE parent=?", (mother["id"],))
        self.assertEqual(len(kids), 3, "three living children a parent")
        self.store.retire(kids[0]["child"], "test")
        self.clock.advance(7 * 3600)
        self.plant(mother, 9.0, 0.0)
        self.assertIn(mother["id"], [self.store.family(k)["parent"] for k in game.reproduce(self.store, self.settings)])

    def test_reproduction_never_reads_the_confirm_table_and_shadow_breeds_nothing(self):
        fam = self.family("blind-a")
        self.plant(fam, 2.0, 2.0, confirm=True)
        statements = []
        real_all, real_one = self.store._all, self.store._one
        self.store._all = lambda sql, params=(): (statements.append(sql), real_all(sql, params))[1]
        self.store._one = lambda sql, params=(): (statements.append(sql), real_one(sql, params))[1]
        self.addCleanup(lambda: (setattr(self.store, "_all", real_all), setattr(self.store, "_one", real_one)))
        self.assertTrue(game.parents(self.store, self.settings))
        self.assertTrue(game.reproduce(self.store, self.settings))
        self.assertTrue(statements)
        self.assertFalse([s for s in statements if "game_confirms" in s])
        self.settings["game"]["mode"] = "shadow"
        self.clock.advance(7 * 3600)
        self.plant(fam, 2.0, 2.0)
        self.assertEqual(game.reproduce(self.store, self.settings), [])


# ------------------------------------------------------------------------------------------------ 11. retirement
class Retirement(GameCase):
    def test_four_looks_without_a_pass(self):
        fam = self.family("ret-a")
        for f in (0.5, 1.0, -1.0):
            self.plant(fam, f, 0.0)
        self.assertIsNone(game.retire_reason(self.store, self.store.family("ret-a"), self.settings))
        self.plant(fam, None, 0.0)
        reason = game.retire_reason(self.store, self.store.family("ret-a"), self.settings)
        self.assertEqual(reason, "spent its four private looks without a pass")
        other = self.family("ret-b")
        for f in (0.5, 1.0, -1.0, 1.3):
            self.plant(other, f, 0.0)
        self.assertIsNone(game.retire_reason(self.store, self.store.family("ret-b"), self.settings), "a pass")

    def test_two_failed_confirm_reads(self):
        fam = self.family("ret-c")
        self.plant(fam, 2.0, 0.5, confirm=False)
        self.assertIsNone(game.retire_reason(self.store, self.store.family("ret-c"), self.settings))
        self.plant(fam, 2.0, 0.4, confirm=False)
        self.assertEqual(game.retire_reason(self.store, self.store.family("ret-c"), self.settings),
                         "failed its private confirmation twice")

    def test_two_validation_tries_both_failed(self):
        fam = self.family("ret-d")
        for v, passed in ((1, False), (2, False)):
            self.store.add_run("ret-d", v, {"run_id": f"val-ret-{v}", "status": "ok", "trials": 1, "summary": {}},
                               window="validation", stress=1.0, purpose="validation")
        self.store.set_state("ret-d", validation_verdicts={"1": {"passed": False}, "2": {"passed": True}})
        self.assertIsNone(game.retire_reason(self.store, self.store.family("ret-d"), self.settings), "one passed")
        self.store.set_state("ret-d", validation_verdicts={"1": {"passed": False}, "2": {"passed": False}})
        reason = game.retire_reason(self.store, self.store.family("ret-d"), self.settings)
        self.assertEqual(reason, "used its two Validation tries")
        self.assertNotRegex(reason, r"\d")

    def test_each_rule_respects_the_floor_and_only_the_game_arm_in_gate_mode_retires(self):
        fam = self.family("ret-e")
        for _ in range(4):
            self.plant(fam, 0.1, 0.0)
        reason = game.retire_reason(self.store, self.store.family("ret-e"), self.settings)
        alive = len(self.store.families(alive=True))
        self.assertEqual(self.store.retire_gym("ret-e", reason, floor=alive, source="tournament")["deferred"], "population_floor")
        self.assertEqual(self.store.retire_gym("ret-e", reason, floor=0, source="tournament")["status"], "retired")
        self.assertIsNone(game.retire_reason(self.store, self.store.family("ret-e"), self.settings), "retired")
        shadow = on(mode="shadow")
        other = self.family("ret-f")
        for _ in range(4):
            self.plant(other, 0.1, 0.0)
        self.assertIsNone(game.retire_reason(self.store, self.store.family("ret-f"), shadow))
        self.assertIsNone(game.retire_reason(self.store, self.store.family("ret-f"), {}))
        self.store.set_band("ret-f", "probe", reason="test")
        self.assertIsNone(game.retire_reason(self.store, self.store.family("ret-f"), self.settings), "the Gym band only")


# ------------------------------------------------------------------------------------------------ 7-8. what agents see
class Visibility(GameCase):
    settings = on(arm_fraction=0.5)

    def by_arm(self, side, prefix):
        for i in range(200):
            fid = f"{prefix}-{i}"
            if canary.in_arm("ltcm-game-v1", "game-v1", fid, 0.5) == (side == "game") and self.store.family(fid) is None:
                return self.family(fid)
        raise AssertionError

    def test_the_graveyard_quarantine_for_every_reader(self):
        switch = dt.datetime(2026, 9, 28, 16, 10, tzinfo=dt.timezone.utc).timestamp()
        root = Path(self.dir.name) / "q"
        clock = Clock(switch - 5 * DAY)
        store = SwarmStore(root, clock=clock)
        self.addCleanup(store.close)

        def bury(fid, lesson):
            store.add_family({"id": fid, "mechanism": MECHANISM + " " + lesson, "structure": "debit_vertical", "roots": ["SPY"]},
                             origin="architect")
            return fid

        old = bury("pre-switch", "calls")
        store.retire_gym(old, "an old lesson about calls", floor=0, source="test")
        learned = bury("learned-hidden", "calls")
        clock.advance(6 * DAY)  # after the switch, before T0
        store.retire_gym(learned, "a lesson learned over 2020-24 calls", floor=0, source="test")
        clock.advance(DAY)
        settings = on(arm_fraction=0.5)
        game.t0(store, settings)
        clock.advance(60)
        sides = {}
        for i in range(40):
            fid = bury(f"new-{i}", "calls")
            side = game.arm(store, store.family(fid), settings)
            if side not in sides:
                sides[side] = fid
                store.retire_gym(fid, f"a {side} lesson about calls", floor=0, source="test")
            if len(sides) == 2:
                break
        names = [r["family"] for r in game.visible_graveyard(store, "calls", limit=10, settings=settings)]
        self.assertEqual(sorted(names), sorted([old, sides["control"]]))
        self.assertEqual(game.quarantined(store, settings), {learned, sides["game"]}, "for the readers of the table itself")
        self.assertEqual(game.quarantined(store, {}), frozenset())
        self.assertEqual([r["family"] for r in game.visible_graveyard(store, "", limit=10, settings={})],
                         [r["family"] for r in store.graveyard("", limit=10)], "the game off: the store's own read")
        self.assertEqual(game.visible_graveyard(store, "calls", limit=10, settings={}), store.graveyard("calls", limit=10))
        kept = game.visible_graveyard(store, "", 1, settings=settings)
        self.assertEqual(len(kept), 1)
        self.assertEqual(set(kept[0]), set(store.graveyard("", limit=1)[0]), "the store's row shape")

    def test_the_graveyard_ranks_over_the_visible_rows_only(self):
        """Non-interference: two stores alike but for game-arm graveyard rows read the same graveyard."""
        reads = []
        for extra in (False, True):
            root = Path(self.dir.name) / f"ni-{extra}"
            store = SwarmStore(root, clock=Clock(self.clock()))
            self.addCleanup(store.close)
            game.t0(store, self.settings)
            for fid, lesson in (("ctl-x", "calls after a low close"), ("ctl-y", "puts on a gap"), ("ctl-z", "calls calls")):
                if canary.in_arm("ltcm-game-v1", "game-v1", fid, 0.5):
                    continue
                store.add_family({"id": fid, "mechanism": MECHANISM, "structure": "debit_vertical", "roots": ["SPY"]}, origin="a")
                store.retire_gym(fid, lesson, floor=0, source="test")
            if extra:
                for i in range(30):
                    fid = f"gx-{i}"
                    if canary.in_arm("ltcm-game-v1", "game-v1", fid, 0.5):
                        store.add_family({"id": fid, "mechanism": MECHANISM, "structure": "debit_vertical", "roots": ["SPY"]},
                                         origin="game")
                        store.retire_gym(fid, "calls " * 30, floor=0, source="test")
            reads.append((game.visible_graveyard(store, "calls gap", limit=5, settings=self.settings),
                          [f["id"] for f in game.visible_families(store, settings=self.settings)]))
        self.assertTrue(reads[0][0], "a control lesson to read")
        self.assertEqual(reads[0], reads[1])
        self.assertEqual(reads[0][1], reads[1][1])

    def test_visible_families_drop_the_game_arm_alone(self):
        played = self.by_arm("game", "vis")
        control = self.by_arm("control", "vis")
        legacy = self.family("vis-legacy", roots=("TSLA",))
        names = [f["id"] for f in game.visible_families(self.store, alive=True, settings=self.settings)]
        self.assertEqual(sorted(names), sorted([control["id"], legacy["id"]]))
        self.assertNotIn(played["id"], names)
        self.assertEqual(game.visible_families(self.store, alive=True, settings={}), self.store.families(alive=True))

    def test_status_and_brief_carry_no_hidden_figure_year_or_result(self):
        played = self.by_arm("game", "txt")
        control = self.by_arm("control", "txt")
        _, out = self.look(played["id"], 1.0)
        self.land(out["look"], 1.3721, 2.4567)
        text = game.status_text(self.store, self.store.family(played["id"]), self.settings)
        self.assertIn("PRIVATE EXAM", text)
        self.assertIn("Looks used: 1 of 4", text)
        self.assertNotRegex(text, r"20(20|21)|1\.37|2\.45|PASS|ALIVE|FAIL")
        self.assertEqual(game.status_text(self.store, control, self.settings), "")
        self.assertEqual(game.status_text(self.store, self.store.family(played["id"]), on(mode="shadow")), "")
        self.assertEqual(game.brief_text(self.store, self.store.family(played["id"]), self.settings), "", "a founder: no change")
        for directive in game.DIRECTIVES + (game.CHILD_NOTE, game.CROSSOVER, game.STATUS):
            self.assertNotRegex(directive, r"20(20|21)")


# ------------------------------------------------------------------------------------------------ control's extra looks
class ControlLooks(GameCase):
    settings = on(arm_fraction=0.5)

    def test_control_looks_at_each_validated_version_once_and_reads_nothing(self):
        fid = next(f"ctl-{i}" for i in range(200) if not canary.in_arm("ltcm-game-v1", "game-v1", f"ctl-{i}", 0.5))
        fam = self.family(fid)
        n = self.best(fid, 1.0)
        self.store.set_state(fid, validation_version=n)
        [seq] = game.shadow_validated(self.store, self.settings, self.pool)
        row = self.store._one("SELECT * FROM game_looks WHERE seq=?", (seq,))
        self.assertEqual((row["arm"], row["role"], row["seen_score"]), ("control", "validated", 1.0))
        self.assertEqual(game.shadow_validated(self.store, self.settings, self.pool), [], "once")
        self.land(seq, 3.0, 3.0)
        self.assertEqual(self.store._all("SELECT * FROM game_confirms"), [], "control's looks are records only")
        self.assertEqual(game.looks_used(self.store, fam), 0, "a validated look counts against nothing")
        self.assertEqual(game.shadow_validated(self.store, {}, self.pool), [])


# ------------------------------------------------------------------------------------------------ the operator's metrics
class Metrics(GameCase):
    def test_metrics_are_aggregate_finite_and_reproducible(self):
        rng = random.Random(4)
        fams = [self.family(f"met-{i}") for i in range(12)]
        for fam in fams:
            for _ in range(3):
                f = rng.uniform(-1, 3)
                self.plant(fam, f, 0.5 * f + rng.uniform(-0.5, 0.5))
        self.settings["game"]["crossover_share"] = 0.0
        kids = game.reproduce(self.store, self.settings)
        for k in kids:
            self.plant(self.store.family(k), 2.0, 2.0)
        a = game.metrics(self.store, settings=self.settings, draws=200)
        b = game.metrics(self.store, settings=self.settings, draws=200)
        self.assertEqual(a, b)
        text = json.dumps(a, allow_nan=False)  # no infinity or NaN anywhere
        self.assertIn("R6", text)
        both = [game._operator_years(r) for r in game._rows(self.store) if r["status"] == "ok"]
        self.assertAlmostEqual(a["R2"]["rho_hidden"], game.spearman([x for x, _ in both], [y for _, y in both]), places=12)
        self.assertEqual(a["R5"]["all"]["children"]["by_op"]["mutate"], len(kids))
        self.assertTrue(a["R1"]["leak"]["passed"])
        self.assertIsNotNone(a["R4"]["G"])
        self.assertEqual(game.spearman([1, 2, 3, 4], [1, 2, 3, 4]), 1.0)
        self.assertAlmostEqual(game.spearman([1, 1, 2], [3, 3, 1]), -1.0, places=12)

    def test_the_leak_scan_finds_a_hidden_year_or_figure_in_a_conversation(self):
        fam = self.family("leak-a")
        self.plant(fam, 1.3721, 0.0)
        self.store.save_convo(fam["id"], [{"role": "tool", "content": "ok"}])
        self.assertTrue(game.metrics(self.store, draws=0)["R1"]["leak"]["passed"])
        self.store.save_convo(fam["id"], [{"role": "tool", "content": "F was 1.3721 on 2021-03-01"}])
        hits = game.metrics(self.store, draws=0)["R1"]["leak"]["hits"]
        self.assertEqual(sorted(h["kind"] for h in hits), ["hidden figure", "hidden year"])


# ------------------------------------------------------------------------------------------------ 13. the CI wall
class Wall(unittest.TestCase):
    def test_game_py_is_protected_by_the_updater_and_the_gateway(self):
        self.assertIn("league/swarm/game.py", ci.FORBIDDEN)
        source = (Path(ci.REPO) / "gateway" / "lib" / "protected.mjs").read_text(encoding="utf-8")
        self.assertIn("'league/swarm/game.py'", source)

    def test_the_tables_are_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            store = SwarmStore(Path(d), clock=Clock())
            try:
                game.ensure(store)
                store._exec("INSERT INTO game_children(at, child, parent, op) VALUES('x','c','p','mutate')")
                for sql in ("UPDATE game_children SET op='crossover'", "DELETE FROM game_children"):
                    with self.assertRaises(Exception):
                        store._exec(sql)
                for table in ("game_looks", "game_results", "game_confirms"):
                    names = {r["name"] for r in store._all("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
                                                         (table,))}
                    self.assertEqual(names, {f"{table}_no_update", f"{table}_no_delete"})
            finally:
                store.close()

    def test_standard_library_and_the_packages_own_modules_only(self):
        source = (Path(ci.REPO) / "league" / "swarm" / "game.py").read_text()
        imports = re.findall(r"^\s*(?:from|import) ([\w.]+)", source, re.M)
        allowed = {"__future__", "datetime", "hashlib", "json", "math", "random", "re", "threading", "time", "typing", ".",
                   ".pool", "..gym.results", ".researcher", ".store"}
        self.assertEqual(set(imports) - allowed, set())



# ------------------------------------------------------------------------------------------------ 5. the tournament ("gate")
def round_settings(**over):
    """The swarm's defaults with the game on ("gate", every new lineage in the game arm unless `arm_fraction` says
    otherwise), the drift screen off (these versions carry no drift figures; test_swarm_drift tests it) and no floor."""
    out = copy.deepcopy(S.DEFAULTS)
    out["game"] = {"enabled": True, "mode": "gate", "arm_fraction": 1.0, **over}
    out["tournament"]["drift_screen"] = False
    out["population"].update(floor=0, start=2, ceiling=96)
    out["gate"]["look_holds"] = None
    return out


def arm_id(side, prefix, fraction=0.5, *, taken=()):
    """A family id whose lineage plays `side` ("game" or "control") under the canary's split at `fraction`."""
    for i in range(1000):
        fid = f"{prefix}-{i}"
        if fid not in taken and canary.in_arm(game.FOLD_SALT, game.ARM_KEY, fid, fraction) == (side == "game"):
            return fid
    raise AssertionError("no such id")


class RoundPool(FakePool):
    """The tournament's fake Gym: a Validation job answered at once (`answer`), any other job recorded; its image and
    bundle (None until a test sets them), stamped on each answer."""

    def __init__(self, answer=None):
        super().__init__()
        self.answer = answer or (lambda job: result(job.name, window=job.window))
        self.img = self.bnd = None

    def image(self, kind="gym"):
        return self.img

    def bundle(self):
        return self.bnd

    def wait(self, job, timeout=None, late=None, late_fail=None):
        out = self.answer(job)
        if self.img is not None:
            out.update(gym_image=self.img, gym_bundle=self.bnd)
        return out

    def run(self, job, timeout=None, late=None, late_fail=None):
        return self.wait(self.submit(job), timeout, late, late_fail)

    def cancel_family(self, family):
        pass

    def validations(self):
        return [(j.family, j.version) for j in self.jobs if j.window == "validation"]


class TournamentGate(GameCase):
    """THE LEARNING GAME in the hourly round (league/swarm/tournament.py, its section 7), mode "gate"."""

    settings = round_settings()

    def setUp(self):
        super().setUp()
        self.gym = RoundPool()
        self.tour = Tournament(self.store, self.gym, self.settings, clock=self.clock, rng=random.Random(1))

    def looked(self, seq):
        return self.store._one("SELECT version FROM game_looks WHERE seq=?", (seq,))["version"]

    def seen_best(self, fid, score):
        """A new best whose Train run carries this Gym's image and bundle (the evaluator's eligible Train run)."""
        v = self.version(fid)
        run = self.store.add_run(fid, v["n"], {"run_id": f"seen-{fid}-{v['n']}", "status": "ok", "trials": 1,
                                               "summary": {"train_score": score, "train_eligible": True, "train_from": game.SEEN_FROM,
                                                           "gym_image": "img", "gym_bundle": "b"}},
                                 window="train", stress=1.0, purpose="train")
        self.store.update_family(fid, best_train=score)
        self.store.set_state(fid, best_train_version=v["n"], best_train_run=run["run_id"])
        return v["n"]

    def test_the_candidate_is_the_latest_confirmed_version_or_none(self):
        fam = self.family("tg-a")
        n = self.best("tg-a", 2.0)
        self.store.update_family("tg-a", best_version=n)  # a submission: not what the game validates
        self.assertIsNone(self.tour.candidate_version(self.store.family("tg-a")))
        self.plant(fam, 2.0, 0.5, confirm=False)
        self.assertIsNone(self.tour.candidate_version(self.store.family("tg-a")), "a failed CONFIRM sends nothing")
        self.plant(fam, 2.0, 2.0, confirm=True)
        latest = self.plant(fam, 2.0, 2.0, confirm=True)
        self.assertEqual(self.tour.candidate_version(self.store.family("tg-a")), self.looked(latest))
        self.assertEqual(self.tour.validate(self.store.families(alive=True))["queued"], 1)
        self.assertEqual(self.gym.validations(), [("tg-a", self.looked(latest))])
        self.assertEqual(self.store.family("tg-a")["validated_version"], self.looked(latest), "judged: the candidate held")
        self.family("tg-legacy", roots=("TSLA",))
        m = self.best("tg-legacy", 1.0)
        self.assertEqual(self.tour.candidate_version(self.store.family("tg-legacy")), m, "legacy: best Train, as today")
        shadow = Tournament(self.store, self.gym, {**self.settings, "game": {**self.settings["game"], "mode": "shadow"}})
        self.assertEqual(shadow.candidate_version(self.store.family("tg-a")), n, "shadow: today's rule")
        off = Tournament(self.store, self.gym, {**self.settings, "game": {"enabled": False, "mode": "gate"}})
        self.assertEqual(off.candidate_version(self.store.family("tg-a")), n, "off: today's rule")

    def test_two_validation_tries_and_a_tried_version_again_is_no_new_try(self):
        fam = self.family("tg-b")
        first = self.looked(self.plant(fam, 2.0, 2.0, confirm=True))
        self.tour.validate(self.store.families(alive=True))
        second = self.looked(self.plant(fam, 2.0, 2.0, confirm=True))
        self.tour.validate(self.store.families(alive=True))
        self.assertEqual(game.validations_left(self.store, fam, self.settings), 0)
        self.tour.validate(self.store.families(alive=True))
        self.assertEqual(self.gym.validations(), [("tg-b", first), ("tg-b", second)], "validated once on this Gym")
        self.gym.img, self.gym.bnd = "img-2", "bundle-2"  # an adoption: the version tried last is validated again
        self.tour.validate(self.store.families(alive=True))
        self.assertEqual(self.gym.validations()[-1], ("tg-b", second), "a tried version again is no new try")
        third = self.looked(self.plant(fam, 2.0, 2.0, confirm=True))
        self.assertEqual(self.tour.candidate_version(self.store.family("tg-b")), third)
        jobs = len(self.gym.validations())
        self.tour.validate(self.store.families(alive=True))
        self.assertEqual(len(self.gym.validations()), jobs, "its two tries are used: the third CONFIRMED version waits")

    def test_the_looks_seen_run_is_an_eligible_train_run(self):
        from league.swarm.evaluator import KEY

        self.store.put(KEY, {"image": "img", "bundle": "b", "execution": "x"})
        self.gym.img, self.gym.bnd = "img", "b"
        self.family("tg-c")
        n = self.seen_best("tg-c", 1.0)
        out = game.maybe_look(self.researcher, "tg-c", n, seen_run())
        self.land(out["look"], 2.0, 2.0)
        self.seen_best("tg-c", 3.0)  # a newer best: the family's best Train run is another version's now
        with mock.patch.object(game, "look_seen_run", return_value=None):
            waiting = self.tour.validate(self.store.families(alive=True))["waiting_robustness"]
        self.assertEqual((waiting, self.gym.validations()), (["tg-c"], []), "without the look's run: no eligible Train run")
        self.tour.validate(self.store.families(alive=True))
        self.assertEqual(self.gym.validations(), [("tg-c", n)])

    def test_the_robustness_bypass_is_the_game_candidates_alone(self):
        played = self.family("tg-d")
        n = self.looked(self.plant(played, 2.0, 2.0, confirm=True))
        self.assertIsNone(researcher_mod.robust_at_stress(self.store.family("tg-d")["state"], n), "no 1.5x row in its state")
        self.family("tg-e", roots=("TSLA",))
        self.best("tg-e", 2.0)  # legacy: its 1.5x run has not landed
        out = self.tour.validate(self.store.families(alive=True))
        self.assertEqual((self.gym.validations(), out["waiting_robustness"]), ([("tg-d", n)], ["tg-e"]))

    def test_the_games_reasons_come_first_under_the_floor(self):
        fam = self.family("tg-f")
        for _ in range(4):
            self.plant(fam, 0.5, 0.0)
        self.family("tg-g", roots=("TSLA",))
        legacy = self.family("tg-h", roots=("TSLA",))
        for _ in range(4):
            self.plant(legacy, 0.5, 0.0, side="game")  # records only: a legacy family is never the game's to retire
        self.settings["population"]["floor"] = 5
        self.assertEqual(self.tour.retirements(self.store.families(alive=True)), [], "the floor holds it")
        self.settings["population"]["floor"] = 0
        self.assertEqual(self.tour.retirements(self.store.families(alive=True)),
                         [{"family": "tg-f", "why": "spent its four private looks without a pass"}])
        self.assertEqual(self.store.family("tg-f")["band"], "retired")
        [row] = [r for r in self.store.graveyard(limit=10) if r["family"] == "tg-f"]
        self.assertNotRegex(row["lesson"], r"20(20|21)|PASS|ALIVE|FAIL")

    def test_the_games_validation_wait_spares_only_a_confirmed_version_or_a_look_out(self):
        self.settings["researcher"]["dormant_cycles"] = 5
        self.family("tg-i")
        n = self.best("tg-i", 1.0)
        self.store.set_state("tg-i", dormant_cycles=9)
        out = game.maybe_look(self.researcher, "tg-i", n, seen_run())
        self.assertIsNone(self.tour.idle_why(self.store.family("tg-i")), "its look is out")
        self.land(out["look"], 0.5, 0.5)  # ALIVE: no CONFIRM, so its best is never validated
        fam = self.store.family("tg-i")
        self.assertTrue(researcher_mod.awaiting_validation(fam), "today's wait would spare it for ever")
        self.assertIsNone(researcher_mod.idle_dead(fam, self.settings))
        why = self.tour.idle_why(fam)
        self.assertIn("made no new Gym evaluation in its last 9 cycles", why)
        self.assertNotRegex(why, r"20(20|21)|private|exam|look")
        self.plant(fam, 2.0, 2.0, confirm=True)  # a CONFIRMED version awaits Validation: spared
        self.assertIsNone(self.tour.idle_why(self.store.family("tg-i")))
        self.family("tg-j", roots=("TSLA",))  # legacy, in the same state: today's wait spares it
        m = self.best("tg-j", 1.0)
        self.store.set_state("tg-j", dormant_cycles=9)
        self.assertIsNone(self.tour.idle_why(self.store.family("tg-j")))
        self.assertTrue(researcher_mod.awaiting_validation(self.store.family("tg-j")), m)
        shadow = Tournament(self.store, self.gym, {**self.settings, "game": {**self.settings["game"], "mode": "shadow"}},
                            clock=self.clock)
        self.family("tg-k")
        k = self.best("tg-k", 1.0)
        self.store.set_state("tg-k", dormant_cycles=9)
        self.land(game.maybe_look(self.researcher, "tg-k", k, seen_run())["look"], 0.5, 0.5)
        self.assertIsNone(shadow.idle_why(self.store.family("tg-k")), "shadow: today's rules")
        self.assertIsNotNone(self.tour.idle_pass()["retired"], "the idle pass reads the same rule")
        self.assertIn("tg-k", [r["family"] for r in self.store.graveyard(limit=20)])

    def test_a_round_bears_the_games_children_and_survives_a_game_error(self):
        fam = self.family("tg-l")
        self.plant(fam, 2.0, 0.0)  # a parent (F of at least 1.0 before thirty looks)
        row = self.tour.run()
        [child] = [b for b in row["born"] if b.startswith("g-")]
        self.assertEqual((self.store.family(child)["parent"], self.store.family(child)["origin"]), ("tg-l", "game"))
        self.assertGreater(self.store.family(child)["weight"], 0, "the second allocation gives the child its share")
        self.assertFalse([e for e in self.store.events_after(0) if e["kind"] == "swarm.born" and e["family"] == child])
        self.clock.advance(3600)
        with mock.patch.object(game, "requeue_stale", side_effect=RuntimeError("a figure 3.1415 of 2021")):
            self.tour.run()
        [event] = [e["payload"] for e in self.store.events_after(0)
                   if e["kind"] == "swarm.status" and e["payload"].get("action") == "game_error"]
        self.assertEqual(event, {"action": "game_error", "step": "requeue_stale", "error": "RuntimeError"}, "its type, never its words")


# ------------------------------------------------------------------------------------------------ 5. main's round, byte for byte
class Golden(unittest.TestCase):
    """Control and legacy families play main's round (ab64c68b) byte for byte, with the game on in "gate" or "shadow", off,
    or absent (league/tests/game_golden.py; `python -m league.tests.game_golden` on main's tree wrote the golden)."""

    GATE = {"enabled": True, "mode": "gate", "arm_fraction": 0.5}

    def test_the_golden_ids_are_control_and_legacy(self):
        for fid in game_golden.CONTROL:
            self.assertFalse(canary.in_arm(game.FOLD_SALT, game.ARM_KEY, fid, 0.5), fid)
        self.assertEqual(game_golden.T0_KEY, game.T0_KEY)
        self.assertEqual(game_golden.GAME_EVENTS, (game.EVENT,))
        self.assertEqual(game_golden.GAME_PURPOSES, (game.PURPOSE,))

    def test_control_and_legacy_play_mains_round_byte_for_byte(self):
        golden = json.loads(game_golden.GOLDEN.read_text(encoding="utf-8"))
        for name, block in (("no game block", None), ("off", {"enabled": False, "mode": "gate"}), ("gate", self.GATE),
                            ("shadow", {**self.GATE, "mode": "shadow"})):
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.assertEqual(game_golden.play(d, block), golden, name)

    def test_in_gate_the_game_played_beside_them(self):
        with tempfile.TemporaryDirectory() as d:
            game_golden.play(d, self.GATE)
            store = SwarmStore(Path(d), readonly=True)
            try:
                looks = {(r["family"], r["arm"], r["role"]) for r in store._all("SELECT * FROM game_looks")}
                events = [e for e in store.events_after(0) if e["kind"] == game.EVENT]
            finally:
                store.close()
        self.assertEqual(looks, {("golden-0", "control", "validated"), ("golden-1", "control", "validated")},
                         "control's records of the versions it validated; the legacy family's none")
        self.assertEqual(len(events), 2)


# ------------------------------------------------------------------------------------------------ 10. the allocation
class AllocationBlind(GameCase):
    settings = on(arm_fraction=0.5)

    def rows(self, settings):
        seen = {}

        def capture(rows, post, conf):
            seen.update({r["id"]: r for r in rows})
            return {}, {}

        with mock.patch.object(allocation, "value_shares", capture):
            allocation.allocate_from_store(self.store, self.store.families(alive=True), settings, now=self.clock())
        return seen

    def test_a_game_arm_familys_validation_t_never_enters_its_row(self):
        played, control = arm_id("game", "alloc"), arm_id("control", "alloc")
        legacy = "alloc-tsla"
        for fid in (played, control, legacy):
            self.family(fid, roots=("TSLA",) if fid == legacy else ("SPY",))
            self.store.update_family(fid, validations=1)
            self.store.set_state(fid, validation_numbers={"mean": 0.05, "t": 3.0, "sharpe_daily": 0.2, "quarters": "4/4"})
        rows = self.rows(self.settings)
        self.assertEqual((rows[played]["t"], rows[control]["t"], rows[legacy]["t"]), (None, 3.0, 3.0))
        for other in (on(arm_fraction=0.5, mode="shadow"), {"game": {"enabled": False, "mode": "gate"}}, {}):
            with self.subTest(other):
                self.assertEqual({k: r["t"] for k, r in self.rows(other).items()}, {played: 3.0, control: 3.0, legacy: 3.0})
        self.assertEqual({k: r for k, r in rows.items() if k != played},
                         {k: r for k, r in self.rows({}).items() if k != played}, "control and legacy rows unchanged")
        self.assertEqual({k: v for k, v in rows[played].items() if k != "t"},
                         {k: v for k, v in self.rows({})[played].items() if k != "t"}, "only its t is withheld")

# ------------------------------------------------------------------------------------------------ 7. the leak tests
#: A hidden year as a quoted key or an ISO date (the operator's leak scan, `game._HIDDEN_TEXT`), and the hidden figures
#: `ResearcherLeaks` plants (t_alpha on the SELECT and CONFIRM years, t_net on both), each at the precisions a view rounds to.
HIDDEN_TEXT = re.compile(r'\\*"20(?:20|21)\\*"|(?<!\d)20(?:20|21)-\d\d-\d\d')
PLANTED = (3.1415926, 2.7182818, 4.6692016)
PLANTED_TEXT = ("3.14", "2.718", "4.669", "4.67")


class ResearcherLeaks(GameCase):
    """7a: a game-arm family whose hidden looks landed (a SELECT PASS and its CONFIRM read, figures planted) sees no hidden
    figure and no 2020 or 2021 year key or date in anything the researcher is shown: the system prompt, the brief, the
    status, every tool's answer over two model cycles (a sweep and its table, read_run's sections, the notebook, the
    graveyard, a gym_run and its score block), its conversation as the store keeps it, and its notebook."""

    def setUp(self):
        from league.swarm.models import ModelRouter
        from league.swarm.seeds import SEEDS, family_spec, program_for
        from league.tests.swarm_fakes import provider
        from league.tests.test_swarm_inputs import card, install
        from league.tests.test_swarm_search import yearly
        from league.tests.test_swarm_sweep import SweepPool

        super().setUp()
        self.settings.clear()
        self.settings.update(round_settings())
        self.settings["gym"]["image_checkpoint"] = "sbcp_synthetic_a"
        install(Path(self.dir.name), card())  # an input card audited from 2020-01-02: the 2020 image's
        from league.swarm import inputs

        inputs._read.cache_clear()
        self.steps: list = []
        self.provider, self.sail = provider(Path(self.dir.name) / "p.sqlite",
                                            lambda body: (self.steps.pop(0) if self.steps else {"text": "done"}))
        self.addCleanup(self.provider.close)
        self.router = ModelRouter(self.store, self.provider, settings=self.settings)
        self.gym = SweepPool(lambda job: yearly(job.name, roots=job.roots))
        spec = next(s for s in SEEDS if s["id"] == "condor-vrp")
        self.fid = self.store.add_family({**family_spec(spec), "id": "leak-vrp"}, origin="seed")["id"]
        self.program_for = program_for

    def real(self):
        """The researcher itself (GameCase's `researcher` is the namespace `maybe_look` reads)."""
        from league.swarm.researcher import Researcher

        return Researcher(self.store, self.router, self.gym, self.settings, clock=self.clock, starter=self.program_for,
                          background=False)

    def landed_look(self):
        """The starter's run, its 1.5x run landing with a profit (the look opens) and the hidden run landing: a SELECT PASS
        and a CONFIRMED read, every figure planted."""
        from league.tests.test_swarm_search import yearly

        self.real().cycle(self.fid)
        [stress] = [j for j in self.gym.jobs if j.purpose == "robustness" and j.stress == 1.5]
        stress.late(yearly(stress.name, roots=stress.roots, stress=1.5, pnl=300.0))
        [private] = [j for j in self.gym.jobs if j.purpose == game.PURPOSE]
        select, confirm = game.fold(self.store.family(self.fid)["lineage"])
        figures = {select: PLANTED[0], confirm: PLANTED[1]}
        private.late(hidden(figures[2020], figures[2021], roots=private.roots, t_net=PLANTED[2]))
        [row] = game._rows(self.store, "family=?", (self.fid,), confirms=True)
        self.assertEqual((row["status"], row["tier"], game.confirm_view(row)["confirmed"]), ("ok", "PASS", True))
        self.assertIn(f"{PLANTED[0]:.4f}"[:5], json.dumps(row["years"]), "the figures are planted where the game keeps them")
        return row

    def assert_clean(self, text, where):
        self.assertIsNone(HIDDEN_TEXT.search(text), f"{where}: a hidden year key or date")
        for figure in PLANTED_TEXT:
            self.assertNotIn(figure, text, f"{where}: a hidden figure")

    def test_nothing_a_game_researcher_is_shown_carries_a_hidden_year_or_figure(self):
        row = self.landed_look()
        researcher = self.real()
        # The graveyard: a legacy family's lesson (a root outside the core five) is read; a game-arm family's, whose notes
        # name a hidden figure and date, never is.
        self.store.add_family({"id": "leak-tsla", "mechanism": MECHANISM, "structure": "debit_vertical", "roots": ["TSLA"]},
                              origin="architect")
        self.store.retire_gym("leak-tsla", "Refuted: the calls never paid after fees", floor=0, source="test")
        self.store.add_family({"id": "leak-dead", "mechanism": MECHANISM, "structure": "debit_vertical", "roots": ["SPY"]},
                              origin="architect")
        self.store.note("leak-dead", "F was 3.1415 on 2021-03-01 in the private exam")
        self.store.retire_gym("leak-dead", "Refuted: the calls never paid", floor=0, source="test")
        fam = self.store.family(self.fid)
        best = fam["state"]["best_train_run"]
        self.steps = [{"calls": [("gym_sweep", {"variants": [{"vrp_min": 1.3}, {"vrp_min": 1.5}], "why": "a grid"})]},
                      {"calls": [("read_run", {"run_id": best, "section": section}) for section in ("summary", "drift", "daily",
                                                                                                      "trades")]
                       + [("notebook", {"action": "read"}), ("graveyard", {"query": "calls refuted"})]},
                      {"text": "Next I change the exit rule."}]
        researcher.cycle(self.fid)
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.45}, "why": "between the two"})]}, {"text": "ok"}]
        researcher.cycle(self.fid)
        shown = json.dumps(self.sail.bodies)
        self.assertIn("leak-tsla", shown, "the graveyard tool answered")
        self.assertNotIn("leak-dead", shown, "never a game-arm lesson")
        self.assertIn("PRIVATE EXAM", shown, "the status was rendered with its look counted")
        self.assertIn("Looks used: 1 of 4", shown)
        self.assertIn("Card: unknown (span_mismatch)", shown, "the 2020 image's card is not shown under a 2022 Train")
        outputs = [o for body in self.sail.bodies for o in body.get("input", [])
                   if isinstance(o, dict) and o.get("type") == "function_call_output"]
        self.assertGreaterEqual(len(outputs), 7, "the sweep, four sections, the notebook, the graveyard and the run")
        self.assert_clean(shown, "the model's inputs")
        self.assert_clean(json.dumps(self.store.convo(self.fid)), "the stored conversation")
        self.assert_clean(json.dumps(self.store.notebook(self.fid, limit=100)), "the notebook")
        fam = self.store.family(self.fid)
        for name, text in (("brief", researcher.brief(fam)), ("status", researcher.status(fam)),
                           ("train view", json.dumps([r["summary"] for r in self.store.runs(self.fid, limit=100)])),
                           ("graveyard", json.dumps(researcher._local_tool(fam, "graveyard", {"query": ""}, {})))):
            self.assert_clean(text, name)
        self.assertNotIn(str(row["select_year"]), researcher.status(fam))
        report = game.metrics(self.store, settings=self.settings, draws=0)
        self.assertTrue(report["R1"]["leak"]["passed"], report["R1"]["leak"])
        self.assertEqual(report["R1"]["leak"]["families"], 1)


class ImportWall(unittest.TestCase):
    """7b: only the named modules import the game, and no module but game.py reads its tables."""

    IMPORTERS = {"league/swarm/researcher.py", "league/swarm/tournament.py", "league/swarm/allocation.py",
                 "league/swarm/architect.py", "league/swarm/strategist.py", "league/swarm/diagnostician.py",
                 "league/swarm/loop.py", "league/ops/game_report.py"}

    def test_only_the_named_modules_import_the_game_and_none_but_it_reads_its_tables(self):
        from league.tests.test_swarm_settings_policy import imported

        repo = Path(ci.REPO)
        importers, readers = set(), set()
        tables = re.compile(r"\bgame_(?:looks|results|confirms|children)\b")
        for path in sorted([*(repo / "league").rglob("*.py"), *(repo / "scripts").rglob("*.py"), *(repo / "ltcm").rglob("*.py")]):
            rel = path.relative_to(repo).as_posix()
            if rel.startswith("league/tests/") or rel == "league/swarm/game.py" or "/__pycache__/" in rel:
                continue
            name = ".".join(path.relative_to(repo).with_suffix("").parts)
            if "league.swarm.game" in imported(name, path):
                importers.add(rel)
            if tables.search(path.read_text(encoding="utf-8")):
                readers.add(rel)
        self.assertEqual(importers, self.IMPORTERS)
        self.assertEqual(readers, set(), "the game's tables are game.py's alone")
        script = (repo / "scripts" / "game_report.py").read_text(encoding="utf-8")
        self.assertIn("from league.ops.game_report import", script, "the report script goes through the report module")
        self.assertNotIn("league.swarm.game", script)


def world(root, *, extra, settings, clock):
    """A store for the non-interference test (7c) and the quarantine's readers (8): a row buried before the 2020-21 switch,
    one of a family born before T0 and buried since (it learned on the hidden years), an operator row, living control and
    legacy families with validation lines, cards and a leaderboard, a control family buried after T0; with `extra`, the
    game arm besides: a living game-arm family with its looks and CONFIRM read, its child (the game's own birth, its card
    copied and its note), a buried game-arm family whose lesson names the hidden figures, their cards and leaderboard rows,
    and the game's tables. Both stores see the same clock at every step."""
    from league.tests.test_swarm_cards import CARD

    store = SwarmStore(Path(root), clock=clock)
    switch = dt.datetime(2026, 9, 28, 16, 10, tzinfo=dt.timezone.utc).timestamp()
    clock.t = switch - 3 * DAY

    def born(fid, roots=("SPY",), mechanism=MECHANISM, line=None, card=False):
        store.add_family({"id": fid, "mechanism": mechanism, "structure": "debit_vertical", "roots": list(roots), "dte": [1, 5]},
                         origin="architect")
        store.add_version(fid, f"NEEDS = {{'roots': {list(roots)!r}}}\nTAG = '{fid}'\n", {"k": 1}, author="test")
        store.update_family(fid, best_train=1.25, trials=12, revisions=3)
        if line is not None:
            store.update_family(fid, validations=1, validated_version=1)
            store.set_state(fid, validation_line=line, validation_version=1,
                            validation_numbers={"mean": 0.01, "t": 1.1, "sharpe_daily": 0.1, "quarters": "3/4"})
        if card:
            cards.put(store, fid, CARD, "debit_vertical")
        return fid

    line = {"passed": False, "checks": {"status_ok": True, "trades": True, "days": True, "mean_positive": True, "t": False,
                                        "dsr": False, "quarters": True, "stress": True}}
    old = born("nw-pre", mechanism=MECHANISM + " Calls after the low close.")
    store.retire_gym(old, "Refuted: the calls never paid after fees", floor=0, source="test")
    learned = born("nw-learned", mechanism=MECHANISM + " ZEBRA learned on the hidden years.")
    legacy = born("nw-legacy", line=line, card=True)
    clock.t = switch + DAY
    store.retire_gym(learned, "Refuted: ZEBRA calls failed over 2020-24", floor=0, source="test")
    store._exec("INSERT INTO graveyard(family, at, mechanism, structure, roots, lesson, best) VALUES(?,?,?,?,?,?,?)",
                ("op-calls-costs", store.now(), "Operator lesson on calls and costs.", "debit_vertical", '["SPY"]',
                 "Operator pre-registered test: calls after a low close did not replicate after costs.", "{}"))
    clock.advance(DAY)
    game.t0(store, settings)
    clock.advance(60)
    taken: set[str] = set()
    ids = []
    for _ in range(3):
        ids.append(arm_id("control", "nw-c", taken=taken))
        taken.add(ids[-1])
    control = [born(ids[0], line=line, card=True), born(ids[1], roots=("QQQ",), card=True)]
    buried = born(ids[2], mechanism=MECHANISM + " Calls on a gap.")
    tsla = born("nw-tsla", roots=("TSLA",))
    clock.advance(3600)
    store.retire_gym(buried, "Refuted: the calls on a gap never paid", floor=0, source="test")
    board = [{"family": fid, "band": "gym", "share": 0.2, "structure": "debit_vertical", "roots": ["SPY"], "revisions": 3,
              "lineage_trials": 12, "best_train": 1.25, "validation": None, "gate_ready": False, "closeable": True}
             for fid in (*control, legacy, tsla)]
    if extra:
        played = arm_id("game", "nw-g", taken=taken)
        taken.add(played)
        gone = arm_id("game", "nw-g", taken=taken)
        born(played, line=line, card=True)
        born(gone, mechanism=MECHANISM + " ZEBRA calls 3.1415.", card=True)
        c = game.cfg(settings)
        for f_sel, f_conf in ((2.5, 3.1415926), (1.8, -2.7182818)):
            v = store.add_version(played, f"NEEDS = {{'roots': ['SPY']}}\nTAG = {f_sel}\n", {"k": 2}, author="test")
            with store.atomic():
                seq = game._record_look(store, store.family(played), "game", "ladder", v, c, seen_score=1.0)
            select, other = game.fold(store.family(played)["lineage"])
            figure = lambda f: {"eligible": True, "trades": 60, "days_traded": 30, "t_net": 9.0, "t_alpha": f, "F": f}  # noqa: E731
            game._result(store, seq, "ok", {str(select): figure(f_sel), str(other): figure(f_conf)}, "PASS")
            store._exec("INSERT INTO game_confirms(look_seq, at, f_confirm, confirmed) VALUES(?,?,?,?)",
                        (seq, store.now(), f_conf, 1 if f_conf >= 1.28 else 0))
        [child] = game.reproduce(store, {**settings, "game": {**settings["game"], "crossover_share": 0.0}}, clock=clock)
        store.retire_gym(gone, "spent its four private looks without a pass; ZEBRA 2021-03-01 F 3.1415", floor=0, source="test")
        board += [{**board[0], "family": fid, "share": 0.1} for fid in (played, child)]
    store.put("leaderboard", {"at": clock(), "board": board, "totals": {}})
    return store


class NonInterference(unittest.TestCase):
    """7c: the architect's request (its prompt, its graveyard digest, its card block, the ids it may cite) and the
    strategist's inputs (its system prompt, its packet with the graveyard sample, the ids it may cite) are byte-identical on
    two stores that differ only in the game arm: its families, its child, its graveyard rows, its cards, its leaderboard
    rows and the game's tables. Pure counts (the refill and the want, the ceiling, the birth quota's window) read every
    family by design (the spec's section 3.8): both stores sit on the same side of each count's threshold."""

    def reads(self, extra):
        from league.swarm.architect import Architect, GraveyardDigest
        from league.swarm.strategist import Strategist
        from league.tests.test_swarm_strategist import LOCKED, FakeRouter

        settings = round_settings(arm_fraction=0.5)
        settings["practice"] = {"feedback": False}
        settings["architect"]["agenda_locked"] = LOCKED
        with tempfile.TemporaryDirectory() as d:
            clock = Clock()
            store = world(d, extra=extra, settings=settings, clock=clock)
            try:
                digest = GraveyardDigest(store, settings, clock=clock)
                architect = Architect(store, FakeRouter(), settings, clock=clock, digest=digest)
                strategist = Strategist(store, FakeRouter(), settings, digest=digest, clock=clock, architect=architect)
                snap = digest.snapshot()
                out = {"prompt": architect.prompt(), "prompt_digest": architect.prompt(full_graveyard=True),
                       "digest": [snap.sealed, snap.tail, snap.rows], "known": sorted(architect.graveyard_ids()),
                       "system": strategist.system(), "packet": strategist.packet(sample=True),
                       "cites": sorted(strategist.known_ids()), "gaps": architect.gaps(), "classes": architect.classes()}
                families = len(store.families(alive=True))
            finally:
                store.close()
        return out, families

    def test_the_architects_and_the_strategists_inputs_do_not_move_with_the_game_arm(self):
        plain, n = self.reads(False)
        played, m = self.reads(True)
        self.assertGreater(m, n, "the second store holds more living families: the game arm's")
        for key in plain:
            self.assertEqual(played[key], plain[key], key)
        text = json.dumps(plain)
        self.assertIn("calls never paid", text, "a visible lesson is read")
        self.assertNotIn("ZEBRA", text, "no quarantined lesson: neither the hidden years' learner's nor the game arm's")
        self.assertNotIn("nw-g", text)
        self.assertIsNone(HIDDEN_TEXT.search(text))


class AgendaYears(unittest.TestCase):
    """7d: after the T0 reset (the operator clears the strategist's section) the agenda the architect reads carries no
    2020 or 2021: a section that names a hidden year is refused while the game is on (the rule "years"), its repair
    accepted; a cited id that holds one is a name, masked as every id is. With the game off the rule is off."""

    def strategist_run(self, settings, answers):
        from league.swarm.architect import AGENDA_KEY, Architect, GraveyardDigest
        from league.swarm.strategist import Strategist
        from league.tests.test_swarm_graveyard_digest import Graves
        from league.tests.test_swarm_strategist import CITES, LOCKED, FakeRouter

        with tempfile.TemporaryDirectory() as d:
            clock = Clock()
            store = SwarmStore(Path(d), clock=clock)
            try:
                graves = Graves(store)
                for fid in (*CITES, "op-t2020-calendar-flows"):
                    graves.bury(fid, reason="The mechanism is refuted on its own evidence.")
                settings["architect"]["agenda_locked"] = LOCKED
                settings["architect"]["agenda"] = "4. WHERE TO LOOK: pooled index ETFs."
                game.t0(store, settings)
                store.put(AGENDA_KEY, None)  # the T0 reset: the strategist's current section cleared
                router = FakeRouter(list(answers))
                out = Strategist(store, router, settings, digest=GraveyardDigest(store, settings, clock=clock), clock=clock).run()
                agenda = Architect(store, router, settings, clock=clock).agenda()[1]
            finally:
                store.close()
        return out, agenda

    def test_the_agenda_after_the_t0_reset_names_no_hidden_year(self):
        from league.swarm.strategist import check_section
        from league.tests.test_swarm_strategist import CITES, CLEAN, reply

        on_settings = round_settings()
        dirty = CLEAN + "\n(e) The 2021 rally favoured calls after a low close."
        out, agenda = self.strategist_run(on_settings, [reply(dirty), reply(CLEAN + "\n(e) Calls after a low close; see "
                                                                                    "op-t2020-calendar-flows.")])
        self.assertTrue(out["accepted"], out)
        self.assertNotRegex(agenda, r"(?<![\w-])20(?:20|21)(?![\w-])", "a cited id that carries the digits is a name")
        self.assertIn("> (e) Calls after a low close", agenda)
        verdict = check_section(dirty, max_chars=2000, cites=CITES, known_ids=set(CITES), min_cites=3, hidden=game.HIDDEN_YEARS)
        self.assertEqual([r.split(":")[0] for r in verdict.reasons], ["years"])
        self.assertTrue(check_section(dirty, max_chars=2000, cites=CITES, known_ids=set(CITES), min_cites=3).ok, "the rule off")
        off = round_settings(enabled=False)
        out, agenda = self.strategist_run(off, [reply(dirty)])
        self.assertTrue(out["accepted"], "with the game off a year is no reason")
        self.assertIn("2021 rally", agenda)


# ------------------------------------------------------------------------------------------------ 8. the quarantine, per reader
class QuarantineReaders(unittest.TestCase):
    """Every reader of the graveyard drops the rows of a family born before T0 and buried since the 2020-21 switch, and the
    game arm's rows, and keeps the rows buried before the switch and control's rows buried after T0: the researchers'
    tool, the architect's request (its 20 newest rows and its digest), the lessons a birth carries, the rebirth index, the
    strategist's sample and the ids either may cite. With the game off each is the store's own read."""

    def test_each_reader_drops_the_quarantined_rows_and_keeps_the_rest(self):
        from league.swarm.architect import Architect, GraveyardDigest
        from league.swarm.researcher import Researcher
        from league.swarm.strategist import Strategist
        from league.tests.test_swarm_strategist import FakeRouter

        for enabled in (True, False):
            settings = round_settings(arm_fraction=0.5, enabled=enabled)
            settings["architect"]["require_card"] = False
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as d:
                clock = Clock()
                store = world(d, extra=True, settings={**settings, "game": {**settings["game"], "enabled": True}}, clock=clock)
                try:
                    hidden_ids = {r["family"] for r in store._all("SELECT family FROM graveyard")
                                  if r["family"] == "nw-learned" or game.arm(store, store.family(r["family"]),
                                                                             {"game": {**settings["game"], "enabled": True}}) == "game"}
                    self.assertEqual(len(hidden_ids), 2, "the learner of the hidden years and the game-arm family")
                    every = {r["family"] for r in store._all("SELECT family FROM graveyard")}
                    want = every - hidden_ids if enabled else every
                    architect = Architect(store, FakeRouter(), settings, clock=clock)
                    tool = Researcher._local_tool(types.SimpleNamespace(store=store, settings=settings), {"id": "x"}, "graveyard",
                                                  {"query": ""}, {})
                    prompt = architect.prompt()
                    newest = json.loads(prompt.split("THE GRAVEYARD:\n", 1)[1].split("\n\nRESEARCH COVERAGE", 1)[0])
                    reads = {"tool": {r["family"] for r in tool["lessons"]},
                             "newest": {r["family"] for r in newest},
                             "digest": {p["id"] for p in GraveyardDigest(store, settings, clock=clock).rows()},
                             "sample": {r["family"] for r in Strategist(store, FakeRouter(), settings, clock=clock)._sample()},
                             "cite": set(architect.graveyard_ids())}
                    for name, seen in reads.items():
                        self.assertEqual(seen, want, name)
                    indexed = {r["row"] for r in cards.RebirthIndex(store, settings, exclude=architect.unseen()).rows}
                    self.assertTrue(indexed and indexed <= want, "the rebirth index reads visible rows only")
                    [born] = architect.admit([{"slug": "calls-low-close", "structure": "debit_vertical", "roots": ["SPY"],
                                               "dte": [1, 5], "mechanism": "Calls bought after a low close rebound by the next open while fees "
                                                            "stay small, a debit vertical on SPY."}])
                    lessons = " ".join(store.family(born)["spec"]["lessons"])
                    self.assertTrue(lessons, "a birth carries the visible lessons")
                    if enabled:
                        self.assertNotIn("ZEBRA", lessons + prompt)
                finally:
                    store.close()

# ------------------------------------------------------------------------------------------------ 14-15. the report and its dry run
def _ranks(xs):
    """Average ranks (1-based), computed apart from the game's own `_ranks`."""
    ordered = sorted(xs)
    first = {}
    for i, value in enumerate(ordered):
        first.setdefault(value, []).append(i + 1)
    return [sum(first[v]) / len(first[v]) for v in xs]


def _spearman(xs, ys):
    a, b = _ranks(xs), _ranks(ys)
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def _mean(xs):
    return sum(xs) / len(xs)


class Report(GameCase):
    """14: the operator's report (league/ops/game_report.py over `game.metrics`) on a store with planted outcomes reproduces
    R1-R6 (section 7 of the spec), each figure computed here apart, to 1e-9; its intervals are seeded and ordered; and the
    pre-registered decisions read off the figures."""

    settings = on(arm_fraction=0.5)

    def look(self, fid, f_sel, f_conf, *, seen, seen_f=None, role="ladder", confirm=None, errors=0):
        fam = self.store.family(fid)
        v = self.version(fid)
        c = game.cfg(self.settings)
        with self.store.atomic():
            seq = game._record_look(self.store, fam, game.arm(self.store, fam, self.settings) or "control", role, v, c,
                                    seen_score=seen, seen_f=seen_f)
        for _ in range(errors):
            game._result(self.store, seq, "error", {"why": "the box failed"})
            game._result(self.store, seq, "requeued", {})
        select, other = game.fold(fam["lineage"])

        def fig(f):
            return {"eligible": f is not None, "trades": 60, "days_traded": 30, "t_net": 10.0, "t_alpha": f, "F": f, "why": None}

        game._result(self.store, seq, "ok", {str(select): fig(f_sel), str(other): fig(f_conf)}, game.tier_of(f_sel, 1.28))
        if confirm is not None:
            self.store._exec("INSERT INTO game_confirms(look_seq, at, f_confirm, confirmed) VALUES(?,?,?,?)",
                             (seq, self.store.now(), f_conf, 1 if confirm else 0))
        return {"seq": seq, "family": fid, "version": v["n"], "sel": f_sel, "conf": f_conf, "seen": seen, "seen_f": seen_f,
                "role": role, "tier": game.tier_of(f_sel, 1.28)}

    def planted(self):
        taken = set()
        g = []
        for _ in range(3):
            g.append(arm_id("game", "rep-g", taken=taken))
            taken.add(g[-1])
        k = []
        for _ in range(2):
            k.append(arm_id("control", "rep-c", taken=taken))
            taken.add(k[-1])
        for fid in (*g, *k):
            self.family(fid)
        rows = [self.look(g[0], 2.1, 1.7, seen=1.4, seen_f=1.1, confirm=True),
                self.look(g[0], 0.4, -0.3, seen=1.9, seen_f=0.9, errors=1),
                self.look(g[1], 1.5, 0.2, seen=0.7, seen_f=1.3, confirm=False),
                self.look(g[1], -0.8, 0.6, seen=2.6),
                self.look(g[2], None, 1.2, seen=1.1, seen_f=0.4),
                self.look(g[2], 0.9, None, seen=1.6),
                self.look(k[0], 0.3, 0.5, seen=2.2, seen_f=1.6, role="validated"),
                self.look(k[0], 1.1, -0.4, seen=0.8, seen_f=0.2),
                self.look(k[1], -0.2, 0.9, seen=1.3, seen_f=0.7, role="validated", errors=2),
                self.look(k[1], 1.7, 1.4, seen=0.5)]
        # A child of g[0]'s first look (the game's own birth) and a grandchild: generations 1 and 2.
        child = self.store.add_family({**self.store.family(g[0])["spec"], "id": "g-0000aaaa"}, origin="game", parent=g[0])["id"]
        self.store._exec("INSERT INTO game_children(at, child, parent, op, directive, donor, parent_look) VALUES(?,?,?,?,?,?,?)",
                         (self.store.now(), child, g[0], "mutate", 2, None, rows[0]["seq"]))
        rows += [self.look(child, 2.4, 2.0, seen=1.0, seen_f=1.5, confirm=True), self.look(child, 1.0, 0.1, seen=1.8)]
        grand = self.store.add_family({**self.store.family(child)["spec"], "id": "g-0000bbbb"}, origin="game", parent=child)["id"]
        self.store._exec("INSERT INTO game_children(at, child, parent, op, directive, donor, parent_look) VALUES(?,?,?,?,?,?,?)",
                         (self.store.now(), grand, child, "crossover", None, json.dumps({"family": g[1], "version": 1}),
                          rows[-2]["seq"]))
        rows += [self.look(grand, 0.2, -1.0, seen=2.0, seen_f=0.3)]
        gens = {g[0]: 0, g[1]: 0, g[2]: 0, k[0]: 0, k[1]: 0, child: 1, grand: 2}
        arms = {**{f: "game" for f in (*g, child, grand)}, **{f: "control" for f in k}}
        for r in rows:
            r.update(gen=gens[r["family"]], arm=arms[r["family"]])
        # Validation: the game family's CONFIRMED version (validated, failed) and control's versions (one passed).
        verdicts = {}
        for r, t, passed in ((rows[0], 1.2, False), (rows[6], 2.9, True), (rows[8], 0.4, False)):
            self.store.add_run(r["family"], r["version"], {"run_id": f"val-{r['seq']}", "status": "ok", "trials": 1,
                                                           "summary": {"t_daily": t}}, window="validation", stress=1.0,
                               purpose="validation")
            verdicts.setdefault(r["family"], {})[str(r["version"])] = {"passed": passed}
        for fid, v in verdicts.items():
            self.store.set_state(fid, validation_verdicts=v)
        return rows, {"game": g, "control": k, "child": child, "grand": grand}

    def test_the_report_reproduces_r1_to_r6(self):
        from league.ops import game_report

        rows, who = self.planted()
        out = game_report.report(Path(self.dir.name), settings=self.settings, now=self.clock(), draws=300, seed=3)
        places = 9
        # R1: D1 over the founders' looks with both years eligible, the failure rate, the ineligible share.
        d = [r["sel"] - r["conf"] for r in rows if r["gen"] == 0 and r["sel"] is not None and r["conf"] is not None]
        mean = _mean(d)
        se = math.sqrt(sum((x - mean) ** 2 for x in d) / (len(d) - 1) / len(d))
        r1 = out["R1"]
        self.assertEqual(r1["d1_founders"]["n"], len(d))
        self.assertAlmostEqual(r1["d1_founders"]["mean"], mean, places=places)
        self.assertAlmostEqual(r1["d1_founders"]["se"], se, places=places)
        self.assertAlmostEqual(r1["d1_founders"]["z"], mean / se, places=places)
        self.assertEqual((r1["failure_rate"]["submissions"], r1["failure_rate"]["errors"]), (len(rows) + 3, 3))
        self.assertAlmostEqual(r1["failure_rate"]["rate"], 3 / (len(rows) + 3), places=places)
        self.assertEqual((r1["ineligible"]["years"], r1["ineligible"]["ineligible"]), (2 * len(rows), 2))
        self.assertTrue(r1["leak"]["passed"])
        # R2: Spearman(F on SELECT, F on CONFIRM) less Spearman(seen, F on CONFIRM), the same looks.
        both = [r for r in rows if r["sel"] is not None and r["conf"] is not None]
        hidden_rho = _spearman([r["sel"] for r in both], [r["conf"] for r in both])
        seen_rho = _spearman([r["seen"] for r in both], [r["conf"] for r in both])
        self.assertEqual(out["R2"]["n"], len(both))
        self.assertAlmostEqual(out["R2"]["rho_hidden"], hidden_rho, places=places)
        self.assertAlmostEqual(out["R2"]["rho_seen"], seen_rho, places=places)
        self.assertAlmostEqual(out["R2"]["delta_rho"], hidden_rho - seen_rho, places=places)
        # R3: the CONFIRM year of the game's SELECT passers against control's validated versions.
        passers = [r for r in rows if r["arm"] == "game" and r["role"] == "ladder" and r["tier"] == "PASS" and r["conf"] is not None]
        validated = [r for r in rows if r["arm"] == "control" and r["role"] == "validated" and r["conf"] is not None]
        self.assertEqual((out["R3"]["n_game"], out["R3"]["n_control"]), (len(passers), len(validated)))
        self.assertAlmostEqual(out["R3"]["delta_sel"], _mean([r["conf"] for r in passers]) - _mean([r["conf"] for r in validated]),
                               places=places)
        self.assertAlmostEqual(out["R3"]["gap_game"], _mean([r["seen_f"] - r["conf"] for r in passers if r["seen_f"] is not None]),
                               places=places)
        self.assertAlmostEqual(out["R3"]["gap_control"], _mean([r["seen_f"] - r["conf"] for r in validated]), places=places)
        # R4: children and grandchildren against the founders, on CONFIRM (G) and on SELECT (G_SEL), and the burn meter.
        ladder = [r for r in rows if r["arm"] == "game" and r["role"] == "ladder"]

        def gain(key):
            kids = [r[key] for r in ladder if r["gen"] >= 1 and r[key] is not None]
            roots = [r[key] for r in ladder if r["gen"] == 0 and r[key] is not None]
            return _mean(kids) - _mean(roots)

        self.assertAlmostEqual(out["R4"]["G"], gain("conf"), places=places)
        self.assertAlmostEqual(out["R4"]["G_SEL"], gain("sel"), places=places)
        self.assertAlmostEqual(out["R4"]["burn"], gain("sel") - gain("conf"), places=places)
        self.assertEqual(sorted(out["R4"]["by_generation"]), ["0", "1", "2"])
        self.assertAlmostEqual(out["R4"]["by_generation"]["2"]["conf"], -1.0, places=places)
        # R5: flow by arm, children by operator and directive, the children that beat their founder on CONFIRM.
        flow = out["R5"]["all"]
        self.assertEqual(flow["game"]["looks"], sum(1 for r in rows if r["arm"] == "game"))
        self.assertEqual(flow["control"]["select_passes"], sum(1 for r in rows if r["arm"] == "control" and r["tier"] == "PASS"))
        self.assertEqual((flow["game"]["confirm_reads"], flow["game"]["confirmed"]), (3, 2))
        self.assertEqual(flow["children"]["by_op"], {"mutate": 1, "crossover": 1})
        self.assertEqual(flow["children"]["by_directive"]["2"], 1)
        # child's first look 2.0 against its founder look's 1.7 (beats); grandchild's -1.0 against the same founder (not).
        self.assertEqual(out["R5"]["children_beat_founder"], {"n": 2, "share": 0.5})
        self.assertEqual(out["R5"]["hidden_submissions"], len(rows) + 3)
        # R6: Validation per arm (the game's tries only of CONFIRMED versions), its median t and the passes.
        self.assertEqual((out["R6"]["game"]["validation_tries"], out["R6"]["game"]["validation_passes"]), (1, 0))
        self.assertAlmostEqual(out["R6"]["game"]["median_t"], 1.2, places=places)
        self.assertEqual((out["R6"]["control"]["validation_tries"], out["R6"]["control"]["validation_passes"]), (2, 1))
        self.assertAlmostEqual(out["R6"]["control"]["median_t"], (2.9 + 0.4) / 2, places=places)
        self.assertAlmostEqual(out["R6"]["control"]["pass_rate"], 0.5, places=places)
        # The intervals: seeded (the same report twice), two-sided and ordered.
        again = game_report.report(Path(self.dir.name), settings=self.settings, now=self.clock(), draws=300, seed=3)
        self.assertEqual(again, out)
        for block in (out["R2"], out["R3"], out["R4"]):
            lo, hi = block["ci"]
            self.assertLessEqual(lo, hi)
        self.assertEqual((out["draws"], out["level"], out["operator_only"]), (300, 0.9, True))
        self.assertEqual(json.loads(json.dumps(out, allow_nan=False)), out, "finite and JSON-safe")
        self.assertEqual(game_report.report(Path(self.dir.name), settings=self.settings, now=self.clock())["draws"], 2000)

    def test_the_pre_registered_decisions(self):
        from league.ops.game_report import decide

        ok = {"R1": {"leak": {"passed": True}, "d1_founders": {"passed": True}, "failure_rate": {"passed": True}}}
        self.assertEqual(decide(ok, days=0.5)["R1"], {"passed": True, "failed": [], "action": None})
        leak = {"R1": {"leak": {"passed": False}, "d1_founders": {"passed": False}, "failure_rate": {"passed": True}}}
        self.assertEqual(decide(leak, days=1)["R1"]["failed"], ["leak", "d1_founders"])
        self.assertEqual((decide(ok, days=2)["day3"], decide(ok, days=2)["day7"]), ("pending", "pending"))
        fails = {**ok, "R2": {"delta_rho": -0.1, "ci": [-0.3, 0.04]}}
        self.assertIn("the premise fails", decide(fails, days=3.2)["day3"])
        self.assertEqual(decide({**ok, "R2": {"delta_rho": -0.1, "ci": [-0.3, 0.06]}}, days=3.2)["day3"], "continue")
        self.assertEqual(decide({**ok, "R2": {"delta_rho": 0.2, "ci": [0.1, 0.3]}}, days=3.2)["day3"], "continue")
        wide = {**ok, "R3": {"delta_sel": 0.1, "ci": [-0.2, 0.4]}, "R4": {"G": 0.35, "ci": [0.05, 0.6]}}
        self.assertTrue(decide(wide, days=7.5)["day7"].startswith("GO-WIDE"))
        back = {**ok, "R3": {"delta_sel": 0.1, "ci": [-0.2, 0.4]}, "R4": {"G": 0.05, "ci": [-0.2, 0.3]}}
        self.assertTrue(decide(back, days=7.5)["day7"].startswith("REVERT"))
        middle = {**ok, "R3": {"delta_sel": 0.25, "ci": [-0.2, 0.6]}, "R4": {"G": 0.05, "ci": [-0.2, 0.3]}}
        self.assertTrue(decide(middle, days=7.5)["day7"].startswith("EXTEND"))
        self.assertTrue(decide({**wide, "R4": {"G": 0.35, "ci": [-0.05, 0.6]}}, days=7.5)["day7"].startswith("EXTEND"),
                        "GO-WIDE needs its interval above zero")


class DryRun(GameCase):
    """15: the report script and the House's `game` job run end to end on a fixture store (the workflow lesson: a syntax
    check misses an undefined name): the script in this process and as a child process, the job read-only, its warning on
    a failed R1 (never a figure), and its silence with the game off and no look."""

    settings = on(arm_fraction=0.5)

    def setUp(self):
        super().setUp()
        self.root = Path(self.dir.name)
        (self.root / "swarm.json").write_text(json.dumps({"game": self.settings["game"]}), encoding="utf-8")
        fid = arm_id("game", "dry")
        fam = self.family(fid)
        for f in (2.0, 0.4, -0.2):
            self.plant(fam, f, f / 2)
        control = self.family(arm_id("control", "dry"))
        self.plant(control, 0.5, 0.1, role="validated")
        self.fid = fid

    def test_the_script_in_process_and_as_a_child(self):
        import importlib.util

        script = Path(ci.REPO) / "scripts" / "game_report.py"
        spec = importlib.util.spec_from_file_location("game_report_script", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        with mock.patch("sys.stdout"):
            self.assertEqual(module.main(["--swarm-root", str(self.root), "--draws", "50", "--day", "2026-10-09"]), 0)
        written = json.loads((self.root / "game" / "report-2026-10-09.json").read_text())
        self.assertEqual((written["day"], written["looks"], written["draws"]), ("2026-10-09", 4, 50))
        for key in ("R1", "R2", "R3", "R4", "R5", "R6", "decisions", "t0"):
            self.assertIn(key, written)
        out = Path(self.dir.name) / "elsewhere"
        child = subprocess.run([sys.executable, str(script), "--swarm-root", str(self.root), "--draws", "20", "--out", str(out)],
                               capture_output=True, text=True, timeout=300, cwd=str(ci.REPO))
        self.assertEqual(child.returncode, 0, child.stderr[-2000:])
        [path] = list(out.glob("report-*.json"))
        self.assertEqual(child.stdout.strip().splitlines()[-1], str(path))
        self.assertEqual(json.loads(path.read_text())["looks"], 4)

    def test_the_houses_job_writes_it_read_only_and_warns_of_a_failed_plumbing_check(self):
        from league.ops import game_report

        alerts = []
        ctx = types.SimpleNamespace(root=self.root, now=self.clock, config=None,
                                    alert=lambda level, text: alerts.append((level, text)))
        out = game_report.run(ctx)
        self.assertTrue(out["ok"])
        self.assertTrue(Path(out["path"]).is_file())
        self.assertEqual(Path(out["path"]).parent, self.root / "game")
        self.assertEqual(alerts, [])
        self.store.save_convo(self.fid, [{"role": "tool", "content": json.dumps({"by_year": {"2021": 1.0}})}])
        out = game_report.run(ctx)
        self.assertEqual(out["r1_failed"], ["leak"])
        [(level, text)] = alerts
        self.assertEqual(level, "warning")
        self.assertIn("leak", text)
        self.assertNotRegex(text, r"\d\.\d|20(20|21)")
        with tempfile.TemporaryDirectory() as d:
            SwarmStore(Path(d)).close()
            (Path(d) / "swarm.json").write_text(json.dumps({"game": {"enabled": False}}), encoding="utf-8")
            quiet = game_report.run(types.SimpleNamespace(root=Path(d), now=self.clock, config=None, alert=None))
            self.assertIn("skipped", quiet)
            self.assertFalse((Path(d) / "game").exists())

    def test_the_registry_runs_it_daily_at_midnight_read_only(self):
        from league.ops.registry import by_name

        job = by_name()["game"]
        self.assertEqual((job.module, job.in_pause, job.paid), ("league.ops.game_report", True, False))
        self.assertEqual([(t.kind, t.at.hour, t.at.minute) for t in job.triggers], [("daily", 0, 0)])


# ------------------------------------------------------------------------------------------------ T0 at the swarm's start
def _loop_case():
    from league.tests.test_swarm_loop import LoopCase

    class LoopT0(LoopCase):
        """T0 (league/swarm/loop.py): the first start with the game on, once the running Train span is the seen span,
        writes it once; the founders it seeded before are legacy. Under a span that shows the hidden years, or with the
        game off, nobody plays."""

        def start(self, game_block, train_from=None):
            self.settings["game"] = game_block
            if train_from:
                self.settings["gym"]["train_from"] = train_from
            out = io.StringIO()
            with mock.patch("sys.stdout", out):
                self.assertEqual(self.swarm().run(once=True), 0)
            return out.getvalue()

        def test_the_first_start_writes_t0_once_and_the_families_alive_then_are_legacy(self):
            said = self.start({"enabled": False, "mode": "gate"})  # the House before the deploy: its families
            self.assertIsNone(self.store.get(game.T0_KEY))
            self.store._exec("UPDATE families SET born_at='2026-10-01T00:00:00Z'")  # born days before the deploy
            said = self.start({"enabled": True, "mode": "gate"})
            t0 = self.store.get(game.T0_KEY)
            self.assertIsNotNone(t0)
            self.assertIn(f"the learning game starts: T0 {t0}", said)
            fams = self.store.families(alive=True)
            self.assertEqual(len(fams), 48)
            self.assertEqual({game.arm(self.store, f, self.settings) for f in fams}, {None}, "alive at T0: legacy")
            born = self.store.add_family({"id": "after-t0", "mechanism": MECHANISM, "structure": "debit_vertical",
                                          "roots": ["SPY"]}, origin="architect")
            self.assertIn(game.arm(self.store, born, self.settings), game.ARMS, "born after T0 on a core root: it plays")
            said = self.start({"enabled": True, "mode": "gate"})
            self.assertEqual(self.store.get(game.T0_KEY), t0, "written once")
            self.assertNotIn("the learning game starts", said)

        def test_under_a_span_that_shows_the_hidden_years_or_with_the_game_off_nobody_plays(self):
            said = self.start({"enabled": True, "mode": "gate"}, train_from="2020-01-02")
            self.assertIsNone(self.store.get(game.T0_KEY))
            self.assertIn("the learning game waits", said)
            said = self.start({"enabled": False, "mode": "gate"})
            self.assertIsNone(self.store.get(game.T0_KEY))
            self.assertNotIn("learning game", said)

    return LoopT0


LoopT0 = _loop_case()


if __name__ == "__main__":
    unittest.main()
