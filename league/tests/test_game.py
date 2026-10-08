"""THE LEARNING GAME v1 (league/swarm/game.py): folds and arms, the fitness, the look ladder and its retries, the CONFIRM
discipline (the sealed accessor, the read budgets, decisions blind to the CONFIRM year), reproduction and its caps,
the game's retirement rules, the graveyard quarantine and what agents see, the operator's metrics, and the CI wall.
Synthetic stores and invented results only; the pool is a fake that records what it is asked to run."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
import random
import re
import tempfile
import types
import unittest
from pathlib import Path

from league import ci
from league.gym.results import _t_of
from league.swarm import canary, cards
from league.swarm import game
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock

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
        the same) give the same parents, children and retirements."""
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
        return {"parents": found, "reasons": reasons, "born": kids}


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


if __name__ == "__main__":
    unittest.main()
