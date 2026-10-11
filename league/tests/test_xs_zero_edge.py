"""THE ZERO-EDGE JOB (release E4; league/ops/xs_zero_edge.py): what the panel Train bar passes at zero edge, measured
each week on the bar as built. Its programs (a hash's picks, read from ctx and never counted, so the bar's own restart
check does not fail them by construction), the week's plan, and the job: its wall asked first, the swarm's own bar
called for each program, the week's row written after each program so a chunk resumes, the alarm, and nothing of a
swarm family read or written. league.xs is faked at its interfaces (league/tests/elane_xs_fakes.py)."""

from __future__ import annotations

import datetime as dt
import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league.gym.safety import check_program
from league.ops import xs_zero_edge as Z
from league.ops.context import Context
from league.swarm import elane_train, elane_xs
from league.tests import elane_xs_fakes as F
from league.xs import config as xconfig

WEEK = "2026-W39"


def ctx_of(ids=range(1000, 1040), ret=None, k=8, seed=7):
    return SimpleNamespace(n=len(list(ids)), ids=list(ids), params={"seed": seed, "k": k},
                           mkt=SimpleNamespace(ret=ret if ret is not None else [0.001 * i for i in range(21)]))


def decide(code, ctx):
    space: dict = {}
    exec(compile(code, "<zero-edge>", "exec"), space)  # noqa: S102 - the job's own generated program
    return space["decide"](ctx)


class ThePrograms(unittest.TestCase):
    def test_every_program_passes_the_code_rules_and_names_the_panels_needs(self):
        for k in Z.KS:
            for rebalance in Z.SCHEDULES:
                code = Z.program_code(11, k, rebalance)
                check_program(code)
                needs = elane_train.needs_literal(code)
                self.assertEqual((needs["panel"], needs["max_names"], needs["rebalance"]), ("sp500", k, rebalance))
                self.assertEqual("weekday" in needs, rebalance == "weekly", "a monthly program declares no weekday")
                self.assertTrue(set(needs) <= {"panel", "history", "max_names", "rebalance", "weekday", "max_hold_sessions"})
                fam = {"spec": {"panel": "sp500", "max_names": k, "rebalance": rebalance, "weekday": 0}}
                self.assertIsNone(elane_xs.check_code(code, fam))
        for bad in ((7, 6, "weekly"), (7, 5, "daily")):
            with self.assertRaises(ValueError):
                Z.program_code(*bad)

    def test_a_target_is_k_slots_at_equal_weights_inside_the_contract(self):
        for k in Z.KS:
            answer = decide(Z.program_code(3, k, "weekly"), ctx_of(k=k))
            self.assertEqual((answer["at"], len(answer["target"])), ("open", k))
            self.assertTrue(set(answer["target"]) <= set(range(1000, 1040)))
            self.assertTrue(all(0 < w <= xconfig.MAX_WEIGHT for w in answer["target"].values()))
            self.assertLessEqual(sum(answer["target"].values()), 1.0 + 1e-9)
        self.assertEqual(decide(Z.program_code(3, 8, "weekly"), ctx_of(ids=range(5), k=8)), {"hold": True},
                         "fewer slots than names: it holds")

    def test_the_picks_are_a_hash_of_the_seed_the_slot_and_the_decisions_key(self):
        code = Z.program_code(3, 8, "weekly")
        first = decide(code, ctx_of())
        self.assertEqual(decide(code, ctx_of()), first, "a fresh load decides the same on the same ctx")
        self.assertNotEqual(set(decide(code, ctx_of(seed=4))["target"]), set(first["target"]), "another seed")
        other_day = [0.002 * i for i in range(21)]
        self.assertNotEqual(set(decide(code, ctx_of(ret=other_day))["target"]), set(first["target"]),
                            "another decision, other picks")
        nan = [float("nan")] * 11 + [0.001 * i for i in range(11, 21)]
        self.assertEqual(decide(code, ctx_of(ret=nan)), first, "the key reads the last ten returns")
        relabelled = decide(code, ctx_of(ids=range(5000, 5040)))
        self.assertFalse(set(relabelled["target"]) & set(first["target"]))
        picks = [frozenset(decide(code, ctx_of(ret=[0.0001 * (i + d) for i in range(21)]))["target"]) for d in range(40)]
        counts: dict = {}
        for chosen in picks:
            for slot in chosen:
                counts[slot] = counts.get(slot, 0) + 1
        self.assertGreater(len(counts), 30, "over forty decisions nearly every slot is picked: no slot is favoured")
        self.assertLess(max(counts.values()), 20)

    def test_it_keeps_nothing_between_calls_and_reads_ids_the_count_the_market_and_its_params_alone(self):
        code = Z.program_code(3, 8, "monthly")
        self.assertNotIn("STATE", code)
        self.assertNotIn("global", code)
        self.assertEqual(sorted(set(re.findall(r"ctx\.(\w+)", code))), ["ids", "mkt", "n", "params"])
        self.assertEqual(sorted(set(re.findall(r"^import (\w+)", code, re.M))), ["math"])

    def test_the_bars_own_restart_check_holds_for_it(self):
        world = F.switch_on(self)
        code = Z.program_code(3, 8, "weekly")
        run = world.runner.train(code, {}, name="z", start=dt.date(2019, 1, 1), end=dt.date(2019, 12, 31), k=1.5,
                                 calls=True)
        out = elane_xs.state_check(world.runner.decider, code, {}, name="z", runs=[run])
        self.assertEqual((out["matched"], out["calls"], out["held"], out["failed"]), (F.STATE_CALLS, F.STATE_CALLS, True, 0),
                         "a call counter in STATE would have failed every time, and the job would measure nothing")


class ThePlan(unittest.TestCase):
    def test_the_week_is_the_iso_week_in_utc(self):
        def epoch(*day):
            return dt.datetime(*day, tzinfo=dt.timezone.utc).timestamp()

        self.assertEqual(Z.week_of(epoch(2026, 10, 11, 6, 0)), "2026-W41", "a Sunday closes its week")
        self.assertEqual(Z.week_of(epoch(2026, 10, 12, 0, 0)), "2026-W42")
        self.assertEqual(Z.week_of(epoch(2027, 1, 3, 12, 0)), "2026-W53", "the year is the ISO week's")
        self.assertEqual(Z.week_of(epoch(2027, 1, 4, 0, 0)), "2027-W01")

    def test_a_weeks_programs_are_fixed_and_cover_every_cell_in_turn(self):
        plan = [Z.plan(WEEK, i) for i in range(12)]
        self.assertEqual(plan, [Z.plan(WEEK, i) for i in range(12)])
        self.assertEqual([(p["k"], p["rebalance"]) for p in plan[:6]],
                         [(5, "weekly"), (8, "weekly"), (12, "weekly"), (5, "monthly"), (8, "monthly"), (12, "monthly")])
        self.assertEqual([(p["k"], p["rebalance"]) for p in plan[6:]], [(p["k"], p["rebalance"]) for p in plan[:6]])
        self.assertEqual(len({p["seed"] for p in plan}), 12)
        self.assertNotEqual([p["seed"] for p in plan], [Z.plan("2026-W40", i)["seed"] for i in range(12)])
        self.assertTrue(all(0 <= p["seed"] < 2 ** 31 for p in plan))

    def test_the_hidden_year_is_drawn_as_a_familys_is(self):
        cell = [Z.plan(WEEK, i)["hidden_year"] for i in range(0, 60, 6)]  # the cell (5, weekly), ten programs
        start = xconfig.TRAIN_YEARS.index(cell[0])
        self.assertEqual(cell, [xconfig.TRAIN_YEARS[(start + i) % 6] for i in range(10)],
                         "the panel's six Train years, in turn within a cell")
        self.assertFalse({Z.plan(WEEK, i)["hidden_year"] for i in range(100)} & {2016, 2020, 2021, None})
        self.assertIsNone(Z.plan(WEEK, 0, hidden=False)["hidden_year"], "no folds recording: no hidden year, as a family's")


class JobCase(unittest.TestCase):
    def setUp(self):
        self.world = F.switch_on(self)
        self.store = F.new_store(self)
        self.root = Path(self.store.root)
        F.ready(self.root)
        self.switch("train")
        self.built = mock.patch.object(Z, "build_runner", return_value=(self.world.runner, self.world.runner.decider))
        self.built.start()
        self.addCleanup(self.built.stop)

    def switch(self, mode, lane="gate", **panel):
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"mode": lane, "panel": {
            "mode": mode, "zero_edge_programs": 20, **panel}}}))
        with elane_xs._cache_lock:
            elane_xs._mode_cache.clear()

    def run_job(self):
        self.ctx = Context("xs_zero_edge", root=self.root, due_at=self.store.clock(), clock=self.store.clock, config={})
        return Z.run(self.ctx)

    def week(self):
        return Z.week_of(self.store.clock())

    def row(self):
        return (self.store.get(Z.KV) or {}).get(self.week())


class TheJob(JobCase):
    def test_its_first_statement_asks_the_quiet_rule_with_its_own_wall(self):
        self.world.quiet = "could still be working at the 15:50 ET wall"
        with mock.patch.object(elane_xs, "mode", side_effect=AssertionError("read after the wall")):
            out = self.run_job()
        self.assertEqual(out, {"status": "skipped", "why": "could still be working at the 15:50 ET wall"})
        self.assertEqual(self.world.quiet_asked, [(self.store.clock(), 3000.0)])
        self.assertEqual(Z.WALL_S, 3000)
        self.assertIsNone(self.store.get(Z.KV))
        self.built.stop()
        self.addCleanup(self.built.start)
        with mock.patch.object(Z, "build_runner", side_effect=AssertionError("built behind a wall")):
            self.assertEqual(self.run_job()["status"], "skipped")

    def test_a_quiet_rule_that_is_not_built_starts_nothing(self):
        def stub(now, need):
            raise NotImplementedError("league.xs.config is a Step 0 stub")

        with mock.patch.object(xconfig, "quiet", stub):
            out = self.run_job()
        self.assertEqual(out["status"], "skipped")
        self.assertEqual(self.world.runner.calls, [])

    def test_with_the_panel_lane_off_it_does_nothing(self):
        for mode, lane in (("off", "gate"), ("train", "off")):
            self.switch(mode, lane)
            out = self.run_job()
            self.assertEqual((out["status"], out["why"]), ("skipped", "the panel lane is off (elane.panel.mode)"))
        self.assertEqual(self.world.runner.calls, [])
        self.assertIsNone(self.store.get(Z.KV))

    def test_each_program_runs_the_whole_bar_and_a_program_with_no_edge_fails_it(self):
        with mock.patch.object(Z, "PROGRAMS_RUN", 3):
            out = self.run_job()
        self.assertEqual((out["status"], out["ran"], out["programs"], out["passes"], out["rate"], out["complete"]),
                         ("ok", 3, 3, 0, 0.0, False))
        self.assertEqual(self.row()["programs"], 3)
        self.assertTrue(set(self.row()["by_rule"]) <= {*elane_xs.JUDGED_XS, "XA0", "STATE", Z.PASS})
        self.assertGreaterEqual(self.row()["by_rule"]["XT1"], 2, "a hash's picks earn no residual")
        calls = self.world.runner.calls
        self.assertEqual(len(calls), 3 * 8, "four runs a seen span: both segments whole while no fold is recording")
        self.assertEqual({(c["k"], c["half"], c["placebos"], c["calls"], c["style"]) for c in calls},
                         {(1.0, None, 0, False, True), (1.5, None, 200, True, False), (1.5, 0, 0, False, False),
                          (1.5, 1, 0, False, False)})
        self.assertEqual({c["name"] for c in calls}, {f"xs-zero-{self.week()}-{i}" for i in range(3)})
        self.assertEqual(self.world.quiet_asked[0][1], 3000.0)
        self.assertEqual({need for _, need in self.world.quiet_asked[1:]}, {600.0},
                         "before each run, as a panel Train run of the swarm asks")
        self.assertEqual(len(self.world.quiet_asked), 1 + 24)

    def test_a_pass_is_counted_and_the_bars_restart_check_is_part_of_it(self):
        original = F.FakeRunner._result

        def edged(runner, code, params, **kw):
            return original(runner, code, {"edge": 0.0015, "sd": 0.004}, **kw)

        with mock.patch.object(Z, "PROGRAMS_RUN", 2), mock.patch.object(F.FakeRunner, "_result", edged):
            out = self.run_job()
        self.assertEqual((out["passes"], out["by_rule"]), (2, {Z.PASS: 2}))
        self.assertTrue(any(":b" in key for key in self.world.runner.decider.loads), "instance B was loaded fresh")
        self.assertEqual(elane_xs.zero_edge_rate(self.store), {"programs": 2, "passes": 2, "rate": 1.0})

    def test_a_chunk_resumes_where_the_weeks_earlier_chunks_stopped_and_stops_at_the_weeks_programs(self):
        seen = []

        def judge(run_through, decider, code, *, name, **kw):
            seen.append((name, kw["hidden"], kw["placebos"]))
            return {"passed": False, "fails": ["XT1", "XP1"]}

        with mock.patch.object(Z, "judge", judge), mock.patch.object(Z, "PROGRAMS_RUN", 8):
            first, second, third, fourth = (self.run_job() for _ in range(4))
        self.assertEqual([o.get("ran") for o in (first, second, third)], [8, 8, 4])
        self.assertEqual((third["programs"], third["complete"]), (20, True))
        self.assertEqual((fourth["status"], fourth["why"]), ("skipped", "this week's zero-edge programs are run"))
        self.assertEqual([name for name, _, _ in seen], [f"xs-zero-{self.week()}-{i}" for i in range(20)],
                         "each program of the week once, in order")
        self.assertEqual({hidden for _, hidden, _ in seen}, {None})
        self.assertEqual(self.row(), {"programs": 20, "passes": 0, "by_rule": {"XT1": 20, "XP1": 20}})

    def test_the_weeks_row_is_written_after_each_program(self):
        done = []

        def judge(run_through, decider, code, *, name, **kw):
            done.append((self.row() or {}).get("programs", 0))
            return {"passed": False, "fails": ["XT1"]}

        with mock.patch.object(Z, "judge", judge), mock.patch.object(Z, "PROGRAMS_RUN", 4):
            self.run_job()
        self.assertEqual(done, [0, 1, 2, 3], "a chunk cut off keeps every program it finished")

    def test_a_wall_met_between_two_runs_stops_the_chunk_with_what_it_has(self):
        asked = []

        def quiet(now, need):
            asked.append(need)
            return "a wall is near" if len(asked) == 1 + 8 + 4 else None  # the job's own, a program, half another

        with mock.patch.object(xconfig, "quiet", quiet), mock.patch.object(Z, "PROGRAMS_RUN", 5):
            out = self.run_job()
        self.assertEqual((out["status"], out["ran"], out["stopped"]), ("ok", 1, "a wall is near"))
        self.assertEqual(self.row()["programs"], 1, "the program cut off is not counted, and is run whole next time")

    def test_a_chunk_starts_no_program_it_could_not_finish_inside_its_own_wall(self):
        self.assertLess(Z.CHUNK_S, Z.WALL_S, "the chunk stops itself before the runner's wall would end it")
        ticks = iter(range(0, 10 ** 6, 300))  # every reading of the job's clock is five minutes after the last
        slow = SimpleNamespace(monotonic=lambda: float(next(ticks)))
        judge = mock.Mock(return_value={"passed": False, "fails": ["XT1"]})
        with mock.patch.object(Z, "time", slow), mock.patch.object(Z, "judge", judge), \
                mock.patch.object(Z, "PROGRAMS_RUN", 8):
            out = self.run_job()
        # started 0; program 1 300-600 (no check before the first); program 2 asked at 900, 1200-1500; program 3 asked
        # at 1800, 2100-2400; program 4 asked at 2700: 2700 worked + the slowest program's 300 is past the budget
        self.assertEqual((out["status"], out["ran"], judge.call_count), ("ok", 3, 3))
        self.assertIn("the chunk's own wall is near", out["stopped"])
        self.assertEqual(self.row()["programs"], 3)
        self.assertEqual(elane_xs.cpu_spent(self.store, self.store.clock()), 900.0, "each program's time is booked")
        with mock.patch.object(Z, "judge", judge), mock.patch.object(Z, "PROGRAMS_RUN", 8):
            out = self.run_job()
        self.assertEqual((out["ran"], out["programs"], out.get("stopped")), (8, 11, None), "the next trigger resumes it")

    def test_one_slow_program_always_runs(self):
        ticks = iter(range(0, 10 ** 6, 5000))
        slow = SimpleNamespace(monotonic=lambda: float(next(ticks)))
        judge = mock.Mock(return_value={"passed": False, "fails": ["XT1"]})
        with mock.patch.object(Z, "time", slow), mock.patch.object(Z, "judge", judge), \
                mock.patch.object(Z, "PROGRAMS_RUN", 8):
            out = self.run_job()
        self.assertEqual((out["ran"], self.row()["programs"]), (1, 1), "a chunk is never stopped before its first")

    def test_a_failure_of_the_houses_counts_no_program(self):
        class RunFailed(RuntimeError):
            pass

        self.world.runner.fail["train"] = RunFailed("the child died")
        out = self.run_job()
        self.assertEqual((out["status"], out["programs"]), ("failed", 0))
        self.assertIn("RunFailed", out["error"])
        self.assertIsNone(self.row())
        answers = iter([{"passed": False, "fails": ["XT1"]}, RunFailed("later")])

        def judge(*a, **kw):
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with mock.patch.object(Z, "judge", judge):
            out = self.run_job()
        self.assertEqual((out["status"], out["ran"], out["programs"]), ("ok", 1, 1))
        self.assertIn("RunFailed", out["stopped"])

    def test_the_alarm_is_raised_once_the_week_is_whole_and_the_rate_is_above_five_percent(self):
        def judge_with(passing):
            count = iter(range(1000))

            def judge(*a, **kw):
                return {"passed": True, "fails": []} if next(count) in passing else {"passed": False, "fails": ["XT1"]}
            return judge

        with mock.patch.object(Z, "judge", judge_with({0, 1})), mock.patch.object(Z, "PROGRAMS_RUN", 10):
            first = self.run_job()
            self.assertEqual((first["rate"], self.ctx.alerts), (0.2, []), "not before the week's programs are all run")
            second = self.run_job()
        self.assertEqual((second["programs"], second["passes"], second["rate"], second["complete"]), (20, 2, 0.1, True))
        self.assertEqual(len(self.ctx.alerts), 1)
        self.assertEqual(self.ctx.alerts[0]["level"], "warning")
        self.assertIn("2 of 20 random-score programs", self.ctx.alerts[0]["text"])
        self.assertIn("too loose", self.ctx.alerts[0]["text"])
        self.store.clock.advance(7 * 86400)
        with mock.patch.object(Z, "judge", judge_with({0})), mock.patch.object(Z, "PROGRAMS_RUN", 20):
            out = self.run_job()
        self.assertEqual((out["rate"], self.ctx.alerts), (0.05, []), "five percent is not above five percent")
        self.assertEqual(sorted(self.store.get(Z.KV)), sorted({Z.week_of(self.store.clock() - 7 * 86400), self.week()}))

    def test_the_kv_keeps_half_a_year_of_weeks_and_a_malformed_row_starts_again(self):
        self.store.put(Z.KV, {**{f"2025-W{i:02d}": {"programs": 100, "passes": 1, "by_rule": {}} for i in range(1, 31)},
                              self.week(): {"programs": 3, "passes": 9}})
        with mock.patch.object(Z, "judge", lambda *a, **kw: {"passed": False, "fails": ["XT1"]}), \
                mock.patch.object(Z, "PROGRAMS_RUN", 1):
            out = self.run_job()
        self.assertEqual(out["programs"], 1, "a row with more passes than programs is no count")
        kept = self.store.get(Z.KV)
        self.assertEqual(len(kept), Z.WEEKS_KEPT)
        self.assertIn(self.week(), kept)
        self.assertNotIn("2025-W01", kept)

    def test_the_job_reads_and_writes_nothing_of_a_swarm_family(self):
        fam = F.panel_family(self.store, "rev-a", code=F.good(), record={"status": "researching", "versions": {}})
        before = json.dumps(self.store.family("rev-a"), sort_keys=True, default=str)
        with mock.patch.object(Z, "PROGRAMS_RUN", 2):
            self.run_job()
        self.assertEqual(json.dumps(self.store.family("rev-a"), sort_keys=True, default=str), before)
        self.assertEqual(self.store.events_after(0), [], "no event")
        self.assertEqual(self.store._all("SELECT 1 FROM runs"), [], "no stored run")
        self.assertNotIn(fam["id"], json.dumps([c["name"] for c in self.world.runner.calls]))
        self.assertGreater(elane_xs.cpu_spent(self.store, self.store.clock()), 0.0, "its seconds count in the day's panel CPU")

    def test_its_runner_is_its_own_niced_decider(self):
        self.built.stop()
        self.addCleanup(self.built.start)
        made = {}

        class Decider:
            hash_seed = None

            def __init__(self, *, log):
                made["log"] = Path(log)

        class Isolated:
            def __init__(self, decider, root, *, budget_seconds, nice):
                made.update(decider=decider, root=Path(root), budget=budget_seconds, nice=nice)

        from league.live import decider as live_decider
        from league.swarm import elane
        from league.xs import runner as xrunner

        with mock.patch.object(live_decider, "Decider", Decider), mock.patch.object(xrunner, "Isolated", Isolated):
            run_through, decider = Z.build_runner(self.root, F.settings("train", run_budget_seconds=300))
        self.assertEqual((made["log"].name, made["root"], made["budget"], made["nice"]),
                         ("xs-zero-decider.log", self.root / "equity-daily", 300.0, 19))
        self.assertNotEqual(made["log"].name, elane_xs.DECIDER_LOG, "never the swarm's own child")
        self.assertEqual(decider.hash_seed, elane.EVIDENCE_HASH_SEED)


if __name__ == "__main__":
    unittest.main()
