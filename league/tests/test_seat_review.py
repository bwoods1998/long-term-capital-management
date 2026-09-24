"""The adversarial review of R2 and R3 (#276, the close-the-gaps run, Sept 24, 2026): what the seat market's capacity
and the proven family's births could do to a live floor of 112-128 agents, each a scenario that failed before its fix.
"""
from __future__ import annotations

from unittest.mock import patch

from league.house import Newcomer
from league.tests.test_house import BUYER
from league.tests.test_hypotheses import FoundryCase
from league.tests.test_lab import KNOB, LabCase
from league.tests.test_seat_capacity import NoFoundryCards
from league.tests.test_seat_evidence import DESK, EvidenceCase
from league.tests.test_seat_market import alerts


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
