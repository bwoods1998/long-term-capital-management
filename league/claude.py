"""Claude, reached only through the gateway (Sept 26, 2026, the swarm sprint).

The Anthropic key lives in the Cloudflare gateway and nowhere else. The House asks
`POST <gateway>/v1/claude/messages`; the gateway reserves the call's worst case against the owner's
funded total (`CLAUDE_USD`), forwards it, settles at what Anthropic says it used and reports that in
`X-LTCM-Cost-USD` (gateway/lib/claude.mjs). A call that does not fit is refused there (402), and so is
every call while the kill switch is engaged (423).

The request is Anthropic's Messages API, not OpenAI's Responses API: thinking cannot be disabled on
Claude Opus 5.5 (it is adaptive; `output_config.effort` is the control, and its default is `medium`, so
it is always sent), there is no sampling parameter, no forced tool choice and no assistant prefill, and
the answer's `stop_reason` is read before its content. The stable system prefix carries a 5-minute
`cache_control` marker, so a second call within minutes reads it at a twentieth of the input rate.

STREAMING (Sept 27, 2026). A high-effort answer can take minutes, and Cloudflare in front of
api.anthropic.com gives up on a silent origin after 100 seconds (HTTP 524). A call with `stream=True` asks
for `stream: true`; the gateway relays Anthropic's server-sent events as they arrive and ends with its own
`ltcm.cost` event (what its meter booked). This client rebuilds the final message from the events (the
text blocks, the stop reason, the usage), with a read timeout between events (`read_timeout`, 120 s) and an
overall limit (`timeout`, 600 s). Thinking is asked for `display: "summarized"` on a stream, so its deltas
keep the bytes flowing while the model thinks (display changes what is shown, not what is billed).

Durable spend holds live with the caller (the swarm's `ModelRouter` books one in its store before
dispatch, #380's pattern); this module gives it the exact request and its worst-case ceiling.
Standard library only.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
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
#: them. Kept here so the caller's hold is never below the gateway's own reservation.
MODEL_CEILINGS = {
    "claude-opus-5-5": (Decimal("5"), Decimal("20")),
    "claude-sonnet-5": (Decimal("2.50"), Decimal("10")),
}
_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_REQUEST_ID = re.compile(r"[A-Za-z0-9:._-]{1,160}")


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
    """`stop_reason: "max_tokens"`: the answer was cut off. Billed at its usage."""


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


def _cost(headers: Any) -> Decimal | None:
    try:
        raw = headers.get(COST_HEADER) if headers is not None else None
        value = Decimal(str(raw)) if raw is not None else None
    except (InvalidOperation, ValueError, TypeError):
        return None
    return value if value is not None and value.is_finite() and value >= 0 else None


class Claude:
    """One model through the gateway. `ask` is one question; `converse` takes text turns (the last the user's)."""

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
        if role is not None and (not isinstance(role, str) or not _SLUG.fullmatch(role)):
            raise ClaudeError("invalid Claude role")
        if request_id is not None and (not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id)):
            raise ClaudeError("invalid Claude request id")
        body = request_body(self.model, system, messages, max_tokens=max_tokens, effort=effort, schema=schema, cache=cache,
                            stream=stream)
        headers = {"Authorization": "Bearer " + self.token_source(), "Content-Type": "application/json",
                   AGENT_HEADER: attribution(agent), "User-Agent": "ltcm-floor/1.0"}
        if role is not None:
            headers[ROLE_HEADER] = role
        if request_id is not None:
            headers[REQUEST_HEADER] = request_id
        request = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
        known = True
        try:
            # A stream's socket timeout is the gap allowed between events; the overall limit is kept by the reader.
            with self.opener(request, timeout=self.read_timeout if stream else self.timeout) as response:
                if stream and str(response.headers.get("Content-Type") or "").startswith("text/event-stream"):
                    payload, cost, known = self._events(response, self.clock() + self.timeout)
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
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ClaudeError(f"Claude call failed: {type(exc).__name__}") from None
        if raw is not None:
            try:
                payload = json.loads(raw)
            except (ValueError, TypeError):
                raise ClaudeError("the Claude answer was not JSON", cost_usd=cost) from None
        if not isinstance(payload, dict):
            raise ClaudeError("the Claude answer was not a JSON object", cost_usd=cost)
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        model = str(payload.get("model") or "")
        verified = (cost is not None and known and type(usage.get("input_tokens")) is int
                    and type(usage.get("output_tokens")) is int and model.startswith(self.model))
        # Only text blocks are the answer; thinking blocks arrive with empty text by default and are never read.
        text = "".join(block.get("text") or "" for block in payload.get("content") or []
                       if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str))
        stop = str(payload.get("stop_reason") or "")
        answer = Answer(text=text, data=None, usage=dict(usage), cost_usd=cost, model=model or self.model, stop_reason=stop,
                        cost_verified=verified, id=str(payload.get("id") or ""), raw=payload)
        if stop == "refusal":
            raise ClaudeRefusal("Claude declined the request (stop_reason refusal)", answer=answer)
        if stop == "max_tokens":
            raise ClaudeTruncated(f"the Claude answer was cut off at max_tokens {body['max_tokens']}", answer=answer)
        if stop not in ("end_turn", "stop_sequence"):
            raise ClaudeError(f"the Claude answer stopped for {stop or 'no reason'}", answer=answer)
        if schema is not None:
            data = extract_json(text)
            if not isinstance(data, dict):
                raise ClaudeError("the Claude answer held no JSON object", answer=answer)
            answer = Answer(text=text, data=data, usage=answer.usage, cost_usd=cost, model=answer.model, stop_reason=stop,
                            cost_verified=verified, id=answer.id, raw=payload)
        return answer

    def _events(self, response: Any, deadline: float) -> tuple[dict[str, Any], Decimal | None, bool]:
        """Read a relayed stream to its end: (the final message rebuilt from its events, the gateway's `ltcm.cost`, whether
        that cost is known). A stream that errs, stops early or goes quiet raises a ClaudeError carrying the gateway's cost
        when it sent one (None when it did not: the caller's hold stands and is trued up from the gateway's record)."""
        message: dict[str, Any] = {}
        blocks: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        state = {"stopped": False, "error": None, "cost": None, "known": False}
        data: list[str] = []

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
            if kind == "message_start" and isinstance(event.get("message"), dict):
                message.update(event["message"])
                usage.update({k: v for k, v in (event["message"].get("usage") or {}).items() if v is not None})
            elif kind == "content_block_start" and isinstance(event.get("content_block"), dict):
                blocks[int(event.get("index") or 0)] = dict(event["content_block"])
            elif kind == "content_block_delta" and isinstance(event.get("delta"), dict):
                block = blocks.setdefault(int(event.get("index") or 0), {"type": "text", "text": ""})
                delta = event["delta"]
                if delta.get("type") == "text_delta":
                    block["text"] = str(block.get("text") or "") + str(delta.get("text") or "")
                elif delta.get("type") == "thinking_delta":
                    block["thinking"] = str(block.get("thinking") or "") + str(delta.get("thinking") or "")
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
                    raise ClaudeError(f"the Claude stream ran past its {self.timeout:.0f}-second limit", cost_usd=state["cost"])
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
        except (OSError, ValueError) as exc:  # socket.timeout: no byte for `read_timeout` seconds
            raise ClaudeError(f"the Claude stream stalled or broke: {type(exc).__name__}", cost_usd=state["cost"]) from None
        if state["error"]:
            raise ClaudeError(f"Anthropic's stream failed: {state['error']}", cost_usd=state["cost"])
        if not state["stopped"]:
            raise ClaudeError("the Claude stream ended before the answer did", cost_usd=state["cost"])
        message["content"] = [blocks[i] for i in sorted(blocks)]
        message["usage"] = usage
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


__all__ = ["Claude", "ClaudeMeter", "ClaudeError", "ClaudeRefusal", "ClaudeTruncated", "Answer", "MODEL", "MAX_TOKENS",
           "MAX_TOKENS_STREAM", "READ_TIMEOUT", "REQUEST_HEADER",
           "request_body", "reservation_ceiling", "extract_json", "attribution"]
