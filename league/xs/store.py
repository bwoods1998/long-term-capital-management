"""The panel store: the point-in-time S&P 500's bars and members on the House, and what a run is sent of them.

Owner: package C. C0 (merged first and alone) is `write_panel` with the layout below and the 2020 refusal, because
package A's jobs are built on it; `synth` writes its synthetic panels through the same function, so the layout is one.

LAYOUT under `<state>/equity-daily/` (E1's root; E1's `write_store` touches only VERSION, calendar.npz, bars/,
manifest.json and GATE). Numpy and JSON only; every file is written to a temporary name and renamed, each directory's
manifest LAST; files 600, directories 700; a reader verifies every file's sha256 against its manifest once a process
(`MissingData` on a mismatch). Nothing here is ever committed or sent off the House.

    universe/SALT                 32 random bytes, written once by package A (os.urandom), never rewritten, never in a
                                  request, a log, an event or a manifest (only its sha256's first 8 hex)
    universe/SOURCE.json          the pinned spell file's commit, sha256, rows, known_through, and the changes table's
                                  {revid, changes_applied, known_through, verdict "ok" | "unverified"}
    universe/spells.csv           ticker,start,end,source ("fja" | "wiki")
    universe/assets.json          {aid: {"spells": [[ticker, start, end | null, exit]], "symbol", "alpaca": {...} | null,
                                  "ref": bool, "renames": [...], "masked": null | "reused" | "no_bars" |
                                  "not_fractionable" | "insane"}}; `exit` of an ended spell: "deal" | "other" |
                                  "unknown", null while open
    universe/tradable.json        {"as_of": day, "stock": [SYM...]}: the 36-month union (scripts/gen_universe.py's input)
    universe/UNIVERSE_MANIFEST.json {"version": "xs-universe-v1", "sha256": {file: sha}, "audit", "exits", "wiki_reach"}
    probe.json                    scripts/panel_probe.py's receipt (step -1): counts only
    panel/VERSION                 `league.xs.XS_STORE_VERSION`
    panel/days.npy                int32 (n_days,): the sessions of `config.SPANS`, oldest first;  panel/early.npy bool
    panel/aids.npy                int32 (n_assets,): REF aids 1..12 first, then members ascending (from 100)
    panel/raw.npy                 float64 (n_days, n_assets, 5): o h l c v, adjustment=raw, NaN where no bar
    panel/adj.npy                 float64 (n_days, n_assets, 4): o h l c, adjustment=all, ONE fetch's series an asset
    panel/member.npy              bool (n_days, n_assets);  panel/tradable.npy  bool (n_days, n_assets)
    panel/hs.npy                  float64 (n_assets, 2): the half-spread fraction at the open and at the close
    panel/PANEL_MANIFEST.json     {"version", "fetched_through", "full_at", "sha256": {file: sha}, "vintage": {aid: day},
                                  "coverage": {year: {"member_days", "with_bar", "share"}}, "train_years_ok": [...],
                                  "verdict": "ok" | "low_coverage" | "insufficient", "vanished": [aid...], "audit",
                                  "i6", "revisions", "hs_share", "live_from": day | null, and the counts "days",
                                  "assets", "first" (the store's first session)}
    spreads.json, neff.json, french/   package B's (league/ops/equity_spreads.py, equity_neff.py, french.py)
    live-bars/<day>.npz           package H's: the 16:20 fetch a live panel decision of `day` read (5 sessions kept)
    xs-twins.json                 package J's marker: which live panel instance has its twin row (ids and days only)

THE CENTS (a binding fact of the vendor, found on real SIP bars after the designs): adjustment=all prices are served
rounded to the cent. So an as-of price, a split or a dividend read from the adj/raw ratio is exact only to that
rounding: every comparison of two such readings takes `config.rounding_bound` (league/xs's own copy of the helper E1
gained after this build's base, same name, same figures), never a fixed tolerance, and a live fetch's ctx equals a
later store's only within it, never byte for byte by assumption (the nightly I6 measures it; D7's dither is drawn on
the RAW price, which is the tape's own and exact).

WHAT A PROGRAM'S RUN IS SENT: a `PanelBars`, and nothing else of the store. It holds NO aid and NO symbol: the PARENT
computes the salted ids, puts the member columns in ascending id and keeps the aids (`Slice`); the child plans orders
by id and the parent names the symbols.

Evidence module (in the xs identity). Raises E1's `league.equity.store.StoreRefused` and `MissingData`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from . import XS_STORE_VERSION, config
from ..equity import config as _e1
from ..equity.store import MissingData, StoreRefused, as_date, from_ordinal, nyse_sessions, ordinal

PANEL_DIR = "panel"
UNIVERSE_DIR = "universe"
SALT_FILE = "SALT"
SALT_BYTES = 32
UNIVERSE_VERSION = "xs-universe-v1"
PANEL_FILES = ("days.npy", "early.npy", "aids.npy", "raw.npy", "adj.npy", "member.npy", "tradable.npy", "hs.npy")
VERSION_FILE = "VERSION"
PANEL_MANIFEST = "PANEL_MANIFEST.json"
UNIVERSE_MANIFEST = "UNIVERSE_MANIFEST.json"
VERDICTS = ("ok", "low_coverage", "insufficient")
MASKS = ("reused", "no_bars", "not_fractionable", "insane")
EXITS = ("deal", "other", "unknown")
#: D2. The REF aids (`config.REF`'s order: SPY is 1), and the first aid a member asset may take.
REF_AIDS = tuple(range(1, len(config.REF) + 1))
FIRST_MEMBER_AID = 100
#: D19. The coverage floor a year needs (the setting `elane.panel.coverage_min`'s default and lower bound), and the
#: years beside the Train years that the verdict "ok" and "low_coverage" both need at it: Validation's and the look's.
COVERAGE_MIN = 0.97
JUDGED_YEARS = (_e1.WINDOWS["validation"][0].year, _e1.LOOK_CAP.year)
#: A stored file is private to the House: files 600, directories 700.
FILE_MODE, DIR_MODE = 0o600, 0o700
_CHUNK = 1 << 20
#: The windows a panel slice may be asked for. "look" is ONE span: Validation's first session through
#: min(the store's last close, `league.equity.config.LOOK_CAP`) (the pre-registration's 4.1: the look's run starts flat
#: at Validation's first session and runs through the holdout); it and "forward" open only with E1's capability.
WINDOWS = ("train", "validation", "look", "forward")
_STUB = "league.xs.store is a Step 0 stub: package C builds it (league/xs/E4_INTERFACES.md)"


@dataclass(frozen=True)
class PanelBars:
    """What one run reads, pickled to the decider child. NO aid, NO symbol, NO date beyond the sessions' ordinals (which
    the engine needs and no program ever sees).

    `days` int32 (n,): the sessions' ordinals (`league.equity.store.ordinal`), oldest first: up to
    `config.DERIVE_SESSIONS` sessions of look-back, then the run's sessions. `early` bool (n,). `first`: the index of
    the run's first session. `raw` float64 (n, m, 5): o h l c v, NaN where no bar. `adj` float64 (n, m, 4): o h l c,
    adjustment=all. Columns: the `ref` (12) REF columns in `config.REF` order, then the member columns in ASCENDING id.
    `elig0` bool (n, m): what only the parent can know of eligibility: member on the session and on the next
    `config.MEMBER_AHEAD` (past the slice's last session, as at the last) AND tradable AND unmasked AND the class of
    the month AND, in a half run, the visible half; REF columns False. The bar, history and characteristic conditions
    are `ctx.derive`'s, read from the arrays. `ids` int32 (m - ref,): the member columns' salted ids, ascending: a
    column's id is READ here, never computed from its position. `exit` int8 (m,): how the column's spell ended (1 deal,
    0 other or unknown or still open): counted beside a result, never a price. `hs` float64 (m, 2): the half-spread
    fraction at the open and at the close. `sector_perm` int8 (11,): the run's salted relabelling of the sector codes.
    `dither_key` bytes: the run's dither key (the child draws; no program sees it). `window`: "train" | "validation" |
    "look" | "forward". `data_version`: 24 hex over the manifest's shas and the span."""

    days: np.ndarray
    early: np.ndarray
    first: int
    raw: np.ndarray
    adj: np.ndarray
    elig0: np.ndarray
    ref: int
    ids: np.ndarray
    exit: np.ndarray
    hs: np.ndarray
    sector_perm: np.ndarray
    dither_key: bytes
    window: str
    data_version: str

    @property
    def n(self) -> int:
        """The number of sessions the slice covers (look-back and run)."""
        return int(np.asarray(self.days).shape[0])


@dataclass(frozen=True)
class Slice:
    """A run's slice as the PARENT holds it: `bars` (what the child is sent), `aids` int32 (m,): the aid of every
    column in the bars' column order (REF first), and `run_key` (D8: `run_sha|window|first run day` in the Gym, the
    instance id live and for that instance's twin). Never pickled to a child, never in a result."""

    bars: PanelBars
    aids: np.ndarray
    run_key: str


class PanelStore:
    """Read-only access to the panel store under `root` (`<state>/equity-daily`). `gate`: an E1
    `league.equity.store.EquityGateCapability` minted by `mint_equity_gate_capability(root, reason)` on E1's `GATE`
    mark, or None (Train and Validation only): there is no second capability type."""

    def __init__(self, root: str | Path, *, gate: Any = None):
        raise NotImplementedError(_STUB)

    def manifest(self) -> dict[str, Any]:
        """panel/PANEL_MANIFEST.json as written (`write_panel`)."""
        raise NotImplementedError(_STUB)

    def verdict(self) -> str:
        """The coverage verdict (D19): one of `VERDICTS`."""
        raise NotImplementedError(_STUB)

    def train_years_ok(self) -> tuple[int, ...]:
        """The years of `config.TRAIN_YEARS` whose member-day coverage is at or above the coverage floor."""
        raise NotImplementedError(_STUB)

    @property
    def fetched_through(self) -> dt.date:
        """The last session the store's fetch covered (its last close)."""
        raise NotImplementedError(_STUB)

    def sessions(self, window: str) -> list[dt.date]:
        """The RUN sessions of `window` (one of `WINDOWS`): never a session of 2016, 2020 or 2021; a sealed window
        lists nothing without the capability (StoreRefused)."""
        raise NotImplementedError(_STUB)

    def bars(self, window: str, *, history: int, run_key: str, start: dt.date | None = None,
             end: dt.date | None = None, aids: Sequence[int] | None = None) -> Slice:
        """The slice of "validation", or with the capability "look" or "forward", cut to [start, end]. Its member
        columns are every asset that is a member on any of its sessions (run and look-back), so the column set never
        depends on the day asked; `aids`: build exactly these member columns instead (a twin, or an I6 check that must
        match a live day's columns). It carries `config.DERIVE_SESSIONS` sessions before its first run session where
        the store holds them. StoreRefused for a run session of 2016, 2020 or 2021 ("history only" / "the reserve")
        and for a sealed window without the capability."""
        raise NotImplementedError(_STUB)

    def train(self, start: dt.date, end: dt.date, *, history: int, run_key: str, half: int | None = None) -> Slice:
        """A Train slice: [start, end] inside ONE span of `config.TRAIN_SEGMENTS`, else StoreRefused (a whole segment
        for the floor's pools, a seen span for the Train bar, a hidden year for the out-of-fold run). `half` 0 | 1: the
        other half's members are invisible (D18: `elig0` False: not eligible, in no cell, no placebo candidate)."""
        raise NotImplementedError(_STUB)

    def data_version(self, days: Sequence[dt.date]) -> str:
        """24 hex over the manifest's shas and the span."""
        raise NotImplementedError(_STUB)


class Universe:
    """The point-in-time membership as the PARENT reads it (`<root>/universe/`): symbols and aids never leave it."""

    def __init__(self, root: str | Path):
        raise NotImplementedError(_STUB)

    @property
    def known_through(self) -> dt.date:
        """The last day the membership is known through (the spell file's, extended by the accepted change rows)."""
        raise NotImplementedError(_STUB)

    def members(self, day: dt.date) -> list[tuple[int, str]]:
        """(aid, symbol) of every member on `day` that is unmasked (the class-pair rule not applied)."""
        raise NotImplementedError(_STUB)

    def symbol(self, aid: int, day: dt.date) -> str:
        """The symbol `aid` traded under on `day` (KeyError when it had none)."""
        raise NotImplementedError(_STUB)

    def aid(self, symbol: str, day: dt.date) -> int:
        """The aid that traded under `symbol` on `day` (KeyError when none did)."""
        raise NotImplementedError(_STUB)

    def tradable(self, day: dt.date) -> set[str]:
        """The symbols of the constitution's `equity_money.universe.stock` in force on `day` (every member before
        `live_from`)."""
        raise NotImplementedError(_STUB)

    def stale_days(self, day: dt.date) -> int:
        """Calendar days from `known_through` to `day` (0 when it is not behind)."""
        raise NotImplementedError(_STUB)

    def table(self) -> np.ndarray:
        """Every aid of assets.json, ascending: the set `ids_for` settles a collision over."""
        raise NotImplementedError(_STUB)


def read_salt(root: str | Path) -> bytes:
    """The House salt (`<root>/universe/SALT`, `SALT_BYTES` bytes); MissingData when it is absent or another length."""
    raise NotImplementedError(_STUB)


def run_salt(salt: bytes, run_key: str) -> bytes:
    """D8: sha256(salt | run key)."""
    raise NotImplementedError(_STUB)


def ids_for(aids: Sequence[int], run_salt: bytes, *, table: Sequence[int]) -> np.ndarray:
    """D8: the salted `config.ID_BITS`-bit id of each aid: the first 31 bits of sha256(run_salt | b"|id|" | str(aid)).
    A COLLISION is settled over the whole asset `table` (every aid of assets.json, ascending), never over the aids
    asked: in ascending aid, an aid whose value a lower aid took takes the next 31 bits of the same digest. So an id
    once given never changes, whatever joins or leaves the index and whichever aids are asked together."""
    raise NotImplementedError(_STUB)


def dither_key(run_salt: bytes) -> bytes:
    """D7: sha256(run_salt | b"|dither|")."""
    raise NotImplementedError(_STUB)


def sector_perm(run_salt: bytes) -> np.ndarray:
    """D8: int8 (11,): the run's relabelling of the sector codes 0..10 (the rank of sha256(run_salt | b"|sector|" | j)
    over j)."""
    raise NotImplementedError(_STUB)


def half_of(salt: bytes, aid: int) -> int:
    """D18: sha256(salt | b"|half-1|" | str(aid))[0] & 1."""
    raise NotImplementedError(_STUB)


# --------------------------------------------------------------------------------------------------------- writing
def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, DIR_MODE)


def _atomic_bytes(path: Path, data: bytes) -> str:
    """Write `data` to a temporary name beside `path` (mode 600), rename it over `path`, and return its sha256."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, FILE_MODE)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_array(path: Path, array: np.ndarray) -> str:
    """Write `array` as an .npy file (the same bytes for the same array: no pickle, a fixed header) to a temporary
    name, rename it over `path`, and return the file's sha256. The array is streamed, never copied whole."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    try:
        with os.fdopen(fd, "wb") as handle:
            np.lib.format.write_array(handle, np.ascontiguousarray(array), version=(1, 0), allow_pickle=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, FILE_MODE)
        sha = _file_sha256(tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return sha


def valid_bars(raw: np.ndarray) -> np.ndarray:
    """D4's VALID BAR, bool over `raw`'s leading axes: a raw close above 0 with a raw volume above 0, both finite. The
    vendor serves a session without a trade as a flat bar of volume 0 carrying the last price: that is NO valid bar
    (a halted name is not eligible on the halt day, in the Gym and live alike). `raw`: (..., 5) o h l c v."""
    raw = np.asarray(raw, dtype=np.float64)
    close, volume = raw[..., 3], raw[..., 4]
    with np.errstate(invalid="ignore"):
        return np.isfinite(close) & np.isfinite(volume) & (close > 0) & (volume > 0)


def coverage(member: np.ndarray, raw: np.ndarray, days: Sequence[dt.date], *, masked: Sequence[bool] | None = None,
             floor: float = COVERAGE_MIN) -> dict[str, Any]:
    """D19: {"coverage": {year: {"member_days", "with_bar", "share"}}, "train_years_ok": [...], "verdict"}.

    coverage[y] = the member-days of year y with a valid bar (`valid_bars`) of an unmasked asset / the member-days of
    y, for every year the days hold (share None for a year with no member-day). `train_years_ok`: the years of
    `config.TRAIN_YEARS` at or above `floor`. THE VERDICT: "ok" when every Train year and both `JUDGED_YEARS` are at
    or above it; "low_coverage" when at least all but one of the Train years and both judged years are; else
    "insufficient" (a year the store does not hold is not at the floor: fail closed). `masked`: bool per asset (a
    masked asset's member-days count below the line, never above it)."""
    member = np.asarray(member, dtype=bool)
    valid = valid_bars(raw)
    if member.shape != valid.shape or member.shape[0] != len(days):
        raise ValueError("coverage: member, raw and days do not agree on their shapes")
    floor = float(floor)
    if not COVERAGE_MIN <= floor <= 1.0:
        raise ValueError(f"the coverage floor is {COVERAGE_MIN} to 1.0 (tighten only), not {floor!r}")
    if masked is not None:
        hidden = np.asarray(masked, dtype=bool)
        if hidden.shape != (member.shape[1],):
            raise ValueError("coverage: masked is one bool an asset")
        valid = valid & ~hidden[None, :]
    years = np.array([as_date(d).year for d in days], dtype=np.int64)
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
    ok = [y for y in config.TRAIN_YEARS if share.get(y, -1.0) >= floor]
    judged = all(share.get(y, -1.0) >= floor for y in JUDGED_YEARS)
    if judged and len(ok) == len(config.TRAIN_YEARS):
        verdict = "ok"
    elif judged and len(ok) >= len(config.TRAIN_YEARS) - 1:
        verdict = "low_coverage"
    else:
        verdict = "insufficient"
    return {"coverage": table, "train_years_ok": ok, "verdict": verdict}


_d19 = coverage     # `write_panel` takes a keyword of the same name


def _vanished(aids: np.ndarray, member: np.ndarray, valid: np.ndarray) -> list[int]:
    """The aids whose bars END while they are still members: at least `config.VANISH_SESSIONS` member sessions after
    their last valid bar (D12's vanish rule would fire on a lot of them). An asset with no valid bar at all is not
    one (it is masked "no_bars", never held)."""
    out = []
    for col in range(len(config.REF), aids.shape[0]):
        hits = np.flatnonzero(valid[:, col])
        if hits.size and int(member[hits[-1] + 1:, col].sum()) >= config.VANISH_SESSIONS:
            out.append(int(aids[col]))
    return out


def _iso(value: Any, name: str) -> str | None:
    if value is None:
        return None
    try:
        return as_date(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"{name} is a day or None, not {value!r}") from None


def write_panel(root: str | Path, *, days: Sequence[dt.date], early: Sequence[bool], aids: Sequence[int],
                raw: np.ndarray, adj: np.ndarray, member: np.ndarray, tradable: np.ndarray, hs: np.ndarray,
                fetched_through: dt.date, vintage: Mapping[int, dt.date], audit: Mapping[str, Any],
                masked: Sequence[bool] | None = None, coverage: Mapping[str, Any] | None = None,
                vanished: Sequence[int] | None = None, full_at: Any = None, revisions: int = 0,
                hs_share: float | None = None, live_from: Any = None,
                i6: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """C0. Write the panel directory under `root` atomically (the layout above, PANEL_MANIFEST.json last) and return
    its manifest. Package A's job and `synth` both write through it. ValueError on arrays that do not agree on their
    shapes, days not ascending, REF aids not first, or A 2020 DAY ("2020 is never in the panel store").

    `days`: EVERY NYSE session from the first to the last, 2020's left out, oldest first (a ctx reads look-back by
    row, so a store with a session missing would shift every window: refused), each inside a span of `config.SPANS`;
    `early` is the calendar's own flag for each. `aids`: `REF_AIDS` first, then the member aids strictly ascending
    from `FIRST_MEMBER_AID`. `raw` (n_days, n_assets, 5) o h l c v and `adj` (n_days, n_assets, 4) o h l c: float64,
    NaN where no bar, never infinite. `member`, `tradable`: bool (n_days, n_assets); a REF column is never a member.
    `hs` (n_assets, 2): finite fractions in [0, 1). `fetched_through`: the fetch's day (no session lies between the
    last row and it). `vintage`: {aid: the day its adj series was fetched}. `audit`: the job's audit block, kept as it
    is.

    THE MANIFEST'S OTHER FACTS (keywords, each with a safe default so a manifest is never without its verdict):
    `coverage`: D19's block as `coverage()` returns it (package A hands its own, at the setting's floor); None: it is
    computed here at `COVERAGE_MIN`, with `masked` (bool an asset; None: no asset is). `vanished`: the aids whose bars
    end while they are members (None: computed, `_vanished`). `full_at`: the day of the last whole refetch.
    `revisions`: the raw rows a refetch changed. `hs_share`: the share of today's eligible names with enough spread
    samples at both fill points (None: unknown, which every reader takes as below any bound). `live_from`: the first
    session the universe deploy was in force (None until then). `i6`: the nightly I6's block (None before the first)."""
    root = Path(root)
    dates = [as_date(d) for d in days]
    n = len(dates)
    if not n:
        raise ValueError("a panel holds at least one session")
    reserve = [d for d in dates if d.year in config.RESERVE_YEARS]
    if reserve:
        raise ValueError(f"{reserve[0].year} is never in the panel store (the reserve): {reserve[0]} refused")
    if any(b <= a for a, b in zip(dates, dates[1:])):
        raise ValueError("the panel's sessions are strictly increasing")
    for day in (dates[0], dates[-1]):
        if not any(first <= day and (last is None or day <= last) for _, first, last in config.SPANS):
            raise ValueError(f"{day} is outside the panel's spans ({', '.join(name for name, _, _ in config.SPANS)})")
    calendar = [(d, e) for d, e in nyse_sessions(dates[0], dates[-1]) if d.year not in config.RESERVE_YEARS]
    if [d for d, _ in calendar] != dates:
        odd = sorted(set(dates) ^ {d for d, _ in calendar})
        raise ValueError(f"the panel's days are every session from {dates[0]} to {dates[-1]} (the reserve left out); "
                         f"{odd[0]} is {'no session' if odd[0] in set(dates) else 'missing'}")
    flags = np.asarray(early, dtype=bool)
    if flags.shape != (n,) or flags.tolist() != [bool(e) for _, e in calendar]:
        raise ValueError("early is the calendar's own half-day flag for each session")
    through = as_date(fetched_through)
    if through < dates[-1] or nyse_sessions(dates[-1] + dt.timedelta(days=1), through):
        raise ValueError(f"fetched_through ({through}) is the day of the panel's last session ({dates[-1]}), or a "
                         "closed day after it")
    columns = np.asarray(aids)
    if columns.ndim != 1 or columns.size < len(REF_AIDS) or not np.issubdtype(columns.dtype, np.integer):
        raise ValueError("aids is one whole number a column: the REF aids first")
    columns = columns.astype(np.int64)
    m, ref = int(columns.shape[0]), len(REF_AIDS)
    if tuple(columns[:ref].tolist()) != REF_AIDS:
        raise ValueError(f"the REF aids {REF_AIDS[0]}..{REF_AIDS[-1]} come first, in config.REF's order")
    members = columns[ref:]
    if members.size and (int(members[0]) < FIRST_MEMBER_AID or bool(np.any(np.diff(members) <= 0))):
        raise ValueError(f"the member aids are strictly ascending from {FIRST_MEMBER_AID}")
    if members.size and int(members[-1]) > np.iinfo(np.int32).max:
        raise ValueError("an aid is an int32")
    raw_a, adj_a = np.asarray(raw, dtype=np.float64), np.asarray(adj, dtype=np.float64)
    member_a, tradable_a = np.asarray(member), np.asarray(tradable)
    hs_a = np.asarray(hs, dtype=np.float64)
    for name, array, shape in (("raw", raw_a, (n, m, 5)), ("adj", adj_a, (n, m, 4)), ("member", member_a, (n, m)),
                               ("tradable", tradable_a, (n, m)), ("hs", hs_a, (m, 2))):
        if array.shape != shape:
            raise ValueError(f"{name} has the shape {array.shape}; the days and aids make it {shape}")
    for name, array in (("member", member_a), ("tradable", tradable_a)):
        if array.dtype != np.bool_:
            raise ValueError(f"{name} is a bool array")
    if bool(np.isinf(raw_a).any()) or bool(np.isinf(adj_a).any()):
        raise ValueError("a price or a volume is a finite number, or NaN where there is no bar")
    if bool(member_a[:, :ref].any()):
        raise ValueError("a REF column is never a member")
    if not bool(np.all(np.isfinite(hs_a) & (hs_a >= 0) & (hs_a < 1))):
        raise ValueError("a half-spread is a finite fraction in [0, 1)")
    known = set(columns.tolist())
    vintages: dict[str, str] = {}
    for aid, day in dict(vintage).items():
        if isinstance(aid, bool) or int(aid) not in known:
            raise ValueError(f"vintage names the aid {aid!r}, which the panel does not hold")
        vintages[str(int(aid))] = _iso(day, "a vintage")  # type: ignore[assignment]
    hidden = None
    if masked is not None:
        hidden = np.asarray(masked, dtype=bool)
        if hidden.shape != (m,):
            raise ValueError("masked is one bool a column")
    if coverage is None:
        block = _d19(member_a, raw_a, dates, masked=hidden)
    else:
        block = json.loads(json.dumps(dict(coverage), default=str))
        if block.get("verdict") not in VERDICTS or not isinstance(block.get("coverage"), dict) or \
                not isinstance(block.get("train_years_ok"), list):
            raise ValueError(f"coverage is D19's block: coverage, train_years_ok and a verdict of {', '.join(VERDICTS)}")
    gone = _vanished(columns, member_a, valid_bars(raw_a)) if vanished is None else sorted(int(a) for a in vanished)
    if set(gone) - known:
        raise ValueError("vanished names an aid the panel does not hold")
    if isinstance(revisions, bool) or int(revisions) < 0:
        raise ValueError("revisions is a count")
    if hs_share is not None and not (math.isfinite(float(hs_share)) and 0.0 <= float(hs_share) <= 1.0):
        raise ValueError("hs_share is a share in [0, 1], or None")
    facts = {"full_at": _iso(full_at, "full_at"), "live_from": _iso(live_from, "live_from"),
             "audit": json.loads(json.dumps(dict(audit or {}), default=str)),
             "i6": None if i6 is None else json.loads(json.dumps(dict(i6), default=str))}

    # Everything is read and refused before the first byte is written.
    _private_dir(root)
    folder = root / PANEL_DIR
    _private_dir(folder)
    shas = {
        "days.npy": _atomic_array(folder / "days.npy", np.array([ordinal(d) for d in dates], dtype=np.int32)),
        "early.npy": _atomic_array(folder / "early.npy", flags),
        "aids.npy": _atomic_array(folder / "aids.npy", columns.astype(np.int32)),
        "raw.npy": _atomic_array(folder / "raw.npy", raw_a),
        "adj.npy": _atomic_array(folder / "adj.npy", adj_a),
        "member.npy": _atomic_array(folder / "member.npy", member_a),
        "tradable.npy": _atomic_array(folder / "tradable.npy", tradable_a),
        "hs.npy": _atomic_array(folder / "hs.npy", hs_a),
    }
    _atomic_bytes(folder / VERSION_FILE, (XS_STORE_VERSION + "\n").encode())
    manifest = {
        "version": XS_STORE_VERSION, "fetched_through": dates[-1].isoformat(), "full_at": facts["full_at"],
        "sha256": shas, "days": n, "assets": m, "first": dates[0].isoformat(), "vintage": vintages,
        "coverage": block["coverage"], "train_years_ok": [int(y) for y in block["train_years_ok"]],
        "verdict": block["verdict"], "vanished": gone, "audit": facts["audit"], "i6": facts["i6"],
        "revisions": int(revisions), "hs_share": None if hs_share is None else float(hs_share),
        "live_from": facts["live_from"],
    }
    _atomic_bytes(folder / PANEL_MANIFEST, json.dumps(manifest, sort_keys=True, indent=1).encode())
    return manifest


__all__ = ["PANEL_DIR", "UNIVERSE_DIR", "SALT_FILE", "SALT_BYTES", "UNIVERSE_VERSION", "PANEL_FILES", "VERSION_FILE",
           "PANEL_MANIFEST", "UNIVERSE_MANIFEST", "VERDICTS", "MASKS", "EXITS", "REF_AIDS", "FIRST_MEMBER_AID",
           "COVERAGE_MIN", "JUDGED_YEARS", "WINDOWS", "StoreRefused", "MissingData", "PanelBars", "Slice",
           "PanelStore", "Universe", "read_salt", "run_salt", "ids_for", "dither_key", "sector_perm", "half_of",
           "valid_bars", "coverage", "write_panel"]
