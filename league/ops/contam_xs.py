"""The contamination probe's panel strata P4-P6, and the look's permit (release E4, package B's patch 18).

Owner: package B of release E4. Protected (league/ops/). THE HOUSE'S `contam_probe` JOB IS THIS MODULE'S `run` since
release E4: release E3's probe (league/ops/contam_probe.py) with THE PLAN of the panel strata handed in. Why a module
of its own: E3's seal lets its probe import no module of league/xs, so the probe owns every word of a prompt and the
state of a run, and this module owns what only the panel can say: which members and periods a panel stratum may ask
about, the truth on the House, and the permit a panel look waits on (the captain's A22 (3)).

WHEN THE PLAN IS HANDED IN (`run`, `plan`). `elane.panel.mode` "off" (the lane's switch, read as set), no panel store
or universe under `<state>/equity-daily/` yet, or a panel whose coverage verdict is "insufficient": NO PLAN, and the
job is release E3's probe to the byte (no panel stratum, no permit written). Otherwise the job first asks the quiet
windows with its own wall (`league.xs.config.quiet(now, WALL_S)`: a skipped receipt, as every E4 job; its Saturday
00:10Z occurrence never meets a wall), then the probe opens its own store and mints the gate's capability, and `plan`
opens the panel store under THAT capability and reads it once (the membership, and the arrays' shas on one Train
session). A panel store that cannot be read there fails the job before any route is marked or dollar spent.

WHAT A PANEL STRATUM ASKS (names and the calendar only; the words are the probe's).
- THE PERIODS (`Plan.periods`): of the era "2016-24", the months (P4, P6) and ISO weeks (P5) that lie, base and end,
  inside ONE span of `league.xs.config.TRAIN_SEGMENTS` (2017-19 and 2022-24): never a period of 2016 or 2021 (history
  only), never one of 2020 (the reserve: no such row exists), and none whose base is in such a year (each segment's
  first month and first week are left out). Of "2025" and "2026H1", every period of the calendar.
- THE MEMBERS (`Plan.names` for P4 and P5): the tickers that were unmasked index members, under one asset and one
  ticker, on EVERY base day of the era's admitted months and on the last of them's end, and that the panel store
  holds a column for. The probe draws its K a cell from them by its own hash rule, the same for every route. STATED
  COST: names that stayed in the index through an era; a route recalls those at least as well as the ones that left.
  P6's names are the probe's own (`contam_probe.FACTORS`).

TRUTH (`Plan.truths`; on the House, never written; asked by the probe a cell at once, after the cell's answers).
- From THE PANEL STORE through its own windows, one slice a period under the run key `RUN_KEY`: a "2016-24" period
  by `PanelStore.train` (no capability); a 2025 or 2026 period by `PanelStore.bars("look", ...)`, which the store
  opens only for the gate's capability (`StoreRefused` without it: 2025 is refused here as 2026 is, though the store
  would open Validation's days without one). A price is the adjustment=all close of a VALID bar
  (`league.xs.placebo.prices`), the base is the last session before the period.
- P4, P5: the member's close ratio over the period less the ratio of THE FUND OF ITS SECTOR, the House's own
  statistical sector at the base (`league.xs.ctx.derive`: the fund of `league.xs.config.FUNDS` whose market-residual
  returns its own correlate most with): "more", "less", "tie" for a zero; None when a close, the sector or the
  membership at the base is missing.
- P6: the House panel factors as a run's record carries them (league/xs/engine.py `factors`, held equal by
  `league/tests/test_contam_xs.py` on a real run): the thirds of the names eligible at the base by 12-1 momentum, by
  the trailing five-session return reversed, and by beta (`derive`'s, ranked ascending by (value, column)); each
  session of the month the equal-weight mean move of the top third less the bottom third's (a side with no move
  that session gives 0); the truth is the sign of the month's sum (`math.fsum`). None when a third would be empty.

THE PERMIT (`permit`, `write_permit`; the swarm reads it: `league.swarm.elane_xs.probe_reading`, `probed`).
`<state>/xs-look-permit.json` (atomic, 0600): {"version": "xs-look-permit-1", "routes": {route: {"at", "model",
"cells": {"P4" | "P5" | "P6": {era: {"readable": bool, "recalled": bool}}}}}}: one row for every route whose
PUBLISHED result carries all three panel strata, and NOTHING ELSE of a cell (no count, no rate, no p). It is rewritten
from the probe's own file each time a result is published and after every run of this job that had a plan (so a
permit lost or left behind is made again). The probe's own file is never read by the swarm (release E3's seal).

Standard library at import; numpy and league.xs inside the functions that read the panel.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (the registry row's).
WALL_S = 3300
#: The equity lanes' state directory (`league.ops.equity_data.STORE_DIR`; spelled here, a test holds them equal).
STORE_DIR = "equity-daily"
#: The run key every slice of a truth is asked under (its salted ids are read by no program and leave no file).
RUN_KEY = "contam|sp500"
#: The probe's era whose panel periods are Train periods (no capability); every other era is read through "look".
TRAIN_ERA = "2016-24"
#: The strata whose names are index members, and the stratum whose periods say when a member must have been one.
MEMBER_STRATA = ("P4", "P5")
MONTH_STRATUM = "P4"


# ------------------------------------------------------------------------------------------------- the arithmetic
def thirds(values: Any, eligible: Any) -> tuple[Any, Any] | None:
    """(the bottom third's columns, the top third's) of `values` among the eligible columns with a finite value,
    ranked ascending by (value, column); None when a third would be empty. The engine's own rule for its factors."""
    import numpy as np

    values = np.asarray(values, dtype=np.float64)
    cols = np.flatnonzero(np.asarray(eligible, dtype=bool) & np.isfinite(values))
    third = len(cols) // 3
    if third < 1:
        return None
    order = cols[np.lexsort((cols, values[cols]))]
    return order[:third], order[-third:]


def factor_days(bars: Any, base: int, last: int) -> dict[str, list[float] | None]:
    """The House panel factors over the sessions `base + 1 .. last` of a slice (`league.xs.store.PanelBars`), thirds
    formed at the close of session index `base`: {"mom" | "strev" | "beta": one value a session, or None when a third
    would be empty}. A session's value is the equal-weight mean move of the top third less the bottom third's, over
    the names with a move that session (0.0 when a side has none), as league/xs/engine.py computes a run's
    `factors`."""
    import numpy as np

    from ..xs import config as xs_config
    from ..xs import ctx as xs_ctx
    from ..xs import placebo as xs_placebo
    from ..xs import program as xs_program

    base, last = int(base), int(last)
    _, closes = xs_placebo.prices(bars)
    needs = xs_program.Needs(panel="sp500", history=xs_config.MAX_HISTORY, max_names=xs_config.MIN_NAMES,
                             rebalance="monthly", weekday=0, max_hold_sessions=xs_config.MAX_HOLD_CAP)
    derived = xs_ctx.derive(xs_ctx.inputs_from_panel(bars, base, needs=needs, cash=0.0, equity=0.0, budget=0.0,
                                                     params={}))
    eligible = np.asarray(derived.elig, dtype=bool)
    with np.errstate(invalid="ignore", divide="ignore"):
        week = closes[base] / closes[base - 5] - 1.0 if base >= 5 else np.full(closes.shape[1], np.nan)
        moves = closes[base + 1:last + 1] / closes[base:last] - 1.0
    sides = {"mom": thirds(np.asarray(derived.mom, dtype=np.float64), eligible), "strev": thirds(-week, eligible),
             "beta": thirds(np.asarray(derived.beta, dtype=np.float64), eligible)}
    out: dict[str, list[float] | None] = {}
    for name, side in sides.items():
        if side is None:
            out[name] = None
            continue
        values = []
        for move in moves:
            low, high = (move[cols] for cols in side)
            low, high = low[np.isfinite(low)], high[np.isfinite(high)]
            values.append(math.fsum(high.tolist()) / high.size - math.fsum(low.tolist()) / low.size
                          if low.size and high.size else 0.0)
        out[name] = values
    return out


def _word(gap: float | None) -> str | None:
    """A truth's word: "more" above zero, "less" under it, "tie" at it, None for no figure."""
    if gap is None or not math.isfinite(gap):
        return None
    return "tie" if gap == 0 else ("more" if gap > 0 else "less")


# --------------------------------------------------------------------------------------------------------- the plan
class Plan:
    """THE PLAN of the panel strata for one run of the probe (the module docstring), over the House's panel store.
    `store`: a `league.xs.store.PanelStore`, opened with the gate's capability on the House (a 2025 or 2026 truth
    is refused without it). What the probe asks of it: `names`, `periods`, `truths`, `published`."""

    def __init__(self, store: Any, state_root: str | Path | None = None):
        from . import contam_probe

        self.store = store
        self.universe = store.universe()
        self.state_root = None if state_root is None else Path(state_root)
        self._columns = {int(aid) for aid in store.aids().tolist()}
        self._aid: dict[tuple[str, str], int] = {}
        self._names: dict[str, list[str]] = {}
        self._periods: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
        for era in contam_probe.ERAS:           # read once: a universe that cannot be read fails the job here
            self.names(MONTH_STRATUM, era)

    # ------------------------------------------------------------------ what a stratum may ask
    def _admitted(self, stratum: str, era: str) -> list[tuple[str, str, str]]:
        """(period, base, end) of the era's periods a panel stratum may ask (THE PERIODS)."""
        found = self._periods.get((stratum, era))
        if found is None:
            from ..xs import config as xs_config
            from . import contam_probe

            every = contam_probe.periods(stratum, era)
            if era == TRAIN_ERA:
                spans = [(lo.isoformat(), hi.isoformat()) for lo, hi in xs_config.TRAIN_SEGMENTS]
                every = [row for row in every if any(lo <= row[1] and row[2] <= hi for lo, hi in spans)]
            found = self._periods[(stratum, era)] = list(every)
        return found

    def periods(self, stratum: str, era: str) -> list[str]:
        """The period names a panel stratum asks in an era, oldest first (calendar and constants only)."""
        return [name for name, _, _ in self._admitted(stratum, era)]

    def names(self, stratum: str, era: str) -> list[str]:
        """P4's and P5's names in an era, sorted (THE MEMBERS): [] for a stratum that asks about no member, and for an
        era with no admitted month."""
        if stratum not in MEMBER_STRATA:
            return []
        found = self._names.get(era)
        if found is None:
            months = self._admitted(MONTH_STRATUM, era)
            days = sorted({base for _, base, _ in months} | ({months[-1][2]} if months else set()))
            held: set[tuple[int, str]] | None = None
            for day in days:
                today = {(int(aid), str(symbol)) for aid, symbol in self.universe.members(dt.date.fromisoformat(day))}
                held = today if held is None else held & today
            pairs = sorted((symbol, aid) for aid, symbol in (held or ()) if aid in self._columns)
            twice = {symbol for i, (symbol, _) in enumerate(pairs) if i and pairs[i - 1][0] == symbol}
            found = self._names[era] = [symbol for symbol, _ in pairs if symbol not in twice]
            self._aid.update({(era, symbol): aid for symbol, aid in pairs if symbol not in twice})
        return list(found)

    # ------------------------------------------------------------------ the truth
    def _slice(self, era: str, base: str, last: str, aids: Sequence[int] | None) -> Any:
        """The panel slice of one period, with its look-back: Train by `PanelStore.train`; a 2025 or 2026 period by
        the sealed "look" window, which opens only for the gate (StoreRefused without the capability)."""
        from ..equity.store import StoreRefused
        from ..xs import config as xs_config

        first, end = dt.date.fromisoformat(base), dt.date.fromisoformat(last)
        if era == TRAIN_ERA:
            return self.store.train(first, end, history=xs_config.MIN_HISTORY, run_key=RUN_KEY, aids=aids)
        if not self.store.gate:
            raise StoreRefused(f"a panel truth of {era} opens only for the gate")
        return self.store.bars("look", history=xs_config.MIN_HISTORY, run_key=RUN_KEY, start=first, end=end, aids=aids)

    def truths(self, questions: Sequence[Mapping[str, Any]]) -> list[str | None]:
        """One truth a question of a panel cell, in order (TRUTH): "more" | "less" | "tie" | None. `MissingData` for a
        store being rewritten, `StoreRefused` for a sealed period without the capability."""
        import numpy as np

        from ..equity.store import ordinal
        from ..xs import config as xs_config
        from ..xs import ctx as xs_ctx
        from ..xs import placebo as xs_placebo
        from ..xs import program as xs_program

        out: list[str | None] = [None] * len(questions)
        groups: dict[tuple[str, str, str, str], list[int]] = {}
        for i, q in enumerate(questions):
            groups.setdefault((str(q["stratum"]), str(q["era"]), str(q["first"]), str(q["last"])), []).append(i)
        for (stratum, era, base, last), members in groups.items():
            if (str(questions[members[0]]["period"]), base, last) not in self._admitted(stratum, era):
                continue  # a period this plan never offered: no truth
            # P4 and P5 read the columns of the members asked about (members at the base); P6 every member's.
            wanted: dict[int, int] = {}
            if stratum in MEMBER_STRATA:
                self.names(stratum, era)
                day = dt.date.fromisoformat(base)
                for i in members:
                    aid = self._aid.get((era, str(questions[i]["symbol"])))
                    if aid is not None and self.universe.member(aid, day):
                        wanted[i] = aid
                if not wanted:
                    continue
            piece = self._slice(era, base, last, sorted(set(wanted.values())) if wanted else None)
            bars = piece.bars
            at = {int(d): j for j, d in enumerate(np.asarray(bars.days, dtype=np.int64).tolist())}
            i0 = at.get(ordinal(dt.date.fromisoformat(base)))
            i1 = at.get(ordinal(dt.date.fromisoformat(last)))
            if i0 is None or i1 is None or not 1 <= i0 < i1:
                continue  # the store does not hold the period whole
            if stratum not in MEMBER_STRATA:
                sums = factor_days(bars, i0, i1)
                for i in members:
                    values = sums.get(str(questions[i]["symbol"]))
                    out[i] = None if values is None else _word(math.fsum(values))
                continue
            _, closes = xs_placebo.prices(bars)
            needs = xs_program.Needs(panel="sp500", history=xs_config.MAX_HISTORY, max_names=xs_config.MIN_NAMES,
                                     rebalance="monthly", weekday=0, max_hold_sessions=xs_config.MAX_HOLD_CAP)
            derived = xs_ctx.derive(xs_ctx.inputs_from_panel(bars, i0, needs=needs, cash=0.0, equity=0.0, budget=0.0,
                                                             params={}))
            column = {int(aid): j for j, aid in enumerate(np.asarray(piece.aids).tolist())}
            for i, aid in wanted.items():
                col = column.get(aid)
                sector = -1 if col is None else int(derived.sector[col])
                if sector < 0:
                    continue
                fund = xs_config.FUND_COLUMNS[sector]
                with np.errstate(invalid="ignore", divide="ignore"):
                    gap = float(closes[i1, col] / closes[i0, col] - closes[i1, fund] / closes[i0, fund])
                out[i] = _word(gap)
        return out

    # ------------------------------------------------------------------ the permit
    def published(self, doc: Mapping[str, Any]) -> None:
        """The probe published a route's result: the permit is rewritten from the probe's file as it now stands."""
        if self.state_root is not None:
            write_permit(self.state_root, doc)


# ------------------------------------------------------------------------------------------------------- the permit
def permit(doc: Mapping[str, Any] | None) -> dict[str, Any]:
    """THE PERMIT a probe file gives (the module docstring): one row for every route whose published result (`at`)
    carries every stratum of `league.swarm.elane_xs.PROBE_STRATA` with at least one cell, each cell cut to its two
    words. Nothing else of the file leaves it."""
    from ..swarm import elane_xs

    routes = doc.get("routes") if isinstance(doc, Mapping) and isinstance(doc.get("routes"), Mapping) else {}
    out: dict[str, Any] = {}
    for key, row in sorted(routes.items()):
        if not isinstance(row, Mapping) or not isinstance(row.get("at"), str) or not row["at"]:
            continue
        cells = row.get("cells") if isinstance(row.get("cells"), Mapping) else {}
        strata = {}
        for stratum in elane_xs.PROBE_STRATA:
            eras = cells.get(stratum)
            kept = {str(era): {"readable": cell.get("readable") is True, "recalled": cell.get("recalled") is True}
                    for era, cell in sorted(eras.items()) if isinstance(cell, Mapping)} if isinstance(eras, Mapping) else {}
            if kept:
                strata[stratum] = kept
        if len(strata) == len(elane_xs.PROBE_STRATA):
            out[str(key)] = {"at": row["at"], "model": row.get("model") if isinstance(row.get("model"), str) else None,
                             "cells": strata}
    return {"version": elane_xs.PROBE_VERSION, "routes": out}


def write_permit(root: str | Path, doc: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Write `<root>/xs-look-permit.json` (`league.swarm.elane_xs.PROBE_FILE`; atomic, 0600) from a probe file's
    content (`doc`; default: the probe's own file as it stands) and return what was written."""
    from ..swarm import elane_xs
    from . import contam_probe
    from .context import write_json

    found = permit(contam_probe.read(root) if doc is None else doc)
    write_json(Path(root) / elane_xs.PROBE_FILE, found)
    return found


# -------------------------------------------------------------------------------------------------------------- the job
def asked(root: str | Path, settings: Mapping[str, Any] | None) -> str | None:
    """Why this run asks NO panel stratum, or None: the lane's switch is off (`elane.panel.mode`, read as set), or
    the House holds no panel store or no universe yet. Files' names only: nothing is opened."""
    from ..swarm import elane_xs
    from ..xs import store as xs_store

    try:
        mode = elane_xs.cfg(settings)["mode"]
    except Exception as exc:  # noqa: BLE001 - a switch that cannot be read is off
        return f"the panel lane's switch could not be read ({type(exc).__name__}): read as off"
    if mode == "off":
        return "elane.panel.mode is off"
    base = Path(root) / STORE_DIR
    if not (base / xs_store.PANEL_DIR / xs_store.PANEL_MANIFEST).is_file() or \
            not (base / xs_store.UNIVERSE_DIR / xs_store.UNIVERSE_MANIFEST).is_file():
        return "no panel store yet"
    return None


def plan(ctx: Any, settings: Mapping[str, Any] | None, capability: Any) -> Plan | None:
    """THE PLAN for this run (what `contam_probe.probe` calls once its own store is open), or None (`asked`, or a
    panel whose coverage verdict is "insufficient": the lane is off by its own rule). The panel store is opened under
    the probe's own capability and READ ONCE here: the membership of every era, and one Train session's slice (every
    array's sha against the manifest). `MissingData` / `StoreRefused` when it cannot be read: the job fails before
    any route is marked."""
    from ..xs import config as xs_config
    from ..xs import store as xs_store

    root = Path(ctx.root)
    if asked(root, settings) is not None:
        return None
    store = xs_store.PanelStore(root / STORE_DIR, gate=capability)
    if store.verdict() == "insufficient":
        return None
    found = Plan(store, root)
    sessions = store.sessions("train")
    if sessions:
        store.train(sessions[-1], sessions[-1], history=xs_config.MIN_HISTORY, run_key=RUN_KEY, aids=[])
    return found


def run(ctx: Any) -> dict[str, Any]:
    """THE HOUSE'S `contam_probe` JOB since release E4 (league/ops/registry.py): `contam_probe.probe(ctx, panel=plan)`.
    With no panel stratum to ask (`asked`) it is release E3's probe and nothing else. With one, the quiet windows
    first (a skipped receipt: no E4 work runs through a wall); the probe's receipt, with `panel` and `permit` beside;
    and after a run that had a plan the permit is written again from the probe's file as it stands."""
    from ..swarm import settings as settings_mod
    from . import contam_probe

    root = Path(ctx.root)
    settings = settings_mod.load(root, config=ctx.config)
    if contam_probe.mode(settings) == "off" or asked(root, settings) is not None:
        return contam_probe.probe(ctx, panel=plan)   # E3's probe: `plan` answers None again, from the same settings
    from ..xs import config as xs_config

    try:
        why = xs_config.quiet(ctx.now(), WALL_S)
    except Exception as exc:  # noqa: BLE001 - a job that cannot learn whether it stands at a wall does not start
        why = f"the quiet windows could not be read ({type(exc).__name__}: {str(exc)[:160]})"
    if why is not None:
        return {"status": "skipped", "why": why}
    made: list[bool] = []

    def planned(*args: Any) -> Plan | None:
        found = plan(*args)
        made.append(found is not None)
        return found

    out = contam_probe.probe(ctx, panel=planned)
    if any(made):
        try:
            write_permit(root)
        except Exception as exc:  # noqa: BLE001 - the probe's result stands; the next run writes the permit again
            ctx.alert("warning", f"contam_probe: the look permit could not be written ({type(exc).__name__})")
    return out


__all__ = ["WALL_S", "STORE_DIR", "RUN_KEY", "TRAIN_ERA", "MEMBER_STRATA", "MONTH_STRATUM", "thirds", "factor_days",
           "Plan", "permit", "write_permit", "asked", "plan", "run"]
