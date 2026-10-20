"""The event lane's daily one-screen report (EVL-DESIGN "report"; PREREG-EVL-1 section 9's reporting).

For one New York day: the events recorded by family (8-K with item 2.02, other 8-K, Form 4, news) with fetched and
failed counts; the verdicts by status and their cost; each program's intents (planned / entered / skipped / exited)
entering that day and to date; its settled outcomes to date (n, issuers, sessions, mean r, mean a, mean a of the
TRADABLE events, the market direction); for a seatable program its next look and its last look's result; the gap
between the auction prints and the daily bars of the day's settled events; the expected false passes (0.10 x every
seatable version registered); the events its decisions KEPT OUT of each program's record (release 1019c: a session a
look of its group stands over is decided again for nothing, and its decision receipt lists what it left out;
PREREG-EVL-1 section 3's late share); and the receipts of the day's jobs, the missed and failed ones listed. `build`
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
    league/events/run.py `_left_out`), each event once; an event listed unjudged by one run and taken on a stored verdict
    by a later one counts as left out (`events`) only."""
    events: dict[str, set[str]] = {}
    unjudged: dict[str, set[str]] = {}
    for row in store.db.execute("SELECT job, summary FROM receipts WHERE (job LIKE 'decide-open:%' OR job LIKE "
                                "'decide-close:%') AND status IN ('ok', 'pending')"):
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
        last_out["control"] = detail.get("control")
    from .bands import bands as _bands

    v2 = SC._seating(program, version)
    left = kept_out(store, day) if left is None else left
    mine = left.get(program if int(version) == 1 else f"{program}@v{int(version)}") or {}
    held = {str(r[0]) for r in store.db.execute("SELECT event FROM intents WHERE program=? AND version=?",
                                                (program, version))}
    out_events = set(mine.get("events") or ()) - held
    return {
        "program": program, "version": version, "seatable": program in SC.SEATABLE,
        "band": _bands(store).get((program, int(version))) if v2 else None,
        "intents_today": today, "intents_all": every, "settled": settled,
        "kept_out": {"events": len(out_events), "unjudged": len(set(mine.get("unjudged") or ()) - held - out_events)},
        "settled_today": sum(1 for r in rows if r["exit_day"] == day),
        "next_look": SC.next_look_v2(store, program, version, day) if v2 else SC.next_look(store, program, version, day),
        "last_look": last_out, "held_looks": sum(1 for r in looks if r["held"]),
    }


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


def build(store: S.Store, day: dt.date, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """The day's report as data (no prices, headlines or symbols)."""
    now = now or S.utc_now()
    left = kept_out(store, day)
    programs = [program_status(store, p, v, day, left=left) for p, v in _programs(store)]
    with_rows = {p["program"] for p in programs}
    return {
        "day": day.isoformat(), "generated_at": S.iso(now), "session": C.session(store, day) is not None,
        "events": events(store, day), "verdicts": verdicts(store, day), "programs": programs,
        "registered_without_intents": [p for p in SC.SEATABLE + SC.RECORDS if p not in with_rows],
        "gaps": gaps(store, day), "expected_false_passes": SC.expected_false_passes(store),
        "jobs": jobs(store, day, now),
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.2f}%"


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
        if p["seatable"]:
            nl, ll = p["next_look"], p["last_look"]
            if nl.get("k") is None:
                nxt = "all written"
            elif "events_needed" in nl:
                nxt = (f"look {nl['k']} at {nl['events_needed']} events (now {nl['events']}, issuers {nl['issuers']}, "
                       f"blocks {nl['blocks']})")
            else:
                nxt = f"look {nl['k']} at session {nl['at_sessions']} (now {nl.get('sessions', 0)}, {nl['status']})"
            if ll is None:
                last = "none"
            else:
                last = f"look {ll['k']} " + ("PASS" if ll["passed"] else ("fail" if ll["held"] else "skipped"))
                if ll["p"] is not None:
                    last += f" p {ll['p']:.4f}/{ll['alpha']:.3f}"
                if ll.get("issuer"):
                    last += f", issuer p {ll['issuer']['p']:.4f}/{ll['issuer']['alpha']:.3f}"
            line += f"; next {nxt}; last {last}"
        lines.append(line)
    if report["registered_without_intents"]:
        lines.append("No intents yet: " + ", ".join(report["registered_without_intents"]))
    gp = report["gaps"]
    lines.append("Print vs bar: " + " | ".join(
        f"{side} n {g['n']}" + (f", mean {g['mean_bp']:+.1f} bp, size {g['mean_abs_bp']:.1f} bp" if g["n"] else "")
        for side, g in gp.items()))
    efp = report["expected_false_passes"]
    lines.append(f"Expected false passes: {efp['expected']:.1f} (0.10 x {efp['versions']} seatable versions)")
    jb = report["jobs"]
    failed = ", ".join(f"{f['job']} {S.parse_iso(f['started_at']).astimezone(C.NY):%H:%M} ET ({f['status']})"
                       for f in jb["failed"]) or "none"
    lines.append(f"Jobs: {jb['receipts']} receipts; missed: {', '.join(jb['missed']) or 'none'}; failed: {failed}")
    return "\n".join(lines)


__all__ = ["build", "render", "events", "verdicts", "program_status", "kept_out", "gaps", "jobs", "day_bounds", "FAMILIES",
           "VERDICT_STATUSES", "SESSION_JOBS", "WEEKDAY_JOBS"]
