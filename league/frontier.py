"""The frontier model, reached only through the gateway.

The OpenAI key lives in the Cloudflare gateway and nowhere else. The House asks
`POST <gateway>/v1/frontier/responses`; the gateway reserves the call's worst case against the
owner's monthly budget, forwards it, settles at what it really cost and says so in
`X-LTCM-Cost-USD`. A call that does not fit in what is left of the month is refused there (402),
not here, so nothing on Sail can spend past the line.
"""

from __future__ import annotations

import json
import re
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

MODEL = "gpt-6-astra"
COST_HEADER = "X-LTCM-Cost-USD"
AGENT_HEADER = "X-LTCM-Agent"
MAX_OUTPUT_TOKENS = 16000
# Verified standard-service ceilings, including long-context cache writes. Kept outside
# game.json: agents may choose a model, but cannot supply the price used to admit its bill.
# https://developers.openai.com/api/docs/pricing (2026-09-20), dollars / million tokens.
MODEL_CEILINGS = {
    "gpt-6-astra": (Decimal("25"), Decimal("75")),
    "gpt-5.6-sol": (Decimal("10"), Decimal("30")),
    "gpt-5.6-terra": (Decimal("5"), Decimal("18")),
    "gpt-5.6-luna": (Decimal("0.50"), Decimal("1.80")),
    # GPT-6 Sol and Luna, launched Sept 22, 2026 at half the GPT-5.6 rates: the long-context
    # cache-write input rate and the long-context output rate (gateway/wrangler.jsonc).
    "gpt-6-sol": (Decimal("5"), Decimal("15")),
    "gpt-6-luna": (Decimal("0.25"), Decimal("0.75")),
}


class FrontierError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Answer:
    text: str
    cost_usd: Decimal
    usage: dict[str, Any]
    model: str
    status: str = 'completed'
    cost_verified: bool = True

    def json(self) -> dict[str, Any]:
        """The first JSON object in the answer. Raises FrontierError when there is none."""
        if self.status != 'completed':
            raise FrontierError(f'the model response is {self.status}; no partial proposal is accepted')
        return extract_json(self.text)


def attribution(name: str) -> str:
    """The name the gateway files this call's cost under. It accepts `^[a-z0-9][a-z0-9_-]{0,63}$`
    and files anything else under "unattributed" (found on the night of the build: `audit:<agent>`
    was unattributed for its colon)."""
    clean = re.sub(r"[^a-z0-9_-]+", "-", str(name or "").lower()).strip("-_")[:64]
    return clean or "house"


def extract_json(text: str) -> dict[str, Any]:
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
    raise FrontierError("the frontier model's answer held no JSON object")


def output_text(payload: dict[str, Any]) -> str:
    """The text of a Responses API result."""
    if isinstance(payload.get("output_text"), str) and payload["output_text"]:
        return payload["output_text"]
    parts = []
    for item in payload.get("output") or []:
        if isinstance(item, dict) and item.get("type") == "message":
            for block in item.get("content") or []:
                if isinstance(block, dict) and block.get("type") in ("output_text", "text") and isinstance(block.get("text"), str):
                    parts.append(block["text"])
    return "\n".join(parts)


class Frontier:
    def __init__(self, gateway_url: str, token_source: Callable[[], str], *, model: str = MODEL, opener: Any = None, timeout: float = 600.0, spend_guard: Any = None):
        self.url = gateway_url.rstrip("/") + "/v1/frontier/responses"
        self.token_source = token_source
        self.model = model
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout
        self.spend_guard = spend_guard

    def ask(self, *, system: str, user: str, agent: str, max_output_tokens: int = 6000, effort: str = "medium") -> Answer:
        return self.converse([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             agent=agent, max_output_tokens=max_output_tokens, effort=effort)

    def converse(self, messages: list[dict[str, Any]], *, agent: str, max_output_tokens: int = 6000, effort: str = "medium",
                 cache: dict[str, Any] | None = None) -> Answer:
        """One call over a list of text messages, optionally with prompt-cache hints.

        `cache` carries `prompt_cache_key` / `prompt_cache_options` exactly as the Responses API
        names them; the gateway admits only bounded values (gateway/lib/frontier.mjs). A cached
        prefix changes the bill only through the usage block the gateway settles from."""
        body = {
            "model": self.model,
            "input": list(messages),
            "max_output_tokens": max(1, min(int(max_output_tokens), MAX_OUTPUT_TOKENS)),
            "reasoning": {"effort": effort},
        }
        for name in ("prompt_cache_key", "prompt_cache_options"):
            if cache and cache.get(name) is not None:
                body[name] = cache[name]
        request = urllib.request.Request(
            self.url, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Authorization": "Bearer " + self.token_source(), "Content-Type": "application/json",
                     AGENT_HEADER: attribution(agent), "User-Agent": "ltcm-floor/1.0"},
        )
        commitment = "frontier:" + secrets.token_hex(16)
        if self.spend_guard is not None:
            if self.model not in MODEL_CEILINGS:
                raise FrontierError("the spend guard has no verified price for this model")
            # One UTF-8 byte per possible input token plus framing, including the long-context
            # and cache-write premiums. Standard service only; no built-in paid tools.
            input_rate, output_rate = MODEL_CEILINGS[self.model]
            hold = (Decimal(len(request.data) + 4096) * input_rate + Decimal(body["max_output_tokens"]) * output_rate) / 1000000
            try:
                self.spend_guard.reserve(commitment, "foundation-review", hold)
            except RuntimeError as exc:
                raise FrontierError(str(exc)) from None
        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.load(response)
                cost = response.headers.get(COST_HEADER)
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "replace")
            if self.spend_guard is not None and 400 <= exc.code < 500:
                # Refused, not billed: the gateway reserves nothing for its own refusals (402 month,
                # 400, 401, 403, 413) and settles an upstream 4xx at $0 (gateway/lib/router.mjs). Until
                # Sept 23, 2026 the House kept the worst-case hold of every refused call for good.
                self.spend_guard.settle(commitment, 0)
            raise FrontierError(f"frontier call refused: HTTP {exc.code} {detail}", status=exc.code) from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise FrontierError(f"frontier call failed: {type(exc).__name__}") from None
        if not isinstance(payload, dict):
            raise FrontierError("the frontier model's answer was not a JSON object")
        try:
            cost_usd = Decimal(str(cost)) if cost is not None else Decimal(0)
        except InvalidOperation:
            cost_usd = Decimal(0)
        if not cost_usd.is_finite() or cost_usd < 0:
            cost_usd = Decimal(0)  # the gateway's own meter is the record; a garbled header charges nothing here
        verified = False
        if cost is not None:
            try:
                confirmed = Decimal(str(cost))
                usage = payload.get('usage') if isinstance(payload.get('usage'), dict) else {}
                tokens_in, tokens_out = usage.get('input_tokens'), usage.get('output_tokens')
                if (confirmed.is_finite() and confirmed >= 0 and type(tokens_in) is int and type(tokens_out) is int
                        and min(tokens_in, tokens_out) >= 0 and payload.get('model') == self.model):
                    verified = True
                    # The gateway's metered cost, the same figure its month line enforces. It prices
                    # cache reads, cache writes and the long-context premiums from the provider's own
                    # usage block (gateway/lib/frontier.mjs actualCost, since Sept 22, 2026). Until
                    # Sept 23 the House booked max(this, every token at the long-context ceiling):
                    # measured then, the gateway's whole September was $267.29 while the House had
                    # settled $393.08 since Sept 21 alone, so the allowance closed at about half the
                    # owner's real spend. The hold is the ceiling; a verified call settles at its cost.
                    if self.spend_guard is not None:
                        self.spend_guard.settle(commitment, confirmed)
            except InvalidOperation:
                pass  # unknown costs retain the full hold, including across restarts
        return Answer(output_text(payload), cost_usd, dict(payload.get("usage") or {}), str(payload.get("model") or self.model),
                      str(payload.get('status') or 'completed'), verified)


class FrontierMonth:
    """What is left of the gateway's monthly frontier budget, read from `GET /v1/health`.

    The House's campaign meters its own holds, but the gateway's month is the line that really
    refuses (402), and it also carries holds the House never sees: a call that times out keeps its
    worst case there. On Sept 21, 2026 the campaign believed $77 remained while the gateway had $40,
    so cheap research would have spent the last of the month and left nothing for the audits that
    promotion to real money requires. `remaining()` is None when the gateway cannot be read; the
    callers then leave spending alone, and the gateway's own 402 is still the backstop.

    Since Sept 24, 2026 this month is also OpenAI's METER. Given the campaign (`meter`), every
    reading is fed to `CampaignBudget.observe_month`, which turns the month's spend into a figure
    that never falls, and the reader registers itself so that a reservation finding the last
    reading a minute old reads again first (`CampaignBudget.meter_reader`). The House reads it on
    every tick; a gateway that cannot be read leaves the meter unread, and after 180 s the campaign
    refuses OpenAI reservations -- paid OpenAI work stops, nothing else does."""

    def __init__(self, gateway_url: str, token_source: Callable[[], str], *, opener: Any = None, ttl: float = 60.0, clock: Any = None,
                 meter: Any = None):
        import threading
        import time as _time

        self.url = gateway_url.rstrip("/") + "/v1/health"
        self.token_source = token_source
        self.opener = opener or urllib.request.urlopen
        self.ttl = ttl
        self.clock = clock or _time.time
        self._at = float("-inf")
        self._value: Decimal | None = None
        self._bonus: Decimal | None = None
        self._lock = threading.Lock()  # one reading at a time: the tick and a reservation may both ask
        self.meter = meter
        if meter is not None:
            meter.meter_reader("openai", self.refresh)

    def remaining(self) -> Decimal | None:
        with self._lock:
            now = self.clock()
            if now - self._at < self.ttl:
                return self._value
            self._at = now
            reading = None
            try:
                request = urllib.request.Request(self.url, headers={"Authorization": "Bearer " + self.token_source(), "User-Agent": "ltcm-floor/1.0"})
                with self.opener(request, timeout=20) as response:
                    month = json.load(response).get("frontier") or {}
                value = Decimal(str(month["cap_usd"])) - Decimal(str(month["spent_usd"]))
                self._value = value if value.is_finite() else None
                self._bonus = None
                if month.get("base_cap_usd") is not None and self._value is not None:
                    # The cap in force less the configured month: what profit on the real accounts
                    # added (gateway/lib/equity.mjs). Absent from a gateway that does not index.
                    bonus = Decimal(str(month["cap_usd"])) - Decimal(str(month["base_cap_usd"]))
                    self._bonus = max(bonus, Decimal(0)) if bonus.is_finite() else None
                reading = month if self._value is not None else None
            except Exception:  # noqa: BLE001 - unreadable is unknown, never a number
                self._value = self._bonus = None
            if reading is not None and self.meter is not None:
                self._feed(reading)
            return self._value

    def _feed(self, month: dict[str, Any]) -> None:
        """One reading to OpenAI's meter. A reading the meter refuses leaves it unread (and OpenAI's
        reservations refused after 180 s); it never makes the month itself unreadable here."""
        try:
            # `cap`: the month's own line, which the House's OpenAI line never reads above while this
            # reading is fresh (`CampaignBudget.remaining`).
            self.meter.observe_month("openai", str(month.get("month") or ""), month["spent_usd"],
                                     settled=month.get("settled_usd"), cap=month["cap_usd"], previous=month.get("previous"),
                                     evidence={k: month.get(k) for k in ("cap_usd", "calls", "inflight_usd")})
        except Exception:  # noqa: BLE001 - see above
            pass

    def refresh(self) -> bool:
        """Read the month again if the last reading is older than the TTL. True when OpenAI's meter
        is fresh afterwards (or, with no meter, when the month could be read)."""
        self.remaining()
        return bool(self.meter.ready("openai")) if self.meter is not None else self._value is not None

    def profit_bonus(self) -> Decimal | None:
        """What the gateway's profit indexing adds to the month's cap, from the same reading as
        `remaining`: None when the gateway cannot be read or does not index."""
        self.remaining()
        return self._bonus


def frontier_tier(remaining: Decimal | None, reserve: Any) -> str:
    """Which frontier work the month still pays for, from `game.json` `frontier_reserve`.

    "all": everything. "earned": the unearned scheduled roles (operator, teacher, designer) and
    cheap-model research stop, so what is left goes to the roles that write code and to the work
    agents pay for. "audits": only audits and consultations agents buy with credits they earned.
    Unknown (None) is "all": the gateway still refuses at its line."""
    if remaining is None or not reserve:
        return "all"
    if remaining < Decimal(str(reserve.get("code_roles_usd", "0"))):
        return "audits"
    if remaining < Decimal(str(reserve.get("earned_usd", "0"))):
        return "earned"
    return "all"


#: The roles each tier still runs.
TIER_ROLES = {"all": None, "earned": frozenset({"architect", "toolsmith"}), "audits": frozenset()}
