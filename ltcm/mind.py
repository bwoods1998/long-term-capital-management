"""The Firm Mind: what one desk learns, every desk inherits.

Every desk writes a `desk.outcome` when a position closes: a Kalshi settlement or a spot sell, with
the entry, the exit, the size, the P&L, how long it was held, the sentence that opened it and
whether real money was at stake. Until now each desk read only its own. The Firm Mind reads all of
them and keeps a small book of *rules*: machine-checkable statements about which trades the floor
should avoid or prefer, each one scored in code against the whole tape.

A rule is JSON::

    {"id": "weather-no-legs-above-90c", "statement": "one sentence a desk can act on",
     "filter": {"series_prefix": ["KXHIGH"], "family": [...], "strategy": [...],
                "result_side": "no", "entry_price": [0.9, 1.0], "held_hours": [0, 24],
                "real_money": null, "venue": "kalshi"},
     "direction": "avoid"}

Every filter key is optional (at least one is required) and a trade must satisfy every key given.
`series_prefix` matches the start of the ticker (Kalshi `SERIES-DATE-STRIKE`, so `KXHIGH` covers
every city's high; a Coinbase product id such as `BTC-USD` matches the same way), `strategy` names
the `[strategy <name>]` tag at the start of the opening rationale (`discretionary` for a trade a
desk placed by hand), `result_side` is the leg the desk held, read from the instrument key (not the
market's result), and the two ranges are inclusive.

`evaluate` selects the matching outcomes from the newest 10,000 of every desk and computes n,
wins, P&L, P&L per dollar of entry notional (entry price x quantity) per trade, a seeded bootstrap
95% interval of its mean (1,000 resamples) and when the pattern was first and last seen. Nothing
about a score is a model's opinion.

Once an hour (`mind.interval_minutes`), off the tick, a pass:

1. re-scores every rule in the book and retires the ones whose interval no longer excludes zero
   in their direction, or that no longer have `min_n` trades -- no model needed;
2. when there are new outcomes, asks one model (`mind.profile`, reasoning high, budget desk
   `mind`, `mind.budget_usd_per_day`) to read a compact packet -- the aggregate table (family x
   strategy x series x price band x leg, computed here, top cells by |P&L| and by n), the book
   with its scores, recent retirements and the desks' post-mortem lessons -- and propose up to
   eight new or revised rules and ids to retire;
3. validates every proposal against the schema, scores it, and admits it only with n >= `min_n`
   and an interval that excludes zero in its direction (`avoid`: upper bound < 0; `prefer`: lower
   bound > 0);
4. keeps at most `max_rules`, ranked by |mean P&L per $| x sqrt(n), in `.data/ltcm/mind.json`
   (atomic write), and publishes a `lab.hypothesis` summarizing the pass and a `lab.result`
   whenever the book changed, with the evidence for every rule added or retired.

The book feeds back three ways: `DeskContext.firm_rules()` puts the rules that apply to a desk
into every session prompt ("# What the firm has learned", after the standings); the lab's packet
carries the family's rules when it writes a strategy; and `rules_for_family(family)` returns the
same block for any other strategy generator (the Foundry's code-candidate prompt)::

    from .mind import rules_for_family
    block = rules_for_family(family)   # "" when the firm has learned nothing that applies
    if block:
        parts.append("## What the firm has learned\\n" + block)

Standard library only. A pass never raises: a failure is one `ops.alert` and the next pass is an
interval away, because the attempt is stamped before any work is done.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .events import canonical, now_iso

OUTCOME_KIND = "desk.outcome"
#: The tape a rule is scored on: the newest outcomes of every desk.
WINDOW = 10_000
RESAMPLES = 1000
#: Fixed, so a score is a function of the tape and nothing else.
BOOTSTRAP_SEED = 20260916
BOOK_VERSION = 1

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "interval_minutes": 60,
    "profile": "k3",
    "reasoning_effort": "high",
    "max_output_tokens": 16384,
    "budget_usd_per_day": "8",
    "min_n": 15,
    "max_rules": 12,
    #: Rules the model may propose in one pass.
    "max_proposals": 8,
    #: Rows of the aggregate table the model reads.
    "cells": 60,
    "resamples": RESAMPLES,
    #: Post-mortem lessons in the packet.
    "lessons": 24,
    #: Rules shown in one desk's session prompt.
    "prompt_rules": 8,
    #: Retired rules remembered in the book (the model reads the newest few).
    "retired_kept": 40,
}

FILTER_KEYS = (
    "series_prefix", "family", "strategy", "result_side", "entry_price", "held_hours", "real_money", "venue",
)
RULE_KEYS = ("id", "statement", "filter", "direction")
DIRECTIONS = ("avoid", "prefer")
SIDES = ("yes", "no")
VENUES = ("kalshi", "coinbase")
DISCRETIONARY = "discretionary"
RULE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
SERIES = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,39}$")
FAMILY = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")  # manifest.DESK_ID
STRATEGY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")  # strategies.NAME
STRATEGY_TAG = re.compile(r"^\s*\[strategy ([a-z][a-z0-9_]{0,39})\]")
MIN_STATEMENT, MAX_STATEMENT = 12, 240
MAX_LIST = 12
#: Entry-price bands of the aggregate table, for contracts priced in dollars between 0 and 1.
PRICE_BANDS = ((0.0, 0.10), (0.10, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 0.90), (0.90, 1.0))
#: The public events stay well inside the site's limits.
MAX_EVENT_BYTES = 3000

#: The book the floor's own FirmMind keeps in this process, for `rules_for_family`.
_ACTIVE_PATH: Path | None = None


class MindError(ValueError):
    """A rule the floor refuses. The message says exactly what was wrong."""


# --------------------------------------------------------------------------- the evidence


@dataclass(frozen=True)
class Outcome:
    """One settled position, as a rule sees it."""

    seq: int
    at: str
    desk_id: str
    family: str
    strategy: str
    ticker: str
    series: str
    venue: str | None
    leg: str | None
    entry_price: float
    quantity: float
    pnl: float
    held_hours: float | None
    real_money: bool | None

    @property
    def notional(self) -> float:
        return self.entry_price * self.quantity

    @property
    def pnl_per_dollar(self) -> float:
        return self.pnl / self.notional


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return float(number)


def strategy_of(rationale: Any) -> str:
    """The strategy a trade belongs to, from the `[strategy <name>]` tag its rationale opens
    with; `discretionary` for a trade a desk placed by hand."""
    match = STRATEGY_TAG.match(str(rationale or ""))
    return match.group(1) if match else DISCRETIONARY


def family_of(desk_id: str, families: Mapping[str, str] | None = None) -> str:
    """The desk's family from the roster; a desk the roster no longer holds takes the family of
    the nearest ancestor it does (`haghani-3-2` is bred from `haghani-3`, from `haghani`), and
    failing that the root of its id."""
    if families:
        if desk_id in families:
            return str(families[desk_id])
        parts = desk_id.split("-")
        for end in range(len(parts) - 1, 0, -1):
            parent = "-".join(parts[:end])
            if parent in families:
                return str(families[parent])
    return desk_id.split("-", 1)[0]


def parse_outcome(event: Any, families: Mapping[str, str] | None = None) -> Outcome | None:
    """An `Outcome` from a `desk.outcome` event, or None when it cannot be scored (no desk, no
    size, no entry price: a per-dollar return needs a notional)."""
    stream = str(getattr(event, "stream", "") or "")
    if not stream.startswith("desk:") or len(stream) <= 5:
        return None
    payload = getattr(event, "payload", None)
    if not isinstance(payload, Mapping):
        return None
    desk_id = stream[5:]
    parts = str(payload.get("instrument") or "").split(":")
    asset_class = parts[0].lower() if parts else ""
    symbol = parts[1] if len(parts) > 1 else ""
    venue = parts[2].lower() if len(parts) > 2 and parts[2] else None
    leg = next((p for p in parts[3:] if p in SIDES), None)
    if leg is None and asset_class == "event":
        leg = "yes"  # an event key without a stated leg is the YES leg (`Instrument.key`)
    ticker = str(payload.get("market_id") or symbol or "").strip().upper()
    entry = _number(payload.get("entry_price"))
    quantity = _number(payload.get("quantity"))
    pnl = _number(payload.get("pnl"))
    if not ticker or entry is None or quantity is None or pnl is None:
        return None
    quantity = abs(quantity)
    if entry <= 0 or quantity <= 0:
        return None
    real = payload.get("real_money")
    return Outcome(
        seq=int(getattr(event, "seq", 0) or 0),
        at=str(getattr(event, "at", "") or ""),
        desk_id=desk_id,
        family=family_of(desk_id, families),
        strategy=strategy_of(payload.get("rationale_excerpt")),
        ticker=ticker,
        series=ticker.split("-", 1)[0],
        venue=venue,
        leg=leg,
        entry_price=entry,
        quantity=quantity,
        pnl=pnl,
        held_hours=_number(payload.get("held_for_hours")),
        real_money=real if isinstance(real, bool) else None,
    )


def matches(rule_filter: Mapping[str, Any], outcome: Outcome) -> bool:
    """Whether a (validated) filter selects this outcome: every key given must hold."""
    prefixes = rule_filter.get("series_prefix")
    if prefixes and not any(outcome.ticker.startswith(p) for p in prefixes):
        return False
    families = rule_filter.get("family")
    if families and outcome.family not in families:
        return False
    strategies = rule_filter.get("strategy")
    if strategies and outcome.strategy not in strategies:
        return False
    side = rule_filter.get("result_side")
    if side is not None and outcome.leg != side:
        return False
    band = rule_filter.get("entry_price")
    if band is not None and not band[0] <= outcome.entry_price <= band[1]:
        return False
    held = rule_filter.get("held_hours")
    if held is not None and (outcome.held_hours is None or not held[0] <= outcome.held_hours <= held[1]):
        return False
    real = rule_filter.get("real_money")
    if real is not None and outcome.real_money is not real:
        return False
    venue = rule_filter.get("venue")
    if venue is not None and outcome.venue != venue:
        return False
    return True


def bootstrap_ci(
    values: Sequence[float], *, resamples: int = RESAMPLES, seed: int = BOOTSTRAP_SEED, level: float = 0.95
) -> tuple[float, float] | None:
    """Percentile bootstrap interval of the mean. Seeded, so the same values give the same
    interval on every pass and every machine."""
    n = len(values)
    if n == 0:
        return None
    if n == 1:
        return (float(values[0]), float(values[0]))
    rng = random.Random(seed)
    count = max(10, int(resamples))
    means = sorted(math.fsum(rng.choices(values, k=n)) / n for _ in range(count))
    tail = (1.0 - level) / 2.0
    low = means[int(math.floor(tail * (count - 1)))]
    high = means[int(math.ceil((1.0 - tail) * (count - 1)))]
    return (low, high)


def evaluate(
    rule: Mapping[str, Any], outcomes: Iterable[Outcome], *, resamples: int = RESAMPLES, seed: int = BOOTSTRAP_SEED
) -> dict[str, Any]:
    """The score of a rule (or a bare filter) on a tape: n, wins, P&L, notional, the mean P&L per
    dollar of entry notional with its bootstrap interval, and first/last seen."""
    rule_filter = rule.get("filter") if isinstance(rule.get("filter"), Mapping) else rule
    hits = [o for o in outcomes if matches(rule_filter, o)]
    n = len(hits)
    score: dict[str, Any] = {
        "n": n,
        "wins": sum(1 for o in hits if o.pnl > 0),
        "pnl_usd": round(math.fsum(o.pnl for o in hits), 4),
        "notional_usd": round(math.fsum(o.notional for o in hits), 4),
        "mean_pnl_per_dollar": None,
        "ci": None,
        "first_seen": min((o.at for o in hits), default=None),
        "last_seen": max((o.at for o in hits), default=None),
        "real_money_n": sum(1 for o in hits if o.real_money),
        "desks": len({o.desk_id for o in hits}),
    }
    if n:
        returns = [o.pnl_per_dollar for o in hits]
        score["mean_pnl_per_dollar"] = round(math.fsum(returns) / n, 6)
        low, high = bootstrap_ci(returns, resamples=resamples, seed=seed)  # type: ignore[misc]
        score["ci"] = [round(low, 6), round(high, 6)]
    return score


def verdict(score: Mapping[str, Any], direction: str, min_n: int) -> tuple[bool, str]:
    """Whether a score earns a rule its place, and why not when it does not."""
    if direction not in DIRECTIONS:
        return False, f"unknown direction {direction!r}"
    n = int(score.get("n") or 0)
    if n < int(min_n):
        return False, f"n={n} is below the {int(min_n)} a rule needs"
    ci = score.get("ci")
    if not ci:
        return False, "no interval"
    low, high = float(ci[0]), float(ci[1])
    if direction == "avoid" and not high < 0:
        return False, f"the interval [{_cents(low)}, {_cents(high)}] cents per $ does not sit below zero"
    if direction == "prefer" and not low > 0:
        return False, f"the interval [{_cents(low)}, {_cents(high)}] cents per $ does not sit above zero"
    return True, "admitted"


def rank_of(score: Mapping[str, Any]) -> float:
    """|mean P&L per $| x sqrt(n): a big effect on few trades and a small one on many compete."""
    mean = score.get("mean_pnl_per_dollar")
    n = int(score.get("n") or 0)
    if mean is None or n <= 0:
        return 0.0
    return abs(float(mean)) * math.sqrt(n)


def _cents(value: Any) -> str:
    return f"{float(value) * 100:.1f}"


def evidence_text(score: Mapping[str, Any]) -> str:
    """`n=47, -6.1 cents per $, CI [-9.0, -3.2]`."""
    n = int(score.get("n") or 0)
    mean = score.get("mean_pnl_per_dollar")
    ci = score.get("ci")
    if mean is None or not ci:
        return f"n={n}"
    return f"n={n}, {_cents(mean)} cents per $, CI [{_cents(ci[0])}, {_cents(ci[1])}]"


# --------------------------------------------------------------------------- the schema


def _string_list(key: str, raw: Any, pattern: re.Pattern[str], *, upper: bool = False) -> list[str]:
    if not isinstance(raw, list) or not raw or len(raw) > MAX_LIST:
        raise MindError(f"filter.{key} must list 1 to {MAX_LIST} values")
    out: set[str] = set()
    for value in raw:
        if not isinstance(value, str):
            raise MindError(f"filter.{key} values must be strings")
        text = value.strip().upper() if upper else value.strip()
        if not pattern.match(text):
            raise MindError(f"filter.{key} value {value[:40]!r} is malformed")
        out.add(text)
    return sorted(out)


def _range(key: str, raw: Any, ceiling: float) -> list[float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise MindError(f"filter.{key} must be [lo, hi]")
    low, high = _number(raw[0]), _number(raw[1])
    if low is None or high is None:
        raise MindError(f"filter.{key} bounds must be numbers")
    if low < 0 or high > ceiling or low > high:
        raise MindError(f"filter.{key} must satisfy 0 <= lo <= hi <= {ceiling:g}")
    return [round(low, 6), round(high, 6)]


def validate_filter(raw: Any) -> dict[str, Any]:
    """The filter, normalized (null keys dropped, lists sorted and deduplicated), or `MindError`."""
    if not isinstance(raw, Mapping):
        raise MindError("filter must be an object")
    unknown = sorted(str(k) for k in raw if k not in FILTER_KEYS)
    if unknown:
        raise MindError(f"unknown filter keys: {', '.join(unknown)}")
    out: dict[str, Any] = {}
    if raw.get("series_prefix") is not None:
        out["series_prefix"] = _string_list("series_prefix", raw["series_prefix"], SERIES, upper=True)
    if raw.get("family") is not None:
        out["family"] = _string_list("family", raw["family"], FAMILY)
    if raw.get("strategy") is not None:
        out["strategy"] = _string_list("strategy", raw["strategy"], STRATEGY)
    if raw.get("result_side") is not None:
        if raw["result_side"] not in SIDES:
            raise MindError("filter.result_side must be \"yes\", \"no\" or null")
        out["result_side"] = raw["result_side"]
    if raw.get("entry_price") is not None:
        out["entry_price"] = _range("entry_price", raw["entry_price"], 10_000_000.0)
    if raw.get("held_hours") is not None:
        out["held_hours"] = _range("held_hours", raw["held_hours"], 24.0 * 366)
    if raw.get("real_money") is not None:
        if not isinstance(raw["real_money"], bool):
            raise MindError("filter.real_money must be true, false or null")
        out["real_money"] = raw["real_money"]
    if raw.get("venue") is not None:
        if raw["venue"] not in VENUES:
            raise MindError(f"filter.venue must be one of {', '.join(VENUES)} or null")
        out["venue"] = raw["venue"]
    if not out:
        raise MindError("a filter must constrain at least one field")
    return out


def validate_rule(raw: Any) -> dict[str, Any]:
    """A rule in the schema, normalized, or `MindError` saying exactly what was wrong."""
    if not isinstance(raw, Mapping):
        raise MindError("a rule must be an object")
    unknown = sorted(str(k) for k in raw if k not in RULE_KEYS)
    if unknown:
        raise MindError(f"unknown rule keys: {', '.join(unknown)}")
    rule_id = raw.get("id")
    if not isinstance(rule_id, str) or not RULE_ID.match(rule_id):
        raise MindError("id must be a lowercase slug of 3 to 64 letters, digits and hyphens")
    statement = raw.get("statement")
    if not isinstance(statement, str):
        raise MindError("statement must be a sentence")
    statement = " ".join(statement.split())
    if not MIN_STATEMENT <= len(statement) <= MAX_STATEMENT:
        raise MindError(f"statement must be {MIN_STATEMENT} to {MAX_STATEMENT} characters")
    if "<" in statement:
        raise MindError("statement may not contain markup")
    direction = raw.get("direction")
    if direction not in DIRECTIONS:
        raise MindError("direction must be \"avoid\" or \"prefer\"")
    return {"id": rule_id, "statement": statement, "filter": validate_filter(raw.get("filter")), "direction": direction}


def parse_reply(body: Any) -> tuple[list[Any], list[str]]:
    """The rules and retirements in a model reply: the first JSON object in the text. Prose
    around it and a fenced block are tolerated; anything else is nothing."""
    text = str(body or "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return [], []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return [], []
    if not isinstance(data, dict):
        return [], []
    rules = data.get("rules") if isinstance(data.get("rules"), list) else []
    retire = [r for r in (data.get("retire") or []) if isinstance(r, str)] if isinstance(data.get("retire"), list) else []
    return list(rules), retire


# --------------------------------------------------------------------------- the table


def band_of(outcome: Outcome) -> str:
    """The entry-price band of the aggregate table; `spot` for a coin priced in dollars."""
    price = outcome.entry_price
    if outcome.venue == "coinbase" or price > 1.0:
        return "spot"
    for low, high in PRICE_BANDS:
        if low <= price < high:
            return f"{low:.2f}-{high:.2f}"
    return f"{PRICE_BANDS[-1][0]:.2f}-{PRICE_BANDS[-1][1]:.2f}"


def aggregate(outcomes: Sequence[Outcome], limit: int = 60) -> list[dict[str, Any]]:
    """Outcome statistics by family x strategy x series x price band x leg, the cells with the
    largest |P&L| and the largest n first, alternately, up to `limit`. Computed in code: the
    model reads numbers the floor wrote, never numbers it guessed."""
    groups: dict[tuple[str, str, str, str, str], list[Outcome]] = {}
    for outcome in outcomes:
        key = (outcome.family, outcome.strategy, outcome.series, band_of(outcome), outcome.leg or "-")
        groups.setdefault(key, []).append(outcome)
    cells: list[dict[str, Any]] = []
    for key, rows in groups.items():
        n = len(rows)
        returns = [o.pnl_per_dollar for o in rows]
        mean = math.fsum(returns) / n
        se = None
        if n > 1:
            variance = math.fsum((r - mean) ** 2 for r in returns) / (n - 1)
            se = math.sqrt(variance / n)
        cells.append(
            {
                "family": key[0], "strategy": key[1], "series": key[2], "band": key[3], "leg": key[4],
                "n": n, "wins": sum(1 for o in rows if o.pnl > 0),
                "pnl_usd": round(math.fsum(o.pnl for o in rows), 2),
                "mean_pnl_per_dollar": round(mean, 6), "se": None if se is None else round(se, 6),
                "real_money_n": sum(1 for o in rows if o.real_money),
            }
        )
    by_pnl = sorted(cells, key=lambda c: (-abs(c["pnl_usd"]), -c["n"], _cell_key(c)))
    by_n = sorted(cells, key=lambda c: (-c["n"], -abs(c["pnl_usd"]), _cell_key(c)))
    chosen: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for pair in zip(by_pnl, by_n):
        for cell in pair:
            if len(chosen) >= max(0, int(limit)):
                return chosen
            key = _cell_key(cell)
            if key not in seen:
                seen.add(key)
                chosen.append(cell)
    return chosen


def _cell_key(cell: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(cell[k]) for k in ("family", "strategy", "series", "band", "leg"))


def table_text(cells: Iterable[Mapping[str, Any]]) -> str:
    lines = ["family | strategy | series | entry band | leg | n | wins | pnl_usd | cents per $ | se | real-money n"]
    for c in cells:
        se = "-" if c.get("se") is None else _cents(c["se"])
        lines.append(
            f"{c['family']} | {c['strategy']} | {c['series']} | {c['band']} | {c['leg']} | {c['n']} | {c['wins']} | "
            f"{c['pnl_usd']:.2f} | {_cents(c['mean_pnl_per_dollar'])} | {se} | {c['real_money_n']}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- the prompt


def render_rules(rules: Iterable[Mapping[str, Any]]) -> str:
    """The session prompt's block: every rule with its evidence, and how to use them."""
    lines = [
        "Rules the firm measured across every desk's settled trades, live and shadow. Each was admitted only when the "
        "95% bootstrap interval of its P&L per dollar of entry excluded zero, and each is re-scored every hour and "
        "retired when it stops holding. Apply them to your own orders and strategies unless your own settled record "
        "says otherwise, and say so in your memo when it does."
    ]
    count = 0
    for rule in rules:
        if not isinstance(rule, Mapping) or not rule.get("statement"):
            continue
        evidence = rule.get("evidence") or evidence_text(rule.get("score") or {})
        lines.append(f"- {str(rule.get('direction') or '').upper()}: {rule['statement']} ({evidence})")
        count += 1
    return "\n".join(lines) if count else ""


def applies(rule: Mapping[str, Any], family: str | None = None, venues: Iterable[str] | None = None) -> bool:
    """Whether a rule speaks to a desk of this family trading these venues. A rule with no family
    or venue in its filter speaks to every desk."""
    rule_filter = rule.get("filter") or {}
    families = rule_filter.get("family")
    if family is not None and families and family not in families:
        return False
    venue = rule_filter.get("venue")
    if venues is not None and venue is not None and venue not in set(venues):
        return False
    return True


def _prompt_row(rule: Mapping[str, Any]) -> dict[str, Any]:
    score = rule.get("score") or {}
    return {
        "id": rule.get("id"),
        "statement": rule.get("statement"),
        "direction": rule.get("direction"),
        "filter": rule.get("filter"),
        "evidence": evidence_text(score),
        "n": score.get("n"),
        "mean_pnl_per_dollar": score.get("mean_pnl_per_dollar"),
        "ci": score.get("ci"),
    }


def read_book(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def rules_for_family(family: str, *, path: str | Path | None = None, limit: int = 8) -> str:
    """The rules that apply to a family, rendered for a strategy generator's prompt (the Foundry's
    code-candidate prompt, the lab's packet): rules scoped to the family and rules scoped to no
    family, strongest first, each with its evidence. `path` defaults to the book the floor's own
    FirmMind keeps in this process. Returns "" when the book is empty, missing or unreadable, so
    a caller appends the block only when it says something."""
    target = Path(path) if path is not None else _ACTIVE_PATH
    if target is None:
        return ""
    try:
        rules = [r for r in read_book(target).get("rules") or [] if isinstance(r, Mapping)]
        chosen = [_prompt_row(r) for r in rules if applies(r, family=family)][: max(0, int(limit))]
        return render_rules(chosen)
    except Exception:
        return ""


# --------------------------------------------------------------------------- the mind


def _parse_at(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").replace("<", "‹").split())[:limit]


class FirmMind:
    """Score, admit, retire and publish the floor's rules. Reads the log; writes the book file
    and `lab.hypothesis` / `lab.result`; never touches a manifest, an order or a ledger."""

    def __init__(
        self,
        log: Any,
        *,
        path: str | Path,
        provider: Any = None,
        clock: Callable[[], float] = time.time,
        config: Mapping[str, Any] | None = None,
        families: Callable[[], Mapping[str, str]] | None = None,
        lessons: Callable[[], Iterable[str]] | None = None,
        alert: Callable[[str, str], None] | None = None,
        register: bool = True,
    ):
        global _ACTIVE_PATH
        self.log = log
        self.path = Path(path)
        self.provider = provider
        self.clock = clock
        self.config = {**DEFAULT_CONFIG, **dict(config or {})}
        self.families = families
        self.lessons = lessons
        self.alert_hook = alert
        self._lock = threading.RLock()
        self._book: dict[str, Any] | None = None
        self._stamp: tuple[int, int] | None = None
        if register:
            _ACTIVE_PATH = self.path

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    def now(self) -> str:
        return now_iso(self.clock)

    def alert(self, text: str) -> None:
        try:
            if self.alert_hook is not None:
                self.alert_hook("warning", text)
        except Exception:
            pass

    # ------------------------------------------------------------------ the book
    def book(self) -> dict[str, Any]:
        """The rule book as it stands, re-read when another process (the manual pass) wrote it."""
        with self._lock:
            try:
                stat = self.path.stat()
                stamp = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                stamp = None
            if self._book is None or (stamp is not None and stamp != self._stamp):
                data = read_book(self.path)
                self._book = {"version": BOOK_VERSION, "rules": [], "retired": [], **data}
                self._stamp = stamp
            return json.loads(json.dumps(self._book))

    def _save(self, book: Mapping[str, Any], persist: bool) -> None:
        with self._lock:
            self._book = json.loads(json.dumps(dict(book)))
            if not persist:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(f"{self.path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
            tmp.write_text(json.dumps(self._book, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp.replace(self.path)
            try:
                stat = self.path.stat()
                self._stamp = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                self._stamp = None

    def rules(self) -> list[dict[str, Any]]:
        return [r for r in self.book().get("rules") or [] if isinstance(r, dict)]

    def rules_for(
        self, family: str | None = None, venues: Iterable[str] | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """The active rules that apply to a desk, strongest first, ready for `render_rules`."""
        cap = int(self.config["prompt_rules"] if limit is None else limit)
        venue_list = list(venues) if venues is not None else None
        rows = [_prompt_row(r) for r in self.rules() if applies(r, family=family, venues=venue_list)]
        return rows[: max(0, cap)]

    def block_for(self, family: str) -> str:
        """`rules_for_family` for this mind's own book."""
        try:
            return render_rules(self.rules_for(family=family))
        except Exception:
            return ""

    # ------------------------------------------------------------------ the evidence
    def outcomes(self) -> tuple[list[Outcome], int]:
        """Every scoreable outcome in the newest `WINDOW` of the log, oldest first, and the
        sequence number of the newest outcome event (the evidence fingerprint)."""
        events = self.log.read(kind=OUTCOME_KIND, limit=WINDOW, newest=True)
        try:
            families = dict(self.families()) if self.families is not None else {}
        except Exception:
            families = {}
        rows = [o for o in (parse_outcome(e, families) for e in events) if o is not None]
        latest = int(getattr(events[-1], "seq", 0) or 0) if events else 0
        return rows, latest

    def score(self, rule: Mapping[str, Any], outcomes: Sequence[Outcome]) -> dict[str, Any]:
        return evaluate(rule, outcomes, resamples=int(self.config["resamples"]))

    def recent_lessons(self) -> list[str]:
        """The desks' newest post-mortem lessons, and any lessons the memory store holds."""
        limit = max(0, int(self.config["lessons"]))
        out: list[str] = []

        def add(text: str) -> None:
            text = _clean(text, 240)
            if len(text) > 8 and text not in out and len(out) < limit:
                out.append(text)

        try:
            for event in reversed(self.log.read(kind="desk.postmortem", limit=60, newest=True)):
                desk = str(event.stream).split(":", 1)[-1]
                for lesson in event.payload.get("lessons") or []:
                    if isinstance(lesson, str):
                        add(f"{desk}: {lesson}")
        except Exception:
            pass
        if self.lessons is not None:
            try:
                for lesson in self.lessons():
                    add(str(lesson))
            except Exception:
                pass
        return out

    # ------------------------------------------------------------------ the schedule
    def due(self, at: str | None = None) -> bool:
        """Whether a pass is due: `interval_minutes` since the last attempt. Asked on the tick, so
        it answers False rather than raise."""
        try:
            if not self.enabled:
                return False
            last = self.book().get("last_pass_at")
            if not last:
                return True
            elapsed = (_parse_at(at or self.now()) - _parse_at(last)).total_seconds()
            return elapsed >= float(self.config["interval_minutes"]) * 60 or elapsed < 0
        except Exception:
            return False

    # ------------------------------------------------------------------ the pass
    def run(
        self, at: str | None = None, *, ask: bool = True, persist: bool = True, publish: bool = True, force: bool = False
    ) -> dict[str, Any]:
        """One pass. Never raises: a failure is an alert and a summary that says so."""
        at = at or self.now()
        try:
            return self._run(at, ask=ask, persist=persist, publish=publish, force=force)
        except Exception as exc:
            self.alert(f"firm mind pass failed: {type(exc).__name__}: {str(exc)[:200]}")
            return {"at": at, "failed": f"{type(exc).__name__}"}

    def _run(self, at: str, *, ask: bool, persist: bool, publish: bool, force: bool) -> dict[str, Any]:
        min_n = int(self.config["min_n"])
        book = self.book()
        # The attempt is stamped before any work, so a pass that fails waits its interval instead
        # of retrying (and paying) every tick.
        book["last_pass_at"] = at
        self._save(book, persist)

        outcomes, latest = self.outcomes()
        fingerprint = {"seq": latest, "n": len(outcomes), "min_n": min_n}
        summary: dict[str, Any] = {
            "at": at, "outcomes": len(outcomes), "rules": len(book.get("rules") or []),
            "added": [], "revised": [], "retired": [], "proposals": [], "asked": False,
        }
        if not force and book.get("evidence") == fingerprint:
            summary["skipped"] = "no new outcomes since the last pass"
            return summary

        before = {r["id"]: r for r in book.get("rules") or [] if isinstance(r, dict) and r.get("id")}
        active: dict[str, dict[str, Any]] = {}
        retired: list[dict[str, Any]] = []
        # 1. Re-score the book. A rule that stopped holding goes, without asking anyone.
        for rule_id, rule in before.items():
            try:  # a book edited by hand is held to the same schema as the model
                rule = {**rule, **validate_rule({k: rule.get(k) for k in RULE_KEYS})}
            except MindError as exc:
                retired.append(self._retirement(rule, {}, f"invalid in the book: {exc}", at))
                continue
            score = self.score(rule, outcomes)
            ok, reason = verdict(score, str(rule.get("direction")), min_n)
            if ok:
                active[rule_id] = {**rule, "score": score}
            else:
                retired.append(self._retirement(rule, score, f"re-scored: {reason}", at))

        # 2. Ask the scientist, when there is evidence it has not read.
        if ask and self.provider is not None and len(outcomes) >= min_n:
            reply = self._ask(at, outcomes, list(active.values()), retired + list(book.get("retired") or []), persist=persist)
            summary["asked"] = reply is not None
            if reply is not None:
                proposals, retire_ids = reply
                for rule_id in retire_ids[: int(self.config["max_rules"])]:
                    rule = active.pop(rule_id, None)
                    if rule is not None:
                        retired.append(self._retirement(rule, rule["score"], "retired by the scientist", at))
                for raw in proposals[: int(self.config["max_proposals"])]:
                    summary["proposals"].append(self._consider(raw, outcomes, active, before, at, min_n))

        # 3. Rank and cap.
        ordered = sorted(active.values(), key=lambda r: (-rank_of(r["score"]), r["id"]))
        cap = max(0, int(self.config["max_rules"]))
        for rule in ordered[cap:]:
            retired.append(self._retirement(rule, rule["score"], f"outranked: the book keeps {cap} rules", at))
        ordered = ordered[:cap]
        kept = {r["id"] for r in ordered}
        retired = [r for r in retired if r["id"] not in kept]  # a revision is not a retirement

        added = [r for r in ordered if r["id"] not in before]
        revised = [
            r for r in ordered
            if r["id"] in before and (r.get("filter"), r.get("direction"), r.get("statement"))
            != (before[r["id"]].get("filter"), before[r["id"]].get("direction"), before[r["id"]].get("statement"))
        ]
        for rule in ordered:
            rule["evidence"] = evidence_text(rule["score"])
            rule["rank"] = round(rank_of(rule["score"]), 6)

        book = self.book()  # the spend may have moved while the model thought
        book.update(
            {
                "version": BOOK_VERSION,
                "rules": ordered,
                "retired": (retired + list(book.get("retired") or []))[: int(self.config["retired_kept"])],
                "last_pass_at": at,
                "evidence": fingerprint,
                "passes": int(book.get("passes") or 0) + 1,
            }
        )
        summary.update(
            {
                "rules": len(ordered),
                "added": [r["id"] for r in added],
                "revised": [r["id"] for r in revised],
                "retired": [r["id"] for r in retired],
            }
        )
        book["last_summary"] = {k: summary[k] for k in ("at", "outcomes", "rules", "added", "revised", "retired", "asked")}
        self._save(book, persist)
        if publish and (outcomes or added or revised or retired):
            self._publish(at, summary, outcomes, added, revised, retired)
        return summary

    def _retirement(self, rule: Mapping[str, Any], score: Mapping[str, Any], reason: str, at: str) -> dict[str, Any]:
        return {
            "id": rule.get("id"),
            "statement": rule.get("statement"),
            "direction": rule.get("direction"),
            "filter": rule.get("filter"),
            "score": dict(score),
            "evidence": evidence_text(score),
            "reason": reason[:240],
            "retired_at": at,
        }

    def _consider(
        self,
        raw: Any,
        outcomes: Sequence[Outcome],
        active: dict[str, dict[str, Any]],
        before: Mapping[str, Mapping[str, Any]],
        at: str,
        min_n: int,
    ) -> dict[str, Any]:
        """Validate, score and admit (or refuse) one proposed rule, in place in `active`."""
        try:
            rule = validate_rule(raw)
        except MindError as exc:
            rule_id = raw.get("id") if isinstance(raw, Mapping) and isinstance(raw.get("id"), str) else None
            return {"id": _clean(rule_id, 64) or None, "status": "invalid", "reason": str(exc)}
        for other in active.values():
            if other["id"] != rule["id"] and other["filter"] == rule["filter"] and other["direction"] == rule["direction"]:
                return {"id": rule["id"], "status": "rejected", "reason": f"duplicates {other['id']}"}
        score = self.score(rule, outcomes)
        ok, reason = verdict(score, rule["direction"], min_n)
        row = {"id": rule["id"], "status": "admitted" if ok else "rejected", "reason": reason, "evidence": evidence_text(score)}
        if ok:
            previous = active.get(rule["id"]) or before.get(rule["id"]) or {}
            active[rule["id"]] = {
                **rule,
                "score": score,
                "admitted_at": previous.get("admitted_at") or at,
                "revised_at": at,
            }
        return row

    # ------------------------------------------------------------------ the scientist
    def _spent_today(self, book: Mapping[str, Any], day: str) -> Decimal:
        spend = book.get("spend") or {}
        if spend.get("day") != day:
            return Decimal(0)
        try:
            return Decimal(str(spend.get("usd") or "0"))
        except InvalidOperation:
            return Decimal(0)

    def _estimate(self, chars: int) -> Decimal:
        profile = str(self.config["profile"])
        max_output = int(self.config["max_output_tokens"])
        estimate = getattr(self.provider, "estimate", None)
        try:
            if callable(estimate):
                return Decimal(str(estimate(profile, chars, max_output)))
        except Exception:
            pass
        try:
            from .provider import reservation_usd

            return reservation_usd(profile, chars, max_output)
        except Exception:
            return Decimal("0.25")

    def _ask(
        self,
        at: str,
        outcomes: Sequence[Outcome],
        rules: Sequence[Mapping[str, Any]],
        retired: Sequence[Mapping[str, Any]],
        *,
        persist: bool = True,
    ) -> tuple[list[Any], list[str]] | None:
        packet = self.packet(at, outcomes, rules, retired)
        instructions = self.instructions()
        day = at[:10]
        budget = Decimal(str(self.config["budget_usd_per_day"]))
        spent = self._spent_today(self.book(), day)
        estimate = self._estimate(len(instructions) + len(packet))
        if spent + estimate > budget:
            self.alert(f"firm mind skipped its model call: ${spent} of ${budget} spent today")
            return None
        try:
            response = self.provider.respond(
                self.config["profile"],
                [{"role": "system", "content": instructions}, {"role": "user", "content": packet}],
                tools=None,
                desk_id="mind",
                session_id=f"mind-{day}",
                request_key=f"mind:{at[:16]}",
                reasoning_effort=self.config["reasoning_effort"],
                max_output_tokens=int(self.config["max_output_tokens"]),
                desk_cap_usd_per_day=self.config["budget_usd_per_day"],
            )
        except Exception as exc:
            self.alert(f"firm mind model call failed: {type(exc).__name__}: {str(exc)[:160]}")
            return None
        cost = getattr(response, "cost_usd", None)
        try:
            cost = Decimal(str(cost)) if cost is not None else estimate
        except InvalidOperation:
            cost = estimate
        current = self.book()
        current["spend"] = {"day": day, "usd": format(self._spent_today(current, day) + cost, "f")}
        current["last_asked_at"] = at
        self._save(current, persist)
        return parse_reply(getattr(response, "output_text", "") or "")

    def instructions(self) -> str:
        cfg = self.config
        return (
            "You are the Firm Mind of a public, fully automated trading floor: its scientist. Every desk's settled "
            "trades are scored in code; your job is to turn them into a small book of machine-checkable rules that "
            "every desk session and every strategy generator on the floor reads. You get an aggregate table computed "
            "in code (family x strategy x series x entry-price band x leg), the current rule book with its scores, "
            "rules recently retired and why, and the desks' own post-mortem lessons (hypotheses, not evidence).\n"
            "Reply with JSON only, in this shape: {\"rules\": [...], \"retire\": [\"rule-id\", ...]}. "
            f"At most {cfg['max_proposals']} rules, each new or a revision of an existing id:\n"
            "{\"id\": \"lowercase-slug\", \"statement\": \"one sentence a desk can act on\", \"filter\": {...}, "
            "\"direction\": \"avoid\" or \"prefer\"}\n"
            "Filter keys, all optional but at least one; a trade must satisfy every key given:\n"
            "- series_prefix: list of ticker prefixes; [\"KXHIGH\"] matches KXHIGHNY-... and KXHIGHCHI-...; a Coinbase "
            "product matches by its id, e.g. [\"BTC-USD\"]\n"
            "- family: list of desk families from the table\n"
            f"- strategy: list of strategy names from the table; \"{DISCRETIONARY}\" means trades a desk placed by hand\n"
            "- result_side: \"yes\" or \"no\", the leg the desk held\n"
            "- entry_price: [lo, hi] inclusive, the entry price (Kalshi contracts are 0 to 1 dollars)\n"
            "- held_hours: [lo, hi] inclusive\n"
            "- real_money: true for real-money trades only, false for shadow books only\n"
            "- venue: \"kalshi\" or \"coinbase\"\n"
            f"How rules are judged, in code, after you answer: the filter runs over the newest {WINDOW} settled outcomes "
            "of every desk, and the score is the mean P&L per dollar of entry notional per trade with a seeded "
            f"bootstrap 95% interval. A rule is admitted only with at least {cfg['min_n']} matching trades and an "
            "interval that excludes zero in its direction: avoid needs the upper bound below zero, prefer needs the "
            "lower bound above zero. Every rule is re-scored every pass and retired automatically when it stops "
            f"holding; the book keeps at most {cfg['max_rules']}, ranked by |mean| x sqrt(n).\n"
            "Write rules narrow enough to act on and broad enough to carry the trades: a cell with a large n and a mean "
            "several standard errors from zero is a candidate, a single outlier trade is not, and neighbouring cells "
            "that agree can be one rule. The statement says what to do and where, in plain words a desk can apply "
            "without reading the filter, and claims nothing the filter does not test. Revise a rule by reusing its id; "
            "retire one only when the table shows it is wrong or superseded. Reply {\"rules\": [], \"retire\": []} when "
            "the evidence supports nothing new."
        )

    def packet(
        self,
        at: str,
        outcomes: Sequence[Outcome],
        rules: Sequence[Mapping[str, Any]],
        retired: Sequence[Mapping[str, Any]],
    ) -> str:
        """Everything the scientist reads: numbers the floor wrote, and the desks' lessons."""
        n = len(outcomes)
        parts = [f"# The floor's settled outcomes, now {at} UTC"]
        if n:
            returns = [o.pnl_per_dollar for o in outcomes]
            parts.append(
                f"{n} outcomes from {len({o.desk_id for o in outcomes})} desks, {min(o.at for o in outcomes)[:16]} to "
                f"{max(o.at for o in outcomes)[:16]}; {sum(1 for o in outcomes if o.real_money)} with real money; net "
                f"{math.fsum(o.pnl for o in outcomes):.2f} USD, mean {_cents(math.fsum(returns) / n)} cents per $ of entry."
            )
            families: dict[str, list[Outcome]] = {}
            for o in outcomes:
                families.setdefault(o.family, []).append(o)
            parts.append(
                "## By family\n"
                + "\n".join(
                    f"- {family}: n={len(rows)}, pnl {math.fsum(o.pnl for o in rows):.2f} USD, "
                    f"{_cents(math.fsum(o.pnl_per_dollar for o in rows) / len(rows))} cents per $"
                    for family, rows in sorted(families.items())
                )
            )
            cells = aggregate(outcomes, int(self.config["cells"]))
            parts.append(f"## Cells (top {len(cells)} by |pnl| and by n; se is the standard error in cents)\n" + table_text(cells))
        else:
            parts.append("(no settled outcomes yet)")
        if rules:
            lines = [
                f"- {r['id']} [{r['direction']}] {r['statement']} | filter {canonical(r['filter'])} | {evidence_text(r['score'])}"
                for r in sorted(rules, key=lambda r: -rank_of(r["score"]))
            ]
            parts.append("## The rule book, re-scored now\n" + "\n".join(lines))
        else:
            parts.append("## The rule book, re-scored now\n(empty)")
        if retired:
            lines = [
                f"- {r.get('id')} [{r.get('direction')}] {r.get('statement')} | filter {canonical(r.get('filter') or {})} | "
                f"{r.get('evidence') or ''} | {r.get('reason')}"
                for r in list(retired)[:8]
            ]
            parts.append("## Retired recently\n" + "\n".join(lines))
        lessons = self.recent_lessons()
        if lessons:
            parts.append("## Post-mortem lessons, newest first (hypotheses to test, not evidence)\n" + "\n".join(f"- {x}" for x in lessons))
        return "\n\n".join(parts)

    # ------------------------------------------------------------------ the record
    def _publish(
        self,
        at: str,
        summary: Mapping[str, Any],
        outcomes: Sequence[Outcome],
        added: Sequence[Mapping[str, Any]],
        revised: Sequence[Mapping[str, Any]],
        retired: Sequence[Mapping[str, Any]],
    ) -> None:
        hypothesis_id = "mind-" + at[:16].replace(":", "")
        proposals = list(summary.get("proposals") or [])
        admitted = sum(1 for p in proposals if p.get("status") == "admitted")
        text = (
            f"The Firm Mind read {len(outcomes)} settled outcomes from {len({o.desk_id for o in outcomes})} desks"
            + (f" and scored {len(proposals)} proposed rules, {admitted} admitted" if summary.get("asked") else "")
            + f"; the book holds {summary.get('rules')} rules ({len(added)} added, {len(revised)} revised, "
            f"{len(retired)} retired)."
        )
        plan = (
            f"Each rule filters the newest {WINDOW} desk.outcome events of every desk and is scored on mean P&L per "
            f"dollar of entry with a seeded bootstrap 95% interval; it holds its place only with n >= "
            f"{self.config['min_n']} and an interval that excludes zero in its direction, re-checked every "
            f"{self.config['interval_minutes']} minutes."
        )
        self._append(
            f"mind:pass:{at}",
            "lab.hypothesis",
            {
                "hypothesis_id": hypothesis_id,
                "text": _clean(text, 600),
                "test_plan": _clean(plan, 600),
                "source": "mind",
                "outcomes": str(len(outcomes)),
                "rules": str(summary.get("rules")),
                "proposed": str(len(proposals)),
                "admitted": str(admitted),
            },
            at,
        )
        if not (added or revised or retired):
            return

        def entry(rule: Mapping[str, Any], reason: str | None = None) -> dict[str, Any]:
            score = rule.get("score") or {}
            ci = score.get("ci") or [None, None]
            row = {
                "id": str(rule.get("id")),
                "direction": str(rule.get("direction")),
                "statement": _clean(rule.get("statement"), 200),
                "n": str(score.get("n") or 0),
                "cents_per_dollar": "" if score.get("mean_pnl_per_dollar") is None else _cents(score["mean_pnl_per_dollar"]),
                "ci_cents": ["" if v is None else _cents(v) for v in ci],
            }
            if reason:
                row["reason"] = _clean(reason, 160)
            return row

        metrics: dict[str, Any] = {
            "added": [entry(r) for r in added],
            "revised": [entry(r) for r in revised],
            "retired": [entry(r, r.get("reason")) for r in retired],
            "rules": str(summary.get("rules")),
        }
        verdict_text = (
            "Firm Mind: "
            + "; ".join(
                part
                for part in (
                    ("added " + ", ".join(f"{r['id']} ({evidence_text(r.get('score') or {})})" for r in added)) if added else "",
                    ("revised " + ", ".join(str(r["id"]) for r in revised)) if revised else "",
                    ("retired " + ", ".join(str(r["id"]) for r in retired)) if retired else "",
                )
                if part
            )
            + "."
        )
        payload = {"hypothesis_id": hypothesis_id, "metrics": metrics, "verdict": _clean(verdict_text, 700)}

        def size() -> int:
            return len(canonical(payload).encode("utf-8"))

        # Shed detail before the record can outgrow the site's appetite: statements of retired rules
        # first, then the verdict's detail, then whole entries from the end, and say so.
        for group in ("retired", "revised", "added"):
            if size() <= MAX_EVENT_BYTES:
                break
            for row in metrics[group]:
                row.pop("statement", None)
        if size() > MAX_EVENT_BYTES:
            payload["verdict"] = _clean(
                f"Firm Mind: {len(added)} added, {len(revised)} revised, {len(retired)} retired; the book holds {summary.get('rules')} rules.",
                300,
            )
        while size() > MAX_EVENT_BYTES and any(metrics[g] for g in ("retired", "revised", "added")):
            group = next(g for g in ("retired", "revised", "added") if metrics[g])
            metrics[group].pop()
            metrics["truncated"] = "true"
        self._append(f"mind:result:{at}", "lab.result", payload, at)

    def _append(self, event_id: str, kind: str, payload: dict[str, Any], at: str) -> None:
        append = getattr(self.log, "append", None)
        if append is None:
            return
        try:
            append("lab", kind, payload, id=event_id, at=at)
        except Exception as exc:
            self.alert(f"firm mind {kind} not written: {type(exc).__name__}")


# --------------------------------------------------------------------------- the floor


def build(service: Any) -> FirmMind | None:
    """The floor's FirmMind, wired to the service's log, provider, roster and memory; None when
    config `mind.enabled` is false."""
    config = {**DEFAULT_CONFIG, **dict(service.config.get("mind") or {})}
    if not config.get("enabled", True):
        return None

    def families() -> dict[str, str]:
        return {desk_id: m.family for desk_id, m in dict(service.manifests).items()}

    def memory_lessons() -> list[str]:
        read = getattr(getattr(service, "memory", None), "read", None)
        if not callable(read):
            return []
        rows = read("lesson", 60)
        return [
            f"{row.get('desk_id')}: {row.get('text')}"
            for row in rows or []
            if isinstance(row, Mapping) and row.get("kind") == "lesson" and row.get("text")
        ]

    return FirmMind(
        service.log,
        path=service.capital_dir / "mind.json",
        provider=service.provider,
        clock=service.clock,
        config=config,
        families=families,
        lessons=memory_lessons,
        alert=service.alert,
    )


__all__ = [
    "BOOTSTRAP_SEED",
    "DEFAULT_CONFIG",
    "FirmMind",
    "MindError",
    "Outcome",
    "aggregate",
    "applies",
    "bootstrap_ci",
    "build",
    "evaluate",
    "evidence_text",
    "matches",
    "parse_outcome",
    "parse_reply",
    "rank_of",
    "render_rules",
    "rules_for_family",
    "strategy_of",
    "validate_filter",
    "validate_rule",
    "verdict",
]
