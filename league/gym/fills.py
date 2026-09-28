"""The fill model: natural by default, better than natural only by a calibrated chance.

A structure order meets each leg's recorded NBBO on the minute after its decision. If its limit is
at or through the natural price (every long leg at the ask, every short leg at the bid) it fills
there, at the natural (a marketable limit gets the touch). Otherwise it works: each later minute
it fills AT ITS LIMIT if the natural has come through it, and otherwise only with the probability
the fill model gives, a per-minute hazard looked up by

- root: every root has its own cells (a root the calibration never sampled has none: natural only);
- q: where the limit sits between the mid (0) and the natural (1) of the UNSTRESSED quotes (a stress
  run widens what fills cost, never which limits can fill), in quarter-spread buckets (negative is
  better than the mid). Bucket 0 is the TOUCH, from the order's own side of the book
  (-1: a buy at the bid, a sell at the ask) to a quarter-spread through the mid; it is measured at
  the touch itself and only where the minute's volume there cleared the queue ahead (`calibrate.py`).
  A limit behind the touch fills only when the market comes through it. A "mid" limit on a
  one-tick spread IS the touch (the mid is off the tick and rounds to the order's own side);
- one leg, or a package: a package's hazard is the LOWEST over its legs of each leg's cell at its
  own days to expiry and moneyness, each the complex-print rate capped by that leg's single-leg rate
  (complex prints are measured leg by leg, and a package needs a counterparty for every leg);
- days to expiry (0, 1-2, 3-7; 8 or more is not modelled: the calibration sample stops at 7 days,
  so a structure with any leg 8 or more days out fills only at or through the natural), moneyness
  (|K/S - 1|: under 0.5%, 0.5-1.5%, 1.5-3%, over 3%) and the time of day (to 10:30, to 15:00, after).

A passive fill takes at most the contracts Train's fills at that level typically found beyond the
queue (`size`, per root, level, leg class and days to expiry; one structure where unknown), and one
minute's passive liquidity on a contract is shared by all of a program's orders on it.

ADVERSE SELECTION: the engine reads the NEXT minute's quotes (the program never sees them) to say whether
the structure's mid then moves against a resting order or stays flat ("adverse": a buyer is not filled
just before the mid rises) or moves in its favour. Two tables, one rule each:

- an UNCONDITIONAL table (`hazard` only; every table fitted before Sept 27, 2026): a passive order fills
  only on adverse-or-flat minutes, drawing against `hazard`, and never on a favourable one. `hazard` is
  measured over ALL quoted minutes, so this fills less often than Train's prints say (the measured rate
  times the share of adverse-or-flat minutes) and never where the market moves the order's way;
- a CONDITIONAL table (`"adverse": "conditional"`, from `calibrate.py --adverse conditional`): the same
  cells measured separately on adverse-or-flat minutes (`hazard_adverse`) and on favourable minutes
  (`hazard_favourable`), and the engine draws against the one the next minute calls for. The average
  rate is then the measured one, and fills still lean toward the minutes that move against the order
  as far as Train's prints did. A package takes the lowest over its legs within that condition, the
  condition being the whole structure's next-minute mid (the legs were measured each on its own). A
  limit at or through the real natural that works only because a stress run widened the spread is no
  measured cell and keeps the unconditional rule (certain on adverse-or-flat minutes, never on others),
  so a conditional table with no favourable cells fills exactly as an unconditional one would. The
  file also carries `hazard`: an engine before this rule reads it as the unconditional table it holds.

Either way a minute with no next quote on a leg fills nothing passively, and the draw is the same keyed
draw (below).

The draw is keyed by (the contracts, the day, the minute, the side) with a fixed seed, never by the
program: a trivial edit to a program cannot re-roll its luck, and two programs that send the same
order at the same minute fill or miss together. The table is a point estimate per cell, fitted from
Train's `trade_quote` samples by `calibrate.py` (the estimator is described there), and read from a
gitignored file: an explicit path, else GYM_FILL_MODEL, else `/data/calibration/fill_model.json` (the
Gym and gate images), else `.data/gym/fill_model.json` under the code's root; absent, every hazard is
zero: natural fills only. A cell the table lacks is zero too, so a table fitted before cells were
keyed by root (Sept 27, 2026) reads as natural-only here, and this table reads as natural-only on
the older engine.

Size is capped by the quoted size at the natural. Stress mode widens every leg's half-spread
(1.5x for the gate's stress test) before the natural is taken, charges a passive fill the extra
half-spread, and multiplies every passive hazard by STRESS_HAZARD (0.5).

numpy is not needed; Python 3.11+.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

#: Part of every fill's key: changing it re-rolls every draw, so it changes only with the engine version.
SEED = "ltcm-gym-fills-v1"
Q_EDGES = (-0.25, 0.0, 0.25, 0.5, 0.75, 1.0)
#: The order's own side of the book (q of a buy at the bid, a sell at the ask): bucket 0's far edge.
TOUCH = -1.0
DTE_EDGES = (0, 1, 3, 8)
#: Passive fills are modelled only through this many days to expiry (the trade sample's reach).
MODELLED_DTE = 7
#: In a stress run (stress above 1: the gate's 1.5x twin) every passive hazard is multiplied by this: the
#: package rate is an upper bound (a complex print may belong to another package), so the stress run also
#: asks whether the edge survives patient orders filling half as often.
STRESS_HAZARD = 0.5
MONEY_EDGES = (0.005, 0.015, 0.03)
TOD_EDGES = (630, 900)
DEFAULT_PATHS = ("/data/calibration/fill_model.json",)
#: The table-level marker (`"adverse"`) of a table whose cells are measured per next-minute condition.
CONDITIONAL = "conditional"
#: Every modelled (dte, moneyness, time) cell suffix: d0-d2 only (8+ days is never modelled).
F_CELLS = tuple(f"d{d}|k{k}|t{t}" for d in range(len(DTE_EDGES) - 1) for k in range(len(MONEY_EDGES) + 1)
                for t in range(len(TOD_EDGES) + 1))


def _bucket(value: float, edges: Sequence[float]) -> int:
    i = 0
    for edge in edges:
        if value >= edge:
            i += 1
    return i


def q_bucket(q: float) -> int:
    """0: the touch up to a quarter-spread short of the mid ... 5: at or past the natural."""
    return _bucket(q, Q_EDGES)


def dte_bucket(dte: int) -> int:
    return max(0, _bucket(dte, DTE_EDGES) - 1)


def money_bucket(moneyness: float) -> int:
    return _bucket(abs(moneyness), MONEY_EDGES)


def tod_bucket(minute: int) -> int:
    return _bucket(minute, TOD_EDGES)


def cell(root: str, q: float, legs: int, dte: int, moneyness: float, minute: int) -> str:
    """The hazard table's key of one leg of a working order's minute (`legs` > 1: a package's leg)."""
    return (f"{str(root).upper()}|q{q_bucket(q)}|{'m' if legs > 1 else 's'}|d{dte_bucket(dte)}|k{money_bucket(moneyness)}"
            f"|t{tod_bucket(minute)}")


def size_cell(root: str, q: float, legs: int, dte: int) -> str:
    """The size table's key: contracts a fill at that level typically found beyond the queue."""
    return f"{str(root).upper()}|q{q_bucket(q)}|{'m' if legs > 1 else 's'}|d{dte_bucket(dte)}"


@dataclass
class FillModel:
    """A hazard table (cell -> per-minute probability) and a size table (size cell -> contracts). Empty:
    natural fills only. A conditional table also carries the same cells measured on adverse-or-flat
    next minutes (`hazard_adverse`) and on favourable ones (`hazard_favourable`): both or neither."""

    hazard: dict[str, float] = field(default_factory=dict)
    source: str = "default: natural only"
    meta: dict[str, Any] = field(default_factory=dict)
    size: dict[str, int] = field(default_factory=dict)
    hazard_adverse: dict[str, float] | None = None
    hazard_favourable: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if (self.hazard_adverse is None) != (self.hazard_favourable is None):
            raise ValueError("a conditional fill model needs both hazard_adverse and hazard_favourable")

    @property
    def conditional(self) -> bool:
        """True when passive fills draw against the hazard of the next minute's condition (the module docstring)."""
        return self.hazard_adverse is not None

    @property
    def version(self) -> str:
        if self.conditional:
            body: Any = {"adverse": CONDITIONAL, "hazard": self.hazard, "size": self.size,
                         "hazard_adverse": self.hazard_adverse, "hazard_favourable": self.hazard_favourable}
            return "fm-" + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
        if not self.hazard:
            return "natural-only"
        body = self.hazard if not self.size else {"hazard": self.hazard, "size": self.size}
        return "fm-" + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]

    def p(self, root: str, q: float, legs: Sequence[tuple[int, float]], minute: int, adverse: bool | None = None) -> float:
        """The per-minute hazard of a limit at `q` on a structure whose legs are (days to expiry,
        moneyness K/S - 1): 1 at or through the natural; 0 behind the touch, with any leg past
        MODELLED_DTE or a moneyness unknown, or where the table has no cell (the module docstring).
        `adverse` picks a conditional table's cells (True: the next minute moves against the order or
        stays flat; False: in its favour); None, or an unconditional table, reads `hazard`."""
        if q >= 1.0 - 1e-12:
            # At or through the real natural (still working only in a stress run) is no measured cell: under a
            # conditional table it keeps the unconditional rule, certain on an adverse-or-flat minute, never on another.
            return 0.0 if adverse is False and self.conditional else 1.0
        table = self.hazard if adverse is None or not self.conditional else (
            self.hazard_adverse if adverse else self.hazard_favourable)
        if not table or q < TOUCH - 1e-6 or not legs:
            return 0.0  # behind the touch: only the market coming through it fills it
        rates = []
        for dte, moneyness in legs:
            if int(dte) > MODELLED_DTE or not math.isfinite(moneyness):
                return 0.0
            single = float(table.get(cell(root, q, 1, dte, moneyness, minute), 0.0))
            if len(legs) == 1:
                return single
            rates.append(min(single, float(table.get(cell(root, q, 2, dte, moneyness, minute), 0.0))))
        return min(rates)

    def sizes(self, root: str, q: float, legs: Sequence[tuple[int, float]], ratios: Sequence[int]) -> list[int]:
        """Contracts of each leg one minute's passive fill may take at `q` (the leg's ratio, one
        structure, where the table does not say)."""
        out = []
        for (dte, _), ratio in zip(legs, ratios):
            known = self.size.get(size_cell(root, q, len(legs), dte))
            out.append(max(1, int(known)) if known is not None else int(ratio))
        return out

    @classmethod
    def from_json(cls, data: Mapping[str, Any], source: str = "") -> "FillModel":
        """A table as `calibrate.py` writes it. An `"adverse"` marker other than "conditional", or a
        conditional table without both conditional hazards, is refused (ValueError): a rule this engine
        does not know is never read as another one."""
        hazard = {str(k): float(v) for k, v in dict(data.get("hazard") or {}).items() if 0.0 <= float(v) <= 1.0}
        size = {str(k): int(v) for k, v in dict(data.get("size") or {}).items()
                if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 1}
        conditional: dict[str, Any] = {}
        marker = data.get("adverse")
        if marker is not None:
            if marker != CONDITIONAL:
                raise ValueError(f"unknown adverse-selection rule {marker!r} in the fill model")
            for name in ("hazard_adverse", "hazard_favourable"):
                if not isinstance(data.get(name), Mapping):
                    raise ValueError(f"a conditional fill model without {name}")
                conditional[name] = {str(k): float(v) for k, v in data[name].items() if 0.0 <= float(v) <= 1.0}
        return cls(hazard=hazard, source=source or str(data.get("source") or "file"), meta=dict(data.get("meta") or {}),
                   size=size, **conditional)

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "FillModel":
        """The fitted table from `path`, GYM_FILL_MODEL, the box's calibration path or the laptop's
        `.data/gym/fill_model.json`; the natural-only default when none exists."""
        candidates = [path] if path else [os.environ.get("GYM_FILL_MODEL"), *DEFAULT_PATHS,
                                         str(Path(__file__).resolve().parents[2] / ".data" / "gym" / "fill_model.json")]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return cls.from_json(json.loads(Path(candidate).read_text()), source=str(candidate))
        if path:
            raise FileNotFoundError(f"no fill model at {path}")
        return cls()


def draw(keys: Sequence[int], day: int, minute: int, side: str) -> float:
    """A uniform number in [0, 1) keyed by the contracts, the day, the minute and the side."""
    text = f"{SEED}|{int(day)}|{int(minute)}|{side}|{','.join(str(int(k)) for k in sorted(keys))}"
    return int.from_bytes(hashlib.blake2b(text.encode(), digest_size=8).digest(), "big") / 18446744073709551616.0


__all__ = ["FillModel", "draw", "cell", "size_cell", "q_bucket", "dte_bucket", "money_bucket", "tod_bucket", "SEED", "TOUCH",
           "MODELLED_DTE", "STRESS_HAZARD", "CONDITIONAL"]
