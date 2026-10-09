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
              root: str = "SPY", legs: list | None = None, entry: float = 0.5, qty: int = 0) -> int:
        self.pid += 1
        opened = ny(day, 10, 0)
        self.live.upsert("positions", {
            "pid": self.pid, "instance": f"{family}@{version}{route}", "family": family, "type": "long_call", "root": root,
            "legs": json.dumps(legs or []), "qty": qty, "opened_qty": 1, "entry": entry, "max_loss_share": max_loss / 100.0,
            "collateral": 0.0, "fees": 0.13, "cash": pnl, "opened_at": opened, "opened_day": day, "opened_minute": 30,
            "status": status, "closed_at": closed_at if closed_at is not None else opened + 3 * 86400.0 + self.pid,
            "tuition": 1 if route in (":t", ":i") else 0,
            "info": json.dumps({"order": self.pid, **({"probe": True} if probe else {})})}, "pid")
        return self.pid

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
        self.assertEqual(out["done"]["p_done_zero_edge"], {"value": 0.13, "label": "P(Done | zero edge), simulation"})
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
        for _ in range(4):
            self.close("dir-a", pnl=-100.0)           # closes 31-34: after the checkpoint
        out = self.report()["done"]["screen"]
        self.assertEqual(len(out["checkpoints"]), 1)
        cp = out["checkpoints"][0]
        self.assertEqual((cp["at_close"], cp["closes"], cp["net_usd"], cp["holds"]), (30, 30, 150.0, True))
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
        done = {"all": {"checkpoints": [{"at_close": 30, "holds": True}]}, "screen": {"checkpoints": []}}
        a = self.alarms(done=done)["A8"]
        self.assertEqual((a["level"], a["meter"], a["at_close"]), ("info", "done_all", 30))
        self.assertNotIn("A8", self.alarms(done=done, previous={"done": done}))

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
        self.assertEqual([t.kind for t in job.triggers], ["start", "daily"])
        self.assertEqual((job.triggers[1].at.hour, job.triggers[1].at.minute), (1, 30))

    def test_the_game_report_says_what_the_lane_changed_mid_experiment_only_while_it_is_on(self):
        """The operator's decision 1: the alpha births' fall and the ROLE prompt's change ride in the game's report."""
        from league.ops import game_report

        with tempfile.TemporaryDirectory() as tmp:
            SwarmStore(tmp).close()
            on = game_report.report(Path(tmp), settings=GATE, now=Fixture.NOW, draws=50)
            off = game_report.report(Path(tmp), settings={}, now=Fixture.NOW, draws=50)
        self.assertEqual(on["direction_lane"], game_report.DIRECTION_LANE_NOTE)
        self.assertIn("about 73 to about 36", on["direction_lane"]["births"])
        self.assertIn("code paths only", on["direction_lane"]["prompt"])
        self.assertNotIn("direction_lane", off)
        self.assertEqual(set(on) - {"direction_lane"}, set(off))

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
