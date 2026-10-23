"""The event lane's daily one-screen report (EVL-DESIGN "report"; PREREG-EVL-1 section 9's reporting).

For one New York day: the events recorded by family (8-K with item 2.02, other 8-K, Form 4, news) with fetched and
failed counts; the verdicts by status and their cost; each program's intents (planned / entered / skipped / exited)
entering that day and to date; its settled outcomes to date (n, issuers, sessions, mean r, mean a, mean a of the
TRADABLE events, the market direction); for a seatable program its next look and its last look's result; the gap
between the auction prints and the daily bars of the day's settled events; the expected false passes (PREREG-EVL-6
section 5: 0.13 for every version it registers or judges and every fresh run, of the lane's restated 3.9, shown three
ways with the per-version figure beside; a PREREG-EVL-6 version's runs, its per-run and per-version figures, its next
look in settled blocks and its last look's tag, S, q and issuer p; a superseded version named as a shadow record);
the events its decisions KEPT OUT of each program's record (release 1019c: a session a look of its group stands over is decided again for nothing, and its decision receipt lists
what it left out, PREREG-EVL-4's and PREREG-EVL-5's rows' own decisions `decide-close-evl4` and `decide-close-evl5`
included; PREREG-EVL-1 section 3's late share); the shadow's difference from real money by storage time (`late_rows`:
events whose row was stored after their decision, intents a later row excluded or, PREREG-EVL-5, put in a set that
skips them); PREREG-EVL-5's funnels of the day's close decision and the closes whose part for its rows failed or ran
past its own bound (`evl5`, section 6's "the report counts each row's funnel"); and the receipts of the day's jobs, the
missed and failed ones listed. `build`
returns the report as JSON-ready data, `render` as a few lines of plain text.

Licensing: Alpaca's data and Benzinga's headlines are not redistributed. Neither form carries a price, a headline, a
symbol or a document's text: only counts and summary statistics (means of returns, gaps in basis points).
Account-shown profit, Net after metered costs and the same-risk buy-and-hold (section 9) need real fills and the
House's cost meter; they are not in this store and are not reported here.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from . import calendar as C
from . import screen as SC
from . import store as S

FAMILIES = ("8-K 2.02", "8-K other", "Form 4", "news")
VERDICT_STATUSES = ("ok", "unparsed", "refused", "failed")
INTENT_CLASSES = ("planned", "entered", "skipped", "exited")
#: The design's timers (America/New_York). Session days: these jobs, at these times ("close" = the session's close
#: decision, 14 minutes before its close). Weekdays: the recorder (every 2 minutes from 06:00) and the verdicts after it.
SESSION_JOBS: dict[str, Any] = {"universe": dt.time(7, 30), "decide-open": dt.time(9, 15), "decide-close": "close",
                                "score": dt.time(20, 30), "screen": dt.time(21, 0)}
WEEKDAY_JOBS: dict[str, Any] = {"record": dt.time(6, 0), "verdicts": dt.time(6, 10)}
MISSED_AFTER = dt.timedelta(minutes=30)
UNFINISHED_AFTER = dt.timedelta(hours=2)


def _mean(xs: list[float]) -> float | None:
    return math.fsum(xs) / len(xs) if xs else None


def day_bounds(day: dt.date) -> tuple[str, str]:
    """[00:00, 24:00) New York time of `day`, as the store's UTC strings."""
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=C.NY)
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, 0), tzinfo=C.NY)
    return S.iso(start), S.iso(end)


def _family(form: str, items: str | None) -> str | None:
    if form == "4":
        return "Form 4"
    if form != "8-K":
        return None
    try:
        listed = json.loads(items or "[]")
    except ValueError:
        listed = []
    return "8-K 2.02" if "2.02" in listed else "8-K other"


def events(store: S.Store, day: dt.date) -> dict[str, Any]:
    """Events of the day (accepted / created that New York day) by family; filings fetched, failed and still listed."""
    lo, hi = day_bounds(day)
    out: dict[str, Any] = {f: {"total": 0, "fetched": 0, "failed": 0, "pending": 0} for f in FAMILIES[:3]}
    for row in store.db.execute("SELECT form, items, status FROM filings WHERE accepted_at>=? AND accepted_at<?", (lo, hi)):
        fam = _family(str(row["form"]), row["items"])
        if fam is None:
            continue
        status = str(row["status"])
        bucket = "fetched" if status == "fetched" else ("failed" if status.startswith("failed") else "pending")
        out[fam]["total"] += 1
        out[fam][bucket] += 1
    news = store.db.execute("SELECT COUNT(*), COALESCE(SUM(live), 0) FROM news WHERE created_at>=? AND created_at<?",
                            (lo, hi)).fetchone()
    out["news"] = {"total": int(news[0]), "live": int(news[1]), "backfilled": int(news[0]) - int(news[1])}
    recorded = 0
    for table in ("filings", "news"):
        recorded += int(store.db.execute(f"SELECT COUNT(*) FROM {table} WHERE received_at>=? AND received_at<?",
                                         (lo, hi)).fetchone()[0])
    out["recorded_today"] = recorded
    return out


def verdicts(store: S.Store, day: dt.date) -> dict[str, Any]:
    """Verdicts answered (or, unanswered, asked) that day, by status, with their metered cost."""
    lo, hi = day_bounds(day)
    out: dict[str, Any] = {s: {"n": 0, "usd": 0.0} for s in VERDICT_STATUSES}
    for row in store.db.execute("SELECT status, COUNT(*) AS n, COALESCE(SUM(usd), 0) AS usd FROM verdicts WHERE "
                                "COALESCE(answered_at, asked_at)>=? AND COALESCE(answered_at, asked_at)<? GROUP BY status",
                                (lo, hi)):
        status = str(row["status"])
        key = status if status in out else status.split(":")[0]
        slot = out.setdefault(key, {"n": 0, "usd": 0.0})
        slot["n"] += int(row["n"])
        slot["usd"] = round(slot["usd"] + float(row["usd"]), 6)
    return out


def _intent_class(status: str) -> str:
    return "skipped" if status.startswith("skipped") else status


def _programs(store: S.Store) -> list[tuple[str, int]]:
    seen = set(SC.program_versions(store))
    seen |= {(r[0], int(r[1])) for r in store.db.execute("SELECT DISTINCT program, version FROM looks")}
    return sorted(seen)


def kept_out(store: S.Store, day: dt.date) -> dict[str, dict[str, set[str]]]:
    """{decision key (`id`, or `id@vN` for a later version): {"events", "unjudged"}}: the event ids the finished decisions
    of the entry sessions through `day` left out of each program's record (their summaries' `kept` entries, written by
    league/events/run.py `_left_out`; PREREG-EVL-4's and PREREG-EVL-5's rows' own decisions, `decide-close-evl4` and
    `decide-close-evl5`, and the births' own,
    `decide-open-births` and `decide-close-births`, included), each event once; an event listed unjudged by one run and
    taken on a stored verdict by a later one counts as left out (`events`) only."""
    events: dict[str, set[str]] = {}
    unjudged: dict[str, set[str]] = {}
    for row in store.db.execute("SELECT job, summary FROM receipts WHERE (job LIKE 'decide-open:%' OR job LIKE "
                                "'decide-close:%' OR job LIKE 'decide-close-evl4:%' OR job LIKE 'decide-open-births:%' "
                                "OR job LIKE 'decide-close-births:%' OR job LIKE 'decide-close-evl5:%') AND status IN "
                                "('ok', 'pending')"):
        if str(row["job"]).split(":", 1)[1] > day.isoformat():
            continue
        try:
            body = json.loads(row["summary"] or "{}")
        except (TypeError, ValueError):
            continue
        kept = body.get("kept") if isinstance(body, dict) else None
        for key, entry in (kept.items() if isinstance(kept, dict) else ()):
            if isinstance(entry, dict):
                events.setdefault(str(key), set()).update(str(e) for e in entry.get("events") or [])
                unjudged.setdefault(str(key), set()).update(str(e) for e in entry.get("unjudged") or [])
    return {key: {"events": events.get(key, set()), "unjudged": unjudged.get(key, set()) - events.get(key, set())}
            for key in set(events) | set(unjudged)}


def _stored_at(store: S.Store, event: str) -> dt.datetime | None:
    """When the lane STORED an event's row (PREREG-EVL-1 section 3, the time a real-money decision reads it by, as
    league/events/book.py `_stored_before` reads it): a news article when it was read (`received_at`); a filing when its
    documents were fetched (the latest `documents.stored_at` of its raw and text documents, never before its listing,
    `received_at`), and never (the latest time there is: real money fails closed) when a document it names has no time
    on record. None when the row is not found."""
    kind, _, ident = str(event).partition(":")
    try:
        if kind == "news":
            row = store.db.execute("SELECT received_at FROM news WHERE id=?", (ident,)).fetchone()
            return None if row is None else S.parse_iso(row["received_at"])
        if kind in ("8k", "f4"):
            row = store.db.execute("SELECT received_at, raw_sha, text_sha FROM filings WHERE accession=?",
                                   (ident,)).fetchone()
            if row is None:
                return None
            when = S.parse_iso(row["received_at"])
            for sha in (row["raw_sha"], row["text_sha"]):
                if not sha:
                    continue
                doc = store.db.execute("SELECT stored_at FROM documents WHERE sha=?", (sha,)).fetchone()
                if doc is None or not doc["stored_at"]:
                    return dt.datetime.max.replace(tzinfo=dt.timezone.utc)
                when = max(when, S.parse_iso(doc["stored_at"]))
            return when
    except (TypeError, ValueError):
        return None
    return None


def late_rows(store: S.Store, program: str, version: int, day: dt.date) -> dict[str, int]:
    """THE SHADOW'S DIFFERENCE FROM REAL MONEY BY STORAGE TIME (PREREG-EVL-1 section 3; PREREG-EVL-4 section 1.3: "a row
    stored later counts in the shadow only, and the report counts the difference"): of the program's intents entering
    by `day`, those taken whose event row the lane stored after the intent's decision time (real money could not read
    it), today and to date, and those a re-decision marked `skipped:excluded` (PREREG-EVL-4: a row stored later put the
    issuer in EXCLUDED or the F8K(D) skip; real money read the rows stored before its decision) or `skipped:taken`
    (PREREG-EVL-5 section 1.3: a row stored later put the issuer in TAKEN AT D'S CLOSE BY AN EARLIER ROW, the <= 0.96 skip
    or NO NEW INFORMATION), counted under `excluded_late` too."""
    out = {"stored_late_today": 0, "stored_late": 0, "excluded_late": 0}
    for r in store.db.execute("SELECT event, decided_at, entry_day, status FROM intents WHERE program=? AND version=? AND "
                              "entry_day<=?", (program, version, day.isoformat())):
        status = str(r["status"])
        if status in ("skipped:excluded", "skipped:taken"):
            out["excluded_late"] += 1
            continue
        if status.startswith("skipped"):
            continue
        when = _stored_at(store, str(r["event"]))
        try:
            late = when is not None and when > S.parse_iso(r["decided_at"])
        except (TypeError, ValueError):
            late = False
        if late:
            out["stored_late"] += 1
            out["stored_late_today"] += int(r["entry_day"] == day.isoformat())
    return out


#: PREREG-EVL-8 SECTION 10 (F8, THE NO-LEADERBOARD TEST; release 1019n's second judges review): a look of this file's
#: versions names its control and that control's block count, NEVER A FIGURE OF IT. A META look's control is its POOL
#: (EVL-META-*-POOL, section 7.1: a free record built from `mrl_pool`'s members, whose mean block is an mrl_* figure no
#: report, site page or births read may carry), and a PX seat's is a free record of section 3.2 (CTRL-PX-ALL-*); so of
#: the judge's control detail ({program, mean_block, blocks, program_mean_block}) only these keys reach the report.
EIGHT_CONTROL_KEYS = ("program", "blocks")


def control_of_look(program: str, control: Any) -> Any:
    """A look's control detail as the report carries it (`program_status`): every earlier file's whole, as before; for a
    version of PREREG-EVL-8 (`programs.is_8`) only `EIGHT_CONTROL_KEYS` (its name and block count: counts only)."""
    from . import programs as P

    if not isinstance(control, Mapping) or not P.is_8(program):
        return control
    return {k: control.get(k) for k in EIGHT_CONTROL_KEYS}


def program_status(store: S.Store, program: str, version: int, day: dt.date, *,
                   left: Mapping[str, Mapping[str, set[str]]] | None = None) -> dict[str, Any]:
    today = {c: 0 for c in INTENT_CLASSES}
    every = {c: 0 for c in INTENT_CLASSES}
    for row in store.db.execute("SELECT status, entry_day FROM intents WHERE program=? AND version=? AND entry_day<=?",
                                (program, version, day.isoformat())):
        cls = _intent_class(str(row["status"]))
        every[cls] = every.get(cls, 0) + 1
        if row["entry_day"] == day.isoformat():
            today[cls] = today.get(cls, 0) + 1
    rows = [r for r in SC.settled_rows(store, program, version) if r["exit_day"] <= day]
    trad = [r for r in rows if r["tradable"]]
    anchor = min((r["exited"] for r in rows), default=None)
    bench = [float(r["b"]) for r in trad if r["b"] is not None]
    mean_r_t = _mean([float(r["r"]) for r in trad])
    late = [r["late"] for r in rows if r["late"] is not None]
    settled = {
        "n": len(rows), "issuers": len({r["issuer"] for r in rows}), "entry_sessions": len({r["entry_day"] for r in rows}),
        "sessions": len(C.sessions(store, anchor, day)) if anchor and anchor <= day else 0,
        "mean_r": _mean([float(r["r"]) for r in rows]), "mean_a": _mean([float(r["a"]) for r in rows]),
        "n_tradable": len(trad), "issuers_tradable": len({r["issuer"] for r in trad}),
        "mean_a_tradable": _mean([float(r["a"]) for r in trad]), "mean_r_tradable": mean_r_t,
        "mean_b_tradable": _mean(bench) if trad and len(bench) == len(trad) else None,
        "fallback_exits": sum(1 for r in rows if r["exited"] != r["exit_day"]),
        "late_share": (sum(1 for x in late if x) / len(late)) if late else None,
    }
    mb = settled["mean_b_tradable"]
    settled["market_share"] = (mb / mean_r_t) if (mb is not None and mean_r_t) else None
    looks = SC.look_rows(store, program, version)
    last = looks[-1] if looks else None
    last_out = None
    if last is not None:
        detail = SC.look_detail(store, program, version, int(last["k"])) or {}
        last_out = {k: last[k] for k in ("k", "held", "passed", "p", "alpha", "fp_check", "n", "issuers", "blocks", "why")}
        last_out["issuer"] = detail.get("issuer")
        last_out["control"] = control_of_look(program, detail.get("control"))
    from .bands import bands as _bands
    from .programs import BY_KEY

    v2 = SC._seating(program, version)
    prog = BY_KEY.get((program, int(version)))
    v6 = bool(prog is not None and prog.evl6)
    left = kept_out(store, day) if left is None else left
    mine = left.get(program if int(version) == 1 else f"{program}@v{int(version)}") or {}
    held = {str(r[0]) for r in store.db.execute("SELECT event FROM intents WHERE program=? AND version=?",
                                                (program, version))}
    out_events = set(mine.get("events") or ()) - held
    out = {
        "program": program, "version": version, "seatable": program in SC.SEATABLE or bool(v2),
        "band": _bands(store).get((program, int(version))) if v2 else None,
        "intents_today": today, "intents_all": every, "settled": settled,
        "kept_out": {"events": len(out_events), "unjudged": len(set(mine.get("unjudged") or ()) - held - out_events)},
        "settled_today": sum(1 for r in rows if r["exit_day"] == day),
        "next_look": _next_look(store, program, version, day, v2, v6),
        "last_look": last_out, "held_looks": sum(1 for r in looks if r["held"]),
        "late_rows": late_rows(store, program, version, day),
    }
    if prog is not None and prog.superseded6:
        # (PREREG-EVL-6 section 1.1: a superseded version is a shadow record; its PREREG-EVL-3 looks are reported and
        # move no band, D7)
        out["superseded_by"] = int(version) + 1
    if v6:
        # PREREG-EVL-6 section 5: PER RUN (the unit the goal's 15% is read in) and PER VERSION (1 - 0.87^n after n runs)
        runs = SC.runs6(store, program, version)
        detail = (SC.look_detail(store, program, version, int(last["k"])) or {}).get("v6") if last is not None else None
        if last_out is not None and detail:
            last_out["v6"] = {k: detail.get(k) for k in ("tag", "S", "q", "p_issuer", "decision", "kind", "n")}
        out["v6"] = {"runs": len(runs), "fresh_runs": len(runs) - 1, "stays": len(SC.stays6(store, program, version)),
                     "per_run": SC.V6_CHARGE, "per_version": round(1 - (1 - SC.V6_CHARGE) ** len(runs), 3)}
    return out


def gaps(store: S.Store, day: dt.date) -> dict[str, Any]:
    """The day's settled events (scheduled exit that day): their auction prints against the same day's raw SIP daily
    bar (entry: the bar's open or close; exit: the bar's close), in basis points: count, signed mean, mean size."""
    out: dict[str, Any] = {}
    sql = ("SELECT i.symbol, i.entry_day, i.entry_at, i.exit_day, i.exit_at FROM outcomes o JOIN intents i ON "
           "i.program=o.program AND i.version=o.version AND i.event=o.event WHERE o.status='settled' AND i.exit_day=?")
    pairs: dict[str, list[float]] = {"entry": [], "exit": []}
    for r in store.db.execute(sql, (day.isoformat(),)):
        for side, d, kind in (("entry", r["entry_day"], r["entry_at"]), ("exit", r["exit_day"], r["exit_at"])):
            mark = store.db.execute("SELECT px FROM marks WHERE symbol=? AND day=? AND label=?",
                                    (r["symbol"], d, kind)).fetchone()
            bar = store.db.execute("SELECT o, c FROM bars WHERE symbol=? AND day=? AND adj='raw'",
                                   (r["symbol"], d)).fetchone()
            ref = None if bar is None else bar["o" if kind == "open" else "c"]
            if mark is not None and mark["px"] and ref:
                pairs[side].append((float(mark["px"]) / float(ref) - 1.0) * 1e4)
    for side, xs in pairs.items():
        out[side] = {"n": len(xs), "mean_bp": _mean(xs), "mean_abs_bp": _mean([abs(x) for x in xs])}
    return out


def jobs(store: S.Store, day: dt.date, now: dt.datetime) -> dict[str, Any]:
    """The day's receipts by job; the expected jobs with no receipt once their time + 30 minutes has passed (missed);
    receipts that ended in anything but `ok`, or still run after 2 hours (failed)."""
    lo, hi = day_bounds(day)
    receipts = [dict(r) for r in store.db.execute("SELECT * FROM receipts WHERE started_at>=? AND started_at<? ORDER BY id",
                                                  (lo, hi))]
    by_job: dict[str, dict[str, int]] = {}
    failed = []
    for r in receipts:
        slot = by_job.setdefault(str(r["job"]), {"n": 0, "ok": 0, "failed": 0})
        slot["n"] += 1
        status = str(r["status"] or "")
        if status == "ok":
            slot["ok"] += 1
        elif status == "running" and r["finished_at"] is None and S.parse_iso(r["started_at"]) + UNFINISHED_AFTER > now:
            pass
        else:
            slot["failed"] += 1
            failed.append({"job": r["job"], "started_at": r["started_at"],
                           "status": status if status != "running" else "unfinished"})
    session = C.session(store, day)
    expected: dict[str, dt.datetime] = {}
    if day.weekday() < 5:
        for job, at in WEEKDAY_JOBS.items():
            expected[job] = dt.datetime.combine(day, at, tzinfo=C.NY)
    if session is not None:
        for job, at in SESSION_JOBS.items():
            expected[job] = session.close_decide if at == "close" else dt.datetime.combine(day, at, tzinfo=C.NY)

    def ran(job: str) -> bool:
        return any(str(r["job"]) == job or str(r["job"]).startswith(job + ":") for r in receipts)
    missed = sorted(job for job, at in expected.items() if at + MISSED_AFTER <= now and not ran(job))
    return {"receipts": len(receipts), "by_job": by_job, "missed": missed, "failed": failed}


def evl5(store: S.Store, day: dt.date) -> dict[str, Any] | None:
    """PREREG-EVL-5 (section 6: "the report counts each row's funnel"; section 1.3's two room effects are the House's
    event book's, in its decisions' summaries): {funnel: the counts its part of the day's latest finished close decision
    of `day` read (league/events/run.py `_rows_5`'s `counts`: ERN(D) -> eligible -> taken -> the <= 0.96 falls and the
    muted band; the attention issuers of P -> (i) named -> (ii) filed -> (iii) bought -> survivors -> eligible -> gaps
    read -> gap >= 1.02; the pre-pass's cut and what the close added and removed), failed: the closes of the last 45 days
    whose latest finished close decision has an `evl5_error` (its part failed or ran past its own bound: decided later
    by themselves, never traded), each with whether a `decide-close-evl5` receipt decided them since}; None before its
    registration (no programs)."""
    if not any(p.prereg == 5 for p in _registered()):
        return None
    latest: dict[str, tuple[int, str, Any]] = {}
    lo = (day - dt.timedelta(days=45)).isoformat()
    for row in store.db.execute("SELECT id, job, status, summary FROM receipts WHERE (job LIKE 'decide-close:%' OR job "
                                "LIKE 'decide-close-evl5:%') AND status IN ('ok', 'pending') ORDER BY id"):
        job = str(row["job"])
        if job.split(":", 1)[1] < lo or job.split(":", 1)[1] > day.isoformat():
            continue
        latest[job] = (int(row["id"]), str(row["status"]), row["summary"])
    funnel = None
    failed = []
    for job, (rid, _, summary) in sorted(latest.items()):
        if not job.startswith("decide-close:"):
            continue
        try:
            body = json.loads(summary or "{}")
        except (TypeError, ValueError):
            continue
        when = job.split(":", 1)[1]
        if when == day.isoformat() and isinstance(body.get("evl5"), dict):
            funnel = body["evl5"]
        if body.get("evl5_error"):
            own = latest.get(f"decide-close-evl5:{when}")
            failed.append({"day": when, "error": str(body["evl5_error"])[:160],
                           "decided_since": bool(own and own[0] > rid)})
    return {"funnel": funnel, "failed": failed, "room": room_effects(store, day)}


#: The House's event book's state beside the lane's store (`<state>/live.sqlite`, league/equity/live.py's tables).
LIVE_DB = "live.sqlite"
#: An event entry the event kind's day order line refused (league/equity/live.py `_count_refusal`), and an entry sizing
#: refused for cash, invested or loss-budget room (league/equity/sizing.py's binding caps, `_size_event`'s words).
LINE_REFUSAL = "the event kind's day order count"
ROOM_REFUSAL = re.compile(r"no whole share fits \((sleeve_cash|invested|cash|budget)\)")
#: A PREREG-EVL-5 buy that waited for the lane's own close decision of D (league/events/book.py `PART_WAIT`, the same
#: words), and a later buy that waited for the room or the line slots kept for such buys (league/equity/live.py
#: `HELD_AHEAD`): each counted when it ENDED UNSENT ("never sent", `_event_finish`'s words).
HELD_UNSENT = "waits for the lane's own close decision"
ROOM_WAIT = "wait for the lane's close decision"


def room_effects(store: S.Store, day: dt.date) -> dict[str, int] | None:
    """PREREG-EVL-5 section 1.3's TWO STATED ROOM EFFECTS on real money (counted, never prevented), read READ-ONLY from
    the House's event book beside the lane's store (`<state>/live.sqlite`): (a) `line_refused`, the buys of this file's
    rows at session `day` that the event kind's day order line refused (it refuses entries in ROOM's order, this file's
    rows first among the PREREG rows), and `exits_held`, the sales of this file's lots at `day`'s open (each kept one
    order of that day's line for its exit); (b) `open_lost`, the earlier rows' open-entry LEARNING buys at `day`'s open
    that sizing refused for cash, invested or loss-budget room while this file's overnight lots were open there (A85
    reserves the next auction's cash for Probe and Sized only). And THE COST OF THE WAIT for the lane's close decision
    (section 1.3, the earlier rows' decision first; the money review of release 1019g): `held_unsent`, this file's buys
    at `day`'s close that ended unsent while they waited for that decision (league/events/book.py `part_hold`), and
    `room_waited`, the later buys there that ended unsent waiting for the room or the line slots ROOM kept for them. None when the book's
    state is not beside the store or cannot be read."""
    path = Path(store.root).parent / LIVE_DB
    if not path.is_file():
        return None
    five = {p.id for p in _registered() if p.prereg == 5}
    try:
        db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5.0)
        try:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT e.program, e.side, e.band, e.at, i.status, i.why FROM eq_event_intents e JOIN "
                              "eq_intents i ON i.iid=e.iid WHERE e.day=?", (day.isoformat(),)).fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return None
    mine = [r for r in rows if str(r["program"]) in five]
    exits = sum(1 for r in mine if r["side"] == "sell" and r["at"] == "open")
    lost = 0
    if exits:
        lost = sum(1 for r in rows if str(r["program"]) not in five and r["side"] == "buy" and r["at"] == "open"
                   and str(r["band"] or "") == "learning" and str(r["status"]) in ("refused", "missed")
                   and ROOM_REFUSAL.search(str(r["why"] or "")))
    def unsent(r: Any, words: str) -> bool:
        why = str(r["why"] or "")
        return r["side"] == "buy" and r["at"] == "close" and str(r["status"]) == "missed" and "never sent" in why and \
            words in why
    return {"line_refused": sum(1 for r in mine if r["side"] == "buy" and LINE_REFUSAL in str(r["why"] or "")),
            "exits_held": exits, "open_lost": lost, "held_unsent": sum(1 for r in mine if unsent(r, HELD_UNSENT)),
            "room_waited": sum(1 for r in rows if str(r["program"]) not in five and unsent(r, ROOM_WAIT))}


def _registered() -> tuple[Any, ...]:
    from .programs import PROGRAMS

    return PROGRAMS


def build(store: S.Store, day: dt.date, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """The day's report as data (no prices, headlines or symbols)."""
    now = now or S.utc_now()
    left = kept_out(store, day)
    programs = [program_status(store, p, v, day, left=left) for p, v in _programs(store)]
    from .programs import is_learner

    for p in programs:      # (PREREG-EVL-7: its learners' looks are PREREG-EVL-6's on COST-7, never PREREG-EVL-3's)
        if is_learner(p["program"]):
            p["next_look"] = _learner_next(store, p["program"], p["version"])
    with_rows = {p["program"] for p in programs}
    return {
        "day": day.isoformat(), "generated_at": S.iso(now), "session": C.session(store, day) is not None,
        "events": events(store, day), "verdicts": verdicts(store, day), "programs": programs,
        "registered_without_intents": [p for p in SC.SEATABLE + SC.RECORDS if p not in with_rows],
        "gaps": gaps(store, day), "expected_false_passes": SC.expected_false_passes(store),
        "births": _births(store), "jobs": jobs(store, day, now), "evl5": evl5(store, day),
        "settle": settle_pace(store, day), "fill_rates": _fill_rates(store, day), "eight": _eight(store, day),
        "learners": _learners(store, day),
    }


def _eight(store: S.Store, day: dt.date) -> dict[str, Any] | None:
    """PREREG-EVL-8's PX and META blocks (its section 10), COUNTS ONLY (league/events/px.py and meta.py
    `report_lines`), and the lane's expected false passes three ways for its versions (league/events/screen8.py
    `charges`); None while it registers nothing. No record's, placebo's, panel's or sub-rule's figure."""
    from . import meta as MT
    from . import programs as P
    from . import px as PXL
    from . import screen8 as S8

    if not P.registers_8():
        return None
    try:
        return {"px": PXL.report_lines(store, store.root, day), "meta": MT.report_lines(store, day),
                "charges": S8.charges(store), "late": late_passes_8(store, day), "mechanism": S8.one_mechanism(store),
                "done_beside": done_beside(store)}
    except Exception as exc:  # noqa: BLE001 - the report is read whatever this says
        return {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}


#: PREREG-EVL-8's late passes of the book (league/equity/live.py `EIGHT_PASSES`), by auction.
EIGHT_PASSES = ("open-px8", "close-px8", "close-meta8")


def late_passes_8(store: S.Store, day: dt.date) -> dict[str, Any] | None:
    """PREREG-EVL-8 section 4.6 and 10: THE AUCTIONS OF D WHOSE LATE PASS DID NOT COME INSIDE THE WINDOW, from the book's
    own rows (`<state>/live.sqlite` `eq_event_decisions`, read-only; the state root is the lane's store's parent): {pass:
    "planned" | "failed" | "not come"}; None with no live.sqlite (no book on this House). Counts only."""
    path = Path(store.root).parent / "live.sqlite"
    if not path.exists():
        return None
    try:
        db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5.0)
        try:
            rows = {str(r[0]): str(r[1]) for r in db.execute(
                "SELECT at, status FROM eq_event_decisions WHERE day=? AND at IN (?, ?, ?)", (day.isoformat(), *EIGHT_PASSES))}
        finally:
            db.close()
    except sqlite3.Error:
        return None
    return {k: ("planned" if rows.get(k) == "done" else rows.get(k) or "not come") for k in EIGHT_PASSES}


def done_beside(store: S.Store) -> dict[str, Any] | None:
    """PREREG-EVL-8 section 10 (the red team's `rt_done_beta`): BESIDE Done's issuer-block bound (league/events/done.py,
    the owner's, unchanged), the same 95% two-sided bound of the counted events' per-event raw return with SESSION
    blocks, and the MARKET-DIRECTION SHARE (the benchmarks' summed return b over the events' summed r): a long-only
    book's issuer-block bound is carried by the market's direction. None before any counted event."""
    from . import done as DN

    rows = []
    for r in DN.counted(store)["counted"]:
        if r.get("r") is None:
            continue
        row = dict(r)
        if not row.get("entry_day"):
            got = store.db.execute("SELECT entry_day FROM intents WHERE program=? AND version=? AND event=?",
                                   (row["program"], int(row["version"]), str(row["event"]))).fetchone()
            if got is None:
                continue
            row["entry_day"] = got[0]
        rows.append(row)
    if not rows:
        return None
    got = SC.bootstrap_bounds(rows, "session", DN.LEVEL, DN.DRAWS, SC.seed_of("PREREG-EVL-8|done-beside|session"))
    sum_r = math.fsum(float(r["r"]) for r in rows)
    b = [float(r["b"]) for r in rows if r.get("b") is not None]
    share = None if not b or sum_r == 0 else round(math.fsum(b) / sum_r, 4)
    return {"n": len(rows), "sessions": got["groups"], "lower": got["lower"], "upper": got["upper"],
            "direction_share": share}


def settle_pace(store: S.Store, night: dt.date) -> dict[str, Any] | None:
    """THE SETTLE-PACE LINE (release 1019i, PREREG-EVL-8's harness plan H1, the batched score): the night's score passes
    (receipts `score` whose summary's `day` is the session `night`, league/events/house.py `_score`) added up: passes,
    whether the last finished the night (`complete`), intents tried, settled, skipped, waiting and failed, the passes'
    seconds and the settlements a minute over them (`pace`), the batched passes, the gateway requests by kind (bars,
    trades, other), the parity night's flags (checked, equal: counts only) and whether THE PARITY LATCH stands
    (league/events/score.py `latched`: a flag 0 turned the batched score off). None when no pass of the night is on
    record."""
    passes = []
    for r in store.db.execute("SELECT status, summary FROM receipts WHERE job='score' ORDER BY id"):
        try:
            summary = json.loads(r["summary"] or "{}")
        except ValueError:
            continue
        if isinstance(summary, dict) and summary.get("day") == night.isoformat():
            passes.append((str(r["status"] or ""), summary))
    if not passes:
        return None
    out: dict[str, Any] = {"passes": len(passes), "complete": passes[-1][0] == "ok",
                           "batched": sum(1 for _, x in passes if x.get("batched")),
                           "requests": {"bars": 0, "trades": 0, "other": 0}, "parity": {"checked": 0, "equal": 0},
                           "seconds": 0.0}
    for key in ("due", "settled", "skipped", "waiting", "errors"):
        out[key] = sum(int(x.get(key) or 0) for _, x in passes if isinstance(x.get(key), (int, float)))
    for _, x in passes:
        out["seconds"] += float(x.get("seconds") or 0.0)
        for kind, n in (x.get("requests") or {}).items():
            if kind in out["requests"]:
                out["requests"][kind] += int(n or 0)
        for kind in ("checked", "equal"):
            out["parity"][kind] += int((x.get("parity") or {}).get(kind) or 0)
    out["seconds"] = round(out["seconds"], 1)
    out["pace"] = round(out["settled"] / (out["seconds"] / 60.0), 1) if out["seconds"] > 0 else None
    from . import score as SCO

    out["latched"] = SCO.latched(store) is not None
    return out


def _fill_rates(store: S.Store, day: dt.date) -> dict[str, Any] | None:
    """The attempts ledger's fill-rate lines (release 1019i; league/events/attempts.py `fill_rates`), None without it."""
    from . import attempts as AT

    try:
        return AT.fill_rates(store, day)
    except Exception as exc:  # noqa: BLE001 - the report is read whatever this says
        return {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}


def _learner_next(store: S.Store, program: str, version: int) -> dict[str, Any]:
    """A learner's next look as the report reads it (league/events/judge7.py `next_look`): its current run, the next
    look's threshold in blocks (PREREG-EVL-6's 22, 25, 30, 35, 40, 50, 60), the run's settled blocks over its LIVE
    decisions' picks only (never a catch-up's), and what holds its real money when something does (the gate's why).
    Counts only."""
    from . import judge7 as J7
    from .programs import BY_KEY

    prog = BY_KEY.get((program, int(version)))
    try:
        if prog is None:
            raise LookupError(f"{program} v{version} is in no registry")
        return J7.next_look(store, prog)
    except Exception as exc:  # noqa: BLE001 - the report is read whatever this says
        return {"k": None, "at_sessions": None, "sessions": 0, "status": f"unreadable ({type(exc).__name__})"}


#: How many sessions back the learners' lost live parts are counted (release 1019m, `_parts_lost`).
PARTS_SESSIONS = 10


def _parts_lost(store: S.Store, day: dt.date, line: Mapping[str, Any]) -> dict[str, Any] | None:
    """RELEASE 1019m (the independent review, A139): a learner's LIVE PARTS that expired or failed over the last
    `PARTS_SESSIONS` sessions to `day` (league/events/learner.py `PART_KEY`), each beside the House's own decision of the
    auction it ran after (`house_receipt`: the seconds from its start to its finish), since the part's bound is what the
    House's run leaves of the task's (120 s at the close, never past the task's bound less `EVL5_FINISH`): a slow House
    decision starves the part, the decision is then written 'late', and section 1.7 keeps a late decision out of the
    judged record. Receipts' times only (no outcome); None for a learner with no session on record."""
    from . import learner as LR
    from .programs import BY_KEY

    prog = BY_KEY.get((str(line.get("program")), int(line.get("version") or 0)))
    if prog is None:
        return None
    days = [d.day for d in C.previous(store, day, PARTS_SESSIONS - 1)] + ([day] if C.session(store, day) else [])
    lost: list[dict[str, Any]] = []
    for d in days:
        raw = store.meta(LR.PART_KEY.format(program=prog.id, version=prog.version, day=d.isoformat()))
        if raw is None:
            continue
        try:
            status = str(json.loads(raw).get("status") or "unreadable")
        except (TypeError, ValueError, AttributeError):
            status = "unreadable"
        house = LR.house_receipt(store, prog, d)
        secs = None
        if house is not None and house.get("started_at") and house.get("finished_at"):
            secs = round((S.parse_iso(str(house["finished_at"])) - S.parse_iso(str(house["started_at"]))).total_seconds())
        lost.append({"day": d.isoformat(), "status": status, "house_s": secs})
    return {"sessions": len(days), "lost": len(lost), "parts": lost}


def _learners(store: S.Store, day: dt.date) -> list[dict[str, Any]]:
    """PREREG-EVL-7's learner lines (league/events/learner.py `report_lines`): each learner's decision of the day, its
    candidates, picks and training rows (counts only: no fitted figure reaches the report); [] while none is pinned.
    Release 1019m: each line also counts the learner's live parts lost to their bound or a failure (`_parts_lost`)."""
    from . import learner as LR

    try:
        lines = LR.report_lines(store, day)
    except Exception as exc:  # noqa: BLE001 - the report is read whatever this says
        return [{"error": f"{type(exc).__name__}: {str(exc)[:120]}"}]
    for line in lines:
        try:
            got = _parts_lost(store, day, line)
        except Exception as exc:  # noqa: BLE001 - the report is read whatever this says
            got = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        if got is not None:
            line["parts_lost"] = got
    return lines


def _parts_text(got: Mapping[str, Any] | None) -> str:
    """The learners' line's tail for `_parts_lost` ("" with none lost)."""
    if not got:
        return ""
    if "error" in got:
        return f"; live parts lost: unreadable ({got['error']})"
    if not got.get("lost"):
        return ""
    each = ", ".join(f"{p['day']} {p['status']} (House run {p['house_s'] if p['house_s'] is not None else '?'} s)"
                     for p in got.get("parts") or [])
    return (f"; live parts lost {got['lost']} of the last {got['sessions']} sessions, out of the judged record "
            f"(section 1.7): {each}")


def _births(store: S.Store) -> dict[str, Any]:
    """R3's births (league/events/births.py `summary`): registered (seatable, records) and the last night's candidates."""
    from . import births as BI

    try:
        return BI.summary(store)
    except Exception as exc:  # noqa: BLE001 - the report is read whatever this says
        return {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.2f}%"


def _next_look(store: S.Store, program: str, version: int, day: dt.date, v2: bool, v6: bool = False) -> dict[str, Any]:
    """A program's next look: PREREG-EVL-8's versions by their own judge (league/events/screen8.py `next_look`, S_k
    blocks), PREREG-EVL-6's by its screen (`screen.next_look6`), every other as before."""
    from . import programs as P

    prog = P.BY_KEY.get((program, int(version)))
    if prog is not None and P.is_8(prog) and prog.can_seat:
        from . import screen8 as S8

        got = S8.next_look(store, prog, day)
        if got.get("k") is None:
            return got
        return {"k": got["k"], "at_sessions": got["blocks_needed"], "sessions": got["blocks"], "status": got["status"]}
    if v6:
        return SC.next_look6(store, program, version, day)
    return SC.next_look_v2(store, program, version, day) if v2 else SC.next_look(store, program, version, day)


def render(report: Mapping[str, Any]) -> str:
    """The report as a few lines of plain text (counts and summary statistics only)."""
    ev, vd = report["events"], report["verdicts"]
    gen = S.parse_iso(report["generated_at"]).astimezone(C.NY)
    lines = [f"EVL {report['day']} ({'session' if report['session'] else 'no session'}; as of {gen:%H:%M} ET)"]
    fam = [f"{f} {ev[f]['total']} (fetched {ev[f]['fetched']}, failed {ev[f]['failed']}, pending {ev[f]['pending']})"
           for f in FAMILIES[:3]]
    fam.append(f"news {ev['news']['total']} (live {ev['news']['live']})")
    lines.append("Events: " + " | ".join(fam) + f"; recorded today {ev['recorded_today']}")
    lines.append("Verdicts: " + " | ".join(f"{s} {v['n']} ${v['usd']:.2f}" for s, v in vd.items()))
    for x in report.get("learners") or []:     # (PREREG-EVL-7: counts only)
        from . import learner as LR

        got = LR.render_lines([x]) if "error" not in x else [f"Learners: {x['error']}"]
        if got and "error" not in x:
            got[-1] += _parts_text(x.get("parts_lost"))      # (release 1019m: the live parts lost, `_parts_lost`)
        lines.extend(got)
    for p in report["programs"]:
        t, st = p["intents_today"], p["settled"]
        today = "/".join(str(t.get(c, 0)) for c in INTENT_CLASSES)
        line = (f"{p['program']} v{p['version']}{'' if p['seatable'] else ' (record)'}: today p/e/s/x {today}; settled "
                f"n {st['n']} (tradable {st['n_tradable']}), issuers {st['issuers']}, sessions {st['sessions']}, "
                f"r {_pct(st['mean_r'])}, a {_pct(st['mean_a'])}, a tradable {_pct(st['mean_a_tradable'])}")
        if p.get("band"):
            line += f"; band {p['band']}"
        ko = p.get("kept_out") or {}
        if ko.get("events") or ko.get("unjudged"):
            line += f"; kept out {ko.get('events', 0)}" + (f" (+{ko['unjudged']} unjudged)" if ko.get("unjudged") else "")
        lr = p.get("late_rows") or {}
        if lr.get("stored_late") or lr.get("excluded_late"):
            line += (f"; stored after its decision {lr.get('stored_late', 0)} (today {lr.get('stored_late_today', 0)}), "
                     f"excluded by a later row {lr.get('excluded_late', 0)}")
        if p.get("superseded_by"):
            line += f"; superseded by v{p['superseded_by']} (PREREG-EVL-6: a shadow record, its looks move no band)"
        if p["seatable"]:
            nl, ll = p["next_look"], p["last_look"]
            if nl.get("k") is None:
                nxt = "all written" if "status" not in nl or nl["status"] == "all looks written" else nl["status"]
            elif "blocks_needed" in nl:      # (PREREG-EVL-6: looks counted in settled session blocks, by run or stay)
                nxt = (f"{nl['kind']} {nl['n']} look {nl['k']} at {nl['blocks_needed']} blocks (now {nl['blocks']}, "
                       f"events {nl['events']}, issuers {nl['issuers']})")
            elif "events_needed" in nl:
                nxt = (f"look {nl['k']} at {nl['events_needed']} events (now {nl['events']}, issuers {nl['issuers']}, "
                       f"blocks {nl['blocks']})")
            else:
                nxt = f"look {nl['k']} at session {nl['at_sessions']} (now {nl.get('sessions', 0)}, {nl['status']})"
            if ll is None:
                last = "none"
            elif ll.get("v6"):
                d6 = ll["v6"]
                verdict = {"pass": "PASS", "retire": "RETIRE"}.get(str(d6.get("decision")), "fail")
                last = f"look {d6.get('tag') or ''}S{d6.get('S')} {verdict}"
                if ll["p"] is not None:
                    last += f" p {ll['p']:.4f}/{ll['alpha']:.3f}, q {float(d6.get('q') or 0):.4f}"
                if d6.get("p_issuer") is not None:
                    last += f", issuer p {float(d6['p_issuer']):.4f}/{SC.V6_ISSUER_P:.2f}"
            else:
                last = f"look {ll['k']} " + ("PASS" if ll["passed"] else ("fail" if ll["held"] else "skipped"))
                if ll["p"] is not None:
                    last += f" p {ll['p']:.4f}/{ll['alpha']:.3f}"
                if ll.get("issuer"):
                    last += f", issuer p {ll['issuer']['p']:.4f}/{ll['issuer']['alpha']:.3f}"
            line += f"; next {nxt}; last {last}"
            if p.get("v6"):
                v6 = p["v6"]
                line += (f"; runs {v6['runs']} (each {v6['per_run']:.2f} worst plausible), per version "
                         f"{v6['per_version']:.2f}")
        lines.append(line)
    if report["registered_without_intents"]:
        lines.append("No intents yet: " + ", ".join(report["registered_without_intents"]))
    gp = report["gaps"]
    lines.append("Print vs bar: " + " | ".join(
        f"{side} n {g['n']}" + (f", mean {g['mean_bp']:+.1f} bp, size {g['mean_abs_bp']:.1f} bp" if g["n"] else "")
        for side, g in gp.items()))
    efp = report["expected_false_passes"]
    # PREREG-EVL-6 section 5: THREE WAYS (this file's count at 0.13 a version or run, the base model's 0.03, the
    # stresses' worst 0.17) and the per-version figure beside them (0.24 within 120 sessions at the worst plausible cell)
    line = (f"Expected false passes: {efp['expected']:.2f} ({efp.get('charge', 0.13):.2f} x {efp['versions']} versions "
            f"and {efp.get('runs', 0)} fresh runs; base {efp.get('base', 0):.2f}, stresses' worst "
            f"{efp.get('stress', 0):.2f}) of the lane's restated {efp['budget']:.1f} (PREREG-EVL-6 section 5; "
            f"{efp['left']:.2f} left, {efp.get('waiting', 0)} runs waiting); per version "
            f"{efp.get('per_version', 0.24):.2f} within 120 sessions")
    lines.append(line)
    e5 = report.get("evl5") or {}
    if e5.get("funnel") or e5.get("failed") or any((e5.get("room") or {}).values()):
        fu = e5.get("funnel") or {}
        line = ("PREREG-EVL-5: ERN(D) " + "/".join(str(fu.get(k, 0)) for k in ("ern_issuers", "ern_eligible", "taken",
                                                                              "falls", "muted"))
                + " (issuers/eligible/taken/falls/muted); attention " + "/".join(
                    str(fu.get(k, 0)) for k in ("attention", "named", "filed", "bought", "survivors",
                                                "survivors_eligible", "gaps_read", "gap_pass"))
                + " (issuers/(i)/(ii)/(iii)/left/eligible/gaps/>=1.02)")
        pre = fu.get("pre") or {}
        if pre:
            line += f"; pre-pass cut {pre.get('cut')}, +{pre.get('added', 0)}/-{pre.get('removed', 0)} at the close"
        room = e5.get("room") or {}
        if room:
            line += (f"; room: line refused {room.get('line_refused', 0)}, exits held {room.get('exits_held', 0)}, "
                     f"earlier open buys lost {room.get('open_lost', 0)}, unsent waiting for the close decision "
                     f"{room.get('held_unsent', 0)} (later buys {room.get('room_waited', 0)})")
        if e5.get("failed"):
            line += "; part failed: " + ", ".join(f"{x['day']}{' (decided since)' if x['decided_since'] else ''}"
                                                   for x in e5["failed"][-5:])
        lines.append(line)
    bi = report.get("births") or {}
    if bi.get("registered") or bi.get("last_night") or bi.get("last_call"):
        night = bi.get("last_night") or {}
        call = bi.get("last_call") or {}
        # (release 1019h's fix round: the architect's last call, its status, cost and seconds, so a night whose call
        # was lost or cut, or that took long, is read here, beside the receipt's `unanswered`)
        lines.append(f"Births: {bi.get('registered', 0)} registered ({bi.get('seatable', 0)} seatable, "
                     f"{bi.get('records', 0)} records); last night {night.get('night') or 'none'}: "
                     + ", ".join(f"{k} {v}" for k, v in sorted(night.items()) if k not in ("night", "usd"))
                     + f"; model ${float(night.get('usd') or 0):.2f}"
                     + (f"; last call {call.get('night')} {call.get('status')} ${float(call.get('usd') or 0):.4f} in "
                        f"{call.get('seconds')} s" if call else ""))
    pace = report.get("settle")
    if pace:
        # (release 1019i: the batched score's settle pace; the parity night's flags, counts only)
        rq = pace.get("requests") or {}
        line = (f"Score: {pace['settled']} settled, {pace['skipped']} skipped, {pace['waiting']} waiting of "
                f"{pace['due']} tried in {pace['passes']} passes ({pace['batched']} batched), {pace['seconds']:.0f} s"
                + (f", {pace['pace']:.1f} a minute" if pace.get("pace") is not None else "")
                + f"; requests: bars {rq.get('bars', 0)}, trades {rq.get('trades', 0)}"
                + ("" if pace.get("complete") else "; the night is not complete"))
        par = pace.get("parity") or {}
        if par.get("checked"):
            line += f"; parity {par['equal']} of {par['checked']} equal"
        if pace.get("latched"):
            line += "; THE BATCHED SCORE IS OFF: a parity flag 0 latched it (score-unlatch once explained)"
        lines.append(line)
    fr = report.get("fill_rates")
    if fr and fr.get("auctions"):
        # (release 1019i: the attempts ledger, by auction over the last 3 and 20 sessions)
        parts = []
        for auction in ("open", "close"):
            by = fr["auctions"].get(auction) or {}
            short, long_ = by.get("3") or {}, by.get("20") or {}
            parts.append(f"{auction} {_rate(short)} (3) / {_rate(long_)} (20), venue cancels "
                         f"{short.get('venue_cancels', 0)}/{short.get('buy_orders', 0)}, re-sends {short.get('resent', 0)}, "
                         f"unsent {short.get('unsent', 0)}")
        lines.append("Fills (attempts ledger): " + " | ".join(parts))
    e8 = report.get("eight")
    if e8:
        lines.extend(_eight_lines(e8))
    jb = report["jobs"]
    failed = ", ".join(f"{f['job']} {S.parse_iso(f['started_at']).astimezone(C.NY):%H:%M} ET ({f['status']})"
                       for f in jb["failed"]) or "none"
    lines.append(f"Jobs: {jb['receipts']} receipts; missed: {', '.join(jb['missed']) or 'none'}; failed: {failed}")
    return "\n".join(lines)


def _eight_lines(e8: Mapping[str, Any]) -> list[str]:
    """PREREG-EVL-8's two lines and its charges (counts only)."""
    if e8.get("error"):
        return [f"PREREG-EVL-8: not read ({e8['error']})"]
    px, meta, ch = e8.get("px") or {}, e8.get("meta") or {}, e8.get("charges") or {}
    progs = px.get("programs") or {}
    seats = "; ".join(f"{k} " + "/".join(f"{s} {n}" for s, n in sorted(v.items())) for k, v in sorted(progs.items()))
    basis = px.get("basis_bp") or {}
    bline = ", ".join(f"{side} n {b['n']} mean {b['mean']:.1f} p90 {b['p90']:.1f} bp" for side, b in basis.items() if b)
    lines = [f"PX: N_U {px.get('N_U')}, FLAGGED {_pct(px.get('flagged_share'))}, premarket {_pct(px.get('premarket_share'))}"
             f", panel rows {px.get('panel_rows')}, decided open {px.get('decided_o1')} / close {px.get('decided_on')}, runs "
             + "/".join(f"{k} {v}" for k, v in sorted((px.get("runs") or {}).items()))
             + f", requests {px.get('requests')} ({px.get('plan_minutes')} min of the plan), pivot count "
             f"{px.get('pivot_count')}, placebos passed {px.get('placebos_passed')}, canary {px.get('canary')}"
             + (f"; {seats}" if seats else "") + (f"; basis {bline}" if bline else "")]
    parts = []
    for pid, m in sorted((meta or {}).items()):
        if m is None:
            parts.append(f"{pid} no decision")
        else:
            parts.append(f"{pid} {m.get('kind')}/{m.get('status')}: members {m.get('members')}, eligible "
                         f"{m.get('eligible')}, picks {m.get('picks')}, imputed {m.get('imputed')}, decided live "
                         f"{_pct(m.get('live_share'))} of the run's sessions")
    lines.append("META: " + ("; ".join(parts) if parts else "none"))
    if ch:
        lines.append(f"PREREG-EVL-8 expected false passes: {ch.get('count'):.2f} (0.13 a version or run), base model "
                     f"{ch.get('base'):.2f}, stresses' worst {ch.get('stress'):.2f}; per version PX "
                     f"{(ch.get('per_version') or {}).get('px')}, META {(ch.get('per_version') or {}).get('meta')}")
    late = e8.get("late")
    if late:
        lines.append("PREREG-EVL-8 late passes: " + ", ".join(f"{k} {v}" for k, v in late.items())
                     + f"; PX auctions lost to a late morning pass {px.get('auctions_lost_am')}")
    mech = e8.get("mechanism") or {}
    if mech.get("count"):
        lines.append(f"PREREG-EVL-8 one mechanism beside Done's >= 3 programs: {mech['count']} pair(s) "
                     + "; ".join("+".join(p) for p in mech.get("pairs") or []))
    beside = e8.get("done_beside")
    if beside:
        lines.append(f"Beside Done's issuer-block bound: session blocks [{beside['lower']:+.4f}, {beside['upper']:+.4f}] "
                     f"over {beside['sessions']} sessions, n {beside['n']}, market-direction share "
                     f"{beside.get('direction_share')}")
    return lines


def _rate(counts: Mapping[str, Any]) -> str:
    rate = counts.get("fill_rate")
    sent = int(counts.get("buys_sent") or 0)
    return f"{counts.get('buys_filled', 0)}/{sent}" + ("" if rate is None else f" {rate * 100:.0f}%")


__all__ = ["build", "render", "events", "verdicts", "program_status", "kept_out", "late_rows", "gaps", "jobs",
           "day_bounds", "FAMILIES", "VERDICT_STATUSES", "SESSION_JOBS", "WEEKDAY_JOBS", "evl5", "room_effects",
           "settle_pace"]
