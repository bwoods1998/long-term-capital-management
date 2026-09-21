"""The public tape: what the site's five sections are drawn from.

1. Live stream: agents' thoughts, research and trades, and the league's own news (births, replays,
   promotions, audits, deaths), as events.
2. Total profit and running time, 3. the balance chart: the REAL venue accounts (Kalshi and
   Alpaca), read through the gateway and marked every few minutes, against the owner's baseline
   with deposits and withdrawals taken out. Practice money is never added to it.
4. Open and closed positions with the agent's own reason for each.
5. One self-improvement series: after-cost return on the capital at work, by generation.

The site validates every byte (`personal-site/capital/schema.js`; the contract this file is
written against is `league/tests/fixtures/site_contract.md`). One bad event refuses its whole
batch, so everything is cleaned here first: no `<`, no control characters, no credential shapes,
no links the site does not allow, exact timestamp and money formats. Rows marked private on the
ledger, and private keys, never leave.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from .constitution import CONSTITUTION
from .ledger import HOUSE, Entry, canonical, now_iso, public_view

ZERO = Decimal(0)
MAX_BATCH = 100
MARK_EVERY_SECONDS = 300
ALLOWED_LINK_HOSTS = ("sec.gov", "www.sec.gov", "efts.sec.gov", "blakewoods.us", "github.com", "kalshi.com", "finance.yahoo.com")
RESEARCH_TOOLS = ("web_search", "library_search", "library_read", "library_write", "replay", "request_tool", "playbook_read")

_LINK = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
_SCHEME = re.compile(r"\b(javascript|vbscript|data|file|blob):(?=\S)", re.IGNORECASE)
_SECRET = re.compile(r"\b(sk-|apca-)|\bbearer[ :]", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ID = re.compile(r"[^A-Za-z0-9:_.-]")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")


class PublishError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------------------- cleaning
def clean_text(value: Any, limit: int = 8000) -> str:
    text = str(value if value is not None else "")
    text = _CONTROL.sub(" ", text).replace("<", "‹")

    def link(match: re.Match) -> str:
        url = match.group(0)
        host = re.sub(r"^https://", "", url).split("/")[0].lower()
        return url if url.startswith("https://") and host in ALLOWED_LINK_HOSTS else "[link removed]"

    text = _LINK.sub(link, text)
    text = _SCHEME.sub(lambda m: m.group(1) + ": ", text)
    text = _SECRET.sub("[removed] ", text)
    return text[:limit]


def clean(value: Any, depth: int = 0) -> Any:
    """A payload the site will accept: strings cleaned, keys legal, nothing too deep or too long."""
    if depth > 6:
        return None
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:90]:
            key = str(key)
            if key.startswith("_") or not _KEY.match(key):
                continue
            out[key] = clean(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [clean(item, depth + 1) for item in list(value)[:200]]
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    return clean_text(value)


def money(value: Any, places: int = 2, *, signed: bool = False) -> str:
    """The site's money format: plain digits, at most eight decimals, no exponent."""
    number = Decimal(str(value if value is not None else 0))
    number = number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if number == 0 or (not signed and number < 0):
        number = ZERO.quantize(Decimal(1).scaleb(-places))  # never "-0.00", never a negative where none is allowed
    return format(number, "f")


def event_id(raw: str) -> str:
    return _ID.sub("_", raw)[:200]


def desk_family(family: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", family.lower()).strip("-")[:40] or "league"


def hours_between(start: str | None, end: str) -> float | None:
    from ltcm.broker import instant

    a, b = instant(start) if start else None, instant(end)
    if a is None or b is None:
        return None
    return round(max((b - a).total_seconds(), 0.0) / 3600, 2)


# --------------------------------------------------------------------------------- events
def league_real_pnl(house: Any) -> Decimal:
    """What the league has made or lost with real money: over every real-money book, each account's
    equity less what it was lent (a closed account's is what it kept or lost), the House row's
    fees and dust included. Zero while no real book exists."""
    total = ZERO
    for book in house.books.values():
        if not book.real_money:
            continue
        for name, account in book.accounts.items():
            total += book.equity(name) - account.staked
    return total

def option_label(instrument: Mapping[str, Any]) -> str:
    """`F 10-09 13C`: the underlying, the expiry's month and day, the strike and C or P."""
    try:
        strike = f"{float(instrument.get('strike')):g}"
    except (TypeError, ValueError):
        strike = str(instrument.get("strike"))
    return f"{instrument.get('symbol')} {str(instrument.get('expiry') or '')[5:]} {strike}{str(instrument.get('right') or '?')[:1].upper()}"


def _shown(instrument: Mapping[str, Any]) -> dict[str, Any]:
    shown = {k: instrument.get(k) for k in ("symbol", "asset_class", "market_id", "right") if instrument.get(k) is not None}
    if instrument.get("asset_class") == "option":
        shown["symbol"] = option_label(instrument)
    return shown

def to_events(entry: Entry) -> list[dict[str, Any]]:
    """The site events one ledger row becomes (usually one, sometimes none, a closing fill two)."""
    if not entry.public:
        return []
    p = public_view(entry.payload)
    agent = entry.agent
    desk = f"desk:{agent}"
    out: list[tuple[str, str, str, dict[str, Any]]] = []  # (id suffix, stream, kind, payload)
    kind = entry.kind
    if kind == "agent.thought":
        out.append(("", desk, "desk.thought", {"text": p.get("text"), "session_id": p.get("session") or p.get("phase") or "decide"}))
    elif kind == "agent.research":
        if p.get("tool") in RESEARCH_TOOLS:
            out.append(("", desk, "desk.tool_call", {"tool": p["tool"], "arguments": p.get("arguments") or {}, "session_id": p.get("session") or "research"}))
        elif p.get("tool") == "summary" and str(p.get("summary") or "").strip():
            out.append(("", desk, "desk.thought", {"text": "Research: " + str(p["summary"]), "session_id": p.get("session") or "research"}))
    elif kind == "book.fill" and agent != HOUSE and p.get("source") in ("venue", "cross"):
        instrument = p.get("instrument") or {}
        venue = re.sub(r"[^a-z0-9-]", "-", str(p.get("book") or "book"))[:40]
        shown = _shown(instrument)
        out.append(("", f"broker:{venue}", "broker.fill", {
            "desk_id": agent, "instrument": shown, "side": p.get("side"), "quantity": p.get("quantity"),
            "price": money(p.get("price") or 0, 8).rstrip("0").rstrip(".") or "0", "real_money": bool(p.get("real_money")),
            "rationale_excerpt": str(p.get("reason") or "")[:240],
        }))
        if p.get("side") == "sell" and p.get("realized") is not None:
            out.append(("outcome:", desk, "desk.outcome", {
                "market_id": instrument.get("market_id") or instrument.get("symbol"), "instrument": shown, "result": "sold",
                "pnl": money(p["realized"], 4, signed=True), "rationale_excerpt": str(p.get("entry_reason") or p.get("reason") or "")[:240],
                "real_money": bool(p.get("real_money")), "held_for_hours": hours_between(p.get("opened_at"), entry.at),
                "quantity": p.get("quantity"), "exit_price": p.get("price"),
            }))
    elif kind == "book.settle" and agent != HOUSE:
        instrument = p.get("instrument") or {}
        shown = _shown(instrument)
        out.append(("", desk, "desk.outcome", {
            "market_id": instrument.get("market_id") or instrument.get("symbol"), "instrument": shown, "result": p.get("result"),
            "pnl": money(p.get("pnl") or 0, 4, signed=True), "rationale_excerpt": str(p.get("reason") or "")[:240],
            "real_money": bool(p.get("real_money")), "held_for_hours": hours_between(p.get("opened_at"), entry.at), "quantity": p.get("quantity"),
        }))
    elif kind == "floor.mark" and "real_account_equity" in p:
        # Only marks on the league's basis are published. The first production hour (Sept 19, 2026)
        # recorded the raw account balance, which the first run's leftover contracts were moving;
        # those rows stay on the ledger and off the chart.
        out.append(("", "ops", "floor.mark", {k: p[k] for k in ("account_equity", "account_cash", "as_of", "venues") if k in p}))
    else:
        message = league_news(entry.kind, agent, p)
        if message:
            out.append(("", "lab", "lab.progress", {"message": message, "stage": "learn" if kind.startswith(("eval.", "audit.", "merton.")) else "test", "component": "league"}))
    events = []
    for prefix, stream, site_kind, payload in out:
        payload = payload if site_kind == "floor.mark" else clean({k: v for k, v in payload.items() if v is not None})
        if site_kind == "desk.thought" and not str(payload.get("text") or "").strip():
            continue
        events.append({
            "id": event_id(prefix + entry.id), "stream": stream, "kind": site_kind, "at": entry.at, "payload": payload,
            "digest": hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest(),
        })
    return events


def league_news(kind: str, agent: str, p: Mapping[str, Any]) -> str | None:
    """One plain sentence for the league's own events."""
    if kind == "agent.born":
        origin = f"a child of {p['parent']}" if p.get("parent") else "a founding seed"
        return f"{agent} is born ({origin}, generation {p.get('generation')}, niche {p.get('venue')}/{p.get('horizon')}/{p.get('style')}). {p.get('reason') or ''}".strip()
    if kind == "agent.forked":
        return f"{agent} forked {p.get('child')} and endowed it with ${p.get('endowment_usd')} of its own compute credits."
    if kind == "agent.died":
        return f"{agent} died of {p.get('cause')}. {p.get('detail') or ''}".strip()
    if kind == "eval.trial":
        verdict = "passed" if p.get("passed") else "failed"
        why = "" if p.get("passed") else " " + "; ".join(str(r) for r in (p.get("reasons") or [])[:2]) + "."
        return f"{agent} {verdict} replay: trial {p.get('trials')} for the {p.get('family')} family, {p.get('trades')} trades, deflated Sharpe {_short(p.get('deflated_sharpe'))}.{why}"
    if kind == "eval.verdict" and p.get("decision") in ("promote", "demote", "die"):
        if p["decision"] == "die":
            return f"The evidence ended {agent}: {p.get('reason')}."
        verb = "climbs" if p["decision"] == "promote" else "drops"
        return f"{agent} {verb} from rung {p.get('from_rung')} to rung {p.get('to_rung')}: {p.get('reason')}."
    if kind == "audit.verdict":
        return f"The auditor {'approved' if p.get('approve') else 'vetoed'} {agent} for real money. {p.get('summary') or p.get('error') or ''}".strip()
    if kind == "merton.pass":
        return f"Merton ({p.get('role')}): {p.get('summary') or ''}".strip()
    if kind == "merton.change":
        return f"Merton's change {p.get('branch')}: {p.get('status')}. {p.get('title') or ''}".strip()
    if kind == "ops.alert" and p.get("level") == "error":
        return f"House alert: {p.get('text')}"
    if kind == "ops.deploy":
        if p.get("action") == "deploying":
            return f"New code on main: release {p.get('release')} is on the canary. The watchdog promotes it only if it stays healthy."
        return f"New code on main was refused before the canary: {'; '.join(str(r) for r in (p.get('reasons') or [])[:2])}"
    if kind == "ops.recommendation":
        return f"Capital recommendation: {p.get('summary')}"
    return None


def _short(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


# ------------------------------------------------------------------------------ publisher
class Publisher:
    def __init__(
        self,
        site_url: str,
        token_source: Callable[[], str],
        state_path: str | Path,
        *,
        tape: str | None = None,
        performance: Mapping[str, Any] | None = None,
        real_brokers: Mapping[str, Any] | None = None,
        opener: Any = None,
        clock: Callable[[], float] = time.time,
        gateway_url: str | None = None,
        gateway_token: Callable[[], str] | None = None,
    ):
        base = site_url.rstrip("/") + "/api/capital"
        self.base = base + (f"/t/{tape}" if tape else "")
        self.token_source = token_source
        self.state_path = Path(state_path)
        self.performance = dict(performance or {})
        self.real_brokers = dict(real_brokers or {})
        self.opener = opener or urllib.request.urlopen
        self.clock = clock
        self._state = self._load()
        self._flows = None
        if self.real_brokers and self.performance:
            from ltcm.performance import AccountPerformance

            self._flows = AccountPerformance({**self.performance, "venues": sorted(self.real_brokers)}, self.real_brokers, clock=clock)
        self._venue_rows: dict[str, dict[str, Any]] = {}

    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        state.setdefault("cursor", 0)
        state.setdefault("last_mark", 0.0)
        return state

    def _save(self) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.state_path)

    # --------------------------------------------------------------- transport
    def post(self, path: str, body: Mapping[str, Any]) -> tuple[int, Any]:
        request = urllib.request.Request(
            self.base + path, data=canonical(body).encode("utf-8"), method="POST",
            headers={"Authorization": "Bearer " + self.token_source(), "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ltcm-floor/1.0"},
        )
        try:
            with self.opener(request, timeout=30) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()[:300].decode("utf-8", "replace")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise PublishError(f"the site did not answer: {type(exc).__name__}") from None

    def _send(self, events: list[dict[str, Any]]) -> int:
        """Send a batch; when the site refuses it, halve it until the one bad event is alone, and drop that one."""
        if not events:
            return 0
        status, reply = self.post("/events", {"schema_version": 1, "events": events})
        if status == 200:
            return len(events)
        if status in (400, 409) and len(events) > 1:
            half = len(events) // 2
            return self._send(events[:half]) + self._send(events[half:])
        if status in (400, 409):
            return 0  # one event the site will never take: skipped, so it cannot block the tape
        raise PublishError(f"the site refused the events: HTTP {status} {reply}", status=status)

    # ------------------------------------------------------------------ publish
    def publish(self, house: Any) -> dict[str, Any]:
        self.mark_floor(house)
        sent = 0
        while True:
            batch = house.ledger.read(after=int(self._state["cursor"]), limit=400, public_only=False)
            if not batch:
                break
            events: list[dict[str, Any]] = []
            for entry in batch:
                events.extend(to_events(entry))
            for start in range(0, len(events), MAX_BATCH):
                sent += self._send(events[start:start + MAX_BATCH])
            self._state["cursor"] = batch[-1].seq
            self._save()
        body = self.checkpoint(house)
        status, reply = self.post("/checkpoint", body)
        if status not in (200, 409):
            raise PublishError(f"the site refused the checkpoint: HTTP {status} {reply}", status=status)
        return {"events": sent, "checkpoint": status}

    # -------------------------------------------------------------- real accounts
    def account(self, house: Any = None) -> dict[str, Any] | None:
        """The real venue accounts, read now. A venue that does not answer keeps its last good row,
        marked stale, and a floor with a stale row publishes no profit figure.

        `account_equity`, the number the public chart draws, is on the LEAGUE'S BASIS: the balance
        the accounts held when the record began (`performance.start_equity`) plus what the league's
        own real-money trading has made since. The owner's decision of Sept 19, 2026: the chart is
        flat until the league trades real money. The raw balance also moves for reasons that are
        not the league's (the owner's transfers; the contracts the first run left behind, marked to
        market until they settle), and it is published beside it as `real_account_equity`."""
        if not self.real_brokers:
            return None
        rows = []
        for venue in sorted(self.real_brokers):
            try:
                balance = self.real_brokers[venue].balance()
                row = {"venue": venue, "equity": money(balance.equity, 4), "cash": money(balance.cash, 4), "as_of": now_iso(self.clock)}
                self._venue_rows[venue] = row
            except Exception:  # noqa: BLE001
                row = self._venue_rows.get(venue)
                if row is None:
                    return None
                row = {**row, "stale": True}
            rows.append(row)
        real = sum(Decimal(r["equity"]) for r in rows)
        start = self.performance.get("start_equity")
        shown = Decimal(str(start)) + league_real_pnl(house) if start is not None and house is not None else real
        return {
            "account_equity": money(shown, 4),
            "real_account_equity": money(real, 4),
            "account_cash": money(sum(Decimal(r["cash"]) for r in rows), 4),
            "venues": rows,
        }

    def mark_floor(self, house: Any) -> None:
        now = self.clock()
        if now - float(self._state["last_mark"]) < MARK_EVERY_SECONDS:
            return
        account = self.account(house)
        if account is None or any(row.get("stale") for row in account["venues"]):
            return
        self._state["last_mark"] = now
        self._account = account
        house.ledger.append("floor.mark", {**account, "as_of": now_iso(self.clock)})

    # ---------------------------------------------------------------- checkpoint
    def checkpoint(self, house: Any) -> dict[str, Any]:
        # The accounts are read first: the site refuses a checkpoint whose venue readings are
        # stamped later than the checkpoint itself (found on the first live publish).
        account = self.account(house)
        at = now_iso(self.clock)
        ledger = house.ledger
        desks, curve_rows = [], {}
        spend = {"tokens": ZERO, "boxes": ZERO, "search": ZERO, "other": ZERO}
        spend_today = dict(spend)
        for entry in ledger.iter(kinds="credit.charge"):
            amount = Decimal(entry.payload["usd"])
            what = entry.payload.get("what", "")
            bucket = "tokens" if "token" in what else ("boxes" if "sandbox" in what else ("search" if what == "web search" else "other"))
            spend[bucket] += amount
            if entry.at[:10] == at[:10]:
                spend_today[bucket] += amount
        living, dead = list(house.registry.living()), list(house.registry.dead())
        displayed = {a.id for a in living + dead[-8:]}
        # The roster is bounded for the site, but the experiment includes every agent ever born.
        # Removing an old loser from the display must never remove its loss or research cost.
        for agent in living + dead:
            row, generation = self._desk(house, agent, at)
            if agent.id in displayed:
                desks.append(row)
            g = curve_rows.setdefault(agent.generation, {"desks": 0, "decisions": 0, "cost": ZERO, "pnl": ZERO, "capital": ZERO})
            g["desks"] += 1
            g["decisions"] += generation["decisions"]
            g["cost"] += generation["cost"]
            g["pnl"] += generation["pnl"]
            g["capital"] += generation["capital"]
        curve = []
        for generation in sorted(curve_rows)[:40]:
            g = curve_rows[generation]
            excess = ((g["pnl"] - g["cost"]) / g["capital"] * 100) if g["capital"] > 0 else ZERO
            curve.append({
                "generation": int(generation), "desks": min(g["desks"], 100), "decisions": g["decisions"], "cost_usd": money(g["cost"], 4),
                "pnl_usd": money(g["pnl"], 4, signed=True), "cost_adjusted_excess_pct": money(excess, 4, signed=True), "brier": None,
                "pnl_per_inference_usd": money(g["pnl"] / g["cost"], 4, signed=True) if g["cost"] > 0 else "0",
            })
        started = next(iter(ledger.read(kinds="ops.started", limit=1)), None)
        started_at = started.at if started else at
        practice_equity = sum((book.total_equity() for book in house.books.values() if not book.real_money), ZERO)
        floor: dict[str, Any] = {
            "equity": money(Decimal(account["account_equity"]) if account else practice_equity, 4),
            "cash": money(Decimal(account["account_cash"]) if account else ZERO, 4),
            "daily_pnl": "0", "capital_usd": money(self.performance.get("start_equity") or 0, 4), "since_inception_pct": "0", "benchmark": None,
            "live_desks": sum(1 for d in desks if d["mode"] == "live" and d["status"] == "active"),
            "shadow_desks": sum(1 for d in desks if d["mode"] == "shadow" and d["status"] == "active"),
        }
        pnl_total = ZERO
        if account:
            # The site's schema is exact: the raw balance stays on the ledger's floor.mark rows.
            floor.update({k: v for k, v in account.items() if k != "real_account_equity"})
            if self._flows is not None:
                performance = self._flows.read({"venues": account["venues"]}, at)
                # `account_equity` is already on the league's basis (see `account`): start + the league's
                # own real-money result. Nothing else moves it, so there is nothing to subtract.
                if performance.get("net_flows") is not None:
                    performance["net_flows"] = "0"
                floor["performance"] = performance
                if performance.get("net_flows") is not None:
                    pnl_total = Decimal(account["account_equity"]) - Decimal(str(performance["start_equity"])) - Decimal(str(performance["net_flows"]))
                    floor["since_inception_pct"] = money(pnl_total / Decimal(str(performance["start_equity"])) * 100, 4, signed=True)
        # Frontier consultations and audits are charged to agent credits too, but are not Sail
        # expenses. Prefer the actual Sail balance-debit meter, which also sees the House box and
        # unassigned infrastructure. Without it, publish only the attributed Sail estimate.
        sail_total = spend["tokens"] + spend["boxes"] + spend["search"]
        sail_today = spend_today["tokens"] + spend_today["boxes"] + spend_today["search"]
        metered = [e for e in ledger.iter(kinds="ops.budget") if e.payload.get("what") == "sail" and e.payload.get("spent_usd") is not None]
        if metered:
            sail_total = sum((Decimal(e.payload["spent_usd"]) for e in metered), ZERO)
            sail_today = sum((Decimal(e.payload["spent_usd"]) for e in metered if e.at[:10] == at[:10]), ZERO)
        pacer = getattr(house, "pacer", None)
        daily_cap = pacer.allowance("sail") if pacer is not None else Decimal(house.game["economy"]["daily_pool_usd"])
        wakes = ledger.count(kinds="agent.woke")
        body = {
            "schema_version": 1,
            "published_at": at,
            "floor": floor,
            "desks": desks,
            "committee": {"last_memo_at": None, "allocations": {d["id"]: d["capital_usd"] for d in desks if d["status"] == "active"}},
            "budget": {"spent_today_usd": money(sail_today, 4), "cap_usd": money(daily_cap, 2),
                       "mode": "stopped" if (house.budget is not None and house.budget.mode == "stopped") else "open"},
            "infra": {"host": "sailbox" if os.environ.get("SAILBOX_ID") or Path("/workspace").exists() else "local"},
            "run": {
                "started_at": started_at, "uptime_seconds": int(max(self.clock() - _epoch(started_at), 0)), "availability_7d_pct": None,
                "sessions_total": wakes, "sessions_today": min(wakes, sum(1 for e in ledger.read(kinds="agent.woke", limit=10000, newest=True) if e.at[:10] == at[:10])),
                "decisions_total": ledger.count(kinds="agent.intent"),
                "sail_model_spend_today_usd": money(spend_today["tokens"], 4), "sail_model_spend_total_usd": money(spend["tokens"], 4),
                "sail_infra_spend_total_usd": money(spend["boxes"], 4), "sail_spend_total_usd": money(sail_total, 4),
                "pnl_total_usd": money(pnl_total, 4, signed=True),
                "pnl_per_sail_dollar": money(pnl_total / sail_total, 4, signed=True) if sail_total > 0 else None,
                "models_used": self._models_used(house, spend["tokens"]),
            },
            "lab": {"experiments": [], "curve": curve, "calibration": {"n": 0, "brier": None}},
        }
        return body

    @staticmethod
    def _models_used(house: Any, token_spend: Decimal) -> list[str]:
        from ltcm.provider import DISPLAY_NAMES, PROFILES
        from .frontier import MODEL

        profiles = {str(e.payload["profile"]) for e in house.ledger.iter(kinds="provider.request") if e.payload.get("profile")}
        if not profiles and token_spend > 0:
            # Older research charges did not carry a profile. The configured profile is the best
            # available attribution for those rows, rather than a hardcoded model from launch day.
            profiles.add(str((house.game.get("research") or {}).get("profile", "flash_flex")))
        models = set()
        for profile in profiles:
            model = PROFILES[profile][0] if profile in PROFILES else profile
            models.add(DISPLAY_NAMES.get(model, model))
        if any(Decimal(str(e.payload.get("cost_usd") or 0)) > 0 for e in house.ledger.iter(kinds=("merton.pass", "audit.verdict"))):
            frontier = getattr(getattr(house, "merton", None), "frontier", None)
            models.add(str(getattr(frontier, "model", MODEL)))
        return [clean_text(model, 40) for model in sorted(models)[:8]]

    def _desk(self, house: Any, agent: Any, at: str) -> tuple[dict[str, Any], dict[str, Any]]:
        rung = house.evaluator.rung(agent.id)
        book = house.book_of(agent) if agent.alive else next((b for b in house.books.values() if agent.id in b.accounts), None)
        account = book.account(agent.id) if book is not None and agent.id in book.accounts else None
        staked = account.staked if account else ZERO
        capital = staked if staked > 0 else Decimal(CONSTITUTION["rungs"]["1"]["stake_usd"]) if account else ZERO
        equity = book.equity(agent.id) if account else ZERO
        pnl = (equity - staked) if account and staked > 0 else (account.realized if account else ZERO)
        cost = sum((Decimal(e.payload["usd"]) for e in house.ledger.iter(kinds="credit.charge", agent=agent.id)), ZERO)
        intents = house.ledger.count(kinds="agent.intent", agent=agent.id)
        verdicts = list(house.ledger.iter(kinds="eval.verdict", agent=agent.id))
        looks = [e.payload for e in verdicts if e.payload.get("decision") == "look"]
        moves = [e for e in verdicts if e.payload.get("decision") in ("promote", "demote")]
        lifecycle = {"born_at": agent.born_at, "died_at": agent.died_at, "cause": agent.cause,
                     "last_move": {"id": moves[-1].id, "at": moves[-1].at,
                                   **{k: moves[-1].payload.get(k) for k in ("decision", "from_rung", "to_rung", "reason")}} if moves else None}
        accounting_ok = book.evidence_integrity(agent.id)["ok"] if book is not None else True
        positions = []
        if account and book is not None:
            for holding in list(account.holdings.values())[:50]:
                inst = holding.instrument
                mark = book.marks.get(inst.key) or holding.average_cost
                value = holding.quantity * mark * inst.multiplier
                positions.append({
                    "instrument": {"symbol": option_label(inst.to_dict()) if inst.asset_class == "option" else (inst.market_id or inst.symbol), "asset_class": inst.asset_class, "venue": "kalshi" if agent.venue == "kalshi" else "alpaca",
                                   **({"market_id": inst.market_id} if inst.market_id else {}), **({"right": inst.right} if inst.right else {})},
                    "side": (inst.right or "yes") if inst.asset_class == "event" else "long",
                    "quantity": money(holding.quantity, 8), "entry_price": money(holding.average_cost, 6), "mark_price": money(mark, 6),
                    "market_value": money(value, 4), "unrealized_pnl": money(value - holding.cost, 4, signed=True),
                    "opened_at": min(holding.opened_at or at, at), "thesis": clean_text(holding.reason, 240),
                    "target_price": None, "stop_price": None, "time_stop_at": None, "exit_orders": [],
                })
        next_wake = house._state["next_wake"].get(agent.id)
        born = _epoch(agent.born_at)
        row = {
            "id": agent.id, "name": agent.id, "family": desk_family(agent.family), "generation": int(agent.generation),
            "parent_id": agent.parent if agent.parent != agent.id else None,
            "mode": "live" if (book is not None and book.real_money) else "shadow",
            "venues": ["kalshi" if agent.venue == "kalshi" else "alpaca"],
            "capital_usd": money(capital, 2), "cost_usd": money(cost, 4), "max_drawdown_pct": money(Decimal(str(looks[-1].get("drawdown") or 0)) * 100 if looks else 0, 4),
            "equity": money(equity, 4, signed=True), "cash": money(account.cash if account else 0, 4, signed=True), "daily_pnl": "0",
            "return_pct": money((pnl / capital * 100) if capital > 0 else 0, 4, signed=True),
            "days_live": int(max(self.clock() - born, 0) // 86400), "orders": intents,
            "status": "active" if agent.alive else "retired",
            "gate": {"name": f"rung {rung}", "passed": rung >= 2, "evidence": clean({"decisions": intents, "rung": rung, "credits_usd": money(house.economy.balance(agent.id), 4, signed=True),
                     "niche": agent.niche, "accounting_ok": accounting_ok, "lifecycle": lifecycle,
                     "last_look": {k: looks[-1].get(k) for k in ("look", "active_blocks", "mean", "lcb", "ucb", "alpha_spent")} if looks else None})},
            "updated_at": at, "pnl_usd": money(pnl, 4, signed=True), "positions": positions,
        }
        if agent.alive and next_wake:
            row["next_session_at"] = now_iso(lambda: float(next_wake))
        return row, {"decisions": intents, "cost": cost, "pnl": pnl, "capital": capital}


def _epoch(iso: str) -> float:
    from ltcm.broker import instant

    parsed = instant(iso)
    return parsed.timestamp() if parsed else 0.0
