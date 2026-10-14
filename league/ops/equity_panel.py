"""The `equity_panel` job: the panel's bars, its store, the coverage audit and the nightly I6 on real data.

Owner: package A of release E4. Protected (league/ops/). It stands on package C's C0 (`league.xs.store.write_panel`
with its manifest keywords, `league.xs.config.quiet`); the registry row is A's patch (E4-SPEC 13: after
`equity_universe`). While C0 is not in the release the job is skipped, never a crash.

PER RUN: `league.xs.config.quiet(now, WALL_S)` first; the universe (league/ops/equity_universe.py's files); REF and
member bars for `league.xs.config.SPANS`, through `GET /v1/alpaca/v2/stocks/bars` with the venue's `asof`
(`fetch_asof`): ONE REQUEST SERIES AN ASSET, its last spell's ticker, the assets whose spell is open together at
today's `asof` (the parameter left out), each ended asset alone at its last member session, a day INSIDE its spell,
so a reused ticker resolves to the spell's own company (`plan`). 2020 IS NEVER FETCHED (ValueError for a span or an
`asof` touching it).

THE ADJ VINTAGE (4.2): `adj` of one asset is always ONE fetch's series. The daily run (`incremental`) fetches the last
`INCREMENTAL_SESSIONS` sessions of every active asset; an asset whose adj/raw close ratios on the overlap equal the
store's WITHIN THE VENDOR'S CENTS (`league.xs.config.rounding_bound`: the adjustment=all series is served rounded to
the cent, so two readings of one unrestated series differ by nothing and two a dividend restated by more than the
rounding) takes the window's rows; any other (a dividend or split restated its history, a bar came or went, a raw
price of the overlap was revised) is refetched whole in the same run and its `vintage` set to today. A whole refetch
of every asset (`full`) runs when `full_at` is older than `FULL_EVERY_DAYS`; if a call still fails after its `TRIES`
it writes nothing new, the run falls back to the incremental, and it is tried again the next night (`full_at` does
not move; two nights running is an alarm). A raw price that a refetch changed is counted in `revisions` (an alarm
above `REVISIONS_ALARM`; a volume alone is not: the next day's fetch always reads a later volume).

D19, COVERAGE AND WHAT MAY MASK A MEMBER. A VALID BAR is a raw close above 0 with a raw volume above 0 (the vendor
serves a session without a trade as a flat bar of volume 0: no valid bar that day, in the Gym and live alike; the
store keeps the bar as served and every reader applies the rule). A spell's series is ACCEPTED when valid bars cover
at least `ACCEPT_SHARE` of its sessions in the store and its first valid bar is within `ACCEPT_FIRST` sessions of its
first session there; else masked "no_bars". A series whose median dollar volume is under `REUSED_USD` is "reused"
whatever its coverage (no index member trades so little: the ticker resolved to another company; the probe's reading).
The only other masks are the venue's "not_fractionable" and "insane" (OHLC sanity failing on more than `INSANE_SHARE`
of the asset's bars; a single insane bar is a missing bar for that day). A BIG MOVE NEVER MASKS: a raw close move past
E1's `RAW_JUMP` with no ratio jump is COUNTED and given a SECOND READ (`second_read`: the 1Min bars of that session and
of the one before); only when the minute bars contradict a daily bar by more than `SECOND_READ_GAP` is that one bar
treated as missing. A ratio jump no raw move explains is counted too. coverage[y] = member-days of year y with a valid
bar of an unmasked asset / member-days of y; the verdict "ok" | "low_coverage" | "insufficient" (`coverage`). The run
FAILS (nothing written) only when a REF fails E1's audit or over `MASKED_MEMBERS_MAX` of current members are masked.

THE NIGHTLY I6 (`i6_check`), both sides of each part built under ONE run key and ONE aid set: (1) the reference
columns of `fetched_through` (REF and that day's members, run key `i6|<day>`) from the store's arrays against the
same from the KEPT 16:20 fetch (`league.xs.book.kept`) when a panel instance decided that day, else from a fresh
253-session fetch; (2) each live decision of that day THAT READ BARS (`eq_rebalances` rows with a `bars_sha`,
read-only) rebuilt from the store against the kept file, by E1's `_bars_verdict`, OVER THE COLUMNS IT HAD. THE
VENDOR'S CENTS: a live fetch and a later store are not byte-identical by assumption, so part 1's verdict is the bars'
(`compare_bars`: sessions and raw prices exactly, the as-of prices of the decision day within `rounding_bound`, a
volume-only difference a note), and the two ctx shas (`ctx_bytes(build(...))` of each side, the reference NEEDS) are
reported beside it with `bytes_equal`. A False is a critical alarm. The job emits a boolean a part, two shas and
counts, nothing else.

THE I6 IS FALSE ON A PRICE THAT DIFFERS AND ON NOTHING THE LIVE BOOK ITSELF TOLERATES (a False holds every open of the
lane: `league.swarm.elane_xs.live_ready`). Three things the book decides on, each COUNTED beside the verdict and
never a mismatch: LATE, a column the kept fetch held no bar of the day for and the store does (`xs.book.complete` let
the decide go without it, B13, and the book's own morning audit calls it a note: `xs.book.same`); the rest of that
column's history is still held to the store. ABSENT, a column one side has and the other lacks (a member tonight's
universe run added or dropped as of the day, after the 16:20 columns were built: a membership gap the receipt shows,
never a bar that differs). UNREAD, a decision that read bars and has no kept fetch to be held to: its `live` entry is
None, never False (a failed decide whose fetch was never whole wrote no file and read no bars: it is not a row of
this part at all; A17: a hold day the House could not ask is an alarm, never an exit).

Data never leaves the House's state directory. The receipt carries counts and verdicts, never a price or a ticker.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from . import equity_universe as U

BARS = "/v1/alpaca/v2/stocks/bars"
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 3300
TRIES = 3
BACKOFF_S = (5, 20)
INCREMENTAL_SESSIONS = 7
FULL_EVERY_DAYS = 6.5
ACCEPT_SHARE = 0.95
ACCEPT_FIRST = 5
REUSED_USD = 5_000_000.0
INSANE_SHARE = 0.01
SECOND_READ_GAP = 0.02
MASKED_MEMBERS_MAX = 0.05
REVISIONS_ALARM = 20
#: The reference NEEDS of the nightly I6's first part.
I6_NEEDS = {"panel": "sp500", "history": 252, "max_names": 12, "rebalance": "weekly", "weekday": 0,
            "max_hold_sessions": 60}
#: Symbols a request of open assets (39 x 253 bars is one page: the live fetch's chunk), bars a page, pages a call.
BATCH = 39
#: Symbols a request of a WHOLE HISTORY (`full`, and the daily run's refetch of a restated asset): a request's answer
#: is held as rows until it is placed, and 39 names x a span's 1,450 sessions is 56,000 rows, 40 MB and more beside
#: the arrays. A page is 10,000 bars whatever the batch, so a smaller one costs no call: 8 names are two pages.
WHOLE_BATCH = 8
PAGE_LIMIT = 10000
MAX_PAGES = 400
#: An asset's bars are fetched from this many calendar days before its first spell (a year of look-back) to this many
#: after its last (a lot of a name that left keeps a bar and a mark until it is sold: the hold cap and more).
LOOKBACK_DAYS = 400
KEEP_ENDED_DAYS = 120
#: D20: a name's own half-spread needs this many samples at a fill point.
MIN_SAMPLES = 8
#: The jumps are read, and an old store copied, this many columns at a time (a whole panel's arrays are never
#: doubled in memory).
JUMP_COLUMNS = 64
#: Second reads a run (two calls each); the rest wait for the next run, their bars standing meanwhile.
SECOND_READS_RUN = 60
#: `live_from` is set by the first run that finds at least this share of the day's members in the constitution's
#: `equity_money.universe.stock`: the universe deploy is in force.
LIVE_FROM_SHARE = 0.5
#: The I6's as-of prices are equal to a millionth, or to the vendor's cents when that is more (E1's `_as_of_equal`).
I6_FLOOR = 1e-6
LIVE_DB = "live.sqlite"
SPREADS_FILE = "spreads.json"
#: The UTC days of the job's failed runs since its last good one (`<state>/equity-daily/`, outside every manifest):
#: two days running is an alarm, critical while a panel instance is live.
FAILURES_FILE = "panel-failures.json"
RAW_FIELDS = ("o", "h", "l", "c", "v")
ADJ_FIELDS = ("o", "h", "l", "c")


# ------------------------------------------------------------------------------------------------- the gateway
def _sealed(start: str, end: str, asof: str | None) -> None:
    """THE SEAL (X5): no request names a day of a reserve year. ValueError, and the request is not sent."""
    from ..xs import config as xs_config

    try:
        first, last = dt.date.fromisoformat(str(start)[:10]), dt.date.fromisoformat(str(end)[:10])
        named = None if asof is None else dt.date.fromisoformat(str(asof)[:10])
    except ValueError:
        raise ValueError("a bars request names its start, its end and its asof as days") from None
    if last < first:
        raise ValueError("a bars request ends before it starts")
    for year in xs_config.RESERVE_YEARS:
        if first.year <= year <= last.year or (named is not None and named.year == year):
            raise ValueError(f"{year} is never fetched: the request's span or asof touches it (the reserve)")


def _call(gateway: Any, params: Mapping[str, Any], tries: int, sleep: Callable[[float], None],
          count: dict[str, int] | None) -> Any:
    last: BaseException | None = None
    for attempt in range(max(1, int(tries))):
        if count is not None:
            count["calls"] = count.get("calls", 0) + 1
        try:
            return gateway.get(BARS, dict(params))
        except Exception as exc:  # noqa: BLE001 - the gateway's own error: tried again, then the caller's
            last = exc
            if attempt + 1 < max(1, int(tries)):
                sleep(U.backoff(exc, attempt))      # (`BACKOFF_S`; after a 429 the longer `U.RATE_WAIT_S`)
    if count is not None:
        count["failed"] = count.get("failed", 0) + 1
    status = getattr(last, "status", None)
    raise RuntimeError(f"a bars call failed {max(1, int(tries))} times: {type(last).__name__}"
                       f"{'' if status is None else f' (HTTP {status})'}")  # its kind, never the venue's own text


def fetch_asof(gateway: Any, symbols: Sequence[str], start: str, end: str, *, adjustment: str,
               asof: str | None, tries: int = TRIES, timeframe: str = "1Day",
               sleep: Callable[[float], None] = time.sleep,
               count: dict[str, int] | None = None) -> dict[str, list[dict[str, Any]]]:
    """{symbol: [bar rows {t, o, h, l, c, v} in time order]} (E1's `equity_data.fetch` paging with the venue's `asof`;
    None: the venue's own default, today). Each call is tried up to `tries` times, backing off `BACKOFF_S` (after an
    HTTP 429 the longer `equity_universe.RATE_WAIT_S`; RuntimeError when it still fails). THE JOB PACES ITS CALLS: it
    hands this the paced client (`equity_universe.Paced`: a pause before every call). ValueError for a span touching
    2020 ("2020 is never fetched": the request is
    not sent) and for a malformed answer. `count`: {"calls", "failed"}, added to."""
    _sealed(start, end, asof)
    names = [str(s) for s in symbols]
    out: dict[str, dict[str, dict[str, Any]]] = {s: {} for s in names}
    token = None
    for _ in range(MAX_PAGES):
        params: dict[str, Any] = {"symbols": ",".join(names), "timeframe": timeframe, "start": start, "end": end,
                                  "adjustment": adjustment, "feed": "sip", "limit": PAGE_LIMIT}
        if asof is not None:
            params["asof"] = asof
        if token:
            params["page_token"] = token
        answer = _call(gateway, params, tries, sleep, count)
        bars = answer.get("bars") if isinstance(answer, Mapping) else None
        if bars is None and isinstance(answer, Mapping) and "bars" in answer:
            bars = {}  # the venue's answer for a span with no bar at all
        if not isinstance(bars, Mapping):
            raise ValueError("the bars answer has no bars")
        for symbol, rows in bars.items():
            seen = out.setdefault(str(symbol), {})
            if rows is None:
                continue
            if not isinstance(rows, list):
                raise ValueError("the bars of a symbol are not a list")
            for row in rows:
                if not isinstance(row, Mapping) or not row.get("t"):
                    raise ValueError("a bar is not an object with a time")
                stamp = str(row["t"])
                if stamp in seen:
                    raise ValueError("a bar came twice")
                seen[stamp] = {"t": stamp, **{k: row.get(k) for k in RAW_FIELDS}}
        token = answer.get("next_page_token") if isinstance(answer, Mapping) else None
        if not token:
            return {s: [rows[k] for k in _in_order(rows)] for s, rows in out.items()}
    raise ValueError(f"the bars did not end within {MAX_PAGES} pages")


def _in_order(stamps: Mapping[str, Any]) -> list[str]:
    """Bar times oldest first. The venue writes one format (RFC 3339 in UTC), which sorts as text; anything else is
    parsed (`_when`)."""
    if all(len(s) == 20 and s.endswith("Z") for s in stamps):
        return sorted(stamps)
    return sorted(stamps, key=_when)


def _when(stamp: str) -> dt.datetime:
    """A bar time as a UTC moment, for ordering (a bare day is its New York midnight). ValueError when it is not one."""
    from .equity_data import NEW_YORK, ny_moment

    if len(stamp) == 10:
        return dt.datetime.combine(dt.date.fromisoformat(stamp), dt.time(0), NEW_YORK).astimezone(dt.timezone.utc)
    return ny_moment(stamp).astimezone(dt.timezone.utc)


# ------------------------------------------------------------------------------------------------- the plan
@dataclass(frozen=True)
class Request:
    """One bars request series: `symbols` at `asof` over [start, end] (ISO days), and the aid of each symbol."""

    asof: str | None
    symbols: tuple[str, ...]
    start: str
    end: str
    aids: tuple[int, ...]


def _open(row: Mapping[str, Any]) -> bool:
    spells = row.get("spells") or ()
    return bool(row.get("ref")) or bool(spells and spells[-1][2] is None)


def _span_windows(days: Sequence[dt.date]) -> list[tuple[dt.date, dt.date]]:
    """(first session, last session) of each store span that `days` reaches."""
    out = []
    for first, end in U.spans():
        inside = [d for d in days if first <= d and (end is None or d <= end)]
        if inside:
            out.append((inside[0], inside[-1]))
    return out


def requests(assets: Mapping[str, Any], days: Sequence[dt.date], *, since: dt.date | None = None,  # noqa: A002
             only: set[int] | None = None, batch: int = BATCH) -> list[Request]:
    """The requests of a fetch over `days` (the store's sessions): the open assets and REF together at today's `asof`,
    `batch` symbols a request and a request a span; each ended asset alone, `asof` its last member session of the
    store, from `LOOKBACK_DAYS` before its first spell to `KEEP_ENDED_DAYS` after its last. `since`: nothing before
    this day (the daily window). `only`: these aids alone. No request touches 2020: every window lies inside a span."""
    days = list(days)
    windows = _span_windows(days)
    order = [aid for aid in U.columns(assets) if only is None or aid in only]
    open_aids = [aid for aid in order if _open(assets[str(aid)])]
    out: list[Request] = []
    for first, last in windows:
        start = first if since is None else max(first, since)
        if start > last:
            continue
        for at in range(0, len(open_aids), max(1, int(batch))):
            group = open_aids[at:at + max(1, int(batch))]
            out.append(Request(None, tuple(str(assets[str(a)]["symbol"]) for a in group), start.isoformat(),
                               last.isoformat(), tuple(group)))
    for aid in order:
        row = assets[str(aid)]
        if _open(row):
            continue
        spells = U._spells_of(row)
        inside = [d for d in days if any(s <= d < e for _, s, e, _ in spells)]
        if not inside:
            continue  # no session of the store inside the spell: no bar is asked for it
        low = spells[0][1] - dt.timedelta(days=LOOKBACK_DAYS)
        high = spells[-1][2] + dt.timedelta(days=KEEP_ENDED_DAYS)
        for first, last in windows:
            start = max(first, low) if since is None else max(first, low, since)
            end = min(last, high)
            if start <= end:
                out.append(Request(inside[-1].isoformat(), (str(row["symbol"]),), start.isoformat(), end.isoformat(),
                                   (aid,)))
    return out


def plan(assets: Mapping[str, Any],  # noqa: A002
         days: Sequence[dt.date]) -> list[tuple[str | None, list[str], str, str]]:
    """[(asof, symbols, start, end)]: open spells together at today's `asof`, each ended spell at its own; no span
    touches 2020."""
    return [(r.asof, list(r.symbols), r.start, r.end) for r in requests(assets, days)]


# ------------------------------------------------------------------------------------------------- the arrays
class Grid:
    """The store's two arrays being filled: `raw` (n_days, n_assets, 5) and `adj` (n_days, n_assets, 4), NaN where no
    bar, over `days` (dates) and `aids` (the columns)."""

    def __init__(self, days: Sequence[dt.date], aids: Sequence[int]):
        self.days = list(days)
        self.aids = [int(a) for a in aids]
        self.row = {d.isoformat(): i for i, d in enumerate(self.days)}
        self.col = {aid: k for k, aid in enumerate(self.aids)}
        self.raw = np.full((len(self.days), len(self.aids), 5), np.nan)
        self.adj = np.full((len(self.days), len(self.aids), 4), np.nan)
        self.dropped = 0
        self._stamps: dict[str, int | None] = {}

    def _index(self, stamp: str) -> int | None:
        if stamp not in self._stamps:
            from .equity_data import ny_day

            try:
                self._stamps[stamp] = self.row.get(ny_day(stamp).isoformat())
            except (TypeError, ValueError):
                self._stamps[stamp] = None
        return self._stamps[stamp]

    def place(self, rows: Mapping[str, Sequence[Mapping[str, Any]]], aid_of: Mapping[str, int],
              adjustment: str) -> None:
        """Put one answer's rows on their days and columns. A row off the grid's days, or with a field that is no
        finite number, is dropped and counted (never half a bar)."""
        target, fields = (self.raw, RAW_FIELDS) if adjustment == "raw" else (self.adj, ADJ_FIELDS)
        for symbol, aid in aid_of.items():
            k = self.col.get(int(aid))
            if k is None:
                continue
            for row in rows.get(symbol) or ():
                i = self._index(str(row.get("t")))
                values = [row.get(f) for f in fields]
                if i is None or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                                    for v in values):
                    self.dropped += 1
                    continue
                target[i, k, :] = values

    def clear(self, aids: Sequence[int]) -> None:
        for aid in aids:
            k = self.col.get(int(aid))
            if k is not None:
                self.raw[:, k, :] = np.nan
                self.adj[:, k, :] = np.nan

    def align(self) -> int:
        """A bar is its raw row AND its adjusted row: a cell with one and not the other is no bar (counted)."""
        odd = np.isfinite(self.raw[:, :, 3]) != np.isfinite(self.adj[:, :, 3])
        self.raw[odd] = np.nan
        self.adj[odd] = np.nan
        return int(odd.sum())


@dataclass
class Panel:
    """The panel store as its writer reads it back (every file checked against the manifest's sha256). `raw` and `adj`
    are MAPPED from the files (`load_panel`), every other array is a copy."""

    days: list[dt.date]
    early: np.ndarray
    aids: list[int]
    raw: np.ndarray
    adj: np.ndarray
    member: np.ndarray
    tradable: np.ndarray
    hs: np.ndarray
    manifest: dict[str, Any]

    def release(self) -> None:
        """Drop the two mapped arrays (the store's bars: about 120 MB of the child's address space at the real panel's
        size); the days, the aids, the masks and the manifest stay. THE JOB'S MEMORY (`league.ops.__main__.limit`: the
        child's address space is capped 500 MB above its start): the old store is mapped by ONE reader at a time and
        never while a whole history's answer is being held as rows. Mapped twice (by `run` and again by
        `incremental`) beside the grid being built, a night with 25 names ex-dividend failed with a MemoryError and
        left its restatements to the next night, which failed the same way."""
        empty_raw = np.zeros((0, len(self.aids), 5))
        empty_adj = np.zeros((0, len(self.aids), 4))
        self.raw, self.adj = empty_raw, empty_adj


def _days_of(values: np.ndarray) -> list[dt.date]:
    from ..equity import store as eq_store

    return [eq_store.from_ordinal(int(v)) for v in values.tolist()]


def load_panel(root: str | Path) -> Panel | None:
    """The panel under `<root>/panel`, or None when there is none. ValueError when a file is not the one the manifest
    names (a store being rewritten, or damaged): nothing is read from it."""
    from ..xs import store as xs_store

    base = Path(root) / xs_store.PANEL_DIR
    try:
        manifest = json.loads((base / getattr(xs_store, "PANEL_MANIFEST", "PANEL_MANIFEST.json"))
                              .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict):
        return None
    arrays: dict[str, np.ndarray] = {}
    shas = manifest.get("sha256") if isinstance(manifest.get("sha256"), Mapping) else {}
    for name in xs_store.PANEL_FILES:
        digest = hashlib.sha256()
        try:
            with open(base / name, "rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
            if digest.hexdigest() != shas.get(name):
                raise ValueError(f"the panel's {name} is not the file its manifest names")
            # mapped, never copied whole: the old store and the one being built are not both in memory
            arrays[name[:-4]] = np.load(base / name, mmap_mode="r", allow_pickle=False)
        except OSError:
            raise ValueError(f"the panel lacks {name}") from None
    n, m = int(arrays["days"].shape[0]), int(arrays["aids"].shape[0])
    for name, shape in (("early", (n,)), ("raw", (n, m, 5)), ("adj", (n, m, 4)), ("member", (n, m)),
                        ("tradable", (n, m)), ("hs", (m, 2))):
        if arrays[name].shape != shape:
            raise ValueError(f"the panel's {name} has the shape {arrays[name].shape}, not {shape}")
    return Panel(days=_days_of(np.asarray(arrays["days"])), early=np.asarray(arrays["early"]).astype(bool),
                 aids=[int(a) for a in np.asarray(arrays["aids"]).tolist()], raw=arrays["raw"], adj=arrays["adj"],
                 member=np.asarray(arrays["member"]).astype(bool), tradable=np.asarray(arrays["tradable"]).astype(bool),
                 hs=np.array(arrays["hs"]), manifest=manifest)


def _fetch_into(grid: Grid, gateway: Any, wanted: Sequence[Request], *, sleep: Callable[[float], None],
                count: dict[str, int]) -> None:
    """Every request of `wanted`, raw then all, each answer placed and dropped before the next is asked for."""
    for req in wanted:
        aid_of = dict(zip(req.symbols, req.aids))
        for adjustment in ("raw", "all"):
            rows = fetch_asof(gateway, req.symbols, req.start, req.end, adjustment=adjustment, asof=req.asof,
                              sleep=sleep, count=count)
            grid.place(rows, aid_of, adjustment)


def _revised(old_raw: np.ndarray, new_raw: np.ndarray) -> int:
    """Raw bars both readings have whose open, high, low or close differ (a volume alone is not a revision)."""
    both = np.isfinite(old_raw[..., 3]) & np.isfinite(new_raw[..., 3])
    return int((both & np.any(old_raw[..., :4] != new_raw[..., :4], axis=-1)).sum())


def _assets(root: str | Path, assets: Mapping[str, Any] | None) -> Mapping[str, Any]:  # noqa: A002
    if assets is not None:
        return assets
    universe = U.read_universe(root)
    if universe is None:
        raise ValueError("there is no universe: the membership job has not written one")
    return universe["assets"]


def full(root: str | Path, gateway: Any, last: dt.date, *, assets: Mapping[str, Any] | None = None,  # noqa: A002
         sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """The weekly whole refetch (one request series an asset, `WHOLE_BATCH` open names a request), same shape as
    `incremental`. Raises on a call that still fails after its tries: `run` then falls back to `incremental` and
    `full_at` does not move. The old store is mapped only AFTER the fetch (to count the revisions) and released."""
    assets = _assets(root, assets)
    calendar = U.store_sessions(last)
    days = [d for d, _ in calendar]
    aids = U.columns(assets)
    grid = Grid(days, aids)
    count = {"calls": 0, "failed": 0}
    _fetch_into(grid, gateway, requests(assets, days, batch=WHOLE_BATCH), sleep=sleep, count=count)
    odd = grid.align()
    revisions = 0
    try:
        before = load_panel(root)
    except ValueError:
        before = None
    if before is not None:
        rows = [i for i, d in enumerate(before.days) if d.isoformat() in grid.row]
        mine = [grid.row[before.days[i].isoformat()] for i in rows]
        for k, aid in enumerate(before.aids):   # a column at a time: the two stores are never both copied
            if rows and aid in grid.col:
                revisions += _revised(np.asarray(before.raw[rows, k]), grid.raw[mine, grid.col[aid]])
        before.release()
    return {"days": days, "early": [bool(e) for _, e in calendar], "aids": aids, "raw": grid.raw, "adj": grid.adj,
            "vintage": {aid: last for aid in aids}, "revisions": revisions, "calls": count["calls"],
            "mode": "full", "refetched": len(aids), "appended": 0, "misaligned": odd, "dropped": grid.dropped}


def ratios_equal(store_raw: np.ndarray, store_adj: np.ndarray, fetch_raw: np.ndarray, fetch_adj: np.ndarray) -> bool:
    """THE VINTAGE TEST of one asset on the overlap ((k, 5) and (k, 4) arrays): on every session both readings have a
    bar, the adj/raw close ratio of the fetch equals the store's within the vendor's cents
    (`league.xs.config.rounding_bound` of the two adjusted closes). False too when a bar the store has is gone from
    the fetch, and when the fetch has a bar and no session holds both (nothing ties the new rows to the store's
    basis). A bar the store lacked and the fetch now has (served late) says nothing against the store; an overlap
    with no bar on either side neither (True)."""
    from ..xs import config as xs_config

    had = np.isfinite(store_raw[:, 3]) & np.isfinite(store_adj[:, 3])
    has = np.isfinite(fetch_raw[:, 3]) & np.isfinite(fetch_adj[:, 3])
    if bool(np.any(had & ~has)) or (bool(has.any()) and not bool(np.any(had & has))):
        return False
    for i in np.flatnonzero(had & has).tolist():
        rs, as_, rf, af = (float(store_raw[i, 3]), float(store_adj[i, 3]), float(fetch_raw[i, 3]),
                           float(fetch_adj[i, 3]))
        if min(rs, as_, rf, af) <= 0:
            return False
        if abs((af / rf) / (as_ / rs) - 1.0) > xs_config.rounding_bound(as_, af):
            return False
    return True


def incremental(root: str | Path, gateway: Any, last: dt.date, *, assets: Mapping[str, Any] | None = None,  # noqa: A002
                blank: Sequence[Sequence[Any]] = (), sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """The daily run's arrays (the module docstring's vintage rule): {days, early, aids, raw, adj, vintage, revisions,
    calls, ...}. ValueError when there is no store to grow, or its sessions are not the calendar's first ones (a
    whole refetch is the answer then). `blank`: the audit's [(aid, day)] bars read as missing, so a bar the store
    blanked is not read as one that came back."""
    assets = _assets(root, assets)
    before = load_panel(root)
    if before is None:
        raise ValueError("there is no panel store to grow")
    calendar = U.store_sessions(last)
    days = [d for d, _ in calendar]
    n_old = len(before.days)
    if days[:n_old] != before.days:
        raise ValueError("the store's sessions are not the calendar's first ones")
    aids = U.columns(assets)
    grid = Grid(days, aids)
    old_col = {aid: k for k, aid in enumerate(before.aids)}
    kept = [aid for aid in aids if aid in old_col]
    for at in range(0, len(kept), JUMP_COLUMNS):   # a block of columns at a time: the old store is never copied whole
        block = kept[at:at + JUMP_COLUMNS]
        grid.raw[:n_old, [grid.col[a] for a in block]] = before.raw[:, [old_col[a] for a in block]]
        grid.adj[:n_old, [grid.col[a] for a in block]] = before.adj[:, [old_col[a] for a in block]]
    # The grid now holds every bar of the old store: its mapping is dropped BEFORE the first answer is asked for
    # (`Panel.release`: the old store, the grid and a request's rows were once all three in the address space).
    before.release()
    start = max(0, min(len(days) - INCREMENTAL_SESSIONS, n_old - (INCREMENTAL_SESSIONS - 1)))
    spans_of = [next((k for k, (first, end) in enumerate(U.spans()) if first <= d and (end is None or d <= end)), None)
                for d in (days[start], days[-1])]
    if spans_of[0] != spans_of[1]:
        raise ValueError("the store is a span behind the calendar")
    window = Grid(days[start:], aids)
    count = {"calls": 0, "failed": 0}
    wanted = requests(assets, days, since=days[start])
    _fetch_into(window, gateway, wanted, sleep=sleep, count=count)
    odd = window.align()
    for aid, day in blank:
        i, k = window.row.get(str(day)[:10]), window.col.get(int(aid))
        if i is not None and k is not None:
            window.raw[i, k, :] = np.nan
            window.adj[i, k, :] = np.nan
    overlap = n_old - start
    active = [aid for req in wanted for aid in req.aids]
    again = {aid for aid in aids if aid not in old_col}
    revisions = 0
    for aid in active:
        if aid in again:
            continue
        k, w = grid.col[aid], window.col[aid]
        fresh = bool(np.isfinite(window.raw[overlap:, w, 3]).any()) and not bool(
            np.isfinite(grid.raw[start:n_old, k, 3]).any())  # bars to append, and none of the store's to hold them to
        if fresh or not ratios_equal(grid.raw[start:n_old, k], grid.adj[start:n_old, k], window.raw[:overlap, w],
                                     window.adj[:overlap, w]) \
                or _revised(grid.raw[start:n_old, k], window.raw[:overlap, w]):
            again.add(aid)  # restated, or the tape itself revised: one fetch's series again, counted below
            continue
        grid.raw[start:, k] = window.raw[:, w]
        grid.adj[start:, k] = window.adj[:, w]
    vintage = {}
    stamps = before.manifest.get("vintage") if isinstance(before.manifest.get("vintage"), Mapping) else {}
    for aid in aids:
        try:
            vintage[aid] = dt.date.fromisoformat(str(stamps.get(str(aid)))[:10])
        except ValueError:
            vintage[aid] = last
    if again:
        whole = Grid(days, sorted(again))
        _fetch_into(whole, gateway, requests(assets, days, only=again, batch=WHOLE_BATCH), sleep=sleep, count=count)
        odd += whole.align()
        for aid in sorted(again):
            k, w = grid.col[aid], whole.col[aid]
            if aid in old_col:
                # (the grid's own column is still the old store's: an asset fetched again took no row of the window)
                revisions += _revised(grid.raw[:n_old, k], whole.raw[:n_old, w])
            grid.raw[:, k] = whole.raw[:, w]
            grid.adj[:, k] = whole.adj[:, w]
            vintage[aid] = last
        grid.dropped += whole.dropped
    return {"days": days, "early": [bool(e) for _, e in calendar], "aids": aids, "raw": grid.raw, "adj": grid.adj,
            "vintage": vintage, "revisions": revisions, "calls": count["calls"], "mode": "incremental",
            "refetched": len(again), "appended": len(set(active) - again), "misaligned": odd,
            "dropped": grid.dropped + window.dropped}


# ------------------------------------------------------------------------------------------------- D19
def valid_bars(raw: np.ndarray) -> np.ndarray:
    """D4's VALID BAR, bool over `raw`'s leading axes: a raw close above 0 with a raw volume above 0, both finite (the
    vendor's flat bar of volume 0, a session without a trade, is no valid bar)."""
    raw = np.asarray(raw, dtype=np.float64)
    close, volume = raw[..., 3], raw[..., 4]
    with np.errstate(invalid="ignore"):
        return np.isfinite(close) & np.isfinite(volume) & (close > 0) & (volume > 0)


def sane_bars(prices: np.ndarray) -> np.ndarray:
    """OHLC sanity, bool over the leading axes of `prices` (..., >= 4: o h l c): every price finite and 0 < low <=
    min(open, close) <= max(open, close) <= high (E1's audit's rule)."""
    o, h, l, c = (np.asarray(prices, dtype=np.float64)[..., k] for k in range(4))
    with np.errstate(invalid="ignore"):
        return (np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c) & (l > 0)
                & (l <= np.minimum(o, c)) & (np.maximum(o, c) <= h))


def acceptance(series: Mapping[str, Any], spell: Sequence[Any]) -> str | None:
    """D19: None when the spell's series is accepted, else its mask ("no_bars" | "reused" | "insane"). `series`:
    {"days": the store's sessions (dates), "raw": the asset's (n, 5) raw bars, "adj": its (n, 4) adjusted bars
    (optional)}; `spell`: (ticker, start, end | None, ...). A spell with no session in the store has nothing to
    accept (None)."""
    days = list(series["days"])
    raw = np.asarray(series["raw"], dtype=np.float64)
    start, end = U._day(spell[1]), U._day(spell[2]) if len(spell) > 2 else None
    inside = np.array([start <= d and (end is None or d < end) for d in days], dtype=bool)
    if not inside.any():
        return None
    has = np.isfinite(raw[:, 3])
    if has.any():
        sane = sane_bars(raw)
        if series.get("adj") is not None:
            sane &= sane_bars(np.asarray(series["adj"], dtype=np.float64))
        if float((has & ~sane).sum()) / float(has.sum()) > INSANE_SHARE:
            return "insane"
    valid = valid_bars(raw) & inside
    if not valid.any():
        return "no_bars"
    dollars = np.sort(raw[valid, 3] * raw[valid, 4])
    half = dollars.shape[0] // 2
    median = float(dollars[half]) if dollars.shape[0] % 2 else (float(dollars[half - 1]) + float(dollars[half])) / 2.0
    if median < REUSED_USD:
        return "reused"
    members = np.flatnonzero(inside)
    first = int(np.searchsorted(members, np.flatnonzero(valid)[0]))
    covered = int(valid.sum()) >= ACCEPT_SHARE * members.shape[0]
    return None if covered and first <= ACCEPT_FIRST else "no_bars"


def coverage(member: Any, raw: Any, days: Sequence[dt.date], *, masked: Sequence[bool] | None = None,
             floor: float = 0.97) -> dict[str, Any]:
    """D19: {"coverage": {year: {"member_days", "with_bar", "share"}}, "train_years_ok": [...], "verdict"}.

    coverage[y] = the member-days of year y with a valid bar (`valid_bars`) of an unmasked asset / the member-days of
    y, for every year the days hold (share None for a year with no member-day). `train_years_ok`: the years of
    `league.xs.config.TRAIN_YEARS` at or above `floor`. THE VERDICT: "ok" when every Train year and both judged years
    (Validation's and the look's: 2025 and 2026) are at or above it; "low_coverage" when all but one of the Train
    years and both judged years are (the year below is dropped from the bar, stated); else "insufficient" (a year the
    store does not hold is not at the floor: fail closed). `masked`: bool an asset (a masked asset's member-days
    count below the line, never above it). ValueError for a floor outside [0.97, 1.0] (tighten only)."""
    from ..equity import config as eq_config
    from ..xs import config as xs_config

    member = np.asarray(member, dtype=bool)
    valid = valid_bars(raw)
    if member.shape != valid.shape or member.shape[0] != len(days):
        raise ValueError("coverage: member, raw and days do not agree on their shapes")
    floor = float(floor)
    if not 0.97 <= floor <= 1.0:
        raise ValueError(f"the coverage floor is 0.97 to 1.0 (tighten only), not {floor!r}")
    if masked is not None:
        hidden = np.asarray(masked, dtype=bool)
        if hidden.shape != (member.shape[1],):
            raise ValueError("coverage: masked is one bool an asset")
        valid = valid & ~hidden[None, :]
    years = np.array([d.year for d in days], dtype=np.int64)
    table: dict[str, dict[str, Any]] = {}
    share: dict[int, float] = {}
    for year in sorted(set(years.tolist())):
        rows = years == year
        member_days = int(member[rows].sum())
        with_bar = int((member[rows] & valid[rows]).sum())
        value = with_bar / member_days if member_days else None
        table[str(year)] = {"member_days": member_days, "with_bar": with_bar, "share": value}
        if value is not None:
            share[year] = value
    judged_years = (eq_config.WINDOWS["validation"][0].year, eq_config.LOOK_CAP.year)
    ok = [y for y in xs_config.TRAIN_YEARS if share.get(y, -1.0) >= floor]
    judged = all(share.get(y, -1.0) >= floor for y in judged_years)
    if judged and len(ok) == len(xs_config.TRAIN_YEARS):
        verdict = "ok"
    elif judged and len(ok) >= len(xs_config.TRAIN_YEARS) - 1:
        verdict = "low_coverage"
    else:
        verdict = "insufficient"
    return {"coverage": table, "train_years_ok": ok, "verdict": verdict}


def _utc(day: dt.date, hour: int, minute: int) -> str:
    from .equity_data import NEW_YORK

    moment = dt.datetime.combine(day, dt.time(hour, minute), NEW_YORK).astimezone(dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def second_read(gateway: Any, symbol: str, day: dt.date, *, asof: str | None, daily: float | None = None,
                early: bool = False, sleep: Callable[[float], None] = time.sleep,
                count: dict[str, int] | None = None) -> bool | None:
    """D19's second read of ONE daily bar of a big move (the job reads the session of the move and the one before):
    True when the session's 1Min bars agree with the daily bar, False when they contradict it by more than
    `SECOND_READ_GAP` (their last regular-session price, the closing minute's with its cross, against the daily
    close), None when they cannot be read (the bar stands). `daily`: the store's raw close of `day` (None: read
    again, one more call). `early`: a 13:00 close."""
    from .equity_data import ny_moment

    try:
        if daily is None:
            rows = fetch_asof(gateway, [symbol], day.isoformat(), day.isoformat(), adjustment="raw", asof=asof,
                              sleep=sleep, count=count).get(symbol) or []
            daily = float(rows[-1]["c"]) if rows else None
        close_at = dt.time(13, 0) if early else dt.time(16, 0)
        minutes = fetch_asof(gateway, [symbol], _utc(day, 9, 30), _utc(day, close_at.hour, close_at.minute),
                             adjustment="raw", asof=asof, timeframe="1Min", sleep=sleep, count=count).get(symbol) or []
        session = [r for r in minutes if ny_moment(r["t"]).date() == day
                   and dt.time(9, 30) <= ny_moment(r["t"]).time() <= close_at]
        price = float(session[-1]["c"]) if session else None
    except (RuntimeError, ValueError, TypeError, KeyError):
        return None
    if daily is None or price is None or not (math.isfinite(daily) and math.isfinite(price)) or min(daily, price) <= 0:
        return None
    return abs(price / daily - 1.0) <= SECOND_READ_GAP


def jumps(raw: np.ndarray, adj: np.ndarray, days: Sequence[dt.date]) -> dict[str, list[tuple[int, int, int]]]:
    """E1's "splits" rule read per column, never a mask: {"moves": [(row, column, the row of the bar before)] (a raw
    close that moves past E1's `RAW_JUMP` between two of the asset's bars with no ratio jump), "unexplained": [...]
    (a raw/all ratio jump past E1's `SPLIT_JUMP`, or the cents' rounding when that is more, that the raw close does
    not show)}. A step is read between two bars of ONE span: nothing is read across the 2020 gap."""
    from ..xs import config as xs_config
    from .equity_data import RAW_JUMP, SPLIT_JUMP, SPLIT_RAW_TOLERANCE

    out: dict[str, list[tuple[int, int, int]]] = {"moves": [], "unexplained": []}
    if raw.shape[0] != len(days):
        raise ValueError("jumps: the arrays and the days do not agree")
    index = {d: i for i, d in enumerate(days)}
    for first, last in _span_windows(days):
        lo, hi = index[first], index[last] + 1
        for c0 in range(0, raw.shape[1], JUMP_COLUMNS):
            rc, ac = raw[lo:hi, c0:c0 + JUMP_COLUMNS, 3], adj[lo:hi, c0:c0 + JUMP_COLUMNS, 3]
            with np.errstate(invalid="ignore"):
                ok = np.isfinite(rc) & np.isfinite(ac) & (rc > 0) & (ac > 0)
            rows = np.where(ok, np.arange(hi - lo)[:, None], -1)
            before = np.full_like(rows, -1)
            before[1:] = np.maximum.accumulate(rows, axis=0)[:-1]
            has = ok & (before >= 0)
            take = np.clip(before, 0, None)
            cols = np.broadcast_to(np.arange(rc.shape[1])[None, :], rows.shape)
            with np.errstate(invalid="ignore", divide="ignore"):
                p_rc, p_ac = rc[take, cols], ac[take, cols]
                jump = (p_rc / p_ac) / (rc / ac)
                move = p_rc / rc
                cents = xs_config.ROUNDING_GUARD * xs_config.ADJUSTED_HALF_STEP * (1 / p_ac + 1 / ac)
                stepped = has & (np.abs(jump - 1.0) > np.maximum(SPLIT_JUMP, cents))
                unexplained = stepped & (np.abs(move / jump - 1.0) > SPLIT_RAW_TOLERANCE)
                moved = has & ~stepped & (np.abs(move - 1.0) > RAW_JUMP) & (np.abs(1.0 / move - 1.0) > RAW_JUMP)
            for name, mask in (("moves", moved), ("unexplained", unexplained)):
                for i, k in zip(*np.nonzero(mask)):
                    out[name].append((lo + int(i), c0 + int(k), lo + int(before[i, k])))
    for found in out.values():
        found.sort()
    return out


def _percentile(values: Sequence[float], q: float) -> float:
    """The q-th percentile by linear interpolation between closest ranks (numpy's default), in plain arithmetic."""
    ordered = sorted(float(v) for v in values)
    at = (len(ordered) - 1) * q / 100.0
    low = int(math.floor(at))
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (at - low)


def _spreads(root: str | Path) -> Mapping[str, Any] | None:
    try:
        table = json.loads((Path(root) / SPREADS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return table if isinstance(table, Mapping) and isinstance(table.get("names"), Mapping) else None


def _bp(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def hs_table(root: str | Path, aids: Sequence[int]) -> Any:
    """D20: float64 (len(aids), 2), the half-spread fraction at the open and at the close, from spreads.json: max(the
    floor, the 75th percentile of the name's samples); fewer than 8 samples: the universe's 75th percentile; no file:
    `league.xs.config.HS_FALLBACK_BP`. Never below `league.xs.config.HS_FLOOR_BP`.

    The file's `names[aid]` carries the name's 75th percentile at each point (`open_bp`, `close_bp`) and its sample
    counts; `default` the universe's figure, computed here from the names with `MIN_SAMPLES` when the file has none
    (the 75th percentile of the name figures; the fallback with no such name)."""
    from ..xs import config as xs_config

    table = _spreads(root)
    out = np.empty((len(aids), 2), dtype=np.float64)
    points = (("open_bp", "n_open"), ("close_bp", "n_close"))
    defaults = list(xs_config.HS_FALLBACK_BP)
    names: Mapping[str, Any] = {}
    if table is not None:
        names = table["names"]
        given = table.get("default") if isinstance(table.get("default"), Mapping) else {}
        for j, (figure, samples) in enumerate(points):
            value = _bp(given.get(figure))
            if value is None:
                full = [_bp(row.get(figure)) for row in names.values()
                        if isinstance(row, Mapping) and _enough(row.get(samples))]
                full = [v for v in full if v is not None]
                value = _percentile(full, 75.0) if full else None
            if value is not None:
                defaults[j] = value
    for i, aid in enumerate(aids):
        row = names.get(str(int(aid))) if names else None
        for j, (figure, samples) in enumerate(points):
            own = _bp(row.get(figure)) if isinstance(row, Mapping) and _enough(row.get(samples)) else None
            value = max(xs_config.HS_FLOOR_BP, defaults[j] if own is None else own)
            out[i, j] = min(value, 9999.0) / 10000.0
    return out


def _enough(count: Any) -> bool:
    return isinstance(count, (int, float)) and not isinstance(count, bool) and count >= MIN_SAMPLES


def hs_share(root: str | Path, member: Any, days: Sequence[dt.date], aids: Sequence[int], *,
             masked: Any = None) -> float:
    """THE SPREADS' SHARE (the manifest's `hs_share`; the lane holds a Train pass to "provisional costs" under
    `elane.panel.spreads_min_share`): OF THE TRAIN ERAS' MEMBER-DAYS, THE SHARE WHOSE NAME IS CHARGED ITS OWN MEASURED
    HALF-SPREAD, that is, has `MIN_SAMPLES` kept samples at BOTH fill points (D20's first branch; every other
    member-day is charged the universe's figure). `member`: bool (len(days), len(aids)), the store's membership of
    the member columns (no REF column); the member-days counted are those of the sessions of
    `league.xs.config.TRAIN_YEARS` among `days`, of the columns not `masked` (bool an aid; None: none is). 0.0 with
    no spreads file, or a store that holds no Train-era member-day.

    WHY NOT TODAY'S MEMBERS (what it read before, and E4-SPEC 7.3's words): a sample is taken on a Train-era session
    of a name that is a member THAT day, and the Train eras end in 2024 (a cost table reads no sealed year). So a
    name that joined the index since can never have a sample, and a share of today's members fell by the index's
    turnover every year, by construction and for ever: under the bound the lane reads "train", takes no Validation
    and no look, and holds a seated program's opens. The share's own job is the backfill's (the spec's gate G2: until
    the cost table is measured, a pass is under provisional costs), and a table of nulls must still pull it down:
    both are questions about the sessions the samples are FOR. Those are a fixed population: the share climbs as
    the backfill fills the table, stands where the table is whole (under 1.0 by the names that were members on fewer
    than `MIN_SAMPLES` sample days), and no later change of the index moves it. THE COST, stated: a name that joined
    after the Train eras is charged the universe's figure (the 75th percentile of the measured names) in every run
    and in its replay twin, whatever this share reads."""
    from ..xs import config as xs_config

    table = _spreads(root)
    if table is None or not len(aids):
        return 0.0
    names = table["names"]
    full = np.array([isinstance(names.get(str(int(aid))), Mapping) and _enough(names[str(int(aid))].get("n_open"))
                     and _enough(names[str(int(aid))].get("n_close")) for aid in aids], dtype=bool)
    era = np.array([d.year in xs_config.TRAIN_YEARS for d in days], dtype=bool)
    inside = np.asarray(member, dtype=bool)
    if inside.shape != (len(days), len(aids)):
        raise ValueError("the membership is not one row a day and one column an aid")
    inside = inside[era]
    if masked is not None:
        inside = inside & ~np.asarray(masked, dtype=bool)[None, :]
    total = int(inside.sum())
    return float(int((inside & full[None, :]).sum()) / total) if total else 0.0


# ------------------------------------------------------------------------------------------------- the nightly I6
def compare_bars(raw_a: np.ndarray, adj_a: np.ndarray, raw_b: np.ndarray, adj_b: np.ndarray
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Two readings of the same sessions and columns ((n, m, 5) and (n, m, 4), the last row the decision day), by
    E1's morning rule read on arrays: (mismatch, volume), a bool a column. MISMATCH: the sessions with a bar differ,
    a raw open, high, low or close differs, or the as-of prices at the decision day (adj x raw_t / adj_t, t the
    column's last bar: E1's `_factor_row`) differ by more than the vendor's cents allow (`rounding_bound` of the four
    adjusted prices each is built from; `I6_FLOOR` when that is more). VOLUME: only a raw volume differs (a note:
    a session's consolidated volume is not final at 16:20)."""
    from ..xs import config as xs_config

    has_a, has_b = np.isfinite(raw_a[..., 3]), np.isfinite(raw_b[..., 3])
    sessions = np.all(has_a == has_b, axis=0) & np.all(np.isfinite(adj_a[..., 3]) == np.isfinite(adj_b[..., 3]), axis=0)
    both = has_a & has_b
    prices = np.all(np.where(both[..., None], raw_a[..., :4] == raw_b[..., :4], True), axis=(0, 2))
    n, m = raw_a.shape[0], raw_a.shape[1]
    as_of = np.ones(m, dtype=bool)
    for k in range(m):
        rows = []
        for raw, adj in ((raw_a, adj_a), (raw_b, adj_b)):
            with np.errstate(invalid="ignore"):
                ok = np.isfinite(raw[:, k, 3]) & np.isfinite(adj[:, k, 3]) & (raw[:, k, 3] > 0) & (adj[:, k, 3] > 0)
            hits = np.flatnonzero(ok)
            rows.append(int(hits[-1]) if hits.size else None)
        if rows[0] != rows[1]:
            as_of[k] = False
            continue
        if rows[0] is None:
            continue
        t = rows[0]
        old_c, new_c = float(adj_a[t, k, 3]), float(adj_b[t, k, 3])
        old_t, new_t = float(raw_a[t, k, 3]) / old_c, float(raw_b[t, k, 3]) / new_c
        x, y = adj_a[:, k, :], adj_b[:, k, :]
        here = np.isfinite(x) & np.isfinite(y)
        if not np.array_equal(np.isfinite(x), np.isfinite(y)) or bool(np.any((x[here] <= 0) | (y[here] <= 0))):
            as_of[k] = False
            continue
        a, b = x[here] * old_t, y[here] * new_t
        rounding = xs_config.ROUNDING_GUARD * xs_config.ADJUSTED_HALF_STEP * (
            1.0 / x[here] + 1.0 / old_c + 1.0 / y[here] + 1.0 / new_c)
        scale = np.maximum(np.maximum(np.abs(a), np.abs(b)), 1.0)
        as_of[k] = bool(np.all(np.abs(a - b) <= np.maximum(I6_FLOOR, rounding) * scale))
    mismatch = ~(sessions & prices & as_of)
    with np.errstate(invalid="ignore"):
        volume = ~mismatch & np.any(both & (raw_a[..., 4] != raw_b[..., 4]), axis=0)
    assert n == raw_b.shape[0]
    return mismatch, volume


def _ticker_on(row: Mapping[str, Any], day: dt.date) -> str:
    for ticker, start, end, _ in U._spells_of(row):
        if start <= day and (end is None or day < end):
            return ticker
    return str(row.get("symbol") or "")


def _aid_of(assets: Mapping[str, Any], symbol: str, day: dt.date) -> int | None:  # noqa: A002
    """The asset that traded under `symbol` on or before `day` (the latest spell of that ticker: a name that left
    the index keeps its column), or None."""
    best: tuple[dt.date, int] | None = None
    for aid, row in assets.items():
        for ticker, start, _, _ in U._spells_of(row):
            if ticker == symbol and start <= day and (best is None or start > best[0]):
                best = (start, int(aid))
    return None if best is None else best[1]


def _ctx_sha(days: Sequence[dt.date], raw: np.ndarray, adj: np.ndarray, *, day: dt.date, elig0: np.ndarray,
             ids: np.ndarray, dither_key: bytes, sector_perm: np.ndarray) -> str:
    from ..equity import store as eq_store
    from ..xs import config as xs_config
    from ..xs import ctx as xs_ctx
    from ..xs import program as xs_program

    budget = float(xs_config.XS_SLEEVE_USD)
    inputs = xs_ctx.inputs_from_arrays(np.array([eq_store.ordinal(d) for d in days], dtype=np.int32), raw, adj, day=day,
                                       elig0=elig0, ids=ids, dither_key=dither_key, sector_perm=sector_perm,
                                       needs=xs_program.parse_needs(dict(I6_NEEDS)), cash=budget, equity=budget,
                                       budget=budget, params={})
    return hashlib.sha256(xs_ctx.ctx_bytes(xs_ctx.build(inputs))).hexdigest()


def _kept(root: str | Path, day: dt.date) -> tuple[tuple[str, ...], Any] | None:
    """The 16:20 fetch a live panel decision of `day` read (`league.xs.book.kept`), or None (none, or the book's
    adapter is not built)."""
    try:
        from ..xs import book as xs_book

        return xs_book.kept(root, day)
    except NotImplementedError:
        return None


def _live_rows(path: str | Path | None, day: dt.date) -> list[dict[str, Any]]:
    """The day's `eq_rebalances` rows of live.sqlite THAT READ BARS (a `bars_sha`: a decide the House could not make
    for want of a whole fetch read none and kept no file), read-only; [] with no book, no such table or no row."""
    if path is None or not Path(path).is_file():
        return []
    db = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True, timeout=5.0)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute("SELECT instance, extra FROM eq_rebalances WHERE decided_day = ? "
                                            "AND bars_sha IS NOT NULL ORDER BY rid", (day.isoformat(),))]
    except sqlite3.Error:
        return []
    finally:
        db.close()


def _column_series(days: Sequence[str], raw: np.ndarray, adj: np.ndarray) -> tuple[dict, dict]:
    """One column as E1's morning audit reads a symbol: ({day: (o, h, l, c, v)}, {day: (o, h, l, c)}), sessions with no
    bar left out."""
    rows, alls = raw.tolist(), adj.tolist()
    return ({d: tuple(r) for d, r in zip(days, rows) if not math.isnan(r[3])},
            {d: tuple(r) for d, r in zip(days, alls) if not math.isnan(r[3])})


def i6_check(root: str | Path, gateway: Any, day: dt.date, *, live: str | Path | None = None,
             panel: Panel | None = None, assets: Mapping[str, Any] | None = None,  # noqa: A002
             blank: Sequence[Sequence[Any]] = (), sleep: Callable[[float], None] = time.sleep,
             count: dict[str, int] | None = None) -> dict[str, Any]:
    """The nightly I6 of `day` (the module docstring): {"day", "store_sha", "fetch_sha", "equal", "source": "kept" |
    "fetch", "live": {instance: True | False | None}} (None: a decision that read bars and has no kept fetch to be
    held to: unread, never False) and, beside, "bytes_equal", "columns", "mismatch", "volume", "blanked", "late",
    "absent" and "why". `equal` is False only on a column that differs (part 1) or a live decision whose own columns
    differ (part 2). `live`: live.sqlite's path (opened read-only), None: no live decision. `panel`, `assets`: the
    arrays the job holds as the store's writer (None: read from `root`). `blank`: the audit's [(aid, day)] bars the
    store reads as missing; the same cells are blanked on the fetch side and counted. It never raises: what it could
    not do is its `why`, and `equal` is then None (never True)."""
    from ..equity import store as eq_store
    from ..xs import config as xs_config

    out: dict[str, Any] = {"day": day.isoformat(), "store_sha": None, "fetch_sha": None, "equal": None,
                           "bytes_equal": None, "source": None, "live": {}, "columns": 0, "mismatch": 0, "volume": 0,
                           "blanked": 0, "late": 0, "absent": 0, "why": None}
    try:
        panel = panel if panel is not None else load_panel(root)
        assets = _assets(root, assets)
        if panel is None or day not in panel.days:
            out["why"] = "the store does not hold the day"
            return out
        t = panel.days.index(day)
        first = t - (xs_config.DERIVE_SESSIONS - 1)
        if first < 0:
            out["why"] = "the store holds less than the decision's window before the day"
            return out
        days = panel.days[first:t + 1]
        isos = [d.isoformat() for d in days]
        col = {aid: k for k, aid in enumerate(panel.aids)}
        ref = [aid for aid in panel.aids if assets.get(str(aid), {}).get("ref")]
        members = [aid for aid in panel.aids if aid not in ref and panel.member[t, col[aid]]
                   and assets.get(str(aid), {}).get("masked") is None]
        order = ref + members
        symbols = [str(assets[str(a)]["symbol"]) if a in ref else _ticker_on(assets[str(a)], day) for a in order]
        cols = [col[a] for a in order]
        store_raw, store_adj = panel.raw[first:t + 1][:, cols], panel.adj[first:t + 1][:, cols]
        gone = {(int(a), str(d)[:10]) for a, d in blank}

        def blanked(raw: np.ndarray, adj: np.ndarray, names: Sequence[int]) -> int:
            hit = 0
            if not gone:
                return hit
            for k, aid in enumerate(names):
                for i, iso in enumerate(isos):
                    if (aid, iso) in gone and np.isfinite(raw[i, k, 3]):
                        raw[i, k, :] = np.nan
                        adj[i, k, :] = np.nan
                        hit += 1
            return hit

        kept = _kept(root, day)
        fetch_raw = fetch_adj = None
        if kept is not None:
            names, fetched = kept
            at = {s: k for k, s in enumerate(names)}
            same_days = [eq_store.from_ordinal(int(v)) for v in np.asarray(fetched.days).tolist()] == days
            if same_days and all(s in at for s in symbols):
                take = [at[s] for s in symbols]
                fetch_raw = np.array(np.asarray(fetched.raw, dtype=np.float64)[:, take], copy=True)
                fetch_adj = np.array(np.asarray(fetched.all, dtype=np.float64)[:, take], copy=True)
                out["source"] = "kept"
        if fetch_raw is None:
            grid = Grid(days, list(range(len(order))))
            spent = count if count is not None else {"calls": 0, "failed": 0}
            for at_ in range(0, len(symbols), BATCH):
                chunk = symbols[at_:at_ + BATCH]
                aid_of = {s: at_ + j for j, s in enumerate(chunk)}
                for adjustment in ("raw", "all"):
                    rows = fetch_asof(gateway, chunk, isos[0], isos[-1], adjustment=adjustment, asof=None,
                                      sleep=sleep, count=spent)
                    grid.place(rows, aid_of, adjustment)
            grid.align()
            fetch_raw, fetch_adj = grid.raw, grid.adj
            out["source"] = "fetch"
        out["blanked"] = blanked(fetch_raw, fetch_adj, order)
        held_raw, held_adj = store_raw, store_adj
        if out["source"] == "kept":
            # LATE: no bar of the day in the 16:20 fetch, one in the store. The decision read it as no bar (B13); the
            # column is held to the store on every session before the day.
            late = np.isfinite(store_raw[-1, :, 3]) & ~np.isfinite(fetch_raw[-1, :, 3])
            if bool(late.any()):
                held_raw, held_adj = np.array(store_raw, copy=True), np.array(store_adj, copy=True)
                held_raw[-1, late, :] = np.nan
                held_adj[-1, late, :] = np.nan
                out["late"] = int(late.sum())
        mismatch, volume = compare_bars(held_raw, held_adj, fetch_raw, fetch_adj)
        out.update(columns=len(order), mismatch=int(mismatch.sum()), volume=int(volume.sum()))
        equal = not bool(mismatch.any())
        # The two ctx shas (the reference NEEDS, one run key, one aid set), beside the bars' verdict.
        try:
            from ..xs import store as xs_store

            salt = xs_store.run_salt(xs_store.read_salt(root), f"i6|{day.isoformat()}")
            table = sorted(int(a) for a in assets)
            ids = np.asarray(xs_store.ids_for(members, salt, table=table), dtype=np.int32)
            by_id = np.argsort(ids, kind="stable")
            take = list(range(len(ref))) + [len(ref) + int(k) for k in by_id]
            elig0 = np.array([False] * len(ref) + [bool(panel.tradable[t, col[members[int(k)]]]) for k in by_id])
            common = {"day": day, "elig0": elig0, "ids": ids[by_id], "dither_key": xs_store.dither_key(salt),
                      "sector_perm": xs_store.sector_perm(salt)}
            out["store_sha"] = _ctx_sha(days, store_raw[:, take], store_adj[:, take], **common)
            out["fetch_sha"] = _ctx_sha(days, fetch_raw[:, take], fetch_adj[:, take], **common)
            out["bytes_equal"] = out["store_sha"] == out["fetch_sha"]
        except NotImplementedError:
            out["why"] = "the panel's ctx is not built: the bars' verdict alone"
        except Exception as exc:  # noqa: BLE001 - a ctx that cannot be built from the day's bars is said, not raised
            out["why"] = f"the ctx could not be built: {type(exc).__name__}: {str(exc)[:160]}"
        # Each live decision of the day that read bars: THE COLUMNS IT HAD, from the store against the kept file, by
        # E1's own verdict. A decision with no kept fetch is unread (None): it cannot be shown equal, and it is not
        # shown to differ.
        decided = _live_rows(live, day)
        if decided:
            from ..equity.live import _bars_verdict

            aid_of = dict(zip(symbols, order))
            names, fetched = kept if kept is not None else ((), None)
            readable = fetched is not None and \
                [eq_store.from_ordinal(int(v)) for v in np.asarray(fetched.days).tolist()] == days
            at = {s: k for k, s in enumerate(names)}
            extras = []
            for row in decided:
                try:
                    extras.append({str(s) for s in json.loads(row.get("extra") or "[]")})
                except (TypeError, ValueError):
                    extras.append(set())
            others = set().union(*extras)
            known = set(symbols)
            # ABSENT, once for the day: a member of the store's day the 16:20 columns lacked, or a column of theirs
            # the store holds no asset for.
            absent = {s for s in symbols if s not in at} if readable else set()
            verdicts: dict[str, bool | None] = {}
            for row, extra in zip(decided, extras):
                instance = str(row.get("instance"))
                if not readable:
                    verdicts.setdefault(instance, None)
                    continue
                good = True
                for symbol in names:
                    if symbol not in known and symbol not in extra and symbol in others:
                        continue  # another instance's held name: no column of this decision
                    aid = aid_of.get(symbol, _aid_of(assets, symbol, day))
                    if aid is None or aid not in col:
                        absent.add(symbol)
                        continue
                    k_raw = np.array(np.asarray(fetched.raw, dtype=np.float64)[:, [at[symbol]]], copy=True)
                    k_adj = np.array(np.asarray(fetched.all, dtype=np.float64)[:, [at[symbol]]], copy=True)
                    hit = blanked(k_raw, k_adj, [aid])
                    out["blanked"] += hit if symbol in extra else 0
                    old_raw, old_all = _column_series(isos, k_raw[:, 0], k_adj[:, 0])
                    new_raw, new_all = _column_series(isos, np.asarray(panel.raw[first:t + 1, col[aid]]),
                                                      np.asarray(panel.adj[first:t + 1, col[aid]]))
                    if isos[-1] not in old_raw and isos[-1] in new_raw:
                        # LATE (as `xs.book.same` reads it): the decision read no bar of the day for it.
                        new_raw.pop(isos[-1])
                        new_all.pop(isos[-1], None)
                        out["late"] += 1 if symbol not in known else 0   # (a member's is counted in part 1)
                    if not old_raw:
                        if new_raw:
                            good = False
                            break
                        continue  # no bar in either reading: nothing differs
                    if _bars_verdict(old_raw, old_all, {d: dict(zip(RAW_FIELDS, v)) for d, v in new_raw.items()},
                                     {d: dict(zip(ADJ_FIELDS, v)) for d, v in new_all.items()},
                                     max(old_raw)) == "mismatch":
                        good = False
                        break
                verdicts[instance] = bool(good) and verdicts.get(instance, True) is not False
            out["live"] = verdicts
            out["absent"] = len(absent)
        out["equal"] = bool(equal and all(v is not False for v in out["live"].values()))
    except NotImplementedError as exc:
        out["equal"], out["why"] = None, f"not built: {str(exc)[:160]}"
    except Exception as exc:  # noqa: BLE001 - the I6 never fails the job: what it could not do is said
        out["equal"], out["why"] = None, f"{type(exc).__name__}: {str(exc)[:200]}"
    return out


# ------------------------------------------------------------------------------------------------- the job
def coverage_floor(root: str | Path) -> float:
    """D19's coverage floor: THE LANE'S OWN SETTING `elane.panel.coverage_min` (policy.json, the box's swarm.json over
    it), held to its bound by `league.swarm.elane_xs.cfg` (tighten only: [0.97, 1.0]; a value outside reads as the
    default). The setting was in the lane's block, its bounds and its documents and was read by NOTHING: this job read
    `<state>/ops.json` `equity_panel.coverage_min`, so a captain who tightened the lane's key changed no verdict and
    nothing said so. A setting that cannot be read is the default."""
    try:
        from ..swarm import elane_xs
        from ..swarm import settings as swarm_settings

        return float(elane_xs.cfg(swarm_settings.load(Path(root)))["coverage_min"])
    except Exception:  # noqa: BLE001 - unread: the default (the lower bound: never looser than the rule's own)
        return 0.97


def _fact(manifest: Mapping[str, Any] | None, key: str) -> Any:
    return (manifest or {}).get(key)


def live_panels(path: str | Path) -> int:
    """The live panel instances of live.sqlite (`eq_instances` of kind "panel" not retired), read-only; 0 with no
    book, no such column (a book from before the panel's patch) or no row."""
    if not Path(path).is_file():
        return 0
    db = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True, timeout=5.0)
    try:
        return int(db.execute("SELECT COUNT(*) FROM eq_instances WHERE kind = 'panel' AND retired_at IS NULL")
                   .fetchone()[0])
    except sqlite3.Error:
        return 0
    finally:
        db.close()


def _fail(ctx: Any, root: Path, error: str, **more: Any) -> dict[str, Any]:
    """A failed receipt, and its UTC day kept beside the store: the job failing two days running is an alarm
    (critical while a panel instance is live: its decisions' bars are no longer being held to the store)."""
    days: list[str] = []
    try:
        held = json.loads((root / FAILURES_FILE).read_text(encoding="utf-8"))
        days = [str(d) for d in held.get("days") or ()]
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    today = U._stamp(ctx.now())[:10]
    days = sorted(set(days) | {today})
    try:
        U._write(root / FAILURES_FILE, U._json_bytes({"days": days}))
    except OSError:
        pass
    if len(days) >= 2:
        ctx.alert("critical" if live_panels(Path(ctx.root) / LIVE_DB) else "warning",
                  f"equity_panel: failed on {len(days)} days running; the last good store stays")
    return U._failed(error, **more)


def _rows_of(days: Sequence[dt.date], raw: np.ndarray, fields: Sequence[str]) -> list[dict[str, Any]]:
    return [{"t": d.isoformat(), **dict(zip(fields, row))} for d, row in zip(days, raw.tolist())
            if not math.isnan(row[3])]


def ref_audit(days: Sequence[dt.date], early: Sequence[bool], raw: np.ndarray, adj: np.ndarray) -> list[str]:
    """E1's own audit (`league.ops.equity_data.audit`) of the REF columns, a span at a time (nothing is read across
    the 2020 gap): the names of the checks that failed, each with its span ([] when every span passes)."""
    from ..xs import config as xs_config
    from . import equity_data

    failed: list[str] = []
    index = {d: i for i, d in enumerate(days)}
    for first, last in _span_windows(days):
        lo, hi = index[first], index[last] + 1
        calendar = [(days[i], bool(early[i])) for i in range(lo, hi)]
        raw_rows = {s: _rows_of(days[lo:hi], raw[lo:hi, k], RAW_FIELDS) for k, s in enumerate(xs_config.REF)}
        adj_rows = {s: _rows_of(days[lo:hi], adj[lo:hi, k], ADJ_FIELDS) for k, s in enumerate(xs_config.REF)}
        result = equity_data.audit(calendar, raw_rows, adj_rows)
        failed.extend(f"{name} ({first.year}-{last.year})" for name, check in result["checks"].items()
                      if not check["passed"])
    return failed


def _stock_universe() -> set[str]:
    from ..constitution import CONSTITUTION

    block = CONSTITUTION.get("equity_money") if isinstance(CONSTITUTION, Mapping) else None
    named = (block or {}).get("universe") if isinstance(block, Mapping) else None
    return {str(s) for s in (named or {}).get("stock") or ()} if isinstance(named, Mapping) else set()


def tradable_rows(days: Sequence[dt.date], aids: Sequence[int], assets: Mapping[str, Any],  # noqa: A002
                  before: Panel | None, *, live_from: dt.date | None, stock: set[str], n_ref: int) -> np.ndarray:
    """D4's `tradable` (n_days, n_assets): True for every member column on every session before `live_from` (None:
    on every session); from it on, whether the asset's symbol was in the constitution's `equity_money.universe.stock`
    in force that day: ONE ROW A SESSION IS APPENDED AND NONE IS REWRITTEN (a row the store already has is kept as
    it is; a new row, and a column the store did not have, read tonight's list). REF columns are False."""
    out = np.ones((len(days), len(aids)), dtype=bool)
    out[:, :n_ref] = False
    listed = np.array([str(assets[str(a)].get("symbol")) in stock for a in aids], dtype=bool)
    if live_from is not None:
        late = np.array([d >= live_from for d in days], dtype=bool)
        out[np.ix_(late, np.arange(n_ref, len(aids)))] = listed[None, n_ref:]
    if before is not None:
        rows = [i for i, d in enumerate(days) if i < len(before.days) and before.days[i] == d]
        old_col = {aid: k for k, aid in enumerate(before.aids)}
        cols = [k for k, a in enumerate(aids) if a in old_col]
        if rows and cols:
            out[np.ix_(rows, cols)] = before.tradable[np.ix_(rows, [old_col[aids[k]] for k in cols])]
    return out


def _run(ctx: Any, *, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """The job. Its first statements are the lane's switch (`equity_universe.lane_off`: with `elane.panel.mode` "off"
    nothing of E4 runs) and `league.xs.config.quiet(ctx.now(), WALL_S)`. {"ok": True, counts and verdicts} with the
    store written, {"status": "skipped", "why"}, or {"status": "failed", "error"} with nothing written and the last
    good store in place. `sleep`: the tests'."""
    why = U.lane_off(ctx.root) or U.quiet_now(ctx.now(), WALL_S)
    if why is not None:
        return {"status": "skipped", "why": why}
    from ..xs import config as xs_config
    from ..xs import store as xs_store
    from .equity_data import last_closed

    now = ctx.now()
    root = Path(ctx.root) / U.STORE_DIR
    try:
        universe = U.read_universe(root)
    except ValueError as exc:
        return U._failed(f"the universe cannot be read: {exc}")
    if universe is None:
        return {"status": "skipped", "why": "there is no universe yet: the membership job writes it first"}
    assets = universe["assets"]
    try:
        last = last_closed(now)
    except Exception as exc:  # noqa: BLE001 - no calendar, no run
        return _fail(ctx, root, f"the last closed session cannot be read: {type(exc).__name__}: {str(exc)[:160]}")
    try:
        before = load_panel(root)
    except ValueError as exc:  # a store that does not match its manifest is not grown: a whole refetch
        before = None
        ctx.alert("warning", f"equity_panel: the store on disk cannot be read ({str(exc)[:120]}): a whole refetch")
    if before is not None:
        before.release()   # its manifest, days, aids and masks are what this function reads; `full` and
        #                    `incremental` map the bars themselves, one reader at a time (`Panel.release`)
    old = before.manifest if before is not None else {}
    audit_before = old.get("audit") if isinstance(old.get("audit"), Mapping) else {}
    reads = dict(audit_before.get("reads") or {})
    blank = [list(b) for b in audit_before.get("blank") or () if isinstance(b, (list, tuple)) and len(b) == 2]
    full_at = U._epoch(str(_fact(old, "full_at")) + "T00:00:00+00:00") if _fact(old, "full_at") else None
    want_full = before is None or full_at is None or now - full_at >= FULL_EVERY_DAYS * 86400
    full_failed = None
    built = None
    try:
        if want_full:
            try:
                built = full(root, U.Paced(ctx.gateway, sleep), last, assets=assets, sleep=sleep)
            except Exception as exc:  # noqa: BLE001 - a whole refetch that fails writes nothing new: the incremental
                full_failed = f"{type(exc).__name__}: {str(exc)[:160]}"
                if before is None:
                    return _fail(ctx, root, f"the first whole fetch failed ({full_failed}): nothing written")
        if built is None:
            try:
                built = incremental(root, U.Paced(ctx.gateway, sleep), last, assets=assets, blank=blank,
                                    sleep=sleep)
            except ValueError as exc:
                if full_failed is not None:
                    return _fail(ctx, root, f"the whole refetch failed ({full_failed}) and the store cannot be grown ({exc}): "
                                     "nothing written")
                # (a store the calendar outgrew)
                built = full(root, U.Paced(ctx.gateway, sleep), last, assets=assets, sleep=sleep)
    except Exception as exc:  # noqa: BLE001 - a gateway error writes nothing: a failed receipt, retried in its grace
        return _fail(ctx, root, f"the bars could not be fetched: {type(exc).__name__}: {str(exc)[:200]}: nothing written, "
                         "the last good store stays")
    days, early, aids, raw, adj = built["days"], built["early"], built["aids"], built["raw"], built["adj"]
    n_ref = len(xs_config.REF)
    col = {aid: k for k, aid in enumerate(aids)}
    count = {"calls": int(built["calls"]), "failed": 0}
    failed_ref = ref_audit(days, early, raw, adj)
    if failed_ref:
        return _fail(ctx, root, f"a REF column fails E1's audit ({', '.join(failed_ref)}): nothing written, the last good "
                         "store stays", mode=built["mode"])
    member = U.membership(assets, days)
    # D19, in its order: what is no bar, what a second read contradicts, what a spell's series is, the coverage.
    has = np.isfinite(raw[:, :, 3])
    insane = has & ~(sane_bars(raw) & sane_bars(adj))
    insane[:, :n_ref] = False
    bars_of = has.sum(axis=0)
    wild = (insane.sum(axis=0) > INSANE_SHARE * np.maximum(bars_of, 1)) & (bars_of > 0)
    single = insane & ~wild[None, :]
    blanks = {(int(a), str(d)[:10]) for a, d in blank}
    for i, k in zip(*np.nonzero(single)):
        blanks.add((aids[int(k)], days[int(i)].isoformat()))
    found = jumps(raw[:, n_ref:], adj[:, n_ref:], days)
    if built["mode"] == "full":
        reads = {key: value for key, value in reads.items() if value is not None}  # the unread are read again
    read_now = contradicted = pending = 0
    for i, k, prior in found["moves"]:
        aid = aids[n_ref + k]
        row = assets[str(aid)]
        asof = None if _open(row) else next((r.asof for r in requests(assets, days, only={aid})), None)
        for at in (i, prior):
            key = f"{aid}:{days[at].isoformat()}"
            if key not in reads:
                if read_now >= SECOND_READS_RUN:
                    pending += 1
                    continue
                read_now += 1
                reads[key] = second_read(U.Paced(ctx.gateway, sleep), str(row["symbol"]), days[at], asof=asof,
                                         daily=float(raw[at, n_ref + k, 3]), early=bool(early[at]), sleep=sleep,
                                         count=count)
            if reads[key] is False:
                blanks.add((aid, days[at].isoformat()))
    row_of = {d.isoformat(): i for i, d in enumerate(days)}
    for aid, iso in sorted(blanks):
        i, k = row_of.get(iso), col.get(aid)
        if i is not None and k is not None and np.isfinite(raw[i, k, 3]):
            raw[i, k, :] = np.nan
            adj[i, k, :] = np.nan
    contradicted = sum(1 for value in reads.values() if value is False)
    masks: dict[int, str | None] = {}
    for k in range(n_ref, len(aids)):
        aid = aids[k]
        mask = "insane" if bool(wild[k]) else None
        if mask is None:
            for spell in U._spells_of(assets[str(aid)]):
                mask = acceptance({"days": days, "raw": raw[:, k]}, spell)
                if mask is not None:
                    break
        masks[aid] = mask
    hidden = np.zeros(len(aids), dtype=bool)
    by_mask: dict[str, int] = {}
    for k in range(n_ref, len(aids)):
        mask = masks[aids[k]] or (U.VENUE_MASK if assets[str(aids[k])].get("masked") == U.VENUE_MASK else None)
        if mask is not None:
            hidden[k] = True
            by_mask[mask] = by_mask.get(mask, 0) + 1
    today = member[-1]
    current = int(today.sum())
    masked_now = int((today & hidden).sum())
    if current and masked_now > MASKED_MEMBERS_MAX * current:
        return _fail(ctx, root, f"{masked_now} of {current} current members are masked (over "
                         f"{int(MASKED_MEMBERS_MAX * 100)}%): nothing written, the last good store stays",
                         mode=built["mode"], masked=dict(sorted(by_mask.items())))
    floor = coverage_floor(ctx.root)
    block = coverage(member, raw, days, masked=hidden, floor=floor)
    with np.errstate(invalid="ignore"):
        zero_volume = int((member & has & ~valid_bars(raw) & (raw[:, :, 3] > 0)).sum())
    # tradable, live_from, the half-spreads
    stock = _stock_universe()
    live_from = U._day(_fact(old, "live_from"))
    unmasked_today = [aids[k] for k in range(n_ref, len(aids)) if today[k] and not hidden[k]]
    if live_from is None and unmasked_today:
        inside = sum(1 for aid in unmasked_today if str(assets[str(aid)].get("symbol")) in stock)
        if inside >= LIVE_FROM_SHARE * len(unmasked_today):
            live_from = last  # the first run that reads the grown constitution universe
    tradable = tradable_rows(days, aids, assets, before, live_from=live_from, stock=stock, n_ref=n_ref)
    hs = hs_table(root, aids)
    share = hs_share(root, member[:, n_ref:], days, aids[n_ref:], masked=hidden[n_ref:])
    revisions = int(built["revisions"])
    audit = {"jumps": len(found["moves"]), "second_read": len(reads), "contradicted": contradicted,
             "zero_volume": zero_volume, "masked": dict(sorted(by_mask.items())),
             "unexplained": len(found["unexplained"]), "insane_bars": int(single.sum()),
             "misaligned": int(built["misaligned"]), "dropped": int(built["dropped"]), "pending": pending,
             "reads": dict(sorted(reads.items())), "blank": [[a, d] for a, d in sorted(blanks)],
             "mode": built["mode"], "refetched": int(built["refetched"]), "full_failed": full_failed,
             "full_failures": (int(audit_before.get("full_failures") or 0) + 1) if full_failed else 0}
    panel = Panel(days=days, early=np.array(early, dtype=bool), aids=aids, raw=raw, adj=adj, member=member,
                  tradable=tradable, hs=hs, manifest={})
    i6 = i6_check(root, U.Paced(ctx.gateway, sleep), last, live=Path(ctx.root) / LIVE_DB, panel=panel, assets=assets,
                  blank=sorted(blanks), sleep=sleep, count=count)
    day_of_full = last if built["mode"] == "full" else U._day(_fact(old, "full_at"))
    try:
        manifest = xs_store.write_panel(root, days=days, early=early, aids=aids, raw=raw, adj=adj, member=member,
                                        tradable=tradable, hs=hs, fetched_through=last, vintage=built["vintage"],
                                        audit=audit, masked=hidden.tolist(), coverage=block, full_at=day_of_full,
                                        revisions=revisions, hs_share=share, live_from=live_from, i6=i6)
    except NotImplementedError:
        return {"status": "skipped", "why": "league.xs.store.write_panel is not built (package C's C0)"}
    except Exception as exc:  # noqa: BLE001 - the writer refuses before its first byte, and its manifest is last
        return _fail(ctx, root, f"the store could not be written: {type(exc).__name__}: {str(exc)[:200]}",
                         mode=built["mode"])
    (root / FAILURES_FILE).unlink(missing_ok=True)
    remasked = True
    try:
        U.remask(root, masks, day=last)
    except Exception as exc:  # noqa: BLE001 - the store is written; the marks are the next run's to repair
        remasked = False
        ctx.alert("warning", f"equity_panel: the universe's marks could not be written ({type(exc).__name__}); the "
                             "next run writes them")
    verdict = block["verdict"]
    below = [y for y, row in block["coverage"].items() if row["share"] is not None and row["share"] < floor]
    if verdict != "ok":
        ctx.alert("critical" if verdict == "insufficient" else "warning",
                  f"equity_panel: the coverage verdict is {verdict} (years under {floor:.2f}: {', '.join(below)}): "
                  "the owner's paid-data question")
    if i6["equal"] is False:
        ctx.alert("critical", f"equity_panel: the nightly I6 is False ({i6['mismatch']} of {i6['columns']} columns "
                              f"differ from the {i6['source']} bars; live decisions equal: "
                              f"{sum(1 for v in i6['live'].values() if v)} of {len(i6['live'])}): mode reads at most "
                              "\"gate\" (a seated panel program opens nothing; its exits go on)")
    unread = sum(1 for v in i6["live"].values() if v is None)
    if i6.get("late") or i6.get("absent") or unread:
        ctx.alert("warning", f"equity_panel: the nightly I6 counted {i6.get('late') or 0} bars served after the 16:20 "
                             f"fetch, {i6.get('absent') or 0} columns one side lacked (a membership change learnt "
                             f"after the decision) and {unread} live decisions with no kept fetch to be held to "
                             "(notes: no price differs)")
    if revisions > REVISIONS_ALARM:
        ctx.alert("warning", f"equity_panel: {revisions} raw bars changed on a refetch (alarm above {REVISIONS_ALARM})")
    if audit["full_failures"] >= 2:
        ctx.alert("warning", f"equity_panel: the whole refetch failed {audit['full_failures']} nights running")
    vanished = manifest.get("vanished") if isinstance(manifest, Mapping) else None
    return {"ok": True, "mode": built["mode"], "sessions": len(days), "assets": len(aids) - n_ref,
            "members": current, "fetched_through": last.isoformat(), "calls": count["calls"],
            "refetched": int(built["refetched"]), "appended": int(built["appended"]), "revisions": revisions,
            "verdict": verdict, "train_years_ok": block["train_years_ok"],
            "coverage": {y: (None if row["share"] is None else round(row["share"], 6))
                         for y, row in block["coverage"].items()},
            "masked": dict(sorted(by_mask.items())), "masked_members": masked_now,
            "audit": {k: audit[k] for k in ("jumps", "second_read", "contradicted", "zero_volume", "unexplained",
                                            "insane_bars", "misaligned", "dropped", "pending")},
            "vanished": len(vanished) if isinstance(vanished, list) else None,
            "hs_share": round(share, 6), "live_from": U._iso(live_from), "full_failed": bool(full_failed),
            "remasked": remasked,
            "i6": {k: i6[k] for k in ("equal", "bytes_equal", "source", "columns", "mismatch", "volume", "blanked")}
            | {"late": int(i6.get("late") or 0), "absent": int(i6.get("absent") or 0)}
            | {"live": len(i6["live"]), "live_equal": sum(1 for v in i6["live"].values() if v),
               "live_unread": sum(1 for v in i6["live"].values() if v is None), "why": i6["why"]}}



#: The job as the registry runs it: `_run` with the wall detector around it (`equity_universe.watched`).
run = U.watched("equity_panel", _run)

__all__ = ["BARS", "WALL_S", "TRIES", "BACKOFF_S", "INCREMENTAL_SESSIONS", "FULL_EVERY_DAYS", "ACCEPT_SHARE",
           "ACCEPT_FIRST", "REUSED_USD", "INSANE_SHARE", "SECOND_READ_GAP", "MASKED_MEMBERS_MAX", "REVISIONS_ALARM",
           "I6_NEEDS", "fetch_asof", "plan", "incremental", "full", "acceptance", "second_read", "coverage",
           "hs_table", "i6_check", "run", "BATCH", "PAGE_LIMIT", "MAX_PAGES", "LOOKBACK_DAYS", "KEEP_ENDED_DAYS",
           "MIN_SAMPLES", "JUMP_COLUMNS", "WHOLE_BATCH", "SECOND_READS_RUN", "LIVE_FROM_SHARE", "I6_FLOOR", "LIVE_DB", "SPREADS_FILE", "FAILURES_FILE", "live_panels", "Request",
           "requests", "Grid", "Panel", "load_panel", "ratios_equal", "valid_bars", "sane_bars", "jumps", "hs_share",
           "compare_bars", "ref_audit", "tradable_rows", "coverage_floor"]
