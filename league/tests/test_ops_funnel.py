"""The daily funnel on the scoreboard (league/ops/scoreboard.py, the owner's rule 3 of Oct 3, 2026): the stages in two
windows from a store the real `SwarmStore` wrote, the chance baseline, the look's bar, the switches and the budget in
force, the private record, the public page, and a store that is missing, locked, older or slow. THE WAITS counted
apart from the holds that bar (the gate's power hold is a wait: league/swarm/gate.py), from the real gate's own rounds.
THE BUDGET IN WORDS: the page never prints a meter's research cap (the rule's constants are public, so a tapered cap
gives the meter's balance), from the budget rule's own documents on invented, round balances."""
import ast
import json
import math
import os
import random
import sqlite3
import time
import unittest
from pathlib import Path
from unittest import mock

from league import stats
from league.ops import budget as B
from league.ops import scoreboard as SB
from league.swarm import HEARTBEAT, evidence
from league.swarm import architect as SA
from league.swarm import gate as G
from league.swarm import incubator as SI
from league.swarm import researcher as RS
from league.swarm import settings as SS
from league.swarm import store as ST
from league.swarm.gate import Gate
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import result
from league.tests.test_ops_jobs import FIXTURES, Base, FakeGateway, at
from league.tests.test_swarm_rounds import RoundCase, strong, weak
from league.tests.test_swarm_store import SPEC

NOW = at("2026-10-06T23:30:00Z")
BEFORE = at("2026-09-25T12:00:00Z")  # before the record's basis: nothing written then is in the funnel
OLD = NOW - 5 * 86400
RECENT = NOW - 2 * 3600
#: A read that never ends and never yields (it takes the window's first instant, as every windowed read does).
ENDLESS = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
           "SELECT 'f' AS family, ? AS at FROM c WHERE x < 0 AND ? IS NOT NULL")
ENDLESS_GATE = ENDLESS.replace("'f' AS family, ? AS at", "? AS at, 'f' AS family, '{}' AS payload")
ENDLESS_STAGES = ENDLESS.replace("'f' AS family, ? AS at", "'f' AS family, 1 AS version, ? AS at, 'audit' AS stage")
#: What a store's own text may hold and the page may never carry.
HOSTILE = "LOOKAHEAD in SPY261009C00600000: its holdout t was 2.4 and the equity 1300"
FAMILIES = ("pre-basis", "old-never", "old-train", "old-fail", "old-look", "old-fork", "old-audit", "old-held", "new-born",
            "new-pass")
#: The look holds as the code's defaults have them, and as the page says them.
HOLDS = dict(SS.DEFAULTS["gate"]["look_holds"])
HOLDS_SAID = f"look holds: drift share {HOLDS['drift_share']:.2f}, least power {HOLDS['min_power']:.2f}"
FLOOR = {meter: B.floor_usd_day(meter) for meter in B.METERS}
FLOOR_SAID = ("In force now, research by meter: sail at the floor, claude at the floor "
              "(source: the floor, no usable budget.json).")
UNREAD_SAID = "In force now, research by meter: sail n/a, claude n/a (source: n/a)."


def no_policy(case):
    """The release's policy layer left out for a test, which then reads the code's defaults whatever the repository's
    policy.json comes to say (`PolicyLayer` reads the real one)."""
    patcher = mock.patch.object(SS, "POLICY_PATH", case.root / "no-policy.json")
    patcher.start()
    case.addCleanup(patcher.stop)


class Fixture(Base):
    """A swarm store written through the real `SwarmStore`, in three times: before the basis, five days ago and two
    hours ago.

        pre-basis  born, an eligible Train run, a test and a dollar before the basis: none of it counts
        old-never  a Train run that was not eligible
        old-train  an eligible Train run; two hours ago a second version, eligible again, tested and short of the line
        old-fail   tested and short of the line; the same version tested again two hours ago
        old-look   met the line; reviewed, audited, looked at: failed
        old-fork   the same result as old-look; looked at: failed
        old-audit  met the line; refused at the audit
        old-held   met the line; its look held (the power hold)
        new-born   born two hours ago, nothing else (an incubator read and the operator's hold are no arrival)
        new-pass   born two hours ago; met the line, looked at, passed: Candidate, then Probe
    """

    def setUp(self):
        super().setUp()
        no_policy(self)
        self.now = NOW
        self.t = BEFORE
        self.store = SwarmStore(self.root, clock=lambda: self.t)
        self.addCleanup(self.close)
        self.write()

    def close(self):
        try:
            self.store.close()
        except sqlite3.Error:
            pass

    def raw(self, sql, params=()):
        """One statement on the store's file behind the store's back (the store is closed first)."""
        self.close()
        db = sqlite3.connect(self.root / "swarm.sqlite")
        try:
            db.execute(sql, params)
            db.commit()
        finally:
            db.close()

    def family(self, fid):
        self.store.add_family({**SPEC, "id": fid}, origin="seed")
        return self.version(fid)

    def version(self, fid, note="first"):
        code = f"# {fid} {note}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\ndef decide(ctx):\n    return []\n"
        return self.store.add_version(fid, code, {}, author="seed")["n"]

    def train(self, fid, n, eligible=True):
        run = result(f"{fid}-train")
        run["summary"].update(train_score=1.0 if eligible else None, train_eligible=eligible)  # as the researcher stamps it
        self.store.add_run(fid, n, run, window="train", stress=1.0, purpose="train")

    def unseen(self, fid, n, t, days=120):
        """One unseen-year test as the tournament records it: the run at the normal spread and its 1.5x twin."""
        run = result(f"{fid}-test", window="validation", t=t, days=days)
        row = self.store.add_run(fid, n, run, window="validation", stress=1.0, purpose="validation")
        self.store.add_run(fid, n, {"run_id": f"{row['run_id']}-s15", "status": "ok", "trials": 1,
                                    "summary": dict(run["stress_1.5"])}, window="validation", stress=evidence.STRESS,
                           purpose="validation")

    def verdicts(self, judged, version=1):
        self.store.event("swarm.tournament", None, {"validation": {"queued": len(judged), "judged": {
            fid: {"version": version, "passed": passed, "mean": 0.05, "t": 2.5} for fid, passed in judged.items()}}, "board": []})

    def read(self, fid, n=1, audit="pass"):
        self.store.event("swarm.gate", fid, {"action": "review", "version": n, "verdict": "pass", "reasons": [HOSTILE]})
        self.store.event("swarm.gate", fid, {"action": "audit", "version": n, "verdict": audit, "reasons": [HOSTILE]})

    def look(self, fid, p, passed=False, n=1):
        line = {"passed": passed, "p": p, "numbers": {"pnl": -9372.0, "p": p}}
        self.store.add_look(fid, n, f"sha-{fid}", passed=passed, p_value=p, detail=line)
        self.store.event("swarm.gate", fid, {"action": "look", "version": n, "passed": passed, "_line": line})

    def write(self):
        self.family("pre-basis")
        self.train("pre-basis", 1)
        self.unseen("pre-basis", 1, 3.0)
        self.verdicts({"pre-basis": True})
        self.store.add_spend("sail_model", 99.0)

        self.t = OLD
        for fid in FAMILIES[1:8]:
            self.family(fid)
        self.train("old-never", 1, eligible=False)
        for fid in FAMILIES[2:8]:
            self.train(fid, 1)
        self.unseen("old-fail", 1, 0.5)
        self.unseen("old-look", 1, 2.5)
        self.unseen("old-fork", 1, 2.5)
        self.unseen("old-audit", 1, 2.1, days=60)
        self.unseen("old-held", 1, 2.3, days=30)
        self.verdicts({"old-fail": False, "old-look": True, "old-fork": True, "old-audit": True, "old-held": True})
        self.verdicts({"old-fail": False})  # a round with no pass: never read
        self.read("old-look")
        self.look("old-look", 0.84)
        self.read("old-fork")
        self.look("old-fork", 0.83)
        self.read("old-audit", audit="fail")
        self.store.refuse("old-audit", 1, "audit", HOSTILE)
        self.store.hold_look("old-held", 1, "sha-old-held", G.HOLD_POWER_STAGE, G.HOLD_WORDS[G.HOLD_POWER_STAGE])
        self.store.event("swarm.gate", "old-held", {"action": "look_hold", "version": 1, "stage": G.HOLD_POWER_STAGE,
                                                    "_figures": {"power": {"power": 0.11}}})
        self.store.add_spend("sail_model", 6.0, family="old-look")
        self.store.add_spend("gym_box", 4.0)

        self.t = RECENT
        self.family("new-born")
        self.family("new-pass")
        self.train("new-pass", 1)
        self.train("old-train", self.version("old-train", "second"))
        self.unseen("new-pass", 1, 3.0, days=200)
        self.unseen("old-train", 2, -1.0)
        self.unseen("old-fail", 1, 0.5)
        self.verdicts({"new-pass": True, "old-train": False, "old-fail": False})
        self.read("new-pass")
        self.look("new-pass", 0.001, passed=True)
        self.store.set_band("new-pass", "candidate", reason="its holdout look passed")
        self.store.set_band("new-pass", "probe", reason="the money table's Probe row")
        self.store.hold_gate("old-train", reason=HOSTILE)
        self.store.event("swarm.gate", "new-born", {"action": "incubator_review", "version": 1, "verdict": "pass"})
        self.store.event("swarm.gate", None, {"action": "forward", "families": 1})
        self.store.add_spend("claude", 0.5, family="new-pass")
        self.store.add_spend("sail_model", 1.5)
        self.t = NOW

    def luck(self, *days):
        return [stats._t_tail(evidence.MIN_T, n - 1) for n in days]

    def funnel(self):
        return SB.funnel(self.root, NOW, config={})


class Stages(Fixture):
    def test_window_counts_and_costs_stop_at_the_reports_timestamp(self):
        before = self.funnel()
        self.t = NOW + 3600
        self.family("future-birth")
        self.train("future-birth", 1)
        self.unseen("future-birth", 1, 0.1)
        self.verdicts({"future-birth": True})
        self.read("future-birth")
        self.look("future-birth", 0.9)
        self.store.add_spend("sail_model", 9.0)
        after = self.funnel()
        self.assertEqual(after["errors"], {})
        for key, _, _ in SB.WINDOWS:
            self.assertEqual(after["windows"][key], before["windows"][key])
        self.assertEqual(after["look"]["made"], before["look"]["made"])

    def test_each_stage_is_counted_in_both_windows_from_what_the_store_holds(self):
        record = self.funnel()
        self.assertEqual(record["errors"], {})
        self.assertEqual((record["schema"], record["at"], record["basis"]), (1, "2026-10-06T23:30:00Z", "2026-09-26T06:25:30Z"))
        whole, day = record["windows"]["since_basis"], record["windows"]["last_24h"]
        self.assertEqual((whole["since"], day["since"]), ("2026-09-26T06:25:30Z", "2026-10-05T23:30:00Z"))
        stages = ("born", "train_eligible", "tested", "met_line", "gate", "bands", "demoted")
        self.assertEqual({k: whole[k] for k in stages},
                         {"born": 9, "train_eligible": 7, "tested": {"families": 7, "versions": 7, "runs": 8}, "met_line": 5,
                          "gate": {"arrived": 5, "refused": {"audit": 1}, "held": {G.HOLD_POWER_STAGE: 1}, "waited": 0,
                                   "looked": 3, "passed": 1},
                          "bands": {"candidate": 1, "probe": 1, "sized": 0}, "demoted": 0})
        self.assertEqual({k: day[k] for k in stages},
                         {"born": 2, "train_eligible": 2, "tested": {"families": 3, "versions": 3, "runs": 3}, "met_line": 1,
                          "gate": {"arrived": 1, "refused": {}, "held": {}, "waited": 0, "looked": 1, "passed": 1},
                          "bands": {"candidate": 1, "probe": 1, "sized": 0}, "demoted": 0})
        self.assertEqual(record["bands_now"], {"candidate": 0, "probe": 1, "sized": 0})
        self.assertEqual(record["waiting_now"], 0, "the fixture's hold is a row from before the power hold was a wait")

    def test_research_dollars_are_the_swarms_booked_spend_and_its_cost_a_stage(self):
        record = self.funnel()
        self.assertEqual(record["windows"]["since_basis"]["usd"],
                         {"booked": 12.0, "by_kind": {"claude": 0.5, "gym_box": 4.0, "sail_model": 7.5},
                          "per_birth": round(12 / 9, 4), "per_test": 1.5, "per_gate_arrival": 2.4, "per_look": 4.0})
        self.assertEqual(record["windows"]["last_24h"]["usd"],
                         {"booked": 2.0, "by_kind": {"claude": 0.5, "sail_model": 1.5}, "per_birth": 1.0,
                          "per_test": round(2 / 3, 4), "per_gate_arrival": 2.0, "per_look": 2.0})

    def test_a_cost_a_stage_nothing_reached_is_not_a_number(self):
        self.raw("DELETE FROM looks")
        usd = self.funnel()["windows"]["since_basis"]["usd"]
        self.assertEqual((usd["per_look"], usd["per_birth"]), (None, round(12 / 9, 4)))

    def test_the_gates_own_housekeeping_is_no_arrival_and_a_family_at_the_gate_met_its_line(self):
        record = self.funnel()
        self.assertEqual(record["windows"]["last_24h"]["gate"]["arrived"], 1, "an incubator read and the operator's hold are none")
        # A verdict that landed after its round stopped waiting is in no round's event: the gate taking the family up says it.
        self.t = NOW - 60
        self.store.event("swarm.gate", "old-train", {"action": "review", "version": 2, "verdict": "pass", "reasons": []})
        day = self.funnel()["windows"]["last_24h"]
        self.assertEqual((day["met_line"], day["gate"]["arrived"]), (2, 2))

    def test_a_family_is_at_the_line_and_the_gate_in_the_window_where_a_program_of_its_first_got_there(self):
        """A later step on a program that was at the gate before, or its verdict judged again, is no second arrival: a
        family is on the day's page for the gate once a program, never once a day it is touched."""
        self.t = NOW - 60
        self.store.event("swarm.gate", "old-held", {"action": "audit", "version": 1, "verdict": "pass", "reasons": []})
        self.verdicts({"old-look": True})  # judged again from its recorded result (`Tournament.validate`), no new test
        self.store.refuse("old-fork", 1, "review", HOSTILE)
        self.store.hold_look("old-audit", 1, "sha-old-audit", G.HOLD_POWER_STAGE, HOSTILE)
        record = self.funnel()
        whole, day = record["windows"]["since_basis"], record["windows"]["last_24h"]
        self.assertEqual((day["met_line"], day["gate"]["arrived"]), (1, 1), "new-pass alone: the others got there five days ago")
        self.assertEqual((whole["met_line"], whole["gate"]["arrived"]), (5, 5))
        self.assertEqual((day["gate"]["refused"], day["gate"]["held"]), ({"review": 1}, {G.HOLD_POWER_STAGE: 1}),
                         "a refusal and a hold are counted where they happen")
        self.assertEqual(day["usd"]["per_gate_arrival"], 2.0)
        # A second program of a family that was there before is an arrival of its own: at the line, then at the gate.
        self.verdicts({"old-look": True}, version=self.version("old-look", "second"))
        day = self.funnel()["windows"]["last_24h"]
        self.assertEqual((day["met_line"], day["gate"]["arrived"]), (2, 1))
        self.store.refuse("old-look", 2, "experiment contract", HOSTILE)  # a refusal the gate writes no event for
        record = self.funnel()
        whole, day = record["windows"]["since_basis"], record["windows"]["last_24h"]
        self.assertEqual((day["met_line"], day["gate"]["arrived"]), (2, 2))
        self.assertEqual((whole["met_line"], whole["gate"]["arrived"]), (5, 5), "a family is one family since the basis")

    def test_a_look_from_before_the_basis_counts_under_holm_and_is_no_arrival_of_the_record(self):
        """Holm counts every look ever made. The record's arrivals are a program's first step inside the record, as every
        other read of the gate runs from the basis."""
        self.t = BEFORE
        self.look("pre-basis", 0.5)
        self.t = NOW - 60
        self.store.event("swarm.gate", "pre-basis", {"action": "audit", "version": 1, "verdict": "pass", "reasons": []})
        record = self.funnel()
        whole, day = record["windows"]["since_basis"], record["windows"]["last_24h"]
        self.assertEqual((record["look"]["made"], whole["gate"]["looked"]), (4, 3))
        self.assertEqual((whole["gate"]["arrived"], day["gate"]["arrived"]), (6, 2))

    def test_a_demotion_is_never_an_entry_into_the_lower_band(self):
        self.t = OLD
        for band in ("candidate", "probe", "sized"):
            self.store.set_band("old-look", band, reason="up, five days ago")
        self.t = NOW - 60
        self.store.set_band("old-look", "probe", reason="the money table's demotion")
        self.store.set_band("old-look", "candidate", reason="the money table's demotion")
        self.store.set_band("new-pass", "candidate", reason="its forward record turned negative")
        self.store.set_band("new-pass", "probe", reason="the money table's Probe row, again")
        self.store.set_band("old-fork", "candidate", reason="up")
        self.store.set_band("old-fork", "gym", reason="back to the Gym")
        record = self.funnel()
        whole, day = record["windows"]["since_basis"], record["windows"]["last_24h"]
        self.assertEqual((whole["bands"], whole["demoted"]), ({"candidate": 3, "probe": 2, "sized": 1}, 3))
        self.assertEqual((day["bands"], day["demoted"]), ({"candidate": 2, "probe": 1, "sized": 0}, 3),
                         "new-pass entered Probe twice today and is one family; no demotion is an entry")
        self.assertEqual(record["bands_now"], {"candidate": 1, "probe": 1, "sized": 0})
        text = "\n".join(SB.funnel_lines(record))
        for line in ("| Families that moved up to Candidate | 3 | 2 |", "| Families that moved up to Probe | 2 | 1 |",
                     "| Families that moved up to Sized | 1 | 0 |", "| Families that moved down a band | 3 | 3 |"):
            self.assertIn(line, text)
        # A move whose bands the event does not name is neither an entry nor a demotion.
        self.store.event("swarm.band", "old-audit", {"band_to": "sized", "reason": "no band it came from"})
        self.store.event("swarm.band", "old-audit", {"band_from": "sized", "band_to": HOSTILE})
        again = self.funnel()["windows"]["last_24h"]
        self.assertEqual((again["bands"], again["demoted"]), (day["bands"], day["demoted"]))

    def test_only_a_completed_run_at_the_normal_spread_is_a_test_or_an_eligible_train_run(self):
        self.t = NOW - 60
        for status in ("error", "disqualified"):
            run = result(f"new-born-{status}", window="validation", t=3.0, days=100, status=status)
            self.store.add_run("new-born", 1, run, window="validation", stress=1.0, purpose="validation")
        for status, stress in (("ok", evidence.STRESS), ("ok", 0.0), ("error", 1.0), ("disqualified", 1.0)):
            run = result(f"old-never-{status}-{stress}", status=status)
            run["summary"].update(train_score=1.0, train_eligible=True)
            self.store.add_run("old-never", 1, run, window="train", stress=stress, purpose="train")
        self.assertEqual(self.store._one("SELECT COUNT(*) AS n FROM runs WHERE at >= ?", (SB.S.iso(NOW - 60),))["n"], 6)
        day = self.funnel()["windows"]["last_24h"]
        self.assertEqual((day["tested"], day["chance"]["versions"], day["train_eligible"]),
                         ({"families": 3, "versions": 3, "runs": 3}, 3, 2))

    def test_an_eligible_train_run_is_found_as_the_store_writes_it(self):
        """The read finds the flag in the summary text as `SwarmStore.add_run` serialises it."""
        row = self.store._one("SELECT summary FROM runs WHERE family='old-look' AND window='train'")
        self.assertIn('"train_eligible":true', row["summary"])
        row = self.store._one("SELECT summary FROM runs WHERE family='old-never' AND window='train'")
        self.assertIn('"train_eligible":false', row["summary"])

    def test_the_windows_run_from_the_basis_and_from_a_day_ago(self):
        self.assertEqual(SB.windows(NOW), {"since_basis": ("2026-09-26T06:25:30Z", at("2026-09-26T06:25:30Z")),
                                           "last_24h": ("2026-10-05T23:30:00Z", NOW - 86400)})
        early = SB.windows(at("2026-09-26T12:00:00Z"))
        self.assertEqual(early["last_24h"], early["since_basis"], "never before the basis")
        self.assertEqual(SB.FS, B.PNL_BASIS)


class Chance(Fixture):
    def test_the_t_check_by_luck_alone_against_how_many_cleared_it(self):
        record = self.funnel()
        luck = self.luck(120, 120, 120, 60, 30, 200, 120)
        self.assertEqual(record["windows"]["since_basis"]["chance"],
                         {"t": 2.0, "versions": 7, "cleared": 5, "by_luck": round(sum(luck), 2),
                          "by_luck_sd": round(math.sqrt(sum(p * (1 - p) for p in luck)), 2),
                          "distinct": {"results": 6, "cleared": 4, "by_luck": round(sum(luck) - luck[0], 2)}})
        day = self.luck(200, 120, 120)
        self.assertEqual(record["windows"]["last_24h"]["chance"]["by_luck"], round(sum(day), 2))
        self.assertEqual((record["windows"]["last_24h"]["chance"]["versions"], record["windows"]["last_24h"]["chance"]["cleared"]),
                         (3, 1))
        # One test's chance is Student's upper tail at the line's t: about one in forty, a little more on few days.
        self.assertTrue(0.0228 < self.luck(200)[0] < self.luck(120)[0] < self.luck(30)[0] < 0.03)

    def test_a_version_tested_again_is_one_trial_and_its_newest_run_is_its_test(self):
        self.t = NOW - 60
        self.unseen("old-look", 1, 0.1)   # cleared five days ago, short of it today
        self.unseen("old-fail", 1, 2.6)   # short of it twice, clear today
        self.unseen("old-audit", 1, 0.2, days=60)
        record = self.funnel()
        whole, day = record["windows"]["since_basis"]["chance"], record["windows"]["last_24h"]["chance"]
        self.assertEqual((whole["versions"], whole["cleared"]), (7, 4), "old-look and old-audit no longer clear; old-fail does")
        self.assertEqual((day["versions"], day["cleared"]), (5, 2))
        self.assertEqual(record["windows"]["since_basis"]["tested"], {"families": 7, "versions": 7, "runs": 11})

    def test_a_test_without_a_t_or_with_one_traded_day_is_no_trial_of_luck(self):
        self.t = NOW - 600
        for fid, days in (("old-never", 1), ("new-born", 0)):
            self.unseen(fid, 1, 2.6, days=days)
        chance = self.funnel()["windows"]["since_basis"]["chance"]
        self.assertEqual((chance["versions"], chance["cleared"]), (7, 5))
        self.assertEqual(self.funnel()["windows"]["since_basis"]["tested"], {"families": 9, "versions": 9, "runs": 10})


class LookBar(unittest.TestCase):
    THREE = [(False, 0.836), (False, 0.831), (False, 0.996)]

    def test_three_failed_looks_set_the_fourths_level_and_what_the_power_hold_asks(self):
        bar = SB.look_bar(self.THREE, in_flight=0, min_power=0.30, sessions=184)
        self.assertEqual((bar["made"], bar["passed"], bar["in_flight"], bar["alpha"]), (3, 0, 0, 0.05))
        self.assertEqual(bar["next_level"], 0.0125)
        self.assertEqual(bar["next_level"], round(evidence.holm_level([p for _, p in self.THREE]), 6))
        self.assertEqual(bar["level_spent"], round(0.05 + 0.05 / 2 + 0.05 / 3, 6))
        self.assertEqual((bar["sharpe_yearly_for_hold"], bar["sharpe_yearly_even_chance"]), (2.01, 2.62))
        # The hold's own figure at that Sharpe is its line, and a hair under it is held.
        daily = SB.sharpe_for_power(0.30, 184, 0.0125)
        self.assertAlmostEqual(evidence.holdout_power(daily, 184, 0.0125), 0.30, places=9)
        self.assertLess(evidence.holdout_power(daily - 1e-6, 184, 0.0125), 0.30)
        self.assertEqual(bar["sharpe_daily_for_hold"], round(daily, 4))

    def test_no_look_yet_a_look_in_flight_and_a_passed_look(self):
        none = SB.look_bar([], min_power=0.30, sessions=184)
        self.assertEqual((none["made"], none["next_level"], none["level_spent"]), (0, 0.05, 0.0))
        flying = SB.look_bar(self.THREE, in_flight=1, min_power=0.30, sessions=184)
        self.assertEqual(flying["next_level"], 0.01, "a look in flight counts as a failed one, as the gate's hold counts it")
        self.assertGreater(flying["sharpe_yearly_for_hold"], 2.01)
        won = SB.look_bar([(False, 0.84), (True, 0.001)], min_power=0.30, sessions=184)
        self.assertEqual((won["made"], won["passed"]), (2, 1))
        self.assertEqual(won["next_level"], round(evidence.holm_level([0.84, 0.001]), 6))
        self.assertEqual(won["level_spent"], round(evidence.holm_level([]) + evidence.holm_level([0.84]), 6))

    def test_what_cannot_be_figured_is_none(self):
        off = SB.look_bar(self.THREE, min_power=None, sessions=184)
        self.assertEqual((off["sharpe_yearly_for_hold"], off["sharpe_daily_for_hold"]), (None, None))
        self.assertEqual(off["sharpe_yearly_even_chance"], 2.62)
        lost = SB.look_bar(self.THREE, min_power=0.30, sessions=None)
        self.assertEqual((lost["sharpe_yearly_for_hold"], lost["sharpe_yearly_even_chance"], lost["next_level"]), (None, None, 0.0125))
        for power in (0.0, 1.0, None, "x", True):
            self.assertIsNone(SB.sharpe_for_power(power, 184, 0.0125))
        self.assertLess(SB.sharpe_for_power(0.005, 184, 0.0125), 0.0, "a line under the test's own level asks for no edge")


class LooksInTheStore(Fixture):
    def test_the_funnel_reads_the_looks_and_the_look_in_flight_from_the_store(self):
        look = self.funnel()["look"]
        self.assertEqual((look["made"], look["passed"], look["in_flight"], look["sessions"], look["min_power"]),
                         (3, 1, 0, G.holdout_sessions(), HOLDS["min_power"]))
        self.assertEqual(look["next_level"], round(evidence.holm_level([0.84, 0.83, 0.001]), 6))
        # The looks in the order they were made: each was tested with the looks before it, never the ones after.
        self.assertEqual(look["level_spent"], round(0.05 + 0.05 / 2 + 0.05 / 3, 6))
        self.assertNotEqual(look["level_spent"], SB.look_bar([(True, 0.001), (False, 0.83), (False, 0.84)])["level_spent"])
        self.store.set_state("old-train", look_inflight={"sha": "s" * 64, "n": 2, "at": NOW - 60})
        self.store.set_state("new-born", look_inflight=None)                          # a marker cleared
        self.store.set_state("old-never", look_inflight={"n": 1, "at": NOW - 60})     # one that names no look
        self.store.set_state("old-audit", review={"look_inflight": {"sha": "u" * 64}})  # not the family's own marker
        self.store.retire("old-fail", "a test retirement of this family")
        self.store.set_state("old-fail", look_inflight={"sha": "t" * 64, "n": 1, "at": NOW - 60})
        record = self.funnel()
        look = record["look"]
        self.assertEqual(sorted(fid for fid, _ in self.store.looks_inflight()), ["old-fail", "old-train"])
        self.assertEqual(look["in_flight"], 2, "as the gate's own hold counts them: a retired family's look is still out")
        self.assertEqual(look["next_level"], round(evidence.holm_level([0.84, 0.83, 0.001, 1.0, 1.0]), 6))
        self.assertIn("Looks made: 3; passed: 1; in flight: 2. The next look (number 6) is tested at the ",
                      "\n".join(SB.funnel_lines(record)))

    def running_gate(self, started):
        """The gate of a swarm that started at `started` and is asked at NOW, with the heartbeat such a swarm writes (the
        page, another process, takes the swarm's start from it)."""
        (self.root / HEARTBEAT).write_text(json.dumps({"pid": 1, "at": NOW - 5, "started_at": started}))
        clock = mock.Mock(return_value=started)
        gate = Gate(self.store, None, None, SS.load(self.root, config={}), clock=clock)
        clock.return_value = NOW
        return gate

    def test_the_bar_is_the_one_the_gates_own_hold_applies(self):
        """The level the page says the next look faces is the level `Gate.look_hold` holds a version at: a look REALLY
        in flight counts, a retired family's included, and a stale marker never does (one a dead process left, one
        whose look never came back in the time a look is given, one whose time cannot be read: `gate.marker_stale`,
        the one rule both read)."""
        started = NOW - 3600
        limit = SS.run_timeout(SS.load(self.root, config={})) + 1200
        self.assertLess(limit, 3600 - 600, "the fixture's marker past the limit was set after the swarm started")
        self.store.set_state("old-train", look_inflight={"sha": "s" * 64, "n": 2, "at": NOW - 60})
        self.store.retire("old-fail", "retired while its look was out")
        self.store.set_state("old-fail", look_inflight={"sha": "t" * 64, "n": 1, "at": NOW - 60})
        self.store.set_state("old-held", validation_version=1, validation_numbers={"sharpe_daily": 0.01})
        gate = self.running_gate(started)
        hold = gate.look_hold(self.store.family("old-held"), 1)
        figures = hold["figures"]["power"]
        look = self.funnel()["look"]
        self.assertEqual((figures["inflight_elsewhere"], look["in_flight"]), (2, 2))
        self.assertEqual(look["next_level"], round(figures["level"], 6))
        self.assertEqual((look["sessions"], look["min_power"]), (figures["sessions"], figures["line"]))
        # Three stale markers beside them: neither the gate's hold nor the page counts one, and the level is the same.
        self.store.set_state("old-look", look_inflight={"sha": "v" * 64, "n": 1, "at": started - 60})     # a dead process's
        self.store.set_state("old-fork", look_inflight={"sha": "w" * 64, "n": 1, "at": NOW - limit - 60})  # never came back
        self.store.set_state("old-audit", look_inflight={"sha": "x" * 64, "n": 1, "at": "soon"})          # no time to read
        self.assertEqual(len(self.store.looks_inflight()), 5)
        again = gate.look_hold(self.store.family("old-held"), 1)["figures"]["power"]
        stale = self.funnel()["look"]
        self.assertEqual((again["inflight_elsewhere"], stale["in_flight"]), (2, 2), "five markers, two looks")
        self.assertEqual((stale["next_level"], again["level"]), (look["next_level"], figures["level"]))
        self.assertEqual(sorted(gate.flying_elsewhere("old-held")), ["old-fail", "old-train"])
        # The swarm restarted a minute ago: every marker is a dead process's, to the gate and to the page.
        gate = self.running_gate(NOW - 30)
        restarted = gate.look_hold(self.store.family("old-held"), 1)["figures"]["power"]
        look = self.funnel()["look"]
        self.assertEqual((restarted["inflight_elsewhere"], look["in_flight"]), (0, 0))
        self.assertEqual(look["next_level"], round(restarted["level"], 6))
        self.assertGreater(look["next_level"], stale["next_level"], "no look in flight: the next look's level is higher")

    def test_with_no_start_to_read_the_page_judges_a_marker_by_the_time_a_look_is_given(self):
        """The page is another process: it takes the swarm's start from the swarm's heartbeat. With none to read (no
        swarm has written one on this state, a file that is no JSON, a start that is no number) only the time limit is
        judged, so the page's count is never under the gate's."""
        limit = SS.run_timeout(SS.load(self.root, config={})) + 1200
        self.store.set_state("old-train", look_inflight={"sha": "s" * 64, "n": 2, "at": NOW - 60})
        self.store.set_state("old-fork", look_inflight={"sha": "w" * 64, "n": 1, "at": NOW - limit - 1})
        self.store.set_state("old-audit", look_inflight={"sha": "x" * 64, "n": 1, "at": None})
        self.assertFalse((self.root / HEARTBEAT).exists())
        self.assertEqual(self.funnel()["look"]["in_flight"], 1, "inside the time a look is given: counted")
        for unread in ("not json", json.dumps([1]), json.dumps({"started_at": "x"}), json.dumps({"started_at": True}),
                       json.dumps({"started_at": math.inf}), json.dumps({"at": NOW})):
            (self.root / HEARTBEAT).write_text(unread)
            record = self.funnel()
            self.assertEqual((record["look"]["in_flight"], record["errors"]), (1, {}), unread)
        (self.root / HEARTBEAT).write_text(json.dumps({"started_at": NOW - 61}))
        self.assertEqual(self.funnel()["look"]["in_flight"], 1, "set a second after the swarm started")
        (self.root / HEARTBEAT).write_text(json.dumps({"started_at": NOW - 59}))
        self.assertEqual(self.funnel()["look"]["in_flight"], 0, "set a second before it: a dead process's marker")
        self.assertEqual(SB.flying([NOW - 60, NOW - 59, NOW - 58, None, "x", True], self.root, NOW, {}), 2)

    def test_the_time_a_look_is_given_is_the_one_the_swarm_reads_from_its_settings(self):
        """The page reads the run timeout as the swarm reads it (`<state>/swarm.json` over the release's), so a longer
        limit the operator set keeps a slow look counted on the page as it is at the gate."""
        default = SS.run_timeout(SS.load(self.root, config={})) + 1200
        self.store.set_state("old-train", look_inflight={"sha": "s" * 64, "n": 2, "at": NOW - default - 60})
        self.assertEqual(self.funnel()["look"]["in_flight"], 0)
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"run_timeout_seconds": default}}))
        settings = SS.load(self.root, config={})
        self.assertEqual(SS.run_timeout(settings), default)
        self.assertEqual(self.funnel()["look"]["in_flight"], 1)
        self.assertFalse(G.marker_stale({"at": NOW - default - 60}, started_at=-math.inf, now=NOW, settings=settings))


class Switches(Base):
    def setUp(self):
        super().setUp()
        no_policy(self)

    def test_the_defaults_in_force(self):
        self.assertEqual(SB.switches(self.root, {}), {"gate.look_holds": HOLDS, "tournament.drift_screen": True,
                                                      "live.incubator": False, "policy": "absent"})


    def test_the_owners_file_moves_them_and_a_misread_brake_is_its_default(self):
        (self.root / "swarm.json").write_text(json.dumps({
            "gate": {"look_holds": {"drift_share": None, "min_power": 0.5}}, "tournament": {"drift_screen": False},
            "live": {"incubator": True}}))
        self.assertEqual(SB.switches(self.root, {}), {"gate.look_holds": {"drift_share": None, "min_power": 0.5},
                                                      "tournament.drift_screen": False, "live.incubator": True, "policy": "absent"})
        (self.root / "swarm.json").write_text(json.dumps({
            "gate": {"look_holds": None}, "tournament": {"drift_screen": 0}, "live": {"incubator": "yes"}}))
        self.assertEqual(SB.switches(self.root, {}), {"gate.look_holds": {"drift_share": None, "min_power": None},
                                                      "tournament.drift_screen": True, "live.incubator": False, "policy": "absent"})
        (self.root / "swarm.json").write_text(json.dumps({"gate": {"look_holds": {"min_power": 7, "drift_share": "x"}}}))
        self.assertEqual(SB.switches(self.root, {})["gate.look_holds"],
                         {"drift_share": evidence.LOOK_HOLD_DRIFT_SHARE, "min_power": evidence.LOOK_HOLD_MIN_POWER})

    def test_the_incubator_is_on_only_by_the_owners_own_file_as_the_live_path_reads_it(self):
        config = {"swarm": {"live": {"incubator": True}, "tournament": {"drift_screen": False}}}
        on = SB.switches(self.root, config)
        self.assertEqual((on["live.incubator"], on["tournament.drift_screen"]), (False, False),
                         "the live path never reads `live` from the release's config; the swarm reads the rest from it")
        (self.root / "swarm.json").write_text(json.dumps({"live": {"incubator": True}}))
        self.assertIs(SB.switches(self.root, config)["live.incubator"], True)
        (self.root / "swarm.json").write_text("not json")
        self.assertIs(SB.switches(self.root, config)["live.incubator"], False)

    def test_the_funnel_takes_the_power_holds_line_from_the_switch_in_force(self):
        (self.root / "swarm.json").write_text(json.dumps({"gate": {"look_holds": {"min_power": 0.5}}}))
        SwarmStore(self.root, clock=lambda: NOW).close()
        record = SB.funnel(self.root, NOW, config={})
        self.assertEqual(record["errors"], {})
        self.assertEqual((record["look"]["min_power"], record["look"]["next_level"]), (0.5, 0.05))
        self.assertEqual(record["look"]["sharpe_yearly_for_hold"], record["look"]["sharpe_yearly_even_chance"])
        (self.root / "swarm.json").write_text(json.dumps({"gate": {"look_holds": None}}))
        record = SB.funnel(self.root, NOW, config={})
        self.assertIsNone(record["look"]["sharpe_yearly_for_hold"])
        self.assertIn("The power hold is off.", "\n".join(SB.funnel_lines(record)))
        self.assertIn("look holds: drift share off, least power off;", "\n".join(SB.funnel_lines(record)))


class PolicyLayer(Base):
    def test_the_releases_own_policy_is_read(self):
        """Each switch is what the swarm's own reader makes of `settings.load`, the release's policy layer included."""
        from league.swarm.researcher import drift_settings

        effective = SS.load(self.root, config={})
        on = SB.switches(self.root, {})
        self.assertEqual(on["policy"], "ok")
        self.assertEqual((on["gate.look_holds"]["drift_share"], on["gate.look_holds"]["min_power"]), G.look_hold_settings(effective))
        self.assertEqual(on["tournament.drift_screen"], drift_settings(effective) is not None)
        self.assertIs(on["live.incubator"], False, "no swarm.json: off")


class BudgetInForce(Base):
    def test_without_a_file_the_floor_and_with_one_its_meters(self):
        block = SB.budget_in_force(self.root, NOW)
        self.assertEqual((block["source"], block["sail_usd_day"], block["claude_usd_day"], block["why"]),
                         ("floor", FLOOR["sail"], FLOOR["claude"], "no budget.json yet"))
        self.assertEqual(SB.budget_in_force_line(block), FLOOR_SAID)
        written = {"schema": B.SCHEMA, "at": NOW - 3600, "state": "research at floor + profit share",
                   "meters": {"sail": {"research_usd_day": 7.5, "fixed_usd_day": 1.0, "balance_usd": 999.0},
                              "claude": {"research_usd_day": 4.25, "balance_usd": 888.0}}}
        (self.root / "budget.json").write_text(json.dumps(written))
        block = SB.budget_in_force(self.root, NOW)
        self.assertEqual((block["source"], block["sail_usd_day"], block["claude_usd_day"]), ("budget.json", 7.5, 4.25),
                         "the private record keeps the dollars")
        line = SB.budget_in_force_line(block)
        self.assertEqual(line, "In force now, research by meter: sail tapering, claude tapering (source: budget.json).")
        for figure in ("7.5", "4.25", "7.50"):
            self.assertNotIn(figure, line, "THE BUDGET IN WORDS: the page never prints a research cap")
        self.assertNotIn("999", json.dumps(block))
        (self.root / "budget.json").write_text(json.dumps({**written, "at": NOW - B.STALE_SECONDS - 60}))
        block = SB.budget_in_force(self.root, NOW)
        stale = (min(FLOOR["sail"], 7.5), min(FLOOR["claude"], 4.25))
        self.assertEqual((block["sail_usd_day"], block["claude_usd_day"]), stale)
        self.assertEqual(SB.budget_in_force_line(block),
                         "In force now, research by meter: sail at most the floor, claude at most the floor "
                         "(source: a stale budget.json, never above the floor).")

    def test_each_meters_words_are_read_against_its_own_share_of_the_ceiling(self):
        ceiling = {meter: B.ceiling_usd_day(meter) for meter in B.METERS}
        for meter in B.METERS:
            self.assertEqual(SB.meter_in_force(meter, ceiling[meter], "budget.json"), "at the ceiling")
            self.assertEqual(SB.meter_in_force(meter, ceiling[meter] + 5.0, "budget.json"), "at the ceiling")
            self.assertEqual(SB.meter_in_force(meter, ceiling[meter] - 0.5, "budget.json"), "tapering")
            self.assertEqual(SB.meter_in_force(meter, 0.01, "budget.json"), "tapering")
            self.assertEqual(SB.meter_in_force(meter, 0.0, "budget.json"), "none")
            self.assertEqual(SB.meter_in_force(meter, 0.0, "floor"), "none")
            self.assertEqual(SB.meter_in_force(meter, FLOOR[meter], "floor"), "at the floor")
            self.assertEqual(SB.meter_in_force(meter, 0.5, "stale budget.json"), "at most the floor")
            for usd, source in ((None, "budget.json"), ("7.5", "budget.json"), (True, "floor"), (float("nan"), "floor"),
                                (7.5, None), (7.5, HOSTILE), (7.5, ["floor"]), (7.5, "unavailable")):
                self.assertEqual(SB.meter_in_force(meter, usd, source), "n/a", (usd, source))
        self.assertEqual(SB.meter_in_force("another meter", 7.5, "budget.json"), "n/a", "no share to compare with")
        written = {"schema": B.SCHEMA, "at": NOW - 3600, "meters": {
            "sail": {"research_usd_day": ceiling["sail"]}, "claude": {"research_usd_day": 0.0}}}
        (self.root / "budget.json").write_text(json.dumps(written))
        self.assertEqual(SB.budget_in_force_line(SB.budget_in_force(self.root, NOW)),
                         "In force now, research by meter: sail at the ceiling, claude none (source: budget.json).")
        for words in ("at the ceiling", "tapering", "at the floor", "at most the floor", "none", "n/a",
                      *SB.METER_WORDS.values()):
            self.assertEqual(SB.public_problems(words), [], words)

    def test_a_block_that_was_not_read_says_so(self):
        self.assertEqual(SB.budget_in_force_line(None), UNREAD_SAID)
        self.assertEqual(SB.budget_in_force_line({"source": HOSTILE, "sail_usd_day": "x", "claude_usd_day": float("nan")}),
                         UNREAD_SAID)
        self.assertEqual(SB.budget_in_force_line({"source": [HOSTILE], "sail_usd_day": 3.0, "claude_usd_day": 2.0}), UNREAD_SAID)


class BudgetInWords(Base):
    """THE BUDGET IN WORDS (the captain's L8 of Oct 3, 2026). The rule's constants are public (the ceiling, its split,
    the runway term, the reserves), so a meter's tapered research dollars a day give its balance by arithmetic. The
    page says the state in words and the rule's own dates; the dollars stay in the private record. The documents here
    are the budget rule's own (`budget.compute`) on invented, round balances."""

    @staticmethod
    def doc(sail, claude):
        return B.compute({"p30_usd": 0.0, "p30_source": "test", "edge": {"stop": False, "why": "test edge"},
                          "meters": {"sail": {"balance_usd": sail, "fixed_usd_day": 1.0, "need_usd": 0.0},
                                     "claude": {"balance_usd": claude, "fixed_usd_day": 0.0, "need_usd": 0.0}}}, now=NOW)

    def page(self, doc, funnel=None):
        return SB.build(day="2026-10-06", release="r", economics=None, deploys={}, budget=doc,
                        ladder={"binding": False, **{key: 0 for key in SB.LADDER_COUNTS}}, jobs={}, written_at="23:30Z",
                        funnel=funnel)

    def in_force(self, doc):
        (self.root / "budget.json").write_text(json.dumps(doc))
        return SB.budget_in_force(self.root, NOW)

    def forms(self, value):
        """How a dollar figure could be printed."""
        return {f"{value:.2f}", f"{value:.1f}", f"{value:.4f}", f"{value:g}", str(value)}

    def test_a_tapering_meters_cap_is_never_printed_and_its_state_and_dates_are(self):
        doc = self.doc(sail=80.0, claude=250.0)  # sail under five days of its ceiling; claude well over
        sail, claude = doc["meters"]["sail"], doc["meters"]["claude"]
        self.assertEqual((sail["limited_by"], claude["limited_by"]), ("runway", "ceiling"))
        self.assertTrue(0 < sail["research_usd_day"] < B.ceiling_usd_day("sail"))
        # The arithmetic the page must not allow: the cap and the rule's public constants give the balance back.
        self.assertAlmostEqual(sail["reserve_usd"] + B.RUNWAY_DAYS * (sail["fixed_usd_day"] + sail["research_usd_day"]), 80.0,
                               places=2)
        text = self.page(doc, {"budget": self.in_force(doc)})
        self.assertEqual(SB.public_problems(text), [])
        budget = text[text.index("## Budget"):text.index("## Releases")]
        self.assertIn("State: research under the ceiling.", budget)
        self.assertIn("| Meter | Research | Would stop at the present rate on | Next card action |", budget)
        self.assertIn(f"| sail | tapering | {sail['runs_out_on']} | {sail['card_date']} |", budget)
        self.assertIn(f"| claude | at the ceiling | {claude['runs_out_on']} | {claude['card_date']} |", budget)
        self.assertIn("In force now, research by meter: sail tapering, claude at the ceiling (source: budget.json).", budget)
        for key in ("research_usd_day", "runway_cap_usd_day", "would_set_usd_day", "total_usd_day", "balance_usd",
                    "reserve_usd", "topup_usd", "demand_usd_day"):
            for form in self.forms(sail[key]):  # as a figure of its own (a day's "-10-" is no figure)
                self.assertIsNone(SB.re.search(rf"(?<![\d.-]){SB.re.escape(form)}(?![\d.-])", budget), f"sail's {key}: {form}")
        self.assertNotIn("USD", budget, "no dollar figure of the budget at all")
        self.assertIsNone(SB.re.search(r"\d+\.\d", budget), "nor any figure with a decimal point")

    def test_the_ceiling_the_unread_meter_and_a_file_of_another_shape(self):
        full = self.doc(sail=600.0, claude=250.0)
        text = self.page(full, {"budget": self.in_force(full)})
        self.assertIn("State: research at the ceiling.", text)
        self.assertIn("| sail | at the ceiling |", text)
        self.assertIn("In force now, research by meter: sail at the ceiling, claude at the ceiling (source: budget.json).", text)
        unread = self.doc(sail=None, claude=250.0)
        self.assertEqual(unread["meters"]["sail"]["limited_by"], "unreadable")
        text = self.page(unread, {"budget": self.in_force(unread)})
        self.assertIn("| sail | unread | n/a | n/a |", text)
        self.assertIn("In force now, research by meter: sail none, claude at the ceiling (source: budget.json).", text)
        self.assertEqual(SB.public_problems(text), [])
        # A file of another shape, or text where a word or a day belongs: nothing of it is printed in those cells.
        odd = {"state": "research at floor", "meters": {"sail": {"research_usd_day": "3.00", "limited_by": HOSTILE,
                                                                 "runs_out_on": HOSTILE, "card_date": "soon"},
                                                        "claude": {"limited_by": ["runway"], "runs_out_on": 20261006}},
               "next_card_action": {"sail": "2027-01-04"}}
        lines = SB.budget_lines(odd)
        self.assertEqual(lines[-2:], ["| claude | n/a | n/a | n/a |", "| sail | n/a | n/a | 2027-01-04 |"])
        self.assertNotIn("3.00", "\n".join(lines))
        self.assertEqual(lines[0], "State: research at floor.", "the rule's words are said")
        # A state that came to hold a figure, or a direction that is none of the rule's three, is left out: the page
        # says the budget in words, whatever a later version of the rule writes into its file.
        for state, direction in (("research tapering: 12.6 of 15.0 a day", "cut to 12.6"), (12.6, 3), (["x"], HOSTILE)):
            said = "\n".join(SB.budget_lines({**odd, "state": state, "direction": direction}))
            self.assertNotIn("State:", said)
            self.assertNotIn("against yesterday", said)
            self.assertNotIn("12.6", said)
        for direction in SB.DIRECTIONS:
            self.assertIn(f"Research budget against yesterday: {direction}.", SB.budget_lines({**odd, "direction": direction}))
        self.assertEqual(SB.budget_lines(None), ["No budget state yet (the budget job has not written one)."])

    def test_what_a_late_first_run_added_back_is_on_no_page(self):
        """THE DAY'S FIRST RUN ADDS BACK WHAT THE DAY ALREADY PAID (league/ops/budget.py, the captain's B12 of Oct 3, 2026)
        beside THE BUDGET IN WORDS. A first run that comes late sets the day's figure from the balance as the day began.
        What it added back and what each meter has paid today are the meter's dollars, so they stay in the private
        records: the page says the same words and the rule's days, and none of those figures."""
        paid = {"sail": 6.37, "claude": 3.19}
        given = {"p30_usd": 0.0, "p30_source": "test", "edge": {"stop": False, "why": "test edge"},
                 "meters": {"sail": {"balance_usd": 80.0, "fixed_usd_day": 1.0, "need_usd": 0.0, "paid_today_usd": paid["sail"]},
                            "claude": {"balance_usd": 30.0, "fixed_usd_day": 0.0, "need_usd": 0.0,
                                       "paid_today_usd": paid["claude"]}}}
        doc = B.compute(given, now=NOW)
        plain = self.doc(sail=80.0, claude=30.0)  # the same readings with nothing added back
        for meter in B.METERS:
            row = doc["meters"][meter]
            self.assertEqual((row["added_back_usd"], row["limited_by"]), (paid[meter], "runway"), meter)
            self.assertAlmostEqual(row["research_usd_day"] - plain["meters"][meter]["research_usd_day"],
                                   paid[meter] / B.RUNWAY_DAYS, places=3, msg="the figure is from the balance as the day began")
            self.assertEqual(doc["inputs"]["meters"][meter]["paid_today_usd"], paid[meter], "the private file keeps it")
        self.assertTrue(any("added back" in line for line in doc["why"]), "and says why, in dollars")
        block = self.in_force(doc)
        self.assertEqual((block["source"], block["sail_usd_day"], block["claude_usd_day"]),
                         ("budget.json", doc["meters"]["sail"]["research_usd_day"], doc["meters"]["claude"]["research_usd_day"]),
                         "the figure in force is the one the late run set")
        text = self.page(doc, {"budget": block})
        self.assertEqual(SB.public_problems(text), [])
        budget = text[text.index("## Budget"):text.index("## Releases")]
        self.assertIn("State: research under the ceiling.", budget)
        self.assertIn("In force now, research by meter: sail tapering, claude tapering (source: budget.json).", budget)
        for meter in B.METERS:
            row = doc["meters"][meter]
            self.assertIn(f"| {meter} | tapering | {row['runs_out_on']} | {row['card_date']} |", budget)
            for key in ("added_back_usd", "research_usd_day", "would_set_usd_day", "runway_cap_usd_day"):
                for form in self.forms(row[key]):
                    self.assertIsNone(SB.re.search(rf"(?<![\d.-]){SB.re.escape(form)}(?![\d.-])", text), f"{meter}'s {key}: {form}")
            for form in self.forms(paid[meter]):
                self.assertNotIn(form, text, f"what {meter} has paid today")
        for line in doc["why"]:
            self.assertNotIn(line, text, "the rule's reasons hold its dollars: they are the private file's")
        for word in ("added back", "added_back", "paid_today", "00:00 UTC"):
            self.assertNotIn(word, text)
        self.assertIsNone(SB.re.search(r"\d+\.\d", budget), "no figure with a decimal point in the budget's section")


class Page(Fixture):
    def test_the_page_separates_tested_program_versions_from_the_subset_with_a_t(self):
        self.t = NOW - 30
        version = self.version("new-born", "few-days")
        self.unseen("new-born", version, 0.1, days=1)
        record = self.funnel()
        self.assertEqual(record["windows"]["last_24h"]["tested"]["versions"], 4)
        self.assertEqual(record["windows"]["last_24h"]["chance"]["versions"], 3)
        text = "\n".join(SB.funnel_lines(record))
        self.assertIn("| Programs that ran the unseen-year test | 8 | 4 |", text)
        self.assertIn("| Programs tested with a t | 7 | 3 |", text)
        self.assertEqual(SB.public_problems(text), [])

    def test_missing_costs_and_unreconciled_costs_are_disclosed_without_private_text(self):
        summary = json.loads((FIXTURES / "expected-summary.json").read_text())
        summary.update(cost_accounting_complete=False, total_costs_usd=None, known_input_cost_subtotal_usd="5.00")
        summary["net"]["net_usd"] = None
        summary["library_report"]["unresolved"] = [HOSTILE]
        text = SB.build(day="2026-10-06", release="synthetic-release", economics=summary, deploys={},
                        budget=None, ladder={"binding": False}, jobs={}, written_at="23:30Z")
        self.assertIn("Cost accounting is incomplete", text)
        self.assertIn("| Known input costs since T0 (incomplete) | 5.00 |", text)
        self.assertIn("| **Net on priced inputs (incomplete)** | **n/a** |", text)
        self.assertNotIn(HOSTILE, text)
        self.assertEqual(SB.public_problems(text), [])

    def economics(self):
        summary = json.loads((FIXTURES / "expected-summary.json").read_text())
        for cost in summary["costs"]:
            cost["basis"] = "a private basis"
        return summary

    def page(self, record, sealed=True):
        if record is not None:
            record = {**record, "sealed_looks": sealed}
        return SB.build(day="2026-10-06", release="20261006T010000Z-x", economics=self.economics(),
                        deploys={"self_promoted": 3, "self_rolled_back": 1},
                        budget={"state": "research at floor", "direction": "same",
                                "meters": {"sail": {"research_usd_day": "3.00"}}, "next_card_action": {"sail": "2027-01-04"}},
                        ladder={"binding": False, "entrants": 61, "in_practice": 12, "would_promote": 0, "promoted": 0,
                                "demoted": 0, "failed": 7},
                        jobs={"ok": 5, "missed": 1}, written_at="23:30Z", funnel=record)

    def test_the_whole_page_passes_the_public_filter_and_says_the_funnel(self):
        text = self.page(self.funnel())
        self.assertEqual(SB.public_problems(text), [])
        for line in ("| Stage | Since the basis | Last 24 hours |",
                     "| Families born | 9 | 2 |",
                     "| Families with an eligible Train version | 7 | 2 |",
                     "| Families that ran the unseen-year test | 7 | 3 |",
                     "| Unseen-year tests run | 8 | 3 |",
                     "| Families that met the unseen-year line | 5 | 1 |",
                     "| Families that reached the gate | 5 | 1 |",
                     "| Programs refused at the gate | 1 | 0 |",
                     "| Programs held at the gate | 1 | 0 |",
                     "| Programs that began to wait at the gate | 0 | 0 |",
                     "| Programs looked at (the unseen-market test) | 3 | 1 |",
                     "| Programs that passed it | 1 | 1 |",
                     "| Families that moved up to Candidate | 1 | 1 |",
                     "| Families that moved up to Probe | 1 | 1 |",
                     "| Families that moved up to Sized | 0 | 0 |",
                     "| Families that moved down a band | 0 | 0 |",
                     "Refused at the gate, by reason: since the basis: the audit 1; last 24 hours: none.",
                     "Held at the gate, by reason: since the basis: the power hold 1; last 24 hours: none.",
                     "A hold closes a program's place at the gate for good. A wait closes nothing and refuses nothing",
                     "Waiting at the gate now: 0.",
                     "| sail | n/a | n/a | 2027-01-04 |",
                     "one under it waits at the gate, with no look spent, and is looked at once that bar allows.",
                     "In each band now: 0 Candidate, 1 Probe, 0 Sized.",
                     "| USD booked | 12.00 | 2.00 |",
                     "| USD per family born | 1.33 | 1.00 |",
                     "| USD per unseen-year test | 1.50 | 0.67 |",
                     "| USD per family that reached the gate | 2.40 | 2.00 |",
                     "| USD per look | 4.00 | 2.00 |",
                     "| Programs tested with a t | 7 | 3 |",
                     "| Cleared the t check | n/a | n/a |",
                     "| Luck alone would clear | n/a | n/a |",
                     "| Distinct results tested | n/a | n/a |",
                     "| Distinct results that cleared | n/a | n/a |",
                     "A window with fewer than 20 programs tested shows no figure under its count",
                     "of which research hears only whether the line was met and how many of its checks passed;",
                     "a later step on the same program is no second arrival.",
                     "Looks made: 3; passed: 1; in flight: 0. The next look (number 4) is tested at the ",
                     "shared across every look made or in flight and this one",
                     "were tested at levels that sum to at most 0.0917, which bounds the chance that luck alone passed any of them.",
                     "a program needs a yearly Sharpe of at least ",
                     f"The owner's switches in force: {HOLDS_SAID}; drift screen: on; incubator: off.", FLOOR_SAID,
                     "The ladder is RECORDING", "It promotes nothing.",
                     "A research program's route to Probe is the unseen-market test at the gate",
                     "it can trade real money at Probe size from the next session to open.",
                     "The ladder records beside that route.",
                     "The incubator is off: no research program opens a real position before that test.",
                     "| 61 | 12 | 0 | 0 | 0 | 7 |", "**Net on priced inputs (incomplete)** | **-165.41**"):
            self.assertIn(line, text)
        for gone in ("The route to real money", "hears only pass or fail", "it trades real money", "Research USD/day",
                     "research USD a day"):
            self.assertNotIn(gone, text)
        self.assertNotIn("3.00", text[text.index("## Budget"):text.index("## Releases")], "no research cap in the budget's lines")

    def test_a_windows_chance_figures_are_public_only_over_enough_programs(self):
        """Research is told whether a program met the line and how many checks, never which (D2a): over one or two
        programs the t check's count would say which. The private record keeps every figure."""
        record = self.funnel()
        self.assertEqual(SB.CHANCE_MIN_PUBLIC, 20)
        self.assertEqual([record["windows"][key]["chance"]["cleared"] for key in ("since_basis", "last_24h")], [5, 1])
        with mock.patch.object(SB, "CHANCE_MIN_PUBLIC", 7):
            text = self.page(record)
        self.assertEqual(SB.public_problems(text), [])
        for line in ("| Programs tested with a t | 7 | 3 |", "| Cleared the t check | 5 | n/a |",
                     "| Luck alone would clear | 0.2 | n/a |",
                     "| Luck's spread (one standard deviation, were the tests independent) | 0.4 | n/a |",
                     "| Distinct results tested | 6 | n/a |", "| Distinct results that cleared | 4 | n/a |",
                     "| Luck alone, over distinct results | 0.1 | n/a |",
                     "A window with fewer than 7 programs tested shows no figure under its count"):
            self.assertIn(line, text)
        with mock.patch.object(SB, "CHANCE_MIN_PUBLIC", 3):
            text = self.page(record)
        for line in ("| Cleared the t check | 5 | 1 |", "| Luck alone would clear | 0.2 | 0.1 |",
                     "| Distinct results tested | 6 | 3 |", "| Distinct results that cleared | 4 | 1 |"):
            self.assertIn(line, text)
        with mock.patch.object(SB, "CHANCE_MIN_PUBLIC", 8):
            text = self.page(record)
        chance = text[text.index("| The t check |"):text.index("### The bar at the next look")]
        self.assertEqual((chance.count("| n/a | n/a |"), chance.count("| 7 | 3 |")), (6, 1), "the count alone is said")
        # A count that is no count shows nothing under it.
        for versions in (None, True, "30", 30.0, float("nan")):
            hostile = json.loads(json.dumps(record))
            hostile["windows"]["since_basis"]["chance"]["versions"] = versions
            with mock.patch.object(SB, "CHANCE_MIN_PUBLIC", 3):
                self.assertIn("| Cleared the t check | n/a | 1 |", self.page(hostile), versions)

    def test_the_route_is_said_with_the_incubator_as_the_owners_switch_stands(self):
        """The unseen-market test is the ONE route to real money only while the incubator is off: with it on the page
        says so, and with the switch not read it claims nothing either way."""
        record = self.funnel()
        route = "A research program's route to Probe is the unseen-market test at the gate"
        on = ("The incubator is on: a program that passed the review and the audit and whose practice record is positive "
              "may trade one lot of real money before that test; that is never evidence and never a promotion.")
        off = "The incubator is off: no research program opens a real position before that test."
        said = {}
        for name, value in (("on", True), ("off", False), ("unread", None)):
            switches = None if value is None else {**record["switches"], "live.incubator": value}
            said[name] = self.page({**record, "switches": switches})
            self.assertEqual(SB.public_problems(said[name]), [], name)
            self.assertIn(route, said[name])
            self.assertNotIn("The route to real money", said[name])
        self.assertTrue(on in said["on"] and off not in said["on"] and "incubator: on." in said["on"])
        self.assertTrue(off in said["off"] and on not in said["off"] and "incubator: off." in said["off"])
        self.assertTrue("The incubator is" not in said["unread"] and "incubator: n/a." in said["unread"])
        # The switch as the owner's own file sets it, read by the funnel itself.
        (self.root / "swarm.json").write_text(json.dumps({"live": {"incubator": True}}))
        self.assertIn(on, self.page(self.funnel()))
        closed = self.page({**self.funnel(), "sealed_looks": False}, sealed=False)
        self.assertEqual(SB.public_problems(closed), [])
        self.assertIn("no program has a route to Probe. The incubator is on: a program that passed the review and the audit "
                      "and whose practice record is positive may trade one lot of real money; that is never", closed)
        self.assertNotIn("before that test", closed)

    def test_nothing_of_the_stores_own_text_reaches_the_page(self):
        text = self.page(self.funnel())
        for private in (*FAMILIES, "sha-", G.HOLD_POWER_STAGE, "look hold (", "LOOKAHEAD", "SPY2610", "holdout", "sail_model",
                        "gym_box", "money table's Probe row", "no budget.json yet", "9372", "0.84", "0.001"):
            self.assertNotIn(private, text)

    def test_a_stage_the_page_does_not_know_is_another_reason_never_its_name(self):
        self.t = NOW - 60
        self.store.refuse("old-fail", 1, HOSTILE, HOSTILE)
        self.store.refuse("old-fail", 1, "rations", "the lineage's three holdout looks are spent")
        self.store.hold_look("old-fail", 1, "sha-old-fail", "def decide(ctx): PARAMS", HOSTILE)
        record = self.funnel()
        self.assertEqual(record["windows"]["last_24h"]["gate"]["refused"], {HOSTILE: 1, "rations": 1}, "the record is private")
        text = self.page(record)
        self.assertEqual(SB.public_problems(text), [])
        self.assertIn("Refused at the gate, by reason: since the basis: another reason 1, the audit 1, the lineage's looks "
                      "were spent 1; last 24 hours: another reason 1, the lineage's looks were spent 1.", text)
        self.assertIn("Held at the gate, by reason: since the basis: another reason 1, the power hold 1; last 24 hours: "
                      "another reason 1.", text)
        self.assertIn("| Programs refused at the gate | 3 | 2 |", text)

    def test_a_stage_whose_own_name_the_filter_refuses_is_said_in_the_pages_words(self):
        """One of the gate's hold stages is named with a word the public page may not carry: its row must never stop
        the page, and is said in the page's own words."""
        stage = "look hold (holdout read)"
        self.assertNotEqual(SB.public_problems(stage), [])
        self.t = NOW - 60
        self.store.hold_look("old-fail", 1, "sha-old-fail", stage, "the holdout look is held: read once already")
        self.store.refuse("old-train", 2, "program bar", "the same program was refused before")
        self.store.event("swarm.gate", "old-train", {"action": "program_bar", "version": 2, "bar": HOSTILE})
        record = self.funnel()
        day = record["windows"]["last_24h"]
        self.assertEqual((day["gate"]["held"], day["gate"]["refused"], day["gate"]["arrived"]),
                         ({stage: 1}, {"program bar": 1}, 3))
        text = self.page(record)
        self.assertEqual(SB.public_problems(text), [])
        self.assertIn("last 24 hours: its unseen market was read before 1.", text)
        self.assertIn("last 24 hours: the program was refused before 1.", text)

    def test_every_word_the_page_can_say_of_a_stage_a_source_or_the_route_is_public(self):
        for words in (*SB.STAGE_WORDS.values(), *SB.BUDGET_SOURCES.values(), "another reason"):
            self.assertEqual(SB.public_problems(words), [], words)
        # Every stage the gate can write: its named stages and holds, and the four it spells where it refuses.
        written = {value for name, value in vars(G).items() if name.endswith("_STAGE") and isinstance(value, str)}
        written |= set(G.HOLD_WORDS) | {"experiment contract", "drift screen", "rations", "review", "audit", "gym"}
        self.assertEqual(written - set(SB.STAGE_WORDS), set(), "a stage the gate writes and the page has no words for")
        # The fast lane's two stages (a program refused before; a program whose unseen market the ladder's read took).
        self.assertEqual(set(SB.STAGE_WORDS) - written - {getattr(G, "PROGRAM_BAR_STAGE", "program bar"),
                                                          getattr(G, "HOLD_READ_STAGE", "look hold (holdout read)")}, set())
        counts = {key: 0 for key in SB.LADDER_COUNTS}
        said = {(sealed, incubator): SB.ladder_lines({"binding": False, **counts}, sealed=sealed, incubator=incubator)
                for sealed in (True, False, None) for incubator in (True, False, None)}
        unread = SB.ladder_lines({"binding": False, **counts})
        self.assertTrue(unread[0].endswith("It promotes nothing."))
        for incubator in (True, False, None):
            self.assertEqual(said[None, incubator], unread, "no word of the route when it was not read")
            self.assertIn("A research program's route to Probe is the unseen-market test at the gate", said[True, incubator][0])
            self.assertIn("The ladder records beside that route.", said[True, incubator][0])
            self.assertIn("no program has a route to Probe", said[False, incubator][0])
        self.assertEqual(len({lines[0] for lines in said.values()}), 6)
        self.assertEqual(said[False, False], said[False, None], "with no route and no incubator there is nothing to add")
        for (sealed, incubator), lines in said.items():
            self.assertTrue(lines[0].startswith("The ladder is RECORDING"))
            self.assertIn("It promotes nothing.", lines[0])
            self.assertEqual(lines[1:], unread[1:], "the same counts under each")
            self.assertEqual(SB.public_problems("\n".join(lines)), [])
            self.assertNotIn("The route to real money", lines[0])
            self.assertEqual("The incubator is on" in lines[0], sealed is not None and incubator is True)
            self.assertEqual("The incubator is off" in lines[0], sealed is True and incubator is False)
        for switch in (HOSTILE, 1, 0, "true", [True]):  # only a boolean is a switch that was read
            self.assertEqual(SB.ladder_lines({"binding": False, **counts}, sealed=True, incubator=switch), said[True, None])
            self.assertEqual(SB.ladder_lines({"binding": False, **counts}, sealed=switch, incubator=True), unread)
        binds = SB.ladder_lines({"binding": True, **counts}, sealed=True, incubator=True)
        self.assertEqual(binds, SB.ladder_lines({"binding": True, **counts}), "a binding ladder says what it said")

    def test_only_a_number_is_printed_as_a_figure(self):
        """Whatever a record came to hold, no text of it is printed where a figure goes."""
        record = json.loads(json.dumps(self.funnel()))
        day = record["windows"]["last_24h"]
        day.update(born=HOSTILE, train_eligible=True, met_line=float("inf"))
        day["tested"]["runs"] = [HOSTILE]
        day["gate"].update(refused={"audit": HOSTILE}, looked=HOSTILE, waited=HOSTILE)
        record["waiting_now"] = HOSTILE
        day["usd"]["booked"] = HOSTILE
        day["chance"]["t"] = HOSTILE
        record["bands_now"]["probe"] = HOSTILE
        record["look"].update(made=HOSTILE, next_level=HOSTILE, alpha=HOSTILE, sharpe_yearly_for_hold=HOSTILE)
        record["switches"].update({"gate.look_holds": {"drift_share": HOSTILE, "min_power": HOSTILE},
                                   "tournament.drift_screen": HOSTILE, "live.incubator": HOSTILE})
        record["budget"].update(source=HOSTILE, sail_usd_day=HOSTILE)
        text = self.page(record, sealed=HOSTILE)
        self.assertEqual(SB.public_problems(text), [])
        self.assertNotIn("LOOKAHEAD", text)
        for line in ("| Families born | 9 | n/a |", "| Families with an eligible Train version | 7 | n/a |",
                     "| Unseen-year tests run | 8 | n/a |", "| Families that met the unseen-year line | 5 | n/a |",
                     "| Programs refused at the gate | 1 | 0 |", "| USD booked | 12.00 | n/a |",
                     "In each band now: 0 Candidate, n/a Probe, 0 Sized.", "Looks made: n/a;",
                     "look holds: drift share n/a, least power n/a; drift screen: n/a; incubator: n/a.",
                     UNREAD_SAID, "last 24 hours: the audit 0.", "| Programs that began to wait at the gate | 0 | n/a |",
                     "Waiting at the gate now: n/a."):
            self.assertIn(line, text)
        self.assertTrue(text.count("It promotes nothing.") == 1 and "route to Probe" not in text
                        and "The incubator is" not in text)

    def test_whatever_one_value_of_a_record_becomes_the_page_is_built_and_public(self):
        """Each value of a real record in turn replaced by what it should never be: the page is built, nothing of the
        text is printed, and the public filter passes."""
        record = json.loads(json.dumps(self.funnel()))

        def paths(value, path=()):
            yield path
            for key, inner in (value.items() if isinstance(value, dict) else ()):
                yield from paths(inner, path + (key,))

        tried = 0
        for path in paths(record):
            for wrong in (None, HOSTILE, [HOSTILE], {HOSTILE: HOSTILE}, True, float("nan"), 10 ** 30, -1):
                changed = json.loads(json.dumps(record))
                if not path:
                    changed = wrong
                else:
                    at = changed
                    for key in path[:-1]:
                        at = at[key]
                    at[path[-1]] = wrong
                text = self.page(changed) if isinstance(changed, dict) else SB.build(
                    day="2026-10-06", release="r", economics=None, deploys={}, budget=None, ladder={}, jobs={},
                    written_at="23:30Z", funnel=changed)
                self.assertEqual(SB.public_problems(text), [], (path, wrong))
                self.assertNotIn("LOOKAHEAD", text, (path, wrong))
                tried += 1
        self.assertGreater(tried, 500)
        for field in ("in_flight", "made", "passed", "next_level", "level_spent"):
            changed = json.loads(json.dumps(record))
            changed["look"][field] = HOSTILE
            self.assertEqual(SB.public_problems(self.page(changed)), [], field)
        changed = json.loads(json.dumps(record))
        changed["look"]["in_flight"] = HOSTILE
        self.assertIn("Looks made: 3; passed: 1; in flight: n/a. The next look (number n/a) is tested", self.page(changed))

    def test_a_page_without_a_funnel_says_na_and_is_whole(self):
        for record in (None, {}, {"windows": "x", "look": 3, "switches": [], "budget": "y"}):
            text = self.page(record)
            self.assertEqual(SB.public_problems(text), [])
            self.assertIn("| Families born | n/a | n/a |", text)
            self.assertIn("| USD per look | n/a | n/a |", text)
            self.assertIn("Refused at the gate, by reason: since the basis: n/a; last 24 hours: n/a.", text)
            self.assertIn("In each band now: n/a Candidate, n/a Probe, n/a Sized.", text)
            self.assertIn("Looks made: n/a; passed: n/a; in flight: n/a. The next look (number n/a) is tested at the n/a level", text)
            self.assertIn("look holds: n/a; drift screen: n/a; incubator: n/a.", text)
            self.assertIn(UNREAD_SAID, text)
            self.assertIn("| Programs that began to wait at the gate | n/a | n/a |", text)
            self.assertIn("Waiting at the gate now: n/a.", text)
            self.assertIn("**Net on priced inputs (incomplete)** | **-165.41**", text)
            self.assertIn("| 61 | 12 | 0 | 0 | 0 | 7 |", text)
            self.assertIn("Ran: 5; failed: 0; missed: 1; skipped: 0.", text)


class Robust(Fixture):
    def whole(self, text):
        """The rest of the page stands."""
        self.assertEqual(SB.public_problems(text), [])
        for line in ("## Money", "## Budget", "## Releases", "## The research funnel", "## The forward ladder",
                     "## The House's jobs today", "It promotes nothing."):
            self.assertIn(line, text)

    def page(self, record):
        return SB.build(day="2026-10-06", release="r", economics=None, deploys={}, budget=None,
                        ladder={"binding": False, **{key: "n/a" for key in SB.LADDER_COUNTS}}, jobs={}, written_at="23:30Z",
                        funnel=record)

    def test_no_store_is_na_for_its_lines_and_the_switches_and_the_budget_are_still_read(self):
        self.store.close()
        os.unlink(self.root / "swarm.sqlite")
        record = self.funnel()
        self.assertEqual(sorted(record["errors"]), ["look", "store"])
        self.assertIn("does not exist", record["errors"]["store"])
        for key in ("since_basis", "last_24h"):
            window = record["windows"][key]
            self.assertEqual({k: window[k] for k in ("born", "train_eligible", "tested", "met_line", "bands", "usd", "chance")},
                             {k: None for k in ("born", "train_eligible", "tested", "met_line", "bands", "usd", "chance")})
            self.assertEqual(window["gate"], {"arrived": None, "refused": None, "held": None, "waited": None, "looked": None,
                                              "passed": None})
        self.assertEqual((record["bands_now"], record["look"], record["waiting_now"]), (None, None, None))
        self.assertEqual(record["switches"]["tournament.drift_screen"], True)
        self.assertEqual(record["budget"]["source"], "floor")
        text = self.page(record)
        self.whole(text)
        self.assertIn("| Families born | n/a | n/a |", text)
        self.assertIn("drift screen: on; incubator: off.", text)
        self.assertIn("(source: the floor, no usable budget.json).", text)

    def test_a_locked_store_is_waited_for_once_and_every_line_is_na(self):
        self.store.close()
        holder = sqlite3.connect(self.root / "swarm.sqlite", isolation_level=None)
        self.addCleanup(holder.close)
        holder.execute("PRAGMA journal_mode=DELETE")
        holder.execute("BEGIN EXCLUSIVE")
        began = time.monotonic()
        with mock.patch.object(SB, "STORE_TIMEOUT", 0.2):
            record = self.funnel()
        self.assertLess(time.monotonic() - began, 3.0, "one wait, never one a line")
        self.assertIn("locked", record["errors"]["born"])
        self.assertEqual({record["errors"][name] for name, _ in SB.STORE_PARTS if name != "born"},
                         {"RuntimeError: the store is locked"})
        self.assertIsNone(record["windows"]["since_basis"]["born"])
        self.assertEqual(record["budget"]["source"], "floor")
        self.whole(self.page(record))
        holder.execute("ROLLBACK")
        self.assertEqual(self.funnel()["errors"], {}, "and read again once the lock is gone")

    def test_a_table_an_older_store_lacks_is_na_for_its_line_alone(self):
        self.raw("DROP TABLE look_holds")
        record = self.funnel()
        self.assertEqual(list(record["errors"]), ["holds"])
        self.assertIn("no such table", record["errors"]["holds"])
        whole = record["windows"]["since_basis"]
        self.assertIsNone(whole["gate"]["held"])
        self.assertEqual((whole["gate"]["arrived"], whole["met_line"], whole["gate"]["refused"], whole["born"]),
                         (5, 5, {"audit": 1}, 9), "a store without the table held no look: the gate's other lines stand")
        text = self.page(record)
        self.whole(text)
        self.assertIn("| Programs held at the gate | n/a | n/a |", text)
        self.assertIn("Held at the gate, by reason: since the basis: n/a; last 24 hours: n/a.", text)
        self.assertIn("| Programs refused at the gate | 1 | 0 |", text)

    def test_a_read_past_its_time_is_stopped_and_is_na_for_its_line_alone(self):
        began = time.monotonic()
        with mock.patch.dict(SB.READS, {"eligible": ENDLESS}), mock.patch.object(SB, "QUERY_SECONDS", 0.2):
            record = self.funnel()
        self.assertLess(time.monotonic() - began, 5.0)
        self.assertEqual(list(record["errors"]), ["eligible"])
        self.assertIn("stopped at its time limit", record["errors"]["eligible"])
        self.assertGreaterEqual(record["seconds"]["eligible"], 0.2)
        whole = record["windows"]["since_basis"]
        self.assertEqual((whole["train_eligible"], whole["born"], whole["tested"]["runs"], whole["usd"]["booked"]), (None, 9, 8, 12.0))
        text = self.page(record)
        self.whole(text)
        self.assertIn("| Families with an eligible Train version | n/a | n/a |", text)
        self.assertIn("| Families born | 9 | 2 |", text)

    def test_the_gate_events_out_of_time_leave_its_family_counts_na_and_its_tables_read(self):
        with mock.patch.dict(SB.READS, {"gate": ENDLESS_GATE}), mock.patch.object(SB, "QUERY_SECONDS", 0.2):
            record = self.funnel()
        whole = record["windows"]["since_basis"]
        self.assertEqual(list(record["errors"]), ["gate"])
        self.assertEqual((whole["gate"]["arrived"], whole["met_line"], whole["usd"]["per_gate_arrival"]), (None, None, None))
        self.assertEqual((whole["gate"]["refused"], whole["gate"]["looked"], whole["usd"]["per_look"]), ({"audit": 1}, 3, 4.0))

    def test_a_gate_table_out_of_time_leaves_the_arrivals_na_never_a_count_without_it(self):
        """Only a table an older store lacks stands for no rows: one that could not be read may hold arrivals."""
        for name in ("refusals", "holds"):
            with mock.patch.dict(SB.READS, {name: ENDLESS_STAGES}), mock.patch.object(SB, "QUERY_SECONDS", 0.2):
                record = self.funnel()
            whole = record["windows"]["since_basis"]
            self.assertEqual(list(record["errors"]), [name])
            self.assertIn("stopped at its time limit", record["errors"][name])
            self.assertEqual((whole["gate"]["arrived"], whole["met_line"], whole["usd"]["per_gate_arrival"]), (None, None, None))
            self.assertEqual((whole["gate"]["looked"], whole["born"]), (3, 9))
            self.assertIn("| Families that reached the gate | n/a | n/a |", self.page(record))
        self.raw("DROP TABLE looks")
        record = self.funnel()
        whole = record["windows"]["since_basis"]
        self.assertEqual(sorted(record["errors"]), ["look", "looks"])
        self.assertEqual((whole["gate"]["arrived"], whole["met_line"], whole["gate"]["looked"]), (5, 5, None),
                         "the looked-at families came through the gate's own events too")

    def test_when_the_funnels_whole_time_is_spent_the_reads_left_are_na(self):
        with mock.patch.object(SB, "FUNNEL_SECONDS", 0.0):
            record = self.funnel()
        self.assertEqual({record["errors"][name] for name, _ in SB.STORE_PARTS},
                         {"TimeoutError: the funnel's 0 s were spent before this read"})
        self.whole(self.page(record))

    def test_a_row_the_funnel_cannot_parse_is_skipped_not_fatal(self):
        self.t = NOW - 60
        self.store.event("swarm.tournament", None, {"validation": {"judged": ["new-born", {"passed": True}]}})
        self.store.event("swarm.tournament", None, {"validation": [{"passed": True}], "board": "x"})
        self.raw("UPDATE runs SET summary='not json' WHERE family='old-fail' AND window='validation' AND stress=1.0")
        for kind in ("swarm.band", "swarm.gate", "swarm.tournament"):
            self.raw("INSERT INTO events(at, kind, family, payload) VALUES(?, ?, 'new-born', ?)",
                     (SB.S.iso(NOW - 60), kind, 'not json, though it says "passed":true'))
        record = self.funnel()
        self.assertEqual(record["errors"], {})
        whole = record["windows"]["since_basis"]
        self.assertEqual((whole["met_line"], whole["gate"]["arrived"], whole["tested"]["runs"], whole["chance"]["versions"],
                          whole["bands"]), (5, 5, 8, 6, {"candidate": 1, "probe": 1, "sized": 0}))


class Reads(Fixture):
    def test_no_read_touches_the_notebook_and_only_a_state_that_holds_a_marker_is_decoded(self):
        seen = set()

        def watched(path, **kwargs):
            db = SB.guard._real_connect(SB.guard.ro_uri(path), uri=True, **kwargs)
            db.row_factory = sqlite3.Row

            def note(action, table, column, *_):
                if action == sqlite3.SQLITE_READ:
                    seen.add((table, column))
                return sqlite3.SQLITE_OK

            db.set_authorizer(note)
            return db

        self.store.note("old-look", "a note of the researcher's")
        for fid in FAMILIES:
            self.store.set_state(fid, canary="A-FAMILY-STATE")
        self.store.set_state("old-train", look_inflight={"sha": "s" * 64, "n": 2, "at": NOW - 60})
        self.store.retire("old-fail", "retired while its look was out")
        self.store.set_state("old-fail", look_inflight={"sha": "t" * 64, "n": 1, "at": NOW - 60})
        waits = {G.LOOK_WAIT: {"sha": "w" * 64, "n": 1, "stage": G.HOLD_POWER_STAGE, "at": NOW - 60},
                 "validation_version": 1, "validation_line": {"passed": True}, "gate_ready": False}
        self.store.set_state("old-audit", **waits)   # a version that waits at the gate now
        self.store.retire("old-never", "retired while its version waited")
        self.store.set_state("old-never", **waits)   # a retired family waits no more: its state is not even read
        sized = {RS.UNIT_WAIT_KEY: {"version": 1, "limit": 100.0}, "validation_version": 1,
                 "validation_line": {"passed": True}, "gate_ready": False}
        self.store.set_state("old-held", **sized)    # a version that met the line and waits before the gate for its unit
        decoded = []
        real = SB._object

        def decode(text):
            decoded.append(text)
            return real(text)

        with mock.patch.object(SB.guard, "connect_ro", watched), mock.patch.object(SB, "_object", decode):
            record = self.funnel()
        self.assertEqual(record["errors"], {})
        self.assertEqual((record["look"]["in_flight"], record["waiting_now"], record["unit_waiting_now"]), (2, 1, 1))
        self.assertEqual(len([text for text in decoded if isinstance(text, str) and "A-FAMILY-STATE" in text]), 4,
                         "of ten families' states, the two that hold a look in flight's marker, the living one that "
                         "holds a wait's and the living one that holds a unit wait's")
        tables = {table for table, _ in seen}
        self.assertEqual(tables, {"families", "runs", "events", "refusals", "look_holds", "looks", "spend"})
        self.assertEqual({column for table, column in seen if table == "families"}, {"born_at", "retired_at", "band", "state"})
        self.assertEqual([name for name, sql in SB.READS.items() if "state" in sql], ["waiting", "unit_waiting", "in_flight"])
        self.assertNotIn("retired_at", SB.READS["in_flight"], "a retired family's look in flight counts, as the gate counts it")
        for name in ("waiting", "unit_waiting"):
            self.assertIn("retired_at IS NULL AND band='gym'", SB.READS[name], "a wait is a living Gym family's")
        for sql in SB.READS.values():
            self.assertTrue(sql.startswith("SELECT ") and "notebook" not in sql and "*" not in sql.replace("COUNT(*)", ""), sql)

    def test_every_action_the_swarm_writes_on_a_familys_gate_event_is_an_arrival_or_named_as_none(self):
        """A new action in the gate is placed in one set or the other before the funnel counts or drops it."""
        written = set()
        for module in (G, ST, SI):
            for node in ast.walk(ast.parse(Path(module.__file__).read_text(encoding="utf-8"))):
                if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "event" and len(node.args) >= 3):
                    continue
                kind, family, payload = node.args[:3]
                if not (isinstance(kind, ast.Constant) and kind.value == "swarm.gate" and isinstance(payload, ast.Dict)):
                    continue
                if isinstance(family, ast.Constant) and family.value is None:
                    continue  # the gate's own rounds: no family
                for key, value in zip(payload.keys, payload.values):
                    if isinstance(key, ast.Constant) and key.value == "action":
                        written |= {leaf.value for leaf in ast.walk(value)
                                    if isinstance(leaf, ast.Constant) and isinstance(leaf.value, str)}
        self.assertTrue({"review", "audit", "look", "to_practice", "gate_hold", "incubator_bar", "prefilter"} <= written, written)
        self.assertEqual(written - SB.GATE_ARRIVALS - SB.GATE_NOT_ARRIVALS, set(), "an action the funnel has not placed")
        self.assertEqual(SB.GATE_ARRIVALS & SB.GATE_NOT_ARRIVALS, set())
        # Every name in the two sets is one the swarm writes (the fast lane's own refusal is written by its gate).
        self.assertEqual((SB.GATE_ARRIVALS | SB.GATE_NOT_ARRIVALS) - written - {"program_bar"}, set())

    def test_the_store_is_opened_read_only_and_left_as_it_was(self):
        self.store.close()
        before = (self.root / "swarm.sqlite").read_bytes()
        opened = []
        real = SB.guard.connect_ro

        def watched(path, **kwargs):
            opened.append(real(path, **kwargs))
            return opened[-1]

        with mock.patch.object(SB.guard, "connect_ro", watched):
            self.funnel()
        self.assertEqual((self.root / "swarm.sqlite").read_bytes(), before)
        with self.assertRaises(sqlite3.ProgrammingError, msg="closed when the funnel is done"):
            opened[0].execute("SELECT 1")
        db = real(self.root / "swarm.sqlite")
        self.addCleanup(db.close)
        with self.assertRaises(sqlite3.OperationalError):
            db.execute("DELETE FROM looks")


class TheResearchStream(Fixture):
    """What release F1's research stream writes, each counted apart from the stage it could be mistaken for: a birth pass
    the cells' pace skipped apart from one no cell could bear; a version set aside before the unseen-year test; a
    verdict read from an identical program's test (a copy of a record, no test); a line pass that waits before the
    gate for its unit apart from a hold and from the look's wait."""

    def passes(self):
        self.t = OLD
        for payload in ({"born": ["a", "b"], "route": "sail", "cost_usd": 0.08},
                        {"born": [], "skipped": "no_cell", "why": HOSTILE, "cells": {"cells": 44}},
                        {"born": [], "error": HOSTILE}):
            self.store.event("swarm.architect", None, payload)
        self.t = RECENT
        for payload in ({"born": [], "route": "sail", "cost_usd": 0.09, "room": {"cells": 44, "bearable": 2}},
                        {"born": [], "skipped": "paced", "why": HOSTILE, "cells": {"hour": {"born": 3, "cap": 3}}},
                        {"born": [], "skipped": "paced", "why": HOSTILE},
                        {"born": [], "skipped": "ceiling", "why": "the population is at its ceiling"},
                        {"born": [], "skipped": "a new kind", "why": HOSTILE}):
            self.store.event("swarm.architect", None, payload)
        self.t = NOW

    def test_a_pass_the_pace_skipped_is_counted_apart_from_one_no_cell_could_bear(self):
        self.passes()
        windows = self.funnel()["windows"]
        self.assertEqual(windows["since_basis"]["passes"],
                         {"paid": 2, "failed": 1, "skipped": {"no_cell": 1, "paced": 2, "ceiling": 1, "other": 1}})
        self.assertEqual(windows["last_24h"]["passes"],
                         {"paid": 1, "failed": 0, "skipped": {"no_cell": 0, "paced": 2, "ceiling": 1, "other": 1}})
        self.assertEqual(SB.PASS_SKIPS, (SA.SKIPPED_NO_CELL, SA.SKIPPED_PACED, SA.SKIPPED_CEILING),
                         "the kinds are the architect's own")

    def test_a_set_aside_is_counted_once_a_version_and_a_demotion_is_none(self):
        self.t = OLD
        self.store.event("swarm.robustness", "old-train", {"version": 1, "action": "set_aside", "why": HOSTILE, "next": None})
        self.store.event("swarm.robustness", "old-fail", {"version": 1, "action": "demoted", "why": HOSTILE, "next": None})
        self.t = RECENT
        for version in (1, 2):  # the same version set aside again (its limit moved and moved back), and a second one
            self.store.event("swarm.robustness", "old-train", {"version": version, "action": "set_aside", "why": HOSTILE,
                                                               "next": None})
        self.store.event("swarm.robustness", "old-train", {"version": 1, "action": "restored", "why": HOSTILE, "next": None})
        self.t = NOW
        windows = self.funnel()["windows"]
        self.assertEqual((windows["since_basis"]["set_aside"], windows["last_24h"]["set_aside"]), (2, 1))

    def test_a_verdict_read_from_an_identical_programs_test_is_no_test(self):
        before = self.funnel()["windows"]
        self.t = RECENT
        fam = self.store.family("new-born")
        source = {"family": "old-fail", "version": 1, "run": "old-fail-test"}
        copy = result("copied", window="validation", t=0.5, days=120)
        copy = {**copy, "trials": 0, "summary": {**copy["summary"], "inherited": source}}
        row = self.store.add_run(fam["id"], 1, copy, window="validation", stress=1.0, purpose="validation")
        self.assertEqual((row["trials"], self.store.family("new-born")["trials"]), (0, fam["trials"]), "no trial moved")
        self.t = NOW
        after = self.funnel()["windows"]
        for key in ("since_basis", "last_24h"):
            self.assertEqual((after[key]["tested"], after[key]["chance"], after[key]["usd"]["per_test"]),
                             (before[key]["tested"], before[key]["chance"], before[key]["usd"]["per_test"]),
                             "a copy of a record is no run, no program tested and no cost per test")
            self.assertEqual((before[key]["inherited"], after[key]["inherited"]), (0, 1))

    def test_a_line_pass_that_waits_for_its_unit_is_no_hold_no_wait_and_no_arrival(self):
        mark = {RS.UNIT_WAIT_KEY: {"version": 1, "limit": 100.0}, "validation_version": 1, "gate_ready": False}
        self.store.set_state("old-held", **mark, validation_line={"passed": True})
        self.store.set_state("old-fail", **mark, validation_line={"passed": False})   # a mark beside a line not met: none
        self.store.set_state("old-train", **{**mark, "validation_version": 2}, validation_line={"passed": True})  # stale
        self.store.retire("old-audit", "retired")
        self.store.set_state("old-audit", **mark, validation_line={"passed": True})   # a retired family waits no more
        before = dict(SB.funnel(self.root, NOW, config={})["windows"]["since_basis"]["gate"])
        record = self.funnel()
        self.assertEqual((record["unit_waiting_now"], record["waiting_now"], record["errors"]), (1, 0, {}))
        self.assertEqual(record["windows"]["since_basis"]["gate"], before)

    def test_the_page_says_each_in_public_words_and_never_the_stores_text(self):
        self.passes()
        self.store.set_state("old-held", **{RS.UNIT_WAIT_KEY: {"version": 1, "limit": 100.0}}, validation_version=1,
                             validation_line={"passed": True}, gate_ready=False)
        self.t = RECENT
        self.store.event("swarm.robustness", "old-train", {"version": 2, "action": "set_aside", "why": HOSTILE, "next": None})
        self.t = NOW
        text = "\n".join(SB.funnel_lines(self.funnel()))
        for line in ("| Birth passes that asked a model | 2 | 1 |",
                     "| Birth passes skipped: no cell could bear a birth | 1 | 0 |",
                     "| Birth passes skipped: the hour's births were spent | 2 | 2 |",
                     "| Birth passes skipped: the population was at its ceiling | 1 | 1 |",
                     "| Programs set aside before the unseen-year test | 1 | 1 |",
                     "| Verdicts read from an identical program's test (no run) | 0 | 0 |",
                     "Waiting before the gate for its unit now: 1."):
            self.assertIn(line, text)
        self.assertEqual(SB.public_problems(text), [])
        self.assertNotIn("LOOKAHEAD", text)

    def test_an_older_store_or_no_store_says_na(self):
        record = SB.funnel(self.root / "nowhere", NOW, config={})
        for key in ("since_basis", "last_24h"):
            self.assertEqual([record["windows"][key][name] for name in ("passes", "set_aside", "inherited")], [None] * 3)
        self.assertIsNone(record["unit_waiting_now"])
        text = "\n".join(SB.funnel_lines(record))
        self.assertIn("| Birth passes skipped: the hour's births were spent | n/a | n/a |", text)
        self.assertIn("Waiting before the gate for its unit now: n/a.", text)


class Job(Fixture):
    def test_run_writes_the_private_record_and_posts_the_page_with_the_funnel(self):
        gateway = FakeGateway()
        out = SB.run(self.ctx("scoreboard", gateway=gateway, due=NOW))
        saved = self.root / "ops" / "funnel.json"
        self.assertEqual(out["funnel"]["file"], str(saved))
        self.assertEqual(out["funnel"]["not_read"], [])
        self.assertLess(out["funnel"]["seconds"], 5.0)
        self.assertEqual(os.stat(saved).st_mode & 0o777, 0o600)
        record = json.loads(saved.read_text())
        mine = json.loads(json.dumps(self.funnel()))
        self.assertEqual({k: v for k, v in record.items() if k != "seconds"}, {k: v for k, v in mine.items() if k != "seconds"})
        self.assertEqual(record["windows"]["since_basis"]["usd"]["by_kind"], {"claude": 0.5, "gym_box": 4.0, "sail_model": 7.5})
        content = gateway.posts[0][1]["content"]
        self.assertEqual(SB.public_problems(content), [])
        self.assertIn("| Families born | 9 | 2 |", content)
        self.assertEqual(content, (self.root / "scoreboard" / "2026-10-06.md").read_text())
        self.assertEqual(out["posted"], "docs/runs/desk/2026-10-06.md")

    def test_the_page_says_the_route_the_running_release_has(self):
        gateway = FakeGateway()
        with mock.patch.object(G, "SEALED_LOOKS", True):
            self.assertIs(SB.sealed_looks(), True)
            SB.run(self.ctx("scoreboard", gateway=gateway, due=NOW))
        with mock.patch.object(G, "SEALED_LOOKS", False):
            self.assertIs(SB.sealed_looks(), False)
            SB.run(self.ctx("scoreboard", gateway=gateway, due=NOW))
        fast, closed = (body["content"] for _, body in gateway.posts)
        self.assertIn("It promotes nothing. A research program's route to Probe is the unseen-market test at the gate", fast)
        self.assertIn("The ladder records beside that route.", fast)
        self.assertIn("The incubator is off: no research program opens a real position before that test.", fast)
        self.assertIn("It promotes nothing. The unseen-market test is off in this release", closed)
        self.assertNotIn("route to Probe is", closed)
        self.assertNotIn("The incubator is", closed)
        (self.root / "swarm.json").write_text(json.dumps({"live": {"incubator": True}}))
        with mock.patch.object(G, "SEALED_LOOKS", True):
            SB.run(self.ctx("scoreboard", gateway=gateway, due=NOW))
        both = gateway.posts[-1][1]["content"]
        self.assertEqual(SB.public_problems(both), [])
        self.assertIn("may trade one lot of real money before that test; that is never evidence and never a promotion.", both)
        self.assertIn("incubator: on.", both)
        self.assertNotIn("The incubator is off", both)
        with mock.patch.object(G, "SEALED_LOOKS", "yes"):
            self.assertIsNone(SB.sealed_looks(), "a switch that is no boolean is not read")

    def test_under_the_switches_release_f1_ships_the_page_says_the_fast_lanes_route(self):
        """No patch: the gate's own switch as this tree ships it (the fast lane: the unseen-market test is the route to
        Probe) and the owner's incubator switch as production has it (on). The page names both lanes truly: the route
        to Probe, and the incubator's one lot of real money BEFORE that test, which is never evidence."""
        self.assertIs(G.SEALED_LOOKS, True, "release F1 ships the sealed look as the route to Probe")
        (self.root / "swarm.json").write_text(json.dumps({"live": {"incubator": True}}))
        gateway = FakeGateway()
        SB.run(self.ctx("scoreboard", gateway=gateway, due=NOW))
        page = gateway.posts[0][1]["content"]
        self.assertEqual(SB.public_problems(page), [])
        record = json.loads((self.root / SB.FUNNEL_FILE).read_text())
        self.assertEqual((record["sealed_looks"], record["switches"]["live.incubator"]), (True, True))
        self.assertIn(
            "The ladder is RECORDING: it judges every practice cohort at its checkpoints and writes down what it would "
            "promote. It promotes nothing. A research program's route to Probe is the unseen-market test at the gate: a "
            "program that passes it is a Candidate; the money table moves a Candidate that fits its Probe row to Probe "
            "with no count of sessions to wait for, and it can trade real money at Probe size from the next session to "
            "open. The ladder records beside that route. It makes no read of the unseen market of its own while that "
            "test is its one reader, so its would-promote count stays 0. The incubator is on: a program that passed the "
            "review and the audit and whose practice record is positive may trade one lot of real money before that "
            "test; that is never evidence and never a promotion.", page)
        self.assertNotIn("no program has a route to Probe", page)
        self.assertNotIn("The incubator is off", page)

    def test_what_the_funnel_could_not_read_is_one_house_warning_naming_the_parts(self):
        from league.ops.runner import public_text

        ctx = self.ctx("scoreboard", gateway=FakeGateway(), due=NOW)
        SB.run(ctx)
        self.assertEqual(ctx.alerts, [], "all of it read: nothing to say")
        with mock.patch.dict(SB.READS, {"eligible": ENDLESS, "usd": "SELECT kind, usd FROM no_such_table WHERE epoch >= ?"}), \
                mock.patch.object(SB, "QUERY_SECONDS", 0.2):
            out = SB.run(ctx)
        self.assertEqual(out["funnel"]["not_read"], ["eligible", "usd"])
        self.assertEqual(ctx.alerts, [{"level": "warning", "text": "scoreboard: the funnel could not read eligible, usd: those "
                                                                 "lines say n/a on today's page"}])
        text = ctx.alerts[0]["text"]
        self.assertEqual((SB.public_problems(text), public_text(text)), ([], text), "an alert is public: parts, never why")

    def test_a_funnel_that_fails_whole_never_stops_the_page(self):
        gateway = FakeGateway()
        ctx = self.ctx("scoreboard", gateway=gateway, due=NOW)
        with mock.patch.object(SB, "funnel", side_effect=RuntimeError("anything at all")):
            out = SB.run(ctx)
        self.assertEqual(out["funnel"], {"error": "RuntimeError: anything at all"})
        self.assertEqual([a["level"] for a in ctx.alerts], ["warning"])
        self.assertNotIn("anything at all", ctx.alerts[0]["text"])
        content = gateway.posts[0][1]["content"]
        self.assertEqual(SB.public_problems(content), [])
        self.assertIn("| Families born | n/a | n/a |", content)
        self.assertIn("It promotes nothing.", content)

    def test_a_record_that_cannot_be_written_never_stops_the_page(self):
        (self.root / "ops").write_text("a file where the folder would be")
        gateway = FakeGateway()
        ctx = self.ctx("scoreboard", gateway=gateway, due=NOW)
        out = SB.run(ctx)
        self.assertIn(out["funnel"]["file_error"], ("FileExistsError", "NotADirectoryError"))
        self.assertEqual(ctx.alerts, [{"level": "warning", "text": "scoreboard: the funnel's private record could not be written"}])
        self.assertIn("| Families born | 9 | 2 |", gateway.posts[0][1]["content"])


class RealRounds(RoundCase):
    """The funnel over what the swarm's own rounds write: the real tournament's verdict events and the real gate's
    review, audit, look and band move (the shapes the fixture above only imitates)."""

    def setUp(self):
        super().setUp()
        self.clock.advance(7 * 86400)  # the fake clock starts before the record's basis

    def funnel(self):
        return SB.funnel(self.root, self.clock() + 60, config={})

    def test_a_round_that_ends_in_a_passed_look(self):
        self.family("a")
        self.family("b")
        self.answer = lambda job: strong(job) if job.family == "a" else weak(job)
        Tournament(self.store, self.pool, self.settings, rng=random.Random(1)).run()
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])
        day = self.funnel()["windows"]["last_24h"]
        born = len(self.store.families())  # the round may fork a family of its own
        self.assertEqual((day["born"], day["tested"], day["met_line"], day["gate"]["arrived"]),
                         (born, {"families": 2, "versions": 2, "runs": 2}, 1, 0))
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}] * 2
        out = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock, sealed_looks=True).run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": True}])
        record = self.funnel()
        self.assertEqual(record["errors"], {})
        day = record["windows"]["last_24h"]
        self.assertEqual((day["met_line"], day["gate"], day["bands"]),
                         (1, {"arrived": 1, "refused": {}, "held": {}, "waited": 0, "looked": 1, "passed": 1},
                          {"candidate": 1, "probe": 0, "sized": 0}))
        self.assertEqual(record["bands_now"], {"candidate": 1, "probe": 0, "sized": 0})
        self.assertEqual((record["look"]["made"], record["look"]["passed"], record["look"]["in_flight"]), (1, 1, 0))
        self.assertEqual(day["chance"]["versions"], 2)
        self.assertEqual(day["chance"]["cleared"], 1)
        self.assertEqual(day, record["windows"]["since_basis"] | {"since": day["since"]})

    def test_a_refusal_at_the_audit_and_a_look_in_flight(self):
        self.family("a")
        self.family("b")
        Tournament(self.store, self.pool, self.settings, rng=random.Random(1)).run()
        self.pool.slow.add("b")
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}, {"text": json.dumps(
            {"verdict": "fail", "reasons": ["a hard-coded regime"], "findings": [{"code_excerpt": "def decide(ctx):",
             "contract_reference": "calendar", "counterexample": "a synthetic finding for this gate transition"}]})},
            {"text": json.dumps({"verdict": "pass", "reasons": []})}, {"text": json.dumps({"verdict": "pass", "reasons": []})}]
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock, sealed_looks=True).run()
        record = self.funnel()
        day = record["windows"]["last_24h"]
        self.assertEqual((day["met_line"], day["gate"]), (2, {"arrived": 2, "refused": {"audit": 1}, "held": {}, "waited": 0,
                                                              "looked": 0, "passed": 0}))
        self.assertEqual((record["look"]["made"], record["look"]["in_flight"], record["look"]["next_level"]), (0, 1, 0.025))
        self.assertEqual(SB.public_problems("\n".join(SB.funnel_lines(record))), [])

    def test_a_place_closed_to_practice_is_an_arrival_at_the_gate(self):
        """With the unseen-market test off the gate sends a version that met the line to practice: its one event."""
        self.family("a")
        self.family("b")
        self.answer = lambda job: strong(job) if job.family == "a" else weak(job)
        Tournament(self.store, self.pool, self.settings, rng=random.Random(1)).run()
        out = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock, sealed_looks=False).run()
        self.assertEqual(out["practice"], ["a"])
        actions = [json.loads(row["payload"]).get("action") for row in self.store._all(
            "SELECT payload FROM events WHERE kind='swarm.gate' AND family='a'")]
        self.assertEqual([action for action in actions if action in SB.GATE_ARRIVALS], ["to_practice"])
        day = self.funnel()["windows"]["last_24h"]
        self.assertEqual((day["met_line"], day["gate"]), (1, {"arrived": 1, "refused": {}, "held": {}, "waited": 0, "looked": 0,
                                                              "passed": 0}))

    def thin(self, job):
        """A Validation run that meets the line with an all-days Sharpe the unseen market cannot judge (invented)."""
        out = strong(job)
        if job.window == "validation":
            out["summary"]["sharpe_daily"] = 0.0371
        return out

    def page(self, record):
        return SB.build(day="2026-10-06", release="r", economics=None, deploys={}, budget=None,
                        ladder={"binding": False, **{key: 0 for key in SB.LADDER_COUNTS}}, jobs={}, written_at="23:30Z",
                        funnel=record)

    def test_a_wait_is_counted_apart_from_a_hold_that_bars_and_the_page_is_public(self):
        """THE POWER HOLD IS A WAIT (the real gate's own rounds): `a` waits for the look's bar, `b`'s look is held for
        good (its unseen market was read before), `c` waits and retires. The page counts the waits on their own line
        and the hold with the holds, says how many wait now, and passes the public check."""
        self.settings["gate"]["look_holds"] = {"drift_share": None, "min_power": 0.30}  # the power hold alone
        for fid in ("a", "b", "c"):
            self.family(fid)
        self.answer = self.thin
        Tournament(self.store, self.pool, self.settings, rng=random.Random(1)).validate(self.store.families(alive=True))
        self.store.put(G.PREFILTER_KEY + G.run_sha(self.store.version("b", 1)), {"status": "done", "at": self.clock()})
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        out = gate.run()
        self.assertEqual((out["look_waiting"], out["look_held"], out["looked"]), (["a", "c"], ["b"], []))
        self.store.retire("c", "a test retirement of this family")
        record = self.funnel()
        self.assertEqual(record["errors"], {})
        day = record["windows"]["last_24h"]
        self.assertEqual(day["gate"], {"arrived": 3, "refused": {}, "held": {G.HOLD_READ_STAGE: 1}, "waited": 2, "looked": 0,
                                       "passed": 0})
        self.assertEqual(record["waiting_now"], 1, "a retired family waits no more")
        text = self.page(record)
        self.assertEqual(SB.public_problems(text), [])
        for line in ("| Programs held at the gate | 1 | 1 |", "| Programs that began to wait at the gate | 2 | 2 |",
                     "| Programs looked at (the unseen-market test) | 0 | 0 |",
                     "Held at the gate, by reason: since the basis: its unseen market was read before 1; last 24 hours: "
                     "its unseen market was read before 1.",
                     "A hold closes a program's place at the gate for good. A wait closes nothing and refuses nothing: a "
                     "program the power hold stops keeps its place, is judged again every round, and gets its one look when "
                     "the bar at the next look allows. Waiting at the gate now: 1.",
                     "| Families that reached the gate | 3 | 3 |"):
            self.assertIn(line, text)
        for private in (G.HOLD_POWER_STAGE, G.HOLD_READ_STAGE, G.LOOK_WAIT, "0.0371"):
            self.assertNotIn(private, text)
        # Rounds later a waiting version is still one wait: one event a version, and nothing new on the page.
        for _ in range(3):
            self.clock.advance(300)
            self.assertEqual(gate.run()["look_waiting"], ["a"])
        again = self.funnel()
        self.assertEqual((again["windows"]["last_24h"]["gate"], again["waiting_now"]), (day["gate"], 1))
        # The bar allows it (the owner's setting here): its look is made. It waits no more, and it did wait in the window.
        self.settings["gate"]["look_holds"] = {"drift_share": None, "min_power": 0.01}
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}] * 2
        self.assertEqual([x["family"] for x in gate.run()["looked"]], ["a"])
        done = self.funnel()
        self.assertEqual((done["waiting_now"], done["windows"]["last_24h"]["gate"]["waited"],
                          done["windows"]["last_24h"]["gate"]["looked"], done["windows"]["last_24h"]["gate"]["arrived"]),
                         (0, 2, 1, 3))
        self.assertIn("Waiting at the gate now: 0.", self.page(done))

    def test_a_wait_from_before_a_window_is_not_in_it_and_an_older_store_is_na_for_nothing(self):
        self.settings["gate"]["look_holds"] = {"drift_share": None, "min_power": 0.30}
        self.family("a")
        self.answer = self.thin
        Tournament(self.store, self.pool, self.settings, rng=random.Random(1)).validate(self.store.families(alive=True))
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.clock.advance(3 * 86400)
        record = self.funnel()
        self.assertEqual((record["windows"]["since_basis"]["gate"]["waited"], record["windows"]["last_24h"]["gate"]["waited"],
                          record["waiting_now"]), (1, 0, 1), "it began to wait three days ago, and waits now")
        self.assertIn("| Programs that began to wait at the gate | 1 | 0 |", self.page(record))

    def test_two_looks_out_at_once_and_the_levels_they_were_tested_at(self):
        """Two looks in flight are two failed looks to the next one's level; once both land, the levels the page sums
        are the most the gate can have tested them at (a gate that counts the other look in flight when one lands
        tested it lower)."""
        self.family("a")
        self.family("b")
        Tournament(self.store, self.pool, self.settings, rng=random.Random(1)).run()
        self.pool.slow |= {"a", "b"}
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}] * 4
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock, sealed_looks=True).run()
        record = self.funnel()
        self.assertEqual((record["look"]["made"], record["look"]["in_flight"], record["look"]["next_level"]),
                         (0, 2, round(0.05 / 3, 6)))
        self.assertIn("in flight: 2. The next look (number 3) is tested", "\n".join(SB.funnel_lines(record)))
        for job, late in list(self.pool.landing):
            late(weak(job))
        looks = self.store.looks()
        self.assertEqual([look["passed"] for look in looks], [0, 0])
        record = self.funnel()
        self.assertEqual((record["look"]["made"], record["look"]["in_flight"], record["look"]["level_spent"]), (2, 0, 0.075))
        tested_at = sum(0.05 / (look["detail"]["numbers"]["looks_before"] + 1) for look in looks)  # every look before failed
        self.assertLessEqual(tested_at, record["look"]["level_spent"] + 1e-9)
        text = "\n".join(SB.funnel_lines(record))
        self.assertIn("were tested at levels that sum to at most 0.0750, which bounds the chance", text)
        self.assertEqual(SB.public_problems(text), [])


if __name__ == "__main__":
    unittest.main()
