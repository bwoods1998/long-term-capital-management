#!/usr/bin/env python3
"""The gap scoreboard: the forward-first run's seven rows and the close-the-gaps run's seven metrics, read from a
snapshot of the House.

    python3 scripts/gap_scoreboard.py --snapshot DIR [--since ISO] [--baseline ISO] [--deploys FILE] [--json | --markdown]
    python3 scripts/gap_scoreboard.py --take DIR [--since ISO] [--baseline ISO] [--json | --markdown]

Workstream Z of docs/goals/LTCM_FORWARD_FIRST.md (and before it of docs/goals/LTCM_CLOSE_THE_GAPS.md): read at
T0, every four hours and at the end of a run. Read-only and standard library only (it borrows `league.stats`,
itself standard library, so its bound is the ladder's own; `scripts/economics.py` for compute, as the plan's
lifetime figures were measured; `ltcm.data`'s NYSE calendar for the US session): the sqlite files are opened
`mode=ro`, the JSON files are read, and nothing is written anywhere except DIR under `--take`. Every number it
prints names the function that computed it. `--take` runs on the owner's machine like `scripts/floor_watch.py`:
it takes a sqlite backup of the House's stores on the box into /tmp, gzips it, downloads it through
`scripts.floor_box.client().download` with the JSON files and the watchdog's `deploys.jsonl`, deletes the box
copies, and then reads what it fetched.

A snapshot directory holds `ledger.sqlite`, `lab.sqlite`, `campaigns.sqlite`, `feeds.sqlite` (the
House's feed store, `league/feeds.py`), `health.json`, `house.json`, `allocator-board.json` and
`deploys.jsonl` (the watchdog's record, `/workspace/deploys.jsonl`; `--deploys FILE` names one kept
elsewhere); only the ledger is required. The clock is the snapshot's newest ledger row, never this machine's:
windows are measured back from it, and instants are compared as instants, never as strings
(sqlite's `datetime('now', ...)` puts a space where the ledger puts `T`, which once let a whole day
into a six-hour window).

THE FORWARD-FIRST ROWS (docs/goals/LTCM_FORWARD_FIRST.md "The scoreboard", Sept 25, 2026; the first table)

Each row is the plan's row of the same number; each number in it names the function that computed it, and the
plan's target is printed beside it. Windows end at the snapshot's newest ledger row and start at `--since`
(default 24 hours before it); "a day" is the window's figure scaled to 24 hours.

1. `real_settled`: the real books' realized result net of fees, as `league.merton.RealPnl` reads it for
   `merton.paused_until_profit` (health.json `research_economy.merton.real_pnl_24h_usd`): each `book.settle`
   `pnl` (payout less a cost that holds the buy fees) and each closing fill's `realized` on `kalshi` and
   `alpaca`, dust rows never; settlements and sales apart. `compute_per_day`: the window's spend by
   `scripts/economics.py` `spend`, the method of the plan's lifetime $562 (Luna: `provider.request`
   gateway-verified `cost_usd`; Astra: `merton.pass`, `audit.verdict`, research grants and `ops.budget` probes,
   gateway-metered; Sail: the balance-debit meter, `ops.budget` `what: sail` `spent_usd`; Jev and web search:
   credit charges), plus the Alpha Lab's model calls, which live in `lab.sqlite` `calls` and never on the ledger
   ($4.50 in the T0 day). Two checks are printed beside it and never added: the House's OpenAI line as the
   gateway meters it (`ops.budget` expedition rows, `campaign.meters.openai.line.settled_usd`, lab calls
   included: $96.41 a day over 21.4 h against the ledger's $98.19 + $4.50 at T0), and the hourly yield rows (`ops.budget`
   `what: yield`, `league/yield_ledger.py`: research tokens, Merton's roles and audits, which the lines above
   already carry). `proven_capacity`: each family the House's pooled record proves, with the board's own
   capacity (`allocator-board.json` `families`), and `capacity_at_sizes`: `family_capacity`'s factors at the
   family's real size (the median real bid of the last 7 days) and at 2x and 4x of it -- the markets a day
   are the band's, the fill rate is the one measured at that size's bucket (none when no bid of that size was
   ever placed), and the profit a settlement is scaled with the size (the same edge a dollar).
2. `forward_positive`: the window's lab graduates (a `lab.graduate:<id>:passed` row in the window, dated as
   `Lab.waiting` dates them) whose latest lab forward window (`lab.sqlite` `forward`) has an active block, and
   the share of them whose log growth is above zero; the window's newborns with an active block on their
   venue's practice book in their first 24 hours (`eval.block`), and the share whose summed log growth is above
   zero, with the newborns whose first day already ended beside it; and the plan's own baseline measure (its 118
   of 224, 53%; 116 of 215 read here at 02:12Z Sept 25): the active `eval.block` rows of lab-born agents
   (`founder` `lab:`) in the window with positive log growth. `practice_standing`: the board's median `W_paper`
   and the agents above the 1.01 line (`W_paper` > 1.01, the plan's count: 33 on the 01:41Z board), with those
   whose E is at the constitution's `bunt_at` beside it.
3. `real_dollars` (metric 3 below: the board's real stakes on proven and on unproven families);
   `capital_on_proof`: the first family swing (a board family in state `swing`, or the first `family.record`
   or `eval.verdict` that names one) and each proven family's swing clock on the board (real settlements, the
   look it waits for, days to it); Alpaca real stock agents ever: agents with a real `alpaca` buy fill of an
   `equity` instrument (and how many of them filled inside a US session), and agents ever staked on the real
   book on an equity desk (league/niches.json `asset_class`).
4. `restarts`: `ops.started` rows in the window, and inside a US session. `deploy_record`: every deploy and its
   verdict from the watchdog's log (`deploys.jsonl`), else from the ledger: `ops.deploy` `deploying` rows are
   the updater's deploys and a first `ops.started` of a release no such row announced an owner's; a start of
   the release that ran before, within 30 minutes and before the next deploy, is its rollback, and the first
   error alert between is its reason. A release killed before it wrote `ops.started` is invisible to the
   ledger (the owner's 00:02Z release of Sept 25 was one), which is why the log comes first. A rollback's
   cause is read from its reasons' words: `backup` (backup, checkpoint), `vendor` (Sailbox, a 5xx, a timeout,
   Cloudflare), `site` (publish, the site), else `house`. A deploy is inside a US session when its start or
   its promotion is (the regular session on the NYSE calendar, `us_session`). `tick_p50`: the median interval
   between ticks, from the `ops.job` rows of `merton:follow`, which every tick submits once and whose job id
   carries the moment: intervals whose earlier job ended within 10 s (so no tick between skipped it) and with
   no restart between. The loop sleeps a tick up to `tick_seconds` (60), so an interval reads a tick's length
   only above 60 s; health.json's last tick (`tick_steps.last.total_seconds`) and its hour's slowest steps
   are beside it.
5. `seat_queue`: health.json `seats` (the House's seat market, refreshed hourly; its `at` is printed): the
   waiters by class, those over two hours and the longest, those on desks with a free seat, and the merged
   strategies waiting (class `strategies`). `life_vs_clock`: per desk, the median life of the window's dead
   beside the desk's evidence clock (`seats.evidence_clocks`, else the scoreboard's own Kaplan-Meier median).
   `displacement_share`: deaths of cause `displaced`, in the window and over the ledger's life.
6. `real_fill_rate`: orders first placed on a real book in the window (`book.order`: one order however many
   status rows it has) and those with a venue fill; the baseline's measure beside it, fill rows over order
   rows, which counts every status row as an order (the plan's 72 of 694, 10%; on the T0 day 62 fill rows of 695
   order rows, where 61 of 165 orders filled, 37%). `real_refusals`: refused real entries (`book.refused` on a real book whose intent was a buy), a day
   and in the last US session, by the constitution key each reason names. `probe_taker_entries`: real buy
   fills taken as a taker, by the band the agent held then (`eval.verdict` `band_to` or `band`), and probes'
   entries refused for taking (`allocator.real_entry_liquidity`).
7. `runway`: Sail's balance, burn and runway from the meter (`ops.budget` `what: sail`) less the reserve,
   beside the House's own (health.json `seats.population.sail`); the OpenAI month the gateway reports and its
   cap, October's cap unset until the gateway's month is 2026-10 or later; whether the population ceiling
   binds on runway (`seats.population` `max_population` under `ceiling`) and the population alerts in the
   window.

THE CLOSE-THE-GAPS METRICS (docs/goals/LTCM_CLOSE_THE_GAPS.md; kept, the second table)

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

The seven metrics (numbers in brackets: that plan's baseline at 00:50Z Sept 24)

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
#: The watchdog's own record of every deploy (`league/watchdog.py` `Releases.record`), beside the stores.
DEPLOYS_JSONL = "deploys.jsonl"
BOX_PYTHON = "/workspace/.venv/bin/python"
#: The first of the key-free data hosts the owner allowed on Sept 24, 2026 (`LEAGUE_HOSTS`' last block).
FIRST_ALLOWED_DATA_HOST = "api.open-meteo.com"

# The forward-first rows (Sept 25, 2026).
#: Every tick submits this job to the ops lane once (`House._tick`); its job id ends in the moment it was queued.
TICK_JOB = "merton:follow"
#: An interval counts only when the earlier job ended within this: a job still in the lane at the next tick is
#: skipped there (`House._background`, one job a key), and that interval would span two ticks. Measured on the T0
#: day: 1,014 of 1,017 intervals qualify (the lane's longest wait behind a Merton role was 11.3 s) and 25 more
#: span a restart.
TICK_JOB_DONE_SECONDS = 10.0
#: The ledger's reading of a rollback: a start of the release that ran before, this soon after a deploy (the
#: watchdog's canary and watch take about fifteen minutes).
ROLLBACK_WATCH_SECONDS = 1800.0
#: A rollback's cause from the words of its reasons, first match wins; anything else is the House's own.
ROLLBACK_CAUSES = (
    ("backup", ("backup", "checkpoint")),
    ("vendor", ("sailbox", "sail api", "api 5", "http 5", "503", "502", "504", "service unavailable", "timed out",
                "cloudflare")),
    ("site", ("publish", "the site", "blakewoods")),
)
OUTSIDE_THE_HOUSE = ("backup", "vendor", "site")
#: Capacity is measured at the real size and at these multiples of it (the plan's target: 1x, 2x and 4x).
CAPACITY_MULTIPLES = (1, 2, 4)
#: The plan's "1.01 line": a living agent above it has W_paper over 1.01 (33 of 128 on the 01:41Z board).
ABOVE_LINE = 1.01
DISPLACED = "displaced"
POPULATION_ALERT = "the league's population is now"
#: The House's Sail reserve when health.json does not say (`economy.sail_reserve_usd`).
SAIL_RESERVE_USD = 5.0
#: The US regular session in UTC when the NYSE calendar cannot say (the plan's hours, Eastern daylight time).
SESSION_HOURS_UTC = (13.5, 20.0)


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


def iso_ms(ts: float) -> str:
    """An instant as the ledger writes `at` (milliseconds and `Z`), for readers that compare the text."""
    moment = datetime.fromtimestamp(ts, timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


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


def read_deploys(path: Path) -> list[dict[str, Any]] | None:
    """The watchdog's `deploys.jsonl` rows, oldest first, or None without the file (a torn line is skipped, as
    `Releases.history` skips it)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


class Snapshot:
    """The stores of one snapshot directory, read-only. Ledger rows are read by kind once and kept."""

    def __init__(self, root: str | Path, deploys: str | Path | None = None):
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
        self.deploys_path = Path(deploys) if deploys is not None else self.root / DEPLOYS_JSONL
        self.deploys = read_deploys(self.deploys_path)
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

    def ids(self, kind: str, pattern: str) -> list[tuple[str, float]]:
        """(id, when) of the ledger rows of `kind` whose id is LIKE `pattern`, in ledger order."""
        return [(str(ident), epoch(at)) for ident, at in self.ledger.execute(
            "SELECT id, at FROM ledger WHERE kind = ? AND id LIKE ? ORDER BY seq", (kind, pattern))]

    def lab_rows(self, sql: str, args: Sequence[Any] = ()) -> list[sqlite3.Row]:
        """Rows from `lab.sqlite`, or [] without the store or the table (a lab from before it)."""
        if self.lab is None:
            return []
        try:
            return self.lab.execute(sql, tuple(args)).fetchall()
        except sqlite3.Error:
            return []

    @property
    def board(self) -> dict[str, Any]:
        return self.json.get("allocator-board.json") or {}

    @property
    def health(self) -> dict[str, Any]:
        return self.json.get("health.json") or {}


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
def left_the_seat_queue(snap: Snapshot, key: str) -> bool:
    """Whether the House's seat queue has let this waiter go (`<class>:<id>`, R2, Sept 24, 2026): its own state when the
    snapshot carries it (house.json `seat_expired`, which the House clears once the reason is gone -- the search reopened
    the desk, the forward window no longer loses: the review of #276), else the ledger's `seat-expired:` row (written
    once, the first departure)."""
    state = snap.json.get("house.json")
    if isinstance(state, Mapping) and isinstance(state.get("seat_expired"), Mapping):
        return key in state["seat_expired"]
    return snap.at_of(f"seat-expired:{key}") is not None


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
    # A card that left the House's seat queue (R2, Sept 24, 2026: its desk closed by the search) waits no more while
    # the House says so (`left_the_seat_queue`, `House._expire_waiters`).
    return [{"card": c, "niche": cards[c].get("niche"), "since": passed_at,
             "created": float(cards[c].get("created_epoch") or cards[c]["_t"])}
            for c, (outcome, passed_at) in outcomes.items() if outcome == "passed" and c in cards and c not in born
            and not left_the_seat_queue(snap, f"cards:{c}")]


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
                if left_the_seat_queue(snap, f"graduates:{candidate}"):
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


# ======================================================================= the forward-first rows (Sept 25, 2026)
def _f(value: Any) -> float | None:
    """A number from a ledger or JSON field (digits in a string, or a number), or None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _get(value: Any, *keys: str) -> Any:
    """`value[k1][k2]...`, or None where a level is missing or not a mapping."""
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _per_day(value: float | None, hours: float) -> float | None:
    return None if value is None or hours <= 0 else value * 24.0 / hours


def _share(part: int, whole: int) -> float | None:
    return _r(part / whole) if whole else None


def _quantile(values: Sequence[float], q: float) -> float | None:
    """The nearest-rank quantile (the value at or below which a share `q` of them lie)."""
    if not values:
        return None
    rows = sorted(values)
    return rows[max(0, min(len(rows) - 1, math.ceil(q * len(rows)) - 1))]


# ----------------------------------------------------------------------------------- the US session
def us_session(ts: float) -> tuple[float, float] | None:
    """(open, close) of the regular US equity session on the New York day of `ts`, holidays and early closes
    included (`ltcm.data.us_equity_session`, the calendar the House's grace reads), or None when the market is
    shut that day. Where that calendar cannot say (a year it does not compute), Monday to Friday 13:30-20:00Z."""
    try:
        from ltcm.data import NEW_YORK, to_datetime, us_equity_session

        day = datetime.fromtimestamp(ts, timezone.utc).astimezone(NEW_YORK).date()
        session = us_equity_session(day)
        if session is None:
            return None
        return to_datetime(session.open_at).timestamp(), to_datetime(session.close_at).timestamp()
    except Exception:  # noqa: BLE001 - no calendar (an import, or a year it does not compute): the plan's hours
        moment = datetime.fromtimestamp(ts, timezone.utc)
        if moment.weekday() >= 5:
            return None
        midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return midnight + SESSION_HOURS_UTC[0] * HOUR, midnight + SESSION_HOURS_UTC[1] * HOUR


def in_us_session(ts: float) -> bool:
    session = us_session(ts)
    return session is not None and session[0] <= ts < session[1]


def last_session(since: float, now: float) -> tuple[float, float] | None:
    """The latest regular session that opened by `now` and closed after `since`, cut at `now`; None without one."""
    t = now
    for _ in range(10):
        session = us_session(t)
        if session is not None and session[0] <= now and session[1] > since:
            return session[0], min(session[1], now)
        t -= DAY
    return None


# ------------------------------------------------------------------------------------------- row 1
def real_settled(snap: Snapshot, since: float) -> dict[str, Any]:
    """The real books' realized result in the window, net of fees, exactly as `league.merton.RealPnl` reads it for
    `merton.paused_until_profit` (health.json `research_economy.merton.real_pnl_24h_usd`): each `book.settle` `pnl`
    and each closing fill's `realized` on `kalshi` and `alpaca`, dust rows and practice books never. A settlement's
    `pnl` is its payout less the holding's cost, and the cost holds the buy fees (`Book.settle`); a sale's
    `realized` is net of its own fee. Settlements and sales apart, by book, and the House's own rows (positions of
    dead members it held to settlement) apart too. On the T0 snapshot: +$21.35 on 57 settlements and 4 sales, to
    the cent the House's own +$21.34797 on 61."""
    now = snap.now
    totals = {"settled": 0.0, "sales": 0.0}
    counts = {"settled": 0, "sales": 0}
    by_book: dict[str, dict[str, Any]] = {}
    house = 0.0
    for row in snap.rows("book.settle", "book.fill"):
        if not since <= row.t <= now:
            continue
        p = row.p
        book = str(p.get("book"))
        if book not in REAL_BOOKS or p.get("real_money") is False or p.get("source") == "dust":
            continue
        amount = _f(p.get("pnl") if row.kind == "book.settle" else p.get("realized"))
        if amount is None:
            continue  # an opening fill realizes nothing
        side = "settled" if row.kind == "book.settle" else "sales"
        totals[side] += amount
        counts[side] += 1
        entry = by_book.setdefault(book, {"realized_usd": 0.0, "closes": 0})
        entry["realized_usd"] += amount
        entry["closes"] += 1
        if row.agent == HOUSE:
            house += amount
    hours = max((now - since) / HOUR, 0.0)
    realized = totals["settled"] + totals["sales"]
    return {"fn": "real_settled", "since": iso(since), "hours": _r(hours, 2),
            "realized_usd": _r(realized), "per_day_usd": _r(_per_day(realized, hours)),
            "settled_usd": _r(totals["settled"]), "settlements": counts["settled"],
            "sales_usd": _r(totals["sales"]), "sales": counts["sales"], "house_rows_usd": _r(house),
            "by_book": {b: {"realized_usd": _r(r["realized_usd"]), "closes": r["closes"]} for b, r in sorted(by_book.items())}}


def lab_calls(snap: Snapshot, since: float | None) -> tuple[float, int]:
    """The Alpha Lab's own model calls (`lab.sqlite` `calls`, Luna's and Sol's through the gateway on the House's
    line, never on the ledger, so neither `scripts/economics.py` nor the yield rows see them): (dollars, calls) from
    `since` (every call with None) to the snapshot's clock. [] of a lab store without the table."""
    usd, n = 0.0, 0
    for r in snap.lab_rows("SELECT at, cost_usd FROM calls"):
        t = _f(r["at"])
        if t is None or t > snap.now or (since is not None and t < since):
            continue
        usd += _f(r["cost_usd"]) or 0.0
        n += 1
    return usd, n


def gateway_meter(snap: Snapshot, since: float) -> dict[str, Any]:
    """The House's OpenAI line as the gateway meters it (lab calls included): `campaign.meters.openai.line.
    settled_usd` on the `ops.budget` expedition rows (about hourly), from the first reading in the window to the
    last, as dollars a day over the hours they span; and the gateway's month as last reported (`meters.openai.
    month`). A check on `compute_per_day`'s OpenAI lines, never added to them."""
    readings: list[tuple[float, float]] = []
    month = None
    for row in snap.rows("ops.budget"):
        if row.p.get("what") != "expedition" or row.t > snap.now:
            continue
        meter = _get(row.p, "campaign", "meters", "openai") or {}
        if isinstance(meter.get("month"), Mapping):
            month = {"at": row.at, **{k: meter["month"].get(k) for k in ("month", "total_usd", "cap_usd")}}
        settled = _f(_get(meter, "line", "settled_usd"))
        if settled is not None and row.t >= since:
            readings.append((row.t, settled))
    out: dict[str, Any] = {"fn": "gateway_meter", "readings": len(readings), "month": month,
                           "usd": None, "hours": None, "per_day_usd": None}
    if len(readings) >= 2:
        usd = readings[-1][1] - readings[0][1]
        hours = (readings[-1][0] - readings[0][0]) / HOUR
        out.update(usd=_r(usd), hours=_r(hours, 2), first=iso(readings[0][0]), last=iso(readings[-1][0]),
                   per_day_usd=_r(_per_day(usd, hours)))
    return out


def yield_rows(snap: Snapshot, since: float) -> dict[str, Any]:
    """The hourly yield rows (`ops.budget` `what: yield`, `league/yield_ledger.py`) written in the window: the hours
    they cover and the dollars by line. A check on `compute_per_day`, never added to it: every line of them (research
    tokens, Merton's roles, audits) is on the ledger already, and the Sail meter carries the Sail research tokens
    again. The House writes one an hour while it runs (31 rows from 21:48Z Sept 23 to T0)."""
    usd = hours = 0.0
    n = 0
    lines: dict[str, float] = defaultdict(float)
    for row in snap.rows("ops.budget"):
        p = row.p
        if p.get("what") != "yield" or not since <= row.t <= snap.now:
            continue
        n += 1
        hours += _f(p.get("hours")) or 0.0
        usd += _f(p.get("total_usd")) or 0.0
        for line, value in (p.get("spend_usd") or {}).items():
            lines[str(line)] += _f(value) or 0.0
    return {"fn": "yield_rows", "rows": n, "hours": _r(hours, 2), "usd": _r(usd), "per_day_usd": _r(_per_day(usd, hours)),
            "by_line": {k: _r(v) for k, v in sorted(lines.items())}}


def compute_per_day(snap: Snapshot, since: float) -> dict[str, Any]:
    """The window's model and infrastructure spend a day: `scripts/economics.py` `spend` over the window (the method
    of the plan's lifetime $562: Luna gateway-verified `provider.request` costs, Astra's gateway-metered `merton.pass`,
    audits, grants and probes, the Sail balance-debit meter, Jev and web-search credit charges; its estimate lines
    are left out where it leaves them out) plus the lab's own calls (`lab_calls`); the lifetime total by the same
    method beside it, and the gateway meter (`gateway_meter`) and the yield rows (`yield_rows`) as checks. Measured on
    the T0 snapshot: $114.39 by economics.py and $4.50 of lab calls in the day; lifetime $564.70 by economics.py
    (the plan read $562 at 01:42Z)."""
    from scripts import economics  # standard library and no league imports: the lifetime method, run as it is

    conn = economics.connect_ro(str(snap.root / "ledger.sqlite"))
    semantic = snap.root / "semantic.sqlite"
    semantic_db = str(semantic) if semantic.exists() else None
    try:
        window = economics.spend(conn, iso_ms(since), None, semantic_db=semantic_db)
        life = economics.spend(conn, None, None, semantic_db=semantic_db)
    finally:
        conn.close()
    hours = max((snap.now - since) / HOUR, 0.0)
    lab_usd, lab_n = lab_calls(snap, since)
    life_lab_usd, life_lab_n = lab_calls(snap, None)
    providers = {str(name): float(usd) for name, usd in window["providers"].items()}
    providers["openai-lab"] = lab_usd
    total = math.fsum(providers.values())
    lines = [{"provider": row["provider"], "component": row["component"], "usd": _r(float(row["usd"])),
              "count": row["count"], "basis": row["basis"]}
             for row in window["lines"] if row["in_total"] and float(row["usd"])]
    lines.append({"provider": "openai-lab", "component": "Alpha Lab model calls (lab.sqlite calls)", "usd": _r(lab_usd),
                  "count": lab_n, "basis": "lab.sqlite cost_usd"})
    openai = providers.get("openai-luna", 0.0) + providers.get("openai-astra", 0.0) + lab_usd
    return {"fn": "compute_per_day", "since": iso(since), "hours": _r(hours, 2),
            "usd": _r(total), "per_day_usd": _r(_per_day(total, hours)),
            "providers": {k: _r(v) for k, v in sorted(providers.items())}, "openai_usd": _r(openai),
            "openai_per_day_usd": _r(_per_day(openai, hours)), "lines": lines,
            "lifetime_usd": _r(float(life["total"]) + life_lab_usd), "lifetime_economics_usd": _r(float(life["total"])),
            "lifetime_lab_usd": _r(life_lab_usd), "lifetime_lab_calls": life_lab_n,
            "lifetime_providers": {str(k): _r(float(v)) for k, v in sorted(life["providers"].items())},
            "gateway": gateway_meter(snap, since), "yield": yield_rows(snap, since)}


def unit_economics(settled: Mapping[str, Any], compute: Mapping[str, Any], swinging: bool) -> dict[str, Any]:
    """Compute a day over real settled profit a day, and the plan's target: compute at most twice the profit, or at
    most $60 a day while no family swings."""
    profit, cost = settled.get("per_day_usd"), compute.get("per_day_usd")
    ratio = cost / profit if profit is not None and cost is not None and profit > 0 else None
    meets = cost is not None and ((ratio is not None and ratio <= 2.0) or (not swinging and cost <= 60.0))
    return {"fn": "unit_economics", "profit_per_day_usd": profit, "compute_per_day_usd": cost,
            "compute_over_profit": _r(ratio, 2), "family_swings": swinging, "meets_target": bool(meets)}


def capacity_at_sizes(snap: Snapshot, venue: str, family: str, members: Sequence[Agent], trades: Sequence[Trade],
                      intents: Mapping[str, Mapping[str, Any]], multiples: Sequence[int] = CAPACITY_MULTIPLES) -> dict[str, Any]:
    """`family_capacity`'s factors at the family's real size and at multiples of it: the size is the median real bid
    of the last 7 days (the median of every bid when the family has no real one); the markets a day are the band's
    and do not move with the size; the fill rate is the one measured at that size's bucket (the real book's once it
    has bid `MIN_REAL_MARKETS_FOR_FILL_RATE` markets there, every book's before, none when no bid of that size was
    ever placed: an unmeasured size is never assumed to fill); the profit a settlement is the family's (real where it
    has real closes) scaled by the multiple, the same edge a dollar."""
    base = family_capacity(snap, venue, family, members, trades, intents)
    out: dict[str, Any] = {"fn": "capacity_at_sizes", "family": family, "venue": venue, "base": base, "sizes": []}
    if base.get("capacity_usd_per_day") is None and base.get("why"):
        out["why"] = base["why"]
        return out
    ids = {a.id for a in members}
    start = snap.now - CAPACITY_DAYS * DAY
    real = sorted(i["notional"] for i in intents.values() if i["agent"] in ids and i["placed"] and i["t"] >= start
                  and i["market"] and i["book"] in REAL_BOOKS and i["notional"] is not None)
    size = median(real) if real else base.get("current_size_usd")
    out.update(size_usd=_r(size, 2), size_basis="the median real bid" if real else "the median bid; no real bid yet")
    if size is None:
        out["why"] = "no bid carries a size"
        return out
    real_rates = (base.get("fill_rates_by_book") or {}).get("real") or {}
    every = base.get("fill_rates") or {}
    profit = base.get("profit_per_settlement_usd")
    for k in multiples:
        bucket = size_bucket(size * k)
        at_real = real_rates.get(bucket) or {}
        if int(at_real.get("markets_bid") or 0) >= MIN_REAL_MARKETS_FOR_FILL_RATE:
            rate, basis = at_real.get("fill_rate"), "real"
        elif bucket in every:
            rate, basis = every[bucket].get("fill_rate"), "all books"
        else:
            rate, basis = None, "no bid of this size yet"
        scaled = profit * k if profit is not None else None
        capacity = base["markets_per_day"] * rate * scaled if rate is not None and scaled is not None else None
        out["sizes"].append({"multiple": k, "size_usd": _r(size * k, 2), "bucket": bucket, "fill_rate": rate,
                             "fill_rate_basis": basis, "profit_per_settlement_usd": _r(scaled),
                             "capacity_usd_per_day": _r(capacity)})
    return out


def proven_capacity(snap: Snapshot, families: Families, intents: Mapping[str, Mapping[str, Any]],
                    proven: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Each family the House's pooled record proves (`real_bounds`' `proven`), with the board's own capacity
    (`allocator-board.json` `families`: size, fill rate, markets and settlements a day, dollars a day) and the
    scoreboard's at its real size and at 2x and 4x (`capacity_at_sizes`); and any family the board calls proven that
    this record does not."""
    board = snap.board.get("families") or {}
    rows = []
    for r in proven:
        venue, family = r["venue"], r["family"]
        house = _get(board, venue, family) or {}
        rows.append({"family": family, "venue": venue, "board_state": house.get("state"), "stake_usd": house.get("stake_usd"),
                     "house_capacity": house.get("capacity"),
                     "sizes": capacity_at_sizes(snap, venue, family, families.members.get((venue, family)) or [],
                                                families.trades.get((venue, family)) or [], intents)})
    listed = {(r["venue"], r["family"]) for r in rows}
    board_proven = sorted((str(v), str(f)) for v, fams in board.items() if isinstance(fams, Mapping)
                          for f, rec in fams.items() if isinstance(rec, Mapping) and rec.get("state") in ("proven", "swing"))
    return {"fn": "proven_capacity", "count": len(rows), "families": rows,
            "board_only": [f"{v}/{f}" for v, f in board_proven if (v, f) not in listed]}


# ------------------------------------------------------------------------------------------- row 2
def forward_positive(snap: Snapshot, agents: Mapping[str, Agent], since: float) -> dict[str, Any]:
    """The share of the window's lab graduates and newborns whose first forward evidence is positive, and the plan's
    baseline measure (the module docstring, row 2). A graduate is measured by its latest lab forward window (tape
    that arrived after its code was frozen); a newborn by its first practice day's active blocks. On the T0 snapshot
    110 candidates graduated in the day, 91 carry a forward window and 8 of those an active block; 116 of 215
    lab-born blocks were positive at 02:12Z against the plan's 118 of 224."""
    now = snap.now
    windows: dict[str, dict[str, Any]] = {}
    for r in snap.lab_rows("SELECT candidate, at, ok, active_blocks, log_growth FROM forward"):
        t = _f(r["at"])
        if t is None or t > now:
            continue
        cand = str(r["candidate"])
        if cand not in windows or t > windows[cand]["at"]:
            windows[cand] = {"at": t, "ok": bool(r["ok"]), "active": int(r["active_blocks"] or 0), "growth": _f(r["log_growth"])}
    graduated: dict[str, float] = {}
    for ident, t in snap.ids("lab.graduate", "lab.graduate:%:passed"):
        parts = ident.split(":")
        if len(parts) == 3 and since <= t <= now:
            graduated.setdefault(parts[1], t)
    carried = [c for c in graduated if c in windows]
    tested = [c for c in carried if windows[c]["ok"] and windows[c]["active"] > 0]
    positive = [c for c in tested if (windows[c]["growth"] or 0.0) > 0]
    blocks: dict[str, list[tuple[float, str, float]]] = defaultdict(list)
    lab_rows: list[bool] = []
    for row in snap.rows("eval.block"):
        if not row.p.get("active") or row.t > now:
            continue
        growth = _f(row.p.get("log_growth")) or 0.0
        blocks[row.agent].append((row.t, str(row.p.get("book")), growth))
        agent = agents.get(row.agent)
        if row.t >= since and agent is not None and str(agent.founder or "").startswith("lab:"):
            lab_rows.append(growth > 0)

    def first_day(agent: Agent) -> list[float]:
        book = PRACTICE_BOOK.get(agent.venue)
        return [g for t, b, g in blocks.get(agent.id, ()) if b == book and agent.born <= t <= agent.born + DAY]

    def cohort(rows: Sequence[Agent]) -> dict[str, Any]:
        measured = [(a, first_day(a)) for a in rows]
        measured = [(a, g) for a, g in measured if g]
        good = sum(1 for _, g in measured if math.fsum(g) > 0)
        return {"born": len(rows), "tested": len(measured), "positive": good, "share": _share(good, len(measured))}

    newborns = cohort([a for a in agents.values() if since <= a.born <= now])
    ended = cohort([a for a in agents.values() if since - DAY <= a.born <= now - DAY])
    lab = _get(snap.health, "lab", "forward") or {}
    return {"fn": "forward_positive", "since": iso(since),
            "graduates": {"graduated": len(graduated), "with_window": len(carried), "tested": len(tested),
                          "positive": len(positive), "share": _share(len(positive), len(tested))},
            "newborns": newborns, "newborns_first_day_ended": ended,
            "lab_blocks": {"active": len(lab_rows), "positive": sum(lab_rows), "share": _share(sum(lab_rows), len(lab_rows))},
            "lab_ranked": {"ranked": lab.get("ranked"), "positive": lab.get("positive")}}


def bunt_line() -> float:
    """The constitution's `allocator.bunt_at` in this checkout (1.01 since Sept 20, 2026)."""
    try:
        from league.constitution import CONSTITUTION

        return float((CONSTITUTION.get("allocator") or {}).get("bunt_at", ABOVE_LINE))
    except Exception:  # noqa: BLE001 - a checkout without it reads the plan's line
        return ABOVE_LINE


def practice_standing(snap: Snapshot) -> dict[str, Any]:
    """The board's living agents (`allocator-board.json` `agents`, the allocator's own evidence): the median `W_paper`,
    how many are above the 1.01 line (W_paper over 1.01, as the plan counted its 33), and how many have E at or over
    the bunt line (`bunt_at`), the line the allocator promotes on."""
    board = snap.board.get("agents") or {}
    w_paper, e = [], []
    for row in board.values():
        evidence = row.get("evidence") if isinstance(row, Mapping) else None
        if not isinstance(evidence, Mapping):
            continue
        if _f(evidence.get("W_paper")) is not None:
            w_paper.append(float(evidence["W_paper"]))
        if _f(evidence.get("E")) is not None:
            e.append(float(evidence["E"]))
    line = bunt_line()
    return {"fn": "practice_standing", "board_at": snap.board.get("at"), "agents": len(board), "with_evidence": len(w_paper),
            "median_w_paper": _r(median(w_paper), 5) if w_paper else None, "line": ABOVE_LINE,
            "above_line": sum(1 for w in w_paper if w > ABOVE_LINE), "bunt_at": line, "e_at_bunt": sum(1 for x in e if x >= line)}


# ------------------------------------------------------------------------------------------- row 3
def desk_asset_classes() -> dict[str, tuple[str, ...]]:
    """Desk id -> the asset classes it trades (league/niches.json `asset_class` or `asset_classes`; a Kalshi desk
    trades events)."""
    try:
        niches = json.loads((REPO_ROOT / "league" / "niches.json").read_text(encoding="utf-8"))["niches"]
    except (OSError, ValueError, KeyError):
        return {}
    out = {}
    for n in niches:
        if isinstance(n, dict):
            classes = n.get("asset_classes") or ([n["asset_class"]] if n.get("asset_class") else ["event"])
            out[str(n.get("id"))] = tuple(str(c) for c in classes)
    return out


def capital_on_proof(snap: Snapshot, agents: Mapping[str, Agent]) -> dict[str, Any]:
    """The first family swing and the swing clocks of the proven families (the board's `families`: `state`,
    `swing_clock`); and the Alpaca real stock agents ever (an `equity` buy fill on the real `alpaca` book, and how
    many of them filled inside a US session; and agents ever staked on the real book on an equity desk -- an open
    desk's member counts once it asked the real book for an equity)."""
    now = snap.now
    board = snap.board.get("families") or {}
    swinging, clocks = [], []
    for venue, fams in sorted(board.items()):
        if not isinstance(fams, Mapping):
            continue
        for family, rec in sorted(fams.items()):
            if not isinstance(rec, Mapping) or rec.get("state") not in ("proven", "swing"):
                continue
            if rec.get("state") == "swing":
                swinging.append(f"{venue}/{family}")
            clock = rec.get("swing_clock") or {}
            clocks.append({"family": family, "venue": venue, "state": rec.get("state"), "real_n": clock.get("real_n"),
                           "look_at": _get(clock, "needs", "look_at"), "to_go": _get(clock, "needs", "real_settlements"),
                           "days_to_swing": clock.get("days_to_swing"), "real_per_day": clock.get("real_per_day")})
    first = None
    for row in snap.rows("family.record"):
        if row.p.get("state") == "swing" and row.t <= now:
            first = {"at": row.at, "family": row.p.get("family"), "venue": row.p.get("venue"), "row": "family.record"}
            break
    for row in snap.rows("eval.verdict"):
        if row.p.get("band_to") == "swing" and row.t <= now:
            if first is None or row.t < epoch(first["at"]):
                first = {"at": row.at, "agent": row.agent, "family": agents[row.agent].family if row.agent in agents else None,
                         "row": "eval.verdict"}
            break
    classes = desk_asset_classes()
    filled: dict[str, str] = {}
    in_session: set[str] = set()
    for row in snap.rows("book.fill"):
        p = row.p
        if (p.get("book") != "alpaca" or p.get("side") != "buy" or p.get("source") not in ("venue", "cross") or row.t > now
                or _get(p, "instrument", "asset_class") != "equity"):
            continue
        filled.setdefault(row.agent, row.at)
        if in_us_session(row.t):
            in_session.add(row.agent)
    asked = {row.agent for row in snap.rows("agent.intent")
             if row.p.get("book") == "alpaca" and _get(row.p, "instrument", "asset_class") == "equity" and row.t <= now}
    staked = set()
    for row in snap.rows("book.stake"):
        agent = agents.get(row.agent)
        if row.p.get("book") != "alpaca" or (_f(row.p.get("usd")) or 0.0) <= 0 or agent is None or row.t > now:
            continue
        desk = classes.get(agent.desk, ())
        if desk == ("equity",) or ("equity" in desk and row.agent in asked):
            staked.add(row.agent)
    return {"fn": "capital_on_proof", "swinging": swinging, "first_swing": first, "swing_clocks": clocks,
            "alpaca_stock_filled": len(filled), "alpaca_stock_filled_in_session": len(in_session),
            "alpaca_stock_staked": len(staked), "alpaca_stock_agents": sorted(set(filled) | staked)}


# ------------------------------------------------------------------------------------------- row 4
def restarts(snap: Snapshot, since: float) -> dict[str, Any]:
    """House restarts in the window (`ops.started`), a day, and those inside a US session (`us_session`)."""
    rows = [r for r in snap.rows("ops.started") if since <= r.t <= snap.now]
    hours = max((snap.now - since) / HOUR, 0.0)
    return {"fn": "restarts", "since": iso(since), "count": len(rows), "per_day": _r(_per_day(len(rows), hours), 1),
            "in_session": sum(1 for r in rows if in_us_session(r.t)),
            "releases": dict(Counter(str(r.p.get("release")) for r in rows)), "at": [r.at for r in rows]}


def rollback_cause(reasons: Iterable[Any]) -> str:
    """`backup`, `vendor` or `site` when a rollback's reasons name a cause outside the House (`ROLLBACK_CAUSES`, first
    match wins), else `house`. Sept 24-25, 2026: six releases in a row went back on "The daily backup of the House
    box failed (SailboxError: sailbox api 503: prepare checkpoint warm snapshot ...)"; one on a practice book frozen
    on a two-cent cash difference, which is the House's."""
    text = " ".join(str(r) for r in reasons or ()).lower()
    for cause, words in ROLLBACK_CAUSES:
        if any(word in text for word in words):
            return cause
    return "house"


def deploys_from_log(rows: Sequence[Mapping[str, Any]], since: float, now: float) -> list[dict[str, Any]]:
    """Every deploy the watchdog staged (`deploys.jsonl`: one `deploy` id a deploy, with its `start`, `promote` and
    `verdict` rows) that started in the window. A `vet` or `attest` refusal has no deploy id: the updater stopped it
    before the watchdog staged anything, and it is not a deploy; nor is a `busy` refusal (another deploy held the
    lock: 20260924T082644Z, re-sent three minutes later) or an `unjudged` one, which `Updater` does not count either."""
    deploys: dict[str, dict[str, Any]] = {}
    for row in rows:
        ident = row.get("deploy")
        if not ident or row.get("busy") or row.get("unjudged"):
            continue
        try:
            t = epoch(row["ts"]) if row.get("ts") is not None else epoch(row["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if t > now:
            continue
        d = deploys.setdefault(str(ident), {"deploy": str(ident), "release": row.get("release"), "by": None, "start": None,
                                             "promoted_at": None, "verdict": None, "reasons": [], "ended": None})
        stage = row.get("stage")
        if stage == "start":
            d["start"] = t
        elif stage == "promote" and row.get("ok", True):
            d["promoted_at"] = t
        elif stage == "verdict":
            d.update(verdict=row.get("verdict"), reasons=[str(r) for r in row.get("reasons") or []], ended=t)
    out = []
    for d in deploys.values():
        began = next((x for x in (d["start"], d["promoted_at"], d["ended"]) if x is not None), None)
        if began is not None and since <= began <= now:
            out.append({**d, "at": began})
    return sorted(out, key=lambda d: d["at"])


def deploys_from_ledger(snap: Snapshot, since: float) -> list[dict[str, Any]]:
    """Deploys as the ledger shows them, without the watchdog's log (the module docstring, row 4): the updater's
    `ops.deploy` `deploying` rows and owners' releases first seen on an `ops.started` no such row announced; a start
    of the release that ran before, within `ROLLBACK_WATCH_SECONDS` and before the next deploy, is its rollback, and
    the first error alert between the deploy and that start is its reason."""
    now = snap.now
    starts = [(r.seq, r.t, str(r.p.get("release") or "")) for r in snap.rows("ops.started")]
    announced = [(r.seq, r.t, str(r.p.get("release") or "")) for r in snap.rows("ops.deploy") if r.p.get("action") == "deploying"]
    errors = [(r.seq, str(r.p.get("text") or "")) for r in snap.rows("ops.alert") if r.p.get("level") == "error"]
    names = {release for _, _, release in announced}
    events = [{"seq": s, "t": t, "release": release, "by": "updater"} for s, t, release in announced]
    seen: set[str] = set()
    for i, (s, t, release) in enumerate(starts):
        if i and release not in seen and release not in names:
            events.append({"seq": s, "t": t, "release": release, "by": "owner"})
        seen.add(release)
    events.sort(key=lambda e: e["seq"])
    out = []
    for i, e in enumerate(events):
        before = [release for s, _, release in starts if s < e["seq"]]
        running = before[-1] if before else None
        until = events[i + 1]["seq"] if i + 1 < len(events) else math.inf
        later = [(s, t, release) for s, t, release in starts if e["seq"] <= s < until and t <= e["t"] + ROLLBACK_WATCH_SECONDS]
        started = next((t for _, t, release in later if release == e["release"]), None)
        back = next(((s, t) for s, t, release in later if running and release == running != e["release"]), None)
        reasons = []
        if back is not None:
            first = next((text for s, text in errors if e["seq"] <= s < back[0]), None)
            reasons = [first] if first else []
        verdict = "rolled_back" if back is not None else "promoted" if started is not None else "not started"
        out.append({"deploy": f"{e['release']}@{int(e['t'])}", "release": e["release"], "by": e["by"], "start": e["t"],
                    "promoted_at": started, "verdict": verdict, "reasons": reasons,
                    "ended": back[1] if back is not None else None, "at": e["t"]})
    return [d for d in out if since <= d["at"] <= now]


def deploy_record(snap: Snapshot, since: float) -> dict[str, Any]:
    """Deploys that started in the window, their verdicts, the rollbacks by cause (`rollback_cause`: those outside
    the House are `backup`, `vendor` and `site`) and the deploys whose start or promotion fell inside a US session.
    Read from the watchdog's `deploys.jsonl` when the snapshot has it (`deploys_from_log`), else from the ledger
    (`deploys_from_ledger`)."""
    if snap.deploys is not None:
        source, rows = "deploys.jsonl", deploys_from_log(snap.deploys, since, snap.now)
    else:
        source, rows = "ledger", deploys_from_ledger(snap, since)
    for d in rows:
        d["in_session"] = in_us_session(d["at"]) or (d.get("promoted_at") is not None and in_us_session(d["promoted_at"]))
        d["cause"] = rollback_cause(d["reasons"]) if d["verdict"] == "rolled_back" else None
    rolled = [d for d in rows if d["verdict"] == "rolled_back"]
    causes = Counter(str(d["cause"]) for d in rolled)
    return {"fn": "deploy_record", "source": source, "path": str(snap.deploys_path) if snap.deploys is not None else None,
            "since": iso(since), "deploys": len(rows), "verdicts": dict(Counter(str(d["verdict"]) for d in rows)),
            "rolled_back": len(rolled), "outside": sum(causes[c] for c in OUTSIDE_THE_HOUSE), "causes": dict(causes),
            "in_session": sum(1 for d in rows if d["in_session"]),
            "rows": [{"release": d["release"], "at": iso(d["at"]), "promoted_at": iso(d.get("promoted_at")),
                      "verdict": d["verdict"], "cause": d["cause"], "in_session": d["in_session"],
                      "reason": (d["reasons"][0] if d["reasons"] else "")[:200]} for d in rows]}


def tick_p50(snap: Snapshot, since: float) -> dict[str, Any]:
    """The median interval between ticks in the window, from the `ops.job` rows of `TICK_JOB` (one a tick; the job
    id ends in the moment the tick queued it): intervals whose earlier job ended within `TICK_JOB_DONE_SECONDS` and
    with no restart between. The loop sleeps a tick up to `tick_seconds` (60), so an interval of about 60 s is a
    tick of 60 s or less. health.json's last tick and its hour's slowest steps beside it. On the T0 day: p50 73.6 s
    over 989 intervals, p90 122 s; the last tick 30.4 s, in the first quarter hour of a new release."""
    jobs: list[tuple[float, float | None]] = []
    for row in snap.rows("ops.job"):
        p = row.p
        if p.get("key") != TICK_JOB or p.get("state") == "started":
            continue
        try:
            queued = float(str(p.get("job")).rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        jobs.append((queued, _f(p.get("elapsed_seconds"))))
    jobs.sort()
    starts = sorted(r.t for r in snap.rows("ops.started"))
    intervals = []
    for (a, done), (b, _) in zip(jobs, jobs[1:]):
        if a < since or b > snap.now or done is None or done >= TICK_JOB_DONE_SECONDS:
            continue
        i = bisect_right(starts, a)
        if i < len(starts) and starts[i] <= b:
            continue  # the House restarted between: not one tick
        intervals.append(b - a)
    steps = snap.health.get("tick_steps") or {}
    last = steps.get("last") or {}
    slowest = [s for s in steps.get("slowest_hour") or [] if isinstance(s, Mapping)]
    return {"fn": "tick_p50", "since": iso(since), "intervals": len(intervals),
            "p50_s": _r(median(intervals), 1) if intervals else None, "p90_s": _r(_quantile(intervals, 0.9), 1),
            "last_tick_s": _f(last.get("total_seconds")), "last_tick_at": last.get("at"), "ticks_in_hour": steps.get("ticks_in_hour"),
            "slowest_hour": [{"step": s.get("step"), "seconds": s.get("seconds")} for s in slowest[:4]],
            "population_slowest_s": next((s.get("seconds") for s in slowest if s.get("step") == "population"), None)}


# ------------------------------------------------------------------------------------------- row 5
def seat_queue(snap: Snapshot, lab: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The House's seat market (health.json `seats`, refreshed hourly): waiters by class, those over two hours and
    the longest, those on desks with a free seat (a desk's `caps` cap over its members: the league's ceiling holds
    them), and the merged strategies waiting (class `strategies`). Without it, the lab's own count (`lab_loop`)."""
    seats = snap.health.get("seats")
    if not isinstance(seats, Mapping):
        lab = lab or {}
        return {"fn": "seat_queue", "at": None, "source": "lab_loop (health.json has no seats)",
                "waiters": lab.get("waiters"), "by_class": {}, "over_two_hours": None, "over_two_hours_by_desk": {},
                "over_two_hours_on_free_desks": None, "free_desks": [], "longest_h": lab.get("longest_wait_h"),
                "longest": {}, "strategies_waiting": None, "displaceable": None}
    waiters = {str(k): int(v or 0) for k, v in (seats.get("waiters") or {}).items()}
    over = {str(d): r for d, r in (seats.get("over_two_hours") or {}).items() if isinstance(r, Mapping)}
    caps = seats.get("caps") or {}
    free = sorted(d for d, c in caps.items() if isinstance(c, Mapping) and int(c.get("cap") or 0) > int(c.get("members") or 0))
    longest = seats.get("longest_wait") if isinstance(seats.get("longest_wait"), Mapping) else {}
    return {"fn": "seat_queue", "at": seats.get("at"), "source": "health.json seats",
            "waiters": sum(waiters.values()), "by_class": waiters,
            "over_two_hours": sum(int(r.get("count") or 0) for r in over.values()),
            "over_two_hours_by_desk": {d: int(r.get("count") or 0) for d, r in sorted(over.items())},
            "over_two_hours_on_free_desks": sum(int(r.get("count") or 0) for d, r in over.items() if d in free),
            "free_desks": free, "longest_h": _f(longest.get("hours")),
            "longest": {k: longest.get(k) for k in ("class", "desk", "id", "since", "reason")},
            "strategies_waiting": waiters.get("strategies"), "displaceable": seats.get("displaceable")}


def life_vs_clock(snap: Snapshot, agents: Mapping[str, Agent], since: float, clocks: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Per desk: the median life (born to died, hours) of the window's dead beside the desk's evidence clock (health.json
    `seats.evidence_clocks.hours`, the House's own; else `clocks`, the scoreboard's `evidence_clocks`, its Kaplan-Meier
    median), whether the median life is under the clock, and the living's median age. The plan's target: a median
    life at or over the clock on every desk."""
    now = snap.now
    house = _get(snap.health, "seats", "evidence_clocks") or {}
    hours = house.get("hours") if isinstance(house.get("hours"), Mapping) else None
    source = "health.json seats.evidence_clocks" if hours else "evidence_clocks (Kaplan-Meier median)"
    if not hours:
        hours = {d: r.get("km_median_h") for d, r in ((clocks or {}).get("desks") or {}).items()}
    dead: dict[str, list[float]] = defaultdict(list)
    living: dict[str, list[float]] = defaultdict(list)
    for a in agents.values():
        if a.died is not None and since <= a.died <= now:
            dead[a.desk].append((a.died - a.born) / HOUR)
        elif (a.died is None or a.died > now) and a.born <= now:
            living[a.desk].append((now - a.born) / HOUR)
    desks = {}
    for desk in sorted(set(dead) | set(hours)):
        life = median(dead[desk]) if dead.get(desk) else None
        clock = _f(hours.get(desk))
        desks[desk] = {"deaths": len(dead.get(desk, ())), "median_life_h": _r(life, 1), "clock_h": clock,
                       "below_clock": life is not None and clock is not None and life < clock,
                       "living": len(living.get(desk, ())), "median_age_h": _r(median(living[desk]), 1) if living.get(desk) else None}
    ages = [h for rows in living.values() for h in rows]
    return {"fn": "life_vs_clock", "since": iso(since), "clocks": source, "clocks_at": house.get("at"), "desks": desks,
            "below": [d for d, r in desks.items() if r["below_clock"]],
            "measured": sum(1 for r in desks.values() if r["median_life_h"] is not None and r["clock_h"] is not None),
            "median_age_h": _r(median(ages), 1) if ages else None}


def displacement_share(agents: Mapping[str, Agent], since: float, now: float) -> dict[str, Any]:
    """Deaths of cause `displaced` (a newcomer took the seat) over all deaths, in the window and over the ledger's
    life (the plan: 464 of 513, 91%, at 04:06Z Sept 25)."""
    dead = [a for a in agents.values() if a.died is not None and a.died <= now]
    window = [a for a in dead if a.died >= since]

    def share(rows: Sequence[Agent]) -> dict[str, Any]:
        n = sum(1 for a in rows if a.cause == DISPLACED)
        return {"deaths": len(rows), "displaced": n, "share": _share(n, len(rows))}

    return {"fn": "displacement_share", "since": iso(since), "window": share(window), "lifetime": share(dead),
            "causes": dict(Counter(str(a.cause) for a in window).most_common())}


# ------------------------------------------------------------------------------------------- row 6
def real_fill_rate(snap: Snapshot, since: float) -> dict[str, Any]:
    """Orders first placed on a real book in the window (`book.order`: an order is one `order_id`, whatever status rows
    follow it: accepted, new, cancelled, filled) and those with a venue fill (`book.fill` `source: venue`), overall, by
    book and for buys; and the baseline's rows measure (fill rows over order rows in the window), which counts every
    status row as an order: 695 rows of 165 orders on the T0 day."""
    now = snap.now
    first: dict[str, dict[str, Any]] = {}
    order_rows = 0
    for row in snap.rows("book.order"):
        p = row.p
        if p.get("book") not in REAL_BOOKS or row.t > now:
            continue
        if row.t >= since:
            order_rows += 1
        oid = str(p.get("order_id") or "")
        if oid and oid not in first:
            first[oid] = {"t": row.t, "book": str(p.get("book")), "side": str(p.get("side") or "")}
    placed = {oid: o for oid, o in first.items() if o["t"] >= since}
    filled: set[str] = set()
    fill_rows = 0
    for row in snap.rows("book.fill"):
        p = row.p
        if p.get("book") not in REAL_BOOKS or p.get("source") != "venue" or row.t > now:
            continue
        if row.t >= since:
            fill_rows += 1
        oid = str(p.get("order_id") or "")
        if oid in placed:
            filled.add(oid)
    by_book = {}
    for book in REAL_BOOKS:
        ids = [oid for oid, o in placed.items() if o["book"] == book]
        n = sum(1 for oid in ids if oid in filled)
        by_book[book] = {"orders": len(ids), "filled": n, "rate": _share(n, len(ids))}
    buys = [oid for oid, o in placed.items() if o["side"] == "buy"]
    buys_filled = sum(1 for oid in buys if oid in filled)
    return {"fn": "real_fill_rate", "since": iso(since), "orders": len(placed), "filled": len(filled),
            "rate": _share(len(filled), len(placed)), "buy_orders": len(buys), "buys_filled": buys_filled,
            "buy_rate": _share(buys_filled, len(buys)), "by_book": by_book,
            "order_rows": order_rows, "fill_rows": fill_rows, "rows_rate": _share(fill_rows, order_rows)}


CONSTITUTION_KEY = re.compile(r"constitution ((?:[a-z_]+\.)*[a-z_]+)")


def refusal_rule(reasons: Iterable[Any]) -> str:
    """The rule a refusal names: the constitution key its reason cites ("... (constitution allocator.max_event_share)"),
    "a frozen book", or the reason's first clause."""
    texts = [str(r) for r in reasons or ()]
    match = CONSTITUTION_KEY.search("; ".join(texts))
    if match:
        return match.group(1)
    if any("is frozen" in t for t in texts):
        return "a frozen book"
    return (texts[0].split(":")[0][:60] if texts else "") or "no reason given"


def intent_books(snap: Snapshot) -> dict[str, tuple[str, str]]:
    """Intent id -> (side, book), from `agent.intent`."""
    return {str(r.p.get("id")): (str(r.p.get("side") or ""), str(r.p.get("book") or "")) for r in snap.rows("agent.intent") if r.p.get("id")}


def real_refusals(snap: Snapshot, since: float) -> dict[str, Any]:
    """Real entries refused: `book.refused` rows on a real book (the row's `book`, else its intent's) whose intent was a
    buy, in the window and a day, and in the last US session (`last_session`), by the rule each names
    (`refusal_rule`). The plan counted 116 in the Sept 24 session."""
    now = snap.now
    intents = intent_books(snap)
    rows = []
    for r in snap.rows("book.refused"):
        if not since <= r.t <= now:
            continue
        side, book = intents.get(str(r.p.get("intent_id")), ("", ""))
        if str(r.p.get("book") or book) in REAL_BOOKS:
            rows.append((r, side))
    entries = [r for r, side in rows if side == "buy"]
    hours = max((now - since) / HOUR, 0.0)
    session = last_session(since, now)
    inside = [r for r in entries if session is not None and session[0] <= r.t <= session[1]]
    return {"fn": "real_refusals", "since": iso(since), "refused": len(rows), "entries": len(entries),
            "per_day": _r(_per_day(len(entries), hours), 1), "unknown_side": sum(1 for _, side in rows if not side),
            "by_rule": dict(Counter(refusal_rule(r.p.get("reasons")) for r in entries).most_common()),
            "session": None if session is None else {
                "open": iso(session[0]), "until": iso(session[1]), "entries": len(inside),
                "by_rule": dict(Counter(refusal_rule(r.p.get("reasons")) for r in inside).most_common())}}


class Bands:
    """Each agent's allocator band over time: the `eval.verdict` rows that name one (`band_to` on a promotion or a
    demotion, `band` on a sizing), in ledger order."""

    def __init__(self, snap: Snapshot):
        self.changes: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for row in snap.rows("eval.verdict"):
            band = row.p.get("band_to") or row.p.get("band")
            if band:
                self.changes[row.agent].append((row.seq, str(band)))
        self._seqs = {a: [s for s, _ in rows] for a, rows in self.changes.items()}

    def at(self, agent: str, seq: int) -> str | None:
        rows = self.changes.get(agent) or []
        i = bisect_right(self._seqs.get(agent, []), seq)
        return rows[i - 1][1] if i else None


def probe_taker_entries(snap: Snapshot, since: float) -> dict[str, Any]:
    """Real buy fills taken as a taker in the window (`book.fill` `liquidity: taker` on a real book), by the band the
    agent held then (`Bands`), with the probes' own count and dollars by book; and the real entries refused for
    taking (a reason citing `allocator.real_entry_liquidity`), the probes' among them. The maker rule is Kalshi's:
    Alpaca reports no fee, so its book books every order at the taker's fee and labels every Alpaca fill a taker
    (`Book._liquidity`), post-only dip bids included -- the T0 day's three Alpaca probe "taker" entries were resting
    crypto bids. The plan's baseline: none allowed on Kalshi."""
    now = snap.now
    bands = Bands(snap)
    taker = []
    for row in snap.rows("book.fill"):
        p = row.p
        if (p.get("book") not in REAL_BOOKS or p.get("side") != "buy" or p.get("source") != "venue"
                or not since <= row.t <= now or p.get("liquidity") != "taker"):
            continue
        taker.append((row, bands.at(row.agent, row.seq) or "unknown"))
    probes = [row for row, band in taker if band == "probe"]
    by_book = {}
    for book in REAL_BOOKS:
        rows = [r for r in probes if r.p.get("book") == book]
        by_book[book] = {"entries": len(rows), "usd": _r(math.fsum(abs(_f(r.p.get("cash_delta")) or 0.0) for r in rows), 2)}
    refused = [r for r in snap.rows("book.refused") if since <= r.t <= now
               and any("real_entry_liquidity" in str(reason) for reason in r.p.get("reasons") or ())]
    probe_refused = [r for r in refused if bands.at(r.agent, r.seq) == "probe"]
    return {"fn": "probe_taker_entries", "since": iso(since), "taker_entries": len(taker),
            "by_band": dict(Counter(band for _, band in taker)), "probe_taker_entries": len(probes),
            "probe_taker_by_book": by_book, "refused_as_takers": len(refused), "probe_refused_as_takers": len(probe_refused),
            "probes_refused": sorted({r.agent for r in probe_refused})}


# ------------------------------------------------------------------------------------------- row 7
def runway(snap: Snapshot, since: float) -> dict[str, Any]:
    """Sail's runway from its meter (`ops.budget` `what: sail`: the latest `balance_usd`, and the burn a day from the
    `spent_usd` of the last 24 hours of readings over the hours they span) less the House's reserve, beside the House's
    own (health.json `seats.population.sail`); the OpenAI month the gateway reports (`campaign.meters.openai.month`:
    health.json's, else the ledger's latest), and October's cap: unset until that month is 2026-10 or later; whether the
    population ceiling binds on runway (`seats.population`: `max_population` under `ceiling`) and the population alerts
    in the window."""
    now = snap.now
    sail = [(row.t, _f(row.p.get("balance_usd")), _f(row.p.get("spent_usd"))) for row in snap.rows("ops.budget")
            if row.p.get("what") == "sail" and row.t <= now]
    day = [s for s in sail if s[0] >= now - DAY]
    balance = next((b for _, b, _ in reversed(sail) if b is not None), None)
    burn = None
    if len(day) >= 2:
        burn = _per_day(math.fsum(s[2] or 0.0 for s in day[1:]), (day[-1][0] - day[0][0]) / HOUR)
    population = _get(snap.health, "seats", "population") or {}
    house = population.get("sail") if isinstance(population.get("sail"), Mapping) else {}
    reserve = _f(house.get("reserve_usd"))
    reserve = SAIL_RESERVE_USD if reserve is None else reserve
    days = (balance - reserve) / burn if balance is not None and burn else None
    month = _get(snap.health, "campaign", "meters", "openai", "month")
    if not isinstance(month, Mapping):
        month = gateway_meter(snap, since).get("month")
    month = {k: (month or {}).get(k) for k in ("month", "total_usd", "cap_usd")}
    october = _f(month.get("cap_usd")) if str(month.get("month") or "") >= "2026-10" else None
    alerts = [r for r in snap.rows("ops.alert") if since <= r.t <= now and str(r.p.get("text") or "").startswith(POPULATION_ALERT)]
    ceiling, target = population.get("ceiling"), population.get("max_population")
    return {"fn": "runway", "sail_balance_usd": balance, "sail_burn_per_day_usd": _r(burn, 2), "sail_reserve_usd": reserve,
            "sail_runway_days": _r(days, 2), "sail_readings": len(day),
            "house": {k: house.get(k) for k in ("at", "balance_usd", "burn_usd_per_day", "runway_days", "reserve_usd")} if house else None,
            "sail_campaign_remaining_usd": _f(_get(snap.health, "campaign", "accounts", "sail", "remaining_usd")),
            "openai_month": month, "october_cap_usd": october,
            "population": {"ceiling": ceiling, "max_population": target, "rule": population.get("rule")} if population else None,
            "population_binds": ceiling is not None and target is not None and int(target) < int(ceiling),
            "population_alerts": len(alerts), "population_held_alerts": sum(1 for r in alerts if r.p.get("level") == "warning")}


# -------------------------------------------------------------------------------------- the rows together
def forward_first(snap: Snapshot, *, since: float, agents: Mapping[str, Agent], families: Families,
                  intents: Mapping[str, Mapping[str, Any]], metrics: Mapping[str, Any], extras: Mapping[str, Any]) -> dict[str, Any]:
    """The seven rows of docs/goals/LTCM_FORWARD_FIRST.md's scoreboard, each a dict of the functions that compute it."""
    settled = real_settled(snap, since)
    compute = compute_per_day(snap, since)
    capital = capital_on_proof(snap, agents)
    return {
        "1": {"real_settled": settled, "compute_per_day": compute,
              "unit_economics": unit_economics(settled, compute, bool(capital["swinging"])),
              "proven_capacity": proven_capacity(snap, families, intents, metrics["1"].get("proven") or [])},
        "2": {"forward_positive": forward_positive(snap, agents, since), "practice_standing": practice_standing(snap)},
        "3": {"real_dollars": metrics["3"], "capital_on_proof": capital},
        "4": {"restarts": restarts(snap, since), "deploy_record": deploy_record(snap, since), "tick_p50": tick_p50(snap, since)},
        "5": {"seat_queue": seat_queue(snap, metrics["5"]), "life_vs_clock": life_vs_clock(snap, agents, since, extras["evidence_clocks"]),
              "displacement_share": displacement_share(agents, since, snap.now)},
        "6": {"real_fill_rate": real_fill_rate(snap, since), "real_refusals": real_refusals(snap, since),
              "probe_taker_entries": probe_taker_entries(snap, since)},
        "7": {"runway": runway(snap, since)},
    }


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
    metrics = {
        "1": real_bounds(snap, families, intents),
        "2": allocator_promotions(snap, agents, rungs, trades, still_open, families, baseline),
        "3": real_dollars(snap, agents, families),
        "4": deaths_in_window(agents, fills, since, snap.now, rungs),
        "5": lab_loop(snap, agents, rungs, since),
        "6": {"self_cross": self_cross_exits(snap), "stacked": stacked_promotions(snap, agents, trades, baseline)},
        "7": {"recorders": recorders_live(snap, hosts), "idle_desks": idle_desks(snap, agents)},
    }
    extras = {
        "evidence_clocks": evidence_clocks(snap, agents, trades, fills),
        "family_records": family_records(snap, agents, families),
        "weather_capacity": weather_capacity(snap, families, intents),
    }
    return {
        "snapshot": {"dir": str(snap.root), "ledger_rows": snap.rows_total, "newest": snap.newest_at,
                     "since": iso(since), "baseline": iso(baseline), "release": health.get("release"),
                     "board_at": snap.board.get("at"), "feeds_store": snap.feeds is not None,
                     "deploys_log": str(snap.deploys_path) if snap.deploys is not None else None,
                     "trades": len(trades), "open_positions": len(still_open), "skipped": skipped},
        "forward_first": forward_first(snap, since=since, agents=agents, families=families, intents=intents,
                                       metrics=metrics, extras=extras),
        "metrics": metrics,
        "extras": extras,
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


#: The forward-first plan's rows and targets (docs/goals/LTCM_FORWARD_FIRST.md, "The scoreboard"), word for word.
FORWARD_METRICS = {
    "1": "Real settled profit a day (24 h) against compute a day (24 h); proven families and each one's capacity at its real size",
    "2": "Forward-positive share of the last day's graduates and newborns (lab forward windows, first practice day); "
         "living median W_paper; agents above the 1.01 line",
    "3": "Real dollars on proven families / on unproven (stake); the first family swing; Alpaca real stock agents (ever)",
    "4": "House restarts a day; releases rolled back by causes outside the House (vendor, backup, site); tick p50; "
         "deploys inside a US session",
    "5": "Waiters over 2 h and the longest; merged strategies never born; median life against each desk's evidence clock; "
         "displacement share of deaths",
    "6": "Real fill rate (fills / orders, 24 h); real entries refused a day; taker entries by probes",
    "7": "Sail runway; the October OpenAI cap; the population ceiling binding on runway",
}
FORWARD_TARGETS = {
    "1": "compute <= 2 x real settled profit, or <= $60/day while no family swings; >= 3 proven families, capacity "
         "measured at 1x, 2x and 4x the stake",
    "2": ">= 60%; >= 1.005; >= 50",
    "3": "proven >= unproven; the swing reached at the sports family's 10th settlement, or the exact count why not; "
         ">= 2 during a session",
    "4": "<= 6; 0; <= 40 s; 0",
    "5": "0 with free capacity, longest < 2 h; 0; >= the clock on every desk; < 50%",
    "6": ">= 25%; < 30; allowed and measured",
    "7": ">= 5 days throughout; set from funded money at the owner's word; never",
}


def _v(value: Any) -> str:
    """A value as printed, `-` for none."""
    return "-" if value is None else str(value)


def _n(value: Any, digits: int = 1) -> str:
    number = _f(value)
    return "-" if number is None else f"{number:.{digits}f}"


def _sizes_line(sizes: Mapping[str, Any]) -> str:
    """`capacity_at_sizes` in one phrase: dollars a day at each multiple of the real size."""
    rows = sizes.get("sizes") or []
    if not rows:
        return f"`capacity_at_sizes` - ({sizes.get('why') or 'no size'})"
    caps = " / ".join(_usd(r["capacity_usd_per_day"]) for r in rows)
    multiples = "/".join(f"{r['multiple']}x" for r in rows)
    return f"`capacity_at_sizes` {caps} a day at {multiples} of {_usd(sizes.get('size_usd'))} ({sizes.get('size_basis')})"


def forward_parts(board: Mapping[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """Each forward-first row's reading as (function, what it says) parts, in the plan's order of the row."""
    ff = board["forward_first"]
    parts: dict[str, list[tuple[str, str]]] = {}

    s, c, u, pc = (ff["1"][k] for k in ("real_settled", "compute_per_day", "unit_economics", "proven_capacity"))
    p, g = c["providers"], c["gateway"]
    families = "; ".join(
        f"{r['family']} {_usd(_f(_get(r, 'house_capacity', 'usd_per_day')))}/day at {_usd(_f(_get(r, 'house_capacity', 'size_usd')))} "
        f"(the board), {_sizes_line(r['sizes'])}" for r in pc["families"]) or "none"
    ratio = u["compute_over_profit"]
    parts["1"] = [
        ("real_settled", f"{_usd(s['per_day_usd'])} a day realized ({s['settlements']} settlements {_usd(s['settled_usd'])}, "
                         f"{s['sales']} closing sales {_usd(s['sales_usd'])})"),
        ("compute_per_day", f"{_usd(c['per_day_usd'])} a day (OpenAI {_usd(c['openai_per_day_usd'])}: Luna {_usd(p.get('openai-luna'))}, "
                            f"Astra {_usd(p.get('openai-astra'))}, lab {_usd(p.get('openai-lab'))}; Sail {_usd(p.get('sail'))}; "
                            f"Jev {_usd(p.get('jev'))}); lifetime {_usd(c['lifetime_usd'])} ({_usd(c['lifetime_economics_usd'])} "
                            f"by scripts/economics.py + {_usd(c['lifetime_lab_usd'])} lab)"),
        ("gateway_meter", f"the gateway metered the OpenAI line at {_usd(g['per_day_usd'])} a day over {_n(g['hours'])} h"),
        ("unit_economics", f"compute {'-' if ratio is None else f'{ratio:.1f}x'} the profit: "
                           f"{'meets' if u['meets_target'] else 'short of'} the target"),
        ("proven_capacity", f"{pc['count']} proven: {families}"),
    ]

    fp, ps = ff["2"]["forward_positive"], ff["2"]["practice_standing"]
    gr, nb, ended, lb = fp["graduates"], fp["newborns"], fp["newborns_first_day_ended"], fp["lab_blocks"]
    parts["2"] = [
        ("forward_positive", f"graduates {gr['positive']} of {gr['tested']} with an active forward block ({_pct(gr['share'])}; "
                             f"{gr['graduated']} graduated, {gr['with_window']} with a window); newborns {nb['positive']} of "
                             f"{nb['tested']} on their first practice day so far ({_pct(nb['share'])}; {nb['born']} born), "
                             f"first day ended {ended['positive']} of {ended['tested']} ({_pct(ended['share'])}); lab-born active "
                             f"blocks {lb['positive']} of {lb['active']} ({_pct(lb['share'])}, the baseline's measure)"),
        ("practice_standing", f"median W_paper {_n(ps['median_w_paper'], 5)} over {ps['with_evidence']}; {ps['above_line']} above "
                              f"the 1.01 line (E at bunt_at {ps['bunt_at']:g}: {ps['e_at_bunt']})"),
    ]

    rd, cp = ff["3"]["real_dollars"], ff["3"]["capital_on_proof"]
    if cp["swinging"]:
        swing = f"swinging: {', '.join(cp['swinging'])}"
    elif cp["first_swing"]:
        swing = f"first swing {cp['first_swing'].get('at')} ({cp['first_swing'].get('family')}), none swinging now"
    else:
        swing = "no family swing yet: " + ("; ".join(
            f"{k['family']} {k['real_n']} real settlements, {k['to_go']} to go (look at {k['look_at']}, "
            f"{'-' if k['days_to_swing'] is None else k['days_to_swing']} days)" for k in cp["swing_clocks"]) or "no proven family")
    parts["3"] = [
        ("real_dollars", f"{_usd(rd['proven_usd'])} proven / {_usd(rd['unproven_usd'])} unproven"),
        ("capital_on_proof", f"{swing}; Alpaca real stock agents ever: {cp['alpaca_stock_filled']} filled "
                             f"({cp['alpaca_stock_filled_in_session']} in a session), {cp['alpaca_stock_staked']} staked on a stock desk"),
    ]

    rs, dr, tp = ff["4"]["restarts"], ff["4"]["deploy_record"], ff["4"]["tick_p50"]
    causes = ", ".join(f"{k} {v}" for k, v in sorted(dr["causes"].items())) or "none"
    parts["4"] = [
        ("restarts", f"{rs['count']} in the window ({_n(rs['per_day'])} a day), {rs['in_session']} inside a US session"),
        ("deploy_record", f"{dr['rolled_back']} releases rolled back, {dr['outside']} by causes outside the House ({causes}); "
                          f"{dr['in_session']} of {dr['deploys']} deploys inside a US session (from {dr['source']})"),
        ("tick_p50", f"interval p50 {_n(tp['p50_s'])} s over {tp['intervals']} ticks (p90 {_n(tp['p90_s'])} s); the last tick "
                     f"{_n(tp['last_tick_s'])} s"),
    ]

    sq, lc, ds = ff["5"]["seat_queue"], ff["5"]["life_vs_clock"], ff["5"]["displacement_share"]
    longest = sq.get("longest") or {}
    below = ", ".join(f"{d} {lc['desks'][d]['median_life_h']} h < {lc['desks'][d]['clock_h']} h" for d in lc["below"]) or "none"
    parts["5"] = [
        ("seat_queue", f"{sq['over_two_hours'] if sq['over_two_hours'] is not None else '-'} of {sq['waiters']} waiters over 2 h "
                       f"({sq['over_two_hours_on_free_desks'] if sq['over_two_hours_on_free_desks'] is not None else '-'} on desks "
                       f"with a free seat), the longest {_n(sq['longest_h'])} h ({longest.get('class') or '-'} on "
                       f"{longest.get('desk') or '-'}); {sq['strategies_waiting'] if sq['strategies_waiting'] is not None else '-'} "
                       f"merged strategies waiting (the seat market at {sq['at'] or '-'})"),
        ("life_vs_clock", f"median life under the desk's clock on {len(lc['below'])} of {lc['measured']} desks ({below})"),
        ("displacement_share", f"{_pct(ds['window']['share'])} of {ds['window']['deaths']} deaths in the window "
                               f"({_pct(ds['lifetime']['share'])} of {ds['lifetime']['deaths']} lifetime)"),
    ]

    fr, rr, pt = ff["6"]["real_fill_rate"], ff["6"]["real_refusals"], ff["6"]["probe_taker_entries"]
    books = ", ".join(f"{b} {r['filled']} of {r['orders']}" for b, r in fr["by_book"].items())
    top = ", ".join(f"{k} {v}" for k, v in list(rr["by_rule"].items())[:3]) or "none"
    session = rr.get("session") or {}
    kalshi, alpaca = pt["probe_taker_by_book"].get("kalshi") or {}, pt["probe_taker_by_book"].get("alpaca") or {}
    parts["6"] = [
        ("real_fill_rate", f"{fr['filled']} of {fr['orders']} orders filled ({_pct(fr['rate'])}; {books}); the baseline's rows "
                           f"measure {fr['fill_rows']} of {fr['order_rows']} ({_pct(fr['rows_rate'])})"),
        ("real_refusals", f"{rr['entries']} real entries refused ({_n(rr['per_day'], 0)} a day), {session.get('entries', '-')} in the "
                          f"last session ({(session.get('open') or '-')[:10]}); the most: {top}"),
        ("probe_taker_entries", f"{kalshi.get('entries', 0)} Kalshi taker entries by probes ({_usd(kalshi.get('usd'))}), "
                                f"{pt['probe_refused_as_takers']} probe entries refused for taking; Alpaca books every fill a "
                                f"taker ({alpaca.get('entries', 0)} probe entries, {_usd(alpaca.get('usd'))})"),
    ]

    rw = ff["7"]["runway"]
    month = rw["openai_month"] or {}
    house = rw.get("house") or {}
    population = rw.get("population") or {}
    october = "unset" if rw["october_cap_usd"] is None else _usd(rw["october_cap_usd"])
    parts["7"] = [
        ("runway", f"Sail {_n(rw['sail_runway_days'], 2)} days ({_usd(rw['sail_balance_usd'])} less {_usd(rw['sail_reserve_usd'])} "
                   f"reserve at {_usd(rw['sail_burn_per_day_usd'])} a day; the House reads {house.get('runway_days', '-')}); the "
                   f"OpenAI month {month.get('month') or '-'} at {_usd(_f(month.get('total_usd')))} of {_usd(_f(month.get('cap_usd')))}, "
                   f"October's cap {october}; the population ceiling {'binds' if rw['population_binds'] else 'does not bind'} on "
                   f"runway ({population.get('max_population', '-')} of {population.get('ceiling', '-')}; "
                   f"{rw['population_alerts']} population alerts in the window)"),
    ]
    return parts


def forward_rows(board: Mapping[str, Any], *, markdown: bool = False) -> list[tuple[str, str, str, str]]:
    """(#, metric, reading, target) for the forward-first rows; each part of a reading names its function."""
    rows = []
    for number, parts in forward_parts(board).items():
        if markdown:
            reading = "; ".join(f"`{fn}` {text}" for fn, text in parts)
        else:
            reading = "; ".join(f"[{fn}] {text}" for fn, text in parts)
        rows.append((number, FORWARD_METRICS[number], reading, FORWARD_TARGETS[number]))
    return rows


def forward_sections(board: Mapping[str, Any], pre: str, section: Any, out: list[str]) -> None:
    """The forward-first rows in detail, below the tables."""
    ff = board["forward_first"]

    section("F1. unit economics and capacity [real_settled, compute_per_day, gateway_meter, yield_rows, unit_economics, "
            "proven_capacity, capacity_at_sizes]")
    s, c = ff["1"]["real_settled"], ff["1"]["compute_per_day"]
    books = ", ".join(f"{book} {_usd(row['realized_usd'])} on {row['closes']}" for book, row in s["by_book"].items()) or "-"
    out.append(f"{pre}realized over {s['hours']} h since {s['since']}: {_usd(s['realized_usd'])} ({books}); the House's own rows "
               f"{_usd(s['house_rows_usd'])}")
    out.append(f"{pre}compute over {c['hours']} h: {_usd(c['usd'])}, by line:")
    for line in c["lines"]:
        out.append(f"{pre}  {line['provider']} {line['component']}: {_usd(line['usd'])} on {line['count']} ({line['basis']})")
    lifetime = ", ".join(f"{k} {_usd(v)}" for k, v in c["lifetime_providers"].items())
    out.append(f"{pre}lifetime by scripts/economics.py: {_usd(c['lifetime_economics_usd'])} ({lifetime}); lab calls "
               f"{_usd(c['lifetime_lab_usd'])} on {c['lifetime_lab_calls']}")
    g, y = c["gateway"], c["yield"]
    month = g.get("month") or {}
    out.append(f"{pre}check, the gateway: the House's OpenAI line settled {_usd(g['usd'])} from {g.get('first', '-')} to "
               f"{g.get('last', '-')} ({g['readings']} readings) = {_usd(g['per_day_usd'])} a day, against the ledger's OpenAI "
               f"{_usd(c['openai_per_day_usd'])} a day; the month {month.get('month') or '-'} read {month.get('total_usd') or '-'} "
               f"of {month.get('cap_usd') or '-'}")
    lines = ", ".join(f"{k} {_usd(v)}" for k, v in y["by_line"].items()) or "-"
    out.append(f"{pre}check, the yield rows: {y['rows']} rows over {y['hours']} h, {_usd(y['usd'])} ({lines})")
    for r in ff["1"]["proven_capacity"]["families"]:
        house = r.get("house_capacity") or {}
        out.append(f"{pre}{r['venue']}/{r['family']} ({r['board_state']}, stake {r['stake_usd']}): the board's capacity "
                   f"{_usd(_f(house.get('usd_per_day')))}/day at {_usd(_f(house.get('size_usd')))}, fill rate "
                   f"{house.get('fill_rate_at_size')}, {house.get('markets_per_day')} markets and {house.get('settlements_per_day')} "
                   f"settlements a day")
        base = r["sizes"].get("base") or {}
        out.append(f"{pre}  {_capacity_line(base)}")
        for z in r["sizes"].get("sizes") or []:
            out.append(f"{pre}  at {z['multiple']}x ({_usd(z['size_usd'])}, bids {z['bucket']}): fill rate {z['fill_rate']} "
                       f"({z['fill_rate_basis']}) x {_usd(z['profit_per_settlement_usd'])} a settlement = "
                       f"{_usd(z['capacity_usd_per_day'])}/day")
    board_only = ff["1"]["proven_capacity"]["board_only"]
    if board_only:
        out.append(f"{pre}the board calls proven, this record does not: {', '.join(board_only)}")

    section("F2. forward evidence [forward_positive, practice_standing]")
    fp, ps = ff["2"]["forward_positive"], ff["2"]["practice_standing"]
    lab = fp["lab_ranked"]
    out.append(f"{pre}the lab's own ranking (health.json lab.forward): {lab.get('positive', '-')} positive of "
               f"{lab.get('ranked', '-')} ranked")
    out.append(f"{pre}the board at {ps['board_at']}: {ps['agents']} agents, {ps['with_evidence']} with evidence")

    section("F3. capital on proof [real_dollars, capital_on_proof]")
    cp = ff["3"]["capital_on_proof"]
    for k in cp["swing_clocks"]:
        out.append(f"{pre}{k['venue']}/{k['family']} ({k['state']}): {k['real_n']} real settlements, look at {_v(k['look_at'])}, "
                   f"{_v(k['to_go'])} to go, {_v(k['real_per_day'])} a day, {_v(k['days_to_swing'])} days to the swing")
    out.append(f"{pre}first swing ever: {cp['first_swing'] or 'none'}; Alpaca stock agents: {', '.join(cp['alpaca_stock_agents']) or 'none'}")

    section("F4. the harness [restarts, deploy_record, rollback_cause, tick_p50]")
    rs, dr, tp = ff["4"]["restarts"], ff["4"]["deploy_record"], ff["4"]["tick_p50"]
    releases = ", ".join(f"{k} {v}" for k, v in rs["releases"].items()) or "-"
    out.append(f"{pre}restarts since {rs['since']} by release: {releases}")
    out.append(f"{pre}deploys read from {dr['source']}{' (' + dr['path'] + ')' if dr.get('path') else ''}: {dr['verdicts']}")
    for d in dr["rows"]:
        tail = f"; {d['cause']}: {d['reason']}" if d["verdict"] == "rolled_back" else ""
        out.append(f"{pre}{d['at']} {d['release']} {d['verdict']}{' (inside a US session)' if d['in_session'] else ''}{tail}")
    slowest = ", ".join(f"{r['step']} {r['seconds']} s" for r in tp["slowest_hour"]) or "-"
    out.append(f"{pre}the last tick {tp['last_tick_s']} s at {tp['last_tick_at']}; {tp['ticks_in_hour']} ticks in its hour; the "
               f"hour's slowest steps: {slowest}")

    section("F5. the seat market [seat_queue, life_vs_clock, displacement_share]")
    sq, lc, ds = ff["5"]["seat_queue"], ff["5"]["life_vs_clock"], ff["5"]["displacement_share"]
    waiters = ", ".join(f"{k} {v}" for k, v in sq["by_class"].items()) or "-"
    over = ", ".join(f"{k} {v}" for k, v in sq["over_two_hours_by_desk"].items()) or "-"
    out.append(f"{pre}waiters by class: {waiters}; over 2 h by desk: {over}; desks with a free seat: {', '.join(sq['free_desks']) or '-'}")
    out.append(f"{pre}the longest: {sq.get('longest')}")
    out.append(f"{pre}evidence clocks from {lc['clocks']} (measured {lc['clocks_at'] or '-'}); the living's median age {lc['median_age_h']} h")
    for desk, r in lc["desks"].items():
        out.append(f"{pre}{desk}: {r['deaths']} deaths, median life {_v(r['median_life_h'])} h, clock {_v(r['clock_h'])} h"
                   f"{' (UNDER THE CLOCK)' if r['below_clock'] else ''}; {r['living']} living, median age {_v(r['median_age_h'])} h")
    out.append(f"{pre}causes of death in the window: {ds['causes']}")

    section("F6. execution [real_fill_rate, real_refusals, probe_taker_entries]")
    fr, rr, pt = ff["6"]["real_fill_rate"], ff["6"]["real_refusals"], ff["6"]["probe_taker_entries"]
    out.append(f"{pre}orders by book: {fr['by_book']}; buys {fr['buys_filled']} of {fr['buy_orders']} ({_pct(fr['buy_rate'])})")
    out.append(f"{pre}refused real entries by rule in the window: {rr['by_rule'] or '-'} ({rr['unknown_side']} refusals of unknown side)")
    if rr.get("session"):
        out.append(f"{pre}in the session {rr['session']['open']} to {rr['session']['until']}: {rr['session']['by_rule'] or '-'}")
    out.append(f"{pre}real taker entries by band: {pt['by_band'] or '-'}; refused for taking: {pt['refused_as_takers']} "
               f"({pt['probe_refused_as_takers']} by probes: {', '.join(pt['probes_refused']) or '-'})")

    section("F7. runway [runway]")
    rw = ff["7"]["runway"]
    out.append(f"{pre}Sail meter: {rw['sail_readings']} readings in the last day; campaign's Sail remaining "
               f"{_usd(rw['sail_campaign_remaining_usd'])}; the House: {rw['house']}")
    out.append(f"{pre}population: {rw['population']}")


def _capacity_line(c: Mapping[str, Any]) -> str:
    if c.get("capacity_usd_per_day") is None and c.get("why"):
        return f"capacity - ({c['why']})"
    return (f"capacity {_usd(c.get('capacity_usd_per_day'))}/day = {c.get('markets_per_day')} markets bid a day "
            f"({c.get('markets_bid')} over {c.get('days')} days) x fill rate {c.get('fill_rate_at_size')} "
            f"({c.get('fill_rate_basis')}, bids {c.get('size_bucket')}, median {_usd(c.get('current_size_usd'))}) x "
            f"{_usd(c.get('profit_per_settlement_usd'))} a settlement ({c.get('profit_basis')}, n {c.get('settlements')}); "
            f"real seats earn {_usd(c.get('real_earning_usd_per_day'))}/day now")


def _cell(text: str) -> str:
    """A markdown table cell: a pipe inside it would end the cell."""
    return str(text).replace("|", "\\|")


def render_text(board: Mapping[str, Any], *, markdown: bool = False) -> str:
    """Both tables (text, or markdown for the run record): the forward-first rows, then the close-the-gaps metrics;
    then each forward-first row in detail, each metric's rows and the extras."""
    s = board["snapshot"]
    m = board["metrics"]
    x = board["extras"]
    out = []
    head = (f"gap scoreboard: ledger {s['ledger_rows']:,} rows to {s['newest']}; window since {s['since']}; "
            f"baseline {s['baseline'] or '-'}; release {s['release'] or '-'}; board {s['board_at'] or '-'}; "
            f"feeds store {'yes' if s['feeds_store'] else 'no'}; deploy log {s.get('deploys_log') or 'none (read from the ledger)'}")
    out.append(("# " if markdown else "") + head)
    pre = "- " if markdown else "   "

    def section(title: str) -> None:
        out.append("")
        out.append(("## " if markdown else "== ") + title)

    if "forward_first" in board:
        section("the forward-first scoreboard (docs/goals/LTCM_FORWARD_FIRST.md)")
        out.append("")
        rows = forward_rows(board, markdown=markdown)
        if markdown:
            out.append("| # | Metric | Reading (each number names its function) | Target at the end |")
            out.append("|---|---|---|---|")
            out += [f"| {a} | {_cell(b)} | {_cell(c)} | {_cell(d)} |" for a, b, c, d in rows]
        else:
            out += [f"{a}  {b}\n   {c}\n   target: {d}" for a, b, c, d in rows]
    section("the close-the-gaps scoreboard (docs/goals/LTCM_CLOSE_THE_GAPS.md; kept)")
    out.append("")
    rows = summary_rows(board)
    if markdown:
        out.append("| # | Metric | Reading | Computed by |")
        out.append("|---|---|---|---|")
        out += [f"| {a} | {b} | {c} | `{d}` |" for a, b, c, d in rows]
    else:
        out += [f"{a}  {b}\n   {c}   [{d}]" for a, b, c, d in rows]
    if "forward_first" in board:
        forward_sections(board, pre, section, out)

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
    from scripts.floor_box import DEPLOYS_JSONL as DEPLOYS_JSONL_ON_BOX, STATE_DIR, client, read_state, require_box

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
        # The watchdog's own record of every deploy (about 3 MB on Sept 25, 2026): the rollbacks and their reasons,
        # which the ledger cannot show for a release killed before its first `ops.started`.
        try:
            data = api.download(box, DEPLOYS_JSONL_ON_BOX, timeout=300)
        except Exception:  # noqa: BLE001 - a box that never deployed through the watchdog has none
            pass
        else:
            (directory / DEPLOYS_JSONL).write_bytes(bytes(data))
            written.append(DEPLOYS_JSONL)
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
    parser.add_argument("--deploys", metavar="FILE", help="the watchdog's deploys.jsonl kept outside the snapshot "
                                                          "(default: DIR/deploys.jsonl; without one, deploys are read from the ledger)")
    form = parser.add_mutually_exclusive_group()
    form.add_argument("--json", action="store_true", help="machine output")
    form.add_argument("--markdown", action="store_true", help="both tables for the run record")
    args = parser.parse_args(argv)
    if args.take:
        take(args.take)
    snap = Snapshot(args.take or args.snapshot, deploys=args.deploys)
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
