"""The equity lane's money bands: who reaches Probe, the pre-registered sizing-up rule and the EDM1 demotion.

TWO OWNERS, BY FUNCTION (league/equity/INTERFACES.md, "Ownership"): money owns `EquityRecord`, `sized_up`,
`sized_sleeve_share` and `edm1` (the pre-registered rules of the design's section 5, written before the first live
trade, as goal item 4 asks); swarm owns `next_band` and `band_for_row` (the band transition and the guard
`league.live.money.band_for` calls through `league/live/equity_hook.py`, A8.8). Each edits only its own functions.

Evidence isolation (A8.8): this module lives here, not in league/live/money.py; the live path reaches it only through
the hook. `table` is a `league.live.money.EquityTable` (read by attribute; this module imports nothing of league.live).

THE BANDS (the EquityBook moves them, writing through its families reader, league/equity/families.py):
- candidate -> probe: the family passed its lane's look (its row's `holdout_passed`) and an equity roster seat is free
  (`elane.roster`, league/swarm/bands.py `seating`; at most `probe.max_programs` live programs): its sleeve is
  `probe.sleeve_share` x E (the seats and the sleeve are the table's two numbers, set together: release E5-S, the
  constitution's `probe` comment);
- probe -> sized: `sized_up` holds on its version's real closes: its sleeve is then `sized_sleeve_share` x E (never
  below the Probe's, at most the larger of the Probe sleeve and `sized.sleeve_share`). PARKED at the table in force
  (`sized.min_trades` 1000): no equity program is Sized, so every equity close stays in the loss budget's tallies;
- probe | sized -> candidate, exits only and sticky for the version: `edm1` names why (EDM1), or the program's realized
  Probe net reached `demotion.program_loss_usd` (-$300; the swarm's `elane.program_loss_usd` retires it too).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from typing import Any, Mapping

from .. import stats

#: EDM1's sigma when the version has no Validation sd (money's): the record's own per-trade sd once it has this many
#: closes, as DM1 reads a forward record's (league/live/money.py `DM1_SIGMA_MIN_TRADES`)...
EDM1_SIGMA_MIN_TRADES = 10
#: ...else this fallback, a net return of 2% of notional a trade: a rule's round figure, chosen and not measured. A
#: smaller sigma demotes sooner, so it errs toward exits only.
EDM1_FALLBACK_SIGMA = 0.02
#: An sd of its own at or under this is no sd (rounding noise of equal returns; the screen's own floor for an sd, 1e-12).
EDM1_SIGMA_FLOOR = 1e-12
#: A Sized sleeve share is floored to this many places (a share of E).
SLEEVE_PLACES = Decimal("0.0001")


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


def _returns(record: EquityRecord) -> list[float]:
    """The record's per-close net returns as floats; ValueError when they are not `n` finite numbers (a record that
    cannot be read sizes nothing up and is no evidence for or against a demotion: the caller records why)."""
    returns = []
    for value in record.returns:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"an equity record's return is not a finite number: {value!r}")
        returns.append(float(value))
    if isinstance(record.n, bool) or not isinstance(record.n, int) or record.n != len(returns):
        raise ValueError(f"an equity record of n={record.n!r} carries {len(returns)} returns")
    return returns


def _positive_sd(value: Any) -> float | None:
    """A Validation sd as a family's state carries it: a finite int or float above zero, else None (absent)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    x = float(value)
    return x if math.isfinite(x) and x > 0 else None


def edm1_sigma(record: EquityRecord, returns: list[float] | None = None) -> tuple[float, str]:
    """(money) EDM1's sigma and where it came from: the per-trade net-return sd of the version's Validation run
    (`validation_r_sd`), else the record's own once it has `EDM1_SIGMA_MIN_TRADES` closes, else `EDM1_FALLBACK_SIGMA`."""
    sd = _positive_sd(record.validation_r_sd)
    if sd is not None:
        return sd, "the per-trade sd of its Validation run"
    returns = _returns(record) if returns is None else returns
    n = len(returns)
    if n >= max(EDM1_SIGMA_MIN_TRADES, 2):
        # `math.fsum`, and a floor: ten equal returns must read as NO sd of its own on every Python. The built-in `sum`
        # is exact for such a list only since 3.12; on 3.11 it left an sd of 2e-18, which EDM1 would have used as sigma.
        mean = math.fsum(returns) / n
        own = _positive_sd(math.sqrt(math.fsum((r - mean) ** 2 for r in returns) / (n - 1)))
        if own is not None and own > EDM1_SIGMA_FLOOR:
            return own, f"the sd of its own {n} real closes"
    return EDM1_FALLBACK_SIGMA, "the rule's fallback (no Validation sd, no usable sd of its own)"


def sized_up(record: EquityRecord, table: Any) -> tuple[bool, str]:
    """(money) THE SIZING-UP RULE: True when ALL hold on the version's real closes: n >= `sized.min_trades` (20 as
    pre-registered; THE STEP IS PARKED at the table in force, whose row is 1000, until Sized closes count in the loss
    budget: the constitution's `sized` comment, so no equity program is Sized); mean
    net return > 0 with its one-sided `sized.confidence` (80%) lower bound > 0; pnl beats `bh_pnl` when
    `sized.beat_bh` (an unpriced buy-and-hold fails it); `probe_sessions` >= `sized.min_probe_sessions` (5). The reason
    names the first that fails (or the figures that passed). A record with no spread at all (every return the same) is
    one the t-bound cannot judge (`stats.mean_bounds`), and never sizes up."""
    returns = _returns(record)
    n, need = record.n, int(table.sized_min_trades)
    if n < need:
        return False, f"{n} real closes, under the {need} sizing up needs"
    bounds = stats.mean_bounds(returns, 1.0 - float(table.sized_confidence))
    if bounds is None or not bounds["sd"] > 0:
        return False, f"its {n} real closes have no spread: the {table.sized_confidence:.0%} bound cannot judge them"
    mean, lcb = bounds["mean"], bounds["lcb"]
    if not mean > 0:
        return False, f"its mean net return {mean:.5f} over {n} real closes is not above zero"
    if not lcb > 0:
        return False, (f"its {table.sized_confidence:.0%} lower bound {lcb:.5f} (mean {mean:.5f}, {n} real closes) is not "
                       "above zero")
    if table.sized_beat_bh:
        if record.bh_pnl is None:
            return False, "the same-risk buy-and-hold over the same sessions could not be priced, so it cannot be beaten"
        if not record.pnl > record.bh_pnl:
            return False, (f"its P&L ${record.pnl:.2f} does not beat the same-risk buy-and-hold's ${record.bh_pnl:.2f} over "
                           "the same sessions")
    if record.probe_sessions < int(table.sized_min_probe_sessions):
        return False, f"{record.probe_sessions} sessions at Probe, under the {table.sized_min_probe_sessions} it needs"
    beside = f", beating the buy-and-hold's ${record.bh_pnl:.2f}" if table.sized_beat_bh else ""
    return True, (f"{n} real closes, mean net return {mean:.5f}, {table.sized_confidence:.0%} lower bound {lcb:.5f}, P&L "
                  f"${record.pnl:.2f}{beside}, after {record.probe_sessions} sessions at Probe")


def sized_sleeve_share(record: EquityRecord, table: Any) -> Decimal:
    """(money) A Sized program's sleeve share of E: `sized.kelly_fraction` (quarter) Kelly on the lower bound of its
    mean net return (`stats.quarter_kelly`: fraction x lcb / variance of the per-close net return), at most
    `sized.sleeve_share` (0.50), never below `probe.sleeve_share` (a Sized program never trades smaller than a Probe).
    Floored to `SLEEVE_PLACES`. A record that sizes nothing (no bound above zero) gets the Probe's share.

    WHERE THE PROBE SLEEVE IS THE CAP ITSELF (0.50: the captain's A20, Oct 11, 2026) the cap EQUALS the floor, so the
    answer is the Probe's for every record: a Sized program keeps the Probe sleeve and sizes nothing up. Under a
    smaller Probe sleeve (release E5-S: the seats and the sleeve are set together) the answer is between the Probe's
    and the cap. The rule itself is unchanged at any sleeve (league/tests/test_equity_bands_money.py holds both); THE
    STEP IS PARKED either way (`sized.min_trades` 1000)."""
    floor, cap = Decimal(table.probe_sleeve_share), Decimal(table.sized_sleeve_share)
    returns = _returns(record)
    bounds = stats.mean_bounds(returns, 1.0 - float(table.sized_confidence)) if len(returns) >= 2 else None
    kelly = 0.0
    if bounds is not None:
        kelly = stats.quarter_kelly(bounds["lcb"], bounds["sd"] ** 2, fraction=float(table.sized_kelly_fraction),
                                    cap=float(cap) if cap > 0 else 0.0)
    share = Decimal(repr(kelly)).quantize(SLEEVE_PLACES, rounding=ROUND_DOWN)
    return max(floor, min(share, cap))


def edm1(record: EquityRecord, table: Any) -> str | None:
    """(money) EDM1, why the version goes to exits only (sticky), or None: n >= `demotion.min_trades` (10) and the
    summed returns < -`demotion.z` (1.645) x sigma x sqrt(n) (sigma `edm1_sigma`: `validation_r_sd`, else the record's
    own sd, else the rule's fallback); `realized_net` <= `demotion.program_loss_usd` (-300); the mean twin SHORTFALL
    above `demotion.twin_gap_bp` (15) a side over >= `demotion.twin_min_closes` (5) priced closes. A twin gap is the
    close's live net return minus its replay twin's, in basis points a side (league/ops/twins.py): negative when the
    fills were worse than the replay's, so the shortfall is minus their mean; fills better than the replay never
    demote."""
    returns = _returns(record)
    n = record.n
    if n >= int(table.demotion_min_trades):
        sigma, source = edm1_sigma(record, returns)
        line = -float(table.demotion_z) * sigma * math.sqrt(n)
        total = sum(returns)
        if total < line:
            return (f"EDM1: its {n} real closes returned {total:.4f} of notional in sum, below -{table.demotion_z} x sigma "
                    f"{sigma:.4f} x sqrt({n}) = {line:.4f} (sigma: {source}): exits only")
    if Decimal(record.realized_net) <= Decimal(table.program_loss_usd):
        return (f"EDM1: its realized Probe net ${Decimal(record.realized_net):.2f} reached the program loss line "
                f"${Decimal(table.program_loss_usd):.2f}: exits only")
    gaps = []
    for gap in record.twin_gaps_bp:
        if isinstance(gap, bool) or not isinstance(gap, (int, float)) or not math.isfinite(float(gap)):
            raise ValueError(f"an equity record's twin gap is not a finite number: {gap!r}")
        gaps.append(float(gap))
    if gaps and len(gaps) >= int(table.twin_min_closes):
        shortfall = -sum(gaps) / len(gaps)
        if shortfall > float(table.twin_gap_bp):
            return (f"EDM1: its fills ran {shortfall:.1f} bp a side below their replay twins on average over {len(gaps)} "
                    f"priced closes (bound {table.twin_gap_bp} bp): not consistent with the replay, exits only")
    return None


def next_band(row: Mapping[str, Any], record: EquityRecord | None, table: Any, *, seat_free: bool,
              sticky: str | None = None) -> tuple[str, str]:
    """(swarm) The band an equity family should be in now, and why: "candidate" (no real entries), "probe" or
    "sized". `row`: its equity families row (league/equity/families.py: band, lane, holdout_passed, version, ...).
    `sticky`: a recorded EDM1 demotion of this version (it stays "candidate"). Order: not passed its look -> candidate;
    sticky or `edm1` -> candidate; a Candidate without a free seat -> candidate; a Candidate with one -> probe; a Probe
    with `sized_up` -> sized; else as it is."""
    band = str(row.get("band") or "")
    if not row.get("holdout_passed"):
        return "candidate", "it has not passed its lane's sealed look"
    if sticky:
        return "candidate", f"exits only, sticky for the version: {sticky}"
    if record is not None:
        why = edm1(record, table)
        if why:
            return "candidate", f"EDM1: {why}"
    if band == "candidate":
        if not seat_free:
            return "candidate", "waiting for an equity roster seat (elane.roster)"
        return "probe", "passed its lane's sealed look and holds an equity roster seat"
    if band == "probe":
        if record is not None:
            up, why = sized_up(record, table)
            if up:
                return "sized", why
            return "probe", why
        return "probe", "at Probe (no real close yet)"
    if band == "sized":
        return "sized", "Sized"
    return "candidate", f"not a live band ({band or 'none'}): no real entries"


def band_for_row(row: Mapping[str, Any]) -> tuple[str, str]:
    """(swarm) What `league.live.money.band_for` answers for an equity-lane row (through
    `league.live.equity_hook.band_for`): the row's band unchanged, with the reason "an equity-lane family: its band is
    the EquityBook's (league/equity/bands.py)". The options path never moves an equity family's band."""
    return str((row or {}).get("band") or ""), "an equity-lane family: its band is the EquityBook's (league/equity/bands.py)"


__all__ = ["EquityRecord", "sized_up", "sized_sleeve_share", "edm1", "next_band", "band_for_row"]
