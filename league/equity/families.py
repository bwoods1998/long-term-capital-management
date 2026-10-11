"""The equity book's reader of the swarm: the equity-lane families it may run, their forward records, their bands.

Owner: book. The options path's reader (league/live/families.py `SwarmFamilies`) reads `league.swarm.bands.read(root)`,
which leaves equity-lane families out by default (swarm: `read(root, lanes=None)` is the options lanes only). This one
reads `league.swarm.bands.read(root, lanes=league.equity.LANES)`; each row is `bands.read`'s (family, band, structure,
roots, holdout_passed, validation_passed, version, code, params, run_sha, version_created_at, version_selected_at,
forward, ...) plus, from the swarm: `lane` ("beta" | "equity"), `symbols` (its card's), `seeded` (True for the three
captain-seeded programs, A4) and here `validation_r_sd` (EDM1's sigma: the swarm state's
`validation_r_sd_by_version[str(version)]`, else `validation_r_sd` while `validation_version` is the version; a positive
finite number, else None).

Writes go through the swarm's store as the options path's do: `add_forward(family, "real", trades)` (each trade once
by its id `eq-<lid>`), `set_band(family, band, reason)` (the book alone moves candidate <-> probe <-> sized for an
equity family), `confirm_band` (the row is still the one the band was judged on, read again inside the store's write
transaction, so a gate or a retirement on the swarm's own connection cannot interleave with the band write).

`last_error` says why the last `read` could not read the store ("" when it could): an unreadable store reads as no
rows, and the book never takes "no rows" from an unreadable store for "every program retired". The read is STRICT
(`bands.read(..., strict=True)`): a missing store, a read that failed within its second and an equity identity that
cannot be computed each raise there and land in `last_error` (the plain read answers [] for all three, which the book
once took for "every family gone"). `standing(family, version)` is the store's own word on ONE family, for an instance
whose family has no row in a good read: the book retires only on what it says ("retired" | "demoted"), never on the
absence alone (one family's code file or version row that cannot be read leaves it out of `read` too). `twins()` is the
swarm store's `equity_twins` record (league/ops/twins.py writes it: {"eq:<lid>": {status, gap_bp, final, ...}}), EDM1's
twin leg.

`MemoryEquityFamilies` is the same API in memory, for tests.
"""

from __future__ import annotations

import copy
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..live.money import positive_sd
from . import LANES

#: The swarm store key league/ops/twins.py records the equity twins under.
TWINS_KEY = "equity_twins"
#: The bands the book itself moves an equity family between (the swarm moves gym <-> candidate and retires).
BOOK_BANDS = ("candidate", "probe", "sized")
#: The bands an instance runs in (league/equity/live.py `LIVE_BANDS`).
RUNNING_BANDS = ("probe", "sized")
#: `standing`'s answers that are POSITIVE EVIDENCE a version no longer runs (the book retires its instance on these
#: alone); "live" (the store shows it running) and "unknown" (it could not be read) change nothing.
GONE = ("retired", "demoted")


def validation_r_sd(state: Any, version: Any) -> float | None:
    """EDM1's sigma for `version` from a family's swarm state (the module docstring), or None."""
    if not isinstance(state, Mapping):
        return None
    by_version = state.get("validation_r_sd_by_version")
    by_version = by_version if isinstance(by_version, Mapping) else {}
    value = by_version.get(str(version),
                           state.get("validation_r_sd") if state.get("validation_version") == version else None)
    return positive_sd(value)


#: The fields of a row that must still hold when its band is written (`confirm_band`).
CONFIRM_FIELDS = ("family", "band", "lane", "version", "run_sha", "holdout_passed", "code", "params")


class EquityFamilies:
    """The swarm-backed reader at `root` (the House's state root)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._store = None
        self.lock = threading.Lock()
        self.last_error = ""

    def _db(self) -> Any:
        if self._store is None:
            from ..swarm.store import SwarmStore

            self._store = SwarmStore(self.root)
        return self._store

    def _rows(self, family: str | None = None) -> list[dict]:
        from ..swarm import bands

        return [dict(row) for row in bands.read(self.root, family=family, lanes=LANES, strict=True)
                if str(row.get("lane") or "") in LANES]

    def read(self, family: str | None = None) -> list[dict]:
        """The equity-lane rows (the module docstring); [] with `last_error` set when the store cannot be read (no
        store, not within a second, no equity identity)."""
        try:
            rows = self._rows(family)
        except Exception as exc:  # noqa: BLE001 - fail closed: no row, and `last_error` says why
            self.last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            return []
        with self.lock:
            for row in rows:
                try:
                    fam = self._db().family(str(row["family"]))
                    row["validation_r_sd"] = validation_r_sd((fam or {}).get("state") or {}, row.get("version"))
                except Exception:  # noqa: BLE001 - absent; `confirm_band` refuses a mismatch
                    row["validation_r_sd"] = None
        self.last_error = ""
        return rows

    def standing(self, family: str, version: int) -> tuple[str, str]:
        """THE STORE'S OWN WORD on `family`'s version `version`, for an instance whose family has no row in a good
        `read`: (code, why), read on the swarm store itself and never inferred from the absence. "retired": its family
        is retired, is no equity-lane family, runs another banded version, or its band's proof is not the current
        equity identity (`bands.current_equity_evaluator`: an evidence release moved it); "demoted": its band is no
        running band (a Candidate waiting for a seat, back in the Gym); "live": the store shows it alive in a running
        band on this version with a current proof (the read left it out for a reason of its own: its code file or its
        version row); "unknown": the family, its version or the equity identity could not be read. Never raises."""
        try:
            with self.lock:
                store = self._db()
                fam = store.family(str(family))
                if fam is None:
                    return "unknown", "the swarm store has no such family"
                if fam.get("retired_at"):
                    return "retired", "its family is retired"
                state = fam.get("state") if isinstance(fam.get("state"), Mapping) else {}
                spec = fam.get("spec") if isinstance(fam.get("spec"), Mapping) else {}
                if str(spec.get("lane") or "") not in LANES:
                    return "retired", "its family is no equity-lane family"
                band = str(fam.get("band") or "")
                if band not in RUNNING_BANDS:
                    return "demoted", f"its band is {band or 'none'}"
                banded = state.get("banded_version")
                if isinstance(banded, bool) or not isinstance(banded, int):
                    return "unknown", f"its band names no version ({banded!r})"
                if banded != int(version):
                    return "retired", f"superseded by version {banded}"
                row = store.version(str(family), banded)
            if row is None or not row.get("sha"):
                return "unknown", f"its version {banded} cannot be read"
            from ..swarm import bands
            from ..swarm.gate import run_sha

            equity_sha = bands._equity_sha()
            if equity_sha is None:
                return "unknown", "the equity identity could not be computed"
            sha = run_sha({"sha": row["sha"], "params": row.get("params") or {}})
            if not bands.current_equity_evaluator(state, sha, equity_sha):
                return "retired", "its band's proof is not the current equity identity"
            return "live", "the store shows it running: its row could not be read (its code file)"
        except Exception as exc:  # noqa: BLE001 - no evidence either way
            return "unknown", f"{type(exc).__name__}: {str(exc)[:160]}"

    def forward_rows(self, family: str) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self._db().forward(family)]

    def add_forward(self, family: str, source: str, trades: Iterable[Mapping[str, Any]]) -> int:
        with self.lock:
            return int(self._db().add_forward(family, source, list(trades)) or 0)

    def set_band(self, family: str, band: str, reason: str) -> None:
        with self.lock:
            self._db().set_band(family, band, reason=reason)

    def confirm_band(self, expected: Mapping[str, Any], band: str, reason: str) -> bool:
        """Write `band` only while the family's row is still `expected` (its band, version, program and look; EDM1's
        sigma), all read again inside the store's write transaction. False (nothing written) otherwise."""
        family = str(expected.get("family") or "")
        if band not in BOOK_BANDS or not family:
            return False
        with self.lock:
            store = self._db()
            with store.atomic():
                fam = store.family(family)
                if not fam or fam.get("retired_at") or fam.get("band") != expected.get("band"):
                    return False
                state = fam.get("state") or {}
                if state.get("banded_version") not in (None, expected.get("version")):
                    return False
                if validation_r_sd(state, expected.get("version")) != expected.get("validation_r_sd"):
                    return False
                row = next((r for r in self._rows(family) if r.get("family") == family), None)
                if row is None or any(row.get(k) != expected.get(k) for k in CONFIRM_FIELDS):
                    return False
                if band != fam["band"]:
                    if store.set_band(family, band, reason=reason) != fam["band"]:
                        return False
                    if fam["band"] == "candidate" and band in ("probe", "sized"):
                        store.set_state(family, live_promoted_at=float(store.clock()))
                return True

    def twins(self) -> dict[str, dict]:
        """The swarm store's equity twins ({} when unreadable)."""
        try:
            with self.lock:
                value = self._db().get(TWINS_KEY, {}) or {}
        except Exception:  # noqa: BLE001
            return {}
        return dict(value) if isinstance(value, Mapping) else {}


class MemoryEquityFamilies:
    """The same API over rows in memory (tests). `forward` {family: {trade id: row}}, `moves` [(family, band, reason)],
    `twin_rows` the twins record; set `last_error` to make `read` answer [] as an unreadable store does. `hidden`:
    families `read` leaves out although they run (a row the store could not read: `standing` then says "live");
    `standing` of a family with no row at all is "unknown" (the store never deletes a family: it retires it, band
    "retired")."""

    def __init__(self, rows: Iterable[Mapping[str, Any]] = ()):
        self.rows = {str(r["family"]): dict(r) for r in rows}
        self.forward: dict[str, dict[str, dict]] = {}
        self.moves: list[tuple[str, str, str]] = []
        self.twin_rows: dict[str, dict] = {}
        self.last_error = ""
        self.hidden: set[str] = set()
        self.lock = threading.Lock()

    def read(self, family: str | None = None) -> list[dict]:
        with self.lock:
            if self.last_error:
                return []
            return [copy.deepcopy(r) for r in self.rows.values() if r.get("band") != "retired"
                    and r["family"] not in self.hidden and (family is None or r["family"] == family)]

    def standing(self, family: str, version: int) -> tuple[str, str]:
        with self.lock:
            row = self.rows.get(str(family))
            if self.last_error:
                return "unknown", self.last_error
            if row is None:
                return "unknown", "the swarm store has no such family"
            if row.get("band") == "retired":
                return "retired", "its family is retired"
            if row.get("band") not in RUNNING_BANDS:
                return "demoted", f"its band is {row.get('band') or 'none'}"
            if int(row.get("version") or 0) != int(version):
                return "retired", f"superseded by version {row.get('version')}"
            return "live", "the store shows it running: its row could not be read (its code file)"

    def forward_rows(self, family: str) -> list[dict]:
        with self.lock:
            return [dict(v) for _, v in sorted(self.forward.get(family, {}).items())]

    def add_forward(self, family: str, source: str, trades: Iterable[Mapping[str, Any]]) -> int:
        if source not in ("nightly", "shadow", "real"):
            raise ValueError(source)
        n = 0
        with self.lock:
            book = self.forward.setdefault(family, {})
            for t in trades:
                key = str(t["id"])
                if key not in book:
                    book[key] = {**dict(t), "source": source}
                    n += 1
        return n

    def set_band(self, family: str, band: str, reason: str) -> None:
        with self.lock:
            if family in self.rows and self.rows[family].get("band") != band:
                self.rows[family]["band"] = band
                self.moves.append((family, band, reason))

    def confirm_band(self, expected: Mapping[str, Any], band: str, reason: str) -> bool:
        with self.lock:
            family = str(expected.get("family") or "")
            current = self.rows.get(family)
            if band not in BOOK_BANDS or current is None or current != dict(expected):
                return False
            if current["band"] != band:
                self.rows[family]["band"] = band
                self.moves.append((family, band, reason))
            return True

    def twins(self) -> dict[str, dict]:
        with self.lock:
            return copy.deepcopy(self.twin_rows)


__all__ = ["TWINS_KEY", "BOOK_BANDS", "RUNNING_BANDS", "GONE", "CONFIRM_FIELDS", "validation_r_sd", "EquityFamilies",
           "MemoryEquityFamilies"]
