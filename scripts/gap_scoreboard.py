#!/usr/bin/env python3
"""The gap scoreboard: the seven metrics of the close-the-gaps run, read from a snapshot of the House.

    python3 scripts/gap_scoreboard.py --snapshot DIR [--since ISO] [--baseline ISO] [--json | --markdown]
    python3 scripts/gap_scoreboard.py --take DIR [--since ISO] [--baseline ISO] [--json | --markdown]

Workstream Z of docs/goals/LTCM_CLOSE_THE_GAPS.md: read at T0, every four hours and at the end of
the run. Read-only and standard library only (it borrows `league.stats`, itself standard library, so
its bound is the ladder's own): the sqlite files are opened `mode=ro`, the JSON files are read, and
nothing is written anywhere except DIR under `--take`. Every number it prints names the function
that computed it. `--take` runs on the owner's machine like `scripts/floor_watch.py`: it takes a
sqlite backup of the House's stores on the box into /tmp, gzips it, downloads it through
`scripts.floor_box.client().download`, deletes the box copies, and then reads what it fetched.

A snapshot directory holds `ledger.sqlite`, `lab.sqlite`, `campaigns.sqlite`, `feeds.sqlite` (the
House's feed store, `league/feeds.py`), `health.json`, `house.json` and `allocator-board.json`;
only the ledger is required. The clock is the snapshot's newest ledger row, never this machine's:
windows are measured back from it, and instants are compared as instants, never as strings
(sqlite's `datetime('now', ...)` puts a space where the ledger puts `T`, which once let a whole day
into a six-hour window).

THE FAMILY RECORD. By default every family record here is the House's own: `HouseRecords` runs
`league.families.family_record` (Deploy B; `league.allocator.family_record` in Deploy A's code) on the
snapshot through a read-only ledger and a registry of every agent ever born, so the scoreboard reads
the Alpaca haircut, the loss-rate gate for lopsided records and the unit exactly as the allocator
does (Sept 24, 2026: the review of #224 found this script proving families the allocator did not).
With a checkout that has no such function, or `scoreboard(..., house_records=False)`, the
scoreboard's own account-unit formula below stands in; the practice-only record is always that one.

The scoreboard's own formula (the definition A-money implemented in `league/allocator.py`; Sept 24, 2026)

- Members: every agent ever born with the family (`agent.born` payload `family`) on its venue,
  living or dead.
- Rows: every closed trade a member made on the practice book (`kalshi-shadow`, `alpaca-paper`,
  weight 0.5) or the real book (`kalshi`, `alpaca`, weight 1), exactly as the evaluator's
  `trade_returns` closes them: a settlement, or a sale that leaves the position flat (the realized
  parts of a position sold in pieces are summed into the sale that flattens it). Rows at or before
  the member's evidence cutoff on that book (`league.accounting.evidence_cutoffs`: a fill
  correction or a baseline repair) are left out, as `trade_returns` leaves them out.
- A row's log growth is `stats.log_growth(staked, staked + pnl)`, i.e. ln(1 + pnl / staked), where
  `staked` is what `trade_returns(until_seq=<the row>)` divides by: the most the member had been
  lent on that book up to that row (a later sweep never rescales or erases a closed trade). A row
  with nothing lent before it has no growth and is counted in `rows_without_stake`.
- Events: a Kalshi market's event is its ticker without the last `-` segment
  (`KXMLBTOTAL-26SEP231840MILPHI-6` -> `KXMLBTOTAL-26SEP231840MILPHI`); on Alpaca every closed trade
  is its own event.
- A member's value on an event is the sum of its rows' log growths on that event, per book (a
  member that traded one event on both books has a practice value and a real value). An event is
  ONE observation: the weight-averaged mean of its values, weighted real 1 and practice 0.5, and
  the observation's weight is the largest weight among its rows.
- Pooled: weighted mean m = sum(w x) / sum(w); weighted sd s with the reliability-weights variance
  sum(w (x - m)^2) / (sum(w) - sum(w^2) / sum(w)) (the sample variance when the weights are equal);
  n_eff = sum(w)^2 / sum(w^2); lcb = m - t(0.8, n_eff - 1) * s / sqrt(n_eff) (Student's t one-sided
  80%, `league.stats.t_quantile`); no bound when n_eff < 2, and a record with no spread at all has
  lcb = m (as `stats.mean_bounds`). Proven: at least 10 observations and lcb > 0. Maker and taker are
  pooled apart by the entry fill's `liquidity` (the first buy fill of the position); a position with
  no entry fill on record (carried in) is in neither.

THE SEVEN METRICS (numbers in brackets: the plan's baseline at 00:50Z Sept 24)

1. `real_bounds`: families whose REAL-only pooled record has lcb > 0 [1 family], and each one's
   capacity (`family_capacity`, $/day) = markets in the family's band a day x the fill rate at its
   current size x the average profit per settlement [about $1/day]. The ledger records only the COUNT
   of markets offered to a wake (`agent.woke` `offered`); which markets are in a family's band is
   what its members' own rules chose, so "markets in the band" are the distinct markets the members
   placed a buy on (`book.order` shares), a day, over the last 7 days (or since the family's first
   bid). The fill rate is markets filled over markets bid, in the size bucket of the family's
   median bid, on the real book once it has bid 10 markets at that size (practice fills are
   conservative by design) and on both books before; the profit is the mean P&L of the family's
   real closed trades (practice when it has none). What its real seats earn a day now is shown
   beside it.
2. `allocator_promotions`: `eval.verdict` promote to rung 2 or 3 with `via` allocator; a stay runs to
   the agent's next rung change below the promoted rung (or its death); its result is the P&L of the
   real positions OPENED in the stay that have closed (whenever they closed); share positive is the
   stays with a result above zero over all stays [-$18.62 on 9, 0 positive]. With `--baseline`, only
   promotions after it, each labelled from the promotion row or the board (`probe`, `bunt`, a
   family state) where the House writes one, else `unlabelled` with the family record's state then.
3. `real_dollars`: the board's `stake_usd` of every agent in a real band (anything above replay and
   paper), by whether its family is proven (the pooled record above) [$66 / $256]; Alpaca real
   agents on the board [0].
4. `deaths_in_window`: `agent.died` in the window: median life (born to died, hours), overall and for
   day-horizon agents (`agent.born` `horizon`, else the desk's only horizon), and the share that died
   with fewer than 3 of their own fills (venue or cross fills on any book; the House's closing sales
   are the House's, not the agent's) [14.3 h; 68%]; and the same for the agents that held a practice
   seat before they died (a replay-only agent has no book and can never fill).
5. `lab_loop`: `lab.sqlite` `batches` in the last hour and an hour over the window; the LLM share of
   born graduates (candidate origin `luna`/`sol`/`agent` against `param`/`seed`) [2 of 18]; waiters
   (graduations `passed`, waiting since their `lab.graduate:<id>:passed` ledger row as `Lab.waiting`
   counts it; foundry cards that passed replay and were never born, as `Foundry.inventory` folds
   them from the ledger, waiting since their passing evaluation) and the longest wait [30 at 11 h]; parents
   superseded (`agent.died` cause `superseded` in the window) and the real-money parents with a
   replay-passing research child (a fork whose child passed a replay trial while the parent stood
   on rung 2 or 3), superseded or not [0].
6. `self_cross_exits`: `book.refused` in the last 6 h whose reasons name "House's own resting order"
   and whose intent was a sell [about 85]; `stacked_promotions`: allocator promotions whose
   qualifying record (every practice-book close since the evidence cutoff, before the promotion) has
   fewer distinct events than closes [1], each with whether it would still pass the bunt line's
   counts were settlements, or every close, counted once per event.
7. `recorders_live`: of the key-free data hosts the owner allowed on Sept 24, 2026 (the block of
   `scripts/floor_box.py` `LEAGUE_HOSTS` that begins with `api.open-meteo.com`), those with a feed
   recorded in the last day: a feed is mapped to a host by the `source` its `data.coverage` rows
   name (and the backfill sources), and it is live when `feeds.sqlite` has an ok poll or a stored
   row for it in the last day (without `feeds.sqlite`, a `data.coverage` row of the last day whose
   feed is not `unavailable`) [0 of 12]. `idle_desks`: desks whose members were offered markets
   (`agent.woke` `offered` > 0) in the last 48 h and placed no intent [3 desks].

ALSO: `evidence_clocks` (per desk: hours from a member's first fill to its third independent
settlement, members whose first fill is in the last 7 days; the median of those who reached it and a
Kaplan-Meier median that counts the ones who died or are still waiting as censored), `family_records`
(every family's pooled record) and `weather_capacity` (the weather-favourites family: markets in its
band a day, the fill rate by size, settlements a day).
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import re
import shutil
import sqlite3
import sys
import time
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from league.stats import log_growth, t_quantile  # noqa: E402  (standard library only, as this script)

HOUSE = "house"
PRACTICE_BOOKS = ("kalshi-shadow", "alpaca-paper")
REAL_BOOKS = ("kalshi", "alpaca")
EVENT_BOOKS = ("kalshi-shadow", "kalshi")
PRACTICE_BOOK = {"kalshi": "kalshi-shadow", "alpaca": "alpaca-paper"}
#: The family record's weights (the plan's `evidence.paper_weight` 0.5 for practice, 1 for real).
WEIGHT = {"kalshi-shadow": 0.5, "alpaca-paper": 0.5, "kalshi": 1.0, "alpaca": 1.0}
#: One-sided 80% (the plan's `allocator.family_proven`), Student's t on n_eff - 1 degrees of freedom.
BOUND_LEVEL = 0.8
PROVEN_MIN_OBSERVATIONS = 10
#: The bands that stand on real money (the allocator's `bunt`, `swing` and `star`; a `probe` after P1).
NOT_REAL_BANDS = ("replay", "paper")
SELF_CROSS = "House's own resting order"
HOUSE_CLOSING = "the House is closing"
LLM_ORIGINS = ("luna", "sol", "agent")
SUPERSEDED = "superseded"
WEATHER_FAMILY = "weather-favorites"
#: Bid-size buckets for fill rates (the weather favourites bid about $10 a market).
SIZE_BUCKETS = ((12.0, "<=$12"), (25.0, "$12-25"), (50.0, "$25-50"), (math.inf, ">$50"))
HOUR, DAY = 3600.0, 86400.0
CAPACITY_DAYS = 7.0
#: The real book's fill rate stands for capacity once it has bid this many markets at the size.
MIN_REAL_MARKETS_FOR_FILL_RATE = 10
EVIDENCE_CLOCK_DAYS = 7.0
SELF_CROSS_HOURS = 6.0
IDLE_DESK_HOURS = 48.0
RECORDER_HOURS = 24.0
SNAPSHOT_SQLITE = ("ledger.sqlite", "lab.sqlite", "campaigns.sqlite", "feeds.sqlite")
SNAPSHOT_JSON = ("health.json", "house.json", "allocator-board.json", "allocator.json")
BOX_PYTHON = "/workspace/.venv/bin/python"
#: The first of the key-free data hosts the owner allowed on Sept 24, 2026 (`LEAGUE_HOSTS`' last block).
FIRST_ALLOWED_DATA_HOST = "api.open-meteo.com"


# ------------------------------------------------------------------------------------ time
def epoch(value: Any) -> float:
    """An instant from an ISO stamp (`Z` or an offset; no offset is UTC; a space for `T` is read the
    same) or from epoch seconds."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def iso(ts: float | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _r(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


# ------------------------------------------------------------------------------- the snapshot
@dataclass(frozen=True)
class Row:
    seq: int
    kind: str
    agent: str
    at: str
    t: float
    p: dict


def connect(path: Path) -> sqlite3.Connection | None:
    """A read-only connection, or None when the file is not in the snapshot."""
    if not path.exists():
        return None
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


class Snapshot:
    """The stores of one snapshot directory, read-only. Ledger rows are read by kind once and kept."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.ledger = connect(self.root / "ledger.sqlite")
        if self.ledger is None:
            raise SystemExit(f"no ledger.sqlite in {self.root}")
        self.lab = connect(self.root / "lab.sqlite")
        self.campaigns = connect(self.root / "campaigns.sqlite")
        self.feeds = connect(self.root / "feeds.sqlite")
        self.json: dict[str, Any] = {}
        for name in SNAPSHOT_JSON:
            try:
                self.json[name] = json.loads((self.root / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.json[name] = None
        head = self.ledger.execute("SELECT count(*), max(seq), max(at) FROM ledger").fetchone()
        self.rows_total, self.head_seq, self.newest_at = int(head[0]), int(head[1] or 0), head[2]
        self.now = epoch(self.newest_at) if self.newest_at else time.time()
        self._rows: dict[str, list[Row]] = {}

    def rows(self, *kinds: str) -> list[Row]:
        out: list[Row] = []
        for kind in kinds:
            if kind not in self._rows:
                self._rows[kind] = [
                    Row(int(seq), kind, str(agent), str(at), epoch(at), _payload(payload))
                    for seq, agent, at, payload in self.ledger.execute(
                        "SELECT seq, agent, at, payload FROM ledger WHERE kind = ? ORDER BY seq", (kind,))
                ]
            out.extend(self._rows[kind])
        if len(kinds) > 1:
            out.sort(key=lambda r: r.seq)
        return out

    def close(self) -> None:
        for conn in (self.ledger, self.lab, self.campaigns, self.feeds):
            if conn is not None:
                conn.close()

    def at_of(self, ident: str) -> float | None:
        """When the ledger row with this id was written, or None."""
        row = self.ledger.execute("SELECT at FROM ledger WHERE id = ?", (ident,)).fetchone()
        return epoch(row[0]) if row else None

    @property
    def board(self) -> dict[str, Any]:
        return self.json.get("allocator-board.json") or {}


def _payload(text: str) -> dict:
    try:
        payload = json.loads(text)
    except ValueError:
        return {}
    if isinstance(payload, dict):
        # Code is kept on the ledger for audit; nothing here reads it, and it is most of the bytes.
        for key in [k for k in payload if k.startswith("_code")]:
            payload.pop(key)
        return payload
    return {"value": payload}


# ---------------------------------------------------------------------------------- agents
@dataclass
class Agent:
    id: str
    family: str
    venue: str
    desk: str
    horizon: str
    parent: str | None
    founder: str | None
    born: float
    born_seq: int
    died: float | None = None
    died_seq: int | None = None
    cause: str | None = None

    @property
    def alive(self) -> bool:
        return self.died is None


def agents_of(snap: Snapshot) -> dict[str, Agent]:
    out: dict[str, Agent] = {}
    for row in snap.rows("agent.born"):
        p = row.p
        if row.agent not in out:
            out[row.agent] = Agent(row.agent, str(p.get("family") or row.agent), str(p.get("venue") or ""),
                                   str(p.get("specialty") or ""), str(p.get("horizon") or ""),
                                   p.get("parent"), p.get("founder"), row.t, row.seq)
    for row in snap.rows("agent.died"):
        agent = out.get(row.agent)
        if agent is not None and agent.died is None:
            agent.died, agent.died_seq, agent.cause = row.t, row.seq, row.p.get("cause")
    return out


def desk_horizons() -> dict[str, list[str]]:
    """Desk id -> its horizons, from `league/niches.json` in this checkout."""
    try:
        niches = json.loads((REPO_ROOT / "league" / "niches.json").read_text(encoding="utf-8"))["niches"]
    except (OSError, ValueError, KeyError):
        return {}
    return {str(n.get("id")): list(n.get("horizons") or []) for n in niches if isinstance(n, dict)}


class Rungs:
    """Every agent's rung changes (`eval.verdict` promote, demote, seat) in ledger order."""

    def __init__(self, snap: Snapshot):
        self.changes: dict[str, list[Row]] = defaultdict(list)
        for row in snap.rows("eval.verdict"):
            if row.p.get("decision") in ("promote", "demote", "seat"):
                self.changes[row.agent].append(row)
        self._seqs = {a: [r.seq for r in rows] for a, rows in self.changes.items()}

    def at(self, agent: str, seq: int) -> int:
        rows = self.changes.get(agent) or []
        i = bisect_right(self._seqs.get(agent, []), seq)
        return int(rows[i - 1].p.get("to_rung") or 0) if i else 0

    def now(self, agent: str) -> int:
        rows = self.changes.get(agent) or []
        return int(rows[-1].p.get("to_rung") or 0) if rows else 0

    def stay_end(self, agent: str, seq: int, rung: int) -> Row | None:
        """The first rung change after `seq` that takes the agent below `rung`."""
        for row in self.changes.get(agent) or []:
            if row.seq > seq and int(row.p.get("to_rung") or 0) < rung:
                return row
        return None


# ---------------------------------------------------------------------------------- trades
def instrument_key(instrument: Mapping[str, Any]) -> str:
    """The evaluator's key of one position (`trade_returns`): an option is its contract."""
    return ":".join(str(instrument.get(k)) for k in ("market_id", "symbol", "right", "expiry", "strike")
                    if instrument.get(k) is not None)


def kalshi_event(market: str) -> str:
    """A Kalshi market's event: its ticker without the last `-` segment."""
    return market.rsplit("-", 1)[0] if "-" in market else market


@dataclass
class Trade:
    agent: str
    book: str
    key: str
    market: str
    event: str
    close_seq: int
    close_t: float
    how: str  # "settle" or "sale"
    pnl: float
    staked: float
    growth: float | None
    entry_seq: int | None
    entry_t: float | None
    liquidity: str | None
    notional: float
    closing: bool  # the sale was the House closing the account, not the agent's own exit

    @property
    def real(self) -> bool:
        return self.book in REAL_BOOKS


@dataclass
class OpenPosition:
    agent: str
    book: str
    key: str
    market: str
    entry_seq: int
    entry_t: float
    notional: float


class Stakes:
    """What `trade_returns(until_seq=seq)` divides by: the most an agent had been lent on a book up
    to a ledger position (the running peak of its net stake)."""

    def __init__(self, snap: Snapshot):
        running: dict[tuple[str, str], float] = defaultdict(float)
        peak: dict[tuple[str, str], float] = defaultdict(float)
        self.rows: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
        for row in snap.rows("book.stake"):
            key = (row.agent, str(row.p.get("book")))
            running[key] += float(row.p.get("usd") or 0)
            peak[key] = max(peak[key], running[key])
            self.rows[key].append((row.seq, peak[key]))
        self._seqs = {k: [s for s, _ in v] for k, v in self.rows.items()}

    def at(self, agent: str, book: str, seq: int) -> float:
        rows = self.rows.get((agent, book)) or []
        i = bisect_right(self._seqs.get((agent, book), []), seq)
        return rows[i - 1][1] if i else 0.0


def evidence_cutoffs(snap: Snapshot) -> dict[tuple[str, str], int]:
    """(agent, book) -> the ledger position scoring restarts after (`league.accounting.evidence_cutoffs`)."""
    out: dict[tuple[str, str], int] = {}
    for row in snap.rows("book.fill_correction"):
        out[(row.agent, str(row.p.get("book")))] = row.seq
    for row in snap.rows("book.baseline"):
        for repair in row.p.get("repairs") or []:
            key = (str(repair.get("agent")), str(row.p.get("book")))
            out[key] = max(out.get(key, 0), row.seq)
    return out


def closed_trades(snap: Snapshot) -> tuple[list[Trade], list[OpenPosition], dict[str, int]]:
    """Every closed trade on the four books, as `Evaluator.trade_returns` closes them; the positions
    still open at the snapshot; and counts of what was left out."""
    stakes = Stakes(snap)
    cutoffs = evidence_cutoffs(snap)
    running: dict[tuple[str, str, str], float] = {}
    entries: dict[tuple[str, str, str], dict[str, Any]] = {}
    trades: list[Trade] = []
    skipped = Counter()
    for row in snap.rows("book.fill", "book.settle"):
        p = row.p
        book = str(p.get("book"))
        if row.agent == HOUSE or book not in WEIGHT:
            continue
        if row.seq <= cutoffs.get((row.agent, book), 0):
            skipped["rows_before_evidence_cutoff"] += 1
            continue
        instrument = p.get("instrument") or {}
        key = instrument_key(instrument)
        market = str(instrument.get("market_id") or instrument.get("symbol") or key)
        slot = (row.agent, book, key)
        closing = False
        if row.kind == "book.settle":
            pnl = running.pop(slot, 0.0) + float(p.get("pnl") or 0)
            how = "settle"
        elif p.get("realized") is not None and p.get("source") != "dust":
            running[slot] = running.get(slot, 0.0) + float(p["realized"])
            if not p.get("flat", True):
                continue
            pnl = running.pop(slot)
            how = "sale"
            closing = str(p.get("reason") or "").startswith(HOUSE_CLOSING)
        else:
            if p.get("side") == "buy" and p.get("source") in ("venue", "cross"):
                entry = entries.setdefault(slot, {"seq": row.seq, "t": row.t, "liquidity": p.get("liquidity"),
                                                  "notional": 0.0, "market": market})
                entry["notional"] += abs(float(p.get("cash_delta") or 0))
            continue
        staked = stakes.at(row.agent, book, row.seq)
        growth = log_growth(staked, staked + pnl) if staked > 0 else None
        if growth is None:
            skipped["rows_without_stake"] += 1
        entry = entries.pop(slot, None) or {}
        event = kalshi_event(market) if book in EVENT_BOOKS else f"{row.agent}|{book}|{key}|{row.seq}"
        trades.append(Trade(row.agent, book, key, market, event, row.seq, row.t, how, pnl, staked, growth,
                            entry.get("seq"), entry.get("t"), entry.get("liquidity"), float(entry.get("notional") or 0.0),
                            closing))
    still_open = [OpenPosition(a, b, k, str(e["market"]), int(e["seq"]), float(e["t"]), float(e["notional"]))
                  for (a, b, k), e in entries.items()]
    return trades, still_open, dict(skipped)


def own_fills(snap: Snapshot) -> dict[str, list[Row]]:
    """Each agent's own fills: venue or cross fills on any book, the House's closing sales left out."""
    out: dict[str, list[Row]] = defaultdict(list)
    for row in snap.rows("book.fill"):
        p = row.p
        if row.agent == HOUSE or p.get("source") not in ("venue", "cross"):
            continue
        if str(p.get("reason") or "").startswith(HOUSE_CLOSING):
            continue
        out[row.agent].append(row)
    return out


# --------------------------------------------------------------------------- the family record
def pooled(observations: Sequence[tuple[float, float]]) -> dict[str, Any]:
    """The weighted pooled record of (value, weight) observations (the module docstring's formulas)."""
    n = len(observations)
    out: dict[str, Any] = {"n": n, "n_eff": None, "mean": None, "sd": None, "lcb": None, "proven": False}
    if not n:
        return out
    sw = math.fsum(w for _, w in observations)
    sw2 = math.fsum(w * w for _, w in observations)
    mean = math.fsum(w * x for x, w in observations) / sw
    n_eff = sw * sw / sw2
    out.update(n_eff=n_eff, mean=mean)
    if n_eff < 2:
        return out
    values = [x for x, _ in observations]
    if max(values) == min(values):
        sd = 0.0
    else:
        sd = math.sqrt(math.fsum(w * (x - mean) ** 2 for x, w in observations) / (sw - sw2 / sw))
    lcb = mean - t_quantile(BOUND_LEVEL, n_eff - 1.0) * sd / math.sqrt(n_eff)
    out.update(sd=sd, lcb=lcb, proven=n >= PROVEN_MIN_OBSERVATIONS and lcb > 0)
    return out


def observations(trades: Iterable[Trade]) -> list[tuple[float, float]]:
    """One (value, weight) per distinct event: each member's per-book sum of log growths on the event,
    averaged at weights real 1 / practice 0.5; the event's weight is its largest row weight."""
    by_event: dict[str, dict[tuple[str, str], float]] = defaultdict(lambda: defaultdict(float))
    for trade in trades:
        if trade.growth is not None:
            by_event[trade.event][(trade.agent, trade.book)] += trade.growth
    out = []
    for values in by_event.values():
        weighted = [(v, WEIGHT[book]) for (_, book), v in values.items()]
        total = math.fsum(w for _, w in weighted)
        out.append((math.fsum(v * w for v, w in weighted) / total, max(w for _, w in weighted)))
    return out


def record(trades: Sequence[Trade]) -> dict[str, Any]:
    out = pooled(observations(trades))
    out["rows"] = len(trades)
    out["real_rows"] = sum(1 for t in trades if t.real)
    out["pnl_usd"] = round(math.fsum(t.pnl for t in trades), 4)
    return out


class SnapshotLedger:
    """The House ledger's read interface (`iter`) over the snapshot's read-only ledger, for the House's
    own family record."""

    class Entry:
        __slots__ = ("seq", "kind", "agent", "at", "payload")

        def __init__(self, seq: int, kind: str, agent: str, at: str, payload: dict):
            self.seq, self.kind, self.agent, self.at, self.payload = seq, kind, agent, at, payload

    def __init__(self, snap: Snapshot):
        self.snap = snap

    def iter(self, *, kinds: Iterable[str] | str | None = None, agent: str | None = None, after: int = 0):
        kinds = [kinds] if isinstance(kinds, str) else list(kinds or ())
        sql, args = "SELECT seq, kind, agent, at, payload FROM ledger WHERE seq > ?", [int(after)]
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            args += kinds
        if agent is not None:
            sql += " AND agent = ?"
            args.append(agent)
        for seq, kind, who, at, payload in self.snap.ledger.execute(sql + " ORDER BY seq", args):
            yield self.Entry(int(seq), str(kind), str(who), str(at), _payload(payload))


class HouseRecords:
    """Each family's pooled forward record exactly as the House computes it: `league.families.family_record`
    (Deploy B; `league.allocator.family_record` before it) run on the snapshot through a read-only ledger
    and a registry of every agent ever born, so the scoreboard and the allocator can never disagree about
    which family is proven (the review of #224 found the scoreboard without the House's Alpaca haircut and
    loss-rate gate; Deploy B's at-risk unit moved the record again). `open` returns None on a checkout
    without the function; the scoreboard's own account-unit record (`record`) stands in then."""

    class _Agent:
        __slots__ = ("id", "family", "venue", "alive")

        def __init__(self, agent: Agent):
            self.id, self.family, self.venue, self.alive = agent.id, agent.family, agent.venue, agent.alive

    def __init__(self, snap: Snapshot, agents: Mapping[str, Agent], compute: Any, tape: Any):
        self.snap, self.compute, self.tape = snap, compute, tape
        self.ledger = SnapshotLedger(snap)
        self.registry = type("Registry", (), {})()
        self.registry.agents = {a.id: self._Agent(a) for a in agents.values()}
        self.through = self.tape.refresh(self.ledger)

    @classmethod
    def open(cls, snap: Snapshot, agents: Mapping[str, Agent]) -> "HouseRecords | None":
        try:
            from league import families as house_families
            compute, tape = house_families.family_record, house_families.TradeTape()
        except ImportError:
            try:
                from league import allocator as house_allocator
                compute, tape = house_allocator.family_record, house_allocator.TradeTape()
            except (ImportError, AttributeError):
                return None
        return cls(snap, agents, compute, tape)

    def record(self, venue: str, family: str, *, through: int | None = None) -> dict[str, Any]:
        """The House's record, in the scoreboard's keys (`n`, `n_eff`, `mean`, `sd`, `lcb`, `proven`), with the
        House's own record under `house` and its real, maker and taker sides normalised the same way."""
        rec = self.compute(self, family, venue, tape=self.tape, through=through)
        out = house_side(rec)
        out["proven"] = bool(rec.get("proven"))
        out["unit"] = rec.get("unit", "account")
        for side in ("real", "maker", "taker"):
            if isinstance(rec.get(side), Mapping):
                out[side] = house_side(rec[side])
        out["house"] = {k: v for k, v in rec.items() if k not in ("real", "maker", "taker", "rule")}
        return out


def house_side(rec: Mapping[str, Any]) -> dict[str, Any]:
    """One side of a House record in the scoreboard's keys; `lcb` is the House's honest bound (the t bound,
    and the loss-rate gate for a lopsided record) where it gives one."""
    honest = rec.get("honest_bound", rec.get("bound"))
    return {"n": int(rec.get("n") or 0), "n_eff": rec.get("n_eff"), "mean": rec.get("mean_log"), "sd": rec.get("sd"),
            "lcb": honest, "t_bound": rec.get("bound"), "loss_gate": rec.get("loss_gate"),
            "proven": bool(rec.get("proven", rec.get("positive", False)))}


class Families:
    """Members and closed trades by family (keyed by (venue, family))."""

    def __init__(self, agents: Mapping[str, Agent], trades: Sequence[Trade], house: HouseRecords | None = None):
        self.house = house
        self.members: dict[tuple[str, str], list[Agent]] = defaultdict(list)
        for agent in agents.values():
            self.members[(agent.venue, agent.family)].append(agent)
        self.trades: dict[tuple[str, str], list[Trade]] = defaultdict(list)
        for trade in trades:
            agent = agents.get(trade.agent)
            if agent is not None:
                self.trades[(agent.venue, agent.family)].append(trade)
        self._records: dict[tuple[str, str], dict[str, Any]] = {}

    def state(self, venue: str, family: str) -> dict[str, Any]:
        """The pooled practice-and-real record (memoised): the House's own (`HouseRecords`) when this
        checkout has it, else the scoreboard's account-unit record."""
        key = (venue, family)
        if key not in self._records:
            if self.house is not None and venue in PRACTICE_BOOK:
                self._records[key] = self.house.record(venue, family)
            else:
                self._records[key] = record(self.trades.get(key) or [])
        return self._records[key]

    def state_before(self, venue: str, family: str, seq: int) -> dict[str, Any]:
        """The pooled record from the rows closed before a ledger position."""
        if self.house is not None and venue in PRACTICE_BOOK:
            return self.house.record(venue, family, through=seq - 1)
        return record([t for t in self.trades.get((venue, family)) or [] if t.close_seq < seq])


def family_records(snap: Snapshot, agents: Mapping[str, Agent], families: Families) -> dict[str, Any]:
    """Every family's pooled forward record: practice and real, real only, maker and taker apart,
    members, living members and the real stake on the board now."""
    board = (snap.board.get("agents") or {})
    rows = []
    for (venue, family), members in sorted(families.members.items()):
        trades = families.trades.get((venue, family)) or []
        stake = math.fsum(float(board[a.id].get("stake_usd") or 0) for a in members
                          if a.id in board and board[a.id].get("band") not in NOT_REAL_BANDS)
        rows.append({
            "family": family, "venue": venue,
            "members": len(members), "living": sum(1 for a in members if a.alive),
            "real_stake_usd": round(stake, 2),
            "pooled": (pooled := families.state(venue, family)),
            "practice": record([t for t in trades if not t.real]),
            "real": pooled.get("real") or record([t for t in trades if t.real]),
            "maker": pooled.get("maker") or record([t for t in trades if t.liquidity == "maker"]),
            "taker": pooled.get("taker") or record([t for t in trades if t.liquidity == "taker"]),
        })
    rows.sort(key=lambda r: (-(r["pooled"]["n"]), r["venue"], r["family"]))
    return {"fn": "family_records", "families": rows,
            "with_observations": sum(1 for r in rows if r["pooled"]["n"]),
            "proven": [r["family"] for r in rows if r["pooled"]["proven"]]}


# ------------------------------------------------------------------------------- capacity
def intent_outcomes(snap: Snapshot) -> dict[str, dict[str, Any]]:
    """Every buy intent: its agent, book, market, size (quantity x limit or reference price), when,
    and whether it was placed (a `book.order` share names it), refused, and filled."""
    out: dict[str, dict[str, Any]] = {}
    for row in snap.rows("agent.intent"):
        p = row.p
        if p.get("side") != "buy" or not p.get("id"):
            continue
        instrument = p.get("instrument") or {}
        try:
            price = float(p["limit_price"]) if p.get("limit_price") is not None else None
            quantity = float(p.get("quantity") or 0)
        except (TypeError, ValueError):
            price, quantity = None, 0.0
        out[str(p["id"])] = {"agent": row.agent, "book": str(p.get("book")), "t": row.t,
                             "market": str(instrument.get("market_id") or instrument.get("symbol") or ""),
                             "quantity": quantity, "price": price, "placed": False, "refused": False, "filled": 0.0}
    for row in snap.rows("book.order"):
        for share in row.p.get("shares") or []:
            intent = out.get(str(share.get("intent_id")))
            if intent is not None:
                intent["placed"] = True
                if intent["price"] is None and row.p.get("reference_price") is not None:
                    intent["price"] = float(row.p["reference_price"])
    for row in snap.rows("book.refused"):
        intent = out.get(str(row.p.get("intent_id")))
        if intent is not None:
            intent["refused"] = True
    for row in snap.rows("book.fill"):
        intent = out.get(str(row.p.get("intent_id")))
        if intent is not None and row.p.get("side") == "buy":
            intent["filled"] += float(row.p.get("quantity") or 0)
    for intent in out.values():
        intent["notional"] = intent["quantity"] * intent["price"] if intent["price"] is not None else None
    return out


def size_bucket(notional: float | None) -> str | None:
    if notional is None:
        return None
    for top, name in SIZE_BUCKETS:
        if notional <= top:
            return name
    return SIZE_BUCKETS[-1][1]


def fill_rates(bids: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """By size bucket: markets bid and markets filled (a market counts once), bids placed and filled."""
    out: dict[str, dict[str, Any]] = {}
    for name in [b for _, b in SIZE_BUCKETS]:
        rows = [b for b in bids if size_bucket(b["notional"]) == name]
        if not rows:
            continue
        markets = {b["market"] for b in rows}
        filled = {b["market"] for b in rows if b["filled"] > 0}
        out[name] = {"markets_bid": len(markets), "markets_filled": len(filled),
                     "fill_rate": _r(len(filled) / len(markets)), "bids": len(rows),
                     "bids_filled": sum(1 for b in rows if b["filled"] > 0)}
    return out


def family_capacity(snap: Snapshot, venue: str, family: str, members: Sequence[Agent], trades: Sequence[Trade],
                    intents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Capacity in $/day = markets in the band a day x the fill rate at the current size x the average
    profit per settlement, each factor shown (the module docstring says where each comes from)."""
    ids = {a.id for a in members}
    start = snap.now - CAPACITY_DAYS * DAY
    bids = [i for i in intents.values() if i["agent"] in ids and i["placed"] and i["t"] >= start and i["market"]]
    if not bids:
        return {"fn": "family_capacity", "family": family, "venue": venue, "capacity_usd_per_day": None,
                "why": "no placed buy in the last 7 days"}
    first = min(b["t"] for b in bids)
    days = max((snap.now - max(first, start)) / DAY, 1.0 / 24.0)
    markets = {b["market"] for b in bids}
    sizes = sorted(b["notional"] for b in bids if b["notional"] is not None)
    current = median(sizes) if sizes else None
    bucket = size_bucket(current)
    by_book = {}
    for kind, books in (("real", REAL_BOOKS), ("practice", PRACTICE_BOOKS)):
        rows = [b for b in bids if b["book"] in books]
        if rows:
            by_book[kind] = fill_rates(rows)
    every = fill_rates(bids)
    # The real book's own fill rate when it has bid enough markets at this size: practice fills are
    # conservative by design (the plan's second principle), and capacity is a real-money number.
    real_at_size = (by_book.get("real") or {}).get(bucket) or {}
    if int(real_at_size.get("markets_bid") or 0) >= MIN_REAL_MARKETS_FOR_FILL_RATE:
        rate, rate_basis = real_at_size.get("fill_rate"), "real"
    else:
        rate, rate_basis = (every.get(bucket) or {}).get("fill_rate"), "all books"
    closed = [t for t in trades if t.close_t >= start]
    real = [t for t in closed if t.real]
    practice = [t for t in closed if not t.real]
    basis = real or closed
    profit = math.fsum(t.pnl for t in basis) / len(basis) if basis else None
    real_profit = math.fsum(t.pnl for t in real) / len(real) if real else None
    per_day = len(markets) / days
    capacity = per_day * rate * profit if rate is not None and profit is not None else None
    events_real = {t.event for t in real}
    return {
        "fn": "family_capacity", "family": family, "venue": venue, "days": _r(days, 2),
        "markets_bid": len(markets), "markets_per_day": _r(per_day, 2),
        "current_size_usd": _r(current, 2), "size_bucket": bucket,
        "fill_rate_at_size": rate, "fill_rate_basis": rate_basis,
        "fill_rates": every, "fill_rates_by_book": by_book,
        "profit_basis": "real" if real else "practice", "settlements": len(basis),
        "profit_per_settlement_usd": _r(profit),
        "practice_profit_per_settlement_usd": _r(math.fsum(t.pnl for t in practice) / len(practice)) if practice else None,
        "settlements_per_day": {"real": _r(len(real) / days, 2), "all": _r(len(closed) / days, 2),
                                "real_independent": _r(len(events_real) / days, 2)},
        "capacity_usd_per_day": _r(capacity),
        # What the family's real seats make a day now, for comparison with what its band could hold.
        "real_earning_usd_per_day": _r(len(real) / days * real_profit) if real_profit is not None else None,
    }


# ---------------------------------------------------------------------------------- metric 1
def real_bounds(snap: Snapshot, families: Families, intents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Families whose real-only pooled record has a lower bound above zero, and each one's capacity; and the
    families the House's own proof calls proven (the pooled practice-and-real record, `HouseRecords`),
    with theirs. With the House's record the real side is the House's (its unit, its honest bound)."""
    rows, proven = [], []
    for (venue, family), trades in sorted(families.trades.items()):
        pooled = families.state(venue, family)
        # The House's real side where its record has one (Deploy B's), else the scoreboard's own.
        real = pooled.get("real") or record([t for t in trades if t.real])
        if pooled.get("proven"):
            proven.append({"family": family, "venue": venue, "pooled": pooled, "real": real,
                           "capacity": family_capacity(snap, venue, family, families.members[(venue, family)], trades, intents)})
        if real and real.get("lcb") is not None and real["lcb"] > 0:
            capacity = family_capacity(snap, venue, family, families.members[(venue, family)], trades, intents)
            rows.append({"family": family, "venue": venue, "real": real, "capacity": capacity})
    return {"fn": "real_bounds", "count": len(rows), "families": rows, "proven": proven,
            "record": "house" if families.house is not None else "scoreboard",
            "with_enough_real_events": sum(1 for r in rows if r["real"]["n"] >= PROVEN_MIN_OBSERVATIONS),
            "real_families": sum(1 for trades in families.trades.values() if any(t.real for t in trades))}


# ---------------------------------------------------------------------------------- metric 2
def promotion_label(row: Row, board_row: Mapping[str, Any] | None, family_state: Mapping[str, Any]) -> tuple[str, str]:
    """(label, where it came from): what the promotion row or the board says it is (a probe, a bunt,
    a family state) once the House writes it (Deploy A), else `unlabelled` with the family record's
    state at the promotion."""
    p = row.p
    for key in ("tier", "band_to", "band", "stake_kind", "kind"):
        value = str(p.get(key) or "")
        if value in ("probe", "probe_bunt"):
            return "probe", f"promotion {key}"
    if p.get("probe") is True:
        return "probe", "promotion probe"
    for key in ("family_state", "family_proven"):
        if key in p:
            proven = p[key] in ("proven", "swing", True)
            return ("proven-family bunt" if proven else "probe"), f"promotion {key}"
    if board_row:
        if str(board_row.get("band")) == "probe" or board_row.get("probe") is True:
            return "probe", "board band"
        if "family_state" in board_row:
            proven = board_row["family_state"] in ("proven", "swing")
            return ("proven-family bunt" if proven else "probe"), "board family_state"
    hint = "proven" if family_state.get("proven") else "unproven"
    return "unlabelled", f"family record then: {hint}"


def allocator_promotions(snap: Snapshot, agents: Mapping[str, Agent], rungs: Rungs, trades: Sequence[Trade],
                         still_open: Sequence[OpenPosition], families: Families, baseline: float | None) -> dict[str, Any]:
    """Allocator promotions to real money: each stay's settled real result."""
    board = snap.board.get("agents") or {}
    by_agent: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        if trade.real and trade.entry_seq is not None:
            by_agent[trade.agent].append(trade)
    open_by_agent: dict[str, list[OpenPosition]] = defaultdict(list)
    for position in still_open:
        if position.book in REAL_BOOKS:
            open_by_agent[position.agent].append(position)
    rows = []
    for row in snap.rows("eval.verdict"):
        p = row.p
        if p.get("decision") != "promote" or int(p.get("to_rung") or 0) < 2 or p.get("via") != "allocator":
            continue
        if baseline is not None and row.t < baseline:
            continue
        rung = int(p["to_rung"])
        end = rungs.stay_end(row.agent, row.seq, rung)
        agent = agents.get(row.agent)
        end_seq = end.seq if end is not None else (agent.died_seq if agent and agent.died_seq else None)

        def inside(seq: int, start: int = row.seq, stop: int | None = end_seq) -> bool:
            return seq >= start and (stop is None or seq <= stop)

        opened = [t for t in by_agent.get(row.agent, []) if inside(t.entry_seq)]
        pending = [o for o in open_by_agent.get(row.agent, []) if inside(o.entry_seq)]
        family = agent.family if agent else None
        venue = agent.venue if agent else None
        state = families.state_before(venue, family, row.seq) if agent else {}
        label, source = promotion_label(row, board.get(row.agent), state)
        result = math.fsum(t.pnl for t in opened)
        rows.append({
            "agent": row.agent, "at": iso(row.t), "to_rung": rung, "family": family,
            "stake_usd": p.get("stake_usd"), "ended": iso(end.t) if end is not None else None,
            "ended_why": str(end.p.get("reason") or "")[:90] if end is not None else None,
            "settlements": len(opened), "settled_pnl_usd": round(result, 4),
            "independent_events": len({t.event for t in opened}),
            "open_positions": len(pending), "label": label, "label_source": source,
            "family_proven_then": bool(state.get("proven")),
        })
    positive = sum(1 for r in rows if r["settled_pnl_usd"] > 0)
    return {"fn": "allocator_promotions", "baseline": iso(baseline), "promotions": len(rows),
            "settled_pnl_usd": round(math.fsum(r["settled_pnl_usd"] for r in rows), 4),
            "settlements": sum(r["settlements"] for r in rows),
            "with_a_settlement": sum(1 for r in rows if r["settlements"]),
            "positive": positive, "share_positive": _r(positive / len(rows)) if rows else None,
            "negative": sum(1 for r in rows if r["settled_pnl_usd"] < 0),
            "labels": dict(Counter(r["label"] for r in rows)), "rows": rows}


# ---------------------------------------------------------------------------------- metric 3
def real_dollars(snap: Snapshot, agents: Mapping[str, Agent], families: Families) -> dict[str, Any]:
    """The board's real stakes by whether the agent's family is proven; Alpaca agents on real money."""
    board = snap.board.get("agents") or {}
    rows = []
    for agent_id, row in sorted(board.items()):
        if row.get("band") in NOT_REAL_BANDS or row.get("band") is None:
            continue
        agent = agents.get(agent_id)
        state = families.state(agent.venue, agent.family) if agent else {}
        rows.append({"agent": agent_id, "venue": row.get("venue"), "band": row.get("band"),
                     "family": agent.family if agent else None, "proven": bool(state.get("proven")),
                     "board_family_state": row.get("family_state"),
                     "stake_usd": round(float(row.get("stake_usd") or 0), 2)})
    proven = math.fsum(r["stake_usd"] for r in rows if r["proven"])
    unproven = math.fsum(r["stake_usd"] for r in rows if not r["proven"])
    ever = {r.agent for r in snap.rows("book.stake") if r.p.get("book") == "alpaca" and float(r.p.get("usd") or 0) > 0}
    # Once the board carries the House's own family state (C4), where it and this record differ.
    differ = [r["agent"] for r in rows if r["board_family_state"] is not None
              and (r["board_family_state"] in ("proven", "swing")) != r["proven"]]
    return {"fn": "real_dollars", "board_at": snap.board.get("at"), "board_disagrees": differ,
            "proven_usd": round(proven, 2), "unproven_usd": round(unproven, 2),
            "alpaca_real_agents": sum(1 for r in rows if r["venue"] == "alpaca"),
            "alpaca_real_agents_ever": len(ever), "rows": rows}


# ---------------------------------------------------------------------------------- metric 4
def deaths_in_window(agents: Mapping[str, Agent], fills: Mapping[str, Sequence[Row]], since: float, now: float,
                     rungs: Rungs | None = None) -> dict[str, Any]:
    """Deaths in the window: median life, overall and on day-horizon agents; deaths before 3 fills.

    With `rungs`, the same for the agents that held a practice seat (rung 1 or more at any point
    before their death): a replay-only agent (rung 0) has no book and can never fill, so while the
    House makes way with them the overall share before 3 fills measures who was chosen to die, not
    whether traders are killed before their evidence (B-seats' measure on the T0 snapshot, Sept 24,
    2026: 41 of the 72 deaths that remain under the evidence clock are rung-0 replay-only code)."""
    horizons = desk_horizons()
    dead = sorted((a for a in agents.values() if a.died is not None and since <= a.died <= now), key=lambda a: a.died)

    def day(agent: Agent) -> bool:
        if agent.horizon:
            return agent.horizon == "day"
        return horizons.get(agent.desk) == ["day"]

    def lived(rows: Sequence[Agent]) -> float | None:
        return _r(median([(a.died - a.born) / HOUR for a in rows]), 2) if rows else None

    few = [a for a in dead if sum(1 for f in fills.get(a.id, ()) if f.seq < (a.died_seq or 0)) < 3]
    day_dead = [a for a in dead if day(a)]
    day_desk_dead = [a for a in dead if horizons.get(a.desk) == ["day"]]
    return {"fn": "deaths_in_window", "since": iso(since), "deaths": len(dead),
            "median_life_h": lived(dead), "day_horizon_deaths": len(day_dead), "median_life_day_h": lived(day_dead),
            "day_desk_deaths": len(day_desk_dead), "median_life_day_desk_h": lived(day_desk_dead),
            "before_3_fills": len(few), "share_before_3_fills": _r(len(few) / len(dead)) if dead else None,
            "causes": dict(Counter(str(a.cause) for a in dead)),
            "day_horizon_before_3_fills": sum(1 for a in few if day(a)),
            **(seated_deaths(dead, few, rungs, lived) if rungs is not None else {})}


def seated_deaths(dead: Sequence[Agent], few: Sequence[Agent], rungs: Rungs, lived: Any) -> dict[str, Any]:
    """The deaths of agents that held a practice seat before they died (`Rungs`: a change to rung 1
    or more before the death row), their median life and the share of them that died before 3 fills."""
    def seated(agent: Agent) -> bool:
        return any(int(r.p.get("to_rung") or 0) >= 1 for r in rungs.changes.get(agent.id) or () if r.seq < (agent.died_seq or 0))

    held = [a for a in dead if seated(a)]
    held_few = [a for a in few if seated(a)]
    return {"seated_deaths": len(held), "median_life_seated_h": lived(held), "seated_before_3_fills": len(held_few),
            "share_seated_before_3_fills": _r(len(held_few) / len(held)) if held else None}


# ---------------------------------------------------------------------------------- metric 5
def waiting_cards(snap: Snapshot, agents: Mapping[str, Agent]) -> list[dict[str, Any]]:
    """Foundry cards that passed replay and were never born (`Foundry.inventory`, folded from the
    ledger). A card waits for a seat from its passing evaluation (the House's own list dates it from
    the card's creation, which counts its time in the replay queue as waiting)."""
    cards: dict[str, dict[str, Any]] = {}
    for row in snap.rows("hypothesis.card"):
        ident = row.p.get("id")
        if ident and ident not in cards:
            cards[str(ident)] = {**row.p, "_t": row.t}
    outcomes: dict[str, tuple[str, float]] = {}
    for row in snap.rows("trace.record"):
        if row.p.get("task") == "hypothesis.evaluate" and row.p.get("id"):
            outcomes[str(row.p["id"])] = (str(row.p.get("outcome")), row.t)
    by_strategy = {}
    for ident, card in sorted(cards.items(), key=lambda kv: kv[1]["_t"]):
        if card.get("strategy"):
            by_strategy[str(card["strategy"])] = ident
    born = set()
    for agent in agents.values():
        founder = str(agent.founder or "")
        if founder.startswith("card:"):
            born.add(founder[5:])
        elif founder in by_strategy:
            born.add(by_strategy[founder])
    # A card that left the House's seat queue (R2, Sept 24, 2026: its desk closed by the search) waits no more:
    # the House's `seat-expired:cards:<id>` row says so (`House._expire_waiters`).
    return [{"card": c, "niche": cards[c].get("niche"), "since": passed_at,
             "created": float(cards[c].get("created_epoch") or cards[c]["_t"])}
            for c, (outcome, passed_at) in outcomes.items() if outcome == "passed" and c in cards and c not in born
            and snap.at_of(f"seat-expired:cards:{c}") is None]


def research_children(snap: Snapshot, agents: Mapping[str, Agent], rungs: Rungs) -> list[dict[str, Any]]:
    """Real-money parents with a replay-passing research child: a fork (`agent.forked`) whose child
    passed a replay trial while the parent stood on rung 2 or 3; and what became of the parent."""
    passed: dict[str, Row] = {}
    for row in snap.rows("eval.trial"):
        if row.p.get("passed") and row.agent not in passed:
            passed[row.agent] = row
    out = []
    for row in snap.rows("agent.forked"):
        child = str(row.p.get("child") or "")
        trial = passed.get(child)
        if not child or trial is None or rungs.at(row.agent, trial.seq) < 2:
            continue
        parent = agents.get(row.agent)
        superseded = parent is not None and parent.cause == SUPERSEDED and (parent.died_seq or 0) > trial.seq
        demoted = any(c.seq > trial.seq and int(c.p.get("to_rung") or 0) < 2 for c in rungs.changes.get(row.agent, []))
        still_real = parent is not None and parent.alive and rungs.now(row.agent) >= 2
        out.append({"parent": row.agent, "child": child, "passed_at": iso(trial.t), "superseded": superseded,
                    "demoted_after": demoted, "parent_still_on_real_money": still_real})
    return out


def lab_loop(snap: Snapshot, agents: Mapping[str, Agent], rungs: Rungs, since: float) -> dict[str, Any]:
    """The loop's joints: lab batches, the LLM share of graduates, waiters, supersessions."""
    now = snap.now
    out: dict[str, Any] = {"fn": "lab_loop"}
    try:
        tables = {r[0] for r in snap.lab.execute("SELECT name FROM sqlite_master WHERE type='table'")} if snap.lab else set()
    except sqlite3.Error:
        tables = set()
    if {"batches", "graduations", "candidates"} <= tables:
        stamps = [float(r[0]) for r in snap.lab.execute("SELECT at FROM batches")]
        window_hours = max((now - since) / HOUR, 1e-9)
        out["batches_last_hour"] = sum(1 for t in stamps if now - HOUR <= t <= now)
        out["batches_an_hour_in_window"] = _r(sum(1 for t in stamps if since <= t <= now) / window_hours, 2)
        out["last_batch_at"] = iso(max(stamps)) if stamps else None
        born = Counter()
        born_window = Counter()
        waiting = []
        expired = 0
        for candidate, state, origin, at in snap.lab.execute(
                "SELECT g.candidate, g.state, c.origin, g.at FROM graduations g LEFT JOIN candidates c ON c.id = g.candidate"):
            origin = str(origin or "unknown")
            if state == "born":
                born[origin] += 1
                if float(at) >= since:
                    born_window[origin] += 1
            elif state == "passed":
                if snap.at_of(f"seat-expired:graduates:{candidate}") is not None:
                    expired += 1  # left the House's seat queue (R2, Sept 24, 2026): never counted as waiting
                    continue
                # From the ledger's `lab.graduate:<id>:passed` row, written once, as `Lab.waiting`
                # counts it: the table's `at` moves at every retry.
                passed = snap.at_of(f"lab.graduate:{candidate}:passed")
                waiting.append(passed if passed is not None else float(at))
        llm = sum(n for o, n in born.items() if o in LLM_ORIGINS)
        out["born_graduates"] = sum(born.values())
        out["born_graduates_llm"] = llm
        out["llm_share"] = _r(llm / sum(born.values())) if born else None
        out["born_graduates_by_origin"] = dict(born)
        out["born_graduates_in_window_by_origin"] = dict(born_window)
        out["graduates_waiting"] = len(waiting)
        out["graduates_left_the_queue"] = expired
        out["graduates_longest_wait_h"] = _r((now - min(waiting)) / HOUR, 2) if waiting else None
    cards = waiting_cards(snap, agents)
    out["cards_waiting"] = len(cards)
    out["cards_longest_wait_h"] = _r((now - min(c["since"] for c in cards)) / HOUR, 2) if cards else None
    waits = [w for w in (out.get("graduates_longest_wait_h"), out["cards_longest_wait_h"]) if w is not None]
    out["waiters"] = int(out.get("graduates_waiting") or 0) + len(cards)
    out["longest_wait_h"] = max(waits) if waits else None
    superseded = [a for a in agents.values() if a.cause == SUPERSEDED and a.died is not None and since <= a.died <= now]
    out["superseded_in_window"] = len(superseded)
    out["superseded_in_window_on_real_money"] = sum(1 for a in superseded if rungs.at(a.id, (a.died_seq or 0) - 1) >= 2)
    children = research_children(snap, agents, rungs)
    out["real_money_parents_with_passing_child"] = len({c["parent"] for c in children})
    out["of_them_superseded"] = len({c["parent"] for c in children if c["superseded"]})
    out["of_them_still_on_real_money"] = len({c["parent"] for c in children if c["parent_still_on_real_money"]})
    out["research_children"] = children
    return out


# ---------------------------------------------------------------------------------- metric 6
def self_cross_exits(snap: Snapshot, hours: float = SELF_CROSS_HOURS) -> dict[str, Any]:
    """Refusals of reducing orders by the self-cross rule in the last `hours`."""
    sides = {str(r.p.get("id")): r.p.get("side") for r in snap.rows("agent.intent") if r.p.get("id")}
    start = snap.now - hours * HOUR
    rows = [r for r in snap.rows("book.refused") if r.t >= start
            and any(SELF_CROSS in str(reason) for reason in r.p.get("reasons") or [])]
    reducing = [r for r in rows if sides.get(str(r.p.get("intent_id"))) == "sell"]
    return {"fn": "self_cross_exits", "hours": hours, "self_cross_refusals": len(rows),
            "reducing": len(reducing), "unknown_side": sum(1 for r in rows if str(r.p.get("intent_id")) not in sides),
            "by_agent": dict(Counter(r.agent for r in reducing).most_common(12))}


def bunt_gates() -> tuple[int, int]:
    """(`bunt_min_trades`, `bunt_min_settled`) from this checkout's constitution."""
    from league.constitution import CONSTITUTION

    rules = CONSTITUTION.get("allocator") or {}
    return int(rules.get("bunt_min_trades", 5)), int(rules.get("bunt_min_settled", 3))


def stacked_promotions(snap: Snapshot, agents: Mapping[str, Agent], trades: Sequence[Trade], baseline: float | None) -> dict[str, Any]:
    """Allocator promotions whose qualifying practice record has fewer distinct events than closes;
    and whether each would still pass the bunt line's counts with only settlements counted once per
    event (`passes_settled_per_event`: closes >= bunt_min_trades or events >= bunt_min_settled) and
    with every close counted once per event (`passes_all_per_event`)."""
    min_trades, min_settled = bunt_gates()
    by_agent: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        by_agent[trade.agent].append(trade)
    rows = []
    for row in snap.rows("eval.verdict"):
        p = row.p
        if p.get("decision") != "promote" or int(p.get("to_rung") or 0) < 2 or p.get("via") != "allocator":
            continue
        if baseline is not None and row.t < baseline:
            continue
        agent = agents.get(row.agent)
        book = PRACTICE_BOOK.get(agent.venue) if agent else None
        closes = [t for t in by_agent.get(row.agent, []) if t.book == book and t.close_seq < row.seq]
        events = len({t.event for t in closes})
        # `closed_trades` counts only settlements as settled (a sale is a closed trade, not a settlement).
        settled_events = len({t.event for t in closes if t.how == "settle" and book in EVENT_BOOKS})
        rows.append({"agent": row.agent, "at": iso(row.t), "closes": len(closes), "events": events,
                     "stacked": events < len(closes),
                     "passes_settled_per_event": len(closes) >= min_trades or settled_events >= min_settled,
                     "passes_all_per_event": events >= min_trades or settled_events >= min_settled})
    stacked = [r for r in rows if r["stacked"]]
    return {"fn": "stacked_promotions", "baseline": iso(baseline), "promotions": len(rows),
            "stacked": len(stacked), "gates": {"bunt_min_trades": min_trades, "bunt_min_settled": min_settled},
            "stacked_failing_settled_per_event": sum(1 for r in stacked if not r["passes_settled_per_event"]),
            "stacked_failing_all_per_event": sum(1 for r in stacked if not r["passes_all_per_event"]),
            "rows": rows}


# ---------------------------------------------------------------------------------- metric 7
def allowed_data_hosts() -> tuple[str, ...]:
    """The key-free data hosts the owner allowed on Sept 24, 2026: `LEAGUE_HOSTS` from the first of them on."""
    from scripts.floor_box import LEAGUE_HOSTS

    return tuple(LEAGUE_HOSTS[LEAGUE_HOSTS.index(FIRST_ALLOWED_DATA_HOST):])


def names_host(text: str, host: str) -> bool:
    """Whether `text` names `host` itself (`api.open-meteo.com` is not named by `ensemble-api.open-meteo.com`)."""
    return re.search(r"(?<![A-Za-z0-9.-])" + re.escape(host) + r"(?!\.?[A-Za-z0-9-])", text) is not None


def recorders_live(snap: Snapshot, hosts: Sequence[str] | None = None, hours: float = RECORDER_HOURS) -> dict[str, Any]:
    """The allowed data hosts with a feed recorded in the last `hours`."""
    hosts = tuple(hosts) if hosts is not None else allowed_data_hosts()
    start = snap.now - hours * HOUR
    sources: dict[str, set[str]] = defaultdict(set)  # feed -> source texts
    coverage_live: set[str] = set()
    for row in snap.rows("data.coverage"):
        p = row.p
        if p.get("asset") != "feed" or not p.get("feed"):
            continue
        feed = str(p["feed"])
        sources[feed].add(str(p.get("source") or ""))
        for backfill in (p.get("backfill") or {}).values():
            if isinstance(backfill, Mapping):
                sources[feed].add(str(backfill.get("source") or ""))
        try:
            end = epoch(p["end"]) if p.get("end") else None
        except (TypeError, ValueError):
            end = None
        if row.t >= start and p.get("status") != "unavailable" and end is not None and end >= start:
            coverage_live.add(feed)
    store_live: set[str] | None = None
    if snap.feeds is not None:
        store_live = set()
        queries = (("SELECT DISTINCT feed, source FROM backfills", (), "source"),
                   ("SELECT DISTINCT feed, NULL FROM polls WHERE ok = 1 AND finished >= ?", (start,), "live"),
                   ("SELECT DISTINCT feed, NULL FROM snapshots WHERE received >= ?", (start,), "live"))
        for query, args, what in queries:
            try:
                rows = snap.feeds.execute(query, args).fetchall()
            except sqlite3.Error:  # a store from before a table existed: what it lacks is not recorded
                continue
            for feed, source in rows:
                if what == "source":
                    sources[str(feed)].add(str(source or ""))
                else:
                    store_live.add(str(feed))
    live_feeds = store_live if store_live is not None else coverage_live
    rows = []
    for host in hosts:
        feeds = sorted(f for f, texts in sources.items() if any(names_host(t, host) for t in texts))
        rows.append({"host": host, "feeds": feeds, "live": any(f in live_feeds for f in feeds)})
    return {"fn": "recorders_live", "basis": "feeds.sqlite" if store_live is not None else "data.coverage rows",
            "hosts": len(hosts), "live": sum(1 for r in rows if r["live"]), "rows": rows,
            "feeds_live": sorted(live_feeds)}


def idle_desks(snap: Snapshot, agents: Mapping[str, Agent], hours: float = IDLE_DESK_HOURS) -> dict[str, Any]:
    """Desks whose members were offered markets in the last `hours` and placed no intent."""
    start = snap.now - hours * HOUR
    offered: Counter = Counter()
    wakes: Counter = Counter()
    intents: Counter = Counter()
    for row in snap.rows("agent.woke"):
        agent = agents.get(row.agent)
        if row.t < start or agent is None:
            continue
        wakes[agent.desk] += 1
        offered[agent.desk] += int(row.p.get("offered") or 0)
        intents[agent.desk] += int(row.p.get("intents") or 0)
    for row in snap.rows("agent.intent"):
        agent = agents.get(row.agent)
        if row.t >= start and agent is not None:
            intents[agent.desk] += 1
    desks = sorted(d for d in wakes if offered[d] > 0 and intents[d] == 0)
    return {"fn": "idle_desks", "hours": hours, "desks": desks, "count": len(desks),
            "offered": {d: offered[d] for d in desks}, "wakes": {d: wakes[d] for d in desks}}


# --------------------------------------------------------------------------------- the extras
def kaplan_meier_median(times: Sequence[tuple[float, bool]]) -> float | None:
    """The median of (time, reached) with the unreached censored at their time; None when the
    survival curve never falls to one half."""
    rows = sorted(times)
    at_risk, survival = len(rows), 1.0
    i = 0
    while i < len(rows):
        t = rows[i][0]
        events = censored = 0
        while i < len(rows) and rows[i][0] == t:
            events += 1 if rows[i][1] else 0
            censored += 0 if rows[i][1] else 1
            i += 1
        if events:
            survival *= 1.0 - events / at_risk
            if survival <= 0.5:
                return t
        at_risk -= events + censored
    return None


def evidence_clocks(snap: Snapshot, agents: Mapping[str, Agent], trades: Sequence[Trade], fills: Mapping[str, Sequence[Row]],
                    days: float = EVIDENCE_CLOCK_DAYS) -> dict[str, Any]:
    """Per desk: hours from a member's first own fill to its third independent settlement (distinct
    events on Kalshi, closed trades on Alpaca, any book; the House's closing sales left out), for
    members whose first fill is in the last `days`."""
    start = snap.now - days * DAY
    by_agent: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        by_agent[trade.agent].append(trade)
    desks: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    for agent in agents.values():
        own = fills.get(agent.id) or []
        if not own or own[0].t < start:
            continue
        first = own[0].t
        seen: set[str] = set()
        third = None
        for trade in sorted(by_agent.get(agent.id, []), key=lambda t: t.close_seq):
            # The House's sale of a dead member's holdings is the House's close, not the member's
            # (the House's own clock, `House._evidence_clocks`, leaves it out since the B-seats review).
            if trade.close_t < first or trade.closing:
                continue
            seen.add(trade.event)
            if len(seen) == 3:
                third = trade.close_t
                break
        if third is not None:
            desks[agent.desk].append(((third - first) / HOUR, True))
        else:
            desks[agent.desk].append((((agent.died or snap.now) - first) / HOUR, False))
    out = {}
    for desk, rows in sorted(desks.items()):
        reached = [t for t, ok in rows if ok]
        out[desk] = {"members": len(rows), "reached": len(reached),
                     "median_reached_h": _r(median(reached), 1) if reached else None,
                     "km_median_h": _r(kaplan_meier_median(rows), 1),
                     "censored_longest_h": _r(max((t for t, ok in rows if not ok), default=0.0), 1)}
    return {"fn": "evidence_clocks", "days": days, "desks": out}


def weather_capacity(snap: Snapshot, families: Families, intents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The weather-favourites family's capacity: markets in its band a day, fill rates by size, settlements a day."""
    key = ("kalshi", WEATHER_FAMILY)
    out = family_capacity(snap, "kalshi", WEATHER_FAMILY, families.members.get(key) or [], families.trades.get(key) or [], intents)
    out["fn"] = "weather_capacity"
    return out


# ----------------------------------------------------------------------------------- the board
def scoreboard(snap: Snapshot, *, since: float | None = None, baseline: float | None = None,
               hosts: Sequence[str] | None = None, house_records: bool = True) -> dict[str, Any]:
    """Every metric and extra of one snapshot. `house_records` False reads every family record with the
    scoreboard's own account-unit formula instead of the House's function (the tests of that formula)."""
    since = snap.now - DAY if since is None else since
    agents = agents_of(snap)
    rungs = Rungs(snap)
    trades, still_open, skipped = closed_trades(snap)
    fills = own_fills(snap)
    families = Families(agents, trades, HouseRecords.open(snap, agents) if house_records else None)
    intents = intent_outcomes(snap)
    health = snap.json.get("health.json") or {}
    return {
        "snapshot": {"dir": str(snap.root), "ledger_rows": snap.rows_total, "newest": snap.newest_at,
                     "since": iso(since), "baseline": iso(baseline), "release": health.get("release"),
                     "board_at": snap.board.get("at"), "feeds_store": snap.feeds is not None,
                     "trades": len(trades), "open_positions": len(still_open), "skipped": skipped},
        "metrics": {
            "1": real_bounds(snap, families, intents),
            "2": allocator_promotions(snap, agents, rungs, trades, still_open, families, baseline),
            "3": real_dollars(snap, agents, families),
            "4": deaths_in_window(agents, fills, since, snap.now, rungs),
            "5": lab_loop(snap, agents, rungs, since),
            "6": {"self_cross": self_cross_exits(snap), "stacked": stacked_promotions(snap, agents, trades, baseline)},
            "7": {"recorders": recorders_live(snap, hosts), "idle_desks": idle_desks(snap, agents)},
        },
        "extras": {
            "evidence_clocks": evidence_clocks(snap, agents, trades, fills),
            "family_records": family_records(snap, agents, families),
            "weather_capacity": weather_capacity(snap, families, intents),
        },
    }


# ---------------------------------------------------------------------------------- rendering
def _usd(value: float | None) -> str:
    return "-" if value is None else f"${value:,.2f}" if value >= 0 else f"-${-value:,.2f}"


def _num(value: float | None, digits: int = 4) -> str:
    return "-" if value is None else f"{value:+.{digits}f}"


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def _rec(rec: Mapping[str, Any]) -> str:
    """A pooled record in one short phrase: n, n_eff, mean, sd, lcb."""
    if not rec.get("n"):
        return "n 0"
    n_eff = rec.get("n_eff")
    sd = rec.get("sd")
    return (f"n {rec['n']} (eff {n_eff:.1f}) mean {_num(rec['mean'])} sd {'-' if sd is None else f'{sd:.4f}'} "
            f"lcb {_num(rec['lcb'])}{' PROVEN' if rec.get('proven') else ''}")


def summary_rows(board: Mapping[str, Any]) -> list[tuple[str, str, str, str]]:
    """(#, metric, reading, computed by) for the seven metrics."""
    m = board["metrics"]
    one, two, three, four, five = m["1"], m["2"], m["3"], m["4"], m["5"]
    six, seven = m["6"], m["7"]
    caps = "; ".join(f"{r['family']} real n {r['real']['n']}, {_usd(r['capacity'].get('capacity_usd_per_day'))}/day"
                     for r in one["families"]) or "none"
    proven_caps = "; ".join(f"{r['family']} n {r['pooled']['n']}, real n {(r.get('real') or {}).get('n', 0)}, "
                            f"{_usd(r['capacity'].get('capacity_usd_per_day'))}/day" for r in one.get("proven") or ()) or "none"
    labels = ", ".join(f"{k} {v}" for k, v in sorted(two["labels"].items()))
    stacked = six["stacked"]
    return [
        ("1", "families with a positive real lower bound; capacity (and proven by the House's pooled record)",
         f"{one['count']} ({caps}); {one['with_enough_real_events']} on >= {PROVEN_MIN_OBSERVATIONS} real events; "
         f"proven ({one.get('record', 'scoreboard')} record): {len(one.get('proven') or ())} ({proven_caps})",
         "real_bounds, family_capacity"),
        ("2", "allocator promotions to real money: settled result, share positive" + (" (since the baseline)" if two["baseline"] else ""),
         f"{two['promotions']} promotions, {_usd(two['settled_pnl_usd'])} on {two['settlements']} settlements, "
         f"{two['positive']} positive ({_pct(two['share_positive'])})" + (f"; {labels}" if two["baseline"] else ""),
         "allocator_promotions"),
        ("3", "real dollars in proven / unproven families; Alpaca real agents",
         f"{_usd(three['proven_usd'])} / {_usd(three['unproven_usd'])}; {three['alpaca_real_agents']}", "real_dollars"),
        ("4", "median life (h), all / day-horizon; deaths before 3 fills (of them, agents that held a practice seat)",
         f"{four['median_life_h']} / {four['median_life_day_h']} h over {four['deaths']} deaths; "
         f"{four['before_3_fills']} ({_pct(four['share_before_3_fills'])}); seated: {four.get('seated_deaths')} deaths, "
         f"median {four.get('median_life_seated_h')} h, {four.get('seated_before_3_fills')} "
         f"({_pct(four.get('share_seated_before_3_fills'))}) before 3 fills", "deaths_in_window"),
        ("5", "lab batches an hour; LLM share of born graduates; waiters, longest wait; supersessions",
         f"{five.get('batches_last_hour')} in the last hour; {five.get('born_graduates_llm')} of {five.get('born_graduates')}; "
         f"{five['waiters']} at {five['longest_wait_h']} h; {five['superseded_in_window']} superseded in the window "
         f"({five['superseded_in_window_on_real_money']} on real money), {five['of_them_superseded']} of "
         f"{five['real_money_parents_with_passing_child']} real-money parents with a passing research child", "lab_loop"),
        ("6", "self-cross refusals of reducing orders (6 h); promotions on stacked positions",
         f"{six['self_cross']['reducing']}; {stacked['stacked']} of {stacked['promotions']} (below the bunt counts: "
         f"{stacked['stacked_failing_all_per_event']} with every close counted per event, "
         f"{stacked['stacked_failing_settled_per_event']} with settlements only)",
         "self_cross_exits, stacked_promotions"),
        ("7", "recorders live on the allowed hosts; desks offered markets with no intent (48 h)",
         f"{seven['recorders']['live']} of {seven['recorders']['hosts']}; {seven['idle_desks']['count']} "
         f"({', '.join(seven['idle_desks']['desks']) or '-'})", "recorders_live, idle_desks"),
    ]


def _capacity_line(c: Mapping[str, Any]) -> str:
    if c.get("capacity_usd_per_day") is None and c.get("why"):
        return f"capacity - ({c['why']})"
    return (f"capacity {_usd(c.get('capacity_usd_per_day'))}/day = {c.get('markets_per_day')} markets bid a day "
            f"({c.get('markets_bid')} over {c.get('days')} days) x fill rate {c.get('fill_rate_at_size')} "
            f"({c.get('fill_rate_basis')}, bids {c.get('size_bucket')}, median {_usd(c.get('current_size_usd'))}) x "
            f"{_usd(c.get('profit_per_settlement_usd'))} a settlement ({c.get('profit_basis')}, n {c.get('settlements')}); "
            f"real seats earn {_usd(c.get('real_earning_usd_per_day'))}/day now")


def render_text(board: Mapping[str, Any], *, markdown: bool = False) -> str:
    """The table (text, or markdown for the run record), then each metric's rows and the extras."""
    s = board["snapshot"]
    m = board["metrics"]
    x = board["extras"]
    out = []
    head = (f"gap scoreboard: ledger {s['ledger_rows']:,} rows to {s['newest']}; window since {s['since']}; "
            f"baseline {s['baseline'] or '-'}; release {s['release'] or '-'}; board {s['board_at'] or '-'}; "
            f"feeds store {'yes' if s['feeds_store'] else 'no'}")
    out.append(("# " if markdown else "") + head)
    out.append("")
    rows = summary_rows(board)
    if markdown:
        out.append("| # | Metric | Reading | Computed by |")
        out.append("|---|---|---|---|")
        out += [f"| {a} | {b} | {c} | `{d}` |" for a, b, c, d in rows]
    else:
        out += [f"{a}  {b}\n   {c}   [{d}]" for a, b, c, d in rows]
    pre = "- " if markdown else "   "

    def section(title: str) -> None:
        out.append("")
        out.append(("## " if markdown else "== ") + title)

    section("1. families with a positive real lower bound [real_bounds, family_capacity]")
    out.append(f"{pre}the family record read: {m['1'].get('record', 'scoreboard')} "
               f"({'the House own function, league.families / league.allocator family_record' if m['1'].get('record') == 'house' else 'the scoreboard account-unit formula'})")
    for r in m["1"]["families"]:
        rows = f"; {r['real']['rows']} rows, P&L {_usd(r['real']['pnl_usd'])}" if "rows" in r["real"] else ""
        out.append(f"{pre}{r['venue']}/{r['family']}: real {_rec(r['real'])}{rows}")
        out.append(f"{pre}  {_capacity_line(r['capacity'])}")
    for r in m["1"].get("proven") or ():
        out.append(f"{pre}PROVEN {r['venue']}/{r['family']}: pooled {_rec(r['pooled'])}; real {_rec(r.get('real') or {})}")
        out.append(f"{pre}  {_capacity_line(r['capacity'])}")
    out.append(f"{pre}families with any real closed trade: {m['1']['real_families']}")
    section("2. allocator promotions to real money [allocator_promotions]")
    for r in m["2"]["rows"]:
        out.append(f"{pre}{r['at']} {r['agent']} ({r['family']}) to rung {r['to_rung']}, stake {r['stake_usd']}: "
                   f"{_usd(r['settled_pnl_usd'])} on {r['settlements']} settlements ({r['independent_events']} events), "
                   f"{r['open_positions']} open; stay ended {r['ended'] or 'no'}; {r['label']} ({r['label_source']})")
    section("3. real dollars by family state [real_dollars]")
    for r in m["3"]["rows"]:
        out.append(f"{pre}{r['agent']} {r['venue']} {r['band']} {_usd(r['stake_usd'])} {r['family']} "
                   f"{'proven' if r['proven'] else 'unproven'}" + (f" (board: {r['board_family_state']})" if r["board_family_state"] else ""))
    out.append(f"{pre}Alpaca agents ever staked on real money: {m['3']['alpaca_real_agents_ever']}")
    if m["3"]["board_disagrees"]:
        out.append(f"{pre}the board's family state differs from this record for: {', '.join(m['3']['board_disagrees'])}")
    section("4. deaths in the window [deaths_in_window]")
    d = m["4"]
    out.append(f"{pre}{d['deaths']} deaths since {d['since']}; causes {d['causes']}")
    out.append(f"{pre}day-horizon agents: {d['day_horizon_deaths']} deaths, median {d['median_life_day_h']} h, "
               f"{d['day_horizon_before_3_fills']} before 3 fills; on day-only desks: {d['day_desk_deaths']} deaths, "
               f"median {d['median_life_day_desk_h']} h")
    if "seated_deaths" in d:
        out.append(f"{pre}agents that held a practice seat: {d['seated_deaths']} deaths, median {d['median_life_seated_h']} h, "
                   f"{d['seated_before_3_fills']} ({_pct(d['share_seated_before_3_fills'])}) before 3 fills; the rest never "
                   f"left replay (rung 0) and could not fill")
    section("5. the lab and the loop [lab_loop]")
    f = m["5"]
    out.append(f"{pre}batches: {f.get('batches_last_hour')} in the last hour, {f.get('batches_an_hour_in_window')} an hour over the "
               f"window, the last at {f.get('last_batch_at')}")
    out.append(f"{pre}born graduates by origin {f.get('born_graduates_by_origin')}; in the window {f.get('born_graduates_in_window_by_origin')}")
    out.append(f"{pre}waiting: {f.get('graduates_waiting')} graduates (longest {f.get('graduates_longest_wait_h')} h since passing), "
               f"{f['cards_waiting']} cards (longest {f['cards_longest_wait_h']} h since passing replay)")
    out.append(f"{pre}superseded in the window: {f['superseded_in_window']} ({f['superseded_in_window_on_real_money']} on real money); "
               f"real-money parents with a replay-passing research child: {f['real_money_parents_with_passing_child']} "
               f"({f['of_them_superseded']} superseded, {f['of_them_still_on_real_money']} still on real money)")
    for c in f["research_children"]:
        out.append(f"{pre}  {c['parent']} -> {c['child']} passed replay {c['passed_at']}; parent superseded {c['superseded']}, "
                   f"demoted since {c['demoted_after']}, on real money now {c['parent_still_on_real_money']}")
    section("6. exits and stacked records [self_cross_exits, stacked_promotions]")
    sc = m["6"]["self_cross"]
    out.append(f"{pre}self-cross refusals in {sc['hours']:g} h: {sc['self_cross_refusals']}, of them reducing (sell intents) "
               f"{sc['reducing']}; by agent {sc['by_agent']}")
    st = m["6"]["stacked"]
    out.append(f"{pre}bunt counts: {st['gates']['bunt_min_trades']} closed trades or {st['gates']['bunt_min_settled']} settlements")
    for r in st["rows"]:
        if r["stacked"]:
            out.append(f"{pre}{r['at']} {r['agent']}: {r['closes']} practice closes on {r['events']} events; passes with "
                       f"settlements per event {r['passes_settled_per_event']}, with every close per event {r['passes_all_per_event']}")
    section("7. inputs [recorders_live, idle_desks]")
    rec = m["7"]["recorders"]
    out.append(f"{pre}read from {rec['basis']}; feeds live in the last day: {rec['feeds_live'] or '-'}")
    out += [f"{pre}{r['host']}: {'LIVE' if r['live'] else 'not recorded'} (feeds {', '.join(r['feeds']) or '-'})" for r in rec["rows"]]
    idle = m["7"]["idle_desks"]
    out += [f"{pre}{desk}: {idle['offered'][desk]} markets offered over {idle['wakes'][desk]} wakes, no intent" for desk in idle["desks"]]
    section("evidence clocks: first fill to the third independent settlement, members whose first fill is in the last 7 days [evidence_clocks]")
    for desk, r in x["evidence_clocks"]["desks"].items():
        km = r["km_median_h"]
        out.append(f"{pre}{desk}: Kaplan-Meier median {km if km is not None else 'not reached'} h; {r['reached']} of {r['members']} "
                   f"reached it (median {r['median_reached_h']} h among them); the longest still waiting or dead first "
                   f"{r['censored_longest_h']} h")
    section("family records: practice 0.5 + real 1, one observation an event [family_records]")
    fr = x["family_records"]
    out.append(f"{pre}{fr['with_observations']} of {len(fr['families'])} families have a closed trade; proven: {', '.join(fr['proven']) or 'none'}")
    for r in fr["families"]:
        if not r["pooled"]["n"]:
            continue
        out.append(f"{pre}{r['venue']}/{r['family']}: {_rec(r['pooled'])}; members {r['members']} ({r['living']} living), "
                   f"real stake {_usd(r['real_stake_usd'])}")
        out.append(f"{pre}  practice (account unit) {_rec(r['practice'])} | real {_rec(r['real'])} | maker {_rec(r['maker'])} | taker {_rec(r['taker'])}")
    section("the weather favourites' capacity [weather_capacity]")
    w = x["weather_capacity"]
    out.append(f"{pre}{_capacity_line(w)}")
    out.append(f"{pre}settlements a day over {w.get('days')} days: {w.get('settlements_per_day')}; practice profit a settlement "
               f"{_usd(w.get('practice_profit_per_settlement_usd'))}")
    for kind, buckets in (w.get("fill_rates_by_book") or {}).items():
        for bucket, r in buckets.items():
            out.append(f"{pre}{kind} bids {bucket}: {r['markets_filled']} of {r['markets_bid']} markets filled ({r['fill_rate']}), "
                       f"{r['bids_filled']} of {r['bids']} bids")
    return "\n".join(out)


# -------------------------------------------------------------------------------------- take
BOX_SNAPSHOT = r'''
import gzip, os, pathlib, shutil, sqlite3, sys
out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
state = pathlib.Path('/workspace/state')
for name in sys.argv[2:]:
    source = state / name
    if not source.exists():
        print('missing', name)
        continue
    target = out / name
    if target.exists():
        target.unlink()
    src = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    dst = sqlite3.connect(str(target))
    src.backup(dst, pages=4096, sleep=0.05)
    dst.close()
    src.close()
    with open(target, 'rb') as f, gzip.open(str(target) + '.gz', 'wb', compresslevel=4) as g:
        shutil.copyfileobj(f, g)
    target.unlink()
    print('ok', name, os.path.getsize(str(target) + '.gz'))
'''


def take(directory: str | Path, api: Any = None, box: str | None = None) -> list[str]:
    """Snapshot the House's stores into `directory`: a sqlite backup of each store on the box (read
    `mode=ro`) into a /tmp directory there, gzipped and downloaded, the JSON files downloaded as they
    are; the box copies are deleted whatever happens. Returns the files written."""
    from scripts.floor_box import STATE_DIR, client, read_state, require_box

    api = api if api is not None else client()
    box = box if box is not None else require_box(read_state())
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    remote = f"/tmp/gap-scoreboard-{int(time.time())}"
    written: list[str] = []
    try:
        run = api.exec(box, [BOX_PYTHON, "-c", BOX_SNAPSHOT, remote, *SNAPSHOT_SQLITE], timeout=1800, on_output=None)
        if not getattr(run, "ok", True):
            raise SystemExit(f"the box's backup failed: {(getattr(run, 'stderr', '') or '')[-2000:]}")
        stored = [line.split()[1] for line in (run.stdout or "").splitlines() if line.startswith("ok ")]
        for name in stored:
            data = api.download(box, f"{remote}/{name}.gz", timeout=1800)
            target = directory / name
            with gzip.open(io.BytesIO(bytes(data))) as source, open(target, "wb") as sink:
                shutil.copyfileobj(source, sink)
            written.append(name)
        for name in SNAPSHOT_JSON:
            try:
                data = api.download(box, f"{STATE_DIR}/{name}", timeout=300)
            except Exception:  # noqa: BLE001 - a JSON file the House has not written is absent, not fatal
                continue
            (directory / name).write_bytes(bytes(data))
            written.append(name)
    finally:
        api.exec(box, ["rm", "-rf", remote], timeout=120, on_output=None)
    return written


# -------------------------------------------------------------------------------------- main
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--snapshot", metavar="DIR", help="read a snapshot directory")
    where.add_argument("--take", metavar="DIR", help="take a snapshot from the House box into DIR, then read it")
    parser.add_argument("--since", help="start of the windowed rows (ISO; default 24 h before the newest ledger row)")
    parser.add_argument("--baseline", help="count promotions only after this moment (ISO), e.g. Deploy A")
    form = parser.add_mutually_exclusive_group()
    form.add_argument("--json", action="store_true", help="machine output")
    form.add_argument("--markdown", action="store_true", help="the table for the run record")
    args = parser.parse_args(argv)
    if args.take:
        take(args.take)
    snap = Snapshot(args.take or args.snapshot)
    try:
        board = scoreboard(snap, since=epoch(args.since) if args.since else None,
                           baseline=epoch(args.baseline) if args.baseline else None)
    finally:
        snap.close()
    if args.json:
        print(json.dumps(board, indent=1, default=str))
    else:
        print(render_text(board, markdown=args.markdown))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
