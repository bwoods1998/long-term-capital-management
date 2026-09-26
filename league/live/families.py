"""What the live path reads from the swarm, and writes back: the families it runs, their forward records, their bands.

The options-swarm run, Wave 5 (Sept 26, 2026), the interface agreed with Wave 4 (the swarm) through the main session:

- `league.swarm.bands.read(root)` -> one row per family the live path may run: {family, band ("gym" | "candidate" |
  "probe" | "sized"), structure, roots, holdout_passed, validation_passed, version, code, params, run_sha,
  typical_max_loss_usd (one structure's median maximum loss in its validation run, or None), seed_era, forward
  (the nightly + shadow + real record, with `negative`)}.
- `SwarmStore(root).add_forward(family, "shadow" | "real", trades)`: the live path's forward trades, each once by id.
- `SwarmStore(root).forward(family)`: the whole forward record, one row a trade ({pnl, max_loss, source, ...}).
- `SwarmStore(root).set_band(family, band, reason=...)`: the live path alone moves candidate <-> probe <-> sized (the
  money table is its; the swarm moves gym <-> candidate and retires families).

`MemoryFamilies` is the same API in memory, for tests and for a House without the swarm.
"""

from __future__ import annotations

import copy
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping


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

    def add_forward(self, family: str, source: str, trades: Iterable[Mapping[str, Any]]) -> int:
        with self.lock:
            return int(self._db().add_forward(family, source, list(trades)) or 0)

    def set_band(self, family: str, band: str, reason: str) -> None:
        with self.lock:
            self._db().set_band(family, band, reason=reason)


class MemoryFamilies:
    """In memory (tests; a House whose swarm is off). Rows as `SwarmFamilies.read` returns them."""

    def __init__(self, rows: Iterable[Mapping[str, Any]] = ()):
        self.rows = {str(r["family"]): dict(r) for r in rows}
        self.forward: dict[str, dict[tuple[str, str], dict]] = {}
        self.moves: list[tuple[str, str, str]] = []
        self.lock = threading.Lock()

    def read(self) -> list[dict]:
        with self.lock:
            return [copy.deepcopy(r) for r in self.rows.values() if r.get("band") != "retired"]

    def forward_rows(self, family: str) -> list[dict]:
        with self.lock:
            return [dict(v, source=k[0]) for k, v in sorted(self.forward.get(family, {}).items())]

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
                                 "max_loss": float(t.get("max_loss") or 0.0)}
                    n += 1
        return n

    def set_band(self, family: str, band: str, reason: str) -> None:
        with self.lock:
            if family in self.rows and self.rows[family].get("band") != band:
                self.rows[family]["band"] = band
                self.moves.append((family, band, reason))


__all__ = ["SwarmFamilies", "MemoryFamilies"]
