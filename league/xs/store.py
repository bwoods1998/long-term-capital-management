"""The panel store: the point-in-time S&P 500's bars and members on the House, and what a run is sent of them.

Owner: package C. C0 (merged first and alone) is `write_panel` with the layout below and the 2020 refusal, because
package A's jobs are built on it. STEP 0 STUB: the two dataclasses are the contract (they are pickled to the decider
child); every function and method raises NotImplementedError until C lands.

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
                                  "i6", "revisions", "hs_share", "live_from": day | null}
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

PANEL_DIR = "panel"
UNIVERSE_DIR = "universe"
SALT_FILE = "SALT"
SALT_BYTES = 32
UNIVERSE_VERSION = "xs-universe-v1"
PANEL_FILES = ("days.npy", "early.npy", "aids.npy", "raw.npy", "adj.npy", "member.npy", "tradable.npy", "hs.npy")
VERDICTS = ("ok", "low_coverage", "insufficient")
MASKS = ("reused", "no_bars", "not_fractionable", "insane")
EXITS = ("deal", "other", "unknown")
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


def write_panel(root: str | Path, *, days: Sequence[dt.date], early: Sequence[bool], aids: Sequence[int],
                raw: np.ndarray, adj: np.ndarray, member: np.ndarray, tradable: np.ndarray, hs: np.ndarray,
                fetched_through: dt.date, vintage: Mapping[int, dt.date], audit: Mapping[str, Any]) -> dict[str, Any]:
    """C0. Write the panel directory under `root` atomically (the layout above, PANEL_MANIFEST.json last) and return
    its manifest. Package A's job and `synth` both write through it. ValueError on arrays that do not agree on their
    shapes, days not ascending, REF aids not first, or A 2020 DAY ("2020 is never in the panel store")."""
    raise NotImplementedError(_STUB)


__all__ = ["PANEL_DIR", "UNIVERSE_DIR", "SALT_FILE", "SALT_BYTES", "UNIVERSE_VERSION", "PANEL_FILES", "VERDICTS",
           "MASKS", "EXITS", "WINDOWS", "PanelBars", "Slice", "PanelStore", "Universe", "read_salt",
           "run_salt", "ids_for", "dither_key", "sector_perm", "half_of", "write_panel"]
