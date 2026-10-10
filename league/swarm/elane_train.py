"""THE EQUITY TRAIN (release E2, Oct 2026): the bar the swarm's own share programs meet on Train before their one
Validation try (equity-v1), the Train runs on the House, the equity review at the first pass, the equity TRAIN MAP the
architect reads, and the minimal equity researcher that writes and revises a family's program on Train alone.

THE BAR, equity-v1 (the design's section 6b, unchanged; `train_score`). A version runs over the House store's Train
window (2016-01-04..2024-12-31; never a day of 2025 or 2026: `TRAIN_FIRST`, `TRAIN_LAST`; a result that carries another
year is refused whole and judged on nothing) at 1.0x and at 1.5x the half-spread (`league.equity.config.K_BASE`,
`K_STRESS`), through E1's isolated runner (`league.equity.runner.Isolated.train`: the program in the decider child,
never in the swarm process). It PASSES when all hold:
  Y1  ACTIVE in at least `min_active_years` (3) Train years: a year with at least `year_min_trades` (40) closed lots
      and `year_min_days` (20) entry days, on the 1.0x run;
  Y2  no Train year's t (the year's daily P&L t, `by_year.t_daily`; a flat year reads 0) below `year_t_floor` (-1.0),
      on the 1.0x run;
  P1  the 1.5x run's net P&L over Train above zero;
  R1  the 1.0x net P&L above zero and the 1.5x P&L at least `cost_ratio` (0.5) of it.
REPORTED BESIDE, NEVER A BAR: the same-exposure buy-and-hold over the same sessions (`bh.pnl`), the mean
time-matched excess (MTE: `mte.mean`, `mte.t`) and the DRIFT SHARE (the buy-and-hold P&L over the program's, while
the program's is above zero: near one, the program earned what holding its average exposure earned). Every number
here is a Train figure. The bar's constants are rules (`BAR`), never a market result.

WHAT A VERDICT IS (`score`). Only the PROGRAM's own doing is judged: its runs finished ("ok": the bar), it was
disqualified by its own errors or timeouts ("DQ"), the child refused to load it ("LOAD": a `ProgramRefused`, a
`CodeRefused` or a `NeedsRefused`), or the child failed its run `train_max_errors` times in a row while other programs'
Train runs completed after its first failure ("RUN"). Anything else is the House's (no equity store yet, the store
being rewritten, a decider child that could not start, a result outside the window, "no_data"): the version is NOT
scored, spends no budget and asks no model; it is tried again after a backoff (`train_every_seconds` doubling, at most
`BACKOFF_MAX`), and a result outside the window is also an alert. Of the verdicts, only Y1, Y2, P1 and R1 judge the
MECHANISM (`JUDGED`); the others judge a program that could not be judged.

THE REVIEW (league/swarm/elane_review.py). A program holding a raw price or volume level against a constant or a PARAMS
value is refused before it is stored (`check_code`). At a version's first bar pass two different models read it under
the leakage rubric (`EquityResearcher.review_step`) before it may be its lineage's Validation try: a pass of both
writes the record E1's look reads (`state["review"]`) and makes it the family's pass; a failure is a Train failure of
that version ("REVIEW") and spends no try.

THE RECORD (family state `STATE_KEY`, E2's own; `record_of`). Per version: its verdict, its fails, its Train figures
and the equity identity it was judged under (`identity`); the family's `status` ("researching", "passed", "refuted",
"stalled", "closed"), `passed_version`, a pending `review`, the `passed_review` (E2's copy of the record E1 reads), its
write `attempts`, its `refused` programs and an `infra` backoff. The FIRST version that passes the bar AND the review
ends the family's Train research: it is the lineage's one Validation try (`may_validate`, the guard E1's tournament
applies: ELANE_E2_PATCHES.md patch 5; the family's `best_version` and `best_train` are set to it). A family whose Train
budget (`train_budget` scored versions, 4) or attempts (`train_max_attempts`) are spent with no pass, or whose
researcher stops after a judged version, is RETIRED: REFUTED on Train (a graveyard row in E2's own words, Train facts
only, and its record's `refuted`) when at least one version was judged on the bar, else STALLED (no graveyard row, no
cell count: no program of it could be judged, which says nothing of the mechanism). The equity generators read the
record, never the graveyard table.

THE IDENTITY (`identity`; E1's `evaluator.equity_identity`). Each verdict carries the identity it was judged under. A
pass judged under another identity, whose version has not had its Validation try, is Train-scored again before E1 may
validate it (`pass_current`): passed again it stands; failed, the pass is withdrawn and the research goes on. E1's
adoption clears `best_version` and the review state; the round restores both for a pass that stands (`upkeep`).

THE EQUITY TRAIN MAP (`train_map`, `train_map_text`). The cells (lane x agenda mechanism x universe group: `cell_of`)
of every E2 family, alive or retired, with its births, the families Train-scored, passed, refuted on Train and stalled,
and the best passing pooled Train t (one decimal), labelled IN-SAMPLE everywhere (`MAP_LABEL`). Computed on the House
from E2's own records at each request: never a committed figure, never a census figure, never a Validation or look
outcome (A9 D3: a family's later fate does not move its row). A cell with `refuted_cell_cap` (3) refutations (each with
a judged version) and no pass is CLOSED (`closed_cells`): the equity pass refuses a birth there.

THE RESEARCHER (`EquityResearcher`; minimal by design). A round (`run`; every `train_every_seconds`, at most
`train_per_round` families, the least recently worked first) gives each E2 family one step: re-score a stale pass, or
review a bar pass, or Train-score its newest version, or write its first program or a revision on its birth route, or
retire it. The question (`brief`) holds the family's card and agenda prior, EQUITY.md, the bar, and its own versions'
Train figures, fails and review reasons, nothing else (league/swarm/elane_seal.py). A program is checked statically
before it is stored (`league.gym.safety.check_program`; NEEDS a literal dict whose symbols are the family's own; the
level rule), and its PARAMS are its declaration's (a version's params are {}). A `stop` answer before any version was
judged on the bar is not accepted (it counts as an attempt).

With `elane.mode` "off" nothing here acts. Standard library only.
"""

from __future__ import annotations

import ast
import math
import re
import time
from typing import Any, Callable, Mapping, Sequence

from ..equity import BETA, EQUITY, LANES
from ..equity import config as eqconfig
from . import elane_review, elane_seal, elane_yield

# ----------------------------------------------------------------------------------------------------------- vocabulary
OBJECTIVE = "equity-v1"
#: E2's family-state key (its own Train record).
STATE_KEY = "elane_e2"
#: The store's kv key of the researcher's last round.
TRAIN_AT_KEY = "elane_e2_train_at"
#: The store's kv key of the last time any E2 Train run completed (a child that fails one program while this moves on is
#: that program's fault: "RUN").
TRAIN_OK_KEY = "elane_e2_train_ok_at"
#: The longest backoff after a failure of the House's (no store, a child that could not start, a result outside Train).
BACKOFF_MAX = 6 * 3600.0
#: THE TRAIN WINDOW (league/equity/config.py WINDOWS["train"]): the only days a run here may read.
TRAIN_FIRST, TRAIN_LAST = eqconfig.WINDOWS["train"][0], eqconfig.WINDOWS["train"][1]
TRAIN_YEARS = tuple(range(TRAIN_FIRST.year, TRAIN_LAST.year + 1))
#: The bar's rules (the design's 6b; rules, never market figures).
BAR: dict[str, Any] = {"min_active_years": 3, "year_min_trades": 40, "year_min_days": 20, "year_t_floor": -1.0,
                       "cost_ratio": 0.5}
FAILS: dict[str, str] = {
    "RUN": "the decider child failed this program's Train run again and again while other programs' runs completed",
    "DQ": "the program was disqualified on Train by its own errors or timeouts",
    "LOAD": "the decider child refused to load the program",
    "REVIEW": "the equity review refused the program (an absolute level, a reconstructed calendar or lookahead)",
    "WINDOW": "the Train result carried a day outside 2016-2024 and was refused whole",
    "Y1": f"active (at least {BAR['year_min_trades']} closed lots on {BAR['year_min_days']} entry days) in fewer than "
          f"{BAR['min_active_years']} Train years",
    "Y2": f"a Train year's daily P&L t below {BAR['year_t_floor']:g}",
    "P1": "net P&L at or below zero at 1.5x the half-spread",
    "R1": f"the 1.0x net P&L at or below zero, or the 1.5x P&L under {BAR['cost_ratio']:g} of it",
}
#: The researcher's settings (`elane.e2` keys; defaults here, policy.json in ELANE_E2_PATCHES.md) and their bounds.
DEFAULTS: dict[str, Any] = {"train_budget": 4, "train_max_attempts": 7, "train_max_errors": 3, "train_every_seconds": 600,
                            "train_per_round": 3, "train_max_output_tokens": 12000, "train_effort": "medium",
                            "refuted_cell_cap": 3}
BOUNDS: dict[str, tuple[float, float]] = {"train_budget": (1, 12), "train_max_attempts": (1, 30),
                                          "train_max_errors": (1, 10), "train_every_seconds": (60, 86400),
                                          "train_per_round": (1, 20), "train_max_output_tokens": (2000, 64000),
                                          "refuted_cell_cap": (1, 50)}
EFFORTS = ("minimal", "low", "medium", "high", "xhigh")
STATUSES = ("researching", "passed", "refuted", "stalled", "closed")
#: The fails that judge the MECHANISM on Train (the bar's). A family is REFUTED only with a version judged by one of these;
#: RUN, DQ, LOAD and REVIEW judge a program, so a family with no other is STALLED (no graveyard row, no cell count).
JUDGED = ("Y1", "Y2", "P1", "R1")
#: The exception classes (by name, anywhere in the class's MRO) that are a program the child would not load: "LOAD".
LOAD_REFUSALS = ("ProgramRefused", "CodeRefused", "NeedsRefused")
#: The exception classes that are the child failing a run (league/equity/runner.py `RunFailed`; the decider's own): the
#: program's fault ("RUN") only once other programs' runs complete meanwhile, else the House's.
RUN_FAILURES = ("RunFailed", "DeciderError")
MAP_LABEL = "in-sample: the swarm's own Train runs, 2016-2024, at 1.0x and 1.5x the half-spread; the screen decides"
REFUTED_TAG = "REFUTED"
STALLED_TAG = "STALLED"

#: THE AGENDA (the mechanisms the equity pass offers, each with its published prior; no figure). `available` False:
#: no program can read its inputs today (earnings dates and surprises are not in the House's data), so a card of it
#: is refused. The key is the family's spec `agenda` and the Train map's mechanism.
AGENDA: dict[str, dict[str, Any]] = {
    "overnight": {"title": "the overnight effect", "available": True, "lane": "beta (always in) or equity (conditioned)",
                  "text": "index ETFs have earned a large share of their return between the close and the next open, "
                          "and little intraday; buy at the close (\"at\": \"close\") and sell at the next open. Always "
                          "in, it is market beta; conditioned (after a down close, by volatility, around events), it is a "
                          "timing claim",
                  "priors": "Cliff, Cooper and Gulen (2008); Lou, Polk and Skouras (2019, Journal of Financial "
                            "Economics)"},
    "reversal": {"title": "short-term reversal", "available": True, "lane": "equity",
                 "text": "after a sharp one- to five-session fall, liquidity providers are paid to absorb the selling and "
                         "prices tend to rebound over the next sessions, more so when volatility is high",
                 "priors": "Jegadeesh (1990); Lehmann (1990); Nagel (2012, Review of Financial Studies); Connors and "
                           "Alvarez (2008) on index ETFs"},
    "trend": {"title": "time-series trend", "available": True, "lane": "equity",
              "text": "an asset whose own trailing 3-12 month return is positive tends to keep rising; hold it while its "
                      "trend is up (its trailing return, or its price against a long moving average), else hold cash",
              "priors": "Moskowitz, Ooi and Pedersen (2012, Journal of Financial Economics); Faber (2007); Hurst, Ooi "
                        "and Pedersen (2017)"},
    "rotation": {"title": "cross-sectional and sector momentum, rotation", "available": True, "lane": "equity",
                 "text": "rank the sector ETFs (or the index ETFs) by their trailing 3-12 month return, skipping the last "
                         "month, and hold the strongest few, rebalanced on a monthly clock",
                 "priors": "Jegadeesh and Titman (1993); Moskowitz and Grinblatt (1999, industries); Asness, Moskowitz "
                           "and Pedersen (2013)"},
    "low_vol": {"title": "low volatility", "available": True, "lane": "equity",
                "text": "low-volatility assets have earned about as much as high-volatility ones with less risk; hold the "
                        "lowest-volatility ETFs of a set, or scale exposure inversely to recent realized volatility",
                "priors": "Ang, Hodrick, Xing and Zhang (2006); Frazzini and Pedersen (2014); Moreira and Muir (2017)"},
    "turn_of_month": {"title": "turn of the month", "available": True, "lane": "beta or equity",
                      "text": "equity returns have concentrated from the last session of a month through the first few "
                              "sessions of the next (payroll and pension flows); ctx.sessions_to_month_end and "
                              "ctx.session_of_month give the clock",
                      "priors": "Ariel (1987); Lakonishok and Smidt (1988); McConnell and Xu (2008)"},
    "earnings_drift": {"title": "post-earnings drift", "available": False, "lane": "equity",
                       "text": "prices keep moving in the direction of an earnings surprise for weeks. NOT AVAILABLE: the "
                               "House has no earnings dates or surprises yet, so no program can read them; a card of "
                               "this mechanism is refused until they exist",
                       "priors": "Ball and Brown (1968); Bernard and Thomas (1989)"},
    "other": {"title": "another mechanism", "available": True, "lane": "beta or equity",
              "text": "a mechanism outside this list, with its own published prior named in the card's hypothesis",
              "priors": "named in the card"},
}
#: The universe groups of the map's cells (in this order).
GROUPS = ("index", "sectors", "defensive", "stocks")


# ----------------------------------------------------------------------------------------------------------- settings
def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """The researcher's settings from `elane.e2`, each inside its bound (a malformed value is its default)."""
    raw = elane_yield.e2_settings(settings)
    out = dict(DEFAULTS)
    for key, (lo, hi) in BOUNDS.items():
        x = _num(raw.get(key))
        if x is not None and lo <= x <= hi:
            out[key] = int(x) if isinstance(DEFAULTS[key], int) else x
    if raw.get("train_effort") in EFFORTS:
        out["train_effort"] = raw["train_effort"]
    return out


def lane_on(settings: Mapping[str, Any] | None) -> bool:
    """`elane.mode` is "gate" (E1's `elane.on`). An `elane` that cannot be read is off (fail closed)."""
    from . import elane

    try:
        return bool(elane.on(settings))
    except Exception:  # noqa: BLE001 - an unreadable switch is off
        return False


def symbols_group(symbols: Sequence[str]) -> str:
    """The universe group of a symbol set ("index", "sectors", "defensive", "stocks", joined by "+")."""
    seen = set()
    for raw in symbols:
        sym = str(raw).upper()
        if sym in eqconfig.INDEX_ETFS:
            seen.add("index")
        elif eqconfig.UNIVERSE.get(sym) == eqconfig.STOCK:
            seen.add("stocks")
        elif sym in ("TLT", "GLD"):
            seen.add("defensive")
        elif sym.startswith("XL"):
            seen.add("sectors")
    return "+".join(g for g in GROUPS if g in seen) or "none"


def cell_of(lane: Any, agenda: Any, symbols: Sequence[str]) -> tuple[str, str, str]:
    """A Train map cell: (lane, agenda mechanism, universe group)."""
    return (str(lane), str(agenda if agenda in AGENDA else "other"), symbols_group(symbols))


def cell_text(cell: Sequence[str]) -> str:
    return f"{cell[0]} / {cell[1]} / {cell[2]}"


# ----------------------------------------------------------------------------------------------------------- the bar
def _year_key(key: Any) -> int | None:
    try:
        return int(str(key)[:4])
    except (TypeError, ValueError):
        return None


def outside_years(result: Mapping[str, Any] | None) -> list[str]:
    """The years a result's by-year rows or its start and end name outside the Train window (WINDOW)."""
    result = result or {}
    out = []
    for key in (result.get("by_year") or {}):
        year = _year_key(key)
        if year is None or year not in TRAIN_YEARS:
            out.append(str(key))
    for name in ("start", "end"):
        day = str(result.get(name) or "")
        if day and (day[:10] < TRAIN_FIRST.isoformat() or day[:10] > TRAIN_LAST.isoformat()):
            out.append(day[:10])
    window = result.get("window")
    if window not in (None, "train"):
        out.append(str(window))
    return out


def year_rows(result: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The Train years' rows of a result's `by_year` ({"2016": {trades, days_traded, pnl, t, exposure, bh_pnl}})."""
    out = {}
    for key, row in sorted(((result or {}).get("by_year") or {}).items(), key=lambda kv: str(kv[0])):
        year = _year_key(key)
        if year is None or year not in TRAIN_YEARS or not isinstance(row, Mapping):
            continue
        out[str(year)] = {"trades": int(_num(row.get("trades")) or 0), "days_traded": int(_num(row.get("days_traded")) or 0),
                          "pnl": _num(row.get("pnl")), "t": _num(row.get("t_daily")),
                          "exposure": _num(row.get("exposure_mean")), "bh_pnl": _num(row.get("bh_pnl"))}
    return out


def _summary(result: Mapping[str, Any] | None) -> Mapping[str, Any]:
    s = (result or {}).get("summary")
    return s if isinstance(s, Mapping) else {}


def train_score(base: Mapping[str, Any] | None, stress: Mapping[str, Any] | None) -> dict[str, Any]:
    """equity-v1 on a version's 1.0x (`base`) and 1.5x (`stress`) Train results (the module docstring): {objective,
    passed, fails, why, score (the pooled daily t at 1.0x), years, active_years, pnl_10, pnl_15, ratio, summary,
    beside}. A result outside the window (WINDOW) or not "ok" (RUN) is judged on nothing else and shows no figure."""
    out: dict[str, Any] = {"objective": OBJECTIVE, "passed": False, "fails": [], "why": None, "score": None,
                           "years": {}, "active_years": 0, "pnl_10": None, "pnl_15": None, "ratio": None,
                           "summary": {}, "beside": {}}
    for result in (base, stress):
        if outside_years(result):
            out["fails"], out["why"] = ["WINDOW"], FAILS["WINDOW"]
            return out
    if not isinstance(base, Mapping) or base.get("status") != "ok" or not isinstance(stress, Mapping) \
            or stress.get("status") != "ok":
        out["fails"], out["why"] = ["RUN"], FAILS["RUN"]
        return out
    years = year_rows(base)
    for row in years.values():
        row["active"] = row["trades"] >= BAR["year_min_trades"] and row["days_traded"] >= BAR["year_min_days"]
    active = sum(1 for r in years.values() if r["active"])
    s10, s15 = _summary(base), _summary(stress)
    pnl_10, pnl_15 = _num(s10.get("pnl")), _num(s15.get("pnl"))
    fails = []
    if active < BAR["min_active_years"]:
        fails.append("Y1")
    if any((r["t"] if r["t"] is not None else 0.0) < BAR["year_t_floor"] for r in years.values()):
        fails.append("Y2")
    if pnl_15 is None or pnl_15 <= 0:
        fails.append("P1")
    if pnl_10 is None or pnl_10 <= 0 or pnl_15 is None or pnl_15 < BAR["cost_ratio"] * pnl_10:
        fails.append("R1")
    bh = (base.get("bh") or {}) if isinstance(base.get("bh"), Mapping) else {}
    mte = (base.get("mte") or {}) if isinstance(base.get("mte"), Mapping) else {}
    bh_pnl = _num(bh.get("pnl"))
    out.update({
        "passed": not fails, "fails": fails, "why": "; ".join(FAILS[f] for f in fails) or None,
        "score": _num(s10.get("t_daily")), "years": years, "active_years": active, "pnl_10": pnl_10, "pnl_15": pnl_15,
        "ratio": (round(pnl_15 / pnl_10, 4) if pnl_10 and pnl_10 > 0 and pnl_15 is not None else None),
        "summary": {k: _num(s10.get(k)) for k in ("trades", "days_traded", "pnl", "fees", "t_daily", "win_rate",
                                                 "exposure_mean", "max_drawdown", "mean_net_return")},
        "beside": {"bh_pnl": bh_pnl, "mte_mean": _num(mte.get("mean")), "mte_t": _num(mte.get("t")),
                   "drift_share": (round(bh_pnl / pnl_10, 4) if bh_pnl is not None and pnl_10 and pnl_10 > 0 else None)},
    })
    return out


def bar_text() -> str:
    """THE BAR in words (rules only)."""
    return (f"THE TRAIN BAR ({OBJECTIVE}), on the House's Train window 2016-2024 at 1.0x and 1.5x the half-spread: "
            f"(Y1) at least {BAR['year_min_trades']} closed lots on {BAR['year_min_days']} entry days in each of at least "
            f"{BAR['min_active_years']} Train years; (Y2) no Train year's daily P&L t below {BAR['year_t_floor']:g}; (P1) "
            f"net P&L above zero at 1.5x; (R1) the 1.0x net P&L above zero and the 1.5x P&L at least "
            f"{BAR['cost_ratio']:g} of it. Reported beside, never a bar: the same-exposure buy-and-hold over the same "
            "sessions, the mean time-matched excess (MTE) and the drift share. The first version that passes is the "
            "lineage's ONE Validation try, then ONE sealed look; their outcomes are sealed and never shown to anyone "
            "who writes programs.")


# ----------------------------------------------------------------------------------------------------------- the record
def record_of(fam: Mapping[str, Any] | None) -> dict[str, Any]:
    """E2's Train record of a family ({} for a family E2 did not bear)."""
    return elane_seal.e2_record(fam, STATE_KEY)


def e2_family(fam: Mapping[str, Any] | None) -> bool:
    """A family the equity pass bore (its spec's `e2_route`): E2 researches it on Train, and E1's tournament validates
    it only where `may_validate` allows (ELANE_E2_PATCHES.md patch 5)."""
    spec = (fam or {}).get("spec") or {}
    return isinstance(spec, Mapping) and bool(spec.get(elane_yield.ROUTE_KEY)) and \
        elane_seal.lane_of_spec(spec) is not None


def passed_version(fam: Mapping[str, Any] | None) -> int | None:
    n = record_of(fam).get("passed_version")
    return int(n) if isinstance(n, int) and not isinstance(n, bool) else None


def identity() -> dict[str, str] | None:
    """The equity identity verdicts are judged under now (E1's `evaluator.equity_identity`: the league/equity code's
    fingerprint and the engine version), or None when it cannot be read (then no pass reads as stale)."""
    try:
        from .evaluator import equity_identity

        value = equity_identity()
    except Exception:  # noqa: BLE001 - no identity: nothing is judged stale by it
        return None
    return dict(value) if isinstance(value, Mapping) else None


def judged(rec: Mapping[str, Any]) -> int:
    """How many of a record's versions the bar judged on the mechanism (a fail among `JUDGED`)."""
    return sum(1 for v in versions_of(rec).values() if any(f in JUDGED for f in (v.get("fails") or [])))


def tried(store: Any, fid: str, n: int) -> bool:
    """Whether version `n` of the family has had its Validation try (a Validation run at k 1.0 that the runner made: E1's
    `elane.lineage_tries` rule for one version). Outcome-free: only that the try happened."""
    try:
        row = store._one("SELECT 1 AS ok FROM runs WHERE family=? AND version=? AND \"window\"='validation' AND stress=1.0 "
                         "AND COALESCE(status, '') NOT IN ('error', 'no_data') LIMIT 1", (str(fid), int(n)))
    except Exception:  # noqa: BLE001 - unreadable: read as tried (a stale pass is then left to E1, never re-scored twice)
        return True
    return row is not None


def pass_current(store: Any, fam: Mapping[str, Any] | None) -> bool:
    """THE IDENTITY (the module docstring): the family's pass was judged under the equity identity in force, or its
    version has had its Validation try (E1 owns it from there), or no identity can be read."""
    n = passed_version(fam)
    if n is None:
        return False
    now = identity()
    if now is None:
        return True
    verdict = versions_of(record_of(fam)).get(str(n)) or {}
    return verdict.get("identity") == now or tried(store, str((fam or {}).get("id")), n)


def may_validate(store: Any, fam: Mapping[str, Any] | None, n: Any) -> bool:
    """THE GUARD E1'S TOURNAMENT APPLIES (ELANE_E2_PATCHES.md patch 5, after `n = elane.next_try(...)`): True for a family
    E2 did not bear; for an E2 family, only when `n` is its pass (the first version that passed equity-v1 AND the equity
    review), the review E1's look reads is in its state for that exact program, and the pass is current (`pass_current`).
    E1's `next_try` keeps its own due, stale and retry logic: a Validation gone stale is validated again through here."""
    if not e2_family(fam):
        return True
    fam = fam or {}
    p = passed_version(fam)
    if n is None or p is None or fam.get("retired_at"):
        return False
    try:
        if int(n) != p:
            return False
        version = store.version(str(fam["id"]), p)
        if version is None or not version.get("code"):
            return False
        from .gate import run_sha

        if not elane_review.holds(fam.get("state"), run_sha(version)):
            return False
        return pass_current(store, fam)
    except Exception:  # noqa: BLE001 - a guard that cannot be read admits nothing
        return False


def compact(score: Mapping[str, Any], *, at: str, ident: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A version's verdict as the record keeps it (Train figures only), with the identity it was judged under."""
    return {"at": at, "objective": OBJECTIVE, "passed": bool(score.get("passed")), "fails": list(score.get("fails") or []),
            "score": score.get("score"), "active_years": score.get("active_years"), "pnl_10": score.get("pnl_10"),
            "pnl_15": score.get("pnl_15"), "ratio": score.get("ratio"), "years": dict(score.get("years") or {}),
            "summary": dict(score.get("summary") or {}), "beside": dict(score.get("beside") or {}),
            "identity": dict(ident) if isinstance(ident, Mapping) else None}


def program_fault(code: str, why: str) -> dict[str, Any]:
    """The verdict of a version judged on its program alone (RUN, DQ, LOAD): no figure."""
    return {"objective": OBJECTIVE, "passed": False, "fails": [code], "why": f"{FAILS[code]}: {why}"[:400], "score": None,
            "years": {}, "active_years": 0, "pnl_10": None, "pnl_15": None, "ratio": None, "summary": {}, "beside": {}}


def _update(store: Any, fid: str, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Read-modify-write the family's record under the store's lock."""
    with store.atomic():
        fam = store.family(fid) or {}
        rec = record_of(fam)
        rec.setdefault("status", "researching")
        rec.setdefault("versions", {})
        change(rec)
        rec["last_at"] = store.now()
        store.set_state(fid, **{STATE_KEY: rec})
    return rec


# ----------------------------------------------------------------------------------------------------------- the map
def train_map(store: Any) -> list[dict[str, Any]]:
    """THE EQUITY TRAIN MAP's rows, one a cell (the module docstring), the cells with a pass first, then by births."""
    cells: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fam in elane_seal.equity_families(store):
        if not e2_family(fam):
            continue
        facts = elane_seal.train_facts(fam, STATE_KEY)
        rec = facts["record"]
        cell = cell_of(facts["lane"], facts["agenda"], facts["symbols"])
        row = cells.setdefault(cell, {"cell": cell, "births": 0, "scored": 0, "passed": 0, "refuted": 0, "stalled": 0,
                                      "best_t": None})
        row["births"] += 1
        versions = rec.get("versions") if isinstance(rec.get("versions"), Mapping) else {}
        row["scored"] += int(bool(versions))
        n = rec.get("passed_version")
        if isinstance(n, int) and not isinstance(n, bool):
            row["passed"] += 1
            t = _num((versions.get(str(n)) or {}).get("score"))
            if t is not None and (row["best_t"] is None or t > row["best_t"]):
                row["best_t"] = t
        # A refutation counts only with a version the bar judged on the mechanism (a family refuted before this rule with
        # none reads as stalled): the House's failures and programs that never ran close no cell.
        refuted = rec.get("status") == "refuted"
        row["refuted"] += int(refuted and judged(rec) > 0)
        row["stalled"] += int(rec.get("status") == "stalled" or (refuted and judged(rec) == 0))
    return sorted(cells.values(), key=lambda r: (-r["passed"], -r["births"], r["cell"]))


def closed_cells(store: Any, settings: Mapping[str, Any] | None) -> list[tuple[str, str, str]]:
    """The cells with at least `refuted_cell_cap` Train refutations (each with a version the bar judged) and no Train
    pass: a birth there is refused."""
    cap = cfg(settings)["refuted_cell_cap"]
    return [r["cell"] for r in train_map(store) if r["refuted"] >= cap and not r["passed"]]


def train_map_text(store: Any, settings: Mapping[str, Any] | None, *, limit: int = 40) -> str:
    """THE EQUITY TRAIN MAP for the architect's equity request ("" with no E2 family yet). Train facts only."""
    rows = train_map(store)
    if not rows:
        return ""
    closed = set(closed_cells(store, settings))
    lines = [f"EQUITY TRAIN MAP (lane / mechanism / universe group; {MAP_LABEL}). Each cell: births, families "
             "Train-scored, passed equity-v1 and the equity review (the best passing pooled daily t at 1.0x), refuted on "
             "Train by the bar, stalled (no program of the family could be judged: nothing said of the mechanism):"]
    for r in rows[:limit]:
        best = f" (best t {r['best_t']:.1f})" if r["best_t"] is not None else ""
        shut = "; CLOSED: no birth here" if r["cell"] in closed else ""
        lines.append(f"- {cell_text(r['cell'])}: births {r['births']}, scored {r['scored']}, passed {r['passed']}{best}, "
                     f"refuted {r['refuted']}, stalled {r['stalled']}{shut}")
    if len(rows) > limit:
        lines.append(f"- ... and {len(rows) - limit} more cells")
    return "\n".join(lines)


def refuted_rows(store: Any, *, limit: int = 30) -> list[dict[str, Any]]:
    """E2's equity graveyard: the families it refuted on Train with a version the bar judged (from its record, newest
    first): {id, lane, agenda, symbols, mechanism, codes, versions, why}. The rows that bind the equity cards
    (`closed_cells`); a stalled family is none."""
    out = []
    for fam in elane_seal.equity_families(store):
        if not e2_family(fam):
            continue
        facts = elane_seal.train_facts(fam, STATE_KEY)
        refuted = facts["record"].get("refuted")
        if facts["record"].get("status") != "refuted" or not isinstance(refuted, Mapping) or not judged(facts["record"]):
            continue
        out.append({"id": facts["id"], "lane": facts["lane"], "agenda": facts["agenda"], "symbols": facts["symbols"],
                    "mechanism": facts["mechanism"][:200], "codes": list(refuted.get("codes") or []),
                    "versions": int(refuted.get("versions") or 0), "why": str(refuted.get("why") or "")[:300],
                    "at": str(refuted.get("at") or "")})
    return sorted(out, key=lambda r: (r["at"], r["id"]), reverse=True)[:limit]


# ----------------------------------------------------------------------------------------------------------- programs
def needs_literal(code: str) -> dict[str, Any] | None:
    """The program's NEEDS when it is a literal dict at the top level, else None."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id == "NEEDS":
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                return None
            return dict(value) if isinstance(value, dict) else None
    return None


def check_code(code: Any, symbols: Sequence[str]) -> str | None:
    """Why a program cannot be a version of a family trading `symbols`, or None: the Gym's static rules
    (`league.gym.safety.check_program`, never executed here), NEEDS a literal dict whose symbols are the family's, and the
    equity level rule (`elane_review.level_text`)."""
    from ..gym.safety import CodeRefused, check_program

    text = str(code or "")
    try:
        check_program(text)
    except CodeRefused as exc:
        return f"refused by the code rules: {str(exc)[:300]}"
    except Exception as exc:  # noqa: BLE001 - an unreadable program is refused
        return f"refused: {type(exc).__name__}"
    needs = needs_literal(text)
    if needs is None:
        return "NEEDS must be a literal dict at the top level ({\"symbols\": [...], \"history\": n, \"max_hold_sessions\": n})"
    named = needs.get("symbols")
    if not isinstance(named, list) or not named:
        return "NEEDS[\"symbols\"] must be a non-empty list of the family's symbols"
    own = {str(s).upper() for s in symbols}
    foreign = [str(s) for s in named if str(s).upper() not in own]
    if foreign:
        return f"NEEDS names {', '.join(foreign[:6])}, outside the family's symbols ({', '.join(sorted(own))})"
    # THE LEVEL RULE (league/swarm/elane_review.py): a raw price or volume level held against a constant or a PARAMS value.
    return elane_review.level_text(text)


_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


def program_of(answer: Mapping[str, Any] | None) -> tuple[str | None, str, str | None]:
    """(the program, its note, a stop reason) from a researcher's answer: the JSON's `program` (else the first fenced
    Python block of its text), its `note`; `stop` when it gave up."""
    from .models import extract_json

    answer = answer or {}
    data = answer.get("json") if isinstance(answer.get("json"), Mapping) else extract_json(str(answer.get("text") or ""))
    data = data if isinstance(data, Mapping) else {}
    stop = data.get("stop")
    if isinstance(stop, str) and stop.strip():
        return None, "", " ".join(stop.split())[:400]
    code = data.get("program")
    if not isinstance(code, str) or "def decide" not in code:
        found = _FENCE.search(str(answer.get("text") or ""))
        code = found.group(1) if found else None
    return (code if isinstance(code, str) and code.strip() else None), " ".join(str(data.get("note") or "").split())[:400], None


def contract_text() -> str:
    """EQUITY.md, the program contract, as the House holds it (core's file; a short stand-in when it cannot be read)."""
    from pathlib import Path

    try:
        return (Path(__file__).resolve().parents[1] / "equity" / "EQUITY.md").read_text()[:12000]
    except OSError:
        return ("An equity program is one Python file: NEEDS = {\"symbols\": [...], \"history\": n, \"max_hold_sessions\": n}, "
                "PARAMS = {...}, and decide(ctx) returning intents: {\"buy\": SYM, \"share\": 0..1, \"at\": \"open\" | "
                "\"close\"}, {\"sell\": lot id}, {\"cancel\": order id}. math and numpy only; no date.")


# ----------------------------------------------------------------------------------------------------------- the researcher
RESEARCHER_SYSTEM = """You write ONE program for one family of the swarm's EQUITY LANES: long-only ETF programs (stocks in a later
release) that the House runs once a session after the close, each order executing at the next session's open or close.
You see your own family's Train runs (2016-2024) and nothing else: no Validation figure, no holdout figure and no other
program's outcome. Validation (2025) and ONE sealed holdout look per lineage judge every program, and nothing of them ever
reaches a program's author, so a program cannot be fitted to them: write the mechanism, not the history. The first
version that passes the Train bar in the request AND the equity review is your lineage's ONE Validation try: send the
version you would stake the lineage on. A rule that works only because you know which years fell is not a mechanism;
use scale-free state (returns, volatility, a price against its own moving average or recent high, the calendar fields),
never a price level or a date. THE LEVEL RULE refuses, before it runs, a program that holds a price, an average or range
of prices, a lot's entry or mark, a share volume, or the log of any of them, against a constant or a PARAMS value
(compared with, offset by, bucketed by or clipped at one); a ratio of two levels is fine. THE REVIEW (two other models)
refuses absolute levels, a calendar reconstructed by counting sessions in STATE, tables of dates or levels, and lookahead.

Reply with ONE JSON object: {"program": "<the whole Python file>", "note": "what this version changes and why, one or two
sentences"}; or, once a version of yours was judged by the bar (Y1, Y2, P1 or R1) and no honest revision is left,
{"stop": "why, in one or two sentences"}. PARAMS are your program's own declaration (the House runs it as written).

THE PROGRAM CONTRACT (league/equity/EQUITY.md):
"""


def _usd(x: Any) -> str:
    v = _num(x)
    return "n/a" if v is None else (f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}")


def _t(x: Any) -> str:
    v = _num(x)
    return "n/a" if v is None else f"{v:.2f}"


def version_text(n: Any, v: Mapping[str, Any]) -> str:
    """One scored version in words (Train figures and the review's reasons only)."""
    fails = list(v.get("fails") or [])
    if not v.get("years") and fails and fails[0] in ("RUN", "DQ", "LOAD", "WINDOW"):
        return f"v{n}: {v.get('why') or FAILS[fails[0]]}."
    s = v.get("summary") or {}
    side = v.get("beside") or {}
    if "REVIEW" in fails:
        status = "passed the Train bar but the EQUITY REVIEW refused it"
    else:
        status = "PASSED" if v.get("passed") else "failed " + ", ".join(fails)
    head = (f"v{n}: {status}. At 1.0x: net P&L "
            f"{_usd(v.get('pnl_10'))}, pooled daily t {_t(v.get('score'))}, closed lots "
            f"{int(_num(s.get('trades')) or 0)}, entry days {int(_num(s.get('days_traded')) or 0)}, mean exposure "
            f"{_t(s.get('exposure_mean'))}; at 1.5x: net P&L {_usd(v.get('pnl_15'))}.")
    years = "; ".join(f"{y} {'IN' if r.get('active') else 'out'} lots {r.get('trades')} entry days {r.get('days_traded')} "
                      f"P&L {_usd(r.get('pnl'))} t {_t(r.get('t'))}" for y, r in sorted((v.get("years") or {}).items()))
    beside = (f"Beside (never a bar): the same-exposure buy-and-hold {_usd(side.get('bh_pnl'))}, MTE mean "
              f"{_t(side.get('mte_mean'))} (t {_t(side.get('mte_t'))}), drift share {_t(side.get('drift_share'))}.")
    words = " ".join(f"({f}) {FAILS[f]}." for f in fails if f in FAILS and f != "REVIEW")
    review = v.get("review") if isinstance(v.get("review"), Mapping) else {}
    said = "; ".join(str(r) for r in (review.get("reasons") or [])[:3])
    told = f"(REVIEW) the {review.get('stage') or 'review'} refused it: {said or FAILS['REVIEW']}." if "REVIEW" in fails else ""
    return " ".join(x for x in (head, f"By Train year: {years}." if years else "", beside, words, told) if x)


def _named(exc: BaseException, names: Sequence[str]) -> bool:
    return any(cls.__name__ in names for cls in type(exc).__mro__)


class EquityResearcher:
    """THE RESEARCHER (the module docstring). `runner` is E1's `league.equity.runner.Isolated` (built lazily from
    `elane.isolated_runner(root)` when not handed in); `router` the swarm's `ModelRouter`."""

    def __init__(self, store: Any, router: Any, settings: Mapping[str, Any], *, runner: Any = None, root: Any = None,
                 clock: Callable[[], float] = time.time):
        self.store = store
        self.router = router
        self.settings = settings
        self._runner = runner
        self.root = root if root is not None else getattr(store, "root", None)
        self.clock = clock

    # ------------------------------------------------------------------ plumbing
    def runner(self) -> Any:
        if self._runner is None:
            from . import elane

            self._runner = elane.isolated_runner(self.root)
        return self._runner

    def due(self) -> bool:
        """The lane is on and `train_every_seconds` passed since the last round."""
        if not lane_on(self.settings):
            return False
        last = _num(self.store.get(TRAIN_AT_KEY)) or 0.0
        return self.clock() - last >= cfg(self.settings)["train_every_seconds"]

    def waiting(self, rec: Mapping[str, Any]) -> bool:
        """Whether a family waits out a backoff after a failure of the House's (`infra.next_at`)."""
        infra = rec.get("infra") if isinstance(rec.get("infra"), Mapping) else {}
        return (_num(infra.get("next_at")) or 0.0) > self.clock()

    def queue(self) -> list[dict[str, Any]]:
        """The living E2 families with a step to take (researching, or a pass to re-score under a new equity identity),
        none waiting out a backoff, the least recently worked first, at most `train_per_round`."""
        rows = []
        for fam in elane_seal.equity_families(self.store, alive=True):
            if not e2_family(fam):
                continue
            rec = record_of(fam)
            status = rec.get("status", "researching")
            if self.waiting(rec):
                continue
            if status == "researching" or (status == "passed" and not pass_current(self.store, fam)):
                rows.append((str(rec.get("last_at") or ""), str(fam.get("born_at") or ""), fam))
        rows.sort(key=lambda r: (r[0], r[1], str(r[2]["id"])))
        return [r[2] for r in rows[: cfg(self.settings)["train_per_round"]]]

    def run(self) -> dict[str, Any]:
        """One round: the upkeep of the passes, then a step for each family of the queue; one `swarm.elane` event."""
        self.store.put(TRAIN_AT_KEY, self.clock())
        if not lane_on(self.settings):
            return {"pass": "train", "skipped": "the equity lanes are off (elane.mode)"}
        closed = self.close_retired()
        kept = self.upkeep()
        steps = []
        for fam in self.queue():
            try:
                steps.append(self.step(fam))
            except Exception as exc:  # noqa: BLE001 - one family's trouble never stops the round
                steps.append({"family": fam["id"], "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
        out: dict[str, Any] = {"pass": "train", "steps": steps}
        if closed:
            out["closed"] = closed
        if kept:
            out["restored"] = kept
        self.store.event("swarm.elane", None, out)
        return out

    def close_retired(self) -> list[str]:
        """E2 families retired outside E2 while their record says they research: their record is closed ("closed"),
        so the equity request's counts stop holding them (the record alone is what the generators read)."""
        out = []
        for fam in elane_seal.equity_families(self.store, alive=False):
            if e2_family(fam) and record_of(fam).get("status", "researching") == "researching":
                _update(self.store, str(fam["id"]), lambda r: r.update(status="closed"))
                out.append(str(fam["id"]))
        return out

    def upkeep(self) -> list[str]:
        """THE PASSES KEPT IN FORCE (the module docstring, THE IDENTITY): for each living E2 family whose current pass
        stands, the review record E1's look reads and the family's `best_version` are written again when they are missing
        (E1's equity adoption clears both). No model is asked and nothing is run."""
        from .gate import run_sha

        out = []
        for fam in elane_seal.equity_families(self.store, alive=True):
            if not e2_family(fam) or record_of(fam).get("status") != "passed" or not pass_current(self.store, fam):
                continue
            fid, n = str(fam["id"]), passed_version(fam)
            rec = record_of(fam)
            version = self.store.version(fid, n)
            kept = rec.get("passed_review") if isinstance(rec.get("passed_review"), Mapping) else None
            if version is None or kept is None:
                continue
            changed = False
            sha = run_sha(version)
            if kept.get("sha") == sha and not elane_review.holds(fam.get("state"), sha):
                self.store.set_state(fid, **{elane_review.STATE_REVIEW: dict(kept)})
                changed = True
            if fam.get("best_version") != n:
                score = (versions_of(rec).get(str(n)) or {}).get("score")
                self.store.update_family(fid, best_version=n, best_train=score)
                changed = True
            if changed:
                out.append(fid)
        return out

    # ------------------------------------------------------------------ one family's step
    def step(self, fam: Mapping[str, Any]) -> dict[str, Any]:
        """One step of a family (the module docstring): re-score a stale pass; review a bar pass; score its newest
        unscored version; else, with budget left, ask for a program (its first, or a revision); else retire it."""
        c = cfg(self.settings)
        fid = str(fam["id"])
        rec = record_of(fam)
        if rec.get("status") == "passed":
            n = passed_version(fam)
            version = self.store.version(fid, n) if n is not None else None
            if version is None:
                return {"family": fid, "skipped": "its passing version cannot be read"}
            return self.score(fam, version, rescore=True)
        pending = rec.get("review") if isinstance(rec.get("review"), Mapping) else None
        if pending is not None and pending.get("version") is not None:
            return self.review_step(fam, int(pending["version"]))
        latest = self.store.latest_version(fid)
        versions = versions_of(rec)
        if latest is not None and str(latest["n"]) not in versions:
            return self.score(fam, latest)
        if len(versions) >= c["train_budget"] or int(rec.get("attempts") or 0) >= c["train_max_attempts"]:
            return self.finish(fam, "its Train budget is spent with no version passing")
        if elane_yield.room(self.store, self.settings, self.clock()) <= 0:
            return {"family": fid, "skipped": "E2's model dollars for the day are spent (elane.e2.usd_day)"}
        return self.write(fam)

    def brief(self, fam: Mapping[str, Any]) -> str:
        """The question's user turn: the family's card, its agenda prior, the bar and its own Train versions (Train
        facts and the review's reasons only: league/swarm/elane_seal.py)."""
        from . import cards, elane

        c = cfg(self.settings)
        facts = elane_seal.train_facts(fam, STATE_KEY)
        rec = facts["record"]
        lane = facts["lane"]
        agenda = AGENDA.get(facts["agenda"], AGENDA["other"])
        try:
            card = (cards.card_of(self.store, facts["id"]) or {}).get("card") or {}
        except Exception:  # noqa: BLE001 - the brief goes without the card
            card = {}
        label = elane.LABELS.get(lane, str(lane).upper())
        lines = [f"YOUR FAMILY: {facts['id']}, lane {label}"
                 + (f" ({elane.BETA_NOTE})" if lane == BETA else "") + f". Symbols: {', '.join(facts['symbols'])}; "
                 f"structure {facts['structure']}. Mechanism: {facts['mechanism']}",
                 f"ITS AGENDA MECHANISM: {agenda['title']}: {agenda['text']}. Published priors: {agenda['priors']}."]
        for name in ("hypothesis", "comparison", "falsification"):
            if card.get(name):
                lines.append(f"CARD {name.upper()}: {card[name]}")
        lines.append(bar_text())
        done = sorted(((int(k), v) for k, v in versions_of(rec).items()), key=lambda kv: kv[0])
        if done:
            lines.append("YOUR VERSIONS ON TRAIN (2016-2024):\n" + "\n".join(f"- {version_text(n, v)}" for n, v in done))
        refused = [r for r in (rec.get("refused") or []) if isinstance(r, Mapping)][-3:]
        if refused:
            lines.append("PROGRAMS REFUSED BEFORE THEY RAN:\n" + "\n".join(f"- {r.get('why')}" for r in refused))
        latest = self.store.latest_version(facts["id"])
        if latest is not None and latest.get("code"):
            lines.append(f"YOUR NEWEST PROGRAM (v{latest['n']}):\n```python\n{str(latest['code'])[:12000]}\n```")
        left = c["train_budget"] - len(done)
        lines.append(f"TRAIN BUDGET: {left} of {c['train_budget']} scored versions left"
                     + ("" if judged(rec) else "; none judged by the bar yet, so a stop is not accepted") + ". Write version "
                     f"{(latest['n'] + 1) if latest is not None else 1}: the whole file.")
        return "\n\n".join(lines)

    def write(self, fam: Mapping[str, Any]) -> dict[str, Any]:
        """Ask the family's birth route for its next program; store it as a version once it passes the static checks
        (a refusal is recorded and counts as an attempt)."""
        c = cfg(self.settings)
        fid = str(fam["id"])
        facts = elane_seal.train_facts(fam, STATE_KEY)
        first = elane_yield.Route.of(facts["route"]) if facts["route"] else None
        answer, route, errors = elane_yield.ask(
            self.router, self.store, self.settings, first=first, role=elane_yield.ROLE,
            system=RESEARCHER_SYSTEM + contract_text(), user=self.brief(fam), key=f"swarm:elane:train:{fid}:{int(self.clock())}",
            max_output=c["train_max_output_tokens"], effort=c["train_effort"], purpose="research", now=self.clock(), family=fid)
        if answer is None:
            return {"family": fid, "error": "no route answered", "errors": errors[:3]}
        # An answered question is one attempt (`train_max_attempts`); a route that could not answer spends none.
        _update(self.store, fid, lambda r: r.update(attempts=int(r.get("attempts") or 0) + 1))
        code, note, stop = program_of(answer)
        if stop is not None:
            if not judged(record_of(self.store.family(fid) or fam)):
                # A stop before the bar judged anything refutes nothing: the mechanism was never tested (B8).
                why = (f"a stop is accepted only once a version was judged by the bar (Y1, Y2, P1 or R1); none was: "
                       f"{stop}")[:400]

                def unheard(r: dict[str, Any]) -> None:
                    r["refused"] = [*(r.get("refused") or []), {"at": self.store.now(), "why": why}][-5:]
                _update(self.store, fid, unheard)
                return {"family": fid, "refused": why, "route": route.key if route else None}
            self.store.note(fid, f"The equity researcher stopped: {stop}")
            return self.finish(self.store.family(fid) or fam, f"its researcher found the mechanism refuted on Train: {stop}")
        why = check_code(code, facts["symbols"]) if code else "the answer held no program"
        if why is not None:
            def refuse(r: dict[str, Any]) -> None:
                r["refused"] = [*(r.get("refused") or []), {"at": self.store.now(), "why": why}][-5:]
            _update(self.store, fid, refuse)
            return {"family": fid, "refused": why, "route": route.key if route else None}
        known = versions_of(record_of(self.store.family(fid) or fam))
        version = self.store.add_version(fid, str(code), {}, author=f"elane:{route.key if route else 'model'}",
                                         note=note or "the equity researcher's version")
        if str(version["n"]) in known:
            # The store keeps one version a program: the same file again is no new version (and no new Train run).
            why = f"the same program as v{version['n']}, already scored"

            def again(r: dict[str, Any]) -> None:
                r["refused"] = [*(r.get("refused") or []), {"at": self.store.now(), "why": why}][-5:]
            _update(self.store, fid, again)
            return {"family": fid, "refused": why, "route": route.key if route else None}
        out = {"family": fid, "version": version["n"], "route": route.key if route else None}
        latest = self.store.family(fid) or fam
        out["score"] = self.score(latest, version)
        return out

    # ------------------------------------------------------------------ the Train run
    def house_failure(self, fam: Mapping[str, Any], n: int, why: str, *, kind: str) -> dict[str, Any] | None:
        """A failure of the House's (the module docstring, WHAT A VERDICT IS): nothing scored, no budget, no model call; a
        backoff. For a child's run failure ("run") repeated `train_max_errors` times while other programs' Train runs
        completed since its first, None: the caller judges the program RUN."""
        c = cfg(self.settings)
        fid = str(fam["id"])
        now = self.clock()
        held = record_of(self.store.family(fid) or fam).get("infra")
        held = dict(held) if isinstance(held, Mapping) and held.get("version") == n else {}
        count = int(held.get("count") or 0) + 1
        first = _num(held.get("first_at")) or now
        if kind == "run" and count >= c["train_max_errors"] and (_num(self.store.get(TRAIN_OK_KEY)) or 0.0) > first:
            return None
        delay = min(float(c["train_every_seconds"]) * (2 ** min(count - 1, 12)), BACKOFF_MAX)
        record = {"version": n, "count": count, "first_at": first, "next_at": now + delay, "kind": kind, "why": why[:240]}
        _update(self.store, fid, lambda r: r.update(infra=record))
        if kind == "window":
            self.store.event("swarm.status", fid, {"action": "elane_train_window", "alert": True, "version": n,
                                                   "text": "an equity Train result carried a day outside 2016-2024: "
                                                           "refused whole; E2 judges nothing on it (check the runner)"})
        return {"family": fid, "version": n, "house": kind, "why": why[:200], "retry_in": delay}

    def score(self, fam: Mapping[str, Any], version: Mapping[str, Any], *, rescore: bool = False) -> dict[str, Any]:
        """Run a version over Train at 1.0x and 1.5x (E1's isolated runner) and judge it (the module docstring, WHAT A
        VERDICT IS). A bar pass goes to the equity review (`review_step`); `rescore` (a pass judged under another equity
        identity): passed again it stands, else the pass is withdrawn."""
        c = cfg(self.settings)
        fid, n = str(fam["id"]), int(version["n"])
        results: list[dict[str, Any]] = []
        verdict: dict[str, Any] | None = None
        try:
            for k in (eqconfig.K_BASE, eqconfig.K_STRESS):
                run = self.runner().train(str(version.get("code") or ""), dict(version.get("params") or {}), name=fid,
                                          start=TRAIN_FIRST, end=TRAIN_LAST, k=float(k))
                results.append(dict(getattr(run, "result", run) or {}))
        except Exception as exc:  # noqa: BLE001 - a refusal is the program's; a run failure is judged below
            why = f"{type(exc).__name__}: {str(exc)[:200]}"
            if _named(exc, LOAD_REFUSALS):
                verdict = program_fault("LOAD", str(exc)[:300])
            else:
                kind = "run" if _named(exc, RUN_FAILURES) else "store"
                out = self.house_failure(fam, n, why, kind=kind)
                if out is not None:
                    return out
                verdict = program_fault("RUN", why)
        if verdict is None:
            base, stress = results[0], results[1]
            if outside_years(base) or outside_years(stress):
                return self.house_failure(fam, n, "a Train result carried a day outside 2016-2024", kind="window") or {}
            statuses = {str(base.get("status")), str(stress.get("status"))}
            if "disqualified" in statuses:
                why = str(base.get("reason") or stress.get("reason") or "its own errors or timeouts")
                verdict = program_fault("DQ", why)
            elif statuses != {"ok"}:
                return self.house_failure(fam, n, f"the Train runs ended {', '.join(sorted(statuses))}",
                                          kind="store") or {}
            else:
                verdict = train_score(base, stress)
                self.store.put(TRAIN_OK_KEY, self.clock())
                for k, result in zip((eqconfig.K_BASE, eqconfig.K_STRESS), (base, stress)):
                    try:
                        self.store.add_run(fid, n, result, window="train", stress=float(k), purpose="elane_train")
                    except Exception:  # noqa: BLE001 - the verdict stands without the stored run
                        pass
        at = self.store.now()
        ident = identity()
        if rescore:
            return self.rescored(fam, n, verdict, at=at, ident=ident)

        def put(r: dict[str, Any]) -> None:
            r.pop("infra", None)
            r["versions"] = {**(r.get("versions") or {}), str(n): compact(verdict, at=at, ident=ident)}
            if verdict["passed"] and r.get("passed_version") is None:
                r["review"] = {"version": n, "unclear": {}, "at": at}  # THE REVIEW, before the pass is the try
        rec = _update(self.store, fid, put)
        out: dict[str, Any] = {"family": fid, "version": n, "passed": bool(verdict["passed"]), "fails": verdict["fails"]}
        if verdict["passed"]:
            out["review"] = self.review_step(self.store.family(fid) or fam, n)
            return out
        if len(versions_of(rec)) >= c["train_budget"]:
            out["retired"] = self.finish(self.store.family(fid) or fam, "its Train budget is spent with no version passing")
        return out

    def rescored(self, fam: Mapping[str, Any], n: int, verdict: Mapping[str, Any], *, at: str,
                 ident: Mapping[str, Any] | None) -> dict[str, Any]:
        """THE IDENTITY (the module docstring): a stale pass judged again. Passed, its verdict is stamped with the identity
        in force (the review stands: the program is the same); failed, the pass is withdrawn (no `passed_version`, no
        `best_version`, no review record) and the family researches again with its budget."""
        fid = str(fam["id"])
        kept = bool(verdict.get("passed"))

        def put(r: dict[str, Any]) -> None:
            r.pop("infra", None)
            old = dict((r.get("versions") or {}).get(str(n)) or {})
            fresh = compact(verdict, at=at, ident=ident)
            if kept:
                fresh["passed"] = True
                fresh["rescored_from"] = old.get("identity")
            r["versions"] = {**(r.get("versions") or {}), str(n): fresh}
            if not kept:
                r["passed_version"], r["status"] = None, "researching"
                r["withdrawn"] = [*(r.get("withdrawn") or []), {"version": n, "at": at, "fails": list(verdict["fails"])}][-5:]
                r.pop("passed_review", None)
        _update(self.store, fid, put)
        if kept:
            self.store.note(fid, f"v{n} passed {OBJECTIVE} on Train again under the equity identity now in force.")
            return {"family": fid, "version": n, "rescored": "kept"}
        self.store.update_family(fid, best_version=None, best_train=None)
        self.store.set_state(fid, **{elane_review.STATE_REVIEW: None})
        self.store.note(fid, f"v{n} no longer passes {OBJECTIVE} on Train under the equity identity now in force: its pass is "
                             "withdrawn and its Train research goes on.")
        return {"family": fid, "version": n, "rescored": "withdrawn", "fails": list(verdict["fails"])}

    # ------------------------------------------------------------------ the review
    def review_step(self, fam: Mapping[str, Any], n: int) -> dict[str, Any]:
        """THE EQUITY REVIEW of a bar pass (league/swarm/elane_review.py): the level rule, then the review and the audit on
        two different models. Both pass: the version is the family's pass (its lineage's one Validation try). A failure
        (or `review_max_unclear` unclear reads of one stage) is a Train failure of the version ("REVIEW"). A question no
        route answered counts nothing and is asked again next round."""
        from .gate import run_sha

        fid = str(fam["id"])
        rec = record_of(fam)
        pending = dict(rec.get("review") or {}) if isinstance(rec.get("review"), Mapping) else {"version": n}
        version = self.store.version(fid, n)
        if version is None or not version.get("code"):
            return {"family": fid, "version": n, "error": "the version cannot be read"}
        code = str(version["code"])
        static = elane_review.level_text(code)
        if static is not None:
            return self.review_failed(fam, n, "the level rule", [static])
        if elane_yield.room(self.store, self.settings, self.clock()) <= 0:
            return {"family": fid, "version": n, "skipped": "E2's model dollars for the day are spent (elane.e2.usd_day)"}
        rc = elane_review.cfg(self.settings)
        served = elane_yield.served([elane_yield.Route.of(k) for k in rc["review_routes"]], self.router)
        from . import cards, elane

        try:
            card = (cards.card_of(self.store, fid) or {}).get("card") or {}
        except Exception:  # noqa: BLE001
            card = {}
        facts = elane_seal.train_facts(fam, STATE_KEY)
        lane_label = elane.LABELS.get(facts["lane"], str(facts["lane"]).upper())
        train = version_text(n, versions_of(rec).get(str(n)) or {})
        unclear = dict(pending.get("unclear") or {})
        for stage in ("review", "audit"):
            done = pending.get(stage)
            if isinstance(done, Mapping) and done.get("verdict") == "pass":
                continue
            reader = (pending.get("review") or {}).get("route") if stage == "audit" else None
            if stage == "audit":
                taken = elane_review.model_of(str(reader or ""))
                candidates = [r for r in served if elane_review.model_of(r.key) != taken]
            else:
                candidates = list(served)
            if not candidates:
                return {"family": fid, "version": n, "error": f"no {stage} route on a second model (elane.e2.review_routes)"}
            tries = int(unclear.get(stage) or 0)
            answer, route, errors = elane_yield.ask(
                self.router, self.store, self.settings, first=None, role=elane_yield.ROLE,
                system=elane_review.REVIEW + contract_text(),
                user=elane_review.question(fam, version, card=card, train=train, lane_label=lane_label, stage=stage),
                key=f"swarm:elane:{stage}:{fid}:{n}:{tries}", max_output=rc["review_max_output_tokens"],
                effort=rc["review_effort"], purpose="review", now=self.clock(), family=fid, candidates=candidates,
                book_as=lambda r: f"review:{r.key}")
            if answer is None or route is None:
                _update(self.store, fid, lambda r: r.update(review={**pending, "unclear": unclear}))
                return {"family": fid, "version": n, "error": f"no {stage} route answered", "errors": errors[:3]}
            read = {**elane_review.grounded(answer, code), "route": route.key}
            if read["verdict"] == "fail":
                return self.review_failed(fam, n, stage, read["reasons"] or [f"the {stage} failed it"], read=read)
            if read["verdict"] != "pass":
                unclear[stage] = tries + 1
                if unclear[stage] >= rc["review_max_unclear"]:
                    return self.review_failed(fam, n, stage, [f"the {stage} stayed unclear after {unclear[stage]} reads"]
                                              + read["reasons"][:2], read=read)
                _update(self.store, fid, lambda r: r.update(review={**pending, "unclear": unclear}))
                return {"family": fid, "version": n, stage: "unclear", "reads": unclear[stage]}
            if stage == "audit" and elane_review.model_of(route.key) == elane_review.model_of(str(reader or "")):
                # A fallback inside the router reached the reviewer's own model: no second reader; asked again next round.
                return {"family": fid, "version": n, "error": "the audit was answered by the reviewer's model"}
            pending[stage] = {k: read.get(k) for k in ("verdict", "route", "model", "reasons")}
            _update(self.store, fid, lambda r: r.update(review={**pending, "unclear": unclear}))
        sha = run_sha(version)
        at = self.store.now()
        held = elane_review.record(sha, pending["review"], pending["audit"], at=at, version=n)
        score = (versions_of(rec).get(str(n)) or {}).get("score")

        def put(r: dict[str, Any]) -> None:
            r.pop("review", None)
            if r.get("passed_version") is None:
                r["passed_version"], r["status"] = n, "passed"
                r["passed_review"] = held
        rec = _update(self.store, fid, put)
        if rec.get("passed_version") == n:
            self.store.set_state(fid, **{elane_review.STATE_REVIEW: held})
            self.store.update_family(fid, best_version=n, best_train=score)
            self.store.note(fid, f"v{n} passed {OBJECTIVE} on Train and the equity review: it is the lineage's one "
                                 "Validation try.")
        return {"family": fid, "version": n, "passed": True, "review": "pass"}

    def review_failed(self, fam: Mapping[str, Any], n: int, stage: str, reasons: Sequence[str], *,
                      read: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """The review refused version `n`: a Train failure of it ("REVIEW", its reasons in the next brief); the family's
        research goes on with its budget, or ends (`finish`) once the budget is spent. No Validation try is spent."""
        c = cfg(self.settings)
        fid = str(fam["id"])
        said = [" ".join(str(x).split())[:400] for x in reasons][:4]

        def put(r: dict[str, Any]) -> None:
            r.pop("review", None)
            v = dict((r.get("versions") or {}).get(str(n)) or {})
            v.update(passed=False, bar_passed=True, fails=["REVIEW"],
                     review={"stage": stage, "reasons": said, "route": (read or {}).get("route"),
                             "model": (read or {}).get("model")})
            r["versions"] = {**(r.get("versions") or {}), str(n): v}
        rec = _update(self.store, fid, put)
        self.store.note(fid, f"v{n} passed the Train bar but the equity {stage} refused it: {'; '.join(said)[:600]}")
        out: dict[str, Any] = {"family": fid, "version": n, "passed": False, "fails": ["REVIEW"], "stage": stage}
        if len(versions_of(rec)) >= c["train_budget"]:
            out["retired"] = self.finish(self.store.family(fid) or fam, "its Train budget is spent with no version passing")
        return out

    # ------------------------------------------------------------------ the end of the research
    def finish(self, fam: Mapping[str, Any], why: str) -> dict[str, Any]:
        """The research ends with no pass: REFUTED on Train when the bar judged a version, else STALLED."""
        return self.refute(fam, why) if judged(record_of(fam)) else self.stall(fam, why)

    def refute(self, fam: Mapping[str, Any], why: str) -> dict[str, Any]:
        """Retire a family REFUTED on Train: its record, a graveyard row in E2's own words (Train facts), the store's
        retirement."""
        fid = str(fam["id"])
        rec = record_of(fam)
        versions = versions_of(rec)
        codes = sorted({f for v in versions.values() for f in (v.get("fails") or [])})
        at = self.store.now()

        def put(r: dict[str, Any]) -> None:
            r["status"] = "refuted"
            r.pop("review", None)
            r["refuted"] = {"at": at, "codes": codes, "versions": len(versions), "why": why[:300]}
        _update(self.store, fid, put)
        facts = elane_seal.train_facts(self.store.family(fid) or fam, STATE_KEY)
        words = "; ".join(f"({c}) {FAILS[c]}" for c in codes if c in FAILS) or "no version was scored"
        title = AGENDA.get(facts["agenda"], AGENDA["other"])["title"]
        lesson = (f"{REFUTED_TAG} on Train ({OBJECTIVE}, {facts['lane']} lane, {title} on {', '.join(facts['symbols'])}): "
                  f"{why}. {len(versions)} versions scored; their fails: {words}.")
        self.store.bury(fid, lesson, {"objective": OBJECTIVE, "codes": codes, "versions": len(versions)})
        self.store.retire(fid, f"{REFUTED_TAG} on Train ({OBJECTIVE}): {why}"[:2000],
                          public_reason="refuted on Train by the equity lane's bar")
        self.store.event("swarm.elane", fid, {"pass": "refuted", "codes": codes, "versions": len(versions)})
        return {"family": fid, "refuted": codes}

    def stall(self, fam: Mapping[str, Any], why: str) -> dict[str, Any]:
        """Retire a family STALLED on Train: no version of it was judged by the bar (its programs failed to run, to load,
        or the review), so nothing is said of its mechanism: no graveyard row, no cell count, its record's `stalled`."""
        fid = str(fam["id"])
        rec = record_of(fam)
        versions = versions_of(rec)
        codes = sorted({f for v in versions.values() for f in (v.get("fails") or [])})
        at = self.store.now()

        def put(r: dict[str, Any]) -> None:
            r["status"] = "stalled"
            r.pop("review", None)
            r["stalled"] = {"at": at, "codes": codes, "versions": len(versions), "why": why[:300]}
        _update(self.store, fid, put)
        self.store.retire(fid, f"{STALLED_TAG} on Train ({OBJECTIVE}): no version could be judged by the bar; {why}"[:2000],
                          public_reason="stalled on Train: no version of its program could be judged by the equity bar")
        self.store.event("swarm.elane", fid, {"pass": "stalled", "codes": codes, "versions": len(versions)})
        return {"family": fid, "stalled": codes}


def versions_of(rec: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    versions = rec.get("versions") if isinstance(rec.get("versions"), Mapping) else {}
    return {str(k): dict(v) for k, v in versions.items() if isinstance(v, Mapping) and str(k).isdigit()}


__all__ = ["OBJECTIVE", "STATE_KEY", "TRAIN_AT_KEY", "TRAIN_OK_KEY", "TRAIN_FIRST", "TRAIN_LAST", "TRAIN_YEARS", "BAR",
           "FAILS", "JUDGED", "DEFAULTS", "AGENDA", "GROUPS", "MAP_LABEL", "cfg", "lane_on", "symbols_group", "cell_of",
           "cell_text", "outside_years", "year_rows", "train_score", "bar_text", "record_of", "e2_family", "passed_version",
           "identity", "judged", "tried", "pass_current", "may_validate", "compact", "program_fault", "train_map",
           "closed_cells", "train_map_text", "refuted_rows", "needs_literal", "check_code", "program_of", "contract_text",
           "RESEARCHER_SYSTEM", "version_text", "EquityResearcher", "versions_of", "BETA", "EQUITY", "LANES"]
