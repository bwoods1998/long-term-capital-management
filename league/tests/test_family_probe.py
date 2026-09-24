"""No probe on a losing family (R5 of the close-the-gaps run, Sept 24, 2026; `allocator.family_probe`).

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
from league.tests.test_allocator import IDLE, HouseCaseReal
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
        self.assertEqual((holds["fam-a"]["seq"], holds["fam-a"]["agent"], holds["fam-a"]["why"]), (1, "a", "drawdown"))
        self.assertEqual(holds["fam-d"]["at"], "2026-09-24T13:06:00.000Z")
        self.assertEqual(states, {"fam-d@kalshi": "unproven", "fam-e@kalshi": "proven"})
        # The latest demotion is the one that holds; folding in two parts is folding once.
        later = [SimpleNamespace(seq=50, kind="eval.verdict", agent="a", at="2026-09-24T14:00:00.000Z",
                                 payload={"decision": "demote", "from_rung": 2, "to_rung": 1, "band_from": "probe", "reason": "again"})]
        self.assertEqual(allocator.fold_demotions(later, holds, states, family_of), 50)
        self.assertEqual(holds["fam-a"]["seq"], 50)
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
        demoted_at = self.house.allocator.state["probe_holds"]["families"]["weather-favorites"]["at"]
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
        self.assertEqual(self.house.allocator.state["probe_holds"]["families"]["weather-favorites"]["agent"], a.id)

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
        self.assertEqual(self.house.allocator.state["probe_holds"]["families"]["weather-favorites"]["agent"], a.id)

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
        self.assertEqual(self.house.allocator.state["probe_holds"]["families"]["weather-favorites"]["agent"], a.id)

    def test_the_gate_reads_the_houses_own_forward_record(self):
        """`House.family_forward` is the definition; the allocator reads the same rows from its tape."""
        self.blocks("weather-favorites", -0.01, 0.02, -0.03, 0.0, -0.04, 0.01, -0.02)
        a = self.agent()
        with self.evidence_of({a.id: READY}):
            self.tick()
        self.house._data_cache.pop("family_forward", None)
        self.assertEqual(self.house.allocator.forward("weather-favorites"), self.house.family_forward()["weather-favorites"])
        self.assertIsNotNone(self.house._losing_family("weather-favorites"))  # the House breeds no more of it either


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
        table = {a.id: dict(e=1.10, w_paper=1.21, w_real=1.0, paper_trades=6)}
        submitted = len(self.real.submitted)
        with self.evidence_of(table):
            self.tick(2)
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        self.assertEqual([o for o in self.real.submitted[submitted:] if o.side == "sell"], [])
        self.assertEqual({k: h.quantity for k, h in book.account(a.id).holdings.items()}, held)
        self.assertEqual(self.house.allocator.board()["agents"][a.id]["probe_gate"], "losing")
        told = [e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert") if a.id in str(e.payload.get("text"))
                and "once it holds nothing" in str(e.payload.get("text"))]
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

    def test_a_probe_with_a_working_order_waits_for_it(self):
        from league.book import Intent
        from league.venues import instrument_for

        a = self.seated()
        book = self.house.books["alpaca"]
        btc = instrument_for("alpaca", {"symbol": "BTC/USD"})
        bid = Intent.new(agent=a.id, instrument=btc, side="buy", quantity=D("0.000125"), order_type="limit", limit_price=D("79000"),
                         reason="test", created_at=now_iso(self.clock))
        outcome = book.submit([bid])[0]
        self.assertTrue(book.open_orders(a.id))
        self.losing()
        table = {a.id: dict(e=1.10, w_paper=1.21, w_real=1.0, paper_trades=6)}
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        self.assertTrue(book.open_orders(a.id))  # the allocator cancels nothing of its own accord
        book.cancel(a.id, outcome.order_id)
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)


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
                      "family's record SINCE then is positive over 6 active blocks.", text)
        start, end = text.index("- YOUR FAMILY'S RECORD"), text.index("- REAL MONEY AT KALSHI")
        self.assertNotIn("paper", text[start:end].lower())  # the copy rule: practice, never paper
        c = copy.deepcopy(CONSTITUTION)
        c["allocator"]["family_probe"]["reseat"] = "any"
        self.assertNotIn("holds its family", self.text(c))
        del c["allocator"]["family_probe"]
        self.assertNotIn("NO PROBE ON A LOSING FAMILY", self.text(c))


if __name__ == "__main__":
    unittest.main()
