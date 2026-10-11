"""Synthetic panels for tests: never market data. Every package's tests build their evidence on these.

Owner: package C. STEP 0 STUB: every function raises NotImplementedError until C lands.

A synthetic panel is a whole `<root>` as the House holds it: E1's store for the REF symbols (through
`league.equity.synth.synthetic_store`: the one call of this package into it), the universe files with a fixed TEST
salt, and the panel through `store.write_panel`. Seeded and deterministic: the same arguments write the same bytes. No
2020 session exists in any of them. The price paths are seeded pseudo-random numbers on the true NYSE calendar
(`league.equity.store.nyse_sessions`): no real price, return or membership date is in them.

Evidence module (in the xs identity: `XS_EVIDENCE`'s extra, as `synth` is E1's).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Mapping, Sequence

#: The fixed salt of every synthetic panel (32 bytes; never the House's).
TEST_SALT = bytes(range(32))

_STUB = "league.xs.synth is a Step 0 stub: package C builds it (league/xs/E4_INTERFACES.md)"


def synthetic_panel(root: str | Path, *, n_assets: int = 60, start: dt.date = dt.date(2016, 1, 4),
                    end: dt.date = dt.date(2026, 10, 9), seed: int = 7, drift: float = 0.0, vol: float = 0.25,
                    churn: float = 0.05, splits: Mapping[int, tuple[dt.date, float]] | None = None,
                    dividends: Mapping[int, Sequence[tuple[dt.date, float]]] | None = None,
                    vanish: Sequence[tuple[int, dt.date]] = (), gate: bool = False,
                    as_of: dt.date | None = None) -> Path:
    """Write a synthetic panel at `root` and return it: `n_assets` member assets (aids from 100) with sector structure
    (each loads on one REF fund), `churn` of them leaving and joining the index a year, `splits` {aid: (day, factor)},
    `dividends` {aid: [(ex day, dollars)]}, `vanish` [(aid, last bar day)] (bars end while still a member). `gate`:
    write E1's GATE mark (so a capability can be minted on it). `as_of`: the day the adjustment=all series is fetched
    (default `end`): two panels that differ only in it hold the same history under two vintages, each rounded to the
    cent as the vendor's is."""
    raise NotImplementedError(_STUB)


def planted_panel(root: str | Path, *, edge_year: float = 0.08, signal: str = "reversal", **kwargs: Any) -> Path:
    """A `synthetic_panel` with a KNOWN residual edge: names ranked by `signal` ("reversal" | "momentum" | "low_vol")
    earn `edge_year` a year more than their cell-mates. `kwargs`: `synthetic_panel`'s."""
    raise NotImplementedError(_STUB)


def cent_panel(root: str | Path, *, n_assets: int = 50, **kwargs: Any) -> Path:
    """A `synthetic_panel` whose RAW prices sit exactly on the cent grid, with dividends: the panel the seal's
    adversary searches for a price level (`test_xs_seal.TheLevelCannotBeSearched`)."""
    raise NotImplementedError(_STUB)


def same_ctx_cases(root: str | Path, *, history: int, count: int = 20, seed: int = 0, window: str = "validation",
                   gate: Any = None) -> list[dict[str, Any]]:
    """THE I6 HELPER: `count` random decision days of `window`, each {day, index, gym (the Gym's `ctx.Inputs`),
    raw_rows, all_rows (the venue-shaped 1Day rows a live fetch of that day would return), columns (symbols), common
    (the keywords `ctx.inputs_from_fetch` needs: elig0, ids, dither_key, sector_perm, needs, the book facts)}, so that
    `ctx_bytes(build(case["gym"]))` equals `ctx_bytes(build(inputs_from_fetch(case["raw_rows"], case["all_rows"],
    day=case["day"], columns=case["columns"], **case["common"])))`. BOTH SIDES OF A CASE ARE BUILT UNDER ONE RUN KEY
    AND ONE AID SET (the live side's columns are REF, that day's members and two held names that have left the index),
    and at least one case straddles an index change."""
    raise NotImplementedError(_STUB)


__all__ = ["TEST_SALT", "synthetic_panel", "planted_panel", "cent_panel", "same_ctx_cases"]
