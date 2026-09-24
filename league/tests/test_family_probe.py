"""No probe on a losing family (R5 of the close-the-gaps run, Sept 24, 2026; `allocator.family_probe`), and the proven
family on the board (R3).

The evidence (docs/research/queries/2026-09-24/R5-family-probe.py, the 15:06Z snapshot): of the allocator's 21 promotions
to real money since Sept 23 00:00Z, 11 went onto families whose pooled forward record -- the House's `family_forward`,
active blocks and summed log growth over every member ever born -- was negative over 6 or more active blocks, and they
realized -$8.12 on 22 closes with no stay positive; the other 10 made +$28.96 on 34 closes. At 15:06Z 9 of the 14 seated
probes ($139.75 of stake) sat on such families. So: no probe is seated from a losing family (the House's own breeding line,
`families.losing`); a probe seated on one goes back to practice at the next pass, by the demotion path, which never sells
a Kalshi contract, and on Alpaca only once it is flat; and a probe that went back to practice holds its family until the
family's record since then is positive over as many blocks. A proven family's agents are bunts and are never gated.
"""

import json
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from league import allocator, families
from league.constitution import CONSTITUTION, digest, money_digest
from league.ledger import now_iso
from league import seeds
from league.tests.test_allocator import IDLE, HouseCaseReal
from league.venues import instrument_for
from league.tests.test_families import real_record
from league.tests.test_promotion_on_proof import KALSHI_IDLE, KalshiHouse, canned

D = Decimal
READY = dict(e=1.10, w_paper=1.21, paper_trades=6, paper_settled=6)


class ForwardBlocks:
    """A family's pooled forward record set by the test: active `eval.block` rows of a dead member (the House's
    `family_forward` counts every agent ever born into the family, living or dead)."""

    def ghost(self, family, code):
        key = ("ghost", family)
        ghosts = self.__dict__.setdefault("_ghosts", {})
        if key not in ghosts:
            agent = self.house.spawn(f"ghost-{len(ghosts)}", family, code, reason="test", endowment="2.5")
            self.house.kill(agent, "evidence", "test: a dead member carries its family's forward record")
            ghosts[key] = agent
        return ghosts[key]

    def blocks(self, family, *growths, book="kalshi-shadow", code=KALSHI_IDLE, active=True):
        ghost = self.ghost(family, code)
        for growth in growths:
            self.house.ledger.append("eval.block", {"book": book, "active": active, "log_growth": growth, "key": "k"}, agent=ghost.id)

    def status(self, agent):
        return self.house._state["promotion_status"].get(agent.id) or {}

    def demotions(self, agent):
        return [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=agent.id) if e.payload.get("decision") == "demote"]


class TheRule(unittest.TestCase):
    def test_the_constitutions_rule_moves_the_money_digest(self):
        """The run's third money-digest change: the owner's live grant pins the new key."""
        import copy

        self.assertEqual(CONSTITUTION["allocator"]["family_probe"], {"losing_min_blocks": 6, "reseat": "gain_since_demotion"})
        self.assertEqual(families.probe_rule(), {"losing_min_blocks": 6, "reseat": "gain_since_demotion", "hold": True})
        for path in (("family_probe",), ("family_probe", "losing_min_blocks"), ("family_probe", "reseat")):
            changed = copy.deepcopy(CONSTITUTION)
            node = changed["allocator"]
            for key in path[:-1]:
                node = node[key]
            del node[path[-1]]
            self.assertNotEqual(money_digest(changed), money_digest(), path)
            self.assertNotEqual(digest(changed), digest(), path)
        # The House's own breeding line is the same count (a risk-free dial there; pinned here).
        with open("league/game.json") as f:
            self.assertEqual(json.load(f)["economy"]["losing_family_min_blocks"], CONSTITUTION["allocator"]["family_probe"]["losing_min_blocks"])

    def test_the_lines(self):
        self.assertFalse(families.losing(5, -1.0, 6))  # five blocks are not a record
        self.assertTrue(families.losing(6, -1e-9, 6))
        self.assertFalse(families.losing(6, sum([0.01, 0.01, 0.01, -0.01, -0.01, -0.01]), 6))  # -3.5e-18 nets to nothing
        self.assertFalse(families.gaining(5, 1.0, 6))
        self.assertTrue(families.gaining(6, 1e-9, 6))
        self.assertFalse(families.gaining(6, 0.0, 6))  # a record that nets to zero has not turned

    def test_without_the_key_there_is_no_gate(self):
        with patch.dict(CONSTITUTION["allocator"]):
            del CONSTITUTION["allocator"]["family_probe"]
            self.assertIsNone(families.probe_rule())

    def test_the_fold_classifies_each_demotion_from_the_ledgers_own_rows(self):
        """A demotion is a probe's when its row says so; a row that names no band (the House's drift, audit veto and
        tuition write none) by the family's state in the mechanism ledger just before it; an unfunded seat never."""
        rows, n = [], [0]

        def row(kind, agent="house", **payload):
            n[0] += 1
            rows.append(SimpleNamespace(seq=n[0], kind=kind, agent=agent, at=f"2026-09-24T13:{n[0]:02d}:00.000Z", payload=payload))

        family_of = {"a": ("fam-a", "kalshi"), "b": ("fam-b", "kalshi"), "c": ("fam-c", "alpaca"), "d": ("fam-d", "kalshi"),
                     "e": ("fam-e", "kalshi"), "f": ("fam-f", "kalshi")}.get
        row("eval.verdict", "a", decision="demote", from_rung=2, to_rung=1, band_from="probe", reason="drawdown")
        row("eval.verdict", "b", decision="demote", from_rung=2, to_rung=1, band_from="bunt", reason="hysteresis")
        row("eval.verdict", "c", decision="demote", from_rung=2, to_rung=1, reason="drift, before any family.record row")
        row("family.record", family="fam-d", venue="kalshi", state="unproven")
        row("family.record", family="fam-e", venue="kalshi", state="proven")
        row("eval.verdict", "d", decision="demote", from_rung=2, to_rung=1, reason="its growth has decayed")
        row("eval.verdict", "e", decision="demote", from_rung=2, to_rung=1, reason="the frontier audit vetoed it")
        row("eval.verdict", "f", decision="demote", from_rung=2, to_rung=1, band_from="probe", unfunded=True, reason="not lent")
        row("eval.verdict", "a", decision="demote", from_rung=3, to_rung=2, band_from="swing", reason="a swing to rung 2")
        row("eval.verdict", "a", decision="progress", stage="envelope", reason="waits")
        holds, states = {}, {}
        self.assertEqual(allocator.fold_demotions(rows, holds, states, family_of), n[0])
        self.assertEqual(sorted(holds), ["fam-a", "fam-d"])
        self.assertEqual([(d["seq"], d["agent"], d["why"]) for d in holds["fam-a"]], [(1, "a", "drawdown")])
        self.assertEqual(holds["fam-d"][0]["at"], "2026-09-24T13:06:00.000Z")
        self.assertEqual(states, {"fam-d@kalshi": "unproven", "fam-e@kalshi": "proven"})
        # Every demotion is kept, each its own hold, in ledger order; a row folded twice is kept once.
        later = [SimpleNamespace(seq=50, kind="eval.verdict", agent="a", at="2026-09-24T14:00:00.000Z",
                                 payload={"decision": "demote", "from_rung": 2, "to_rung": 1, "band_from": "probe", "reason": "again"})]
        self.assertEqual(allocator.fold_demotions(later + later, holds, states, family_of), 50)
        self.assertEqual([d["seq"] for d in holds["fam-a"]], [1, 50])
        self.assertIsNone(allocator.fold_demotions([], holds, states, family_of))


class ProbeGateOnKalshi(ForwardBlocks, KalshiHouse):
    """The gate in a House: a Kalshi probe is $10 here and a bunt $30; the family's record is set by `blocks`."""

    def seated(self, name="kay", family="weather-favorites", **evidence):
        a = self.agent(name, family=family)
        with self.evidence_of({a.id: dict(READY, **evidence)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        return a

    def test_a_losing_familys_newcomer_waits_with_the_familys_numbers(self):
        self.blocks("weather-favorites", *[-0.01] * 6)
        a = self.agent()
        with self.evidence_of({a.id: READY}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        status = self.status(a)
        self.assertEqual(status["stage"], "family_losing")
        self.assertEqual(status["reason"], "its family weather-favorites's pooled forward record is -0.0600 over 6 active blocks: "
                                           "no probe is seated from a family at or below zero after 6 (allocator.family_probe)")
        self.assertEqual(status["family_forward"], {"blocks": 6, "growth": -0.06})
        row = self.house.allocator.board()["agents"][a.id]
        self.assertEqual((row["probe_gate"], row["family_forward"]), ("losing", {"blocks": 6, "growth": -0.06}))
        # The status is written once while the numbers stand (a `progress` row only when the reason changes).
        with self.evidence_of({a.id: READY}):
            self.tick(2)
        progress = [e for e in self.house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "progress"]
        self.assertEqual(len(progress), 1)

    def test_five_blocks_are_not_a_losing_record(self):
        self.blocks("weather-favorites", *[-0.05] * 5)
        a = self.seated()
        self.assertEqual(self.house.books["kalshi"].account(a.id).staked, D("10"))
        self.assertIsNone(self.house.allocator.board()["agents"][a.id]["probe_gate"])

    def test_a_record_that_nets_to_zero_is_not_losing(self):
        self.blocks("weather-favorites", 0.01, 0.01, 0.01, -0.01, -0.01, -0.01)
        self.seated()
        blocks, growth = self.house.allocator.forward("weather-favorites")
        self.assertEqual(blocks, 6)
        self.assertLess(growth, 0)  # -3.5e-18: floating point, not a loss

    def test_inactive_blocks_and_other_families_do_not_count(self):
        self.blocks("weather-favorites", *[-0.5] * 6, active=False)
        self.blocks("kalshi-favorites", *[-0.5] * 6)
        self.seated()

    def test_a_seated_probe_on_a_losing_family_goes_back_at_the_next_pass_and_keeps_its_contracts(self):
        from league.book import Intent
        from league.tests.fakes import without_real_entry_rules
        from league.tests.test_book import event

        a = self.seated()
        book = self.house.books["kalshi"]
        instrument = event(venue="kalshi")
        self.real.set_quote(instrument, ".79", ".80")
        book.resolves_at = lambda instrument: self.clock() + 3600
        with without_real_entry_rules():  # the floor's cap on one market is $1.00 of a $10 probe's event capital here
            intent = Intent.new(agent=a.id, instrument=instrument, side="buy", quantity=D(1), reason="test", created_at=now_iso(self.clock))
            self.assertEqual(book.submit([intent])[0].status, "filled")
        held = {k: h.quantity for k, h in book.account(a.id).holdings.items()}
        self.assertTrue(held)
        self.blocks("weather-favorites", *[-0.02] * 6)
        submitted = len(self.real.submitted)
        with self.evidence_of({a.id: dict(READY, w_real=1.0)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        demote = self.demotions(a)[-1]
        self.assertEqual((demote["band_from"], demote["band_to"], demote["rule"]), ("probe", "paper", "allocator.family_probe"))
        self.assertEqual(demote["family_forward"], {"blocks": 6, "growth": -0.12})
        self.assertEqual(demote["reason"], "its family weather-favorites's pooled forward record is -0.1200 over 6 active blocks: "
                                           "a probe is not kept on a family at or below zero after 6 (allocator.family_probe)")
        # The demotion path holds a Kalshi contract to settlement: nothing was sold.
        self.assertEqual([o for o in self.real.submitted[submitted:] if o.side == "sell"], [])
        self.assertEqual({k: h.quantity for k, h in book.account(a.id).holdings.items()}, held)
        moves = self.house.allocator.board()["moves"]
        self.assertEqual([(m["from_band"], m["to_band"]) for m in moves if m["agent"] == a.id], [("paper", "probe"), ("probe", "paper")])

    def test_a_proven_familys_newcomer_is_still_a_bunt_and_its_bunts_stay(self):
        self.families["weather-favorites"] = canned("weather-favorites", proven=True, n=16, bound=0.0033)
        self.blocks("weather-favorites", *[-0.05] * 8)
        a = self.seated()
        self.assertEqual(self.house.books["kalshi"].account(a.id).staked, D("30"))
        with self.evidence_of({a.id: dict(READY, w_real=1.0)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        row = self.house.allocator.board()["agents"][a.id]
        self.assertEqual((row["band"], row["probe_gate"], row["family_forward"]["blocks"]), ("bunt", None, 8))
        self.assertIsNone(self.house.allocator.probe_gate(self.house.registry.get(a.id)))

    def drawdown(self, a):
        """Its stay drawdown sends the probe back to practice at once: a probe's demotion, for a reason of its own."""
        with self.evidence_of({a.id: dict(READY, e=0.9, w_real=0.64, real_drawdown=0.36)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        return self.demotions(a)[-1]

    def test_a_demoted_probes_family_seats_no_probe_until_its_record_since_turns(self):
        # Before the demotion: six positive blocks, which would have "turned" the record had they counted.
        self.blocks("weather-favorites", *[0.01] * 6)
        a = self.seated()
        self.drawdown(a)
        demoted_at = self.house.allocator.state["probe_holds"]["families"]["weather-favorites"][-1]["at"]
        b = self.agent("hawk")
        table = {a.id: dict(READY, e=0.9, w_real=0.64, real_drawdown=0.36), b.id: READY}
        self.blocks("weather-favorites", *[0.01] * 5)  # five positive blocks since: not yet
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(b.id), 1)
        status = self.status(b)
        self.assertEqual(status["stage"], "family_held")
        self.assertEqual(status["reason"], f"{a.id}, a probe of its family weather-favorites, went back to practice at {demoted_at}: "
                                           "no probe is seated from the family until its pooled forward record since then is "
                                           "positive over 6 active blocks (it is +0.0500 over 5; allocator.family_probe)")
        self.assertEqual((status["held_since"], status["family_forward"]), (demoted_at, {"blocks": 5, "growth": 0.05}))
        self.assertEqual(self.house.allocator.board()["agents"][b.id]["probe_gate"], f"held since {demoted_at}")
        self.blocks("weather-favorites", -0.05)  # six since, and they net to zero: still held (the whole record is +0.06)
        with self.evidence_of(table):
            self.tick()
        self.assertEqual((self.house.evaluator.rung(b.id), self.status(b)["stage"]), (1, "family_held"))
        self.blocks("weather-favorites", 0.02)  # seven since, +0.02: the record has turned
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(b.id), 2)
        self.assertEqual(self.house.books["kalshi"].account(b.id).staked, D("10"))

    def test_a_restart_keeps_the_hold_from_its_state_and_from_the_ledger_alone(self):
        a = self.seated()
        self.drawdown(a)
        b = self.agent("hawk")
        table = {a.id: dict(READY, e=0.9, w_real=0.64, real_drawdown=0.36), b.id: READY}
        path = self.house.allocator.path
        self.house.allocator = allocator.Allocator(self.house, path.parent)  # the House restarted: allocator.json read back
        self.assertIn("weather-favorites", self.house.allocator.state["probe_holds"]["families"])
        with self.evidence_of(table):
            self.tick()
        self.assertEqual((self.house.evaluator.rung(b.id), self.status(b)["stage"]), (1, "family_held"))
        path.unlink()  # a restart that lost allocator.json: the ledger's rows alone
        self.house.allocator = allocator.Allocator(self.house, path.parent)
        self.assertEqual(self.house.allocator.state["probe_holds"], {})
        with self.evidence_of(table):
            self.tick()
        self.assertEqual((self.house.evaluator.rung(b.id), self.status(b)["stage"]), (1, "family_held"))
        self.assertEqual(self.house.allocator.state["probe_holds"]["families"]["weather-favorites"][-1]["agent"], a.id)

    def test_a_demotion_that_names_no_band_holds_an_unproven_family_by_the_mechanism_ledger(self):
        """The House's drift demotion writes no `band_from`: the family's state in its last `family.record` row decides."""
        a = self.seated()
        self.clock.advance(301)
        with self.evidence_of({a.id: dict(READY, w_real=1.0)}):
            self.tick()  # the family's `family.record` row: unproven
        self.assertTrue([e for e in self.house.ledger.iter(kinds="family.record") if e.payload.get("family") == "weather-favorites"])

        def drifted(agent_id, book, horizon="hour"):
            return self.house.evaluator.demote(agent_id, "its growth has decayed from the record that earned this rung", {})
        with self.evidence_of({a.id: dict(READY, w_real=1.0)}), patch.object(self.house.evaluator, "drift", side_effect=drifted):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        self.assertNotIn("band_from", self.demotions(a)[-1])
        self.assertEqual(self.house.allocator.state["probe_holds"]["families"]["weather-favorites"][-1]["agent"], a.id)

    def test_a_stake_that_was_never_lent_holds_nothing(self):
        from league.book import Book, BookError

        a = self.agent()
        real, original = self.house.books["kalshi"], Book.stake

        def refuse(book, agent, usd, *, note=""):
            if book is real and float(usd) > 0:
                raise BookError("the venue's cash moved")
            return original(book, agent, usd, note=note)

        with patch.object(Book, "stake", refuse), self.evidence_of({a.id: READY}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        self.assertTrue(self.demotions(a)[-1]["unfunded"])
        self.assertNotIn("weather-favorites", self.house.allocator.state["probe_holds"].get("families", {}))
        self.clock.advance(3600)  # past its own re-entry cooldown
        with self.evidence_of({a.id: READY}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)

    def test_a_newcomer_never_displaces_a_probe_of_its_own_family(self):
        """Displacing its own family's probe would hold the family, and the newcomer with it, the moment it was made."""
        tight = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "10"})
        tight.start()
        self.addCleanup(tight.stop)
        a = self.seated(e=1.02, w_real=1.0)
        table = {a.id: dict(READY, e=1.02, w_real=1.0)}
        b = self.agent("hawk")
        table[b.id] = READY
        with self.evidence_of(table):
            self.tick()
        self.assertEqual((self.house.evaluator.rung(a.id), self.house.evaluator.rung(b.id)), (2, 1))
        self.assertEqual(self.status(b)["stage"], "envelope")
        # Another family's newcomer displaces it, and its family is held from then on.
        c = self.agent("huang", family="crypto-15m-favorites")
        table[c.id] = READY
        with self.evidence_of(table):
            self.tick()
        self.assertEqual((self.house.evaluator.rung(a.id), self.house.evaluator.rung(c.id)), (1, 2))
        self.assertEqual(self.house.allocator.state["probe_holds"]["families"]["weather-favorites"][-1]["agent"], a.id)

    def test_the_gate_reads_the_houses_own_forward_record(self):
        """`House.family_forward` is the definition; the allocator reads the same rows from its tape."""
        self.blocks("weather-favorites", -0.01, 0.02, -0.03, 0.0, -0.04, 0.01, -0.02)
        a = self.agent()
        with self.evidence_of({a.id: READY}):
            self.tick()
        self.house._data_cache.pop("family_forward", None)
        self.assertEqual(self.house.allocator.forward("weather-favorites"), self.house.family_forward()["weather-favorites"])
        self.assertIsNotNone(self.house._losing_family("weather-favorites"))  # the House breeds no more of it either


    def test_each_demotion_holds_until_the_record_since_it_turns(self):
        """Review of #276: two probes of one family demoted apart are two holds; the later one's turn does not release the
        earlier, whose record since includes the family's losses in between."""
        self.blocks("weather-favorites", *[0.05] * 6)  # +0.30 before: the whole record never loses in this test
        a, b = self.seated("kay"), self.seated("hawk")
        drawdown = dict(READY, e=0.9, w_real=0.64, real_drawdown=0.36)
        table = {a.id: drawdown, b.id: dict(READY, w_real=1.0)}
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        self.blocks("weather-favorites", *[-0.05] * 3)  # the family loses -0.15 while b trades on
        table[b.id] = drawdown
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(b.id), 1)
        self.blocks("weather-favorites", *[0.01] * 6)  # since b: +0.06 over 6, turned; since a: -0.09 over 9, not
        c = self.agent("huang")
        table[c.id] = READY
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(c.id), 1)
        status = self.status(c)
        self.assertEqual(status["stage"], "family_held")
        self.assertTrue(status["reason"].startswith(f"{a.id}, a probe of its family weather-favorites"), status["reason"])
        self.assertIn("(it is -0.0900 over 9;", status["reason"])
        self.assertEqual([d["agent"] for d in self.house.allocator.state["probe_holds"]["families"]["weather-favorites"]], [a.id])
        self.blocks("weather-favorites", 0.10)  # since a: +0.01 over 10: turned
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(c.id), 2)
        self.assertNotIn("weather-favorites", self.house.allocator.state["probe_holds"]["families"])

    def test_a_turn_is_for_good(self):
        """"Until the family's record turns" (review of #276): once the record since a demotion has turned, the hold is over,
        even if the record since then falls back; the whole record's losing line still stands guard."""
        self.blocks("weather-favorites", *[0.10] * 6)  # +0.60 before the demotion
        a = self.seated()
        self.drawdown(a)
        self.blocks("weather-favorites", *[0.01] * 6)  # turned
        b = self.agent("hawk")
        table = {a.id: dict(READY, e=0.9, w_real=0.64, real_drawdown=0.36)}
        with self.evidence_of(table):
            self.tick()
        self.assertNotIn("weather-favorites", self.house.allocator.state["probe_holds"]["families"])
        self.blocks("weather-favorites", -0.50)  # the record since the demotion is -0.44 now; the whole record +0.16
        table[b.id] = READY
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(b.id), 2)

    def test_a_family_whose_record_cannot_be_read_demotes_nobody(self):
        """Review of #276: an unreadable record counts a family's agents as probes for money; the losing line must not then
        send a proven family's bunt back to practice for a read that failed. No probe is seated from it either."""
        a = self.seated()
        self.blocks("weather-favorites", *[-0.05] * 6)
        b = self.agent("hawk")

        def unreadable(house, family, venue, **kw):
            if family == "weather-favorites":
                raise RuntimeError("the tape could not be read")
            return self._record(house, family, venue, **kw)

        self.records.stop()
        try:
            with patch.object(allocator, "family_record", side_effect=unreadable), \
                    self.evidence_of({a.id: dict(READY, w_real=1.0), b.id: READY}):
                self.tick()
        finally:
            self.records.start()
        self.assertEqual((self.house.evaluator.rung(a.id), self.house.evaluator.rung(b.id)), (2, 1))
        self.assertEqual(self.demotions(a), [])
        self.assertEqual(self.status(b)["stage"], "family_losing")

    def test_a_gate_that_cannot_be_read_seats_no_probe_and_demotes_nobody(self):
        a = self.seated()
        self.blocks("weather-favorites", *[-0.05] * 6)
        b = self.agent("hawk", family="kalshi-favorites")
        table = {a.id: dict(READY, w_real=1.0), b.id: READY}
        with patch.object(allocator, "fold_demotions", side_effect=OSError("disk I/O error")), self.evidence_of(table):
            self.tick()
        self.assertEqual((self.house.evaluator.rung(a.id), self.house.evaluator.rung(b.id)), (2, 1))
        self.assertEqual(self.status(b)["stage"], "family_unreadable")
        self.assertEqual(self.house.allocator.board()["agents"][b.id]["probe_gate"], "unreadable")
        with self.evidence_of(table):
            self.tick()  # read again: the losing family's probe goes back, the other family's newcomer is seated
        self.assertEqual((self.house.evaluator.rung(a.id), self.house.evaluator.rung(b.id)), (1, 2))

    def test_an_audit_that_approves_a_seat_meets_the_gate_again(self):
        """Review of #276: a known defect is audited off the tick before its seat, and its family may turn losing meanwhile.
        `House._commit_promotion` asks the gate again (`Allocator.refuses_probe`)."""
        from league.evaluator import Verdict

        a = self.agent()
        with self.evidence_of({a.id: dict(READY, e=1.0)}):
            self.tick()  # below the bunt line: nothing to gate yet
        self.blocks("weather-favorites", *[-0.05] * 6)
        verdict = Verdict(a.id, 1, "eligible", "a known defect's seat, approved by its audit", {"via": "allocator", "book": "kalshi-shadow"})
        self.house._commit_promotion(a.id, verdict, 1, self.house._generation(a.id))
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        self.assertEqual(self.status(a)["stage"], "family_losing")
        self.assertIn("-0.3000 over 6 active blocks", self.status(a)["reason"])


class ProbeGateOnAlpaca(ForwardBlocks, HouseCaseReal):
    """On Alpaca the demotion path sells what the account holds: a probe on a losing family goes back only once flat."""

    def seated(self):
        a = self.agent("haghani", code=IDLE)
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        return a

    def losing(self):
        self.blocks("alloc-test", *[-0.01] * 6, book="alpaca-paper", code=IDLE)

    def test_a_probe_holding_a_position_keeps_its_seat_until_it_is_flat_and_nothing_is_sold(self):
        from league.book import Intent
        from league.venues import instrument_for

        a = self.seated()
        book = self.house.books["alpaca"]
        btc = instrument_for("alpaca", {"symbol": "BTC/USD"})
        buy = Intent.new(agent=a.id, instrument=btc, side="buy", quantity=D("0.000125"), reason="test", created_at=now_iso(self.clock))
        self.assertEqual(book.submit([buy])[0].status, "filled")
        held = {k: h.quantity for k, h in book.account(a.id).holdings.items()}
        self.assertTrue(held)
        self.losing()
        # W_real 1.2: its target rises to $30 (a bunt keeps what it makes), but a probe on a losing family waiting to go
        # back is lent nothing more (review of #276).
        table = {a.id: dict(e=1.10, w_paper=1.21, w_real=1.2, paper_trades=6)}
        submitted = len(self.real.submitted)
        with self.evidence_of(table):
            self.tick(2)
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        self.assertEqual([o for o in self.real.submitted[submitted:] if o.side == "sell"], [])
        self.assertEqual({k: h.quantity for k, h in book.account(a.id).holdings.items()}, held)
        self.assertEqual(book.account(a.id).staked, D("25"))
        self.assertEqual(self.house.allocator.board()["agents"][a.id]["probe_gate"], "losing")
        told = [e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert") if a.id in str(e.payload.get("text"))
                and "once the demotion would sell nothing (now: holding)" in str(e.payload.get("text"))]
        self.assertEqual(len(told), 1)  # told once, not at every pass
        # Its own exit: flat, it goes back to practice at the next pass.
        sell = Intent.new(agent=a.id, instrument=btc, side="sell", quantity=held[btc.key], reason="its own exit", created_at=now_iso(self.clock))
        self.assertEqual(book.submit([sell])[0].status, "filled")
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        self.assertEqual(self.demotions(a)[-1]["rule"], "allocator.family_probe")

    def test_a_probe_holding_only_dust_goes_back_and_its_dust_is_booked_not_sold(self):
        """What the demotion path would not sell -- a holding under a cent, as the wind-down books it -- does not keep a
        probe on a losing family seated (haghani-h426990's 0.000000001 LINK/USD sat on a book for a day)."""
        from league.venues import instrument_for

        a = self.seated()
        book = self.house.books["alpaca"]
        btc = instrument_for("alpaca", {"symbol": "BTC/USD"})
        with book._lock:
            entry = self.house.ledger.append("book.fill", {
                "book": "alpaca", "source": "venue", "instrument": btc.to_dict(), "side": "buy", "quantity": "0.00000001",
                "price": "80002", "fee_usd": "0", "cash_delta": "-0.00080002", "position_delta": "0.00000001", "real_money": True},
                agent=a.id)
            book._apply(entry.kind, a.id, entry.payload, entry.at)
        self.real.held[btc.key] = (btc, D("0.00000001"))
        self.assertTrue(book.account(a.id).holdings)
        self.losing()
        submitted = len(self.real.submitted)
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, w_real=1.0, paper_trades=6)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        self.assertEqual([o for o in self.real.submitted[submitted:] if o.side == "sell"], [])
        self.assertEqual(book.account(a.id).holdings, {})  # booked as dust by the wind-down

    def resting_bid(self, a):
        from league.book import Intent
        from league.venues import instrument_for

        book = self.house.books["alpaca"]
        btc = instrument_for("alpaca", {"symbol": "BTC/USD"})
        bid = Intent.new(agent=a.id, instrument=btc, side="buy", quantity=D("0.000125"), order_type="limit", limit_price=D("79000"),
                         reason="test", created_at=now_iso(self.clock))
        outcome = book.submit([bid])[0]
        self.assertTrue(book.open_orders(a.id))
        return book, btc, outcome.order_id

    def test_a_probe_resting_only_a_bid_has_it_cancelled_and_goes_back_in_one_pass(self):
        """The demotion path's own first step, cancelling working buys, sells nothing (review of #276: haghani-r42c38c
        only rested bids, re-posted every wake, and would never have been flat between them)."""
        a = self.seated()
        book, _, order_id = self.resting_bid(a)
        self.losing()
        submitted = len(self.real.submitted)
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, w_real=1.0, paper_trades=6)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        self.assertIn(order_id, self.real.cancelled)
        self.assertEqual([o for o in self.real.submitted[submitted:] if o.side == "sell"], [])
        self.assertEqual(book.account(a.id).holdings, {})

    def test_a_bid_that_fills_as_it_is_cancelled_is_a_position_and_the_probe_waits(self):
        """A fill racing the cancel is booked by the cancel's own read: the probe now holds a position, and waits for its own
        exit rather than have it sold."""
        a = self.seated()
        book, btc, order_id = self.resting_bid(a)
        self.losing()
        real, cancel = self.real, self.real.cancel

        def filled_first(reference):  # the venue fills the bid a moment before it takes the cancel
            order = real.get_order(reference)
            if not order.terminal:
                real.fill_resting(next(key for key, o in real.orders.items() if o is order), "0.000125")
            return cancel(reference)

        submitted = len(self.real.submitted)
        with patch.object(self.real, "cancel", side_effect=filled_first), \
                self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, w_real=1.0, paper_trades=6)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        self.assertGreater(book.account(a.id).holdings[btc.key].quantity, 0)  # the fill, less the venue's fee in the coin
        self.assertEqual([o for o in self.real.submitted[submitted:] if o.side == "sell"], [])

    def test_a_buy_the_book_still_asks_the_venue_about_keeps_the_probe_seated(self):
        """A buy closed as never arrived may be revived with its fill for a quarter of an hour (`Book._reserved_cash`): its
        fill after a demotion would be sold by the wind-down's retry (review of #276)."""
        a = self.seated()
        self.losing()
        book = self.house.books["alpaca"]
        with patch.object(type(book), "_reserved_cash", return_value=D("10")), \
                self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, w_real=1.0, paper_trades=6)}):
            self.tick()
            self.assertEqual(self.house.allocator._unflat(self.house.registry.get(a.id)), "reserved")
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, w_real=1.0, paper_trades=6)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)


class ProbeGateOnOptions(ForwardBlocks, HouseCaseReal):
    """An options probe (the coordinator's case, Sept 24, 2026): krasker-14 (alpaca-options, family options-pullback) was
    seated at 16:47:37Z as an $80 real-money probe (`option_bunt_usd`: a probe cannot hold a smaller contract than a bunt)
    while its family's forward record read 19 practice blocks and -0.3829 (16:53:40Z; bound -0.1088 on n 28): losing by
    `families.losing(19, -0.3829, 6)`. The demotion path sells a long option at the bid, and outside the session holds the
    sale for the open (`House._wind_down`): an options probe on a losing family goes back only once flat."""

    def setUp(self):
        super().setUp()
        room = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "500"})
        room.start()
        self.addCleanup(room.stop)
        self.clock.now = 1789048800.0  # Thursday Sept 10, 14:00Z: the options session is open
        self.quote()
        self.option = instrument_for("alpaca", {"occ": "F261009C00013000"})
        self.real.set_quote(self.option, "0.30", "0.32")

    def options_agent(self):
        agent = self.house.spawn("krasker", "options-pullback", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        self.house.evaluator.seat(agent.id, 1, "test: straight to practice")
        self.house._state["tried"][agent.id] = agent.code_sha256
        self.house._state["next_wake"][agent.id] = self.clock() + 10 ** 9  # it never wakes: the test places its orders
        return agent

    def losing_like_krasker_14(self):
        self.blocks("options-pullback", *([-0.02] * 18 + [-0.0229]), book="alpaca-paper", code=IDLE)  # 19 blocks, -0.3829

    def test_an_options_probe_from_a_losing_family_is_refused(self):
        self.losing_like_krasker_14()
        a = self.options_agent()
        self.assertEqual(self.house.allocator.target_stake(a, "bunt"), D("80"))  # what it would have been lent
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        self.assertEqual(self.status(a)["stage"], "family_losing")
        self.assertIn("its family options-pullback's pooled forward record is -0.3829 over 19 active blocks", self.status(a)["reason"])
        self.assertNotIn(a.id, self.house.books["alpaca"].accounts)

    def test_a_seated_options_probe_holding_a_contract_goes_back_only_once_flat(self):
        from league.book import Intent

        a = self.options_agent()
        table = {a.id: dict(e=1.10, w_paper=1.21, w_real=1.0, paper_trades=6)}
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        book = self.house.books["alpaca"]
        self.assertEqual(book.account(a.id).staked, D("80"))
        buy = Intent.new(agent=a.id, instrument=self.option, side="buy", quantity="1", order_type="limit", limit_price="0.32",
                         reason="test", created_at=now_iso(self.clock), nonce="call")
        self.assertEqual(book.submit([buy])[0].status, "filled")
        self.losing_like_krasker_14()
        submitted = len(self.real.submitted)
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        self.assertIn(self.option.key, book.account(a.id).holdings)
        self.assertEqual(self.house.allocator.board()["agents"][a.id]["probe_gate"], "losing")
        # After the bell the demotion path would hold the sale for the open: still nothing is planned or sold.
        self.clock.now = 1789048800.0 + 8 * 3600  # 22:00Z
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        self.assertNotIn(a.id, self.house._state.get("wind_down_held") or {})
        self.assertEqual([o for o in self.real.submitted[submitted:] if o.side == "sell"], [])
        # Its own exit the next session: flat, it goes back to practice at the next pass.
        self.clock.now = 1789048800.0 + 86400  # Friday 14:00Z
        self.quote()
        self.real.set_quote(self.option, "0.30", "0.32")
        sell = Intent.new(agent=a.id, instrument=self.option, side="sell", quantity="1", order_type="limit", limit_price="0.30",
                          reason="its own exit", created_at=now_iso(self.clock), nonce="exit")
        self.assertEqual(book.submit([sell])[0].status, "filled")
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        demote = self.demotions(a)[-1]
        self.assertEqual((demote["band_from"], demote["rule"]), ("probe", "allocator.family_probe"))
        # 20 blocks by then: its own real day (the contract bought at 0.32, sold at 0.30) counts in its family's record too.
        self.assertEqual(demote["family_forward"]["blocks"], 20)
        self.assertLess(demote["family_forward"]["growth"], -0.3829)
        self.assertEqual(len([o for o in self.real.submitted[submitted:] if o.side == "sell"]), 1)  # its own, and only it


class TheBoard(ForwardBlocks, KalshiHouse):
    """R3: the board's real rows carry equity beside the net loan, and each family its clock to the swing."""

    def test_a_real_row_carries_its_equity_beside_its_net_loan(self):
        a = self.agent()
        with self.evidence_of({a.id: READY}):
            self.tick()
        b = self.agent("hawk")
        with self.evidence_of({a.id: dict(READY, w_real=1.0), b.id: dict(READY, e=1.0)}):
            self.tick()
        rows = self.house.allocator.board()["agents"]
        book = self.house.books["kalshi"]
        self.assertEqual(rows[a.id]["equity_usd"], book.equity(a.id).quantize(D("0.01")))
        self.assertEqual(rows[a.id]["stake_usd"], book.account(a.id).staked)
        self.assertIsNone(rows[b.id]["equity_usd"])  # practice: no real account
        self.assertEqual(rows[b.id]["family_forward"], {"blocks": 0, "growth": 0.0})

    def test_each_family_carries_its_clock_to_the_swing(self):
        self.families["weather-favorites"] = real_record(n=5, bound=-0.5)  # proven on the pooled record, 5 real events
        a = self.agent()
        with self.evidence_of({a.id: READY}):
            self.tick()
        self.assertEqual(self.house.books["kalshi"].account(a.id).staked, D("30"))
        self.clock.advance(86400 - 300)
        with self.evidence_of({a.id: dict(READY, w_real=1.0)}):
            self.tick()  # a day after its first real dollar
        clock = self.house.allocator.board()["families"]["kalshi"]["weather-favorites"]["swing_clock"]
        self.assertEqual((clock["real_n"], clock["real_days"], clock["real_per_day"]), (5, 1.0, 5.0))
        released = self.house.allocator._swing_released()
        self.assertEqual(clock["needs"], {"real_settlements": 10, "look_at": 15, "confidence": 0.9, "proof": False, "audit": True,
                                          "grant": not released})
        self.assertEqual(clock["days_to_swing"], 2.0)
        # The clock rides the board, never a `family.record` row (it moves with the clock alone).
        self.assertFalse([e for e in self.house.ledger.iter(kinds="family.record") if "swing_clock" in e.payload])

    def test_the_clock_where_no_estimate_stands(self):
        """Review of #276: no real dollar yet, a real life under an hour (a rate over minutes is noise), no member on real
        money (the real record does not grow), or only the pooled proof left: no days to swing. A passed look waits for the
        audit alone."""
        rule, day = families.swing_rule(), 86400.0
        self.assertIsNone(families.swing_clock(real_record(n=0, bound=-0.5), rule, first_real=None, now=1000.0)["days_to_swing"])
        record = real_record(n=5, bound=-0.5)
        record["members_real"] = 1
        self.assertEqual(families.swing_clock(record, rule, first_real=0.0, now=3 * day)["days_to_swing"], 6.0)  # 10 at 5/3 a day
        early = families.swing_clock(record, rule, first_real=0.0, now=1800.0)
        self.assertEqual((early["real_per_day"], early["days_to_swing"]), (None, None))
        record["members_real"] = 0
        self.assertIsNone(families.swing_clock(record, rule, first_real=0.0, now=3 * day)["days_to_swing"])
        passed = real_record(n=15, bound=0.05)  # its entry look at 15 passed: the audit is what is left
        clock = families.swing_clock(passed, rule, first_real=0.0, now=3 * day, released=True)
        self.assertEqual((clock["needs"]["real_settlements"], clock["days_to_swing"], clock["real_per_day"]), (0, 0.0, 5.0))
        self.assertFalse(clock["needs"]["grant"])
        unproven = real_record(n=15, bound=0.05, proven=False)  # a passed look without the pooled proof
        clock = families.swing_clock(unproven, rule, first_real=0.0, now=3 * day, released=False)
        self.assertEqual((clock["needs"]["proof"], clock["needs"]["grant"], clock["days_to_swing"]), (True, True, None))
        self.assertIsNone(families.swing_clock(passed, None, first_real=0.0, now=1.0))

    def test_the_sites_checkpoint_carries_none_of_the_new_fields(self):
        """The site's validators refuse unknown fields: the publisher copies the board's fields by name. The board here has
        every new field: a losing family's newcomer, a held family's newcomer, a real row's equity, each family's clock."""
        from league.publish import Publisher

        self.blocks("weather-favorites", *[-0.01] * 6)
        a, b, c = self.agent(), self.agent("hawk", family="kalshi-favorites"), self.agent("mullins", family="sports-favorites")
        table = {a.id: READY, b.id: READY, c.id: READY}
        with self.evidence_of(table):
            self.tick()
        table[c.id] = dict(READY, e=0.9, w_real=0.64, real_drawdown=0.36)  # back to practice: sports-favorites is held
        d = self.agent("meriwether", family="sports-favorites")
        table[d.id] = READY
        with self.evidence_of(table):
            self.tick()
        board = self.house.allocator.board()
        self.assertEqual(board["agents"][a.id]["probe_gate"], "losing")
        self.assertTrue(str(board["agents"][d.id]["probe_gate"]).startswith("held since "))
        self.assertIsNotNone(board["agents"][b.id]["equity_usd"])
        self.assertIn("swing_clock", board["families"]["kalshi"]["kalshi-favorites"])
        self.clock.advance(5)
        publisher = Publisher("https://blakewoods.us", lambda: "t" * 40, self.house.allocator.path.parent / "publish.json",
                              tape="test", opener=lambda *a, **k: None, clock=self.clock)
        body = json.dumps(publisher.checkpoint(self.house), default=str)
        for field in ("probe_gate", "family_forward", "equity_usd", "swing_clock", "held since", "losing"):
            self.assertNotIn(field, body)


class RulesText(unittest.TestCase):
    def text(self, constitution=None):
        from league.rules import rules_text

        with open("league/game.json") as f:
            return " ".join(rules_text(json.load(f), constitution).split())

    def test_the_agents_are_told_the_gate(self):
        import copy

        text = self.text()
        self.assertIn("NO PROBE ON A LOSING FAMILY. When your family's forward record -- the active blocks of every member ever born, "
                      "living or dead, summed -- is at or below zero after 6 active blocks, no probe is seated from it", text)
        self.assertIn("A probe that goes back to practice for ANY reason holds its family: no probe from it is seated until the "
                      "family's record SINCE then is positive over 6 active blocks (each such demotion, until its own turn).", text)
        self.assertIn("at Alpaca once it holds nothing that demotion would sell: its bids are cancelled, and nothing is sold for it", text)
        start, end = text.index("- YOUR FAMILY'S RECORD"), text.index("- REAL MONEY AT KALSHI")
        self.assertNotIn("paper", text[start:end].lower())  # the copy rule: practice, never paper
        c = copy.deepcopy(CONSTITUTION)
        c["allocator"]["family_probe"]["reseat"] = "any"
        self.assertNotIn("holds its family", self.text(c))
        del c["allocator"]["family_probe"]
        self.assertNotIn("NO PROBE ON A LOSING FAMILY", self.text(c))


if __name__ == "__main__":
    unittest.main()
