"""An append-only, recoverable paper account; it never submits brokerage orders.

All fills are explicit paper simulations at a subsequently observed bid or ask.
The caller supplies sourced market sessions, constituent snapshots and quotes.
No last-known price, missing corporate action, or benchmark is manufactured.
"""

from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from .contracts import (
    BenchmarkPoint,
    DailyBar,
    Mandate,
    MarketSession,
    Quote,
    UniverseSnapshot,
    decimal_text,
    identifier,
    number,
    record,
    source_url,
    symbol,
    timestamp,
    utc_now,
)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(value):
    return sha256(_json(value).encode()).hexdigest()


def _percentage(value):
    with localcontext() as context:
        context.prec = 80
        ratio = Decimal(value.numerator) / Decimal(value.denominator)
        return decimal_text(
            (ratio * 100).quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_EVEN)
        )


class PortfolioLedger:
    """Single-writer accounting through SQLite IMMEDIATE transactions.

    IDs are idempotency keys. Repeating identical requests returns their saved
    result. Reusing an ID for different content fails. All rows are immutable;
    restart reconstructs balances from the ordered, hash-checked event journal.
    Research can run without any membership or market-data feed. Trading cannot.
    """

    def __init__(self, path, mandate=None, *, created_at=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS paper_config (
            key TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS paper_universe (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS paper_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL, at TEXT NOT NULL, payload TEXT NOT NULL,
            previous_hash TEXT NOT NULL, digest TEXT NOT NULL);
          CREATE TRIGGER IF NOT EXISTS paper_config_no_update BEFORE UPDATE ON paper_config
            BEGIN SELECT RAISE(ABORT, 'paper config is immutable'); END;
          CREATE TRIGGER IF NOT EXISTS paper_config_no_delete BEFORE DELETE ON paper_config
            BEGIN SELECT RAISE(ABORT, 'paper config is immutable'); END;
          CREATE TRIGGER IF NOT EXISTS paper_universe_no_update BEFORE UPDATE ON paper_universe
            BEGIN SELECT RAISE(ABORT, 'membership snapshots are immutable'); END;
          CREATE TRIGGER IF NOT EXISTS paper_universe_no_delete BEFORE DELETE ON paper_universe
            BEGIN SELECT RAISE(ABORT, 'membership snapshots are immutable'); END;
          CREATE TRIGGER IF NOT EXISTS paper_events_no_update BEFORE UPDATE ON paper_events
            BEGIN SELECT RAISE(ABORT, 'paper events are immutable'); END;
          CREATE TRIGGER IF NOT EXISTS paper_events_no_delete BEFORE DELETE ON paper_events
            BEGIN SELECT RAISE(ABORT, 'paper events are immutable'); END;
        """)
        with self._transaction():
            saved = self.db.execute(
                "SELECT * FROM paper_config WHERE key='mandate'"
            ).fetchone()
            if saved:
                config = json.loads(saved["payload"])
                if _hash(config) != saved["digest"]:
                    raise ValueError("Paper mandate integrity check failed")
                self.mandate = Mandate(**config["mandate"])
                self.created_at = config["created_at"]
                if mandate is not None and mandate != self.mandate:
                    raise ValueError("The paper mandate is frozen for this account")
                if created_at is not None and created_at != self.created_at:
                    raise ValueError("The account creation time is immutable")
            else:
                self.mandate = mandate or Mandate()
                if not isinstance(self.mandate, Mandate):
                    raise ValueError("A validated Mandate is required")
                self.created_at = created_at or utc_now()
                timestamp(self.created_at)
                config = {
                    "schema_version": 1,
                    "mode": "paper",
                    "created_at": self.created_at,
                    "mandate": record(self.mandate),
                }
                self.db.execute(
                    "INSERT INTO paper_config VALUES (?,?,?)",
                    ("mandate", _json(config), _hash(config)),
                )
            self._state()

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            with localcontext() as context:
                context.prec = 80
                yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _events(self):
        previous = ""
        events = []
        for row in self.db.execute("SELECT * FROM paper_events ORDER BY sequence"):
            payload = json.loads(row["payload"])
            material = {
                "id": row["id"],
                "kind": row["kind"],
                "at": row["at"],
                "payload": payload,
                "previous_hash": previous,
            }
            if row["previous_hash"] != previous or row["digest"] != _hash(material):
                raise ValueError("Paper event journal integrity check failed")
            previous = row["digest"]
            events.append(material)
        return events

    def _append(self, event_id, kind, at, payload):
        identifier(event_id)
        timestamp(at)
        saved = self.db.execute(
            "SELECT * FROM paper_events WHERE id=?", (event_id,)
        ).fetchone()
        if saved:
            if (
                saved["kind"] != kind
                or saved["at"] != at
                or saved["payload"] != _json(payload)
            ):
                raise ValueError("An idempotency key cannot identify different content")
            return False
        last = self.db.execute(
            "SELECT at,digest FROM paper_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if timestamp(at) < timestamp(last["at"] if last else self.created_at):
            raise ValueError(
                "Events cannot be backdated before the latest account event"
            )
        previous = last["digest"] if last else ""
        material = {
            "id": event_id,
            "kind": kind,
            "at": at,
            "payload": payload,
            "previous_hash": previous,
        }
        self.db.execute(
            "INSERT INTO paper_events(id,kind,at,payload,previous_hash,digest) VALUES (?,?,?,?,?,?)",
            (event_id, kind, at, _json(payload), previous, _hash(material)),
        )
        return True

    def _saved(self, event_id, kind=None):
        row = self.db.execute(
            "SELECT kind,payload,at FROM paper_events WHERE id=?", (event_id,)
        ).fetchone()
        if row and kind is not None and row["kind"] != kind:
            raise ValueError("An idempotency key cannot identify another event type")
        return None if row is None else json.loads(row["payload"])

    def _state(self):
        state = {
            "cash": number(self.mandate.initial_cash),
            "holdings": {},
            "fees": Decimal(0),
            "deposits": Decimal(0),
            "decisions": {},
            "actions": {},
            "history": [],
            "marks": {},
            "last_equity": None,
            "last_at": self.created_at,
            "started_at": None,
            "growth": Fraction(1),
            "base_equity": None,
            "benchmarks": {},
            "fills": [],
            "last_accounting_at": self.created_at,
        }
        with localcontext() as context:
            context.prec = 80
            for event in self._events():
                kind, data = event["kind"], event["payload"]
                state["last_at"] = event["at"]
                if kind in ("rebalance", "mark", "deposit"):
                    state["last_accounting_at"] = event["at"]
                if kind == "decision":
                    state["decisions"][event["id"]] = {
                        **data,
                        "status": "pending",
                        "id": event["id"],
                    }
                elif kind == "cancel":
                    state["decisions"][data["decision_id"]]["status"] = "cancelled"
                elif kind == "rebalance":
                    for fill in data["fills"]:
                        ticker, quantity = fill["symbol"], number(fill["quantity"])
                        state["holdings"][ticker] = state["holdings"].get(
                            ticker, Decimal(0)
                        ) + (quantity if fill["side"] == "buy" else -quantity)
                        state["fees"] += number(fill["fee"])
                        state["fills"].append(fill)
                    state["holdings"] = {
                        s: q for s, q in state["holdings"].items() if q
                    }
                    state["cash"] = number(data["cash_after"])
                    state["decisions"][data["decision_id"]]["status"] = "filled"
                elif kind == "deposit":
                    cash = number(data["amount"])
                    state["cash"] += cash
                    state["deposits"] += cash
                elif kind == "action_flag":
                    state["actions"][data["symbol"]] = data
                elif kind == "benchmark":
                    state["benchmarks"][data["as_of"]] = data
                elif kind != "mark":
                    raise ValueError("Unknown paper event type")
                nav = data.get("nav")
                if nav:
                    valuation_at = nav.get("valuation_at", event["at"])
                    before_flow = number(nav["equity_before_flow"])
                    after_flow = number(nav["equity"])
                    if state["started_at"] is None:
                        state["started_at"] = valuation_at
                        state["base_equity"] = number(nav["opening_equity"])
                    if state["base_equity"] <= 0:
                        raise ValueError(
                            "A return interval requires positive opening equity"
                        )
                    state["growth"] *= Fraction(before_flow) / Fraction(
                        state["base_equity"]
                    )
                    state["base_equity"] = after_flow
                    state["last_equity"] = after_flow
                    state["marks"] = nav["prices"]
                    point = {
                        "at": valuation_at,
                        "equity": decimal_text(after_flow),
                        "time_weighted_return_pct": _percentage(state["growth"] - 1),
                        "benchmark_return_pct": None,
                    }
                    if state["history"] and state["history"][-1]["at"] == valuation_at:
                        state["history"][-1] = point
                    else:
                        state["history"].append(point)
                if state["cash"] < 0 or any(q < 0 for q in state["holdings"].values()):
                    raise ValueError(
                        "Paper accounting cannot create negative cash or short holdings"
                    )
        return state

    def register_universe(self, snapshot):
        if not isinstance(snapshot, UniverseSnapshot):
            raise ValueError("A validated UniverseSnapshot is required")
        data = record(snapshot)
        with self._transaction():
            saved = self.db.execute(
                "SELECT payload FROM paper_universe WHERE id=?", (snapshot.snapshot_id,)
            ).fetchone()
            if saved:
                if saved["payload"] != _json(data):
                    raise ValueError("Membership snapshot IDs are immutable")
                return data
            self.db.execute(
                "INSERT INTO paper_universe VALUES (?,?,?)",
                (snapshot.snapshot_id, _json(data), _hash(data)),
            )
        return data

    def _universe(self, at, requested=None):
        current = timestamp(at)
        candidates = []
        for row in self.db.execute("SELECT * FROM paper_universe"):
            data = json.loads(row["payload"])
            if _hash(data) != row["digest"]:
                raise ValueError("Membership snapshot integrity check failed")
            entry = UniverseSnapshot(**data)
            if (
                timestamp(entry.effective_at) <= current
                and timestamp(entry.captured_at)
                <= current
                < timestamp(entry.expires_at)
                and current - timestamp(entry.captured_at)
                <= timedelta(days=self.mandate.universe_max_age_days)
            ):
                candidates.append(entry)
        if not candidates:
            raise ValueError(
                "No current, previously captured S&P 500 membership snapshot is available"
            )
        selected = max(
            candidates,
            key=lambda entry: (
                entry.effective_at,
                entry.captured_at,
                entry.snapshot_id,
            ),
        )
        if requested is not None and requested != selected.snapshot_id:
            raise ValueError(
                "Decisions must use the latest effective membership snapshot available at that time"
            )
        return selected

    def propose(
        self,
        decision_id,
        *,
        decided_at,
        targets,
        universe_id,
        evidence_refs,
        rationale="",
        supersedes=None,
        expected_open_at=None,
        calendar_source=None,
    ):
        identifier(decision_id)
        timestamp(decided_at)
        identifier(universe_id)
        if not isinstance(targets, dict) or len(targets) > 550:
            raise ValueError("Targets must be a bounded symbol-to-weight mapping")
        checked = {}
        with localcontext() as context:
            context.prec = 80
            for ticker, weight in sorted(targets.items()):
                symbol(ticker)
                amount = number(weight)
                if amount > number(self.mandate.max_position_weight):
                    raise ValueError("A target exceeds the frozen position limit")
                if amount:
                    checked[ticker] = decimal_text(amount)
            if sum((number(weight) for weight in checked.values()), Decimal(0)) > 1:
                raise ValueError("Target weights cannot use leverage")
        if (
            not isinstance(evidence_refs, (tuple, list))
            or not 1 <= len(evidence_refs) <= 128
            or len(set(evidence_refs)) != len(evidence_refs)
        ):
            raise ValueError("Decisions require distinct immutable evidence references")
        refs = [identifier(ref) for ref in evidence_refs]
        if not isinstance(rationale, str) or len(rationale) > 8000:
            raise ValueError("Rationale must be bounded text")
        if expected_open_at is not None:
            if timestamp(expected_open_at) <= timestamp(decided_at):
                raise ValueError("The planned next opening must follow the decision")
            source_url(calendar_source)
        elif calendar_source is not None:
            raise ValueError("Calendar evidence requires an expected opening timestamp")
        data = {
            "decided_at": decided_at,
            "targets": checked,
            "universe_id": universe_id,
            "evidence_refs": refs,
            "rationale": rationale,
            "supersedes": supersedes,
            "expected_open_at": expected_open_at,
            "calendar_source": calendar_source,
        }
        with self._transaction():
            saved = self._saved(decision_id, "decision")
            if saved:
                if saved != data:
                    raise ValueError("Decision evidence and allocation are immutable")
                return self._state()["decisions"][decision_id]
            universe = self._universe(decided_at, universe_id)
            if any(ticker not in universe.symbols for ticker in checked):
                raise ValueError(
                    "Only current S&P 500 constituent stocks may receive target capital"
                )
            state = self._state()
            pending = [
                item
                for item in state["decisions"].values()
                if item["status"] == "pending"
            ]
            if pending:
                if len(pending) != 1 or supersedes != pending[0]["id"]:
                    raise ValueError(
                        "Explicitly supersede the outstanding target decision"
                    )
                self._append(
                    "cancel:" + _hash({"superseded_by": decision_id})[:40],
                    "cancel",
                    decided_at,
                    {
                        "decision_id": supersedes,
                        "reason": "superseded",
                        "replacement": decision_id,
                    },
                )
            elif supersedes is not None:
                raise ValueError("A replacement must identify the outstanding decision")
            self._append(decision_id, "decision", decided_at, data)
            return self._state()["decisions"][decision_id]

    def cancel(self, decision_id, *, at, cancellation_id):
        identifier(decision_id)
        identifier(cancellation_id)
        payload = {
            "decision_id": decision_id,
            "reason": "cancelled",
            "replacement": None,
        }
        with self._transaction():
            saved = self._saved(cancellation_id, "cancel")
            if saved:
                self._append(cancellation_id, "cancel", at, payload)
                return self._state()["decisions"][decision_id]
            state = self._state()
            if (
                decision_id not in state["decisions"]
                or state["decisions"][decision_id]["status"] != "pending"
            ):
                raise ValueError("Only pending decisions can be cancelled")
            self._append(cancellation_id, "cancel", at, payload)
            return self._state()["decisions"][decision_id]

    def _quotes(
        self, quotes, required, at, *, after=None, market_session=None, exact=False
    ):
        if not isinstance(quotes, (tuple, list)) or not all(
            isinstance(q, Quote) for q in quotes
        ):
            raise ValueError("Validated Quote records are required")
        by_symbol = {q.symbol: q for q in quotes}
        if len(by_symbol) != len(quotes) or set(by_symbol) != set(required):
            raise ValueError(
                "Provide exactly one synchronized quote for every required position"
            )
        now = timestamp(at)
        for quote in quotes:
            observed = timestamp(quote.as_of)
            if observed > now or now - observed > timedelta(
                seconds=self.mandate.max_quote_age_seconds
            ):
                raise ValueError(
                    "Future or stale prices cannot value or fill a paper position"
                )
            if exact and observed != now:
                raise ValueError(
                    "External funding needs quotes at the exact valuation boundary"
                )
            if after is not None and observed <= timestamp(after):
                raise ValueError(
                    "A paper fill needs a market quote strictly after the decision"
                )
            if (
                quote.corporate_actions_checked_through is None
                or timestamp(quote.corporate_actions_checked_through) < observed
                or timestamp(quote.corporate_actions_checked_through) > now
            ):
                raise ValueError(
                    "Quotes need an explicit completed corporate-action check through their timestamp"
                )
            if market_session is not None:
                if quote.session != "regular" or not timestamp(
                    market_session.opens_at
                ) <= observed < timestamp(market_session.closes_at):
                    raise ValueError(
                        "A paper fill requires a quote inside a sourced regular market session"
                    )
        times = [timestamp(q.as_of) for q in quotes]
        if times and max(times) - min(times) > timedelta(
            seconds=self.mandate.max_quote_skew_seconds
        ):
            raise ValueError("Quote timestamps are not sufficiently synchronized")
        return by_symbol

    def _action_guard(self, state, required, at):
        if any(
            s in required and timestamp(action["effective_at"]) <= timestamp(at)
            for s, action in state["actions"].items()
        ):
            raise ValueError(
                "An unresolved corporate action blocks affected marks and fills"
            )

    @staticmethod
    def _equity(cash, holdings, quotes):
        return cash + sum(
            (
                quantity * number(quotes[ticker].last)
                for ticker, quantity in holdings.items()
            ),
            Decimal(0),
        )

    @staticmethod
    def _nav(equity, opening_equity, quotes, before_flow=None):
        return {
            "equity": decimal_text(equity),
            "opening_equity": decimal_text(opening_equity),
            "equity_before_flow": decimal_text(
                equity if before_flow is None else before_flow
            ),
            "prices": {
                ticker: {
                    "price": quote.last,
                    "as_of": quote.as_of,
                    "source": quote.source,
                }
                for ticker, quote in sorted(quotes.items())
            },
        }

    def fill_pending(
        self,
        decision_id,
        *,
        quotes,
        now,
        market_session,
        fee_per_order="0",
        _daily_bars=None,
    ):
        """Atomically simulate a rebalance; a market-data failure leaves intent pending.

        Buys use ask, sells use bid, fees reduce cash. Whole-share rounding is
        conservative. Simulated fills do not claim liquidity or actual execution.
        """
        identifier(decision_id)
        timestamp(now)
        if not isinstance(market_session, MarketSession):
            raise ValueError("An explicit sourced market calendar session is required")
        fee = number(fee_per_order)
        event_id = "fill:" + _hash({"decision_id": decision_id})[:40]
        with self._transaction():
            saved = self._saved(event_id, "rebalance")
            if saved:
                return saved
            if _daily_bars is None and not timestamp(
                market_session.opens_at
            ) <= timestamp(now) < timestamp(market_session.closes_at):
                raise ValueError("Market is closed; the allocation remains pending")
            state = self._state()
            decision = state["decisions"].get(decision_id)
            if decision is None or decision["status"] != "pending":
                raise ValueError("Only a pending decision can produce fills")
            valuation_at = market_session.opens_at if _daily_bars is not None else now
            if _daily_bars is not None:
                if decision.get("expected_open_at") != market_session.opens_at:
                    raise ValueError(
                        "A daily-bar fill must use the next opening frozen with the decision"
                    )
                if timestamp(state["last_accounting_at"]) > timestamp(valuation_at):
                    raise ValueError(
                        "Intervening accounting prevents retroactive opening execution"
                    )
            universe = self._universe(valuation_at)
            if any(ticker not in universe.symbols for ticker in decision["targets"]):
                raise ValueError(
                    "A target left the S&P 500 before execution; revise the decision"
                )
            required = set(state["holdings"]) | set(decision["targets"])
            self._action_guard(state, required, now)
            quote_map = self._quotes(
                quotes,
                required,
                valuation_at,
                after=decision["decided_at"],
                market_session=market_session,
            )
            opening = self._equity(state["cash"], state["holdings"], quote_map)
            quantum = Decimal(1).scaleb(-self.mandate.share_decimals)
            # Reserve all possible per-order fees before assigning any capital.
            available_nav = opening - fee * len(required)
            if available_nav <= 0:
                raise ValueError("Trading fees exhaust the virtual portfolio")
            targets = {}
            for ticker in sorted(required):
                weight = number(decision["targets"].get(ticker, "0"))
                # Use the greater of ask and last to preserve a marked-value cap.
                divisor = max(
                    number(quote_map[ticker].ask), number(quote_map[ticker].last)
                )
                targets[ticker] = (available_nav * weight / divisor).quantize(
                    quantum, rounding=ROUND_FLOOR
                )
            fills = []
            cash = state["cash"]
            holdings = dict(state["holdings"])
            # Sell first, with every leg committed in the same SQLite transaction.
            changes = [
                (ticker, targets[ticker] - holdings.get(ticker, Decimal(0)))
                for ticker in sorted(required)
            ]
            changes.sort(key=lambda item: (item[1] >= 0, item[0]))
            for ticker, delta in changes:
                if delta == 0:
                    continue
                side = "buy" if delta > 0 else "sell"
                quantity = abs(delta)
                price = number(
                    quote_map[ticker].ask if side == "buy" else quote_map[ticker].bid
                )
                if side == "buy":
                    affordable = ((cash - fee) / price).quantize(
                        quantum, rounding=ROUND_FLOOR
                    )
                    quantity = min(quantity, max(Decimal(0), affordable))
                    if quantity == 0:
                        continue
                notion = quantity * price
                cash += -notion - fee if side == "buy" else notion - fee
                holdings[ticker] = holdings.get(ticker, Decimal(0)) + (
                    quantity if side == "buy" else -quantity
                )
                intent = {
                    "decision_id": decision_id,
                    "symbol": ticker,
                    "side": side,
                    "quantity": decimal_text(quantity),
                }
                fills.append(
                    {
                        "order_id": "order:" + _hash(intent)[:40],
                        "fill_id": "paper:" + _hash(intent)[:40],
                        **intent,
                        "price": decimal_text(price),
                        "fee": decimal_text(fee),
                        "quote_at": quote_map[ticker].as_of,
                        "source": quote_map[ticker].source,
                    }
                )
            holdings = {
                ticker: quantity for ticker, quantity in holdings.items() if quantity
            }
            ending = self._equity(cash, holdings, quote_map)
            if cash < 0 or ending <= 0:
                raise ValueError(
                    "A simulated rebalance cannot create leverage or nonpositive equity"
                )
            # Spreads/fees can move final weights beyond the requested cap. Fail
            # closed instead of quietly widening the frozen allocation mandate.
            cap = number(self.mandate.max_position_weight)
            if any(
                quantity * number(quote_map[ticker].last) > ending * cap
                for ticker, quantity in holdings.items()
            ):
                raise ValueError(
                    "Execution costs would breach the final marked position limit; reduce the targets"
                )
            payload = {
                "decision_id": decision_id,
                "universe_id": universe.snapshot_id,
                "session": record(market_session),
                "quotes": []
                if _daily_bars is not None
                else [record(q) for q in quotes],
                "bars": [record(bar) for bar in _daily_bars]
                if _daily_bars is not None
                else [],
                "execution_model": "next_open_fixed_slippage"
                if _daily_bars is not None
                else "subsequent_bid_ask",
                "simulated": True,
                "slippage_bps": self.mandate.open_slippage_bps
                if _daily_bars is not None
                else None,
                "fills": fills,
                "cash_before": decimal_text(state["cash"]),
                "cash_after": decimal_text(cash),
                "nav": self._nav(
                    ending,
                    opening,
                    {s: q for s, q in quote_map.items() if s in holdings},
                ),
            }
            payload["nav"]["valuation_at"] = valuation_at
            self._append(event_id, "rebalance", now, payload)
            self._state()
            return payload

    def fill_at_next_open(
        self, decision_id, *, bars, now, market_session, fee_per_order="0"
    ):
        """Use the precommitted next session's observed open, plus fixed slippage.

        A sourced daily bar may arrive after the opening. Only the open affects
        allocation and simulated execution; later high/low/close never do. The
        journal distinguishes receipt time from its effective opening valuation.
        """
        timestamp(now)
        if not isinstance(market_session, MarketSession):
            raise ValueError("A sourced next market session is required")
        if not isinstance(bars, (tuple, list)) or not all(
            isinstance(bar, DailyBar) for bar in bars
        ):
            raise ValueError("Validated DailyBar records are required")
        if timestamp(now) < timestamp(market_session.opens_at):
            raise ValueError("Market has not opened; the allocation remains pending")
        modeled_quotes = []
        with localcontext() as context:
            context.prec = 80
            slippage = number(self.mandate.open_slippage_bps) / 10000
            for bar in bars:
                observed = timestamp(bar.observed_at)
                if (
                    bar.opens_at != market_session.opens_at
                    or observed > timestamp(now)
                    or timestamp(now) - observed
                    > timedelta(seconds=self.mandate.max_quote_age_seconds)
                ):
                    raise ValueError(
                        "Require a freshly captured bar for the precommitted opening"
                    )
                if bar.corporate_actions_checked_through is None or not timestamp(
                    bar.opens_at
                ) <= timestamp(bar.corporate_actions_checked_through) <= timestamp(now):
                    raise ValueError(
                        "Opening bars need an explicit corporate-action check through the opening"
                    )
                opening = number(bar.open)
                # Modeled prices use declared eight-decimal half-even rounding.
                bid = (opening * (1 - slippage)).quantize(
                    Decimal("0.00000001"), rounding=ROUND_HALF_EVEN
                )
                ask = (opening * (1 + slippage)).quantize(
                    Decimal("0.00000001"), rounding=ROUND_HALF_EVEN
                )
                modeled_quotes.append(
                    Quote(
                        symbol=bar.symbol,
                        bid=decimal_text(bid),
                        ask=decimal_text(ask),
                        last=bar.open,
                        as_of=bar.opens_at,
                        source=bar.source,
                        corporate_actions_checked_through=bar.opens_at,
                    )
                )
        return self.fill_pending(
            decision_id,
            quotes=modeled_quotes,
            now=now,
            market_session=market_session,
            fee_per_order=fee_per_order,
            _daily_bars=bars,
        )

    def mark(
        self,
        quotes,
        *,
        observed_at,
        mark_id=None,
        benchmark=None,
        _daily_bars=None,
        _session=None,
    ):
        timestamp(observed_at)
        mark_id = mark_id or "mark:" + observed_at
        identifier(mark_id)
        with self._transaction():
            state = self._state()
            self._action_guard(state, set(state["holdings"]), observed_at)
            valuation_at = _session.closes_at if _session is not None else observed_at
            if timestamp(valuation_at) < timestamp(self.created_at):
                raise ValueError("A market valuation cannot precede this paper account")
            if state["history"] and timestamp(valuation_at) < timestamp(
                state["history"][-1]["at"]
            ):
                raise ValueError(
                    "Valuations cannot precede the last recorded market observation"
                )
            quote_map = self._quotes(quotes, set(state["holdings"]), valuation_at)
            equity = self._equity(state["cash"], state["holdings"], quote_map)
            payload = {
                "quotes": []
                if _daily_bars is not None
                else [record(q) for q in quotes],
                "bars": [record(bar) for bar in _daily_bars]
                if _daily_bars is not None
                else [],
                "valuation_model": "daily_close"
                if _daily_bars is not None
                else "observed_last",
                "nav": self._nav(equity, equity, quote_map),
            }
            payload["nav"]["valuation_at"] = valuation_at
            self._append(mark_id, "mark", observed_at, payload)
            if benchmark is not None:
                self._record_benchmark(benchmark, recorded_at=observed_at)
            return self._public(self._state())

    def establish_cash_baseline(self, *, market_session, benchmark, observed_at):
        """Value known opening cash against an actually observed index opening.

        This is neither a trade nor a reconstructed position. Once investment
        history exists it cannot move the start boundary or rewrite returns.
        """
        timestamp(observed_at)
        if (not isinstance(market_session, MarketSession)
            or not isinstance(benchmark, BenchmarkPoint)
            or benchmark.as_of != market_session.opens_at
            or timestamp(benchmark.captured_at) > timestamp(observed_at)
            or not timestamp(self.created_at) <= timestamp(market_session.opens_at) <= timestamp(observed_at)):
            raise ValueError("Opening cash baseline requires an observed aligned index opening")
        with self._transaction():
            state = self._state()
            if state["history"]:
                return self._public(state)
            due_pending = any(d["status"] == "pending" and (
                not d.get("expected_open_at") or timestamp(d["expected_open_at"]) <= timestamp(observed_at)
            ) for d in state["decisions"].values())
            if state["holdings"] or state["actions"] or due_pending:
                raise ValueError("Only an uninvested cash account has a known opening baseline")
            nav = self._nav(state["cash"], state["cash"], {})
            nav["valuation_at"] = market_session.opens_at
            self._append("opening-cash:"+market_session.opens_at, "mark", observed_at,
                         {"quotes": [], "bars": [], "valuation_model": "opening_cash_baseline",
                          "calendar_source": market_session.source, "nav": nav})
            self._record_benchmark(benchmark, recorded_at=observed_at)
            return self._public(self._state())

    def mark_daily_close(self, bars, *, observed_at, market_session, benchmark=None):
        """Record an observed, completed session close without inventing quotes."""
        timestamp(observed_at)
        if not isinstance(market_session, MarketSession) or timestamp(
            observed_at
        ) < timestamp(market_session.closes_at):
            raise ValueError(
                "A completed sourced market session is required for closing valuation"
            )
        if not isinstance(bars, (tuple, list)) or not all(
            isinstance(bar, DailyBar) for bar in bars
        ):
            raise ValueError("Validated DailyBar records are required")
        prices = []
        for bar in bars:
            if (
                bar.opens_at != market_session.opens_at
                or not timestamp(market_session.closes_at)
                <= timestamp(bar.observed_at)
                <= timestamp(observed_at)
                or timestamp(observed_at) - timestamp(bar.observed_at)
                > timedelta(seconds=self.mandate.max_quote_age_seconds)
            ):
                raise ValueError(
                    "Closing bars require fresh capture after the same session has ended"
                )
            if bar.corporate_actions_checked_through is None or not timestamp(
                market_session.closes_at
            ) <= timestamp(bar.corporate_actions_checked_through) <= timestamp(
                observed_at
            ):
                raise ValueError(
                    "Closing bars need a corporate-action check through the close"
                )
            prices.append(
                Quote(
                    symbol=bar.symbol,
                    bid=bar.close,
                    ask=bar.close,
                    last=bar.close,
                    as_of=market_session.closes_at,
                    source=bar.source,
                    corporate_actions_checked_through=market_session.closes_at,
                )
            )
        return self.mark(
            prices,
            observed_at=observed_at,
            mark_id="close:" + market_session.closes_at,
            benchmark=benchmark,
            _daily_bars=bars,
            _session=market_session,
        )

    def deposit(self, amount, *, external_id, at, quotes=()):
        """Add virtual funding, with exact before/after valuations when invested."""
        cash = number(amount, positive=True)
        identifier(external_id)
        timestamp(at)
        event_id = "deposit:" + external_id
        with self._transaction():
            saved = self._saved(event_id, "deposit")
            if saved:
                row = self.db.execute(
                    "SELECT at FROM paper_events WHERE id=?", (event_id,)
                ).fetchone()
                if saved["amount"] != decimal_text(cash) or row["at"] != at:
                    raise ValueError("A deposit ID cannot identify different funding")
                return self._public(self._state())
            state = self._state()
            self._action_guard(state, set(state["holdings"]), at)
            quote_map = self._quotes(quotes, set(state["holdings"]), at, exact=True)
            before = self._equity(state["cash"], state["holdings"], quote_map)
            payload = {
                "amount": decimal_text(cash),
                "quotes": [record(q) for q in quotes],
                "nav": self._nav(before + cash, before, quote_map, before_flow=before)
                if state["started_at"] is not None or state["holdings"]
                else None,
            }
            self._append(event_id, "deposit", at, payload)
            return self._public(self._state())

    def flag_corporate_action(
        self, ticker, *, action_id, effective_at, observed_at, source
    ):
        """Suspend an affected symbol until a supported, explicit action adapter exists.

        Dividend entitlement, splits, mergers and delistings are not silently
        treated as price returns. This version deliberately cannot clear a flag.
        """
        symbol(ticker)
        identifier(action_id)
        timestamp(effective_at)
        source_url(source)
        data = {
            "symbol": ticker,
            "action_id": action_id,
            "effective_at": effective_at,
            "source": source,
        }
        with self._transaction():
            self._append("action:" + action_id, "action_flag", observed_at, data)
        return data

    def _record_benchmark(self, point, *, recorded_at):
        if not isinstance(point, BenchmarkPoint):
            raise ValueError("A validated BenchmarkPoint is required")
        state = self._state()
        if point.as_of not in {entry["at"] for entry in state["history"]}:
            raise ValueError(
                "Benchmark timestamps must match actual portfolio valuation boundaries"
            )
        if timestamp(point.captured_at) > timestamp(recorded_at):
            raise ValueError(
                "A benchmark cannot be recorded before its data is captured"
            )
        self._append(
            "benchmark:" + point.as_of, "benchmark", recorded_at, record(point)
        )

    def record_benchmark(self, point, *, recorded_at):
        """Attach an identified total-return point; never substitute a price index."""
        with self._transaction():
            self._record_benchmark(point, recorded_at=recorded_at)
            return self._public(self._state())

    def events(self):
        """Private audit record, including source metadata and decision rationale."""
        with localcontext() as context:
            context.prec = 80
            return self._events()

    def public_state(self):
        with localcontext() as context:
            context.prec = 80
            return self._public(self._state())

    def _public(self, state):
        pending = [
            value
            for value in state["decisions"].values()
            if value["status"] == "pending"
        ]
        blocked = any(
            ticker in state["holdings"]
            and timestamp(action["effective_at"]) <= timestamp(state["last_at"])
            for ticker, action in state["actions"].items()
        )
        holdings = []
        for ticker, quantity in sorted(state["holdings"].items()):
            price = None if blocked else state["marks"].get(ticker, {}).get("price")
            holdings.append(
                {
                    "symbol": ticker,
                    "quantity": decimal_text(quantity),
                    "price": price,
                    "market_value": decimal_text(quantity * number(price))
                    if price
                    else None,
                }
            )
        equity = (
            (None if blocked else state["last_equity"]) if holdings else state["cash"]
        )
        history = [dict(point) for point in state["history"]]
        baseline = state["benchmarks"].get(state["started_at"])
        if baseline:
            for point in history:
                index = state["benchmarks"].get(point["at"])
                if index:
                    point["benchmark_return_pct"] = _percentage(
                        Fraction(number(index["value"]))
                        / Fraction(number(baseline["value"]))
                        - 1
                    )
        benchmark_return = history[-1]["benchmark_return_pct"] if history else None
        twr = (
            _percentage(state["growth"] - 1)
            if state["started_at"] is not None and not blocked
            else None
        )
        excess = None
        if twr is not None and benchmark_return is not None:
            closing_index = state["benchmarks"][history[-1]["at"]]
            benchmark_growth = Fraction(number(closing_index["value"])) / Fraction(
                number(baseline["value"])
            )
            excess = _percentage(state["growth"] - benchmark_growth)
        return {
            "schema_version": 1,
            "mode": "paper",
            "currency": "USD",
            "status": "suspended"
            if blocked
            else "pending"
            if pending
            else "invested"
            if holdings
            else "cash",
            "created_at": self.created_at,
            "as_of": history[-1]["at"] if history else state["last_at"],
            "initial_cash": decimal_text(number(self.mandate.initial_cash)),
            "cash": decimal_text(state["cash"]),
            "equity": decimal_text(equity) if equity is not None else None,
            "net_deposits": decimal_text(state["deposits"]),
            "trading_fees": decimal_text(state["fees"]),
            "holdings": holdings,
            "pending_decisions": [
                {
                    "id": item["id"],
                    "decided_at": item["decided_at"],
                    "targets": [
                        {"symbol": ticker, "weight": weight}
                        for ticker, weight in sorted(item["targets"].items())
                    ],
                    "evidence_count": len(item["evidence_refs"]),
                }
                for item in pending
            ],
            "performance": {
                "started_at": state["started_at"],
                "time_weighted_return_pct": twr,
                "investment_pnl": (
                    decimal_text(
                        equity - number(self.mandate.initial_cash) - state["deposits"]
                    )
                    if state["started_at"] is not None and equity is not None
                    else None
                ),
                "benchmark": {
                    "name": "S&P 500 Total Return",
                    "status": "available"
                    if benchmark_return is not None
                    else "unavailable",
                    "return_pct": benchmark_return,
                    "excess_return_percentage_points": excess,
                },
            },
            "history": history,
        }
