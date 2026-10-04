"""THE FORWARD LADDER'S BENCHMARK (`league/swarm/forward_benchmarks.py`): its worlds are the plan's, its rows are the
practice ledger's shape, the drift control does what it claims on them, the sealed look's bootstrap port agrees with the
original, its ladder arm is the House's rule (the checkpoints, the latch, the answer session, the pre-filter's line) and
reproduces the development harness's desks, its seed id feeds the generator's streams and nothing else, and it counts
the first 32 entrants of each desk and names no verdict (the judge's: `test_ladder_judge.py`). Small desks, and two of
the protocol's on the development seed id (the full run is an operator's)."""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import functools
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import numpy  # noqa: F401

    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

from league.live import ladder as L
from league.live import observe as O
from league.swarm import forward_benchmarks as FB
from league.tests.test_live_ladder import CODE, EVALUATOR, MemoryBridge, StoreCase

OUTCOMES = ("promoted", "validation_failed", "prefilter_negative", "window", "running")
ROW = {"id", "world", "kind", "ladder", "ladder_outcome", "start", "at", "sealed", "sealed_bare", "validation_passed",
       "drift_hold", "holdout_p", "holdout_ok", "last"}

# THE GOLDEN DESKS: the development harness's own rows (the rule's design run, outside this repository) of replication 0
# of the mixed desk and of a single-world desk on the development seed id: each entrant in admission order, its (ladder
# outcome, the checkpoint that decided it, the session index of its admission).
P, V, W, R = "promoted", "validation_failed", "window", "running"
GOLDEN = {
    FB.MIXED: [
        (W, None, 0), (W, None, 0), (P, 60, 0), (W, None, 0), (W, None, 0), (W, None, 0), (W, None, 0), (W, None, 0),
        (W, None, 0), (W, None, 0), (W, None, 0), (W, None, 0), (W, None, 0), (W, None, 0), (W, None, 0), (W, None, 0),
        (W, None, 60), (W, None, 60), (W, None, 60), (W, None, 60), (W, None, 60), (W, None, 60), (P, 40, 60),
        (W, None, 60), (W, None, 60), (W, None, 60), (W, None, 60), (W, None, 60), (W, None, 60), (W, None, 60),
        (V, 40, 60), (V, 40, 61), (W, None, 100), (R, None, 101), (R, None, 101), (R, None, 120), (R, None, 120),
        (R, None, 120), (R, None, 120), (R, None, 120), (R, None, 120), (R, None, 120), (R, None, 120), (R, None, 120),
        (R, None, 120), (R, None, 120), (R, None, 120), (R, None, 120)],
    "planted_premium": [
        (P, 60, 0), (P, 40, 0), (P, 40, 0), (P, 60, 0), (V, 60, 0), (W, None, 0), (P, 40, 0), (W, None, 0), (P, 40, 0),
        (V, 60, 0), (P, 60, 0), (P, 60, 0), (W, None, 0), (W, None, 0), (W, None, 0), (W, None, 0), (P, 60, 41),
        (W, None, 41), (W, None, 41), (W, None, 41), (V, 60, 60), (P, 60, 60), (P, 60, 60), (P, 60, 60), (P, 60, 60),
        (P, 40, 60), (P, 60, 60), (P, 40, 60), (P, 60, 61), (P, 60, 61), (P, 60, 61), (W, None, 61), (R, None, 101),
        (R, None, 101), (P, 40, 101), (P, 40, 101), (R, None, 101), (R, None, 102), (R, None, 120), (R, None, 121),
        (R, None, 121), (R, None, 121), (R, None, 121), (R, None, 121), (R, None, 121), (R, None, 122), (R, None, 122),
        (R, None, 122), (R, None, 142), (R, None, 142)],
}


@functools.lru_cache(maxsize=None)
def protocol_part() -> dict:
    """The golden desks as the module plays them: one part of the protocol's own desks (16 slots, 160 sessions),
    replication 0 of each, on the development seed id (the default). Played once for the whole module."""
    return FB.run(list(GOLDEN), 1)


@functools.lru_cache(maxsize=None)
def small_desk(world: str, replication: int, slots: int, sessions: int) -> dict:
    """A desk on the development seed id, played once for the tests that read it."""
    return FB.desk(world, replication, slots=slots, sessions=sessions)


def judge_module():
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts" / "ladder_judge.py"
    spec = importlib.util.spec_from_file_location("ladder_judge_for_the_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stub(kind, ladder, sealed, bare=None, n=FB.COUNTED, world="absent", outcome="window", first=0):
    """`n` entrants of one kind from id `first`: the first `ladder`, `sealed` and `bare` of them promoted by each
    design."""
    return [{"id": first + i, "world": world, "kind": kind, "ladder": i < ladder, "sealed": i < sealed,
             "sealed_bare": i < (sealed if bare is None else bare), "ladder_outcome": "promoted" if i < ladder else outcome,
             "validation_passed": False, "drift_hold": False, "last": None} for i in range(n)]


def desk_of(world, mine, replication=0):
    return {"world": world, "replication": replication, "rows": mine}


class TheDefinition(unittest.TestCase):
    def test_the_plans_worlds_are_there_with_their_kinds(self):
        kinds = {name: spec["kind"] for name, spec in FB.WORLDS.items()}
        for name in ("absent", "cost_erased", "drift_only", "fading"):
            self.assertEqual(kinds[name], "negative", name)
        for name in ("planted_dense", "planted_sparse"):
            self.assertEqual(kinds[name], "positive", name)
        self.assertEqual(FB.WORLDS["cost_erased"]["edge_forward"] < 0 < FB.WORLDS["cost_erased"]["edge"], True)
        self.assertEqual(FB.WORLDS["fading"]["edge_forward"] < 0 < FB.WORLDS["fading"]["edge"], True)
        self.assertGreater(FB.WORLDS["drift_only"]["delta"], 0)
        self.assertEqual(FB.suite_sha(), FB.suite_sha())
        self.assertFalse(hasattr(FB, "VARIANTS"), "the variants are no part of the suite")

    def test_the_judge_judges_the_same_worlds_and_the_same_count(self):
        judge = judge_module()
        self.assertEqual(FB.COUNTED, judge.COUNTED)
        self.assertEqual(FB.COUNTED, 2 * FB.PROTOCOL["slots"], "two whole generations of the protocol's slots")
        self.assertEqual(FB.MIXED, judge.MIXED)
        for kind, names in (("negative", judge.NEGATIVE), ("positive", judge.POSITIVE)):
            self.assertEqual(sorted(names), sorted(w for w, spec in FB.WORLDS.items() if spec["kind"] == kind), kind)

    def test_the_count_is_the_first_32_entrants_whatever_their_outcome_and_the_module_names_no_verdict(self):
        """THE COUNT (rewritten for the ladder's frozen rule: the module's own binding rule is gone, the verdict is the
        judge's; `test_ladder_judge.py` holds every item of that rule, met and missed)."""
        # 32 counted negatives, 3 of them promoted by the ladder, 5 by the sealed look (4 without its holds); then a
        # third generation that is never counted, whatever became of it: two more promotions and entrants still running.
        late = stub("negative", 2, 1, n=4, first=FB.COUNTED) + stub("negative", 0, 0, n=3, first=FB.COUNTED + 4,
                                                                    outcome="running")
        out = FB.aggregate([desk_of("absent", stub("negative", 3, 5, 4) + late)])
        block = out["worlds"]["absent"]["false_promotions"]
        self.assertEqual({d: (block[d]["count"], block[d]["of"]) for d in FB.DESIGNS},
                         {"ladder": (3, 32), "sealed": (5, 32), "sealed_bare": (4, 32)})
        self.assertEqual((out["counted"], out["worlds"]["absent"]["desks"], out["worlds"]["absent"]["entrants"]),
                         (32, 1, 32))
        # An entrant is counted whatever its outcome (a failed one and one at its window alike), by its id alone, in any
        # order of the rows.
        mine = stub("negative", 1, 0, n=16, outcome="validation_failed") + \
            stub("negative", 0, 0, n=16, first=16, outcome="prefilter_negative")
        shuffled = list(reversed(mine))
        self.assertEqual(FB.aggregate([desk_of("fading", shuffled)])["pooled_negatives"]["ladder"]["of"], 32)
        self.assertEqual([r["id"] for r in FB.counted(desk_of("fading", shuffled))], list(range(32)))
        # A missed signal is a counted positive that was not promoted.
        missed = FB.aggregate([desk_of("planted_dense", stub("positive", 7, 9, 8))])["worlds"]["planted_dense"]
        self.assertEqual({d: missed["missed_signals"][d]["count"] for d in FB.DESIGNS},
                         {"ladder": 25, "sealed": 23, "sealed_bare": 24})
        self.assertNotIn("false_promotions", missed)
        # The pools: the single-world desks' negatives; the mixed desks' negatives and positives apart.
        mixed = stub("negative", 1, 2, 3, n=20) + stub("positive", 4, 6, 5, n=12, first=20, world="planted_dense")
        out = FB.aggregate([desk_of("absent", stub("negative", 3, 5, 4)), desk_of("absent", stub("negative", 0, 1), 1),
                            desk_of("fading", stub("negative", 2, 0)), desk_of(FB.MIXED, mixed)])
        self.assertEqual({d: (r["count"], r["of"]) for d, r in out["pooled_negatives"].items()},
                         {"ladder": (5, 96), "sealed": (6, 96), "sealed_bare": (5, 96)})
        self.assertEqual({d: (r["count"], r["of"]) for d, r in out["mixed_negatives"].items()},
                         {"ladder": (1, 20), "sealed": (2, 20), "sealed_bare": (3, 20)})
        self.assertEqual({d: (r["count"], r["of"]) for d, r in out["mixed_positives"].items()},
                         {"ladder": (8, 12), "sealed": (6, 12), "sealed_bare": (7, 12)})
        self.assertEqual(out["worlds"]["absent"]["desks"], 2)
        # No verdict: the ladder exceeds the sealed look in `fading` here, and the module says only whose word it is.
        self.assertEqual(out["verdict"], FB.VERDICT)
        self.assertIn("scripts/ladder_judge.py", FB.VERDICT)
        for gone in ("binding", "conditions", "worlds_where_ladder_exceeds_sealed"):
            self.assertNotIn(gone, out)
        self.assertEqual(set(out), {"counted", "verdict", "worlds", "pooled_negatives", "mixed_negatives",
                                    "mixed_positives"})

    def test_a_desk_the_count_cannot_take_is_refused(self):
        running = stub("negative", 0, 0)
        running[31]["ladder_outcome"] = "running"
        with self.assertRaisesRegex(ValueError, r"absent replication 4: counted entrants \[31\] are still running"):
            FB.aggregate([desk_of("absent", running, 4)])
        with self.assertRaisesRegex(ValueError, "has not its first 32 entrants"):
            FB.aggregate([desk_of("absent", stub("negative", 0, 0, n=31))])
        with self.assertRaisesRegex(ValueError, "has not its first 32 entrants"):
            FB.aggregate([desk_of("absent", stub("negative", 0, 0) + stub("negative", 0, 0, n=1, first=5))])
        with self.assertRaisesRegex(ValueError, "has not its first 32 entrants"):
            FB.aggregate([desk_of("absent", stub("negative", 0, 0, first=1))])
        # The judge refuses the same desks, on the same count.
        judge = judge_module()
        with self.assertRaisesRegex(SystemExit, "still running"):
            judge.counted(running, "absent", 4)
        with self.assertRaisesRegex(SystemExit, "has not its first 32 entrants"):
            judge.counted(stub("negative", 0, 0, n=31), "absent", 0)
        self.assertEqual([r["id"] for r in judge.counted(stub("negative", 0, 0, n=40), "absent", 0)], list(range(32)))

    def test_rates_carry_exact_bounds(self):
        r = FB.rate(0, 1000)
        self.assertEqual((r["count"], r["rate"], r["lower_95"]), (0, 0.0, 0.0))
        self.assertAlmostEqual(r["upper_95"], 0.00368, places=4)
        r = FB.rate(5, 100)
        self.assertLess(r["lower_95"], 0.05)
        self.assertGreater(r["upper_95"], 0.05)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheSeedId(unittest.TestCase):
    """THE SEED ID: a parameter, the development desks' by default; it feeds every stream of the generator and nothing
    else. No desk is played here on any seed id but the development one."""

    def test_the_default_is_the_development_id_and_its_streams_are_the_old_constants(self):
        self.assertEqual(FB.SEED_ID, "forward-suite-1", "the worlds' streams are suite 1's")
        for parts in (("market", "mixed:drift0.08", 3, "forward"), ("trades", "absent", 0, 7, "holdout"),
                      ("mix", "mixed", 5)):
            text = "|".join(str(p) for p in ("forward-suite-1",) + parts)
            old = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)   # what the module constant fed
            self.assertEqual(FB._seed(*parts), old)
            self.assertEqual(FB._seed(*parts, seed_id="forward-suite-1"), old)
        days = FB.nyse_sessions("2026-10-05", 30)
        path = FB.market(days, drift=0.08, replication=0, period="forward", world="absent")
        self.assertEqual(path, FB.market(days, drift=0.08, replication=0, period="forward", world="absent",
                                         seed_id="forward-suite-1"))
        self.assertEqual(FB.trades("absent", 0, 0, "forward", days, path),
                         FB.trades("absent", 0, 0, "forward", days, path, seed_id="forward-suite-1"))
        default = FB.desk(FB.MIXED, 0, slots=3, sessions=45)
        named = FB.desk(FB.MIXED, 0, slots=3, sessions=45, seed_id="forward-suite-1")
        self.assertEqual(json.dumps(default, sort_keys=True), json.dumps(named, sort_keys=True))
        self.assertEqual(json.dumps(FB.demotions("absent", programs=3, horizon=25), sort_keys=True),
                         json.dumps(FB.demotions("absent", programs=3, horizon=25, seed_id="forward-suite-1"),
                                    sort_keys=True))

    def test_another_seed_id_is_another_seed_of_every_stream(self):
        """Two seed ids give two disjoint sets of desks: every generator stream's seed differs between them (shown on
        the seeds alone: no market, no close and no desk is drawn on another id), and a desk hands its own seed id to
        every stream it draws (the next test)."""
        seeds = set()
        for seed_id in ("forward-suite-1", "forward-suite-1 ", "another id", "x"):
            for parts in (("market", "mixed:drift0.08", 0, "forward"), ("trades", "absent", 0, 0, "forward"),
                          ("mix", "mixed", 0)):
                seeds.add(FB._seed(*parts, seed_id=seed_id))
        self.assertEqual(len(seeds), 12, "one seed a stream and a seed id")
        for bad in ("", None, 7):
            with self.assertRaises(ValueError):
                FB._seed("market", "absent", 0, "forward", seed_id=bad)

    def test_a_desk_hands_its_seed_id_to_every_stream_of_the_generator_and_to_nothing_else(self):
        """No stream is left to a default, nor pinned to the module's constant: with every default seed id and the
        constant itself made one the generator refuses (nothing can be drawn on it), a run given the development seed
        id plays the very desks the defaults play. And the designs' resamples never carry it."""
        development = FB.SEED_ID
        want = FB.run([FB.MIXED], 1, slots=2, sessions=45)["desks"]
        want_demotions = FB.run_demotions(["absent"], programs=2, horizon=25)["demotion"]
        threaded = (FB._seed, FB._rng, FB.market, FB.trades, FB._entrant, FB.desk, FB.demotions, FB.run, FB.run_demotions)
        real_seed, real_judge, real_prefilter = FB._seed, L.judge, FB.prefilter
        streams, resamples, prefilters = [], [], []

        def seed(*parts, **kw):
            streams.append((parts[0], kw["seed_id"]))
            return real_seed(*parts, **kw)

        def judge(*args, **kw):
            resamples.append(kw["seed"])
            return real_judge(*args, **kw)

        def prefilter(holdout, run_sha, level):
            prefilters.append(run_sha)
            return real_prefilter(holdout, run_sha, level)

        with contextlib.ExitStack() as stack:
            for function in threaded:
                self.assertEqual(function.__kwdefaults__["seed_id"], development, function.__name__)
                stack.enter_context(patch.dict(function.__kwdefaults__, {"seed_id": None}))
            stack.enter_context(patch.object(FB, "SEED_ID", None))    # a stream that read the constant would be refused
            with self.assertRaises(ValueError):
                FB.market(FB.nyse_sessions("2026-10-05", 5), drift=0.08, replication=0, period="forward", world="absent")
            with self.assertRaises(ValueError):
                FB.desk("absent", 0, slots=2, sessions=5)
            with self.assertRaises(ValueError):
                FB._seed("market", "absent", 0, "forward", seed_id=FB.SEED_ID)
            with patch.object(FB, "_seed", seed), patch.object(L, "judge", judge), patch.object(FB, "prefilter", prefilter):
                got = FB.run([FB.MIXED], 1, slots=2, sessions=45, seed_id=development)["desks"]
                got_demotions = FB.run_demotions(["absent"], programs=2, horizon=25, seed_id=development)["demotion"]
        self.assertEqual(json.dumps(got, sort_keys=True), json.dumps(want, sort_keys=True))
        self.assertEqual(json.dumps(got_demotions, sort_keys=True), json.dumps(want_demotions, sort_keys=True))
        self.assertEqual({name for name, _ in streams}, {"market", "trades", "mix"}, "the generator's streams, all three")
        self.assertEqual(({given for _, given in streams}, FB.SEED_ID), ({development}, development))
        # The designs' resamples are seeded from the desk (its world, its replication, the entrant, its sessions
        # practised) and the pre-filter's from the entrant's run sha: neither from the seed id.
        self.assertEqual(resamples, ["mixed:0:0:40", "mixed:0:1:40"])
        self.assertEqual(prefilters, [f"bench-{r['id']}" for r in got[0]["rows"]])

    def test_the_prefilters_seed_is_the_gates(self):
        from league.swarm import evidence, gate

        seen = []

        def line(result, *, level, seed):
            seen.append((level, seed, evidence.block_bootstrap is FB.np_block_bootstrap))
            return {"passed": True, "pnl": 1.0, "p": 0.01, "level": level}

        with patch.object(evidence, "prefilter_line", line):
            FB.prefilter({"summary": {}}, "bench-7", 0.02)
        self.assertEqual(seen, [(0.02, "prefilter:bench-7", True)], "the gate's line, at the gate's seed, through the port")
        self.assertEqual(gate.PREFILTER_SEED, "prefilter:")
        self.assertIsNot(evidence.block_bootstrap, FB.np_block_bootstrap, "the port is put back")

    def test_the_cli_takes_the_seed_id_and_a_part_names_its_own(self):
        calls = []

        def run(worlds, replications, **kw):
            calls.append(("run", kw["seed_id"]))
            return {"suite": FB.SUITE_ID, "suite_sha": FB.suite_sha(), "seed_id": kw["seed_id"], "desks": []}

        def run_demotions(worlds, **kw):
            calls.append(("demotions", kw["seed_id"]))
            return {"suite": FB.SUITE_ID, "suite_sha": FB.suite_sha(), "seed_id": kw["seed_id"], "demotion": []}

        with tempfile.TemporaryDirectory() as tmp, patch.object(FB, "run", run), \
                patch.object(FB, "run_demotions", run_demotions):
            out = Path(tmp) / "part.json"
            self.assertEqual(FB.main(["--world", "absent", "--seed-id", "a-seed-id", "--output", str(out)]), 0)
            self.assertEqual(json.loads(out.read_text())["seed_id"], "a-seed-id")
            self.assertEqual(FB.main(["--world", "absent", "--output", str(out)]), 0)
            self.assertEqual(FB.main(["--demotion", "--world", "absent", "--seed-id", "a-seed-id"]), 0)
            self.assertEqual(FB.main(["--demotion", "--world", "absent"]), 0)
        self.assertEqual(calls, [("run", "a-seed-id"), ("run", FB.SEED_ID), ("demotions", "a-seed-id"),
                                 ("demotions", FB.SEED_ID)])
        part = FB.run(["absent"], 0)
        self.assertEqual((part["seed_id"], part["desks"], part["suite"]), (FB.SEED_ID, [], "forward-suite-3"))
        self.assertEqual(FB.run_demotions([FB.MIXED])["seed_id"], FB.SEED_ID)
        with self.assertRaisesRegex(ValueError, "the parts differ in seed_id"):
            FB.combine([part, dict(part, seed_id="a-seed-id")])


@unittest.skipUnless(HAVE, "numpy not installed")
class TheRows(unittest.TestCase):
    def forward(self, world, n=40):
        days = FB.nyse_sessions("2026-10-05", n)
        drift = float(FB.WORLDS[world].get("drift", FB.PROTOCOL["market_drift"]))
        path = FB.market(days, drift=drift, replication=0, period="forward", world=world)
        return days, FB.trades(world, 0, 0, "forward", days, path)

    def test_the_rows_are_the_practice_ledgers_and_judge_the_same_through_the_store(self):
        from league.live.observe import ObserveStore

        days, closes = self.forward("planted_dense")
        rows = FB.ledger_rows(closes, start=1)       # the store numbers its rows from 1: the same keys, the same seed
        cohort = {"family": "f", "version": 1, "first_day": days[0], "snapshot": {"run_sha": "s", "practice_evaluator": "e"}}
        rules = L.Rules.from_constitution()
        mine = {"first_day": days[0], "sessions": len(days)}
        direct = L.judge_daily(cohort, mine, rows, through=days[-1], rules=rules)
        at = L.judge(cohort, mine, rows, through=days[-1], rules=rules, checkpoint=40)
        with tempfile.TemporaryDirectory() as tmp:
            store = ObserveStore(tmp, clock=lambda: 1.0)
            store.evaluator = "e"
            engine = [dict(r["body"], id=r["seq"], day=r["exit_day"], evaluator="e") for r in rows]
            self.assertTrue(store.add("f@1:o", "f", 1, engine, account="a"))
            store._connect().execute("INSERT INTO practice(family, version, tier, capital, first_at, first_day, last_at, "
                                     "last_day, sessions) VALUES('f', 1, 'train', 10000, 1, ?, 2, ?, ?)",
                                     (days[0], days[-1], len(days)))
            practice, stored = store.ladder_rows("f", 1, evaluator="e", first_day=days[0], through=days[-1])
            through = L.judge_daily(cohort, practice, stored, through=days[-1], rules=rules)
            through_at = L.judge(cohort, practice, stored, through=days[-1], rules=rules, checkpoint=40)
            store.close()
        for key in ("closes", "mean", "lcb", "p", "windows", "drift", "lines"):
            self.assertEqual(json.dumps(direct[key], sort_keys=True), json.dumps(through[key], sort_keys=True), key)
        # The same at a checkpoint: the same inputs hash, so the same seeds and the same figures to the last digit.
        self.assertEqual(json.dumps(at, sort_keys=True), json.dumps(through_at, sort_keys=True))
        self.assertTrue(at["full"])

    def test_the_drift_control_stops_drift_keeps_premium_and_costs_the_timing_edge(self):
        """On one entrant's sixty forward sessions of each world. THE DRIFT CONTROL as the ladder judges it (L4 at the
        last checkpoint: the tilted test on the drift-adjusted returns, at that checkpoint's alpha), and the mean of
        those returns (the daily lines' reading, which no judgement uses now)."""
        rules = L.Rules.from_constitution()
        at = {}
        for world, passed in (("drift_only", False), ("planted_dense", True), ("planted_premium", True),
                              ("planted_directional", False)):
            days, closes = self.forward(world, 60)
            rows = FB.ledger_rows(closes)
            line = L.drift_line([L.close_of(r) for r in rows], 0.9)
            self.assertEqual(line["passed"], passed, world)
            self.assertEqual(line["share"], 1.0, "every figure is known in the ledger's rows")
            cohort = {"family": "f", "version": 1, "first_day": days[0], "snapshot": {"run_sha": "s"}}
            at[world] = L.judge(cohort, {"first_day": days[0], "sessions": len(days)}, rows, through=days[-1], rules=rules,
                                checkpoint=60)
            self.assertEqual((at[world]["alpha"], at[world]["full"], at[world]["drift"]["share"]), (0.05, True, 1.0), world)
            self.assertEqual(at[world]["lines"]["drift"], at[world]["p_adj"] <= 0.05, world)
        # Drift alone, and a directional timing edge (its P&L IS its delta times the move): nothing is left net of the
        # drift, so the adjusted record cannot be tested at all (p = 1) though the raw record has a mean above zero.
        for world in ("drift_only", "planted_directional"):
            self.assertEqual((at[world]["p_adj"], at[world]["lines"]["drift"]), (1.0, False), world)
            self.assertLess(at[world]["p"], 1.0, world)
        # An edge that is not its delta keeps the line where its record is strong enough for the test...
        self.assertTrue(at["planted_premium"]["lines"]["drift"])
        self.assertLessEqual(at["planted_premium"]["p_adj"], 0.05)
        # ...and loses nothing to the control where it is not: the adjusted record tests as the raw one does.
        for world in ("planted_premium", "planted_dense"):
            self.assertLess(abs(at[world]["p_adj"] - at[world]["p"]), 0.02, world)
        self.assertEqual((at["planted_dense"]["lines"]["drift"], at["planted_dense"]["p"] <= 0.05), (False, False),
                         "this one entrant's record is short of the level on the raw returns too")
        _, closes = self.forward("drift_only", 60)
        self.assertGreater(sum(c["pnl"] for c in closes), 0, "drift alone looks like an edge before the control")

    def test_the_numpy_bootstrap_agrees_with_the_original(self):
        out = FB.bootstrap_agreement()
        self.assertLess(out["max_p_gap"], 0.03)
        for case in out["cases"]:
            self.assertLess(abs(case["lcb_original"] - case["lcb_numpy"]), 0.06)

    def test_the_drift_hold_holds_the_drift_world_only(self):
        days = FB.weekdays(__import__("datetime").date(2025, 1, 2), 252)
        held = {}
        for world in ("drift_only", "absent", "planted_dense"):
            drift = float(FB.WORLDS[world].get("drift", FB.PROTOCOL["market_drift"]))
            path = FB.market(days, drift=drift, replication=1, period="validation", world=world)
            closes = FB.trades(world, 0, 1, "validation", days, path)
            held[world] = FB.drift_hold(FB.gym_result(closes, days), path, closes)
        self.assertEqual(held, {"drift_only": True, "absent": False, "planted_dense": False})


@unittest.skipUnless(HAVE, "numpy not installed")
class TheDesk(unittest.TestCase):
    """THE LADDER's arm is the House's rule: small desks on the development seed id (found, then pinned)."""

    def outcomes(self, out):
        return [(r["id"], r["ladder_outcome"], r["at"], r["start"]) for r in out["rows"]]

    def test_a_small_desk_runs_both_designs_on_the_same_entrants(self):
        out = FB.desk("absent", 0, slots=3, sessions=45)
        self.assertEqual(out["entrants"], len(out["rows"]))
        self.assertGreaterEqual(out["entrants"], 3)
        self.assertEqual([r["id"] for r in out["rows"]], list(range(out["entrants"])), "in admission order")
        for row in out["rows"]:
            self.assertEqual(set(row), ROW)
            self.assertEqual(row["kind"], "negative")
            self.assertIn(row["ladder_outcome"], OUTCOMES)
            self.assertEqual(row["ladder"], row["ladder_outcome"] == "promoted")
            self.assertIs(type(row["start"]), int)
            self.assertIn(row["at"], (None, 40, 60))
            for key in ("ladder", "sealed", "sealed_bare", "validation_passed", "drift_hold", "holdout_ok"):
                self.assertIs(type(row[key]), bool, key)
            self.assertIs(type(row["holdout_p"]), float)
            self.assertTrue(0.0 < row["holdout_p"] <= 1.0)
        # 45 sessions: each of the three was judged once, at its 40-session checkpoint, and practises on.
        self.assertEqual(self.outcomes(out), [(0, "running", None, 0), (1, "running", None, 0), (2, "running", None, 0)])
        self.assertEqual([r["last"]["checkpoint"] for r in out["rows"]], [40, 40, 40])
        self.assertEqual(set(out["rows"][0]["last"]), {"checkpoint", "full", "bound", "windows", "drift", "fdr"})
        short = FB.desk("absent", 0, slots=3, sessions=39)
        self.assertEqual([r["last"] for r in short["rows"]], [None, None, None], "no judgement before a checkpoint")
        again = FB.desk("absent", 0, slots=3, sessions=45)
        self.assertEqual(json.dumps(out, sort_keys=True), json.dumps(again, sort_keys=True), "deterministic")

    def test_a_planted_edge_climbs_at_its_checkpoints_and_a_slot_is_held_until_the_answer(self):
        """The four ways a cohort leaves its slot, on one desk: each slot's next entrant starts the session after."""
        out = small_desk("planted_dense", 0, 4, 70)
        self.assertEqual(self.outcomes(out), [
            (0, "window", None, 0),            # no line met at 40 or at 60: it ends at its window, session index 59
            (1, "promoted", 40, 0),            # latched at index 39, its answer read at index 40
            (2, "promoted", 60, 0),            # latched at its window's end, index 59: held past it, answered at 60
            (3, "validation_failed", 40, 0),   # L1-L5 met at index 39, the Validation line not: it ends that night
            (4, "running", None, 40),          # the slot of 3, freed at index 39's end
            (5, "running", None, 41),          # the slot of 1, held until its answer
            (6, "running", None, 60),          # the slot of 0
            (7, "running", None, 61)])         # the slot of 2, held one session past its window
        rules = L.Rules.from_constitution()
        promoted = [r for r in out["rows"] if r["ladder"]]
        self.assertEqual(len(promoted), 2)
        for r in promoted:
            self.assertTrue(r["holdout_ok"] and r["holdout_p"] <= rules.prefilter_p, "never past the pre-filter's line")
            self.assertTrue(r["validation_passed"], "never past a Validation line it did not meet")
            self.assertEqual(r["last"], {"checkpoint": r["at"], "full": True, "bound": True, "windows": True, "drift": True,
                                         "fdr": True}, "its deciding checkpoint is its last: no line is judged again")
        # A latch is no outcome until its answer is read: the same desk ended on the checkpoint's own session.
        at_40 = FB.desk("planted_dense", 0, slots=4, sessions=40)
        self.assertEqual(self.outcomes(at_40), [(0, "running", None, 0), (1, "running", None, 0), (2, "running", None, 0),
                                                (3, "validation_failed", 40, 0)])
        at_60 = FB.desk("planted_dense", 0, slots=4, sessions=60)
        self.assertEqual(self.outcomes(at_60)[:4], [(0, "window", None, 0), (1, "promoted", 40, 0), (2, "running", None, 0),
                                                    (3, "validation_failed", 40, 0)])

    def test_the_validation_line_then_the_prefilters_line_decide_a_checkpoint_that_met_the_forward_lines(self):
        """The first generation of a planted-premium desk (rewritten for the checkpoint rule: suite 2's `no_validation`
        variant is gone; that an entrant met every forward line and was stopped by L0 or L6 alone is read from its
        last checkpoint's lines)."""
        out = small_desk("planted_premium", 4, 16, 62)   # the protocol's 16 slots, through the first answers
        rules = L.Rules.from_constitution()
        met = {"full": True, "bound": True, "windows": True, "drift": True, "fdr": True}
        first = out["rows"][:16]
        self.assertEqual([(r["ladder_outcome"], r["at"]) for r in first], [
            (P, 60), (P, 60), (W, None), (P, 60), (P, 60), (P, 60), (W, None), (V, 60), ("prefilter_negative", 60), (P, 60),
            (W, None), (P, 60), (P, 60), (P, 60), (W, None), (P, 40)])
        failed = [r for r in first if r["ladder_outcome"] == V]
        self.assertTrue(failed and all(not r["validation_passed"] and not r["ladder"] for r in failed))
        for r in failed:
            self.assertEqual(r["last"], dict(met, checkpoint=r["at"]), "it met L1-L5; the Validation line alone stopped it")
        asked = [r for r in out["rows"] if r["ladder_outcome"] in (P, "prefilter_negative")]
        self.assertTrue(all(r["validation_passed"] for r in asked), "the pre-filter is asked for past the Validation line")
        negative = [r for r in first if r["ladder_outcome"] == "prefilter_negative"]
        self.assertEqual(len(negative), 1)
        for r in negative:
            self.assertEqual(r["last"], dict(met, checkpoint=r["at"]))
            self.assertTrue(r["holdout_ok"], "its holdout P&L is not negative: suite 2 would have promoted it")
            self.assertGreater(r["holdout_p"], rules.prefilter_p, "the bootstrap's p-value is over the line")
        for r in out["rows"]:
            if r["ladder"]:
                self.assertTrue(r["holdout_ok"] and r["holdout_p"] <= rules.prefilter_p)
            if r["ladder_outcome"] == W:
                self.assertEqual(r["last"]["checkpoint"], 60)
                self.assertFalse(all(r["last"][k] for k in met), "it ended at its window: a line was not met")
        # The slots: 5 ended at index 59 (4 windows, 1 Validation failure at 60), 10 read their answer at index 60.
        self.assertEqual(sorted(r["start"] for r in out["rows"][16:]), [41] + [60] * 5 + [61] * 10)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheHouseAndTheDesk(StoreCase):
    """The desk plays the House's rule: the House's own session end (`Ladder.end_of_day` on a real practice store: its
    checkpoints, its latch, its answer session, its store's window and hold, binding) ends every entrant of a desk as
    `desk` does, and frees its slot the same session. Only the three resamples' seeds are the benchmark's (the House
    seeds them from its inputs hash)."""

    def house(self, world, replication, *, slots, sessions):
        """The desk of a single world played by the House: [(entrant, outcome, checkpoint, admission's session index)]."""
        rules = dataclasses.replace(L.Rules.from_constitution(), binding=True)
        *forward_days, after = FB.nyse_sessions(FB.PROTOCOL["first_session"], sessions + 1)
        days = {"validation": FB.weekdays(dt.date(FB.PROTOCOL["validation_year"], 1, 2), 252),
                "holdout": FB.weekdays(dt.date.fromisoformat(FB.PROTOCOL["holdout_first"]),
                                       FB.PROTOCOL["holdout_sessions"])}
        drift = float(FB.WORLDS[world].get("drift", FB.PROTOCOL["market_drift"]))
        paths = {period: FB.market(days.get(period, forward_days), drift=drift, replication=replication,
                                   period=period, world=f"{world}:drift{drift}")
                 for period in ("validation", "holdout", "forward")}
        bridge, alerts, starts = MemoryBridge(), [], {}
        live = SimpleNamespace(observe_store=self.store, clock=lambda: self.now[0], record=lambda *a, **k: None,
                               alert=lambda level, text: alerts.append(text))
        ladder, db, real_judge = L.Ladder(live, bridge=bridge), self.store._connect(), L.judge

        def judge(cohort, practice, rows, **kw):
            entrant = int(cohort["family"].split("-")[1])
            return real_judge(cohort, practice, rows, **kw, seed=f"{world}:{replication}:{entrant}:{practice['sessions']}")

        for t, day in enumerate(forward_days):
            if t:
                self.store.cohort_candidates([], day=day, in_session=True)   # the session's first pins: windows end
            active = [f for (f,) in db.execute("SELECT family FROM cohorts WHERE status='active' ORDER BY family")]
            while len(active) < slots:
                i = len(starts)
                fam = f"e-{i}"
                e = FB._entrant(world, i, replication, paths, days)
                bridge.validated[fam] = e["validation_line"]["passed"]
                # The gate's record of its read, as `Gate._prefilter_write` writes one that is done.
                bridge.prefilters[f"bench-{i}"] = dict(FB.prefilter(e["holdout"], f"bench-{i}", rules.prefilter_p),
                                                       status="done", bundle="bundle", ran_bundle="bundle")
                self.store.freeze({"family": fam, "version": 1, "band": "gym", "observe": True, "tier": "validated",
                                   "lineage": fam, "code": CODE, "params": {}, "run_sha": f"bench-{i}",
                                   "structure": "debit_vertical"}, day=day)
                window = forward_days[t:t + rules.max_sessions]
                closes = FB.trades(world, i, replication, "forward", window, paths["forward"])
                engine = [dict(r["body"], id=r["seq"], day=r["exit_day"], evaluator=EVALUATOR)
                          for r in FB.ledger_rows(closes, start=1)]
                self.assertTrue(self.store.add(f"{fam}@1:o", fam, 1, engine, account="a"))
                db.execute("INSERT INTO practice(family, version, tier, capital, first_at, first_day, last_at, last_day, "
                           "sessions) VALUES(?, 1, 'validated', 10000, 1, ?, 2, ?, 0)", (fam, day, day))
                starts[fam] = t
                active.append(fam)
            for fam in active:
                db.execute("UPDATE practice SET sessions=?, last_day=? WHERE family=?", (t - starts[fam] + 1, day, fam))
            with patch.object(L.Rules, "from_constitution", return_value=rules), patch.object(L, "judge", judge), \
                    patch.object(L.Ladder, "_bundle", return_value="bundle"):
                out = ladder.end_of_day(day)
            self.assertNotIn("error", out["verdicts"], (day, alerts))
        # The pins of the session after the desk's last: a window that ended on the last session ends there in the House.
        self.store.cohort_candidates([], day=after, in_session=True)
        played = []
        for fam, start in starts.items():
            status, reason = db.execute("SELECT status, reason FROM cohorts WHERE family=?", (fam,)).fetchone()
            receipt = db.execute("SELECT verdict, checkpoint, stats FROM ladder_decisions WHERE family=? ORDER BY id DESC "
                                 "LIMIT 1", (fam,)).fetchone()
            latch = (json.loads(receipt[2]) if receipt else {}).get("latch") or {}
            if status == "active":
                outcome, at = "running", None
            elif status == "promoted":
                outcome, at = "promoted", latch["checkpoint"]
            elif status == "failed":
                outcome, at = receipt[0], receipt[1] if receipt[1] is not None else latch["checkpoint"]
            else:
                self.assertEqual((status, reason), ("complete", O.WINDOW_ENDED), fam)
                outcome, at = "window", None
            played.append((int(fam.split("-")[1]), outcome, at, start))
        self.assertEqual(len(bridge.promoted), sum(1 for row in played if row[1] == "promoted"))
        return played

    def played_alike(self, world, replication, slots, sessions):
        desk = small_desk(world, replication, slots, sessions)
        want = [(r["id"], r["ladder_outcome"], r["at"], r["start"]) for r in desk["rows"]]
        self.assertEqual(self.house(world, replication, slots=slots, sessions=sessions), want)
        return {(outcome, at) for _, outcome, at, _ in want}

    def test_the_house_ends_every_entrant_of_a_small_desk_as_the_desk_does(self):
        # Every way out but a failed pre-filter read, the hold past the window among them (`TheDesk` pins this desk).
        self.assertEqual(self.played_alike("planted_dense", 0, 4, 70),
                         {("window", None), ("promoted", 40), ("promoted", 60), ("validation_failed", 40),
                          ("running", None)})

    def test_the_house_ends_the_first_generation_of_a_protocol_desk_as_the_desk_does(self):
        # The protocol's 16 slots through the first answers: a read that fails on its p-value alone among them.
        self.assertEqual(self.played_alike("planted_premium", 4, 16, 62),
                         {("window", None), ("promoted", 40), ("promoted", 60), ("validation_failed", 60),
                          ("prefilter_negative", 60), ("running", None)})


@unittest.skipUnless(HAVE, "numpy not installed")
class TheGoldenDesks(unittest.TestCase):
    """The protocol's own desks on the development seed id: the production desk reproduces the development harness's
    rows, and the module's report counts them.

    A FIXTURE, NEVER A READING OF THE RULE. The tallies pinned below are ONE development desk a world (replication 0 on
    the public default seed id, which anyone can replay): they hold the desk's arithmetic and the report's table to the
    judge's count. They are no aggregate, no expectation and no verdict about the ladder's binding. The binding rule is
    judged on a confirmation's desks alone, on seeds never used in development, by `scripts/ladder_judge.py`."""

    def test_the_desk_reproduces_the_harnesss_rows(self):
        part = protocol_part()
        self.assertEqual([(d["world"], d["replication"]) for d in part["desks"]], [(w, 0) for w in GOLDEN])
        self.assertEqual((part["seed_id"], part["slots"], part["sessions"]), ("forward-suite-1", 16, 160))
        for d in part["desks"]:
            want = [(i, *row) for i, row in enumerate(GOLDEN[d["world"]])]
            self.assertEqual([(r["id"], r["ladder_outcome"], r["at"], r["start"]) for r in d["rows"]], want, d["world"])
            self.assertEqual(d["entrants"], len(want))
        rules = L.Rules.from_constitution()
        self.assertEqual((rules.checkpoints, rules.alphas, rules.prefilter_p, rules.max_sessions),
                         ((40, 60), (0.004, 0.05), 0.02, 60), "the rule the golden rows were played under")

    def test_the_report_counts_the_first_32_and_names_no_verdict(self):
        part = protocol_part()
        mixed = next(d for d in part["desks"] if d["world"] == FB.MIXED)
        self.assertGreater(len({r["world"] for r in mixed["rows"]}), 1, "a mixed desk draws several worlds")
        judge = judge_module()
        for d in part["desks"]:
            self.assertEqual(FB.counted(d), judge.counted(d["rows"], d["world"], d["replication"]), "the judge's count")
        report = FB.combine([part])
        agg = report["aggregate"]
        self.assertEqual(report["seed_id"], "forward-suite-1")
        # The single-world desk: 32 counted positives, 19 promoted by the ladder. Its two promotions of the third
        # generation (ids 34 and 35) are not counted, and its 16 entrants still running are neither counted nor an error.
        premium = agg["worlds"]["planted_premium"]
        self.assertEqual((premium["desks"], premium["entrants"]), (1, 32))
        self.assertEqual({d: (r["count"], r["of"]) for d, r in premium["missed_signals"].items()},
                         {"ladder": (13, 32), "sealed": (22, 32), "sealed_bare": (22, 32)})
        self.assertEqual(sum(1 for r in part["desks"][1]["rows"] if r["ladder"]), 21)
        self.assertEqual({d: (r["count"], r["of"]) for d, r in agg["mixed_negatives"].items()},
                         {"ladder": (0, 19), "sealed": (5, 19), "sealed_bare": (6, 19)})
        self.assertEqual({d: (r["count"], r["of"]) for d, r in agg["mixed_positives"].items()},
                         {"ladder": (11, 13), "sealed": (9, 13), "sealed_bare": (10, 13)})
        self.assertEqual(agg["pooled_negatives"]["ladder"]["of"], 0, "the single-world desk here has no negative")
        text = FB.markdown(report)
        self.assertTrue(text.startswith("# Forward ladder benchmark (forward-suite-3)"))
        self.assertIn(f"**Verdict: {FB.VERDICT}.**", text)
        self.assertIn("the first 32 entrants of each desk in admission order, whatever their outcome", text)
        self.assertIn("seed id `forward-suite-1`", text)
        self.assertIn("| planted_premium (missed) | 1 | 32 | 13/32", text)
        self.assertIn("| mixed (FP) | 1 | 19 | 0/19", text)
        self.assertIn("| mixed (missed) | 1 | 13 | 11/13", text)
        for gone in ("Binding rule", "MET", "Variants", "exceed"):
            self.assertNotIn(gone, text)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "part.json"
            path.write_text(json.dumps(part, default=str))
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                self.assertEqual(FB.main(["--combine", str(path), "--report", str(Path(tmp) / "r.md"), "--json"]), 0)
            self.assertEqual((Path(tmp) / "r.md").read_text(), text)
            headline = json.loads(printed.getvalue())
            self.assertEqual((headline["verdict"], headline["counted"], headline["seed_id"]), (FB.VERDICT, 32, FB.SEED_ID))
            self.assertNotIn("binding", headline)
            self.assertEqual(headline["mixed_positives"]["ladder"]["count"], 11)
            # The same desk twice is no second replication.
            with self.assertRaisesRegex(ValueError, "the parts hold mixed replication 0 twice"):
                FB.combine([part, part])
            # A run that is not the protocol's has no count: the part is written, the report refused.
            short = Path(tmp) / "short.json"
            refused = io.StringIO()
            with contextlib.redirect_stderr(refused):
                self.assertEqual(FB.main(["--world", "absent", "--replications", "1", "--slots", "2", "--sessions", "30",
                                          "--output", str(short), "--json"]), 2)
            self.assertIn("no report: absent replication 0 has not its first 32 entrants", refused.getvalue())
            self.assertEqual(len(json.loads(short.read_text())["desks"]), 1)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheDemotionRule(unittest.TestCase):
    """THE DEMOTION RULE's measurement (the WP6 review): the ladder's demotion through the money table's own functions,
    and the other readings of its words, on a promoted program's forward stream."""

    def test_the_readings_are_ordered_as_their_definitions_say(self):
        for world in ("absent", "planted_dense"):
            out = FB.demotions(world, programs=12, horizon=40)
            self.assertEqual((out["world"], out["programs"], out["horizon"]), (world, 12, 40))
            r = {name: {m: by[m]["count"] for m in by} for name, by in out["readings"].items()}
            self.assertEqual(set(r["as_built"]), {"20", "40"})
            for m in ("20", "40"):
                self.assertGreaterEqual(r["bound_95"][m], r["as_built"][m], "a higher confidence's bound is lower")
                self.assertLessEqual(r["blocks_of_20"][m], r["as_built"][m], "a block reads the bound less often")
                self.assertLessEqual(r["negative_only"][m], r["as_built"][m])
                self.assertLessEqual(r["as_built"]["20"], r["as_built"]["40"])
        self.assertEqual(json.dumps(FB.demotions("absent", programs=3, horizon=25), sort_keys=True),
                         json.dumps(FB.demotions("absent", programs=3, horizon=25), sort_keys=True), "deterministic")

    def test_its_part_combines_into_the_report(self):
        part = protocol_part()
        demotion = FB.run_demotions(["absent", FB.MIXED], programs=2, horizon=25)
        self.assertEqual([w["world"] for w in demotion["demotion"]], ["absent"], "a world's own programs, never mixed")
        report = FB.combine([part, demotion])
        self.assertEqual([w["world"] for w in report["demotion"]], ["absent"])
        self.assertIn("The demotion rule", FB.markdown(report))
        with self.assertRaises(ValueError):
            FB.combine([part, dict(demotion, suite_sha="another")])

    def test_demotion_parts_alone_make_a_report_of_the_demotion_rule(self):
        demotion = FB.run_demotions(["absent", "planted_dense"], programs=2, horizon=25)
        report = FB.combine([demotion])
        self.assertEqual([w["world"] for w in report["demotion"]], ["absent", "planted_dense"])
        self.assertEqual((report["suite"], report["suite_sha"], report["seed_id"]),
                         (FB.SUITE_ID, FB.suite_sha(), FB.SEED_ID))
        self.assertNotIn("aggregate", report, "no desk: no count")
        text = FB.markdown(report)
        self.assertIn("The demotion rule", text)
        self.assertIn("| absent (negative) |", text)
        self.assertNotIn("Verdict", text)
        both = FB.combine([FB.run_demotions(["absent"], programs=2, horizon=25),
                           FB.run_demotions(["planted_dense"], programs=2, horizon=25)])
        self.assertEqual(json.dumps(both["demotion"], sort_keys=True), json.dumps(report["demotion"], sort_keys=True))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demotion.json"
            path.write_text(json.dumps(demotion, default=str))
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                self.assertEqual(FB.main(["--combine", str(path), "--report", str(Path(tmp) / "r.md"),
                                          "--output", str(Path(tmp) / "full.json"), "--json"]), 0)
            self.assertIn("The demotion rule", (Path(tmp) / "r.md").read_text())
            self.assertEqual(json.loads((Path(tmp) / "full.json").read_text())["demotion"], report["demotion"])
            self.assertEqual(json.loads(printed.getvalue())["counted"], None)
        with self.assertRaisesRegex(ValueError, "no part to combine"):
            FB.combine([])


if __name__ == "__main__":
    unittest.main()
