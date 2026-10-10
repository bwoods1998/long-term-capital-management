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
equity family), `confirm_band` (the row is still the one the band was judged on).

`MemoryEquityFamilies` is the same API in memory, for tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping


def validation_r_sd(state: Any, version: Any) -> float | None:
    """EDM1's sigma for `version` from a family's swarm state (the module docstring), or None."""
    raise NotImplementedError("book: league/equity/families.py validation_r_sd")


class EquityFamilies:
    """The swarm-backed reader at `root` (the House's state root)."""

    def __init__(self, root: str | Path):
        raise NotImplementedError("book: league/equity/families.py EquityFamilies")

    def read(self, family: str | None = None) -> list[dict]:
        """The equity-lane rows (the module docstring); [] when the store cannot be read within a second."""
        raise NotImplementedError("book: league/equity/families.py EquityFamilies.read")

    def forward_rows(self, family: str) -> list[dict]:
        raise NotImplementedError("book: league/equity/families.py EquityFamilies.forward_rows")

    def add_forward(self, family: str, source: str, trades: Iterable[Mapping[str, Any]]) -> int:
        raise NotImplementedError("book: league/equity/families.py EquityFamilies.add_forward")

    def set_band(self, family: str, band: str, reason: str) -> None:
        raise NotImplementedError("book: league/equity/families.py EquityFamilies.set_band")

    def confirm_band(self, expected: Mapping[str, Any], band: str, reason: str) -> bool:
        raise NotImplementedError("book: league/equity/families.py EquityFamilies.confirm_band")


class MemoryEquityFamilies:
    """The same API over rows in memory (tests)."""

    def __init__(self, rows: Iterable[Mapping[str, Any]] = ()):
        raise NotImplementedError("book: league/equity/families.py MemoryEquityFamilies")

    def read(self, family: str | None = None) -> list[dict]:
        raise NotImplementedError("book: league/equity/families.py MemoryEquityFamilies.read")

    def forward_rows(self, family: str) -> list[dict]:
        raise NotImplementedError("book: league/equity/families.py MemoryEquityFamilies.forward_rows")

    def add_forward(self, family: str, source: str, trades: Iterable[Mapping[str, Any]]) -> int:
        raise NotImplementedError("book: league/equity/families.py MemoryEquityFamilies.add_forward")

    def set_band(self, family: str, band: str, reason: str) -> None:
        raise NotImplementedError("book: league/equity/families.py MemoryEquityFamilies.set_band")

    def confirm_band(self, expected: Mapping[str, Any], band: str, reason: str) -> bool:
        raise NotImplementedError("book: league/equity/families.py MemoryEquityFamilies.confirm_band")


__all__ = ["validation_r_sd", "EquityFamilies", "MemoryEquityFamilies"]
