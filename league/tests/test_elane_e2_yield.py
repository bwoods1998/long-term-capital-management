"""Release E2, YIELD PER DOLLAR (league/swarm/elane_yield.py): the ledger a model route keeps (requests, dollars, births),
the Train counts read from E2's records, the operator's report (with the later stages), the day's line, one route a
question with the fallback booked to the route that answered, and THE ROUTE CHOICE: the first route with no births,
the cheapest route that has produced births by default, exploration every third request until every route has its
sample (births, or requests answered or failed), then the most Train passes per dollar, smoothed, with a route never
starved; never a Validation or look outcome. Every number here is invented."""

from __future__ import annotations

import unittest

from league.swarm import elane_yield
from league.swarm.elane_train import STATE_KEY
from league.swarm.elane_yield import Route, book, book_births, choose, ledger, report, room, routes
from league.swarm.models import ModelError
from league.tests import elane_e2_fakes as fx


class YieldCase(unittest.TestCase):
    def setUp(self):
        fx.switch_on(self)
        self.clock = fx.Clock()
        self.store = fx.new_store(self, self.clock)
        self.settings = fx.settings(min_births=2, routes=["sail:pro_asap", "sail:glm_asap", "sail:k3"])
        self.routes = routes(self.settings, fx.FakeRouter())

    def spend(self, key: str, usd: float, births: int, requests: int = 1) -> None:
        for _ in range(requests):
            book(self.store, key, usd=usd / requests, known=True, purpose="births", answered=True, now=self.clock())
        book_births(self.store, key, births)

    def pick(self, turn: int) -> str:
        route, _ = choose(self.store, self.settings, self.routes, turn=turn, train_key=STATE_KEY)
        return route.key


class TheChoice(YieldCase):
    def test_no_births_yet_the_first_route(self):
        self.assertEqual([self.pick(t) for t in (0, 1)], ["sail:pro_asap", "sail:pro_asap"])
        self.assertEqual(self.pick(2), "sail:pro_asap", "exploration: the least-sampled route, list order on ties")

    def test_the_cheapest_route_that_bore_by_default_and_exploration_every_third(self):
        self.spend("sail:pro_asap", 3.0, 1, requests=2)
        self.spend("sail:glm_asap", 0.5, 1, requests=1)
        self.assertEqual(self.pick(0), "sail:glm_asap", "0.50 a request beats 1.50")
        self.assertEqual(self.pick(2), "sail:k3", "the route furthest from its sample")
        self.spend("sail:k3", 1.0, 1)
        self.assertEqual(self.pick(5), "sail:glm_asap", "fewest births, then fewest requests, then list order")

    def test_after_every_sample_the_most_train_passes_per_dollar(self):
        for key, usd in (("sail:pro_asap", 1.0), ("sail:glm_asap", 1.0), ("sail:k3", 4.0)):
            self.spend(key, usd, 2)
        for i, (key, passed) in enumerate((("sail:k3", True), ("sail:k3", True), ("sail:pro_asap", False))):
            fx.e2_family(self.store, f"f{i}", route=key, symbols=(fx.UNIVERSE[i],),
                         record={"status": "passed" if passed else "researching", "versions": {"1": {}},
                                 **({"passed_version": 1} if passed else {})})
        self.assertEqual(self.pick(0), "sail:k3", "2 passes on 4 dollars beat none")
        self.assertEqual(self.pick(2), "sail:k3", "the sample's exploration is over once sampled")

    def test_no_train_pass_anywhere_then_births_per_dollar(self):
        for key, usd in (("sail:pro_asap", 2.0), ("sail:glm_asap", 1.0), ("sail:k3", 4.0)):
            self.spend(key, usd, 2)
        self.assertEqual(self.pick(0), "sail:glm_asap")

    def test_the_choice_never_reads_a_later_stage(self):
        for key, usd in (("sail:pro_asap", 1.0), ("sail:glm_asap", 1.0), ("sail:k3", 1.0)):
            self.spend(key, usd, 2)
        fam = fx.e2_family(self.store, "won", route="sail:k3",
                           record={"status": "passed", "passed_version": 1, "versions": {"1": {}}})
        before = [self.pick(t) for t in range(4)]
        self.store.set_state(fam["id"], elane_try={"entered": True}, elane_look={"verdict": {"passed": True}})
        self.store.update_family(fam["id"], band="probe")
        other = fx.e2_family(self.store, "lost", route="sail:pro_asap", symbols=("QQQ",))
        self.store.set_state(other["id"], elane_look={"verdict": {"passed": True}})
        self.assertEqual([self.pick(t) for t in range(4)], before)

    def test_a_route_that_never_bears_is_sampled_by_its_requests(self):
        """Finding 3 of the adversarial review: a route whose answers are always cut, refused or failed (0 births) once
        held the choice in exploration for ever; at `sample_requests` it is sampled, at a yield of zero births."""
        settings = fx.settings(min_births=10, sample_requests=30)
        self.spend("sail:pro_asap", 2.0, 30, requests=40)
        self.spend("sail:glm_asap", 2.5, 25, requests=40)
        self.spend("sail:k3", 9.0, 0, requests=30)
        picks = [choose(self.store, settings, self.routes, turn=t, train_key=STATE_KEY) for t in range(300, 309)]
        self.assertTrue(all("smoothed" in why or "every route keeps being measured" in why for _, why in picks))
        self.assertEqual(sum(1 for r, _ in picks if r.key == "sail:k3"), 1, "one turn in nine, not one in three")

    def test_a_route_with_no_pass_yet_is_never_starved(self):
        """Finding 4 of the adversarial review: one pass on an expensive route beat a cheap route with none on every turn.
        Now every (explore_every x routes)-th turn measures the least-requested route, and the smoothed yield lets a
        cheap route's first pass overtake at once."""
        for key, usd in (("sail:pro_asap", 2.0), ("sail:glm_asap", 200.0), ("sail:k3", 6.0)):
            self.spend(key, usd, 10, requests=20)
        fx.e2_family(self.store, "one-pass", route="sail:glm_asap",
                     record={"status": "passed", "passed_version": 1, "versions": {"1": {}}})
        picks = {self.pick(t) for t in range(0, 1000)}
        self.assertIn("sail:pro_asap", picks, "the cheap route keeps being measured")
        fx.e2_family(self.store, "cheap-pass", route="sail:pro_asap", symbols=("QQQ",),
                     record={"status": "passed", "passed_version": 1, "versions": {"1": {}}})
        self.assertEqual(self.pick(0), "sail:pro_asap", "one pass on 2 dollars beats one on 200")

    def test_revisions_alone_never_make_a_route_sampled(self):
        # The integration review's seal-8: a family's Train revisions are booked on its birth route's row, and the
        # sample read every request, so a route with 4 births and 26 revisions was "sampled": exploration ended and the
        # ranking began on a fraction of the births the rule names.
        settings = fx.settings(min_births=10, sample_requests=30, routes=["sail:pro_asap", "sail:glm_asap"])
        candidates = routes(settings, fx.FakeRouter())
        for key in ("sail:pro_asap", "sail:glm_asap"):
            for _ in range(4):
                book(self.store, key, usd=0.10, known=True, purpose="births", answered=True, now=self.clock())
            book_births(self.store, key, 4)
            for _ in range(40):
                book(self.store, key, usd=0.01, known=True, purpose="research", answered=True, now=self.clock())
        rows = ledger(self.store)["routes"]
        self.assertEqual((rows["sail:pro_asap"]["requests"], rows["sail:pro_asap"]["requests_births"],
                          rows["sail:pro_asap"]["answered_births"]), (44, 4, 4))
        _, why = choose(self.store, settings, candidates, turn=0, train_key=STATE_KEY)
        self.assertEqual(why, "the cheapest route that has produced births", "44 requests, 4 of them births: not sampled")
        _, why = choose(self.store, settings, candidates, turn=2, train_key=STATE_KEY)
        self.assertIn("furthest from its sample of 10 births", why)
        # 30 BIRTH requests, answered or failed, do sample a route that never bears.
        for key in ("sail:pro_asap", "sail:glm_asap"):
            for _ in range(26):
                book(self.store, key, usd=0.10, known=True, purpose="births", answered=False, now=self.clock())
        _, why = choose(self.store, settings, candidates, turn=0, train_key=STATE_KEY)
        self.assertIn("every route has its sample", why)

    def test_the_cheapest_route_is_priced_on_its_birth_requests(self):
        # A 24k-token birth request and a 12k-token revision are not one price: the default is the lowest mean dollars
        # a BIRTH request, whatever the route's revisions cost.
        self.spend("sail:pro_asap", 0.60, 1, requests=2)   # 0.30 a birth request
        self.spend("sail:glm_asap", 0.40, 1, requests=1)   # 0.40 a birth request
        for _ in range(20):                                # glm's many cheap revisions would have averaged it down
            book(self.store, "sail:glm_asap", usd=0.01, known=True, purpose="research", answered=True, now=self.clock())
        self.assertEqual(self.pick(0), "sail:pro_asap")

    def test_a_claude_route_only_while_the_router_serves_its_role(self):
        settings = fx.settings(routes=["claude:architect", "sail:pro_asap"])
        self.assertEqual([r.key for r in routes(settings, fx.FakeRouter())], ["sail:pro_asap"])
        self.assertEqual([r.key for r in routes(settings, fx.FakeRouter(claude_roles=("architect",)))],
                         ["claude:architect", "sail:pro_asap"])

    def test_malformed_settings_read_their_defaults(self):
        bad = fx.settings(routes=["nope", 3], min_births=-1, usd_day="lots")
        c = elane_yield.cfg(bad)
        self.assertEqual((c["routes"], c["min_births"], c["usd_day"]),
                         (elane_yield.DEFAULTS["routes"], elane_yield.DEFAULTS["min_births"], elane_yield.DEFAULTS["usd_day"]))


class TheLedger(YieldCase):
    def test_one_route_a_question_and_the_fallback_booked_to_who_answered(self):
        def script(call):
            if call["sail_profile"] == "pro_asap":
                return ModelError("busy", billed=[{"route": "sail", "cost_usd": 0.02}])
            return {"text": "{}", "route": "sail", "model": call["sail_profile"], "cost_usd": 0.07}
        router = fx.FakeRouter(script)
        answer, route, errors = elane_yield.ask(router, self.store, self.settings, first=Route.of("sail:pro_asap"),
                                                role="architect", system="s", user="u", key="swarm:elane:test",
                                                max_output=4000, effort="medium", purpose="births", now=self.clock())
        self.assertEqual(route.key, "sail:glm_asap")
        self.assertEqual([(c["sail_profile"], c["claude"], c["openai_model"]) for c in router.calls],
                         [("pro_asap", False, None), ("glm_asap", False, None)])
        rows = ledger(self.store)["routes"]
        self.assertEqual((rows["sail:pro_asap"]["failed"], rows["sail:pro_asap"]["usd"]), (1, 0.02))
        self.assertEqual((rows["sail:glm_asap"]["answered"], rows["sail:glm_asap"]["usd_births"]), (1, 0.07))
        self.assertEqual(len(errors), 1)

    def test_a_window_fallback_is_booked_to_the_profile_that_answered(self):
        router = fx.FakeRouter(lambda call: {"text": "{}", "route": "sail", "model": "pro_asap", "cost_usd": 0.03,
                                             "sail_fallback": {"from": "k3", "to": "pro_asap", "why": "flagged"}})
        _, route, _ = elane_yield.ask(router, self.store, self.settings, first=Route.of("sail:k3"), role="architect",
                                      system="s", user="u", key="k", max_output=4000, effort="medium", purpose="research",
                                      now=self.clock())
        self.assertEqual(route.key, "sail:pro_asap")
        self.assertEqual(ledger(self.store)["routes"]["sail:pro_asap"]["usd_research"], 0.03)

    def test_a_call_that_failed_after_it_was_sent_ends_the_question_and_books_its_hold(self):
        # The swarm's meter holds what the router booked for the call (its request key); the ledger books the same, the
        # next route is NOT asked the same question, and the errors say the call may still answer.
        def script(call):
            self.store.add_spend("sail_model", 0.085, family="f", detail={"profile": call["sail_profile"], "key": call["key"],
                                                                         "desk": "f", "unsettled": "provider_poll_timeout"})
            return ModelError("sail: ProviderError: provider_poll_timeout")
        router = fx.FakeRouter(script)
        answer, route, errors = elane_yield.ask(router, self.store, self.settings, first=Route.of("sail:pro_asap"),
                                                role="elane", system="s", user="u", key="swarm:elane:train:f:1",
                                                max_output=4000, effort="medium", purpose="research", now=self.clock())
        self.assertEqual((answer, route), (None, None))
        self.assertEqual([c["sail_profile"] for c in router.calls], ["pro_asap"])
        self.assertTrue(errors[0].startswith(elane_yield.SENT_UNANSWERED))
        self.assertFalse(elane_yield.unsent(errors))
        row = ledger(self.store)["routes"]["sail:pro_asap"]
        self.assertEqual((row["failed"], row["usd"], row["unknown_cost"]), (1, 0.085, 1))
        self.assertAlmostEqual(elane_yield.booked_for(self.store, "swarm:elane:train:f:1:sail:pro_asap"), 0.085)
        self.assertEqual(elane_yield.booked_for(self.store, "swarm:elane:train:f:2:sail:pro_asap"), 0.0)
        # The timeout named with no hold on the meter (a fake Provider) ends the question the same way.
        other = fx.FakeRouter(lambda call: ModelError("sail: ProviderError: provider_transport_timeout"))
        _, _, errors = elane_yield.ask(other, self.store, self.settings, first=None, role="elane", system="s", user="u",
                                       key="swarm:elane:train:f:3", max_output=4000, effort="medium", purpose="research",
                                       now=self.clock())
        self.assertEqual(len(other.calls), 1)
        self.assertFalse(elane_yield.unsent(errors))
        # A refusal before anything was sent (no hold, no timeout) still falls to the next route, as before.
        self.assertTrue(elane_yield.unsent(["sail:pro_asap: ModelError: busy"]))

    def test_an_answer_the_asker_may_not_read_is_booked_and_the_next_route_is_asked(self):
        # The audit's rule (league/swarm/elane_train.py `review_step`): the router's window fallback answered on the
        # reviewer's model; the dollars are booked to the route that answered and the next candidate is asked.
        def script(call):
            if call["sail_profile"] == "k3_balanced":
                return {"text": "{}", "route": "sail", "model": "pro_asap", "cost_usd": 0.03,
                        "sail_fallback": {"from": "k3_balanced", "to": "pro_asap", "why": "stall"}}
            return {"text": "{}", "route": "sail", "model": call["sail_profile"], "cost_usd": 0.04}
        router = fx.FakeRouter(script)
        answer, route, errors = elane_yield.ask(
            router, self.store, self.settings, first=None, role="elane", system="s", user="u",
            key="swarm:elane:audit:f:1:0", max_output=4000, effort="medium", purpose="review", now=self.clock(),
            candidates=[Route.of("sail:k3_balanced"), Route.of("sail:glm_balanced")], book_as=lambda r: f"review:{r.key}",
            accept=lambda r: r.key != "sail:pro_asap")
        self.assertEqual(route.key, "sail:glm_balanced")
        self.assertEqual([c["sail_profile"] for c in router.calls], ["k3_balanced", "glm_balanced"])
        rows = ledger(self.store)["routes"]
        self.assertEqual((rows["review:sail:pro_asap"]["usd"], rows["review:sail:glm_balanced"]["usd"]), (0.03, 0.04))
        self.assertIn("may not read this question", errors[0])

    def test_an_unknown_bill_books_its_hold(self):
        router = fx.FakeRouter(lambda call: {"text": "{}", "route": "claude", "model": "m", "cost_usd": None,
                                             "held_usd": 0.5}, claude_roles=("architect",))
        settings = fx.settings(routes=["claude:architect"])
        elane_yield.ask(router, self.store, settings, first=Route.of("claude:architect"), role="architect", system="s",
                        user="u", key="k", max_output=4000, effort="medium", purpose="births", now=self.clock())
        row = ledger(self.store)["routes"]["claude:architect"]
        self.assertEqual((row["usd"], row["unknown_cost"]), (0.5, 1))
        self.assertEqual((router.calls[0]["role"], router.calls[0]["claude"], router.calls[0]["sail_profile"]),
                         ("architect", True, None))

    def test_a_route_no_longer_served_is_passed_over(self):
        router = fx.FakeRouter(lambda call: {"text": "{}", "route": "sail", "model": call["sail_profile"], "cost_usd": 0.01})
        _, route, _ = elane_yield.ask(router, self.store, self.settings, first=Route.of("claude:architect"),
                                      role="architect", system="s", user="u", key="k", max_output=4000, effort="medium",
                                      purpose="research", now=self.clock())
        self.assertEqual(route.key, "sail:pro_asap")
        self.assertNotIn("claude:architect", ledger(self.store)["routes"])

    def test_the_days_line(self):
        self.assertEqual(room(self.store, self.settings, self.clock()), elane_yield.DEFAULTS["usd_day"])
        book(self.store, "sail:k3", usd=7.5, known=True, purpose="research", answered=True, now=self.clock())
        self.assertAlmostEqual(room(self.store, self.settings, self.clock()), 0.5)
        self.clock.advance(86400)
        self.assertEqual(room(self.store, self.settings, self.clock()), elane_yield.DEFAULTS["usd_day"], "a new UTC day")

    def test_the_turn_counts_requests(self):
        self.assertEqual([elane_yield.next_turn(self.store) for _ in range(3)], [0, 1, 2])

    def test_the_reviews_dollars_have_rows_of_their_own(self):
        router = fx.FakeRouter(lambda call: {"text": "{}", "route": "sail", "model": call["sail_profile"], "cost_usd": 0.04})
        _, route, _ = elane_yield.ask(router, self.store, self.settings, first=None, role="elane", system="s", user="u",
                                      key="swarm:elane:review:f:1:0", max_output=4000, effort="medium", purpose="review",
                                      now=self.clock(), candidates=[Route.of("sail:k3_balanced")],
                                      book_as=lambda r: f"review:{r.key}")
        self.assertEqual(route.key, "sail:k3_balanced")
        rows = ledger(self.store)["routes"]
        self.assertEqual(rows["review:sail:k3_balanced"]["usd_review"], 0.04)
        self.assertNotIn("sail:k3_balanced", rows)
        self.assertAlmostEqual(room(self.store, self.settings, self.clock()), elane_yield.DEFAULTS["usd_day"] - 0.04)
        rep = report(self.store, self.settings, train_key=STATE_KEY)
        self.assertIn("review:sail:k3_balanced", rep["review"])
        self.assertNotIn("review:sail:k3_balanced", rep["routes"])

    def test_the_report_per_dollar(self):
        self.spend("sail:pro_asap", 2.0, 4)
        fx.e2_family(self.store, "won", record={"status": "passed", "passed_version": 1, "versions": {"1": {}}})
        rep = report(self.store, self.settings, train_key=STATE_KEY)
        row = rep["routes"]["sail:pro_asap"]
        self.assertEqual((row["births"], row["families"], row["train_passes"]), (4, 1, 1))
        self.assertEqual(row["per_usd"]["births"], 2.0)
        self.assertEqual(row["per_usd"]["train_passes"], 0.5)
        self.assertIn("A9 D3", rep["rule"])


class ThePace(YieldCase):
    """E2'S DOLLARS: a share of the swarm's Sail model line, counted apart (the integration review's loop-1 and merge-1:
    E2's dollars landed on the options researchers' hourly pace and E2 itself was held by no pace)."""

    def e2_row(self, usd: float, key: str = "swarm:elane:train:f:1:sail:pro_asap", *, kind: str = "sail_model",
               field: str = "key") -> None:
        self.store.add_spend(kind, usd, family="f", detail={field: key, "profile": "pro_asap", "desk": "f"})

    def lined(self, line, **e2) -> dict:
        return {**fx.settings(**e2), "researcher": {"sail_usd_per_hour": line, "usd_per_hour": 5}}

    def test_the_line_is_read_as_the_loop_reads_it(self):
        nan, inf = float("nan"), float("inf")
        for block, want in (({"sail_usd_per_hour": 0.34, "usd_per_hour": 5}, (0.34, True)),
                            ({"sail_usd_per_hour": None, "usd_per_hour": 5}, (5.0, True)),
                            ({"usd_per_hour": 2}, (2.0, True)), ({}, (4.0, True)), ({"sail_usd_per_hour": 0}, (0.0, True)),
                            ({"sail_usd_per_hour": "x"}, (0.0, False)), ({"sail_usd_per_hour": True}, (0.0, False)),
                            ({"sail_usd_per_hour": -1}, (0.0, False)), ({"sail_usd_per_hour": nan}, (0.0, False)),
                            ({"sail_usd_per_hour": inf}, (0.0, False)), ({"sail_usd_per_hour": [1]}, (0.0, False))):
            self.assertEqual(elane_yield.model_line({"researcher": block}), want, block)
        self.assertEqual(elane_yield.model_line({}), (4.0, True))
        self.assertEqual(elane_yield.model_line(None), (4.0, True))
        self.assertEqual(elane_yield.model_line({"researcher": "x"}), (4.0, True))

    def test_the_pace_is_a_share_of_the_line_and_the_day_never_more_than_a_day_at_it(self):
        ceiling = self.lined(20.0 * 0.4 / 24)  # the owner's ceiling: Sail $20 a day, $8.00 of it for models
        self.assertAlmostEqual(elane_yield.usd_hour(ceiling), 0.25 * 8.0 / 24)
        self.assertAlmostEqual(elane_yield.day_line(ceiling), 2.0, msg="a quarter of the day's model dollars")
        self.assertEqual(elane_yield.cfg(ceiling)["usd_day"], 8.0, "the captain's line is a cap above it, unchanged")
        floor = self.lined(4.0 * 0.4 / 24)  # the budget's floor tightens E2 with the line
        self.assertAlmostEqual(elane_yield.day_line(floor), 0.4)
        self.assertAlmostEqual(elane_yield.day_line(self.lined(20.0 * 0.4 / 24, usd_day=0.5)), 0.5, msg="usd_day under it binds")
        self.assertAlmostEqual(elane_yield.day_line(self.lined(20.0 * 0.4 / 24, pace_share=0.5)), 4.0)
        self.assertAlmostEqual(elane_yield.usd_hour(ceiling, 1.0), 0.25, msg="the loop hands in its own reading of the line")
        for raw in (0.51, -0.1, "x", True, None):
            self.assertEqual(elane_yield.cfg(self.lined(1.0, pace_share=raw))["pace_share"], 0.25, raw)

    def test_only_e2s_own_rows_count_and_they_leave_the_hour(self):
        s = self.lined(0.4)  # E2's pace: 0.10 an hour, 2.40 a day
        self.store.add_spend("sail_model", 5.0, family="opt", detail={"key": "swarm:opt-family:c1:m0:0"})
        self.store.add_spend("sail_model", 5.0, family="swarm", detail={"key": "swarm:architect:1791030654"})
        self.store.add_spend("gym_box", 5.0, detail={"key": "swarm:elane:never-a-box"})
        self.assertEqual(elane_yield.spent_since(self.store, self.clock() - 3600), 0.0)
        self.assertIsNone(elane_yield.hold(self.store, s, self.clock()))
        self.e2_row(0.04)
        self.e2_row(0.03, "swarm:elane:audit:f:1:0:sail:k3_balanced:fallback:pro_asap")  # a window fallback's key
        self.assertIsNone(elane_yield.hold(self.store, s, self.clock()), "0.07 of 0.10")
        self.e2_row(0.02, "swarm:elane:births:9:claude:architect", kind="claude", field="hold")
        self.e2_row(0.02, "swarm:elane:births:8:openai:m", kind="openai", field="settles")
        self.assertAlmostEqual(elane_yield.spent_since(self.store, self.clock() - 3600), 0.11)
        self.assertAlmostEqual(elane_yield.spent_since(self.store, self.clock() - 3600, ["sail_model"]), 0.07)
        pace = elane_yield.pace(self.store, s, self.clock())
        self.assertEqual((pace["paused"], pace["limit_usd_per_hour"], pace["spent_last_hour_usd"]), (True, 0.1, 0.11))
        held = elane_yield.hold(self.store, s, self.clock())
        self.assertIn("pace", held)
        self.assertNotEqual(held, elane_yield.DAY_SPENT)
        self.clock.advance(3601)
        self.assertIsNone(elane_yield.hold(self.store, s, self.clock()), "the hour passed: E2 may ask again")
        self.assertAlmostEqual(room(self.store, s, self.clock()), 2.4 - 0.11, msg="the day still counts them")

    def test_the_day_counts_what_the_swarm_booked_for_a_call_the_ledger_never_heard_of(self):
        # A hold the router booked for a call that failed after it was sent (the review's loop-2): no answer was booked in
        # the ledger, the swarm's meter has the row, and E2's day is the larger of the two.
        s = self.lined(1.0, usd_day=0.2)
        book(self.store, "sail:k3", usd=0.05, known=True, purpose="research", answered=True, now=self.clock())
        self.assertAlmostEqual(elane_yield.spent_today(self.store, self.clock()), 0.05, msg="a fake router: the ledger alone")
        self.e2_row(0.08, "swarm:elane:train:f:2:sail:k3")
        self.e2_row(0.09, "swarm:elane:train:f:3:sail:pro_asap")
        self.assertAlmostEqual(elane_yield.spent_today(self.store, self.clock()), 0.17)
        self.assertAlmostEqual(room(self.store, s, self.clock()), 0.03)
        self.e2_row(0.03, "swarm:elane:train:f:4:sail:glm_asap")
        self.assertEqual(elane_yield.hold(self.store, s, self.clock()), elane_yield.DAY_SPENT)
        self.clock.advance(86400)
        self.assertIsNone(elane_yield.hold(self.store, s, self.clock()), "a new UTC day")

    def test_no_share_or_an_unreadable_line_asks_nothing(self):
        for s in (self.lined(0.4, pace_share=0.0), self.lined("x"), self.lined(0.0)):
            self.assertEqual(elane_yield.usd_hour(s), 0.0)
            self.assertIsNotNone(elane_yield.hold(self.store, s, self.clock()))

    def test_the_report_names_the_line_e2_is_held_to(self):
        rep = report(self.store, self.lined(20.0 * 0.4 / 24), train_key=STATE_KEY)
        self.assertEqual((rep["usd_day"], rep["day_line"], rep["pace_share"]), (8.0, 2.0, 0.25))
        self.assertAlmostEqual(rep["usd_hour"], 0.083333, places=6)


if __name__ == "__main__":
    unittest.main()
