"""Release E4 at integration: what holds ACROSS its packages, on every package's real code (league/tests/test_e4_e2e.py
is the lane's one path from a birth to the Done meter; this module is what stands around it).

- `WithEverySwitchOff`: `elane.panel.mode` "off", as the committed policy.json ships it, on a state root where every
  OTHER condition of the lane holds (the panel store, the spreads, the pinned receipt, the universe deploy, the I6, the
  twin marker): nothing of E4 is born, runs, spends or takes a seat; and the data jobs are registered read-only.
- `TheSeatOfASeatedPanelProgram`: the seat rule holds for a panel family ALREADY at Probe (the integrator's fix: the
  packages gave a Candidate no row while the lane is not live, and left a seated program buying): no row; the store's
  word the book retires on is "demoted" ONLY when the captain's switch is down, "held" when a store-side leg of the
  lane failed (E4-SPEC 17: its opens stop, its exits go on, nothing is retired) and "unknown" when the lane cannot be
  read; an ETF family is asked nothing of it.
- `TheLaneStopsWhereItsRuleSays`: with no contamination reading of the panel strata (the probe's permit and package B's
  patch 18: owed) no look runs and none is spent (the captain's A22 (3)); with no twin marker (package J's panel
  night writes it: league/ops/forward_xs.py) the effective mode is "gate" whatever the setting.
- `TheDataJobsOnTheRealStore`: package B's spreads and N_eff jobs on package C's real store (they were built against
  fakes of it), and package A's and the twins' readers of what they leave.
- `TheLiveColumnsOnTheRealUniverse`: package H's columns on package C's real universe: the live eligibility is the
  store's own (the class of the month included), and a held name that left the index keeps its column.
- `TheSeams`: the committed receipt, its pin and the House's sentence; one rounding bound for both lanes; the stall
  job's structures are the store's; every job row names a built module with its own wall."""

from __future__ import annotations

import ast
import datetime as dt
import importlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping
from unittest import mock

try:
    import numpy  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.equity import LANES
    from league.equity import config as econfig
    from league.equity.families import EquityFamilies
    from league.ops import registry, stall
    from league.swarm import bands, elane, elane_xs
    from league.swarm import settings as settings_mod
    from league.swarm import store as store_mod
    from league.swarm.architect import Architect
    from league.swarm.elane_train import EquityResearcher
    from league.swarm.gate import Gate, run_sha
    from league.swarm.store import SwarmStore
    from league.swarm.tournament import Tournament
    from league.tests import REAL_POLICY_PATH
    from league.tests.elane_e2_fakes import FakeRouter, answer
    from league.tests.test_e4_e2e import CARD, FAKE_RECEIPT, PROGRAM, PROPOSAL, ROUTE
    from league.tests.test_equity_book import Clock, at
    from league.xs import book as xbook
    from league.xs import config as xconfig
    from league.xs import identity as xidentity
    from league.xs import screen as xscreen
    from league.xs import synth

REPO = Path(__file__).resolve().parents[2]
SUNDAY = dt.date(2026, 10, 11)
FRIDAY = dt.date(2026, 10, 9)
E4_JOBS = ("equity_universe", "equity_panel", "equity_spreads", "equity_neff", "french", "xs_zero_edge")


class _Exploding:
    """A panel runner (or a decider) nothing may ask: every attribute read fails the test."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the panel runner was asked for {name!r} with the lane off")


class _Root(unittest.TestCase):
    """A state root ready for the panel lane in every respect but the switches a test sets: a synthetic panel store
    with the universe deploy in force and the I6 held, the twin marker, the probe's file, and a release whose
    policy.json pins the FAKE receipt (as the real one is pinned)."""

    SWITCHES: Mapping[str, Any] = {}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.root.mkdir()
        self.repo = Path(self.tmp.name) / "release"
        (self.repo / "docs" / "benchmarks").mkdir(parents=True)
        shutil.copyfile(FAKE_RECEIPT, self.repo / xscreen.RECEIPT_PATH)
        policy = json.loads(REAL_POLICY_PATH.read_text(encoding="utf-8"))
        policy["elane"]["screens"]["equity_xs"] = xscreen.pin(self.repo / xscreen.RECEIPT_PATH)
        (self.repo / "policy.json").write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
        for patcher in (mock.patch.object(settings_mod, "POLICY_PATH", self.repo / "policy.json"),
                        mock.patch.object(elane, "REPO", self.repo)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.forget)
        self.clock = Clock(at(SUNDAY, 12, 0))
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.store_root = synth.synthetic_panel(self.root / elane_xs.STORE_DIR, n_assets=24, gate=True,
                                                live_from=dt.date(2026, 9, 1))
        self.manifest(i6={"day": FRIDAY.isoformat(), "equal": True, "source": "fetch", "live": {}})
        self.marker()
        cell = {"readable": True, "recalled": False}
        self.probe = {"version": elane_xs.PROBE_VERSION, "routes": {ROUTE: {
            "model": "fake-model", "at": "2026-10-10T00:20:00Z",
            "cells": {s: {"2016-24": dict(cell), "2025": dict(cell)} for s in elane_xs.PROBE_STRATA}}}}
        (self.root / elane_xs.PROBE_FILE).write_text(json.dumps(self.probe), encoding="utf-8")
        self.switch(self.SWITCHES)

    @staticmethod
    def forget() -> None:
        with elane_xs._cache_lock:
            elane_xs._mode_cache.clear()
            elane_xs._json_cache.clear()

    def switch(self, layer: Mapping[str, Any]) -> dict:
        (self.root / "swarm.json").write_text(json.dumps(layer), encoding="utf-8")
        self.forget()
        self.settings = settings_mod.load(self.root)
        return self.settings

    def manifest(self, **facts: Any) -> None:
        path = self.store_root / "panel" / "PANEL_MANIFEST.json"
        path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), **facts}), encoding="utf-8")
        self.forget()

    def marker(self, through: dt.date = FRIDAY) -> None:
        (self.store_root / xbook.TWINS_FILE).write_text(json.dumps(
            {"version": xbook.TWINS_VERSION, "through": through.isoformat(), "at": "2026-10-10T01:00:00Z",
             "instances": {}}), encoding="utf-8")
        self.forget()

    def family(self, slug: str = "rev-a", *, band: str | None = None, structure: str = "panel") -> dict:
        """A family with a v1: a panel family as the lane bears it, or an ETF family of the equity lanes; `band`: put
        there with a band proof under the identity its structure is judged by."""
        if structure == "panel":
            spec = {"id": slug, "mechanism": PROPOSAL["mechanism"], "structure": "panel", "roots": [], "lane": "equity",
                    "agenda": "xs_reversal", "panel": "sp500", "max_names": 5, "rebalance": "weekly", "weekday": 0,
                    "e2_route": ROUTE, "hidden_year": None, "gid": "g0"}
            code = PROGRAM
        else:
            spec = {"id": slug, "mechanism": "Index holders are paid for overnight risk they cannot trade out of.",
                    "structure": "etf", "roots": ["SPY"], "lane": "beta", "symbols": ["SPY"]}
            code = ('NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}\n\n\ndef decide(ctx):\n'
                    '    return [{"buy": "SPY", "share": 0.5, "at": "close"}]\n')
        fam = self.store.add_family(spec, origin="architect")
        version = self.store.add_version(fam["id"], code, {}, author="architect:test")
        if structure == "panel":
            self.store.set_state(fam["id"], **{elane_xs.STATE_KEY: {"status": "researching", "versions": {}}})
        if band is not None:
            from league.swarm.evaluator import equity_identity

            sha = run_sha(self.store.version(fam["id"], version["n"]))
            proof = ({"engine": xidentity.xs_identity()["engine"], "xs_sha256": xidentity.xs_fingerprint(), "run_sha": sha}
                     if structure == "panel" else
                     {"engine": equity_identity()["engine"], "equity_sha256": equity_identity()["equity"], "run_sha": sha})
            self.store.update_family(fam["id"], best_version=version["n"], validated_version=version["n"])
            self.store.set_state(fam["id"], banded_version=version["n"], banded_at=self.clock(), banded_evaluator=proof,
                                 gate="pass", holdout_passed=True)
            self.store.set_band(fam["id"], "candidate", reason="a test's look")
            if band != "candidate":
                self.store.set_band(fam["id"], band, reason="a test's seat")
        return self.store.family(fam["id"])


@unittest.skipUnless(HAVE, "numpy not installed")
class WithEverySwitchOff(_Root):
    """`elane.panel.mode` "off" (what policy.json ships) with E1's and E2's lanes ON and every other condition of the
    panel lane held: the one switch is what keeps the lane closed."""

    SWITCHES = {"elane": {"mode": "gate", "birth_share": 0.25}, "dlane": {"mode": "gate"}}

    def test_the_committed_policy_ships_the_lane_off_and_its_parent_lanes_off(self):
        policy = json.loads(REAL_POLICY_PATH.read_text(encoding="utf-8"))["elane"]
        self.assertEqual((policy["mode"], policy["birth_share"], policy["panel"]["mode"]), ("off", 0.0, "off"))
        self.assertEqual(policy["panel"], {**elane_xs.DEFAULTS, "mode": "off"}, "the block is the code's defaults")
        shipped = settings_mod.load(policy=json.loads(REAL_POLICY_PATH.read_text(encoding="utf-8")))
        self.assertEqual(elane_xs.mode(shipped, self.root), "off")

    def test_the_one_switch_keeps_the_lane_closed_when_everything_else_is_ready(self):
        self.assertEqual(elane_xs.mode(self.settings, self.root), "off")
        self.assertEqual(elane_xs.seat_standing(self.root)[0], False)
        up = {**self.SWITCHES, "elane": {**self.SWITCHES["elane"], "panel": {"mode": "live"}}}
        self.assertEqual(elane_xs.mode(self.switch(up), self.root), "live", "and it is the only thing in the way")

    def test_nothing_is_born_nothing_runs_nothing_is_spent_and_nobody_is_seated(self):
        # A panel family born before the switch went down, a panel Candidate and one at Probe: none moves.
        self.family("rev-old")
        self.family("rev-cand", band="candidate")
        self.family("rev-probe", band="probe")
        calls: list[dict] = []

        def model(call):
            calls.append(dict(call))
            return answer([dict(PROPOSAL, slug="rev-new", card=dict(CARD))])

        router = FakeRouter(model)
        self.clock.set(self.clock() + 7200)
        out = Architect(self.store, router, self.settings, clock=self.clock).equity_pass()
        self.assertEqual(out["born"], [])
        self.assertNotIn("panel", out, "with the lane off the pass is E2's own")
        self.assertIn("the panel lane is closed", out["refused"]["items"][0]["why"])
        [request] = [c["user"] for c in calls]
        for part in ("THE PANEL", "PANEL QUOTA", "PANEL TRAIN MAP", "equity-xs-v1"):
            self.assertNotIn(part, request)
        self.assertIsNone(self.store.family("rev-new"))

        runner = _Exploding()
        researcher = EquityResearcher(self.store, router, self.settings, root=self.root, clock=self.clock)
        researcher.xs_runner = runner
        self.assertEqual(elane_xs.blocked(researcher), "the panel lane is closed (elane.panel.mode)")
        self.assertEqual(researcher.step(self.store.family("rev-old")),
                         {"family": "rev-old", "skipped": "the panel lane is closed (elane.panel.mode)"})
        tournament = Tournament(self.store, None, self.settings, clock=self.clock)
        tournament.xs_runner = runner
        fam = self.store.family("rev-old")
        got = elane.validate(tournament, fam, self.store.version("rev-old", 1))
        self.assertEqual((got["entered"], got["refused"]),
                         (False, "the panel lane's gate is closed (elane.panel.mode, the pinned receipt, the spreads)"))
        gate = Gate(self.store, None, None, self.settings, clock=self.clock)
        gate.xs_runner = runner
        version = self.store.version("rev-old", 1)
        self.assertIsNone(elane.look(gate, fam, version, run_sha(version)))
        self.assertEqual(self.store.looks(), [], "no look is spent")
        self.assertEqual(len(calls), 1, "one model call: E2's own births request")
        self.assertEqual(elane_xs.cpu_spent(self.store, self.clock()), 0)
        self.assertEqual(self.store.runs("rev-old"), [])

        # NO SEAT: neither the Candidate nor the family already at Probe has a row for the book.
        self.assertFalse(elane_xs.seatable(self.root)("panel"))
        self.assertEqual(bands.read(self.root, lanes=LANES), [])
        self.assertEqual(EquityFamilies(self.root).read(), [])

    def test_the_zero_edge_job_is_skipped_and_starts_no_child(self):
        from league.ops import xs_zero_edge

        ctx = SimpleNamespace(root=self.root, now=self.clock, alert=lambda *a, **k: None)
        with mock.patch.object(xs_zero_edge, "build_runner", side_effect=AssertionError("a child with the lane off")):
            self.assertEqual(xs_zero_edge.run(ctx), {"status": "skipped", "why": "the panel lane is off (elane.panel.mode)"})

    def test_the_data_jobs_are_skipped_and_ask_the_gateway_nothing(self):
        """WITH EVERY E4 SWITCH OFF NOTHING OF E4 RUNS: the data jobs too (the review's live-9: at the first House
        start after the release they went at once, a whole panel fetch of about 1,000 gateway calls among them, and
        the spreads job asked 6,000 calls a night). Each one's first statement is the lane's switch."""
        from league.ops import equity_neff, equity_panel, equity_spreads, equity_universe, french
        from league.ops.context import Context

        class Gateway:
            def __getattr__(self, name):
                raise AssertionError(f"the gateway was asked ({name}) with the lane off")

        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())
        now = at(SUNDAY, 2, 30)
        for module in (equity_universe, equity_panel, equity_spreads, equity_neff, french):
            name = module.__name__.rsplit(".", 1)[1]
            ctx = Context(name, root=self.root, due_at=now, clock=lambda: now, gateway=Gateway(), config={},
                          settings_value={})
            with mock.patch.object(xconfig, "quiet", side_effect=AssertionError("asked the walls with the lane off")):
                self.assertEqual(module.run(ctx), {"status": "skipped", "why": equity_universe.LANE_OFF}, name)
            self.assertEqual(ctx.alerts, [], name)
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file()), before,
                         "and nothing was written")
        # THE SETTING is read, never the effective mode (which reads "off" until these jobs have written the store):
        # the captain's first step up starts the data.
        self.assertEqual(equity_universe.lane_off(self.root), equity_universe.LANE_OFF)
        self.switch({"elane": {"mode": "off", "panel": {"mode": "train"}}})
        self.assertEqual((elane_xs.mode(self.settings, self.root), equity_universe.lane_off(self.root)), ("off", None))
        (self.root / "swarm.json").write_text('{"elane": {"panel": {"mo', encoding="utf-8")   # caught mid-write
        self.assertEqual(equity_universe.lane_off(self.root), equity_universe.LANE_OFF, "a switch not read is off")

    def test_the_data_jobs_are_registered_read_only_unpaid_and_never_in_a_session(self):
        """The data jobs read, they spend no model dollar, they send no order, no row of them is due inside a session,
        and none starts with the House or behind another job's success (each has its own time of night)."""
        rows = {job.name: job for job in registry.JOBS}
        self.assertEqual([job.name for job in registry.JOBS][-len(E4_JOBS):], list(E4_JOBS), "last: after every older job")
        writes = re.compile(r"\.(put|delete|patch|submit|cancel)\(|/v2/orders|orders_path|ORDERS")
        for name in E4_JOBS:
            job = rows[name]
            self.assertEqual((job.paid, job.in_pause, job.owner), (False, True, "breadth"), name)
            self.assertEqual([t.kind for t in job.triggers if t.kind in ("start", "after")], [], name)
            module = importlib.import_module(job.module)
            self.assertTrue(callable(module.run), name)
            self.assertEqual(job.wall, module.WALL_S, f"{name}: the row's wall is the module's own")
            text = Path(module.__file__).read_text(encoding="utf-8")
            gateway_calls = re.findall(r"gateway\.(\w+)\(", text)
            self.assertTrue(set(gateway_calls) <= {"get", "post"}, (name, gateway_calls))
            self.assertIsNone(writes.search(text.replace("store.put(", "")), f"{name} names an order or a write route")
        # The one POST of the six is the gateway's web READER (a public page fetched for the membership source).
        universe = Path(importlib.import_module(rows["equity_universe"].module).__file__).read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"gateway\.post\((\w+)", universe), ["WEB"])
        self.assertEqual(sum(1 for name in E4_JOBS for _ in re.findall(
            r"gateway\.post\(", Path(importlib.import_module(rows[name].module).__file__).read_text(encoding="utf-8"))), 1)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheLaneSaysWhereItStands(_Root):
    """The review's spec-6: the reason the lane's mode reads under its setting reached no status, heartbeat or alert,
    a seatless panel Candidate was listed with no word on what it waits for, and nothing looked for a job at a wall."""

    SWITCHES = {"elane": {"mode": "gate", "birth_share": 0.25, "panel": {"mode": "live"}}, "dlane": {"mode": "gate"}}

    def test_the_heartbeat_the_report_and_the_roster_name_the_leg(self):
        from league.ops import dlane_report
        from league.swarm.loop import Swarm

        self.family("rev-cand", band="candidate")
        beat = Swarm.panel_status(SimpleNamespace(settings=self.settings, store=self.store))
        self.assertEqual(beat, {"panel": {"setting": "live", "mode": "live", "why": None}})
        self.assertEqual(bands.roster(self.root, lanes=LANES)["seatless"], [])
        self.manifest(i6={"day": FRIDAY.isoformat(), "equal": False, "source": "fetch", "live": {}})
        leg = "the last nightly I6 did not hold (the live ctx is not proved equal to the Gym's)"
        beat = Swarm.panel_status(SimpleNamespace(settings=self.settings, store=self.store))
        self.assertEqual(beat, {"panel": {"setting": "live", "mode": "gate", "why": leg}})
        roster = bands.roster(self.root, lanes=LANES)
        self.assertEqual(roster["seatless"], ["rev-cand"])
        self.assertEqual(roster["seatless_why"], {"rev-cand": f'the panel lane is not live (set "live", it reads "gate"): {leg}'})
        lane = dlane_report.panel_lane(self.root, self.settings)["panel_lane"]
        self.assertEqual((lane["setting"], lane["mode"], lane["why"]), ("live", "gate", leg))
        self.assertEqual(lane["roster"]["seatless_why"], roster["seatless_why"])
        # The captain's own step down reads so too; and with the switch off nothing of the lane is read or said.
        self.switch({"elane": {"mode": "gate", "birth_share": 0.25, "panel": {"mode": "gate"}}})
        self.assertIn("elane.panel.mode is set so", bands.roster(self.root, lanes=LANES)["seatless_why"]["rev-cand"])
        self.switch({"elane": {"mode": "gate", "birth_share": 0.25}})
        self.assertEqual(Swarm.panel_status(SimpleNamespace(settings=self.settings, store=self.store)), {})
        self.assertEqual(dlane_report.panel_lane(self.root, self.settings), {})

    def test_a_job_found_running_at_a_wall_says_so_critically(self):
        """E4-SPEC 17: every E4 job asks `quiet` before it starts; nothing looked afterwards."""
        from league.ops import equity_universe as U
        from league.ops import registry

        times = iter([at(dt.date(2026, 10, 12), 9, 10), at(dt.date(2026, 10, 12), 9, 30)])   # 09:10 to 09:30 New York
        ctx = SimpleNamespace(now=lambda: next(times), alerts=[])
        ctx.alert = lambda level, text: ctx.alerts.append((level, text))
        out = U.watched("equity_panel", lambda c: {"ok": True, "calls": 3})(ctx)
        self.assertEqual(out, {"ok": True, "calls": 3, "wall": True})
        [(level, text)] = ctx.alerts
        self.assertEqual(level, "critical")
        self.assertIn("equity_panel: found RUNNING at a wall of the session (1200 s from its start)", text)
        quiet = SimpleNamespace(now=lambda: at(SUNDAY, 2, 30), alerts=[], alert=lambda *a: quiet.alerts.append(a))
        self.assertEqual(U.watched("x", lambda c: {"ok": True})(quiet), {"ok": True})
        self.assertEqual(U.watched("x", lambda c: {"status": "skipped", "why": "w"})(quiet), {"status": "skipped", "why": "w"})
        self.assertEqual(quiet.alerts, [])
        for name in E4_JOBS:                                     # every E4 job is run through the detector
            module = importlib.import_module(registry.by_name()[name].module)
            self.assertTrue(callable(getattr(module, "_run", None)), name)
            text = Path(module.__file__).read_text(encoding="utf-8")
            self.assertRegex(text, rf'watched\("{name}", _run\)', name)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheSeatOfASeatedPanelProgram(_Root):
    SWITCHES = {"elane": {"mode": "gate", "birth_share": 0.25, "panel": {"mode": "live"}}, "dlane": {"mode": "gate"}}

    def rows(self) -> dict[str, str]:
        return {r["family"]: r["band"] for r in bands.read(self.root, lanes=LANES)}

    def test_a_seated_panel_family_has_a_row_only_while_the_lane_is_live(self):
        self.family("rev-probe", band="probe")
        self.family("etf-probe", band="probe", structure="etf")
        families = EquityFamilies(self.root)
        self.assertEqual(elane_xs.seat_standing(self.root), (True, ""))
        self.assertEqual(self.rows(), {"rev-probe": "probe", "etf-probe": "probe"})
        self.assertIsNone(bands.equity_seat_withdrawn(self.root, self.store.family("rev-probe")))
        self.assertEqual(families.standing("rev-probe", 1)[0], "live")

        # A LEG OF live_ready FAILS (the night's I6): no row for the panel family, the ETF family's as before, and
        # the store's word is "held" with the leg named: E4-SPEC 17, ITS OPENS STOP AND ITS EXITS GO ON. The book
        # retires on "retired" and "demoted" alone (`families.GONE`), so one restated bar sells no basket.
        from league.equity.families import GONE, HELD

        self.assertNotIn(HELD, GONE)
        self.manifest(i6={"day": FRIDAY.isoformat(), "equal": False, "source": "fetch", "live": {}})
        self.assertEqual(self.rows(), {"etf-probe": "probe"})
        code, why = families.standing("rev-probe", 1)
        self.assertEqual(code, HELD)
        self.assertEqual(why, 'the panel lane is not live (its mode reads "gate"): the last nightly I6 did not hold '
                              "(the live ctx is not proved equal to the Gym's)")
        self.assertEqual(elane_xs.seat_standing(self.root), (None, why), "neither given nor taken away")
        self.assertEqual(elane_xs.seat_word(self.root), (elane_xs.SEAT_HELD, why))
        self.assertEqual(families.standing("etf-probe", 1)[0], "live", "an ETF family is asked nothing of the panel")
        self.assertIsNone(bands.equity_seat_withdrawn(self.root, self.store.family("etf-probe")))
        self.assertEqual(self.store.family("rev-probe")["band"], "probe", "its band in the store is not moved")

        # THE TWIN MARKER two sessions behind (package J's nightly run stopped): the same.
        self.manifest(i6={"day": FRIDAY.isoformat(), "equal": True, "source": "fetch", "live": {}})
        self.assertEqual(self.rows(), {"rev-probe": "probe", "etf-probe": "probe"}, "live again: its row is back")
        self.marker(dt.date(2026, 10, 7))
        self.assertEqual(self.rows(), {"etf-probe": "probe"})
        self.assertEqual(families.standing("rev-probe", 1),
                         (HELD, 'the panel lane is not live (its mode reads "gate"): the twin marker is behind the '
                                "panel store (the forward record's nightly run stopped)"))
        self.marker()
        # EVERY OTHER STORE-SIDE LEG is held the same way, whatever mode it lowers the lane to: the spreads' share
        # slipping under its bound (it decays by construction as members join), a coverage verdict, a manifest gone.
        whole = json.loads((self.store_root / "panel" / "PANEL_MANIFEST.json").read_text(encoding="utf-8"))
        for change, mode_reads in (({"hs_share": 0.899}, "train"), ({"verdict": "insufficient"}, "off"),
                                   ({"live_from": None}, "gate")):
            self.manifest(**change)
            self.assertEqual(elane_xs.mode(self.settings, self.root), mode_reads, change)
            self.assertEqual((self.rows(), families.standing("rev-probe", 1)[0]), ({"etf-probe": "probe"}, HELD), change)
            self.manifest(**{key: whole.get(key) for key in change})
        self.assertEqual(self.rows(), {"rev-probe": "probe", "etf-probe": "probe"})

        # THE SWITCHES, each step down, and E1's own above them.
        for layer, word in (({"panel": {"mode": "gate"}}, '"gate"): elane.panel.mode is set so'),
                            ({"panel": {"mode": "train"}}, '"train"): elane.panel.mode is set so'),
                            ({"panel": {"mode": "off"}}, '"off"): elane.panel.mode is set so'),
                            ({"mode": "off", "panel": {"mode": "live"}}, '"off"): the equity lanes are off (elane.mode)')):
            self.switch({"elane": {"mode": "gate", "birth_share": 0.25, **layer}})
            self.assertNotIn("rev-probe", self.rows(), layer)
            self.assertEqual(elane_xs.seat_standing(self.root),
                             (False, f"the panel lane is not live (its mode reads {word}"), layer)
            self.assertEqual(families.standing("rev-probe", 1)[0], "demoted", "only the captain's SWITCH demotes")
        # A SWITCH DOWN AND A LEG FAILED TOGETHER: the switch is positive evidence, whatever else reads.
        self.manifest(i6={"day": FRIDAY.isoformat(), "equal": False, "source": "fetch", "live": {}})
        self.assertEqual(families.standing("rev-probe", 1)[0], "demoted")

    def test_a_lane_that_cannot_be_read_gives_no_row_and_retires_nobody(self):
        self.family("rev-probe", band="probe")
        families = EquityFamilies(self.root)
        torn = {"the box's swarm.json": self.root / "swarm.json",
                "the panel manifest": self.store_root / "panel" / "PANEL_MANIFEST.json",
                "the twin marker": self.store_root / xbook.TWINS_FILE}
        for what, path in torn.items():
            whole = path.read_text(encoding="utf-8")
            path.write_text(whole[:len(whole) // 2], encoding="utf-8")          # a file caught mid-write
            self.forget()
            live, why = elane_xs.seat_standing(self.root)
            self.assertIsNone(live, what)
            self.assertTrue(why.startswith(f"{what} could not be read"), why)
            self.assertEqual(self.rows(), {}, f"{what}: no row, so no open")
            self.assertEqual(families.standing("rev-probe", 1)[0], "unknown", f"{what}: and nobody retired on it")
            path.write_text(whole, encoding="utf-8")
            self.forget()
            self.assertEqual(self.rows(), {"rev-probe": "probe"})
        # A LEG that cannot be read (the universe's own file): the mode reads "gate", as it always did (Validation and
        # looks go on; nobody is seated), `live_ready` says so, and the seat's word is "unknown".
        assets = self.store_root / "universe" / "assets.json"
        whole = assets.read_bytes()
        assets.write_bytes(whole[:100])
        self.forget()
        self.assertEqual(elane_xs.mode(self.settings, self.root), "gate")
        ready, why = elane_xs.live_ready(self.root, self.settings)
        self.assertEqual((ready, why[:30]), (False, "the live legs cannot be read ("))
        self.assertIsNone(elane_xs.seat_standing(self.root)[0])
        self.assertEqual((self.rows(), families.standing("rev-probe", 1)[0]), ({}, "unknown"))
        assets.write_bytes(whole)
        self.forget()
        self.assertEqual(self.rows(), {"rev-probe": "probe"})
        # A file that is GONE is the rule's own word, not a failed read: no marker, no seat; and a leg of the rule
        # (the twin marker's): held, with the leg named, never retired.
        (self.store_root / xbook.TWINS_FILE).unlink()
        self.forget()
        self.assertEqual(families.standing("rev-probe", 1),
                         ("held", 'the panel lane is not live (its mode reads "gate"): the twin marker is missing (the '
                                  "forward record's nightly run has not written it: package J)"))
        self.assertEqual(self.rows(), {})

    def test_the_proof_is_asked_before_the_seat(self):
        """A panel band whose proof is not the running files' identity is "retired" (an evidence release moved it),
        whatever the lane's mode: the seat's word never hides it."""
        fam = self.family("rev-probe", band="probe")
        self.store.set_state(fam["id"], banded_evaluator={**fam["state"]["banded_evaluator"], "xs_sha256": "0" * 64})
        self.switch({"elane": {"mode": "gate", "panel": {"mode": "gate"}}})
        self.assertEqual(EquityFamilies(self.root).standing("rev-probe", 1),
                         ("retired", "its band's proof is not the current equity identity"))


@unittest.skipUnless(HAVE, "numpy not installed")
class TheLaneStopsWhereItsRuleSays(_Root):
    SWITCHES = {"elane": {"mode": "gate", "birth_share": 0.25, "panel": {"mode": "live"}}, "dlane": {"mode": "gate"}}

    def test_without_the_twin_marker_live_reads_as_gate(self):
        self.assertEqual(elane_xs.mode(self.settings, self.root), "live")
        (self.store_root / xbook.TWINS_FILE).unlink()
        self.forget()
        self.assertEqual(elane_xs.mode(self.settings, self.root), "gate")
        ready, why = elane_xs.live_ready(self.root, self.settings)
        self.assertEqual((ready, why), (False, "the twin marker is missing (the forward record's nightly run has not "
                                               "written it: package J)"))
        self.family("rev-cand", band="candidate")
        self.assertEqual(bands.read(self.root, lanes=LANES), [], "a panel Candidate is seatless")

    def test_without_the_probes_panel_strata_no_look_runs_and_none_is_spent(self):
        """A22 (3): the contamination probe before a panel look. Release E3's probe has no panel strata until package
        B's patch 18 lands, so on the House every panel look WAITS (nothing spent) until then."""
        for strata in ((), ("P4", "P5")):                         # a permit with no panel stratum; and one short
            cells = self.probe["routes"][ROUTE]["cells"]
            doc = {**self.probe, "routes": {ROUTE: {**self.probe["routes"][ROUTE],
                                                    "cells": {k: v for k, v in cells.items() if k in strata}}}}
            (self.root / elane_xs.PROBE_FILE).write_text(json.dumps(doc), encoding="utf-8")
            self.forget()
            self.assertIsNotNone(elane_xs.probed(self.root, self.family(f"rev-{len(strata)}")), strata)
        (self.root / elane_xs.PROBE_FILE).write_text(json.dumps(self.probe), encoding="utf-8")
        self.forget()
        self.assertIsNone(elane_xs.probed(self.root, self.store.family("rev-0")))
        self.assertEqual(elane_xs.MAX_CELL_LOOKS, 2, "A22 (2): two looks an agenda cell until a forward verdict")


@unittest.skipUnless(HAVE, "numpy not installed")
class TheDataJobsOnTheRealStore(unittest.TestCase):
    """Package B's jobs were built against fakes of package C's store (C was a stub at their base). Here each runs on
    C's REAL universe and panel (a synthetic one), and package A's and the twins' readers read the files they leave."""

    def setUp(self):
        from league.ops.context import Context
        from league.tests.test_equity_spreads import Quotes

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.root = synth.synthetic_panel(self.state / elane_xs.STORE_DIR, n_assets=40, gate=True)
        (self.state / "swarm.json").write_text('{"elane": {"panel": {"mode": "train"}}}', encoding="utf-8")   # the lane's switch is up
        self.now = at(SUNDAY, 2, 30)                               # a Sunday night: no wall is near
        self.gateway = Quotes(bp=lambda symbol, start: 4.0 + len(symbol))
        self.ctx = lambda name: Context(name, root=self.state, due_at=self.now, clock=lambda: self.now,
                                        gateway=self.gateway, config={}, settings_value={})

    def test_the_spreads_job_fills_the_table_the_panel_job_and_the_twins_read(self):
        from league.equity.store import nyse_sessions
        from league.ops import equity_panel, equity_spreads
        from league.xs import store as xstore

        out = equity_spreads.run(self.ctx("equity_spreads"), sleep=lambda seconds: None)
        self.assertEqual((out["ok"], out["done"], out["remaining"], out["errors"], out["refused"]), (True, True, 0, 0, 0), out)
        self.assertEqual({call["path"] for call in self.gateway.calls}, {equity_spreads.QUOTES})
        years = {int(call["start"][:4]) for call in self.gateway.calls}
        self.assertEqual(years, set(xconfig.TRAIN_YEARS), "a Train-era session only: never the reserve, never 2025-26")
        panel = equity_panel.load_panel(self.root)
        table = equity_panel.hs_table(self.root, panel.aids)
        self.assertEqual(table.shape, (len(panel.aids), 2))
        self.assertTrue(((table >= xconfig.HS_FLOOR_BP / 1e4) & (table <= xconfig.HS_MAX_BP / 1e4)).all())
        universe = xstore.Universe(self.root)
        today = [aid for aid, _ in universe.members(FRIDAY)]
        # A name is sampled on a sample day only while it is a member, so the names with 8 samples at both points
        # are exactly those that were members on 8 Train-era sample days: every later joiner is charged the
        # universe's figure, and of TODAY'S members the measured share is under one and falls with every change of
        # the index (E4_INTERFACES section 10, point 10).
        days = [d for year in equity_spreads.sample_days(nyse_sessions(dt.date(2016, 1, 4), FRIDAY)).values() for d in year]
        sampled = [aid for aid in today if sum(1 for d in days if universe.member(aid, d)) >= equity_panel.MIN_SAMPLES]
        late = sorted(set(today) - set(sampled))
        self.assertTrue(late and all(not universe.member(aid, days[-equity_panel.MIN_SAMPLES]) for aid in late))
        self.assertTrue(0.5 < len(sampled) / len(today) < 1.0)
        # THE SPREADS' SHARE the lane's bound reads is of the Train eras' member-days (the sessions the samples are
        # for): on this store, whose backfill is whole, it is the share of those member-days whose name was a member
        # on 8 sample days, and it is over the share of today's members: no joiner since 2024 is in it.
        import numpy as np

        members = [int(a) for a in panel.aids[len(xconfig.REF):]]
        member = np.asarray(panel.member)[:, len(xconfig.REF):]
        share = equity_panel.hs_share(self.root, member, panel.days, members)
        train = [i for i, d in enumerate(panel.days) if d.year in xconfig.TRAIN_YEARS]
        full = {aid for aid in members if sum(1 for d in days if universe.member(aid, d)) >= equity_panel.MIN_SAMPLES}
        owed = int(member[train].sum())
        measured = int(sum(member[train, k].sum() for k, aid in enumerate(members) if aid in full))
        self.assertEqual(share, measured / owed)
        self.assertGreater(share, len(sampled) / len(today))
        self.assertGreater(share, 0.9)
        # The twins' reader (package B's patch 11): a panel lot's half-spreads at the open and at the close.
        reader = equity_spreads.panel_half_spread(self.root)
        got = reader(universe.symbol(sampled[0], FRIDAY), FRIDAY.isoformat())
        self.assertEqual(len(got), 2)
        self.assertTrue(all(xconfig.HS_FLOOR_BP / 1e4 <= x <= xconfig.HS_MAX_BP / 1e4 for x in got), got)
        self.assertIsNone(reader("NOSUCH", FRIDAY.isoformat()))

    def test_the_neff_job_measures_the_real_panel_and_the_french_job_is_skipped_with_no_route(self):
        from league.ops import equity_neff, french

        out = equity_neff.run(self.ctx("equity_neff"))
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["panel"], "sp500")
        self.assertTrue(1.0 < out["neff_pr"] <= out["names"] <= 40, out)
        kept = json.loads((self.root / equity_neff.FILE).read_text(encoding="utf-8"))["sp500"]
        self.assertEqual((kept["neff_pr"], kept["names"], kept["coverage"]), (out["neff_pr"], out["names"], "ok"))
        self.assertEqual(self.gateway.calls, [], "it reads the store and asks the venue nothing")
        self.assertEqual(french.run(self.ctx("french"))["status"], "skipped")


@unittest.skipUnless(HAVE, "numpy not installed")
class TheLiveColumnsOnTheRealUniverse(unittest.TestCase):
    """Package H's adapter was built against doubles of package C's universe and store. Here its columns are built on
    C's REAL ones: the eligibility a live decision reads is the store's own, the class of the month included (the
    nightly I6 compares bars and leaves the class rule out), and a held name that left the index keeps its column."""

    @classmethod
    def setUpClass(cls):
        from league.equity.store import mint_equity_gate_capability
        from league.ops import equity_panel
        from league.xs import store as xstore

        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = synth.synthetic_panel(Path(cls.tmp.name) / "equity-daily", n_assets=40, gate=True,
                                         live_from=dt.date(2026, 9, 1))
        cls.panel = equity_panel.load_panel(cls.root)
        cls.store = xstore.PanelStore(cls.root, gate=mint_equity_gate_capability(cls.root, reason="a test reads 2025-26"))
        cls.assets = json.loads((cls.root / "universe" / "assets.json").read_text(encoding="utf-8"))

    def test_the_live_eligibility_is_the_stores_own_with_the_class_of_the_month(self):
        import numpy as np

        from league.equity import store as estore

        ref = len(xconfig.REF)
        column = {aid: k for k, aid in enumerate(self.panel.aids)}
        chosen = set()
        for t in range(len(self.panel.days) - 420, len(self.panel.days), 7):     # twenty months: the choice flips
            day = self.panel.days[t]
            cols = xbook.columns(self.root, "fam@1:r", day)
            take = [column[int(aid)] for aid in cols.aids]
            first = t - (xconfig.DERIVE_SESSIONS - 1)
            fetched = xbook.Fetched(days=np.array([estore.ordinal(d) for d in self.panel.days[first:t + 1]], dtype=np.int32),
                                    raw=np.asarray(self.panel.raw[first:t + 1][:, take]),
                                    all=np.asarray(self.panel.adj[first:t + 1][:, take]), meta={})
            aids = [int(aid) for aid in cols.aids[ref:]]
            live = np.asarray(xbook.eligible(cols, fetched, day), dtype=bool)[ref:]
            gym = np.asarray(self.store.elig0_row(day, aids), dtype=bool)
            self.assertEqual(live.tolist(), gym.tolist(), day)
            # Before the class rule the adapter's row differs from the store's by the month's other class alone.
            before = np.asarray(cols.elig0, dtype=bool)[ref:]
            out = set(self.store.class_out(day))
            self.assertEqual({aid for aid, a, b in zip(aids, before, gym) if a != b}, out, day)
            chosen |= out
        self.assertEqual(len(chosen), 2, "both classes of the pair were the month's other class at some time")

    def test_a_held_name_that_left_the_index_keeps_a_column_and_is_no_candidate(self):
        from league.equity.store import nyse_sessions

        aid, spell = max(((int(aid), row["spells"][-1]) for aid, row in self.assets.items()
                          if not row.get("ref") and row["spells"][-1][2]), key=lambda item: item[1][2])
        symbol, left = spell[0], dt.date.fromisoformat(spell[2])
        day = [d for d, _ in nyse_sessions(left, left + dt.timedelta(days=10))][1]     # the session after it left
        for held in ({symbol: (left - dt.timedelta(days=20)).isoformat()}, [symbol]):
            cols = xbook.columns(self.root, "fam@1:r", day, held=held)
            self.assertEqual(cols.extra, (symbol,))
            at_ = cols.symbols.index(symbol)
            self.assertEqual((int(cols.aids[at_]), bool(cols.elig0[at_])), (aid, False))
        self.assertNotIn(symbol, xbook.columns(self.root, "fam@1:r", day).symbols, "not held: no column")
        with self.assertRaises(xbook.ColumnsRefused):
            xbook.columns(self.root, "fam@1:r", day, held=["NOSUCH"])


@unittest.skipUnless(HAVE, "numpy not installed")
class TheSeams(unittest.TestCase):
    def test_the_committed_receipt_is_pinned_whole_and_its_sentence_fills(self):
        """The receipt in the tree is the one policy.json pins (its sha256 and every pinned figure), it loads under
        the screen's own bounds, and every threshold a look reads is the receipt's (no figure of it is in a test)."""
        path = REPO / xscreen.RECEIPT_PATH
        policy = json.loads(REAL_POLICY_PATH.read_text(encoding="utf-8"))
        block = policy["elane"]["screens"]["equity_xs"]
        self.assertEqual(block, xscreen.pin(path))
        self.assertEqual(block["receipt_sha256"], xscreen.receipt_sha256(path))
        loaded = xscreen.load_receipt(path, pinned_sha256=block["receipt_sha256"])
        pinned = xscreen.pinned_receipt(block)
        self.assertEqual((loaded.c_XS, loaded.rung, loaded.placebo_draws), (pinned.c_XS, pinned.rung, pinned.placebo_draws))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["c_XS"], block["c_XS"])
        with mock.patch.object(settings_mod, "POLICY_PATH", REAL_POLICY_PATH):
            got, why = elane_xs.receipt()
        self.assertIsNone(why)
        self.assertEqual(got.receipt_sha256, block["receipt_sha256"])
        for field in xscreen.BESIDE_FIELDS:
            self.assertIn("{" + field + "}", block["beside"], "the House fills each placeholder beside a live trade")

    def test_the_vendors_cents_are_one_bound_for_both_lanes(self):
        self.assertIs(xconfig.rounding_bound, econfig.rounding_bound)
        self.assertEqual((xconfig.ADJUSTED_HALF_STEP, xconfig.ROUNDING_GUARD),
                         (econfig.ADJUSTED_HALF_STEP, econfig.ROUNDING_GUARD))
        from league.xs import engine as xengine

        self.assertTrue(xengine._E1_SPLIT_TOLERANCE, "the panel engine reads a split with E1's own tolerance-aware rule")

    def test_the_ops_jobs_know_the_panel_as_an_equity_structure(self):
        self.assertEqual(stall.EQUITY_STRUCTURES, store_mod.EQUITY_STRUCTURES)
        self.assertEqual(stall.OPTIONS_FAMILIES, store_mod.OPTIONS_ONLY_SQL)
        literal = re.compile(r"""['"]etf['"]\s*,\s*['"]stock['"]""")
        found = set()
        for path in sorted((REPO / "league" / "ops").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docs = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Expr)}   # docstrings: prose
            for node in ast.walk(tree):
                if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
                    words = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                    if "etf" in words and "stock" in words:
                        found.add(path.name)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs \
                        and literal.search(node.value):
                    found.add(path.name)
        # The stall job spells the equity structures out in code, held to the store's above. Release E3's forward
        # record spells out ITS OWN two, on purpose narrower: it registers ETF and stock programs and counts their
        # runs (the registry's `STRUCTURES`; the report's replay multiple, which names the panel beside them since
        # package J); a panel program's forward row and shadow are package J's own reader's (league/ops/forward_xs.py:
        # it spells no structure, it asks the panel lane). No other ops job names the structures.
        self.assertEqual(sorted(found), ["forward_register.py", "forward_report.py", "stall.py"])
        from league.ops import forward_register

        self.assertEqual(forward_register.STRUCTURES, tuple(s for s in store_mod.EQUITY_STRUCTURES if s != "panel"),
                         "the forward record's structures are the store's less the panel (package J's)")

    def test_the_two_hidden_year_rotations_never_move_each_other(self):
        """Release E3's fold beside the panel lane's (league/xs/E4_INTERFACES.md, "for release E3's integrator"): a
        panel family carries a hidden year of ITS lane's draw (six Train years, counted over panel families alone),
        an ETF family one of E3's (seven, counted over the others). Read as E2's facts a panel family names no symbol
        and an agenda E2 does not know, so it would stand in E2's cell (lane, "other", "none"): `elane_folds.born`
        counts none there, and `elane_xs.assign` counts no ETF family."""
        from league.swarm import elane_folds, elane_seal, elane_train

        with tempfile.TemporaryDirectory() as tmp:
            store = SwarmStore(Path(tmp), clock=Clock(at(SUNDAY, 12, 0)))
            self.addCleanup(store.close)
            recording = {"elane": {"memory": {"mode": "record"}}}
            panel_cell = elane_xs.cell_of("equity", "xs_reversal", "sp500")
            first = elane_xs.assign(store, panel_cell, recording)
            self.assertEqual(first, xconfig.TRAIN_YEARS[elane_folds.cell_hash(panel_cell) % len(xconfig.TRAIN_YEARS)])
            self.assertIsNone(elane_xs.assign(store, panel_cell, {"elane": {"memory": {"mode": "off"}}}))
            fam = store.add_family({"id": "rev-a", "mechanism": PROPOSAL["mechanism"], "structure": "panel", "roots": [],
                                    "lane": "equity", "agenda": "xs_reversal", "panel": "sp500", "max_names": 5,
                                    "rebalance": "weekly", "weekday": 0, "e2_route": ROUTE, "hidden_year": first,
                                    "gid": elane_folds.GID0}, origin="architect")
            self.assertEqual(elane_folds.hidden_year(fam), first, "one of E3's work years too: read as any spec's")
            facts = elane_seal.train_facts(fam, elane_train.STATE_KEY)
            as_e2 = elane_train.cell_of(facts["lane"], facts["agenda"], facts["symbols"])
            self.assertEqual(as_e2, ("equity", "other", "none"))
            self.assertEqual(elane_folds.born(store, as_e2), 0, "E3's count holds no panel family")
            self.assertEqual(elane_folds.assign(store, as_e2),
                             elane_folds.WORK_YEARS[elane_folds.cell_hash(as_e2) % len(elane_folds.WORK_YEARS)])
            # The panel's own count does hold it: the cell's next panel family draws the next of the six years.
            second = elane_xs.assign(store, panel_cell, recording)
            self.assertEqual(second, xconfig.TRAIN_YEARS[(1 + elane_folds.cell_hash(panel_cell)) % len(xconfig.TRAIN_YEARS)])
            # An ETF family with a hidden year moves E3's count of ITS cell and not the panel's.
            etf = store.add_family({"id": "ovn-a", "mechanism": "Index holders are paid for overnight risk.",
                                    "structure": "etf", "roots": ["SPY"], "lane": "beta", "symbols": ["SPY"],
                                    "agenda": "other", "hidden_year": 2018, "gid": elane_folds.GID0}, origin="architect")
            facts = elane_seal.train_facts(etf, elane_train.STATE_KEY)
            self.assertEqual(elane_folds.born(store, elane_train.cell_of(facts["lane"], facts["agenda"], facts["symbols"])), 1)
            self.assertEqual(elane_xs.assign(store, panel_cell, recording), second)

    def test_what_the_lane_reads_of_release_e3_keeps_e3s_seal(self):
        """The panel lane was built before E3 was merged and read two of E3's files by name. One reader is an ops
        job (the funnel's asset-years read the forward report's N_eff: league/ops, where E3 lets its files be
        named). The other was the SWARM's (the look's gate, the captain's A22 (3), read the probe's own file), which
        E3's seal forbids: no module of league/swarm names a file of the forward record or the probe's, nor imports
        an E3 ops module. So the swarm reads a PERMIT the probe's job writes (two words a stratum and era); the
        probe's own file opens no look, whatever it holds; and the probe's strata do not yet hold the panel's
        (package B's patch to the probe, owed), so no permit exists and every panel look waits."""
        from league.ops import contam_probe, equity_neff, forward_db, forward_report
        from league.tests import test_e3_seal_imports as seal

        self.assertEqual(equity_neff.FORWARD_REPORT, forward_report.FILE)
        self.assertIn("cey", forward_report.SECTION_KEYS)
        self.assertIn("hist_iy REAL", " ".join(forward_db.SCHEMA.split()), "the report's `cey` is a row of fwd_cey")
        self.assertNotIn(elane_xs.PROBE_FILE, seal.NAMES)
        self.assertNotEqual(elane_xs.PROBE_FILE, contam_probe.FILE)
        self.assertEqual(seal.named(REPO, "league/swarm", seal.NAMES, pattern=r"\bfwd_[a-z0-9_]+"), [])
        self.assertEqual(seal.e3_ops_imports(REPO, "league/swarm"), [])
        self.assertEqual(set(elane_xs.PROBE_STRATA) & set(contam_probe.STRATA), set(),
                         "the day the probe carries the panel strata it writes the permit, and a look may be taken")
        fam = {"spec": {"e2_route": ROUTE}}
        with tempfile.TemporaryDirectory() as tmp:
            cells = {s: {"2016-24": {"readable": True, "recalled": False}} for s in elane_xs.PROBE_STRATA}
            row = {"at": "2026-10-10T00:20:00Z", "model": "fake-model", "cells": cells}
            # The probe's own file, panel strata and all, at its own name: never read, the look waits.
            (Path(tmp) / contam_probe.FILE).write_text(json.dumps(
                {"version": contam_probe.VERSION, "history": [], "routes": {ROUTE: row}}), encoding="utf-8")
            self.assertIn("no published result", elane_xs.probed(tmp, fam))
            # The same text under the permit's name is no permit either (another version).
            (Path(tmp) / elane_xs.PROBE_FILE).write_text(json.dumps(
                {"version": contam_probe.VERSION, "routes": {ROUTE: row}}), encoding="utf-8")
            self.assertIn("no published result", elane_xs.probed(tmp, fam))
            # The permit: every panel stratum published for the route.
            (Path(tmp) / elane_xs.PROBE_FILE).write_text(json.dumps(
                {"version": elane_xs.PROBE_VERSION, "routes": {ROUTE: row}}), encoding="utf-8")
            self.assertIsNone(elane_xs.probed(tmp, fam))
            # Whatever else a permit carried, the swarm keeps the two words and nothing else.
            row["cells"]["P4"]["2016-24"].update(acc=0.61, base=0.55, n=40)
            (Path(tmp) / elane_xs.PROBE_FILE).write_text(json.dumps(
                {"version": elane_xs.PROBE_VERSION, "routes": {ROUTE: row}}), encoding="utf-8")
            self.assertEqual(elane_xs.probe_reading(tmp, ROUTE)["strata"]["P4"],
                             {"2016-24": {"readable": True, "recalled": False}})

    def test_no_stub_is_left_on_a_built_path(self):
        left = []
        for path in [*sorted((REPO / "league" / "xs").glob("*.py")), REPO / "league" / "swarm" / "elane_xs.py",
                     REPO / "scripts" / "gen_universe.py", REPO / "scripts" / "panel_probe.py",
                     *(REPO / "league" / "ops" / f"{name}.py" for name in E4_JOBS)]:
            text = path.read_text(encoding="utf-8")
            if re.search(r"raise NotImplementedError|^_STUB\b", text, flags=re.M):
                left.append(path.name)
        self.assertEqual(left, [])


if __name__ == "__main__":
    unittest.main()
