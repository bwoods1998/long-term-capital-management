"""The `equity_neff` job: how many independent names the panel holds (D21), for the funnel's independent asset-years.

Owner: package B of release E4. Protected (league/ops/). The registry row is package A's patch (E4-SPEC 13: monthly).

On Train segment 2 (2022-24: no sealed row), names with a full series: R = the correlation matrix of their daily
SECTOR-RESIDUAL returns (a name's close-to-close return less its sector's equal-weight mean, sectors re-formed monthly
by `league.xs.ctx.derive`); neff_rho = n / (1 + (n - 1) x the mean off-diagonal of R); neff_pr = (the sum of R's
eigenvalues)^2 / the sum of their squares. Into `<state>/equity-daily/neff.json` {"sp500": {"window", "names", "rho",
"neff_rho", "neff_pr", "computed_at"}} (and, beside them, "sessions", "columns", "dropped", "months",
"months_skipped", "coverage"). Receipts and the funnel carry N_eff, never a return. Every sum is `math.fsum`.

THE DEFINITION, to the last step (`residuals`, `neff`; each a formula `test_equity_neff.py` checks on synthetic data):
- The slice is `PanelStore.train` over the whole second span of `league.xs.config.TRAIN_SEGMENTS`, with its look-back.
  A session's return of a name is its adjustment=all close over the one before it, minus 1, where both sessions hold
  a valid bar (raw close > 0, raw volume > 0, a finite adjusted close > 0), else none. (A ratio of two adjusted
  closes carries the vendor's cent rounding, at most `league.xs.config.rounding_bound` of the two; nothing here
  compares two readings, so no tolerance is taken.)
- The month of a session forms its baskets at the close BEFORE the month's first session (the first month's in the
  look-back): `derive` says which columns are eligible there and each one's sector. The basket of a sector that
  month is its eligible columns; a session's sector mean is the mean of the basket's returns that exist that session.
  A MONTH WHOSE FORMATION HAS NO ELIGIBLE NAME IS NOT READ: the segment's first month is one (at the close before
  the first run session the store holds 252 sessions, one short of a 12-1 momentum, so nothing is eligible there:
  E4-SPEC D1), so the window read is 2022-02 through 2024-12 and the file's `window` says so.
- A NAME HAS A FULL SERIES when it has a return on every session of the window and is eligible, with a sector, at
  every month's formation. Its residual is its return less its own sector's mean (the basket holds the name itself).
  A name whose residual never moves (a basket of one) is dropped and counted.
- rho_ij is the Pearson correlation of two names' residuals over the window. With n names: `rho` = the mean of the
  n (n - 1) / 2 off-diagonal figures; `neff_rho` = n / (1 + (n - 1) rho), and n when rho is at or under zero (no
  common factor is left: a count of names is never above the names; sector residuals sum to about zero inside a
  sector, so this cap binds in practice and `neff_pr` is the figure the funnel reads); `neff_pr` = n^2 / the sum of
  rho_ij^2 over EVERY i and j (the diagonal's ones included). That is the participation ratio: the sum of R's
  eigenvalues is its trace, n, and the sum of their squares is the sum of its squared entries, so no eigenvalue
  routine is called and the figure is the same on every numpy.

THE FUNNEL'S ROWS (`funnel_rows`; package B's patch 11 has `league.ops.funnel.window` call it): per equity lane and
structure, the Gym's Train runs in a window as SIMULATED PROGRAM-YEARS (each evaluated run's sessions x its trials /
252) beside the INDEPENDENT ASSET-YEARS they read: the Train years of those runs (never more than the structure's
Train era holds: `TRAIN_YEARS`) x the N_eff of their data (a panel program: `neff_pr` of neff.json; an ETF program:
release E3's figure when its report carries one, else `ETF_NEFF_DEFAULT`; a stock program: E3's figure or none), and
their ratio, THE REPLAY MULTIPLE: how many times one independent asset-year was replayed. Simulated years are compute,
never evidence; the row says so in numbers.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

FILE = "neff.json"
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 900
#: The equity lane's state directory (`league.ops.equity_data.STORE_DIR`; spelled here, a test holds them equal).
STORE_DIR = "equity-daily"
#: Which span of `league.xs.config.TRAIN_SEGMENTS` the job reads: the second (2022-24).
SEGMENT = 1
#: The run key the job's slice is asked under (its salted ids are read by no program and leave no file).
RUN_KEY = "neff|sp500"
#: The fewest names and sessions a correlation matrix is formed from.
MIN_NAMES = 2
MIN_SESSIONS = 3
#: Sessions a year, for program-years and Train years.
YEAR_SESSIONS = 252
#: The Train years one structure's runs can read: E1's Train era (2016-19 and 2022-24) for an ETF or a stock program,
#: the panel's six (2017-19 and 2022-24: 2016 is history only). Spelled here so the funnel's rows stay standard
#: library only; a test holds them to `league.equity.config.TRAIN_ERA_SEGMENTS` and `league.xs.config.TRAIN_YEARS`.
TRAIN_YEARS = {"etf": 7, "stock": 7, "panel": 6}
#: An ETF program's N_eff while release E3's own figure is absent (the roadmap's reading of the ETF universe).
ETF_NEFF_DEFAULT = 2.3
#: Release E3's report (`league.ops.forward_report.FILE`) and where its history's independent years stand in it.
FORWARD_REPORT = "forward-report.json"


# ------------------------------------------------------------------------------------------------- the arithmetic
def neff(returns: Any) -> dict[str, Any]:
    """{names, rho, neff_rho, neff_pr} of a (sessions, names) array of residual returns with no missing value (the
    module docstring's last step; also "sessions"). ValueError for an array that is not two-dimensional, fewer than
    `MIN_SESSIONS` sessions or `MIN_NAMES` names, a value that is not finite, and a name whose returns never move (it
    has no correlation: `residuals` drops such a name before this is asked)."""
    import numpy as np

    x = np.asarray(returns, dtype=np.float64)
    if x.ndim != 2:
        raise ValueError(f"the returns are a (sessions, names) array; got {x.ndim} dimensions")
    sessions, names = int(x.shape[0]), int(x.shape[1])
    if sessions < MIN_SESSIONS or names < MIN_NAMES:
        raise ValueError(f"{sessions} sessions of {names} names: a correlation matrix needs at least {MIN_SESSIONS} "
                         f"sessions of {MIN_NAMES} names")
    if not np.isfinite(x).all():
        raise ValueError("a return is missing or not finite")
    means = np.array([math.fsum(column) / sessions for column in x.T.tolist()], dtype=np.float64)
    d = x - means
    squares = [math.fsum(column) for column in (d * d).T.tolist()]
    flat = [i for i, value in enumerate(squares) if not value > 0.0]
    if flat:
        raise ValueError(f"{len(flat)} of {names} names have returns that never move")
    off: list[float] = []
    for i in range(names - 1):
        cross = [math.fsum(column) for column in (d[:, i:i + 1] * d[:, i + 1:]).T.tolist()]
        for j, value in enumerate(cross, start=i + 1):
            off.append(max(-1.0, min(1.0, value / math.sqrt(squares[i] * squares[j]))))
    rho = math.fsum(off) / len(off)
    spread = 1.0 + (names - 1) * rho
    neff_rho = float(names) if spread <= 1.0 else names / spread
    neff_pr = names * names / (names + 2.0 * math.fsum(value * value for value in off))
    return {"names": names, "sessions": sessions, "rho": rho, "neff_rho": neff_rho, "neff_pr": neff_pr}


def residuals(returns: Any, month: Sequence[int], sector: Any, eligible: Any) -> dict[str, Any]:
    """THE SECTOR-RESIDUAL RETURNS of the names with a full series (the module docstring). `returns`: (sessions,
    columns) float, NaN where a column has no return that session. `month`: each session's month index, 0 .. M - 1,
    never falling. `sector` (M, columns) int and `eligible` (M, columns) bool: `league.xs.ctx.derive`'s answer at each
    month's formation close (a sector under 0 is none). {"x": (sessions, n) float64, "columns": the n kept columns'
    indices, "dropped": {"no_return", "not_eligible", "flat"}} (counts of columns; a column is counted once, under the
    first reason that holds). Pure; every sum is `math.fsum`."""
    import numpy as np

    r = np.asarray(returns, dtype=np.float64)
    sector = np.asarray(sector)
    elig = np.asarray(eligible, dtype=bool)
    months = [int(m) for m in month]
    if r.ndim != 2 or len(months) != r.shape[0]:
        raise ValueError("the returns are (sessions, columns) and every session has its month")
    if sector.ndim != 2 or sector.shape != elig.shape or sector.shape[1] != r.shape[1]:
        raise ValueError("the sectors and the eligible set are (months, columns), the returns' columns")
    count = int(sector.shape[0])
    if months and (months[0] < 0 or months[-1] >= count or any(b < a for a, b in zip(months, months[1:]))):
        raise ValueError("a session's month is outside the formations given, or the months fall")
    placed = elig & (sector >= 0)
    has_return = np.isfinite(r).all(axis=0) if r.shape[0] else np.zeros(r.shape[1], dtype=bool)
    in_every = placed[sorted(set(months))].all(axis=0) if months else np.zeros(r.shape[1], dtype=bool)
    full = has_return & in_every
    x = np.full(r.shape, np.nan, dtype=np.float64)
    rows_of: dict[int, list[int]] = {}
    for t, m in enumerate(months):
        rows_of.setdefault(m, []).append(t)
    for m, rows in rows_of.items():
        for code in sorted({int(c) for c in sector[m][placed[m]].tolist()}):
            basket = np.flatnonzero(placed[m] & (sector[m] == code))
            mine = basket[full[basket]]
            if not mine.size:
                continue
            for t in rows:
                held = [value for value in r[t, basket].tolist() if math.isfinite(value)]
                x[t, mine] = r[t, mine] - math.fsum(held) / len(held)
    columns = np.flatnonzero(full)
    moved = np.array([_moves(column) for column in x[:, columns].T.tolist()], dtype=bool) if columns.size else \
        np.zeros(0, dtype=bool)
    kept = columns[moved]
    dropped = {"no_return": int((~has_return).sum()), "not_eligible": int((has_return & ~in_every).sum()),
               "flat": int(columns.size - kept.size)}
    return {"x": np.ascontiguousarray(x[:, kept]), "columns": [int(c) for c in kept.tolist()], "dropped": dropped}


def _moves(column: Sequence[float]) -> bool:
    """Whether a residual series has any variance (the sum of its squared deviations from its mean is above zero)."""
    mean = math.fsum(column) / len(column)
    return math.fsum((value - mean) * (value - mean) for value in column) > 0.0


def formations(days: Sequence[dt.date], first: int) -> tuple[list[int], list[int]]:
    """(each run session's month index, each month's formation index) for a slice whose sessions are `days` and whose
    run begins at index `first`: a month's formation is the index of the session before its first run session.
    ValueError when the run's first session has none before it (the slice carries no look-back)."""
    if not 0 < first < len(days):
        raise ValueError("the slice holds no run session, or none before the run's first: no formation close")
    month, formed, last = [], [], None
    for index in range(first, len(days)):
        key = (days[index].year, days[index].month)
        if key != last:
            formed.append(index - 1)
            last = key
        month.append(len(formed) - 1)
    return month, formed


# ------------------------------------------------------------------------------------------------- the job
def panel_returns(bars: Any) -> Any:
    """(n - first, m) float64: each run session's close-to-close adjustment=all return of every column of a
    `league.xs.store.PanelBars`, NaN unless that session and the one before both hold a valid bar (raw close > 0, raw
    volume > 0, a finite adjusted close > 0)."""
    import numpy as np

    raw, adj = np.asarray(bars.raw, dtype=np.float64), np.asarray(bars.adj, dtype=np.float64)
    close = adj[:, :, 3]
    with np.errstate(invalid="ignore"):
        valid = (raw[:, :, 3] > 0) & (raw[:, :, 4] > 0) & np.isfinite(close) & (close > 0)
    first = int(bars.first)
    out = np.full((close.shape[0] - first, close.shape[1]), np.nan, dtype=np.float64)
    both = valid[first:] & valid[first - 1:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        out[both] = (close[first:] / close[first - 1:-1] - 1.0)[both]
    return out


def measure(bars: Any) -> dict[str, Any]:
    """D21 on one Train slice (`league.xs.store.PanelBars` with its look-back): `neff`'s answer with "window" (the
    first and last session read), "columns" (the member columns), "dropped", "months" and "months_skipped". The
    formations are `league.xs.ctx.derive`'s, asked once a month at the close before the month's first session; a
    month whose formation has no eligible name is not read."""
    import numpy as np

    from ..equity import store as eq_store
    from ..xs import config as xs_config
    from ..xs import ctx as xs_ctx
    from ..xs import program as xs_program

    days = [eq_store.from_ordinal(int(value)) for value in np.asarray(bars.days).tolist()]
    first, ref = int(bars.first), int(bars.ref)
    month, formed = formations(days, first)
    needs = xs_program.Needs(panel="sp500", history=xs_config.MAX_HISTORY, max_names=xs_config.MIN_NAMES,
                             rebalance="monthly", weekday=0, max_hold_sessions=xs_config.MAX_HOLD_CAP)
    columns = int(np.asarray(bars.raw).shape[1])
    sector = np.full((len(formed), columns), -1, dtype=np.int64)
    eligible = np.zeros((len(formed), columns), dtype=bool)
    for m, index in enumerate(formed):
        derived = xs_ctx.derive(xs_ctx.inputs_from_panel(bars, index, needs=needs, cash=0.0, equity=0.0, budget=0.0,
                                                         params={}))
        sector[m] = np.asarray(derived.sector, dtype=np.int64)
        eligible[m] = np.asarray(derived.elig, dtype=bool)
    # The REF columns (SPY and the sector funds) lead every slice and are never names: the members alone are read.
    sector, eligible = sector[:, ref:], eligible[:, ref:]
    # A month whose formation close has no eligible name has no basket and is left out (the segment's FIRST month:
    # at the close before the first run session the store is one session short of a 12-1 momentum, so nothing is
    # eligible there, on the House and in the screen's study alike: E4-SPEC D1).
    formed_months = [m for m in range(len(formed)) if eligible[m].any()]
    place = {m: j for j, m in enumerate(formed_months)}
    rows = [t for t, m in enumerate(month) if m in place]
    if not rows:
        raise ValueError("no month's formation close has an eligible name: no basket, no matrix")
    parts = residuals(panel_returns(bars)[rows][:, ref:], [place[month[t]] for t in rows], sector[formed_months],
                      eligible[formed_months])
    if len(parts["columns"]) < MIN_NAMES:
        raise ValueError(f"{len(parts['columns'])} names have a full series of {len(rows)} sessions: no matrix")
    out = neff(parts["x"])
    out.update(window=[days[first + rows[0]].isoformat(), days[first + rows[-1]].isoformat()], columns=columns - ref,
               dropped=parts["dropped"], months=len(formed_months), months_skipped=len(formed) - len(formed_months))
    return out


def run(ctx: Any) -> dict[str, Any]:
    """The job. Its first statement is `league.xs.config.quiet(ctx.now(), WALL_S)`. {"ok": True, "panel", "names",
    "sessions", "columns", "neff_rho", "neff_pr", "window", "dropped", "months", "months_skipped"} and neff.json
    written; {"status": "skipped", "why"} inside a quiet window, before the panel store exists, and while its
    coverage verdict is "insufficient"; {"status": "failed", "ok": False, "error"} when the store or the matrix
    cannot be read (the last neff.json stays)."""
    from ..xs import config as xs_config
    from .equity_universe import lane_off

    off = lane_off(ctx.root)    # WITH THE LANE'S SWITCH OFF NOTHING OF E4 RUNS (`elane.panel.mode`): its data too
    if off is not None:
        return {"status": "skipped", "why": off}
    try:
        why = xs_config.quiet(ctx.now(), WALL_S)
    except Exception as exc:  # noqa: BLE001 - a job that cannot learn whether it stands at a wall does not start
        why = f"the quiet windows could not be read ({type(exc).__name__}: {str(exc)[:160]})"
        ctx.alert("warning", f"equity_neff: {why}; the job did not run")
    if why is not None:
        return {"status": "skipped", "why": why}
    from .. import xs
    from ..xs import store as xs_store
    from . import schedule as S
    from .context import read_json, write_json

    root = Path(ctx.root) / STORE_DIR
    if not (root / xs_store.PANEL_DIR / "PANEL_MANIFEST.json").exists():
        return {"status": "skipped", "why": "no panel store yet"}
    panel = xs.PANELS[0]
    try:
        store = xs_store.PanelStore(root)
        verdict = store.verdict()
        if verdict == "insufficient":
            return {"status": "skipped", "why": "the panel's coverage is insufficient: the lane is off"}
        start, end = xs_config.TRAIN_SEGMENTS[SEGMENT]
        found = measure(store.train(start, end, history=xs_config.MAX_HISTORY, run_key=RUN_KEY).bars)
    except Exception as exc:  # noqa: BLE001 - nothing written: the last neff.json stays
        return {"status": "failed", "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    row = {"window": found["window"], "names": found["names"], "rho": round(found["rho"], 6),
           "neff_rho": round(found["neff_rho"], 2), "neff_pr": round(found["neff_pr"], 2),
           "computed_at": S.iso(ctx.now()), "sessions": found["sessions"], "columns": found["columns"],
           "dropped": found["dropped"], "months": found["months"], "months_skipped": found["months_skipped"],
           "coverage": verdict}
    held = read_json(root / FILE, {})
    held = dict(held) if isinstance(held, Mapping) else {}
    held[panel] = row
    write_json(root / FILE, held)
    return {"ok": True, "panel": panel, **{k: row[k] for k in ("names", "sessions", "columns", "neff_rho", "neff_pr",
                                                               "window", "dropped", "months", "months_skipped")}}


# ------------------------------------------------------------------------------------------------- the funnel's rows
def _figure(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) and float(value) > 0 else None


def panel_neff(root: str | Path, panel: str = "sp500") -> float | None:
    """The panel's `neff_pr` as neff.json holds it (`root`: the House's state directory), or None."""
    from .context import read_json

    held = read_json(Path(root) / STORE_DIR / FILE, {})
    row = held.get(panel) if isinstance(held, Mapping) else None
    return _figure(row.get("neff_pr")) if isinstance(row, Mapping) else None


def etf_neff(root: str | Path) -> tuple[float, str]:
    """(an ETF program's N_eff, where it came from): release E3's figure when its report carries one ("forward-report":
    the report's independent years of the store's history, `cey.hist_iy`, over that history's years: the sessions of
    2016-01-04 through `league.equity.config.LOOK_CAP` / 252; never under 1), else (`ETF_NEFF_DEFAULT`, "default")."""
    from .context import read_json

    report = read_json(Path(root) / FORWARD_REPORT, {})
    cey = report.get("cey") if isinstance(report, Mapping) else None
    history = _figure(cey.get("hist_iy")) if isinstance(cey, Mapping) else None
    if history is not None:
        try:
            from ..equity import config as eq_config
            from ..equity import store as eq_store
            from .equity_data import FIRST_DAY

            years = len(eq_store.nyse_sessions(dt.date.fromisoformat(FIRST_DAY), eq_config.LOOK_CAP)) / YEAR_SESSIONS
            if years > 0:
                return max(1.0, history / years), "forward-report"
        except Exception:  # noqa: BLE001 - E3's figure cannot be read: the default, said so
            pass
    return ETF_NEFF_DEFAULT, "default"


def funnel_rows(root: str | Path, db: sqlite3.Connection, start: float, end: float) -> dict[str, Any]:
    """{lane: {structure: {"train_runs", "program_years", "train_years", "neff", "neff_source",
    "independent_asset_years", "replay_multiple"}}} for the equity lanes' families (the module docstring's last
    paragraph), over the swarm store's Train runs in `[start, end)`. `db`: swarm.sqlite inside the funnel's read
    transaction. A structure with no N_eff reads None for it and for the two figures built on it, never a zero.
    Standard library only."""
    from . import funnel, guard
    from . import schedule as S

    a, b = S.iso(start), S.iso(end)
    out: dict[str, dict[str, dict[str, Any]]] = {lane: {} for lane in funnel.EQUITY_LANES}
    group: dict[str, tuple[str, str]] = {}
    for row in guard.rows(db, "SELECT id, structure, spec FROM families WHERE instr(spec, '\"lane\"') > 0"):
        try:
            spec = json.loads(row["spec"])
        except (TypeError, ValueError):
            continue
        lane = spec.get("lane") if isinstance(spec, Mapping) else None
        structure = str(row["structure"] or "")
        if lane in funnel.EQUITY_LANES and structure in TRAIN_YEARS:
            group[str(row["id"])] = (lane, structure)
            out[lane].setdefault(structure, {"train_runs": 0, "sessions": 0.0})
    for row in guard.rows(db, 'SELECT family, status, trials, summary FROM runs WHERE "window"=\'train\' AND at>=? AND '
                              "at<?", (a, b)):
        key = group.get(str(row["family"] or ""))
        trials = int(row["trials"] or 0)
        if key is None or row["status"] in funnel.NOT_RUN or trials <= 0:
            continue
        try:
            days = json.loads(row["summary"] or "{}").get("days")
        except (TypeError, ValueError, AttributeError):
            days = None
        cell = out[key[0]][key[1]]
        cell["train_runs"] += 1
        cell["sessions"] += float(days) * trials if _figure(days) is not None else 0.0
    etf: tuple[float, str] | None = None
    for lane, structures in out.items():
        for structure, cell in structures.items():
            if structure == "panel":
                value = panel_neff(root)
                size, source = value, (FILE if value is not None else None)
            else:
                etf = etf if etf is not None else etf_neff(root)
                size, source = etf if (structure == "etf" or etf[1] != "default") else (None, None)
            years = cell.pop("sessions") / YEAR_SESSIONS
            read = min(float(TRAIN_YEARS[structure]), years)
            independent = None if size is None else read * size
            cell.update(program_years=round(years, 2), train_years=round(read, 2),
                        neff=None if size is None else round(size, 2), neff_source=source,
                        independent_asset_years=None if independent is None else round(independent, 2),
                        replay_multiple=round(years / independent, 2) if independent else None)
    return out


def funnel_lines(rows: Any) -> list[str]:
    """`funnel_rows`' answer as a report's lines, one a lane and structure that ran (counts, N_eff and the multiple:
    never a return). A structure with no N_eff says "unmeasured"; rows that are not `funnel_rows`' shape give no
    line. For the operator's report (the daily page prints from its own allowlist and shows none of it)."""
    lines = []
    for lane, structures in sorted(rows.items()) if isinstance(rows, Mapping) else ():
        for structure, cell in sorted(structures.items()) if isinstance(structures, Mapping) else ():
            if not isinstance(cell, Mapping) or not cell.get("train_runs"):
                continue
            head = (f"{lane} / {structure}: {cell.get('program_years')} simulated program-years in "
                    f"{cell['train_runs']} Train runs")
            if cell.get("independent_asset_years") is None:
                lines.append(f"{head}; independent asset-years unmeasured (no N_eff for its data)")
                continue
            multiple = cell.get("replay_multiple")
            lines.append(f"{head} on {cell['independent_asset_years']} independent asset-years "
                         f"({cell.get('train_years')} Train years x N_eff {cell.get('neff')}, "
                         f"{cell.get('neff_source')}): each asset-year replayed "
                         f"{'n/a' if multiple is None else multiple} times. Simulated years are compute, not evidence")
    return lines


__all__ = ["FILE", "WALL_S", "STORE_DIR", "SEGMENT", "RUN_KEY", "MIN_NAMES", "MIN_SESSIONS", "YEAR_SESSIONS",
           "TRAIN_YEARS", "ETF_NEFF_DEFAULT", "FORWARD_REPORT", "neff", "residuals", "formations", "panel_returns",
           "measure", "run", "panel_neff", "etf_neff", "funnel_rows", "funnel_lines"]
