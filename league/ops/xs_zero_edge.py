"""The `xs_zero_edge` job: what the panel Train bar passes at ZERO edge, measured every week on the bar as built.

Owner: package G of release E4. Protected (league/ops/). The registry rows are package A's patch (E4-SPEC 13: four
chunks on Sunday).

Each week `elane.panel.zero_edge_programs` (100) seeded RANDOM-SCORE programs (the top k by a hash of (seed, id,
decision index); k in `KS`; weekly and monthly; each with a hidden year drawn as a family's is) run the WHOLE bar
equity-xs-v1, the restart check included, through the job's own niced decider (never the swarm's, never the live
one), `PROGRAMS_RUN` a run. Into the swarm store's kv `elane_xs_zero_edge` {week: {programs, passes, by_rule}}: the
Train map shows each cell's passes beside births x that pass rate (the ZERO-EDGE EXPECTED column). An alarm when the
rate is above `ALARM_RATE`: the bar is too loose. Rule-level figures only: no program of the swarm is read, and no
result of one is written.

THE PROGRAMS (`program_code`, `plan`). A program's picks are a hash's and nothing else's: at each call the k slots
whose hash of (its seed, the slot id, the decision's key) is smallest, at equal weights. THE DECISION'S KEY IS READ
FROM ctx, NEVER COUNTED: a call counter kept in STATE would fail the bar's own restart check every time (the check
empties STATE), and the job would then measure nothing; the key is a hash of the market's last ten returns as ctx
gives them, which no two decisions share and a fresh load reads the same. The hash is integer arithmetic (the
program contract allows math and numpy only). `plan(week, index)` fixes program `index` of a week: its seed, its k
(`KS` in turn), its schedule (`SCHEDULES` in turn) and its hidden year, drawn as `elane_xs.assign` draws a family's
(the panel's six Train years, rotated within its cell of k and schedule) while the swarm's folds are recording, else
none (families then have none either, and the bar reads all six years).

THE BAR IS THE SWARM'S OWN, CALLED, NEVER COPIED: `elane_xs.run_spans` (one run a seen span, each starting flat: the
full universe at 1.0x and at 1.5x with `placebos_train` placebos and `calls=True`, each asset half at 1.5x),
`elane_xs.train_score_xs`, then on a bar pass `elane_xs.state_check` and `elane_xs.with_state`. No hidden run is made
(it judges nothing). A program is counted once its verdict is whole; one the House could not judge (a run that
failed, a restart check that could not finish) is not counted, and the job stops there with what it has.

THE WALLS. The job's first statement is `league.xs.config.quiet(now, WALL_S)` (its own wall: a start that could
still be working at a wall is skipped, and the chunk resumes at its next trigger), and every run asks
`quiet(now, run_budget_seconds)` before it starts, as a panel Train run of the swarm does. With `elane.panel.mode`
under "train" the job does nothing. THE CHUNK'S OWN WALL: a chunk starts no further program once the time it has
worked plus its slowest program's would pass `CHUNK_S` (the registry row's working budget, under `WALL_S`): it
stops with what it has, the week's row already written, and the next trigger resumes it; the runner never has to
end it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import time
from pathlib import Path
from typing import Any, Mapping

KV = "elane_xs_zero_edge"
PROGRAMS_RUN = 25
KS = (5, 8, 12)
SCHEDULES = ("weekly", "monthly")
ALARM_RATE = 0.05
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 3000
#: The chunk's working budget (seconds; the registry row's cpu figure, under `WALL_S`): no further program starts
#: once the time the chunk has worked plus its slowest program's would pass it.
CHUNK_S = 2400
#: The job's decider log, under the state root (its own child: never the swarm's `xs-decider.log`).
DECIDER_LOG = "xs-zero-decider.log"
#: The weeks the kv keeps (half a year: the Train map's rate is over all of them).
WEEKS_KEPT = 26
#: What a week's row counts a program under when it passed, and when its own code failed (a fault of this module).
PASS, FAULT = "pass", "FAULT"

_PROGRAM = '''import math

NEEDS = {needs}
PARAMS = {{"seed": {seed}, "k": {k}}}


def _mix(a, b):
    x = (a * 2654435761 + b * 40503 + 2654435769) % 4294967296
    x = x ^ (x >> 15)
    x = (x * 2246822519) % 4294967296
    x = x ^ (x >> 13)
    x = (x * 3266489917) % 4294967296
    return x ^ (x >> 16)


def decide(ctx):
    k = int(ctx.params["k"])
    if ctx.n < k:
        return {{"hold": True}}
    key = 0
    for value in ctx.mkt.ret[-10:]:
        v = float(value)
        if v == v:
            key = _mix(key, int(round(v * 1000000.0)) % 4294967296)
    seed = int(ctx.params["seed"])
    scored = sorted((_mix(_mix(seed, int(slot)), key), int(slot)) for slot in ctx.ids)
    weight = min(0.2, 1.0 / k)
    return {{"target": {{slot: weight for _, slot in scored[:k]}}, "at": "open"}}
'''


def program_code(seed: int, k: int, rebalance: str) -> str:
    """The source of one random-score panel program (XS.md's contract; no signal: its picks are a hash's)."""
    if k not in KS or rebalance not in SCHEDULES:
        raise ValueError(f"a zero-edge program holds one of {KS} names on one of {SCHEDULES}, not {k!r} {rebalance!r}")
    needs = {"panel": "sp500", "history": 20, "max_names": int(k), "rebalance": rebalance, "max_hold_sessions": 60}
    if rebalance == "weekly":
        needs["weekday"] = 0
    return _PROGRAM.format(needs=repr(needs), seed=int(seed), k=int(k))


def week_of(now: float) -> str:
    """The ISO week key of the epoch `now` ("2026-W42")."""
    year, week, _ = dt.datetime.fromtimestamp(float(now), dt.timezone.utc).isocalendar()
    return f"{year}-W{week:02d}"


def plan(week: str, index: int, *, hidden: bool = True) -> dict[str, Any]:
    """Program `index` of `week` (the module docstring): {index, seed, k, rebalance, hidden_year}. Deterministic: a
    chunk that resumes runs the programs the week's earlier chunks did not. `hidden` False: no hidden year (the
    swarm's folds are not recording)."""
    from ..xs import config as xconfig

    index = int(index)
    k = KS[index % len(KS)]
    rebalance = SCHEDULES[(index // len(KS)) % len(SCHEDULES)]
    seed = int.from_bytes(hashlib.sha256(f"xs-zero-1|{week}|{index}".encode()).digest()[:4], "big") >> 1
    born = index // (len(KS) * len(SCHEDULES))  # the programs of this cell (k, schedule) already drawn this week
    turn = int(hashlib.sha256(f"xs-zero-1|{week}|{k}|{rebalance}".encode()).hexdigest()[:8], 16)
    year = int(xconfig.TRAIN_YEARS[(born + turn) % len(xconfig.TRAIN_YEARS)]) if hidden else None
    return {"index": index, "seed": seed, "k": k, "rebalance": rebalance, "hidden_year": year}


def build_runner(root: Path, settings: Mapping[str, Any]) -> tuple[Any, Any]:
    """(the job's `league.xs.runner.Isolated`, its decider): its OWN `league.live.decider.Decider`, nice 19, its hash
    seed pinned as the swarm's evidence child's is; never the swarm's runner and never the live decider."""
    from ..live.decider import Decider
    from ..swarm import elane, elane_xs
    from ..xs.runner import NICE, Isolated

    decider = Decider(log=Path(root) / DECIDER_LOG)
    decider.hash_seed = elane.EVIDENCE_HASH_SEED
    budget = float(elane_xs.cfg(settings)["run_budget_seconds"])
    return Isolated(decider, Path(root) / elane_xs.STORE_DIR, budget_seconds=budget, nice=NICE), decider


class Stopped(RuntimeError):
    """A run may not start now (a wall is near): the chunk stops with what it has and resumes at its next trigger."""


def judge(run_through: Any, decider: Any, code: str, *, name: str, hidden: int | None, years_ok: Any,
          placebos: int, before: Any = None) -> dict[str, Any]:
    """THE WHOLE BAR for one program (the module docstring), nothing recorded: {passed, fails}. `before()` is called
    before each run (it raises `Stopped` to stop the chunk). The runner's and the decider's own errors pass through
    (the House's: the program is not counted)."""
    from ..swarm import elane_xs

    spans = elane_xs.run_spans(hidden, years_ok)
    if not spans:
        raise RuntimeError("the panel store names no Train year the bar can run on")
    runs: dict[Any, list[Any]] = {"base": [], "stress": [], 0: [], 1: []}

    def one(**kw: Any) -> Any:
        if before is not None:
            before()
        return run_through.train(code, {}, name=name, **kw)

    for first, last in spans:
        runs["base"].append(one(start=first, end=last, k=elane_xs.K_BASE, style=True))
        runs["stress"].append(one(start=first, end=last, k=elane_xs.K_STRESS, placebos=int(placebos), calls=True))
        for half in elane_xs.HALVES:
            runs[half].append(one(start=first, end=last, k=elane_xs.K_STRESS, half=half))
    parts = {key: [dict(getattr(run, "result", None) or {}) for run in rs] for key, rs in runs.items()}
    statuses = {str(result.get("status")) for rs in parts.values() for result in rs}
    if "disqualified" in statuses:
        return {"passed": False, "fails": [FAULT]}  # a random-score program has no error of its own to make
    if statuses != {"ok"}:
        raise RuntimeError(f"the zero-edge runs ended {', '.join(sorted(statuses))}")
    verdict = elane_xs.train_score_xs({"spans": spans, "base": parts["base"], "stress": parts["stress"],
                                       "halves": {0: parts[0], 1: parts[1]}}, years_ok=years_ok)
    if verdict["passed"]:
        verdict = elane_xs.with_state(verdict, elane_xs.state_check(decider, code, {}, name=name, runs=runs["stress"]))
    return {"passed": bool(verdict["passed"]), "fails": list(verdict["fails"])}


def _row(value: Any) -> dict[str, Any]:
    """A week's row as the kv keeps it: {programs, passes, by_rule {code: programs}} (a malformed one starts again)."""
    value = value if isinstance(value, Mapping) else {}
    rules = value.get("by_rule") if isinstance(value.get("by_rule"), Mapping) else {}
    count = [value.get("programs"), value.get("passes")]
    ok = all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in count) and count[1] <= count[0]
    return {"programs": count[0] if ok else 0, "passes": count[1] if ok else 0,
            "by_rule": {str(k): int(v) for k, v in rules.items() if isinstance(v, int) and not isinstance(v, bool)}
            if ok else {}}


def _folds_on(settings: Mapping[str, Any]) -> bool:
    """Whether a new panel family is born with a hidden year (release E3's folds are merged and recording)."""
    try:
        from ..swarm import elane_folds

        return elane_folds.mode(settings) == "record"
    except Exception:  # noqa: BLE001 - no folds: no hidden year, for families and for these programs alike
        return False


def run(ctx: Any) -> dict[str, Any]:
    """The job. Its first statement is `league.xs.config.quiet(ctx.now(), WALL_S)`."""
    from ..xs import config as xconfig

    try:
        wall = xconfig.quiet(ctx.now(), WALL_S)
    except Exception as exc:  # noqa: BLE001 - a wall that cannot be read starts nothing
        return {"status": "skipped", "why": f"the panel's quiet windows cannot be read ({type(exc).__name__})"}
    if wall is not None:
        return {"status": "skipped", "why": str(wall)}
    from ..swarm import elane_xs
    from ..swarm import settings as swarm_settings
    from ..swarm.store import SwarmStore

    root = Path(ctx.root)
    settings = swarm_settings.load(root)
    if elane_xs.MODES.index(elane_xs.mode(settings, root)) < elane_xs.MODES.index("train"):
        return {"status": "skipped", "why": "the panel lane is off (elane.panel.mode)"}
    c = elane_xs.cfg(settings)
    years_ok = elane_xs.years_ok(root)
    if not years_ok:
        return {"status": "skipped", "why": "the panel store names no Train year the bar can run on"}
    week = week_of(ctx.now())
    store = SwarmStore(root)
    decider = None
    done = 0
    stopped: str | None = None
    try:
        held = store.get(KV)
        weeks = {str(k): _row(v) for k, v in (held.items() if isinstance(held, Mapping) else ())}
        row = _row(weeks.get(week))
        todo = min(PROGRAMS_RUN, int(c["zero_edge_programs"]) - row["programs"])
        if todo <= 0:
            return {"status": "skipped", "why": "this week's zero-edge programs are run", "week": week,
                    "programs": row["programs"], "passes": row["passes"]}
        run_through, decider = build_runner(root, settings)
        folds = _folds_on(settings)

        def before() -> None:
            why = xconfig.quiet(ctx.now(), float(c["run_budget_seconds"]))
            if why is not None:
                raise Stopped(str(why))

        started, slowest = time.monotonic(), 0.0
        for index in range(row["programs"], row["programs"] + todo):
            if done and time.monotonic() - started + slowest > CHUNK_S:
                stopped = "the chunk's own wall is near: the next trigger resumes the week"
                break
            spec = plan(week, index, hidden=folds)
            code = program_code(spec["seed"], spec["k"], spec["rebalance"])
            began = time.monotonic()
            try:
                verdict = judge(run_through, decider, code, name=f"xs-zero-{week}-{index}", hidden=spec["hidden_year"],
                                years_ok=years_ok, placebos=int(c["placebos_train"]), before=before)
            except Stopped as exc:
                stopped = str(exc)
                break
            except Exception as exc:  # noqa: BLE001 - the House's: this program is not counted, the chunk ends here
                stopped = f"{type(exc).__name__}: {str(exc)[:200]}"
                if not done:
                    return {"status": "failed", "error": stopped, "week": week, "programs": row["programs"],
                            "passes": row["passes"]}
                break
            finally:
                took = time.monotonic() - began
                slowest = max(slowest, took)
                elane_xs.book_cpu(store, took, ctx.now())
            row["programs"] += 1
            row["passes"] += int(verdict["passed"])
            for code_ in ([PASS] if verdict["passed"] else verdict["fails"] or [FAULT]):
                row["by_rule"][code_] = row["by_rule"].get(code_, 0) + 1
            weeks[week] = row
            store.put(KV, {k: weeks[k] for k in sorted(weeks)[-WEEKS_KEPT:]})  # after EACH program: a chunk resumes
            done += 1
    finally:
        try:
            if decider is not None and callable(getattr(decider, "close", None)):
                decider.close()
        finally:
            store.close()
    rate = row["passes"] / row["programs"] if row["programs"] else None
    complete = row["programs"] >= int(c["zero_edge_programs"])
    if complete and rate is not None and rate > ALARM_RATE:
        ctx.alert("warning", f"the panel Train bar passed {row['passes']} of {row['programs']} random-score programs "
                             f"with no edge in {week} (above {ALARM_RATE:.0%}): the bar is too loose")
    out = {"status": "ok", "week": week, "ran": done, "programs": row["programs"], "passes": row["passes"],
           "rate": round(rate, 4) if rate is not None else None, "by_rule": dict(sorted(row["by_rule"].items())),
           "complete": complete}
    if stopped is not None:
        out["stopped"] = stopped
    return out


__all__ = ["KV", "PROGRAMS_RUN", "KS", "SCHEDULES", "ALARM_RATE", "WALL_S", "CHUNK_S", "DECIDER_LOG", "WEEKS_KEPT",
           "PASS", "FAULT", "Stopped", "program_code", "week_of", "plan", "build_runner", "judge", "run"]
