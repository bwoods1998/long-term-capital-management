"""The seat market follows evidence (Sept 23, 2026, the learn-and-unblock run, workstream S1).

Measured at 16:28Z on the 16:28Z ledger snapshot: 441 agents born since Sept 19, 345 died, 312 of
them (90%) displaced and 9 on evidence. The House's own parameter mutations were 74% of births and
88% of displacements, staked every two minutes and displaced at rung 0 after a median three hours,
before ever passing replay; meanwhile 20 lab graduates (replay and sealed holdout passed), 6
replay-passed foundry cards and 6 merged strategies waited for seats, and `enroll()` broke silently
when nobody could be displaced. So: waiters take every freed seat first, an evidenced newcomer
outranks a resident that has never traded, no mutation is staked while anyone waits, a losing family
is not bred again, every desk keeps a seat for a member that trades, and the seat market is in
health.json with an alert when it stalls."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from league.ledger import now_iso
from league.tests.test_house import BUYER, HouseCase
from league.tests.test_hypotheses import PASSER, FoundryCase
from league.tests.test_lab import DESK, KNOB, LabCase

SPY = BUYER.replace('"BTC/USD"', '"SPY"')


def alerts(house, level, *words):
    return [e.payload["text"] for e in house.ledger.iter(kinds="ops.alert")
            if e.payload.get("level") == level and all(w in e.payload.get("text", "") for w in words)]


class SeatCase(HouseCase):
    def setUp(self):
        super().setUp()
        self.rules = self.house.game["economy"]
        self.grace = float(self.rules["epoch_seconds"]) * float(self.rules["displace_after_epochs"])

    def fill(self, agent):
        self.house.ledger.append("book.fill", {"book": "alpaca-paper", "symbol": "BTC/USD", "side": "buy",
                                               "quantity": "0.001", "price": "60000", "source": "venue"}, agent=agent.id)

    def blocks(self, agent, growth, n):
        for i in range(n):
            self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": growth, "active": True,
                                                    "book": "alpaca-paper", "block": f"b{i}"}, agent=agent.id)


class GraduatesFirst(LabCase):
    """A waiting graduate holds every mutation, and its desk's next seat is its own."""

    def setUp(self):
        super().setUp()
        self.rules = self.house.game["economy"]
        self.grace = float(self.rules["epoch_seconds"]) * float(self.rules["displace_after_epochs"])

    def evolve(self, *codes):
        """As test_lab's graduation tests: queue Luna children and evaluate them into the archive."""
        ids = [self.queue(code, origin="luna") for code in codes]
        self.lab.evaluate_batch()
        self.forward_wins()  # F1 (Sept 25, 2026): a winning forward window of its own before the House's replay
        return ids

    def test_no_house_mutation_is_staked_while_a_graduate_waits(self):
        self.evolve(KNOB)
        self.niche.max_members = 1
        resident = self.seated("resident")  # rung 1 on the graduate's desk, never traded
        with patch.object(self.house, "_weakest", return_value=None):
            self.assertEqual(self.lab.graduate()[0]["state"], "waiting_seat")
        self.rules.update(newcomer_seconds=600, max_population=1)
        self.clock.advance(self.grace + 601)
        self.assertEqual(self.house._weakest(self.rules).id, resident.id, "the tournament alone would give a mutation this seat")
        self.assertIsNone(self.house._refill(self.rules))
        self.assertEqual([a.id for a in self.house.registry.living()], [resident.id])
        self.assertEqual([w["niche"] for w in self.house.seat_waiters()["graduates"]], [DESK])
        self.assertEqual(self.lab.graduate()[0]["state"], "born")  # the lab's next step takes the seat instead
        self.assertFalse(self.house.registry.get(resident.id).alive)

    def test_a_graduate_nobody_can_make_room_for_is_told_once_an_hour(self):
        self.evolve(KNOB)
        self.niche.max_members = 1
        resident = self.seated("resident")
        self.house.evaluator.promote(resident.id, 2, "test: real money")
        self.assertEqual(self.lab.graduate()[0]["state"], "waiting_seat")
        self.rules.update(newcomer_seconds=600, max_population=1)
        self.clock.advance(601)
        self.assertIsNone(self.house._refill(self.rules))
        self.assertEqual(len(alerts(self.house, "warning", "1 Alpha Lab graduate")), 1)
        self.assertIsNone(self.house._refill(self.rules))
        self.assertEqual(len(alerts(self.house, "warning", "1 Alpha Lab graduate")), 1)
        self.clock.advance(3601)
        self.assertIsNone(self.house._refill(self.rules))
        self.assertEqual(len(alerts(self.house, "warning", "1 Alpha Lab graduate")), 2)
        self.assertEqual(self.house._state["seat_refusals"]["graduates"]["count"], 1)


class CardsFirst(FoundryCase):
    def test_a_replay_passed_card_takes_a_replay_only_seat_inside_its_grace(self):
        """Before: the desk was full of young rung-0 mutations and the card waited for their grace."""
        self.call()  # the sawtooth card passes replay on the crypto majors desk
        young = [self.house.spawn("rosenfeld", "crypto-family", PASSER, reason="a House mutation")
                 for _ in range(self.house.niches[self.DESK].max_members)]
        self.rules.update(newcomer_seconds=600, max_population=40)
        self.clock.advance(601)
        child = self.house._refill(self.rules)
        card = self.card_of("sawtooth")
        self.assertIsNotNone(child)
        self.assertEqual(child.founder, f"card:{card['id']}")
        self.assertEqual(sum(1 for a in young if self.house.registry.get(a.id).alive), len(young) - 1)
        self.assertEqual(self.foundry.inventory(), [])

    def test_a_card_never_overfills_a_full_league_whose_seats_are_all_earned(self):
        self.call()
        resident = self.seated("resident")
        self.house.evaluator.promote(resident.id, 2, "test: real money")
        self.rules.update(newcomer_seconds=600, max_population=1)
        self.clock.advance(601)
        self.assertIsNone(self.house._refill(self.rules))
        self.assertEqual([a.id for a in self.house.registry.living()], [resident.id])
        self.assertEqual(len(self.foundry.inventory()), 1)
        self.assertEqual(self.house._state["seat_refusals"]["cards"]["count"], 1)


class EvidencedNewcomers(SeatCase):
    def test_replay_only_code_and_never_traded_seats_make_way_inside_their_grace(self):
        young = self.house.spawn("young", "test-family", BUYER, reason="a House mutation")  # rung 0
        idle = self.seated("idle")  # rung 1, never traded
        self.clock.advance(600)
        self.assertIsNone(self.house._weakest(self.rules))
        self.assertEqual(self.house._weakest(self.rules, evidenced=True).id, young.id)
        self.house.kill(young, "displaced", "test")
        self.clock.advance(float(self.house.settings.desk_displacement_seconds) + 1)  # one displacement a desk a minute
        # Sept 24, 2026: a never-traded paper seat first has its fair chance (an hour on a desk with no clock) --
        # after Deploy B evidenced waiters took each other's seats 33 s to 14 min after birth.
        self.assertIsNone(self.house._weakest(self.rules, evidenced=True), "inside its fair chance")
        self.clock.advance(3600)  # past it, still inside the plain grace
        self.assertEqual(self.house._weakest(self.rules, evidenced=True).id, idle.id)

    def test_real_money_winners_traders_short_of_their_record_and_unopened_stock_desks_are_never_taken(self):
        real = self.seated("real")
        self.house.evaluator.promote(real.id, 2, "test: real money")
        winner = self.seated("winner")
        self.blocks(winner, 0.003, 1)
        trader = self.seated("trader")
        self.fill(trader)  # trading, and short of the bunt line's closed trades and its sessions
        self.seated("stocks", SPY)  # keeps hours and has not yet been offered a session
        self.clock.advance(self.grace + 1)
        self.assertIsNone(self.house._weakest(self.rules, evidenced=True))

    def test_a_stock_desk_seat_is_taken_only_after_its_first_session_has_closed(self):
        """The case the grace was written for (#190): a newborn daily agent before its first session."""
        from league.tests.test_stock_desk_seats import FIRST_WAKE, ts

        self.clock.now = ts("2026-09-22T22:00:00Z")
        agent = self.seated("stocks", SPY)
        self.clock.now = ts(FIRST_WAKE)
        self.house.ledger.append("agent.woke", {"ok": True, "offered": 1}, agent=agent.id)
        self.clock.now = ts("2026-09-23T19:59:00Z")
        self.assertIsNone(self.house._weakest(self.rules, evidenced=True))
        self.clock.now = ts("2026-09-23T20:00:01Z")  # Wednesday's session closed: 6.5 session hours, inside the grace
        self.assertIsNone(self.house._weakest(self.rules))
        self.assertEqual(self.house._weakest(self.rules, evidenced=True).id, agent.id)

    def test_one_displacement_a_desk_a_tick(self):
        first, second = self.seated("first"), self.seated("second")
        self.clock.advance(self.grace + 1)
        loser = self.house._weakest(self.rules)
        self.house.kill(loser, "displaced", "test")
        self.assertIsNone(self.house._weakest(self.rules))
        self.clock.advance(float(self.house.settings.desk_displacement_seconds) + 1)
        self.assertEqual(self.house._weakest(self.rules).id, (second if loser.id == first.id else first).id)


class MergedStrategies(SeatCase):
    def strategies(self, rows):
        patcher = patch("league.strategies.all_strategies", return_value=rows)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_merged_strategy_takes_a_never_traded_seat_inside_the_grace(self):
        resident = self.seated("resident")
        self.rules["max_population"] = 1
        self.clock.advance(3601)  # past the seat's fair chance (an hour with no desk clock), inside the plain grace
        self.strategies([{"name": "btc-gap-fade", "family": "gap-fade", "why": "a test strategy", "code": BUYER}])
        born = self.house.enroll()
        self.assertEqual([a.founder for a in born], ["btc-gap-fade"])
        self.assertFalse(self.house.registry.get(resident.id).alive)

    def test_a_merged_strategy_nobody_can_make_room_for_is_recorded_and_told_once_an_hour(self):
        resident = self.seated("resident")
        self.house.evaluator.promote(resident.id, 2, "test: real money")
        self.rules["max_population"] = 1
        self.strategies([{"name": "btc-gap-fade", "family": "gap-fade", "why": "a test strategy", "code": BUYER}])
        self.assertEqual(self.house.enroll(), [])
        self.assertEqual(len(alerts(self.house, "warning", "1 merged strateg")), 1)
        self.assertEqual(self.house.enroll(), [])
        self.assertEqual(len(alerts(self.house, "warning", "1 merged strateg")), 1)
        self.clock.advance(3601)
        self.assertEqual(self.house.enroll(), [])
        self.assertEqual(len(alerts(self.house, "warning", "1 merged strateg")), 2)
        self.assertEqual(self.house._state["seat_refusals"]["strategies"]["count"], 1)
        self.assertTrue(self.house.registry.get(resident.id).alive)


class LosingFamilies(SeatCase):
    def test_a_family_losing_forward_after_six_blocks_is_not_bred_again_unless_the_code_changes(self):
        self.rules.update(newcomer_seconds=600, max_population=5)
        parent = self.seated("parent")
        self.blocks(parent, -0.01, 6)
        self.clock.advance(601)
        self.assertIsNone(self.house._refill(self.rules))
        self.assertEqual(len(alerts(self.house, "info", "test-family", "pooled")), 1)
        self.house.economy.grant(parent.id, "100", "test: a rich parent")
        self.assertIsNone(self.house.fork(parent), "a parameter copy runs the same mechanism")
        self.clock.advance(601)
        self.assertIsNone(self.house._refill(self.rules))
        self.assertEqual(len(alerts(self.house, "info", "test-family", "pooled")), 1, "told once an hour")
        child = self.house.fork(parent, code=BUYER + "\n# a different mechanism\n", reason="a research candidate")
        self.assertIsNotNone(child)

    def test_five_blocks_still_breed(self):
        self.rules.update(newcomer_seconds=600, max_population=5)
        parent = self.seated("parent")
        self.blocks(parent, -0.01, 5)
        self.clock.advance(601)
        self.assertEqual(self.house._refill(self.rules).parent, parent.id)

    def test_a_positive_pooled_record_breeds(self):
        self.rules.update(newcomer_seconds=600, max_population=5)
        parent = self.seated("parent")
        self.blocks(parent, 0.002, 6)
        self.clock.advance(601)
        self.assertEqual(self.house._refill(self.rules).parent, parent.id)

    def test_the_pooled_record_includes_dead_members_and_a_revival_is_refused_too(self):
        from league.constitution import CONSTITUTION

        dead = self.seated("dead")
        self.blocks(dead, -0.01, 6)
        self.house.kill(dead, "evidence", "a test death")
        self.assertIsNotNone(self.house._losing_family("test-family"))
        self.assertLess(CONSTITUTION["ladder"]["replay"]["min_oos_growth"], -0.0003)
        miss = self.house.spawn("miss", "test-family", BUYER, reason="a test agent")
        self.house.ledger.append("eval.trial", {"family": "test-family", "passed": False, "reasons": ["out-of-sample growth is not above zero"],
                                                "oos_mean_log_growth": -0.0003, "code_sha256": miss.code_sha256}, agent=miss.id)
        self.house.kill(miss, "never qualified", "a test death")
        self.house._state["replay_rules"] = "an-older-gate"
        self.house._replay_rules_changed()
        self.assertEqual([a for a in self.house.registry.living() if a.parent], [])


class TraderSeats(SeatCase):
    """Analyst C: two crypto desks had no trading member for 34-35 of 48 hours while "full" of
    rung-0 replay-only children cycling through births and displacements."""

    def test_a_desk_keeps_one_seat_for_a_trading_member_so_replay_only_children_never_fill_it(self):
        self.rules.update(newcomer_seconds=600, max_population=10)
        self.house.niches["alpaca-crypto-majors"].max_members = 2
        resident = self.seated("resident")
        self.clock.advance(601)
        self.assertIsNone(self.house._refill(self.rules), "the desk's last seat is kept for a member that trades")
        self.fill(resident)
        self.clock.advance(601)
        self.assertEqual(self.house._refill(self.rules).parent, resident.id)

    def test_a_house_mutation_never_displaces_a_desks_last_trading_member(self):
        self.rules.update(newcomer_seconds=600, max_population=1)
        trader = self.seated("trader")
        self.fill(trader)
        self.clock.advance(self.grace + 601)
        self.assertEqual(self.house._weakest(self.rules).id, trader.id)
        self.assertIsNone(self.house._refill(self.rules))
        self.assertTrue(self.house.registry.get(trader.id).alive)


class SeatsHealth(SeatCase):
    def test_health_reports_the_seat_market_and_warns_when_waiters_pile_up(self):
        waiting = {"graduates": [{"candidate": f"c{n}", "niche": "alpaca-crypto-majors", "since": 0.0} for n in range(9)],
                   "cards": [], "strategies": []}
        with patch.object(self.house, "seat_waiters", return_value=waiting):
            self.house._seat_market_watch(fresh=True)
            self.house._health({"at": now_iso(self.clock)})
            health = json.loads((Path(self.house.root) / "health.json").read_text())
            self.assertEqual(health["seats"]["waiters"]["graduates"], 9)
            for key in ("displaceable", "never_traded_past_grace", "last_refused_birth", "reserved_desks"):
                self.assertIn(key, health["seats"])
            self.assertEqual(alerts(self.house, "warning", "waited for seats"), [])
            self.clock.advance(3601)
            self.house._seat_market_watch(fresh=True)
            self.assertEqual(len(alerts(self.house, "warning", "9 newcomers", "waited for seats")), 1)
            self.house._seat_market_watch(fresh=True)
            self.assertEqual(len(alerts(self.house, "warning", "waited for seats")), 1)


class SeatCaps(unittest.TestCase):
    @unittest.skip('Wave 2b rewrites the seat market for the swarm: the options overhaul (Sept 26, 2026) cut niches.json to the options desk and deleted turbo.json')
    def test_desk_caps_and_the_population_follow_the_evidence(self):
        root = Path(__file__).resolve().parents[1]
        niches = {row["id"]: row for row in json.loads((root / "niches.json").read_text())["niches"]}
        # R2 (Sept 24, 2026): the seats follow the waiters that remain once the search's closed desks are taken out
        # (niches.json `_about` has the 15:06Z count behind each), and fewer where the search is closed.
        # Sept 25, 2026 (K1, K1c, K3): sports 19 -> 25 and weather 17 -> 21, a seat for each of the flagged founders;
        # crypto-15m 8 -> 4, the floor its `yields_seats` gives founders down to.
        for desk, cap in {"kalshi-weather": 21, "kalshi-sports": 25, "alpaca-index-etfs": 18, "alpaca-megacaps": 16,
                          "alpaca-crypto-alts": 16, "kalshi-crypto-15m": 4, "kalshi-crypto-strikes": 6, "kalshi-sports-props": 6,
                          "kalshi-attention": 4}.items():
            self.assertEqual(niches[desk]["max_members"], cap, desk)
        turbo = json.loads((root / "turbo.json").read_text())
        self.assertEqual((turbo["max_population"], turbo["newcomer_seconds"]), (128, 600))
        self.assertGreaterEqual(sum(int(row.get("max_members") or 5) for row in niches.values()), turbo["max_population"])
        game = json.loads((root / "game.json").read_text())
        self.assertEqual((game["economy"]["max_population_short_runway"], game["economy"]["population_runway_days"]), (112, 1.5))


if __name__ == "__main__":
    unittest.main()
