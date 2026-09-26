"""Regression tests for the adversarial review of PR #358 (Sept 26, 2026), one per finding, each
failing before its fix; plus W4's needs for the validation and gate views. Synthetic stores only."""

import datetime as dt
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import batch as B
    from league.gym import ctx as C
    from league.gym import engine as E
    from league.gym import events as EV
    from league.gym import fills as F
    from league.gym import results as RS
    from league.gym import runtime as R
    from league.gym import store as S
    from league.gym import synth
    from league.gym.safety import CodeRefused, check_program

REPO = Path(__file__).resolve().parents[2]
D1, D2, D3, D4 = dt.date(2023, 3, 6), dt.date(2023, 3, 7), dt.date(2023, 3, 8), dt.date(2023, 3, 9)


def trade(day, pnl, max_loss, qty=1):
    return {"day": day, "pnl": pnl, "max_loss": max_loss, "qty": qty, "return_on_max_loss": pnl / max_loss, "fees": 0.0}


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class ReviewFindings(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="gym-review-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def store(self, name, days, build):
        w = synth.Writer(self.dir / name)
        w.calendar(days)
        build(w)
        w.finish()
        return S.Store(self.dir / name)

    def run_one(self, store, code, roots=("SPY",), days=None, **cfg):
        [r] = E.run([R.load_program(code, name="p")], store, E.RunConfig(window="train", roots=roots, **cfg), days=days)
        return r

    # (1) the lines' t is on DAILY-aggregated returns: splitting a day's trade into five moves nothing.
    def test_1_t_daily_is_invariant_to_splitting_trades(self):
        rng = np.random.default_rng(5)
        returns = rng.normal(0.02, 0.2, 80)
        days = [(dt.date(2023, 1, 2) + dt.timedelta(days=i)).isoformat() for i in range(80)]
        whole = [trade(d, 100 * r, 100.0) for d, r in zip(days, returns)]
        split = [trade(d, 20 * r, 20.0) for d, r in zip(days, returns) for _ in range(5)]
        daily = [[d, 0.0, 0.0] for d in days]
        a, b = RS.summarize(whole, daily, 10_000.0), RS.summarize(split, daily, 10_000.0)
        self.assertAlmostEqual(a["t_daily"], b["t_daily"], places=6)
        self.assertEqual((a["days_traded"], b["days_traded"]), (80, 80))
        self.assertGreater(abs(b["t_stat"]), 2 * abs(a["t_stat"]))    # the per-trade t is what splitting inflates
        self.assertEqual((a["trades"], b["trades"]), (80, 400))
        self.assertEqual(a["median_max_loss_per_structure"], 100.0)
        self.assertEqual(b["median_max_loss_per_structure"], 20.0)

    # (2) stress charges passive fills too, and a passive order never fills into a move in its favour.
    PASSIVE = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.2, "cadence": 5, "start": 600}
PARAMS = {}
STATE = {"opened": False}
def decide(ctx):
    if not STATE["opened"]:
        STATE["opened"] = True
        return [{"open": "debit_vertical", "legs": [{"side": "long", "right": "C", "dte": 1, "strike": 400},
                 {"side": "short", "right": "C", "dte": 1, "strike": 401}], "qty": 1, "limit": "mid"}]
    if ctx.minute >= 700 and ctx.positions and not ctx.orders:
        return [{"close": ctx.positions[0]["id"], "limit": "mid"}]
    return []
'''

    def test_2_stress_charges_passive_fills(self):
        store = self.store("s2", [D1], lambda w: synth.flat_day(w, "SPY", D1, [
            {"expiration": D2, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.20)}},
            {"expiration": D2, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.60)}}], prices=400.5))
        model = F.FillModel(hazard={f"q{q}|m|d{d}|k{k}|t{t}": 0.3 for q in range(6) for d in range(4) for k in range(4) for t in range(3)})
        pnl = [self.run_one(store, self.PASSIVE, fill_model=model, stress=s)["summary"]["pnl"] for s in (1.0, 1.5, 3.0)]
        self.assertGreater(pnl[0], pnl[1])
        self.assertGreater(pnl[1], pnl[2])

    def test_2_no_passive_fill_into_a_favourable_move(self):
        rising = {m: (2.00 + 0.01 * (m - 571), 2.20 + 0.01 * (m - 571)) for m in range(571, 961)}
        falling = {m: (2.00 - 0.001 * (m - 571), 2.20 - 0.001 * (m - 571)) for m in range(571, 961)}
        model = F.FillModel(hazard={f"q{q}|m|d{d}|k{k}|t{t}": 1.0 for q in range(6) for d in range(4) for k in range(4) for t in range(3)})
        opener = self.PASSIVE.replace("ctx.minute >= 700", "ctx.minute >= 10000")
        for name, quotes, fills in (("up", rising, 0), ("down", falling, 1)):
            store = self.store(name, [D1], lambda w, q=quotes: synth.flat_day(w, "SPY", D1, [
                {"expiration": D2, "strike": 400, "right": "C", "quotes": q},
                {"expiration": D2, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.60)}}], prices=400.5))
            r = self.run_one(store, opener, fill_model=model)
            self.assertEqual(r["fills"]["opens"], 1)
            self.assertEqual(r["summary"]["trades"], fills, name)

    # (3) a timeout cannot be swallowed, re-arms through `finally`, and a batch kills a runaway worker.
    def test_3_a_swallowed_timeout_still_counts(self):
        code = ("NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    try:\n        x = 0\n        while True:\n"
                "            x += 1\n    except Exception:\n        pass\n    return [{'cancel': 1}]\n")
        runner = R.load_program(code).start(timeout=0.05)
        self.assertEqual(runner.decide(None), [])
        self.assertEqual(runner.timeouts, 1)
        for body in ("    try:\n        pass\n    except:\n        pass\n    return []\n",
                     "    try:\n        pass\n    except BaseException:\n        pass\n    return []\n"):
            with self.assertRaises(CodeRefused):
                check_program("NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n" + body)

    def test_3_the_alarm_re_arms_through_finally(self):
        code = ("NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    try:\n        while True:\n            pass\n"
                "    finally:\n        n = 0\n        while n < 10 ** 12:\n            n += 1\n    return []\n")
        script = ("import sys\nfrom league.gym.runtime import load_program\nr = load_program(sys.stdin.read()).start(timeout=0.05)\n"
                  "print(r.decide(None), r.timeouts)\n")
        try:
            done = subprocess.run([sys.executable, "-c", script], input=code, capture_output=True, text=True, cwd=REPO, timeout=30)
        except subprocess.TimeoutExpired:
            self.fail("a finally-block loop outlived its timeout")
        self.assertEqual(done.stdout.strip(), "[] 1", done.stderr)

    def test_3_a_runaway_worker_is_killed(self):
        store = self.store("s3", [D1], lambda w: synth.flat_day(w, "SPY", D1, [
            {"expiration": D2, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.20)}}], prices=400.5))
        jobs = [("p", self.PASSIVE, {}), ("q", self.PASSIVE.replace("600", "605"), {})]
        doc = B.run_batch(jobs, store_root=str(store.root), window="train", roots=["SPY"], workers=2, unit_timeout=3,
                          _fault_hang=60)
        self.assertEqual([r["status"] for r in doc["results"]], ["error", "error"])
        self.assertIn("timed out", doc["results"][0]["reason"])

    # (4) a long leg sold at a zero bid does not cap the close: a stop still gets out.
    def test_4_zero_bid_wing_does_not_block_a_close(self):
        store = self.store("s4", [D1], lambda w: synth.flat_day(w, "SPY", D1, [
            {"expiration": D2, "strike": 400, "right": "P", "quotes": {571: (1.00, 1.05), 700: (0.30, 0.35)}},
            {"expiration": D2, "strike": 395, "right": "P", "quotes": {571: (0.05, 0.10), 700: (0.00, 0.05, 0, 100)}}],
            prices=400.5))
        code = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.2, "cadence": 5, "start": 600}
PARAMS = {}
STATE = {"opened": False}
def decide(ctx):
    if not STATE["opened"]:
        STATE["opened"] = True
        return [{"open": "credit_vertical", "legs": [{"side": "short", "right": "P", "dte": 1, "strike": 400},
                 {"side": "long", "right": "P", "dte": 1, "strike": 395}], "qty": 2}]
    if ctx.minute >= 705 and ctx.positions and not ctx.orders:
        return [{"close": ctx.positions[0]["id"]}]
    return []
'''
        [t] = self.run_one(store, code)["trades"]
        self.assertEqual((t["entry"], t["exit"], t["exit_reason"]), (-0.90, -0.35, "program"))

    # (5) no program can make a handed-out array writeable; `flags` is refused.
    def test_5_arrays_are_immutable(self):
        snap = C.Snapshot("SPY", 700, 400.0, [0, 0], [400.0, 401.0], [True, True], [1.0, 0.5], [1.1, 0.6], [5, 5], [5, 5])
        view = snap.view(snap.slice_index(0, 1, 0.1))
        under = C.underlying_view("SPY", [400.0, 401.0], closes=[399.0])
        for arr in (view.bid, view.ask, view.mid, view.strike, view.id, view.delta, under.prices, under.closes):
            with self.assertRaises(ValueError):
                arr.setflags(write=True)
            with self.assertRaises(ValueError):
                arr.flags["WRITEABLE"] = True
        with self.assertRaises(CodeRefused):
            check_program("NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    ctx.chain.bid.flags['WRITEABLE'] = True\n    return []\n")

    # (6) an expiry that falls between run days is settled, not carried as a zombie.
    CARRY = '''
NEEDS = {"roots": ["XSP"], "dte": [0, 5], "band": 0.2, "cadence": 5, "start": 600}
PARAMS = {}
STATE = {"opened": False}
def decide(ctx):
    if not STATE["opened"]:
        STATE["opened"] = True
        return [{"open": "credit_vertical", "legs": [{"side": "short", "right": "C", "dte": 1, "strike": 452},
                 {"side": "long", "right": "C", "dte": 1, "strike": 455}], "qty": 1}]
    return []
'''

    def test_6_expiry_between_run_days_settles(self):
        def build(w, d2_underlying):
            synth.flat_day(w, "XSP", D1, [
                {"expiration": D2, "strike": 452, "right": "C", "quotes": {571: (0.50, 0.55)}},
                {"expiration": D2, "strike": 455, "right": "C", "quotes": {571: (0.15, 0.18)}}], prices=450.0)
            if d2_underlying:
                w.underlying("XSP", D2, list(range(570, 961)), [452.40] * 391)
            synth.flat_day(w, "XSP", D3, [{"expiration": D4, "strike": 450, "right": "C", "quotes": {571: (1.0, 1.1)}}],
                           prices={570: 453.0})
        for hole, expected_exit, reason in ((False, -0.40, "settled"), (True, -1.00, "settled_data_hole")):
            store = self.store(f"s6{hole}", [D1, D2, D3], lambda w, h=hole: build(w, not h))
            r = self.run_one(store, self.CARRY, roots=("XSP",))
            [t] = r["trades"]
            self.assertEqual((t["exit"], t["exit_reason"]), (expected_exit, reason))
            self.assertEqual(t["exit_day"], D2.isoformat() if not hole else D3.isoformat())

    # (7) a marketable order's remainder takes the better natural; a debit over the width is refused.
    def test_7_remainder_at_the_natural_and_no_debit_over_the_width(self):
        store = self.store("s7", [D1], lambda w: synth.flat_day(w, "SPY", D1, [
            {"expiration": D2, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10, 3), 602: (1.80, 2.00, 100)}},
            {"expiration": D2, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.50, 100)}},
            {"expiration": D2, "strike": 402, "right": "C", "quotes": {571: (0.80, 0.90, 100)}}], prices=400.5))
        code = self.PASSIVE.replace('"qty": 1, "limit": "mid"', '"qty": 5, "limit": "natural"').replace(
            "ctx.minute >= 700", "ctx.minute >= 10000")
        [t] = self.run_one(store, code)["trades"]
        self.assertEqual(t["entry"], round((3 * 0.70 + 2 * 0.60) / 5, 4))
        over = code.replace('"strike": 401}', '"strike": 402}').replace('"strike": 400}', '"strike": 400}')
        # 400/402 call vertical: 2.10 - 0.80 = 1.30 debit on a 2.00 width is fine; make the width 1 with a 1.10 debit:
        wide = self.store("s7b", [D1], lambda w: synth.flat_day(w, "SPY", D1, [
            {"expiration": D2, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10)}},
            {"expiration": D2, "strike": 401, "right": "C", "quotes": {571: (1.00, 1.50)}}], prices=400.5))
        r = self.run_one(wide, code)
        self.assertEqual(r["summary"]["trades"], 0)
        self.assertTrue(any("never pay" in k for k in r["fills"]["reject_reasons"]), r["fills"]["reject_reasons"])
        del over

    # (8) repr is gone (addresses are not deterministic) and ctx objects print without addresses.
    def test_8_no_addresses(self):
        with self.assertRaises(CodeRefused):
            check_program("NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return [{'note': repr(ctx)}]\n")
        snap = C.Snapshot("SPY", 700, 400.0, [0], [400.0], [True], [1.0], [1.1])
        view = snap.view(snap.slice_index(0, 1, 0.1))
        for obj in (view, C.underlying_view("SPY", [400.0]), C.Ctx(minute=700)):
            self.assertNotIn("0x", str(obj))
            self.assertNotIn("0x", repr(obj))

    # (9) the run's identity names the engine code, the tables and the calendar.
    def test_9_identity_covers_code_tables_and_calendar(self):
        def build(half):
            return lambda w: synth.flat_day(w, "SPY", D1, [
                {"expiration": D2, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.20)}}], prices=400.5)
        a = self.store("s9a", [D1, D2], build(False))
        b_dir = self.dir / "s9b"
        shutil.copytree(a.root, b_dir)
        synth.Writer(b_dir).calendar([D1, D2], half_days=[D2])     # only the calendar differs
        b = S.Store(b_dir)
        ra, rb = self.run_one(a, self.PASSIVE, days=[D1]), self.run_one(b, self.PASSIVE, days=[D1])
        self.assertNotEqual(ra["run_id"], rb["run_id"])
        self.assertIn("code", ra)
        self.assertIn("tables", ra)
        saved = EV.FOMC
        try:
            EV.FOMC = frozenset(EV.FOMC | {D1})
            rc = self.run_one(a, self.PASSIVE, days=[D1])
        finally:
            EV.FOMC = saved
        self.assertNotEqual(ra["run_id"], rc["run_id"])

    # (10) a validation run returns the validation view only, with what the lines need; no cuts.
    def test_10_validation_runs_return_the_view(self):
        v1, v2 = dt.date(2025, 3, 3), dt.date(2025, 3, 4)
        store = self.store("s10", [v1, v2], lambda w: [synth.flat_day(w, "SPY", d, [
            {"expiration": d, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.20)}},
            {"expiration": d, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.60)}}], prices=400.5) for d in (v1, v2)])
        code = self.PASSIVE.replace('"dte": 1', '"dte": 0').replace('"limit": "mid"', '"limit": "natural"')
        doc = B.run_batch([("p", code, {})], store_root=str(store.root), window="validation", roots=["SPY"])
        [v] = doc["results"]
        for banned in ("trades", "daily", "worst", "segments", "start", "end"):
            self.assertNotIn(banned, v)
        hashes = ("run_id", "run_sha", "program_sha", "result_sha", "data_version", "fill_model", "code", "tables")
        text = RS.canonical({k: x for k, x in v.items() if k not in hashes})     # a hex hash may hold "2025" by chance
        self.assertNotIn("2025", text)
        self.assertNotIn("-03-0", text)
        for key in ("sharpe_daily", "days", "skew_daily", "kurt_daily", "t_daily", "days_traded", "trades", "quarters_positive",
                    "median_max_loss_per_structure"):
            self.assertIn(key, v["summary"])
        self.assertIn("stress_1.5", v)
        self.assertIn("pnl", v["stress_1.5"])
        self.assertNotIn("first_day", doc["batch"])
        with self.assertRaises(ValueError):
            B.run_batch([("p", code, {})], store_root=str(store.root), window="validation", roots=["SPY"], start=v1)

    def test_10_views_by_window(self):
        result = {"run_id": "x", "window": "holdout", "status": "ok", "trials": 1, "summary": {"pnl": 1.0}, "fills": {},
                  "daily": [["2026-03-02", 1.0, 1.0]], "trades": [{"day": "2026-03-02", "pnl": 1.0, "max_loss": 50.0, "legs": [],
                                                                  "context": {"spot": 1}}], "breakdown": {}, "runtime": {}}
        holdout = RS.view(result, "holdout")
        self.assertEqual(holdout["daily"], result["daily"])
        self.assertNotIn("trades", holdout)
        forward = RS.view(result, "forward")
        self.assertEqual(forward["trades"], [{"day": "2026-03-02", "pnl": 1.0, "max_loss": 50.0}])
        self.assertIn("daily", forward)

    # (12) index settlement uses a recorded settlement when the store has one; a forced back leg is valued at its natural.
    def test_12_recorded_settlement_and_forced_mark_at_the_natural(self):
        store = self.store("s12", [D1], lambda w: synth.flat_day(w, "XSP", D1, [
            {"expiration": D1, "strike": 452, "right": "C", "quotes": {571: (0.50, 0.55)}},
            {"expiration": D1, "strike": 455, "right": "C", "quotes": {571: (0.15, 0.18)}}],
            prices={570: 450.0, 960: 452.30}, extra={"settle": 452.80}))
        [t] = self.run_one(store, self.CARRY.replace('"dte": 1', '"dte": 0'), roots=("XSP",))["trades"]
        self.assertEqual((t["exit"], t["exit_reason"]), (-0.80, "settled"))
        cal = self.store("s12b", [D1, D2], lambda w: synth.flat_day(w, "SPY", D1, [
            {"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (1.00, 1.05), 929: (None, None)}},
            {"expiration": D2, "strike": 400, "right": "C", "quotes": {571: (3.00, 3.20)}}], prices={570: 400.0, 940: 399.0}))
        code = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 5], "band": 0.2, "cadence": 5, "start": 600}
PARAMS = {}
STATE = {"opened": False}
def decide(ctx):
    if not STATE["opened"]:
        STATE["opened"] = True
        return [{"open": "calendar", "legs": [{"side": "short", "right": "C", "dte": 0, "strike": 400},
                 {"side": "long", "right": "C", "dte": 1, "strike": 400}], "qty": 1}]
    return []
'''
        [t] = self.run_one(cal, code, days=[D1])["trades"]
        self.assertEqual(t["exit_reason"], "forced_mark")
        self.assertEqual(t["exit"], 3.00)                    # the long back leg at its bid, not its 3.10 mid
        self.assertEqual(t["fees"], 0.05 + 0.05 + 0.06)      # open (buy 3.20, sell 1.00) and the back leg's sale at 3.00


if __name__ == "__main__":
    unittest.main()
