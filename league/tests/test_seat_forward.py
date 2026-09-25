"""The seat market's forward tenure, desk capacity, the merged strategies' quota and waiter expiry (F3), and a proven family's
real members on disjoint events (C7): the forward-first run, Sept 25, 2026.

Measured on the T0 snapshot (04:23Z Sept 25): 128 of 128 seats held and none displaceable; 65 waiters, the longest 60.6 h (a
weather card); 111 deaths in 24 h, 96 displaced (86%), the median life under the desk's evidence clock on four desks; the 18
merged strategies "waiting" were 13 corrected children whose foundry card had passed replay -- counted a second time among the
16 cards and born only at the cards' one-an-hour cadence, never on a desk a graduate or card waited for -- and 5 whose card had
failed replay and could never be born; kalshi-crypto-15m held 9 seats (cap 8) on a 7-day pooled record of -4.04 over 307
active blocks while kalshi-sports held 18 of 19 on +1.87 over 61. On Sept 24 the House's births into the proven
sports-central-run-under family traded the same games as their anchor: more weight on one settlement, not more settlements.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league.house import DESK_CLOSED, House, event_share
from league.ledger import now_iso
from league.tests.test_hypotheses import IDLE, PASSER, WEATHER, FoundryCase
from league.tests.test_lab import DESK as LAB_DESK, KNOB, LabCase
from league.tests.test_seat_evidence import EvidenceCase
from league.tests.test_seat_market import SPY, alerts
from league.tests.test_house import BUYER
from league.venues import instrument_for

MAJORS = "alpaca-crypto-majors"
ALTS = "alpaca-crypto-alts"
ALT_BUYER = BUYER.replace('"BTC/USD"', '"SOL/USD"')


class Tenure(EvidenceCase):
    """A resident that has traded keeps its seat until its desk's evidence clock has run from its first fill."""

    def test_a_trader_is_kept_until_its_desks_clock_has_run_from_its_first_fill_not_from_its_seat(self):
        self.desk_clock(20.0)
        trader = self.seated("trader")
        self.clock.advance(19 * 3600)  # its seat is 19 hours old when it first trades
        self.buy(trader)
        self.clock.advance(2 * 3600)  # 21 h seated: past the plain grace (12 h) and the clock from its seat (20 h)
        why: dict[str, int] = {}
        self.assertEqual(self.house._displaceable(self.rules, why=why), [], "2 h from its first fill: inside the clock")
        self.assertEqual(why, {"a trader inside its desk's evidence clock from its first fill": 1})
        self.clock.advance(18 * 3600 + 60)  # 20 h and a minute from its first fill
        self.assertEqual(self.house._weakest(self.rules).id, trader.id, "the clock has run from its first fill")

    def test_a_never_traded_seat_keeps_only_its_fair_chance_and_a_desk_with_no_clock_uses_the_plain_grace(self):
        idle, trader = self.seated("idle"), self.seated("trader")
        self.buy(trader)
        self.clock.advance(3601)  # past the never-traded seat's fair chance (an hour: no clock on the desk)
        self.assertEqual([row[-1].id for row in self.house._displaceable(self.rules, evidenced=True)], [idle.id])
        self.clock.advance(12 * 3600)  # the plain grace from the trader's first fill
        self.assertIn(trader.id, [row[-1].id for row in self.house._displaceable(self.rules)])


class Deaths(EvidenceCase):
    def test_desk_closed_retirements_are_counted_apart_from_displacements(self):
        taken, closed, judged, living = (self.seated(name) for name in ("taken", "closed", "judged", "living"))
        self.house.kill(taken, "displaced", "a newcomer took the seat")
        self.house.kill(closed, DESK_CLOSED, "the Kalshi-scale run's yielding desk gave it up")
        self.house.kill(judged, "evidence", "its record")
        deaths = self.house._deaths_health()
        self.assertEqual((deaths["deaths"], deaths["displaced"], deaths["desk_closed"], deaths["displacement_share"]), (3, 1, 1, 0.333))
        self.assertEqual(self.house._seats_health()["deaths"]["by_cause"], {"desk_closed": 1, "displaced": 1, "evidence": 1})
        self.clock.advance(24 * 3600 + 1)
        self.assertEqual(self.house._deaths_health()["deaths"], 0, "the last day only")


class DeskCapacity(EvidenceCase):
    """A desk's cap follows its pooled forward record over the last 7 days: a negative desk loses a seat every 12 hours
    down to its floor, a positive one gains one up to its niches.json cap plus the gain; nobody is killed for it."""

    def record(self, agent, growth, n, *, hours_ago=0.0):
        key = now_iso(lambda: self.clock() - hours_ago * 3600)[:13]
        for _ in range(n):
            self.house.ledger.append("eval.block", {"agent": agent.id, "active": True, "log_growth": growth, "book": "alpaca-paper",
                                                    "horizon": "hour", "key": key}, agent=agent.id)

    def test_the_desks_records_are_the_blocks_that_began_in_the_window(self):
        loser, winner = self.seated("loser"), self.seated("winner", SPY)
        self.record(loser, -0.01, 100)
        self.record(loser, +5.0, 7, hours_ago=8 * 24)  # began eight days ago: outside the window
        self.record(winner, 0.002, 30)
        self.house.ledger.append("eval.block", {"active": False, "log_growth": 0.5, "key": now_iso(self.clock)[:13]}, agent=winner.id)
        records = self.house.desk_records()
        self.assertEqual(records[MAJORS][0], 100)
        self.assertAlmostEqual(records[MAJORS][1], -1.0)
        self.assertEqual(records["alpaca-index-etfs"][0], 30, "an inactive block is not counted")
        self.assertAlmostEqual(records["alpaca-index-etfs"][1], 0.06)

    def test_a_negative_desk_loses_a_seat_every_twelve_hours_to_its_floor_and_a_positive_one_gains(self):
        loser, winner = self.seated("loser"), self.seated("winner", SPY)
        self.record(loser, -0.01, 100)
        self.record(winner, 0.002, 30)
        majors, etfs, weather = self.house.niches[MAJORS], self.house.niches["alpaca-index-etfs"], self.house.niches["kalshi-weather"]
        base_majors, base_etfs, base_weather = majors.max_members, etfs.max_members, weather.max_members
        self.rules["desk_capacity_floor"] = base_majors - 2
        self.house.keep_population(refill=False)
        self.assertEqual((majors.max_members, etfs.max_members, weather.max_members), (base_majors - 1, base_etfs + 1, base_weather),
                         "a desk with no record keeps its niches.json cap")
        rows = [e.payload for e in self.house.ledger.iter(kinds="route.decision") if str(e.payload.get("task")).startswith("desk-capacity:")]
        self.assertEqual(sorted((r["evidence"]["desk"], r["route"], r["evidence"]["cap"]) for r in rows),
                         [("alpaca-crypto-majors", "shrink", base_majors - 1), ("alpaca-index-etfs", "grow", base_etfs + 1)])
        self.assertEqual(len(alerts(self.house, "info", "desk capacity follows the forward record")), 1)
        self.clock.advance(3600)
        self.house._data_cache.pop("desk_records", None)
        self.house.keep_population(refill=False)
        self.assertEqual(majors.max_members, base_majors - 1, "two seats a day: one step every twelve hours")
        self.clock.advance(11 * 3600)
        self.house._data_cache.pop("desk_records", None)
        self.house.keep_population(refill=False)
        self.assertEqual((majors.max_members, etfs.max_members), (base_majors - 2, base_etfs + 2))
        self.clock.advance(12 * 3600)
        self.house._data_cache.pop("desk_records", None)
        self.house.keep_population(refill=False)
        self.assertEqual(majors.max_members, base_majors - 2, "at its floor: done")
        self.assertTrue(self.house._state["desk_capacity"][MAJORS]["rule"].startswith("at its floor: done"))
        caps = self.house._desk_caps()
        self.assertEqual((caps[MAJORS]["cap"], caps[MAJORS]["base"], caps[MAJORS]["record"]["blocks"]), (base_majors - 2, base_majors, 100))
        self.assertTrue(self.house.registry.get(loser.id).alive, "nobody is killed by the rule")
        self.rules["desk_capacity_seats_a_day"] = 0  # off: every cap back to niches.json
        self.house.keep_population(refill=False)
        self.assertEqual((majors.max_members, etfs.max_members), (base_majors, base_etfs))

    def test_a_desk_over_its_cap_makes_no_seat_there_and_its_residents_go_first_league_wide(self):
        first, second, third = (self.seated(name) for name in ("first", "second", "third"))
        alt = self.seated("alt", ALT_BUYER)
        for agent in (first, second, third):
            self.house.economy.grant(agent.id, "5", "test: a richer purse ranks after a poorer one")
        self.house.niches[MAJORS].max_members = 2
        self.clock.advance(3601)  # every seat past its fair chance, none ever traded
        why: dict[str, int] = {}
        self.assertEqual(self.house._displaceable(self.rules, specialty=MAJORS, evidenced=True, why=why), [])
        self.assertEqual(why, {"its desk is over the cap its forward record gives it (3 members, cap 2)": 1})
        order = [row[-1].id for row in self.house._displaceable(self.rules, evidenced=True)]
        self.assertEqual(order[-1], alt.id, "the over-cap desk's residents rank first league-wide")
        with self.proven("test-family"):
            self.assertTrue(self.house._displaceable(self.rules, specialty=MAJORS, evidenced=True,
                                                     newcomer=__import__("league.house", fromlist=["Newcomer"]).Newcomer(
                                                         family="test-family", venue="alpaca")),
                            "a proven family's newcomer still has a seat there")


class StrategiesQuota(FoundryCase):
    """A merged corrected child is one waiter with its route; one whose card failed replay leaves the queue; the quota
    births a passed one first into a free seat or its desk's weakest never-traded resident, and keeps those seats for it."""

    def merged(self, *rows):
        import league.strategies as strategies

        full = [{"name": name, "family": "fam", "code": code, "why": "a corrected child",
                 "repair": {"key": key, "parent": "parent"}} for name, code, key in rows]
        strategies.all_strategies.return_value = full
        self.house._data_cache.pop("seat_waiters", None)
        return full

    def passed(self, name):
        card = self.foundry.strategy_cards()[name]
        self.foundry.evaluate_all([card["id"]])
        self.house._data_cache.pop("seat_waiters", None)
        return card

    def test_a_merged_strategys_card_is_one_waiter_with_its_route_never_a_card_too(self):
        self.merged(("majors-fixed", PASSER, "strategy_defect:parent:abcdef123456"))
        self.house.enroll()  # the foundry takes it: its card is replayed before any seat
        waiting = self.house.seat_waiters(fresh=True)
        self.assertEqual([(w["strategy"], w["route"]) for w in waiting["strategies"]], [("majors-fixed", "replay")])
        card = self.passed("majors-fixed")
        waiting = self.house.seat_waiters(fresh=True)
        self.assertEqual([(w["strategy"], w["route"], w["card"]) for w in waiting["strategies"]], [("majors-fixed", "card", card["id"])])
        self.assertEqual(waiting["cards"], [], "counted once, as a merged strategy")

    def test_a_merged_strategy_whose_card_failed_replay_leaves_the_queue(self):
        self.merged(("majors-idle", IDLE, "strategy_defect:parent:abcdef123456"))
        self.house.enroll()
        card = self.passed("majors-idle")
        self.assertEqual(self.foundry.evaluations()[card["id"]]["outcome"], "failed")
        self.assertEqual(self.house.seat_waiters(fresh=True)["strategies"], [])
        gone = self.house._state["seat_expired"]["strategies:majors-idle"]
        self.assertEqual(gone["rule"], "replay")
        self.assertIn("failed the House's replay gate", gone["why"])
        self.assertEqual(self.house._seat_market_watch(fresh=True)["expired"]["by_rule"], {"replay": 1})

    def test_the_quota_births_it_first_into_its_desks_never_traded_seat_and_keeps_that_seat_from_others(self):
        self.merged(("majors-fixed", PASSER, "strategy_defect:parent:abcdef123456"))
        self.house.enroll()
        card = self.passed("majors-fixed")
        self.house.niches[self.DESK].max_members = 2
        idle, trader = self.seated("idle"), self.seated("trader")
        for _ in range(3):
            self.house.ledger.append("book.fill", {"book": "alpaca-paper", "symbol": "BTC/USD", "side": "buy", "quantity": "0.001",
                                                   "price": "60000", "source": "venue"}, agent=trader.id)
        self.rules.update(max_population=2)
        self.clock.advance(3601)  # past the idle seat's fair chance
        self.assertIsNone(self.house._weakest(self.rules, specialty=self.DESK, evidenced=True),
                          "another class's newcomer is not given the seat the quota keeps for the merged strategy")
        child = self.house._strategy_births(self.rules)
        self.assertIsNotNone(child)
        self.assertEqual((child.founder, child.specialty, self.house.evaluator.rung(child.id)), ("majors-fixed", self.DESK, 1))
        self.assertFalse(self.house.registry.get(idle.id).alive)
        self.assertTrue(self.house.registry.get(trader.id).alive, "a trader's seat is never the quota's")
        route = self.house.ledger.get(f"quota:{child.id}").payload
        self.assertEqual((route["route"], route["evidence"]["card"], route["evidence"]["displaced"]), ("strategies_quota", card["id"], idle.id))
        self.assertEqual(self.house.seat_waiters(fresh=True)["strategies"], [])
        self.assertEqual(self.foundry.inventory(), [])

    def test_a_corrected_child_of_a_real_money_parent_is_born_first(self):
        self.merged(("majors-older", PASSER, "strategy_defect:parent:abcdef123456"))
        self.house.enroll()
        self.clock.advance(3600)
        self.merged(("majors-older", PASSER, "strategy_defect:parent:abcdef123456"),
                    ("majors-real", PASSER.replace("sawtooth", "sawtooth-real"),
                     "order_refusal:alpaca:position would be #% of desk equity, cap #%"))
        self.house.enroll()
        self.passed("majors-older")
        self.passed("majors-real")
        waiting = {w["strategy"]: w for w in self.house.seat_waiters(fresh=True)["strategies"]}
        self.assertEqual((waiting["majors-real"]["real"], waiting["majors-older"]["real"]), (True, False))
        self.rules.update(max_population=10)
        child = self.house._strategy_births(self.rules)
        self.assertEqual(child.founder, "majors-real", "a refusal on a real book: a live defect is fixed first")

    def test_a_merged_strategy_with_no_seat_for_a_day_goes_to_the_lab_and_is_never_born_by_the_house(self):
        self.merged(("majors-fixed", PASSER, "strategy_defect:parent:abcdef123456"))
        self.house.enroll()
        self.passed("majors-fixed")
        resident = self.seated("resident")
        self.house.evaluator.promote(resident.id, 2, "test: real money")  # nobody may make way
        self.rules.update(max_population=1)
        self.assertIsNone(self.house._strategy_births(self.rules))
        self.assertIn("the quota found no seat for majors-fixed", self.house._state["seat_refusals"]["strategies"]["why"])
        lab = self.house.lab = FakeLab()
        self.clock.advance(24 * 3600 + 60)
        self.assertEqual(self.house.seat_waiters(fresh=True)["strategies"], [])
        gone = self.house._state["seat_expired"]["strategies:majors-fixed"]
        self.assertEqual((gone["rule"], gone["lab"]), ("aged", "queued in the Alpha Lab as candidate lab-candidate-1"))
        self.assertEqual((lab.admitted[0][1]["lineage"], lab.admitted[0][1]["author"]), ("strategy:majors-fixed", "merton"))
        self.rules.update(max_population=10)
        self.assertIsNone(self.house._strategy_births(self.rules))
        self.assertEqual(self.house.enroll(), [])
        self.assertEqual([a.founder for a in self.house.registry.living()], [None])

    def test_the_quota_off_births_nothing_and_holds_nothing(self):
        self.merged(("majors-fixed", PASSER, "strategy_defect:parent:abcdef123456"))
        self.house.enroll()
        self.passed("majors-fixed")
        self.rules["strategies_reserved_seats"] = 0
        self.rules.update(max_population=10)
        self.assertIsNone(self.house._strategy_births(self.rules))
        self.assertEqual(self.house._strategy_holds(), {})
        self.rules.update(newcomer_seconds=600)
        self.seated()  # a league of one: the refill runs only over a living league
        self.clock.advance(601)
        child = self.house._refill(self.rules)
        self.assertEqual(child.founder, "majors-fixed", "born by the refill's card pass, as before")


class FakeLab:
    def __init__(self):
        self.admitted = []

    def admit(self, code, **kw):
        self.admitted.append((code, kw))
        return "lab-candidate-1"

    def forward_scores(self):
        return {}


class CardsAge(FoundryCase):
    def test_a_card_that_waited_its_day_goes_back_to_the_lab_and_is_never_admitted_by_the_house(self):
        self.call()  # the sawtooth card passes replay on the crypto majors desk
        card = self.card_of("sawtooth")
        lab = self.house.lab = FakeLab()
        self.assertEqual([w["card"] for w in self.house.seat_waiters(fresh=True)["cards"]], [card["id"]])
        self.clock.advance(24 * 3600 + 60)
        self.assertEqual(self.house.seat_waiters(fresh=True)["cards"], [])
        gone = self.house._state["seat_expired"][f"cards:{card['id']}"]
        self.assertEqual(gone["rule"], "aged")
        self.assertEqual(gone["lab"], "queued in the Alpha Lab as candidate lab-candidate-1")
        code, kw = lab.admitted[0]
        self.assertEqual((kw["niche"].id, kw["origin"], kw["lineage"]), (self.DESK, "agent", card["line_id"]))
        self.assertIn("NEEDS", code)
        row = self.house.ledger.get(f"seat-expired:cards:{card['id']}").payload
        self.assertEqual((row["evidence"]["rule"], row["evidence"]["lab"]), ("aged", gone["lab"]))
        self.rules.update(newcomer_seconds=600, max_population=40)
        self.clock.advance(601)
        self.assertIsNone(self.house._refill(self.rules), "the foundry admits only the waiters the House counts")
        self.assertEqual([c["id"] for c in self.foundry.inventory()], [card["id"]], "the foundry's own record is untouched")


class GraduatesAge(LabCase):
    def setUp(self):
        super().setUp()
        self.rules = self.house.game["economy"]

    def waiting_graduate(self):
        self.queue(KNOB, origin="luna")
        self.lab.evaluate_batch()
        self.forward_wins()  # F1: a graduate needs a winning forward window of its own
        self.niche.max_members = 1
        resident = self.seated("resident")
        self.house.evaluator.promote(resident.id, 2, "test: real money")  # nobody may be displaced: the graduate waits
        self.assertEqual(self.lab.graduate()[0]["state"], "waiting_seat")
        return self.house.seat_waiters(fresh=True)["graduates"][0]["candidate"]

    def window(self, ident, mean):
        now = self.clock()
        self.lab._x("INSERT INTO forward(candidate, at, window_start, window_end, tape_id, ok, blocks, active_blocks, log_growth,"
                    " mean_log_growth, trades, error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ident, now, now - 86400, now, "fwd:test", 1, 4, 4, mean * 4, mean, 6, None))

    def test_a_graduate_that_waited_its_day_is_held_by_the_lab_until_its_forward_window_wins(self):
        """Under F1 a graduate reaches the queue only on a winning window of its own, so one that waited its day
        and whose latest window has since lost leaves the queue by the lab's forward rule (the more specific
        reason than "aged"), and is a waiter again once a later window of its own wins."""
        ident = self.waiting_graduate()
        self.clock.advance(24 * 3600 + 60)
        self.window(ident, -0.0002)  # its latest window loses
        self.assertEqual(self.house.seat_waiters(fresh=True)["graduates"], [])
        gone = self.house._state["seat_expired"][f"graduates:{ident}"]
        self.assertEqual(gone["rule"], "forward")
        self.assertTrue(str(self.lab._hold(self.candidate(ident))).startswith("forward: "))
        self.clock.advance(60)
        self.window(ident, 0.0002)  # its own window wins again
        self.assertIsNone(self.lab._hold(self.candidate(ident)))
        self.assertEqual([w["candidate"] for w in self.house.seat_waiters(fresh=True)["graduates"]], [ident], "a waiter again")
        self.assertNotIn(f"graduates:{ident}", self.house._state["seat_expired"])

    def test_a_graduate_with_a_winning_window_keeps_its_place_however_long_it_waits(self):
        ident = self.waiting_graduate()
        self.window(ident, 0.0002)
        self.clock.advance(48 * 3600)
        self.assertEqual([w["candidate"] for w in self.house.seat_waiters(fresh=True)["graduates"]], [ident])


class EventSplit(EvidenceCase):
    """C7: a proven family's members on real money take disjoint events of their desk."""

    def members(self, n=3):
        agents = [self.house.spawn("mullins", "weather-favorites", WEATHER.replace("favorites", f"favorites-{i}"), reason="test")
                  for i in range(n)]
        for agent in agents[:2]:
            self.house.evaluator.seat(agent.id, 1, "test")
            self.house.evaluator.promote(agent.id, 2, "test: real money")
        return agents

    def test_the_split_is_a_stable_hash_of_the_event_and_each_member(self):
        members = ["a", "b", "c"]
        event = "KXHIGHNY-26SEP25"
        expected = max(members, key=lambda m: (hashlib.sha256(f"{event}|{m}".encode()).digest(), m))
        self.assertEqual(event_share(members, event), expected)
        self.assertEqual(event_share(list(reversed(members)), event.lower()), expected)
        self.assertIsNone(event_share([], event))

    def test_a_member_seated_or_gone_moves_only_its_own_share_of_the_events(self):
        """The Deploy B review (Sept 25, 2026): the event's hash modulo the number of members moved about half of the
        events between the members already there when a second one joined. Rendezvous hashing moves only the newcomer's."""
        events = [f"KXMLBTOTAL-26SEP{day:02d}{game}" for day in range(1, 29) for game in ("TBPHI", "PITDET", "TEXMIN", "AZSD")]
        two = {e: event_share(["x", "y"], e) for e in events}
        three = {e: event_share(["x", "y", "z"], e) for e in events}
        moved = [e for e in events if two[e] != three[e]]
        self.assertTrue(moved)
        self.assertEqual({three[e] for e in moved}, {"z"}, "only the newcomer's share moves")
        self.assertEqual({e: event_share(["x", "y"], e) for e in events}, two)

    def real_book(self, holdings=(), bids=()):
        """A stand-in for the real Kalshi book: `holdings` [(agent, market)] held, `bids` [(agent, market)] working buys."""
        accounts = {}
        for agent, market in holdings:
            instrument = instrument_for("kalshi", {"market": market})
            accounts.setdefault(agent.id, SimpleNamespace(holdings={}))
            accounts[agent.id].holdings[instrument.key] = SimpleNamespace(instrument=instrument, quantity=2)
        orders = [SimpleNamespace(side="buy", instrument=instrument_for("kalshi", {"market": market}),
                                  shares=[SimpleNamespace(agent=agent.id, quantity=2, filled=0)]) for agent, market in bids]
        return SimpleNamespace(real_money=True, accounts=accounts, open_orders=lambda agent=None: list(orders))

    def test_an_event_a_member_holds_stays_its_own_when_the_split_moves(self):
        """The Deploy B review (Sept 25, 2026): meriwether-h2d625d holds NO on up to ~6 open MLB totals, 2-27 h before the
        first pitch. A second member seated on real money must not be handed one of those games by the hash, nor enter it
        once the holder is sent back to practice to wind down; and the holder keeps seeing the markets of what it holds."""
        first, second, practice = self.members()
        self.house.evaluator.demote(second.id, "test: back to practice")  # first alone on real money
        games = [f"KXMLBTOTAL-26SEP25{game}" for game in ("1840TBPHI", "1905PITDET", "2010TEXMIN", "2140AZSD", "2210SDLAD", "1910NYYBAL")]
        theirs = next(g for g in games if event_share(sorted([first.id, second.id]), g) == second.id)
        held = f"{theirs}-8"
        book = self.real_book(holdings=[(first, held)])
        markets = [{"market": f"{g}-{strike}"} for g in games for strike in (7, 8, 9)]
        with self.proven("weather-favorites"):
            self.assertEqual(self.house._event_members(first), [first.id])
            self.house.evaluator.promote(second.id, 2, "test: seated on real money")  # the split moves at once: no cache
            self.assertEqual(self.house._event_members(second), sorted([first.id, second.id]))
            seen = {}
            for agent in (first, second):
                ctx = {"markets": list(markets)}
                self.house._split_events(agent, ctx, book)
                seen[agent.id] = {m["market"] for m in ctx["markets"]}
            self.assertIn(held, seen[first.id], "the holder still sees the markets of what it holds")
            self.assertNotIn(held, seen[second.id], "the newcomer is not handed a game its family already holds")
            self.assertFalse(seen[first.id] & seen[second.id])
            refusal = self.house._event_refusal(second, book, instrument_for("kalshi", {"market": f"{theirs}-9"}))
            self.assertIn(f"held or bid by {first.id}", refusal)
            self.assertEqual(self.house._event_refusal(first, book, instrument_for("kalshi", {"market": f"{theirs}-9"})), "")
            # The holder is sent back to practice and winds its contracts down to settlement: its game stays its own.
            self.house.evaluator.demote(first.id, "test: back to practice")
            self.assertIn(f"held or bid by {first.id}", self.house._event_refusal(second, book, instrument_for("kalshi", {"market": held})))
            ctx = {"markets": list(markets)}
            self.house._split_events(second, ctx, book)
            self.assertNotIn(held, {m["market"] for m in ctx["markets"]})
            self.assertEqual(len(ctx["markets"]), len(markets) - 3, "every other game is the lone member's")
            # A working buy holds its event the same way.
            bidding = self.real_book(bids=[(practice, held)])
            self.house.registry.get(practice.id).family = "weather-other"
            self.assertEqual(self.house._event_refusal(second, bidding, instrument_for("kalshi", {"market": held})), "",
                             "an agent of another family is no member")
            self.house.registry.get(practice.id).family = second.family
            self.assertIn(f"held or bid by {practice.id}",
                          self.house._event_refusal(second, bidding, instrument_for("kalshi", {"market": held})))

    def test_two_real_members_of_a_proven_family_see_disjoint_events_and_each_event_whole(self):
        first, second, practice = self.members()
        markets = [{"market": f"KXHIGHNY-26SEP{day:02d}-T{strike}"} for day in range(1, 29) for strike in (70, 75, 80)]
        with self.proven("weather-favorites"):
            self.assertEqual(self.house._event_members(first), sorted([first.id, second.id]))
            self.assertEqual(self.house._event_members(practice), [], "a practice member trades what it likes")
            shown = {}
            for agent in (first, second):
                ctx = {"markets": list(markets)}
                self.house._split_events(agent, ctx)
                shown[agent.id] = {m["market"] for m in ctx["markets"]}
                self.assertEqual(ctx["event_share"]["members"], 2)
            self.assertFalse(shown[first.id] & shown[second.id], "no event is bet by two members")
            self.assertEqual(shown[first.id] | shown[second.id], {m["market"] for m in markets})
            self.assertTrue(shown[first.id] and shown[second.id])
            for day in range(1, 29):
                owners = {agent for agent, seen in shown.items() for strike in (70, 75, 80) if f"KXHIGHNY-26SEP{day:02d}-T{strike}" in seen}
                self.assertEqual(len(owners), 1, "one event's strikes stay with one member")
            real = SimpleNamespace(real_money=True)
            theirs = next(iter(shown[second.id]))
            refusal = self.house._event_refusal(first, real, instrument_for("kalshi", {"market": theirs}))
            self.assertIn(f"{second.id}'s share", refusal)
            mine = next(iter(shown[first.id]))
            self.assertEqual(self.house._event_refusal(first, real, instrument_for("kalshi", {"market": mine})), "")
            self.assertEqual(self.house._event_refusal(first, SimpleNamespace(real_money=False), instrument_for("kalshi", {"market": theirs})), "")
        self.house._data_cache.clear()
        ctx = {"markets": list(markets)}
        self.house._split_events(first, ctx)
        self.assertEqual(len(ctx["markets"]), len(markets), "an unproven family is not split")


class Bounds(EvidenceCase):
    KEYS = ("strategies_reserved_seats", "waiter_expiry_hours", "desk_capacity_days", "desk_capacity_shrink_blocks",
            "desk_capacity_grow_blocks", "desk_capacity_seats_a_day", "desk_capacity_floor", "desk_capacity_max_gain")

    def test_every_new_dial_has_a_bound_that_the_check_enforces(self):
        from league.economy import check_bounds

        game = json.loads((Path(__file__).resolve().parents[1] / "game.json").read_text(encoding="utf-8"))
        for key in self.KEYS:
            self.assertIn(key, game["economy"])
            self.assertIn(key, game["bounds"])
            low, high = game["bounds"][key]
            self.assertTrue(float(low) <= float(game["economy"][key]) <= float(high), key)
            broken = json.loads(json.dumps(game))
            broken["economy"][key] = float(high) + 1
            with self.assertRaises(ValueError):
                check_bounds(broken)
