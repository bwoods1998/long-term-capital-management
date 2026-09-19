"""Adversarial tests of the auditor: a veto before real money that must fail closed, charge the
agent what the look cost, leave a full `audit.verdict` row, send the frontier model the evidence
and no secret, and score its own vetoes honestly.

A real `Frontier` is used with a fake `opener`, so the request that would reach the gateway is
what is inspected. The ledger, the evaluator and the economy are the real ones.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from decimal import Decimal
from pathlib import Path

from league.agents import Agent
from league.auditor import SYSTEM, Auditor
from league.constitution import CONSTITUTION
from league.economy import Economy
from league.evaluator import Evaluator, Verdict
from league.frontier import AGENT_HEADER, COST_HEADER, MODEL, Frontier
from league.ledger import Ledger

GATEWAY = "https://gateway.example.test"
SECRET = "gw-token-5f1c-DO-NOT-LEAK"
CODE = 'NEEDS = {"venue": "kalshi", "horizon": "hour", "style": "favourites"}\nPARAMS = {"floor": 0.93}\n\ndef decide(ctx):\n    return {"intents": []}\n'


class FakeResponse:
    def __init__(self, payload, headers):
        self.body = json.dumps(payload).encode("utf-8")
        self.headers = dict(headers)

    def read(self, *_):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeOpener:
    def __init__(self, *script):
        self.script = list(script)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def says(answer, *, cost="0.0375", raw_text=None) -> FakeResponse:
    text = raw_text if raw_text is not None else json.dumps(answer)
    return FakeResponse({"output_text": text, "model": MODEL, "usage": {"output_tokens": 50}}, {COST_HEADER: cost})


def finding(severity, issue="an issue", evidence="the packet") -> dict:
    return {"severity": severity, "issue": issue, "evidence": evidence}


class AuditorCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.db")
        self.evaluator = Evaluator(self.ledger)
        self.economy = Economy(self.ledger)
        self.agent = self.make_agent("fav-1")
        self.economy.grant(self.agent.id, "5", "test grant")
        self.verdict = Verdict(self.agent.id, 1, "eligible", "the lower bound on its growth is above zero",
                               {"book": "kalshi-shadow", "blocks": 31, "active_blocks": 30, "lcb": 0.0011, "look": 3})

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def make_agent(self, agent_id) -> Agent:
        return Agent(id=agent_id, name=agent_id, family="favourites", venue="kalshi", horizon="hour", style="favourites", generation=2,
                     parent="fav-0", code=CODE, params={"floor": 0.93}, wake_minutes=15, born_at="2026-09-20T00:00:00.000Z",
                     needs={"venue": "kalshi", "horizon": "hour", "series": ["KXBTC"]})

    def auditor(self, *script, live_agents=lambda: []):
        self.opener = FakeOpener(*script)
        frontier = Frontier(GATEWAY, lambda: SECRET, opener=self.opener)
        return Auditor(frontier, self.ledger, self.economy, self.evaluator, live_agents=live_agents)

    def verdict_rows(self, agent=None):
        return [e.payload for e in self.ledger.iter(kinds="audit.verdict", agent=agent)]

    def charges(self, agent=None):
        return [e.payload for e in self.ledger.iter(kinds="credit.charge", agent=agent)]


class Approval(AuditorCase):
    def test_a_clean_answer_approves(self):
        answer = {"approve": True, "confidence": 0.8, "summary": "nothing found", "findings": [finding("note"), finding("concern")]}
        result = self.auditor(says(answer)).audit(self.agent, self.verdict)
        self.assertIs(result["approve"], True)
        self.assertEqual(self.verdict_rows(), [result])

    def test_one_blocker_vetoes_whatever_approve_says_and_in_any_case(self):
        for severity in ("blocker", "BLOCKER", "Blocker", "bLoCkEr"):
            answer = {"approve": True, "confidence": 0.99, "summary": "fine", "findings": [finding("note"), finding(severity, "look-ahead")]}
            result = self.auditor(says(answer)).audit(self.agent, self.verdict)
            self.assertIs(result["approve"], False, severity)
        self.assertTrue(all(row["approve"] is False for row in self.verdict_rows()))

    def test_approve_false_or_missing_vetoes(self):
        for answer in ({"approve": False, "findings": []}, {"findings": []}, {"approve": None}, {"approve": 0}, {}):
            result = self.auditor(says(answer)).audit(self.agent, self.verdict)
            self.assertIs(result["approve"], False, answer)

    def test_approve_must_be_the_json_true_not_a_truthy_string(self):
        # Regression: the gate once read `bool(result.get("approve"))`, so `"false"`, `"no"` and
        # `[false]` were approvals. Only the JSON literal `true` approves now.
        for value in ("false", "no", "False", "veto", [False], {"approve": False}):
            result = self.auditor(says({"approve": value, "summary": "do not promote", "findings": []})).audit(self.agent, self.verdict)
            self.assertIs(result["approve"], False, value)

    def test_a_blocker_beyond_the_twentieth_finding_still_vetoes(self):
        # Regression: findings were once cut to twenty BEFORE the search for blockers, so a blocker
        # listed 21st was dropped. All findings are searched now; only the ledger row is cut.
        findings = [finding("note", f"note {i}") for i in range(20)] + [finding("blocker", "the fills are look-ahead")]
        result = self.auditor(says({"approve": True, "summary": "ok", "findings": findings})).audit(self.agent, self.verdict)
        self.assertIs(result["approve"], False)

    def test_a_blocker_with_stray_whitespace_still_vetoes(self):
        # Regression: the severity was once compared without `strip()`, so "blocker " was no blocker.
        for severity in ("blocker ", " Blocker", "BLOCKER\n"):
            result = self.auditor(says({"approve": True, "findings": [finding(severity)]})).audit(self.agent, self.verdict)
            self.assertIs(result["approve"], False, repr(severity))

    def test_findings_that_are_not_objects_are_ignored_without_crashing(self):
        answer = {"approve": True, "summary": "ok", "findings": ["blocker: a string is not a finding", 7, None, finding("note")]}
        result = self.auditor(says(answer)).audit(self.agent, self.verdict)
        self.assertEqual(len(result["findings"]), 1)

    def test_findings_of_the_wrong_type_are_a_veto_not_a_crash(self):
        # Regression: `"findings": 3` once raised TypeError after the audit was charged and before any
        # `audit.verdict` row was written. Findings that are not a list are now read as none.
        for value in (3, True, 2.5):
            result = self.auditor(says({"approve": True, "findings": value})).audit(self.agent, self.verdict)
            self.assertIn("approve", result)


class FailsClosed(AuditorCase):
    def test_a_frontier_failure_is_a_veto_and_costs_the_agent_nothing(self):
        before = self.economy.balance(self.agent.id)
        failures = (
            urllib.error.HTTPError(GATEWAY, 402, "payment required", {}, io.BytesIO(b"the month's budget is spent")),
            urllib.error.HTTPError(GATEWAY, 403, "forbidden", {}, io.BytesIO(b"kill switch")),
            urllib.error.HTTPError(GATEWAY, 503, "unavailable", {}, io.BytesIO(b"upstream")),
            urllib.error.URLError("no route"),
            TimeoutError("slow"),
        )
        for failure in failures:
            if isinstance(failure, urllib.error.HTTPError):
                self.addCleanup(failure.close)
            result = self.auditor(failure).audit(self.agent, self.verdict)
            self.assertIs(result["approve"], False)
            self.assertTrue(result["error"])
        rows = self.verdict_rows(self.agent.id)
        self.assertEqual(len(rows), len(failures))
        for row in rows:
            self.assertIs(row["approve"], False)
            self.assertTrue(row["error"])
            self.assertIn("stays on paper", row["summary"])
            self.assertNotIn(SECRET, json.dumps(row))
        self.assertIn("402", rows[0]["error"])
        self.assertEqual(self.charges(), [])
        self.assertEqual(self.economy.balance(self.agent.id), before)

    def test_an_answer_that_cannot_be_read_is_a_veto_that_is_still_paid_for(self):
        before = self.economy.balance(self.agent.id)
        for text in ("I approve of this agent wholeheartedly.", "", '{"approve": true, "findings": [', "approve: true"):
            result = self.auditor(says(None, raw_text=text, cost="0.02")).audit(self.agent, self.verdict)
            self.assertIs(result["approve"], False, text)
            self.assertIn("could not be read", result["summary"])
            self.assertEqual(result["cost_usd"], "0.02")
        self.assertEqual(self.economy.balance(self.agent.id), before - Decimal("0.08"))

    def test_an_empty_frontier_response_is_a_veto(self):
        opener_response = FakeResponse({"output": []}, {COST_HEADER: "0.001"})
        result = self.auditor(opener_response).audit(self.agent, self.verdict)
        self.assertIs(result["approve"], False)


class CostAndRow(AuditorCase):
    def test_the_audit_is_charged_to_the_agents_credits(self):
        self.auditor(says({"approve": True, "findings": []}, cost="0.0375")).audit(self.agent, self.verdict)
        self.assertEqual(self.economy.balance(self.agent.id), Decimal("5") - Decimal("0.0375"))
        (charge,) = self.charges(self.agent.id)
        self.assertEqual((charge["usd"], charge["what"], charge["detail"]), ("0.03750000", "frontier audit", {"model": MODEL}))
        # A fresh fold of the ledger sees the same balance: the charge is a ledger fact.
        self.assertEqual(Economy(self.ledger).balance(self.agent.id), Decimal("5") - Decimal("0.0375"))

    def test_a_veto_is_charged_too_and_a_free_audit_writes_no_charge(self):
        self.auditor(says({"approve": False, "findings": [finding("blocker")]}, cost="0.05")).audit(self.agent, self.verdict)
        self.assertEqual(len(self.charges()), 1)
        self.auditor(says({"approve": True, "findings": []}, cost="0")).audit(self.agent, self.verdict)
        self.assertEqual(len(self.charges()), 1)

    def test_an_audit_can_take_an_agent_to_zero(self):
        poor = self.make_agent("poor")
        self.economy.grant("poor", "0.01", "test")
        self.auditor(says({"approve": True, "findings": []}, cost="0.04")).audit(poor, self.verdict)
        self.assertFalse(self.economy.alive("poor"))

    def test_the_ledger_row(self):
        for i in range(3):
            self.ledger.append("eval.block", {"book": "kalshi-shadow", "key": f"k{i}", "log_growth": 0.001, "active": True,
                                              "start_equity": 200.0, "end_equity": 200.2, "flow": 0.0}, agent=self.agent.id)
        answer = {"approve": True, "confidence": 0.75, "summary": "S" * 5000,
                  "findings": [{"severity": "concern-but-very-long-severity", "issue": "I" * 900, "evidence": "E" * 900, "extra": "dropped"}]}
        result = self.auditor(says(answer, cost="0.0375")).audit(self.agent, self.verdict)
        (row,) = self.verdict_rows(self.agent.id)
        self.assertEqual(row, result)
        self.assertEqual(set(row), {"approve", "confidence", "summary", "findings", "cost_usd", "model", "book", "blocks_at_audit"})
        self.assertEqual((row["approve"], row["confidence"], row["cost_usd"], row["model"]), (True, 0.75, "0.0375", MODEL))
        self.assertEqual((row["book"], row["blocks_at_audit"]), ("kalshi-shadow", 3))
        self.assertEqual(len(row["summary"]), 1200)
        (found,) = row["findings"]
        self.assertEqual(set(found), {"severity", "issue", "evidence"})
        self.assertEqual((len(found["severity"]), len(found["issue"]), len(found["evidence"])), (12, 400, 400))
        entry = list(self.ledger.iter(kinds="audit.verdict"))[0]
        self.assertEqual(entry.agent, self.agent.id)


class Packet(AuditorCase):
    def fill_ledger(self):
        book, agent = "kalshi-shadow", self.agent.id
        inst = {"asset_class": "event", "symbol": "KXBTC-26SEP2013-T64000", "right": "no", "venue": "kalshi"}
        self.ledger.append("book.stake", {"book": book, "usd": "200"}, agent=agent)
        self.ledger.append("book.fill", {"book": book, "source": "venue", "side": "buy", "quantity": "5", "price": "0.95", "fee_usd": "0.00", "fee_quantity": None,
                                         "liquidity": "maker", "realized": None, "reason": "a favourite", "instrument": inst, "order_id": "o-1",
                                         "intent_id": "i-1", "cash_delta": "-4.75", "_private": "never"}, agent=agent)
        self.ledger.append("book.settle", {"book": book, "instrument": inst, "result": "no", "quantity": "5", "pnl": "0.25", "reason": "a favourite"}, agent=agent)
        self.ledger.append("book.fill", {"book": book, "source": "dust", "side": "sell", "quantity": "0.0001", "price": "0", "instrument": inst}, agent=agent)
        self.ledger.append("book.fill", {"book": "kalshi", "source": "venue", "side": "buy", "quantity": "1", "price": "0.5", "instrument": inst}, agent=agent)
        self.ledger.append("book.fill", {"book": book, "source": "venue", "side": "buy", "quantity": "9", "price": "0.9", "instrument": inst}, agent="someone-else")
        self.ledger.append("book.refused", {"book": book, "reasons": ["over the order cap"]}, agent=agent)
        for i in range(4):
            self.ledger.append("eval.block", {"book": book, "key": f"2026-09-20T{i:02d}", "log_growth": 0.001 * i, "active": bool(i % 2),
                                              "start_equity": 200.0, "end_equity": 200.1, "flow": 0.0}, agent=agent)
        self.ledger.append("eval.block", {"book": "kalshi", "key": "other-book", "log_growth": -0.5, "active": True,
                                          "start_equity": 25.0, "end_equity": 15.0, "flow": 0.0}, agent=agent)
        self.ledger.append("eval.trial", {"family": "favourites", "sharpe": 0.4, "deflated_sharpe": 0.95, "trials": 3, "trades": 40,
                                          "return_pct": 3.0, "max_drawdown": 0.02, "passed": True, "reasons": [], "code_sha256": "abc"}, agent=agent)
        self.ledger.append("eval.trial", {"family": "favourites", "sharpe": 0.1, "passed": False}, agent="a-cousin")

    def test_the_packet_holds_the_evidence(self):
        self.fill_ledger()
        live = [{"agent": "fav-0", "family": "favourites", "niche": "kalshi/hour/favourites"}]
        packet = self.auditor(live_agents=lambda: live).packet(self.agent, self.verdict)
        self.assertEqual(packet["strategy_code"], CODE)
        self.assertEqual(packet["params"], {"floor": 0.93})
        self.assertEqual(packet["needs"], self.agent.needs)
        self.assertEqual(packet["agent"], {"id": "fav-1", "family": "favourites", "niche": "kalshi/hour/favourites", "generation": 2, "parent": "fav-0"})
        self.assertEqual(packet["thresholds"], CONSTITUTION["ladder"])
        self.assertEqual(packet["micro_real_limits"], CONSTITUTION["rungs"]["2"])
        self.assertEqual(packet["test_passed"], self.verdict.numbers)
        self.assertEqual(packet["family_trials"], 2)  # the cousin's trial counts against the family
        self.assertEqual([t["sharpe"] for t in packet["replay_trials"]], [0.4])  # but only its own are listed
        self.assertEqual([b["key"] for b in packet["paper_blocks"]], [f"2026-09-20T{i:02d}" for i in range(4)])
        self.assertEqual(packet["paper_blocks"][1], {"key": "2026-09-20T01", "log_growth": 0.001, "active": True})
        self.assertEqual(len(packet["paper_fills"]), 2)  # its buy and its settlement: no dust, no other book, no other agent
        buy, settled = packet["paper_fills"]
        self.assertEqual((buy["side"], buy["quantity"], buy["price"], buy["liquidity"], buy["source"], buy["reason"]), ("buy", "5", "0.95", "maker", "venue", "a favourite"))
        self.assertEqual((buy["symbol"], buy["leg"]), ("KXBTC-26SEP2013-T64000", "no"))
        self.assertTrue(buy["at"])
        self.assertEqual(settled["symbol"], "KXBTC-26SEP2013-T64000")
        self.assertEqual(packet["refused_orders"], [["over the order cap"]])
        self.assertEqual(packet["already_on_real_money"], live)

    def test_the_packet_is_bounded(self):
        book, agent = "kalshi-shadow", self.agent.id
        for i in range(210):
            self.ledger.append("eval.block", {"book": book, "key": f"k{i:04d}", "log_growth": 0.0, "active": True, "start_equity": 1.0, "end_equity": 1.0}, agent=agent)
        for i in range(130):
            self.ledger.append("book.fill", {"book": book, "source": "venue", "side": "buy", "quantity": str(i)}, agent=agent)
        for i in range(25):
            self.ledger.append("book.refused", {"book": book, "reasons": [f"r{i}"]}, agent=agent)
        for i in range(12):
            self.ledger.append("eval.trial", {"family": "favourites", "sharpe": 0.01 * i, "passed": False}, agent=agent)
        packet = self.auditor().packet(self.agent, self.verdict)
        self.assertEqual((len(packet["paper_blocks"]), packet["paper_blocks"][-1]["key"]), (200, "k0209"))
        self.assertEqual((len(packet["paper_fills"]), packet["paper_fills"][-1]["quantity"]), (120, "129"))
        self.assertEqual((len(packet["refused_orders"]), packet["refused_orders"][-1]), (20, ["r24"]))
        self.assertEqual((len(packet["replay_trials"]), packet["replay_trials"][-1]["sharpe"]), (10, 0.11))

    def test_what_reaches_the_gateway_is_the_packet_and_no_secret(self):
        self.fill_ledger()
        auditor = self.auditor(says({"approve": True, "findings": []}))
        auditor.audit(self.agent, self.verdict)
        (request,) = self.opener.requests
        headers = {k.lower(): v for k, v in request.header_items()}
        self.assertEqual(headers[AGENT_HEADER.lower()], "audit-fav-1")
        self.assertEqual(headers["authorization"], "Bearer " + SECRET)  # the only place the token may appear
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "gpt-6-astra")
        self.assertEqual(body["max_output_tokens"], 6000)
        system, user = body["input"]
        self.assertEqual((system["role"], system["content"]), ("system", SYSTEM))
        self.assertEqual(user["role"], "user")
        sent = json.loads(user["content"])
        self.assertEqual(sent, json.loads(json.dumps(auditor.packet(self.agent, self.verdict), default=str)))
        text = request.data.decode("utf-8")
        self.assertNotIn(SECRET, text)
        lowered = user["content"].lower()
        for word in ("bearer", "authorization", "api_key", "apikey", "secret", "password", "token", "_private", "never", "order_id", "intent_id"):
            self.assertNotIn(word, lowered, word)

    def test_no_row_the_audit_writes_holds_the_token(self):
        self.auditor(says({"approve": True, "findings": []})).audit(self.agent, self.verdict)
        refusal = urllib.error.HTTPError(GATEWAY, 500, "x", {}, io.BytesIO(b"boom"))
        self.addCleanup(refusal.close)
        self.auditor(refusal).audit(self.agent, self.verdict)
        for entry in self.ledger.iter():
            self.assertNotIn(SECRET, json.dumps(entry.payload))

    def test_a_verdict_without_a_book_still_makes_a_packet(self):
        packet = self.auditor().packet(self.agent, Verdict(self.agent.id, 1, "eligible", "r", {}))
        self.assertEqual((packet["paper_blocks"], packet["paper_fills"]), ([], []))


class Score(AuditorCase):
    def audit_row(self, agent, approve, *, cost="0.05", book="paper", error=None):
        row = {"approve": approve, "cost_usd": cost, "book": book}
        if error:
            row = {"approve": False, "error": error, "summary": "the audit could not run"}
        return self.ledger.append("audit.verdict", row, agent=agent)

    def paper_block(self, agent, start, end, *, flow=0.0, book="paper"):
        return self.ledger.append("eval.block", {"book": book, "key": f"k{self.ledger.head()[0]}", "start_equity": start, "end_equity": end,
                                                 "flow": flow, "log_growth": 0.0, "active": True}, agent=agent)

    def test_a_veto_that_kept_a_loss_off_the_real_account(self):
        self.paper_block("loser", 200.0, 230.0)  # before the veto: not the gate's doing
        self.audit_row("loser", False, cost="0.05")
        self.paper_block("loser", 200.0, 196.0)
        self.paper_block("loser", 196.0, 192.0)
        result = self.auditor().score()
        # -$8 on a $200 paper stake is -$1 on the $25 micro-real stake.
        self.assertEqual(result, {"vetoes": 1, "approvals": 0, "audit_cost_usd": "0.05", "losses_avoided_usd": "1.0000",
                                  "gains_missed_usd": "0.0000", "net_value_usd": "0.9500"})
        self.assertEqual([e.payload for e in self.ledger.iter(kinds="audit.counterfactual")], [result])

    def test_a_veto_that_kept_a_gain_off_it(self):
        self.audit_row("winner", False, cost="0.05")
        self.paper_block("winner", 200.0, 216.0)
        result = self.auditor().score()
        self.assertEqual((result["losses_avoided_usd"], result["gains_missed_usd"], result["net_value_usd"]), ("0.0000", "2.0000", "-2.0500"))

    def test_vetoes_approvals_errors_and_costs_add_up(self):
        self.audit_row("loser", False, cost="0.05")
        self.audit_row("winner", False, cost="0.07")
        self.audit_row("clean", True, cost="0.04")
        self.audit_row("unlucky", None, error="HTTP 503")
        self.paper_block("loser", 200.0, 184.0)  # -16 -> 2.00 avoided
        self.paper_block("winner", 200.0, 204.0)  # +4 -> 0.50 missed
        self.paper_block("clean", 200.0, 100.0)  # approved: its paper book is no counterfactual
        self.paper_block("unlucky", 200.0, 100.0)  # never audited: no verdict to score
        result = self.auditor().score()
        self.assertEqual((result["vetoes"], result["approvals"]), (2, 1))
        self.assertEqual(result["audit_cost_usd"], "0.16")
        self.assertEqual((result["losses_avoided_usd"], result["gains_missed_usd"]), ("2.0000", "0.5000"))
        self.assertEqual(result["net_value_usd"], "1.3400")

    def test_stake_flows_and_other_books_are_not_profit_or_loss(self):
        self.audit_row("a", False, cost="0")
        self.paper_block("a", 200.0, 120.0, flow=-80.0)  # the House took $80 back: no loss
        self.paper_block("a", 25.0, 5.0, book="real")  # another book
        result = self.auditor().score()
        self.assertEqual((result["losses_avoided_usd"], result["gains_missed_usd"], result["net_value_usd"]), ("0.0000", "0.0000", "0.0000"))

    def test_the_scale_is_the_micro_stake_over_the_paper_stake(self):
        scale = Decimal(CONSTITUTION["rungs"]["2"]["stake_usd"]) / Decimal(CONSTITUTION["rungs"]["1"]["stake_usd"])
        self.assertEqual(scale, Decimal("25") / Decimal("200"))
        self.audit_row("a", False, cost="0")
        self.paper_block("a", 200.0, 199.0)
        self.assertEqual(self.auditor().score()["losses_avoided_usd"], "0.1250")

    def test_an_empty_ledger_scores_zero(self):
        result = self.auditor().score()
        self.assertEqual(result, {"vetoes": 0, "approvals": 0, "audit_cost_usd": "0", "losses_avoided_usd": "0.0000",
                                  "gains_missed_usd": "0.0000", "net_value_usd": "0.0000"})

    def test_a_real_audit_feeds_the_score(self):
        auditor = self.auditor(says({"approve": False, "summary": "look-ahead", "findings": [finding("blocker")]}, cost="0.0375"))
        self.verdict = Verdict(self.agent.id, 1, "eligible", "r", {"book": "paper"})
        auditor.audit(self.agent, self.verdict)
        self.paper_block(self.agent.id, 200.0, 192.0)
        result = auditor.score()
        self.assertEqual((result["vetoes"], result["audit_cost_usd"], result["losses_avoided_usd"], result["net_value_usd"]), (1, "0.0375", "1.0000", "0.9625"))

    def test_an_agent_vetoed_twice_is_not_scored_twice_for_the_same_blocks(self):
        # Regression: `score()` once scored every veto row against every later block, so an agent
        # re-audited at each look had one paper loss counted once per veto ($2.00 avoided here, not
        # $1.00). Each agent now has one window, from its first veto to its approval.
        self.audit_row("loser", False, cost="0")
        self.paper_block("loser", 200.0, 200.0)
        self.audit_row("loser", False, cost="0")
        self.paper_block("loser", 200.0, 192.0)
        self.assertEqual(self.auditor().score()["losses_avoided_usd"], "1.0000")


if __name__ == "__main__":
    unittest.main()
