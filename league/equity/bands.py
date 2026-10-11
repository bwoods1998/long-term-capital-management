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

THE SEAT RULE (release E5-A; the captain's A24; the constitution's `equity_money.probe.seat`, read here by
`seat_settings`, never by league/live/money.py). Owner: swarm. Pure functions; the EquityBook applies them
(league/equity/live.py `_seat_bands`) and is THE ONE SOURCE of who holds a seat and who waits.
- "first-come" (the rollback): release E5-S's behaviour exactly; nothing below is called.
- "activity-1-free" (in force): a FREE seat goes to the best-ranked waiting passed program (`seat_order`): not
  idle-flagged before idle-flagged, then the higher K, then the earlier look pass, then the family id. K (`seat_k`) is
  the smaller of the program's Validation close days and its Train-era close days per `K_PER_SESSIONS` sessions
  (`close_days`, `seat_counts`: a day counts when the lots closed on it sum to at least `k_floor` of the sleeve, less
  `K_TOLERANCE`, the engine's rounding of a lot's weight). K reads no P&L and no sealed window; the swarm writes its
  two counts beside the look, once (league/swarm/elane.py `SEAT_KEY`). A program whose counts cannot be read ranks
  after every program whose counts can.
- THE IDLE SEAT (`seat_idle`): a seated program that is flat and has had no asked buy for `idle_sessions` seated
  sessions. It keeps its seat while nobody waits; when an unflagged program waits, ONE idle program a decision day
  yields (`seat_yielder`: the lowest K, then the latest seated, the latest pass, the higher id) and is flagged.
- No function here stops a program that trades, sells a lot or names an exit: the rule only orders who may OPEN next.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Iterable, Mapping, Sequence

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


# ----------------------------------------------------------------------------------------------------- the seat rule
#: `equity_money.probe.seat.rule`'s values (`league.constitution.EQUITY_MONEY_CHOICES`; a test holds the two equal).
FIRST_COME = "first-come"
ACTIVITY_FREE = "activity-1-free"
SEAT_RULES = (ACTIVITY_FREE, FIRST_COME)
#: A close day's floor is read as `k_floor` minus this (A24): the engine writes a lot's weight rounded to eight places
#: of a notional floored to whole millionths of a share, so a lot bought with a share of exactly the floor weighs a
#: hair under it (league/equity/engine.py `_lot`).
K_TOLERANCE = Decimal("0.0005")
#: K is a count of close days per this many sessions (the Validation year's length, as the rule states it).
K_PER_SESSIONS = 250
#: The engine's places of a lot's weight (league/equity/engine.py `_lot`: round(notional / capital, 8)).
WEIGHT_PLACES = Decimal("0.00000001")


@dataclass(frozen=True)
class SeatSettings:
    """`equity_money.probe.seat` as the book reads it: `rule` (one of `SEAT_RULES`), `k_floor` (a share of the sleeve)
    and `idle_sessions` (seated sessions)."""

    rule: str
    k_floor: Decimal
    idle_sessions: int

    @property
    def first_come(self) -> bool:
        return self.rule == FIRST_COME


#: What a table with no readable seat block is read as: first come (the rollback value, release E5-S's behaviour). A
#: block that cannot be read never moves a seat by a rule nobody can state. (The constitution's own check,
#: `equity_money_problems`, refuses such a table before any of this runs.)
SEAT_FALLBACK = SeatSettings(FIRST_COME, Decimal("0.25"), 10)


def seat_settings(constitution: Mapping[str, Any] | None = None) -> SeatSettings:
    """(swarm) THE SEAT RULE's row, `equity_money.probe.seat` of `constitution` (None: the one in force), read here so
    that league/live/money.py (inside the options execution fingerprint) never has to learn it. `SEAT_FALLBACK` when
    the block is absent or any of its three values cannot be read."""
    if constitution is None:
        from ..constitution import CONSTITUTION as constitution  # noqa: N811
    try:
        block = constitution["equity_money"]["probe"]["seat"]
        rule, sessions = block["rule"], block["idle_sessions"]
        floor = Decimal(str(block["k_floor"]))
        if rule not in SEAT_RULES or isinstance(sessions, bool) or not isinstance(sessions, int) or sessions < 1 \
                or not floor.is_finite() or not Decimal(0) < floor <= 1:
            return SEAT_FALLBACK
        return SeatSettings(str(rule), floor, int(sessions))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return SEAT_FALLBACK


def close_days(lots: Iterable[Mapping[str, Any]], *, floor: Decimal) -> int:
    """(swarm) K's count over ONE run's lots (league/equity/engine.py's `lots` rows): the number of days on which the
    lots that closed (`exit_day`; a lot still open at the run's end has none and counts nowhere) have entry weights
    (`weight`: entry notional over the run's capital, eight places) summing to at least `floor` - `K_TOLERANCE`. It
    reads a lot's size and its exit day and nothing else: no price, no return, no P&L. Decimal sums, so the count is
    the same on every Python. ValueError for a row whose weight is no finite number."""
    need = Decimal(floor) - K_TOLERANCE
    by_day: dict[str, Decimal] = {}
    for lot in lots:
        day = lot.get("exit_day")
        if day is None:
            continue
        weight = lot.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float, Decimal)):
            raise ValueError(f"a lot's weight is not a number: {weight!r}")
        value = Decimal(repr(weight)) if isinstance(weight, float) else Decimal(weight)
        if not value.is_finite():
            raise ValueError(f"a lot's weight is not finite: {weight!r}")
        by_day[str(day)] = by_day.get(str(day), Decimal(0)) + value.quantize(WEIGHT_PLACES)
    return sum(1 for total in by_day.values() if total >= need)


def run_sessions(result: Mapping[str, Any]) -> int:
    """The sessions one run covered: its `daily` rows (one a run session), else its summary's `days`."""
    daily = result.get("daily")
    if isinstance(daily, (list, tuple)):
        return len(daily)
    days = (result.get("summary") or {}).get("days") if isinstance(result.get("summary"), Mapping) else None
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("a run names no sessions")
    return int(days)


def seat_counts(validation: Mapping[str, Any], train: Sequence[Mapping[str, Any]], *, floor: Decimal) -> dict[str, Any]:
    """(swarm) K's TWO COUNTS from the runs a look already makes: the recorded Validation run's result and the
    Train-era runs' results (league/equity/runner.py `Isolated.validation`, `segments`: unsealed windows, both). ->
    {"floor", "validation": {"close_days", "sessions"}, "train": {"close_days", "sessions"}}, whole numbers only. A
    Train-era run with no data ("no_data": the program has no history there, the screen's own reading) adds neither
    days nor sessions; any other run that did not end "ok" is a ValueError (a partial series is never counted)."""
    def one(result: Mapping[str, Any]) -> tuple[int, int]:
        return close_days(result.get("lots") or [], floor=floor), run_sessions(result)

    if str(validation.get("status") or "") != "ok":
        raise ValueError(f"the Validation run ended {validation.get('status')!r}")
    v_days, v_sessions = one(validation)
    t_days = t_sessions = 0
    for result in train:
        status = str(result.get("status") or "")
        if status == "no_data":
            continue
        if status != "ok":
            raise ValueError(f"a Train-era run ended {status!r}")
        days, sessions = one(result)
        t_days, t_sessions = t_days + days, t_sessions + sessions
    return {"floor": str(floor), "validation": {"close_days": v_days, "sessions": v_sessions},
            "train": {"close_days": t_days, "sessions": t_sessions}}


def seat_k(activity: Any) -> Fraction | None:
    """(swarm) K, exactly: the smaller of the Validation close days and the Train-era close days per `K_PER_SESSIONS`
    sessions, from `seat_counts`' record (as a family's row carries it, `seat_activity`); None when it cannot be read
    (no record, a count that is no whole number, no Train-era session). A Fraction, so two programs compare the same
    on every Python and a tie is a tie."""
    if not isinstance(activity, Mapping):
        return None
    try:
        v, t = activity["validation"], activity["train"]
        counts = (v["close_days"], t["close_days"], t["sessions"])
    except (KeyError, TypeError):
        return None
    if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in counts) or counts[2] < 1:
        return None
    return min(Fraction(counts[0]), Fraction(counts[1] * K_PER_SESSIONS, counts[2]))


@dataclass(frozen=True)
class SeatFacts:
    """One passed program as the seat rule reads it. `k`: `seat_k` (None: unreadable). `passed_at`: when its look
    passed (epoch seconds; None: unknown, after every known time). `flagged`: it yielded an idle seat and has not been
    seated since. For a seated program: `seat_day` (the decision day it took its seat), `seated_sessions` (sessions
    since), `quiet_sessions` (sessions since its last asked buy; None: it never asked) and `flat` (no lot, no working
    order, no planned or sent intent)."""

    family: str
    k: Fraction | None = None
    passed_at: float | None = None
    flagged: bool = False
    seeded: bool = False
    seat_day: str = ""
    seated_sessions: int = 0
    quiet_sessions: int | None = None
    flat: bool = False


def _pass_key(p: SeatFacts) -> tuple:
    return (p.passed_at is None, p.passed_at if p.passed_at is not None else 0.0, p.family)


def seat_key(p: SeatFacts) -> tuple:
    """(swarm) THE RANK of a waiting program, smallest first: not idle-flagged before idle-flagged; a readable K before
    an unreadable one; the higher K; the earlier look pass; the family id. Total: no two programs compare equal."""
    return (p.flagged, p.k is None, -(p.k if p.k is not None else Fraction(0)), *_pass_key(p))


def seat_order(waiting: Iterable[SeatFacts]) -> list[SeatFacts]:
    """(swarm) The waiting programs, best-ranked first (`seat_key`)."""
    return sorted(waiting, key=seat_key)


def seat_idle(p: SeatFacts, settings: SeatSettings) -> bool:
    """(swarm) THE IDLE SEAT's test of a seated program at a decision: it has held its seat for at least
    `idle_sessions` sessions, it is flat, and it has had no asked buy in the last `idle_sessions` sessions (asked: a
    buy reached the venue, or the loss budget cut or refused it; the book says which, `EquityBook._last_ask`)."""
    n = int(settings.idle_sessions)
    return bool(p.flat and p.seated_sessions >= n and (p.quiet_sessions is None or p.quiet_sessions >= n))


def seat_yielder(idle: Iterable[SeatFacts]) -> SeatFacts | None:
    """(swarm) Which of the idle seated programs yields when an unflagged program waits (one a decision day): the
    lowest K (an unreadable K lowest of all), then the latest seated, then the latest look pass, then the higher id.
    None when none is idle."""
    def key(p: SeatFacts) -> tuple:
        return (p.k is not None, p.k if p.k is not None else Fraction(0), _neg(p.seat_day), p.passed_at is not None,
                -(p.passed_at or 0.0), _neg(p.family))

    rows = list(idle)
    return min(rows, key=key) if rows else None


def _neg(text: str) -> tuple:
    """A string's sort key reversed (the later day, the higher id, first)."""
    return tuple(-ord(c) for c in str(text)) + (1,)


def seat_plan(holders: Sequence[SeatFacts], waiting: Sequence[SeatFacts], *, seats: int, settings: SeatSettings,
              late: bool = False, yielded_today: bool = False) -> dict[str, Any]:
    """(swarm) THE PLAN OF ONE BAND SYNC, pure (the conformance vectors, league/tests/fixtures/equity_seat_vectors.json,
    are its inputs and answers; a second implementation of the rule must give them all). `holders`: the seated
    programs AFTER the sync's demotions; `waiting`: the passed programs with no seat that are not sticky; `seats`: the
    seats there are; `late`: the seating pass (free seats only); `yielded_today`: a seat already yielded at this
    decision day. -> {"idle": the idle holders, "yields": the one that yields (or None), "for": the best-ranked
    unflagged waiting program it yields to (named as the reason, not as the seat's owner), "queue": the waiting
    programs best first (the yielded one among them, flagged), "seat": the first of the queue that the free seats
    take, in order}. THE BOOK APPLIES IT AND MAY FALL THROUGH: a seating that does not take passes to the next of
    the queue. Under "first-come" the queue is by pass time and nothing is idle (the book does not call this then: its
    band sync is release E5-S's own; the answer is here for the vectors).

    WHAT IT NEVER SAYS: that a program holding a lot, a working order or a planned intent leaves its seat (an idle
    program is flat by definition), or that a better-ranked arrival takes a held seat (outranking is not adopted)."""
    holders, waiting = list(holders), list(waiting)
    if settings.first_come:
        queue = sorted(waiting, key=_pass_key)
        free = max(0, int(seats) - len(holders))
        return {"idle": [], "yields": None, "for": None, "queue": [p.family for p in queue],
                "seat": [p.family for p in queue[:free]]}
    idle = [] if late else [p for p in holders if seat_idle(p, settings)]
    fresh = [p for p in waiting if not p.flagged]
    goes = taker = None
    if idle and fresh and len(holders) <= int(seats) and not yielded_today:
        goes, taker = seat_yielder(idle), seat_order(fresh)[0]
        holders = [p for p in holders if p.family != goes.family]
        waiting = waiting + [SeatFacts(family=goes.family, k=goes.k, passed_at=goes.passed_at, flagged=True,
                                       seeded=goes.seeded)]
    queue = seat_order(waiting)
    free = max(0, int(seats) - len(holders))
    return {"idle": [p.family for p in idle], "yields": goes.family if goes else None,
            "for": taker.family if taker else None, "queue": [p.family for p in queue],
            "seat": [p.family for p in queue[:free]]}


def band_for_row(row: Mapping[str, Any]) -> tuple[str, str]:
    """(swarm) What `league.live.money.band_for` answers for an equity-lane row (through
    `league.live.equity_hook.band_for`): the row's band unchanged, with the reason "an equity-lane family: its band is
    the EquityBook's (league/equity/bands.py)". The options path never moves an equity family's band."""
    return str((row or {}).get("band") or ""), "an equity-lane family: its band is the EquityBook's (league/equity/bands.py)"


__all__ = ["EquityRecord", "sized_up", "sized_sleeve_share", "edm1", "next_band", "band_for_row", "FIRST_COME",
           "ACTIVITY_FREE", "SEAT_RULES", "K_TOLERANCE", "K_PER_SESSIONS", "SeatSettings", "SEAT_FALLBACK",
           "seat_settings", "close_days", "run_sessions", "seat_counts", "seat_k", "SeatFacts", "seat_key", "seat_order",
           "seat_idle", "seat_yielder", "seat_plan"]
