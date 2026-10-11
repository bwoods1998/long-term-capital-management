"""The panel lane's constants, each a rule, and its quiet windows. Owner: package C (C0 delivers this module whole).

STEP 0 STUB: the constants are the contract (every package imports them from here from day one) and `rounding_bound`
is built; `quiet`, `rebalance_session` and `decision_due` raise NotImplementedError until C0 lands. Changing a constant here is a new xs identity or a new receipt, never a
setting (E4-SPEC 12).

WHERE A FIGURE COMES FROM. "PREREG" is the pinned pre-registration XSCREEN-1 (revision 2, sha256 c46aec17...): where
it and E4-SPEC disagree on the program contract, the residual and its cells, the stress leg, the House exit law or the
gate, the pre-registration wins, and the line says so. Everything else is E4-SPEC section 5 and 6.1.

Evidence module (in the xs identity). Standard library only.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from decimal import Decimal

# ------------------------------------------------------------------------------------------------ sessions and spans
#: D1. What the panel store holds: span A and span B. NO 2020 ROW EXISTS (the reserve): `store.write_panel` refuses one.
SPANS: tuple[tuple[str, dt.date, dt.date | None], ...] = (("A", dt.date(2016, 1, 4), dt.date(2019, 12, 31)),
                                                         ("B", dt.date(2021, 1, 4), None))
#: D1. The panel's Train RUN sessions: 754 and 753 sessions. 2016 and 2021 are history only (look-back, never a run
#: session); both segments lie inside E1's `league.equity.config.TRAIN_ERA_SEGMENTS`.
TRAIN_SEGMENTS: tuple[tuple[dt.date, dt.date], ...] = ((dt.date(2017, 1, 3), dt.date(2019, 12, 31)),
                                                       (dt.date(2022, 1, 3), dt.date(2024, 12, 31)))
TRAIN_YEARS = (2017, 2018, 2019, 2022, 2023, 2024)
HISTORY_YEARS = (2016, 2021)
#: The year no panel session, fetch or file ever names.
RESERVE_YEARS = (2020,)

# ------------------------------------------------------------------------------------------------------ the columns
#: D2. The REF columns of every panel slice (aids 1..12, never members), in the store's column order.
REF = ("SPY", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")
#: PREREG 3.2: the sector funds IN THE ORDER THE SECTOR RULE READS THEM (a name's sector code is its fund's index here,
#: 0..10, and a tie goes to the first). Not `REF`'s order: `FUND_COLUMNS` maps one onto the other.
FUNDS = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC")
#: The `REF` column of each fund of `FUNDS`, and of the market (SPY).
FUND_COLUMNS = tuple(REF.index(s) for s in FUNDS)
MARKET_COLUMN = REF.index("SPY")
#: D4. One class a company: the eligible class is chosen at each month's first session (the higher median raw dollar
#: volume over the 63 sessions through the session before it; ties: the lower aid) and held for the month.
CLASS_PAIRS = (("GOOG", "GOOGL"), ("FOX", "FOXA"), ("NWS", "NWSA"), ("DISCA", "DISCK"), ("UA", "UAA"))
CLASS_SESSIONS = 63

# ------------------------------------------------------------------------------- the program contract (PREREG C-XS-1)
#: C2. A target holds 0 names (all cash) or `MIN_NAMES`..NEEDS max_names, each weight in (0, `MAX_WEIGHT`], sum <= 1.
MIN_NAMES = 5
#: The contract's ceiling; the lane's cap is the setting `elane.panel.max_names` (12).
MAX_NAMES = 40
MAX_WEIGHT = 0.20
#: NEEDS history, in sessions (PREREG allows up to 504; the live fetch is 253 sessions: narrower, never wider).
MIN_HISTORY = 20
MAX_HISTORY = 252
#: NEEDS max_hold_sessions: 5..60.
MIN_HOLD_CAP = 5
MAX_HOLD_CAP = 60
#: D9. The decision schedules a program may declare (PREREG C4 allows any session; a daily schedule is refused here).
REBALANCE = ("weekly", "monthly")
#: C3, THE KEEP RULE's order cap: at most 12 buys and 12 sells a decision. A target that needs more is refused WHOLE
#: and the decision is a hold (PREREG; E4-SPEC's "orders past the cap are dropped" is superseded).
MAX_BUYS = 12
MAX_SELLS = 12
MAX_ORDERS = MAX_BUYS + MAX_SELLS
#: C3, C8. The Gym sleeve E0: `league.equity.config.SLEEVE_USD`'s figure (PREREG; E4-SPEC said 500: superseded, the
#: stress leg charges the smaller live sleeve's fee instead). A lot of weight w is bought for w x E0; nothing compounds.
XS_SLEEVE_USD = Decimal("1000")
#: A name's smallest order, E1's `MIN_ORDER_USD`.
MIN_NAME_USD = Decimal("10")
#: D11. E1's `sizing.size_entry` arguments for a panel entry: class "stock", 20% of the sleeve, open risk at 0.40.
POSITION_SHARE = Decimal("0.20")
RISK_WEIGHT = Decimal("0.40")

# ------------------------------------------------------------------------------- the eligible set and the strata
#: The sessions a decision reads: 253 closes, 252 returns (PREREG 3.2's window W(d)).
DERIVE_SESSIONS = 253
WINDOW = 252
#: PREREG 3.2: beta and the sector need at least this many valid returns in W(d) (E4-SPEC said 60: superseded).
MIN_VALID = 200
#: PREREG 3.2: mom = c[d - 21] / c[d - 252] - 1.
MOM_SKIP = 21
MOM_BACK = 252
#: PREREG 3.1: a name is eligible at d only while it is an index member on d, d + 1 and d + 2.
MEMBER_AHEAD = 2
#: PREREG C1: rel_volume is a session's volume over the median of the name's own trailing 63 sessions.
REL_VOLUME_SESSIONS = 63
#: PREREG 3.3, THE REGISTERED STRATUM (rung R0): (beta groups, momentum groups) by the sector's eligible count, as
#: ((minimum count, (nb, nm)), ...) highest first; a sector under `MIN_CELL` names gives them to the pooled cell
#: `SMALL_CELL`. R1 is the one rung the ladder may fall back to (the receipt names the rung in force; `screen`
#: refuses any other). A cell's id is `CELL_SECTOR` x sector + `CELL_BETA` x beta group + momentum group.
RUNGS: dict[str, tuple[tuple[int, tuple[int, int]], ...]] = {
    "R0": ((45, (3, 3)), (20, (2, 2)), (10, (1, 2)), (5, (1, 1))),
    "R1": ((20, (2, 2)), (10, (1, 2)), (5, (1, 1))),
}
RUNG = "R0"
MIN_CELL = 5
SMALL_CELL = 9999
CELL_SECTOR, CELL_BETA = 100, 10
#: PREREG 4.6: the universe excess u is the residual with ONE cell, every eligible name (rung R3): its cell id.
UNIVERSE_CELL = 0

# --------------------------------------------------------------------------------------- costs and the stress leg
#: D20. Half-spreads in basis points: a name's floor, the fallback (open, close) without a spreads file, and the
#: widest sample kept. THE FLOOR IS 3 BP, PREREG C5's figure for every fill (E4-SPEC said 1: the House may charge
#: more than the registered contract, never less, without a new receipt).
HS_FLOOR_BP = 3.0
HS_FALLBACK_BP = (10.0, 5.0)
HS_MAX_BP = 100.0
#: PREREG 3.4, THE STRESS LEG: x15 = x - `STRESS_SPREAD` x s - `STRESS_FEES` x f (1.5 times the half-spread, every
#: sell fee charged twice).
STRESS_SPREAD = 0.5
STRESS_FEES = 1.0

# -------------------------------------------------------------------------------------------- the House exit law
#: PREREG C6, 3.5, 5.5: a held name with no valid bar on this many sessions in a row is closed on the last of them,
#: at its last valid close x (1 - `VANISH_HAIRCUT`): the lot, its placebo counterparts and its cell's members ALIKE,
#: so the haircut makes and destroys no residual. (E4-SPEC's no-haircut "deal" exit is superseded: how a spell ended
#: is COUNTED beside a result, `VANISH_DEAL`, and sets no price.)
VANISH_SESSIONS = 3
VANISH_HAIRCUT = 0.30
#: How an index change row's reason is read as a deal (case-blind): a membership fact, never a price.
VANISH_DEAL = re.compile(r"acqui|merg|private|buyout|takeover|tender", re.I)

# ------------------------------------------------------------------------------------------- what a program sees
#: D7. Every bar's RAW price is moved by at most half a cent before any ratio is formed (the level is removed, not
#: hidden), and what a program reads is rounded to `CTX_PLACES` decimals (beta to `BETA_PLACES`: PREREG C1).
DITHER_HALF = 0.005
CTX_PLACES = 6
BETA_PLACES = 2
#: D8. A slot id is the first `ID_BITS` bits of a salted hash of the aid.
ID_BITS = 31

# ------------------------------------------------------------------------------------------ the vendor's rounding
#: THE VENDOR'S CENTS (found on real SIP bars after the designs): the adjustment=all series is rounded to the cent
#: (the raw series is the tape's own), so one adjusted price is off by up to half a cent, and a ratio or product built
#: from several by up to half a cent over each of them, summed. E1 gained `league.equity.config.rounding_bound` for it
#: AFTER this build's base (E1 547206fa): these three are league/xs's OWN copy, same names and same figures, so the
#: integrator can make them a re-export once E1's is in the base. Every as-of price, split and dividend reading of
#: league/xs takes this bound, never a fixed tolerance.
ADJUSTED_HALF_STEP = 0.005
ROUNDING_GUARD = 1.5


def rounding_bound(*adjusted: float) -> float:
    """The largest relative move the cent rounding of these adjustment=all prices explains in a ratio or product built
    from them: `ROUNDING_GUARD` x `ADJUSTED_HALF_STEP` x the sum of 1 / price. ValueError for no price or one that is
    not a positive finite number (the caller decides what an unreadable price means; it is never "all rounding").
    BUILT (not a stub): one shared helper, so no package writes a second."""
    if not adjusted:
        raise ValueError("the rounding bound of no price")
    parts = []
    for price in adjusted:
        value = float(price)
        if not (math.isfinite(value) and value > 0):
            raise ValueError(f"an adjusted price is a positive finite number, not {price!r}")
        parts.append(1.0 / value)
    return ROUNDING_GUARD * ADJUSTED_HALF_STEP * math.fsum(parts)


# ------------------------------------------------------------------------------------------------- quiet windows
#: The walls (New York time, on a session) at which no E4 job and no panel Train run may be RUNNING.
WALLS_ET = (("09:25", "09:45"), ("15:50", "16:35"))

_STUB = "league.xs.config is a Step 0 stub: package C (C0) builds it (league/xs/E4_INTERFACES.md)"


def quiet(now: float, need_s: float) -> str | None:
    """Why nothing that needs `need_s` seconds may START at the epoch `now`, or None: on a session, when [now, now +
    need_s] meets a wall of `WALLS_ET` (a half day's close wall moves with its close). A job passes ITS OWN wall-clock
    limit and a Train run its run budget: a start is refused when the work could still be running at a wall, not only
    when it begins inside one. Sessions are `league.equity.store.nyse_sessions`."""
    raise NotImplementedError(_STUB)


def rebalance_session(day: dt.date, rule: str, weekday: int = 0) -> bool:
    """D9. Whether the session `day` is a rebalance session: "weekly": the first session of its ISO week with weekday >=
    `weekday` (a week with none has no rebalance); "monthly": the first session of its month. ValueError for a rule
    outside `REBALANCE` or a day that is no session."""
    raise NotImplementedError(_STUB)


def decision_due(t: dt.date, rule: str, weekday: int = 0) -> bool:
    """D9. Whether the program is CALLED at the close of session `t`: the next session is a rebalance session."""
    raise NotImplementedError(_STUB)


__all__ = ["SPANS", "TRAIN_SEGMENTS", "TRAIN_YEARS", "HISTORY_YEARS", "RESERVE_YEARS", "REF", "FUNDS", "FUND_COLUMNS",
           "MARKET_COLUMN", "CLASS_PAIRS", "CLASS_SESSIONS", "MIN_NAMES", "MAX_NAMES", "MAX_WEIGHT", "MIN_HISTORY",
           "MAX_HISTORY", "MIN_HOLD_CAP", "MAX_HOLD_CAP", "REBALANCE", "MAX_BUYS", "MAX_SELLS", "MAX_ORDERS",
           "XS_SLEEVE_USD", "MIN_NAME_USD", "POSITION_SHARE", "RISK_WEIGHT", "DERIVE_SESSIONS", "WINDOW", "MIN_VALID",
           "MOM_SKIP", "MOM_BACK", "MEMBER_AHEAD", "REL_VOLUME_SESSIONS", "RUNGS", "RUNG", "MIN_CELL", "SMALL_CELL",
           "CELL_SECTOR", "CELL_BETA", "UNIVERSE_CELL", "HS_FLOOR_BP", "HS_FALLBACK_BP", "HS_MAX_BP", "STRESS_SPREAD",
           "STRESS_FEES", "VANISH_SESSIONS", "VANISH_HAIRCUT", "VANISH_DEAL", "DITHER_HALF", "CTX_PLACES",
           "BETA_PLACES", "ID_BITS", "ADJUSTED_HALF_STEP", "ROUNDING_GUARD", "rounding_bound", "WALLS_ET", "quiet",
           "rebalance_session", "decision_due"]
