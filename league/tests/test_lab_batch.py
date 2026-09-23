"""The lab's batch evaluator: `replay.run_batch`, `sandbox.replay_batch` and `labbox.LabBox`.

The promise under test is that a batch is a faster way to get EXACTLY the numbers single replays
give: every candidate's result equals `run_replay`'s for it (plus its id), whatever else is in the
batch -- a crash, a hang, a candidate that tampers with its interpreter -- and however many
workers run it. Then the tape cache (upload once, reuse, re-upload on a miss), the seal on a bound
lab box, and the holdout: no tape that reaches into the sealed window ever enters a batch box.
"""

from __future__ import annotations

import calendar
import gzip
import hashlib
import json
import random
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from league import ci, replay, seeds
from league.experiments import Archive
from league.labbox import LabBox
from league.replay import NOT_EVALUATED, run_batch, run_replay
from league.runner import needs_of
from league.sandbox import (RESULT_DIR, SEALED, TAPE_DIR, LocalSandbox, SailSandbox, SandboxError, TapeMissing, TapeRefused,
                            holdout_problem, tape_bytes, tape_digest)
from league.tests.test_sandbox import FakeSail

STRATEGIES = Path(replay.__file__).resolve().parent / "strategies"
LIMITS = {"max_position_usd": 100.0, "max_order_usd": 75.0}

CRASH_ON_LOAD = "x = 1 / 0\n\ndef decide(ctx):\n    return {}\n"
CRASH_IN_DECIDE = "def decide(ctx):\n    return {'intents': [1 / 0]}\n"
REFUSED = "import os\n\ndef decide(ctx):\n    return {}\n"
SLOW = "import time\n\ndef decide(ctx):\n    time.sleep(0.3)\n    return {}\n"
#: Swallows its decide deadline inside an endless loop: a single replay of it runs until the box's
#: own limit; a batch stops it at `candidate_seconds`.
HANGS = ("def decide(ctx):\n    while True:\n        try:\n            while True:\n                pass\n"
         "        except BaseException:\n            pass\n")
#: Changes its interpreter's decimal context, which the simulator's Kalshi fee arithmetic uses.
#: Run in the same process as another candidate it would change that candidate's fees.
POISON = "import decimal\n\ndef decide(ctx):\n    decimal.setcontext(decimal.Context(prec=1))\n    return {}\n"
#: Asks for far more memory than a candidate may add.
HOG = "def decide(ctx):\n    block = [0] * (10 ** 9)\n    return {'memory': {'n': len(block)}}\n"
#: Sleeps a little at every step: a candidate that takes a while, for the budget.
PLODS = "import time\n\ndef decide(ctx):\n    time.sleep(0.02)\n    return {}\n"
#: Takes the touch on Kalshi, so it pays the taker fee the simulator computes in decimal arithmetic.
TAKER = """
NEEDS = {"venue": "kalshi", "horizon": "hour", "series": ["KXBTCD"]}

def decide(ctx):
    if ctx["positions"] or ctx["open_orders"]:
        return {}
    for market in ctx["markets"]:
        ask = market.get("yes_ask")
        if ask and 0.3 <= ask <= 0.8:
            return {"intents": [{"market": market["market"], "leg": "yes", "side": "buy", "type": "market", "quantity": 7,
                                 "reason": "take the touch"}]}
    return {}
"""


def small(venue: str, *, steps: int = 240, seed: int = 7) -> dict:
    """A canned tape (`ci.regression_tape`) short enough that a test replays it many times."""
    return ci.regression_tape(venue, steps=steps, seed=seed)


def seed_candidates(venue: str) -> list[dict]:
    return [{"id": f"seed:{s['name']}", "code": s["code"], "params": {}} for s in seeds.all_seeds()
            if needs_of(s["code"])["needs"].get("venue") == venue]


def strategy_candidates(venue: str) -> list[dict]:
    out = []
    for path in sorted(STRATEGIES.glob("*.py")):
        if path.name == "__init__.py":
            continue
        code = path.read_text(encoding="utf-8")
        try:
            wanted = needs_of(code)["needs"].get("venue")
        except Exception:  # noqa: BLE001 - one the runner cannot read is not this test's business
            continue
        if wanted == venue:
            params = path.with_suffix(".json")
            out.append({"id": f"strategy:{path.stem}", "code": code,
                        "params": (json.loads(params.read_text(encoding="utf-8")).get("params") or {}) if params.exists() else {}})
    return out


def single(candidate: dict, tape: dict, **options) -> dict:
    """What one box run of the candidate answers (`replay.main`): the result as JSON, or the
    failure `main` prints when it cannot be encoded."""
    try:
        result = json.loads(json.dumps(run_replay(candidate.get("code"), candidate.get("params"), tape, **options), allow_nan=False))
    except ValueError as exc:
        result = {"ok": False, "error": f"replay failed: {type(exc).__name__}: {str(exc)[:200]}"}
    return {**result, "id": candidate["id"]}


def dated_tape(first: str, days: int, *, warmup_from: str | None = None) -> dict:
    """A small alpaca tape with hourly steps from `first` (a day) for `days` days."""
    start = calendar.timegm(time.strptime(first, "%Y-%m-%d"))
    steps = []
    for hour in range(days * 24):
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start + hour * 3600))
        price = 100.0 + (hour % 7)
        steps.append({"t": stamp, "bars": {"SPY": {"o": price, "h": price + 1, "l": price - 1, "c": price, "v": 10.0}}})
    tape = {"venue": "alpaca", "horizon": "hour", "step_seconds": 3600, "steps": steps, "results": {}}
    if warmup_from:
        tape["warmup_bars"] = {"SPY": [{"t": f"{warmup_from}T00:00:00Z", "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0}]}
    return tape


# =================================================================================================
# run_batch: the same numbers as single replays
# =================================================================================================
class BatchEqualsSingle(unittest.TestCase):
    def assert_same(self, candidates: list[dict], tape: dict, **options):
        out = run_batch(candidates, tape, **options)
        self.assertEqual([r["id"] for r in out], [c["id"] for c in candidates])
        replay_options = {k: v for k, v in options.items() if k in ("stake", "limits", "oos_fraction", "max_decide_seconds")}
        for candidate, result in zip(candidates, out):
            self.assertEqual(result, single(candidate, tape, **replay_options), candidate["id"])
        return out

    def test_seeds_and_strategies_on_both_venues(self):
        for venue in ("alpaca", "kalshi"):
            with self.subTest(venue=venue):
                candidates = seed_candidates(venue) + strategy_candidates(venue)
                self.assertGreaterEqual(len(candidates), 4)
                out = self.assert_same(candidates, small(venue, steps=360), workers=3)
                self.assertTrue(any(r["ok"] and r["trades"] > 0 for r in out))  # the batch really traded

    def test_crashing_refused_and_slow_candidates_answer_as_they_do_alone(self):
        tape = ci.regression_tape("alpaca", steps=120)
        # Only candidates whose answer does not depend on the machine's speed share this short deadline.
        candidates = [{"id": "load", "code": CRASH_ON_LOAD}, {"id": "decide", "code": CRASH_IN_DECIDE},
                      {"id": "refused", "code": REFUSED}, {"id": "slow", "code": SLOW}, {"id": "no-code"}]
        out = self.assert_same(candidates, tape, workers=3, max_decide_seconds=0.05)
        by = {r["id"]: r for r in out}
        self.assertIn("did not load", by["load"]["error"])
        self.assertEqual(by["decide"]["error"], "too many errors")
        self.assertIn("refused", by["refused"]["error"])
        self.assertEqual(by["slow"]["error"], "too many errors")
        self.assertIn("took longer", by["slow"]["last_error"])

    def test_every_option_reaches_every_candidate(self):
        tape = small("kalshi")
        self.assert_same(seed_candidates("kalshi"), tape, workers=2, stake=500.0, limits={"max_position_usd": 40.0, "max_order_usd": 20.0},
                         oos_fraction=0.5)

    def test_worker_count_changes_nothing(self):
        tape = small("alpaca")
        candidates = seed_candidates("alpaca")
        self.assertEqual(run_batch(candidates, tape, workers=1), run_batch(candidates, tape, workers=4))

    def test_the_in_process_fallback_gives_the_same_numbers(self):
        tape = small("kalshi")
        candidates = seed_candidates("kalshi")
        self.assertEqual(run_batch(candidates, tape, workers=0), run_batch(candidates, tape, workers=2))

    def test_a_bad_tape_fails_every_candidate_as_it_fails_one(self):
        tape = {"venue": "alpaca", "steps": [{"t": "2026-08-03T00:00:00Z"}, {"t": "2026-08-02T00:00:00Z"}]}
        out = self.assert_same(seed_candidates("alpaca")[:2], tape, workers=2)
        self.assertTrue(all("bad tape" in r["error"] for r in out))

    def test_a_malformed_candidate_is_answered_in_its_place(self):
        out = run_batch(["not a dict", {"code": "x"}, *seed_candidates("kalshi")[:1]], small("kalshi"), workers=1)
        self.assertEqual(len(out), 3)
        self.assertIn("malformed candidate", out[0]["error"])
        self.assertIn("malformed candidate", out[1]["error"])
        self.assertTrue(out[2]["ok"])

    def test_empty(self):
        self.assertEqual(run_batch([], small("kalshi")), [])


class BatchIsolation(unittest.TestCase):
    def test_a_candidate_that_tampers_with_its_interpreter_reaches_no_other(self):
        tape = small("kalshi")
        others = [{"id": "taker", "code": TAKER}] + seed_candidates("kalshi")
        # POISON first, one worker: every other candidate's process is forked after it ran.
        out = run_batch([{"id": "poison", "code": POISON}] + others, tape, workers=1)
        self.assertTrue(out[0]["ok"])
        for candidate, result in zip(others, out[1:]):
            self.assertEqual(result, single(candidate, tape), candidate["id"])
        self.assertTrue(any(r["fees_usd"] > 0 for r in out[1:]))  # the fee arithmetic really ran

    def test_a_hung_candidate_is_stopped_and_the_rest_are_answered(self):
        tape = ci.regression_tape("kalshi", steps=120)
        others = seed_candidates("kalshi")[:2]
        started = time.monotonic()
        out = run_batch([{"id": "hangs", "code": HANGS}] + others, tape, workers=3, candidate_seconds=4.0)
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(out[0], {"ok": False, "error": "timed out after 4s", "id": "hangs"})
        for candidate, result in zip(others, out[1:]):
            self.assertEqual(result, single(candidate, tape), candidate["id"])

    def test_a_memory_hog_fails_alone(self):
        tape = small("kalshi")
        others = seed_candidates("kalshi")[:2]
        out = run_batch([{"id": "hog", "code": HOG}] + others, tape, workers=2, memory_mb=256)
        self.assertFalse(out[0]["ok"])
        self.assertIn("MemoryError", json.dumps(out[0]))
        for candidate, result in zip(others, out[1:]):
            self.assertEqual(result, single(candidate, tape), candidate["id"])


class Budget(unittest.TestCase):
    def test_a_spent_budget_evaluates_nothing(self):
        candidates = seed_candidates("kalshi")
        out = run_batch(candidates, small("kalshi"), budget_seconds=0)
        self.assertEqual(out, [{"ok": False, "error": NOT_EVALUATED, "id": c["id"]} for c in candidates])

    def test_the_budget_cuts_off_what_it_did_not_reach(self):
        tape = ci.regression_tape("alpaca", steps=60)  # about 1.2 s a candidate
        candidates = [{"id": f"plod-{i}", "code": PLODS} for i in range(8)]
        started = time.monotonic()
        out = run_batch(candidates, tape, workers=1, budget_seconds=2.0)
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual([r["id"] for r in out], [c["id"] for c in candidates])
        self.assertEqual(out[-1], {"ok": False, "error": NOT_EVALUATED, "id": "plod-7"})
        reached = [r for r in out if r.get("error") != NOT_EVALUATED]
        self.assertLess(len(reached), 8)
        for result in reached:  # what it did evaluate is exactly a single replay
            self.assertEqual(result, single(candidates[0], tape) | {"id": result["id"]})

    def test_the_budget_counts_from_the_call(self):
        clock = iter([0.0, 5.0] + [100.0] * 100)
        out = run_batch(seed_candidates("kalshi")[:2], small("kalshi"), budget_seconds=10.0, clock=lambda: next(clock))
        self.assertTrue(all(r["error"] == NOT_EVALUATED for r in out))


class PreparedTape(unittest.TestCase):
    def test_the_bar_index_answers_exactly_what_bars_until_does(self):
        rng = random.Random(11)
        for trial in range(40):
            bars = []
            for _ in range(rng.randint(0, 30)):
                kind = rng.random()
                if kind < 0.1:
                    bars.append("junk")
                elif kind < 0.2:
                    bars.append({"t": "not a time"})
                else:  # mostly in order, with the odd row out of place
                    bars.append({"t": f"2026-09-10T{rng.randint(0, 23):02d}:{rng.choice([0, 30]):02d}:00Z", "c": rng.random()})
            prepared = replay._Prepared({}, eager=False)
            for hour in range(-1, 25):
                now = replay._parse_ts(f"2026-09-10T{max(0, min(23, hour)):02d}:15:00Z") + (hour < 0) * -86400
                want = replay._bars_until(bars, now)
                self.assertEqual(prepared.bars_until("x", "S", bars, now), want, (trial, hour))
                for last in (1, 3, 60):
                    self.assertEqual(prepared.bars_until("x", "S", bars, now, last), want[-last:], (trial, hour, last))

    def test_an_eager_reading_is_the_lazy_one(self):
        for venue in ("alpaca", "kalshi"):
            tape = ci.regression_tape(venue)
            eager, lazy = replay._Prepared(tape, eager=True), replay._Prepared(tape)
            for index, step in enumerate(tape["steps"][:200]):
                stamp = lazy.stamp(index, step)
                self.assertEqual(eager.stamp(index, step), stamp)
                self.assertEqual(eager.block_key(index, stamp, "day"), lazy.block_key(index, stamp, "day"))
                half, stress = replay._spread_of(tape)
                a, b = {}, {}
                self.assertEqual(vars(eager.view(index, step, venue, half, stress, a)), vars(lazy.view(index, step, venue, half, stress, b)))
                self.assertEqual(a, b)


# =================================================================================================
# The box program and the sandboxes
# =================================================================================================
class BoxProgram(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def put(self, tape) -> tuple[str, str]:
        raw = tape_bytes(tape)
        path = self.root / "tape.json.gz"
        path.write_bytes(gzip.compress(raw))
        return str(path), hashlib.sha256(raw).hexdigest()

    def test_a_tape_from_file_answers_like_one_inline(self):
        tape = small("kalshi")
        path, digest = self.put(tape)
        candidates = seed_candidates("kalshi")
        from_file = replay._main_batch({"candidates": candidates, "tape_path": path, "tape_digest": digest, "workers": 2})
        inline = replay._main_batch({"candidates": candidates, "tape": tape, "workers": 2})
        self.assertEqual(from_file["results"], inline["results"])
        self.assertEqual(from_file["evaluated"], len(candidates))

    def test_a_missing_or_different_tape_is_reported_as_missing(self):
        path, digest = self.put(small("kalshi"))
        self.assertEqual(replay._main_batch({"candidates": [], "tape_path": str(self.root / "nope.json.gz")})["tape_missing"], True)
        wrong = replay._main_batch({"candidates": [], "tape_path": path, "tape_digest": "0" * 64})
        self.assertEqual((wrong["ok"], wrong["tape_missing"], wrong["error"]), (False, True, "tape does not match its digest"))

    def test_the_full_results_go_to_a_file_with_their_digest(self):
        tape = small("kalshi")
        out = self.root / "results" / "r.json.gz"
        summary = replay._main_batch({"candidates": seed_candidates("kalshi"), "tape": tape, "result_path": str(out), "workers": 1})
        raw = out.read_bytes()
        self.assertEqual(summary["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotIn("results", summary)
        self.assertEqual(json.loads(gzip.decompress(raw))["results"], run_batch(seed_candidates("kalshi"), tape, workers=1))


class Local(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.box = LocalSandbox(Path(self.dir.name) / "boxes")
        self.tape = small("kalshi")
        self.digest = tape_digest(self.tape)
        self.candidates = seed_candidates("kalshi") + [{"id": "crash", "code": CRASH_IN_DECIDE}]

    def tearDown(self):
        self.dir.cleanup()

    def batch(self, tape, **options):
        return self.box.replay_batch("lab", self.candidates, tape, tape_digest=options.pop("digest", self.digest), stake=200.0,
                                     limits=LIMITS, timeout=120, **options)

    def test_the_tape_is_sent_once_and_reused(self):
        first = self.batch(self.tape)
        again = self.batch(None)
        self.assertEqual((first.result["uploaded"], again.result["uploaded"]), (True, False))
        self.assertEqual(first.result["results"], again.result["results"])
        self.assertEqual(first.result["results"], [single(c, self.tape) for c in self.candidates])
        self.assertEqual(first.result["evaluated"], len(self.candidates))
        self.assertEqual(sorted(p.name for p in (Path(self.dir.name) / "boxes" / "lab" / "tapes").iterdir()), [f"{self.digest}.json.gz"])
        self.assertFalse(list((Path(self.dir.name) / "boxes" / "lab").glob("batch-*.json")))  # the spec is cleaned up

    def test_a_tape_the_box_does_not_hold_is_asked_for(self):
        with self.assertRaises(TapeMissing):
            self.batch(None)
        self.batch(self.tape)
        (Path(self.dir.name) / "boxes" / "lab" / "tapes" / f"{self.digest}.json.gz").unlink()  # the box lost it
        with self.assertRaises(TapeMissing):
            self.batch(None)

    def test_a_tape_that_is_not_its_digest_is_refused(self):
        with self.assertRaises(TapeRefused):
            self.batch(self.tape, digest="a" * 64)
        with self.assertRaises(SandboxError):
            self.batch(self.tape, digest="not a digest")

    def test_a_holdout_tape_never_reaches_the_box(self):
        sealed = dated_tape("2025-12-01", 3)
        with self.assertRaises(TapeRefused):
            self.box.replay_batch("lab", self.candidates, sealed, tape_digest=tape_digest(sealed), stake=200.0, limits=LIMITS)
        self.assertFalse((Path(self.dir.name) / "boxes" / "lab" / "tapes").exists())

    def test_the_budget_reaches_the_box(self):
        run = self.batch(self.tape, budget_seconds=0)
        self.assertTrue(all(r["error"] == NOT_EVALUATED for r in run.result["results"]))
        self.assertEqual(run.result["evaluated"], 0)


class BatchSail(FakeSail):
    """`FakeSail` whose boxes run a batch for real: `exec` reads the uploaded batch spec and tape
    from the box's files and runs `replay._main_batch` on them, and `download` serves the result."""

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.downloads: list[str] = []

    def exec(self, box, argv, *, timeout=600):
        self._call("exec", box, tuple(argv), timeout)
        state = self._box(box)
        if state["status"] != "running":
            raise RuntimeError(f"409: {box} is {state['status']}")
        command = argv[-1]
        kit = command.split("cd ", 1)[1].split(" && ", 1)[0]
        name = command.split("--batch ", 1)[1].split(";", 1)[0].strip()
        spec = json.loads(state["files"][f"{kit}/{name}"].decode("utf-8"))
        self.execs.append({"box": box, "spec": spec, "egress": state["egress"], "files": sorted(state["files"])})
        local = self.root / box
        local.mkdir(parents=True, exist_ok=True)
        tape = state["files"].get(spec["tape_path"])
        tape_path = local / "tape.json.gz"
        if tape is None:
            tape_path.unlink(missing_ok=True)
        else:
            tape_path.write_bytes(tape)
        result_path = local / "result.json.gz"
        summary = replay._main_batch({**spec, "tape_path": str(tape_path), "result_path": str(result_path)})
        if summary.get("ok"):
            state["files"][spec["result_path"]] = result_path.read_bytes()
            summary["result_path"] = spec["result_path"]
        return SimpleNamespace(stdout=f"{replay.RESULT_PREFIX} {spec['token']} {json.dumps(summary)}\n", stderr="", return_code=0)

    def download(self, box, path, *, timeout=300.0):
        self._call("download", box, path)
        self.downloads.append(path)
        return self._box(box)["files"][path]


class Sail(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.sail = BatchSail(self.root / "boxes")
        self.sandbox = SailSandbox(self.sail, self.root / "state" / "sandbox.json", image_checkpoint="cp_clean_image")
        self.tape = small("kalshi")
        self.digest = tape_digest(self.tape)
        self.candidates = seed_candidates("kalshi")

    def tearDown(self):
        self.dir.cleanup()

    def uploads(self, what: str) -> list[tuple]:
        return [c for c in self.sail.calls if c[0] == "upload" and c[2].startswith(what)]

    def test_batch_equals_single_through_the_box_and_the_tape_goes_once(self):
        first = self.sandbox.replay_batch("lab", self.candidates, self.tape, tape_digest=self.digest, stake=200.0, limits=LIMITS)
        again = self.sandbox.replay_batch("lab", self.candidates, None, tape_digest=self.digest, stake=200.0, limits=LIMITS)
        self.assertEqual(first.result["results"], [single(c, self.tape) for c in self.candidates])
        self.assertEqual(again.result["results"], first.result["results"])
        self.assertEqual(len(self.uploads(TAPE_DIR)), 1)
        self.assertEqual(self.uploads(TAPE_DIR)[0][2], f"{TAPE_DIR}/{self.digest}.json.gz")
        self.assertTrue(first.created)
        self.assertTrue(all(e["egress"] == SEALED for e in self.sail.execs))  # every batch ran sealed
        self.assertTrue(all(d.startswith(RESULT_DIR) for d in self.sail.downloads))
        # the tape the box holds is the canonical JSON, gzipped
        box = self.sandbox.box_of("lab")
        self.assertEqual(gzip.decompress(self.sail.boxes[box]["files"][f"{TAPE_DIR}/{self.digest}.json.gz"]), tape_bytes(self.tape))

    def test_the_cache_survives_a_new_sandbox_and_a_miss_on_the_box_is_answered(self):
        self.sandbox.replay_batch("lab", self.candidates, self.tape, tape_digest=self.digest, stake=200.0, limits=LIMITS)
        reborn = SailSandbox(self.sail, self.root / "state" / "sandbox.json", image_checkpoint="cp_clean_image")
        reborn.replay_batch("lab", self.candidates, None, tape_digest=self.digest, stake=200.0, limits=LIMITS)
        self.assertEqual(len(self.uploads(TAPE_DIR)), 1)
        box = reborn.box_of("lab")
        del self.sail.boxes[box]["files"][f"{TAPE_DIR}/{self.digest}.json.gz"]  # the box's disk lost it
        with self.assertRaises(TapeMissing):
            reborn.replay_batch("lab", self.candidates, None, tape_digest=self.digest, stake=200.0, limits=LIMITS)
        with self.assertRaises(TapeMissing):  # and the state no longer claims it: no exec is spent asking again
            execs = len(self.sail.execs)
            reborn.replay_batch("lab", self.candidates, None, tape_digest=self.digest, stake=200.0, limits=LIMITS)
        self.assertEqual(len(self.sail.execs), execs)

    def test_a_bound_box_is_sealed_before_anything_reaches_it_and_never_terminated(self):
        self.sail.boxes["sb_lab"] = {"status": "sleeping", "egress": ["deb.debian.org"], "files": {}, "name": "ltcm-lab"}
        self.sandbox.bind("lab", "sb_lab")
        run = self.sandbox.replay_batch("lab", self.candidates, self.tape, tape_digest=self.digest, stake=200.0, limits=LIMITS)
        self.assertFalse(run.created)
        names = self.sail.names()
        self.assertNotIn("from_checkpoint", names)
        seal = self.sail.calls.index(("set_egress", "sb_lab", SEALED))
        first_upload = next(i for i, c in enumerate(self.sail.calls) if c[0] == "upload")
        self.assertLess(seal, first_upload)
        self.assertEqual(self.sail.boxes["sb_lab"]["egress"], SEALED)
        self.sandbox.retire("lab")
        self.assertNotIn("terminate", self.sail.names())
        self.assertIsNone(self.sandbox.box_of("lab"))

    def test_a_box_that_is_asleep_after_the_batch_unless_kept_awake(self):
        self.sandbox.replay_batch("lab", self.candidates, self.tape, tape_digest=self.digest, stake=200.0, limits=LIMITS)
        box = self.sandbox.box_of("lab")
        self.assertEqual(self.sail.boxes[box]["status"], "sleeping")
        self.sandbox.replay_batch("lab", self.candidates, None, tape_digest=self.digest, stake=200.0, limits=LIMITS, keep_awake=True)
        self.assertEqual(self.sail.boxes[box]["status"], "running")

    def test_a_sail_failure_is_the_boxes_not_the_strategies(self):
        self.sail.failing["exec"] = RuntimeError("503 from sail")
        with self.assertRaises(SandboxError):
            self.sandbox.replay_batch("lab", self.candidates, self.tape, tape_digest=self.digest, stake=200.0, limits=LIMITS)


# =================================================================================================
# LabBox and the holdout
# =================================================================================================
class LabBoxes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.sail = BatchSail(self.root / "boxes")
        self.sandbox = SailSandbox(self.sail, self.root / "state" / "sandbox.json", image_checkpoint="cp_clean_image")
        self.sail.boxes["sb_lab"] = {"status": "running", "egress": None, "files": {}, "name": "ltcm-lab"}
        self.lab = LabBox.from_config(self.sandbox, {"lab": {"box_id": "sb_lab", "box_key": "lab"}})
        self.tape = small("alpaca")
        self.candidates = seed_candidates("alpaca")

    def tearDown(self):
        self.dir.cleanup()

    def test_evaluate_answers_single_replays_and_uploads_once(self):
        out = self.lab.evaluate(self.candidates, "reg:alpaca", self.tape, stake=200.0, limits=LIMITS)
        self.assertEqual(out, [single(c, self.tape) for c in self.candidates])
        self.lab.evaluate(self.candidates[:2], "reg:alpaca", self.tape, stake=200.0, limits=LIMITS)
        self.assertEqual((self.lab.stats["batches"], self.lab.stats["uploads"], self.lab.stats["misses"]), (2, 1, 1))
        self.assertEqual(self.lab.stats["evaluated"], len(self.candidates) + 2)
        self.assertEqual(self.sandbox.box_of("lab"), "sb_lab")
        self.assertEqual(self.sail.boxes["sb_lab"]["egress"], SEALED)

    def test_a_lost_tape_is_sent_again(self):
        self.lab.evaluate(self.candidates[:1], "reg:alpaca", self.tape, stake=200.0, limits=LIMITS)
        self.sail.boxes["sb_lab"]["files"] = {k: v for k, v in self.sail.boxes["sb_lab"]["files"].items() if not k.startswith(TAPE_DIR)}
        out = self.lab.evaluate(self.candidates[:1], "reg:alpaca", self.tape, stake=200.0, limits=LIMITS)
        self.assertEqual(out, [single(self.candidates[0], self.tape)])
        self.assertEqual(self.lab.stats["uploads"], 2)

    def test_large_batches_are_split(self):
        lab = LabBox(self.sandbox, max_batch=3)
        out = lab.evaluate(self.candidates, "reg:alpaca", self.tape, stake=200.0, limits=LIMITS)
        self.assertEqual([r["id"] for r in out], [c["id"] for c in self.candidates])
        self.assertEqual(lab.stats["batches"], -(-len(self.candidates) // 3))

    def test_a_new_tape_under_an_old_id_gets_its_own_digest(self):
        first = self.lab.digest("alpaca:SPY", self.tape)
        changed = small("alpaca", seed=8)
        self.assertNotEqual(self.lab.digest("alpaca:SPY", changed), first)
        self.assertEqual(self.lab.digest("alpaca:SPY", changed), tape_digest(changed))

    def test_the_digest_is_the_experiment_archive_id(self):
        archive = Archive(self.root / "archive")
        self.assertEqual(archive.put(self.tape), tape_digest(self.tape))

    def test_a_holdout_tape_is_refused_before_anything_is_sent(self):
        sealed = dated_tape("2026-01-05", 2)
        with self.assertRaises(TapeRefused):
            self.lab.evaluate(self.candidates, "sealed", sealed, stake=200.0, limits=LIMITS)
        self.assertEqual(self.sail.calls, [])

    def test_disabled_in_config(self):
        self.assertIsNone(LabBox.from_config(self.sandbox, {"lab": {"enabled": False}}))


class Holdout(unittest.TestCase):
    WINDOW = ("2025-11-14", "2026-05-15")

    def test_the_default_window_is_deep_replays(self):
        from league.deep_replay import HOLDOUT

        self.assertEqual(HOLDOUT, self.WINDOW)
        self.assertIsNotNone(holdout_problem(dated_tape("2026-02-01", 1)))

    def test_inside_straddling_and_warmup_into_it_are_refused(self):
        self.assertIsNotNone(holdout_problem(dated_tape("2025-12-01", 2), self.WINDOW))  # inside
        self.assertIsNotNone(holdout_problem(dated_tape("2025-11-13", 2), self.WINDOW))  # runs into its first day
        self.assertIsNotNone(holdout_problem(dated_tape("2026-05-14", 3), self.WINDOW))  # runs out of its last day
        spanning = dated_tape("2025-10-01", 1)
        spanning["steps"] += dated_tape("2026-06-01", 1)["steps"]  # nothing inside, but the tape spans it
        self.assertIsNotNone(holdout_problem(spanning, self.WINDOW))
        # a live daily tape that starts after the holdout but whose warmup bars reach back into it
        self.assertIsNotNone(holdout_problem(dated_tape("2026-06-01", 2, warmup_from="2026-03-02"), self.WINDOW))
        observed = dated_tape("2026-06-01", 1)
        observed["observed_bars"] = {"BTC/USD": [{"t": "2026-01-01T00:00:00Z", "c": 1.0}]}
        self.assertIsNotNone(holdout_problem(observed, self.WINDOW))
        fed = dated_tape("2026-06-01", 1)
        fed["feeds"] = {"vol": {"BTC": [{"t": "2026-04-01T00:00:00Z", "v": 1.0}]}}
        self.assertIsNotNone(holdout_problem(fed, self.WINDOW))

    def test_development_tapes_before_it_and_live_tapes_after_it_pass(self):
        self.assertIsNone(holdout_problem(dated_tape("2025-11-10", 4, warmup_from="2025-06-01"), self.WINDOW))
        self.assertIsNone(holdout_problem(dated_tape("2026-05-15", 3), self.WINDOW))
        self.assertIsNone(holdout_problem(small("kalshi"), self.WINDOW))
        dev = dated_tape("2025-11-10", 4)  # a deep_replay development tape: its window ends where the holdout begins
        dev["source"] = {"store": "history", "window": ["2025-02-24", "2025-11-14"]}
        self.assertIsNone(holdout_problem(dev, self.WINDOW))
        dev["source"]["window"] = ["2025-06-01", "2025-12-01"]  # a window that claims holdout days is refused
        self.assertIsNotNone(holdout_problem(dev, self.WINDOW))

    def test_a_tape_with_no_dates_is_refused(self):
        self.assertIsNotNone(holdout_problem({"venue": "alpaca", "steps": []}, self.WINDOW))


if __name__ == "__main__":
    unittest.main()
