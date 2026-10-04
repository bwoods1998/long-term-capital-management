"""THE FAST LANE, end to end (release F1, Oct 3, 2026; the owner's rule 2 of that day: "a program trades real money at
Probe size as soon as it passes Validation and the unseen-market test. No session-count wait. The ladder records
alongside and decides sizing up and demotion only. Losses stay capped by the money table's existing probe, daily-stop
and drawdown-stop rows").

The swarm's REAL store, tournament and gate, and the House's REAL `OptionsLive` on the same state directory, under the
switches the tree ships (`gate.SEALED_LOOKS` True, `bands.TUITION_ROWS` False, `options_money.ladder.binding` false; no
patch here). The Gym, Sail and the venue are the fakes (`FakeGymPool`, `swarm_fakes`, `live_fakes`: invented numbers).

What it pins, whole:
- a look that passes on a Saturday is a Candidate at once; the House's quiet-hours families pass makes it a Probe on an
  EMPTY forward record, with no practice record and no ladder receipt; its real instance is wanted for Monday's first
  minute and its open is sized by the Probe cap. No session and no day is counted between the pass and the order;
- a look that lands inside a session is immediately Probe-eligible; only its program's normal intent makes an order;
- a structure whose one-lot maximum loss with fees is over the Probe cap and its floor stays a Candidate, with the
  reason recorded;
- the gate's forward replay can still return it: 20 or more losing forward trades before Monday, and no real instance
  is left; a record that is not negative still trades;
- NO BAND ROW WITHOUT ITS LOOK: a band and a proof with no passed look row give no row and no real instance; nor does
  a forward-ladder proof, whatever receipt it names, while the look is the route;
- tuition stays retired: the only real instance a Gym-band family can get is the incubator's (the owner's own switch,
  the one route where one-lot real money comes before the unseen-market test)."""

from __future__ import annotations

import copy
import datetime as dt
import json
import unittest
from decimal import Decimal as D

from league.constitution import CONSTITUTION
from league.swarm import bands
from league.swarm import gate as G
from league.swarm import settings as S
from league.swarm.evaluator import KEY, identity
from league.swarm.gate import Gate, run_sha
from league.swarm.models import ModelRouter
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.evaluator_fakes import band_proof, passed_look, reviewed, seed_current_run
from league.tests.swarm_fakes import FakeFrontier, FakeMonth, provider
from league.tests.test_live_step import HAVE, LiveCase
from league.tests.test_swarm_rounds import FakeGymPool, strong, weak

if HAVE:
    from league.live import ladder as L
    from league.live.families import SwarmFamilies
    from league.tests.live_fakes import MONDAY, VERTICAL, at

#: The switches as the tree ships them, read at import (before any test's patch).
SHIPPED = (G.SEALED_LOOKS, bands.TUITION_ROWS, CONSTITUTION["options_money"]["ladder"]["binding"])
IMAGE = "synthetic-image"
PASS = {"text": json.dumps({"verdict": "pass", "reasons": []})}
SATURDAY, SUNDAY, TUESDAY = (MONDAY + dt.timedelta(days=d) for d in (-2, -1, 1)) if HAVE else (None, None, None)


class SwarmSide:
    """The swarm on the House's own state directory: its real store, tournament and gate over a fake Gym (a named image
    and this checkout's bundle) and a scripted Sail. A mixin for a `LiveCase` (`swarm()` after its `setUp`)."""

    def swarm(self) -> None:
        cfg = json.loads((self.root / "swarm.json").read_text())
        cfg["gym"] = {"image_checkpoint": IMAGE}
        (self.root / "swarm.json").write_text(json.dumps(cfg))
        self.bundle = bands._bundle()
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.store.put(KEY, identity(IMAGE, self.bundle))
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.settings["gym"].update(gate_checkpoint=IMAGE, image_checkpoint=IMAGE)
        # A best's 1.5x Train run is its researcher's (league/tests/test_swarm_search.py), and the Train drift screen
        # needs the Gym's yearly figures (league/tests/test_swarm_drift.py): Train's side, not this route's.
        self.settings["tournament"].update(require_robustness=False, drift_screen=False)
        self.settings["budget"] = {"source": "test", "sail_usd_day": 1000.0, "claude_usd_day": 1000.0}
        self.typical: dict[str, float] = {}             # a family's one-lot maximum loss in its Validation run
        self.holdout = strong                           # what a holdout look answers
        self.forward_trades: list[dict] | None = None   # what a forward replay answers
        self.pool = FakeGymPool(self.gym)
        self.pool.image = lambda kind="gym": IMAGE
        self.pool.bundle = lambda: self.bundle
        self.replies: list = []
        self.provider, self.sail = provider(self.root / "p.sqlite",
                                            lambda body: self.replies.pop(0) if self.replies else {"text": "{}"})
        self.addCleanup(self.provider.close)
        self.asked: list = []
        self.router = ModelRouter(self.store, self.provider, settings=self.settings, month=FakeMonth(None),
                                  frontier_factory=lambda model: FakeFrontier(model, asked=self.asked))
        self.tournament = Tournament(self.store, self.pool, self.settings, clock=self.clock)

    def gym(self, job) -> dict:
        """The fake Gym: every result names the image and the bundle it ran on, as production's do."""
        if job.window == "forward":
            out = {**weak(job), "trades": list(self.forward_trades or [])}
        else:
            out = self.holdout(job) if job.window == "holdout" else strong(job)
        if job.window == "validation" and job.family in self.typical:
            out["summary"]["median_max_loss_per_structure"] = self.typical[job.family]
        return {**out, "gym_image": IMAGE, "gym_bundle": self.bundle}

    def born(self, fid: str = "vert", *, code: str | None = None, params: dict | None = None,
             structure: str = "debit_vertical") -> str:
        """A Gym family whose version 1 is its best by an eligible Train run on the Gym in force. Its run sha."""
        self.store.add_family({"id": fid, "mechanism": "An invented mechanism for the fast lane's test.",
                               "structure": structure, "roots": ["SPY"], "dte": [0, 2]}, origin="test")
        version = self.store.add_version(fid, VERTICAL if code is None else code,
                                         {"hold": 600} if params is None else params, author="test")
        row = seed_current_run(self.store, fid, 1, window="train")
        self.store.update_family(fid, best_train=1.2, best_version=1)
        self.store.set_state(fid, best_train_run=row["run_id"], best_train_version=1)
        return run_sha(version)

    def validated(self, fid: str = "vert", **kw) -> str:
        """`born`, then validated by the tournament: the line met, at the gate."""
        sha = self.born(fid, **kw)
        self.assertTrue(self.tournament.validate([self.store.family(fid)])["judged"][fid]["passed"])
        self.assertTrue(self.fam(fid)["state"]["gate_ready"])
        return sha

    def gate_round(self) -> dict:
        return Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()

    def look(self, fid: str = "vert", **kw) -> str:
        """Validation, the review, the audit and the one holdout look, in one gate round: the look's verdict is the
        round's. Its run sha."""
        sha = self.validated(fid, **kw)
        self.replies = [PASS, PASS]
        out = self.gate_round()
        self.assertEqual([x["family"] for x in out["looked"]], [fid], out)
        self.assertEqual(len(self.sail.bodies), 2, "one review and one audit")
        return sha

    def fam(self, fid: str = "vert") -> dict:
        return self.store.family(fid)

    def band(self, fid: str = "vert") -> str:
        return self.fam(fid)["band"]


@unittest.skipUnless(HAVE, "numpy not installed")
class FastLaneCase(SwarmSide, LiveCase):
    def setUp(self):
        super().setUp()
        self.swarm()

    def house(self):
        """The House on the swarm's own store (`SwarmFamilies`), real money on, the grant active."""
        live = self.make([])
        self.addCleanup(live.observe_store.close)
        live.families = SwarmFamilies(self.root)
        self.addCleanup(lambda: live.families._store.close() if live.families._store is not None else None)
        return live

    def quiet(self, minutes: int = 5) -> dict:
        """The House's next pass `minutes` later (outside a session: the quiet hours' families pass, every five minutes)."""
        self.clock.set(self.clock() + 60 * minutes)
        return self.live.minute()

    def to(self, day: dt.date, hh: int, mm: int) -> dict:
        self.clock.set(at(day, hh, mm))
        return self.live.minute()

    def band_moves(self, fid: str = "vert") -> list[tuple]:
        return [(p["from"], p["to"]) for p, a in self.ledger.of("live.band") if a == fid and not p.get("held")]

    def real_instances(self) -> list[str]:
        return sorted(k for k, inst in self.live.instances.items() if inst.kind == "real")

    def practice_record(self) -> tuple:
        """(cohorts, practice rows, ladder receipts, entrants) in the House's practice record."""
        db = self.live.observe_store._connect()
        return tuple(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("cohorts", "practice", "ladder_decisions", "entrants"))

    def probe_cap(self) -> D:
        return self.live.table.probe_share * self.live.sizing_equity()


class TheSwitches(unittest.TestCase):
    def test_as_shipped(self):
        self.assertEqual(SHIPPED, (True, False, False),
                         "the sealed look is the route to Probe; tuition stays retired; the ladder records")
        self.assertIs(bands.ladder_promotes(), False)


class ASaturdayPass(FastLaneCase):
    def test_a_look_that_passes_on_a_saturday_trades_at_probe_size_from_mondays_first_minute(self):
        self.clock.set(at(SATURDAY, 11, 0))
        live = self.house()
        self.assertEqual(live.minute()["state"], "closed")
        self.assertEqual((live.families.read(), live.instances), ([], {}), "before the look: nothing to run")

        # 11:01 on Saturday: the review, the audit and the one look. A pass is a Candidate in the same round.
        self.clock.set(at(SATURDAY, 11, 1))
        sha = self.look()
        state = self.fam()["state"]
        self.assertEqual((self.band(), state["gate"], state["gate_outcome"]["result"], state["banded_version"]),
                         ("candidate", "pass", "passed", 1))
        [look] = self.store.looks()
        self.assertEqual((look["family"], look["version"], look["run_sha"], look["passed"]), ("vert", 1, sha, 1))
        [row] = live.families.read()
        self.assertEqual((row["band"], row["holdout_passed"], row["run_sha"], row["typical_max_loss_usd"], row["forward"]),
                         ("candidate", True, sha, 60.0, None))

        # The House's quiet-hours families pass (every five minutes, nights and weekends included): Probe.
        self.quiet()
        self.assertEqual((self.band(), self.band_moves()), ("probe", [("candidate", "probe")]),
                         "minutes after the pass: no session counted, no day waited")
        moved = dt.datetime.fromtimestamp(self.fam()["state"]["live_promoted_at"], dt.timezone.utc)
        self.assertEqual((moved.date(), moved.weekday()), (SATURDAY, 5), "on the Saturday itself")
        self.assertEqual(self.store.forward("vert"), [], "on an EMPTY forward record")
        self.assertEqual(self.practice_record(), (0, 0, 0, 0), "no practice cohort, no practice row, no ladder receipt")
        self.assertEqual(self.fam()["state"]["banded_evaluator"].get("route"), None, "the look's proof, not the ladder's")
        self.assertEqual(self.real_instances(), ["vert@1:r"], "its real instance is wanted for the next session already")
        self.assertEqual(self.venue.sent, [], "and no order goes while the market is closed")
        for _ in range(3):
            self.quiet(60)
        self.assertEqual((self.band(), self.venue.sent), ("probe", []))

        # Monday's first minute: the real open, sized by the Probe cap (never by the program's own quantity).
        out = self.to(MONDAY, 9, 31)
        self.assertEqual((out["state"], sorted(live.instances)), ("session", ["vert@1:r", "vert@1:s"]))
        real = live.instances["vert@1:r"]
        self.assertEqual((real.code, real.params, real.version, real.band), (VERTICAL, {"hold": 600}, 1, "probe"),
                         "exactly the program that was looked at")
        [sent] = self.venue.sent
        self.assertEqual(sent["order_class"], "mleg")
        [position] = live.book.positions.values()
        unit = position.max_loss_share * 100 + 2 * (position.fees / position.qty)
        cap = self.probe_cap()
        self.assertEqual(position.qty, int(cap // D(str(round(unit, 2)))), "as many lots as the Probe cap holds")
        self.assertLessEqual(D(str(unit)) * position.qty, cap)
        self.assertGreater(position.qty, 1)
        [(fill, agent)] = self.ledger.of("book.fill")
        self.assertEqual((agent, fill["side"], fill["real_money"]), ("vert", "buy", True))
        self.assertEqual(self.practice_record(), (0, 0, 0, 0), "still no practice record: the look was its test")

    def test_the_ladder_blocks_nothing_and_judges_nothing_of_it(self):
        """Beside the lane: the ladder's session end sees no cohort of the fast-lane Probe, writes no receipt, and its
        demotion does not read a band the look earned."""
        self.clock.set(at(SATURDAY, 11, 0))
        live = self.house()
        live.minute()
        self.look()
        self.quiet()
        self.assertEqual(self.band(), "probe")
        out = L.end_of_day(live, MONDAY.isoformat())
        self.assertEqual((out["binding"], out["judged"], out["verdicts"], out["demoted"], out["entrants"]),
                         (False, 0, {}, [], 0))
        self.assertEqual((L.SwarmBridge(live.families).ladder_families(), self.band()), ([], "probe"))


class APassInsideASession(FastLaneCase):
    def test_a_look_that_lands_inside_a_session_is_immediately_eligible_at_probe_size(self):
        live = self.house()
        self.run_to(9, 40)                                    # Monday's session is under way
        self.assertEqual((live.instances, self.venue.sent), ({}, []))
        self.look()
        self.assertEqual(self.band(), "candidate")
        live.sync_families(self.clock(), force=True)
        self.assertEqual(self.real_instances(), ["vert@1:r"])
        self.assertEqual(self.venue.sent, [], "qualification creates no forced order")
        self.run_to(9, 50)
        self.assertEqual((self.band(), self.band_moves()), ("probe", [("candidate", "probe")]),
                         "a Probe within minutes, inside the session")
        moved = dt.datetime.fromtimestamp(self.fam()["state"]["live_promoted_at"], dt.timezone.utc)
        self.assertEqual(moved.date(), MONDAY)
        self.assertIn("vert@1:s", live.instances, "its shadow runs")
        real = live.instances["vert@1:r"]
        self.assertEqual((real.code, real.params, real.band, len(self.venue.sent)), (VERTICAL, {"hold": 600}, "probe", 1),
                         "the program's first normal intent trades within the same session")
        [position] = live.book.positions.values()
        self.assertLessEqual(D(str(position.max_loss)), self.probe_cap())
        self.assertEqual((len(self.store.looks()), self.practice_record()), (1, (0, 0, 0, 0)),
                         "no second unseen read or ladder checkpoint admits the first Probe")


class AStructureOverTheProbeCap(FastLaneCase):
    def test_as_shipped_such_a_version_waits_before_the_gate_and_no_look_is_spent_on_it(self):
        """WHERE THE RESEARCH STREAM MEETS THE FAST LANE (release F1): THE UNIT ON VALIDATION (`Tournament._verdict`,
        `researcher.max_unit_usd`: the Probe's one-contract floor) reads the unit the money table will fit BEFORE the
        gate. A version that met the line with one lot over it waits there: no review, no audit, no look, no band, and
        nothing refused. When the owner's limit moves it goes on by itself, and the money table still has the last word
        (the test below)."""
        self.clock.set(at(SATURDAY, 11, 0))
        live = self.house()
        live.minute()
        self.typical["vert"] = 5000.0
        self.born()
        out = self.tournament.validate([self.store.family("vert")])["judged"]["vert"]
        self.assertEqual((out["passed"], out.get("unit_wait")), (True, True))
        state = self.fam()["state"]
        self.assertEqual((state["gate_ready"], state["unit_wait"], state["typical_max_loss_usd"]),
                         (False, {"version": 1, "limit": 100.0}, 5000.0))
        self.replies = [PASS, PASS]
        out = self.gate_round()
        self.assertEqual((out["looked"], out["refused"], out["look_held"], out["look_waiting"], out["waiting"]), ([], [], [], [], []))
        self.assertEqual((self.sail.bodies, self.asked, self.store.looks(), self.store.refusals("vert"), self.band()),
                         ([], [], [], [], "gym"), "nothing paid, nothing opened, nothing refused: a wait")
        for _ in range(3):
            self.quiet()
        self.assertEqual((self.band(), self.band_moves(), self.real_instances()), ("gym", [], []))
        # The owner raises the limit over this unit: the version goes to the gate by itself and gets its one look, and
        # the money table, whose cap did not move, keeps it a Candidate.
        self.settings["researcher"]["max_unit_usd"] = 6000
        self.tournament.validate([self.store.family("vert")])
        self.assertEqual((self.fam()["state"]["gate_ready"], self.fam()["state"]["unit_wait"]), (True, None))
        out = self.gate_round()
        self.assertEqual(([x["family"] for x in out["looked"]], len(self.sail.bodies), len(self.store.looks())), (["vert"], 2, 1))
        for _ in range(3):
            self.quiet()
        self.assertEqual((self.band(), self.band_moves(), self.real_instances()), ("candidate", [], []))

    def test_a_one_lot_loss_over_the_cap_and_the_floor_stays_a_candidate_with_the_reason(self):
        """A passed look does not guarantee trading: the money table keeps a Candidate shadow-only when one lot of its
        typical structure, with fees, is over the Probe cap and the one-contract floor. The look is spent all the same.
        (Reached only past THE UNIT ON VALIDATION, which makes such a version wait before the gate as shipped: here the
        owner's switch for that wait is off, `researcher.max_unit_usd` null, so the money table's own rule is what
        stands between the look and an order.)"""
        self.settings["researcher"]["max_unit_usd"] = None
        self.clock.set(at(SATURDAY, 11, 0))
        live = self.house()
        live.minute()
        self.typical["vert"] = 5000.0
        self.look()
        self.assertEqual((self.band(), live.families.read()[0]["typical_max_loss_usd"]), ("candidate", 5000.0))
        for _ in range(4):
            self.quiet()
        self.assertEqual((self.band(), self.band_moves(), self.real_instances()), ("candidate", [], []))
        [(held, agent)] = [(p, a) for p, a in self.ledger.of("live.band") if p.get("held")]
        self.assertEqual((agent, held["from"], held["to"]), ("vert", "candidate", "candidate"))
        cap, floor = self.probe_cap(), live.table.probe_floor
        self.assertGreater(D("5000"), max(cap, floor))
        self.assertIn("its typical structure risks $5000.00, over the Probe's cap of", held["why"])
        self.assertIn(f"the one-contract floor of ${floor}", held["why"])
        self.to(MONDAY, 9, 31)
        self.run_to(9, 40)
        self.assertEqual((self.band(), self.real_instances(), self.venue.sent), ("candidate", [], []),
                         "shadow only: no real order, at any size")
        self.assertIn("vert@1:s", live.instances)
        self.assertEqual(len(self.store.looks()), 1, "its look is spent, and counted for every later look")


class TheForwardReplay(FastLaneCase):
    """One more judge stands between a pass and the first Probe order: the gate's forward replay of the banded version
    over the days after the holdout (`Gate.forward`). It only tightens."""

    def saturday_probe(self):
        self.clock.set(at(SATURDAY, 11, 0))
        live = self.house()
        live.minute()
        self.look()
        self.quiet()
        self.assertEqual((self.band(), self.real_instances()), ("probe", ["vert@1:r"]))
        return live

    def replay(self, pnl: float, n: int = 25) -> dict:
        """The gate's forward replay on Sunday: `n` forward trades of `pnl` each."""
        self.clock.set(at(SUNDAY, 8, 0))
        self.forward_trades = [{"id": i, "day": f"2026-09-{21 + i % 5:02d}", "entry_minute": 600 + i, "root": "SPY",
                                "type": "debit_vertical", "pnl": pnl, "max_loss": 60.0} for i in range(n)]
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.assertTrue(gate.forward_due())
        out = gate.forward()
        self.assertEqual((out["families"], out["trades"]), (1, n))
        return out

    def test_twenty_or_more_losing_forward_trades_before_monday_leave_no_real_instance(self):
        live = self.saturday_probe()
        self.replay(-5.0)
        record = self.fam()["state"]["forward"]
        self.assertEqual((record["trades"], record["negative"], self.band()), (25, True, "probe"),
                         "the swarm flags it; a Probe's band is the live path's to move")
        self.quiet()
        self.assertEqual((self.band(), self.band_moves()), ("candidate", [("candidate", "probe"), ("probe", "candidate")]))
        [(back, _)] = [(p, a) for p, a in self.ledger.of("live.band") if p.get("to") == "candidate" and not p.get("held")]
        self.assertIn("its forward record turned negative", back["why"])
        self.to(MONDAY, 9, 31)
        self.run_to(9, 40)
        self.assertEqual(self.venue.sent, [], "no real order on Monday")
        self.assertNotEqual(getattr(live.instances.get("vert@1:r"), "mode", "gone"), "live", "its real instance left the real band")
        # And the gate's next judgement sends the Candidate back to the Gym, its program's bar for good.
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.assertEqual(gate.judge_forward("vert"), {"family": "vert", "to": "gym"})
        state = self.fam()["state"]
        self.assertEqual((self.band(), state["gate_outcome"]["result"], live.families.read()), ("gym", "demoted", []))

    def test_a_record_that_is_not_negative_still_trades(self):
        live = self.saturday_probe()
        self.replay(4.0)
        record = self.fam()["state"]["forward"]
        self.assertEqual((record["trades"], record["negative"]), (25, False))
        self.quiet()
        self.assertEqual((self.band(), self.band_moves()), ("probe", [("candidate", "probe")]),
                         "25 shadow replay trades are no real fills: still a Probe, and never Sized on them")
        self.to(MONDAY, 9, 31)
        self.assertEqual((self.real_instances(), len(self.venue.sent)), (["vert@1:r"], 1))

    def test_nineteen_losing_trades_are_not_yet_a_verdict(self):
        self.saturday_probe()
        self.replay(-5.0, n=19)
        self.assertIs(self.fam()["state"]["forward"]["negative"], False)
        self.quiet()
        self.to(MONDAY, 9, 31)
        self.assertEqual((self.band(), len(self.venue.sent)), ("probe", 1))


class NoBandRowWithoutItsLook(FastLaneCase):
    def banded_by_hand(self, band: str = "probe") -> str:
        """A family some other writer banded: a live band and a proof that names the running release exactly, and no
        look of the gate's behind it."""
        sha = self.validated()
        version = self.store.version("vert", 1)
        self.store.set_state("vert", gate_ready=False, banded_version=1, banded_sha=version["sha"], banded_at=self.clock(),
                             banded_evaluator=band_proof(version), live_promoted_at=at(SATURDAY - dt.timedelta(days=7), 12, 0))
        self.store.set_band("vert", band, reason="written by another writer")
        self.assertTrue(bands.current_banded_evaluator(self.fam()["state"], sha), "its proof is current")
        return sha

    def test_a_band_with_a_proof_and_no_passed_look_row_gives_no_row_and_no_real_instance(self):
        self.clock.set(at(SATURDAY, 11, 0))
        live = self.house()
        self.banded_by_hand("probe")
        self.assertEqual((self.band(), self.store.looks(), bands.read(self.root), live.families.read()),
                         ("probe", [], [], []))
        for _ in range(3):
            self.quiet()
        self.to(MONDAY, 9, 31)
        self.run_to(9, 40)
        self.assertEqual((live.instances, self.venue.sent, self.band_moves()), ({}, [], []),
                         "no instance of any kind, no order, no band move")

    def test_a_ladder_proof_gives_no_row_and_no_real_instance_while_the_look_is_the_route(self):
        """One route to real money at a time. A band whose proof is THE FORWARD LADDER's (route "ladder"), with a
        `promote` receipt of the House's own practice record naming that very family, version and program: in the
        ladder's own mode it is a Probe's row. As shipped the ladder promotes nothing, so the House wrote no such
        receipt and no such band; whoever did, it gives no row and no real instance."""
        from unittest.mock import patch

        self.clock.set(at(SATURDAY, 11, 0))
        live = self.house()
        sha = self.validated()
        version = self.store.version("vert", 1)
        db = live.observe_store._connect()
        with db:
            receipt = db.execute(
                "INSERT INTO ladder_decisions(day, family, version, run_sha, inputs, stats, verdict, binding, at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (SATURDAY.isoformat(), "vert", 1, sha, "{}", "{}", "promote", 1, self.clock())).lastrowid
        self.store.set_state("vert", gate_ready=False, banded_version=1, banded_sha=version["sha"], banded_at=self.clock(),
                             banded_evaluator={**band_proof(version), "route": "ladder", "receipt": receipt},
                             live_promoted_at=at(SATURDAY - dt.timedelta(days=7), 12, 0))
        self.store.set_band("vert", "probe", reason=f"written by another writer (ladder receipt {receipt})")
        self.assertTrue(bands.current_banded_evaluator(self.fam()["state"], sha), "its proof is current")
        self.assertTrue(bands.ladder_receipt(self.root, family="vert", version=1, run_sha=sha, receipt=receipt),
                        "and its receipt is in the House's record")
        with patch("league.swarm.gate.SEALED_LOOKS", False):   # the ladder's own mode: this very band is a Probe's row
            self.assertEqual([(r["family"], r["band"], r["holdout_passed"]) for r in bands.read(self.root)],
                             [("vert", "probe", True)])
        self.assertEqual(SHIPPED, (True, False, False))
        self.assertEqual((self.band(), self.store.looks(), bands.ladder_promotes()), ("probe", [], False))
        self.assertEqual((bands.read(self.root), live.families.read()), ([], []))
        for _ in range(3):
            self.quiet()
        self.to(MONDAY, 9, 31)
        self.run_to(9, 40)
        self.assertEqual((live.instances, self.venue.sent, self.band_moves()), ({}, [], []),
                         "no instance of any kind, no order, no band move")

    def test_only_a_passed_look_at_that_very_family_version_and_program_stands_behind_a_band(self):
        sha = self.banded_by_hand("candidate")
        self.store.add_look("vert", 1, sha, passed=False, p_value=0.4, detail={})
        self.assertEqual(bands.read(self.root), [], "a failed look is no pass")
        self.store._exec("DELETE FROM looks")
        self.store.add_look("vert", 2, sha, passed=True, p_value=0.001, detail={})
        self.assertEqual(bands.read(self.root), [], "a passed look at another version")
        self.store._exec("DELETE FROM looks")
        self.store.add_look("other", 1, sha, passed=True, p_value=0.001, detail={})
        self.assertEqual(bands.read(self.root), [], "a passed look made in another family")
        self.store._exec("DELETE FROM looks")
        self.store.add_look("vert", 1, "another-program", passed=True, p_value=0.001, detail={})
        self.assertEqual(bands.read(self.root), [], "a passed look at another program")
        self.store._exec("DELETE FROM looks")
        passed_look(self.store, "vert", self.store.version("vert", 1))
        [row] = bands.read(self.root)
        self.assertEqual((row["family"], row["band"], row["holdout_passed"], row["run_sha"]), ("vert", "candidate", True, sha))


if HAVE:
    from league.tests.test_live_incubator import PARAMS, PROGRAM, Base as IncubatorBase, winning


@unittest.skipUnless(HAVE, "numpy not installed")
class TheOnlyRealGymInstanceIsTheIncubators(SwarmSide, IncubatorBase if HAVE else unittest.TestCase):
    """Under the shipped switches a Gym-band family gets no tuition instance (`:t`): tuition is retired, so no real money
    comes before the unseen-market test on the swarm's own route. THE INCUBATOR stays the owner's switch (his row of
    Sept 29: one lot, $50 a structure, 4 open, $150 a week): it is the ONE route where one-lot real money comes before
    that test, and its `:i` is the only real instance a Gym-band family can get."""

    def setUp(self):
        super().setUp()                                   # the incubator's switch on (`live.incubator`), as production's
        self.swarm()

    def house(self):
        live = self.make()
        self.addCleanup(live.observe_store.close)
        live.families = SwarmFamilies(self.root)
        self.addCleanup(lambda: live.families._store.close() if live.families._store is not None else None)
        return live

    def reviewed_and_waiting(self, fid: str = "tuit") -> str:
        """A Gym family on the retired tuition route: validated (the line met), its review and audit passed, waiting
        for its look."""
        sha = self.validated(fid)
        self.store.set_state(fid, review=reviewed(sha))
        return sha

    def incubated(self, fid: str = "inc") -> str:
        """A Gym family the incubator's facts admit, on the swarm's real store: never validated, a current Train and
        drift mark, its incubator review and audit passed; and its practice cohort (three sessions, ten winning
        closes) in the House's record, frozen on that very program."""
        sha = self.born(fid, code=PROGRAM, params=PARAMS)
        self.store.put("train_objective", "robust")
        self.store.set_state(fid, train_passed={"1": {"evaluator": self.store.get(KEY), "objective": "robust",
                                                      "robust_pnl": 40.0, "drift": {"t": 2.4, "positive": 3, "years": 3}}},
                             incubator_reviews={sha: reviewed(sha)})
        [facts] = bands.incubator(self.root, family=fid, version=1)
        self.assertEqual((facts["run_sha"], facts["incubator"], facts["band"]), (sha, True, "gym"))
        self.cohort(fid, 1, trades=winning(), incubate=False, code=PROGRAM, params=PARAMS, run_sha=sha)
        return sha

    def test_no_tuition_instance_and_the_incubators_is_the_only_real_one(self):
        live = self.house()
        self.reviewed_and_waiting("tuit")
        self.incubated("inc")
        self.assertEqual([(r["family"], r["band"]) for r in bands.read(self.root, tuition=True)], [("tuit", "gym")],
                         "the retired route's own read: a tuition row")
        self.assertEqual((bands.read(self.root), live.families.read()), ([], []), "as shipped: no Gym-band row")
        self.assertGreater(live.table.tuition_day, 0, "the money table's tuition row is untouched; no row reaches it")
        self.run_to(9, 31)
        real = sorted(k for k, inst in live.instances.items() if inst.kind == "real")
        self.assertEqual(real, ["inc@1:i"], "the incubator's instance, and no `:t` and no `:r`")
        inst = live.instances["inc@1:i"]
        self.assertEqual((inst.tuition, inst.incubator, inst.band), (True, True, "gym"))
        [row] = self.opens("inc")
        self.assertEqual((row["qty"], row["instance"]), (1, "inc@1:i"), "one lot, whatever the program asked")
        cap = float(CONSTITUTION["options_money"]["incubator"]["max_loss_usd"])
        self.assertLessEqual(row["max_loss"] + 2 * row["fees_est"], cap)
        self.assertEqual(self.opens("tuit"), [], "the validated, reviewed family sends nothing before its look")
        self.run_to(9, 40)
        self.assertEqual((self.store.forward("inc"), self.band("inc"), self.band("tuit")), ([], "gym", "gym"),
                         "never a forward row, never a band: the incubator is no evidence and no promotion")

    def test_with_the_incubator_switched_off_a_gym_family_gets_no_real_instance_at_all(self):
        self.switch(False)
        cfg = json.loads((self.root / "swarm.json").read_text())
        cfg["gym"] = {"image_checkpoint": IMAGE}
        (self.root / "swarm.json").write_text(json.dumps(cfg))
        live = self.house()
        self.reviewed_and_waiting("tuit")
        self.incubated("inc")
        self.run_to(9, 40)
        self.assertEqual((sorted(k for k, inst in live.instances.items() if inst.kind == "real"), self.venue.sent), ([], []))


if __name__ == "__main__":
    unittest.main()
