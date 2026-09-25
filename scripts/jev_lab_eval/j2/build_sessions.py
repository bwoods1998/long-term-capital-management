"""Part A, step 1-2: the research-session population, outcomes, F2 replay flag and the evidence text.

Reads data/*.jsonl (read-only ledger extracts made by box_extract.py) and writes sessions.jsonl.
Nothing here looks at or after a session's start when building its evidence.
"""
import json
import os
import statistics
from bisect import bisect_left
from collections import Counter, defaultdict

from common import (DATA, HERE, RESTATING, ROUTINE, TRAIN_END, WINDOW_END, WINDOW_START, epoch, lesson_arm, lesson_terms,
                    lesson_words, load, outcome, primary, refusal_class)

summ = load("summ")
gate = load("gate")
book = load("book")
ev = load("eval")
text = load("text")
born = load("born")
woke = load("woke")
repair = load("repair")

summaries = [r for r in summ if r["p"].get("tool") == "summary"]
consult_rows = [r for r in summ if r["p"].get("tool") == "merton"]

# ------------------------------------------------------------------ agent metadata and lineage
meta = {}
for r in born:
    p = r["p"]
    meta[r["agent"]] = {"family": p.get("family"), "niche": p.get("niche") or p.get("specialty"), "specialty": p.get("specialty"),
                        "style": p.get("style"), "venue": p.get("venue"), "horizon": p.get("horizon"), "parent": p.get("parent"),
                        "founder": p.get("founder"), "line": p.get("line"), "doc": p.get("doc") or "", "born_at": r["at"]}


def lineage(agent):
    out, seen = [agent], {agent}
    cur = agent
    while cur in meta and meta[cur].get("parent") and meta[cur]["parent"] not in seen:
        cur = meta[cur]["parent"]
        out.append(cur)
        seen.add(cur)
    return out


# ------------------------------------------------------------------ indexes
by_agent = defaultdict(list)  # agent -> rows of agent-scoped evidence kinds
AGENT_KINDS = ("book.fill", "book.settle", "book.refused", "eval.verdict", "eval.trial", "eval.block", "audit.verdict",
               "agent.inactive", "agent.strategy", "credit.grant", "tool.request")
for r in book + ev + text:
    if r["kind"] in AGENT_KINDS:
        by_agent[r["agent"]].append(r)
for a in by_agent:
    by_agent[a].sort(key=lambda r: r["seq"])
notes = [r for r in text if r["kind"] == "library.note"]
lessons = [r for r in text if r["kind"] == "playbook.entry"]
fulfilled = [r for r in text if r["kind"] == "tool.fulfilled"]
repair_status = [r for r in repair if r["kind"] == "repair.status"]
trials_by_agent = defaultdict(list)
for r in ev:
    if r["kind"] == "eval.trial":
        trials_by_agent[r["agent"]].append(r)
changes_by_agent = defaultdict(list)  # adoptions (non-restating agent.strategy) and forks, F2's yield column
for r in text:
    if r["kind"] == "agent.strategy" and r["p"].get("control") not in RESTATING:
        changes_by_agent[r["agent"]].append(epoch(r["at"]))
    elif r["kind"] == "agent.forked":
        changes_by_agent[r["agent"]].append(epoch(r["at"]))
births_by_parent = defaultdict(list)
for r in born:
    if r["p"].get("parent"):
        births_by_parent[r["p"]["parent"]].append(r)


def between(rows, lo_seq, hi_epoch):
    """Rows with seq > lo_seq and time < hi_epoch (rows are seq-sorted)."""
    seqs = [r["seq"] for r in rows]
    i = bisect_left(seqs, lo_seq + 1)
    out = []
    for r in rows[i:]:
        if r["t"] >= hi_epoch:
            break
        out.append(r)
    return out


# ------------------------------------------------------------------ F2 replay (adapted read-only from
# ~/Work/ltcm-f-research scripts/gate_replay.py at 7abb77e; same state machine, window = our whole window)
REAL = ("kalshi", "alpaca")


def f2_flags(start_seq):
    stream = []
    for r in gate:
        stream.append(r)
    for r in summ:
        stream.append(r)
    for r in book:
        if r["kind"] in ("book.refused", "book.fill"):
            stream.append(r)
    for r in woke + born:
        stream.append(r)
    for r in text:
        if r["kind"] in ("playbook.entry", "agent.strategy", "agent.forked", "agent.died"):
            stream.append(r)
    stream.sort(key=lambda r: r["seq"])
    gaps, last_gate = defaultdict(list), {}
    for r in gate:
        if r["seq"] >= start_seq:
            t = epoch(r["at"])
            if r["agent"] in last_gate:
                gaps[r["agent"]].append(t - last_gate[r["agent"]])
            last_gate[r["agent"]] = t
    interval = {a: statistics.median(g) for a, g in gaps.items() if g}
    st = defaultdict(lambda: {"gate": None, "refused": [], "streak": 0, "book": None, "acted": False, "barren": 0, "barren_seen": None,
                              "last": None, "last_run": None, "keys": set(), "consulted": set(), "words": set(), "born": None, "lessons": 0})
    flags = {}
    for r in stream:
        kind, agent, p, seq = r["kind"], r["agent"], r["p"], r["seq"]
        s = st[agent]
        t = epoch(r["at"])
        if kind == "agent.born":
            s["born"] = t
            s["words"] = lesson_words(agent, p.get("specialty"), p.get("niche"), p.get("family"))
            continue
        if kind == "playbook.entry":
            if p.get("source") == "teacher":
                terms = lesson_terms(p)
                for name, other in st.items():
                    if other["words"] and any(w in terms for w in other["words"]):
                        other["lessons"] += 1
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
            s["refused"].append(f"{r['at'][:10]}|{p.get('book') or ''}|{refusal_class(reasons[0] if reasons else '')}")
            continue
        if kind == "book.fill":
            continue
        if kind == "research.gate":
            if p.get("decision") in ("run", "sample"):
                s["gate"] = p
            continue
        if kind in ("agent.strategy", "agent.forked"):
            continue
        if p.get("tool") == "merton" and p.get("wrote_code"):
            s["consulted"].add(str(p.get("session")))
            continue
        if p.get("tool") != "summary":
            continue
        out = outcome(p)
        run = seq < start_seq
        if seq >= start_seq:
            g = s["gate"]
            real = s["book"] in REAL
            holds = s["acted"]
            refused = bool(s["refused"])
            new_keys = {k for k in s["refused"] if k not in s["keys"]}
            paused = not real and s["streak"] >= 3
            locked = real and s["streak"] >= 3
            base = max(s["last"] or 0.0, s["born"] or 0.0)
            if g is None and refused:
                source, found = "refusal_prompt", ["book.refused"]
            elif g is None:
                source, found = "resume", []
            else:
                source = f"{g.get('decision')}:{g.get('trigger') or str(g.get('reason') or '').split(':')[0]}"
                found = [str(x).split(":")[0] for x in g.get("triggers") or []]
            kept = []
            for trigger in found:
                if trigger == "book.refused" and not new_keys:
                    continue
                if trigger == "lesson" and (s["lessons"] == 0 or lesson_arm(agent) != "lesson"):
                    continue
                if paused and trigger != "book.fill":
                    continue
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
            elif not (paused or locked) and s["barren_seen"] is not None and \
                    (s["barren"] - s["barren_seen"] if s["barren"] >= s["barren_seen"] else s["barren"]) >= 10:
                reason = "trigger:barren"
            elif not paused and t - base >= (24.0 if real else 72.0) * 3600:
                reason = "heartbeat"
            run = bool(reason)
            flags[seq] = {"f2_source": source, "f2_would": run, "f2_reason": reason, "f2_real": real}
            if run:
                s["keys"] |= set(s["refused"])
        if out == "abstained" and str(p.get("session")) not in s["consulted"]:
            s["streak"] += 1
        elif out in ("candidate", "failed_evaluation", "abstained"):
            s["streak"] = 0
        s["gate"] = None
        if run:
            s["refused"] = []
            s["last"] = t
            s["last_run"] = t
            s["barren_seen"] = s["barren"]
            s["lessons"] = 0
    return flags


start_seq = min(r["seq"] for r in summaries if r["at"] >= WINDOW_START)
f2 = f2_flags(start_seq)

# ------------------------------------------------------------------ matching sessions to gate rows
gate_by_agent = defaultdict(list)
for r in gate:
    gate_by_agent[r["agent"]].append(r)
refused_by_agent = defaultdict(list)
for r in book:
    if r["kind"] == "book.refused":
        refused_by_agent[r["agent"]].append(r)
summ_by_agent = defaultdict(list)
for r in summaries:
    summ_by_agent[r["agent"]].append(r)


def fmt_money(x):
    try:
        return f"{float(x):+.2f}"
    except (TypeError, ValueError):
        return str(x)


def evidence(agent, prev, started, lo_seq, concl=None):
    """The compact 'new since the previous finished session' text, and deterministic counts."""
    m = meta.get(agent, {})
    rows = between(by_agent.get(agent, []), lo_seq, started)
    counts = Counter(r["kind"] for r in rows)
    parts = []
    fills = [r for r in rows if r["kind"] == "book.fill" and r["p"].get("source") != "dust"]
    settles = [r for r in rows if r["kind"] == "book.settle"]
    refused = [r for r in rows if r["kind"] == "book.refused"]
    verdicts = [r for r in rows if r["kind"] == "eval.verdict"]
    trials = [r for r in rows if r["kind"] == "eval.trial"]
    blocks = [r for r in rows if r["kind"] == "eval.block"]
    audits = [r for r in rows if r["kind"] == "audit.verdict"]
    inactive = [r for r in rows if r["kind"] == "agent.inactive"]
    strategies = [r for r in rows if r["kind"] == "agent.strategy" and r["p"].get("control") not in RESTATING]
    grants = [r for r in rows if r["kind"] == "credit.grant" and r["p"].get("reason") != "endowment"]
    real_fill = any(r["p"].get("real_money") for r in fills)
    real_settle = any(r["p"].get("real_money") for r in settles)
    if fills:
        ex = "; ".join(f"{f['p'].get('side')} {f['p'].get('quantity')} {str(f['p'].get('market'))[:28]} @{f['p'].get('price')}"
                       + (f" realized {fmt_money(f['p'].get('realized'))}" if f['p'].get('realized') is not None else "")
                       for f in fills[-3:])
        parts.append(f"FILLS {len(fills)} ({'real money' if real_fill else 'practice'}): {ex}")
    if settles:
        pnl = sum(float(s["p"].get("pnl") or 0) for s in settles)
        wins = sum(1 for s in settles if float(s["p"].get("pnl") or 0) > 0)
        ex = "; ".join(f"{str(s['p'].get('market'))[:28]} {fmt_money(s['p'].get('pnl'))}" for s in settles[-3:])
        parts.append(f"SETTLEMENTS {len(settles)} ({'real money' if real_settle else 'practice'}), {wins} won, pnl {pnl:+.2f}: {ex}")
    if refused:
        reasons = Counter(refusal_class((r["p"].get("reasons") or [""])[0]) for r in refused)
        parts.append(f"ORDERS REFUSED {len(refused)}: " + "; ".join(f"{n}x {k[:110]}" for k, n in reasons.most_common(2)))
    if verdicts:
        parts.append("VERDICTS: " + "; ".join(f"{v['p'].get('decision')}: {str(v['p'].get('reason'))[:100]}" for v in verdicts[-2:]))
    if audits:
        parts.append("AUDIT: " + "; ".join(f"{'approve' if a['p'].get('approve') else 'refuse'}: {str(a['p'].get('summary'))[:120]}" for a in audits[-1:]))
    if blocks:
        g = sum(float(b["p"].get("log_growth") or 0) for b in blocks)
        parts.append(f"ACTIVE FORWARD BLOCKS {len(blocks)}, log growth {g:+.4f}")
    if trials:
        parts.append("REPLAYS (outside a session): " + "; ".join(
            f"{'passed' if t_['p'].get('passed') else 'failed'} trades {t_['p'].get('trades')} dsr {t_['p'].get('deflated_sharpe') if t_['p'].get('deflated_sharpe') is None else round(float(t_['p'].get('deflated_sharpe')), 2)}"
            for t_ in trials[-2:]))
    if strategies:
        parts.append("CODE CHANGED: " + str(strategies[-1]["p"].get("reason") or "")[:120])
    if inactive:
        parts.append("INACTIVITY: " + "; ".join(f"{r['p'].get('reason') or 'active'} ({str(r['p'].get('detail'))[:70]})" for r in inactive[-2:]))
    if grants:
        parts.append("CREDITS: " + "; ".join(f"{g_['p'].get('usd')} {str(g_['p'].get('reason'))[:40]}" for g_ in grants[-2:]))
    # Notes by other agents in its niche; lessons that name its desk, family or specialty.
    niche = m.get("niche") or ""
    words = {w for w in (niche, m.get("specialty"), m.get("family")) if w}
    lw = lesson_words(agent, m.get("specialty"), m.get("niche"), m.get("family"))
    niche_notes = [n for n in between(notes, lo_seq, started) if n["p"].get("niche") == niche and n["agent"] != agent]
    if niche_notes:
        parts.append(f"DESK NOTES {len(niche_notes)}: " + "; ".join(str(n["p"].get("title"))[:110] for n in niche_notes[-3:]))
    my_lessons, teacher = [], 0
    for le in between(lessons, lo_seq, started):
        body = f"{le['p'].get('title') or ''} {le['p'].get('text') or ''}".lower()
        if any(str(w).lower() in body for w in words) or any(w in lesson_terms(le["p"]) for w in lw):
            my_lessons.append(le)
            teacher += le["p"].get("source") == "teacher"
    if my_lessons:
        parts.append(f"LESSONS {len(my_lessons)} ({teacher} teacher): " + "; ".join(str(le["p"].get("title"))[:100] for le in my_lessons[-3:]))
    line = set(lineage(agent))
    mine = set()
    for member in line:
        for r in by_agent.get(member, []):
            if r["kind"] == "tool.request" and epoch(r["at"]) < started:
                mine.add(r["id"])
    ful = [f for f in between(fulfilled, lo_seq, started) if f["p"].get("request") in mine]
    if ful:
        parts.append("REQUEST FULFILLED: " + "; ".join(str(f["p"].get("outcome"))[:150] for f in ful[-2:]))
    reps = [r for r in between(repair_status, lo_seq, started) if f":{agent}:" in str(r["p"].get("key") or "") + ":"]
    if reps:
        parts.append("REPAIRS: " + "; ".join(f"{r['p'].get('state')}" for r in reps[-3:]))
    head = (f"STRATEGY {agent}: desk {niche}, family {m.get('family')}, style {m.get('style')}, venue {m.get('venue')}, horizon {m.get('horizon')}. "
            + (f"Doc: {m.get('doc')[:160]}. " if m.get("doc") else ""))
    if prev is not None:
        hours = (started - epoch(prev["at"])) / 3600
        said = str(prev['p'].get('summary') or '').strip()
        if not said and concl is not None:
            said = "(no summary; last conclusion) " + str(concl['p'].get('summary') or '')
        head += f"PREVIOUS SESSION ({hours:.1f} h ago, {outcome(prev['p'])}): {said[:300]}"
    else:
        head += "PREVIOUS SESSION: none (first research)."
    body = " | ".join(parts) if parts else "NOTHING NEW since the previous session."
    textv = head + " || NEW SINCE: " + body
    feats = {"n_fill": len(fills), "n_settle": len(settles), "n_refused": len(refused), "n_verdict": len(verdicts), "n_audit": len(audits),
             "n_block": len(blocks), "n_trial_between": len(trials), "n_code": len(strategies), "n_inactive": len(inactive),
             "n_notes": len(niche_notes), "n_lessons": len(my_lessons), "n_teacher_lessons": teacher, "n_fulfilled": len(ful),
             "n_repair": len(reps), "real_fill": real_fill, "real_settle": real_settle,
             "settle_pnl": round(sum(float(s["p"].get("pnl") or 0) for s in settles), 4),
             "any_new": bool(parts)}
    return textv[:1500], feats


out = []
stats = Counter()
for agent, rows in summ_by_agent.items():
    grows = gate_by_agent.get(agent, [])
    gseqs = [g["seq"] for g in grows]
    for i, s in enumerate(rows):
        if not (WINDOW_START <= s["at"] < WINDOW_END):
            continue
        p = s["p"]
        started = float(p.get("started") or epoch(s["at"]))
        prev = rows[i - 1] if i > 0 else None
        lo = prev["seq"] if prev else 0
        # the gate decision (run/sample) between the previous summary and this one
        j = bisect_left(gseqs, s["seq"]) - 1
        g = None
        while j >= 0 and grows[j]["seq"] > lo:
            if grows[j]["p"].get("decision") in ("run", "sample"):
                g = grows[j]
                break
            j -= 1
        if g is not None:
            gp = g["p"]
            decision = gp.get("decision")
            kind = gp.get("trigger") or (primary(gp.get("triggers")) if gp.get("reason") == "trigger" else str(gp.get("reason") or "").split(":")[0])
            if decision == "run" and gp.get("reason") == "jev_relevant_note":
                kind = "jev"
            source = decision
            lag = started - epoch(g["at"])
        else:
            refs = [r for r in refused_by_agent.get(agent, []) if r["seq"] > lo and epoch(r["at"]) < started]
            source = "refusal_prompt" if refs else "ungated"
            kind = "refusal_prompt" if refs else "ungated"
            decision, gp, lag = None, {}, None
        stats[source] += 1
        oc = outcome(p)
        finished = float(p.get("finished") or epoch(s["at"]))
        o1 = oc == "candidate"
        passed = [t for t in trials_by_agent.get(agent, []) if t["p"].get("passed") and started - 1 <= epoch(t["at"]) <= finished + 7200]
        o2 = o1 and bool(passed)
        t_s = epoch(s["at"])
        o3 = any(t_s - 60 <= x <= t_s + 600 for x in changes_by_agent.get(agent, ()))
        births = [b for b in births_by_parent.get(agent, []) if t_s - 60 <= epoch(b["at"]) <= t_s + 7200]
        lo_evidence = prev["seq"] if prev else 0
        concl = next((r for r in reversed(rows[:i]) if str(r["p"].get("summary") or "").strip()), None)
        txt, feats = evidence(agent, prev, started, lo_evidence, concl)
        rec = {"seq": s["seq"], "agent": agent, "session": p.get("session"), "at": s["at"], "started": started, "finished": finished,
               "split": "train" if s["at"] < TRAIN_END else "test", "cost": float(p.get("cost_usd") or 0), "profile": p.get("profile"),
               "outcome": oc, "o1": o1, "o2": o2, "o3_adopt_or_fork": o3, "o3_birth": bool(births),
               "source": source, "kind": kind or "", "gate_reason": gp.get("reason"), "streak": gp.get("empty_streak"),
               "record": gp.get("record"), "inactive": gp.get("inactive"), "gate_lag_s": lag,
               "prev_outcome": outcome(prev["p"]) if prev else None, "hours_since_prev": (started - epoch(prev["at"])) / 3600 if prev else None,
               "family": meta.get(agent, {}).get("family"), "niche": meta.get(agent, {}).get("niche"), "venue": meta.get(agent, {}).get("venue"),
               **f2.get(s["seq"], {"f2_source": None, "f2_would": None, "f2_reason": None, "f2_real": None}),
               **feats, "text": txt}
        out.append(rec)
out.sort(key=lambda r: r["seq"])
with open(os.path.join(HERE, "sessions.jsonl"), "w") as fh:
    for r in out:
        fh.write(json.dumps(r) + "\n")
print(stats)
print(len(out))
