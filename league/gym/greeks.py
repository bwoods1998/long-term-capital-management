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


def implied_vol(price, spot, strike, years, rate, is_call, *, guess=None, iterations: int = 30,
                tol: float = 1e-7) -> np.ndarray:
    """Implied vol of each price (NaN where there is none). All inputs broadcast together; `guess`
    (a previous minute's vols, NaN where unknown) warm-starts the solve.

    It solves on the OUT-OF-THE-MONEY side: an in-the-money call's time value is the same-strike put's
    price by parity, and solving for that small number is well conditioned where the call's full price
    is not. Newton steps on the active elements only, bisecting whenever a step leaves the bracket."""
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
    # Start: a warm guess where one is known, else Brenner-Subrahmanyam on the time value.
    vol = np.sqrt(2.0 * np.pi) * tv / (s * sqrt_t)
    if guess is not None:
        g = np.broadcast_to(np.asarray(guess, dtype=np.float64), shape).ravel()[idx]
        vol = np.where(np.isfinite(g) & (g > VOL_LO) & (g < VOL_HI), g, vol)
    vol = np.clip(vol, 0.01, 4.0)
    lo = np.full(idx.size, VOL_LO)
    hi = np.full(idx.size, VOL_HI)
    live = np.arange(idx.size)
    for _ in range(iterations):
        v = vol[live]
        st = sqrt_t[live]
        sq = v * st
        d1 = (log_sk[live] + (rate + 0.5 * v * v) * t[live]) / sq
        d2 = d1 - sq
        cl = call[live]
        sgn = np.where(cl, 1.0, -1.0)
        model = sgn * (s[live] * norm_cdf(sgn * d1) - dk[live] * norm_cdf(sgn * d2))
        diff = model - tv[live]
        vega = s[live] * norm_pdf(d1) * st
        high = diff > 0
        hi[live] = np.where(high, v, hi[live])
        lo[live] = np.where(high, lo[live], v)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            newton = v - diff / vega
        bad = ~np.isfinite(newton) | (newton <= lo[live]) | (newton >= hi[live])
        done = np.abs(diff) <= tol * np.maximum(tv[live], 1e-4)
        # A converged element keeps its vol: a last step from it could leave the bracket and bisect.
        vol[live] = np.where(done, v, np.where(bad, 0.5 * (lo[live] + hi[live]), newton))
        live = live[~done]
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
