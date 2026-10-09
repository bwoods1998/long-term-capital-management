"""RELEASE D-1b (Oct 9, 2026): the direction lane switched to the D2 screen and the Oct 9 goal's reporting terms, on top of
release D-1 (league/swarm/dlane.py; the operator's DSCREEN-ADOPT, a REPORTED LOOSENING; the SPEC's items 1-5, item 6 is
docs):

1. D2 ON: the committed policy chooses D2 and pins DSCREEN-2's receipt (sha c3605947, c 1.00, its lane figures), CI holds
   the sha to docs/benchmarks/direction_screen_2.json (test_dlane.Screen), the statistic is DSCREEN-2's to the digit on
   exact figures and never passes on the Gym's rounding what the exact statistic fails, swarm.json `dlane.screen` "S-C"
   reverts at once, and the alpha lane is untouched;
2. CALLS ONLY: `dlane.structures` ["long_single"] (a direction debit vertical and a put are refused at the card; D2 only
   while the lane is calls only) and the Train bar C1 (every Train trade a long call);
3. ONE VALIDATION TRY AND ONE HOLDOUT LOOK PER DIRECTION LINEAGE (the lineage retires once either is used without a pass
   still in play); the alpha lane keeps its counts;
4. THE FALSE-POSITIVE RATE BESIDE EVERY LOOK, BAND ROW, PROBE TRADE AND REAL CLOSE (operator-facing only);
5. (league/tests/test_ops_budget.py TwoDayLead: the meter warning two days before research runs out, once a day.)

Invented stores, results and figures only, but for the committed policy and receipt (aggregate figures, public)."""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
import random
import types
import unittest
from pathlib import Path
from unittest import mock

from league.gym import results as GR
from league.swarm import cards, dlane, evidence
from league.swarm import settings as S
from league.swarm.gate import Gate, run_sha
from league.swarm.tournament import Tournament
from league.tests import REAL_POLICY_PATH
from league.tests.swarm_fakes import result
from league.tests.test_dlane import always_in, run as train_run
from league.tests.test_dlane_report import Fixture as ReportFixture
from league.tests.test_swarm_rounds import RoundCase, strong, weak

PASS = {"text": json.dumps({"verdict": "pass", "reasons": []})}
RECEIPT_SHA = "c36059470d00241db67e1542361097e397289b87f024261b96da2db323c63b5b"
#: The committed policy document (the repository's league/swarm/policy.json), parsed.
POLICY = json.loads(Path(REAL_POLICY_PATH).read_text())
COMMITTED = {"dlane": copy.deepcopy(POLICY["dlane"])}
#: A holdout whose daily P&L alternates 12 and 0 (it passes S-C against a Validation Sharpe of 3), and one that loses.
HOLDOUT_DAILY = [12.0 if i % 2 else 0.0 for i in range(250)]
LOSING_DAILY = [-3.0 if i % 2 else 1.0 for i in range(250)]


_READ_POLICY = S.read_policy


def committed_policy(path=None):
    """`settings.read_policy` reading the committed file (the tests' own layer is empty)."""
    return _READ_POLICY(REAL_POLICY_PATH)


# ================================================================================================== 1. D2 ON
class ReferenceD2:
    """DSCREEN-2's expressions, transcribed from its pinned code (dscreen2.py `eval_world2`, sha 6f7010e5; MONEY's
    `mlib.entry_moments`, sha ce5d36a0) for one program, as plain Python: the reference the swarm's D2 is held to. BUILD.md's
    proof runs the pinned numpy code itself on the same kind of fixtures."""

    @staticmethod
    def entry_moments(xs):
        n = len(xs)
        mean = sum(xs) / max(n, 1)
        m2 = sum((x - mean) ** 2 for x in xs) / max(n, 1)
        sd = math.sqrt(m2 * n / max(n - 1, 1))
        return n, mean, sd

    @classmethod
    def pooled_t(cls, rv, rl):
        n, mean, sd = cls.entry_moments(list(rv) + list(rl))
        return mean / sd * math.sqrt(n) if n >= 2 and sd > 0 else -math.inf

    @classmethod
    def passes(cls, trades_v, rv, rl, holdout_pnl, c):
        nv, mean_v, _ = cls.entry_moments(rv)
        pre = trades_v >= 50 and nv >= 25 and mean_v > 0
        return pre and holdout_pnl > 0 and cls.pooled_t(rv, rl) >= c


def window(rng, start, sessions, p_entry, mu, sd, two=0.15):
    """Invented Gym trades over `sessions` days from `start` (an ordinal), one or two a day, and their daily rows."""
    trades = []
    for i in range(sessions):
        if rng.random() > p_entry:
            continue
        day = dt.date.fromordinal(start + i).isoformat()
        for _ in range(2 if rng.random() < two else 1):
            loss = round(rng.uniform(40, 130), 2)
            pnl = round(max(-1.0, rng.gauss(mu, sd)) * loss, 2)
            trades.append({"day": day, "pnl": pnl, "max_loss": loss, "fees": 1.3, "qty": 1,
                           "return_on_max_loss": round(pnl / loss, 4)})
    daily: dict[str, float] = {}
    for t in trades:
        daily[t["day"]] = daily.get(t["day"], 0.0) + t["pnl"]
    return trades, [[d, p, 10000.0] for d, p in sorted(daily.items())]


def exact(trades, returns):
    """A summary with the window's moments unrounded (the Gym's fields at full precision)."""
    m = sum(returns) / len(returns)
    sd = math.sqrt(sum((x - m) ** 2 for x in returns) / (len(returns) - 1))
    return {"trades": len(trades), "days_traded": len({t["day"] for t in trades}), "pnl": sum(t["pnl"] for t in trades),
            "mean_return_on_max_loss_daily": m, "t_daily": m / sd * math.sqrt(len(returns))}


class TheD2Statistic(unittest.TestCase):
    def fixtures(self, n=300, seed=20261009):
        rng = random.Random(seed)
        out = []
        while len(out) < n:
            mu, sd = rng.choice([-0.05, 0.0, 0.02, 0.05, 0.1]), rng.uniform(0.4, 0.9)
            tv, dv = window(rng, 739253, 252, rng.uniform(0.15, 0.5), mu, sd)
            tl, dl = window(rng, 739653, 184, rng.uniform(0.15, 0.5), mu, sd)
            rv, rl = GR.daily_returns(tv), GR.daily_returns(tl)
            if len(rv) >= 2 and len(rl) >= 2:
                out.append((tv, dv, tl, dl, rv, rl))
        return out

    def test_on_exact_figures_it_is_dscreen2s_statistic_to_the_digit(self):
        for tv, _, tl, _, rv, rl in self.fixtures():
            ref = ReferenceD2.pooled_t(rv, rl)
            got = dlane.d2_pooled_t(exact(tv, rv), exact(tl, rl))
            self.assertAlmostEqual(got, ref, places=12)

    def test_on_the_gyms_summaries_a_pass_is_always_a_pass_of_the_exact_statistic(self):
        """The Gym rounds the daily mean to 6 decimals and the t to 4: D2 is judged on the statistic's lower bound over
        that rounding, so no pass comes from the rounding; the point figure stays within the rounding of the exact one."""
        decided = 0
        for tv, dv, tl, dl, rv, rl in self.fixtures():
            sv, sl = GR.summarize(tv, dv, 10000.0), GR.summarize(tl, dl, 10000.0)
            ref = ReferenceD2.pooled_t(rv, rl)
            low = dlane.d2_pooled_t_low(sv, sl)
            point = dlane.d2_pooled_t(sv, sl)
            if low is None:
                continue
            self.assertLessEqual(low, ref + 1e-12, "the bound is below the exact statistic")
            self.assertLessEqual(low, point + 1e-12)
            verdict = dlane.d2_verdict(sv, sl, 1.0)
            want = ReferenceD2.passes(len(tv), rv, rl, sum(t["pnl"] for t in tl), 1.0)
            if verdict["passed"]:
                self.assertTrue(want, "never a pass the exact rule fails")
            if abs(ref - 1.0) > 0.05:
                self.assertEqual(verdict["passed"], want)
                decided += 1
            self.assertEqual(verdict["checks"]["precheck"], len(tv) >= 50 and len(rv) >= 25 and sum(rv) / len(rv) > 0)
            self.assertEqual(verdict["checks"]["pnl"], sum(t["pnl"] for t in tl) > 0)
        self.assertGreater(decided, 250)

    def test_the_figures_it_cannot_read_fail_closed_and_one_entry_day_is_exact(self):
        val = {"trades": 60, "days_traded": 40, "mean_return_on_max_loss_daily": 0.05, "t_daily": 1.0, "pnl": 10.0}
        one = {"trades": 1, "days_traded": 1, "mean_return_on_max_loss_daily": 0.3, "t_daily": None, "pnl": 12.0}
        rv = [0.05 + 0.25 * (1 if i % 2 else -1) for i in range(40)]  # mean 0.05; a t of its own
        sv = exact([{"day": str(i), "pnl": 1.0} for i in range(40)], rv)
        self.assertAlmostEqual(dlane.d2_pooled_t(sv, one), ReferenceD2.pooled_t(rv, [0.3]), places=12,
                               msg="one holdout entry day: its return alone, exactly as dscreen2 pools it")
        for bad in ({**one, "days_traded": 3}, {**val, "t_daily": 0.0}, {**val, "mean_return_on_max_loss_daily": 0.0},
                    {**val, "days_traded": 0}, {**val, "days_traded": True}, None):
            self.assertIsNone(dlane.d2_pooled_t(val, bad), bad)
            self.assertIsNone(dlane.d2_pooled_t_low(val, bad), bad)
            self.assertFalse(dlane.d2_verdict(val, bad, 1.0)["passed"])
        self.assertFalse(dlane.d2_verdict(val, {**val, "pnl": 0.0}, 0.5)["checks"]["pnl"], "holdout P&L above zero")
        self.assertFalse(dlane.d2_verdict({**val, "trades": 49}, val, 0.5)["checks"]["precheck"])
        self.assertFalse(dlane.d2_verdict(val, val, None)["passed"], "no c, no pass")

    def test_the_lane_computes_the_gates_run_sha(self):
        version = {"sha": "abc123", "params": {"x": 1, "y": [2, 3]}}
        self.assertEqual(dlane._run_sha(version), run_sha(version))


class TheCommittedScreen(unittest.TestCase):
    def test_the_committed_policy_runs_d2_on_its_receipt_and_states_its_figures(self):
        with mock.patch.object(S, "read_policy", committed_policy):
            screen = dlane.screen_effective(COMMITTED, "direction")
        self.assertEqual((screen["screen"], screen["receipt"], screen["c"], screen["validation"]),
                         ("D2", RECEIPT_SHA, 1.0, "precheck"))
        self.assertEqual({k: screen[k] for k in ("fp_lane_mixed", "fp_lane_2224", "fp_lane_ci_mixed", "fp_lane_cluster_mixed",
                                                  "power10", "fp_unconditional")},
                         {"fp_lane_mixed": 0.1037, "fp_lane_2224": 0.1239, "fp_lane_ci_mixed": [0.0957, 0.1116],
                          "fp_lane_cluster_mixed": [0.079, 0.1276], "power10": 0.1995, "fp_unconditional": 0.1037})
        self.assertEqual(dlane.fp_beside(screen), {"screen": "D2", "fp_lane_mixed": 0.1037, "fp_lane_2224": 0.1239,
                                                   "receipt": RECEIPT_SHA})
        self.assertLessEqual(screen["fp_lane_2224"], 0.15, "the owner's ceiling: at most 15% per program at zero edge")
        # The tests' own (empty) policy layer pins nothing: D2 is refused there, whatever a setting says.
        self.assertEqual(dlane.screen_effective(COMMITTED, "direction")["screen"], "S-C")

    def test_swarm_json_s_c_reverts_at_once_and_is_never_a_pin(self):
        """THE ROLLBACK: swarm.json `dlane.screen` "S-C" over the committed policy is S-C on the next settings read; a
        swarm.json that names its own receipt or figures moves nothing (a receipt is pinned only by the repository)."""
        import tempfile

        with tempfile.TemporaryDirectory() as d, mock.patch.object(S, "read_policy", committed_policy):
            root = Path(d)
            self.assertEqual(dlane.screen_effective(S.load(root, policy=POLICY), "direction")["screen"], "D2")
            (root / "swarm.json").write_text(json.dumps({"dlane": {"screen": "S-C"}}))
            back = dlane.screen_effective(S.load(root, policy=POLICY), "direction")
            self.assertEqual((back["screen"], back["receipt"], back["look_level"], back["sharpe_share"]),
                             ("S-C", None, 0.2, 0.25))
            self.assertEqual((back["fp_lane_mixed"], back["fp_lane_2224"]), (0.0141, 0.0209), "S-C's own rates beside it")
            (root / "swarm.json").write_text(json.dumps({"dlane": {"screens": {"D2": {"receipt_sha256": "f" * 64, "c": 0.5,
                                                                                      "fp_lane_mixed": 0.01}}}}))
            forged = dlane.screen_effective(S.load(root, policy=POLICY), "direction")
            self.assertEqual((forged["receipt"], forged["c"], forged["fp_lane_mixed"]), (RECEIPT_SHA, 1.0, 0.1037))
            # A swarm.json that widens the lane past single calls refuses D2 (it was measured on calls only).
            (root / "swarm.json").write_text(json.dumps({"dlane": {"structures": ["long_single", "debit_vertical"]}}))
            wide = dlane.screen_effective(S.load(root, policy=POLICY), "direction")
            self.assertEqual(wide["screen"], "S-C")
            self.assertIn("single calls", wide["why"])

    def test_the_alpha_lane_is_untouched(self):
        with mock.patch.object(S, "read_policy", committed_policy):
            alpha = dlane.screen_effective(COMMITTED, "alpha")
        self.assertEqual((alpha["screen"], alpha["look_level"], alpha["sharpe_share"], alpha["receipt"]),
                         ("S-B", evidence.LOOK_LEVEL, evidence.HOLDOUT_SHARPE_SHARE, None))
        self.assertEqual((evidence.LOOK_LEVEL, evidence.HOLDOUT_SHARPE_SHARE, evidence.LOOKS_PER_LINEAGE,
                          evidence.MIN_TRADES, evidence.MIN_DAYS, evidence.MIN_T), (0.10, 0.5, 3, 50, 25, 1.65))
        self.assertIsNone(alpha["fp_lane_mixed"])
        fam = {"id": "a", "spec": {}}
        self.assertEqual(dlane.looks_ration(None, fam, COMMITTED), 3)
        self.assertEqual(dlane.looks_ration(None, {"id": "d", "spec": {"lane": "direction"}}, COMMITTED), 1)
        self.assertEqual(dlane.looks_ration(None, {"id": "d", "spec": {"lane": "direction"}}, {"dlane": {"mode": "off"}}), 3,
                         "the rollback: every lane is alpha")


# ================================================================================================== 2. calls only
class CallsOnly(unittest.TestCase):
    CARD = {"lane": "direction", "hypothesis": "x" * 80, "mechanism_class": "equity_premium", "inputs": ["underlying_price"],
            "holding": "days_4_10", "cost": {"hurdle": 0.2, "why": "y" * 40}, "comparison": "z" * 60,
            "ablation": {"param": "gate_on", "off": 0},
            "falsification": "it loses money: its P&L is below 0 over every Train year"}

    def test_the_card_check_refuses_a_direction_debit_vertical_and_a_put(self):
        for structure in ("debit_vertical", "long_put"):
            errors = dlane.card_errors(self.CARD, structure, ["SPY"], COMMITTED)
            self.assertTrue(any(e.startswith("structure:") for e in errors), (structure, errors))
            self.assertIn("buys calls only", " ".join(errors))
            card, errs = cards.validate(self.CARD, structure, roots=["SPY"], settings=COMMITTED)
            self.assertIsNone(card, structure)
            self.assertTrue(any(e.startswith("structure:") for e in errs))
        self.assertEqual(dlane.card_errors(self.CARD, "long_single", ["SPY"], COMMITTED), [])
        card, errs = cards.validate(self.CARD, "long_single", roots=["SPY"], settings=COMMITTED)
        self.assertEqual((card or {}).get("lane"), "direction", errs)
        self.assertEqual(dlane.cfg(COMMITTED)["structures"], ["long_single"])

    def test_c1_fails_a_train_run_that_bought_a_put_or_sold_a_leg(self):
        call = {"right": "C", "side": "long", "strike": 600.0, "dte": 7, "ratio": 1}
        def trades(*legs, year="2023"):
            return [{"day": f"{year}-03-{d + 1:02d}", "root": "SPY", "max_loss": 70.0, "fees": 2.6, "qty": 1, "pnl": 1.0,
                     "legs": [dict(leg) for leg in legs]} for d in range(20)]
        clean = dlane.train_score(train_run({"2022": (-1500.0, -3.9, {}), "2023": (2600.0, 2.1, {}), "2024": (2400.0, 1.9, {})},
                                            trades_2024=trades(call)), settings=COMMITTED)
        self.assertNotIn("C1", clean["fails"])
        self.assertTrue(dlane.calls_only({"trades": trades(call)}))
        for bad in ({**call, "right": "P"}, {**call, "side": "short"}):
            r = train_run({"2022": (-1500.0, -3.9, {}), "2023": (2600.0, 2.1, {}), "2024": (2400.0, 1.9, {})},
                          trades_2024=trades(call) + trades(bad))
            score = dlane.train_score(r, settings=COMMITTED)
            self.assertEqual(score["fails"][0], "C1")
            self.assertFalse(score["eligible"])
            self.assertTrue(score["why"].startswith("fails C1: the direction lane buys calls only"))
            self.assertFalse(any(ch.isdigit() for ch in score["why"].replace("C1", "")), "rules only in its words")
        # Unread is no failure: no legs written (a stored score, a fixture), or no Train-year trade (an older year).
        self.assertIsNone(dlane.calls_only(always_in()))
        self.assertIsNone(dlane.calls_only({"trades": trades({**call, "right": "P"}, year="2021")}))
        self.assertNotIn("C1", dlane.train_score(always_in(), settings=COMMITTED)["fails"])
        # A C1 failure beside E5 is not counted as "the unit only" (A7's count).
        import tempfile

        from league.swarm.store import SwarmStore

        with tempfile.TemporaryDirectory() as d:
            store = SwarmStore(Path(d))
            try:
                for fid, fails in (("c1-and-e5", ["C1", "E5"]), ("e5-only", ["E5"])):
                    store.add_family({"id": fid, "mechanism": "a mechanism sentence long enough", "structure": "long_single",
                                      "roots": ["SPY"], "lane": "direction"}, origin="architect")
                    dlane.record(store, fid, 1, score={"objective": dlane.OBJECTIVE, "fails": fails, "eligible": False})
                counts = dlane.failure_counts(store, 48.0)
            finally:
                store.close()
        self.assertEqual((counts["versions"], counts["unit_only"], counts["fails"]["E5"]), (2, 1, 2))

    def test_the_brief_and_the_lanes_block_say_calls_only_and_the_ration_with_no_figure(self):
        brief = dlane.brief_text(COMMITTED, ["SPY"])
        lanes = dlane.lanes_text(COMMITTED)
        for text in (brief, lanes):
            self.assertIn("no put", text)
            self.assertIn("ONE VALIDATION TRY AND ONE HOLDOUT LOOK", text)
            for figure in ("0.1037", "10.37", "12.39", "0.1239", "1.41", "2017", "2019", "2020", "2021", "2025", "2026",
                           "c36059", "receipt"):
                self.assertNotIn(figure, text, figure)
        self.assertIn("(C1) every trade is a long call", brief)
        # A lane that still admits verticals keeps D-1's words (and runs S-C).
        wide = {"dlane": {"mode": "gate", "structures": ["long_single", "debit_vertical"]}}
        self.assertNotIn("C1", dlane.brief_text(wide))
        self.assertEqual(dlane.brief_text({"dlane": {"mode": "off"}}), "")
        self.assertEqual(dlane.ration_text({"dlane": {"mode": "off"}}), "")


# ================================================================================================== 3. one try, one look
class TheRation(RoundCase):
    def setUp(self):
        super().setUp()
        self.settings["dlane"] = {"mode": "gate"}
        # THE EXTENSION HOLD (the operator's, R11-4) spares a family that met six of the line's checks from every
        # retirement rule, the ration's too, until the operator clears it: off here, so the rule itself is seen.
        self.settings["researcher"]["extension_hold_checks"] = 0

    def t(self):
        return Tournament(self.store, self.pool, self.settings)

    def new_best(self, fid, text="# v2"):
        fam = self.store.family(fid)
        v = self.store.add_version(fid, f"{text}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\ndef decide(ctx):\n    return []\n",
                                   {}, author="r")
        self.store.update_family(fid, best_version=v["n"])
        return v["n"]

    def child(self, parent, fid):
        fam = self.store.add_family({"id": fid, "mechanism": "the same idea on more roots", "structure": "iron_condor",
                                     "roots": ["SPY", "QQQ"], "lane": "direction"}, origin="fork", parent=parent)
        v = self.store.add_version(fid, f"# {fid}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\ndef decide(ctx):\n    return []\n",
                                   {}, author="fork")
        self.store.update_family(fid, best_version=v["n"])
        return fam

    def why(self, fid):
        t = self.t()
        return t._why(self.store.family(fid), t.identity(), frozenset())

    def test_a_failed_try_is_the_lineages_only_one_and_it_retires(self):
        self.answer = weak
        self.family("d", lane="direction")
        out = self.t().validate(self.store.families(alive=True))
        self.assertFalse(out["judged"]["d"]["passed"])
        state = self.store.family("d")["state"]
        self.assertEqual({k: state[dlane.TRY_KEY][k] for k in ("version", "first", "entered")},
                         {"version": 1, "first": True, "entered": False})
        self.assertEqual(self.why("d"), dlane.SPENT_TRY)
        jobs = len(self.pool.jobs)
        self.new_best("d")
        self.answer = strong
        out = self.t().validate(self.store.families(alive=True))
        self.assertEqual((out["spent_lane"], len(self.pool.jobs)), (["d"], jobs), "no second Validation try")
        self.assertFalse(dlane.try_open(self.store, self.store.family("d"), 2, self.settings))
        self.assertTrue(dlane.try_open(self.store, self.store.family("d"), 1, self.settings), "the try itself, again")
        self.assertFalse(any(ch.isdigit() for ch in dlane.SPENT_TRY.replace("one", "")), "a public cause: no figure")

    def test_the_alpha_lane_keeps_its_counts(self):
        self.answer = weak
        self.family("a")
        self.t().validate(self.store.families(alive=True))
        self.new_best("a")
        self.answer = strong
        out = self.t().validate(self.store.families(alive=True))
        self.assertTrue(out["judged"]["a"]["passed"], "an alpha family's second version is validated, as before")
        self.assertNotIn("spent_lane", out)
        self.assertNotIn(dlane.TRY_KEY, self.store.family("a")["state"])
        self.assertIsNone(self.why("a"))

    def test_the_rollback_reads_no_ration(self):
        self.settings["dlane"] = {"mode": "off"}
        self.answer = weak
        self.family("d", lane="direction")
        self.t().validate(self.store.families(alive=True))
        self.new_best("d")
        self.answer = strong
        out = self.t().validate(self.store.families(alive=True))
        self.assertTrue(out["judged"]["d"]["passed"])
        self.assertNotIn(dlane.TRY_KEY, self.store.family("d")["state"])
        self.assertIsNone(dlane.lineage_spent(self.store, self.store.family("d"), self.settings))

    def test_one_member_of_a_lineage_a_round_then_none(self):
        self.answer = weak
        self.family("d", lane="direction")
        self.child("d", "d-on-qqq")
        out = self.t().validate(self.store.families(alive=True))
        self.assertEqual(sorted(out["judged"]), ["d"])
        self.assertEqual(out["waiting_lane"], ["d-on-qqq"])
        self.assertEqual([j.family for j in self.pool.jobs], ["d"])
        out = self.t().validate(self.store.families(alive=True))
        self.assertEqual(out["spent_lane"], ["d-on-qqq"])
        self.assertEqual(self.why("d-on-qqq"), dlane.SPENT_TRY, "a member with no try of its own retires")

    def test_the_backstop_a_late_second_try_never_enters_the_gate(self):
        self.answer = weak
        self.family("d", lane="direction")
        self.child("d", "d-on-qqq")
        self.t().validate(self.store.families(alive=True))
        late = strong(types.SimpleNamespace(family="d-on-qqq", window="validation", stress=1.0, name="d-on-qqq"))
        row = self.t().judge("d-on-qqq", 1, late, record=True)
        self.assertEqual((row["passed"], row["refused"]), (False, "not its direction lineage's one Validation try"))
        state = self.store.family("d-on-qqq")["state"]
        self.assertFalse(state.get("gate_ready"))
        self.assertNotIn("validation_line", state)
        self.assertEqual([e["payload"]["action"] for e in self.store.events_after(0)
                          if e["kind"] == "swarm.status" and e["family"] == "d-on-qqq"], ["lane_try_refused"])
        self.assertEqual(len(dlane.lineage_tries(self.store, "d")), 2, "its rows and trials are recorded")

    def test_a_run_the_gym_could_not_make_is_no_try(self):
        self.answer = lambda job: result(job.name, window=job.window, status="error")
        self.family("d", lane="direction")
        self.t().validate(self.store.families(alive=True))
        self.assertEqual(dlane.lineage_tries(self.store, "d"), [])
        self.assertNotIn(dlane.TRY_KEY, self.store.family("d")["state"])
        self.assertIsNone(self.why("d"))
        self.assertTrue(dlane.try_open(self.store, self.store.family("d"), 2, self.settings))

    def test_one_look_a_direction_lineage_and_the_lineage_retires_on_a_failed_one(self):
        self.answer = lambda job: (result(job.name, daily=LOSING_DAILY, window="holdout") if job.window == "holdout"
                                   else strong(job))
        self.family("d", lane="direction")
        self.child("d", "d-on-qqq")
        self.t().validate(self.store.families(alive=True))
        self.assertTrue(self.store.family("d")["state"]["gate_ready"])
        # Before its look the passed try waits, even with its gate mark reset (a new Gym image has it validated again).
        self.store.set_state("d", gate_ready=False)
        self.assertIsNone(self.why("d"), "its try entered the gate and waits for its one look")
        self.store.set_state("d", gate_ready=True)
        self.replies = [PASS] * 2
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(out["looked"], [{"family": "d", "passed": False}])
        self.assertEqual(self.why("d"), dlane.SPENT_LOOK)
        self.assertEqual(self.why("d-on-qqq"), dlane.SPENT_LOOK)
        # No second look in the lineage, whoever asks: a member made ready by hand is refused on its ration.
        self.store.set_state("d-on-qqq", gate_ready=True, validation_version=1, validation_line={"passed": True},
                             validation_image=None, validation_bundle=None)
        self.store.update_family("d-on-qqq", validated_version=1)
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual((out["looked"], out["refused"]), ([], ["d-on-qqq"]))
        [refusal] = self.store.refusals("d-on-qqq")
        self.assertEqual((refusal["stage"], refusal["reason"]), ("rations", "the direction lineage's one holdout look is spent"))

    def test_the_gate_that_refuses_the_try_spends_it(self):
        self.answer = strong
        self.family("d", lane="direction")
        self.t().validate(self.store.families(alive=True))
        sha = run_sha(self.store.version("d", 1))
        self.store.set_state("d", gate_ready=False, gated_sha=sha)  # the gate refused it (a review, a duplicate)
        self.assertEqual(self.why("d"), dlane.SPENT_TRY)

    def test_the_cohort_keep_spares_the_ration_as_it_spares_the_clocks(self):
        self.answer = weak
        self.family("d", lane="direction")
        t = self.t()
        t.validate(self.store.families(alive=True))
        self.assertIsNone(t._why(self.store.family("d"), t.identity(), frozenset({"d"})))
        self.assertEqual(t.keep_spared.get("d"), "ration")

    def test_a_direction_family_never_forks_once_its_lineage_has_tried(self):
        self.answer = strong
        self.family("d", lane="direction")
        self.family("a")
        t = self.t()
        t.validate(self.store.families(alive=True))
        self.assertFalse(t.lane_forks(self.store.family("d")))
        self.assertTrue(t.lane_forks(self.store.family("a")))
        born = t.forks(self.store.families(alive=True))
        self.assertTrue(born and all(self.store.family(f)["parent"] == "a" for f in born), born)


# ================================================================================================== 4. FP beside
class FalsePositiveBesideTheLook(RoundCase):
    def setUp(self):
        super().setUp()
        self.settings["dlane"] = {"mode": "gate"}
        self.answer = lambda job: (result(job.name, daily=HOLDOUT_DAILY, window="holdout") if job.window == "holdout"
                                   else result(job.name, window=job.window, sharpe_daily=3.0))

    def look(self, fid, lane=None):
        self.family(fid, **({"lane": lane} if lane else {}))
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.replies = [PASS] * 2
        Gate(self.store, self.pool, self.router, self.settings).run()
        [look] = [x for x in self.store.looks() if x["family"] == fid]
        [event] = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.gate"
                   and e["family"] == fid and e["payload"].get("action") == "look"]
        return look["detail"], event

    def test_a_direction_look_states_its_screens_rates_and_an_alpha_look_none(self):
        detail, event = self.look("d", "direction")
        self.assertEqual({k: detail[k] for k in ("screen", "fp_lane_mixed", "fp_lane_2224", "receipt")},
                         {"screen": "S-C", "fp_lane_mixed": 0.0141, "fp_lane_2224": 0.0209, "receipt": None})
        self.assertEqual({k: event[k] for k in ("screen", "fp_lane_mixed", "fp_lane_2224", "receipt")},
                         {"screen": "S-C", "fp_lane_mixed": 0.0141, "fp_lane_2224": 0.0209, "receipt": None})
        alpha, alpha_event = self.look("a")
        self.assertFalse({"fp_lane_mixed", "fp_lane_2224"} & (set(alpha) | set(alpha_event)), "the alpha look as in D-1")

    def test_under_d2_the_look_states_the_receipts_rates(self):
        self.settings["dlane"] = {"mode": "gate", "screen": "D2", "structures": ["long_single"]}
        with mock.patch.object(S, "read_policy", committed_policy):
            detail, event = self.look("d", "direction")
        self.assertEqual({k: event[k] for k in ("screen", "fp_lane_mixed", "fp_lane_2224", "receipt")},
                         {"screen": "D2", "fp_lane_mixed": 0.1037, "fp_lane_2224": 0.1239, "receipt": RECEIPT_SHA})
        self.assertEqual(detail["numbers"]["rule"], "D2")
        self.assertIn("pooled_t_low", detail["numbers"])

    def test_the_rollback_states_nothing_new(self):
        self.settings["dlane"] = {"mode": "off"}
        detail, event = self.look("d", "direction")
        self.assertFalse({"fp_lane_mixed", "fp_lane_2224", "screen"} & (set(detail) | set(event)))


class FalsePositiveBesideEveryTrade(ReportFixture):
    D2_DETAIL = {"lane": "direction", "screen": "D2", "receipt": RECEIPT_SHA, "fp_lane_mixed": 0.1037,
                 "fp_lane_2224": 0.1239}

    def test_every_probe_trade_and_every_real_close_carries_its_screen_and_rates(self):
        from league.ops import dlane_report as R

        self.fam("dir-a", lane="direction", band="probe", banded_version=1)
        self.fam("alp-b", band="probe", banded_version=2)
        self.fam("tui-c")
        self.store.add_look("dir-a", 1, "sha-a", passed=True, p_value=0.2, detail=self.D2_DETAIL)
        self.store.add_look("alp-b", 2, "sha-b", passed=True, p_value=0.05, detail={})
        self.close("dir-a", route=":r", pnl=-12.0)
        self.close("dir-a", route=":r", status="open", closed_at=None, qty=1)
        self.close("alp-b", route=":r", pnl=8.0, version=2)
        self.close("tui-c", route=":t", pnl=-3.0)
        with mock.patch.object(S, "read_policy", committed_policy):
            out = self.report()["fp_beside_trades"]
        self.assertEqual(out["contamination"], R.CONTAMINATION)
        trades = {(r["family"], r["status"]): r for r in out["probe_trades"]}
        self.assertEqual(sorted(trades), [("alp-b", "closed"), ("dir-a", "closed"), ("dir-a", "open")])
        for status in ("open", "closed"):
            row = trades[("dir-a", status)]
            self.assertEqual({k: row[k] for k in ("screen", "fp_lane_mixed", "fp_lane_2224", "receipt", "lane")},
                             {"screen": "D2", "fp_lane_mixed": 0.1037, "fp_lane_2224": 0.1239, "receipt": RECEIPT_SHA,
                              "lane": "direction"})
            self.assertEqual(row["label"], dlane.LABEL)
        alpha = trades[("alp-b", "closed")]
        self.assertEqual((alpha["screen"], alpha["fp_lane_mixed"], alpha["fp_upper_bound"]), ("S-B", None, 0.02))
        closes = {r["family"]: r for r in out["closes"]}
        self.assertEqual(sorted(closes), ["alp-b", "dir-a", "tui-c"])
        self.assertEqual(closes["dir-a"]["fp_lane_2224"], 0.1239)
        self.assertIsNone(closes["tui-c"]["screen"])
        self.assertIn("no passed holdout look", closes["tui-c"]["fp_why"])
        # A Probe family's row in `probes` states the same rates.
        probes = {r["family"]: r for r in self.report()["probes"]}
        self.assertEqual((probes["dir-a"]["fp_lane_mixed"], probes["dir-a"]["fp_lane_2224"]), (0.1037, 0.1239))

    def test_a_direction_look_from_before_d1b_reads_its_screens_rates_now(self):
        self.assertEqual(dlane.fp_of_look({"lane": "direction", "screen": "S-C"}, COMMITTED),
                         {"screen": "S-C", "fp_lane_mixed": 0.0141, "fp_lane_2224": 0.0209, "receipt": None})
        with mock.patch.object(S, "read_policy", committed_policy):
            self.assertEqual(dlane.fp_of_look({"screen": "D2", "receipt": RECEIPT_SHA}, COMMITTED)["fp_lane_mixed"], 0.1037)
            self.assertIsNone(dlane.fp_of_look({"screen": "D2", "receipt": "e" * 64}, COMMITTED)["fp_lane_mixed"],
                              "another receipt's rates are not this one's")
        self.assertEqual(dlane.fp_of_look({}, COMMITTED)["screen"], "S-B")

    def test_each_band_row_carries_its_screen_and_rates_only_while_the_lane_is_on(self):
        from league.ops import direction as DIR
        from league.ops import fast_lane as FL

        self.fam("dir-a", lane="direction", band="probe", banded_version=1)
        self.fam("alp-b", band="candidate", banded_version=1)
        self.store.add_look("dir-a", 1, "sha-a", passed=True, p_value=0.2, detail=self.D2_DETAIL)
        self.store.add_look("alp-b", 1, "sha-b", passed=True, p_value=0.05, detail={})

        def bands(settings):
            with mock.patch.object(DIR, "train_fit", lambda store, fam, n: {"basis": "train-held-hours"}), \
                    mock.patch.object(FL, "_roots", lambda store, fam, n: ("SPY",)):
                out = FL.report(self.root, None, self.root / "direction-closes.json", today="2026-10-20", settings=settings)
            return {b["family"]: b for b in out["bands"]}

        on = bands({"dlane": {"mode": "gate"}})
        self.assertEqual(on["dir-a"]["fp"], {"screen": "D2", "fp_lane_mixed": 0.1037, "fp_lane_2224": 0.1239,
                                             "receipt": RECEIPT_SHA, "look_recorded": True})
        self.assertEqual((on["alp-b"]["fp"]["screen"], on["alp-b"]["fp"]["fp_lane_mixed"]), ("S-B", None))
        self.assertIsInstance(on["dir-a"]["screen"], list, "the row's screen rows are where they were")
        for settings in (None, {"dlane": {"mode": "off"}}):
            self.assertTrue(all("fp" not in b for b in bands(settings).values()), settings)


class TheReportStatesTheLoosening(unittest.TestCase):
    def test_d2_is_listed_with_its_cost_and_the_ration_and_calls_only_as_tightenings(self):
        from league.ops import dlane_report as R

        [row] = [r for r in R.LOOSENED if "D2" in r["rule"]]
        for figure in ("10.37%", "12.39%", "19.95%", "14.08%", "15.01%", "c = 1.00", "c3605947", "post-hoc"):
            self.assertIn(figure, " ".join(row.values()), figure)
        tightened = " ".join(R.TIGHTENED)
        self.assertIn("ONE Validation try and ONE holdout look per direction lineage", tightened)
        self.assertIn("calls only", tightened)
        for text in [*[" ".join(r.values()) for r in R.LOOSENED], *R.TIGHTENED]:
            self.assertTrue(text.isascii())
            for year in ("2020", "2021", "2025", "2026"):
                self.assertNotIn(year, text)


if __name__ == "__main__":
    unittest.main()
