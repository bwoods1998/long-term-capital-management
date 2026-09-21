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
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Callable, Mapping

from .agents import Agent
from .commons import SEARCH_CHARGE_USD, Commons
from .ledger import Ledger, now_iso
from .safety import CodeRefused, check_code
from .sandbox import SandboxError
from .research_jobs import ResearchPending

ZERO = Decimal(0)

TOOLS: list[dict[str, Any]] = [
    {"name": "runtime_status", "description": "Read the House's current replay, data and research capabilities, limits and implementation revision. Free. Verify old journal or library blockers here before asking for a tool that may already be implemented. This reports support/configuration, not measured tape coverage.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "replay_coverage", "description": "Inspect actual tape dates, counts, warmup and missing observed symbols. Omit needs for your current strategy, or supply COMPLETE proposed NEEDS to preflight a candidate before writing code or buying a replay. Uses normal bounded data reads, no strategy execution, sandbox charge or selection trial. One missing required symbol can block a replay while others have data: inspect missing symbols and test a narrower hypothesis. Counts do not demonstrate an edge or realistic fills.",
     "parameters": {"type": "object", "properties": {"needs": {"type": "object", "description": "Optional complete candidate NEEDS; same venue/horizon and specialty as the current agent."}}}},
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
    {"name": "markets_now", "description": "Inspect a compact research preview of your strategy's current markets, quotes, bars, option chain, positions and working orders. Read coverage for the actual snapshot counts and history dates: this preview shows only the latest 30 bars per symbol, 40 busiest markets and first 40 option contracts. Preview truncation does not shorten the strategy's input. Free. Look before you design: a rule about spreads or prices should start from the spreads and prices that are really there.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "journal_write", "description": "Write a note to your FUTURE SELF. Your journal is handed back to you at the start of every research pass, and your children inherit it: what you tried, what the result was, what you will check next, what not to repeat. Keep each entry short and dated by the House.",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "ask_merton", "description": "Hire Merton, the firm's theorist, to think about YOUR problem. He is the frontier model that writes the firm's strategies and audits every candidate for real money, and he is EXPENSIVE: this costs many times a research pass, out of your own credits, and hiring follows your rung's activity, credit and cooldown rules. He is shown everything you know (your file, your journal, your trades, your replays, your specialty) and answers with advice or with a whole strategy file you can then `replay`. Ask when you are stuck or when your idea may be structurally dead, not for a parameter.",
     "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}},
    {"name": "research_grant", "description": "Request one House-funded specialist call for an untraded research/paper family. Use after replay_coverage or a replay in this pass, when there is a specific blocker or new falsifiable hypothesis. Supply the question, hypothesis and acceptance check. It costs no agent credits; family/niche receives only one grant per campaign, including all descendants. The floor has twelve grants, with a $0.25 reservation ceiling each. It writes proposed code for normal replay, never trading capital or qualification.",
     "parameters": {"type": "object", "properties": {k: {"type": "string"} for k in ("question", "hypothesis", "acceptance_check")},
                    "required": ["question", "hypothesis", "acceptance_check"]}},
    {"name": "replay", "description": "Run candidate strategy code through the mechanical replay over recorded history. It is COUNTED AS A TRIAL against your lineage, and costs sandbox seconds. Code that PASSES is kept for the House to adopt or fork when this pass ends (the House stakes a child if you cannot). A later failed trial cannot discard a passing file. If you are on PAPER, your OWN rules have not fired for hours and you have no record to protect, code that merely TRADES on the tape can replace yours in place, failed verdict and all: a strategy that never acts cannot be measured, and paper is then the test. Give the complete strategy file and what you changed and why.",
     "parameters": {"type": "object", "properties": {"code": {"type": "string"}, "purpose": {"type": "string"}}, "required": ["code", "purpose"]}},
    {"name": "finish", "description": "End this research pass with one or two sentences on what you concluded.",
     "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}},
]

# These tools buy no inference and write no strategy, credits, orders or shared notes.
# After a crash, their new receipt describes a refreshed observation, not the lost one.
REFRESHABLE_TOOLS = frozenset(('runtime_status', 'replay_coverage', 'markets_now',
                             'library_search', 'library_read', 'playbook_read'))


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


def pass_state(out) -> dict[str, Any]:
    values = asdict(Pass(out.agent if hasattr(out, 'agent') else ''))
    values.update({key: getattr(out, key, value) for key, value in values.items()})
    values['cost_usd'] = str(values['cost_usd'])
    return values


def restore_pass(values) -> Pass:
    return Pass(**{**values, 'cost_usd': Decimal(str(values['cost_usd']))})


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
        jobs: Any = None,  # durable queue owned by the House; None for an in-memory pass
        may_continue: Callable[[Agent], str] | None = None,
        capabilities: Callable[[Agent], Mapping[str, Any]] | None = None,
        coverage: Callable[..., Mapping[str, Any]] | None = None,
        grants: Any = None,
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
        self.jobs, self.may_continue, self.capabilities = jobs, may_continue, capabilities
        self.coverage = coverage
        self.grants = grants

    # ------------------------------------------------------------------ prompt
    def _system(self) -> str:
        return (
            self.rules
            + "\n\nTHE STRATEGY CONTRACT (the file format your code must follow)\n\n"
            + self.contract
            + "\n\nHOW TO WORK. Call one tool per turn. Start from your journal and your own recent trades: they are what you know that "
            "nobody else does. Look at the live view (`markets_now`) before you design a rule about prices or spreads. Read the library "
            "and the playbook before paying for a search. State a falsifiable question, the existing baseline, the artifact you will "
            "produce, and the acceptance check. Spend a replay only when its answer can change a specific decision. A reused historical "
            "tail is development evidence, not independent forward validation. A documented missing input or an explicit abstention "
            "with a measurable next trigger is useful; repeated known failures and spending for its own sake are not. "
            "Write a library note when you learn something another agent could use, "
            "and a journal note (`journal_write`) for your future self: you keep nothing else of this pass. "
            "A replay submits a candidate; it does not install code during this conversation. The House checks adoption or "
            "fork eligibility after the pass. Describe a submitted candidate as proposed, and do not claim it is installed. "
            "Your standing's runtime_capabilities and runtime_status describe the deployed House: check them before treating an "
            "old journal or library note about missing infrastructure as current. Preflight proposed inputs with replay_coverage(needs=...) "
            "before spending a replay to diagnose data. One unsupported symbol does not establish that a whole feed is absent. "
            "A tool request answered as blocked is still unimplemented. If you have never traded and a concrete blocker or "
            "new hypothesis needs specialist help, inspect replay_coverage then use research_grant once; it is House-funded "
            "and does not require trading history. This is separate from earned ask_merton access. "
            "Your own model turns cost credits, including abstention. End with `finish`."
        )

    def _state(self, agent: Agent, standing: Mapping[str, Any]) -> str:
        brief = self.specialty(agent) if self.specialty else ""
        journal = self.journal(agent.id)
        pages = "\n".join(f"- [{row['at'][:16]} {row['by']}] {row['text']}" for row in journal)
        return (
            f"You are {agent.id} (family {agent.family}, niche {agent.niche}, generation {agent.generation}).\n"
            + (f"\n{brief}\n\n" if brief else "")
            + (f"YOUR JOURNAL (your and your ancestors' notes, oldest first; conclusions are unverified claims. Compare them with the current qualification_policy, runtime capabilities and peer evidence before relying on them; add with `journal_write`):\n{pages}\n\n" if pages else
               "YOUR JOURNAL is empty. Before you finish, write yourself a note with `journal_write`: you will remember nothing else of this pass.\n\n")
            + f"Your standing: {json.dumps(standing, default=str)}\n\n"
            + (f"WHY YOU ARE AWAKE NOW: {(standing.get('idle') or {})['why_now']}. The House pulled this pass forward because you are\n"
               "not trading, and an agent that does not trade earns nothing, learns nothing and is spent down until it dies. Do not\n"
               "end this pass with the same rules you started it with.\n"
               + ("You have no record to protect, so an eligible candidate can replace your rules after this pass without a fork.\n"
                  "On rung 0 a strategy MUST pass replay to qualify. A parameter-only repair of an invalid configuration\n"
                  "may be adopted after a failed replay with unchanged decision logic/NEEDS; it stays on rung 0.\n"
                  "Only an empty PAPER record with enough barren wakes may accept another failed\n"
                  "candidate that at least trades; the House checks those conditions. Submitting a replay is not adoption.\n"
                  "Make the change large enough to answer a concrete question, and report its actual replay verdict.\n"
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
            "runtime_capabilities": dict(self.capabilities(agent)) if self.capabilities else None,
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
                if text and len(str(text).strip()) >= 20 and p.get('tool') == 'summary':
                    text = (f"Recorded model cost ${p.get('cost_usd', 'unknown')}; {p.get('trials', 0)} replay tool trials. "
                            f"Agent conclusion (unverified): {text}")
                if text and len(str(text).strip()) >= 20:  # "done" is not a memory
                    rows.append({"at": entry.at, "by": name, "text": str(text).strip()[:chars]})
        return rows[-entries:]

    # -------------------------------------------------------------------- pass
    def research(self, agent: Agent, standing: Mapping[str, Any], *, session: str) -> Pass:
        """Resume at a saved model or tool boundary, with the original request and transcript.

        Completed tool results and candidate source are saved before buying another turn. An
        interrupted tool intent is ambiguous: keep its evidence and end the pass instead of
        risking another paid replay, consultation, library write or charge. The provider's own
        durable response store makes a resumed model request safe under the same request key.
        """
        job = self.jobs.get(session) if self.jobs else None
        state = job['checkpoint'] if job else None
        if state is None:
            settings = self.provider.settings_for(agent, self.settings) if hasattr(self.provider, 'settings_for') else dict(self.settings)
            state = {
                'version': 1, 'stage': 'model', 'turn': 0, 'started': self.clock(),
                'conversation': [{'role': 'system', 'content': self._system()},
                                 {'role': 'user', 'content': self._state(agent, standing)}],
                'nudged': False, 'truncated': 0,
                'effort': str(settings.get('reasoning_effort', 'low')),
                'profile': str(settings.get('profile', 'flash_flex')),
                'settings': settings, 'tools': TOOLS,
                'out': pass_state(Pass(agent.id)),
            }
        if state.get('version') != 1:
            raise RuntimeError('unsupported research checkpoint version')
        out = restore_pass(state['out'])
        conversation, settings = state['conversation'], state['settings']

        def save():
            state['out'] = pass_state(out)
            if self.jobs:
                self.jobs.save(session, state)

        def advance():
            state['turn'] += 1
            state['stage'] = 'model'
            state.pop('response', None)
            save()

        save()  # freeze the prompt, settings and exact tool schema before any paid request
        while state['stage'] != 'done':
            turn = state['turn']
            if state['stage'] == 'tool_pending':
                # A receipt was not saved. Even a successful write followed by process exit
                # looks like this, so no side effect is safe to repeat. A replay may already
                # have retained a candidate on the append-only ledger: recover that code.
                call = state['response']['calls'][state['call_index']]
                if call['name'] in REFRESHABLE_TOOLS:
                    self.ledger.append('agent.research', {'tool': 'refreshed_read', 'session': session,
                        'turn': turn, 'name': call['name'], 'reason': 'interrupted read refreshed after restart'},
                        agent=agent.id, id=f'research-read-recovery:{session}:{turn}:{state["call_index"]}')
                    state['stage'] = 'tools'
                    save()
                    continue
                for entry in self.ledger.iter(kinds='agent.research', agent=agent.id):
                    p = entry.payload
                    if p.get('session') == session and p.get('status') == 'retained' and p.get('_candidate'):
                        if _candidate_rank(p['_candidate']) >= _candidate_rank(out.candidate):
                            out.candidate = p['_candidate']
                out.reason = f"tool outcome unconfirmed: {call['name']}"
                out.summary = 'A restart interrupted a tool before its receipt was saved. Its outcome is unconfirmed; the tool was not repeated. Retained candidate evidence is preserved.'
                state['stage'] = 'done'
                save()
                break
            permission = self.may_continue(agent) if self.may_continue else ''
            if permission == 'retired or changed':
                out.reason, state['stage'] = permission, 'done'
                save()
                break
            if permission:
                raise ResearchPending(permission)
            if self.jobs and self.clock() - state['started'] > 6 * 3600:
                out.reason, state['stage'] = 'session expired after six hours', 'done'
                save()
                break
            if state['stage'] == 'model':
                if turn >= int(settings.get('max_turns', 6)):
                    state['stage'] = 'done'
                    save()
                    break
                balance = self.economy.balance(agent.id)
                request_key = f'{session}:{turn}'
                record = self.provider.record(request_key) if self.jobs and hasattr(self.provider, 'record') else None
                if record is None and balance <= Decimal(str(settings.get('min_credits_usd', '0.10'))):
                    out.reason, state['stage'] = 'credits', 'done'
                    save()
                    break
                try:
                    response = self.provider.respond(
                        state['profile'], conversation, tools=state['tools'], desk_id=agent.id,
                        session_id=session, request_key=request_key, reasoning_effort=state['effort'],
                        max_output_tokens=int(settings.get('max_output_tokens', 4096)),
                        tool_choice=str(settings.get('tool_choice', 'auto')),
                        # The provider counts today's cumulative spend, so balance is headroom,
                        # not the cumulative desk cap. Charge ids below remain stable on resume.
                        desk_cap_usd_per_day=balance + self._charged_today(agent.id),
                        cache_key=f'league:{agent.family}',
                    )
                except Exception as exc:  # a refused call ends the pass, not the House
                    code = str(getattr(exc, 'code', None) or type(exc).__name__)
                    record = self.provider.record(request_key) if self.jobs and hasattr(self.provider, 'record') else None
                    if record and record.get('response_id') and code in (
                        'provider_poll_timeout', 'provider_transport_unconfirmed', 'provider_transport_timeout', 'provider_http_429',
                        'provider_http_500', 'provider_http_502', 'provider_http_503', 'provider_http_504',
                        'provider_http_529',
                    ):
                        # Timeout is not cancellation. Release the worker and poll THIS response
                        # again later; buying the fast tier here duplicates the accepted work.
                        raise ResearchPending(code) from exc
                    fast = str(settings.get('fast_profile') or '')
                    if not self.jobs and code == 'provider_poll_timeout' and fast and state['profile'] != fast:
                        self.ledger.append('agent.research', {'tool': 'queued', 'session': session,
                            'turn': turn, 'was': state['profile'], 'now': fast}, agent=agent.id)
                        state['profile'] = fast
                        advance()
                        continue
                    out.reason, state['stage'] = f'provider: {code}', 'done'
                    save()
                    break
                state['response'] = {
                    'cost_usd': str(response.cost_usd or 0), 'items': response.output_items,
                    'text': (response.output_text or '').strip(), 'status': response.status,
                    'incomplete': response.incomplete,
                    'incomplete_reason': getattr(response, 'incomplete_reason', None),
                    'calls': [{'name': c.name, 'arguments': c.arguments, 'call_id': c.call_id,
                               'error': c.error} for c in response.function_calls],
                }
                state['stage'] = 'response'
                save()  # the response is durable before charging the agent or running its tools
            if state['stage'] == 'response':
                response = state['response']
                out.turns = turn + 1
                cost = Decimal(response['cost_usd'])
                if cost > 0:
                    self.economy.charge(agent.id, cost, 'research tokens', detail={'session': session, 'turn': turn}, id=f'tokens:{session}:{turn}')
                    out.cost_usd += cost
                conversation.extend(response['items'])
                if response['text']:
                    self.ledger.append('agent.thought', {'text': response['text'][:4000], 'session': session,
                        'phase': 'research'}, agent=agent.id, id=f'research-thought:{session}:{turn}' if self.jobs else None)
                calls = response['calls']
                if response['status'] in ('failed', 'cancelled') or response['incomplete']:
                    reason = str(response['incomplete_reason'] or response['status'])
                    self.ledger.append('agent.research', {'tool': 'truncated', 'session': session, 'turn': turn,
                        'reason': reason, 'calls': [c['name'] for c in calls], 'effort': state['effort']},
                        agent=agent.id, id=f'research-truncated:{session}:{turn}' if self.jobs else None)
                    state['truncated'] += 1
                    if state['truncated'] > 2:
                        out.reason, state['stage'] = f'provider: {reason}', 'done'
                        save()
                        break
                    if not calls:
                        state['effort'] = 'low'
                        conversation.append({'role': 'user', 'content':
                            'Your last reply ran out of room before you called a tool, so it bought you nothing. '
                            'Stop weighing options. Call one tool now, with the shortest arguments that do the job.'})
                        advance()
                        continue
                if not calls:
                    if state['nudged']:
                        out.reason, state['stage'] = 'no tool call', 'done'
                        save()
                        break
                    state['nudged'] = True
                    conversation.append({'role': 'user', 'content': 'Call a tool. If you are done, call `finish`.'})
                    advance()
                    continue
                state.update(stage='tools', call_index=0, finished=False)
                save()
            if state['stage'] == 'tools':
                calls = state['response']['calls']
                while state['call_index'] < len(calls):
                    permission = self.may_continue(agent) if self.may_continue else ''
                    if permission == 'retired or changed':
                        out.reason, state['stage'] = permission, 'done'
                        save()
                        break
                    if permission:
                        raise ResearchPending(permission)
                    call = calls[state['call_index']]
                    state['stage'] = 'tool_pending'
                    save()  # write the intent before any side effect
                    result = {'error': call['error']} if call['error'] else self._execute(agent, call['name'], call['arguments'], out, session)
                    out.calls.append(call['name'])
                    # Complete specialist strategy files must survive the tool receipt. Cutting
                    # serialized JSON at 12k corrupted precisely the artifact we paid to obtain.
                    limit = 100000 if call['name'] in ('research_grant', 'ask_merton') else 12000
                    encoded = json.dumps(result, default=str)
                    if len(encoded) > limit and call['name'] in ('research_grant', 'ask_merton'):
                        encoded = json.dumps({'error': 'specialist answer exceeded the bounded tool receipt; no truncated code delivered'})
                    conversation.append({'type': 'function_call_output', 'call_id': call['call_id'],
                                         'output': encoded[:limit]})
                    state['finished'] = state['finished'] or call['name'] == 'finish'
                    state['call_index'] += 1
                    state['stage'] = 'tools'
                    save()  # receipt, transcript and Pass effects are one atomic checkpoint
                if state['stage'] == 'done':
                    break
                if state['finished']:
                    out.reason, state['stage'] = 'finished', 'done'
                    save()
                    break
                advance()
        summary_id = f'research-summary:{session}' if self.jobs else None
        if summary_id and self.ledger.get(summary_id):
            return out
        if 'finished_at' not in state:
            state['finished_at'] = self.clock()
            save()
        self.ledger.append('agent.research', {
            'tool': 'summary', 'session': session, 'turns': out.turns,
            'profile': state['profile'], 'started': state['started'], 'finished': state['finished_at'],
            'elapsed_seconds': round(max(0, state['finished_at'] - state['started']), 3),
            'cost_usd': format(out.cost_usd, 'f'), 'trials': out.trials,
            'summary': out.summary[:1200], 'reason': out.reason, 'candidate': bool(out.candidate),
        }, agent=agent.id, id=summary_id)
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
        if name == "runtime_status":
            return dict(self.capabilities(agent)) if self.capabilities else {"error": "runtime capabilities unavailable"}
        if name == "replay_coverage":
            if not self.coverage:
                return {"error": "replay coverage unavailable", "counted_as_trial": False}
            return dict(self.coverage(agent, args['needs']) if 'needs' in args else self.coverage(agent))
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
        if name == "research_grant":
            if self.grants is None:
                return {'error': 'startup research grants are not configured'}
            if self.house_budget is not None and not self.house_budget():
                return {'error': 'the current House research budget is closed'}
            if not {'replay_coverage', 'replay'}.intersection(out.calls):
                return {'error': 'inspect replay_coverage or run a replay in this pass before requesting a grant'}
            evidence = self.consult_evidence(agent)
            evidence['record']['rung'] = self.rung(agent.id) if self.rung else 0
            reply = self.grants.request(agent, args, evidence, session=session, contract=self.contract)
            code = reply.get('code') or ''
            if code:
                try:
                    check_code(code)
                except CodeRefused as exc:
                    return {**reply, 'code': None, 'note': f'proposed grant code refused: {exc}'}
                out.consulted = code
            return reply
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
            counted = bool(outcome.get("counted_as_trial", not outcome.get("error")))
            out.trials += int(counted)
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
            return {"counted_as_trial": counted, "passed": bool(outcome.get("passed")), "reasons": numbers.get("reasons"), "trials_in_family": numbers.get("trials"),
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
    """The live view, cut to what a model can read: the busiest 40 markets, the first 40 option
    contracts, the last 30 bars of each symbol. Coverage describes the untrimmed strategy input."""
    def coverage(rows: Any, limit: int) -> dict[str, Any]:
        return {"available_to_strategy": len(rows), "shown": min(len(rows), limit), "truncated": len(rows) > limit}

    # Explain the preview before the potentially large arrays: the tool response also has a
    # character limit, and agents must not mistake displayed rows for the full runtime feed.
    out = {"view_note": "Rows shown here are a research preview. Coverage counts and dates describe the strategy snapshot "
                        "before preview trimming; this preview does not shorten the strategy's input. "
                        "Shown counts are before the response-size limit, which may cut long previews further.", "coverage": {}}
    out.update({k: v for k, v in dict(ctx).items() if k not in ("markets", "chain", "bars", "memory", "params", "view_note", "coverage")})
    if "markets" in ctx:
        rows = sorted(ctx["markets"] or [], key=lambda m: -(m.get("volume_24h") or 0))
        out["markets"] = rows[:40]
        out["markets_shown"] = f"{min(len(rows), 40)} busiest of {len(rows)}"
        out["coverage"]["markets"] = coverage(rows, 40)
    if "chain" in ctx:
        rows = ctx["chain"] or []
        out["chain"] = rows[:40]
        out["coverage"]["chain"] = coverage(rows, 40)
    if "bars" in ctx:
        out["bars"], out["coverage"]["bars"] = {}, {}
        for symbol, bars in (ctx["bars"] or {}).items():
            rows = bars or []
            out["bars"][symbol] = rows[-30:]
            details = coverage(rows, 30)
            if rows:
                for name, row in (("available_first_at", rows[0]), ("available_last_at", rows[-1]), ("shown_first_at", rows[-30:][0])):
                    if isinstance(row, Mapping) and isinstance(row.get("t"), str):
                        details[name] = row["t"]
            out["coverage"]["bars"][symbol] = details
    return out
