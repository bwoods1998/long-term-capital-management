"""The incubator's swarm facts (release B2, Sept 30, 2026): what research records for the House's incubator route to read.

THE ROUTE. The owner approved the incubator on Sept 29, 2026, and its reading was settled on Sept 30. It is a
shadow-to-real route for families that pass Train, pass the drift screen alone and show positive live practice. It
trades one lot of an approved real structure, at most $50 maximum loss each. Its trades are never strategy evidence and
never a promotion: D2 is the only route to Probe and Sized. Every money rule of the route lives in the House
(`league/live`, the constitution's `options_money.incubator` row). The swarm records only the two facts below, in the
family's state. Each is bound to the evaluator it was made under, so no stale fact can pass.

1. THE TRAIN AND DRIFT MARK (`facts`, called by the tournament's hourly round after validation). For version `n` of an
   alive Gym-band family that holds an active practice cohort under the current evaluator, it writes
   `train_passed[str(n)] = {evaluator, objective, run, robust_pnl, drift: {t, positive, years}, at}` when ALL of these hold:
   - an eligible Train run of `n` (`train_eligible`) over the running Train span, under the current research evaluator;
   - its 1.5x Train robustness run landed with a profit (`researcher.robust_at_stress`);
   - it was not demoted (`bands.demoted`: a loss at 1.5x, or a failed drift screen);
   - THE DRIFT SCREEN knows its figures and passes them (`researcher.drift_verdict`). A screen switched off never passes.
   `evaluator` is the store's `research_evaluator` and `objective` its `train_objective`, both as the mark was made. The
   live side (`bands.incubator`) accepts a mark only while both still equal the store's, because an evaluator adoption
   clears alive families only. The mark is written with a compare-and-set on the version's `robust_failed`,
   `drift_failed` and `train_passed` as read, so a demotion landing meanwhile wins. A mark whose version later fails
   for good (a demotion, a loss at 1.5x, a known failed drift screen) is removed at the next round. The newest
   `MARKS_KEPT` marks are kept per family. No Gym run is queued here: a version whose 1.5x run never landed stays
   unmarked (fail-closed).

2. THE INCUBATOR REVIEW AND AUDIT (`due_reviews` names the versions; `gate.Gate.incubator_reviews` makes them). The owner
   kept the gate's review and audit required. A marked version of an active, current cohort is due once its practice
   so far has at least `REVIEW_MIN_SESSIONS` completed sessions, at least `REVIEW_MIN_CLOSES` program closes and a
   positive program P&L, so the review is ready by the first look. It is due only while no FINAL review of its program
   (`gate.run_sha`) exists under the current review contract: a gate review (`review`) that failed or was audited, or an
   incubator review (`incubator_reviews[sha]`) that failed or was audited. The gate records
   `incubator_reviews[sha] = {sha, version, verdict, reasons, model, route, contract_sha, audit, at}` (the newest
   `REVIEWS_KEPT`). A failed review or audit is final for that program. The gate's own review state (`review`,
   `gate_ready`, `gated_sha`, `gate_outcome`) and its holdout looks are never touched, and no look is spent.

WHY NEITHER FACT CAN PROMOTE ANYTHING. Neither is read by validation, the validation line, the gate's holdout, the
forward record, the bands' moves or `bands.read`. Only the live side's incubator reader (`bands.incubator`) reads them,
for the incubator route, whose trades are tuition (never a forward row) under its own money row. Research never reads
the House's real incubator rows; practice is read only from the House's `observe.sqlite`, read-only.

Adoption of a new evaluator clears both (`evaluator.SELECTION_KEYS`); `researcher.demote_version` removes a demoted
version's mark. Standard library only.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .bands import demoted
from .researcher import drift_verdict, robust_at_stress, row_span, running_span
from .store import SwarmStore

#: Marks and incubator reviews kept per family (the newest versions' marks; the newest reviews by time).
MARKS_KEPT = 24
REVIEWS_KEPT = 8
#: A marked version is reviewed once its practice so far has this many completed sessions and program closes and a
#: positive program P&L: ready before its first look (3 sessions and 10 closes), and paid for only when it could pass.
REVIEW_MIN_SESSIONS = 2
REVIEW_MIN_CLOSES = 5
#: Incubator reviews a gate round makes (`gate.incubator_reviews`); a value past `REVIEWS_CEILING` is the ceiling.
REVIEWS_PER_ROUND = 2
REVIEWS_CEILING = 8
#: The House's practice record (`league/live/observe.py` `FILE`), read here read-only.
OBSERVE_FILE = "observe.sqlite"
NEW_YORK = "America/New_York"


# ---------------------------------------------------------------------------------------------------- small readers
def session_day(clock: Callable[[], float] = time.time) -> str:
    """Today's session day as the House names it: the New York date."""
    from zoneinfo import ZoneInfo

    return dt.datetime.fromtimestamp(float(clock()), ZoneInfo(NEW_YORK)).date().isoformat()


def practice_current(evaluator: Any, research: Mapping[str, Any] | None) -> bool:
    """A cohort's practice evaluator is the current research evaluator. The House writes it as
    "<Gym bundle>:<fill model version>:<execution fingerprint>" (`league/live/step.py`); the bundle and the fingerprint
    must be the store's `research_evaluator`'s. The fill model is the House's alone, and a cohort under an older one is
    completed by the House itself."""
    if not isinstance(evaluator, str) or not isinstance(research, Mapping):
        return False
    bundle, execution = research.get("bundle"), research.get("execution")
    if not bundle or not execution:
        return False
    head, tail = f"{bundle}:", f":{execution}"
    return evaluator.startswith(head) and evaluator.endswith(tail) and len(evaluator) > len(head) + len(tail)


def current_mark(mark: Any, evaluator: Any, objective: Any) -> bool:
    """A Train and drift mark made under the running research evaluator and Train objective (both known)."""
    return (isinstance(mark, Mapping) and evaluator is not None and objective is not None
            and mark.get("evaluator") == evaluator and mark.get("objective") == objective)


def final_review(state: Mapping[str, Any], sha: str) -> dict[str, Any] | None:
    """The FINAL review of program `sha` under the current review contract, or None: the gate's (`review`) or the
    incubator's (`incubator_reviews`), when it failed or its audit was made. A review that passed with its audit still
    owed is not final."""
    from ..gym.review_contract import review_contract

    contract = review_contract()["sha256"]
    for record in (state.get("review"), (state.get("incubator_reviews") or {}).get(sha)):
        if isinstance(record, Mapping) and record.get("sha") == sha and record.get("contract_sha") == contract \
                and (record.get("verdict") == "fail" or "audit" in record):
            return dict(record)
    return None


#: The gate's refusals that judge the program itself (`gate.Gate.refuse` stages): final for the incubator too.
PROGRAM_REFUSALS = ("review", "audit", "experiment contract")


def program_refused(store: SwarmStore, fid: str, n: int) -> bool:
    """The gate refused version `n`'s program itself (its review, its audit or the experiment contract). The family's
    `review` keeps one version's review only, so the refusal's durable row is what keeps a failed review final."""
    return any(row.get("version") == int(n) and row.get("stage") in PROGRAM_REFUSALS for row in store.refusals(fid))


def reviews_per_round(settings: Mapping[str, Any]) -> int:
    """`gate.incubator_reviews`: a whole number from 0 (off) to `REVIEWS_CEILING`; anything else is the default."""
    raw = (settings.get("gate") or {}).get("incubator_reviews", REVIEWS_PER_ROUND)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or float(raw) != int(raw):
        return REVIEWS_PER_ROUND
    return max(0, min(REVIEWS_CEILING, int(raw)))


# ---------------------------------------------------------------------------------------------------- the cohorts
def practice_cohorts(root: str | Path, *, research: Mapping[str, Any] | None, before: str) -> list[dict[str, Any]]:
    """The House's ACTIVE practice cohorts under the current evaluator (`practice_current`), with their practice so far,
    read-only (`mode=ro`, a one-second timeout). Never raises: [] without the file, before its cohorts table, or on any
    error. One row a cohort, oldest first:

        family, version, first_day, run_sha (the snapshot's program), evaluator (the cohort's practice evaluator)
        sessions         completed sessions (`practice.sessions`, less today's); None when there is no practice row or it
                         is older than the cohort (a record from before the cohort is not the cohort's)
        closes_program   program-closed trades (not forced) under the cohort's evaluator that closed before `before`
        pnl_program      their P&L (the engine's, after its fees)
    """
    path = Path(root) / OBSERVE_FILE
    if not path.exists():
        return []
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            return _cohorts(db, research, str(before))
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - a fact that cannot be read is not written
        return []


def _cohorts(db: sqlite3.Connection, research: Mapping[str, Any] | None, before: str) -> list[dict[str, Any]]:
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"cohorts", "practice", "trades"} <= tables:
        return []
    columns = {row[1] for row in db.execute("PRAGMA table_info(trades)")}
    if not {"evaluator", "forced", "exit_day"} <= columns:
        return []
    out = []
    rows = db.execute("SELECT family, version, first_day, snapshot FROM cohorts WHERE status='active' "
                      "ORDER BY admitted_at, family, version").fetchall()
    for family, version, first_day, snapshot in rows:
        try:
            snap = json.loads(snapshot)
        except (TypeError, ValueError):
            continue
        if not isinstance(snap, dict) or not practice_current(snap.get("practice_evaluator"), research):
            continue
        evaluator = snap["practice_evaluator"]
        live = db.execute("SELECT first_day, last_day, sessions FROM practice WHERE family=? AND version=?",
                          (family, version)).fetchone()
        sessions = None
        if live is not None and str(live[0]) >= str(first_day):
            sessions = int(live[2] or 0) - int(str(live[1]) == before)
        closes, pnl = db.execute("SELECT COUNT(*), COALESCE(SUM(pnl), 0) FROM trades WHERE family=? AND version=? "
                                 "AND evaluator=? AND forced=0 AND exit_day < ?",
                                 (family, version, evaluator, before)).fetchone()
        out.append({"family": str(family), "version": int(version), "first_day": str(first_day),
                    "run_sha": snap.get("run_sha"), "evaluator": evaluator, "sessions": sessions,
                    "closes_program": int(closes or 0), "pnl_program": float(pnl or 0.0)})
    return out


# ---------------------------------------------------------------------------------------------------- 1. the mark
def eligible_train_run(store: SwarmStore, fam: Mapping[str, Any], n: int, evaluator: Mapping[str, Any]) -> dict[str, Any] | None:
    """Version `n`'s newest eligible Train run (`train_eligible`, completed, at the normal spread) over the running Train
    span under `evaluator` (`evaluator.row_matches`), or None."""
    from .evaluator import row_matches

    span = running_span(store)
    for row in store.version_runs(fam["id"], int(n), window="train", stress=1.0, limit=20):
        if row.get("status") != "ok" or (row.get("summary") or {}).get("train_eligible") is not True:
            continue
        if row_span(row) == span and row_matches(store, row, evaluator):
            return row
    return None


def mark_of(store: SwarmStore, fam: Mapping[str, Any], n: int, settings: Mapping[str, Any], *, evaluator: Mapping[str, Any],
            objective: Any, clock: Callable[[], float] = time.time) -> tuple[dict[str, Any] | None, str, bool]:
    """(the mark, why not, final): version `n`'s Train and drift mark (the module docstring) when every condition holds,
    else None with the reason. `final` is True when the version has failed for good (demoted, a loss at 1.5x, a known
    failed drift screen): an existing mark then goes."""
    state = fam.get("state") or {}
    if demoted(state, n):
        return None, "demoted (a loss at 1.5x or a failed drift screen)", True
    robust = robust_at_stress(state, n)
    if robust is False:
        return None, "its 1.5x Train run lost money", True
    if robust is None:
        return None, "its 1.5x Train run has not landed", False
    stressed = ((state.get("robustness") or {}).get(str(n)) or {}).get("stress_1.5") or {}
    from .evaluator import matches

    if ("gym_image" in stressed or "gym_bundle" in stressed) and not matches(stressed, evaluator):
        return None, "its 1.5x Train run is another evaluator's", False
    run = eligible_train_run(store, fam, n, evaluator)
    if run is None:
        return None, "no eligible Train run under the current evaluator", False
    screen = drift_verdict(store, fam, n, settings)
    if screen is None:
        return None, "the drift screen is off (an off screen never passes)", False
    if not screen["known"]:
        return None, "its drift figures are owed", False
    if not screen["passed"]:
        return None, f"it fails the drift screen: {screen['why']}", True
    t = screen.get("t")
    return {"evaluator": dict(evaluator), "objective": objective, "run": str(run["run_id"]),
            "robust_pnl": round(float(stressed["pnl"]), 2),
            "drift": {"t": None if t is None else round(float(t), 4), "positive": int(screen.get("positive") or 0),
                      "years": int(screen.get("years") or 0)},
            "at": float(clock())}, "", False


def _kept(marks: Mapping[str, Any]) -> dict[str, Any]:
    keys = sorted((k for k in marks if str(k).isdigit()), key=int)[-MARKS_KEPT:]
    return {k: marks[k] for k in keys}


def facts(store: SwarmStore, settings: Mapping[str, Any], root: str | Path | None = None, *,
          clock: Callable[[], float] = time.time) -> dict[str, Any]:
    """THE TRAIN AND DRIFT MARKS (the module docstring, 1), for the tournament's hourly round. Returns the round's account:
    {cohorts, marked, written, removed, waiting} (written and removed as "family@version"). Writes nothing without a
    research evaluator and a Train objective in the store, or without a readable practice record."""
    from .evaluator import KEY

    out: dict[str, Any] = {"cohorts": 0, "marked": 0, "written": [], "removed": [], "waiting": 0}
    evaluator, objective = store.get(KEY), store.get("train_objective")
    if not isinstance(evaluator, Mapping) or objective is None:
        out["skipped"] = "no research evaluator or Train objective in the store"
        return out
    cohorts = practice_cohorts(root if root is not None else store.root, research=evaluator, before=session_day(clock))
    out["cohorts"] = len(cohorts)
    for cohort in cohorts:
        fid, n = cohort["family"], int(cohort["version"])
        fam = store.family(fid)
        if fam is None or fam.get("retired_at") or fam.get("band") != "gym":
            continue
        state = fam.get("state") or {}
        marks = dict(state.get("train_passed") or {})
        mark, _, final = mark_of(store, fam, n, settings, evaluator=evaluator, objective=objective, clock=clock)
        if mark is None:
            if final and str(n) in marks:
                marks.pop(str(n))
                changed = "removed"
            else:
                out["waiting"] += 1
                continue
        elif current_mark(marks.get(str(n)), evaluator, objective):
            out["marked"] += 1
            continue
        else:
            marks[str(n)] = mark
            changed = "written"
        expect = {key: state.get(key) for key in ("robust_failed", "drift_failed", "train_passed")}
        with store.atomic():
            now = store.family(fid) or {}
            if now.get("retired_at") or now.get("band") != "gym":
                continue
            done = store.compare_and_set_state(fid, expect, train_passed=_kept(marks))
        if done:
            out[changed].append(f"{fid}@{n}")
            if changed == "written":
                out["marked"] += 1
    return out


# ---------------------------------------------------------------------------------------------------- 2. the reviews
def due_reviews(store: SwarmStore, settings: Mapping[str, Any], root: str | Path | None = None, *,
                clock: Callable[[], float] = time.time) -> list[dict[str, Any]]:
    """The versions that need an incubator review (the module docstring, 2), oldest cohort first: [{family, version, sha,
    sessions, closes}]. [] without a research evaluator and Train objective, without a current mark on any alive Gym
    family (the practice record is not read then), or without a readable practice record."""
    from .evaluator import KEY
    from .gate import run_sha

    evaluator, objective = store.get(KEY), store.get("train_objective")
    if not isinstance(evaluator, Mapping) or objective is None:
        return []
    marked = {fam["id"]: fam for fam in store.families(alive=True) if fam.get("band") == "gym"
              and any(current_mark(m, evaluator, objective) for m in ((fam.get("state") or {}).get("train_passed") or {}).values())}
    if not marked:
        return []
    out = []
    for cohort in practice_cohorts(root if root is not None else store.root, research=evaluator, before=session_day(clock)):
        fam = marked.get(cohort["family"])
        if fam is None:
            continue
        n, state = int(cohort["version"]), fam.get("state") or {}
        if state.get("gate_hold") or demoted(state, n):
            continue  # the operator holds it (no paid stage), or it failed for good
        if not current_mark((state.get("train_passed") or {}).get(str(n)), evaluator, objective):
            continue
        sessions, closes = cohort["sessions"], cohort["closes_program"]
        if sessions is None or sessions < REVIEW_MIN_SESSIONS or closes < REVIEW_MIN_CLOSES or not cohort["pnl_program"] > 0:
            continue
        version = store.version(fam["id"], n)
        if version is None or not version.get("code"):
            continue
        sha = run_sha(version)
        if cohort["run_sha"] != sha:
            continue  # the cohort practises another program than this version's
        if final_review(state, sha) is not None or program_refused(store, fam["id"], n):
            continue
        outcome = state.get("gate_outcome") or {}
        if outcome.get("sha") == sha and outcome.get("result") in ("refused", "failed", "demoted"):
            continue  # the live side never admits it: no review is paid
        if state.get("gate_ready") and state.get("validation_version") == n:
            continue  # the gate is reviewing this very version now: its review and audit serve
        out.append({"family": fam["id"], "version": n, "sha": sha, "sessions": sessions, "closes": closes,
                    "first_day": cohort["first_day"]})
    out.sort(key=lambda r: (r["first_day"], r["family"], r["version"]))
    return out


def reviewable(store: SwarmStore, fid: str, n: int, sha: str) -> bool:
    """Before each paid stage: the family is alive in the Gym band, not held by the operator, version `n` is not demoted,
    its mark is current and its program is still `sha`."""
    from .evaluator import KEY
    from .gate import run_sha

    fam = store.family(fid) or {}
    state = fam.get("state") or {}
    if fam.get("retired_at") or fam.get("band") != "gym" or state.get("gate_hold") or demoted(state, n):
        return False
    if not current_mark((state.get("train_passed") or {}).get(str(n)), store.get(KEY), store.get("train_objective")):
        return False
    version = store.version(fid, n)
    return version is not None and bool(version.get("code")) and run_sha(version) == sha


def put_review(store: SwarmStore, fid: str, sha: str, record: Mapping[str, Any]) -> None:
    """Record program `sha`'s incubator review in its family's state, keeping the newest `REVIEWS_KEPT`."""
    with store.atomic():
        state = (store.family(fid) or {}).get("state") or {}
        records = {k: v for k, v in dict(state.get("incubator_reviews") or {}).items() if isinstance(v, Mapping)}
        records[sha] = dict(record)
        keep = sorted(records, key=lambda k: (float(records[k].get("at") or 0.0), k))[-REVIEWS_KEPT:]
        store.set_state(fid, incubator_reviews={k: records[k] for k in keep})


__all__ = ["facts", "due_reviews", "practice_cohorts", "practice_current", "current_mark", "final_review", "mark_of",
           "program_refused", "PROGRAM_REFUSALS",
           "eligible_train_run", "reviewable", "put_review", "reviews_per_round", "session_day",
           "MARKS_KEPT", "REVIEWS_KEPT", "REVIEW_MIN_SESSIONS", "REVIEW_MIN_CLOSES", "REVIEWS_PER_ROUND",
           "REVIEWS_CEILING", "OBSERVE_FILE"]
