#!/usr/bin/env python3
"""Replay the research gate's F2/X2 rules (Sept 25, 2026) over the sessions a ledger actually ran.

    python3 scripts/gate_replay.py LEDGER [--hours 24] [--idle barren|off|clock] [--no-parity]
                                          [--skip-practice book.fill,book.settle] [--throttle-research] [--json]

Read-only (sqlite `mode=ro`), standard library plus `league.research_gate`'s own `refusal_class` and
`lesson_arm`. The window is the last `--hours` before the ledger's newest row. For every research
session that finished in the window it asks: would `clock_runs: real_positions` (rules 9-12 of
league/research_gate.py) have run it? It prints, by the reason the session ran under the gate of the
day (`run:<trigger>`, `sample:<reason>`, `refusal_prompt` for the House's fast path, `resume` for a
saved session), how many ran and would have run, with their candidates, adoptions or forks within ten
minutes, and dollars (the summary's `cost_usd`).

It is an approximation, and it says where:

- State is rebuilt from the ledger: an agent is on real money when its latest wake before the session
  was on `kalshi` or `alpaca`; it holds a position or a working order when that wake did something or
  held something (no `barren`/`shut` count on it); its idle count is the wake's `barren`.
- Outcomes exist only for sessions that ran. A session the new rules skip is taken to have happened as
  far as the abstention streak goes (its outcome is unknown otherwise), but not for the heartbeat, the
  barren count or the refusal keys, which only a run moves.
- The clock's interval is estimated per agent as the median gap between its gate decisions.
- Samples are not replayed row by row: the new rule draws at most once per `sample_hours` window per
  agent, so the expected samples are 10% of the (agent, 6-hour) windows in which the agent had a skip,
  priced at the day's own sampled sessions' mean cost and candidate rate.
- Rung 0 (whose clock the rules keep, unpaused and unlocked) is not visible on the ledger rows read
  here; at T0 three agents were in the replay band.
- A paused agent (rule 10) runs on news of its program (`PAUSE_NEWS`) and on its own trading
  (`PAUSE_DAILY`) once a UTC day; an active forward block can wake it where the gate of the day's
  lock did not, and those sessions never ran, so they are not here (at most one a paused agent a day).
- `--skip-practice` (Y, rule 13): those trigger kinds are taken out of a practice agent's triggers
  before the pause's filter, as `ResearchGate.allow` does; game.json's are `book.fill,book.settle`.
- `--throttle-research` (Y1, rule 14): the research lane throttled all day (as the T0 day's yield rows
  would have had it from their first hour): a practice agent's session within twice its estimated
  interval (never past a day) of its last is held. A held session would have run later, with what it
  waited for, and that session is not here: the throttle's `would` is a lower bound.
- A session the new rules would add is not in `would`: the only ones are a teacher's lesson waking an
  agent the gate of the day did not match (`lessons.named_in_arm` is their upper bound) and the new
  sample draws (`samples.expected`).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from league.research_gate import PAUSE_DAILY, PAUSE_NEWS, lesson_arm, lesson_terms, lesson_words, refusal_class  # noqa: E402
from league.ledger import Entry  # noqa: E402

REAL = ("kalshi", "alpaca")
KINDS = ("research.gate", "agent.research", "book.refused", "agent.woke", "book.fill", "agent.born", "playbook.entry",
         "agent.strategy", "agent.forked", "agent.died")


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _outcome(p: dict) -> str:
    reason = str(p.get("reason") or "")
    if reason.startswith("provider") or reason.startswith("tool outcome unconfirmed"):
        return "provider_failure"
    if p.get("candidate"):
        return "candidate"
    if int(p.get("trials") or 0) > 0:
        return "failed_evaluation"
    if reason in ("retired or changed", "credits"):
        return "other"
    return "abstained"


def replay(path: str, *, hours: float = 24.0, idle: str = "barren", practice_heartbeat: float = 72.0, real_heartbeat: float = 24.0,
           pause_after: int = 3, lock_after: int = 3, barren_wakes: int = 10, sample_percent: float = 10.0,
           sample_hours: float = 6.0, parity: bool = True, skip_practice: tuple[str, ...] = (),
           throttle_research: bool = False) -> dict:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    end = _epoch(db.execute("SELECT max(at) FROM ledger").fetchone()[0])
    start_at = datetime.fromtimestamp(end - hours * 3600, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    start = db.execute("SELECT min(seq) FROM ledger WHERE at >= ?", (start_at,)).fetchone()[0]
    rows = db.execute(f"SELECT seq, at, kind, agent, payload FROM ledger WHERE kind IN ({','.join('?' * len(KINDS))}) ORDER BY seq",
                      KINDS).fetchall()

    # Adoptions and forks after a session, for the yield column.
    changes: dict[str, list[float]] = defaultdict(list)
    gaps: dict[str, list[float]] = defaultdict(list)
    last_gate: dict[str, float] = {}
    for seq, at, kind, agent, payload in rows:
        if kind in ("agent.strategy", "agent.forked") and seq >= start:
            p = json.loads(payload)
            if kind == "agent.forked" or p.get("control") not in ("pause_entries", "resume_entries"):
                changes[agent].append(_epoch(at))
        elif kind == "research.gate" and seq >= start:
            t = _epoch(at)
            if agent in last_gate:
                gaps[agent].append(t - last_gate[agent])
            last_gate[agent] = t
    interval = {a: statistics.median(g) for a, g in gaps.items() if g}

    st: dict[str, dict] = defaultdict(lambda: {"gate": None, "refused": [], "streak": 0, "book": None, "acted": False, "barren": 0,
                                               "barren_seen": None, "last": None, "last_run": None, "keys": set(), "consulted": set(),
                                               "words": set(), "born": None, "lessons": 0})
    table: dict[str, Counter] = defaultdict(Counter)
    why: Counter = Counter()
    windows: set[tuple[str, int]] = set()
    sampled = Counter()
    refusals = Counter()
    lessons = Counter()
    for seq, at, kind, agent, payload in rows:
        p = json.loads(payload)
        s = st[agent]
        t = _epoch(at)
        if kind == "agent.born":
            s["born"] = t
            s["words"] = lesson_words(agent, p.get("specialty"), p.get("niche"), p.get("family"))
            continue
        if kind == "playbook.entry":
            if p.get("source") == "teacher":
                terms = lesson_terms(Entry(seq, "", kind, agent, at, True, p, "", ""))
                for name, other in st.items():
                    if other["words"] and any(w in terms for w in other["words"]):
                        other["lessons"] += 1
                        if seq >= start and not other.get("dead") and (not parity or lesson_arm(name) == "lesson"):
                            lessons["named_in_arm"] += 1
                if seq >= start:
                    lessons["teacher_lessons"] += 1
            continue
        if kind == "agent.died":
            s["dead"] = True
            continue
        if kind == "agent.woke":
            if p.get("ok"):
                s["book"] = p.get("book")
                s["barren"] = int(p.get("barren") or 0)
                s["acted"] = not p.get("barren") and not p.get("shut")
                if s["barren_seen"] is None:
                    s["barren_seen"] = s["barren"]
            continue
        if kind == "book.refused":
            reasons = p.get("reasons") or [""]
            s["refused"].append(f"{at[:10]}|{p.get('book') or ''}|{refusal_class(reasons[0] if reasons else '')}")
            if seq >= start:
                refusals["refusals"] += 1
            continue
        if kind == "research.gate":
            if p.get("decision") in ("run", "sample"):
                s["gate"] = p
                if p.get("decision") == "sample" and seq >= start:
                    sampled["sessions"] += 1
            elif seq >= start:
                windows.add((agent, int(t // (sample_hours * 3600))))
            continue
        if kind in ("agent.strategy", "agent.forked"):
            continue
        if p.get("tool") == "merton" and p.get("wrote_code"):
            s["consulted"].add(str(p.get("session")))
            continue
        if p.get("tool") != "summary":
            continue
        outcome = _outcome(p)
        run = seq < start
        paused, kept = False, []
        if seq >= start:
            g = s["gate"]
            real = s["book"] in REAL
            holds = s["acted"]
            refused = bool(s["refused"])
            new_keys = {k for k in s["refused"] if k not in s["keys"]}
            paused = not real and pause_after > 0 and s["streak"] >= pause_after
            locked = real and lock_after > 0 and s["streak"] >= lock_after
            base = max(s["last"] or 0.0, s["born"] or 0.0)
            if g is None and refused:
                source = "refusal_prompt"
                found = ["book.refused"]
            elif g is None:
                source = "resume"
                found = []
            else:
                source = f"{g.get('decision')}:{g.get('trigger') or str(g.get('reason') or '').split(':')[0]}"
                found = [str(x).split(":")[0] for x in g.get("triggers") or []]
            kept = []
            for trigger in found:
                if not real and trigger in skip_practice:
                    continue  # rule 13: a practice agent's own fills and settlements do not wake it
                if trigger == "book.refused" and not new_keys:
                    continue
                if trigger == "lesson" and (s["lessons"] == 0 or (parity and lesson_arm(agent) != "lesson")):
                    continue
                if paused and trigger not in PAUSE_NEWS and not (trigger in PAUSE_DAILY and s.get("trade_day") != at[:10]):
                    continue  # rule 10: news of its program, or its own trading once a UTC day
                if locked and trigger not in ("book.fill", "book.settle", "book.refused"):
                    continue
                kept.append(trigger)
            due = s["last_run"] is None or t - s["last_run"] >= interval.get(agent, 7200.0)
            reason = ""
            if source == "resume":
                reason = "resume"
            elif kept:
                reason = f"trigger:{kept[0]}"
            elif source.endswith(":jev") and not (paused or locked):
                reason = "jev"
            elif not (paused or locked) and real and (holds or refused) and due:
                reason = "clock:real"
            elif not (paused or locked) and idle == "clock" and g is not None and g.get("record") == "idle" and due:
                reason = "clock:idle"
            elif not locked and idle == "barren" and s["barren_seen"] is not None and \
                    (s["barren"] - s["barren_seen"] if s["barren"] >= s["barren_seen"] else s["barren"]) >= barren_wakes:
                reason = "trigger:barren"
            elif not paused and t - base >= (real_heartbeat if real else practice_heartbeat) * 3600:
                reason = "heartbeat"
            if reason and throttle_research and not real and reason != "resume" and s["last_run"] is not None:
                gap = interval.get(agent, 7200.0)
                if t - s["last_run"] < min(2 * gap, max(gap, 86400.0)):
                    reason = ""  # rule 14: held for a later slot
            run = bool(reason)
            row = table[source]
            usd = float(p.get("cost_usd") or 0)
            changed = any(t - 60 <= x <= t + 600 for x in changes.get(agent, ()))
            row["did"] += 1
            row["did_usd_micro"] += int(usd * 1e6)
            row["did_candidates"] += outcome == "candidate"
            row["did_changes"] += changed
            if run:
                row["would"] += 1
                row["would_usd_micro"] += int(usd * 1e6)
                row["would_candidates"] += outcome == "candidate"
                row["would_changes"] += changed
                why[reason] += 1
                s["keys"] |= set(s["refused"])
                refusals["keys_used"] += len(new_keys)
            else:
                windows.add((agent, int(t // (sample_hours * 3600))))
            if source.startswith("sample:"):
                sampled["usd_micro"] += int(usd * 1e6)
                sampled["candidates"] += outcome == "candidate"
        if outcome == "abstained" and str(p.get("session")) not in s["consulted"]:
            s["streak"] += 1
        elif outcome in ("candidate", "failed_evaluation", "abstained"):
            s["streak"] = 0
        s["gate"] = None
        if run:
            s["refused"] = []
            s["last"] = t
            s["last_run"] = t
            s["barren_seen"] = s["barren"]
            s["lessons"] = 0
            if paused and any(k in PAUSE_DAILY for k in kept):
                s["trade_day"] = at[:10]
    expected = len(windows) * sample_percent / 100
    per_sample_usd = sampled["usd_micro"] / 1e6 / sampled["sessions"] if sampled["sessions"] else 0.0
    per_sample_candidates = sampled["candidates"] / sampled["sessions"] if sampled["sessions"] else 0.0
    total = Counter()
    for row in table.values():
        total.update(row)
    return {
        "window": {"from": start_at + "Z", "to": datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "hours": hours},
        "rules": {"idle_runs": idle, "practice_max_skip_hours": practice_heartbeat, "max_skip_hours": real_heartbeat,
                  "practice_pause_after": pause_after, "abstain_lock_after": lock_after, "sample_hours": sample_hours,
                  "lesson_arm": "parity" if parity else "all", "practice_skip_triggers": list(skip_practice),
                  "research_throttled": throttle_research},
        "sessions": {"did": total["did"], "would": total["would"], "would_with_samples": round(total["would"] + expected, 1)},
        "candidates": {"did": total["did_candidates"], "would": total["would_candidates"],
                       "would_with_samples": round(total["would_candidates"] + expected * per_sample_candidates, 1)},
        "adoptions_or_forks": {"did": total["did_changes"], "would": total["would_changes"]},
        "usd": {"did": round(total["did_usd_micro"] / 1e6, 2), "would": round(total["would_usd_micro"] / 1e6, 2),
                "would_with_samples": round(total["would_usd_micro"] / 1e6 + expected * per_sample_usd, 2)},
        "samples": {"expected": round(expected, 1), "windows_with_a_skip": len(windows)},
        "refusals": dict(refusals),
        # A teacher's lesson wakes agents the gate of the day did not (it matched full desk ids and
        # post-mortems): sessions that never ran cannot be replayed, so this is their upper bound.
        "lessons": {**dict(lessons), "note": "named_in_arm bounds the lesson sessions the rules add (not in `would`)"},
        "would_run_as": dict(why.most_common()),
        "by_reason": {k: {"did": v["did"], "would": v["would"], "candidates": [v["did_candidates"], v["would_candidates"]],
                          "adoptions_or_forks": [v["did_changes"], v["would_changes"]],
                          "usd": [round(v["did_usd_micro"] / 1e6, 2), round(v["would_usd_micro"] / 1e6, 2)]}
                      for k, v in sorted(table.items(), key=lambda kv: -kv[1]["did"])},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("ledger")
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--idle", choices=("barren", "off", "clock"), default="barren")
    parser.add_argument("--no-parity", action="store_true", help="lessons wake every agent they name (lesson_arm: all)")
    parser.add_argument("--skip-practice", default="", help="trigger kinds that do not wake a practice agent (rule 13)")
    parser.add_argument("--throttle-research", action="store_true", help="the research lane throttled all day (rule 14)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    out = replay(args.ledger, hours=args.hours, idle=args.idle, parity=not args.no_parity,
                 skip_practice=tuple(k for k in args.skip_practice.split(",") if k), throttle_research=args.throttle_research)
    if args.json:
        print(json.dumps(out, indent=1))
        return 0
    s, c, a, u = out["sessions"], out["candidates"], out["adoptions_or_forks"], out["usd"]
    print(f"window {out['window']['from']} .. {out['window']['to']}  rules {out['rules']}")
    print(f"sessions {s['did']} -> {s['would']} (+{out['samples']['expected']} expected samples)   candidates {c['did']} -> {c['would']}"
          f"   adoptions/forks {a['did']} -> {a['would']}   usd {u['did']} -> {u['would']} ({u['would_with_samples']} with samples)")
    print(f"refusals {out['refusals']}   teacher lessons {out['lessons']}")
    print(f"{'ran as':28s} {'did':>5s} {'would':>5s}  {'cand':>9s}  {'adopt':>7s}  {'usd':>13s}")
    for name, row in out["by_reason"].items():
        print(f"{name:28s} {row['did']:5d} {row['would']:5d}  {row['candidates'][0]:4d}>{row['candidates'][1]:<4d}  "
              f"{row['adoptions_or_forks'][0]:3d}>{row['adoptions_or_forks'][1]:<3d}  {row['usd'][0]:6.2f}>{row['usd'][1]:<6.2f}")
    print(f"would run as: {out['would_run_as']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
