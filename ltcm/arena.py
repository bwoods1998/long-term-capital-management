"""Factual execution telemetry: distinguish live fills, paused entries and shadow research."""
from collections import Counter
from datetime import datetime, timedelta


def execution_pulse(log, manifests, store, at):
    cutoff = (datetime.fromisoformat(at.replace("Z", "+00:00")) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    venues = {v: {"fills": 0, "sells": 0, "live_enabled": 0, "live_paused": 0, "shadow_enabled": 0, "last_fill_at": None} for v in ("kalshi", "coinbase")}
    for event in log.read(kind="broker.fill", limit=10000, newest=True):
        p = event.payload
        venue = (p.get("instrument") or {}).get("venue")
        if venue not in venues or p.get("shadow") or getattr(event, "stream", "") == "broker:shadow" or event.at < cutoff or p.get("repair") or str(p.get("fill_id", "")).startswith("repair:"):
            continue
        row = venues[venue]
        row["fills"] += 1
        row["sells"] += int(p.get("side") == "sell")
        row["last_fill_at"] = max(row["last_fill_at"] or event.at, event.at)
    for desk in manifests.values():
        if desk.market_venue not in venues:
            continue
        row = venues[desk.market_venue]
        for strategy in store.for_desk(desk.id).values():
            enabled = strategy.get("enabled", True)
            key = ("live_enabled" if enabled else "live_paused") if desk.live else "shadow_enabled"
            if desk.live or enabled:
                row[key] += 1
    blockers = {v: Counter() for v in venues}
    for event in log.read(kind="risk.decision", limit=5000, newest=True):
        p = event.payload
        desk = manifests.get(p.get("desk_id"))
        if event.at < cutoff or p.get("approved") or desk is None or not desk.live or desk.market_venue not in blockers:
            continue
        for reason in p.get("reasons") or []:
            blockers[desk.market_venue][str(reason)[:180]] += 1
    for venue, row in venues.items():
        row["blockers"] = [{"reason": reason, "count": count} for reason, count in blockers[venue].most_common(3)]
    message = "Past hour · " + " · ".join(f"{venue.title()}: {row['fills']} real fills ({row['sells']} sells), {row['live_enabled']} live strategies enabled, {row['live_paused']} paused, {row['shadow_enabled']} shadow strategies testing" for venue, row in venues.items())
    return {"component": "execution", "stage": "heartbeat", "message": message, "venues": venues, "window_hours": 1}
