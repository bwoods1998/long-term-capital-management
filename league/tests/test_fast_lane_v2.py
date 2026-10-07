"""FAST LANE V2 (Oct 7, 2026; the owner's goal of Oct 7, item 4): the screen (the Validation line and one flat holdout look
a program), direction counts (the drift screen's refusal and the look holds off by setting), the one-structure Probe
within 10% of E with at most 3 Probe positions and the $400 Probe loss budget, same-minute entry, and the rooms the
other routes keep for Probe opens. Every figure is invented."""

from __future__ import annotations

import copy
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
from league.tests.swarm_fakes import drift_block, result
from league.tests.test_live_step import HAVE, LiveCase
from league.tests.test_swarm_look_holds import PASS, HoldCase, lean
from league.tests.test_swarm_rounds import RoundCase

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

    def plan(self, unit, *, band="probe", equity=E, fwd=None, **exposure):
        values = {k: (v if k in ("family_open", "probe_open") else D(str(v))) for k, v in exposure.items()}
        return M.plan_open(self.t, band=band, tuition=False, equity=D(str(equity)), unit=D(str(unit)), fwd=fwd,
                           exposure=M.Exposure(**values))

    def test_the_table(self):
        self.assertEqual((self.t.probe_share, self.t.probe_contracts, self.t.probe_max_open, self.t.probe_loss_budget,
                          self.t.probe_floor), (D("0.10"), 1, 3, D("400"), D("0")))
        self.assertEqual(options_money_problems(), [])
        self.assertEqual(CONSTITUTION["options_money"]["probe"]["max_open"], 3)
        # At E = $1,288.40: the Probe cap $128.84; N x cap $386.52 <= $400; inside the daily stop's $450.94.
        self.assertEqual(M.cents(M.probe_cap(self.t, E)), D("128.84"))
        self.assertEqual(M.cents(M.probe_room(self.t, E)), D("386.52"))
        self.assertLessEqual(M.probe_room(self.t, E), self.t.probe_loss_budget)
        self.assertLess(M.probe_room(self.t, E), self.t.daily_stop_share * E)
        self.assertEqual(M.probe_room(self.t, None), M.ZERO)

    def test_one_structure_within_ten_percent(self):
        self.assertEqual(self.plan(40).qty, 1)
        self.assertEqual(self.plan("128.84").qty, 1)
        refused = self.plan(130)
        self.assertEqual(refused.qty, 0)
        self.assertIn("over the Probe's cap of $128.84", refused.reason)

    def test_at_most_three_probe_positions(self):
        self.assertEqual(self.plan(40, probe_open=2).qty, 1)
        refused = self.plan(40, probe_open=3)
        self.assertEqual(refused.qty, 0)
        self.assertIn("3 Probe positions held or working; the most at once is 3", refused.reason)

    def test_the_loss_budget_counts_realized_and_at_risk(self):
        self.assertEqual(self.plan(40, probe_realized="300", probe_at_risk="60").qty, 1, "exactly $400")
        refused = self.plan("40.01", probe_realized="300", probe_at_risk="60")
        self.assertEqual(refused.qty, 0)
        self.assertTrue(refused.reason.startswith("probe: the loss budget"), refused.reason)
        self.assertIn("realized $300.00, held or working $60.00", refused.reason)
        self.assertEqual(self.plan(40, probe_realized="400").qty, 0, "spent")
        self.assertEqual(self.plan(40, probe_at_risk="380").qty, 0, "held and working count whole")

    def test_sized_kelly_sizing_and_c3(self):
        fwd = M.forward_stats([{"pnl": r * 100.0, "max_loss": 100.0} for r in [0.44, -0.28] * 10], 0.8)
        kelly = M.kelly_cap(self.t, D("5481.65"), fwd)
        self.assertGreater(kelly, D("20"))
        sized = self.plan(10, band="sized", equity="5481.65", fwd=fwd)
        self.assertEqual(sized.qty, int(kelly / D("10")), "Kelly buys structures: floor(kelly / unit), Sized limits")
        self.assertTrue(sized.reason.startswith("sized:"), sized.reason)
        under = self.plan(kelly + 1, band="sized", equity="5481.65", fwd=fwd)
        self.assertEqual(under.qty, 1, "Kelly buys none: the Probe's one structure, never smaller")
        self.assertTrue(under.reason.startswith("sized: one structure"), under.reason)
        # A Sized open is never refused by the Probe budget or the Probe count.
        spent = self.plan(10, band="sized", equity="5481.65", fwd=fwd, probe_open=3, probe_realized="400",
                          probe_at_risk="100")
        self.assertEqual(spent.qty, int(kelly / D("10")))


class TheTally(unittest.TestCase):
    """`real.probe_tally` over the live state's own rows."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "live.sqlite"
        self.state = LiveState(self.path)
        self.oid = self.pid = 0

    def position(self, instance, *, share, fees=1.0, status="open", cash=None, qty=1, tuition=0):
        self.pid += 1
        self.state.upsert("positions", {"pid": self.pid, "instance": instance, "family": instance.split("@")[0],
                                        "type": "debit_vertical", "root": "SPY", "legs": "[]",
                                        "qty": 0 if status == "closed" else qty, "opened_qty": qty, "entry": share,
                                        "max_loss_share": share, "collateral": 0.0, "fees": fees,
                                        "cash": cash if cash is not None else -(share * 100 + fees), "opened_at": 1.0,
                                        "opened_day": "2026-10-05", "opened_minute": 1, "status": status,
                                        "closed_at": 2.0 if status == "closed" else None, "tuition": tuition,
                                        "info": "{}"}, "pid")

    def order(self, instance, *, max_loss, qty=1, filled=0, fees=1.0, status="working", day="2026-10-07", pid=None,
              tuition=0):
        self.oid += 1
        self.state.upsert("orders", {"oid": self.oid, "client_id": f"lv-{self.oid}", "instance": instance,
                                     "family": instance.split("@")[0], "action": "open", "type": "debit_vertical",
                                     "root": "SPY", "legs": "[]", "qty": qty, "limit_value": 0.3, "limit_price": "0.30",
                                     "placed_at": 1.0, "day": day, "placed_minute": 1, "status": status, "pid": pid,
                                     "filled_qty": filled, "max_loss": max_loss, "fees_est": fees, "tuition": tuition,
                                     "answer": json.dumps({"dispatched": True}), "updated_at": 1.0}, "oid")

    def tally(self, state=None):
        return probe_tally((state or self.state).rows, week_start="2026-10-05")

    def test_it_counts_real_positions_and_orders_only(self):
        self.position("a@1:r", share=0.40, status="closed", cash=-50.0)       # a loss of $50
        self.position("b@1:r", share=0.40, status="closed", cash=20.0)        # a gain offsets it: realized $30
        self.position("a@1:r", share=0.40, fees=1.0, cash=-41.0)              # held: 40 + 2 x 1 = 42
        self.position("b@2:r", share=0.40, fees=1.0, cash=-60.0)              # a broken structure lost more: 60
        self.order("c@1:r", max_loss=80.0, qty=2, filled=1)                   # working: (80 + 2) x 1 / 2 = 41
        self.order("c@1:r", max_loss=30.0, status="lost")                     # lost this week: whole, 32
        self.order("c@1:r", max_loss=30.0, status="lost", day="2026-09-30")   # lost last week: not counted
        self.order("c@1:r", max_loss=30.0, status="filled")                   # done: its position counts
        for other in ("t@1:t", "i@1:i", "house:rebound-live@1:h"):            # tuition, incubator, the House test
            self.position(other, share=0.90, status="closed", cash=-90.0)
            self.position(other, share=0.90)
            self.order(other, max_loss=90.0)
        open_n, realized, at_risk = self.tally()
        self.assertEqual((open_n, realized, at_risk), (4, D("30"), D("42") + D("60") + D("41") + D("32")))

    def test_it_survives_a_restart(self):
        self.position("a@1:r", share=0.40, status="closed", cash=-50.0)
        self.position("a@1:r", share=0.40)
        before = self.tally()
        self.state.close()
        again = LiveState(self.path)
        self.addCleanup(again.close)
        self.assertEqual(probe_tally(again.rows, week_start="2026-10-05"), before)

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
        """A closed real position that lost $400: the Probe loss budget is spent."""
        live.state.upsert("positions", {"pid": 900, "instance": "old@1:r", "family": "old", "type": "debit_vertical",
                                        "root": "SPY", "legs": "[]", "qty": 0, "opened_qty": 1, "entry": 4.0,
                                        "max_loss_share": 4.0, "collateral": 0.0, "fees": 1.0, "cash": -400.0,
                                        "opened_at": 1.0, "opened_day": "2026-09-25", "opened_minute": 1,
                                        "status": "closed", "closed_at": 2.0, "tuition": 0, "info": "{}"}, "pid")

    def test_a_candidate_moved_to_probe_opens_from_the_next_minute(self):
        live = self.make([family("vert", VERTICAL, band="candidate", params={"hold": 600})])
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "probe")
        self.assertEqual(live.instances["vert@1:r"].mode, "live")
        self.run_to(9, 33)
        opens = [b for b in self.venue.sent if b.get("legs") and b["legs"][0]["position_intent"] == "buy_to_open"]
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0]["qty"], "1", "one structure")

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
        self.assertEqual(M.cents(M.probe_room(live.table, E)), D("386.52"))


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
    def setUp(self):
        self.t = M.Table.from_constitution()

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
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 3, "opens": 3})])
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

        live = self.make([])
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


if __name__ == "__main__":
    unittest.main()
