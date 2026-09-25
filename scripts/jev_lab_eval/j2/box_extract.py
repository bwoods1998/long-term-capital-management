# Runs ON the House box (read-only). argv: group lo hi. Prints base64(gzip(jsonl)) of compact projections.
import sqlite3, json, sys, gzip, base64, ast
group, lo, hi = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
db = sqlite3.connect("file:/workspace/state/ledger.sqlite?mode=ro", uri=True)
def T(v, n):
    if v is None: return None
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s[:n]
def inst(p):
    i = p.get("instrument")
    if isinstance(i, str):
        try: i = json.loads(i)
        except Exception: i = {}
    i = i or {}
    return i.get("market_id") or i.get("symbol")
def doc(code):
    try: return (ast.get_docstring(ast.parse(code or "")) or "")[:500]
    except Exception: return ""
def proj(kind, p):
    g = p.get
    if kind == "agent.research":
        if g("tool") == "summary":
            return {k: g(k) for k in ("session", "started", "finished", "profile", "cost_usd", "candidate", "trials", "turns", "refunded_usd")} | {"tool": "summary", "reason": T(g("reason"), 120), "summary": T(g("summary"), 900)}
        if g("tool") == "merton":
            return {"tool": "merton", "session": g("session"), "wrote_code": g("wrote_code"), "cost_usd": g("cost_usd"), "question": T(g("question"), 600), "error": g("error")}
        return None
    if kind == "research.gate":
        return {k: g(k) for k in ("decision", "reason", "triggers", "sampled", "sessions", "empty_streak", "inactive", "trigger", "record", "cost_usd", "aggregated")}
    if kind == "book.fill":
        return {"book": g("book"), "side": g("side"), "price": g("price"), "quantity": g("quantity"), "liquidity": g("liquidity"), "realized": g("realized"), "real_money": g("real_money"), "source": g("source"), "market": inst(p), "reason": T(g("reason"), 160)}
    if kind == "book.settle":
        return {"book": g("book"), "pnl": g("pnl"), "result": g("result"), "market": inst(p), "real_money": g("real_money"), "quantity": g("quantity")}
    if kind == "book.refused":
        r = g("reasons") or []
        return {"book": g("book"), "reasons": [T(x, 200) for x in r[:2]], "market": inst(p)}
    if kind == "eval.verdict":
        if g("decision") in ("look", "progress"): return None
        return {"decision": g("decision"), "reason": T(g("reason"), 200), "from_rung": g("from_rung"), "to_rung": g("to_rung"), "book": g("book"), "band_to": g("band_to")}
    if kind == "eval.trial":
        return {"passed": g("passed"), "family": g("family"), "trades": g("trades"), "deflated_sharpe": g("deflated_sharpe"), "return_pct": g("return_pct"), "reasons": [T(x, 120) for x in (g("reasons") or [])[:3]], "code_sha256": g("code_sha256")}
    if kind == "eval.block":
        if not g("active"): return None
        return {"log_growth": g("log_growth"), "book": g("book"), "key": g("key")}
    if kind == "audit.verdict":
        return {"approve": g("approve"), "summary": T(g("summary"), 300), "cost_usd": g("cost_usd")}
    if kind == "library.note":
        return {"niche": g("niche"), "title": T(g("title"), 200), "text": T(g("text"), 400), "tags": g("tags")}
    if kind == "playbook.entry":
        return {"source": g("source"), "title": T(g("title"), 200), "text": T(g("text"), 3000)}
    if kind == "tool.fulfilled":
        return {"request": g("request"), "outcome": T(g("outcome"), 300), "status": g("status")}
    if kind == "tool.request":
        return {"name": g("name"), "description": T(g("description"), 300)}
    if kind == "agent.inactive":
        return {"reason": g("reason"), "detail": T(g("detail"), 200), "was": g("was")}
    if kind == "agent.strategy":
        return {"control": g("control"), "code_sha256": g("code_sha256"), "reason": T(g("reason"), 300)}
    if kind == "agent.born":
        return {k: g(k) for k in ("family", "specialty", "niche", "style", "venue", "horizon", "parent", "founder", "line", "generation", "code_sha256")} | {"reason": T(g("reason"), 300), "doc": doc(g("_code"))}
    if kind == "agent.forked":
        return {"child": g("child"), "new_code": g("new_code"), "reason": T(g("reason"), 200)}
    if kind == "agent.died":
        return {"cause": g("cause"), "detail": T(g("detail"), 200)}
    if kind == "agent.woke":
        return {"ok": g("ok"), "book": g("book"), "barren": g("barren"), "shut": g("shut"), "intents": g("intents"), "offered": g("offered")}
    if kind == "repair.status":
        return {"key": T(g("key"), 200), "state": g("state"), "pr": g("pr"), "cost_usd": g("cost_usd")}
    if kind == "repair.reported":
        return {"key": T(g("key"), 200), "kind": g("kind"), "source": g("source"), "severity": g("severity"), "agents": (g("agents") or [])[:5], "summary": T(g("summary"), 500), "occurrences": g("occurrences")}
    if kind == "credit.grant":
        if str(g("reason") or "").startswith("epoch payout"): return None
        return {"reason": T(g("reason"), 120), "usd": g("usd")}
    if kind == "merton.pass":
        return {k: (T(v, 1500) if isinstance(v, str) else v) for k, v in p.items() if k != "code"}
    if kind == "merton.change":
        return {k: g(k) for k in ("role", "branch", "number", "title", "status", "paths")}
    if kind == "hypothesis.card":
        return {k: g(k) for k in ("id", "niche", "family", "created_for", "line_id", "name")}
    if kind == "trace.record":
        return {k: g(k) for k in ("task", "id", "outcome", "useful", "cost_usd")}
    return None
GROUPS = {
    "summ": ["agent.research"],
    "gate": ["research.gate"],
    "book": ["book.fill", "book.settle", "book.refused"],
    "eval": ["eval.verdict", "eval.trial", "eval.block", "audit.verdict"],
    "text": ["library.note", "playbook.entry", "tool.fulfilled", "tool.request", "agent.inactive", "agent.strategy", "agent.forked", "agent.died", "credit.grant"],
    "born": ["agent.born"],
    "woke": ["agent.woke"],
    "repair": ["repair.status", "repair.reported"],
    "merton": ["merton.pass", "merton.change", "hypothesis.card"],
}
out = []
for kind in GROUPS[group]:
    sql = "SELECT seq, id, agent, at, payload FROM ledger WHERE kind=? AND seq>=? AND seq<?"
    params = [kind, lo, hi]
    if kind == "agent.research":
        sql += " AND (payload LIKE ? OR payload LIKE ?)"; params += ['%"tool":"summary"%', '%"tool":"merton"%']
    for seq, rid, agent, at, payload in db.execute(sql, params):
        p = json.loads(payload)
        q = proj(kind, p)
        if q is None: continue
        out.append(json.dumps({"seq": seq, "id": rid, "kind": kind, "agent": agent, "at": at, "p": q}, default=str, separators=(",", ":")))
sys.stdout.write(base64.b64encode(gzip.compress("\n".join(out).encode())).decode())
