"""PREREG-EVL-7 SECTIONS 1.10 AND 3.1: THE LEARNERS' LOOKS AND RUNS, judged by PREREG-EVL-6's screen AS FROZEN through
its ONE NARROW INTERFACE (league/events/costs7.py `judge_record`, which hands a record to screen.py `v6_judge` over
`blocks6`, PREREG-EVL-6's code). Standard library only. Nothing here runs while league/events/programs.py
`REGISTERED_AT_7` is None (no learner is in any registry), and only for COST-7's explicit set (`costs7.VERSIONS`).

WHAT IT DOES, each night in the House's screen step (league/events/house.py `_screen`), after the earlier files' looks
and PREREG-EVL-6's start of its waiting runs, for each learner version AT LEARNING (`run`):

1. THE NIGHT'S COST BASIS. With no `cost_basis` row for the night, or one that cannot be read, EVERY LOOK OF THESE
   VERSIONS WAITS, and the run's end with it (section 2.2 (d); A66: late data delays a look, never its as-of close).
2. ITS RUN RECORD (section 3.1; PREREG-EVL-6 section 1.2): `costs7.record7` with `before` the look's compute time (the
   latest `cost_basis` row written before it: section 2.1), the forward picks of the decisions made LIVE only (each
   under the learner's own live receipt `decide-<at>-lrnlive:<D>` finished `ok`), each valued on a7 and r7 with its
   sigma, ADV20 and E_prev as the decision stored them; run n >= 2 only the blocks after its start record's `after_day` and the entries
   decided after its `after` (PREREG-EVL-6 section 3). Its control: `costs7.control7`, the POOL record of the same live
   decisions (section 6), read only when a look falls due.
3. ITS LOOKS (PREREG-EVL-6 section 2, `schedule`): look k at the first session close X at which the run's record
   covered at X holds at least S_k = 22, 25, 30, 35, 40, 50, 60 BLOCKS (an entry session with at least one event
   TRADABLE under COST-7) AND the minimums hold (30 TRADABLE events, 30 issuers, 6 blocks); thresholds reached
   together are one look, the lowest k, the others merged into it; no look after the 60th block. A look as of X is
   computed once X is FINAL FOR THE LEARNER (`final`: final for every pool program feeding its control, screen.py
   `final_until` of each; the learner's own live decisions are written once and never decided again) and every intent
   of the learner and of its pool programs scheduled to exit by X has settled. It is judged by `judge_record` (the
   record's first 60 blocks, its POOL control, the run's TAG "" for run 1 and f"run{n}|" after), WRITTEN ONCE
   (screen.py `write_look`, INSERT OR IGNORE, its stored key carrying the run and S: `look_key`), with its band move in
   its own transaction: RETIRE to `retired` (for good), PASS to `probe` (from the first decision after the look).
   WITH NO PREREG-EVL-6 SCREEN IN THE TREE (`judge_record` answers no decision and says so), NOTHING IS WRITTEN: no
   look, no pass, no retirement, no run's end (and the real-money gate below then refuses the learner's buys once a
   look is due).
4. THE RUN'S END AT ITS 60TH BLOCK (D2): decided with that close's look (after its RETIRE and PASS) or, with no look
   held there, once that close is final; written once (meta `END_KEY`), the version staying in learning.
5. ITS NEXT RUN (section 1.10, E2; `start_runs`): due when run n ended at its 60th block, or after a demotion from a
   Probe stay back to learning; CHARGED c7 = 0.13 WHEN IT STARTS (`CHARGE`), and it starts ONLY WHEN THE LANE'S COUNT
   HOLDS IT (`used`: every seating version's 0.13 and every fresh run started, against PREREG-EVL-6's frozen 3.9), the
   earlier files' waiting runs drawn first (registration order: a run of PREREG-EVL-6 still waiting holds its 0.13 ahead
   of the learners'). A learner id has AT MOST THREE RUNS (`RUNS_MAX`). A run that cannot start, or a fourth that
   would be due, is written as REFUSED for good (meta `NORUN_KEY`): the version continues as a shadow record, NEVER
   SEATS AGAIN, and its open lots exit by their rules.

THE REAL-MONEY GATE (`gate`, read by league/events/book.py `learner_picks` before any pick of a learner goes to real
money, and by the H5 alarm league/ops/evl_learner.py): a learner buys nothing when it is retired; at Probe or Sized
(no PREREG-EVL-6 section 3 stay judge for COST-7's versions is in this tree: `STAYS_JUDGED`, fail closed); when its
current run ended (its next run not started) or was refused, or its three runs are spent; and, FAILING CLOSED (the
judges review), when its current run's record holds the blocks of its next look (with the minimums) and that look is
not written, or 60 blocks and no end, as with no PREREG-EVL-6 screen in the tree. The shadow decisions go on in
every case; only real money stops.

THE STORED FORMS ARE PREREG-EVL-6's (league/events/screen.py on release 1019i: `V6_RUN_KEY`, `V6_END_KEY`, `look_key6`,
`_look6_row`'s `v6` detail), held equal by league/tests/test_events_evl7.py wherever the tree carries that code, so the
lane's one count (screen.py `budget6`, R3's validator) counts these versions' runs with every other and every reader of
a run or a look reads these the same way. This module never edits the screen, the costs or any frozen code."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Iterable, Mapping, Sequence

from . import calendar as C
from . import costs7 as C7
from . import programs as P
from . import store as S

#: PREREG-EVL-6 section 2 AS FROZEN (its screen.py `V6_LOOKS`, `V6_RUN_BLOCKS`, `V6_MIN_*`): the looks' thresholds in
#: blocks, the run's end, the minimums at a look.
LOOKS = (22, 25, 30, 35, 40, 50, 60)
RUN_BLOCKS = 60
MIN_EVENTS, MIN_ISSUERS, MIN_BLOCKS = 30, 30, 6
#: Section 1.10 and 4 (E1, E2): c7 = max(PREREG-EVL-6's 0.13, W7 0.087 rounded up) = 0.13 a run, at most three runs an
#: id; the lane's lifetime budget on PREREG-EVL-6's frozen basis (30 x 0.13), all in hundredths (no float drift).
CHARGE = 13
BUDGET = 390
RUNS_MAX = 3
#: PREREG-EVL-6's stored forms (league/events/screen.py `V6_STAY_BASE`, `V6_RUN_KEY`, `V6_END_KEY` on release 1019i).
STAY_BASE = 1_000_000
RUN_KEY = "evl6:run:{program}:{version}:{n}"
END_KEY = "evl6:end:{program}:{version}:{n}"
#: This file's own: a run that could not start (the lane's count could not hold it, or a fourth run would be due) is
#: refused FOR GOOD (section 1.10: "never seats again"); the look's COST-7 detail beside screen.py's own (`look:` meta).
NORUN_KEY = "evl7:norun:{program}:{version}:{n}"
LOOK_KEY = "evl7:look:{program}:{version}:{k}"
#: PREREG-EVL-6 section 3's STAYS (Sized, demotion, the money stop, the fixed reads, the stay's lower tail) for COST-7's
#: versions: not in this tree. A learner at Probe or Sized buys nothing in real money (fail closed) and the H5 alarm
#: says so; its shadow decisions go on.
STAYS_JUDGED = False
#: What `gate` answers (`kind`), and the kinds the H5 alarm raises (a stall the captain must read).
ALARM_KINDS = ("look_overdue", "end_overdue", "no_stay_judge")


def applies(learner: Any) -> bool:
    return C7.applies(getattr(learner, "id", ""), int(getattr(learner, "version", 0) or 0))


def in_force() -> list[P.Program]:
    """The learner versions in force that COST-7 judges, in registration order then id (`P.learners`)."""
    return sorted((p for p in P.learners() if applies(p)), key=lambda p: (str(P.REGISTERED_AT_7), p.id, p.version))


def _day(value: Any) -> dt.date:
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value)[:10])


def tag(kind: str, n: int) -> str:
    """PREREG-EVL-6 section 1.3's TAG: "" for a version's run 1, f"run{n}|" for its run n >= 2, f"stay{n}|" a stay's."""
    if kind == "stay":
        return f"stay{int(n)}|"
    return "" if int(n) == 1 else f"run{int(n)}|"


def look_key(kind: str, n: int, s: int) -> int:
    """A look's stored `k` (PREREG-EVL-6's `look_key6`): 1000 x n + S for run n, STAY_BASE + 1000 x n + S a stay's."""
    return (STAY_BASE if kind == "stay" else 0) + 1000 * int(n) + int(s)


def key_of(k: int) -> tuple[str, int, int]:
    k = int(k)
    kind = "stay" if k >= STAY_BASE else "run"
    rest = k - (STAY_BASE if kind == "stay" else 0)
    return kind, rest // 1000, rest % 1000


def _meta(store: Any, key: str) -> dict[str, Any] | None:
    raw = store.meta(key)
    if raw is None:
        return None
    try:
        got = json.loads(raw)
    except ValueError:
        return {"unreadable": True}
    return got if isinstance(got, dict) else {"unreadable": True}


def band_of(store: Any, learner: Any) -> str:
    """The learner's band in the lane's band table (no row: learning from birth); unreadable reads `retired` (the reading
    that trades less)."""
    try:
        row = store.db.execute("SELECT band FROM bands WHERE program=? AND version=?",
                               (learner.id, int(learner.version))).fetchone()
    except Exception:  # noqa: BLE001 - no table, or unreadable
        return "retired"
    return "learning" if row is None else str(row[0])


def _looks(store: Any, learner: Any) -> list[dict[str, Any]]:
    """The learner's written looks, each {k, at, detail}: the COST-7 detail this module wrote beside the look
    (`LOOK_KEY`), else the screen's own (`look:` meta, PREREG-EVL-6's `v6` there on release 1019i)."""
    out = []
    try:
        rows = store.db.execute("SELECT k, at FROM looks WHERE program=? AND version=? ORDER BY k",
                                (learner.id, int(learner.version))).fetchall()
    except Exception:  # noqa: BLE001 - no table yet
        return out
    for r in rows:
        k = int(r[0])
        mine = _meta(store, LOOK_KEY.format(program=learner.id, version=int(learner.version), k=k))
        screen = _meta(store, f"look:{learner.id}:{int(learner.version)}:{k}") or {}
        detail = mine if mine is not None else (screen.get("v6") or {})
        out.append({"k": k, "at": str(r[1]), "detail": detail, "merged": screen.get("merged") or detail.get("merged")
                    or []})
    return out


def runs(store: Any, learner: Any) -> list[dict[str, Any]]:
    """The learner version's runs as the store records them (PREREG-EVL-6's `runs6` reading): [{n, after_day, after,
    started, ended (None, or {why: pass | retire | horizon, at})}], run 1 charged with the version, run n >= 2 the one
    `start_runs` wrote; the last carries `next_refused` when its successor was refused for good."""
    pid, v = learner.id, int(learner.version)
    out: list[dict[str, Any]] = [{"n": 1, "after_day": None, "after": None, "started": None, "ended": None}]
    n = 2
    while True:
        rec = _meta(store, RUN_KEY.format(program=pid, version=v, n=n))
        if rec is None:
            break
        out.append({"n": n, "after_day": rec.get("after_day"), "after": rec.get("after"), "started": rec.get("started"),
                    "ended": None, "why": rec.get("why")})
        n += 1
    looks = _looks(store, learner)
    for run in out:
        for look in looks:
            kind, rn, _ = key_of(look["k"])
            if kind == "run" and rn == run["n"] and look["detail"].get("decision") in ("pass", "retire"):
                run["ended"] = {"why": look["detail"]["decision"], "at": look["at"]}
                break
        end = _meta(store, END_KEY.format(program=pid, version=v, n=run["n"]))
        if run["ended"] is None and end is not None:
            run["ended"] = {"why": "horizon", "at": end.get("at"), "last_day": end.get("last_day")}
    refused = _meta(store, NORUN_KEY.format(program=pid, version=v, n=out[-1]["n"] + 1))
    if refused is not None:
        out[-1]["next_refused"] = refused
    return out


def written(store: Any, learner: Any, kind: str, n: int) -> dict[str, Any]:
    """The looks on record of one run: {consumed: the thresholds used (1-based, a look's own and those merged into it),
    last: the as-of New York day of the latest, S: the largest S looked at} (PREREG-EVL-6's `written6`)."""
    consumed: set[int] = set()
    last: dt.date | None = None
    top = 0
    for look in _looks(store, learner):
        knd, rn, s = key_of(look["k"])
        if knd != kind or rn != int(n):
            continue
        consumed |= {int(look["detail"].get("look") or 0)} | {int(x) for x in look["merged"] or []}
        day = S.parse_iso(look["at"]).astimezone(C.NY).date()
        last = day if last is None or day > last else last
        top = max(top, s)
    consumed.discard(0)
    return {"consumed": consumed, "last": last, "S": top}


def _after(row: Mapping[str, Any], moment: dt.datetime | None) -> bool:
    if moment is None:
        return True
    try:
        return S.parse_iso(str(row["decided_at"])) > moment
    except (KeyError, TypeError, ValueError):
        return False        # (a decision time that cannot be read: not in the record, the reading less likely to pass)


def run_record(rows: Sequence[Mapping[str, Any]], run: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """A run's record of `rows`: run 1 every one; run n >= 2 the blocks after its `after_day` and the entries decided
    after its `after` (PREREG-EVL-6's `run_record6`)."""
    after_day = _day(run["after_day"]) if run.get("after_day") else None
    after = S.parse_iso(str(run["after"])) if run.get("after") else None
    return [r for r in rows if (after_day is None or _day(r["entry_day"]) > after_day) and _after(r, after)]


def covered(rows: Iterable[Mapping[str, Any]], as_of: dt.date) -> list[Mapping[str, Any]]:
    """The events of the blocks a look as of `as_of` covers: those whose SCHEDULED exit is at or before it."""
    return [r for r in rows if _day(r.get("exit_day") or r.get("exited")) <= as_of]


def blocks(rows: Iterable[Mapping[str, Any]]) -> list[tuple[dt.date, list[Mapping[str, Any]]]]:
    """The record's blocks (PREREG-EVL-6 section 1.2): every entry session holding at least one TRADABLE event, in
    session order, with those events."""
    groups: dict[dt.date, list[Mapping[str, Any]]] = {}
    for r in rows:
        if r.get("tradable") and r.get("a") is not None:
            groups.setdefault(_day(r["entry_day"]), []).append(r)
    return sorted(groups.items())


def minimums(events: Sequence[Mapping[str, Any]], s: int) -> bool:
    return len(events) >= MIN_EVENTS and len({str(e["issuer"]) for e in events}) >= MIN_ISSUERS and s >= MIN_BLOCKS


def pending(store: Any, learner: Any) -> list[tuple[dt.date, dt.date]]:
    """(entry, scheduled exit) of every intent not yet resolved of the learner and of its pool programs (the control)."""
    from .learner import POOLS

    out = []
    for program, version in [(learner.id, int(learner.version))] + [(pid, 1) for pid in POOLS.get(learner.id, ())]:
        out += [(_day(r[0]), _day(r[1])) for r in store.db.execute(
            "SELECT entry_day, exit_day FROM intents WHERE program=? AND version=? AND status IN ('planned', 'entered')",
            (program, version))]
    return out


def final(store: Any, learner: Any, today: dt.date, now: dt.datetime) -> tuple[dt.date | None, str]:
    """The last close FINAL FOR THE LEARNER's look (PREREG-EVL-6 section 2's FINALITY with this file's record): the
    earliest of its pool programs' final closes (screen.py `final_until` of each registered one: the POOL control reads
    their records, which a re-decision inside A66's reach could still change); the learner's own live decisions are
    written once and never decided again (section 1.7), so they hold none back. None when one pool program has none."""
    from . import screen as SN
    from .learner import POOLS

    horizon: dt.date | None = None
    why = "no pool program is registered"
    for pid in POOLS.get(learner.id, ()):
        if P.BY_KEY.get((pid, 1)) is None:
            continue        # (a pool program not in this tree contributes no candidate, section 1.2)
        day, reason = SN.final_until(store, pid, 1, today, now)
        if day is None:
            return None, f"{pid}: {reason}"
        if horizon is None or day < horizon:
            horizon, why = day, f"{pid}: {reason}"
    return horizon, why


def schedule(store: Any, record: Sequence[Mapping[str, Any]], today: dt.date, *,
             waits: Sequence[tuple[dt.date, dt.date]] = (), consumed: Iterable[int] = (), after: dt.date | None = None,
             horizon: tuple[dt.date | None, str] | None = None) -> dict[str, Any]:
    """Section 2's looks of one run record from where the record on file left it (PREREG-EVL-6's `schedule6`, block
    counts by COST-7's TRADABLE): {looks: [(look k, as-of day, merged ks, S)], horizon: (the close its 60th block is
    covered at, that block's day) when the scan reaches it, stopped, why}."""
    out: dict[str, Any] = {"looks": [], "horizon": None, "stopped": None, "why": None}
    if not record:
        return out
    j = max(set(int(k) for k in consumed)) if consumed else 0
    first = min(_day(r["entry_day"]) for r in record)
    for s in C.sessions(store, first, today):
        if after is not None and s.day <= after:
            continue
        if any(x <= s.day for _, x in waits):
            out["stopped"], out["why"] = s.day, f"an intent scheduled to exit by {s.day.isoformat()} has not settled"
            break
        every = blocks(covered(record, s.day))
        blk = every[:RUN_BLOCKS]
        events = [e for _, es in blk for e in es]
        held = j < len(LOOKS) and len(blk) >= LOOKS[j] and minimums(events, len(blk))
        ends = len(every) >= RUN_BLOCKS
        if (held or ends) and horizon is not None and (horizon[0] is None or s.day > horizon[0]):
            what = f"look {j + 1}" if held else "the run's 60th block"
            out["stopped"], out["why"] = s.day, f"{what} falls due at {s.day.isoformat()}, not final yet: {horizon[1]}"
            break
        if held:
            reached = [i for i in range(j, len(LOOKS)) if len(blk) >= LOOKS[i]]
            out["looks"].append((reached[0] + 1, s.day, [i + 1 for i in reached[1:]], len(blk)))
            j = reached[-1] + 1
        if ends:
            out["horizon"] = (s.day, every[RUN_BLOCKS - 1][0])
            break
    return out


def _look_row(learner: Any, n: int, k: int, merged: list[int], at: dt.datetime, days: int, judged: Mapping[str, Any],
              basis: Mapping[str, Any]) -> dict[str, Any]:
    """A look as screen.py `write_look` writes it, in PREREG-EVL-6's shape (`_look6_row`): its `looks` row (k carries
    the run and S), its detail (the issuer guard, the control, the figures beside, the lower tail, the merged
    thresholds) and `v6` (the tag, the look's k, S, p, q, p_I, alpha, the guards, the decision), with COST-7's basis."""
    decision = judged.get("decision")
    q = judged.get("q")
    v6 = {"rule": "PREREG-EVL-6", "cost": "COST-7", "basis": {"id": basis.get("id"), "night": basis.get("night")},
          "kind": "run", "n": int(n), "tag": judged.get("tag", tag("run", n)), "look": int(k), "S": judged["S"],
          "seed": judged.get("seed"), "p": judged.get("p"), "q": q, "p_issuer": judged.get("p_issuer"),
          "alpha": judged.get("alpha"), "guards": judged.get("guards"), "top14": judged.get("top14"),
          "money_a": judged.get("money_a"), "block_mean": judged.get("block_mean"), "decision": decision,
          "merged": list(merged)}
    return {
        "program": learner.id, "version": int(learner.version), "k": look_key("run", n, judged["S"]), "at": S.iso(at),
        "sessions": int(days), "n": judged.get("n"), "issuers": judged.get("issuers"), "blocks": judged["S"],
        "mean_a": judged.get("mean_a"), "mean_r": judged.get("mean_r"), "mean_a_tradable": judged.get("mean_a"),
        "p": judged.get("p"), "alpha": judged.get("alpha"), "fp_check": None, "held": 1,
        "passed": int(decision == "pass"), "why": str(judged.get("why") or "")[:400],
        "issuer": {"p": judged.get("p_issuer"), "alpha": 0.10}, "control": judged.get("control"), "skew": None,
        "beside": judged.get("beside"), "retirement": {"retire": decision == "retire", "q": q, "p_below": q},
        "merged": list(merged), "v6": v6}


def _move(store: Any, learner: Any, look: Mapping[str, Any], db: Any, now: dt.datetime) -> str | None:
    """PREREG-EVL-6 section 1.4's move of a run look, in the look's own transaction: RETIRE retires the version (for
    good); PASS moves a `learning` version to `probe`; nothing else."""
    from . import bands as BA

    decision = look["v6"].get("decision")
    at = str(look["at"])
    if decision == "retire":
        if BA.set_band(store, learner.id, int(learner.version), "retired", since=at, now=now, db=db,
                       why=f"look {look['v6']['tag']}S{look['v6']['S']} (PREREG-EVL-7 on COST-7): mean a7 < 0, q "
                           f"{float(look['v6'].get('q') or 0):.5f} <= alpha {float(look['v6'].get('alpha') or 0):.3f} "
                           "(PREREG-EVL-6 section 1.4, RETIRE)"):
            return "retired"
        return None
    if decision == "pass" and band_of(store, learner) == "learning":
        if BA.set_band(store, learner.id, int(learner.version), "probe", since=at, now=now, db=db,
                       why=f"look {look['v6']['tag']}S{look['v6']['S']} passed (PREREG-EVL-7 on COST-7, PREREG-EVL-6 "
                           "section 1.4)"):
            return "probe"
    return None


def run_one(store: Any, learner: Any, today: dt.date, *, now: dt.datetime, draws: int | None = None) -> dict[str, Any]:
    """One learner version's looks due by `today` in its current run, and the run's end at its 60th block (the module
    docstring, steps 2-4). A version not at learning, retired, waiting for its next run or refused writes nothing."""
    from . import screen as SN

    done: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    head = {"program": learner.id, "version": int(learner.version)}
    band = band_of(store, learner)
    if band != "learning":
        if band in ("probe", "sized"):
            waiting.append(head | {"k": None, "why": f"at {band}: PREREG-EVL-6 section 3's stay for COST-7's versions is "
                                                     "not judged in this tree (no real money: `gate`)"})
        return {"written": done, "waiting": waiting}
    run = runs(store, learner)[-1]
    if run["ended"] is not None:
        return {"written": done, "waiting": waiting}
    basis = C7.basis_for(store, now)
    rows = C7.record7(store, learner, before=now)
    if basis is None or rows is None:
        waiting.append(head | {"k": None, "why": "no cost_basis row before the look (section 2.2 (d))"})
        return {"written": done, "waiting": waiting}
    record = run_record(rows, run)
    if not record:
        return {"written": done, "waiting": waiting}
    on = written(store, learner, "run", run["n"])
    plan = schedule(store, record, today, waits=pending(store, learner), consumed=on["consumed"], after=on["last"],
                    horizon=final(store, learner, today, now))
    if on["S"] >= RUN_BLOCKS and plan["horizon"] is None and on["last"] is not None:
        every = blocks(covered(record, on["last"]))
        if len(every) >= RUN_BLOCKS:
            plan["horizon"] = (on["last"], every[RUN_BLOCKS - 1][0])
    if plan["stopped"] is not None:
        waiting.append(head | {"k": None, "why": plan["why"]})
    ctl_all: list[dict[str, Any]] | None = None
    ended = False
    for k, as_of, merged, s_k in plan["looks"]:
        session = C.session(store, as_of)
        cov = covered(record, as_of)
        first_blocks = {d for d, _ in blocks(cov)[:RUN_BLOCKS]}
        cov = [r for r in cov if _day(r["entry_day"]) in first_blocks]
        if ctl_all is None:
            ctl_all = C7.control7(store, learner, before=now) or []
        ctl = covered(ctl_all, as_of)
        judged = C7.judge_record(cov, ctl, program=learner.id, version=int(learner.version), tag=tag("run", run["n"]),
                                 draws=draws)
        if judged.get("decision") is None and judged.get("S") is None:
            # (no PREREG-EVL-6 screen in this tree: nothing is written, and the gate refuses the learner's buys)
            waiting.append(head | {"k": k, "why": str(judged.get("why") or "no judge")[:200]})
            return {"written": done, "waiting": waiting}
        first_entry = min(_day(r["entry_day"]) for r in record)
        look = _look_row(learner, run["n"], k, merged, session.close_at, len(C.sessions(store, first_entry, as_of)),
                         judged, basis)
        moved: list[str | None] = [None]

        def apply(db: Any, look: dict[str, Any] = look) -> None:
            db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                       (LOOK_KEY.format(program=learner.id, version=int(learner.version), k=look["k"]),
                        json.dumps(look["v6"], sort_keys=True, default=str)))
            moved[0] = _move(store, learner, look, db, now)
        if SN.write_look(store, look, apply=apply, now=now):
            done.append(head | {"k": look["k"], "look": k, "S": s_k, "merged": merged, "decision": look["v6"]["decision"],
                                "band": moved[0], "tag": look["v6"]["tag"], "held": 1, "passed": look["passed"],
                                "p": look["p"], "alpha": look["alpha"], "why": look["why"]})
        if look["v6"]["decision"] in ("pass", "retire"):
            ended = True
            break
    if not ended and plan["horizon"] is not None:
        at, last_day = plan["horizon"]
        session = C.session(store, at)
        key = END_KEY.format(program=learner.id, version=int(learner.version), n=run["n"])
        with store.tx() as db:
            cur = db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                             (key, json.dumps({"at": S.iso(session.close_at), "last_day": last_day.isoformat(),
                                               "n": run["n"], "written_at": S.iso(now)}, sort_keys=True)))
        if cur.rowcount == 1:
            done.append(head | {"k": None, "end": at.isoformat(), "why": f"run {run['n']} ended at its {RUN_BLOCKS}th "
                                                                         "block: the version stays in learning; its next "
                                                                         "run starts only when the lane's count holds it"})
    return {"written": done, "waiting": waiting}


def used(store: Any) -> dict[str, int]:
    """THE LANE'S COUNT in hundredths (section 4, PREREG-EVL-6 section 5's frozen basis): 0.13 for every seating version
    (`programs.SEATING`: every file's, the learners' and the births') and for every fresh run on record (meta
    `RUN_KEY`'s form, any program's), and, where the tree carries PREREG-EVL-6's own count (screen.py `budget6`), the
    larger of the two (the reading that charges more); plus 0.13 held for each PREREG-EVL-6 run still waiting for room
    (screen.py `waiting_runs`: an earlier file's run is drawn first). {used, waiting, budget}."""
    from . import screen as SN

    versions = sum(1 for p in P.SEATING if p.can_seat)
    fresh = int(store.db.execute("SELECT COUNT(*) FROM meta WHERE key LIKE 'evl6:run:%'").fetchone()[0])
    mine = CHARGE * (versions + fresh)
    theirs = 0
    count = getattr(SN, "budget6", None)
    if count is not None:
        theirs = int(count(store).get("used") or 0)
    waits = getattr(SN, "waiting_runs", None)
    waiting = len(waits(store)) if waits is not None else 0
    return {"used": max(mine, theirs), "waiting": CHARGE * waiting, "budget": BUDGET}


def _demoted_after(store: Any, learner: Any, since: str | None) -> str | None:
    """The time of the learner's latest move back to `learning` from a Probe stay after `since` (a pass's look), or
    None: a fresh run is due after a demotion (PREREG-EVL-6 section 3)."""
    try:
        rows = store.db.execute("SELECT band, since, written_at FROM band_history WHERE program=? AND version=? ORDER BY "
                                "id", (learner.id, int(learner.version))).fetchall()
    except Exception:  # noqa: BLE001 - no history
        return None
    seen_probe, out = False, None
    for r in rows:
        if r["band"] == "probe":
            seen_probe = True
        elif r["band"] == "learning" and seen_probe:
            out = max(str(r["since"] or ""), str(r["written_at"] or "")) or None
    if out is not None and since is not None and out <= since:
        return None
    return out


def start_runs(store: Any, now: dt.datetime, learners: Sequence[Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    """THE START OF THE LEARNERS' NEXT RUNS (section 1.10, E2), in registration order then id, after the earlier files'
    (the module docstring, step 5): each due run starts when used + every earlier waiting run + 0.13 <= 3.9, written
    once (meta `RUN_KEY`, charge 0.13) with its record's bounds; else it is REFUSED FOR GOOD (meta `NORUN_KEY`), as is a
    fourth run. Returns {started, refused}."""
    out: dict[str, list[dict[str, Any]]] = {"started": [], "refused": []}
    count = used(store)
    room = count["used"] + count["waiting"]
    close = _last_close(store, now)
    for learner in (learners if learners is not None else in_force()):
        if band_of(store, learner) != "learning":
            continue
        history = runs(store, learner)
        last = history[-1]
        ended = last.get("ended")
        if ended is None or last.get("next_refused"):
            continue
        n = last["n"] + 1
        if ended["why"] == "horizon":
            item = {"why": f"run {last['n']} reached its {RUN_BLOCKS}th block unpassed", "after_day": ended.get("last_day"),
                    "at": ended.get("at"), "after": None}
        elif ended["why"] == "pass":
            demoted = _demoted_after(store, learner, ended.get("at"))
            if demoted is None:
                continue        # (passed: at Probe; a demotion back to learning opens the next run)
            item = {"why": "demoted from its Probe stay", "after_day": None, "at": None, "after": demoted}
        else:
            continue            # (retired: no run ever again)
        head = {"program": learner.id, "version": int(learner.version), "n": n}
        if n > RUNS_MAX or room + CHARGE > BUDGET:
            why = (f"a run {n} would be due: the id's {RUNS_MAX} runs are spent" if n > RUNS_MAX else
                   f"the lane's count {room / 100:.2f} (with {count['waiting'] / 100:.2f} held for earlier waiting runs) "
                   f"cannot hold 0.13 more of {BUDGET / 100:.2f}")
            rec = {"n": n, "why": why, "at": S.iso(now), "after": item["why"]}
            cur = store.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                                   (NORUN_KEY.format(program=learner.id, version=int(learner.version), n=n),
                                    json.dumps(rec, sort_keys=True)))
            if cur.rowcount == 1:
                out["refused"].append(head | rec)
            continue
        bound = item.get("after")
        if item.get("at"):          # (a 60th block's end: no extra bound when the room holds it at that very close)
            end_close = S.parse_iso(str(item["at"]))
            if close is not None and close.close_at > end_close:
                bound = S.iso(close.close_at)
        elif bound is not None and close is not None and close.close_at > S.parse_iso(bound):
            bound = S.iso(close.close_at)
        record = {"n": n, "after_day": item.get("after_day"), "after": bound, "started": S.iso(now), "why": item["why"],
                  "charge": CHARGE / 100}
        cur = store.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                               (RUN_KEY.format(program=learner.id, version=int(learner.version), n=n),
                                json.dumps(record, sort_keys=True)))
        if cur.rowcount == 1:
            room += CHARGE
            out["started"].append(head | record)
    return out


def _last_close(store: Any, now: dt.datetime) -> C.Session | None:
    row = store.db.execute("SELECT day FROM sessions WHERE close_at<=? ORDER BY day DESC LIMIT 1", (S.iso(now),)).fetchone()
    return None if row is None else C.session(store, _day(row[0]))


def run(store: Any, today: dt.date, *, now: dt.datetime | None = None, draws: int | None = None) -> dict[str, Any]:
    """THE NIGHT'S LOOKS AND RUNS OF THE LEARNERS (the module docstring): nothing while no learner is pinned; every look
    waits while the night has no `cost_basis` row (section 2.2 (d)); then each version's looks and run end
    (`run_one`; one version's failure is its own), then the next runs (`start_runs`). {written, waiting, started,
    refused, errors}."""
    now = now or S.utc_now()
    out: dict[str, Any] = {"written": [], "waiting": [], "started": [], "refused": [], "errors": []}
    learners = in_force()
    if not learners:
        return out
    if C7.night_row(store, today) is None:
        out["waiting"] = [{"program": p.id, "version": int(p.version), "k": None,
                           "why": f"no cost_basis row for the night of {today.isoformat()} (section 2.2 (d)): every look "
                                  "and the run's end wait"} for p in learners]
        return out
    for learner in learners:
        try:
            got = run_one(store, learner, today, now=now, draws=draws)
        except Exception as exc:  # noqa: BLE001 - its looks are computed again at the next night
            out["errors"].append({"program": learner.id, "version": int(learner.version),
                                  "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue
        out["written"] += got["written"]
        out["waiting"] += got["waiting"]
    try:
        got = start_runs(store, now, learners)
    except Exception as exc:  # noqa: BLE001 - started again at the next night
        out["errors"].append({"program": None, "version": None, "error": f"start_runs: {type(exc).__name__}: "
                                                                          f"{str(exc)[:200]}"})
    else:
        out["started"], out["refused"] = got["started"], got["refused"]
    return out


# ------------------------------------------------------------------------------------------------ the money gate
def live_rows(store: Any, learner: Any) -> list[dict[str, Any]]:
    """The learner's settled, TRADABLE (the shadow's, an upper bound of COST-7's) intents of its LIVE decisions: what the
    gate counts in blocks without a cost basis (more blocks than the record can hold: the gate shuts no later)."""
    try:
        got = store.db.execute("SELECT i.event, i.cik, i.symbol, i.entry_day, i.exit_day, i.decided_at FROM intents i JOIN "
                               "learner_fits f ON f.program=i.program AND f.version=i.version AND f.day=i.entry_day JOIN "
                               "outcomes o ON o.program=i.program AND o.version=i.version AND o.event=i.event WHERE "
                               "i.program=? AND i.version=? AND f.kind='live' AND o.status='settled' AND o.tradable=1 "
                               "ORDER BY i.entry_day, i.event", (learner.id, int(learner.version))).fetchall()
    except Exception:  # noqa: BLE001 - no learner table yet: nothing live
        return []
    return [{"event": str(r["event"]), "issuer": str(r["cik"] or r["symbol"]), "entry_day": _day(r["entry_day"]),
             "exit_day": _day(r["exit_day"]), "decided_at": r["decided_at"], "tradable": 1, "a": 0.0} for r in got]


def blocked(store: Any, learner: Any) -> dict[str, str] | None:
    """Why the learner's real money buys nothing now ({kind, why}; a look or an end overdue also `since`, the entry
    session of the block that made it due), None when it may buy (the module docstring's GATE). Unreadable reads as
    blocked (fail closed)."""
    try:
        band = band_of(store, learner)
        if band == "retired":
            return {"kind": "retired", "why": "retired: no more real money (its shadow continues as a record)"}
        if band in ("probe", "sized"):
            if not STAYS_JUDGED:
                return {"kind": "no_stay_judge", "why": f"at {band}, and PREREG-EVL-6 section 3's stay of COST-7's versions "
                                                         "is not judged in this tree: no real money (fail closed)"}
            return None
        history = runs(store, learner)
        last = history[-1]
        if last.get("next_refused"):
            return {"kind": "no_run", "why": f"run {last['n'] + 1} refused for good: "
                                             f"{last['next_refused'].get('why')} (a shadow record only)"}
        if last.get("ended") is not None:
            return {"kind": "run_ended", "why": f"run {last['n']} ended ({last['ended']['why']}); run {last['n'] + 1} has "
                                                "not started"}
        record = run_record(live_rows(store, learner), last)
        on = written(store, learner, "run", last["n"])
        every = blocks(record)
        blk = every[:RUN_BLOCKS]
        events = [e for _, es in blk for e in es]
        j = max(on["consumed"]) if on["consumed"] else 0
        if j < len(LOOKS) and len(blk) >= LOOKS[j] and minimums(events, len(blk)):
            return {"kind": "look_overdue", "since": blk[LOOKS[j] - 1][0].isoformat(),
                    "why": f"run {last['n']}'s record holds {len(blk)} settled blocks and its look {j + 1} (due from block "
                           f"{LOOKS[j]}) is not written: no real money until it is (fail closed)"}
        if len(every) >= RUN_BLOCKS:
            return {"kind": "end_overdue", "since": every[RUN_BLOCKS - 1][0].isoformat(),
                    "why": f"run {last['n']}'s record holds {len(every)} settled blocks and its end at the {RUN_BLOCKS}th "
                           "is not written: no real money until it is"}
    except Exception as exc:  # noqa: BLE001 - fail closed
        return {"kind": "unreadable", "why": f"the learner's runs could not be read ({type(exc).__name__})"}
    return None


def gate(store: Any, learner: Any) -> str | None:
    got = blocked(store, learner)
    return None if got is None else got["why"]


def next_look(store: Any, learner: Any) -> dict[str, Any]:
    """THE REPORT'S NEXT LOOK of a learner (counts only, no figure of a look): {run, k, at_sessions (the blocks it falls
    due at), sessions (the run's settled live blocks, the gate's count), status}."""
    history = runs(store, learner)
    last = history[-1]
    on = written(store, learner, "run", last["n"])
    j = max(on["consumed"]) if on["consumed"] else 0
    held = blocks(run_record(live_rows(store, learner), last))[:RUN_BLOCKS]
    got = blocked(store, learner)
    status = "PREREG-EVL-6's screen on COST-7, live decisions only" if got is None else got["why"]
    return {"run": last["n"], "k": j + 1 if j < len(LOOKS) else None, "at_sessions": LOOKS[j] if j < len(LOOKS) else None,
            "sessions": len(held), "status": status[:300], "gate": None if got is None else got["kind"]}


__all__ = ["LOOKS", "RUN_BLOCKS", "MIN_EVENTS", "MIN_ISSUERS", "MIN_BLOCKS", "CHARGE", "BUDGET", "RUNS_MAX", "STAY_BASE",
           "RUN_KEY", "END_KEY", "NORUN_KEY", "LOOK_KEY", "STAYS_JUDGED", "ALARM_KINDS", "in_force", "tag", "look_key",
           "key_of", "band_of", "runs", "written", "run_record", "covered", "blocks", "minimums", "pending", "final",
           "schedule", "run_one", "used", "start_runs", "run", "live_rows", "blocked", "gate", "next_look"]
