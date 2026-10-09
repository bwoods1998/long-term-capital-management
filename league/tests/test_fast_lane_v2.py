"""FAST LANE V2 (Oct 7, 2026; the owner's goal of Oct 7, item 4): the screen (the Validation line and one flat holdout look
a program), direction counts (the drift screen's refusal and the look holds off by setting), the one-structure Probe
within 10% of E with at most 3 Probe positions and the $400 Probe loss budget, same-minute entry, and the rooms the
other routes keep for Probe opens. Every figure is invented.

Release L-D (Oct 9, 2026) moved three of these rows (`loss_basis` "net", `max_open` 8, `demotion` "dm1"): the tests of
fast lane v2's gross budget, three slots and D5 run on the CON-only rollback's table (`money_fakes.rollback_table`),
which pins that rollback to fast lane v2's behaviour; L-D's own rules are tested in `test_ld_release.py`."""

from __future__ import annotations

import datetime as dt
import json
import random
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from league.constitution import CONSTITUTION, options_money_problems
from league.live import money as M
from league.swarm import evidence
from league.swarm import settings as S
from league.swarm.gate import DUPLICATE_STAGE, Gate, look_hold_settings
from league.swarm.researcher import drift_settings
from league.swarm.tournament import Tournament
from league.tests import REAL_POLICY_PATH
from league.tests.money_fakes import rollback_table
from league.tests.swarm_fakes import result
from league.tests.test_live_step import HAVE, LiveCase
from league.tests.test_swarm_look_holds import PASS, HoldCase, lean
from league.tests.test_swarm_rounds import RoundCase, review_failure

if HAVE:
    from league.live.real import probe_tally
    from league.live.state import LiveState
    from league.tests.live_fakes import MONDAY, VERTICAL, at, family

E = D("1288.40")


def committed_policy() -> dict:
    """The committed policy layer (`league/swarm/policy.json`), as the House reads it."""
    with mock.patch.object(S, "POLICY_PATH", REAL_POLICY_PATH):
        layer, status = S.read_policy()
    assert status["state"] == "ok", status
    return layer


# ================================================================================================== D1: the screen
class TheScreen(RoundCase):
    def validated_lineage(self, fid: str, versions: int) -> None:
        """`versions` validated versions in `fid`'s lineage (a validation run with a trial each)."""
        for i in range(versions):
            v = self.store.add_version(fid, f"# {fid} v{i + 2}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\n"
                                            f"def decide(ctx):\n    return []  # {i}\n", {}, author="seed")
            self.store.add_run(fid, v["n"], {"run_id": f"val-{fid}-{v['n']}", "status": "ok", "trials": 1,
                                             "summary": {"t_daily": 0.4 + 0.1 * (i % 5), "days_traded": 120}},
                               window="validation", stress=1.0, purpose="validation")

    def judged(self, fid: str, *, t: float, quarters: str) -> dict:
        fam = self.store.family(fid)
        n = int(fam["best_version"])
        r = result(f"{fid}-val", window="validation", t=t, quarters=quarters, trades=300, days=120, sharpe_daily=0.1)
        # Traded-day moments of a mildly right-skewed program: with N = 1 the deflated Sharpe is the probabilistic Sharpe
        # against 0, a moments-adjusted t (`evidence.deflated`) that the conservative moments would hold under 1.65.
        r["summary"].update(skew_traded=0.5, kurt_traded=3.0)
        Tournament(self.store, self.pool, self.settings).judge(fid, n, r)
        return self.store.family(fid)["state"]["validation_line"]

    def test_the_validation_line_is_t_1_65_two_quarters_and_n_one_whatever_the_lineage(self):
        self.family("a")
        self.validated_lineage("a", 14)
        self.assertEqual(self.store.lineage_validated("a")[0], 14)
        last = self.store.version("a", 15)
        self.store.update_family("a", best_version=last["n"])
        line = self.judged("a", t=1.65, quarters="2/4")
        self.assertTrue(line["passed"], line)
        self.assertEqual(line["numbers"]["validated_versions"], 1, "the program, never the lineage's 14")
        for t, quarters, check in ((1.64, "2/4", "t"), (1.65, "1/4", "quarters")):
            line = self.judged("a", t=t, quarters=quarters)
            self.assertFalse(line["passed"], (t, quarters))
            self.assertFalse(line["checks"][check], (t, quarters))
            self.assertEqual(line["numbers"]["validated_versions"], 1)

    def test_the_look_is_flat_at_ten_percent_after_any_number_of_failed_looks(self):
        rng = random.Random(11)
        daily = [rng.gauss(2.0, 10.0) for _ in range(184)]
        days = [(dt.date(2026, 1, 2) + dt.timedelta(days=i)).isoformat() for i in range(184)]
        r = result("h", daily=daily, pnl=sum(daily))
        r["daily"] = [[d, x, 0.0] for d, x in zip(days, daily)]
        base = evidence.holdout_line(r, validation_sharpe=0.05, previous_ps=[0.6, 0.7, 0.9], seed="s")
        self.assertEqual(set(base["checks"]), {"status_ok", "pnl", "level", "sharpe"})
        self.assertEqual((base["numbers"]["level"], base["numbers"]["rule"], base["numbers"]["looks_before"]),
                         (0.10, "flat", 3))
        p = base["p"]
        self.assertEqual(base["checks"]["level"], p <= 0.10)
        # The level is what decides: just above and just below this look's own p.
        self.assertTrue(evidence.holdout_line(r, validation_sharpe=0.05, previous_ps=[0.6, 0.7, 0.9], seed="s",
                                              level=p)["checks"]["level"])
        self.assertFalse(evidence.holdout_line(r, validation_sharpe=0.05, previous_ps=[0.6, 0.7, 0.9], seed="s",
                                               level=p - 1e-6)["checks"]["level"])
        tail = base["numbers"]["tail"]
        self.assertEqual(tail["days"], sum(1 for d in days if d >= "2026-07-01"))
        self.assertNotIn("tail", base["checks"])

    def test_a_planted_p_of_0_09_passes_and_0_11_fails(self):
        """The flat rule on the bootstrap's own p: a look at p 0.09 passes after three failed looks; one at 0.11 fails."""
        r = result("h", daily=[1.0, 2.0], pnl=3.0)
        with mock.patch.object(evidence, "block_bootstrap", return_value={"mean": 1.0, "lcb95": -0.1, "p": 0.09}):
            passed = evidence.holdout_line(r, validation_sharpe=0.001, previous_ps=[0.6, 0.7, 0.9], seed="s")
        with mock.patch.object(evidence, "block_bootstrap", return_value={"mean": 1.0, "lcb95": -0.1, "p": 0.11}):
            failed = evidence.holdout_line(r, validation_sharpe=0.001, previous_ps=[0.6, 0.7, 0.9], seed="s")
        self.assertTrue(passed["passed"], passed)
        self.assertFalse(failed["passed"])
        self.assertEqual([k for k, ok in failed["checks"].items() if not ok], ["level"])

    def test_a_duplicate_program_is_looked_at_once(self):
        self.replies = [PASS] * 8
        self.family("a")
        self.family("b")
        code = self.store.version("a", 1)["code"]
        v = self.store.add_version("b", code, {}, author="seed")  # the same program in another family
        self.store.update_family("b", best_version=v["n"])
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        out = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.assertEqual([x["family"] for x in out["looked"]], ["a"])
        self.assertEqual(out["refused"], ["b"])
        self.assertEqual([r["stage"] for r in self.store.refusals("b")], [DUPLICATE_STAGE])
        self.assertEqual(len([j for j in self.pool.jobs if j.window == "holdout"]), 1)


class APaidVerdictBinds(RoundCase):
    """The fast lane's review (Oct 7, 2026): the release's evaluator adoption clears the gate's `review` and `gated_sha`,
    so a version a paid review or audit refused (never looked at) was gate-ready again under the new line and would be
    reviewed again, and could pass on a second roll. A kept paid refusal or bar now closes it before anything is paid."""

    FAIL = {"text": json.dumps(review_failure("it reads the day's settlement before the close"))}

    def gate(self):
        return Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)

    def paid(self) -> int:
        return len(self.sail.bodies) + len(self.asked)

    def validate(self):
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))

    def adopt_and_validate_again(self, fid: str) -> None:
        from league.swarm import bands
        from league.swarm.evaluator import adopt, identity
        from league.tests.evaluator_fakes import seed_current_run

        train = seed_current_run(self.store, fid, 1, window="train")  # the researcher's Train run under the new evaluator
        self.assertTrue(adopt(self.store, identity("synthetic-image", bands._bundle()))["adopted"])
        state = self.store.family(fid)["state"]
        self.assertEqual((state.get("gated_sha"), state.get("review")), (None, None), "the adoption clears both")
        self.store.update_family(fid, best_version=1)
        self.store.set_state(fid, best_train_run=train["run_id"], best_train_version=1)
        self.validate()
        self.assertTrue(self.store.family(fid)["state"]["gate_ready"], "gate-ready again: the gap the review found")

    def events(self, fid):
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.gate" and e["family"] == fid
                and e["payload"].get("action") == "paid_verdict"]

    def test_a_failed_audit_binds_after_an_evaluator_adoption(self):
        from league.swarm.gate import run_sha

        self.replies = [PASS, self.FAIL]
        self.family("a")
        self.validate()
        out = self.gate().run()
        self.assertEqual((out["refused"], out["looked"]), (["a"], []))
        self.assertEqual([r["stage"] for r in self.store.refusals("a")], ["audit"])
        paid = self.paid()
        self.adopt_and_validate_again("a")
        self.replies = [PASS] * 8                                    # a second roll would pass: it is never asked
        out = self.gate().run()
        self.assertEqual((out["refused"], out["looked"]), (["a"], []))
        self.assertEqual(self.paid(), paid, "no new review or audit is paid")
        self.assertEqual([j for j in self.pool.jobs if j.window == "holdout"], [], "no look")
        self.assertEqual([r["stage"] for r in self.store.refusals("a")], ["audit"], "the earlier row is the record")
        [event] = self.events("a")
        self.assertTrue(event["earlier"].startswith("the audit refused it on "), event)
        state = self.store.family("a")["state"]
        self.assertEqual((state["gated_sha"], state["gate_ready"]), (run_sha(self.store.version("a", 1)), False))
        self.assertEqual(state["gate_outcome"]["result"], "refused")
        self.assertTrue(state["gate"].startswith("fail (an earlier paid review or audit"), state["gate"])
        self.assertEqual(self.gate().run()["refused"], [], "closed: the next round passes it by")

    def test_a_failed_review_of_the_same_program_in_another_family_binds(self):
        self.replies = [self.FAIL]
        self.family("a")
        self.validate()
        self.assertEqual(self.gate().run()["refused"], ["a"])
        self.assertEqual([r["stage"] for r in self.store.refusals("a")], ["review"])
        paid = self.paid()
        self.family("b")
        v = self.store.add_version("b", self.store.version("a", 1)["code"], {}, author="seed")  # the same program
        self.store.update_family("b", best_version=v["n"])
        self.replies = [PASS] * 8
        self.validate()
        out = self.gate().run()
        self.assertEqual((out["refused"], out["looked"]), (["b"], []))
        self.assertEqual(self.paid(), paid)
        [event] = self.events("b")
        self.assertIn("(the same program in a, version 1)", event["earlier"])
        self.assertEqual(self.store.refusals("b"), [], "no new refusal row: a's is the record")

    def test_a_kept_bar_from_a_failed_review_binds_without_a_refusal_row(self):
        from league.swarm.gate import run_sha

        self.family("a")
        sha = run_sha(self.store.version("a", 1))
        self.store.set_state("a", incubator_barred={sha: {"why": "the gate's reviewer failed it", "at": 1.0, "version": 1}})
        self.replies = [PASS] * 8
        self.validate()
        paid = self.paid()
        out = self.gate().run()
        self.assertEqual((out["refused"], out["looked"]), (["a"], []))
        self.assertEqual(self.paid(), paid)
        self.assertEqual(self.events("a")[0]["earlier"], "the gate's reviewer failed it")

    def test_the_incubators_own_failed_read_does_not_bind_the_gate(self):
        """The incubator's reads bar the incubator route only (`league/swarm/incubator.py`; the gate asks its own
        questions, `test_swarm_incubator.GateUnchanged`): its failed audit in the bars does not close the gate's look."""
        from league.swarm.gate import run_sha

        self.family("a")
        sha = run_sha(self.store.version("a", 1))
        self.store.set_state("a", incubator_barred={sha: {"why": "the incubator's audit failed it", "at": 1.0}})
        self.replies = [PASS] * 8
        self.validate()
        out = self.gate().run()
        self.assertEqual([x["family"] for x in out["looked"]], ["a"])
        self.assertEqual(self.events("a"), [])

    def test_a_free_refusal_does_not_bind(self):
        """A refusal at a free stage (here the drift screen, which this release switches off) is judged again by its own
        rule: the version is reviewed, audited and looked at."""
        from league.swarm.gate import run_sha

        self.family("a")
        sha = run_sha(self.store.version("a", 1))
        self.store.refuse("a", 1, "drift screen", "its Train drift-adjusted t is under the line")
        self.store.set_state("a", incubator_barred={sha: {"why": "the gate refused it (the drift screen)", "at": 1.0}})
        self.replies = [PASS] * 8
        self.validate()
        out = self.gate().run()
        self.assertEqual(out["refused"], [])
        self.assertEqual([x["family"] for x in out["looked"]], ["a"])
        self.assertEqual(self.events("a"), [])


# ======================================================================================= D2: direction counts
class TheSettings(HoldCase):
    """The committed policy switches the drift screen's refusal and both look holds off."""

    def setUp(self):
        super().setUp()
        policy = committed_policy()
        self.settings["gate"]["look_holds"] = policy["gate"]["look_holds"]
        self.settings["tournament"]["drift_screen"] = policy["tournament"]["drift_screen"]

    def test_the_committed_policy_turns_both_holds_and_the_drift_screen_off(self):
        policy = committed_policy()
        self.assertIsNone(policy["gate"]["look_holds"])
        self.assertIs(policy["tournament"]["drift_screen"], False)
        with mock.patch.object(S, "POLICY_PATH", REAL_POLICY_PATH):
            loaded = S.load(None)
        self.assertIsNone(loaded["gate"]["look_holds"])
        self.assertIs(loaded["tournament"]["drift_screen"], False)
        self.assertEqual(look_hold_settings(loaded), (None, None))
        self.assertIsNone(drift_settings(loaded))

    def test_a_long_delta_low_power_drift_failing_version_is_looked_at(self):
        # Long delta, 94% of its Train profit drift, a drift-adjusted t of 0.2 (the old screen refused it), and a
        # Validation Sharpe the old power hold held.
        block = lean(alpha=10.0, drift=150.0, beta=300.0, t=0.2)
        self.assertFalse(evidence.drift_screen(evidence.drift_numbers(block))["passed"])
        n = self.ready("a", block=block, sharpe=0.03)
        self.assertIsNone(self.gate.look_hold(self.store.family("a"), n))
        out = self.gate.run()
        self.assertEqual((out["refused"], out["look_held"]), ([], []))
        self.assertEqual(out["looked"], [{"family": "a", "passed": False}])
        self.assertEqual(self.store.look_holds(), [])
        self.assertNotIn(str(n), (self.store.family("a")["state"].get("drift_failed") or {}))


# ================================================================================================= D3, D4: money
class TheProbe(unittest.TestCase):
    def setUp(self):
        self.t = M.Table.from_constitution()

    def plan(self, unit, *, band="probe", equity=E, fwd=None, table=None, **exposure):
        values = {k: (v if k in ("family_open", "probe_open") else D(str(v))) for k, v in exposure.items()}
        return M.plan_open(table or self.t, band=band, tuition=False, equity=D(str(equity)), unit=D(str(unit)), fwd=fwd,
                           exposure=M.Exposure(**values))

    def test_the_table(self):
        self.assertEqual((self.t.probe_share, self.t.probe_contracts, self.t.probe_max_open, self.t.probe_loss_budget,
                          self.t.probe_floor), (D("0.10"), 1, 8, D("400"), D("0")))
        self.assertEqual(options_money_problems(), [])
        self.assertEqual(CONSTITUTION["options_money"]["probe"]["max_open"], 8, "release L-D (3 at the fast lane)")
        # At E = $1,288.40: the Probe cap $128.84; at the fast lane's 3 slots the room was N x cap, $386.52 <= $400; at
        # L-D's 8 it is the budget, $400 (never 8 x $128.84 = $1,030.72); both inside the daily stop's $450.94.
        self.assertEqual(M.cents(M.probe_cap(self.t, E)), D("128.84"))
        self.assertEqual(M.cents(M.probe_room(rollback_table(), E)), D("386.52"))
        self.assertEqual(M.cents(M.probe_room(self.t, E)), D("400.00"))
        self.assertLessEqual(M.probe_room(self.t, E), self.t.probe_loss_budget)
        self.assertLess(M.probe_room(self.t, E), self.t.daily_stop_share * E)
        self.assertEqual(M.probe_room(self.t, None), M.ZERO)
        # The grant's smallest real stake stays $100 with the floor at $0 (the review: the floor's move loosened a grant
        # refusal): the standing grant still refuses under $100 of capital.
        from league.live_trading import policy, smallest_stake

        self.assertEqual(smallest_stake(), D("100"))
        self.assertEqual((policy("1288.40", "5500")["stake_usd"], policy("1288.40", "5500")["max_agents"]), ("100", 12))
        with self.assertRaises(ValueError):
            policy("99.99", "5500")

    def test_one_structure_within_ten_percent(self):
        self.assertEqual(self.plan(40).qty, 1)
        self.assertEqual(self.plan("128.84").qty, 1)
        refused = self.plan(130)
        self.assertEqual(refused.qty, 0)
        self.assertIn("over the Probe's cap of $128.84", refused.reason)

    def test_at_most_three_probe_positions(self):
        """Fast lane v2's three slots (the CON-only rollback of release L-D; L-D's 8: `test_ld_release`)."""
        self.assertEqual(self.plan(40, probe_open=2, table=rollback_table()).qty, 1)
        refused = self.plan(40, probe_open=3, table=rollback_table())
        self.assertEqual(refused.qty, 0)
        self.assertIn("3 Probe positions held or working; the most at once is 3", refused.reason)

    def test_the_loss_budget_counts_realized_and_at_risk(self):
        self.assertEqual(self.plan(40, probe_realized="300", probe_at_risk="60").qty, 1, "exactly $400")
        refused = self.plan("40.01", probe_realized="300", probe_at_risk="60")
        self.assertEqual(refused.qty, 0)
        self.assertTrue(refused.reason.startswith("probe: the loss budget"), refused.reason)
        self.assertIn("realized net $300.00, held or working $60.00", refused.reason)
        gross = self.plan("40.01", probe_realized="300", probe_at_risk="60", table=rollback_table())
        self.assertIn("realized $300.00, held or working $60.00", gross.reason, "the rollback's words, as before")
        self.assertEqual(self.plan(40, probe_realized="400").qty, 0, "spent")
        self.assertEqual(self.plan(40, probe_at_risk="380").qty, 0, "held and working count whole")

    def test_sized_kelly_sizing_and_c3(self):
        weak = M.forward_stats([{"pnl": r * 100.0, "max_loss": 100.0} for r in [0.44, -0.28] * 10], 0.8)
        kelly = M.kelly_cap(self.t, D("5481.65"), weak)
        self.assertGreater(kelly, D("20"))
        self.assertLess(kelly, M.probe_cap(self.t, D("5481.65")))
        # C3 (kept by the fast lane's review): Kelly under the Probe's cap is sized under the Probe's limits, one structure.
        under = self.plan(10, band="sized", equity="5481.65", fwd=weak)
        self.assertEqual(under.qty, 1, "a Probe-sized stake: the Probe's one structure")
        self.assertTrue(under.reason.startswith("sized: one structure"), under.reason)
        self.assertFalse(under.probe)
        self.assertEqual(self.plan(kelly + 1, band="sized", equity="5481.65", fwd=weak).qty, 1, "never smaller than a Probe")
        # Kelly at its 10% cap: Kelly buys structures, floor(kelly / unit), under the Sized limits.
        strong = M.forward_stats([{"pnl": r * 100.0, "max_loss": 100.0} for r in [0.9, 0.8, 1.0, 0.7] * 5], 0.8)
        sized = self.plan(10, band="sized", equity="5481.65", fwd=strong)
        self.assertEqual(sized.qty, 54, "floor(548.165 / 10)")
        self.assertTrue(sized.reason.startswith("sized:"), sized.reason)
        # A Sized open is never refused by the Probe budget or the Probe count.
        for fwd, qty in ((strong, 54), (weak, 1)):
            spent = self.plan(10, band="sized", equity="5481.65", fwd=fwd, probe_open=3, probe_realized="400",
                              probe_at_risk="100")
            self.assertEqual(spent.qty, qty)


class TheTally(unittest.TestCase):
    """`real.probe_tally` over the live state's own rows."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "live.sqlite"
        self.state = LiveState(self.path)
        self.oid = self.pid = 0

    def position(self, instance, *, share, fees=1.0, status="open", cash=None, qty=1, tuition=0, probe=True):
        """A position row; `probe`: opened by a Probe family (the mark `money.Plan.probe` sets, via its order)."""
        self.pid += 1
        self.state.upsert("positions", {"pid": self.pid, "instance": instance, "family": instance.split("@")[0],
                                        "type": "debit_vertical", "root": "SPY", "legs": "[]",
                                        "qty": 0 if status == "closed" else qty, "opened_qty": qty, "entry": share,
                                        "max_loss_share": share, "collateral": 0.0, "fees": fees,
                                        "cash": cash if cash is not None else -(share * 100 + fees), "opened_at": 1.0,
                                        "opened_day": "2026-10-05", "opened_minute": 1, "status": status,
                                        "closed_at": 2.0 if status == "closed" else None, "tuition": tuition,
                                        "info": json.dumps({"order": self.pid, **({"probe": True} if probe else {})})},
                          "pid")

    def order(self, instance, *, max_loss, qty=1, filled=0, fees=1.0, status="working", day="2026-10-07", pid=None,
              tuition=0, expiry="2026-10-09"):
        self.oid += 1
        legs = json.dumps([{"symbol": "SPY261009C00600000", "side": 1, "ratio": 1, "is_call": True, "strike": 600.0,
                            "expiry": expiry, "key": 0}])
        self.state.upsert("orders", {"oid": self.oid, "client_id": f"lv-{self.oid}", "instance": instance,
                                     "family": instance.split("@")[0], "action": "open", "type": "debit_vertical",
                                     "root": "SPY", "legs": legs, "qty": qty, "limit_value": 0.3, "limit_price": "0.30",
                                     "placed_at": 1.0, "day": day, "placed_minute": 1, "status": status, "pid": pid,
                                     "filled_qty": filled, "max_loss": max_loss, "fees_est": fees, "tuition": tuition,
                                     "answer": json.dumps({"dispatched": True}), "updated_at": 1.0}, "oid")

    def tally(self, state=None, basis="gross"):
        """Fast lane v2's GROSS figure by default (the CON-only rollback of release L-D); NET: `test_ld_release`."""
        return probe_tally((state or self.state).rows, day="2026-10-07", basis=basis)

    def test_it_counts_real_positions_and_orders_only(self):
        self.position("a@1:r", share=0.40, status="closed", cash=-50.0)       # a Probe loss of $50
        self.position("b@1:r", share=0.40, status="closed", cash=20.0)        # a Probe gain offsets nothing: still $50
        self.position("s@1:r", share=0.40, status="closed", cash=500.0, probe=False)  # a Sized gain: never counted
        self.position("o@1:r", share=0.40, status="closed", cash=-70.0, probe=False)  # unmarked: not a Probe's (Sized)
        self.position("a@1:r", share=0.40, fees=1.0, cash=-41.0)              # held: 40 + 2 x 1 = 42
        self.position("b@2:r", share=0.40, fees=1.0, cash=-60.0, probe=False)  # held, Sized: counts at risk too: 60
        self.order("c@1:r", max_loss=80.0, qty=2, filled=1)                   # working: (80 + 2) x 1 / 2 = 41
        self.order("c@1:r", max_loss=30.0, status="lost")                     # lost this week: whole, 32, a slot
        self.order("c@1:r", max_loss=30.0, status="lost", day="2026-09-30")   # lost last week: whole too, a slot
        self.order("c@1:r", max_loss=30.0, status="lost", day="2026-09-28", expiry="2026-10-02")  # expired: 32, no slot
        self.order("c@1:r", max_loss=30.0, status="filled")                   # done: its position counts
        for other in ("t@1:t", "i@1:i", "house:rebound-live@1:h"):            # tuition, incubator, the House test
            self.position(other, share=0.90, status="closed", cash=-90.0)
            self.position(other, share=0.90)
            self.order(other, max_loss=90.0)
        open_n, realized, at_risk = self.tally()
        self.assertEqual((open_n, realized, at_risk), (5, D("50"), D("42") + D("60") + D("41") + 3 * D("32")))

    def test_a_sized_gain_never_refills_the_probe_budget(self):
        """The review's reproduction (Oct 7, 2026): a closed Sized position at +$500 and five closed Probe positions at
        -$121 each. The net figure read $105 and let the next $121 Probe open go (gross losses could reach about $900);
        the gross figure reads $605, and the next Probe open is refused."""
        self.position("sized@1:r", share=1.0, status="closed", cash=500.0, probe=False)
        for i in range(5):
            self.position(f"p{i}@1:r", share=1.20, status="closed", cash=-121.0)
        open_n, realized, at_risk = self.tally()
        self.assertEqual((open_n, realized, at_risk), (0, D("605"), M.ZERO))
        t = rollback_table()
        plan = M.plan_open(t, band="probe", tuition=False, equity=E, unit=D("121"), fwd=None,
                           exposure=M.Exposure(probe_open=open_n, probe_realized=realized, probe_at_risk=at_risk))
        self.assertEqual(plan.qty, 0)
        self.assertTrue(plan.reason.startswith("probe: the loss budget"), plan.reason)
        # One Probe position's gain never offsets another's loss either.
        self.position("p9@1:r", share=1.0, status="closed", cash=300.0)
        self.assertEqual(self.tally()[1], D("605"))

    def test_a_lost_open_counts_until_it_is_found_whatever_its_week(self):
        """The review (Oct 7, 2026): the Probe budget is a running total, so a lost open from an earlier week still counts
        whole (it may have filled); it holds a slot until its first leg has expired."""
        self.order("c@1:r", max_loss=100.0, status="lost", day="2026-09-21", expiry="2026-10-16")
        self.assertEqual(self.tally(), (1, M.ZERO, D("102")))
        self.order("d@1:r", max_loss=100.0, status="lost", day="2026-09-21", expiry="2026-09-25")
        self.assertEqual(self.tally(), (1, M.ZERO, D("204")), "expired: its slot is free, its maximum loss still counts")
        # Found at the venue (`RealBook.ingest` takes it back): it counts as the working order it is.
        self.state.db.execute("UPDATE orders SET status='working' WHERE oid=1")
        self.assertEqual(self.tally(), (1, M.ZERO, D("204")))
        self.state.db.execute("UPDATE orders SET status='cancelled' WHERE oid=1")
        self.assertEqual(self.tally(), (0, M.ZERO, D("102")))

    def test_it_survives_a_restart(self):
        self.position("a@1:r", share=0.40, status="closed", cash=-50.0)
        self.position("a@1:r", share=0.40)
        before = self.tally()
        self.state.close()
        again = LiveState(self.path)
        self.addCleanup(again.close)
        self.assertEqual(probe_tally(again.rows, day="2026-10-07", basis="gross"), before)

    def tearDown(self):
        try:
            self.state.close()
        except Exception:  # noqa: BLE001 - closed by the restart test
            pass


@unittest.skipUnless(HAVE, "numpy not installed")
class TheLivePath(LiveCase):
    def refusals(self):
        return [p["why"] for p, a in self.ledger.of("live.refusal")]

    def spend_the_budget(self, live) -> None:
        """A closed real position that lost $400: the Probe loss budget is spent (closed on the Friday before, inside
        THE ROLLING PROBE BUDGET's window of release L-D, so its $400 binds there as fast lane v2's $400 did)."""
        live.state.upsert("positions", {"pid": 900, "instance": "old@1:r", "family": "old", "type": "debit_vertical",
                                        "root": "SPY", "legs": "[]", "qty": 0, "opened_qty": 1, "entry": 4.0,
                                        "max_loss_share": 4.0, "collateral": 0.0, "fees": 1.0, "cash": -400.0,
                                        "opened_at": 1.0, "opened_day": "2026-09-25", "opened_minute": 1,
                                        "status": "closed", "closed_at": at(MONDAY - dt.timedelta(days=3), 15, 0),
                                        "tuition": 0,
                                        "info": json.dumps({"order": 900, "probe": True})}, "pid")

    def test_a_candidate_moved_to_probe_opens_from_the_next_minute(self):
        live = self.make([family("vert", VERTICAL, band="candidate", params={"hold": 600})])
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "probe")
        self.assertEqual(live.instances["vert@1:r"].mode, "live")
        self.run_to(9, 33)
        opens = [b for b in self.venue.sent if b.get("legs") and b["legs"][0]["position_intent"] == "buy_to_open"]
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0]["qty"], "1", "one structure")
        # A Probe family's open is marked, and so is its position: the Probe loss budget counts its realized loss.
        [order] = live.state.rows("SELECT answer, pid FROM orders WHERE action='open'")
        self.assertIs(json.loads(order["answer"]).get("probe"), True)
        [position] = live.state.rows("SELECT info FROM positions WHERE pid=?", (order["pid"],))
        self.assertIs(json.loads(position["info"]).get("probe"), True)
        self.assertNotIn("probe", self.venue.sent[0], "the mark never reaches the venue")

    def test_a_sized_familys_open_is_not_marked(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        returns = [0.30, 0.10, 0.20, -0.10, 0.25] * 5
        self.families.add_forward("vert", "shadow", [{"id": f"s{i}", "day": f"2026-09-{i % 25 + 1:02d}", "pnl": r * 100.0,
                                                       "max_loss": 100.0} for i, r in enumerate(returns)])
        self.families.add_forward("vert", "real", [{"id": f"r{i}", "day": f"2026-08-{i + 1:02d}", "pnl": 6.0, "max_loss": 50.0}
                                                   for i in range(5)])
        live.state.put("band_moves", {"vert": {"band": "probe", "at": at(MONDAY, 9, 0) - 7 * 86400}})
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "sized")
        [order] = live.state.rows("SELECT answer, pid FROM orders WHERE action='open'")
        self.assertNotIn("probe", json.loads(order["answer"]))
        [position] = live.state.rows("SELECT info FROM positions WHERE pid=?", (order["pid"],))
        self.assertNotIn("probe", json.loads(position["info"]))

    def test_a_probe_with_no_promotion_record_still_waits_a_session(self):
        row = family("vert", VERTICAL, band="probe")
        row["real_promoted_at"] = None
        live = self.make([row])
        self.run_to(9, 33)
        self.assertNotIn("vert@1:r", live.instances)
        self.assertEqual(self.venue.sent, [])
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 9, 31))
        live._families_at = float("-inf")
        live.minute()
        self.assertIn("vert@1:r", live.instances)

    def test_the_spent_budget_refuses_a_probe_open_tells_once_a_day_and_exits_go(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600, "opens": 3})])
        self.spend_the_budget(live)
        self.run_to(9, 40)
        self.assertEqual(self.venue.sent, [])
        self.assertTrue(any(w.startswith("probe: the loss budget") for w in self.refusals()), self.refusals())
        told = [t for lvl, t in self.alerts if "Probe loss budget" in t]
        self.assertEqual(len(told), 1, "once a New York day")
        self.assertIn("exits go on", told[0])

    def test_the_stops_and_the_kill_switch_refuse_before_the_budget_is_read(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 3, "opens": 2})])
        self.run_to(9, 31)
        self.assertEqual(len(self.venue.sent), 1)
        self.venue.equity = D("3500")                                      # -36% on the day: the daily stop
        self.spend_the_budget(live)
        self.run_to(9, 45)
        self.assertTrue(live.stops.daily_tripped)
        refused = self.refusals()
        self.assertIn("daily stop", " ".join(refused))
        self.assertFalse(any(w.startswith("probe: the loss budget") for w in refused), refused)
        self.assertEqual([b["legs"][0]["position_intent"] for b in self.venue.sent], ["buy_to_open", "sell_to_close"],
                         "the exit goes")

    def test_the_kill_switch_refuses_first(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        self.spend_the_budget(live)
        self.killed = True
        self.run_to(9, 35)
        self.assertEqual(self.venue.sent, [])
        refused = self.refusals()
        self.assertIn("kill switch", " ".join(refused))
        self.assertFalse(any(w.startswith("probe: the loss budget") for w in refused), refused)

    def test_the_rooms_the_other_routes_keep(self):
        from league.live import calibration as C

        live = self.make([])
        self.assertFalse(hasattr(C, "FAMILY_ROOM_PROBES"))
        self.assertEqual(live.incubator.room(E) - (live.table.house_test_structure
                                                   if live.switches().get("house_test") else M.ZERO),
                         M.probe_room(live.table, E))
        self.assertEqual(M.cents(M.probe_room(live.table, E)), D("400.00"), "release L-D: 8 slots, capped at the budget")
        self.assertEqual(M.cents(M.probe_room(rollback_table(), E)), D("386.52"), "fast lane v2's 3 x 10% x E")


# ======================================================================================= D5: demotion by live results
def real_rows(n, *, pnl, max_loss=40.0, day0=1, version=1):
    return [{"day": f"2026-10-{day0 + i:02d}", "source": "real", "pnl": pnl, "max_loss": max_loss, "version": version}
            for i in range(n)]


def matched(n, *, gap, max_loss=50.0):
    """`n` days on which the version traded real money (at $0 a trade) and its nightly replay made `gap` a dollar of
    maximum loss: a replay gap of `gap` over `n` real trades."""
    out = []
    for i in range(n):
        day = f"2026-10-{i + 1:02d}"
        out.append({"day": day, "source": "real", "pnl": 0.0, "max_loss": max_loss, "version": 1})
        out.append({"day": day, "source": "nightly", "pnl": gap * max_loss, "max_loss": max_loss, "version": 1})
    return out


class TheDemotion(unittest.TestCase):
    """D5 as fast lane v2 built it: `probe.demotion` "dm0", the CON-only rollback of release L-D (DM1: `test_ld_release`)."""

    def setUp(self):
        self.t = rollback_table()

    def band(self, rows, band="probe"):
        row = {"family": "f", "band": band, "structure": "debit_vertical", "holdout_passed": True,
               "typical_max_loss_usd": 40.0}
        return M.band_for(self.t, row, E, M.forward_stats(rows, 0.8, version=1))

    def test_real_losses_past_three_mean_maximum_losses_end_the_probe_for_good(self):
        self.assertEqual(self.band(real_rows(4, pnl=-30.0))[0], "probe", "-$120 is not below -3 x $40")
        band, why = self.band(real_rows(4, pnl=-30.01))
        self.assertEqual(band, "candidate")
        self.assertTrue(why.startswith("D5: its 4 real trades realized $-120.04, below -3 x its mean maximum loss $40.00"),
                        why)
        self.assertEqual(self.band(real_rows(4, pnl=-30.01), band="candidate")[0], "candidate", "sticky at the next pass")
        self.assertEqual(self.band(real_rows(4, pnl=-30.01) + real_rows(1, pnl=100.0, day0=20, version=2))[0], "candidate",
                         "another version's rows never lift it")
        fwd = M.forward_stats(real_rows(4, pnl=-30.01), 0.8, version=1)
        self.assertEqual((fwd.real_n, round(fwd.real_pnl, 2), fwd.real_max_loss), (4, -120.04, 40.0))

    def test_the_replay_gap_needs_five_matched_real_trades_over_0_20(self):
        self.assertTrue(self.band(matched(5, gap=0.21))[1].startswith("D5: its live fills ran 0.210"))
        self.assertEqual(self.band(matched(5, gap=0.21))[0], "candidate")
        self.assertEqual(self.band(matched(4, gap=0.21))[0], "probe", "4 matched trades: too few")
        self.assertEqual(self.band(matched(10, gap=0.19))[0], "probe", "0.19: inside the bound")
        fwd = M.forward_stats(matched(5, gap=0.21) + [{"day": "2026-10-30", "source": "real", "pnl": 0.0,
                                                        "max_loss": 50.0, "version": 1}], 0.8, version=1)
        self.assertEqual(fwd.replay_n, 5, "a real day without a replay is not matched")
        self.assertAlmostEqual(fwd.replay_gap, 0.21)

    def test_sized_is_untouched(self):
        self.assertNotEqual(self.band(real_rows(4, pnl=-30.01), band="sized")[1][:3], "D5:")
        self.assertIsNone(M.demotion(M.forward_stats([], 0.8)))


@unittest.skipUnless(HAVE, "numpy not installed")
class TheDemotionLive(LiveCase):
    def refusals(self):
        return [p["why"] for p, a in self.ledger.of("live.refusal")]

    def test_a_demoted_record_refuses_the_next_open_at_once_and_the_real_instance_goes_exit_only(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 3, "opens": 3})], table=rollback_table())
        self.run_to(9, 31)
        self.assertEqual(len(self.venue.sent), 1)
        self.families.add_forward("vert", "real", [dict(r, id=f"d5-{i}") for i, r in enumerate(real_rows(4, pnl=-60.0))])
        self.run_to(9, 36)
        self.assertIn("its current forward evidence no longer qualifies for this real band", self.refusals())
        self.run_to(9, 38)
        self.assertEqual(self.families.rows["vert"]["band"], "candidate")
        inst = live.instances.get("vert@1:r")
        [row] = live.state.rows("SELECT mode FROM instances WHERE id='vert@1:r'")
        self.assertTrue(inst is None or inst.mode == "exit_only", "exits only, then gone once flat")
        self.assertEqual(row["mode"], "exit_only")
        moved = [p for p, a in self.ledger.of("live.band") if p.get("to") == "candidate"]
        self.assertTrue(moved and moved[0]["why"].startswith("D5:"), moved)
        opens = [b for b in self.venue.sent if b.get("legs") and b["legs"][0]["position_intent"] == "buy_to_open"]
        self.assertEqual(len(opens), 1, "no real open after the demotion")

    def test_the_swarms_band_event_keeps_the_reason(self):
        from league.live.families import SwarmFamilies
        from league.swarm.store import SwarmStore
        from league.tests.evaluator_fakes import band_proof

        live = self.make([], table=rollback_table())
        store = SwarmStore(self.root)
        self.addCleanup(store.close)
        store.add_family({"id": "vert", "mechanism": "An invented mechanism for the demotion test.",
                          "structure": "debit_vertical", "roots": ["SPY"], "dte": [0, 2]}, origin="test")
        version = store.add_version("vert", VERTICAL, {"hold": 600}, author="test")
        store.set_state("vert", banded_version=1, banded_sha=version["sha"], banded_evaluator=band_proof(version),
                        typical_by_version={"1": 50}, forward={"negative": False},
                        live_promoted_at=at(MONDAY - dt.timedelta(days=3), 16, 1))
        store.add_look("vert", 1, "a" * 64, passed=True, p_value=0.05, detail={})
        store.set_band("vert", "probe", reason="synthetic pass")
        store.add_forward("vert", "real", [dict(r, id=f"d5-{i}") for i, r in enumerate(real_rows(4, pnl=-60.0, max_loss=50.0))])
        live.families = SwarmFamilies(self.root)
        self.addCleanup(lambda: live.families._store.close() if live.families._store is not None else None)
        live.account_row = self.venue.account()
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "candidate")
        events = [e["payload"] for e in store.events_after(0) if e["kind"] == "swarm.band"
                  and e["payload"].get("band_to") == "candidate"]
        self.assertTrue(events and events[-1]["reason"].startswith("D5: its 4 real trades realized $-240.00"), events)
        self.assertEqual(len(store.forward("vert")), 4, "the record keeps its rows: failures are never erased")


# ================================================================================ D2: direction, reported only
class TheDirection(unittest.TestCase):
    def test_the_same_risk_buy_and_hold_is_n_sigma_p_mu_over_sigma_b(self):
        from league.ops import direction as DIR

        market = {"by_day": {"d1": 0.01, "d2": -0.005, "d3": 0.02, "d4": None, "d5": 0.0}, "roots": ["SPY"], "proxy": {}}
        known = [0.01, -0.005, 0.02, 0.0]
        import statistics

        expect = 4 * 30.0 * statistics.fmean(known) / statistics.stdev(known)
        out = DIR.same_risk_bh(30.0, market)
        self.assertAlmostEqual(out["usd"], round(expect, 2))
        self.assertEqual((out["days"], out["missing_days"], out["sd_program"]), (4, 1, 30.0))
        self.assertAlmostEqual(sum(30.0 / statistics.stdev(known) * r for r in known), expect,
                               msg="a long position sized to the program's own daily volatility, held every session")

    def test_the_daily_fit_recovers_a_planted_beta(self):
        from league.ops import direction as DIR

        rng = random.Random(7)
        days = [f"d{i:03d}" for i in range(250)]
        r = {d: rng.gauss(0.0005, 0.01) for d in days}
        pnl = {d: 50.0 * r[d] + rng.gauss(0.0, 0.05) for d in days}
        fit = DIR.daily_fit(pnl, {"by_day": r})
        self.assertAlmostEqual(fit["beta"], 50.0, delta=1.0)
        self.assertAlmostEqual(fit["drift_usd"], fit["beta"] * sum(r.values()))
        self.assertAlmostEqual(fit["alpha_usd"] + fit["drift_usd"], sum(pnl.values()))
        self.assertEqual(fit["basis"], "daily-close")
        self.assertIsNone(DIR.daily_fit({"d000": 1.0}, {"by_day": r})["beta"])

    def test_index_roots_read_spy_and_a_missing_file_says_why(self):
        from league.ops import direction as DIR

        closes = {"SPY": {"2026-01-02": 100.0, "2026-01-05": 101.0}, "QQQ": {"2026-01-02": 50.0, "2026-01-05": 49.0}}
        market = DIR.market_returns(closes, ["XSP", "SPXW", "QQQ"], ["2026-01-02", "2026-01-05"])
        self.assertEqual((market["symbols"], market["proxy"]), (["QQQ", "SPY"], {"XSP": "SPY", "SPXW": "SPY"}))
        self.assertIsNone(market["by_day"]["2026-01-02"], "no previous close")
        self.assertAlmostEqual(market["by_day"]["2026-01-05"], (0.01 - 0.02) / 2)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(DIR.load_closes(Path(tmp) / "absent.json"), {})
        none = DIR.same_risk_bh(25.0, DIR.market_returns({}, ["SPY"], ["2026-01-05"]))
        self.assertIsNone(none["usd"])
        self.assertIn("direction job", none["why"])


class TheDirectionJob(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"roots": ["SPY", "XSP", "QQQ"]}}))

    def ctx(self, gateway):
        from types import SimpleNamespace

        return SimpleNamespace(root=self.root, now=lambda: at(MONDAY, 21, 0) if HAVE else 1790800000.0, gateway=gateway)

    def test_it_writes_the_closes_of_every_page_and_the_proxy(self):
        from league.ops import direction as DIR

        calls = []
        pages = [{"bars": {"SPY": [{"t": "2025-01-02T05:00:00Z", "c": 590.0}], "QQQ": [{"t": "2025-01-02T05:00:00Z", "c": 510.0}]},
                  "next_page_token": "p2"},
                 {"bars": {"SPY": [{"t": "2025-01-03T05:00:00Z", "c": 595.0}]}, "next_page_token": None}]

        class Gateway:
            def get(self, path, params=None):
                calls.append((path, dict(params or {})))
                return pages[len(calls) - 1]

        out = DIR.run(self.ctx(Gateway()))
        self.assertTrue(out["ok"], out)
        doc = json.loads((self.root / DIR.FILE).read_text())
        self.assertEqual((doc["schema"], doc["feed"], doc["adjustment"], doc["proxy"]), (1, "sip", "split", {"XSP": "SPY"}))
        self.assertEqual(doc["closes"], {"QQQ": {"2025-01-02": 510.0}, "SPY": {"2025-01-02": 590.0, "2025-01-03": 595.0}})
        (path, first), (_, second) = calls
        self.assertEqual(path, "/v1/alpaca/v2/stocks/bars")
        self.assertEqual((first["symbols"], first["timeframe"], first["start"], first["feed"], first["adjustment"]),
                         ("QQQ,SPY", "1Day", "2024-12-31", "sip", "split"))
        self.assertNotIn("page_token", first)
        self.assertEqual(second["page_token"], "p2")

    def test_a_gateway_error_writes_nothing(self):
        from league.ops import direction as DIR
        from league.ops.context import GatewayError

        class Gateway:
            def get(self, path, params=None):
                raise GatewayError("gateway 503: unavailable", status=503)

        out = DIR.run(self.ctx(Gateway()))
        self.assertEqual((out["status"], out["ok"]), ("failed", False))
        self.assertIn("unavailable", out["error"])
        self.assertFalse((self.root / DIR.FILE).exists())

    def test_a_failure_is_a_failed_receipt(self):
        """The review (Oct 7, 2026): a gateway error or a swarm with no roots was an "ok" receipt, so it was never a House
        warning and never retried inside its grace. `run_job` now records it failed, with its reason."""
        from league.ops import direction as DIR
        from league.ops.__main__ import run_job
        from league.ops.context import GatewayError

        class Gateway:
            def get(self, path, params=None):
                raise GatewayError("gateway 503: unavailable", status=503)

        ctx = self.ctx(Gateway())
        ctx.alerts = []
        out = run_job("direction", root=self.root, due_at=0.0, ctx=ctx)
        self.assertEqual(out["status"], "failed")
        self.assertIn("unavailable", out["error"])
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"roots": []}}))
        self.assertEqual(DIR.run(self.ctx(Gateway()))["status"], "failed", "no roots: failed too")

    def test_the_registry_runs_it_at_start_and_daily_outside_the_sessions(self):
        from league.ops.registry import JOBS, by_name

        self.assertEqual([j.name for j in JOBS].count("direction"), 1)
        job = by_name()["direction"]
        self.assertEqual((job.module, job.in_pause, job.paid), ("league.ops.direction", True, False))
        self.assertEqual([t.kind for t in job.triggers], ["start", "daily"])
        report = by_name()["fast_lane"]
        self.assertEqual((report.module, report.in_pause, report.paid), ("league.ops.fast_lane", True, False))
        self.assertEqual([(t.kind, t.job) for t in report.triggers], [("after", "direction")])

    def test_at_a_house_start_the_grant_runs_before_the_direction_job(self):
        """The review (Oct 7, 2026): due at the same instant, the runner ordered by name, so `direction` (its gateway reads,
        up to 600 s) ran before the grant re-ratified the moved money digest, and no real order could go out meanwhile.
        Occurrences due at the same instant now start in the registry's order: the grant first."""
        from league.ops.runner import Ops

        repo = Path(__file__).resolve().parents[2]
        now = 1790800000.0
        ops = Ops(self.root / "ops-state", release=repo, clock=lambda: now, spawn=lambda a, j: None,
                  kill=lambda p, s: None, proc=lambda pid: None, present=lambda name: True)
        self.addCleanup(ops.close)
        due = [(job.name, kind) for _, job, kind in ops.due(now, {})]
        self.assertEqual(due[:2], [("grant", "run"), ("direction", "run")])


class TheFastLaneJob(RoundCase):
    """`league/ops/fast_lane.py`'s job (the review, Oct 7, 2026: D2's figures existed only in a script run by hand): after
    each `direction` run it writes the report, read-only, to `<state>/fast-lane-report.json`."""

    @unittest.skipUnless(HAVE, "numpy not installed")
    def test_it_writes_the_report_read_only_and_warns_of_a_probe_without_its_buy_and_hold(self):
        from types import SimpleNamespace

        from league.ops import fast_lane as FL

        self.replies = [PASS] * 8
        self.family("a")
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.store.set_state("a", banded_version=1, live_promoted_at=at(MONDAY, 9, 31))
        self.store.set_band("a", "probe", reason="synthetic pass")
        live = LiveState(self.root / "live.sqlite")
        live.upsert("positions", {"pid": 1, "instance": "a@1:r", "family": "a", "type": "debit_vertical", "root": "SPY",
                                  "legs": "[]", "qty": 0, "opened_qty": 1, "entry": 0.4, "max_loss_share": 0.4,
                                  "collateral": 0.0, "fees": 1.0, "cash": -20.0, "opened_at": 1.0, "opened_day": "2026-09-28",
                                  "opened_minute": 1, "status": "closed", "closed_at": at(MONDAY, 15, 0), "tuition": 0,
                                  "info": json.dumps({"order": 1, "probe": True})}, "pid")
        live.close()
        alerts = []
        ctx = SimpleNamespace(root=self.root, now=lambda: at(MONDAY, 21, 0), alert=lambda level, text: alerts.append((level, text)))
        out = FL.run(ctx)                    # inside `guard.readonly()`: a writable SQLite open would raise
        self.assertEqual((out["ok"], out["bands"], out["without_bh"]), (True, 1, 1))
        doc = json.loads((self.root / FL.FILE).read_text())
        self.assertEqual((doc["window_days"], doc["reported_only"]), (FL.JOB_DAYS, True))
        self.assertEqual(doc["probe_budget"]["realized_usd"], "20.00")
        self.assertEqual(doc["probe_budget"]["realized_total_usd"], "20.00")
        self.assertEqual({r["window"] for r in doc["screen"]}, {"validation", "holdout"})
        self.assertIn("contamination", doc)
        [(level, text)] = alerts
        self.assertEqual(level, "warning")
        self.assertIn("1 Probe or Sized families have no same-risk buy-and-hold", text)


class ReportedOnly(RoundCase):
    """The drift fit and the same-risk buy-and-hold are reported, never a bar: no module of the swarm or the live path
    reads them, and the tournament's and the gate's verdicts are the same with or without the closes file and the report."""

    def test_no_swarm_or_live_module_reads_the_direction_figures(self):
        repo = Path(__file__).resolve().parents[2]
        paths = [p for tree in ("league/swarm", "league/live", "league/gym") for p in (repo / tree).rglob("*.py")]
        paths += [repo / "league" / "house.py", repo / "league" / "constitution.py"]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for needle in ("ops.direction", "ops import direction", "direction-closes", "same_risk_bh", "daily_fit(",
                           "ops.fast_lane", "ops import fast_lane", "fast-lane-report", "pooled_contamination"):
                self.assertNotIn(needle, text, f"{path.relative_to(repo)} reads {needle}")

    def outcome(self, *, closes: bool, report: bool) -> dict:
        case = RoundCase("run")
        case.setUp()
        try:
            case.replies = [PASS] * 8
            if closes:
                (case.root / "direction-closes.json").write_text(json.dumps({
                    "schema": 1, "closes": {"SPY": {f"2026-01-{d:02d}": 600.0 + d for d in range(2, 30)}}}))
            case.family("a")
            case.family("b", id="b")
            Tournament(case.store, case.pool, case.settings).validate(case.store.families(alive=True))
            if report:
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    "fast_lane_report", Path(__file__).resolve().parents[2] / "scripts" / "fast_lane_report.py")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                out = module.report(case.root, None, case.root / "direction-closes.json", today="2026-10-07")
                self.assertTrue(out["screen"], "the report has rows to read")
            gate = Gate(case.store, case.pool, case.router, case.settings, clock=case.clock).run()
            return {"gate": {k: v for k, v in gate.items()},
                    "looks": [(x["family"], x["version"], x["passed"], x["p_value"]) for x in case.store.looks()],
                    "lines": {f["id"]: (f["state"].get("validation_line") or {}).get("checks") for f in case.store.families()},
                    "refusals": [(r["family"], r["stage"]) for r in case.store.refusals()]}
        finally:
            case.doCleanups()

    @unittest.skipUnless(HAVE, "numpy not installed")
    def test_the_report_prints_the_screen_the_bands_and_the_probe_budget(self):
        """Every figure on real days (the review, Oct 7, 2026: closes dated outside the windows let the report test pass
        on the "no market closes" path): Validation in 2025, the holdout look Jan 2 - Sep 25 2026, live from Sep 28."""
        import importlib.util

        from league.ops import direction as DIR

        spec = importlib.util.spec_from_file_location(
            "fast_lane_report", Path(__file__).resolve().parents[2] / "scripts" / "fast_lane_report.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        holdout_days = DIR.sessions("2026-01-02", "2026-09-25")
        rng = random.Random(3)
        draws = {fid: random.Random(fid) for fid in ("a", "b")}
        series = {fid: [draws[fid].gauss(4.0, 10.0) for _ in holdout_days] for fid in ("a", "b")}
        holdout = series["a"]

        def answer(job):
            from league.tests.test_swarm_rounds import strong

            out = strong(job)
            if job.window == "holdout":
                out["daily"] = [[d, x, 10000.0 + x] for d, x in zip(holdout_days, series[job.family])]
                out["summary"]["pnl_per_max_loss"] = 0.08
            return out

        self.answer = answer
        self.replies = [PASS] * 8
        self.family("a")
        self.family("b")
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.store.set_state("b", validation_verdicts={})          # a verdict the map no longer keeps (pruned)
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.store.set_state("a", banded_version=1, live_promoted_at=at(MONDAY, 9, 31))
        self.store.set_band("a", "candidate", reason="synthetic pass")
        self.store.add_forward("a", "real", [{"id": "r1", "day": "2026-09-28", "pnl": -12.5, "max_loss": 40.0, "version": 1}])
        walk, closes = 580.0, {}
        for day in DIR.sessions("2024-12-31", "2026-09-30"):
            walk *= 1.0 + rng.gauss(0.0004, 0.01)
            closes[day] = round(walk, 2)
        (self.root / "direction-closes.json").write_text(json.dumps({"schema": 1, "closes": {"SPY": closes}}))
        live = LiveState(self.root / "live-copy.sqlite")
        base = {"type": "debit_vertical", "root": "SPY", "legs": "[]", "qty": 0, "opened_qty": 1, "entry": 0.4,
                "max_loss_share": 0.4, "collateral": 0.0, "fees": 1.0, "opened_at": 1.0, "opened_day": "2026-09-28",
                "opened_minute": 1, "status": "closed", "closed_at": at(MONDAY, 15, 0), "tuition": 0}
        live.upsert("positions", {**base, "pid": 1, "instance": "a@1:r", "family": "a", "cash": -12.5,
                                  "info": json.dumps({"order": 1, "probe": True})}, "pid")
        live.upsert("positions", {**base, "pid": 2, "instance": "s@1:r", "family": "s", "cash": 100.0,
                                  "info": json.dumps({"order": 2})}, "pid")        # a Sized gain: never in the budget
        # A Probe loss closed Aug 3: before the rolling window (release L-D), in the total only.
        live.upsert("positions", {**base, "pid": 3, "instance": "a@1:r", "family": "a", "cash": -30.0,
                                  "closed_at": at(dt.date(2026, 8, 3), 15, 0),
                                  "info": json.dumps({"order": 3, "probe": True})}, "pid")
        live.close()
        out = module.report(self.root, self.root / "live-copy.sqlite", self.root / "direction-closes.json",
                            today="2026-09-30")
        windows = sorted({r["window"] for r in out["screen"]})
        self.assertEqual(windows, ["holdout", "validation"])
        # Validation rows come from the store's run rows: a version whose verdict the map dropped still has its row.
        rows = {r["family"]: r for r in out["screen"] if r["window"] == "validation"}
        self.assertEqual((rows["a"]["passed"], rows["a"]["verdict_kept"]), (True, True))
        self.assertEqual((rows["b"]["passed"], rows["b"]["verdict_kept"]), (None, False))
        self.assertIsInstance(rows["a"]["bh"]["usd"], float, rows["a"]["bh"])
        self.assertEqual(rows["a"]["bh"]["days"], 250, "every 2025 session with a market return")
        look = next(r for r in out["screen"] if r["window"] == "holdout" and r["family"] == "a")
        self.assertEqual((look["level"], look["rule"]), (0.10, "flat"))
        self.assertEqual(look["tail"]["from"], "2026-07-01")
        self.assertIsInstance(look["bh"]["usd"], float, look["bh"])
        self.assertEqual(look["bh"]["days"], len(holdout_days))
        self.assertIsInstance(look["drift_window"]["beta"], float, look["drift_window"])
        self.assertEqual(look["drift_window"]["days"], len(holdout_days))
        self.assertEqual(look["drift_train"]["basis"], "train-held-hours")
        # Contamination, measured: the in-training head and the after-cutoff tail of the look's own daily series.
        head = [x for d, x in zip(holdout_days, holdout) if d < "2026-07-01"]
        tail = [x for d, x in zip(holdout_days, holdout) if d >= "2026-07-01"]
        c = look["contamination"]
        self.assertEqual((c["head"]["days"], c["tail"]["days"]), (len(head), len(tail)))
        self.assertEqual((len(head), len(tail)), (123, 61), "the holdout's 184 sessions: 123 inside Opus 5.5's training")
        self.assertAlmostEqual(c["head"]["pnl"], round(sum(head), 2))
        self.assertAlmostEqual(c["sharpe_gap"], c["head"]["sharpe_daily"] - c["tail"]["sharpe_daily"])
        pooled = out["contamination"]
        self.assertEqual((pooled["looks"], pooled["with_gap"], pooled["reported_only"]), (2, 2, True))
        self.assertIsNotNone(pooled["t"])
        band = next(b for b in out["bands"] if b["family"] == "a")
        self.assertEqual((band["family"], band["band"], band["live"]["realized_usd"], band["live"]["trades"]),
                         ("a", "candidate", -12.5, 1))
        self.assertEqual(band["live"]["sessions"], 3)
        self.assertIsInstance(band["live"]["bh"]["usd"], float, band["live"]["bh"])
        self.assertIsInstance(band["live"]["drift_window"]["beta"], float, band["live"]["drift_window"])
        self.assertEqual(band["live_vs_holdout"]["live_pnl_per_max_loss"], -12.5 / 40.0)
        self.assertEqual(band["live_vs_holdout"]["holdout_pnl_per_max_loss"], 0.08)
        self.assertIsNone(band["d5"]["demoted"])
        from league.ops.fast_lane import REALIZED_BASIS

        # THE ROLLING PROBE BUDGET (release L-D): the window's 20 sessions through Sep 30 start Sep 2 (Labor Day, Sep 7, is
        # no session), so the Aug 3 loss is in the total only; the total in force is $400 (Oct 9), so it binds.
        self.assertEqual(out["probe_budget"], {"realized_usd": "12.50", "realized_total_usd": "42.50",
                                               "realized_basis": REALIZED_BASIS["net"], "window_sessions": 20,
                                               "window_start": "2026-09-02", "at_risk_usd": "0.00", "open": 0,
                                               "max_open": 8, "budget_usd": "400", "total_budget_usd": "400",
                                               "room_usd": "357.50", "binding": "total"})
        self.assertTrue(REALIZED_BASIS["net"].startswith("net: "), "release L-D: the label is the basis in force")
        self.assertEqual(band["d5"]["rule"], "dm1")
        self.assertTrue(out["reported_only"])

    def test_the_verdicts_are_the_same_with_and_without_the_figures(self):
        plain = self.outcome(closes=False, report=False)
        self.assertTrue(plain["looks"])
        self.assertEqual(self.outcome(closes=True, report=True), plain)


if __name__ == "__main__":
    unittest.main()
