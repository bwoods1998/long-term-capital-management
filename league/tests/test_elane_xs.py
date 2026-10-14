"""THE PANEL LANE in the swarm (release E4; league/swarm/elane_xs.py): its settings and effective mode, the live legs,
cards and agenda cells, the panel quota and the hidden year, a panel version's ONE Validation try (both Train series
kept before it, the lineage asked before it), the ONE sealed look under XS1, and the seals this package owes:
X10 (no receipt, no look), X16 (a panel lineage has one try; no structure literal outside the store) and X17 (a panel
band is current only under the running code); and the captain's A22 as the House holds it: a style-open passer takes
no band, two looks an agenda cell, the review and the contamination probe before a look. league.xs is faked at its
interfaces (league/tests/elane_xs_fakes.py); every family, program and number is invented."""

from __future__ import annotations

import datetime as dt
import ast
import hashlib
import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from league.equity import LANES
from league.equity.store import STORE_DIR
from league.swarm import bands, elane, elane_seal, elane_xs
from league.swarm import store as store_mod
from league.swarm.gate import Gate, run_sha
from league.swarm.tournament import Tournament
from league.tests import elane_xs_fakes as F
from league.xs import config as xconfig
from league.xs import screen as xscreen

#: The quiet rule itself (the fakes replace `xconfig.quiet` with the world's own answer for a test's life).
REAL_QUIET = xconfig.quiet
from league.xs import store as xstore

REPO = Path(__file__).resolve().parents[2]
CELL = ("equity", "xs_reversal", "panel:sp500")


class Settings(unittest.TestCase):
    def test_the_defaults_are_off_and_every_default_is_inside_its_bound(self):
        c = elane_xs.cfg(None)
        self.assertEqual({k: v for k, v in c.items() if k != "screen"}, elane_xs.DEFAULTS)
        self.assertEqual((c["mode"], c["screen"]), ("off", {}))
        for key, (low, high) in elane_xs.BOUNDS.items():
            self.assertTrue(low <= elane_xs.DEFAULTS[key] <= high, key)

    def test_a_value_outside_its_bound_reads_as_its_default(self):
        raw = {"mode": "shadow", "panels": ["sp500", "r2000"], "birth_share": 1.5, "max_alive": 101, "max_names": 4,
               "rebalance": ["daily"], "train_budget": 5, "placebos_train": 199, "cpu_seconds_day": -1,
               "run_budget_seconds": 601, "zero_edge_programs": 19, "coverage_min": 0.9, "spreads_min_share": 0.4,
               "membership_max_stale_days": 6, "universe_max_age_days": 501, "live_min_tradable_share": 0.5}
        c = elane_xs.cfg({"elane": {"panel": raw}})
        self.assertEqual({k: c[k] for k in raw if k != "panels"}, {k: elane_xs.DEFAULTS[k] for k in raw if k != "panels"})
        self.assertEqual(c["panels"], ["sp500"], "a panel this code does not know is dropped")
        self.assertEqual(elane_xs.cfg({"elane": {"panel": {"max_names": True, "birth_share": "0.2",
                                                           "train_budget": 2.5}}})["train_budget"], 4)
        for bad in (None, 7, "live", ["live"]):
            self.assertEqual(elane_xs.cfg({"elane": {"panel": bad}})["mode"], "off")

    def test_a_value_inside_its_bound_is_kept(self):
        c = elane_xs.cfg({"elane": {"panel": {"mode": "live", "birth_share": 0.25, "max_alive": 0, "max_names": 8,
                                              "rebalance": ["monthly"], "train_budget": 2, "cpu_seconds_day": 0,
                                              "coverage_min": 0.99}}})
        self.assertEqual((c["mode"], c["birth_share"], c["max_alive"], c["max_names"], c["rebalance"], c["train_budget"],
                          c["cpu_seconds_day"], c["coverage_min"]), ("live", 0.25, 0, 8, ["monthly"], 2, 0, 0.99))

    def test_census_notes_are_held_to_the_agenda_and_to_two_hundred_characters(self):
        notes = {"xs_reversal": "x" * 500, "no_such_cell": "kept nowhere", "xs_momentum": 7}
        c = elane_xs.cfg({"elane": {"panel": {"census_notes": notes}}})
        self.assertEqual(c["census_notes"], {"xs_reversal": "x" * elane_xs.CENSUS_NOTE_MAX})
        text = elane_xs.agenda_text({"elane": {"panel": {"census_notes": {"xs_low_vol": "an invented note"}}}})
        self.assertIn(f"[census_informed; {elane_xs.CENSUS_LABEL}: an invented note]", text)
        self.assertNotIn("census", elane_xs.agenda_text(None))
        self.assertIn("earnings_drift is REFUSED", text)

    def test_the_names_are_the_stores_and_e1s(self):
        self.assertEqual(elane_xs.STORE_DIR, STORE_DIR)
        self.assertEqual(elane_xs.STORE_DIR, elane.STORE_DIR)
        self.assertEqual(elane_xs.PANEL_MANIFEST, f"{xstore.PANEL_DIR}/PANEL_MANIFEST.json")
        self.assertEqual(elane_xs.UNIVERSE_MANIFEST, f"{xstore.UNIVERSE_DIR}/UNIVERSE_MANIFEST.json")
        self.assertEqual(tuple(elane_xs.SCREEN_NULLS), xscreen.PIN_KEYS)
        self.assertEqual(set(elane_xs.SCREEN_NULLS.values()), {None})
        self.assertEqual(elane_xs.SCREEN_NAME, xscreen.SCREEN)
        self.assertEqual(elane_xs.STRUCTURE, "panel")
        self.assertEqual(len(set(elane_xs.SEALED)), 9)

    def test_the_pin_is_the_repositorys_policy_and_never_the_boxs_settings(self):
        policy = {"elane": {"screens": {"equity_xs": {"receipt_sha256": "a" * 64}}}}
        self.assertEqual(elane_xs.pin(policy), {"receipt_sha256": "a" * 64})
        self.assertEqual(elane_xs.pin(policy["elane"]), {"receipt_sha256": "a" * 64})
        self.assertEqual(elane_xs.pin({}), {})
        self.assertEqual(elane_xs.pin({"elane": {"screens": {"equity_xs": None}}}), {})


class TheEffectiveMode(unittest.TestCase):
    def setUp(self):
        self.world = F.switch_on(self)
        self.store = F.new_store(self)
        self.root = self.store.root

    def mode(self, wanted="live", **kw):
        return elane_xs.mode(F.settings(wanted, **kw), self.root)

    def test_the_ladder(self):
        self.assertEqual(self.mode(), "off", "no panel manifest: nothing of the lane runs")
        F.write_manifest(self.root)
        self.assertEqual(self.mode("off"), "off")
        self.assertEqual(self.mode("train"), "train")
        self.assertEqual(self.mode("gate"), "gate")
        self.assertEqual(self.mode("live"), "gate", "the universe deploy is not in force: live reads as gate")
        F.ready(self.root)
        self.assertEqual(self.mode("live"), "live")
        self.assertEqual(self.mode("gate"), "gate", "the setting is never exceeded")

    def test_the_reason_the_mode_reads_lower_reaches_the_status_and_an_alarm(self):
        """The review's spec-6: `_mode_why`'s reason reached no status, heartbeat or alert. The captain sets "gate";
        the spreads' share is 0.89, so the lane reads "train": no Validation, no look, and no line said why."""
        F.ready(self.root, hs_share=0.89)
        wanted = F.settings("gate")
        self.assertEqual(elane_xs.status(wanted, self.root),
                         {"setting": "gate", "mode": "train",
                          "why": "the spreads' share is under elane.panel.spreads_min_share", "look": None})
        F.ready(self.root)
        self.assertEqual(elane_xs.status(F.settings("live"), self.root), {"setting": "live", "mode": "live", "why": None,
                                                                               "look": None})
        self.assertEqual(elane_xs.status(F.settings("gate"), self.root), {"setting": "gate", "mode": "gate", "why": None,
                                                                               "look": None})
        self.assertEqual(elane_xs.status(None, self.root)["mode"], "off", "it never raises")
        F.ready(self.root, i6={"equal": False})
        said = elane_xs.status(F.settings("live"), self.root)
        self.assertEqual((said["mode"], said["why"][:27]), ("gate", "the last nightly I6 did not"))
        # THE ALARMS (`health`), each once a UTC day: the mode held under its setting, the spreads, the universe's
        # age, a store two nights stale. With the switch off nothing is read and nothing is said.
        now = F.NOW if hasattr(F, "NOW") else 1791720000.0

        def alerts():
            return [(e["payload"]["action"], e["payload"]["text"]) for e in self.store.events_after(0, limit=5000)
                    if e["kind"] == "swarm.status" and e["payload"].get("alert")
                    and str(e["payload"].get("action", "")).startswith("elane_xs_")]

        self.assertEqual(elane_xs.health(self.store, F.settings("off"), self.root, now), [])
        F.ready(self.root, hs_share=0.89, live_from="2025-01-02")
        raised = elane_xs.health(self.store, F.settings("gate"), self.root, now)
        self.assertEqual(raised, ["mode", "spreads", "universe_age"])
        said = dict(alerts())
        self.assertIn('set "gate" and the lane reads "train"', said["elane_xs_mode"])
        self.assertIn("0.890", said["elane_xs_spreads"])
        self.assertIn("regenerate it (an owner deploy)", said["elane_xs_universe_age"])
        self.assertEqual(elane_xs.health(self.store, F.settings("gate"), self.root, now), [], "once a UTC day")
        self.assertEqual(elane_xs.health(self.store, F.settings("gate"), self.root, now + 86400.0)[:2], ["mode", "spreads"])
        F.ready(self.root)
        late = dt.datetime(2026, 10, 16, 14, 0, tzinfo=dt.timezone.utc).timestamp()   # the store ends Friday the 9th
        self.assertEqual(elane_xs.health(self.store, F.settings("train"), self.root, late), ["stale"])
        self.assertIn("the panel store is stale: its last session is 2026-10-09", dict(alerts())["elane_xs_stale"])
        self.assertEqual(elane_xs.health(self.store, F.settings("train"), self.root,
                                         dt.datetime(2026, 10, 11, 14, 0, tzinfo=dt.timezone.utc).timestamp()), [],
                         "a lane whose every leg holds says nothing")

    def test_a_panel_run_may_not_start_where_it_could_work_inside_a_session(self):
        """ONE CORE (the ship pass): a panel run's wall is the whole session, the two walls and everything between
        them. `may_run` asks the real rule with the run budget; a weekend, a holiday and the night have no wall."""
        patcher = mock.patch.object(xconfig, "quiet", REAL_QUIET)                                  # the rule itself
        patcher.start()
        self.addCleanup(patcher.stop)

        def at(day, hh, mm):                                                                     # New York time
            return dt.datetime(*day, hh, mm, tzinfo=xconfig.NEW_YORK).timestamp()

        monday, saturday, half, holiday = (2026, 10, 12), (2026, 10, 10), (2026, 11, 27), (2026, 11, 26)
        settings = F.settings("train")
        budget = float(elane_xs.cfg(settings)["run_budget_seconds"])
        self.assertEqual((budget, xconfig.RUN_SESSION_ET), (600.0, ("09:25", "16:35")))
        for hh, mm, may in ((9, 14, True), (9, 16, False), (9, 30, False), (11, 0, False), (13, 30, False),
                            (15, 0, False), (16, 0, False), (16, 35, False), (16, 36, True), (20, 0, True), (3, 0, True)):
            why = elane_xs.may_run(self.store, settings, at(monday, hh, mm))
            self.assertEqual(why is None, may, (hh, mm, why))
            if not may:
                self.assertIn("no panel run works while the market is open", why)
        # the data jobs' own question keeps the two walls alone: 11:00 is no wall of theirs
        self.assertIsNone(xconfig.quiet(at(monday, 11, 0), budget))
        self.assertIsNotNone(xconfig.quiet(at(monday, 11, 0), budget, session=True))
        self.assertIsNotNone(xconfig.quiet(at(monday, 9, 30), budget))
        # no session, no wall: a Saturday at noon and Thanksgiving at noon
        for day in (saturday, holiday):
            self.assertIsNone(elane_xs.may_run(self.store, settings, at(day, 12, 0)), day)
        # a half day (the Friday after Thanksgiving closes at 13:00): the session's end moves with its close
        self.assertIsNotNone(elane_xs.may_run(self.store, settings, at(half, 13, 30)))
        self.assertIsNone(elane_xs.may_run(self.store, settings, at(half, 13, 36)))
        self.assertIsNotNone(elane_xs.may_run(self.store, settings, at(half, 9, 20)))

    def test_a_run_found_running_at_a_wall_is_a_critical_alert_once_a_day(self):
        """E4-SPEC 17: "an E4 job or a Train run found RUNNING at a wall" (critical: a bug in `quiet`, which every
        run asks before it starts). For a panel run the wall is the whole session. Nothing looked afterwards."""
        monday_open = dt.datetime(2026, 10, 12, 13, 28, tzinfo=dt.timezone.utc).timestamp()      # 09:28 New York
        patcher = mock.patch.object(xconfig, "quiet", REAL_QUIET)                                  # the rule itself
        patcher.start()
        self.addCleanup(patcher.stop)
        elane_xs._wall_alert(self.store, monday_open - 3600.0, 600.0)                             # 08:28-08:38: no wall
        def walls():
            return [e["payload"] for e in self.store.events_after(0, limit=5000)
                    if e["kind"] == "swarm.status" and e["payload"].get("action") == "elane_xs_wall"]

        self.assertEqual(walls(), [])
        elane_xs._wall_alert(self.store, monday_open - 600.0, 900.0)                              # 09:18-09:33: the open's
        elane_xs._wall_alert(self.store, monday_open, 60.0)
        [alarm] = walls()
        self.assertEqual((alarm["alert"], alarm["level"]), (True, "critical"))
        self.assertIn("found RUNNING inside a session", alarm["text"])
        with mock.patch.object(elane_xs.time, "time", return_value=monday_open), \
                mock.patch.object(elane_xs.time, "monotonic", side_effect=[0.0, 5.0]):
            self.assertEqual(elane_xs._timed(self.store, types.SimpleNamespace(clock=lambda: monday_open),
                                             lambda: "ran"), "ran")
        self.assertEqual(len(walls()), 1, "once a UTC day")

    def test_the_equity_lanes_own_switch_comes_first(self):
        F.ready(self.root)
        self.assertEqual(elane_xs.mode(F.settings("live", lane="off"), self.root), "off")
        self.assertEqual(elane_xs.mode({}, self.root), "off")
        self.assertEqual(elane_xs.mode(None, self.root), "off")

    def test_an_insufficient_coverage_holds_the_lane_off_and_a_low_one_does_not(self):
        F.ready(self.root, verdict="insufficient")
        self.assertEqual(self.mode(), "off")
        F.ready(self.root, verdict="low_coverage")
        self.assertEqual(self.mode(), "live")
        F.ready(self.root, verdict="unheard-of")
        self.assertEqual(self.mode(), "off")

    def test_no_receipt_is_at_most_train(self):
        F.ready(self.root)
        self.world.pin = dict(elane_xs.SCREEN_NULLS)
        self.assertEqual(self.mode("live"), "train", "NO RECEIPT, NO LOOK")
        self.world.pin = F.pin_block(alpha_plac=0.2)
        self.assertEqual(self.mode("gate"), "train", "a figure the pre-registration does not allow pins nothing")

    def test_unsampled_spreads_are_at_most_train(self):
        F.ready(self.root, hs_share=0.89)
        self.assertEqual(self.mode("live"), "train", "provisional costs: research only")
        F.ready(self.root, hs_share=None)
        self.assertEqual(self.mode("live"), "train")
        self.assertEqual(self.mode("live", spreads_min_share=0.5), "train", "an unread share is no share")
        F.ready(self.root, hs_share=0.6)
        self.assertEqual(self.mode("live", spreads_min_share=0.5), "live")

    def test_without_a_root_the_mode_is_the_settings_and_never_live(self):
        self.assertEqual(elane_xs.mode(F.settings("live")), "gate")
        self.assertEqual(elane_xs.mode(F.settings("train")), "train")
        self.world.pin = dict(elane_xs.SCREEN_NULLS)
        self.assertEqual(elane_xs.mode(F.settings("live")), "train")

    def test_a_manifest_that_cannot_be_read_is_off_and_nothing_raises(self):
        path = Path(self.root) / elane_xs.STORE_DIR / elane_xs.PANEL_MANIFEST
        path.parent.mkdir(parents=True)
        path.write_text("{ not json")
        self.assertEqual(self.mode(), "off")
        path.write_text("[1, 2]")
        self.assertEqual(self.mode(), "off")
        with mock.patch.object(elane_xs, "_manifest", side_effect=OSError("the disk")):
            self.assertEqual(self.mode(), "off")

    def test_a_screen_that_is_not_built_reads_as_no_receipt(self):
        F.ready(self.root)

        def stub(block):
            raise NotImplementedError("league.xs.screen is a Step 0 stub")

        with mock.patch.object(xscreen, "pinned_receipt", stub):
            self.assertEqual(self.mode("live"), "train")
            self.assertEqual(elane_xs.receipt()[0], None)

    def test_a_receipt_file_at_hand_must_be_the_pins_bytes(self):
        F.ready(self.root)
        repo = Path(self.root) / "release"
        (repo / "docs" / "benchmarks").mkdir(parents=True)
        (repo / xscreen.RECEIPT_PATH).write_text("{}")
        pinned = F.pinned_receipt(F.pin_block())
        with mock.patch.object(xscreen, "load_receipt", side_effect=xscreen.ScreenRefused("the sha256 is not the pin's")):
            got, why = elane_xs.receipt(repo=repo)
        self.assertIsNone(got)
        self.assertIn("cannot be checked", why)
        other = F.pinned_receipt(F.pin_block(c_XS=1.38))
        with mock.patch.object(xscreen, "load_receipt", return_value=other):
            self.assertIn("not the receipt file's", elane_xs.receipt(repo=repo)[1])
        with mock.patch.object(xscreen, "load_receipt", return_value=pinned) as loaded:
            self.assertEqual(elane_xs.receipt(repo=repo), (pinned, None))
        self.assertEqual(loaded.call_args.kwargs, {"pinned_sha256": F.FAKE_SHA})
        self.assertEqual(elane_xs.receipt(repo=F.NO_DOCS), (pinned, None), "no file at hand: nothing to compare")


class TheLiveLegs(unittest.TestCase):
    def setUp(self):
        self.world = F.switch_on(self)
        self.store = F.new_store(self)
        self.root = self.store.root
        self.settings = F.settings("live")

    def ready(self):
        return elane_xs.live_ready(self.root, self.settings)

    def test_every_leg_holds(self):
        F.ready(self.root)
        self.assertEqual(self.ready(), (True, None))

    def test_the_universe_deploy(self):
        F.ready(self.root, live_from=None)
        self.assertIn("live_from", self.ready()[1])

    def test_the_tradable_share(self):
        F.ready(self.root)
        self.world.tradable = 0.948
        ok, why = self.ready()
        self.assertFalse(ok)
        self.assertIn("live_min_tradable_share", why)
        self.world.tradable = 0.95
        self.assertTrue(self.ready()[0])
        with mock.patch.object(xstore, "Universe", side_effect=NotImplementedError("a stub")):
            self.assertFalse(self.ready()[0], "a universe that cannot be read is not ready")

    def test_the_universes_age(self):
        F.ready(self.root, live_from="2025-09-04")
        self.assertEqual(self.ready(), (True, None), "400 days old")
        F.ready(self.root, live_from="2025-09-03")
        self.assertIn("universe_max_age_days", self.ready()[1])
        F.ready(self.root, live_from="2025-09-03", universe_at="2026-09-01")
        self.assertTrue(self.ready()[0], "a regenerated list is as old as the day the House first read it")

    def test_the_nightly_i6(self):
        for i6 in ({"equal": False}, {"equal": None}, {}, None, "ok"):
            F.ready(self.root, i6=i6)
            self.assertIn("I6", self.ready()[1])

    def test_the_store_is_fresh_by_the_calendar_and_the_clock(self):
        """Every other leg is read from the last manifest, so a panel store that stopped being written kept the lane
        "live" on its last good I6 for as long as its files stayed as they were. The store's last session (Friday
        2026-10-09 here) must be the last closed session or the one before, by the clock handed in."""
        F.ready(self.root)

        def at(day, hour, minute=0):
            return dt.datetime(2026, 10, day, hour, minute, tzinfo=dt.timezone.utc).timestamp()

        def ready(now):
            return elane_xs.live_ready(self.root, self.settings, now=now)

        self.assertEqual(ready(at(9, 20, 1)), (True, None), "Friday, a minute after the close: the night's job is to come")
        self.assertEqual(ready(at(11, 16)), (True, None), "the weekend")
        self.assertEqual(ready(at(12, 13, 31)), (True, None), "Monday's open: Friday is the last closed session")
        self.assertEqual(ready(at(12, 20, 1)), (True, None), "Monday after the close: Friday is the one before")
        self.assertEqual(ready(at(13, 13, 31)), (True, None), "Tuesday's sends: ONE missed night is tolerated")
        ok, why = ready(at(13, 20, 1))                    # Tuesday's close: Monday's night never ran, nor is Tuesday's due
        self.assertFalse(ok)
        self.assertEqual(why, "the panel store is stale: its last session is 2026-10-09 and the session before the last "
                              "closed one is 2026-10-12 (the nightly equity_panel job has not written it for two nights)")
        self.assertTrue(why.startswith(elane_xs.STALE))
        self.assertFalse(ready(at(16, 14))[0], "and five nights later")
        # The process's own clock when none is handed in (the tests' is the weekend: league/tests/__init__.py).
        self.assertEqual(self.ready(), (True, None))
        with mock.patch.object(elane_xs, "CLOCK", lambda: at(16, 14)):
            self.assertEqual(self.ready()[0], False)
            self.assertEqual(elane_xs.mode(self.settings, self.root), "gate", "a stale store reads the lane at most gate")
        self.assertEqual(elane_xs.mode(self.settings, self.root), "live")
        # THE TWIN MARKER likewise: through the store's last session or the one before is not enough once the clock
        # has moved two sessions past it.
        F.ready(self.root, fetched_through="2026-10-13")
        F.write_twins(self.root, through="2026-10-12")
        self.assertEqual(ready(at(14, 13, 31)), (True, None))
        self.assertIn("twin marker is behind", ready(at(14, 20, 1))[1], "Wednesday's close: the marker is two behind")

    def test_the_twin_marker(self):
        F.write_manifest(self.root, live_from="2026-09-01")
        self.assertIn("twin marker is missing", self.ready()[1], "with no panel night's marker, live reads as gate")
        F.write_twins(self.root, version="xs-twins-0")
        self.assertIn("twin marker is missing", self.ready()[1])
        F.write_twins(self.root, through="2026-10-08")
        self.assertTrue(self.ready()[0], "the session before the store's last is one night behind: allowed")
        F.write_twins(self.root, through="2026-10-07")
        self.assertIn("behind the panel store", self.ready()[1], "two nights stopped")
        F.write_twins(self.root, instances={"fam@1:r": {"due": None, "last": None}})
        self.assertTrue(self.ready()[0], "before an instance's first decision nothing is due")
        F.write_twins(self.root, instances={"fam@1:r": {"due": "2026-10-08", "last": "2026-10-07"}})
        self.assertTrue(self.ready()[0], "one session behind its due day")
        F.write_twins(self.root, instances={"fam@1:r": {"due": "2026-10-05", "last": "2026-10-01"}})
        self.assertIn("more than one session behind", self.ready()[1], "Friday is the session before Monday")
        F.write_twins(self.root, instances={"fam@1:r": {"due": "2026-10-05", "last": "2026-10-02"}})
        self.assertTrue(self.ready()[0])
        F.write_twins(self.root, instances={"fam@1:r": {"due": "2026-10-08"}})
        self.assertFalse(self.ready()[0], "a due row with no twin")
        F.write_twins(self.root, instances={"fam@1:r": {"due": "soon", "last": "2026-10-08"}})
        self.assertFalse(self.ready()[0])


class TheSeatRule(unittest.TestCase):
    def setUp(self):
        self.world = F.switch_on(self)
        self.store = F.new_store(self)
        self.root = self.store.root

    def on_disk(self, mode):
        (Path(self.root) / "swarm.json").write_text(json.dumps({"elane": {"mode": "gate", "panel": {"mode": mode}}}))
        with elane_xs._cache_lock:
            elane_xs._mode_cache.clear()

    def test_a_panel_candidate_is_seatable_only_while_the_mode_is_live(self):
        F.ready(self.root)
        self.on_disk("live")
        rule = elane_xs.seatable(self.root)
        self.assertTrue(rule("panel"))
        self.assertTrue(rule("etf") and rule("stock"))
        self.assertFalse(rule("iron_condor") or rule(None))
        self.on_disk("gate")
        self.assertFalse(elane_xs.seatable(self.root)("panel"))
        self.on_disk("live")
        F.write_manifest(self.root, live_from="2026-09-01", i6={"equal": False})
        self.assertFalse(elane_xs.seatable(self.root)("panel"), "a failed I6 stops new seats")

    def test_with_no_panel_family_asked_about_nothing_of_the_panel_is_read(self):
        with mock.patch.object(elane_xs, "mode", side_effect=AssertionError("read")):
            rule = elane_xs.seatable(Path(self.root) / "no-such-root")
            self.assertTrue(rule("etf"))
            self.assertFalse(rule("long_call"))

    def test_the_mode_is_reused_for_half_a_minute(self):
        F.ready(self.root)
        self.on_disk("live")
        rule = elane_xs.seatable(self.root)
        self.assertTrue(rule("panel"))
        with mock.patch.object(elane_xs, "mode", side_effect=AssertionError("read again")):
            self.assertTrue(rule("panel"))
            with mock.patch.object(elane_xs.time, "monotonic", return_value=elane_xs.time.monotonic() + 31.0):
                with self.assertRaises(AssertionError):
                    rule("panel")


class ThePanelsOwnRunner(unittest.TestCase):
    def test_it_is_built_once_a_root_over_its_own_niced_decider_with_the_evidence_hash_seed(self):
        from league.live import decider as live_decider
        from league.xs import runner as xrunner

        made = []

        class Decider:
            hash_seed = None

            def __init__(self, *, log):
                self.log = Path(log)

        class Isolated:
            def __init__(self, decider, root, *, budget_seconds, nice):
                self.decider, self.root, self.budget, self.nice = decider, Path(root), budget_seconds, nice
                made.append(self)

        store = F.new_store(self)
        root = Path(store.root)
        self.addCleanup(elane_xs._runners.pop, str(root.resolve()), None)
        self.addCleanup(elane_xs._deciders.pop, str(root.resolve()), None)
        with mock.patch.object(live_decider, "Decider", Decider), mock.patch.object(xrunner, "Isolated", Isolated):
            first = elane_xs.runner(root, F.settings("train", run_budget_seconds=120))
            again = elane_xs.runner(root, F.settings("train"))
        self.assertIs(first, again)
        self.assertEqual(len(made), 1, "built once a process and root")
        self.assertEqual((first.root, first.budget, first.nice), (root / "equity-daily", 120.0, 19))
        self.assertEqual(first.decider.log, root / "xs-decider.log", "its own child and its own log")
        self.assertNotEqual(first.decider.log.name, "equity-decider.log", "never E1's evidence child")
        self.assertEqual(first.decider.hash_seed, elane.EVIDENCE_HASH_SEED)
        self.assertIs(elane_xs._decider_of(object(), root), first.decider)
        owner = F.owner(store, F.World(), F.settings("train"))
        owner.xs_runner = None
        self.assertIs(elane_xs._runner_of(owner), first)


class CardsAndCells(unittest.TestCase):
    def setUp(self):
        self.world = F.switch_on(self)
        self.store = F.new_store(self)
        F.ready(self.store.root)
        self.settings = F.settings("train")

    def errors(self, **over):
        return elane_xs.card_errors(F.card(**over), self.settings)

    def test_a_card_inside_the_box_has_no_error(self):
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.errors(rebalance="monthly", weekday=None, max_names=12), [])
        self.assertEqual(elane_xs.card_errors(F.card(agenda="xs_low_vol"), self.settings, store=self.store), [])

    def test_every_refusal_is_named(self):
        cases = {"lane": {"lane": "beta"}, "panel": {"panel": "r2000"}, "max_names": {"max_names": 13},
                 "rebalance": {"rebalance": "daily"}, "weekday": {"weekday": 5}, "agenda": {"agenda": "earnings_drift"},
                 "symbols": {"symbols": ["AAPL"]}, "inputs": {"inputs": ["event_calendar"]},
                 "ablation": {"ablation": {"flat": True}}}
        for field, over in cases.items():
            errors = self.errors(**over)
            self.assertEqual(len(errors), 1, (field, errors))
            self.assertTrue(errors[0].startswith(f"{field}:"), errors)
        self.assertTrue(self.errors(max_names=4) and self.errors(max_names=True) and self.errors(max_names=5.0))
        self.assertTrue(self.errors(rebalance="monthly", weekday=0)[0].startswith("weekday:"))
        self.assertEqual(self.errors(inputs="underlying_price, clock"), [])

    def test_with_the_lane_closed_a_panel_card_is_refused(self):
        for settings in (F.settings("off"), F.settings("train", lane="off"), {}):
            errors = elane_xs.card_errors(F.card(), settings)
            self.assertIn("the panel lane is closed", errors[0])

    def test_the_cell_is_the_panels_own_three_tuple(self):
        self.assertEqual(elane_xs.cell_of("equity", "xs_reversal", "sp500"), CELL)
        self.assertEqual(elane_xs.cell_of("equity", "overnight", "sp500"), ("equity", "xs_other", "panel:sp500"))
        fam = F.panel_family(self.store, "mom-a", agenda="xs_momentum")
        self.assertEqual(elane_xs.family_cell(fam), ("equity", "xs_momentum", "panel:sp500"))
        self.assertTrue(elane_xs.is_panel(fam))
        self.assertFalse(elane_xs.is_panel({"structure": "etf"}) or elane_xs.is_panel(None))

    def test_a_cell_refuted_too_often_with_no_pass_is_closed(self):
        judged = {"status": "refuted", "versions": {"1": {"fails": ["XT1"]}}}
        stalled = {"status": "stalled", "versions": {"1": {"fails": ["DQ"]}}}
        for i in range(3):
            F.panel_family(self.store, f"rev-{i}", record=judged if i < 2 else stalled)
        self.assertEqual(elane_xs.closed_cells(self.store, self.settings), [], "two refutations and a stall")
        F.panel_family(self.store, "rev-3", record=judged)
        self.assertEqual(elane_xs.closed_cells(self.store, self.settings), [CELL])
        errors = elane_xs.card_errors(F.card(agenda="xs_reversal"), self.settings, store=self.store)
        self.assertEqual(len(errors), 1)
        self.assertIn("CLOSED", errors[0])
        self.assertEqual(elane_xs.card_errors(F.card(agenda="xs_momentum"), self.settings, store=self.store), [])
        F.panel_family(self.store, "rev-4", record={"status": "passed", "passed_version": 1,
                                                    "versions": {"1": {"score": 3.1, "fails": []}}})
        self.assertEqual(elane_xs.closed_cells(self.store, self.settings), [], "a pass reopens nothing: it never closed")

    def test_the_map_counts_train_facts_and_shows_the_zero_edge_column(self):
        F.panel_family(self.store, "rev-a", record={"status": "passed", "passed_version": 1, "versions": {
            "1": {"score": 3.14, "fails": [], "flags": [elane_xs.FLAG_SURVIVORSHIP]}}})
        F.panel_family(self.store, "rev-b", record={"status": "refuted", "versions": {"1": {"fails": ["XT1"]}}})
        F.panel_family(self.store, "mom-a", agenda="xs_momentum")
        rows = elane_xs.train_map(self.store)
        self.assertEqual(rows[0], {"cell": CELL, "births": 2, "scored": 2, "passed": 1, "refuted": 1, "stalled": 0,
                                   "best_t": 3.14, "sensitive": 1, "zero_rate": None, "zero_expected": None})
        text = elane_xs.train_map_text(self.store, self.settings)
        self.assertIn("zero-edge expected unmeasured", text)
        self.assertIn("the zero-edge rate is not measured yet", text)
        self.store.put(elane_xs.ZERO_KEY, {"2026-W40": {"programs": 100, "passes": 3, "by_rule": {}},
                                           "2026-W41": {"programs": 100, "passes": 1, "by_rule": {}},
                                           "bad": {"programs": 1, "passes": 9}})
        self.assertEqual(elane_xs.zero_edge_rate(self.store), {"programs": 200, "passes": 4, "rate": 0.02})
        rows = elane_xs.train_map(self.store)
        self.assertEqual((rows[0]["zero_rate"], rows[0]["zero_expected"]), (0.02, 0.04))
        text = elane_xs.train_map_text(self.store, self.settings)
        self.assertIn("births 2, scored 2, passed 1 (best t 3.1), 1 survivorship-sensitive, zero-edge expected 0.04", text)
        self.assertIn("passed 4 of 200 random-score programs", text)
        self.assertIn("in-sample", text)
        self.assertEqual(elane_xs.train_map_text(F.new_store(self), self.settings), "")

    def test_the_request_carries_the_map_after_e2s_and_never_in_the_panel_block(self):
        text = elane_xs.train_map_text(self.store, self.settings)
        self.assertEqual(elane_xs.request_map_text(self.store, self.settings), text)
        self.assertEqual(elane_xs.request_map_text(self.store, self.settings, limit=1),
                         elane_xs.train_map_text(self.store, self.settings, limit=1))
        block = elane_xs.request_text(self.store, self.settings, 4)
        self.assertIn("THE PANEL (structure \"panel\", lane equity)", block)
        self.assertNotIn("PANEL TRAIN MAP", block, "the map is E2's request's, once (patch 7), not the block's too")
        for closed in (F.settings("off"), F.settings("gate", lane="off"), None):
            self.assertEqual(elane_xs.request_map_text(self.store, closed), "", "a closed lane shows no map of itself")
            self.assertEqual(elane_xs.request_text(self.store, closed, 4), "")

    def test_the_maps_label_says_what_the_store_dropped(self):
        F.write_manifest(self.store.root, train_years_ok=[2017, 2018, 2019, 2022, 2024], verdict="low_coverage")
        (Path(self.store.root) / elane_xs.STORE_DIR / "universe").mkdir()
        (Path(self.store.root) / elane_xs.STORE_DIR / elane_xs.UNIVERSE_MANIFEST).write_text(
            json.dumps({"exits": {"deal": 80, "other": 9, "unknown": 4}}))
        notes = elane_xs.map_notes(self.store.root)
        self.assertEqual(notes, ["dropped from the bar for thin coverage: 2023",
                                 "4 index exits of unknown kind take the vanish haircut"])
        F.panel_family(self.store, "rev-a")
        self.assertIn(notes[0], elane_xs.train_map_text(self.store, self.settings))
        # THE THIN LOOK-BACK NOTE reads the lane's own `coverage_min` (the review's spec-5: it read the default,
        # whatever the captain had set).
        F.write_manifest(self.store.root, coverage={"2016": {"share": 0.975}, "2021": {"share": 0.995}})
        self.assertEqual(elane_xs.map_notes(self.store.root)[:1], ["4 index exits of unknown kind take the vanish haircut"])
        tighter = {"elane": {"mode": "gate", "panel": {"mode": "train", "coverage_min": 0.99}}}
        self.assertIn("thin look-back in the first months after 2016", elane_xs.map_notes(self.store.root, tighter))


class TheQuotaAndTheHiddenYear(unittest.TestCase):
    def setUp(self):
        self.world = F.switch_on(self)
        self.store = F.new_store(self)
        F.ready(self.store.root)
        self.settings = F.settings("train")

    def born(self, structure):
        self.store.event("swarm.born", None, {"lane": "equity", "structure": structure})

    def test_a_closed_lane_bears_nothing(self):
        for settings in (F.settings("off"), F.settings("train", lane="off"), F.settings("train", birth_share=0.0),
                         F.settings("train", max_alive=0)):
            self.assertEqual(elane_xs.quota(self.store, settings, 6), 0)
        self.assertEqual(elane_xs.quota(self.store, self.settings, 0), 0)

    def test_the_share_is_held_over_the_window_so_a_pass_of_one_birth_alternates(self):
        took = []
        for _ in range(6):
            n = elane_xs.quota(self.store, self.settings, 1)
            took.append(n)
            self.born("panel" if n else "etf")
        self.assertEqual(took, [1, 0, 1, 0, 1, 0], "half of the equity lanes' births, never every one nor none")
        self.assertEqual(elane_xs.quota(F.new_store(self), self.settings, 6), 0, "another store has no manifest")

    def test_a_pass_of_several_takes_its_share_and_the_ceiling_binds(self):
        self.assertEqual(elane_xs.quota(self.store, self.settings, 6), 3)
        self.assertEqual(elane_xs.quota(self.store, F.settings("train", birth_share=1.0), 6), 6)
        self.assertEqual(elane_xs.quota(self.store, F.settings("train", birth_share=0.25), 6), 2, "the ceiling of 1.5")
        for i in range(11):
            F.panel_family(self.store, f"rev-{i}")
        self.assertEqual(elane_xs.researching(self.store), 11)
        self.assertEqual(elane_xs.quota(self.store, self.settings, 6), 1, "eleven of twelve in research")
        F.panel_family(self.store, "rev-11", record={"status": "passed", "passed_version": 1, "versions": {}})
        self.assertEqual(elane_xs.quota(self.store, self.settings, 6), 1, "a family that passed Train left the count")
        F.panel_family(self.store, "rev-12")
        self.assertEqual(elane_xs.quota(self.store, self.settings, 6), 0)

    def test_the_folds_three_facts_are_e3s_own_and_the_lane_imports_no_memory_module(self):
        """Release E3's seal T1: only its Train module, its births and league/ops import the memory modules. The
        panel lane spells the three facts of the fold it needs; they are E3's, input for input."""
        from league.swarm import elane_folds

        self.assertEqual((elane_xs.FOLD_GID0, elane_xs._gid()), (elane_folds.GID0, elane_folds.GID0))
        self.assertIn(elane_xs.FOLD_RECORD, elane_folds.MODES)
        for cell in (CELL, ("beta", "other", "index"), ("equity", "xs_momentum", "panel:sp500"), ("a",), ()):
            self.assertEqual(elane_xs.fold_hash(cell), elane_folds.cell_hash(cell), cell)
        for settings in (None, {}, [], {"elane": None}, {"elane": {"memory": None}}, {"elane": {"memory": []}},
                         {"elane": {"memory": {}}}, {"elane": {"memory": {"mode": "off"}}},
                         {"elane": {"memory": {"mode": "record"}}}, {"elane": {"memory": {"mode": "Record"}}},
                         {"elane": {"memory": {"mode": True}}}, {"elane": {"memory": {"mode": ["record"]}}}):
            self.assertEqual(elane_xs.fold_recording(settings), elane_folds.mode(settings) == "record", settings)
        tree = ast.parse(Path(elane_xs.__file__).read_text(encoding="utf-8"))
        named = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                 for alias in node.names} | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertFalse({n for n in named if n.split(".")[-1] in ("elane_folds", "elane_effects", "elane_memory")})

    def test_the_hidden_year_rotates_over_the_panels_six_train_years_by_cell(self):
        from league.swarm import elane_folds as folds

        recording = {**self.settings, "elane": {**self.settings["elane"], "memory": {"mode": "record"}}}
        self.assertIsNone(elane_xs.assign(self.store, CELL, self.settings), "the folds are not recording")
        start = folds.cell_hash(CELL) % 6
        years = []
        for i in range(7):
            year = elane_xs.assign(self.store, CELL, recording)
            years.append(year)
            F.panel_family(self.store, f"rev-{i}", hidden=year)
        self.assertEqual(years, [xconfig.TRAIN_YEARS[(start + i) % 6] for i in range(7)])
        self.assertFalse(set(years) & {2016, 2020, 2021}, "never a history year: nothing would be hidden")
        other = ("equity", "xs_momentum", "panel:sp500")
        self.assertEqual(elane_xs.assign(self.store, other, recording),
                         xconfig.TRAIN_YEARS[folds.cell_hash(other) % 6], "each cell has its own count")
        F.panel_family(self.store, "no-year", hidden=None)
        self.assertEqual(elane_xs.assign(self.store, CELL, recording), xconfig.TRAIN_YEARS[(start + 7) % 6],
                         "a family born with no hidden year does not move the count")


class NoThresholdReachesAGenerator(unittest.TestCase):
    """A generator or a reviewer is told the screen's NAME and never a figure of its receipt (a threshold in a prompt
    would be a target to fit), as E2 holds for the share screen."""

    def test_the_texts_name_no_figure_of_the_receipt(self):
        world = F.switch_on(self)
        store = F.new_store(self)
        F.ready(store.root)
        settings = F.settings("gate")
        F.panel_family(store, "rev-a", record={"status": "passed", "passed_version": 1,
                                               "versions": {"1": {"score": 3.1, "fails": []}}})
        block, contract = elane_xs.request_text(store, settings, 4), elane_xs.contract_text()
        self.assertIn(contract, block, "the architect's block ends with the contract, whole")
        texts = {"the researcher's system text": elane_xs.RESEARCHER_SYSTEM, "the review's rubric": elane_xs.REVIEW_SYSTEM,
                 "the bar": elane_xs.bar_text(), "the agenda": elane_xs.agenda_text(settings),
                 "the architect's block": block.replace(contract, ""), "the map's label": elane_xs.MAP_LABEL,
                 "the contract's stand-in": elane_xs.CONTRACT_FALLBACK, "the contract": contract,
                 "the map": elane_xs.train_map_text(store, settings)}
        pinned = F.pinned_receipt(world.pin)
        for where, text in texts.items():
            self.assertTrue(text, where)
            for word in ("c_XS", "c_used", "c_p", "c_margin", "alpha_plac", "p_plac", "t_H", "fp_cap", "own_fp",
                         pinned.receipt_sha256[:12]):
                self.assertNotIn(word, text, where)
            for count in ("999", "119", "1000", "1,000"):  # the placebo draws and the bar on them (a year is no count,
                if where == "the contract" and count == "999":  # nor is a sleeve's dollars)
                    continue  # XS.md (package C's) says how many portfolios the screen draws: never the bar on them
                self.assertIsNone(re.search(rf"(?<![\d.$]){re.escape(count)}(?!\d)", text), (where, count))
            for sentence in re.split(r"(?<=[.;:])\s+", " ".join(text.split())):
                if not re.search(r"XS1|screen|Validation|\blook\b|holdout", sentence):
                    continue
                for figure in ("0.12", "12%", "0.15", "15%", "0.05", "1.30", "1.38", "88%"):
                    self.assertNotIn(figure, sentence, (where, figure))
        self.assertIn("XS1", texts["the bar"])


class GateCase(unittest.TestCase):
    """A panel family brought to its Validation and its look, `elane_xs.validate` and `elane_xs.look` called as E1's
    tournament and gate call them."""

    def setUp(self):
        self.world = F.switch_on(self)
        self.store = F.new_store(self)
        F.ready(self.store.root)
        self.settings = F.settings("gate")
        self.owner = F.owner(self.store, self.world, self.settings)
        self.runner = self.world.runner

    def family(self, slug="rev-a", *, code=None, style=None, reviewed=True, **kw):
        """A family whose v1 passed the bar (its record written by hand: the bar has its own tests) and the review."""
        fam = F.panel_family(self.store, slug, code=code if code is not None else F.good(tag=slug), **kw)
        lean = style if isinstance(style, dict) else {}
        verdict = F.style_open({"lots": 90, "loadings": {"size": 0.0, "beta": 0.0, "mom": 0.0, "vol": 0.0, **lean}})
        self.store.set_state(fam["id"], **{elane_xs.STATE_KEY: {
            "status": "passed", "passed_version": 1,
            "versions": {"1": {"n": 1, "passed": True, "fails": [], "score": 3.0, "identity": elane_xs.identity(),
                               **({} if style == "none" else {elane_xs.STYLE_FIELD: verdict})}}}})
        if reviewed:
            F.reviewed(self.store, fam["id"])
        return self.store.family(fam["id"])

    def validate(self, fam, n=1):
        fam = self.store.family(fam["id"])
        return elane_xs.validate(self.owner, fam, self.store.version(fam["id"], n))

    def look(self, fam, n=1):
        fam = self.store.family(fam["id"])
        version = self.store.version(fam["id"], n)
        return elane_xs.look(self.owner, fam, version, run_sha(version))

    def state(self, fam):
        return self.store.family(fam["id"])["state"]

    def events(self, kind, action=None):
        return [e["payload"] for e in self.store.events_after(0, limit=5000)
                if e["kind"] == kind and (action is None or e["payload"].get("action") == action)]

    def windows(self):
        return [c["window"] for c in self.runner.calls]


class Validation(GateCase):
    def test_both_train_series_are_kept_before_the_one_try(self):
        fam = self.family()
        out = self.validate(fam)
        self.assertEqual((out["passed"], out["entered"], out["first"], out["screen"], out["structure"]),
                         (True, True, True, "XS1", "panel"))
        self.assertEqual(self.windows(), ["train", "train", "validation", "validation"],
                         "the two whole Train segments, THEN the 2025 run at both k")
        self.assertEqual([(c["start"], c["end"], c["k"]) for c in self.runner.calls[:2]],
                         [(a, b, 1.0) for a, b in xconfig.TRAIN_SEGMENTS])
        self.assertEqual([c["k"] for c in self.runner.calls[2:]], [1.0, 1.5])
        state = self.state(fam)
        x, u = state[elane_xs.TRAIN_X_KEY], state[elane_xs.TRAIN_U_KEY]
        self.assertEqual((x["version"], u["version"]), (1, 1))
        self.assertEqual(len(x["days"]), 754 + 753)
        self.assertEqual(x["days"], u["days"])
        self.assertEqual(x["days"], sorted(x["days"]))
        self.assertEqual((len(x["x"]), len(u["u"])), (1507, 1507))
        self.assertNotEqual(x["x"], u["u"], "two series: the residual and the universe excess")
        self.assertEqual(state[elane_xs.PRECHECK_KEY], {"version": 1, "at": self.store.now(), "reached": True,
                                                        "passed": True})
        self.assertEqual(state[elane.TRY_KEY]["retry_sha"], None, "no Validation-only retry is ever registered")
        self.assertTrue(state[elane.TRY_KEY]["entered"] and state["gate_ready"])
        self.assertEqual(state[elane.SIGMA_KEY], {"1": 0.011}, "EDM1's sigma: the sd of a close DATE's return")
        self.assertEqual(state[elane.VALIDATION_KEY]["screen"], "XS1")
        self.assertEqual(self.events("swarm.status", "elane_validation")[0]["structure"], "panel")

    def test_the_stored_validation_rows_are_the_status_alone_and_count_as_the_try(self):
        fam = self.family()
        self.validate(fam)
        rows = self.store.runs(fam["id"], window="validation")
        self.assertEqual(sorted((r["stress"], r["trials"]) for r in rows), [(1.0, 1), (1.5, 1)])
        for row in rows:
            kept = self.store.run_result(row["run_id"])
            self.assertEqual(sorted(kept), ["run_id", "status", "trials"], "no figure of Validation is stored in a run")
        self.assertEqual(len(elane.lineage_tries(self.store, fam["id"])), 1)
        self.store.add_version(fam["id"], F.good(tag="later"), {}, author="test")
        self.assertEqual(self.validate(fam, 2)["refused"], elane.SPENT_TRY)
        self.assertIsNone(elane.next_try(self.store, self.store.family(fam["id"]), self.settings))

    def test_a_refusal_at_the_precheck_spends_the_try_and_keeps_both_series(self):
        fam = self.family(code=F.good(edge_in={"validation": -0.002}))
        later = self.store.add_version(fam["id"], F.good(tag="later"), {}, author="test")
        out = self.validate(fam)
        self.assertEqual((out["passed"], out["entered"]), (False, False))
        state = self.state(fam)
        self.assertEqual((state[elane_xs.PRECHECK_KEY]["reached"], state[elane_xs.PRECHECK_KEY]["passed"]), (True, False))
        self.assertIn(elane_xs.TRAIN_X_KEY, state)
        self.assertIn(elane_xs.TRAIN_U_KEY, state)
        self.assertFalse(state["gate_ready"])
        self.assertIsNone(state[elane.TRY_KEY]["retry_sha"], "R-g: no retry, though a later version stood ready")
        fam = self.store.family(fam["id"])
        self.assertIsNone(elane.next_try(self.store, fam, self.settings))
        self.assertFalse(elane.try_open(self.store, fam, later["n"], self.settings))
        self.assertEqual(elane_xs.lineage_spent(self.store, fam, self.settings), elane.SPENT_TRY)

    def test_the_gate_closed_validates_nothing(self):
        fam = self.family()
        for settings in (F.settings("train"), F.settings("off"), F.settings("gate", lane="off")):
            owner = F.owner(self.store, self.world, settings)
            self.assertIn("closed", elane_xs.validate(owner, fam, self.store.version(fam["id"], 1))["refused"])
        self.world.pin = dict(elane_xs.SCREEN_NULLS)
        self.assertIn("closed", self.validate(fam)["refused"], "no receipt: the mode reads train")
        self.assertEqual(self.runner.calls, [])
        self.assertIn("not a panel", elane_xs.validate(self.owner, {"id": "x", "structure": "etf"}, {"n": 1})["refused"])

    def test_the_try_waits_for_the_quiet_rule_and_spends_nothing(self):
        fam = self.family()
        self.world.quiet = "inside 600 s of the 09:25 ET wall"
        out = self.validate(fam)
        self.assertEqual(out["waits"], "inside 600 s of the 09:25 ET wall")
        self.assertEqual((self.runner.calls, elane.lineage_tries(self.store, fam["id"])), ([], []))
        self.assertNotIn(elane_xs.PRECHECK_KEY, self.state(fam))

    def test_a_run_the_house_could_not_make_is_no_try(self):
        fam = self.family()
        self.runner.fail["train"] = RuntimeError("the child failed")
        self.assertEqual(self.validate(fam)["error"], "RuntimeError")
        self.runner.fail = {"validation": RuntimeError("the child failed")}
        self.assertEqual(self.validate(fam)["error"], "RuntimeError")
        self.assertEqual(self.store.runs(fam["id"], window="validation"), [])
        self.assertEqual(elane.lineage_tries(self.store, fam["id"]), [])
        self.assertNotIn(elane_xs.PRECHECK_KEY, self.state(fam))
        self.runner.fail = {}
        gone = self.family("rev-b", code=F.good(status_in={"validation": "no_data"}))
        self.assertEqual(self.validate(gone)["error"], "no_data")
        self.assertEqual(elane.lineage_tries(self.store, gone["id"]), [], "a run the runner could not make is no try")
        self.assertTrue(self.validate(fam)["entered"], "and the try is still open")

    def test_a_validation_run_the_programs_own_errors_ended_is_its_try(self):
        fam = self.family(code=F.good(status_in={"validation": "disqualified"}))
        out = self.validate(fam)
        self.assertEqual((out["entered"], out.get("error")), (False, None))
        state = self.state(fam)
        self.assertEqual(state[elane_xs.PRECHECK_KEY]["passed"], False)
        self.assertEqual(elane_xs.lineage_spent(self.store, self.store.family(fam["id"]), self.settings), elane.SPENT_TRY)

    def test_a_train_segment_the_programs_own_errors_ended_takes_no_try(self):
        fam = self.family(code=F.good(status_in={"train": "disqualified"}))
        out = self.validate(fam)
        self.assertEqual(out["refused"], elane_xs.TRAIN_ENDED)
        self.assertEqual(self.windows(), ["train", "train"], "no Validation run was made")
        self.assertEqual(elane_xs.lineage_spent(self.store, self.store.family(fam["id"]), self.settings),
                         elane_xs.TRAIN_ENDED)
        self.assertEqual(self.validate(fam)["refused"], elane_xs.TRAIN_ENDED)
        self.assertEqual(len(self.runner.calls), 2, "asked again, it runs nothing")


class TheLineage(GateCase):
    def template(self, fam):
        return elane.lineage_key("equity", self.store.version(fam["id"], 1)["sha"])

    def test_the_same_program_in_another_family_is_one_lineage_by_the_stores_own_link(self):
        code = F.good(tag="one")
        first = self.family("rev-a", code=code)
        self.validate(first)
        self.runner.calls.clear()
        clone = self.family("mom-a", code=code, agenda="xs_momentum")
        self.assertEqual(self.validate(clone)["refused"], elane.SPENT_TRY, "identical code joins the lineages")
        self.assertEqual(self.runner.calls, [])

    def test_the_same_template_takes_no_second_try(self):
        first = self.family("rev-a", code=F.good(tag="one"))
        self.validate(first)
        self.runner.calls.clear()
        clone = self.family("mom-a", code=F.good(tag="two"), agenda="xs_momentum")
        self.store.set_state(first["id"], **{elane_xs.PRECHECK_KEY: {"version": 1, "reached": True, "passed": False},
                                            elane.TEMPLATE_KEY: self.template(clone)})
        out = self.validate(clone)
        self.assertEqual(out["refused"], elane_xs.SAME_LINEAGE_XS)
        self.assertEqual(self.windows(), ["train", "train"], "its Train series, and no Validation run")
        state = self.state(clone)
        self.assertEqual((state[elane_xs.PRECHECK_KEY]["reached"], state[elane_xs.PRECHECK_KEY]["twin"]), (False, "rev-a"))
        self.assertEqual(elane.lineage_tries(self.store, clone["id"]), [])
        self.assertEqual(elane_xs.lineage_spent(self.store, self.store.family(clone["id"]), self.settings),
                         elane_xs.SAME_LINEAGE_XS)
        self.assertEqual([r["stage"] for r in self.store.refusals(clone["id"])], ["same lineage"])
        self.assertNotIn("rev-a", json.dumps(self.events("swarm.status", "elane_validation_refused")[0]).replace(
            "\"_twin\": \"rev-a\"", ""), "the twin's name is private")

    def test_a_retired_family_is_still_a_lineage_comparator(self):
        """The review's evidence-4. In production a refused pre-check or a failed look RETIRES the family, so a
        retired comparator is the normal case: were `same_lineage` to read the alive families only, every clone of a
        refused program would get a fresh Validation try and a fresh look."""
        first = self.family("rev-a", code=F.good(tag="one"))
        self.validate(first)
        clone = self.family("mom-a", code=F.good(tag="two"), agenda="xs_momentum")
        self.store.set_state(first["id"], **{elane_xs.PRECHECK_KEY: {"version": 1, "reached": True, "passed": False},
                                            elane.TEMPLATE_KEY: self.template(clone)})
        self.assertTrue(self.store.retire(first["id"], "its Validation pre-check refused it"))
        self.assertIsNotNone(self.store.family(first["id"])["retired_at"])
        self.assertNotIn(first["id"], [f["id"] for f in elane_xs.panel_families(self.store, alive=True)])
        self.runner.calls.clear()
        out = self.validate(clone)
        self.assertEqual(out["refused"], elane_xs.SAME_LINEAGE_XS, "a retired twin spent the lineage's try all the same")
        self.assertEqual(self.windows(), ["train", "train"], "its Train series, and no Validation run")
        self.assertEqual(self.state(clone)[elane_xs.PRECHECK_KEY]["twin"], "rev-a")
        # And by the series alone (no template in common): a retired family's kept Train series still bind.
        a, b = self.series(11), self.series(12)
        other = F.panel_family(self.store, "other")
        self.store.set_state("other", **{elane.TEMPLATE_KEY: "equity:other-code",
                                         elane_xs.PRECHECK_KEY: {"version": 1, "reached": True, "passed": False},
                                         **self.kept(a, b)})
        self.assertTrue(self.store.retire("other", "refused at its pre-check"))
        mine = F.panel_family(self.store, "mine")
        days = list(range(1000, 1300))
        self.assertEqual(elane_xs.same_lineage(self.store, mine, template="equity:my-code",
                                               train_x={"days": days, "x": a}, train_u={"days": days, "u": self.series(13)}),
                         "other")

    def test_a_program_that_passed_its_precheck_and_was_not_looked_at_binds_nobody(self):
        first = self.family("rev-a", code=F.good(tag="one"))
        self.validate(first)
        clone = self.family("mom-a", code=F.good(tag="two"), agenda="xs_momentum")
        self.store.set_state(first["id"], **{elane.TEMPLATE_KEY: self.template(clone)})
        self.assertTrue(self.validate(clone)["entered"], "neither looked at nor refused at its pre-check")

    def rule(self, mine_x, mine_u, **their_state):
        """`same_lineage` of a new family against one whose state is given."""
        other = F.panel_family(self.store, "other")
        self.store.set_state("other", **{elane.TEMPLATE_KEY: "equity:other-code", **their_state})
        fam = F.panel_family(self.store, "mine")
        days = list(range(1000, 1300))
        return elane_xs.same_lineage(self.store, fam, template="equity:my-code",
                                     train_x={"days": days, "x": mine_x}, train_u={"days": days, "u": mine_u})

    def series(self, seed, n=300):
        import random

        rng = random.Random(seed)
        return [rng.random() - 0.5 for _ in range(n)]

    def kept(self, x, u):
        days = list(range(1000, 1300))
        return {elane_xs.TRAIN_X_KEY: {"version": 1, "days": days, "x": x},
                elane_xs.TRAIN_U_KEY: {"version": 1, "days": days, "u": u}}

    def test_a_correlation_in_either_series_is_the_same_lineage(self):
        a, b, c, d = (self.series(i) for i in range(4))
        refused = {elane_xs.PRECHECK_KEY: {"version": 1, "reached": True, "passed": False}}
        self.assertEqual(self.rule(a, b, **refused, **self.kept(a, d)), "other", "the residuals correlate")

    def test_a_correlation_in_the_universe_excess_alone_is_the_same_lineage(self):
        a, b, c, d = (self.series(i) for i in range(4))
        refused = {elane_xs.PRECHECK_KEY: {"version": 1, "reached": True, "passed": False}}
        self.assertEqual(self.rule(a, b, **refused, **self.kept(c, b)), "other",
                         "x removes what two variants share; u keeps it")

    def test_two_unrelated_programs_are_two_lineages(self):
        a, b, c, d = (self.series(i) for i in range(4))
        refused = {elane_xs.PRECHECK_KEY: {"version": 1, "reached": True, "passed": False}}
        self.assertIsNone(self.rule(a, b, **refused, **self.kept(c, d)))

    def test_the_rule_reads_programs_looked_at_in_flight_or_refused_at_the_precheck_and_no_other(self):
        a, b = self.series(0), self.series(1)
        cases = {"looked at": {elane_xs.LOOK_KEY: {"version": 1, "verdict": {"passed": False}}},
                 "a look in flight": {"look_inflight": {"sha": "s", "n": 1}},
                 "refused at the pre-check": {elane_xs.PRECHECK_KEY: {"version": 1, "reached": True, "passed": False}}}
        for said, state in cases.items():
            with self.subTest(said):
                store = F.new_store(self)
                self.store, kept = store, self.store
                try:
                    self.assertEqual(self.rule(a, b, **state, **self.kept(a, b)), "other", said)
                finally:
                    self.store = kept
        for said, state in {"passed its pre-check, not looked at": {elane_xs.PRECHECK_KEY: {"version": 1, "reached": True,
                                                                                         "passed": True}},
                            "refused before its try": {elane_xs.PRECHECK_KEY: {"version": 1, "reached": False}},
                            "only scored on Train": {}}.items():
            with self.subTest(said):
                store = F.new_store(self)
                self.store, kept = store, self.store
                try:
                    self.assertIsNone(self.rule(a, b, **state, **self.kept(a, b)), said)
                finally:
                    self.store = kept

    def test_a_judged_program_that_keeps_no_series_is_never_skipped(self):
        a, b = self.series(0), self.series(1)
        with self.assertRaises(elane_xs.LineageUnread) as caught:
            self.rule(a, b, **{elane_xs.LOOK_KEY: {"version": 1, "verdict": {"passed": True}}})
        self.assertEqual(caught.exception.family, "other")

    def test_a_missing_series_is_written_again_from_the_train_runs_or_the_program_waits(self):
        first = self.family("rev-a", code=F.good(tag="one", common=0.0))
        self.validate(first)
        self.store.set_state(first["id"], **{elane_xs.PRECHECK_KEY: {"version": 1, "reached": True, "passed": False},
                                            elane_xs.TRAIN_X_KEY: None, elane_xs.TRAIN_U_KEY: None})
        second = self.family("mom-a", code=F.good(tag="two"), agenda="xs_momentum")
        self.assertTrue(self.validate(second)["entered"], "restored, compared and found unrelated")
        self.assertEqual(len(self.state(first)[elane_xs.TRAIN_X_KEY]["days"]), 1507)
        self.assertEqual(len(self.events("swarm.gate", "panel_lineage_restored")), 1)
        self.store.set_state(first["id"], **{elane_xs.TRAIN_X_KEY: None, elane_xs.PRECHECK_KEY: {"reached": True,
                                                                                                "passed": False}})
        third = self.family("vol-a", code=F.good(tag="three"), agenda="xs_low_vol")
        out = self.validate(third)
        self.assertIn("cannot be judged", out["waits"], "its pre-check names no version to run again")
        self.assertEqual(elane.lineage_tries(self.store, third["id"]), [])


class TheLook(GateCase):
    def gated(self, slug="rev-a", **kw):
        fam = self.family(slug, **kw)
        self.assertTrue(self.validate(fam)["entered"], slug)
        self.runner.calls.clear()
        return self.store.family(fam["id"])

    def test_a_pass_makes_a_candidate_proven_on_the_xs_identity(self):
        fam = self.gated()
        self.assertIs(self.look(fam), True)
        got = self.store.family(fam["id"])
        state = got["state"]
        version = self.store.version(fam["id"], 1)
        sha = run_sha(version)
        self.assertEqual(got["band"], "candidate")
        self.assertEqual(state["banded_evaluator"], {"engine": "xs-engine-1", "xs_sha256": "c" * 64, "run_sha": sha})
        self.assertEqual((state["banded_version"], state["gate"], state["gated_sha"]), (1, "pass", sha))
        looked = state[elane_xs.LOOK_KEY]
        self.assertEqual((looked["version"], looked["seat"], looked["seat_why"], looked["cell"], looked["n_cell"]),
                         (1, elane_xs.SEAT_CANDIDATE, None, list(CELL), 0))
        self.assertTrue(looked["verdict"]["passed"])
        self.assertEqual(looked["probe"]["route"], F.ROUTE)
        self.assertEqual(sorted(looked["probe"]["strata"]), ["P4", "P5", "P6"])
        self.assertTrue(self.store.looked(sha))
        row = self.store.looks()[0]
        self.assertEqual((row["family"], row["passed"]), (fam["id"], 1))
        event = self.events("swarm.gate", "look")[0]
        self.assertEqual((event["screen"], event["receipt"], event["seat"], event["passed"]),
                         ("XS1", F.FAKE_SHA, "candidate", True))
        self.assertEqual(elane_xs.view(got)["look"], {"version": 1, "passed": True})

    def test_the_sealed_run_is_one_run_with_the_receipts_draws_under_the_seed_fixed_before_it(self):
        fam = self.gated()
        self.look(fam)
        sealed = [c for c in self.runner.calls if c["window"] == "look"]
        self.assertEqual(len(sealed), 1)
        code = self.store.version(fam["id"], 1)["code"]
        seed = F.look_seed(F.FAKE_SHA, hashlib.sha256(code.encode()).hexdigest())
        self.assertEqual((sealed[0]["placebos"], sealed[0]["seed"], sealed[0]["k"]), (999, seed, 1.0))
        self.assertEqual((sealed[0]["start"], sealed[0]["end"]), (dt.date(2025, 1, 2), dt.date(2026, 10, 9)),
                         "Validation's first session through the holdout's cap")
        self.assertEqual(self.windows(), ["train", "train", "validation", "look"],
                         "the floor's segments, the recorded Validation reproduced, then the one look")

    def test_the_sentence_is_recorded_with_the_look_and_counts_the_cells_earlier_looks(self):
        first, second = self.gated("rev-a"), self.gated("rev-b")
        self.look(first)
        self.look(second)
        a, b = elane_xs.beside_line(self.store.family("rev-a")), elane_xs.beside_line(self.store.family("rev-b"))
        self.assertIn("earlier looks in its cell 0", a)
        self.assertIn("earlier looks in its cell 1", b, "the House's count, stated beside every live trade")
        self.assertEqual(a, self.store.looks()[0]["detail"]["beside"])
        self.assertIsNone(elane_xs.beside_line(self.family("rev-c")), "a family that took no look has no sentence")
        self.assertEqual(elane_xs.view(self.store.family("rev-a"))["beside"], a)

    def test_a_failed_look_is_spent_and_retires_the_family(self):
        fam = self.gated(code=F.good(edge_by_year={"2026": -0.0008}))
        self.assertIs(self.look(fam), False)
        got = self.store.family(fam["id"])
        self.assertEqual((got["band"], got["state"]["gate"]), ("gym", "fail"))
        self.assertNotIn("banded_evaluator", got["state"])
        self.assertIsNone(got["state"][elane_xs.LOOK_KEY]["seat"])
        self.assertIs(got["state"][elane_xs.LOOK_KEY]["passed"], False)
        self.assertEqual(elane_xs.lineage_spent(self.store, got, self.settings), elane.SPENT_LOOK)
        self.assertIsNone(self.look(fam), "its one look is spent")
        self.assertEqual(len(self.store.looks()), 1)


class NoReceiptNoLook(GateCase):
    """Seal X10 (the swarm's half): with nulls pinned no panel look runs and nothing is spent."""

    def test_nulls_refuse_every_look(self):
        fam = self.family()
        self.assertTrue(self.validate(fam)["entered"])
        self.runner.calls.clear()
        self.world.pin = dict(elane_xs.SCREEN_NULLS)
        got, why = elane_xs.receipt()
        self.assertIsNone(got)
        self.assertIn("no receipt is pinned", why)
        self.assertEqual(elane_xs.mode(self.settings, self.store.root), "train")
        self.assertIsNone(self.look(fam))
        self.assertEqual((self.runner.calls, self.store.looks()), ([], []))
        self.assertTrue(self.state(fam)["gate_ready"], "nothing spent: its look is owed once a receipt is pinned")

    def test_a_receipt_lost_between_the_mode_and_the_look_waits(self):
        fam = self.family()
        self.validate(fam)
        self.runner.calls.clear()
        self.world.pin = dict(elane_xs.SCREEN_NULLS)
        with mock.patch.object(elane_xs, "mode", return_value="gate"):
            self.assertIsNone(self.look(fam))
            self.assertIsNone(self.look(fam))
        state = self.state(fam)
        self.assertEqual(state["gate_outcome"]["result"], "waiting")
        self.assertIn("XS1 refused", state["gate"])
        self.assertEqual((self.runner.calls, self.store.looks()), ([], []))
        self.assertEqual(len(self.events("swarm.gate", "equity_look_waits")), 1, "said once, though asked every round")

    def test_a_pin_the_preregistration_does_not_allow_pins_nothing(self):
        for bad in ({"alpha_plac": 0.2}, {"placebo_draws": 200}, {"rung": "R2"}, {"retry": True},
                    {"receipt_sha256": "abc"}, {"screen": "S2"}):
            self.world.pin = F.pin_block(**bad)
            self.assertIsNone(elane_xs.receipt()[0], bad)

    def test_the_committed_policy_ships_the_pin_as_nulls_in_the_pins_own_order(self):
        doc = json.loads((REPO / "league" / "swarm" / "policy.json").read_text())
        block = (doc["elane"].get("screens") or {}).get(elane_xs.SCREEN_KEY)
        if block is None:
            self.skipTest(F.HOLDS.format(n=9))
        self.assertEqual(tuple(block), xscreen.PIN_KEYS)
        if block["receipt_sha256"] is None:
            self.assertEqual(block, elane_xs.SCREEN_NULLS, "nulls until the integrator lands the receipt with its pin")
            self.assertEqual(set(block.values()), {None}, "a pin is whole or it is nulls: never half-filled")
        else:
            path = REPO / xscreen.RECEIPT_PATH
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), block["receipt_sha256"])
        panel = doc["elane"][elane_xs.SETTINGS_KEY]
        self.assertEqual(panel["mode"], "off", "the lane ships off")
        self.assertEqual(elane_xs.cfg({"elane": {"panel": panel}})["mode"], "off")
        self.assertEqual({k: v for k, v in elane_xs.cfg({"elane": {"panel": panel}}).items() if k != "screen"}, panel,
                         "every shipped value is inside its bound")


class TheCaptainsA22(TheLook):
    def test_a_style_open_passer_gets_no_band_and_is_not_retired(self):
        fam = self.gated(style={"size": 0.5})
        self.assertIs(self.look(fam), True, "the screen passed it")
        got = self.store.family(fam["id"])
        state = got["state"]
        self.assertEqual(got["band"], "gym", "RECORDED AND SHADOWED, NEVER SEATED")
        for key in ("banded_evaluator", "banded_version", "banded_at"):
            self.assertNotIn(key, state)
        looked = state[elane_xs.LOOK_KEY]
        self.assertEqual((looked["seat"], looked["seat_why"]), (elane_xs.SEAT_STYLE, "style-open: size +"))
        self.assertTrue(looked["verdict"]["passed"])
        self.assertIs(looked["passed"], True, "the record's top level says so too (the operator report reads it there)")
        self.assertTrue(self.store.looks()[0]["passed"], "the look is spent and its pass recorded")
        self.assertEqual(self.store.looks()[0]["detail"]["seat"], "style-open")
        self.assertIsNone(elane_xs.lineage_spent(self.store, got, self.settings), "alive: the forward route is its way")
        self.assertIsNone(self.look(fam), "and it takes no second look")
        self.assertEqual(len(self.store.looks()), 1)
        note = self.events("swarm.status", "panel_style_open")[0]
        self.assertIn("takes no live seat", note["text"])
        self.assertIn("takes no live seat", elane_xs.view(got)["notes"][0])
        self.assertEqual(elane_xs.view(got)["seat"], "style-open")

    def test_a_passer_with_no_style_reading_or_one_made_under_other_figures_is_style_open(self):
        missing = self.gated("rev-a", style="none")
        self.look(missing)
        self.assertEqual(self.state(missing)[elane_xs.LOOK_KEY]["seat_why"], "style-open: unmeasured")
        other = self.gated("mom-a", agenda="xs_momentum")
        rec = elane_xs.record_of(self.store.family("mom-a"))
        rec["versions"]["1"][elane_xs.STYLE_FIELD]["rule"] = {"tilt": 0.5, "min_lots": 40}
        self.store.set_state("mom-a", **{elane_xs.STATE_KEY: rec})
        self.look(other)
        self.assertEqual(self.state(other)[elane_xs.LOOK_KEY]["seat"], elane_xs.SEAT_STYLE)
        self.assertEqual([self.store.family(f)["band"] for f in ("rev-a", "mom-a")], ["gym", "gym"])
        from league.xs import style as xstyle

        with mock.patch.object(xstyle, "seat_refusal", side_effect=NotImplementedError("a stub")):
            last = self.gated("vol-a", agenda="xs_low_vol")
            self.assertIs(self.look(last), True)
        self.assertEqual(self.store.family("vol-a")["band"], "gym", "a rule that cannot be asked seats nothing")

    def test_a_failed_look_of_a_style_open_program_is_simply_failed(self):
        fam = self.gated(style={"vol": -0.6}, code=F.good(edge_by_year={"2026": -0.0008}))
        self.assertIs(self.look(fam), False)
        self.assertIsNone(self.state(fam)[elane_xs.LOOK_KEY]["seat"])
        self.assertEqual(elane_xs.lineage_spent(self.store, self.store.family(fam["id"]), self.settings),
                         elane.SPENT_LOOK)

    def test_at_most_two_looks_an_agenda_cell_and_the_third_waits_unspent(self):
        fams = [self.gated(f"rev-{i}") for i in range(3)]
        other = self.gated("mom-a", agenda="xs_momentum")
        self.assertEqual(elane_xs.MAX_CELL_LOOKS, 2)
        self.assertIsNotNone(self.look(fams[0]))
        self.assertIsNotNone(self.look(fams[1]))
        self.assertEqual(elane_xs.cell_looks(self.store, CELL), 2)
        self.runner.calls.clear()
        self.assertIsNone(self.look(fams[2]))
        self.assertIsNone(self.look(fams[2]))
        state = self.state(fams[2])
        self.assertEqual(self.runner.calls, [], "held back before any run")
        self.assertEqual(len(self.store.looks()), 2)
        self.assertTrue(state["gate_ready"], "not spent: the family waits")
        self.assertIn("at most 2 a cell until a forward verdict exists", state["gate"])
        self.assertIsNone(elane_xs.lineage_spent(self.store, self.store.family("rev-2"), self.settings))
        self.assertEqual(len([e for e in self.events("swarm.gate", "equity_look_waits")]), 1)
        self.assertIsNotNone(self.look(other), "another cell has its own two")
        self.assertIsNone(elane_xs.look_room(self.store, ("equity", "xs_low_vol", "panel:sp500")))

    def test_a_retired_familys_look_still_counts_toward_its_cell(self):
        """The review's evidence-4: a failed look retires its family, so were `cell_looks` to count the alive
        families only, the cap of two looks a cell (the captain's A22 (2)) would never bind."""
        fams = [self.gated(f"rev-{i}") for i in range(3)]
        self.assertIsNotNone(self.look(fams[0]))
        self.assertIsNotNone(self.look(fams[1]))
        for fam in fams[:2]:
            self.store.retire(fam["id"], "its look failed") or self.assertIsNotNone(
                self.store.family(fam["id"])["retired_at"])
            self.assertIsNotNone(self.store.family(fam["id"])["retired_at"])
        self.assertEqual([f["id"] for f in elane_xs.panel_families(self.store, alive=True)], ["rev-2"])
        self.assertEqual(elane_xs.cell_looks(self.store, CELL), 2, "the cell's two looks are spent, their families gone")
        self.runner.calls.clear()
        self.assertIsNone(self.look(fams[2]))
        self.assertEqual(self.runner.calls, [], "held back before any run")
        self.assertEqual(len(self.store.looks()), 2)
        self.assertIn("at most 2 a cell until a forward verdict exists", self.state(fams[2])["gate"])

    def test_a_look_in_flight_counts_toward_its_cell(self):
        fams = [self.gated(f"rev-{i}") for i in range(3)]
        self.look(fams[0])
        self.store.set_state("rev-1", look_inflight={"sha": "s", "n": 1, "at": 1.0})
        self.assertEqual(elane_xs.cell_looks(self.store, CELL), 2)
        self.assertIsNone(self.look(fams[2]))
        self.assertEqual(len(self.store.looks()), 1)

    def test_the_look_waits_on_the_contamination_probe(self):
        fam = self.gated()
        probe = Path(self.store.root) / elane_xs.PROBE_FILE
        probe.unlink()
        self.assertIsNone(self.look(fam))
        self.assertIn("no published result", self.state(fam)["gate"], "release E3's probe has not run")
        F.write_probe(self.store.root, route="sail:another")
        self.assertIsNone(self.look(fam))
        self.assertIn(F.ROUTE, self.state(fam)["gate"])
        F.write_probe(self.store.root, published=False)
        self.assertIsNone(self.look(fam))
        F.write_probe(self.store.root, strata=("P4", "P5"))
        self.assertIsNone(self.look(fam))
        self.assertIn("no panel stratum P6", self.state(fam)["gate"])
        probe.write_text("{ not json")
        self.assertIsNone(self.look(fam))
        self.assertEqual((self.runner.calls, self.store.looks()), ([], []), "no run was made and no look spent")
        self.assertTrue(self.state(fam)["gate_ready"])
        F.write_probe(self.store.root)
        self.assertIs(self.look(fam), True)
        reading = self.state(fam)[elane_xs.LOOK_KEY]["probe"]
        self.assertEqual(reading["strata"]["P4"]["2025"], {"readable": True, "recalled": False})
        self.assertNotIn("acc", json.dumps(reading), "the reading recorded is two booleans a cell")

    def test_the_look_waits_on_the_review_under_the_panel_rubric(self):
        fam = self.family(reviewed=False)
        self.store.set_state(fam["id"], **{elane_xs.STATE_KEY: {**elane_xs.record_of(fam), "passed_version": 1}})
        self.validate(fam)
        self.runner.calls.clear()
        self.assertIsNone(self.look(fam))
        self.assertIn("under the panel rubric", self.state(fam)["gate"])
        from league.swarm import elane_review

        sha = run_sha(self.store.version(fam["id"], 1))
        etf = elane_review.record(sha, {"route": "sail:a"}, {"route": "sail:b"}, at="now", version=1)
        self.store.set_state(fam["id"], review=etf)
        self.assertTrue(elane.reviewed(self.state(fam), sha), "E1 would take this record")
        self.assertIsNone(self.look(fam), "a review under the ETF rubric is not the panel's")
        self.assertEqual(self.runner.calls, [])
        F.reviewed(self.store, fam["id"])
        self.assertIs(self.look(fam), True)


class TheLooksRefusalsAndWaits(TheLook):
    def test_the_look_asks_the_lanes_mode_itself_and_is_refused_under_gate(self):
        """THE LOOK'S OWN MODE CHECK (the ship check's finding: no test held it). A family validated under "gate" has
        everything a look needs: its Validation entered, its review, the probe, the floor's segments, the holdout.
        With the setting lowered to "train" (the captain's step one), or to "off", the look itself must refuse:
        nothing run on the sealed window, no look spent, no band. It is the only guard if the setting is ever lowered
        from "gate": Validation's own refusal (`may_validate`) is behind the family by then."""
        fam = self.gated()
        version = self.store.version(fam["id"], 1)
        for lowered in ("train", "off"):
            owner = F.owner(self.store, self.world, F.settings(lowered))
            self.assertEqual(elane_xs.mode(owner.settings, self.store.root), lowered)
            self.assertIsNone(elane_xs.look(owner, self.store.family(fam["id"]), version, run_sha(version)), lowered)
            self.assertEqual(self.store.looks(), [], "no look spent")
            self.assertNotIn("look", self.windows(), "the sealed run was not made")
            got = self.store.family(fam["id"])
            self.assertNotEqual(got["band"], "candidate")
            self.assertNotIn(elane_xs.LOOK_KEY, got["state"])
            self.assertNotIn("banded_evaluator", got["state"])
            self.assertEqual(self.events("swarm.gate", "look"), [])
        # With the setting back at "gate" the same family takes its one look: the check above refused nothing else.
        self.assertIs(self.look(self.store.family(fam["id"])), True)
        self.assertEqual(self.store.family(fam["id"])["band"], "candidate")
        self.assertEqual(len(self.store.looks()), 1)

    def test_an_ineligible_floor_spends_no_look(self):
        fam = self.gated()
        self.world.screen.eligible = False
        self.assertIsNone(self.look(fam))
        self.assertEqual(self.store.looks(), [])
        self.assertEqual([r["stage"] for r in self.store.refusals(fam["id"])], ["screen floor"])
        self.assertEqual(elane_xs.lineage_spent(self.store, self.store.family(fam["id"]), self.settings),
                         elane.FLOOR_INELIGIBLE)
        self.assertNotIn("look", self.windows())

    def test_the_floor_is_computed_from_the_segments_just_run_never_taken_from_an_earlier_attempt(self):
        """The review's evidence-3. A floor kept from an earlier attempt of the look was reused whenever it fit the
        receipt's figures: nothing tied it to the Train series it was computed from. Between two attempts (the look
        waited on its lineage, on Validation, or lost its run once) the panel job restates a name's adjusted history
        or the spreads job rewrites the half-spreads; the Train residual changes; the look was judged at the OLD
        k_used and its sentence stated the old c_p and own_fp beside every live trade."""
        fam = self.gated()
        self.look(fam)
        self.assertEqual(self.world.screen.floors, 1)
        kept = self.state(fam)[elane_xs.FLOOR_KEY]["1"]
        self.assertEqual((kept["c_XS"], kept["c_used"]), (1.0, 1.0))
        # A floor left by an earlier attempt, under THIS receipt's figures and from OTHER Train series (a higher own
        # floor): it fits the receipt, and it is not the program's floor today.
        second = self.gated("mom-a", agenda="xs_momentum")
        stale = {**kept, "c_p": 1.2, "k_p": 120, "c_used": 1.25, "k_used": 125, "own_fp": 0.01}
        self.store.set_state("mom-a", **{elane_xs.FLOOR_KEY: {"1": stale}})
        figures = ("screen", "L", "fp_cap", "c_XS", "c_margin")
        self.assertEqual([stale[k] for k in figures], [kept[k] for k in figures], "it fits the receipt as the first does")
        self.assertIs(self.look(second), True)
        self.assertEqual(self.world.screen.floors, 2, "computed again from the segments this attempt ran")
        now = self.state(second)[elane_xs.FLOOR_KEY]["1"]
        self.assertEqual((now["c_p"], now["c_used"], now["own_fp"]), (kept["c_p"], kept["c_used"], kept["own_fp"]),
                         "the record is today's floor, and the look was judged on it")
        look = self.state(second)[elane_xs.LOOK_KEY]
        self.assertNotIn("1.25", look["beside"], "the sentence states the floor it was judged on")
        # One kept under another receipt's figures is run again too (as before).
        third = self.gated("vol-a", agenda="xs_low_vol")
        self.store.set_state("vol-a", **{elane_xs.FLOOR_KEY: {"1": {**kept, "c_XS": 1.38}}})
        self.look(third)
        self.assertEqual(self.world.screen.floors, 3)
        self.assertEqual(self.state(third)[elane_xs.FLOOR_KEY]["1"]["c_XS"], kept["c_XS"])

    def test_the_same_lineage_at_the_look_is_refused_with_no_look(self):
        first = self.gated("rev-a", code=F.good(tag="one", common=0.99, family_noise="shared"))
        second = self.gated("mom-a", code=F.good(tag="two", common=0.99, family_noise="shared"), agenda="xs_momentum")
        self.assertIs(self.look(first), True)
        self.runner.calls.clear()
        self.assertIsNone(self.look(second))
        self.assertEqual(len(self.store.looks()), 1)
        self.assertNotIn("look", self.windows())
        self.assertEqual(elane_xs.lineage_spent(self.store, self.store.family("mom-a"), self.settings),
                         elane_xs.SAME_LINEAGE_XS)

    def test_the_look_waits_for_the_whole_calibrated_holdout_and_a_fresh_membership(self):
        fam = self.gated()
        F.write_manifest(self.store.root, live_from="2026-09-01", fetched_through="2026-10-08")
        self.assertIsNone(self.look(fam))
        self.assertIn("2026-10-09", self.state(fam)["gate"])
        F.ready(self.store.root)
        self.world.stale_days = 46
        self.assertIsNone(self.look(fam))
        self.assertIn("membership_max_stale_days", self.state(fam)["gate"])
        self.assertEqual((self.runner.calls, self.store.looks()), ([], []))
        self.world.stale_days = 45
        self.assertIs(self.look(fam), True)

    def test_no_identity_no_look(self):
        fam = self.gated()
        self.world.xs_sha = None
        self.assertIsNone(self.look(fam))
        self.assertEqual((self.runner.calls, self.store.looks()), ([], []))
        self.assertEqual(self.events("swarm.gate", "look_failed")[0]["stage"], "identity")

    def test_a_recorded_validation_that_no_longer_reproduces_is_validated_again_first(self):
        fam = self.gated(code=F.good(mkt=1.0))
        self.runner.market = {2025: 0.0005}  # the store was refetched: 2025 reads otherwise now
        self.assertIsNone(self.look(fam))
        state = self.state(fam)
        self.assertTrue(state[elane.VERDICTS_KEY]["1"]["stale"])
        self.assertFalse(state["gate_ready"])
        self.assertEqual(self.store.looks(), [])
        self.assertEqual(elane.next_try(self.store, self.store.family(fam["id"]), self.settings), 1, "the same try")
        self.assertTrue(self.validate(fam)["entered"])
        self.assertIs(self.look(fam), True)

    def test_a_sealed_run_that_does_not_return_is_owed_once_then_spent_and_failed(self):
        from league.equity.runner import RunLost

        fam = self.gated()
        self.runner.fail["look"] = RunLost("sent and not answered")
        self.assertIsNone(self.look(fam))
        state = self.state(fam)
        self.assertEqual((state[elane.LOST_KEY]["count"], state["gate_ready"], state.get("look_inflight")), (1, True, None))
        self.assertEqual(self.store.looks(), [])
        self.assertIs(self.look(fam), False, "the second time the look is spent and FAILED")
        self.assertEqual(len(self.store.looks()), 1)
        self.assertEqual(self.state(fam)[elane_xs.LOOK_KEY]["verdict"]["status"], "lost")
        self.assertEqual(self.world.screen.verdicts, 0)
        self.assertEqual(len(self.events("swarm.status", "equity_look_lost")), 2)

    def test_a_sealed_run_the_house_could_not_make_is_owed_again(self):
        from league.equity.runner import RunFailed

        fam = self.gated()
        self.runner.fail["look"] = RunFailed("the child could not start")
        self.assertIsNone(self.look(fam))
        self.assertIsNone(self.look(fam))
        state = self.state(fam)
        self.assertEqual((state["gate_ready"], state.get("look_inflight"), self.store.looks()), (True, None, []))
        del self.runner.fail["look"]
        self.assertIs(self.look(fam), True)

    def test_a_sealed_run_the_programs_own_errors_ended_is_spent_and_never_judged(self):
        fam = self.gated(code=F.good(status_in={"look": "disqualified"}))
        self.assertIs(self.look(fam), False)
        self.assertEqual(self.world.screen.verdicts, 0, "a partial series is never judged")
        self.assertEqual(self.state(fam)[elane_xs.LOOK_KEY]["verdict"]["status"], "disqualified")
        self.assertEqual(len(self.store.looks()), 1)
        gone = self.gated("mom-a", agenda="xs_momentum", code=F.good(tag="m", status_in={"look": "no_data"}))
        self.assertIsNone(self.look(gone), "a run the House could not make is no look")
        self.assertEqual(len(self.store.looks()), 1)

    def test_a_pass_whose_sentence_cannot_be_stated_takes_no_seat(self):
        fam = self.gated()
        self.world.screen.beside_fails = True
        self.assertIs(self.look(fam), True)
        got = self.store.family(fam["id"])
        looked = got["state"][elane_xs.LOOK_KEY]
        self.assertEqual((got["band"], looked["seat"]), ("gym", elane_xs.SEAT_UNSTATED))
        self.assertNotIn("banded_evaluator", got["state"])
        self.assertIsNone(elane_xs.lineage_spent(self.store, got, self.settings))
        self.assertTrue(self.events("swarm.status", "panel_unstated")[0]["alert"])

    def test_the_quiet_rule_holds_the_look_back(self):
        fam = self.gated()
        self.world.quiet = "inside 600 s of the 15:50 ET wall"
        self.assertIsNone(self.look(fam))
        self.assertEqual((self.runner.calls, self.store.looks()), ([], []))
        self.assertIn("15:50", self.state(fam)["gate"])


class TheClockAtValidationAndTheLook(TheLook):
    """THE CLOCK AND QUIET RULE IN VALIDATION AND THE LOOK (step two; the ship check's open item): every run of the
    Validation try (2025 at k 1.0 and 1.5), the Train segments both read, and the look's sealed run go through
    `steady`, and `may_run` is asked before EACH run. A run with a decide timeout is never read; the first steady run
    is. Timeouts that do not repeat are the House's: nothing spent, owed after a backoff, one alert at the third,
    AND THE OWE HAS AN END: the third round with the try's sealed run made spends the try, the second with the look's
    sealed run made spends and fails the look, and an owed try holds its lineage's try. Timeouts that repeat as a
    program's are SLOW: the try is spent, the look spent and failed. The look's seed and draws are the same in every
    run of the bound. Invented runtimes (the fakes' `clock`: one entry a run, in order)."""

    def clocked(self, slug, clock, **kw):
        return self.family(slug, code=F.good(tag=slug, clock=list(clock)), **kw)

    def kv(self, fid, stage):
        return ((self.store.get(elane_xs.GATE_CLOCK_KEY) or {}).get(fid) or {}).get(stage)

    def test_timeouts_in_runs_one_and_two_then_run_three_is_read(self):
        fam = self.clocked("rev-c", [0, 0, 3, 5, 0, 0])            # segments, segments, k 1.0 x3, k 1.5
        out = self.validate(fam)
        self.assertTrue(out["entered"], out)
        self.assertEqual(self.windows(), ["train", "train", "validation", "validation", "validation", "validation"])
        self.assertEqual([c["k"] for c in self.runner.calls[2:]], [1.0, 1.0, 1.0, 1.5])
        self.assertEqual(self.state(fam)[elane.TRY_KEY]["version"], 1)
        self.assertIsNone(self.kv(fam["id"], "validation"))

    def test_three_runs_that_do_not_repeat_are_owed_with_nothing_spent(self):
        fam = self.clocked("rev-d", [0, 0, 3, 5, 7] * 2)
        for attempt in range(1, 3):
            out = self.validate(fam)
            self.assertFalse(out["entered"])
            self.assertIn("the House's clock", out["waits"])
            self.assertNotIn(elane.TRY_KEY, self.state(fam), "nothing spent")
            self.assertEqual(elane.lineage_tries(self.store, fam["id"]), [])
            row = self.kv(fam["id"], "validation")
            self.assertEqual((row["version"], row["count"], row["sealed"]), (1, attempt, attempt))
            self.assertEqual(self.state(fam)[elane.VERDICTS_KEY]["1"]["owed"], elane_xs.OWED, "marked: asked first")
            self.assertEqual(elane.next_try(self.store, self.store.family(fam["id"]), self.settings), 1)
            self.assertIn("backoff", self.validate(fam)["waits"], "owed after a backoff, not at once")
            self.store.clock.advance(row["next_at"] - self.store.clock() + 1)
        self.assertEqual(self.events("swarm.status", "elane_xs_clock"), [], "no alert before the third")

    def test_the_third_round_with_the_sealed_run_made_spends_the_try(self):
        """THE OWE HAS AN END (the review of step two): a program that sees its own equity in a run could make its
        decides straddle the limit on a losing path of 2025 and never have its try counted. The third round of the
        House's clock in which the try's sealed run was made spends the try (a "clock" run, no pre-check), with an
        alert that says so."""
        fam = self.clocked("rev-d2", [0, 0, 3, 5, 7] * 3)
        for attempt in range(1, 4):
            out = self.validate(fam)
            self.assertFalse(out["entered"])
            if attempt < 3:
                self.assertIn("the House's clock", out["waits"])
                row = self.kv(fam["id"], "validation")
                self.store.clock.advance(row["next_at"] - self.store.clock() + 1)
        held = self.state(fam)[elane.TRY_KEY]
        self.assertEqual((held["version"], held["entered"], held["precheck"]), (1, False, False))
        self.assertIn("read none of the try's sealed run in 3 rounds", held["clock"])
        self.assertEqual([t["version"] for t in elane.lineage_tries(self.store, fam["id"])], [1], "the try is spent")
        self.assertEqual(self.state(fam)[elane.VALIDATION_KEY]["status"], "clock")
        self.assertFalse(self.state(fam)[elane.VERDICTS_KEY]["1"]["stale"], "the try's own verdict replaces the mark")
        self.assertIsNone(self.kv(fam["id"], "validation"))
        alerts = self.events("swarm.status", "elane_xs_clock")
        self.assertEqual([(a["stage"], a["spent"]) for a in alerts], [("validation", True)])
        self.assertIn("SPENT and failed", alerts[0]["text"])
        self.assertEqual(self.validate(fam).get("refused"), None, "the lineage's own try, read again: no new run")

    def test_a_clock_at_the_train_segments_is_owed_with_no_end_and_spends_nothing(self):
        """No sealed run is made before the try's 2025 run: a round of the House's clock at the two Train segments
        reads nothing sealed, so it never counts toward the spend."""
        fam = self.clocked("rev-d3", [3, 5, 3, 7, 3, 5] * 4)                # three pairs of segments a round
        for attempt in range(1, 5):
            out = self.validate(fam)
            self.assertIn("the House's clock", out["waits"])
            row = self.kv(fam["id"], "validation")
            self.assertEqual((row["count"], row["sealed"]), (attempt, 0))
            self.store.clock.advance(row["next_at"] - self.store.clock() + 1)
        self.assertNotIn(elane.TRY_KEY, self.state(fam))
        self.assertNotIn(elane.VERDICTS_KEY, self.state(fam))

    def test_no_other_version_of_the_lineage_takes_the_try_while_one_is_owed(self):
        """KEYED BY LINEAGE: while v1 owes its try's sealed run, its family's v2 and a family of the same lineage (the
        same code) wait, with no run made; v1 is the version `next_try` asks; once v1's try is read the lineage's try
        is v1's. A retired owing family leaves the lineage's try spent."""
        code = F.good(tag="rev-o", clock=[0, 0, 3, 5, 7])
        fam = self.family("rev-o", code=code)
        self.assertIn("the House's clock", self.validate(fam)["waits"])
        v2 = self.store.add_version(fam["id"], F.good(tag="rev-o2"), {}, author="architect:invented")
        clone = self.family("mom-o", code=code, agenda="xs_momentum")
        self.runner.calls.clear()
        for other, n in ((fam, int(v2["n"])), (clone, 1)):
            out = self.validate(other, n)
            self.assertIn("no other version takes the lineage's try", out["waits"])
            self.assertNotIn("rev-o", out["waits"], "the other family is never named")
        self.assertEqual(self.runner.calls, [], "no run made")
        self.assertEqual(elane.next_try(self.store, self.store.family(fam["id"]), self.settings), 1)
        row = self.kv(fam["id"], "validation")
        self.store.clock.advance(row["next_at"] - self.store.clock() + 1)
        self.assertTrue(self.validate(fam)["entered"], "v1's try, read this time")
        self.assertEqual(self.validate(clone)["refused"], elane.SPENT_TRY)
        lone = self.family("rev-p", code=F.good(tag="rev-p", clock=[0, 0, 3, 5, 7]))
        self.assertIn("the House's clock", self.validate(lone)["waits"])
        twin = self.family("mom-p", code=self.store.version(lone["id"], 1)["code"], agenda="xs_momentum")
        self.store.retire(lone["id"], "an invented retirement")
        self.assertEqual(self.validate(twin)["refused"], elane.SPENT_TRY, "a retired owing family: the try is spent")

    def test_timeouts_that_repeat_as_a_programs_spend_the_try_as_slow(self):
        fam = self.clocked("rev-e", [0, 0, 4, 4, 4])
        out = self.validate(fam)
        self.assertEqual((out["entered"], out["passed"]), (False, False))
        held = self.state(fam)[elane.TRY_KEY]
        self.assertEqual((held["version"], held["entered"]), (1, False))
        self.assertIn("ran past 1.00 s of wall time in each of 3 runs", held["slow"])
        self.assertEqual([t["version"] for t in elane.lineage_tries(self.store, fam["id"])], [1], "the try is spent")
        self.assertEqual(self.state(fam)[elane.VALIDATION_KEY]["status"], "slow")

    def test_no_second_run_starts_inside_a_session_wall(self):
        fam = self.clocked("rev-f", [0, 0, 3, 0, 0])
        made = self.runner.validation

        def first_then_the_wall(*args, **kw):
            run = made(*args, **kw)
            self.world.quiet = "inside 600 s of the 15:50 ET wall"
            return run

        with mock.patch.object(self.runner, "validation", first_then_the_wall):
            out = self.validate(fam)
        self.assertIn("15:50", out["waits"])
        self.assertEqual(self.windows(), ["train", "train", "validation"], "the run with a timeout, and no second")
        self.assertNotIn(elane.TRY_KEY, self.state(fam))
        self.assertTrue(all(self.world.quiet_sessions), "every run asked the whole session as its wall")

    def test_the_looks_sealed_run_reads_the_first_steady_one_with_the_same_seed(self):
        fam = self.gated("rev-g", code=F.good(tag="rev-g", clock=[0, 0, 0, 0, 0, 0, 0, 3, 0]))
        self.assertIs(self.look(fam), True)
        sealed = [c for c in self.runner.calls if c["window"] == "look"]
        self.assertEqual(len(sealed), 2)
        self.assertEqual({(c["seed"], c["placebos"]) for c in sealed}, {(sealed[0]["seed"], 999)}, "one seed, one draw")
        self.assertEqual(len(self.store.looks()), 1)

    def test_a_look_the_houses_clock_held_is_owed_with_nothing_spent(self):
        fam = self.gated("rev-h", code=F.good(tag="rev-h", clock=[0, 0, 0, 0, 0, 0, 0, 3, 5, 7]))
        self.assertIsNone(self.look(fam))
        state = self.state(fam)
        self.assertEqual((self.store.looks(), state.get("look_inflight"), state["gate_ready"]), ([], None, True))
        self.assertIn("the House's clock", state["gate"])
        self.assertEqual((self.kv(fam["id"], "look")["count"], self.kv(fam["id"], "look")["sealed"]), (1, 1))
        self.assertEqual(state[elane.LOST_KEY]["count"], 1, "one send of the sealed run")
        self.assertFalse(self.store.looked(run_sha(self.store.version(fam["id"], 1))))

    def test_a_look_the_houses_clock_held_twice_is_spent_and_failed(self):
        """THE OWE HAS AN END AT THE LOOK (E1's `LOOK_SENDS`): the sealed run was made in each round, so the second
        round of the House's clock spends the look and FAILS it, with an alert; it is never taken again."""
        clock = [0, 0, 0, 0] + [0, 0, 0, 3, 5, 7] * 2
        fam = self.gated("rev-h2", code=F.good(tag="rev-h2", clock=clock))
        self.assertIsNone(self.look(fam))
        self.store.clock.advance(self.kv(fam["id"], "look")["next_at"] - self.store.clock() + 1)
        self.assertIs(self.look(fam), False)
        looked = self.state(fam)[elane_xs.LOOK_KEY]
        self.assertEqual((looked["passed"], looked["verdict"]["status"]), (False, "clock"))
        self.assertIn("sent 2 times and none of it was read", looked["beside"])
        self.assertEqual(len(self.store.looks()), 1, "spent")
        self.assertEqual(len([c for c in self.runner.calls if c["window"] == "look"]), 6)
        alerts = [a for a in self.events("swarm.status", "elane_xs_clock") if a["stage"] == "look"]
        self.assertEqual([a["spent"] for a in alerts], [True])
        self.assertIsNone(self.look(fam), "and never taken again")

    def test_a_clock_round_and_a_lost_run_are_two_sends_of_one_look(self):
        clock = [0, 0, 0, 0] + [0, 0, 0, 3, 5, 7] + [0, 0, 0]
        fam = self.gated("rev-h3", code=F.good(tag="rev-h3", clock=clock))
        self.assertIsNone(self.look(fam))
        self.store.clock.advance(self.kv(fam["id"], "look")["next_at"] - self.store.clock() + 1)
        from league.equity.runner import RunLost

        with mock.patch.object(self.runner, "look", side_effect=RunLost("the sealed run did not return")):
            self.assertIs(self.look(fam), False)
        self.assertEqual(self.state(fam)[elane_xs.LOOK_KEY]["verdict"]["status"], "lost")

    def test_a_look_whose_timeouts_repeat_is_spent_and_failed(self):
        fam = self.gated("rev-i", code=F.good(tag="rev-i", clock=[0, 0, 0, 0, 0, 0, 0, 4, 4, 4]))
        self.assertIs(self.look(fam), False)
        looked = self.state(fam)[elane_xs.LOOK_KEY]
        self.assertEqual((looked["passed"], looked["verdict"]["status"]), (False, "slow"))
        self.assertIn(elane_xs.PROGRAM_FAILS["SLOW"], looked["beside"])
        self.assertEqual(len(self.store.looks()), 1, "spent")
        self.assertIsNone(self.look(fam), "and never taken again")


class KForABasket(GateCase):
    """K FOR A BASKET (step two; the seat rule's rank inside the panel pool, A24's counts): Train-era close days per
    250 sessions from the seen spans' full-universe 1.0x runs (`score` keeps them, sealed), and the Validation count
    from the 2025 k 1.0 run the try itself made; a day counts when the lots closed that day sum to at least 0.25 of
    the sleeve (read 0.2495). Written as `elane.SEAT_KEY` beside the try. Never printed. Every figure invented."""

    @staticmethod
    def made(lots, days, status="ok"):
        return {"status": status, "lots": lots, "daily": [[d] for d in days]}

    def test_the_counts_on_an_invented_fixture(self):
        eight = [{"exit_day": "2017-03-01", "weight": 0.125} for _ in range(8)]          # one date: a whole basket
        two = [{"exit_day": "2017-03-08", "weight": 0.125}, {"exit_day": "2017-03-08", "weight": 0.12475}]
        one = [{"exit_day": "2017-03-15", "weight": 0.2}]                                  # under a quarter
        held = [{"exit_day": None, "weight": 0.5}]                                         # still open: no date
        days = [f"2017-03-{d:02d}" for d in range(1, 21)]
        self.assertEqual(elane_xs.train_activity([self.made(eight + two + one + held, days)]),
                         {"close_days": 2, "sessions": 20}, "8 lots one date, 0.24975 at the floor, 0.20 under it")
        later = self.made([{"exit_day": "2023-05-02", "weight": 0.3}], ["2023-05-01", "2023-05-02"])
        self.assertEqual(elane_xs.train_activity([self.made(eight, days), later]), {"close_days": 2, "sessions": 22})
        spans = ((dt.date(2023, 1, 3), dt.date(2023, 12, 29)),)
        self.assertEqual(elane_xs.train_activity([self.made(eight, days), later], spans=spans),
                         {"close_days": 1, "sessions": 2}, "inside the seen spans alone")
        self.assertEqual(elane_xs.train_activity([self.made([], [], status="no_data")]), {"close_days": 0, "sessions": 0})
        with self.assertRaises(ValueError):
            elane_xs.train_activity([self.made([], days, status="disqualified")])

    def test_the_try_writes_the_seat_record_and_k_ranks_it(self):
        from league.equity import bands as equity_bands

        fam = self.family()
        n = 1
        self.store.set_state(fam["id"], **{elane_xs.ACTIVITY_KEY: {str(n): {"close_days": 160, "sessions": 1000}}})
        lots = [{"exit_day": f"2025-0{m}-1{d}", "weight": 0.125} for m in range(1, 7) for d in range(5) for _ in range(4)]
        made = self.runner.validation

        def with_lots(*args, **kw):
            run = made(*args, **kw)
            run.result["lots"] = lots if kw.get("k") == 1.0 else []
            return run

        with mock.patch.object(self.runner, "validation", with_lots):
            out = self.validate(fam)
        self.assertTrue(out["entered"], out)
        seat = self.state(fam)[elane.SEAT_KEY]
        version = self.store.version(fam["id"], n)
        self.assertEqual((seat["version"], seat["run_sha"], seat["floor"], seat["source"]),
                         (n, run_sha(version), "0.25", "panel"))
        self.assertEqual(seat["train"], {"close_days": 160, "sessions": 1000})
        self.assertEqual(seat["validation"]["close_days"], 30, "30 dates of four eighths each")
        k = equity_bands.seat_k(elane.seat_activity(self.state(fam), n, run_sha(version)))
        self.assertEqual(k, 30, "the smaller of 30 and 160 per 1000 x 250 = 40")
        text = json.dumps([e["payload"] for e in self.store.events_after(0, limit=5000)])
        self.assertNotIn("close_days", text, "K is never in a public event")
        self.assertIn(elane_xs.ACTIVITY_KEY, elane_seal.SEALED_KEYS)
        self.assertIn(elane.SEAT_KEY, elane_seal.SEALED_KEYS)

    def test_a_version_scored_before_the_count_was_kept_is_read_from_the_try_s_segments(self):
        fam = self.family(hidden=2018)
        self.assertTrue(self.validate(fam)["entered"])
        seat = self.state(fam)[elane.SEAT_KEY]
        self.assertEqual(seat["source"], "panel (Train segments, seen spans)")
        seen = sum(len(F._days(a, b)) for a, b in elane_xs.seen_spans(2018))
        self.assertGreater(seat["train"]["sessions"], 0)
        self.assertLessEqual(seat["train"]["sessions"], seen, "the hidden year's sessions are not read")

    def test_no_seat_record_for_a_try_that_did_not_enter(self):
        fam = self.family(code=F.good(tag="rev-n", edge_in={"validation": -0.002}))
        self.assertFalse(self.validate(fam)["entered"])
        self.assertNotIn(elane.SEAT_KEY, self.state(fam))


class TheA31LookHold(TheLook):
    """`elane.panel.look_rule` (the captain's A31: NO XS1 LOOK BEFORE STUDY XS1-R RULES). "hold", the policy's
    default, holds every look, nothing spent, with everything else a look needs in place; "xs1" is XS1 as built; a
    value this tree does not implement holds. Validation is never held."""

    def under(self, rule):
        settings = F.settings("gate", look_rule=rule)
        if rule is None:
            del settings["elane"]["panel"]["look_rule"]
        self.owner = F.owner(self.store, self.world, settings)
        return settings

    def test_the_policy_holds_every_look_with_the_receipt_the_permit_the_review_and_room_in_place(self):
        fam = self.gated()
        for rule in (None, "hold"):
            self.under(rule)
            self.assertIsNone(self.look(fam))
            self.assertEqual(self.state(fam)["gate"], f"waiting ({elane_xs.A31_HOLD})")
            self.assertEqual((self.runner.calls, self.store.looks()), ([], []), "no run was made and no look spent")
            self.assertTrue(self.state(fam)["gate_ready"], "the look is owed, not spent")
            self.assertIsNone(elane_xs.look_room(self.store, CELL), "the cell has room")
            self.assertIsNone(elane_xs.probed(self.store.root, fam), "the permit holds the route")
        waits = [e for e in self.events("swarm.gate", "equity_look_waits") if e["why"] == elane_xs.A31_HOLD]
        self.assertEqual(len(waits), 1, "the wait is said once for its reason")
        self.under("xs1")
        self.assertIs(self.look(fam), True, "XS1 as built: the same look runs")
        self.assertEqual(len(self.store.looks()), 1)

    def test_a_value_the_tree_does_not_implement_holds_and_says_so(self):
        fam = self.gated()
        for raw in ("xs1-rc", "XS1", 7, None, ["xs1"]):
            settings = self.under("hold")
            settings["elane"]["panel"]["look_rule"] = raw
            self.assertEqual(elane_xs.cfg(settings)["look_rule"], "hold", raw)
            self.assertIsNone(self.look(fam))
            self.assertTrue(self.state(fam)["gate"].startswith(f"waiting ({elane_xs.A31_HOLD}"), raw)
            self.assertIn("names no rule this tree implements", elane_xs.look_held(settings))
        self.assertEqual((self.runner.calls, self.store.looks()), ([], []))
        self.assertEqual((elane_xs.look_held(None), elane_xs.look_held({"elane": 3})), (elane_xs.A31_HOLD,) * 2)
        self.assertEqual(elane_xs.LOOK_RULES_BUILT, ("xs1",), "a remedy's value is added only by the code that builds it")

    def test_validation_is_not_held(self):
        self.under("hold")
        fam = self.family()
        out = self.validate(fam)
        self.assertTrue(out["entered"], out)
        self.assertEqual(self.windows(), ["train", "train", "validation", "validation"])
        self.assertEqual(self.state(fam)[elane.TRY_KEY]["version"], 1, "the lineage's try is taken")
        self.assertIsNone(self.look(fam))
        self.assertEqual(self.store.looks(), [])

    def test_the_heartbeat_and_the_report_say_why(self):
        from league.ops import dlane_report
        from league.swarm.loop import Swarm
        from types import SimpleNamespace

        for rule, said in (("hold", elane_xs.A31_HOLD), ("xs1", None)):
            settings = F.settings("gate", look_rule=rule)
            self.assertEqual(elane_xs.status(settings, self.store.root),
                             {"setting": "gate", "mode": "gate", "why": None, "look": said})
            beat = Swarm.panel_status(SimpleNamespace(settings=settings, store=self.store))
            self.assertEqual(beat["panel"]["look"], said)
            self.assertEqual(dlane_report.panel_lane(self.store.root, settings)["panel_lane"]["look"], said)

    def test_the_policy_ships_hold_and_the_default_is_hold(self):
        policy = json.loads((REPO / "league" / "swarm" / "policy.json").read_text())
        self.assertEqual(policy["elane"]["panel"]["look_rule"], "hold")
        self.assertEqual((elane_xs.DEFAULTS["look_rule"], elane_xs.cfg(None)["look_rule"]), ("hold", "hold"))
        self.assertEqual(elane_xs.LOOK_RULES, ("hold", "xs1"))


@unittest.skipUnless(F.PATCHED, F.HOLDS.format(n=4))
class ThePanelLineageHasOneTry(GateCase):
    """Seal X16: with `elane._members` reading every equity structure, a panel lineage has members, its tries are
    counted, and a fork of a tried panel family gets no second Validation run."""

    def test_a_fork_of_a_tried_panel_family_gets_no_second_validation_run(self):
        parent = self.family("rev-a", code=F.good(edge_in={"validation": -0.002}))
        self.validate(parent)
        self.assertEqual(elane._members(self.store, "rev-a"), ["rev-a"])
        fork = self.family("rev-a-fork", code=F.good(tag="fork"), parent="rev-a")
        self.assertEqual(sorted(elane._members(self.store, fork["id"])), ["rev-a", "rev-a-fork"])
        self.assertEqual(len(elane.lineage_tries(self.store, fork["id"])), 1, "the lineage's one try is taken")
        self.assertFalse(elane.try_open(self.store, fork, 1, self.settings))
        self.runner.calls.clear()
        self.assertEqual(self.validate(fork)["refused"], elane.SPENT_TRY)
        self.assertEqual(self.runner.calls, [], "no run of any kind")
        self.assertEqual(elane.lineage_spent(self.store, self.store.family(fork["id"]), self.settings), elane.SPENT_TRY)

    def test_the_tournament_and_the_gate_forward_a_panel_family(self):
        tournament = Tournament(self.store, None, self.settings, clock=self.store.clock)
        gate = Gate(self.store, None, None, self.settings, clock=self.store.clock)
        tournament.xs_runner = gate.xs_runner = self.runner
        self.family("rev-a")
        (Path(self.store.root) / "swarm.json").write_text(json.dumps({"elane": self.settings["elane"]}))
        with elane_xs._cache_lock:
            elane_xs._mode_cache.clear()
        out = tournament.equity_round()
        self.assertEqual((sorted(out["validated"]), out["validated"]["rev-a"]["screen"]), (["rev-a"], "XS1"))
        looks: dict = {"looked": [], "held": []}
        gate.equity_round(looks)
        self.assertEqual(looks["looked"], [{"family": "rev-a", "passed": True, "lane": "equity"}])
        self.assertEqual(self.store.family("rev-a")["band"], "candidate")
        self.assertEqual(elane.view(self.store.family("rev-a"), lane="equity")["screen"], "XS1")
        fork = self.family("rev-a-fork", code=F.good(tag="fork"), parent="rev-a")
        out = tournament.equity_round()
        self.assertEqual(out["retired"], [fork["id"]], "its lineage's look is spent")

    def test_an_etf_lineage_never_reads_a_panel_program(self):
        looked = self.family("rev-a")
        self.validate(looked)
        self.look(looked)
        train = {"days": [1, 2, 3, 4], "r": [0.1, -0.1, 0.2, 0.0]}
        self.assertIsNone(elane.same_lineage(self.store, {"id": "beta-x"}, "beta", "beta:tpl", train),
                          "a panel program is judged on its residual: E1's rule has nothing to compare")

    def test_elanes_settings_carry_the_panels_block_and_pin(self):
        c = elane.cfg(self.settings)
        self.assertEqual(c["panel"]["mode"], "gate")
        self.assertEqual(sorted(c["screens"]), ["beta", "equity", "equity_xs"])
        self.assertEqual(elane.STRUCTURES, store_mod.EQUITY_STRUCTURES)
        self.assertIn("the panel lane is closed", elane.card_errors(F.card(), "panel", [], F.settings("off"))[0])
        self.assertEqual(elane.card_errors(F.card(), "panel", [], self.settings), [])


@unittest.skipUnless(F.PATCHED, F.HOLDS.format(n="5 and 6"))
class ThePanelBirths(unittest.TestCase):
    """Patches 5 and 6: E2's equity pass shows the PANEL block, forwards a panel proposal to `elane_xs.admit`, and
    splits its births by structure; `cards.validate` knows a panel card."""

    def setUp(self):
        from league.swarm.architect import Architect
        from league.tests.elane_e2_fakes import FakeRouter, answer

        self.world = F.switch_on(self)
        self.store = F.new_store(self)
        F.ready(self.store.root)
        self.answers: list = []
        self.answer = answer
        self.router = FakeRouter(lambda call: self.answers.pop(0) if self.answers else answer([]))
        self.make = lambda settings: Architect(self.store, self.router, settings, clock=self.store.clock)
        self.settings = F.settings("train", e2={"max_per_pass": 4, "min_per_pass": 4})
        self.arch = self.make(self.settings)

    def proposal(self, slug, **over):
        row = {"slug": slug, "lane": "equity", "structure": "panel", "panel": "sp500", "agenda": "xs_reversal",
               "max_names": 5, "rebalance": "weekly", "weekday": 0,
               "mechanism": f"Invented mechanism {slug}: liquidity providers are paid to absorb a week of selling.",
               "rejection": "the residual at or below zero at 1.5x", "sketch": "rank the week's losers within a sector",
               "card": F.card(), "program": F.good(tag=slug)}
        row.update(over)
        return row

    def pass_(self, rows, arch=None):
        self.answers.append(self.answer(rows))
        self.store.clock.advance(7200)
        return (arch or self.arch).equity_pass()

    def test_a_panel_proposal_is_born_a_panel_family_with_its_card_its_program_and_its_own_record(self):
        out = self.pass_([self.proposal("rev-a")])
        self.assertEqual(out["born"], ["rev-a"])
        fam = self.store.family("rev-a")
        self.assertEqual((fam["structure"], fam["roots"], fam["band"]), ("panel", [], "gym"))
        spec = fam["spec"]
        self.assertEqual({k: spec[k] for k in ("lane", "agenda", "panel", "max_names", "rebalance", "weekday", "e2_route",
                                               "hidden_year", "gid")},
                         {"lane": "equity", "agenda": "xs_reversal", "panel": "sp500", "max_names": 5,
                          "rebalance": "weekly", "weekday": 0, "e2_route": F.ROUTE, "hidden_year": None, "gid": "g0"})
        from league.swarm import cards, elane_train

        card = cards.card_of(self.store, "rev-a")["card"]
        self.assertEqual({k: card.get(k) for k in ("lane", "structure", "panel", "max_names", "rebalance", "weekday")},
                         {"lane": "equity", "structure": "panel", "panel": "sp500", "max_names": 5,
                          "rebalance": "weekly", "weekday": 0})
        self.assertNotIn("symbols", card)
        self.assertEqual(cards.card_of(self.store, "rev-a")["key"]["family"], "equity:panel")
        self.assertEqual(spec["card_sha"], cards.card_sha(card))
        self.assertEqual(self.store.latest_version("rev-a")["n"], 1)
        state = fam["state"]
        self.assertEqual(state[elane_xs.STATE_KEY]["status"], "researching")
        self.assertNotIn(elane_train.STATE_KEY, state)
        born = [e["payload"] for e in self.store.events_after(0, limit=500) if e["kind"] == "swarm.born"][0]
        self.assertEqual((born["lane"], born["structure"], born["roots"], born["panel"], born["program"]),
                         ("equity", "panel", [], "sp500", "v1"))
        self.assertNotIn("hidden_year", born)
        self.assertEqual(out["panel"], {"want": 2, "born": 1})

    def test_the_request_carries_the_panel_block_only_while_the_lane_bears(self):
        self.pass_([])
        request = self.router.calls[-1]["user"]
        for part in ("THE PANEL (structure \"panel\", lane equity)", "PANEL QUOTA: of this pass's births, 2 may be panel",
                     "THE PANEL AGENDA", "THE PANEL TRAIN BAR (equity-xs-v1)", "THE PANEL CONTRACT"):
            self.assertIn(part, request)
        self.pass_([self.proposal("rev-a")])
        self.pass_([])
        self.assertEqual(self.router.calls[-1]["user"].count("PANEL TRAIN MAP"), 1, "once: after E2's own map")
        off = self.make(F.settings("off", e2={"max_per_pass": 4, "min_per_pass": 4}))
        out = self.pass_([self.proposal("rev-b")], off)
        self.assertNotIn("THE PANEL (structure", self.router.calls[-1]["user"])
        self.assertEqual(out["born"], [])
        self.assertIn("the panel lane is closed", out["refused"]["items"][0]["why"])
        self.assertNotIn("panel", out, "with the lane off the pass is E2's own")

    def test_the_passes_births_split_by_structure(self):
        from league.tests.elane_e2_fakes import proposal as etf

        rows = [self.proposal(f"rev-{i}", agenda=agenda) for i, agenda in enumerate(
            ("xs_reversal", "xs_momentum", "xs_low_vol"))]
        rows += [etf(f"etf-{i}", symbols=(sym,), mechanism=f"Invented ETF mechanism number {i}: holders of {sym} are "
                                                           "paid for overnight risk.")
                 for i, sym in enumerate(("SPY", "QQQ", "IWM"))]
        out = self.pass_(rows)
        self.assertEqual(sorted(out["born"]), ["etf-0", "etf-1", "rev-0", "rev-1"])
        whys = {item["slug"]: item["why"] for item in out["refused"]["items"]}
        self.assertIn("2 panel births are born", whys["rev-2"])
        self.assertIn("4 equity births are born", whys["etf-2"])
        self.assertEqual(out["panel"], {"want": 2, "born": 2})
        from league.swarm.elane_births import EquityQuota

        quota = EquityQuota(F.new_store(self), self.settings, now=self.store.clock())
        self.assertEqual((quota.want, quota.panel), (4, 0), "a store with no panel manifest: the pass is E2's own")
        store = F.new_store(self)
        F.ready(store.root)
        quota = EquityQuota(store, self.settings, now=store.clock())
        self.assertEqual((quota.want, quota.panel, quota.by_structure), (4, 2, True))
        for _ in range(2):
            self.assertTrue(quota.admits("equity"))
            quota.born("equity")
        self.assertIn("2 share-program births are born", quota.why_not("beta"))
        self.assertIsNone(quota.why_not("equity", "panel"), "the panel's share is not the share programs' to fill")

    def test_a_proposal_outside_the_panels_box_is_refused_with_its_reason(self):
        closed = {"status": "refuted", "versions": {"1": {"fails": ["XT1"]}}}
        for i in range(3):
            F.panel_family(self.store, f"dead-{i}", agenda="xs_52w_high", record=closed)
        F.panel_family(self.store, "busy", agenda="xs_momentum",
                       mechanism="Invented mechanism busy: winners of the last year keep winning for months.")
        tried = F.panel_family(self.store, "tried", agenda="xs_low_vol", record={
            "status": "passed", "passed_version": 1, "versions": {"1": {"fails": []}}})
        rows = [self.proposal("a", max_names=13, card=F.card(max_names=13)),
                self.proposal("b", agenda="overnight"),
                self.proposal("c", agenda="xs_52w_high"),
                self.proposal("d", agenda="xs_momentum",
                              mechanism="Invented mechanism busy: winners of the last year keep winning for months."),
                self.proposal("e", agenda="xs_low_vol", parent=tried["id"]),
                self.proposal("f", card=F.card(symbols=["AAPL"])),
                self.proposal("g", max_names=8),
                self.proposal("h", mechanism="too short")]
        out = self.pass_(rows)
        self.assertEqual(out["born"], [])
        whys = {item["slug"]: item["why"] for item in out["refused"]["items"]}
        self.assertIn("max_names", whys["a"])
        self.assertIn("THE PANEL AGENDA", whys["b"])
        self.assertIn("CLOSED", whys["c"])
        self.assertIn("in Train research: busy", whys["d"])
        self.assertIn("its one Validation try", whys["e"])
        self.assertIn("symbols", whys["f"])
        self.assertIn("different values", whys["g"])
        self.assertIn("mechanism", whys["h"])

    def test_a_program_that_does_not_fit_is_left_for_the_researcher(self):
        out = self.pass_([self.proposal("rev-a", program=F.good(names=8))])
        self.assertEqual(out["born"], ["rev-a"])
        self.assertIsNone(self.store.latest_version("rev-a"))
        refused = self.store.family("rev-a")["state"][elane_xs.STATE_KEY]["refused"]
        self.assertIn("max_names", refused[0]["why"])


@unittest.skipUnless(F.PATCHED, F.HOLDS.format(n="1, 2, 4 and 5"))
class NoStructureLiteralOutsideTheStore(unittest.TestCase):
    """Seal X16: every scope that told the equity lanes apart by spelling "etf" and "stock" out reads the store's
    tuple, so a panel family is an equity family everywhere at once."""

    LITERAL = re.compile(r"""['"]etf['"]\s*,\s*['"]stock['"]""")

    def test_no_file_of_the_swarm_spells_the_structures_out(self):
        found = []
        for path in sorted((REPO / "league" / "swarm").glob("*.py")):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if self.LITERAL.search(line):
                    found.append((path.name, number, line.strip()))
        self.assertEqual(len(found), 1, found)
        name, _, line = found[0]
        self.assertEqual(name, "store.py")
        self.assertTrue(line.startswith("EQUITY_STRUCTURES = "), line)

    def test_the_scopes_are_built_from_the_tuple(self):
        self.assertEqual(store_mod.EQUITY_STRUCTURES, ("etf", "stock", "panel"))
        self.assertEqual(store_mod.EQUITY_ONLY_SQL, "structure IN ('etf', 'stock', 'panel')")
        self.assertEqual(store_mod.OPTIONS_ONLY_SQL, "structure NOT IN ('etf', 'stock', 'panel')")
        self.assertTrue(bands.equity_seatable("panel"))

    def test_the_stall_monitors_copies_of_the_scope_know_the_panel(self):
        from league.ops import stall

        self.assertEqual(stall.OPTIONS_FAMILIES, store_mod.OPTIONS_ONLY_SQL)
        self.assertIn(store_mod.EQUITY_ONLY_SQL, stall.OPTIONS_RUNS)

    def test_the_pre_open_reads_the_stores_scope(self):
        """league/ops/preopen.py is package I's to patch (e4_patches/I.md: both of its options scopes read
        `store.OPTIONS_ONLY_SQL`). Held here once that patch is in the tree: it then spells no structure out."""
        text = (REPO / "league" / "ops" / "preopen.py").read_text()
        if "OPTIONS_ONLY_SQL" not in text:
            self.skipTest("held once package I's patch of league/ops/preopen.py is applied (e4_patches/I.md)")
        self.assertIsNone(self.LITERAL.search(text), "the pre-open spells the equity structures out")

    def test_a_panel_family_is_an_equity_family_with_no_root_and_only_in_the_equity_lane(self):
        store = F.new_store(self)
        fam = F.panel_family(store, "rev-a")
        self.assertEqual((fam["structure"], fam["roots"], fam["spec"]["roots"]), ("panel", [], []))
        self.assertEqual([f["id"] for f in store.families(lanes=LANES)], ["rev-a"])
        self.assertEqual(store.families(), [], "no options reader sees it")
        self.assertEqual([f["id"] for f in elane_seal.equity_families(store)], ["rev-a"])
        spec = {**fam["spec"], "id": "x", "structure": "panel", "mechanism": fam["mechanism"]}
        for bad in ({"lane": "beta"}, {"roots": ["SPY"]}, {"lane": None}):
            with self.assertRaises(ValueError, msg=bad):
                store.add_family({**spec, **bad}, origin="architect")
        from league.swarm import dlane

        self.assertEqual(dlane.declared_lane(store, fam), dlane.ALPHA, "never read as a direction family")

    def test_the_sealed_keys_are_the_seals(self):
        self.assertLessEqual(set(elane_xs.SEALED), set(elane_seal.SEALED_KEYS))


@unittest.skipUnless(F.PATCHED, F.HOLDS.format(n=2))
class TheBandIsCurrentOnlyUnderTheRunningCode(GateCase):
    """Seal X17: a panel band whose proof names another xs fingerprint than the release's FILES give, or another
    run_sha, has no row, whatever the kv `xs_evaluator` says and with the swarm loop stopped."""

    def setUp(self):
        super().setUp()
        self.addCleanup(self.forget)
        self.forget()
        (Path(self.store.root) / "swarm.json").write_text(json.dumps({"elane": {"mode": "gate",
                                                                                "panel": {"mode": "live"}}}))
        fam = self.family()
        self.validate(fam)
        self.assertIs(self.look(fam), True)
        self.fid = fam["id"]

    def forget(self):
        bands._xs_cache = None
        with elane_xs._cache_lock:
            elane_xs._mode_cache.clear()

    def rows(self, **kw):
        self.forget()
        return bands.read(self.store.root, lanes=LANES, **kw)

    def test_a_current_proof_under_mode_live_has_its_row_with_the_sentence(self):
        rows = self.rows()
        self.assertEqual([(r["family"], r["structure"], r["band"], r["seat"], r["symbols"]) for r in rows],
                         [(self.fid, "panel", "candidate", "seated", [])])
        self.assertEqual(rows[0]["beside"], elane_xs.beside_line(self.store.family(self.fid)))
        self.assertEqual(rows[0]["validation_r_sd_by_version"], {"1": 0.011})
        self.assertEqual(bands.roster(self.store.root, lanes=LANES)["seated"], [self.fid])

    def test_another_fingerprint_than_the_files_give_has_no_row_whatever_the_kv_says(self):
        from league.xs.identity import XS_KEY

        self.store.put(XS_KEY, {"xs": "c" * 64, "engine": "xs-engine-1"})  # what the loop adopted when it last started
        self.assertEqual(len(self.rows()), 1)
        self.world.xs_sha = "d" * 64  # a release changed an xs evidence module; the swarm loop never started again
        self.assertEqual(self.rows(), [], "the band is judged against the running release's own files")
        self.assertEqual(self.store.get(XS_KEY)["xs"], "c" * 64, "and no kv was consulted")
        self.assertEqual(self.store.family(self.fid)["band"], "candidate", "its lots keep their exits")
        self.world.xs_sha = "c" * 64
        self.assertEqual(len(self.rows()), 1)

    def test_another_program_than_the_proofs_has_no_row(self):
        proof = self.store.family(self.fid)["state"]["banded_evaluator"]
        self.store.set_state(self.fid, banded_evaluator={**proof, "run_sha": "0" * 64})
        self.assertEqual(self.rows(), [])
        self.store.set_state(self.fid, banded_evaluator={**proof, "engine": "equity-engine-1"})
        self.assertEqual(self.rows(), [], "a proof naming another engine is not a panel proof")

    def test_an_identity_that_cannot_be_computed_is_unread_never_no_row(self):
        self.world.xs_sha = None
        self.assertEqual(self.rows(), [])
        with self.assertRaises(bands.EquityUnreadable):
            self.rows(strict=True)
        state = self.store.family(self.fid)["state"]
        version = self.store._one("SELECT sha, params FROM versions WHERE family=? AND n=1", (self.fid,))
        version = {"sha": version["sha"], "params": json.loads(version["params"] or "{}")}
        self.forget()
        self.assertIsNone(bands.equity_proof_current(state, version), "unknown: nothing is retired on it")
        self.world.xs_sha = "c" * 64
        self.forget()
        self.assertIs(bands.equity_proof_current(state, version), True)
        self.world.xs_sha = "d" * 64
        self.forget()
        self.assertIs(bands.equity_proof_current(state, version), False)

    def test_under_any_mode_but_live_a_panel_candidate_is_seatless(self):
        (Path(self.store.root) / "swarm.json").write_text(json.dumps({"elane": {"mode": "gate",
                                                                                "panel": {"mode": "gate"}}}))
        self.assertEqual(self.rows(), [])
        roster = bands.roster(self.store.root, lanes=LANES)
        self.assertEqual((roster["seated"], roster["seatless"]), ([], [self.fid]))
        (Path(self.store.root) / "swarm.json").write_text(json.dumps({"elane": {"mode": "gate",
                                                                                "panel": {"mode": "live"}}}))
        F.write_twins(self.store.root, through="2026-10-06")
        self.assertEqual(self.rows(), [], "the twin marker two nights behind: live reads as gate")

    def test_an_etf_candidate_is_read_as_before(self):
        from league.swarm.evaluator import equity_fingerprint
        from league.tests.test_elane import CODE, equity_spec

        self.store.add_family(equity_spec("beta-a"), origin="seed")
        version = self.store.add_version("beta-a", CODE, {}, author="test")
        self.store.set_state("beta-a", banded_version=1, banded_at=self.store.clock(), banded_evaluator={
            "engine": "equity-engine-1", "equity_sha256": equity_fingerprint(), "run_sha": run_sha(version)})
        self.store.set_band("beta-a", "candidate", reason="a test")
        from league.equity import EQUITY_ENGINE_VERSION

        self.assertEqual(EQUITY_ENGINE_VERSION, "equity-engine-1")
        self.world.xs_sha = None
        rows = self.rows()
        self.assertEqual([r["family"] for r in rows], ["beta-a"], "an uncomputable xs identity hides no ETF row")


if __name__ == "__main__":
    unittest.main()
