"""What a researcher sees of a run.

- TRAIN (`train_view`): a compact table of the Gym's result, trimmed to what helps a revision: the
  summary (trades, P&L per dollar of maximum loss, its t, Sharpe, drawdown, fees, quarters positive),
  the fills (rate, slippage, rejects and why), the breakdowns (weekday, time of day, DTE, realized and
  implied vol tercile, quarter, type, root, exit reason) as rows of [n, pnl, win rate, pnl per $ of max
  loss], the five worst trades with their context, and the program's errors. Train is the window the
  agents see in full; `read_run` pages through the rest (`section`). And THE DRIFT LINES (`drift_view`, Sept 27):
  per Train year and over Train, "drift-adjusted alpha $X (t Y), drift $Z", so a researcher learns that what its exposure
  earns at the roots' average return over the hours it held is drift, not an edge, and the screen's verdict.
- VALIDATION (`validation_view`): pass or fail, and how many of the line's checks passed (the owner's
  decision D2a, Sept 26: "Researchers see Validation only as pass or fail and a count of checks
  passed"). Never a number the run measured, nor which checks failed: a researcher that saw Validation's
  mean, t and failed checks tuned against it, and Validation became a second training set. Lessons
  written before D2 carried a validation view with numbers; `scrub` takes it out of any text a model
  reads (the graveyard, the lessons a family is born with).
- HOLDOUT: pass or fail, from the gate; never here.

Standard library only.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Mapping

from . import evidence

SUMMARY_KEYS = ("trades", "days", "days_traded", "pnl", "pnl_per_max_loss", "mean_return_on_max_loss_daily", "t_daily",
                "sharpe_daily", "mean_return_on_max_loss", "t_stat", "win_rate",
                "profit_factor", "sharpe", "max_drawdown", "max_drawdown_frac", "fees", "quarters_positive", "avg_trade",
                "turnover", "max_loss_opened")
FILL_KEYS = ("orders", "opens", "closes", "filled", "partial_fills", "partial", "cancelled", "expired", "rejected", "liquidated", "settled",
             "exercised", "fill_rate", "at_natural", "open_slip_half_spreads", "close_slip_half_spreads")
BREAKDOWNS = ("weekday", "time_of_day", "dte", "rv_tercile", "iv_tercile", "quarter", "type", "root", "exit_reason")
TRADE_KEYS = ("day", "root", "type", "legs", "entry_minute", "filled_minute", "exit_minute", "sessions_held", "exit_reason", "qty",
              "entry", "exit", "pnl", "max_loss", "fees", "return_on_max_loss", "tag", "note", "context")
MAX_CHARS = 9000


def _r(value: Any, places: int = 4) -> Any:
    if isinstance(value, float):
        return round(value, places) if math.isfinite(value) else None
    return value


def _rows(table: Mapping[str, Any] | None) -> dict[str, list]:
    out = {}
    for key, row in (table or {}).items():
        if isinstance(row, Mapping):
            out[str(key)] = [row.get("n"), _r(row.get("pnl"), 2), _r(row.get("win_rate"), 3), _r(row.get("pnl_per_max_loss"), 4)]
    return out


def _trade(t: Mapping[str, Any]) -> dict[str, Any]:
    out = {k: _r(t.get(k)) for k in TRADE_KEYS if t.get(k) is not None and k not in ("legs", "context")}
    if isinstance(t.get("legs"), list):
        out["legs"] = [f"{l.get('side')} {l.get('ratio', 1)}x {l.get('right')} dte{l.get('dte')} k{l.get('strike')}"
                       for l in t["legs"] if isinstance(l, Mapping)][:4]
    ctx = t.get("context")
    if isinstance(ctx, Mapping):
        out["context"] = {k: _r(v) for k, v in list(ctx.items())[:12] if not isinstance(v, (list, dict))}
    return out


#: What the drift lines mean, once a view (the figures are Train's; nothing another window measured).
DRIFT_NOTE = ("P&L = drift + alpha. Beta: your exposure per 1% move of the roots you held, over the hours you held them. "
              "Drift: what that exposure earns at the roots' average return over those hours; a placebo holding it on random "
              "days earns it too. Alpha: the rest, after costs. Only alpha is an edge.")


def _usd(value: Any) -> str:
    x = evidence._num(value)
    return "n/a" if x is None else f"{'-' if x < 0 else ''}${abs(x):,.0f}"


def _tval(value: Any) -> str:
    x = evidence._num(value)
    return "n/a" if x is None else f"{x:.2f}"


def drift_view(block: Any, *, screen: tuple[float, int | None] | None = None, first_year: int | None = None) -> dict[str, Any] | None:
    """THE DRIFT LINES of a Train result's `drift` block (or its compact figures): per year and over Train, "drift-adjusted
    alpha $X (t Y), drift $Z, beta $B per 1% move, held H of D days", the note (`DRIFT_NOTE`), and with `screen` (min t,
    years positive: the researcher's `drift_settings`) the screen's verdict over the years it counts from `first_year` (the
    run's Train span's, `evidence.drift_years`). None when the run predates the figures."""
    numbers = evidence.drift_numbers(block)
    if numbers is None:
        return None

    def line(row: Mapping[str, Any]) -> str:
        beta = evidence._num(row.get("beta"))
        held = f", held {row.get('held_days')} of {row.get('days')} days" if row.get("held_days") is not None else ""
        return (f"drift-adjusted alpha {_usd(row.get('alpha_usd'))} (t {_tval(row.get('t'))}), drift {_usd(row.get('drift_usd'))}, "
                f"beta {_usd(None if beta is None else beta / 100.0)} per 1% move{held}")

    out: dict[str, Any] = {year: line(row) for year, row in numbers["years"].items()}
    out["train"] = line(numbers["pooled"])
    if screen is not None:
        verdict = evidence.drift_screen(numbers, min_t=screen[0], years_positive=screen[1], first_year=first_year)
        out["screen"] = (f"passes (Validation needs t >= {screen[0]:g} over Train and alpha positive in {verdict['need']} of "
                         f"{verdict['years']} years)" if verdict["passed"] else f"fails: {verdict['why']}")
    out["note"] = DRIFT_NOTE
    return out


def train_view(result: Mapping[str, Any], *, lineage_trials: int | None = None,
               screen: tuple[float, int | None] | None = None) -> dict[str, Any]:
    """The compact diagnostic of a train run (see the module docstring); `screen` adds the drift screen's verdict."""
    if result.get("status") == "refused":
        return {"run_id": result.get("run_id"), "status": "refused", "reason": str(result.get("reason") or "")[:600],
                "hint": "the program was refused before it ran: fix the rule named (league/CONTRACT.md) and run again"}
    s = result.get("summary") or {}
    f = result.get("fills") or {}
    rt = result.get("runtime") or {}
    view: dict[str, Any] = {
        "run_id": result.get("run_id"), "status": result.get("status"), "window": result.get("window"),
        "roots": result.get("roots"), "stress": result.get("stress"), "params": result.get("params"),
        "summary": {k: _r(s.get(k)) for k in SUMMARY_KEYS if k in s},
        "fills": {k: _r(f.get(k)) for k in FILL_KEYS if k in f},
        "rejects": dict(sorted((f.get("reject_reasons") or {}).items(), key=lambda kv: -kv[1])[:6]),
        "by": {name: _rows((result.get("breakdown") or {}).get(name)) for name in BREAKDOWNS
               if (result.get("breakdown") or {}).get(name)},
        "by_columns": ["n", "pnl", "win_rate", "pnl_per_max_loss"],
        "worst": [_trade(t) for t in (result.get("worst") or [])[:5]],
        "runtime": {"calls": rt.get("calls"), "errors": rt.get("errors"), "timeouts": rt.get("timeouts"),
                    "disqualified": rt.get("disqualified"), "messages": list(rt.get("messages") or [])[:4]},
    }
    if lineage_trials is not None:
        view["lineage_trials"] = int(lineage_trials)
    text = json.dumps(view, default=str)
    if len(text) > MAX_CHARS:  # the long tables go first; read_run has them
        for name in ("rv_tercile", "iv_tercile", "quarter", "weekday"):
            view["by"].pop(name, None)
            if len(json.dumps(view, default=str)) <= MAX_CHARS:
                break
    drift = drift_view(result.get("drift"), screen=screen, first_year=int(str(result.get("train_from") or "2022-01-03")[:4]))
    if drift is not None:  # outside the cap: a few hundred characters that never cost the researcher a table
        view["drift"] = drift
    return view


def section(result: Mapping[str, Any], name: str, *, page: int = 0, per_page: int = 25) -> dict[str, Any]:
    """One section of a past train run for `read_run`: summary, fills, runtime, worst, trades (paged), daily,
    drift, or breakdown.<name>."""
    name = str(name or "summary")
    if name == "trades":
        trades = result.get("trades") or []
        start = max(0, int(page)) * per_page
        return {"trades": [_trade(t) for t in trades[start:start + per_page]], "page": int(page), "per_page": per_page,
                "total": len(trades)}
    if name.startswith("breakdown"):
        key = name.split(".", 1)[1] if "." in name else ""
        table = (result.get("breakdown") or {}).get(key)
        if table is None:
            return {"error": f"breakdown sections: {', '.join('breakdown.' + b for b in BREAKDOWNS)}"}
        return {name: _rows(table), "columns": ["n", "pnl", "win_rate", "pnl_per_max_loss"]}
    if name in ("summary", "fills", "runtime"):
        return {name: result.get(name)}
    if name == "worst":
        return {"worst": [_trade(t) for t in (result.get("worst") or [])]}
    if name == "daily":
        return {"daily": [[d[0], _r(d[1], 2)] for d in (result.get("daily") or [])][-120:]}
    if name == "drift":
        drift = drift_view(result.get("drift"))
        return {"drift": drift} if drift is not None else {"error": "this run predates the drift figures: run it again"}
    return {"error": "sections: summary, fills, runtime, worst, trades (with page), daily, drift, breakdown.<weekday|time_of_day|"
                     "dte|rv_tercile|iv_tercile|quarter|type|root|exit_reason>"}


def validation_view(result: Mapping[str, Any], line: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """What a researcher may know of a validation run (D2a): the line met or not and the number of its checks that
    passed. `result` is not read: nothing it measured reaches a researcher."""
    passed, of = evidence.checks_passed(line)
    return {"line_met": bool((line or {}).get("passed")), "checks_passed": passed, "checks": of}


def validation_words(line: Mapping[str, Any] | None) -> str:
    """The validation verdict in words for a prompt: "met the line" or "did not meet the line", with the count (D2a)."""
    view = validation_view({}, line)
    verdict = "met the validation line" if view["line_met"] else "did not meet the validation line"
    return f"{verdict} ({view['checks_passed']} of {view['checks']} checks passed)"


#: A validation view as lessons before D2 wrote it (`best validation {...}`: its mean, t and failed checks), also when
#: a length cut took its closing brace.
_OLD_VIEW = re.compile(r"best validation (?:\{[^{}]*\}?|null|None)")


#: A figure after "validation" or "deflated" and the statistic's words ("validation t 1.9", "(deflated Sharpe probability
#: 0.012)", "validation mean: 0.01"), or after "t =": what old fork notes, retirement reasons and notes carried.
_FIGURE = re.compile(r"\b((?:validation|deflated)(?:[ \t]+(?:t|mean|sharpe|probability|dsr|return|returns|pnl|p&l|trades|days|"
                     r"quarters|daily|traded|on|of|the|per|was|is|at))*)[ \t]*[:=]?[ \t]*(?!(?:19|20)\d\d\b)-?\d+(?:\.\d+)?(?:/\d+)?",
                     re.I)  # a year ("Validation 2025") is the window's name, not a figure
_T_IS = re.compile(r"\bt[ \t]*=[ \t]*-?\d+(?:\.\d+)?")


def scrub(text: Any) -> str:
    """Text a model reads (graveyard lessons, notes) with Validation's figures taken out (D2a): a pre-D2 validation view
    (its numbers and failed checks), a figure after "validation" or "deflated" (old fork notes' "validation t", old
    retirement reasons' deflated Sharpe probability), and any "t =" figure."""

    def verdict(match: re.Match) -> str:
        try:
            view = json.loads(match.group(0)[len("best validation "):])
        except ValueError:
            view = None
        if isinstance(view, dict) and "line_met" in view:
            return "best validation: " + ("line met" if view.get("line_met") else "line not met")
        return "best validation: not recorded"

    out = _OLD_VIEW.sub(verdict, str(text or ""))
    out = _FIGURE.sub(lambda m: f"{m.group(1)} (withheld)", out)
    return _T_IS.sub("t = (withheld)", out)


__all__ = ["train_view", "drift_view", "section", "validation_view", "validation_words", "scrub", "DRIFT_NOTE"]
