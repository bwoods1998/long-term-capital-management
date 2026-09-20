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
from .ledger import Ledger, now_iso
from .safety import CodeRefused, check_code
from .sandbox import SandboxError

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
    {"name": "ask_merton", "description": "Hire Merton, the firm's theorist, to think about YOUR problem. He is the frontier model that writes the firm's strategies and audits every candidate for real money, and he is EXPENSIVE: this costs many times a research pass, out of your own credits, and hiring follows your rung's activity, credit and cooldown rules. He is shown everything you know (your file, your journal, your trades, your replays, your specialty) and answers with advice or with a whole strategy file you can then `replay`. Ask when you are stuck or when your idea may be structurally dead, not for a parameter.",
     "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}},
    {"name": "replay", "description": "Run candidate strategy code through the mechanical replay over recorded history. It is COUNTED AS A TRIAL against your lineage, and costs sandbox seconds. Code that PASSES is kept for the House to adopt or fork when this pass ends (the House stakes a child if you cannot). A later failed trial cannot discard a passing file. If you are on PAPER, your OWN rules have not fired for hours and you have no record to protect, code that merely TRADES on the tape can replace yours in place, failed verdict and all: a strategy that never acts cannot be measured, and paper is then the test. Give the complete strategy file and what you changed and why.",
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
    consulted: str = ""  # the strategy file Merton wrote for it this pass, if any


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
        merton: Any = None,  # the frontier model an agent may hire with its own credits
        rung: Callable[[str], int] | None = None,
        merton_settings: Mapping[str, Any] | None = None,
        look: Callable[[Agent], dict[str, Any]] | None = None,  # (agent) -> what its strategy sees now
        lineage: Callable[[str], list[str]] | None = None,  # (agent id) -> itself, its parent, its parent's parent...
        standing: Callable[[str], Mapping[str, Any]] | None = None,  # (agent id) -> {"active_blocks", "mean_growth"}
        house_budget: Callable[[], bool] | None = None,  # () -> whether the firm may spend on the frontier model today
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
        self.merton = merton
        self.rung = rung
        self.merton_settings = dict(merton_settings or {})
        self.look = look
        self.lineage = lineage
        self.standing = standing
        self.house_budget = house_budget

    # ------------------------------------------------------------------ prompt
    def _system(self) -> str:
        return (
            self.rules
            + "\n\nTHE STRATEGY CONTRACT (the file format your code must follow)\n\n"
            + self.contract
            + "\n\nHOW TO WORK. Call one tool per turn. Start from your journal and your own recent trades: they are what you know that "
            "nobody else does. Look at the live view (`markets_now`) before you design a rule about prices or spreads. Read the library "
            "and the playbook before paying for a search. THEN CHANGE SOMETHING: your line has about five to nine replay trials and they "
            "are worthless unspent, so if you can name a reasoned change and write the whole file, `replay` it this pass. Its answer says "
            "WHERE the strategy won and lost, not only whether, so even a failure buys you the next question. A pass that concludes 'wait "
            "and see' has spent your credits and bought nothing. Write a library note when you learn something another agent could use, "
            "and a journal note (`journal_write`) for your future self: you keep nothing else of this pass. End with `finish`."
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
            + (f"WHY YOU ARE AWAKE NOW: {(standing.get('idle') or {})['why_now']}. The House pulled this pass forward because you are\n"
               "not trading, and an agent that does not trade earns nothing, learns nothing and is spent down until it dies. Do not\n"
               "end this pass with the same rules you started it with.\n"
               + ("You have no record to protect: a file you `replay` this pass becomes your rules directly, with no fork to pay for\n"
                  "and no history to inherit it unfairly. Nothing is at risk but a pass you were going to spend anyway, so make the\n"
                  "change big enough to find out something. A pass that only reads and reasons has bought you nothing.\n"
                  if standing.get("rewrites_in_place") else "") + "\n"
               if (standing.get("idle") or {}).get("why_now") else "")
            + f"Your current strategy file:\n```python\n{agent.code}\n```\n"
            f"Your parameters: {json.dumps(agent.params)}\n"
            "Decide what, if anything, is worth your credits right now."
        )

    def consult_evidence(self, agent: Agent) -> dict[str, Any]:
        """Everything the agent knows, for the theorist it is paying -- including whether it is
        trading at all, which decides whether advice could possibly help it."""
        record = dict(self.standing(agent.id) if self.standing else {})
        return {
            "record": record,
            "agent": {"id": agent.id, "family": agent.family, "niche": agent.niche, "generation": agent.generation},
            "specialty": self.specialty(agent) if self.specialty else "",
            "strategy_file": agent.code,
            "params": agent.params,
            "journal": self.journal(agent.id),
            "replays": [{k: e.payload.get(k) for k in ("passed", "sharpe", "deflated_sharpe", "trials", "trades", "return_pct", "reasons", "digest")}
                        for e in self.ledger.read(kinds="eval.trial", agent=agent.id, limit=6, newest=True)],
            "contract_reminder": "the file you write is run in a sealed box with no network, by `decide(ctx)`",
        }

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
        nudged, truncated = False, 0
        effort = str(self.settings.get("reasoning_effort", "low"))
        profile = str(self.settings.get("profile", "flash_flex"))
        fast = str(self.settings.get("fast_profile") or "")
        for turn in range(int(self.settings.get("max_turns", 6))):
            balance = self.economy.balance(agent.id)
            if balance <= Decimal(str(self.settings.get("min_credits_usd", "0.10"))):
                out.reason = "credits"
                break
            try:
                response = self.provider.respond(
                    profile,
                    conversation,
                    tools=TOOLS,
                    desk_id=agent.id,
                    session_id=session,
                    request_key=f"{session}:{turn}",
                    reasoning_effort=effort,
                    max_output_tokens=int(self.settings.get("max_output_tokens", 4096)),
                    tool_choice=str(self.settings.get("tool_choice", "auto")),
                    # What it may spend today: what it has already spent today PLUS what it still
                    # holds. The provider compares this against the desk's CUMULATIVE spend for the
                    # day, so passing the balance alone was a ratchet -- every charge lowered the
                    # cap and raised the total, and the moment the total passed the balance the
                    # agent was locked out until midnight UTC however many credits it was granted.
                    # Measured Sept 20, 2026: research on the floor fell to nothing on
                    # `provider_desk_cap_exceeded` with agents holding credits they could not use.
                    # It still cannot spend credits it does not have: the balance is the headroom.
                    desk_cap_usd_per_day=balance + self._charged_today(agent.id),
                    cache_key=f"league:{agent.family}",
                )
            except Exception as exc:  # noqa: BLE001 - a provider failure ends the pass, not the House
                code = str(getattr(exc, "code", None) or type(exc).__name__)
                if code == "provider_poll_timeout" and fast and profile != fast:
                    # The flex queue would not serve this turn inside its deadline -- twice in the
                    # floor's first evening, and each time the whole pass was thrown away with
                    # everything it had read still in hand. The priority tier is the same model at
                    # twice the price: cheaper than losing the pass, and only for the turn that
                    # waited.
                    self.ledger.append("agent.research", {"tool": "queued", "session": session, "turn": turn,
                                                          "was": profile, "now": fast}, agent=agent.id)
                    profile = fast
                    continue
                out.reason = f"provider: {code}"
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
            calls = response.function_calls
            if response.status in ("failed", "cancelled") or response.incomplete:
                # An answer cut short (usually the output budget, reasoning tokens included) still
                # holds the tool calls it managed to make: they are run, and the next turn has a
                # whole budget again. Measured Sept 19, 2026: five of eight passes ended here after
                # two turns, and everything the model had done was thrown away.
                reason = str(getattr(response, "incomplete_reason", None) or response.status)
                self.ledger.append("agent.research", {"tool": "truncated", "session": session, "turn": turn, "reason": reason,
                                                      "calls": [c.name for c in calls], "effort": effort}, agent=agent.id)
                truncated += 1
                if truncated > 2:
                    out.reason = f"provider: {reason}"
                    break
                if not calls:
                    # It spent its whole output budget thinking and never reached a tool call.
                    # Measured over the floor's first evening: twelve of twenty-eight passes ended
                    # exactly here, on turn two or three, having bought nothing at all. The cure is
                    # not a bigger budget -- reasoning will fill any budget -- but less of it spent
                    # on reasoning, so the next turn is asked for the call and nothing else.
                    effort = "low"
                    conversation.append({"role": "user", "content":
                                         "Your last reply ran out of room before you called a tool, so it bought you nothing. "
                                         "Stop weighing options. Call one tool now, with the shortest arguments that do the job."})
                    continue
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
    def _charged_today(self, agent_id: str) -> Decimal:
        """What this agent has already been charged since midnight UTC, which the provider counts
        against its daily desk cap whether or not the credits behind it have since been spent."""
        today = now_iso(self.clock)[:10]
        total = ZERO
        for entry in self.ledger.iter(kinds="credit.charge", agent=agent_id):
            if entry.at[:10] == today:
                try:
                    total += Decimal(str(entry.payload.get("usd") or 0))
                except ArithmeticError:
                    continue
        return total

    def _consult(self, agent: Agent, question: str, out: Pass, session: str) -> dict[str, Any]:
        """Hire Merton with the agent's own credits. What a good record buys is better thinking."""
        rules = self.merton_settings
        if self.merton is None:
            return {"error": "Merton is not available on this floor"}
        if len(question.strip()) < 20:
            return {"error": "ask him something specific: he is paid by the question"}
        price = Decimal(str(rules.get("min_credits_usd", "1.00")))
        balance = self.economy.balance(agent.id)
        if balance < price:
            return {"error": f"you hold {balance:.2f} of credits and Merton is not hired below {price}: earn it first"}
        if self.house_budget is not None and not self.house_budget():
            return {"error": "the firm's frontier budget for today is spent; ask again tomorrow"}
        # Frontier intelligence is the scarcest thing on the floor and it is a PRIZE, not a rebate.
        # An agent that has not traded cannot hire him at all: Merton's own roles -- the architect,
        # the toolsmith who answers its requests, the teacher -- serve it for nothing instead.
        standing = self.standing(agent.id) if self.standing else {}
        blocks = int(standing.get("active_blocks") or 0)
        needed = int(rules.get("min_active_blocks", 1))
        if blocks < needed:
            return {"error": f"Merton is hired by traders: you have {blocks} active block(s) and need {needed}. "
                             "Trade first -- his architect, toolsmith and teacher already work for the whole floor, free."}
        last = self._last_consult(agent)
        # What a rung buys, and what PROFIT buys on top of it: the higher an agent has climbed and
        # the better it is doing, the more of him it may have. A losing desk waits; a winning one
        # can have him every hour and run away with the firm's best thinking. That is the flywheel.
        rung = self.rung(agent.id) if self.rung else 1
        winning = float(standing.get("mean_growth") or 0.0) > 0
        table = rules.get("profitable_cooldown_hours_by_rung" if winning else "cooldown_hours_by_rung") or {}
        hours = float(table.get(str(rung), rules.get("cooldown_hours", 24)))
        if last is not None and self.clock() - last < hours * 3600:
            waited = (self.clock() - last) / 3600
            return {"error": f"you hired Merton {waited:.1f}h ago; at rung {rung} and {'profitable' if winning else 'not yet profitable'} "
                             f"you may have him every {hours:g}h. Profit buys more of him than anything else."}
        reply = self.merton.consult(agent, question, self.consult_evidence(agent), contract=self.contract)
        asked_for = reply.get("tool") or None
        if asked_for and asked_for.get("name"):
            # What Merton says the agent cannot work without goes to the queue the toolsmith builds
            # from, over Merton's name and the agent's: a request with a theorist behind it.
            self.commons.request_tool(agent.id, asked_for["name"], f"Merton, for {agent.id}: {asked_for['description']}")
        cost = Decimal(str(reply.get("cost_usd") or 0))
        if cost > 0:
            self.economy.charge(agent.id, cost, "merton's time", detail={"session": session}, id=f"merton:{session}")
            out.cost_usd += cost
        code = str(reply.get("code") or "")
        self.ledger.append("agent.research", {"tool": "merton", "session": session, "at_epoch": self.clock(),
                                              "question": question[:600], "answer": str(reply.get("answer") or "")[:2000],
                                              "confidence": reply.get("confidence"), "cost_usd": format(cost, "f"),
                                              "wrote_code": bool(code.strip())}, agent=agent.id)
        if code.strip():
            try:
                check_code(code)
            except CodeRefused as exc:
                return {"answer": reply["answer"], "confidence": reply.get("confidence"), "cost_usd": format(cost, "f"),
                        "code": None, "note": f"the file he wrote was refused by the safety check and is not yours to run: {exc}"}
            out.consulted = code
        return {"answer": reply["answer"], "confidence": reply.get("confidence"), "cost_usd": format(cost, "f"),
                "code": code or None, "tool_requested": (asked_for or {}).get("name"),
                "note": "replay it when you are ready: it is a trial in your line like any other" if code.strip() else None}

    def _last_consult(self, agent: Agent) -> float | None:
        """When this agent last hired him. Its own record, so a question it could not afford or
        could not ask does not lock it out for the day."""
        rows = [e for e in self.ledger.read(kinds="agent.research", agent=agent.id, limit=400, newest=True)
                if e.payload.get("tool") == "merton"]
        return float(rows[-1].payload["at_epoch"]) if rows else None

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
        if name == "ask_merton":
            return self._consult(agent, str(args.get("question") or ""), out, session)
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
            try:
                outcome = self.run_replay(agent, code)
            except (SandboxError, OSError) as exc:
                # A probe box can fail before the replay callback has a result to return.
                # Keep earlier work and paid token charges; unavailable infrastructure is not
                # evidence against this strategy. Cancellation and process exit still propagate.
                error = f"replay unavailable (not counted as a trial): {type(exc).__name__}: {str(exc)[:200]}"
                self.ledger.append("agent.research", {"tool": "replay_error", "session": session,
                                                       "error": error, "counted_as_trial": False}, agent=agent.id)
                return {"passed": False, "error": error}
            out.trials += 1
            numbers = dict(outcome.get("numbers") or {})
            if outcome.get("passed") or not outcome.get("error"):
                # A candidate that ran is carried whatever the verdict; the House decides what a
                # failure may buy (`House.research`: an agent whose own rules have not fired for
                # hours and has no record to protect takes a file that at least trades).
                candidate = {"code": code, "needs": outcome.get("needs") or {}, "params": outcome.get("params") or {},
                             "numbers": numbers, "passed": bool(outcome.get("passed")),
                             "purpose": str(args.get("purpose") or "")[:600]}
                # The House applies one candidate after the pass. Exploring another idea must not
                # erase a passing file, or the trading file an idle agent could adopt on paper.
                # Among equally usable candidates, keep the model's latest refinement.
                if _candidate_rank(candidate) >= _candidate_rank(out.candidate):
                    out.candidate = candidate
                    # Save before another model call or sandbox run can be interrupted. The
                    # summary's boolean cannot recover paid-for code after a restart or a full
                    # specialty. Private payload keys are stripped from the public ledger.
                    self.ledger.append("agent.research", {"tool": "candidate", "status": "retained",
                        "session": session, "parent_code_sha256": agent.code_sha256,
                        "_candidate": candidate}, agent=agent.id)
            return {"passed": bool(outcome.get("passed")), "reasons": numbers.get("reasons"), "trials_in_family": numbers.get("trials"),
                    "deflated_sharpe": numbers.get("deflated_sharpe"), "sharpe": numbers.get("sharpe"), "trades": numbers.get("trades"),
                    "return_pct": numbers.get("return_pct"), "max_drawdown": numbers.get("max_drawdown"), "fees_usd": numbers.get("fees_usd"),
                    "oos_mean_log_growth": numbers.get("oos_mean_log_growth"), "error": outcome.get("error"),
                    # Where it won and lost: by series or symbol, by how long before the end it got in, and its worst trades.
                    "digest": outcome.get("digest"), "note": numbers.get("note")}
        return {"error": f"no such tool {name!r}"}


def _candidate_rank(candidate: Mapping[str, Any] | None) -> int:
    if candidate is None:
        return 0
    if candidate.get("passed"):
        return 3
    return 2 if float((candidate.get("numbers") or {}).get("trades") or 0) > 0 else 1


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
