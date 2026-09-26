"""Vectorized Black-Scholes on the mid: implied vol, delta, gamma, theta, vega. numpy only.

The engine computes these for the chain a program asks for (`ctx.py`), the same way in a replay and
live: European Black-Scholes, no dividend, the day's rate from `events.rate_on`, time to expiry
measured to 16:00 ET of the expiry day in calendar minutes over a 365-day year. American equity
options are priced as European: for 0-14 day contracts the early-exercise premium is small next to
the spread, and the greeks are features a program reads, never prices the engine fills at.

numpy has no erf, so the normal CDF is Zelen and Severo's (Abramowitz and Stegun 26.2.17, absolute
error under 7.5e-8). Implied vol is a safeguarded Newton (bisection whenever a step leaves the
bracket), from a Brenner-Subrahmanyam start; a price at or under intrinsic, or at or over the
no-arbitrage ceiling, has no implied vol (NaN) and gets the limit greeks (delta 1/0/-1, the rest 0).
"""

from __future__ import annotations

import math

import numpy as np

MINUTES_A_YEAR = 365.0 * 24.0 * 60.0
SQRT_2PI = math.sqrt(2.0 * math.pi)
VOL_LO, VOL_HI = 1e-4, 8.0
_P = 0.2316419
_B = (0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429)


def norm_pdf(x: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * x * x) / SQRT_2PI


def norm_cdf(x: np.ndarray) -> np.ndarray:
    """The standard normal CDF, vectorized (A&S 26.2.17)."""
    x = np.asarray(x, dtype=np.float64)
    a = np.abs(x)
    t = 1.0 / (1.0 + _P * a)
    poly = t * (_B[0] + t * (_B[1] + t * (_B[2] + t * (_B[3] + t * _B[4]))))
    upper = norm_pdf(a) * poly  # P(Z > |x|)
    return np.where(x >= 0.0, 1.0 - upper, upper)


def years_to_expiry(dte: np.ndarray, minute: int | np.ndarray, *, close_minute: int = 960) -> np.ndarray:
    """Calendar years from `minute` (ET, minutes since midnight) to 16:00 of the expiry day, at least
    one minute (an expiring contract at the bell still has a sliver of time)."""
    dte = np.asarray(dte, dtype=np.float64)
    minutes = dte * 1440.0 + (close_minute - np.asarray(minute, dtype=np.float64))
    return np.maximum(minutes, 1.0) / MINUTES_A_YEAR


def bs_price(spot, strike, years, rate, vol, is_call) -> np.ndarray:
    spot = np.asarray(spot, dtype=np.float64)
    strike = np.asarray(strike, dtype=np.float64)
    years = np.asarray(years, dtype=np.float64)
    vol = np.asarray(vol, dtype=np.float64)
    sq = vol * np.sqrt(years)
    d1 = (np.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / sq
    d2 = d1 - sq
    disc = strike * np.exp(-rate * years)
    call = spot * norm_cdf(d1) - disc * norm_cdf(d2)
    return np.where(is_call, call, call - spot + disc)


# The normalized out-of-the-money Black price b(|x|, s) = e^(-|x|/2) N(s/2 - |x|/s) - e^(|x|/2) N(-s/2 - |x|/s),
# with x = ln(S / (K e^-rT)) and s = vol x sqrt(T): an out-of-the-money option's price is sqrt(S K e^-rT) b.
# It is increasing in s, so a table over |x| and s inverts by a vectorized binary search: the solve's
# starting point, within about a percent of the answer, so Newton needs two or three steps.
_TX = np.linspace(0.0, 0.6, 241)
_TS = np.exp(np.linspace(np.log(1e-4), np.log(4.0), 256))


def _table() -> np.ndarray:
    x = _TX[:, None]
    s = _TS[None, :]
    return np.exp(-x / 2.0) * norm_cdf(s / 2.0 - x / s) - np.exp(x / 2.0) * norm_cdf(-s / 2.0 - x / s)


_TB = _table()


def _guess_total_vol(abs_x: np.ndarray, b: np.ndarray) -> np.ndarray:
    """s = vol x sqrt(T) whose normalized price is b at |x| (NaN outside the table)."""
    row = np.clip(np.rint(abs_x / (_TX[1] - _TX[0])).astype(np.int64), 0, _TX.size - 1)
    lo = np.zeros(b.shape, dtype=np.int64)
    hi = np.full(b.shape, _TS.size - 1, dtype=np.int64)
    for _ in range(9):  # 256 columns
        mid = (lo + hi) // 2
        above = _TB[row, mid] >= b
        hi = np.where(above, mid, hi)
        lo = np.where(above, lo, mid)
    b0, b1 = _TB[row, lo], _TB[row, hi]
    with np.errstate(divide="ignore", invalid="ignore"):
        w = np.clip((b - b0) / (b1 - b0), 0.0, 1.0)
    s = np.exp(np.log(_TS[lo]) + w * (np.log(_TS[hi]) - np.log(_TS[lo])))
    inside = (abs_x <= _TX[-1]) & (b > _TB[row, 0]) & (b < _TB[row, -1])
    return np.where(inside, s, np.nan)


def implied_vol(price, spot, strike, years, rate, is_call, *, guess=None, iterations: int = 24,
                tol: float = 1e-7, vol_tol: float = 1e-5) -> np.ndarray:
    """Implied vol of each price (NaN where there is none). All inputs broadcast together; `guess`
    (a previous minute's vols, NaN where unknown) warm-starts the solve.

    It solves on the OUT-OF-THE-MONEY side: an in-the-money call's time value is the same-strike put's
    price by parity, and solving for that small number is well conditioned where the call's full price
    is not. Newton steps on the active elements only, bisecting whenever a step leaves the bracket; an
    element is done when its price is matched to `tol` (relative), or its vol moves less than `vol_tol`,
    or its bracket is narrower than that (a one-cent quote moves a vol far more)."""
    price, spot, strike, years = np.broadcast_arrays(
        np.asarray(price, dtype=np.float64), np.asarray(spot, dtype=np.float64),
        np.asarray(strike, dtype=np.float64), np.asarray(years, dtype=np.float64))
    shape = price.shape
    price, spot, strike, years = price.ravel(), spot.ravel(), strike.ravel(), years.ravel()
    is_call = np.broadcast_to(np.asarray(is_call, dtype=bool), shape).ravel()
    disc_k = strike * np.exp(-rate * years)
    intrinsic = np.where(is_call, np.maximum(spot - disc_k, 0.0), np.maximum(disc_k - spot, 0.0))
    ceiling = np.where(is_call, spot, disc_k)
    out = np.full(price.shape, np.nan)
    ok = (np.isfinite(price) & np.isfinite(spot) & (spot > 0) & (strike > 0) & (years > 0)
          & (price > intrinsic + 1e-9) & (price < ceiling))
    idx = np.flatnonzero(ok)
    if idx.size == 0:
        return out.reshape(shape)
    s, k, t, dk = spot[idx], strike[idx], years[idx], disc_k[idx]
    tv = price[idx] - intrinsic[idx]           # the out-of-the-money option's price
    call = s <= dk                              # solve as a call where the call is out of the money
    sqrt_t = np.sqrt(t)
    log_sk = np.log(s / k)
    # Start: a warm guess where one is known, else the normalized-price table, else Brenner-Subrahmanyam.
    vol = np.sqrt(2.0 * np.pi) * tv / (s * sqrt_t)
    table = _guess_total_vol(np.abs(np.log(s / dk)), tv / np.sqrt(s * dk)) / sqrt_t
    vol = np.where(np.isfinite(table), table, vol)
    if guess is not None:
        g = np.broadcast_to(np.asarray(guess, dtype=np.float64), shape).ravel()[idx]
        # A previous minute's vol is used only where the table has no answer: the table's start is
        # already within a percent, and a stale vol (a one-cent mid that moved) is not.
        vol = np.where(np.isfinite(table) | ~(np.isfinite(g) & (g > VOL_LO) & (g < VOL_HI)), vol, g)
    vol = np.clip(vol, VOL_LO * 2, VOL_HI / 2)
    lo = np.full(idx.size, VOL_LO)
    hi = np.full(idx.size, VOL_HI)
    live = np.arange(idx.size)
    sign = np.where(call, 1.0, -1.0)
    rt = rate * t
    for _ in range(iterations):
        v = vol[live]
        st = sqrt_t[live]
        sq = v * st
        d1 = (log_sk[live] + rt[live] + 0.5 * v * v * t[live]) / sq
        sgn = sign[live]
        s_l = s[live]
        model = sgn * (s_l * norm_cdf(sgn * d1) - dk[live] * norm_cdf(sgn * (d1 - sq)))
        diff = model - tv[live]
        vega = s_l * norm_pdf(d1) * st
        high = diff > 0
        lo_l = np.where(high, lo[live], v)
        hi_l = np.where(high, v, hi[live])
        lo[live] = lo_l
        hi[live] = hi_l
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            newton = v - diff / vega
        bad = ~np.isfinite(newton) | (newton <= lo_l) | (newton >= hi_l)
        done = np.abs(diff) <= tol * np.maximum(tv[live], 1e-4)
        nxt = np.where(bad, 0.5 * (lo_l + hi_l), newton)
        settled = ~done & ((np.abs(nxt - v) < vol_tol) | (hi_l - lo_l < vol_tol))
        # A converged element keeps its vol: a last step from it could leave the bracket and bisect.
        vol[live] = np.where(done, v, nxt)
        live = live[~(done | settled)]
        if live.size == 0:
            break
    out[idx] = vol
    return out.reshape(shape)


def greeks(spot, strike, years, rate, vol, is_call):
    """(delta, gamma, theta a calendar day, vega a vol point) for each option. Where `vol` is NaN the
    limit values: delta 1 (a call in the money), -1 (a put in the money) or 0, the others 0."""
    spot, strike, years, vol = np.broadcast_arrays(
        np.asarray(spot, dtype=np.float64), np.asarray(strike, dtype=np.float64),
        np.asarray(years, dtype=np.float64), np.asarray(vol, dtype=np.float64))
    is_call = np.broadcast_to(np.asarray(is_call, dtype=bool), spot.shape)
    known = np.isfinite(vol) & (vol > 0)
    v = np.where(known, vol, 0.2)
    sqrt_t = np.sqrt(years)
    sq = v * sqrt_t
    d1 = (np.log(np.where(spot > 0, spot, 1.0) / strike) + (rate + 0.5 * v * v) * years) / sq
    d2 = d1 - sq
    pdf = norm_pdf(d1)
    nd1 = norm_cdf(d1)
    disc = np.exp(-rate * years)
    delta = np.where(is_call, nd1, nd1 - 1.0)
    gamma = pdf / (spot * sq)
    common = -spot * pdf * v / (2.0 * sqrt_t)
    theta_call = common - rate * strike * disc * norm_cdf(d2)
    theta_put = common + rate * strike * disc * norm_cdf(-d2)
    theta = np.where(is_call, theta_call, theta_put) / 365.0
    vega = spot * pdf * sqrt_t / 100.0
    itm = np.where(is_call, spot > strike, spot < strike)
    limit_delta = np.where(itm, np.where(is_call, 1.0, -1.0), 0.0)
    return (np.where(known, delta, limit_delta), np.where(known, gamma, 0.0),
            np.where(known, theta, 0.0), np.where(known, vega, 0.0))


def chain_greeks(mid, spot, strike, dte, is_call, minute, rate, *, close_minute: int = 960):
    """(iv, delta, gamma, theta, vega) of a chain at one minute (or a [contract, minute] block when
    `minute` and `spot` are row vectors): the one call `ctx.py` makes."""
    years = years_to_expiry(np.asarray(dte)[..., None] if np.ndim(minute) else dte, minute, close_minute=close_minute) \
        if np.ndim(minute) else years_to_expiry(dte, minute, close_minute=close_minute)
    k = np.asarray(strike, dtype=np.float64)
    c = np.asarray(is_call, dtype=bool)
    if np.ndim(minute):
        k, c = k[:, None], c[:, None]
    iv = implied_vol(mid, spot, k, years, rate, c)
    d, g, t, v = greeks(spot, k, years, rate, iv, c)
    return iv, d, g, t, v
