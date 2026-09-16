"""The Firm Mind: what one desk learns, every desk inherits.

Every desk writes a `desk.outcome` when a position closes: a Kalshi settlement, or a sell of a spot
position or of an event leg before its market settles, with the entry, the exit, the size, the
P&L, the fees its opening fills paid, how long it was held, the sentence that opened it and whether
real money was at stake. Until now each desk read only its own. The Firm Mind reads all of them and
keeps a small book of *rules*: machine-checkable statements about which trades the floor should
avoid or prefer, each one scored in code.

A rule is JSON::

    {"id": "weather-no-legs-above-90c", "statement": "one sentence for the public record",
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

**The score.** `evaluate` selects the matching outcomes and groups them into *positions that are
one draw of chance*: every desk, leg and strike of one Kalshi event (fifteen bred desks holding one
settled market are one observation, not fifteen), or the partial sells of one spot position. n
counts those groups. Each group's return is its P&L net of entry fees per dollar of entry notional;
the score is their mean with a seeded bootstrap interval (a normal approximation above
`bootstrap_max_n` groups), and, when every group is one settled contract, an exact binomial test of
the groups that won against the break-even count (the sum of what each paid per contract, fees
included). `verdict` refuses an interval with no width and a rule without `min_each_way` winning
and losing groups: fifteen fairly priced 5-cent longshots all lose 46% of the time, and a bootstrap
of fifteen identical losses is [-1, -1]. Nothing about a score is a model's opinion.

**Out of sample.** A model that reads a table and proposes its most extreme cells will find rules
in pure noise, and scoring them on the trades it read admits them. So once an hour
(`mind.interval_minutes`), off the tick, a pass:

1. splits the newest 10,000 outcomes by log order: the older `1 - holdout_fraction` is what the
   model reads, the newest `holdout_fraction` (less any position the older part already holds) it
   never sees;
2. re-scores every rule in the book on the outcomes newer than the tape its proposer read, and
   retires it when that interval no longer excludes zero in its direction, or when `min_n` groups
   have arrived since its admission and their mean sits on the wrong side of zero -- no model
   needed;
3. when there are new outcomes and the held-out part could admit a rule, asks one model
   (`mind.profile`, reasoning high, budget desk `mind`, `mind.budget_usd_per_day` held by the mind
   itself) to read a compact packet built from the older part only -- the aggregate table (family x
   strategy x series x price band x leg), the book scored on that part, recent retirements and the
   post-mortem lessons written before the held-out outcomes -- and propose up to eight new or
   revised rules and ids to retire;
4. validates every proposal against the schema and admits it only when the held-out outcomes alone
   give n >= `min_n` and a verdict at the level 1 - `alpha` / `max_proposals` (the pass's proposals
   share one error rate), and the older part agrees in sign. A proposal that trades on the same
   outcomes as an active rule (`max_overlap`) is a duplicate, and a filter the book retired is
   tested only on outcomes newer than its retirement;
5. keeps at most `max_rules`, ranked by the interval's bound nearest zero x sqrt(n), in
   `.data/ltcm/mind.json` (atomic write, under `mind.json.lock` for the whole pass, so a pass by
   hand and the floor's never interleave), and publishes a `lab.hypothesis` summarizing the pass and
   a `lab.result` whenever the book changed, with the evidence for every rule added or retired.

The book feeds back three ways, as evidence rather than instructions, each line written by code
from the rule's filter and score (the model's statement never reaches a desk):
`DeskContext.firm_rules()` puts the rules that apply to a desk into every session prompt ("# What
the firm has learned", after the standings); the lab's packet carries the family's rules when it
writes a strategy; and `rules_for_family(family)` returns the same block for any other strategy
generator (the Foundry's code-candidate prompt)::

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
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import NormalDist
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from .events import canonical, now_iso

try:  # the floor runs on Linux; elsewhere a pass simply runs unlocked
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

OUTCOME_KIND = "desk.outcome"
FILL_KIND = "broker.fill"
#: The tape a rule is scored on: the newest outcomes of every desk.
WINDOW = 10_000
RESAMPLES = 1000
#: Fixed, so a score is a function of the tape and nothing else.
BOOTSTRAP_SEED = 20260916
BOOK_VERSION = 1
#: The two-sided level of a score kept in the book and of a retention check.
LEVEL = 0.95
#: What `run` says when another pass (the floor's, or one by hand) holds the book.
LOCKED = "another pass holds the book"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "interval_minutes": 60,
    "profile": "k3",
    "reasoning_effort": "high",
    "max_output_tokens": 16384,
    "budget_usd_per_day": "8",
    "min_n": 15,
    "max_rules": 12,
    #: Rules the model may propose in one pass; they share one error rate (Bonferroni).
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
    #: The newest share of the tape the model never reads: proposals are scored on it alone.
    "holdout_fraction": 0.3,
    #: The two-sided error rate of one retention check; admission divides it by `max_proposals`.
    "alpha": 0.05,
    #: Winning and losing positions a rule needs, each way.
    "min_each_way": 3,
    #: Above this many positions the interval is the normal approximation, not a bootstrap.
    "bootstrap_max_n": 300,
    #: A proposal sharing this share of its outcomes with an active rule of its direction is a duplicate.
    "max_overlap": 0.8,
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
#: Lines a rendered block ever carries, whatever a caller asks for.
MAX_PROMPT_RULES = 12
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
    """One closed position, as a rule sees it."""

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
    #: The closed quantity's share of its opening fills' fees (`pnl` already nets an exit's fee).
    fees: float = 0.0
    #: The market's result for a settlement (`yes`/`no`); `sold` for a position sold before.
    result: str | None = None
    asset_class: str = ""
    #: The draw of chance this outcome belongs to (`cluster_of`); empty means its own.
    cluster: str = ""

    @property
    def notional(self) -> float:
        return self.entry_price * self.quantity

    @property
    def net_pnl(self) -> float:
        return self.pnl - self.fees

    @property
    def pnl_per_dollar(self) -> float:
        return self.net_pnl / self.notional

    @property
    def group(self) -> str:
        return self.cluster or f"outcome:{self.seq}"


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


def event_of(ticker: str) -> str:
    """A Kalshi market's event: `KXHIGHNY-26SEP16-B81.5` is one strike of `KXHIGHNY-26SEP16`, whose
    strikes all settle on the same day's temperature."""
    parts = ticker.split("-")
    return "-".join(parts[:-1]) if len(parts) >= 3 else ticker


def cluster_of(
    *, asset_class: str, venue: str | None, ticker: str, desk_id: str, instrument: str, opened_at: str | None, seq: int
) -> str:
    """The draw of chance an outcome belongs to. Every desk's position on one Kalshi event is
    one draw; the partial sells of one spot position (one desk, one instrument, one open) are one
    position; an outcome that says too little to place stands alone."""
    if asset_class == "event" or (not asset_class and venue == "kalshi"):
        return "event:" + event_of(ticker)
    if opened_at:
        return f"position:{desk_id}:{instrument}:{opened_at}"
    return f"outcome:{seq}"


def fill_opens(events: Iterable[Any]) -> dict[str, tuple[str | None, float]]:
    """(opened_at, entry fees) for every reducing fill on the tape, keyed `fill:<fill id>` and
    `close:<desk>:<instrument key>:<at>`: what an outcome written before the gateway recorded
    either (Sept 16, 2026) is scored with, when its fills are still in the window."""
    from .broker import Instrument
    from .ledger import position_walk

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    keys: dict[str, str | None] = {}
    for event in events:
        payload = getattr(event, "payload", None)
        if not isinstance(payload, Mapping):
            continue
        desk_id = payload.get("desk_id")
        instrument = payload.get("instrument")
        if not isinstance(desk_id, str) or not desk_id or not isinstance(instrument, Mapping):
            continue
        marker = canonical(instrument)
        if marker not in keys:
            try:
                keys[marker] = Instrument.from_dict(dict(instrument)).key
            except Exception:
                keys[marker] = None
        key = keys[marker]
        if key is None:
            continue
        at = str(getattr(event, "at", "") or payload.get("at") or "")
        groups.setdefault((desk_id, key), []).append({**payload, "at": at})
    out: dict[str, tuple[str | None, float]] = {}
    for (desk_id, key), rows in groups.items():
        for row in position_walk(rows):
            if row["closed"] <= 0:
                continue
            value = (row["opened_at"], float(row["entry_fees"]))
            if row["fill_id"]:
                out[f"fill:{row['fill_id']}"] = value
            out[f"close:{desk_id}:{key}:{row['at']}"] = value
    return out


def parse_outcome(
    event: Any, families: Mapping[str, str] | None = None, opens: Mapping[str, tuple[str | None, float]] | None = None
) -> Outcome | None:
    """An `Outcome` from a `desk.outcome` event, or None when it cannot be scored (no desk, no
    size, no entry price: a per-dollar return needs a notional). `opens` (`fill_opens`) supplies
    the entry fees and the open of an outcome that does not carry them."""
    stream = str(getattr(event, "stream", "") or "")
    if not stream.startswith("desk:") or len(stream) <= 5:
        return None
    payload = getattr(event, "payload", None)
    if not isinstance(payload, Mapping):
        return None
    desk_id = stream[5:]
    instrument = str(payload.get("instrument") or "")
    parts = instrument.split(":")
    asset_class = parts[0].lower() if parts else ""
    symbol = parts[1] if len(parts) > 1 else ""
    venue = parts[2].lower() if len(parts) > 2 and parts[2] else None
    leg = next((p.lower() for p in parts[3:] if p.lower() in SIDES), None)
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
    at = str(getattr(event, "at", "") or "")
    seq = int(getattr(event, "seq", 0) or 0)
    fees = _number(payload.get("entry_fees"))
    opened_at = payload.get("opened_at") if isinstance(payload.get("opened_at"), str) else None
    if opens and (fees is None or not opened_at):
        fill_id = payload.get("fill_id")
        found = opens.get(f"fill:{fill_id}") if fill_id else None
        if found is None:
            found = opens.get(f"close:{desk_id}:{instrument}:{at}")
        if found is not None:
            fees = found[1] if fees is None else fees
            opened_at = opened_at or found[0]
    real = payload.get("real_money")
    result = str(payload.get("result") or "").strip().lower() or None
    return Outcome(
        seq=seq,
        at=at,
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
        fees=max(0.0, fees or 0.0),
        result=result,
        asset_class=asset_class,
        cluster=cluster_of(
            asset_class=asset_class, venue=venue, ticker=ticker, desk_id=desk_id, instrument=instrument,
            opened_at=opened_at, seq=seq,
        ),
    )


def split_at(outcomes: Sequence[Outcome], seq: int) -> tuple[list[Outcome], list[Outcome]]:
    """(older, newer): the outcomes written at or before log position `seq`, and the ones after
    it. An outcome of a position the older part already holds (another desk's settlement of the
    same event, the last partial sell of a position) goes with the older part: it is not news."""
    if seq <= 0:
        return [], list(outcomes)
    older = [o for o in outcomes if o.seq <= seq]
    known = {o.group for o in older}
    newer: list[Outcome] = []
    for outcome in outcomes:
        if outcome.seq <= seq:
            continue
        (older if outcome.group in known else newer).append(outcome)
    return older, newer


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


def clusters(hits: Sequence[Outcome]) -> list[dict[str, Any]]:
    """The draws of chance among some outcomes, in order of first appearance: each group's net
    P&L, notional and return per dollar, and, when the group is one settled contract (one market,
    one leg, held to its result), whether it won and the break-even probability it paid for."""
    groups: dict[str, list[Outcome]] = {}
    for outcome in hits:
        groups.setdefault(outcome.group, []).append(outcome)
    out: list[dict[str, Any]] = []
    for key, rows in groups.items():
        pnl = math.fsum(o.net_pnl for o in rows)
        notional = math.fsum(o.notional for o in rows)
        binary = None
        if (
            len({o.ticker for o in rows}) == 1
            and len({o.leg for o in rows}) == 1
            and all(o.asset_class == "event" and o.result in SIDES and o.leg in SIDES and o.entry_price <= 1.0 for o in rows)
        ):
            quantity = math.fsum(o.quantity for o in rows)
            paid = math.fsum(o.entry_price * o.quantity + o.fees for o in rows)
            binary = {"won": rows[0].leg == rows[0].result, "break_even": min(1.0, paid / quantity)}
        out.append(
            {"key": key, "pnl": pnl, "notional": notional, "value": pnl / notional, "trades": len(rows), "binary": binary}
        )
    return out


def bootstrap_ci(
    values: Sequence[float], *, resamples: int = RESAMPLES, seed: int = BOOTSTRAP_SEED, level: float = LEVEL
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


def normal_ci(values: Sequence[float], *, level: float = LEVEL) -> tuple[float, float] | None:
    """Mean +/- z x standard error: what a bootstrap of many positions converges to, at a
    fraction of the CPU (a 10,000-trade bootstrap took 4.9 s of the interpreter lock)."""
    n = len(values)
    if n == 0:
        return None
    mean = math.fsum(values) / n
    if n == 1:
        return (mean, mean)
    variance = math.fsum((v - mean) ** 2 for v in values) / (n - 1)
    half = NormalDist().inv_cdf(1.0 - (1.0 - level) / 2.0) * math.sqrt(variance / n)
    return (mean - half, mean + half)


def binomial_tails(wins: int, n: int, p: float) -> tuple[float, float]:
    """(P(W <= wins), P(W >= wins)) for W ~ Binomial(n, p). With p the mean break-even
    probability of contracts bought at different prices this is conservative: the count of a
    Poisson-binomial is more concentrated than the binomial of the same mean (Hoeffding, 1956)."""
    if n <= 0:
        return 1.0, 1.0
    p = min(max(float(p), 0.0), 1.0)
    if p == 0.0:
        return 1.0, (1.0 if wins <= 0 else 0.0)
    if p == 1.0:
        return (1.0 if wins >= n else 0.0), 1.0
    log_p, log_q = math.log(p), math.log1p(-p)
    top = math.lgamma(n + 1)
    pmf = [math.exp(top - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * log_p + (n - k) * log_q) for k in range(n + 1)]
    wins = min(max(int(wins), 0), n)
    return min(1.0, math.fsum(pmf[: wins + 1])), min(1.0, math.fsum(pmf[wins:]))


def evaluate(
    rule: Mapping[str, Any],
    outcomes: Iterable[Outcome],
    *,
    resamples: int = RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    level: float = LEVEL,
    interval: bool = True,
    bootstrap_max_n: int = int(DEFAULT_CONFIG["bootstrap_max_n"]),
) -> dict[str, Any]:
    """The score of a rule (or a bare filter) on a tape: n independent positions (`clusters`),
    the trades in them, winning and losing positions, P&L net of entry fees, notional, the mean
    return per dollar of entry across positions with its interval at `level` (skipped when
    `interval` is False), the binomial test when every position is one settled contract, and
    first/last seen."""
    rule_filter = rule.get("filter") if isinstance(rule.get("filter"), Mapping) else rule
    hits = [o for o in outcomes if matches(rule_filter, o)]
    groups = clusters(hits)
    n = len(groups)
    values = [g["value"] for g in groups]
    score: dict[str, Any] = {
        "n": n,
        "trades": len(hits),
        "wins": sum(1 for v in values if v > 0),
        "losses": sum(1 for v in values if v < 0),
        "pnl_usd": round(math.fsum(o.net_pnl for o in hits), 4),
        "fees_usd": round(math.fsum(o.fees for o in hits), 4),
        "notional_usd": round(math.fsum(o.notional for o in hits), 4),
        "mean_pnl_per_dollar": None,
        "ci": None,
        "level": level,
        "binomial": None,
        "first_seen": min((o.at for o in hits), default=None),
        "last_seen": max((o.at for o in hits), default=None),
        "real_money_n": sum(1 for o in hits if o.real_money),
        "desks": len({o.desk_id for o in hits}),
    }
    if not n:
        return score
    score["mean_pnl_per_dollar"] = round(math.fsum(values) / n, 6)
    if not interval:
        return score
    if n > max(1, int(bootstrap_max_n)):
        low, high = normal_ci(values, level=level)  # type: ignore[misc]
    else:
        low, high = bootstrap_ci(values, resamples=resamples, seed=seed, level=level)  # type: ignore[misc]
    score["ci"] = [round(low, 6), round(high, 6)]
    if all(g["binary"] for g in groups):
        won = sum(1 for g in groups if g["binary"]["won"])
        break_even = math.fsum(g["binary"]["break_even"] for g in groups)
        p_low, p_high = binomial_tails(won, n, break_even / n)
        score["binomial"] = {"won": won, "break_even": round(break_even, 4), "p_low": p_low, "p_high": p_high}
    return score


def agrees(score: Mapping[str, Any], direction: str) -> bool:
    """Whether a score's mean sits on the rule's side of zero."""
    mean = score.get("mean_pnl_per_dollar")
    if mean is None:
        return False
    return float(mean) < 0 if direction == "avoid" else float(mean) > 0


def verdict(
    score: Mapping[str, Any], direction: str, min_n: int, *, min_each_way: int = int(DEFAULT_CONFIG["min_each_way"])
) -> tuple[bool, str]:
    """Whether a score earns a rule its place, and why not when it does not."""
    if direction not in DIRECTIONS:
        return False, f"unknown direction {direction!r}"
    n = int(score.get("n") or 0)
    if n < int(min_n):
        return False, f"n={n} is below the {int(min_n)} a rule needs"
    if "wins" in score and "losses" in score:
        wins, losses = int(score.get("wins") or 0), int(score.get("losses") or 0)
        if wins < min_each_way or losses < min_each_way:
            return False, f"{wins} winning and {losses} losing positions; a rule needs {min_each_way} of each"
    ci = score.get("ci")
    if not ci:
        return False, "no interval"
    low, high = float(ci[0]), float(ci[1])
    if not high > low:
        return False, "the interval has no width"
    if direction == "avoid" and not high < 0:
        return False, f"the interval [{_cents(low)}, {_cents(high)}] cents per $ does not sit below zero"
    if direction == "prefer" and not low > 0:
        return False, f"the interval [{_cents(low)}, {_cents(high)}] cents per $ does not sit above zero"
    binomial = score.get("binomial")
    if isinstance(binomial, Mapping):
        tail = (1.0 - float(score.get("level") or LEVEL)) / 2.0
        won, even = binomial.get("won"), binomial.get("break_even")
        if direction == "avoid" and not float(binomial.get("p_low", 1.0)) <= tail:
            return False, f"{won} of {n} settled positions won against {even} to break even: not significantly fewer"
        if direction == "prefer" and not float(binomial.get("p_high", 1.0)) <= tail:
            return False, f"{won} of {n} settled positions won against {even} to break even: not significantly more"
    return True, "admitted"


def rank_of(score: Mapping[str, Any]) -> float:
    """The interval's bound nearest zero x sqrt(n): the effect the evidence is sure of, on as
    many positions as carry it. A rule whose interval straddles zero ranks nothing."""
    ci = score.get("ci")
    n = int(score.get("n") or 0)
    if not ci or n <= 0:
        return 0.0
    low, high = float(ci[0]), float(ci[1])
    bound = low if low > 0 else (-high if high < 0 else 0.0)
    return bound * math.sqrt(n)


def _cents(value: Any) -> str:
    return f"{float(value) * 100:.1f}"


def evidence_text(score: Mapping[str, Any]) -> str:
    """`n=47, -6.1 cents per $, CI [-9.0, -3.2]`; with the trades a position count stands for,
    `n=47 positions (63 trades, 12 real money), -6.1 cents per $ net of fees, CI [-9.0, -3.2]`."""
    n = int(score.get("n") or 0)
    mean = score.get("mean_pnl_per_dollar")
    ci = score.get("ci")
    counted = "trades" in score
    head = f"n={n}"
    if counted:
        head += f" positions ({int(score.get('trades') or 0)} trades, {int(score.get('real_money_n') or 0)} real money)"
    if mean is None or not ci:
        return head
    net = " net of fees" if counted else ""
    return f"{head}, {_cents(mean)} cents per ${net}, CI [{_cents(ci[0])}, {_cents(ci[1])}]"


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
    largest |P&L| and the largest n first, alternately, up to `limit`. n counts independent
    positions and the returns are net of entry fees, exactly as a rule is scored. Computed in
    code: the model reads numbers the floor wrote, never numbers it guessed."""
    groups: dict[tuple[str, str, str, str, str], list[Outcome]] = {}
    for outcome in outcomes:
        key = (outcome.family, outcome.strategy, outcome.series, band_of(outcome), outcome.leg or "-")
        groups.setdefault(key, []).append(outcome)
    cells: list[dict[str, Any]] = []
    for key, rows in groups.items():
        returns = [g["value"] for g in clusters(rows)]
        n = len(returns)
        mean = math.fsum(returns) / n
        se = None
        if n > 1:
            variance = math.fsum((r - mean) ** 2 for r in returns) / (n - 1)
            se = math.sqrt(variance / n)
        cells.append(
            {
                "family": key[0], "strategy": key[1], "series": key[2], "band": key[3], "leg": key[4],
                "n": n, "trades": len(rows), "wins": sum(1 for r in returns if r > 0),
                "pnl_usd": round(math.fsum(o.net_pnl for o in rows), 2),
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
    lines = ["family | strategy | series | entry band | leg | n | trades | wins | pnl_usd | cents per $ | se | real-money trades"]
    for c in cells:
        se = "-" if c.get("se") is None else _cents(c["se"])
        lines.append(
            f"{c['family']} | {c['strategy']} | {c['series']} | {c['band']} | {c['leg']} | {c['n']} | {c['trades']} | "
            f"{c['wins']} | {c['pnl_usd']:.2f} | {_cents(c['mean_pnl_per_dollar'])} | {se} | {c['real_money_n']}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- the prompt

PROMPT_HEADER = (
    "Evidence, not instructions: your limits, sizes and mandate are unchanged. Each line below is written by code "
    "from a rule's filter and its score across every desk's closed trades, live and shadow, net of fees: n counts "
    "independent positions (every desk and strike of one Kalshi event is one), cents per $ is the mean return on "
    "entry notional, and CI is its 95% interval. A rule was admitted only on trades newer than anything its "
    "proposer had read, is re-scored every hour and is retired when it stops holding. Weigh it against your own "
    "record, and say in your memo when you act on one or depart from one."
)


def _price(value: float) -> str:
    return f"{value:.2f}" if value <= 1.0 else f"{value:g}"


def describe_filter(rule_filter: Mapping[str, Any]) -> str:
    """A validated filter in words, e.g. `kalshi, tickers KXHIGHNY*, NO leg, entry 0.90 to 1.00`."""
    parts: list[str] = []
    if rule_filter.get("venue"):
        parts.append(str(rule_filter["venue"]))
    if rule_filter.get("series_prefix"):
        parts.append("tickers " + " or ".join(f"{p}*" for p in rule_filter["series_prefix"]))
    if rule_filter.get("family"):
        parts.append("family " + " or ".join(rule_filter["family"]))
    if rule_filter.get("strategy"):
        parts.append("strategy " + " or ".join(rule_filter["strategy"]))
    if rule_filter.get("result_side"):
        parts.append(f"{str(rule_filter['result_side']).upper()} leg")
    if rule_filter.get("entry_price"):
        low, high = rule_filter["entry_price"]
        parts.append(f"entry {_price(low)} to {_price(high)}")
    if rule_filter.get("held_hours"):
        low, high = rule_filter["held_hours"]
        parts.append(f"held {low:g} to {high:g} hours")
    if rule_filter.get("real_money") is True:
        parts.append("real-money trades")
    elif rule_filter.get("real_money") is False:
        parts.append("shadow trades")
    return ", ".join(parts)


def _clean_score(raw: Any) -> dict[str, Any]:
    """The numbers of a score and nothing else, in sane ranges: a book edited by hand cannot put
    words or a 300-digit figure into a prompt through its score."""
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key in ("n", "trades", "real_money_n"):
        value = _number(raw.get(key))
        if value is not None and 0 <= value <= 10_000_000:
            out[key] = int(value)
    if "n" not in out:
        return {}
    mean = _number(raw.get("mean_pnl_per_dollar"))
    if mean is not None and abs(mean) <= 1000:
        out["mean_pnl_per_dollar"] = mean
    ci = raw.get("ci")
    if isinstance(ci, (list, tuple)) and len(ci) == 2:
        low, high = _number(ci[0]), _number(ci[1])
        if low is not None and high is not None and abs(low) <= 1000 and abs(high) <= 1000:
            out["ci"] = [low, high]
    return out


def render_rules(rules: Iterable[Mapping[str, Any]], *, limit: int = MAX_PROMPT_RULES) -> str:
    """The prompt's block: one line per rule, written here from its validated filter and its
    numbers. A rule's statement is the model's sentence and never reaches a desk; a row without a
    valid filter and direction is left out."""
    lines = [PROMPT_HEADER]
    for rule in rules:
        if len(lines) > min(max(0, int(limit)), MAX_PROMPT_RULES):
            break
        if not isinstance(rule, Mapping) or rule.get("direction") not in DIRECTIONS:
            continue
        try:
            rule_filter = validate_filter(rule.get("filter"))
        except MindError:
            continue
        score = _clean_score(rule.get("score"))
        if not score:
            continue
        lines.append(f"- {str(rule['direction']).upper()}: {describe_filter(rule_filter)}; {evidence_text(score)}")
    return "\n".join(lines) if len(lines) > 1 else ""


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


def _prompt_row(rule: Any) -> dict[str, Any] | None:
    """A book rule as a prompt reads it, held to the schema (a hand-edited book is not trusted),
    or None."""
    if not isinstance(rule, Mapping):
        return None
    try:
        valid = validate_rule({k: rule.get(k) for k in RULE_KEYS})
    except MindError:
        return None
    score = _clean_score(rule.get("score"))
    if not score:
        return None
    return {
        "id": valid["id"],
        "direction": valid["direction"],
        "filter": valid["filter"],
        "score": score,
        "evidence": evidence_text(score),
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
        rows = [row for row in (_prompt_row(r) for r in read_book(target).get("rules") or []) if row is not None]
        chosen = [row for row in rows if applies(row, family=family)][: max(0, int(limit))]
        return render_rules(chosen)
    except Exception:
        return ""


# --------------------------------------------------------------------------- the mind


def _parse_at(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").replace("<", "‹").split())[:limit]


def _seq(value: Any) -> int:
    number = _number(value)
    return int(number) if number is not None and number > 0 else 0


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
        lessons: Callable[[], Iterable[Any]] | None = None,
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
        self._matched_cache: dict[str, frozenset[int]] = {}
        if register:
            _ACTIVE_PATH = self.path

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    @property
    def min_each_way(self) -> int:
        return int(self.config["min_each_way"])

    @property
    def admission_level(self) -> float:
        """One minus the pass's error rate shared across its proposals."""
        return 1.0 - float(self.config["alpha"]) / max(1, int(self.config["max_proposals"]))

    @property
    def retention_level(self) -> float:
        return 1.0 - float(self.config["alpha"])

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

    def _write(self, data: Mapping[str, Any]) -> None:
        """The book on disk, atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
        try:
            stat = self.path.stat()
            self._stamp = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            self._stamp = None

    def _save(self, book: Mapping[str, Any], persist: bool) -> None:
        with self._lock:
            self._book = json.loads(json.dumps(dict(book)))
            if persist:
                self._write(self._book)

    @contextmanager
    def _pass_lock(self) -> Iterator[bool]:
        """An exclusive, non-blocking `flock` on `<book>.lock` for a whole pass: the floor's worker
        and a pass by hand each re-read the book and write it back, so whichever wrote last used
        to erase the other's rules. Yields False when another pass holds it."""
        if fcntl is None:  # pragma: no cover
            yield True
            return
        lock_path = self.path.with_name(self.path.name + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+")
        try:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def rules(self) -> list[dict[str, Any]]:
        return [r for r in self.book().get("rules") or [] if isinstance(r, dict)]

    def rules_for(
        self, family: str | None = None, venues: Iterable[str] | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """The active rules that apply to a desk, strongest first, ready for `render_rules`. A rule
        that fails the schema (a book edited by hand) is left out."""
        cap = min(int(self.config["prompt_rules"] if limit is None else limit), MAX_PROMPT_RULES)
        venue_list = list(venues) if venues is not None else None
        rows = [row for row in (_prompt_row(r) for r in self.rules()) if row is not None]
        return [row for row in rows if applies(row, family=family, venues=venue_list)][: max(0, cap)]

    def block_for(self, family: str) -> str:
        """`rules_for_family` for this mind's own book."""
        try:
            return render_rules(self.rules_for(family=family))
        except Exception:
            return ""

    # ------------------------------------------------------------------ the evidence
    def outcomes(self) -> tuple[list[Outcome], int]:
        """Every scoreable outcome in the newest `WINDOW` of the log, in log order, and the
        sequence number of the newest outcome event (the evidence fingerprint). An outcome written
        before the gateway recorded its entry fees and its open takes them from the fills."""
        events = self.log.read(kind=OUTCOME_KIND, limit=WINDOW, newest=True)
        try:
            families = dict(self.families()) if self.families is not None else {}
        except Exception:
            families = {}
        opens = None
        if any(isinstance(getattr(e, "payload", None), Mapping) and e.payload.get("entry_fees") is None for e in events):
            try:
                opens = fill_opens(self.log.read(kind=FILL_KIND, limit=WINDOW, newest=True))
            except Exception:
                opens = None
        rows = sorted((o for o in (parse_outcome(e, families, opens) for e in events) if o is not None), key=lambda o: o.seq)
        latest = max((int(getattr(e, "seq", 0) or 0) for e in events), default=0)
        return rows, latest

    def score(
        self, rule: Mapping[str, Any], outcomes: Sequence[Outcome], *, level: float | None = None, interval: bool = True
    ) -> dict[str, Any]:
        return evaluate(
            rule,
            outcomes,
            resamples=int(self.config["resamples"]),
            level=self.retention_level if level is None else level,
            interval=interval,
            bootstrap_max_n=int(self.config["bootstrap_max_n"]),
        )

    def split(self, outcomes: Sequence[Outcome]) -> tuple[list[Outcome], list[Outcome], int]:
        """(read, held out, cut): the older part of the tape the scientist reads, the newest
        `holdout_fraction` it never sees, and the log position between them."""
        if not outcomes:
            return [], [], 0
        fraction = min(0.9, max(0.1, float(self.config["holdout_fraction"])))
        keep = min(len(outcomes), max(1, math.ceil(len(outcomes) * (1.0 - fraction))))
        cut = outcomes[keep - 1].seq
        read, held_out = split_at(outcomes, cut)
        return read, held_out, cut

    def retention(self, rule: Mapping[str, Any], outcomes: Sequence[Outcome]) -> tuple[bool, str, dict[str, Any]]:
        """Whether a book rule keeps its place, why, and its score: on the outcomes newer than the
        tape its proposer read (all of them for a rule written by hand), and, once `min_n`
        positions have closed since its admission, their mean must still sit on its side of zero."""
        direction = str(rule.get("direction"))
        min_n = int(self.config["min_n"])
        cut, admitted = _seq(rule.get("holdout_from_seq")), _seq(rule.get("admitted_seq"))
        _, unseen = split_at(outcomes, cut)
        score = self.score(rule, unseen)
        ok, reason = verdict(score, direction, min_n, min_each_way=self.min_each_way)
        if not ok:
            return False, reason, score
        if admitted > cut:
            _, since = split_at(outcomes, admitted)
            later = self.score(rule, since, interval=False)
            score["since_admission"] = {"n": later["n"], "mean_pnl_per_dollar": later["mean_pnl_per_dollar"]}
            if later["n"] >= min_n and not agrees(later, direction):
                return (
                    False,
                    f"the {later['n']} positions closed since admission average {_cents(later['mean_pnl_per_dollar'])} "
                    f"cents per $, the wrong side of zero",
                    score,
                )
        return True, "holds", score

    def recent_lessons(self, *, before_seq: int | None = None, before_at: str | None = None) -> list[str]:
        """The desks' newest post-mortem lessons, and any lessons the memory store holds. With a
        cutoff, only lessons written before the held-out outcomes: a lesson drawn from them would
        carry the test's answers into the question."""
        limit = max(0, int(self.config["lessons"]))
        out: list[str] = []

        def add(text: str) -> None:
            text = _clean(text, 240)
            if len(text) > 8 and text not in out and len(out) < limit:
                out.append(text)

        try:
            for event in reversed(self.log.read(kind="desk.postmortem", limit=60, newest=True)):
                if before_seq is not None and int(getattr(event, "seq", 0) or 0) >= before_seq:
                    continue
                desk = str(event.stream).split(":", 1)[-1]
                for lesson in event.payload.get("lessons") or []:
                    if isinstance(lesson, str):
                        add(f"{desk}: {lesson}")
        except Exception:
            pass
        if self.lessons is not None:
            try:
                for lesson in self.lessons():
                    if isinstance(lesson, Mapping):
                        written, text = lesson.get("at"), lesson.get("text")
                    else:
                        written, text = None, lesson
                    if before_at is not None and not (isinstance(written, str) and written < before_at):
                        continue  # written after the cutoff, or undated: it may know the answers
                    add(str(text or ""))
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
        """One pass, under the book's lock. Never raises: a failure is an alert and a summary that
        says so; a pass that finds the lock held does nothing and says `skipped: LOCKED`."""
        at = at or self.now()
        try:
            with self._pass_lock() as held:
                if not held:
                    return {"at": at, "skipped": LOCKED}
                return self._run(at, ask=ask, persist=persist, publish=publish, force=force)
        except Exception as exc:
            self.alert(f"firm mind pass failed: {type(exc).__name__}: {str(exc)[:200]}")
            return {"at": at, "failed": f"{type(exc).__name__}"}

    def _run(self, at: str, *, ask: bool, persist: bool, publish: bool, force: bool) -> dict[str, Any]:
        min_n = int(self.config["min_n"])
        self._matched_cache = {}
        book = self.book()
        # The attempt is stamped before any work, so a pass that fails waits its interval instead
        # of retrying (and paying) every tick.
        book["last_pass_at"] = at
        self._save(book, persist)

        outcomes, latest = self.outcomes()
        fingerprint = {"seq": latest, "n": len(outcomes), "min_n": min_n, "holdout": float(self.config["holdout_fraction"])}
        read, held_out, cut = self.split(outcomes)
        summary: dict[str, Any] = {
            "at": at, "outcomes": len(outcomes), "held_out": len(held_out), "rules": len(book.get("rules") or []),
            "added": [], "revised": [], "retired": [], "proposals": [], "asked": False,
        }
        if not force and book.get("evidence") == fingerprint:
            summary["skipped"] = "no new outcomes since the last pass"
            return summary

        before = {r["id"]: r for r in book.get("rules") or [] if isinstance(r, dict) and r.get("id")}
        history = [r for r in book.get("retired") or [] if isinstance(r, dict)]
        active: dict[str, dict[str, Any]] = {}
        retired: list[dict[str, Any]] = []
        # 1. Re-score the book on what its proposers never read. A rule that stopped holding goes,
        #    without asking anyone.
        for rule_id, rule in before.items():
            try:  # a book edited by hand is held to the same schema as the model
                rule = {**rule, **validate_rule({k: rule.get(k) for k in RULE_KEYS})}
            except MindError as exc:
                retired.append(self._retirement(rule, {}, f"invalid in the book: {exc}", at, latest))
                continue
            ok, reason, score = self.retention(rule, outcomes)
            if ok:
                active[rule_id] = {**rule, "score": score}
            else:
                retired.append(self._retirement(rule, score, f"re-scored: {reason}", at, latest))

        # 2. Ask the scientist, when the held-out outcomes could admit a rule at all.
        if ask and self.provider is not None and len({o.group for o in held_out}) >= min_n and read:
            reply = self._ask(at, read, held_out, list(active.values()), retired + history, persist=persist)
            summary["asked"] = reply is not None
            if reply is not None:
                proposals, retire_ids = reply
                for rule_id in retire_ids[: int(self.config["max_rules"])]:
                    rule = active.pop(rule_id, None)
                    if rule is not None:
                        retired.append(self._retirement(rule, rule["score"], "retired by the scientist", at, latest))
                for raw in proposals[: int(self.config["max_proposals"])]:
                    summary["proposals"].append(
                        self._consider(raw, outcomes, read, cut, latest, active, before, retired + history, at)
                    )

        # 3. Rank and cap.
        ordered = sorted(active.values(), key=lambda r: (-rank_of(r["score"]), r["id"]))
        cap = max(0, int(self.config["max_rules"]))
        for rule in ordered[cap:]:
            retired.append(self._retirement(rule, rule["score"], f"outranked: the book keeps {cap} rules", at, latest))
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
        book["last_summary"] = {
            k: summary[k] for k in ("at", "outcomes", "held_out", "rules", "added", "revised", "retired", "asked")
        }
        self._save(book, persist)
        if publish and (outcomes or added or revised or retired):
            self._publish(at, summary, outcomes, added, revised, retired)
        return summary

    def _retirement(
        self, rule: Mapping[str, Any], score: Mapping[str, Any], reason: str, at: str, latest: int
    ) -> dict[str, Any]:
        return {
            "id": rule.get("id"),
            "statement": rule.get("statement"),
            "direction": rule.get("direction"),
            "filter": rule.get("filter"),
            "score": dict(score),
            "evidence": evidence_text(score),
            "reason": reason[:240],
            "retired_at": at,
            # A filter retired here is tested again only on outcomes written after this.
            "retired_seq": latest,
        }

    def _consider(
        self,
        raw: Any,
        outcomes: Sequence[Outcome],
        read: Sequence[Outcome],
        cut: int,
        latest: int,
        active: dict[str, dict[str, Any]],
        before: Mapping[str, Mapping[str, Any]],
        retired: Sequence[Mapping[str, Any]],
        at: str,
    ) -> dict[str, Any]:
        """Validate, test out of sample and admit (or refuse) one proposed rule, in place in
        `active`."""
        min_n = int(self.config["min_n"])
        try:
            rule = validate_rule(raw)
        except MindError as exc:
            rule_id = raw.get("id") if isinstance(raw, Mapping) and isinstance(raw.get("id"), str) else None
            return {"id": _clean(rule_id, 64) or None, "status": "invalid", "reason": str(exc)}
        mine = self._matched(rule["filter"], outcomes)
        for other in active.values():
            if other["id"] == rule["id"] or other["direction"] != rule["direction"]:
                continue
            if other["filter"] == rule["filter"]:
                return {"id": rule["id"], "status": "rejected", "reason": f"duplicates {other['id']}"}
            theirs = self._matched(other["filter"], outcomes)
            shared = len(mine & theirs)
            if self._same_trades(mine, theirs):
                return {
                    "id": rule["id"], "status": "rejected",
                    "reason": f"duplicates {other['id']}: {shared} of its {len(theirs)} trades and {len(mine)} of these are the same",
                }
        # A filter the book retired -- or one that trades on the same outcomes, whichever way it
        # points -- is tested only on outcomes written after that retirement, so proposing it
        # again every hour, or with its hours nudged, until chance admits it gains nothing.
        since = 0
        for old in retired:
            try:
                old_filter = validate_filter(old.get("filter"))
            except MindError:
                continue
            if old_filter == rule["filter"] or self._same_trades(mine, self._matched(old_filter, outcomes)):
                since = max(since, _seq(old.get("retired_seq")))
        test_cut = max(cut, since)
        _, unseen = split_at(outcomes, test_cut)
        level = self.admission_level
        trial = self.score(rule, unseen, level=level)
        ok, reason = verdict(trial, rule["direction"], min_n, min_each_way=self.min_each_way)
        if ok:
            older = self.score(rule, read, interval=False)
            if not agrees(older, rule["direction"]):
                ok = False
                reason = (
                    f"held on the unseen outcomes, but the {older['n']} positions the scientist read do not sit on "
                    f"the same side of zero"
                )
        row = {
            "id": rule["id"],
            "status": "admitted" if ok else "rejected",
            "reason": reason,
            "evidence": evidence_text(trial) + f" at {level * 100:.2f}% on unseen outcomes",
        }
        if ok:
            previous = active.get(rule["id"]) or before.get(rule["id"]) or {}
            active[rule["id"]] = {
                **rule,
                "score": self.score(rule, unseen),
                "admission": {"level": round(level, 6), "n": trial["n"], "ci": trial["ci"], "binomial": trial["binomial"]},
                "holdout_from_seq": test_cut,
                "admitted_seq": latest,
                "admitted_at": previous.get("admitted_at") or at,
                "revised_at": at,
            }
        return row

    def _same_trades(self, mine: frozenset[int], theirs: frozenset[int]) -> bool:
        """Whether two rules select mostly the same outcomes (`max_overlap` of the larger set)."""
        return bool(mine and theirs) and len(mine & theirs) >= float(self.config["max_overlap"]) * max(len(mine), len(theirs))

    def _matched(self, rule_filter: Mapping[str, Any], outcomes: Sequence[Outcome]) -> frozenset[int]:
        """The log positions a filter selects on the pass's tape (the cache is emptied as each
        pass starts)."""
        key = canonical(rule_filter)
        if key not in self._matched_cache:
            self._matched_cache[key] = frozenset(o.seq for o in outcomes if matches(rule_filter, o))
        return self._matched_cache[key]

    # ------------------------------------------------------------------ the scientist
    def _spent_today(self, book: Mapping[str, Any], day: str) -> Decimal:
        spend = book.get("spend") or {}
        if spend.get("day") != day:
            return Decimal(0)
        try:
            return Decimal(str(spend.get("usd") or "0"))
        except InvalidOperation:
            return Decimal(0)

    def _add_spend(self, day: str, delta: Decimal) -> None:
        """Move today's tally by `delta`, on disk whether or not the pass persists its rules: a
        dry run's model call costs the same money. Read from and written to the file alone, so a
        dry run's unsaved book never lands with it."""
        with self._lock:
            disk = {"version": BOOK_VERSION, "rules": [], "retired": [], **read_book(self.path)}
            usd = max(self._spent_today(disk, day) + delta, Decimal(0))
            spend = {"day": day, "usd": format(usd.normalize(), "f")}
            disk["spend"] = spend
            self._write(disk)
            if self._book is not None:
                self._book["spend"] = spend

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
        read: Sequence[Outcome],
        held_out: Sequence[Outcome],
        rules: Sequence[Mapping[str, Any]],
        retired: Sequence[Mapping[str, Any]],
        *,
        persist: bool = True,
    ) -> tuple[list[Any], list[str]] | None:
        packet = self.packet(
            at, read, rules, retired, held_out=len(held_out),
            before_seq=min((o.seq for o in held_out), default=None),
            before_at=min((o.at for o in held_out), default=None),
        )
        instructions = self.instructions()
        day = at[:10]
        budget = Decimal(str(self.config["budget_usd_per_day"]))
        spent = self._spent_today(self.book(), day)
        estimate = self._estimate(len(instructions) + len(packet))
        if spent + estimate > budget:
            self.alert(f"firm mind skipped its model call: ${spent} of ${budget} spent today")
            return None
        # The provider's own per-desk cap is the floor's desk fuse, not this budget, so the tally
        # here is the cap: the estimate is booked before the call and stays booked if the call
        # fails after it was sent.
        self._add_spend(day, estimate)
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
            if any(cls.__name__ == "BudgetExceeded" for cls in type(exc).__mro__):
                self._add_spend(day, -estimate)  # refused before anything was sent
            self.alert(f"firm mind model call failed: {type(exc).__name__}: {str(exc)[:160]}")
            return None
        cost = getattr(response, "cost_usd", None)
        try:
            cost = Decimal(str(cost)) if cost is not None else estimate
        except InvalidOperation:
            cost = estimate
        self._add_spend(day, cost - estimate)
        current = self.book()
        current["last_asked_at"] = at
        self._save(current, persist)
        return parse_reply(getattr(response, "output_text", "") or "")

    def instructions(self) -> str:
        cfg = self.config
        holdout = min(0.9, max(0.1, float(cfg["holdout_fraction"])))
        return (
            "You are the Firm Mind of a public, fully automated trading floor: its scientist. Every desk's closed "
            "trades are scored in code; your job is to turn them into a small book of machine-checkable rules that "
            "every desk session and every strategy generator on the floor reads as evidence. You get an aggregate table "
            "computed in code (family x strategy x series x entry-price band x leg), the current rule book scored on "
            "the same outcomes, rules recently retired and why, and the desks' own post-mortem lessons (hypotheses, not "
            "evidence).\n"
            "Reply with JSON only, in this shape: {\"rules\": [...], \"retire\": [\"rule-id\", ...]}. "
            f"At most {cfg['max_proposals']} rules, each new or a revision of an existing id:\n"
            "{\"id\": \"lowercase-slug\", \"statement\": \"one sentence for the public record\", \"filter\": {...}, "
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
            f"How rules are judged, in code, after you answer. The outcomes you read are the older "
            f"{round((1 - holdout) * 100)}% of the newest {WINDOW}; the newest {round(holdout * 100)}% are held out, and a "
            "proposal is scored on them alone. n counts independent positions: every desk, leg and strike of one Kalshi "
            "event is one, and so are the partial sells of one spot position. The score is the mean P&L per dollar of "
            "entry notional per position, net of entry fees, with a seeded bootstrap interval at "
            f"{self.admission_level * 100:.2f}% (the pass's proposals share a 5% error rate), and for settled contracts "
            "an exact binomial test of the positions that won against the break-even count. A rule is admitted only with "
            f"at least {cfg['min_n']} held-out positions, {cfg['min_each_way']} winning and {cfg['min_each_way']} losing, "
            "an interval that excludes zero in its direction (avoid: upper bound below zero; prefer: lower bound above "
            "zero), and a mean on the same side in the outcomes you read. A rule that trades on the same outcomes as an "
            "active one is a duplicate, and a filter the book retired is tested only on outcomes after its retirement. "
            "Every rule is re-scored every pass on outcomes newer than what its proposer read and retired automatically "
            f"when it stops holding; the book keeps at most {cfg['max_rules']}, ranked by the interval's bound nearest "
            "zero x sqrt(n). Desks read a line written from your filter and the score, never your statement.\n"
            "Write rules narrow enough to act on and broad enough to carry the trades: a cell with a large n and a mean "
            "several standard errors from zero is a candidate, a single outlier trade is not, and neighbouring cells "
            "that agree can be one rule; expect a cell picked for being extreme to be weaker on newer outcomes. The "
            "statement says what the rule is and where, in plain words, and claims nothing the filter does not test. "
            "Revise a rule by reusing its id; retire one only when the table shows it is wrong or superseded. Reply "
            "{\"rules\": [], \"retire\": []} when the evidence supports nothing new."
        )

    def packet(
        self,
        at: str,
        outcomes: Sequence[Outcome],
        rules: Sequence[Mapping[str, Any]],
        retired: Sequence[Mapping[str, Any]],
        *,
        held_out: int = 0,
        before_seq: int | None = None,
        before_at: str | None = None,
    ) -> str:
        """Everything the scientist reads, from the older part of the tape only: numbers the
        floor wrote, and the lessons desks wrote before the held-out outcomes."""
        n = len(outcomes)
        parts = [f"# The floor's closed positions, now {at} UTC"]
        if n:
            groups = clusters(outcomes)
            parts.append(
                f"{n} outcomes ({len(groups)} independent positions) from {len({o.desk_id for o in outcomes})} desks, "
                f"{min(o.at for o in outcomes)[:16]} to {max(o.at for o in outcomes)[:16]}; "
                f"{sum(1 for o in outcomes if o.real_money)} with real money; net of fees "
                f"{math.fsum(o.net_pnl for o in outcomes):.2f} USD, mean "
                f"{_cents(math.fsum(g['value'] for g in groups) / len(groups))} cents per $ of entry per position."
            )
            if held_out:
                parts.append(
                    f"The newest {held_out} outcomes are held out: you do not see them, and every rule you propose is "
                    "scored on them alone."
                )
            families: dict[str, list[Outcome]] = {}
            for o in outcomes:
                families.setdefault(o.family, []).append(o)
            lines = []
            for family, rows in sorted(families.items()):
                values = [g["value"] for g in clusters(rows)]
                lines.append(
                    f"- {family}: n={len(values)} positions ({len(rows)} trades), pnl {math.fsum(o.net_pnl for o in rows):.2f} "
                    f"USD, {_cents(math.fsum(values) / len(values))} cents per $"
                )
            parts.append("## By family\n" + "\n".join(lines))
            cells = aggregate(outcomes, int(self.config["cells"]))
            parts.append(
                f"## Cells (top {len(cells)} by |pnl| and by n; n is independent positions, se the standard error in "
                "cents)\n" + table_text(cells)
            )
        else:
            parts.append("(no settled outcomes yet)")
        if rules:
            lines = []
            for r in sorted(rules, key=lambda r: -rank_of(r["score"])):
                here = self.score(r, outcomes, interval=False)
                lines.append(
                    f"- {r['id']} [{r['direction']}] {r['statement']} | filter {canonical(r['filter'])} | "
                    f"on these outcomes: {evidence_text(here)}, {'-' if here['mean_pnl_per_dollar'] is None else _cents(here['mean_pnl_per_dollar'])} cents per $"
                )
            parts.append("## The rule book, scored on the outcomes above\n" + "\n".join(lines))
        else:
            parts.append("## The rule book\n(empty)")
        if retired:
            lines = [
                f"- {r.get('id')} [{r.get('direction')}] {r.get('statement')} | filter {canonical(r.get('filter') or {})} | "
                f"{r.get('reason')}"
                for r in list(retired)[:8]
            ]
            parts.append("## Retired recently\n" + "\n".join(lines))
        lessons = self.recent_lessons(before_seq=before_seq, before_at=before_at)
        if lessons:
            parts.append(
                "## Post-mortem lessons written before the held-out outcomes, newest first (hypotheses to test, not "
                "evidence)\n" + "\n".join(f"- {x}" for x in lessons)
            )
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
            f"The Firm Mind read {len(outcomes)} settled outcomes from {len({o.desk_id for o in outcomes})} desks, "
            f"{summary.get('held_out')} of them held out"
            + (f", and tested {len(proposals)} proposed rules on those alone, {admitted} admitted" if summary.get("asked") else "")
            + f"; the book holds {summary.get('rules')} rules ({len(added)} added, {len(revised)} revised, "
            f"{len(retired)} retired)."
        )
        plan = (
            f"A proposal is scored only on the newest {round(float(self.config['holdout_fraction']) * 100)}% of the "
            f"newest {WINDOW} desk.outcome events, which its proposer never read: mean P&L per dollar of entry net of "
            f"fees, one observation per Kalshi event or spot position, admitted with n >= {self.config['min_n']}, "
            f"{self.config['min_each_way']} wins and losses each, an interval at {self.admission_level * 100:.2f}% "
            f"excluding zero in its direction and a binomial test for settled contracts; re-checked every "
            f"{self.config['interval_minutes']} minutes on outcomes newer than its admission."
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

    def memory_lessons() -> list[dict[str, Any]]:
        read = getattr(getattr(service, "memory", None), "read", None)
        if not callable(read):
            return []
        rows = read("lesson", 60)
        return [
            {"at": row.get("at"), "text": f"{row.get('desk_id')}: {row.get('text')}"}
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
    "LOCKED",
    "MindError",
    "Outcome",
    "aggregate",
    "agrees",
    "applies",
    "binomial_tails",
    "bootstrap_ci",
    "build",
    "clusters",
    "cluster_of",
    "describe_filter",
    "evaluate",
    "event_of",
    "evidence_text",
    "fill_opens",
    "matches",
    "normal_ci",
    "parse_outcome",
    "parse_reply",
    "rank_of",
    "render_rules",
    "rules_for_family",
    "split_at",
    "strategy_of",
    "validate_filter",
    "validate_rule",
    "verdict",
]
