"""Rung 3 sizing, and the standing capital recommendation for the owner.

**Sizing.** An agent on rung 3 has real fills behind a lower confidence bound on its growth. Its
stake is a quarter of Kelly on that LOWER bound, never on the point estimate: with block returns
of mean m and variance v on its present stake S, full Kelly would scale the stake by m / v; the
House uses 0.25 x m_lower / v, where m_lower is the one-sided lower bound the ladder already
computed. The result is clamped: never below the micro stake, never above a fixed share of the
venue's cash, and every order still meets the gateway's $75 cap. An agent whose lower bound is at
or below zero is sized back to the micro stake, and the drift monitor may send it down a rung.

**Recommendation.** The owner is the only one who moves money between venues or adds capital. The
House's job is to say, from evidence alone, where another dollar would be best used: it adds up,
per venue, the capital the rung-2 and rung-3 agents' lower bounds can justify, compares it with
the cash the venue holds, and writes one plain sentence. With no agent above paper it says so:
the honest recommendation in the first weeks is to add nothing.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import Any

from . import stats
from .constitution import CONSTITUTION

ZERO = Decimal(0)
CENT = Decimal("0.01")


def kelly_stake(growth: list[float], present_stake: Decimal, venue_cash: Decimal, *, alpha: float | None = None, family_lcb: float | None = None) -> tuple[Decimal, dict[str, Any]]:
    """The stake a rung-3 record justifies, and the numbers behind it.

    `family_lcb` is for an agent that was scaled on its family's pooled record: while its own
    lower bound is not above zero it is sized on the family's, against its OWN variance (the
    pooled series is an average, and an average is calmer than any one member)."""
    rules = CONSTITUTION["rungs"]["3"]
    floor = Decimal(CONSTITUTION["rungs"]["2"]["stake_usd"])
    ceiling = (venue_cash * Decimal(str(rules["max_share_of_venue"]))).quantize(CENT, rounding=ROUND_DOWN)
    bounds = stats.mean_bounds(growth, alpha if alpha is not None else float(CONSTITUTION["ladder"]["alpha"]))
    numbers: dict[str, Any] = {"blocks": len(growth), "floor_usd": str(floor), "ceiling_usd": str(ceiling)}
    if bounds is None or bounds["sd"] <= 0:
        return floor, {**numbers, "reason": "no bounded record yet"}
    lcb, basis = bounds["lcb"], "a quarter of Kelly on the lower bound"
    if lcb <= 0 and family_lcb is not None and family_lcb > 0 and bounds["mean"] > 0:
        lcb, basis = min(family_lcb, bounds["mean"]), "a quarter of Kelly on its family's lower bound"
    fraction = stats.quarter_kelly(lcb, bounds["sd"] ** 2, fraction=float(rules["kelly_fraction"]), cap=1e9)
    numbers.update(mean=bounds["mean"], lcb=bounds["lcb"], sized_on=lcb, variance=bounds["sd"] ** 2, scale=fraction)
    if fraction <= 0:
        return floor, {**numbers, "reason": "the lower bound on its growth is not above zero"}
    target = (present_stake * Decimal(str(fraction))).quantize(CENT, rounding=ROUND_DOWN)
    return max(floor, min(target, ceiling)), {**numbers, "reason": basis}


def resize(house: Any, agent: Any) -> dict[str, Any] | None:
    """Move a rung-3 agent's stake toward what its record justifies. Returns what was done."""
    book = house.book_of(agent)
    if book is None or not book.real_money or house.evaluator.rung(agent.id) < 3:
        return None
    entered = house.evaluator._rung_entered(agent.id)
    growth = [float(r["log_growth"]) for r in house.evaluator._record_below(agent.id, 3)] + [
        float(r["log_growth"]) for r in house.evaluator.blocks(agent.id, since_seq=entered, book=book.name)
    ]
    account = book.account(agent.id)
    present = max(account.staked, Decimal(CONSTITUTION["rungs"]["2"]["stake_usd"]))
    target, numbers = kelly_stake(growth, present, book.venue_cash or ZERO, family_lcb=_family_lcb(house, agent, book))
    equity = book.equity(agent.id)
    delta = target - equity
    # Small moves are noise: act on a tenth of the stake or more. Shrinking never forces a sale:
    # only free cash comes back, and the position caps shrink with the stake at once.
    if abs(delta) < max(equity, Decimal(1)) / 10:
        return None
    if delta < 0:
        free = account.cash - book._reserved_cash(agent.id)
        delta = -min(-delta, max(free, ZERO))
        if delta == 0:
            return None
    book.stake(agent.id, delta, note="rung 3 sizing: " + numbers["reason"])
    from .book import Limits

    cap = Decimal(CONSTITUTION["order_caps"]["max_order_usd"])
    # A position must always be closable in ONE order under the gateway's cap, even after it has
    # appreciated by a quarter: so no position is opened above four fifths of the order cap.
    ceiling = (cap * Decimal("0.8")).quantize(CENT)
    book.limits[agent.id] = Limits(max_position_usd=min((target / 2).quantize(CENT), ceiling), max_order_usd=min(cap, (target / 2).quantize(CENT), ceiling))
    row = {"agent": agent.id, "book": book.name, "stake_usd": str(target), "moved_usd": str(delta), **numbers}
    house.ledger.append("eval.verdict", {"decision": "size", "rung": 3, **{k: v for k, v in row.items() if k != "agent"}}, agent=agent.id)
    return row


def _family_lcb(house: Any, agent: Any, book: Any) -> float | None:
    """The family's pooled lower bound today, for an agent that reached rung 3 on it."""
    promoted = [e.payload for e in house.ledger.iter(kinds="eval.verdict", agent=agent.id) if e.payload.get("decision") == "promote" and int(e.payload.get("to_rung") or 0) == 3]
    if not promoted or promoted[-1].get("via") != "family":
        return None
    members = [a.id for a in house.registry.agents.values() if a.family == agent.family and a.venue == agent.venue]
    series, _, _, counted = house.evaluator.family_record(members, book.name)
    if counted < int(CONSTITUTION["ladder"]["family"]["min_members"]):
        return None
    bounds = stats.mean_bounds(series, float(CONSTITUTION["ladder"]["family"]["alpha"]))
    return None if bounds is None else bounds["lcb"]


def recommend(house: Any, accounts: dict[str, Decimal] | None = None) -> dict[str, Any]:
    """The standing recommendation: where, on the evidence, the owner's next dollar belongs."""
    demand: dict[str, Decimal] = {"kalshi": ZERO, "alpaca": ZERO}
    ranked = []
    for agent in house.registry.living():
        rung = house.evaluator.rung(agent.id)
        if rung < 2:
            continue
        book = house.book_of(agent)
        if book is None or not book.real_money:
            continue
        entered = house.evaluator._rung_entered(agent.id)
        growth = [float(r["log_growth"]) for r in house.evaluator.blocks(agent.id, since_seq=entered, book=book.name)]
        account = book.account(agent.id)
        present = max(account.staked, Decimal(CONSTITUTION["rungs"]["2"]["stake_usd"]))
        target, numbers = kelly_stake(growth, present, Decimal("1e12"))  # what the evidence asks for, before the venue's cash binds
        if numbers.get("lcb") is not None and numbers["lcb"] > 0:
            demand[agent.venue] += target
            ranked.append({"agent": agent.id, "venue": agent.venue, "rung": rung, "lcb": numbers["lcb"], "blocks": numbers["blocks"], "justified_usd": str(target)})
    ranked.sort(key=lambda row: -row["lcb"])
    cash = {venue: Decimal(str((accounts or {}).get(venue, ZERO))) for venue in demand}
    share = Decimal(str(CONSTITUTION["rungs"]["3"]["max_share_of_venue"]))
    shortfall = {venue: max(demand[venue] - cash[venue] * share * max(len([r for r in ranked if r["venue"] == venue]), 1), ZERO) for venue in demand}
    if not ranked:
        summary = ("Add nothing yet. No agent has a real-money record with a lower bound on its growth above zero, so no "
                   "dollar has evidence behind it. The cash already at the venues is more than the micro-real rung can use.")
    else:
        best = max(shortfall, key=lambda v: shortfall[v])
        if shortfall[best] > 0:
            summary = (f"The evidence could use about ${shortfall[best]:.0f} more at {best.title()}: {len([r for r in ranked if r['venue'] == best])} "
                       f"agent(s) there have growth bounded above zero and are capped by the venue's cash. Strongest: {ranked[0]['agent']} "
                       f"(lower bound {ranked[0]['lcb']:+.5f} a block over {ranked[0]['blocks']} blocks).")
        else:
            summary = (f"Add nothing: the {len(ranked)} agent(s) with growth bounded above zero are fully funded by the cash already at their venues. "
                       f"Strongest: {ranked[0]['agent']} (lower bound {ranked[0]['lcb']:+.5f} a block).")
    row = {"summary": summary, "ranked": ranked[:10], "justified_usd": {k: str(v) for k, v in demand.items()},
           "venue_cash_usd": {k: str(v) for k, v in cash.items()}, "shortfall_usd": {k: str(v.quantize(CENT)) for k, v in shortfall.items()}}
    house.ledger.append("ops.recommendation", row)
    return row
