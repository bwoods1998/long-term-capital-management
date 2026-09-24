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

import hashlib
import json
from decimal import Decimal
from typing import Any, Mapping

from .agents import Agent
from .constitution import CONSTITUTION
from .evaluator import Verdict
from .frontier import Frontier, FrontierError
from .ledger import Ledger, canonical

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
Inspect book_accounting and recent_order_outcomes: a reconciled aggregate can conceal a negative baseline
offsetting an agent's phantom holding. Submitted exit intentions do not establish executed exits, and venue
rejections can explain an apparent strategy failure. Unresolved attribution invalidates affected performance.
paper_fills includes both executions and settlements; use each row's kind, cost, payout, pnl and result when present.
Since Sept 23, 2026 capital is the ladder: when promotion_context.allocation_context names the allocator,
the experiment is the allocator's BUNT (a small real stake: allocation_context.stake_usd, with its
max_position_usd and max_order_usd) or an agent's FIRST SWING (a stake sized by its evidence), inside the owner's
live grant for that venue (allocation_context.venue_capital_usd, venue_headroom_usd, fits). Judge capacity against
that envelope, not against the legacy $50 / four-agent tuition or the $60 micro_real_limits, which apply only when
no allocation_context is given. A real drawdown, hysteresis and a cooldown send a losing bunt back to paper.
When allocation_context.family_swing is true (since Sept 24, 2026), the experiment is a FAMILY SWING: every member
of the agent's family on real money is staked above the bunt (allocation_context.stake_usd each, ramp and caps in
allocation_context.ramp), because the family's pooled REAL record qualified. Judge that record in family_packet:
its independent events (one per event, whatever the strikes), the honest lower bound (for a favourites record the
loss-rate bound, not only the t bound), whether a few events or one member carry it, whether the fills behind it
would survive the larger size (family_packet.capacity), and whether the strategy code can behave in ways the
record has not shown. The agent's own record (paper_fills, from its real book here) is one member's part of it.
Answer with ONE JSON object and nothing else:
{"approve": true|false, "confidence": 0.0-1.0, "summary": "two or three plain sentences",
 "findings": [{"severity": "blocker"|"concern"|"note", "issue": "...", "evidence": "what in the packet shows it"}]}
Approve only if you found no blocker. When in doubt, veto: a vetoed agent keeps trading on paper and can return."""

EXECUTION_POLICY = {
    "entry_caps": "The House applies rung order and position caps to entries, including working buys and fees.",
    "reducing_exits": "Book.check exempts position-reducing sells from entry dollar caps. The risk engine checks held quantity including reserved sells, so an exit cannot reverse into a short position.",
    "gateway_exit_path": "Book._order_intent labels sells as exits; the gateway exempts that tag from entry dollar caps. Per-agent reducing-quantity validation is in the trusted House, not the gateway.",
    "source": "league/book.py:Book.check, Book._order_intent; ltcm/risk.py; gateway/lib/router.mjs",
    "interpretation": "A profitable holding may be sold above the $10 entry cap. These controls do not guarantee a fill, a price, a profitable edge or continuous venue availability."}


def order_outcomes(ledger: Ledger, agent: str, book: str, *, limit: int = 12) -> list[dict[str, Any]]:
    """Include refusals before submission as well as House orders attributed by their shares."""
    if limit <= 0:
        return []
    orders = {}
    for entry in ledger.iter(kinds=('book.order', 'book.refused')):
        p = entry.payload
        if p.get('book') != book:
            continue
        if entry.kind == 'book.refused':
            if entry.agent == agent:
                key = ('intent', p.get('intent_id') or entry.id)
                orders.pop(key, None)
                orders[key] = {'at': entry.at, **{k: p[k] for k in ('intent_id', 'instrument') if p.get(k) is not None},
                               'status': 'refused',
                               'reason': '; '.join(str(reason) for reason in p.get('reasons') or []),
                               'submitted_to_venue': False}
            continue
        if not any(s.get('agent') == agent for s in p.get('shares') or []):
            continue
        key = ('order', p.get('order_id'))
        previous = orders.pop(key, {})
        row = {'at': entry.at, **{k: p.get(k) for k in ('order_id', 'instrument', 'side', 'quantity', 'status', 'reason')}}
        if p.get('status') == 'unknown' and p.get('reason'):
            row['submission_error'] = p['reason']
        elif previous.get('submission_error'):
            row['submission_error'] = previous['submission_error']
        orders[key] = row
    return list(orders.values())[-limit:]


class Auditor:
    def __init__(self, frontier: Frontier, ledger: Ledger, economy: Any, evaluator: Any, *, live_agents=lambda: [], lineage=None,
                 book_evidence=None):
        self.frontier = frontier
        self.ledger = ledger
        self.economy = economy
        self.evaluator = evaluator
        self.live_agents = live_agents  # () -> [{"agent", "family", "niche"}] already on real money
        self.lineage = lineage  # (agent id) -> itself, its parent, its parent's parent...
        self.book_evidence = book_evidence

    @property
    def policy_digest(self):
        # Quotes, elapsed time and another profitable mark cannot buy a fresh audit. A changed
        # trusted policy/packet definition can: the earlier veto may have relied on a fixed defect.
        return hashlib.sha256(canonical({'system': SYSTEM, 'execution_policy': EXECUTION_POLICY,
            'ladder': CONSTITUTION['ladder'], 'rungs': CONSTITUTION['rungs'],
            'tuition': CONSTITUTION['tuition'], 'allocator': CONSTITUTION.get('allocator')}).encode()).hexdigest()

    # ----------------------------------------------------------------- packet
    def packet(self, agent: Agent, verdict: Verdict) -> dict[str, Any]:
        from .accounting import evidence_cutoffs
        book = str(verdict.numbers.get("book") or "")
        cutoff = evidence_cutoffs(self.ledger, agent.id).get(book, 0)
        fills = [
            {k: e.payload.get(k) for k in ("side", "quantity", "price", "fee_usd", "fee_quantity", "liquidity", "source", "realized", "reason",
                                         "cost", "payout", "pnl", "result", "opened_at", "flat")}
            | {"at": e.at, "kind": e.kind,
               "instrument": {k: v for k, v in (e.payload.get("instrument") or {}).items()
                              if k in ("asset_class", "symbol", "venue", "market_id", "right", "expiry", "strike", "multiplier", "currency")},
               "symbol": (e.payload.get("instrument") or {}).get("symbol"), "leg": (e.payload.get("instrument") or {}).get("right")}
            for e in self.ledger.iter(kinds=("book.fill", "book.settle"), agent=agent.id)
            if e.payload.get("book") == book and e.payload.get("source") != "dust" and e.seq > cutoff
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
                                                                          "position_diffs", "dust_booked", "detail", "ledger_seq", "attribution_issues")}}
        blocks = self.evaluator.blocks(agent.id, book=book)
        trials = [e.payload for e in self.ledger.iter(kinds="eval.trial", agent=agent.id)]
        return {
            "agent": {"id": agent.id, "family": agent.family, "niche": agent.niche, "generation": agent.generation, "parent": agent.parent},
            "strategy_code": agent.code,
            "params": agent.params,
            "needs": agent.needs,
            "test_passed": {k: v for k, v in verdict.numbers.items() if k != "family_packet"},  # the packet goes once, below
            "promotion_context": {"from_rung": verdict.rung, "to_rung": verdict.rung + 1,
                                  "paper_gate": CONSTITUTION["ladder"]["paper"],
                                  "completed_exposure_gate": CONSTITUTION['ladder'].get('completed_exposures'),
                                  "purpose": (str((verdict.numbers.get('allocation_context') or {}).get('purpose'))
                                              if (verdict.numbers.get('allocation_context') or {}).get('family_swing')
                                              else "the allocator's " + str((verdict.numbers.get('allocation_context') or {}).get('band_to') or 'bunt')
                                              + ": a small real stake sized inside the owner's per-venue grant"
                                              if (verdict.numbers.get('allocation_context') or {}).get('allocator')
                                              else "bounded micro-real experiment"),
                                  "tuition": (verdict.numbers.get('allocation_context') or {}).get('tuition', CONSTITUTION["tuition"]),
                                  "allocation_context": verdict.numbers.get('allocation_context')},
            "thresholds": CONSTITUTION["ladder"],
            "trials_in_its_line": len(self.evaluator.family_trials(agent.family, self.lineage(agent.id) if self.lineage else None)),
            "replay_trials": [{k: t.get(k) for k in ("sharpe", "deflated_sharpe", "trials", "trades", "return_pct", "max_drawdown", "passed", "reasons")} for t in trials][-10:],
            "paper_blocks": [{"key": b["key"], "log_growth": b["log_growth"], "active": b["active"]} for b in blocks][-200:],
            "paper_fills": fills[-120:],
            "refused_orders": [row["reasons"] for row in refused],
            "refused_order_history": refused,
            "latest_reconciliations": reconciliations,
            "book_accounting": self.book_evidence(agent.id, book) if self.book_evidence else None,
            "recent_order_outcomes": order_outcomes(self.ledger, agent.id, book),
            "already_on_real_money": self.live_agents(),
            "micro_real_limits": ({k: (verdict.numbers.get('allocation_context') or {}).get(k) for k in ("stake_usd", "max_position_usd", "max_order_usd")}
                                  if (verdict.numbers.get('allocation_context') or {}).get('allocator') else CONSTITUTION["rungs"]["2"]),
            "execution_policy": dict(EXECUTION_POLICY),
            "audit_policy_digest": self.policy_digest,
            # The family swing's first entry (C2, Sept 24, 2026) is audited on the family's REAL record: every
            # member's real closes, event by event, the pooled numbers and the capacity measured
            # (`Allocator._family_packet`). None for an agent's own promotion.
            "family_packet": verdict.numbers.get("family_packet"),
        }

    # ------------------------------------------------------------------ audit
    def audit(self, agent: Agent, verdict: Verdict, *, charge: bool = True) -> dict[str, Any]:
        """`charge=False`: the House pays (game.json `audit.house_pays`, Sept 23, 2026). The cost is
        still recorded on the verdict and still booked against the owner's frontier allowance."""
        packet = self.packet(agent, verdict)
        # Whose verdict this is when it judged a family swing (Sept 24, 2026), on every row this audit writes, a failed
        # call's included: the allocator reads it back after a restart (`Allocator._family_verdict_on_ledger`), and the
        # House's own audit readers never take it for the member's own verdict (review of #242).
        family = {"family_swing": packet["test_passed"]["family_swing"]} if packet["test_passed"].get("family_swing") else {}
        try:
            # 12,000, as Merton's own passes get: reasoning tokens are spent out of this budget
            # before a single character of the JSON is written, and an audit that runs out of room
            # is read as a veto by an agent that may have earned its seat.
            answer = self.frontier.ask(system=SYSTEM, user=json.dumps(packet, default=str), agent=f"audit-{agent.id}", max_output_tokens=12000)
        except FrontierError as exc:
            # No audit, no promotion: a gate that fails open is not a gate.
            self.ledger.append("audit.verdict", {"approve": False, "error": str(exc)[:300],
                "policy_digest": packet['audit_policy_digest'],
                "summary": "the audit could not run; the agent stays on paper", **family}, agent=agent.id)
            return {"approve": False, "error": str(exc)}
        if answer.cost_usd > 0 and charge:
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
            "policy_digest": packet['audit_policy_digest'],
            **({"error": "the auditor's answer could not be read"} if result.get("unreadable") else {}),
            "confidence": result.get("confidence"),
            "summary": str(result.get("summary") or "")[:1200],
            "findings": [{"severity": str(f.get("severity"))[:12], "issue": str(f.get("issue"))[:400], "evidence": str(f.get("evidence"))[:400]} for f in findings],
            "cost_usd": format(answer.cost_usd, "f"),
            "paid_by": "agent" if charge else "house",
            "model": answer.model,
            "book": packet["test_passed"].get("book"),
            "blocks_at_audit": len(packet["paper_blocks"]),
            **family,
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
            from .accounting import evidence_cutoffs
            cutoff = evidence_cutoffs(self.ledger, agent).get(window['book'], 0)
            pnl = Decimal(0)
            for block in self.ledger.iter(kinds="eval.block", agent=agent):
                first = int(block.payload.get("first_mark_seq") or block.seq)
                if first > max(window["since"], cutoff) and (window["until"] is None or first <= window["until"]) and block.payload.get("book") == window["book"]:
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
