"""The frontier model, reached only through the gateway.

The OpenAI key lives in the Cloudflare gateway and nowhere else. The House asks
`POST <gateway>/v1/frontier/responses`; the gateway reserves the call's worst case against the
owner's monthly budget, forwards it, settles at what it really cost and says so in
`X-LTCM-Cost-USD`. A call that does not fit in what is left of the month is refused there (402),
not here, so nothing on Sail can spend past the line.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

MODEL = "gpt-6-astra"
COST_HEADER = "X-LTCM-Cost-USD"
AGENT_HEADER = "X-LTCM-Agent"
MAX_OUTPUT_TOKENS = 16000


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

    def json(self) -> dict[str, Any]:
        """The first JSON object in the answer. Raises FrontierError when there is none."""
        return extract_json(self.text)


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
    def __init__(self, gateway_url: str, token_source: Callable[[], str], *, model: str = MODEL, opener: Any = None, timeout: float = 600.0):
        self.url = gateway_url.rstrip("/") + "/v1/frontier/responses"
        self.token_source = token_source
        self.model = model
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout

    def ask(self, *, system: str, user: str, agent: str, max_output_tokens: int = 6000, effort: str = "medium") -> Answer:
        body = {
            "model": self.model,
            "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_output_tokens": max(1, min(int(max_output_tokens), MAX_OUTPUT_TOKENS)),
            "reasoning": {"effort": effort},
        }
        request = urllib.request.Request(
            self.url, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Authorization": "Bearer " + self.token_source(), "Content-Type": "application/json",
                     AGENT_HEADER: agent[:60], "User-Agent": "ltcm-floor/1.0"},
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.load(response)
                cost = response.headers.get(COST_HEADER)
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "replace")
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
        return Answer(output_text(payload), cost_usd, dict(payload.get("usage") or {}), str(payload.get("model") or self.model))
