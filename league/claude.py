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

Durable spend holds live with the caller (the swarm's `ModelRouter` books one in its store before
dispatch, #380's pattern); this module gives it the exact request and its worst-case ceiling.
Standard library only.
"""

from __future__ import annotations

import json
import re
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
#: The gateway's ceiling (gateway/lib/claude.mjs MAX_TOKENS): thinking and the answer together.
MAX_TOKENS = 16000
EFFORTS = ("low", "medium", "high", "xhigh", "max")
#: Dollars per million tokens: the dearest input rate (a 5-minute cache write) and the output rate, from
#: platform.claude.com/docs/en/about-claude/pricing (Sept 26, 2026), as gateway/wrangler.jsonc CLAUDE_MODELS prices
#: them. Kept here so the caller's hold is never below the gateway's own reservation.
MODEL_CEILINGS = {
    "claude-opus-5-5": (Decimal("5"), Decimal("20")),
    "claude-sonnet-5": (Decimal("2.50"), Decimal("10")),
}
_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


class ClaudeError(RuntimeError):
    """A Claude call that produced no usable answer. `status` is the HTTP status when there was one; `answer` is the
    billed answer when one came back (a refusal, a truncation, an answer without the asked-for JSON); `cost_usd` is the
    gateway's settled cost when it said (None when it is unknown)."""

    def __init__(self, message: str, *, status: int | None = None, answer: "Answer | None" = None,
                 cost_usd: Decimal | None = None):
        super().__init__(message)
        self.status = status
        self.answer = answer
        self.cost_usd = answer.cost_usd if answer is not None and cost_usd is None else cost_usd


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
                 effort: str = "high", schema: Mapping[str, Any] | None = None, cache: bool = True) -> dict[str, Any]:
    """The one request shape the gateway admits: the system prompt as a text block (marked for the 5-minute cache when
    `cache`), text turns ending with the user's, adaptive thinking, an explicit effort, and a JSON-schema answer format
    when `schema` is given."""
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
    body: dict[str, Any] = {"model": model, "max_tokens": max(1, min(int(max_tokens), MAX_TOKENS))}
    if block["text"]:
        body["system"] = [block]
    body.update({"messages": turns, "thinking": {"type": "adaptive"}, "output_config": output})
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
                 timeout: float = 600.0):
        self.url = gateway_url.rstrip("/") + PATH
        self.token_source = token_source
        self.model = model
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout

    def ask(self, system: str, user: str, *, agent: str, role: str | None = None, max_tokens: int = MAX_TOKENS,
            effort: str = "high", schema: Mapping[str, Any] | None = None, cache: bool = True) -> Answer:
        return self.converse(system, [{"role": "user", "content": user}], agent=agent, role=role, max_tokens=max_tokens,
                             effort=effort, schema=schema, cache=cache)

    def converse(self, system: str, messages: Sequence[Mapping[str, Any]], *, agent: str, role: str | None = None,
                 max_tokens: int = MAX_TOKENS, effort: str = "high", schema: Mapping[str, Any] | None = None,
                 cache: bool = True) -> Answer:
        if role is not None and (not isinstance(role, str) or not _SLUG.fullmatch(role)):
            raise ClaudeError("invalid Claude role")
        body = request_body(self.model, system, messages, max_tokens=max_tokens, effort=effort, schema=schema, cache=cache)
        headers = {"Authorization": "Bearer " + self.token_source(), "Content-Type": "application/json",
                   AGENT_HEADER: attribution(agent), "User-Agent": "ltcm-floor/1.0"}
        if role is not None:
            headers[ROLE_HEADER] = role
        request = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read()
                cost = _cost(response.headers)
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "replace")
            raise ClaudeError(f"Claude call refused: HTTP {exc.code} {detail}", status=exc.code, cost_usd=_cost(exc.headers)) from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ClaudeError(f"Claude call failed: {type(exc).__name__}") from None
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            raise ClaudeError("the Claude answer was not JSON", cost_usd=cost) from None
        if not isinstance(payload, dict):
            raise ClaudeError("the Claude answer was not a JSON object", cost_usd=cost)
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        model = str(payload.get("model") or "")
        verified = (cost is not None and type(usage.get("input_tokens")) is int and type(usage.get("output_tokens")) is int
                    and model.startswith(self.model))
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


class ClaudeMeter:
    """What is left of the owner's funded Claude total, read from the gateway's `GET /v1/health` (`claude` block).
    `remaining()` is None when the gateway cannot be read or has no Claude block; callers then spend nothing on Claude,
    and the gateway's own 402 is still the backstop."""

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
                self._value = value if value.is_finite() else None
                self.last = {k: block.get(k) for k in ("cap_usd", "spent_usd", "inflight_usd", "calls", "configured")}
            except Exception:  # noqa: BLE001 - unreadable is unknown, never a number
                self._value = None
            return self._value


__all__ = ["Claude", "ClaudeMeter", "ClaudeError", "ClaudeRefusal", "ClaudeTruncated", "Answer", "MODEL", "MAX_TOKENS",
           "request_body", "reservation_ceiling", "extract_json", "attribution"]
