"""Rung 3 sizing, and the standing capital recommendation for the owner.

**Sizing.** An agent on rung 3 has real fills behind a lower confidence bound on its growth. Its
stake is `rungs.3.kelly_fraction` of Kelly on that LOWER bound, never on the point estimate: with
block returns of mean m and variance v on its present stake S, full Kelly would scale the stake by
m / v; the House uses fraction x m_lower / v, where m_lower is the one-sided lower bound the ladder
already computed. Since the owner's swing-and-bunt revision (Sept 23, 2026) the fraction is 1: full
Kelly on the lower bound, so the size of the swing follows the strength of the evidence. The result is clamped: never below the micro stake, never above a fixed share of the
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
    ladder = CONSTITUTION["ladder"]
    bounds = stats.mean_bounds(growth, alpha if alpha is not None else float(ladder.get("promotion_alpha", ladder["alpha"])))
    numbers: dict[str, Any] = {"blocks": len(growth), "floor_usd": str(floor), "ceiling_usd": str(ceiling)}
    if bounds is None or bounds["sd"] <= 0:
        return floor, {**numbers, "reason": "no bounded record yet"}
    share = float(rules["kelly_fraction"])
    label = "full Kelly" if share == 1 else f"{share:g} of Kelly"
    lcb, basis = bounds["lcb"], f"{label} on the lower bound"
    if lcb <= 0 and family_lcb is not None and family_lcb > 0 and bounds["mean"] > 0:
        lcb, basis = min(family_lcb, bounds["mean"]), f"{label} on its family's lower bound"
    fraction = stats.quarter_kelly(lcb, bounds["sd"] ** 2, fraction=share, cap=1e9)
    numbers.update(mean=bounds["mean"], lcb=bounds["lcb"], sized_on=lcb, variance=bounds["sd"] ** 2, scale=fraction)
    if fraction <= 0:
        return floor, {**numbers, "reason": "the lower bound on its growth is not above zero"}
    target = (present_stake * Decimal(str(fraction))).quantize(CENT, rounding=ROUND_DOWN)
    return max(floor, min(target, ceiling)), {**numbers, "reason": basis}


def scaled_limits(staked: Decimal) -> tuple[Decimal, Decimal]:
    """(max position, max order) for a rung-3 account lent `staked`: half the stake a position,
    and never more than can be closed in ONE order under the gateway's cap even after it has
    appreciated by a quarter (four fifths of the order cap). Never below the micro rung's."""
    micro = CONSTITUTION["rungs"]["2"]
    cap = Decimal(CONSTITUTION["order_caps"]["max_order_usd"])
    ceiling = (cap * Decimal("0.8")).quantize(CENT)
    half = (staked / 2).quantize(CENT)
    return max(Decimal(micro["max_position_usd"]), min(half, ceiling)), max(Decimal(micro["max_order_usd"]), min(cap, half, ceiling))


def _sizing_record(house, agent, book):
    """Keep the qualifying real record when promotion starts a fresh rung window."""
    entered = house.evaluator._rung_entered(agent.id)
    previous = house.evaluator._record_below(agent.id, 3) if house.evaluator.rung(agent.id) >= 3 else []
    growth = [float(r["log_growth"]) for r in previous] + [
        float(r["log_growth"]) for r in house.evaluator.blocks(agent.id, since_seq=entered, book=book.name)
    ]
    admissions = [e.payload for e in house.ledger.iter(kinds='eval.verdict', agent=agent.id)
                  if e.seq == entered and e.payload.get('decision') == 'promote' and e.payload.get('to_rung') == 3]
    admission = admissions[-1] if admissions else {}
    if admission.get('via') == 'completed_exposures':
        from .episodes import completed
        growth = [r['log_growth'] for r in completed(house.ledger, agent.id, book.name,
                                                   since_seq=int(admission['first_seq']) - 1)]
    return growth, admission.get('alpha_spent')


def resize(house: Any, agent: Any) -> dict[str, Any] | None:
    """Move a rung-3 agent's stake toward what its record justifies. Returns what was done."""
    book = house.book_of(agent)
    if book is None or not book.real_money or house.evaluator.rung(agent.id) < 3:
        return None
    growth, alpha = _sizing_record(house, agent, book)
    account = book.account(agent.id)
    present = max(account.staked, Decimal(CONSTITUTION["rungs"]["2"]["stake_usd"]))
    guard = getattr(house, 'campaigns', None)
    pilot = guard.live_authorization() if guard else None
    venue_cash = book.venue_cash or ZERO
    venue_caps = pilot['policy'].get('venue_capital_usd') if pilot else None
    if venue_caps:
        venue_cash = min(venue_cash, Decimal(venue_caps[agent.venue]) + max(house.tuition(agent.venue)['pnl_usd'], ZERO))
    target, numbers = kelly_stake(growth, present, venue_cash,
                                 alpha=alpha, family_lcb=_family_lcb(house, agent, book))
    equity = book.equity(agent.id)
    delta = target - equity
    if pilot:
        if not guard.allows_live(3):
            return None
        # Every promoted account stays inside the same experiment's risk envelope. A rung-3
        # label must not turn $25 of tuition into unrestricted venue capital.
        room = house.tuition()['headroom_usd']
        if venue_caps:
            room = min(room, house.tuition(agent.venue)['headroom_usd'])
        else:
            room = min(room, Decimal(pilot['policy']['max_stake_usd']) - account.staked)
        if delta > 0:
            delta = min(delta, max(room, ZERO))
            target = equity + delta
        numbers['live_authorization'] = pilot['id']
        if not venue_caps:
            numbers['pilot_max_stake_usd'] = pilot['policy']['max_stake_usd']
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
    house.seat(agent)  # the limits follow the stake
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
    guard = getattr(house, 'campaigns', None)
    pilot = guard.live_authorization() if guard else None
    for agent in house.registry.living():
        rung = house.evaluator.rung(agent.id)
        if rung < 2:
            continue
        book = house.book_of(agent)
        if book is None or not book.real_money:
            continue
        growth, alpha = _sizing_record(house, agent, book)
        account = book.account(agent.id)
        present = max(account.staked, Decimal(CONSTITUTION["rungs"]["2"]["stake_usd"]))
        target, numbers = kelly_stake(growth, present, Decimal("1e12"), alpha=alpha)  # before venue cash binds
        if pilot:
            ceiling = (pilot['policy']['venue_capital_usd'][agent.venue] if pilot['policy'].get('venue_capital_usd')
                       else pilot['policy']['max_stake_usd'])
            target = min(target, Decimal(ceiling))
        if numbers.get("lcb") is not None and numbers["lcb"] > 0:
            demand[agent.venue] += target
            ranked.append({"agent": agent.id, "venue": agent.venue, "rung": rung, "lcb": numbers["lcb"], "blocks": numbers["blocks"], "justified_usd": str(target)})
    ranked.sort(key=lambda row: -row["lcb"])
    cash = {venue: Decimal(str((accounts or {}).get(venue, ZERO))) for venue in demand}
    share = Decimal(str(CONSTITUTION["rungs"]["3"]["max_share_of_venue"]))
    shortfall = {venue: max(demand[venue] - cash[venue] * share * max(len([r for r in ranked if r["venue"] == venue]), 1), ZERO) for venue in demand}
    if pilot:
        shortfall = {venue: ZERO for venue in demand}
        summary = (f"The owner allocated ${pilot['policy']['max_loss_usd']} across the live venues. "
                   "Performance earns sizing within that allocation; losses remain recorded and deposits do not enlarge it."
                   if pilot['policy'].get('venue_capital_usd') else
                   f"Add nothing for this live-learning window. Its ${pilot['policy']['max_loss_usd']} aggregate risk envelope "
                   f"and ${pilot['policy']['max_stake_usd']} per-agent capital limit remain binding after promotion. "
                   "Research evidence cannot authorize an expanded financial experiment.")
    elif not ranked:
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


def top_up_micro(house: Any, agent: Any) -> dict[str, Any] | None:
    """Raise a rung-2 agent's stake to the constitution's micro stake when that rose after it was
    seated (the learning surge of Sept 21, 2026: $25 -> $60), inside the owner's capital headroom.
    Never on a swept, abandoned or losing-below-stake account; never more than the difference."""
    book = house.book_of(agent)
    if book is None or not book.real_money or house.evaluator.rung(agent.id) != 2:
        return None
    account = book.account(agent.id)
    target = Decimal(CONSTITUTION["rungs"]["2"]["stake_usd"])
    if not account.funded or account.swept or account.staked >= target or book.equity(agent.id) < account.staked:
        return None
    delta = target - account.staked
    headroom = Decimal(str(house.tuition(agent.venue)["headroom_usd"]))
    if headroom < delta:
        return None
    book.stake(agent.id, delta, note=f"micro stake raised to ${target} (learning surge)")
    house.seat(agent)  # the limits follow the stake
    row = {"agent": agent.id, "book": book.name, "stake_usd": str(target), "moved_usd": str(delta), "reason": "micro stake raised to the constitution's"}
    house.ledger.append("eval.verdict", {"decision": "size", "rung": 2, **{k: v for k, v in row.items() if k != "agent"}}, agent=agent.id)
    return row
