"""THE FORWARD LADDER (evidence v3, `league/live/ladder.py`): its table, its two tests and their golden vectors, its
checkpoints and the judgement at one, the store's checkpoint and answer state, its cohort lifecycle and the window
hold, the session's end night by night (the checkpoints, the latch, the answer session, the wait, recording and
binding), the same through the swarm's own store, the swarm's side of a promotion and a demotion, the daily lines (the
rule before the checkpoints), and its public-safe counts."""

from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league.constitution import CONSTITUTION, options_money_problems
from league.live import ladder as L
from league.live.observe import ObserveStore

try:
    import numpy as np

    HAVE = True
except ImportError:  # pragma: no cover - the House and CI carry numpy
    HAVE = False

EVALUATOR = "bundle-1:fills-1:exec-1"
CODE = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {"hold": 3}

def decide(ctx):
    return []
'''


def sessions(first: str, n: int) -> list[str]:
    return L.sessions_between(first, (dt.date.fromisoformat(first) + dt.timedelta(days=3 * n)).isoformat())[:n]


def body(pnl: float, *, delta: float = 0.0, spot: float = 500.0, move: float = 0.0, qty: int = 1, fees: float = 1.3,
         exit_spot: bool = True) -> dict:
    """An engine trade row's body: two legs whose context deltas differ by `delta` / 100 a lot."""
    out = {"qty": qty, "fees": fees, "type": "debit_vertical",
           "legs": [{"side": "long", "ratio": 1, "right": "C"}, {"side": "short", "ratio": 1, "right": "C"}],
           "context": {"spot": spot, "delta": [0.3 + delta / 100.0, 0.3]}}
    if exit_spot:
        out["exit_spot"] = spot + move
    return out


def record(days: list[str], returns: list[list[float]], *, loss: float = 100.0, delta: float = 0.0,
           moves: dict[str, float] | None = None) -> list[dict]:
    """Ledger rows: on each day, one close per return (pnl = return x loss, plus delta x that day's move)."""
    rows, seq = [], 0
    for day, rs in zip(days, returns):
        move = (moves or {}).get(day, 0.0)
        for r in rs:
            pnl = r * loss + delta * move
            rows.append({"seq": seq, "trade_id": str(seq), "pnl": pnl, "max_loss": loss, "exit_day": day,
                         "body": body(pnl, delta=delta, move=move)})
            seq += 1
    return rows


def rules(**changes) -> L.Rules:
    base = L.Rules.from_constitution()
    return L.Rules(**{**base.__dict__, **changes})


def ladders_own_gate(case: unittest.TestCase) -> None:
    """THE LADDER'S OWN MODE for a test class that reads the swarm's real store: evidence v3's own gate, sealed looks
    off (`gate.SEALED_LOOKS` False), where the pre-filter reads for the ladder and THE LADDER'S BELT can let a promotion
    through. As shipped (THE FAST LANE, release F1, Oct 3, 2026) the sealed look is the route to Probe and the belt
    refuses every program (`bands.BELT_LOOK_ROUTE`): `TheFastLane` below holds that."""
    switch = patch("league.swarm.gate.SEALED_LOOKS", False)
    switch.start()
    case.addCleanup(switch.stop)


def pattern(n: int, *, per_day: int = 2, shift: int = 8, scale: float = 20.0) -> list[list[float]]:
    """Invented returns, the same every run: day d's j-th close returns ((37 d + 11 j) mod 23 - `shift`) / `scale` (a
    mean of (11 - shift) / scale a close, with losing days)."""
    return [[((37 * d + 11 * j) % 23 - shift) / scale for j in range(per_day)] for d in range(n)]


def market(days: list[str], base: float, step: float) -> dict[str, float]:
    """An invented underlying's move each day: `base` plus a five-day cycle of -2, 0, 2, -1, 1 steps."""
    return {d: base + ((7 * i) % 5 - 2) * step for i, d in enumerate(days)}


# ================================================================================================== the constitution
class TheTable(unittest.TestCase):
    def test_the_ladder_block_reads_as_the_plan_states_it(self):
        r = L.Rules.from_constitution()
        self.assertEqual((r.min_sessions, r.min_closes, r.confidence, r.windows, r.windows_positive, r.fdr_q, r.fdr_days,
                          r.max_sessions), (20, 30, 0.95, 4, 3, 0.10, 90, 60))
        self.assertEqual((r.checkpoints, r.alphas, r.prefilter_p, r.answer_sessions, r.draws),
                         ((40, 60), (0.004, 0.05), 0.02, 5, 10000))
        self.assertEqual((r.alpha(40), r.alpha(60)), (0.004, 0.05), "each checkpoint has its own nominal level")
        for unknown in (20, 41, 0, True):
            with self.assertRaises(ValueError):
                r.alpha(unknown)
        self.assertIsInstance(r.binding, bool)
        self.assertEqual(options_money_problems(), [])

    def test_a_row_may_only_tighten(self):
        # The window is exactly the last checkpoint (60 sessions: 40 was allowed before the checkpoints fixed it) and
        # the two tests draw exactly 10,000 resamples (2,000 before them): more is another resample stream and a lower
        # floor on the p-values, so another rule than the one confirmed, never a tightening.
        for key, value in (("min_sessions", 19), ("min_closes", 29), ("confidence", "0.94"), ("draws", 1999),
                           ("draws", 9999), ("draws", 10001), ("draws", 100000), ("draws", 100001), ("draws", 10000.0),
                           ("windows_positive", 2), ("fdr_q", "0.11"), ("fdr_days", 89),
                           ("max_sessions", 61), ("max_sessions", 59), ("max_sessions", 40), ("prefilter_p", "0.021"),
                           ("prefilter_p", "-0.01"), ("answer_sessions", 6), ("answer_sessions", 0),
                           ("answer_sessions", 3.0), ("drift_known_share", "0.89"), ("demote_sessions", 21),
                           ("demote_confidence", "0.79"), ("windows", 5), ("min_closes", 30.0)):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["ladder"][key] = value
            self.assertTrue(any(f"ladder.{key}" in p for p in options_money_problems(changed)), (key, value))
            with self.assertRaises(ValueError):
                L.Rules.from_constitution(changed)
        for key, value in (("min_sessions", 40), ("min_closes", 60), ("confidence", "0.99"), ("fdr_q", "0.05"),
                           ("fdr_days", 180), ("draws", 10000), ("windows_positive", 4), ("demote_sessions", 10),
                           ("prefilter_p", "0.01"), ("answer_sessions", 1)):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["ladder"][key] = value
            self.assertEqual(options_money_problems(changed), [], (key, value))

    def test_the_checkpoints_are_fixed_and_an_alpha_may_only_go_down(self):
        def problems(**changes):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["ladder"].update(changes)
            out = options_money_problems(changed)
            if out:
                with self.assertRaises(ValueError):
                    L.Rules.from_constitution(changed)
            return out

        for changes, why in (
                ({"checkpoints": [60, 40]}, "checkpoints must increase"),
                ({"checkpoints": [40, 40]}, "checkpoints must increase"),
                ({"checkpoints": [40, 50]}, "checkpoints must end at ladder.max_sessions"),
                ({"checkpoints": [40]}, "checkpoints must end at ladder.max_sessions"),
                ({"checkpoints": [30, 60]}, "checkpoints is exactly [40, 60]"),
                ({"checkpoints": [20, 40, 60], "alphas": ["0.001", "0.004", "0.05"]}, "checkpoints is exactly [40, 60]"),
                ({"checkpoints": [40.0, 60]}, "checkpoints is a list of whole session counts"),
                ({"checkpoints": [True, 60]}, "checkpoints is a list of whole session counts"),
                ({"checkpoints": "40,60"}, "checkpoints is a list of whole session counts"),
                ({"checkpoints": []}, "checkpoints is a list of whole session counts"),
                ({"alphas": ["0.004"]}, "alphas must hold one level for each of ladder.checkpoints"),
                ({"alphas": ["0.004", "0.05", "0.05"]}, "alphas must hold one level for each of ladder.checkpoints"),
                ({"checkpoints": [40], "alphas": ["0.004"]}, "alphas must hold one level for each of ladder.checkpoints"),
                ({"alphas": ["0.0041", "0.05"]}, "alphas: '0.0041' is outside [0, 0.004]"),
                ({"alphas": ["0.004", "0.051"]}, "alphas: '0.051' is outside [0, 0.05]"),
                ({"alphas": ["0.05", "0.004"]}, "alphas: '0.05' is outside [0, 0.004]"),
                ({"alphas": ["-0.001", "0.05"]}, "alphas: '-0.001' is outside [0, 0.004]"),
                ({"alphas": ["0.004", "x"]}, "alphas: 'x' is not a number"),
                ({"alphas": ["0.004", "nan"]}, "alphas: 'nan' is not a number"),
                ({"alphas": [True, "0.05"]}, "alphas: True is not a number"),
                ({"alphas": "0.004"}, "alphas is a list of levels"),
                ({"alphas": []}, "alphas is a list of levels")):
            self.assertTrue(any(why in p for p in problems(**changes)), (changes, problems(**changes)))
        for key in ("checkpoints", "alphas", "prefilter_p", "answer_sessions"):
            changed = copy.deepcopy(CONSTITUTION)
            del changed["options_money"]["ladder"][key]
            self.assertTrue(any(f"ladder.{key}" in p for p in options_money_problems(changed)), key)
        for alphas in (["0.004", "0.05"], ["0.002", "0.01"], [0.004, 0.05], ["0", "0"]):
            self.assertEqual(problems(alphas=alphas), [], alphas)

    def test_binding_is_a_json_boolean_and_the_window_holds_the_record(self):
        for value in (1, "true", None):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["ladder"]["binding"] = value
            self.assertTrue(any("ladder.binding" in p for p in options_money_problems(changed)), value)
        changed = copy.deepcopy(CONSTITUTION)
        changed["options_money"]["ladder"].update(min_sessions=40, max_sessions=30)
        self.assertTrue(any("max_sessions" in p for p in options_money_problems(changed)))
        changed = copy.deepcopy(CONSTITUTION)
        del changed["options_money"]["ladder"]
        self.assertTrue(options_money_problems(changed))

    def test_sized_waits_for_twenty_real_trades_and_five_sessions(self):
        sized = CONSTITUTION["options_money"]["sized"]
        self.assertEqual((sized["min_probe_real_trades"], sized["min_probe_sessions"]), (20, 5))


# ================================================================================================== the lines
@unittest.skipUnless(HAVE, "numpy not installed")
class TheLines(unittest.TestCase):
    def closes(self, returns_by_day: list[list[float]], first="2026-10-05", r_adj=None) -> list[L.Close]:
        out = []
        for day, rs in zip(sessions(first, len(returns_by_day)), returns_by_day):
            out += [L.Close(day=day, r=r, r_adj=r if r_adj is None else r_adj, unit=50.0) for r in rs]
        return out

    def test_the_bootstrap_is_deterministic_and_bounds_a_positive_record(self):
        rng = np.random.default_rng(1)
        good = self.closes([[0.3 + 0.2 * float(rng.standard_normal()) for _ in range(2)] for _ in range(25)])
        a = L.bootstrap(good, confidence=0.95, draws=2000, seed="s")
        b = L.bootstrap(good, confidence=0.95, draws=2000, seed="s")
        self.assertEqual(a, b)
        self.assertGreater(a["lcb"], 0)
        self.assertLess(a["p"], 0.05)
        self.assertEqual(a["days"], 25)

    def test_a_mean_at_or_below_zero_or_one_day_is_p_one_and_no_bound(self):
        flat = self.closes([[0.1, -0.1]] * 25)
        self.assertEqual((L.bootstrap(flat, confidence=0.95, draws=2000, seed="s")["p"],
                          L.bootstrap(flat, confidence=0.95, draws=2000, seed="s")["lcb"]), (1.0, None))
        one_day = [L.Close(day="2026-10-05", r=0.5, r_adj=0.5, unit=1.0)] * 40
        out = L.bootstrap(one_day, confidence=0.95, draws=2000, seed="s")
        self.assertEqual((out["p"], out["lcb"]), (1.0, None), "one block has no spread: no bound")

    def test_a_noisy_null_rarely_bounds_above_zero(self):
        rng = np.random.default_rng(7)
        passed = 0
        for k in range(200):
            null = self.closes([[0.5 * float(rng.standard_normal()) for _ in range(2)] for _ in range(25)])
            passed += (L.bootstrap(null, confidence=0.95, draws=2000, seed=str(k))["lcb"] or -1) > 0
        self.assertLess(passed, 25, "about 5% of nulls, not more")

    def test_windows_split_the_sessions_equally(self):
        days = sessions("2026-10-05", 20)
        closes = [L.Close(day=d, r=1.0 if i < 15 else -5.0, r_adj=None, unit=None) for i, d in enumerate(days)]
        sums = L.windows(closes, days, 4)
        self.assertEqual(sums, [5.0, 5.0, 5.0, -25.0])
        self.assertEqual(L.windows([], days, 4), [0.0, 0.0, 0.0, 0.0])
        self.assertEqual(len(L.windows(closes, days[:6], 4)), 4)

    def test_benjamini_hochberg_steps_up(self):
        ps = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
        self.assertEqual(L.benjamini_hochberg(ps, 0.05), (0.008, 10))
        self.assertEqual(L.benjamini_hochberg(ps, 0.10), (0.06, 10), "the step-up rejects past ranks that failed")
        self.assertEqual(L.benjamini_hochberg([0.2, 0.5], 0.10), (None, 2))
        cut, m = L.benjamini_hochberg([0.004] + [1.0] * 30, 0.10)
        self.assertEqual((cut, m), (None, 31), "entrants without a record (p = 1) raise the bar")

    def test_the_entry_delta_and_the_drift_charge(self):
        b = body(0.0, delta=20.0, spot=500.0, move=4.0)
        self.assertAlmostEqual(L.entry_delta(b), 20.0)
        self.assertAlmostEqual(L.drift_usd(b), 80.0)
        short = dict(b, legs=[{"side": "short", "ratio": 1}, {"side": "long", "ratio": 1}], qty=2)
        self.assertAlmostEqual(L.entry_delta(short), -40.0)
        for broken in (dict(b, exit_spot=None), dict(b, context={"spot": 500.0, "delta": [0.5]}),
                       dict(b, context={"spot": 500.0, "delta": [None, 0.3]}), dict(b, legs=[{"side": "?", "ratio": 1}] * 2),
                       dict(b, qty=0)):
            self.assertIsNone(L.drift_usd(broken))

    def test_the_drift_control_fails_drift_and_keeps_a_non_directional_edge(self):
        days = sessions("2026-10-05", 30)
        moves = {d: 3.0 if i % 2 else 1.0 for i, d in enumerate(days)}             # a market that only rises
        drift = [L.close_of(r) for r in record(days, [[-0.03]] * 30, delta=20.0, moves=moves)]
        self.assertGreater(sum(c.r for c in drift), 0, "raw P&L is positive: the market's drift")
        self.assertFalse(L.drift_line(drift, 0.9)["passed"])
        premium = [L.close_of(r) for r in record(days, [[0.05]] * 30, delta=0.0, moves=moves)]
        self.assertTrue(L.drift_line(premium, 0.9)["passed"])
        unknown = [L.Close(day=c.day, r=c.r, r_adj=None if i % 5 == 0 else c.r_adj, unit=None)
                   for i, c in enumerate(premium)]
        line = L.drift_line(unknown, 0.9)
        self.assertEqual((line["passed"], line["share"]), (False, 0.8), "figures known for under 90% of closes fail it")


# ================================================================================================== the two tests
#: GOLDEN VECTORS. Invented day sums (name, `s`: each session day's summed returns, `c`: its closes) and the p-value of
#: each test on them at 10,000 draws, seeds "vector:<name>:r" (tilted) and "vector:<name>:perc" (percentile), as the
#: reference implementation the rule was developed on (kept outside the repo) returned them, to the last digit and the
#: same under Python 3.11 and 3.14. Where the tilted column says `WEIGHTS` that implementation raised (the tilt's
#: weights overflow): the ladder's p-value there is 1, said in the figures.
FLOOR = 9.999000099990002e-05          # 1 / 10,001: no resampled mean on the wrong side
WEIGHTS = "weights"
VECTORS = (
    # a skewed premium-like record: small wins, two large losing days
    ("premium", [0.12, 0.24, 0.36, 0.12, 0.24, 0.36, 0.12, -0.66, 0.36, 0.12, 0.24, 0.36, 0.12, 0.24, 0.36, 0.12, 0.24,
                 0.36, 0.12, 0.24, 0.36, -0.78, 0.24, 0.36, 0.12, 0.24, 0.36, 0.12, 0.24, 0.36], [1, 2, 3] * 10,
     0.0055, 0.0009),
    ("plain", [0.31, -0.18, 0.05, 0.42, -0.27, 0.11, 0.2, -0.09, 0.36, -0.4, 0.15, 0.08, -0.03, 0.27, 0.19, -0.22, 0.33,
               0.02, -0.11, 0.24, 0.4, -0.35, 0.09, 0.17, -0.06, 0.29, 0.13, -0.19, 0.21, 0.07, -0.14, 0.38, 0.03, 0.16,
               -0.08, 0.26, 0.1, -0.31, 0.22, 0.18], [2, 1, 3, 2, 2, 1, 2, 3, 1, 2] * 4, 0.0179, 0.0147),
    ("weak", [0.2, -0.25, 0.1, 0.3, -0.35, 0.05, 0.15, -0.1, 0.25, -0.2, 0.1, 0.05, -0.15, 0.2, 0.1, -0.05, 0.15, -0.1,
              0.05, 0.1], [1] * 20, 0.2321, 0.2149),
    # no losing day: the tilted test cannot be run (p = 1), whatever the percentile test says
    ("no_losing_day", [0.05, 0.3, 0.12, 0.2, 0.08, 0.25, 0.1, 0.15], [1, 2, 1, 2, 1, 2, 1, 1], 1.0, FLOOR),
    ("one_tiny_loss", [0.6, 0.5, 0.7, -0.01, 0.55, 0.65, 0.45, 0.6], [2] * 8, FLOOR, FLOOR),
    # every losing day tiny against the largest day: the tilt's weights are not finite
    ("weights", [0.8, 0.5, 0.004, -0.00001, 0.3], [1, 1, 1, 1, 1], WEIGHTS, 0.0001),
    ("weights_many", [1.5, 0.9, 0.002, -0.000004, 1.1, 0.7], [3, 2, 1, 1, 2, 2], WEIGHTS, 0.0002),
    # fewer than two session days, and a mean at or below zero: p = 1 in both tests
    ("one_day", [0.5], [3], 1.0, 1.0),
    ("no_day", [], [], 1.0, 1.0),
    ("mean_zero", [0.5, -0.5], [1, 1], 1.0, 1.0),
    ("mean_negative", [0.1, -0.3, 0.05, -0.02], [1, 2, 1, 1], 1.0, 1.0),
    ("two_days", [0.4, -0.1], [2, 1], 0.353, 0.2476),
)
#: Why each vector's tilted p-value is 1 without a resample (None: the days were resampled).
VECTOR_TILTS = {"no_losing_day": L.TILT_NO_LOSS, "weights": L.TILT_WEIGHTS, "weights_many": L.TILT_WEIGHTS,
                "one_day": L.TILT_DAYS, "no_day": L.TILT_DAYS, "mean_zero": L.TILT_MEAN, "mean_negative": L.TILT_MEAN}


@unittest.skipUnless(HAVE, "numpy not installed")
class TheTwoTests(unittest.TestCase):
    def blocks(self, s, c):
        return np.array(s, dtype=float), np.array(c, dtype=float)

    def test_the_golden_vectors_to_the_last_digit(self):
        import warnings

        self.assertEqual(FLOOR, 1.0 / 10001)
        for name, s, c, tilted, perc in VECTORS:
            s, c = self.blocks(s, c)
            with warnings.catch_warnings():
                warnings.simplefilter("error", RuntimeWarning)   # a tilt that overflows is read, never warned of
                got, why = L.tilted(s, c, draws=10000, seed=f"vector:{name}:r")
                again = L.tilted_p(s, c, draws=10000, seed=f"vector:{name}:r")
                share = L.percentile_p(s, c, draws=10000, seed=f"vector:{name}:perc")
            self.assertEqual(got, 1.0 if tilted == WEIGHTS else tilted, name)
            self.assertEqual(again, got, name)
            self.assertEqual(why, VECTOR_TILTS.get(name), name)
            self.assertEqual(share, perc, name)

    def test_a_tilt_whose_weights_are_not_finite_is_p_one_and_says_so(self):
        for name in ("weights", "weights_many"):
            [(s, c)] = [self.blocks(v[1], v[2]) for v in VECTORS if v[0] == name]
            self.assertEqual(L.tilted(s, c, draws=10000, seed="any"), (1.0, L.TILT_WEIGHTS), name)
            self.assertLess(L.percentile_p(s, c, draws=10000, seed="any"), 0.05, "the percentile test alone would pass it")

    def test_the_guards_are_p_one_in_their_order(self):
        s, c = self.blocks([0.5], [3])
        self.assertEqual(L.tilted(s, c, draws=100, seed="s"), (1.0, L.TILT_DAYS))
        self.assertEqual(L.percentile(s, c, draws=100, seed="s", confidence=0.95), (1.0, None))
        s, c = self.blocks([0.5, -0.5], [1, 1])
        self.assertEqual(L.tilted(s, c, draws=100, seed="s"), (1.0, L.TILT_MEAN), "a mean of exactly zero")
        self.assertEqual(L.percentile(s, c, draws=100, seed="s", confidence=0.95), (1.0, None))
        s, c = self.blocks([-0.1, -0.2, -0.3], [1, 1, 1])
        self.assertEqual(L.tilted(s, c, draws=100, seed="s"), (1.0, L.TILT_MEAN), "the mean is read before the losing days")
        s, c = self.blocks([0.1, 0.2, 0.0], [1, 1, 1])
        self.assertEqual(L.tilted(s, c, draws=100, seed="s"), (1.0, L.TILT_NO_LOSS), "a flat day is no losing day")

    def test_each_is_deterministic_for_a_seed_and_floored(self):
        [(s, c)] = [self.blocks(v[1], v[2]) for v in VECTORS if v[0] == "plain"]
        self.assertEqual(L.tilted_p(s, c, draws=10000, seed="a"), L.tilted_p(s, c, draws=10000, seed="a"))
        self.assertNotEqual(L.tilted_p(s, c, draws=10000, seed="a"), L.tilted_p(s, c, draws=10000, seed="b"))
        self.assertEqual(L.percentile_p(s, c, draws=10000, seed="a"), L.percentile_p(s, c, draws=10000, seed="a"))
        [(s, c)] = [self.blocks(v[1], v[2]) for v in VECTORS if v[0] == "one_tiny_loss"]
        for draws in (200, 10000):
            self.assertEqual(L.tilted_p(s, c, draws=draws, seed="a"), 1.0 / (draws + 1))
            self.assertEqual(L.percentile_p(s, c, draws=draws, seed="a"), 1.0 / (draws + 1))

    def test_the_percentile_line_is_the_plans_bound(self):
        self.assertEqual(L.percentile_line(0.95), 0.05, "exactly 0.05 at the plan's 95%")
        self.assertEqual(L.percentile_line(0.99), 0.01)
        for name, s, c, _, perc in VECTORS:
            s, c = self.blocks(s, c)
            p, lcb = L.percentile(s, c, draws=10000, seed=f"vector:{name}:perc", confidence=0.95)
            self.assertEqual(p, perc, name)
            self.assertEqual(lcb is not None and lcb > 0, p <= L.percentile_line(0.95), name)

    def test_the_blocks_are_the_session_days_sums_in_day_order(self):
        closes = [L.Close(day=day, r=r, r_adj=r_adj, unit=None) for day, r, r_adj in (
            ("2026-10-06", 0.2, 0.1), ("2026-10-05", -0.1, None), ("2026-10-06", 0.3, None), ("2026-10-07", 0.4, None))]
        s, c = L.day_sums(closes)
        self.assertEqual((s.tolist(), c.tolist()), ([-0.1, 0.5, 0.4], [1.0, 2.0, 1.0]))
        s, c = L.day_sums(closes, adjusted=True)
        self.assertEqual((s.tolist(), c.tolist()), ([0.1], [1.0]),
                         "the closes whose figure is known; a day with none is no block")
        s, c = L.day_sums([])
        self.assertEqual((len(s), len(c)), (0, 0))

    def test_the_bootstrap_of_a_record_is_the_percentile_test_on_its_blocks(self):
        closes = []
        for day, rs in zip(sessions("2026-10-05", 40), pattern(40)):
            closes += [L.Close(day=day, r=r, r_adj=r, unit=None) for r in rs]
        s, c = L.day_sums(closes)
        out = L.bootstrap(closes, confidence=0.95, draws=10000, seed="s")
        self.assertEqual((out["p"], out["lcb"]), L.percentile(s, c, draws=10000, seed="s", confidence=0.95))
        self.assertEqual((out["mean"], out["days"], out["draws"]), (float(s.sum() / c.sum()), 40, 10000))


# ================================================================================================== the checkpoints
class TheCheckpoints(unittest.TestCase):
    def due(self, practised, calendar, judged=()):
        return L.checkpoint_due(practised, calendar, judged, rules())

    def test_the_first_falls_due_when_its_sessions_are_practised(self):
        self.assertIsNone(self.due(39, 39))
        self.assertEqual(self.due(40, 40), 40)
        self.assertEqual(self.due(40, 52), 40, "sessions practised, not calendar sessions")
        self.assertIsNone(self.due(39, 52))
        self.assertEqual(self.due(47, 47), 40, "a missed night: judged at the first session's end after it was due")

    def test_each_is_judged_at_most_once(self):
        self.assertIsNone(self.due(40, 40, [40]))
        self.assertIsNone(self.due(59, 59, [40]))
        self.assertEqual(self.due(60, 60, [40]), 60)
        self.assertIsNone(self.due(60, 60, [40, 60]))
        self.assertIsNone(self.due(60, 61, [40, 60]))

    def test_the_last_falls_due_when_the_window_ends_whatever_was_practised(self):
        self.assertEqual(self.due(12, 60), 60)
        self.assertEqual(self.due(0, 60), 60)
        self.assertEqual(self.due(None, 60), 60, "a record that began before its cohort is judged (ineligible) there too")
        self.assertIsNone(self.due(None, 59))
        self.assertEqual(self.due(60, 61, [40]), 60, "a missed last night: the first session's end after it")

    def test_a_first_checkpoint_due_only_at_the_windows_end_is_judged_once_at_the_last_alpha(self):
        self.assertEqual(self.due(40, 60), 60)
        self.assertEqual(self.due(55, 60), 60)
        self.assertIsNone(self.due(55, 60, [60]), "no earlier checkpoint is judged after the last")
        self.assertIsNone(self.due(55, 61, [60]))
        self.assertEqual(rules().alpha(60), 0.05)


# ================================================================================================== judge at a checkpoint
def cases() -> dict[str, tuple[list[str], list[dict], int]]:
    """Invented practice records in the ledger's shape: name -> (its session days, its rows, the checkpoint judged)."""
    d40, d60 = sessions("2026-10-05", 40), sessions("2026-10-05", 60)
    return {
        "edge": (d40, record(d40, pattern(40)), 40),                                   # an edge that is not its delta's
        "drift": (d40, record(d40, pattern(40, shift=12), delta=20.0, moves=market(d40, 1.0, 0.75)), 40),  # drift alone
        "neutral": (d40, record(d40, pattern(40), delta=20.0, moves=market(d40, 0.0, 0.5)), 40),  # an edge beside a delta
        "slow": (d60, record(d60, pattern(60, shift=10)), 60),                         # a smaller edge over the window
        "fading": (d40, record(d40, pattern(20, shift=3) + pattern(20, shift=13)), 40),  # an edge gone in its second half
    }


#: The reference implementation's own checkpoint figures on those records, base seed "vector:judge:<name>": (the
#: tilted p-value on the returns, the same on the drift-adjusted returns, the percentile p-value, the positive
#: sub-windows of four), to the last digit, the same under Python 3.11 and 3.14.
JUDGED = {"edge": (FLOOR, FLOOR, FLOOR, 4), "drift": (0.0018, 1.0, 0.002, 4), "neutral": (0.0001, FLOOR, 0.0002, 4),
          "slow": (0.0083, 0.0086, 0.0075, 4), "fading": (0.0005, 0.0012, 0.0017, 2)}


@unittest.skipUnless(HAVE, "numpy not installed")
class TheCheckpointJudgement(unittest.TestCase):
    def cohort(self, first="2026-10-05"):
        return {"family": "fam", "version": 1, "first_day": first,
                "snapshot": {"run_sha": "sha-1", "practice_evaluator": EVALUATOR}}

    def judged(self, rows, days, checkpoint, **kw):
        return L.judge(self.cohort(days[0]), {"first_day": days[0], "sessions": len(days)}, rows, through=days[-1],
                       rules=kw.pop("rules", None) or rules(), checkpoint=checkpoint, **kw)

    def test_the_reference_figures_on_invented_records(self):
        lines = {"edge": (True, True, True, True), "drift": (True, True, True, False), "neutral": (True, True, True, True),
                 "slow": (True, True, True, True), "fading": (True, True, False, True)}
        for name, (days, rows, checkpoint) in cases().items():
            out = self.judged(rows, days, checkpoint, seed=f"vector:judge:{name}")
            self.assertEqual((out["p"], out["p_adj"], out["perc_p"], out["windows_positive"]), JUDGED[name], name)
            self.assertEqual(tuple(out["lines"][k] for k in ("record", "bound", "windows", "drift")), lines[name], name)
            self.assertEqual((out["checkpoint"], out["alpha"], out["draws"], out["full"]),
                             (checkpoint, rules().alpha(checkpoint), 10000, True), name)
            self.assertEqual(out["drift"]["p"], out["p_adj"])
            self.assertEqual(json.loads(json.dumps(out)), out, "a receipt's figures are plain JSON")

    def test_each_checkpoint_judges_at_its_own_alpha(self):
        days, rows, _ = cases()["slow"]
        first, last = (self.judged(rows, days, k, seed="vector:judge:slow") for k in (40, 60))
        self.assertEqual((first["p"], first["p_adj"]), (last["p"], last["p_adj"]), "the same record, the same seed")
        self.assertEqual((first["alpha"], last["alpha"]), (0.004, 0.05))
        self.assertEqual((first["lines"]["bound"], first["lines"]["drift"]), (False, False), "0.0083 is over 0.004")
        self.assertEqual((last["lines"]["bound"], last["lines"]["drift"]), (True, True), "and at or under 0.05")
        for unknown in (20, 41, 0):
            with self.assertRaises(ValueError):
                self.judged(rows, days, unknown)

    def test_the_house_seeds_from_the_inputs_hash_and_the_benchmark_from_its_own(self):
        days, rows, _ = cases()["slow"]
        closes = [L.close_of(r) for r in rows]
        s, c = L.day_sums(closes)
        adj = L.day_sums(closes, adjusted=True)
        for seed in (None, "world:0:7:60"):
            out = self.judged(rows, days, 60, seed=seed)
            base = out["inputs"] if seed is None else seed
            self.assertEqual(out["p"], L.tilted_p(s, c, draws=10000, seed=base + ":r"))
            self.assertEqual(out["p_adj"], L.tilted_p(*adj, draws=10000, seed=base + ":adj"))
            self.assertEqual((out["perc_p"], out["lcb"]),
                             L.percentile(s, c, draws=10000, seed=base + ":perc", confidence=0.95))
        self.assertEqual(self.judged(rows, days, 60), self.judged(rows, days, 60), "deterministic")

    def test_the_inputs_hash_moves_with_the_checkpoint_and_with_any_close(self):
        days, rows, _ = cases()["slow"]
        a, b = self.judged(rows, days, 40), self.judged(rows, days, 60)
        self.assertNotEqual(a["inputs"], b["inputs"])
        rows[3] = dict(rows[3], pnl=rows[3]["pnl"] + 0.01)
        self.assertNotEqual(self.judged(rows, days, 60)["inputs"], b["inputs"])
        self.assertEqual(self.judged(rows, days, 60, seed="another")["inputs"], self.judged(rows, days, 60)["inputs"],
                         "the seed's base is not an input")

    def test_a_record_that_is_not_full_resamples_nothing(self):
        days = sessions("2026-10-05", 19)
        out = self.judged(record(days, pattern(19)), days, 40)
        self.assertEqual((out["full"], out["p"], out["p_adj"], out["perc_p"], out["lcb"], out["draws"]),
                         (False, 1.0, 1.0, 1.0, None, 0))
        self.assertEqual(out["tilt"], {"raw": L.TILT_RECORD, "adjusted": L.TILT_RECORD})
        self.assertEqual((out["lines"]["record"], out["lines"]["bound"], out["lines"]["drift"]), (False, False, False))
        self.assertEqual((out["closes"], out["per_session"][days[0]]), (38, 2))
        days = sessions("2026-10-05", 40)
        few = self.judged(record(days, [[0.2]] * 29 + [[]] * 11), days, 40)
        self.assertEqual((few["full"], few["closes"], few["p"]), (False, 29, 1.0), "30 program closes, not 29")
        old = L.judge(self.cohort(days[1]), {"first_day": days[0], "sessions": 40}, record(days, pattern(40)),
                      through=days[-1], rules=rules(), checkpoint=40)
        self.assertEqual((old["eligible"], old["sessions"], old["full"], old["p"]), (False, None, False, 1.0),
                         "a practice row older than its cohort is ineligible")

    def test_the_drift_control_runs_on_the_known_closes_at_ninety_percent(self):
        days, rows, _ = cases()["neutral"]

        def unknown(n):
            out = [dict(r, body=dict(r["body"])) for r in rows]
            for r in out[:n]:
                del r["body"]["exit_spot"]
            return out

        at = self.judged(unknown(8), days, 40, seed="s")
        known = [c for c in (L.close_of(r) for r in unknown(8)) if c.r_adj is not None]
        self.assertEqual((at["drift"]["known"], at["drift"]["share"], at["tilt"]["adjusted"]), (72, 0.9, None))
        self.assertEqual(at["p_adj"], L.tilted_p(*L.day_sums(known, adjusted=True), draws=10000, seed="s:adj"))
        self.assertTrue(at["lines"]["drift"])
        under = self.judged(unknown(9), days, 40, seed="s")
        self.assertEqual((under["drift"]["known"], under["p_adj"], under["tilt"]["adjusted"], under["lines"]["drift"]),
                         (71, 1.0, L.TILT_UNKNOWN, False), "figures known for under 90% of its closes: p = 1")
        self.assertEqual(under["p"], at["p"], "the returns' own test does not read the drift figures")

    def test_drift_alone_fails_the_drift_line_and_only_it(self):
        days, rows, _ = cases()["drift"]
        out = self.judged(rows, days, 40, seed="vector:judge:drift")
        self.assertGreater(out["mean"], 0, "raw P&L is positive: the market's drift")
        self.assertLess(out["drift"]["mean"], 0)
        self.assertEqual((out["p_adj"], out["tilt"]), (1.0, {"raw": None, "adjusted": L.TILT_MEAN}))
        self.assertEqual(out["lines"], {"record": True, "bound": True, "windows": True, "drift": False})

    def test_a_tilt_that_cannot_be_computed_is_p_one_said_in_the_figures(self):
        days = sessions("2026-10-05", 30)
        rows = record(days, [[0.8], [0.004], [-0.00001]] * 10)   # every losing day tiny against the largest day
        out = self.judged(rows, days, 60)
        self.assertEqual((out["full"], out["p"], out["p_adj"]), (True, 1.0, 1.0))
        self.assertEqual(out["tilt"], {"raw": L.TILT_WEIGHTS, "adjusted": L.TILT_WEIGHTS})
        self.assertLess(out["perc_p"], 0.05)
        self.assertEqual((out["lines"]["bound"], out["lines"]["drift"]), (False, False))

    def test_no_losing_day_is_p_one_whatever_the_percentile_test_says(self):
        days = sessions("2026-10-05", 40)
        out = self.judged(record(days, [[0.05, 0.1]] * 40), days, 40)
        self.assertEqual((out["p"], out["perc_p"], out["tilt"]["raw"]), (1.0, FLOOR, L.TILT_NO_LOSS))
        self.assertFalse(out["lines"]["bound"])

    def test_the_bound_needs_both_tests(self):
        days, rows, _ = cases()["edge"]
        for tilted, perc, bound in ((0.004, 0.05, True), (0.0041, 0.01, False), (0.001, 0.0501, False),
                                    (0.004, 0.0501, False)):
            with patch.object(L, "tilted", return_value=(tilted, None)), \
                    patch.object(L, "percentile", return_value=(perc, 0.01)):
                self.assertEqual(self.judged(rows, days, 40)["lines"]["bound"], bound, (tilted, perc))
        with patch.object(L, "percentile", return_value=(0.02, 0.01)):
            self.assertTrue(self.judged(rows, days, 40)["lines"]["bound"])
            self.assertFalse(self.judged(rows, days, 40, rules=rules(confidence=0.99))["lines"]["bound"],
                             "a higher confidence tightens the percentile line")


# ================================================================================================== the daily lines
@unittest.skipUnless(HAVE, "numpy not installed")
class TheJudgement(unittest.TestCase):
    """THE DAILY LINES (`judge_daily`): the rule before the checkpoints, which nothing judges by now."""

    def cohort(self, first="2026-10-05"):
        return {"family": "fam", "version": 1, "first_day": first,
                "snapshot": {"run_sha": "sha-1", "practice_evaluator": EVALUATOR}}

    def test_a_short_record_has_p_one_and_says_why(self):
        days = sessions("2026-10-05", 19)
        out = L.judge_daily(self.cohort(), {"first_day": days[0], "sessions": 19}, record(days, [[0.4, 0.4]] * 19),
                      through=days[-1], rules=rules())
        self.assertEqual((out["full"], out["p"], out["lines"]["record"]), (False, 1.0, False))
        self.assertEqual(out["closes"], 38)
        self.assertEqual(out["per_session"][days[0]], 2)

    def test_a_strong_record_meets_every_line_but_the_desks(self):
        rng = np.random.default_rng(3)
        days = sessions("2026-10-05", 24)
        rows = record(days, [[0.25 + 0.3 * float(rng.standard_normal()) for _ in range(2)] for _ in days])
        out = L.judge_daily(self.cohort(), {"first_day": days[0], "sessions": 24}, rows, through=days[-1], rules=rules())
        self.assertTrue(all(out["lines"].values()), out["lines"])
        self.assertLess(out["p"], 0.05)
        self.assertEqual(out["typical"], round(100.0 + 2.6, 2), "the median lot's maximum loss with both fees")

    def test_a_practice_row_older_than_its_cohort_is_ineligible(self):
        days = sessions("2026-10-05", 24)
        out = L.judge_daily(self.cohort(days[1]), {"first_day": days[0], "sessions": 24}, record(days, [[0.3]] * 24),
                      through=days[-1], rules=rules())
        self.assertEqual((out["eligible"], out["sessions"], out["p"]), (False, None, 1.0))

    def test_the_inputs_hash_moves_with_any_close(self):
        days = sessions("2026-10-05", 22)
        rows = record(days, [[0.3, 0.1]] * 22)
        a = L.judge_daily(self.cohort(), {"first_day": days[0], "sessions": 22}, rows, through=days[-1], rules=rules())
        rows[3] = dict(rows[3], pnl=rows[3]["pnl"] + 0.01)
        b = L.judge_daily(self.cohort(), {"first_day": days[0], "sessions": 22}, rows, through=days[-1], rules=rules())
        self.assertNotEqual(a["inputs"], b["inputs"])


# ================================================================================================== the store
class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = [1_790_000_000.0]
        self.store = ObserveStore(self.root, clock=lambda: self.now[0])
        self.store.evaluator = EVALUATOR
        self.addCleanup(self.store.close)

    def program(self, fid="fam", n=1, tier="validated") -> dict:
        return {"family": fid, "version": n, "band": "gym", "observe": True, "tier": tier, "lineage": fid,
                "code": CODE, "params": {"hold": 3}, "run_sha": f"sha-{fid}-{n}", "structure": "debit_vertical"}

    def add_record(self, fid: str, n: int, days: list[str], returns: list[list[float]], **kw) -> None:
        db = self.store._connect()
        for r in record(days, returns, **kw):
            db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, "
                       "body, exit_day, reason, forced, evaluator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (f"{fid}@{n}:o", "a", fid, n, f"{fid}-{r['trade_id']}", r["exit_day"], r["pnl"], r["max_loss"], 1.0,
                        json.dumps(r["body"]), r["exit_day"], "program", 0, EVALUATOR))
        db.execute("INSERT OR REPLACE INTO practice(family, version, tier, capital, first_at, first_day, last_at, last_day, "
                   "sessions) VALUES(?,?,?,?,?,?,?,?,?)", (fid, n, "validated", 10000.0, 1.0, days[0], 2.0, days[-1],
                                                           len(days)))


class TheCohortLifecycle(StoreCase):
    # ------------------------------------------------------------------ THE RE-ENTRY RULE (`test_live_reentry.py` holds it whole)
    def test_a_program_a_release_interrupted_practises_again_as_a_new_cohort(self):
        self.store.freeze(self.program(), day="2026-10-05")
        old = sessions("2026-10-05", 4)
        self.add_record("fam", 1, old, [[0.2]] * 4)
        self.store.evaluator = "bundle-2:fills-1:exec-2"         # a release moved the practice evaluator
        out = self.store.cohort_candidates([self.program()], day="2026-10-12", in_session=True)
        self.assertEqual([(r["family"], r.get("practice_frozen")) for r in out], [("fam", None)],
                         "offered again, not as the old snapshot")
        snap = self.store.freeze(out[0], day="2026-10-12")
        self.assertEqual(snap["practice_evaluator"], "bundle-2:fills-1:exec-2")
        db = self.store._connect()
        self.assertEqual(db.execute("SELECT status, first_day, evaluator FROM cohorts").fetchall(),
                         [("active", "2026-10-12", "bundle-2:fills-1:exec-2")])
        [(status, reason, evaluator, practice)] = db.execute(
            "SELECT status, reason, evaluator, practice FROM cohort_archive").fetchall()
        self.assertEqual((status, evaluator), ("complete", EVALUATOR))
        self.assertIn("evaluator changed", reason)
        self.assertEqual(json.loads(practice)["sessions"], 4, "its old practice row is kept in the archive")
        self.assertIsNone(db.execute("SELECT 1 FROM practice").fetchone(), "its practice row starts again")
        self.assertEqual(sorted((e["evaluator"], e["entered_day"]) for e in self.store.entrants(since="2026-01-01")),
                         [(EVALUATOR, "2026-10-05"), ("bundle-2:fills-1:exec-2", "2026-10-12")], "two trials")
        new = sessions("2026-10-12", 3)
        self.store.practice([{"family": "fam", "version": 1, "tier": "validated", "capital": 10000.0, "account": "b",
                              "at": self.now[0] + 86_400.0 * i, "day": d, "equity": 10000.0} for i, d in enumerate(new)])
        practice, _ = self.store.ladder_rows("fam", 1, evaluator=self.store.evaluator, first_day="2026-10-12",
                                             through=new[-1])
        cohort = self.store.ladder_cohorts()[0]
        self.assertEqual(L.practised(cohort, practice, new[-1]), (3, new), "its checkpoints count its own sessions")
        self.store.add_decision({"day": new[-1], "family": "fam", "version": 1, "run_sha": "sha-fam-1", "inputs": "x",
                                 "stats": {}, "p_value": 0.5, "verdict": "fail", "binding": False, "checkpoint": 40})
        self.assertEqual({e["evaluator"]: (e["p_value"], e["p_checkpoint"]) for e in self.store.entrants(since="2026-01-01")},
                         {"bundle-2:fills-1:exec-2": (0.5, 40), EVALUATOR: (None, None)}, "a judgement is its own entrant's")

    def test_a_cohort_that_completed_or_was_ended_by_the_ladder_never_reenters_under_any_evaluator(self):
        from league.live.observe import EVALUATOR_CHANGED, WINDOW_ENDED

        endings = (("complete", WINDOW_ENDED), ("failed", "ladder: its family retired"), ("promoted", "ladder: promoted"),
                   ("demoted", "ladder: demoted"), ("complete", None))
        for i, (status, reason) in enumerate(endings):
            self.store.freeze(self.program(f"f{i}"), day="2026-10-05")
            self.store._connect().execute("UPDATE cohorts SET status=?, reason=? WHERE family=?", (status, reason, f"f{i}"))
        self.store.freeze(self.program("cut"), day="2026-10-05")
        self.store._connect().execute("UPDATE cohorts SET status='complete', reason=? WHERE family='cut'",
                                      (EVALUATOR_CHANGED,))
        current = [self.program(f"f{i}") for i in range(len(endings))] + [self.program("cut")]
        for evaluator in (EVALUATOR, "another"):
            self.store.evaluator = evaluator
            out = self.store.cohort_candidates(current, day="2026-10-12", in_session=True)
            self.assertEqual([r["family"] for r in out], ["cut"], "only the one an evaluator change interrupted, read by "
                                                                  "its recorded ending and not by its evaluator")
            for i in range(len(endings)):
                with self.assertRaises(ValueError):
                    self.store.freeze(self.program(f"f{i}"), day="2026-10-12")

    def test_the_trade_cap_spares_an_active_or_promoted_ladder_record(self):
        store = ObserveStore(self.root / "capped", clock=lambda: 1.0, max_rows=10)
        store.evaluator = EVALUATOR
        self.addCleanup(store.close)
        store.freeze(self.program("kept"), day="2026-10-05")
        store.freeze(self.program("up"), day="2026-10-05")
        store.close_cohort("up", 1, status="promoted", day="2026-11-02", reason="r")
        for fid in ("kept", "up", "other"):
            store.add(f"{fid}@1:o", fid, 1, [{"id": i, "pnl": 1.0, "max_loss": 10.0, "exit_day": "2026-10-06",
                                              "evaluator": EVALUATOR} for i in range(8)], account="a")
        counts = dict(store._connect().execute("SELECT family, COUNT(*) FROM trades GROUP BY family").fetchall())
        self.assertEqual((counts.get("kept"), counts.get("up"), counts.get("other")), (8, 8, None),
                         "the oldest unprotected rows go; the ladder's records stay whole")

    def test_an_older_file_gains_the_cohorts_evaluator(self):
        import sqlite3

        path = self.root / "old"
        path.mkdir()
        db = sqlite3.connect(str(path / "observe.sqlite"))
        db.execute("CREATE TABLE cohorts (family TEXT NOT NULL, version INTEGER NOT NULL, admitted_at REAL NOT NULL, "
                   "first_day TEXT NOT NULL, snapshot TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', "
                   "completed_day TEXT, reason TEXT, PRIMARY KEY (family, version))")
        db.execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot) VALUES('a', 1, 1, '2026-10-01', ?)",
                   (json.dumps({"practice_evaluator": "e-old"}),))
        db.commit()
        db.close()
        store = ObserveStore(path, clock=lambda: 1.0)
        self.addCleanup(store.close)
        self.assertEqual(store._connect().execute("SELECT evaluator FROM cohorts").fetchone(), ("e-old",))

    def test_a_frozen_cohort_is_a_ladder_entrant_once(self):
        snap = self.store.freeze(self.program(), day="2026-10-05")
        self.assertEqual(snap["ladder"], L.LADDER_VERSION)
        self.assertEqual(snap["practice_max_sessions"], L.Rules.from_constitution().max_sessions)
        self.store.freeze(self.program(), day="2026-10-06")
        [entrant] = self.store.entrants(since="2026-01-01")
        self.assertEqual((entrant["family"], entrant["version"], entrant["run_sha"], entrant["tier"], entrant["evaluator"],
                          entrant["entered_day"], entrant["p_value"]),
                         ("fam", 1, "sha-fam-1", "validated", EVALUATOR, "2026-10-05", None))

    def test_a_ladder_cohort_never_completes_at_the_old_target_but_at_its_window(self):
        self.store.freeze(self.program(), day="2026-10-05")
        days = sessions("2026-10-05", 5)
        self.add_record("fam", 1, days, [[0.2, 0.2, 0.2]] * 5)
        out = self.store.cohort_candidates([], day=sessions("2026-10-05", 6)[-1], in_session=True)
        self.assertEqual([r["family"] for r in out], ["fam"], "3 sessions and 10 closes no longer end it")
        late = sessions("2026-10-05", 61)[-1]
        self.assertEqual([r["family"] for r in self.store.cohort_candidates([], day=sessions("2026-10-05", 60)[-1],
                                                                            in_session=True)], ["fam"])
        self.store.add_decision({"day": sessions("2026-10-05", 60)[-1], "family": "fam", "version": 1, "inputs": "x",
                                 "stats": {}, "p_value": 1.0, "verdict": "short", "binding": False, "checkpoint": 60})
        self.assertEqual(self.store.cohort_candidates([], day=late, in_session=True), [])
        status = self.store._connect().execute("SELECT status, reason FROM cohorts").fetchone()
        self.assertEqual(status, ("complete", "ladder: its practice window ended"))

    def test_a_cohort_whose_last_checkpoint_is_not_judged_is_held_for_it_and_no_longer_than_the_wait(self):
        self.store.freeze(self.program(), day="2026-10-05")
        self.store.freeze(self.program("early"), day="2026-10-05")
        self.store.add_decision({"day": "2026-12-01", "family": "early", "version": 1, "inputs": "x", "stats": {},
                                 "p_value": 1.0, "verdict": "short", "binding": False, "checkpoint": 40})
        days = sessions("2026-10-05", 67)
        for k in (61, 62, 63, 64, 65):                       # the House missed the 60th session's end
            out = self.store.cohort_candidates([], day=days[k - 1], in_session=True)
            self.assertEqual(sorted(r["family"] for r in out), ["early", "fam"], k)
        self.assertEqual(self.store.cohort_candidates([], day=days[65], in_session=True), [])
        self.assertEqual(self.store._connect().execute("SELECT DISTINCT status, reason FROM cohorts").fetchall(),
                         [("complete", "ladder: its practice window ended and its last checkpoint was never judged")])

    def test_the_window_hold_is_one_rule(self):
        from league.live.observe import WINDOW_ENDED, WINDOW_UNANSWERED, WINDOW_UNJUDGED, ladder_window

        def window(state, latched=60, hold=5):
            return ladder_window(60, state, sessions_through=lambda day: latched, answer_sessions=hold)

        waiting = {"checkpoint": 60, "day": "2026-12-30", "receipt": 2, "waits": "prefilter"}
        self.assertEqual(window({"judged": {}, "latch": None}), (65, WINDOW_UNJUDGED))
        self.assertEqual(window({"judged": {40: {}}, "latch": None}), (65, WINDOW_UNJUDGED))
        self.assertEqual(window({"judged": {40: {}, 60: {}}, "latch": None}), (60, WINDOW_ENDED))
        self.assertEqual(window({"judged": {60: {}}, "latch": waiting}), (65, WINDOW_UNANSWERED))
        self.assertEqual(window({"judged": {60: {}}, "latch": dict(waiting, waits="validation")}), (65, WINDOW_UNANSWERED))
        self.assertEqual(window({"judged": {60: {}}, "latch": waiting}, latched=61), (66, WINDOW_UNANSWERED),
                         "judged a session late: its wait counts from its own checkpoint's day")
        self.assertEqual(window({"judged": {40: {}}, "latch": dict(waiting, checkpoint=40)}, latched=40),
                         (60, WINDOW_UNANSWERED), "a first checkpoint's wait is inside the window")
        self.assertEqual(window({"judged": {40: {}}, "latch": dict(waiting, checkpoint=40)}, latched=58),
                         (63, WINDOW_UNANSWERED))
        self.assertEqual(window({"judged": {40: {}}, "latch": dict(waiting, waits=None, answer={})}), (60, WINDOW_ENDED),
                         "its answer was read: it ends at its window")
        self.assertEqual(window({"judged": {}, "latch": None}, hold=0), (60, WINDOW_UNJUDGED))
        self.assertEqual(window({"judged": {60: {}}, "latch": dict(waiting, day=None)}, latched="x"),
                         (60, WINDOW_UNANSWERED), "a latch whose day cannot be counted holds nothing")
        self.assertEqual(window(json.dumps({"judged": {"60": {}}, "latch": waiting})), (65, WINDOW_UNANSWERED),
                         "the column as it is stored")
        self.assertEqual(window(None), (65, WINDOW_UNJUDGED))

    def test_a_pre_ladder_cohort_keeps_the_old_rule(self):
        snapshot = dict(self.program(), practice_frozen=True, practice_evaluator=EVALUATOR)
        self.store._connect().execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot) VALUES(?,?,?,?,?)",
                                      ("old", 1, 1.0, "2026-10-05", json.dumps(snapshot)))
        days = sessions("2026-10-05", 4)
        self.add_record("old", 1, days, [[0.2, 0.2, 0.2]] * 4)
        self.store.cohort_candidates([], day=sessions("2026-10-05", 5)[-1], in_session=True)
        status = self.store._connect().execute("SELECT status, reason FROM cohorts WHERE family='old'").fetchone()
        self.assertEqual(status, ("complete", "observation target reached"))

    def test_close_cohort_moves_only_from_the_states_named(self):
        self.store.freeze(self.program(), day="2026-10-05")
        self.assertTrue(self.store.close_cohort("fam", 1, status="promoted", day="2026-11-02", reason="r"))
        self.assertFalse(self.store.close_cohort("fam", 1, status="failed", day="2026-11-02", reason="r"))
        self.assertTrue(self.store.close_cohort("fam", 1, status="demoted", day="2026-12-02", reason="r",
                                                was=("promoted",)))
        with self.assertRaises(ValueError):
            self.store.close_cohort("fam", 1, status="active", day="x", reason="r")
        self.assertEqual(self.store.ladder_cohorts(), [])
        self.assertEqual([c["status"] for c in self.store.ladder_cohorts(statuses=("demoted",))], ["demoted"])

    def test_fail_cohort_fails_an_active_cohort_only(self):
        """A program that cannot benefit from more practice frees its slot; a cohort the ladder promoted or demoted, or
        that ended already, keeps its own ending (a promoted row turned `failed` would lose its later demotion and the
        trade cap's protection)."""
        endings = {"promoted": ("promoted", "ladder: promoted to Probe (receipt 1)"), "demoted": ("demoted", "ladder: x"),
                   "complete": ("complete", "ladder: its practice window ended"), "failed": ("failed", "ladder: y")}
        db = self.store._connect()
        for fid, (status, reason) in endings.items():
            self.store.freeze(self.program(fid), day="2026-10-05")
            db.execute("UPDATE cohorts SET status=?, completed_day='2026-11-02', reason=? WHERE family=?",
                       (status, reason, fid))
        self.store.freeze(self.program("live"), day="2026-10-05")
        for fid in endings:
            self.assertIs(self.store.fail_cohort(fid, 1, day="2026-12-01", reason="the program does not load"), False)
            self.assertEqual(db.execute("SELECT status, completed_day, reason FROM cohorts WHERE family=?",
                                        (fid,)).fetchone(), (endings[fid][0], "2026-11-02", endings[fid][1]), fid)
        self.assertIs(self.store.fail_cohort("nobody", 1, day="2026-12-01", reason="r"), False)
        self.assertIs(self.store.fail_cohort("live", 1, day="2026-12-01", reason="the program does not load"), True)
        self.assertEqual(db.execute("SELECT status, completed_day, reason FROM cohorts WHERE family='live'").fetchone(),
                         ("failed", "2026-12-01", "the program does not load"))
        self.assertTrue(self.store.close_cohort("promoted", 1, status="demoted", day="2026-12-02", reason="r",
                                                was=("promoted",)), "its later demotion still finds it promoted")

    def test_the_record_is_the_cohorts_own_program_closes_under_its_evaluator(self):
        self.store.freeze(self.program(), day="2026-10-05")
        days = sessions("2026-10-05", 3)
        self.add_record("fam", 1, days, [[0.1]] * 3)
        db = self.store._connect()
        db.execute("UPDATE trades SET forced=1 WHERE trade_id='fam-0'")
        db.execute("UPDATE trades SET evaluator='other' WHERE trade_id='fam-1'")
        practice, rows = self.store.ladder_rows("fam", 1, evaluator=EVALUATOR, first_day=days[0], through=days[-1])
        self.assertEqual([r["trade_id"] for r in rows], ["fam-2"])
        self.assertEqual(practice["sessions"], 3)
        _, none = self.store.ladder_rows("fam", 1, evaluator=EVALUATOR, first_day=days[0], through=days[1])
        self.assertEqual(none, [], "nothing after the day judged")


# ================================================================================================== the checkpoint's store
#: The ladder's tables as the release before the checkpoints wrote them (no `ladder_state`, `p_checkpoint`, `checkpoint`).
BEFORE_CHECKPOINTS = """
CREATE TABLE cohorts (
    family TEXT NOT NULL, version INTEGER NOT NULL, admitted_at REAL NOT NULL, first_day TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', completed_day TEXT, reason TEXT, evaluator TEXT,
    PRIMARY KEY (family, version));
CREATE TABLE cohort_archive (
    family TEXT NOT NULL, version INTEGER NOT NULL, evaluator TEXT, admitted_at REAL NOT NULL, first_day TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL, completed_day TEXT, reason TEXT, practice TEXT,
    archived_at REAL NOT NULL);
CREATE TABLE entrants (
    family TEXT NOT NULL, version INTEGER NOT NULL, run_sha TEXT, lineage TEXT, tier TEXT, evaluator TEXT NOT NULL,
    entered_at REAL NOT NULL, entered_day TEXT NOT NULL, p_value REAL, p_day TEXT,
    PRIMARY KEY (family, version, evaluator));
CREATE TABLE ladder_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL,
    run_sha TEXT, inputs TEXT NOT NULL, stats TEXT NOT NULL, p_value REAL, bh_rank INTEGER, bh_size INTEGER,
    bh_threshold REAL, verdict TEXT NOT NULL, reasons TEXT, binding INTEGER NOT NULL, at REAL NOT NULL);
"""


class TheCheckpointStore(StoreCase):
    def setUp(self):
        super().setUp()
        self.store.freeze(self.program(), day="2026-10-05")

    def judge(self, fid="fam", **changes) -> int:
        """A checkpoint's receipt for `fid`'s cohort (the first checkpoint, a failed line, unless changed)."""
        row = {"day": "2026-12-01", "family": fid, "version": 1, "run_sha": f"sha-{fid}-1", "inputs": "hash",
               "stats": {"lines": {"windows": False}}, "p_value": 0.003, "bh_rank": 1, "bh_size": 4, "bh_threshold": 0.025,
               "verdict": "fail", "reasons": ["the windows line"], "binding": False, "checkpoint": 40, **changes}
        return self.store.add_decision(row)

    def entrant(self, fid="fam") -> tuple:
        return self.store._connect().execute("SELECT p_value, p_day, p_checkpoint FROM entrants WHERE family=? AND "
                                             "evaluator=?", (fid, self.store.evaluator)).fetchone()

    def receipts(self) -> int:
        return self.store._connect().execute("SELECT COUNT(*) FROM ladder_decisions").fetchone()[0]

    def test_a_checkpoints_receipt_names_it_and_writes_the_p_value_and_the_state_with_it(self):
        self.assertEqual(self.entrant(), (None, None, None))
        self.assertEqual(self.store.ladder_state("fam", 1), {"judged": {}, "latch": None})
        receipt = self.judge()
        row = self.store.decision(receipt)
        self.assertEqual((row["checkpoint"], row["verdict"], row["p_value"], row["bh_rank"], row["bh_size"],
                          row["bh_threshold"], row["inputs"], row["stats"], row["reasons"], row["day"]),
                         (40, "fail", 0.003, 1, 4, 0.025, "hash", {"lines": {"windows": False}}, ["the windows line"],
                          "2026-12-01"))
        self.assertEqual(self.entrant(), (0.003, "2026-12-01", 40))
        [entrant] = self.store.entrants(since="2026-01-01")
        self.assertEqual((entrant["p_value"], entrant["p_day"], entrant["p_checkpoint"]), (0.003, "2026-12-01", 40))
        state = {"judged": {40: {"day": "2026-12-01", "receipt": receipt}}, "latch": None}
        self.assertEqual(self.store.ladder_state("fam", 1), state)
        self.assertEqual(self.store.ladder_cohorts()[0]["state"], state)
        self.assertEqual(self.store.ladder_state("nobody", 1), {"judged": {}, "latch": None})

    def test_each_checkpoint_is_judged_at_most_once_and_never_an_earlier_one_after_a_later(self):
        first = self.judge()
        with self.assertRaises(ValueError):
            self.judge(p_value=0.9, day="2026-12-02")
        self.assertEqual((self.receipts(), self.entrant()), (1, (0.003, "2026-12-01", 40)), "nothing written")
        last = self.judge(checkpoint=60, p_value=0.2, day="2026-12-30")
        self.assertEqual(self.entrant(), (0.2, "2026-12-30", 60), "its latest judged checkpoint's")
        self.assertEqual(self.store.ladder_state("fam", 1)["judged"],
                         {40: {"day": "2026-12-01", "receipt": first}, 60: {"day": "2026-12-30", "receipt": last}})
        for checkpoint in (40, 60):
            with self.assertRaises(ValueError):
                self.judge(checkpoint=checkpoint, p_value=0.0001, day="2026-12-31")
        self.store.freeze(self.program("late"), day="2026-10-05")
        self.judge("late", checkpoint=60, p_value=0.5)       # its first checkpoint fell due only at its window's end
        with self.assertRaises(ValueError):
            self.judge("late", checkpoint=40, p_value=0.0001, day="2026-12-31")
        self.assertEqual((self.receipts(), self.entrant("late")), (3, (0.5, "2026-12-01", 60)))

    def test_the_p_value_is_written_only_at_a_checkpoint(self):
        self.assertFalse(hasattr(self.store, "set_entrant_p"), "the store has no write of a p-value but a checkpoint's")

        def plain(day):
            return self.store.add_decision({"day": day, "family": "fam", "version": 1, "run_sha": "sha-fam-1",
                                            "inputs": "x", "stats": {}, "p_value": 0.0001, "verdict": "would_promote",
                                            "binding": False})

        plain("2026-10-06")
        self.assertEqual(self.entrant(), (None, None, None), "nothing before its first checkpoint")
        self.judge()
        receipt = plain("2026-12-02")
        self.assertIsNone(self.store.decision(receipt)["checkpoint"])
        self.assertEqual(self.entrant(), (0.003, "2026-12-01", 40),
                         "never rewritten between checkpoints: a receipt that names no checkpoint writes no p-value")
        self.assertEqual(set(self.store.ladder_state("fam", 1)["judged"]), {40})
        self.judge(checkpoint=60, p_value=0.4, day="2026-12-30")
        plain("2027-01-04")
        self.assertEqual(self.entrant(), (0.4, "2026-12-30", 60), "nor after its last")
        self.store.close_cohort("fam", 1, status="failed", day="2027-01-04", reason="r")
        with self.assertRaises(ValueError):
            self.judge(checkpoint=60, p_value=0.0001, day="2027-01-05")
        self.assertEqual(self.entrant(), (0.4, "2026-12-30", 60), "nor after it ended")

    def test_a_latch_holds_the_checkpoints_verdict_and_only_moves_on(self):
        receipt = self.judge(verdict="await_validation", reasons=[], latch="validation")
        latch = {"checkpoint": 40, "day": "2026-12-01", "receipt": receipt, "waits": "validation"}
        self.assertEqual(self.store.ladder_state("fam", 1)["latch"], latch)
        self.assertEqual(self.store.ladder_cohorts()[0]["state"]["latch"], latch)
        with self.assertRaises(ValueError):
            self.judge(checkpoint=60, p_value=0.0001, day="2026-12-30")
        self.assertEqual((self.receipts(), self.entrant()), (1, (0.003, "2026-12-01", 40)),
                         "a latched cohort is never judged again and its p-value stands")
        self.assertFalse(self.store.move_latch("fam", 1, waits="validation"), "it already waits for that")
        self.assertTrue(self.store.move_latch("fam", 1, waits="prefilter"))
        self.assertEqual(self.store.ladder_state("fam", 1)["latch"], dict(latch, waits="prefilter"))
        self.assertFalse(self.store.move_latch("fam", 1, waits="validation"), "never back")
        self.assertFalse(self.store.move_latch("fam", 1, waits="prefilter"))
        answer = {"day": "2026-12-02", "receipt": receipt + 1, "verdict": "would_promote"}
        self.assertTrue(self.store.move_latch("fam", 1, waits=None, answer=answer))
        self.assertEqual(self.store.ladder_state("fam", 1)["latch"], dict(latch, waits=None, answer=answer))
        for waits in ("validation", "prefilter", None):
            self.assertFalse(self.store.move_latch("fam", 1, waits=waits), "its answer was read: nothing waits")
        with self.assertRaises(ValueError):
            self.judge(checkpoint=60, p_value=0.0001, day="2026-12-30")
        with self.assertRaises(ValueError):
            self.store.move_latch("fam", 1, waits="the gate")

    def test_a_latch_may_wait_for_the_prefilter_from_the_start_and_needs_a_checkpoint(self):
        receipt = self.judge(verdict="await_prefilter", reasons=[], latch="prefilter", checkpoint=60)
        self.assertEqual(self.store.ladder_state("fam", 1)["latch"],
                         {"checkpoint": 60, "day": "2026-12-01", "receipt": receipt, "waits": "prefilter"})
        self.assertTrue(self.store.move_latch("fam", 1, waits=None, answer={"verdict": "prefilter_negative"}))
        self.store.freeze(self.program("two"), day="2026-10-05")
        self.assertFalse(self.store.move_latch("two", 1, waits="prefilter"), "no latch to move")
        self.assertFalse(self.store.move_latch("nobody", 1, waits="prefilter"))
        for changes in ({"checkpoint": None, "latch": "validation"}, {"latch": "the gate"}):
            with self.assertRaises(ValueError):
                self.judge("two", **changes)
        self.judge("two", latch="validation")
        self.store.close_cohort("two", 1, status="failed", day="2026-12-02", reason="r")
        self.assertFalse(self.store.move_latch("two", 1, waits="prefilter"), "an ended cohort's latch moves no more")
        self.assertEqual(self.store.ladder_cohorts(statuses=("failed",))[0]["state"]["latch"]["waits"], "validation")

    def answer(self, fid="fam", **changes) -> dict:
        """A latched cohort's answer's receipt (no checkpoint)."""
        return {"day": "2026-12-02", "family": fid, "version": 1, "run_sha": f"sha-{fid}-1", "inputs": "hash",
                "stats": {"latch": {"checkpoint": 40}}, "p_value": 0.003, "verdict": "would_promote", "reasons": [],
                "binding": False, **changes}

    def status(self, fid="fam") -> tuple:
        return self.store._connect().execute("SELECT status, completed_day, reason FROM cohorts WHERE family=?",
                                             (fid,)).fetchone()

    def test_an_answer_is_written_with_its_latch_and_its_ending_in_one_transaction(self):
        with self.assertRaises(ValueError):
            self.store.add_answer(self.answer())             # never latched: there is nothing to answer
        first = self.judge(verdict="await_prefilter", reasons=[], latch="prefilter")
        with self.assertRaises(ValueError):
            self.store.add_answer(self.answer(checkpoint=60))
        with self.assertRaises(ValueError):
            self.store.add_answer(self.answer(), close="demoted")
        self.assertEqual(self.receipts(), 1, "nothing written")
        receipt = self.store.add_answer(self.answer())
        latch = self.store.ladder_state("fam", 1)["latch"]
        self.assertEqual(latch, {"checkpoint": 40, "day": "2026-12-01", "receipt": first, "waits": None,
                                 "answer": {"day": "2026-12-02", "receipt": receipt, "verdict": "would_promote"}})
        self.assertEqual(self.status(), ("active", None, None), "answered, it practises on")
        self.assertEqual((self.store.decision(receipt)["checkpoint"], self.entrant()), (None, (0.003, "2026-12-01", 40)))
        with self.assertRaises(ValueError):
            self.store.add_answer(self.answer(day="2026-12-03"))
        self.assertEqual(self.receipts(), 2, "once: an answered latch takes no second answer")
        for fid, close in (("f", "failed"), ("c", "complete"), ("p", "promoted")):
            self.store.freeze(self.program(fid), day="2026-10-05")
            self.judge(fid, verdict="await_validation", reasons=[], latch="validation")
            receipt = self.store.add_answer(self.answer(fid, verdict="x"), close=close, reason="ladder: why")
            self.assertEqual(self.status(fid), (close, "2026-12-02", "ladder: why"))
            self.assertEqual(self.store.ladder_cohorts(statuses=(close,))[0]["state"]["latch"]["answer"],
                             {"day": "2026-12-02", "receipt": receipt, "verdict": "x"})
        self.store.freeze(self.program("moved"), day="2026-10-05")
        self.judge("moved", verdict="await_prefilter", reasons=[], latch="prefilter")
        self.store.evaluator = "bundle-2:fills-1:exec-2"
        with self.assertRaises(ValueError):
            self.store.add_answer(self.answer("moved"))

    def test_an_answer_that_cannot_write_its_latch_writes_no_receipt(self):
        self.judge(verdict="await_prefilter", reasons=[], latch="prefilter")
        with patch.object(self.store, "_answered", side_effect=__import__("sqlite3").OperationalError("locked")):
            with self.assertRaises(__import__("sqlite3").OperationalError):
                self.store.add_answer(self.answer())
        self.assertEqual((self.receipts(), self.store.ladder_state("fam", 1)["latch"]["waits"]), (1, "prefilter"))

    def test_a_pending_promotion_is_settled_with_its_cohort_and_is_no_promotion_until_then(self):
        from league.live.observe import PROMOTE_PENDING
        from league.swarm import bands

        first = self.judge(verdict="await_prefilter", reasons=[], latch="prefilter")
        pending = self.store.add_decision(self.answer(verdict=PROMOTE_PENDING, binding=True))
        self.assertEqual((self.status(), self.store.ladder_state("fam", 1)["latch"]["waits"]),
                         (("active", None, None), "prefilter"), "a pending receipt changes nothing of its cohort")
        self.assertFalse(bands.ladder_receipt(self.root, family="fam", version=1, run_sha="sha-fam-1", receipt=pending),
                         "the live path takes no pending receipt")
        with self.assertRaises(ValueError):
            self.store.settle_answer(first, "promote", day="2026-12-02", close="promoted", reason="r")
        with self.assertRaises(ValueError):
            self.store.settle_answer(pending, "promote", day="2026-12-02", close="active", reason="r")
        self.assertEqual(self.store.decision(pending)["verdict"], PROMOTE_PENDING)
        self.assertTrue(self.store.settle_answer(pending, "promote", ["promoted"], day="2026-12-02", close="promoted",
                                                 reason="ladder: promoted"))
        row = self.store.decision(pending)
        self.assertEqual((row["verdict"], row["reasons"]), ("promote", ["promoted"]))
        self.assertEqual(self.status(), ("promoted", "2026-12-02", "ladder: promoted"))
        self.assertTrue(bands.ladder_receipt(self.root, family="fam", version=1, run_sha="sha-fam-1", receipt=pending))
        with self.assertRaises(ValueError):
            self.store.settle_answer(pending, "blocked", ["x"], day="2026-12-03", close="failed", reason="r")
        self.assertFalse(self.store.settle_answer(pending, "promote", day="2026-12-03", close="promoted", reason="again",
                                                  was=("promote", PROMOTE_PENDING)), "its cohort already moved")
        self.assertEqual(self.status(), ("promoted", "2026-12-02", "ladder: promoted"))
        self.assertEqual(self.store.decision(pending)["reasons"], ["promoted"], "no reasons given: they stand")
        self.assertFalse(self.store.set_verdict(pending, "promote_void", ["x"], was=(PROMOTE_PENDING,)),
                         "a settled receipt is never voided")
        again = self.store.add_decision(self.answer(verdict=PROMOTE_PENDING))
        self.assertTrue(self.store.set_verdict(again, "promote_void", ["its band move raised"], was=(PROMOTE_PENDING,)))
        self.assertEqual(self.store.decision(again)["verdict"], "promote_void")

    def test_a_checkpoints_judgement_can_end_its_cohort_with_it(self):
        receipt = self.judge(verdict="validation_failed", reasons=[], checkpoint=40)
        self.assertEqual(self.status(), ("active", None, None))
        for bad in ({"latch": "validation"}, {"checkpoint": None}):
            with self.assertRaises(ValueError):
                self.store.add_decision(self.answer() | {"checkpoint": 60, "verdict": "x", **bad}, close="failed", reason="r")
        with self.assertRaises(ValueError):
            self.store.add_decision(self.answer() | {"checkpoint": 60}, close="complete", reason="r")
        last = self.store.add_decision(self.answer() | {"checkpoint": 60, "verdict": "validation_failed"}, close="failed",
                                       reason="ladder: its version did not meet the Validation line")
        self.assertEqual(self.status(), ("failed", "2026-12-02", "ladder: its version did not meet the Validation line"))
        self.assertEqual(self.store.ladder_cohorts(statuses=("failed",))[0]["state"],
                         {"judged": {40: {"day": "2026-12-01", "receipt": receipt},
                                     60: {"day": "2026-12-02", "receipt": last}}, "latch": None})
        self.assertEqual(self.entrant(), (0.003, "2026-12-02", 60))

    def test_a_waiting_latch_is_told_of_once(self):
        self.assertFalse(self.store.latch_told("fam", 1, day="2026-12-03"), "no latch")
        self.judge(verdict="await_validation", reasons=[], latch="validation")
        self.assertTrue(self.store.latch_told("fam", 1, day="2026-12-03"))
        self.assertFalse(self.store.latch_told("fam", 1, day="2026-12-04"))
        self.assertEqual(self.store.ladder_state("fam", 1)["latch"]["told"], "2026-12-03")
        self.assertTrue(self.store.move_latch("fam", 1, waits="prefilter"))
        self.assertFalse(self.store.latch_told("fam", 1, day="2026-12-05"), "once for both waits")
        self.store.freeze(self.program("two"), day="2026-10-05")
        self.judge("two", verdict="await_prefilter", reasons=[], latch="prefilter")
        self.store.add_answer(self.answer("two"))
        self.assertFalse(self.store.latch_told("two", 1, day="2026-12-05"), "answered: nothing waits")

    def test_only_an_active_ladder_cohort_under_the_running_evaluator_is_judged_at_a_checkpoint(self):
        with self.assertRaises(ValueError):
            self.judge("nobody")
        snapshot = dict(self.program("old"), practice_frozen=True, practice_evaluator=EVALUATOR)   # before the ladder
        db = self.store._connect()
        db.execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot, evaluator) VALUES(?,?,?,?,?,?)",
                   ("old", 1, 1.0, "2026-10-05", json.dumps(snapshot), EVALUATOR))
        with self.assertRaises(ValueError):
            self.judge("old")
        for bad in ({"p_value": None}, {"p_value": 1.5}, {"p_value": -0.1}, {"p_value": True}, {"p_value": float("nan")},
                    {"checkpoint": 0}, {"checkpoint": True}, {"checkpoint": "40"}, {"checkpoint": 40.0}):
            with self.assertRaises(ValueError):
                self.judge(**bad)
        db.execute("DELETE FROM entrants WHERE family='fam'")
        with self.assertRaises(ValueError):
            self.judge()
        self.assertEqual((self.receipts(), self.store.ladder_state("fam", 1)), (0, {"judged": {}, "latch": None}),
                         "a judgement that cannot write its p-value writes nothing")
        self.store.freeze(self.program("moved"), day="2026-10-05")
        self.store.evaluator = "bundle-2:fills-1:exec-2"
        with self.assertRaises(ValueError):
            self.judge("moved")
        self.assertEqual(self.receipts(), 0)

    def test_a_cohort_frozen_again_starts_unjudged_and_the_archive_keeps_the_old_state(self):
        receipt = self.judge()                                   # its first checkpoint: the lines not met
        self.store.evaluator = "bundle-2:fills-1:exec-2"         # a release moved the practice evaluator
        [again] = self.store.cohort_candidates([self.program()], day="2026-12-02", in_session=True)
        self.store.freeze(again, day="2026-12-02")
        self.assertEqual(self.store.ladder_state("fam", 1), {"judged": {}, "latch": None})
        db = self.store._connect()
        own = "SELECT p_value, p_day, p_checkpoint FROM entrants WHERE id=(SELECT entrant FROM cohorts WHERE family='fam')"
        self.assertEqual(db.execute(own).fetchone(), (None, None, None), "the new cohort is its own entrant")
        [(kept, entrant)] = db.execute("SELECT ladder_state, entrant FROM cohort_archive").fetchall()
        self.assertEqual(json.loads(kept), {"judged": {"40": {"day": "2026-12-01", "receipt": receipt}}, "latch": None})
        self.judge(day="2027-02-01", p_value=0.5)
        self.assertEqual(db.execute(own).fetchone(), (0.5, "2027-02-01", 40))
        self.assertEqual(db.execute("SELECT p_value, p_checkpoint, evaluator FROM entrants WHERE id=?",
                                    (entrant,)).fetchone(), (0.003, 40, EVALUATOR), "the old entrant's stands")

    def test_a_latched_cohort_is_never_frozen_again_and_the_house_keeps_its_state(self):
        receipt = self.judge(verdict="await_validation", reasons=[], latch="validation")
        self.store.evaluator = "bundle-2:fills-1:exec-2"         # a release moved the practice evaluator
        self.assertEqual(self.store.cohort_candidates([self.program()], day="2026-12-02", in_session=True), [],
                         "its checkpoint's verdict was final: no second window for the same version")
        with self.assertRaises(ValueError):
            self.store.freeze(self.program(), day="2026-12-02")
        self.assertEqual(self.store.ladder_state("fam", 1)["latch"],
                         {"checkpoint": 40, "day": "2026-12-01", "receipt": receipt, "waits": "validation"})
        db = self.store._connect()
        self.assertEqual(db.execute("SELECT p_value, p_day, p_checkpoint, evaluator FROM entrants").fetchall(),
                         [(0.003, "2026-12-01", 40, EVALUATOR)], "its entrant's p-value stands, and it is the only one")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM cohort_archive").fetchone(), (0,))

    # ------------------------------------------------------------------ the files written before the checkpoints
    def older(self, name: str, ddl: str, **marks) -> Path:
        """A record file an earlier release wrote, with one active cohort ("kept"; `marks`: its snapshot's own)."""
        import sqlite3

        path = self.root / name
        path.mkdir()
        db = sqlite3.connect(str(path / "observe.sqlite"))
        db.executescript(ddl)
        snapshot = json.dumps(dict(self.program("kept"), practice_frozen=True, practice_evaluator=EVALUATOR, **marks))
        db.execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot) VALUES('kept', 1, 1, "
                   "'2026-10-05', ?)", (snapshot,))
        db.commit()
        db.close()
        return path

    def test_a_file_the_release_before_the_checkpoints_wrote_gains_the_columns_and_keeps_its_rows(self):
        import sqlite3

        path = self.older("before", BEFORE_CHECKPOINTS, ladder=1, practice_max_sessions=60)
        db = sqlite3.connect(str(path / "observe.sqlite"))
        db.execute("UPDATE cohorts SET evaluator=?", (EVALUATOR,))
        db.execute("INSERT INTO entrants(family, version, run_sha, evaluator, entered_at, entered_day, p_value, p_day) "
                   "VALUES('kept', 1, 'sha-kept-1', ?, 1, '2026-10-05', 0.4, '2026-10-20')", (EVALUATOR,))
        db.execute("INSERT INTO ladder_decisions(day, family, version, run_sha, inputs, stats, p_value, verdict, reasons, "
                   "binding, at) VALUES('2026-10-20', 'kept', 1, 'sha-kept-1', 'x', '{}', 0.4, 'fail', '[]', 0, 1)")
        db.execute("INSERT INTO cohort_archive(family, version, evaluator, admitted_at, first_day, snapshot, status, "
                   "archived_at) VALUES('gone', 1, 'e-old', 1, '2026-09-01', '{}', 'complete', 2)")
        db.commit()
        db.close()
        for _ in range(2):                                       # opened twice: the migration runs once
            store = ObserveStore(path, clock=lambda: 2.0)
            store.evaluator = EVALUATOR
            db = store._connect()
            for table, column in (("cohorts", "ladder_state"), ("cohort_archive", "ladder_state"),
                                  ("entrants", "p_checkpoint"), ("ladder_decisions", "checkpoint")):
                self.assertIn(column, {r[1] for r in db.execute(f"PRAGMA table_info({table})")}, (table, column))
            self.assertEqual(db.execute("SELECT p_value, p_day, p_checkpoint FROM entrants").fetchall(),
                             [(0.4, "2026-10-20", None)])
            self.assertEqual(db.execute("SELECT verdict, p_value, checkpoint FROM ladder_decisions").fetchall(),
                             [("fail", 0.4, None)])
            self.assertEqual(db.execute("SELECT family, ladder_state FROM cohort_archive").fetchall(), [("gone", None)])
            [cohort] = store.ladder_cohorts()
            self.assertEqual((cohort["family"], cohort["state"]), ("kept", {"judged": {}, "latch": None}))
            self.assertIsNone(store.decision(1)["checkpoint"])
            store.close()
        store = ObserveStore(path, clock=lambda: 3.0)
        store.evaluator = EVALUATOR
        self.addCleanup(store.close)
        receipt = store.add_decision({"day": "2026-12-01", "family": "kept", "version": 1, "run_sha": "sha-kept-1",
                                      "inputs": "y", "stats": {}, "p_value": 0.01, "verdict": "fail", "binding": False,
                                      "checkpoint": 40})
        self.assertEqual(store.ladder_state("kept", 1)["judged"], {40: {"day": "2026-12-01", "receipt": receipt}})
        self.assertEqual(store._connect().execute("SELECT p_value, p_checkpoint FROM entrants").fetchall(), [(0.01, 40)])

    def test_a_file_from_before_the_ladder_gains_its_tables_whole(self):
        ddl = BEFORE_CHECKPOINTS.split("CREATE TABLE cohort_archive")[0].replace(" evaluator TEXT,\n", "\n")
        self.assertNotIn("evaluator", ddl)
        path = self.older("a1", ddl)
        store = ObserveStore(path, clock=lambda: 2.0)
        store.evaluator = EVALUATOR
        self.addCleanup(store.close)
        db = store._connect()
        self.assertEqual(db.execute("SELECT evaluator, ladder_state FROM cohorts").fetchall(), [(EVALUATOR, None)])
        for table, column in (("cohort_archive", "ladder_state"), ("entrants", "p_checkpoint"),
                              ("ladder_decisions", "checkpoint")):
            self.assertIn(column, {r[1] for r in db.execute(f"PRAGMA table_info({table})")}, (table, column))
        self.assertEqual(store.ladder_cohorts(), [], "its cohorts are from before the ladder")
        self.assertEqual(store.ladder_state("kept", 1), {"judged": {}, "latch": None})
        with self.assertRaises(ValueError):
            store.add_decision({"day": "2026-12-01", "family": "kept", "version": 1, "inputs": "y", "stats": {},
                                "p_value": 0.01, "verdict": "fail", "binding": False, "checkpoint": 40})
        store.freeze(self.program("new"), day="2026-12-01")
        store.add_decision({"day": "2027-02-01", "family": "new", "version": 1, "run_sha": "sha-new-1", "inputs": "y",
                            "stats": {}, "p_value": 1.0, "verdict": "short", "binding": False, "checkpoint": 40})
        self.assertEqual(db.execute("SELECT p_value, p_checkpoint FROM entrants").fetchall(), [(1.0, 40)])


# ================================================================================================== the session's end
def gate_answer(pnl=120.0, p=0.01, *, level=0.02, bundle="bundle-1", **changes) -> dict:
    """The gate's record of a pre-filter read it made and judged at `level` (`Gate._prefilter_write`)."""
    return {"status": "done", "bundle": bundle, "ran_bundle": bundle, "pnl": pnl, "p": p, "level": level,
            "passed": pnl is not None and pnl >= 0 and p is not None and p <= level, **changes}


class MemoryBridge:
    """The swarm's side, in memory."""

    def __init__(self):
        self.prefilters: dict[str, dict] = {}
        self.requests: dict[str, dict] = {}
        #: The belt's reading (None: it refuses nothing), a refused promotion's reason, what a band move raises.
        self.refused: str | None = None
        self.promote_fails: str | None = None
        self.promote_raises: Exception | None = None
        self.promoted: list[dict] = []
        self.families: list[dict] = []
        self.forward: dict[str, list[dict]] = {}
        self.demoted: list[tuple[str, str]] = []
        #: L0: each family's validation verdict (True unless named); the families as the swarm's store holds them.
        self.validated: dict[str, bool | None] = {}
        self.status: dict[str, dict | None] = {}
        self.swept: list[set] = []

    def prefilter(self, run_sha):
        return self.prefilters.get(run_sha)

    def request_prefilter(self, run_sha, *, family, version, bundle, day):
        self.requests.setdefault(run_sha, {"family": family, "version": version, "bundle": bundle, "day": day})

    def sweep_prefilter(self, waiting):
        keep = set(waiting)
        self.swept.append(keep)
        gone = [sha for sha in self.requests if sha not in keep]
        for sha in gone:
            self.requests.pop(sha)
        return len(gone)

    def family_status(self, family):
        if family in self.status:
            return self.status[family]
        return {"retired": False, "band": "gym", "version": None, "proof": {}}

    def validation(self, family, version):
        return self.validated.get(family, True)

    def refusal(self, family, version, run_sha):
        return self.refused

    def promote(self, **kw):
        if self.promote_raises is not None:
            raise self.promote_raises
        if self.promote_fails:
            return self.promote_fails
        self.promoted.append(kw)
        return None

    def ladder_families(self):
        return self.families

    def forward_rows(self, family):
        return self.forward.get(family, [])

    def demote(self, family, *, why, receipt, at):
        self.demoted.append((family, why))
        return True


def ops_promotions(case: unittest.TestCase, root: Path, now: float) -> int:
    """The ladder's promotions as the budget rule's PRODUCTION reader counts them (`budget._swarm_reads`, what `gather`
    hands the no-forward-edge stop: the swarm's own band moves and the ladder's receipts, one a promotion), with its
    read of the receipts alone (`budget.ladder_promotions`) and the scoreboard's count (`scoreboard.ladder_counts`)
    held equal to it. Without the swarm's store (the in-memory bridge) that reader holds no promotion record at all:
    the receipts' read is counted."""
    from league.ops import budget, scoreboard

    errors: list[str] = []
    counted = budget.ladder_promotions(Path(root), errors)
    if (Path(root) / "swarm.sqlite").exists():
        read = budget._swarm_reads(Path(root), now, errors)["promotions"]
        case.assertEqual((errors, read is not None and len(read)), ([], len(counted)),
                         "the budget counts a promotion exactly where a receipt is settled")
    case.assertEqual((errors, scoreboard.ladder_counts(root, now)["promoted"]), ([], len(counted)))
    return len(counted)


class Killed(BaseException):
    """A House process that dies mid-write: nothing that catches `Exception` sees it."""


class NightCase(StoreCase):
    """The House's session ends, night by night. `self.days` are seventy sessions from Oct 5, 2026; a cohort holds its
    whole sixty-session record from the start, and each night reads it through that night's day."""

    def setUp(self):
        super().setUp()
        self.bridge = MemoryBridge()
        self.events, self.alerts = [], []
        self.live = SimpleNamespace(observe_store=self.store, clock=lambda: self.now[0],
                                    record=lambda kind, payload, agent=None: self.events.append((kind, payload)),
                                    alert=lambda level, text: self.alerts.append(text))
        self.ladder = L.Ladder(self.live, bridge=self.bridge)
        self.days = sessions("2026-10-05", 70)
        self.bundle = patch.object(L.Ladder, "_bundle", return_value="bundle-1")
        self.bundle.start()
        self.addCleanup(self.bundle.stop)

    def cohort(self, fid="fam", returns=None, *, first=1, tier="validated", **kw):
        """A cohort frozen at the `first`-th session, with its record of the sixty sessions from it: the edge
        (`pattern(60)`: every line met at its first checkpoint) unless `returns`."""
        days = self.days[first - 1:first + 59]
        self.store.freeze(self.program(fid, tier=tier), day=days[0])
        self.add_record(fid, 1, days, pattern(60) if returns is None else returns, **kw)

    def night(self, k, *, binding=False, missed=None, **changes):
        """The end of the k-th session: every cohort has practised each session from its first day through it (less
        `missed[family]`)."""
        day = self.days[k - 1]
        db = self.store._connect()
        for fid, first in db.execute("SELECT family, first_day FROM practice").fetchall():
            if first <= day:
                practised = len(L.sessions_between(first, day)) - (missed or {}).get(fid, 0)
                db.execute("UPDATE practice SET sessions=?, last_day=? WHERE family=?", (practised, day, fid))
        with patch.object(L.Rules, "from_constitution", return_value=rules(binding=binding, **changes)):
            return self.ladder.end_of_day(day)

    def pins(self, k):
        """The first pins of the k-th session (`cohort_candidates`): the families still in their slots."""
        return sorted(r["family"] for r in self.store.cohort_candidates([], day=self.days[k - 1], in_session=True))

    def receipts(self, fid=None):
        rows = self.store._connect().execute(
            "SELECT id, day, family, verdict, reasons, checkpoint, p_value, bh_rank, bh_size, bh_threshold, binding, stats, "
            "inputs FROM ladder_decisions ORDER BY id").fetchall()
        keys = ("id", "day", "family", "verdict", "reasons", "checkpoint", "p_value", "bh_rank", "bh_size", "bh_threshold",
                "binding", "stats", "inputs")
        out = [dict(zip(keys, r)) for r in rows]
        for r in out:
            r["reasons"], r["stats"] = json.loads(r["reasons"]), json.loads(r["stats"])
        return [r for r in out if fid is None or r["family"] == fid]

    def status(self, fid="fam"):
        return self.store._connect().execute("SELECT status, reason FROM cohorts WHERE family=?", (fid,)).fetchone()

    def entrant(self, fid="fam"):
        return self.store._connect().execute("SELECT p_value, p_day, p_checkpoint FROM entrants WHERE family=?",
                                             (fid,)).fetchone()

    def latch(self, fid="fam"):
        state = self.store._connect().execute("SELECT ladder_state FROM cohorts WHERE family=?", (fid,)).fetchone()[0]
        return (json.loads(state) if state else {}).get("latch")

    def latched(self, fid="fam", **kw):
        """A cohort latched on its first checkpoint (the 40th session's end), the gate asked."""
        self.cohort(fid, **kw)
        self.assertEqual(self.night(40)["verdicts"], {"await_prefilter": 1})
        return self.receipts(fid)[-1]


@unittest.skipUnless(HAVE, "numpy not installed")
class TheCheckpointNights(NightCase):
    def test_a_cohort_is_judged_only_at_its_checkpoints_each_once(self):
        self.cohort(returns=pattern(20, shift=3) + pattern(40, shift=13))      # an edge gone after twenty sessions
        for k in range(1, 40):
            out = self.night(k)
            self.assertEqual((out["judged"], out["verdicts"], out["practising"]), (0, {}, 1), k)
        self.assertEqual(self.receipts(), [], "no judgement before its first checkpoint")
        self.assertEqual(self.entrant(), (None, None, None), "and no p-value")
        out = self.night(40)
        self.assertEqual((out["judged"], out["verdicts"], out["practising"], out["bh_size"]), (1, {"fail": 1}, 0, 1))
        [first] = self.receipts()
        self.assertEqual((first["checkpoint"], first["verdict"], first["reasons"], first["day"]),
                         (40, "fail", ["the windows line"], self.days[39]))
        self.assertEqual((first["stats"]["alpha"], first["stats"]["sessions"], first["stats"]["calendar_sessions"]),
                         (0.004, 40, 40))
        self.assertEqual(first["stats"]["tilt"], {"raw": None, "adjusted": None}, "why a tilted p-value is 1: said")
        self.assertLessEqual({"p_adj", "perc_p", "lcb", "lines", "drift", "windows"}, set(first["stats"]))
        self.assertEqual(self.entrant(), (first["p_value"], self.days[39], 40))
        for k in range(41, 60):
            self.assertEqual(self.night(k)["judged"], 0, k)
        self.assertEqual(len(self.receipts()), 1, "nothing is judged between its checkpoints")
        self.assertEqual(self.entrant(), (first["p_value"], self.days[39], 40), "and its p-value stands")
        self.assertEqual(self.night(60)["verdicts"], {"fail": 1})
        last = self.receipts()[-1]
        self.assertEqual((last["checkpoint"], last["stats"]["alpha"], last["stats"]["sessions"]), (60, 0.05, 60))
        self.assertEqual(self.entrant(), (last["p_value"], self.days[59], 60), "its latest judged checkpoint's")
        self.assertNotEqual(last["inputs"], first["inputs"])
        out = self.night(61)
        self.assertEqual((out["judged"], out["practising"], len(self.receipts())), (0, 1, 2), "each checkpoint once")
        self.assertEqual(self.status(), ("active", None))
        self.assertEqual(self.pins(61), [], "it did not meet the lines at its last checkpoint: it ends at its window")
        self.assertEqual(self.status(), ("complete", "ladder: its practice window ended"))

    def test_each_line_fails_alone(self):
        d = self.days[:60]
        self.cohort("short", [[0.2]] * 29 + [[]] * 31)                                      # 29 program closes
        self.cohort("bound", delta=20.0, moves=market(d, 0.0, 1.5))        # an edge under the noise of a delta it holds
        self.cohort("windows", pattern(20, shift=3) + pattern(40, shift=13))
        self.cohort("drift", pattern(60, shift=12), delta=20.0, moves=market(d, 1.0, 0.75))  # the market's drift alone
        out = self.night(40, binding=True)
        self.assertEqual((out["verdicts"], out["bh_size"]), ({"short": 1, "fail": 3}, 4))
        by = {r["family"]: r for r in self.receipts()}
        self.assertEqual(by["short"]["reasons"], ["40 sessions and 29 program closes; the line is 20 and 30"])
        self.assertEqual((by["short"]["p_value"], by["short"]["stats"]["tilt"]["raw"]), (1.0, L.TILT_RECORD))
        self.assertEqual(self.entrant("short"), (1.0, self.days[39], 40), "without a full record it counts at 1")
        for name in ("bound", "windows", "drift"):
            self.assertEqual((by[name]["verdict"], by[name]["reasons"]), ("fail", [f"the {name} line"]), name)
            lines = by[name]["stats"]["lines"]
            self.assertEqual([k for k, ok in lines.items() if not ok], [name])
            self.assertLessEqual(by[name]["p_value"], by[name]["bh_threshold"], "Benjamini-Hochberg rejects it")
        self.assertGreater(by["bound"]["p_value"], 0.004, "the tilted p-value is over the first checkpoint's alpha")
        self.assertLessEqual(by["bound"]["stats"]["perc_p"], 0.05, "though the percentile bound is above zero")
        self.assertEqual(by["drift"]["stats"]["tilt"]["adjusted"], L.TILT_MEAN)
        for name in by:
            self.assertEqual((self.status(name), self.latch(name)), (("active", None), None), name)
        self.assertEqual((self.bridge.requests, self.bridge.promoted), ({}, []))

    def test_the_fdr_line_fails_alone_over_every_entrant_of_its_window(self):
        self.cohort()
        for i in range(3):                                   # entrants with no checkpoint yet: p = 1 each
            self.store.freeze(self.program(f"new{i}"), day=self.days[38])
        db = self.store._connect()
        # ... and entrants whose cohorts ended without a judged checkpoint: enough of them that the bar (0.10 over the
        # family) is under the smallest p-value 10,000 draws can give (1 / 10,001).
        for i in range(1100):
            db.execute("INSERT INTO entrants(family, version, evaluator, entered_at, entered_day) VALUES(?,?,?,?,?)",
                       (f"gone{i}", 1, EVALUATOR, 1.0, self.days[0]))
        out = self.night(40, binding=True)
        self.assertEqual(out["bh_size"], 1104)
        self.assertLess(0.10 / out["bh_size"], 1.0 / 10001)
        [fam] = self.receipts("fam")
        self.assertEqual((fam["verdict"], fam["reasons"], fam["p_value"]), ("fail", ["the fdr line"], FLOOR))
        self.assertTrue(all(fam["stats"]["lines"].values()), "L1-L4 are met")
        self.assertEqual((self.bridge.requests, self.latch()), ({}, None))

    def test_the_fdr_reads_each_entrant_at_its_latest_checkpoint_and_one_never_judged_at_one(self):
        self.cohort()                                        # p at the floor at its first checkpoint
        self.cohort("slow", pattern(60, shift=10))           # about 0.05 at its first, about 0.01 at its last
        self.cohort("late", first=30)                        # its first checkpoint is thirty sessions on
        db = self.store._connect()
        # A p-value no checkpoint wrote (a release before the checkpoints wrote one every session) is not a judged one.
        db.execute("UPDATE entrants SET p_value=0.00001, p_day=? WHERE family='late'", (self.days[38],))
        out = self.night(40)
        self.assertEqual((out["verdicts"], out["bh_size"], out["practising"]), ({"await_prefilter": 1, "fail": 1}, 3, 1))
        fam, slow = self.receipts("fam")[0], self.receipts("slow")[0]
        self.assertEqual((fam["bh_rank"], slow["bh_rank"]), (1, 2), "the entrant never judged counts at 1: the last rank")
        self.assertEqual(slow["bh_threshold"], slow["p_value"], "the largest p-value the procedure rejects")
        self.assertEqual(slow["reasons"], ["the bound line", "the drift line"])
        self.assertEqual(self.entrant("late"), (0.00001, self.days[38], None), "no judgement wrote to it")
        self.bridge.prefilters["sha-fam-1"] = gate_answer(-5.0)
        self.assertEqual(self.night(41)["verdicts"], {"prefilter_negative": 1})
        for k in range(42, 60):
            self.night(k)
        self.assertEqual(self.entrant()[::2], (FLOOR, 40), "never rewritten after its cohort ended")
        out = self.night(60)
        self.assertEqual((out["verdicts"], out["bh_size"]), ({"await_prefilter": 1}, 3))
        last = self.receipts("slow")[-1]
        self.assertEqual((last["checkpoint"], last["bh_rank"]), (60, 2), "the ended entrant still counts, at its own")
        self.assertEqual(self.entrant("slow"), (last["p_value"], self.days[59], 60))
        self.assertLess(last["p_value"], slow["p_value"])

    def test_an_old_entrant_leaves_the_window_and_a_judged_cohort_is_always_in_its_own_family(self):
        self.cohort()
        db = self.store._connect()
        for i in range(40):
            self.store.freeze(self.program(f"old{i}"), day="2026-05-01")
            db.execute("UPDATE entrants SET entered_day='2026-05-01' WHERE family=?", (f"old{i}",))
            self.store.close_cohort(f"old{i}", 1, status="failed", day="2026-07-01", reason="r")
        self.assertEqual(self.night(40)["bh_size"], 1)
        self.cohort("aged", pattern(60, shift=10))
        db.execute("UPDATE entrants SET entered_day='2026-05-01' WHERE family='aged'")   # outside the trailing 90 days
        out = self.night(60)
        self.assertEqual((out["bh_size"], out["entrants"]), (2, 2), "the latched one, and the one judged tonight")
        self.assertEqual(self.receipts("aged")[-1]["verdict"], "await_prefilter")

    def test_a_missed_first_checkpoint_night_is_judged_at_the_next_sessions_end(self):
        self.cohort()
        self.night(39)                                       # the House was down at the 40th session's close
        out = self.night(41)
        self.assertEqual(out["verdicts"], {"await_prefilter": 1})
        [r] = self.receipts()
        self.assertEqual((r["checkpoint"], r["day"], r["stats"]["alpha"]), (40, self.days[40], 0.004))
        self.assertEqual((r["stats"]["sessions"], r["stats"]["closes"]), (41, 82), "on the record through that session")
        self.assertEqual(self.latch()["day"], self.days[40])
        self.assertEqual(self.night(42)["judged"], 0, "once")

    def test_a_missed_last_checkpoint_night_holds_the_cohort_to_be_judged(self):
        self.cohort("slow", pattern(60, shift=10))
        self.night(40)
        self.night(59)                                       # the House was down at the 60th session's close
        self.assertEqual(self.pins(61), ["slow"], "its last checkpoint is not judged yet: held past its window")
        out = self.night(61)
        self.assertEqual(out["verdicts"], {"await_prefilter": 1})
        last = self.receipts()[-1]
        self.assertEqual((last["checkpoint"], last["day"], last["stats"]["alpha"], last["stats"]["calendar_sessions"]),
                         (60, self.days[60], 0.05, 61))
        self.assertEqual(self.night(62)["judged"], 0)
        self.assertEqual(self.pins(62), ["slow"], "now latched: held for its answer")

    def test_a_first_checkpoint_due_only_at_the_windows_end_is_judged_once_at_the_last_alpha(self):
        missed = {"under": 21, "at": 20}                     # 39 sessions practised by the 60th, and exactly 40
        for fid in missed:
            self.cohort(fid, pattern(60, shift=10))
        for k in range(38, 60):
            self.assertEqual(self.night(k, missed=missed)["judged"], 0, k)
        self.assertEqual(self.night(60, missed=missed)["verdicts"], {"await_prefilter": 2})
        for fid, sessions_practised in (("under", 39), ("at", 40)):
            [r] = self.receipts(fid)
            self.assertEqual((r["checkpoint"], r["stats"]["alpha"], r["stats"]["sessions"]), (60, 0.05, sessions_practised))
            self.assertEqual(sorted(self.store.ladder_state(fid, 1)["judged"]), [60], "the first is never judged")
        self.assertEqual(self.night(61, missed=missed)["judged"], 0)

    def test_one_cohorts_error_stops_no_others_judgement(self):
        self.cohort()
        self.cohort("two")
        asked = self.bridge.request_prefilter

        def request(sha, **kw):
            if sha == "sha-fam-1":
                raise RuntimeError("the store is locked")
            return asked(sha, **kw)

        self.bridge.request_prefilter = request
        out = self.night(40, binding=True)
        self.assertEqual(out["verdicts"], {"error": 1, "await_prefilter": 1})
        self.assertIn("fam@1", self.alerts[0])
        self.assertEqual(self.bridge.promoted, [])
        self.assertEqual((self.latch(), self.receipts("fam")), (None, []), "an errored attempt is no judgement")
        self.assertEqual(self.entrant(), (None, None, None))
        self.bridge.request_prefilter = asked
        self.assertEqual(self.night(41)["verdicts"], {"await_prefilter": 1}, "judged again at the next session's end")
        self.assertEqual(self.receipts("fam")[0]["stats"]["sessions"], 41)

    def test_one_cohorts_read_error_stops_neither_another_nor_the_demotions(self):
        self.cohort()
        self.cohort("two")
        rows = self.store.ladder_rows

        def broken(family, version, **kw):
            if family == "fam":
                raise __import__("sqlite3").OperationalError("database is locked")
            return rows(family, version, **kw)

        self.bridge.families = [{"family": "old", "band": "probe", "version": 1, "promoted_at": None}]
        self.bridge.forward["old"] = [{"day": d, "source": "real", "pnl": -5.0, "max_loss": 100.0, "version": 1}
                                      for d in self.days[:21]]
        with patch.object(self.store, "ladder_rows", side_effect=broken):
            out = self.night(40, binding=True)
        self.assertEqual(out["verdicts"], {"error": 1, "await_prefilter": 1})
        self.assertEqual([d["family"] for d in out["demoted"]], ["old"])
        self.assertIn("fam@1", self.alerts[0])

    def test_a_cohort_under_another_evaluator_is_not_judged(self):
        self.cohort()
        self.store.evaluator = "another"
        out = self.night(40)
        self.assertEqual((out["judged"], out["practising"], self.receipts()), (0, 0, []))

    def test_a_snapshot_without_a_run_sha_that_meets_the_lines_ends_blocked_for_good(self):
        """A checkpoint that meets L1-L5 is final. With no run sha nothing can be asked of the gate, so the cohort
        ends there, `failed`: never judged again at its last checkpoint, never started again by a release."""
        self.cohort()
        db = self.store._connect()
        snap = json.loads(db.execute("SELECT snapshot FROM cohorts").fetchone()[0])
        db.execute("UPDATE cohorts SET snapshot=?", (json.dumps({k: v for k, v in snap.items() if k != "run_sha"}),))
        self.assertEqual(self.night(40, binding=True)["verdicts"], {"blocked": 1})
        self.assertEqual((self.latch(), self.status(), self.bridge.requests),
                         (None, ("failed", "ladder: its snapshot names no run sha"), {}))
        self.assertEqual(self.receipts()[0]["reasons"], ["its snapshot names no run sha"])
        self.assertEqual(self.entrant()[2], 40, "its p-value is written with its receipt and its ending")
        out = self.night(60, binding=True)
        self.assertEqual((out["judged"], out["practising"], len(self.receipts())), (0, 0, 1), "never judged again")
        program = {k: v for k, v in self.program().items() if k != "run_sha"}
        for evaluator in ("bundle-2:fills-1:exec-2", EVALUATOR):
            self.store.evaluator = evaluator
            self.assertEqual(self.store.cohort_candidates([program], day=self.days[45], in_session=True), [])
            with self.assertRaises(ValueError):
                self.store.freeze(program, day=self.days[45])


@unittest.skipUnless(HAVE, "numpy not installed")
class TheLatchAndTheAnswer(NightCase):
    def test_a_checkpoint_that_meets_the_lines_is_latched_and_its_answer_is_read_at_a_later_session(self):
        self.bridge.prefilters["sha-fam-1"] = gate_answer()  # the gate's record is already there
        self.cohort()
        out = self.night(40, binding=True)
        self.assertEqual((out["verdicts"], out["waiting"]), ({"await_prefilter": 1}, 0))
        [r] = self.receipts()
        self.assertEqual((r["checkpoint"], r["reasons"]), (40, ["the pre-filter read is requested from the gate"]))
        self.assertEqual(self.latch(), {"checkpoint": 40, "day": self.days[39], "receipt": r["id"], "waits": "prefilter"})
        self.assertEqual(self.bridge.requests["sha-fam-1"], {"family": "fam", "version": 1, "bundle": "bundle-1",
                                                             "day": self.days[39]})
        self.assertEqual((self.bridge.promoted, self.status()), ([], ("active", None)), "nothing on its own night")
        with patch.object(L.Rules, "from_constitution", return_value=rules(binding=True)):
            again = self.ladder.end_of_day(self.days[39])    # the same session's end, run again
        self.assertEqual((again["verdicts"], again["waiting"], len(self.receipts())), ({}, 1, 1))
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"promoted": 1})

    def test_recording_writes_would_promote_once_and_the_cohort_practises_on_to_its_window(self):
        first = self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.bridge.refused = "its version was demoted (a loss at 1.5x, or the drift screen failed)"
        out = self.night(41)
        self.assertEqual((out["verdicts"], out["judged"]), ({"would_promote": 1}, 0))
        answer = self.receipts()[-1]
        self.assertEqual((answer["verdict"], answer["checkpoint"], answer["binding"], answer["day"]),
                         ("would_promote", None, 0, self.days[40]))
        self.assertEqual((answer["p_value"], answer["inputs"], answer["bh_rank"], answer["bh_size"], answer["bh_threshold"]),
                         (first["p_value"], first["inputs"], first["bh_rank"], first["bh_size"], first["bh_threshold"]),
                         "its checkpoint's figures: no line is judged again")
        self.assertEqual(answer["stats"]["latch"], {"checkpoint": 40, "day": self.days[39], "receipt": first["id"]})
        self.assertEqual(answer["stats"]["answer"], {
            "waited": 1, "prefilter": {"passed": True, "pnl": 120.0, "p": 0.01, "level": 0.02},
            "belt": {"read": True, "refusal": self.bridge.refused}}, "the belt's reading is recorded and refuses nothing")
        self.assertEqual({k: answer["stats"][k] for k in first["stats"]}, first["stats"])
        self.assertEqual((self.bridge.promoted, self.status()), ([], ("active", None)), "it keeps practising")
        self.assertEqual(self.latch()["waits"], None)
        self.assertEqual(self.latch()["answer"], {"day": self.days[40], "receipt": answer["id"], "verdict": "would_promote"})
        self.assertEqual(self.bridge.requests, {}, "its request is swept")
        for k in range(42, 62):
            out = self.night(k)
            self.assertEqual((out["judged"], out["verdicts"], out["recorded"], out["waiting"]), (0, {}, 1, 0), k)
        self.assertEqual([r["verdict"] for r in self.receipts()], ["await_prefilter", "would_promote"],
                         "once, and no further judgement: not at its last checkpoint either")
        self.assertEqual(self.entrant(), (first["p_value"], self.days[39], 40))
        self.assertEqual(self.pins(60), ["fam"])
        self.assertEqual(self.pins(61), [])
        self.assertEqual(self.status(), ("complete", "ladder: its practice window ended"))

    def test_the_latch_survives_worse_later_sessions(self):
        self.cohort(returns=pattern(40) + [[-0.9] * 6] * 20)     # every line met at forty sessions, then ruin
        self.assertEqual(self.night(40)["verdicts"], {"await_prefilter": 1})
        for k in (41, 42, 43):
            self.assertEqual(self.night(k)["waiting"], 1)
        [cohort] = self.store.ladder_cohorts()
        practice, rows = self.store.ladder_rows("fam", 1, evaluator=EVALUATOR, first_day=self.days[0], through=self.days[42])
        now = L.judge(cohort, practice, rows, through=self.days[42], rules=rules(), checkpoint=60)
        self.assertEqual((now["sessions"], now["p"], now["lines"]["bound"], now["lines"]["drift"]), (43, 1.0, False, False),
                         "judged on its record through the session before its answer, it would meet no line at any alpha")
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.assertEqual(self.night(44)["verdicts"], {"would_promote": 1})
        first, answer = self.receipts()
        self.assertEqual((answer["p_value"], answer["stats"]["lines"], answer["stats"]["sessions"], answer["stats"]["mean"]),
                         (first["p_value"], first["stats"]["lines"], 40, first["stats"]["mean"]),
                         "the checkpoint's verdict is final: nothing practised after it is evidence")
        self.assertTrue(all(answer["stats"]["lines"].values()))
        self.assertEqual(self.entrant(), (first["p_value"], self.days[39], 40))

    def test_binding_the_latch_survives_worse_later_sessions_too(self):
        self.cohort(returns=pattern(40) + [[-0.9] * 6] * 20)
        first = self.night(40, binding=True) and self.receipts()[-1]
        for k in (41, 42, 43):
            self.assertEqual(self.night(k, binding=True)["waiting"], 1)
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.assertEqual(self.night(44, binding=True)["verdicts"], {"promoted": 1})
        self.assertEqual([r["verdict"] for r in self.receipts()], ["await_prefilter", "promote"])
        self.assertEqual((self.status()[0], self.bridge.promoted[0]["typical"]), ("promoted", first["stats"]["typical"]))

    def test_the_answer_is_read_one_session_later(self):
        self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.assertEqual(self.night(41)["verdicts"], {"would_promote": 1})
        self.assertEqual((self.receipts()[-1]["stats"]["answer"]["waited"], self.alerts), (1, []))

    def test_the_answer_is_read_five_sessions_later_and_the_house_alerts_once(self):
        self.latched()
        self.assertEqual((self.night(41)["waiting"], self.alerts), (1, []), "one session is the plan")
        self.assertEqual(self.night(42)["waiting"], 1)
        [alert] = self.alerts
        self.assertIn("fam@1", alert)
        self.assertIn("waited 2 sessions for the pre-filter's answer", alert)
        self.assertIn("after 5", alert)
        for k in (43, 44):
            self.assertEqual(self.night(k)["waiting"], 1)
        self.assertEqual(len(self.alerts), 1, "once")
        self.assertEqual(self.latch()["told"], self.days[41])
        self.assertEqual(len(self.receipts()), 1, "a waiting night writes no receipt")
        self.assertIn("sha-fam-1", self.bridge.requests, "its request stays while it waits")
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.assertEqual(self.night(45)["verdicts"], {"would_promote": 1}, "the fifth session is inside the wait")
        self.assertEqual(self.receipts()[-1]["stats"]["answer"]["waited"], 5)

    def test_no_answer_within_the_wait_ends_it_unpromoted(self):
        self.latched()
        for k in (41, 42, 43, 44):
            self.assertEqual(self.night(k, binding=True)["waiting"], 1)
        out = self.night(45, binding=True)
        self.assertEqual(out["verdicts"], {"unanswered": 1})
        self.assertEqual(self.status(), ("complete", "ladder: no pre-filter answer within 5 sessions of its checkpoint"))
        last = self.receipts()[-1]
        self.assertEqual((last["verdict"], last["checkpoint"], last["stats"]["answer"]), ("unanswered", None, {"waited": 5}))
        self.assertEqual(self.latch()["answer"]["verdict"], "unanswered")
        self.assertEqual((self.bridge.requests, self.bridge.promoted), ({}, []))
        self.bridge.prefilters["sha-fam-1"] = gate_answer()  # an answer that comes after the wait promotes nothing
        out = self.night(46, binding=True)
        self.assertEqual((out["verdicts"], out["waiting"], self.bridge.promoted), ({}, 0, []))

    def test_a_shorter_wait_in_the_table_ends_it_sooner(self):
        self.latched()
        self.assertEqual(self.night(41, answer_sessions=2)["waiting"], 1)
        self.assertEqual(self.night(42, answer_sessions=2)["verdicts"], {"unanswered": 1})
        self.assertEqual(self.alerts, [], "it ended at the session it would have alerted at")

    def test_a_latch_no_session_end_read_inside_the_wait_ends_unread(self):
        self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer()  # the gate answered, but the House was down for six closes
        out = self.night(46, binding=True)
        self.assertEqual((out["verdicts"], self.bridge.promoted), ({"unanswered": 1}, []))
        self.assertEqual(self.status(), ("complete", "ladder: no session's end read its answer within 5 sessions of its "
                                                     "checkpoint"))

    def test_a_read_the_gate_could_not_make_ends_it_the_same_way(self):
        self.latched()
        self.bridge.prefilters["sha-fam-1"] = {"status": "failed", "bundle": "bundle-1", "tries": 3, "why": "x"}
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"unanswered": 1})
        self.assertEqual(self.status(), ("complete", "ladder: the gate could not make its pre-filter read"))
        self.latched("two")
        self.bridge.prefilters["sha-two-1"] = {"status": "failed", "bundle": "bundle-0", "tries": 3, "why": "x"}
        self.assertEqual(self.night(41)["waiting"], 1, "out of tries on another bundle: this one is still asked")

    def test_a_read_that_does_not_pass_on_its_pnl_or_on_its_p_fails_the_cohort_for_good(self):
        reads = {"pnl": gate_answer(-0.01, 0.0005), "p": gate_answer(50.0, 0.0201), "no-p": gate_answer(50.0, None),
                 "flag": gate_answer(50.0, 0.01, passed=False), "figures": gate_answer(50.0, 0.03, passed=True),
                 "looser": gate_answer(50.0, 0.03, level=0.05)}
        for name in reads:
            self.cohort(name)
        self.assertEqual(self.night(40)["verdicts"], {"await_prefilter": 6})
        for name, read in reads.items():
            self.bridge.prefilters[f"sha-{name}-1"] = read
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"prefilter_negative": 6})
        for name in reads:
            self.assertEqual(self.status(name), ("failed", "ladder: the pre-filter read did not pass its line"), name)
            last = self.receipts(name)[-1]
            self.assertEqual((last["verdict"], last["checkpoint"], last["stats"]["answer"]["prefilter"]["passed"]),
                             ("prefilter_negative", None, False), name)
        self.assertEqual(self.receipts("pnl")[-1]["stats"]["answer"]["prefilter"],
                         {"passed": False, "pnl": -0.01, "p": 0.0005, "level": 0.02})
        self.assertEqual((self.bridge.promoted, self.bridge.requests), ([], {}))

    def test_the_tables_level_holds_when_it_is_the_stricter(self):
        self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer(50.0, 0.01)        # passed at the gate's 0.02
        self.assertEqual(self.night(41, binding=True, prefilter_p=0.005)["verdicts"], {"prefilter_negative": 1})
        self.assertEqual(self.receipts()[-1]["stats"]["answer"]["prefilter"]["level"], 0.005)

    def test_a_read_at_the_line_passes(self):
        self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer(0.0, 0.02)
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"promoted": 1})

    def test_a_record_from_before_the_line_or_on_another_bundle_is_no_answer_and_is_asked_for_again(self):
        self.latched()
        self.latched("two")
        self.bridge.requests.clear()
        self.bridge.prefilters["sha-fam-1"] = {"status": "done", "passed": True, "pnl": 120.0, "bundle": "bundle-1",
                                               "ran_bundle": "bundle-1"}        # only the sign of its P&L was read
        self.bridge.prefilters["sha-two-1"] = gate_answer(bundle="bundle-0")
        out = self.night(41, binding=True)
        self.assertEqual((out["verdicts"], out["waiting"], self.bridge.promoted), ({}, 2, []))
        self.assertEqual({sha: r["bundle"] for sha, r in self.bridge.requests.items()},
                         {"sha-fam-1": "bundle-1", "sha-two-1": "bundle-1"})
        self.bridge.prefilters["sha-two-1"] = gate_answer(ran_bundle="bundle-0")
        self.assertEqual(self.night(42, binding=True)["waiting"], 2, "run on another bundle than the one asked for")
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.assertEqual(self.night(43, binding=True)["verdicts"], {"promoted": 1})

    # ------------------------------------------------------------------ L0: the Validation line (the WP6 review)
    def test_a_version_that_did_not_meet_the_validation_line_fails_and_asks_the_gate_nothing(self):
        self.cohort()
        self.bridge.validated["fam"] = False
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.assertEqual(self.night(40, binding=True)["verdicts"], {"validation_failed": 1})
        self.assertEqual(self.bridge.promoted, [])
        self.assertEqual(self.bridge.requests, {}, "no pre-filter read is asked for")
        self.assertEqual(self.status(), ("failed", "ladder: its version did not meet the Validation line"))
        [r] = self.receipts()
        self.assertEqual((r["verdict"], r["checkpoint"], self.latch()), ("validation_failed", 40, None))
        self.assertEqual(self.entrant()[2], 40, "its checkpoint was judged: it stays a trial at that p-value")

    def test_a_train_entrant_never_validated_waits_and_is_still_a_trial(self):
        self.cohort()
        self.store.freeze(self.program("other", tier="train"), day=self.days[0])
        self.bridge.validated["fam"] = None
        out = self.night(40, binding=True)
        self.assertEqual((out["verdicts"], out["bh_size"], out["practising"]), ({"await_validation": 1}, 2, 1))
        self.assertEqual(self.status(), ("active", None), "it keeps practising")
        self.assertEqual(self.latch()["waits"], "validation")
        self.assertEqual((self.bridge.requests, self.bridge.promoted), ({}, []))
        out = self.night(41, binding=True)
        self.assertEqual((out["waiting"], out["verdicts"], len(self.receipts())), (1, {}, 1))
        self.bridge.validated["fam"] = True              # the tournament validated it since: the gate is asked
        out = self.night(42, binding=True)
        self.assertEqual((out["waiting"], self.latch()["waits"]), (1, "prefilter"))
        self.assertEqual(self.bridge.requests["sha-fam-1"]["day"], self.days[41])
        self.assertIn("waited 2 sessions for the pre-filter's answer", self.alerts[0])
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.assertEqual(self.night(43, binding=True)["verdicts"], {"promoted": 1})
        self.assertEqual(self.receipts()[-1]["stats"]["answer"]["waited"], 3, "both waits count from the checkpoint")

    def test_a_validation_that_comes_and_fails_ends_the_latch_failed(self):
        self.cohort()
        self.bridge.validated["fam"] = None
        self.night(40)
        self.bridge.validated["fam"] = False
        self.assertEqual(self.night(41)["verdicts"], {"validation_failed": 1})
        self.assertEqual(self.status(), ("failed", "ladder: its version did not meet the Validation line"))
        last = self.receipts()[-1]
        self.assertEqual((last["verdict"], last["checkpoint"], last["stats"]["latch"]["checkpoint"]),
                         ("validation_failed", None, 40))
        self.assertEqual(self.bridge.requests, {})

    def test_both_waits_together_end_at_the_limit(self):
        self.cohort()
        self.cohort("late")
        self.bridge.validated.update(fam=None, late=None)
        self.night(40)
        for k in (41, 42, 43):
            self.assertEqual(self.night(k)["waiting"], 2)
        self.assertEqual(len(self.alerts), 2, "one alert a latch")
        self.assertIn("for its Validation verdict", self.alerts[0])
        self.bridge.validated["late"] = True             # validated at the fourth session: one session left for the gate
        self.assertEqual(self.night(44)["waiting"], 2)
        out = self.night(45)
        self.assertEqual(out["verdicts"], {"unanswered": 2})
        self.assertEqual(self.status(), ("complete", "ladder: no Validation verdict within 5 sessions of its checkpoint"))
        self.assertEqual(self.status("late"),
                         ("complete", "ladder: no pre-filter answer within 5 sessions of its checkpoint"))
        self.assertEqual(len(self.alerts), 2)

    def test_no_swarm_store_promotes_nothing(self):
        self.cohort()
        self.ladder.bridge = None
        self.assertEqual(self.night(40, binding=True)["verdicts"], {"await_validation": 1})
        self.assertEqual(self.receipts()[-1]["reasons"], ["no swarm store to ask"])
        for k in (41, 42, 43, 44):
            self.assertEqual(self.night(k, binding=True)["waiting"], 1)
        self.assertEqual(self.night(45, binding=True)["verdicts"], {"unanswered": 1})
        self.assertEqual(self.status()[0], "complete")

    # ------------------------------------------------------------------ the last checkpoint and the window
    def test_the_last_checkpoints_answer_is_read_past_the_window(self):
        for fid in ("rec", "bind"):
            self.cohort(fid, pattern(60, shift=10))          # under the first alpha at forty, met at sixty
        self.assertEqual(self.night(40)["verdicts"], {"fail": 2})
        self.night(59)
        self.assertEqual(self.night(60)["verdicts"], {"await_prefilter": 2})
        self.assertEqual(self.latch("rec")["checkpoint"], 60)
        self.assertEqual(self.pins(61), ["bind", "rec"], "latched: kept in its slot past its window")
        self.bridge.prefilters["sha-rec-1"] = gate_answer()
        self.assertEqual(self.night(61)["verdicts"], {"would_promote": 1})
        self.assertEqual(self.pins(62), ["bind"], "its answer is read: its window is over")
        self.assertEqual(self.status("rec"), ("complete", "ladder: its practice window ended"))
        self.bridge.prefilters["sha-bind-1"] = gate_answer()
        self.assertEqual(self.night(62, binding=True)["verdicts"], {"promoted": 1})
        self.assertEqual(self.status("bind")[0], "promoted")
        self.assertEqual(self.pins(63), [])

    def test_a_latch_past_the_window_is_held_to_the_waits_limit_and_no_longer(self):
        self.cohort("slow", pattern(60, shift=10))
        self.night(40)
        self.night(59)
        self.night(60)
        for k in (61, 62, 63, 64, 65):
            self.assertEqual(self.pins(k), ["slow"], k)
        held = self.store._connect().execute("SELECT status FROM cohorts").fetchone()[0]
        self.assertEqual(held, "active")
        self.assertEqual(self.pins(66), [], "the ladder ends it at the 65th session's end; the pins never hold it longer")
        self.assertEqual(self.status("slow"), ("complete", "ladder: its latch had no answer within the sessions it may wait"))

    # ------------------------------------------------------------------ binding: the belt, the band, the receipt
    def promotions(self):
        """The ladder promotions the budget rule and the scoreboard count (`league/ops`, their own readers)."""
        return ops_promotions(self, self.root, self.now[0])

    def test_binding_it_promotes_the_practised_program_with_its_receipt(self):
        first = self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"promoted": 1})
        [promotion] = self.bridge.promoted
        receipt = self.receipts()[-1]
        self.assertEqual(promotion["receipt"], receipt["id"])
        self.assertEqual((promotion["family"], promotion["version"], promotion["snapshot"]["code"]), ("fam", 1, CODE))
        self.assertEqual(promotion["typical"], first["stats"]["typical"])
        self.assertEqual((receipt["verdict"], receipt["checkpoint"], receipt["binding"], receipt["p_value"]),
                         ("promote", None, 1, first["p_value"]))
        self.assertEqual(receipt["reasons"], ["every line met and the pre-filter passed: promoted to Probe"])
        self.assertEqual(self.status(), ("promoted", f"ladder: promoted to Probe (receipt {receipt['id']})"))
        self.assertEqual(self.latch()["answer"], {"day": self.days[40], "receipt": receipt["id"], "verdict": "promote"})
        self.assertNotIn("sha-fam-1", self.bridge.requests)
        self.assertEqual(self.events[-1], ("live.band", {"family": "fam", "from": "gym", "to": "probe", "version": 1,
                                                         "receipt": receipt["id"], "why": "the forward ladder promoted it"}))
        self.assertEqual((self.promotions(), len(self.receipts())), (1, 2))

    def test_the_belt_and_a_refused_promotion_fail_the_cohort(self):
        self.latched()
        self.latched("two")
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.bridge.refused = "the family retired"
        out = self.night(41, binding=True)
        self.assertEqual((out["verdicts"], out["waiting"]), ({"blocked": 1}, 1))
        self.assertEqual(self.status(), ("failed", "ladder: the family retired"))
        self.assertEqual(self.receipts("fam")[-1]["reasons"], ["the ladder's belt: the family retired"])
        self.bridge.prefilters["sha-two-1"] = gate_answer()
        self.bridge.refused, self.bridge.promote_fails = None, "the family is at probe, not in the Gym band"
        self.assertEqual(self.night(42, binding=True)["verdicts"], {"blocked": 1})
        last = self.receipts("two")[-1]
        self.assertEqual((last["verdict"], last["reasons"]), ("blocked", [self.bridge.promote_fails]),
                         "the pending receipt ends blocked")
        self.assertEqual(self.status("two"), ("failed", "ladder: the family is at probe, not in the Gym band"))
        self.assertEqual(self.latch("two")["answer"]["verdict"], "blocked")
        self.assertEqual((self.promotions(), self.bridge.promoted, self.events), (0, [], []))

    def test_a_belt_that_cannot_be_read_is_read_again_and_never_fails_the_cohort(self):
        from league.swarm.bands import BELT_UNREAD

        self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        for k, why in zip((41, 42), BELT_UNREAD):
            self.bridge.refused = why
            out = self.night(k, binding=True)
            self.assertEqual((out["verdicts"], out["waiting"]), ({"error": 1}, 0), why)
            self.assertEqual((self.status(), self.latch()["waits"]), (("active", None), "prefilter"), why)
            self.assertIn(f"the ladder's belt: {why}", self.alerts[-1])
            self.assertIn("read again at the next session's end", self.alerts[-1])
        self.assertEqual((len(self.receipts()), self.bridge.promoted), (1, []), "no receipt, no promotion, no failure")
        self.bridge.refused = None
        self.assertEqual(self.night(43, binding=True)["verdicts"], {"promoted": 1})
        self.latched("two")
        self.bridge.prefilters["sha-two-1"] = gate_answer()
        self.bridge.refused = BELT_UNREAD[0]
        for k in (41, 42, 43, 44, 45):
            self.assertEqual(self.night(k, binding=True)["verdicts"], {"error": 1}, k)
        self.assertEqual(self.night(46, binding=True)["verdicts"], {"unanswered": 1})
        self.assertEqual(self.status("two")[0], "complete", "unread to the end of its wait: unpromoted, never failed")

    def test_recording_an_unread_belt_is_recorded_as_unread(self):
        from league.swarm.bands import BELT_UNREAD

        self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.bridge.refused = BELT_UNREAD[1]
        self.assertEqual(self.night(41)["verdicts"], {"would_promote": 1})
        self.assertEqual(self.receipts("fam")[-1]["stats"]["answer"]["belt"], {"read": False, "refusal": None})

    def test_a_band_move_that_raised_voids_its_receipt_and_the_answer_is_read_again(self):
        self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.bridge.promote_raises = __import__("sqlite3").OperationalError("database is locked")
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"error": 1})
        void = self.receipts()[-1]
        self.assertEqual((void["verdict"], void["reasons"]),
                         (L.PROMOTE_VOID, ["its band move raised and the swarm's store holds no band of it"]))
        self.assertEqual((self.promotions(), self.status(), self.latch()["waits"], self.events),
                         (0, ("active", None), "prefilter", []), "no promotion is counted, and the cohort is not failed")
        self.assertIn("fam@1's answer", self.alerts[-1])
        self.bridge.promote_raises = None
        self.assertEqual(self.night(42, binding=True)["verdicts"], {"promoted": 1})
        self.assertEqual([r["verdict"] for r in self.receipts()], ["await_prefilter", L.PROMOTE_VOID, "promote"])
        self.assertEqual((self.promotions(), self.bridge.promoted[0]["receipt"]), (1, self.receipts()[-1]["id"]))

    def test_a_band_move_that_raised_after_it_landed_is_settled(self):
        self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        promote = self.bridge.promote

        def lands_then_raises(**kw):
            promote(**kw)
            self.bridge.status["fam"] = {"retired": False, "band": "probe", "version": 1,
                                         "proof": {"route": "ladder", "run_sha": "sha-fam-1", "receipt": kw["receipt"]}}
            raise RuntimeError("the connection dropped after the commit")

        self.bridge.promote = lands_then_raises
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"promoted": 1})
        self.assertEqual((self.receipts()[-1]["verdict"], self.status()[0], self.promotions()), ("promote", "promoted", 1))

    def test_a_band_move_whose_outcome_cannot_be_read_stays_pending_and_is_no_promotion(self):
        self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        status = self.bridge.family_status
        calls = []

        def unreadable_after_the_move(family):
            calls.append(family)
            if self.bridge.promote_raises is not None and len(calls) > 1:
                raise RuntimeError("the store is locked")
            return status(family)

        self.bridge.family_status = unreadable_after_the_move
        self.bridge.promote_raises = RuntimeError("the store is locked")
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"error": 1})
        pending = self.receipts()[-1]
        self.assertEqual((pending["verdict"], self.promotions(), self.status()), (L.PROMOTE_PENDING, 0, ("active", None)))
        # The band did land: the next session's end finds it by this receipt and settles it.
        self.bridge.family_status, self.bridge.promote_raises = status, None
        self.bridge.status["fam"] = {"retired": False, "band": "probe", "version": 1,
                                     "proof": {"route": "ladder", "run_sha": "sha-fam-1", "receipt": pending["id"]}}
        out = self.night(42, binding=True)
        self.assertEqual((out["ended"], out["verdicts"]), ({"promoted": 1}, {}))
        self.assertEqual((self.receipts()[-1]["verdict"], self.promotions(), self.status()[0]), ("promote", 1, "promoted"))

    def test_a_promotion_whose_house_writes_failed_is_made_good_at_the_next_session_end(self):
        self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        settle = self.store.settle_answer

        def locked(receipt, verdict, *a, **kw):
            if verdict == "promote":
                raise __import__("sqlite3").OperationalError("database is locked")
            return settle(receipt, verdict, *a, **kw)

        with patch.object(self.store, "settle_answer", side_effect=locked):
            self.assertEqual(self.night(41, binding=True)["verdicts"], {"error": 1})
        [promotion] = self.bridge.promoted                   # the swarm's band was written
        pending = self.receipts()[-1]
        self.assertEqual((pending["id"], pending["verdict"]), (promotion["receipt"], L.PROMOTE_PENDING))
        self.assertEqual((self.status(), self.promotions()), (("active", None), 0),
                         "no reader counts a promotion whose receipt is not settled")
        self.assertEqual([e for e in self.events if e[0] == "live.band"], [])
        self.assertTrue(self.alerts)
        # The swarm's store now holds the band the ladder gave this program by its receipt: a restart (a new ladder on
        # the same stores) makes the House's records good instead of failing the cohort.
        self.bridge.status["fam"] = {"retired": False, "band": "probe", "version": 1,
                                     "proof": {"route": "ladder", "run_sha": "sha-fam-1",
                                               "receipt": promotion["receipt"]}}
        self.ladder = L.Ladder(self.live, bridge=self.bridge)
        out = self.night(42, binding=True)
        self.assertEqual((out["ended"], out["verdicts"]), ({"promoted": 1}, {}))
        self.assertEqual(self.status()[0], "promoted")
        self.assertEqual((self.receipts()[-1]["verdict"], self.promotions()), ("promote", 1))
        self.assertEqual(self.receipts()[-1]["reasons"], ["every line met and the pre-filter passed: promoted to Probe "
                                                          "(settled at a later session's end)"])
        self.assertEqual(self.latch()["answer"]["verdict"], "promote")
        self.assertEqual(self.events[-1], ("live.band", {"family": "fam", "from": "gym", "to": "probe", "version": 1,
                                                         "receipt": promotion["receipt"],
                                                         "why": "the forward ladder promoted it"}))
        self.assertNotIn("sha-fam-1", self.bridge.requests)
        self.assertEqual(len(self.bridge.promoted), 1, "one band move")
        self.bridge.families = [{"family": "fam", "band": "probe", "version": 1, "promoted_at": self.now[0]}]
        self.bridge.forward["fam"] = [{"day": "2027-01-04", "source": "real", "pnl": -5.0, "max_loss": 100.0,
                                       "version": 1}] * 21
        self.night(43)
        self.assertEqual(self.status()[0], "demoted", "its later demotion finds it promoted")

    def test_a_ledger_record_that_fails_never_fails_the_promotion_at_the_answer_or_made_good(self):
        def broken(kind, payload, agent=None):
            raise RuntimeError("the ledger is locked")

        self.live.record = broken
        self.latched()
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"promoted": 1})
        self.assertIn("could not be recorded in the ledger", self.alerts[-1])
        self.latched("two")
        receipt = self.store.add_decision({"day": self.days[40], "family": "two", "version": 1, "run_sha": "sha-two-1",
                                           "inputs": "x", "stats": {}, "verdict": L.PROMOTE_PENDING, "binding": True})
        self.bridge.status["two"] = {"retired": False, "band": "probe", "version": 1,
                                     "proof": {"route": "ladder", "run_sha": "sha-two-1", "receipt": receipt}}
        out = self.night(41, binding=True)
        self.assertEqual((out["ended"], out["verdicts"]), ({"promoted": 1}, {}), "the cohort ends promoted all the same")
        self.assertEqual((self.status("two")[0], self.store.decision(receipt)["verdict"]), ("promoted", "promote"))
        self.assertEqual(len([a for a in self.alerts if "could not be recorded in the ledger" in a]), 2)

    # ------------------------------------------------------------------ the family's state first (the WP6 review)
    def test_a_retired_familys_cohort_ends_and_its_request_goes(self):
        self.latched()
        self.assertIn("sha-fam-1", self.bridge.requests)
        self.bridge.status["fam"] = {"retired": True, "band": "retired", "version": None, "proof": {}}
        self.bridge.prefilters["sha-fam-1"] = gate_answer()
        out = self.night(41, binding=True)
        self.assertEqual((out["ended"], out["verdicts"], out["judged"]), ({"family_retired": 1}, {}, 0))
        self.assertEqual(self.status(), ("failed", "ladder: its family retired"))
        self.assertEqual(self.bridge.requests, {})
        self.assertEqual(len(self.receipts()), 1, "nothing read")
        self.cohort("gone")
        self.bridge.status["gone"] = None
        self.assertEqual(self.night(41)["ended"], {"family_retired": 1})
        self.assertEqual(self.status("gone"), ("failed", "ladder: its family is not in the swarm's store"))

    def test_a_band_another_receipt_or_program_gave_is_not_taken_for_this_promotion(self):
        self.cohort()
        receipt = self.store.add_decision({"day": self.days[0], "family": "fam", "version": 1, "run_sha": "sha-fam-1",
                                           "inputs": "x", "stats": {}, "verdict": "would_promote", "binding": False})
        void = self.store.add_decision({"day": self.days[0], "family": "fam", "version": 1, "run_sha": "sha-fam-1",
                                        "inputs": "x", "stats": {}, "verdict": L.PROMOTE_VOID, "binding": True})
        other = self.store.add_decision({"day": self.days[0], "family": "other", "version": 1, "run_sha": "sha-fam-1",
                                         "inputs": "x", "stats": {}, "verdict": L.PROMOTE_PENDING, "binding": True})
        # The other family holds its own band by its own receipt (so that one is settled, never void).
        self.bridge.status["other"] = {"retired": False, "band": "probe", "version": 1,
                                       "proof": {"route": "ladder", "run_sha": "sha-fam-1", "receipt": other}}
        for proof in ({"route": "ladder", "run_sha": "sha-fam-1", "receipt": receipt},       # not a promote receipt
                      {"route": "ladder", "run_sha": "sha-fam-1", "receipt": void},
                      {"route": "ladder", "run_sha": "sha-fam-1", "receipt": other},          # another family's
                      {"route": "ladder", "run_sha": "sha-other", "receipt": receipt},
                      {"route": "holdout", "run_sha": "sha-fam-1", "receipt": receipt}):
            self.bridge.status["fam"] = {"retired": False, "band": "probe", "version": 1, "proof": proof}
            self.assertEqual(self.night(5)["ended"], {}, proof)
        self.assertEqual(self.status(), ("active", None))
        self.assertEqual([self.store.decision(r)["verdict"] for r in (receipt, void, other)],
                         ["would_promote", L.PROMOTE_VOID, "promote"], "the other family's receipt is that family's own")

    def test_the_requests_are_those_of_the_latches_that_wait_for_the_gate(self):
        self.latched()
        self.bridge.requests["sha-ended"] = {"family": "ended", "version": 1, "bundle": "bundle-1", "day": self.days[0]}
        out = self.night(41)                                 # its own request stays: its latch waits for the gate
        self.assertEqual(out["swept"], 1)
        self.assertEqual((set(self.bridge.requests), self.bridge.swept[-1]), ({"sha-fam-1"}, {"sha-fam-1"}))
        self.store.close_cohort("fam", 1, status="failed", day=self.days[40], reason="r")
        self.night(42)
        self.assertEqual(self.bridge.requests, {}, "its cohort ended: its request goes too")

    def test_one_cohorts_answer_error_stops_no_others_answer(self):
        self.latched()
        self.latched("two")
        self.bridge.prefilters["sha-two-1"] = gate_answer()
        read = self.bridge.prefilter

        def prefilter(sha):
            if sha == "sha-fam-1":
                raise RuntimeError("the store is locked")
            return read(sha)

        self.bridge.prefilter = prefilter
        out = self.night(41, binding=True)
        self.assertEqual(out["verdicts"], {"error": 1, "promoted": 1})
        self.assertIn("fam@1's answer", self.alerts[0])
        self.assertEqual(self.status(), ("active", None))


@unittest.skipUnless(HAVE, "numpy not installed")
class TheGatesAnswer(unittest.TestCase):
    """`prefilter_answer`: the pre-filter's line as the ladder reads the gate's record."""

    def read(self, record, level=0.02, bundle="bundle-1"):
        return L.prefilter_answer(record, bundle=bundle, level=level)

    def test_it_passes_on_both_conditions_read_from_the_records_own_figures(self):
        self.assertEqual(self.read(gate_answer()), {"passed": True, "pnl": 120.0, "p": 0.01, "level": 0.02})
        self.assertEqual(self.read(gate_answer(0.0, 0.02))["passed"], True, "not negative, and at the line")
        for record in (gate_answer(-0.01, 0.0005), gate_answer(50.0, 0.0201), gate_answer(50.0, None),
                       gate_answer(None, 0.01), gate_answer(50.0, 0.01, passed=False),
                       gate_answer(50.0, 0.03, passed=True), gate_answer(50.0, 0.01, passed="yes"),
                       gate_answer(50.0, 0.01, passed=1), gate_answer(float("nan"), 0.01, passed=True),
                       gate_answer(50.0, True, passed=True)):
            self.assertIs(self.read(record)["passed"], False, record)

    def test_the_stricter_of_the_gates_level_and_the_tables_holds(self):
        loose = gate_answer(50.0, 0.03, level=0.05)
        self.assertEqual((loose["passed"], self.read(loose)),
                         (True, {"passed": False, "pnl": 50.0, "p": 0.03, "level": 0.02}))
        self.assertEqual(self.read(gate_answer(50.0, 0.01), level=0.005)["passed"], False, "the table tightened since")
        self.assertEqual(self.read(gate_answer(50.0, 0.004, level=0.005), level=0.02),
                         {"passed": True, "pnl": 50.0, "p": 0.004, "level": 0.005})

    def test_a_record_that_holds_no_answer_on_the_houses_bundle_is_none(self):
        old = {"status": "done", "passed": True, "pnl": 120.0, "bundle": "bundle-1", "ran_bundle": "bundle-1"}
        self.assertIsNone(self.read(old), "written before the line: only the sign of its P&L was read")
        self.assertIsNone(self.read(dict(old, p=0.001)), "a p-value with no level it was judged at")
        self.assertIsNone(self.read(dict(old, p=0.001, level="x")))
        for record in (None, {}, "done", gate_answer(status="waiting"), gate_answer(status="failed"),
                       gate_answer(bundle="bundle-0"), gate_answer(ran_bundle="bundle-0"), gate_answer(ran_bundle=None)):
            self.assertIsNone(self.read(record), record)
        self.assertIsNone(self.read(gate_answer(), bundle=None), "no bundle to match it on")

    def test_the_band_the_ladder_gave_names_its_receipt(self):
        status = {"retired": False, "band": "probe", "version": 1,
                  "proof": {"route": "ladder", "run_sha": "sha-1", "receipt": 7}}
        self.assertEqual(L.banded_receipt(status, 1, "sha-1"), 7)
        for band in ("candidate", "sized"):
            self.assertEqual(L.banded_receipt(dict(status, band=band), 1, "sha-1"), 7)
        for change in ({"band": "gym"}, {"retired": True}, {"version": 2}, {"proof": {}},
                       {"proof": dict(status["proof"], route="holdout")}, {"proof": dict(status["proof"], receipt=True)},
                       {"proof": dict(status["proof"], receipt="7")}, {"proof": dict(status["proof"], run_sha="other")}):
            self.assertIsNone(L.banded_receipt(dict(status, **change), 1, "sha-1"), change)
        self.assertIsNone(L.banded_receipt(None, 1, "sha-1"))
        self.assertIsNone(L.banded_receipt(status, 1, ""))


class SwarmStoreNights(NightCase):
    """The session's end through the REAL bridge (`SwarmBridge` on a swarm store in the House's state directory), the
    gate's record written by the gate's own writer on its own line. No tests of its own, and no switch patched."""

    def setUp(self):
        from league.swarm.gate import run_sha
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock

        super().setUp()
        self.swarm = SwarmStore(self.root, clock=Clock())
        self.addCleanup(self.swarm.close)
        self.swarm.add_family({"id": "fam", "mechanism": "An invented mechanism.", "structure": "debit_vertical",
                               "roots": ["SPY"], "dte": [0, 5]}, origin="test")
        self.swarm.add_version("fam", CODE, {"hold": 3}, author="test")
        self.swarm.set_state("fam", validation_version=1, validation_line={"passed": True})
        self.sha = run_sha(self.swarm.version("fam", 1))
        self.families = SimpleNamespace(root=self.root, lock=__import__("threading").Lock(), _db=lambda: self.swarm)
        self.bridge = L.SwarmBridge(self.families)
        self.ladder = L.Ladder(self.live, bridge=self.bridge)

    def program(self, fid="fam", n=1, tier="validated") -> dict:
        return dict(super().program(fid, n, tier), run_sha=self.sha)   # the very program the swarm's store holds

    def requests(self):
        return self.swarm.get(L.PREFILTER_REQUESTS) or {}

    def gate_reads(self, *, daily=None, pnl=120.0) -> dict:
        """The gate's read of the holdout the House asked for, judged on the gate's own line and written by the gate's
        own writer (`evidence.prefilter_line`, `Gate._prefilter_write`): the line's figures."""
        from league.swarm import evidence, gate
        from league.tests.swarm_fakes import result

        ask = self.requests()[self.sha]
        line = evidence.prefilter_line(result("fam", window="holdout", daily=daily, pnl=pnl), level=gate.prefilter_level(),
                                       seed=gate.PREFILTER_SEED + self.sha)
        gate.Gate._prefilter_write(SimpleNamespace(store=self.swarm, clock=lambda: 1.0), self.sha, ask, {}, status="done",
                                   line=line, ran_bundle=ask["bundle"], ran_image="image")
        return line

    def band(self):
        fam = self.swarm.family("fam")
        return fam["band"], (fam["state"].get("banded_evaluator") or {}).get("receipt")


@unittest.skipUnless(HAVE, "numpy not installed")
class TheSwarmsOwnStore(SwarmStoreNights):
    """Recording and binding through the swarm's own store, in THE LADDER'S OWN MODE (`ladders_own_gate`: evidence v3's
    own gate, where the pre-filter reads and the belt can let a promotion through). `TheFastLane` runs the same
    cohorts under the shipped switches."""

    def setUp(self):
        ladders_own_gate(self)
        super().setUp()

    def test_the_request_is_the_houses_and_the_gates_record_is_the_answer(self):
        self.latched()
        self.assertEqual(self.requests(), {self.sha: {"family": "fam", "version": 1, "bundle": "bundle-1",
                                                      "day": self.days[39]}})
        line = self.gate_reads()
        self.assertEqual((line["passed"], line["level"], line["pnl"]), (True, 0.02, 120.0))
        self.assertEqual(L.prefilter_answer(self.bridge.prefilter(self.sha), bundle="bundle-1", level=0.02), line)

    def test_recording_it_would_promote_and_the_swarms_store_is_not_touched(self):
        from league.swarm import bands

        self.latched()
        line = self.gate_reads()
        events = len(self.swarm.events_after(0))
        self.assertEqual(self.night(41)["verdicts"], {"would_promote": 1})
        answer = self.receipts()[-1]
        self.assertEqual(answer["stats"]["answer"], {"waited": 1, "prefilter": line, "belt": {"read": True, "refusal": None}})
        self.assertEqual((self.band(), bands.read(self.root)), (("gym", None), []), "no band, no proof, no live row")
        self.assertEqual([e["kind"] for e in self.swarm.events_after(0)][events:], [], "nothing written to the swarm")
        self.assertEqual((self.requests(), self.status(), self.latch()["answer"]["verdict"]),
                         ({}, ("active", None), "would_promote"))
        self.assertEqual(ops_promotions(self, self.root, self.now[0]), 0)
        self.assertEqual(self.night(42)["recorded"], 1)
        self.assertEqual(len(self.receipts()), 2, "once")

    def test_recording_the_belts_refusal_is_recorded_and_refuses_nothing(self):
        self.latched()
        self.gate_reads()
        self.swarm.set_state("fam", robust_failed=[1])       # the Gym demoted this version since
        self.assertEqual(self.night(41)["verdicts"], {"would_promote": 1})
        belt = self.receipts()[-1]["stats"]["answer"]["belt"]
        self.assertEqual((belt["read"], "demoted" in belt["refusal"], self.status()), (True, True, ("active", None)))

    def test_binding_it_promotes_through_the_swarms_store_with_its_settled_receipt(self):
        from league.swarm import bands

        first = self.latched()
        self.gate_reads()
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"promoted": 1})
        receipt = self.receipts()[-1]
        self.assertEqual((receipt["verdict"], receipt["p_value"], receipt["binding"]), ("promote", first["p_value"], 1))
        self.assertEqual(self.band(), ("probe", receipt["id"]))
        [row] = bands.read(self.root)
        self.assertEqual((row["family"], row["band"], row["version"], row["code"], row["run_sha"],
                          row["typical_max_loss_usd"]), ("fam", "probe", 1, CODE, self.sha, first["stats"]["typical"]))
        self.assertTrue(bands.ladder_receipt(self.root, family="fam", version=1, run_sha=self.sha, receipt=receipt["id"]))
        self.assertEqual((self.status()[0], self.requests(), ops_promotions(self, self.root, self.now[0])),
                         ("promoted", {}, 1))
        self.assertEqual(self.events[-1][1]["receipt"], receipt["id"])
        self.assertEqual(self.bridge.ladder_families()[0]["family"], "fam")

    def test_binding_a_read_over_the_line_on_its_p_fails_the_cohort_and_bands_nothing(self):
        rng = __import__("random").Random(5)
        noisy = [rng.gauss(0.4, 10.0) for _ in range(180)]
        self.latched()
        line = self.gate_reads(daily=noisy, pnl=sum(noisy))
        self.assertEqual((line["passed"], line["pnl"] > 0, line["p"] > 0.02), (False, True, True),
                         "a holdout that made money, by a margin its own noise explains")
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"prefilter_negative": 1})
        self.assertEqual((self.band(), self.status()),
                         (("gym", None), ("failed", "ladder: the pre-filter read did not pass its line")))
        self.assertEqual(ops_promotions(self, self.root, self.now[0]), 0)

    def test_binding_a_belt_that_cannot_be_read_fails_nothing_and_is_read_again(self):
        from league.swarm import bands

        self.latched()
        self.gate_reads()
        owed = self.root / bands.BARS_OWED_FILE
        owed.write_text("not json", encoding="utf-8")        # the gate's owed bars cannot be read
        self.assertEqual(self.bridge.refusal("fam", 1, self.sha), bands.BELT_BARS_UNREAD)
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"error": 1})
        self.assertEqual((self.band(), self.status(), len(self.receipts())), (("gym", None), ("active", None), 1))
        self.assertIn(bands.BELT_BARS_UNREAD, self.alerts[-1])
        owed.unlink()
        self.assertEqual(self.night(42, binding=True)["verdicts"], {"promoted": 1})
        self.assertEqual(self.band()[0], "probe")
        self.assertEqual(ladder_refusal_without_a_store(self), bands.BELT_STORE_UNREAD)

    def test_binding_a_real_refusal_of_the_belt_fails_the_cohort(self):
        self.latched()
        self.gate_reads()
        self.swarm.set_state("fam", robust_failed=[1])
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"blocked": 1})
        self.assertEqual((self.band(), self.status()[0], ops_promotions(self, self.root, self.now[0])),
                         (("gym", None), "failed", 0))

    def test_binding_a_record_with_no_typical_unit_is_blocked_and_bands_nothing(self):
        with patch.object(L, "_typical", return_value=None):          # no close of its record carries a quantity
            first = self.latched()
        self.assertIsNone(first["stats"]["typical"])
        self.gate_reads()
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"blocked": 1})
        unknown = "its typical maximum loss is unknown: it cannot be shown to fit the Probe's cap"
        self.assertEqual((self.receipts()[-1]["verdict"], self.receipts()[-1]["reasons"]), ("blocked", [unknown]))
        self.assertEqual((self.band(), self.status(), ops_promotions(self, self.root, self.now[0])),
                         (("gym", None), ("failed", f"ladder: {unknown}"), 0))

    def test_binding_a_band_write_that_raised_voids_the_receipt_and_the_next_session_promotes(self):
        self.latched()
        self.gate_reads()
        with patch.object(self.swarm, "set_band", side_effect=__import__("sqlite3").OperationalError("database is locked")):
            self.assertEqual(self.night(41, binding=True)["verdicts"], {"error": 1})
        self.assertEqual((self.band(), self.receipts()[-1]["verdict"], self.status()),
                         (("gym", None), L.PROMOTE_VOID, ("active", None)), "the swarm's transaction rolled back whole")
        self.assertEqual(ops_promotions(self, self.root, self.now[0]), 0)
        self.assertEqual(self.night(42, binding=True)["verdicts"], {"promoted": 1})
        self.assertEqual(self.band(), ("probe", self.receipts()[-1]["id"]))
        self.assertEqual(([r["verdict"] for r in self.receipts()], ops_promotions(self, self.root, self.now[0])),
                         (["await_prefilter", L.PROMOTE_VOID, "promote"], 1))

    def test_binding_a_settling_that_failed_is_made_good_from_the_swarms_own_band(self):
        from league.swarm import bands

        self.latched()
        self.gate_reads()
        with patch.object(self.store, "settle_answer", side_effect=__import__("sqlite3").OperationalError("locked")):
            self.assertEqual(self.night(41, binding=True)["verdicts"], {"error": 1})
        pending = self.receipts()[-1]
        self.assertEqual((self.band(), pending["verdict"]), (("probe", pending["id"]), L.PROMOTE_PENDING))
        self.assertEqual((bands.read(self.root), ops_promotions(self, self.root, self.now[0])), ([], 0),
                         "the band has no settled receipt yet: no live row, no promotion counted")
        out = self.night(42, binding=True)
        self.assertEqual((out["ended"], self.status()[0], self.receipts()[-1]["verdict"]),
                         ({"promoted": 1}, "promoted", "promote"))
        self.assertEqual(([r["family"] for r in bands.read(self.root)], ops_promotions(self, self.root, self.now[0])),
                         (["fam"], 1))

    def a_band_that_landed_with_its_receipt_pending(self) -> dict:
        """The band the ladder gave is in the swarm's store and the House died before settling its receipt: no live
        row, no promotion to any reader. The pending receipt."""
        from league.swarm import bands

        self.latched()
        self.gate_reads()
        with patch.object(self.store, "settle_answer", side_effect=Killed()), self.assertRaises(Killed):
            self.night(41, binding=True)
        pending = self.receipts()[-1]
        self.assertEqual((self.band(), pending["verdict"], self.status()),
                         (("probe", pending["id"]), L.PROMOTE_PENDING, ("active", None)))
        self.assertEqual((bands.read(self.root), ops_promotions(self, self.root, self.now[0])), ([], 0))
        return pending

    def test_binding_a_landed_band_is_settled_after_a_release_ended_its_cohort(self):
        """A release changed the evaluator between the band's move and its receipt's settling, and the next session's
        pins ended the cohort (latched: its verdict was final). The session's end settles the receipt all the same: no
        landed band is left with a pending receipt, and the cohort's own ending stands."""
        from league.live.observe import EVALUATOR_CHANGED_FINAL

        pending = self.a_band_that_landed_with_its_receipt_pending()
        self.store.evaluator = "bundle-2:fills-1:exec-2"         # a release that changed the practice evaluator
        self.assertEqual(self.pins(42), [])
        self.assertEqual(self.status(), ("complete", EVALUATOR_CHANGED_FINAL))
        out = self.night(42, binding=True)
        self.assertEqual((out["settled"], out["ended"], out["verdicts"]), ({"promoted": 1, "void": 0}, {}, {}))
        settled = self.receipts()[-1]
        self.assertEqual((settled["id"], settled["verdict"], settled["reasons"]),
                         (pending["id"], "promote", ["every line met and the pre-filter passed: promoted to Probe "
                                                     "(settled at a later session's end)"]))
        self.assertEqual(self.status(), ("complete", EVALUATOR_CHANGED_FINAL), "its cohort stays as the pins ended it")
        self.assertEqual([p for kind, p in self.events if kind == "live.band"],
                         [{"family": "fam", "from": "gym", "to": "probe", "version": 1, "receipt": pending["id"],
                           "why": "the forward ladder promoted it"}], "its move is recorded, once")
        self.assertEqual(ops_promotions(self, self.root, self.now[0]), 1, "the budget and the scoreboard agree again")
        out = self.night(43, binding=True)
        self.assertEqual((out["settled"], len(self.receipts()), len(self.events)), ({"promoted": 0, "void": 0}, 2, 1))
        # Its band is then exactly a promotion settled on its own night: live while its proof is current, and void,
        # settled or not, once a release has changed the code the proof pins (the execution fingerprint).
        from league.swarm import bands

        self.assertEqual([r["family"] for r in bands.read(self.root)], ["fam"])
        with patch("league.swarm.evaluator.execution_fingerprint", return_value="another-live-path"):
            self.assertEqual(bands.read(self.root), [])

    def test_binding_a_landed_band_is_settled_under_another_evaluator_before_any_pins(self):
        """The same with the session's end reached before any pins: the cohort, still active under the earlier
        evaluator, ends `promoted` with its receipt (never judged, never left pending)."""
        pending = self.a_band_that_landed_with_its_receipt_pending()
        self.store.evaluator = "bundle-2:fills-1:exec-2"
        out = self.night(42, binding=True)
        self.assertEqual((out["settled"], out["ended"], out["judged"]), ({"promoted": 1, "void": 0}, {"promoted": 1}, 0))
        self.assertEqual((self.receipts()[-1]["verdict"], self.status()),
                         ("promote", ("promoted", f"ladder: promoted to Probe (receipt {pending['id']}; recorded at a "
                                                  "later session's end)")))
        self.assertEqual(self.latch()["answer"]["verdict"], "promote")
        self.assertEqual(ops_promotions(self, self.root, self.now[0]), 1)
        self.assertEqual(self.pins(43), [], "promoted: never offered again, never ended as changed")

    def test_binding_a_pending_receipt_whose_band_never_landed_is_void_at_the_next_session_end(self):
        """The House died after the pending receipt and before the band's move: the store shows no band of it, so the
        next session's end voids it and the cohort's answer is read again, with a receipt of its own."""
        self.latched()
        self.gate_reads()
        with patch.object(L.SwarmBridge, "promote", side_effect=Killed()), self.assertRaises(Killed):
            self.night(41, binding=True)
        self.assertEqual((self.band(), self.receipts()[-1]["verdict"]), (("gym", None), L.PROMOTE_PENDING))
        out = self.night(42, binding=True)
        self.assertEqual((out["settled"], out["verdicts"]), ({"promoted": 0, "void": 1}, {"promoted": 1}))
        self.assertEqual([(r["verdict"], r["reasons"][0]) for r in self.receipts()[1:]],
                         [(L.PROMOTE_VOID, "the swarm's store holds no band of it"),
                          ("promote", "every line met and the pre-filter passed: promoted to Probe")])
        self.assertEqual((self.band(), ops_promotions(self, self.root, self.now[0])),
                         (("probe", self.receipts()[-1]["id"]), 1))

    def test_binding_a_pending_receipt_stays_pending_while_the_store_cannot_be_read(self):
        pending = self.a_band_that_landed_with_its_receipt_pending()
        self.store.evaluator = "bundle-2:fills-1:exec-2"
        self.pins(42)
        with patch.object(self.bridge, "family_status", side_effect=__import__("sqlite3").OperationalError("locked")):
            out = self.night(42, binding=True)
        self.assertEqual((out["settled"], self.receipts()[-1]["verdict"]), ({"promoted": 0, "void": 0}, L.PROMOTE_PENDING))
        self.assertIn(f"could not settle fam@1's pending promotion (receipt {pending['id']}", self.alerts[-1])
        self.assertEqual(ops_promotions(self, self.root, self.now[0]), 0)
        self.assertEqual(self.night(43, binding=True)["settled"], {"promoted": 1, "void": 0})
        self.assertEqual((self.receipts()[-1]["verdict"], ops_promotions(self, self.root, self.now[0])), ("promote", 1))

    def test_a_validation_the_store_does_not_hold_yet_waits_and_one_that_failed_ends_it(self):
        self.swarm.set_state("fam", validation_version=None, validation_line=None)
        self.cohort()
        self.assertEqual(self.night(40, binding=True)["verdicts"], {"await_validation": 1})
        self.assertEqual((self.requests(), self.latch()["waits"]), ({}, "validation"))
        self.swarm.set_state("fam", validation_version=1, validation_line={"passed": True})
        self.assertEqual(self.night(41, binding=True)["waiting"], 1)
        self.assertEqual((set(self.requests()), self.latch()["waits"]), ({self.sha}, "prefilter"))
        self.swarm.set_state("fam", validation_version=1, validation_line={"passed": False})
        self.gate_reads()
        self.assertEqual(self.night(42, binding=True)["verdicts"], {"blocked": 1},
                         "the belt reads the Validation line again before any band is written")
        self.assertEqual((self.band(), self.status()[0]), (("gym", None), "failed"))

    def test_a_family_the_swarm_retired_ends_its_latched_cohort(self):
        self.latched()
        self.gate_reads()
        self.swarm.retire("fam", "test")
        out = self.night(41, binding=True)
        self.assertEqual((out["ended"], out["verdicts"], self.status()),
                         ({"family_retired": 1}, {}, ("failed", "ladder: its family retired")))
        self.assertEqual(self.requests(), {})


def ladder_refusal_without_a_store(case: unittest.TestCase) -> str | None:
    """THE LADDER'S BELT on a state directory with no swarm store."""
    from league.swarm import bands

    empty = Path(case.tmp.name) / "empty"
    empty.mkdir()
    return bands.ladder_refusal(empty, family="fam", version=1, run_sha="x")


class TheDemotions(NightCase):
    def test_one_familys_demotion_error_stops_no_other(self):
        self.bridge.families = [{"family": "bad", "band": "probe", "version": 1, "promoted_at": None},
                                {"family": "old", "band": "probe", "version": 1, "promoted_at": None}]
        self.bridge.forward["old"] = [{"day": d, "source": "real", "pnl": -5.0, "max_loss": 100.0, "version": 1}
                                      for d in self.days[:21]]
        forward = self.bridge.forward_rows

        def rows(family):
            if family == "bad":
                raise RuntimeError("unreadable")
            return forward(family)

        self.bridge.forward_rows = rows
        self.assertEqual([d["family"] for d in self.night(25)["demoted"]], ["old"])
        self.assertIn("bad", self.alerts[0])
        self.bridge.ladder_families = lambda: (_ for _ in ()).throw(RuntimeError("the store is locked"))
        self.assertEqual(self.night(25)["demoted"], [], "the session's end still ends")

    @unittest.skipUnless(HAVE, "numpy not installed")
    def test_a_ladder_probe_is_demoted_on_a_negative_record_or_a_low_session_bound(self):
        self.cohort()
        self.store.close_cohort("fam", 1, status="promoted", day=self.days[0], reason="r")
        promoted_at = dt.datetime(2026, 10, 1, 21, tzinfo=dt.timezone.utc).timestamp()
        self.bridge.families = [{"family": "fam", "band": "probe", "version": 1, "promoted_at": promoted_at}]
        self.bridge.forward["fam"] = [{"day": d, "source": "real", "pnl": -5.0, "max_loss": 100.0, "version": 1}
                                      for d in self.days[:21]]
        out = self.night(25)
        self.assertEqual([d["family"] for d in out["demoted"]], ["fam"])
        self.assertIn("negative over 21 trades", self.bridge.demoted[0][1])
        self.assertEqual(self.status()[0], "demoted")
        self.bridge.demoted.clear()
        rng = np.random.default_rng(5)
        self.bridge.forward["fam"] = [{"day": d, "source": "real", "pnl": float(1.0 + 40 * rng.standard_normal()),
                                       "max_loss": 100.0, "version": 1} for d in self.days[:20]]
        self.bridge.forward["fam"][0]["pnl"] = 60.0          # a mean above zero: not negative
        self.night(25)
        self.assertEqual(len(self.bridge.demoted), 1, "the 20-session bound below zero demotes it")
        self.bridge.demoted.clear()
        self.bridge.forward["fam"] = [{"day": d, "source": "real", "pnl": 20.0 + i % 3, "max_loss": 100.0, "version": 1}
                                      for i, d in enumerate(self.days[:20])]
        self.night(25)
        self.assertEqual(self.bridge.demoted, [])

    def test_the_rows_before_its_promotion_never_save_or_sink_it(self):
        self.bridge.families = [{"family": "fam", "band": "probe", "version": 1,
                                 "promoted_at": dt.datetime(2026, 11, 20, 21, tzinfo=dt.timezone.utc).timestamp()}]
        self.bridge.forward["fam"] = [{"day": d, "source": "nightly", "pnl": -5.0, "max_loss": 100.0, "version": 1}
                                      for d in self.days[:24]]
        self.assertEqual(self.night(25)["demoted"], [])


# ================================================================================================== the swarm's side
class TheSwarmSide(unittest.TestCase):
    def setUp(self):
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock

        ladders_own_gate(self)   # the belt and the promotion as the ladder's own mode has them
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = SwarmStore(self.root, clock=Clock())
        self.addCleanup(self.store.close)
        self.store.add_family({"id": "fam", "mechanism": "An invented mechanism.", "structure": "debit_vertical",
                               "roots": ["SPY"], "dte": [0, 5]}, origin="test")
        self.store.add_version("fam", CODE, {"hold": 3}, author="test")
        from league.swarm.gate import run_sha

        self.sha = run_sha(self.store.version("fam", 1))
        self.store.set_state("fam", validation_version=1, validation_line={"passed": True})
        self.families = SimpleNamespace(root=self.root, lock=__import__("threading").Lock(), _db=lambda: self.store)
        self.bridge = L.SwarmBridge(self.families)
        self.snapshot = {"code": CODE, "params": {"hold": 3}, "run_sha": self.sha, "practice_evaluator": EVALUATOR}
        self.observed = ObserveStore(self.root, clock=lambda: 1.0)
        self.addCleanup(self.observed.close)

    def receipt(self, verdict="promote", **changes) -> int:
        """A receipt of the House's practice record (`ladder_decisions`)."""
        row = {"day": "2026-11-02", "family": "fam", "version": 1, "run_sha": self.sha, "inputs": "x", "stats": {},
               "verdict": verdict, "binding": True, **changes}
        return self.observed.add_decision(row)

    def test_a_promotion_bands_exactly_the_practised_program(self):
        from league.swarm import bands

        self.assertIsNone(self.bridge.refusal("fam", 1, self.sha))
        receipt = self.receipt()
        self.assertIsNone(self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=receipt,
                                              typical=52.6, at=1_790_000_000.0))
        fam = self.store.family("fam")
        self.assertEqual(fam["band"], "probe")
        state = fam["state"]
        self.assertEqual((state["banded_version"], state["banded_evaluator"]["route"], state["banded_evaluator"]["receipt"],
                          state["typical_by_version"]["1"], state["live_promoted_at"]),
                         (1, "ladder", receipt, 52.6, 1_790_000_000.0))
        self.assertTrue(bands.current_banded_evaluator(state, self.sha))
        [row] = bands.read(self.root)
        self.assertEqual((row["band"], row["version"], row["code"], row["params"], row["run_sha"], row["holdout_passed"],
                          row["typical_max_loss_usd"]), ("probe", 1, CODE, {"hold": 3}, self.sha, True, 52.6))
        events = [e for e in self.store.events_after(0) if e["kind"] == "swarm.band"]
        self.assertIn(f"practice receipt {receipt}", events[-1]["payload"]["reason"])
        self.assertEqual(self.bridge.ladder_families(), [{"family": "fam", "band": "probe", "version": 1,
                                                          "promoted_at": 1_790_000_000.0}])

    def test_the_demotions_record_starts_at_the_ladders_own_promotion(self):
        """The money table's own candidate -> probe move rewrites `live_promoted_at` (`SwarmFamilies.confirm_band`); the
        demotion's record "since its promotion" stays the one since the LADDER promoted it (its proof's `at`)."""
        from league.live.families import SwarmFamilies
        from league.swarm import bands

        t0 = 1_790_000_000.0
        self.assertIsNone(self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=self.receipt(),
                                              typical=52.6, at=t0))
        families = SwarmFamilies(self.root)
        self.addCleanup(lambda: families._store.close() if families._store is not None else None)
        forward = families.forward_rows("fam")
        [row] = bands.read(self.root)
        self.assertTrue(families.confirm_band(row, "candidate", "its unit does not fit", forward, at=t0 + 86400.0))
        [row] = bands.read(self.root)
        self.assertTrue(families.confirm_band(row, "probe", "its unit fits again", forward, at=t0 + 5 * 86400.0))
        state = self.store.family("fam")["state"]
        self.assertEqual((state["live_promoted_at"], state["banded_evaluator"]["at"]), (t0 + 5 * 86400.0, t0),
                         "the money table's own clock moved")
        self.assertEqual(self.bridge.ladder_families(), [{"family": "fam", "band": "probe", "version": 1,
                                                          "promoted_at": t0}])
        # A proof that names no time (none is written so): the money table's is all there is.
        self.store.set_state("fam", banded_evaluator={k: v for k, v in state["banded_evaluator"].items() if k != "at"})
        self.assertEqual(self.bridge.ladder_families()[0]["promoted_at"], t0 + 5 * 86400.0)

    def test_a_proof_without_its_receipt_or_under_another_fingerprint_is_not_current(self):
        from league.swarm import bands

        self.assertIsNone(self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=self.receipt(),
                                              typical=52.6, at=1.0))
        state = self.store.family("fam")["state"]
        for change in ({"receipt": None}, {"receipt": True}, {"execution_sha256": "another"}, {"run_sha": "x"}):
            broken = dict(state, banded_evaluator={**state["banded_evaluator"], **change})
            self.assertFalse(bands.current_banded_evaluator(broken, self.sha), change)

    def test_another_program_a_retired_family_or_another_band_refuses_the_promotion(self):
        self.assertIn("not the practised program",
                      self.bridge.promote(family="fam", version=1, snapshot={**self.snapshot, "params": {"hold": 4}},
                                          receipt=1, typical=None, at=1.0))
        self.assertIn("not the practised program", self.bridge.refusal("fam", 1, "another-sha"))
        self.assertEqual(self.store.family("fam")["band"], "gym", "nothing written")
        self.store.set_band("fam", "candidate", reason="test")
        self.assertIn("candidate", self.bridge.refusal("fam", 1, self.sha))
        self.assertIn("candidate", self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=1,
                                                       typical=None, at=1.0))
        self.store.retire("fam", "test")
        self.assertEqual(self.bridge.refusal("fam", 1, self.sha), "the family retired")

    def test_a_promotion_whose_typical_unit_is_unknown_is_refused(self):
        """The money table holds only a Candidate whose typical unit is unknown; the ladder bands at Probe, so it
        promotes nothing it cannot show to fit the Probe's cap."""
        from league.swarm import bands

        unknown = "its typical maximum loss is unknown: it cannot be shown to fit the Probe's cap"
        for typical in (None, 0.0, -5.0, float("nan"), "x"):
            self.assertEqual(self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=self.receipt(),
                                                 typical=typical, at=1.0), unknown, typical)
        fam = self.store.family("fam")
        self.assertEqual((fam["band"], fam["state"].get("banded_version"), fam["state"].get("typical_by_version")),
                         ("gym", None, None), "nothing written")
        self.assertEqual([e for e in self.store.events_after(0) if e["kind"] == "swarm.band"], [])
        # The store's own typical for that very version (its validation run's) is known: enough.
        self.store.set_state("fam", typical_max_loss_usd=41.0, validation_version=2)
        self.assertEqual(self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=self.receipt(),
                                             typical=None, at=1.0), unknown, "another version's is not this one's")
        self.store.set_state("fam", validation_version=1)
        self.assertIsNone(self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=self.receipt(),
                                              typical=None, at=1.0))
        [row] = bands.read(self.root)
        self.assertEqual((row["band"], row["typical_max_loss_usd"]), ("probe", 41.0))

    def test_a_ladder_proof_trades_only_with_its_practice_receipt(self):
        from league.live.families import SwarmFamilies
        from league.swarm import bands

        self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=41, typical=52.6, at=1.0)
        self.assertEqual(bands.read(self.root), [], "no receipt 41 in the House's record: no row")
        for changes in ({"verdict": "would_promote"}, {"family": "other"}, {"version": 2}, {"run_sha": "another"}):
            receipt = self.receipt(**changes)
            self.store.set_state("fam", banded_evaluator={**self.store.family("fam")["state"]["banded_evaluator"],
                                                          "receipt": receipt})
            self.assertEqual(bands.read(self.root), [], changes)
            self.assertFalse(bands.ladder_receipt(self.root, family="fam", version=1, run_sha=self.sha, receipt=receipt))
        receipt = self.receipt()
        self.store.set_state("fam", banded_evaluator={**self.store.family("fam")["state"]["banded_evaluator"],
                                                      "receipt": receipt})
        [row] = bands.read(self.root)
        families = SwarmFamilies(self.root)
        self.addCleanup(lambda: families._store.close() if families._store is not None else None)
        forward = families.forward_rows("fam")
        self.assertTrue(families.confirm_band(row, "probe", "unchanged", forward))
        self.store.set_state("fam", banded_evaluator={**self.store.family("fam")["state"]["banded_evaluator"],
                                                      "receipt": receipt + 1000})
        self.assertFalse(families.confirm_band(row, "probe", "unchanged", forward), "a copied proof never confirms")
        self.assertFalse(bands.ladder_receipt(self.root / "nowhere", family="fam", version=1, run_sha=self.sha,
                                              receipt=receipt), "an unread record admits nothing")

    def test_the_belt_needs_the_validation_line_on_the_gym_in_force(self):
        """L0 is Gym evidence on the Gym in force (`bands.validation_passed`; `test_live_ladder_adoption.py` holds it
        whole, across the swarm's real adoptions): a verdict judged under another evaluator is the version's only when
        that evaluator differs by the execution fingerprint alone."""
        from league.swarm import bands

        self.store.set_state("fam", validation_version=None, validation_line=None)
        self.assertIn("Validation line", self.bridge.refusal("fam", 1, self.sha), "a Train-tier entrant never validated")
        self.assertIsNone(self.bridge.validation("fam", 1))
        self.store.set_state("fam", validation_version=1, validation_line={"passed": False})
        self.assertIn("Validation line", self.bridge.refusal("fam", 1, self.sha))
        self.assertIs(self.bridge.validation("fam", 1), False)
        self.store.put("research_evaluator", "E2")
        self.store.set_state("fam", validation_version=2, validation_line={"passed": True},
                             validation_verdicts={"1": {"passed": True, "at": "x", "evaluator": "E1"}})
        self.assertIn("Validation line", self.bridge.refusal("fam", 1, self.sha), "a pass under another evaluator")
        self.store.set_state("fam", validation_verdicts={"1": {"passed": True, "at": "x", "evaluator": "E2"}})
        self.assertIsNone(self.bridge.refusal("fam", 1, self.sha), "its latest verdict under this one passed")
        self.assertIs(self.bridge.validation("fam", 1), True)
        self.assertIs(bands.validation_passed({"validation_version": 1, "validation_line": {"passed": True}}, 1, None), True)
        self.assertIsNone(bands.validation_passed({"validation_version": 2, "validation_line": {"passed": True}}, 1, None))
        # An identity that names its Gym: the same image and bundle under an earlier execution fingerprint is the Gym in
        # force; another image is not.
        gym = {"image": "image", "bundle": "bundle", "execution": "this league/live"}
        self.store.put("research_evaluator", gym)
        for judged, met in (({**gym, "execution": "an earlier league/live"}, True), ({**gym, "image": "another image"}, False)):
            self.store.set_state("fam", validation_verdicts={"1": {"passed": True, "at": "x", "evaluator": judged}})
            self.assertIs(self.bridge.validation("fam", 1), True if met else None, judged)
            self.assertEqual(self.bridge.refusal("fam", 1, self.sha),
                             None if met else "its version has not met the Validation line on the Gym in force")

    def test_a_version_the_ladder_demoted_is_refused_again(self):
        self.store.set_state("fam", ladder_demoted={"receipt": 4, "why": "w", "at": 2.0, "version": 1})
        self.assertIn("ladder demoted", self.bridge.refusal("fam", 1, self.sha))
        self.store.set_state("fam", ladder_demoted={"receipt": 4, "why": "w", "at": 2.0, "version": 3})
        self.assertIsNone(self.bridge.refusal("fam", 1, self.sha))

    def test_the_family_as_the_store_holds_it_and_the_requests_sweep(self):
        self.assertEqual(self.bridge.family_status("fam"), {"retired": False, "band": "gym", "version": None, "proof": {}})
        self.assertIsNone(self.bridge.family_status("nobody"))
        for sha in ("a", "b", "c"):
            self.bridge.request_prefilter(sha, family="fam", version=1, bundle="b1", day="2026-11-02")
        self.assertEqual(self.bridge.sweep_prefilter(["b"]), 2)
        self.assertEqual(set(self.store.get(L.PREFILTER_REQUESTS)), {"b"})
        self.store.retire("fam", "test")
        self.assertTrue(self.bridge.family_status("fam")["retired"])

    def test_the_belt_reads_the_programs_verdicts_and_demotions(self):
        self.store.set_state("fam", incubator_barred={self.sha: {"why": "test"}})
        self.assertIn("barred", self.bridge.refusal("fam", 1, self.sha))
        self.store.set_state("fam", incubator_barred={}, robust_failed=[1])
        self.assertIn("demoted", self.bridge.refusal("fam", 1, self.sha))
        self.store.set_state("fam", robust_failed=[], review={"sha": self.sha, "verdict": "fail"})
        self.assertIn("review", self.bridge.refusal("fam", 1, self.sha))
        self.store.set_state("fam", review=None)
        self.store.refuse("fam", 1, "experiment contract", "test")
        self.assertIn("refused", self.bridge.refusal("fam", 1, self.sha))

    def test_the_belt_refuses_a_program_whose_holdout_look_failed_whatever_the_state_says(self):
        """The `looks` row is kept for good: a failed look refuses the promotion with no bar and no gate outcome on
        record for it (the incubator's reader holds the same line). A look that passed, or another program's, does not."""
        from league.swarm import bands
        from league.swarm.gate import run_sha

        self.store.add_family({"id": "passed", "mechanism": "Another invented mechanism.", "structure": "debit_vertical",
                               "roots": ["SPY"], "dte": [0, 5]}, origin="test")
        passed = run_sha(self.store.add_version("passed", CODE, {"hold": 4}, author="test"))
        self.store.set_state("passed", validation_version=1, validation_line={"passed": True})
        self.store.add_look("passed", 1, passed, passed=True, p_value=0.01, detail={})
        self.store.add_look("fam", 1, "another-program", passed=False, p_value=0.4, detail={})
        self.assertEqual((self.bridge.refusal("passed", 1, passed), self.bridge.refusal("fam", 1, self.sha)), (None, None))
        self.store.add_look("fam", 1, self.sha, passed=False, p_value=0.4, detail={})
        state = self.store.family("fam")["state"]
        self.assertEqual((state.get("incubator_barred"), state.get("gate_outcome")), (None, None), "nothing else says so")
        self.assertEqual(self.bridge.refusal("fam", 1, self.sha), "a holdout look on its program failed")
        self.assertEqual(bands.ladder_refusal(self.root, family="fam", version=1, run_sha=self.sha),
                         "a holdout look on its program failed")
        self.assertIn("not the practised program", self.bridge.refusal("fam", 1, "another-program"),
                      "the earlier conditions still come first")

    def test_the_prefilter_request_is_the_houses_and_the_demotion_goes_back_to_the_gym(self):
        self.bridge.request_prefilter(self.sha, family="fam", version=1, bundle="b1", day="2026-11-02")
        self.assertEqual(self.store.get(L.PREFILTER_REQUESTS)[self.sha]["bundle"], "b1")
        self.assertIsNone(self.bridge.prefilter(self.sha))
        self.store.put(L.PREFILTER_KEY + self.sha, {"status": "done", "passed": True})
        self.assertEqual(self.bridge.prefilter(self.sha)["passed"], True)
        self.assertFalse(hasattr(self.bridge, "settle_prefilter"), "the sweep alone takes a request away")
        self.assertEqual((self.bridge.sweep_prefilter([self.sha]), set(self.store.get(L.PREFILTER_REQUESTS))),
                         (0, {self.sha}))
        self.assertEqual((self.bridge.sweep_prefilter([]), self.store.get(L.PREFILTER_REQUESTS)), (1, {}))
        self.assertIsNone(self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=3, typical=52.6,
                                              at=1.0))
        self.assertTrue(self.bridge.demote("fam", why="w", receipt=4, at=2.0))
        fam = self.store.family("fam")
        self.assertEqual((fam["band"], fam["state"]["ladder_demoted"]["receipt"]), ("gym", 4))
        self.assertFalse(self.bridge.demote("fam", why="w", receipt=5, at=3.0), "a Gym family has nothing to lose")

    def test_the_default_bridge_is_the_swarms_store_only(self):
        self.assertIsInstance(L.default_bridge(SimpleNamespace(families=self.families)), L.SwarmBridge)
        from league.live.families import MemoryFamilies

        self.assertIsNone(L.default_bridge(SimpleNamespace(families=MemoryFamilies())))


# ============================================================================================= beside the fast lane
@unittest.skipUnless(HAVE, "numpy not installed")
class TheFastLane(SwarmStoreNights):
    """THE FAST LANE (release F1, Oct 3, 2026), under the tree's own switches: the gate's sealed look is the route to
    Probe, and the forward ladder RECORDS beside it. It blocks nothing and promotes nothing: its table does not bind;
    the gate makes no pre-filter read, so a latched cohort is never answered; and were its table set to bind, THE
    LADDER'S BELT refuses while the look is the route. A band a look earned is not the ladder's to demote."""

    def gate_round(self) -> dict:
        """One round of the gate as the tree ships it, on the swarm's own store."""
        import copy as _copy

        from league.swarm import gate, settings
        from league.tests.test_swarm_rounds import FakeGymPool

        cfg = _copy.deepcopy(settings.DEFAULTS)
        cfg["gym"]["gate_checkpoint"] = "image"
        pool = FakeGymPool(lambda job: self.fail(f"the gate read the holdout: {job.purpose}"))
        return gate.Gate(self.swarm, pool, None, cfg, clock=lambda: 1.0).run()

    def test_the_switches_as_shipped(self):
        from league.swarm import bands, gate

        self.assertIs(gate.SEALED_LOOKS, True, "the sealed look is the route to Probe")
        self.assertIs(bands.TUITION_ROWS, False, "tuition stays retired: no real money before the unseen-market test")
        self.assertIs(CONSTITUTION["options_money"]["ladder"]["binding"], False, "the ladder records")
        self.assertIs(bands.ladder_promotes(), False)

    def test_a_latched_cohort_is_never_answered_and_ends_unpromoted(self):
        """The ladder records beside the look. A cohort meets every forward line and is latched; the House asks the
        gate for the pre-filter's read; the gate, as shipped, makes none (the holdout has one reader, the look). After
        the ladder's wait the cohort ends `complete`, unanswered: no band, no bar, no `would_promote`."""
        from league.swarm import bands

        self.latched()
        self.assertEqual(set(self.requests()), {self.sha}, "the House's request is on record")
        for k in (41, 42, 43, 44):
            self.assertNotIn("prefilter", self.gate_round())
            self.assertEqual((self.night(k)["waiting"], self.swarm.get(L.PREFILTER_KEY + self.sha)), (1, None), k)
        self.gate_round()
        self.assertEqual(self.night(45)["verdicts"], {"unanswered": 1})
        self.assertEqual(self.status()[0], "complete")
        self.assertEqual([r["verdict"] for r in self.receipts()], ["await_prefilter", "unanswered"])
        state = self.swarm.family("fam")["state"]
        self.assertEqual((self.band(), bands.read(self.root), state.get("incubator_barred"), self.swarm.refusals("fam"),
                          self.swarm.look_holds("fam")), (("gym", None), [], None, [], []),
                         "no band, no row, no bar, no refusal, no hold: the ladder blocked nothing")
        self.assertEqual((ops_promotions(self, self.root, self.now[0]), L.counts(self.root, day=self.days[44])["would_promote"]),
                         (0, 0))
        self.assertTrue(any("waited" in a and "pre-filter" in a for a in self.alerts), "the House said the latch waited")

    def test_a_table_set_to_bind_beside_the_look_promotes_nothing(self):
        """`binding` true while `SEALED_LOOKS` is true, decided: the ladder promotes nothing while the look is the route.
        As shipped the gate makes no pre-filter read, so no answer ever comes (above). Even with a passed read on record
        (as a tool that ran evidence v3's own gate would leave), THE LADDER'S BELT refuses: the cohort ends `failed`,
        blocked, and no band is written."""
        from league.swarm import bands

        self.assertEqual(self.bridge.refusal("fam", 1, self.sha), bands.BELT_LOOK_ROUTE, "every other line of the belt is clear")
        self.latched()
        self.gate_reads()
        self.assertEqual(self.night(41, binding=True)["verdicts"], {"blocked": 1})
        answer = self.receipts()[-1]
        self.assertEqual((answer["verdict"], answer["reasons"]), ("blocked", [f"the ladder's belt: {bands.BELT_LOOK_ROUTE}"]))
        self.assertEqual((self.band(), bands.read(self.root), self.status()),
                         (("gym", None), [], ("failed", f"ladder: {bands.BELT_LOOK_ROUTE}")))
        self.assertEqual(ops_promotions(self, self.root, self.now[0]), 0)
        self.assertEqual([e for e in self.swarm.events_after(0) if e["kind"] == "swarm.band"], [], "no band move")

    def test_recording_beside_the_look_the_belt_says_why_it_would_not_promote(self):
        self.latched()
        self.gate_reads()
        self.assertEqual(self.night(41)["verdicts"], {"would_promote": 1})
        from league.swarm import bands

        self.assertEqual(self.receipts()[-1]["stats"]["answer"]["belt"], {"read": True, "refusal": bands.BELT_LOOK_ROUTE})
        self.assertEqual((self.band(), bands.read(self.root), self.status()), (("gym", None), [], ("active", None)))

    def test_the_belts_other_reasons_still_come_first(self):
        from league.swarm import bands

        self.swarm.set_state("fam", robust_failed=[1])
        self.assertIn("demoted", self.bridge.refusal("fam", 1, self.sha))
        self.swarm.set_state("fam", robust_failed=[], validation_line={"passed": False})
        self.assertIn("Validation line", self.bridge.refusal("fam", 1, self.sha))
        self.assertEqual(ladder_refusal_without_a_store(self), bands.BELT_STORE_UNREAD)

    def test_a_band_a_look_earned_is_not_the_ladders_to_demote(self):
        """The ladder's demotion reads the families IT banded (`route` "ladder"). A fast-lane Probe's band is the look's:
        the money table alone moves it (its forward record, its real fills), whatever its record says to the ladder."""
        from league.swarm import bands
        from league.tests.evaluator_fakes import band_proof, passed_look

        version = self.swarm.version("fam", 1)
        self.swarm.set_state("fam", banded_version=1, banded_sha=version["sha"], banded_at=1.0,
                             banded_evaluator=band_proof(version), typical_by_version={"1": 50.0})
        passed_look(self.swarm, "fam", version)
        self.swarm.set_band("fam", "probe", reason="passed its holdout look; the money table moved it")
        [row] = bands.read(self.root)
        self.assertEqual((row["band"], row["holdout_passed"]), ("probe", True))
        self.assertEqual(self.bridge.ladder_families(), [], "no ladder proof: not among the families the ladder demotes")
        self.swarm.add_forward("fam", "real", [{"id": f"t{i}", "day": self.days[40 + i // 2], "pnl": -9.0, "max_loss": 50.0}
                                                for i in range(24)], version=1)
        out = self.night(60, binding=True)
        self.assertEqual((out["demoted"], self.band()[0]), ([], "probe"), "24 losing trades: the ladder moves nothing")
        self.assertEqual([r for r in self.receipts() if r["verdict"] == "demote"], [])


# ================================================================================================== the exit's spot
@unittest.skipUnless(HAVE, "numpy not installed")
class TheExitSpot(unittest.TestCase):
    def day(self, prices):
        under = SimpleNamespace(price=np.array(prices, dtype=float), settle=None, close=None)
        return SimpleNamespace(day=dt.date(2026, 10, 5), open_min=570, chains={"SPY": SimpleNamespace(underlying=under)})

    def test_the_exit_minutes_price_or_the_last_within_five_minutes(self):
        day = self.day([500.0, 501.0, float("nan"), float("nan"), 503.0] + [float("nan")] * 10)
        trade = {"root": "spy", "exit_day": "2026-10-05", "exit_minute": 571}
        self.assertEqual(L.exit_spot(trade, day), 501.0)
        self.assertEqual(L.exit_spot(dict(trade, exit_minute=573), day), 501.0)
        self.assertEqual(L.exit_spot(dict(trade, exit_minute=574), day), 503.0)
        self.assertIsNone(L.exit_spot(dict(trade, exit_minute=584), day), "stale past five minutes")
        self.assertIsNone(L.exit_spot(dict(trade, exit_day="2026-10-06"), day), "another session")
        self.assertIsNone(L.exit_spot(dict(trade, root="QQQ"), day))
        self.assertIsNone(L.exit_spot(trade, None))

    def test_an_expiry_takes_the_settlement_level(self):
        day = self.day([500.0, 502.0])
        self.assertEqual(L.exit_spot({"root": "SPY", "exit_day": "2026-10-05", "exit_minute": None}, day), 502.0)


# ================================================================================================== the live path
from league.tests.live_fakes import MONDAY, at  # noqa: E402
from league.tests.test_live_practice import PracticeCase, trained  # noqa: E402


class TheLivePath(PracticeCase):
    def test_practice_closes_carry_their_exit_spot_and_the_close_judges_the_ladder(self):
        self.clock.set(at(MONDAY, 15, 30))
        self.build(observed=[trained("f", params={"hold": 3, "opens": 3})])
        self.run_to(15, 50)
        db = self.live.observe_store._connect()
        bodies = [json.loads(b) for (b,) in db.execute("SELECT body FROM trades WHERE forced=0")]
        self.assertTrue(bodies, "the program closed trades")
        for b in bodies:
            self.assertIsInstance(b.get("exit_spot"), float)
            self.assertGreater(b["exit_spot"], 0)
            self.assertIsNotNone(L.drift_usd(b), "the drift control's figures are all there")
        [entrant] = self.live.observe_store.entrants(since="2026-01-01")
        self.assertEqual((entrant["family"], entrant["entered_day"]), ("f", MONDAY.isoformat()))
        out = self.run_to(16, 0)
        self.assertEqual(out["ended"], MONDAY.isoformat())
        ladder = out["ladder"]
        self.assertEqual((ladder["day"], ladder["judged"], ladder["verdicts"], ladder["practising"], ladder["bh_size"]),
                         (MONDAY.isoformat(), 0, {}, 1, 1), "its first session's end is no checkpoint: nothing is judged")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM ladder_decisions").fetchone()[0], 0)
        self.assertEqual(self.live.observe_store.entrants(since="2026-01-01")[0]["p_value"], None)
        self.assertEqual([a for a in self.alerts if "ladder" in a[1]], [])

    def test_a_checkpoint_is_left_due_while_closes_of_its_account_are_not_in_the_record(self):
        """The practice export at the close cannot be written (the trades stay in the account, offered again) and a
        checkpoint is due that night: it is not spent on a record known to lack closes, and the next session's end,
        the record whole, judges it."""
        self.clock.set(at(MONDAY, 15, 30))
        self.build(observed=[trained("f", params={"hold": 3, "opens": 3})])
        self.run_to(15, 58)
        store = self.live.observe_store
        db = store._connect()
        [acc] = [a for k, a in self.live.shadow.accounts.items() if k.endswith(":o")]
        stored = db.execute("SELECT COUNT(*) FROM trades WHERE forced=0").fetchone()[0]
        self.assertGreater(stored, 0)
        self.assertEqual(self.live.practice_unexported(), set())
        # One more program close of today, booked by the engine and not yet exported (as an expiry settled at the close).
        acc.trades.append(dict(acc.trades[-1], id=f"{acc.trades[-1]['id']}-late"))
        with patch.object(store, "add", return_value=False), patch.object(L, "checkpoint_due", return_value=40):
            out = self.run_to(16, 0)
            self.assertEqual(self.live.practice_unexported(), {("f", 1)})
        ladder = out["ladder"]
        self.assertEqual((ladder["deferred"], ladder["judged"], ladder["verdicts"], ladder["practising"]), (1, 0, {}, 0))
        self.assertEqual((db.execute("SELECT COUNT(*) FROM ladder_decisions").fetchone()[0],
                          store.ladder_state("f", 1)["judged"]), (0, {}), "the checkpoint is not spent")
        self.assertEqual(self.live.observe_store.entrants(since="2026-01-01")[0]["p_checkpoint"], None)
        told = [text for _, text in self.alerts if "left f@1's 40-session checkpoint due" in text]
        self.assertEqual(len(told), 1, self.alerts)
        # The closes reach the record at a later export; the next session's end judges the checkpoint on all of them.
        self.live._export_shadow()
        self.assertEqual((self.live.practice_unexported(),
                          db.execute("SELECT COUNT(*) FROM trades WHERE forced=0").fetchone()[0]), (set(), stored + 1))
        with patch.object(L, "checkpoint_due", return_value=40):
            later = L.end_of_day(self.live, MONDAY.isoformat())
        self.assertEqual((later["deferred"], later["judged"]), (0, 1))
        closes, checkpoint = db.execute("SELECT stats, checkpoint FROM ladder_decisions").fetchone()
        self.assertEqual((json.loads(closes)["closes"], checkpoint, list(store.ladder_state("f", 1)["judged"])),
                         (stored + 1, 40, [40]))

    def the_session_end_with_a_ladder_that_fails(self, failing, said: str) -> None:
        """The hook's guard (`OptionsLive._end_of_day`): with the ladder's session end failing, the session still ends
        (`ended_day` written, the shadow book saved after it, `ended` returned), the House alerts once, and the ladder is
        not run again that day."""
        self.clock.set(at(MONDAY, 15, 30))
        self.build(observed=[trained("f", params={"hold": 3, "opens": 3})])
        self.run_to(15, 50)
        self.assertIsNone(self.live.state.get("ended_day"))
        saved, save = [], self.live.shadow.save
        def saving():
            saved.append(self.live.state.get("ended_day"))
            return save()

        with failing as failed, patch.object(self.live.shadow, "save", side_effect=saving):
            out = self.run_to(16, 0)
            self.assertTrue(failed.called, "the ladder's session end was reached")
        self.assertEqual((out["state"], out["ended"]), ("after the close", MONDAY.isoformat()))
        self.assertNotIn("ladder", out)
        self.assertEqual(self.live.state.get("ended_day"), MONDAY.isoformat())
        self.assertEqual(saved[-1], MONDAY.isoformat(), "the shadow book is saved after the day is marked ended")
        told = [text for _, text in self.alerts if "the forward ladder's session end failed" in text]
        self.assertEqual(len(told), 1, self.alerts)
        self.assertIn(said, told[0])
        with patch.object(L.Ladder, "end_of_day", side_effect=AssertionError("run twice in one day")) as again:
            later = self.run_to(16, 3)
        self.assertEqual((again.call_count, later["state"]), (0, "after the close"), "the session's end runs once a day")
        self.assertNotIn("ended", later)
        self.assertEqual(len([t for _, t in self.alerts if "the forward ladder's session end failed" in t]), 1)
        self.assertEqual(self.venue.sent, [])

    def test_a_ladder_that_raises_never_stops_the_session_end(self):
        self.the_session_end_with_a_ladder_that_fails(
            patch.object(L.Ladder, "end_of_day", side_effect=RuntimeError("the practice record is locked")),
            "RuntimeError: the practice record is locked")

    def test_a_refused_money_table_never_stops_the_session_end(self):
        self.the_session_end_with_a_ladder_that_fails(
            patch.object(L.Rules, "from_constitution", side_effect=ValueError("the forward ladder's table is refused: x")),
            "ValueError: the forward ladder's table is refused: x")


from league.tests.test_live_step import HAVE as HAVE_LIVE, LiveCase  # noqa: E402
from league.tests.live_fakes import VERTICAL  # noqa: E402


@unittest.skipUnless(HAVE_LIVE, "numpy not installed")
class TheLadderProbeLive(LiveCase):
    """A ladder promotion read by the House's own path (`SwarmFamilies`, `OptionsLive`), IN THE LADDER'S OWN MODE
    (`ladders_own_gate`: sealed looks off): real money only from the session after it, the money table's type and fit
    checks, and the practice receipt the live path reads (the WP6 review). As shipped the look is the route and a
    ladder proof gives the live path no row at all, whatever its receipt (`bands.read`; `league/tests/test_fast_lane.py`
    holds that, and the last test here)."""

    def setUp(self):
        super().setUp()
        ladders_own_gate(self)

    def ladder_live(self, *, structure="debit_vertical", typical=50.0, promoted_at=None):
        from league.live.families import SwarmFamilies
        from league.swarm.gate import run_sha
        from league.swarm.store import SwarmStore

        live = self.make([])
        self.addCleanup(live.observe_store.close)
        store = SwarmStore(self.root)
        self.addCleanup(store.close)
        store.add_family({"id": "vert", "mechanism": "An invented mechanism for the ladder's live test.",
                          "structure": structure, "roots": ["SPY"], "dte": [0, 2]}, origin="test")
        version = store.add_version("vert", VERTICAL, {"hold": 600}, author="test")
        sha = run_sha(version)
        store.set_state("vert", validation_version=1, validation_line={"passed": True})
        live.families = SwarmFamilies(self.root)
        self.addCleanup(lambda: live.families._store.close() if live.families._store is not None else None)
        live.account_row = self.venue.account()
        receipt = live.observe_store.add_decision({"day": MONDAY.isoformat(), "family": "vert", "version": 1,
                                                   "run_sha": sha, "inputs": "x", "stats": {}, "verdict": "promote",
                                                   "binding": True})
        snapshot = {"code": VERTICAL, "params": {"hold": 600}, "run_sha": sha,
                    "practice_evaluator": live.observe_store.evaluator}
        self.assertIsNone(L.SwarmBridge(live.families).promote(
            family="vert", version=1, snapshot=snapshot, receipt=receipt, typical=typical,
            at=self.clock() if promoted_at is None else promoted_at))
        return live, store, receipt

    def test_a_ladder_probe_trades_real_money_only_from_the_session_after_its_promotion(self):
        live, store, _ = self.ladder_live()                  # promoted in the session (a late session end's judgement)
        self.run_to(9, 40)
        self.assertEqual(store.family("vert")["band"], "probe")
        self.assertIn("vert@1:s", live.instances)
        self.assertNotIn("vert@1:r", live.instances, "no real instance the session it was promoted")
        self.assertEqual(self.venue.sent, [])
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 9, 31))
        live.minute()
        real = live.instances["vert@1:r"]
        self.assertEqual((real.code, real.params, real.version), (VERTICAL, {"hold": 600}, 1),
                         "exactly the practised program")
        self.assertEqual(len(self.venue.sent), 1)

    def test_a_ladder_probe_whose_type_is_not_real_is_held_at_candidate(self):
        live, store, _ = self.ladder_live(structure="long_straddle", promoted_at=at(MONDAY - dt.timedelta(days=3), 16, 5))
        self.run_to(9, 35)
        self.assertEqual(store.family("vert")["band"], "candidate")
        self.assertNotIn("vert@1:r", live.instances)
        self.assertEqual(self.venue.sent, [])

    def test_a_ladder_probe_whose_typical_unit_does_not_fit_is_held_at_candidate(self):
        live, store, _ = self.ladder_live(typical=5000.0, promoted_at=at(MONDAY - dt.timedelta(days=3), 16, 5))
        self.run_to(9, 35)
        self.assertEqual(store.family("vert")["band"], "candidate")
        self.assertNotIn("vert@1:r", live.instances)
        self.assertEqual(self.venue.sent, [])
        held = [p for p, _ in self.ledger.of("live.band") if p.get("to") == "candidate"]
        self.assertIn("over the Probe's cap", held[0]["why"])

    def test_a_ladder_band_without_its_receipt_never_trades(self):
        live, store, receipt = self.ladder_live(promoted_at=at(MONDAY - dt.timedelta(days=3), 16, 5))
        self.assertEqual([r["family"] for r in live.families.read()], ["vert"], "with its receipt: a row")
        live.observe_store._connect().execute("UPDATE ladder_decisions SET verdict='blocked' WHERE id=?", (receipt,))
        self.run_to(9, 35)
        self.assertEqual(live.families.read(), [])
        self.assertNotIn("vert@1:r", live.instances)
        self.assertNotIn("vert@1:s", live.instances)
        self.assertEqual(self.venue.sent, [])

    def test_as_shipped_a_ladder_band_with_its_receipt_never_trades_either(self):
        """THE LOOK IS THE ROUTE: the same promoted band, its receipt in the House's record, under the shipped switch."""
        from league.swarm import bands

        live, store, receipt = self.ladder_live(promoted_at=at(MONDAY - dt.timedelta(days=3), 16, 5))
        self.assertEqual([r["family"] for r in live.families.read()], ["vert"], "the ladder's own mode: a row")
        with patch("league.swarm.gate.SEALED_LOOKS", True):
            self.assertEqual((bands.read(self.root), live.families.read()), ([], []))
            self.run_to(9, 35)
            self.assertEqual((live.instances, self.venue.sent, store.family("vert")["band"]), ({}, [], "probe"))


# ================================================================================================== the scoreboard
class TheCounts(StoreCase):
    def test_counts_only_never_a_figure_or_a_name(self):
        self.assertEqual(L.counts(self.root / "nowhere")["entrants"], 0)
        for i in range(5):
            self.store.freeze(self.program(f"f{i}"), day="2026-10-05")
        receipt = {"day": "2026-11-02", "version": 1, "inputs": "x", "stats": {}, "binding": True}
        pending = self.store.add_decision({**receipt, "family": "f0", "verdict": L.PROMOTE_PENDING})
        self.store.add_decision({**receipt, "family": "f3", "verdict": L.PROMOTE_PENDING})
        self.store.add_decision({**receipt, "family": "f4", "verdict": L.PROMOTE_VOID})
        self.assertEqual(L.counts(self.root, day="2026-11-02")["promoted"], 0, "a pending or void receipt is no promotion")
        self.store.settle_answer(pending, "promote", day="2026-11-02", close="promoted", reason="r")
        self.store.close_cohort("f1", 1, status="failed", day="2026-11-02", reason="r")
        self.store.add_decision({"day": "2026-11-02", "family": "f2", "version": 1, "inputs": "x", "stats": {},
                                 "verdict": "would_promote", "binding": False})
        out = L.counts(self.root, day="2026-11-02")
        self.assertEqual({k: out[k] for k in ("entrants", "in_practice", "promoted", "failed", "demoted", "would_promote")},
                         {"entrants": 5, "in_practice": 3, "promoted": 1, "failed": 1, "demoted": 0, "would_promote": 1})
        self.store.close_cohort("f0", 1, status="demoted", day="2026-12-02", reason="r", was=("promoted",))
        later = L.counts(self.root, day="2026-12-02")
        self.assertEqual((later["promoted"], later["demoted"]), (1, 1), "a promotion made stays one; its demotion is apart")
        self.assertEqual(L.counts(self.root, day="2026-12-15")["would_promote"], 1, "written once: counted on later days")
        self.assertEqual(L.counts(self.root, day="2026-11-01")["would_promote"], 0, "not before it was written")
        self.assertEqual(L.counts(self.root, day="2027-03-01")["would_promote"], 0, "nor once it left the trailing window")
        self.assertNotIn("f2", json.dumps(out))
        self.assertTrue(all(isinstance(v, (int, bool)) for v in out.values()))


if __name__ == "__main__":
    unittest.main()
