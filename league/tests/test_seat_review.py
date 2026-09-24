"""The adversarial review of R2 and R3 (#276, the close-the-gaps run, Sept 24, 2026): what the seat market's capacity
and the proven family's births could do to a live floor of 112-128 agents, each a scenario that failed before its fix.
"""
from __future__ import annotations

from unittest.mock import patch

from league.house import Newcomer
from league.tests.test_house import BUYER, HouseCase
from league.tests.test_hypotheses import FoundryCase
from league.tests.test_lab import KNOB, LabCase
from league.tests.test_seat_capacity import NoFoundryCards
from league.tests.test_seat_evidence import DESK, EvidenceCase
from league.tests.test_seat_market import SeatCase, alerts


class ReviewCase(EvidenceCase):
    def resident(self, name, family="another-family", code=BUYER):
        """A paper resident of the test desk in a family of its own (`seated` puts everyone in "test-family")."""
        agent = self.house.spawn(name, family, code, reason="a resident of another family")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        return agent


class ProvenProgramWithNoMutationLeft(ReviewCase):
    """R3 breeds a proven family's program by a House mutation of its anchor's PARAMS (`_mutated_params`). When no
    distinct valid mutation is left (no declared or standard knob, the anchor's own PARAMS outside its rules, or 64
    proposals that all repeat a living twin), the family stayed owed: its desk gave every other family's newcomer no
    seat for good (`_displaceable`'s R3 hold), and the pass asked for the desk's weakest resident and a mutation (a
    rejected `agent.mutation` row each time the registry grew) on every tick."""

    def setUp(self):
        super().setUp()
        self.rules.update(newcomer_seconds=600, proven_family_members=4)
        self.anchor = self.seated("anchor")
        self.house.evaluator.promote(self.anchor.id, 2, "test: a bunt on real money")
        self.buy(self.anchor)

    def test_a_program_with_no_mutation_left_holds_no_desk_and_is_asked_again_hourly_not_every_tick(self):
        idle = self.resident("idle")  # never trades: an evidenced newcomer's seat once its fair chance has run
        self.clock.advance(3601)
        another = Newcomer(family="another", venue="alpaca", what="a graduate of another family")
        with self.proven("test-family"), patch.object(self.house, "_mutated_params", return_value=None) as mutated:
            self.assertEqual([w["family"] for w in self.house.seat_waiters(fresh=True)["proven"]], ["test-family"])
            self.assertIsNone(self.house._proven_births(self.rules))
            self.assertEqual(mutated.call_count, 1)
            self.assertEqual(self.house.seat_waiters(fresh=True)["proven"], [], "nothing can be bred: nothing is owed")
            self.assertIn("no distinct valid mutation", self.house._proven_programs()[0]["held"])
            self.assertEqual(self.house._weakest(self.rules, specialty=self.anchor.specialty, evidenced=True, newcomer=another).id,
                             idle.id, "its desk is not held for births that cannot be made")
            for _ in range(5):
                self.clock.advance(601)
                self.assertIsNone(self.house._proven_births(self.rules))
            self.assertEqual(mutated.call_count, 1, "not asked again every tick")
            self.clock.advance(3600)
            self.assertIsNone(self.house._proven_births(self.rules))
            self.assertEqual(mutated.call_count, 2, "asked again an hour on: a twin's death or a new anchor may open one")
        with self.proven("test-family"):
            self.clock.advance(3601)
            child = self.house._proven_births(self.rules)
            self.assertIsNotNone(child, "a mutation found again: the family is bred first again")
            self.assertNotIn("test-family", self.house._state.get("proven_unbred") or {})


class ExpiredWaitersComeBackWhenTheirReasonIsGone(FoundryCase):
    """R2 (1): a waiter whose desk the search closes leaves the queue. It left for SEAT_EXPIRED_KEEP_SECONDS (a week)
    whatever happened next: a desk the search reopened (the foundry's reopening rule reads one family's pooled record
    there -- kalshi-crypto-strikes reopened at 15:06Z on crypto-strikes-lab-1b9d16's +0.026 over 7 active blocks and
    955dae's +0.234 over 17 -- and the House reads it through a ten-minute cache, so a waiter could leave in the minutes
    after a reopening) kept its waiters out of the count for a week, while the lab and the foundry, which never read the
    House's expiry, seated them there; a retained candidate was dropped for good at the next admission pass."""

    def close(self, *desks):
        self.house.game.setdefault("hypotheses", {})["closed_desks"] = list(desks)
        self.house._data_cache.pop("search_closed", None)

    def test_a_card_whose_desk_reopens_is_a_waiter_again_and_leaves_again_if_it_closes(self):
        self.call()  # the sawtooth card passes replay on the crypto majors desk
        card = self.card_of("sawtooth")
        key = f"cards:{card['id']}"
        self.close(self.DESK)
        self.assertEqual(self.house.seat_waiters(fresh=True)["cards"], [])
        self.assertIn(key, self.house._state["seat_expired"])
        self.close()  # a family there turns positive: the search reopens the desk
        self.assertEqual([w["card"] for w in self.house.seat_waiters(fresh=True)["cards"]], [card["id"]], "back in the queue")
        self.assertNotIn(key, self.house._state["seat_expired"])
        self.assertEqual(self.house._seat_market_watch(fresh=True)["waiters"]["cards"], 1)
        self.close(self.DESK)
        self.assertEqual(self.house.seat_waiters(fresh=True)["cards"], [], "closed again: it leaves again")
        self.assertEqual(len(alerts(self.house, "info", "left the seat queue")), 1, "told at most once an hour a desk")


class RetainedCandidateOnAClosedDesk(ReviewCase):
    """An expired retained candidate's admission was dropped at the next admission pass: a desk closed for one pass lost
    a replay-passed program for good. It now waits outside the queue while the search closes its desk (never counted,
    never seated there), comes back if the desk reopens inside RETAINED_TTL_SECONDS, and is dropped by that TTL if not."""

    def retained(self, code):
        from league import niches as niches_module
        from league.lab import static_literal

        needs = niches_module.constrain(static_literal(code, "NEEDS"), self.house.niches[DESK])
        return {"code": code, "params": static_literal(code, "PARAMS"), "needs": needs, "passed": True,
                "purpose": "a retained test candidate", "numbers": {"trades": 40, "passed": True, "return_pct": 12.0}}

    def row(self, session):
        from league.admissions import Admissions

        return next(r for r in Admissions(self.house.ledger).rows() if r["session"] == session)

    def search(self, closed):
        self.house.hypotheses = NoFoundryCards(closed)
        self.house._data_cache.pop("search_closed", None)

    def test_a_retained_candidate_is_kept_while_its_desk_is_closed_and_seated_when_it_reopens(self):
        from league.admissions import Admissions

        author = self.seated("author")
        candidate = self.retained(BUYER + "\n# a better program\n")
        queue = Admissions(self.house.ledger)
        row = queue.enqueue(author.id, self.house._generation(author.id), candidate, "research:author:1")
        queue.record(row, "deferred", "niche is full; waiting for an eligible seat")
        self.house.kill(author, "displaced", "test")
        self.search({DESK: f"no family on {DESK} has a positive forward record over 3 active blocks there"})
        self.assertEqual(self.house.seat_waiters(fresh=True)["retained"], [], "it left the queue")
        self.assertEqual(self.house._state["seat_expired"]["retained:research:author:1"]["rule"], "closed")
        rows = Admissions(self.house.ledger).rows()
        for entry in self.house._retained_waiting(expired=True):
            self.assertIsNone(self.house._admit_orphan(entry, self.rules, rows))
        self.assertEqual(self.row("research:author:1")["status"], "orphaned", "not dropped while its desk is closed")
        self.search({})  # the search reopens the desk
        self.assertEqual([w["session"] for w in self.house.seat_waiters(fresh=True)["retained"]], ["research:author:1"])
        self.rules.update(newcomer_seconds=600, max_population=10)
        self.clock.advance(601)
        child = self.house._refill(self.rules)
        self.assertEqual((child.parent, child.code), (author.id, candidate["code"]))
        self.assertEqual(self.row("research:author:1")["status"], "admitted")

    def test_a_retained_candidate_whose_desk_stays_closed_is_dropped_by_its_ttl(self):
        from league.admissions import Admissions

        author = self.seated("author")
        queue = Admissions(self.house.ledger)
        row = queue.enqueue(author.id, self.house._generation(author.id), self.retained(BUYER + "\n# closed for good\n"), "research:author:1")
        queue.record(row, "deferred", "niche is full; waiting for an eligible seat")
        self.house.kill(author, "displaced", "test")
        self.search({DESK: "closed"})
        self.house.seat_waiters(fresh=True)
        self.clock.advance(self.house.RETAINED_TTL_SECONDS + 60)
        rows = Admissions(self.house.ledger).rows()
        for entry in self.house._retained_waiting(expired=True):
            self.assertIsNone(self.house._admit_orphan(entry, self.rules, rows))
        self.assertEqual(self.row("research:author:1")["status"], "dropped")
        self.assertEqual(self.house._state.get("retained") or {}, {})


class GraduateWhoseWindowStopsLosing(LabCase):
    def test_a_graduate_whose_forward_window_no_longer_loses_is_a_waiter_again(self):
        self.queue(KNOB, origin="luna")
        self.lab.evaluate_batch()
        self.niche.max_members = 1
        resident = self.seated("resident")
        self.house.evaluator.promote(resident.id, 2, "test: real money")  # nobody may be displaced: the graduate waits
        self.assertEqual(self.lab.graduate()[0]["state"], "waiting_seat")
        ident = self.house.seat_waiters(fresh=True)["graduates"][0]["candidate"]
        now = self.clock()
        window = ("INSERT INTO forward(candidate, at, window_start, window_end, tape_id, ok, blocks, active_blocks, log_growth,"
                  " mean_log_growth, trades, error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)")
        self.lab._x(window, (ident, now, now - 86400, now, "fwd:test", 1, 4, 4, -0.000568, -0.000142, 6, None))
        self.assertEqual(self.house.seat_waiters(fresh=True)["graduates"], [], "its window loses: it leaves")
        self.clock.advance(3600)
        self.lab._x(window, (ident, self.clock(), now - 86400, self.clock(), "fwd:test", 1, 5, 5, 0.00051, 0.000102, 8, None))
        self.assertEqual([w["candidate"] for w in self.house.seat_waiters(fresh=True)["graduates"]], [ident],
                         "its window wins now: the lab will seat it, and the House counts it again")
        self.assertNotIn(f"graduates:{ident}", self.house._state["seat_expired"])


class PopulationAtTheRunwayFloor(SeatCase):
    """R2 (3) grows the league toward turbo.json's 128 while Sail's runway is over 1.5 days and holds it at 112 otherwise.
    Measured on the 15:06Z snapshot (492 readings of the House's Sail meter, the builder's formula): the runway moves a
    median 0.6% a reading, 2.6% at the 90th percentile and 7.9% at the 99th, and it ROSE with no top-up in 243 of 491
    readings (a heavy hour leaving the trailing day's window lowers the burn). Near the floor the rule flipped with the
    readings: an alert each time, and each ten-minute window over the floor seated newcomers that the next window never
    removed, so the league crept toward 128 on a runway at the floor. And a meter that could not be read raised out of
    the rule, which left turbo.json's 128 in place at startup and skipped the rule in the tick."""

    def setUp(self):
        super().setUp()
        self.house._burst = {"id": "test-burst", "started": 0.0, "policy": {"minimum_research_passes": 2}}
        self.house._population_ceiling = 128
        self.rules.update(population_runway_days=1.5, max_population_short_runway=112, max_population=128)

    def runway(self, days, *, spent=0.36, every=900):
        """A day of the Sail meter's rows (league/budget.py `Budget.check`) whose runway over the $5 reserve is `days`
        at `spent` a reading ($34.56 a day at $0.36 each fifteen minutes)."""
        from league.ledger import now_iso

        self.clock.advance(25 * 3600)  # yesterday's readings leave the trailing day
        balance = 5 + days * spent * 86400 / every
        end, n = self.clock(), int(86400 / every)
        for i in range(n + 1):
            at = end - (n - i) * every
            self.house.ledger.append("ops.budget", {"what": "sail", "balance_usd": f"{balance + spent * (n - i):.2f}",
                                                    "spent_usd": f"{spent:.2f}", "month_usd": "0", "cap_usd": "300", "mode": "open"},
                                     at=now_iso(lambda at=at: at))
        self.house._data_cache.pop("sail_runway", None)

    def test_a_runway_hovering_at_the_floor_does_not_flip_the_population(self):
        self.runway(1.45)
        self.assertEqual(self.house._population_rule()["max_population"], 112)
        self.runway(1.55)  # back over 1.5 with no top-up: a heavy hour left the window
        self.assertEqual(self.house._population_rule()["max_population"], 112, "inside the band: still held")
        self.rules["max_population"] = 128  # a restart: `game_for` sets turbo.json's ceiling again
        self.runway(1.6)
        self.assertEqual(self.house._population_rule()["max_population"], 112, "held across a restart (house.json)")
        self.runway(1.8)
        report = self.house._population_rule()
        self.assertEqual(report["max_population"], 128, "clear of the band: it grows")
        self.runway(1.6)
        self.assertEqual(self.house._population_rule()["max_population"], 128, "growing: held only at the floor")
        self.runway(1.45)
        self.assertEqual(self.house._population_rule()["max_population"], 112)
        self.assertEqual(len(alerts(self.house, "warning", "population is now 112")), 3, "held, held again at the restart, held")
        self.assertEqual(len(alerts(self.house, "info", "population is now 128")), 1)

    def test_a_meter_that_cannot_be_read_holds_the_population(self):
        import sqlite3

        with patch.object(self.house, "_sail_runway", side_effect=sqlite3.OperationalError("database is locked")):
            report = self.house._population_rule()
        self.assertEqual((report["max_population"], self.rules["max_population"]), (112, 112))
        self.assertIn("database is locked", report["rule"])

    def test_the_tick_applies_the_population_rule_when_the_caps_cannot_follow_the_search(self):
        self.runway(1.0)
        with patch.object(self.house, "_follow_the_search", side_effect=RuntimeError("a foundry that cannot be read")):
            self.house.keep_population(refill=False)
        self.assertEqual(self.rules["max_population"], 112)
        self.assertEqual(len(alerts(self.house, "warning", "could not follow the search")), 1)


class CapsBeforeTheSearchSeats(ReviewCase):
    """R2 (3) holds a desk the search closes at its members (`_follow_the_search`), in the tick's population step. The
    foundry's and the lab's steps come earlier in the same tick (and the lab's runs on its own thread), and the House
    reads each desk's niches.json cap afresh at every start: after a restart, the first tick's foundry and lab steps saw
    a closed desk's full cap, so the lab could seat one of the graduates that passed before the rule (3 for
    kalshi-crypto-15m at 15:06Z) on a desk the search closes once its members fell under that cap."""

    def test_a_closed_desks_cap_is_held_before_the_foundry_and_the_lab_take_seats(self):
        seen = []

        class Foundry(NoFoundryCards):
            def tick(inner, open_for_business=True):
                seen.append(self.house.niches[DESK].max_members)

        self.resident("first"), self.resident("second")
        base = self.house.niches[DESK].max_members
        self.assertGreater(base, 2)
        self.house.hypotheses = Foundry({DESK: f"no family on {DESK} has a positive forward record over 3 active blocks there"})
        self.house._data_cache.pop("search_closed", None)
        self.house.tick()  # the first tick after a restart: the cap is niches.json's until the search is read
        self.assertEqual(seen, [2], "held at its members before the foundry (and the lab after it) could seat anyone there")
        self.assertEqual(self.house.niches[DESK].max_members, 2)


class ProvenRecordThatCannotBeRead(ReviewCase):
    """Every waiter source of the seat queue is read under a guard ("read again on the next tick") except R3's
    `_waiting_proven`, which reads the allocator's family records, every living member's rung and fills, and the lab's
    mechanism digests. `seat_waiters` is on every seat question -- the lab's step, `_displaceable` for a desk, `enroll`,
    `_refill`, health -- and `_proven_births` runs first in every birth pass, where only a SandboxError is caught: one
    exception there stopped every birth and failed the tick ("tick failed", an error the watchdog reads) until it
    cleared."""

    def test_a_proven_record_that_cannot_be_read_stops_no_seat_question_and_no_birth_pass(self):
        idle = self.resident("idle")
        self.clock.advance(3601)
        with patch.object(self.house, "_proven_programs", side_effect=KeyError("to_rung")):
            self.assertEqual(self.house.seat_waiters(fresh=True)["proven"], [])
            self.assertEqual(self.house._weakest(self.rules, specialty=DESK, evidenced=True).id, idle.id)
            self.assertIsNone(self.house._proven_births(self.rules))
            self.house._births(self.rules)  # the rest of the birth pass runs
            self.house.seat_waiters(fresh=True)
        self.assertEqual(len(alerts(self.house, "warning", "proven famil", "KeyError")), 1, "told once an hour")


class AProvenFamilysNameFollowsItsProgram(ReviewCase):
    """The new-family rule (`_program_family`, the builder's follow-up commit) compares a child's markets and style with
    its PARENT's program now. A member that already carries a proven family's name with another program -- meriwether-
    h2d625d-2: sports-central-run-under's name on a CFB and soccer moneyline-favourites file, rung 1 at 15:06Z, no fill
    yet, its markets on the weekend's slate -- passes that test with a fix of its own moneyline file, so its research
    forks would carry the run-unders' proof into moneylines: shielded as a proven family's members from unproven
    newcomers, staked on the proven family's bunt tier at the bunt line, their settlements pooled into the record the
    family swing reads. And R3's anchor was the living member on the highest rung with a fill, the earliest born first:
    with meriwether-h2d625d dead and -2 trading, the House would breed -2's moneyline program as the proven family's."""

    def setUp(self):
        super().setUp()
        self.house.close(wait=None)  # a House with a Kalshi practice book too (test_seat_capacity's NewCodeFamilies)
        from pathlib import Path

        from league.economy import load_game
        from league.house import House, Settings
        from league.sandbox import LocalSandbox
        from league.tests.fakes import FakeBroker

        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.house = House(Path(self.dir.name) / "house-review", brokers={"alpaca-paper": self.broker,
                                                                           "kalshi-shadow": FakeBroker("kalshi-shadow", family="kalshi")},
                           sandbox=LocalSandbox(Path(self.dir.name) / "boxes-review"), alpaca_data=self.data, clock=self.clock,
                           settings=Settings(mark_every_seconds=0, research=False), game=game)
        self.rules = self.house.game["economy"]

    def sports(self, code, *, parent=None):
        agent = self.house.spawn("meriwether", "sports-central-run-under", code, parent=parent, reason="a test agent")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house.economy.grant(agent.id, "100", "test: an agent that can fork")
        return agent

    def test_a_fork_of_a_member_running_another_program_leaves_a_proven_familys_name(self):
        import hashlib

        from league.tests.test_seat_capacity import MONEYLINE_FAVOURITES, RUN_UNDER, RUN_UNDER_MAKER_FIX

        anchor = self.sports(RUN_UNDER)
        misfiled = self.sports(MONEYLINE_FAVOURITES, parent=anchor.id)  # born before the rule: the family's name, other code
        self.assertEqual(misfiled.family, "sports-central-run-under")
        with self.proven("sports-central-run-under"):
            fix = self.house.fork(misfiled, code=MONEYLINE_FAVOURITES.replace("buy a deep favourite", "rest a bid on a deep favourite"),
                                  reason="a maker fix of its own moneyline file", passed_replay=True)
            root = hashlib.sha256("sports-central-run-under|sports-moneyline-deep-favourites".encode()).hexdigest()[:6]
            self.assertEqual(fix.family, f"sports-moneyline-deep-favourites-{root}",
                             "the proven family's name stays with the program that proved it")
            same = self.house.fork(anchor, code=RUN_UNDER_MAKER_FIX, reason="a maker fix of the run-unders", passed_replay=True)
            self.assertEqual(same.family, "sports-central-run-under", "a fix of the family's own program keeps it")
        unproven = self.house.fork(misfiled, code=MONEYLINE_FAVOURITES.replace("buy a deep favourite", "buy a deeper favourite"),
                                   reason="another fix", passed_replay=True)
        self.assertEqual(unproven.family, "sports-central-run-under", "an unproven family keeps the rule as it was")

    def test_a_member_running_another_program_never_becomes_the_proven_familys_anchor(self):
        from league.tests.test_seat_capacity import MONEYLINE_FAVOURITES, RUN_UNDER
        from league.tests.test_seat_evidence import BTC

        self.rules.update(newcomer_seconds=600, proven_family_members=4)
        anchor = self.sports(RUN_UNDER)
        self.house.evaluator.promote(anchor.id, 2, "test: a bunt on real money")
        misfiled = self.sports(MONEYLINE_FAVOURITES, parent=anchor.id)
        for agent in (anchor, misfiled):
            self.buy(agent, book="kalshi-shadow", instrument=BTC)  # a fill of its own
        with self.proven("sports-central-run-under"):
            self.assertEqual([r["anchor"].id for r in self.house._proven_programs()], [anchor.id])
            self.house.kill(anchor, "evidence", "a test death")
            self.assertEqual(self.house._proven_programs(), [], "no member runs the program that proved the family")
            self.assertIsNone(self.house._proven_births(self.rules))


class StaleSeatsOnADeskThatKeepsHours(HouseCase):
    """A pin, not a fix: S3 on a desk that keeps an exchange's hours, which the builder's tests (a 24/7 crypto desk)
    never reached. S3 passes over the trading protection (`_trading_pending`: the bunt line's closed trades, or three
    sessions) once the desk's evidence clock has run and a session has closed -- but never takes a trader holding a
    position while its market is shut (scholes-23, 07:11Z Sept 23, mid-basket: the House would sell at the open what
    the agent's own exit sells there)."""

    def setUp(self):
        super().setUp()
        from league.venues import instrument_for

        self.rules = self.house.game["economy"]
        self.book = self.house.books["alpaca-paper"]
        self.spy = instrument_for("alpaca-paper", {"symbol": "SPY"})

    def at(self, stamp):
        from league.tests.test_stock_desk_seats import ts

        self.clock.now = ts(stamp)

    def fill(self, agent, stamp, *, closed=False):
        self.at(stamp)
        payload = {"book": "alpaca-paper", "symbol": "SPY", "side": "sell" if closed else "buy",
                   "quantity": "0.05", "price": "500", "source": "venue"}
        if closed:
            payload.update(realized="-0.02", flat=True)
        self.house.ledger.append("book.fill", payload, agent=agent.id)

    def stale_pick(self, desk):
        """The pick for a waiter with a winning forward window (+0.0001) against residents with no window of their own,
        the desk's evidence clock the index ETFs' at 15:06Z (19.2 h)."""
        with patch.object(self.house, "_resident_forward", return_value=None), \
                patch.object(self.house, "_forward_scorable", return_value=True), \
                patch.object(self.house, "_desk_clocks", return_value={desk: 19.2 * 3600}):
            found = self.house._weakest(self.rules, evidenced=True, newcomer=Newcomer(forward=0.0001))
        return None if found is None else found.id

    def test_s3_takes_a_stale_trader_past_its_trading_protection_but_never_one_holding_through_a_shut_market(self):
        from decimal import Decimal

        from league.book import Holding
        from league.tests.test_stock_desk_seats import FIRST_WAKE, SPY_HOURLY

        self.at("2026-09-22T22:00:00Z")
        agent = self.seated("stocks", SPY_HOURLY)
        desk = self.house.niche_of(agent)
        self.assertTrue(desk.keeps_hours(agent.needs))
        self.at(FIRST_WAKE)  # Wednesday Sept 23, the open
        self.house.ledger.append("agent.woke", {"ok": True, "offered": 1}, agent=agent.id)
        self.fill(agent, "2026-09-23T14:10:00Z")
        self.fill(agent, "2026-09-23T14:11:00Z", closed=True)  # one closed trade: short of the bunt line's record
        self.at("2026-09-24T07:00:00Z")  # 17.5 h: inside the desk's clock
        self.assertIsNone(self.stale_pick(desk.id))
        self.at("2026-09-24T09:00:00Z")  # 19.5 h and Wednesday's session closed: stale, and flat
        self.assertEqual(self.stale_pick(desk.id), agent.id)
        self.assertIsNone(self.house._weakest(self.rules, evidenced=True), "without a forward score: the trading protection")
        self.fill(agent, "2026-09-24T19:30:00Z")  # Thursday's basket, held overnight
        self.book.account(agent.id).holdings[self.spy.key] = Holding(self.spy, Decimal("0.05"), Decimal("25"))
        self.at("2026-09-25T07:11:00Z")
        self.assertIsNone(self.stale_pick(desk.id), "holding through a shut market: never, stale or not")
        self.at("2026-09-25T13:31:00Z")
        self.assertEqual(self.stale_pick(desk.id), agent.id, "the market is open: the House can sell at market")


class TwoProvenFamiliesOnOneDesk(ReviewCase):
    """`_displaceable`'s R3 hold read the owed births as desk -> family: with two proven families owed births on one desk
    the later overwrote the earlier, and the earlier family's own births were refused there ("even by a proven family's
    newcomer") until the later one had its members."""

    def test_either_owed_familys_birth_may_take_the_seat_and_no_other_family_may(self):
        self.rules.update(newcomer_seconds=600, proven_family_members=4)
        first = self.resident("first", family="first-family")
        second = self.resident("second", family="second-family")
        for agent in (first, second):
            self.house.evaluator.promote(agent.id, 2, "test: a bunt on real money")
            self.buy(agent)
        idle = self.resident("idle")
        self.clock.advance(3601)
        with self.proven("first-family", "second-family"):
            self.assertEqual(sorted(w["family"] for w in self.house.seat_waiters(fresh=True)["proven"]), ["first-family", "second-family"])
            for family in ("first-family", "second-family"):
                pick = self.house._weakest(self.rules, specialty=DESK, evidenced=True, newcomer=Newcomer(family=family, venue="alpaca"))
                self.assertEqual(pick.id if pick else None, idle.id, f"{family}'s birth may take the seat")
            self.assertIsNone(self.house._weakest(self.rules, specialty=DESK, evidenced=True,
                                                  newcomer=Newcomer(family="another", venue="alpaca")))
