"""What the live path reads from the swarm, and writes back: the families it runs, their forward records, their bands.

The options-swarm run, Wave 5 (Sept 26, 2026), the interface agreed with Wave 4 (the swarm) through the main session:

- `league.swarm.bands.read(root)` -> one row per family the live path may run: {family, band ("gym" | "candidate" |
  "probe" | "sized"), structure, roots, holdout_passed, validation_passed, version, code, params, run_sha,
  typical_max_loss_usd (one structure's median maximum loss in its validation run, or None), seed_era, forward
  (the nightly + shadow + real record, with `negative`)}.
- `SwarmStore(root).add_forward(family, "shadow" | "real", trades)`: the live path's forward trades, each once by id, each
  carrying its program `version` (a new version starts its own record).
- `SwarmStore(root).forward(family)`: the whole forward record, one row a trade ({pnl, max_loss, source, ...}).
- `SwarmStore(root).set_band(family, band, reason=...)`: the live path alone moves candidate <-> probe <-> sized (the
  money table is its; the swarm moves gym <-> candidate and retires families).

`MemoryFamilies` is the same API in memory, for tests and for a House without the swarm.
"""

from __future__ import annotations

import copy
from contextlib import contextmanager
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


def _entry_matches(row: Mapping[str, Any] | None, expected: Mapping[str, Any], real: bool) -> bool:
    # The decider's run hash includes merged program defaults; the swarm's hash covers stored overrides. Compare
    # the exact immutable source and overrides actually loaded, so those distinct hash conventions cannot disagree.
    if (not row or row.get("version") != expected.get("version") or row.get("code") != expected.get("code")
            or (row.get("params") or {}) != (expected.get("params") or {})):
        return False
    band = row.get("band")
    if not real:
        return band in ("candidate", "probe", "sized")
    if band != expected.get("band"):
        return False
    if expected.get("tuition"):
        return band == "gym" and bool(row.get("validation_passed")) and not row.get("holdout_passed")
    return band in ("probe", "sized") and bool(row.get("holdout_passed")) and not (row.get("forward") or {}).get("negative")


class SwarmFamilies:
    """The swarm's store in the House's state root (read and written from the House's process)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._store = None
        self.lock = threading.Lock()

    def _db(self) -> Any:
        if self._store is None:
            from ..swarm.store import SwarmStore

            self._store = SwarmStore(self.root)
        return self._store

    def read(self) -> list[dict]:
        from ..swarm import bands

        return [dict(row) for row in bands.read(self.root)]

    def forward_rows(self, family: str) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self._db().forward(family)]

    @contextmanager
    def admit_open(self, expected: Mapping[str, Any], *, real: bool):
        """Serialize current eligibility with durable local order admission, never with venue/network work."""
        with self.lock, self._db().atomic():
            row = next((r for r in self.read() if r["family"] == expected["family"]), None)
            evidence_current = (not real or expected.get("tuition") or
                                self._db().forward(str(expected["family"])) == expected.get("forward_rows"))
            yield _entry_matches(row, expected, real) and evidence_current

    def add_forward(self, family: str, source: str, trades: Iterable[Mapping[str, Any]]) -> int:
        with self.lock:
            return int(self._db().add_forward(family, source, list(trades)) or 0)

    def set_band(self, family: str, band: str, reason: str) -> None:
        with self.lock:
            self._db().set_band(family, band, reason=reason)

    def confirm_band(self, expected: Mapping[str, Any], band: str, reason: str,
                     forward: Sequence[Mapping[str, Any]], *, at: float | None = None) -> bool:
        """Commit a decision only while its identity, eligibility and exact evidence snapshot still hold.

        The gate uses another SQLite connection and can demote, retire or replace this version while the House
        calculates its money band. The immediate transaction excludes those writers through the final band write.
        Even an unchanged Probe/Sized band requires confirmation before scheduling a real instance.
        """
        from ..swarm.gate import run_sha

        with self.lock:
            store = self._db()
            with store.atomic():
                fam = store.family(str(expected["family"]))
                if not fam or fam["retired_at"] or fam["band"] != expected["band"]:
                    return False
                state = fam["state"] or {}
                version = state.get("banded_version")
                if version != expected.get("version"):
                    return False
                selected = store.version(fam["id"], version)
                if selected is None or run_sha(selected) != expected.get("run_sha"):
                    return False
                typical = (state.get("typical_by_version") or {}).get(str(version),
                    state.get("typical_max_loss_usd") if state.get("validation_version") == version else None)
                if (typical != expected.get("typical_max_loss_usd")
                        or state.get("forward") != expected.get("forward")
                        or store.forward(fam["id"]) != list(forward)):
                    return False
                if band != fam["band"]:
                    if store.set_band(fam["id"], band, reason=reason) != fam["band"]:
                        return False
                    if fam["band"] == "candidate" and band in ("probe", "sized"):
                        store.set_state(fam["id"], live_promoted_at=float(store.clock() if at is None else at))
                return True

    def promoted_at(self, family: str) -> float | None:
        with self.lock:
            row = self._db().family(family)
            value = (row["state"] or {}).get("live_promoted_at") if row else None
            return None if value is None else float(value)


class MemoryFamilies:
    """In memory (tests; a House whose swarm is off). Rows as `SwarmFamilies.read` returns them."""

    def __init__(self, rows: Iterable[Mapping[str, Any]] = ()):
        self.rows = {str(r["family"]): dict(r) for r in rows}
        self.forward: dict[str, dict[tuple[str, str], dict]] = {}
        self.moves: list[tuple[str, str, str]] = []
        self.promotions: dict[str, float] = {}
        self.lock = threading.Lock()

    def read(self) -> list[dict]:
        with self.lock:
            return [copy.deepcopy(r) for r in self.rows.values() if r.get("band") != "retired"]

    def forward_rows(self, family: str) -> list[dict]:
        with self.lock:
            return [dict(v, source=k[0]) for k, v in sorted(self.forward.get(family, {}).items())]

    @contextmanager
    def admit_open(self, expected: Mapping[str, Any], *, real: bool):
        with self.lock:
            family = str(expected["family"])
            rows = [dict(v, source=k[0]) for k, v in sorted(self.forward.get(family, {}).items())]
            evidence_current = not real or expected.get("tuition") or rows == expected.get("forward_rows")
            yield _entry_matches(self.rows.get(family), expected, real) and evidence_current

    def add_forward(self, family: str, source: str, trades: Iterable[Mapping[str, Any]]) -> int:
        if source not in ("nightly", "shadow", "real"):
            raise ValueError(source)
        n = 0
        with self.lock:
            book = self.forward.setdefault(family, {})
            for t in trades:
                key = (source, str(t["id"]))
                if key not in book:
                    book[key] = {"id": str(t["id"]), "day": str(t.get("day") or ""), "pnl": float(t["pnl"]),
                                 "max_loss": float(t.get("max_loss") or 0.0), "version": t.get("version")}
                    n += 1
        return n

    def set_band(self, family: str, band: str, reason: str) -> None:
        with self.lock:
            if family in self.rows and self.rows[family].get("band") != band:
                self.rows[family]["band"] = band
                self.moves.append((family, band, reason))

    def confirm_band(self, expected: Mapping[str, Any], band: str, reason: str,
                     forward: Sequence[Mapping[str, Any]], *, at: float | None = None) -> bool:
        with self.lock:
            family = str(expected["family"])
            current = self.rows.get(family)
            if current != expected:
                return False
            rows = [dict(v, source=k[0]) for k, v in sorted(self.forward.get(family, {}).items())]
            if rows != list(forward):
                return False
            if current["band"] != band:
                if current["band"] == "candidate" and band in ("probe", "sized") and at is not None:
                    self.promotions[family] = float(at)
                self.rows[family]["band"] = band
                self.moves.append((family, band, reason))
            return True

    def promoted_at(self, family: str) -> float | None:
        with self.lock:
            value = self.promotions.get(family, self.rows.get(family, {}).get("real_promoted_at"))
            return None if value is None else float(value)


__all__ = ["SwarmFamilies", "MemoryFamilies"]
