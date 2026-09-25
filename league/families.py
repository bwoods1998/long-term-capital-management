"""The mechanism ledger (C1 of the close-the-gaps run, Sept 24, 2026; docs/goals/LTCM_CLOSE_THE_GAPS.md).

A FAMILY is a mechanism: every agent ever born with the same `family` on one venue, living or dead.
Its pooled forward record is the proof that moves real money, and this module is the one place
that record is computed. Every reader reads it here: the allocator (probe, bunt or family swing, and
the book's taker rule through `Allocator.family_taker`), the board and the site, the House's
births (`Allocator.family_forward`, a drop-in for `House.family_forward`), the foundry (through
the House's `_losing_family`), and the lab's lineage weights (`Allocator.family_score`).

- **The key** (C8 of the forward-first run, Sept 25, 2026; the constitution's `allocator.family_key`
  "mechanism"): a family is keyed by its program's MECHANISM (`mechanism_key`: the code beyond its
  PARAMS literal, as `parameters.same_logic` draws the line and `lab.mechanism_digest` digests it, and
  the venue, series and symbols it trades). A child whose program is its parent's beyond PARAMS stays in
  its parent's family; a program whose code differs beyond PARAMS, or whose venue, series or symbols
  differ, founds a family of its own (`MechanismIndex.place`), and an agent that rewrites itself in place
  moves to its new program's family from that ledger position on (an `agent.family` row). A member's
  rows count for a family only while it ran the family's program (`TradeTape.spans`); its lineage stays
  on its birth row. The labels born before C8 are re-keyed once, by new `agent.family` rows
  (`MechanismIndex.refresh` with every program checked); no older row is edited. Measured on the T0
  snapshot (04:23Z Sept 25): 343 of 647 births carried a label whose founding program was another
  mechanism and 148 agents rewrote themselves into another one, among them meriwether-h2d625d-4, which
  kept the proven sports-central-run-under's name after it rewrote itself into a KXWNBAGAME favourite
  maker at 02:37Z.

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
  Each event WEIGHS what it put at risk against its member's mean on that book (review of #242,
  Sept 24, 2026: the ratio estimator, sum made / sum at risk, within a member's book): weighed
  alike, small wins and large losses -- a resting bid filled in full as the price falls through
  it -- read as an edge while the dollars lost, and a family that lost $44 of real money over 100
  events was proven and ready to swing. The effect at T0 is Deploy A's: weather-favorites unproven
  (2 losses in 16; its practice losers carried 2.4 times its winners' dollars), sports-central-
  run-under proven (+0.1423 at risk: 6 of 11 practice events won at about even money, and its
  winners carried twice its losers' dollars), every other family unproven.
- **The states** (`next_state`): "unproven"; "proven" (`allocator.family_proven`, the POOLED record,
  the table's one proof: probes become bunts); "swing" (`allocator.family_swing`): a proven family
  ENTERS when its entry look passes -- judged only at `min_real_settlements` real settlements and
  every `entry_every` more, on the first that many real events, with the honest lower bound (the t
  bound, and the loss-rate bound for a lopsided record) at `entry_confidence` above zero
  (`entry_look`) -- and that entry's audit approves it; it STAYS while its whole real record's honest
  bound at the table's 80% holds at every pass (`swing_ready`) and it is still proven. Leaving the
  swing, a member's new program, or a member born into the family after the audit looked lapses the
  approval: the next entry is audited again (a swing already running is untouched). Each state carries its `since`; `family.record` ledger rows carry the ledger at most every
  five minutes, a row for each family whose record changed.
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
- **The probe gate** (`probe_rule`, `losing`, `gaining`; R5, Sept 24, 2026): no probe on a family whose pooled forward
  record (the House's `family_forward`: active blocks and summed log growth, every member ever born) is at or below zero
  after `losing_min_blocks` active blocks, and none from a family one of whose probes went back to practice until its
  record since then is positive over as many (`Allocator.probe_gate`). The board's clock to a family's swing is
  `swing_clock`.

A money judge: `league/ci.py` forbids Merton's pull requests to touch it.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import re
import threading
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Any, Iterable, Mapping, NamedTuple, Sequence

from . import stats
from .constitution import CONSTITUTION
from .structure_core import is_code
from .ledger import HOUSE

CENT = Decimal("0.01")
PAPER_BOOK = {"alpaca": "alpaca-paper", "kalshi": "kalshi-shadow"}
#: Every practice book of a venue (G of the options-desk run, Sept 25, 2026): an Alpaca STRUCTURE agent practises on the
#: House's `options-shadow` book (or `alpaca-paper`, as `league/config.json` `options_structures.book` names it), so a
#: family's record reads each member's practice wherever it traded; a member never lent anything on a book has no record
#: there. And the practice books whose fills pay the execution haircut (`evidence.alpaca_paper_haircut_bps`): Alpaca's.
PRACTICE_BOOKS = {"alpaca": ("alpaca-paper", "options-shadow"), "kalshi": ("kalshi-shadow",)}
HAIRCUT_BOOKS = ("alpaca-paper", "options-shadow")
REAL_BOOK = {"alpaca": "alpaca", "kalshi": "kalshi"}
REAL_BOOKS = tuple(REAL_BOOK.values())
STATES = ("unproven", "proven", "swing")
#: What the tape folds from the ledger: every agent's fills, settlements and stakes, the two kinds that
#: move an agent's evidence cutoff (`accounting.evidence_cutoffs`), the House's orders (the buys a family
#: placed: its capacity), the evaluator's blocks (every member's active blocks), every agent's program
#: changes (`agent.strategy`) and births (`agent.born`): a family swing's approval lapses when a member's
#: program changes, or a member is born into the family, after the audit looked. And the family changes
#: (`agent.family`, C8): which family each stretch of an agent's rows belongs to.
TAPE_KINDS = ("book.fill", "book.settle", "book.stake", "book.fill_correction", "book.baseline", "book.order", "eval.block",
              "agent.strategy", "agent.born", "agent.family")
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
#: C6 of the forward-first run (Sept 25, 2026): a size's fill rate is the REAL book's once the family has bid this
#: many markets there at that size (the scoreboard's `MIN_REAL_MARKETS_FOR_FILL_RATE`), every book's before. Capacity
#: is a real-money number and practice fills are conservative by design; five real markets (the swing's
#: `capacity_min_markets`) were one bad night's worth: sports-central-run-under bid 19.07 markets a day at T0.
REAL_FILL_MIN_MARKETS = 10
#: The multiples of the stake a family's capacity row reports its fill curve at (C6): what the family swing's first
#: two doublings would meet (`swing_target` reads the same rates, `capacity_holds`).
CURVE_MULTIPLES = (1, 2, 4)


def _epoch(at: Any) -> float:
    try:
        return datetime.fromisoformat(str(at).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def instrument_key(instrument: Mapping[str, Any] | None) -> str:
    """The instrument key a closed trade carries (`evaluator.closed_trade_rows`)."""
    inst = instrument or {}
    return ":".join(str(inst.get(k)) for k in ("market_id", "symbol", "right", "expiry", "strike") if inst.get(k) is not None)


def place_segment(segments: list[tuple[int, str, int]], since: int, family: str, row: int) -> None:
    """Put (since, family, row) into an agent's segments in `since` order (C8): a segment that starts where another
    starts replaces it (a birth re-keyed from its first row leaves its label no stretch at all)."""
    for i, (start, _, _) in enumerate(segments):
        if start == since:
            segments[i] = (since, family, row)
            return
        if start > since:
            segments.insert(i, (since, family, row))
            return
    segments.append((since, family, row))


def segment_spans(segments: Sequence[tuple[int, str, int]], family: str) -> list[tuple[int, float]]:
    """The non-empty stretches [from, to) of the ledger that `segments` give `family`."""
    out = []
    for i, (since, name, _) in enumerate(segments):
        end = segments[i + 1][0] if i + 1 < len(segments) else math.inf
        if name == family and since < end:
            out.append((since, end))
    return out


def within(spans: Sequence[tuple[int, float]] | None, seq: int) -> bool:
    """Whether a ledger position lies in `spans` (None: everywhere)."""
    return spans is None or any(lo <= seq < hi for lo, hi in spans)


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
        #: (seq, book, active, log growth, began): `began` is the ledger position of the block's first mark
        #: (`first_mark_seq`), where the block BEGAN; a block is written when it closes, so the block in progress at a
        #: ledger position is written after it (`Evaluator.blocks(since_seq=...)` reads a record since by `began` too;
        #: the R5 adversarial review, Sept 24, 2026). A row without it began where it was written.
        self.blocks: dict[str, list[tuple[int, str, bool, float, int]]] = {}
        #: (agent, the block's ledger position) -> its period `key` (an hour or a day): the probe gate's record since a
        #: demotion is one observation per period (`allocator.family_probe` `reseat: "bound_since_demotion"`, M5).
        self.periods: dict[tuple[str, int], str] = {}
        self.filled: dict[str, float] = {}  # order id -> when a buy fill named it
        self.last_seq: dict[str, int] = {}  # agent -> the newest row folded for it: a family's version
        self.programs: dict[str, int] = {}  # agent -> the ledger position of its last program change (`agent.strategy`)
        #: agent -> the ledger position of its birth (`agent.born`), or of its move into another family (`agent.family`,
        #: C8): joining a family after its swing's audit looked lapses the approval as a birth into it does.
        self.born: dict[str, int] = {}
        #: agent -> [(since, family, the row that said so)], in `since` order: its birth's label, then each `agent.family`
        #: row (C8). Kept only for an agent that has such a row: every other agent is its label's for all of its rows.
        self.segments: dict[str, list[tuple[int, str, int]]] = {}
        self._labels: dict[str, tuple[int, str]] = {}  # agent -> (its birth, the family it was born with)
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
        elif entry.kind == "agent.strategy":
            if entry.agent != HOUSE:
                self.programs[str(entry.agent)] = max(self.programs.get(str(entry.agent), 0), entry.seq)
        elif entry.kind == "agent.born":
            if entry.agent != HOUSE:
                self.born[str(entry.agent)] = entry.seq
                self._labels[str(entry.agent)] = (entry.seq, str(p.get("family") or ""))
        elif entry.kind == "agent.family":
            agent = str(entry.agent)
            if entry.agent != HOUSE and p.get("family") and agent in self._labels:
                segments = self.segments.setdefault(agent, [(*self._labels[agent], self._labels[agent][0])])
                place_segment(segments, int(p.get("since_seq") or entry.seq), str(p["family"]), entry.seq)
                self.born[agent] = max(self.born.get(agent, 0), entry.seq)
                self._touch(agent, entry.seq)
        elif entry.kind == "eval.block":
            if entry.agent != HOUSE:
                with contextlib.suppress(TypeError, ValueError):
                    self.blocks.setdefault(entry.agent, []).append(
                        (entry.seq, str(p.get("book") or ""), bool(p.get("active")), float(p.get("log_growth") or 0.0),
                         int(p.get("first_mark_seq") or entry.seq)))
                    self._touch(entry.agent, entry.seq)
                    if p.get("key"):  # the block's period (an hour or a day): one observation of a family per period (M5)
                        self.periods[(str(entry.agent), entry.seq)] = str(p["key"])
        elif entry.agent != HOUSE:
            keep = {k: p[k] for k in _TAPE_FIELDS if k in p}
            if p.get("liquidity_role") in ("maker", "taker"):
                # M6 (Sept 25, 2026): an Alpaca fill's own role, the book's reading of its order when it was placed
                # (`Book._liquidity_role`); its `liquidity` stays the fee it was charged at. Rows before it keep theirs.
                keep["liquidity"] = p["liquidity_role"]
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

    def spans(self, agent: str, family: str | None = None, *, through: int | None = None) -> list[tuple[int, float]] | None:
        """The stretches of the ledger (from, to) in which `agent`'s rows are `family`'s (C8), read from its `agent.family`
        rows up to `through`; with no `family`, its current family's. None for an agent with no such row: all of its
        rows are the family it carries (the registry's), as before C8."""
        segments = self.segments.get(str(agent))
        if not segments:
            return None
        kept = [s for s in segments if through is None or s[2] <= through]
        if family is None:
            family = kept[-1][1] if kept else None
        return segment_spans(kept, family) if family is not None else []

    def family_at(self, agent: str, seq: int) -> str | None:
        """The family `agent`'s rows at ledger position `seq` belong to (C8), or None for an agent with no `agent.family`
        row (its label's, all of it): what a probe demotion at `seq` holds (`allocator.fold_demotions` reads the agent's
        family now)."""
        found = None
        for since, family, _ in self.segments.get(str(agent)) or ():
            if since <= seq:
                found = family
        return found

    def current(self, agent: str, *, through: int | None = None) -> str | None:
        """The family `agent` belongs to now (its last `agent.family` row up to `through`), or None when it has none."""
        segments = [s for s in self.segments.get(str(agent)) or () if through is None or s[2] <= through]
        return segments[-1][1] if segments else None


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
            # The ENTRY is judged at `min_real_settlements` real settlements and every `entry_every` more, at
            # `entry_confidence` (the main session's decision on the review of #242, Sept 24, 2026). Without the keys:
            # every settlement, at the proof's own confidence (the rule as #242 had it).
            "entry_every": max(1, int(rule.get("entry_every", 1))),
            "entry_confidence": float(rule.get("entry_confidence", proof_rule(c)["confidence"])),
            # M1 of the forward-first run (Sept 25, 2026): every swing look -- the entry on its first events, the hold and
            # so every doubling on the whole real record -- needs the real events to span this many distinct settlement
            # dates (`event_day`). Without the key: no dates are asked (the rule as Deploy B had it).
            "min_distinct_dates": max(0, int(rule.get("min_distinct_dates", 0))),
            # Full Kelly on the lower bound, as the constitution's scaled rung (`rungs.3.kelly_fraction`).
            "kelly_fraction": float((c.get("rungs") or {}).get("3", {}).get("kelly_fraction", 1.0)),
            "max_share_of_venue": float(allocator.get("max_share_of_venue", 0.6))}


def probe_rule(constitution: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """`allocator.family_probe` (R5 of the close-the-gaps run, Sept 24, 2026), or None where the constitution has none: a
    probe is then seated on any family's record. `losing_min_blocks` is the losing line's count of active blocks (and the
    count a family's record since a probe's demotion must be positive over); `hold` is whether a probe demoted from real
    money holds its family (`reseat: "gain_since_demotion"`)."""
    allocator = (constitution or CONSTITUTION).get("allocator") or {}
    rule = allocator.get("family_probe")
    if not isinstance(rule, Mapping):
        return None
    reseat = str(rule.get("reseat") or "")
    # M5 of the forward-first run (Sept 25, 2026): `reseat: "bound_since_demotion"` holds too, and a hold turns only when
    # the record since the demotion has a one-sided `reseat_confidence` (80%) lower bound above zero over
    # `losing_min_blocks` or more block periods (`bound_gaining`), not on a positive sum (`gaining`).
    return {"losing_min_blocks": int(rule.get("losing_min_blocks", 6)), "reseat": reseat,
            "hold": reseat in ("gain_since_demotion", "bound_since_demotion"), "bound": reseat == "bound_since_demotion",
            "confidence": float(rule.get("reseat_confidence", 0.8))}


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
    from .allocator import _haircut_rate, _structure_fill

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
        rate = _haircut_rate(bps, inst.get("asset_class"), structure=_structure_fill(inst))  # O5: a structure's own rate
        charges.setdefault(instrument_key(inst), []).append((r.seq, notional * rate / 10_000.0))
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


def member_bids(tape: TradeTape, members: Sequence[str], *, since: float,
                spans: Mapping[str, Sequence[tuple[int, float]] | None] | None = None) -> list[Bid]:
    """The bids the members placed since `since`, each only while it ran the family's program (C8): a member's spans
    in the family when `spans` names it, else those of the family it is in now (`TradeTape.spans`; every bid for an
    agent that never changed family)."""
    out = []
    for m in members:
        where = spans[m] if spans is not None and m in spans else tape.spans(m)
        out.extend(b for b in tape.bids.get(m, ()) if b.at >= since and b.market and within(where, b.seq))
    return out


def fill_rates(tape: TradeTape, members: Sequence[str], *, since: float, min_markets: int,
               spans: Mapping[str, Sequence[tuple[int, float]] | None] | None = None) -> dict[str, dict[str, Any]]:
    """By bid-size bucket: markets bid and markets filled (a market counts once), on the REAL book once it has
    bid `REAL_FILL_MIN_MARKETS` markets at that size (C6, Sept 25, 2026; `min_markets` when that is larger):
    practice fills are conservative by design, and capacity is a real-money number. Before that, on both
    books. The family swing's capacity rule (`capacity_holds`) and the capacity row's fill curve (`capacity`)
    read these same rates."""
    bids = member_bids(tape, members, since=since, spans=spans)
    real_min = max(int(min_markets), REAL_FILL_MIN_MARKETS)
    out: dict[str, dict[str, Any]] = {}
    for _, name in SIZE_BUCKETS:
        rows = [b for b in bids if bucket_of(b.notional) == name]
        if not rows:
            continue
        real = [b for b in rows if b.book in REAL_BOOKS]
        chosen, basis = (real, "real") if len({b.market for b in real}) >= real_min else (rows, "all")
        markets = {b.market for b in chosen}
        filled = {b.market for b in chosen if b.order_id in tape.filled}
        out[name] = {"markets_bid": len(markets), "markets_filled": len(filled),
                     "fill_rate": len(filled) / len(markets) if markets else None, "basis": basis}
    return out


def fill_curve(rates: Mapping[str, Mapping[str, Any]], size: float, *, min_markets: int, markets_per_day: float | None,
               edge: float | None, multiples: Sequence[int] = CURVE_MULTIPLES) -> list[dict[str, Any]]:
    """The fill curve at multiples of a position's size (C6, Sept 25, 2026): at each, the fill rate of its size's
    bucket (`fill_rates`: the real book's once it has bid `REAL_FILL_MIN_MARKETS` markets there) when that bucket
    was bid on `min_markets` markets, else None -- a size never bid enough is never assumed to fill -- and the
    dollars a day it implies: markets a day x that rate x the edge a dollar at risk x the size. The family swing's
    doublings are points on it: `capacity_holds` compares two of these rates."""
    out = []
    for k in multiples:
        at = float(size) * k
        row = rates.get(bucket_of(at) or "") or {}
        measured = int(row.get("markets_bid") or 0) >= min_markets and row.get("fill_rate") is not None
        rate = float(row["fill_rate"]) if measured else None
        usd = markets_per_day * rate * edge * at if rate is not None and edge is not None and markets_per_day is not None else None
        out.append({"multiple": k, "size_usd": round(at, 2), "bucket": bucket_of(at), "fill_rate": rate,
                    "basis": row.get("basis") if measured else None, "markets_bid": int(row.get("markets_bid") or 0),
                    "usd_per_day": usd})
    return out


def capacity(tape: TradeTape, members: Sequence[str], venue: str, *, now: float, days: float, stake_usd: float,
             edge: float | None, real_events: Sequence[float], min_markets: int,
             constitution: Mapping[str, Any] | None = None,
             spans: Mapping[str, Sequence[tuple[int, float]] | None] | None = None) -> dict[str, Any]:
    """E3 (capacity is measured, not assumed): the markets the family's members bid a day (the ledger keeps
    only the COUNT of markets a wake is offered, so the markets in a family's band are the ones its own
    rules chose to bid), the fill rate by size, the real independent settlements a day, and the dollars a
    day that implies at the stake: markets a day x the fill rate at the stake's largest position x that
    position x the edge per dollar at risk. Over the last `days` (or since the family's first bid).

    C6 (the forward-first run, Sept 25, 2026): the rate at the stake is the REAL book's once the family has bid
    `REAL_FILL_MIN_MARKETS` markets there at that size (`fill_rate_basis` "real"), every book's before ("all"), the
    members' median bid's when the stake's size was not bid on `min_markets` markets; and `curve` is the fill curve
    at 1x, 2x and 4x the stake (`fill_curve`), which the family swing's capacity rule reads as well. At T0 the
    scoreboard measured sports-central-run-under at $28.41 a day (19.07 markets bid a day x fill 1.0 x $1.49 a
    settlement, real n 11) and megacaps-chip-demand-relay at $0.29."""
    since = now - days * DAY
    bids = member_bids(tape, members, since=since, spans=spans)
    size = position_share(venue, constitution) * float(stake_usd)
    events = [t for t in real_events if t >= since]
    out: dict[str, Any] = {"days": None, "markets_bid": 0, "markets_per_day": None, "median_bid_usd": None, "size_usd": round(size, 2),
                           "size_bucket": bucket_of(size), "fill_rate_at_size": None, "fill_rates": {},
                           "settlements_per_day": None, "edge_per_dollar": edge, "usd_per_day": None, "stake_usd": round(float(stake_usd), 2),
                           "curve": []}
    if not bids:
        out["why"] = f"no bid by a member in the last {days:g} days"
        return out
    first = min(b.at for b in bids)
    span = max((now - max(first, since)) / DAY, 1.0 / 24.0)
    markets = {b.market for b in bids}
    notionals = sorted(b.notional for b in bids if b.notional is not None)
    rates = fill_rates(tape, members, since=since, min_markets=min_markets, spans=spans)
    at_size = rates.get(bucket_of(size) or "") or {}
    measured = int(at_size.get("markets_bid") or 0) >= min_markets
    rate = at_size.get("fill_rate") if measured else None
    basis = ("real" if at_size.get("basis") == "real" else "all books") if measured else "at the median bid"
    if rate is None:
        # Not measured at the stake's size: the rate at the members' own median bid, which is what they place.
        median = notionals[len(notionals) // 2] if notionals else None
        row = rates.get(bucket_of(median) or "") or {}
        rate, basis = row.get("fill_rate"), "at the median bid"
    per_day = len(markets) / span
    out.update(days=round(span, 3), markets_bid=len(markets), markets_per_day=per_day,
               median_bid_usd=notionals[len(notionals) // 2] if notionals else None, fill_rate_at_size=rate,
               fill_rate_basis=basis, fill_rates=rates, settlements_per_day=len(events) / span,
               curve=fill_curve(rates, size, min_markets=min_markets, markets_per_day=per_day, edge=edge))
    if rate is not None and edge is not None:
        out["usd_per_day"] = per_day * rate * edge * size
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

    - members: every agent ever born into `family` on `venue`, living or dead, and every agent an `agent.family`
      row moved into it (C8), each counted only for the rows of its stretch in the family (`TradeTape.spans`);
    - observations: one per distinct EVENT (`evaluator.event_key`) that any member closed -- settled,
      or sold flat -- on the practice book or the real book since that member's evidence cutoff; on
      Alpaca, where nothing groups trades, one per closed trade. A member's value on an event is, in the
      "account" unit, the sum of the log growths ln(1 + r) of its closed trades there, r as
      `Evaluator.trade_returns` computes it read through that trade's own ledger position (its result
      over the most the member had been lent on that book by then); in the "at_risk" unit, what the
      event made over what its positions put at risk (`at_risk_value`), weighted by what it put at risk
      against the mean its member put at risk on that book (so the record is sum made / sum at risk);
    - an event several members traded is ONE observation: the weighted mean of their values (real at
      `real_weight`, practice at `practice_weight`, times the event's weight at risk) at the largest
      weight among them (`pool`);
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
    # Every practice book of the venue (G, Sept 25, 2026: a structure member's practice is on its structure book).
    books = {**{name: rule["practice_weight"] for name in PRACTICE_BOOKS[venue]}, REAL_BOOK[venue]: rule["real_weight"]}
    haircut = ((c.get("allocator") or {}).get("evidence") or {}).get("alpaca_paper_haircut_bps", 0)
    registry = house.registry
    with (getattr(registry, "_lock", None) or contextlib.nullcontext()):
        everyone = [a for a in list(registry.agents.values()) if a.venue == venue]
    # C8 (Sept 25, 2026): a member is every agent whose rows were ever this family's -- its label's for all of them when
    # it never changed family (`TradeTape.spans` None), else the stretches its `agent.family` rows give it -- and each
    # member's rows count only inside those stretches: an agent that rewrote itself keeps what it did under the family's
    # program here and takes the rest to its new family.
    spans: dict[str, list[tuple[int, float]] | None] = {}
    living = 0
    for a in everyone:
        where = tape.spans(a.id, family, through=through)
        if where is None and a.family != family or where == []:
            continue
        spans[a.id] = where
        now_in = a.family == family if where is None else tape.current(a.id, through=through) == family
        living += bool(now_in and getattr(a, "alive", True))
    members = sorted(spans)
    units: dict[str, list[tuple[float, float, str, str]]] = {}
    real_units: dict[str, list[tuple[float, float]]] = {}
    real_first: dict[str, int] = {}
    real_at: dict[str, float] = {}
    days: dict[str, str] = {}  # observation -> its own settlement date (`event_day`): M1 and M3 ask how many dates a proof spans
    real_days: dict[str, str] = {}
    edges: dict[str, list[tuple[float, float]]] = {}
    risked: list[float] = []  # each entry's cash over what had been lent then, as `trade_returns` reads its risk
    without_risk = 0
    made_by_book = {"practice": 0.0, "real": 0.0}  # what its closed trades made, by book, before any haircut (C8: to the cent)
    # The family's closed level-3 STRUCTURES (O4 of the options-desk run, Sept 25, 2026): one flat sale (or settlement) of a
    # held structure is one; on practice books and the real one, with the account-unit log growth of each after its haircut.
    structures = {"practice_closed": 0, "practice_log": 0.0, "real_closed": 0, "real_log": 0.0}
    for member in members:
        rows = tape.rows.get(member) or []
        cutoffs = tape.cutoffs.get(member) or {}
        where = spans[member]  # its stretches in this family (C8); None: all of its rows
        for book, weight in books.items():
            stakes = [(r.seq, float(r.payload.get("usd") or 0)) for r in rows if r.kind == "book.stake" and r.payload.get("book") == book]
            if staked_base(stakes, through) <= 0:
                continue  # never lent anything on this book: no record there
            for r in rows:
                p = r.payload
                if (r.kind == "book.fill" and p.get("book") == book and p.get("side") == "buy" and p.get("source") in ("venue", "cross")
                        and cutoffs.get(book, 0) < r.seq <= through and within(where, r.seq)):
                    lent = staked_base(stakes, r.seq)
                    if lent > 0:
                        with contextlib.suppress(KeyError, TypeError, ValueError):
                            risked.append(-float(p["cash_delta"]) / lent)
            closed, _ = closed_trade_rows((r for r in rows if r.kind != "book.stake"), book,
                                          since_seq=cutoffs.get(book, 0), until_seq=through)
            at_risk = risked_at_close(rows, book, through)
            when = {r.seq: r.at for r in rows}
            by_event = per_event(book, c)
            charges = practice_charges(rows, book, haircut) if book in HAIRCUT_BOOKS else {}
            # observation -> [account log growth, made, at risk, (first entry seq, its liquidity), first close, last close]
            mine: dict[str, list[Any]] = {}
            for row in closed:
                lent = staked_base(stakes, row["seq"])  # `trade_returns` read through this trade's position
                opened = row["entry_seq"] if row["entry_seq"] is not None else row["seq"]
                if lent <= 0 or not within(where, opened):
                    # A trade ENTERED outside the member's stretch in the family is another family's (C8): it counts for
                    # the family whose program opened it, wherever it closes -- as the at-risk entries above and
                    # `Allocator.proven_code` read it (the Deploy B money review, Sept 25, 2026: read by its close, a
                    # real member sent back to practice and rewritten in place before its contracts settled took their
                    # settlements, dates and dollars out of the proven family's real record into its new program's).
                    continue
                key = (event_key(row["instrument"]) if by_event else None) or f"{book}:{member}:{row['seq']}"
                unit = mine.setdefault(key, [0.0, 0.0, 0.0, (math.inf, "taker"), row["seq"], row["seq"]])
                paid = math.fsum(ch for seq, ch in charges.get(row["key"], ()) if opened <= seq <= row["seq"])
                made = row["made"] - paid
                made_by_book["real" if book == REAL_BOOK[venue] else "practice"] += row["made"]
                if is_code((row["instrument"] or {}).get("market_id")):
                    side_of = "real" if book == REAL_BOOK[venue] else "practice"
                    structures[f"{side_of}_closed"] += 1
                    structures[f"{side_of}_log"] += log1p(made / lent)
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
            # An event weighs what it put at risk against the mean this member put at risk on this book (review of #242,
            # Sept 24, 2026): the ratio estimator, sum made / sum at risk within a member's book. Weighed alike, a record
            # of small wins and large losses -- a resting bid filled in full as the price falls through it -- read as an
            # edge while its dollars lost (weather-favorites' practice events on the T0 snapshot: $16.17 at risk on the
            # average win, $38.50 on the average loss; +0.0077 a dollar an event alike, -0.025 a dollar in its dollars).
            # Books, purses and stakes stay on one scale: a member's mean event weighs its book's weight. The account
            # unit already scales an event's growth with what it risked, and keeps Deploy A's weights.
            risks = [u[2] for u in mine.values() if u[2] > 0]
            mean_risk = math.fsum(risks) / len(risks) if risks else 0.0
            for key, (growth, made, risk, (_, liquidity), first, last) in mine.items():
                value = at_risk_value(made, risk, share) if at_risk_unit else growth
                dollars = risk / mean_risk if risk > 0 and mean_risk > 0 else 1.0
                size = dollars if at_risk_unit else 1.0
                units.setdefault(key, []).append((value, weight * size, liquidity, member))
                edges.setdefault(key, []).append((max(made / risk, -1.0) if risk > 0 else (-1.0 if made < 0 else 0.0), weight * dollars))
                day = event_day(key, when.get(last))
                if day is not None:
                    days[key] = min(days.get(key, day), day)
                if book == REAL_BOOK[venue]:
                    real_units.setdefault(key, []).append((value, size))
                    real_first[key] = min(real_first.get(key, first), first)
                    real_at[key] = max(real_at.get(key, 0.0), when.get(last, 0.0))
                    if day is not None:
                        real_days[key] = min(real_days.get(key, day), day)
    minimum, confidence = rule["min_independent_settlements"], rule["confidence"]
    win_rate = float(c["ladder"]["lopsided_win_rate"]) if rule["lopsided_gate"] else None
    risk_per_entry = math.fsum(risked) / len(risked) if risked else 1.0  # with no entry seen, all of it was at risk
    # The gate reads a lopsided record as an account's growth: in the account unit, one that put the
    # family's mean cash an entry at risk; in the at-risk unit, the reference bet (`reference_share`).
    gate = {"win_rate": win_rate, "risk": share if at_risk_unit else risk_per_entry, "scale": share if at_risk_unit else 1.0}

    # M2 of the forward-first run (Sept 25, 2026): the TAKER record, which lets a family's bunts take on the real book
    # (`allocator.real_entry_liquidity`), is positive from `allocator.taker_proof_min` independent taker events with its
    # honest bound above zero; without the key, from the proof's own count.
    taker_min = int((c.get("allocator") or {}).get("taker_proof_min") or minimum)

    def side(liquidity: str | None) -> dict[str, Any]:
        chosen = {k: [u for u in group if liquidity is None or (u[2] == "taker") == (liquidity == "taker")] for k, group in units.items()}
        pooled = pool({k: [(u[0], u[1]) for u in group] for k, group in chosen.items()},
                      taker_min if liquidity == "taker" else minimum, confidence, **gate)
        pooled["members"] = len({u[3] for group in chosen.values() for u in group})
        return pooled

    whole = side(None)
    real = pool(real_units, minimum, confidence, **gate)
    # Each real event as `pool` observes it -- its first close, its value (the weighted mean of its real members'
    # values) and its weight (the largest of theirs) -- in the order of the first closes: the ramp counts the positive
    # ones that closed after the family entered the swing, and the swing's entry is judged on the first ones.
    events = sorted((real_first[k], math.fsum(v * w for v, w in group) / math.fsum(w for _, w in group), max(w for _, w in group))
                    for k, group in real_units.items() if group)
    real["first_closes"] = [(seq, value) for seq, value, _ in events]
    real["closed_at"] = sorted(real_at.values())
    real["dates"] = len(set(real_days.values()))  # M1: the distinct settlement dates the real record spans
    swing = swing_rule(c)
    # The family swing's ENTRY look (`entry_look`): at the real count's checkpoint, on its first events and their dates.
    real["entry"] = entry_look(events, swing, gate=gate, days={real_first[k]: d for k, d in real_days.items()}) if swing else None
    weight_sum = math.fsum(max(w for _, w in group) for group in edges.values())
    edge = (math.fsum(max(w for _, w in group) * math.fsum(r * w for r, w in group) / math.fsum(w for _, w in group)
                      for group in edges.values()) / weight_sum) if weight_sum > 0 else None
    blocks = {"practice": 0, "real": 0, "growth": 0.0}
    for member in members:
        for _, book, active, growth, began in tape.blocks.get(member) or ():
            if active and book in books and within(spans[member], began):
                blocks["real" if book == REAL_BOOK[venue] else "practice"] += 1
                blocks["growth"] += growth
    record = {"family": family, "venue": venue, "through": through, "unit": rule["unit"], "members": len(members),
              "members_living": living, "members_counted": whole.pop("members"), "n": whole["n"], "n_eff": whole["n_eff"],
              "mean_log": whole["mean_log"], "sd": whole["sd"], "bound": whole["bound"], "proven": whole["positive"],
              "state": "proven" if whole["positive"] else "unproven", "real_n": len(real_units), "dates": len(set(days.values())),
              "lopsided": whole.get("lopsided"), "loss_gate": whole.get("loss_gate"), "honest_bound": whole["honest_bound"],
              "risk_per_entry": risk_per_entry, "rows_without_risk": without_risk, "edge_per_dollar": edge,
              "maker": side("maker"), "taker": side("taker"), "real": real, "blocks": blocks, "rule": rule,
              "dollars": {k: round(v, 6) for k, v in made_by_book.items()}, "structures": structures}
    if now is not None and stake_usd is not None:
        record["capacity"] = capacity(tape, members, venue, now=float(now), days=(swing or {}).get("capacity_days", 7.0),
                                      stake_usd=float(stake_usd), edge=edge, real_events=real["closed_at"],
                                      min_markets=(swing or {}).get("capacity_min_markets", 5), constitution=c, spans=spans)
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
           "state": "unproven", "real_n": 0, "dates": 0, "lopsided": None, "loss_gate": None, "honest_bound": None, "risk_per_entry": None,
           "rows_without_risk": 0, "edge_per_dollar": None, "maker": dict(side), "taker": dict(side),
           "real": {**side, "first_closes": [], "closed_at": [], "entry": None}, "blocks": {"practice": 0, "real": 0, "growth": 0.0},
           "rule": rule, "dollars": {"practice": 0.0, "real": 0.0},
           "structures": {"practice_closed": 0, "practice_log": 0.0, "real_closed": 0, "real_log": 0.0}}
    if error is not None:
        out["error"] = error
    return out


# ---------------------------------------------------------------------------------- the swing
def swing_ready(record: Mapping[str, Any], rule: Mapping[str, Any] | None) -> bool:
    """The swing's HOLD: the whole REAL record has `min_real_settlements` independent real settlements and its
    honest lower bound at the table's confidence (`family_proven.confidence`, 0.8: the t bound, and the loss-rate
    gate for a lopsided record) is above zero. Read at every pass: a swinging family stays, and its ramp doubles,
    only while it holds (the exit side needs no correction for repeated looks). The ENTRY is `entry_ready`."""
    if rule is None:
        return False
    real = record.get("real") or {}
    bound = real.get("honest_bound")
    # M1 (Sept 25, 2026): and the real record spans `min_distinct_dates` distinct settlement dates. The ramp doubles only
    # while the family holds, so every doubling's look asks it too.
    return (int(real.get("n") or 0) >= int(rule["min_real_settlements"]) and bound is not None and bound > 0
            and int(real.get("dates") or 0) >= int(rule.get("min_distinct_dates") or 0))


def entry_checkpoint(n: int, rule: Mapping[str, Any]) -> int | None:
    """The real count the swing's entry is judged at for a REAL record of `n` independent settlements: the last of
    `min_real_settlements`, then every `entry_every` more (15, 20, 25, ...) that `n` has reached, or None below the
    first. Derived from the count alone, so a restart looks at exactly what the pass before it looked at."""
    first, every = int(rule["min_real_settlements"]), max(1, int(rule.get("entry_every", 1)))
    if n < first:
        return None
    return first + every * ((n - first) // every)


def entry_look(events: Sequence[tuple[int, float, float]], rule: Mapping[str, Any] | None, *,
               gate: Mapping[str, Any], days: Mapping[int, str] | None = None) -> dict[str, Any]:
    """The family swing's ENTRY look (C2; the main session's decision on the review of #242, Sept 24, 2026). A
    one-sided 80% bound re-read at every settlement is crossed by an edgeless family far more often than one time in
    five (37% by 30 real settlements and 44% by 50 in the main session's simulation, 61% by 200; and eventually always).
    So the entry is judged only at `entry_checkpoint` -- `min_real_settlements` real settlements and every `entry_every`
    more -- on the FIRST that many real events (`events`: (first close, value, weight) as `pool` observes each), with the
    honest bound at `entry_confidence`: the t bound AND, for a lopsided record, the loss-rate bound (`gate`), both at
    that confidence (19% and 22% by 30 and 50 at every 5th settlement at 90%). Between checkpoints the look stands:
    a failed look waits for the next checkpoint, and a restart looks at the same events. Staying in the swing and each
    doubling are `swing_ready`, at the table's 80% at every pass.

    M1 of the forward-first run (Sept 25, 2026): the looked-at events must also span `min_distinct_dates` distinct
    settlement dates (`days`: each event's own date by its first close, `event_day`), or the look does not pass, whatever
    its bound. The one proven family's first 10 real events lay on 2 slate dates (T0, Sept 25): a count of events cannot
    tell a regime from an edge. `dates_so_far` is how many dates the first events up to the next look span now."""
    confidence = float((rule or {}).get("entry_confidence", 0.8))
    ordered = sorted(events)
    days = days or {}
    minimum_dates = int((rule or {}).get("min_distinct_dates") or 0)
    out: dict[str, Any] = {"checkpoint": None, "next_checkpoint": None, "confidence": confidence, "n": len(ordered),
                           "bound": None, "loss_gate": None, "honest_bound": None, "ready": False,
                           "dates": None, "min_dates": minimum_dates}
    if rule is None:
        return out
    checkpoint = entry_checkpoint(len(ordered), rule)
    first = int(rule["min_real_settlements"])
    out["next_checkpoint"] = first if checkpoint is None else checkpoint + max(1, int(rule.get("entry_every", 1)))
    out["dates_so_far"] = len({days[e[0]] for e in ordered[:out["next_checkpoint"]] if days.get(e[0])})
    if checkpoint is None:
        return out
    looked = pool({str(i): [(value, weight)] for i, (_, value, weight) in enumerate(ordered[:checkpoint])}, checkpoint,
                  confidence, **gate)
    honest = looked["honest_bound"]
    spanned = len({days[e[0]] for e in ordered[:checkpoint] if days.get(e[0])})
    out.update(checkpoint=checkpoint, bound=looked["bound"], loss_gate=looked.get("loss_gate"), honest_bound=honest,
               dates=spanned, ready=honest is not None and honest > 0 and spanned >= minimum_dates)
    return out


def entry_ready(record: Mapping[str, Any], rule: Mapping[str, Any] | None) -> bool:
    """The swing's ENTRY passes at the family's current checkpoint (`entry_look`, computed with its record)."""
    if rule is None:
        return False
    return bool(((record.get("real") or {}).get("entry") or {}).get("ready"))


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
def next_state(previous: str, *, proven: bool, entry: bool, hold: bool, approved: bool) -> str:
    """The family's state after a pass (C2; the main session's decisions on the review of #242, Sept 24, 2026).
    "proven" follows the POOLED record alone (`family_proven`, the table's one proof: a real record strong enough to
    swing on proves the pooled record too, unless the practice record contradicts it, and then it must not swing).
    A proven family ENTERS the swing when its entry look passes at its checkpoint (`entry`) and that entry's audit
    approved it; a swinging family STAYS while its real record holds at the table's 80% (`hold`) and it is still
    proven. Otherwise "proven", or "unproven" without the pooled proof. Leaving the swing returns the members to bunts
    (probes when the proof has gone too), by free cash only, and lapses the approval: re-entry is audited again."""
    if not proven:
        return "unproven"
    if previous == "swing":
        return "swing" if hold else "proven"
    return "swing" if (entry and approved) else "proven"


def row_of(record: Mapping[str, Any], state: Mapping[str, Any], *, swing: Mapping[str, Any] | None,
           members_real: int, stake_usd: Any) -> dict[str, Any]:
    """The compact `family.record` row (and the board's `families` entry): the record, its state and since,
    the stake a member on real money is lent, and the capacity estimate."""
    def r(value: Any, digits: int = 6) -> Any:
        return None if value is None else round(float(value), digits)

    real = record.get("real") or {}
    entry = real.get("entry") or {}
    cap = record.get("capacity") or {}
    return {"family": record["family"], "venue": record["venue"], "unit": record.get("unit"), "state": state.get("state", "unproven"),
            "since": state.get("since"), "n": int(record.get("n") or 0), "n_eff": r(record.get("n_eff"), 3),
            "mean_log": r(record.get("mean_log")), "bound": r(record.get("bound")), "loss_gate": r(record.get("loss_gate")),
            "proven": bool(record.get("proven")), "edge_per_dollar": r(record.get("edge_per_dollar")),
            # M1 and M3 (Sept 25, 2026): the distinct settlement dates the pooled proof and the real record span.
            "dates": int(record.get("dates") or 0),
            "real": {"n": int(real.get("n") or 0), "mean_log": r(real.get("mean_log")), "bound": r(real.get("bound")),
                     "loss_gate": r(real.get("loss_gate")), "honest_bound": r(real.get("honest_bound")),
                     "dates": int(real.get("dates") or 0),
                     # The swing's entry look at the real count's checkpoint, and the count that looks next.
                     "entry": {"checkpoint": entry.get("checkpoint"), "next_checkpoint": entry.get("next_checkpoint"),
                               "confidence": entry.get("confidence"), "honest_bound": r(entry.get("honest_bound")),
                               "dates": entry.get("dates"), "ready": bool(entry.get("ready"))} if entry else None},
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
                         "fill_rate_basis": cap.get("fill_rate_basis"),
                         # C6: the fill curve at 1x, 2x and 4x the stake (`fill_curve`); None where a size is not measured.
                         "curve": [{"multiple": pt["multiple"], "size_usd": r(pt["size_usd"], 2), "fill_rate": r(pt["fill_rate"], 4),
                                    "basis": pt["basis"], "usd_per_day": r(pt["usd_per_day"], 4)} for pt in cap.get("curve") or ()],
                         "binds": bool(swing and swing.get("limit") == "capacity")},
            "swing": None if not swing else {k: (str(v) if isinstance(v, Decimal) else v) for k, v in swing.items()}}


def row_digest(row: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()[:16]


def change_view(row: Mapping[str, Any]) -> dict[str, Any]:
    """What makes a `family.record` row worth writing again: everything but the capacity estimate's rates, which move with
    the clock alone (markets and settlements a day over a window that slides; review of #242, Sept 24, 2026: 36 of the 43
    families followed on the T0 snapshot changed digest every five minutes with no new trade, about 10,000 rows a day
    burying the state changes the rows exist to record). Whether capacity binds a swing stays in it, and a row written
    for any other change carries the capacity of that moment."""
    view = {k: v for k, v in row.items() if k != "capacity"}
    view["capacity_binds"] = bool((row.get("capacity") or {}).get("binds"))
    return view


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


def gaining(blocks: int, growth: float, minimum: int) -> bool:
    """The mirror of `losing`: a pooled forward record POSITIVE over at least `minimum` active blocks, the turn a family
    held by a probe's demotion waits for (`allocator.family_probe`). A record that nets to zero has not turned."""
    return blocks >= minimum and growth >= 1e-9


def bound_gaining(values: Sequence[float], minimum: int, confidence: float) -> tuple[bool, float | None]:
    """M5 of the forward-first run (Sept 25, 2026; `allocator.family_probe` `reseat: "bound_since_demotion"`): (whether a
    record has turned, its lower bound). `values` is one observation per block PERIOD (`Allocator._turned`: the mean of
    the family's active blocks of that hour or day), and the record has turned when there are `minimum` or more of them
    and their one-sided `confidence` lower bound on Student's t is above zero -- not when their sum is (`gaining`). The
    evidence: the zero-edge crypto-alts-reversion (its whole pooled forward record +0.0570 over 423 active blocks at T0,
    an 80% bound of -0.00006 a block) was let back in at 21:00:53Z Sept 24 on six blocks since the 18:47Z demotion that
    summed to +0.0101 -- one hour's blocks of its members, five of them written in the same second. Read one a period,
    those six blocks are two observations; the turn waited until 01:02Z Sept 25 (6 periods, bound +0.0012)."""
    n = len(values)
    if n < 2:
        return False, None
    mean = math.fsum(values) / n
    sd = math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (n - 1))
    bound = mean - stats.t_quantile(confidence, n - 1) * sd / math.sqrt(n)
    return n >= minimum and bound > 1e-12, bound


#: A Kalshi event ticker's date code: YYMONDD at the start of its second segment (`KXMLBTOTAL-26SEP231840MILPHI`,
#: `KXHIGHNY-26SEP24`, `KXBTCD-26SEP2401`).
_DATE_CODE = re.compile(r"^(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})")
_MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}


def event_day(key: str | None, closed_at: float | None) -> str | None:
    """An observation's OWN settlement date, "YYYY-MM-DD" (M1 and M3 of the forward-first run, Sept 25, 2026): the date code
    of its Kalshi event (`evaluator.event_key`: the day the game was played, the city's weather day, the strike's hour's
    day), else the UTC date of its last close (an Alpaca trade: a US stock's session is inside one UTC date), else None
    (counted toward no date). The event's own date, not the UTC date it settled on: a night MLB slate settles across two
    UTC dates (on the T0 snapshot the real Sept 24 slate settled one event on Sept 24 UTC and five on Sept 25), and one
    slate -- one regime's day -- must count once."""
    parts = str(key or "").upper().split("-")
    if len(parts) >= 2:
        found = _DATE_CODE.match(parts[1])
        if found:
            with contextlib.suppress(ValueError):
                return datetime(2000 + int(found.group(1)), _MONTHS[found.group(2)], int(found.group(3))).strftime("%Y-%m-%d")
    if closed_at:
        return datetime.fromtimestamp(float(closed_at), tz=timezone.utc).strftime("%Y-%m-%d")
    return None


def first_real_at(tape: TradeTape, members: Iterable[str], venue: str) -> float | None:
    """When the family's first real dollar was lent (the earliest `book.stake` above zero on the venue's real book, any
    member, living or dead), in epoch seconds, or None: where the family's real life starts."""
    book = REAL_BOOK.get(venue)
    first = None
    for member in members:
        for row in tape.rows.get(member) or ():
            if row.kind != "book.stake" or row.payload.get("book") != book or not row.at:
                continue
            try:
                lent = float(row.payload.get("usd") or 0)
            except (TypeError, ValueError):
                continue
            if lent > 0 and (first is None or row.at < first):
                first = row.at
    return first


def swing_clock(record: Mapping[str, Any], rule: Mapping[str, Any] | None, *, first_real: float | None,
                now: float, released: bool | None = None) -> dict[str, Any] | None:
    """The family's clock to its swing (R3 of the close-the-gaps run, Sept 24, 2026; the board's `families`, never a
    `family.record` row: it moves with the clock alone). `real_per_day`: its independent REAL settlements a day over its
    real life, from its first real dollar (`first_real_at`), once that life is an hour long (a rate over minutes is
    noise); `needs`: what the family swing (`allocator.family_swing`) still asks -- the real settlements to the next entry
    look (`min_real_settlements`, then every `entry_every`), the confidence that look's bound is read at, whether the
    pooled proof is still missing, the audit that follows a passing look, and whether the live grant does not yet release
    stakes above the bunt (`grant`, when `released` is known); `days_to_swing`: the days to that look at the family's own
    real rate. None where no estimate stands: no rate yet, no member on real money (its real record does not grow), or
    nothing left to count but the pooled proof. A swinging family needs nothing; one whose look passed waits only for its
    audit. The owner's notes at the resume (Sept 24, 2026 14:30Z) read sports-central-run-under, the one proven family, at
    real n 5 against 15: this is that clock, read from the rule itself."""
    if rule is None:
        return None
    real = record.get("real") or {}
    entry = real.get("entry") or {}
    n = int(real.get("n") or 0)
    swinging = record.get("state") == "swing"
    proven = bool(record.get("proven"))
    days = max(now - first_real, 0.0) / DAY if first_real is not None else None
    rate = (n / days if n > 0 else 0.0) if days is not None and days >= 1 / 24 else None
    dates = 0  # M1 (Sept 25, 2026): the distinct settlement dates the next look's events still lack
    if swinging:
        needed, look = 0, None
    elif entry.get("ready"):
        needed, look = 0, entry.get("checkpoint")  # the look passed: the entry's audit is what is left
    else:
        look = int(entry.get("next_checkpoint") or rule["min_real_settlements"])
        needed = max(look - n, 0)
        dates = max(int(rule.get("min_distinct_dates") or 0) - int(entry.get("dates_so_far") or 0), 0)
    if swinging or (needed == 0 and dates == 0 and proven):
        to_swing = 0.0
    elif (needed == 0 and dates == 0) or not rate or int(record.get("members_real") or 0) <= 0:
        to_swing = None
    else:
        to_swing = max(needed / rate, float(dates))  # a new settlement date comes at most once a day
    return {"real_n": n, "real_since": None if first_real is None else datetime.fromtimestamp(first_real, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"), "real_days": None if days is None else round(days, 3),
            "real_per_day": None if rate is None else round(rate, 3),
            "needs": {"real_settlements": needed, "look_at": look, "confidence": float(rule["entry_confidence"]), "distinct_dates": dates,
                      "proof": not proven, "audit": not swinging,
                      "grant": None if released is None or swinging else not released},
            "days_to_swing": None if to_swing is None else round(to_swing, 2)}


def score(record: Mapping[str, Any], state: str) -> int:
    """What a family's record says to a search that weighs lineages (`Lab.lineage_weights` may read it): +1 when
    the family is proven or swinging, -1 when its pooled mean is below zero after the proof's minimum count of
    independent settlements, else 0. Nothing here moves anyone's band."""
    if state in ("proven", "swing"):
        return 1
    minimum = int((record.get("rule") or {}).get("min_independent_settlements", 10))
    return -1 if int(record.get("n") or 0) >= minimum and float(record.get("mean_log") or 0.0) < 0 else 0


# ------------------------------------------------------------------------------------ the key (C8)
#: The House's own `agent.family` row that records the one-time re-key of the labels born before C8 (C8 of the
#: forward-first run, Sept 25, 2026): what it moved, and the ledger position whose programs it checked (`through`).
REKEY_ID = "family-key:rekey"
#: The rows a family's key is folded from: births, program changes and family changes.
KEY_KINDS = ("agent.born", "agent.strategy", "agent.family")


def family_key_rule(constitution: Mapping[str, Any] | None = None) -> str:
    """`allocator.family_key` (C8): "mechanism", or "label" where the constitution has no such key -- a birth's family is
    then the label it is given (with the Sept 24 rule for a research fork's other markets or style,
    `House._program_family`), as before C8."""
    allocator = (constitution or CONSTITUTION).get("allocator") or {}
    return "mechanism" if allocator.get("family_key") == "mechanism" else "label"


def _names(value: Any) -> tuple[str, ...]:
    items = [value] if isinstance(value, str) else (value if isinstance(value, (list, tuple, set)) else ())
    return tuple(sorted({str(v).upper() for v in items}))


def program_needs(needs: Any) -> dict[str, Any]:
    """What a program's key and a new family's name read of its NEEDS: its venue, series, symbols and style."""
    n = needs if isinstance(needs, Mapping) else {}
    return {"venue": str(n.get("venue") or "").lower(), "series": _names(n.get("series")), "symbols": _names(n.get("symbols")),
            "style": re.sub(r"[^a-z0-9-]+", "-", str(n.get("style") or "").lower()).strip("-")}


def mechanism_key(code: str | None, needs: Any, *, digest: str | None = None) -> str | None:
    """What a program IS (C8, Sept 25, 2026): its code beyond its PARAMS literal -- the line `parameters.same_logic`
    draws for a repair ("literal PARAMS and comments, never decision code or NEEDS"), which `lab.mechanism_digest`
    digests (no PARAMS, docstrings or comments; its NEEDS literal without the knobs `lab.MECHANISM_IGNORED_NEEDS`: a
    style label, parameter bounds, the wake cadence, a market window) and R3 already reads to say which members run a
    proven family's program -- with the venue, series and symbols its NEEDS trade once its desk held them
    (`niches.constrain`). Two programs with one key differ only in parameters. None for code that does not parse.
    `digest`: its `lab.mechanism_digest`, when the caller has it."""
    from .lab import mechanism_digest

    body = digest if digest is not None else (mechanism_digest(code) if code else None)
    if body is None:
        return None
    lite = program_needs(needs)
    return hashlib.sha256(json.dumps([body, lite["venue"], lite["series"], lite["symbols"]]).encode()).hexdigest()[:16]


def family_name(desk: str, style: str, key: str, width: int = 6) -> str:
    """The name of a family a new mechanism founds: `<desk>-<style>-<key>`, at most 40 characters (the site takes ids of
    40), the shape of the Sept 24 rule's names (`House._program_family`) with the mechanism's key for its tail."""
    style = style or "program"
    base = style if (desk and style.startswith(desk)) or not desk else f"{desk}-{style}"
    return f"{base[:39 - width].rstrip('-')}-{key[:width]}"


class _Program(NamedTuple):
    seq: int  # where it took effect: the agent's birth, or its `agent.strategy` row
    row: str  # the id of the ledger row that carries its code (`_code`)
    code_sha: str
    needs: dict  # `program_needs`


class MechanismIndex:
    """Which family each program belongs to under C8 (`allocator.family_key` "mechanism", Sept 25, 2026), folded from
    the ledger's births, program changes and family changes (`KEY_KINDS`).

    `refresh(ledger, check_after=...)` CHECKS every program that took effect after that ledger position as it folds it
    -- a birth against the rule it should have been born by (`place`), an in-place rewrite against its family's
    mechanism -- and returns the `agent.family` rows that put each misfiled one right, applied here at once so the
    programs after it are placed as the floor will hold them. `check_after=0` is the one-time re-key of every label
    born before C8; later, the House checks what was written since it last looked (a release without C8 could have
    run meanwhile) and each new birth and rewrite. Everything before `check_after` is trusted as the rows say.

    A family's mechanism is its first program's (`family_mechanism`: the earliest stretch any agent spent in it, read
    from the `agent.family` row that began it when that row names one). After the re-key every stretch of a family
    runs that mechanism, so a member's program is its family's."""

    def __init__(self) -> None:
        self.cursor = 0
        self.venue: dict[str, str] = {}
        self.desk: dict[str, str] = {}
        self.parent: dict[str, str | None] = {}
        self.programs: dict[str, list[_Program]] = {}
        self.segments: dict[str, list[tuple[int, str, int]]] = {}  # as `TradeTape.segments`, for every agent
        self.named: dict[tuple[str, int], str] = {}  # (agent, since) -> the mechanism the `agent.family` row names
        self.carriers: dict[tuple[str, str], set[str]] = {}  # (family, venue) -> agents with a segment there
        self._keys: dict[tuple[str, int], str | None] = {}  # (agent, program seq) -> its `mechanism_key`
        self._digests: dict[str, str | None] = {}  # code sha256 -> `lab.mechanism_digest`
        self._founding: dict[tuple[str, str], tuple[int, str] | None] = {}  # memo: (family, venue) -> (since, agent)
        self._ledger: Any = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ folding
    def refresh(self, ledger: Any, *, check_after: int | None = None) -> list[dict[str, Any]]:
        """Fold the rows after the cursor. With `check_after`, check each program that took effect after that position
        and return the `agent.family` rows (`{"agent", "id", "payload"}`) that re-key the misfiled ones, in ledger
        order; the caller writes them."""
        out: list[dict[str, Any]] = []
        with self._lock:
            self._ledger = ledger
            for entry in ledger.iter(kinds=KEY_KINDS, after=self.cursor):
                out.extend(self._fold(entry, check_after is not None and entry.seq > check_after))
                self.cursor = entry.seq
        return out

    def _fold(self, entry: Any, check: bool) -> list[dict[str, Any]]:
        if entry.agent == HOUSE:
            return []
        agent, p = str(entry.agent), entry.payload
        if entry.kind == "agent.born":
            code = p.get("_code")
            program = _Program(entry.seq, entry.id, str(p.get("code_sha256") or hashlib.sha256(str(code or "").encode()).hexdigest()),
                               program_needs(p.get("needs")))
            self.venue[agent], self.desk[agent], self.parent[agent] = str(p.get("venue") or ""), str(p.get("specialty") or ""), p.get("parent")
            self.programs[agent] = [program]
            label = str(p.get("family") or "")
            placed = None
            if check:
                self._remember(program, code)
                placed = self.place(label, self.venue[agent], self.key(agent, program), parent=p.get("parent"),
                                    desk=self._desk(agent), style=program.needs["style"])
            self._segment(agent, entry.seq, label, entry.seq)
            if placed is not None and placed[0] != label:
                return [self._rekey(agent, entry.seq, placed[0], was=label, why=placed[1], key=self.key(agent, program))]
            return []
        if agent not in self.programs:
            return []
        if entry.kind == "agent.strategy":
            code = p.get("_code")
            sha = str(p.get("code_sha256") or hashlib.sha256(str(code or "").encode()).hexdigest())
            last = self.programs[agent][-1]
            if sha == last.code_sha:
                return []  # a restatement: a pause, a resume, an edit of PARAMS, the House's note of a rewrite
            program = _Program(entry.seq, entry.id, sha, program_needs(p.get("needs")) if p.get("needs") else last.needs)
            self.programs[agent].append(program)
            if not check:
                return []
            self._remember(program, code)
            key, home, venue = self.key(agent, program), self.family(agent), self.venue[agent]
            if key is None or self.family_mechanism(home, venue) in (None, key):
                return []
            family, why = self.place(home, venue, key, desk=self._desk(agent), style=program.needs["style"], rewrite=True)
            if family == home:
                return []
            return [self._rekey(agent, entry.seq, family, was=home, why=f"it rewrote itself at ledger position {entry.seq}: {why}",
                                key=key)]
        if entry.kind == "agent.family" and p.get("family"):
            since = int(p.get("since_seq") or entry.seq)
            if p.get("mechanism"):
                self.named[(agent, since)] = str(p["mechanism"])
            self._segment(agent, since, str(p["family"]), entry.seq)
        return []

    def _segment(self, agent: str, since: int, family: str, row: int) -> None:
        segments = self.segments.setdefault(agent, [])
        venue = self.venue.get(agent, "")
        touched = {name for _, name, _ in segments} | {family}
        place_segment(segments, since, family, row)
        self.carriers.setdefault((family, venue), set()).add(agent)
        for name in touched:
            self._founding.pop((name, venue), None)

    def _rekey(self, agent: str, since: int, family: str, *, was: str, why: str, key: str | None) -> dict[str, Any]:
        """One re-key row, applied here now (the caller writes it; folding it again changes nothing)."""
        if key:
            self.named[(agent, since)] = key
        self._segment(agent, since, family, since)
        return {"agent": agent, "id": f"family-key:{agent}:{since}",
                "payload": {"family": family, "was": was, "venue": self.venue.get(agent, ""), "since_seq": since, "mechanism": key,
                            "why": why[:600], "rule": "allocator.family_key"}}

    def _desk(self, agent: str) -> str:
        desk = self.desk.get(agent) or ""
        return desk.split("-", 1)[-1] if desk else self.venue.get(agent, "")

    # ------------------------------------------------------------------ keys
    def _remember(self, program: _Program, code: Any) -> None:
        """The digest of a program whose code is in hand (a checked row): no second read of the ledger for it."""
        if program.code_sha not in self._digests and code:
            from .lab import mechanism_digest

            self._digests[program.code_sha] = mechanism_digest(str(code))

    def key(self, agent: str, program: _Program) -> str | None:
        """The program's `mechanism_key`, its code read from its ledger row when not in hand (a trusted row)."""
        memo = (agent, program.seq)
        if memo not in self._keys:
            if program.code_sha not in self._digests:
                row = self._ledger.get(program.row) if self._ledger is not None else None
                self._remember(program, (row.payload if row is not None else {}).get("_code"))
            digest = self._digests.get(program.code_sha)
            self._keys[memo] = mechanism_key(None, program.needs, digest=digest) if digest is not None else None
        return self._keys[memo]

    def key_of(self, code: str, needs: Any) -> str | None:
        """The `mechanism_key` of a program about to be born (its digest kept for the check of its birth row)."""
        sha = hashlib.sha256(str(code).encode("utf-8")).hexdigest()
        with self._lock:
            if sha not in self._digests:
                from .lab import mechanism_digest

                self._digests[sha] = mechanism_digest(str(code))
            digest = self._digests[sha]
        return mechanism_key(None, needs, digest=digest) if digest is not None else None

    def program_at(self, agent: str, seq: int) -> _Program | None:
        """The program `agent` ran at a ledger position: its birth's, or its latest program change at or before it."""
        found = None
        for program in self.programs.get(agent) or ():
            if program.seq <= seq:
                found = program
        return found

    # ------------------------------------------------------------------ reads
    def family(self, agent: str) -> str | None:
        """The family `agent` is in now."""
        segments = self.segments.get(agent)
        return segments[-1][1] if segments else None

    def founding(self, family: str, venue: str) -> tuple[int, str] | None:
        """(since, agent) of the earliest stretch any agent spent in `family` on `venue`, or None: no agent's rows were
        ever that family's (a label every program born with it was re-keyed away from is not a family)."""
        memo = (family, venue)
        if memo not in self._founding:
            best = None
            for agent in self.carriers.get(memo, ()):
                segments = self.segments.get(agent) or []
                for i, (since, name, _) in enumerate(segments):
                    end = segments[i + 1][0] if i + 1 < len(segments) else math.inf
                    if name == family and since < end and (best is None or (since, agent) < best):
                        best = (since, agent)
            self._founding[memo] = best
        return self._founding[memo]

    def family_mechanism(self, family: str | None, venue: str) -> str | None:
        """The mechanism of `family`: its first program's (`founding`), None for no such family or unreadable code."""
        first = self.founding(family, venue) if family else None
        if first is None:
            return None
        since, agent = first
        if (agent, since) in self.named:
            return self.named[(agent, since)]
        program = self.program_at(agent, since)
        return self.key(agent, program) if program is not None else None

    def place(self, label: str, venue: str, key: str | None, *, parent: str | None = None, desk: str = "", style: str = "",
              rewrite: bool = False) -> tuple[str, str]:
        """(family, why): the family a program belongs to under C8, read BEFORE it is filed.

        - Its code cannot be read (no key): the family it was given.
        - A child whose program is its parent's family's mechanism beyond PARAMS: its PARENT'S family, whatever label it
          was given -- a House mutation of the parent's parameters, an Alpha Lab graduate that nudged its parent's
          PARAMS (five lab families of the T0 snapshot were such nudges, each under a label of its own).
        - A founder (no parent), or a child whose program is not its parent's: the family it was given, when no agent's
          rows were ever that family's or that family's mechanism is its own ("a founder founds its own family keyed by
          its mechanism"); a research child's label is its parent's family, which is another mechanism by then.
        - Else, and for an agent that rewrites itself into another mechanism (`rewrite`): the family its mechanism names
          (`family_name`: `<desk>-<style>-<key>`, with more of the key where that name is already another
          mechanism's), which a second program with the same key joins."""
        with self._lock:
            return self._place(label, venue, key, parent=parent, desk=desk, style=style, rewrite=rewrite)

    def _place(self, label: str, venue: str, key: str | None, *, parent: str | None, desk: str, style: str,
               rewrite: bool) -> tuple[str, str]:
        if key is None:
            return label, "its program could not be read, so it keeps the family it was given"
        home = self.family(parent) if parent else None
        if home is not None and self.family_mechanism(home, venue) == key:
            return home, f"it runs its parent {parent}'s program beyond PARAMS: the mechanism of {home}"
        if not rewrite and label and label != home:
            if self.founding(label, venue) is None or self.family_mechanism(label, venue) == key:
                return label, f"its program founds {label}" if self.founding(label, venue) is None else f"its program is {label}'s mechanism"
        against = f"{parent}'s program" if home is not None else f"{label}'s mechanism"
        for width in (6, 8, 10, 12, 16):
            name = family_name(desk, style, key, width)
            if self.founding(name, venue) is None or self.family_mechanism(name, venue) == key:
                return name, (f"its program differs from {against} beyond PARAMS, or in its venue, series or symbols: it is "
                              f"{'the mechanism of ' if self.founding(name, venue) is not None else 'the first of its mechanism, '}{name}")
        return label, "no name was left for its mechanism, so it keeps the family it was given"
