"""Part B, step 1: every Merton pass Sept 22 00:00Z - Sept 25 06:00Z, what it cost, what it produced, and its REQUEST text.

The request is what Merton was asked BEFORE it answered:
- consultant: the agent's own question (merton.pass `question`), with the agent's desk and family;
- engineer: the repair job (key, kind, severity, source, attempt) and the latest `repair.reported` summary before the pass;
- foundry: the allocation (desk, route, reason);
- architect / teacher / operator / designer / toolsmith: no request is recorded (the House sends a scheduled evidence
  packet); a stand-in is built from what the ledger recorded since the role's previous pass (clearly a construction).
Writes merton.jsonl.
"""
import json
import os
import re
from bisect import bisect_left
from collections import Counter, defaultdict

from common import HERE, RESTATING, TRAIN_END, WINDOW_END, WINDOW_START, epoch, load, outcome

merton = load("merton")
summ = load("summ")
repair = load("repair")
ev = load("eval")
text = load("text")
born = load("born")

meta = {r["agent"]: r["p"] for r in born}
passes = [r for r in merton if r["kind"] == "merton.pass"]
changes = [r for r in merton if r["kind"] == "merton.change"]
reported = defaultdict(list)
for r in repair:
    if r["kind"] == "repair.reported":
        reported[r["p"].get("key")].append(r)
status_by_key = defaultdict(list)
for r in repair:
    if r["kind"] == "repair.status":
        status_by_key[r["p"].get("key")].append(r)
change_status = defaultdict(list)
for r in changes:
    if r["p"].get("number") is not None:
        change_status[int(r["p"]["number"])].append(r)
trials = defaultdict(list)
for r in ev:
    if r["kind"] == "eval.trial":
        trials[r["agent"]].append(r)
adopt = defaultdict(list)
for r in text:
    if (r["kind"] == "agent.strategy" and r["p"].get("control") not in RESTATING) or r["kind"] == "agent.forked":
        adopt[r["agent"]].append(r["t"])
summaries = defaultdict(list)
consult_in_session = defaultdict(list)
for r in summ:
    if r["p"].get("tool") == "summary":
        summaries[r["agent"]].append(r)
    elif r["p"].get("tool") == "merton":
        consult_in_session[r["agent"]].append(r)
MISSING = re.compile(r"not[_ ]supplied|not available|unavailable|unimplemented|missing|absent|no historical|"
                     r"lacks?\b|without (?:a|the|any) [a-z-]+ (?:feed|data|history)|no [a-z/ -]{0,30}(?:feed|data)\b", re.I)


def since_rows(kind_filter, lo, hi):
    return [r for r in text + ev if lo <= r["t"] < hi and kind_filter(r)]


rows = []
last_by_role = {}
key_history = defaultdict(list)  # engineer repair key -> earlier passes (files)
agent_history = defaultdict(list)  # consultant agent -> earlier passes (wrote_code)
for r in passes:
    p = r["p"]
    role = p.get("role")
    t = float(p.get("at_epoch") or r["t"])
    prev_t = last_by_role.get(role)
    last_by_role[role] = t
    if not (WINDOW_START <= r["at"] < WINDOW_END):
        if role == "engineer":
            key_history[p.get("repair")].append(int(p.get("files") or 0))
        if role == "consultant":
            agent_history[p.get("agent")].append(bool(p.get("wrote_code")))
        continue
    cost = float(p.get("cost_usd") or 0)
    rec = {"seq": r["seq"], "at": r["at"], "t": t, "role": role, "cost": cost, "error": bool(p.get("error")),
           "split": "train" if r["at"] < TRAIN_END else "test", "summary": str(p.get("summary") or p.get("answer") or "")[:300]}
    det = {}
    if role == "consultant":
        agent = p.get("agent")
        m = meta.get(agent, {})
        q = str(p.get("question") or "")
        rec["agent"] = agent
        rec["request"] = (f"An agent pays Merton (the frontier model) to consult on its strategy. Agent {agent}, desk {m.get('specialty') or m.get('niche')}, "
                          f"family {m.get('family')}, venue {m.get('venue')}. Its question: {q}")[:1500]
        produced = bool(p.get("wrote_code")) and not p.get("error")
        # the research session that bought the consult, and what it retained
        near = [c for c in consult_in_session.get(agent, []) if abs(c["t"] - r["t"]) < 120 and str(c["p"].get("question") or "")[:80] == q[:80]]
        session = near[0]["p"].get("session") if near else None
        summ_row = next((s for s in summaries.get(agent, []) if s["p"].get("session") == session), None) if session else None
        cand = bool(summ_row and summ_row["p"].get("candidate"))
        end = float(summ_row["p"].get("finished")) if summ_row else t
        passed = any(tr["p"].get("passed") and t <= tr["t"] <= end + 7200 for tr in trials.get(agent, []))
        rec.update(produced=produced, yield_=produced and cand and passed, candidate=cand, replay_passed=passed, session=session,
                   adopted=any(t <= x <= end + 7200 for x in adopt.get(agent, [])))
        hist = agent_history[agent]
        det = {"prior_consults": len(hist), "prior_consult_no_code": sum(1 for h in hist if not h), "q_missing": bool(MISSING.search(q)),
               "q_len": len(q)}
        hist.append(bool(p.get("wrote_code")))
    elif role == "engineer":
        key = str(p.get("repair") or "")
        rep = [x for x in reported.get(key, []) if x["t"] < t]
        last = rep[-1]["p"] if rep else {}
        rec["agent"] = key
        rec["request"] = (f"Repair job for the House's repair engineer (may patch strategies, tools and permitted dials, not core code). "
                          f"Key: {key}. Kind {last.get('kind') or key.split(':')[0]}, severity {last.get('severity')}, source {last.get('source')}, "
                          f"occurrences {last.get('occurrences')}, agents {', '.join((last.get('agents') or [])[:3])}. Attempt {p.get('attempt')}. "
                          f"Reported: {last.get('summary') or ''}")[:1500]
        files = int(p.get("files") or 0)
        produced = files > 0 and not p.get("error")
        later = [x["p"].get("state") for x in status_by_key.get(key, []) if t <= x["t"] <= t + 86400]
        # repair.status states: admitted, reproducing, patching, testing, revising, canary (merged, staged), observing, verified,
        # rejected, dormant. A PR that reached canary or beyond shipped.
        rec.update(produced=produced, yield_=produced and any(s in ("canary", "observing", "verified") for s in later),
                   later_states=sorted(set(s for s in later if s)))
        hist = key_history[key]
        det = {"attempt": int(p.get("attempt") or 0), "prior_passes_on_key": len(hist), "prior_empty_on_key": sum(1 for h in hist if h == 0),
               "repair_kind": key.split(":")[0], "q_missing": bool(MISSING.search(str(last.get("summary") or ""))),
               "core_words": bool(re.search(r"reconcil|accounting|ledger|freeze|cash|core|house", str(last.get("summary") or "") + key, re.I))}
        hist.append(files)
    elif role == "foundry":
        a = p.get("allocation") or {}
        if isinstance(a, str):
            a = {"raw": a}
        rec["agent"] = "foundry:" + str(a.get("desk"))
        rec["request"] = (f"Hypothesis foundry call: write up to four new strategy hypotheses (cards) for desk {a.get('desk')} via route "
                          f"{a.get('route')}. Why this desk: {a.get('reason') or a.get('raw') or ''}")[:1500]
        cards = p.get("cards") or []
        produced = bool(cards) and not p.get("error")
        rec.update(produced=produced, yield_=produced, cards=len(cards))
        det = {"route": a.get("route"), "desk": a.get("desk")}
    else:
        # scheduled role: a stand-in request from what was recorded since the role's previous pass
        lo = prev_t or (t - 86400)
        new = [x for x in text if lo <= x["t"] < t]
        kinds = Counter(x["kind"] for x in new)
        pm = [x for x in new if x["kind"] == "playbook.entry" and x["p"].get("source") == "graveyard"]
        lessons = [x for x in new if x["kind"] == "playbook.entry" and x["p"].get("source") == "teacher"]
        reqs = [x for x in new if x["kind"] == "tool.request"]
        tr = [x for x in ev if x["kind"] == "eval.trial" and lo <= x["t"] < t]
        rec["agent"] = "scheduled:" + role
        rec["request"] = (f"Scheduled {role} pass ({(t - lo) / 3600:.1f} h after the previous one). Recorded since: {kinds['agent.died']} deaths, "
                          f"{len(pm)} post-mortems (e.g. {'; '.join(str(x['p'].get('title'))[:60] for x in pm[-3:])}), {len(lessons)} teacher lessons, "
                          f"{len(tr)} replay trials ({sum(1 for x in tr if x['p'].get('passed'))} passed), {len(reqs)} new tool requests "
                          f"({'; '.join(str(x['p'].get('name'))[:40] for x in reqs[-3:])}), {kinds['library.note']} library notes.")[:1500]
        files = int(p.get("files") or 0)
        produced = files > 0 and not p.get("error")
        number = p.get("number")
        merged = number is not None and any(x["p"].get("status") in ("merged", "deployed") for x in change_status.get(int(number), []))
        rec.update(produced=produced, yield_=produced and merged)
        det = {"hours_since_prev": (t - lo) / 3600, "n_new_pm": len(pm), "n_new_req": len(reqs)}
    rec["nothing"] = not rec["produced"]
    rec["det"] = det
    rows.append(rec)

with open(os.path.join(HERE, "merton.jsonl"), "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")
c = Counter((r["split"], r["role"], r["produced"], r["yield_"]) for r in rows)
for k, v in sorted(c.items(), key=str):
    print(k, v)
print(len(rows))
