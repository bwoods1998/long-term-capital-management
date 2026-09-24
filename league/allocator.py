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
from typing import Any, Mapping, NamedTuple

from . import stats
from .constitution import CONSTITUTION
from .ledger import HOUSE, now_iso

ZERO = Decimal(0)
CENT = Decimal("0.01")
BANDS = ("replay", "paper", "bunt", "swing", "star")
RUNG_OF = {"replay": 0, "paper": 1, "bunt": 2, "swing": 3, "star": 3}
PAPER_BOOK = {"alpaca": "alpaca-paper", "kalshi": "kalshi-shadow"}
REAL_BOOK = {"alpaca": "alpaca", "kalshi": "kalshi"}
EVENT_BOOKS = ("kalshi-shadow", "kalshi")
MAX_MOVES = 50
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

    def row(self) -> dict[str, Any]:
        return {"W_paper": round(self.w_paper, 6), "W_real": round(self.w_real, 6), "E": round(self.e, 6),
                "trades": int(self.paper_trades), "settled": int(self.paper_settled),
                "real_trades": int(self.real_trades), "real_pnl": round(self.real_pnl, 4),
                "real_drawdown": round(self.real_drawdown, 4)}


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
#: What the family record folds from the ledger (`TradeTape`): every agent's fills, settlements and
#: stakes, and the two kinds that move an agent's evidence cutoff (`accounting.evidence_cutoffs`).
TAPE_KINDS = ("book.fill", "book.settle", "book.stake", "book.fill_correction", "book.baseline")
_TAPE_FIELDS = ("book", "pnl", "realized", "source", "flat", "side", "cash_delta", "liquidity", "usd")
_TAPE_INSTRUMENT = ("market_id", "symbol", "right", "expiry", "strike", "event_ticker", "event")


class TapeRow(NamedTuple):
    seq: int
    kind: str
    payload: dict


class TradeTape:
    """Every agent's fills, settlements and stakes, read from the ledger BY KIND after a cursor and
    kept in a compact form, with each agent's evidence cutoffs folded exactly as
    `accounting.evidence_cutoffs` computes them (the latest correction or repair baseline on a book).

    The family record reads every member of a family, living or dead. Read agent by agent that was
    ~500 indexed reads a pass (1.4 s on the T0 snapshot of Sept 24, 2026); by kind it is one read of
    ~3,000 rows (0.09 s) once, then only the rows that are new at each pass."""

    def __init__(self) -> None:
        self.cursor = 0
        self.rows: dict[str, list[TapeRow]] = {}
        self.cutoffs: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    def refresh(self, ledger: Any) -> int:
        """Fold what is new on the ledger; the ledger position it now stands at."""
        with self._lock:
            for entry in ledger.iter(kinds=TAPE_KINDS, after=self.cursor):
                self._fold(entry)
                self.cursor = entry.seq
            return self.cursor

    def _cut(self, agent: Any, book: Any, seq: int) -> None:
        if agent and book:
            cuts = self.cutoffs.setdefault(str(agent), {})
            cuts[str(book)] = max(cuts.get(str(book), 0), seq)

    def _fold(self, entry: Any) -> None:
        p = entry.payload
        if entry.kind == "book.fill_correction":
            self._cut(entry.agent, p.get("book"), entry.seq)
        elif entry.kind == "book.baseline":
            for repair in p.get("repairs") or []:
                if isinstance(repair, Mapping):
                    self._cut(repair.get("agent"), p.get("book"), entry.seq)
        elif entry.agent != HOUSE:
            keep = {k: p[k] for k in _TAPE_FIELDS if k in p}
            instrument = p.get("instrument")
            if isinstance(instrument, Mapping):
                keep["instrument"] = {k: instrument[k] for k in _TAPE_INSTRUMENT if k in instrument}
            self.rows.setdefault(entry.agent, []).append(TapeRow(entry.seq, entry.kind, keep))


def _family_rule(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    rule = dict(rules(constitution).get("family_proven") or {})
    return {"min_independent_settlements": int(rule.get("min_independent_settlements", 10)),
            "practice_weight": float(rule.get("practice_weight", 0.5)), "real_weight": float(rule.get("real_weight", 1)),
            "confidence": float(rule.get("confidence", 0.8))}


def _log1p(r: float) -> float:
    """ln(1 + r), a whole loss or worse floored at `stats.RUIN` as `stats.log_growth` floors it; a
    return that is not a number (a malformed row) is no growth."""
    if r <= -1.0:
        return stats.RUIN
    return max(stats.RUIN, math.log1p(r)) if math.isfinite(r) else 0.0


def _pool(groups: Mapping[str, list[tuple[float, float]]], min_n: int, confidence: float) -> dict[str, Any]:
    """One observation per group (an event, or a trade where nothing groups them): the weighted mean
    of its members' values at the largest of their weights -- correlated bets are never counted as
    independent. Then the weighted mean m, the reliability-weighted sd s, n_eff = (sum w)^2 / sum w^2
    and the one-sided lower bound m - t(confidence, n_eff - 1) * s / sqrt(n_eff) on Student's t (the
    coordinator's precision, Sept 24, 2026; no bound under two effective observations). `positive`
    when there are `min_n` observations and the bound is above zero."""
    observations = []
    for units in groups.values():
        if units:
            total = sum(w for _, w in units)
            observations.append((math.fsum(v * w for v, w in units) / total, max(w for _, w in units)))
    out: dict[str, Any] = {"n": len(observations), "n_eff": 0.0, "mean_log": 0.0, "sd": None, "bound": None, "positive": False}
    if not observations:
        return out
    weight = math.fsum(w for _, w in observations)
    squares = math.fsum(w * w for _, w in observations)
    mean = math.fsum(v * w for v, w in observations) / weight
    n_eff = weight * weight / squares
    out.update(n_eff=n_eff, mean_log=mean)
    if n_eff >= 2:
        sd = math.sqrt(math.fsum(w * (v - mean) ** 2 for v, w in observations) / (weight - squares / weight))
        out.update(sd=sd, bound=mean - stats.t_quantile(confidence, n_eff - 1) * sd / math.sqrt(n_eff))
    out["positive"] = bool(out["n"] >= min_n and out["bound"] is not None and out["bound"] > 0)
    return out


def family_record(house: Any, family: str, venue: str, *, tape: TradeTape | None = None,
                  through: int | None = None) -> dict[str, Any]:
    """A family's pooled forward record (P1, the close-the-gaps run, Sept 24, 2026): the proof that
    moves a family's real stakes from probes to bunts. Read-only; a pure function of the ledger and
    the registry. The scoreboard (`scripts/gap_scoreboard.py`) implements the same definition:

    - members: every agent ever born into `family` on `venue`, living or dead;
    - observations: one per distinct EVENT (`evaluator.event_key`) that any member closed -- settled,
      or sold flat -- on the practice book or the real book since that member's evidence cutoff; on
      Alpaca, where nothing groups trades, one per closed trade. A member's value on an event is the
      sum of the log growths ln(1 + r) of its closed trades there, r as `Evaluator.trade_returns`
      computes it read through this pass's fixed ledger position (`through`): a trade's result over
      the most the member was ever lent on that book, so a sweep or a death never erases or rescales
      a closed trade;
    - an event several members traded is ONE observation: the weighted mean of their values (real at
      `real_weight`, practice at `practice_weight`) at the largest weight among them (`_pool`);
    - pooled: mean, sd, n_eff and the one-sided `confidence` lower bound; `proven` with at least
      `min_independent_settlements` observations and the bound above zero;
    - the maker and taker records apart: a member's observation is "taker" when its first entry fill
      on that event (on that trade, on Alpaca) was a taker fill (`book.fill` `liquidity`).
    """
    from .evaluator import closed_trade_rows, event_key, per_event, staked_base

    tape = tape if tape is not None else TradeTape()
    head = tape.refresh(house.ledger)
    through = head if through is None else min(int(through), head)
    rule = _family_rule()
    books = {PAPER_BOOK[venue]: rule["practice_weight"], REAL_BOOK[venue]: rule["real_weight"]}
    registry = house.registry
    with (getattr(registry, "_lock", None) or contextlib.nullcontext()):
        members = sorted(a.id for a in list(registry.agents.values()) if a.family == family and a.venue == venue)
    units: dict[str, list[tuple[float, float, str, str]]] = {}
    real_keys: set[str] = set()
    for member in members:
        rows = tape.rows.get(member) or []
        cutoffs = tape.cutoffs.get(member) or {}
        for book, weight in books.items():
            stakes = [(r.seq, float(r.payload.get("usd") or 0)) for r in rows if r.kind == "book.stake" and r.payload.get("book") == book]
            staked = staked_base(stakes, through)
            if staked <= 0:
                continue  # never lent anything on this book: no record there
            closed, _ = closed_trade_rows((r for r in rows if r.kind != "book.stake"), book,
                                          since_seq=cutoffs.get(book, 0), until_seq=through)
            by_event = per_event(book)
            mine: dict[str, list[Any]] = {}  # observation -> [sum of log growths, (first entry seq, its liquidity)]
            for row in closed:
                key = (event_key(row["instrument"]) if by_event else None) or f"{book}:{member}:{row['seq']}"
                unit = mine.setdefault(key, [0.0, (math.inf, "taker")])
                unit[0] += _log1p(row["made"] / staked)
                entry = (row["entry_seq"] if row["entry_seq"] is not None else row["seq"], row["liquidity"])
                if entry[0] < unit[1][0]:
                    unit[1] = entry
            for key, (value, (_, liquidity)) in mine.items():
                units.setdefault(key, []).append((value, weight, liquidity, member))
                if book == REAL_BOOK[venue]:
                    real_keys.add(key)
    minimum, confidence = rule["min_independent_settlements"], rule["confidence"]

    def side(liquidity: str | None) -> dict[str, Any]:
        chosen = {k: [u for u in group if liquidity is None or (u[2] == "taker") == (liquidity == "taker")] for k, group in units.items()}
        pooled = _pool({k: [(u[0], u[1]) for u in group] for k, group in chosen.items()}, minimum, confidence)
        pooled["members"] = len({u[3] for group in chosen.values() for u in group})
        return pooled

    whole = side(None)
    return {"family": family, "venue": venue, "through": through, "members": len(members),
            "members_counted": whole.pop("members"), "n": whole["n"], "n_eff": whole["n_eff"], "mean_log": whole["mean_log"],
            "sd": whole["sd"], "bound": whole["bound"], "proven": whole["positive"],
            "state": "proven" if whole["positive"] else "unproven", "real_n": len(real_keys),
            "maker": side("maker"), "taker": side("taker"), "rule": rule}


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
    before the agent last adopted code does not speak for the code it runs now)."""
    adopted = house.ledger.last("agent.strategy", agent=agent.id)
    since = adopted.seq if adopted is not None else 0
    latest = None
    for entry in house.ledger.iter(kinds="audit.verdict", agent=agent.id, after=since):
        if not entry.payload.get("error"):
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
                    real_seen=seen, cooling=cooling)


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
    if ev.e < p["bunt_at"] * p["hysteresis"]:
        return "paper", f"E {ev.e:.4f} fell below {p['bunt_at'] * p['hysteresis']:.4f} (the bunt line with hysteresis)"
    if rung == 2:
        if swing_ready(ev, p) and not ev.cooling:
            return "swing", (f"E {ev.e:.4f} is at or above {p['swing_at']:g}, W_real {ev.w_real:.4f}, "
                             f"{ev.real_trades} real closed trades")
        return "bunt", "holds the bunt band"
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


def limits_for(stake: Decimal, venue: str, *, order_cap: Decimal | None = None) -> tuple[Decimal, Decimal]:
    """(max position, max order) for a real account staked `stake`: `position_share` of the stake,
    never under the venue's minimum order (Alpaca crypto takes nothing under $10), and every order
    within the gateway's per-order cap."""
    p = _params()
    cap = order_cap if order_cap is not None else _d(CONSTITUTION["order_caps"]["max_order_usd"])
    if order_cap is None and venue == "alpaca":
        # The gateway counts an Alpaca market order at the touch plus ten per cent
        # (`book.GATEWAY_MARKET_MARKUP`): an entry over $68.18 at the ask is over its $75 cap.
        from .book import GATEWAY_MARKET_MARKUP

        cap = (cap / GATEWAY_MARKET_MARKUP).quantize(CENT, rounding=ROUND_DOWN)
    # A fifth above the venue's minimum: a minimum-sized order must still fit after its fee and a
    # price-grid step (Alpaca takes no crypto order under $10; a $15 bunt must be able to place one).
    minimum = (_d((rules().get("venue_minimum_usd") or {}).get(venue, "1")) * _d("1.2")).quantize(CENT)
    position = max((stake * _d(p["position_share"])).quantize(CENT, rounding=ROUND_DOWN), minimum)
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

    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        state.setdefault("throttle", False)
        state.setdefault("fee_cursor", None)
        state.setdefault("last_board_at", 0.0)
        return state

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, sort_keys=True), encoding="utf-8")
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

    # ------------------------------------------------------------- stakes
    def target_stake(self, agent: Any, band: str, ev: Evidence | None = None) -> Decimal:
        p = _params()
        base = p["bunt_usd"].get(agent.venue, _d("10"))
        niche = self.house.niche_of(agent)
        if niche is not None and niche.asset_class == "option":
            # One option contract cannot be cut smaller: an options bunt is one contract's premium,
            # and since Sept 23, 2026 (A2a) `option_bunt_usd`, $80: the book holds a position and an
            # order to half the account's equity, so at $40 the $40 contract the bunt was staked for
            # could never be bought and the chain was filtered at contracts the book refused.
            base = max(base, p["option_bunt_usd"])
            p = {**p, "bunt_usd": {**p["bunt_usd"], agent.venue: base}}
        if band in ("swing", "star") and ev is not None:
            stake = swing_stake(ev, self.capital(agent.venue), p)
        else:
            stake = bunt_stake(ev, base, p)
        if self.state.get("throttle"):
            # Halved, but never under the smallest stake that can still trade: a position is at most
            # `position_share` of the stake and must hold the venue's minimum order (x1.2), or the
            # seat would hold capital and never open anything (Sept 23, 2026 review).
            tradable = (_d((rules().get("venue_minimum_usd") or {}).get(agent.venue, "1")) * _d("1.2") / _d(p["position_share"])).quantize(CENT)
            stake = max((stake / 2).quantize(CENT, rounding=ROUND_DOWN), min(tradable, stake))
        return stake

    def seat_stake(self, agent: Any) -> Decimal:
        """The stake a newly seated real account is lent (House.seat)."""
        ev = self._evidence.get(agent.id)
        rung = self.house.evaluator.rung(agent.id)
        band = "swing" if rung >= 3 else "bunt"
        return self.target_stake(agent, band, ev)

    def limits(self, agent: Any, staked: Decimal) -> tuple[Decimal, Decimal]:
        target = self.seat_stake(agent)
        return limits_for(max(staked, target) if staked > 0 else target, agent.venue)

    # ---------------------------------------------------- facts for the books
    def band_of(self, agent_id: str) -> str | None:
        """The band an agent stands in, for the real book's daily-loss rule (constitution
        `allocator.bunt_daily_loss`): "bunt" on rung 2, "swing" on rung 3 (a star is a swing), None
        below real money or while the allocator is off, when the book's own rule stands. The rung is
        read, not the board: a promotion, a demotion by drift or a veto moves the rung at once and
        the board only at the next pass."""
        if not enabled():
            return None
        rung = self.house.evaluator.rung(agent_id)
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
        return {
            "allocator": "capital is the ladder (league/allocator.py): stakes follow evidence inside the grant's per-venue envelope",
            "band_to": band, "stake_usd": str(stake), "max_position_usd": str(position), "max_order_usd": str(order),
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

    def _numbers(self, ev: Evidence, band_from: str, band_to: str, stake: Decimal | None, why: str) -> dict[str, Any]:
        return {"via": "allocator", "band_from": band_from, "band_to": band_to,
                "stake_usd": None if stake is None else str(stake), "evidence": ev.row(), "reason_detail": why}

    def _move_down(self, agent: Any, ev: Evidence, band: str, why: str, summary: dict[str, Any]) -> None:
        house = self.house
        old = house.book_of(agent)
        band_from = self._band_now(agent, ev)
        target = RUNG_OF[band]
        numbers = self._numbers(ev, band_from, band, None, why)
        while house.evaluator.rung(agent.id) > max(target, 1):
            house.evaluator.demote(agent.id, why, numbers)
        if target <= 1 and old is not None and old.real_money:
            house._move_books(agent, old)
        elif old is not None:
            house.seat(agent)  # swing -> bunt: the same real book, the limits follow; the stake follows in _size
        summary["moves"].append({"agent": agent.id, "from": band_from, "to": band, "why": why})

    def _band_now(self, agent: Any, ev: Evidence) -> str:
        return self._board["agents"].get(agent.id, {}).get("band") or band_of_rung(ev.rung)

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
            weakest = self._weakest_bunt(venue, ev.e, displaced_at)
            if weakest is None:
                # The reason stays the same while the wait does (a `progress` row is written only when
                # it changes); the moving numbers ride along as detail.
                house._promotion_status(agent, _verdict(agent.id, 1, why, ev), "envelope",
                                        f"the {venue} envelope cannot seat another ${stake} bunt and no weaker flat bunt can be displaced",
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
        numbers = self._numbers(ev, "paper", "bunt", stake, why)
        house.evaluator.promote(agent.id, 2, f"bunt: {why}", numbers)
        if source is not None:
            house._move_books(agent, source)  # winds the paper account down; seat() lends the bunt stake
        real = house.books.get(REAL_BOOK[venue])
        if real is None or not real.account(agent.id).funded:
            # The stake did not land: straight back, in the same pass, rather than hold an unfunded seat.
            house.evaluator.demote(agent.id, "the bunt's stake could not be lent; back to paper", self._numbers(ev, "bunt", "paper", None, why))
            house.seat(agent)
            house.alert("warning", f"allocator: {agent.id}'s ${stake} bunt could not be staked on {venue}; it stays on paper")
            return
        house._promotion_status(agent, _verdict(agent.id, 1, why, ev), "promoted", "the allocator seated it as a bunt")
        summary["moves"].append({"agent": agent.id, "from": "paper", "to": "bunt", "why": why, "stake_usd": str(stake)})

    def _weakest_bunt(self, venue: str, e: float, displaced_at: set[str]) -> tuple[Any, Evidence] | None:
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
        house.evaluator.promote(agent.id, 3, f"swing: {why}", self._numbers(ev, "bunt", "swing", stake, why))
        house._promotion_status(agent, verdict, "promoted", "the allocator moved it to the swing band")
        summary["moves"].append({"agent": agent.id, "from": "bunt", "to": "swing", "why": why, "stake_usd": str(stake)})

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
        row = {"band": band, "stake_usd": str(target), "moved_usd": str(delta), "equity_usd": str(equity.quantize(CENT)),
               "via": "allocator", "evidence": ev.row(),
               "reason": f"{band} stake follows the evidence (E {ev.e:.4f})" + (" and the floor throttle" if self.state.get("throttle") else "")}
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
            agents[agent.id] = {"band": band, "stake_usd": stake, "target_usd": target, "evidence": ev.row() if ev else None,
                                "venue": agent.venue, "last_move": None}
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
        board = {"enabled": True, "agents": agents, "moves": moves, "bands": bands,
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
    numbers: dict[str, Any] = {"via": "allocator", "book": book, "evidence": ev.row(), "E": ev.e, "band_to": band}
    if allocator is not None:
        numbers["allocation_context"] = allocator.context(ev, band)
    return Verdict(agent_id, rung, "eligible", why, numbers)
