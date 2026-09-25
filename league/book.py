"""One netting book per venue account.

Every agent that trades on a venue trades through that venue's one `Book`. The book

- keeps each agent's cash and holdings, folded from the ledger and from nothing else, so a
  restart rebuilds exactly the state the ledger records;
- runs every intent through the first run's deterministic risk engine (`ltcm/risk.py`, all 21
  rules, unchanged) plus the league's own rules: the $75 order cap the gateway also enforces, a
  per-agent position cap set by the agent's rung, no leverage, no shorts, and no order that
  could trade against one of the House's own resting orders;
- nets the market orders of one batch: opposite sides on one instrument are crossed inside the
  House and only the difference is sent to the venue, so two agents on one account never trade
  against each other (a wash trade, and double fees). A crossed agent is filled exactly as the
  venue would have filled it alone: the buyer pays the ask, the seller receives the bid, both
  pay the taker fee. The spread and fees the account did not actually pay accrue to the House
  row of the book, which is what keeps the agents' books summing to the venue's.
- attributes venue fills back to the intents behind an order pro rata, by largest remainder on
  the instrument's quantity step;
- reconciles its total cash and positions to the venue's, and books sub-cent differences as dust.

Limit orders are never pooled: each is one venue order owned by one agent, so its fills need no
apportioning. An ENTRY that would cross one of the House's own resting orders is refused, as a
venue refuses a post-only order that would cross: the agent re-prices or waits.

Exits are never walled off (D3, Sept 24, 2026). A sell that would cross the House's own resting
order is cleared instead: the seller's own crossing order is cancelled first; a peer's resting bid
is cancelled at the venue and, once the venue has confirmed the cancel and what had filled, the two
are crossed inside the House (`_cross_resting`: the seller a taker at the market's bid, what its venue
would have paid it alone, never under its own limit; the bidder a maker at its own limit; the House
row keeping the gap and balancing, one `book.cross_plan`; no fresh market bid, no cross); what cannot be crossed so (a cancel not
confirmed, an order the venue has not acknowledged, any doubt) is re-priced as a post-only limit at
the ask, and the order row says why. Before, 74 sells in the 48 hours to Sept 24 01:42Z were
refused against a sibling's resting bid, and their positions sat hours past their stops.

The real book's entry rules (X0, Sept 24, 2026) are read through the allocator's constitution keys:
`longshot_floor_real`, `real_entry_liquidity` and `max_event_share` (`_real_entry_reasons`).

Sliced exits (Sept 23, 2026). A sell -- an agent's exit, a wind-down, the horizon rule, a stop --
worth more than the order cap is sent as SLICES, each its own venue order of at most the cap,
each with a distinct, deterministic client order id. The slices' fills are attributed to the one
intent, per slice, and the book reconciles after each. The plan behind them is durable
(`book.exit_plan`): a slice the venue or the book refuses, or one that fills only in part, leaves
the rest to the next pass (`poll`), which sizes the next slice off what is still held, and a
restart resumes the plan without sending any slice twice. Until then a position could only be as
large as one order could close. Entries are unchanged: each is one order of at most the cap.

Kalshi legs: an agent holds YES or NO contracts of a market as separate long holdings, never a
short. For crossing checks both legs are read in YES price space, because a NO bid at q is a YES
offer at 1 - q and would trade against a resting YES bid at or above it.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence

from ltcm.broker import (
    Broker,
    BrokerError,
    Instrument,
    Order,
    OrderIntent,
    Position,
    Quote,
    RejectedOrder,
    money,
)
from ltcm.risk import RiskContext, RiskEngine, add_event_exposure, cluster_at_risk, event_cluster, gross_exposure

from .constitution import CONSTITUTION
from .fees import CENT, QTY_PLACES, Charge, Fees, received
from .ledger import HOUSE, Ledger, now_iso

ZERO = Decimal(0)
ONE = Decimal(1)
CASH_PLACES = Decimal("0.00000001")
#: How many readings in a row a PRACTICE book may fail to reconcile before it takes the venue's
#: word for what is held. Three is about a quarter of an hour: long enough for an order whose poll
#: failed to be polled again and settle itself, short enough that no desk loses an afternoon.
ADOPT_AFTER = 3
DUST_USD = Decimal("0.01")
#: A PRACTICE book's cash difference under this, with every position agreeing and no order of
#: unknown outcome, is booked to the House row as dust at once: never a freeze (`_reconcile`).
#: Sept 24, 2026, 14:39:07Z: `alpaca-paper` read "cash differs by -0.0322" -- $0.03 the venue took
#: at the fill of krasker-14's one-contract AAL option buy (the OCC clearing fee, which Alpaca lists
#: as a FEE activity only the next morning, so `_book_venue_fees` cannot see it yet) and $0.0022 of
#: cent rounding on a $28 BTC buy -- and refused every Alpaca practice entry until 14:51:06Z, when
#: four more fills had raised the per-fill tolerance past it. The same cents froze the book every
#: day (adopted after three readings at -0.1436 Sept 21, -0.0200 Sept 22, -0.0326 Sept 23, +0.8616
#: Sept 24 11:40Z), and at 15:37:27Z Sept 24 (-0.0269: krasker-6's AAL buy, $0.03, less a stock
#: sale's rounding) the freeze was the reading that rolled Deploy C back inside its watch. A cent
#: per fill (`DUST_USD`) is the venue's rounding; a practice book's option fees and maker refunds are
#: cents more, and a dollar is far above them all and far below what an unbooked fill moves (the
#: smallest Alpaca order is $10). Real-money books keep the freeze: there it is the point.
PRACTICE_DUST_USD = Decimal("1.00")
#: H4 (the forward-first run, Sept 25, 2026): the bounds of `allocator.real_book_dust_usd`, the line
#: under which a REAL book's cash difference that the venue's own fees explain is booked to the House
#: row as dust, with an error alert, instead of freezing every entry on the venue
#: (`Book._explain_real_cents`). A key outside them, or one that cannot be read, is no key at all:
#: the book freezes as it did before (`real_book_dust_usd`).
REAL_BOOK_DUST_BOUNDS = (Decimal("0.25"), Decimal("1.00"))
#: What Alpaca takes from cash at an option or stock fill and lists as a FEE activity only hours
#: later, so that no fill row and no listed activity shows it when the book next reads the venue:
#: the regulators' fees (ORF and CAT on every option contract; TAF and the SEC fee on sales; CAT on
#: stock fills), each kept as a running day total rounded UP to the cent as it grows. Measured:
#:   - the real account, Sept 24, 2026: the one-contract AAL call bought at 18:19:57Z (premium $19.00,
#:     OCC fee $0.03) took $19.06 from cash at the fill; the $0.03 more was listed at 20:35:02Z ("ORF fee
#:     for proceed of 2 contracts", $0.03) and 00:31:38Z Sept 25 ("CAT fee for proceed of 2 trades",
#:     $0.01). The second contract, at 18:52:18Z, took $0.01 more than its premium and OCC fee;
#:   - the paper account, Sept 21-23: ORF $0.11 for 7 contracts, $0.23 for 15, $0.38 for 25 ($0.0152
#:     a contract); OPT TAF $0.03 for 8 contracts sold, $0.04 for 11; OPT REG $0.01 on $134-201 of sales.
#: One fill can so take at most a cent for each of the four fees' rounding, $0.0152 (ORF) and $0.0035
#: (TAF) a contract, or a stock's $0.000166 a share of TAF and $0.0000278 a dollar of SEC fee (a cent
#: on the $60 of a stock probe): the room each fill leaves, below. Crypto fees are the book's own
#: model, charged at the fill (`league/fees.py`), and leave no room.
UNLISTED_FEE_PER_FILL_USD = Decimal("0.04")
UNLISTED_FEE_PER_CONTRACT_USD = Decimal("0.02")
UNLISTED_FEE_PER_SHARE_USD = Decimal("0.0002")
#: How long a fill's room lasts. The real account took the regulators' cents at the fill (Sept 24),
#: and the book reads the venue every five minutes, so the first clean reading after the fill meets
#: them; six hours (a US session) covers a book held frozen for another reason meanwhile, no longer.
UNLISTED_FEE_HOURS = 6
#: How long an event position the venue no longer shows may wait for its settlement row.
SETTLEMENT_GRACE_SECONDS = 300

#: What the adapters' open statuses look like to the book.
OPEN_STATUSES = ("new", "accepted", "partially_filled", "unknown")
#: How long a sliced exit keeps sending what is left of it. An exit the venue will not take for an
#: hour (a closed market, a kill switch, a book with no bid) ends; the agent, the wind-down or the
#: horizon rule asks again on a later wake, with a fresh intent, and the plan does not outlive the
#: agent's wish by a trading session.
EXIT_PLAN_TTL_SECONDS = 3600
#: An order the venue never acknowledged (`new`, `unknown`) is "never arrived" only once the venue
#: has said it has no such order on two polls at least this far apart (Sept 23, 2026, workstream B:
#: 153 alpaca-paper orders were closed "the venue has no such order" on one look, 149 of them the
#: venue's own 403 refusals an older adapter read as unknown, 4 of them lost in a gateway outage;
#: none had a fill, but one look at a venue that answers 404 while it catches up would have lost
#: one). And for this long after that verdict the book keeps asking, once a poll: an order the
#: venue has after all is revived and its fill booked, never stranded as a position diff.
NEVER_ARRIVED_SECONDS = 60
NEVER_ARRIVED_RECHECK_SECONDS = 900
NEVER_ARRIVED = "the venue has no such order"
#: How often, and how far apart, an exit clearing the House's own order in its way (D3) reads that
#: order again when the venue has not yet confirmed its cancel: Alpaca answers a cancel with 204 and
#: moves the order through `pending_cancel` (read as open) to `canceled`. Past these reads the
#: cancel is not confirmed within the pass, and the exit rests post-only at the ask instead.
CANCEL_CONFIRM_READS = 2
CANCEL_CONFIRM_WAIT_SECONDS = 0.25
#: What the gateway counts an Alpaca market order at: the venue's own touch plus ten per cent
#: (`gateway/lib/router.mjs`, "a market order may fill through the touch"). A slice sized on this
#: price fits the gateway's per-order cap on its own pricing, not only on the book's.
GATEWAY_MARKET_MARKUP = Decimal("1.10")


class BookError(RuntimeError):
    """The book cannot do what was asked (not a refusal of one intent: those are outcomes)."""


def q_cash(value: Decimal) -> Decimal:
    return money(value).quantize(CASH_PLACES)


def text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def step_of(instrument: Instrument, order_type: str = "market") -> Decimal:
    """The smallest quantity increment the venue takes for this instrument. An equity order is
    fractional whether market or limit (Sept 23, 2026, A7: a limit order was held to whole shares,
    so a $25 stock bunt could rest no bid at all; Alpaca takes a fractional limit order as a `day`
    order, which `default_tif` gives and `Book.check` requires)."""
    if instrument.asset_class in ("event", "option", "future"):
        return ONE
    return QTY_PLACES


def yes_space(instrument: Instrument, side: str, price: Decimal | None) -> tuple[str, Decimal | None]:
    """An order's side and price in the market's YES price space (identity for everything else)."""
    if instrument.asset_class != "event" or (instrument.right or "yes") == "yes":
        return side, price
    flipped = "sell" if side == "buy" else "buy"
    return flipped, (None if price is None else ONE - price)


def position_key(instrument: Instrument) -> str:
    """One spelling for one position, however the venue or an agent wrote it. Alpaca reports a
    crypto position as `BTCUSD` and takes orders for `BTC/USD`; a strike comes back `650.000`."""
    symbol = instrument.symbol.upper()
    if instrument.asset_class == "crypto":
        return f"crypto:{symbol.replace('/', '').replace('-', '')}:{instrument.venue}"
    if instrument.asset_class == "option":
        strike = format(money(instrument.strike).normalize(), "f")
        return f"option:{symbol}:{instrument.venue}:{instrument.expiry}:{strike}:{instrument.right}"
    if instrument.asset_class == "event":
        ticker = (instrument.market_id or symbol).upper()
        return f"event:{ticker}:{instrument.venue}:{instrument.right or 'yes'}"
    return f"{instrument.asset_class}:{symbol}:{instrument.venue}"


def market_key(instrument: Instrument) -> str:
    """What two orders must share to be able to trade against each other."""
    if instrument.asset_class == "event":
        return f"event:{(instrument.market_id or instrument.symbol).upper()}:{instrument.venue}"
    return instrument.key


def _event_of(ticker: str) -> str:
    """The Kalshi event a market belongs to: the evaluator's `event_key` (the ticker's first two `-`
    segments, SERIES-EVENT, as Kalshi's own `event_ticker` reads; a ticker of fewer than three segments
    is its own event), so the book's `max_event_share` and the allocator's event counts can never
    disagree on what one bet is (Deploy A's integration, Sept 24, 2026; the review of #226 had found
    the book dropping only the LAST segment, which made each player of one game its own event)."""
    from .evaluator import event_key

    return event_key({"market_id": str(ticker or "")}) or str(ticker or "").strip().upper()


def real_book_dust_usd() -> Decimal | None:
    """`allocator.real_book_dust_usd` (H4), or None when it is absent, unreadable or outside
    `REAL_BOOK_DUST_BOUNDS` ($0.25-1.00, the owner's table): then a real book books no cents it
    cannot fold into its per-fill tolerance, and freezes, exactly as before the key existed."""
    value = _allocator_rule("real_book_dust_usd")
    low, high = REAL_BOOK_DUST_BOUNDS
    if value is None or not value.is_finite() or not low <= value <= high:
        return None
    return value


def _allocator_rule(key: str) -> Decimal | None:
    """A decimal money rule of the allocator's constitution that the book reads (X0), or None when
    the key is absent or unreadable: then the book is exactly as it was without it."""
    value = (CONSTITUTION.get("allocator") or {}).get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        return money(str(value) if isinstance(value, (int, float)) else value)
    except (ValueError, ArithmeticError):
        return None


#: `allocator.real_entry_liquidity`'s one value that holds a real event entry to a post-only limit.
MAKER_UNLESS_TAKER_POSITIVE = "maker_unless_family_taker_positive"
#: What the House tells an agent whose own resting order stood in its exit's way (`_clear_the_way`).
OWN_CROSS_WHY = ("cancelled by the House: your own exit of this instrument would have met it, and an account never "
                 "trades against itself")
#: What a peer is told when its resting bid is cancelled to cross another agent's exit inside the House.
PEER_CROSS_WHY = ("cancelled by the House to cross another agent's exit inside the House at your limit, as a maker "
                  "(see your cross fill); the rest of this bid is not re-placed: bid again at your next wake if you "
                  "still want it")
#: What an agent is told when its own new sell replaces an exit the House had re-priced (`_withdraw_repriced`), when
#: the House re-prices such an exit again at a later pass (`_recheck_repriced`), and on the order sent again.
SUPERSEDED_WHY = ("cancelled by the House: your newer sell of this instrument replaces this exit, which the House had "
                  "re-priced for you")
RECHECK_WHY = ("cancelled by the House to send your exit again: the House's own orders that stood in its way have "
               "changed since it was re-priced")
RESENT_NOTE = ("sent again by the House as you asked: nothing of the House's stands in its way any more; your "
               "re-priced exit was cancelled first")
#: What that peer is told when the venue confirmed the House's cancel only after the pass had given the cross up
#: (`_clear_the_way`: two re-reads, then doubt): its bid is gone and nothing was crossed (review of #226).
PEER_UNCROSSED_WHY = ("cancelled by the House to cross another agent's exit inside the House, but the venue confirmed "
                      "the cancel too late for the cross, so nothing was crossed: bid again at your next wake if you "
                      "still want it")


# --------------------------------------------------------------------------------------- data
@dataclass(frozen=True)
class Intent:
    """One agent's wish to trade. `id` is derived, so a retried batch is the same batch."""

    id: str
    agent: str
    instrument: Instrument
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None
    post_only: bool
    time_in_force: str
    reason: str
    created_at: str
    expires_at: str | None = None

    @classmethod
    def new(
        cls,
        *,
        agent: str,
        instrument: Instrument,
        side: str,
        quantity: Any,
        order_type: str = "market",
        limit_price: Any = None,
        post_only: bool = False,
        time_in_force: str | None = None,
        reason: str,
        created_at: str,
        nonce: str = "",
        expires_at: str | None = None,
    ) -> "Intent":
        quantity = money(quantity)
        limit = None if limit_price is None else money(limit_price)
        if time_in_force is None:
            time_in_force = default_tif(instrument, order_type)
        material = "|".join(
            [agent, instrument.key, side, format(quantity, "f"), order_type, text(limit) or "", nonce]
        )
        return cls(
            id="in-" + hashlib.sha256(material.encode()).hexdigest()[:32],
            agent=agent,
            instrument=instrument,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit,
            post_only=bool(post_only),
            time_in_force=time_in_force,
            reason=str(reason or "").strip()[:2000] or "no reason given",
            created_at=created_at,
            expires_at=expires_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "instrument": self.instrument.to_dict(),
            "side": self.side,
            "quantity": text(self.quantity),
            "order_type": self.order_type,
            "limit_price": text(self.limit_price),
            "post_only": self.post_only,
            "time_in_force": self.time_in_force,
            "reason": self.reason,
            "created_at": self.created_at,
        }


def default_tif(instrument: Instrument, order_type: str) -> str:
    """Crypto and event orders have no trading day; a fractional equity order, market or limit, must
    be `day` (the venue's rule), and so every equity and option order is one."""
    if instrument.asset_class in ("crypto", "event"):
        return "gtc"
    return "day"


def fractional_tif_reason(instrument: Instrument, quantity: Decimal, time_in_force: str) -> str | None:
    """Why a fractional share order with this time in force cannot be sent: Alpaca takes a
    fractional equity order, market or limit, as a `day` order only. The book, the practice
    simulator and the adapter all refuse it before the venue would."""
    if instrument.asset_class == "equity" and quantity != quantity.to_integral_value() and str(time_in_force) != "day":
        return f"a fractional share order must be a day order, not {time_in_force} (the venue takes no other)"
    return None


@dataclass
class Holding:
    instrument: Instrument
    quantity: Decimal = ZERO
    cost: Decimal = ZERO  # what the units still held cost, fees included
    opened_at: str | None = None
    reason: str = ""

    @property
    def average_cost(self) -> Decimal:
        per = self.quantity * self.instrument.multiplier
        return self.cost / per if per else ZERO


@dataclass
class Account:
    agent: str
    staked: Decimal = ZERO
    cash: Decimal = ZERO
    realized: Decimal = ZERO
    fees: Decimal = ZERO
    swept: bool = False
    holdings: dict[str, Holding] = field(default_factory=dict)
    funded: bool = False  # a positive stake was ever lent; net staked can be negative after profits return


@dataclass
class Share:
    """One intent's part of a venue order."""

    intent_id: str
    agent: str
    quantity: Decimal
    reason: str
    filled: Decimal = ZERO


@dataclass
class Working:
    """A venue order the book sent and is still responsible for."""

    order_id: str
    broker_order_id: str | None
    instrument: Instrument
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None
    post_only: bool
    status: str
    shares: list[Share]
    submitted_at: str
    liquidity: str = "taker"  # decided when routed: a limit order that did not cross is a maker
    rested: bool = False
    filled: Decimal = ZERO
    notional: Decimal = ZERO  # sum of price x quantity attributed so far
    fees_seen: Decimal = ZERO  # venue-reported fees attributed so far
    reference_price: Decimal | None = None  # reserve an unfilled market buy at its ask, not its liquidation bid
    allocation: dict[str, Any] | None = None  # durable targets for an incremental venue fill being attributed
    slice_of: str | None = None  # the exit plan this order is one slice of (`ExitPlan.plan_id`)
    slice_index: int | None = None  # which slice: 0, 1, 2 ... in the order they were sent
    #: The AGENT'S own order terms when the House re-priced this exit (D3: one step above the House's bid, or post-only
    #: at the ask on doubt): such an order never walls the agent's own next exit off (`_withdraw_repriced`) and lives
    #: one pass (`_recheck_repriced`). From the order rows' `house_repriced`, so a restart keeps it (review of #226).
    repriced: dict[str, Any] | None = None

    @property
    def open(self) -> bool:
        # Older releases recorded a terminal submit response before attributing its fills.
        # Recover an interrupted attribution by reading that same venue order again; the
        # terminal label alone must never make an unbooked fill disappear from polling.
        return self.status in OPEN_STATUSES or (self.status == "filled" and self.filled < self.quantity)

    @property
    def remaining(self) -> Decimal:
        return self.quantity - self.filled


@dataclass
class ExitPlan:
    """One sell too large for one order, and what the book still owes it.

    The slices are the book's orders whose `slice_of` is `plan_id`; what is left to send is the
    plan's quantity less what they filled and what is still working. Nothing else is state: a
    restart folds the plan row and the slices' order rows and knows exactly where it stood."""

    plan_id: str
    intent: Intent  # the agent's one intent: its id is on every slice's shares and fills
    quantity: Decimal  # what the plan sells: the intent's quantity, less any part crossed inside the House
    cap_usd: Decimal
    created_at: str
    max_orders: int  # a bound on venue orders, so a market that keeps half-filling cannot loop
    ttl_seconds: int
    #: In memory only: since when the plan's market has been shut (its market slices wait for the
    #: open, `_advance_plan`), and when it last reopened, from which the time-to-live is counted
    #: again. A restart forgets both and counts from `created_at`: a plan held over a close is then
    #: closed at the open as "not finished", and the holder sells the rest with a fresh intent.
    held_since: str | None = None
    resumed_at: str | None = None


@dataclass(frozen=True)
class Limits:
    """What one agent may do on one book. Set by the House from the agent's rung."""

    max_position_usd: Decimal
    max_order_usd: Decimal
    #: Options are not offered yet: the order path is proven (a paper contract was accepted and
    #: cancelled on Sept 19, 2026), but the House has no option quotes or chains to price, size or
    #: mark one with, and the gateway does not serve Alpaca's contract listing.
    asset_classes: tuple[str, ...] = ("equity", "crypto", "event")
    max_orders_per_day: int = 200
    #: The horizon rule: no entry in an event market expected to pay later than this many hours
    #: from now (None: no rule). Fast feedback is what the ladder runs on, and a stake parked in
    #: a contract that pays next year closes no trades. Equities and options are not bounded.
    max_hours_to_resolve: float | None = None


@dataclass(frozen=True)
class Outcome:
    intent_id: str
    agent: str
    status: str  # refused | crossed | sent | filled | partial | resting | rejected | unknown | duplicate
    detail: str = ""
    order_id: str | None = None
    filled: Decimal = ZERO


@dataclass
class Clearing:
    """What `Book._clear_the_way` did about the House's own orders an exit would have met (D3)."""

    crossed: Decimal = ZERO  # sold inside the House to peers' resting bids
    price: Decimal | None = None  # what it was sold at (the bids' prices, weighted)
    left: Decimal = ZERO  # still to sell
    doubt: str | None = None  # why what is left must rest post-only at the ask instead of its own order type
    detail: str = ""


@dataclass(frozen=True)
class Reconciliation:
    ok: bool
    cash_venue: Decimal
    cash_ledger: Decimal
    cash_diff: Decimal
    position_diffs: dict[str, str]
    dust_booked: Decimal
    detail: str = ""
    #: A real book's cents booked as dust (H4): what explained them. Empty otherwise.
    explained: str = ""


#: The first run's firm rules, kept. See `ltcm/config.json` `event_rules`.
DEFAULT_RULES: dict[str, Any] = {
    "max_order_usd": "75",  # the gateway refuses more; the book refuses first and says why
    "min_event_price": "0.15",
    "max_event_market_pct": "0.30",
    "max_event_market_floor_pct": "0.10",
    "max_event_cluster_floor_pct": "0.25",
    "max_position_pct": "0.50",
    "max_gross_pct": "1.0",
    "max_order_notional_pct": "0.50",
    "max_daily_loss_pct": "0.10",
    "max_limit_deviation_pct": "0.10",
    "floor_max_daily_loss_pct": "0.08",
    "max_quote_age_seconds": 900,
    # Alpaca's indicative options feed supplies modified quotes; its trades are delayed.
    # These quotes are not executable NBBO (the live OPRA feed needs its agreement signed).
    # This age limit is an existing guard, not a claim that indicative quotes are executable.
    "max_option_quote_age_seconds": 1500,
    "market_slippage_pct": "0.005",
}


def allocate(total: Decimal, weights: Sequence[Decimal], step: Decimal) -> list[Decimal]:
    """Split `total` across `weights` pro rata on a grid of `step`, by largest remainder.

    Never allocates more than a weight (a share cannot fill beyond what it asked for) and the
    parts always sum to `total` when the weights can hold it. Ties go to the earlier weight.
    """
    total = money(total)
    capacity = sum(weights, ZERO)
    if total <= 0 or capacity <= 0:
        return [ZERO for _ in weights]
    if total >= capacity:
        return [money(w) for w in weights]
    raw = [total * w / capacity for w in weights]
    parts = [(r / step).to_integral_value(rounding=ROUND_DOWN) * step for r in raw]
    left = total - sum(parts, ZERO)
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] - parts[i]), i))
    while left > 0:
        moved = False
        for i in order:
            room = weights[i] - parts[i]
            if room <= 0:
                continue
            add = min(step, left, room)
            parts[i] += add
            left -= add
            moved = True
            if left <= 0:
                break
        if not moved:
            break
    return parts


# --------------------------------------------------------------------------------------- book
class Book:
    """The one path from an agent's intent to a venue, and the only writer of `book.*` rows."""

    def __init__(
        self,
        name: str,
        broker: Broker,
        ledger: Ledger,
        *,
        fees: Fees,
        real_money: bool,
        rules: Mapping[str, Any] | None = None,
        clock=time.time,
        market_open: Any = None,
        resolves_at: Any = None,
        sleep: Any = time.sleep,
        kill_switch: Any = None,
        event_capital_budget: Any = None,
        band_of: Any = None,
        halt_basis_usd: Any = None,
        family_taker: Any = None,
    ):
        self.name = name
        self.broker = broker
        self.ledger = ledger
        self.fees = fees
        self.real_money = bool(real_money)
        self.rules = {**DEFAULT_RULES, **dict(rules or {})}
        self.clock = clock
        self.market_open = market_open  # callable(instrument, iso) -> bool | None
        self.resolves_at = resolves_at  # callable(instrument) -> epoch seconds | None: when an event market is expected to pay
        self.sleep = sleep
        self.kill_switch = kill_switch  # callable() -> bool
        self.event_capital_budget = event_capital_budget  # callable() -> explicit venue dollars, or None
        #: The two facts the constitution's daily-loss keys (`allocator.bunt_daily_loss`,
        #: `allocator.real_halt`; the owner's revision of Sept 23, 2026 ~16:00 UTC) need from the
        #: House, read only on a real-money book: the agent's band under the allocator ("bunt",
        #: "swing", or None when it has none) and this venue's grant capital in dollars (None when no
        #: grant names it). Absent -- every practice book, the tests, the allocator switched off --
        #: the book's own rules stand exactly as before.
        self.band_of = band_of  # callable(agent) -> str | None
        self.halt_basis_usd = halt_basis_usd  # callable() -> Decimal | None
        #: X0 (Sept 24, 2026): the agent's family's pooled TAKER record, from the allocator
        #: (`{"family", "positive", "n", "mean_log", "bound"}` or None), which
        #: `allocator.real_entry_liquidity` reads on a real event book. None, or no callable, is "not
        #: measured", and unmeasured is not proven: a taker entry is refused.
        self.family_taker = family_taker  # callable(agent) -> dict | None
        self.engine = RiskEngine()
        self.limits: dict[str, Limits] = {}
        self.accounts: dict[str, Account] = {}
        self.orders: dict[str, Working] = {}
        self._cross_plans: dict[str, dict[str, Any]] = {}
        self._cross_applied: set[str] = set()
        self._cross_cursor = 0
        self.seen_intents: set[str] = set()
        self.marks: dict[str, Decimal] = {}  # instrument key -> last liquidation mark
        self.day_open: dict[str, tuple[str, Decimal]] = {}  # agent -> (day, equity at its start)
        #: agent -> (day, equity when the opening was taken, the ledger's head then): what is persisted
        #: (`_day_open_path`) so a restart does not forget the day's loss; `day_open` is this plus the
        #: day's stakes since.
        self._day_open_taken: dict[str, tuple[str, Decimal, int]] = {}
        self._day_open_dirty = False
        #: Agents whose opening was restored from the file and whose holdings are not yet marked in this
        #: process (`_day_pnl` quotes them once before comparing; review of #211, Sept 23, 2026).
        self._day_open_unmarked: set[str] = set()
        self.orders_today: dict[tuple[str, str], int] = {}
        # Ledger replay is not a fresh venue check. A restart must not clear a mismatch
        # and permit an entry before the first reconciliation of this process.
        self.frozen: str | None = "awaiting startup reconciliation" if self.real_money else None
        #: What the venue account held that is not the book's: cash and positions from before the
        #: book opened (the paper account's $100,000; the real account's unallocated cash).
        self.baseline_cash: Decimal | None = None
        self.baseline_positions: dict[str, Decimal] = {}
        self.venue_cash: Decimal | None = None
        self.baseline_at: str | None = None
        self._evidence_issues: dict[str, dict[str, Any]] = {}
        self._receipt_checked: set[str] = set()
        self._accounting_corrections: dict[str, list[dict[str, Any]]] = {}
        self._fills_since_reconcile = 0
        self._awaiting_settlement: dict[str, float] = {}
        self._unreconciled = 0  # consecutive readings that did not reconcile (see `_adopt_the_venue`)
        #: How far the venue may fairly differ from the book since the last reconciliation because
        #: a limit order was booked as a taker and may have been a maker: dollars, and units by key.
        self._fee_slack_usd = ZERO
        self._fee_slack_units: dict[str, Decimal] = {}
        #: H4 (Sept 25, 2026): the room for the regulators' fees Alpaca takes at each option or stock
        #: fill and lists only later (`UNLISTED_FEE_PER_FILL_USD`), and the real dust booked on that room
        #: (negative): `(when, dollars, what)`, read over the last `UNLISTED_FEE_HOURS`. Folded from the
        #: fill and dust rows' own times, so a restart neither forgets a fill's room nor spends it twice.
        self._unlisted_fees: list[tuple[float, Decimal, str]] = []
        #: H4's one transition: how far the book's cash may stand from the venue's at its first clean
        #: reading because the last clean reading before it added resting bids back unrounded
        #: (`_bid_rounding`, set by the fold from a `book.reconciled` row without `holds`).
        self._holds_transition = ZERO
        #: Every instrument the book has ever traded, by position key: a crumb the venue still
        #: shows after its holder sold out must still be valued, or it cannot be called dust.
        self._traded: dict[str, Instrument] = {}
        #: Sliced exits still selling (closed plans leave), and each plan's slice orders by id.
        self.exit_plans: dict[str, ExitPlan] = {}
        self._plan_orders: dict[str, list[str]] = {}
        #: Whether this process has read the venue yet. A plan resumed from the ledger sends nothing
        #: until then: the startup poll books what filled during a restart, and only a reading of
        #: the venue says what is really still held.
        self._reconciled_here = False
        #: Orders the venue said it has no record of: when a poll first heard so (`_venue_missed`),
        #: and when the book closed one as never arrived (`_recheck_never_arrived` asks again).
        self._missed: dict[str, str] = {}
        self._never_arrived: dict[str, str] = {}
        #: Why the House cancelled an order whose cancel the venue had not confirmed within the pass (`_clear_the_way`),
        #: for the cancelled row a later poll writes (`_attribute`): the agent reads its orders' latest rows. In memory
        #: only: after a restart that row carries no reason, as before (review of #226, Sept 24, 2026).
        self._cancel_why: dict[str, str] = {}
        self._lock = threading.RLock()
        self._cursor = 0
        self._fold()
        self._restore_day_open()  # after the fold, which adjusts no opening: none exists yet
        self._finish_crosses()

    # ----------------------------------------------------------------- folding
    def _fold(self) -> None:
        """Rebuild state from the ledger. Every mutation below appends first and applies the
        appended row through `_apply`, so the live state and a rebuilt one are the same state.

        `book.reconciled` is folded too (H4, Sept 25, 2026), and only here: a clean reading starts the
        counts "since the last reconciliation" again (`_reset_since_clean`), as it did in the process
        that wrote it. Before, the fold counted every venue fill the book ever had as one since the last
        reconciliation, so the first reading after each restart allowed a cent for each of them: $0.12
        on the real Alpaca book (12 fills), which booked its "cash differs by 0.0108" as dust 1.2 s after
        the restart of 04:11:49Z Sept 25, and its "-0.0324" 1.0 s after the one of 18:45:21Z Sept 24;
        $1.39 on the real Kalshi book (139 fills). What no fill since the last clean reading explains
        stays a freeze across a restart."""
        kinds = ("book.stake", "book.fill", "book.fill_correction", "book.settle", "book.order", "book.baseline", "book.cross_plan",
                 "book.exit_plan", "agent.intent", "book.reconciled")
        for entry in self.ledger.iter(kinds=kinds):
            if entry.payload.get("book") == self.name:
                self._apply(entry.kind, entry.agent, entry.payload, entry.at)
            self._cross_cursor = entry.seq

    def _account(self, agent: str) -> Account:
        account = self.accounts.get(agent)
        if account is None:
            account = self.accounts[agent] = Account(agent)
        return account

    def _apply(self, kind: str, agent: str, p: Mapping[str, Any], at: str) -> None:
        if kind == "agent.intent":
            self.seen_intents.add(str(p["id"]))
            day = str(p.get("created_at") or at)[:10]
            self.orders_today[(agent, day)] = self.orders_today.get((agent, day), 0) + 1
        elif kind == "book.stake":
            account = self._account(agent)
            usd = money(p["usd"])
            account.staked += usd
            account.cash += usd
            if usd > 0:
                account.funded = True
                account.swept = False
            elif usd < 0:
                # Sizing can return only part of a loan, or leave holdings that will later
                # settle. Only an empty account has closed and needs a fresh stake on reentry.
                account.swept = account.cash == 0 and not account.holdings
            opened = self.day_open.get(agent)
            if opened is not None and opened[0] == at[:10]:
                # Capital lent or taken back is not a day's profit or loss: without this, sweeping a
                # promoted agent's paper account read as a 100% loss and tripped the floor breaker
                # for every other agent on the book.
                self.day_open[agent] = (opened[0], opened[1] + usd)
        elif kind == "book.fill":
            if agent == HOUSE:
                self._apply_house(p, at)
            else:
                self._apply_fill(agent, p, at)
            if p.get("cross_plan_id"):
                self._cross_applied.add(f"{p['source']}:{p['intent_id']}")
        elif kind == "book.fill_correction":
            from .accounting import apply_correction
            apply_correction(self._account(agent), p)
            working = self.orders.get(p['order_id'])
            if working is not None:
                working.notional += money(p['notional_delta'])
                working.fees_seen += money(p['venue_fee_delta'])
            self._receipt_checked.add(p['order_id'])
            self._accounting_corrections.setdefault(agent, []).append({
                'at': at, **{key: p[key] for key in ('original_fill_id', 'corrected', 'cash_delta',
                                                   'realized_delta', 'receipt', 'evidence')}})
        elif kind == "book.baseline":
            if self.baseline_at is None:
                self.baseline_at = at  # when this book first looked at its venue: fees from before it are not its own
            self.baseline_cash = money(p["cash"])
            self.baseline_positions = {k: money(v) for k, v in dict(p.get("positions") or {}).items()}
            # A negative baseline can hide an agent holding more units than the venue owns.
            # Aggregate cash/units may still reconcile; the affected agent's history does not.
            # Keep this provenance even if a later baseline is rewritten: that cannot repair
            # the already recorded forward marks or prove ownership of a missing execution.
            for key, quantity in self.baseline_positions.items():
                if quantity >= 0:
                    continue
                for name, account in self.accounts.items():
                    if name == HOUSE:
                        continue
                    if any(position_key(h.instrument) == key and h.quantity > 0 for h in account.holdings.values()):
                        self._evidence_issues.setdefault(name, {})[key] = {
                            'instrument': key, 'baseline_quantity': text(quantity), 'detected_at': at,
                            'reason': 'a negative baseline offsets this agent\'s holding; ownership and forward marks require repair',
                        }
            # A receipt-backed repair (`accounting.repair_paper_phantoms`) clears exactly what it repaired.
            for repair in p.get("repairs") or []:
                issues = self._evidence_issues.get(repair["agent"], {})
                issues.pop(repair["instrument"], None)
                if not issues:
                    self._evidence_issues.pop(repair["agent"], None)
                self._accounting_corrections.setdefault(repair["agent"], []).append(
                    {"at": at, "repaired": repair["instrument"], "receipt": repair.get("broker_order_id"),
                     "evidence": "history before this repair is excluded from scoring"})
        elif kind == "book.settle":
            account = self._account(agent)
            instrument = Instrument.from_dict(p["instrument"])
            holding = account.holdings.get(instrument.key)
            payout = money(p["payout"])
            account.cash += payout
            if holding is not None:
                account.realized += payout - holding.cost
                del account.holdings[instrument.key]
        elif kind == "book.order":
            self._apply_order(p, at)
        elif kind == "book.exit_plan":
            self._apply_exit_plan(p)
        elif kind == "book.reconciled":
            # Read by the fold only: a live reading resets in `_reconcile` and appends its row unapplied.
            # A clean reading reconciled with no settlement awaited (its `detail` then names none).
            if p.get("ok") and "awaiting settlement" not in str(p.get("detail") or ""):
                self._reset_since_clean()
                if p.get("holds") != "cent":
                    # Written before H4: its reading added the bids resting then back unrounded and
                    # booked their sub-cent errors as dust, so the ledger's cash stands that far from
                    # the venue's as the next process reads it (`self.orders` is as of this row here).
                    self._holds_transition = abs(self._bid_rounding())
        elif kind == "book.cross_plan":
            if p.get("complete"):
                plan = self._cross_plans.get(p["plan_id"])
                if plan and all(fill["id"] in self._cross_applied for fill in plan["fills"]):
                    self._cross_plans.pop(p["plan_id"], None)
            else:
                self._cross_plans[p["plan_id"]] = dict(p)

    def _apply_fill(self, agent: str, p: Mapping[str, Any], at: str) -> None:
        account = self._account(agent)
        self._apply_account_fill(account, p, at)
        if money(p["position_delta"]) != 0:
            instrument = Instrument.from_dict(p["instrument"])
            self._traded[position_key(instrument)] = instrument
        order_id = p.get("order_id")
        working = self.orders.get(order_id) if order_id else None
        if working is not None and p.get("source") == "venue":
            self._fills_since_reconcile += 1
            traded = money(p["quantity"])
            if self.fees.family == "alpaca" and working.instrument.asset_class in ("option", "equity"):
                per_unit = UNLISTED_FEE_PER_CONTRACT_USD if working.instrument.asset_class == "option" else UNLISTED_FEE_PER_SHARE_USD
                self._note_unlisted(at, UNLISTED_FEE_PER_FILL_USD + traded * per_unit,
                                    f"{p.get('side')} {format(traded.normalize(), 'f')} {working.instrument.symbol} {working.instrument.asset_class}")
            if working.order_type == "limit" and self.fees.family == "alpaca":
                self._fee_slack_usd += money(p.get("fee_usd") or 0)
                if money(p.get("fee_quantity") or 0) > 0:
                    key = position_key(working.instrument)
                    self._fee_slack_units[key] = self._fee_slack_units.get(key, ZERO) + money(p["fee_quantity"])
            working.filled += traded
            working.notional += traded * money(p["price"])
            working.fees_seen += money(p.get("venue_fee") or 0)
            for share in working.shares:
                if share.intent_id == p.get("intent_id"):
                    share.filled += traded

    @staticmethod
    def _apply_account_fill(account: Account, p: Mapping[str, Any], at: str) -> None:
        """Apply a fill to one account, also used to price a cross against a private copy."""
        cash_delta = money(p["cash_delta"])
        position_delta = money(p["position_delta"])
        account.cash += cash_delta
        account.fees += money(p.get("fee_usd") or 0)
        if position_delta != 0:
            instrument = Instrument.from_dict(p["instrument"])
            holding = account.holdings.get(instrument.key)
            if holding is None:
                holding = account.holdings[instrument.key] = Holding(instrument)
            if position_delta > 0:
                if holding.quantity <= 0:
                    holding.opened_at = at
                    holding.reason = str(p.get("reason") or "")
                holding.quantity += position_delta
                holding.cost += -cash_delta
            else:
                sold = -position_delta
                basis = holding.cost * sold / holding.quantity if holding.quantity > 0 else ZERO
                account.realized += cash_delta - basis
                holding.quantity -= sold
                holding.cost -= basis
            if holding.quantity <= 0:
                del account.holdings[instrument.key]

    def _apply_order(self, p: Mapping[str, Any], at: str = "") -> None:
        order_id = str(p["order_id"])
        if p.get("status") == "rejected" and p.get("reason") == NEVER_ARRIVED:
            self._never_arrived[order_id] = at  # the poll keeps asking the venue about it for a while (`_recheck_never_arrived`)
        else:
            self._never_arrived.pop(order_id, None)
        working = self.orders.get(order_id)
        if working is None:
            working = self.orders[order_id] = Working(
                order_id=order_id,
                broker_order_id=p.get("broker_order_id"),
                instrument=Instrument.from_dict(p["instrument"]),
                side=p["side"],
                quantity=money(p["quantity"]),
                order_type=p["order_type"],
                limit_price=None if p.get("limit_price") is None else money(p["limit_price"]),
                post_only=bool(p.get("post_only")),
                status=p["status"],
                shares=[
                    Share(s["intent_id"], s["agent"], money(s["quantity"]), str(s.get("reason") or ""))
                    for s in p["shares"]
                ],
                submitted_at=p.get("submitted_at") or "",
                liquidity=str(p.get("liquidity") or "taker"),
                reference_price=None if p.get("reference_price") is None else money(p["reference_price"]),
                repriced=dict(p["house_repriced"]) if p.get("house_repriced") else None,
            )
            part = p.get("slice") or {}
            if part.get("plan"):
                working.slice_of, working.slice_index = str(part["plan"]), int(part["index"])
                self._plan_orders.setdefault(working.slice_of, []).append(order_id)
        working.status = p["status"]
        working.rested = bool(p.get("rested", working.rested))
        if "allocation" in p:
            working.allocation = dict(p["allocation"])
        if p.get("broker_order_id"):
            working.broker_order_id = p["broker_order_id"]

    def _apply_exit_plan(self, p: Mapping[str, Any]) -> None:
        plan_id = str(p["plan_id"])
        if p.get("closed"):
            self.exit_plans.pop(plan_id, None)
            return
        if plan_id in self.exit_plans:
            return
        row = p["intent"]
        intent = Intent(
            id=str(row["id"]), agent=str(row["agent"]), instrument=Instrument.from_dict(row["instrument"]), side=str(row["side"]),
            quantity=money(row["quantity"]), order_type=str(row["order_type"]),
            limit_price=None if row.get("limit_price") is None else money(row["limit_price"]), post_only=bool(row.get("post_only")),
            time_in_force=str(row["time_in_force"]), reason=str(row.get("reason") or ""), created_at=str(row["created_at"]),
            expires_at=row.get("expires_at"),
        )
        self.exit_plans[plan_id] = ExitPlan(plan_id, intent, money(p["quantity"]), money(p["cap_usd"]), str(p["created_at"]),
                                            int(p["max_orders"]), int(p["ttl_seconds"]))

    # ------------------------------------------------------------------ stakes
    def stake(self, agent: str, usd: Any, *, note: str = "") -> None:
        """Lend an agent capital on this book (negative takes it back). On a real-money book the
        stakes are slices of the venue's actual cash; on a paper book they are the live account's
        size, not the paper account's $100,000."""
        usd = money(usd)
        with self._lock:
            account = self._account(agent)
            if usd < 0 and account.cash - self._reserved_cash(agent) + usd < 0:
                raise BookError(f"{agent} does not have {-usd} of free cash on {self.name}")
            if usd > 0 and self.real_money:
                # A real stake is a slice of cash the venue actually holds, never a promise.
                if self.venue_cash is None:
                    raise BookError(f"{self.name} has not been reconciled to its venue yet")
                lent = sum((a.staked for name, a in self.accounts.items() if name != HOUSE), ZERO)
                if lent + usd > self.venue_cash:
                    raise BookError(f"{self.name} holds ${self.venue_cash:.2f}; ${lent + usd:.2f} of stakes would exceed it")
            payload = {"book": self.name, "usd": text(usd), "note": note, "real_money": self.real_money}
            entry = self.ledger.append("book.stake", payload, agent=agent)
            self._apply(entry.kind, agent, entry.payload, entry.at)

    # ------------------------------------------------------------------- reads
    def account(self, agent: str) -> Account:
        with self._lock:
            return self._account(agent)

    def evidence_integrity(self, agent: str) -> dict[str, Any]:
        """Attribution is distinct from an aggregate reconciliation, and survives restarts."""
        with self._lock:
            issues = [dict(row) for row in self._evidence_issues.get(agent, {}).values()]
            return {'ok': not issues, 'book': self.name, 'issues': issues,
                    'corrections': self._accounting_corrections.get(agent, [])[-4:],
                    'note': 'An accounting repair must also exclude contaminated evidence; changing a baseline alone is not a repair.'}

    def agents(self) -> list[str]:
        with self._lock:
            return sorted(a for a in self.accounts if a != HOUSE)

    def open_orders(self, agent: str | None = None) -> list[Working]:
        with self._lock:
            return [
                w
                for w in self.orders.values()
                if w.open and (agent is None or any(s.agent == agent for s in w.shares))
            ]

    def _reservations(self, pending: Sequence[tuple[Intent, Quote]] = ()) -> list[tuple[str, Instrument, str, Decimal, Decimal, str]]:
        """Unfilled commitments, including market intents accepted earlier in this batch.

        Queued buys consume cash and exposure immediately; queued sells consume held units.
        Neither a pending sale nor an unfilled buy supplies cash or units for another intent.
        """
        out = []
        for working in self.orders.values():
            if working.open:
                self._reserve(out, working)
        # A BUY closed as never arrived still binds its cash while the book keeps asking the venue
        # about it (`_recheck_never_arrived`): the verdict alone freed the cash, a second buy of the
        # same size passed `check`, and when the venue had the first order after all its revived
        # fill left the agent 96% invested against the 50% cap, on the venue's pooled cash (found
        # in review, Sept 23, 2026). A sell reserves nothing here: the venue refuses a sale of units
        # already offered, and an exit must not wait a quarter of an hour to be tried again.
        if self._never_arrived:
            now = _epoch_seconds(now_iso(self.clock))
            for order_id, since in self._never_arrived.items():
                working = self.orders.get(order_id)
                if (working is not None and working.side == "buy" and since
                        and now - _epoch_seconds(since) <= NEVER_ARRIVED_RECHECK_SECONDS):
                    self._reserve(out, working)
        for intent, quote in pending:
            price = intent.limit_price or quote.reference(intent.side) or ZERO
            out.append((intent.agent, intent.instrument, intent.side, intent.quantity, price, intent.order_type))
        return out

    def _reserve(self, out: list[tuple[str, Instrument, str, Decimal, Decimal, str]], working: Working) -> None:
        """Append what is still unfilled of `working`, share by share, at the price it was committed at."""
        price = working.limit_price or working.reference_price
        if price is None:
            quote = self._quote(working.instrument)  # an order recorded by an older release
            price = (quote.reference(working.side) if quote is not None else None) or self.marks.get(working.instrument.key) or ZERO
        for share in working.shares:
            if share.quantity > share.filled:
                out.append((share.agent, working.instrument, working.side, share.quantity - share.filled, price, working.order_type))

    def _reserved_cash(self, agent: str, pending: Sequence[tuple[Intent, Quote]] = ()) -> Decimal:
        total = ZERO
        for owner, instrument, side, quantity, price, order_type in self._reservations(pending):
            if owner != agent or side != "buy":
                continue
            if price <= 0:
                return max(self._account(agent).cash, ZERO)  # unknown commitment: none of its cash is free to lend or spend
            notional = quantity * price * instrument.multiplier
            fee = self.fees.charge(instrument, "buy", quantity, price)
            slack = notional * money(self.rules["market_slippage_pct"]) if order_type == "market" else ZERO
            total += notional + fee.usd + slack
        return total

    def equity(self, agent: str) -> Decimal:
        """Cash plus holdings at their last liquidation mark (cost when never marked)."""
        with self._lock:
            account = self._account(agent)
            total = account.cash
            for key, holding in account.holdings.items():
                mark = self.marks.get(key)
                if mark is None:
                    total += holding.cost
                else:
                    total += holding.quantity * mark * holding.instrument.multiplier
            return total

    def total_equity(self) -> Decimal:
        with self._lock:
            return sum((self.equity(a) for a in self.accounts), ZERO)

    def event_floor_capital(self) -> Decimal | None:
        """Funded authorization, including unused reserve; never a new trading allocation.

        Only an explicit venue envelope replaces the legacy allocated-equity denominator.
        Stakes are internal loans, not deposits. Include all booked P&L (also swept/dead
        accounts and House fees), so a restart or another agent cannot erase losses. Gains
        and later deposits cannot enlarge the original authorization. Unattributed owner
        positions supply no capital here. Daily-loss denominators are unchanged.
        """
        if not self.real_money or self.event_capital_budget is None:
            return None
        budget = self.event_capital_budget()
        if budget is None:
            return None
        with self._lock:
            if self.baseline_cash is None:
                return ZERO
            pnl = sum((self.equity(a) - row.staked for a, row in self.accounts.items()), ZERO)
            return max(ZERO, min(money(budget) + min(pnl, ZERO), self.baseline_cash + pnl))

    def _event_exposure(self, reservations, *, agent: str | None = None) -> dict[str, Decimal]:
        exposure: dict[str, Decimal] = {}
        for owner, account in self.accounts.items():
            if agent is not None and owner != agent:
                continue
            for holding in account.holdings.values():
                if holding.instrument.asset_class == 'event' and holding.cost > 0:
                    add_event_exposure(exposure, (holding.instrument.market_id or holding.instrument.symbol).upper(), holding.cost)
        for owner, instrument, side, quantity, price, _ in reservations:
            if (agent is None or owner == agent) and side == 'buy' and instrument.asset_class == 'event':
                add_event_exposure(exposure, (instrument.market_id or instrument.symbol).upper(), quantity * price * instrument.multiplier)
        return exposure

    def event_risk(self, agent: str, markets: Iterable[str] = ()) -> dict[str, Any]:
        """The same concentration caps/exposures as check(), visible before a strategy sizes.

        Headroom is principal, not a promise of execution: cash, fees, price changes, other
        rules and concurrently accepted orders are checked again at submission.
        """
        with self._lock:
            authorized = self.event_floor_capital()
            capital = self.total_equity() if authorized is None else authorized
            def cap(rule, basis, enabled=True):
                pct = money(self.rules[rule])
                return max(ZERO, basis * pct) if enabled and pct > 0 else None
            desk = cap('max_event_market_pct', self.equity(agent))
            market_cap = cap('max_event_market_floor_pct', capital, self.real_money)
            cluster_cap = cap('max_event_cluster_floor_pct', capital, self.real_money)
            reservations = self._reservations()
            own, floor = self._event_exposure(reservations, agent=agent), self._event_exposure(reservations)
            unknown = any(side == 'buy' and price <= 0 for _, _, side, _, price, _ in reservations)
            remaining = {}
            for symbol in markets:
                market = str(symbol).upper()
                bounds = [limit - used for limit, used in (
                    (desk, own.get(market, ZERO)), (market_cap, floor.get(market, ZERO)),
                    (cluster_cap, cluster_at_risk(floor, event_cluster(market)))) if limit is not None]
                remaining[str(symbol)] = float(max(ZERO, min(bounds))) if bounds and not unknown else (0.0 if unknown else None)
            return {'basis': 'authorized_venue' if authorized is not None else 'allocated_equity',
                    'capital_usd': float(capital), 'desk_market_cap_usd': None if desk is None else float(desk),
                    'floor_market_cap_usd': None if market_cap is None else float(market_cap),
                    'floor_cluster_cap_usd': None if cluster_cap is None else float(cluster_cap),
                    'remaining_by_market_usd': remaining}

    # -------------------------------------------------------------------- risk
    def _desk_daily_loss(self, agent: str) -> tuple[Decimal, str | None]:
        """(the per-desk daily-loss line `rule_daily_loss` holds this agent to, why it is not the
        book's rule or None). A REAL-money BUNT under the allocator is held to the allocator's stay
        drawdown and hysteresis instead of the book's `max_daily_loss_pct` (constitution
        `allocator.bunt_daily_loss: "stay_drawdown"`, Sept 23, 2026: huang-h51fdd3-2, a $10 Kalshi
        bunt down $1.52 on its first real trade, was frozen for the day at 12:21 UTC before the
        allocator's own lines could act). The rule list in `ltcm/risk.py` is not forked: the line is
        set where it cannot bind (a whole loss, which `rule_daily_loss` never reaches while the desk
        has equity). Swings keep the book's rule, and so does every practice book."""
        pct = money(self.rules["max_daily_loss_pct"])
        if not self.real_money or self.band_of is None:
            return pct, None
        if str((CONSTITUTION.get("allocator") or {}).get("bunt_daily_loss") or "book") != "stay_drawdown":
            return pct, None
        try:
            band = self.band_of(agent)
        except Exception:  # noqa: BLE001 - a band the House cannot read keeps the book's rule
            return pct, None
        if band != "bunt":
            return pct, None
        return ONE, "stay_drawdown"

    def halt_basis(self) -> Decimal | None:
        """The dollars the real book's daily-loss halt is a share of when the constitution puts it on
        the venue's grant capital (`allocator.real_halt` `basis: "venue_grant_capital"`, Sept 23,
        2026: on the staked accounts' sum, one $25 bunt made it a $2.00 halt) and the House can say
        what that capital is. None keeps the book's own basis, the staked accounts' equity at the
        start of the day: every practice book, and a real book with no grant naming its venue."""
        if not self.real_money or self.halt_basis_usd is None:
            return None
        rule = (CONSTITUTION.get("allocator") or {}).get("real_halt") or {}
        if str(rule.get("basis") or "staked") != "venue_grant_capital":
            return None
        try:
            basis = self.halt_basis_usd()
        except Exception:  # noqa: BLE001 - a grant the House cannot read keeps the book's basis
            return None
        if basis is None or money(basis) <= 0:
            return None
        return money(basis)

    def _halt_pct(self, basis: Decimal | None) -> Decimal:
        if basis is None:
            return money(self.rules["floor_max_daily_loss_pct"])
        rule = (CONSTITUTION.get("allocator") or {}).get("real_halt") or {}
        return money(rule.get("pct") or self.rules["floor_max_daily_loss_pct"])

    def risk_lines(self, agent: str) -> dict[str, Any]:
        """The daily-loss lines this book holds `agent` to now, for whatever publishes or reports the
        limits (health, an agent's standing): the per-desk rule, or "stay_drawdown" when the
        allocator's lines govern a real bunt instead, and the halt with its basis; and the real
        book's entry rules in force (`entry_rules`, X0; empty on a practice book)."""
        pct, why = self._desk_daily_loss(agent)
        basis = self.halt_basis()
        return {
            "desk_daily_loss_pct": None if why else float(pct),
            "desk_daily_loss_rule": why or "book",
            "halt_pct": float(self._halt_pct(basis)),
            "halt_basis": "staked_accounts" if basis is None else "venue_grant_capital",
            "halt_basis_usd": None if basis is None else float(basis),
            "entry_rules": self.entry_rules(),
        }

    def entry_rules(self) -> dict[str, Any]:
        """The constitution's entry rules this book enforces (X0, Sept 24, 2026): on a real book only,
        and only the keys the constitution carries. Each binds entries on event contracts."""
        if not self.real_money:
            return {}
        out: dict[str, Any] = {}
        floor = _allocator_rule("longshot_floor_real")
        if floor is not None:
            out["longshot_floor_real"] = float(floor)
        if str((CONSTITUTION.get("allocator") or {}).get("real_entry_liquidity") or "") == MAKER_UNLESS_TAKER_POSITIVE:
            out["real_entry_liquidity"] = MAKER_UNLESS_TAKER_POSITIVE
        share = _allocator_rule("max_event_share")
        if share is not None:
            out["max_event_share"] = float(share)
        return out

    def _family_taker(self, agent: str) -> Mapping[str, Any] | None:
        """The agent's family's pooled taker record from the House, or None when it is not measured,
        not wired, or cannot be read (never a pass: unmeasured is not proven)."""
        if self.family_taker is None:
            return None
        try:
            record = self.family_taker(agent)
        except Exception:  # noqa: BLE001 - a record the House cannot read is an unmeasured one
            return None
        return record if isinstance(record, Mapping) else None

    def _real_entry_reasons(self, intent: Intent, quote: Quote | None, equity: Decimal, account: Account,
                            reservations: Sequence[tuple[str, Instrument, str, Decimal, Decimal, str]]) -> list[str]:
        """X0 (Sept 24, 2026): the real book's entry rules on event contracts, each read through a key
        of the allocator's constitution and absent with it. The longshot floor rides the risk engine's
        own longshot rule (`check`); these are the other two.

        - `real_entry_liquidity` "maker_unless_family_taker_positive": an entry must be a post-only
          limit unless the agent's family has a positive pooled TAKER record (`family_taker`). The taker
          mechanisms were the loss engine of the allocator's nine promotions to real money (15-minute
          crypto momentum at 182 bps, MLB-total takers at a 7% fee; settled -$18.62 on 16).
        - `max_event_share`: the agent's exposure to one event -- its holdings there at cost, its
          working buys on every market of the event, and this order -- at most that share of its
          equity on the book. meriwether-h7d7702 held NO at strikes 6, 7 and 8 of one MLB total, which
          lost together (Sept 23, 2026)."""
        if not self.real_money or intent.side != "buy" or intent.instrument.asset_class != "event":
            return []
        reasons: list[str] = []
        liquidity = str((CONSTITUTION.get("allocator") or {}).get("real_entry_liquidity") or "")
        if liquidity == MAKER_UNLESS_TAKER_POSITIVE and not (intent.order_type == "limit" and intent.post_only):
            record = self._family_taker(intent.agent)
            if not (record is not None and record.get("positive") is True):
                family = str((record or {}).get("family") or "").strip()
                if record is not None and record.get("n") is not None:
                    bound = record.get("bound")
                    measured = f"{int(record['n'])} taker settlements" + ("" if bound is None else f", bound {float(bound):.4g}")
                else:
                    measured = "no pooled taker record is measured for this agent's family"
                reasons.append(
                    f"a real entry on {family or 'this venue'} must be a post-only limit until the family's pooled taker record "
                    f"is positive ({measured}): send a limit with post_only, which rests or is refused "
                    "(constitution allocator.real_entry_liquidity)"
                )
        share = _allocator_rule("max_event_share")
        if share is not None and share > 0:
            event = _event_of(intent.instrument.market_id or intent.instrument.symbol)
            price = intent.limit_price if intent.order_type == "limit" and intent.limit_price else (quote.ask if quote is not None else None)
            if price is not None and price > 0:
                held = sum((h.cost for h in account.holdings.values() if h.instrument.asset_class == "event" and h.cost > 0
                            and _event_of(h.instrument.market_id or h.instrument.symbol) == event), ZERO)
                working = sum((quantity * at * instrument.multiplier for owner, instrument, side, quantity, at, _ in reservations
                               if owner == intent.agent and side == "buy" and instrument.asset_class == "event"
                               and _event_of(instrument.market_id or instrument.symbol) == event), ZERO)
                total = held + working + intent.quantity * price * intent.instrument.multiplier
                if total > share * max(equity, ZERO):
                    reasons.append(
                        f"one event may hold at most {float(share):.0%} of the stake: {event} would hold ${total:.2f} of this "
                        f"account's ${equity:.2f} (holdings at cost, working buys on every market of the event, and this order; "
                        "constitution allocator.max_event_share)"
                    )
        return reasons

    def _manifest(self, agent: str, limits: Limits) -> Any:
        r = self.rules
        return SimpleNamespace(
            id=agent,
            venues=(self.broker.venue,),
            live=self.real_money,
            instruments=SimpleNamespace(
                asset_classes=tuple(limits.asset_classes),
                permits_symbol=lambda symbol: True,
                allow_short=False,
                min_price=ZERO,
                min_adv_usd=ZERO,
            ),
            limits=SimpleNamespace(
                max_position_pct=money(r["max_position_pct"]),
                max_gross_pct=money(r["max_gross_pct"]),
                max_order_notional_pct=money(r["max_order_notional_pct"]),
                max_daily_loss_pct=self._desk_daily_loss(agent)[0],
                max_orders_per_day=int(limits.max_orders_per_day),
                max_limit_deviation_pct=money(r["max_limit_deviation_pct"]),
            ),
        )

    def _order_intent(self, intent: Intent, *, quantity: Decimal | None = None, nonce: str = "") -> OrderIntent:
        # Nobody can short, so every sell reduces a holding: it is an exit, and says so. The risk
        # engine then checks that it reduces without reversing, and the gateway (which lets an
        # exit through its dollar caps) does not count closing a position against the day.
        closing = {"purpose": "exit", "exit_reason": "desk", "exit_of": intent.id} if intent.side == "sell" else {}
        return OrderIntent.new(
            **closing,
            desk_id=f"book-{self.name}"[:60],
            instrument=intent.instrument,
            side=intent.side,
            quantity=intent.quantity if quantity is None else quantity,
            order_type=intent.order_type,
            limit_price=intent.limit_price,
            time_in_force=intent.time_in_force,
            rationale=intent.reason,
            created_at=intent.created_at,
            nonce=nonce or intent.id,
            post_only=intent.post_only,
            expires_at=intent.expires_at,
        )

    def _day_pnl(self, agent: str, now: str, *, save: bool = True) -> Decimal:
        with self._lock:
            day = now[:10]
            if agent in self._day_open_unmarked:
                # A restored opening was taken at liquidation marks, but marks live in memory only and
                # the startup reconcile quotes only a position that differs from the venue: until the
                # first mark pass (up to `mark_every_seconds` after a restart) a holding would be valued
                # at cost against it, so a winner read as the day's loss (a false halt) and a loser's
                # loss, or just the spread, was hidden (review of #211, Sept 23, 2026). Quote each
                # unmarked holding once, as the mark pass would, before comparing.
                self._day_open_unmarked.discard(agent)
                for key, holding in list(self._account(agent).holdings.items()):
                    if key not in self.marks:
                        self._quote(holding.instrument)
            equity = self.equity(agent)
            opened = self.day_open.get(agent)
            if opened is None or opened[0] != day:
                self.day_open[agent] = (day, equity)
                # The ledger's head as the opening is taken: every stake after it adjusts the opening
                # (`_apply`), and a restart replays exactly those (`_restore_day_open`).
                self._day_open_taken[agent] = (day, equity, self.ledger.head()[0])
                self._day_open_dirty = True
                if save:
                    self._save_day_open()
                return ZERO
            return equity - opened[1]

    # ------------------------------------------------------- the day's opening, across a restart
    # Sept 23, 2026 (the #198 review; pre-existing): each account's start-of-day equity lived in memory
    # only, so a House restart mid-day forgot the day's loss, and both the per-desk daily-loss rule and
    # the real book's halt began again from the restart's equity: a real account down 6% of the halt's
    # basis was given the whole 8% again. No ledger row holds the opening (the first check of the day
    # takes it; `book.mark` rows are the mark pass's, at other moments), and a new ledger kind is
    # `league/ledger.py`'s, so the opening is kept in a small JSON per book beside the ledger (the
    # House's root): the equity when it was taken and the ledger's head then. It is written when an
    # opening is taken, never when a stake adjusts one: at construction, after the fold, every
    # `book.stake` row of this book for that agent after that head and on that day is replayed exactly
    # as `_apply` adjusted the opening live, so a crash between a stake and a write can neither lose
    # nor repeat the adjustment. Another day's openings are dropped; an unreadable file is the old
    # behaviour (a fresh opening at the next check), never a crash.
    def _day_open_path(self) -> Path | None:
        path = getattr(self.ledger, "path", None)
        return Path(path).parent / f"day_open.{self.name}.json" if path else None

    def _save_day_open(self) -> None:
        """Write the newest day's openings, when one was taken since the last write."""
        with self._lock:
            if not self._day_open_dirty:
                return
            path = self._day_open_path()
            day = max((taken[0] for taken in self._day_open_taken.values()), default=None)
            if path is None or day is None:
                self._day_open_dirty = False
                return
            self._day_open_taken = {a: taken for a, taken in self._day_open_taken.items() if taken[0] == day}
            rows = {a: {"equity": text(equity), "seq": seq} for a, (_, equity, seq) in sorted(self._day_open_taken.items())}
            tmp = path.with_name(path.name + ".tmp")
            try:
                tmp.write_text(json.dumps({"book": self.name, "day": day, "open": rows}, sort_keys=True))
                os.replace(tmp, path)
            except OSError:
                return  # still dirty: the next opening taken writes again
            self._day_open_dirty = False

    def _restore_day_open(self) -> None:
        """Today's openings from `_day_open_path`, each with the day's stakes since it was taken."""
        path = self._day_open_path()
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            day = str(data["day"])
            taken = {str(a): (money(row["equity"]), int(row["seq"])) for a, row in dict(data["open"]).items()}
        except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
            return
        if data.get("book") != self.name or day != now_iso(self.clock)[:10] or not taken:
            return
        opened = {a: equity for a, (equity, _) in taken.items()}
        for entry in self.ledger.iter(kinds="book.stake", after=min(seq for _, seq in taken.values())):
            if entry.agent in taken and entry.payload.get("book") == self.name and entry.seq > taken[entry.agent][1] \
                    and entry.at[:10] == day:
                opened[entry.agent] += money(entry.payload["usd"])
        for agent, (equity, seq) in taken.items():
            self._day_open_taken[agent] = (day, equity, seq)
            self.day_open[agent] = (day, opened[agent])
            self._day_open_unmarked.add(agent)

    def check(self, intent: Intent, quote: Quote | None, now: str, *, pending: Sequence[tuple[Intent, Quote]] = (),
              clearing: bool = False) -> list[str]:
        """Every reason this intent may not trade. Empty means it may.

        `clearing`: the caller clears the way for a sell itself (`_clear_the_way`), so a sell is not
        refused for crossing the House's own resting order (D3). An entry always is."""
        reasons: list[str] = []
        limits = self.limits.get(intent.agent)
        if limits is None:
            return [f"{intent.agent} has no seat on the {self.name} book"]
        if intent.instrument.venue != self.broker.venue:
            return [f"instrument venue {intent.instrument.venue!r} is not this book's {self.broker.venue!r}"]
        try:
            order_intent = self._order_intent(intent)
        except (ValueError, ArithmeticError) as exc:
            return [f"malformed intent: {exc}"]
        account = self._account(intent.agent)
        reducing = intent.side == "sell"
        if self.frozen and not reducing:
            reasons.append(f"the {self.name} book is frozen until it reconciles: {self.frozen}")
        step = step_of(intent.instrument, intent.order_type)
        if (intent.quantity / step) % 1 != 0:
            reasons.append(f"quantity {intent.quantity} is not a multiple of {step}")
        fractional_tif = fractional_tif_reason(intent.instrument, intent.quantity, intent.time_in_force)
        if fractional_tif:
            reasons.append(fractional_tif)
        positions = {
            key: Position(h.instrument, h.quantity, h.average_cost, self.marks.get(key))
            for key, h in account.holdings.items()
        }
        capabilities = set(self.broker.capabilities()) - {"short"}  # the live account cannot short
        equity = self.equity(intent.agent)
        floor_equity = self.total_equity()
        floor_daily_pnl = sum((self._day_pnl(a, now, save=False) for a in list(self.accounts)), ZERO)
        self._save_day_open()  # one write for every opening just taken, not one an account
        event_floor_capital = self.event_floor_capital()
        halt_basis = self.halt_basis()
        if halt_basis is not None:
            # `rule_floor_loss` divides the day's loss by the floor's equity at the start of the day
            # (floor_equity - floor_daily_pnl): with the venue's grant capital as that start the halt
            # is `real_halt.pct` of the grant. The event concentration caps keep reading the staked
            # accounts' equity where no explicit event capital replaces it.
            if event_floor_capital is None and floor_equity > 0:
                event_floor_capital = floor_equity
            floor_equity = halt_basis + floor_daily_pnl
        reservations = self._reservations(pending)
        if not reducing and any(side == "buy" and price <= 0 for _, _, side, _, price, _ in reservations):
            reasons.append("an outstanding buy cannot be priced; new entries wait until its commitment is known")
        working_sells: dict[str, Decimal] = {}
        working_buys: dict[str, Decimal] = {}
        working_event_buys: dict[str, Decimal] = {}
        floor_event_exposure = self._event_exposure(reservations)
        for owner, instrument, side, quantity, price, _ in reservations:
            key = instrument.key
            value = quantity * price * instrument.multiplier
            if side == "buy" and instrument.asset_class == "event":
                market = (instrument.market_id or instrument.symbol).upper()
                if owner == intent.agent:
                    working_event_buys[market] = working_event_buys.get(market, ZERO) + value
            if owner != intent.agent:
                continue
            if side == "sell":
                working_sells[key] = working_sells.get(key, ZERO) + quantity
            else:
                working_buys[key] = working_buys.get(key, ZERO) + value
        # X0 (Sept 24, 2026): on a real book the longshot floor is the larger of the book's own
        # `min_event_price` (0.15, which practice books keep) and `allocator.longshot_floor_real`:
        # 20-cent ETH strikes lost twice on real money on Sept 23. The risk engine's rule applies it,
        # to entries only, as it always has.
        min_event_price = money(self.rules["min_event_price"])
        real_floor = _allocator_rule("longshot_floor_real") if self.real_money else None
        if real_floor is not None and real_floor > min_event_price:
            min_event_price = real_floor
        else:
            real_floor = None
        ctx = RiskContext(
            manifest=self._manifest(intent.agent, limits),
            desk_equity=equity,
            desk_cash=account.cash - self._reserved_cash(intent.agent, pending),
            positions=positions,
            quote=quote,
            now=now,
            desk_daily_pnl=self._day_pnl(intent.agent, now),
            desk_orders_today=self.orders_today.get((intent.agent, now[:10]), 0),
            floor_equity=floor_equity,
            floor_daily_pnl=floor_daily_pnl,
            floor_max_daily_loss_pct=self._halt_pct(halt_basis),
            kill_switch=bool(self.kill_switch and self.kill_switch()),
            market_open=self.market_open(intent.instrument, now) if self.market_open else None,
            adv_usd=None,
            open_orders=len(self.open_orders(intent.agent)) + sum(1 for queued, _ in pending if queued.agent == intent.agent),
            venue_capabilities=capabilities,
            working_sells=working_sells,
            working_event_buys=working_event_buys,
            min_event_price=min_event_price,
            max_event_market_pct=money(self.rules["max_event_market_pct"]),
            max_event_market_floor_pct=money(self.rules["max_event_market_floor_pct"]),
            max_event_cluster_floor_pct=money(self.rules["max_event_cluster_floor_pct"]),
            floor_event_exposure=floor_event_exposure,
            event_floor_capital=event_floor_capital,
        )
        decision = self.engine.check(order_intent, ctx)
        for reason in decision.reasons:
            if halt_basis is not None and reason.startswith("floor daily loss"):
                reason += f" of the {self.broker.venue} grant capital ${halt_basis:.2f} (constitution allocator.real_halt)"
            if real_floor is not None and reason.startswith("buying a longshot"):
                reason += (f"; on real money the floor is {real_floor} (constitution allocator.longshot_floor_real), where cheap "
                           f"contracts lost twice on Sept 23, 2026; practice books keep {self.rules['min_event_price']}")
            reasons.append(reason)
        # The league's own rules.
        reference = decision.reference_price
        notional = decision.notional
        if notional is None and reference is not None:
            notional = intent.quantity * reference * intent.instrument.multiplier
        if quote is not None and not reducing:
            age = _age_seconds(quote.as_of, now)
            oldest = self.rules["max_option_quote_age_seconds" if intent.instrument.asset_class == "option" else "max_quote_age_seconds"]
            if age is not None and age > int(oldest):
                reasons.append(f"the quote is {int(age)}s old")
        if notional is not None and intent.side == "buy" and reference is not None:
            # No leverage, to the cent: the fee and a market order's slippage must be covered too.
            charge = self.fees.charge(intent.instrument, "buy", intent.quantity, reference)
            slack = notional * money(self.rules["market_slippage_pct"]) if intent.order_type == "market" else ZERO
            need = notional + charge.usd + slack
            if need > ctx.desk_cash:
                reasons.append(f"needs ${need:.2f} with fees; free cash is ${ctx.desk_cash:.2f}")
        if notional is not None and not reducing:
            gateway = self._gateway_entry_price(intent, reference) if self.real_money else None
            if notional > money(self.rules["max_order_usd"]):
                reasons.append(f"order of ${notional:.2f} is over the ${self.rules['max_order_usd']} order cap")
            elif gateway is not None and intent.quantity * gateway * intent.instrument.multiplier > money(self.rules["max_order_usd"]):
                # The gateway would refuse it with a 403. Say so here, and why, before it is sent.
                counted = intent.quantity * gateway * intent.instrument.multiplier
                how = "its limit price" if intent.order_type == "limit" else "the touch plus ten per cent, as a market order may fill through it"
                reasons.append(
                    f"order of ${notional:.2f} counts as ${counted:.2f} at the gateway ({how}), over its ${self.rules['max_order_usd']} order cap"
                )
            if notional > limits.max_order_usd:
                reasons.append(f"order of ${notional:.2f} is over this rung's ${limits.max_order_usd} an order")
            held = account.holdings.get(intent.instrument.key)
            held_value = (held.quantity * reference * intent.instrument.multiplier) if held and reference else ZERO
            position_value = held_value + working_buys.get(intent.instrument.key, ZERO) + notional
            if position_value > limits.max_position_usd:
                reasons.append(
                    f"position of ${position_value:.2f} including working buys would be over this rung's ${limits.max_position_usd}"
                )
            if working_buys and position_value > equity * money(self.rules["max_position_pct"]):
                reasons.append("position including working buys exceeds the desk's position cap")
            if working_buys and gross_exposure(positions) + sum(working_buys.values(), ZERO) + notional > equity * money(self.rules["max_gross_pct"]):
                reasons.append("gross exposure including working buys exceeds the desk's gross cap")
        if intent.side == "buy" and intent.instrument.asset_class == "event":
            other = "no" if (intent.instrument.right or "yes") == "yes" else "yes"
            market = market_key(intent.instrument)
            held = any(
                market_key(h.instrument) == market and (h.instrument.right or "yes") == other
                for a in self.accounts.values() for h in a.holdings.values()
            )
            bidding = any(
                side == "buy" and market_key(instrument) == market and (instrument.right or "yes") == other
                for _, instrument, side, _, _, _ in reservations
            )
            if held or bidding:
                reasons.append(f"the House already holds or bids the {other} leg of this market; one account cannot hold both")
        if intent.instrument.asset_class == "option":
            if intent.order_type != "limit" or intent.limit_price is None:
                reasons.append("an option order must be a limit order")
            if intent.side == "buy" and str(intent.instrument.expiry or "") <= _new_york_date(now):
                reasons.append("an option entry must expire after today: what expires today is a coin held to the bell")
        if intent.side == "buy" and intent.instrument.asset_class == "event" and limits.max_hours_to_resolve is not None:
            try:
                due = self.resolves_at(intent.instrument) if self.resolves_at else None
            except Exception:  # noqa: BLE001 - not knowing is a refusal, never a pass
                due = None
            hours = None if due is None else (float(due) - _epoch_seconds(now)) / 3600.0
            if hours is None:
                reasons.append("the House cannot tell when this market resolves, so it cannot be entered")
            elif hours > limits.max_hours_to_resolve:
                reasons.append(f"this market is expected to resolve in {hours:.0f} hours; entries must resolve within {limits.max_hours_to_resolve:g}")
        reasons.extend(self._real_entry_reasons(intent, quote, equity, account, reservations))
        crossing = self._would_cross_own(intent, quote)
        if crossing and not (clearing and reducing):
            reasons.append(crossing)
        if intent.order_type != "market":
            # These market orders will be routed after the limits. A limit placed now must not
            # be left for a queued opposite market order to hit at the venue.
            side, _ = yes_space(intent.instrument, intent.side, intent.limit_price)
            if any(market_key(queued.instrument) == market_key(intent.instrument)
                   and yes_space(queued.instrument, queued.side, queued.limit_price)[0] != side
                   for queued, _ in pending):
                reasons.append("this order could trade against the House's queued market order")
        return reasons

    def _would_cross_own(self, intent: Intent, quote: Quote | None) -> str | None:
        """An order that could execute against one of the House's own resting orders is refused."""
        side, price = yes_space(intent.instrument, intent.side, intent.limit_price)
        key = market_key(intent.instrument)
        for working in self.orders.values():
            if not working.open or market_key(working.instrument) != key:
                continue
            other_side, other_price = yes_space(working.instrument, working.side, working.limit_price)
            if other_side == side:
                continue
            if price is None or other_price is None:
                return "a market order here could trade against the House's own resting order"
            if (side == "buy" and price >= other_price) or (side == "sell" and price <= other_price):
                return "this price would trade against the House's own resting order; re-price or wait"
        return None

    # ------------------------------------------------------------ exits (D3)
    def _crossing_orders(self, intent: Intent) -> list[Working]:
        """The House's open orders this intent could execute against (`_would_cross_own`'s test, in YES
        space for Kalshi legs), best price for the intent first -- a sell meets the highest bid first,
        as at the venue -- then the earliest, then by id; an unpriced order (a market order in flight)
        last."""
        side, price = yes_space(intent.instrument, intent.side, intent.limit_price)
        key = market_key(intent.instrument)
        found: list[tuple[tuple[Any, ...], Working]] = []
        for working in self.orders.values():
            if not working.open or market_key(working.instrument) != key:
                continue
            other_side, other_price = yes_space(working.instrument, working.side, working.limit_price)
            if other_side == side:
                continue
            if price is None or other_price is None or (side == "buy" and price >= other_price) or (side == "sell" and price <= other_price):
                rank = (1, ZERO) if other_price is None else (0, -other_price if side == "sell" else other_price)
                found.append(((*rank, working.submitted_at, working.order_id), working))
        return [working for _, working in sorted(found, key=lambda pair: pair[0])]

    @staticmethod
    def _doubt_about(working: Working) -> str | None:
        """Why the House cannot say where one of its own crossing orders stands (None: it can). A market
        order in flight, or an order the venue has not acknowledged, may trade at any moment: doubt,
        and doubt neither crosses nor takes liquidity (`_clear_the_way`, step 3)."""
        if working.order_type != "limit" or working.limit_price is None or working.limit_price <= 0:
            return f"the House's order {working.order_id} that could meet it is a market order still in flight"
        if working.status not in ("accepted", "partially_filled") or not working.broker_order_id:
            return f"the venue has not acknowledged the House's order {working.order_id} that could meet it"
        return None

    def _crossable(self, working: Working, intent: Intent, *, cross: bool, touch: Decimal | None, now: str) -> bool:
        """Whether this resting order of another agent's may be cancelled and crossed with the exit
        inside the House: one agent's bid on the same leg, on a book in good standing, AT OR ABOVE the
        venue's bid for the leg -- where a sell at the venue would really have met it. A bid under the
        touch is not what the venue would have filled the exit against: crossed at its limit, the
        bidder would buy at a price the market never reached (its record flattered by the gap) and
        the exiter would sell under the bid it could have had (Sept 24, 2026: the alpaca-crypto-alts
        bids rested 1.3-3% under their 32-bar means). Such an exit goes to the venue instead, one step
        above the House's bid (`_floored_exit`). A slice (`cross=False`) is never crossed, and neither
        is a post-only exit, which asked never to take: it rests one step above the House's bid.
        Nor is anything crossed while the venue itself is shut (a stock or an option outside the
        regular session, where only a LIMIT exit passes `check`): the venue could fill neither order
        until the open, so a cross then would book both agents a fill no venue could have made, on a
        quote from the close (review of #226, Sept 24, 2026). The exit goes to the venue one step
        above the House's bid, to wait for the open like any order."""
        if not cross or intent.post_only or self.frozen or touch is None:
            return False
        try:
            if self.market_open is not None and self.market_open(working.instrument, now) is False:
                return False
        except Exception:  # noqa: BLE001 - a session that cannot be read is shut, for this purpose
            return False
        try:
            if self.kill_switch and self.kill_switch():
                return False
        except Exception:  # noqa: BLE001 - a switch that cannot be read is on, for this purpose
            return False
        if len(working.shares) != 1 or working.side != "buy" or position_key(working.instrument) != position_key(intent.instrument):
            return False
        return working.limit_price is not None and working.limit_price >= touch

    def _clear_the_way(self, intent: Intent, quote: Quote | None, now: str, *, cross: bool = True) -> Clearing | None:
        """D3 (Sept 24, 2026): a sell that would cross the House's own resting order is never refused
        for it. None when nothing of the House's stands in its way (the normal path, unchanged).

        1. The seller's OWN crossing orders are cancelled first, through `cancel`.
        2. A PEER's resting bid at or above the venue's bid (`_crossable`), best price first, is read
           at the venue (a fill since the last poll is booked, and an order already gone is passed
           over), cancelled, and crossed with the exit inside the House at the bid's price
           (`_cross_resting`) only once the venue has confirmed the cancel and what had filled
           (`cancel` books the venue's answer to a read AFTER the cancel). What the exit still needs
           meets the next such bid; what is left of a bid is not re-placed. The first bid that may not
           be crossed stops the crossing, and what is left goes to the venue one step above the House's
           best bid (`_exit_past_the_house`).
        3. Doubt about a crossing order -- a cancel not confirmed, an order the venue has not
           acknowledged, a market order in flight, a venue that cannot be read -- stops the crossing,
           and what is left of the exit rests post-only at the ask (`_post_only_exit`).
        A fill in flight is never booked twice: every venue fill goes through `_attribute`, which books
        only the venue's cumulative count above what is booked, and a cross takes only what the venue
        says was left unfilled of an order it says is cancelled."""
        if intent.side != "sell" or not self._crossing_orders(intent):
            return None
        touch = self._fresh_bid(intent.instrument, quote, now)
        doubt: str | None = None
        withdrawn: list[str] = []
        for working in [w for w in self._crossing_orders(intent) if any(s.agent == intent.agent for s in w.shares)]:
            if working.status not in ("accepted", "partially_filled") or not all(s.agent == intent.agent for s in working.shares):
                doubt = doubt or f"your own order {working.order_id} could meet it and the venue has not confirmed where it stands"
                continue
            self.cancel(intent.agent, working.order_id, why=OWN_CROSS_WHY)
            self._await_cancel(working, now, why=OWN_CROSS_WHY)
            if working.open:
                self._cancel_why[working.order_id] = OWN_CROSS_WHY
                doubt = doubt or f"the venue has not confirmed the cancel of your own order {working.order_id}"
            elif working.status == "cancelled":
                withdrawn.append(working.order_id)  # one that filled first is booked, and is no longer in the way
        left = intent.quantity
        parts: list[tuple[Working, Share, Decimal]] = []
        for _ in range(len(self.orders) + 1):
            peers = [w for w in self._crossing_orders(intent) if not any(s.agent == intent.agent for s in w.shares)]
            if left <= 0 or not peers:
                break
            working = peers[0]
            doubt = doubt or self._doubt_about(working)
            if not doubt and touch is None and cross and not intent.post_only and not self.frozen:
                # A cross pays the seller the market's bid (`_cross_resting`); with no fresh one there is no price to
                # pay it, and no way to tell a bid at the market from one under it (review of #226).
                doubt = "no fresh market bid to price a cross inside the House at"
            if doubt or not self._crossable(working, intent, cross=cross, touch=touch, now=now):
                break
            reference = working.broker_order_id or working.order_id
            try:
                self._attribute(working, self.broker.get_order(reference), now)  # a fill since the last poll is booked first
            except BrokerError as exc:
                doubt = f"the venue could not be read about the House's order {working.order_id} ({str(exc)[:120]})"
                break
            if not working.open:
                continue  # filled or closed at the venue: it no longer rests
            share = working.shares[0]
            need = min(left, share.quantity - share.filled) * working.limit_price * working.instrument.multiplier
            if self._account(share.agent).cash < need:
                doubt = f"the bidder of the House's order {working.order_id} cannot pay for it"  # never: its bid reserved the cash
                break
            self.cancel(share.agent, working.order_id, why=PEER_CROSS_WHY)
            self._await_cancel(working, now, why=PEER_CROSS_WHY)
            if working.open:
                self._cancel_why[working.order_id] = PEER_UNCROSSED_WHY
                doubt = f"the venue has not confirmed the cancel of the House's resting bid {working.order_id}"
                break
            if working.status != "cancelled":
                continue  # it filled or expired at the venue first: nothing of it is left to cross
            quantity = min(left, share.quantity - share.filled)
            if quantity > 0:
                parts.append((working, share, quantity))
                left -= quantity
        cleared = Clearing(left=left, doubt=doubt)
        notes = [f"your own resting order{'s' if len(withdrawn) > 1 else ''} {', '.join(withdrawn)} cancelled first"] if withdrawn else []
        if parts:
            cleared.crossed, cleared.price = self._cross_resting(intent, parts, now, touch=touch)
            notes.append(
                f"{text(cleared.crossed)} sold inside the House at {text(cleared.price)} to the House's own resting "
                f"bid{'s' if len(parts) > 1 else ''} ({', '.join(f'{s.agent} {w.order_id}' for w, s, _ in parts)}), "
                "each cancelled at the venue first: no venue order"
            )
        cleared.detail = "; ".join(notes)
        return cleared

    def _fresh_bid(self, instrument: Instrument, quote: Quote | None, now: str) -> Decimal | None:
        """The market's bid to price a cross at, or None when the quote has none, or is older than the book lets a
        quote be for an entry (`max_quote_age_seconds`; options `max_option_quote_age_seconds`), or cannot say how
        old it is: then there is no fresh touch and nothing is crossed (the doubt path, `_clear_the_way`)."""
        if quote is None or quote.bid is None or quote.bid <= 0:
            return None
        age = _age_seconds(quote.as_of, now)
        oldest = self.rules["max_option_quote_age_seconds" if instrument.asset_class == "option" else "max_quote_age_seconds"]
        if age is None or age > int(oldest):
            return None
        return quote.bid

    def _await_cancel(self, working: Working, now: str, *, why: str = "") -> None:
        """Read an order whose cancel the venue has not confirmed yet again, a moment apart and a
        bounded number of times (`CANCEL_CONFIRM_READS`), booking each answer through `_attribute`, so
        a cancel still passing through Alpaca's `pending_cancel` is not taken for one the venue refused.
        A read that fails ends the wait: the order stays open to the book, and the poll asks again."""
        reference = working.broker_order_id or working.order_id
        for _ in range(CANCEL_CONFIRM_READS):
            if not working.open:
                return
            self.sleep(CANCEL_CONFIRM_WAIT_SECONDS)
            try:
                order = self.broker.get_order(reference)
            except BrokerError:
                return
            self._attribute(working, order, now, reason=why if order.status == "cancelled" else "")

    def _cross_resting(self, intent: Intent, parts: Sequence[tuple[Working, Share, Decimal]], now: str, *,
                       touch: Decimal) -> tuple[Decimal, Decimal]:
        """Cross an exit with peers' resting bids the venue has confirmed cancelled: one `book.cross_plan`
        committed as one ledger transaction (`_commit_cross`), so a restart, or the next submit or poll,
        finishes it from the ledger alone and an older release sees all of it or none.

        Each bidder buys at its own limit as a maker. The seller sells the sum as a taker
        (`cross:<exit intent>`) at what the venue would have paid it alone: the market's bid `touch`,
        never under the seller's own limit and never over a crossed bid's price. The House row keeps the
        gap to the bids' prices, as `_net` keeps the spread (the module's rule: a crossed agent is filled
        exactly as the venue would have filled it alone). Before the review of #226 (Sept 24, 2026) the
        seller was paid the bids' own prices, so a bid resting inside the spread -- which the House's own
        post-only re-pricing puts one tick under the ask -- paid a practice seller up to the spread more
        than its venue would have (0.42 for a market NO sell on a 0.40 bid). Fees are what the venue
        would have charged each side, and a House row mirrors every fill exactly, so the accounts still
        sum to the venue's, which saw nothing. Fill ids keep the fold's rule (`<source>:<intent id>`): the exit intent is crossed here
        at most once and never also netted (`submit`), and a bid is cancelled so it is crossed once."""
        plan_id = f"cross-plan:{self.name}:" + hashlib.sha256(f"resting|{intent.id}".encode()).hexdigest()[:32]
        sold = sum((quantity for _, _, quantity in parts), ZERO)
        price = touch
        own = intent.limit_price if intent.order_type == "limit" else None
        if own is not None and own > price:
            price = own  # never under the seller's own limit (every crossed bid is at or above it)
        price = min([price] + [working.limit_price for working, _, _ in parts])  # never over a crossed bid's price
        orders = [working.order_id for working, _, _ in parts]
        accounts = {intent.agent: copy.deepcopy(self._account(intent.agent))}
        for _, share, _ in parts:
            accounts.setdefault(share.agent, copy.deepcopy(self._account(share.agent)))
        fills: list[dict[str, Any]] = []

        def add(agent: str, intent_id: str, payload: dict[str, Any]) -> None:
            payload["cross_plan_id"] = plan_id
            fills.append({"id": f"cross:{intent_id}", "agent": agent, "payload": payload})
            self._apply_account_fill(accounts[agent], payload, now)
            fills.append({"id": f"cross-house:{intent_id}", "agent": HOUSE, "payload": {
                "book": self.name, "source": "cross-house", "cross_plan_id": plan_id, "intent_id": intent_id,
                "instrument": payload["instrument"], "side": "buy" if payload["side"] == "sell" else "sell",
                "quantity": payload["quantity"], "price": payload["price"], "fee_usd": "0",
                "cash_delta": text(-money(payload["cash_delta"])), "position_delta": text(-money(payload["position_delta"])),
                "real_money": self.real_money,
            }})

        charge = self.fees.charge(intent.instrument, "sell", sold, price, liquidity="taker")
        payload = self._fill_payload(intent.agent, intent, quantity=sold, price=price, charge=charge, source="cross", order_id=None,
                                     account=accounts[intent.agent])
        payload.update(resting_orders=orders, note=(
            f"crossed inside the House at {text(price)}, what the venue would have paid this sell alone (the market's bid, "
            "never under your own limit): it would have met the House's own resting bid, which was cancelled at the venue "
            "first and filled at its own limit; the House keeps any gap between the two; no venue order"))
        add(intent.agent, intent.id, payload)
        for working, share, quantity in parts:
            charge = self.fees.charge(working.instrument, "buy", quantity, working.limit_price, liquidity="maker")
            payload = self._fill_payload(share.agent, None, quantity=quantity, price=working.limit_price, charge=charge, source="cross",
                                         order_id=None, instrument=working.instrument, side="buy", reason=share.reason,
                                         intent_id=share.intent_id, liquidity="maker", account=accounts[share.agent])
            payload.update(resting_order=working.order_id, note=(
                f"crossed inside the House: another agent's exit met your resting bid {working.order_id}, which was cancelled at the "
                f"venue first; you bought {text(quantity)} at your limit as a maker; the rest of that bid is not re-placed: bid again "
                "at your next wake if you still want it"))
            add(share.agent, share.intent_id, payload)
        self._commit_cross({"book": self.name, "plan_id": plan_id, "at": now, "fills": fills,
                            "resting": {"exit_intent_id": intent.id, "orders": orders}})
        return sold, price

    def _price_step(self, instrument: Instrument, price: Decimal) -> Decimal:
        """One step of the venue's price grid at `price` (`venues.price_increment`: a Kalshi market's
        cent, a stock's cent, a coin's stated increment), or -- where the venue has stated none -- one
        unit in the last place of `price` itself: a House order the venue accepted at that price is on
        a grid at least that fine."""
        from .venues import price_increment

        asset = None
        lookup = getattr(self.broker, "asset", None)
        if instrument.asset_class == "crypto" and callable(lookup):
            try:
                asset = lookup(instrument.market_id or instrument.symbol)
            except Exception:  # noqa: BLE001 - an unread record is an unknown increment
                asset = None
        step = price_increment(instrument, price, asset=asset if isinstance(asset, Mapping) else None)
        return step if step is not None and step > 0 else ONE.scaleb(price.as_tuple().exponent)

    def _beyond(self, intent: Intent, bound: Decimal) -> Decimal | None:
        """A price for this sell one step past the House's own best opposite order `bound` (YES space),
        back in the leg's own dollars; None when that leaves the instrument's range."""
        side, _ = yes_space(intent.instrument, intent.side, None)
        step = self._price_step(intent.instrument, bound)
        price = yes_space(intent.instrument, side, bound + step if side == "sell" else bound - step)[1]
        if price is None or price <= 0 or (intent.instrument.asset_class == "event" and price >= ONE):
            return None
        return price

    def _floored_exit(self, rest: Intent, best: Working) -> tuple[Intent | None, str]:
        """What is left of an exit sent to the venue as a limit one step past the House's own best
        crossing bid `best`: marketable against every better bid of the market's, never able to trade at
        or through the House's own. What a sell at the market would have done there, less the one fill
        it must not have."""
        bound = yes_space(best.instrument, best.side, best.limit_price)[1]
        price = self._beyond(rest, bound)
        if price is None:
            return None, f"no price lies between the House's own resting bid at {text(best.limit_price)} and the end of the market"
        if rest.limit_price is not None:
            price = max(price, rest.limit_price)  # never more aggressive than the agent asked
        if rest.post_only:
            note = (f"the House rested this post-only exit at {text(price)}, one step above the House's own resting bid at "
                    f"{text(best.limit_price)}: at your price it would have met the House's own bid")
        else:
            note = (f"the House sent this exit as a limit at {text(price)}, one step above the House's own resting bid at "
                    f"{text(best.limit_price)}: it takes the market's better bids and never trades against the House's own")
        return dataclasses.replace(rest, order_type="limit", limit_price=price), note

    def _post_only_exit(self, rest: Intent, quote: Quote | None, doubt: str) -> tuple[Intent | None, str]:
        """What is left of an exit that could not be cleared, re-priced as a post-only limit at the ask
        (D3, step 3), and the note that tells the agent why -- or None and the reason when no price
        exists. Never at or through the House's own best opposite order, read in YES space for a Kalshi
        leg: a consistent venue quote never asks at or under a bid still resting, so this binds only on
        a stale quote, where the exit rests one price step past the House's bid instead. And never
        under the agent's own limit: a take-profit limit ABOVE the ask that met one of the House's orders
        in flight (a market order is in the way of every sell) rests at its own price, not at the ask
        (review of #226, Sept 24, 2026: it was re-priced down to the ask, selling under what it asked)."""
        ask = quote.ask if quote is not None else None
        if ask is None or ask <= 0:
            # Neither refusal says "the House's own resting order": that phrase is the old self-cross refusal of a
            # sell, which docs/operations.md names a D3 defect (review of #226). These are the edges where no price
            # exists at all.
            return None, (f"no ask to rest this exit at while the House cannot say where one of its own orders in the way "
                          f"stands ({doubt}); ask again at your next wake")
        price: Decimal | None = ask
        side, at = yes_space(rest.instrument, "sell", ask)
        opposite = [yes_space(w.instrument, w.side, w.limit_price)[1] for w in self.orders.values()
                    if w.open and w.limit_price is not None and market_key(w.instrument) == market_key(rest.instrument)
                    and yes_space(w.instrument, w.side, w.limit_price)[0] != side]
        if opposite:
            bound = max(opposite) if side == "sell" else min(opposite)
            if (side == "sell" and at <= bound) or (side == "buy" and at >= bound):
                price = self._beyond(rest, bound)
        if price is None:
            return None, f"no price is left above the House's own best bid to rest this exit at ({doubt}); ask again at your next wake"
        where = "the ask"
        if rest.limit_price is not None and rest.limit_price > price:
            # A sell in its own leg's dollars: a higher price is the less aggressive one, on either Kalshi leg.
            price, where = rest.limit_price, "your own limit"
        note = (f"the House re-priced this exit as a post-only limit at {where} {text(price)}: at the market it could meet the "
                f"House's own resting order, which could not be crossed inside the House ({doubt})")
        return dataclasses.replace(rest, order_type="limit", limit_price=price, post_only=True), note

    def _exit_past_the_house(self, rest: Intent, quote: Quote | None, doubt: str | None) -> tuple[Intent | None, str]:
        """How what is left of an exit goes to the venue without meeting the House's own orders, and the
        note that says what changed: as asked when nothing of the House's is in its way; one step past
        the House's best bid when its orders there are known (`_floored_exit`); post-only at the ask on
        any doubt (`_post_only_exit`). None, with the reason, when no price exists."""
        if doubt is None:
            crossing = self._crossing_orders(rest)
            if not crossing:
                return rest, ""
            doubt = next((reason for reason in map(self._doubt_about, crossing) if reason), None)
            if doubt is None:
                floored, note = self._floored_exit(rest, crossing[0])
                if floored is not None:
                    return floored, note
                doubt = note
        return self._post_only_exit(rest, quote, doubt)

    def _finish_clearing(self, intent: Intent, cleared: Clearing, quote: Quote | None, now: str) -> Outcome:
        """Send what is left of a cleared exit, after the batch's market orders (`submit`): alone, never
        netted, and past the House's own orders as they stand now (`_exit_past_the_house`); one outcome
        for the whole intent."""
        if cleared.left <= 0:
            return Outcome(intent.id, intent.agent, "crossed", cleared.detail, None, cleared.crossed)
        asked = dataclasses.replace(intent, quantity=cleared.left)
        rest, note = self._exit_past_the_house(asked, quote, cleared.doubt)
        if rest is None:
            refused = self._refuse(intent, [note])
            return Outcome(intent.id, intent.agent, "partial" if cleared.crossed > 0 else "refused",
                           "; ".join(part for part in (cleared.detail, refused.detail) if part), None, cleared.crossed)
        market = rest.order_type == "market"
        if self._over_cap(rest, cleared.left, quote):
            # Over the cap it is an exit plan, and the plan keeps the AGENT'S intent: each slice is cleared of the
            # House's orders as they stand when it goes (`_advance_plan`), so once the House's bid is gone the rest
            # of a market exit is a market order again. Started with `rest`, every later slice kept the first
            # slice's floor and flags, the market fell under it, and the stop rested for the plan's hour (review
            # of #226, Sept 24, 2026).
            sent = self._start_exit_plan(asked, cleared.left, now, quote)
        else:
            sent = self._route([rest], [cleared.left], now, reference_price=quote.bid if (market and quote is not None) else None, note=note,
                               repriced=self._terms(asked) if note else None)
        filled = cleared.crossed + sent.filled
        if cleared.crossed <= 0:
            status = sent.status
        else:
            status = "filled" if filled >= intent.quantity else "partial"
        detail = "; ".join(part for part in (cleared.detail, note, sent.detail) if part)
        return Outcome(intent.id, intent.agent, status, detail, sent.order_id, filled)

    # ------------------------------------------------------------------ submit
    def submit(self, intents: Iterable[Intent]) -> list[Outcome]:
        """Take one batch of intents: record, check, net the market orders, route, attribute."""
        outcomes: list[Outcome] = []
        with self._lock:
            self._finish_crosses()
            now = now_iso(self.clock)
            market_groups: dict[str, list[tuple[Intent, Quote]]] = {}
            pending: list[tuple[Intent, Quote]] = []
            #: Exits cleared of the House's own orders (`_clear_the_way`) that still have something to sell:
            #: sent after the batch's market orders, each alone. A crossed exit is never also netted: both
            #: would book `cross:<intent id>`.
            cleared: list[tuple[Intent, Clearing, Quote | None]] = []
            for intent in intents:
                if intent.id in self.seen_intents:
                    outcomes.append(Outcome(intent.id, intent.agent, "duplicate", "already recorded"))
                    continue
                entry = self.ledger.append(
                    "agent.intent", {"book": self.name, **intent.to_dict()}, agent=intent.agent, id=f"intent:{intent.id}"
                )
                self._apply(entry.kind, intent.agent, entry.payload, entry.at)
                quote = self._quote(intent.instrument)
                if intent.side == "sell":
                    # The agent's own sell replaces any exit of its there that the House re-priced, which would
                    # otherwise hold the units and wall this sell off (review of #226): withdrawn before `check`.
                    self._withdraw_repriced(intent, now)
                reasons = self.check(intent, quote, now, pending=pending, clearing=True)
                if reasons:
                    outcomes.append(self._refuse(intent, reasons))
                    continue
                if intent.order_type == "market" and (quote is None or quote.bid is None or quote.ask is None or quote.bid <= 0):
                    outcomes.append(self._refuse(intent, ["no two-sided quote to price a market order against"]))
                    continue
                if intent.side == "sell":
                    self._supersede(intent)
                    clearing = self._clear_the_way(intent, quote, now)
                    if clearing is not None and (clearing.crossed > 0 or clearing.doubt is not None or self._crossing_orders(intent)):
                        if clearing.left <= 0:
                            outcomes.append(self._finish_clearing(intent, clearing, quote, now))
                        else:
                            # What is left holds its units for the rest of the batch, as a queued sell does.
                            pending.append((dataclasses.replace(intent, quantity=clearing.left), quote))
                            cleared.append((intent, clearing, quote))
                        continue
                if intent.order_type == "market":
                    market_groups.setdefault(intent.instrument.key, []).append((intent, quote))
                    pending.append((intent, quote))
                else:
                    outcomes.append(self._send(intent, intent.quantity, now, quote))
            for group in market_groups.values():
                outcomes.extend(self._net(group, now))
            for intent, clearing, quote in cleared:
                outcomes.append(self._finish_clearing(intent, clearing, quote, now))
        return outcomes

    def _refuse(self, intent: Intent, reasons: Sequence[str]) -> Outcome:
        self.ledger.append(
            "book.refused",
            {"book": self.name, "intent_id": intent.id, "reasons": list(reasons), "instrument": intent.instrument.to_dict()},
            agent=intent.agent,
            id=f"refused:{intent.id}",
        )
        return Outcome(intent.id, intent.agent, "refused", "; ".join(reasons))

    def _quote(self, instrument: Instrument) -> Quote | None:
        try:
            quote = self.broker.quote(instrument)
        except Exception:  # noqa: BLE001 - a venue that cannot quote is a refusal, not a crash
            return None
        if quote is not None and quote.bid is not None and quote.bid > 0:
            self.marks[instrument.key] = quote.bid
        return quote

    def _net(self, group: list[tuple[Intent, Quote]], now: str) -> list[Outcome]:
        """Cross the opposite market orders of one instrument; send only the difference."""
        outcomes: list[Outcome] = []
        quote = group[-1][1]
        buys = [i for i, _ in group if i.side == "buy"]
        sells = [i for i, _ in group if i.side == "sell"]
        instrument = group[0][0].instrument
        step = step_of(instrument, "market")
        crossed = min(sum((i.quantity for i in buys), ZERO), sum((i.quantity for i in sells), ZERO))
        buy_cross = allocate(crossed, [i.quantity for i in buys], step)
        sell_cross = allocate(crossed, [i.quantity for i in sells], step)
        residual: dict[str, Decimal] = {}
        cross_parts: list[tuple[Intent, Decimal]] = []
        for intents, parts in ((buys, buy_cross), (sells, sell_cross)):
            for intent, part in zip(intents, parts):
                if part > 0:
                    cross_parts.append((intent, part))
                residual[intent.id] = intent.quantity - part
        if cross_parts:
            self._plan_cross(cross_parts, quote, now)
        cap = money(self.rules["max_order_usd"])
        touch = {"buy": quote.ask, "sell": quote.bid}
        for intents in (buys, sells):
            rest = [i for i in intents if residual[i.id] > 0]
            # Both sides are counted as the gateway would count them (`_cap_price`: for Alpaca the
            # touch plus ten per cent), so a pool of entries or of exits is never one order over the
            # cap on the gateway's own pricing, though each of its parts is under it.
            price = self._cap_price(instrument, "market", None, quote) or ZERO
            pooled = sum((residual[i.id] for i in rest), ZERO) * price * instrument.multiplier
            # The gateway refuses any order over the cap, and each intent was checked against it
            # alone: a pool that would be larger is sent as its parts, one venue order each. A
            # single sell larger than the cap is sent in slices (`_start_exit_plan`).
            batches = [rest] if pooled <= cap else [[i] for i in rest]
            for batch in batches:
                if not batch:
                    continue
                if len(batch) == 1 and batch[0].side == "sell":
                    result = self._send(batch[0], residual[batch[0].id], now, quote, reference_price=touch["sell"])
                    outcomes.append(result)
                    continue
                result = self._route(batch, [residual[i.id] for i in batch], now, reference_price=touch[batch[0].side])
                for intent in batch:
                    outcomes.append(
                        Outcome(intent.id, intent.agent, result.status, result.detail, result.order_id, result.filled)
                    )
            for intent in intents:
                if residual[intent.id] <= 0:
                    outcomes.append(Outcome(intent.id, intent.agent, "crossed", "netted inside the House", None, intent.quantity))
        return outcomes

    def _plan_cross(self, parts: Sequence[tuple[Intent, Decimal]], quote: Quote, now: str) -> None:
        """Record all sides of an internal cross before moving any account's money.

        Exact fill payloads are prepared against private account copies so multiple intents
        by the same agent preserve sequential cost basis, realized profit and opening time.
        A restart needs neither a quote nor a venue write to finish this commitment.
        """
        identity = "|".join(intent.id for intent, _ in parts)
        plan_id = f"cross-plan:{self.name}:" + hashlib.sha256(identity.encode()).hexdigest()[:32]
        accounts = {intent.agent: copy.deepcopy(self._account(intent.agent)) for intent, _ in parts}
        fills = []
        for intent, quantity in parts:
            price = quote.ask if intent.side == "buy" else quote.bid
            charge = self.fees.charge(intent.instrument, intent.side, quantity, price, liquidity="taker")
            payload = self._fill_payload(intent.agent, intent, quantity=quantity, price=price, charge=charge,
                                         source="cross", order_id=None, account=accounts[intent.agent])
            payload["cross_plan_id"] = plan_id
            fills.append({"id": f"cross:{intent.id}", "agent": intent.agent, "payload": payload})
            self._apply_account_fill(accounts[intent.agent], payload, now)
            multiplier = intent.instrument.multiplier
            if intent.side == "buy":
                house_cash = quantity * price * multiplier + charge.usd
                house_units = -(quantity - charge.quantity)
            else:
                house_cash = -(quantity * price * multiplier - charge.usd)
                house_units = quantity
            house_payload = {
                "book": self.name,
                "source": "cross-house",
                "cross_plan_id": plan_id,
                "intent_id": intent.id,
                "instrument": intent.instrument.to_dict(),
                "side": "sell" if intent.side == "buy" else "buy",
                "quantity": text(quantity),
                "price": text(price),
                "fee_usd": "0",
                "cash_delta": text(q_cash(house_cash)),
                "position_delta": text(house_units),
                "real_money": self.real_money,
            }
            fills.append({"id": f"cross-house:{intent.id}", "agent": HOUSE, "payload": house_payload})
        payload = {"book": self.name, "plan_id": plan_id, "at": now, "fills": fills}
        self._commit_cross(payload)

    def _commit_cross(self, plan: Mapping[str, Any]) -> None:
        plan_id = plan["plan_id"]
        rows = [{"kind": "book.cross_plan", "payload": dict(plan), "id": plan_id, "at": plan["at"]}]
        rows.extend({"kind": "book.fill", "payload": fill["payload"], "agent": fill["agent"], "id": fill["id"], "at": plan["at"]}
                    for fill in plan["fills"])
        rows.append({"kind": "book.cross_plan", "payload": {"book": self.name, "plan_id": plan_id, "complete": True},
                     "id": f"{plan_id}:complete", "at": plan["at"]})
        # Older releases do not know the plan kind. They must still see either every ordinary
        # fill or none: an automatic rollback can never inherit half of an internal trade.
        entries = self.ledger.append_many(rows)
        for entry in entries:
            if entry.kind != "book.fill" or entry.id not in self._cross_applied:
                self._apply(entry.kind, entry.agent, entry.payload, entry.at)
        self._cross_cursor = max(self._cross_cursor, max(entry.seq for entry in entries))
        self._cross_applied.difference_update(fill["id"] for fill in plan["fills"])

    def _finish_crosses(self) -> None:
        """Finish durable internal commitments before accepting another order or polling."""
        with self._lock:
            # An append can be durable even when its caller did not reach the in-memory fold.
            # Read plans since the last pass so this process can recover too, without a restart.
            for entry in self.ledger.iter(kinds="book.cross_plan", after=self._cross_cursor):
                if entry.payload.get("book") == self.name:
                    self._apply(entry.kind, entry.agent, entry.payload, entry.at)
                self._cross_cursor = entry.seq
            for plan_id, plan in list(self._cross_plans.items()):
                self._commit_cross(plan)
            self._cross_applied.intersection_update(fill["id"] for plan in self._cross_plans.values() for fill in plan["fills"])

    def _apply_house(self, p: Mapping[str, Any], at: str = "") -> None:
        """The House row carries balancing cash and units; its units net to dust, never a position
        it meant to take, so they are held without cost-basis bookkeeping. A real book's dust that the
        regulators' unlisted fees explained (H4) spends that much of their room."""
        account = self._account(HOUSE)
        account.cash += money(p["cash_delta"])
        if p.get("unlisted_fees_usd"):
            self._note_unlisted(at, -money(p["unlisted_fees_usd"]), "real-book dust")
        delta = money(p["position_delta"])
        if delta != 0 and p.get("instrument"):
            instrument = Instrument.from_dict(p["instrument"])
            self._traded[position_key(instrument)] = instrument
            holding = account.holdings.get(instrument.key)
            if holding is None:
                holding = account.holdings[instrument.key] = Holding(instrument)
            holding.quantity += delta
            if holding.quantity == 0:
                del account.holdings[instrument.key]

    def _fill_payload(
        self,
        agent: str,
        intent: Intent | None,
        *,
        quantity: Decimal,
        price: Decimal,
        charge: Charge,
        source: str,
        order_id: str | None,
        instrument: Instrument | None = None,
        side: str | None = None,
        reason: str = "",
        intent_id: str | None = None,
        liquidity: str = "taker",
        venue_fee: Decimal = ZERO,
        account: Account | None = None,
    ) -> dict[str, Any]:
        instrument = instrument or intent.instrument
        side = side or intent.side
        multiplier = instrument.multiplier
        gross = quantity * price * multiplier
        if side == "buy":
            cash_delta = -(gross + charge.usd)
            position_delta = received(quantity, charge) if charge.quantity else quantity
        else:
            cash_delta = gross - charge.usd
            position_delta = -quantity
        realized = None
        held = None
        if side == "sell":
            # What this sale made against what the units cost, fees included: one closed trade.
            held = (account if account is not None else self._account(agent)).holdings.get(instrument.key)
            if held is not None and held.quantity > 0:
                realized = q_cash(cash_delta - held.cost * min(quantity, held.quantity) / held.quantity)
        payload = {
            "book": self.name,
            "source": source,
            "order_id": order_id,
            "intent_id": intent_id or (intent.id if intent else None),
            "realized": text(realized),
            "flat": bool(held is not None and quantity >= held.quantity) if side == "sell" else None,
            "opened_at": held.opened_at if held is not None else None,
            "entry_reason": held.reason if held is not None else None,
            "instrument": instrument.to_dict(),
            "side": side,
            "quantity": text(quantity),
            "price": text(price),
            "fee_usd": text(charge.usd),
            "fee_quantity": text(charge.quantity),
            "venue_fee": text(venue_fee),
            "liquidity": liquidity,
            "cash_delta": text(q_cash(cash_delta)),
            "position_delta": text(position_delta),
            "reason": reason or (intent.reason if intent else ""),
            "real_money": self.real_money,
        }
        if source == 'venue' and self.fees.family == 'kalshi':
            payload['venue_accounting_version'] = 2
        return payload

    def _route(self, intents: Sequence[Intent], quantities: Sequence[Decimal], now: str, *, reference_price: Decimal | None = None,
               slice_of: tuple[str, int] | None = None, note: str = "", repriced: Mapping[str, Any] | None = None,
               again: str | None = None) -> Outcome:
        """Send one venue order for these intents' quantities, then attribute what filled at once.

        `slice_of` is (plan id, index) for one slice of a sliced exit: its client order id is
        derived from the plan and the index, so each slice is a distinct order and the same slice
        can never be sent twice, whatever its size came to.

        `note` is what the House changed about the order and why (D3: an exit re-priced post-only to
        the ask). It is the `reason` of the rows written as the order is sent, beside any reason the
        venue gives, because an agent reads its orders' latest row (`recent_order_outcomes`)."""
        first = intents[0]
        total = sum(quantities, ZERO)
        identity = "|".join(sorted(i.id for i in intents)) if slice_of is None else f"{slice_of[0]}#{slice_of[1]}"
        if again:
            # The same intent sent again after the House cancelled its re-priced order (`_recheck_repriced`): its own
            # client order id, derived from the order it replaces, so it is never the cancelled order again.
            identity = f"{identity}#again:{again}"
        nonce = hashlib.sha256(identity.encode()).hexdigest()[:24]
        order_intent = self._order_intent(first, quantity=total, nonce=nonce)
        order_id = "ord-" + order_intent.id[3:]
        shares = [Share(i.id, i.agent, q, i.reason) for i, q in zip(intents, quantities)]
        base = {
            "book": self.name,
            "order_id": order_id,
            "instrument": first.instrument.to_dict(),
            "side": first.side,
            "quantity": text(total),
            "order_type": first.order_type,
            "limit_price": text(first.limit_price),
            "post_only": first.post_only,
            "shares": [{"intent_id": s.intent_id, "agent": s.agent, "quantity": text(s.quantity), "reason": s.reason} for s in shares],
            "submitted_at": now,
            "liquidity": self._liquidity(first),
            "real_money": self.real_money,
            "reference_price": text(first.limit_price or reference_price),
        }
        if slice_of is not None:
            base["slice"] = {"plan": slice_of[0], "index": int(slice_of[1])}
        if repriced is not None:
            base["house_repriced"] = dict(repriced)
        # The order is on the ledger before it is on the wire: a crash between the two leaves an
        # `unknown` order the next poll resolves by its client id, never an order nobody recorded.
        def told(reason: str = "") -> str:
            return "; ".join(part for part in (reason, note) if part)

        self._order_row(base, "new", None, suffix="new", reason=told())
        try:
            order = self.broker.submit(order_intent)
        except RejectedOrder as exc:
            self._order_row(base, "rejected", None, suffix="rejected", reason=told(str(exc)))
            return Outcome(first.id, first.agent, "rejected", str(exc), order_id)
        except (BrokerError, ValueError) as exc:
            # A gateway 502, venue 5xx or unreadable success may follow an accepted write.
            # Only an explicit rejection establishes that no order exists; preserve every
            # other outcome for client-id polling, without submitting another order.
            self._order_row(base, "unknown", None, suffix="unknown", reason=told(str(exc)))
            return Outcome(first.id, first.agent, "unknown", str(exc), order_id)
        # Persist the acknowledgement as pollable until every fill has been attributed.
        # Recording `filled` first used to strand the venue position after a crash here.
        # An answer that closes the order without a fill (the shadow book's "post-only order would
        # cross", a market with no quote) carries the venue's reason on the row: 148 kalshi-shadow
        # rejections by Sept 23, 2026 had an empty one, and only the wake's outcome knew why.
        closed_unfilled = order.filled_quantity <= 0 and order.status not in OPEN_STATUSES
        self._order_row(base, "accepted" if order.filled_quantity > 0 else order.status, order.broker_order_id, suffix="sent",
                        reason=told(str(order.reason or "") if closed_unfilled else ""))
        working = self.orders[order_id]
        self._attribute(working, order, now)
        if working.open and not working.rested:
            self._order_row(base, working.status, working.broker_order_id, suffix="rested", rested=True, reason=told())
        if working.filled >= working.quantity:
            status = "filled"
        elif working.filled > 0:
            status = "partial"
        elif working.open:
            # Alpaca accepts every order first and fills it a moment later: the next poll has it.
            status = "resting" if first.order_type == "limit" else "sent"
        else:
            status = working.status
        return Outcome(first.id, first.agent, status, order.reason or "", order_id, working.filled)

    def _liquidity(self, intent: Intent) -> str:
        """What the book assumes a fill of this order costs. Kalshi reports each order's fee, so
        this only matters on Alpaca, which reports none: there every order is booked at the
        taker's fee (a limit order may really have made, which only the venue knows), and
        reconciliation hands the difference to the House row within a known allowance."""
        if self.fees.family == "kalshi" and intent.order_type == "limit" and intent.post_only:
            return "maker"
        return "taker"

    def _order_row(self, base: Mapping[str, Any], status: str, broker_order_id: str | None, *, suffix: str, reason: str = "", rested: bool | None = None,
                   allocation: Mapping[str, Any] | None = None) -> None:
        payload = {**base, "status": status, "broker_order_id": broker_order_id, "reason": reason}
        if rested is not None:
            payload["rested"] = rested
        if allocation is not None:
            payload["allocation"] = dict(allocation)
        entry_id = f"order:{base['order_id']}:{suffix}"
        try:
            entry = self.ledger.append("book.order", payload, id=entry_id)
            self._apply(entry.kind, HOUSE, entry.payload, entry.at)
        except BaseException:
            # The append may already be durable. Retain its exact allocation/acknowledgement
            # in this process too; rebuilding it at a later time would conflict with its id.
            # Order metadata folds are idempotent and do not move cash or positions.
            recorded = self.ledger.get(entry_id)
            if recorded is not None:
                self._apply_order(recorded.payload, recorded.at)
            raise

    def _base_of(self, working: Working) -> dict[str, Any]:
        base = {
            "book": self.name,
            "order_id": working.order_id,
            "instrument": working.instrument.to_dict(),
            "side": working.side,
            "quantity": text(working.quantity),
            "order_type": working.order_type,
            "limit_price": text(working.limit_price),
            "post_only": working.post_only,
            "shares": [{"intent_id": s.intent_id, "agent": s.agent, "quantity": text(s.quantity), "reason": s.reason} for s in working.shares],
            "submitted_at": working.submitted_at,
            "liquidity": working.liquidity,
            "reference_price": text(working.reference_price),
            "real_money": self.real_money,
        }
        if working.slice_of is not None:
            base["slice"] = {"plan": working.slice_of, "index": int(working.slice_index or 0)}
        if working.repriced is not None:
            base["house_repriced"] = dict(working.repriced)
        return base

    def _attribute(self, working: Working, order: Order, now: str, *, reason: str = "") -> None:
        """Give each intent behind an order its part of what the venue has filled since last time.
        `reason` goes on the row recording a new status, when one is written."""
        self._finish_allocation(working)
        filled = money(order.filled_quantity)
        delta = filled - working.filled
        if delta < 0 or (delta > 0 and order.average_price is None):
            return  # a stale or incomplete venue response cannot close an unaccounted order
        if delta > 0 and order.average_price is not None:
            average = money(order.average_price)
            if (self.fees.family == 'kalshi' and market_key(order.instrument) == market_key(working.instrument)
                    and (order.instrument.right or 'yes') != (working.instrument.right or 'yes')):
                # GET reports directional exposure: selling YES is buying NO. Its cumulative
                # cost is on that returned leg. Attribute the receipt on the agent's original
                # leg, just as the V2 acknowledgement already does when an intent is present.
                average = ONE - average
            total_notional = average * filled
            price = (total_notional - working.notional) / delta
            venue_fees = money(order.fees or 0)
            fee_delta = max(venue_fees - working.fees_seen, ZERO)
            liquidity = working.liquidity
            if self.fees.family == "kalshi" and working.order_type == "limit" and liquidity == "taker" and fee_delta == 0:
                # Kalshi decides maker or taker at the moment of the fill and reports the fee (the
                # shadow book does the same): a limit order that rested and was then filled paid the
                # maker's fee, nothing on most series. Booked as "taker" it read as a taker execution
                # with no fee, and the frontier auditor vetoed the best paper agent on the floor for
                # "unexplained zero-fee taker executions" (huang-h6d3302, Sept 23, 2026 09:32Z). The
                # money is the venue's number either way; only the label was wrong.
                liquidity = "maker"
            step = step_of(working.instrument, working.order_type)
            rooms = [s.quantity - s.filled for s in working.shares]
            parts = allocate(delta, rooms, step)
            fee_parts = _split_cash(fee_delta, parts)
            before = working.filled
            targets = []
            for share, part, venue_fee in zip(list(working.shares), parts, fee_parts):
                if part <= 0:
                    continue
                if self.fees.family == "kalshi":
                    # The venue's own number: the real adapter and the shadow book both report each
                    # order's fees, and they decide maker or taker at the moment of the fill.
                    charge = Charge(usd=venue_fee)
                else:
                    charge = self.fees.charge(
                        working.instrument, working.side, part, price, liquidity=liquidity, filled_before=before
                    )
                target = share.filled + part
                targets.append({"intent_id": share.intent_id, "target": text(target), "quantity": text(part),
                                "fee_usd": text(charge.usd), "fee_quantity": text(charge.quantity), "venue_fee": text(venue_fee),
                                "fill_id": f"fill:{working.order_id}:{share.intent_id}:{text(target)}"})
                before += part
            # The plan is durable before the first share is applied. Recomputing a partially
            # applied pro-rata split after a restart gives the first share some of the next
            # share's fill; the venue can still reconcile while the agents' records are wrong.
            plan = {"filled": text(filled), "price": text(price), "at": now, "liquidity": liquidity, "targets": targets}
            self._order_row(self._base_of(working), working.status, order.broker_order_id or working.broker_order_id,
                            suffix=f"allocation:{text(filled)}", allocation=plan)
            self._finish_allocation(working)
        if order.status != working.status:
            if order.status not in OPEN_STATUSES:
                told = self._cancel_why.pop(working.order_id, "")
                if not reason and order.status == "cancelled":
                    reason = told  # the House's own cancel, confirmed only now (`_clear_the_way`)
            self._order_row(self._base_of(working), order.status, order.broker_order_id or working.broker_order_id, suffix=f"{order.status}:{text(filled)}",
                            reason=reason)

    def _finish_allocation(self, working: Working) -> None:
        plan = working.allocation
        if not plan:
            return
        shares = {share.intent_id: share for share in working.shares}
        accounts: dict[str, Account] = {}
        rows = []
        for target in plan["targets"]:
            share = shares[target["intent_id"]]
            if share.filled >= money(target["target"]):
                continue
            if share.agent not in accounts:
                accounts[share.agent] = copy.deepcopy(self._account(share.agent))
            payload = self._fill_payload(
                share.agent, None, quantity=money(target["quantity"]), price=money(plan["price"]),
                charge=Charge(usd=money(target["fee_usd"]), quantity=money(target["fee_quantity"])),
                source="venue", order_id=working.order_id,
                instrument=working.instrument, side=working.side, reason=share.reason, intent_id=share.intent_id,
                liquidity=plan["liquidity"], venue_fee=money(target["venue_fee"]), account=accounts[share.agent],
            )
            rows.append({"kind": "book.fill", "payload": payload, "agent": share.agent, "id": target["fill_id"], "at": plan["at"]})
            self._apply_account_fill(accounts[share.agent], payload, plan["at"])
        # A rollback into an older release must not see only the first agent's share either.
        # Commit the entire incremental allocation before updating any in-memory account.
        for entry in self.ledger.append_many(rows) if rows else []:
            self._apply(entry.kind, entry.agent, entry.payload, entry.at)

    # ------------------------------------------------------------ sliced exits
    def _cap_price(self, instrument: Instrument, order_type: str, limit_price: Decimal | None, quote: Quote | None) -> Decimal | None:
        """The price an order is counted at against the order cap: the dearest of its own limit and
        both sides of the quote, and for an Alpaca market order the gateway's own ten per cent over
        the touch (`GATEWAY_MARKET_MARKUP`). Kalshi's gateway counts an exit on the leg it trades,
        at most the leg's ask. None when there is nothing to count it at."""
        prices = [p for p in (limit_price, getattr(quote, "bid", None), getattr(quote, "ask", None)) if p is not None and p > 0]
        if not prices:
            return None
        price = max(prices)
        if self.fees.family == "alpaca" and order_type == "market":
            price *= GATEWAY_MARKET_MARKUP
        return price

    def _gateway_entry_price(self, intent: Intent, reference: Decimal | None) -> Decimal | None:
        """What the gateway counts one unit of an ENTRY at against its per-order cap
        (`gateway/lib/caps.mjs`, `router.mjs`), which can be dearer than the book's own count: a
        limit order at its own limit even where the ask is lower (the book counts a marketable limit
        at the ask it will fill at), and an Alpaca market order -- the adapter always sends `qty` --
        at the venue's touch plus ten per cent (`GATEWAY_MARKET_MARKUP`), since it may fill through
        the touch. A Kalshi market order goes out as a limit at the touch, so it counts at the touch.
        Found in review, Sept 23, 2026: a rung-3 order limit of $75 let the book approve a $75 market
        buy of BTC/USD that the gateway counted at $82.50 and refused."""
        if intent.order_type == "limit" and intent.limit_price is not None and intent.limit_price > 0:
            return intent.limit_price
        if reference is None or reference <= 0:
            return None
        if self.fees.family == "alpaca" and intent.instrument.asset_class != "option":
            return reference * GATEWAY_MARKET_MARKUP
        return reference

    def _over_cap(self, intent: Intent, quantity: Decimal, quote: Quote | None) -> bool:
        price = self._cap_price(intent.instrument, intent.order_type, intent.limit_price, quote)
        return price is not None and quantity * price * intent.instrument.multiplier > money(self.rules["max_order_usd"])

    def _send(self, intent: Intent, quantity: Decimal, now: str, quote: Quote | None, *, reference_price: Decimal | None = None,
              note: str = "") -> Outcome:
        """Route one intent's order; a sell worth more than the order cap is sent in slices."""
        if intent.side == "sell" and self._over_cap(intent, quantity, quote):
            return self._start_exit_plan(intent, quantity, now, quote)
        return self._route([intent], [quantity], now, reference_price=reference_price, note=note)

    def _slice_quantity(self, intent: Intent, available: Decimal, quote: Quote | None, cap: Decimal) -> Decimal:
        """The next slice: `available` cut into equal parts of at most the cap, on the instrument's
        quantity grid, so the last part is never a crumb. Where the venue has a minimum order ($10
        for Alpaca crypto, `venues.min_order_usd`) and equal parts would fall under it, parts are
        merged: one order a little over the cap -- an exit, which the gateway lets through -- rather
        than an order the venue refuses. A single unit worth more than the cap (a whole share of an
        equity order that is not a `day` order, an option contract) cannot be cut, and goes as one
        unit: an exit, which the gateway lets through its cap."""
        from .venues import min_order_usd  # the venue's own rule, kept with the venue's others

        instrument = intent.instrument
        step = step_of(instrument, intent.order_type)
        if instrument.asset_class == "equity" and str(intent.time_in_force) != "day":
            # A fractional share order is a `day` order only (`fractional_tif_reason`): a gtc exit is
            # cut on whole shares, never into fractional slices the venue, the adapter and this book's
            # own `check` on the next pass would all refuse (review of A7, Sept 23, 2026: a 2-share gtc
            # limit exit at $95 went out as three 0.67-share gtc slices).
            step = ONE
        price = self._cap_price(instrument, intent.order_type, intent.limit_price, quote)
        if price is None:
            return available
        value = available * price * instrument.multiplier
        if value <= cap:
            return available
        pieces = (value / cap).to_integral_value(rounding=ROUND_CEILING)
        minimum = min_order_usd(instrument)
        sale = intent.limit_price or (quote.bid if quote is not None else None)
        if minimum is not None and sale:
            worth = available * sale * instrument.multiplier
            if worth / pieces < minimum:
                pieces = max(ONE, (worth / minimum).to_integral_value(rounding=ROUND_FLOOR))
        size = (available / pieces / step).to_integral_value(rounding=ROUND_DOWN) * step
        return min(available, max(size, step))

    def _plan_slices(self, plan_id: str) -> list[Working]:
        return [self.orders[order_id] for order_id in self._plan_orders.get(plan_id, ()) if order_id in self.orders]

    def _start_exit_plan(self, intent: Intent, quantity: Decimal, now: str, quote: Quote | None) -> Outcome:
        """Record the plan for a sell too large for one order, then send what this pass can."""
        cap = money(self.rules["max_order_usd"])
        price = self._cap_price(intent.instrument, intent.order_type, intent.limit_price, quote) or ZERO
        expected = max(1, int((quantity * price * intent.instrument.multiplier / cap).to_integral_value(rounding=ROUND_CEILING)))
        plan_id = f"exit-plan:{self.name}:{intent.id}"
        payload = {
            "book": self.name, "plan_id": plan_id, "intent": {**intent.to_dict(), "expires_at": intent.expires_at},
            "quantity": text(quantity), "cap_usd": text(cap), "slices_expected": expected,
            "max_orders": max(8, 3 * expected + 2), "ttl_seconds": EXIT_PLAN_TTL_SECONDS, "created_at": now,
            "real_money": self.real_money,
        }
        entry = self.ledger.append("book.exit_plan", payload, agent=intent.agent, id=plan_id)
        self._apply(entry.kind, entry.agent, entry.payload, entry.at)
        plan = self.exit_plans.get(plan_id)
        sent = self._advance_plan(plan, now, quote=quote, checked=True) if plan is not None else []
        slices = self._plan_slices(plan_id)
        filled = sum((w.filled for w in slices), ZERO)
        if filled >= quantity:
            status = "filled"
        elif filled > 0:
            status = "partial"
        elif any(w.open for w in slices):
            status = "resting" if intent.order_type == "limit" else "sent"
        elif slices and slices[-1].status in ("rejected", "unknown"):
            status = slices[-1].status
        else:
            status = "sent"
        still = plan_id in self.exit_plans
        detail = (f"a sell worth more than the ${cap} order cap, sent in slices of at most the cap: {len(sent)} order(s) now, "
                  f"{text(filled)} of {text(quantity)} filled" + ("; the rest follows on the next passes" if still and filled < quantity else ""))
        return Outcome(intent.id, intent.agent, status, detail, sent[0] if sent else None, filled)

    def _advance_plans(self, now: str) -> None:
        """Send the next slices of every unfinished exit (`poll` calls this after booking fills)."""
        for plan in list(self.exit_plans.values()):
            try:
                self._advance_plan(plan, now)
            except Exception as exc:  # noqa: BLE001 - one plan's failure must not stop the poll or the settlements after it
                try:
                    self._refuse_slice(plan, len(self._plan_orders.get(plan.plan_id, ())),
                                       [f"the book could not send this slice: {type(exc).__name__}: {str(exc)[:200]}"])
                except Exception:  # noqa: BLE001 - the plan is retried next pass either way
                    pass

    def _advance_plan(self, plan: ExitPlan, now: str, *, quote: Quote | None = None, checked: bool = False) -> list[str]:
        """Send slices of `plan` until one does not finish at once, and return their order ids.

        Each slice sizes off what is still held and not already offered, and off what the plan
        still owes (its quantity less what its slices filled and what is still working). A slice
        that fills in full is followed at once by the next; one still working (a resting limit,
        an Alpaca market order the venue fills a moment later) is too, since it already holds its
        own units; one refused, rejected or only partly filled ends this pass and leaves the rest
        to the next. `checked` is for the pass inside `submit`, where the whole intent has just
        passed `check`; on every later pass each slice is checked again, as a new order would be.

        A slice that would meet the House's own resting order is not refused for it (D3): the
        seller's own crossing order is cancelled, and a slice that would meet another agent's goes one
        step above the House's bid, or post-only to the ask on doubt (`_clear_the_way` with
        `cross=False`, `_exit_past_the_house`): a plan is never crossed inside the House, whose fills
        would share the intent's one cross id. That holds for every slice, the first pass's included,
        each against the House's orders as they stand when it goes (review of #226)."""
        sent: list[str] = []
        intent = plan.intent
        key = intent.instrument.key
        market = intent.order_type == "market"
        for _ in range(plan.max_orders):
            if plan.plan_id not in self.exit_plans:
                break
            slices = self._plan_slices(plan.plan_id)
            filled = sum((w.filled for w in slices), ZERO)
            working = sum((w.remaining for w in slices if w.open), ZERO)
            holding = self._account(intent.agent).holdings.get(key)
            held = holding.quantity if holding is not None else ZERO
            remaining = plan.quantity - filled - working
            if remaining <= 0 or held <= 0:
                if working <= 0:
                    self._close_plan(plan, "sold" if remaining <= 0 else "nothing of it is held any more")
                break
            if any(w.status in ("new", "unknown") for w in slices):
                break  # the venue has not said what became of a slice: the poll finds out before anything more is sent
            if market and self.market_open is not None and self.market_open(intent.instrument, now) is False:
                # A market sell of a stock or an option outside the regular session is refused
                # ("market orders outside regular hours are not permitted"), so a plan begun in
                # session whose later slices fell after the close was refused slice by slice until it
                # timed out, and the rest of the position waited for a fresh intent (Sept 23, 2026,
                # workstream B; the House holds a whole wind-down for the open the same way). The
                # remaining slices wait here instead: nothing is refused, and the time-to-live counts
                # again from the open, not through the night.
                if plan.held_since is None:
                    plan.held_since = now
                break
            if plan.held_since is not None:
                plan.held_since, plan.resumed_at = None, now
            if len(slices) >= plan.max_orders:
                self._close_plan(plan, f"{len(slices)} orders sent, the most one exit may send")
                break
            if _epoch_seconds(now) - _epoch_seconds(plan.resumed_at or plan.created_at) > plan.ttl_seconds:
                self._close_plan(plan, f"not finished within {plan.ttl_seconds // 60} minutes")
                break
            offered = sum((share.quantity - share.filled for w in self.orders.values() if w.open and w.side == "sell" and w.instrument.key == key
                           for share in w.shares if share.agent == intent.agent), ZERO)
            available = min(remaining, held - offered)
            if available <= 0:
                break
            index = len(slices)
            fresh = quote if (checked and not sent and quote is not None) else self._quote(intent.instrument)
            if market and (fresh is None or fresh.bid is None or fresh.ask is None or fresh.bid <= 0):
                self._refuse_slice(plan, index, ["no two-sided quote to price a market order against"])
                break
            size = self._slice_quantity(intent, available, fresh, plan.cap_usd)
            part = dataclasses.replace(intent, quantity=size)
            told, repriced = "", None
            if not checked:
                reasons = self.check(part, fresh, now, clearing=True)
                if reasons:
                    self._refuse_slice(plan, index, reasons)
                    break
            # Every slice, the first pass's too, is cleared of the House's orders as they stand when it goes: the
            # plan holds the agent's own intent (`_finish_clearing`), never a price the House chose for an earlier
            # slice. With nothing of the House's in the way this changes nothing (review of #226).
            cleared = self._clear_the_way(part, fresh, now, cross=False)
            if cleared is not None:
                part, told = self._exit_past_the_house(part, fresh, cleared.doubt)
                if part is None:
                    self._refuse_slice(plan, index, [told])
                    break
                repriced = self._terms(intent) if told else None
            outcome = self._route([part], [size], now, reference_price=fresh.bid if (part.order_type == "market" and fresh is not None) else None,
                                  slice_of=(plan.plan_id, index), note=told, repriced=repriced)
            if outcome.order_id:
                sent.append(outcome.order_id)
            order = self.orders.get(outcome.order_id or "")
            if order is None or not (order.open or order.filled >= order.quantity):
                break
        return sent

    def _refuse_slice(self, plan: ExitPlan, index: int, reasons: Sequence[str]) -> None:
        """On the record once per slice, however many passes find the same wall."""
        entry_id = f"refused:{plan.plan_id}:{index}"
        if self.ledger.get(entry_id) is not None:
            return
        self.ledger.append(
            "book.refused",
            {"book": self.name, "intent_id": plan.intent.id, "slice_of": plan.plan_id, "slice_index": index,
             "reasons": list(reasons), "instrument": plan.intent.instrument.to_dict()},
            agent=plan.intent.agent, id=entry_id,
        )

    def _close_plan(self, plan: ExitPlan, reason: str) -> None:
        slices = self._plan_slices(plan.plan_id)
        payload = {"book": self.name, "plan_id": plan.plan_id, "closed": reason,
                   "filled": text(sum((w.filled for w in slices), ZERO)), "orders": len(slices)}
        entry = self.ledger.append("book.exit_plan", payload, agent=plan.intent.agent, id=f"{plan.plan_id}:closed")
        self._apply(entry.kind, entry.agent, entry.payload, entry.at)

    def _supersede(self, intent: Intent) -> None:
        """An agent's newer sell of the same instrument is its wish now: an older exit still
        slicing stops (its working slices stay working and keep their units), so two plans never
        compete for one holding."""
        for plan in list(self.exit_plans.values()):
            if plan.intent.agent == intent.agent and plan.intent.instrument.key == intent.instrument.key and plan.intent.id != intent.id:
                self._close_plan(plan, f"superseded by a newer sell ({intent.id})")

    # -------------------------------------------------------------------- poll
    def poll(self) -> int:
        """Ask the venue about every open order and attribute new fills. Returns orders checked."""
        checked = 0
        with self._lock:
            self._finish_crosses()
            now = now_iso(self.clock)
            for working in list(self.orders.values()):
                if not working.open:
                    continue
                try:
                    order = self.broker.get_order(working.broker_order_id or working.order_id)
                except RejectedOrder:
                    if working.status in ("new", "unknown"):
                        self._venue_missed(working, now)
                    continue
                except BrokerError:
                    continue
                self._missed.pop(working.order_id, None)
                checked += 1
                self._attribute(working, order, now)
            checked += self._recheck_never_arrived(now)
            if self._reconciled_here:
                # Every fill the venue reported is booked first: the next slice of an exit sizes
                # off what is still held after them, never off what was held a pass ago. An exit the House
                # re-priced is read again first (`_recheck_repriced`), so a plan whose re-priced slice it
                # cancels sends the rest, cleared as the House's orders stand now.
                self._recheck_repriced(now)
                self._advance_plans(now)
        return checked

    def _venue_missed(self, working: Working, now: str) -> None:
        """The venue answered a poll about an order it never acknowledged with "no such order".
        One such answer is remembered, not believed: the verdict "never arrived" -- which frees the
        order's cash and stops the polling -- takes a second one at least `NEVER_ARRIVED_SECONDS`
        later, so a venue answering 404 while it catches up with a write it took cannot make a fill
        disappear. A restart forgets the first answer and asks twice again, which is the safe way round."""
        first = self._missed.get(working.order_id)
        if first is None:
            self._missed[working.order_id] = now
            return
        if _epoch_seconds(now) - _epoch_seconds(first) < NEVER_ARRIVED_SECONDS:
            return
        self._missed.pop(working.order_id, None)
        self._order_row(self._base_of(working), "rejected", None, suffix="never-arrived", reason=NEVER_ARRIVED)

    def _recheck_never_arrived(self, now: str) -> int:
        """Ask the venue once more, each poll for `NEVER_ARRIVED_RECHECK_SECONDS` after the verdict,
        about every order closed as never arrived (`_never_arrived`, folded from the ledger so a
        restart keeps asking). One the venue has after all is revived on the record (a `found` row
        with the venue's own status) and its fills are booked as any order's: a rejected order the
        venue then fills was otherwise a position the book did not know, a frozen book, and an
        agent's entry lost from its record. Returns the orders checked."""
        checked = 0
        for order_id, since in list(self._never_arrived.items()):
            if _epoch_seconds(now) - _epoch_seconds(since or now) > NEVER_ARRIVED_RECHECK_SECONDS:
                self._never_arrived.pop(order_id, None)
                continue
            working = self.orders.get(order_id)
            if working is None:
                self._never_arrived.pop(order_id, None)
                continue
            try:
                order = self.broker.get_order(working.broker_order_id or working.order_id)
            except BrokerError:
                continue  # still no such order, or no answer: asked again next poll until the window closes
            checked += 1
            self._order_row(self._base_of(working), "accepted" if order.filled_quantity > 0 else order.status, order.broker_order_id,
                            suffix="found", reason="the venue has this order after all; it was closed as never arrived")
            self._attribute(working, order, now)
        return checked

    def cancel(self, agent: str, order_id: str, *, why: str = "") -> Outcome:
        """Cancel one of `agent`'s orders at the venue and book what the venue then says of it.

        What is booked is the venue's answer to a READ after the cancel, not the cancel's own answer
        (Sept 24, 2026, found building D3): the Kalshi adapter reads the order, deletes it, and returns
        the count it read BEFORE the delete, so a fill landing in between was closed as "cancelled"
        without it, never polled again, and left the real book a position short of its venue. A read
        that fails books nothing: the order stays open to the book and the next poll asks again. `why`
        is the reason on the order's cancelled row (the House's own cancels say why; D3)."""
        with self._lock:
            working = self.orders.get(order_id)
            if working is None or not any(s.agent == agent for s in working.shares):
                return Outcome("", agent, "refused", "no such order of yours", order_id)
            if not working.open:
                return Outcome("", agent, "refused", f"order is already {working.status}", order_id)
            now = now_iso(self.clock)
            refused = self._cancel_at_venue(working, agent, now, why=why)
            if refused is not None:
                return Outcome("", agent, "rejected", refused, order_id)
            plan = self.exit_plans.get(working.slice_of or "")
            if plan is not None:
                # Cancelling a slice withdraws the exit: the rest of it is not sent behind the
                # canceller's back. Whoever cancelled it (the agent, the horizon rule) asks again.
                self._close_plan(plan, f"a slice ({order_id}) was cancelled")
            return Outcome("", agent, working.status, "", order_id, working.filled)

    def _cancel_at_venue(self, working: Working, agent: str, now: str, *, why: str = "") -> str | None:
        """The venue half of `cancel`: ask the venue to cancel, write the `book.cancel` row, and book the venue's
        answer to a READ after the cancel (see `cancel`). Returns the venue's refusal, or None. It never closes an
        exit plan: `cancel` does that for a slice the agent or a House rule withdraws, and `_recheck_repriced` keeps
        the plan, whose next slice is cleared again."""
        self._cancel_why.pop(working.order_id, None)  # a new cancel says its own why
        reference = working.broker_order_id or working.order_id
        try:
            self.broker.cancel(reference)
        except BrokerError as exc:
            return str(exc)
        self.ledger.append("book.cancel", {"book": self.name, "order_id": working.order_id}, agent=agent, id=f"cancel:{working.order_id}")
        try:
            order = self.broker.get_order(reference)
        except BrokerError:
            order = None
        if order is not None:
            self._attribute(working, order, now, reason=why if order.status == "cancelled" else "")
        return None

    @staticmethod
    def _terms(intent: Intent) -> dict[str, Any]:
        """The agent's own order terms, kept on an exit the House re-priced (`house_repriced`), so the House can send
        the agent's order again, as asked, once nothing of the House's stands in its way (`_recheck_repriced`)."""
        return {"order_type": intent.order_type, "limit_price": text(intent.limit_price), "post_only": intent.post_only,
                "time_in_force": intent.time_in_force, "created_at": intent.created_at, "expires_at": intent.expires_at}

    def _withdraw_repriced(self, intent: Intent, now: str) -> None:
        """The agent's own new sell of an instrument supersedes every exit of its there that the House re-priced
        (review of #226, the owner's decision): each is cancelled through the venue, read again until the venue
        confirms it (`_await_cancel`), and only then is the new sell checked, against the position as if it were
        gone. One whose cancel the venue has not confirmed still holds its units, so the new sell can never sell
        them twice; it is refused for them, and the cancelled row says why once the venue confirms it."""
        for working in list(self.orders.values()):
            if (working.repriced is None or not working.open or working.side != "sell"
                    or working.instrument.key != intent.instrument.key or not working.shares
                    or not all(share.agent == intent.agent for share in working.shares)):
                continue
            self.cancel(intent.agent, working.order_id, why=SUPERSEDED_WHY)
            self._await_cancel(working, now, why=SUPERSEDED_WHY)
            if working.open:
                self._cancel_why[working.order_id] = SUPERSEDED_WHY

    def _recheck_repriced(self, now: str) -> None:
        """An exit the House re-priced lives one pass (review of #226, the owner's decision). Each poll reads it again:
        where the House would still put the agent's order now (`_exit_past_the_house` as the orders stand), it stays;
        otherwise it is cancelled and what the venue left of it is sent again -- as the agent asked once nothing of
        the House's stands in its way, one step above the House's bid, or post-only at the NEW ask while in doubt. A
        slice's plan sends its rest itself, cleared as it stands (`_advance_plan`, next in the poll). An order whose
        cancel the venue has not confirmed is read again next pass; one the House cannot price now is left, and the
        agent's own next sell supersedes it (`_withdraw_repriced`). Nothing is crossed here: a cross takes the
        agent's own next sell, which clears the way afresh."""
        for working in list(self.orders.values()):
            terms = working.repriced
            if (terms is None or not working.open or working.side != "sell" or len(working.shares) != 1
                    or working.status not in ("accepted", "partially_filled") or not working.broker_order_id):
                continue  # not one the venue has acknowledged as resting: the poll finds out first
            if working.slice_of is not None and working.slice_of not in self.exit_plans:
                continue  # a slice of a plan that has ended: the agent's next sell supersedes it
            try:
                self._recheck_one(working, terms, now)
            except Exception:  # noqa: BLE001 - one order read again next pass must not stop the poll or the plans after it
                continue

    def _recheck_one(self, working: Working, terms: Mapping[str, Any], now: str) -> None:
        share = working.shares[0]
        left = share.quantity - share.filled
        if left <= 0:
            return
        asked = Intent(
            id=share.intent_id, agent=share.agent, instrument=working.instrument, side="sell", quantity=left,
            order_type=str(terms.get("order_type") or "market"),
            limit_price=None if terms.get("limit_price") is None else money(terms["limit_price"]),
            post_only=bool(terms.get("post_only")), time_in_force=str(terms.get("time_in_force") or default_tif(working.instrument, "market")),
            reason=share.reason, created_at=str(terms.get("created_at") or working.submitted_at), expires_at=terms.get("expires_at"),
        )
        quote = self._quote(working.instrument)
        target, _ = self._exit_past_the_house(asked, quote, None)
        if target is None or (target.order_type, target.limit_price, target.post_only) == (
                working.order_type, working.limit_price, working.post_only):
            return  # still where the House would put it, or no price for it now
        if working.slice_of is None and self._over_cap(target, left, quote):
            return  # sent again it would be over the order cap: the agent's own next sell sends it in slices
        if self._cancel_at_venue(working, share.agent, now, why=RECHECK_WHY) is not None:
            return  # the venue refused the cancel: read again next pass
        self._await_cancel(working, now, why=RECHECK_WHY)
        if working.open:
            self._cancel_why[working.order_id] = RECHECK_WHY
            return
        if working.slice_of is not None:
            return  # the plan sends what is left, cleared as the orders stand now
        holding = self._account(share.agent).holdings.get(working.instrument.key)
        offered = sum((s.quantity - s.filled for w in self.orders.values() if w.open and w.side == "sell"
                       and w.instrument.key == working.instrument.key for s in w.shares if s.agent == share.agent), ZERO)
        left = min(share.quantity - share.filled, (holding.quantity if holding is not None else ZERO) - offered)
        if left <= 0:
            return
        target, note = self._exit_past_the_house(dataclasses.replace(asked, quantity=left), quote, None)
        if target is None:
            return
        market = target.order_type == "market"
        self._route([target], [left], now, reference_price=quote.bid if (market and quote is not None) else None,
                    note=note or RESENT_NOTE, repriced=dict(terms) if note else None, again=working.order_id)

    def cancel_all(self, agent: str) -> int:
        return sum(1 for w in self.open_orders(agent) if self.cancel(agent, w.order_id).status == "cancelled")

    # ------------------------------------------------------------------ settle
    def settle(self, market_id: str, result: str, *, at: str | None = None) -> int:
        """A Kalshi market resolved: every holding of it pays $1 or $0 a contract."""
        result = str(result).lower()
        if result not in ("yes", "no"):
            raise BookError(f"settlement result must be yes or no, not {result!r}")
        settled = 0
        with self._lock:
            for agent, account in list(self.accounts.items()):
                for key, holding in list(account.holdings.items()):
                    inst = holding.instrument
                    if inst.asset_class != "event" or (inst.market_id or inst.symbol).upper() != market_id.upper():
                        continue
                    wins = (inst.right or "yes") == result
                    payout = holding.quantity * inst.multiplier if wins else ZERO
                    payload = {
                        "book": self.name,
                        "instrument": inst.to_dict(),
                        "result": result,
                        "quantity": text(holding.quantity),
                        "cost": text(q_cash(holding.cost)),
                        "payout": text(q_cash(payout)),
                        "pnl": text(q_cash(payout - holding.cost)),
                        "reason": holding.reason,
                        "opened_at": holding.opened_at,
                        "real_money": self.real_money,
                    }
                    entry = self.ledger.append("book.settle", payload, agent=agent, id=f"settle:{self.name}:{agent}:{key}", at=at)
                    self._apply(entry.kind, agent, entry.payload, entry.at)
                    self.marks.pop(key, None)
                    settled += 1
        return settled

    def expire_options(self, *, at: str | None = None) -> int:
        """Write off long options that have expired and that the venue no longer shows: they paid
        nothing. One the venue still shows is left alone (it clears overnight); one that was
        exercised into shares shows up as a position the book does not know, and freezes it."""
        now = at or now_iso(self.clock)
        today = _new_york_date(now)
        with self._lock:
            due = [(agent, key, holding) for agent, account in self.accounts.items() for key, holding in account.holdings.items()
                   if holding.instrument.asset_class == "option" and str(holding.instrument.expiry or "9999") < today]
            if not due:
                return 0
            shown = {position_key(p.instrument) for p in self.broker.positions() if money(p.quantity) != 0}
            expired = 0
            for agent, key, holding in due:
                inst = holding.instrument
                if position_key(inst) in shown:
                    continue
                payload = {
                    "book": self.name, "instrument": inst.to_dict(), "result": "expired", "quantity": text(holding.quantity),
                    "cost": text(q_cash(holding.cost)), "payout": "0", "pnl": text(q_cash(-holding.cost)),
                    "reason": holding.reason, "opened_at": holding.opened_at, "real_money": self.real_money,
                }
                entry = self.ledger.append("book.settle", payload, agent=agent, id=f"expire:{self.name}:{agent}:{key}", at=at)
                self._apply(entry.kind, agent, entry.payload, entry.at)
                self.marks.pop(key, None)
                expired += 1
            return expired

    # -------------------------------------------------------------------- mark
    def mark(self) -> dict[str, Decimal]:
        """Re-quote every held instrument and record each agent's equity. Returns agent -> equity."""
        with self._lock:
            now = now_iso(self.clock)
            held: dict[str, Instrument] = {}
            for account in self.accounts.values():
                for key, holding in account.holdings.items():
                    held[key] = holding.instrument
            for instrument in held.values():
                self._quote(instrument)
            out: dict[str, Decimal] = {}
            for agent in self.agents():
                account = self._account(agent)
                equity = self.equity(agent)
                out[agent] = equity
                self.ledger.append(
                    "book.mark",
                    {
                        "book": self.name,
                        "equity": text(q_cash(equity)),
                        "cash": text(q_cash(account.cash)),
                        "staked": text(account.staked),
                        "realized": text(q_cash(account.realized)),
                        "fees": text(q_cash(account.fees)),
                        "holdings": len(account.holdings),
                        "real_money": self.real_money,
                    },
                    agent=agent,
                    at=now,
                )
            return out

    # --------------------------------------------------------------- reconcile
    def _venue(self) -> tuple[Decimal, dict[str, Decimal]]:
        balance = self.broker.balance()
        cash = money(balance.cash)
        if self.fees.family == "alpaca":
            # Measured on the paper account (Sept 19, 2026): Alpaca takes the cash behind an open
            # crypto buy order out of `cash` while the order rests ($80.00 for two $40 bids, to the
            # cent) and gives it back on a cancel. It is still the account's money, so it is added
            # back before comparing, or every resting bid would look like a missing $40.
            #
            # It holds each bid at its notional ROUNDED HALF-UP TO THE CENT (H4, measured on the real
            # account, Sept 25, 2026), not at `remaining x limit` to eighteen places, which the book added
            # back until then. At 04:37Z the account read $317.95 of cash beside twelve resting bids:
            # the bids' notionals rounded half-up sum to $147.68, and $317.95 + $147.68 = $465.63, what
            # its own activities add up to (the $500 deposit, each fill's cash to the cent, the fees);
            # rounded up, down or not at all they do not. Read that way, every one of the 339 readings
            # from Sept 24 00:00Z to Sept 25 04:26Z with no fill between them shows the account's cash
            # unchanged; read unrounded it moved 66 times, a few tenths of a cent a bid, each booked as
            # dust, until four of eight bids were cancelled in one pass (02:33-02:49Z Sept 25) and took
            # a cent of that error with them: "cash differs by 0.0108", a frozen real book and every
            # Alpaca real entry refused for 82 minutes, with no fill and no fee behind it.
            for order in self.broker.open_orders():
                if order.instrument.asset_class == "crypto" and order.side == "buy" and order.limit_price is not None:
                    held = money(order.remaining) * money(order.limit_price) * order.instrument.multiplier
                    cash += held.quantize(CENT, rounding=ROUND_HALF_UP)
        positions: dict[str, Decimal] = {}
        for position in self.broker.positions():
            instrument, quantity = position.instrument, money(position.quantity)
            if instrument.asset_class == "event" and quantity < 0:
                # The real Kalshi adapter reports NO contracts as a negative count on the market.
                instrument = Instrument("event", instrument.symbol, instrument.venue, market_id=instrument.market_id, right="no")
                quantity = -quantity
            key = position_key(instrument)
            positions[key] = positions.get(key, ZERO) + quantity
        return cash, positions

    def _book_venue_fees(self, shortfall: Decimal) -> Decimal:
        """Book venue fee activities not yet on the ledger, oldest first, while they fit inside the
        shortfall (a fee from before the baseline is already in the baseline and explains nothing).
        They are the House's cost: a day's fees are one rounded-up cent or two across every agent.
        An "OCC Clearing Fee" row is not booked where the option fill paid it (`Fees.option_clearing`,
        every Alpaca book since H4, Sept 25, 2026): Alpaca's paper account takes it at the fill and
        lists it the next morning, and booked again then it only ever explained some other shortfall
        (Sept 21-24, 2026: every one of the 46 was booked a day late, against an unrelated shortfall);
        the real account takes it at the fill too and lists it seconds later (Sept 24, 2026: 11 s and
        8 s after its two AAL call buys)."""
        read = getattr(self.broker, "fee_activities", None)
        if read is None:
            return ZERO
        try:
            since = (self.baseline_at or "")[:10] or None
            rows = read(since)
        except Exception:  # noqa: BLE001 - not knowing leaves the shortfall standing, which freezes entries
            return ZERO
        booked = ZERO
        for row in rows:
            if self.fees.option_clearing and str(row.get("description") or "").lower().startswith("occ clearing fee"):
                continue  # the option fill paid it, in the cash the venue took then
            fee = money(row["usd"])
            entry_id = f"venue-fee:{self.name}:{row['id']}"
            if fee <= 0 or self.ledger.get(entry_id) is not None or booked + fee > shortfall + DUST_USD:
                continue
            payload = {"book": self.name, "source": "venue-fee", "side": "fee", "instrument": None, "quantity": "0", "price": "0",
                       "cash_delta": text(-fee), "position_delta": "0", "fee_usd": text(fee), "realized": None,
                       "detail": f"{row.get('date')} {row.get('description') or 'regulatory fees'}".strip(), "real_money": self.real_money}
            entry = self.ledger.append("book.fill", payload, agent=HOUSE, id=entry_id)
            self._apply(entry.kind, HOUSE, entry.payload, entry.at)
            booked += fee
        return booked

    def _reset_since_clean(self) -> None:
        """A clean reading (reconciled, no settlement awaited): the counts since the last one start again."""
        self._fills_since_reconcile = 0
        self._fee_slack_usd = ZERO
        self._fee_slack_units = {}
        self._holds_transition = ZERO

    def _bid_rounding(self) -> Decimal:
        """What the book's working crypto bids add back unrounded beyond what Alpaca holds for them at
        the cent (`_venue`, H4): the error every reading before H4 booked as dust."""
        out = ZERO
        for working in self.orders.values():
            if working.open and working.instrument.asset_class == "crypto" and working.side == "buy" and working.limit_price is not None:
                held = working.remaining * working.limit_price * working.instrument.multiplier
                out += held - held.quantize(CENT, rounding=ROUND_HALF_UP)
        return out

    def _note_unlisted(self, at: str, usd: Decimal, what: str) -> None:
        """Add (or, negative, spend) room for the regulators' unlisted fees at the row's own time."""
        try:
            when = _epoch_seconds(at)
        except ValueError:
            when = float(self.clock())
        if when >= float(self.clock()) - UNLISTED_FEE_HOURS * 3600:
            self._unlisted_fees.append((when, usd, what))

    def _unlisted_room(self) -> tuple[Decimal, list[str]]:
        """The regulators' fees the last `UNLISTED_FEE_HOURS` of option and stock fills may still have
        taken unlisted, less the real dust already booked on them, and the fills that make the room."""
        cutoff = float(self.clock()) - UNLISTED_FEE_HOURS * 3600
        self._unlisted_fees = [row for row in self._unlisted_fees if row[0] >= cutoff]
        room = sum((usd for _, usd, _ in self._unlisted_fees), ZERO)
        return max(ZERO, room), [what for _, usd, what in self._unlisted_fees if usd > 0]

    def _explain_real_cents(self, cash_diff: Decimal, tolerance: Decimal) -> tuple[str, Decimal, Decimal] | None:
        """Why a REAL book's cash difference is the venue's own fees, or None: then it freezes (H4).

        Called only once every position agrees (after position dust), no order's outcome is unknown,
        no settlement is awaited, every venue fee activity that fits the shortfall has been booked
        (`_book_venue_fees`), and the difference is still over the per-fill tolerance (a cent for each
        venue fill since the last clean reading, the venue's rounding) and the maker's fee slack. It
        is EXPLAINED, and returned as `(why, dollars booked on the unlisted fees' room, the key)`,
        only when all of these hold:

        1. `allocator.real_book_dust_usd` is set inside its bounds ($0.25-1.00) and the difference is
           under it;
        2. the venue holds LESS than the book says: a shortfall. A surplus beyond the tolerance and
           the maker's fee slack is no fee of the venue's -- a dividend, interest, a refund, or a fill
           the book never saw -- and the owner is told by the freeze;
        3. option or stock fills on this book in the last `UNLISTED_FEE_HOURS` leave room for the
           regulators' fees Alpaca takes at the fill and lists as FEE activities only later (ORF, CAT,
           TAF, SEC: `UNLISTED_FEE_PER_FILL_USD` a fill plus `UNLISTED_FEE_PER_CONTRACT_USD` a
           contract or `UNLISTED_FEE_PER_SHARE_USD` a share), less the real dust already booked on
           that room, and the shortfall is no more than that room plus the tolerance.

        Nothing else explains: with no option or stock fill in the window a shortfall over the
        tolerance freezes (crypto fees are the book's own model, charged at the fill), and so does
        anything at or over the key, beside a position difference or an order in doubt, or larger
        than the fees could be. When the fees are listed (that evening, or the next night) they find
        no shortfall and are not booked; should a later shortfall meet one, `_book_venue_fees` books
        it then, and the House row still pays each dollar the venue took once, under one name or the
        other: every row here follows a reading of the venue."""
        key = real_book_dust_usd()
        if key is None or cash_diff >= 0 or -cash_diff >= key:
            return None
        room, fills = self._unlisted_room()
        shortfall = -cash_diff
        if room <= 0 or shortfall > room + tolerance:
            return None
        spent = q_cash(min(shortfall, room))
        shown = ", ".join(fills[-5:]) + (f" and {len(fills) - 5} more" if len(fills) > 5 else "")
        why = (f"regulatory fees (ORF, CAT, TAF, SEC) that Alpaca takes at option and stock fills and lists as FEE activities "
               f"only later: room for ${room:.2f} from the fills of the last {UNLISTED_FEE_HOURS} h ({shown}), and a cent of "
               f"rounding for each of the {self._fills_since_reconcile} venue fill(s) since the last clean reading")
        return why, spent, key

    def _ledger_totals(self) -> tuple[Decimal, dict[str, Decimal], dict[str, Instrument]]:
        """The book's own cash (profit and loss, fees, dust: stakes are slices, not deposits) and
        its positions, summed over every agent and the House row."""
        cash = sum((a.cash - a.staked for a in self.accounts.values()), ZERO)
        positions: dict[str, Decimal] = {}
        instruments: dict[str, Instrument] = {}
        for account in self.accounts.values():
            for holding in account.holdings.values():
                key = position_key(holding.instrument)
                positions[key] = positions.get(key, ZERO) + holding.quantity
                instruments[key] = holding.instrument
        return cash, positions, instruments

    def open_baseline(self) -> None:
        """Record, once, what the venue account holds that is not the book's. Everything the
        venue shows beyond this baseline must be explained by the ledger, to the cent."""
        with self._lock:
            if self.baseline_cash is not None:
                return
            # Orders resting at the venue that this book never sent (an earlier House on the same
            # account, a test) would fill later and read as money moving by itself: found on the
            # night of the build, when a leftover SOL bid filled under a new ledger. A practice
            # account is cleared of them; on a real account they are the owner's, so the book
            # refuses to open until they are gone.
            foreign = [o for o in self.broker.open_orders() if o.id not in self.orders]
            if foreign and self.real_money:
                raise BookError(f"{self.name} has {len(foreign)} open order(s) this book did not send; cancel them at the venue first")
            for order in foreign:
                self.broker.cancel(order.broker_order_id or order.id)
            for _ in range(10 if foreign else 0):
                # A cancel is not instant, and an order can fill while it is being cancelled. The
                # venue is read only once nothing of that kind is still working, so the baseline is
                # not half of one moment and half of the next.
                if not [o for o in self.broker.open_orders() if o.id not in self.orders]:
                    break
                self.sleep(1.0)
            venue_cash, venue_positions = self._venue()
            cash, positions, _ = self._ledger_totals()
            baseline = {
                key: venue_positions.get(key, ZERO) - positions.get(key, ZERO)
                for key in set(venue_positions) | set(positions)
            }
            self._baseline_row(venue_cash - cash, {k: v for k, v in baseline.items() if v != 0}, "opened")
            self.venue_cash = venue_cash

    def adjust_baseline(self, cash_delta: Any, note: str) -> None:
        """The owner moved money (a deposit or a withdrawal the venue's own record confirms)."""
        with self._lock:
            if self.baseline_cash is None:
                raise BookError(f"{self.name} has no baseline yet")
            self._baseline_row(self.baseline_cash + money(cash_delta), self.baseline_positions, note)

    def _baseline_row(self, cash: Decimal, positions: Mapping[str, Decimal], note: str) -> None:
        entry = self.ledger.append(
            "book.baseline",
            {"book": self.name, "cash": text(q_cash(cash)), "positions": {k: text(v) for k, v in positions.items()}, "note": note},
        )
        self._apply(entry.kind, HOUSE, entry.payload, entry.at)

    def _position_dust(self, instrument: Instrument, diff: Decimal) -> None:
        """The venue rounds an in-kind fee its own way. Under a cent of value, the ledger takes the
        venue's number: a shortfall comes off the largest holder (so its sell-all is a quantity the
        venue really has), a surplus goes to the House row."""
        agent = HOUSE
        if diff < 0:
            holders = [
                (account.holdings[instrument.key].quantity, name)
                for name, account in self.accounts.items()
                if instrument.key in account.holdings and account.holdings[instrument.key].quantity >= -diff
            ]
            if holders:
                agent = max(holders)[1]
        entry = self.ledger.append(
            "book.fill",
            {
                "book": self.name,
                "source": "dust",
                "instrument": instrument.to_dict(),
                "side": "sell" if diff < 0 else "buy",
                "quantity": text(abs(diff)),
                "price": "0",
                "fee_usd": "0",
                "cash_delta": "0",
                "position_delta": text(diff),
                "real_money": self.real_money,
            },
            agent=agent,
        )
        self._apply(entry.kind, agent, entry.payload, entry.at)

    def reconcile(self) -> Reconciliation:
        """Compare the book to the venue: venue cash must equal the baseline plus the book's own
        cash, and every venue position the baseline's plus the agents'. A difference under a cent
        (a cent a venue fill since the last reconciliation) is booked to the House row as dust, and
        on a PRACTICE book so is any cash difference under `PRACTICE_DUST_USD` while every position
        agrees and no order is in doubt; anything larger freezes new entries until it clears."""
        with self._lock:
            self.open_baseline()
            result = self._reconcile()
            self._reconciled_here = True
            if result.ok:
                self._unreconciled = 0
                return result
            # Counted before the never-traded re-read, not inside the other branch: a position the
            # venue holds that the ledger never learned about leaves every account empty, so
            # `_traded_yet` is false, so the counter never moved -- and the re-read below corrects
            # CASH only and leaves the position diff standing. The book froze for ever in exactly
            # the state the adoption exists to clear.
            self._unreconciled += 1
            if not self._traded_yet() and not result.position_diffs:
                # A book that has never traded cannot have drifted: its first reading of the venue
                # was taken across a moment that moved. (Sept 19, 2026: a leftover bid filled
                # between the cash read and the position read of a new league's first baseline, and
                # froze the book $40 short with no agent having traded at all.) It has nothing of
                # its own to lose by reading again -- unless a POSITION differs too: then the cash
                # is the price of units the venue holds and the book does not know (an order closed
                # as never arrived that filled after all, `_recheck_never_arrived`), and a re-read
                # that took that cash into the baseline left the book a fill's worth off for good
                # once the units were booked (Sept 23, 2026). Both diffs stand, and are cleared
                # together: by the revival, or by `_adopt_the_venue` on practice money.
                self._baseline_row(self.baseline_cash + result.cash_diff, self.baseline_positions,
                                   f"re-read: the book has never traded and the venue was {result.cash_diff:+.4f} against its first reading")
                result = self._reconcile()
                if result.ok:
                    self._unreconciled = 0
                    return result
            if self.real_money or self._unreconciled < ADOPT_AFTER:
                return result
            return self._adopt_the_venue(result)

    def _adopt_the_venue(self, result: Reconciliation) -> Reconciliation:
        """Practice money: take the venue's word for what is held and carry on.

        Sept 20, 2026: an order was sent to Alpaca's paper account, its poll failed on a transport
        error, and the book never learned it had filled. The venue held $40 of LTC the book did not
        know about, and the book froze -- which on this venue stops EVERY agent from entering
        anything, and it had been frozen for ninety minutes before anyone looked. An unattended
        floor cannot be stopped that way by practice money: a lost order must cost the agent that
        lost it, not the thirteen desks that share its venue.

        So after `ADOPT_AFTER` readings that do not reconcile, the difference joins the House's
        baseline -- it is not credited to any agent, so no agent's record is flattered by it -- and
        the ledger and the alert say exactly what was adopted. A real-money book never does this:
        there the freeze is the point, and the owner is told."""
        venue_cash, venue_positions = self._venue()
        cash, positions, _ = self._ledger_totals()
        baseline = {}
        for key in set(venue_positions) | set(positions):
            held = venue_positions.get(key, ZERO) - positions.get(key, ZERO)
            if held != 0:
                baseline[key] = held
        if any(value < 0 for value in baseline.values()):
            # Absorbing missing owned units into a negative baseline leaves phantom holdings
            # and fictitious mark-to-market performance while falsely reporting reconciliation.
            return result
        self._baseline_row(venue_cash - cash, baseline,
                           f"adopted the venue after {self._unreconciled} readings that did not reconcile ({result.detail}): "
                           "practice money, and a frozen book stops every agent on the venue")
        self._unreconciled = 0
        return self._reconcile()

    def _traded_yet(self) -> bool:
        """Whether any money of the league's has moved on this book. A stake is not a trade, and
        neither is an order resting at the venue: what counts is a position held, a result
        realised, or a fee paid. Nothing of the league's can be hidden by re-reading a baseline
        when none of those exists, and a fill that lands during the re-read leaves a position the
        ledger does not know, which freezes the book again on the next reading."""
        return any(a.holdings or a.realized or a.fees for name, a in self.accounts.items() if name != HOUSE)

    def _reconcile(self) -> Reconciliation:
        if True:
            from .accounting import repair_legacy_kalshi_fills, repair_paper_phantoms
            repair_legacy_kalshi_fills(self)
            repair_paper_phantoms(self)
            venue_cash, venue_positions = self._venue()
            self.venue_cash = venue_cash
            cash, positions, instruments = self._ledger_totals()
            # A baseline position the venue no longer shows has settled or been closed by the
            # owner: it leaves the baseline, and the cash it paid (at most $1 a contract for an
            # event contract) joins the baseline with it.
            for key, held in list(self.baseline_positions.items()):
                if key not in venue_positions and key not in positions and key.startswith("event:"):
                    paid = venue_cash - (self.baseline_cash + cash)
                    if ZERO <= paid <= abs(held) + DUST_USD:
                        remaining = {k: v for k, v in self.baseline_positions.items() if k != key}
                        self._baseline_row(self.baseline_cash + paid, remaining, f"baseline position {key} settled")
            expected = self.baseline_cash + cash
            cash_diff = venue_cash - expected
            diffs: dict[str, str] = {}
            for key in sorted(set(venue_positions) | set(positions) | set(self.baseline_positions)):
                diff = venue_positions.get(key, ZERO) - positions.get(key, ZERO) - self.baseline_positions.get(key, ZERO)
                if diff == 0:
                    continue
                instrument = instruments.get(key) or self._traded.get(key)
                mark = self.marks.get(instrument.key) if instrument is not None else None
                if instrument is not None and mark is None:
                    quote = self._quote(instrument)  # sold out long ago: the mark is gone, so ask
                    mark = self.marks.get(instrument.key) if quote is not None else None
                # Dust: under a cent of value, or no more than one quantity step for each venue fill
                # since the last reconciliation (the venue rounds each in-kind fee its own way).
                crumbs = step_of(instrument) * max(1, self._fills_since_reconcile) if instrument is not None else ZERO
                small = instrument is not None and (
                    (mark is not None and abs(diff) * mark * instrument.multiplier < DUST_USD)
                    or (step_of(instrument) < ONE and abs(diff) <= crumbs)
                )
                # The venue kept fewer coins than the taker's fee the book assumed: a maker's fill.
                refund = instrument is not None and ZERO < diff <= self._fee_slack_units.get(key, ZERO)
                if small or refund:
                    self._position_dust(instrument, diff)
                else:
                    diffs[key] = text(diff)
            # An event contract the venue no longer shows while the ledger still holds it has
            # usually just SETTLED, and the settlement row lands on the House's next pass (every 90
            # s). Sept 21, 2026 22:00:43: a 15-minute DOGE contract settled five seconds before its
            # row, the real book froze for one reading, and the watchdog rolled back a release. So
            # such a difference waits `SETTLEMENT_GRACE_SECONDS`, with the cash it may have paid.
            now_ts = float(self.clock())
            awaiting = {}
            for key in list(diffs):
                held = positions.get(key, ZERO)
                if key.startswith("event:") and venue_positions.get(key, ZERO) == 0 and held > 0 and money(diffs[key]) == -held:
                    first = self._awaiting_settlement.setdefault(key, now_ts)
                    if now_ts - first < SETTLEMENT_GRACE_SECONDS:
                        awaiting[key] = held
                        del diffs[key]
            for key in list(self._awaiting_settlement):
                if key not in awaiting and key not in diffs:
                    del self._awaiting_settlement[key]
            pending = any(w.status in ("new", "unknown") for w in self.orders.values())
            if cash_diff <= -DUST_USD and not diffs and not awaiting and not pending:
                # The venue holds less than the book says. Alpaca passes on the regulators' fees
                # (on equity sales and on every option contract) as one FEE activity at the end of
                # the day, which no fill ever showed: book the ones that explain the shortfall.
                # Never beside a position difference or an order in doubt: that shortfall is the
                # price of units the ledger has not booked yet. Sept 24, 2026, 11:29:48Z: an
                # in-flight BTC buy read "cash differs by -24.1299" with its coins at the venue, and
                # $0.87 of the day before's fee rows -- their cash long gone, at their fills -- were
                # booked against it; the fill landed seven seconds later and the book froze on
                # +0.8700 for ten minutes, until it adopted the venue.
                booked = self._book_venue_fees(-cash_diff)
                if booked:
                    cash, _, _ = self._ledger_totals()
                    expected = self.baseline_cash + cash
                    cash_diff = venue_cash - expected
            # A venue shows cash to the cent and rounds each fill's fee its own way: allow a cent
            # of drift for each venue fill since the last reconciliation, and book it as dust.
            tolerance = DUST_USD * max(1, self._fills_since_reconcile)
            # H4's transition (Sept 25, 2026): the first clean reading after the restart into this code
            # also allows the sub-cent errors the last reading before it booked on the bids resting then,
            # measured from the ledger's own orders (`_holds_transition`). On the snapshot of 04:26Z Sept
            # 25, 3 of the real Alpaca book's 101 clean readings since 18:30Z Sept 24 left 1.1-1.3 cents
            # of them: without this, a restart just after one would freeze the book and roll back the
            # deploy that ships the fix.
            tolerance += self._holds_transition
            within = abs(cash_diff) < tolerance or ZERO < cash_diff <= self._fee_slack_usd + tolerance
            if awaiting and not within and -tolerance < cash_diff <= sum(awaiting.values(), ZERO) + tolerance:
                within = True  # the venue has paid a settlement the ledger has not recorded yet
            if not within and self.fees.family == "alpaca":
                # Not yet measured (options first trade on Monday Sept 21, 2026): whether Alpaca
                # takes the premium behind a resting option bid out of `cash`, as it does for a
                # resting crypto bid. If it does, the shortfall is exactly that premium.
                held = sum((money(o.remaining) * money(o.limit_price) * o.instrument.multiplier for o in self.broker.open_orders()
                            if o.instrument.asset_class == "option" and o.side == "buy" and o.limit_price is not None), ZERO)
                if held > 0 and abs(cash_diff + held) < tolerance:
                    within, cash_diff = True, ZERO
            # A practice book is never frozen by cents (`PRACTICE_DUST_USD`): with every position
            # agreeing and no order in doubt, a difference under a dollar either way is the venue's
            # fees and rounding, and is booked as dust now, not after three frozen readings.
            practice_dust = (not within and not self.real_money and not diffs and not pending and not awaiting
                             and abs(cash_diff) < PRACTICE_DUST_USD)
            within = within or practice_dust
            # A REAL book is never frozen by cents its venue's own fees explain (H4, Sept 25, 2026;
            # `allocator.real_book_dust_usd`): with every position agreeing, no order in doubt and no
            # settlement awaited, a shortfall under the key that the regulators' unlisted fees on its
            # option and stock fills can make (`_explain_real_cents`) is booked to the House row as dust
            # with an error alert naming it. Sept 24, 2026, 18:23:24Z: the real account's first option
            # buy froze the book on -0.0308 (its OCC fee and $0.03 of ORF and CAT, all taken at the fill
            # and listed 11 s, two hours and six hours later), which blocked every Alpaca real entry.
            # Anything else keeps the freeze for the owner.
            real_dust = None
            if not within and self.real_money and not diffs and not pending and not awaiting:
                real_dust = self._explain_real_cents(cash_diff, tolerance)
                within = real_dust is not None
            ok = within and not diffs and not pending
            problems = []
            if not within:
                problems.append(f"cash differs by {cash_diff:.4f}")
            if diffs:
                problems.append("positions differ: " + ", ".join(f"{k} {v}" for k, v in diffs.items()))
            if pending:
                problems.append("an order's outcome is unknown")
            detail = "; ".join(problems)
            dust = ZERO
            if awaiting:
                detail = "; ".join([detail] if detail else []) + ("; " if detail else "") + "awaiting settlement: " + ", ".join(sorted(awaiting))
            explained = ""
            if ok and q_cash(cash_diff) != 0 and not awaiting:
                dust = q_cash(cash_diff)
                said: dict[str, Any] = {}
                if practice_dust:
                    said = {"detail": f"practice book: a cash difference under ${PRACTICE_DUST_USD} with every position agreeing and "
                                      f"no order in doubt, booked at once instead of freezing entries ({self._fills_since_reconcile} "
                                      f"fill(s) since the last reconciliation allowed {tolerance:.2f})"}
                elif real_dust is not None:
                    explained, spent, key = real_dust
                    said = {"detail": f"real book: a cash difference of {cash_diff:+.4f} under allocator.real_book_dust_usd (${key}) "
                                      f"with every position agreeing and no order in doubt, explained by {explained}; booked to the "
                                      "House row instead of freezing entries",
                            "unlisted_fees_usd": text(spent)}
                entry = self.ledger.append(
                    "book.fill",
                    {
                        "book": self.name,
                        "source": "dust",
                        "instrument": None,
                        "quantity": "0",
                        "price": "0",
                        "fee_usd": "0",
                        "cash_delta": text(dust),
                        "position_delta": "0",
                        "real_money": self.real_money,
                        **said,
                    },
                    agent=HOUSE,
                )
                self._apply(entry.kind, HOUSE, entry.payload, entry.at)
                if real_dust is not None:
                    # The owner is told, as the freeze used to tell them, but nothing stops.
                    self.ledger.append("ops.alert", {
                        "level": "error", "book": self.name, "dust_usd": text(dust), "real_book_dust_usd": text(real_dust[2]),
                        "text": (f"{self.name}: {dust:+.4f} of cash booked as dust on the House row, not a freeze (under "
                                 f"allocator.real_book_dust_usd ${real_dust[2]}): {explained}")[:1000]})
            self.frozen = None if ok else detail
            if ok and not awaiting:
                self._reset_since_clean()
            head_seq, head_digest = self.ledger.head()
            self.ledger.append(
                "book.reconciled",
                {
                    "book": self.name,
                    "ok": ok,
                    "cash_venue": text(venue_cash),
                    "cash_expected": text(q_cash(expected)),
                    "cash_diff": text(q_cash(cash_diff)),
                    "position_diffs": diffs,
                    "dust_booked": text(dust),
                    "detail": detail,
                    "ledger_seq": head_seq,
                    "ledger_digest": head_digest,
                    "real_money": self.real_money,
                    # H4: this reading added resting bids back at the cent, as the venue holds them.
                    "holds": "cent",
                    "attribution_issues": {name: self.evidence_integrity(name)['issues']
                                           for name in self._evidence_issues},
                },
            )
            return Reconciliation(ok, venue_cash, q_cash(expected), q_cash(cash_diff), diffs, dust, detail, explained)


def _split_cash(total: Decimal, parts: Sequence[Decimal]) -> list[Decimal]:
    """Split a venue-reported fee across the parts of a fill, to $0.0001, summing exactly."""
    whole = sum(parts, ZERO)
    if total <= 0 or whole <= 0:
        return [ZERO for _ in parts]
    grid = Decimal("0.0001")
    out = [(total * p / whole).quantize(grid, rounding=ROUND_DOWN) for p in parts]
    left = total - sum(out, ZERO)
    for i in sorted(range(len(parts)), key=lambda i: -parts[i]):
        if left <= 0:
            break
        if parts[i] > 0:
            out[i] += left
            left = ZERO
    return out


def _age_seconds(as_of: str, now: str) -> float | None:
    from ltcm.broker import instant

    a, b = instant(as_of), instant(now)
    if a is None or b is None:
        return None
    return (b - a).total_seconds()


def _epoch_seconds(now: str) -> float:
    from ltcm.broker import instant

    moment = instant(now)
    if moment is None:
        raise ValueError(f"not a timestamp: {now!r}")
    return moment.timestamp()


def _new_york_date(now: str) -> str:
    """The calendar date in New York at this instant (options expire by New York's calendar)."""
    from zoneinfo import ZoneInfo

    from ltcm.broker import instant

    moment = instant(now)
    if moment is None:
        raise ValueError(f"not a timestamp: {now!r}")
    return moment.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
