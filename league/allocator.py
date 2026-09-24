"""The allocator: capital is the ladder (the owner's direction of Sept 23, 2026).

An agent's rank is its capital, and its capital moves with its evidence at every mark pass,
around the clock, with no calendar gates:

    "I deeply want to speed up the dynamism of agents moving up and down the levels of the game as
    quickly as possible and aggressively aligned on incentives so star traders can compound and run
    wild and profit exponentially and losing agents die off"

**Evidence is wealth.** An agent's paper purse is traded under conservative fills with fees, so its
wealth multiple W is an anytime-valid e-value against "no edge after fees": by Ville's inequality
an edgeless strategy reaches W >= 1/alpha with probability at most alpha, however it sizes or times
its bets. So there are no looks, no blocks and no calendars here, and sizing is the agent's own
choice -- a big swing with an edge compounds evidence fastest, and one without an edge ends in
death.

- `W_paper`: the agent's wealth multiple on its paper book, stakes lent or returned taken out, the
  block in progress included (`Evaluator.wealth`). Alpaca's paper fills looked optimistic on Sept
  22 (haghani +7.4% on paper against negative replays), so a conservative execution haircut of
  `evidence.alpaca_paper_haircut_bps` per side of filled notional is taken off `alpaca-paper`, at
  the rate of each fill's asset class (A8, Sept 23, 2026: each class's own measured optimism).
  The Kalshi shadow book already fills conservatively and is not haircut.
- `W_real`: the same on its real book since its first real dollar. A real record is never reset by
  a promotion or a sweep.
- `E = W_paper ** paper_weight * W_real`: paper counts as its square root, and real results
  dominate as they accrue.

**Bands** are computed, not gated; they map onto the rungs so the grant, the books, publishing and
death keep working:

| Band   | Rung | Entry                                                              | Stake |
|--------|------|--------------------------------------------------------------------|-------|
| replay | 0    | new code                                                           | none |
| paper  | 1    | passed replay                                                      | the paper purse |
| bunt   | 2    | E >= bunt_at and enough closed (or, on event books, settled) trades | bunt_usd per venue |
| swing  | 3    | E >= swing_at, W_real >= 1 and enough REAL closed trades; the first entry is audited | bunt_usd x min(E, e_cap)^kappa, up to max_share_of_venue |
| star   | 3    | the top `stars` swing agents by real P&L with W_real >= star_min_w_real | the swing stake |

Down: hysteresis (leave a band below `hysteresis` x its entry), a real drawdown of
`real_drawdown_demote` from the real high-water mark sends an agent back to paper at once, and an
agent whose paper wealth is below `die_below` after `die_min_trades` closed trades dies (paper death
and statistical death stay). The envelope is the grant's per-venue capital plus realized profit at
that venue (profit-indexed; losses count in full); when it cannot seat every eligible agent, the
best E is seated first and a newcomer with higher E displaces the weakest flat bunt. If the floor's
real P&L since the grant falls below `throttle.halve_below` of the envelope every real stake is
halved until it recovers above `throttle.restore_above`. Stake changes under `min_stake_change` are
ignored, and shrinking never forces a sale: only free cash comes back.

A performance fee in compute: `performance_fee_share` of every realized real profit (a settlement or
a sell) is granted to the agent as compute credits, once per settlement or fill (ledger ids).

This module is a money judge: `league/ci.py` forbids Merton's pull requests to touch it.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import threading
from dataclasses import asdict, dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import families
from .constitution import CONSTITUTION
from .ledger import HOUSE, now_iso

ZERO = Decimal(0)
CENT = Decimal("0.01")
#: A PROBE (Sept 24, 2026) is rung 2 staked `probe_bunt_usd`, for an agent whose family has not proven its
#: mechanism; a member of a proven family is a bunt. A first-class band: the board's rows and summary and
#: the verdicts' `band_from`/`band_to` say it, and the publisher (#222) and the site (personal-site #6)
#: know it. Only the rung and the book's daily-loss rule (`band_of`) read "bunt" for both.
BANDS = ("replay", "paper", "probe", "bunt", "swing", "star")
RUNG_OF = {"replay": 0, "paper": 1, "probe": 2, "bunt": 2, "swing": 3, "star": 3}
PAPER_BOOK = {"alpaca": "alpaca-paper", "kalshi": "kalshi-shadow"}
REAL_BOOK = {"alpaca": "alpaca", "kalshi": "kalshi"}
EVENT_BOOKS = ("kalshi-shadow", "kalshi")
MAX_MOVES = 50
#: The mechanism ledger's states in the order of their proof (C2, Sept 24, 2026): a newcomer never displaces a
#: member of a family whose state ranks above its own family's.
STATE_RANK = {"unproven": 0, "proven": 1, "swing": 2}
#: Whether `Book` slices a reducing order larger than the gateway's order cap. Since Workstream C
#: (PR #164, Sept 23, 2026) it does, so a position follows its stake past one order's size; before,
#: no position could exceed four fifths of the cap, exactly as `capital.scaled_limits` held rung 3.
EXITS_SLICED = True


def rules(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return dict((constitution or CONSTITUTION).get("allocator") or {})


def enabled(constitution: Mapping[str, Any] | None = None) -> bool:
    return bool(rules(constitution).get("enabled"))


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def band_of_rung(rung: int) -> str:
    return ("replay", "paper", "bunt", "swing")[max(0, min(int(rung), 3))]


# ------------------------------------------------------------------ evidence
@dataclass
class Evidence:
    agent: str
    venue: str
    rung: int
    w_paper: float
    w_real: float
    e: float
    paper_trades: int
    paper_settled: int
    real_trades: int
    real_pnl: float  # equity less staked on the real book: what the agent has made or lost there
    real_drawdown: float  # of the real wealth index from its high-water mark, 0..1
    haircut_log: float  # the log wealth taken off the paper record by the execution haircut
    real_seen: bool  # the agent has ever had a real account
    cooling: bool = False  # demoted within `reentry_cooldown_hours`: no move up until it passes
    #: Independent real results in the current stay on real money (P2, Sept 24, 2026): settled or
    #: sold-flat events on Kalshi, closed trades on Alpaca, since `real_stay_start`. The hysteresis exit
    #: waits for `hysteresis_after_settled` of them.
    real_stay_closed: int = 0
    #: Whether the agent's family's pooled record is proven (`Allocator.family`), set by the pass before
    #: any band is read. Only a proven family's agent swings (Sept 24, 2026: every real-money agent is a
    #: probe or a proven family's member). None where no pass set it: no family gate.
    family_proven: bool | None = None

    def row(self) -> dict[str, Any]:
        return {"W_paper": round(self.w_paper, 6), "W_real": round(self.w_real, 6), "E": round(self.e, 6),
                "trades": int(self.paper_trades), "settled": int(self.paper_settled),
                "real_trades": int(self.real_trades), "real_pnl": round(self.real_pnl, 4),
                "real_drawdown": round(self.real_drawdown, 4), "stay_closed": int(self.real_stay_closed)}


def _haircut_rate(bps: Any, asset_class: Any) -> float:
    """The haircut in bps a side for one fill: a plain number charges every class (the form before A8,
    kept for rollback); a table charges the fill's asset class, and a class the table does not name
    pays the table's largest rate, never nothing (evidence honesty: an unmeasured class is not
    assumed to fill at the quote)."""
    if isinstance(bps, Mapping):
        rates = [float(v) for v in bps.values()]
        return float(bps[asset_class]) if asset_class in bps else max(rates, default=0.0)
    return float(bps or 0)


def _paper_haircut(house: Any, agent: str, book_name: str, bps: Any) -> float:
    """The execution haircut on a paper record, in log wealth: `bps` of every filled notional (each
    side) since the evidence cutoff, each over the stake of the stay it was traded in (a sweep ends a
    stay; the next stake begins one), so each stay pays for its own trading and an evidence cutoff
    never zeroes it (Sept 23, 2026 review: the old base, every dollar lent since the cutoff, was 0
    after a repair and diluted across re-seats). `bps` is a number for every class or, since A8
    (Sept 23, 2026), a table by the fill's instrument's asset class (`_haircut_rate`)."""
    if (max((float(v) for v in bps.values()), default=0.0) if isinstance(bps, Mapping) else float(bps or 0)) <= 0:
        return 0.0
    from .accounting import evidence_cutoffs

    cutoff = evidence_cutoffs(house.ledger, agent).get(book_name, 0)
    base, closed, total = 0.0, True, 0.0
    for entry in house.ledger.iter(kinds=("book.fill", "book.stake"), agent=agent):
        p = entry.payload
        if p.get("book") != book_name:
            continue
        if entry.kind == "book.stake":
            usd = float(p.get("usd") or 0)
            if usd > 0:
                base, closed = (usd, False) if closed else (base + usd, False)
            elif usd < 0:
                closed = True  # a sweep: the next stake starts a new stay
            continue
        if entry.seq <= cutoff or p.get("source") not in ("venue", "cross"):
            continue
        instrument = p.get("instrument") or {}
        try:
            multiplier = float(instrument.get("multiplier") or 1)
            notional = abs(float(p["quantity"]) * float(p["price"]) * multiplier)
        except (KeyError, TypeError, ValueError):
            continue
        total += notional * _haircut_rate(bps, instrument.get("asset_class")) / 10_000.0 / max(base, 1.0)
    return min(total, 5.0)


def closed_trades(house: Any, agent: str, book_name: str, *, since_seq: int = 0) -> tuple[int, int]:
    """(closed trades, settlements) on one book since its evidence cutoff (and after `since_seq`):
    every settlement, and every sale that left the position flat, counted as `Evaluator.trade_returns`
    counts them, but never dropped because the net stake is zero or less after sweeps (Sept 23, 2026
    review).

    INDEPENDENT on the event books (D4, the close-the-gaps run, Sept 24, 2026): under the constitution's
    `independent_settlements: "event"` each counts once per distinct EVENT (`evaluator.event_key`), so
    three strikes of one game that all settle are one settlement and one closed trade, and a flat sale
    counts toward its event the same way. meriwether-h7d7702 reached the bunt line "on 6 closed trades"
    at 00:39:48Z Sept 24 that were two games. Alpaca books count every closed trade. W is unchanged."""
    from .accounting import evidence_cutoffs
    from .evaluator import count_key, per_event

    cutoff = max(evidence_cutoffs(house.ledger, agent).get(book_name, 0), int(since_seq or 0))
    by_event = per_event(book_name)
    closed: set[str] = set()
    settled: set[str] = set()
    for entry in house.ledger.iter(kinds=("book.fill", "book.settle"), agent=agent, after=cutoff):
        p = entry.payload
        if p.get("book") != book_name:
            continue
        if entry.kind == "book.settle":
            key = count_key(entry.seq, p, by_event)
            closed.add(key)
            settled.add(key)
        elif p.get("realized") is not None and p.get("source") != "dust" and p.get("flat", True):
            closed.add(count_key(entry.seq, p, by_event))
    return len(closed), len(settled)


# ------------------------------------------------------------ the family record
# The family record lives in `league/families.py` since C1 (the close-the-gaps run's Deploy B, Sept 24,
# 2026): the mechanism ledger, the one source the allocator, the board, the House's births, the foundry and
# the lab read. These names stay for every caller and every test that patches them (`Allocator.family`
# calls this module's `family_record`, so patching `allocator.family_record` still stands in for it).
TAPE_KINDS = families.TAPE_KINDS
TapeRow = families.TapeRow
TradeTape = families.TradeTape
_log1p = families.log1p
_practice_charges = families.practice_charges


def _family_rule(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return families.proof_rule(constitution)


def _pool(groups: Mapping[str, list[tuple[float, float]]], min_n: int, confidence: float, *,
          win_rate: float | None = None, risk: float = 1.0) -> dict[str, Any]:
    return families.pool(groups, min_n, confidence, win_rate=win_rate, risk=risk)


def family_record(house: Any, family: str, venue: str, *, tape: TradeTape | None = None,
                  through: int | None = None, **kwargs: Any) -> dict[str, Any]:
    """A family's pooled forward record: `families.family_record`."""
    return families.family_record(house, family, venue, tape=tape, through=through, **kwargs)


def real_stay_start(house: Any, agent: str) -> int | None:
    """The ledger position where the agent's current stay on real money began (its last promotion
    from paper), or None when it is not on real money."""
    rows = house.ledger.read(kinds="eval.verdict", agent=agent, limit=10_000, newest=True)
    for entry in reversed(rows):
        p = entry.payload
        if p.get("decision") in ("promote", "demote", "seat") and int(p.get("to_rung") or 0) <= 1:
            return None
        if p.get("decision") in ("promote", "seat") and int(p.get("to_rung") or 0) == 2 and int(p.get("from_rung") or 0) <= 1:
            return entry.seq
    return None


def left_real_at(house: Any, agent: str) -> float | None:
    """When the agent was last demoted -- by the allocator, drift, an audit veto or the envelope --
    in epoch seconds, or None. Any demotion starts the re-entry cooldown, so a band that was just
    taken away is not handed straight back in the same or the next pass (Sept 23, 2026 review)."""
    from ltcm.broker import instant

    rows = house.ledger.read(kinds="eval.verdict", agent=agent, limit=10_000, newest=True)
    for entry in reversed(rows):
        p = entry.payload
        if p.get("decision") == "demote":
            parsed = instant(entry.at)
            return parsed.timestamp() if parsed else None
    return None


def audit_standing(house: Any, agent: Any) -> str:
    """"approved" when the latest real audit verdict on the agent's CURRENT code approved it,
    "vetoed" when it refused, "none" when there is none (errors are not verdicts; a verdict from
    before the agent last adopted code does not speak for the code it runs now). A family swing's
    verdict (`family_swing` on the row) is its FAMILY's, written against one member: it judged the
    family's stake, never this agent's own promotion (review of #242, Sept 24, 2026: the member it was
    written against took the agent-level swing, up to 60% of the venue, on its family's approval)."""
    adopted = house.ledger.last("agent.strategy", agent=agent.id)
    since = adopted.seq if adopted is not None else 0
    latest = None
    for entry in house.ledger.iter(kinds="audit.verdict", agent=agent.id, after=since):
        if not entry.payload.get("error") and not entry.payload.get("family_swing"):
            latest = entry.payload
    if latest is None:
        return "none"
    return "approved" if latest.get("approve") else "vetoed"


def evidence(house: Any, agent: Any, rung: int | None = None) -> Evidence:
    """The agent's evidence now, from the ledger and its books (read-only)."""
    r = rules()
    weights = r.get("evidence") or {}
    ev = house.evaluator
    rung = ev.rung(agent.id) if rung is None else rung
    paper_name, real_name = PAPER_BOOK[agent.venue], REAL_BOOK[agent.venue]
    # Evidence does not depend on the rung the agent stands on: both records are read in full,
    # blocks in progress included (Sept 23, 2026 review: reading the real record only while on real
    # money let a demoted bunt's unfinished loss vanish, and it was re-bunted every other pass).
    # The drawdown that demotes is the current real stay's, from where that stay began.
    stay = real_stay_start(house, agent.id) if rung >= 2 else None
    paper = ev.wealth(agent.id, paper_name, agent.horizon, current=True)
    real = ev.wealth(agent.id, real_name, agent.horizon, current=True, drawdown_since=stay if stay is not None else None)
    haircut = _paper_haircut(house, agent.id, paper_name, weights.get("alpaca_paper_haircut_bps", 0)) \
        if paper_name == "alpaca-paper" else 0.0
    w_paper = math.exp(max(min(paper["log"] - haircut, 50.0), -50.0))
    w_real = math.exp(max(min(real["log"], 50.0), -50.0))
    e = (w_paper ** float(weights.get("paper_weight", 0.5))) * w_real
    paper_closed, settled = closed_trades(house, agent.id, paper_name)
    real_closed, _ = closed_trades(house, agent.id, real_name)
    stay_closed = closed_trades(house, agent.id, real_name, since_seq=stay)[0] if stay is not None else 0
    left = left_real_at(house, agent.id)
    hours = float(r.get("reentry_cooldown_hours", 1.0))
    cooling = rung in (1, 2) and left is not None and house.clock() - left < hours * 3600
    real_book = house.books.get(real_name)
    real_pnl, seen = 0.0, False
    if real_book is not None and agent.id in real_book.accounts:
        account = real_book.account(agent.id)
        seen = bool(account.funded)
        real_pnl = float(real_book.equity(agent.id) - account.staked)
    return Evidence(agent=agent.id, venue=agent.venue, rung=rung, w_paper=w_paper, w_real=w_real, e=e,
                    paper_trades=paper_closed, paper_settled=settled if paper_name in EVENT_BOOKS else 0, real_trades=real_closed,
                    real_pnl=real_pnl, real_drawdown=real["drawdown"] if stay is not None else 0.0, haircut_log=haircut,
                    real_seen=seen, cooling=cooling, real_stay_closed=stay_closed)


# --------------------------------------------------------------------- bands
def _params() -> dict[str, Any]:
    r = rules()
    return {
        "bunt_at": float(r.get("bunt_at", 1.03)), "bunt_min_trades": int(r.get("bunt_min_trades", 5)),
        "bunt_min_settled": int(r.get("bunt_min_settled", 3)),
        "swing_at": float(r.get("swing_at", 1.5)), "swing_min_real_trades": int(r.get("swing_min_real_trades", 8)),
        "swing_min_w_real": float(r.get("swing_min_w_real", 1.0)), "swing_exit_w_real": float(r.get("swing_exit_w_real", 0.9)),
        "hysteresis": float(r.get("hysteresis", 0.85)), "real_drawdown_demote": float(r.get("real_drawdown_demote", 0.35)),
        "die_below": float(r.get("die_below", 0.80)), "die_min_trades": int(r.get("die_min_trades", 10)),
        "stars": int(r.get("stars", 3)), "star_min_w_real": float(r.get("star_min_w_real", 1.25)),
        "kappa": float(r.get("kappa", 1.0)), "e_cap": float(r.get("e_cap", 20)),
        "max_share_of_venue": float(r.get("max_share_of_venue", 0.6)), "position_share": float(r.get("position_share", 0.5)),
        "min_stake_change": float(r.get("min_stake_change", 0.10)),
        "performance_fee_share": float(r.get("performance_fee_share", 0.2)),
        "throttle": dict(r.get("throttle") or {"halve_below": -0.30, "restore_above": -0.15}),
        "bunt_usd": {k: _d(v) for k, v in (r.get("bunt_usd") or {"kalshi": "10", "alpaca": "15"}).items()},
        # The close-the-gaps run (Sept 24, 2026): an unproven family's first real stake is a probe, the
        # hysteresis exit waits for a few real settlements, and an event book's position is a fifth.
        # Without the keys every bunt is `bunt_usd`, the exit applies at once, and a Kalshi position's
        # share is `position_share`, as on every other book.
        "probe_bunt_usd": {k: _d(v) for k, v in (r.get("probe_bunt_usd") or r.get("bunt_usd") or {"kalshi": "10", "alpaca": "15"}).items()},
        "hysteresis_after_settled": int(r.get("hysteresis_after_settled") or 0),
        "position_share_event": float(r.get("position_share_event") or r.get("position_share", 0.5)),
        "profit_indexed_envelope": bool(r.get("profit_indexed_envelope", True)),
        # The learn-and-unblock run (Sept 23, 2026 ~16:00 UTC): a bunt keeps what it makes, and an
        # options bunt is staked one affordable contract. See the constitution for the evidence.
        "bunt_growth": str(r.get("bunt_growth") or "flat"),
        "option_bunt_usd": _d(r.get("option_bunt_usd") or CONSTITUTION["rungs"]["2"]["option_max_position_usd"]),
    }


def bunt_ready(ev: Evidence, p: Mapping[str, Any]) -> bool:
    """Paper -> bunt: E at or above `bunt_at` on enough closed trades (or, on an event book, enough
    settlements: a settlement is the market's verdict)."""
    enough = ev.paper_trades >= p["bunt_min_trades"] or (ev.venue == "kalshi" and ev.paper_settled >= p["bunt_min_settled"])
    return enough and ev.e >= p["bunt_at"]


def swing_ready(ev: Evidence, p: Mapping[str, Any]) -> bool:
    return ev.e >= p["swing_at"] and ev.w_real >= p["swing_min_w_real"] and ev.real_trades >= p["swing_min_real_trades"]


def target_band(ev: Evidence, p: Mapping[str, Any]) -> tuple[str, str]:
    """(the band the evidence asks for, why), before the envelope and the audit have their say."""
    rung = ev.rung
    if rung <= 0:
        return "replay", "judged by replay"
    if rung == 1:
        if ev.cooling:
            return "paper", "back from real money within the re-entry cooldown"
        if bunt_ready(ev, p):
            from .evaluator import per_event

            counted = f"{ev.paper_trades} closed trades" + (f" ({ev.paper_settled} settled)" if ev.venue == "kalshi" else "")
            if per_event(PAPER_BOOK.get(ev.venue, "")):
                counted += ", one an event"  # D4 (Sept 24, 2026): stacked strikes on one game are one bet
            return "bunt", f"E {ev.e:.4f} is at or above {p['bunt_at']:g} on {counted}"
        return "paper", "E below the bunt line or too few trades"
    if ev.real_drawdown >= p["real_drawdown_demote"]:
        return "paper", f"down {ev.real_drawdown:.0%} of its real record from its high-water mark: back to paper at once"
    line = p["bunt_at"] * p["hysteresis"]
    if ev.e < line:
        if ev.real_stay_closed >= p["hysteresis_after_settled"]:
            return "paper", f"E {ev.e:.4f} fell below {line:.4f} (the bunt line with hysteresis)"
        # The one-loss trial (P2, Sept 24, 2026): the exit waits for `hysteresis_after_settled` independent
        # real results in this stay. A $30 bunt could hold a $15 position and one lost position over ~15%
        # of the stake took E under the line: 4 of the allocator's nine promotions were demoted after one
        # loss. Until then only the stay drawdown (above) and death apply; a swing still drops to a bunt
        # at its own floor (below).
        if rung == 2:
            return "bunt", (f"E {ev.e:.4f} is under the exit line {line:.4f}, which applies after "
                            f"{p['hysteresis_after_settled']} real settlements in this stay ({ev.real_stay_closed} so far): "
                            "one early loss is not a demotion")
    if rung == 2:
        if swing_ready(ev, p) and not ev.cooling:
            if ev.family_proven is False:
                # The agent-level swing is the second route for a PROVEN family's agent only (the close-
                # the-gaps run, Sept 24, 2026): an unproven family's agent stays a probe, whatever its
                # own E on a few real settlements says (the plan's gap 2).
                return "bunt", (f"E {ev.e:.4f} is at or above {p['swing_at']:g}, but its family's pooled record is not "
                                "proven: only a proven family's agent swings")
            return "swing", (f"E {ev.e:.4f} is at or above {p['swing_at']:g}, W_real {ev.w_real:.4f}, "
                             f"{ev.real_trades} real closed trades")
        return "bunt", "holds the bunt band"
    if ev.family_proven is False:
        return "bunt", "its family's pooled record is no longer proven: an unproven family's agent is a probe, not a swing"
    if ev.e < p["swing_at"] * p["hysteresis"] or ev.w_real < p["swing_exit_w_real"]:
        return "bunt", (f"E {ev.e:.4f} or W_real {ev.w_real:.4f} fell below the swing band's floor "
                        f"({p['swing_at'] * p['hysteresis']:.4f} / {p['swing_exit_w_real']:g})")
    return "swing", "holds the swing band"


def bunt_stake(ev: Evidence | None, base: Decimal, p: Mapping[str, Any]) -> Decimal:
    """A bunt's target stake. Under `bunt_growth: "w_real"` it is `base x clamp(W_real, 1, swing_at)`:
    a bunt keeps what it makes, up to the swing line, and what it loses comes off its stake (`_size`
    never tops a bunt with W_real under 1 back up). Without evidence in hand -- the stake at seating,
    an unfunded seat counted at risk -- or under `"flat"`, it is `base` (Sept 23, 2026: the flat rule
    had swept mullins-2, the floor's best real record at W_real 1.158, down to a $5.11 stake)."""
    if ev is None or p["bunt_growth"] != "w_real":
        return base
    scale = min(max(float(ev.w_real), 1.0), float(p["swing_at"]))
    if scale <= 1.0:
        return base
    return (base * _d(round(scale, 6))).quantize(CENT, rounding=ROUND_DOWN)


def swing_stake(ev: Evidence, venue_capital: Decimal, p: Mapping[str, Any]) -> Decimal:
    base = p["bunt_usd"][ev.venue]
    scale = min(max(ev.e, 1.0), p["e_cap"]) ** p["kappa"]
    stake = (base * _d(round(scale, 6))).quantize(CENT, rounding=ROUND_DOWN)
    ceiling = (venue_capital * _d(p["max_share_of_venue"])).quantize(CENT, rounding=ROUND_DOWN)
    return max(base, min(stake, ceiling))


def _position_share(venue: str, p: Mapping[str, Any]) -> float:
    """The share of a real stake one position may hold: `position_share_event` on an event book (P2,
    Sept 24, 2026: a fifth, so one binary miss stays inside the stay drawdown), `position_share` else."""
    return float(p["position_share_event"] if REAL_BOOK.get(venue) in EVENT_BOOKS else p["position_share"])


def limits_for(stake: Decimal, venue: str, *, order_cap: Decimal | None = None) -> tuple[Decimal, Decimal]:
    """(max position, max order) for a real account staked `stake`: `position_share` of the stake
    (`position_share_event` on Kalshi since Sept 24, 2026: $6 of a $30 bunt, $2 of a $10 probe), never
    under the venue's minimum order x 1.2 (Alpaca crypto takes nothing under $10), and every order
    within the gateway's per-order cap."""
    p = _params()
    share = _position_share(venue, p)
    cap = order_cap if order_cap is not None else _d(CONSTITUTION["order_caps"]["max_order_usd"])
    if order_cap is None and venue == "alpaca":
        # The gateway counts an Alpaca market order at the touch plus ten per cent
        # (`book.GATEWAY_MARKET_MARKUP`): an entry over $68.18 at the ask is over its $75 cap.
        from .book import GATEWAY_MARKET_MARKUP

        cap = (cap / GATEWAY_MARKET_MARKUP).quantize(CENT, rounding=ROUND_DOWN)
    # A fifth above the venue's minimum: a minimum-sized order must still fit after its fee and a
    # price-grid step (Alpaca takes no crypto order under $10; a $15 bunt must be able to place one).
    minimum = (_d((rules().get("venue_minimum_usd") or {}).get(venue, "1")) * _d("1.2")).quantize(CENT)
    position = max((stake * _d(share)).quantize(CENT, rounding=ROUND_DOWN), minimum)
    if not EXITS_SLICED:
        position = min(position, (cap * _d("0.8")).quantize(CENT))
    order = max(min(position, cap), minimum)
    return position, order


# -------------------------------------------------------------------- state
class Allocator:
    """The House's allocator. `rebalance()` runs in the mark pass under the House's lifecycle lock."""

    def __init__(self, house: Any, root: str | Path):
        self.house = house
        self.path = Path(root) / "allocator.json"
        self._lock = threading.RLock()
        self._board: dict[str, Any] = {"enabled": enabled(), "agents": {}, "moves": [], "bands": {}, "throttle": {}}
        self.state = self._load()
        self._evidence: dict[str, Evidence] = {}
        #: The family records of this pass (P1, Sept 24, 2026), each computed once a pass from `_tape`
        #: read through `_through`, the pass's ledger position; readers between passes (the book's
        #: `family_taker`) see the last pass's. Since C1 (Deploy B) each carries its state in the mechanism
        #: ledger ("unproven", "proven" or "swing", `league/families.py`) with its `since`, and a swinging
        #: family its stake (`swing`).
        self._tape = TradeTape()
        self._families: dict[tuple[str, str], dict[str, Any]] = {}
        self._through: int | None = None
        self._family_alerted: set[tuple[str, str, str]] = set()  # (family, venue, error): each told once
        self._rungs: dict[str, int] | None = None  # the pass's rungs while `_begin_pass` reads the families
        self._released: bool | None = None  # whether the live grant releases rung 3, read once a pass (`_swing_released`)
        if self.state.get("families") is None:
            # A first start under the mechanism ledger: the states the ledger's last `family.record` rows say.
            self.state["families"] = families.restore_states(getattr(house, "ledger", None))

    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        state.setdefault("throttle", False)
        state.setdefault("fee_cursor", None)
        state.setdefault("last_board_at", 0.0)
        # The mechanism ledger (C1, Sept 24, 2026): each family's state and since, its swing's entry and
        # audit ("families"); the digest of each family's last `family.record` row and when rows were last
        # written ("family_rows", "family_rows_at"), so a restart writes only what changed.
        state.setdefault("family_rows", {})
        state.setdefault("family_rows_at", 0.0)
        return state

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        with self._lock:  # a family swing's audit writes its verdict into the state from the audit lane
            text = json.dumps(self.state, sort_keys=True)
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.path)

    # ------------------------------------------------------------ envelope
    def grant(self) -> dict[str, Any] | None:
        guard = getattr(self.house, "campaigns", None)
        return guard.live_authorization() if guard else None

    def grant_capital(self, venue: str | None = None) -> Decimal:
        grant = self.grant()
        caps = (grant or {}).get("policy", {}).get("venue_capital_usd") or {}
        if venue is not None and venue in caps:
            return _d(caps[venue])
        if grant:
            return sum((_d(v) for v in caps.values()), ZERO) if caps else _d(grant["policy"]["max_loss_usd"])
        return _d(CONSTITUTION["tuition"]["max_loss_usd"])

    def realized(self, venue: str) -> Decimal:
        """Realized real P&L at a venue: every real account's realized result (settlements and
        sells), losses included."""
        book = self.house.books.get(REAL_BOOK[venue])
        if book is None:
            return ZERO
        return sum((book.account(a).realized for a in book.agents()), ZERO)

    def capital(self, venue: str) -> Decimal:
        """The venue's envelope: the grant's capital, plus realized profit there (E2: stars'
        compounding is not capped at the starting envelope; losses still count in full)."""
        base = self.grant_capital(venue)
        if _params()["profit_indexed_envelope"]:
            base += max(self.realized(venue), ZERO)
        return base

    def at_risk(self, venue: str, *, exclude: str | None = None) -> Decimal:
        """What the real accounts at a venue can still lose: a seated account's spendable cash and
        what its holdings cost; a seat promoted but not yet funded, its target stake; any other
        account, what its holdings cost, and its cash too while it has a resting buy. (Sept 23, 2026
        review: counting a seated account's net loan left out profit it still held, and a returned
        profit or an unfunded seat opened room that was not there.)"""
        house = self.house
        book = house.books.get(REAL_BOOK[venue])
        if book is None:
            return ZERO
        total = ZERO
        seen: set[str] = set()
        for agent_id in book.agents():
            seen.add(agent_id)
            if agent_id == exclude:
                continue
            account = book.account(agent_id)
            held = sum((h.cost for h in account.holdings.values()), ZERO)
            agent = house.registry.get(agent_id)
            seated = agent is not None and agent.alive and house.evaluator.rung(agent_id) >= 2
            if seated:
                total += max(account.cash, ZERO) + held
                if not account.funded or (account.swept and not account.holdings):
                    # Its stake is owed and will be lent: exactly what `House.seat` lends (`seat_stake`:
                    # a bunt's base x W_real on a re-seat, a swing's stake on rung 3), not the flat base
                    # (review of #198, Sept 23, 2026: a $30 re-seat was reserved $25).
                    total += self.seat_stake(agent)
            else:
                buying = any(w.side == "buy" for w in book.open_orders(agent_id))
                total += held + (max(account.cash, ZERO) if buying else ZERO)
        for agent in house.registry.living():
            # Seated on the real rung without an account on the book yet (its stake failed): reserved.
            if agent.venue == venue and agent.id not in seen and agent.id != exclude and house.evaluator.rung(agent.id) >= 2:
                total += self.seat_stake(agent)
        return total

    def headroom(self, venue: str, *, exclude: str | None = None) -> Decimal:
        """What may still be put at risk at a venue: the grant's capital, plus realized results there
        (profit only while the envelope is profit-indexed; losses always), less what is at risk."""
        realized = self.realized(venue)
        if not _params()["profit_indexed_envelope"]:
            realized = min(realized, ZERO)
        return self.grant_capital(venue) + realized - self.at_risk(venue, exclude=exclude)

    def committed(self, venue: str) -> Decimal:
        """The envelope in use: the profit-indexed capital less the headroom (at risk plus realized losses)."""
        return self.capital(venue) - self.headroom(venue)

    def can_fund(self, venue: str, stake: Decimal) -> bool:
        """Whether the real book would accept a new stake of this size now (`Book.stake` refuses one
        over the venue's cash less what is already lent)."""
        book = self.house.books.get(REAL_BOOK[venue])
        if book is None or book.venue_cash is None:
            return False
        lent = sum((book.account(a).staked for a in book.agents()), ZERO)
        return lent + stake <= book.venue_cash

    def floor_pnl(self) -> Decimal:
        total = ZERO
        for venue in REAL_BOOK:
            book = self.house.books.get(REAL_BOOK[venue])
            if book is None:
                continue
            for agent_id in book.agents():
                total += book.equity(agent_id) - book.account(agent_id).staked
        return total

    def _throttle(self) -> bool:
        p = _params()["throttle"]
        envelope = sum((self.grant_capital(v) for v in REAL_BOOK if self.house.books.get(REAL_BOOK[v]) is not None), ZERO)
        if envelope <= 0:
            return False
        ratio = float(self.floor_pnl() / envelope)
        before = bool(self.state.get("throttle"))
        now = ratio < float(p["halve_below"]) or (before and ratio < float(p["restore_above"]))
        if now != before:
            self.state["throttle"] = now
            self.house.ledger.append("ops.budget", {"what": "allocator throttle", "active": now, "floor_pnl_ratio": round(ratio, 4),
                                                    "reason": ("the floor's real P&L fell below the throttle line: every real stake is halved"
                                                               if now else "the floor recovered: stakes are restored")})
        return now

    # ------------------------------------------------------------ families
    #: The House's background-job key of a family's swing audit (the audit lane: `House._background`).
    FAMILY_AUDIT = "audit:family:"

    def _begin_pass(self) -> None:
        """A new pass reads every family afresh, once, through the ledger position it starts at, and moves
        the mechanism ledger's states (C1, Sept 24, 2026: `families.next_state`). A ledger that cannot be
        read now leaves the tape where it stood: the pass goes on (Sept 24, 2026)."""
        try:
            self._through = self._tape.refresh(self.house.ledger)
        except Exception as exc:  # noqa: BLE001 - an unreadable ledger must not stop the pass or its exits
            self._family_error("the family records' tape", "", exc)
            self._through = self._tape.cursor
        self._families = {}
        self._released = None
        self._released = self._swing_released()  # the grant's rung-3 release, read once a pass
        try:
            # Each living agent's rung read once for the families' members on real money (a ledger read an agent).
            self._rungs = {a.id: self.house.evaluator.rung(a.id) for a in list(self.house.registry.living())}
            for family, venue in self._family_keys():
                self._families[(family, venue)] = self._compute_family(family, venue, advance=True)
        except Exception as exc:  # noqa: BLE001 - the ledger's states feed money; a fault there never stops the pass
            self._family_error("the mechanism ledger", "", exc)
        finally:
            self._rungs = None  # after the families, rungs move with the pass: read afresh

    def _family_keys(self) -> list[tuple[str, str]]:
        """The families the ledger follows at a pass: every living agent's, and every family whose state is not
        "unproven" (so a proven family whose last member died still records its fall)."""
        keys = {(a.family, a.venue) for a in list(self.house.registry.living()) if a.family and a.venue in REAL_BOOK}
        for key, st in list((self.state.get("families") or {}).items()):
            family, _, venue = str(key).rpartition("@")
            if family and venue in REAL_BOOK and (st or {}).get("state") in ("proven", "swing"):
                keys.add((family, venue))
        return sorted(keys)

    def _family_error(self, family: str, venue: str, exc: BaseException, *, then: str | None = None) -> None:
        """One warning per family and distinct error, however many wakes and passes meet it. `then`: what follows, when
        it is not the unreadable record's fallback."""
        why = f"{type(exc).__name__}: {str(exc)[:160]}"
        key = (family, venue, why)
        if key in self._family_alerted:
            return
        self._family_alerted.add(key)
        try:
            self.house.alert("warning", f"allocator: {family}{' at ' + venue if venue else ''} could not be read ({why}); "
                                        + (then or "until it can, its agents count as an unproven family's: probes, no swing, "
                                                   "post-only real entries"))
        except Exception:  # noqa: BLE001 - the alert is a courtesy; the fallback is the protection
            pass

    def _unreadable_family(self, family: str, venue: str, exc: BaseException) -> dict[str, Any]:
        """What a family counts as while its record cannot be computed: unproven, with no taker record, no
        swing -- for money. Its state in the ledger is not moved: a swing that could not be read this pass
        does not lose its entry (the ramp would start again) for a read that fails once."""
        self._family_error(f"the {family} family's record", venue, exc)
        record = families.empty_record(family, venue, through=self._through, error=f"{type(exc).__name__}: {str(exc)[:160]}")
        return {**record, "since": None, "swing": None, "members_real": 0}

    def _compute_family(self, family: str, venue: str, *, advance: bool) -> dict[str, Any]:
        """The record, its state and (swinging) its stake. `advance`: the pass moves the ledger's state and may
        start the family's swing audit; a read between passes (a wake, the book's order path) computes the
        same state from the record without writing it."""
        try:
            base = self._family_base_stake(family, venue)
            record = family_record(self.house, family, venue, tape=self._tape, through=self._through,
                                   now=self.house.clock(), stake_usd=float(base))
        except Exception as exc:  # noqa: BLE001 - exits must run: see `family`
            return self._unreadable_family(family, venue, exc)
        try:
            return self._decorate(record, advance=advance)
        except Exception as exc:  # noqa: BLE001 - the same: a state that cannot be read is an unproven family's
            return self._unreadable_family(family, venue, exc)

    def _family_base_stake(self, family: str, venue: str) -> Decimal:
        """A proven family's bunt at `venue`, the stake the capacity estimate is read at until the family swings."""
        return _params()["bunt_usd"].get(venue, _d("10"))

    def _members(self, family: str, venue: str) -> list[Any]:
        registry = self.house.registry
        with (getattr(registry, "_lock", None) or contextlib.nullcontext()):
            return [a for a in list(registry.agents.values()) if a.family == family and a.venue == venue]

    def _members_real_ids(self, family: str, venue: str) -> list[str]:
        """The family's living members on real money at `venue`: the family swing's caps are shared by them."""
        rungs = getattr(self, "_rungs", None) or {}
        return sorted(a.id for a in self._members(family, venue)
                      if a.alive and (rungs[a.id] if a.id in rungs else self.house.evaluator.rung(a.id)) >= 2)

    def _members_real(self, family: str, venue: str) -> int:
        return len(self._members_real_ids(family, venue))

    def _reswing(self, record: Mapping[str, Any], members_real: int) -> dict[str, Any] | None:
        """The family swing's stake a member, shared by `members_real` members on real money (the pass's record keeps
        the ramp's entry and the fill rates it was read at: `swing_inputs`)."""
        rule = families.swing_rule()
        if rule is None:
            return None
        family, venue = record["family"], record["venue"]
        inputs = record.get("swing_inputs") or {}
        return families.swing_target(record, rule=rule, venue=venue, bunt_usd=self._family_base_stake(family, venue),
                                     venue_capital=self.capital(venue), members_real=members_real,
                                     entered_seq=inputs.get("entered_seq"), rates=inputs.get("rates"))

    def _swing_for(self, agent: Any) -> dict[str, Any] | None:
        """The family swing's stake for `agent` while its family swings, else None. The pass's record shares the family's
        caps among the members it counted on real money; an agent it did not count -- a newcomer being seated -- shares
        them with ONE MORE member from its first dollar (review of #242, Sept 24, 2026: two newcomers seated in one pass
        were each lent the one-member share, and the family held three times its Kelly cap until the next pass)."""
        record = self.family(agent.family, agent.venue)
        swing = record.get("swing") if record.get("state") == "swing" else None
        if not swing or agent.id in (record.get("members_real_ids") or ()):
            return swing
        return self._reswing(record, int(record.get("members_real") or 0) + 1) or swing

    def _admit(self, agent: Any) -> None:
        """A newcomer just seated on real money counts among its family's members for the rest of the pass: a swinging
        family's share is recomputed with it, so the next newcomer and every member's stake (`_size`) follow the count."""
        key = (agent.family, agent.venue)
        record = self._families.get(key)
        if not record or agent.id in (record.get("members_real_ids") or ()):
            return
        record = dict(record)
        record["members_real_ids"] = sorted({*(record.get("members_real_ids") or ()), agent.id})
        record["members_real"] = len(record["members_real_ids"])
        if record.get("state") == "swing" and record.get("swing"):
            record["swing"] = self._reswing(record, record["members_real"]) or record["swing"]
        self._families[key] = record

    def _decorate(self, record: Mapping[str, Any], *, advance: bool) -> dict[str, Any]:
        """The record with the mechanism ledger's state (`families.next_state`): "proven" on the POOLED record alone;
        "swing" for a proven family whose entry look passes at its checkpoint (`families.entry_look`, at
        `entry_confidence`) and whose entry's audit approved it (`_request_family_audit`), kept while its real record
        holds at the table's 80% (`families.swing_ready`); else "unproven"; its `since`; and for a swinging family the
        member's stake (`families.swing_target`) and the capacity at that stake. Leaving the swing, a member's new program
        or a member born into the family after the audit looked lapses the approval (`_lapse_approval`)."""
        family, venue = record["family"], record["venue"]
        key = families.key_of(family, venue)
        with self._lock:
            previous = dict((self.state.get("families") or {}).get(key) or {})
        rule = families.swing_rule()
        # A swing is a stake above the bunt, which the live grant releases with rung 3 (`allows_live(3)`, its `max_rung`):
        # the family swing holds only while it does, not only at its first audit (review of #242, Sept 24, 2026: with an
        # approval on record nothing else read the grant, and a grant narrowed to rung 2 left the swing staked).
        released = self._swing_released()
        entry = released and families.entry_ready(record, rule)
        hold = released and families.swing_ready(record, rule)
        proven = bool(record.get("proven"))
        before = previous.get("state") if previous.get("state") in families.STATES else ("proven" if proven else "unproven")
        approved, lapse = self._swing_approval(key, family, venue)
        state = families.next_state(before, proven=proven, entry=entry, hold=hold, approved=approved)
        stamp = now_iso(self.house.clock)
        since = previous.get("since") if state == before and previous.get("since") else stamp
        entered = previous.get("entered_seq") if before == "swing" else self._through
        counted = self._members_real_ids(family, venue)
        members_real = len(counted)
        swing = inputs = None
        out = dict(record)
        members = [a.id for a in self._members(family, venue)]
        if state == "swing" and rule is not None:
            since_capacity = self.house.clock() - rule["capacity_days"] * families.DAY
            rates = families.fill_rates(self._tape, members, since=since_capacity, min_markets=rule["capacity_min_markets"])
            inputs = {"entered_seq": entered, "rates": rates}
            swing = families.swing_target(record, rule=rule, venue=venue, bunt_usd=self._family_base_stake(family, venue),
                                          venue_capital=self.capital(venue), members_real=members_real,
                                          entered_seq=entered, rates=rates)
        stake = self._family_stake({**record, "state": state, "swing": swing})
        if record.get("capacity") is not None and stake != self._family_base_stake(family, venue):
            # The capacity estimate at the stake a member of this family is lent: a probe's, or the family swing's.
            out["capacity"] = families.capacity(self._tape, members, venue, now=self.house.clock(),
                                                days=(rule or {}).get("capacity_days", 7.0), stake_usd=float(stake),
                                                edge=record.get("edge_per_dollar"),
                                                real_events=(record.get("real") or {}).get("closed_at") or [],
                                                min_markets=(rule or {}).get("capacity_min_markets", 5))
        if advance:
            new = {"state": state, "since": since}
            if state != before:
                new["was"] = before
            if state == "swing":
                new["entered_seq"] = entered
                new["entered_at"] = previous.get("entered_at") if before == "swing" else stamp
            with self._lock:
                self.state.setdefault("families", {})[key] = new
            # An approval licenses an entry: it lapses when the family leaves the swing, or when a member's program
            # changed, or a member was born into the family, after the audit looked (the main session's decisions on
            # the review of #242, Sept 24, 2026). A swing already running is untouched: its next entry is audited again.
            if before == "swing" and state != "swing":
                self._lapse_approval(key, f"the family left the swing ({state})")
            elif lapse:
                self._lapse_approval(key, lapse)
            if proven and entry and state != "swing":
                try:
                    self._request_family_audit(key, out, members_real)
                except Exception as exc:  # noqa: BLE001 - asking for the audit is not the record (review of #242)
                    # A failure here (the member's evidence unreadable, say) used to make the whole family unreadable
                    # for money: its proven members were swept to probes at every pass it lasted. It is told once and
                    # asked again at the next pass; the family keeps its state and its stakes.
                    self._family_error(f"the {family} family swing's audit request", venue, exc,
                                       then="the family keeps its state and stakes, and its audit is asked for again at the next pass")
        out.update(state=state, since=since, swing=swing, members_real=members_real, members_real_ids=counted, swing_inputs=inputs)
        return out

    def family(self, family: str, venue: str) -> dict[str, Any]:
        """The family's pooled record (`family_record`) with its state in the mechanism ledger, computed once a
        pass and kept until the next. Never raises: it is on every wake's path (`limits` -> `seat_stake` ->
        `tier`), on the book's order path (`family_taker`, `band_of`) and in the pass, and a record that cannot
        be computed is an UNPROVEN family's until the next pass tries again (review of #224, Sept 24, 2026)."""
        key = (family, venue)
        record = self._families.get(key)
        if record is None:
            record = self._compute_family(family, venue, advance=False)
            self._families[key] = record
        return record

    def family_state(self, agent: Any) -> str:
        """"unproven", "proven" or "swing": the agent's family's state in the mechanism ledger."""
        state = self.family(agent.family, agent.venue).get("state")
        return state if state in families.STATES else "unproven"

    def tier(self, agent: Any) -> str:
        """"bunt" when the agent's family is proven or swinging (`family_proven`, `family_swing`), else "probe"
        (P1, Sept 24, 2026). The proof's tier: a swinging family's member is a bunt that is staked more."""
        return "bunt" if self.family_state(agent) in ("proven", "swing") else "probe"

    def rung2_band(self, agent: Any) -> str:
        """What a rung-2 agent is called on the board, the tape and the book: "probe", "bunt", or "swing" for a
        member of a swinging family (C2, Sept 24, 2026: its stake is the family swing's, and the book holds it
        to the swing's daily-loss rule, as every stake above the bunt)."""
        return "swing" if self.family_state(agent) == "swing" else self.tier(agent)

    def swing_allowed(self, agent: Any) -> bool:
        """Whether the agent may take the agent-level swing (`swing_at`): always, unless the constitution's
        `swing_requires_proven_family` holds it to a proven (or swinging) family's agent (Sept 24, 2026). The
        House's `_commit_promotion` reads it when a swing audit finishes."""
        if not rules().get("swing_requires_proven_family"):
            return True
        return self.family_state(agent) in ("proven", "swing")

    def family_summary(self, agent: Any) -> dict[str, Any]:
        """The family record as a verdict, the board and an audit carry it."""
        r = self.family(agent.family, agent.venue)
        split = ("n", "mean_log", "bound", "positive", "members")
        real = r.get("real") or {}
        swing = r.get("swing")
        return {"family": agent.family, "state": r["state"], "since": r.get("since"), "proven": bool(r.get("proven")),
                "unit": r.get("unit"), "n": r["n"], "n_eff": r["n_eff"], "mean_log": r["mean_log"],
                "sd": r["sd"], "bound": r["bound"], "loss_gate": r.get("loss_gate"), "real_n": r["real_n"], "members": r["members"],
                "members_counted": r["members_counted"], "through": r["through"],
                "real": {**{k: real.get(k) for k in ("n", "mean_log", "bound", "loss_gate", "honest_bound")}, "entry": real.get("entry")},
                "swing": None if not swing else {k: (str(v) if isinstance(v, Decimal) else v) for k, v in swing.items()},
                "maker": {k: r["maker"].get(k) for k in split}, "taker": {k: r["taker"].get(k) for k in split}, "rule": r["rule"]}

    def family_taker(self, agent_id: str) -> dict[str, Any] | None:
        """The agent's family's pooled TAKER record, for the book's `real_entry_liquidity` rule (P3, Sept 24,
        2026: a real entry on an event book is post-only unless this is `positive`): {"family", "positive",
        "n", "mean_log", "bound"}. None while the allocator is off or for an agent it does not know."""
        if not enabled():
            return None
        agent = self.house.registry.get(agent_id)
        if agent is None:
            return None
        taker = self.family(agent.family, agent.venue)["taker"]
        return {"family": agent.family, "positive": bool(taker["positive"]), "n": int(taker["n"]),
                "mean_log": float(taker["mean_log"]), "bound": taker["bound"]}

    def _family_note(self, agent: Any) -> str:
        r = self.family(agent.family, agent.venue)
        bound = "no bound yet" if r["bound"] is None else f"bound {r['bound']:+.5f}"
        return (f"its family {agent.family} is {r['state']} ({r['n']} independent settlements, {bound}; "
                f"proven at {r['rule']['min_independent_settlements']} with the bound above zero)")

    # ------------------------------------------------ the family swing's audit
    def _swing_released(self) -> bool:
        """Whether the live grant releases stakes above the bunt (`allows_live(3)`), read once a pass (`_begin_pass`); a
        grant that cannot be read releases nothing above the bunt."""
        released = getattr(self, "_released", None)
        if released is not None:
            return released
        guard = getattr(self.house, "campaigns", None)
        if guard is None:
            return True
        try:
            return bool(guard.allows_live(3))
        except Exception:  # noqa: BLE001 - an unreadable grant releases nothing above the bunt
            return False

    def _swing_approval(self, key: str, family: str, venue: str) -> tuple[bool, str | None]:
        """(whether an approved audit licenses the family's entry into the swing now, why an approval on record no
        longer does). The entry is audited on the family's REAL record (C2, Sept 24, 2026), and an approval licenses
        entries until it lapses (the main session's decision on the review of #242): when the family leaves the swing
        (`_decorate` lapses it), or when a member of the family takes a new program (`agent.strategy`) or is BORN into it
        (`agent.born`: a research child is how a real-money line changes its code) after the audit looked at the family
        (its `started_seq`), as the agent-level route voids an approval on new code. A swing already running is untouched:
        the lapse makes its next entry ask for a new audit. A veto waits out the audit cooldown before it is asked again."""
        with self._lock:
            audit = dict((self.state.get("family_audits") or {}).get(key) or {})
        if audit.get("status") != "done" or audit.get("approve") is not True:
            return False, None
        since = int(audit.get("started_seq") or 0)
        members = self._members(family, venue)
        changed = sorted(a.id for a in members if self._tape.programs.get(a.id, 0) > since)
        born = sorted(a.id for a in members if self._tape.born.get(a.id, 0) > since)

        def named(ids: list[str]) -> str:
            return ", ".join(ids[:3]) + (" and others" if len(ids) > 3 else "")

        if changed:
            return False, f"{named(changed)} took a new program after the audit"
        if born:
            return False, f"{named(born)} {'was' if len(born) == 1 else 'were'} born into the family after the audit"
        return True, None

    def _lapse_approval(self, key: str, why: str) -> None:
        """An approval that no longer licenses an entry: the next entry asks for a new audit, with no cooldown to wait."""
        with self._lock:
            audits = self.state.setdefault("family_audits", {})
            was = dict(audits.get(key) or {})
            if was.get("status") != "done" or was.get("approve") is not True:
                return
            audits[key] = {"status": "lapsed", "why": why, "agent": was.get("agent"), "approved_at": was.get("at"),
                           "started_seq": was.get("started_seq"), "at": now_iso(self.house.clock), "at_epoch": self.house.clock()}
        try:
            self.house.alert("info", f"allocator: the {key} family swing's approval lapsed ({why}); its next entry is audited again")
        except Exception:  # noqa: BLE001 - a courtesy
            pass

    def _audit_hours(self, error: bool) -> float:
        rules_ = (getattr(self.house, "game", None) or {}).get("audit") or {}
        return float(rules_.get("error_cooldown_hours", 0.5) if error else rules_.get("cooldown_hours", 72))

    def _request_family_audit(self, key: str, record: Mapping[str, Any], members_real: int) -> None:
        """Start the family's swing audit unless one runs, has approved, or waits out its cooldown. Without an
        auditor there is no family swing: a gate that fails open is not a gate."""
        house = self.house
        if getattr(house, "auditor", None) is None or not hasattr(house, "_background"):
            return
        guard = getattr(house, "campaigns", None)
        if guard and not guard.allows_live(3):
            return  # the live grant has not released stakes above the bunt: nothing to audit for
        with self._lock:
            audit = dict((self.state.setdefault("family_audits", {})).get(key) or {})
        if audit.get("status") == "running":
            job = (getattr(house, "_jobs", None) or {}).get(self.FAMILY_AUDIT + key)
            if job is not None and job.is_alive():
                return
            found = self._family_verdict_on_ledger(key, audit)
            if found is not None:
                with self._lock:
                    self.state["family_audits"][key] = found
                return
        elif audit.get("status") == "done":
            if audit.get("approve") is True:
                return
            if house.clock() - float(audit.get("at_epoch") or 0) < self._audit_hours(bool(audit.get("error"))) * 3600:
                return
        agent = self._family_representative(record)
        if agent is None:
            return
        verdict = self._family_swing_verdict(agent, record, key, members_real)
        running = {"status": "running", "agent": agent.id, "started_seq": int(house.ledger.head()[0]),
                   "started_at": now_iso(house.clock), "at_epoch": house.clock()}
        with self._lock:
            self.state["family_audits"][key] = running
        if not house._background(self.FAMILY_AUDIT + key, self._run_family_audit, key, agent.id, verdict):
            with self._lock:
                self.state["family_audits"][key] = audit  # closing: the next process asks again

    def _family_representative(self, record: Mapping[str, Any]) -> Any:
        """The member the family's audit is written against (its code is the mechanism the auditor reads): the
        living member on real money with the most real closed trades, else the living member on practice with
        the most; None when no member lives."""
        house = self.house
        best = None
        for agent in self._members(record["family"], record["venue"]):
            if not agent.alive:
                continue
            rung = house.evaluator.rung(agent.id)
            if rung < 1:
                continue
            ev = self._evidence.get(agent.id)
            rank = (rung >= 2, ev.real_trades if ev else 0, ev.paper_trades if ev else 0, agent.id)
            if best is None or rank > best[0]:
                best = (rank, agent)
        return best[1] if best else None

    def _run_family_audit(self, key: str, agent_id: str, verdict: Any) -> None:
        """The audit, off the tick (the audit lane). Its verdict is the family's: the next pass reads it."""
        from copy import deepcopy

        house = self.house
        agent = deepcopy(house.registry.get(agent_id))
        try:
            result = house._call_auditor(agent, verdict)
        except Exception as exc:  # noqa: BLE001 - an auditor that raises has not audited
            result = {"approve": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                      "summary": "the family swing's audit could not run; the family stays in bunts"}
            house.ledger.append("audit.verdict", {**result, "family_swing": key,
                                                  "policy_digest": getattr(house.auditor, "policy_digest", None)}, agent=agent_id)
        done = {"status": "done", "agent": agent_id, "approve": result.get("approve") is True and not result.get("error"),
                "error": bool(result.get("error")), "summary": str(result.get("summary") or result.get("error") or "")[:300],
                "at": now_iso(house.clock), "at_epoch": house.clock()}
        with self._lock:
            audits = self.state.setdefault("family_audits", {})
            # Where the audit looked at the family: a member's program changed after it lapses the approval.
            done["started_seq"] = (audits.get(key) or {}).get("started_seq")
            audits[key] = done
        try:
            house.alert("info", f"allocator: the {key} family swing's audit {'approved' if done['approve'] else 'did not approve'} "
                                f"its entry ({done['summary'][:160]})")
        except Exception:  # noqa: BLE001 - a courtesy
            pass

    def _family_verdict_on_ledger(self, key: str, audit: Mapping[str, Any]) -> dict[str, Any] | None:
        """An audit that finished before a restart: the auditor's own row for the family (`family_swing`)."""
        from ltcm.broker import instant

        agent = audit.get("agent")
        if not agent:
            return None
        for entry in self.house.ledger.iter(kinds="audit.verdict", agent=agent, after=int(audit.get("started_seq") or 0)):
            p = entry.payload
            if p.get("family_swing") == key:
                parsed = instant(entry.at)
                return {"status": "done", "agent": agent, "approve": p.get("approve") is True and not p.get("error"),
                        "error": bool(p.get("error")), "summary": str(p.get("summary") or "")[:300], "at": entry.at,
                        "at_epoch": parsed.timestamp() if parsed else self.house.clock(), "started_seq": audit.get("started_seq")}
        return None

    def _family_swing_verdict(self, agent: Any, record: Mapping[str, Any], key: str, members_real: int) -> Any:
        """What the auditor judges: the family packet -- its REAL record, event by event, every member's real
        closes, its capacity -- with `allocation_context`, the stake the family swing would take (the Sept 23
        lesson: without the allocator's context the auditor judged a bunt against the legacy tuition and
        vetoed on capacity it could not see)."""
        from .evaluator import Verdict

        family, venue = record["family"], record["venue"]
        ev = self._evidence.get(agent.id) or evidence(self.house, agent)
        rule = families.swing_rule() or {}
        members = [a.id for a in self._members(family, venue)]
        rates = families.fill_rates(self._tape, members, since=self.house.clock() - rule.get("capacity_days", 7) * families.DAY,
                                    min_markets=rule.get("capacity_min_markets", 5))
        entry = families.swing_target(record, rule=rule, venue=venue, bunt_usd=self._family_base_stake(family, venue),
                                      venue_capital=self.capital(venue), members_real=max(members_real, 1),
                                      entered_seq=None, rates=rates)
        real = record.get("real") or {}
        look = real.get("entry") or {}
        why = (f"the {family} family is proven and its REAL record qualifies for the family swing: its first {look.get('checkpoint')} "
               f"of {real.get('n')} independent real settlements clear the entry's {float(look.get('confidence') or 0):.0%} lower bound "
               f"({float(look.get('honest_bound') or 0):+.5f} a dollar at risk; the whole record's bound at "
               f"{float((record.get('rule') or {}).get('confidence') or 0.8):.0%} is {float(real.get('honest_bound') or 0):+.5f})")
        numbers = {"via": "family_swing", "book": REAL_BOOK[venue], "evidence": ev.row(), "E": ev.e, "band_to": "swing",
                   "family_swing": key, "family_packet": self._family_packet(record),
                   "allocation_context": self._family_swing_context(agent, ev, record, entry, members_real)}
        return Verdict(agent.id, 2, "eligible", why, numbers)

    def _family_packet(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """The family's REAL record for the auditor: the pooled numbers, each real event's first close and value,
        every member's real closed trades (the last 80), the members and the capacity measured."""
        family, venue = record["family"], record["venue"]
        book = REAL_BOOK[venue]
        closes = []
        agents = self._members(family, venue)
        for agent in agents:
            for row in self._tape.rows.get(agent.id) or ():
                p = row.payload
                if p.get("book") != book:
                    continue
                inst = p.get("instrument") or {}
                market = inst.get("market_id") or inst.get("symbol")
                if row.kind == "book.settle":
                    closes.append({"agent": agent.id, "market": market, "made": p.get("pnl"), "seq": row.seq, "kind": "settlement"})
                elif row.kind == "book.fill" and p.get("realized") is not None and p.get("flat", True) and p.get("source") != "dust":
                    closes.append({"agent": agent.id, "market": market, "made": p.get("realized"), "seq": row.seq, "kind": "sale",
                                   "liquidity": p.get("liquidity")})
        closes.sort(key=lambda c: c["seq"])
        real = record.get("real") or {}
        keys = ("n", "n_eff", "mean_log", "sd", "bound", "lopsided", "loss_gate", "honest_bound", "variance")
        return {"family": family, "venue": venue, "unit": record.get("unit"),
                "unit_meaning": ("each value is what the event made per dollar its positions put at risk, as log growth at a 1% bet"
                                 if record.get("unit") == "at_risk" else "each value is the member's account growth on the event"),
                "proof_rule": record.get("rule"), "swing_rule": families.swing_rule(),
                "real_record": {k: real.get(k) for k in keys},
                # The entry look that qualified it: the first `checkpoint` real events at `entry_confidence`.
                "entry_look": real.get("entry"),
                "pooled_record": {k: record.get(k) for k in ("n", "n_eff", "mean_log", "sd", "bound", "loss_gate", "proven", "edge_per_dollar")},
                "maker": {k: (record.get("maker") or {}).get(k) for k in ("n", "mean_log", "bound", "positive")},
                "taker": {k: (record.get("taker") or {}).get(k) for k in ("n", "mean_log", "bound", "positive")},
                "real_events": [{"first_close_seq": seq, "value": value} for seq, value in (real.get("first_closes") or [])[-80:]],
                "real_closes": closes[-80:],
                "members": [{"agent": a.id, "alive": bool(a.alive), "rung": self.house.evaluator.rung(a.id) if a.alive else None}
                            for a in agents][:80],
                "capacity": record.get("capacity")}

    def _family_swing_context(self, agent: Any, ev: Evidence, record: Mapping[str, Any], entry: Mapping[str, Any],
                              members_real: int) -> dict[str, Any]:
        """`allocation_context` for the family swing: the member's stake at entry, the family's, the ramp and its
        caps, inside the venue's envelope and the owner's grant."""
        context = self.context(ev, "bunt")
        stake = _d(entry["stake_usd"])
        position, order = limits_for(stake, agent.venue)
        base = self._family_base_stake(record["family"], agent.venue)
        increase = (stake - base) * max(members_real, 1)
        context.update({
            "band_to": "swing", "tier": "swing", "family_swing": True,
            "stake_usd": str(stake), "max_position_usd": str(position), "max_order_usd": str(order),
            "members_on_real_money": members_real, "family_stake_usd": str(stake * max(members_real, 1)),
            "ramp": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in entry.items()},
            "purpose": ("the FAMILY SWING: every member of the family on real money is staked at the ramp above the bunt, "
                        "doubling after every further run of positive independent real settlements while the family's "
                        "real lower bound holds, up to Kelly on that bound and the venue share, shared by its members"),
            "fits": bool(self.headroom(agent.venue) >= increase),
        })
        return context

    # ------------------------------------------------ the ledger's rows, the readers
    def _family_stake(self, record: Mapping[str, Any]) -> Decimal:
        """The stake a member of this family on real money is lent before the throttle and its own W_real: the
        family swing's, a proven family's bunt, or an unproven family's probe."""
        p = _params()
        venue = record["venue"]
        if record.get("state") == "swing" and record.get("swing"):
            return _d(record["swing"]["stake_usd"])
        if record.get("state") in ("proven", "swing"):
            return p["bunt_usd"].get(venue, _d("10"))
        return p["probe_bunt_usd"].get(venue, p["bunt_usd"].get(venue, _d("10")))

    def _family_row(self, record: Mapping[str, Any]) -> dict[str, Any]:
        state = {"state": record.get("state", "unproven"), "since": record.get("since")}
        return families.row_of(record, state, swing=record.get("swing"), members_real=int(record.get("members_real") or 0),
                               stake_usd=self._family_stake(record))

    def _persist_families(self) -> None:
        """`family.record` rows (C1, Sept 24, 2026): at most every five minutes, one for each family whose row
        changed since its last one -- the durable record of every state change and every new settlement."""
        house = self.house
        now = house.clock()
        if now - float(self.state.get("family_rows_at") or 0) < families.PERSIST_SECONDS:
            return
        self.state["family_rows_at"] = now
        digests = self.state.setdefault("family_rows", {})
        stamp = now_iso(house.clock)
        for (family, venue), record in sorted(self._families.items()):
            if record.get("error"):
                continue
            row = self._family_row(record)
            key = families.key_of(family, venue)
            digest = families.row_digest(families.change_view(row))  # never for the clock alone (review of #242)
            if digests.get(key) == digest:
                continue
            digests[key] = digest
            house.ledger.append("family.record", {**row, "through": record.get("through"), "at": stamp})

    def families_board(self) -> dict[str, dict[str, Any]]:
        """The board's `families` block (C4): per venue, per family followed this pass, its state and since, the
        pooled and real counts and bounds, the stake a member on real money is lent, its members on real money
        and its capacity."""
        out: dict[str, dict[str, Any]] = {}
        for (family, venue), record in sorted(self._families.items()):
            row = self._family_row(record)
            row.pop("family", None)
            row.pop("venue", None)
            out.setdefault(venue, {})[family] = row
        return out

    def family_forward(self) -> dict[str, tuple[int, float]]:
        """Each family's pooled forward record by active `eval.block`s and their summed log growth, over every
        agent ever born into it, living or dead, from the mechanism ledger's tape: a drop-in for
        `House.family_forward` (what `House._losing_family` -- the House's births, `_refill` and the foundry --
        reads), so they read the one source (`families.losing` is the rule)."""
        registry = self.house.registry
        with (getattr(registry, "_lock", None) or contextlib.nullcontext()):
            family_of = {a.id: a.family for a in list(registry.agents.values())}
        out: dict[str, list[float]] = {}
        for agent_id, blocks in list(self._tape.blocks.items()):
            family = family_of.get(agent_id)
            if not family:
                continue
            row = out.setdefault(family, [0, 0.0])
            for _, _, active, growth in blocks:
                if active:
                    row[0] += 1
                    row[1] += growth
        return {family: (int(n), float(growth)) for family, (n, growth) in out.items()}

    def family_score(self, family: str, venue: str) -> int:
        """+1 proven or swinging, -1 a negative pooled record past the proof's count, else 0 (`families.score`):
        what `Lab.lineage_weights` may read to weigh a lineage by its family (lab.py is not this module's)."""
        record = self.family(family, venue)
        return families.score(record, record.get("state", "unproven"))

    def lineage_score(self, agent_ids: Sequence[str]) -> int:
        """`family_score` of the first of `agent_ids` the registry knows (a lab lineage's origin, nearest first:
        `Lab._origin`), 0 when none."""
        for agent_id in agent_ids:
            agent = self.house.registry.get(agent_id)
            if agent is not None:
                return self.family_score(agent.family, agent.venue)
        return 0

    # ------------------------------------------------------------- stakes
    def target_stake(self, agent: Any, band: str, ev: Evidence | None = None) -> Decimal:
        p = _params()
        base = p["bunt_usd"].get(agent.venue, _d("10"))
        family = self.family(agent.family, agent.venue)
        # A newcomer being seated shares the family's caps with the members already on real money (`_swing_for`).
        swing = self._swing_for(agent) if family.get("state") == "swing" and band in ("bunt", "swing", "star") else None
        if band in ("bunt", "probe") and (band == "probe" or self.tier(agent) == "probe"):
            # P1 (Sept 24, 2026): a bunt of an unproven family is a probe, pocket change for an unproven
            # mechanism. `bunt_growth` then keeps what it makes on the probe's own base.
            base = p["probe_bunt_usd"].get(agent.venue, base)
        niche = self.house.niche_of(agent)
        if niche is not None and niche.asset_class == "option":
            # One option contract cannot be cut smaller: an options bunt is one contract's premium,
            # and since Sept 23, 2026 (A2a) `option_bunt_usd`, $80: the book holds a position and an
            # order to half the account's equity, so at $40 the $40 contract the bunt was staked for
            # could never be bought and the chain was filtered at contracts the book refused. A probe
            # too (Sept 24, 2026): a probe cannot hold a smaller contract than a bunt.
            base = max(base, p["option_bunt_usd"])
            p = {**p, "bunt_usd": {**p["bunt_usd"], agent.venue: base}}
        if band in ("swing", "star") and ev is not None:
            stake = swing_stake(ev, self.capital(agent.venue), p)
            if swing:
                stake = max(stake, _d(swing["stake_usd"]))  # the agent-level route never stakes a member less
        elif swing and band == "bunt":
            # The family swing (C2, Sept 24, 2026): every member on real money is staked at the family's ramp
            # up to its shared caps (`families.swing_target`), never under its own bunt; the family's record,
            # not the member's own W_real, sizes it.
            stake = max(_d(swing["stake_usd"]), base)
        else:
            stake = bunt_stake(ev, base, p)
        if self.state.get("throttle"):
            # Halved, but never under the smallest stake that can still trade: a position is at most
            # `position_share` of the stake (`position_share_event` on Kalshi) and must hold the venue's
            # minimum order (x1.2), or the seat would hold capital and never open anything (Sept 23,
            # 2026 review).
            tradable = (_d((rules().get("venue_minimum_usd") or {}).get(agent.venue, "1")) * _d("1.2")
                        / _d(_position_share(agent.venue, p))).quantize(CENT)
            stake = max((stake / 2).quantize(CENT, rounding=ROUND_DOWN), min(tradable, stake))
        return stake

    def seat_stake(self, agent: Any) -> Decimal:
        """The stake a newly seated real account is lent (House.seat)."""
        ev = self._evidence.get(agent.id)
        rung = self.house.evaluator.rung(agent.id)
        band = "swing" if rung >= 3 else "bunt"
        return self.target_stake(agent, band, ev)

    def limits(self, agent: Any, staked: Decimal) -> tuple[Decimal, Decimal]:
        """(max position, max order) for a real account lent `staked` net: a share of its stake, which
        at a new seat is the target `House.seat` is about to lend. A raise the allocator has not lent
        is not yet the account's stake: while the target is above both what the account was lent and
        what it holds, the limits follow what it holds. (Review of #224, Sept 24, 2026: a $10 probe
        whose family was proven while the envelope had no room for the $20 raise was given the $30
        bunt's $6 position at its next wake, and a $3.00 position, 30% of its stake, filled.)"""
        target = self.seat_stake(agent)
        if staked <= 0:
            return limits_for(target, agent.venue)
        book = self.house.book_of(agent)
        held = book.equity(agent.id) if book is not None and agent.id in book.accounts else staked
        return limits_for(min(max(staked, target), max(staked, held)), agent.venue)

    # ---------------------------------------------------- facts for the books
    def band_of(self, agent_id: str) -> str | None:
        """The band an agent stands in, for the real book's daily-loss rule (constitution
        `allocator.bunt_daily_loss`): "bunt" on rung 2, "swing" on rung 3 (a star is a swing), None
        below real money or while the allocator is off, when the book's own rule stands. The rung is
        read, not the board: a promotion, a demotion by drift or a veto moves the rung at once and
        the board only at the next pass. A rung-2 member of a SWINGING family is a "swing" here (C2, Sept 24,
        2026): its stake is above the bunt, and the book keeps its own daily-loss rule for every stake above
        the bunt, as the constitution's `bunt_daily_loss` says of swings."""
        if not enabled():
            return None
        rung = self.house.evaluator.rung(agent_id)
        if rung == 2:
            agent = self.house.registry.get(agent_id)
            if agent is not None and self.family_state(agent) == "swing":
                return "swing"
        return band_of_rung(rung) if rung >= 2 else None

    def halt_basis_usd(self, venue: str) -> Decimal | None:
        """The venue's grant capital, the real book's daily-loss halt basis under the constitution's
        `allocator.real_halt` ($517.75 Kalshi, $500 Alpaca on Sept 23, 2026: 8% is $41.42 and $40.00,
        per venue). None while the allocator is off or no grant names the venue, when the book keeps
        its own basis. The grant's capital, not the profit-indexed envelope: a halt line that grows
        with the day's winners is not a halt."""
        if not enabled():
            return None
        caps = ((self.grant() or {}).get("policy") or {}).get("venue_capital_usd") or {}
        if venue not in caps:
            return None
        return _d(caps[venue])

    def context(self, ev: Evidence, band: str) -> dict[str, Any]:
        """The allocation an audit judges capacity against: the stake and limits the move would take,
        the venue's envelope now, and the grant behind it. Replaces the legacy tuition in the packet."""
        agent = self.house.registry.get(ev.agent)
        stake = self.target_stake(agent, band, ev) if agent is not None else _params()["bunt_usd"].get(ev.venue, _d("10"))
        position, order = limits_for(stake, ev.venue)
        grant = self.grant()
        policy = (grant or {}).get("policy") or {}
        seated = sum(1 for a in self.house.registry.living() if a.venue == ev.venue and self.house.evaluator.rung(a.id) >= 2)
        tier = (self.tier(agent) if band in ("bunt", "probe") else None) if agent is not None else None
        # A swinging family's member on rung 2 is staked the family swing's stake (C2, Sept 24, 2026).
        named = (self.rung2_band(agent) if band in ("bunt", "probe") else None) if agent is not None else None
        return {
            "allocator": "capital is the ladder (league/allocator.py): stakes follow evidence inside the grant's per-venue envelope",
            "band_to": named or band, "stake_usd": str(stake), "max_position_usd": str(position), "max_order_usd": str(order),
            # P1 (Sept 24, 2026): a probe is judged as a probe -- pocket change for an unproven family's
            # mechanism -- and a bunt as a proven family's member, on the family's pooled record.
            "tier": tier, "family": self.family_summary(agent) if agent is not None else None,
            "venue": ev.venue, "venue_capital_usd": str(self.capital(ev.venue)), "venue_headroom_usd": str(self.headroom(ev.venue)),
            "venue_at_risk_usd": str(self.at_risk(ev.venue)), "seated_on_real_money_at_venue": seated,
            "fits": bool(self.headroom(ev.venue) >= stake),
            "tuition": {"max_loss_usd": str(self.grant_capital(ev.venue)), "max_agents": int(policy.get("max_agents") or 0),
                        "note": "the owner's live grant for this venue; the legacy $50 / 4-agent tuition does not apply under the allocator"},
            "live_grant": {k: policy.get(k) for k in ("max_agents", "stake_usd", "venue_capital_usd", "max_loss_usd")} if policy else None,
            "demotion": {"hysteresis": rules().get("hysteresis"), "real_drawdown_demote": rules().get("real_drawdown_demote"),
                         "reentry_cooldown_hours": rules().get("reentry_cooldown_hours")},
        }

    # ------------------------------------------------------------- the pass
    def rebalance(self) -> dict[str, Any]:
        """One pass: evidence for every living agent on rung 1+, band moves, stakes, the performance
        fee, and the board the site and the watch read. Called in the House's mark pass."""
        house = self.house
        if not enabled():
            return {"enabled": False}
        p = _params()
        summary: dict[str, Any] = {"moves": [], "sized": [], "deaths": [], "fees": 0}
        with house._lifecycle_lock:
            self._begin_pass()
            self._pay_fees(p, summary)
            throttle = self._throttle()
            living = [a for a in house.registry.living()]
            rungs = {a.id: house.evaluator.rung(a.id) for a in living}
            evid: dict[str, Evidence] = {}
            for agent in living:
                if rungs[agent.id] < 1:
                    continue
                try:
                    evid[agent.id] = evidence(house, agent, rungs[agent.id])
                except Exception as exc:  # noqa: BLE001 - one agent's unreadable record must not stop the pass
                    house.alert("warning", f"allocator: {agent.id}'s evidence could not be read ({type(exc).__name__}: {str(exc)[:160]})")
                    continue
                # Only a proven (or swinging) family's agent takes the agent-level swing (Sept 24, 2026), while the
                # constitution's `swing_requires_proven_family` says so; `family` never raises.
                evid[agent.id].family_proven = self.swing_allowed(agent) if rules().get("swing_requires_proven_family") else None
            self._evidence = evid
            live_ok = {v: self._live_open(v) for v in REAL_BOOK}
            # 1. Deaths on paper wealth.
            for agent in living:
                ev = evid.get(agent.id)
                if ev is None or ev.rung != 1:
                    continue
                if ev.paper_trades >= p["die_min_trades"] and ev.w_paper < p["die_below"]:
                    reason = (f"paper wealth {ev.w_paper:.4f} is below {p['die_below']:g} after {ev.paper_trades} closed trades: "
                              "evidence is wealth, and this record has spent it")
                    house.kill(agent, "evidence", reason)
                    summary["deaths"].append(agent.id)
            living = list(house.registry.living())
            # 2. Moves down first (they free capital), then up.
            for agent in living:
                ev = evid.get(agent.id)
                if ev is None or ev.rung < 2:
                    continue
                band, why = target_band(ev, p)
                if RUNG_OF[band] < ev.rung:
                    self._move_down(agent, ev, band, why, summary)
            # 3. Moves up, best evidence first, inside the envelope.
            ups = []
            for agent in living:
                ev = evid.get(agent.id)
                if ev is None or ev.rung not in (1, 2):
                    continue
                if house.evaluator.rung(agent.id) != ev.rung:
                    continue  # moved this pass
                band, why = target_band(ev, p)
                if RUNG_OF[band] > ev.rung:
                    ups.append((ev.e, agent, ev, band, why))
            ups.sort(key=lambda row: -row[0])
            displaced_at: set[str] = set()
            for _, agent, ev, band, why in ups:
                if not live_ok.get(agent.venue):
                    continue
                if band == "bunt":
                    self._bunt(agent, ev, why, p, summary, displaced_at)
                elif band == "swing":
                    self._swing(agent, ev, why, summary)
            # 4. Stakes follow the evidence.
            for agent in living:
                if house.registry.get(agent.id) is None or not house.registry.get(agent.id).alive:
                    continue
                rung = house.evaluator.rung(agent.id)
                ev = evid.get(agent.id)
                if rung >= 2 and ev is not None:
                    row = self._size(agent, ev, "swing" if rung >= 3 else "bunt", p)
                    if row:
                        summary["sized"].append(row)
            self._publish_board(evid, p, throttle)
            try:
                self._persist_families()
            except Exception as exc:  # noqa: BLE001 - the ledger's rows are a record; a failed write never stops a pass
                self._family_error("the family.record rows", "", exc)
            self._save()
        return summary

    def _live_open(self, venue: str) -> bool:
        house = self.house
        if not house.settings.real_money or REAL_BOOK[venue] not in house.books:
            return False
        if house.paused():
            return False
        guard = getattr(house, "campaigns", None)
        return not guard or guard.allows_live(2)

    def _numbers(self, ev: Evidence, band_from: str, band_to: str, stake: Decimal | None, why: str,
                 agent: Any = None) -> dict[str, Any]:
        """A band move's verdict numbers; a move to a probe or a bunt carries the family record that
        decided which (P1, Sept 24, 2026)."""
        out = {"via": "allocator", "band_from": band_from, "band_to": band_to,
               "stake_usd": None if stake is None else str(stake), "evidence": ev.row(), "reason_detail": why}
        if agent is not None and band_to in ("probe", "bunt", "swing"):
            out["family"] = self.family_summary(agent)
        return out

    def _move_down(self, agent: Any, ev: Evidence, band: str, why: str, summary: dict[str, Any]) -> None:
        house = self.house
        old = house.book_of(agent)
        band_from = self._band_now(agent, ev)
        target = RUNG_OF[band]
        if band == "bunt":
            band = self.rung2_band(agent)  # a swing lands on rung 2 as a probe, a bunt or a swinging family's member (Sept 24, 2026)
        numbers = self._numbers(ev, band_from, band, None, why)
        while house.evaluator.rung(agent.id) > max(target, 1):
            house.evaluator.demote(agent.id, why, numbers)
        if target <= 1 and old is not None and old.real_money:
            house._move_books(agent, old)
        elif old is not None:
            house.seat(agent)  # swing -> bunt: the same real book, the limits follow; the stake follows in _size
        summary["moves"].append({"agent": agent.id, "from": band_from, "to": band, "why": why})

    def _band_now(self, agent: Any, ev: Evidence) -> str:
        if ev.rung == 2:
            return self.rung2_band(agent)  # "probe", "bunt" or "swing" (Sept 24, 2026), as the board says it
        band = self._board["agents"].get(agent.id, {}).get("band")
        # The last board's band while it is still the agent's rung's (a star is a swing); else the rung's.
        return band if band is not None and RUNG_OF.get(band) == ev.rung else band_of_rung(ev.rung)

    def _bunt(self, agent: Any, ev: Evidence, why: str, p: Mapping[str, Any], summary: dict[str, Any], displaced_at: set[str]) -> None:
        house = self.house
        venue = agent.venue
        stake = self.target_stake(agent, "bunt", ev)  # what `seat` will lend: the same target
        source = house.book_of(agent)
        if source is not None and not source.evidence_integrity(agent.id)["ok"]:
            house._promotion_status(agent, _verdict(agent.id, 1, why, ev), "accounting_integrity",
                                    "the source record contains an unresolved position attribution defect")
            return
        if house.auditor is not None and audit_standing(house, agent) == "vetoed":
            wait = house._audit_wait(agent)
            if wait:
                house._promotion_status(agent, _verdict(agent.id, 1, why, ev), **wait)
                return  # a veto's cooldown holds a bunt, whoever the agent is
        defect = house._known_defect(agent) if house.auditor is not None else None
        if defect is not None:
            # An agent with a known defect is audited before any real dollar (the existing path:
            # approval commits the promotion, a veto keeps it on paper through the cooldown).
            verdict = _verdict(agent.id, 1, why, ev, self)
            generation = house._generation(agent.id)
            if generation is None:
                return
            inflight = house._audit_inflight(agent.id, generation)
            if inflight == "running":
                return
            if isinstance(inflight, dict):
                house._finish_audit(agent.id, verdict, generation, inflight)  # a verdict from before a restart
                return
            wait = house._audit_wait(agent)
            if wait:
                house._promotion_status(agent, verdict, **wait)
                return
            house._promotion_status(agent, verdict, "auditing", f"a known defect is audited before any real dollar ({defect})")
            house._start_audit(agent, verdict, generation)
            return
        if self.headroom(venue) < stake:
            newcomer = self.tier(agent)
            weakest = self._weakest_bunt(venue, ev.e, displaced_at, tier=newcomer, state=self.family_state(agent))
            if weakest is None:
                # The reason stays the same while the wait does (a `progress` row is written only when
                # it changes); the moving numbers ride along as detail.
                house._promotion_status(agent, _verdict(agent.id, 1, why, ev), "envelope",
                                        f"the {venue} envelope cannot seat another ${stake} {newcomer} and no weaker flat "
                                        + ("probe" if newcomer == "probe" else "bunt") + " can be displaced",
                                        capital_usd=str(self.capital(venue)), headroom_usd=str(self.headroom(venue)))
                return
            other, other_ev = weakest
            displaced_at.add(venue)
            self._move_down(other, other_ev, "paper", f"displaced by {agent.id} (E {ev.e:.4f} > {other_ev.e:.4f}): "
                                                        "the envelope seats the best evidence first", summary)
            if self.headroom(venue) < stake:
                return
        if not self.can_fund(venue, stake):
            house._promotion_status(agent, _verdict(agent.id, 1, why, ev), "venue_cash",
                                    f"the {venue} account's free cash cannot take another ${stake} stake now")
            return
        tier = self.rung2_band(agent)  # "probe", "bunt", or "swing" for a swinging family's newcomer (C2, Sept 24, 2026)
        numbers = self._numbers(ev, "paper", tier, stake, why, agent)
        house.evaluator.promote(agent.id, 2, f"{tier}: {why}; {self._family_note(agent)}", numbers)
        if source is not None:
            house._move_books(agent, source)  # winds the paper account down; seat() lends the bunt stake
        real = house.books.get(REAL_BOOK[venue])
        if real is None or not real.account(agent.id).funded:
            # The stake did not land: straight back, in the same pass, rather than hold an unfunded seat.
            house.evaluator.demote(agent.id, f"the {tier}'s stake could not be lent; back to paper", self._numbers(ev, tier, "paper", None, why))
            house.seat(agent)
            house.alert("warning", f"allocator: {agent.id}'s ${stake} {tier} could not be staked on {venue}; it stays on paper")
            return
        self._admit(agent)  # it shares its family's caps from now on in this pass (review of #242)
        house._promotion_status(agent, _verdict(agent.id, 1, why, ev), "promoted", f"the allocator seated it as a {tier}")
        summary["moves"].append({"agent": agent.id, "from": "paper", "to": tier, "why": why, "stake_usd": str(stake)})

    def _weakest_bunt(self, venue: str, e: float, displaced_at: set[str], *, tier: str = "bunt",
                      state: str | None = None) -> tuple[Any, Evidence] | None:
        """The flat rung-2 agent with the weakest E under `e` that a newcomer of `tier` may displace, or None.
        A probe displaces only a probe: an agent's own E on a few settlements is the statistic the family's
        proof replaced (the plan's gap 2), so it never sends a proven family's bunt back to practice to seat
        an unproven mechanism's pocket change (review of #224, Sept 24, 2026). A proven family's newcomer
        displaces either. With the newcomer's family `state` (C2, Sept 24, 2026) the same holds one step up:
        a proven family's newcomer never displaces a SWINGING family's member (the envelope would otherwise
        undo a family swing at every full pass); a swinging family's newcomer displaces any weaker one."""
        if venue in displaced_at:
            return None  # one displacement a venue a pass: no churn
        house = self.house
        book = house.books.get(REAL_BOOK[venue])
        best = None
        for agent_id, ev in getattr(self, "_evidence", {}).items():
            agent = house.registry.get(agent_id)
            if agent is None or not agent.alive or agent.venue != venue or house.evaluator.rung(agent_id) != 2:
                continue
            if ev.e >= e or book is None:
                continue
            if tier == "probe" and self.tier(agent) != "probe":
                continue  # capital follows proof: an unproven newcomer never displaces a proven family's bunt
            if state is not None and STATE_RANK.get(self.family_state(agent), 0) > STATE_RANK.get(state, 0):
                continue  # nor a proven family's newcomer a swinging family's member
            account = book.account(agent_id)
            if account.holdings or book.open_orders(agent_id):
                continue  # displacing never forces a sale
            if best is None or ev.e < best[1].e:
                best = (agent, ev)
        return best

    def _swing(self, agent: Any, ev: Evidence, why: str, summary: dict[str, Any]) -> None:
        """Bunt -> swing. The first entry into the swing band is audited (size is at stake); an agent
        with an approved audit on record goes straight up."""
        house = self.house
        verdict = _verdict(agent.id, 2, why, ev, self)
        guard = getattr(house, "campaigns", None)
        if guard and not guard.allows_live(3):
            house._promotion_status(agent, verdict, "campaign", "the live grant has not released the swing band")
            return
        approved = audit_standing(house, agent) == "approved"
        if not approved and house.auditor is not None:
            generation = house._generation(agent.id)
            if generation is None:
                return
            inflight = house._audit_inflight(agent.id, generation)
            if inflight == "running":
                return
            if isinstance(inflight, dict):
                house._finish_audit(agent.id, verdict, generation, inflight)
                return
            wait = house._audit_wait(agent)
            if wait:
                house._promotion_status(agent, verdict, **wait)
                return
            house._promotion_status(agent, verdict, "auditing", "the first entry into the swing band is audited")
            house._start_audit(agent, verdict, generation)
            return
        stake = self.target_stake(agent, "swing", ev)
        band_from = self._band_now(agent, ev)  # "probe" or "bunt": the tape says what the board said (review of #224)
        house.evaluator.promote(agent.id, 3, f"swing: {why}", self._numbers(ev, band_from, "swing", stake, why))
        house._promotion_status(agent, verdict, "promoted", "the allocator moved it to the swing band")
        summary["moves"].append({"agent": agent.id, "from": band_from, "to": "swing", "why": why, "stake_usd": str(stake)})

    def _size(self, agent: Any, ev: Evidence, band: str, p: Mapping[str, Any]) -> dict[str, Any] | None:
        """Move a real account's stake toward its target: up to the envelope's headroom, down by free
        cash only. Moves under `min_stake_change` of the equity are ignored."""
        from .book import BookError

        house = self.house
        book = house.book_of(agent)
        if book is None or not book.real_money:
            return None
        account = book.account(agent.id)
        if not account.funded:
            return None
        target = self.target_stake(agent, band, ev)
        equity = book.equity(agent.id)
        delta = target - equity
        if abs(delta) < max(equity, Decimal(1)) * _d(p["min_stake_change"]):
            return None
        if delta > 0:
            if band == "bunt" and p["bunt_growth"] == "w_real" and ev.w_real < 1.0:
                # A losing bunt is not refilled (Sept 23, 2026): its stake shrinks by what it lost,
                # and the stay drawdown, hysteresis and death decide the rest. Under the flat rule a
                # $10 bunt down to $9 was topped back up to $10 at every pass the loss cleared
                # `min_stake_change`. The stake at seating is `House.seat`'s, not this.
                # But a bunt lent LESS than today's base is lent up to it (Sept 23, 2026 ~21:30 UTC):
                # when Deploy A raised the Kalshi base $10 -> $30, every bunt seated at $10 with W_real a
                # hair under 1 stayed at $10 (meriwether-h2d625d: W_real 0.9978, stake $10, target $30),
                # and a bunt halved by the throttle stayed halved when it lifted (the #198 review, item
                # 4). So it is lent at most the target (here the base, or the throttle's half of it)
                # less what it has been lent net of every sweep (`account.staked`): lent $10 under a
                # $30 base it gets up to $20; lent the base and down to $27 it gets nothing. Its equity
                # and its net loan on the book never pass the target, and a loss (this stay's, or a
                # past stay's still counted in `staked`) is lent back only out of real profit the
                # account had already handed back (a sweep of profit lowers `staked`).
                delta = min(delta, target - account.staked)
                if delta <= 0:
                    return None
            room = self.headroom(agent.venue)
            delta = min(delta, max(room, ZERO)).quantize(CENT, rounding=ROUND_DOWN)
            if delta <= 0 or delta < max(equity, Decimal(1)) * _d(p["min_stake_change"]):
                return None
        else:
            free = account.cash - book._reserved_cash(agent.id)
            delta = -min(-delta, max(free, ZERO)).quantize(CENT, rounding=ROUND_DOWN)
            if delta == 0:
                return None
        try:
            book.stake(agent.id, delta, note=f"allocator: {band} stake toward ${target}")
        except BookError as exc:
            house.alert("warning", f"allocator: {agent.id}'s stake could not move by {delta} ({exc})")
            return None
        house.seat(agent)  # the limits follow the stake
        named = self.rung2_band(agent) if band == "bunt" else band  # a rung-2 stake is a probe's, a bunt's or a family swing's (Sept 24, 2026)
        row = {"band": named, "stake_usd": str(target), "moved_usd": str(delta), "equity_usd": str(equity.quantize(CENT)),
               "via": "allocator", "evidence": ev.row(),
               "reason": f"{named} stake follows the evidence (E {ev.e:.4f})" + (" and the floor throttle" if self.state.get("throttle") else "")}
        house.ledger.append("eval.verdict", {"decision": "size", "rung": house.evaluator.rung(agent.id), "book": book.name, **row}, agent=agent.id)
        return {"agent": agent.id, **row}

    # -------------------------------------------------------- performance fee
    def _pay_fees(self, p: Mapping[str, Any], summary: dict[str, Any]) -> None:
        """`performance_fee_share` of each realized real profit, as compute credits, once per row."""
        share = _d(p["performance_fee_share"])
        if share <= 0:
            return
        house = self.house
        if self.state.get("fee_cursor") is None:
            # Fees start with the allocator: profits before it was switched on are not back-paid.
            self.state["fee_cursor"] = int(house.ledger.head()[0])
            return
        cursor = int(self.state["fee_cursor"])
        last = cursor
        for entry in house.ledger.iter(kinds=("book.fill", "book.settle"), after=cursor):
            last = entry.seq
            payload = entry.payload
            if payload.get("book") not in REAL_BOOK.values() or entry.agent == HOUSE:
                continue
            made = payload.get("pnl") if entry.kind == "book.settle" else payload.get("realized")
            if made is None or payload.get("source") == "dust":
                continue
            profit = _d(made)
            if profit <= 0:
                continue
            fee = (profit * share).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
            if fee <= 0:
                continue
            house.economy.grant(entry.agent, fee, f"performance fee: {p['performance_fee_share']:.0%} of ${profit} realized real profit",
                                id=f"perf:{entry.id}")
            summary["fees"] += 1
        self.state["fee_cursor"] = last

    # ---------------------------------------------------------------- board
    def _publish_board(self, evid: Mapping[str, Evidence], p: Mapping[str, Any], throttle: bool) -> None:
        house = self.house
        agents: dict[str, Any] = {}
        swings = []
        for agent in house.registry.living():
            rung = house.evaluator.rung(agent.id)
            ev = evid.get(agent.id)
            band = band_of_rung(rung)
            stake = target = None
            if rung >= 2:
                book = house.book_of(agent)
                if book is not None and agent.id in book.accounts:
                    stake = max(book.account(agent.id).staked, ZERO)
                if ev is not None:  # the target the stake follows: the same number `seat_stake`, `limits` and `context` use
                    target = str(self.target_stake(agent, "swing" if rung >= 3 else "bunt", ev))
            if rung >= 3 and ev is not None and ev.w_real >= p["star_min_w_real"]:
                swings.append((ev.real_pnl, agent.id))
            record = self.family(agent.family, agent.venue)
            if rung == 2:
                band = self.rung2_band(agent)  # P1 and C2 (Sept 24, 2026): "probe", "bunt" or "swing", by the family's state
            # `league/publish.py` sends the site only the fields it knows: the family fields are for the
            # watch and the scoreboard until the site learns them (W). C4 (Sept 24, 2026): the family's state
            # in the mechanism ledger ("unproven", "proven", "swing"), its capacity estimate in dollars a day at
            # its stake and whether capacity holds the stake, and what set a family-swing member's stake.
            swing = record.get("swing") if record.get("state") == "swing" and rung >= 2 else None
            capacity = record.get("capacity") or {}
            usd = capacity.get("usd_per_day")
            agents[agent.id] = {"band": band, "stake_usd": stake, "target_usd": target, "evidence": ev.row() if ev else None,
                                "venue": agent.venue, "last_move": None, "family": agent.family,
                                # The HONEST bound (the t bound, and the loss-rate gate for a lopsided record): the one
                                # that proves the family. The t bound alone read weather favourites at +0.0033 while
                                # the proof read -0.2112 (C-site's finding, Sept 24, 2026).
                                "family_state": record["state"], "family_bound": record.get("honest_bound", record["bound"]),
                                "family_n": record["n"],
                                "capacity": {"usd_per_day": None if usd is None else round(float(usd), 4),
                                             "binds": bool(swing and swing.get("limit") == "capacity")},
                                "stake_limit": swing.get("limit") if swing else None}
        for _, agent_id in sorted(swings, reverse=True)[:p["stars"]]:
            agents[agent_id]["band"] = "star"
        moves = self._moves()
        for move in moves:
            if move["agent"] in agents:
                agents[move["agent"]]["last_move"] = {k: move[k] for k in ("at", "from_band", "to_band", "reason")}
        bands: dict[str, dict[str, Any]] = {}
        for row in agents.values():
            slot = bands.setdefault(row["venue"], {}).setdefault(row["band"], {"count": 0, "capital_usd": ZERO})
            slot["count"] += 1
            slot["capital_usd"] += row["stake_usd"] or ZERO
        envelope = sum((self.grant_capital(v) for v in REAL_BOOK), ZERO)
        board = {"enabled": True, "agents": agents, "moves": moves, "bands": bands, "families": self.families_board(),
                 "throttle": {"active": bool(throttle), "floor_pnl_usd": self.floor_pnl(), "envelope_usd": envelope},
                 "at": now_iso(house.clock),
                 "envelope": {v: {"capital_usd": str(self.capital(v)), "committed_usd": str(self.committed(v))} for v in REAL_BOOK
                              if house.books.get(REAL_BOOK[v]) is not None}}
        with self._lock:
            self._board = board
        now = house.clock()
        if now - float(self.state.get("last_board_at") or 0) >= 300:
            self.state["last_board_at"] = now
            compact = {a: [r["band"], None if r["stake_usd"] is None else str(r["stake_usd"]),
                           *( [r["evidence"]["W_paper"], r["evidence"]["W_real"], r["evidence"]["E"], r["evidence"]["trades"], r["evidence"]["real_trades"]]
                              if r["evidence"] else [])]
                       for a, r in agents.items() if r["band"] != "replay"}
            house.ledger.append("alloc.board", {"agents": compact, "throttle": bool(throttle),
                                                "envelope": board["envelope"]}, agent=HOUSE)
        try:
            tmp = self.path.with_name("allocator-board.tmp")
            tmp.write_text(json.dumps(board, default=str, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path.with_name("allocator-board.json"))
        except OSError:
            pass

    def _moves(self) -> list[dict[str, Any]]:
        """The last band moves, from the ledger (promote/demote rows the allocator wrote, and any
        other rung change, which is a band change too)."""
        house = self.house
        rows = house.ledger.read(kinds="eval.verdict", limit=4000, newest=True)
        out = []
        for entry in rows:
            payload = entry.payload
            if payload.get("decision") not in ("promote", "demote"):
                continue
            agent = house.registry.get(entry.agent)
            out.append({"id": entry.id, "at": entry.at, "agent": entry.agent,
                        "venue": getattr(agent, "venue", None) or "kalshi",
                        "from_band": payload.get("band_from") or band_of_rung(int(payload.get("from_rung") or 0)),
                        "to_band": payload.get("band_to") or band_of_rung(int(payload.get("to_rung") or 0)),
                        "stake_usd": payload.get("stake_usd"), "reason": str(payload.get("reason") or "")[:300]})
        return out[-MAX_MOVES:]

    def board(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._board)


def _verdict(agent_id: str, rung: int, why: str, ev: Evidence, allocator: "Allocator | None" = None):
    """The verdict the House's promotion and audit machinery take. `book` is the record the auditor
    reads: the paper record for a bunt audited first (a known defect), the REAL record for the first
    swing, where size is at stake (Sept 23, 2026 review: without it the packet was empty).

    `allocation_context` is what the auditor judges capacity against. Without it the auditor read
    the legacy tuition (4 agents, $50, a $60 stake) and vetoed the floor's two best paper agents on
    Sept 23 for capacity it could not see (09:32 and 10:06Z)."""
    from .evaluator import Verdict

    book = PAPER_BOOK[ev.venue] if rung <= 1 else REAL_BOOK[ev.venue]
    band = "bunt" if rung <= 1 else "swing"
    if band == "bunt" and allocator is not None:
        agent = allocator.house.registry.get(agent_id)
        band = allocator.rung2_band(agent) if agent is not None else band  # a probe, a bunt or a family swing's member (Sept 24, 2026)
    numbers: dict[str, Any] = {"via": "allocator", "book": book, "evidence": ev.row(), "E": ev.e, "band_to": band}
    if allocator is not None:
        numbers["allocation_context"] = allocator.context(ev, band)
    return Verdict(agent_id, rung, "eligible", why, numbers)
