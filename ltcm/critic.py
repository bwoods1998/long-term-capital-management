"""The live-order critic: a second model reads every real-money order before it is sent.

The deterministic `RiskEngine` is the guardrail and it runs first. It is very good at the rules a
computer can state -- notional, cash, position and gross caps, order counts, market hours -- and
blind to the one failure a language model makes and a rule cannot see: an order that contradicts
the words the desk just published. A rationale that argues a company is overearning, followed by
a buy. A size that does not match the plan the memo laid out. A ticker the rationale never names.

So for a desk trading real money, and only then, one cheap model call reads the mandate, the
intent, the risk engine's own numbers, the rationale, the desk's latest memo and its book, and
answers with two fields. It can only ever say `approve` or `block`, it is asked to judge obvious
contradictions and nothing else, and it is told to approve when in doubt: it is a second pair of
eyes, not a second opinion about the thesis.

Everything about it fails open. A provider error, a timeout, a budget refusal or any output that
is not exactly the JSON asked for leaves the order to the deterministic engine and raises an
`ops.alert`. A model that cannot answer must never become a model that can halt the floor.

An `approve` and a `block` are both published as a `risk.review` event, so the public tape shows
the second check on every live order it actually judged, including the ones it waved through. The
site's contract for that event admits `approve` and `block` only, so a failure (`error`) is an
`ops.alert` and nothing else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .broker import OrderIntent, Position, text
from .manifest import DeskManifest
from .risk import Decision

#: The default profile. Cheap, fast, and a different family from the desks' own models: a critic
#: that shares the writer's blind spots is not a critic.
DEFAULT_PROFILE = "glm_asap"
DEFAULT_EFFORT = "low"
DEFAULT_MAX_OUTPUT_TOKENS = 1024

#: Clip lengths for the packet. The critic reads a page, not a dossier.
MANDATE_CHARS = 1500
RATIONALE_CHARS = 2000
MEMO_CHARS = 1500
REASON_CHARS = 300
MAX_POSITIONS = 25

INSTRUCTIONS = (
    "You are the live-order critic on a public, fully automated trading floor. A deterministic "
    "risk engine has already approved this order against the desk's hard limits; you are the "
    "second pair of eyes before real money is sent to a venue.\n"
    "Block the order only for an obvious error:\n"
    "- the side contradicts the rationale (the rationale argues one way, the order goes the other);\n"
    "- the size or the limit price is inconsistent with the plan the rationale states;\n"
    "- the instrument is one the rationale never mentions;\n"
    "- the order adds to a position the desk already holds beyond what the mandate allows;\n"
    "- the rationale states no catalyst and no exit.\n"
    "Judge nothing else. You do not re-argue the thesis, second-guess the price level or the "
    "timing, and you do not apply risk limits of your own: the engine owns those and has already "
    "run. When in doubt, approve.\n"
    'Answer with one line of strict JSON and nothing else: {"verdict": "approve"|"block", '
    '"reason": "<one sentence>"}'
)


@dataclass(frozen=True)
class CriticReview:
    """One verdict. `error` means the critic could not answer and the order proceeds."""

    verdict: str  # "approve" | "block" | "error"
    reason: str
    model: str

    @property
    def blocked(self) -> bool:
        return self.verdict == "block"

    def payload(self, intent_id: str, desk_id: str) -> dict[str, Any]:
        """The public `risk.review` payload.

        Exactly these five keys, in the shapes the site accepts: `verdict` is `approve` or
        `block` (an `error` review is never published), `reason` is at most 2000 characters and
        `model` at most 80. One malformed row would reject a whole publication batch.
        """
        return {
            "intent_id": intent_id,
            "desk_id": desk_id,
            "verdict": self.verdict,
            "reason": str(self.reason)[:2000],
            "model": str(self.model)[:80],
        }


def _clip(value: Any, limit: int) -> str:
    body = " ".join(str(value or "").split())
    return body if len(body) <= limit else body[: limit - 1].rstrip() + "…"


def _instrument_label(instrument: Any) -> str:
    label = f"{instrument.asset_class} {instrument.symbol} on {instrument.venue}"
    if instrument.market_id:
        label += f" (market {instrument.market_id})"
    if instrument.expiry:
        label += f" expiring {instrument.expiry}"
    if instrument.strike is not None and instrument.right:
        label += f", {text(instrument.strike)} {instrument.right}"
    return label


def _limits_line(manifest: DeskManifest) -> str:
    limits = manifest.limits
    return (
        f"max {limits.max_position_pct:.0%} of desk equity in one position, "
        f"max {limits.max_gross_pct:.0%} gross, "
        f"max {limits.max_order_notional_pct:.0%} of equity in one order, "
        f"halt at {limits.max_daily_loss_pct:.0%} daily loss, "
        f"at most {limits.max_orders_per_day} orders a day, "
        f"limit price within {limits.max_limit_deviation_pct:.0%} of the reference price"
    )


def _position_lines(positions: Mapping[str, Position] | None) -> list[str]:
    rows = []
    for key, position in sorted((positions or {}).items()):
        if position.quantity == 0:
            continue
        line = f"- {key}: {text(position.quantity)} at average cost {text(position.average_cost)}"
        if position.mark is not None:
            line += f", marked {text(position.mark)}"
        rows.append(line)
    return rows[:MAX_POSITIONS] or ["- none"]


def packet(
    *,
    intent: OrderIntent,
    manifest: DeskManifest,
    decision: Decision,
    positions: Mapping[str, Position] | None = None,
    memo: str | None = None,
) -> str:
    """The facts the critic judges. No prompts, no prices it could republish, no secrets."""
    reference = text(decision.reference_price) or "unknown"
    notional = text(decision.notional) or "unknown"
    limit_price = text(intent.limit_price) or "none (market order)"
    return "\n".join(
        [
            f"Desk: {manifest.name} ({manifest.id}), {manifest.family} family, live capital.",
            f"Mandate: {_clip(manifest.mandate, MANDATE_CHARS)}",
            f"Limits: {_limits_line(manifest)}",
            "",
            "The order the desk wants to send:",
            f"- instrument: {_instrument_label(intent.instrument)}",
            f"- side: {intent.side}",
            f"- quantity: {text(intent.quantity)}",
            f"- order type: {intent.order_type}",
            f"- limit price: {limit_price}",
            f"- time in force: {intent.time_in_force}",
            f"- risk engine reference price: {reference}",
            f"- risk engine notional: {notional} USD",
            "",
            "Rationale the desk published with this order:",
            _clip(intent.rationale, RATIONALE_CHARS),
            "",
            "The desk's latest memo:",
            _clip(memo, MEMO_CHARS) or "(none)",
            "",
            "Positions the desk holds now:",
            *_position_lines(positions),
        ]
    )


def parse_verdict(output: Any) -> tuple[str, str] | None:
    """`(verdict, reason)` for strict JSON with the two fields asked for, else None.

    A single fenced code block is unwrapped -- models add them and the JSON inside is still
    exactly what was asked for -- but nothing else is guessed at. Anything this returns None for
    is an unusable answer, and an unusable answer means the order proceeds on the engine alone.
    """
    if not isinstance(output, str):
        return None
    body = output.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.rstrip()
        if body.endswith("```"):
            body = body[:-3]
        body = body.strip()
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    verdict = data.get("verdict")
    reason = data.get("reason")
    if verdict not in ("approve", "block"):
        return None
    if not isinstance(reason, str) or not reason.strip():
        return None
    return verdict, _clip(reason, REASON_CHARS)


class LiveOrderCritic:
    """One model call per live order. Never raises; the worst it returns is `error`."""

    def __init__(
        self,
        provider: Any,
        *,
        profile: str = DEFAULT_PROFILE,
        reasoning_effort: str = DEFAULT_EFFORT,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ):
        self.provider = provider
        self.profile = profile or DEFAULT_PROFILE
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = int(max_output_tokens)

    # ------------------------------------------------------------------ helpers
    def model(self) -> str:
        try:
            from .provider import model_of

            return model_of(self.profile)
        except Exception:
            return self.profile

    def request_key(self, intent_id: str) -> str:
        return f"critic:{intent_id}"

    # ------------------------------------------------------------------ the call
    def review(
        self,
        *,
        intent: OrderIntent,
        manifest: DeskManifest,
        decision: Decision,
        positions: Mapping[str, Position] | None = None,
        memo: str | None = None,
    ) -> CriticReview:
        model = self.model()
        if self.provider is None:
            return CriticReview("error", "no model provider is configured", model)
        items = [
            {"role": "system", "content": INSTRUCTIONS},
            {
                "role": "user",
                "content": packet(
                    intent=intent,
                    manifest=manifest,
                    decision=decision,
                    positions=positions,
                    memo=memo,
                ),
            },
        ]
        try:
            response = self.provider.respond(
                self.profile,
                items,
                tools=None,
                desk_id=manifest.id,
                session_id=intent.session_id,
                request_key=self.request_key(intent.id),
                reasoning_effort=self.reasoning_effort,
                max_output_tokens=self.max_output_tokens,
                desk_cap_usd_per_day=manifest.budget_usd_per_day,
            )
        except Exception as exc:
            # Budget refusals, transport failures and timeouts all look the same from here, and
            # all of them mean the same thing: the engine decides alone. The code, never a body.
            code = getattr(exc, "code", None) or type(exc).__name__
            return CriticReview("error", f"critic call failed: {code}", model)
        parsed = parse_verdict(getattr(response, "output_text", None))
        if parsed is None:
            return CriticReview("error", "critic returned no usable verdict", model)
        verdict, reason = parsed
        return CriticReview(verdict, reason, model)


def build(provider: Any, config: Mapping[str, Any] | None = None) -> LiveOrderCritic | None:
    """The critic a service configuration asks for, or None when it is switched off."""
    settings = dict(config or {})
    if not settings.get("critic_enabled", True):
        return None
    if provider is None:
        return None
    return LiveOrderCritic(
        provider,
        profile=str(settings.get("critic_profile") or DEFAULT_PROFILE),
        reasoning_effort=str(settings.get("critic_reasoning_effort") or DEFAULT_EFFORT),
        max_output_tokens=int(settings.get("critic_max_output_tokens") or DEFAULT_MAX_OUTPUT_TOKENS),
    )


__all__ = [
    "CriticReview",
    "DEFAULT_PROFILE",
    "INSTRUCTIONS",
    "LiveOrderCritic",
    "build",
    "packet",
    "parse_verdict",
]
