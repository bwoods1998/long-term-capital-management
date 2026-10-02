"""The House's private receipts: `<state>/receipts/<YYYY-MM-DD>.json` (the UTC day) and `<state>/receipts/latest.json`.

One file a day, rewritten every ten minutes by the runner (on the House's background lane), and read by the operator
through the Sail Files API (`scripts/desk_receipts.py`, never an exec): every job occurrence of the day with its
receipt, a small health summary, the day's rows of `<base>/deploys.jsonl`, the swarm's spend today by kind, and the
budget's state (`<state>/budget.json`, when the budget job has written one). Private: it carries what the House's own
files carry (mode 0600 in a 0700 directory); the public scoreboard is a separate, filtered page (`scoreboard.py`).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import guard
from . import schedule as S
from .context import read_json, write_json
from .store import read_runs, summaries

SCHEMA = "ltcm-ops-receipts-1"
#: health.json keys copied into the receipt (small ones; never the per-instance or per-agent tables).
HEALTH_KEYS = ("at", "release", "real_money", "failures", "stopped_because", "restarts_24h", "restarts_24h_in_session",
               "last_start", "ops", "pluggable_steps")


def deploys_of(base: str | Path, day: str, *, limit: int = 400) -> list[dict[str, Any]]:
    """The rows of `<base>/deploys.jsonl` written on UTC `day` (their `at`), oldest first, at most `limit`."""
    path = Path(base) / "deploys.jsonl"
    out: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if day not in line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and str(row.get("at") or "").startswith(day):
                    out.append(row)
    except OSError:
        return []
    return out[-limit:]


def spend_of(root: str | Path, start: float, end: float) -> dict[str, Any] | None:
    """The swarm's spend between two instants by kind (`swarm.sqlite` `spend`), read-only; None when unreadable."""
    path = Path(root) / "swarm.sqlite"
    if not path.exists():
        return None
    try:
        rows = guard.read(path, lambda db: guard.rows(
            db, "SELECT kind, count(*) AS n, sum(usd) AS usd FROM spend WHERE epoch>=? AND epoch<? GROUP BY kind", (start, end)))
    except Exception as exc:  # noqa: BLE001 - a receipt says what it could not read
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return {r["kind"]: {"n": r["n"], "usd": round(float(r["usd"] or 0), 6)} for r in rows}


def health_of(root: str | Path) -> dict[str, Any] | None:
    health = read_json(Path(root) / "health.json", None)
    if not isinstance(health, dict):
        return None
    out = {k: health.get(k) for k in HEALTH_KEYS}
    live = health.get("options_live") if isinstance(health.get("options_live"), dict) else {}
    out["options_live"] = {"state": (live.get("summary") or {}).get("state") if isinstance(live.get("summary"), dict) else None,
                           "blocked": live.get("blocked"), "frozen": live.get("frozen"),
                           "instances": len(live.get("instances") or {})}
    return out


def build(root: str | Path, base: str | Path, now: float, *, day: str | None = None) -> dict[str, Any]:
    root, base = Path(root), Path(base)
    day = day or S.iso(now)[:10]
    start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    runs = summaries(read_runs(root, S.iso(start.timestamp()), S.iso(end.timestamp())))
    by_status: dict[str, int] = {}
    for row in runs:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    return {"schema": SCHEMA, "day": day, "written_at": S.iso(now),
            "jobs": runs, "jobs_by_status": by_status,
            "health": health_of(root),
            "deploys": deploys_of(base, day),
            "spend": spend_of(root, start.timestamp(), min(end.timestamp(), now)),
            "budget": read_json(root / "budget.json", None),
            "economics": latest_economics(root)}


def latest_economics(root: str | Path) -> dict[str, Any] | None:
    """Where the newest close economics is, and its headline (private)."""
    folder = Path(root) / "economics"
    try:
        dirs = sorted(p for p in folder.iterdir() if p.is_dir() and p.name.endswith("-close"))
    except OSError:
        return None
    for path in reversed(dirs):
        summary = read_json(path / "summary.json", None)
        if isinstance(summary, dict):
            net = summary.get("net") or {}
            return {"dir": str(path), "cutoff": summary.get("cutoff"), "net_usd": net.get("net_usd"),
                    "realized_options_pnl_usd": (summary.get("realized") or {}).get("realized_options_pnl_usd"),
                    "total_costs_usd": summary.get("total_costs_usd"), "p30": summary.get("p30")}
    return None


def write(root: str | Path, base: str | Path, now: float) -> str:
    """Write the day's file and `latest.json` (the same content). The day's path."""
    value = build(root, base, now)
    folder = Path(root) / "receipts"
    path = write_json(folder / f"{value['day']}.json", value)
    write_json(folder / "latest.json", value)
    return str(path)
