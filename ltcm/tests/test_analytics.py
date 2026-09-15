"""The results ledger, folded over a synthetic day of floor events.

The fixture is one UTC day (2026-09-15) of three desks: `mullins` (live, Kalshi event contracts,
`pro_flex`), `rosenfeld` (live, equities, `kimi_flex`) and `hilibrand` (shadow, crypto,
`oss_asap`), with a committee request nobody's desk paid for, a shadow settlement fill that
belongs to no desk at all, and one session on the previous day that must stay outside the window.
Every expected number below is worked out by hand in the comments.
"""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ltcm.analytics import (
    DEFAULT_WINDOW_DAYS,
    ResultsLedger,
    markdown,
    metrics_block,
    parse_probability,
    verdict_for,
)
from ltcm.broker import Instrument
from ltcm.events import EventLog
from ltcm.manifest import DeskManifest
from ltcm.publish import sanitize_for_site, shape_problem
from ltcm.tests.test_manifest import SAMPLE

NOW = "2026-09-15T23:00:00.000Z"
DAY = "2026-09-15"

AAPL = Instrument("equity", "AAPL", "alpaca")
CPI = Instrument("event", "CPI", "kalshi", market_id="CPI-26SEP", right="yes")

ROSTER = {
    "mullins": ("Mullins", "kalshi", "live", "pro_flex"),
    "rosenfeld": ("Rosenfeld", "earnings", "live", "kimi_flex"),
    "hilibrand": ("Hilibrand", "crypto", "shadow", "oss_asap"),
}


def manifests():
    out = {}
    for desk_id, (name, family, mode, profile) in ROSTER.items():
        data = copy.deepcopy(SAMPLE)
        data.update(
            {
                "id": desk_id,
                "name": name,
                "family": family,
                "playbook": f"playbooks/{desk_id}.md",
                "capital": {"mode": mode, "usd": "1000"},
                "model": {**data["model"], "profile": profile},
            }
        )
        out[desk_id] = DeskManifest.from_dict(data)
    return out


class Floor:
    """A tiny writer for the synthetic log, one method per event kind the fold reads."""

    def __init__(self, log):
        self.log = log
        self.n = 0

    def _at(self, stamp):
        self.n += 1
        return stamp

    def allocate(self, at, allocations, shadow=None):
        self.log.append(
            "committee",
            "committee.allocation",
            {
                "allocations": {k: str(v) for k, v in allocations.items()},
                "shadow": shadow or {},
                "reasons": {},
            },
            at=self._at(at),
        )

    def session(self, desk, session_id, at, *, tool_calls=0, requests=0, cost="0"):
        self.log.append(
            f"desk:{desk}",
            "desk.session_started",
            {"session_id": session_id, "trigger": "cadence:09:35"},
            at=at,
        )
        for index in range(tool_calls):
            self.log.append(
                f"desk:{desk}",
                "desk.tool_call",
                {
                    "session_id": session_id,
                    "call_id": f"{session_id}-c{index}",
                    "tool": "quote",
                    "arguments": {},
                },
                at=at,
            )
        self.log.append(
            f"desk:{desk}",
            "desk.session_ended",
            {
                "session_id": session_id,
                "requests": requests,
                "cost_usd": str(cost),
                "reason": "end_session",
            },
            at=at,
        )

    def intent(self, desk, session_id, at, instrument, rationale):
        self.n += 1
        self.log.append(
            f"desk:{desk}",
            "desk.intent",
            {
                "intent_id": f"i{self.n}",
                "desk_id": desk,
                "instrument": instrument.to_dict(),
                "side": "buy",
                "quantity": "1",
                "order_type": "limit",
                "limit_price": "1",
                "rationale": rationale,
                "session_id": session_id,
            },
            at=at,
        )

    def request(self, desk, session_id, at, profile, cost, count=1):
        for index in range(count):
            self.n += 1
            self.log.append(
                "ops",
                "provider.request",
                {
                    "request_id": f"r{self.n}",
                    "desk_id": desk,
                    "session_id": session_id,
                    "profile": profile,
                    "status": "completed",
                    "cost_usd": str(cost),
                    "usage": {"input_tokens": 1000, "output_tokens": 100},
                    "_response_id": "resp-secret",
                },
                at=at,
                public=False,
            )

    def fill(self, desk, at, instrument, side, quantity, price, fee="0", venue="alpaca", shadow=False):
        self.n += 1
        payload = {
            "fill_id": f"f{self.n}",
            "order_id": f"o{self.n}",
            "desk_id": desk,
            "instrument": instrument.to_dict(),
            "side": side,
            "quantity": str(quantity),
            "price": str(price),
            "fee": str(fee),
            "at": at,
            "venue": venue,
        }
        if shadow:
            payload["shadow"] = True
        self.log.append(f"broker:{venue}", "broker.fill", payload, at=at)

    def outcome(self, desk, at, *, market_id, result, pnl, rationale, entry="0.60", exit="1.00"):
        self.n += 1
        self.log.append(
            f"desk:{desk}",
            "desk.outcome",
            {
                "instrument": f"event:CPI:kalshi:{market_id}",
                "market_id": market_id,
                "result": result,
                "entry_price": entry,
                "exit_price": exit,
                "quantity": "100",
                "pnl": str(pnl),
                "held_for_hours": "12.0",
                "rationale_excerpt": rationale,
            },
            at=at,
        )

    def mark(self, desk, at, equity, shadow=False):
        payload = {
            "desk_id": desk,
            "equity": str(equity),
            "cash": str(equity),
            "positions": [],
            "daily_pnl": "0",
            "as_of": at,
        }
        if shadow:
            payload["shadow"] = True
        self.log.append(f"ledger:{desk}", "ledger.mark", payload, id=f"mark:{desk}:{at}", at=at)

    def decision(self, desk, at, approved, reasons):
        self.n += 1
        self.log.append(
            "risk",
            "risk.decision",
            {
                "intent_id": f"i{self.n}",
                "desk_id": desk,
                "approved": approved,
                "reasons": list(reasons),
                "checked_at": at,
            },
            at=at,
        )

    def review(self, desk, at, verdict):
        self.n += 1
        self.log.append(
            "risk",
            "risk.review",
            {
                "intent_id": f"i{self.n}",
                "desk_id": desk,
                "verdict": verdict,
                "reason": "the rationale names no exit",
                "model": "zai-org/GLM-5.3",
            },
            at=at,
        )


def build_log(path):
    log = EventLog(path)
    floor = Floor(log)

    # ---------------------------------------------------------------- the day before
    floor.allocate(
        "2026-09-14T12:00:00.000Z",
        {"mullins": 200, "rosenfeld": 500, "hilibrand": 300},
        shadow={"hilibrand": True},
    )
    # Rosenfeld's opening lot. Outside the window, but the average cost it sets is what makes the
    # sale inside the window worth +30 rather than nothing.
    floor.fill("rosenfeld", "2026-09-14T14:00:00.000Z", AAPL, "buy", 10, "100", fee="0.10")
    floor.session("mullins", "s-old", "2026-09-14T13:00:00.000Z", tool_calls=9, requests=3)
    floor.request("mullins", "s-old", "2026-09-14T13:00:00.000Z", "pro_flex", "1.00", count=3)

    # ---------------------------------------------------------------- mullins, two sessions
    floor.session("mullins", "s-m1", "2026-09-15T08:00:00.000Z", tool_calls=3, requests=4)
    floor.intent(
        "mullins",
        "s-m1",
        "2026-09-15T08:00:40.000Z",
        CPI,
        "Base rates and the nowcast say probability: 0.70 the print lands above 3%.",
    )
    floor.request("mullins", "s-m1", "2026-09-15T08:00:10.000Z", "pro_flex", "0.05", count=4)
    floor.session("mullins", "s-m2", "2026-09-15T13:00:00.000Z", tool_calls=1, requests=2)
    floor.request("mullins", "s-m2", "2026-09-15T13:00:10.000Z", "pro_flex", "0.03", count=2)
    # The critic rides on the desk's session id and a different, cheaper profile.
    floor.request("mullins", "s-m2", "2026-09-15T13:05:00.000Z", "glm_asap", "0.01")

    floor.fill("mullins", "2026-09-15T08:05:00.000Z", CPI, "buy", 100, "0.60", fee="0.35", venue="kalshi")
    floor.fill("mullins", "2026-09-15T20:00:00.000Z", CPI, "sell", 100, "1.00", venue="kalshi")
    floor.outcome(
        "mullins",
        "2026-09-15T20:00:00.000Z",
        market_id="CPI-26SEP",
        result="yes",
        pnl="40.00",
        rationale="Base rates and the nowcast say probability: 0.70 the print lands above 3%.",
    )
    floor.outcome(
        "mullins",
        "2026-09-15T20:01:00.000Z",
        market_id="NFP-26SEP",
        result="no",
        pnl="-15.00",
        rationale="p=0.40 that payrolls beat the consensus.",
    )
    floor.outcome(
        "mullins",
        "2026-09-15T20:02:00.000Z",
        market_id="RAIN-26SEP",
        result="yes",
        pnl="5.00",
        rationale="Cheap tail, no number stated.",
    )
    floor.decision("mullins", "2026-09-15T08:04:00.000Z", True, ["ok"])
    floor.decision("mullins", "2026-09-15T08:06:00.000Z", True, ["ok"])
    floor.decision("mullins", "2026-09-15T13:06:00.000Z", False, ["limit: position over 15%"])
    # The critic's block is a second risk.decision. Counting it here as well would turn one
    # refusal into two.
    floor.decision("mullins", "2026-09-15T13:07:00.000Z", False, ["critic: contradicts rationale"])
    floor.review("mullins", "2026-09-15T08:04:30.000Z", "approve")
    floor.review("mullins", "2026-09-15T13:07:00.000Z", "block")
    log.append(
        "desk:mullins",
        "desk.playbook_updated",
        {"version": "3", "diff": "+ size down into CPI", "reason": "two losses in a row"},
        at="2026-09-15T21:00:00.000Z",
    )
    log.append(
        "desk:mullins",
        "desk.postmortem",
        {"session_id": "s-m2", "period": DAY, "text": "Worst decision: NFP.", "lessons": ["wait"]},
        at="2026-09-15T21:05:00.000Z",
    )
    floor.mark("mullins", "2026-09-15T09:00:00.000Z", "200")
    floor.mark("mullins", "2026-09-15T12:00:00.000Z", "190")  # -5% from the peak
    floor.mark("mullins", "2026-09-15T20:30:00.000Z", "240")

    # ---------------------------------------------------------------- rosenfeld, one session
    floor.session("rosenfeld", "s-r1", "2026-09-15T14:00:00.000Z", tool_calls=2, requests=5)
    floor.intent("rosenfeld", "s-r1", "2026-09-15T14:01:00.000Z", AAPL, "Drift after the beat.")
    floor.request("rosenfeld", "s-r1", "2026-09-15T14:00:30.000Z", "kimi_flex", "0.10", count=5)
    floor.fill("rosenfeld", "2026-09-15T14:05:00.000Z", AAPL, "sell", 10, "103", fee="0.10")
    floor.decision("rosenfeld", "2026-09-15T14:04:00.000Z", True, ["ok"])
    floor.mark("rosenfeld", "2026-09-15T14:00:00.000Z", "500")
    # The committee adds 100 at 14:30. Marked equity then rises, but the desk lost 20 of its own.
    floor.allocate(
        "2026-09-15T14:30:00.000Z",
        {"mullins": 200, "rosenfeld": 600, "hilibrand": 300},
        shadow={"hilibrand": True},
    )
    floor.mark("rosenfeld", "2026-09-15T15:00:00.000Z", "580")
    floor.mark("rosenfeld", "2026-09-15T16:00:00.000Z", "630")

    # ---------------------------------------------------------------- hilibrand, all talk
    floor.session("hilibrand", "s-h1", "2026-09-15T09:00:00.000Z", tool_calls=1, requests=2)
    floor.request("hilibrand", "s-h1", "2026-09-15T09:00:20.000Z", "oss_asap", "0.004", count=2)
    floor.mark("hilibrand", "2026-09-15T09:05:00.000Z", "300", shadow=True)

    # ---------------------------------------------------------------- nobody's desk
    floor.request("committee", "committee-2026-W38", "2026-09-15T22:00:00.000Z", "glm_flex", "0.02")
    # The shadow book closes its own settled contracts under an id no desk ledger folds.
    floor.fill(
        "settlement",
        "2026-09-15T20:00:00.000Z",
        CPI,
        "sell",
        100,
        "1.00",
        venue="shadow",
        shadow=True,
    )
    return log


class AnalyticsCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.log = build_log(Path(cls.tmp.name) / "events.sqlite")
        cls.manifests = manifests()
        cls.results = ResultsLedger(cls.log, cls.manifests)
        cls.report = cls.results.report(1, NOW)

    @classmethod
    def tearDownClass(cls):
        cls.log.close()
        cls.tmp.cleanup()

    def floor(self):
        return self.report["floor"]

    def desk(self, desk_id):
        return self.report["desks"][desk_id]


class FloorMetrics(AnalyticsCase):
    def test_the_window_and_the_roster(self):
        self.assertEqual(self.report["window_days"], 1)
        self.assertEqual(self.report["generated_at"], NOW)
        self.assertEqual(self.report["window"]["start"], "2026-09-14T23:00:00.000Z")
        self.assertEqual(sorted(self.report["desks"]), ["hilibrand", "mullins", "rosenfeld"])
        self.assertEqual(self.floor()["desks"], 3)
        self.assertEqual((self.floor()["live_desks"], self.floor()["shadow_desks"]), (2, 1))

    def test_work_done(self):
        floor = self.floor()
        self.assertEqual(floor["sessions"], 4)  # two mullins, one each for the others
        self.assertEqual(floor["turns"], 13)  # 4 + 2 + 5 + 2, from the desks' own counts
        self.assertEqual(floor["turns_per_session"], "3.25")
        self.assertEqual(floor["tool_calls"], 7)
        self.assertEqual(floor["tool_calls_per_session"], "1.75")
        self.assertEqual(floor["requests"], 15)  # 14 desk requests plus the committee's

    def test_money(self):
        floor = self.floor()
        # 0.27 mullins + 0.50 rosenfeld + 0.008 hilibrand + 0.02 committee
        self.assertEqual(floor["sail_cost_usd"], "0.7980")
        self.assertEqual(floor["desk_sail_cost_usd"], "0.7780")
        self.assertEqual(floor["overhead_cost_usd"], "0.0200")
        self.assertEqual(floor["decisions"], 3)  # the settlement fill belongs to no desk
        self.assertEqual(floor["closed_trades"], 4)
        self.assertEqual(floor["wins"], 3)
        self.assertEqual(floor["win_rate"], "0.7500")
        self.assertEqual(floor["avg_pnl_usd"], "15.0000")
        self.assertEqual(floor["closed_pnl_usd"], "60.0000")
        self.assertEqual(floor["realized_pnl_usd"], "60.0000")
        self.assertEqual(floor["hypothetical_pnl_usd"], "0.0000")
        self.assertEqual(floor["fees_usd"], "0.4500")
        # 60 - 0.45 of fees - 0.798 of inference
        self.assertEqual(floor["net_pnl_usd"], "58.7520")
        self.assertEqual(floor["cost_per_decision_usd"], "0.2660")
        self.assertEqual(floor["pnl_per_inference_dollar"], "74.6241")  # 59.55 / 0.798

    def test_judgement(self):
        floor = self.floor()
        self.assertEqual(floor["max_drawdown_pct"], "0.0500")  # the worst desk's window
        self.assertEqual((floor["brier"], floor["brier_n"]), ("0.1250", 2))
        self.assertEqual(floor["critic_block_rate"], "0.5000")
        self.assertEqual(floor["risk_rejection_rate"], "0.2500")  # 1 of 4, critic excluded
        self.assertEqual(floor["playbook_versions"], 1)
        self.assertEqual(floor["postmortems"], 1)
        self.assertEqual(floor["seconds_to_first_order"], "50.00")  # 40s and 60s
        self.assertEqual(floor["sessions_with_order"], 2)


class DeskMetrics(AnalyticsCase):
    def test_an_event_desk(self):
        row = self.desk("mullins")
        self.assertEqual(
            (row["name"], row["family"], row["mode"], row["profile"]),
            ("Mullins", "kalshi", "live", "pro_flex"),
        )
        self.assertEqual((row["sessions"], row["turns"], row["turns_per_session"]), (2, 6, "3.00"))
        self.assertEqual((row["tool_calls"], row["tool_calls_per_session"]), (4, "2.00"))
        self.assertEqual((row["requests"], row["sail_cost_usd"]), (7, "0.2700"))
        self.assertEqual((row["decisions"], row["fees_usd"]), (2, "0.3500"))
        self.assertEqual((row["closed_trades"], row["wins"], row["win_rate"]), (3, 2, "0.6667"))
        self.assertEqual(row["avg_pnl_usd"], "10.0000")
        self.assertEqual(row["closed_pnl_usd"], "30.0000")
        self.assertEqual(row["realized_pnl_usd"], "30.0000")
        self.assertEqual(row["hypothetical_pnl_usd"], "0.0000")
        self.assertEqual(row["net_pnl_usd"], "29.3800")
        self.assertEqual(row["cost_per_decision_usd"], "0.1350")
        self.assertEqual(row["pnl_per_inference_dollar"], "109.8148")
        self.assertEqual(row["max_drawdown_pct"], "0.0500")
        self.assertEqual((row["brier"], row["brier_n"]), ("0.1250", 2))
        self.assertEqual((row["critic_reviews"], row["critic_blocks"]), (2, 1))
        self.assertEqual(row["critic_block_rate"], "0.5000")
        self.assertEqual((row["risk_decisions"], row["risk_rejections"]), (3, 1))
        self.assertEqual(row["risk_rejection_rate"], "0.3333")
        self.assertEqual((row["playbook_versions"], row["playbook_version"]), (1, "3"))
        self.assertEqual(row["postmortems"], 1)
        self.assertEqual(row["seconds_to_first_order"], "40.00")
        self.assertEqual(row["equity_usd"], "240.0000")

    def test_an_equity_desk_closes_by_average_cost(self):
        row = self.desk("rosenfeld")
        # One fill in the window, closing a lot opened the day before at 100: 10 x (103 - 100).
        self.assertEqual((row["decisions"], row["closed_trades"]), (1, 1))
        self.assertEqual((row["wins"], row["win_rate"]), (1, "1.0000"))
        self.assertEqual(row["closed_pnl_usd"], "30.0000")
        self.assertEqual(row["pnl_per_inference_dollar"], "59.8000")  # (30 - 0.10) / 0.50
        self.assertEqual(row["seconds_to_first_order"], "60.00")
        self.assertIsNone(row["brier"])

    def test_a_shadow_desk_that_never_traded(self):
        row = self.desk("hilibrand")
        self.assertEqual((row["mode"], row["sessions"], row["turns"]), ("shadow", 1, 2))
        self.assertEqual((row["decisions"], row["closed_trades"]), (0, 0))
        self.assertEqual(row["sail_cost_usd"], "0.0080")
        self.assertEqual(row["realized_pnl_usd"], "0.0000")
        self.assertEqual(row["hypothetical_pnl_usd"], "0.0000")
        # No denominator, so no number. A fabricated zero would read as "never wins".
        for key in ("win_rate", "avg_pnl_usd", "cost_per_decision_usd", "brier"):
            self.assertIsNone(row[key], key)

    def test_a_shadow_desk_that_did_trade_is_hypothetical(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = build_log(Path(tmp) / "events.sqlite")
            floor = Floor(log)
            floor.fill(
                "hilibrand", "2026-09-15T10:00:00.000Z", AAPL, "buy", 1, "100", venue="shadow",
                shadow=True,
            )
            floor.fill(
                "hilibrand", "2026-09-15T11:00:00.000Z", AAPL, "sell", 1, "110", venue="shadow",
                shadow=True,
            )
            report = ResultsLedger(log, manifests()).report(1, NOW)
            row = report["desks"]["hilibrand"]
            self.assertEqual(row["closed_pnl_usd"], "10.0000")
            self.assertEqual(row["hypothetical_pnl_usd"], "10.0000")
            self.assertEqual(row["realized_pnl_usd"], "0.0000")
            # The floor's real book is unmoved by a score.
            self.assertEqual(report["floor"]["realized_pnl_usd"], "60.0000")
            self.assertEqual(report["floor"]["hypothetical_pnl_usd"], "10.0000")
            log.close()

    def test_the_window_excludes_yesterday(self):
        # Yesterday's session had nine tool calls and three one-dollar requests. Neither shows up.
        self.assertEqual(self.desk("mullins")["sessions"], 2)
        self.assertNotIn("1.00", self.desk("mullins")["sail_cost_usd"])
        wide = self.results.report(7, NOW)
        self.assertEqual(wide["desks"]["mullins"]["sessions"], 3)
        self.assertEqual(wide["desks"]["mullins"]["sail_cost_usd"], "3.2700")
        self.assertEqual(wide["window_days"], 7)

    def test_the_shadow_books_own_settlement_is_not_a_desk(self):
        self.assertNotIn("settlement", self.report["desks"])
        self.assertNotIn("committee", self.report["desks"])
        self.assertEqual(self.floor()["decisions"], 3)


class DrawdownAndCalibration(AnalyticsCase):
    def test_drawdown_is_measured_net_of_capital_flows(self):
        # Marked equity only rose (500, 580, 630), but 100 of that was the committee's deposit:
        # flow-adjusted the desk went 500, 480, 530, which is a 4% fall.
        self.assertEqual(self.desk("rosenfeld")["max_drawdown_pct"], "0.0400")

    def test_brier_scores_only_stated_probabilities(self):
        # (0.70 - 1)^2 = 0.09 and (0.40 - 0)^2 = 0.16; the third outcome stated no number.
        row = self.desk("mullins")
        self.assertEqual((row["brier"], row["brier_n"]), ("0.1250", 2))
        self.assertEqual(row["closed_trades"], 3)

    def test_probability_parsing(self):
        self.assertEqual(parse_probability("probability: 0.62 of a cut"), Decimal("0.62"))
        self.assertEqual(parse_probability("I make it p=0.3"), Decimal("0.3"))
        self.assertEqual(parse_probability("prob = .45 here"), Decimal(".45"))
        self.assertEqual(parse_probability("probability: 62%"), Decimal("0.62"))
        self.assertEqual(parse_probability("P: 1"), Decimal("1"))
        for absent in (
            "no number at all",
            "probability of about two thirds",
            "p=1.4",  # not a probability
            "the stop=0.5 level",  # not a probability either
            None,
            "",
        ):
            self.assertIsNone(parse_probability(absent), absent)


class FamiliesAndProfiles(AnalyticsCase):
    def test_families_group_by_mandate(self):
        families = self.report["families"]
        self.assertEqual(sorted(families), ["crypto", "earnings", "kalshi"])
        self.assertEqual(families["kalshi"]["desks"], ["mullins"])
        self.assertEqual(families["kalshi"]["closed_pnl_usd"], "30.0000")
        self.assertEqual(families["earnings"]["closed_pnl_usd"], "30.0000")
        self.assertEqual(families["crypto"]["decisions"], 0)
        self.assertEqual(families["crypto"]["sail_cost_usd"], "0.0080")

    def test_profiles_separate_what_a_model_was_paid_from_what_it_earned(self):
        profiles = self.report["profiles"]
        self.assertEqual(
            sorted(profiles), ["glm_asap", "glm_flex", "kimi_flex", "oss_asap", "pro_flex"]
        )
        pro = profiles["pro_flex"]
        self.assertEqual(pro["desks"], ["mullins"])
        self.assertEqual((pro["requests"], pro["sail_cost_usd"]), (6, "0.2600"))  # 4x0.05 + 2x0.03
        self.assertEqual(pro["cost_per_request_usd"], "0.0433")
        # The desk also paid a cent to the critic on another profile; its own results are charged
        # the whole 0.27.
        self.assertEqual(pro["desk_cost_usd"], "0.2700")
        self.assertEqual(pro["closed_pnl_usd"], "30.0000")
        self.assertEqual(pro["pnl_per_inference_dollar"], "109.8148")

        critic = profiles["glm_asap"]
        self.assertEqual((critic["requests"], critic["sail_cost_usd"]), (1, "0.0100"))
        self.assertEqual(critic["desks"], [])  # no desk runs on it; it only reviews
        self.assertEqual(critic["closed_trades"], 0)

        cheap = profiles["oss_asap"]
        self.assertEqual((cheap["requests"], cheap["desks"]), (2, ["hilibrand"]))
        self.assertEqual(cheap["cost_per_request_usd"], "0.0040")
        # It was paid and it returned nothing, which is a number, not a missing one.
        self.assertEqual(cheap["pnl_per_inference_dollar"], "0.0000")
        self.assertIsNone(cheap["cost_per_decision_usd"])  # no decisions to divide by

    def test_the_committees_own_spend_is_overhead_not_a_desk(self):
        self.assertEqual(self.report["profiles"]["glm_flex"]["desks"], [])
        self.assertEqual(self.floor()["overhead_cost_usd"], "0.0200")


class WithoutManifests(AnalyticsCase):
    def test_the_roster_is_discovered_from_the_log(self):
        report = ResultsLedger(self.log).report(1, NOW)
        self.assertEqual(sorted(report["desks"]), ["hilibrand", "mullins", "rosenfeld"])
        row = report["desks"]["mullins"]
        self.assertEqual(row["name"], "Mullins")  # from the id, in the absence of a manifest
        self.assertEqual(row["family"], "mullins")  # no family in the log for a first-generation desk
        self.assertEqual(row["profile"], "pro_flex")  # the profile that served most of its turns
        self.assertEqual(row["closed_pnl_usd"], "30.0000")
        # The committee's allocation flagged the shadow sleeve, so the mode survives too.
        self.assertEqual(report["desks"]["hilibrand"]["mode"], "shadow")

    def test_a_spawned_desk_keeps_its_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = build_log(Path(tmp) / "events.sqlite")
            log.append(
                "evolution",
                "evolution.spawned",
                {
                    "desk_id": "mullins-2",
                    "family": "kalshi",
                    "parent_id": "mullins",
                    "generation": 2,
                    "mutation": {},
                },
                at="2026-09-15T07:00:00.000Z",
            )
            Floor(log).session("mullins-2", "s-x", "2026-09-15T08:00:00.000Z", requests=1)
            report = ResultsLedger(log).report(1, NOW)
            self.assertEqual(report["desks"]["mullins-2"]["family"], "kalshi")
            self.assertIn("mullins-2", report["families"]["kalshi"]["desks"])
            log.close()


class DailyResult(AnalyticsCase):
    def publish(self, log, now="2026-09-16T00:10:00.000Z", **kwargs):
        return ResultsLedger.publish_daily(log, now, manifests=self.manifests, **kwargs)

    def test_one_event_per_utc_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = build_log(Path(tmp) / "events.sqlite")
            first = self.publish(log)
            self.assertIsNotNone(first)
            self.assertEqual(first.id, f"lab:daily:{DAY}")
            self.assertEqual(first.kind, "lab.result")
            self.assertEqual(first.stream, "lab")
            self.assertTrue(first.public)
            self.assertEqual(first.payload["hypothesis_id"], f"daily-{DAY}")

            # Called again an hour later, and again with an explicit day: still one event.
            again = self.publish(log, now="2026-09-16T01:10:00.000Z")
            third = self.publish(log, now="2026-09-16T02:00:00.000Z", day=DAY)
            self.assertEqual(again.id, first.id)
            self.assertEqual(third.digest, first.digest)
            self.assertEqual(len(log.read(stream="lab", kind="lab.result", limit=100)), 1)
            log.close()

    def test_the_payload_is_publishable(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = build_log(Path(tmp) / "events.sqlite")
            event = self.publish(log)
            self.assertIsNone(shape_problem(event))
            payload = event.payload
            self.assertEqual(sorted(payload), ["hypothesis_id", "metrics", "verdict"])
            metrics = payload["metrics"]
            self.assertTrue(metrics)
            for key, value in metrics.items():
                if key == "by_generation":  # leap: lab -- the one list in the block, per the contract
                    self.assertIsInstance(value, list)
                    for row in value:
                        self.assertEqual(
                            sorted(row),
                            ["brier", "cost_adjusted_excess_pct", "cost_usd", "decisions", "desks",
                             "generation", "pnl_per_inference_usd", "pnl_usd"],
                        )
                    continue
                self.assertIsInstance(value, str, key)
                self.assertNotIn("<", value)
                self.assertNotIn("<", key)
                self.assertLess(len(value), 8000)
            self.assertLessEqual(len(json.dumps(metrics).encode("utf-8")), 20_000)
            self.assertNotIn("<", payload["verdict"])
            self.assertLess(len(payload["verdict"]), 8000)
            # The publisher changes nothing, because nothing needed changing.
            self.assertEqual(sanitize_for_site(payload), payload)
            log.close()

    def test_the_metrics_carry_the_floor_the_desks_and_the_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = build_log(Path(tmp) / "events.sqlite")
            metrics = self.publish(log).payload["metrics"]
            self.assertEqual(metrics["window.days"], "1")
            self.assertEqual(metrics["window.start"], "2026-09-15T00:00:00.000Z")
            self.assertEqual(metrics["floor.closed_pnl_usd"], "60.0000")
            self.assertEqual(metrics["floor.sail_cost_usd"], "0.7980")
            self.assertEqual(metrics["floor.win_rate"], "0.7500")
            self.assertEqual(metrics["desk.mullins.win_rate"], "0.6667")
            self.assertEqual(metrics["desk.mullins.brier"], "0.1250")
            self.assertEqual(metrics["desk.hilibrand.mode"], "shadow")
            self.assertEqual(metrics["profile.pro_flex.sail_cost_usd"], "0.2600")
            # An undefined ratio is absent, not zero.
            self.assertNotIn("desk.hilibrand.win_rate", metrics)
            log.close()

    def test_the_verdict_reads_like_a_sentence(self):
        verdict = verdict_for(self.report)
        self.assertEqual(
            verdict,
            "Mullins 3 outcomes, 66.7% hit, +$29.65 net of $0.27 inference; "
            "Rosenfeld 1 outcome, 100% hit, +$29.90 net of $0.50 inference; "
            "Hilibrand 0 trades",
        )

    def test_a_day_with_no_activity_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = build_log(Path(tmp) / "events.sqlite")
            self.assertIsNone(self.publish(log, now="2026-09-20T00:10:00.000Z"))
            self.assertEqual(log.read(stream="lab", limit=10), [])
            log.close()

    def test_the_default_day_is_the_one_that_has_finished(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = build_log(Path(tmp) / "events.sqlite")
            # Called during the 15th, the record written is the 14th's, not a partial day.
            event = ResultsLedger.publish_daily(log, "2026-09-15T12:00:00.000Z")
            self.assertEqual(event.id, "lab:daily:2026-09-14")
            self.assertEqual(event.payload["hypothesis_id"], "daily-2026-09-14")
            log.close()

    def test_a_crowded_block_sheds_detail_instead_of_overflowing(self):
        full = metrics_block(self.report)
        self.assertLess(len(json.dumps(full).encode("utf-8")), 20_000)
        self.assertNotIn("metrics.truncated", full)

        small = metrics_block(self.report, limit=1500)
        self.assertLessEqual(len(json.dumps(small).encode("utf-8")), 1500)
        self.assertEqual(small["metrics.truncated"], "true")
        self.assertIn("floor.closed_pnl_usd", small)  # the floor is never dropped
        self.assertIn("desk.mullins.closed_pnl_usd", small)  # nor is the busiest desk
        self.assertNotIn("desk.mullins.seconds_to_first_order", small)  # detail goes first
        self.assertNotIn("desk.hilibrand.sessions", small)  # then the quietest desk


class MarkdownReport(AnalyticsCase):
    def test_it_renders_tables_a_human_can_read(self):
        body = markdown(self.report)
        self.assertTrue(body.startswith("# Lab report -- 2026-09-15"))
        for heading in (
            "## Floor",
            "## Desks: work and cost",
            "## Desks: results",
            "## Families",
            "## Model profiles",
            "## Verdict",
        ):
            self.assertIn(heading, body)
        self.assertIn("| desk | family | mode | profile |", body)
        self.assertIn("| Mullins | kalshi | live | pro_flex |", body)
        self.assertIn("| Hilibrand | crypto | shadow | oss_asap |", body)
        self.assertIn("| Mullins | 3 | 66.7% |", body)  # the results table
        self.assertIn("66.7%", body)  # the hit rate as a percentage, not a ratio
        self.assertIn("74.6241", body)  # P&L per inference dollar
        self.assertIn("--", body)  # a ratio with no denominator
        self.assertNotIn("<", body)
        self.assertEqual(body, ResultsLedger.markdown(self.report))
        # Every table row has the same number of columns as its header.
        for block in body.split("\n\n"):
            rows = [line for line in block.splitlines() if line.startswith("|")]
            widths = {row.count("|") for row in rows}
            self.assertLessEqual(len(widths), 1, block[:120])

    def test_it_survives_an_empty_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = EventLog(Path(tmp) / "events.sqlite")
            report = ResultsLedger(log).report(DEFAULT_WINDOW_DAYS, NOW)
            self.assertEqual(report["desks"], {})
            body = markdown(report)
            self.assertIn("no desks in the window", body)
            self.assertIn("## Floor", body)
            log.close()


class CommandLine(AnalyticsCase):
    """`python3 -m ltcm report`, with the event log this fixture already built."""

    def setUp(self):
        from ltcm import __main__ as cli

        self.cli = cli
        original = cli._service
        self.addCleanup(setattr, cli, "_service", original)
        log, roster = self.log, self.manifests
        cli._service = lambda args: SimpleNamespace(
            log=log, manifests=roster, close=lambda: None
        )

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_the_parser_accepts_the_documented_flags(self):
        args = self.cli.build_parser().parse_args(
            ["report", "--days", "3", "--markdown", "--write", "docs/runs/"]
        )
        self.assertEqual((args.command, args.days, args.markdown), ("report", 3, True))
        self.assertEqual(args.write, "docs/runs/")
        self.assertEqual(self.cli.build_parser().parse_args(["report"]).days, 7)

    def test_json_by_default(self):
        code, out, _ = self.run_cli(["report", "--days", "30"])
        self.assertEqual(code, 0)
        body = json.loads(out)
        self.assertEqual(sorted(body), ["by_generation", "desks", "families", "floor", "generated_at", "profiles", "window", "window_days"])
        self.assertEqual(body["window_days"], 30)
        self.assertIn("mullins", body["desks"])

    def test_markdown_and_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = self.run_cli(
                ["--root", tmp, "report", "--days", "30", "--markdown", "--write", "runs"]
            )
            self.assertEqual(code, 0)
            self.assertTrue(out.startswith("# Lab report -- "))
            written = sorted(Path(tmp, "runs").glob("*-lab-report.md"))
            self.assertEqual(len(written), 1)
            self.assertEqual(written[0].read_text(encoding="utf-8"), out.rstrip("\n") + "\n")
            self.assertIn("written", err)
            # Writing a report is a file, not a commit: nothing else in the tree moved.
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["runs"])

    def test_an_impossible_window_is_refused(self):
        code, _, err = self.run_cli(["report", "--days", "0"])
        self.assertEqual(code, 2)
        self.assertIn("--days", err)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
