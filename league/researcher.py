"""The research loop: a cheap Sail model thinking on one agent's behalf, at that agent's expense.

The House runs the loop (the agent's box has no network and no key). Every token is charged to
the agent's credits at Sail's prices; every tool call the model makes is executed by the House:
web search, the shared library, the playbook, the tool-request queue, and `replay`, which runs
candidate code through the mechanical simulator in the agent's own box and is counted as a trial.

What a research pass can change: on rung 0 the agent adopts code that passes replay. Above rung
0 the agent's record belongs to its code, so passing code becomes a `candidate` the House may
fork into a child if the parent can afford the endowment.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Mapping

from .agents import Agent
from .commons import SEARCH_CHARGE_USD, Commons
from .ledger import Ledger
from .safety import CodeRefused, check_code

ZERO = Decimal(0)

TOOLS: list[dict[str, Any]] = [
    {"name": "web_search", "description": "Search the web. Costs credits. Use it to check a fact or find evidence for an idea, not to browse.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "library_search", "description": "Search the research library every agent shares. Free. Notes written by your own specialty come first. Look here before paying for a web search.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "library_read", "description": "Read one library note by id or exact title.",
     "parameters": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}},
    {"name": "library_write", "description": "Save a finding for every agent: what you learned, the evidence, and what it implies for strategies.",
     "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "text": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["title", "text"]}},
    {"name": "playbook_read", "description": "Read the graveyard playbook: post-mortems of dead agents and the architect's lessons.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}},
    {"name": "request_tool", "description": "Ask the architect to build something the House does not offer (a data feed, an indicator, a venue feature). Say what and why.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}}, "required": ["name", "description"]}},
    {"name": "markets_now", "description": "See what your strategy sees right now: the live markets, quotes, bars or option chain of your specialty, your positions and working orders. Free. Look before you design: a rule about spreads or prices should start from the spreads and prices that are really there.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "journal_write", "description": "Write a note to your FUTURE SELF. Your journal is handed back to you at the start of every research pass, and your children inherit it: what you tried, what the result was, what you will check next, what not to repeat. Keep each entry short and dated by the House.",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "replay", "description": "Run candidate strategy code through the mechanical replay over recorded history. It is COUNTED AS A TRIAL against your whole family, and costs sandbox seconds. Code that PASSES is born as your child at once (the House stakes it if you cannot). Give the complete strategy file and what you changed and why.",
     "parameters": {"type": "object", "properties": {"code": {"type": "string"}, "purpose": {"type": "string"}}, "required": ["code", "purpose"]}},
    {"name": "finish", "description": "End this research pass with one or two sentences on what you concluded.",
     "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}},
]


@dataclass
class Pass:
    agent: str
    turns: int = 0
    cost_usd: Decimal = ZERO
    summary: str = ""
    reason: str = "max_turns"
    candidate: dict[str, Any] | None = None  # {"code", "needs", "params", "result", "purpose"}
    trials: int = 0
    calls: list[str] = field(default_factory=list)


class Researcher:
    def __init__(
        self,
        *,
        ledger: Ledger,
        provider: Any,  # ltcm.provider.Provider, or anything with its `respond`
        commons: Commons,
        economy: Any,
        rules: str,
        contract: str,
        run_replay: Callable[[Agent, str], dict[str, Any]],  # (agent, code) -> {"verdict", "numbers", "needs", "params", "seconds"}
        settings: Mapping[str, Any],
        clock=time.time,
        specialty: Callable[[Agent], str] | None = None,  # (agent) -> what is known of its niche
        look: Callable[[Agent], dict[str, Any]] | None = None,  # (agent) -> what its strategy sees now
        lineage: Callable[[str], list[str]] | None = None,  # (agent id) -> itself, its parent, its parent's parent...
    ):
        self.ledger = ledger
        self.provider = provider
        self.commons = commons
        self.economy = economy
        self.rules = rules
        self.contract = contract
        self.run_replay = run_replay
        self.settings = dict(settings)
        self.clock = clock
        self.specialty = specialty
        self.look = look
        self.lineage = lineage

    # ------------------------------------------------------------------ prompt
    def _system(self) -> str:
        return (
            self.rules
            + "\n\nTHE STRATEGY CONTRACT (the file format your code must follow)\n\n"
            + self.contract
            + "\n\nHOW TO WORK. Call one tool per turn. Start from your journal and your own recent trades: they are what you know that "
            "nobody else does. Look at the live view (`markets_now`) before you design a rule about prices or spreads. Read the library "
            "and the playbook before paying for a search. Only call `replay` when you have a specific, reasoned change: each call is a "
            "counted trial, and its answer says WHERE the strategy won and lost, not only whether. Write a library note when you learn "
            "something another agent could use, and a journal note (`journal_write`) for your future self: you keep nothing else of this "
            "pass. End with `finish`."
        )

    def _state(self, agent: Agent, standing: Mapping[str, Any]) -> str:
        brief = self.specialty(agent) if self.specialty else ""
        journal = self.journal(agent.id)
        pages = "\n".join(f"- [{row['at'][:16]} {row['by']}] {row['text']}" for row in journal)
        return (
            f"You are {agent.id} (family {agent.family}, niche {agent.niche}, generation {agent.generation}).\n"
            + (f"\n{brief}\n\n" if brief else "")
            + (f"YOUR JOURNAL (what you and your ancestors wrote to yourselves, oldest first; add to it with `journal_write`):\n{pages}\n\n" if pages else
               "YOUR JOURNAL is empty. Before you finish, write yourself a note with `journal_write`: you will remember nothing else of this pass.\n\n")
            + f"Your standing: {json.dumps(standing, default=str)}\n\n"
            f"Your current strategy file:\n```python\n{agent.code}\n```\n"
            f"Your parameters: {json.dumps(agent.params)}\n"
            "Decide what, if anything, is worth your credits right now."
        )

    # ----------------------------------------------------------------- journal
    def journal(self, agent_id: str, *, entries: int = 14, chars: int = 700) -> list[dict[str, Any]]:
        """An agent's persistent memory: the notes it wrote to itself and the conclusion of each
        research pass, its ancestors' before its own, newest kept. It lives on the ledger, so it
        survives a restart, a new box and the agent's own death (its children read it)."""
        line = list(reversed((self.lineage(agent_id) if self.lineage else None) or [agent_id]))
        rows = []
        for name in line:
            for entry in self.ledger.iter(kinds="agent.research", agent=name):
                p = entry.payload
                text = p.get("text") if p.get("tool") == "journal" else (p.get("summary") if p.get("tool") == "summary" else None)
                if text and len(str(text).strip()) >= 20:  # "done" is not a memory
                    rows.append({"at": entry.at, "by": name, "text": str(text).strip()[:chars]})
        return rows[-entries:]

    # -------------------------------------------------------------------- pass
    def research(self, agent: Agent, standing: Mapping[str, Any], *, session: str) -> Pass:
        out = Pass(agent.id)
        conversation: list[dict[str, Any]] = [
            {"role": "system", "content": self._system()},
            {"role": "user", "content": self._state(agent, standing)},
        ]
        nudged = False
        for turn in range(int(self.settings.get("max_turns", 6))):
            balance = self.economy.balance(agent.id)
            if balance <= Decimal(str(self.settings.get("min_credits_usd", "0.10"))):
                out.reason = "credits"
                break
            try:
                response = self.provider.respond(
                    str(self.settings.get("profile", "flash_flex")),
                    conversation,
                    tools=TOOLS,
                    desk_id=agent.id,
                    session_id=session,
                    request_key=f"{session}:{turn}",
                    reasoning_effort=str(self.settings.get("reasoning_effort", "low")),
                    max_output_tokens=int(self.settings.get("max_output_tokens", 4096)),
                    desk_cap_usd_per_day=balance,  # an agent can never spend credits it does not have
                    cache_key=f"league:{agent.family}",
                )
            except Exception as exc:  # noqa: BLE001 - a provider failure ends the pass, not the House
                out.reason = f"provider: {getattr(exc, 'code', type(exc).__name__)}"
                break
            out.turns = turn + 1
            cost = Decimal(str(response.cost_usd or 0))
            if cost > 0:
                out.cost_usd += cost
                self.economy.charge(agent.id, cost, "research tokens", detail={"session": session, "turn": turn}, id=f"tokens:{session}:{turn}")
            conversation.extend(response.output_items)
            text = (response.output_text or "").strip()
            if text:
                self.ledger.append("agent.thought", {"text": text[:4000], "session": session, "phase": "research"}, agent=agent.id)
            if response.status in ("failed", "cancelled") or response.incomplete:
                out.reason = "provider: incomplete"
                break
            calls = response.function_calls
            if not calls:
                if nudged:
                    out.reason = "no tool call"
                    break
                nudged = True
                conversation.append({"role": "user", "content": "Call a tool. If you are done, call `finish`."})
                continue
            finished = False
            for call in calls:
                result = {"error": call.error} if call.error else self._execute(agent, call.name, call.arguments, out, session)
                out.calls.append(call.name)
                conversation.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result, default=str)[:12000]})
                if call.name == "finish":
                    finished = True
            if finished:
                out.reason = "finished"
                break
        self.ledger.append(
            "agent.research",
            {"tool": "summary", "session": session, "turns": out.turns, "cost_usd": format(out.cost_usd, "f"), "trials": out.trials,
             "summary": out.summary[:1200], "reason": out.reason, "candidate": bool(out.candidate)},
            agent=agent.id,
        )
        return out

    # ------------------------------------------------------------------- tools
    def _execute(self, agent: Agent, name: str, args: Mapping[str, Any], out: Pass, session: str) -> dict[str, Any]:
        public = {k: (str(v)[:200] if k != "code" else f"{len(str(v))} characters") for k, v in dict(args or {}).items() if k != "text"}
        self.ledger.append("agent.research", {"tool": name, "arguments": public, "session": session}, agent=agent.id)
        if name == "markets_now":
            if self.look is None:
                return {"error": "the House cannot show the live view here"}
            try:
                return _trim(self.look(agent))
            except Exception as exc:  # noqa: BLE001 - a venue that is down is an answer
                return {"error": f"the live view could not be read: {type(exc).__name__}: {str(exc)[:160]}"}
        if name == "journal_write":
            text = str(args.get("text") or "").strip()[:1500]
            if len(text) < 20:
                return {"error": "write at least a sentence"}
            self.ledger.append("agent.research", {"tool": "journal", "text": text, "session": session}, agent=agent.id)
            return {"saved": True, "note": "you will be shown this at the start of every pass from now on"}
        if name == "web_search":
            self.economy.charge(agent.id, SEARCH_CHARGE_USD, "web search", detail={"query": str(args.get("query"))[:200]})
            return self.commons.web_search(str(args.get("query") or ""))
        if name == "library_search":
            return self.commons.library_search(str(args.get("query") or ""), niche=agent.specialty)
        if name == "library_read":
            return self.commons.library_read(str(args.get("title") or ""))
        if name == "library_write":
            return self.commons.library_write(agent.id, str(args.get("title") or ""), str(args.get("text") or ""), list(args.get("tags") or []), niche=agent.specialty)
        if name == "playbook_read":
            return self.commons.playbook_read(str(args.get("query") or ""))
        if name == "request_tool":
            return self.commons.request_tool(agent.id, str(args.get("name") or ""), str(args.get("description") or ""))
        if name == "finish":
            out.summary = str(args.get("summary") or "")[:1200]
            return {"ok": True}
        if name == "replay":
            code = str(args.get("code") or "")
            try:
                check_code(code)
            except CodeRefused as exc:
                return {"error": f"code refused (not counted as a trial): {exc}"}
            outcome = self.run_replay(agent, code)
            out.trials += 1
            numbers = dict(outcome.get("numbers") or {})
            if outcome.get("passed"):
                out.candidate = {"code": code, "needs": outcome.get("needs") or {}, "params": outcome.get("params") or {},
                                 "numbers": numbers, "purpose": str(args.get("purpose") or "")[:600]}
            return {"passed": bool(outcome.get("passed")), "reasons": numbers.get("reasons"), "trials_in_family": numbers.get("trials"),
                    "deflated_sharpe": numbers.get("deflated_sharpe"), "sharpe": numbers.get("sharpe"), "trades": numbers.get("trades"),
                    "return_pct": numbers.get("return_pct"), "max_drawdown": numbers.get("max_drawdown"), "fees_usd": numbers.get("fees_usd"),
                    "oos_mean_log_growth": numbers.get("oos_mean_log_growth"), "error": outcome.get("error"),
                    # Where it won and lost: by series or symbol, by how long before the end it got in, and its worst trades.
                    "digest": outcome.get("digest"), "note": numbers.get("note")}
        return {"error": f"no such tool {name!r}"}


def _trim(ctx: Mapping[str, Any]) -> dict[str, Any]:
    """The live view, cut to what a model can read: the busiest 40 markets, the 40 nearest option
    contracts, the last 30 bars of each symbol."""
    out = {k: v for k, v in dict(ctx).items() if k not in ("markets", "chain", "bars", "memory", "params")}
    if "markets" in ctx:
        rows = sorted(ctx["markets"] or [], key=lambda m: -(m.get("volume_24h") or 0))
        out["markets"] = rows[:40]
        out["markets_shown"] = f"{min(len(rows), 40)} busiest of {len(rows)}"
    if "chain" in ctx:
        out["chain"] = (ctx["chain"] or [])[:40]
    if "bars" in ctx:
        out["bars"] = {symbol: (bars or [])[-30:] for symbol, bars in (ctx["bars"] or {}).items()}
    return out
