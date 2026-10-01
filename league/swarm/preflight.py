"""THE PREFLIGHT: a candidate program meets small synthetic sessions in the decider's sandbox before a Train run is spent.

About one Train run in nine came back disqualified on Sept 30, 2026, and the retained ones were not losing ideas but
programs that could not run: `ctx.positions.items()` (a list used as a mapping), `ctx.under.get("price")` (the
underlying is an object), arithmetic on a None, a root the program never asked for. Each cost a multi-year replay on a
Gym box, a trial, and a research cycle. `check_experiment` (league/gym/experiment.py) is static; this is the runtime
half, and it runs nowhere near the Gym:

- **Where the code runs.** In the live path's own sandbox: `league.live.decider.Decider` itself, its spawn and every
  isolation rule it has (an empty environment, `-E -s`, the child's own limits, a read-only runtime copy, fail-closed
  off a root House, a mandatory private network namespace whose failed probe is retried), with two differences: the
  child runs under its own uid (`PREFLIGHT_UID`, not the 65534 the live and observe deciders run as, so an escaped
  program cannot signal or trace them), and at the lowest scheduling priority (`PREFLIGHT_NICE`: the live minute wins
  the House's one core). The House never executes a program in its own process. `load` is the Gym's
  `load_program` (safety check, NEEDS, PARAMS, the module body) and each call is the Gym's `Runner.decide` with its
  one-second limit.
- **What it sees.** Up to three synthetic sessions (a regular 09:30-16:00 day, no event; Tuesday to Thursday, or the
  weekdays on which its roots list the most expiries in its dte range, `session_weekdays`) on the program's own NEEDS:
  every root it names, with the chain the Gym's store lists for it (`listing`: the root's expiry weekdays within its dte
  range and the store's reach, 14 days, 45 for SPY and QQQ; the store's count of strikes a side on the root's listed
  step, $1 for the index ETFs, $5 for SPX/SPXW, a stock's by its price; mids priced by Black-Scholes on the root's own
  vol with a skew, `VOLS`, and quoted as the market quotes them, `quote`: tight near the money, wider away from it, never
  under one tick of the venue's), the underlying's prices from the open, NEEDS['history'] prior sessions, volume
  unknown (NaN, as in the replay), the Gym's venue rules, and a flat account of the run's capital (`swarm.json`
  `gym.capital`, which the researcher passes; `CAPITAL` otherwise). It is called at the
  Gym's own decision minutes (`engine.Account.decision_minutes`). The market is made up; nothing here reads recorded
  data, so it is no trial and says nothing about profit.
- **What it says.** One of four answers. The Train run goes ahead on every one but `refused`:
  - `passed`: decide never raised.
  - `advisory`: decide raised, and the error is not one that no market could spare. The researcher gets each error
    with its line, the line's source and the ctx API to use (`warnings`, `advice`), and the run goes on to the Gym,
    which judges it. Every error that could turn on the market's numbers is advisory, however often it recurs: an
    empty selection, a filter that keeps nothing (a quote width, a book's depth, a vol), a selection turned into one
    number, two selections of different lengths, a None, a numeric edge case, a STATE key or a local only a market
    condition would have written, a name not defined.
  - `inconclusive`: it could not say (a call past its time limit, the sandbox, the preflight's deadline, a busy lock).
  - `refused`, only for MARKET-INDEPENDENT MISUSE OF THE CTX API (`api_misuse`), when all three hold:
    1. decide raised on `STREAK` (25, the Gym's `DEFAULT_MAX_ERRORS`) consecutive calls spanning at least two
       sessions, before the program returned any intent, and every error the streak may hold is named in the Runner's
       message list;
    2. each of those errors is an AttributeError, TypeError, KeyError or IndexError that misuses a ctx object in a way
       its type forbids on every market, at a line whose failing expression is located in the program's source: a ctx
       list used as a mapping, a chain, an underlying or ctx itself read with `.get` or `[...]`, iterated or called, a
       field it does not have, a key a ctx dict can never hold (a root outside NEEDS, a PARAMS key the program never
       declared, an event that does not exist), a ctx array indexed in two dimensions, a ctx method called with the
       wrong number of arguments. Where the error names a plain type (a list, a dict, a float), the receiver on the
       line must resolve statically to a ctx field of that type (`_Source`): the program's own lists and dicts can hold
       what the market put there. Never an error raised on a None, an empty or size-0 value, one the House's own Python
       or numpy may cause (`environmental`) or one that says the market's numbers caused it (`market_dependent`);
    3. and the same exception type at the same line recurs, as a refusable streak, on a fresh instance of the program
       meeting each of the other markets (`CONFIRMATIONS`, `REGIMES`): a SATURATED one where every selection is filled
       and any filter keeps contracts (an expiry every calendar day, strikes at half the finer step and out to the far
       wings, each contract its own vol from 3% to 300%, quotes from one tick to one and a half times the mid, books to a
       million contracts, known volumes); a sparser and a denser listing, which bracket each admitted root's store on
       every Train day (`LISTING`); the listing quoted one tick wide on deep books at twice the vol; and quoted three
       times as wide on thin books at a lower vol, each on its own price paths.
  At load, only the Gym's static code check refuses (`static_refusal`: `league.gym.safety.check_program`, which
  `load_program` runs first and the researcher's `check_experiment` has already run on this box). Every other load
  failure is advisory, whatever it says: the module body, NEEDS and PARAMS run here on the House's Python 3.11 and
  numpy 2.4, and the Gym's boxes run 3.12+ with numpy 2.5 (a float `sum`, a slice used as a key and
  `math.nextafter(steps=)` each load there and not here), so the Gym, on its own runtime, judges them. A load that ran
  out of time is inconclusive. The risk left, accepted: decide runs here on the House's runtime too, so a value only
  3.12+ computes the Gym's way (`sum(W) != 1.0` on a float list) could steer every call into a misuse line the Gym's
  run never reaches. It is contrived, and none of the 300 sampled House programs that ran OK in the Gym is refused here.
  A clean program costs one session plus `STREAK` calls of the next (a streak that begins later could only be confirmed
  by yet another session, and is left to the Gym); the first intent ends the preflight (a flat account no longer mirrors
  the Gym's).
  The preflight never blocks on its own failure.
- **What the researcher gets.** On a refusal: the exception, the line and its source, the call it began at, and the
  ctx API it should have used (`advice`): no Gym job, no version and no trial are made, and the refusal is written in
  the family's notebook. A sweep drops only the variants refused and runs the others, reporting each refused one; it
  is refused whole only when every new variant is. On an advisory: the same for each error (`warnings`), beside the
  Gym's own answer.

numpy on the calling side (the House has it; the Gym's store and pyarrow are not needed). Python 3.11+.
"""

from __future__ import annotations

import ast
import atexit
import difflib
import hashlib
import math
import re
import subprocess
import threading
import time
import zlib
from typing import Any, Callable, Mapping, NamedTuple, Sequence

VERSION = "preflight-v7"
#: Consecutive erring calls that refuse: the Gym's own disqualification count (`league.gym.runtime.DEFAULT_MAX_ERRORS`).
STREAK = 25
#: Synthetic sessions at most (a third only to confirm a streak that began in the second).
SESSIONS = 3
#: Distinct messages a Gym Runner keeps (`league.gym.runtime.Runner._error`): an error past them is not reported.
RUNNER_MESSAGES = 10
#: Errors an advisory answer describes at most (`warnings`).
WARNINGS = 4
#: The account's capital when the caller names none: the Gym's default. The researcher passes the run's own
#: (`swarm.json` `gym.capital`, as the Gym's pool does), so a program that sizes by ctx.cash or ctx.budget takes the
#: branch here that it takes in the Gym.
CAPITAL = 10_000.0
#: The preflight's wall-clock budget; past it the program is not refused (inconclusive, or advisory with what it saw).
DEADLINE_SECONDS = 20.0
#: Weekdays of the synthetic sessions when the roots list as much every weekday (Tuesday, Wednesday, Thursday), and the
#: order ties are broken in otherwise (`session_weekdays`).
WEEKDAYS = (1, 2, 3)
PREFERRED_WEEKDAYS = (1, 2, 3, 0, 4)
OPEN, CLOSE = 570, 960
MINUTES = CLOSE - OPEN + 1
RATE = 0.04
#: What the Gym's store holds of a root's chain (scripts/data/storelib.py): NBBO 0-14 days to expiry (`MAX_DTE`) for every
#: root and, for SPY and QQQ only, their back months out to 45 (`BACK_MONTH_DTE`); `STRIKE_RANGE` listed strikes a side
#: of the money (25; 40 for SPXW only).
FRONT_DTE, BACK_MONTH_DTE = 14, 45
BACK_MONTH_ROOTS = frozenset({"SPY", "QQQ"})
STORE_STRIKES = {"SPXW": 40}
STORE_DEFAULT_STRIKES = 25
DAILY, MON_WED_FRI, FRIDAY = (0, 1, 2, 3, 4), (0, 2, 4), (4,)
#: THE LISTING: each root's chain as the exchanges list it near the money over Train (2020-2024, `gym.train_from`), which
#: is what the store holds: a representative price, the strike step at that price, and the weekdays that have an expiry
#: within FRONT_DTE (past it, Fridays). A root's schedule changed over Train, so no one listing is the Gym's on every
#: day. Two confirming listings bracket it (`listing`): the sparse one, Fridays only and the next wider step, and the
#: dense one, every weekday and the next finer step's strikes too; a refusal must recur on both (and on the saturated
#: market, which lists more than any of them). Every admitted root's store lies inside that bracket on every Train day,
#: whatever it listed that day: SPY and QQQ list every weekday from late 2022 (Monday, Wednesday and Friday before),
#: SPXW from spring 2022 (the same before), XSP every weekday in the store's 2024 sample (fewer earlier), IWM Monday,
#: Wednesday and Friday for most of Train (every weekday from spring 2024), all at a fixed step. Each is listed here with
#: its latest schedule but IWM; the listing only decides what the first market shows. Every other root lists Fridays
#: (the weeklies and the monthly). A root with monthlies only is coarser than the sparse listing: SPX (the AM-settled
#: root; its weeklies are SPXW) is one, and like a stock without weeklies it is not an admitted root. The index ETFs and
#: GLD list $1 strikes and SPX/SPXW $5 at any price; a stock or another ETF lists by its price (`equity_step`: $0.5
#: under $75, $1 under $150, $2.5 under $500, $5 above). A root not named here is a $100 stock with Friday expiries.
#: Since v6 a listing that is off costs catches, never a refusal: an error that turns on what a chain lists is not a
#: misuse of the ctx API (`api_misuse`) and never refuses, whatever the listing.
LISTING: dict[str, tuple[float, float, tuple[int, ...]]] = {
    "SPY": (450.0, 1.0, DAILY), "QQQ": (380.0, 1.0, DAILY), "SPXW": (4500.0, 5.0, DAILY), "SPX": (4500.0, 5.0, FRIDAY),
    "IWM": (190.0, 1.0, MON_WED_FRI), "XSP": (450.0, 1.0, DAILY), "DIA": (350.0, 1.0, FRIDAY),
    "GLD": (180.0, 1.0, FRIDAY),
}
#: Representative Train prices of the rest of the universe (`equity_step` gives their strike step, Fridays their
#: expiries).
PRICES = {"SLV": 22.0, "TLT": 100.0, "SMH": 220.0, "NVDA": 400.0, "MSFT": 300.0, "AMZN": 130.0, "AMD": 110.0,
          "GOOGL": 120.0, "TSM": 100.0, "TSLA": 220.0, "PLTR": 20.0, "SMCI": 250.0, "META": 300.0, "AAPL": 170.0,
          "MARA": 15.0, "MU": 80.0, "BABA": 90.0, "SOXL": 25.0, "TQQQ": 40.0}
DEFAULT_PRICE = 100.0
#: The roots whose near-money step is the same on every Train day (the $1 index ETFs, SPX's $5): a sparser or denser
#: listing (`listing`) keeps it; any other root's sparser listing takes the next wider step, and its denser one lists
#: the next finer step's strikes beside its own (`strikes`).
FIXED_STEP = frozenset({"SPY", "QQQ", "IWM", "XSP", "DIA", "SPXW", "SPX"})
WIDER = {0.5: 1.0, 1.0: 2.5, 2.5: 5.0, 5.0: 10.0}
FINER = {1.0: 0.5, 2.5: 1.0, 5.0: 2.5}
#: Each root's implied vol in the synthetic market: ballpark levels of the kind any options screen shows, not fitted to
#: any vendor's quotes (the repository is public and holds none). A cheap, wild stock needs its own: at the index's vol a
#: $15 stock's weekly at-the-money option would be worth a few cents, and its one-cent tick a quarter of that.
VOLS = {"SPY": 0.17, "QQQ": 0.22, "IWM": 0.22, "SPXW": 0.17, "SPX": 0.17, "XSP": 0.17, "DIA": 0.16, "GLD": 0.15,
        "SLV": 0.28, "TLT": 0.16, "SMH": 0.35, "NVDA": 0.50, "MSFT": 0.26, "AMZN": 0.33, "AMD": 0.48, "GOOGL": 0.30,
        "TSM": 0.38, "TSLA": 0.55, "PLTR": 0.60, "SMCI": 0.75, "META": 0.36, "AAPL": 0.26, "MARA": 0.85, "MU": 0.45,
        "BABA": 0.40, "SOXL": 0.85, "TQQQ": 0.60}
DEFAULT_VOL = 0.35
#: THE QUOTES (`quote`): a contract's full quoted width near the money as a share of its mid (`DEFAULT_WIDTH` for a
#: root not named). An assumption of the usual shape of US listed-option quotes, not fitted to any vendor's data: the index
#: ETFs quote a cent or two on a few dollars near the money, SPX/SPXW a tick or two of $0.05-0.10 on tens of dollars, a
#: stock a few cents on a few dollars. Away from the money a quote widens as a share of its mid (by `WIDENING` a standard
#: deviation of moneyness, up to `WIDEST_Z` of them), and none is narrower than one tick of the venue's (`venue.leg_tick`:
#: a cent on SPY, QQQ and IWM; $0.05 and $0.10 on SPX/SPXW; a cent under $3 and a nickel from $3 on the rest), so a far
#: out-of-the-money contract of a few cents is quoted tens of percent wide, as in the market. Near the money every root
#: quotes no wider than the Gym's own synthetic store (3% of the mid, `gym.synth.generate`).
NEAR_WIDTH = {"SPY": 0.004, "QQQ": 0.004, "IWM": 0.008, "SPXW": 0.01, "SPX": 0.01}
DEFAULT_WIDTH = 0.015
WIDENING, WIDEST_Z = 0.5, 4.0
#: THE SATURATED MARKET (`REGIMES["saturated"]`): numbers drawn so wide that a filter on any of them keeps contracts and
#: every selection by expiry or strike is filled. Each contract's vol is drawn once a session, evenly on a log scale
#: (`SATURATED_VOLS`); its quote's width as a share of its mid at every minute (`SATURATED_WIDTHS`, never under one tick);
#: its books up to `REGIMES["saturated"].sizes` and its open interest up to `.oi`, evenly on a log scale. Its chain lists
#: an expiry on every calendar day of the program's dte range out to BACK_MONTH_DTE, and strikes at half the finer step
#: across the listing's span plus a strike every `WING_STEP` of the open out to the program's band and `WING_MARGIN`
#: past it (`saturated_strikes`, at most `SATURATED_REACH`). The underlying's minute and daily volumes are known.
SATURATED_VOLS = (0.03, 3.0)
SATURATED_WIDTHS = (1e-4, 1.5)
WING_STEP, WING_MARGIN, SATURATED_REACH = 0.025, 0.05, 0.6


class Regime(NamedTuple):
    """One synthetic market's numbers (`REGIMES`): its listing (`chain`: "listed", "sparse", "dense" or "saturated",
    `listing`), its quotes' width (a multiple of `quote`'s; 0: every quote one tick wide, the venue's narrowest), each
    root's vol and price as multiples of `VOLS` and the listing's price, its books' sizes (a range, drawn evenly on a log
    scale) and open interest (the most), and its own price paths (`salt`)."""

    label: str
    chain: str
    width: float
    vol: float
    level: float
    sizes: tuple[int, int]
    oi: int
    salt: int


#: THE MARKETS a program meets. It is first run on the listing with typical quotes on books of every size, from one
#: contract to thousands. A refusal must then recur (the same exception type at the same line, as a refusable streak) on
#: each of the others in turn (`CONFIRMATIONS`): the saturated market (THE SATURATED MARKET above); the listing's bracket
#: (`LISTING`), the same roots listed more thinly on the same numbers and listed more densely on its own price paths at a
#: vol between the listing's and the tight market's; and the listing again with other numbers at both ends: every quote
#: one tick wide (the venue's narrowest) on deep books at twice the vol and a higher price, and quotes three times as wide
#: on thin books at a lower vol and price; each on its own price paths. Only a misuse of the ctx API (`api_misuse`) can
#: refuse at all; these markets check that it does not hang on a branch the made-up numbers opened.
REGIMES = {
    "listed": Regime("the listed chain", "listed", 1.0, 1.0, 1.0, (1, 5_000), 50_000, 1),
    "saturated": Regime("a saturated market (an expiry every calendar day, strikes at half the finer step and out to the "
                        "far wings, each contract its own vol from 3% to 300%, quotes from one tick to 1.5 times the mid, "
                        "books to a million contracts, known volumes)", "saturated", 1.0, 1.0, 1.0, (1, 1_000_000),
                        10_000_000, 5),
    "sparse": Regime("a sparser listing of the same roots (one expiry a week, a wider strike step)", "sparse", 1.0, 1.0,
                     1.0, (1, 5_000), 50_000, 1),
    "dense": Regime("a denser listing of the same roots (an expiry every weekday, a finer strike step; another price "
                    "path, a vol between)", "dense", 1.0, 1.4, 1.05, (1, 5_000), 50_000, 4),
    "tight": Regime("the listing quoted one tick wide on deep books (twice the vol, another price path, a higher price)",
                    "listed", 0.0, 2.0, 1.1, (200, 5_000), 500_000, 2),
    "wide": Regime("the listing quoted three times as wide on thin books (a lower vol, another price path, a lower price)",
                   "listed", 3.0, 0.6, 0.9, (1, 40), 3_000, 3),
}
CONFIRMATIONS = ("saturated", "sparse", "dense", "tight", "wide")


def equity_step(price: float) -> float:
    """The strike step a stock's weekly lists near the money at `price` (`LISTING`)."""
    return 0.5 if price < 75 else 1.0 if price < 150 else 2.5 if price < 500 else 5.0


def listing(root: str, *, sparse: bool = False, dense: bool = False) -> tuple[float, float, tuple[int, ...]]:
    """(price, strike step, expiry weekdays) of `root` (`LISTING`). `sparse`: the same root listed more thinly, one
    expiry a week (Fridays) and, unless the root's step never changes, the next wider strike step. `dense`: listed more
    densely, an expiry every weekday and, unless the root's step never changes, the next finer step (`strikes` lists it
    beside the root's own)."""
    root = str(root).upper()
    if root in LISTING:
        price, step, weekdays = LISTING[root]
    else:
        price = PRICES.get(root, DEFAULT_PRICE)
        step, weekdays = equity_step(price), FRIDAY
    if sparse:
        return price, (step if root in FIXED_STEP else WIDER.get(step, 2.0 * step)), FRIDAY
    if dense:
        return price, (step if root in FIXED_STEP else FINER.get(step, step)), DAILY
    return price, step, weekdays


def strikes(root: str, price: float, *, chain: str = "listed") -> Any:
    """The strikes listed about `price` (the session's open): the store's count a side of the money on the step of
    `chain`'s listing (`listing`, `STORE_STRIKES`), none at or under zero. The dense chain spans the listing's strikes
    and lists the finer step's inside that span beside them, so it holds every strike of the listing."""
    import numpy as np

    root = str(root).upper()
    side = STORE_STRIKES.get(root, STORE_DEFAULT_STRIKES)
    step = listing(root, sparse=chain == "sparse")[1]
    ks = round(float(price) / step) * step + step * np.arange(-side, side + 1)
    if chain == "dense":
        fine = listing(root, dense=True)[1]
        if fine != step:
            lo, hi = float(ks[0]), float(ks[-1])
            finer = fine * np.arange(math.ceil(lo / fine - 1e-9), math.floor(hi / fine + 1e-9) + 1)
            ks = np.unique(np.round(np.concatenate([ks, finer]), 6))
    return ks[ks > 0]


def saturated_strikes(root: str, price: float, band: float) -> Any:
    """The saturated market's strikes about `price` (THE SATURATED MARKET): the dense chain's (so every strike of the
    listing), half the finer step across the same span, and a strike every WING_STEP of `price` out to `band` and
    WING_MARGIN past it (at most SATURATED_REACH), each on the half step; none at or under zero."""
    import numpy as np

    root = str(root).upper()
    ks = strikes(root, price, chain="dense")
    half = min(listing(root)[1], listing(root, dense=True)[1]) / 2.0
    lo, hi = float(ks[0]), float(ks[-1])
    grid = half * np.arange(math.ceil(lo / half - 1e-9), math.floor(hi / half + 1e-9) + 1)
    wings = int(min(SATURATED_REACH, max(0.0, float(band)) + WING_MARGIN) / WING_STEP)
    far = np.round(float(price) * (1.0 + WING_STEP * np.arange(-wings, wings + 1)) / half) * half
    ks = np.unique(np.round(np.concatenate([ks, grid, far]), 6))
    return ks[ks > 0]


def vol_of(root: str) -> float:
    """`root`'s implied vol in the synthetic market (`VOLS`)."""
    return VOLS.get(str(root).upper(), DEFAULT_VOL)


def quote(root: str, mid: Any, z: Any, width: float = 1.0, *, share: Any = None) -> tuple[Any, Any]:
    """Bid and ask about each `mid` (THE QUOTES, `NEAR_WIDTH`): `width` times the root's near-money width as a share of
    the mid, wider by WIDENING for each standard deviation of moneyness `z` (up to WIDEST_Z), to the nearest tick of the
    venue's at that premium and never less than one (`venue.leg_tick`); `width` 0 quotes every contract one tick wide.
    `share`: each contract's full width as a share of its mid instead (the saturated market's), never under one tick."""
    import numpy as np

    from ..gym import venue as V

    root = str(root).upper()
    mid = np.asarray(mid, dtype=np.float64)
    tick = np.where(mid < 3.0, V.leg_tick(root, 0.0), V.leg_tick(root, 3.0))
    if share is None:
        share = NEAR_WIDTH.get(root, DEFAULT_WIDTH) * float(width) * (1.0 + WIDENING * np.minimum(np.abs(z), WIDEST_Z))
    ticks = np.maximum(1.0, np.round(np.asarray(share, dtype=np.float64) * mid / tick))
    bid = np.maximum(0.0, np.round((mid - 0.5 * ticks * tick) / tick)) * tick
    return np.round(bid, 4), np.round(bid + ticks * tick, 4)


def expiries(root: str, weekday: int, dte_min: int, dte_max: int, weekdays: Sequence[int]) -> list[int]:
    """The days to expiry listed on a session of `weekday` (0 = Monday) within [dte_min, dte_max]: an expiry on each of
    `weekdays` out to FRONT_DTE, Fridays past it, and nothing past what the store keeps for the root."""
    top = BACK_MONTH_DTE if str(root).upper() in BACK_MONTH_ROOTS else FRONT_DTE
    return [d for d in range(int(dte_min), min(int(dte_max), top) + 1)
            if (weekday + d) % 7 in (weekdays if d <= FRONT_DTE else FRIDAY)]


def session_weekdays(roots: Sequence[str], needs: Mapping[str, Any], *, sparse: bool = False) -> tuple[int, ...]:
    """The synthetic sessions' weekdays: the SESSIONS weekdays on which the roots' listings hold the most expiries in the
    program's dte range (ties: Tuesday, Wednesday, Thursday, Monday, Friday), in calendar order. A Friday-only root with
    dte [10, 20] lists on Monday, Tuesday and Friday (11, 10 and 14 days out), not midweek: its sessions are those."""
    dte_min, dte_max = (int(x) for x in needs["dte"])
    held = {day: sum(len(expiries(root, day, dte_min, dte_max, listing(root, sparse=sparse)[2])) for root in roots)
            for day in PREFERRED_WEEKDAYS}
    ranked = sorted(PREFERRED_WEEKDAYS, key=lambda day: (-held[day], PREFERRED_WEEKDAYS.index(day)))
    return tuple(sorted(ranked[:SESSIONS]))


# ------------------------------------------------------------------------------------------------ the synthetic market
def _rng(root: str, salt: int) -> Any:
    import numpy as np

    return np.random.default_rng(zlib.crc32(f"{root}:{salt}".encode()) & 0xFFFFFFFF)


def _log_uniform(rng: Any, low: float, high: float, n: int) -> Any:
    import numpy as np

    return np.exp(rng.uniform(math.log(low), math.log(high), n))


class Market:
    """Synthetic sessions for a program's NEEDS (the module docstring) on each root's chain (`listing`, `strikes`,
    `saturated_strikes`) with the numbers of `regime` (`REGIMES`: "listed" first; `sparse` is the "sparse" one). Its
    sessions fall on the weekdays of the listing's (`session_weekdays`), the dense and saturated ones' too, so on each
    session the dense chain lists every expiry the listing does and, about its own open, the listing's strikes with the
    finer step's beside them. Deterministic: the same roots, NEEDS and regime make the same market."""

    def __init__(self, roots: Sequence[str], needs: Mapping[str, Any], *, sparse: bool = False, regime: str = "listed"):
        import numpy as np

        from ..gym import greeks as G

        self.roots = tuple(roots)
        self.needs = dict(needs)
        self.regime = REGIMES["sparse" if sparse else regime]
        self.chain = self.regime.chain
        self.sparse, self.dense, self.saturated = self.chain == "sparse", self.chain == "dense", self.chain == "saturated"
        self.weekdays = session_weekdays(self.roots, needs, sparse=self.sparse)
        dte_min, dte_max = (int(x) for x in needs["dte"])
        history = int(needs["history"])
        self.vols = {root: vol_of(root) * self.regime.vol for root in self.roots}
        self.days: dict[str, list[dict[str, Any]]] = {}
        for root in self.roots:
            rng = _rng(root, self.regime.salt)
            spot, _, weekdays = listing(root, sparse=self.sparse, dense=self.dense)
            spot *= self.regime.level
            per_minute = self.vols[root] / math.sqrt(252 * 390)
            overnight = 0.35 * self.vols[root] / math.sqrt(252)  # about a third of a day's move
            bars, paths = [], []
            for _ in range(history + SESSIONS):
                spot *= math.exp(rng.normal(0.0, overnight))  # the overnight move
                path = spot * np.exp(np.cumsum(rng.normal(0.0, per_minute, MINUTES)))
                path[0] = spot
                bars.append((float(path[0]), float(path.max()), float(path.min()), float(path[-1])))
                paths.append(path)
                spot = float(path[-1])
            daily = _log_uniform(rng, 1e6, 1e9, history + SESSIONS).round() if self.saturated else None
            sessions = []
            for s in range(SESSIONS):
                i = history + s
                prior = np.array(bars[i - history:i], dtype=np.float64).reshape(-1, 4)
                path = paths[i]
                weekday = self.weekdays[s]
                if self.saturated:  # every calendar day, and strikes past the listing's (THE SATURATED MARKET)
                    dtes = list(range(dte_min, min(dte_max, BACK_MONTH_DTE) + 1))
                    ks = saturated_strikes(root, float(path[0]), float(needs["band"]))
                else:
                    dtes = expiries(root, weekday, dte_min, dte_max, weekdays)
                    ks = strikes(root, float(path[0]), chain=self.chain)  # the store's strikes a side of the open's money
                dte = np.repeat(np.array(dtes, dtype=np.int64), ks.size * 2)
                strike = np.tile(np.repeat(ks, 2), len(dtes))
                is_call = np.tile(np.array([True, False]), ks.size * len(dtes))
                n = strike.size
                day = {"weekday": weekday, "path": path, "prior": prior, "dte": dte, "strike": strike, "is_call": is_call}
                if self.saturated:
                    day["oi"] = np.floor(_log_uniform(rng, 1.0, float(self.regime.oi), n)).astype(np.int64)
                    day["sigma"] = _log_uniform(rng, *SATURATED_VOLS, n)
                    day["minute_volumes"] = _log_uniform(rng, 1e2, 1e6, MINUTES).round()
                    day["daily_volumes"] = daily[s:i]
                else:
                    day["oi"] = rng.integers(0, self.regime.oi, n)
                day["rng"] = _rng(root, 100 * self.regime.salt + s)
                sessions.append(day)
            self.days[root] = sessions
        self._G = G

    def snapshot(self, root: str, session: int, mi: int) -> Any:
        """The root's chain at minute `mi` of the session (a `Snapshot`, as the replay makes one): Black-Scholes mids on
        the root's vol with a skew (the saturated market: each contract's own vol), quoted about them (`quote`), with the
        regime's sizes (evenly on a log scale, so a size filter at any depth in the range keeps some contracts and drops
        others, at any quote width)."""
        import numpy as np

        from ..gym.ctx import Snapshot

        day = self.days[root][session]
        spot = float(day["path"][mi])
        dte, strike, is_call = day["dte"], day["strike"], day["is_call"]
        n = strike.size
        if n == 0:
            return Snapshot(root, OPEN + mi, spot, dte, strike, is_call, np.zeros(0), np.zeros(0), oi=day["oi"], rate=RATE)
        years = self._G.years_to_expiry(dte, OPEN + mi, close_minute=CLOSE)
        m = np.log(strike / spot)
        rng, (low, high) = day["rng"], self.regime.sizes
        if self.saturated:
            mid = self._G.bs_price(spot, strike, years, RATE, day["sigma"], is_call)
            bid, ask = quote(root, mid, 0.0, share=_log_uniform(rng, *SATURATED_WIDTHS, n))
        else:
            sigma = self.vols[root] * (1.0 - 1.5 * m + 8.0 * m * m)
            mid = self._G.bs_price(spot, strike, years, RATE, sigma, is_call)
            bid, ask = quote(root, mid, m / (sigma * np.sqrt(years)), self.regime.width)
        sizes = lambda: np.floor(np.exp(rng.uniform(math.log(low), math.log(high + 1), n))).astype(np.int64)  # noqa: E731
        return Snapshot(root, OPEN + mi, spot, dte, strike, is_call, bid, ask, sizes(), sizes(), oi=day["oi"], rate=RATE,
                        close_minute=CLOSE)

    def under(self, root: str, session: int, mi: int) -> Any:
        """The root's underlying at minute `mi` (as `engine.DayData.under`: prices from the open, prior sessions, volume
        unknown as in a replay without first-observation receipts; the saturated market's volumes are known)."""
        from ..gym.ctx import underlying_view

        day = self.days[root][session]
        prior = day["prior"]
        volumes: dict[str, Any] = {"volume_provenance": "historical_without_asof", "daily_volume_provenance": "unavailable"}
        if self.saturated:
            volumes = {"minute_volumes": day["minute_volumes"][:mi], "daily_volumes": day["daily_volumes"],
                       "volume_provenance": "first_observed", "daily_volume_provenance": "first_observed_session_sum"}
        return underlying_view(root, day["path"][: mi + 1], opens=prior[:, 0], highs=prior[:, 1], lows=prior[:, 2],
                               closes=prior[:, 3], **volumes)


def decision_minutes(needs: Mapping[str, Any]) -> list[int]:
    """The Gym's decision minutes on a regular session (`engine.Account.decision_minutes`)."""
    first = max(int(needs["start"]), OPEN + 1) - OPEN
    last = min(int(needs["end"]) - OPEN, MINUTES - 3)
    return list(range(first, last + 1, int(needs["cadence"]))) if first <= last else []


# ------------------------------------------------------------------------------------------------ what to say
_LIST_ROWS = ("ctx.positions, ctx.orders and ctx.closed are LISTS of dicts (ctx.rejects a list of strings), never "
              "mappings: iterate `for p in ctx.positions:` and read `p['id']`, `p['legs']`, `p['pnl']`; find one with "
              "`next((p for p in ctx.positions if p['id'] == pid), None)`; key them yourself with "
              "`{p['id']: p for p in ctx.positions}`.")
_NONE = ("a value was None. In the Gym: `ctx.chain`/`ctx.under` are None when the first root has no data now; "
         "`ctx.chains.get(root)` and `ctx.underlyings.get(root)` are None for a root without data; `dict.get` is None for "
         "a missing key (STATE starts empty in every run; ctx.params holds exactly your PARAMS keys{params}); a "
         "position's `mark`, `natural` and `pnl` are None without a two-sided quote. Test `is None` (or give `.get` a "
         "default) before arithmetic or a comparison.")
POSITION_KEYS = ("id", "type", "root", "qty", "legs", "entry", "credit", "max_loss", "mark", "natural", "pnl", "held_minutes",
                 "held_days", "tag")
LEG_KEYS = ("id", "dte", "strike", "is_call", "side", "ratio")
ORDER_KEYS = ("id", "kind", "type", "root", "qty", "filled", "limit", "age_minutes", "position", "tag")


def _names(cls: Any, extra: Sequence[str] = ()) -> list[str]:
    return [n for n in getattr(cls, "__slots__", ()) if not n.startswith("_")] + list(extra)


def _close(word: str, names: Sequence[str]) -> str:
    near = difflib.get_close_matches(word, list(names), n=1, cutoff=0.6)
    return f" Did you mean `{near[0]}`?" if near and near[0] != word else ""


def advice(message: str, *, roots: Sequence[str] = (), params: Mapping[str, Any] | None = None, source: str = "") -> str:
    """The ctx API a runtime error message points at (PROGRAM.md / league/CONTRACT.md, "ctx"): one or two sentences."""
    from ..gym.ctx import ChainView, Ctx, UnderlyingView

    chain = _names(ChainView, ("iv", "delta", "gamma", "theta", "vega"))
    under = _names(UnderlyingView)
    keys = sorted((params or {}).keys())
    shown = f": {', '.join(keys[:24])}" if keys else ""
    text = str(message or "")
    m = re.search(r"'(list|tuple)' object has no attribute '(\w+)'", text)
    if m:
        return _LIST_ROWS
    m = re.search(r"'UnderlyingView' object has no attribute '(\w+)'", text)
    if m:
        return ("ctx.under and ctx.underlyings[root] are objects read by ATTRIBUTE, not dicts (no `.get`, no `[...]`): "
                + ", ".join(under) + ". E.g. `u = ctx.underlyings.get(root)`, then `u.price`, `u.closes[-1]`; an optional "
                "field is `getattr(u, 'name', None)`." + _close(m.group(1), under))
    m = re.search(r"'ChainView' object has no attribute '(\w+)'", text)
    if m:
        return ("ctx.chains[root] (and ctx.chain) holds numpy arrays read by ATTRIBUTE, one entry per contract: "
                + ", ".join(chain) + " (`strike` is singular; `expiries` lists the days to expiry present)."
                + _close(m.group(1), chain))
    m = re.search(r"'Ctx' object has no attribute '(\w+)'", text)
    if m:
        fields = _names(Ctx)
        return "ctx has these fields only: " + ", ".join(fields) + "." + _close(m.group(1), fields)
    m = re.search(r"'dict' object has no attribute '(\w+)'", text)
    if m:
        return ("position and order rows, ctx.rules[root], ctx.params and ctx.events are dicts: read `row['name']`, not "
                "`row.name`. A position row's keys: " + ", ".join(POSITION_KEYS) + ".")
    if re.search(r"'(float|int)' object is not (subscriptable|iterable)", text):
        return ("a number was indexed or iterated: ctx.under.price, .open, .high, .low and .prior_close are numbers; "
                "ctx.under.prices (today's minutes) and .closes, .opens, .highs, .lows (prior sessions) are the arrays.")
    if re.search(r"'(ChainView|UnderlyingView|Ctx)'( object is not| is not a container)", text) or \
            re.search(r"argument of type '(ChainView|UnderlyingView|Ctx)'", text):
        return ("ctx, a chain (ctx.chains[root]) and an underlying (ctx.underlyings[root]) are objects: read their fields as "
                "attributes (`ctx.chain.strike`, `ctx.under.price`); only ctx.chains, ctx.underlyings, ctx.rules, "
                "ctx.params and ctx.events are dicts.")
    if "NoneType" in text:
        return _NONE.format(params=shown)
    m = re.search(r"KeyError: '([^']*)'", text)
    if m:
        key = m.group(1)
        if key.upper() == key and key.isalpha() and key not in keys:
            return (f"ctx.chains, ctx.underlyings and ctx.rules hold only the NEEDS['roots'] with data now "
                    f"({', '.join(roots) or 'none'}); `{key}` is not one of them. Name it in NEEDS['roots'] (the Gym's "
                    f"admitted roots only), or read `ctx.chains.get(root)` and skip a None.")
        if key in keys:
            return (f"`{key}` is one of your PARAMS: read it as `ctx.params['{key}']` (or `PARAMS['{key}']`); it is not in "
                    "STATE (empty at the start of every run), a position row or ctx.rules.")
        if key in LEG_KEYS and key not in POSITION_KEYS:
            return (f"a position row has no `{key}`; its legs do (`p['legs'][i]['{key}']`). A position row's keys: "
                    + ", ".join(POSITION_KEYS) + "; a leg's: " + ", ".join(LEG_KEYS) + ".")
        return ("a missing key. ctx.params holds exactly your PARAMS keys" + shown + "; STATE starts empty in every run "
                "(use `STATE.get(k, default)`); a position row's keys: " + ", ".join(POSITION_KEYS) + "; a working order's: "
                + ", ".join(ORDER_KEYS) + "; ctx.events: fomc, cpi, jobs, monthly_opex, quarter_end, half_day.")
    if re.search(r"list indices must be integers or slices, not (dict|str)", text):
        return "a list was indexed by a row or a key: " + _LIST_ROWS
    if re.search(r"'(int|float|str|bool|numpy\.\w+)' object has no attribute 'get'", text):
        return ("`.get` was called on a number or a string, not a dict: check what the name holds (a position row's "
                "fields are plain values; ctx.chain fields are numpy arrays; ctx.under fields are attributes).")
    if "too many indices for array" in text:
        return ("ctx.chain's fields are one-dimensional numpy arrays, one entry per contract: index them with one index or "
                "mask (`c.mid[i]`, `c.mid[mask]`), never two (`c.mid[i, j]`, `c.mid[:, 0]`).")
    if "truth value of an array" in text:
        return ("a numpy array was used as one boolean: chain fields are arrays, one entry per contract, and a mask keeps "
                "every contract that matches it (every listed expiry, every strike within a tolerance); use `.any()`, "
                "`.all()`, or index a single contract first (`i = np.flatnonzero(mask)`, check `i.size`).")
    if re.search(r"only (length-1|0-dimensional) arrays can be converted|convert an array of size 1", text):
        return ("an array was converted to one number: `float(c.bid[mask])` needs a mask that keeps exactly one contract, "
                "and the Gym's numpy refuses even that; index one contract first (`i = np.flatnonzero(mask)`, check "
                "`i.size`, then `float(c.bid[i[0]])`).")
    if "read-only" in text:
        return "arrays from ctx are read-only: copy one first (`np.array(ctx.chain.mid)`) before changing it."
    if "IndexError" in text:
        return ("an empty or short array or list was indexed: a chain slice can be empty (`ctx.chain.n == 0`, or a mask "
                "that matches no contract), ctx.under.closes holds at most NEEDS['history'] sessions, and ctx.positions "
                "is empty until an open fills. Check the length first.")
    if "ZeroDivisionError" in text:
        return "a division by zero: guard the denominator (a bid, a spread or a count can be 0)."
    if "decide returned" in text or "an intent" in text:
        return "decide returns a list of intent dicts (or [] / None), each with exactly one of 'open', 'close' or 'cancel'."
    if "not associated with a value" in text:
        return ("a local was read before any assignment reached it: set it on every path (a default before the `if` that "
                "fills it), since a filter can keep nothing on some minutes.")
    if "is not defined" in text:
        return "a name is not defined: only math and numpy import, and the short list of safe builtins is all there is."
    return "check the line against the ctx section of league/CONTRACT.md."


#: Attribute names no Python or numpy version gives a number, a string or an array: reading one of them off such a value
#: is the program's mistake on every version (the ctx's own names are added in `environmental`).
_NEVER_ON_SCALARS = frozenset({"get", "items", "keys", "values", "update", "setdefault", "popitem", "append", "extend",
                               "insert", "remove", "add", "discard"})
#: Types whose attributes Python 3.11-3.14 all share (none gained a method since 3.11), and the ctx's own classes (the same
#: league/gym code on the House and in the Gym's bundle). An attribute missing on one of them is missing in the Gym too.
_STABLE_TYPES = frozenset({"list", "tuple", "dict", "set", "frozenset", "NoneType", "range", "ChainView", "UnderlyingView",
                           "Ctx", "Snapshot"})


#: Every complaint about a keyword argument, on any version's wording ("got an unexpected keyword argument", "takes no
#: keyword arguments", "is an invalid keyword argument for", "positional-only arguments passed as keyword arguments", a
#: keyword-only argument): keywords are what newer Pythons and numpys add (`str.replace(count=)` from 3.13,
#: `math.nextafter(steps=)` from 3.12), so no such error says the same thing on every runtime.
_KEYWORD_ERRORS = re.compile(r"keyword(?:-only)? arguments?")


def environmental(message: str) -> bool:
    """An error that could be this box's and not the Gym's: the House runs Python 3.11 with numpy 2.4 and caps the
    decider child at 2 GB, the Gym's boxes run 3.12+ with numpy 2.5 (requirements-gym.txt) and give a worker 6 GB. So a
    module attribute one version has and the other lacks (`math.sumprod`, a numpy function), a keyword argument
    (`_KEYWORD_ERRORS`, whatever the version's wording), a method a newer Python gave a number, a string or a numpy value
    (`int.is_integer`), memory, or recursion depth says nothing about the program. Such an error never refuses."""
    text = str(message or "")
    if (_KEYWORD_ERRORS.search(text) or "No module named" in text or "MemoryError" in text
            or "Unable to allocate" in text or "recursed too deep" in text or "RecursionError" in text):
        return True
    if re.search(r"module '[\w.]+' has no attribute", text):
        return True
    m = re.search(r"'([\w.]+)' object has no attribute '(\w+)'", text)
    if m and m.group(1) not in _STABLE_TYPES:
        from ..gym.ctx import ChainView, Ctx, UnderlyingView

        ctx_names = set(_names(ChainView)) | set(_names(UnderlyingView)) | set(_names(Ctx)) | set(POSITION_KEYS) | \
            set(ORDER_KEYS) | set(LEG_KEYS)
        return m.group(2) not in _NEVER_ON_SCALARS and m.group(2) not in ctx_names
    return False


#: Errors whose presence turns on the market's numbers, not on the program's use of the API: an empty selection, a
#: division by a price or a count, a strike looked up in a dict, a log of a non-positive number, a None from a search that
#: found nothing on this market. Such an error is advisory however often it recurs; `api_misuse` never takes one (but for
#: an array indexed in two dimensions, which its own words place outside this list). First by the exception's type alone,
#: whatever its words: an index past an empty or short array, a division by zero, an exhausted search, an overflow, a
#: singular fit, a None, a numeric key (a strike, or a strike's text), a pop from an empty set or dict.
_MARKET_ERRORS = re.compile(r"\b(IndexError|ZeroDivisionError|StopIteration|OverflowError|FloatingPointError|LinAlgError|"
                            r"NoneType|KeyError: -?[\d.]+|KeyError: '-?\d+(?:\.\d+)?'|KeyError: \(|KeyError: np\.|"
                            r"KeyError: nan|KeyError: '(?:pop from an empty set|popitem\(\): dictionary is empty)')")
#: Then a ValueError or a TypeError by what it says, each wording raised on the House's runtime (Python 3.11, numpy 2.4.4)
#: and on 3.14 with numpy 2.5.3 (the tests raise every one on the runtime they run on; CI runs both). An empty selection
#: says "empty", "non-empty", "size 0" or "zero-size", or prints a shape with a zero in it, or is too small for what was
#: asked of it. Turning a selection into one number cannot tell an empty one from a crowded one (`.item()`,
#: `np.squeeze(axis=0)`; `float()`, `int()` or a format of an array). Two selections of different lengths are each as long
#: as the market makes them. A search that found nothing, a step, a scale or a range worked out from the numbers, and a
#: NaN or an infinity are the market's too, as are the math module's domain errors on 3.11 and 3.14.
_MARKET_VALUES = re.compile(
    r"\bempty\b|non-empty|\bsize 0\b|zero-size|can only convert an array of size 1|"
    r"only (?:0-dimensional|length-1|size-1) arrays can be converted|squeeze out which has size not equal to one|"
    r"unsupported format string passed to numpy\.ndarray|"
    r"\((?:\d+,\s*)*0(?:,\s*\d+)*,?\)|size 0 is different|different from 0\)|"
    r"broadcast|not aligned|mismatch in its core dimension|not of the same length|to have same length|"
    r"zip\(\) argument \d+ is (?:longer|shorter) than|too small to calculate|kth\(=-?\d+\) out of bounds|"
    r"number sections must be larger than 0|does not result in an equal division|must be non-negative|"
    r"negative dimensions are not allowed|arg 3 must not be zero|max must be larger than min|scale < 0|"
    r"math domain error|^expected [^,]*, got |not in (?:list|tuple)|All-NaN slice|cannot convert float (?:NaN|infinity)|"
    r"attempt to get argm|(?:not enough|too many) values to unpack|must not contain infs or NaNs|"
    r"cannot reshape array of size|need at least one array")
_VALUE_OR_TYPE = re.compile(r"\b(?:ValueError|TypeError): (.*)", re.S)


def market_dependent(message: str) -> bool:
    """An error the market's numbers could cause or spare (`_MARKET_ERRORS`, `_MARKET_VALUES`): never a refusal."""
    text = str(message or "")
    if _MARKET_ERRORS.search(text):
        return True
    m = _VALUE_OR_TYPE.search(text)
    return bool(m and _MARKET_VALUES.search(m.group(1)))


# ------------------------------------------------------------------------------------------------ what refuses
#: The ctx's own classes. The program cannot make one: an error that names one of them is about the ctx object itself,
#: and one it raises for its type (a field it lacks, `[...]`, iteration, a call, arithmetic) it raises on every market.
CTX_CLASSES = frozenset({"ChainView", "UnderlyingView", "Ctx"})
#: The type each ctx field ALWAYS has (league/gym/ctx.py `build_ctx`, `ChainView`, `UnderlyingView`), as an error names
#: it; a dict or a list carries which one it is, so a key can be checked against the keys it can ever hold. A view field
#: can also be None (a root without data now): an error on a None never refuses.
_CTX_TYPES = {"positions": "list:positions", "orders": "list:orders", "closed": "list:closed", "rejects": "list:rejects",
              "roots": "tuple:roots", "chains": "dict:chains", "underlyings": "dict:underlyings", "rules": "dict:rules",
              "params": "dict:params", "events": "dict:events", "events_next": "dict:events", "chain": "ChainView",
              "under": "UnderlyingView", "minute": "int", "open_minute": "int", "close_minute": "int",
              "minutes_to_close": "int", "weekday": "int", "cash": "float", "equity": "float", "budget": "float",
              "buying_power": "float", "root": "str"}
_CHAIN_TYPES = {"root": "str", "spot": "float", "minute": "int", "n": "int",
                **{name: "numpy.ndarray" for name in ("id", "dte", "strike", "is_call", "bid", "ask", "mid", "spread",
                                                      "bid_size", "ask_size", "oi", "expiries", "iv", "delta", "gamma",
                                                      "theta", "vega")}}
_UNDER_TYPES = {"root": "str", "volume_coverage": "dict:coverage",
                **{name: "float" for name in ("price", "open", "high", "low", "prior_close", "volume", "prior_volume")},
                **{name: "numpy.ndarray" for name in ("prices", "closes", "opens", "highs", "lows", "minute_volumes",
                                                      "daily_volumes")}}
#: What one entry of a ctx container is (a position row, a chain, a root's rules, an event's flag).
_ITEMS = {"dict:chains": "ChainView", "dict:underlyings": "UnderlyingView", "dict:rules": "dict:rule",
          "dict:events": "bool", "list:positions": "dict:position", "list:orders": "dict:order",
          "list:closed": "dict:closed", "list:rejects": "str", "tuple:roots": "str"}
#: Builtins that iterate their positional arguments.
_ITERATING = frozenset({"list", "tuple", "set", "frozenset", "dict", "sorted", "sum", "min", "max", "any", "all", "zip",
                        "enumerate", "map", "filter", "reversed", "iter"})
#: The TypeErrors that say a ctx object was used as something its type is not: a number, a sequence, a function.
_CTX_CLASS_TYPE_ERRORS = (
    r"^'(\w+)' object is not (?:subscriptable|iterable|callable)",
    r"^'(\w+)' object does(?:n't| not) support item (?:assignment|deletion)",
    r"^argument of type '(\w+)' is not (?:a container or )?iterable", r"^cannot unpack non-iterable (\w+) object",
    r"^object of type '(\w+)' has no len\(\)", r"^type (\w+) doesn't define __round__ method",
    r"argument must be [^']*, not '(\w+)'", r"^'(\w+)' object cannot be interpreted as an integer",
    r"^bad operand type for [^:]+: '(\w+)'", r"^unsupported operand type\(s\) for [^:]+: '(\w+)' and '\w+'",
    r"^unsupported operand type\(s\) for [^:]+: '\w+' and '(\w+)'",
    r"^'[^']+' not supported between instances of '(\w+)' and '\w+'",
    r"^'[^']+' not supported between instances of '\w+' and '(\w+)'",
)


def _base(kind: str | None) -> str | None:
    return None if kind is None else kind.split(":", 1)[0]


def _literal_params(tree: ast.Module, overrides: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The program's PARAMS as the Gym binds them (the literal declaration with the overrides, `merge_params`); None
    when the declaration is not a literal dict."""
    try:
        from ..gym.safety import params_declaration

        declared = ast.literal_eval(params_declaration(tree).value)
    except Exception:  # noqa: BLE001 - not a literal: no key is known to be missing
        return None
    if not isinstance(declared, dict):
        return None
    out = {str(k): (list(v) if isinstance(v, (list, tuple)) else v) for k, v in declared.items()}
    for key, value in (overrides or {}).items():
        out[str(key)] = list(value) if isinstance(value, (list, tuple)) else value
    return out


class _Source:
    """The program's source, read to locate a runtime error at its line and name what the failing expression's receiver
    is (`kind`). Nothing is guessed: a receiver is a ctx field only when every binding of every name on the way to it
    resolves to one (an alias assigned once from ctx, a loop over a ctx container, decide's own parameter, a closure's
    or a helper's parameter named `ctx`); anything else is unknown, and an unknown receiver never refuses."""

    SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    #: Python 3's comprehensions are scopes of their own: their targets are theirs, not the enclosing function's (only
    #: an assignment expression inside one binds in the function around it, PEP 572).
    COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

    def __init__(self, code: str, roots: Sequence[str], params: Mapping[str, Any] | None):
        import builtins

        from ..gym.events import EVENT_NAMES
        from ..gym.runtime import _SAFE_BUILTIN_NAMES
        from ..gym import venue as V

        self.tree = ast.parse(code)
        self.parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                self.parents[child] = node
        self.params = _literal_params(self.tree, params)
        self.domains: dict[str, frozenset[str] | None] = {
            "dict:chains": frozenset(str(r).upper() for r in roots), "dict:underlyings": frozenset(str(r).upper() for r in roots),
            "dict:rules": frozenset(str(r).upper() for r in roots), "dict:events": frozenset(EVENT_NAMES),
            "dict:rule": frozenset(V.rules_for("SPY").as_dict()),
            "dict:params": None if self.params is None else frozenset(self.params)}
        stored: dict[str, int] = {}
        for node in ast.walk(self.tree):
            for name in self._bound_names(node):
                stored[name] = stored.get(name, 0) + 1
        self.stored = stored
        self.builtins = {n for n in _SAFE_BUILTIN_NAMES if callable(getattr(builtins, n, None)) and n not in stored}
        self.defs = {node.name for node in self.tree.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and stored.get(node.name) == 1}
        self.modules: dict[str, Any] = {}
        for node in self.tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    if stored.get(name) == 1 and alias.name in ("math", "numpy"):
                        self.modules[name] = __import__(alias.name)
        self.readonly_params = self._params_readonly()
        #: The program assigns or deletes an attribute somewhere: it could have replaced a ctx field (Ctx's slots take an
        #: assignment) on some markets only, so no field's type is certain (`_misuse`).
        self.stored_attrs = any(isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Store, ast.Del))
                                for n in ast.walk(self.tree))
        self._bindings: dict[Any, dict[str, list[tuple]]] = {}
        self._readonly: dict[str, bool] = {}

    @staticmethod
    def _bound_names(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            return [node.id]
        if isinstance(node, ast.arg):
            return [node.arg]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return [node.name]
        if isinstance(node, ast.alias):
            return [node.asname or node.name.split(".")[0]]
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            return list(node.names)
        if isinstance(node, ast.ExceptHandler) and node.name:
            return [node.name]
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            return [node.name]
        if isinstance(node, ast.MatchMapping) and node.rest:
            return [node.rest]
        return []

    def _params_readonly(self) -> bool:
        """PARAMS is only ever read after its declaration (a key, `.get`, `.keys`/`.items`/`.values`, `in`, `len`):
        then its keys are exactly the declared ones on every call, and a key it lacks is never there."""
        if self.params is None:
            return False
        try:
            from ..gym.safety import params_declaration

            declaration = params_declaration(self.tree)
        except Exception:  # noqa: BLE001
            return False
        target = declaration.targets[0] if isinstance(declaration, ast.Assign) else declaration.target
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.Global, ast.Nonlocal)) and "PARAMS" in node.names:
                return False
            if not isinstance(node, ast.Name) or node.id != "PARAMS" or node is target:
                continue
            parent = self.parents.get(node)
            if not isinstance(node.ctx, ast.Load):
                return False
            if isinstance(parent, ast.Subscript) and parent.value is node and isinstance(parent.ctx, ast.Load):
                continue
            if isinstance(parent, ast.Attribute) and parent.attr in ("get", "keys", "items", "values") and \
                    isinstance(self.parents.get(parent), ast.Call) and self.parents[parent].func is parent:
                continue
            if isinstance(parent, ast.Compare) and node is not parent.left and \
                    all(isinstance(op, (ast.In, ast.NotIn)) for op in parent.ops):
                continue
            if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == "len" \
                    and "len" in self.builtins:
                continue
            return False
        return True

    # -------------------------------------------------------------- names
    def scope(self, node: ast.AST) -> ast.AST | None:
        """The function, lambda or comprehension whose local names `node` sees first; None: the module. As Python
        evaluates them: a comprehension's first iterable and a function's or lambda's default values in the scope around
        it."""
        inner, child, parent = None, node, self.parents.get(node)
        while parent is not None:
            if isinstance(parent, self.SCOPES):
                if not (child is parent.args and inner is not None and
                        any(inner is d for d in [*parent.args.defaults, *parent.args.kw_defaults])):
                    return parent
            elif isinstance(parent, self.COMPREHENSIONS):
                if not (parent.generators and child is parent.generators[0] and inner is parent.generators[0].iter):
                    return parent
            inner, child, parent = child, parent, self.parents.get(parent)
        return None

    def bindings(self, scope: ast.AST) -> dict[str, list[tuple]]:
        """Every binding of every name local to `scope`, as ("ctx",), ("expr", node), ("item", iterable),
        ("key", mapping), ("value", mapping), ("int",) or ("unknown",). A comprehension binds its targets only; a
        function binds none of its comprehensions' targets, and a name a function nested in it declares `nonlocal` is
        rebound there, so it is unknown here too."""
        if scope in self._bindings:
            return self._bindings[scope]
        out: dict[str, list[tuple]] = {}
        add = lambda name, how: out.setdefault(name, []).append(how)  # noqa: E731
        if isinstance(scope, self.COMPREHENSIONS):
            for generator in scope.generators:
                self._loop(generator.target, generator.iter, add)
            self._bindings[scope] = out
            return out
        args = scope.args
        positional = [*args.posonlyargs, *args.args]
        first = positional[0].arg if positional else None
        is_decide = isinstance(scope, ast.FunctionDef) and scope.name == "decide" and self.scope(scope) is None
        for arg in [*positional, *args.kwonlyargs, *([args.vararg] if args.vararg else []),
                    *([args.kwarg] if args.kwarg else [])]:
            add(arg.arg, ("ctx",) if (arg.arg == "ctx" or (is_decide and arg.arg == first)) and arg not in
                (args.vararg, args.kwarg) else ("unknown",))
        body = scope.body if isinstance(scope.body, list) else [scope.body]
        todo = list(body)
        while todo:
            node = todo.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                # Its body is its own scope; what runs here is its decorators and default values. A `nonlocal` anywhere
                # inside it may rebind one of this scope's names (or a scope's between): unknown here.
                if not isinstance(node, ast.Lambda):
                    add(node.name, ("unknown",))
                    todo.extend(node.decorator_list)
                if not isinstance(node, ast.ClassDef):
                    todo.extend([*node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)])
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Nonlocal):
                        for name in inner.names:
                            add(name, ("unknown",))
                continue
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    self._assign(target, node.value, add)
            elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and isinstance(node.target, ast.Name):
                if getattr(node, "value", None) is not None:
                    add(node.target.id, ("expr", node.value))
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                self._loop(node.target, node.iter, add)
            elif isinstance(node, ast.comprehension):
                pass  # its targets are the comprehension's own (`COMPREHENSIONS`); a walrus inside it is still this scope's
            else:
                for name in self._bound_names(node):
                    if not (isinstance(node, ast.Name) and self._handled(node)):
                        add(name, ("unknown",))
            todo.extend(ast.iter_child_nodes(node))
        self._bindings[scope] = out
        return out

    def _handled(self, name: ast.Name) -> bool:
        """A stored Name the Assign, AnnAssign, NamedExpr, For or comprehension above it already recorded."""
        node: ast.AST = name
        parent = self.parents.get(node)
        while isinstance(parent, (ast.Tuple, ast.List, ast.Starred)):
            node, parent = parent, self.parents.get(parent)
        if isinstance(parent, ast.Assign) and node in parent.targets:
            return True
        if isinstance(parent, (ast.AnnAssign, ast.NamedExpr)) and parent.target is node and \
                getattr(parent, "value", None) is not None and node is name:
            return True
        return isinstance(parent, (ast.For, ast.AsyncFor, ast.comprehension)) and parent.target is node

    def _assign(self, target: ast.AST, value: ast.AST, add: Callable[[str, tuple], None]) -> None:
        if isinstance(target, ast.Name):
            add(target.id, ("expr", value))
        elif isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)) and \
                len(target.elts) == len(value.elts) and not any(isinstance(e, ast.Starred) for e in target.elts):
            for t, v in zip(target.elts, value.elts):
                self._assign(t, v, add)
        else:
            for node in ast.walk(target):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    add(node.id, ("unknown",))

    def _loop(self, target: ast.AST, iterable: ast.AST, add: Callable[[str, tuple], None]) -> None:
        if isinstance(target, ast.Name):
            add(target.id, ("item", iterable))
            return
        if isinstance(target, (ast.Tuple, ast.List)) and len(target.elts) == 2 and \
                all(isinstance(e, ast.Name) for e in target.elts) and isinstance(iterable, ast.Call) and \
                not iterable.keywords:
            func = iterable.func
            if isinstance(func, ast.Attribute) and func.attr == "items" and not iterable.args:
                add(target.elts[0].id, ("key", func.value))
                add(target.elts[1].id, ("value", func.value))
                return
            if isinstance(func, ast.Name) and func.id == "enumerate" and "enumerate" in self.builtins and \
                    len(iterable.args) == 1:
                add(target.elts[0].id, ("int",))
                add(target.elts[1].id, ("item", iterable.args[0]))
                return
        for node in ast.walk(target):
            if isinstance(node, ast.Name):
                add(node.id, ("unknown",))

    # -------------------------------------------------------------- kinds
    def kind(self, node: ast.AST, depth: int = 0) -> str | None:
        """What `node` always is when it is a ctx field or a part of one (`_CTX_TYPES`); None: unknown."""
        if depth > 24:
            return None
        if isinstance(node, ast.Name):
            return self._name(node.id, self.scope(node), depth)
        if isinstance(node, ast.Attribute):
            owner = self.kind(node.value, depth + 1)
            table = {"Ctx": _CTX_TYPES, "ChainView": _CHAIN_TYPES, "UnderlyingView": _UNDER_TYPES}.get(owner or "")
            return table.get(node.attr) if table else None
        if isinstance(node, ast.Subscript):
            owner = self.kind(node.value, depth + 1)
            if owner is None:
                return None
            if isinstance(node.slice, ast.Slice):
                return owner if owner.startswith(("list:", "tuple:")) else None
            if owner == "dict:params":
                return self._param(node.slice)
            return _ITEMS.get(owner)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and not node.keywords:
            owner = self.kind(node.func.value, depth + 1)
            if owner is None:
                return None
            if node.func.attr == "get" and owner.startswith("dict:") and (
                    len(node.args) == 1 or len(node.args) == 2 and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value is None):
                return self._param(node.args[0]) if owner == "dict:params" else _ITEMS.get(owner)
            if node.func.attr == "copy" and not node.args and owner.startswith(("list:", "dict:")):
                return owner
        return None

    def _param(self, key: ast.AST) -> str | None:
        if self.params is None or not isinstance(key, ast.Constant) or key.value not in self.params:
            return None
        value = self.params[key.value]
        return {bool: "bool", int: "int", float: "float", str: "str", list: "list:param"}.get(type(value))

    def _name(self, name: str, scope: ast.AST | None, depth: int) -> str | None:
        while scope is not None:
            bound = self.bindings(scope).get(name)
            if bound is not None:
                kinds = {self._binding(how, scope, depth + 1) for how in bound}
                return kinds.pop() if len(kinds) == 1 and None not in kinds else None
            scope = self.scope(scope)
        return "dict:params" if name == "PARAMS" and self.readonly_params else None

    def _binding(self, how: tuple, scope: ast.AST, depth: int) -> str | None:
        tag = how[0]
        if tag == "ctx":
            return "Ctx"
        if tag == "int":
            return "int"
        if tag == "expr":
            return self.kind(how[1], depth)
        if tag in ("key", "value"):
            owner = self.kind(how[1], depth)
            if owner is None or not owner.startswith("dict:"):
                return None
            return "str" if tag == "key" else (None if owner == "dict:params" else _ITEMS.get(owner))
        if tag == "item":
            iterable = how[1]
            if isinstance(iterable, ast.Call) and isinstance(iterable.func, ast.Attribute) and not iterable.args \
                    and not iterable.keywords and iterable.func.attr in ("keys", "values"):
                owner = self.kind(iterable.func.value, depth)
                if owner is None or not owner.startswith("dict:"):
                    return None
                return "str" if iterable.func.attr == "keys" else (None if owner == "dict:params" else _ITEMS.get(owner))
            owner = self.kind(iterable, depth)
            if owner is None:
                return None
            if owner.startswith("dict:"):
                return "str"
            return _ITEMS.get(owner)
        return None

    # -------------------------------------------------------------- the line
    def at(self, line: int) -> list[ast.AST]:
        """Every expression and statement node that spans `line` (the Runner's line is the failing instruction's)."""
        return [node for node in ast.walk(self.tree) if isinstance(node, (ast.expr, ast.stmt, ast.comprehension))
                and getattr(node, "lineno", None) is not None and node.lineno <= line <= (node.end_lineno or node.lineno)]

    def known_callable(self, func: ast.AST) -> bool:
        """A callee that is certainly callable: a safe builtin or a module-level function the program never rebinds, or
        a function of math or numpy."""
        if isinstance(func, ast.Name):
            return func.id in self.builtins or func.id in self.defs
        chain = []
        while isinstance(func, ast.Attribute):
            chain.append(func.attr)
            func = func.value
        if not isinstance(func, ast.Name) or func.id not in self.modules or self._name(func.id, self.scope(func), 0) \
                is not None or func.id in self._locals_of(func):
            return False
        value = self.modules[func.id]
        for attr in reversed(chain):
            value = getattr(value, attr, None)
        return callable(value)

    def _locals_of(self, node: ast.AST) -> set[str]:
        scope, names = self.scope(node), set()
        while scope is not None:
            names |= set(self.bindings(scope))
            scope = self.scope(scope)
        return names

    #: What reads a dict without changing it or handing it on (`readonly`).
    READS = ("get", "keys", "items", "values", "copy")
    PURE = frozenset({"len", "list", "sorted", "set", "frozenset", "tuple", "any", "all", "enumerate", "zip", "iter",
                      "bool", "str", "max", "min", "sum", "reversed"})

    def readonly(self, kind: str) -> bool:
        """Every expression of `kind` (a ctx dict, built afresh for each call) is only read: by key, `.get`, `.keys`,
        `.items`, `.values`, `.copy`, a comparison, `len` and the like, a loop, a test, a format or an alias that is
        itself only read. A ctx dict the program writes to, mutates or hands on could hold a key on some markets only."""
        if kind not in self._readonly:
            self._readonly[kind] = all(self._read_only(node) for node in ast.walk(self.tree)
                                       if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Call))
                                       and not isinstance(getattr(node, "ctx", None), (ast.Store, ast.Del))
                                       and self.kind(node) == kind)
        return self._readonly[kind]

    def _read_only(self, node: ast.AST) -> bool:
        parent = self.parents.get(node)
        if isinstance(parent, ast.Subscript) and parent.value is node:
            return isinstance(parent.ctx, ast.Load)
        if isinstance(parent, ast.Attribute) and parent.value is node:
            call = self.parents.get(parent)
            called = isinstance(call, ast.Call) and call.func is parent
            return parent.attr in self.READS if called else (isinstance(parent.ctx, ast.Load)
                                                             and not hasattr(dict, parent.attr))
        if isinstance(parent, (ast.Compare, ast.Expr, ast.FormattedValue)):
            return True
        if isinstance(parent, (ast.If, ast.While, ast.IfExp, ast.Assert)) and parent.test is node:
            return True
        if isinstance(parent, ast.UnaryOp) and isinstance(parent.op, ast.Not):
            return True
        if isinstance(parent, (ast.For, ast.AsyncFor, ast.comprehension)) and parent.iter is node:
            return True
        if isinstance(parent, ast.Call) and node in parent.args:
            return isinstance(parent.func, ast.Name) and parent.func.id in self.PURE and parent.func.id in self.builtins
        if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and parent.value is node:
            targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
            return all(isinstance(t, ast.Name) and self._name(t.id, self.scope(t), 0) == self.kind(node) for t in targets)
        return False

    def only(self, receivers: Sequence[ast.AST], kind: str) -> str | None:
        """What the receivers that could be a `kind` are (`_what` of the first), when every one of them (unknown, or
        known to be one) is known to be one and there is one; None otherwise."""
        kinds = [self.kind(r) for r in receivers]
        relevant = [k for k in kinds if k is None or _base(k) == kind]
        return _what(relevant[0]) if relevant and all(k is not None for k in relevant) else None


def _a(name: str) -> str:
    return ("an " if name[:1].upper() in "AEIOU" else "a ") + name


def _what(kind: str) -> str:
    names = {"list:positions": "ctx.positions (a list)", "list:orders": "ctx.orders (a list)", "list:closed":
             "ctx.closed (a list)", "list:rejects": "ctx.rejects (a list)", "tuple:roots": "ctx.roots (a tuple)",
             "dict:chains": "ctx.chains", "dict:underlyings": "ctx.underlyings", "dict:rules": "ctx.rules",
             "dict:params": "the program's PARAMS (ctx.params)", "dict:events": "ctx.events", "dict:rule": "ctx.rules[root]"}
    return names.get(kind, f"{_a('ctx ' + str(_base(kind)))}")


def api_misuse(message: str, code: str, *, roots: Sequence[str] = (), params: Mapping[str, Any] | None = None) -> str | None:
    """Why a runtime error message (the Runner's `line N: Type: words`) is MARKET-INDEPENDENT MISUSE OF THE CTX API at
    that line of `code` (a short phrase), or None (`_misuse`). The classifier's own failure is None: it never refuses."""
    try:
        return _misuse(message, code, roots=roots, params=params)
    except Exception:  # noqa: BLE001 - an unreadable line is not misuse
        return None


def _misuse(message: str, code: str, *, roots: Sequence[str] = (), params: Mapping[str, Any] | None = None) -> str | None:
    """`api_misuse`. `roots`: the program's NEEDS roots (the only keys ctx.chains,
    ctx.underlyings and ctx.rules can hold); `params`: the run's overrides. Only an AttributeError, a TypeError, a
    KeyError or an IndexError; never one raised on a None or an empty value (`market_dependent`) or one this box may cause
    (`environmental`); and only when the failing expression is found on the line and its receiver is a ctx object of the
    type the error names (a ctx class by the error's own words; a list, a dict or a number by `_Source.kind`). A wrong
    argument count only on a call without keywords (a keyword is version-dependent, `environmental`). A KeyError
    only on a ctx dict the program never writes to or hands on (`_Source.readonly`), and nothing at all in a program that
    assigns an attribute anywhere (it could have replaced a ctx field on some markets only)."""
    text = str(message or "")
    m = re.match(r"line (\d+): ([\w.]+): (.*)", text, re.S)
    if not m or m.group(2) not in ("AttributeError", "TypeError", "KeyError", "IndexError"):
        return None
    line, error, said = int(m.group(1)), m.group(2), m.group(3).strip()
    if environmental(text) or "NoneType" in said:
        return None
    src = _Source(code, roots, params)
    nodes = src.at(line)
    if not nodes or src.stored_attrs:
        return None
    if error == "IndexError":  # a 1-D ctx array indexed in two dimensions: its words are not the market's
        if not re.match(r"too many indices for array: array is 1-dimensional, but \d+ were indexed", said):
            return None
        subs = [n.value for n in nodes if isinstance(n, ast.Subscript) and not isinstance(n.slice, (ast.Constant, ast.Slice))]
        return "a ctx array is one-dimensional" if src.only(subs, "numpy.ndarray") else None
    if market_dependent(text):
        return None
    if error == "AttributeError":
        m = re.match(r"'([\w.]+)' object has no attribute '(\w+)'", said)
        if not m:
            return None
        kind, attr = m.groups()
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("getattr", "delattr")
               and len(n.args) == 2 and not (isinstance(n.args[1], ast.Constant) and n.args[1].value != attr)
               for n in nodes):
            return None  # getattr(x, name) may have raised it, with a name the market chose
        found = [n.value for n in nodes if isinstance(n, ast.Attribute) and n.attr == attr]
        if not found:
            return None
        if kind in CTX_CLASSES:
            return f"{_a(kind)} has no `{attr}`"
        what = src.only(found, kind)
        return f"{what} has no `{attr}`" if what else None
    if error == "KeyError":
        m = re.fullmatch(r"'([^'\\]*)'", said)
        if not m:
            return None
        key, receivers = m.group(1), []
        for n in nodes:
            if isinstance(n, ast.Subscript) and not isinstance(n.ctx, ast.Store):
                if isinstance(n.slice, ast.Constant):
                    if n.slice.value == key:
                        receivers.append(n.value)
                elif not isinstance(n.slice, ast.Slice):
                    receivers.append(n.value)
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in (
                    "pop", "remove", "format", "format_map", "popitem", "__getitem__", "__delitem__"):
                receivers.append(n.func.value)
            elif isinstance(n, ast.Call) and not isinstance(n.func, ast.Attribute) and not src.known_callable(n.func):
                return None
            elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod) and isinstance(n.left, (ast.Constant, ast.JoinedStr)):
                return None
        kinds = [k for k in (src.kind(r) for r in receivers) if k is None or k.startswith("dict:")]
        if not kinds or any(k is None or src.domains.get(k) is None or key in src.domains[k] or not src.readonly(k)
                            for k in kinds):
            return None
        return f"`{key}` is never a key of {_what(kinds[0])}"
    # TypeError
    for pattern in _CTX_CLASS_TYPE_ERRORS:
        m = re.search(pattern, said)
        if m and m.group(1) in CTX_CLASSES:
            return f"{_a(m.group(1))} used as something it is not"
    m = re.match(r"'([\w.]+)' object (is not subscriptable|does(?:n't| not) support item \w+|is not callable|is not iterable)",
                 said) or re.match(r"argument of type '([\w.]+)' (is not (?:a container or )?iterable)", said)
    if m:
        kind, how = m.groups()
        if "subscriptable" in how or "support item" in how:
            receivers = [n.value for n in nodes if isinstance(n, ast.Subscript)]
        elif "callable" in how:
            receivers = [n.func for n in nodes if isinstance(n, ast.Call) and not src.known_callable(n.func)]
        else:
            receivers = []
            for n in nodes:
                if isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
                    receivers.append(n.iter)
                elif isinstance(n, ast.Compare):
                    receivers += [c for op, c in zip(n.ops, n.comparators) if isinstance(op, (ast.In, ast.NotIn))]
                elif isinstance(n, ast.Starred):
                    receivers.append(n.value)
                elif isinstance(n, ast.Assign) and any(isinstance(t, (ast.Tuple, ast.List)) for t in n.targets):
                    receivers.append(n.value)
                elif isinstance(n, ast.Call):
                    receivers += [a for a in n.args if not isinstance(a, ast.Starred)]
                    receivers += [k.value for k in n.keywords]
        what = src.only(receivers, kind)
        return f"{what} {how}" if what else None
    m = re.match(r"(list|tuple) indices must be integers or slices, not \w+", said)
    if m:
        what = src.only([n.value for n in nodes if isinstance(n, ast.Subscript)], m.group(1))
        return f"{what} is indexed by position" if what else None
    m = re.match(r"(?:([\w.]+)\.)?(\w+)\(\) (?:takes|missing|got)", said) or \
        re.match(r"()(\w+) expected (?:at least |at most )?\d+ arguments?, got \d+", said)
    if m:  # a ctx container's method called with the wrong number of positional arguments
        owner, method = m.groups()
        calls = [n for n in nodes if isinstance(n, ast.Call) and (
            isinstance(n.func, ast.Attribute) and n.func.attr == method or isinstance(n.func, ast.Name) and n.func.id == method)]
        if not calls or not all(isinstance(c.func, ast.Attribute) for c in calls):
            return None
        if any(c.keywords for c in calls):
            return None  # a keyword a newer Python may take (`str.replace(count=)` from 3.13): never the same everywhere
        kinds = [src.kind(c.func.value) for c in calls]
        if any(k is None or (owner and _base(k) != owner) for k in kinds):
            return None
        return f"{_what(kinds[0])}.{method}() takes other arguments"
    return None


def _declared(code: str, params: Mapping[str, Any] | None) -> dict[str, Any]:
    """The program's PARAMS keys (its literal declaration with the overrides), for the advice; the overrides alone when
    the declaration is not a literal."""
    try:
        return _literal_params(ast.parse(code), params) or dict(params or {})
    except (SyntaxError, ValueError, RecursionError):
        return dict(params or {})


def _located(message: str, code: str) -> tuple[int | None, str]:
    m = re.match(r"line (\d+):", str(message or ""))
    if not m:
        return None, ""
    line = int(m.group(1))
    lines = code.splitlines()
    return line, (lines[line - 1].strip()[:200] if 0 < line <= len(lines) else "")


def warnings_for(messages: Sequence[str], code: str, *, roots: Sequence[str] = (),
                 params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """What an advisory says of each error (the first WARNINGS): the Runner's message, its line and the line's source,
    the ctx API to use (`advice`) and, where the error could be the made-up market's or this box's, which."""
    declared = _declared(code, params)
    out = []
    for message in list(dict.fromkeys(str(m) for m in messages))[:WARNINGS]:
        line, source = _located(message, code)
        row: dict[str, Any] = {"error": message[:300], "line": line, "source": source,
                               "hint": advice(message, roots=roots, params=declared, source=source)}
        if environmental(message):
            row["may_be"] = "this box's Python, numpy or memory, not the Gym's"
        elif market_dependent(message):
            row["may_be"] = "the made-up market's numbers (an empty selection, a count, a None): the Gym's may spare it"
        out.append({k: v for k, v in row.items() if v not in (None, "")})
    return out


# ------------------------------------------------------------------------------------------------ the run
def _answer(status: str, why: str, **fields: Any) -> dict[str, Any]:
    return {"status": status, "why": why, "version": VERSION, **fields}


def _advisory(why: str, messages: Sequence[str], code: str, roots: Sequence[str], params: Mapping[str, Any] | None,
              **fields: Any) -> dict[str, Any]:
    """An advisory answer: `why`, and each error as `warnings`, the first's error, line, source and hint on top."""
    warned = warnings_for(messages, code, roots=roots, params=params)
    first = warned[0] if warned else {}
    return _answer("advisory", why, warnings=warned, **{k: first[k] for k in ("error", "line", "source", "hint") if k in first},
                   **fields)


def static_refusal(code: str) -> str | None:
    """Why the Gym's static code check refuses `code` (`league.gym.safety.check_program`: the imports, names and
    attributes it allows, no date, NEEDS, PARAMS and one decide(ctx), it compiles), or None. The only refusal at load:
    the check reads the source and runs none of it, and it is what the Gym's `load_program` runs first. None too when
    the check itself fails: the preflight never refuses on its own failure."""
    from ..gym.safety import CodeRefused, check_program

    try:
        check_program(code)
    except CodeRefused as exc:
        return str(exc) or "the program fails the code check"
    except Exception:  # noqa: BLE001 - the check's own failure is no refusal
        return None
    return None


#: What a load-stage advisory's warnings say the load failure may be (`run`).
LOAD_MAY_BE = ("this box's Python 3.11 and numpy 2.4 (the Gym's boxes run 3.12+ with numpy 2.5). The Gym may still load and "
               "run it, but the live path loads every program here on the House's 3.11 and numpy 2.4, so as written it can "
               "never practise or trade live: make it load on Python 3.11 with numpy 2.4 too")


def run(code: str, params: Mapping[str, Any] | None, decider: Any, *, universe: Sequence[str] | None = None,
        name: str = "preflight", deadline: float = DEADLINE_SECONDS, clock: Callable[[], float] = time.monotonic,
        capital: float | None = None) -> dict:
    """The preflight of one (code, params) on `decider` (a `league.live.decider` Decider or InlineDecider). `universe`: the
    run's roots (a program trades its NEEDS roots within them). `capital`: the run's (`gym.capital`; CAPITAL when None).
    {"status": "passed" | "advisory" | "refused" | "inconclusive", "why": ..., ...}: only "refused" stops the Train run.
    At load only the static code check refuses (`static_refusal`); any other load failure is advisory."""
    from ..live.decider import DeciderError, ProgramRefused

    began = clock()
    key = f"preflight:{hashlib.sha256((code + repr(sorted((params or {}).items()))).encode()).hexdigest()[:16]}:{began:.6f}"
    try:
        capital = float(capital) if capital is not None else CAPITAL
    except (TypeError, ValueError):
        capital = CAPITAL
    if not math.isfinite(capital) or capital <= 0:
        capital = CAPITAL
    try:
        info = decider.load(key, code, dict(params or {}), name)
    except ProgramRefused as exc:
        message = str(exc)
        static = static_refusal(code)
        if static is not None:  # the same source, the same check, on every box
            line, source = _located(static, code)
            return _answer("refused", "the program fails the Gym's static code check (league/gym/safety.py), which refuses "
                                      "it the same way on every box", stage="load", error=static[:500], line=line,
                           source=source, calls=0, hint="fix the rule the check names (league/CONTRACT.md and PROGRAM.md "
                                                        "say what a program may contain); nothing of the program ran")
        if "ran past" in message:
            return _answer("inconclusive", f"the load says nothing on this box: {message[:300]}", stage="load", calls=0)
        # The module body, NEEDS or PARAMS failed on this box's runtime (the House's, which the live path also uses): the
        # run goes ahead (the Gym may load it on 3.12+), but the program cannot practise or trade live until it loads here.
        out = _advisory("the program did not load on this box, though it passes the static code check (the only refusal at "
                        "load): its module body, NEEDS and PARAMS ran here on the House's Python 3.11 and numpy 2.4. The "
                        "Train run goes ahead (the Gym may load it on 3.12+), but the live path loads every program on this "
                        "same 3.11 runtime, so as written it can never practise or trade live: make it load on 3.11 too",
                        [message], code, (), params, stage="load", calls=0)
        out["house_unloadable"] = True
        for warning in out["warnings"]:  # a load reads no market: what differs is the runtime
            warning["may_be"] = LOAD_MAY_BE
        return out
    except DeciderError as exc:
        return _answer("inconclusive", f"the sandbox failed: {str(exc)[:300]}")
    needs = info["needs"]
    try:
        verdict = _decide_loop(code, params or {}, decider, key, needs, universe, began, deadline, clock, capital=capital)
    except DeciderError as exc:
        return _answer("inconclusive", f"the sandbox failed: {str(exc)[:300]}")
    finally:
        _drop(decider, key)
    if verdict["status"] != "refused":
        return verdict
    # THE OTHER MARKETS (`CONFIRMATIONS`): a fresh instance of the program on each. The refusal stands only when the same
    # exception type at the same line recurs, as a refusable streak, on every one (`_same`): a misuse behind a branch the
    # made-up numbers opened (a filter that kept something here, a vol in a band) is then advisory.
    calls, roots = int(verdict.get("calls") or 0), [str(r).upper() for r in needs["roots"]]
    first = verdict.get("messages") or [verdict["error"]]
    for regime in CONFIRMATIONS:
        label = REGIMES[regime].label
        again_key = f"{key}:{regime}"
        try:
            decider.load(again_key, code, dict(params or {}), name)
            again = _decide_loop(code, params or {}, decider, again_key, needs, universe, began, deadline, clock,
                                 regime=regime, capital=capital)
        except (ProgramRefused, DeciderError) as exc:
            return _advisory(f"decide raised a misuse of the ctx API on every call, but the sandbox failed on {label}, so "
                             f"it could not be confirmed there: {str(exc)[:200]}; the run goes ahead", first, code, roots,
                             params, calls=calls)
        finally:
            _drop(decider, again_key)
        calls += int(again.get("calls") or 0)
        if again["status"] != "refused" or not _same(again.get("error"), verdict.get("error")):
            err = str(again.get("error") or "")[:160]
            said = ("there decide did not raise" if again["status"] == "passed" else f"there it raised `{err}`" if err
                    else f"there: {str(again.get('why') or '')[:160]}")
            return _advisory(f"decide raised `{str(verdict.get('error') or '')[:200]}` on every call, a misuse of the ctx "
                             f"API on this market, but not at the same line on {label} ({said}): it may hang on a branch "
                             "the made-up numbers opened, so the run goes ahead", first, code, roots, params, calls=calls)
    verdict["why"] += ("; again, the same exception at the same line, on a saturated market (every selection filled, any "
                       "filter keeping contracts), on a sparser and a denser listing, on quotes one tick wide at twice the "
                       "vol and on quotes three times as wide at a lower vol (other price paths and levels)")
    verdict["calls"] = calls
    return verdict


def _drop(decider: Any, key: str) -> None:
    try:
        decider.drop(key)
    except Exception:  # noqa: BLE001 - dropping a runner never fails the preflight
        pass


def _kind(message: Any) -> tuple[str, str]:
    """An error's line and exception type (`line 12: TypeError: ...` -> ("12", "TypeError")): the same kind of error at
    the same place, whatever numbers it prints."""
    m = re.match(r"(?:line (\d+): )?([\w.]+)", str(message or ""))
    return (m.group(1) or "", m.group(2)) if m else ("", "")


def _same(again: Any, first: Any) -> bool:
    """`again` (another market's streak) is `first` recurring: the same exception type at the same line."""
    line, kind = _kind(again)
    return bool(line) and (line, kind) == _kind(first)


def _decide_loop(code: str, params: Mapping[str, Any], decider: Any, key: str, needs: Mapping[str, Any],
                 universe: Sequence[str] | None, began: float, deadline: float, clock: Callable[[], float], *,
                 regime: str = "listed", capital: float = CAPITAL) -> dict:
    from ..gym import venue as V
    from ..gym.events import EVENT_NAMES

    wanted = [str(r).upper() for r in needs["roots"]]
    roots = [r for r in wanted if not universe or r in {str(u).upper() for u in universe}]
    schedule = decision_minutes(needs)
    if not roots or not schedule:
        return _answer("passed", "the program has no decision in the run's roots and hours", calls=0)
    market = Market(roots, needs, regime=regime)
    rules = {r: V.rules_for(r).as_dict() for r in roots}
    quiet = {name: False for name in EVENT_NAMES}
    restarts = getattr(decider, "restarts", 0)
    calls = errors = timeouts = 0
    streak: list[tuple[int, int]] = []    # (session, call) of the current run of erring calls
    named: list[str] = []                 # the streak's errors the Runner's message list names (new in it at the call)
    unnamed = blind = False               # a streak error already in the list / one the full list could not take
    first_message = ""
    messages: list[str] = []

    def settle(status: str, why: str) -> dict:
        """A loop that ended without a refusable streak: `status`, or advisory when decide raised at all."""
        if errors and status == "passed":
            return _advisory(f"decide raised on {errors} of {calls} calls on {REGIMES[regime].label} ({why}); only a "
                             "misuse of the ctx API that raises on every call on every made-up market is refused, so the "
                             "run goes ahead", messages, code, wanted, params, calls=calls, errors=errors)
        extra = {"warnings": warnings_for(messages, code, roots=wanted, params=params)} if errors else {}
        return _answer(status, why, calls=calls, errors=errors, **extra)

    for s in range(SESSIONS):
        if s == SESSIONS - 1 and not streak:
            break  # the last session only confirms a streak still running at the end of the one before
        for k, mi in enumerate(schedule):
            if s and k >= STREAK and not streak:
                # A streak must span two sessions: one not running STREAK calls into a later session cannot, this session.
                return settle("passed", "no persistent error on the synthetic sessions")
            if clock() - began > deadline:
                return settle("inconclusive", f"the preflight's {deadline:.0f} s ran out after {calls} calls")
            token = s * 1000 + mi
            snaps = {(r, token): market.snapshot(r, s, mi) for r in roots}
            unders = {(r, int(needs["history"]), token): market.under(r, s, mi) for r in roots}
            job = {"key": key, "mi": token, "roots": roots, "minute": OPEN + mi, "open_minute": OPEN, "close_minute": CLOSE,
                   "weekday": market.weekdays[s], "positions": [], "orders": [], "cash": capital, "equity": capital,
                   "budget": capital, "buying_power": capital, "rules": rules, "events": quiet, "events_next": quiet,
                   "closed": [], "rejects": []}
            answer = decider.decide(snaps, unders, [job]).get(key) or {}
            stats = answer.get("stats")
            if answer.get("missing") or answer.get("skipped") or not isinstance(stats, Mapping) \
                    or getattr(decider, "restarts", 0) != restarts or int(stats.get("calls") or 0) != calls + 1:
                return settle("inconclusive", "the sandbox lost the program's runner")
            calls += 1
            raised = int(stats.get("errors") or 0) - errors
            errors = int(stats.get("errors") or 0)
            seen = [str(m) for m in stats.get("messages") or []]
            if int(stats.get("timeouts") or 0) > timeouts:
                messages = seen
                return settle("inconclusive", "a call ran past its time limit (this box is not a Gym box)")
            if answer.get("intents"):
                messages = seen
                return settle("passed", f"the program returned an intent at call {calls}; a flat account no longer "
                                        "mirrors the Gym's from there")
            if raised <= 0:
                streak, named, unnamed, blind, first_message = [], [], False, False, ""
                messages = seen
                continue
            # The Runner keeps the first RUNNER_MESSAGES distinct messages only: a call's error is named when it is new in
            # the list; one already there is one of the list's; one the full list did not take could be anything.
            new = [m for m in seen if m not in messages]
            if not streak:
                first_message = new[0] if new else ""
            named.extend(new)
            if raised > len(new):
                if len(messages) + len(new) >= RUNNER_MESSAGES:
                    blind = True
                else:
                    unnamed = True
            messages = seen
            streak.append((s, calls))
            if len(streak) >= STREAK and len({x[0] for x in streak}) >= 2:
                return _verdict(code, params, wanted, streak, named, unnamed, blind, first_message, seen, calls, errors)
    return settle("passed", "no persistent error on the synthetic sessions")


def _verdict(code: str, params: Mapping[str, Any], roots: Sequence[str], streak: Sequence[tuple[int, int]],
             named: Sequence[str], unnamed: bool, blind: bool, first_message: str, seen: Sequence[str], calls: int,
             errors: int) -> dict:
    """A streak long enough to refuse: refused (for the other markets to confirm, `run`) only when every error it may
    hold is known and is market-independent misuse of the ctx API (`api_misuse`); advisory otherwise."""
    span = f"{len(streak)} calls over {len({x[0] for x in streak})} synthetic sessions, before any intent"
    advisory = lambda why, shown: _advisory(  # noqa: E731
        f"decide raised on every call from call {streak[0][1]} ({span}), but {why}: the run goes ahead", shown, code,
        roots, params, calls=calls, errors=errors)
    if blind:
        return advisory(f"the Runner's list holds {RUNNER_MESSAGES} messages and the streak's error is not among them",
                        seen)
    candidates = list(dict.fromkeys([*named, *(seen if unnamed else ())]))
    if not first_message and len(candidates) == 1:
        first_message = candidates[0]
    if not first_message or not candidates:
        return advisory("the streak's first error cannot be told apart from earlier ones", seen)
    shown = [first_message, *[m for m in candidates if m != first_message], *seen]
    found = next((m for m in candidates if environmental(m)), None)
    if found:
        return advisory(f"the error may be this box's Python, numpy or memory, not the Gym's: {found[:200]}", shown)
    reasons = [api_misuse(m, code, roots=roots, params=params) for m in candidates]
    if not all(reasons):
        found = next(m for m, why in zip(candidates, reasons) if not why)
        if market_dependent(found):
            return advisory(f"the error could turn on the market's numbers, which are made up here: {found[:200]}", shown)
        return advisory(f"`{found[:200]}` is not a misuse of the ctx API that no market could spare (only such a misuse "
                        "is refused)", shown)
    line, source = _located(first_message, code)
    misuse = reasons[candidates.index(first_message)] if first_message in candidates else reasons[0]
    return _answer("refused", f"decide raised the same misuse of the ctx API ({misuse}) on every call from call "
                              f"{streak[0][1]} ({span})",
                   stage="decide", error=first_message[:500], line=line, source=source, calls=calls, errors=errors,
                   misuse=misuse, messages=[m[:200] for m in candidates[:4]],
                   hint=advice(first_message, roots=roots, params=_declared(code, params), source=source))


# ------------------------------------------------------------------------------------------------ the House's instance
#: The preflight child's uid and gid on the root House: not 65534, which the live and observe decider children run as.
#: Programs no Gym has run yet execute here, so a process that escaped the code check must not be able to signal or trace
#: the money path's decider (the kernel's kill and ptrace checks compare these uids). No process on the House runs as it.
PREFLIGHT_UID = 65533


def child_uids(pid: int) -> tuple[int, ...]:
    """A process's real and effective uid, from `/proc/<pid>/status` (as the parent's namespace sees them); () when it
    cannot be read."""
    try:
        with open(f"/proc/{int(pid)}/status", encoding="ascii", errors="replace") as status:
            for line in status:
                if line.startswith("Uid:"):
                    return tuple(int(x) for x in line.split()[1:3])
    except (OSError, ValueError):
        pass
    return ()


#: The preflight child's scheduling priority: the lowest. The House has one core, the live decider's child runs at nice
#: 5 (`decider.child_main`) and each call's limit is wall-clock time, so the live minute must win the core from a
#: preflight whenever both want it (a preflight call that then runs past its limit is inconclusive, never a refusal).
PREFLIGHT_NICE = 19
_POPEN = subprocess.Popen


def _lowest_priority(proc: Any) -> None:
    """Renice a freshly spawned preflight child to PREFLIGHT_NICE. The root House may renice its child whatever its uid;
    elsewhere it is the caller's own child. The child's own `os.nice(5)` at start then leaves it at the lowest either way.
    Only a real child is reniced (`_POPEN`, the class as imported, never a test's stand-in or its pid); one that cannot
    be still runs (the priority only orders the core)."""
    import os

    try:
        if isinstance(proc, _POPEN) and isinstance(proc.pid, int) and proc.pid > 0:
            os.setpriority(os.PRIO_PROCESS, proc.pid, PREFLIGHT_NICE)
    except (OSError, AttributeError, TypeError):
        pass


def _sandbox() -> Any:
    """`league.live.decider.Decider` under the preflight's own uid. Nothing of the decider is copied: the spawn is
    `Decider._spawn`, so every isolation rule it has or gains (fail-closed off a root House, the network-namespace probe
    and its retry window, the empty environment, the child's own limits, the read-only runtime copy) is the
    preflight's too. `Decider._spawn` builds the child's credentials and hands that very dict to `_namespace` (the
    probe runs under them) and then to `Popen`; `_namespace` here writes the preflight's uid into it. Should a later
    decider stop doing that, the child would run as 65534: `_spawn` then reads the child's uid back and kills a child
    that is not `PREFLIGHT_UID` before any program reaches it."""
    from ..live import decider as D

    class SandboxDecider(D.Decider):
        uid = PREFLIGHT_UID

        def _namespace(self, budget_seconds: float, credentials: Any) -> bool:
            if credentials:  # the root House's credentials (the child's): the preflight's own uid and gid
                credentials.update(user=self.uid, group=self.uid, extra_groups=[])
            return super()._namespace(budget_seconds, credentials)

        def _spawn(self, budget_seconds: float = 10.0) -> None:
            super()._spawn(budget_seconds)
            if self.isolated and self.proc is not None:
                uids = child_uids(self.proc.pid)
                if not uids or any(uid != self.uid for uid in uids):
                    self._kill()
                    raise D.DeciderError(f"the preflight's decider child runs as uid {uids or 'unknown'}, not "
                                         f"{self.uid}: it was killed before any program reached it")
            _lowest_priority(self.proc)

    return SandboxDecider


class Preflight:
    """The researcher's preflight: one sandboxed decider child for the process, one preflight at a time (the House has
    one core; a Gym run can wait a second, the live minute cannot). `decider` for tests (an InlineDecider)."""

    def __init__(self, decider: Any = None, *, deadline: float = DEADLINE_SECONDS, wait: float = 60.0):
        self._decider = decider
        self.deadline, self.wait = float(deadline), float(wait)
        self._lock = threading.Lock()

    def decider(self) -> Any:
        if self._decider is None:
            # max_errors: every call's own outcome is read (the preflight counts its streak itself, at the Gym's 25).
            self._decider = _sandbox()(timeout=1.0, max_errors=10 ** 9)
            atexit.register(self.close)  # the child and its read-only runtime copy go with the process
        return self._decider

    def __call__(self, code: str, params: Mapping[str, Any] | None = None, *, roots: Sequence[str] | None = None,
                 name: str = "preflight", capital: float | None = None) -> dict:
        began = time.monotonic()
        if not self._lock.acquire(timeout=self.wait):
            return _answer("inconclusive", "another preflight held the sandbox", seconds=0.0)
        try:
            out = run(code, params, self.decider(), universe=roots, name=name, deadline=self.deadline, capital=capital)
        finally:
            self._lock.release()
        out["seconds"] = round(time.monotonic() - began, 3)
        return out

    def close(self) -> None:
        if self._decider is not None and callable(getattr(self._decider, "close", None)):
            self._decider.close()


__all__ = ["VERSION", "STREAK", "SESSIONS", "PREFLIGHT_UID", "PREFLIGHT_NICE", "LISTING", "REGIMES", "CONFIRMATIONS", "CTX_CLASSES",
           "Market", "Preflight", "Regime", "advice", "decision_minutes", "environmental", "equity_step", "expiries",
           "listing", "market_dependent", "quote", "run", "saturated_strikes", "session_weekdays", "strikes", "vol_of",
           "api_misuse", "static_refusal", "warnings_for"]
