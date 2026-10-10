"""Release E2, YIELD PER DOLLAR (league/swarm/elane_yield.py): the ledger a model route keeps (requests, dollars, births),
the Train counts read from E2's records, the operator's report (with the later stages), the day's line, one route a
question with the fallback booked to the route that answered, and THE ROUTE CHOICE: the first route with no births,
the cheapest route that has produced births by default, exploration every third request until every route has its
sample, then the most Train passes per dollar; never a Validation or look outcome. Every number here is invented."""

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
        self.assertEqual(self.pick(5), "sail:pro_asap", "fewest births, then list order")

    def test_after_every_sample_the_most_train_passes_per_dollar(self):
        for key, usd in (("sail:pro_asap", 1.0), ("sail:glm_asap", 1.0), ("sail:k3", 4.0)):
            self.spend(key, usd, 2)
        for i, (key, passed) in enumerate((("sail:k3", True), ("sail:k3", True), ("sail:pro_asap", False))):
            fx.e2_family(self.store, f"f{i}", route=key, symbols=(fx.UNIVERSE[i],),
                         record={"status": "passed" if passed else "researching", "versions": {"1": {}},
                                 **({"passed_version": 1} if passed else {})})
        self.assertEqual(self.pick(0), "sail:k3", "2 passes on 4 dollars beat none")
        self.assertEqual(self.pick(2), "sail:k3", "no exploration once sampled")

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

    def test_the_report_per_dollar(self):
        self.spend("sail:pro_asap", 2.0, 4)
        fx.e2_family(self.store, "won", record={"status": "passed", "passed_version": 1, "versions": {"1": {}}})
        rep = report(self.store, self.settings, train_key=STATE_KEY)
        row = rep["routes"]["sail:pro_asap"]
        self.assertEqual((row["births"], row["families"], row["train_passes"]), (4, 1, 1))
        self.assertEqual(row["per_usd"]["births"], 2.0)
        self.assertEqual(row["per_usd"]["train_passes"], 0.5)
        self.assertIn("A9 D3", rep["rule"])


if __name__ == "__main__":
    unittest.main()
