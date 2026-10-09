"""RELEASE L-D (Oct 9, 2026; the plan of Oct 9, "L: Release L-D", and its critic): THE PROBE LOSS BUDGET read NET (L1), 8
Probe slots inside the $400 envelope with the Probe room capped at the budget (L2), DM1's demotion behind its switch with
its sigma read from the swarm's family state (L3), and the marketable natural limit `{"natural": k}` (L5).

Each L-D rule has a rollback value ("gross", 3, "dm0": the CON-only rollback, `money_fakes.rollback_table`), and each is
checked here against a FROZEN COPY of fast lane v2's code at ccfa48d5 (`v2_probe_tally`, `v2_demotion`, `v2_band_for`):
the rollback is fast lane v2's rule byte for byte, not a rewrite of it. Every figure is invented."""

from __future__ import annotations

import copy
import itertools
import json
import math
import random
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from typing import Any, Mapping

from league.constitution import CONSTITUTION, OPTIONS_MONEY_BOUNDS, OPTIONS_MONEY_CHOICES, options_money_problems
from league.live import money as M
from league.tests.money_fakes import FAST_LANE_V2, constitution, rollback_table, table
from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    import numpy as np

    from league.gym import ctx as C
    from league.gym import greeks as G
    from league.gym import legs as L
    from league.gym import venue as V
    from league.live.real import probe_tally
    from league.live.state import LiveState, loads
    from league.tests.live_fakes import MONDAY, VERTICAL, at, family

E = D("1289.34")        # the sizing equity at the start of day Oct 8, 2026 (the plan's E)


# ===================================================================================== fast lane v2, frozen (ccfa48d5)
def v2_probe_tally(rows, *, day: str):
    """`league/live/real.py` `probe_tally` at ccfa48d5 (fast lane v2), frozen: the reference for "gross"."""
    from league.live.real import REAL_SUFFIX, _expired

    like = REAL_SUFFIX
    at_risk = M.ZERO
    realized = M.ZERO
    open_n = 0
    for r in rows("SELECT qty, opened_qty, max_loss_share, fees, cash, status, info FROM positions "
                  "WHERE substr(instance, -2)=? AND tuition=0", (like,)):
        if r["status"] == "closed":
            if (loads(r["info"], {}) or {}).get("probe") is True:
                realized += max(M.ZERO, -M.D(r["cash"]))
            continue
        units = int(r["opened_qty"]) if r["status"] == "unpriced_close" else max(0, int(r["qty"]))
        at_risk += max(M.D(r["max_loss_share"]) * V.MULTIPLIER * units + 2 * M.D(r["fees"]), -M.D(r["cash"]))
        open_n += 1
    for r in rows("SELECT qty, filled_qty, status, max_loss, fees_est, day, pid, legs FROM orders WHERE action='open' "
                  "AND substr(instance, -2)=? AND tuition=0 AND status IN ('pending', 'working', 'unknown', 'lost')", (like,)):
        lost = r["status"] == "lost"
        remaining = int(r["qty"]) if lost else max(0, int(r["qty"]) - int(r["filled_qty"]))
        at_risk += (M.D(r["max_loss"]) + 2 * M.D(r["fees_est"])) * M.D(remaining) / max(1, int(r["qty"]))
        if r["pid"] is None and not (lost and _expired(r["legs"], day)):
            open_n += 1
    return open_n, realized, at_risk


def v2_demotion(fwd: M.Forward) -> str | None:
    """`money.demotion` at ccfa48d5 (D5), frozen."""
    if fwd.real_n and fwd.real_max_loss and fwd.real_pnl < -M.DEMOTE_LOSS_MULTIPLE * fwd.real_max_loss:
        return (f"D5: its {fwd.real_n} real trades realized ${fwd.real_pnl:.2f}, below -{M.DEMOTE_LOSS_MULTIPLE} x its mean "
                f"maximum loss ${fwd.real_max_loss:.2f}: exits only")
    if fwd.replay_n >= M.REPLAY_GAP_MIN_TRADES and fwd.replay_gap is not None and fwd.replay_gap > M.REPLAY_GAP_BOUND:
        return (f"D5: its live fills ran {fwd.replay_gap:.3f} a dollar of maximum loss below its replay of the same days "
                f"over {fwd.replay_n} real trades (bound {M.REPLAY_GAP_BOUND}): exits only")
    return None


def v2_band_for(table_: M.Table, row: Mapping[str, Any], equity: D, fwd: M.Forward, *, probe_sessions: int = 0):
    """`money.band_for` at ccfa48d5, frozen (its helpers, unchanged by L-D, are today's)."""
    band = str(row.get("band") or "")
    if band not in ("candidate", "probe", "sized"):
        return band, "not a Candidate"
    if not row.get("holdout_passed"):
        return "candidate", "has not passed the holdout"
    if fwd.negative:
        return "candidate", f"its forward record turned negative ({fwd.n} trades, ${fwd.pnl:.2f})"
    if band in ("candidate", "probe"):
        why = v2_demotion(fwd)
        if why:
            return "candidate", why
    why = table_.family_allowed(str(row.get("structure") or ""), equity)
    if why:
        return "candidate", why
    typical = row.get("typical_max_loss_usd")
    try:
        unit = M.D(typical) if typical is not None else None
    except (ValueError, ArithmeticError):
        unit = None
    if (unit is None or unit <= 0) and band == "candidate":
        return "candidate", "its typical maximum loss is unknown (no structure in the banded version's validation run)"
    if unit is not None and unit > 0 and not M.fits_probe(table_, equity, unit):
        floor = f" and the one-contract floor of ${table_.probe_floor}" if table_.probe_floor > 0 else ""
        return "candidate", (f"its typical structure risks ${M.cents(unit)}, over the Probe's cap of "
                             f"${M.cents(M.probe_cap(table_, equity))} ({table_.probe_share:%} of ${M.cents(equity)}){floor}")
    if band in ("probe", "sized") and fwd.real_bad:
        return "probe", (f"its {fwd.real_n} real trades lose (mean {fwd.real_mean:.4f} a dollar of maximum loss): held at "
                         "Probe")
    probe_done = band == "sized" or (fwd.real_n >= table_.min_probe_real_trades and probe_sessions >= table_.min_probe_sessions)
    if band in ("probe", "sized") and M.sized_ok(table_, fwd) and probe_done:
        return "sized", (f"a forward record of {fwd.n} trades, mean {fwd.mean:.4f} a dollar of maximum loss, "
                         f"{table_.sized_confidence:.0%} lower bound {fwd.lcb:.4f}, after {fwd.real_n} real Probe trades")
    if band == "candidate":
        return "probe", "passed the holdout and trades a real type that fits the Probe's cap (Sized only from Probe)"
    return "probe", "passed the holdout and trades a real type that fits the Probe's cap"


def v2_probe_room(table_: M.Table, equity):
    """`money.probe_room` at ccfa48d5, frozen."""
    return M.ZERO if equity is None else table_.probe_max_open * M.probe_cap(table_, equity)


# ================================================================================================ the constitution
class TheRows(unittest.TestCase):
    def test_the_three_rows_and_their_bounds(self):
        probe = CONSTITUTION["options_money"]["probe"]
        self.assertEqual((probe["loss_basis"], probe["max_open"], probe["demotion"]), ("net", 8, "dm1"))
        self.assertEqual(OPTIONS_MONEY_BOUNDS["probe.max_open"], ("0", "8"))
        self.assertEqual(OPTIONS_MONEY_CHOICES, {"probe.loss_basis": ("gross", "net"), "probe.demotion": ("dm0", "dm1")})
        self.assertEqual(M.LOSS_BASES, OPTIONS_MONEY_CHOICES["probe.loss_basis"])
        self.assertEqual(M.DEMOTION_RULES, OPTIONS_MONEY_CHOICES["probe.demotion"])
        self.assertEqual(FAST_LANE_V2, {"loss_basis": "gross", "max_open": 3, "demotion": "dm0"})
        self.assertEqual(options_money_problems(), [])
        self.assertEqual(options_money_problems(constitution(**FAST_LANE_V2)), [], "the CON-only rollback is in bounds")
        t = M.Table.from_constitution()
        self.assertEqual((t.probe_loss_basis, t.probe_max_open, t.probe_demotion), ("net", 8, "dm1"))
        r = rollback_table()
        self.assertEqual((r.probe_loss_basis, r.probe_max_open, r.probe_demotion), ("gross", 3, "dm0"))

    def test_the_table_refuses_a_rule_it_does_not_know(self):
        for key, value in (("loss_basis", "Net"), ("loss_basis", ""), ("loss_basis", "NET"), ("loss_basis", None),
                           ("max_open", 9), ("max_open", -1), ("demotion", "DM1"), ("demotion", ""),
                           ("demotion", "dm2"), ("demotion", True)):
            c = constitution(**{key: value})
            self.assertTrue(any(f"probe.{key}" in p for p in options_money_problems(c)), (key, value))
            with self.assertRaises(ValueError, msg=(key, value)):
                M.Table.from_constitution(c)
        for key in ("loss_basis", "demotion"):
            c = copy.deepcopy(CONSTITUTION)
            del c["options_money"]["probe"][key]
            with self.assertRaises(ValueError, msg=key):
                M.Table.from_constitution(c)

    def test_the_digests_moved(self):
        from league.constitution import PINNED_DIGEST, digest, money_digest

        self.assertEqual(money_digest(), "b212d4e60a6b2a29666fb923907b73c6ec9ee154b7be3c50fd3e9fe45408dd47")
        self.assertEqual(digest(), PINNED_DIGEST)
        self.assertNotEqual(money_digest(constitution(**FAST_LANE_V2)), money_digest())
        for key, value in (("loss_basis", "gross"), ("max_open", 3), ("demotion", "dm0")):
            self.assertNotEqual(money_digest(constitution(**{key: value})), money_digest(), key)


# ================================================================================================ L1: the net budget
@unittest.skipUnless(HAVE, "numpy not installed")
class TheNetTally(unittest.TestCase):
    """`real.probe_tally` over the live state's own rows, basis by basis."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = LiveState(Path(self.tmp.name) / "live.sqlite")
        self.addCleanup(self.state.close)
        self.oid = self.pid = 0

    def position(self, instance, *, share=0.40, fees=1.0, status="closed", cash=None, qty=1, tuition=0, probe=True):
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

    def tally(self, basis):
        return probe_tally(self.state.rows, day="2026-10-07", basis=basis)

    def test_a_probe_gain_offsets_a_probe_loss_under_net_but_a_sized_gain_never_does(self):
        self.position("a@1:r", cash=-50.0)                       # a Probe loss
        self.position("b@1:r", cash=20.0)                        # a Probe gain: offsets it under NET only
        self.assertEqual(self.tally("net")[1], D("30"))
        self.assertEqual(self.tally("gross")[1], D("50"))
        self.position("s@1:r", cash=500.0, probe=False)          # a Sized gain: no Probe mark, never counted
        self.position("o@1:r", cash=-70.0, probe=False)          # a Sized loss: not the Probe's either
        self.assertEqual(self.tally("net")[1], D("30"))
        self.assertEqual(self.tally("gross")[1], D("50"))
        self.position("c@1:r", cash=100.0)                       # Probe gains past the losses: floored at $0
        self.assertEqual(self.tally("net")[1], D("0"), "a net gain is no extra room")
        self.position("d@1:r", cash=-90.0)
        self.assertEqual(self.tally("net")[1], D("20"), "the running net: -50 + 20 + 100 - 90")
        self.assertEqual(self.tally("gross")[1], D("140"))
        for other in ("t@1:t", "i@1:i", "house:rebound-live@1:h"):   # tuition, incubator, the House test: never
            self.position(other, cash=-90.0)
            self.position(other, cash=300.0)
        self.position("x@1:r", cash=400.0, tuition=1)            # a tuition-flagged real row: never either
        self.assertEqual((self.tally("net")[1], self.tally("gross")[1]), (D("20"), D("140")))

    def test_at_risk_and_the_count_are_the_same_under_both_and_a_lost_open_counts_whole(self):
        self.position("a@1:r", cash=-50.0)
        self.position("a@1:r", status="open", fees=1.0, cash=-41.0)                      # held: 42
        self.position("b@2:r", status="open", fees=1.0, cash=-60.0, probe=False)         # Sized held: 60
        self.order("c@1:r", max_loss=80.0, qty=2, filled=1)                              # working: 41
        self.order("c@1:r", max_loss=30.0, status="lost", day="2026-09-21")              # lost, any week: 32 whole
        net, gross = self.tally("net"), self.tally("gross")
        self.assertEqual((net[0], net[2]), (gross[0], gross[2]))
        self.assertEqual(net[2], D("42") + D("60") + D("41") + D("32"))
        self.assertEqual(net[0], 4)
        # The envelope with the lost open whole: $50 + $175 already; a $175.01 open would pass $400.
        t = M.Table.from_constitution()
        ok = M.plan_open(t, band="probe", tuition=False, equity=E, unit=D("128.93"), fwd=None,
                         exposure=M.Exposure(probe_open=net[0], probe_realized=net[1], probe_at_risk=net[2]))
        self.assertEqual(ok.qty, 1, ok.reason)
        refused = M.plan_open(t, band="probe", tuition=False, equity=E, unit=D("128.93"), fwd=None,
                              exposure=M.Exposure(probe_open=net[0], probe_realized=net[1],
                                                  probe_at_risk=net[2] + D("46.08")))
        self.assertEqual(refused.qty, 0)
        self.assertTrue(refused.reason.startswith("probe: the loss budget"), refused.reason)

    def test_gross_is_fast_lane_v2s_figure_on_any_rows_and_net_is_the_floored_sum(self):
        rng = random.Random(20261009)
        for case in range(40):
            self.state.execute("DELETE FROM positions")
            self.state.execute("DELETE FROM orders")
            marked = M.ZERO
            for _ in range(rng.randrange(0, 14)):
                suffix = rng.choice([":r", ":r", ":r", ":t", ":i", ":h"])
                status = rng.choice(["closed", "closed", "open", "awaiting_expiry", "unpriced_close"])
                cash = round(rng.uniform(-150, 150), 2)
                probe, tuition = rng.random() < 0.7, int(rng.random() < 0.15)
                self.position(f"f{rng.randrange(4)}@1{suffix}", share=round(rng.uniform(0.1, 1.3), 2),
                              fees=round(rng.uniform(0.5, 2.0), 2), status=status, cash=cash, qty=rng.randrange(1, 3),
                              tuition=tuition, probe=probe)
                if suffix == ":r" and status == "closed" and probe and not tuition:
                    marked += D(str(cash))
            for _ in range(rng.randrange(0, 6)):
                self.order(f"g{rng.randrange(3)}@1{rng.choice([':r', ':r', ':t'])}", max_loss=round(rng.uniform(10, 120), 2),
                           qty=2, filled=rng.randrange(0, 2), status=rng.choice(["working", "pending", "unknown", "lost", "filled"]),
                           day=rng.choice(["2026-09-21", "2026-10-07"]), expiry=rng.choice(["2026-10-02", "2026-10-16"]))
            v2 = v2_probe_tally(self.state.rows, day="2026-10-07")
            self.assertEqual(self.tally("gross"), v2, case)
            net = self.tally("net")
            self.assertEqual((net[0], net[2]), (v2[0], v2[2]), case)
            self.assertEqual(net[1], max(M.ZERO, -marked), case)
            self.assertLessEqual(net[1], v2[1], "net never above gross")

    def test_any_other_basis_is_refused(self):
        for basis in ("Net", "", "GROSS", None, "hwm"):
            with self.assertRaises(ValueError, msg=basis):
                probe_tally(self.state.rows, day="2026-10-07", basis=basis)
        with self.assertRaises(TypeError):
            probe_tally(self.state.rows, day="2026-10-07")         # no default: every caller names the basis in force


# ======================================================================================== L1, L2: the envelope, the slots
class TheEnvelope(unittest.TestCase):
    def setUp(self):
        self.t = M.Table.from_constitution()

    def plan(self, unit, *, table_=None, **exposure):
        values = {k: (v if k in ("family_open", "probe_open") else D(str(v))) for k, v in exposure.items()}
        return M.plan_open(table_ or self.t, band="probe", tuition=False, equity=E, unit=D(str(unit)), fwd=None,
                           exposure=M.Exposure(**values))

    def test_the_open_that_would_breach_400_counting_open_maximum_loss_is_refused(self):
        self.assertEqual(self.plan(100, probe_realized="100", probe_at_risk="200").qty, 1, "exactly $400")
        refused = self.plan("100.01", probe_realized="100", probe_at_risk="200")
        self.assertEqual(refused.qty, 0)
        self.assertIn("realized net $100.00, held or working $200.00", refused.reason)
        self.assertEqual(self.plan(1, probe_at_risk="400").qty, 0, "open maximum loss alone fills it")
        # A Sized open is never refused by it.
        strong = M.forward_stats([{"pnl": r * 100.0, "max_loss": 100.0} for r in [0.9, 0.8, 1.0, 0.7] * 5], 0.8)
        sized = M.plan_open(self.t, band="sized", tuition=False, equity=E, unit=D("10"), fwd=strong,
                            exposure=M.Exposure(probe_open=8, probe_realized=D("400"), probe_at_risk=D("400")))
        self.assertGreater(sized.qty, 0)

    def test_eight_slots_admit_the_fourth_to_eighth_open_only_inside_the_envelope(self):
        # $50 units: eight fit the $400 exactly; the ninth is refused by the count.
        for n in range(3, 8):
            self.assertEqual(self.plan(50, probe_open=n, probe_at_risk=str(50 * n)).qty, 1, n)
        self.assertEqual(self.plan(50, probe_open=7, probe_at_risk="350").qty, 1, "the 8th: $400 exactly")
        ninth = self.plan(1, probe_open=8, probe_at_risk="10")
        self.assertEqual(ninth.qty, 0)
        self.assertIn("8 Probe positions held or working; the most at once is 8", ninth.reason)
        # $128.93 units (10% of E): the dollars bind before the count, at the fourth.
        self.assertEqual(self.plan("128.93", probe_open=2, probe_at_risk="257.86").qty, 1, "the third")
        fourth = self.plan("128.93", probe_open=3, probe_at_risk="386.79")
        self.assertEqual(fourth.qty, 0)
        self.assertTrue(fourth.reason.startswith("probe: the loss budget"), fourth.reason)
        # A realized net loss takes slots' dollars too: $300 realized leaves one $100 open.
        self.assertEqual(self.plan(100, probe_open=4, probe_realized="300").qty, 1)
        self.assertEqual(self.plan("100.01", probe_open=4, probe_realized="300").qty, 0)
        # The rollback's three slots refuse the fourth whatever the dollars.
        self.assertEqual(self.plan(10, probe_open=3, table_=rollback_table()).qty, 0)
        self.assertEqual(self.plan(10, probe_open=3).qty, 1)

    def test_the_rollback_plans_as_fast_lane_v2_did(self):
        r = rollback_table()
        for unit, open_, realized, risk in itertools.product(("40", "128.84", "130"), (0, 2, 3), ("0", "300", "400"),
                                                             ("0", "60", "380")):
            plan = self.plan(unit, table_=r, probe_open=open_, probe_realized=realized, probe_at_risk=risk)
            if plan.qty == 0 and plan.reason.startswith("probe: the loss budget"):
                self.assertIn(f"(realized ${D(realized):.2f}, held", plan.reason, "the rollback's words, as before")


# ============================================================================================ L2: the Probe room
class TheProbeRoom(unittest.TestCase):
    def test_it_is_the_lower_of_the_slots_and_the_budget(self):
        t, r = M.Table.from_constitution(), rollback_table()
        self.assertEqual(M.cents(M.probe_room(r, E)), D("386.80"), "3 x $128.934")
        self.assertEqual(M.cents(M.probe_room(t, E)), D("400.00"), "never 8 x $128.934 = $1,031.47")
        self.assertEqual(M.cents(v2_probe_room(t, E)), D("1031.47"), "what the old formula would claim at 8")
        self.assertEqual(M.probe_room(t, None), M.ZERO)
        self.assertEqual(M.cents(M.probe_room(t, D("481.63"))), D("385.30"), "8 x 10% under $400 at a small E")
        # At three slots the room is fast lane v2's at any E to $1,333.33 (3 x 10% x E = $400); above it, the $400 a
        # Probe open can ever hold.
        for equity in ("100", "481.63", "1000", "1288.40", "1289.34", "1333.33"):
            self.assertEqual(M.probe_room(r, D(equity)), v2_probe_room(r, D(equity)), equity)
        self.assertEqual(M.probe_room(r, D("1465")), D("400"))
        self.assertEqual(v2_probe_room(r, D("1465")), D("439.5"))

    def test_the_incubator_opens_at_eight_slots_with_the_probe_idle(self):
        """The critic, B1: at 8 slots the old room ($1,031.47 + the House test's $100 at E $1,289.34) refused every
        incubator open, with nothing else open; capped, a $75 lot opens."""
        t = M.Table.from_constitution()
        for room, qty in ((M.probe_room(t, E) + t.house_test_structure, 1),
                          (v2_probe_room(t, E) + t.house_test_structure, 0)):
            plan = M.plan_incubator(t, unit=D("75"), equity=E, tally=M.IncubatorTally(), exposure=M.Exposure(), room=room)
            self.assertEqual(plan.qty, qty, plan.reason)
        # At three slots the plan is fast lane v2's.
        r = rollback_table()
        for book in ("0", "500", "600", "700"):
            exposure = M.Exposure(book_loss=D(book))
            new = M.plan_incubator(r, unit=D("75"), equity=E, tally=M.IncubatorTally(), exposure=exposure,
                                   room=M.probe_room(r, E) + r.house_test_structure)
            old = M.plan_incubator(r, unit=D("75"), equity=E, tally=M.IncubatorTally(), exposure=exposure,
                                   room=v2_probe_room(r, E) + r.house_test_structure)
            self.assertEqual(new, old, book)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheRoomsLive(LiveCase):
    """The incubator's room through the live path's own object (the House live test's: `test_live_house_test`
    `test_at_eight_probe_slots_it_opens_with_the_probe_idle`; the calibration's: `test_live_calibration`
    `test_at_eight_probe_slots_it_leaves_the_budget_not_eight_caps`)."""

    def test_the_incubator_keeps_the_capped_room(self):
        live = self.make([])
        self.run_to(9, 31)
        self.assertEqual(live.table.probe_max_open, 8)
        test = live.table.house_test_structure if live.switches().get("house_test") else M.ZERO
        self.assertEqual(live.incubator.room(E) - test, D("400"))
        self.assertEqual(live.incubator.room(E) - test, M.probe_room(live.table, E))


# ============================================================================================== L3: DM1
def real_rows(returns, *, max_loss=40.0, version=1, day0=1):
    return [{"day": f"2026-10-{day0 + i:02d}", "source": "real", "pnl": r * max_loss, "max_loss": max_loss,
             "version": version} for i, r in enumerate(returns)]


def shadow_rows(returns, *, max_loss=40.0, version=1, month="11"):
    return [{"day": f"2026-{month}-{1 + i:02d}", "source": "shadow", "pnl": r * max_loss, "max_loss": max_loss,
             "version": version} for i, r in enumerate(returns)]


def matched(n, *, gap, max_loss=50.0):
    out = []
    for i in range(n):
        day = f"2026-10-{i + 1:02d}"
        out.append({"day": day, "source": "real", "pnl": 0.0, "max_loss": max_loss, "version": 1})
        out.append({"day": day, "source": "nightly", "pnl": gap * max_loss, "max_loss": max_loss, "version": 1})
    return out


def row(band="probe", **kw):
    return {"family": "f", "band": band, "structure": "debit_vertical", "holdout_passed": True,
            "typical_max_loss_usd": 40.0, **kw}


class DM1(unittest.TestCase):
    def setUp(self):
        self.t = M.Table.from_constitution()

    def band(self, rows, band="probe", *, negative=None, table_=None, **kw):
        fwd = M.forward_stats(rows, 0.8, version=1, negative=negative)
        return M.band_for(table_ or self.t, row(band, **kw), E, fwd)

    def test_it_never_fires_under_ten_real_trades(self):
        nine = real_rows([-1.0] * 9)
        self.assertEqual(self.band(nine, validation_r_sd=0.1)[0], "probe")
        self.assertIsNone(M.demotion(M.forward_stats(nine, 0.8, version=1), band="probe", rule="dm1", validation_r_sd=0.1))
        self.assertEqual(self.band(nine, table_=rollback_table())[0], "candidate", "D5's loss leg would have: -9 < -3")

    def test_it_fires_just_below_the_band_and_not_just_above(self):
        # sigma 1.0 (the Validation sd), n = 10: the line is -1.645 x 1.0 x sqrt(10) = -5.2019.
        line = -1.645 * math.sqrt(10)
        below = real_rows([line / 10 - 0.001] * 10)            # sum -5.2119
        above = real_rows([line / 10 + 0.001] * 10)            # sum -5.1919
        band, why = self.band(below, validation_r_sd=1.0)
        self.assertEqual(band, "candidate")
        self.assertTrue(why.startswith("DM1: its 10 real trades returned -5.212 maximum losses in sum, below -1.645 x sigma "
                                       "1.000 x sqrt(10) = -5.202"), why)
        self.assertIn("its banded version's Validation run", why)
        self.assertEqual(self.band(above, validation_r_sd=1.0)[0], "probe")
        for band_ in ("probe", "sized"):
            self.assertIsNotNone(M.live_demotion(self.t, band_, M.forward_stats(below, 0.8, version=1), 1.0), band_)
            self.assertIsNone(M.live_demotion(self.t, band_, M.forward_stats(above, 0.8, version=1), 1.0), band_)
        # Sized falls to Candidate on it too (D5's mechanics: back to Candidate, exits only).
        self.assertEqual(self.band(below, "sized", validation_r_sd=1.0)[0], "candidate")

    def test_sigma_is_the_validation_sd_then_the_forward_records_then_two(self):
        rows = real_rows([-0.9, -0.1] * 5)                     # n 10, sum -5.0; its own sd 0.4216
        fwd = M.forward_stats(rows, 0.8, version=1)
        self.assertEqual(M.dm1_sigma(fwd, 1.5)[0], 1.5)
        self.assertAlmostEqual(M.dm1_sigma(fwd, None)[0], fwd.sd)
        self.assertIn("forward record of 10 trades", M.dm1_sigma(fwd, None)[1])
        self.assertAlmostEqual(fwd.sd, 0.42164, places=4)
        for garbage in (None, 0, 0.0, -1.0, float("nan"), float("inf"), "1.5", True, [1.5]):
            self.assertAlmostEqual(M.dm1_sigma(fwd, garbage)[0], fwd.sd, msg=repr(garbage))
        # The forward sd at 1.5: -5.0 is above -1.645 x 1.5 x sqrt(10) = -7.80 (stays); at its own 0.42, below -2.19.
        self.assertEqual(self.band(rows, validation_r_sd=1.5)[0], "probe")
        self.assertEqual(self.band(rows)[0], "candidate")
        # Under ten trades in the record there is no forward sd: 2.0 (here only through `dm1_sigma` itself).
        few = M.forward_stats(real_rows([-0.9, -0.1] * 4), 0.8, version=1)
        self.assertEqual(M.dm1_sigma(few, None)[0], M.DM1_FALLBACK_SIGMA)
        # A record with no spread at all (every trade lost its whole maximum loss): sd 0 reads as absent, so 2.0.
        flat = real_rows([-1.0] * 11)
        fwd = M.forward_stats(flat, 0.8, version=1)
        self.assertEqual(fwd.sd, 0.0)
        self.assertEqual(M.dm1_sigma(fwd, None), (2.0, M.dm1_sigma(fwd, None)[1]))
        self.assertIn("census", M.dm1_sigma(fwd, None)[1])
        # -11 < -1.645 x 2 x sqrt(11) = -10.91: it fires at 11 (the critic: 11 or more closes nearly all losers); not at 10.
        self.assertEqual(self.band(flat)[0], "candidate")
        self.assertEqual(self.band(real_rows([-1.0] * 10))[0], "probe")
        self.assertEqual((M.DM1_MIN_REAL_TRADES, M.DM1_Z, M.DM1_FALLBACK_SIGMA, M.DM1_SIGMA_MIN_TRADES), (10, 1.645, 2.0, 10))

    def test_d5s_loss_leg_and_the_negative_record_no_longer_end_a_probe_or_sized_band(self):
        four = real_rows([-0.76] * 4)                          # -$121.60 < -3 x $40: D5 would end it
        self.assertEqual(self.band(four)[0], "probe")
        self.assertEqual(self.band(four, table_=rollback_table())[0], "candidate")
        negative = shadow_rows([-0.1] * 25)
        self.assertTrue(M.forward_stats(negative, 0.8, version=1).negative)
        self.assertEqual(self.band(negative)[0], "probe")
        self.assertEqual(self.band(negative, negative=True)[0], "probe", "the swarm's flag too")
        self.assertEqual(self.band(negative, table_=rollback_table())[0], "candidate")
        self.assertFalse(M.negative_demotes(self.t, "probe"))
        self.assertFalse(M.negative_demotes(self.t, "sized"))
        self.assertTrue(M.negative_demotes(self.t, "candidate"))
        for band_ in ("candidate", "probe", "sized"):
            self.assertTrue(M.negative_demotes(rollback_table(), band_))
        # A Sized family with a negative record is not demoted for it, but it is no longer Sized either (Sized rules).
        self.assertEqual(self.band(negative, "sized", negative=True)[0], "probe")

    def test_a_candidate_keeps_every_check_of_dm0_and_a_version_dm1_demoted_stays_a_candidate(self):
        negative = shadow_rows([-0.1] * 25)
        self.assertEqual(self.band(negative, "candidate"), self.band(negative, "candidate", table_=rollback_table()))
        self.assertEqual(self.band(negative, "candidate")[0], "candidate")
        four = real_rows([-0.76] * 4)
        self.assertEqual(self.band(four, "candidate")[0], "candidate", "D5's loss leg, for a Candidate")
        self.assertTrue(self.band(four, "candidate")[1].startswith("D5:"))
        # Sticky: ten trades at -0.3 with a Validation sd of 0.5: DM1's line is -2.60, D5's -3 x $40 = -$120 is not
        # passed (-$120.00), so only DM1 keeps the demoted version a Candidate.
        rows = real_rows([-0.3] * 10)
        self.assertEqual(self.band(rows, validation_r_sd=0.5)[0], "candidate")
        band, why = self.band(rows, "candidate", validation_r_sd=0.5)
        self.assertEqual(band, "candidate")
        self.assertTrue(why.startswith("DM1:"), why)
        self.assertEqual(self.band(rows, "candidate", table_=rollback_table())[0], "probe", "dm0 would promote it again")

    def test_the_replay_gap_leg_and_the_real_bad_hold_are_kept(self):
        self.assertTrue(self.band(matched(5, gap=0.21))[1].startswith("D5: its live fills ran 0.210"))
        self.assertEqual(self.band(matched(4, gap=0.21))[0], "probe")
        self.assertEqual(self.band(matched(5, gap=0.21), "candidate")[0], "candidate")
        losing = real_rows([-0.05] * 12)                        # real_bad, inside DM1's band at the forward sd? sd 0 -> 2.0
        fwd = M.forward_stats(losing, 0.8, version=1)
        self.assertTrue(fwd.real_bad)
        self.assertIsNone(M.live_demotion(self.t, "sized", fwd))
        band, why = self.band(losing, "sized")
        self.assertEqual(band, "probe")
        self.assertIn("held at Probe", why)

    def test_dm0_is_fast_lane_v2s_band_and_demotion_on_every_fixture(self):
        r = rollback_table()
        records = [
            [], real_rows([0.1] * 3), real_rows([-0.76] * 4), real_rows([-0.75] * 4), real_rows([-1.0] * 12),
            real_rows([-0.3] * 10), real_rows([0.2, -0.1] * 6), matched(5, gap=0.21), matched(10, gap=0.19),
            shadow_rows([-0.1] * 25), shadow_rows([0.3, 0.1, 0.2, -0.1, 0.25] * 5) + real_rows([0.15] * 6),
            shadow_rows([0.3, 0.1, 0.2, -0.1, 0.25] * 5) + real_rows([-0.2] * 11),
            real_rows([-0.76] * 4) + real_rows([2.0], day0=20, version=2),
        ]
        rows = [dict(row(band), **extra) for band in ("gym", "candidate", "probe", "sized")
                for extra in ({}, {"holdout_passed": False}, {"structure": "credit_vertical"},
                              {"typical_max_loss_usd": None}, {"typical_max_loss_usd": 900.0}, {"validation_r_sd": 0.2})]
        n = 0
        for rec, family_row, negative, sessions in itertools.product(records, rows, (None, True), (0, 3)):
            fwd = M.forward_stats(rec, 0.8, version=1, negative=negative)
            self.assertEqual(M.band_for(r, family_row, E, fwd, probe_sessions=sessions),
                             v2_band_for(r, family_row, E, fwd, probe_sessions=sessions), (rec, family_row, negative))
            self.assertEqual(M.demotion(fwd), v2_demotion(fwd))
            self.assertEqual(M.demotion(fwd, band=family_row["band"], rule="dm0", validation_r_sd=0.01), v2_demotion(fwd))
            self.assertEqual(M.live_demotion(r, family_row["band"], fwd, 0.01),
                             v2_demotion(fwd) if family_row["band"] in ("candidate", "probe") else None)
            n += 1
        self.assertGreater(n, 500)

    def test_an_unknown_rule_is_refused(self):
        with self.assertRaises(ValueError):
            M.demotion(M.forward_stats([], 0.8), rule="DM1")


# ================================================================================ L3: the sigma reader (families.py)
class TheSigmaReader(unittest.TestCase):
    def test_absent_garbage_and_valid(self):
        from league.live.families import validation_r_sd

        self.assertIsNone(validation_r_sd({}, 3))
        self.assertIsNone(validation_r_sd(None, 3))
        self.assertIsNone(validation_r_sd("junk", 3))
        self.assertEqual(validation_r_sd({"validation_r_sd_by_version": {"3": 1.7}}, 3), 1.7)
        self.assertEqual(validation_r_sd({"validation_r_sd_by_version": {"3": 2}}, 3), 2.0)
        self.assertEqual(validation_r_sd({"validation_version": 3, "validation_r_sd": 0.8}, 3), 0.8)
        self.assertIsNone(validation_r_sd({"validation_version": 4, "validation_r_sd": 0.8}, 3), "another version's")
        self.assertEqual(validation_r_sd({"validation_r_sd_by_version": {"3": 1.2}, "validation_version": 3,
                                          "validation_r_sd": 0.8}, 3), 1.2, "the version's own first")
        for garbage in (0, 0.0, -0.5, float("nan"), float("inf"), "1.2", True, None, [1.2], {"sd": 1.2}):
            self.assertIsNone(validation_r_sd({"validation_r_sd_by_version": {"3": garbage}}, 3), repr(garbage))
            self.assertIsNone(validation_r_sd({"validation_version": 3, "validation_r_sd": garbage}, 3), repr(garbage))
        self.assertIsNone(validation_r_sd({"validation_r_sd_by_version": ["3", 1.2]}, 3), "a map that is not a map")
        self.assertEqual(validation_r_sd({"validation_r_sd_by_version": [1], "validation_version": 3,
                                          "validation_r_sd": 0.9}, 3), 0.9)

    def test_the_swarm_families_row_carries_it_and_confirm_band_checks_it(self):
        from league.live.families import SwarmFamilies
        from league.swarm.store import SwarmStore
        from league.tests.evaluator_fakes import band_proof
        from league.tests.swarm_fakes import Clock as SwarmClock

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            store = SwarmStore(root, clock=SwarmClock())
            store.add_family({"id": "vert", "mechanism": "Calls after a quiet open.", "structure": "debit_vertical",
                              "roots": ["SPY"], "dte": [0, 2]}, origin="seed")
            store.add_version("vert", "# vert\nNEEDS = {}\n", {"k": 1}, author="seed")
            store.set_state("vert", banded_version=1, validation_version=1, validation_line={"passed": True},
                            typical_max_loss_usd=60.0, banded_evaluator=band_proof(store.version("vert", 1)))
            store.set_band("vert", "probe", reason="passed the holdout")
            store.close()
            families = SwarmFamilies(root)
            self.addCleanup(lambda: families._store.close() if families._store is not None else None)
            [first] = families.read()
            self.assertIn("validation_r_sd", first)
            self.assertIsNone(first["validation_r_sd"], "no writer yet (release D-1): absent")
            # The writer's keys (release D-1 writes them beside typical_max_loss_usd).
            families._db().set_state("vert", validation_r_sd_by_version={"1": 1.8})
            [row_] = families.read()
            self.assertEqual(row_["validation_r_sd"], 1.8)
            families._db().set_state("vert", validation_r_sd_by_version={"1": "garbage"})
            self.assertIsNone(families.read()[0]["validation_r_sd"])
            # confirm_band: the sigma the band was decided on must still be the state's.
            families._db().set_state("vert", validation_r_sd_by_version={"1": 1.8})
            [row_] = families.read()
            forward = families.forward_rows("vert")
            families._db().set_state("vert", validation_r_sd_by_version={"1": 0.4})
            self.assertFalse(families.confirm_band(row_, "probe", "unchanged", forward), "a changed sigma: not confirmed")
            [row_] = families.read()
            self.assertTrue(families.confirm_band(row_, "probe", "unchanged", forward))


# ======================================================================================== L3: the live path under DM1
@unittest.skipUnless(HAVE, "numpy not installed")
class DM1Live(LiveCase):
    def refusals(self):
        return [p["why"] for p, a in self.ledger.of("live.refusal")]

    def opens(self):
        return [b for b in self.venue.sent if b.get("legs") and b["legs"][0]["position_intent"] == "buy_to_open"]

    def test_a_negative_record_neither_moves_the_band_nor_refuses_the_open(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 3, "opens": 3})])
        self.families.add_forward("vert", "shadow", [dict(r, id=f"s{i}") for i, r in enumerate(shadow_rows([-0.1] * 25))])
        self.families.rows["vert"]["forward"] = {"trades": 25, "negative": True}
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "probe")
        self.assertEqual(live.instances["vert@1:r"].mode, "live")
        self.run_to(9, 40)
        self.assertGreaterEqual(len(self.opens()), 2, self.refusals())
        self.assertNotIn("its current forward evidence no longer qualifies for this real band", self.refusals())
        self.assertNotIn("its family or version is no longer eligible to open", self.refusals())

    def test_under_dm0_the_same_record_ends_the_band(self):
        from league.tests.money_fakes import rollback_table

        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 3, "opens": 3})], table=rollback_table())
        self.families.add_forward("vert", "shadow", [dict(r, id=f"s{i}") for i, r in enumerate(shadow_rows([-0.1] * 25))])
        self.families.rows["vert"]["forward"] = {"trades": 25, "negative": True}
        self.run_to(9, 33)
        self.assertEqual(self.families.rows["vert"]["band"], "candidate")
        self.assertEqual(self.opens(), [])
        del live

    def test_dm1_refuses_the_next_open_at_once_and_the_real_instance_goes_exit_only(self):
        fam = family("vert", VERTICAL, band="probe", params={"hold": 3, "opens": 3})
        fam["validation_r_sd"] = 0.5
        live = self.make([fam])
        self.run_to(9, 31)
        self.assertEqual(len(self.opens()), 1)
        self.assertEqual(live.instances["vert@1:r"].validation_r_sd, 0.5)
        # Ten real trades at -0.3: DM1's line at sigma 0.5 is -2.60 (D5's loss leg, -$120 against -$120, would not fire).
        self.families.add_forward("vert", "real", [dict(r, id=f"dm1-{i}") for i, r in enumerate(real_rows([-0.3] * 10))])
        self.run_to(9, 36)
        self.assertIn("its current forward evidence no longer qualifies for this real band", self.refusals())
        self.run_to(9, 38)
        self.assertEqual(self.families.rows["vert"]["band"], "candidate")
        [row_] = live.state.rows("SELECT mode FROM instances WHERE id='vert@1:r'")
        self.assertEqual(row_["mode"], "exit_only")
        moved = [p for p, a in self.ledger.of("live.band") if p.get("to") == "candidate"]
        self.assertTrue(moved and moved[0]["why"].startswith("DM1:"), moved)
        self.assertEqual(len(self.opens()), 1, "no real open after the demotion")


# ============================================================================================ L5: {"natural": k}
@unittest.skipUnless(HAVE, "numpy not installed")
class TheNaturalLimit(unittest.TestCase):
    def test_k_ticks_against_the_trader_on_the_signed_value(self):
        nl = L.limit_value
        self.assertEqual(nl({"natural": 3}, "open", 1.23, 1.10, 0.01), 1.26, "a debit open pays more")
        self.assertEqual(nl({"natural": 3}, "close", 1.23, 1.30, 0.01), 1.20, "a debit close takes in less")
        self.assertEqual(nl({"natural": 2}, "open", -1.00, -1.10, 0.01), -0.98, "a credit open takes in less")
        self.assertEqual(nl({"natural": 2}, "close", -0.50, -0.45, 0.01), -0.52, "a credit buy-back pays more")
        self.assertEqual(nl({"natural": 0}, "open", 1.23, 1.10, 0.01), 1.23)
        self.assertEqual(nl({"natural": 10}, "open", 2.95, 2.80, 0.05), 3.45)
        self.assertEqual(nl({"natural": 10}, "close", 0.05, 0.03, 0.01), -0.05, "as {'price': v}: no floor here")

    def test_k_is_a_whole_number_from_0_to_10(self):
        for k in (11, -1, 2.5, 2.0, True, False, "3", None, float("nan"), [2]):
            with self.assertRaises(L.Refused, msg=repr(k)) as caught:
                L.limit_value({"natural": k}, "open", 1.23, 1.10, 0.01)
            self.assertIn("{'natural': k} takes a whole number k from 0 to 10 ticks", str(caught.exception))
        with self.assertRaises(L.Refused) as caught:
            L.limit_value({"natural": 1, "price": 1.0}, "open", 1.23, 1.10, 0.01)
        self.assertIn("{'natural': k}", str(caught.exception), "the refusal lists the rule")
        self.assertEqual(L.NATURAL_MAX_TICKS, 10)

    def test_it_is_the_price_rule_with_v_from_the_natural(self):
        rng = random.Random(9)
        for _ in range(2000):
            tick = rng.choice([0.01, 0.05, 0.10])
            natural = round(rng.randrange(-300, 600) * tick, 6)
            mid = natural - rng.choice([1, -1]) * tick
            k = rng.randrange(0, 11)
            for action in ("open", "close"):
                v = natural + k * tick if action == "open" else natural - k * tick
                self.assertEqual(L.limit_value({"natural": k}, action, natural, mid, tick),
                                 L.limit_value({"price": v}, action, natural, mid, tick), (natural, tick, k, action))

    def chain(self, minute=700):
        spot = 450.0
        strikes = np.arange(440.0, 461.0)
        dte = np.zeros(strikes.size * 2, dtype=int)
        k = np.repeat(strikes, 2)
        call = np.tile([True, False], strikes.size)
        years = G.years_to_expiry(dte, minute)
        mid = G.bs_price(spot, k, years, 0.04, 0.25, call)
        bid = np.maximum(np.round(mid - 0.02, 2), 0.0)
        ask = np.round(mid + 0.02, 2) + 0.01
        return C.Snapshot("SPY", minute, spot, dte, k, call, bid, ask, np.full(k.size, 50), np.full(k.size, 50), rate=0.04)

    def test_open_and_close_resolve_as_the_price_rule_does(self):
        snap, rules = self.chain(), V.rules_for("SPY")
        legs = [{"side": "long", "right": "C", "dte": 0, "atm": 0}, {"side": "short", "right": "C", "rel": 0, "offset": 2.0}]
        base = {"open": "debit_vertical", "root": "SPY", "qty": 1, "legs": legs}
        nat = L.resolve_open(dict(base, limit={"natural": 4}), snap, rules, buying_power=1e9)
        self.assertAlmostEqual(nat.limit, round(nat.natural + 0.04, 2))
        price = L.resolve_open(dict(base, limit={"price": nat.natural + 0.04}), snap, rules, buying_power=1e9)
        self.assertEqual((nat.limit, nat.max_loss_share, nat.fees), (price.limit, price.max_loss_share, price.fees))
        condor = [{"side": "long", "right": "P", "rel": 1, "offset": -1.0}, {"side": "short", "right": "P", "dte": 0, "atm": -2},
                  {"side": "short", "right": "C", "dte": 0, "atm": 2}, {"side": "long", "right": "C", "rel": 2, "offset": 1.0}]
        credit = L.resolve_open({"open": "iron_condor", "root": "SPY", "qty": 1, "legs": condor, "limit": {"natural": 3}},
                                snap, rules, buying_power=1e9)
        self.assertLess(credit.natural, 0)
        self.assertAlmostEqual(credit.limit, round(credit.natural + 0.03, 2), msg="less credit taken in")
        self.assertAlmostEqual(credit.max_loss_share, 1.0 + credit.limit)
        close = L.resolve_close({"close": 1, "limit": {"natural": 2}}, nat.type, nat.legs, 1, snap, rules, position=1)
        self.assertAlmostEqual(close.limit, round(close.natural - 0.02, 2))
        again = L.resolve_close({"close": 1, "limit": {"price": close.natural - 0.02}}, nat.type, nat.legs, 1, snap, rules,
                                position=1)
        self.assertEqual(close.limit, again.limit)
        with self.assertRaises(L.Refused):
            L.resolve_open(dict(base, limit={"natural": 11}), snap, rules, buying_power=1e9)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheNaturalLimitLive(LiveCase):
    def test_the_real_order_path_prices_it_from_the_decision_minutes_natural(self):
        code = VERTICAL.replace('"limit": "natural", "tag": "t"', '"limit": {"natural": 2}, "tag": "t"')
        self.assertNotEqual(code, VERTICAL)
        live = self.make([family("vert", code, band="probe", params={"hold": 600})])
        self.run_to(9, 31)
        [order] = live.state.rows("SELECT limit_value, limit_price, placed_minute FROM orders WHERE action='open'")
        refusals = [p["why"] for p, a in self.ledger.of("live.refusal")]
        self.assertEqual(refusals, [])
        snap = live.day.snapshot("SPY", int(order["placed_minute"]))
        intent = {"open": "debit_vertical", "root": "SPY", "qty": 1, "limit": {"natural": 2},
                  "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0},
                           {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]}
        gym = L.resolve_open(intent, snap, live.day.rules["SPY"], buying_power=float("inf"))
        self.assertAlmostEqual(order["limit_value"], gym.limit)
        self.assertAlmostEqual(gym.limit, round(gym.natural + 0.02, 2))
        self.assertEqual(order["limit_price"], f"{gym.limit:.2f}")


if __name__ == "__main__":
    unittest.main()
