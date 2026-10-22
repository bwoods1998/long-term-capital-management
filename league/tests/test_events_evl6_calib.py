"""PREREG-EVL-6's screen reproduces its own calibration (release 1019i; the frozen text, section 4.1: docs/prereg/evl-6/).

THE ORCHESTRATOR'S CHECK: "your screen must reproduce them exactly on their own synthetic inputs". The reference
implementations are the frozen directory's calib_v2.py (the generator of section 4.2 on the widened grid, its values,
guards, p, q and issuer guard per program and session), search_final.py (the schedule, alpha(S), PASS, RETIRE, the end of
a run and run 2) and demotion_v2.py (a Probe stay's fixed reads, its money stop over the whole stay, its lower tail and
its Sized move, in section 3's order). Each runs here on its own synthetic arrays (invented returns, none a market's),
SYNTHETIC ONLY; its per-session draws are captured as it runs (a trace of its own frame, nothing in it changed), and
league/events/screen.py's and bands.py's functions are run over the same draws:

- THE STATISTIC: at every session where calib_v2 computed p (and q), screen.v6_count_p of screen.v6_values (v6_lower)
  over the same blocks gives the same p (q), to the float32 the calibration stores; exact below 17 blocks (all 2^S
  vectors, no injection), else over the calibration's own fixed 19,999 vectors (it applies them to |y|; they are turned
  into vectors over y, `flips`), its issuer guard over its own 999.
- THE DECISIONS: screen.v6_judge's RETIRE and PASS at section 2's looks (22, 25, 30, 35, 40, 50, 60; alpha 0.020 / 0.006
  / 0.001; the minimums), run 1's end at its 60th block and run 2 from the 61st block, for every program: the same first
  pass, first retirement and end as search_final.first_pass and its run 2 on calib_v2's arrays.
- THE STAY: bands.read_p6 (the fixed reads at the 100th, 200th, ... real event, p <= 0.15), bands.money_stop6 (10% of the
  whole stay's buy cost), screen.v6_judge's lower tail and PASS at the stay's looks, in section 3's order, give
  demotion_v2.simulate_stay's demotion (when and by which trigger) and its Sized move (when) for every stay.

numpy runs the calibration (the frozen scripts' own dependency); the lane's code is the standard library's. Skipped when
numpy is not installed. Each case runs its scripts from their own directory with their array folders in a temporary
directory (TMPDIR), never in the tree.
"""

from __future__ import annotations

import datetime as dt
import importlib
import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path

from league.events import bands as BA
from league.events import screen as SC

try:
    import numpy as np

    HAVE_NUMPY = True
except ImportError:  # pragma: no cover - the calibration needs numpy
    HAVE_NUMPY = False

REPO = Path(__file__).resolve().parents[2]
CALIB = REPO / "docs" / "prereg" / "evl-6"
#: The chosen rule as the frozen directory records it (chosen_v2.json, demotion_v2.json): section 1.3's schedule.
RULE = "[22, [[30, 0.02], [40, 0.006], [60, 0.001]]]"
DAY0 = dt.date(2030, 1, 1)
NONE = 10 ** 6


def scripts():
    """The frozen calibration's modules, imported from docs/prereg/evl-6 with their array folders in TMPDIR."""
    arrays = tempfile.mkdtemp(prefix="evl6-calib-arrays-")
    os.environ["V2_ARR"] = arrays
    os.environ["FINAL_ARR"] = arrays
    if str(CALIB) not in sys.path:
        sys.path.insert(0, str(CALIB))
    names = ("calib_final", "calib_v2", "search_final", "demotion_final", "demotion_v2")
    keep = sys.dont_write_bytecode
    sys.dont_write_bytecode = True       # (never a __pycache__ in the frozen directory)
    try:
        return {name: importlib.import_module(name) for name in names}
    finally:
        sys.dont_write_bytecode = keep


def capture(fn, code, line_text, names):
    """Run `fn()` and keep, per session `t`, the locals `names` of `code`'s frame at its first line whose text is
    `line_text` (a trace of the script's own frame: nothing in it is changed)."""
    src, start = inspect.getsourcelines(code)
    line = next(start + i for i, text in enumerate(src) if text.strip() == line_text)
    caps: dict[int, dict] = {}

    def local(frame, event, arg):
        if event == "line" and frame.f_lineno == line:
            got = frame.f_locals
            t = int(got["t"])
            if t not in caps:
                caps[t] = {k: (got[k].copy() if hasattr(got[k], "copy") else got[k]) for k in names}
        return local

    def tracer(frame, event, arg):
        return local if event == "call" and frame.f_code is code.__code__ else None
    sys.settrace(tracer)
    try:
        out = fn()
    finally:
        sys.settrace(None)
    return out, caps


def over_y(signs):
    """The calibration's fixed sign vectors over |y| as vectors over y (s o sign(y), as little-endian bytes)."""
    def source(values):
        y = np.asarray(values, float)
        s = signs[:, :y.size] * np.where(y < 0, -1.0, 1.0)
        return [bytes(row) for row in np.packbits(s > 0, axis=1, bitorder="little")]
    return source


def plain(flips):
    """The calibration's issuer guard's vectors (applied to the values themselves) as little-endian bytes."""
    def source(values):
        n = len(values)
        return [bytes(row) for row in np.packbits(flips[:, :n] > 0, axis=1, bitorder="little")]
    return source


def sessions_of(caps, r):
    """Program r's events (TRADABLE, its own ranking by the draw order) and its control's a, by session."""
    out = {}
    for t, c in sorted(caps.items()):
        mine = np.nonzero(c["er"] == r)[0]
        if mine.size == 0:
            continue
        day = DAY0 + dt.timedelta(days=t)
        events = [{"event": f"e{t:04d}-{int(c['pos'][i]):05d}-{i}", "entry_day": day, "a": float(c["a"][i]),
                   "r": float(c["rr_"][i]), "issuer": f"{int(c['ei'][i]):05d}", "tradable": True,
                   "rank_key": -float(c["pos"][i]), "adv20": None}
                  for i in mine if c["sel"][i]]
        control = [{"entry_day": day, "a": float(c["a"][i]), "tradable": True} for i in mine]
        out[t] = (events, control)
    return out


class TheRunsReproduceCalibV2(unittest.TestCase):
    """calib_v2.py's statistic and search_final.py's decisions, reproduced on calib_v2.py's own arrays."""

    CELLS = (
        # (a true 60 bp edge at 13 a session, rho_day 0.05: passes in run 1 and in run 2)
        ("P60|sym|nodrift", dict(nbar=13, rho_day=0.05, skill=0.006), 18, 120, 123_456),
        # (a cost-only program, -60 bp, crash days with a t(3) body clustered in high volatility: retirements)
        ("cost|bothTC", dict(nbar=8, rho_day=0.15, phi_day=0.20, mu_family=-0.006, day="crasht3cl", ev_left=1.4,
                             ev_right=0.6, jump_left=0.8), 14, 120, 223_456),
        # (the knife-edge null at the worst plausible cell's shape, counts that follow the day: ends, run 2)
        ("N3|bothTC|AR10|phi0.20|cnt", dict(nbar=3, rho_day=0.15, phi_day=0.20, skill=0.006, mu_family=-0.006,
                                            day="crasht3cl", ev_left=1.4, ev_right=0.6, jump_left=0.8,
                                            drift_sd=0.0010, cnt_kappa=0.3, mw_knife=14), 14, 120, 323_456),
    )

    @classmethod
    def setUpClass(cls):
        if not HAVE_NUMPY:
            raise unittest.SkipTest("numpy not installed (the frozen calibration's own dependency)")
        cls.m = scripts()

    def one_run(self, sessions, *, after_block, control, issuer_flips, flips, checks):
        """Run 1 (`after_block` 0) or run 2 (60) of one program by the lane's functions: ('pass' | 'retire' | 'end' |
        None, the session)."""
        j, record, ctl, seen_blocks = 0, [], [], 0
        for t in sorted(sessions):
            events, control_rows = sessions[t]
            if not events:
                continue
            seen_blocks += 1
            if seen_blocks <= after_block:
                continue
            record.append(events)
            ctl.extend(control_rows)
            blocks = SC.blocks6([e for evs in record for e in evs])
            S = len(blocks)
            if S > SC.V6_RUN_BLOCKS:
                return None, None
            flat = [e for b in blocks for e in b.events]
            if j < len(SC.V6_LOOKS) and S >= SC.V6_LOOKS[j] and \
                    SC.v6_minimums(len(flat), len({e["issuer"] for e in flat}), S):
                judged = SC.v6_judge(blocks, program="CAL", version=1, tag="", control_rows=ctl, control="CTRL",
                                     flips=flips, issuer_flips=issuer_flips, beside=False)
                checks.append((t, judged))
                j = max(i for i in range(len(SC.V6_LOOKS)) if S >= SC.V6_LOOKS[i]) + 1
                if judged["decision"] in ("pass", "retire"):
                    return judged["decision"], t
            if S >= SC.V6_RUN_BLOCKS:
                return "end", t
        return None, None

    def test_every_programs_p_q_and_decisions_are_the_calibrations(self):
        V, CF, SF = self.m["calib_v2"], self.m["calib_final"], self.m["search_final"]
        rule = SF.Rule.of(RULE)
        self.assertEqual((rule.start, rule.pieces), (SC.V6_LOOKS[0], SC.V6_ALPHAS), "the rule section 1.3 states")
        self.assertEqual((CF.CAP, CF.MARGIN, CF.MIN_EV, CF.MIN_ISS, CF.MIN_BLK, CF.ISS_G, CF.S_RUN, CF.TIE, CF.EXACT_S),
                         (SC.V6_CAP, SC.V6_MARGIN, SC.V6_MIN_EVENTS, SC.V6_MIN_ISSUERS, SC.V6_MIN_BLOCKS,
                          SC.V6_ISSUER_P, SC.V6_RUN_BLOCKS, SC.TIE, SC.V6_EXACT))
        self.assertEqual(SF.LOOKS[SF.LOOKS.index(22):], SC.V6_LOOKS)
        decisions = compared = ps = qs = 0
        flips = over_y(CF._signs())
        for label, kw, R, T, seed in self.CELLS:
            g = V.Gen2(**kw)
            (out, _info), caps = capture(lambda: V.simulate(g, R, T, seed, run2=True), V.simulate,
                                         "for rec in recs:", ("t", "er", "ei", "a", "rr_", "sel", "pos"))
            issuers = plain(np.where(np.random.default_rng(seed + 77_777).random((CF.B_ISS_G, g.U)) < 0.5, -1.0, 1.0))
            fp, fr, fe = SF.first_pass(out, "", rule)
            fp2, _, _ = SF.first_pass(out, "_2", rule)
            for r in range(R):
                sessions = sessions_of(caps, r)
                checks: list = []
                got, at = self.one_run(sessions, after_block=0, control=True, issuer_flips=issuers, flips=flips,
                                       checks=checks)
                want = ("pass", fp[r]) if fp[r] < NONE else ("retire", fr[r]) if fr[r] < NONE else \
                    ("end", fe[r]) if fe[r] < NONE else (None, None)
                self.assertEqual((got, at), want, (label, r))
                decisions += 1
                for t, judged in checks:
                    P, Q = out["P"][r, t - 1], out["Q"][r, t - 1]
                    if not np.isnan(P) and P < 1.0:
                        self.assertEqual(np.float32(judged["p"]), P, (label, r, t, "p"))
                        ps += 1
                    if not np.isnan(Q) and Q < 1.0:
                        self.assertEqual(np.float32(judged["q"]), Q, (label, r, t, "q"))
                        qs += 1
                if got == "end":
                    got2, at2 = self.one_run(sessions, after_block=SC.V6_RUN_BLOCKS, control=True, issuer_flips=issuers,
                                             flips=flips, checks=[])
                    self.assertEqual(at2 if got2 == "pass" else NONE, fp2[r], (label, r, "run 2"))
                    compared += 1
        self.assertGreater(decisions, 40)
        self.assertGreater(compared, 3, "run 2 compared")
        self.assertGreater(ps + qs, 20, "p and q compared at the looks the calibration computed them")

    def test_the_exact_count_below_17_blocks_is_every_vector(self):
        """S <= 16 (section 1.3): every one of the 2^S vectors, the calibration's own enumeration of patterns over |y|
        (calib_final.signflip_p_rows), with no injected vector; S >= 17: the seeded Monte Carlo of the seed string."""
        CF = self.m["calib_final"]
        rng = np.random.default_rng(7)
        for S in (6, 9, 12, 16):
            for _ in range(5):
                y = rng.normal(0.0005, 0.01, S)
                want = float(CF.signflip_p_rows(y[None, :], S)[0])
                self.assertEqual(SC.v6_count_p(list(y), "unused", 1), want, S)
        y = list(rng.normal(0.001, 0.01, 22))
        text = SC.v6_seed_string("EVL-X", 3, "", 22)
        self.assertEqual(text, "EVL-X|v3|evl6|S22")
        flips = SC._flips(SC.seed_of(text), 22, 999)
        self.assertEqual(SC.v6_count_p(y, text, 999), (1 + SC._count(y, flips)) / 1000)


class TheStayReproducesDemotionV2(unittest.TestCase):
    """demotion_v2.py's stays: the lane's reads, money stop, lower tail and Sized, in section 3's order."""

    CELLS = (
        ("60bp|dayskewTC", dict(nbar=30, skill=0.006, rho_day=0.15, phi_day=0.20, drift_sd=0.0020, day="crasht3cl",
                                jump_left=0.5), 12, 90, 424_242),
        ("-15bp (cost only)|base", dict(nbar=30, skill=0.006, mu_family=-0.0075, rho_day=0.05), 12, 90, 524_242),
        ("0bp (knife)|bothTC", dict(nbar=13, skill=0.006, mu_family=-0.006, rho_day=0.15, phi_day=0.20,
                                    drift_sd=0.0020, day="crasht3cl", ev_left=1.4, ev_right=0.6, jump_left=0.8), 12, 120,
         624_242),
    )

    @classmethod
    def setUpClass(cls):
        if not HAVE_NUMPY:
            raise unittest.SkipTest("numpy not installed (the frozen calibration's own dependency)")
        cls.m = scripts()

    def stay(self, caps, r, *, flips, read_flips, read_p, alpha_of):
        """One stay of program r by the lane's functions, in section 3's order: (dem_at, why, sized_at)."""
        DV = self.m["demotion_v2"]
        band, nreal, nxt = 0, 0, 0
        blocks: list = []
        real: list[dict] = []
        sized_at = -1
        lots = {0: DV.LOT_P, 1: DV.LOT_S}
        caps_by_band = {0: DV.CAP_P, 1: DV.CAP_S}
        for t, c in sorted(caps.items()):
            if band >= 2 or nreal >= DV.N_MAX:
                break
            mine = np.nonzero(c["er"] == r)[0]
            sel = [i for i in mine if c["sel"][i]]
            day = DAY0 + dt.timedelta(days=t)
            if sel:
                blocks.append([{"event": f"e{t:04d}-{int(c['pos'][i]):05d}", "entry_day": day, "a": float(c["a"][i]),
                                "r": float(c["rr_"][i]), "issuer": f"{int(c['ei'][i]):05d}", "tradable": True,
                                "rank_key": -float(c["pos"][i]), "adv20": None} for i in sel])
            look = None
            if sel:
                stay_blocks = SC.blocks6([e for b in blocks[:SC.V6_RUN_BLOCKS + 1] for e in b])
                S = len(blocks)
                flat = [e for b in blocks for e in b]
                if S <= SC.V6_RUN_BLOCKS and nxt < len(SC.V6_LOOKS) and S >= SC.V6_LOOKS[nxt] and \
                        SC.v6_minimums(len(flat), len({e["issuer"] for e in flat}), S):
                    nxt = max(i for i in range(len(SC.V6_LOOKS)) if S >= SC.V6_LOOKS[i]) + 1
                    look = (S, stay_blocks, flat)
            cap = caps_by_band[band]
            mine_real = sorted((i for i in sel if c["pos"][i] <= cap), key=lambda i: c["pos"][i])
            lot = lots[band]
            new = [{"entry_day": day.isoformat(), "r": float(c["rr_"][i]), "pnl": lot * float(c["rr_"][i]), "cost": lot}
                   for i in mine_real][:DV.N_MAX + 200 - nreal]
            k0, k1 = nreal, nreal + len(new)
            demoted = None
            every = real + new
            for kk in range((k0 // BA.READ_EVERY + 1) * BA.READ_EVERY, k1 + 1, BA.READ_EVERY):
                if BA.read_p6(every[:kk], "unused", 1, flips=read_flips) <= read_p + SC.TIE:
                    demoted = (kk, 3)
                    break
            if demoted is None:
                real, nreal = every, k1
                if new and BA.money_stop6(real):
                    demoted = (nreal, 1)
            if demoted is None and look is not None:
                S, stay_blocks, flat = look
                mean_a = SC._mean([e["a"] for e in flat])
                alpha = alpha_of(S)
                q = SC.v6_count_p(SC.v6_lower(stay_blocks), "unused", 1, flips=flips)
                if mean_a < 0 and q <= alpha + SC.TIE:
                    demoted = (nreal, 2)
                elif band == 0:
                    tops = [e for b in stay_blocks for e in b.top()]
                    guards = (mean_a > 0 and SC._mean([e["r"] for e in flat]) > 0 and SC._mean([e["a"] for e in tops]) > 0
                              and SC._mean([e["r"] for e in tops]) > 0)
                    if guards:
                        p = SC.v6_count_p(SC.v6_values(stay_blocks), "unused", 1, flips=flips)
                        pnl = sum(e["pnl"] for e in real)
                        if p <= alpha and nreal >= BA.SIZED_MIN6 and pnl > 0:
                            band, sized_at = 1, nreal
            if demoted is not None:
                return demoted[0], demoted[1], sized_at
        return NONE, 0, sized_at

    def test_every_stays_demotion_and_sized_move_are_demotion_v2s(self):
        V, CF, SF, DF, DV = (self.m[k] for k in ("calib_v2", "calib_final", "search_final", "demotion_final",
                                                   "demotion_v2"))
        rule = SF.Rule.of(RULE)
        self.assertEqual((DV.READ_EVERY, DV.CAP_P, DV.CAP_S), (BA.READ_EVERY, SC.V6_CAP, 8))
        flips = over_y(CF._signs())
        read_flips = over_y(DF._signs_r(400))
        compared = moved = demoted = 0
        for label, kw, R, T, seed in self.CELLS:
            g = V.Gen2(**kw)
            got, caps = capture(lambda: DV.simulate_stay(g, R, T, seed, rule, BA.READ_P, f"whole:{BA.STOP_SHARE}"),
                                DV.simulate_stay, "hr = np.nonzero(has)[0]", ("t", "er", "ei", "a", "rr_", "sel", "pos"))
            for r in range(R):
                mine = self.stay(caps, r, flips=flips, read_flips=read_flips, read_p=BA.READ_P,
                                 alpha_of=lambda S: SC.v6_alpha(S))
                want = (int(got["dem_at"][r]), int(got["why"][r]), int(got["sized_at"][r]))
                self.assertEqual(mine, want, (label, r))
                compared += 1
                moved += mine[2] >= 0
                demoted += mine[0] < NONE
        self.assertGreater(compared, 30)
        self.assertGreater(demoted, 3, "demotions compared")


if __name__ == "__main__":
    unittest.main()
