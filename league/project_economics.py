"""Private project economics: receipt-backed inputs and realized options cash, never account-balance movement.

The booked Gym estimate and provider box bill are alternatives. Reservations are not invoices. Position cash already
contains fees. Missing categories, unresolved bills and asynchronously dated sources prevent a complete project Net.
Readers below use existing state read-only; only persist() writes, to a separate private report directory.
"""
from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from typing import Any, Mapping

from .publish import MONTH_SECONDS, SUBSCRIPTIONS_MONTHLY_USD
from .trading_profit import cents, complete as complete_trading, row_value

T0 = "2026-09-26T06:23:14Z"
FINANCIAL_START = "2026-09-26T06:25:30Z"
SCHEMA = "project-economics-2"
MODEL_SETTLEMENT_BASIS = "admissions-and-verified-settlements-2"
MODEL_KINDS = ("sail_model", "openai", "claude")
ZERO = Decimal(0)


def decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = Decimal(str(value))
        return out if out.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def money(value: Any) -> str | None:
    value = decimal(value)
    return None if value is None else format(value.quantize(Decimal("0.000001")), "f")


def is_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def position_money_map(value: Any) -> bool:
    """An explicit map, including an explicitly empty one; no missing map or ambiguous position ids."""
    return isinstance(value, dict) and all(
        isinstance(pid, str) and pid.isdecimal() and str(int(pid)) == pid and int(pid) > 0 and decimal(amount) is not None
        for pid, amount in value.items())


def epoch(value: Any) -> float | None:
    try:
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            return dt.datetime.fromtimestamp(value, dt.timezone.utc).timestamp()
        stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.timestamp() if stamp.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def iso(value: float) -> str:
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


@contextmanager
def readonly(path: Path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        yield db
    finally:
        db.close()


def collect(root: Path, *, clock=time.time) -> dict:
    """A redacted receipt of local accounting state. No broker/network calls, secrets, quotes or strategy code."""
    root = Path(root)
    result = {"schema": SCHEMA, "cost_start": T0, "financial_start": FINANCIAL_START, "sources": {}, "errors": []}
    sources, errors = result["sources"], result["errors"]
    try:
        with readonly(root / "swarm.sqlite") as db:
            rows = list(db.execute("SELECT seq,epoch,kind,usd,detail FROM spend WHERE epoch>=? ORDER BY seq", (epoch(T0),)))
            states = {r["key"]: json.loads(r["value"]) for r in db.execute(
                "SELECT key,value FROM kv WHERE key IN ('unsettled','claude_unsettled')")}
            booked, count = {}, {}
            # A settlement belongs to its request's original admission, not the later refund/billing timestamp.
            # Read only prior admission metadata to distinguish an earlier call from a genuinely missing receipt.
            origins = {}
            for row in db.execute("SELECT epoch,kind,detail FROM spend WHERE kind IN ('claude','openai') ORDER BY seq"):
                detail = json.loads(row["detail"] or "{}")
                if detail.get("hold"):
                    key = detail.get("request") or detail["hold"]
                    origins.setdefault((row["kind"], str(key)), []).append(row["epoch"])
            invalid_kinds, excluded_settlements = set(), {}
            openai_holds = {}
            claude_calls = {}
            ambiguous_refunds = 0
            for row in rows:
                amount = decimal(row["usd"])
                if amount is None:
                    raise ValueError("non-finite spend")
                kind = row["kind"]
                detail = json.loads(row["detail"] or "{}")
                if kind in ("claude", "openai") and (detail.get("settles") or detail.get("settles_hold")):
                    key = detail.get("settles_hold") or detail.get("request") or detail.get("settles")
                    admitted = origins.get((kind, str(key))) or []
                    if len(admitted) != 1:
                        invalid_kinds.add(kind)
                        errors.append(f"{kind} settlement has no unique admission receipt")
                    elif admitted[0] < epoch(T0):
                        excluded_settlements[kind] = excluded_settlements.get(kind, 0) + 1
                        continue
                booked[kind] = booked.get(kind, ZERO) + amount
                count[kind] = count.get(kind, 0) + 1
                if kind == "claude":
                    key = detail.get("request") or detail.get("settles_hold") or detail.get("hold") or detail.get("settles")
                    if not key:
                        invalid_kinds.add(kind)
                        errors.append("Claude booking has no identifiable request receipt")
                    else:
                        call = claude_calls.setdefault(str(key), {"usd": ZERO, "state": "unmatched_admission"})
                        call["usd"] += amount
                        if detail.get("hold"):
                            call["state"] = "unmatched_admission"
                        elif detail.get("settles_hold"):
                            gateway = detail.get("gateway_state")
                            call["state"] = ("verified" if gateway in ("settled", "released", "absent")
                                             else "gateway_unknown" if gateway == "unknown" else "missing_gateway_state")
                        elif detail.get("settles"):
                            # _ClaudeHold.resolve only records a priced response or a verified refusal here.
                            call["state"] = "gateway_unknown" if detail.get("gateway_state") == "unknown" else "verified"
                if kind == "openai":
                    if detail.get("hold"):
                        key = str(detail["hold"])
                        if key in openai_holds:
                            ambiguous_refunds += 1
                        openai_holds[key] = amount
                    if detail.get("settles"):
                        openai_holds.pop(str(detail["settles"]), None)
                    if detail.get("refused"):
                        # Historical 4xx refund rows did not name their hold. Never guess which parallel call it was.
                        ambiguous_refunds += 1
            holds = {kind: {"count": 0, "usd": ZERO} for kind in MODEL_KINDS}
            held_keys = set()
            for field, default_kind in (("unsettled", "sail_model"), ("claude_unsettled", "claude")):
                if field not in states or not isinstance(states[field], dict):
                    errors.append(f"{field} state unavailable; model settlement coverage is incomplete")
                    invalid_kinds.add(default_kind)
                    continue
                for key, item in states[field].items():
                    kind = item.get("kind", default_kind)
                    amount = decimal(item.get("usd"))
                    if kind not in holds or amount is None or amount < 0:
                        raise ValueError("unreadable model hold")
                    held_at = epoch(item.get("at"))
                    if held_at is None:
                        invalid_kinds.add(kind)
                        errors.append(f"{kind} booked reservation has no admission timestamp")
                    elif held_at < epoch(T0):
                        continue
                    holds[kind]["count"] += 1
                    holds[kind]["usd"] += amount
                    held_keys.add((kind, str(key)))
            holds["openai"] = {"count": len(openai_holds), "usd": sum(openai_holds.values(), ZERO)}
            unverified = {"count": 0, "usd": ZERO, "reasons": {}}
            for key, call in claude_calls.items():
                if call["state"] == "verified":
                    continue
                if ("claude", key) in held_keys:
                    if call["state"] != "unmatched_admission":
                        invalid_kinds.add("claude")
                        errors.append("Claude request is both an active hold and an unverified gateway booking")
                    continue  # a still-filed reservation is already excluded by holds; never subtract it twice
                if call["usd"] < 0:
                    invalid_kinds.add("claude")
                    errors.append("Claude unverified booking has a negative balance")
                    continue
                unverified["count"] += 1
                unverified["usd"] += call["usd"]
                unverified["reasons"][call["state"]] = unverified["reasons"].get(call["state"], 0) + 1
            sources["models"] = {"as_of": iso(clock()), "booked_usd": {k: money(v) if k not in invalid_kinds else None for k, v in booked.items()},
                                 "rows": count, "through_seq": rows[-1]["seq"] if rows else 0,
                                 "prior_period_settlements_excluded": excluded_settlements,
                                 "holds": {k: {**v, "usd": money(v["usd"])} for k, v in holds.items()},
                                 "settlement_basis": MODEL_SETTLEMENT_BASIS,
                                 "claude_unverified_bookings": {**unverified, "usd": money(unverified["usd"])},
                                 "openai_hold_attribution_uncertain": bool(ambiguous_refunds),
                                 "basis": "swarm spend, including negative settlements; open holds listed separately"}
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append(f"swarm accounting unavailable: {type(exc).__name__}")
    try:
        with readonly(root / "swarm-provider.sqlite") as db:
            grouped = {}
            for row in db.execute("SELECT status,cost_usd,reserved_usd,error FROM requests WHERE julianday(created_at)>=julianday(?)", (T0,)):
                group = grouped.setdefault(row["status"], {"count": 0, "settled_usd": ZERO, "unpriced": 0, "reserved_usd": ZERO,
                                                          "unverified": 0, "unverified_booked_usd": ZERO})
                group["count"] += 1
                cost, reserved = decimal(row["cost_usd"]), decimal(row["reserved_usd"])
                unverified = cost is not None and row["error"] == "usage_unsettled"
                # The Provider deliberately books its full reservation when usage is missing. It is a conservative
                # budget charge awaiting invoice reconciliation, not measured model cost. Abandoned holds release.
                group["settled_usd"] += cost if cost is not None and not unverified else ZERO
                group["unpriced"] += unverified or (cost is None and row["status"] != "abandoned")
                group["unverified"] += unverified
                group["unverified_booked_usd"] += cost if unverified else ZERO
                group["reserved_usd"] += reserved or ZERO
            sources["provider_requests"] = {"as_of": iso(clock()), "cost_basis": "verified_usage_only", "groups": {
                k: {**v, **{field: money(v[field]) for field in ("settled_usd", "reserved_usd", "unverified_booked_usd")}}
                for k, v in grouped.items()}}
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        errors.append(f"provider request reconciliation unavailable: {type(exc).__name__}")
    try:
        with readonly(root / "ledger.sqlite") as db:
            # Existing House accounting kinds are outside the swarm meter. Their attribution cannot silently vanish
            # or be added to swarm/provider totals without checking overlap. The options run normally has no such rows.
            rows = list(db.execute("""SELECT kind,COUNT(*) AS n FROM ledger WHERE julianday(at)>=julianday(?) AND kind IN
                ('provider.request','merton.pass','audit.verdict','credit.charge') GROUP BY kind""", (T0,)))
            sources["house_accounting"] = {"as_of": iso(clock()), "rows_by_kind": {r["kind"]: r["n"] for r in rows}}
    except (OSError, sqlite3.Error) as exc:
        errors.append(f"House accounting coverage unavailable: {type(exc).__name__}")
    try:
        with readonly(root / "live.sqlite") as db:
            positions = [dict(r) for r in db.execute("SELECT pid,qty,cash,fees,status,opened_at,closed_at FROM positions WHERE opened_at>=?", (epoch(FINANCIAL_START),))]
            orders = list(db.execute("SELECT status,updated_at FROM orders"))
            recon = db.execute("SELECT value FROM kv WHERE key='recon'").fetchone()
            recon = json.loads(recon[0]) if recon else {}
            last_fill = db.execute("SELECT MAX(at) FROM fills").fetchone()[0]
            last_change = max([epoch(FINANCIAL_START), float(last_fill or 0), *[float(r["updated_at"]) for r in orders],
                               *[float(p.get("closed_at") or p["opened_at"]) for p in positions]])
            closed = [p for p in positions if p["status"] == "closed"]
            values = {str(p["pid"]): row_value(p, {}) for p in closed}
            sources["options"] = {"as_of": iso(clock()), "closed_cash_by_pid": {k: money(cents(v)) if v is not None else None for k, v in values.items()},
                                  "closed": len(closed), "open_or_unresolved": len(positions) - len(closed),
                                  "fees_already_in_cash_usd": money(sum((decimal(p["fees"]) or ZERO for p in closed), ZERO)),
                                  "pending_orders": sum(r["status"] in ("pending", "unknown") for r in orders),
                                  "last_book_change_at": iso(last_change),
                                  "recon": {"as_of": iso(recon["at"]) if epoch(recon.get("at")) is not None else None,
                                            # RealBook persists its reason string ("" means clear); missing is distinct.
                                            "frozen": bool(recon["frozen"]) if isinstance(recon.get("frozen"), (str, bool)) else None,
                                            "problems": len(recon["problems"]) if isinstance(recon.get("problems"), list) else None,
                                            "good": recon.get("good")},
                                  "basis": "all closed real positions opened since the financial basis; cash already net of execution fees"}
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append(f"real options book unavailable: {type(exc).__name__}")
    try:
        saved = json.loads((root / "publish.json").read_text()).get("activity")
        reading = saved["reading"]
        sources["broker_activity"] = {"as_of": reading["as_of"], "read_at": saved["read_at"], "start_at": saved["start_at"],
                                      "fees_by_pid": reading.get("fees_by_pid"), "blocking": reading.get("blocking"),
                                      "problems": reading.get("problems"), **{
                                          k: reading.get(k) for k in ("fees_usd", "crypto_usd", "interest_usd", "misc_usd", "unreconciled_usd")}}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"broker activity receipt unavailable: {type(exc).__name__}")
    result["as_of"] = iso(clock())
    return result


def box_cost(receipt: Mapping[str, Any] | None, app_id: str) -> dict:
    """Provider billing for exactly one project app. Global totals and the Gym meter are never added to it."""
    out = {"usd": None, "estimated_active_usd": None, "as_of": None, "basis": "provider app-scoped box billing", "problems": []}
    try:
        if not receipt or receipt.get("pricing_configured") is not True or epoch(receipt.get("start_at")) != epoch(T0):
            raise ValueError("missing pricing or mismatched cost start")
        rows = [r for r in receipt["sailboxes"] if r.get("app_id") == app_id]
        if not rows or len({r["sailbox_id"] for r in rows}) != len(rows):
            raise ValueError("missing project scope or duplicate box ids")
        finalized = active = ZERO
        for row in rows:
            f, a, total = [decimal(row.get(key)) for key in (
                "finalized_cost_usd_nanos", "estimated_active_cost_usd_nanos", "estimated_total_cost_usd_nanos")]
            if any(v is None or v < 0 for v in (f, a, total)) or f + a != total:
                raise ValueError("incomplete or inconsistent box costs")
            finalized += f
            active += a
        out.update(usd=money(finalized / Decimal(10 ** 9)), estimated_active_usd=money(active / Decimal(10 ** 9)),
                   as_of=receipt["end_at"], boxes=len(rows), app_id=app_id)
    except (ValueError, KeyError, TypeError) as exc:
        out["problems"].append(str(exc))
    return out


def report(evidence: Mapping[str, Any], boxes: Mapping[str, Any] | None, *, app_id: str,
           external: Mapping[str, Any] | None = None, subscription_rates: Mapping[str, Any] | None = None) -> dict:
    """A deterministic snapshot. Missing evidence stays null; a known subtotal is never labelled complete Net."""
    as_of = evidence.get("as_of")
    at = epoch(as_of)
    if at is None or at < epoch(FINANCIAL_START):
        raise ValueError("a valid reporting time after the preserved basis is required")
    unresolved = list(evidence.get("errors") or [])
    if evidence.get("cost_start") != T0 or evidence.get("financial_start") != FINANCIAL_START:
        unresolved.append("accounting basis mismatch; no automatic reset is permitted")
    sources = evidence.get("sources") or {}
    if evidence.get("schema") != SCHEMA:
        unresolved.append("unknown state-receipt schema")
    models = sources.get("models") or {}
    inputs = {}
    for kind in MODEL_KINDS:
        booked = decimal((models.get("booked_usd") or {}).get(kind))
        held = (models.get("holds") or {}).get(kind) or {}
        amount = decimal(held.get("usd"))
        settled = (booked - amount if booked is not None and amount is not None and booked >= amount >= 0
                   and is_count(held.get("count")) and (held["count"] > 0 or amount == ZERO) else None)
        inputs[kind] = {"usd": money(settled), "booked_usd": money(booked), "included_hold_usd": money(amount),
                        "as_of": models.get("as_of"), "basis": "recorded model spend less outstanding booked reservations"}
        if held.get("count"):
            unresolved.append(f"{kind}: {held['count']} unresolved booked reservation(s), not an extra charge")
    unverified = models.get("claude_unverified_bookings")
    unverified = unverified if isinstance(unverified, dict) else {}
    unverified_usd = decimal(unverified.get("usd"))
    claude_settled = decimal(inputs["claude"]["usd"])
    if (models.get("settlement_basis") != MODEL_SETTLEMENT_BASIS or not is_count(unverified.get("count"))
            or unverified_usd is None or unverified_usd < 0 or (unverified["count"] == 0 and unverified_usd != ZERO)
            or claude_settled is None or claude_settled < unverified_usd):
        inputs["claude"]["usd"] = None
        unresolved.append("Claude admission/gateway settlement verification is missing or inconsistent")
    else:
        inputs["claude"]["usd"] = money(claude_settled - unverified_usd)
        if unverified["count"]:
            unresolved.append(f"claude: {unverified['count']} unverified booking(s) require a priced gateway receipt or invoice")
    inputs["claude"]["included_unverified_booking_usd"] = money(unverified_usd)
    inputs["claude"]["basis"] = "recorded model spend less outstanding reservations and unverified gateway bookings"
    if models.get("openai_hold_attribution_uncertain"):
        inputs["openai"]["usd"] = None
        unresolved.append("historical OpenAI hold/refund attribution is ambiguous")
    unexpected = set(models.get("booked_usd") or {}) - set(MODEL_KINDS) - {"gym_box"}
    if unexpected:
        unresolved.append("unclassified swarm spend categories: " + ", ".join(sorted(unexpected)))
    provider = sources.get("provider_requests")
    if provider is None:
        unresolved.append("provider settlement reconciliation unavailable")
        inputs["sail_model"]["usd"] = None
    else:
        groups = provider.get("groups") if isinstance(provider.get("groups"), dict) else {}
        valid_groups = provider.get("cost_basis") == "verified_usage_only" and isinstance(provider.get("groups"), dict) and all(
            isinstance(v, dict) and all(type(v.get(field)) is int for field in ("count", "unpriced", "unverified"))
            and v["count"] >= v["unpriced"] >= v["unverified"] >= 0
            and all(decimal(v.get(field)) is not None and decimal(v[field]) >= 0 for field in ("settled_usd", "unverified_booked_usd"))
            for v in groups.values())
        unpriced = sum(v["unpriced"] for v in groups.values()) if valid_groups else None
        if unpriced:
            unresolved.append(f"provider has {unpriced} unpriced request(s); reservations are not added as invoices")
        paid = sum((decimal(v["settled_usd"]) for v in groups.values()), ZERO) if valid_groups else None
        own = decimal(inputs["sail_model"]["usd"])
        if paid is None or own is None or abs(paid - own) > Decimal("0.01"):
            unresolved.append("Sail provider settlement and swarm model spend have not reconciled to the cent")
        if not valid_groups:
            unresolved.append("provider settlement amounts or coverage counts are missing")
        inputs["sail_model"].update(usd=money(paid) if valid_groups else None, as_of=provider.get("as_of"),
                                    basis="settled provider request costs; swarm bookings and reservations are comparison only")
    house_rows = (sources.get("house_accounting") or {}).get("rows_by_kind")
    if not isinstance(house_rows, dict) or house_rows:
        unresolved.append("House model/accounting rows require attribution outside the swarm meter")
    if epoch((sources.get("house_accounting") or {}).get("as_of")) != at:
        unresolved.append("House accounting coverage does not share the reporting cutoff")
    inputs["sail_boxes"] = box_cost(boxes, app_id)
    unresolved.extend(inputs["sail_boxes"]["problems"])
    estimate = decimal(inputs["sail_boxes"]["estimated_active_usd"])
    if estimate:
        unresolved.append("active box usage is estimated, not finalized provider billing")
    rates = {**SUBSCRIPTIONS_MONTHLY_USD, **dict(subscription_rates or {})}
    months = Decimal(str(at - epoch(FINANCIAL_START))) / MONTH_SECONDS
    for key in SUBSCRIPTIONS_MONTHLY_USD:
        rate = decimal(rates.get(key))
        inputs[key] = {"usd": money(rate * months) if rate is not None and rate >= 0 else None, "monthly_usd": money(rate),
                       "as_of": as_of, "basis": "existing 365.25-day-year proration from financial/subscription start"}
    valid_external = bool(external and external.get("complete") is True and external.get("incremental_only") is True
                          and epoch(external.get("start_at")) == epoch(T0) and epoch(external.get("end_at")) == at
                          and external.get("source") and decimal(external.get("usd")) is not None and decimal(external["usd"]) >= 0)
    inputs["external_engineering_and_other"] = {"usd": money(external["usd"]) if valid_external else None,
                                               "as_of": external.get("end_at") if external else None,
                                               "source": external.get("source") if external else None,
                                               "basis": "external engineering, standalone inference and every other incremental project input"}
    if not valid_external:
        unresolved.append("external engineering/inference and other inputs remain unresolved pending attributed receipts or explicit owner coverage")
    for name, component in inputs.items():
        if component["usd"] is None:
            unresolved.append(f"missing cost category: {name}")
        if epoch(component.get("as_of")) is None:
            unresolved.append(f"missing cost as-of: {name}")
        elif epoch(component["as_of"]) != at:
            unresolved.append(f"asynchronous cost source: {name} ends at {component['as_of']}, not the reporting cutoff")
    options, broker = sources.get("options") or {}, sources.get("broker_activity") or {}
    cash_rows = options.get("closed_cash_by_pid")
    closed_coverage = position_money_map(cash_rows) and is_count(options.get("closed")) and options["closed"] == len(cash_rows)
    raw_cash = sum((decimal(v) for v in cash_rows.values()), ZERO) if closed_coverage else None
    if not closed_coverage:
        unresolved.append("closed position count and cash receipts are missing or inconsistent")
    broker_fields = (position_money_map(broker.get("fees_by_pid")) and isinstance(broker.get("blocking"), list)
                     and all(isinstance(reason, str) for reason in broker["blocking"]))
    if not broker_fields:
        unresolved.append("broker fee corrections or blocking-liability coverage is missing or invalid")
    brokerage_ok = bool(broker and options and closed_coverage and broker_fields
                        and epoch(broker.get("start_at")) == epoch(FINANCIAL_START)
                        and epoch(broker.get("as_of")) is not None and 0 <= at - epoch(broker["as_of"]) <= 600
                        and epoch(broker.get("read_at")) is not None and 0 <= at - epoch(broker["read_at"]) <= 600
                        and epoch(options.get("last_book_change_at")) is not None
                        and epoch(options["last_book_change_at"]) <= epoch(broker["as_of"])
                        and not broker.get("blocking") and decimal(broker.get("unreconciled_usd")) is not None
                        and is_count(options.get("pending_orders")) and options["pending_orders"] == 0
                        and (options.get("recon") or {}).get("frozen") is False
                        and is_count((options.get("recon") or {}).get("problems")) and options["recon"]["problems"] == 0
                        and epoch((options.get("recon") or {}).get("as_of")) is not None
                        and 0 <= at - epoch(options["recon"]["as_of"]) <= 600)
    realized = correction = other = unreconciled = cash_total = None
    if brokerage_ok and raw_cash is not None:
        # Reuse the existing account convention: diagnostic problems do not veto known cash. Fee corrections belong
        # to their position once; unmatched corrections go to Other; known unreconciled dollars remain a visible line.
        book = {"as_of": options.get("as_of"), "pnl_usd": money(raw_cash),
                "rows": [{"pid": int(pid), "pnl_usd": money(value)} for pid, value in cash_rows.items()]}
        trading, positions = complete_trading(book, {**broker, "blocking": []}, at=as_of)
        cash_total = decimal(trading["pnl_usd"])
        if cash_total is not None:
            realized = sum((decimal(r["pnl_usd"]) for r in positions["rows"]), ZERO)
            correction = realized - raw_cash
            other = sum((decimal(positions["other"][k]) for k in ("fees_usd", "crypto_usd", "interest_usd", "misc_usd")), ZERO)
            unreconciled = decimal(positions["unreconciled_usd"])
    if not brokerage_ok or realized is None or other is None:
        unresolved.append("brokerage cash/fee reconciliation is missing, stale, blocked, or predates a book change")
    if not is_count(options.get("open_or_unresolved")) or options["open_or_unresolved"] != 0 or raw_cash is None:
        unresolved.append("open or unresolved options prevent a complete realized project Net")
        # The closed rows remain useful, but a whole-account cash figure would incorrectly absorb fee corrections
        # for positions whose current cash/inventory is absent from this intentionally realized-only report.
        cash_total = None
    if epoch(broker.get("as_of")) != at:
        unresolved.append("broker activity and cost sources do not share the reporting cutoff")
    if epoch(options.get("as_of")) != at:
        unresolved.append("the options book and cost sources do not share the reporting cutoff")
    known = sum((decimal(v["usd"]) for v in inputs.values() if v["usd"] is not None), ZERO)
    complete = not unresolved and cash_total is not None
    return {"schema": SCHEMA, "as_of": as_of, "cost_start": T0, "financial_start": FINANCIAL_START,
            "inputs": inputs, "known_input_subtotal_usd": money(known),
            "provisional_subtotal_with_active_box_estimate_usd": money(known + estimate) if estimate is not None else None,
            "comparison_only": {"booked_gym_box_estimate_usd": (models.get("booked_usd") or {}).get("gym_box"), "included_in_total": False},
            "reservations_and_provider_comparison": {"booked_model_holds": models.get("holds"),
                                                      "claude_unverified_bookings": models.get("claude_unverified_bookings"),
                                                      "provider_requests": provider, "additional_invoice_charge": False},
            "trading": {"book_closed_net_cash_usd": money(raw_cash), "fees_already_in_cash_usd": options.get("fees_already_in_cash_usd"),
                        "broker_fee_correction_usd": money(correction) if brokerage_ok else None, "realized_options_net_usd": money(realized),
                        "other_reconciled_account_activity_usd": money(other), "cached_broker_receipt_consistent": brokerage_ok,
                        "account_unreconciled_usd": money(unreconciled), "diagnostic_notes": broker.get("problems"),
                        "broker_reconciled": brokerage_ok and unreconciled == ZERO and epoch(broker.get("as_of")) == at and epoch(options.get("as_of")) == at,
                        "book_as_of": options.get("as_of"), "broker_as_of": broker.get("as_of"), "open_or_unresolved": options.get("open_or_unresolved")},
            "known_realized_less_known_inputs_usd": money(cash_total - known) if cash_total is not None else None,
            "project_net_usd": money(cash_total - known) if complete else None,
            "complete": complete, "unresolved": sorted(set(unresolved)),
            "provenance": {"state_receipt_sha": digest(evidence), "box_receipt_sha": digest(boxes), "external_receipt_sha": digest(external),
                           "subscription_rate_override_sha": digest(subscription_rates),
                           "component_as_of": {k: v.get("as_of") for k, v in sources.items()}, "subscription_month_seconds": str(MONTH_SECONDS)},
            "limitations": ["Known subtotal excludes missing/unresolved categories; it is not complete project Net.",
                            "Closed position cash already includes fees; only broker-posted corrections are added once.",
                            "Deposits, withdrawals, raw account equity and practice P&L are never treated as profit.",
                            "Broker receipt coverage uses existing account-activity conventions; later posted fees can revise the record."]}


def persist(root: Path, value: Mapping[str, Any]) -> Path:
    """Content-addressed, private and idempotent. No ledger mutation and no rewritten history."""
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / (digest(value) + ".json")
    raw = canonical(value) + b"\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix=".pending-", delete=False) as file:
            temporary = Path(file.name)
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ValueError("existing snapshot does not match its content hash")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return path


__all__ = ["collect", "report", "persist", "T0", "FINANCIAL_START"]
