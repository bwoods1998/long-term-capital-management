"""The mechanism ledger (C1 of the close-the-gaps run, Sept 24, 2026; docs/goals/LTCM_CLOSE_THE_GAPS.md).

A FAMILY is a mechanism: every agent ever born with the same `family` on one venue, living or dead.
Its pooled forward record is the proof that moves real money, and this module is the one place
that record is computed. Every reader reads it here: the allocator (probe, bunt or family swing, and
the book's taker rule through `Allocator.family_taker`), the board and the site, the House's
births (`Allocator.family_forward`, a drop-in for `House.family_forward`), the foundry (through
the House's `_losing_family`), and the lab's lineage weights (`Allocator.family_score`).

- **The record** (`family_record`): one observation per independent EVENT (`evaluator.event_key`;
  an Alpaca closed trade is its own event) that any member closed, settled or sold flat, on the
  practice book (weight `practice_weight`, 0.5) or the real book (`real_weight`, 1) since that
  member's evidence cutoff; an event several members traded is one observation at the largest of
  their weights; the weighted mean, the reliability-weighted sd, n_eff and the one-sided lower
  bound on Student's t, and for a LOPSIDED record (80% or more winning) the House's exact
  loss-rate bound beside it (`stats.lopsided_growth_lcb`). The maker and taker records apart, the
  REAL-only record the family swing reads, every member's active blocks, and the capacity estimate.
- **The unit of an observation** (`family_proven.unit`). "account" (Deploy A) is the member's
  account growth, ln(1 + made / lent). "at_risk" (Deploy B, Sept 24, 2026) is what the event made
  per dollar its positions put at risk, as the log growth of a small reference bet:
  ln(1 + f x r) / f with r = made / at risk (never below -1: a contract that expires worthless is
  -100% of its position, a finite -1.005 at f = 1%, not the account's ruin). Measured on the T0
  snapshot (2026-09-24 01:42Z): practice rows were growth on a $200 purse and real rows on a
  $30-60 stake, so a real row counted three to seven times its declared weight
  (weather-favorites risked a median 9.25% of the purse a practice event and 31.7% of the stake
  a real one), and the account unit moves with the stake itself: a family swing that doubles a
  member's stake would halve that member's growth per event and pull its own bound down. The
  at-risk unit is scale-free across purses, stakes and books, so the table's weights mean what
  they say, and `bound / variance` in it is the Kelly fraction of capital at risk an event.
  The effect at T0, both units computed on the same events: weather-favorites unproven in both
  (loss-rate gate -0.0125 account, -0.2114 at risk: 2 losses in 16); sports-central-run-under
  proven on account growth (+0.0058) and unproven at risk (-0.1190): 6 of 11 practice events won
  at about even money after a 7% taker fee, and its account-growth proof came from buying two
  strikes on the games it won and one on those it lost. Every other family's state is the same.
- **The states** (`FamilyBook`): "unproven"; "proven" (`allocator.family_proven`: probes become
  bunts); "swing" (`allocator.family_swing`: the REAL record has `min_real_settlements` or more
  independent settlements and its honest lower bound -- the t bound, and the loss-rate bound for a
  lopsided record -- is above zero, and the family's first entry has an approved audit). Each
  state carries its `since`; `family.record` ledger rows carry the ledger at most every five
  minutes, a row for each family whose record changed.
- **The family swing's stake** (`swing_target`): per member on real money, min(the ramp, the
  family's caps / its members on real money), never under the bunt. The ramp starts at
  `start_multiple` x `bunt_usd` when the family enters the swing and doubles after every
  `doubling_every` further POSITIVE independent real settlements while the bound stays above zero;
  it holds where the fill rate at the next size is under `capacity_fill_ratio` of the fill rate at
  the size before (the board says "capacity"). The family's caps are full Kelly on the honest
  bound against the venue's capital (the constitution's rung-3 `kelly_fraction`) and
  `max_share_of_venue` of it: FAMILY caps, shared by its members, because members of one family
  bid the same markets (mullins-2 and mullins-6 both held KXRAIN-26SEP22-SATX on real money): two
  members each at full Kelly on the family's bound are twice Kelly on one mechanism.

A money judge: `league/ci.py` forbids Merton's pull requests to touch it.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import threading
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any, Iterable, Mapping, NamedTuple, Sequence

from . import stats
from .constitution import CONSTITUTION
from .ledger import HOUSE

CENT = Decimal("0.01")
PAPER_BOOK = {"alpaca": "alpaca-paper", "kalshi": "kalshi-shadow"}
REAL_BOOK = {"alpaca": "alpaca", "kalshi": "kalshi"}
REAL_BOOKS = tuple(REAL_BOOK.values())
STATES = ("unproven", "proven", "swing")
#: What the tape folds from the ledger: every agent's fills, settlements and stakes, the two kinds that
#: move an agent's evidence cutoff (`accounting.evidence_cutoffs`), the House's orders (the buys a family
#: placed: its capacity) and the evaluator's blocks (every member's active blocks).
TAPE_KINDS = ("book.fill", "book.settle", "book.stake", "book.fill_correction", "book.baseline", "book.order", "eval.block")
_TAPE_FIELDS = ("book", "pnl", "realized", "source", "flat", "side", "cash_delta", "liquidity", "usd", "quantity", "price", "order_id")
_TAPE_INSTRUMENT = ("market_id", "symbol", "right", "expiry", "strike", "event_ticker", "event", "multiplier", "asset_class")
#: Bid-size buckets for fill rates, the scoreboard's (`scripts/gap_scoreboard.py`): the weather favourites
#: bid about $10 a market, and a swing's positions step through these as its stake doubles.
SIZE_BUCKETS = ((12.0, "<=$12"), (25.0, "$12-25"), (50.0, "$25-50"), (math.inf, ">$50"))
DAY = 86400.0
#: How long a bid is kept on the tape: the longest capacity window allowed, and a day more.
BID_DAYS = 15.0
#: How often a family's record is written to the ledger at most (`family.record`).
PERSIST_SECONDS = 300.0


def _epoch(at: Any) -> float:
    try:
        return datetime.fromisoformat(str(at).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def instrument_key(instrument: Mapping[str, Any] | None) -> str:
    """The instrument key a closed trade carries (`evaluator.closed_trade_rows`)."""
    inst = instrument or {}
    return ":".join(str(inst.get(k)) for k in ("market_id", "symbol", "right", "expiry", "strike") if inst.get(k) is not None)


# ------------------------------------------------------------------------------------ the tape
class TapeRow(NamedTuple):
    seq: int
    kind: str
    payload: dict
    at: float = 0.0


class Bid(NamedTuple):
    """One buy order the House placed for a member (`book.order`, its first row): what a family's capacity
    is measured from."""
    seq: int
    at: float
    book: str
    market: str
    notional: float | None
    order_id: str


class TradeTape:
    """Every agent's fills, settlements and stakes, the House's buy orders by member, and every agent's
    blocks, read from the ledger BY KIND after a cursor and kept in a compact form, with each agent's
    evidence cutoffs folded exactly as `accounting.evidence_cutoffs` computes them (the latest
    correction or repair baseline on a book).

    The family record reads every member of a family, living or dead. Read agent by agent that was
    ~500 indexed reads a pass (1.4 s on the T0 snapshot of Sept 24, 2026); by kind it is one read of the
    kinds once (about 1 s for 25,000 rows at T0), then only the rows that are new at each pass."""

    def __init__(self) -> None:
        self.cursor = 0
        self.rows: dict[str, list[TapeRow]] = {}
        self.cutoffs: dict[str, dict[str, int]] = {}
        self.bids: dict[str, list[Bid]] = {}
        self.blocks: dict[str, list[tuple[int, str, bool, float]]] = {}  # (seq, book, active, log growth)
        self.filled: dict[str, float] = {}  # order id -> when a buy fill named it
        self.last_seq: dict[str, int] = {}  # agent -> the newest row folded for it: a family's version
        self.newest_at = 0.0
        self._orders: dict[str, float] = {}  # order ids already folded (an order has several rows)
        self._lock = threading.Lock()

    def refresh(self, ledger: Any) -> int:
        """Fold what is new on the ledger; the ledger position it now stands at."""
        with self._lock:
            for entry in ledger.iter(kinds=TAPE_KINDS, after=self.cursor):
                self._fold(entry)
                self.cursor = entry.seq
            self._prune()
            return self.cursor

    def _touch(self, agent: Any, seq: int) -> None:
        if agent:
            self.last_seq[str(agent)] = max(self.last_seq.get(str(agent), 0), seq)

    def _cut(self, agent: Any, book: Any, seq: int) -> None:
        if agent and book:
            cuts = self.cutoffs.setdefault(str(agent), {})
            cuts[str(book)] = max(cuts.get(str(book), 0), seq)
            self._touch(agent, seq)

    def _fold(self, entry: Any) -> None:
        p = entry.payload
        at = _epoch(getattr(entry, "at", None))
        self.newest_at = max(self.newest_at, at)
        if entry.kind == "book.fill_correction":
            self._cut(entry.agent, p.get("book"), entry.seq)
        elif entry.kind == "book.baseline":
            for repair in p.get("repairs") or []:
                if isinstance(repair, Mapping):
                    self._cut(repair.get("agent"), p.get("book"), entry.seq)
        elif entry.kind == "book.order":
            self._fold_order(entry, p, at)
        elif entry.kind == "eval.block":
            if entry.agent != HOUSE:
                with contextlib.suppress(TypeError, ValueError):
                    self.blocks.setdefault(entry.agent, []).append(
                        (entry.seq, str(p.get("book") or ""), bool(p.get("active")), float(p.get("log_growth") or 0.0)))
                    self._touch(entry.agent, entry.seq)
        elif entry.agent != HOUSE:
            keep = {k: p[k] for k in _TAPE_FIELDS if k in p}
            instrument = p.get("instrument")
            if isinstance(instrument, Mapping):
                keep["instrument"] = {k: instrument[k] for k in _TAPE_INSTRUMENT if k in instrument}
            self.rows.setdefault(entry.agent, []).append(TapeRow(entry.seq, entry.kind, keep, at))
            self._touch(entry.agent, entry.seq)
            if entry.kind == "book.fill" and p.get("side") == "buy" and p.get("order_id") and p.get("source") in ("venue", "cross"):
                self.filled[str(p["order_id"])] = at

    def _fold_order(self, entry: Any, p: Mapping[str, Any], at: float) -> None:
        """A buy order's first row: one bid per member's share, at its limit (or reference) price."""
        order_id = str(p.get("order_id") or "")
        if p.get("side") != "buy" or not order_id or order_id in self._orders:
            return
        self._orders[order_id] = at
        inst = p.get("instrument") or {}
        market = str(inst.get("market_id") or inst.get("symbol") or "")
        try:
            price = float(p.get("limit_price") if p.get("limit_price") is not None else p.get("reference_price"))
            multiplier = float(inst.get("multiplier") or 1)
        except (TypeError, ValueError):
            price, multiplier = None, 1.0
        for share in p.get("shares") or []:
            if not isinstance(share, Mapping) or not share.get("agent"):
                continue
            try:
                notional = abs(float(share.get("quantity")) * price * multiplier) if price is not None else None
            except (TypeError, ValueError):
                notional = None
            agent = str(share["agent"])
            self.bids.setdefault(agent, []).append(Bid(entry.seq, at, str(p.get("book") or ""), market, notional, order_id))
            self._touch(agent, entry.seq)

    def _prune(self) -> None:
        """Bids older than `BID_DAYS` measure no window; their order ids go with them."""
        if not self.newest_at:
            return
        oldest = self.newest_at - BID_DAYS * DAY
        for agent in list(self.bids):
            kept = [b for b in self.bids[agent] if b.at >= oldest]
            if kept:
                self.bids[agent] = kept
            else:
                del self.bids[agent]
        for table in (self._orders, self.filled):
            for key in [k for k, t in table.items() if t < oldest]:
                del table[key]

    def version(self, members: Iterable[str]) -> tuple:
        """What a family's record depends on: its members and the newest row folded for any of them."""
        ids = tuple(sorted(members))
        return ids, max((self.last_seq.get(m, 0) for m in ids), default=0)


# ------------------------------------------------------------------------------------ the rules
def proof_rule(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """`allocator.family_proven`, with the defaults of its first form (Deploy A): without `unit` a row is
    the member's account growth, as before the at-risk unit."""
    allocator = (constitution or CONSTITUTION).get("allocator") or {}
    rule = dict(allocator.get("family_proven") or {})
    unit = str(rule.get("unit") or "account")
    return {"min_independent_settlements": int(rule.get("min_independent_settlements", 10)),
            "practice_weight": float(rule.get("practice_weight", 0.5)), "real_weight": float(rule.get("real_weight", 1)),
            "confidence": float(rule.get("confidence", 0.8)),
            # The House's loss-rate bound for a lopsided record, beside the t bound (Sept 24, 2026; the
            # constitution's comment has the evidence). Absent or false: the t bound alone.
            "lopsided_gate": rule.get("lopsided_gate") is True,
            "unit": unit if unit in ("account", "at_risk") else "account",
            "reference_share": float(rule.get("reference_share", 0.01))}


def swing_rule(constitution: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """`allocator.family_swing` (Deploy B, Sept 24, 2026), or None where the constitution has none: no
    family swing, and the agent-level swing (`swing_at`) is the only route above the bunt."""
    c = constitution or CONSTITUTION
    allocator = c.get("allocator") or {}
    rule = allocator.get("family_swing")
    if not isinstance(rule, Mapping):
        return None
    return {"min_real_settlements": int(rule.get("min_real_settlements", 15)),
            "start_multiple": float(rule.get("start_multiple", 2)), "doubling_every": max(1, int(rule.get("doubling_every", 10))),
            "capacity_fill_ratio": float(rule.get("capacity_fill_ratio", 0.5)),
            "capacity_min_markets": int(rule.get("capacity_min_markets", 5)),
            "capacity_days": float(rule.get("capacity_days", 7)),
            # Full Kelly on the lower bound, as the constitution's scaled rung (`rungs.3.kelly_fraction`).
            "kelly_fraction": float((c.get("rungs") or {}).get("3", {}).get("kelly_fraction", 1.0)),
            "max_share_of_venue": float(allocator.get("max_share_of_venue", 0.6))}


def position_share(venue: str, constitution: Mapping[str, Any] | None = None) -> float:
    """The share of a real stake one position may hold at `venue`: `position_share_event` on an event book
    (Kalshi), `position_share` elsewhere (`allocator._position_share`)."""
    allocator = (constitution or CONSTITUTION).get("allocator") or {}
    if REAL_BOOK.get(venue) == "kalshi":
        return float(allocator.get("position_share_event") or allocator.get("position_share", 0.5))
    return float(allocator.get("position_share", 0.5))


def event_share(venue: str, constitution: Mapping[str, Any] | None = None) -> float:
    """The most of a real stake one EVENT may put at risk at `venue`: on an event book the larger of a position's share
    and the real book's `max_event_share` (the book lets several strikes of one event hold that much of the equity
    together, and the at-risk unit measures an event, not a position), elsewhere a position's share (an Alpaca trade is
    its own event). Kelly's fraction of capital at risk an event becomes a stake through it (review of #242, Sept 24,
    2026: through the position's 20% a Kelly-capped member could put 25% of its stake, 1.25 x Kelly, on one event)."""
    allocator = (constitution or CONSTITUTION).get("allocator") or {}
    share = position_share(venue, constitution)
    if REAL_BOOK.get(venue) == "kalshi":
        share = max(share, float(allocator.get("max_event_share") or 0.0))
    return share


# ----------------------------------------------------------------------------------- statistics
def log1p(r: float) -> float:
    """ln(1 + r), a whole loss or worse floored at `stats.RUIN` as `stats.log_growth` floors it; a
    return that is not a number (a malformed row) is no growth."""
    if r <= -1.0:
        return stats.RUIN
    return max(stats.RUIN, math.log1p(r)) if math.isfinite(r) else 0.0


def at_risk_value(made: float, at_risk: float, share: float) -> float:
    """An event's value in the at-risk unit: ln(1 + share x r) / share, r = made / at_risk and never below -1
    (a long position cannot lose more than it put at risk; an exit fee past a worthless contract is still
    that). Finite: a total loss is ln(1 - share) / share (-1.005 at 1%). A row with nothing on record at
    risk counts as a total loss if it lost and a scratch otherwise: never as a win."""
    if at_risk > 0 and math.isfinite(made) and math.isfinite(at_risk):
        r = max(made / at_risk, -1.0)
    else:
        r = -1.0 if made < 0 else 0.0
    return math.log1p(share * r) / share


def pool(groups: Mapping[str, list[tuple[float, float]]], min_n: int, confidence: float, *,
         win_rate: float | None = None, risk: float = 1.0, scale: float = 1.0) -> dict[str, Any]:
    """One observation per group (an event, or a trade where nothing groups them): the weighted mean
    of its members' values at the largest of their weights -- correlated bets are never counted as
    independent. Then the weighted mean m, the reliability-weighted sd s, n_eff = (sum w)^2 / sum w^2
    and the one-sided lower bound m - t(confidence, n_eff - 1) * s / sqrt(n_eff) on Student's t (no
    bound under two effective observations). `positive` when there are `min_n` observations and the
    bound is above zero.

    With `win_rate` (the ladder's `lopsided_win_rate`), a LOPSIDED record -- that share or more of its
    observations winning: favourites, many small wins and a rare whole loss -- must also clear the
    House's exact loss-rate gate at the same confidence (`stats.lopsided_growth_lcb`, the rule
    `Evaluator._judge_family` and `judge` apply beside their t bounds): until a loss is on the record
    a t bound is badly anti-conservative. Review of #224, Sept 24, 2026: an edgeless 93c favourites
    family passes the t bound alone at its 10th observation about half the time. The gate reads each
    observation as the log growth of an account (`scale` converts an at-risk value back to it: the
    reference bet's share) that puts `risk` of itself at risk, and is returned in the record's unit.

    Also `honest_bound` (the t bound and, for a lopsided record, the gate: the smaller), and `variance`
    for Kelly: the sample variance, and for a lopsided record at least the variance of a record whose
    loss rate is the gate's upper bound and whose every loss is whole."""
    observations = []
    for units in groups.values():
        if units:
            total = sum(w for _, w in units)
            observations.append((math.fsum(v * w for v, w in units) / total, max(w for _, w in units)))
    out: dict[str, Any] = {"n": len(observations), "n_eff": 0.0, "mean_log": 0.0, "sd": None, "bound": None, "positive": False,
                           "honest_bound": None, "variance": None}
    if not observations:
        return out
    weight = math.fsum(w for _, w in observations)
    squares = math.fsum(w * w for _, w in observations)
    mean = math.fsum(v * w for v, w in observations) / weight
    n_eff = weight * weight / squares
    out.update(n_eff=n_eff, mean_log=mean)
    if n_eff >= 2:
        sd = math.sqrt(math.fsum(w * (v - mean) ** 2 for v, w in observations) / (weight - squares / weight))
        out.update(sd=sd, bound=mean - stats.t_quantile(confidence, n_eff - 1) * sd / math.sqrt(n_eff), variance=sd * sd)
    gate = None
    if win_rate is not None:
        returns = [math.expm1(v * scale) for v, _ in observations]
        lopsided = stats.lopsided(returns, win_rate)
        if lopsided:
            gate = stats.lopsided_growth_lcb(returns, risk, 1.0 - confidence) / scale
            wins = [v for v, _ in observations if v > 0]
            p = stats.exact_upper(len(observations) - len(wins), len(observations), 1.0 - confidence)
            worst = min(min(v for v, _ in observations), math.log1p(-min(abs(risk), 0.999999)) / scale)
            model = p * (1.0 - p) * ((math.fsum(wins) / len(wins) if wins else 0.0) - worst) ** 2
            out["variance"] = max(out["variance"] or 0.0, model)
        out.update(lopsided=lopsided, loss_gate=gate)
    bound = out["bound"]
    out["honest_bound"] = None if bound is None else (min(bound, gate) if gate is not None else bound)
    out["positive"] = bool(out["n"] >= min_n and bound is not None and bound > 0 and (gate is None or gate > 0))
    return out


def practice_charges(rows: list[TapeRow], book: str, bps: Any) -> dict[str, list[tuple[int, float]]]:
    """The execution haircut of each venue or cross fill of one member on `book`, in dollars, by the
    instrument key a closed trade carries (`evaluator.closed_trade_rows`): `bps` (a number, or a table
    by asset class) of the fill's notional, as the allocator's `_paper_haircut` charges the paper
    record its E reads."""
    from .allocator import _haircut_rate

    charges: dict[str, list[tuple[int, float]]] = {}
    for r in rows:
        p = r.payload
        if r.kind != "book.fill" or p.get("book") != book or p.get("source") not in ("venue", "cross"):
            continue
        inst = p.get("instrument") or {}
        try:
            notional = abs(float(p["quantity"]) * float(p["price"]) * float(inst.get("multiplier") or 1))
        except (KeyError, TypeError, ValueError):
            continue
        charges.setdefault(instrument_key(inst), []).append((r.seq, notional * _haircut_rate(bps, inst.get("asset_class")) / 10_000.0))
    return charges


def risked_at_close(rows: Sequence[TapeRow], book: str, until_seq: int) -> dict[int, float]:
    """For every row that closes a position on `book` (a settlement, or a sale that left it flat, exactly
    as `evaluator.closed_trade_rows` closes them), the cash its buys put at risk from the position's first
    buy to its close: the capital at risk the at-risk unit divides by. Read from the first row, so a
    position opened before an evidence cutoff still has its cost."""
    buys: dict[str, float] = {}
    out: dict[int, float] = {}
    for r in rows:
        p = r.payload
        if p.get("book") != book or r.seq > until_seq or r.kind == "book.stake":
            continue
        key = instrument_key(p.get("instrument"))
        if r.kind == "book.fill" and p.get("side") == "buy" and p.get("source") in ("venue", "cross"):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                buys[key] = buys.get(key, 0.0) - float(p["cash_delta"])
        sale = r.kind == "book.fill" and p.get("realized") is not None and p.get("source") != "dust"
        if r.kind == "book.settle" or (sale and p.get("flat", True)):
            out[r.seq] = buys.pop(key, 0.0)
    return out


# ------------------------------------------------------------------------------------- capacity
def bucket_of(usd: float | None) -> str | None:
    if usd is None or not math.isfinite(usd):
        return None
    return next(name for top, name in SIZE_BUCKETS if usd <= top)


def fill_rates(tape: TradeTape, members: Sequence[str], *, since: float, min_markets: int) -> dict[str, dict[str, Any]]:
    """By bid-size bucket: markets bid and markets filled (a market counts once), on the REAL book when it
    has bid `min_markets` markets at that size (practice fills are conservative by design, and capacity is
    a real-money number), on both books before."""
    bids = [b for m in members for b in tape.bids.get(m, ()) if b.at >= since and b.market]
    out: dict[str, dict[str, Any]] = {}
    for _, name in SIZE_BUCKETS:
        rows = [b for b in bids if bucket_of(b.notional) == name]
        if not rows:
            continue
        real = [b for b in rows if b.book in REAL_BOOKS]
        chosen, basis = (real, "real") if len({b.market for b in real}) >= min_markets else (rows, "all")
        markets = {b.market for b in chosen}
        filled = {b.market for b in chosen if b.order_id in tape.filled}
        out[name] = {"markets_bid": len(markets), "markets_filled": len(filled),
                     "fill_rate": len(filled) / len(markets) if markets else None, "basis": basis}
    return out


def capacity(tape: TradeTape, members: Sequence[str], venue: str, *, now: float, days: float, stake_usd: float,
             edge: float | None, real_events: Sequence[float], min_markets: int,
             constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """E3 (capacity is measured, not assumed): the markets the family's members bid a day (the ledger keeps
    only the COUNT of markets a wake is offered, so the markets in a family's band are the ones its own
    rules chose to bid), the fill rate by size, the real independent settlements a day, and the dollars a
    day that implies at the stake: markets a day x the fill rate at the stake's largest position x that
    position x the edge per dollar at risk. Over the last `days` (or since the family's first bid)."""
    since = now - days * DAY
    bids = [b for m in members for b in tape.bids.get(m, ()) if b.at >= since and b.market]
    size = position_share(venue, constitution) * float(stake_usd)
    events = [t for t in real_events if t >= since]
    out: dict[str, Any] = {"days": None, "markets_bid": 0, "markets_per_day": None, "median_bid_usd": None, "size_usd": round(size, 2),
                           "size_bucket": bucket_of(size), "fill_rate_at_size": None, "fill_rates": {},
                           "settlements_per_day": None, "edge_per_dollar": edge, "usd_per_day": None, "stake_usd": round(float(stake_usd), 2)}
    if not bids:
        out["why"] = f"no bid by a member in the last {days:g} days"
        return out
    first = min(b.at for b in bids)
    span = max((now - max(first, since)) / DAY, 1.0 / 24.0)
    markets = {b.market for b in bids}
    notionals = sorted(b.notional for b in bids if b.notional is not None)
    rates = fill_rates(tape, members, since=since, min_markets=min_markets)
    at_size = rates.get(bucket_of(size) or "") or {}
    rate = at_size.get("fill_rate") if int(at_size.get("markets_bid") or 0) >= min_markets else None
    basis = "at size"
    if rate is None:
        # Not measured at the stake's size: the rate at the members' own median bid, which is what they place.
        median = notionals[len(notionals) // 2] if notionals else None
        row = rates.get(bucket_of(median) or "") or {}
        rate, basis = row.get("fill_rate"), "at the median bid"
    out.update(days=round(span, 3), markets_bid=len(markets), markets_per_day=len(markets) / span,
               median_bid_usd=notionals[len(notionals) // 2] if notionals else None, fill_rate_at_size=rate,
               fill_rate_basis=basis, fill_rates=rates, settlements_per_day=len(events) / span)
    if rate is not None and edge is not None:
        out["usd_per_day"] = len(markets) / span * rate * edge * size
    return out


def capacity_holds(rates: Mapping[str, Mapping[str, Any]], old_size: float, new_size: float, *, ratio: float,
                   min_markets: int) -> bool:
    """Whether measured capacity stops a stake at `old_size` a position from growing to `new_size`: the fill
    rate at the new size's bucket is below `ratio` of the rate at the old size's, both measured on at least
    `min_markets` markets. A size never bid is not measured, and the ramp itself is how it gets measured."""
    old, new = bucket_of(old_size), bucket_of(new_size)
    if old is None or new is None or old == new:
        return False
    a, b = rates.get(old) or {}, rates.get(new) or {}
    if int(a.get("markets_bid") or 0) < min_markets or int(b.get("markets_bid") or 0) < min_markets:
        return False
    if a.get("fill_rate") is None or b.get("fill_rate") is None:
        return False
    return float(b["fill_rate"]) < ratio * float(a["fill_rate"])


# ------------------------------------------------------------------------------------ the record
def family_record(house: Any, family: str, venue: str, *, tape: TradeTape | None = None, through: int | None = None,
                  now: float | None = None, stake_usd: float | None = None,
                  constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A family's pooled forward record (P1 and C1, the close-the-gaps run, Sept 24, 2026): the proof that
    moves a family's real stakes from probes to bunts and to the family swing. Read-only; a pure function
    of the ledger and the registry. `scripts/gap_scoreboard.py` implements the account unit of it:

    - members: every agent ever born into `family` on `venue`, living or dead;
    - observations: one per distinct EVENT (`evaluator.event_key`) that any member closed -- settled,
      or sold flat -- on the practice book or the real book since that member's evidence cutoff; on
      Alpaca, where nothing groups trades, one per closed trade. A member's value on an event is, in the
      "account" unit, the sum of the log growths ln(1 + r) of its closed trades there, r as
      `Evaluator.trade_returns` computes it read through that trade's own ledger position (its result
      over the most the member had been lent on that book by then); in the "at_risk" unit, what the
      event made over what its positions put at risk (`at_risk_value`);
    - an event several members traded is ONE observation: the weighted mean of their values (real at
      `real_weight`, practice at `practice_weight`) at the largest weight among them (`pool`);
    - pooled: mean, sd, n_eff and the one-sided `confidence` lower bound; `proven` with at least
      `min_independent_settlements` observations and the bound above zero (and the loss-rate gate for a
      lopsided record);
    - the maker and taker records apart: a member's observation is "taker" when its first entry fill
      on that event (on that trade, on Alpaca) was a taker fill (`book.fill` `liquidity`);
    - the REAL-only record the family swing reads (`real`), with each real event's first close;
    - every member's active blocks (`blocks`), and the capacity estimate at `stake_usd` (`capacity`);
    - an Alpaca PRACTICE trade pays the execution haircut the allocator's E takes off the same fills
      (`evidence.alpaca_paper_haircut_bps`): practice fills there look optimistic, and the proof that
      moves real money must not read them rawer than E does (review of #224, Sept 24, 2026).
    """
    from .evaluator import closed_trade_rows, event_key, per_event, staked_base

    c = constitution or CONSTITUTION
    tape = tape if tape is not None else TradeTape()
    # Inside a pass the tape already holds the pass's ledger position: no read at all.
    head = tape.cursor if through is not None and int(through) <= tape.cursor else tape.refresh(house.ledger)
    through = head if through is None else min(int(through), head)
    rule = proof_rule(c)
    at_risk_unit = rule["unit"] == "at_risk"
    share = rule["reference_share"]
    books = {PAPER_BOOK[venue]: rule["practice_weight"], REAL_BOOK[venue]: rule["real_weight"]}
    haircut = ((c.get("allocator") or {}).get("evidence") or {}).get("alpaca_paper_haircut_bps", 0)
    registry = house.registry
    with (getattr(registry, "_lock", None) or contextlib.nullcontext()):
        agents = [a for a in list(registry.agents.values()) if a.family == family and a.venue == venue]
    members = sorted(a.id for a in agents)
    living = sum(1 for a in agents if getattr(a, "alive", True))
    units: dict[str, list[tuple[float, float, str, str]]] = {}
    real_units: dict[str, list[tuple[float, float]]] = {}
    real_first: dict[str, int] = {}
    real_at: dict[str, float] = {}
    edges: dict[str, list[tuple[float, float]]] = {}
    risked: list[float] = []  # each entry's cash over what had been lent then, as `trade_returns` reads its risk
    without_risk = 0
    for member in members:
        rows = tape.rows.get(member) or []
        cutoffs = tape.cutoffs.get(member) or {}
        for book, weight in books.items():
            stakes = [(r.seq, float(r.payload.get("usd") or 0)) for r in rows if r.kind == "book.stake" and r.payload.get("book") == book]
            if staked_base(stakes, through) <= 0:
                continue  # never lent anything on this book: no record there
            for r in rows:
                p = r.payload
                if (r.kind == "book.fill" and p.get("book") == book and p.get("side") == "buy" and p.get("source") in ("venue", "cross")
                        and cutoffs.get(book, 0) < r.seq <= through):
                    lent = staked_base(stakes, r.seq)
                    if lent > 0:
                        with contextlib.suppress(KeyError, TypeError, ValueError):
                            risked.append(-float(p["cash_delta"]) / lent)
            closed, _ = closed_trade_rows((r for r in rows if r.kind != "book.stake"), book,
                                          since_seq=cutoffs.get(book, 0), until_seq=through)
            at_risk = risked_at_close(rows, book, through)
            when = {r.seq: r.at for r in rows}
            by_event = per_event(book, c)
            charges = practice_charges(rows, book, haircut) if book == "alpaca-paper" else {}
            # observation -> [account log growth, made, at risk, (first entry seq, its liquidity), first close, last close]
            mine: dict[str, list[Any]] = {}
            for row in closed:
                lent = staked_base(stakes, row["seq"])  # `trade_returns` read through this trade's position
                if lent <= 0:
                    continue
                key = (event_key(row["instrument"]) if by_event else None) or f"{book}:{member}:{row['seq']}"
                unit = mine.setdefault(key, [0.0, 0.0, 0.0, (math.inf, "taker"), row["seq"], row["seq"]])
                opened = row["entry_seq"] if row["entry_seq"] is not None else row["seq"]
                paid = math.fsum(ch for seq, ch in charges.get(row["key"], ()) if opened <= seq <= row["seq"])
                made = row["made"] - paid
                unit[0] += log1p(made / lent)
                unit[1] += made
                risk = at_risk.get(row["seq"], 0.0)
                unit[2] += max(risk, 0.0)
                if risk <= 0:
                    without_risk += 1
                entry = (opened, row["liquidity"])
                if entry[0] < unit[3][0]:
                    unit[3] = entry
                unit[4], unit[5] = min(unit[4], row["seq"]), max(unit[5], row["seq"])
            for key, (growth, made, risk, (_, liquidity), first, last) in mine.items():
                value = at_risk_value(made, risk, share) if at_risk_unit else growth
                units.setdefault(key, []).append((value, weight, liquidity, member))
                edges.setdefault(key, []).append((max(made / risk, -1.0) if risk > 0 else (-1.0 if made < 0 else 0.0), weight))
                if book == REAL_BOOK[venue]:
                    real_units.setdefault(key, []).append((value, 1.0))
                    real_first[key] = min(real_first.get(key, first), first)
                    real_at[key] = max(real_at.get(key, 0.0), when.get(last, 0.0))
    minimum, confidence = rule["min_independent_settlements"], rule["confidence"]
    win_rate = float(c["ladder"]["lopsided_win_rate"]) if rule["lopsided_gate"] else None
    risk_per_entry = math.fsum(risked) / len(risked) if risked else 1.0  # with no entry seen, all of it was at risk
    # The gate reads a lopsided record as an account's growth: in the account unit, one that put the
    # family's mean cash an entry at risk; in the at-risk unit, the reference bet (`reference_share`).
    gate = {"win_rate": win_rate, "risk": share if at_risk_unit else risk_per_entry, "scale": share if at_risk_unit else 1.0}

    def side(liquidity: str | None) -> dict[str, Any]:
        chosen = {k: [u for u in group if liquidity is None or (u[2] == "taker") == (liquidity == "taker")] for k, group in units.items()}
        pooled = pool({k: [(u[0], u[1]) for u in group] for k, group in chosen.items()}, minimum, confidence, **gate)
        pooled["members"] = len({u[3] for group in chosen.values() for u in group})
        return pooled

    whole = side(None)
    real = pool(real_units, minimum, confidence, **gate)
    # Each real event's first close and its value (the mean of its real members' values, as `pool` takes
    # it): the ramp counts the positive ones that closed after the family entered the swing.
    real["first_closes"] = sorted((real_first[k], math.fsum(v for v, _ in group) / len(group)) for k, group in real_units.items() if group)
    real["closed_at"] = sorted(real_at.values())
    weight_sum = math.fsum(max(w for _, w in group) for group in edges.values())
    edge = (math.fsum(max(w for _, w in group) * math.fsum(r * w for r, w in group) / math.fsum(w for _, w in group)
                      for group in edges.values()) / weight_sum) if weight_sum > 0 else None
    blocks = {"practice": 0, "real": 0, "growth": 0.0}
    for member in members:
        for _, book, active, growth in tape.blocks.get(member) or ():
            if active and book in books:
                blocks["real" if book == REAL_BOOK[venue] else "practice"] += 1
                blocks["growth"] += growth
    record = {"family": family, "venue": venue, "through": through, "unit": rule["unit"], "members": len(members),
              "members_living": living, "members_counted": whole.pop("members"), "n": whole["n"], "n_eff": whole["n_eff"],
              "mean_log": whole["mean_log"], "sd": whole["sd"], "bound": whole["bound"], "proven": whole["positive"],
              "state": "proven" if whole["positive"] else "unproven", "real_n": len(real_units),
              "lopsided": whole.get("lopsided"), "loss_gate": whole.get("loss_gate"), "honest_bound": whole["honest_bound"],
              "risk_per_entry": risk_per_entry, "rows_without_risk": without_risk, "edge_per_dollar": edge,
              "maker": side("maker"), "taker": side("taker"), "real": real, "blocks": blocks, "rule": rule}
    swing = swing_rule(c)
    if now is not None and stake_usd is not None:
        record["capacity"] = capacity(tape, members, venue, now=float(now), days=(swing or {}).get("capacity_days", 7.0),
                                      stake_usd=float(stake_usd), edge=edge, real_events=real["closed_at"],
                                      min_markets=(swing or {}).get("capacity_min_markets", 5), constitution=c)
    return record


def empty_record(family: str, venue: str, *, through: int | None = None, error: str | None = None) -> dict[str, Any]:
    """What a family counts as while its record cannot be computed: unproven, with no taker record."""
    try:
        rule = proof_rule()
    except Exception:  # noqa: BLE001 - a malformed rule is no reason to raise into a wake
        rule = {"min_independent_settlements": 10, "practice_weight": 0.5, "real_weight": 1.0, "confidence": 0.8,
                "lopsided_gate": True, "unit": "account", "reference_share": 0.01}
    side = {"n": 0, "n_eff": 0.0, "mean_log": 0.0, "sd": None, "bound": None, "positive": False, "members": 0,
            "honest_bound": None, "variance": None}
    out = {"family": family, "venue": venue, "through": through, "unit": rule["unit"], "members": 0, "members_living": 0,
           "members_counted": 0, "n": 0, "n_eff": 0.0, "mean_log": 0.0, "sd": None, "bound": None, "proven": False,
           "state": "unproven", "real_n": 0, "lopsided": None, "loss_gate": None, "honest_bound": None, "risk_per_entry": None,
           "rows_without_risk": 0, "edge_per_dollar": None, "maker": dict(side), "taker": dict(side),
           "real": {**side, "first_closes": [], "closed_at": []}, "blocks": {"practice": 0, "real": 0, "growth": 0.0}, "rule": rule}
    if error is not None:
        out["error"] = error
    return out


# ---------------------------------------------------------------------------------- the swing
def swing_ready(record: Mapping[str, Any], rule: Mapping[str, Any] | None) -> bool:
    """The REAL record qualifies the family for the swing: `min_real_settlements` independent real settlements
    and the honest lower bound (the t bound, and the loss-rate gate for a lopsided record) above zero."""
    if rule is None:
        return False
    real = record.get("real") or {}
    bound = real.get("honest_bound")
    return int(real.get("n") or 0) >= int(rule["min_real_settlements"]) and bound is not None and bound > 0


def positive_since(record: Mapping[str, Any], entered_seq: int | None) -> int:
    """Independent real settlements with a positive value whose first close came after the family entered
    the swing (`entered_seq`): what the ramp doubles on."""
    if entered_seq is None:
        return 0
    return sum(1 for first, value in (record.get("real") or {}).get("first_closes") or () if first > entered_seq and value > 0)


def _q(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_DOWN)


def swing_target(record: Mapping[str, Any], *, rule: Mapping[str, Any], venue: str, bunt_usd: Any, venue_capital: Any,
                 members_real: int, entered_seq: int | None, rates: Mapping[str, Mapping[str, Any]] | None = None,
                 constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The family swing's stake for ONE member on real money, and why (C2, Sept 24, 2026):

        min(ramp, family caps / members on real money), never under the bunt

    - ramp: `start_multiple` x `bunt_usd`, doubled after every `doubling_every` further positive
      independent real settlements since the family entered the swing, but held at the last size the
      capacity rule lets through (`capacity_holds`: the fill rate at the next size under
      `capacity_fill_ratio` of the rate at the size before);
    - family caps: full Kelly (`kelly_fraction`) on the REAL record's honest lower bound against the
      venue's capital, and `max_share_of_venue` of that capital. In the at-risk unit Kelly's fraction is
      the capital to put AT RISK an event, so the family's stake is that over the most of a stake one event
      may hold (`event_share`: `max_event_share` on Kalshi, where strikes of one event hold it together);
      in the account unit it is the stake;
    - `limit`: which of "ramp", "capacity", "kelly" or "venue_share" set the stake ("bunt" when the caps
      are below the bunt, which a proven family's member always keeps)."""
    c = constitution or CONSTITUTION
    real = record.get("real") or {}
    bunt = Decimal(str(bunt_usd))
    capital = Decimal(str(venue_capital))
    share_position = position_share(venue, c)
    positive = positive_since(record, entered_seq)
    level = positive // int(rule["doubling_every"])
    steps = [bunt * Decimal(str(rule["start_multiple"])) * (2 ** i) for i in range(level + 1)]
    held, limit = 0, "ramp"
    for i in range(1, len(steps)):
        if capacity_holds(rates or {}, float(steps[i - 1]) * share_position, float(steps[i]) * share_position,
                          ratio=float(rule["capacity_fill_ratio"]), min_markets=int(rule["capacity_min_markets"])):
            limit = "capacity"
            break
        held = i
    ramp = steps[held]
    fraction = stats.quarter_kelly(float(real.get("honest_bound") or 0.0), float(real.get("variance") or 0.0),
                                   fraction=float(rule["kelly_fraction"]), cap=1e9)
    unit_scale = event_share(venue, c) if str(record.get("unit")) == "at_risk" else 1.0
    kelly = Decimal(str(round(fraction / unit_scale, 9))) * capital if fraction > 0 else Decimal(0)
    venue_share = capital * Decimal(str(rule["max_share_of_venue"]))
    members = max(int(members_real), 1)
    caps = {"kelly": kelly / members, "venue_share": venue_share / members}
    stake, why = ramp, limit
    for name, cap in caps.items():
        if cap < stake:
            stake, why = cap, name
    if stake < bunt:
        stake, why = bunt, "bunt"
    doubling = int(rule["doubling_every"])
    return {"stake_usd": _q(stake), "ramp_usd": _q(ramp), "level": level, "held_level": held, "limit": why,
            "positive_since_entry": positive, "next_doubling_in": doubling - positive % doubling,
            "kelly_fraction_at_risk": fraction, "kelly_usd": _q(kelly), "venue_share_usd": _q(venue_share),
            "members_real": int(members_real), "entered_seq": entered_seq}


# ------------------------------------------------------------------------------ the states, the rows
def next_state(previous: str, *, proven: bool, ready: bool, approved: bool) -> str:
    """The family's state after a pass: "swing" while its real record qualifies and its entry was approved
    (the first entry is audited), else "proven" when the pooled record is proven or the real record alone
    qualifies (15 real settlements with a positive honest bound are stronger proof than 10 pooled), else
    "unproven". A swing whose bound falls to zero or below returns its members to bunts, or to probes when
    the pooled record is no longer proven either (free cash only: no position is sold for it)."""
    if ready and (previous == "swing" or approved):
        return "swing"
    return "proven" if (proven or ready) else "unproven"


def row_of(record: Mapping[str, Any], state: Mapping[str, Any], *, swing: Mapping[str, Any] | None,
           members_real: int, stake_usd: Any) -> dict[str, Any]:
    """The compact `family.record` row (and the board's `families` entry): the record, its state and since,
    the stake a member on real money is lent, and the capacity estimate."""
    def r(value: Any, digits: int = 6) -> Any:
        return None if value is None else round(float(value), digits)

    real = record.get("real") or {}
    cap = record.get("capacity") or {}
    return {"family": record["family"], "venue": record["venue"], "unit": record.get("unit"), "state": state.get("state", "unproven"),
            "since": state.get("since"), "n": int(record.get("n") or 0), "n_eff": r(record.get("n_eff"), 3),
            "mean_log": r(record.get("mean_log")), "bound": r(record.get("bound")), "loss_gate": r(record.get("loss_gate")),
            "proven": bool(record.get("proven")), "edge_per_dollar": r(record.get("edge_per_dollar")),
            "real": {"n": int(real.get("n") or 0), "mean_log": r(real.get("mean_log")), "bound": r(real.get("bound")),
                     "loss_gate": r(real.get("loss_gate")), "honest_bound": r(real.get("honest_bound"))},
            "maker": {"n": int((record.get("maker") or {}).get("n") or 0), "bound": r((record.get("maker") or {}).get("bound")),
                      "positive": bool((record.get("maker") or {}).get("positive"))},
            "taker": {"n": int((record.get("taker") or {}).get("n") or 0), "bound": r((record.get("taker") or {}).get("bound")),
                      "positive": bool((record.get("taker") or {}).get("positive"))},
            "blocks": dict(record.get("blocks") or {}), "members": int(record.get("members") or 0),
            "members_living": int(record.get("members_living") or 0), "members_real": int(members_real),
            "stake_usd": None if stake_usd is None else str(stake_usd),
            "capacity": {"usd_per_day": r(cap.get("usd_per_day"), 4), "markets_per_day": r(cap.get("markets_per_day"), 3),
                         "fill_rate_at_size": r(cap.get("fill_rate_at_size"), 4), "size_usd": r(cap.get("size_usd"), 2),
                         "settlements_per_day": r(cap.get("settlements_per_day"), 3),
                         "binds": bool(swing and swing.get("limit") == "capacity")},
            "swing": None if not swing else {k: (str(v) if isinstance(v, Decimal) else v) for k, v in swing.items()}}


def row_digest(row: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()[:16]


def restore_states(ledger: Any) -> dict[str, dict[str, Any]]:
    """The states the ledger's last `family.record` rows carry, for an allocator whose own state file has none
    (a first start under this code keeps nothing to restore: every family starts from its record)."""
    out: dict[str, dict[str, Any]] = {}
    try:
        rows = ledger.read(kinds="family.record", limit=10_000, newest=True)
    except Exception:  # noqa: BLE001 - a ledger that cannot be read restores nothing; the records decide afresh
        return out
    for entry in rows:
        p = entry.payload
        if p.get("family") and p.get("venue") and p.get("state") in STATES:
            swing = p.get("swing") or {}
            out[key_of(p["family"], p["venue"])] = {"state": p["state"], "since": p.get("since"),
                                                     "entered_seq": swing.get("entered_seq") if p["state"] == "swing" else None}
    return out


def key_of(family: str, venue: str) -> str:
    return f"{family}@{venue}"


# -------------------------------------------------------------------------------- the readers
def losing(blocks: int, growth: float, minimum: int) -> bool:
    """A family is not bred again (`House._losing_family`) when its pooled forward record is negative after
    `minimum` active blocks. A record that nets to zero is not a loss (six blocks of +0.01 and -0.01 sum to
    -3.5e-18 in floating point)."""
    return blocks >= minimum and growth <= -1e-9


def score(record: Mapping[str, Any], state: str) -> int:
    """What a family's record says to a search that weighs lineages (`Lab.lineage_weights` may read it): +1 when
    the family is proven or swinging, -1 when its pooled mean is below zero after the proof's minimum count of
    independent settlements, else 0. Nothing here moves anyone's band."""
    if state in ("proven", "swing"):
        return 1
    minimum = int((record.get("rule") or {}).get("min_independent_settlements", 10))
    return -1 if int(record.get("n") or 0) >= minimum and float(record.get("mean_log") or 0.0) < 0 else 0
