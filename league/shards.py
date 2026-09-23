"""Collateral on every Kalshi exchange shard the League trades (U2, Sept 23, 2026).

Kalshi runs its markets on several exchange shards: crypto and commodities on 2, exotics on 1,
MLB, WNBA, tennis and (since Sept 10, 2026) basketball on 3, everything else on 0. An order on a
shard with no collateral fails with HTTP 404 `insufficient_shard_balance`. Measured Sept 23,
2026: the sports bunt meriwether-h2d625d's first real orders (12:58Z and 13:30Z) were refused
that way. Shard 3 was funded by hand ($30 at 13:50Z, $1 at 16:27Z); at 16:27Z the account held
shard 0 $372.81, shard 2 $36.60, shard 3 $22.77, plus $83 of positions. The first run's service
funded shards 0 and 2 hourly from a fixed list (`ltcm/service.py` `_fund_kalshi_shards`); the
League had no shard code at all.

`ShardFunder` is the House's mover. Once an hour, and at once after a refusal, OFF the tick (its
own background lane, never behind a Merton pass or the backup, never under the lifecycle lock),
a pass:

1. reads the cash per shard (`KalshiBroker.shard_balances`, `GET /portfolio/balance`);
2. works out the WANTED shards from the venue's own data, never a fixed list: the
   `exchange_index` of the open markets the living Kalshi desks are offered (their NEEDS series,
   read through the House's shared listing cache), plus every shard holding a real position or a
   resting real order;
3. tops up every wanted shard under `FLOOR_USD` with `TOP_UP_USD` from the richest other shard
   that keeps its own floor and the stakes of the desks that trade there;
4. records each move as an `ops.alert` carrying the transfer id, the amount, the shards and the
   balances before and after (a cross-shard move runs in up to three steps that are not undone on
   failure, so the balances are read again after every move, failed or not).

Bounds (docs/goals/LTCM_LEARN_AND_UNBLOCK.md, U2): only the gateway's one allowed funds move
(`POST /portfolio/intra_exchange_instance_transfer`, between shards of the owner's own account,
so money never leaves the account); at most `MAX_MOVE_USD` a move and `MAX_DAY_USD` a rolling day,
counted from the ledger so a restart does not reset it (a move whose outcome is unknown counts,
only a definite rejection does not); a shard is never drawn below the stakes of the desks that
trade there (a stake whose shard cannot be told is kept on every shard); nothing moves while the
kill switch is engaged, the grant is inactive, the House is paused or the real Kalshi book is
frozen, read again before every move. A failed move is a warning alert and backs that shard off
for `BACKOFF_SECONDS`; a blocked or failed pass tries again in `BLOCKED_RETRY_SECONDS`.

The invariant (workstream B): a real Kalshi order refused with `insufficient_shard_balance` raises
a warning alert at once naming the agent, the market and the shard, and a funding pass is
scheduled for that shard. The `book.order` rows are scanned incrementally from a saved cursor on
every tick, never the whole ledger.

A money mover, in `ci.FORBIDDEN`: only the owner's deploy changes it.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ltcm.broker import RejectedOrder

from .ledger import HOUSE, now_iso

ZERO = Decimal(0)
CENT = Decimal("0.01")

#: A shard under this is topped up. A Kalshi bunt is staked $10 with a $5 position cap
#: (constitution `allocator.bunt_usd`, `position_share`), so $20 covers two bunts entering on one
#: shard between hourly passes; the first run used $40 when every stake was $25.
FLOOR_USD = Decimal("20")
#: What one top-up moves: the hand move of 13:50Z on Sept 23, 2026, which carried the sports bunt
#: through its first afternoon; three bunts' stakes.
TOP_UP_USD = Decimal("30")
#: What shard 0, the home shard, keeps after donating: the first run's keep, six bunts' stakes.
#: Any other donor keeps at least its own floor. Both are raised to the stakes of the desks that
#: trade on the donor (`stakes_by_shard`).
KEEP_USD = Decimal("60")
#: The plan's bounds: at most $100 a move and $200 a rolling day, unless a run record gives a
#: measured reason (docs/goals/LTCM_LEARN_AND_UNBLOCK.md, U2).
MAX_MOVE_USD = Decimal("100")
MAX_DAY_USD = Decimal("200")
#: Below this a move is not worth a three-step transfer that cannot be undone: one bunt position.
MIN_MOVE_USD = Decimal("5")
#: The home shard: where deposits land and where every unattributed stake is counted.
HOME_SHARD = 0
INTERVAL_SECONDS = 3600.0
BACKOFF_SECONDS = 3600.0
#: A pass that was blocked (the real book frozen for a moment at startup, a pause, the kill
#: switch) or failed tries again this soon, not in an hour; the shards a refusal asked for wait.
BLOCKED_RETRY_SECONDS = 300.0
DAY_SECONDS = 86400.0
#: How old the House's shared listing of a desk's series may be for the wanted set: a shard does
#: not move between an hourly pass and the next, and a fresh read of every desk's series is what
#: drew HTTP 429 on Sept 19, 2026.
LISTING_MAX_AGE = 3600.0
#: The venue's refusal (`ltcm/adapters/kalshi.py`): the code, and the message it came with on
#: Sept 23, 2026 ("Exchange user not found ... Exchange Sharding").
REFUSAL_MARKERS = ("insufficient_shard_balance", "exchange sharding")
#: The book whose orders and stakes are real Kalshi money.
REAL_BOOK = "kalshi"
#: The House's background key: its own lane (`House._background`), so a pass a refusal asked for
#: never waits behind a Merton pass, the backup or a repair on the ops lane.
JOB = "shards:fund"


def _epoch(stamp: str) -> float:
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(epoch * 1000) % 1000:03d}Z"


def series_of(ticker: str) -> str:
    """The series a market ticker belongs to: `KXMLBTOTAL-26SEP231840STLPIT-8` -> `KXMLBTOTAL`."""
    return str(ticker or "").strip().upper().split("-")[0]


def is_shard_refusal(reason: str) -> bool:
    text = str(reason or "").lower()
    return any(marker in text for marker in REFUSAL_MARKERS)


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - a venue field that is not a number holds nothing
        return ZERO


def _text(balances: Mapping[int, Decimal]) -> dict[str, str]:
    return {str(k): f"{v:.2f}" for k, v in sorted(balances.items())}


class ShardFunder:
    """The House's Kalshi shard funder. `tick()` runs on the tick thread and makes no venue call;
    `run()` is the funding pass, scheduled on the House's ops lane."""

    def __init__(self, house: Any, root: str | Path, *, clock: Callable[[], float] | None = None):
        self.house = house
        self.clock = clock or house.clock
        self.path = Path(root) / "shards.json"
        self._lock = threading.RLock()
        self.state = self._load()
        if self.state.get("cursor") is None:
            # The refusal scan starts at the ledger's head when the funder first exists: the
            # refusals before it (12:58Z and 13:30Z on Sept 23, 2026) were handled by hand, and the
            # whole ledger is never scanned.
            try:
                self.state["cursor"] = int(house.ledger.head()[0] or 0)
                self._save()
            except Exception:  # noqa: BLE001 - set on the first scan instead
                pass

    # ------------------------------------------------------------------ state
    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        state.setdefault("cursor", None)  # the last `book.order` row scanned for a shard refusal
        state.setdefault("moves_after", 0)  # the last alert row older than the rolling day (`moved_in_day`)
        state.setdefault("last_check", None)
        state.setdefault("last_check_epoch", 0.0)
        state.setdefault("backoff", {})  # shard -> epoch until which it is not funded again
        state.setdefault("series", {})  # series -> shard, learned from listings carrying `exchange_index`
        state.setdefault("balances", {})
        state.setdefault("wanted", [])
        state.setdefault("unmapped", [])
        state.setdefault("requested", [])  # shards a refusal asked to fund before the next hourly pass
        state.setdefault("pending", [])  # requested shards a blocked or failed pass could not fund yet
        state.setdefault("moved_24h_usd", "0.00")
        state.setdefault("unattributed_usd", "0.00")  # real stakes whose shard cannot be told: kept on every donor
        state.setdefault("blocked", None)
        state.setdefault("last_error", None)
        state.setdefault("told", {})  # what was said and when, so a standing shortfall is told hourly
        return state

    def _save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path)

    def book(self) -> Any | None:
        books = getattr(self.house, "books", None) or {}
        book = books.get(REAL_BOOK)
        return book if book is not None and getattr(book, "real_money", False) else None

    # ------------------------------------------------------------- the tick
    def tick(self) -> bool:
        """Every tick, cheaply: scan the new order rows for a shard refusal, and schedule the
        funding pass when it is due or a refusal asked for one. Never raises."""
        try:
            self.scan_refusals()
        except Exception as exc:  # noqa: BLE001 - the scan runs again next tick from its cursor
            self._alert("warning", f"kalshi shard refusal scan failed ({type(exc).__name__}: {str(exc)[:160]})")
        if not self.due():
            return False
        schedule = getattr(self.house, "_background", None)
        return bool(schedule(JOB, self.run)) if callable(schedule) else False

    def due(self, now: float | None = None) -> bool:
        now = self.clock() if now is None else now
        with self._lock:
            if self.state.get("requested"):
                return True
            return now - float(self.state.get("last_check_epoch") or 0.0) >= INTERVAL_SECONDS

    def request(self, shard: int | None) -> None:
        """Ask for a pass before the next hourly one (a refusal); `None` asks for a pass whose
        target is not known, which re-reads the balances and funds whatever is wanted and short."""
        with self._lock:
            wanted = list(self.state.get("requested") or [])
            key = -1 if shard is None else int(shard)
            if key not in wanted:
                wanted.append(key)
            self.state["requested"] = wanted
            self._save()

    def scan_refusals(self) -> list[dict[str, Any]]:
        """The invariant: a real Kalshi order the venue refused for want of shard collateral is
        told at once, and its shard is funded before the next hourly pass."""
        book = self.book()
        ledger = self.house.ledger
        with self._lock:
            cursor = self.state.get("cursor")
            if cursor is None:
                cursor = int(ledger.head()[0] or 0)
                self.state["cursor"] = cursor
                self._save()
        if book is None:
            return []
        found: list[dict[str, Any]] = []
        rows = ledger.read(kinds="book.order", after=int(cursor), limit=2000)
        for entry in rows:
            payload = entry.payload or {}
            if payload.get("book") != book.name or payload.get("status") != "rejected":
                continue
            if not is_shard_refusal(payload.get("reason")):
                continue
            instrument = payload.get("instrument") or {}
            ticker = str(instrument.get("market_id") or instrument.get("symbol") or "").upper()
            agents = sorted({str(s.get("agent")) for s in (payload.get("shares") or []) if isinstance(s, dict) and s.get("agent")})
            shard = self.shard_of(ticker)
            found.append({"agent": agents, "market": ticker, "shard": shard, "seq": entry.seq})
            where = f"shard {shard}" if shard is not None else f"a shard no listing has named for {series_of(ticker)}"
            self._alert("warning", f"kalshi shard refusal: {', '.join(agents) or 'an agent'}'s real order on {ticker} was refused "
                                   f"with insufficient_shard_balance ({where}); a funding pass is scheduled")
            self.request(shard)
        if rows:
            with self._lock:
                self.state["cursor"] = rows[-1].seq
                self._save()
        return found

    # --------------------------------------------------------- what is wanted
    def shard_of(self, ticker: str) -> int | None:
        known = self.state.get("series") or {}
        value = known.get(series_of(ticker))
        return None if value is None else int(value)

    def _learn(self, rows: Iterable[Mapping[str, Any]], unmapped: set[str]) -> set[int]:
        shards: set[int] = set()
        with self._lock:
            known = self.state.setdefault("series", {})
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                series = str(row.get("series") or series_of(str(row.get("market") or ""))).upper()
                index = row.get("exchange_index")
                try:
                    shard = int(index)
                except (TypeError, ValueError):
                    if series:
                        unmapped.add(series)
                    continue
                shards.add(shard)
                if series:
                    known[series] = shard
        return shards

    def _kalshi_agents(self) -> list[Any]:
        registry = getattr(self.house, "registry", None)
        living = registry.living() if registry is not None else []
        return [a for a in living if getattr(a, "venue", None) == "kalshi"]

    def _series_of_agent(self, agent: Any) -> list[str]:
        needs = getattr(agent, "needs", None) or {}
        return [str(s).strip().upper() for s in (needs.get("series") or []) if str(s).strip()][:12]

    def wanted(self) -> tuple[set[int], set[str], list[str]]:
        """The shards to keep funded, from the venue's data: (shards, series or tickers whose shard
        no listing has named, listing errors)."""
        shards: set[int] = set()
        unmapped: set[str] = set()
        errors: list[str] = []
        for agent in self._kalshi_agents():
            series = self._series_of_agent(agent)
            if not series:
                continue
            needs = getattr(agent, "needs", None) or {}
            hours = float(needs.get("max_hours_to_close") or 24)
            try:
                rows = self.house._markets(series, hours, LISTING_MAX_AGE)
            except Exception as exc:  # noqa: BLE001 - a listing that is down is not a reason to move nothing
                errors.append(f"{','.join(series)}: {type(exc).__name__}")
                continue
            shards |= self._learn(rows or [], unmapped)
        book = self.book()
        if book is not None:
            for ticker in self._held_tickers(book):
                shard = self.shard_of(ticker)
                if shard is None:
                    unmapped.add(ticker)
                else:
                    shards.add(shard)
        return shards, unmapped, errors

    @staticmethod
    def _held_tickers(book: Any) -> set[str]:
        tickers: set[str] = set()
        for agent_id in book.agents():
            account = book.account(agent_id)
            for holding in (getattr(account, "holdings", None) or {}).values():
                if getattr(holding, "quantity", ZERO):
                    inst = holding.instrument
                    tickers.add(str(inst.market_id or inst.symbol).upper())
        for working in book.open_orders():
            inst = working.instrument
            tickers.add(str(inst.market_id or inst.symbol).upper())
        return tickers

    def stakes_by_shard(self, book: Any) -> tuple[dict[int, Decimal], Decimal]:
        """What each shard must keep for the desks that trade there: the real book's stakes,
        attributed by the shards of each agent's NEEDS series through the learned map, and the
        stakes that cannot be attributed. An agent whose series span several shards counts on
        each of them. A stake whose shard cannot be told (a series no listing has named yet, an
        agent no longer in the registry, no series at all) is returned apart, and EVERY donor
        keeps it: nobody knows which shard it is on, so no shard may be drawn as if it were
        elsewhere. (Counting it on shard 0 alone, as first built, let a small shard whose desks'
        listing was down for one pass be drained to its floor below those desks' stakes.)"""
        out: dict[int, Decimal] = {}
        unattributed = ZERO
        registry = getattr(self.house, "registry", None)
        for agent_id in book.agents():
            if agent_id == HOUSE:
                continue
            staked = _money(getattr(book.account(agent_id), "staked", ZERO))
            if staked <= 0:
                continue
            agent = registry.get(agent_id) if registry is not None else None
            shards = {self.shard_of(series) for series in (self._series_of_agent(agent) if agent is not None else [])}
            if agent is None or not shards or None in shards:
                unattributed += staked
                continue
            for shard in shards:
                out[shard] = out.get(shard, ZERO) + staked  # type: ignore[index]
        return out, unattributed

    # ------------------------------------------------------------- the pass
    def blocked(self) -> str | None:
        """Why nothing may move now, or None."""
        house = self.house
        switch = getattr(house, "kill_switch", None)
        try:
            if callable(switch) and switch():
                return "the kill switch is engaged"
        except Exception as exc:  # noqa: BLE001 - a switch that cannot be read is engaged
            return f"the kill switch cannot be read ({type(exc).__name__})"
        campaigns = getattr(house, "campaigns", None)
        grant = campaigns.live_authorization() if campaigns is not None else None
        if not grant or grant.get("active") is False or grant.get("revoked"):
            return "no live grant is active"
        try:
            if house.paused():
                return "the House is paused"
        except Exception:  # noqa: BLE001
            return "the pause file cannot be read"
        book = self.book()
        if book is None:
            return "there is no real Kalshi book"
        if getattr(book, "frozen", None):
            return f"the real Kalshi book is frozen ({str(book.frozen)[:120]})"
        return None

    def moved_in_day(self, now: float | None = None) -> Decimal:
        """Dollars moved in the rolling day, from the ledger's own `ops.alert` move rows (so a
        restart does not reset the day's cap). The scan starts after the last alert older than
        the window and advances with it."""
        now = self.clock() if now is None else now
        start = now - DAY_SECONDS
        total = ZERO
        with self._lock:
            after = int(self.state.get("moves_after") or 0)
        last_old = after
        for entry in self.house.ledger.iter(kinds="ops.alert", after=after):
            if _epoch(entry.at) < start:
                last_old = entry.seq
                continue
            move = (entry.payload or {}).get("shard_move")
            # A move that succeeded, and one whose outcome is unknown (a gateway or transport
            # failure after a request the venue may have executed): only a definite rejection
            # counts nothing. Rows from before `counted` existed carry `ok` alone.
            if isinstance(move, dict) and move.get("counted", move.get("ok")):
                total += _money(move.get("usd"))
        with self._lock:
            self.state["moves_after"] = last_old
        return total

    def run(self) -> dict[str, Any]:
        """One funding pass. Runs on its own lane; every venue call is here. Never raises."""
        now = self.clock()
        with self._lock:
            requested = {int(s) for s in list(self.state.get("requested") or []) + list(self.state.get("pending") or [])}
            self.state["requested"], self.state["pending"] = [], []
        report: dict[str, Any] = {"at": _iso(now), "moves": [], "short": [], "blocked": None, "wanted": [], "unmapped": []}
        retry = False  # a blocked or failed pass tries again soon and keeps what was requested
        try:
            book = self.book()
            broker = getattr(book, "broker", None) if book is not None else None
            reader = getattr(broker, "shard_balances", None)
            mover = getattr(broker, "transfer_between_shards", None)
            if not callable(reader) or not callable(mover):
                report["blocked"] = "the Kalshi broker cannot read or move shard collateral"
                return report
            balances = {int(k): _money(v) for k, v in dict(reader()).items()}
            wanted, unmapped, errors = self.wanted()
            wanted |= {s for s in requested if s >= 0}
            report["wanted"], report["unmapped"], report["listing_errors"] = sorted(wanted), sorted(unmapped), errors
            blocked = self.blocked()
            report["blocked"] = blocked
            stakes, unattributed = self.stakes_by_shard(book)
            day_total = self.moved_in_day(now)
            for shard in sorted(wanted):
                cash = balances.get(shard, ZERO)  # a shard the breakdown does not list holds nothing
                asked = shard in requested  # the venue refused an order there: its word, whatever the floor says
                if cash >= FLOOR_USD and not asked:
                    continue
                standing = f"under the ${FLOOR_USD:.0f} floor" if cash < FLOOR_USD else "where a real order was refused for want of collateral"
                until = float((self.state.get("backoff") or {}).get(str(shard)) or 0.0)
                if until > now:
                    report["short"].append({"shard": shard, "cash": f"{cash:.2f}", "why": f"backing off until {_iso(until)}"})
                    continue
                # Read again before every move, not once a pass: a switch engaged, a grant revoked
                # or a book frozen while the first move was on the wire must stop the second.
                blocked = self.blocked()
                report["blocked"] = blocked
                if blocked:
                    report["short"].append({"shard": shard, "cash": f"{cash:.2f}", "why": blocked})
                    self._tell(f"blocked:{shard}", "warning", f"kalshi shard {shard} holds ${cash:.2f}, {standing}, "
                                                              f"and nothing moves while {blocked}; its markets will refuse orders", now)
                    continue
                moved = False
                for donor_cash, donor in sorted(((b, s) for s, b in balances.items() if s != shard), reverse=True):
                    # A stake whose shard cannot be told is kept on every donor, not on shard 0 alone.
                    keep = max(KEEP_USD if donor == HOME_SHARD else FLOOR_USD, stakes.get(donor, ZERO) + unattributed)
                    # Rounded DOWN: the venue reports four decimals, and half-even rounding of the
                    # spare could take a third of a cent past the keep.
                    amount = min(TOP_UP_USD, donor_cash - keep, MAX_MOVE_USD, MAX_DAY_USD - day_total).quantize(CENT, rounding=ROUND_DOWN)
                    if amount < MIN_MOVE_USD:
                        continue
                    outcome = self._move(book, broker, donor, shard, amount, balances, now)
                    report["moves"].append(outcome)
                    if outcome["counted"]:
                        day_total += amount
                    moved = bool(outcome["ok"])
                    if moved and cash >= FLOOR_USD:
                        # Funded above the floor on the venue's word: not again for an hour on that word alone.
                        with self._lock:
                            self.state.setdefault("backoff", {})[str(shard)] = now + BACKOFF_SECONDS
                    break  # one attempt a shard a pass, failed or not: the balances are re-read either way
                if not moved and not any(m["destination"] == shard for m in report["moves"]):
                    why = (f"the day's ${MAX_DAY_USD:.0f} is spent (${day_total:.2f} moved)" if MAX_DAY_USD - day_total < MIN_MOVE_USD
                           else f"no other shard can spare ${MIN_MOVE_USD:.0f} above its keep and the stakes on it"
                           + (f" (${unattributed:.2f} of stakes cannot be told to a shard and are kept on every one)" if unattributed else ""))
                    report["short"].append({"shard": shard, "cash": f"{cash:.2f}", "why": why})
                    self._tell(f"short:{shard}", "warning", f"kalshi shard {shard} holds ${cash:.2f}, {standing}, and {why}; "
                                                            f"its markets will refuse orders", now)
            retry = bool(blocked)
            with self._lock:
                self.state["balances"] = _text(balances)
                self.state["wanted"] = sorted(wanted)
                self.state["unmapped"] = sorted(unmapped)[:40]
                self.state["blocked"] = blocked
                self.state["moved_24h_usd"] = f"{day_total:.2f}"
                self.state["unattributed_usd"] = f"{unattributed:.2f}"
                self.state["last_error"] = None
        except Exception as exc:  # noqa: BLE001 - tried again in BLOCKED_RETRY_SECONDS, or sooner on a refusal
            retry = True
            report["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            with self._lock:
                self.state["last_error"] = report["error"]
            self._alert("warning", f"kalshi shard funding failed ({report['error']})")
        finally:
            with self._lock:
                self.state["last_check"] = _iso(now)
                # A blocked or failed pass is due again in `BLOCKED_RETRY_SECONDS` (the real book is
                # frozen for a moment at startup; a pause or the kill switch lifts), not an hour, and
                # the shards the refusals asked for wait for it rather than being dropped.
                self.state["last_check_epoch"] = (now - INTERVAL_SECONDS + BLOCKED_RETRY_SECONDS) if retry else now
                if retry and requested:
                    self.state["pending"] = sorted(requested | {int(s) for s in (self.state.get("pending") or [])})
                self._save()
        return report

    def _move(self, book: Any, broker: Any, donor: int, shard: int, amount: Decimal, balances: dict[int, Decimal], now: float) -> dict[str, Any]:
        """One transfer, recorded whatever happens. Made under the real book's lock, so a mark
        pass never reads the venue between the transfer and its re-read. The balances are read
        again after it, because a cross-shard move runs in up to three steps that are not undone
        on failure. `outcome`: `moved`; `rejected` (the venue or the adapter said no: nothing
        moved, nothing counted); `unknown` (a gateway or transport failure after a request the
        venue may have executed: counted against the day like a move, `counted` true)."""
        amount = amount.quantize(CENT, rounding=ROUND_DOWN)
        before = dict(balances)
        row: dict[str, Any] = {"ok": False, "outcome": None, "counted": False, "usd": f"{amount:.2f}", "source": donor, "destination": shard,
                               "before": _text(before), "transfer_id": None, "after": None, "error": None}
        guard = getattr(book, "_lock", None)
        with (guard if guard is not None else nullcontext()):
            try:
                row["transfer_id"] = broker.transfer_between_shards(amount, donor, shard)
                row["ok"], row["outcome"] = True, "moved"
            except (RejectedOrder, ValueError) as exc:
                row["error"], row["outcome"] = f"{type(exc).__name__}: {str(exc)[:200]}", "rejected"
            except Exception as exc:  # noqa: BLE001 - recorded, backed off; the venue's state is re-read below
                row["error"], row["outcome"] = f"{type(exc).__name__}: {str(exc)[:200]}", "unknown"
            row["counted"] = row["outcome"] != "rejected"
            try:
                after = {int(k): _money(v) for k, v in dict(broker.shard_balances()).items()}
                row["after"] = _text(after)  # the venue's word, as read
                balances.clear()
                balances.update(after)
                if row["counted"]:
                    # The read may lag the move: for the rest of the pass the donor is never richer
                    # than the move leaves it, nor the destination richer than the read shows.
                    balances[donor] = min(after.get(donor, ZERO), before.get(donor, ZERO) - amount)
                    if row["ok"]:
                        balances[shard] = min(after.get(shard, ZERO), before.get(shard, ZERO) + amount)
            except Exception as exc:  # noqa: BLE001 - not knowing is said; the next pass reads again
                row["after_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
                if row["counted"]:
                    balances[donor] = before.get(donor, ZERO) - amount
                    balances[shard] = before.get(shard, ZERO) + amount
        if row["ok"]:
            text = (f"kalshi collateral: moved ${amount:.2f} from shard {donor} to shard {shard} "
                    f"(transfer {row['transfer_id'] or 'unconfirmed'}; before {row['before']}, after {row['after'] or 'unread'})")
            level = "info"
        else:
            with self._lock:
                self.state.setdefault("backoff", {})[str(shard)] = now + BACKOFF_SECONDS
            unknown = "; the outcome is unknown and counts against the day" if row["outcome"] == "unknown" else ""
            text = (f"kalshi collateral: moving ${amount:.2f} from shard {donor} to shard {shard} FAILED ({row['error']}{unknown}); "
                    f"before {row['before']}, after {row['after'] or 'unread'}; shard {shard} is not tried again for an hour")
            level = "warning"
        self.house.ledger.append("ops.alert", {"level": level, "text": text[:1000], "shard_move": row})
        return row

    # ------------------------------------------------------------- reporting
    def _alert(self, level: str, text: str) -> None:
        alert = getattr(self.house, "alert", None)
        if callable(alert):
            alert(level, text)
        else:
            self.house.ledger.append("ops.alert", {"level": level, "text": str(text)[:1000]})

    def _tell(self, key: str, level: str, text: str, now: float) -> None:
        """A standing condition is said once an hour, not once a pass."""
        with self._lock:
            told = self.state.setdefault("told", {})
            if now - float(told.get(key) or 0.0) < INTERVAL_SECONDS:
                return
            told[key] = now
        self._alert(level, text)

    def health(self) -> dict[str, Any]:
        """health.json's `shards` block. Never raises."""
        try:
            with self._lock:
                state = dict(self.state)
            now = self.clock()
            return {"last_check": state.get("last_check"), "balances": dict(state.get("balances") or {}),
                    "wanted": list(state.get("wanted") or []), "unmapped": list(state.get("unmapped") or []),
                    "moved_24h_usd": state.get("moved_24h_usd"), "day_cap_usd": f"{MAX_DAY_USD:.2f}",
                    "floor_usd": f"{FLOOR_USD:.2f}", "requested": list(state.get("requested") or []),
                    "pending": list(state.get("pending") or []), "unattributed_usd": state.get("unattributed_usd"),
                    "backoff": {k: _iso(float(v)) for k, v in (state.get("backoff") or {}).items() if float(v) > now},
                    "blocked": state.get("blocked"), "last_error": state.get("last_error"),
                    "series": dict(state.get("series") or {})}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
