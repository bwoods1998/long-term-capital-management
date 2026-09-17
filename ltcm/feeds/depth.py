"""Bounded, snapshot-first Coinbase L2 state. Quantities are replacements, not deltas."""
from decimal import Decimal, InvalidOperation
from heapq import nlargest, nsmallest


class DepthBook:
    def __init__(self, max_levels=50000):
        self.bids, self.asks = {}, {}
        self.ready = False
        self.max_levels = max_levels

    def apply(self, event):
        snapshot = event.get("type") == "snapshot"
        if not snapshot and not self.ready:
            raise ValueError("depth update before snapshot")
        bids, asks = ({}, {}) if snapshot else (self.bids, self.asks)
        for row in event.get("updates") or []:
            try:
                price, size = Decimal(str(row["price_level"])), Decimal(str(row["new_quantity"]))
                side = row["side"]
                if not price.is_finite() or not size.is_finite() or price <= 0 or size < 0 or side not in ("bid", "offer"):
                    raise ValueError("invalid depth level")
            except (KeyError, InvalidOperation, TypeError) as exc:
                raise ValueError("invalid depth level") from exc
            levels = bids if side == "bid" else asks
            if size == 0:
                levels.pop(price, None)
            else:
                levels[price] = size
            if len(bids) + len(asks) > self.max_levels:
                raise ValueError("depth level bound exceeded")
        self.bids, self.asks, self.ready = bids, asks, True

    def summary(self, levels=10):
        bids, asks = nlargest(levels, self.bids), nsmallest(levels, self.asks)
        if not self.ready or not bids or not asks or bids[0] >= asks[0]:
            return None
        bid_value = sum((p * self.bids[p] for p in bids), Decimal(0))
        ask_value = sum((p * self.asks[p] for p in asks), Decimal(0))
        total = bid_value + ask_value
        mid = (bids[0] + asks[0]) / 2
        return {"bid": str(bids[0]), "ask": str(asks[0]),
                "spread_bps": str((asks[0] - bids[0]) / mid * 10000),
                "bid_depth_usd": str(bid_value), "ask_depth_usd": str(ask_value),
                "imbalance": str((bid_value - ask_value) / total) if total else "0",
                "levels": levels, "source": "coinbase:level2",
                "bids": [[str(p), str(self.bids[p])] for p in bids],
                "asks": [[str(p), str(self.asks[p])] for p in asks]}
