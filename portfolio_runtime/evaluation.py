"""Read-only, paired Sail experiment accounting; source checks are not alpha.

Comparisons are admitted only after their frozen inputs match. Provider costs,
unfinished requests, cache writes and missing arms remain visible. No model text,
credentials, request identifiers or account information enters this projection.
"""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote


TERMINAL = frozenset(("completed", "failed", "cancelled", "incomplete"))
WINDOWS = ("asap", "balanced", "flex")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _decode(value):
    if not isinstance(value, str) or len(value) > 8_000_000:
        return None
    try:
        return json.loads(value, parse_constant=lambda item: None)
    except (ValueError, TypeError):
        return None


def _money(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]{0,14})(?:\.[0-9]{1,18})?(?:[Ee][+-]?\d{1,2})?", value
    ):
        return None
    result = Decimal(value)
    return (
        result
        if result.is_finite()
        and result <= Decimal("1000000000000000")
        and result.as_tuple().exponent >= -24
        else None
    )


def _text(value):
    raw = format(value, "f")
    return (
        raw.rstrip("0").rstrip(".") if "." in raw and value else raw if value else "0"
    )


def _mean(values):
    if not values:
        return None
    return _text(
        (sum(values, Decimal(0)) / len(values)).quantize(
            Decimal("0.000000000001"), rounding=ROUND_HALF_EVEN
        )
    )


def _time(value):
    return (
        type(value) in (float, int)
        and math.isfinite(value)
        and 0 <= value <= 10_000_000_000
    )


def _latency(row):
    if (
        row["status"] not in TERMINAL
        or not _time(row.get("created"))
        or not _time(row.get("updated"))
    ):
        return None
    result = Decimal(str(row["updated"])) - Decimal(str(row["created"]))
    return result if result >= 0 else None


def _distribution(values):
    values = sorted(values)
    if not values:
        return {"samples": 0, "median_seconds": None, "p95_seconds": None}
    middle = len(values) // 2
    median = (
        values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    )
    p95 = values[max(0, math.ceil(len(values) * 0.95) - 1)]
    return {
        "samples": len(values),
        "median_seconds": float(round(median, 3)),
        "p95_seconds": float(round(p95, 3)),
    }


def _read(path, tables):
    url = "file:" + quote(str(Path(path).resolve()), safe="/") + "?mode=ro"
    db = sqlite3.connect(url, uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN")
        names = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if tables[0] not in names:
            raise ValueError("The evaluation database lacks its required runtime table")
        result = {}
        for table in tables:
            if table not in names:
                result[table] = []
                continue
            # Read only aggregate inputs, and discard each large prompt before
            # fetching the next. A long shared prefix can occupy hundreds of MB
            # on disk; retaining raw and decoded copies would exhaust the host.
            wanted = {
                "requests": (
                    "id",
                    "task_id",
                    "profile",
                    "body",
                    "cost",
                    "response",
                    "status",
                    "created",
                    "updated",
                    "cache",
                ),
                "tasks": (
                    "id",
                    "wave",
                    "kind",
                    "symbol",
                    "profile",
                    "cache",
                    "body",
                    "request_id",
                    "grade",
                ),
                "events": ("at", "kind", "payload"),
                "allocations": ("id", "cost"),
            }[table]
            available = {
                row[1] for row in db.execute("PRAGMA table_info(" + table + ")")
            }
            columns = ",".join(name for name in wanted if name in available)
            result[table] = []
            for count, raw in enumerate(
                db.execute("SELECT " + columns + " FROM " + table + " LIMIT 100001"), 1
            ):
                if count > 100000:
                    raise ValueError(
                        "The evaluation snapshot exceeds its reviewed row limit"
                    )
                row = dict(raw)
                if table in ("requests", "tasks"):
                    row["_body"] = _fingerprints(
                        row.pop("body", None), paired=table == "tasks"
                    )
                if table == "requests":
                    row["_usage"] = _usage(row)
                    row.pop("response", None)
                if table == "tasks":
                    row["_grade"] = _grade(row)
                    row.pop("grade", None)
                result[table].append(row)
        return result
    finally:
        db.close()


def _usage(row):
    if "_usage" in row:
        return row["_usage"]
    response = _decode(row.get("response"))
    if not isinstance(response, dict):
        return None
    usage = response.get("usage")
    metadata = response.get("metadata") or {}
    if not isinstance(usage, dict) or not isinstance(metadata, dict):
        return None
    details = usage.get("input_tokens_details") or {}
    if not isinstance(details, dict):
        return None
    values = [
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        details.get("cached_tokens", 0),
    ]
    if (
        any(type(value) is not int or value < 0 for value in values)
        or values[2] > values[0]
    ):
        return None
    counters = []
    for name in ("supercached_input_tokens", "supercache_write_input_tokens"):
        value = metadata.get(name, "0")
        if not isinstance(value, str) or not re.fullmatch(r"\d{1,16}", value):
            return None
        counters.append(int(value))
    if counters[0] > values[2] or counters[1] > values[0] - values[2]:
        return None
    if row.get("cache") in ("write", "read") and not all(
        name in metadata
        for name in ("supercached_input_tokens", "supercache_write_input_tokens")
    ):
        return None
    return dict(
        zip(
            (
                "input_tokens",
                "output_tokens",
                "cached_tokens",
                "supercached_tokens",
                "written_tokens",
            ),
            values + counters,
        )
    )


def _grade(task):
    if task and "_grade" in task:
        return task["_grade"]
    value = _decode(task.get("grade")) if task else None
    if (
        not isinstance(value, dict)
        or type(value.get("source_check_passed")) is not bool
    ):
        return None
    if type(value.get("claims_checked")) is not int or value["claims_checked"] < 0:
        return None
    return {
        "passed": value["source_check_passed"],
        "claims_checked": value["claims_checked"],
    }


def _stats(rows):
    costs = [row["_cost"] for row in rows if row["_cost"] is not None]
    grades = [row["_grade"] for row in rows if row["_grade"] is not None]
    times = [value for row in rows if (value := _latency(row)) is not None]
    usage = [value for row in rows if (value := _usage(row)) is not None]
    return {
        "requests": len(rows),
        "completed": sum(row["status"] == "completed" for row in rows),
        "terminal_failures": sum(
            row["status"] in TERMINAL - {"completed"} for row in rows
        ),
        "known_cost_usd": _text(sum(costs, Decimal(0))),
        "unsettled_requests": len(rows) - len(costs),
        "source_checks_passed": sum(value["passed"] for value in grades),
        "source_checks_evaluated": len(grades),
        "claims_checked": sum(value["claims_checked"] for value in grades),
        "token_receipts": len(usage),
        "tokens": {
            key: sum(value[key] for value in usage)
            for key in (
                "input_tokens",
                "output_tokens",
                "cached_tokens",
                "supercached_tokens",
                "written_tokens",
            )
        },
        "intent_to_terminal": _distribution(times),
    }


def _paired(pairs, left, right):
    costs, latencies, source = (
        [],
        [],
        {
            "both_passed": 0,
            "left_only_passed": 0,
            "right_only_passed": 0,
            "neither_passed": 0,
        },
    )
    for first, second in pairs:
        if first["_cost"] is not None and second["_cost"] is not None:
            costs.append(second["_cost"] - first["_cost"])
        a, b = _latency(first), _latency(second)
        if a is not None and b is not None:
            latencies.append(b - a)
        a, b = first["_grade"], second["_grade"]
        if a is not None and b is not None:
            key = (
                "both_passed"
                if a["passed"] and b["passed"]
                else "left_only_passed"
                if a["passed"]
                else "right_only_passed"
                if b["passed"]
                else "neither_passed"
            )
            source[key] += 1
    return {
        "left": left,
        "right": right,
        "matched_inputs": len(pairs),
        "cost_pairs": len(costs),
        "mean_right_minus_left_cost_usd": _mean(costs),
        "latency_pairs": len(latencies),
        "mean_right_minus_left_seconds": _mean(latencies),
        "source_check_pairs": sum(source.values()),
        "source_checks": source,
    }


def _window_body(body):
    if not isinstance(body, dict) or not isinstance(body.get("metadata"), dict):
        return None
    normalized = {**body, "metadata": dict(body["metadata"])}
    normalized["metadata"].pop("completion_window", None)
    return normalized


def _memory_body(body):
    if (
        not isinstance(body, dict)
        or not isinstance(body.get("input"), list)
        or any(not isinstance(message, dict) for message in body["input"])
    ):
        return None, None
    normalized = {**body, "input": [dict(message) for message in body["input"]]}
    user = [message for message in normalized["input"] if message.get("role") == "user"]
    if len(user) != 1:
        return None, None
    packet = _decode(user[0].get("content"))
    if (
        not isinstance(packet, dict)
        or not isinstance(packet.get("prior_work"), list)
        or "evidence" not in packet
    ):
        return None, None
    history = packet.pop("prior_work")
    user[0]["content"] = _json(packet)
    return normalized, history


def _cache_body(body):
    if (
        not isinstance(body, dict)
        or not isinstance(body.get("input"), list)
        or any(not isinstance(message, dict) for message in body["input"])
    ):
        return None
    normalized = {**body, "input": [dict(message) for message in body["input"]]}
    normalized.pop("prompt_cache_key", None)
    metadata = normalized.get("metadata")
    if not isinstance(metadata, dict):
        return None
    metadata = normalized["metadata"] = dict(metadata)
    metadata.pop("supercache_write", None)
    # The experiment intentionally changes this routing line to keep its
    # ordinary-cache arm separate. Every remaining byte must agree.
    for message in normalized["input"]:
        if message.get("role") == "system" and isinstance(message.get("content"), str):
            message["content"] = re.sub(
                r"\AExperiment context: [A-Za-z0-9_-]+\.\n",
                "",
                message["content"],
                count=1,
            )
    return normalized


def _fingerprints(raw, *, paired):
    """Compact SHA256 identities of full and explicitly normalized inputs.

    Canonical JSON equality remains the cross-database binding rule. Paired
    fingerprints remove only each experiment's designated intervention; every
    other input byte, model setting and output ceiling contributes to the hash.
    Raw frozen requests remain unchanged in their original databases.
    """
    body = _decode(raw)
    if not isinstance(body, dict):
        return None

    def digest(value):
        return (
            hashlib.sha256(_json(value).encode()).hexdigest()
            if value is not None
            else None
        )

    result = {"full": digest(body)}
    if paired:
        metadata = body.get("metadata")
        result["window"] = (
            metadata.get("completion_window") if isinstance(metadata, dict) else None
        )
        result["window_body"] = digest(_window_body(body))
        memory, prior = _memory_body(body)
        result["memory_body"] = digest(memory)
        result["has_prior"] = bool(prior)
        result["cache_body"] = digest(_cache_body(body))
    return result


def _windows(tasks):
    groups = defaultdict(lambda: defaultdict(list))
    for task in tasks:
        if task.get("kind") == "window_pair":
            window = (task.get("_body") or {}).get("window")
            if window in WINDOWS:
                groups[(task["wave"], task["symbol"])][window].append(task)
    pairs = {
        (a, b): []
        for a, b in (("asap", "balanced"), ("asap", "flex"), ("balanced", "flex"))
    }
    missing = {window: 0 for window in WINDOWS}
    arms = {window: [] for window in WINDOWS}
    matched, mismatched, duplicate, incomplete = 0, 0, 0, 0
    for group in groups.values():
        for window in WINDOWS:
            if len(group[window]) != 1 or group[window][0].get("_request") is None:
                missing[window] += 1
            arms[window].extend(
                task["_request"]
                for task in group[window]
                if task.get("_request") is not None
            )
        if any(len(group[window]) > 1 for window in WINDOWS):
            duplicate += 1
            continue
        if any(
            len(group[window]) != 1 or group[window][0].get("_request") is None
            for window in WINDOWS
        ):
            incomplete += 1
        else:
            bodies = [group[window][0]["_body"]["window_body"] for window in WINDOWS]
            if None not in bodies and all(body == bodies[0] for body in bodies):
                matched += 1
            else:
                mismatched += 1
        for (left, right), values in pairs.items():
            if len(group[left]) != 1 or len(group[right]) != 1:
                continue
            a, b = group[left][0], group[right][0]
            if (
                a.get("_request") is not None
                and b.get("_request") is not None
                and a["_body"]["window_body"] is not None
                and a["_body"]["window_body"] == b["_body"]["window_body"]
            ):
                values.append((a["_request"], b["_request"]))
    return {
        "planned_groups": len(groups),
        "matched_triplets": matched,
        "incomplete_groups": incomplete,
        "nonidentical_input_groups": mismatched,
        "duplicate_arm_groups": duplicate,
        "missing_cells": missing,
        "arms": {window: _stats(rows) for window, rows in arms.items()},
        "paired_comparisons": [
            _paired(values, left, right) for (left, right), values in pairs.items()
        ],
    }


def _memory(tasks):
    groups = defaultdict(lambda: defaultdict(list))
    for task in tasks:
        if task.get("kind") in ("company", "fresh_review"):
            groups[(task["wave"], task["symbol"])][task["kind"]].append(task)
    eligible = [group for group in groups.values() if group["fresh_review"]]
    missing = {"company": 0, "fresh_review": 0}
    pairs, nonidentical, empty_memory, duplicate = [], 0, 0, 0
    for group in eligible:
        for kind in missing:
            if len(group[kind]) != 1 or group[kind][0].get("_request") is None:
                missing[kind] += 1
        if any(len(group[kind]) > 1 for kind in missing):
            duplicate += 1
            continue
        if any(
            len(group[kind]) != 1 or group[kind][0].get("_request") is None
            for kind in missing
        ):
            continue
        company, fresh = group["company"][0], group["fresh_review"][0]
        a, history = company["_body"]["memory_body"], company["_body"]["has_prior"]
        b, no_history = fresh["_body"]["memory_body"], fresh["_body"]["has_prior"]
        if (
            a is None
            or b is None
            or a != b
            or company["profile"] != fresh["profile"]
            or company["cache"] != fresh["cache"]
        ):
            nonidentical += 1
        elif not history or no_history:
            empty_memory += 1
        else:
            pairs.append((company["_request"], fresh["_request"]))
    return {
        "planned_pairs": len(eligible),
        "matched_pairs": len(pairs),
        "missing_cells": missing,
        "nonidentical_input_pairs": nonidentical,
        "invalid_memory_assignment_pairs": empty_memory,
        "duplicate_arm_groups": duplicate,
        "persistent": _stats([a for a, _ in pairs]),
        "fresh": _stats([b for _, b in pairs]),
        "paired_comparison": _paired(pairs, "persistent", "fresh"),
    }


def _cache(tasks, requests):
    writes = [row for row in requests if row.get("cache") == "write"]
    reads = [row for row in requests if row.get("cache") == "read"]
    ordinary = [row for row in requests if row.get("cache") == "ordinary"]
    groups = defaultdict(lambda: defaultdict(list))
    for task in tasks:
        if task.get("kind") == "cache_control":
            groups[(task["wave"], task["symbol"])]["control"].append(task)
        elif task.get("kind") == "company" and task.get("cache") == "read":
            groups[(task["wave"], task["symbol"])]["read"].append(task)
    planned = [group for group in groups.values() if group["control"]]
    pairs, missing, nonidentical, contaminated = [], 0, 0, 0
    for group in planned:
        if any(
            len(group[kind]) != 1 or group[kind][0].get("_request") is None
            for kind in ("control", "read")
        ):
            missing += 1
            continue
        read, control = group["read"][0], group["control"][0]
        a, b = read["_body"]["cache_body"], control["_body"]["cache_body"]
        if (
            a is None
            or b is None
            or a != b
            or read["profile"] != control["profile"]
            or control["cache"] != "ordinary"
        ):
            nonidentical += 1
            continue
        usage = _usage(control["_request"])
        if (
            usage is None
            or usage["supercached_tokens"] > 0
            or usage["written_tokens"] > 0
        ):
            contaminated += 1
            continue
        pairs.append((control["_request"], read["_request"]))
    cost = sum(
        (row["_cost"] for row in writes + reads if row["_cost"] is not None), Decimal(0)
    )
    complete_cost = all(row["_cost"] is not None for row in writes + reads)
    amortized = _mean([cost / len(reads)]) if reads and complete_cost else None
    cost_pairs = [
        (a, b) for a, b in pairs if a["_cost"] is not None and b["_cost"] is not None
    ]
    pair_advantage = sum((a["_cost"] - b["_cost"] for a, b in cost_pairs), Decimal(0))
    write_cost = sum(
        (row["_cost"] for row in writes if row["_cost"] is not None), Decimal(0)
    )
    all_writes_settled = bool(writes) and all(
        row["_cost"] is not None for row in writes
    )
    # This is only a descriptive estimate from observed paired requests, never a
    # hypothetical ordinary token bill or a claim that the whole run broke even.
    advantage_per_read = pair_advantage / len(cost_pairs) if cost_pairs else None
    break_even = (
        int(
            (write_cost / advantage_per_read).to_integral_value(
                rounding="ROUND_CEILING"
            )
        )
        if all_writes_settled
        and advantage_per_read is not None
        and advantage_per_read > 0
        else None
    )
    return {
        "writes": _stats(writes),
        "reads": _stats(reads),
        "ordinary_requests": _stats(ordinary),
        "write_plus_read_known_cost_usd": _text(cost),
        "write_and_read_costs_complete": complete_cost,
        "amortized_cost_per_read_usd": amortized,
        "planned_control_pairs": len(planned),
        "matched_control_pairs": len(pairs),
        "missing_control_pairs": missing,
        "nonidentical_control_pairs": nonidentical,
        "contaminated_or_unverified_control_pairs": contaminated,
        "paired_comparison": _paired(pairs, "ordinary_control", "supercache_read"),
        "observed_control_minus_read_cost_usd": _text(pair_advantage)
        if cost_pairs
        else None,
        "observed_pair_advantage_after_all_writes_usd": _text(
            pair_advantage - write_cost
        )
        if cost_pairs and all_writes_settled
        else None,
        "inferred_reads_to_amortize_writes": break_even,
        "break_even_basis": "Observed matched mean request-cost difference; assumes it repeats. Not a measured whole-run saving.",
    }


def _concurrency(events, requests):
    plans = []
    for event in events:
        payload = _decode(event.get("payload"))
        if (
            event.get("kind") == "wave_planned"
            and _time(event.get("at"))
            and isinstance(payload, dict)
            and type(payload.get("concurrency")) is int
            and 1 <= payload["concurrency"] <= 1024
        ):
            plans.append((event["at"], payload["concurrency"]))
    plans.sort()
    endpoints = []
    horizon = max(
        [row["updated"] for row in requests if _time(row.get("updated"))]
        + [at for at, _ in plans]
        + [0]
    )
    cohorts = defaultdict(list)
    for row in requests:
        if not _time(row.get("created")):
            continue
        start = row["created"]
        end = (
            row["updated"]
            if row["status"] in TERMINAL and _time(row.get("updated"))
            else horizon
        )
        if end < start:
            continue
        # End events sort before starts at the same instant: adjacent requests
        # do not falsely appear concurrent. Zero-duration receipts add no span.
        if end > start:
            endpoints.extend(((start, 1), (end, -1)))
        levels = [level for at, level in plans if at <= start]
        cohorts[levels[-1] if levels else 0].append(row)
    active, peak = 0, 0
    for _, change in sorted(endpoints):
        active += change
        peak = max(peak, active)
    return {
        "planned_levels": sorted(set(level for _, level in plans)),
        "wave_plan_events": len(plans),
        "peak_admitted_request_overlap": peak,
        "cohorts": [
            {"planned_concurrency": level or None, **_stats(rows)}
            for level, rows in sorted(cohorts.items())
        ],
        "measurement": "Admission-to-observed-terminal overlap includes local dispatch, provider queueing and polling; it is not simultaneous model execution.",
    }


def evaluate(request_db, research_db):
    """Return safe aggregate comparisons from two read-only local DB snapshots."""
    with localcontext() as context:
        context.prec = 80
        return _evaluate(request_db, research_db)


def _evaluate(request_db, research_db):
    request_snapshot = _read(request_db, ("requests", "allocations"))
    research_snapshot = _read(research_db, ("tasks", "events"))
    requests, tasks = request_snapshot["requests"], research_snapshot["tasks"]
    request_by_id = {row["id"]: row for row in requests}
    mismatched_join = 0
    for row in requests:
        row["_cost"] = (
            _money(row.get("cost")) if row.get("status") in TERMINAL else None
        )
        row["_grade"] = None
    for task in tasks:
        row = request_by_id.get(task.get("request_id"))
        if (
            row is not None
            and row.get("task_id") == task["id"]
            and row.get("profile") == task.get("profile")
            and row.get("cache") == task.get("cache")
            and task["_body"] is not None
            and row["_body"] is not None
            and row["_body"]["full"] == task["_body"]["full"]
        ):
            task["_request"] = row
            row["_grade"] = _grade(task)
        else:
            task["_request"] = None
            mismatched_join += row is not None
    allocations = request_snapshot["allocations"]
    allocation_costs = [_money(row.get("cost")) for row in allocations]
    return {
        "schema_version": 1,
        "scope": "coordinator_request_comparisons",
        "requests": _stats(requests),
        "planned_tasks": len(tasks),
        "tasks_without_attached_request": sum(
            task.get("_request") is None for task in tasks
        ),
        "mismatched_request_bindings": mismatched_join,
        "delegated_allowances": {
            "count": len(allocations),
            "unsettled": sum(cost is None for cost in allocation_costs),
            "known_cost_usd": _text(
                sum((cost for cost in allocation_costs if cost is not None), Decimal(0))
            ),
        },
        "completion_windows": _windows(tasks),
        "memory": _memory(tasks),
        "supercache": _cache(tasks, requests),
        "concurrency": _concurrency(research_snapshot["events"], requests),
        "limitations": [
            "Source checks test extracted claims against supplied evidence, not investment merit or future returns.",
            "One run gives descriptive paired observations; output randomness, cache state and queue conditions can affect results.",
            "Intent-to-terminal latency includes coordinator dispatch and polling; provider service time is not measured.",
            "Shared cache writes are included once. Inferred break-even is conditional, not observed whole-run savings.",
            "Cache treatment is submitted before its matched control; request order is not counterbalanced.",
            "Read-only database snapshots may straddle an in-progress attachment or settlement; missing cells remain explicit.",
        ],
    }
