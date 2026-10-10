"""THE DIRECTION LANE's operator report and its walls (release D-1, Oct 9, 2026; league/ops/dlane_report.py; HARNESS 6.4
items 11 and 13, the plan's D8 and D9, the operator's decisions 8 and 9): the DONE meter of the pinned rule on fixture live
and swarm stores (what counts, the checkpoints, the per-program minimum, net after fees, consistency with replay), the
same-risk buy-and-hold, alarms A1-A9 and K5, the job's read-only run and its rollback (`dlane.mode` "off" writes
nothing), the fast lane rows' lane, and the agenda guard (the swarm's House warning and the operator's tool). Every
figure is invented."""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from league.live.state import LiveState
from league.ops import dlane_report as R
from league.ops import guard
from league.swarm import dlane
from league.swarm.store import SwarmStore, iso

NY = ZoneInfo("America/New_York")
GATE = {"dlane": {"mode": "gate"}}
#: The lane on with the per-close twins switched off (`forward.twins` null): A1.4's finality reads the nightly replay's
#: landing, as these tests were written (the integration of Oct 10, 2026; the twins' own finality is in test_close_twins).
NIGHTLY = {**GATE, "forward": {"twins": None}}
REPO = Path(__file__).resolve().parents[2]


def ny(day: str, hh: int = 10, mm: int = 0) -> float:
    d = dt.date.fromisoformat(day)
    return dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).timestamp()


def sessions_from(first: str, n: int) -> list[str]:
    from league.ops.direction import sessions

    start = dt.date.fromisoformat(first)
    return sessions(first, (start + dt.timedelta(days=3 * n + 10)).isoformat())[:n]


class Fixture(unittest.TestCase):
    """A state root with a swarm store and a live book, the clock at Tue Oct 20, 2026 16:00Z."""

    NOW = dt.datetime(2026, 10, 20, 16, 0, tzinfo=dt.timezone.utc).timestamp()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = self.NOW
        self.store = SwarmStore(self.root, clock=lambda: self.now)
        self.addCleanup(self.store.close)
        self.live = LiveState(self.root / "live.sqlite")
        self.addCleanup(self.live.close)
        self.pid = 0

    def fam(self, fid: str, *, lane: str = "alpha", band: str = "gym", roots: tuple = ("SPY",), **state) -> dict:
        spec = {"id": fid, "mechanism": "a mechanism sentence long enough for the store", "structure": "long_single",
                "roots": list(roots)}
        if lane == "direction":
            spec["lane"] = "direction"
        self.store.add_family(spec, origin="architect")
        if band != "gym":
            self.store.set_band(fid, band, reason="fixture")
        if state:
            self.store.set_state(fid, **state)
        return self.store.family(fid)

    def close(self, family: str, *, route: str = ":r", pnl: float = -10.0, max_loss: float = 50.0, version: int = 1,
              day: str = "2026-10-05", closed_at: float | None = None, status: str = "closed", probe: bool = False,
              root: str = "SPY", legs: list | None = None, entry: float = 0.5, qty: int = 0, fees: float = 0.13,
              opened: float | None = None) -> int:
        self.pid += 1
        opened = ny(day, 10, 0) if opened is None else opened
        self.live.upsert("positions", {
            "pid": self.pid, "instance": f"{family}@{version}{route}", "family": family, "type": "long_call", "root": root,
            "legs": json.dumps(legs or []), "qty": qty, "opened_qty": 1, "entry": entry, "max_loss_share": max_loss / 100.0,
            "collateral": 0.0, "fees": fees, "cash": pnl, "opened_at": opened, "opened_day": day, "opened_minute": 30,
            "status": status, "closed_at": None if status == "open" else
            closed_at if closed_at is not None else opened + 3 * 86400.0 + self.pid,
            "tuition": 1 if route in (":t", ":i") else 0,
            "info": json.dumps({"order": self.pid, **({"probe": True} if probe else {})})}, "pid")
        return self.pid

    def steady(self, first: str = "2026-09-30", last: str = "2026-10-19", *, skip: tuple = ()) -> None:
        """Research ran every UTC day from `first` to `last` but `skip` (DONE-RULE item 7): a birth, a Gym run and a
        Validation a day, the day's budget receipt at the ceiling and a stall receipt with nothing standing."""
        from league.ops.store import OpsStore

        if self.store.family("busy") is None:
            self.fam("busy")
        ops = OpsStore(self.root)
        self.addCleanup(ops.close)
        keep, d = self.now, dt.date.fromisoformat(first)
        while d <= dt.date.fromisoformat(last):
            if d.isoformat() not in skip:
                self.now = dt.datetime(d.year, d.month, d.day, 12, tzinfo=dt.timezone.utc).timestamp()
                self.store.event("swarm.born", "busy", {"lane": "alpha"})
                for window in ("train", "validation"):
                    self.store.add_run("busy", 1, {"run_id": f"{d}-{window}", "status": "ok", "trials": 1}, window=window,
                                       stress=1.0, purpose=window, prune=False)
                ops.record("budget", f"{d}T00:30:00Z", "ok", f"{d}T00:31:00Z",
                           summary={"meters": {"sail": {"limited_by": "ceiling"}, "claude": {"limited_by": "ceiling"}}})
                ops.record("stall", f"{d}T00:20:00Z", "ok", f"{d}T00:20:30Z", summary={"checks": {}})
            d += dt.timedelta(days=1)
        self.now = keep

    def posted(self, as_of: str = "2026-10-20T15:00:00Z", pids=None) -> None:
        """The broker's fees posted for `pids` (every position by default), the activity reading of `as_of`."""
        pids = range(1, self.pid + 1) if pids is None else pids
        (self.root / "publish.json").write_text(json.dumps({"activity": {"read_at": self.now - 60, "reading": {
            "as_of": as_of, "fees_by_pid": {str(p): "0.00" for p in pids}, "fees_usd": "0", "crypto_usd": "0",
            "interest_usd": "0", "misc_usd": "0", "unreconciled_usd": "0"}}}))

    def replays(self, fid: str, days, *, version: int = 1, pnl: float = 5.0, max_loss: float = 50.0) -> None:
        self.store.add_forward(fid, "nightly", [{"id": f"{fid}{i}", "day": d, "pnl": pnl, "max_loss": max_loss}
                                                for i, d in enumerate(days)], version=version)

    def report(self, settings=GATE, previous=None) -> dict:
        return R.report(self.root, settings=settings, now=self.now, previous=previous)


# ================================================================================================== the Done meter
class TheDoneMeter(Fixture):
    def test_it_counts_every_agent_close_on_the_three_routes_since_inception_and_never_the_houses(self):
        self.fam("dir-a", lane="direction")
        self.fam("alp-b")
        self.fam("tuition-before-d1")
        for _ in range(3):
            self.close("dir-a", route=":r", pnl=-10.0)
        self.close("alp-b", route=":t", pnl=4.0)
        self.close("alp-b", route=":t", pnl=6.0)
        self.close("alp-b", route=":i", pnl=-2.5)
        # An agent real close before D-1 (tuition, Oct 8, as the rule's one such close): counted in done_all.
        self.close("tuition-before-d1", route=":t", pnl=-150.0, version=27, day="2026-10-06",
                   closed_at=ny("2026-10-08", 15, 0))
        # Never counted: the House's calibration round trip and its live test, and an agent close before inception.
        self.close("house:calibration", route=":c", pnl=-1.0, version=0)
        self.close("house:rebound-live", route=":h", pnl=-1.0, version=0)
        self.close("alp-b", route=":r", pnl=99.0, day="2026-09-20", closed_at=ny("2026-09-24", 12))
        out = self.report()
        run_all, run_screen = out["done"]["all"]["running"], out["done"]["screen"]["running"]
        self.assertEqual((run_all["closes"], run_screen["closes"]), (7, 3))
        self.assertEqual(run_all["net_usd"], round(-30.0 + 4.0 + 6.0 - 2.5 - 150.0, 2))
        self.assertEqual(run_screen["net_usd"], -30.0)
        self.assertEqual(set(run_all["by_route"]), {":r", ":t", ":i"})
        self.assertEqual(run_all["by_route"][":t"]["closes"], 3)
        families = {c["family"] for c in out["done"]["all"]["closes"]}
        self.assertNotIn("house:calibration", families)
        self.assertNotIn("house:rebound-live", families)
        self.assertIn("tuition-before-d1", families)
        self.assertEqual(out["rule"]["sha256"], "0d007696c9a6a1cbbd7d2cc345811359ab1cec389cf88f75ceff295bbbc48dca")
        # DONE-RULE-A1 A1.2: the figure under the budget in force, said with its source: 2.7% at 12 weeks since THE
        # PROBE TOTAL AT $800 (PREREG-T, Oct 10, 2026, on fixed 2-, 3- and 5-session holds; 2.4% at 3-session holds
        # under L-D's $400 total before it).
        zero = out["done"]["p_done_zero_edge"]
        self.assertEqual((zero["value"], zero["label"], zero["horizon"], zero["holds"]),
                         (0.027, "P(Done | zero edge), simulation", "12 weeks",
                          "fixed 2-, 3- and 5-session holds (the simulation's stand-in for the House's pool)"))
        self.assertIn("A1.2", zero["source"])
        self.assertIn("PREREG-T", zero["source"])
        self.assertIn("$800 net in total", zero["variant"])
        self.assertTrue(zero["by"].startswith("PREREG-T"))
        self.assertNotIn("note", zero, "the figure for the rules this code ships")
        self.assertEqual(out["rule"]["amendment_sha256"], dlane.DONE["amendment_sha256"])
        self.assertIsNone(out["done"]["all"]["latest"], "no reading before the 30th close")
        self.assertEqual(out["done"]["all"]["next_checkpoint"], 30)
        # Every direction figure carries the label; the alpha program's does not.
        rows = {p["family"]: p for p in run_all["by_program"]}
        self.assertEqual(rows["dir-a"]["label"], dlane.LABEL)
        self.assertNotIn("label", rows["alp-b"])
        self.assertEqual(out["direction_net"]["net_usd"], -30.0)
        self.assertEqual(out["contamination"]["statement"], R.CONTAMINATION)

    def test_a_reading_is_made_only_at_a_checkpoint_over_its_first_k_closes(self):
        self.fam("dir-a", lane="direction")
        self.fam("dir-b", lane="direction")
        for i in range(15):
            self.close("dir-a", pnl=5.0)
            self.close("dir-b", pnl=5.0)
        self.replays("dir-a", ["2026-10-05"])
        self.replays("dir-b", ["2026-10-05"])
        self.steady()
        self.posted()
        for _ in range(4):
            self.close("dir-a", pnl=-100.0)           # closes 31-34: after the checkpoint
        out = self.report(settings=NIGHTLY)["done"]["screen"]
        self.assertEqual(len(out["checkpoints"]), 1)
        cp = out["checkpoints"][0]
        self.assertEqual((cp["at_close"], cp["closes"], cp["net_usd"], cp["holds"], cp["final"]), (30, 30, 150.0, True, True))
        self.assertEqual(cp["items"], {"3": True, "4": True, "7": True})
        self.assertEqual(cp["research_247"]["first_day"], "2026-10-02", "the first checkpoint reads its last 7 UTC days")
        self.assertTrue(out["holds"])
        self.assertEqual(out["running"]["net_usd"], -250.0)
        self.assertIsNone(out["running"]["holds"], "a running figure is never a reading")
        self.assertEqual(out["next_checkpoint"], 40)
        for _ in range(6):
            self.close("dir-b", pnl=-1.0)
        out = self.report()["done"]["screen"]
        self.assertEqual([c["at_close"] for c in out["checkpoints"]], [30, 40])
        self.assertFalse(out["checkpoints"][1]["holds"])
        self.assertIn("not above $0", out["checkpoints"][1]["why"])

    def test_the_bar_needs_five_closes_from_each_of_two_programs(self):
        self.fam("dir-a", lane="direction")
        self.fam("dir-b", lane="direction")
        for _ in range(26):
            self.close("dir-a", pnl=5.0)
        for _ in range(4):
            self.close("dir-b", pnl=5.0)
        cp = self.report()["done"]["screen"]["latest"]
        self.assertFalse(cp["holds"])
        self.assertEqual(cp["programs_with_min_closes"], 1)
        self.assertIn("programs with 5+ closes", cp["why"])

    def test_an_unpriced_close_makes_the_net_unknown_never_zero(self):
        self.fam("dir-a", lane="direction")
        self.close("dir-a", pnl=5.0)
        self.close("dir-a", pnl=0.0, status="unpriced_close", qty=1)
        run = self.report()["done"]["all"]["running"]
        self.assertEqual((run["closes"], run["unpriced"], run["net_known"], run["net_usd"]), (2, 1, False, None))
        self.assertIn("could not price", run["why"])

    def test_consistency_binds_programs_with_five_matched_closes_and_lists_the_rest(self):
        self.fam("dir-a", lane="direction")
        self.fam("dir-b", lane="direction")
        self.fam("dir-c", lane="direction")
        days = sessions_from("2026-10-01", 12)
        for i, day in enumerate(days[:10]):
            self.close("dir-a", pnl=5.0, max_loss=50.0, day=day)
            self.close("dir-b", pnl=-25.0, max_loss=50.0, day=day)
            if i < 3:
                self.close("dir-c", pnl=5.0, day=day)
        # Nightly replays: dir-a's matches its live fills; dir-b's replay made money where live lost half a max loss;
        # dir-c's replay covers 3 of its closes only.
        self.store.add_forward("dir-a", "nightly", [{"id": f"a{i}", "day": d, "pnl": 5.0, "max_loss": 50.0}
                                                    for i, d in enumerate(days[:10])], version=1)
        self.store.add_forward("dir-b", "nightly", [{"id": f"b{i}", "day": d, "pnl": 5.0, "max_loss": 50.0}
                                                    for i, d in enumerate(days[:10])], version=1)
        self.store.add_forward("dir-c", "nightly", [{"id": f"c{i}", "day": d, "pnl": 5.0, "max_loss": 50.0}
                                                    for i, d in enumerate(days[:3])], version=1)
        out = self.report()["done"]["screen"]
        rows = {p["family"]: p["replay"] for p in out["running"]["by_program"]}
        self.assertEqual(rows["dir-a"], {"matched": 10, "gap": 0.0, "consistent": True})
        self.assertEqual(rows["dir-b"]["consistent"], False)
        self.assertAlmostEqual(rows["dir-b"]["gap"], -0.6)
        self.assertEqual((rows["dir-c"]["matched"], rows["dir-c"]["consistent"]), (3, None), "listed, never dropped")
        self.assertIsNone(out["latest"], "23 closes: no checkpoint yet")
        # Seven more closes of dir-a take the screen to 30: dir-b's inconsistency fails the reading.
        for day in days[:7]:
            self.close("dir-a", pnl=5.0, max_loss=50.0, day=day, version=2)
        cp = self.report()["done"]["screen"]["latest"]
        self.assertEqual(cp["at_close"], 30)
        self.assertFalse(cp["consistent_ok"])
        self.assertIn("inconsistent with replay: dir-b", cp["why"])

    def test_the_brokers_posted_fees_replace_the_estimate(self):
        self.fam("dir-a", lane="direction")
        first = self.close("dir-a", pnl=-10.0)
        self.close("dir-a", pnl=-10.0)
        (self.root / "publish.json").write_text(json.dumps({"activity": {
            "read_at": self.now - 60, "start_at": "x",
            "reading": {"as_of": "2026-10-20T15:00:00Z", "fees_by_pid": {str(first): "0.04"}, "fees_usd": "-0.10",
                        "crypto_usd": "0", "interest_usd": "0.02", "misc_usd": "0", "unreconciled_usd": "0"}}}))
        out = self.report()["done"]["all"]
        rows = {c["pid"]: c for c in out["closes"]}
        self.assertEqual((rows[first]["pnl_usd"], rows[first]["fee_basis"]), (-9.96, "broker"))
        self.assertEqual(rows[first + 1]["fee_basis"], "estimate")
        self.assertEqual(out["running"]["estimate_closes"], 1)

    def test_a_close_on_a_route_the_rule_does_not_name_is_listed_apart(self):
        self.fam("alp-b")
        self.close("alp-b", route=":q", pnl=-3.0)
        out = self.report()["done"]
        self.assertEqual(out["all"]["running"]["closes"], 0)
        self.assertEqual([r["route"] for r in out["other_routes"]], ["agent_other"])


# ================================================================================================== buy-and-hold
class TheSameRiskBuyAndHold(unittest.TestCase):
    def call(self, strike: float, side: int = 1) -> dict:
        return {"symbol": "X", "side": side, "ratio": 1, "is_call": True, "strike": strike, "expiry": "2026-11-20", "key": 0}

    def test_the_entry_delta_is_black_scholes_at_the_volatility_that_prices_the_entry(self):
        from league.options_history import bs_delta, bs_price, years_to

        at = ny("2026-10-21", 10)
        years = years_to("2026-11-20", at)
        entry = bs_price(500.0, 505.0, years, 0.18, "call")
        delta = R.entry_delta({"legs": [self.call(505.0)], "entry": entry, "opened_at": at}, 500.0)
        self.assertAlmostEqual(delta, bs_delta(500.0, 505.0, years, 0.18, "call"), places=4)
        vertical = bs_price(500.0, 500.0, years, 0.2, "call") - bs_price(500.0, 510.0, years, 0.2, "call")
        delta = R.entry_delta({"legs": [self.call(500.0), self.call(510.0, -1)], "entry": vertical, "opened_at": at}, 500.0)
        want = bs_delta(500.0, 500.0, years, 0.2, "call") - bs_delta(500.0, 510.0, years, 0.2, "call")
        self.assertAlmostEqual(delta, want, places=4)
        self.assertIsNone(R.entry_delta({"legs": [self.call(505.0)], "entry": 400.0, "opened_at": at}, 500.0),
                          "no volatility prices it: unknown, never a guess")

    def test_both_ways_over_the_same_closes(self):
        from league.options_history import bs_price, years_to

        at = ny("2026-10-05", 10)
        entry = bs_price(500.0, 505.0, years_to("2026-11-20", at), 0.18, "call")
        doc = {"SPY": {"2026-10-02": 495.0, "2026-10-05": 500.0, "2026-10-08": 510.0}}
        close = {"root": "SPY", "opened_day": "2026-10-05", "day": "2026-10-08", "max_loss_usd": 100.0, "opened_qty": 1,
                 "legs": [self.call(505.0)], "entry": entry, "opened_at": at}
        bh = R.buy_and_hold(close, doc)
        self.assertEqual(bh["risk_usd"], 2.0)                          # $100 held from 500 to 510
        delta = R.entry_delta(close, 500.0)
        self.assertAlmostEqual(bh["delta_usd"], round(delta * 100.0 * 10.0, 2), places=2)
        xsp = R.buy_and_hold({**close, "root": "XSP"}, doc)
        self.assertEqual((xsp["risk_usd"], xsp["delta_usd"]), (2.0, None))
        self.assertIn("no stock bars", xsp["why"])
        none = R.buy_and_hold(close, {})
        self.assertEqual((none["risk_usd"], none["delta_usd"]), (None, None))


# ================================================================================================== the alarms
class TheAlarms(Fixture):
    def alarms(self, *, settings=GATE, closes=(), envelope=None, done=None, k5=None, unit=None, previous=None,
               book=None) -> dict:
        lanes = R.Lanes(self.store)
        out = R.alarms(self.store, settings, lanes, book or {"positions": [], "instances": []}, list(closes),
                       envelope or {"basis_in_force": "gross", "room_gross_units": 3.0},
                       done or {"all": {"checkpoints": []}, "screen": {"checkpoints": []}}, k5 or {"tripped": False},
                       unit or {"cap_usd": 128.9}, previous, now=self.now, today="2026-10-20")
        return {a["id"]: a for a in out}

    def test_a_quiet_lane_raises_nothing(self):
        self.fam("alp-a")
        self.assertEqual(self.alarms(), {})

    def test_a1_no_direction_birth_in_twelve_hours(self):
        self.store.put(dlane.STARTED_KEY, iso(self.now - 13 * 3600))
        self.assertIn("A1", self.alarms())
        self.fam("dir-a", lane="direction")
        self.store.event("swarm.born", "dir-a", {"lane": "direction"})   # now: inside the window
        self.assertNotIn("A1", self.alarms())

    def cleared(self, fid: str, hours: float, n: int = 1, **fam) -> None:
        self.fam(fid, lane="direction", **fam)
        self.store.set_state(fid, **{dlane.STATE_KEY: {"objective": dlane.OBJECTIVE, "versions": {str(n): {
            "at": iso(self.now - hours * 3600), "train": {"eligible": True, "fails": []},
            "robust": {"known": True, "passed": True, "fails": []}}}}})

    def test_a2_a_cleared_direction_best_and_no_validation_or_look_for_a_day(self):
        self.cleared("dir-a", 25)
        self.assertIn("A2", self.alarms())
        self.store.add_look("dir-a", 1, "sha-1", passed=False, p_value=0.5, detail={})
        self.assertNotIn("A2", self.alarms())

    def test_a3_a_cleared_best_waits_for_validation_and_a_pass_waits_for_its_look(self):
        self.cleared("dir-a", 7)
        self.store.update_family("dir-a", best_version=1)
        a = self.alarms()["A3"]
        self.assertEqual((a["validation"], a["gate"]), (["dir-a"], []))
        self.fam("dir-b", lane="direction", validation_verdicts={"2": {"passed": True, "at": iso(self.now - 13 * 3600)}})
        self.assertEqual(self.alarms()["A3"]["gate"], ["dir-b"])
        self.store.add_look("dir-b", 2, "sha-2", passed=True, p_value=0.1, detail={})
        self.assertEqual(self.alarms()["A3"]["gate"], [])

    def test_a4_no_room_while_a_direction_probe_has_under_five_real_closes(self):
        self.fam("dir-a", lane="direction", band="probe")
        tight = {"basis_in_force": "gross", "room_gross_units": 0.6}
        self.assertIn("A4", self.alarms(envelope=tight))
        closes = [{"family": "dir-a", "code": ":r"}] * 5
        self.assertNotIn("A4", self.alarms(envelope=tight, closes=closes))
        self.assertNotIn("A4", self.alarms(envelope={"basis_in_force": "gross", "room_gross_units": 1.2}))

    def test_a5_live_fills_below_replay_over_five_matched_closes(self):
        self.fam("dir-a", lane="direction", band="probe", banded_version=1)
        days = sessions_from("2026-10-01", 6)
        self.store.add_forward("dir-a", "real", [{"id": f"real:{i}", "day": d, "pnl": -5.0, "max_loss": 50.0}
                                                 for i, d in enumerate(days)], version=1)
        self.store.add_forward("dir-a", "nightly", [{"id": f"n{i}", "day": d, "pnl": 2.0, "max_loss": 50.0}
                                                    for i, d in enumerate(days)], version=1)
        self.assertEqual(self.alarms()["A5"]["families"], ["dir-a"])     # gap 0.14 > 0.10 (D5 acts at 0.20)

    def test_a6_under_one_eligible_version_per_fifty_direction_births(self):
        self.fam("dir-a", lane="direction")
        for _ in range(49):
            self.store.event("swarm.born", "dir-a", {"lane": "direction"})
        self.assertNotIn("A6", self.alarms(), "under 50 births the ratio is not judged")
        self.store.event("swarm.born", "dir-a", {"lane": "direction"})
        self.assertIn("A6", self.alarms())
        self.cleared("dir-b", 1)
        self.assertNotIn("A6", self.alarms())

    def test_a7_most_versions_that_clear_the_years_fail_the_unit(self):
        self.fam("dir-a", lane="direction")
        self.store.set_state("dir-a", **{dlane.STATE_KEY: {"objective": dlane.OBJECTIVE, "versions": {
            str(n): {"at": iso(self.now - 3600), "train": {"eligible": False, "fails": ["E5"],
                                                         "unit": {"scaled_usd": 140.0 + n}}} for n in (1, 2, 3)}}})
        a = self.alarms()["A7"]
        self.assertEqual((a["cap_usd"], a["median_failing_usd"]), (128.9, 142.0))
        self.assertIn("$128.90", a["text"])

    def test_a8_a_holding_checkpoint_is_said_once(self):
        items = {"3": True, "4": True, "7": True}
        done = {"all": {"checkpoints": [{"at_close": 30, "holds": True, "final": True, "items": items,
                                         "measured_programs": 2}]}, "screen": {"checkpoints": []}}
        a = self.alarms(done=done)["A8"]
        self.assertEqual((a["level"], a["meter"], a["at_close"]), ("info", "done_all", 30))
        self.assertIn("FINAL checkpoint of close 30 (item 3, item 4, item 7", a["text"])
        self.assertNotIn("A8", self.alarms(done=done, previous={"done": done}))
        # DONE-RULE-A1 A1.4: a provisional holding reading raises nothing; it is said once it is final, even if an earlier
        # report saw it holding provisionally.
        provisional = {"all": {"checkpoints": [{"at_close": 30, "holds": True, "final": False, "items": items}]},
                       "screen": {"checkpoints": []}}
        self.assertNotIn("A8", self.alarms(done=provisional))
        self.assertIn("A8", self.alarms(done=done, previous={"done": provisional}))

    def test_a9_every_live_direction_program_flat_for_ten_sessions(self):
        self.fam("dir-a", lane="direction")
        book = {"instances": [{"id": "dir-a@1:i", "family": "dir-a", "created_at": ny("2026-09-28"), "retired_at": None}],
                "positions": [{"family": "dir-a", "opened_day": "2026-10-01"}]}
        self.assertEqual(self.alarms(book=book)["A9"]["level"], "info")
        book["positions"].append({"family": "dir-a", "opened_day": "2026-10-19"})
        self.assertNotIn("A9", self.alarms(book=book))

    def test_k5_is_an_alarm_while_it_holds(self):
        self.assertIn("K5", self.alarms(k5={"tripped": True}))


# ================================================================================================== the job
class TheJob(Fixture):
    def ctx(self):
        self.alerts: list[tuple[str, str]] = []
        return SimpleNamespace(root=self.root, now=lambda: self.now, config={},
                               alert=lambda level, text: self.alerts.append((level, text)))

    def gate(self, **extra) -> None:
        (self.root / "swarm.json").write_text(json.dumps({"dlane": {"mode": "gate", **extra}}))

    def test_with_the_lane_off_it_writes_nothing(self):
        out = R.run(self.ctx())
        self.assertEqual(out["status"], "skipped")
        self.assertFalse((self.root / R.FILE).exists())

    def test_it_writes_the_report_read_only_and_keeps_e0(self):
        self.gate()
        self.fam("dir-a", lane="direction")
        self.close("dir-a", pnl=-10.0)
        (self.root / "health.json").write_text(json.dumps({"options_live": {"stops": {
            "sod_equity": "1289.34", "last_reading": [self.now - 600, "1280.00", "2026-10-20"]}}}))
        out = R.run(self.ctx())
        self.assertTrue(out["ok"])
        doc = json.loads((self.root / R.FILE).read_text())
        self.assertEqual((doc["operator_only"], doc["lane"]["mode"], doc["lane"]["mode_effective"]), (True, "gate", "gate"))
        self.assertEqual(doc["account"]["e0"]["usd"], 1280.0)
        self.assertEqual(doc["unit"]["cap_usd"], 128.0)
        self.assertEqual(len(doc["loosened"]), len(R.LOOSENED))
        self.assertEqual(set(doc["funnel"]), {"24h", "7d"})
        self.assertEqual(doc["funnel"]["7d"]["direction"]["real_closes"][":r"], 0, "closed 12 days ago")
        # E0 is the first reading the report saw: the next day's report keeps it.
        (self.root / "health.json").write_text(json.dumps({"options_live": {"stops": {
            "sod_equity": "1300.00", "last_reading": [self.now + 86000, "1300.00", "2026-10-21"]}}}))
        self.now += 86400
        R.run(self.ctx())
        doc = json.loads((self.root / R.FILE).read_text())
        self.assertEqual((doc["account"]["e0"]["usd"], doc["account"]["change_usd"]), (1280.0, 20.0))

    def test_the_report_opens_nothing_writable(self):
        self.gate()
        self.fam("dir-a", lane="direction")
        self.close("dir-a", pnl=-10.0)
        with guard.readonly():               # a writable SQLite open inside raises
            out = R.report(self.root, settings=GATE, now=self.now)
        self.assertEqual(out["done"]["all"]["running"]["closes"], 1)

    def test_k5_trips_once_at_the_line_and_holds_until_the_operator_clears_it(self):
        self.gate()
        self.fam("dir-a", lane="direction")
        self.fam("alp-b")
        self.close("alp-b", route=":t", pnl=-900.0)      # an alpha loss never counts toward the lane's K5
        self.close("dir-a", route=":i", pnl=-300.0)
        self.close("dir-a", route=":r", pnl=-299.0)
        out = R.run(self.ctx())
        self.assertFalse(out["k5_tripped"], "-$599 is above the line")
        self.assertIsNone(self.store.get(dlane.K5_KEY))
        self.close("dir-a", route=":t", pnl=-1.0)
        out = R.run(self.ctx())
        self.assertEqual((out["k5_tripped"], out["k5_new"]), (True, True))
        self.assertEqual(self.store.get(dlane.K5_KEY)["net"], -600.0)
        self.assertEqual(dlane.mode_effective(self.store, GATE), "shadow")
        self.assertTrue(any("K5 tripped" in text for _, text in self.alerts))
        out = R.run(self.ctx())
        self.assertEqual((out["k5_tripped"], out["k5_new"]), (True, False), "written once")
        self.gate(k5_clear=True)
        self.assertEqual(dlane.mode_effective(self.store, {"dlane": {"mode": "gate", "k5_clear": True}}), "gate")

    def test_an_unnamed_route_is_a_warning(self):
        self.gate()
        self.fam("alp-b")
        self.close("alp-b", route=":q", pnl=-3.0)
        R.run(self.ctx())
        self.assertTrue(any("a route the Done rule does not name" in text for _, text in self.alerts))


# ================================================================================================== DONE-RULE-A1 (Oct 10)
class TheAmendment(Fixture):
    """DONE-RULE-A1 (pinned Oct 9, 2026, sha 333bad06) and the readiness audit's B1, M7, M8 and M9, read by the meter:
    consistency must be measured (A1.1), item 7 is read per UTC day, a reading is FINAL only on landed replays and posted
    fees and is then frozen (A1.4), and Net after costs rides beside the meter."""

    def thirty(self, *, replay=("dir-a", "dir-b")) -> None:
        self.fam("dir-a", lane="direction")
        self.fam("dir-b", lane="direction")
        for _ in range(15):
            self.close("dir-a", pnl=5.0)
            self.close("dir-b", pnl=5.0)
        for fid in replay:
            self.replays(fid, ["2026-10-05"])
        self.steady()
        self.posted()

    def test_zero_replay_evidence_never_passes(self):
        self.thirty(replay=())
        cp = self.report()["done"]["screen"]["latest"]
        self.assertFalse(cp["holds"], "B1's local repro: 30 closes, 2 programs, no replay row held before A1.1")
        self.assertEqual(cp["items"], {"3": True, "4": False, "7": True})
        self.assertIn("replay untested: 0 of 30 closes matched a replay (a twin or the nightly); 0 programs with 5+ matched "
                      "closes of the 2 needed (DONE-RULE-A1 A1.1)", cp["why"])
        self.assertEqual(cp["replay_coverage"], {"matched": 0, "closes": 30, "share": 0.0})
        self.assertEqual([(p["family"], p["closes"], p["matched"], p["gap"]) for p in cp["by_program"]],
                         [("dir-a", 15, 0, None), ("dir-b", 15, 0, None)], "every program listed, never dropped")
        self.assertEqual(self.report()["done"]["screen"]["gap_measure"], R.GAP_MEASURE)

    def test_one_measured_program_is_not_enough(self):
        self.thirty(replay=("dir-a",))
        cp = self.report()["done"]["screen"]["latest"]
        self.assertFalse(cp["holds"])
        self.assertEqual(cp["measured_programs"], 1)
        self.assertIn("1 programs with 5+ matched closes of the 2 needed", cp["why"])
        self.replays("dir-b", ["2026-10-05"])
        self.assertTrue(self.report()["done"]["screen"]["latest"]["holds"])

    def test_research_247_needs_every_day_at_budget_with_no_owner_step_waiting(self):
        from league.ops.store import OpsStore

        self.steady("2026-10-01", "2026-10-07", skip=("2026-10-04",))
        research = R.Research247(self.store, self.root)
        out = research("2026-10-01", "2026-10-07")
        self.assertFalse(out["holds"])
        self.assertEqual(out["why"], "2026-10-04: no births; no Gym runs; no Validations; no budget receipt; no stall receipt")
        self.assertTrue(research("2026-10-05", "2026-10-07")["holds"])
        ops = OpsStore(self.root)
        self.addCleanup(ops.close)
        # A Done checkpoint told at once is news, never an owner step waiting; a top-up asked for is one.
        ops.record("stall", "2026-10-05T10:20:00Z", "ok", "2026-10-05T10:20:30Z", summary={"checks": {
            "done": {"stalled": True, "owner_step": "Done holds: read the claim"}, "births": {"stalled": True, "owner_step": None}}})
        ops.record("stall", "2026-10-06T10:20:00Z", "ok", "2026-10-06T10:20:30Z", summary={"checks": {
            "runway_sail": {"stalled": True, "owner_step": "top up Sail"}}})
        # The budget tapered on the 7th: research under the ceiling.
        ops.record("budget", "2026-10-07T20:10:00Z", "ok", "2026-10-07T20:10:30Z",
                   summary={"meters": {"sail": {"limited_by": "runway"}, "claude": {"limited_by": "ceiling"}}})
        for name in ("swarm.json.before-set-20261006T120000Z", "budget.json.before-sailraise-20261005T143356Z",
                     "swarm.json.before-set-20260920T000000Z", "swarm.json.before-train2020"):
            (self.root / name).write_text("{}")
        out = R.Research247(self.store, self.root)("2026-10-05", "2026-10-07")
        days = {d["day"]: d for d in out["days"]}
        self.assertTrue(days["2026-10-05"]["holds"], "the done cause is news")
        self.assertEqual(days["2026-10-06"]["why"], "an owner step waiting (runway_sail)")
        self.assertEqual(days["2026-10-07"]["why"], "research under the ceiling (runway)")
        self.assertEqual((days["2026-10-05"]["births"], days["2026-10-05"]["gym_runs"], days["2026-10-05"]["validations"]),
                         (1, 2, 1))
        self.assertEqual(out["edits"], [
            {"file": "budget.json", "what": "sailraise", "at": "2026-10-05T14:33:56Z"},
            {"file": "swarm.json", "what": "set", "at": "2026-10-06T12:00:00Z"}], "listed beside it, never a bar")
        self.assertEqual(out["edits_count"], 2)
        self.assertEqual(R.NEWS_CAUSES, ("done",))

    def test_a_day_no_stall_receipt_read_is_not_a_day_with_no_owner_step_waiting(self):
        """The review of the weekend fixes (Oct 10, 2026): the stall job failing all day (an unreadable swarm store) or
        missed left `owner` empty, so the day held on no evidence; the budget leg already failed a day with no receipt."""
        from league.ops.store import OpsStore

        self.steady("2026-10-05", "2026-10-07")
        ops = OpsStore(self.root)
        self.addCleanup(ops.close)
        ops.db.execute("DELETE FROM runs WHERE job='stall' AND due_at LIKE '2026-10-06%'")
        # A failed stall run is no reading either: only a receipt the job finished counts.
        ops.record("stall", "2026-10-06T10:20:00Z", "failed", "2026-10-06T10:20:30Z", error="OperationalError: locked")
        out = R.Research247(self.store, self.root)("2026-10-05", "2026-10-07")
        days = {d["day"]: d for d in out["days"]}
        self.assertEqual((days["2026-10-06"]["holds"], days["2026-10-06"]["why"]), (False, "no stall receipt"))
        self.assertEqual((days["2026-10-06"]["at_budget"], days["2026-10-06"]["stall_receipts"]), (True, 0))
        self.assertTrue(days["2026-10-05"]["holds"] and days["2026-10-07"]["holds"])
        self.assertEqual(out["why"], "2026-10-06: no stall receipt")

    def test_a_reading_is_final_only_on_landed_replays_and_posted_fees_and_then_frozen(self):
        self.thirty()
        # dir-a is at Probe: its nightly replay has replayed only to the 7th, the closes exit on the 8th.
        self.store.set_band("dir-a", "probe", reason="fixture")
        self.store.set_state("dir-a", forward_replay={"target": {"day": "2026-10-07"}, "version": 1})
        out = self.report(settings=NIGHTLY)
        cp, meter = out["done"]["screen"]["latest"], out["done"]["screen"]
        self.assertEqual((cp["holds"], cp["final"], meter["holds"], meter["provisional"]), (True, False, False, True))
        self.assertIn("the nightly replay has not yet replayed the exit day of 15 closes", cp["final_why"])
        self.assertNotIn("A8", [a["id"] for a in out["alarms"]], "never on a provisional reading")
        self.store.set_state("dir-a", forward_replay={"target": {"day": "2026-10-08"}, "version": 1})
        self.posted(as_of="2026-10-08T21:00:00Z")
        self.assertIn("broker's fees have not posted for 30 closes",
                      self.report(settings=NIGHTLY)["done"]["screen"]["latest"]["final_why"],
                      "fees post the session after the exit: a reading of the exit day is not final")
        self.posted()
        final = self.report(settings=NIGHTLY, previous=out)
        self.assertTrue(final["done"]["screen"]["holds"])
        self.assertEqual([a["id"] for a in final["alarms"] if a["id"] == "A8"], ["A8", "A8"], "done_all and done_screen")
        # Frozen: the nightly rows are replaced each night; a final reading does not flip after A8.
        self.store.replace_forward("dir-b", "nightly", [], version=1)
        later = self.report(settings=NIGHTLY, previous=final)
        cp = later["done"]["screen"]["latest"]
        self.assertEqual((cp["holds"], cp["final"], cp.get("frozen")), (True, True, True))
        self.assertEqual(later["done"]["screen"]["running"]["consistent_ok"], False, "the running figure reads it now")
        self.assertNotIn("A8", [a["id"] for a in later["alarms"]])
        # The stall job's `done` cause reads the frozen final reading, not the once-said A8 (the review of the weekend
        # fixes, Oct 10, 2026): the later report still carries the claim for a notice that has not been sent.
        from league.ops import stall as ST

        (self.root / R.FILE).write_text(json.dumps(later, default=str))
        self.assertEqual(ST.dlane_facts(self.root)["done_final"],
                         [{"meter": "done_all", "at_close": 30}, {"meter": "done_screen", "at_close": 30}])

    def test_finality_reads_each_close(self):
        rows = [{"family": "f", "day": "2026-10-08", "pnl_usd": Decimal("1"), "fee_basis": "broker"}]
        self.assertTrue(R.finality(rows, replay_days={"f": {"replayed": True, "day": "2026-10-08"}},
                                   fees_as_of="2026-10-09")["final"])
        self.assertFalse(R.finality(rows, replay_days={"f": {"replayed": True, "day": None}}, fees_as_of="2026-10-09")["final"])
        self.assertTrue(R.finality(rows, replay_days={}, fees_as_of="2026-10-09")["final"],
                        "a program no longer replayed: its rows are frozen, they cannot change")
        unpriced = R.finality([{**rows[0], "pnl_usd": None}], replay_days={}, fees_as_of="2026-10-09")
        self.assertEqual((unpriced["final"], unpriced["unpriced"]), (False, 1))

    def test_net_after_costs_is_the_meter_less_every_cost_over_the_same_days(self):
        self.fam("dir-a", lane="direction")
        self.close("dir-a", pnl=-10.0)
        self.close("dir-a", route=":t", pnl=4.0)
        self.close("dir-a", pnl=99.0, day="2026-10-19", closed_at=ny("2026-10-20", 11))   # after the cutoff
        self.assertIn("no close economics summary", self.report()["done"]["net_after_costs"]["why"])
        folder = self.root / "economics" / "20261019-close"
        folder.mkdir(parents=True)
        (folder / "summary.json").write_text(json.dumps({
            "cutoff": "2026-10-19T20:00:00Z", "cost_start": "2026-09-26T06:23:14Z", "total_costs_usd": "700.00",
            "costs": [{"service": "Sail (models + boxes)", "usd": "400.00", "basis": "x"},
                      {"service": "Claude (Anthropic via the gateway)", "usd": "300.00", "basis": "y"}],
            "net": {"net_usd": "-760.00"}, "realized": {"realized_options_pnl_usd": "-60.00"}}))
        out = self.report()
        n = out["done"]["net_after_costs"]
        self.assertEqual((n["cutoff"], n["costs_usd"], n["economics_net_usd"], n["stale"]),
                         ("2026-10-19T20:00:00Z", 700.0, "-760.00", False))
        self.assertEqual(n["done_all"], {"closes_to_cutoff": 2, "net_usd_to_cutoff": -6.0, "net_after_costs_usd": -706.0})
        self.assertEqual(n["done_screen"]["net_after_costs_usd"], -710.0)
        self.assertEqual([c["service"] for c in n["costs_by_service"]], ["Sail (models + boxes)",
                                                                         "Claude (Anthropic via the gateway)"])
        self.assertIn("comparison only", out["costs"]["basis"])

    def test_dm1s_first_firing_rides_beside_the_probe_row(self):
        self.fam("eqp-real", lane="direction", band="probe", banded_version=17,
                 validation_r_sd_by_version={"17": 2.458545})
        self.close("eqp-real", version=17, status="open", qty=1, entry=0.43, max_loss=43.0, fees=0.05, probe=True,
                   day="2026-10-19")
        row = next(p for p in self.report()["probes"] if p["family"] == "eqp-real")
        dm1 = row["dm1"]
        self.assertEqual((dm1["first_fire_at"], dm1["trades_to_first_fire"], dm1["real_trades"], dm1["sigma"]),
                         (17, 17, 0, 2.458545), "the audit's n >= 17 at the live sigma")
        self.assertAlmostEqual(dm1["r_floor"], 43.05 / 43.0, places=5)
        self.assertEqual((row["probe_net_usd"], row["probe_closes"], row["program_loss_line_usd"]), (0.0, 0, -300.0))
        self.store.set_state("eqp-real", validation_r_sd_by_version={})
        self.assertEqual(R.dm1_reach(self.store, self.store.family("eqp-real"), [])["first_fire_at"], 11,
                         "DM1's fallback sigma 2.0: (1.645 x 2)^2 = 10.8")

    def test_a_zero_edge_figure_the_amendment_did_not_pin_says_so(self):
        """A figure this code does not name is a setting's; it attributes neither 0.024 nor 0.027 to the wrong rule (the
        review of THE PROBE TOTAL AT $800, Oct 10, 2026: A1.2 pinned 0.024; PREREG-T measured 0.027)."""
        out = R.zero_edge({"dlane": {"mode": "gate", "done_zero_edge_p": 0.13}})
        self.assertEqual(out["value"], 0.13)
        self.assertIn("not one this code names", out["note"])
        self.assertIn("0.024: DONE-RULE-A1 A1.2, under L-D's $400 total", out["note"])
        self.assertIn("0.027: PREREG-T", out["note"])
        self.assertNotIn("pinned 0.027", out["note"])
        self.assertNotIn("horizon", out)

    def test_both_named_zero_edge_figures_keep_their_own_labels_and_the_rollback_reads_l_ds(self):
        """0.024 is A1.2's figure with its own horizon, holds and source whatever the code ships; a setting that picks it
        beside the $800 rules says so; THE ROLLBACK (`ZERO_EDGE = ZERO_EDGES[0.024]`, 0.024 in DEFAULTS and policy.json)
        reports it as the pinned figure with no note."""
        from unittest import mock

        self.assertEqual(sorted(dlane.ZERO_EDGES), [0.024, 0.027])
        self.assertTrue(all(z["value"] == v for v, z in dlane.ZERO_EDGES.items()))
        self.assertIs(dlane.ZERO_EDGE, dlane.ZERO_EDGES[dlane.DEFAULTS["done_zero_edge_p"]])
        ld = R.zero_edge({"dlane": {"mode": "gate", "done_zero_edge_p": 0.024}})
        self.assertEqual((ld["value"], ld["holds"], ld["by"]),
                         (0.024, "3-session holds", "DONE-RULE-A1 A1.2, under L-D's $400 total"))
        self.assertIn("pinned by DONE-RULE-A1 A1.2", ld["source"])
        self.assertIn("the rules this code ships carry 0.027", ld["note"])
        with mock.patch.object(dlane, "ZERO_EDGE", dlane.ZERO_EDGES[0.024]), \
                mock.patch.dict(dlane.DEFAULTS, {"done_zero_edge_p": 0.024}):
            rolled = R.zero_edge({"dlane": {"mode": "gate"}})
        self.assertEqual((rolled["value"], rolled["holds"]), (0.024, "3-session holds"))
        self.assertNotIn("note", rolled)


class TheProgramLossLine(Fixture):
    """DONE-RULE-A1 A1.3 (Oct 9, 2026): one program's own realized Probe net at or below the program loss line (-$300
    since THE PROBE TOTAL AT $800, PREREG-T, Oct 10, 2026; -$200 with the $400 before it) retires it swarm-side; its
    real positions exit by the House's rules."""

    def ctx(self):
        self.alerts: list[tuple[str, str]] = []
        return SimpleNamespace(root=self.root, now=lambda: self.now, config={},
                               alert=lambda level, text: self.alerts.append((level, text)))

    def gate(self, **extra) -> None:
        (self.root / "swarm.json").write_text(json.dumps({"dlane": {"mode": "gate", **extra}}))

    def test_due_at_the_line_from_priced_probe_closes_only(self):
        self.fam("dir-a", lane="direction", band="probe")
        self.fam("dir-b", lane="direction", band="probe")
        self.close("dir-a", pnl=-250.0, probe=True)
        self.close("dir-a", pnl=-49.99, probe=True)
        self.close("dir-a", route=":t", pnl=-500.0)               # tuition is no Probe loss
        self.close("dir-a", pnl=-80.0)                            # a Sized close (no probe mark) is no Probe loss
        self.close("dir-b", pnl=-400.0, probe=True)
        self.close("dir-b", pnl=0.0, probe=True, status="unpriced_close", qty=1)
        out = self.report()
        rows = {r["family"]: r for r in out["program_loss"]["programs"]}
        self.assertEqual((rows["dir-a"]["probe_net_usd"], rows["dir-a"]["due"]), (-299.99, False))
        self.assertEqual((rows["dir-b"]["unpriced"], rows["dir-b"]["due"]), (1, False), "an unpriced close may be a gain")
        self.assertEqual((out["program_loss"]["line_usd"], out["program_loss"]["total_usd"]), (-300.0, 800.0))
        probe = next(p for p in out["probes"] if p["family"] == "dir-a")
        self.assertEqual((probe["probe_net_usd"], probe["share_of_probe_total"]), (-299.99, 0.375))
        self.assertNotIn("PL1", [a["id"] for a in out["alarms"]])
        self.close("dir-a", pnl=-0.01, probe=True)
        out = self.report()
        self.assertEqual(out["program_loss"]["due"], ["dir-a"])
        pl1 = next(a for a in out["alarms"] if a["id"] == "PL1")["text"]
        self.assertIn("dir-a $-300.00", pl1)
        self.assertIn("($-300.00, dlane.program_loss_usd; DONE-RULE-A1 A1.3)", pl1)

    def test_the_job_retires_it_swarm_side_once_and_says_so(self):
        self.gate()
        self.fam("dir-a", lane="direction", band="probe")
        self.fam("alp-c", band="probe")
        self.close("dir-a", pnl=-310.0, probe=True)
        self.close("alp-c", pnl=-250.0, probe=True)
        self.close("dir-a", pnl=0.0, probe=True, status="open", qty=1, day="2026-10-19")   # its exit goes on
        out = R.run(self.ctx())
        self.assertEqual(out["retired"], ["dir-a"])
        fam = self.store.family("dir-a")
        self.assertEqual((fam["band"], bool(fam["retired_at"])), ("retired", True))
        self.assertIn("DONE-RULE-A1 A1.3", fam["retire_reason"])
        self.assertIsNone(self.store.family("alp-c")["retired_at"], "-$250 is above the line")
        public = [e for e in self.store._all("SELECT kind, payload FROM events WHERE family='dir-a'") if e["kind"] == "swarm.retired"]
        self.assertEqual(json.loads(public[0]["payload"])["cause"], R.PROGRAM_LOSS_PUBLIC)
        self.assertFalse(any(ch.isdigit() for ch in R.PROGRAM_LOSS_PUBLIC), "the site's tape carries words, no figure")
        private = [json.loads(e["payload"]) for e in self.store._all("SELECT kind, payload FROM events WHERE family='dir-a'")
                   if e["kind"] == "swarm.dlane"]
        self.assertEqual(private[0]["probe_net_usd"], -310.0)
        doc = json.loads((self.root / R.FILE).read_text())
        self.assertEqual(doc["program_loss"]["retired"], ["dir-a"])
        self.assertTrue(any("PL1: retired swarm-side 1 programs" in text for _, text in self.alerts))
        # Nothing else is touched: the live book's open position is the House's to close.
        self.assertEqual(self.live.rows("SELECT count(*) AS n FROM positions WHERE status='open'")[0]["n"], 1)
        again = R.run(self.ctx())
        self.assertEqual(again["retired"], [])
        self.assertNotIn("PL1", again["alarms"])

    def test_with_the_lane_off_the_line_still_holds_and_no_report_is_written(self):
        """The review of the weekend fixes (Oct 10, 2026): `dlane.mode` "off" rolled back the lane AND the program loss line
        (the job returned before `program_losses`), so an alpha Probe program could drain the shared total. The rule
        names one program whatever its lane: with the lane off the job still retires a due one, and writes no report."""
        (self.root / R.FILE).write_text(json.dumps({"at": "2026-10-19T01:30:00Z", "alarms": []}))
        before = (self.root / R.FILE).read_text()
        self.fam("alp-a", band="probe")
        self.fam("dir-b", lane="direction", band="probe")
        self.close("alp-a", pnl=-120.0, probe=True)
        self.close("dir-b", pnl=-90.0, probe=True)
        out = R.run(self.ctx())
        self.assertEqual(out["status"], "skipped", "nothing due: the rollback's receipt, as before")
        self.assertEqual(out["program_loss"]["due"], [])
        self.close("alp-a", pnl=-180.0, probe=True)
        out = R.run(self.ctx())
        self.assertEqual((out["ok"], out["lane"], out["retired"], out["alarms"]), (True, "off", ["alp-a"], ["PL1"]))
        self.assertEqual(self.store.family("alp-a")["band"], "retired")
        self.assertIsNone(self.store.family("dir-b")["retired_at"], "-$90 is above the line")
        self.assertTrue(any(level == "warning" and "PL1: retired swarm-side 1 programs" in text and "lane is off" in text
                            for level, text in self.alerts))
        self.assertEqual((self.root / R.FILE).read_text(), before, "the lane off writes no report")
        self.assertEqual(R.run(self.ctx())["status"], "skipped", "retired once: nothing due again")

    def test_a_setting_can_only_tighten_the_line(self):
        self.fam("dir-a", lane="direction", band="probe")
        self.close("dir-a", pnl=-150.0, probe=True)
        self.assertEqual(self.report(settings={"dlane": {"mode": "gate", "program_loss_usd": -100}})["program_loss"]["due"],
                         ["dir-a"])
        loose = self.report(settings={"dlane": {"mode": "gate", "program_loss_usd": -1000}})["program_loss"]
        self.assertEqual((loose["line_usd"], loose["due"]), (-300.0, []))


class TheProbeTotalsRoster(Fixture):
    """PT1 (THE PROBE TOTAL AT $800's review, Oct 10, 2026): PREREG-T measured the $800 total and the -$300 line at roster
    5 alone, and the roster moves by a swarm.json setting with no deploy: the report warns while the pair runs beside any
    other roster, and says nothing once the pair is rolled back."""

    def roster(self, value) -> None:
        (self.root / "swarm.json").write_text(json.dumps({"dlane": {"mode": "gate", "roster": value}}))

    def ids(self, settings=GATE) -> list[str]:
        return [a["id"] for a in self.report(settings=settings)["alarms"]]

    def test_the_pair_beside_roster_5_raises_nothing(self):
        self.roster(5)
        self.assertNotIn("PT1", self.ids())

    def test_the_pair_with_the_roster_off_or_moved_is_a_warning(self):
        [pt1] = [a for a in self.report()["alarms"] if a["id"] == "PT1"]
        self.assertEqual((pt1["level"], pt1["roster"], pt1["total_usd"], pt1["line_usd"]), ("warning", None, 800.0, -300.0))
        self.assertIn("the roster is off", pt1["text"])
        self.assertIn("roll the pair back to $400 and $-200 (an owner deploy)", pt1["text"])
        self.roster(3)
        [pt1] = [a for a in self.report()["alarms"] if a["id"] == "PT1"]
        self.assertEqual(pt1["roster"], 3)
        self.assertIn("the roster is 3 seats", pt1["text"])
        self.roster(0)
        self.assertIn("PT1", self.ids(), "0 is the roster's rollback: the pair needs its own")

    def test_a_closed_roster_and_the_bare_function(self):
        self.assertEqual(R.pt1_alarms({"seats": 5, "closed": False}, GATE), [])
        [pt1] = R.pt1_alarms({"seats": 0, "closed": True}, GATE)
        self.assertEqual(pt1["roster"], "closed")
        self.assertIn("closed (no new seat)", pt1["text"])

    def test_the_rolled_back_pair_raises_nothing_and_half_a_rollback_still_warns(self):
        from unittest import mock

        from league.constitution import CONSTITUTION

        ld = {"dlane": {"mode": "gate", "program_loss_usd": -200}}
        with mock.patch.dict(CONSTITUTION["options_money"]["probe"], {"loss_total_usd": "400"}):
            self.assertEqual(R.pt1_alarms(None, ld), [], "L-D's $400 and -$200: what every roster was measured beside")
            self.assertEqual(R.pt1_alarms({"seats": 3, "closed": False}, ld), [])
            self.assertEqual([a["id"] for a in R.pt1_alarms(None, GATE)], ["PT1"], "the -$300 line alone is the pair's")
        self.assertEqual([a["id"] for a in R.pt1_alarms(None, ld)], ["PT1"], "the $800 total alone is the pair's")


class TheReportFixes(Fixture):
    """The readiness audit's m11 (Oct 10, 2026): an exact close or a why; real opens in the funnel; E0 said as it is."""

    def test_the_buy_and_hold_never_takes_another_days_close(self):
        close = {"root": "SPY", "opened_day": "2026-10-05", "day": "2026-10-08", "max_loss_usd": 100.0, "opened_qty": 1,
                 "legs": [], "entry": 0.5, "opened_at": ny("2026-10-05")}
        bh = R.buy_and_hold(close, {"SPY": {"2026-10-02": 495.0, "2026-10-05": 500.0}})
        self.assertEqual((bh["risk_usd"], bh["delta_usd"]), (None, None))
        self.assertIn("on 2026-10-08", bh["why"])
        self.assertIn("its last close: 2026-10-05", bh["why"])

    def test_the_direction_job_keeps_only_finished_sessions(self):
        from league.ops import direction as DIR

        friday = dt.datetime(2026, 10, 9, 17, 5, tzinfo=dt.timezone.utc).timestamp()     # 13:05 ET, in session
        self.assertFalse(DIR.session_closed("2026-10-09", friday))
        self.assertTrue(DIR.session_closed("2026-10-09", friday + 3 * 3600 + 15 * 60))
        self.assertTrue(DIR.session_closed("2026-10-10", friday), "a Saturday has no bar to be partial")

        class Gateway:
            def get(self, path, params=None):
                return {"bars": {"SPY": [{"t": "2026-10-08T04:00:00Z", "c": 770.0}, {"t": "2026-10-09T04:00:00Z", "c": 778.35}]},
                        "next_page_token": None}

        (self.root / "swarm.json").write_text(json.dumps({"gym": {"roots": ["SPY"]}}))
        for now, want in ((friday, {"2026-10-08": 770.0}), (friday + 4 * 3600, {"2026-10-08": 770.0, "2026-10-09": 778.35})):
            out = DIR.run(SimpleNamespace(root=self.root, now=lambda now=now: now, gateway=Gateway()))
            self.assertTrue(out["ok"], out)
            self.assertEqual(DIR.load_closes(self.root / DIR.FILE)["SPY"], want)

    def test_the_funnel_counts_real_opens_by_route(self):
        self.fam("dir-a", lane="direction")
        self.close("dir-a", status="open", qty=1, day="2026-10-20", opened=self.now - 3600, probe=True)
        self.close("house:calibration", route=":c", status="open", qty=1, day="2026-10-20", opened=self.now - 3600)
        funnel = self.report()["funnel"]
        self.assertEqual(funnel["24h"]["direction"]["real_opens"], {":r": 1, ":t": 0, ":i": 0, "other": 0})
        self.assertEqual(funnel["24h"]["direction"]["real_closes"][":r"], 0)
        self.assertEqual(sum(funnel["24h"]["alpha"]["real_opens"].values()), 0, "the House's routes are never counted")

    def test_e0_is_said_as_what_it_is(self):
        (self.root / "health.json").write_text(json.dumps({"options_live": {"stops": {
            "sod_equity": "1300.00", "last_reading": [self.now - 60, "1335.01", "2026-10-20"]}}}))
        previous = {"account": {"e0": {"usd": 1295.11, "at": "2026-10-08T19:54:03Z",
                                       "basis": "the first equity reading the dlane report saw (release L-D's deploy "
                                                "reading is the plan's E0)"}}}
        e0 = self.report(previous=previous)["account"]["e0"]
        self.assertEqual((e0["usd"], e0["at"], e0["basis"]), (1295.11, "2026-10-08T19:54:03Z", R.E0_BASIS))


class ReportedOnly(unittest.TestCase):
    def test_no_swarm_live_or_gym_module_reads_the_report(self):
        paths = [p for tree in ("league/swarm", "league/live", "league/gym") for p in (REPO / tree).rglob("*.py")]
        paths += [REPO / "league" / "house.py", REPO / "league" / "constitution.py"]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for needle in ("dlane_report", "dlane-report"):
                self.assertNotIn(needle, text, f"{path.relative_to(REPO)} reads {needle}")

    def test_the_registry_runs_it_at_start_and_daily_at_0130z_in_a_pause_too(self):
        from league.ops.registry import JOBS, by_name

        self.assertEqual([j.name for j in JOBS].count("dlane"), 1)
        job = by_name()["dlane"]
        self.assertEqual((job.module, job.in_pause, job.paid), ("league.ops.dlane_report", True, False))
        self.assertEqual([t.kind for t in job.triggers], ["start", "daily", "open"])
        self.assertEqual((job.triggers[1].at.hour, job.triggers[1].at.minute), (1, 30))
        # The review of the weekend fixes (Oct 10, 2026): 30 minutes before each open too, after the overnight expiry
        # reconciliation (the program loss line acts before the session, A1.3).
        self.assertEqual(job.triggers[2].offset_minutes, -30)

    def test_the_game_report_says_what_the_lane_changed_mid_experiment_only_while_it_is_on(self):
        """The operator's decision 1: the alpha births' fall and the ROLE prompt's change ride in the game's report, once:
        through `game.metrics`' `dlane` block (`game.DIRECTION_NOTES`; the integration of release D-1 kept that one
        place and dropped the report's own copy)."""
        from league.ops import game_report
        from league.swarm import game

        with tempfile.TemporaryDirectory() as tmp:
            SwarmStore(tmp).close()
            on = game_report.report(Path(tmp), settings=GATE, now=Fixture.NOW, draws=50)
            off = game_report.report(Path(tmp), settings={}, now=Fixture.NOW, draws=50)
        notes = " ".join(on["dlane"]["notes"])
        self.assertEqual(on["dlane"]["notes"], list(game.DIRECTION_NOTES))
        self.assertIn("about 73 to about 36", notes)
        self.assertIn("code paths only", notes)
        self.assertIn("arm_fraction 0", notes)
        self.assertNotIn("dlane", off)
        self.assertEqual(set(on) - {"dlane"}, set(off))

    def test_the_header_lists_the_graveyards_alpha_rows_with_their_cost(self):
        """The direction graveyard rule (PR #519, deployed 12:44Z Oct 9, 2026) is a reported loosening: the header of every
        report names it beside the DRIFT rows' with its cost (the owner's goal of Oct 9, item 5)."""
        rules = [r["rule"] for r in R.LOOSENED]
        [row] = [r for r in R.LOOSENED if r["rule"].startswith("graveyard alpha rows")]
        self.assertEqual(rules.index(row["rule"]), rules.index("graveyard DRIFT rows") + 1)
        self.assertIn("PR #519", row["rule"])
        self.assertIn("bound only by direction families' graveyard rows", row["now"])
        self.assertIn("retry ideas similar to dead alpha ones", row["cost"])
        self.assertIn("10.4% per program", row["cost"])

    def test_the_header_lists_the_probe_total_and_the_program_line_with_their_costs(self):
        """THE PROBE TOTAL AT $800 (PREREG-T, Oct 10, 2026): the total $400 -> $800 and the program loss line -$200 ->
        -$300 are reported loosenings, each with its cost (the owner's goal of Oct 9, item 5), and the header's figures
        follow the settings in force."""
        from league.constitution import CONSTITUTION

        rows = {r["rule"]: r for r in R.LOOSENED}
        total = rows["the Probe total (PREREG-T, Oct 10)"]
        line = rows["the program loss line (PREREG-T, Oct 10)"]
        order = list(rows)  # the pair as adopted, in order (the always-in graveyard's row of Oct 10 follows them)
        self.assertEqual(order.index(line["rule"]), order.index(total["rule"]) + 1)
        self.assertEqual((total["was"][:4], total["now"][:4]), ("$400", "$800"))
        self.assertEqual((line["was"][:5], line["now"][:5]), ("-$200", "-$300"))
        for figure in ("17.8% -> 36.8%", "0.6% -> 4.4%", "-$396 -> -$679", "21% -> 48%", "-$327 -> -$231",
                       "4.6% -> 5.5%", "11.6% -> 14.4%", "2.2% -> 2.7%", "6.9% -> 9.0%", "not alpha",
                       "with the -$300 line below (the pair as adopted)", "35.8%, 4.1%, -$674 and 46%",
                       "the agents' running real net", "roster 5 alone", "alarm PT1"):
            self.assertIn(figure, total["cost"])
        # The review of Oct 10: PREREG-T measured the line's own step (the $800 total with -$200 beside it), so its row
        # carries that cost and how narrowly it cleared the pre-registered preference, not "measured only together".
        self.assertIn("$100 more of the shared total", line["cost"])
        for figure in ("35.8% -> 36.8%", "4.1% -> 4.4%", "46% -> 48%", "2.5% -> 2.7%", "5.3% -> 5.5%",
                       "+0.24 points, SE 0.12", "2.06 SE", "roster 5 alone"):
            self.assertIn(figure, line["cost"])
        self.assertNotIn("only together", line["cost"])
        self.assertNotIn("running Probe net", total["cost"] + line["cost"])
        self.assertEqual(CONSTITUTION["options_money"]["probe"]["loss_total_usd"], total["now"][1:4])
        self.assertEqual(dlane.cfg({"dlane": {"mode": "gate"}})["program_loss_usd"],
                         float(line["now"][:5].replace("$", "")))

    def test_the_contamination_statement_names_windows_and_no_figure(self):
        """The operator's rule: no private study's figure in the repository. The statement names its windows and the
        authors' cutoff, and no other number; the costs are ASCII (they ride in a House alert's report)."""
        import re

        numbers = set(re.findall(r"\d[\d,.\-]*\d|\d", R.CONTAMINATION))
        self.assertEqual(numbers, {"2022-24", "2025", "2026", "5.5", "2017-19", "2026-07-01"})
        for text in [R.CONTAMINATION, *[" ".join(r.values()) for r in R.LOOSENED], *R.TIGHTENED]:
            self.assertTrue(text.isascii())
        self.assertIn("2017-19 census is spent", R.CONTAMINATION)
        self.assertIn("for the direction lane as a whole", R.CONTAMINATION)


# ================================================================================================== the fast lane rows
class TheFastLaneRowsLane(Fixture):
    def rows(self, settings) -> list[dict]:
        from unittest import mock

        from league.ops import direction as DIR
        from league.ops import fast_lane as FL

        with mock.patch.object(DIR, "train_fit", lambda store, fam, n: {"basis": "train-held-hours"}), \
                mock.patch.object(FL, "_roots", lambda store, fam, n: ("SPY",)):
            out = FL.report(self.root, None, self.root / "direction-closes.json", today="2026-10-20", settings=settings)
        return out["screen"]

    def test_each_row_names_its_lane_only_while_the_lane_is_on(self):
        self.fam("dir-a", lane="direction")
        self.fam("alp-b")
        self.store.add_look("dir-a", 1, "sha-a", passed=True, p_value=0.15, detail={})
        self.store.add_look("alp-b", 1, "sha-b", passed=False, p_value=0.5, detail={})
        on = {r["family"]: r.get("lane") for r in self.rows(GATE)}
        self.assertEqual(on, {"dir-a": "direction", "alp-b": "alpha"})
        for settings in (None, {}, {"dlane": {"mode": "off"}}):
            self.assertTrue(all("lane" not in r for r in self.rows(settings)), settings)


# ================================================================================================== the agenda guard (D9)
def install_tool():
    spec = importlib.util.spec_from_file_location("agenda_install", REPO / "scripts" / "agenda_install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def quiet(fn, *args, **kwargs):
    """`fn` with its stdout swallowed (the tool prints its JSON; the swarm logs its warning)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


class TheAgendaGuard(unittest.TestCase):
    """HARNESS 6.4 item 13: an agenda the architect reads whole (v20 and v21 are under 4,000 characters) passes; v19's
    4,407 is refused, by the operator's tool before it is written and by the swarm's House warning after. The agendas
    are the operator's private text: these stand-ins have their lengths, never their words."""

    def text(self, n: int) -> str:
        words = "Train is 2022-2024 and nothing else. Aim every birth at a program that makes money after costs. "
        return (words * (n // len(words) + 1))[:n]

    def test_the_limit_is_what_the_architect_reads(self):
        from league.swarm import architect

        self.assertEqual(dlane.AGENDA_MAX, architect.AGENDA_LOCKED_MAX)
        self.assertEqual(dlane.agenda_problems(self.text(3943)), [])
        self.assertEqual(dlane.agenda_problems(self.text(4000)), [])
        [problem] = dlane.agenda_problems(self.text(4407))
        self.assertIn("4,407 characters", problem)
        self.assertTrue(dlane.agenda_problems(self.text(3000) + " 2021"))
        self.assertTrue(dlane.agenda_problems(self.text(3000) + " —"))

    def test_the_swarm_warns_at_its_start_and_again_only_when_the_problem_changes(self):
        from league.swarm import loop

        settings = {**GATE, "architect": {"agenda_locked": self.text(4407), "agenda": self.text(3900)}}
        payload = loop.agenda_alert(settings)
        self.assertEqual(set(payload["problems"]), {"agenda_locked"})
        self.assertTrue(payload["alert"])
        self.assertNotIn(self.text(40), payload["text"], "lengths and reasons, never the agenda's words")
        self.assertIsNone(loop.agenda_alert({"architect": settings["architect"]}), "the lane off: the rollback")
        self.assertIsNone(loop.agenda_alert({**GATE, "architect": {"agenda_locked": "", "agenda": ""}}))
        events = []
        swarm = SimpleNamespace(settings=settings, store=SimpleNamespace(event=lambda *a: events.append(a)))
        self.assertIsNotNone(quiet(loop.Swarm.agenda_notice, swarm))
        self.assertIsNone(quiet(loop.Swarm.agenda_notice, swarm), "never one a loop")
        swarm.settings = {**GATE, "architect": {"agenda_locked": self.text(4500)}}
        self.assertIsNotNone(quiet(loop.Swarm.agenda_notice, swarm))
        self.assertEqual([e[0] for e in events], ["swarm.status", "swarm.status"])

    def test_the_operators_tool_refuses_a_long_agenda_and_installs_one_that_fits(self):
        tool = install_tool()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / "swarm.json").write_text(json.dumps({"architect": {"agenda_locked": "old", "agenda": "old"},
                                                          "dlane": {"mode": "gate"}}))
            before = (state / "swarm.json").read_bytes()
            store = SwarmStore(state)
            store.put(tool.SECTION_KEY, {"text": "a section written under the old preamble"})
            store.close()
            long_file, good_file = state / "v19.txt", state / "v21.txt"
            long_file.write_text(self.text(4407) + "\n")
            good_file.write_text(self.text(3943) + "\n")
            self.assertEqual(quiet(tool.main, ["apply", str(long_file), "--state", str(state)]), 2)
            self.assertEqual((state / "swarm.json").read_bytes(), before, "refused: nothing written")
            self.assertEqual(list(state.glob("swarm.json.before-*")), [])
            self.assertEqual(quiet(tool.main, ["check", str(good_file), "--state", str(state)]), 0)
            self.assertEqual((state / "swarm.json").read_bytes(), before, "check is read-only")
            self.assertEqual(quiet(tool.main, ["apply", str(good_file), "--state", str(state)]), 0)
            doc = json.loads((state / "swarm.json").read_text())
            self.assertEqual(doc["architect"]["agenda_locked"], self.text(3943))
            self.assertEqual(doc["architect"]["agenda"], self.text(3943))
            self.assertEqual(doc["dlane"], {"mode": "gate"}, "nothing else moves")
            [backup] = state.glob("swarm.json.before-agenda-*")
            self.assertEqual(backup.read_bytes(), before)
            self.assertEqual(os.stat(state / "swarm.json").st_mode & 0o777, 0o600)
            store = SwarmStore(state)
            self.assertIsNone(store.get(tool.SECTION_KEY))
            store.close()

    def test_the_committed_settings_hold_no_agenda_the_guard_refuses(self):
        from league.swarm import settings as S
        from league.tests import REAL_POLICY_PATH

        policy = json.loads(REAL_POLICY_PATH.read_text())
        for layer in (S.DEFAULTS, policy):
            block = layer.get("architect") or {}
            for key in ("agenda_locked", "agenda"):
                text = str(block.get(key) or "").strip()
                if text:
                    self.assertEqual(dlane.agenda_problems(text), [], key)


if __name__ == "__main__":
    unittest.main()
