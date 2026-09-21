"""The gateway's monthly frontier line, read by the House, and what each tier still pays for.

Measured Sept 21, 2026: the campaign believed $77 of OpenAI allowance remained while the
gateway's month had $40, and timed-out calls kept their worst case there. Cheap research and the
unearned roles would have spent the last of it and left nothing for the audits promotion needs."""

from __future__ import annotations

import io
import json
import unittest
from decimal import Decimal
from types import SimpleNamespace

from league.fast_research import PROFILE, ResearchRouter
from league.frontier import TIER_ROLES, FrontierMonth, frontier_tier
from league.tests.fakes import Clock
from league.tests.test_house import HouseCase

RESERVE = {"earned_usd": "20", "code_roles_usd": "8"}


class Health:
    def __init__(self, body):
        self.body, self.calls = body, 0

    def __call__(self, request, timeout=None):
        self.calls += 1
        if isinstance(self.body, Exception):
            raise self.body
        return io.BytesIO(json.dumps(self.body).encode())


class FrontierMonthTest(unittest.TestCase):
    def test_remaining_is_the_cap_less_the_spend_and_is_cached(self):
        clock = Clock()
        opener = Health({"kill_switch": False, "frontier": {"month": "2026-09", "spent_usd": "133.80", "cap_usd": "174.00"}})
        month = FrontierMonth("https://gw.test", lambda: "t" * 20, opener=opener, clock=clock)
        self.assertEqual(month.remaining(), Decimal("40.20"))
        month.remaining()
        self.assertEqual(opener.calls, 1)
        clock.advance(61)
        month.remaining()
        self.assertEqual(opener.calls, 2)

    def test_an_unreadable_gateway_is_unknown_never_zero(self):
        for body in (OSError("down"), {"frontier": {}}, {"frontier": {"spent_usd": "x", "cap_usd": "1"}}):
            month = FrontierMonth("https://gw.test", lambda: "t" * 20, opener=Health(body), clock=Clock())
            self.assertIsNone(month.remaining())

    def test_tiers(self):
        self.assertEqual(frontier_tier(None, RESERVE), "all")
        self.assertEqual(frontier_tier(Decimal("40"), RESERVE), "all")
        self.assertEqual(frontier_tier(Decimal("19.99"), RESERVE), "earned")
        self.assertEqual(frontier_tier(Decimal("7.99"), RESERVE), "audits")
        self.assertEqual(frontier_tier(Decimal("0"), None), "all")
        self.assertIsNone(TIER_ROLES["all"])
        self.assertEqual(TIER_ROLES["earned"], {"architect", "toolsmith"})
        self.assertEqual(TIER_ROLES["audits"], set())


class RouterTest(unittest.TestCase):
    def test_a_luna_agent_runs_on_sail_once_the_month_is_kept(self):
        tier = {"now": "all"}
        router = ResearchRouter(None, None, {"enabled": True, "fraction": 1, "cohort": "c"}, tier=lambda: tier["now"])
        agent = SimpleNamespace(id="a1")
        settings = {"profile": "pro_flex"}
        self.assertEqual(router.settings_for(agent, settings)["profile"], PROFILE)
        tier["now"] = "earned"
        self.assertEqual(router.settings_for(agent, settings), settings)


class Month:
    def __init__(self, value):
        self.value = value

    def remaining(self):
        return self.value


class HouseTierTest(HouseCase):
    def test_a_tier_change_is_told_once(self):
        self.house.game["frontier_reserve"] = RESERVE
        self.house.frontier_month = Month(Decimal("40"))
        self.assertEqual(self.house.frontier_tier(), "all")
        self.house.frontier_month.value = Decimal("15")
        self.assertEqual(self.house.frontier_tier(), "earned")
        self.assertEqual(self.house.frontier_tier(), "earned")
        alerts = [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if "frontier month" in e.payload.get("text", "")]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["level"], "warning")
        self.assertIn("$15.00", alerts[0]["text"])

    def test_without_a_month_reader_everything_runs(self):
        self.house.frontier_month = None
        self.assertEqual(self.house.frontier_tier(), "all")


if __name__ == "__main__":
    unittest.main()
