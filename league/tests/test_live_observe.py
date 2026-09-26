"""The observe band (the sprint, B4, Sept 26, 2026): every alive Gym-band family's validated version trades live shadow,
pinned for the session, never real, never a forward row, never on the site; its programs in their own decider child.
With the fakes of `live_fakes` (the venue's shapes, invented numbers) and the in-process decider."""

import datetime as dt
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.live.decider import DeciderError, InlineDecider
    from league.live.families import MemoryFamilies, SwarmFamilies, _entry_matches
    from league.live.step import OptionsLive
    from league.tests.live_fakes import MONDAY, VERTICAL, at, family

TUESDAY = MONDAY + dt.timedelta(days=1)


def observed(name, *, version=1, t=1.0, params=None, code=None):
    return {"family": name, "version": version, "code": code or VERTICAL, "params": dict(params or {"hold": 600}),
            "structure": "debit_vertical", "roots": ["SPY"], "run_sha": f"sha-{name}-{version}", "validation_t": t,
            "validated_version": version}


@unittest.skipUnless(HAVE, "numpy not installed")
class ObserveCase(LiveCase):
    def switches(self, **live):
        (self.root / "swarm.json").write_text(json.dumps({"live": {"calibration": False, **live}}))

    def restart(self, **kw):
        """A new House process on the same state root and the same swarm."""
        self.live.state.close()
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=kw.get("decider") or InlineDecider(),
                                config={"require_paper_proof": False}, real_money=kw.get("real_money", False),
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        return self.live


class TheBand(ObserveCase):
    def test_every_validated_gym_family_trades_shadow_only_and_never_reaches_the_forward_record(self):
        live = self.make([], observed=[observed("obs", params={"hold": 3})])
        self.run_to(9, 45)
        inst = live.instances["obs@1:o"]
        self.assertEqual((inst.kind, inst.observe, inst.tuition, inst.band), ("shadow", True, False, "gym"))
        acc = live.shadow.accounts["obs@1:o"]
        self.assertTrue(acc.trades, "it traded the shadow book on live quotes")
        self.assertEqual(self.venue.sent, [], "never real")
        self.assertEqual(self.families.forward, {}, "never a forward row")
        self.assertEqual(self.families.moves, [], "never a band move")
        self.assertEqual(acc.new_trades(), [], "its trades are consumed, not kept to be sent")
        self.assertTrue(live.health()["instances"]["obs@1:o"]["observe"])
        self.assertEqual(live.state.get("observe_pins")["versions"], {"obs": 1})

    def test_the_site_never_shows_an_observe_structure(self):
        live = self.make([family("vert", VERTICAL, band="candidate", params={"hold": 600})],
                         observed=[observed("obs")], real_money=False)
        self.run_to(9, 36)
        self.assertTrue(live.shadow.accounts["obs@1:o"].positions)
        agents = {row["agent"] for row in live.site_inputs()["structures"]}
        self.assertEqual(agents, {"vert"})

    def test_a_family_never_validated_has_no_instance_until_it_is(self):
        live = self.make([], observed=[])
        self.run_to(9, 33)
        self.assertFalse([k for k in live.instances if k.endswith(":o")])
        self.families.observed["late"] = {1: dict(observed("late"), observe=True, band="gym")}
        self.clock.set(self.clock() + 300)
        live.minute()
        self.assertIn("late@1:o", live.instances, "validated mid-session: it joins, its version pinned from then")


class Pins(ObserveCase):
    def test_the_version_is_pinned_for_the_session_across_a_restart_and_moves_at_the_next_session(self):
        live = self.make([], observed=[observed("obs")])
        self.run_to(9, 33)
        self.assertIn("obs@1:o", live.instances)
        before = dict(live.shadow.accounts["obs@1:o"].positions)
        self.assertTrue(before)
        self.families.observed["obs"][2] = dict(observed("obs", version=2), observe=True, band="gym")
        live.sync_families(self.clock(), force=True)
        self.assertEqual(sorted(k for k in live.instances if k.endswith(":o")), ["obs@1:o"], "pinned for the session")
        live = self.restart()
        self.clock.set(self.clock() + 60)
        live.minute()
        self.assertEqual(sorted(k for k in live.instances if k.endswith(":o")), ["obs@1:o"],
                         "a restart keeps the session's pin (the live state), not the swarm's newer version")
        self.assertEqual(set(live.shadow.accounts["obs@1:o"].positions), set(before), "and its shadow book")
        self.clock.set(at(TUESDAY, 9, 31))
        live.minute()
        self.assertIn("obs@2:o", live.instances, "the next session pins the current validated version")
        self.assertEqual(live.instances["obs@1:o"].mode, "wind_down")
        self.clock.set(at(TUESDAY, 9, 40))
        for _ in range(3):
            live.minute()
            self.clock.set(self.clock() + 60)
        self.assertNotIn("obs@1:o", live.instances)
        self.assertNotIn("obs@1:o", live.shadow.accounts)
        self.assertEqual(self.families.forward, {})

    def test_retirement_winds_the_instance_down(self):
        live = self.make([], observed=[observed("obs")])
        self.run_to(9, 34)
        self.assertTrue(live.shadow.accounts["obs@1:o"].positions)
        del self.families.observed["obs"]                                  # retired (or promoted out of the Gym band)
        live.sync_families(self.clock(), force=True)
        self.assertEqual(live.instances["obs@1:o"].mode, "wind_down")
        self.run_to(9, 40)
        self.assertNotIn("obs@1:o", live.instances)
        self.assertNotIn("obs@1:o", live.shadow.accounts)
        self.assertEqual(live.state.get("observe_pins")["order"], [])
        self.assertEqual(self.families.forward, {})
        self.assertEqual(self.venue.sent, [])

    def test_the_cap_holds_the_likeliest_and_says_which_it_held_back(self):
        self.switches(observe_max=2)
        live = self.make([], observed=[observed("a", t=1.0), observed("b", t=3.0), observed("c", t=2.0)])
        self.run_to(9, 32)
        self.assertEqual(sorted(k for k in live.instances if k.endswith(":o")), ["b@1:o", "c@1:o"])
        [(record, _)] = self.ledger.of("live.observe")
        self.assertEqual(record["capped"], ["a"])
        self.run_to(9, 40)
        self.assertEqual(len(self.ledger.of("live.observe")), 1, "said once a day")
        # Lowered at runtime (no deploy): the first pinned stay. The switches are read once a minute pass; the families
        # every five minutes (here at once).
        self.switches(observe_max=1)
        live._switches = None
        live.sync_families(self.clock(), force=True)
        self.assertEqual(live.instances["c@1:o"].mode, "wind_down")
        self.assertEqual(live.instances["b@1:o"].mode, "live")

    def test_the_switch_turns_it_off_and_on_without_a_deploy(self):
        self.switches(observe=False)
        live = self.make([], observed=[observed("obs")])
        self.run_to(9, 33)
        self.assertFalse([k for k in live.instances if k.endswith(":o")])
        self.switches(observe=True)
        self.run_to(9, 34)
        self.assertIn("obs@1:o", live.instances, "the first minute after it is switched on pins it")
        self.switches(observe=False)
        self.run_to(9, 39)                                                   # the next families pass (every five minutes)
        self.assertEqual(live.instances["obs@1:o"].mode, "wind_down")

    def test_a_malformed_switch_is_off_and_a_malformed_cap_is_the_default(self):
        (self.root / "swarm.json").write_text(json.dumps({"live": {"observe": "true", "observe_max": "lots", "calibration": 1}}))
        live = self.make([])
        sw = live.switches()
        self.assertEqual((sw["observe"], sw["observe_max"], sw["calibration"]), (False, 48, False))


class NeverACandidate(ObserveCase):
    def test_an_observe_row_admits_only_an_observe_shadow_open(self):
        row = dict(observed("obs"), observe=True, band="gym")
        ident = {"family": "obs", "version": 1, "code": VERTICAL, "params": {"hold": 600}, "band": "gym", "tuition": False,
                 "observe": True}
        self.assertTrue(_entry_matches(row, ident, False))
        self.assertFalse(_entry_matches(row, ident, True), "never real")
        self.assertFalse(_entry_matches(row, dict(ident, tuition=True), False), "never tuition")
        self.assertFalse(_entry_matches(row, dict(ident, observe=False), False), "an observe row is no Candidate's row")
        cand = dict(row, observe=False, band="candidate")
        self.assertFalse(_entry_matches(cand, ident, False), "a Candidate's row admits no observe instance")
        self.assertFalse(_entry_matches(dict(row, band="candidate"), ident, False), "promoted: it leaves the band")
        families = MemoryFamilies([], [observed("obs")])
        with families.admit_open(ident, real=True) as allowed:
            self.assertFalse(allowed)
        with families.admit_open(ident, real=False) as allowed:
            self.assertTrue(allowed)
        with families.admit_open(dict(ident, version=2), real=False) as allowed:
            self.assertFalse(allowed, "only the pinned version's program")


class OwnChild(ObserveCase):
    def test_observe_programs_run_in_their_own_child_after_the_real_orders_went(self):
        main, other = InlineDecider(), InlineDecider()
        seen = []
        decide = other.decide

        def watched(*args, **kwargs):
            seen.append(len(self.venue.sent))
            return decide(*args, **kwargs)

        other.decide = watched
        self.families = MemoryFamilies([family("vert", VERTICAL, band="probe")], [observed("obs")])
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=main, observe_decider=other,
                                config={"require_paper_proof": False}, real_money=True,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        self.run_to(9, 33)
        self.assertIn("obs@1:o", other.loaded)
        self.assertNotIn("obs@1:o", main.loaded)
        self.assertIn("vert@1:r", main.loaded)
        self.assertTrue(seen)
        self.assertEqual(seen[0], 1, "the minute's real open had gone before the observe band was asked")

    def test_a_failing_observe_child_never_costs_a_real_decision(self):
        main, other = InlineDecider(), InlineDecider()

        def broken(*args, **kwargs):
            raise DeciderError("an observe program hung; the child was killed")

        other.decide = broken
        self.families = MemoryFamilies([family("vert", VERTICAL, band="probe")], [observed("obs")])
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=main, observe_decider=other,
                                config={"require_paper_proof": False}, real_money=True,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        out = self.run_to(9, 33)
        self.assertEqual(len(self.venue.sent), 1)
        self.assertTrue(any("the observe band" in text for _, text in self.alerts))
        self.assertIn("observe_decider", out)
        self.assertNotIn("decider", out)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheSwarmsStore(unittest.TestCase):
    """`bands.observe` and `SwarmFamilies` against the swarm's real store."""

    def setUp(self):
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock as SwarmClock

        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.store = SwarmStore(self.root, clock=SwarmClock())

    def tearDown(self):
        self.store.close()
        self.dir.cleanup()

    def add(self, fid, *, validated=True, t=1.0, versions=1):
        self.store.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": "debit_vertical",
                               "roots": ["SPY"], "dte": [0, 2]}, origin="test")
        for n in range(versions):
            self.store.add_version(fid, f"# {fid} v{n + 1}\n" + VERTICAL, {"hold": 600}, author="test")
        if validated:
            self.store.set_state(fid, validation_version=versions, validation_line={"passed": False},
                                 validation_numbers={"t": t})

    def test_only_alive_gym_families_with_a_validated_version_and_never_as_candidates(self):
        from league.swarm import bands

        self.add("gym-a", t=0.5)
        self.add("gym-b", t=2.5, versions=2)
        self.add("never", validated=False)
        self.add("cand")
        self.store.set_state("cand", banded_version=1)
        self.store.set_band("cand", "candidate", reason="passed")
        self.add("dead")
        self.store.retire_gym("dead", "finished", floor=0, source="test")
        rows = bands.observe(self.root)
        self.assertEqual([r["family"] for r in rows], ["gym-b", "gym-a"], "the likeliest first; alive, Gym, validated")
        b = rows[0]
        self.assertEqual((b["version"], b["band"], b["observe"], b["holdout_passed"], b["validation_passed"]),
                         (2, "gym", True, False, False))
        self.assertIn("gym-b v2", b["code"])
        [pinned] = bands.observe(self.root, family="gym-b", version=1)
        self.assertIn("gym-b v1", pinned["code"])
        self.assertEqual(bands.observe(self.root, family="cand", version=1), [], "a Candidate is never an observe row")
        self.assertEqual([r["family"] for r in bands.read(self.root)], ["cand"], "and observe rows never reach read()")
        families = SwarmFamilies(self.root)
        ident = {"family": "gym-b", "version": 1, "code": pinned["code"], "params": pinned["params"], "band": "gym",
                 "tuition": False, "observe": True}
        with families.admit_open(ident, real=False) as allowed:
            self.assertTrue(allowed, "the pinned version, while the family is alive in the Gym band")
        with families.admit_open(ident, real=True) as allowed:
            self.assertFalse(allowed)
        self.store.retire_gym("gym-b", "finished", floor=0, source="test")
        with families.admit_open(ident, real=False) as allowed:
            self.assertFalse(allowed, "retired: no more opens")
        if families._store is not None:
            families._store.close()


@unittest.skipUnless(HAVE, "numpy not installed")
class Capacity(ObserveCase):
    """The House box is size s: one minute's budget is 40 s (`decider.MAX_BATCH_SECONDS`), shared by the minute's loads
    and decisions. 48 observe instances (the default `live.observe_max`), each deciding every minute, on the swarm's real
    store: every minute well inside it, the Gym bundle built once, and the 49th family held back by the cap."""

    def test_forty_eight_observe_instances_fit_in_a_minute(self):
        from league.swarm import bands
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock as SwarmClock
        import league.gym.driver as driver

        store = SwarmStore(self.root, clock=SwarmClock())
        self.addCleanup(store.close)
        for i in range(49):
            fid = f"obs-{i:02d}"
            store.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": "debit_vertical",
                              "roots": ["SPY"], "dte": [0, 2]}, origin="test")
            store.add_version(fid, f"# {fid}\n" + VERTICAL, {"hold": 5, "opens": 3}, author="test")
            store.set_state(fid, validation_version=1, validation_numbers={"t": float(i)})
        self.live = self.make([], real_money=False)
        self.families = self.live.families = SwarmFamilies(self.root)
        self.addCleanup(lambda: self.families._store.close() if self.families._store is not None else None)
        built = []
        real_build = driver.build_bundle

        def counted(*args, **kwargs):
            built.append(1)
            return real_build(*args, **kwargs)

        bands._bundle_cache = None
        seconds = []
        with patch("league.gym.driver.build_bundle", counted):
            for _ in range(12):
                began = time.monotonic()
                self.live.minute()
                seconds.append(time.monotonic() - began)
                self.clock.set(self.clock() + 60)
        bands._bundle_cache = None
        observing = [k for k, i in self.live.instances.items() if i.observe and i.mode == "live"]
        self.assertEqual(len(observing), 48)
        self.assertNotIn("obs-00@1:o", observing, "the 49th (the least likely) is held back by the cap")
        decided = sum(1 for acc in self.live.shadow.accounts.values() if acc.trades or acc.positions)
        self.assertEqual(decided, 48, "every one of them traded the shadow book")
        self.assertLessEqual(len(built), 1, "the Gym bundle is built once, not per instance per minute")
        # The first minute loads 48 programs; every minute after decides 48. Far inside the 40 s budget (CI's machines
        # are slower than a laptop, so the bound is generous: the measured figures are printed in the failure).
        self.assertLess(seconds[0], 25.0, seconds)
        self.assertLess(max(seconds[1:]), 15.0, seconds)


if __name__ == "__main__":
    unittest.main()
