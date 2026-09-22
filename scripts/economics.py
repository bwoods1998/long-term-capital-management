#!/usr/bin/env python3
"""A read-only economics report over the league ledger. Standard library only.

    python scripts/economics.py --ledger /workspace/state/ledger.sqlite [--since ISO] [--until ISO] [--json]

It is self-contained (no `league` imports) so it runs on the House box through `rx.py`, which
executes the source with `python -c`. Every database is opened `mode=ro` (plus `query_only`); the
report never writes anything anywhere.

What it reports, and the definitions it uses:

1. TRADING P&L AFTER EXECUTION COSTS, real money and practice money in separate sections that are
   never summed together. Real books are `alpaca` and `kalshi`, practice books are `alpaca-paper`
   and `kalshi-shadow` (league/house.py REAL_BOOK / PRACTICE_BOOK). The ledger rows are folded
   exactly as league/book.py folds them (`_apply`, `_apply_account_fill`, league/accounting.py
   `apply_correction`): a holding's cost includes its buy fees and a sale's proceeds are net of
   its sell fee, so the book's own `realized` is already AFTER fees. The report adds back the
   fees inside each closed trade to show gross realized, fees and net side by side. Alpaca crypto
   buy fees are taken in kind (fewer units); they are valued at the fill price, as an estimate.
   The House row (venue fee activities, dust, internal-cross balancing) is shown separately.

   Account returns for REAL money follow the public site's definitions, which this file does not
   change: docs/account-performance.md ("Tracked profit = current account equity - opening mark -
   subsequent net external deposits. Withdrawals are negative deposits") as superseded by
   league/publish.py `Publisher.account` / `Publisher.checkpoint` (the owner's decision of
   Sept 19, 2026): the chart's `account_equity` is on the LEAGUE'S BASIS, i.e.
   `performance.start_equity` (league/config.json) plus `league_real_pnl`, which is, over every
   real-money book, each account's equity less what it was lent (House row included). Nothing
   else moves it, so the checkpoint sets net_flows to 0 and
   `pnl_total = account_equity - start_equity`, `since_inception_pct = pnl_total / start_equity`.
   The raw venue balance (`real_account_equity`) also moves with the owner's transfers and the
   first run's leftover contracts; the deposits/withdrawals needed to turn it into a return are
   read live from venue funding APIs (ltcm/performance.py) and are NOT recorded in the ledger,
   so the report says so instead of inventing that number.

2. MODEL AND INFRASTRUCTURE SPEND BY PROVIDER, each line labelled with its basis:
   - OpenAI gpt-5.6-luna via the gateway: `provider.request` rows (cost_verified by the gateway).
   - OpenAI gpt-6-astra via the gateway (gateway cost header): `merton.pass` (every Merton role,
     consultant included), `audit.verdict`, `agent.research` research_grant (completed) and
     semantic_question_experiment rows, `ops.budget` phase1-frontier-probe. The agent credit
     charges "merton's time" / "frontier audit" duplicate these and are shown only as checks.
   - Sail: the balance-debit meter (`ops.budget` what=sail spent_usd, as the site uses it), and
     the attributed estimate (research-token charges of sessions whose `agent.research`
     tool=summary profile is a Sail profile, plus sandbox seconds).
   - Jev (TypeSafe, jev-1.13.0): "jev classification" credit charges, plus the semantic lab's own
     task costs from semantic.sqlite beside the ledger when it can be read (not in the ledger).
   - Web search: the flat internal "web search" charge.

3. USEFUL WORK PER DOLLAR: unique replay-passing candidates (`agent.research` tool=candidate,
   status retained, `_candidate.passed` true; the box ledger keeps `_` keys, a public copy strips
   them), adoptions of replay-passing code (House.research: rung-0 in-place adoption =
   eval.verdict promote "its new code passed replay...", rung-1 in-place rewrite =
   agent.strategy passed_replay true, and forks = eval.verdict seat "its code passed replay as
   its parent's candidate"), and verified repairs (`repair.status` state verified). The
   denominator is research model spend (research tokens of both providers + Merton consults +
   research grants + Jev classify charges; sandbox seconds excluded) and is printed.

4. SAMPLE-SIZE WARNINGS.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

ZERO = Decimal(0)
HOUSE = "house"
REAL_BOOK = {"alpaca": "alpaca", "kalshi": "kalshi"}  # league/house.py
PRACTICE_BOOK = {"alpaca": "alpaca-paper", "kalshi": "kalshi-shadow"}  # league/house.py
LUNA_PROFILE = "openai_luna"  # league/fast_research.py PROFILE
MERTON_HOUSE_ROLES = ("architect", "toolsmith", "operator", "designer", "teacher")

MIN_CLOSED_TRADES = 30
MIN_ADOPTIONS = 5
MIN_CANDIDATES = 5
MIN_WINDOW_HOURS = 24.0
TINY_REAL_STAKE_USD = Decimal("250")

DOC = "docs/account-performance.md"
DOC_CODE = "league/publish.py (Publisher.account, Publisher.checkpoint, league_real_pnl)"

ADOPT_PROMOTE_REASON = "its new code passed replay against every trial in its own line"
NEWBORN_PROMOTE_REASON = "passed replay against every trial in its own line"
ADOPT_SEAT_REASON = "its code passed replay as its parent's candidate"


# ----------------------------------------------------------------------------- basics
def D(value) -> Decimal:
    if value is None or value == "":
        return ZERO
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ZERO
    return out if out.is_finite() else ZERO


def connect_ro(path: str) -> sqlite3.Connection:
    """Open a SQLite file read-only. A write through this connection fails."""
    absolute = os.path.abspath(path)
    if not os.path.exists(absolute):
        raise FileNotFoundError(absolute)
    conn = sqlite3.connect(f"file:{urllib.parse.quote(absolute)}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def iso(value: str | None) -> str | None:
    """Any ISO date or time, as the ledger's `YYYY-MM-DDTHH:MM:SS.mmmZ` in UTC."""
    if value is None:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if len(text) == 10:
        text += "T00:00:00+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def epoch(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def inside(at: str, since: str | None, until: str | None) -> bool:
    return (since is None or at >= since) and (until is None or at < until)


def rows(conn: sqlite3.Connection, kinds, *, until: str | None = None, tools=None):
    """(seq, kind, agent, at, payload) in ledger order for the given kinds, up to `until`."""
    kinds = [kinds] if isinstance(kinds, str) else list(kinds)
    sql = f"SELECT seq, kind, agent, at, payload FROM ledger WHERE kind IN ({','.join('?' * len(kinds))})"
    args: list = list(kinds)
    if until is not None:
        sql += " AND at < ?"
        args.append(until)
    filtered = False
    if tools:
        try:
            conn.execute("SELECT json_extract('{\"a\":1}', '$.a')").fetchone()
            sql += f" AND json_extract(payload, '$.tool') IN ({','.join('?' * len(tools))})"
            args += list(tools)
            filtered = True
        except sqlite3.OperationalError:
            filtered = False
    for seq, kind, agent, at, payload in conn.execute(sql + " ORDER BY seq", args):
        try:
            p = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(p, dict):
            continue
        if tools and not filtered and p.get("tool") not in tools:
            continue
        yield seq, kind, agent, at, p


def ledger_span(conn) -> tuple[str | None, str | None, int]:
    first, last, count = conn.execute("SELECT MIN(at), MAX(at), COUNT(*) FROM ledger").fetchone()
    return first, last, int(count or 0)


def section_of(book: str, real_money) -> str:
    if book in REAL_BOOK.values():
        return "real"
    if book in PRACTICE_BOOK.values():
        return "practice"
    return "real" if real_money else "practice"


def venue_of(book: str) -> str:
    for mapping in (REAL_BOOK, PRACTICE_BOOK):
        for venue, name in mapping.items():
            if name == book:
                return venue
    return book


def instrument_key(d) -> str:
    """ltcm/broker.py Instrument.key, from an instrument dict."""
    d = d or {}
    parts = [str(d.get("asset_class")), str(d.get("symbol")), str(d.get("venue"))]
    if d.get("expiry"):
        parts.append(str(d["expiry"]))
    if d.get("strike") is not None:
        parts.append(format(D(d["strike"]), "f"))
    right = d.get("right") or ("yes" if d.get("asset_class") == "event" else None)
    if right:
        parts.append(str(right))
    market = d.get("market_id")
    if market and not (d.get("asset_class") == "crypto" and market == d.get("symbol")):
        parts.append(str(market))
    return ":".join(parts)


# --------------------------------------------------------------------------- trading
def _window_stats() -> dict:
    return {"closed_trades": 0, "wins": 0, "losses": 0, "realized_gross": ZERO, "fees_on_closed": ZERO,
            "realized_net": ZERO, "house_row": ZERO, "net_after_costs": ZERO, "fees_paid": ZERO,
            "in_kind_fee_estimate": ZERO, "venue_fee_rows": 0, "fills": 0, "settlements": 0,
            "corrections": 0, "stakes_lent": ZERO, "stakes_returned": ZERO}


def trading(conn, since: str | None = None, until: str | None = None) -> dict:
    """Fold book rows per book and account, as league/book.py does, and total the window."""
    books: dict[str, dict] = {}

    def book_state(name: str, real_money) -> dict:
        if name not in books:
            books[name] = {"book": name, "venue": venue_of(name), "section": section_of(name, real_money),
                           "known": name in REAL_BOOK.values() or name in PRACTICE_BOOK.values(),
                           "accounts": {}, "house_cash": ZERO, "house_cash_before": ZERO,
                           "window": _window_stats(), "baseline_rows": 0}
        return books[name]

    def account(state: dict, agent: str) -> dict:
        acct = state["accounts"].get(agent)
        if acct is None:
            acct = state["accounts"][agent] = {"staked": ZERO, "cash": ZERO, "realized": ZERO, "fees": ZERO, "holdings": {}}
        return acct

    def close(w: dict, piece: Decimal, fee_part: Decimal, *, counted: bool) -> None:
        w["realized_net"] += piece
        w["fees_on_closed"] += fee_part
        if counted:
            w["closed_trades"] += 1
            if piece > 0:
                w["wins"] += 1
            elif piece < 0:
                w["losses"] += 1

    kinds = ("book.stake", "book.fill", "book.fill_correction", "book.settle", "book.baseline")
    for _seq, kind, agent, at, p in rows(conn, kinds, until=until):
        name = p.get("book")
        if not name:
            continue
        state = book_state(str(name), p.get("real_money"))
        w = state["window"]
        now = inside(at, since, None)
        if kind == "book.baseline":
            state["baseline_rows"] += 1
            continue
        if kind == "book.stake":
            usd = D(p.get("usd"))
            acct = account(state, agent)
            acct["staked"] += usd
            acct["cash"] += usd
            if now:
                w["stakes_lent" if usd > 0 else "stakes_returned"] += abs(usd)
            continue
        if kind == "book.fill":
            cash_delta, position_delta, fee = D(p.get("cash_delta")), D(p.get("position_delta")), D(p.get("fee_usd"))
            source = p.get("source")
            if agent == HOUSE:
                state["house_cash"] += cash_delta
                if not now:
                    state["house_cash_before"] += cash_delta
                else:
                    w["house_row"] += cash_delta
                    w["fees_paid"] += fee
                    w["venue_fee_rows"] += int(source == "venue-fee")
                continue
            acct = account(state, agent)
            acct["cash"] += cash_delta
            acct["fees"] += fee
            inst = p.get("instrument") or {}
            in_kind = ZERO
            if D(p.get("fee_quantity")) > 0:
                in_kind = D(p.get("fee_quantity")) * D(p.get("price")) * (D(inst.get("multiplier")) or Decimal(1))
            if now:
                w["fees_paid"] += fee
                w["in_kind_fee_estimate"] += in_kind
                w["fills"] += int(source != "dust")
            if position_delta == 0:
                continue
            key = instrument_key(inst)
            holding = acct["holdings"].get(key)
            if holding is None:
                holding = acct["holdings"][key] = {"quantity": ZERO, "cost": ZERO, "fees": ZERO}
            if position_delta > 0:
                holding["quantity"] += position_delta
                holding["cost"] += -cash_delta
                holding["fees"] += fee + in_kind
            else:
                sold = -position_delta
                if holding["quantity"] > 0:
                    basis = holding["cost"] * sold / holding["quantity"]
                    fee_basis = holding["fees"] * sold / holding["quantity"]
                else:
                    basis = fee_basis = ZERO
                piece = cash_delta - basis
                acct["realized"] += piece
                holding["quantity"] -= sold
                holding["cost"] -= basis
                holding["fees"] -= fee_basis
                if now:
                    close(w, piece, fee_basis + fee, counted=source != "dust")
            if holding["quantity"] <= 0:
                del acct["holdings"][key]
            continue
        if kind == "book.settle":
            payout = D(p.get("payout"))
            if agent == HOUSE:
                state["house_cash"] += payout
                if not now:
                    state["house_cash_before"] += payout
                else:
                    w["house_row"] += payout
                continue
            acct = account(state, agent)
            acct["cash"] += payout
            holding = acct["holdings"].pop(instrument_key(p.get("instrument")), None)
            if holding is not None:
                piece = payout - holding["cost"]
                acct["realized"] += piece
                if now:
                    w["settlements"] += 1
                    close(w, piece, holding["fees"], counted=True)
            continue
        if kind == "book.fill_correction":
            acct = account(state, agent)
            acct["cash"] += D(p.get("cash_delta"))
            acct["fees"] += D(p.get("fees_delta"))
            acct["realized"] += D(p.get("realized_delta"))
            deltas = p.get("holding_cost_deltas") or {}
            for key, delta in deltas.items():
                if key in acct["holdings"]:
                    acct["holdings"][key]["cost"] += D(delta)
            if deltas:
                first = next((k for k in deltas if k in acct["holdings"]), None)
                if first:
                    acct["holdings"][first]["fees"] += D(p.get("fees_delta"))
            if now:
                w["corrections"] += 1
                w["fees_paid"] += D(p.get("fees_delta"))
                w["realized_net"] += D(p.get("realized_delta"))
                if not deltas:
                    w["fees_on_closed"] += D(p.get("fees_delta"))

    # Marks: each account's equity less what it was lent, at the start and the end of the window.
    start_marks: dict[tuple, dict] = {}
    end_marks: dict[tuple, dict] = {}
    for _seq, _kind, agent, at, p in rows(conn, "book.mark", until=until):
        name = p.get("book")
        if not name:
            continue
        book_state(str(name), p.get("real_money"))
        end_marks[(name, agent)] = p
        if since is not None and at < since:
            start_marks[(name, agent)] = p

    for name, state in books.items():
        w = state["window"]
        w["realized_gross"] = w["realized_net"] + w["fees_on_closed"]
        w["net_after_costs"] = w["realized_net"] + w["house_row"]
        marks_end = {a: p for (b, a), p in end_marks.items() if b == name}
        marks_start = {a: p for (b, a), p in start_marks.items() if b == name}
        value_end = sum((D(p.get("equity")) - D(p.get("staked")) for p in marks_end.values()), ZERO) + state["house_cash"]
        value_start = (sum((D(p.get("equity")) - D(p.get("staked")) for p in marks_start.values()), ZERO)
                       + state["house_cash_before"]) if since is not None else ZERO
        state["mark_to_market"] = {"equity_less_staked_end": value_end, "equity_less_staked_start": value_start,
                                   "change": value_end - value_start, "accounts_marked": len(marks_end)}
        accounts = {a: acct for a, acct in state["accounts"].items()}
        state["staked_outstanding"] = sum((acct["staked"] for acct in accounts.values()), ZERO)
        state["funded_accounts"] = sum(1 for acct in accounts.values() if acct["staked"] > 0)
        state["open_lots"] = sum(len(acct["holdings"]) for acct in accounts.values())
        state["open_cost_basis"] = sum((h["cost"] for acct in accounts.values() for h in acct["holdings"].values()), ZERO)
        folded = sum((acct["realized"] for acct in accounts.values()), ZERO)
        marked = sum((D(p.get("realized")) for p in marks_end.values()), ZERO)
        state["check"] = {"folded_realized": folded, "book_mark_realized": marked, "difference": folded - marked}
        del state["accounts"]

    sections = {}
    for section in ("real", "practice"):
        members = sorted((s for s in books.values() if s["section"] == section), key=lambda s: s["book"])
        total = _window_stats()
        for s in members:
            for k, v in s["window"].items():
                total[k] += v
        sections[section] = {
            "books": members,
            "total": total,
            "mark_to_market_change": sum((s["mark_to_market"]["change"] for s in members), ZERO),
            "staked_outstanding": sum((s["staked_outstanding"] for s in members), ZERO),
        }
    return sections


# ------------------------------------------------------------------ site account basis
def load_performance(ledger_path: str, config: str | None, start_equity: str | None, start_at: str | None) -> dict:
    if start_equity is not None:
        return {"start_equity": D(start_equity), "start_at": iso(start_at) if start_at else None, "source": "command line"}
    candidates = [config] if config else []
    here = globals().get("__file__")
    if here:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(here)), "..", "league", "config.json"))
    state_dir = os.path.dirname(os.path.abspath(ledger_path))
    candidates += [os.path.join(state_dir, "..", "current", "league", "config.json"),
                   os.path.join(os.getcwd(), "league", "config.json")]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as handle:
                performance = json.load(handle).get("performance") or {}
        except (OSError, ValueError):
            continue
        if performance.get("start_equity") is not None:
            return {"start_equity": D(performance["start_equity"]), "start_at": performance.get("start_at"),
                    "source": os.path.normpath(path)}
    return {"start_equity": None, "start_at": None, "source": None}


def site_basis(conn, performance: dict, real: dict, since: str | None, until: str | None) -> dict:
    """The public chart's real-money figure, from `floor.mark` rows, on the site's own definition."""
    last = before = first = None
    count = 0
    for _seq, _kind, _agent, at, p in rows(conn, "floor.mark", until=until):
        if "real_account_equity" not in p:
            continue  # publish.py: only league-basis marks are published
        count += 1
        if first is None:
            first = (at, p)
        last = (at, p)
        if since is not None and at < since:
            before = (at, p)
    start = performance.get("start_equity")
    out = {"definition_doc": DOC, "definition_code": DOC_CODE, "start_equity": start, "start_at": performance.get("start_at"),
           "start_source": performance.get("source"), "floor_marks": count, "net_flows_on_league_basis": ZERO,
           "recomputed_from_books": sum((s["mark_to_market"]["equity_less_staked_end"] for s in real["books"]), ZERO),
           "recomputed_change": real["mark_to_market_change"]}
    if last is None:
        out["missing"] = "no league-basis floor.mark rows in the window: the site's account figure cannot be read from the ledger"
        return out
    at, p = last
    out.update({"as_of": at, "account_equity": D(p.get("account_equity")), "real_account_equity": D(p.get("real_account_equity")),
                "account_cash": D(p.get("account_cash")),
                "venues": [{k: v for k, v in row.items() if k in ("venue", "equity", "cash", "as_of", "stale")} for row in p.get("venues") or []]})
    if start is None:
        out["missing"] = ("performance.start_equity (league/config.json) was not found: pass --start-equity or --config; "
                          "the site's tracked profit is account_equity - start_equity and is not computed without it")
        return out
    pnl = out["account_equity"] - start
    out["pnl_total"] = pnl
    out["since_inception_pct"] = (pnl / start * 100) if start else None
    if since is not None:
        base = (D(before[1].get("account_equity")) - start) if before else ZERO
        out["window_change"] = pnl - base
    out["raw_balance_change"] = out["real_account_equity"] - start
    out["raw_note"] = ("real_account_equity - start_equity is NOT a return: it moves with the owner's deposits and withdrawals "
                       "and the first run's leftover contracts. The net external flows the doc's raw definition subtracts are read "
                       "live from venue funding APIs (ltcm/performance.py) and are not recorded in the ledger.")
    return out


# ----------------------------------------------------------------------------- spend
def _sum_cost(items, field="cost_usd") -> Decimal:
    return sum((D(i.get(field)) for i in items), ZERO)


def spend(conn, since: str | None = None, until: str | None = None, semantic_db: str | None = None) -> dict:
    lines: list[dict] = []

    def line(provider: str, component: str, usd: Decimal, basis: str, count: int, *, in_total: bool = True, note: str = "") -> None:
        lines.append({"provider": provider, "component": component, "usd": usd, "basis": basis, "count": count,
                      "in_total": in_total, "note": note})

    # Session profiles, from summary rows (every session) and provider.request (Luna sessions).
    profile: dict[str, str | None] = {}
    luna_sessions: set[str] = set()
    for _s, _k, _a, _at, p in rows(conn, "agent.research", tools=("summary",)):
        if p.get("session"):
            profile[p["session"]] = p.get("profile")

    luna_ok, luna_unconfirmed = [], []
    for _s, _k, _a, at, p in rows(conn, "provider.request", until=until):
        if p.get("session_id"):
            luna_sessions.add(p["session_id"])
        if not inside(at, since, until):
            continue
        if p.get("cost_verified") is True and p.get("cost_usd") is not None:
            luna_ok.append(p)
        else:
            luna_unconfirmed.append(p)
    luna_models = sorted({str(p.get("model")) for p in luna_ok if p.get("model")})
    line("openai-luna", "research requests (" + (", ".join(luna_models) or "gpt-5.6-luna") + ")", _sum_cost(luna_ok),
         "gateway-verified", len(luna_ok))
    if luna_unconfirmed:
        line("openai-luna", "unconfirmed requests: held reservation (upper bound)", _sum_cost(luna_unconfirmed, "held_usd"),
             "reservation hold, bill unknown", len(luna_unconfirmed), in_total=False)

    # Credit charges, by reason; research tokens split by the session's provider.
    charges: dict[str, dict] = {}
    tokens = {"luna": ZERO, "sail": {}, "sail_count": {}, "luna_n": 0}
    for _s, _k, _a, at, p in rows(conn, "credit.charge", until=until):
        if not inside(at, since, until):
            continue
        what = str(p.get("what") or "")
        usd = D(p.get("usd"))
        entry = charges.setdefault(what, {"count": 0, "usd": ZERO})
        entry["count"] += 1
        entry["usd"] += usd
        if what == "research tokens":
            session = str((p.get("detail") or {}).get("session") or "")
            prof = profile.get(session)
            if prof == LUNA_PROFILE or (prof is None and session in luna_sessions):
                tokens["luna"] += usd
                tokens["luna_n"] += 1
            else:
                label = prof or "profile not recorded"
                tokens["sail"][label] = tokens["sail"].get(label, ZERO) + usd
                tokens["sail_count"][label] = tokens["sail_count"].get(label, 0) + 1

    # Astra (frontier) rows.
    merton: dict[str, list] = {}
    for _s, _k, _a, at, p in rows(conn, "merton.pass", until=until):
        if inside(at, since, until):
            merton.setdefault(str(p.get("role") or "unknown"), []).append(p)
    for role in sorted(merton):
        line("openai-astra", f"merton {role}", _sum_cost(merton[role]), "gateway-metered (cost header)", len(merton[role]))
    audits = [p for _s, _k, _a, at, p in rows(conn, "audit.verdict", until=until) if inside(at, since, until)]
    line("openai-astra", "frontier audits", _sum_cost(audits), "gateway-metered (cost header)", len(audits))
    grants, semantic_rubrics = [], []
    for _s, _k, _a, at, p in rows(conn, "agent.research", until=until, tools=("research_grant", "semantic_question_experiment")):
        if not inside(at, since, until):
            continue
        if p.get("tool") == "research_grant" and p.get("status") == "completed":
            grants.append(p)
        elif p.get("tool") == "semantic_question_experiment":
            semantic_rubrics.append(p)
    line("openai-astra", "research grants", _sum_cost(grants), "gateway-metered (cost header)", len(grants))
    probes = []
    sail_meter, campaign = [], None
    for _s, _k, _a, at, p in rows(conn, "ops.budget", until=until):
        if p.get("what") == "expedition" and isinstance(p.get("campaign"), dict):
            campaign = (at, p["campaign"])
        if not inside(at, since, until):
            continue
        if p.get("what") == "sail" and p.get("spent_usd") is not None:
            sail_meter.append(p)
        elif p.get("cost_usd") is not None and p.get("what") not in ("payout",):
            probes.append(p)
    if probes:
        line("openai-astra", "frontier probes (ops.budget)", _sum_cost(probes), "gateway-metered (cost header)", len(probes))

    # Semantic lab database (Jev tasks and Astra rubric proposals), read-only, when present.
    semantic = {"path": semantic_db, "read": False}
    if semantic_db and os.path.exists(semantic_db):
        try:
            sconn = connect_ro(semantic_db)
            lo = epoch(since) if since else float("-inf")
            hi = epoch(until) if until else float("inf")
            known, unknown, n = ZERO, 0, 0
            for status, cost, finished in sconn.execute("SELECT status, cost, finished FROM semantic_tasks"):
                if finished is None or not lo <= float(finished) < hi:
                    continue
                if cost is None:
                    unknown += int(status in ("unconfirmed", "calling"))
                else:
                    known += D(cost)
                    n += 1
            rubric_known, rubric_n = ZERO, 0
            for status, cost, created in sconn.execute("SELECT status, cost, created FROM semantic_rubrics"):
                if cost is not None and created is not None and lo <= float(created) < hi:
                    rubric_known += D(cost)
                    rubric_n += 1
            sconn.close()
            semantic.update(read=True, jev_known_usd=known, jev_tasks=n, jev_unconfirmed=unknown,
                            rubric_known_usd=rubric_known, rubric_rounds=rubric_n)
        except (sqlite3.Error, OSError, ValueError) as exc:
            semantic["error"] = f"{type(exc).__name__}: {exc}"
    if semantic.get("read"):
        line("openai-astra", "semantic lab rubric proposals", semantic["rubric_known_usd"], "semantic.sqlite known cost",
             semantic["rubric_rounds"], note="supersedes the ledger's semantic_question_experiment rows (completed only)")
    else:
        line("openai-astra", "semantic lab rubric proposals", _sum_cost(semantic_rubrics), "gateway-metered (cost header)",
             len(semantic_rubrics))

    # Sail.
    sail_attributed = sum(tokens["sail"].values(), ZERO) + charges.get("sandbox seconds", {}).get("usd", ZERO)
    metered = _sum_cost(sail_meter, "spent_usd")
    for label in sorted(tokens["sail"]):
        line("sail", f"research tokens ({label})", tokens["sail"][label], "credit charge at Sail prices (estimate)",
             tokens["sail_count"][label], in_total=not sail_meter)
    line("sail", "sandbox seconds", charges.get("sandbox seconds", {}).get("usd", ZERO), "credit charge (estimate)",
         charges.get("sandbox seconds", {}).get("count", 0), in_total=not sail_meter)
    if sail_meter:
        line("sail", "balance-debit meter (all Sail use: House box, agent boxes, inference)", metered,
             "Sail balance meter", len(sail_meter),
             note=f"attributed estimate ${sail_attributed:.4f}; unattributed Sail ${metered - sail_attributed:.4f}")

    # Jev.
    jev_charges = charges.get("jev classification", {"count": 0, "usd": ZERO})
    line("jev", "classify tool charges (jev-1.13.0)", jev_charges["usd"], "credit charge at gateway cost", jev_charges["count"])
    if semantic.get("read"):
        line("jev", "semantic lab tasks (jev-1.13.0)", semantic["jev_known_usd"], "semantic.sqlite known cost",
             semantic["jev_tasks"], note=f"{semantic['jev_unconfirmed']} unconfirmed task(s) with unknown cost excluded")
    else:
        line("jev", "semantic lab tasks", ZERO, "not in the ledger", 0, in_total=False,
             note="semantic.sqlite was not read: " + (semantic.get("error") or "not found beside the ledger"))

    web = charges.get("web search", {"count": 0, "usd": ZERO})
    line("web-search", "web search", web["usd"], "flat internal charge (estimate)", web["count"],
         note="the site counts this inside Sail spend; no paid search backend is recorded in the ledger")

    providers: dict[str, Decimal] = {}
    for item in lines:
        if item["in_total"]:
            providers[item["provider"]] = providers.get(item["provider"], ZERO) + item["usd"]
    total = sum(providers.values(), ZERO)
    verified = sum((i["usd"] for i in lines if i["in_total"] and not i["basis"].endswith("(estimate)")), ZERO)

    astra_consult = _sum_cost(merton.get("consultant", []))
    astra_grants = _sum_cost(grants)
    research_spend = {
        "luna_research": _sum_cost(luna_ok),
        "sail_research_tokens": sum(tokens["sail"].values(), ZERO),
        "astra_consults": astra_consult,
        "astra_research_grants": astra_grants,
        "jev_classify": jev_charges["usd"],
    }
    research_spend["total"] = sum(research_spend.values(), ZERO)
    return {
        "lines": lines,
        "providers": providers,
        "total": total,
        "total_verified_or_metered": verified,
        "total_estimated": total - verified,
        "charges": charges,
        "checks": {
            "luna_research_token_charges": tokens["luna"],
            "luna_provider_request_cost": _sum_cost(luna_ok),
            "merton_consult_charges": charges.get("merton's time", {}).get("usd", ZERO),
            "merton_consult_rows": astra_consult,
            "frontier_audit_charges": charges.get("frontier audit", {}).get("usd", ZERO),
            "frontier_audit_rows": _sum_cost(audits),
            "site_sail_model_spend": charges.get("research tokens", {}).get("usd", ZERO),
            "sail_metered": metered if sail_meter else None,
            "sail_attributed": sail_attributed,
        },
        "astra_house_roles": sum((_sum_cost(merton.get(r, [])) for r in MERTON_HOUSE_ROLES), ZERO),
        "campaign": ({"as_of": campaign[0], **{name: {k: acct.get(k) for k in ("cap_usd", "committed_usd", "remaining_usd")}
                                               for name, acct in (campaign[1].get("accounts") or {}).items()}}
                     if campaign else None),
        "semantic_db": semantic,
        "research_spend": research_spend,
    }


# ----------------------------------------------------------------------- useful work
def useful_work(conn, spent: dict, since: str | None = None, until: str | None = None) -> dict:
    passing, passing_rows, failing, candidate_rows, private_seen = set(), 0, 0, 0, False
    admitted = 0
    for _s, _k, agent, at, p in rows(conn, "agent.research", until=until, tools=("candidate", "candidate_admission")):
        if not inside(at, since, until):
            continue
        if p.get("tool") == "candidate_admission":
            admitted += int(p.get("status") == "admitted")
            continue
        candidate_rows += 1
        candidate = p.get("_candidate")
        if isinstance(candidate, dict):
            private_seen = True
        if p.get("status", "retained") != "retained" or not isinstance(candidate, dict):
            continue
        numbers = candidate.get("numbers") or {}
        if candidate.get("passed") is True:
            passing_rows += 1
            passing.add((agent, p.get("session"), numbers.get("code_sha256") or hash(str(candidate.get("code")))))
        else:
            failing += 1

    promote_adopt = newborn_passes = seat_adopt = 0
    for _s, _k, _a, at, p in rows(conn, "eval.verdict", until=until):
        if not inside(at, since, until):
            continue
        reason = str(p.get("reason") or "")
        if p.get("decision") == "promote" and reason == ADOPT_PROMOTE_REASON:
            promote_adopt += 1
        elif p.get("decision") == "promote" and reason == NEWBORN_PROMOTE_REASON:
            newborn_passes += 1
        elif p.get("decision") == "seat" and reason == ADOPT_SEAT_REASON:
            seat_adopt += 1
    rewrite_passed = rewrite_unpassed = 0
    for _s, _k, _a, at, p in rows(conn, "agent.strategy", until=until):
        if not inside(at, since, until):
            continue
        if p.get("passed_replay") is True:
            rewrite_passed += 1
        elif p.get("passed_replay") is False:
            rewrite_unpassed += 1

    verified: set = set()
    repair_cost = ZERO
    repair_rows = 0
    for _s, _k, agent, at, p in rows(conn, "repair.status", until=until):
        if not inside(at, since, until):
            continue
        repair_rows += 1
        repair_cost += D(p.get("cost_usd"))
        if str(p.get("state") or p.get("status") or "").lower() == "verified":
            verified.add(str(p.get("repair_id") or p.get("key") or p.get("id") or p.get("job") or f"{agent}:{at}"))

    adoptions = promote_adopt + rewrite_passed + seat_adopt
    research = spent["research_spend"]["total"]
    repair_denominator = repair_cost if repair_cost > 0 else spent["astra_house_roles"]

    def ratio(n: int, usd: Decimal):
        return (Decimal(n) / usd) if usd > 0 else None

    def per(n: int, usd: Decimal):
        return (usd / Decimal(n)) if n > 0 else None

    return {
        "candidate_rows": candidate_rows,
        "private_candidate_keys_present": private_seen,
        "replay_passing_candidates": len(passing),
        "replay_passing_rows": passing_rows,
        "replay_failing_candidates": failing,
        "adoptions": adoptions,
        "adoptions_detail": {"in_place_rung0_promote": promote_adopt, "in_place_rung1_rewrite": rewrite_passed,
                             "forked_child_seated": seat_adopt, "candidate_admission_admitted_rows": admitted,
                             "rewrites_without_replay_pass (not counted)": rewrite_unpassed,
                             "newborn_replay_passes (House, not research; not counted)": newborn_passes},
        "verified_repairs": len(verified),
        "repair_status_rows": repair_rows,
        "denominator_research_usd": research,
        "denominator_repairs_usd": repair_denominator,
        "denominator_repairs_basis": ("cost_usd on repair.status rows" if repair_cost > 0 else
                                      "Astra spend on Merton's House roles (" + ", ".join(MERTON_HOUSE_ROLES) + ")"),
        "candidates_per_usd": ratio(len(passing), research),
        "usd_per_candidate": per(len(passing), research),
        "adoptions_per_usd": ratio(adoptions, research),
        "usd_per_adoption": per(adoptions, research),
        "verified_repairs_per_usd": ratio(len(verified), repair_denominator) if verified else Decimal(0),
        "repairs_note": None if repair_rows else "none yet: no repair.status rows in the window",
    }


# -------------------------------------------------------------------------- warnings
def warnings(report: dict) -> list[str]:
    out = []
    window = report["window"]
    if window["hours"] is not None and window["hours"] < MIN_WINDOW_HOURS:
        out.append(f"window is {window['hours']:.1f} h (< {MIN_WINDOW_HOURS:g} h): a day's noise, not a trend")
    for section in ("real", "practice"):
        for book in report["trading"][section]["books"]:
            n = book["window"]["closed_trades"]
            if n < MIN_CLOSED_TRADES:
                out.append(f"{section} book {book['book']}: {n} closed trade(s) (< {MIN_CLOSED_TRADES}): no edge can be read from it")
            if not book["known"]:
                out.append(f"book {book['book']} is not one of the four known books; placed in {section} by its real_money flag")
            diff = book["check"]["difference"]
            if report["window"]["since"] is None and abs(diff) > Decimal("0.01"):
                out.append(f"book {book['book']}: folded realized differs from its latest book.mark rows by {diff:.4f} "
                           "(usually a fill booked after the last mark)")
        if section == "real":
            staked = report["trading"]["real"]["staked_outstanding"]
            for book in report["trading"]["real"]["books"]:
                if book["staked_outstanding"] < TINY_REAL_STAKE_USD:
                    out.append(f"real book {book['book']}: ${book['staked_outstanding']:.2f} staked over {book['funded_accounts']} "
                               f"account(s): tiny stakes, a few contracts decide the result")
            if staked == 0:
                out.append("no real-money stake is outstanding")
    work = report["useful_work"]
    if work["adoptions"] < MIN_ADOPTIONS:
        out.append(f"{work['adoptions']} adoption(s) (< {MIN_ADOPTIONS}): adoptions per dollar is not a rate yet")
    if work["replay_passing_candidates"] < MIN_CANDIDATES:
        out.append(f"{work['replay_passing_candidates']} replay-passing candidate(s) (< {MIN_CANDIDATES}): too few to price")
    if work["candidate_rows"] and not work["private_candidate_keys_present"]:
        out.append("candidate rows carry no _candidate payload (a public copy strips _ keys): replay passes cannot be counted")
    if work["verified_repairs"] == 0:
        out.append("verified repairs: none yet")
    site = report["site_account"]
    if site.get("missing"):
        out.append(site["missing"])
    elif site.get("pnl_total") is not None and abs(site["pnl_total"] - site["recomputed_from_books"]) > Decimal("0.05"):
        out.append(f"site-basis P&L ({site['pnl_total']:.4f}) and the book recomputation ({site['recomputed_from_books']:.4f}) "
                   "differ by more than 5 cents: marks are taken at different moments")
    for item in report["spend"]["lines"]:
        if "unconfirmed" in item["component"] and item["count"]:
            out.append(f"{item['count']} {item['provider']} request(s) have unknown bills (held ${item['usd']:.4f})")
    out.append("never sum practice and real money; never compare books, desks or providers with unequal stakes, "
               "and never rank samples this small")
    return out


# ---------------------------------------------------------------------------- report
def build(ledger: str, since: str | None = None, until: str | None = None, *, semantic_db: str | None = "auto",
          config: str | None = None, start_equity: str | None = None, start_at: str | None = None) -> dict:
    since, until = iso(since), iso(until)
    conn = connect_ro(ledger)
    try:
        first, last, count = ledger_span(conn)
        lo = max(filter(None, [since, first])) if (since or first) else None
        hi = min(filter(None, [until, last])) if (until or last) else None
        hours = (epoch(hi) - epoch(lo)) / 3600 if lo and hi else None
        if semantic_db == "auto":
            semantic_db = os.path.join(os.path.dirname(os.path.abspath(ledger)), "semantic.sqlite")
        performance = load_performance(ledger, config, start_equity, start_at)
        trade = trading(conn, since, until)
        spent = spend(conn, since, until, semantic_db)
        work = useful_work(conn, spent, since, until)
        site = site_basis(conn, performance, trade["real"], since, until)
    finally:
        conn.close()
    report = {
        "ledger": {"path": os.path.abspath(ledger), "rows": count, "first_at": first, "last_at": last, "mode": "read-only"},
        "window": {"since": since, "until": until, "effective_from": lo, "effective_to": hi, "hours": hours},
        "trading": trade,
        "site_account": site,
        "spend": spent,
        "useful_work": work,
    }
    pnl = site.get("window_change", site.get("pnl_total"))
    if pnl is not None:
        sail = spent["checks"]["sail_metered"] if spent["checks"]["sail_metered"] is not None else spent["checks"]["sail_attributed"]
        report["site_account"]["pnl_less_all_spend"] = pnl - spent["total"]
        report["site_account"]["pnl_per_sail_dollar"] = (pnl / sail) if sail else None
    report["warnings"] = warnings(report)
    return report


def to_json(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(k): to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json(v) for v in value]
    return value


def m(value, places: int = 2, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    q = Decimal(1).scaleb(-places)
    v = Decimal(value).quantize(q)
    return (f"{v:+,.{places}f}" if signed else f"{v:,.{places}f}")


def render(report: dict) -> str:
    out: list[str] = []
    add = out.append
    led, win = report["ledger"], report["window"]
    add("LTCM LEAGUE ECONOMICS (read-only)")
    add(f"ledger {led['path']} ({led['rows']} rows, {led['first_at']} .. {led['last_at']}), opened mode=ro")
    add(f"window {win['since'] or 'start'} .. {win['until'] or 'end'} -> effective {win['effective_from']} .. {win['effective_to']}"
        + (f" ({win['hours']:.1f} h)" if win["hours"] is not None else ""))
    add("")
    add("1. TRADING P&L AFTER EXECUTION COSTS (real and practice are never summed)")
    add("   gross = realized before fees; fees = fees inside the closed trades; net = the book's realized (league/book.py);")
    add("   House = venue fee activities, dust and cross balancing; MTM = change in sum(equity - staked) from book.mark + House row")
    for section, title in (("real", "REAL MONEY"), ("practice", "PRACTICE MONEY (paper / shadow)")):
        sec = report["trading"][section]
        add(f"   {title}")
        add(f"   {'book':<14}{'venue':<8}{'closed':>7}{'W/L':>9}{'gross':>12}{'fees':>10}{'net':>12}{'House':>10}{'net+House':>12}"
            f"{'fees paid':>11}{'MTM chg':>12}{'staked':>11}")
        for b in sec["books"] + [{"book": "total", "venue": "", "window": sec["total"],
                                   "mark_to_market": {"change": sec["mark_to_market_change"]},
                                   "staked_outstanding": sec["staked_outstanding"]}]:
            w = b["window"]
            add(f"   {b['book']:<14}{b['venue']:<8}{w['closed_trades']:>7}{str(w['wins']) + '/' + str(w['losses']):>9}"
                f"{m(w['realized_gross'], 2, True):>12}{m(w['fees_on_closed']):>10}{m(w['realized_net'], 2, True):>12}"
                f"{m(w['house_row'], 4, True):>10}{m(w['net_after_costs'], 2, True):>12}{m(w['fees_paid']):>11}"
                f"{m(b['mark_to_market']['change'], 2, True):>12}{m(b['staked_outstanding']):>11}")
        for b in sec["books"]:
            w = b["window"]
            extra = []
            if w["in_kind_fee_estimate"]:
                extra.append(f"in-kind crypto fees ~${m(w['in_kind_fee_estimate'], 4)} (valued at fill price, inside gross)")
            if w["corrections"]:
                extra.append(f"{w['corrections']} receipt correction(s)")
            if b["open_lots"]:
                extra.append(f"{b['open_lots']} open lot(s), cost ${m(b['open_cost_basis'])}")
            if b["baseline_rows"] > 1:
                extra.append(f"{b['baseline_rows']} baseline rows (venue differences outside agent P&L)")
            extra.append(f"lent ${m(w['stakes_lent'])} / returned ${m(w['stakes_returned'])} in window")
            add(f"     {b['book']}: " + "; ".join(extra))
    site = report["site_account"]
    add("   REAL ACCOUNT RETURN, the public site's definition")
    add(f"     definition: {site['definition_doc']} as superseded by {site['definition_code']}:")
    add("     account_equity = start_equity + league real P&L (each real account's equity less what it was lent, House row")
    add("     included); net flows are 0 on this basis; tracked profit = account_equity - start_equity - net_flows")
    add(f"     start_equity {m(site.get('start_equity'), 4)} at {site.get('start_at')} (from {site.get('start_source')}); "
        f"{site['floor_marks']} league-basis floor.mark row(s)")
    if site.get("account_equity") is not None:
        add(f"     latest floor.mark {site['as_of']}: account_equity {m(site['account_equity'], 4)}, "
            f"raw real_account_equity {m(site['real_account_equity'], 4)}, cash {m(site['account_cash'], 4)}")
        for v in site.get("venues") or []:
            add(f"       {v.get('venue')}: equity {v.get('equity')} cash {v.get('cash')} as of {v.get('as_of')}"
                + (" STALE" if v.get("stale") else ""))
    if site.get("pnl_total") is not None:
        add(f"     tracked profit (site pnl_total) {m(site['pnl_total'], 4, True)} = {m(site['since_inception_pct'], 4, True)}% of start")
        if site.get("window_change") is not None:
            add(f"     change inside the window {m(site['window_change'], 4, True)}")
        add(f"     recomputed from book rows: {m(site['recomputed_from_books'], 4, True)} (window MTM change {m(site['recomputed_change'], 4, True)})")
        add(f"     raw balance change {m(site['raw_balance_change'], 4, True)}: {site['raw_note']}")
        add(f"     tracked profit less ALL recorded model/infra spend in the window: {m(site.get('pnl_less_all_spend'), 2, True)}; "
            f"per Sail dollar (site's run.pnl_per_sail_dollar): {m(site.get('pnl_per_sail_dollar'), 4, True)}")
    if site.get("missing"):
        add(f"     NOT COMPUTED: {site['missing']}")
    add("")
    sp = report["spend"]
    add("2. MODEL AND INFRASTRUCTURE SPEND BY PROVIDER")
    add(f"   {'provider':<13}{'component':<58}{'n':>7}{'usd':>11}  basis")
    for item in sp["lines"]:
        flag = "" if item["in_total"] else "  [not in total]"
        add(f"   {item['provider']:<13}{item['component'][:57]:<58}{item['count']:>7}{m(item['usd'], 4):>11}  {item['basis']}{flag}")
        if item["note"]:
            add(f"   {'':<13}  note: {item['note']}")
    add("   per provider: " + ", ".join(f"{k} ${m(v, 4)}" for k, v in sp["providers"].items()))
    add(f"   TOTAL ${m(sp['total'], 4)} (verified or metered ${m(sp['total_verified_or_metered'], 4)}, estimates ${m(sp['total_estimated'], 4)})")
    c = sp["checks"]
    add("   checks: Luna research-token charges ${} vs provider.request ${}; Merton consult charges ${} vs merton.pass ${}; "
        "audit charges ${} vs audit.verdict ${}".format(m(c["luna_research_token_charges"], 4), m(c["luna_provider_request_cost"], 4),
                                                         m(c["merton_consult_charges"], 4), m(c["merton_consult_rows"], 4),
                                                         m(c["frontier_audit_charges"], 4), m(c["frontier_audit_rows"], 4)))
    add(f"   site caveat: the site's sail_model_spend_total_usd sums every 'research tokens' charge (${m(c['site_sail_model_spend'], 4)}), "
        f"including ${m(c['luna_research_token_charges'], 4)} served by OpenAI Luna")
    if sp.get("campaign"):
        camp = sp["campaign"]
        add(f"   campaign commitments (cumulative, conservative holds) as of {camp['as_of']}: "
            + ", ".join(f"{k} {v.get('committed_usd')} of {v.get('cap_usd')}" for k, v in camp.items() if isinstance(v, dict)))
    add("   credit charges by reason: " + ", ".join(f"{k} {v['count']} ${m(v['usd'], 4)}" for k, v in sorted(sp["charges"].items())))
    add("")
    w = report["useful_work"]
    add("3. USEFUL WORK PER DOLLAR")
    rs = sp["research_spend"]
    add(f"   denominator: research model spend ${m(rs['total'], 4)} = Luna ${m(rs['luna_research'], 4)} + Sail research tokens "
        f"${m(rs['sail_research_tokens'], 4)} + Astra consults ${m(rs['astra_consults'], 4)} + Astra grants "
        f"${m(rs['astra_research_grants'], 4)} + Jev classify ${m(rs['jev_classify'], 4)} (sandbox seconds excluded)")
    add(f"   replay-passing candidates: {w['replay_passing_candidates']} unique ({w['replay_passing_rows']} rows; "
        f"{w['replay_failing_candidates']} failing retained) -> {m(w['candidates_per_usd'], 4)} per $, ${m(w['usd_per_candidate'], 2)} each")
    d = w["adoptions_detail"]
    add(f"   adoptions of replay-passing code: {w['adoptions']} (rung-0 in place {d['in_place_rung0_promote']}, rung-1 rewrite "
        f"{d['in_place_rung1_rewrite']}, forked child seated {d['forked_child_seated']}) -> {m(w['adoptions_per_usd'], 4)} per $, "
        f"${m(w['usd_per_adoption'], 2)} each")
    add(f"     not counted: {d['rewrites_without_replay_pass (not counted)']} rewrite(s) to a file that did not pass replay; "
        f"{d['newborn_replay_passes (House, not research; not counted)']} House replay pass(es) of newborns; "
        f"candidate_admission admitted rows {d['candidate_admission_admitted_rows']}")
    add(f"   verified repairs: {w['verified_repairs']} ({w['repair_status_rows']} repair.status rows) -> "
        f"{m(w['verified_repairs_per_usd'], 4)} per $ of {w['denominator_repairs_basis']} (${m(w['denominator_repairs_usd'], 4)})"
        + (f"; {w['repairs_note']}" if w["repairs_note"] else ""))
    add("")
    add("4. SAMPLE-SIZE WARNINGS")
    for item in report["warnings"]:
        add(f"   - {item}")
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only league economics report.")
    parser.add_argument("--ledger", default="/workspace/state/ledger.sqlite")
    parser.add_argument("--since", help="ISO date or time (UTC if no zone), inclusive")
    parser.add_argument("--until", help="ISO date or time (UTC if no zone), exclusive")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--semantic-db", default="auto", help="semantic lab DB (default: semantic.sqlite beside the ledger)")
    parser.add_argument("--no-semantic", action="store_true", help="do not read the semantic lab DB")
    parser.add_argument("--config", help="league/config.json for performance.start_equity")
    parser.add_argument("--start-equity", help="override performance.start_equity")
    parser.add_argument("--start-at", help="override performance.start_at")
    args = parser.parse_args(argv)
    report = build(args.ledger, args.since, args.until, semantic_db=None if args.no_semantic else args.semantic_db,
                   config=args.config, start_equity=args.start_equity, start_at=args.start_at)
    if args.json:
        print(json.dumps(to_json(report), indent=2, sort_keys=True))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
