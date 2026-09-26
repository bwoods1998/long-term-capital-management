"""Read-only, PRIVATE post-close execution comparison; never fits or installs a model.

    python -m league.live.execution_report --root /workspace/state --day 2026-09-28 --out /private/report-20260928

Outputs JSON and Markdown containing licensed observations. Keep them outside git and public/site paths. Paper
proves routing; shadow is a simulation; only separately reviewed real exposure could inform a future calibration.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .evidence import FILE, HEALTH, NY, QUOTE_STALE_SECONDS, dumps, number
from .venue import parse_time


def readonly(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    return db


def reply(event: dict) -> dict | None:
    data = event["data"]
    detail = data.get("detail")
    if event["source"] == "real" and event["kind"] == "reply":
        return detail if isinstance(detail, dict) else None
    if event["kind"] in ("submit_reply", "lookup", "open_sent", "close_sent", "cleanup_sent", "order_observed") \
            and isinstance(detail, dict) and isinstance(detail.get("answer"), dict):
        return detail["answer"]
    return None


def filled_legs(body: dict, answer: dict | None) -> tuple[list[dict], list[str]]:
    if answer is None:
        return [], ["no_broker_reply"]
    requested = body.get("legs") or ([body] if body.get("symbol") else [])
    actual = answer.get("legs") or ([answer] if answer.get("symbol") else [])
    found = {r.get("symbol"): r for r in actual}
    if len(found) != len(actual) or set(found) != {r.get("symbol") for r in requested}:
        return [], ["broker_leg_identity_unreadable"]
    rows, missing = [], []
    for leg in requested:
        got = found[leg["symbol"]]
        qty, price = number(got.get("filled_qty")), number(got.get("filled_avg_price"))
        target = number(body.get("qty"))
        ratio = number(leg.get("ratio_qty", 1))
        if (qty is None or qty < 0 or qty != int(qty) or target is None or ratio is None or ratio <= 0
                or qty > target * ratio or got.get("side") != leg.get("side") or (qty and (price is None or price < 0))):
            missing.append("broker_leg_fill_unreadable")
        rows.append({"symbol": leg["symbol"], "direction": 1 if leg["side"] == "buy" else -1,
                     "ratio": ratio, "filled_qty": qty, "vwap": price,
                     "broker_filled_at": got.get("filled_at")})
    return rows, sorted(set(missing))


def comparison(quote: dict | None, fills: list[dict], submitted_at: float | None) -> dict:
    unknown = {"natural_slippage_usd": None, "mid_slippage_usd": None, "half_spreads": None,
               "basis": "sampled_NBBO_not_exchange_fill_time", "missing": []}
    if not quote or quote.get("status") != "sampled":
        return dict(unknown, missing=["quote_sample_missing"])
    quoted = {r["symbol"]: r for r in quote.get("legs") or []}
    actual = natural = mid = 0.0
    missing = set()
    for fill in fills:
        qty, price = fill["filled_qty"], fill["vwap"]
        if qty == 0:
            continue
        row = quoted.get(fill["symbol"])
        if row is None or qty is None or price is None:
            missing.add("leg_or_fill_missing")
            continue
        if row.get("observation_status") not in (None, "accepted"):
            missing.add("quote_" + row["observation_status"])
        bid, ask, stamp, observed = (number(row.get(k)) for k in ("bid", "ask", "quote_at", "received_at"))
        if bid is None or ask is None or not (0 <= bid <= ask and ask > 0):
            missing.add("NBBO_invalid")
            continue
        if stamp is None or observed is None:
            missing.add("quote_timing_unknown")
        elif stamp > observed or (submitted_at is not None and observed > submitted_at):
            missing.add("quote_not_observed_by_reference_time")
        elif observed - stamp > QUOTE_STALE_SECONDS or (submitted_at is not None and submitted_at - stamp > QUOTE_STALE_SECONDS):
            missing.add("quote_stale")
        sign = -fill["direction"] * qty * 100
        actual += sign * price
        natural += sign * (ask if fill["direction"] > 0 else bid)
        mid += sign * (bid + ask) / 2
    if missing or not any((r["filled_qty"] or 0) > 0 for r in fills):
        return dict(unknown, missing=sorted(missing) or ["no_fill"])
    half = mid - natural
    return {"natural_slippage_usd": round(natural - actual, 8), "mid_slippage_usd": round(mid - actual, 8),
            "half_spreads": (mid - actual) / half if half > 1e-12 else None,
            "basis": unknown["basis"], "missing": [], "reference_minute": quote.get("minute")}


def complete_sample(quote: dict) -> bool:
    return (quote.get("status") == "sampled" and bool(quote.get("legs")) and all(
        r.get("quote_at") is not None and r.get("received_at") is not None
        and r["quote_at"] <= r["received_at"]
        and r["received_at"] - r["quote_at"] <= QUOTE_STALE_SECONDS
        and r.get("observation_status") == "accepted"
        and r.get("bid_size_status") == r.get("ask_size_status") == "quoted"
        for r in quote["legs"]))


def chronology(body: dict, answers: list[tuple[dict, dict]]) -> list[str]:
    """A stale/corrected broker snapshot is uncertainty, never a new settled cumulative total."""
    previous: dict[str, dict] = {}
    clocks: dict[str, float] = {}
    ids: set[str] = set()
    missing = set()
    for _, answer in answers:
        cid = body.get("client_order_id")
        if cid and answer.get("client_order_id") != cid:
            missing.add("broker_client_identity_unreadable")
        if answer.get("id"):
            ids.add(str(answer["id"]))
        rows, bad = filled_legs(body, answer)
        if bad:
            # An initial explicit refusal has no leg fills; it still cannot establish a fill total.
            continue
        for row in rows:
            old = previous.get(row["symbol"])
            qty, price = row["filled_qty"], row["vwap"]
            if old is not None:
                old_qty, old_price = old["filled_qty"], old["vwap"]
                if qty < old_qty:
                    missing.add("cumulative_leg_fill_regressed")
                if qty == old_qty and qty > 0 and abs(price - old_price) > 1e-9:
                    missing.add("cumulative_price_changed_without_quantity")
                if qty > old_qty and old_qty > 0 and qty * price < old_qty * old_price - 1e-9:
                    missing.add("cumulative_fill_value_regressed")
            previous[row["symbol"]] = row
        for key in ("updated_at", "filled_at"):
            stamp = parse_time(answer.get(key))
            if stamp is not None:
                if key in clocks and stamp < clocks[key]:
                    missing.add("broker_timestamp_regressed")
                clocks[key] = stamp
    if len(ids) > 1:
        missing.add("broker_order_identity_changed")
    return sorted(missing)


def order_report(source: str, ident: str, events: list[dict], checkpoints: dict[str, int] | None = None) -> dict:
    first = next((e for e in events if e["kind"] == "submit"), None)
    decision = next((e for e in events if e["kind"] == "decision"), None)
    reference = first or decision
    data = reference["data"] if reference else {}
    work = data.get("work") or {}
    body = data.get("body") or work.get("body") or {}
    opportunities = [e for e in events if e["kind"] == "opportunity"]
    models = sorted({e["data"]["model"]["sha256"] for e in events if e["data"].get("model")})
    identities = {(e["data"]["model"].get("sha256"), e["data"]["model"].get("engine_bundle"))
                  for e in events if e["data"].get("model")}
    out = {"source": source, "id": ident, "model_hashes": models, "submission_observed_at": first["at"] if first else None,
           "decision_observed_at": decision["at"] if decision else None,
           "decision_minute": (decision["data"].get("decision_minute",
                               (decision["data"].get("quote") or {}).get("minute"))) if decision else None,
           "pricing_reference_minute": (data.get("quote") or {}).get("minute"),
           "opportunity_samples": len(opportunities), "rejections": [], "missing": [],
           "calibration_eligible": False, "calibration_action": "none", "fees_usd": None}
    out["cashflow_scope"] = "cumulative_order_through_last_observation; not session P&L"
    out["engine_bundles"] = sorted({engine for _, engine in identities if engine})
    out["execution_identities"] = [{"model_sha256": sha, "engine_bundle": engine}
                                   for sha, engine in sorted(identities, key=lambda item: (str(item[0]), str(item[1])))]
    out["comparison_scope"] = "sampled_quote_benchmark; no fitted probability or exact venue replay"
    if len(models) != 1:
        out["missing"].append("model_identity_missing_or_changed")
    identity_uncertain = len(identities) != 1 or any(not sha or not engine for sha, engine in identities)
    if identity_uncertain:
        out["missing"].append("model_engine_identity_missing_or_changed")
    if not reference:
        out["missing"].append("submission_or_decision_receipt_missing")
    if source == "shadow":
        fills = [e for e in events if e["kind"] == "fill"]
        checkpoints = checkpoints or {}
        confirmed = [e for e in fills if isinstance(e.get("seq"), int)
                     and e["seq"] < checkpoints.get(e["data"].get("recorder_run"), -1)]
        if len(confirmed) != len(fills):
            out["missing"].append("uncheckpointed_shadow_fill_or_replay")
        out.update(gross_cashflow_usd=(sum(e["data"]["detail"]["cashflow"] for e in fills)
                                      if len(confirmed) == len(fills) and not identity_uncertain else None),
                   fees_usd=(sum(e["data"]["detail"]["fees"] for e in fills)
                             if len(confirmed) == len(fills) and not identity_uncertain else None),
                   fee_provenance="venue_table_simulation",
                   simulated_fills=[dict(e["data"]["detail"], observed_at=e["at"], checkpointed=e in confirmed) for e in fills],
                   simulated_arrival_index=(work.get("arrival_mi")),
                   working_opportunities=[{"sample_minute": (e["data"].get("quote") or {}).get("minute"),
                                           "next_sample_minute": (e["data"].get("next_quote") or {}).get("minute"),
                                           "observed_at": e["at"], "seen": e["data"]["work"].get("seen"),
                                           "aggressive": e["data"]["work"].get("aggressive")} for e in opportunities])
        prior_seen = False
        for e in opportunities:
            seen = bool(e["data"]["work"].get("seen"))
            if prior_seen and not seen:
                out["missing"].append("working_state_discontinuity")
            if e["data"]["work"].get("fill_flags_known") is not True:
                out["missing"].append("legacy_working_flags_unknown")
            prior_seen |= seen
        usable = [e for e in opportunities if all(complete_sample(e["data"].get(k) or {})
                                                  for k in ("quote", "next_quote"))]
        out["incomplete_opportunity_samples"] = len(opportunities) - len(usable)
        if len(usable) != len(opportunities):
            out["missing"].append("opportunity_inputs_incomplete")
        out["nonfill_samples"] = sum(1 for e in usable if not any(
            f["data"]["detail"].get("simulated_minute") == (e["data"].get("quote") or {}).get("minute") for f in fills))
        out["natural_slippage"] = None  # full samples retained privately; not independent execution validation
        return out
    answers = [(e, reply(e)) for e in events]
    answers = [(e, a) for e, a in answers if a is not None]
    answer = answers[-1][1] if answers else None
    legs, missing = filled_legs(body, answer)
    uncertain = chronology(body, answers)
    missing += uncertain
    out["missing"] += missing
    out["legs"] = legs
    out["status"] = "uncertain" if uncertain else answer.get("status") if answer else None
    out["broker_reported_status"] = answer.get("status") if answer else None
    out["gross_cashflow_usd"] = (None if missing else round(sum(
        -r["direction"] * r["filled_qty"] * (r["vwap"] or 0) * 100 for r in legs), 8))
    out["fee_provenance"] = "unknown" if source == "paper" else "venue_table_estimate_in_real_book"
    broker_submit = answer.get("submitted_at") if answer else None
    broker_fill = answer.get("filled_at") if answer else None
    start, end = parse_time(broker_submit), parse_time(broker_fill)
    out["broker_submitted_at"], out["broker_filled_at"] = broker_submit, broker_fill
    out["broker_fill_latency_seconds"] = end - start if start is not None and end is not None and end >= start else None
    if any((r["filled_qty"] or 0) > 0 for r in legs) and out["broker_fill_latency_seconds"] is None:
        out["missing"].append("broker_fill_timing_unknown")
    if source == "paper":
        out["missing"].append("paper_fees_not_recorded")
    first_fill = next((e["at"] for e, a in answers if any((number(r.get("filled_qty")) or 0) > 0
                                                        for r in (a.get("legs") or [a]))), None)
    out["first_fill_observed_at"] = first_fill
    out["observation_latency_seconds"] = (first_fill - first["at"] if first and first_fill is not None else None)
    out["submission_sample_comparison"] = comparison(data.get("quote"), legs, first["at"] if first else None)
    if uncertain:
        out["submission_sample_comparison"] = {"natural_slippage_usd": None, "mid_slippage_usd": None,
                                               "half_spreads": None, "missing": uncertain,
                                               "basis": "unreconciled_broker_snapshots"}
    out["missing"] += out["submission_sample_comparison"]["missing"]
    # Nonfill means an observed working order and a readable zero fill, never a skipped wall minute.
    out["observed_working_samples"] = len(opportunities)
    for e in events:
        detail = e["data"].get("detail") or {}
        if isinstance(detail, dict) and (detail.get("error") or detail.get("reject_reason")):
            out["rejections"].append({"at": e["at"], "reason": detail.get("error") or detail.get("reject_reason")})
    out["missing"] = sorted(set(out["missing"]))
    return out


def matching_fees(order: dict, rows: list[dict], cutoff: float) -> float | None:
    """Match the broker's witnessed cumulative units, not every future fill on this client ID."""
    if order.get("gross_cashflow_usd") is None or not order.get("legs"):
        return None
    units = {r["filled_qty"] / r["ratio"] for r in order["legs"] if r["filled_qty"] is not None and r["ratio"]}
    if len(units) != 1:
        return None
    target = next(iter(units))
    if target != int(target):
        return None
    qty = total = 0.0
    for row in rows:
        if qty == target:
            return total
        at, add, fee = number(row["at"]), number(row["qty"]), number(row["fees"])
        if at is None or add is None or fee is None or add <= 0:
            return None
        if at >= cutoff:
            continue
        qty += add
        total += fee
        if qty > target:
            return None
    return total if qty == target else None


def report(root: Path, day: str) -> dict:
    """No write, external API, model call or calibration. A consistent SQLite read snapshot per input."""
    from .chains import session_minutes
    date = dt.date.fromisoformat(day)
    out = {"schema": 1, "day": day, "private": True, "complete": False, "gaps": [], "orders": [],
           "trades": [], "rejections": [], "model_identities": [], "calibration": {"action": "none", "paper_eligible": False,
           "shadow_eligible": False, "real_fit": "not_attempted; requires separately reviewed complete exposure"},
           "goal_note": "The Done sentence mentions paper calibration; the detailed fill contract excludes synthetic paper fills."}
    path = Path(root) / FILE
    if not path.is_file():
        out["gaps"].append("execution_database_missing")
        return out
    with closing(readonly(path)) as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM events WHERE day=? ORDER BY seq", (day,))]
        coverage_rows = [list(r) for r in db.execute("SELECT minute,complete FROM coverage WHERE day=? ORDER BY minute", (day,))]
        gap_rows = [r[0] for r in db.execute("SELECT reason FROM gaps WHERE day=? ORDER BY reason", (day,))]
        pending = db.execute("SELECT value FROM meta WHERE key='pending'").fetchone()
        models = {r["hash"]: dict(r) for r in db.execute("SELECT * FROM models ORDER BY hash")}
    # Release the short read snapshot before parsing and formatting potentially many private observations.
    events = [dict(r, data=json.loads(r["body"])) for r in rows]
    coverage = {int(r[0]): r[1] == 1 for r in coverage_rows}
    gaps = list(gap_rows)
    if pending and json.loads(pending[0])["day"] == day:
        gaps.append("pending_or_failed_observation")
    health = Path(root) / HEALTH
    health_input = None
    if health.exists():
        try:
            health_input = health.read_text()
            if json.loads(health_input).get(day, {}).get("incomplete"):
                gaps.append("recorder_write_failure")
        except (ValueError, OSError, AttributeError) as exc:
            if health_input is None:
                health_input = {"read_error": type(exc).__name__}
            gaps.append("recorder_health_unreadable")
    session = session_minutes(date)
    missing_minutes = [m for m in range(session[0], session[1] + 1) if not coverage.get(m)] if session else []
    out["coverage"] = {"recorded_minutes": sum(coverage.values()), "missing_minutes": missing_minutes}
    if missing_minutes:
        gaps.append("session_coverage_incomplete")
    grouped: dict[tuple[str, str], list[dict]] = {}
    completed_trades: dict[str, list[dict]] = {}
    model_refs = set()
    checkpoints = {}
    for event in events:
        data = event["data"]
        if event["kind"] == "checkpoint" and event["source"] == "shadow":
            checkpoints[data["recorder_run"]] = event["seq"]
        if data.get("model"):
            model_refs.add(data["model"]["sha256"])
        if event["kind"] == "trade" and event["source"] == "shadow":
            completed_trades.setdefault(event["ident"], []).append(event)
        if event["kind"] == "rejection":
            out["rejections"].append({"source": event["source"], "instance": event["ident"],
                                      "observed_at": event["at"], "detail": data.get("detail")})
        if data.get("work") or data.get("order"):
            grouped.setdefault((event["source"], event["ident"]), []).append(event)
    for sha in sorted(model_refs):
        model = models.get(sha)
        if model is None or hashlib.sha256(model["body"].encode()).hexdigest() != sha:
            gaps.append("model_artifact_missing_or_corrupt")
        else:
            engines = sorted({e["data"]["model"]["engine_bundle"] for e in events
                              if (e["data"].get("model") or {}).get("sha256") == sha
                              and e["data"]["model"].get("engine_bundle")})
            out["model_identities"].append({"sha256": sha, "version": model["version"], "engine_bundles": engines})
    out["orders"] = [order_report(source, ident, es, checkpoints) for (source, ident), es in grouped.items()]
    for ident, observations in completed_trades.items():
        witnessed = [dict(observed_at=e["at"], trade=e["data"]["detail"],
                          recorder_run=e["data"]["recorder_run"],
                          checkpointed=e["seq"] < checkpoints.get(e["data"]["recorder_run"], -1))
                     for e in observations]
        confirmed = all(e["checkpointed"] for e in witnessed)
        out["trades"].append({"source": "shadow", "id": ident, "instance": observations[-1]["data"]["instance"],
                              "observed_at": witnessed[-1]["observed_at"], "checkpointed": confirmed,
                              "trade": witnessed[-1]["trade"] if confirmed else None, "observations": witnessed})
        if not confirmed:
            gaps.append("uncheckpointed_shadow_trade_or_replay")
    # Link existing authoritative real fills/fees and census paper/real requests without querying either venue.
    state = Path(root) / "live.sqlite"
    census = []
    account_input = None
    if state.exists():
        with closing(readonly(state)) as db:
            begin = dt.datetime.combine(date, dt.time(), NY).timestamp()
            end = dt.datetime.combine(date + dt.timedelta(days=1), dt.time(), NY).timestamp()
            real = [dict(r) for r in db.execute("SELECT * FROM orders WHERE day=? OR oid IN "
                "(SELECT oid FROM fills WHERE at>=? AND at<?) OR status IN ('pending','working','unknown') ORDER BY oid",
                (day, begin, end))]
            oids = [r["oid"] for r in real]
            fills = ([dict(r) for r in db.execute("SELECT * FROM fills WHERE oid IN (" + ",".join("?" for _ in oids)
                                                + ") ORDER BY id", oids)] if oids else [])
            paper = db.execute("SELECT value FROM kv WHERE key='paper_proof'").fetchone()
        account_input = {"orders": real, "fills": fills, "paper_proof": paper[0] if paper else None}
        for row in real:
            census.append(["real", row["client_id"]])
            found = next((o for o in out["orders"] if o["source"] == "real" and o["id"] == row["client_id"]), None)
            if found is not None:
                found["fees_usd"] = matching_fees(found, [f for f in fills if f["oid"] == row["oid"]], end)
                if found["fees_usd"] is None:
                    found["missing"].append("authoritative_fee_scope_unmatched")
        if paper:
            proof = json.loads(paper[0])
            for work in proof.get("orders") or []:
                stamp = number(work.get("at"))
                if stamp is not None and dt.datetime.fromtimestamp(stamp, NY).date() == date:
                    census.append(["paper", work["cid"]])
            out["paper_proof"] = {k: proof.get(k) for k in ("day", "status", "open_witness", "close_witness")}
    else:
        gaps.append("authoritative_live_state_missing")
    recorded = {(o["source"], o["id"]) for o in out["orders"]}
    if any(tuple(k) not in recorded for k in census):
        gaps.append("authoritative_order_receipt_missing")
    for order in out["orders"]:
        if order["missing"]:
            gaps.append("one_or_more_order_comparisons_incomplete")
        gross, fees = order.get("gross_cashflow_usd"), order.get("fees_usd")
        order["net_cashflow_usd"] = gross - fees if gross is not None and fees is not None else None
    out["counts"] = {source: sum(o["source"] == source for o in out["orders"]) for source in ("paper", "shadow", "real")}
    digest = lambda value: hashlib.sha256(dumps(value).encode()).hexdigest()
    out["input_manifest"] = {
        "schema": 1, "day": day, "session": list(session) if session else None,
        "code_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                        for name in ("execution_report.py", "evidence.py", "venue.py", "chains.py")},
        "execution_sha256": digest({"events": rows, "coverage": coverage_rows, "gaps": gap_rows,
                                     "pending": pending[0] if pending else None, "models": models}),
        "accounting_sha256": digest(account_input), "health_sha256": digest(health_input),
    }
    out["input_sha256"] = digest(out["input_manifest"])
    out["gaps"] = sorted(set(gaps))
    out["complete"] = not out["gaps"]
    return out


def markdown(result: dict) -> str:
    lines = [f"# Private execution report — {result['day']}", "",
             "Complete evidence: " + ("yes" if result["complete"] else "no"), "",
             "Paper is a route diagnostic. Shadow is simulated. No model was fitted or installed.", ""]
    if result["gaps"]:
        lines += ["Missing evidence: " + ", ".join(result["gaps"]), ""]
    lines += ["| Source | Order | Gross cashflow | Fees | Status |", "|---|---|---:|---:|---|"]
    for order in result["orders"]:
        lines.append(f"| {order['source']} | {order['id']} | {order.get('gross_cashflow_usd')} | "
                     f"{order.get('fees_usd')} | {order.get('status', 'simulated')} |")
    lines += ["", "Full timings, quantities, provenance and completeness reasons are in the adjacent private JSON.",
              "This report compares captured sampled NBBO; it does not invent an exchange-time quote or fill probability.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--day", required=True)
    parser.add_argument("--out", type=Path, required=True, help="private output prefix, outside git and site paths")
    args = parser.parse_args(argv)
    result = report(args.root, args.day)
    for suffix, content in ((".json", json.dumps(result, indent=2, sort_keys=True) + "\n"), (".md", markdown(result))):
        path = Path(str(args.out) + suffix)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
    return result


if __name__ == "__main__":
    main()
