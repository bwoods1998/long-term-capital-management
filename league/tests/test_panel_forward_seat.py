"""THE PANEL POOL'S SEAT ON A FORWARD PASS, AND NO SEAT FROM A HISTORICAL LOOK (the captain's A34, release U).

A34 (18:42Z Oct 14, 2026, from study XS1-R): no historical XS1 look and no seat from one, for any panel program; its
only path to money is FWD1-R case N. So, on the House's own value (`elane_xs.A34_FORWARD_ONLY`, never a setting):
- a panel family takes no sealed Validation try and no look, whatever `elane.panel.mode` and `look_rule` say, nothing
  spent and nothing retired (`TheHistoricalRouteIsHeld`);
- a FWD1-R panel pass that `elane_forward.step` made eligible is seated THROUGH THE PANEL POOL (`elane_xs.forward_seats`,
  once an equity round right after the seat path): into a free seat of the pool only, while the lane is live, after
  `elane_forward.seat_refused` and with `elane_forward.mark_seated` in the transaction that moves the band
  (`AForwardPassIsSeatedThroughThePool`, `ThePoolsRoom`, `OneSeatAMechanismCell`);
- a panel Candidate that holds no forward seat (one a historical look made) is seatless (`AHistoricalLookSeatsNobody`);
- with `elane.fwd1.seats` off nothing panel is seated (`TheSwitchOff`).

The panel lane's fakes are package G's (league/tests/elane_xs_fakes.py) with the House's A34 value kept
(`switch_on(..., historical=False)`); the permit file is written as league/ops/forward_screen.py writes it (ids and
words only). Every family, program, label and number is invented."""

from __future__ import annotations

import inspect
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league.equity import EQUITY_ENGINE_VERSION, LANES
from league.swarm import bands, elane, elane_xs
from league.swarm import elane_forward as EF
from league.swarm import gate as gate_mod
from league.swarm import settings as settings_mod
from league.swarm.evaluator import equity_fingerprint
from league.swarm.gate import run_sha
from league.tests import elane_xs_fakes as F
from league.xs import XS_ENGINE_VERSION

CELL = "equity / xs_reversal / panel:sp500"
WORDS = "FWD1-R forward screen (PANEL, case N): passed at checkpoint 5 (an invented test's words)"


class Base(unittest.TestCase):
    def setUp(self):
        self.world = F.switch_on(self, historical=False)    # THE HOUSE'S VALUE: A34 holds the historical route
        self.assertIs(elane_xs.A34_FORWARD_ONLY, True)
        self.store = F.new_store(self)
        self.root = Path(self.store.root)
        F.ready(self.root)
        self.box(fwd1="on")
        for name in ("_xs_cache",):
            patcher = mock.patch.object(bands, name, None)
            patcher.start()
            self.addCleanup(patcher.stop)

    # ---------------------------------------------------------------------------------------------- the fixtures
    def box(self, *, fwd1: str = "on", mode: str = "live", look_rule: str = "hold", **panel) -> dict:
        """The box's swarm.json (the captain's switches: `elane.fwd1.seats` is `fwd1`, `elane.panel` gets `mode`,
        `look_rule` and `panel`) and the settings the House reads from it."""
        layer = F.settings(mode, look_rule=look_rule, **panel)
        layer["elane"]["fwd1"] = {"mode": "record", "seats": fwd1}
        (self.root / "swarm.json").write_text(json.dumps(layer))
        with elane_xs._cache_lock:
            elane_xs._mode_cache.clear()
            elane_xs._json_cache.clear()
        self.settings = settings_mod.load(self.root)
        return self.settings

    def family(self, slug: str) -> dict:
        return F.panel_family(self.store, slug, code=F.good(tag=slug))

    def label(self, xs: str | None = None) -> str:
        """The forward record's engine label of a panel row (league/ops/forward_xs.py `engine_label`)."""
        return (f"{EQUITY_ENGINE_VERSION}+{equity_fingerprint()[:12]}+fwd-1+xs."
                f"{(xs or self.world.fingerprint())[:12]}")

    def passed(self, fid: str, *, cell: str = CELL, case: str = "N", engine: str | None = None) -> dict:
        version = self.store.version(fid, 1)
        return {"status": "pass", "type": "PANEL", "case": case, "cell": cell, "family": fid, "version": 1,
                "run_sha": run_sha(version), "k": 5, "weak": True, "engine": engine or self.label(), "words": WORDS}

    def permit(self, rows: dict) -> None:
        (self.root / EF.PERMITS).write_text(json.dumps({"version": EF.PERMITS_VERSION, "screen": "FWD1-R",
                                                       "receipt": "c" * 64, "start": "2026-10-16", "at": "x",
                                                       "lineages": rows}))

    def lineage(self, fid: str) -> str:
        return EF.lineage_of(self.store, self.store.family(fid))

    def gate(self) -> SimpleNamespace:
        return SimpleNamespace(store=self.store, settings=self.settings, clock=self.store.clock)

    def round(self) -> tuple[dict, dict]:
        """The equity round's two seat steps, in the gate's order (league/swarm/gate.py `equity_round`)."""
        return EF.step(self.gate()), elane_xs.forward_seats(self.gate())

    def fam(self, fid: str) -> dict:
        return self.store.family(fid)

    def events(self, action: str) -> list[dict]:
        return [e for e in self.store.events_after(0, limit=5000) if e["payload"].get("action") == action]


class AForwardPassIsSeatedThroughThePool(Base):
    def test_a_fwd1_panel_pass_becomes_the_pools_candidate_when_the_switch_is_on_and_a_seat_is_free(self):
        fid = self.family("rev-a")["id"]
        self.permit({self.lineage(fid): self.passed(fid)})
        forward, pool = self.round()
        self.assertEqual(forward["eligible"], [fid], "the seat path makes the pass eligible only")
        self.assertEqual(pool, {"seated": [fid], "waits": {}})
        got = self.fam(fid)
        state = got["state"]
        sha = run_sha(self.store.version(fid, 1))
        self.assertEqual(got["band"], "candidate")
        self.assertEqual((state["banded_version"], state["banded_sha"]), (1, self.store.version(fid, 1)["sha"]))
        self.assertEqual(state["banded_evaluator"], {"engine": XS_ENGINE_VERSION, "xs_sha256": self.world.fingerprint(),
                                                     "run_sha": sha}, "proven on the xs identity, as a look proves it")
        self.assertTrue(bands.current_xs_evaluator(state, sha, self.world.fingerprint()))
        held = state[EF.STATE_KEY]
        self.assertEqual((held["eligible"], held["seated"], held["case"], held["cell"], held["type"]),
                         (True, True, "N", CELL, "PANEL"))
        self.assertTrue(elane_xs.forward_seated(got))
        self.assertIsNone(elane_xs.seat_refused_a34(got))
        [seat] = self.events("forward_seat")
        self.assertEqual((seat["family"], seat["payload"]["screen"], seat["payload"]["lane"]), (fid, "FWD1-R", "PANEL"))
        [moved] = [e for e in self.store.events_after(0, limit=5000) if e["kind"] == "swarm.band"]
        self.assertIn("FWD1-R", moved["payload"]["reason"])
        self.assertIn("A34", moved["payload"]["reason"])
        self.assertEqual(self.round(), ({"seated": [], "eligible": [], "waits": {}}, {"seated": [], "waits": {}}),
                         "once: a family seated on its pass is never seated again by this path")

    def test_the_roster_seats_it_in_the_panel_pool_and_its_row_carries_the_verdicts_words(self):
        fid = self.family("rev-a")["id"]
        self.permit({self.lineage(fid): self.passed(fid)})
        self.round()
        roster = bands.roster(self.root, lanes=LANES)
        self.assertIn(fid, roster["seated"])
        self.assertNotIn(fid, roster["seatless"])
        self.assertEqual(roster["panel_seats"], 1, "the lower of equity_money.panel.seats and elane.panel.seats")
        [row] = [r for r in bands.read(self.root, lanes=LANES) if r["family"] == fid]
        self.assertEqual((row["structure"], row["band"], row["version"]), ("panel", "candidate", 1))
        self.assertEqual(row["beside"], WORDS, "the forward pass's words stand beside its trades (it took no look)")

    def test_the_seat_and_its_record_are_one_transaction(self):
        fid = self.family("rev-a")["id"]
        self.permit({self.lineage(fid): self.passed(fid)})
        EF.step(self.gate())
        with mock.patch.object(self.store, "set_band", return_value=None):
            pool = elane_xs.forward_seats(self.gate())
        self.assertEqual(pool["seated"], [])
        self.assertIn("did not move", pool["waits"][fid])
        state = self.fam(fid)["state"]
        self.assertIs(state[EF.STATE_KEY]["seated"], False, "the record rolled back with the band")
        self.assertNotIn("banded_evaluator", state)
        self.assertEqual(self.events("forward_seat"), [])
        self.assertEqual(elane_xs.forward_seats(self.gate())["seated"], [fid], "asked again next round")

    def test_it_waits_on_what_it_cannot_prove(self):
        fid = self.family("rev-a")["id"]
        self.permit({self.lineage(fid): self.passed(fid, engine=self.label("d" * 64))})
        self.assertIn("identity moved", self.round()[1]["waits"][fid])
        self.permit({self.lineage(fid): self.passed(fid, engine=f"{EQUITY_ENGINE_VERSION}+"
                                                                f"{equity_fingerprint()[:12]}+fwd-1")})
        self.assertIn("identity moved", elane_xs.forward_seats(self.gate())["waits"][fid],
                      "a panel label that names no xs identity is refused")
        self.permit({self.lineage(fid): self.passed(fid)})
        self.box(mode="gate")
        self.assertIn("not live", elane_xs.forward_seats(self.gate())["waits"][fid])
        self.assertEqual(self.fam(fid)["band"], "gym")
        self.store.set_state(fid, gate_hold=True)
        self.box(mode="live")
        self.assertIn("held by the operator", elane_xs.forward_seats(self.gate())["waits"][fid])
        self.store.set_state(fid, gate_hold=False)
        self.assertEqual(elane_xs.forward_seats(self.gate())["seated"], [fid])

    def test_the_gate_round_asks_the_pool_right_after_the_seat_path(self):
        source = inspect.getsource(gate_mod.Gate.equity_round)
        self.assertLess(source.index("elane_forward.step(self)"), source.index("elane_xs.forward_seats(self)"))
        fid = self.family("rev-a")["id"]
        self.permit({self.lineage(fid): self.passed(fid)})
        out: dict = {"held": [], "looked": []}
        gate_mod.Gate(self.store, None, None, self.settings, clock=self.store.clock).equity_round(out)
        self.assertEqual((out["forward"]["eligible"], out["forward_panel"]["seated"]), ([fid], [fid]), out)
        self.assertEqual(self.fam(fid)["band"], "candidate")


class ThePoolsRoom(Base):
    def test_no_seat_in_the_pool_seats_nobody_and_spends_nothing(self):
        fid = self.family("rev-a")["id"]
        self.permit({self.lineage(fid): self.passed(fid)})
        self.box(fwd1="on", seats=0)               # elane.panel.seats 0: the swarm lowers the row to none
        self.assertEqual(bands.panel_pool_seats(self.root), 0)
        forward, pool = self.round()
        self.assertEqual(forward["eligible"], [fid])
        self.assertIn("no free seat", pool["waits"][fid])
        self.assertEqual(self.fam(fid)["band"], "gym")
        self.assertIs(self.fam(fid)["state"][EF.STATE_KEY]["seated"], False, "it waits eligible: nothing is spent")
        self.box(fwd1="on")
        self.assertEqual(elane_xs.forward_seats(self.gate())["seated"], [fid], "a seat freed: it is seated")

    def test_a_held_seat_leaves_no_room(self):
        first, second = self.family("rev-a")["id"], self.family("mom-b")["id"]
        self.permit({self.lineage(first): self.passed(first), self.lineage(second): self.passed(second,
                     cell="equity / xs_momentum / panel:sp500")})
        forward, pool = self.round()
        self.assertEqual(sorted(forward["eligible"]), sorted([first, second]), "two cells: both eligible")
        self.assertEqual(len(pool["seated"]), 1, "ONE seat in the pool (equity_money.panel.seats 1)")
        [waiting] = [fid for fid in (first, second) if fid not in pool["seated"]]
        self.assertIn("no free seat (1 of 1 held", pool["waits"][waiting])
        self.store.set_band(pool["seated"][0], "probe", reason="the EquityBook's seat (a test's)")
        self.assertIn("no free seat", elane_xs.forward_seats(self.gate())["waits"][waiting], "a Probe holds the seat")
        self.store.set_band(pool["seated"][0], "gym", reason="demoted by the money rows (a test's)")
        self.assertEqual(elane_xs.forward_seats(self.gate())["seated"], [waiting], "the seat is free again")


class OneSeatAMechanismCell(Base):
    def test_two_passes_in_one_cell_take_one_seat_whatever_the_room(self):
        one, two, other = (self.family(slug)["id"] for slug in ("rev-a", "rev-b", "mom-c"))
        self.permit({self.lineage(one): self.passed(one), self.lineage(two): self.passed(two),
                     self.lineage(other): self.passed(other, cell="equity / xs_momentum / panel:sp500")})
        with mock.patch.object(bands, "panel_pool_seats", return_value=3):   # room for three
            forward, pool = self.round()
            self.assertEqual(sorted(pool["seated"]), sorted([one, other]))
            self.assertIn("one live forward seat a mechanism cell", forward["waits"][two])
            self.assertEqual(self.fam(two)["band"], "gym")
            # A POOL THAT READ THE FLAG ALONE would seat a second copy of the cell: the flag written by hand is refused
            held = dict(self.fam(one)["state"][EF.STATE_KEY])
            self.store.set_state(two, **{EF.STATE_KEY: {**held, "lineage": self.lineage(two), "seated": False,
                                                        "run_sha": run_sha(self.store.version(two, 1))}})
            again = elane_xs.forward_seats(self.gate())
            self.assertEqual(again["seated"], [])
            self.assertIn(f"one live forward seat a mechanism cell: {one}", again["waits"][two])
            self.assertEqual(self.fam(two)["band"], "gym")
        self.assertEqual(len([f for f in elane_xs.panel_families(self.store, alive=True)
                              if f["band"] == "candidate"]), 2)


class AHistoricalLookSeatsNobody(Base):
    def looked_candidate(self, slug: str = "rev-x") -> str:
        """A panel Candidate as a pass of the look AS BUILT leaves it (league/swarm/elane_xs.py `look`): the look's
        record, the xs proof, the band. Under A34 nothing on the House can make one; this is one written by hand."""
        fid = self.family(slug)["id"]
        version = self.store.version(fid, 1)
        sha = run_sha(version)
        self.store.set_state(fid, banded_version=1, banded_sha=version["sha"], banded_at=self.store.clock(),
                             banded_evaluator={"engine": XS_ENGINE_VERSION, "xs_sha256": self.world.fingerprint(),
                                               "run_sha": sha},
                             **{elane_xs.LOOK_KEY: {"version": 1, "passed": True, "seat": elane_xs.SEAT_CANDIDATE,
                                                    "beside": "an XS1 sentence (a test's)", "verdict": {"passed": True}}})
        self.store.set_band(fid, "candidate", reason="passed its sealed look (XS1, EQUITY panel)")
        return fid

    def test_the_look_and_the_try_hold_under_every_setting_and_spend_nothing(self):
        fid = self.family("rev-a")["id"]
        F.reviewed(self.store, fid)
        for rule in ("hold", "xs1", "xs1-rc", None):
            settings = self.box(look_rule=rule) if rule else self.box()
            self.assertEqual(elane_xs.look_held(settings), elane_xs.A34_HOLD, rule)
            self.assertEqual(elane_xs.status(settings, self.root)["look"], elane_xs.A34_HOLD)
            self.assertFalse(elane.try_open(self.store, self.fam(fid), 1, settings), "no sealed Validation try")
            self.assertIsNone(elane.next_try(self.store, self.fam(fid), settings))
        owner = F.owner(self.store, self.world, self.box(look_rule="xs1"))
        self.assertEqual(elane_xs.validate(owner, self.fam(fid), self.store.version(fid, 1))["refused"], elane_xs.A34_HOLD)
        version = self.store.version(fid, 1)
        self.assertIsNone(elane.look(owner, self.fam(fid), version, run_sha(version)))
        self.assertEqual((self.store.looks(), self.world.runner.calls), ([], []), "no run, no look row")
        self.assertIsNone(elane_xs.lineage_spent(self.store, self.fam(fid), self.settings), "nothing spent or retired")
        self.assertEqual(self.fam(fid)["band"], "gym")
        # A SETTING NEVER REOPENS IT: the House's value is code (the committed module says so in its own line)
        source = Path(elane_xs.__file__).read_text(encoding="utf-8")
        self.assertIn("\nA34_FORWARD_ONLY = True\n", source)

    def test_a_panel_candidate_a_look_made_is_seatless(self):
        fid = self.looked_candidate()
        roster = bands.roster(self.root, lanes=LANES)
        self.assertIn(fid, roster["seatless"])
        self.assertNotIn(fid, roster["seated"] + roster["waiting"])
        self.assertEqual(roster["seatless_why"][fid], elane_xs.A34_SEATLESS)
        self.assertEqual([r for r in bands.read(self.root, lanes=LANES) if r["family"] == fid], [], "no row")
        self.assertEqual([r for r in bands.read(self.root, lanes=LANES, queued=True) if r["family"] == fid], [])
        self.assertEqual(elane_xs.forward_seats(self.gate()), {"seated": [], "waits": {}}, "no pass, no forward seat")
        # It is A34 that refuses it: the same Candidate under the route as built would hold the pool's seat.
        with mock.patch.object(elane_xs, "A34_FORWARD_ONLY", False):
            self.assertIn(fid, bands.roster(self.root, lanes=LANES)["seated"])

    def test_a_forward_record_of_another_case_or_version_holds_no_seat(self):
        """`forward_seated` reads the record whole: a panel Candidate whose forward record says case XS1, or names a
        version the band proof does not, holds no seat however `seated` was written."""
        fid = self.looked_candidate()
        sha = run_sha(self.store.version(fid, 1))
        record = {"eligible": True, "seated": True, "lineage": self.lineage(fid), "version": 1, "run_sha": sha,
                  "cell": CELL, "type": "PANEL", "case": "N", "words": WORDS}
        for name, over in (("case XS1", {"case": "XS1"}), ("another version", {"version": 2}),
                           ("an ETF record", {"type": "ETF"}), ("not seated", {"seated": False}),
                           ("not eligible", {"eligible": False})):
            with self.subTest(name):
                self.store.set_state(fid, **{EF.STATE_KEY: {**record, **over}})
                self.assertFalse(elane_xs.forward_seated(self.fam(fid)))
                self.assertIn(fid, bands.roster(self.root, lanes=LANES)["seatless"])
        self.store.set_state(fid, **{EF.STATE_KEY: record})
        self.assertTrue(elane_xs.forward_seated(self.fam(fid)), "the whole record holds the seat")
        self.assertIn(fid, bands.roster(self.root, lanes=LANES)["seated"])

    def test_a_pass_of_case_xs1_takes_no_seat_however_its_state_was_written(self):
        fid = self.family("rev-a")["id"]
        self.permit({self.lineage(fid): self.passed(fid, case="XS1")})
        forward, pool = self.round()
        self.assertIn("A34", forward["waits"][fid])
        self.assertEqual(pool, {"seated": [], "waits": {}})
        row = self.passed(fid, case="XS1")
        self.store.set_state(fid, **{EF.STATE_KEY: {"eligible": True, "seated": False, "lineage": self.lineage(fid),
                                                    "version": 1, "run_sha": row["run_sha"], "cell": CELL,
                                                    "type": "PANEL", "case": "XS1"}})
        pool = elane_xs.forward_seats(self.gate())
        self.assertIn("A34", pool["waits"][fid])
        self.assertEqual(self.fam(fid)["band"], "gym")


class TheSwitchOff(Base):
    def test_with_the_forward_seats_off_nothing_panel_is_seated(self):
        fid = self.family("rev-a")["id"]
        self.permit({self.lineage(fid): self.passed(fid)})
        self.box(fwd1="off")
        self.assertEqual(self.round(), ({}, {}))
        self.assertEqual(self.fam(fid)["band"], "gym")
        self.assertNotIn(EF.STATE_KEY, self.fam(fid)["state"])
        # a pass made eligible while the switch was on, then the switch put down: the pool seats nothing
        self.box(fwd1="on")
        EF.step(self.gate())
        self.box(fwd1="off")
        self.assertEqual(elane_xs.forward_seats(self.gate()), {})
        self.assertEqual(self.fam(fid)["band"], "gym")
        self.assertIsNotNone(EF.seat_refused(self.store, self.fam(fid), self.settings))

    def test_the_committed_policy_ships_every_switch_of_the_path_off(self):
        from league.tests import REAL_POLICY_PATH

        policy = json.loads(REAL_POLICY_PATH.read_text(encoding="utf-8"))
        self.assertEqual((policy["elane"]["fwd1"]["seats"], policy["elane"]["panel"]["mode"],
                          policy["elane"]["panel"]["look_rule"]), ("off", "off", "hold"))
        self.assertFalse(EF.seats_on(policy))


if __name__ == "__main__":
    unittest.main()
