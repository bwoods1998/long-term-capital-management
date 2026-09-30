"""THE PREFLIGHT: a candidate program meets a small synthetic session in the decider's sandbox before a Train run is spent.

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
  unknown (NaN, as in the replay), the Gym's venue rules, and a flat account of the Gym's capital. It is called at the
  Gym's own decision minutes (`engine.Account.decision_minutes`). The market is made up; nothing here reads recorded
  data, so it is no trial and says nothing about profit.
- **When it refuses.** Only when the Gym would refuse or disqualify the same program on the same kind of input:
  1. `load` refuses it (the Gym's worker would refuse it identically), except a load that ran out of time or memory
     (this box is not a Gym box: that says nothing) or an `environmental` error (the House's Python, numpy and memory
     cap are not the Gym boxes');
  2. decide raised on `STREAK` (25, the Gym's `DEFAULT_MAX_ERRORS`) consecutive calls spanning at least two sessions,
     BEFORE the program returned any intent, and every error the streak may hold is named in the Runner's message
     list and is neither `environmental` nor `market_dependent` (an empty selection, a selection turned into one
     number, two selections of different lengths, a division by zero, a numeric key, a None: the made-up numbers could
     cause or spare those, on Python 3.11 and 3.14 alike). Until its first intent a Gym account is flat too, and an
     erring call returns no intent, so the Gym's account would stay exactly as flat as this one while the program
     erred: the only difference left is the market's numbers, which such an error does not depend on;
  3. and a decide refusal recurs (`_recurs`: the same exception at the same line, or saying the same thing at another)
     on a fresh instance of the program meeting each of the other markets (`CONFIRMATIONS`, `REGIMES`). Two bracket the
     listing: a sparser one of the same roots (`listing(sparse=True)`: one expiry a week, the next wider strike step)
     and a denser one (`listing(dense=True)`: an expiry every weekday and, where a root's step changes over Train, the
     next finer step as well as its own). A listing is one the Gym holds over a long stretch of Train, not on every day,
     and each admitted root's store lies between these two on every Train day (`LISTING`). So an error that turns on
     how many contracts a selection keeps is spared on one of them: a selection that keeps one contract on a coarser
     day keeps several on the listing (its truth value then raises) but not on the sparse one, and a selection the
     listing leaves empty (a calendar between two expiries it never lists on one day, then a STATE key never written) is
     filled on the dense one. The others are the listing again with other numbers at both ends: one-tick quotes, deep
     books and a higher vol; quotes three times as wide, thin books and a lower vol; each on its own price paths at
     another level (the dense market has its own too, at a vol between). An error that follows from the numbers
     without saying so (a liquidity filter that keeps nothing, then a STATE key it never wrote or a local it never set)
     is spared on one of them.
  Anything else passes: the first intent ends the preflight (a flat account no longer mirrors the Gym's), as does a
  call past its time limit, a decider failure or the preflight's own deadline. The preflight never blocks on its own
  failure. A clean program costs one session plus `STREAK` calls of the next (a streak that begins later could only
  be confirmed by yet another session, and is left to the Gym).
- **What the researcher gets.** The exception, the line and its source, the call it began at, and the ctx API it
  should have used (`advice`): no Gym job, no version and no trial are made, and the refusal is written in the family's
  notebook.

numpy on the calling side (the House has it; the Gym's store and pyarrow are not needed). Python 3.11+.
"""

from __future__ import annotations

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

VERSION = "preflight-v5"
#: Consecutive erring calls that refuse: the Gym's own disqualification count (`league.gym.runtime.DEFAULT_MAX_ERRORS`).
STREAK = 25
#: Synthetic sessions at most (a third only to confirm a streak that began in the second).
SESSIONS = 3
#: Distinct messages a Gym Runner keeps (`league.gym.runtime.Runner._error`): an error past them is not reported.
RUNNER_MESSAGES = 10
#: The account's capital: the Gym's default (`swarm.json` `gym.capital` overrides it for real runs; a flat account's
#: numbers are the same either way up to scale).
CAPITAL = 10_000.0
#: The preflight's wall-clock budget; past it the program passes (inconclusive).
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
#: dense one, every weekday and the next finer step's strikes too; a refusal must recur on both. Every admitted root's
#: store lies inside that bracket on every Train day, whatever it listed that day: SPY and QQQ list every weekday from
#: late 2022 (Monday, Wednesday and Friday before), SPXW from spring 2022 (the same before), XSP every weekday in the
#: store's 2024 sample (fewer earlier), IWM Monday, Wednesday and Friday for most of Train (every weekday from spring
#: 2024), all at a fixed step. Each is listed here with its latest schedule but IWM; the listing only decides what the
#: first market shows, the bracket decides a refusal. Every other root lists Fridays (the weeklies and the monthly). A
#: root with monthlies only is coarser than the sparse listing: SPX (the AM-settled root; its weeklies are SPXW) is one,
#: and like a stock without weeklies it is not an admitted root; admitting one needs its schedule here first. The index
#: ETFs and GLD list $1 strikes and SPX/SPXW $5 at any price; a stock or another ETF lists by its price (`equity_step`:
#: $0.5 under $75, $1 under $150, $2.5 under $500, $5 above). A root not named here is a $100 stock with Friday
#: expiries. When in doubt, list a root as it lists on most Train days: the bracket covers one expiry schedule and one
#: strike step either side of it, and nothing past that.
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
#: quotes no wider than the Gym's own synthetic store (3% of the mid, `gym.synth.generate`), so a liquidity filter that
#: keeps contracts there keeps them here.
NEAR_WIDTH = {"SPY": 0.004, "QQQ": 0.004, "IWM": 0.008, "SPXW": 0.01, "SPX": 0.01}
DEFAULT_WIDTH = 0.015
WIDENING, WIDEST_Z = 0.5, 4.0


class Regime(NamedTuple):
    """One synthetic market's numbers (`REGIMES`): its listing (`chain`: "listed", "sparse" or "dense", `listing`), its
    quotes' width (a multiple of `quote`'s; 0: every quote one tick wide, the venue's narrowest), each root's vol and
    price as multiples of `VOLS` and the listing's price, its books' sizes (a range, drawn evenly on a log scale) and open
    interest (the most), and its own price paths (`salt`)."""

    label: str
    chain: str
    width: float
    vol: float
    level: float
    sizes: tuple[int, int]
    oi: int
    salt: int


#: THE MARKETS a program meets. It is first run on the listing with typical quotes on books of every size, from one
#: contract to thousands. A refusal must then recur (`_recurs`: the same exception at the same line, or saying the same
#: thing at another) on each of the others in turn (`CONFIRMATIONS`): the listing's bracket (`LISTING`), the same roots
#: listed more thinly on the same numbers and listed more densely on its own price paths at a vol between the listing's
#: and the tight market's; and the listing again with other numbers at both ends: every quote one tick wide (the venue's
#: narrowest) on deep books at twice the vol and a higher price, whose richer premiums make those ticks the smallest
#: share of a mid; and quotes three times as wide on thin books at a lower vol and price, the widest share; each on its
#: own price paths. An error that turns on how many contracts a selection keeps, or on a quote's width, a vol, a size or
#: a price (a liquidity filter that keeps nothing, then a STATE key it never wrote) is spared on one of them, and so
#: never refuses. A filter that keeps nothing even on one-tick quotes at twice the vol would keep nothing on almost every
#: Gym day either (no quote there is narrower than a tick), and 25 errors in a run disqualify it there. The price is a
#: misuse behind a gate on the numbers that none of these markets opens (a z-score, a band of vols between theirs): it is
#: left to the Gym.
REGIMES = {
    "listed": Regime("the listed chain", "listed", 1.0, 1.0, 1.0, (1, 5_000), 50_000, 1),
    "sparse": Regime("a sparser listing of the same roots (one expiry a week, a wider strike step)", "sparse", 1.0, 1.0,
                     1.0, (1, 5_000), 50_000, 1),
    "dense": Regime("a denser listing of the same roots (an expiry every weekday, a finer strike step; another price "
                    "path, a vol between)", "dense", 1.0, 1.4, 1.05, (1, 5_000), 50_000, 4),
    "tight": Regime("the listing quoted one tick wide on deep books (twice the vol, another price path, a higher price)",
                    "listed", 0.0, 2.0, 1.1, (200, 5_000), 500_000, 2),
    "wide": Regime("the listing quoted three times as wide on thin books (a lower vol, another price path, a lower price)",
                   "listed", 3.0, 0.6, 0.9, (1, 40), 3_000, 3),
}
CONFIRMATIONS = ("sparse", "dense", "tight", "wide")


def equity_step(price: float) -> float:
    """The strike step a stock's weekly lists near the money at `price` (`LISTING`)."""
    return 0.5 if price < 75 else 1.0 if price < 150 else 2.5 if price < 500 else 5.0


def listing(root: str, *, sparse: bool = False, dense: bool = False) -> tuple[float, float, tuple[int, ...]]:
    """(price, strike step, expiry weekdays) of `root` (`LISTING`). `sparse`: the same root listed more thinly, one
    expiry a week (Fridays) and, unless the root's step never changes, the next wider strike step. `dense`: listed more
    densely, an expiry every weekday and, unless the root's step never changes, the next finer step (`strikes` lists it
    beside the root's own). A refusal on the listing must recur on both (`run`): a listing one step or schedule finer or
    coarser than the Gym's on some day (a selection that holds one contract there holds several here, or one that holds
    a contract there holds none here) then never refuses on its own."""
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


def vol_of(root: str) -> float:
    """`root`'s implied vol in the synthetic market (`VOLS`)."""
    return VOLS.get(str(root).upper(), DEFAULT_VOL)


def quote(root: str, mid: Any, z: Any, width: float = 1.0) -> tuple[Any, Any]:
    """Bid and ask about each `mid` (THE QUOTES, `NEAR_WIDTH`): `width` times the root's near-money width as a share of
    the mid, wider by WIDENING for each standard deviation of moneyness `z` (up to WIDEST_Z), to the nearest tick of the
    venue's at that premium and never less than one (`venue.leg_tick`); `width` 0 quotes every contract one tick wide."""
    import numpy as np

    from ..gym import venue as V

    root = str(root).upper()
    mid = np.asarray(mid, dtype=np.float64)
    tick = np.where(mid < 3.0, V.leg_tick(root, 0.0), V.leg_tick(root, 3.0))
    share = NEAR_WIDTH.get(root, DEFAULT_WIDTH) * float(width) * (1.0 + WIDENING * np.minimum(np.abs(z), WIDEST_Z))
    ticks = np.maximum(1.0, np.round(share * mid / tick))
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


class Market:
    """Synthetic sessions for a program's NEEDS (the module docstring) on each root's chain (`listing`, `strikes`) with
    the numbers of `regime` (`REGIMES`: "listed" first; `sparse` is the "sparse" one). Its sessions fall on the weekdays
    of the listing's (`session_weekdays`), the dense one's too, so on each session the dense chain lists every expiry the
    listing does and, about its own open, the listing's strikes with the finer step's beside them. Deterministic: the
    same roots, NEEDS and regime make the same market."""

    def __init__(self, roots: Sequence[str], needs: Mapping[str, Any], *, sparse: bool = False, regime: str = "listed"):
        import numpy as np

        from ..gym import greeks as G

        self.roots = tuple(roots)
        self.needs = dict(needs)
        self.regime = REGIMES["sparse" if sparse else regime]
        self.chain = self.regime.chain
        self.sparse, self.dense = self.chain == "sparse", self.chain == "dense"
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
            sessions = []
            for s in range(SESSIONS):
                i = history + s
                prior = np.array(bars[i - history:i], dtype=np.float64).reshape(-1, 4)
                path = paths[i]
                weekday = self.weekdays[s]
                dtes = expiries(root, weekday, dte_min, dte_max, weekdays)
                ks = strikes(root, float(path[0]), chain=self.chain)  # the store's strikes a side of the open's money
                dte = np.repeat(np.array(dtes, dtype=np.int64), ks.size * 2)
                strike = np.tile(np.repeat(ks, 2), len(dtes))
                is_call = np.tile(np.array([True, False]), ks.size * len(dtes))
                n = strike.size
                sessions.append({"weekday": weekday, "path": path, "prior": prior, "dte": dte, "strike": strike,
                                 "is_call": is_call, "oi": rng.integers(0, self.regime.oi, n),
                                 "rng": _rng(root, 100 * self.regime.salt + s)})
            self.days[root] = sessions
        self._G = G

    def snapshot(self, root: str, session: int, mi: int) -> Any:
        """The root's chain at minute `mi` of the session (a `Snapshot`, as the replay makes one): Black-Scholes mids on
        the root's vol with a skew, quoted about them (`quote`), with the regime's sizes (evenly on a log scale, so a
        size filter at any depth in the range keeps some contracts and drops others, at any quote width)."""
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
        sigma = self.vols[root] * (1.0 - 1.5 * m + 8.0 * m * m)
        mid = self._G.bs_price(spot, strike, years, RATE, sigma, is_call)
        bid, ask = quote(root, mid, m / (sigma * np.sqrt(years)), self.regime.width)
        rng, (low, high) = day["rng"], self.regime.sizes
        sizes = lambda: np.floor(np.exp(rng.uniform(math.log(low), math.log(high + 1), n))).astype(np.int64)  # noqa: E731
        return Snapshot(root, OPEN + mi, spot, dte, strike, is_call, bid, ask, sizes(), sizes(), oi=day["oi"], rate=RATE,
                        close_minute=CLOSE)

    def under(self, root: str, session: int, mi: int) -> Any:
        """The root's underlying at minute `mi` (as `engine.DayData.under`: prices from the open, prior sessions, volume
        unknown as in a replay without first-observation receipts)."""
        from ..gym.ctx import underlying_view

        day = self.days[root][session]
        prior = day["prior"]
        return underlying_view(root, day["path"][: mi + 1], opens=prior[:, 0], highs=prior[:, 1], lows=prior[:, 2],
                               closes=prior[:, 3], volume_provenance="historical_without_asof",
                               daily_volume_provenance="unavailable")


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
    if re.search(r"'(ChainView|UnderlyingView|Ctx)' object is not (subscriptable|iterable)", text):
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


def environmental(message: str) -> bool:
    """An error that could be this box's and not the Gym's: the House runs Python 3.11 with numpy 2.4 and caps the
    decider child at 2 GB, the Gym's boxes run 3.12+ with numpy 2.5 (requirements-gym.txt) and give a worker 6 GB. So a
    module attribute one version has and the other lacks (`math.sumprod`, a numpy function), a keyword, a method a
    newer Python gave a number, a string or a numpy value (`int.is_integer`), memory, or recursion depth says nothing
    about the program. Such an error never refuses."""
    text = str(message or "")
    if ("unexpected keyword argument" in text or "No module named" in text or "MemoryError" in text
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
#: found nothing on this market. The synthetic market is not the real one, so such an error proves nothing about the Gym
#: and never refuses (the Gym still judges it). First by the exception's type alone, whatever its words: an index past an
#: empty or short array, a division by zero, an exhausted search, an overflow, a singular fit, a None, a numeric key (a
#: strike, or a strike's text), a pop from an empty set or dict.
_MARKET_ERRORS = re.compile(r"\b(IndexError|ZeroDivisionError|StopIteration|OverflowError|FloatingPointError|LinAlgError|"
                            r"NoneType|KeyError: -?[\d.]+|KeyError: '-?\d+(?:\.\d+)?'|KeyError: \(|KeyError: np\.|"
                            r"KeyError: nan|KeyError: '(?:pop from an empty set|popitem\(\): dictionary is empty)')")
#: Then a ValueError or a TypeError by what it says, each wording raised on the House's runtime (Python 3.11, numpy 2.4.4)
#: and on 3.14 with numpy 2.5.3 (the tests raise every one on the runtime they run on; CI runs both, and the wordings
#: below are the same on both but where named). An empty selection says "empty", "non-empty", "size 0" or "zero-size"
#: (min() and max(): 3.11's "arg is an empty sequence", 3.14's "iterable argument is empty"; argmin, a reduction,
#: np.interp, np.polyfit, the truth value of an empty array), or prints a shape with a zero in it ("(0,)", "(3, 0)"), or
#: is too small for what was asked of it (np.gradient, np.partition's kth, a count less one as a length). Turning a
#: selection into one number cannot tell an empty one from a crowded one (`.item()`, `np.squeeze(axis=0)`; `float()`,
#: `int()` or a format of an array, which np.squeeze of exactly one contract would have spared), so none of them refuses. Two
#: selections of different lengths (a broadcast, a dot product, np.interp's fp and xp, np.polyfit's x and y, a strict
#: zip) are each as long as the market makes them; np.interp and np.polyfit do not say whether one was empty. A search
#: that found nothing (`list.index`, `tuple.index`, an all-NaN slice), a step, a scale or a range worked out from the
#: numbers, and a NaN or an infinity are the market's too. The math module's domain errors say "math domain error" on 3.11
#: and, on 3.14, what they expected and got ("expected a positive input, got 0.0"). The truth value of an array of
#: several contracts, a string read as a number and an operator on a list stay refusable: a sparser listing keeps them
#: from refusing where a selection could hold one contract in the Gym.
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


def _declared(code: str, params: Mapping[str, Any] | None) -> dict[str, Any]:
    """The program's PARAMS keys (its literal declaration with the overrides), for the advice; the overrides alone when
    the declaration is not a literal."""
    import ast

    out: dict[str, Any] = {}
    try:
        from ..gym.safety import params_declaration

        declared = ast.literal_eval(params_declaration(ast.parse(code)).value)
        if isinstance(declared, dict):
            out.update(declared)
    except Exception:  # noqa: BLE001 - advice only
        pass
    out.update(params or {})
    return out


def _located(message: str, code: str) -> tuple[int | None, str]:
    m = re.match(r"line (\d+):", str(message or ""))
    if not m:
        return None, ""
    line = int(m.group(1))
    lines = code.splitlines()
    return line, (lines[line - 1].strip()[:200] if 0 < line <= len(lines) else "")


# ------------------------------------------------------------------------------------------------ the run
def _answer(status: str, why: str, **fields: Any) -> dict[str, Any]:
    return {"status": status, "why": why, "version": VERSION, **fields}


def run(code: str, params: Mapping[str, Any] | None, decider: Any, *, universe: Sequence[str] | None = None,
        name: str = "preflight", deadline: float = DEADLINE_SECONDS, clock: Callable[[], float] = time.monotonic) -> dict:
    """The preflight of one (code, params) on `decider` (a `league.live.decider` Decider or InlineDecider). `universe`: the
    run's roots (a program trades its NEEDS roots within them). {"status": "passed" | "refused" | "inconclusive", ...}."""
    from ..live.decider import DeciderError, ProgramRefused

    began = clock()
    key = f"preflight:{hashlib.sha256((code + repr(sorted((params or {}).items()))).encode()).hexdigest()[:16]}:{began:.6f}"
    try:
        info = decider.load(key, code, dict(params or {}), name)
    except ProgramRefused as exc:
        message = str(exc)
        if "ran past" in message or environmental(message):
            return _answer("inconclusive", f"the load says nothing on this box: {message[:300]}")
        line, source = _located(message, code)
        return _answer("refused", "the program does not load (the Gym's worker would refuse it the same way)", stage="load",
                       error=message[:500], line=line, source=source, calls=0,
                       hint=advice(message, params=_declared(code, params), source=source))
    except DeciderError as exc:
        return _answer("inconclusive", f"the sandbox failed: {str(exc)[:300]}")
    try:
        verdict = _decide_loop(code, params or {}, decider, key, info["needs"], universe, began, deadline, clock)
    except DeciderError as exc:
        return _answer("inconclusive", f"the sandbox failed: {str(exc)[:300]}")
    finally:
        _drop(decider, key)
    if verdict["status"] != "refused":
        return verdict
    # THE OTHER MARKETS (`CONFIRMATIONS`): a fresh instance of the program on each. The refusal stands only when the error
    # recurs on every one (`_recurs`), so an error that turns on how many contracts the chain lists (a selection that
    # holds one contract in the Gym holds several here, or none) or on the made-up numbers (a liquidity filter that keeps
    # nothing at these quotes, then a STATE key it never wrote) never refuses on its own.
    calls = int(verdict.get("calls") or 0)
    for regime in CONFIRMATIONS:
        label = REGIMES[regime].label
        again_key = f"{key}:{regime}"
        try:
            decider.load(again_key, code, dict(params or {}), name)
            again = _decide_loop(code, params or {}, decider, again_key, info["needs"], universe, began, deadline, clock,
                                 regime=regime)
        except (ProgramRefused, DeciderError) as exc:
            return _answer("inconclusive", f"the sandbox failed on {label}: {str(exc)[:300]}", calls=calls)
        finally:
            _drop(decider, again_key)
        calls += int(again.get("calls") or 0)
        if again["status"] == "inconclusive":  # it could not say there (its deadline, a timeout, the sandbox)
            return _answer("inconclusive", f"on {label}: {again.get('why')}", calls=calls)
        if again["status"] != "refused" or not _recurs(again.get("error"), verdict.get("error")):
            because = {"sparse": "it may turn on how many contracts the chain lists, which the Gym's store decides",
                       "dense": "it may turn on how many contracts the chain lists, which the Gym's store decides, or on "
                                "the market's numbers, which are made up here"}.get(
                regime, "it may turn on the market's numbers (a quote's width, a vol, a size, a price), which are made up "
                        "here")
            return _answer("inconclusive", f"the error did not recur on {label}: {because}: "
                                           f"{str(verdict.get('error') or '')[:240]}", calls=calls)
    verdict["why"] += ("; again on a sparser listing (one expiry a week, a wider strike step), on a denser one (an expiry "
                       "every weekday, a finer strike step), on quotes one tick wide at twice the vol and on quotes three "
                       "times as wide at a lower vol (other price paths and levels)")
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


def _recurs(again: Any, first: Any) -> bool:
    """`again` (another market's streak) is `first` recurring: the same exception at the same line, or the same exception
    saying the same thing at another line (`name 'intents' is not defined` where another branch ran first)."""
    (line, kind), (first_line, first_kind) = _kind(again), _kind(first)
    if kind != first_kind:
        return False
    text = lambda message: re.sub(r"^line \d+: ", "", str(message or ""))  # noqa: E731
    return line == first_line or text(again) == text(first)


def _decide_loop(code: str, params: Mapping[str, Any], decider: Any, key: str, needs: Mapping[str, Any],
                 universe: Sequence[str] | None, began: float, deadline: float, clock: Callable[[], float], *,
                 regime: str = "listed") -> dict:
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
    for s in range(SESSIONS):
        if s == SESSIONS - 1 and not streak:
            break  # the last session only confirms a streak still running at the end of the one before
        for k, mi in enumerate(schedule):
            if s and k >= STREAK and not streak:
                # A streak must span two sessions: one not running STREAK calls into a later session cannot, this session.
                return _answer("passed", "no persistent error on the synthetic sessions", calls=calls, errors=errors)
            if clock() - began > deadline:
                return _answer("inconclusive", f"the preflight's {deadline:.0f} s ran out after {calls} calls", calls=calls)
            token = s * 1000 + mi
            snaps = {(r, token): market.snapshot(r, s, mi) for r in roots}
            unders = {(r, int(needs["history"]), token): market.under(r, s, mi) for r in roots}
            job = {"key": key, "mi": token, "roots": roots, "minute": OPEN + mi, "open_minute": OPEN, "close_minute": CLOSE,
                   "weekday": market.weekdays[s], "positions": [], "orders": [], "cash": CAPITAL, "equity": CAPITAL,
                   "budget": CAPITAL, "buying_power": CAPITAL, "rules": rules, "events": quiet, "events_next": quiet,
                   "closed": [], "rejects": []}
            answer = decider.decide(snaps, unders, [job]).get(key) or {}
            stats = answer.get("stats")
            if answer.get("missing") or answer.get("skipped") or not isinstance(stats, Mapping) \
                    or getattr(decider, "restarts", 0) != restarts or int(stats.get("calls") or 0) != calls + 1:
                return _answer("inconclusive", "the sandbox lost the program's runner", calls=calls)
            calls += 1
            if int(stats.get("timeouts") or 0) > timeouts:
                return _answer("inconclusive", "a call ran past its time limit (this box is not a Gym box)", calls=calls)
            raised = int(stats.get("errors") or 0) - errors
            errors = int(stats.get("errors") or 0)
            seen = [str(m) for m in stats.get("messages") or []]
            if answer.get("intents"):
                return _answer("passed", f"the program returned an intent at call {calls}; a flat account no longer "
                                         "mirrors the Gym's from there", calls=calls, errors=errors)
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
                return _verdict(code, params, roots, streak, named, unnamed, blind, first_message, seen, calls, errors)
    return _answer("passed", "no persistent error on the synthetic sessions", calls=calls, errors=errors)


def _verdict(code: str, params: Mapping[str, Any], roots: Sequence[str], streak: Sequence[tuple[int, int]],
             named: Sequence[str], unnamed: bool, blind: bool, first_message: str, seen: Sequence[str], calls: int,
             errors: int) -> dict:
    """A streak long enough to refuse: refused only when every error it may hold is known and says the program misuses the
    API on any market, on any box (not `environmental`, not `market_dependent`)."""
    if blind:
        return _answer("inconclusive", f"the Runner's list holds {RUNNER_MESSAGES} messages and the streak's error is not "
                                       "among them", calls=calls, errors=errors)
    candidates = list(dict.fromkeys([*named, *(seen if unnamed else ())]))
    if not first_message and len(candidates) == 1:
        first_message = candidates[0]
    if not first_message or not candidates:
        return _answer("inconclusive", "the streak's first error cannot be told apart from earlier ones", calls=calls,
                       errors=errors)
    if any(environmental(m) for m in [*candidates, *seen]):
        found = next(m for m in [*candidates, *seen] if environmental(m))
        return _answer("inconclusive", f"the error may be this box's Python, numpy or memory, not the Gym's: {found[:300]}",
                       calls=calls, errors=errors)
    if any(market_dependent(m) for m in candidates):
        found = next(m for m in candidates if market_dependent(m))
        return _answer("inconclusive", f"the error turns on the market's numbers, which are made up here: {found[:300]}",
                       calls=calls, errors=errors)
    line, source = _located(first_message, code)
    return _answer("refused", f"decide raised on every call from call {streak[0][1]} ({len(streak)} calls over "
                              f"{len({x[0] for x in streak})} synthetic sessions, before any intent)",
                   stage="decide", error=first_message[:500], line=line, source=source, calls=calls, errors=errors,
                   messages=[m[:200] for m in candidates[:4]],
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
                 name: str = "preflight") -> dict:
        began = time.monotonic()
        if not self._lock.acquire(timeout=self.wait):
            return _answer("inconclusive", "another preflight held the sandbox", seconds=0.0)
        try:
            out = run(code, params, self.decider(), universe=roots, name=name, deadline=self.deadline)
        finally:
            self._lock.release()
        out["seconds"] = round(time.monotonic() - began, 3)
        return out

    def close(self) -> None:
        if self._decider is not None and callable(getattr(self._decider, "close", None)):
            self._decider.close()


__all__ = ["VERSION", "STREAK", "SESSIONS", "PREFLIGHT_UID", "PREFLIGHT_NICE", "LISTING", "REGIMES", "CONFIRMATIONS",
           "Market", "Preflight", "Regime", "advice", "decision_minutes", "environmental", "equity_step", "expiries",
           "listing", "market_dependent", "quote", "run", "session_weekdays", "strikes", "vol_of"]
