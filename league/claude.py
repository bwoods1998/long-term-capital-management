"""Claude, reached only through the gateway (Sept 26, 2026, the swarm sprint).

The Anthropic key lives in the Cloudflare gateway and nowhere else. The House asks
`POST <gateway>/v1/claude/messages`; the gateway reserves the call's worst case against the owner's
funded total (`CLAUDE_USD`), forwards it, settles at what Anthropic says it used and reports that in
`X-LTCM-Cost-USD` (gateway/lib/claude.mjs). A call that does not fit is refused there (402), and so is
every call while the kill switch is engaged (423).

The request is Anthropic's Messages API, not OpenAI's Responses API: thinking cannot be disabled on
Claude Opus 5.5 (it is adaptive; `output_config.effort` is the control, and its default is `medium`, so
it is always sent), there is no sampling parameter, no forced tool choice and no assistant prefill, and
the answer's `stop_reason` is read before its content. The same shape serves Claude Sonnet 5.5 (Sept 29,
2026): adaptive thinking, all five efforts (its default is `high`), no forced tool choice, no sampling. The
stable system prefix carries a 5-minute `cache_control` marker, so a second call within minutes reads it at
a twentieth of the input rate on Opus 5.5 (a tenth on Sonnet 5 and Sonnet 5.5).

STREAMING (Sept 27, 2026). A high-effort answer can take minutes, and Cloudflare in front of
api.anthropic.com gives up on a silent origin after 100 seconds (HTTP 524). A call with `stream=True` asks
for `stream: true`; the gateway relays Anthropic's server-sent events as they arrive and ends with its own
`ltcm.cost` event (what its meter booked). This client rebuilds the final message from the events (the
text blocks, the stop reason, the usage), with a read timeout between events (`read_timeout`, 120 s) and an
overall limit (`timeout`, 600 s). Thinking is asked for `display: "summarized"` on a stream, so its deltas
keep the bytes flowing while the model thinks (display changes what is shown, not what is billed).

TOOL CALLS (Sept 29, 2026: the swarm's top researchers run their tool loop on Claude Sonnet 5.5). `Claude.messages`
sends the House's own tools (`tool_request_body`: custom tools only, each `{name, description, input_schema}`, with
`eager_input_streaming` and cache markers placed by the caller) and a list of turns that may hold the loop's `tool_use`,
`tool_result`, `thinking` and `redacted_thinking` blocks, with `tool_choice` auto or none (forced tool choice is a 400 on
Sonnet 5.5) and adaptive thinking at an explicit effort (never `budget_tokens`). The stream is rebuilt block by block:
text from `text_delta`, thinking from `thinking_delta` and its `signature` from `signature_delta` (a thinking block passed
back without its signature is refused), a tool call's input from its `input_json_delta` fragments, parsed strictly when
its block stops (an empty input is `{}`; one that does not parse is `{}` with `ToolUse.error` set, never guessed). The
answer carries every block exactly as it came (`Answer.content`, thinking included, so the caller passes them back
unchanged) and its calls (`Answer.tool_uses`). Its stop reason is read first: `tool_use`, `end_turn` and
`stop_sequence` are answers; a refusal is `ClaudeRefusal`, a cut (`max_tokens`, `model_context_window_exceeded`)
`ClaudeTruncated`, anything else a `ClaudeError`, each carrying the billed answer: none of a refused or cut turn's calls
may run.

Durable spend holds live with the caller (the swarm's `ModelRouter` books one in its store before
dispatch, #380's pattern); this module gives it the exact request and its worst-case ceiling.
Standard library only.
"""

from __future__ import annotations

import copy
import http.client
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Sequence

MODEL = "claude-opus-5-5"
PATH = "/v1/claude/messages"
COST_HEADER = "X-LTCM-Cost-USD"
AGENT_HEADER = "X-LTCM-Agent"
ROLE_HEADER = "X-LTCM-Role"
#: The House's id for one call: the gateway files what became of it under this id (`GET /v1/claude/request/<id>`).
REQUEST_HEADER = "X-LTCM-Request"
#: The gateway's ceiling (gateway/lib/claude.mjs MAX_TOKENS): thinking and the answer together.
MAX_TOKENS = 16000
#: A streamed call's ceiling (gateway/lib/claude.mjs MAX_TOKENS_STREAM).
MAX_TOKENS_STREAM = 32000
#: The longest a stream may go without a byte (Anthropic pings, and summarized thinking streams its deltas).
READ_TIMEOUT = 120.0
EFFORTS = ("low", "medium", "high", "xhigh", "max")
#: Dollars per million tokens: the dearest input rate (a 5-minute cache write) and the output rate, from
#: platform.claude.com/docs/en/about-claude/pricing (Sept 26, 2026), as gateway/wrangler.jsonc CLAUDE_MODELS prices
#: them. Kept here so the caller's hold is never below the gateway's own reservation. Claude Sonnet 5.5 (Sept 29, 2026,
#: released Sept 28) is listed on the same page at Sonnet 5's prices: $2 input, $2.50 a 5-minute write, $10 output.
MODEL_CEILINGS = {
    "claude-opus-5-5": (Decimal("5"), Decimal("20")),
    "claude-sonnet-5": (Decimal("2.50"), Decimal("10")),
    "claude-sonnet-5-5": (Decimal("2.50"), Decimal("10")),
}
_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_REQUEST_ID = re.compile(r"[A-Za-z0-9:._-]{1,160}")
#: A custom tool's name and a tool call's id, as the gateway admits them (gateway/lib/claude.mjs TOOL_NAME, TOOL_ID).
TOOL_NAME = re.compile(r"[a-zA-Z0-9_-]{1,128}")
TOOL_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
#: The gateway's limits: tools a request, blocks a turn, turns a request, cache markers a request.
MAX_TOOLS = 16
MAX_BLOCKS = 64
MAX_TURNS = 64
MAX_BREAKPOINTS = 4
#: The stop reasons of a tool-loop answer; a cut one is `ClaudeTruncated`.
TOOL_STOPS = ("tool_use", "end_turn", "stop_sequence")
CUT_STOPS = ("max_tokens", "model_context_window_exceeded")


class ClaudeError(RuntimeError):
    """A Claude call that produced no usable answer. `status` is the HTTP status when there was one; `answer` is the
    billed answer when one came back (a refusal, a truncation, an answer without the asked-for JSON); `cost_usd` is the
    gateway's settled cost when it said (None when it is unknown); `cap` names the gateway's own refusal (`setup`,
    `claude_funded`, `kill_switch`: refused before anything was reserved or sent)."""

    def __init__(self, message: str, *, status: int | None = None, answer: "Answer | None" = None,
                 cost_usd: Decimal | None = None, cap: str | None = None):
        super().__init__(message)
        self.status = status
        self.answer = answer
        self.cost_usd = answer.cost_usd if answer is not None and cost_usd is None else cost_usd
        self.cap = cap


class ClaudeRefusal(ClaudeError):
    """`stop_reason: "refusal"`: Anthropic declined. Billed at its usage."""


class ClaudeTruncated(ClaudeError):
    """`stop_reason: "max_tokens"` (or `model_context_window_exceeded`): the answer was cut off. Billed at its usage."""


@dataclass(frozen=True)
class ToolUse:
    """One tool call in an answer: its `id`, `name` and `input` (an object), the `raw` input text it was parsed from (the
    streamed `input_json_delta` fragments joined), and `error` when that text was not a JSON object (`input` is then `{}`:
    never run it)."""

    id: str
    name: str
    input: dict[str, Any]
    raw: str = ""
    error: str | None = None


@dataclass(frozen=True)
class Answer:
    text: str
    data: Any
    usage: dict[str, Any]
    cost_usd: Decimal | None
    model: str
    stop_reason: str
    cost_verified: bool = False
    id: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)
    #: Every content block exactly as it came (thinking with its signature included): a tool loop passes them back.
    content: tuple[dict[str, Any], ...] = field(default=(), repr=False, compare=False)
    #: The answer's tool calls, in order.
    tool_uses: tuple[ToolUse, ...] = ()


def attribution(name: str) -> str:
    """The name the gateway files this call's cost under (`^[a-z0-9][a-z0-9_-]{0,63}$`, else "unattributed")."""
    clean = re.sub(r"[^a-z0-9_-]+", "-", str(name or "").lower()).strip("-_")[:64]
    return clean or "house"


def extract_json(text: str) -> Any:
    """The answer's JSON: the whole text when it parses, else the first JSON object in it, else None."""
    text = str(text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def request_body(model: str, system: str, messages: Sequence[Mapping[str, Any]], *, max_tokens: int = MAX_TOKENS,
                 effort: str = "high", schema: Mapping[str, Any] | None = None, cache: bool = True,
                 stream: bool = False) -> dict[str, Any]:
    """The one request shape the gateway admits: the system prompt as a text block (marked for the 5-minute cache when
    `cache`), text turns ending with the user's, adaptive thinking, an explicit effort, and a JSON-schema answer format
    when `schema` is given. `stream` asks for server-sent events (up to MAX_TOKENS_STREAM), with summarized thinking."""
    if effort not in EFFORTS:
        raise ClaudeError(f"invalid effort {effort!r}")
    turns = []
    for turn in messages:
        role, content = turn.get("role"), turn.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content:
            raise ClaudeError("each turn is a user or assistant role with text content")
        turns.append({"role": role, "content": content})
    if not turns or turns[-1]["role"] != "user":
        raise ClaudeError("the last turn must be the user's (no assistant prefill)")
    block: dict[str, Any] = {"type": "text", "text": str(system or "")}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    output: dict[str, Any] = {"effort": effort}
    if schema is not None:
        output["format"] = {"type": "json_schema", "schema": dict(schema)}
    body: dict[str, Any] = {"model": model, "max_tokens": max(1, min(int(max_tokens), MAX_TOKENS_STREAM if stream else MAX_TOKENS))}
    if stream:
        body["stream"] = True
    if block["text"]:
        body["system"] = [block]
    thinking = {"type": "adaptive", "display": "summarized"} if stream else {"type": "adaptive"}
    body.update({"messages": turns, "thinking": thinking, "output_config": output})
    return body


def _mark(block: Mapping[str, Any]) -> int:
    """1 for a five-minute cache marker, 0 for none; a ClaudeError for any other (the gateway admits no other)."""
    mark = block.get("cache_control")
    if mark is None and "cache_control" not in block:
        return 0
    if not isinstance(mark, Mapping) or mark.get("type") != "ephemeral" or set(mark) - {"type", "ttl"} or mark.get("ttl", "5m") != "5m":
        raise ClaudeError("a cache marker is ephemeral and five minutes")
    return 1


def _only(block: Mapping[str, Any], keys: set[str]) -> bool:
    return not (set(block) - keys)


def _check_block(role: str, block: Any) -> int:
    """One block of a turn, by the gateway's rules (gateway/lib/claude.mjs `turnBlocks`): its cache marker count."""
    if not isinstance(block, Mapping):
        raise ClaudeError("a content block is an object")
    kind = block.get("type")
    if kind == "text":
        ok = (isinstance(block.get("text"), str) and _only(block, {"type", "text", "cache_control"} | ({"citations"} if role == "assistant" else set()))
              and block.get("citations") is None)
    elif kind == "tool_result" and role == "user":
        content = block.get("content")
        ok = (_only(block, {"type", "tool_use_id", "content", "is_error", "cache_control"})
              and isinstance(block.get("tool_use_id"), str) and TOOL_ID.fullmatch(block["tool_use_id"]) is not None
              and (content is None and "content" not in block or isinstance(content, str)
                   or isinstance(content, list) and 1 <= len(content) <= 16
                   and all(isinstance(b, Mapping) and b.get("type") == "text" and isinstance(b.get("text"), str) and _only(b, {"type", "text"})
                           for b in content))
              and isinstance(block.get("is_error", False), bool))
    elif kind == "tool_use" and role == "assistant":
        caller = block.get("caller")
        ok = (_only(block, {"type", "id", "name", "input", "caller", "cache_control"}) and isinstance(block.get("id"), str)
              and TOOL_ID.fullmatch(block["id"]) is not None and isinstance(block.get("name"), str)
              and TOOL_NAME.fullmatch(block["name"]) is not None and isinstance(block.get("input"), Mapping)
              and ("caller" not in block or isinstance(caller, Mapping) and dict(caller) == {"type": "direct"}))
    elif kind == "thinking" and role == "assistant":
        ok = (_only(block, {"type", "thinking", "signature"}) and isinstance(block.get("thinking"), str)
              and isinstance(block.get("signature"), str) and bool(block["signature"]))
    elif kind == "redacted_thinking" and role == "assistant":
        ok = _only(block, {"type", "data"}) and isinstance(block.get("data"), str) and bool(block["data"])
    else:
        ok = False
    if not ok:
        raise ClaudeError(f"a {role} turn cannot hold this {kind or 'untyped'} block")
    return _mark(block)


def _check_tools(tools: Sequence[Mapping[str, Any]]) -> int:
    """The House's own tools, by the gateway's rules (`toolDefs`): their cache marker count."""
    if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)) or not 1 <= len(tools) <= MAX_TOOLS:
        raise ClaudeError(f"tools are 1 to {MAX_TOOLS} of the House's own")
    names: set[str] = set()
    marks = 0
    for tool in tools:
        if not isinstance(tool, Mapping) or not _only(tool, {"name", "description", "input_schema", "cache_control", "eager_input_streaming"}):
            raise ClaudeError("a tool is a name, a description, an input_schema, a cache marker and eager_input_streaming")
        name = tool.get("name")
        if not isinstance(name, str) or TOOL_NAME.fullmatch(name) is None or name in names:
            raise ClaudeError(f"invalid or repeated tool name {name!r}")
        names.add(name)
        if "description" in tool and not isinstance(tool["description"], str):
            raise ClaudeError(f"tool {name}: the description is text")
        if not isinstance(tool.get("input_schema"), Mapping) or tool["input_schema"].get("type") != "object":
            raise ClaudeError(f"tool {name}: input_schema is an object schema")
        if "eager_input_streaming" in tool and not isinstance(tool["eager_input_streaming"], bool):
            raise ClaudeError(f"tool {name}: eager_input_streaming is true or false")
        marks += _mark(tool)
    return marks


def tool_request_body(model: str, system: Any, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]], *,
                      tool_choice: Any = "auto", max_tokens: int = MAX_TOKENS_STREAM, effort: str = "medium",
                      stream: bool = True) -> dict[str, Any]:
    """A tool loop's request, exactly as the gateway admits it (TOOL CALLS in the module docstring), checked here by the
    gateway's own rules so a bad body fails in the House without a round trip. `system` is a string or text blocks (the
    caller places its cache markers); `messages` are turns of text, tool and thinking blocks ending with the user's;
    `tools` the House's own; `tool_choice` "auto" or "none" (or `{"type": ..., "disable_parallel_tool_use": bool}`);
    adaptive thinking (summarized on a stream, so its deltas keep the bytes flowing) and `effort`, never `budget_tokens`."""
    if effort not in EFFORTS:
        raise ClaudeError(f"invalid effort {effort!r}")
    marks = 0
    if isinstance(system, str):
        system_blocks = [{"type": "text", "text": system}] if system else []
    elif isinstance(system, Sequence) and 1 <= len(system) <= 16:
        system_blocks = []
        for block in system:
            if not isinstance(block, Mapping) or block.get("type") != "text" or not isinstance(block.get("text"), str) \
                    or not _only(block, {"type", "text", "cache_control"}):
                raise ClaudeError("the system prompt is text blocks")
            marks += _mark(block)
            system_blocks.append(dict(block))
    else:
        raise ClaudeError("the system prompt is a string or 1 to 16 text blocks")
    marks += _check_tools(tools)
    choice = {"type": tool_choice} if isinstance(tool_choice, str) else dict(tool_choice or {})
    if choice.get("type") not in ("auto", "none") or not _only(choice, {"type", "disable_parallel_tool_use"}) \
            or not isinstance(choice.get("disable_parallel_tool_use", False), bool):
        raise ClaudeError("tool_choice is auto or none: forced tool choice is refused by Sonnet 5.5 and Opus 5.5")
    if not isinstance(messages, Sequence) or not 1 <= len(messages) <= MAX_TURNS:
        raise ClaudeError(f"messages hold 1 to {MAX_TURNS} turns")
    turns = []
    for turn in messages:
        role, content = (turn.get("role"), turn.get("content")) if isinstance(turn, Mapping) else (None, None)
        if role not in ("user", "assistant") or set(turn) - {"role", "content"}:
            raise ClaudeError("each turn is a user or assistant role")
        if isinstance(content, str):
            if not content:
                raise ClaudeError("a turn's text is not empty")
        elif isinstance(content, Sequence) and 1 <= len(content) <= MAX_BLOCKS:
            marks += sum(_check_block(role, block) for block in content)
        else:
            raise ClaudeError(f"a turn holds text or 1 to {MAX_BLOCKS} blocks")
        turns.append({"role": role, "content": content})
    if turns[-1]["role"] != "user":
        raise ClaudeError("the last turn must be the user's (no assistant prefill)")
    if marks > MAX_BREAKPOINTS:
        raise ClaudeError(f"at most {MAX_BREAKPOINTS} cache markers across the system prompt, the tools and the turns")
    body: dict[str, Any] = {"model": model, "max_tokens": max(1, min(int(max_tokens), MAX_TOKENS_STREAM if stream else MAX_TOKENS))}
    if stream:
        body["stream"] = True
    if system_blocks:
        body["system"] = system_blocks
    body.update({"tools": [dict(t) for t in tools], "tool_choice": choice, "messages": turns,
                 "thinking": {"type": "adaptive", "display": "summarized"} if stream else {"type": "adaptive"},
                 "output_config": {"effort": effort}})
    return body


def reservation_ceiling(body: Mapping[str, Any]) -> Decimal:
    """The gateway's worst case for this exact body, never below it: every byte a token written to the cache, plus the
    gateway's framing, and every `max_tokens` output token."""
    model = body.get("model")
    if model not in MODEL_CEILINGS:
        raise ClaudeError("no verified price for this Claude model")
    input_rate, output_rate = MODEL_CEILINGS[model]
    size = len(json.dumps(body).encode("utf-8"))
    value = (Decimal(size + 4096) * input_rate + Decimal(int(body["max_tokens"])) * output_rate) / 1000000
    return value.quantize(Decimal("0.000001"), rounding="ROUND_CEILING") + Decimal("0.000001")


#: Where `_events` leaves each streamed tool call's raw input and parse error for `_answer` (taken out before the answer).
_TOOL_INPUTS = "_ltcm_tool_inputs"


def _no_constant(name: str) -> Any:
    """Strict JSON: NaN and Infinity are not JSON."""
    raise ValueError(f"{name} is not JSON")


def _same_model(answered: str, asked: str) -> bool:
    """The answer came from the model asked for: the same id, or that id with a dated snapshot suffix. Not a bare prefix:
    `claude-sonnet-5` is a prefix of `claude-sonnet-5-5` (Sept 29, 2026), and the gateway priced the call at the asked
    model's rates."""
    return answered == asked or re.fullmatch(re.escape(asked) + r"-\d{8}", answered) is not None


def _cost(headers: Any) -> Decimal | None:
    try:
        raw = headers.get(COST_HEADER) if headers is not None else None
        value = Decimal(str(raw)) if raw is not None else None
    except (InvalidOperation, ValueError, TypeError):
        return None
    return value if value is not None and value.is_finite() and value >= 0 else None


class Claude:
    """One model through the gateway. `ask` is one question; `converse` takes text turns (the last the user's);
    `messages` is one turn of a tool loop (TOOL CALLS in the module docstring)."""

    def __init__(self, gateway_url: str, token_source: Callable[[], str], *, model: str = MODEL, opener: Any = None,
                 timeout: float = 600.0, read_timeout: float = READ_TIMEOUT, clock: Callable[[], float] | None = None):
        self.url = gateway_url.rstrip("/") + PATH
        self.token_source = token_source
        self.model = model
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout
        self.read_timeout = read_timeout
        self.clock = clock or time.monotonic

    def ask(self, system: str, user: str, *, agent: str, role: str | None = None, max_tokens: int = MAX_TOKENS,
            effort: str = "high", schema: Mapping[str, Any] | None = None, cache: bool = True,
            request_id: str | None = None, stream: bool = False) -> Answer:
        return self.converse(system, [{"role": "user", "content": user}], agent=agent, role=role, max_tokens=max_tokens,
                             effort=effort, schema=schema, cache=cache, request_id=request_id, stream=stream)

    def converse(self, system: str, messages: Sequence[Mapping[str, Any]], *, agent: str, role: str | None = None,
                 max_tokens: int = MAX_TOKENS, effort: str = "high", schema: Mapping[str, Any] | None = None,
                 cache: bool = True, request_id: str | None = None, stream: bool = False) -> Answer:
        """One call. `request_id` (`[A-Za-z0-9:._-]{1,160}`) is the id the gateway files the call's outcome under, so a
        caller that never saw the answer can ask what it cost (`settlement`). `stream` reads the answer as server-sent
        events (the module docstring)."""
        headers = self._headers(agent, role, request_id)
        body = request_body(self.model, system, messages, max_tokens=max_tokens, effort=effort, schema=schema, cache=cache,
                            stream=stream)
        answer = self._answer(*self._send(body, headers, stream=stream, limit=self.timeout))
        stop = answer.stop_reason
        if stop == "refusal":
            raise ClaudeRefusal("Claude declined the request (stop_reason refusal)", answer=answer)
        if stop == "max_tokens":
            raise ClaudeTruncated(f"the Claude answer was cut off at max_tokens {body['max_tokens']}", answer=answer)
        if stop not in ("end_turn", "stop_sequence"):
            raise ClaudeError(f"the Claude answer stopped for {stop or 'no reason'}", answer=answer)
        if schema is not None:
            data = extract_json(answer.text)
            if not isinstance(data, dict):
                raise ClaudeError("the Claude answer held no JSON object", answer=answer)
            answer = replace(answer, data=data)
        return answer

    def messages(self, system: Any, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]], *, agent: str,
                 role: str | None = None, max_tokens: int = MAX_TOKENS_STREAM, effort: str = "medium", tool_choice: Any = "auto",
                 request_id: str | None = None, stream: bool = True, timeout: float | None = None) -> Answer:
        """One turn of a tool loop (TOOL CALLS in the module docstring): the body is `tool_request_body`'s, and the answer
        carries its blocks (`content`) and its calls (`tool_uses`). A `tool_use`, `end_turn` or `stop_sequence` stop is an
        answer; a refusal raises `ClaudeRefusal`, a cut `ClaudeTruncated`, anything else `ClaudeError`, each with the billed
        answer (none of its calls may run). `timeout`, when given, is this call's overall limit (never above the client's);
        the read timeout between events stays."""
        headers = self._headers(agent, role, request_id)
        body = tool_request_body(self.model, system, messages, tools, tool_choice=tool_choice, max_tokens=max_tokens,
                                 effort=effort, stream=stream)
        limit = self.timeout if timeout is None else max(1.0, min(float(timeout), self.timeout))
        answer = self._answer(*self._send(body, headers, stream=stream, limit=limit))
        stop = answer.stop_reason
        if stop == "refusal":
            raise ClaudeRefusal("Claude declined the request (stop_reason refusal)", answer=answer)
        if stop in CUT_STOPS:
            raise ClaudeTruncated(f"the Claude answer was cut off ({stop}, max_tokens {body['max_tokens']})", answer=answer)
        if stop not in TOOL_STOPS:
            raise ClaudeError(f"the Claude answer stopped for {stop or 'no reason'}", answer=answer)
        return answer

    def _headers(self, agent: str, role: str | None, request_id: str | None) -> dict[str, str]:
        if role is not None and (not isinstance(role, str) or not _SLUG.fullmatch(role)):
            raise ClaudeError("invalid Claude role")
        if request_id is not None and (not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id)):
            raise ClaudeError("invalid Claude request id")
        headers = {"Authorization": "Bearer " + self.token_source(), "Content-Type": "application/json",
                   AGENT_HEADER: attribution(agent), "User-Agent": "ltcm-floor/1.0"}
        if role is not None:
            headers[ROLE_HEADER] = role
        if request_id is not None:
            headers[REQUEST_HEADER] = request_id
        return headers

    def _send(self, body: Mapping[str, Any], headers: Mapping[str, str], *, stream: bool,
              limit: float) -> tuple[dict[str, Any], Decimal | None, bool]:
        """POST one body: (the answer's message, the gateway's cost, whether that cost is known). Every failure is a
        ClaudeError (an HTTP refusal with its status and the gateway's `cap`; a transport failure; a stream that errs, stops
        early or goes quiet, with the cost the gateway reported when it did)."""
        request = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), method="POST", headers=dict(headers))
        known = True
        try:
            # A stream's socket timeout is the gap allowed between events; the overall limit is kept by the reader.
            with self.opener(request, timeout=self.read_timeout if stream else limit) as response:
                if stream and str(response.headers.get("Content-Type") or "").startswith("text/event-stream"):
                    payload, cost, known = self._events(response, self.clock() + limit, limit)
                    raw = None
                else:
                    raw = response.read()
                    cost = _cost(response.headers)
        except ClaudeError:
            raise
        except urllib.error.HTTPError as exc:
            raw_error = exc.read()[:4000]
            detail = raw_error[:300].decode("utf-8", "replace")
            try:
                cap = json.loads(raw_error).get("cap")
            except (ValueError, AttributeError):
                cap = None
            raise ClaudeError(f"Claude call refused: HTTP {exc.code} {detail}", status=exc.code, cost_usd=_cost(exc.headers),
                              cap=cap if isinstance(cap, str) else None) from None
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
            raise ClaudeError(f"Claude call failed: {type(exc).__name__}") from None
        if raw is not None:
            try:
                payload = json.loads(raw)
            except (ValueError, TypeError):
                raise ClaudeError("the Claude answer was not JSON", cost_usd=cost) from None
        if not isinstance(payload, dict):
            raise ClaudeError("the Claude answer was not a JSON object", cost_usd=cost)
        return payload, cost, known

    def _answer(self, payload: dict[str, Any], cost: Decimal | None, known: bool) -> Answer:
        """The answer a message makes, before its stop reason is judged: its text (text blocks only; thinking blocks are
        never read as the answer), its blocks as they came, its tool calls, and whether its cost is verified."""
        tool_inputs = payload.pop(_TOOL_INPUTS, None) or {}
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        model = str(payload.get("model") or "")
        verified = (cost is not None and known and type(usage.get("input_tokens")) is int
                    and type(usage.get("output_tokens")) is int and _same_model(model, self.model))
        content = [block for block in payload.get("content") or [] if isinstance(block, dict)]
        text = "".join(block.get("text") or "" for block in content
                       if block.get("type") == "text" and isinstance(block.get("text"), str))
        uses = []
        for block in content:
            if block.get("type") != "tool_use":
                continue
            given = tool_inputs.get(str(block.get("id") or ""))
            value = block.get("input")
            if given is not None:  # streamed: parsed from its fragments when its block stopped
                raw, error = given
            else:
                raw, error = json.dumps(value), None if isinstance(value, dict) else "the tool input was not a JSON object"
            uses.append(ToolUse(id=str(block.get("id") or ""), name=str(block.get("name") or ""),
                                input=dict(value) if isinstance(value, dict) and error is None else {}, raw=raw, error=error))
        return Answer(text=text, data=None, usage=dict(usage), cost_usd=cost, model=model or self.model,
                      stop_reason=str(payload.get("stop_reason") or ""), cost_verified=verified, id=str(payload.get("id") or ""),
                      raw=payload, content=tuple(copy.deepcopy(content)), tool_uses=tuple(uses))

    def _events(self, response: Any, deadline: float, limit: float | None = None) -> tuple[dict[str, Any], Decimal | None, bool]:
        """Read a relayed stream to its end: (the final message rebuilt from its events, the gateway's `ltcm.cost`, whether
        that cost is known). A stream that errs, stops early or goes quiet raises a ClaudeError carrying the gateway's cost
        when it sent one (None when it did not: the caller's hold stands and is trued up from the gateway's record).

        Blocks are rebuilt as Anthropic sends them: a block's own start fields (a tool call's `caller`, a thinking block's
        empty `thinking`), then its deltas: text, thinking, a thinking block's `signature` (`signature_delta`, just before
        the block stops), and a tool call's input fragments (`input_json_delta`), parsed strictly when the block stops (an
        empty input is `{}`; one that is not a JSON object is `{}`, with its raw text and the reason kept for `ToolUse`)."""
        limit = self.timeout if limit is None else limit
        message: dict[str, Any] = {}
        blocks: dict[int, dict[str, Any]] = {}
        partial: dict[int, list[str]] = {}
        inputs: dict[str, tuple[str, str | None]] = {}
        usage: dict[str, Any] = {}
        state = {"stopped": False, "error": None, "cost": None, "known": False}
        data: list[str] = []

        def finish(index: int) -> None:
            """A tool call's block stopped: its input is its fragments, parsed strictly."""
            block = blocks.get(index)
            if block is None or block.get("type") != "tool_use" or index not in partial:
                return
            raw = "".join(partial.pop(index))
            error = None
            try:
                value = json.loads(raw, parse_constant=_no_constant) if raw.strip() else {}
            except ValueError as exc:
                value, error = {}, f"the tool input is not valid JSON ({str(exc)[:120]})"
            if not isinstance(value, dict):
                value, error = {}, "the tool input is not a JSON object"
            block["input"] = value
            inputs[str(block.get("id") or "")] = (raw, error)

        def dispatch() -> None:
            if not data:
                return
            try:
                event = json.loads("\n".join(data))
            except ValueError:
                event = None
            data.clear()
            if not isinstance(event, dict):
                return
            kind = event.get("type")
            index = event.get("index") if type(event.get("index")) is int else 0
            if kind == "message_start" and isinstance(event.get("message"), dict):
                message.update(event["message"])
                usage.update({k: v for k, v in (event["message"].get("usage") or {}).items() if v is not None})
            elif kind == "content_block_start" and isinstance(event.get("content_block"), dict):
                blocks[index] = dict(event["content_block"])
                if blocks[index].get("type") == "tool_use":
                    partial[index] = []
            elif kind == "content_block_delta" and isinstance(event.get("delta"), dict):
                block = blocks.setdefault(index, {"type": "text", "text": ""})
                delta = event["delta"]
                if delta.get("type") == "text_delta":
                    block["text"] = str(block.get("text") or "") + str(delta.get("text") or "")
                elif delta.get("type") == "thinking_delta":
                    block["thinking"] = str(block.get("thinking") or "") + str(delta.get("thinking") or "")
                elif delta.get("type") == "signature_delta":
                    block["signature"] = str(delta.get("signature") or "")
                elif delta.get("type") == "input_json_delta":
                    partial.setdefault(index, []).append(str(delta.get("partial_json") or ""))
            elif kind == "content_block_stop":
                finish(index)
            elif kind == "message_delta":
                for key in ("stop_reason", "stop_sequence", "stop_details"):
                    if isinstance(event.get("delta"), dict) and event["delta"].get(key) is not None:
                        message[key] = event["delta"][key]
                usage.update({k: v for k, v in (event.get("usage") or {}).items() if v is not None})
            elif kind == "message_stop":
                state["stopped"] = True
            elif kind == "error":
                state["error"] = str((event.get("error") or {}).get("type") or "error")
            elif kind == "ltcm.cost":
                try:
                    amount = Decimal(str(event.get("cost_usd"))) if event.get("cost_usd") is not None else None
                except (InvalidOperation, ValueError):
                    amount = None
                if amount is not None and amount.is_finite() and amount >= 0:
                    state["cost"], state["known"] = amount, event.get("known") is True

        try:
            while True:
                if self.clock() > deadline:
                    raise ClaudeError(f"the Claude stream ran past its {limit:.0f}-second limit", cost_usd=state["cost"])
                line = response.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                if not text:
                    dispatch()
                elif text.startswith("data:"):
                    data.append(text[5:][1:] if text[5:].startswith(" ") else text[5:])
            dispatch()
        except ClaudeError:
            raise
        except (http.client.HTTPException, OSError, ValueError) as exc:  # a quiet or cut stream (IncompleteRead)
            raise ClaudeError(f"the Claude stream stalled or broke: {type(exc).__name__}", cost_usd=state["cost"]) from None
        if state["error"]:
            raise ClaudeError(f"Anthropic's stream failed: {state['error']}", cost_usd=state["cost"])
        if not state["stopped"]:
            raise ClaudeError("the Claude stream ended before the answer did", cost_usd=state["cost"])
        for index in list(partial):  # a tool call whose block never stopped: its fragments as they are
            finish(index)
        message["content"] = [blocks[i] for i in sorted(blocks)]
        message["usage"] = usage
        if inputs:
            message[_TOOL_INPUTS] = inputs
        return message, state["cost"], state["known"]

    def settlement(self, request_id: str) -> dict[str, Any] | None:
        """What the gateway booked for call `request_id`: `{"state": "held"|"settled"|"unknown"|"released"|"absent",
        "cost_usd": Decimal | None}`, or None when the gateway cannot be read."""
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            return None
        url = self.url.rsplit("/messages", 1)[0] + "/request/" + request_id
        request = urllib.request.Request(url, headers={"Authorization": "Bearer " + self.token_source(), "User-Agent": "ltcm-floor/1.0"})
        try:
            with self.opener(request, timeout=20) as response:
                data = json.loads(response.read())
            state = str(data.get("state") or "")
            cost = data.get("cost_usd")
            amount = Decimal(str(cost)) if cost is not None else None
        except Exception:  # noqa: BLE001 - unreadable is unknown
            return None
        if state not in ("held", "settled", "unknown", "released", "absent") or (amount is not None and (not amount.is_finite() or amount < 0)):
            return None
        return {"state": state, "cost_usd": amount}


class ClaudeMeter:
    """What is left of the owner's funded Claude total, read from the gateway's `GET /v1/health` (`claude` block).
    `remaining()` is None when the gateway cannot be read, has no Claude block, or reports Claude not configured (no key:
    every call would be a 503); callers then spend nothing on Claude, and the gateway's own 402 is still the backstop."""

    def __init__(self, gateway_url: str, token_source: Callable[[], str], *, opener: Any = None, ttl: float = 60.0,
                 clock: Any = None):
        import threading
        import time as _time

        self.url = gateway_url.rstrip("/") + "/v1/health"
        self.token_source = token_source
        self.opener = opener or urllib.request.urlopen
        self.ttl = ttl
        self.clock = clock or _time.time
        self._at = float("-inf")
        self._value: Decimal | None = None
        self.last: dict[str, Any] = {}
        self._lock = threading.Lock()

    def remaining(self) -> Decimal | None:
        with self._lock:
            now = self.clock()
            if now - self._at < self.ttl:
                return self._value
            self._at = now
            try:
                request = urllib.request.Request(self.url, headers={"Authorization": "Bearer " + self.token_source(),
                                                                    "User-Agent": "ltcm-floor/1.0"})
                with self.opener(request, timeout=20) as response:
                    block = json.load(response).get("claude") or {}
                value = Decimal(str(block["cap_usd"])) - Decimal(str(block["spent_usd"]))
                self._value = value if value.is_finite() and block.get("configured") is not False else None
                self.last = {k: block.get(k) for k in ("cap_usd", "spent_usd", "inflight_usd", "calls", "configured")}
            except Exception:  # noqa: BLE001 - unreadable is unknown, never a number
                self._value = None
            return self._value


__all__ = ["Claude", "ClaudeMeter", "ClaudeError", "ClaudeRefusal", "ClaudeTruncated", "Answer", "ToolUse", "MODEL", "MAX_TOKENS",
           "MAX_TOKENS_STREAM", "READ_TIMEOUT", "REQUEST_HEADER",
           "request_body", "tool_request_body", "reservation_ceiling", "extract_json", "attribution"]
