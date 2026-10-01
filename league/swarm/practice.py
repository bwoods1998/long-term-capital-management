"""The practice league's feedback to research (Sept 29, 2026): a RESEARCH signal, never evidence.

WHAT PRACTICE IS. Every alive Gym-band family with a validated version, or an eligible Train version, trades the House's
shadow book on live quotes as a practice instance (`league/live/step.py`, the observe band), under the Gym's own fill
rules, on a $10,000 practice account; never a real order, never a forward row. Its trades and its minute-by-minute record
are the House's private `<state>/observe.sqlite` (`league/live/observe.py`). Live quotes from Sept 29, 2026 on are the one
period no model behind the architect, the strategist or the researchers has seen. THE INCUBATOR (release B, Oct 1, 2026;
`league/live/incubator.py`) is the one other reader of that record: it reads a cohort's record as a pre-registered sign
test of positive live practice, for one lot of real money within the owner's caps. That is money, and never a
promotion, a band, a forward row or evidence; nothing here, and no weight, feeds it.

WHAT THIS MODULE GIVES RESEARCH (`observe.practice_summary`, read-only, cached `CACHE_SECONDS` a process):

- `table(store, settings)`: the strategist's PRACTICE part: by mechanism class (structure x root group) and by family,
  sessions, program-closed trades, the SIGN of their realized P&L and a t (the daily t from 2 days of closes, else the
  per-trade t; null below 3 trades). Never dollars, dates, versions, code, parameters or Validation numbers.
- `class_lines(store, settings)`: the architect's PRACTICE BY CLASS lines (at most `MAX_CLASSES`).
- `apply_bonus(shares, store, settings)`: THE BANDIT'S BONUS. For each family with a positive practice record (at least
  `practice.min_trades` program-closed trades, positive P&L and a positive per-trade t) over the window:
  `b = bonus x clip(t / 2, 0, 1) x min(1, days / 3)` (days: session days with a program close), so one day at t >= 2
  gives a third of `bonus` and three days the whole of it. If the added share `M = sum(w x b)` passes
  `practice.bonus_total`, every `b` is scaled by `bonus_total / M`. Then `w' = w x (1 + b)`, normalized. So a family
  gains at most `bonus` (25%) of its share, and all others together give up at most `bonus_total / (1 + bonus_total)`
  (about 9%). Forced (wind-down) closes never count.

WHY IT CANNOT PROMOTE ANYTHING TO REAL MONEY. The bonus changes `families.weight` only, and the weight is read only for
the researchers' turn order (`loop.py`), Gym Train-job priority (`researcher.py`; validation jobs have a fixed priority),
the order retirements are considered in (`tournament.py`), the Claude top band (`researcher.is_top`) and the leaderboard
share. It is never read by the tournament's choice of the version to validate (Train score), the validation line, the
drift screen, the gate, the holdout, `bands.read` or `bands.observe`, the live path, the money table, tuition, Profit or
the grant. Promotion to real money stays D2 exactly: Validation plus the holdout, then the money table (and the forward
embargo on Sized, `OptionsLive._move_band`). A test holds each of these (`league/tests/test_swarm_practice.py`).
THE COHORT KEEP (L1, release B, Sept 30) is research attention only, too: `cohort_status` reads the House's active practice
cohorts and their records before today, and the tournament spares at most `tournament.incubator_keep_max` (12) Gym
families with an active cohort (whatever its record before the incubator's sample, and a record that is not negative
once it meets it) from its revision, evaluation and idle retirement rules until the cohort's window ends
(`Tournament.incubator_keep`); what it keeps is saved (`KEEP_KV`) so that a kept family's researcher is not urged to
retire it for being idle (`kept_version`). It never spares a family from the deflated-Sharpe rule, its researcher's or
the diagnostician's own retire, the population floor or the operator's gate hold, and no trial count, look, validation,
gate, band or money rule reads it (`league/tests/test_swarm_incubator_keep.py`).

`practice.feedback` false (swarm.json, no deploy) turns all three off (not the keep: `tournament.incubator_keep_max` 0
does). Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

CACHE_SECONDS = 300.0
MAX_FAMILIES = 40
MAX_CLASSES = 12
BONUS_CEILING = 0.5
TOTAL_CEILING = 0.2
DEFAULTS = {"feedback": True, "sessions": 10, "bonus": 0.25, "bonus_total": 0.10, "min_trades": 3}

HEADER = ("PRACTICE (shadow trades on the live market under the Gym's own fill rules, the last {n} sessions: a research "
          "signal, never evidence; a handful of trades is noise; refer to it as \"practice\"):")
ARCHITECT_HEADER = ("PRACTICE BY CLASS (shadow trades on the live market under the Gym's fill rules, the last {n} sessions; "
                    "a research signal, never evidence; a handful of trades is noise):")

_cache: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`practice` in the swarm's settings, each value inside its bounds (a malformed one is its default; a number past a
    bound is the bound: the bonus never passes its code ceiling)."""
    raw = (settings or {}).get("practice")
    raw = raw if isinstance(raw, Mapping) else {}

    def number(key: str, low: float, high: float) -> float:
        value = raw.get(key, DEFAULTS[key])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            value = DEFAULTS[key]
        return float(min(high, max(low, value)))

    return {"feedback": raw.get("feedback", DEFAULTS["feedback"]) is True,
            "sessions": int(number("sessions", 1, 60)), "bonus": number("bonus", 0.0, BONUS_CEILING),
            "bonus_total": number("bonus_total", 0.0, TOTAL_CEILING), "min_trades": int(number("min_trades", 1, 50))}


def summary(root: str | Path | None, sessions: int, *, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """`observe.practice_summary(root, sessions=)`, cached `CACHE_SECONDS` a process ({} without a root or a record)."""
    if root is None:
        return {}
    key = (str(root), int(sessions))
    now = clock()
    with _lock:
        hit = _cache.get(key)
    if hit is not None and 0.0 <= now - hit[0] < CACHE_SECONDS:
        return hit[1]
    from ..live.observe import practice_summary

    value = practice_summary(root, sessions=int(sessions))
    with _lock:
        _cache[key] = (now, value)
    return value


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _rows(store: Any, settings: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(the settings, the summary's rows) when feedback is on, else (the settings, [])."""
    c = cfg(settings)
    if not c["feedback"]:
        return c, []
    try:
        return c, list(summary(getattr(store, "root", None), c["sessions"]).get("rows") or [])
    except Exception:  # noqa: BLE001 - research goes on without it
        return c, []


def _sign(value: float) -> str:
    return "+" if value > 0 else "-" if value < 0 else "0"


def _t(program: Mapping[str, Any]) -> float | None:
    """The t research is shown: the daily t from 2 days of closes, else the per-trade t; null below 3 trades."""
    if int(program.get("trades") or 0) < 3:
        return None
    t = program.get("t_daily") if int(program.get("days") or 0) >= 2 else None
    t = program.get("t_trade") if t is None else t
    return round(float(t), 1) if isinstance(t, (int, float)) and math.isfinite(t) else None


def _t_of(values: list[float], minimum: int) -> float | None:
    from ..live.observe import t_stat

    return t_stat(values, minimum)


def _class_of(row: Mapping[str, Any], fam: Mapping[str, Any] | None) -> str:
    from .strategist import mechanism_class

    structure = row.get("structure") or (fam or {}).get("structure")
    roots = row.get("roots") or (fam or {}).get("roots") or []
    return mechanism_class(structure, roots)


def _status(fam: Mapping[str, Any] | None) -> str:
    if fam is None:
        return "retired"
    if not fam.get("retired_at"):
        return "alive"
    from .architect import tag_of

    return f"retired {tag_of({'family': fam['id'], 'lesson': ''}, fam)}"


def _classes(rows: list[dict[str, Any]], fams: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """By mechanism class: families, session days with a program close, program-closed trades, the sign of their P&L and
    a t (the class's daily t from 2 days, else its per-trade t; null below 3 trades)."""
    classes: dict[str, dict[str, Any]] = {}
    for row in rows:
        program = row.get("program") or {}
        c = classes.setdefault(_class_of(row, fams.get(row["family"])),
                               {"families": set(), "days": {}, "returns": [], "trades": 0, "pnl": 0.0})
        c["families"].add(row["family"])
        c["trades"] += int(program.get("trades") or 0)
        c["pnl"] += float(program.get("pnl_usd") or 0.0)
        c["returns"] += [float(x) for x in program.get("returns") or []]
        for day, ret, _ in program.get("daily") or []:
            c["days"][day] = c["days"].get(day, 0.0) + float(ret)
    out = []
    for name, c in classes.items():
        t = None
        if c["trades"] >= 3:
            t = _t_of([v for _, v in sorted(c["days"].items())], 2) if len(c["days"]) >= 2 else None
            t = _t_of(c["returns"], 3) if t is None else t
        out.append({"class": name, "families": len(c["families"]), "sessions": len(c["days"]), "trades": c["trades"],
                    "sign": _sign(c["pnl"]), "t": None if t is None else round(t, 1)})
    out.sort(key=lambda r: (-r["trades"], -r["families"], r["class"]))
    return out[:MAX_CLASSES]


def table(store: Any, settings: Mapping[str, Any]) -> dict[str, Any] | None:
    """The strategist's PRACTICE part ({"by_class": [...], "families": [...]}), or None (feedback off, or no record)."""
    c, rows = _rows(store, settings)
    if not rows:
        return None
    fams = {f["id"]: f for f in store.families()}
    per: dict[str, dict[str, Any]] = {}
    for row in rows:                                       # a family's versions together (research sees no version)
        program = row.get("program") or {}
        p = per.setdefault(row["family"], {"row": row, "trades": 0, "pnl": 0.0, "returns": [], "days": {}, "sessions": 0,
                                           "tier": "train"})
        p["trades"] += int(program.get("trades") or 0)
        p["pnl"] += float(program.get("pnl_usd") or 0.0)
        p["returns"] += [float(x) for x in program.get("returns") or []]
        for day, ret, _ in program.get("daily") or []:
            p["days"][day] = p["days"].get(day, 0.0) + float(ret)
        p["sessions"] = max(p["sessions"], int(row.get("sessions") or 0))
        p["tier"] = "validated" if "validated" in (p["tier"], row.get("tier")) else "train"
    families = []
    for fid, p in per.items():
        fam = fams.get(fid)
        t = _t({"trades": p["trades"], "days": len(p["days"]),
                "t_daily": _t_of([v for _, v in sorted(p["days"].items())], 2), "t_trade": _t_of(p["returns"], 3)})
        families.append({"family": fid, "class": _class_of(p["row"], fam), "tier": p["tier"], "status": _status(fam),
                         "sessions": p["sessions"], "trades": p["trades"], "sign": _sign(p["pnl"]), "t": t})
    families.sort(key=lambda r: (-r["trades"], r["family"]))
    return {"by_class": _classes(rows, fams), "families": families[:MAX_FAMILIES]}


def header(settings: Mapping[str, Any], *, architect: bool = False) -> str:
    return (ARCHITECT_HEADER if architect else HEADER).format(n=cfg(settings)["sessions"])


def class_lines(store: Any, settings: Mapping[str, Any]) -> list[str]:
    """The architect's PRACTICE BY CLASS lines: "long_put x etf: 5 families, 14 trades on 3 sessions, net +, t 0.9"; []
    when feedback is off or there is no record."""
    _, rows = _rows(store, settings)
    if not rows:
        return []
    fams = {f["id"]: f for f in store.families()}
    out = []
    for c in _classes(rows, fams):
        fam_word = "family" if c["families"] == 1 else "families"
        out.append(f"{c['class']}: {c['families']} {fam_word}, {c['trades']} trades on {c['sessions']} sessions, "
                   f"net {c['sign']}, t {'n/a' if c['t'] is None else c['t']}")
    return out


def family_records(store: Any, settings: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """{family: {trades, days, pnl, t}} over the window, all its versions, program-closed trades only (the bandit's)."""
    _, rows = _rows(store, settings)
    per: dict[str, dict[str, Any]] = {}
    for row in rows:
        program = row.get("program") or {}
        p = per.setdefault(str(row["family"]), {"trades": 0, "days": set(), "pnl": 0.0, "returns": []})
        p["trades"] += int(program.get("trades") or 0)
        p["pnl"] += float(program.get("pnl_usd") or 0.0)
        p["returns"] += [float(x) for x in program.get("returns") or []]
        p["days"] |= {str(d) for d, _, _ in program.get("daily") or []}
    return {fid: {"trades": p["trades"], "days": len(p["days"]), "pnl": p["pnl"], "t": _t_of(p["returns"], 3)}
            for fid, p in per.items()}


def family_feedback(store: Any, settings: Mapping[str, Any], family: str) -> dict[str, Any] | None:
    """Actionable researcher context after ten program closes across three distinct sessions. It remains training
    feedback, never promotion evidence. A scheduler can watch `revision` without waking on every quote or minute:
    the token changes only on a new close day or another five closed trades. No dates, prices or versions are exposed."""
    _, rows = _rows(store, settings)
    rows = [r for r in rows if r.get("family") == family]
    trades, pnl, days, returns, due, made, forced = 0, 0.0, {}, [], 0, 0, 0
    for row in rows:
        p = row.get("program") or {}
        trades += int(p.get("trades") or 0)
        pnl += float(p.get("pnl_usd") or 0)
        returns.extend(float(x) for x in p.get("returns") or [])
        for day, ret, _ in p.get("daily") or []:
            days[day] = days.get(day, 0.0) + float(ret)
        due += int(row.get("decisions_due") or 0)
        made += int(row.get("decisions_made") or 0)
        forced += int(row.get("forced") or 0)
    if trades < 10 or len(days) < 3:
        return None
    token = hashlib.sha256(f"{family}:{trades // 5}:{max(days)}".encode()).hexdigest()[:16]
    return {"revision": token, "trades": trades, "sessions": len(days), "sign": _sign(pnl),
            "t": _t({"trades": trades, "days": len(days), "t_daily": _t_of(list(days.values()), 2),
                     "t_trade": _t_of(returns, 3)}),
            "coverage": round(made / due, 4) if due else None, "forced_closes_excluded": forced,
            "use": "Practice research feedback only. Any resulting revision requires subsequent untouched evaluation."}


def feedback_revision(store: Any, settings: Mapping[str, Any], family: str) -> str | None:
    record = family_feedback(store, settings, family)
    return record["revision"] if record else None


def bonuses(shares: Mapping[str, float], records: Mapping[str, Mapping[str, Any]], c: Mapping[str, Any]) -> dict[str, float]:
    """Each family's relative bonus `b` (the module docstring), scaled so the added share is at most `bonus_total`. Pure."""
    top, total, need = float(c["bonus"]), float(c["bonus_total"]), int(c["min_trades"])
    if top <= 0 or total <= 0:
        return {}
    out: dict[str, float] = {}
    for fid, w in shares.items():
        rec = records.get(fid)
        if not rec or float(w) <= 0:
            continue
        n, k, pnl, t = int(rec.get("trades") or 0), int(rec.get("days") or 0), float(rec.get("pnl") or 0.0), rec.get("t")
        if n < need or not pnl > 0 or not isinstance(t, (int, float)) or not math.isfinite(t) or t <= 0:
            continue
        b = top * min(1.0, max(0.0, float(t) / 2.0)) * min(1.0, k / 3.0)
        if b > 0:
            out[fid] = b
    mass = sum(float(shares[f]) * b for f, b in out.items())
    if mass > total:
        out = {f: b * total / mass for f, b in out.items()}
    return out


def apply_bonus(shares: Mapping[str, float], store: Any, settings: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    """(the shares with the bonus, {family: b} for each family that got one). The shares unchanged when feedback is off,
    the bonus is 0, there is no record, or anything fails (the bandit never waits on practice)."""
    base = {str(k): float(v) for k, v in shares.items()}
    try:
        c = cfg(settings)
        if not c["feedback"] or not base:
            return base, {}
        b = bonuses(base, family_records(store, settings), c)
    except Exception:  # noqa: BLE001
        return base, {}
    if not b:
        return base, {}
    raised = {f: w * (1.0 + b.get(f, 0.0)) for f, w in base.items()}
    norm = sum(raised.values())
    total = sum(base.values())
    if not norm > 0:
        return base, {}
    return {f: v * total / norm for f, v in raised.items()}, {f: round(v, 4) for f, v in b.items()}


# ------------------------------------------------------------------------------------------ the active cohorts (L1)
#: A cohort's bounded session window, as the House computes it (`ObserveStore.cohort_candidates` with its step's
#: DEFAULTS): the snapshot's `practice_max_sessions`, at least `COHORT_WINDOW` (`observe_max_sessions`), at most
#: `COHORT_WINDOW_MAX`, and never below `COHORT_WINDOW_MIN` (`observe_min_sessions`).
COHORT_WINDOW = 10
COHORT_WINDOW_MAX = 60
COHORT_WINDOW_MIN = 3
NEW_YORK = ZoneInfo("America/New_York")
#: THE COHORT KEEP's store key (L1): the tournament's last keep, {"at": epoch, "families": {family: version}, and "held":
#: [family] when any of them hold the incubator's cohorts (`tournament.incubator_held`)}, written at each read
#: (`Tournament.incubator_keep`) and read by a researcher's status (`kept_version`) so that a family the keep holds is
#: not urged to retire for being idle. A value older than `KEEP_KV_SECONDS` reads as no keep. A fresh swarm process whose
#: first practice read fails takes it as its last good keep while it is at most an hour old
#: (`tournament.KEEP_STALE_SECONDS`, `Tournament._saved_keep`: the "held" families first, never cut by the cap).
KEEP_KV = "cohort_keep"  # not the House's own `incubator_keep` (L2', in its live state)
KEEP_KV_SECONDS = 7200.0


def session_day(at: float) -> str:
    """The New York calendar date of the epoch `at` (the House's session day)."""
    return dt.datetime.fromtimestamp(float(at), NEW_YORK).date().isoformat()


def kept_version(store: Any, family: str, *, now: float) -> int | None:
    """The version THE COHORT KEEP holds `family` alive for (`KEEP_KV`, the tournament's last keep), or None: none, a
    value older than `KEEP_KV_SECONDS`, or one that cannot be read. Never raises."""
    try:
        value = store.get(KEEP_KV) or {}
        at = value.get("at")
        if isinstance(at, bool) or not isinstance(at, (int, float)) or not 0 <= float(now) - float(at) <= KEEP_KV_SECONDS:
            return None
        version = (value.get("families") or {}).get(str(family))
        return int(version) if isinstance(version, int) and not isinstance(version, bool) else None
    except Exception:  # noqa: BLE001 - a status line never fails a cycle
        return None


def cohort_status(root: str | Path | None, *, today: str | None = None) -> list[dict[str, Any]] | None:
    """THE ACTIVE PRACTICE COHORTS (`<state>/observe.sqlite`, table `cohorts`, status "active") and each one's record
    BEFORE `today` under its OWN evaluator (its snapshot's `practice_evaluator`): the basis of the incubator's first look
    and its re-checks (`observe.practice_record(before=today)`), so today's closes and today's session are left out and the
    record moves at most once a session day. Read-only (`mode=ro`, a one-second timeout), standard library only, never
    raising: [] without a root, a file or a cohorts table; None when the file cannot be read, which a caller must never
    take for "no cohort". `today` is the New York session date (default: now). A cohort whose snapshot cannot be read is
    left out. One row a cohort, the oldest admitted first:

        family, version, first_day                   the cohort (`first_day`: the session it was frozen in)
        evaluator, tier, validation_t, best_train,   from its snapshot (`tier`, `validation_t`, `best_train`: what
        structure, run_sha                           `bands.priority` orders by)
        window     its bounded session window (the House's rule, `COHORT_WINDOW`)
        elapsed    session days on the calendar from its first day to before `today`, counted up to `window` (the House
                   completes it at the first session at which `elapsed >= window`)
        sessions   its practice row's completed sessions before `today`; None when that row predates the cohort (the
                   incubator never takes a first look at such a cohort)
        unpracticed  session days on the calendar before `today` since the House last practised it (its practice row's
                   last day, else its first day), counted up to `window`: 0 while it is practised every session
        coverage   decisions made / due over its practice row; None before any was due
        closes_program, pnl_program      program closes (not forced) under its evaluator before `today`, and their P&L
        closes_all, pnl_all, max_loss_all   every close under its evaluator before `today`, forced ones included
        return_on_risk   pnl_all / max_loss_all (None without a maximum loss)

    P&L is the engine's after its fees under the House's shadow fill model, in dollars to the cent, realized only: the
    open mark is left to the incubator's own first look (it starts below zero at every open, the entry's fees and spread
    booked against it). `practice.pnl_marked` is never read: it is rebased on trades of any evaluator."""
    if root is None:
        return []
    try:
        from ..live.observe import FILE

        path = Path(root) / FILE
        if not path.exists():
            return []
        day = str(today or session_day(time.time()))
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            return _cohorts(db, day)
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - None: the caller decides what an unreadable record means
        return None


def _cohorts(db: sqlite3.Connection, today: str) -> list[dict[str, Any]]:
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "cohorts" not in tables:
        return []
    columns = {r[1] for r in db.execute("PRAGMA table_info(trades)")} if "trades" in tables else set()
    has_trades = {"evaluator", "forced", "exit_day", "pnl", "max_loss"} <= columns
    out = []
    for family, version, first, snapshot in db.execute(
            "SELECT family, version, first_day, snapshot FROM cohorts WHERE status='active' "
            "ORDER BY admitted_at, family, version").fetchall():
        try:
            snap = json.loads(snapshot)
            first_date = dt.date.fromisoformat(str(first))
            version = int(version)
        except (TypeError, ValueError):
            continue
        evaluator = snap.get("practice_evaluator") if isinstance(snap, dict) else None
        if not isinstance(evaluator, str) or not evaluator:
            continue
        horizon = snap.get("practice_max_sessions")
        horizon = int(horizon) if isinstance(horizon, int) and not isinstance(horizon, bool) else COHORT_WINDOW
        window = max(COHORT_WINDOW_MIN, min(COHORT_WINDOW_MAX, max(COHORT_WINDOW, horizon)))
        closes_all = closes = 0
        pnl_all = pnl = max_loss = 0.0
        if has_trades:
            row = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(pnl), 0), COALESCE(SUM(max_loss), 0), "
                "COALESCE(SUM(CASE WHEN COALESCE(forced, 0) = 0 THEN 1 ELSE 0 END), 0), "
                "COALESCE(SUM(CASE WHEN COALESCE(forced, 0) = 0 THEN pnl ELSE 0 END), 0) "
                "FROM trades WHERE family=? AND version=? AND evaluator=? AND exit_day IS NOT NULL AND exit_day<?",
                (family, version, evaluator, today)).fetchone()
            closes_all, pnl_all, max_loss, closes, pnl = (int(row[0]), float(row[1]), float(row[2]), int(row[3]),
                                                          float(row[4]))
        live = (db.execute("SELECT first_day, last_day, sessions, decisions_due, decisions_made FROM practice "
                           "WHERE family=? AND version=?", (family, version)).fetchone() if "practice" in tables else None)
        sessions: int | None = 0
        coverage = None
        since = first_date
        if live is not None:
            if str(live[0]) < str(first):
                sessions = None
            else:
                sessions = int(live[2]) - int(str(live[1]) == today)
                try:
                    since = max(first_date, dt.date.fromisoformat(str(live[1])) + dt.timedelta(days=1))
                except ValueError:
                    pass
            coverage = round(int(live[4]) / int(live[3]), 4) if int(live[3] or 0) > 0 else None
        out.append({"family": str(family), "version": version, "first_day": str(first), "evaluator": evaluator,
                    "tier": snap.get("tier") or "validated", "validation_t": snap.get("validation_t"),
                    "best_train": snap.get("best_train"), "structure": snap.get("structure"), "run_sha": snap.get("run_sha"),
                    "window": window, "elapsed": _sessions_between(first_date, today, window),
                    "sessions": sessions, "unpracticed": _sessions_between(since, today, window), "coverage": coverage,
                    "closes_program": closes, "pnl_program": round(pnl, 2),
                    "closes_all": closes_all, "pnl_all": round(pnl_all, 2), "max_loss_all": round(max_loss, 2),
                    "return_on_risk": round(pnl_all / max_loss, 4) if max_loss > 0 else None})
    return out


def _sessions_between(first: dt.date, today: str, limit: int) -> int:
    """Session days on the calendar from `first` to before `today`, counted up to `limit` (the House's own count: a day
    outside the calendar's years is no session)."""
    from ltcm.data import us_equity_session

    day, end, count = first, dt.date.fromisoformat(today), 0
    while day < end and count < limit:
        try:
            count += us_equity_session(day) is not None
        except ValueError:
            pass
        day += dt.timedelta(days=1)
    return count


__all__ = ["cfg", "summary", "table", "class_lines", "family_records", "bonuses", "apply_bonus", "header", "clear_cache",
           "family_feedback", "feedback_revision", "cohort_status", "session_day", "kept_version",
           "DEFAULTS", "CACHE_SECONDS", "BONUS_CEILING", "TOTAL_CEILING", "MAX_FAMILIES", "MAX_CLASSES",
           "COHORT_WINDOW", "COHORT_WINDOW_MAX", "COHORT_WINDOW_MIN", "KEEP_KV", "KEEP_KV_SECONDS"]
