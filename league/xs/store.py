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
rounding: every comparison of two such readings takes `config.rounding_bound` (E1's own helper, re-exported: one
bound for both lanes), never a fixed tolerance, and a live fetch's ctx equals a
later store's only within it, never byte for byte by assumption (the nightly I6 measures it). It is also why the
ctx's dither is drawn on the ADJUSTED price's own cent grid (league/xs/ctx.py): that is the grid a ratio of two
history prices keeps.

WHAT A PROGRAM'S RUN IS SENT: a `PanelBars`, and nothing else of the store. It holds NO aid and NO symbol: the PARENT
computes the salted ids, puts the member columns in ascending id and keeps the aids (`Slice`); the child plans orders
by id and the parent names the symbols.

Evidence module (in the xs identity). Raises E1's `league.equity.store.StoreRefused` and `MissingData`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import numpy as np

from . import XS_STORE_VERSION, config
from ..equity import config as _e1
from ..equity.store import (EquityGateCapability, MissingData, StoreRefused, as_date, from_ordinal, nyse_sessions,
                            ordinal)

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
#: The universe directory's files a manifest names (SALT is in none: only its sha256's first `SALT_MARK` hex).
UNIVERSE_FILES = ("assets.json", "spells.csv", "SOURCE.json", "tradable.json")
SALT_MARK = 8
_CHUNK = 1 << 20
#: (path, sha256, inode, size, mtime) of every large file this process has verified against a manifest.
_VERIFIED: set[tuple[str, str, int, int, int]] = set()
#: The windows a panel slice may be asked for. "look" is ONE span: Validation's first session through
#: min(the store's last close, `league.equity.config.LOOK_CAP`) (the pre-registration's 4.1: the look's run starts flat
#: at Validation's first session and runs through the holdout); it and "forward" open only with E1's capability.
WINDOWS = ("train", "validation", "look", "forward")
#: The windows that open only with E1's capability.
SEALED = ("look", "forward")


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


# --------------------------------------------------------------------------------------------------- verified reads
def _json_file(path: Path, what: str) -> Any:
    if not path.is_file():
        raise MissingData(f"the panel store has no {what} ({path.name})")
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise MissingData(f"the panel store's {what} is unreadable: {exc}") from None


def _verified_bytes(path: Path, sha: Any, what: str) -> bytes:
    """A small file's bytes, checked against its manifest's sha256 (MissingData on a mismatch: a store being rewritten
    under a reader refuses, never mixes days)."""
    if not path.is_file():
        raise MissingData(f"the panel store has no {what} ({path.name})")
    data = path.read_bytes()
    if not isinstance(sha, str) or hashlib.sha256(data).hexdigest() != sha:
        raise MissingData(f"the panel store's {what} does not match its manifest (the store is being rewritten, or "
                          "was changed by hand): refused rather than mixed")
    return data


def _verified_array(path: Path, sha: Any, what: str) -> np.ndarray:
    """A large array memory-mapped read-only, its FILE checked against the manifest's sha256 once a process and
    manifest (`_VERIFIED`; the file's identity is read again after the map opens, so a file renamed in between is
    refused). The live process reads a few rows of it and never holds the whole."""
    if not path.is_file():
        raise MissingData(f"the panel store has no {what} ({path.name})")
    mixed = MissingData(f"the panel store's {what} does not match its manifest (the store is being rewritten, or was "
                        "changed by hand): refused rather than mixed")
    if not isinstance(sha, str):
        raise mixed
    before = path.stat()
    key = (str(path.resolve()), sha, before.st_ino, before.st_size, before.st_mtime_ns)
    if key not in _VERIFIED and _file_sha256(path) != sha:
        raise mixed
    try:
        array = np.load(path, mmap_mode="r", allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise MissingData(f"the panel store's {what} is unreadable: {exc}") from None
    after = path.stat()
    if (after.st_ino, after.st_size, after.st_mtime_ns) != (before.st_ino, before.st_size, before.st_mtime_ns):
        raise mixed
    _VERIFIED.add(key)
    return array


def _small_array(path: Path, sha: Any, what: str) -> np.ndarray:
    try:
        return np.load(io.BytesIO(_verified_bytes(path, sha, what)), allow_pickle=False)
    except ValueError as exc:
        raise MissingData(f"the panel store's {what} is unreadable: {exc}") from None


def _frozen(array: np.ndarray) -> np.ndarray:
    array = np.ascontiguousarray(array)
    array.setflags(write=False)
    return array


def _sealed(day: dt.date) -> bool:
    """Whether `day` is one of E1's sealed days (the holdout and the forward days: `league.equity.config.SEALED`)."""
    for name in _e1.SEALED:
        first, last = _e1.WINDOWS[name]
        if first <= day and (last is None or day <= last):
            return True
    return False


# ------------------------------------------------------------------------------------------------------- the salt
def read_salt(root: str | Path) -> bytes:
    """The House salt (`<root>/universe/SALT`, `SALT_BYTES` bytes); MissingData when it is absent or another length."""
    path = Path(root) / UNIVERSE_DIR / SALT_FILE
    if not path.is_file():
        raise MissingData(f"the panel store has no salt ({UNIVERSE_DIR}/{SALT_FILE}): no slot id can be given")
    salt = path.read_bytes()
    if len(salt) != SALT_BYTES:
        raise MissingData(f"the panel store's salt is {len(salt)} bytes, not {SALT_BYTES}")
    return salt


def _salt(salt: Any, name: str = "the salt") -> bytes:
    if not isinstance(salt, (bytes, bytearray)) or len(salt) != SALT_BYTES:
        raise ValueError(f"{name} is {SALT_BYTES} bytes")
    return bytes(salt)


def run_salt(salt: bytes, run_key: str) -> bytes:
    """D8: sha256(salt | run key)."""
    if not isinstance(run_key, str) or not run_key:
        raise ValueError("a run key is a non-empty string")
    return hashlib.sha256(_salt(salt) + run_key.encode("utf-8")).digest()


def _id_candidates(run: bytes, aid: int) -> Iterator[int]:
    """The successive `config.ID_BITS`-bit values of one aid: the 4-byte windows of sha256(run_salt | b"|id|" | aid),
    then of that digest's own sha256, and on (a collision past the eighth window has never been met; the rule is
    total all the same)."""
    digest = hashlib.sha256(run + b"|id|" + str(int(aid)).encode()).digest()
    shift = 32 - config.ID_BITS
    while True:
        for at in range(0, len(digest), 4):
            yield int.from_bytes(digest[at:at + 4], "big") >> shift
        digest = hashlib.sha256(digest).digest()


def ids_for(aids: Sequence[int], run_salt: bytes, *, table: Sequence[int]) -> np.ndarray:
    """D8: the salted `config.ID_BITS`-bit id of each aid: the first 31 bits of sha256(run_salt | b"|id|" | str(aid)).
    A COLLISION is settled over the whole asset `table` (every aid of assets.json, ascending), never over the aids
    asked: in ascending aid, an aid whose value a lower aid took takes the next 31 bits of the same digest. So an id
    once given never changes, whatever joins or leaves the index and whichever aids are asked together. ValueError
    for an aid the table lacks."""
    run = _salt(run_salt, "a run salt")
    every = sorted({int(a) for a in np.asarray(table).reshape(-1).tolist()})
    wanted = [int(a) for a in np.asarray(aids).reshape(-1).tolist()]
    missing = sorted(set(wanted) - set(every))
    if missing:
        raise ValueError(f"the asset table lacks the aid {missing[0]}: an id is settled over the whole table")
    taken: set[int] = set()
    given: dict[int, int] = {}
    last = max(wanted, default=-1)
    for aid in every:
        if aid > last:
            break
        for value in _id_candidates(run, aid):
            if value not in taken:
                taken.add(value)
                given[aid] = value
                break
    return np.array([given[a] for a in wanted], dtype=np.int32)


def dither_key(run_salt: bytes) -> bytes:
    """D7: sha256(run_salt | b"|dither|")."""
    return hashlib.sha256(_salt(run_salt, "a run salt") + b"|dither|").digest()


def sector_perm(run_salt: bytes) -> np.ndarray:
    """D8: int8 (11,): the run's relabelling of the sector codes 0..10 (the rank of sha256(run_salt | b"|sector|" | j)
    over j): a program reads `sector_perm[j]` where the House computed sector j."""
    run = _salt(run_salt, "a run salt")
    digests = [hashlib.sha256(run + b"|sector|" + str(j).encode()).digest() for j in range(len(config.FUNDS))]
    perm = np.empty(len(digests), dtype=np.int8)
    for rank, j in enumerate(sorted(range(len(digests)), key=lambda k: digests[k])):
        perm[j] = rank
    return perm


def half_of(salt: bytes, aid: int) -> int:
    """D18: sha256(salt | b"|half-1|" | str(aid))[0] & 1."""
    return hashlib.sha256(_salt(salt) + b"|half-1|" + str(int(aid)).encode()).digest()[0] & 1


# --------------------------------------------------------------------------------------------------- the universe
@dataclass(frozen=True)
class _Asset:
    aid: int
    spells: tuple[tuple[str, dt.date, dt.date | None, str | None], ...]
    symbol: str
    ref: bool
    masked: str | None

    def spell(self, day: dt.date) -> tuple[str, dt.date, dt.date | None, str | None] | None:
        """D3: the spell with start <= day and (end is null or day < end)."""
        for row in self.spells:
            if row[1] <= day and (row[2] is None or day < row[2]):
                return row
        return None


def _assets(raw: Any) -> dict[int, _Asset]:
    """assets.json's object as `_Asset` rows; MissingData says what is malformed (a universe that cannot be read is
    no universe)."""
    if not isinstance(raw, Mapping) or not raw:
        raise MissingData("the universe's assets.json is not an object of assets")
    out: dict[int, _Asset] = {}
    try:
        for key, row in raw.items():
            aid = int(key)
            spells = []
            for spell in row.get("spells") or ():
                ticker, start, end = str(spell[0]).strip().upper(), as_date(spell[1]), spell[2]
                how = spell[3] if len(spell) > 3 else None
                spells.append((ticker, start, None if end is None else as_date(end), None if how is None else str(how)))
            spells.sort(key=lambda r: r[1])
            ref = bool(row.get("ref")) or aid in REF_AIDS
            symbol = str(row.get("symbol") or (spells[-1][0] if spells else "")).strip().upper()
            masked = row.get("masked")
            out[aid] = _Asset(aid, tuple(spells), symbol, ref, None if masked is None else str(masked))
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
        raise MissingData(f"the universe's assets.json is malformed: {type(exc).__name__}: {exc}") from None
    for aid, symbol in zip(REF_AIDS, config.REF):
        if aid not in out or out[aid].symbol != symbol:
            raise MissingData(f"the universe's aid {aid} is not {symbol}: the REF aids are config.REF's, in its order")
    return out


class Universe:
    """The point-in-time membership as the PARENT reads it (`<root>/universe/`): symbols and aids never leave it."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        folder = self.root / UNIVERSE_DIR
        manifest = _json_file(folder / UNIVERSE_MANIFEST, "universe manifest")
        if not isinstance(manifest, dict) or manifest.get("version") != UNIVERSE_VERSION or \
                not isinstance(manifest.get("sha256"), dict):
            raise MissingData(f"the universe's manifest is not a {UNIVERSE_VERSION} manifest")
        self._manifest = manifest
        shas = manifest["sha256"]
        try:
            raw = json.loads(_verified_bytes(folder / "assets.json", shas.get("assets.json"), "assets"))
        except ValueError as exc:
            raise MissingData(f"the universe's assets.json is unreadable: {exc}") from None
        self._assets = _assets(raw)
        self._source: dict[str, Any] | None = None
        if "SOURCE.json" in shas:
            try:
                self._source = json.loads(_verified_bytes(folder / "SOURCE.json", shas["SOURCE.json"], "source"))
            except ValueError as exc:
                raise MissingData(f"the universe's SOURCE.json is unreadable: {exc}") from None
        mark = manifest.get("salt")
        if mark is not None and hashlib.sha256(read_salt(self.root)).hexdigest()[:SALT_MARK] != mark:
            raise MissingData("the House salt is not the one this universe was written under: every slot id of every "
                              "run would move (refused)")
        self._panel: PanelStore | None = None
        self._by_ticker: dict[str, list[_Asset]] = {}
        for asset in self._assets.values():
            for ticker in {row[0] for row in asset.spells} | {asset.symbol}:
                self._by_ticker.setdefault(ticker, []).append(asset)

    def manifest(self) -> dict[str, Any]:
        """universe/UNIVERSE_MANIFEST.json as written."""
        return json.loads(json.dumps(self._manifest))

    @property
    def sha256(self) -> str:
        """assets.json's sha256 (what a slice's `data_version` names of the universe)."""
        return str(self._manifest["sha256"].get("assets.json"))

    @property
    def known_through(self) -> dt.date:
        """The last day the membership is known through (the spell file's, extended by the accepted change rows)."""
        source = self._source or {}
        wiki = source.get("wiki") if isinstance(source.get("wiki"), Mapping) else {}
        try:
            found = [as_date(d) for d in (source.get("known_through"), wiki.get("known_through")) if d]
        except (TypeError, ValueError):
            found = []
        if not found:
            raise MissingData("the universe's SOURCE.json names no known_through day")
        return max(found)

    def has(self, aid: int) -> bool:
        """Whether assets.json holds `aid`."""
        return int(aid) in self._assets

    def member(self, aid: int, day: dt.date) -> bool:
        """D3: some spell of `aid` has start <= day and (end is null or day < end). A REF aid is never a member."""
        asset = self._assets.get(int(aid))
        return asset is not None and not asset.ref and asset.spell(as_date(day)) is not None

    def masked(self, aid: int) -> str | None:
        """Why `aid` is masked (one of `MASKS`), or None. KeyError for an aid the universe lacks."""
        return self._assets[int(aid)].masked

    def members(self, day: dt.date) -> list[tuple[int, str]]:
        """(aid, symbol) of every member on `day` that is unmasked (the class-pair rule not applied)."""
        day = as_date(day)
        out = []
        for aid in sorted(self._assets):
            asset = self._assets[aid]
            if asset.ref or asset.masked is not None:
                continue
            spell = asset.spell(day)
            if spell is not None:
                out.append((aid, spell[0]))
        return out

    def symbol(self, aid: int, day: dt.date) -> str:
        """The symbol `aid` traded under on `day` (KeyError when it had none): its spell's ticker on a member day; once
        its last spell is over, the asset's current or last venue symbol; between two spells the ended one's ticker; a
        REF aid's own symbol on every day."""
        asset = self._assets.get(int(aid))
        if asset is None:
            raise KeyError(f"the universe holds no aid {aid}")
        if asset.ref:
            return asset.symbol
        day = as_date(day)
        spell = asset.spell(day)
        if spell is not None:
            return spell[0]
        earlier = [row for row in asset.spells if row[2] is not None and row[2] <= day]
        if not earlier:
            raise KeyError(f"aid {aid} had no symbol on {day} (its first spell starts later)")
        return asset.symbol if earlier[-1] is asset.spells[-1] and asset.symbol else earlier[-1][0]

    def aid(self, symbol: str, day: dt.date) -> int:
        """The aid that traded under `symbol` on `day` (KeyError when none did, or more than one): `symbol`'s inverse;
        a member of that day before a name that has left."""
        name, day = str(symbol).strip().upper(), as_date(day)
        found = []
        for asset in self._by_ticker.get(name, ()):
            try:
                if self.symbol(asset.aid, day) == name:
                    found.append(asset)
            except KeyError:
                continue
        pick = [a for a in found if a.ref or a.spell(day) is not None] or found
        if len(pick) != 1:
            raise KeyError(f"{'no' if not pick else 'more than one'} asset traded as {name} on {day}")
        return pick[0].aid

    def left(self, day: dt.date) -> list[int]:
        """The aids that were index members before `day` and are not on it (a held lot of one keeps its column)."""
        day = as_date(day)
        return sorted(a.aid for a in self._assets.values()
                      if not a.ref and a.spell(day) is None and any(row[2] is not None and row[2] <= day
                                                                    for row in a.spells))

    def exit(self, aid: int, day: dt.date) -> str | None:
        """How the spell of `aid` that covers `day`, or its last one before it, ended ("deal" | "other" | "unknown"),
        None while it is open (D12: counted beside a result, never a price). The spell's end may lie after `day`: it
        is a membership fact about the spell a vanished name's bars ended in, and no price."""
        asset = self._assets[int(aid)]
        day = as_date(day)
        rows = [row for row in asset.spells if row[1] <= day]
        if not rows or rows[-1][2] is None:
            return None
        return rows[-1][3] if rows[-1][3] in EXITS else "unknown"

    def class_aids(self, pair: Sequence[str]) -> list[int]:
        """Every aid that has traded as one of a class pair's tickers (`config.CLASS_PAIRS`), ascending."""
        names = {str(t).strip().upper() for t in pair}
        return sorted(a.aid for a in self._assets.values()
                      if not a.ref and (names & ({row[0] for row in a.spells} | {a.symbol})))

    def panel(self) -> "PanelStore":
        """This root's panel store (no capability: the membership side opens no sealed bar)."""
        if self._panel is None:
            self._panel = PanelStore(self.root)
            self._panel._universe = self
        return self._panel

    def tradable(self, day: dt.date) -> set[str]:
        """The symbols of the constitution's `equity_money.universe.stock` in force on `day` (every member before
        `live_from`): the members of `day` whose column the panel's `tradable` row of `day` marks, or its last row for
        a day after the store's last (the constitution moves only by a release, and the data job writes a row a
        session)."""
        day = as_date(day)
        allowed = self.panel().tradable_aids(day)
        return {symbol for aid, symbol in self.members(day) if allowed is None or aid in allowed}

    def stale_days(self, day: dt.date) -> int:
        """Calendar days from `known_through` to `day` (0 when it is not behind)."""
        return max(0, (as_date(day) - self.known_through).days)

    def table(self) -> np.ndarray:
        """Every aid of assets.json, ascending: the set `ids_for` settles a collision over."""
        return np.array(sorted(self._assets), dtype=np.int32)


# -------------------------------------------------------------------------------------------------- the panel store
class PanelStore:
    """Read-only access to the panel store under `root` (`<state>/equity-daily`). `gate`: an E1
    `league.equity.store.EquityGateCapability` minted by `mint_equity_gate_capability(root, reason)` on E1's `GATE`
    mark, or None (Train and Validation only): there is no second capability type."""

    def __init__(self, root: str | Path, *, gate: Any = None):
        self.root = Path(root)
        if gate is not None:
            if not isinstance(gate, EquityGateCapability):
                raise StoreRefused("gate must be an EquityGateCapability minted on the House's store")
            if gate.store_root != str(self.root.resolve()):
                raise StoreRefused("this capability was minted for another store")
        self._gate = gate
        folder = self.root / PANEL_DIR
        self._folder = folder
        version_file = folder / VERSION_FILE
        if not version_file.is_file():
            raise MissingData(f"no panel store at {self.root} (no {PANEL_DIR}/{VERSION_FILE} file)")
        version = version_file.read_text().strip()
        if version != XS_STORE_VERSION:
            raise MissingData(f"{folder} is {version!r}; this engine reads {XS_STORE_VERSION}")
        manifest = _json_file(folder / PANEL_MANIFEST, "panel manifest")
        if not isinstance(manifest, dict) or manifest.get("version") != XS_STORE_VERSION or \
                not isinstance(manifest.get("sha256"), dict):
            raise MissingData(f"the panel store's manifest is not a {XS_STORE_VERSION} manifest")
        self._manifest = manifest
        shas = manifest["sha256"]
        self._days = np.asarray(_small_array(folder / "days.npy", shas.get("days.npy"), "days"), dtype=np.int32)
        self._early = np.asarray(_small_array(folder / "early.npy", shas.get("early.npy"), "early flags"), dtype=bool)
        self._aids = np.asarray(_small_array(folder / "aids.npy", shas.get("aids.npy"), "aids"), dtype=np.int32)
        self._dates = [from_ordinal(int(d)) for d in self._days]
        self._index = {d: i for i, d in enumerate(self._dates)}
        n, m = len(self._dates), int(self._aids.shape[0])
        if not n or self._early.shape != (n,) or tuple(self._aids[:len(REF_AIDS)].tolist()) != REF_AIDS:
            raise MissingData("the panel store's days, early flags and aids do not agree")
        try:
            self._through = dt.date.fromisoformat(str(manifest["fetched_through"]))
        except (KeyError, ValueError):
            raise MissingData("the panel store's manifest names no fetched_through day") from None
        if self._through != self._dates[-1]:
            raise MissingData("the panel store's last session is not its manifest's fetched_through")
        self._shape = (n, m)
        self._column = {int(a): i for i, a in enumerate(self._aids.tolist())}
        self._arrays: dict[str, np.ndarray] = {}
        self._universe: Universe | None = None
        self._class_out: dict[tuple[int, int], frozenset[int]] = {}

    # ------------------------------------------------------------------ facts
    @property
    def gate(self) -> bool:
        """Whether this store was opened with the gate's capability."""
        return self._gate is not None

    def manifest(self) -> dict[str, Any]:
        """panel/PANEL_MANIFEST.json as written (`write_panel`)."""
        return json.loads(json.dumps(self._manifest))

    def verdict(self) -> str:
        """The coverage verdict (D19): one of `VERDICTS` (a manifest without one reads "insufficient")."""
        verdict = self._manifest.get("verdict")
        return verdict if verdict in VERDICTS else "insufficient"

    def train_years_ok(self) -> tuple[int, ...]:
        """The years of `config.TRAIN_YEARS` whose member-day coverage is at or above the coverage floor."""
        try:
            listed = {int(y) for y in self._manifest.get("train_years_ok") or ()}
        except (TypeError, ValueError):
            listed = set()
        return tuple(y for y in config.TRAIN_YEARS if y in listed)

    @property
    def fetched_through(self) -> dt.date:
        """The last session the store's fetch covered (its last close)."""
        return self._through

    @property
    def live_from(self) -> dt.date | None:
        """The first session the universe deploy was in force (None until then)."""
        value = self._manifest.get("live_from")
        try:
            return None if value is None else dt.date.fromisoformat(str(value))
        except ValueError:
            raise MissingData("the panel store's manifest names a live_from that is no day") from None

    def aids(self) -> np.ndarray:
        """int32: the aid of every column the store holds (the REF aids first, then the members ascending)."""
        return self._aids.copy()

    def universe(self) -> Universe:
        """This root's universe (`<root>/universe/`): the masks, the class pairs, the exits and the asset table a
        slice is built with. MissingData when it is absent."""
        if self._universe is None:
            self._universe = Universe(self.root)
            self._universe._panel = self
        return self._universe

    def _array(self, name: str) -> np.ndarray:
        found = self._arrays.get(name)
        if found is None:
            n, m = self._shape
            shape = {"raw.npy": (n, m, 5), "adj.npy": (n, m, 4), "member.npy": (n, m), "tradable.npy": (n, m),
                     "hs.npy": (m, 2)}[name]
            sha = self._manifest["sha256"].get(name)
            if name in ("raw.npy", "adj.npy"):
                found = _verified_array(self._folder / name, sha, name)
            else:
                found = _small_array(self._folder / name, sha, name)
            if found.shape != shape:
                raise MissingData(f"the panel store's {name} is {found.shape}, not {shape}")
            self._arrays[name] = found
        return found

    # ------------------------------------------------------------------ windows
    def _span(self, window: str) -> tuple[dt.date, dt.date]:
        if window == "validation":
            first, last = _e1.WINDOWS["validation"]
            return first, min(last, self._through)  # type: ignore[type-var]
        if window == "look":
            return _e1.WINDOWS["validation"][0], min(self._through, _e1.LOOK_CAP)
        return _e1.WINDOWS["forward"][0], self._through

    def _check(self, window: str) -> None:
        if window not in WINDOWS:
            raise StoreRefused(f"no window {window!r}; one of {', '.join(WINDOWS)}")
        if window in SEALED and self._gate is None:
            raise StoreRefused(f"the {window} days open only for the gate")

    def sessions(self, window: str) -> list[dt.date]:
        """The RUN sessions of `window` (one of `WINDOWS`): never a session of 2016, 2020 or 2021; a sealed window
        lists nothing without the capability (StoreRefused)."""
        self._check(window)
        if window == "train":
            return [d for d in self._dates if any(lo <= d <= hi for lo, hi in config.TRAIN_SEGMENTS)]
        first, last = self._span(window)
        return [d for d in self._dates if first <= d <= last]

    # ------------------------------------------------------------------ the parent's part of eligibility
    def class_out(self, day: dt.date) -> frozenset[int]:
        """D4, ONE CLASS A COMPANY: the aids that are NOT the eligible class of their company in `day`'s month.

        For each pair of `config.CLASS_PAIRS` the eligible class is CHOSEN ONCE A MONTH, at the month's first session
        m0, among the pair's classes that are index members on m0: the one with the higher median raw dollar volume
        (raw close x raw volume over its valid bars) on the `config.CLASS_SESSIONS` store sessions through the
        session BEFORE m0 (no valid bar there reads as the lowest; ties: the lower aid), and it is held for the whole
        month: every other aid of the pair is out, a class that joins the index mid-month too. A pair with no member
        on m0 has no choice that month. The Gym's slices and a live day's columns read this one function (live knows
        the choice a day ahead: it reads no bar of m0)."""
        day = as_date(day)
        key = (day.year, day.month)
        found = self._class_out.get(key)
        if found is None:
            universe = self.universe()
            first = nyse_sessions(day.replace(day=1), day.replace(day=1) + dt.timedelta(days=14))[0][0]
            hi = int(np.searchsorted(self._days, ordinal(first)))      # the store rows strictly before m0
            lo = max(0, hi - config.CLASS_SESSIONS)
            out: set[int] = set()
            for pair in config.CLASS_PAIRS:
                aids = universe.class_aids(pair)
                members = [a for a in aids if universe.member(a, first)]
                if not members:
                    continue
                best, best_volume = members[0], -math.inf
                for aid in members:                                    # ascending: a tie keeps the lower aid
                    volume = -math.inf
                    if aid in self._column and hi > lo:
                        rows = np.asarray(self._array("raw.npy")[lo:hi, self._column[aid], :], dtype=np.float64)
                        valid = valid_bars(rows)
                        if bool(valid.any()):
                            volume = float(np.median(rows[valid, 3] * rows[valid, 4]))
                    if volume > best_volume:
                        best, best_volume = aid, volume
                out.update(a for a in aids if a != best)
            found = self._class_out[key] = frozenset(out)
        return found

    def tradable_aids(self, day: dt.date) -> set[int] | None:
        """The aids the store's `tradable` row of `day` marks (its last row for a day after the store's last), or None
        before `live_from`: every member is tradable then (D4)."""
        day = as_date(day)
        live_from = self.live_from
        if live_from is None or day < live_from:
            return None
        row = int(np.searchsorted(self._days, ordinal(day), side="right")) - 1
        if row < 0:
            return set()
        flags = np.asarray(self._array("tradable.npy")[row], dtype=bool)
        return {int(a) for a in self._aids[flags].tolist()}

    def elig0_row(self, day: dt.date, aids: Sequence[int]) -> np.ndarray:
        """bool (len(aids),): THE PARENT'S PART OF ELIGIBILITY at the close of `day` for the columns `aids`, as a LIVE
        decision's columns need it (`league.xs.book.columns`), by the rules a slice's `elig0` rows are built from: a
        member on `day` and on the next `config.MEMBER_AHEAD` sessions (read from the universe's spells: live knows
        the changes the universe job has read by the decision), tradable (`tradable_aids`), unmasked, and the class
        of the month (`class_out`). A REF aid and an aid the universe lacks are False."""
        day = as_date(day)
        universe = self.universe()
        ahead = [day]
        for _ in range(config.MEMBER_AHEAD):
            ahead.append(config.next_session(ahead[-1]))
        out_class = self.class_out(day)
        tradable = self.tradable_aids(day)
        row = []
        for aid in (int(a) for a in np.asarray(aids).reshape(-1).tolist()):
            row.append(universe.has(aid) and universe.masked(aid) is None and aid not in out_class
                       and all(universe.member(aid, d) for d in ahead) and (tradable is None or aid in tradable))
        return np.array(row, dtype=bool)

    # ------------------------------------------------------------------ slices
    def data_version(self, days: Sequence[dt.date]) -> str:
        """24 hex over the manifest's shas and the span (the universe's assets among them: a slice's eligibility,
        exits and ids are read from it)."""
        days = list(days)
        digest = hashlib.sha256(XS_STORE_VERSION.encode())
        for name in sorted(self._manifest["sha256"]):
            digest.update(f"{name}={self._manifest['sha256'][name]};".encode())
        digest.update(f"universe={self.universe().sha256};".encode())
        span = f"{days[0].isoformat()}..{days[-1].isoformat()}" if days else "none"
        digest.update(f"days={len(days)}:{span}".encode())
        return digest.hexdigest()[:24]

    def _slice(self, run: list[dt.date], window: str, history: int, run_key: str, *,
               aids: Sequence[int] | None = None, half: int | None = None) -> Slice:
        if isinstance(history, bool) or not isinstance(history, int) or \
                not config.MIN_HISTORY <= history <= config.MAX_HISTORY:
            raise ValueError(f"history is {config.MIN_HISTORY} to {config.MAX_HISTORY} sessions")
        if half not in (None, 0, 1) or isinstance(half, bool):
            raise ValueError("a half is 0, 1 or None")
        for day in run:
            if day.year in config.RESERVE_YEARS:
                raise StoreRefused(f"{day} is the reserve: never in the panel store, never a run session")
            if day.year in config.HISTORY_YEARS:
                raise StoreRefused(f"{day.year} is history only: look-back for the year after it, never a run session")
        universe = self.universe()
        salt = read_salt(self.root)
        run_s = run_salt(salt, run_key)
        ref = len(REF_AIDS)
        first = lo = hi = 0
        if run:
            first, last = self._index[run[0]], self._index[run[-1]]
            if last - first + 1 != len(run):
                raise StoreRefused("a slice's run sessions are consecutive sessions of the store")
            # THE LOOK-BACK: up to DERIVE_SESSIONS sessions before the run's first, never across the reserve (no
            # look-back and no return crosses 2020: a segment's first decision reads its own span's history only, a
            # session short of a 12-1 momentum).
            span_first = max((a for _, a, b in config.SPANS if a <= run[0] and (b is None or run[0] <= b)),
                             default=run[0])
            lo = max(int(np.searchsorted(self._days, ordinal(span_first))), first - config.DERIVE_SESSIONS)
            hi = last + 1
        if self._gate is None:
            for day in self._dates[lo:first]:
                if _sealed(day):
                    raise StoreRefused(f"a look-back session ({day}) opens only for the gate")
        n = hi - lo
        member_rows = np.asarray(self._array("member.npy")[lo:hi], dtype=bool)
        if aids is None:
            wanted = [int(a) for a in self._aids[ref:][member_rows[:, ref:].any(axis=0)].tolist()] if n else []
        else:
            wanted = sorted({int(a) for a in np.asarray(aids).reshape(-1).tolist()} - set(REF_AIDS))
        missing = [a for a in wanted if a not in self._column]
        if missing:
            raise MissingData(f"the panel store holds no column for the aid {missing[0]}")
        ids = ids_for(wanted, run_s, table=universe.table()) if wanted else np.zeros(0, dtype=np.int32)
        order = np.argsort(ids, kind="stable")
        member_aids = [wanted[i] for i in order.tolist()]
        ids = ids[order].astype(np.int32)
        cols = np.array([*range(ref), *(self._column[a] for a in member_aids)], dtype=np.int64)
        m = int(cols.shape[0])
        raw = np.asarray(self._array("raw.npy")[lo:hi], dtype=np.float64)[:, cols, :]
        adj = np.asarray(self._array("adj.npy")[lo:hi], dtype=np.float64)[:, cols, :]
        elig0 = np.zeros((n, m), dtype=bool)
        if n and m > ref:
            mem = member_rows[:, cols]
            elig0 = mem.copy()
            for k in range(1, config.MEMBER_AHEAD + 1):           # past the slice's last session: as at the last
                elig0 &= mem[np.minimum(np.arange(n) + k, n - 1)]
            elig0 &= np.asarray(self._array("tradable.npy")[lo:hi], dtype=bool)[:, cols]
            keep = np.array([False] * ref + [universe.masked(a) is None and (half is None or half_of(salt, a) == half)
                                             for a in member_aids], dtype=bool)
            elig0 &= keep[None, :]
            position = {a: ref + i for i, a in enumerate(member_aids)}
            months: dict[tuple[int, int], list[int]] = {}
            for row, day in enumerate(self._dates[lo:hi]):
                months.setdefault((day.year, day.month), []).append(row)
            for (year, month), rows in months.items():
                out = [position[a] for a in self.class_out(dt.date(year, month, 1)) if a in position]
                if out:
                    elig0[np.ix_(rows, out)] = False
        days = self._dates[lo:hi]
        exits = np.zeros(m, dtype=np.int8)
        if days:
            for i, aid in enumerate(member_aids):
                exits[ref + i] = 1 if universe.exit(aid, days[-1]) == "deal" else 0
        hs = np.maximum(np.asarray(self._array("hs.npy"), dtype=np.float64)[cols], config.HS_FLOOR_BP / 10_000.0)
        bars = PanelBars(days=_frozen(self._days[lo:hi].astype(np.int32)), early=_frozen(self._early[lo:hi].copy()),
                         first=first - lo, raw=_frozen(raw), adj=_frozen(adj), elig0=_frozen(elig0), ref=ref,
                         ids=_frozen(ids), exit=_frozen(exits), hs=_frozen(hs), sector_perm=_frozen(sector_perm(run_s)),
                         dither_key=dither_key(run_s), window=window, data_version=self.data_version(days))
        return Slice(bars=bars, aids=_frozen(np.array([*REF_AIDS, *member_aids], dtype=np.int32)), run_key=run_key)

    def bars(self, window: str, *, history: int, run_key: str, start: dt.date | None = None,
             end: dt.date | None = None, aids: Sequence[int] | None = None) -> Slice:
        """The slice of "validation", or with the capability "look" or "forward", cut to [start, end]. Its member
        columns are every asset that is a member on any of its sessions (run and look-back), so the column set never
        depends on the day asked; `aids`: build exactly these member columns instead (a twin, or an I6 check that must
        match a live day's columns). It carries `config.DERIVE_SESSIONS` sessions before its first run session where
        the store holds them. StoreRefused for a run session of 2016, 2020 or 2021 ("history only" / "the reserve")
        and for a sealed window without the capability."""
        self._check(window)
        if window == "train":
            raise StoreRefused("a Train slice is one span inside a Train segment: PanelStore.train(start, end)")
        first, last = self._span(window)
        lo = first if start is None else max(first, as_date(start))
        hi = last if end is None else min(last, as_date(end))
        return self._slice([d for d in self._dates if lo <= d <= hi], window, history, run_key, aids=aids)

    def train(self, start: dt.date, end: dt.date, *, history: int, run_key: str, half: int | None = None,
              aids: Sequence[int] | None = None) -> Slice:
        """A Train slice: [start, end] inside ONE span of `config.TRAIN_SEGMENTS`, else StoreRefused (a whole segment
        for the floor's pools, a seen span for the Train bar, a hidden year for the out-of-fold run). `half` 0 | 1: the
        other half's members are invisible (D18: `elig0` False: not eligible, in no cell, no placebo candidate).
        `aids`: build exactly these member columns (`bars`' keyword: the I6 helper's)."""
        start, end = as_date(start), as_date(end)
        if not any(lo <= start <= end <= hi for lo, hi in config.TRAIN_SEGMENTS):
            years = set(range(min(start.year, end.year), max(start.year, end.year) + 1))
            if years & set(config.RESERVE_YEARS):
                raise StoreRefused(f"{start}..{end} touches the reserve: never in the panel store, never a run session")
            if years & set(config.HISTORY_YEARS):
                raise StoreRefused(f"{start}..{end} touches a year that is history only: look-back, never a run "
                                   "session")
            raise StoreRefused(f"a Train slice lies inside ONE Train segment; {start}..{end} does not")
        return self._slice([d for d in self._dates if start <= d <= end], "train", history, run_key, half=half,
                           aids=aids)


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
    `revisions`: the raw rows a refetch changed. `hs_share`: the share of the Train eras' member-days whose name has
    enough spread samples at both fill points (package A's `equity_panel.hs_share`; None: unknown, which every reader
    takes as below any bound). `live_from`: the first
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


def write_universe(root: str | Path, *, assets: Mapping[Any, Mapping[str, Any]], salt: bytes | None = None,
                   spells: Sequence[Sequence[Any]] | None = None, source: Mapping[str, Any] | None = None,
                   tradable: Mapping[str, Any] | None = None, audit: Mapping[str, Any] | None = None,
                   wiki_reach: Any = None) -> dict[str, Any]:
    """Write `<root>/universe/` atomically (the layout above, UNIVERSE_MANIFEST.json last) and return its manifest.
    `synth` writes its universes through it; package A's job may. `assets`: assets.json's object (aid -> {spells,
    symbol, alpaca, ref, renames, masked}); the REF aids are `REF_AIDS` in `config.REF`'s order. `spells`: spells.csv's
    rows (ticker, start, end | None, source). `source`, `tradable`: SOURCE.json's and tradable.json's objects.

    THE SALT IS WRITTEN ONCE: when `<root>/universe/SALT` exists it is kept (a `salt` that differs is a ValueError:
    the salt is never rewritten); else it is `salt`, or `os.urandom`. It is in no manifest: only the first
    `SALT_MARK` hex of its sha256, to detect a change."""
    root = Path(root)
    body: dict[str, Any] = {}
    exits = {name: 0 for name in EXITS}
    for key in sorted(assets, key=int):
        row = assets[key]
        aid = int(key)
        mask = row.get("masked")
        if mask is not None and mask not in MASKS:
            raise ValueError(f"aid {aid}: a mask is one of {', '.join(MASKS)}, or null")
        rows = []
        for spell in row.get("spells") or ():
            ticker, start = str(spell[0]).strip().upper(), as_date(spell[1])
            end = None if spell[2] is None else as_date(spell[2])
            how = spell[3] if len(spell) > 3 else None
            if not ticker or (end is not None and end <= start):
                raise ValueError(f"aid {aid}: a spell is a ticker with a start before its end")
            if (how is None) != (end is None) or (how is not None and how not in EXITS):
                raise ValueError(f"aid {aid}: an ended spell's exit is one of {', '.join(EXITS)}; an open one's is null")
            if how is not None:
                exits[how] += 1
            rows.append([ticker, start.isoformat(), None if end is None else end.isoformat(), how])
        ref = aid in REF_AIDS
        if bool(row.get("ref", ref)) != ref or (not ref and aid < FIRST_MEMBER_AID):
            raise ValueError(f"aid {aid}: the REF aids are {REF_AIDS[0]}..{REF_AIDS[-1]}, members from "
                             f"{FIRST_MEMBER_AID}")
        symbol = str(row.get("symbol") or (rows[-1][0] if rows else "")).strip().upper()
        if not symbol or (ref and symbol != config.REF[aid - 1]):
            raise ValueError(f"aid {aid}: an asset has a symbol (a REF aid config.REF's own)")
        body[str(aid)] = {"spells": rows, "symbol": symbol, "alpaca": row.get("alpaca"), "ref": ref,
                          "renames": list(row.get("renames") or ()), "masked": mask}
    if [a for a in REF_AIDS if str(a) not in body]:
        raise ValueError("assets holds every REF aid")
    lines = None
    if spells is not None:
        lines = ["ticker,start,end,source"]
        for ticker, start, end, origin in spells:
            lines.append(",".join([str(ticker).strip().upper(), as_date(start).isoformat(),
                                   "" if end is None else as_date(end).isoformat(), str(origin)]))
    blocks = {name: json.dumps(json.loads(json.dumps(dict(block), default=str)), sort_keys=True, indent=1).encode()
              for name, block in (("SOURCE.json", source), ("tradable.json", tradable)) if block is not None}
    reach = _iso(wiki_reach, "wiki_reach")
    checked = json.loads(json.dumps(dict(audit or {}), default=str))
    if salt is not None:
        salt = _salt(salt)
    folder = root / UNIVERSE_DIR
    salt_path = folder / SALT_FILE
    if salt_path.is_file():
        kept = read_salt(root)
        if salt is not None and salt != kept:
            raise ValueError("the House salt is written once and never rewritten")
        salt = kept
    # Everything is read and refused before the first byte is written.
    _private_dir(root)
    _private_dir(folder)
    if not salt_path.is_file():
        salt = salt if salt is not None else os.urandom(SALT_BYTES)
        _atomic_bytes(salt_path, salt)
    shas = {"assets.json": _atomic_bytes(folder / "assets.json", json.dumps(body, sort_keys=True, indent=1).encode())}
    if lines is not None:
        shas["spells.csv"] = _atomic_bytes(folder / "spells.csv", ("\n".join(lines) + "\n").encode())
    for name, data in blocks.items():
        shas[name] = _atomic_bytes(folder / name, data)
    manifest = {"version": UNIVERSE_VERSION, "sha256": shas, "audit": checked, "exits": exits, "wiki_reach": reach,
                "salt": hashlib.sha256(salt).hexdigest()[:SALT_MARK]}  # type: ignore[arg-type]
    _atomic_bytes(folder / UNIVERSE_MANIFEST, json.dumps(manifest, sort_keys=True, indent=1).encode())
    return manifest


__all__ = ["PANEL_DIR", "UNIVERSE_DIR", "SALT_FILE", "SALT_BYTES", "UNIVERSE_VERSION", "PANEL_FILES", "VERSION_FILE",
           "PANEL_MANIFEST", "UNIVERSE_MANIFEST", "VERDICTS", "MASKS", "EXITS", "REF_AIDS", "FIRST_MEMBER_AID",
           "COVERAGE_MIN", "JUDGED_YEARS", "UNIVERSE_FILES", "SALT_MARK", "WINDOWS", "SEALED", "StoreRefused",
           "MissingData", "PanelBars", "Slice", "PanelStore", "Universe", "read_salt", "run_salt", "ids_for",
           "dither_key", "sector_perm", "half_of", "valid_bars", "coverage", "write_panel", "write_universe"]
