"""Cross-agent exposure groups: which open bets are really the same bet. Report only.

Every agent sizes against its own limits, and the risk engine checks each book, but nothing
showed that four agents on different desks can all be long the same WTI settlement, or that a
Kalshi BTC-range desk and an Alpaca crypto desk both lose on the same move. This module groups
open holdings across agents:

1. **Exact identifiers first**: the Kalshi event ticker (market id minus its strike segment), the
   Kalshi series (the prefix before the first dash) and, for Alpaca, the underlying (an option's
   root symbol, a crypto pair's base asset).
2. **Jev only for related-but-not-identical contracts**: two different series, or a Kalshi series
   and an Alpaca underlying, asked "do these depend on the same underlying asset or event?"
   Cached by the pair, so each pair is bought once.

It is published in health.json as `jev.exposure`. It makes no decision: the deterministic risk
layer keeps every sizing, refusal and exit decision.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Callable, Mapping

from .jev import sha

RELATED = ("Do the item and the reference contract in state depend on the same underlying asset, price or real-world "
           "event, so that one move or outcome would move both? Identical tickers are not required.")
DEFAULTS: dict[str, Any] = {"enabled": True, "interval_seconds": 1800, "related_threshold": 0.7, "max_questions_per_run": 32}


def keys_of(instrument: Any) -> dict[str, str]:
    """Exact grouping identifiers for one instrument."""
    venue = str(getattr(instrument, "venue", "") or "")
    market = str(getattr(instrument, "market_id", "") or getattr(instrument, "symbol", "") or "")
    if venue.startswith("kalshi"):
        parts = market.split("-")
        return {"event": "-".join(parts[:-1]) if len(parts) > 2 else market, "series": parts[0]}
    symbol = str(getattr(instrument, "symbol", "") or market)
    base = symbol.replace("/", "-").split("-")[0]
    return {"underlying": base}


class Exposure:
    def __init__(self, house: Any, sensor: Any = None, *, clock: Callable[[], float] = time.time,
                 settings: Mapping[str, Any] | None = None):
        self.house, self.sensor, self.clock = house, sensor, clock
        self.settings = {**DEFAULTS, **dict(settings or {})}
        self.last_run = 0.0
        self.latest: dict[str, Any] | None = None

    def due(self) -> bool:
        return bool(self.settings.get("enabled", True)) and self.clock() - self.last_run >= float(self.settings["interval_seconds"])

    def holdings(self) -> list[dict[str, Any]]:
        rows = []
        for name, book in dict(self.house.books).items():
            lock = getattr(book, "_lock", None)
            with lock if lock is not None else _Null():
                accounts = {agent: list(account.holdings.values()) for agent, account in book.accounts.items()}
            for agent, holdings in accounts.items():
                if agent == "house":
                    continue
                for h in holdings:
                    if h.quantity == 0:
                        continue
                    rows.append({"book": name, "agent": agent, "real_money": bool(book.real_money),
                                 "instrument": h.instrument, "cost": Decimal(str(h.cost)), **keys_of(h.instrument)})
        return rows

    def run(self) -> dict[str, Any]:
        self.last_run = self.clock()
        rows = self.holdings()
        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            for level in ("event", "series", "underlying"):
                if row.get(level):
                    group = groups.setdefault(f"{level}:{row[level]}", {"level": level, "agents": set(), "books": set(), "cost_usd": Decimal(0), "positions": 0})
                    group["agents"].add(row["agent"])
                    group["books"].add(row["book"])
                    group["cost_usd"] += abs(row["cost"])
                    group["positions"] += 1
        related = self._related(groups)
        shared = {k: g for k, g in groups.items() if len(g["agents"]) >= 2}
        report = {"at": self.clock(), "positions": len(rows),
                  "shared_groups": sorted(({"key": k, "level": g["level"], "agents": sorted(g["agents"]), "books": sorted(g["books"]),
                                            "positions": g["positions"], "cost_usd": format(g["cost_usd"], "f")}
                                           for k, g in shared.items()), key=lambda r: (-len(r["agents"]), r["key"]))[:30],
                  "related": related,
                  "max_agents_on_one_event": max((len(g["agents"]) for g in groups.values() if g["level"] == "event"), default=0),
                  "authority": "report only: the deterministic risk layer decides sizing, refusals and exits"}
        self.latest = report
        return report

    def _related(self, groups: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Jev on distinct series/underlyings held by DIFFERENT agents, pairwise, capped and cached."""
        if self.sensor is None:
            return []
        tops = [(k, g) for k, g in groups.items() if g["level"] in ("series", "underlying")]
        pairs = [(a, b) for i, (a, ga) in enumerate(tops) for b, gb in tops[i + 1:] if ga["agents"] != gb["agents"] or len(ga["agents"]) > 1]
        pairs = pairs[:int(self.settings["max_questions_per_run"])]
        out = []
        by_ref: dict[str, list[str]] = {}
        for a, b in pairs:
            by_ref.setdefault(a, []).append(b)
        for ref, others in by_ref.items():
            items = {"exposure:" + sha(sorted((ref, other))): (other.split(":", 1)[1], RELATED) for other in others}
            answers = self.sensor.ask("exposure", {"reference_contract": ref.split(":", 1)[1],
                                                   "note": "Kalshi tickers: series-event-strike; Alpaca: the traded symbol."}, items)
            for other, key in zip(others, items):
                p = answers.get(key)
                if p is not None and p >= float(self.settings["related_threshold"]):
                    agents = sorted(groups[ref]["agents"] | groups[other]["agents"])
                    out.append({"a": ref, "b": other, "p": round(p, 3), "agents": agents, "method": "jev"})
        return out


class _Null:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False
