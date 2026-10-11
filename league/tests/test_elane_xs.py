"""THE PANEL LANE in the swarm (release E4; league/swarm/elane_xs.py): its settings and effective mode, the live legs,
cards and agenda cells, the panel quota and the hidden year, a panel version's ONE Validation try (both Train series
kept before it, the lineage asked before it), the ONE sealed look under XS1, and the seals this package owes:
X10 (no receipt, no look), X16 (a panel lineage has one try; no structure literal outside the store) and X17 (a panel
band is current only under the running code); and the captain's A22 as the House holds it: a style-open passer takes
no band, two looks an agenda cell, the review and the contamination probe before a look. league.xs is faked at its
interfaces (league/tests/elane_xs_fakes.py); every family, program and number is invented."""

from __future__ import annotations

import datetime as dt
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
        self.assertEqual(elane_xs.SCREEN_NAME, xscreen.SCREEN)
        self.assertEqual(elane_xs.STRUCTURE, "panel")
        self.assertEqual(len(set(elane_xs.SEALED)), 8)

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

    def test_the_twin_marker(self):
        F.write_manifest(self.root, live_from="2026-09-01")
        self.assertIn("twin marker is missing", self.ready()[1], "with package J unmerged, live reads as gate")
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

    def test_without_release_e3_no_year_is_hidden(self):
        with mock.patch.dict(sys.modules, {"league.swarm.elane_folds": None}):
            self.assertIsNone(elane_xs.assign(self.store, CELL, self.settings))

    def test_the_hidden_year_rotates_over_the_panels_six_train_years_by_cell(self):
        folds = types.ModuleType("league.swarm.elane_folds")
        folds.GID0 = "g0"
        folds.mode = lambda settings: (settings.get("elane") or {}).get("memory", {}).get("mode", "off")
        folds.cell_hash = lambda cell: int(hashlib.sha256(("fold-1|" + "/".join(cell)).encode()).hexdigest()[:8], 16)
        recording = {**self.settings, "elane": {**self.settings["elane"], "memory": {"mode": "record"}}}
        with mock.patch.dict(sys.modules, {"league.swarm.elane_folds": folds}), \
                mock.patch.object(sys.modules["league.swarm"], "elane_folds", folds, create=True):
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
            for count in ("999", "119", "1000", "1,000"):  # the placebo draws and the bar on them (a year is no count)
                if where == "the contract" and count == "999":
                    continue  # XS.md (package C's) says how many portfolios the screen draws: never the bar on them
                self.assertIsNone(re.search(rf"(?<![\d.]){re.escape(count)}(?!\d)", text), (where, count))
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
    def test_an_ineligible_floor_spends_no_look(self):
        fam = self.gated()
        self.world.screen.eligible = False
        self.assertIsNone(self.look(fam))
        self.assertEqual(self.store.looks(), [])
        self.assertEqual([r["stage"] for r in self.store.refusals(fam["id"])], ["screen floor"])
        self.assertEqual(elane_xs.lineage_spent(self.store, self.store.family(fam["id"]), self.settings),
                         elane.FLOOR_INELIGIBLE)
        self.assertNotIn("look", self.windows())

    def test_the_floor_is_kept_a_version_while_it_fits_the_receipt(self):
        fam = self.gated()
        self.look(fam)
        self.assertEqual(self.world.screen.floors, 1)
        kept = self.state(fam)[elane_xs.FLOOR_KEY]["1"]
        self.assertEqual((kept["c_XS"], kept["c_used"]), (1.0, 1.0))
        second = self.gated("mom-a", agenda="xs_momentum")
        self.store.set_state("mom-a", **{elane_xs.FLOOR_KEY: {"1": {**kept, "c_p": 1.2, "c_used": 1.25}}})
        self.look(second)
        self.assertEqual(self.world.screen.floors, 1, "a floor that fits the receipt is not computed again")
        third = self.gated("vol-a", agenda="xs_low_vol")
        self.store.set_state("vol-a", **{elane_xs.FLOOR_KEY: {"1": {**kept, "c_XS": 1.38}}})
        self.look(third)
        self.assertEqual(self.world.screen.floors, 2, "one kept under another receipt's figures is run again")

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

    def test_the_ops_two_copies_of_the_scope_know_the_panel(self):
        from league.ops import stall

        self.assertEqual(stall.OPTIONS_FAMILIES, store_mod.OPTIONS_ONLY_SQL)
        self.assertIn(store_mod.EQUITY_ONLY_SQL, stall.OPTIONS_RUNS)
        self.assertIn(f"NULL AND {store_mod.OPTIONS_ONLY_SQL}",
                      " ".join((REPO / "league" / "ops" / "preopen.py").read_text().replace('"\n', "").split()).replace(
                          '" "', ""))

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
