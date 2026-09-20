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

SYSTEM = """You are the auditor of a small real-money trading league. An agent (a strategy program) has cleared
the constitution's paper gate and is being considered for a bounded micro-real experiment. You are the last check.
Read promotion_context and thresholds for the actual policy. The paper gate is a SCREEN, not proof of a positive
confidence bound: it requires forward activity, closed trades, positive growth and bounded recent drawdown.
A negative lower confidence bound can therefore be expected at this stage; by itself it is not a rule violation
or an automatic veto. The stricter confidence-bound gate protects scaled capital after micro-real evidence.
This experiment is constrained by micro_real_limits and the aggregate tuition limits in promotion_context.
Do not claim it establishes a profitable strategy. Judge whether the supplied accounting, data and execution
support the bounded experiment, and veto actual defects or unsupported safety assumptions.
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
Use the timestamps in refused_order_history and latest_reconciliations to distinguish historical failures from
the latest account state. A historical freeze alone does not prove the book is still frozen. A newer successful
reconciliation also does not by itself validate earlier incorrect marks: identify any remaining accounting defect.
Missing or old reconciliation evidence is an uncertainty to assess, not evidence of a successful reconciliation.
paper_fills includes both executions and settlements; use each row's kind, cost, payout, pnl and result when present.
Answer with ONE JSON object and nothing else:
{"approve": true|false, "confidence": 0.0-1.0, "summary": "two or three plain sentences",
 "findings": [{"severity": "blocker"|"concern"|"note", "issue": "...", "evidence": "what in the packet shows it"}]}
Approve only if you found no blocker. When in doubt, veto: a vetoed agent keeps trading on paper and can return."""


class Auditor:
    def __init__(self, frontier: Frontier, ledger: Ledger, economy: Any, evaluator: Any, *, live_agents=lambda: [], lineage=None):
        self.frontier = frontier
        self.ledger = ledger
        self.economy = economy
        self.evaluator = evaluator
        self.live_agents = live_agents  # () -> [{"agent", "family", "niche"}] already on real money
        self.lineage = lineage  # (agent id) -> itself, its parent, its parent's parent...

    # ----------------------------------------------------------------- packet
    def packet(self, agent: Agent, verdict: Verdict) -> dict[str, Any]:
        book = str(verdict.numbers.get("book") or "")
        fills = [
            {k: e.payload.get(k) for k in ("side", "quantity", "price", "fee_usd", "fee_quantity", "liquidity", "source", "realized", "reason",
                                         "cost", "payout", "pnl", "result", "opened_at", "flat")}
            | {"at": e.at, "kind": e.kind,
               "instrument": {k: v for k, v in (e.payload.get("instrument") or {}).items()
                              if k in ("asset_class", "symbol", "venue", "market_id", "right", "expiry", "strike", "multiplier", "currency")},
               "symbol": (e.payload.get("instrument") or {}).get("symbol"), "leg": (e.payload.get("instrument") or {}).get("right")}
            for e in self.ledger.iter(kinds=("book.fill", "book.settle"), agent=agent.id)
            if e.payload.get("book") == book and e.payload.get("source") != "dust"
        ]
        refused = [{"at": e.at, "book": book, "reasons": e.payload.get("reasons")}
                   for e in self.ledger.iter(kinds="book.refused", agent=agent.id) if e.payload.get("book") == book][-20:]
        # One latest fact per relevant book; a newer row on another venue must not replace it.
        reconciliations: dict[str, Any] = {name: None for name in (book, agent.venue) if name}
        for entry in self.ledger.iter(kinds="book.reconciled"):
            name = entry.payload.get("book")
            if name in reconciliations:
                reconciliations[name] = {"at": entry.at, "seq": entry.seq,
                                        **{k: entry.payload.get(k) for k in ("book", "ok", "cash_venue", "cash_expected", "cash_diff",
                                                                          "position_diffs", "dust_booked", "detail", "ledger_seq")}}
        blocks = self.evaluator.blocks(agent.id, book=book)
        trials = [e.payload for e in self.ledger.iter(kinds="eval.trial", agent=agent.id)]
        return {
            "agent": {"id": agent.id, "family": agent.family, "niche": agent.niche, "generation": agent.generation, "parent": agent.parent},
            "strategy_code": agent.code,
            "params": agent.params,
            "needs": agent.needs,
            "test_passed": verdict.numbers,
            "promotion_context": {"from_rung": verdict.rung, "to_rung": verdict.rung + 1,
                                  "paper_gate": CONSTITUTION["ladder"]["paper"],
                                  "purpose": "bounded micro-real experiment", "tuition": CONSTITUTION["tuition"]},
            "thresholds": CONSTITUTION["ladder"],
            "trials_in_its_line": len(self.evaluator.family_trials(agent.family, self.lineage(agent.id) if self.lineage else None)),
            "replay_trials": [{k: t.get(k) for k in ("sharpe", "deflated_sharpe", "trials", "trades", "return_pct", "max_drawdown", "passed", "reasons")} for t in trials][-10:],
            "paper_blocks": [{"key": b["key"], "log_growth": b["log_growth"], "active": b["active"]} for b in blocks][-200:],
            "paper_fills": fills[-120:],
            "refused_orders": [row["reasons"] for row in refused],
            "refused_order_history": refused,
            "latest_reconciliations": reconciliations,
            "already_on_real_money": self.live_agents(),
            "micro_real_limits": CONSTITUTION["rungs"]["2"],
        }

    # ------------------------------------------------------------------ audit
    def audit(self, agent: Agent, verdict: Verdict) -> dict[str, Any]:
        packet = self.packet(agent, verdict)
        try:
            # 12,000, as Merton's own passes get: reasoning tokens are spent out of this budget
            # before a single character of the JSON is written, and an audit that runs out of room
            # is read as a veto by an agent that may have earned its seat.
            answer = self.frontier.ask(system=SYSTEM, user=json.dumps(packet, default=str), agent=f"audit-{agent.id}", max_output_tokens=12000)
        except FrontierError as exc:
            # No audit, no promotion: a gate that fails open is not a gate.
            self.ledger.append("audit.verdict", {"approve": False, "error": str(exc)[:300], "summary": "the audit could not run; the agent stays on paper"}, agent=agent.id)
            return {"approve": False, "error": str(exc)}
        if answer.cost_usd > 0:
            self.economy.charge(agent.id, answer.cost_usd, "frontier audit", detail={"model": answer.model})
        try:
            result = answer.json()
        except FrontierError:
            # Not a verdict: the gate stays shut, but an agent is not made to wait out a day's
            # cooldown for the auditor's own malfunction (`House._audit_due` reads `error`).
            result = {"approve": False, "summary": "the auditor's answer could not be read", "findings": [], "unreadable": True}
        listed = result.get("findings") if isinstance(result.get("findings"), list) else []
        everything = [f for f in listed if isinstance(f, dict)]
        blockers = [f for f in everything if str(f.get("severity")).strip().lower() == "blocker"]
        findings = (blockers + [f for f in everything if f not in blockers])[:20]  # a blocker is never the one cut off
        # Only the literal JSON `true` with no blocker is an approval: "false", "no" and [false] are all truthy.
        approve = result.get("approve") is True and not blockers
        row = {
            "approve": approve,
            **({"error": "the auditor's answer could not be read"} if result.get("unreadable") else {}),
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
        # One window per agent: from its FIRST veto to its approval (or to now). An agent vetoed
        # three times is still one agent kept off the real account once.
        windows: dict[str, dict[str, Any]] = {}
        for entry in self.ledger.iter(kinds="audit.verdict"):
            p = entry.payload
            cost += Decimal(str(p.get("cost_usd") or 0))
            if p.get("error"):
                continue
            if p.get("approve") is True:
                approvals += 1
                if entry.agent in windows and windows[entry.agent]["until"] is None:
                    windows[entry.agent]["until"] = entry.seq
                continue
            vetoes += 1
            windows.setdefault(entry.agent, {"since": entry.seq, "until": None, "book": p.get("book")})
        for agent, window in windows.items():
            pnl = Decimal(0)
            for block in self.ledger.iter(kinds="eval.block", agent=agent):
                first = int(block.payload.get("first_mark_seq") or block.seq)
                if first > window["since"] and (window["until"] is None or first <= window["until"]) and block.payload.get("book") == window["book"]:
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
