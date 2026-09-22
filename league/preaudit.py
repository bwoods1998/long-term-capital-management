"""The pre-audit: a cheap, deterministic look at an agent's code and first paper wakes, long
before the frontier audit sees its record.

The production audit (`league/auditor.py`) runs only when a paper record clears the constitution's
screen, which can be weeks of paper. By then a strategy that was broken on its first wake has
spent every one of those weeks proving nothing. Measured Sept 22, 2026: the auditor vetoed haghani
(audit.verdict seq 123905) because "cent rounding defeats the minimum entry discount on low-priced
coins" -- the code rounds its buy target to two decimals, so DOGE buys at $0.10 reported discounts
of -2.0%, -1.5% and -1.1% (buys ABOVE the mean) against a `min_edge_pct` of 0.8. That defect was in
the file from its first line on paper; any reader of the code could have seen it on day one. And the
floor is not short of dead weight: replay passes 6.5% of trials and 66% of House births land on six
dead desks, so a paper seat spent on broken code is a seat a working idea did not get.

So when an agent is on paper (rung 1), this module looks twice:

1. at rung entry, the CODE: obvious defects an AST can see (today, cent rounding of prices on a
   desk that trades sub-dollar instruments), cited by line;
2. after its first few paper wakes (`wakes`, default six), the BEHAVIOUR: how often its decide
   raised, how many intents the House dropped as malformed, how often the book refused what it
   sent, and how often it looked at a live market and did nothing while never trading at all.

A red flag becomes a `repair.reported` row (`kind: strategy_defect`, `source: audit`) -- the durable
repair queue's input, from which a corrected CHILD is written -- and a mark on the agent's
promotion status, so the agent and its research packet see what is wrong. It is a report, never a
verdict: it kills nobody, changes no credit, no rung, no statistic and no gate. A strategy that
really is fine keeps its seat and its record; the full audit still decides real money.

Deterministic and free. `escalate` is a hook for a future few-cent model check on red flags only;
it is None by default and nothing on the floor sets it.
"""

from __future__ import annotations

import ast
import re
import threading
import time
from typing import Any, Callable, Mapping, Sequence

from .ledger import LedgerConflict, now_iso

PREAUDIT_STATE_KEY = "pre_audit"

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "wakes": 6,  # paper wakes before the behaviour is judged
    "every_seconds": 600,  # one pass every ten minutes; each pass is a few ledger reads an agent
    "max_agents_per_run": 40,
    "error_rate": 0.34,  # more than a third of wakes raised
    "refusal_rate": 0.5,  # the book refused at least half of what it was sent
    "barren_rate": 0.8,  # live market in front of it, nothing done, and no fill ever
    "dropped": 1,  # any intent the House could not even read
}

#: Coins that trade under a dollar (or near it) on Alpaca's crypto venue, where a cent is a large
#: fraction of the price. Evidence from the agent's own fills below a dollar counts the same.
LOW_PRICED = frozenset({"DOGE", "SHIB", "XRP", "ADA", "PEPE", "BONK", "TRX", "XLM", "HBAR", "VET", "ALGO", "GRT", "FLOKI",
                        "MATIC", "POL", "SUSHI", "BAT", "CRV", "CHZ", "JASMY", "ONE", "SAND", "MANA", "DOT"})

#: Names that hold a price; names that hold something else (a quantity, a fraction) are left alone.
PRICE_WORDS = re.compile(r"(price|target|limit|entry|exit|bid|ask|mean|level|stop|fair|mid|vwap|close|open|high|low)", re.I)
NOT_PRICE_WORDS = re.compile(r"(qty|quantity|size|shares|units|notional|pct|percent|fraction|weight|ratio|share_|count|volume|usd_amount|dollars)", re.I)
PRICE_KEYS = frozenset({"limit_price", "price", "stop_price", "target_price", "entry_price", "exit_price"})

#: Refusals that are the House's doing, not the strategy's: a maintenance pause or a closed live
#: window refuses every buy of every agent, and must not read as this agent's defect.
HOUSE_REFUSALS = ("paused for maintenance", "allocation window", "this phase permits exits")


def mark_of(state: Mapping[str, Any], agent: Any) -> dict[str, Any] | None:
    """The pre-audit mark for this agent's CURRENT code, or None (a mark on older code is stale)."""
    mark = ((state or {}).get(PREAUDIT_STATE_KEY) or {}).get(agent.id)
    if isinstance(mark, dict) and mark.get("code_sha256") == agent.code_sha256:
        return mark
    return None


# ------------------------------------------------------------------------------ static checks
def _names(node: ast.AST) -> list[str]:
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.append(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.append(sub.attr)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def _cent_digits(call: ast.Call) -> bool:
    """`round(x, 2)`, `round(x, ndigits=1)`, `round(x)`-with-digits-0 is left alone (it is not a
    price rounding anyone writes by accident); `.quantize(Decimal("0.01"))` and coarser."""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "round":
        digits = call.args[1] if len(call.args) >= 2 else next((k.value for k in call.keywords if k.arg == "ndigits"), None)
        return isinstance(digits, ast.Constant) and isinstance(digits.value, int) and not isinstance(digits.value, bool) and 1 <= digits.value <= 2
    if isinstance(func, ast.Attribute) and func.attr == "quantize" and call.args:
        arg = call.args[0]
        if isinstance(arg, ast.Call) and arg.args and isinstance(arg.args[0], ast.Constant) and isinstance(arg.args[0].value, str):
            text = arg.args[0].value.strip()
            return text in ("0.01", "0.1", "1", "1.0", "1.00", ".01", ".1")
    return False


def _rounded(call: ast.Call) -> ast.AST | None:
    if isinstance(call.func, ast.Name):
        return call.args[0] if call.args else None
    if isinstance(call.func, ast.Attribute):
        return call.func.value
    return None


def cent_roundings(code: str) -> list[tuple[int, str]]:
    """Every place the code rounds a PRICE to cents: `(line, source text)`. Conservative on
    purpose -- the rounding must feed something that names a price (a `limit_price`/`price` key,
    or a variable called target, limit, entry, mean, bid ...), and nothing that names a quantity."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    lines = code.splitlines()
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    found: dict[int, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _cent_digits(node):
            continue
        inner = _rounded(node)
        inner_names = _names(inner) if inner is not None else []
        target_names: list[str] = []
        keyed_price = False
        parent = parents.get(id(node))
        if isinstance(parent, ast.Dict):
            for key, value in zip(parent.keys, parent.values):
                if value is node and isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keyed_price = key.value in PRICE_KEYS
                    target_names.append(key.value)
        elif isinstance(parent, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
            for target in targets:
                target_names.extend(_names(target))
        elif isinstance(parent, ast.keyword) and parent.arg:
            target_names.append(parent.arg)
            keyed_price = parent.arg in PRICE_KEYS
        named = target_names + inner_names
        if any(NOT_PRICE_WORDS.search(name) for name in target_names):
            continue
        if not keyed_price and not any(PRICE_WORDS.search(name) for name in named):
            continue
        if not keyed_price and any(NOT_PRICE_WORDS.search(name) for name in inner_names) and not any(PRICE_WORDS.search(n) for n in target_names):
            continue
        line = getattr(node, "lineno", 0)
        found.setdefault(line, (lines[line - 1].strip() if 0 < line <= len(lines) else "")[:200])
    return sorted(found.items())


def _symbols(needs: Mapping[str, Any]) -> list[str]:
    out = []
    for key in ("symbols", "universe", "observe"):
        value = (needs or {}).get(key)
        if isinstance(value, (list, tuple)):
            out.extend(str(v) for v in value)
    return out


def _low_priced(symbols: Sequence[str]) -> list[str]:
    return [s for s in symbols if re.split(r"[/\-]", s.upper())[0] in LOW_PRICED]


# ------------------------------------------------------------------------------------ the pass
class PreAudit:
    def __init__(self, ledger: Any, *, clock: Callable[[], float] = time.time, settings: Mapping[str, Any] | None = None,
                 escalate: Callable[..., Any] | None = None):
        self.ledger = ledger
        self.clock = clock
        self.settings = {**DEFAULTS, **dict(settings or {})}
        #: OFF. A future short model check on red flags only, bounded at a few cents on the cheapest
        #: adequate route. `(agent, flags) -> {"note": str}`; nothing on the floor passes one.
        self.escalate = escalate
        self._last = 0.0
        self._static: dict[str, list[tuple[int, str]]] = {}  # code sha -> cent roundings

    def due(self) -> bool:
        if not self.settings.get("enabled", True):
            return False
        return self.clock() - self._last >= float(self.settings["every_seconds"])

    # ------------------------------------------------------------------ one agent
    def _origin(self, agent_id: str) -> Any:
        return self.ledger.last("agent.strategy", agent=agent_id) or self.ledger.last("agent.born", agent=agent_id)

    def _check(self, house: Any, agent: Any, rung_entered: int) -> dict[str, Any]:
        s = self.settings
        book = house.book_of(agent) if hasattr(house, "book_of") else None
        book_name = getattr(book, "name", None)
        flags: list[str] = []
        evidence: list[dict[str, Any]] = []
        severity = "medium"
        facts: list[str] = []

        # 1. the code. Cent rounding only matters where a cent is a large part of the price.
        sha = agent.code_sha256
        if sha not in self._static:
            self._static[sha] = cent_roundings(agent.code or "")
        roundings = self._static[sha]
        fills = [e for e in self.ledger.read(kinds="book.fill", agent=agent.id, after=0, limit=2000, newest=True)
                 if book_name is None or e.payload.get("book") == book_name]
        if roundings and str(agent.venue).startswith("alpaca"):
            cheap = _low_priced(_symbols(agent.needs))
            sub_dollar = []
            for entry in fills:
                try:
                    price = float(entry.payload.get("price") or 0)
                except (TypeError, ValueError):
                    continue
                # A cent IS the tick of a Kalshi contract and of an option premium under $3, so only
                # a coin or a share under a dollar (Alpaca quotes those to 1/10000) is evidence.
                if 0 < price < 1 and ((entry.payload.get("instrument") or {}).get("asset_class") not in ("event", "option")):
                    sub_dollar.append(entry)
            if cheap or sub_dollar:
                where = ", ".join(cheap[:6]) or f"{len(sub_dollar)} fill(s) under $1"
                flags.append("cent_rounding")
                severity = "high"
                origin = self._origin(agent.id)
                for line, text in roundings[:4]:
                    evidence.append({"seq": origin.seq if origin else 0, "at": origin.at if origin else now_iso(self.clock), "agent": agent.id,
                                     "excerpt": f"line {line}: {text} -- rounds a price to cents while it trades {where}"[:600]})
                for entry in sub_dollar[:2]:
                    evidence.append({"seq": entry.seq, "at": entry.at, "agent": agent.id,
                                     "excerpt": f"filled {entry.payload.get('side')} {(entry.payload.get('instrument') or {}).get('symbol')} at "
                                                f"{entry.payload.get('price')}: a cent there is {100 * 0.01 / max(float(entry.payload.get('price') or 1), 1e-9):.1f}% of the price"})
                facts.append(f"{len(roundings)} cent rounding(s) of a price (line {', '.join(str(l) for l, _ in roundings[:4])}) on {where}")

        # 2. the behaviour, once it has had its first few paper wakes.
        wakes = [e for e in self.ledger.read(kinds="agent.woke", agent=agent.id, after=rung_entered, limit=2000)
                 if book_name is None or e.payload.get("book") in (None, book_name)]
        final = len(wakes) >= int(s["wakes"])
        if final:
            errors = [e for e in wakes if e.payload.get("ok") is False]
            dropped_rows = [e for e in wakes if e.payload.get("dropped")]
            dropped = sum(len(e.payload["dropped"]) if isinstance(e.payload["dropped"], list) else int(e.payload["dropped"] or 0) for e in dropped_rows)
            sent = sum(int(e.payload.get("intents") or 0) for e in wakes if e.payload.get("ok") is not False)
            refusals = [e for e in self.ledger.read(kinds="book.refused", agent=agent.id, after=rung_entered, limit=2000)
                        if (book_name is None or e.payload.get("book") == book_name)
                        and not any(h in "; ".join(str(r) for r in e.payload.get("reasons") or []) for h in HOUSE_REFUSALS)]
            offered = [e for e in wakes if int(e.payload.get("offered") or 0) > 0]
            barren = [e for e in offered if e.payload.get("barren")]
            new_fills = [e for e in fills if e.seq > rung_entered]
            error_rate = len(errors) / len(wakes)
            refusal_rate = len(refusals) / max(1, sent)  # a book refusal is one of the intents the wake sent
            barren_rate = len(barren) / len(offered) if offered else 0.0
            facts.append(f"{len(wakes)} paper wakes: {len(errors)} raised ({error_rate:.0%}), {dropped} intent(s) dropped, "
                         f"{len(refusals)} refused of {sent} sent ({refusal_rate:.0%}), "
                         f"{len(barren)} of {len(offered)} live-market wakes did nothing ({barren_rate:.0%}), {len(new_fills)} fill(s)")
            if errors and error_rate >= float(s["error_rate"]):
                flags.append("errors")
                severity = "high"
                evidence += [{"seq": e.seq, "at": e.at, "agent": agent.id, "excerpt": f"decide raised: {str(e.payload.get('error'))[:300]}"} for e in errors[:3]]
            if dropped >= int(s["dropped"]):
                flags.append("dropped_intents")
                evidence += [{"seq": e.seq, "at": e.at, "agent": agent.id,
                              "excerpt": "dropped: " + "; ".join(str(d) for d in (e.payload["dropped"] if isinstance(e.payload["dropped"], list) else []))[:300]}
                             for e in dropped_rows[:3]]
            if refusals and refusal_rate >= float(s["refusal_rate"]):
                flags.append("refusals")
                evidence += [{"seq": e.seq, "at": e.at, "agent": agent.id,
                              "excerpt": "refused: " + "; ".join(str(r) for r in e.payload.get("reasons") or [])[:300]} for e in refusals[:3]]
            if len(offered) >= int(s["wakes"]) and not new_fills and barren_rate >= float(s["barren_rate"]):
                flags.append("barren")
                evidence += [{"seq": e.seq, "at": e.at, "agent": agent.id,
                              "excerpt": f"{e.payload.get('offered')} live market(s) offered, nothing done ({e.payload.get('barren')} in a row)"} for e in barren[-2:]]
        return {"flags": flags, "evidence": evidence[:12], "severity": severity, "final": final, "wakes": len(wakes), "facts": facts}

    # -------------------------------------------------------------------- the pass
    def run(self, house: Any) -> list[dict[str, Any]]:
        """One pass over the paper agents. Returns what it concluded for each agent it looked at."""
        self._last = self.clock()
        if not self.settings.get("enabled", True):
            return []
        results: list[dict[str, Any]] = []
        marks = house._state.get(PREAUDIT_STATE_KEY) or {}
        looked = 0
        for agent in list(house.registry.living()):
            if looked >= int(self.settings["max_agents_per_run"]):
                break
            try:
                if house.evaluator.rung(agent.id) != 1:
                    continue
                rung_entered = int(house.evaluator._rung_entered(agent.id))
                old = marks.get(agent.id) if isinstance(marks.get(agent.id), dict) else None
                same = bool(old and old.get("code_sha256") == agent.code_sha256 and old.get("rung_entered") == rung_entered)
                if same and old.get("final"):
                    continue
                looked += 1
                results.append(self._conclude(house, agent, rung_entered, old if same else None))
            except Exception as exc:  # noqa: BLE001 - one agent's odd record is that agent skipped, not the pass
                results.append({"agent": agent.id, "skipped": f"{type(exc).__name__}: {str(exc)[:160]}"})
        return results

    def _reported_before(self, agent_id: str, sha: str, rung_entered: int) -> list[str]:
        """What was already reported for this code and rung when the mark itself is gone (a restart
        before the House saved its state): the ledger rows are the record, not house.json."""
        flags: list[str] = []
        for final in (False, True):
            entry = self.ledger.get(f"preaudit:{agent_id}:{sha[:12]}:{rung_entered}:{final}")
            if entry is not None:
                match = re.search(r" shows ([a-z_, ]+)\. ", str(entry.payload.get("summary") or ""))
                flags += [f.strip() for f in (match.group(1).split(",") if match else []) if f.strip() and f.strip() not in flags]
        return flags

    def _conclude(self, house: Any, agent: Any, rung_entered: int, old: Mapping[str, Any] | None) -> dict[str, Any]:
        found = self._check(house, agent, rung_entered)
        flags = found["flags"]
        sha = agent.code_sha256
        key = f"strategy_defect:{agent.id}:{sha[:12]}" if flags else None
        reported = list((old or {}).get("reported") or []) if old else self._reported_before(agent.id, sha, rung_entered)
        wrote = False
        fresh = [flag for flag in flags if flag not in reported]
        if fresh:
            summary = (f"pre-audit on paper: {agent.id} ({agent.niche}) shows {', '.join(flags)}. " + " ".join(found["facts"])
                       + ". A report, not a verdict: the agent keeps its seat; a corrected child should replace this code.")
            if self.escalate is not None:
                try:
                    note = (self.escalate(agent, flags) or {}).get("note")
                    if note:
                        summary += f" Model check: {str(note)[:400]}"
                except Exception:  # noqa: BLE001 - the optional check never blocks the deterministic report
                    pass
            payload = {"key": key, "kind": "strategy_defect", "summary": summary[:2000], "evidence": found["evidence"],
                       "agents": [agent.id], "source": "audit", "severity": found["severity"]}
            try:
                self.ledger.append("repair.reported", payload, agent=agent.id,
                                   id=f"preaudit:{agent.id}:{sha[:12]}:{rung_entered}:{found['final']}")
                wrote = True
            except LedgerConflict:
                pass  # this code and rung were already reported at this stage
            reported = reported + fresh
        mark = {"at": now_iso(self.clock), "code_sha256": sha, "rung_entered": rung_entered, "final": found["final"],
                "verdict": "red" if flags else "clear", "flags": flags, "repair_key": key, "wakes": found["wakes"], "reported": reported}
        lock = getattr(house, "_state_lock", None) or threading.RLock()
        with lock:
            house._state.setdefault(PREAUDIT_STATE_KEY, {})[agent.id] = mark
            status = (house._state.get("promotion_status") or {}).get(agent.id)
            if isinstance(status, dict) and status.get("code_sha256") == sha:
                status["pre_audit"] = {"verdict": mark["verdict"], "flags": flags, "repair_key": key}
        return {"agent": agent.id, "verdict": mark["verdict"], "flags": flags, "repair_key": key, "final": found["final"], "wrote": wrote}
