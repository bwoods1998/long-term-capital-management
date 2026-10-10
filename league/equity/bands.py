"""The equity lane's money bands: who reaches Probe, the pre-registered sizing-up rule and the EDM1 demotion.

TWO OWNERS, BY FUNCTION (league/equity/INTERFACES.md, "Ownership"): money owns `EquityRecord`, `sized_up`,
`sized_sleeve_share` and `edm1` (the pre-registered rules of the design's section 5, written before the first live
trade, as goal item 4 asks); swarm owns `next_band` and `band_for_row` (the band transition and the guard
`league.live.money.band_for` calls through `league/live/equity_hook.py`, A8.8). Each edits only its own functions.

Evidence isolation (A8.8): this module lives here, not in league/live/money.py; the live path reaches it only through
the hook. `table` is a `league.live.money.EquityTable` (read by attribute; this module imports nothing of league.live).

THE BANDS (the EquityBook moves them, writing through its families reader, league/equity/families.py):
- candidate -> probe: the family passed its lane's look (its row's `holdout_passed`) and an equity roster seat is free
  (`elane.roster`, league/swarm/bands.py `seating`): its sleeve is `probe.sleeve_share` x E (0.25, A5);
- probe -> sized: `sized_up` holds on its version's real closes: its sleeve is then `sized_sleeve_share` x E;
- probe | sized -> candidate, exits only and sticky for the version: `edm1` names why (EDM1), or the program's realized
  Probe net reached `demotion.program_loss_usd` (-$300; the swarm's `elane.program_loss_usd` retires it too).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping


@dataclass(frozen=True)
class EquityRecord:
    """One program version's real record (owner: money). `returns`: each real close's net return on its entry notional
    (net cash incl. fees and dividends / notional), in close order. `pnl`: their net cash summed (dollars). `bh_pnl`:
    the same-risk buy-and-hold over the same sessions (dollars; None when it cannot be priced). `probe_sessions`: whole
    sessions spent at Probe. `realized_net`: the program's realized Probe net (dollars). `twin_gaps_bp`: each priced
    close's live-minus-twin gap, basis points a side. `validation_r_sd`: the per-trade net-return sd of its Validation
    run (EDM1's sigma; None when unknown)."""

    n: int
    returns: tuple[float, ...]
    pnl: Decimal
    bh_pnl: Decimal | None
    probe_sessions: int
    realized_net: Decimal
    twin_gaps_bp: tuple[float, ...] = field(default_factory=tuple)
    validation_r_sd: float | None = None


def sized_up(record: EquityRecord, table: Any) -> tuple[bool, str]:
    """(money) THE SIZING-UP RULE: True when ALL hold on the version's real closes: n >= `sized.min_trades` (20); mean
    net return > 0 with its one-sided `sized.confidence` (80%) lower bound > 0; pnl beats `bh_pnl` when
    `sized.beat_bh` (an unpriced buy-and-hold fails it); `probe_sessions` >= `sized.min_probe_sessions` (5). The reason
    names the first that fails (or the figures that passed)."""
    raise NotImplementedError("money: league/equity/bands.py sized_up")


def sized_sleeve_share(record: EquityRecord, table: Any) -> Decimal:
    """(money) A Sized program's sleeve share of E: `sized.kelly_fraction` (quarter) Kelly on the lower bound of its
    mean net return, at most `sized.sleeve_share` (0.50), never below `probe.sleeve_share` (a Sized program never
    trades smaller than a Probe)."""
    raise NotImplementedError("money: league/equity/bands.py sized_sleeve_share")


def edm1(record: EquityRecord, table: Any) -> str | None:
    """(money) EDM1, why the version goes to exits only (sticky), or None: n >= `demotion.min_trades` (10) and the
    summed returns < -`demotion.z` (1.645) x sigma x sqrt(n) (sigma: `validation_r_sd`, else the record's own sd, else
    the rule's fallback); `realized_net` <= `demotion.program_loss_usd` (-300); the mean twin gap > `demotion.twin_gap_bp`
    (15) a side over >= `demotion.twin_min_closes` (5) priced closes."""
    raise NotImplementedError("money: league/equity/bands.py edm1")


def next_band(row: Mapping[str, Any], record: EquityRecord | None, table: Any, *, seat_free: bool,
              sticky: str | None = None) -> tuple[str, str]:
    """(swarm) The band an equity family should be in now, and why: "candidate" (no real entries), "probe" or
    "sized". `row`: its equity families row (league/equity/families.py: band, lane, holdout_passed, version, ...).
    `sticky`: a recorded EDM1 demotion of this version (it stays "candidate"). Order: not passed its look -> candidate;
    sticky or `edm1` -> candidate; a Candidate without a free seat -> candidate; a Candidate with one -> probe; a Probe
    with `sized_up` -> sized; else as it is."""
    raise NotImplementedError("swarm: league/equity/bands.py next_band")


def band_for_row(row: Mapping[str, Any]) -> tuple[str, str]:
    """(swarm) What `league.live.money.band_for` answers for an equity-lane row (through
    `league.live.equity_hook.band_for`): the row's band unchanged, with the reason "an equity-lane family: its band is
    the EquityBook's (league/equity/bands.py)". The options path never moves an equity family's band."""
    raise NotImplementedError("swarm: league/equity/bands.py band_for_row")


__all__ = ["EquityRecord", "sized_up", "sized_sleeve_share", "edm1", "next_band", "band_for_row"]
