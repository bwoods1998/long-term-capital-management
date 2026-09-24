"""OpenAI's meter is the gateway's frontier month, and stale OpenAI holds are absorbed into it.

Measured Sept 24, 2026 (01:34Z): the House's campaigns.sqlite held 49 OpenAI commitments with no
settled cost and no linked response, $98.36 in all (21 aged 6-24 h, $26.36; 28 older, $72.01).
They counted as spend, so the House's line read $7.94 while the gateway's month had $13.54 left,
and the frontier tier fell to "audits". The gateway, which made those calls, had already counted
each one on its month: at its metered cost, or at its whole worst case when the call failed.
`campaigns.json` `meter_required` was ["sail"], so `absorb_stale` never touched them.

Three facts from that snapshot shape these tests:
- the House booked OpenAI calls at its ceiling prices until Sept 23, so its settled sum since the
  burst ($495.35) was ABOVE the gateway's whole September ($402.96): "the meter must dominate the
  settled sum" can only be checked from a point where both are in the gateway's own prices;
- three of the holds (`external-pilot:typesafe:*`, $20) are Jev's retained backing, which the
  gateway's frontier month never sees: they are never absorbed into it;
- the gateway's month falls when a call settles below its worst case, and starts at zero on the 1st.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

from league.campaigns import CampaignBudget, CampaignClosed, CampaignPacer, load_policy
from league.frontier import FrontierMonth
from league.overnight import load_policy as burst_policy
from league.tests.test_house import HouseCase
from league.tests.test_phase1 import policy

HOUR = 3600.0
SIX_HOURS = 6 * HOUR
RESERVE = {"earned_usd": "20", "code_roles_usd": "8"}


def stamp(text: str) -> float:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def rules(*meters: str) -> dict:
    value = policy()
    value["meter_required"] = list(meters)
    return value


def night(openai: str = "40") -> dict:
    value = burst_policy()
    value["caps_usd"] = {"sail": "2", "openai": openai}
    return value


class Gateway:
    """`GET /v1/health` as the House reads it: the `frontier` block, or an outage."""

    def __init__(self, frontier):
        self.frontier, self.calls = frontier, 0

    def __call__(self, request, timeout=None):
        self.calls += 1
        if isinstance(self.frontier, Exception):
            raise self.frontier
        return io.BytesIO(json.dumps({"kill_switch": False, "frontier": self.frontier}).encode())


class Floor(unittest.TestCase):
    """A campaign whose history happened while only Sail was metered, as on production, and which is
    then reopened with OpenAI metered too (the recorded policy migration)."""

    START = "2026-09-24T01:00:00"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "campaigns.sqlite"
        self.now = [stamp(self.START)]
        self.guard = self.open("sail")
        self.guard.observe_balance("sail", "100.00")
        self.guard.activate_burst("night", night())

    def clock(self):
        return self.now[0]

    def open(self, *meters):
        guard = CampaignBudget(self.path, rules(*meters), clock=self.clock)
        self.addCleanup(guard.close)
        return guard

    def advance(self, seconds):
        self.now[0] += seconds
        self.guard.observe_balance("sail", "100.00")  # Sail stays read, as on the tick

    def call(self, ident, hold, cost=None):
        self.assertTrue(self.guard.reserve(ident, "foundation-review", hold))
        if cost is not None:
            self.guard.settle(ident, cost)

    def metered(self):
        """Reopen with OpenAI metered, as the deploy after Sept 24, 2026 does."""
        self.guard = self.open("sail", "openai")
        return self.guard

    def read(self, spent, settled=None, month="2026-09", previous=None, cap=None):
        return self.guard.observe_month("openai", month, spent, settled=settled, previous=previous, cap=cap)

    def history(self):
        """Jev's backing, a call booked above the gateway's price, two calls that never answered,
        and a younger one."""
        self.assertTrue(self.guard.reserve("external-pilot:typesafe:backing", "foundation-review", "10.00"))
        self.call("frontier:ceiling", "12.00", "10.00")  # the gateway metered it at $4
        self.call("frontier:lost-1", "2.00")             # timed out: the gateway kept its $2
        self.call("frontier:lost-2", "3.00")             # cut off by a restart: the gateway settled $0.50
        self.advance(HOUR)
        self.call("frontier:young", "1.50")              # an hour younger; the gateway kept its $1.50

    def anchored(self):
        """Metered, read once (the anchor), then one verified call settles after it and the
        gateway's settled figure grows by exactly its cost."""
        self.history()
        self.advance(5.5 * HOUR)
        g = self.metered()
        self.read("8.00", "8.00")  # $4 + $2 + $0.50 + $1.50 at the gateway's prices
        self.call("frontier:after", "1.00", "0.30")
        self.read("8.30", "8.30")
        return g


class PolicyMigration(Floor):
    def test_the_real_policy_meters_openai(self):
        self.assertEqual(load_policy()["meter_required"], ["sail", "openai"])

    def test_adding_a_meter_is_an_amendment_on_the_record_and_a_rollback_still_opens(self):
        pinned = self.guard.db.execute("SELECT policy, started FROM phase").fetchone()
        guard = self.metered()
        self.assertEqual(guard.started, pinned[1], "the phase's clock is never reset")
        self.assertEqual(guard.policy["meter_required"], ["sail", "openai"])
        self.assertEqual(guard.db.execute("SELECT policy FROM phase").fetchone()[0], pinned[0],
                         "the pinned policy is never rewritten")
        rows = guard.db.execute("SELECT old_policy, new_policy, why FROM phase_amendments").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0][0])["meter_required"], ["sail"])
        self.assertEqual(json.loads(rows[0][1])["meter_required"], ["sail", "openai"])
        self.assertIn("openai", rows[0][2])
        self.open("sail", "openai")  # the same policy again: nothing more to record
        self.assertEqual(guard.db.execute("SELECT COUNT(*) FROM phase_amendments").fetchone()[0], 1)
        # A rollback to the release before: its campaigns.json and code open the same store.
        old = self.open("sail")
        self.assertEqual(old.policy["meter_required"], ["sail"])

    def test_any_other_change_still_needs_the_owner(self):
        changed = rules("sail")
        changed["duration_hours"] = 72
        with self.assertRaises(CampaignClosed):
            CampaignBudget(self.path, changed, clock=self.clock)
        with self.assertRaises(CampaignClosed):
            CampaignBudget(self.path, rules(), clock=self.clock)  # dropping a meter is not a migration
        both = rules("sail", "openai")
        both["daily_caps_usd"] = {"sail": "9", "openai": "9"}
        with self.assertRaises(CampaignClosed):
            CampaignBudget(self.path, both, clock=self.clock)  # a meter added beside another change


class MonthMeter(Floor):
    def test_a_settle_down_within_the_month_moves_nothing_backwards_and_never_latches(self):
        g = self.metered()
        self.assertFalse(g.ready("openai"), "metered now: no reading, no OpenAI spending")
        self.assertTrue(self.read("100.00", "99.00"))
        self.assertTrue(g.ready("openai"))
        self.read("104.00", "99.00")   # a call in flight at its worst case
        self.read("101.00", "100.00")  # it settled at $1 of its $5: the month fell $3
        self.assertTrue(g.ready("openai"), "a settle-down is not a vendor reset")
        self.assertEqual(g.db.execute("SELECT failed FROM meter_health WHERE id='openai'").fetchone()[0], 0)
        self.assertEqual(g.db.execute("SELECT latest FROM meter WHERE id='openai'").fetchone()[0], 104_000_000)
        month = g.month_meter("openai")
        self.assertEqual((month["high_usd"], month["settled_total_usd"]), ("104", "100"))

    def test_a_month_rollover_carries_the_months_final_and_keeps_counting(self):
        g = self.metered()
        self.read("402.96", "400.00")
        covered = g.month_meter("openai")["covers_from"]
        self.assertEqual(covered, stamp("2026-09-01T00:00:00"))
        self.now[0] = stamp("2026-10-01T00:05:00")
        self.read("1.00", "0.50", month="2026-10",
                  previous={"month": "2026-09", "spent_usd": "403.50", "settled_usd": "403.000000"})
        self.assertTrue(g.ready("openai"), "the 1st of the month is not a vendor reset")
        self.assertEqual(g.db.execute("SELECT latest FROM meter WHERE id='openai'").fetchone()[0], 404_500_000)
        month = g.month_meter("openai")
        self.assertEqual((month["month"], month["carried_usd"], month["covers_from"]), ("2026-10", "403.5", covered))
        self.assertEqual(month["settled_total_usd"], "403.5", "the settled figure carries its final too")
        # The check starts again in the new month: a call in flight at midnight is refused its settle
        # by the gateway (its month has ended) while the House may settle it.
        self.assertEqual(month["anchor"]["at"], self.now[0])
        self.read("0.40", "0.40", month="2026-10")  # a settle-down in the new month
        self.assertEqual(g.db.execute("SELECT latest FROM meter WHERE id='openai'").fetchone()[0], 404_500_000)

    def test_a_rollover_the_gateway_cannot_close_moves_the_coverage_forward(self):
        g = self.metered()
        self.read("402.96", "400.00")
        self.now[0] = stamp("2026-10-01T00:05:00")
        self.read("1.00", "0.50", month="2026-10")  # no final for September: its last minutes are unknown
        month = g.month_meter("openai")
        self.assertEqual(month["carried_usd"], "402.96")
        self.assertEqual(month["covers_from"], stamp("2026-10-01T00:00:00"))
        self.assertEqual(month["anchor"]["at"], self.now[0], "the check starts again from this reading")
        self.assertEqual(g.db.execute("SELECT latest FROM meter WHERE id='openai'").fetchone()[0], 403_960_000)
        rows = g.db.execute("SELECT evidence FROM meter_reconciliations WHERE kind='openai'").fetchall()
        self.assertTrue(any('"final_reported":false' in r[0] for r in rows))

    def test_an_older_month_is_no_reading_and_a_garbled_one_is_refused(self):
        g = self.metered()
        self.read("10.00", "9.00")
        self.now[0] += 170
        self.assertFalse(self.read("9.00", "9.00", month="2026-08"))
        for month in ("2026-9", "Sept", ""):
            with self.assertRaises(ValueError):
                self.read("11.00", "10.00", month=month)
        with self.assertRaises(ValueError):
            self.read("-1")
        self.now[0] += 11
        self.assertFalse(g.ready("openai"), "only a real reading keeps the meter fresh")

    def test_an_unread_gateway_stops_openai_spending_and_nothing_else(self):
        g = self.metered()
        self.read("10.00", "9.00")
        self.call("frontier:a", "1.00", "0.40")
        self.advance(181)
        self.assertFalse(g.ready("openai"))
        with self.assertRaises(CampaignClosed):
            g.reserve("frontier:b", "foundation-review", "1.00")
        self.assertTrue(g.reserve("sail:x", "baseline-research", "0.10"), "Sail work goes on")
        pacer = CampaignPacer(None, g, clock=self.clock)
        self.assertFalse(pacer.may_spend("openai"))
        self.assertTrue(pacer.may_spend("sail"))

    def test_the_first_reading_moves_no_line(self):
        self.call("frontier:ceiling", "12.00", "10.00")  # booked at the House's ceiling prices
        self.call("frontier:lost", "3.00")               # no answer: held
        before = self.guard.remaining("openai")
        g = self.metered()
        self.read("8.00", "7.50")  # the gateway metered the same calls at less
        self.assertEqual(g.remaining("openai"), before)
        self.assertEqual(g.remaining("openai"), Decimal("40") - Decimal("10") - Decimal("3"))

    def test_a_stale_meter_is_read_again_before_a_reservation(self):
        g = self.metered()
        gateway = Gateway({"month": "2026-09", "spent_usd": "10.00", "settled_usd": "9.000000", "cap_usd": "400.00"})
        month = FrontierMonth("https://gw.test", lambda: "t" * 20, opener=gateway, clock=self.clock, meter=g)
        self.assertEqual(month.remaining(), Decimal("390.00"))
        self.assertTrue(g.ready("openai"))
        self.advance(30)
        self.assertTrue(g.reserve("frontier:1", "foundation-review", "1.00"), "fresh: no new reading")
        self.assertEqual(gateway.calls, 1)
        self.advance(170)  # 200 s since the last reading: read again first, not refused
        self.assertTrue(g.reserve("frontier:2", "foundation-review", "1.00"))
        self.assertEqual(gateway.calls, 2)
        gateway.frontier = OSError("down")
        self.advance(200)
        with self.assertRaises(CampaignClosed):
            g.reserve("frontier:3", "foundation-review", "1.00")
        self.assertEqual(gateway.calls, 3)


class StaleOpenAIHolds(Floor):
    def test_holds_older_than_six_hours_are_released_when_the_meter_dominates(self):
        g = self.anchored()
        self.advance(0.3 * HOUR)  # the two lost calls are 6.8 h old; the young one 5.8 h
        self.read("8.30", "8.30")
        before = g.remaining("openai")
        out = g.absorb_stale("openai", older_than_seconds=SIX_HOURS, evidence={"by": "test"})
        self.assertEqual((out["absorbed"], out["usd"]), (2, "5"))
        self.assertEqual(g.remaining("openai") - before, Decimal("5"))
        pending = {r[0] for r in g.db.execute("SELECT id FROM commitments WHERE cost IS NULL")}
        self.assertEqual(pending, {"external-pilot:typesafe:backing", "frontier:young"})
        evidence = json.loads(g.db.execute(
            "SELECT evidence FROM cost_reconciliations WHERE id='absorbed:frontier:lost-1'").fetchone()[0])
        self.assertEqual(evidence["meter"], "the gateway's frontier month")
        self.assertEqual(evidence["check"]["house_settled_since_micro_usd"], 300_000)
        self.assertEqual(evidence["check"]["gateway_settled_growth_micro_usd"], 300_000)
        self.assertEqual(evidence["reserved_micro_usd"], 2_000_000)
        self.assertEqual(evidence["covers_from"], stamp("2026-09-01T00:00:00"))
        self.assertEqual(evidence["by"], "test")
        self.assertEqual(g.absorb_stale("openai", older_than_seconds=SIX_HOURS)["absorbed"], 0, "idempotent")

    def test_nothing_is_released_before_the_meter_has_counted_a_settled_call(self):
        self.history()
        self.advance(6.5 * HOUR)
        g = self.metered()
        self.read("8.00", "8.00")
        out = g.absorb_stale("openai", older_than_seconds=SIX_HOURS)
        self.assertEqual(out["absorbed"], 0)
        self.assertTrue(out["retry"])
        self.call("frontier:refused", "1.00", "0")  # a refusal settles at $0: still nothing to compare
        self.assertEqual(g.absorb_stale("openai", older_than_seconds=SIX_HOURS)["absorbed"], 0)

    def test_nothing_is_released_while_the_gateways_settled_figure_lags_the_house(self):
        self.history()
        self.advance(6.5 * HOUR)
        g = self.metered()
        self.read("8.00", "8.00")
        self.call("frontier:after", "1.00", "0.30")
        self.read("8.30", "8.10")  # the gateway settled $0.10 while the House settled $0.30
        out = g.absorb_stale("openai", older_than_seconds=SIX_HOURS)
        self.assertEqual(out["absorbed"], 0)
        self.assertFalse(out.get("retry"))
        self.assertIn("less than", out["why"])

    def test_nothing_is_released_while_the_meter_is_stale(self):
        g = self.anchored()
        self.advance(0.3 * HOUR)
        self.assertEqual(g.absorb_stale("openai", older_than_seconds=SIX_HOURS)["why"], "the meter is not healthy")

    def test_a_gateway_that_reports_no_settled_figure_releases_nothing(self):
        self.history()
        self.advance(6.5 * HOUR)
        g = self.metered()
        self.read("8.00")
        self.call("frontier:after", "1.00", "0.30")
        self.read("8.30")
        out = g.absorb_stale("openai", older_than_seconds=SIX_HOURS)
        self.assertEqual(out["absorbed"], 0)
        self.assertTrue(out["retry"])
        self.assertIn("settled figure", out["why"])

    def test_jevs_backing_is_never_absorbed_and_its_cost_is_never_hidden_in_the_meter(self):
        g = self.anchored()
        g.settle("external-pilot:typesafe:backing", "6.00")  # Jev billed $6, which the month never sees
        self.read("30.00", "30.00")                            # the month now dominates what the House settled
        used = Decimal(g.report()["burst"]["committed_usd"]["openai"])
        # max(settled frontier $10.30, measured $30) + Jev's $6 + the three holds' $6.50
        self.assertEqual(used, Decimal("30") + Decimal("6") + Decimal("6.5"))

    def test_the_report_shows_the_lines_arithmetic(self):
        g = self.anchored()
        meter = g.report()["meters"]["openai"]
        self.assertTrue(meter["ready"])
        self.assertEqual(meter["line"]["cap_usd"], "40")
        self.assertEqual(meter["line"]["settled_usd"], "10.3")
        self.assertEqual(meter["line"]["measured_usd"], "8.3")
        self.assertEqual(meter["line"]["unmetered_settled_usd"], "0")
        self.assertEqual(meter["line"]["before_meter_usd"], "0")
        self.assertEqual(meter["line"]["pending_usd"], "16.5")
        self.assertEqual(meter["line"]["remaining_usd"], str(g.remaining("openai")))
        self.assertEqual(g.remaining("openai"), Decimal("40") - Decimal("10.3") - Decimal("16.5"))
        self.assertEqual(meter["month"]["month"], "2026-09")
        self.assertIsNotNone(meter["month"]["anchor"])


class HoldsBeforeTheMeterCovers(Floor):
    START = "2026-09-30T20:00:00"

    def test_holds_from_a_month_the_meter_never_read_stay_held(self):
        self.call("frontier:september", "2.00")  # 20:00Z Sept 30
        self.now[0] = stamp("2026-10-01T02:30:00")
        self.guard.observe_balance("sail", "100.00")
        g = self.metered()
        self.read("0.50", "0.50", month="2026-10")  # the first reading is October's
        self.call("frontier:after", "1.00", "0.30")
        self.read("0.80", "0.80", month="2026-10")
        out = g.absorb_stale("openai", older_than_seconds=SIX_HOURS)
        self.assertEqual(out["absorbed"], 0, "October's month cannot vouch for a September call")
        self.assertEqual(g.db.execute("SELECT cost FROM commitments WHERE id='frontier:september'").fetchone()[0], None)

    def test_a_month_the_gateway_cannot_close_is_counted_once(self):
        """Sept 24, 2026 review: the meter kept September's last high (`carried`) while `covers_from`
        moved to October, and September's settled calls were added apart as well: $10 read as $20."""
        g = self.metered()
        self.read("0.00", "0.00")
        self.call("frontier:september", "12.00", "10.00")  # the House and the gateway both settle $10
        self.read("10.00", "10.00")
        self.now[0] = stamp("2026-10-01T00:30:00")
        self.guard.observe_balance("sail", "100.00")
        self.read("0.00", "0.00", month="2026-10")  # the gateway cannot report September's final
        self.call("frontier:october", "1.00", "0.50")
        self.read("0.50", "0.50", month="2026-10")
        line = g.report()["meters"]["openai"]["line"]
        self.assertEqual((line["settled_usd"], line["measured_usd"], line["before_meter_usd"]), ("0.5", "0.5", "10"))
        self.assertEqual(Decimal(g.report()["burst"]["committed_usd"]["openai"]), Decimal("10.5"))
        self.assertEqual(Decimal(g.report()["accounts"]["openai"]["committed_usd"]), Decimal("10.5"), "the phase's line too")
        self.assertEqual(g.month_meter("openai")["base_usd"], "10")

    def test_a_month_the_gateway_closes_stays_inside_the_meter(self):
        g = self.metered()
        self.read("0.00", "0.00")
        self.call("frontier:september", "12.00", "10.00")
        self.read("10.00", "10.00")
        self.now[0] = stamp("2026-10-01T00:30:00")
        self.guard.observe_balance("sail", "100.00")
        self.read("0.00", "0.00", month="2026-10", previous={"month": "2026-09", "spent_usd": "10.00", "settled_usd": "10.000000"})
        self.call("frontier:october", "1.00", "0.50")
        self.read("0.50", "0.50", month="2026-10")
        line = g.report()["meters"]["openai"]["line"]
        self.assertEqual((line["settled_usd"], line["measured_usd"], line["before_meter_usd"]), ("10.5", "10.5", "0"))
        self.assertEqual(Decimal(g.report()["burst"]["committed_usd"]["openai"]), Decimal("10.5"))

    def test_calls_settled_before_the_meter_covers_are_counted_beside_it_never_inside(self):
        self.call("frontier:september", "2.00")                   # no answer, 20:00Z Sept 30
        self.call("frontier:september-settled", "12.00", "10.00")  # settled in September
        self.now[0] = stamp("2026-10-01T02:30:00")
        self.guard.observe_balance("sail", "100.00")
        g = self.metered()
        self.read("0.50", "0.50", month="2026-10")
        self.call("frontier:after", "1.00", "0.30")
        self.read("30.00", "30.00", month="2026-10")  # October's month, far above the House's October
        line = g.report()["meters"]["openai"]["line"]
        self.assertEqual((line["settled_usd"], line["before_meter_usd"], line["measured_usd"]), ("0.3", "10", "30"))
        # max(October settled $0.30, October's month $30) + September settled $10 + the $2 hold. The
        # month cannot count September's calls, so $10 of them must not vanish inside its $30.
        used = Decimal(g.report()["burst"]["committed_usd"]["openai"])
        self.assertEqual(used, Decimal("30") + Decimal("10") + Decimal("2"))


class TheHouseLineNeverReadsAboveTheMonth(Floor):
    """Sept 24, 2026 review: the plan aligns the House's OpenAI line "up to funded money, never above".
    With the phantom holds absorbed, the House line read $273.85 on the T0 snapshot while the gateway's
    month -- itself aligned to the owner's funded balance ($607 = $394.46 metered at T0 + $213 funded)
    -- had $203.74 left. Every reader of `remaining` sees at most the month's own line while a reading
    is fresh, and the House's own line when there is none (and then nothing is reserved)."""

    def test_every_reader_sees_the_months_line_when_it_is_the_lower(self):
        g = self.metered()
        self.read("10.00", "10.000000", cap="12.00")  # the month has $2 left; the House's own line $30
        pacer = CampaignPacer(None, g, clock=self.clock)
        self.assertEqual(g.remaining("openai"), Decimal("2"))
        self.assertEqual(pacer.remaining("openai"), Decimal("2"))
        self.assertEqual(pacer.room("openai"), Decimal("2"))
        report = g.report()
        self.assertEqual(report["accounts"]["openai"]["remaining_usd"], "2")
        self.assertEqual(report["burst"]["remaining_usd"]["openai"], "2")
        line = report["meters"]["openai"]["line"]
        self.assertEqual((line["house_line_usd"], line["provider_left_usd"], line["remaining_usd"]), ("30", "2", "2"))
        self.assertEqual(report["meters"]["openai"]["month"]["cap_usd"], "12")
        with self.assertRaises(CampaignClosed):
            g.reserve("frontier:too-dear", "foundation-review", "2.50")  # the House's own line would admit it
        self.assertTrue(g.reserve("frontier:fits", "foundation-review", "1.50"))
        self.assertEqual(g.remaining("openai"), Decimal("0.5"), "a hold made since the reading comes off the month")
        g.settle("frontier:fits", "0.40")
        self.assertEqual(g.remaining("openai"), Decimal("1.6"), "and then its cost")
        self.read("10.40", "10.400000", cap="12.00")  # the month has counted it now: never twice
        self.assertEqual(g.remaining("openai"), Decimal("1.6"))

    def test_the_agents_credit_pool_is_sized_from_the_bounded_line(self):
        g = self.metered()
        self.read("10.00", "10.000000", cap="12.00")
        self.assertTrue(g.activate_live_trading("earned", {"alpaca": "500", "kalshi": "500"})["active"])
        pacer = CampaignPacer(None, g, clock=self.clock)
        # (Sail's $2 x 0.75 + OpenAI's $2 x 0.5) x one hour of the eight-hour burst; the House's own
        # $30 would have made it $2.06.
        self.assertEqual(pacer.credit_pool(per_seconds=3600), Decimal("0.31"))

    def test_a_month_with_more_left_never_raises_the_house_line(self):
        g = self.metered()
        self.read("0.00", "0.000000", cap="400.00")
        self.call("frontier:dear", "40.00", "35.00")  # booked at the House's own (dearer) prices
        self.read("20.00", "20.000000", cap="400.00")
        self.assertEqual(g.remaining("openai"), Decimal("5"))
        self.assertEqual(g.report()["meters"]["openai"]["line"]["provider_left_usd"], "380")

    def test_without_a_fresh_reading_the_house_line_stands_alone_and_nothing_is_reserved(self):
        g = self.metered()
        self.read("10.00", "10.000000", cap="12.00")
        self.advance(181)
        self.assertEqual(g.remaining("openai"), Decimal("30"))
        self.assertIsNone(g.report()["meters"]["openai"]["line"]["provider_left_usd"])
        with self.assertRaises(CampaignClosed):
            g.reserve("frontier:unmetered", "foundation-review", "0.10")

    def test_the_gateway_month_reader_passes_the_months_cap(self):
        g = self.metered()
        gateway = Gateway({"month": "2026-09", "spent_usd": "10.00", "settled_usd": "10.000000", "cap_usd": "12.00"})
        month = FrontierMonth("https://gw.test", lambda: "t" * 20, opener=gateway, clock=self.clock, meter=g)
        self.assertEqual(month.remaining(), Decimal("2.00"))
        self.assertEqual(g.remaining("openai"), Decimal("2"))

    def test_a_store_the_first_build_opened_gains_the_months_line(self):
        path = Path(self.tmp.name) / "first-build.sqlite"
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE meter_month(id TEXT PRIMARY KEY, month TEXT NOT NULL, high INTEGER NOT NULL, "
                   "carried INTEGER NOT NULL, settled_high INTEGER, settled_carried INTEGER NOT NULL, covers_from REAL NOT NULL, "
                   "anchor_at REAL, anchor_row INTEGER, anchor_settled INTEGER, at REAL NOT NULL)")
        db.commit()
        db.close()
        g = CampaignBudget(path, rules("sail", "openai"), clock=self.clock)
        self.addCleanup(g.close)
        g.observe_balance("sail", "100.00")
        g.observe_month("openai", "2026-09", "10.00", settled="10.000000", cap="12.00")
        g.activate_burst("night", night())
        self.assertEqual(g.remaining("openai"), Decimal("2"))


class TheHouseAbsorbs(HouseCase):
    """The tick reads the gateway's month (OpenAI's meter), absorbs the stale OpenAI holds against
    it every ten minutes, and the tier follows the nearer of the two lines."""

    def test_the_tick_reads_the_month_releases_the_phantoms_and_the_tier_rises(self):
        self.house.game["frontier_reserve"] = RESERVE
        path = self.house.root / "campaigns-test.sqlite"
        guard = CampaignBudget(path, rules("sail"), clock=self.clock)
        guard.observe_balance("sail", "100.00")
        guard.activate_burst("night", night("30"))
        guard.reserve("external-pilot:typesafe:backing", "foundation-review", "10.00")
        guard.reserve("frontier:ceiling", "foundation-review", "12.00")
        guard.settle("frontier:ceiling", "10.00")
        guard.reserve("frontier:lost-1", "foundation-review", "2.00")
        guard.reserve("frontier:lost-2", "foundation-review", "3.00")
        guard.close()
        self.clock.advance(6.5 * HOUR)
        guard = CampaignBudget(path, rules("sail", "openai"), clock=self.clock)
        self.addCleanup(guard.close)
        gateway = Gateway({"month": "2026-09", "spent_usd": "8.00", "settled_usd": "8.000000", "cap_usd": "20.00",
                           "base_cap_usd": "20.00"})
        self.house.campaigns = guard
        self.house.frontier_month = FrontierMonth("https://gw.test", lambda: "t" * 20, opener=gateway,
                                                  clock=self.clock, meter=guard)
        # Before: the phantoms hold the House's line under the audits reserve ($30 - $10 - $15).
        self.assertEqual(guard.remaining("openai"), Decimal("5"))
        self.house.tick()
        self.assertTrue(guard.ready("openai"), "the tick read the gateway's month")
        self.assertEqual(self.house.frontier_tier(), "audits")
        absorbed = [e.payload for e in self.house.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "holds absorbed"]
        self.assertEqual(absorbed, [], "nothing settled since the anchor: nothing to check the meter against yet")
        guard.reserve("frontier:after", "foundation-review", "1.00")  # an audit, answered
        guard.settle("frontier:after", "0.30")
        gateway.frontier = {**gateway.frontier, "spent_usd": "8.30", "settled_usd": "8.300000"}
        self.clock.advance(61)
        self.house.tick()
        absorbed = [e.payload for e in self.house.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "holds absorbed"]
        self.assertEqual(len(absorbed), 1)
        self.assertEqual((absorbed[0]["kind"], absorbed[0]["absorbed"], absorbed[0]["usd"]), ("openai", 2, "5"))
        # After: $30 - $10.30 - $10 (Jev's backing stays) = $9.70; the gateway month has $11.70 left.
        self.assertEqual(guard.remaining("openai"), Decimal("9.7"))
        self.clock.advance(31)
        self.assertEqual(self.house.frontier_remaining(), Decimal("9.7"))
        self.assertEqual(self.house.frontier_tier(), "earned")
        self.clock.advance(61)
        self.house.tick()
        again = [e for e in self.house.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "holds absorbed"]
        self.assertEqual(len(again), 1, "once every ten minutes, and nothing is left to release")


if __name__ == "__main__":
    unittest.main()
