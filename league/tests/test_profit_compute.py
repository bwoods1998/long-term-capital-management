"""Profit-indexed compute: the House's OpenAI line mirrors the gateway's profit-indexed month.

The gateway raises its monthly OpenAI cap by a share of the verified profit on the real accounts,
which it reads through its own venue keys (gateway/lib/equity.mjs), and reports the cap in force
beside the configured one in `/v1/health`. The House's own line is raised by exactly that raise,
never more, and falls back to the configured line when the raise falls or cannot be read.
"""

from __future__ import annotations

import io
import json
import unittest
from decimal import Decimal

from league.frontier import FrontierMonth
from league.overnight import load_policy
from league.tests.fakes import Clock
from league.tests.test_house import HouseCase
from league.tests.test_phase1 import PhaseCase


class Health:
    def __init__(self, frontier):
        self.frontier, self.calls = frontier, 0

    def __call__(self, request, timeout=None):
        self.calls += 1
        if isinstance(self.frontier, Exception):
            raise self.frontier
        return io.BytesIO(json.dumps({"frontier": self.frontier}).encode())


INDEXED = {"month": "2026-09", "spent_usd": "100.00", "cap_usd": "404.00", "base_cap_usd": "374.00",
           "profit_index": {"bonus_usd": "30.00", "equity_usd": "1117.75", "baseline_usd": "1017.75"}}


class TheGatewaysRaise(unittest.TestCase):
    def month(self, frontier, clock=None):
        return FrontierMonth("https://gw.test", lambda: "t" * 20, opener=Health(frontier), clock=clock or Clock())

    def test_the_raise_is_the_cap_in_force_less_the_configured_month(self):
        month = self.month(INDEXED)
        self.assertEqual(month.remaining(), Decimal("304.00"))
        self.assertEqual(month.profit_bonus(), Decimal("30.00"))
        self.assertEqual(month.opener.calls, 1)  # one reading serves both

    def test_a_gateway_that_does_not_index_or_cannot_be_read_raises_nothing(self):
        self.assertIsNone(self.month({"spent_usd": "100", "cap_usd": "374"}).profit_bonus())
        self.assertIsNone(self.month(OSError("down")).profit_bonus())
        self.assertIsNone(self.month({**INDEXED, "base_cap_usd": "x"}).profit_bonus())
        self.assertEqual(self.month({**INDEXED, "cap_usd": "374.00"}).profit_bonus(), Decimal("0"))


class TheHouseLine(PhaseCase):
    def burst(self):
        guard = self.budget()
        policy = load_policy()
        policy["caps_usd"] = {"sail": "2", "openai": "3"}
        guard.activate_burst("night", policy)
        return guard

    def test_the_line_rises_and_falls_with_the_gateways_raise_and_never_by_more(self):
        guard = self.burst()
        self.assertEqual(guard.remaining("openai"), Decimal("3"))
        guard.mirror_gateway_bonus("openai", Decimal("30.00"))
        self.assertEqual(guard.remaining("openai"), Decimal("33"))
        self.assertEqual(guard.burst()["gateway_bonus_usd"], {"openai": "30"})
        self.assertEqual(guard.remaining("sail"), Decimal("2"))  # Sail is prepaid: never indexed
        guard.reserve("r1", "foundation-review", "20")
        self.assertEqual(guard.remaining("openai"), Decimal("13"))
        # Profit falls: the line falls with it, and what was committed stays committed.
        guard.mirror_gateway_bonus("openai", "5")
        self.assertEqual(guard.remaining("openai"), Decimal("0"))
        self.assertEqual(guard.report()["burst"]["committed_usd"]["openai"], "20")
        with self.assertRaises(ValueError):
            guard.mirror_gateway_bonus("sail", "5")
        with self.assertRaises(ValueError):
            guard.mirror_gateway_bonus("openai", "-1")

    def test_a_raise_the_gateway_stops_reporting_lapses(self):
        guard = self.burst()
        guard.mirror_gateway_bonus("openai", "10")
        self.now[0] += 200
        guard.mirror_gateway_bonus("openai", "10")  # unchanged and fresh: not stamped again
        self.now[0] += 200
        guard.mirror_gateway_bonus("openai", "10")  # five minutes on: stamped again
        self.now[0] += guard.GATEWAY_BONUS_SECONDS
        self.assertEqual(guard.remaining("openai"), Decimal("13"))
        self.now[0] += 1
        self.assertEqual(guard.remaining("openai"), Decimal("3"), "no reading for half an hour: the configured line")
        reopened = self.budget()
        self.assertEqual(reopened.gateway_bonus("openai"), 0)


class TheHouseReadsIt(HouseCase):
    def test_the_house_mirrors_the_raise_and_governs_by_the_nearer_line(self):
        from league.campaigns import CampaignBudget
        from league.tests.test_phase1 import policy

        guard = CampaignBudget(self.house.root / "campaigns-test.sqlite", policy(), clock=self.clock)
        self.addCleanup(guard.close)
        burst = load_policy()
        burst["caps_usd"] = {"sail": "2", "openai": "3"}
        guard.activate_burst("night", burst)
        self.house.campaigns = guard
        self.house.frontier_month = FrontierMonth("https://gw.test", lambda: "t" * 20, opener=Health(INDEXED), clock=self.clock)
        # The gateway has $304 left; the House's line is $3 plus the gateway's $30 raise.
        self.assertEqual(self.house.frontier_remaining(), Decimal("33"))
        self.assertEqual(guard.gateway_bonus("openai"), 30_000_000)
        # A gateway that no longer indexes: the raise is mirrored as nothing.
        self.house.frontier_month = FrontierMonth("https://gw.test", lambda: "t" * 20,
                                                  opener=Health({**INDEXED, "cap_usd": "374.00"}), clock=self.clock)
        self.clock.advance(31)
        self.assertEqual(self.house.frontier_remaining(), Decimal("3"))


if __name__ == "__main__":
    unittest.main()
