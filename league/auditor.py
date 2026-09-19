"""The auditor: a veto before real money, never a pick.

When an agent's paper record clears the constitution's test, the House does not promote it: it
hands the frontier model the agent's whole evidence packet and asks it to find what is wrong.
Look-ahead, fee errors, stale or thin data, a record that depends on one lucky fill, exposure
that duplicates what is already live, a strategy that breaks a rule it has not been caught
breaking yet. One blocker is a veto. The audit is charged to the agent's credits at cost, so an
agent pays for the look that may end its climb.

The gate must earn its keep too. A vetoed agent stays on paper, so its record after the veto is
exactly what the veto cost or saved: `score()` writes that counterfactual to the ledger, scaled to
the micro-real stake, next to what the approved agents really made.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping

from .agents import Agent
from .constitution import CONSTITUTION
from .evaluator import Verdict
from .frontier import Frontier, FrontierError
from .ledger import Ledger

SYSTEM = """You are the auditor of a small real-money trading league. An agent (a strategy program) has passed the
statistical test on paper and is about to trade real money at $1 to $10 a position. You are the last check.
You do not pick trades and you do not judge whether the idea is clever. You hunt for reasons the evidence is
not what it seems:
- look-ahead or any use of information not available at decision time;
- fee, spread or fill assumptions the live venue will not honour (the paper venue fills market orders at the
  touch with unlimited depth; Kalshi shadow fills are conservative maker fills; real queues are worse);
- a record carried by one or two outsized trades, or by a regime that has ended;
- too few independent observations for the claim, or blocks that are not independent;
- behaviour the code can exhibit that the record has not shown yet: averaging down, unbounded adds, size that
  grows after losses, orders that would breach the $75 order cap, shorting, leverage, trading closed markets;
- a mismatch between what the code does and what the record shows (e.g. the code sends market orders but the
  fills are maker fills), or between the stated reasons and the trades;
- exposure that duplicates agents already trading real money.
Answer with ONE JSON object and nothing else:
{"approve": true|false, "confidence": 0.0-1.0, "summary": "two or three plain sentences",
 "findings": [{"severity": "blocker"|"concern"|"note", "issue": "...", "evidence": "what in the packet shows it"}]}
Approve only if you found no blocker. When in doubt, veto: a vetoed agent keeps trading on paper and can return."""


class Auditor:
    def __init__(self, frontier: Frontier, ledger: Ledger, economy: Any, evaluator: Any, *, live_agents=lambda: []):
        self.frontier = frontier
        self.ledger = ledger
        self.economy = economy
        self.evaluator = evaluator
        self.live_agents = live_agents  # () -> [{"agent", "family", "niche"}] already on real money

    # ----------------------------------------------------------------- packet
    def packet(self, agent: Agent, verdict: Verdict) -> dict[str, Any]:
        book = str(verdict.numbers.get("book") or "")
        fills = [
            {k: e.payload.get(k) for k in ("side", "quantity", "price", "fee_usd", "fee_quantity", "liquidity", "source", "realized", "reason")}
            | {"at": e.at, "symbol": (e.payload.get("instrument") or {}).get("symbol"), "leg": (e.payload.get("instrument") or {}).get("right")}
            for e in self.ledger.iter(kinds=("book.fill", "book.settle"), agent=agent.id)
            if e.payload.get("book") == book and e.payload.get("source") != "dust"
        ]
        refused = [e.payload.get("reasons") for e in self.ledger.iter(kinds="book.refused", agent=agent.id)][-20:]
        blocks = self.evaluator.blocks(agent.id, book=book)
        trials = [e.payload for e in self.ledger.iter(kinds="eval.trial", agent=agent.id)]
        return {
            "agent": {"id": agent.id, "family": agent.family, "niche": agent.niche, "generation": agent.generation, "parent": agent.parent},
            "strategy_code": agent.code,
            "params": agent.params,
            "needs": agent.needs,
            "test_passed": verdict.numbers,
            "thresholds": CONSTITUTION["ladder"],
            "family_trials": len(self.evaluator.family_trials(agent.family)),
            "replay_trials": [{k: t.get(k) for k in ("sharpe", "deflated_sharpe", "trials", "trades", "return_pct", "max_drawdown", "passed", "reasons")} for t in trials][-10:],
            "paper_blocks": [{"key": b["key"], "log_growth": b["log_growth"], "active": b["active"]} for b in blocks][-200:],
            "paper_fills": fills[-120:],
            "refused_orders": refused,
            "already_on_real_money": self.live_agents(),
            "micro_real_limits": CONSTITUTION["rungs"]["2"],
        }

    # ------------------------------------------------------------------ audit
    def audit(self, agent: Agent, verdict: Verdict) -> dict[str, Any]:
        packet = self.packet(agent, verdict)
        try:
            answer = self.frontier.ask(system=SYSTEM, user=json.dumps(packet, default=str), agent=f"audit:{agent.id}", max_output_tokens=6000)
        except FrontierError as exc:
            # No audit, no promotion: a gate that fails open is not a gate.
            self.ledger.append("audit.verdict", {"approve": False, "error": str(exc)[:300], "summary": "the audit could not run; the agent stays on paper"}, agent=agent.id)
            return {"approve": False, "error": str(exc)}
        if answer.cost_usd > 0:
            self.economy.charge(agent.id, answer.cost_usd, "frontier audit", detail={"model": answer.model})
        try:
            result = answer.json()
        except FrontierError:
            result = {"approve": False, "summary": "the auditor's answer could not be read", "findings": []}
        findings = [f for f in (result.get("findings") or []) if isinstance(f, dict)][:20]
        blockers = [f for f in findings if str(f.get("severity")).lower() == "blocker"]
        approve = bool(result.get("approve")) and not blockers
        row = {
            "approve": approve,
            "confidence": result.get("confidence"),
            "summary": str(result.get("summary") or "")[:1200],
            "findings": [{"severity": str(f.get("severity"))[:12], "issue": str(f.get("issue"))[:400], "evidence": str(f.get("evidence"))[:400]} for f in findings],
            "cost_usd": format(answer.cost_usd, "f"),
            "model": answer.model,
            "book": packet["test_passed"].get("book"),
            "blocks_at_audit": len(packet["paper_blocks"]),
        }
        self.ledger.append("audit.verdict", row, agent=agent.id)
        return row

    # ------------------------------------------------------------------ score
    def score(self) -> dict[str, Any]:
        """What the gate has been worth: each veto scored as if the agent had been let through."""
        scale = Decimal(CONSTITUTION["rungs"]["2"]["stake_usd"]) / Decimal(CONSTITUTION["rungs"]["1"]["stake_usd"])
        avoided = Decimal(0)  # losses a veto kept off the real account (positive is good)
        missed = Decimal(0)  # gains a veto kept off it
        cost = Decimal(0)
        vetoes = approvals = 0
        for entry in self.ledger.iter(kinds="audit.verdict"):
            p = entry.payload
            cost += Decimal(str(p.get("cost_usd") or 0))
            if p.get("error"):
                continue
            if p.get("approve"):
                approvals += 1
                continue
            vetoes += 1
            book = p.get("book")
            pnl = Decimal(0)
            for block in self.ledger.iter(kinds="eval.block", agent=entry.agent):
                if block.seq > entry.seq and block.payload.get("book") == book:
                    pnl += Decimal(str(block.payload["end_equity"])) - Decimal(str(block.payload["start_equity"])) - Decimal(str(block.payload.get("flow") or 0))
            scaled = pnl * scale
            if scaled < 0:
                avoided += -scaled
            else:
                missed += scaled
        result = {
            "vetoes": vetoes, "approvals": approvals, "audit_cost_usd": format(cost, "f"),
            "losses_avoided_usd": format(avoided.quantize(Decimal("0.0001")), "f"),
            "gains_missed_usd": format(missed.quantize(Decimal("0.0001")), "f"),
            "net_value_usd": format((avoided - missed - cost).quantize(Decimal("0.0001")), "f"),
        }
        self.ledger.append("audit.counterfactual", result)
        return result
