"""Owner-controlled options money rules. Every live order uses this table.

The gateway repeats the listed absolute caps. A change of these rules invalidates the owner's
live grant until it is ratified again. Per-family compute budgets live in swarm/settings.py.
"""
from __future__ import annotations
import hashlib
import json
from typing import Any

CONSTITUTION: dict[str, Any] = {'version': 2,
 'options_money': {'real_types': ['debit_vertical',
                                  'credit_vertical',
                                  'iron_condor',
                                  'iron_butterfly',
                                  'long_butterfly'],
                   'credit_types': ['credit_vertical', 'iron_condor', 'iron_butterfly'],
                   'credit_min_equity_usd': '2000',
                   'probe': {'max_loss_share': '0.03',
                             'open_per_family': 3,
                             'family_share': '0.12',
                             'floor_usd': '60'},
                   'sized': {'min_trades': 20,
                             'confidence': '0.80',
                             'kelly_fraction': '0.25',
                             'max_loss_share': '0.10',
                             'family_share': '0.30',
                             'min_probe_real_trades': 5,
                             'min_probe_sessions': 1},
                   'book_share': '0.70',
                   'daily_stop_share': '0.25',
                   'drawdown_stop_share': '0.50',
                   'tuition': {'day_usd': '100', 'week_usd': '300'},
                   'order_path': {'max_orders_day': 250,
                                  'max_requests_minute': 150,
                                  'bp_buffer': '0.10',
                                  'near_money_share': '0.01',
                                  'expiry_close_lead_minutes': 10},
                   'gateway': {'order_max_loss_usd': '1000',
                               'order_equity_share': '0.15',
                               'day_equity_share': '1.0',
                               'max_day_orders': 300,
                               'max_day_open_orders': 250}}}

def digest(constitution: dict[str, Any] | None = None) -> str:
    """The SHA-256 of the constitution's canonical JSON."""
    text = json.dumps(constitution or CONSTITUTION, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: The schema version is metadata; every options money rule participates in the grant digest.
RISK_FREE = (("version",),)


def money_digest(constitution: dict[str, Any] | None = None) -> str:
    """The SHA-256 of the rules that govern real money. The owner's live-trading grant pins this,
    not `digest()`: changing schema metadata alone does not revoke authorization; changing a money rule does."""
    import copy

    rules = copy.deepcopy(constitution or CONSTITUTION)
    for path in RISK_FREE:
        node = rules
        for key in path[:-1]:
            node = node.get(key, {})
        node.pop(path[-1], None)
    return digest(rules)



#: The allowed range of every tunable row of `options_money` this run (the plan's "Money" table, Sept 26, 2026), and the
#: rows that are not tunable at all: `(low, high)` inclusive. Loosening a row past its range is the owner's decision,
#: in this file. `league.ci` refuses a constitution outside them (`options_money_problems`).
OPTIONS_MONEY_BOUNDS: dict[str, tuple[str, str]] = {
    "probe.max_loss_share": ("0.02", "0.05"),
    "probe.open_per_family": ("1", "5"),
    "probe.family_share": ("0.08", "0.15"),
    "probe.floor_usd": ("0", "100"),
    "sized.min_trades": ("20", "1000"),
    "sized.confidence": ("0.80", "0.99"),
    "sized.kelly_fraction": ("0.125", "0.5"),
    "sized.max_loss_share": ("0.05", "0.15"),
    "sized.family_share": ("0.20", "0.40"),
    # The Probe is a real stage (the review of #362, C2): Sized only after this many real Probe trades on the current
    # program version and this many whole sessions at Probe. A tightening of the plan's row; loosening is the owner's.
    "sized.min_probe_real_trades": ("5", "50"),
    "sized.min_probe_sessions": ("1", "20"),
    "book_share": ("0.50", "0.90"),
    "daily_stop_share": ("0.15", "0.35"),
    "drawdown_stop_share": ("0.40", "0.60"),
    "tuition.day_usd": ("0", "200"),
    "tuition.week_usd": ("0", "600"),
    "credit_min_equity_usd": ("2000", "2000"),
    "order_path.max_orders_day": ("1", "250"),
    "order_path.max_requests_minute": ("1", "150"),
    "order_path.bp_buffer": ("0.10", "0.50"),
    "order_path.near_money_share": ("0", "0.05"),
    "order_path.expiry_close_lead_minutes": ("1", "30"),
    "gateway.order_max_loss_usd": ("0", "1000"),
    "gateway.order_equity_share": ("0", "0.15"),
    "gateway.day_equity_share": ("0", "1.0"),
    "gateway.max_day_orders": ("1", "300"),
    "gateway.max_day_open_orders": ("1", "300"),
}
#: The five types the venue closes in one order: the only ones real money may open this run.
OPTIONS_REAL_TYPES = ("debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly", "long_butterfly")
OPTIONS_CREDIT_TYPES = ("credit_vertical", "iron_condor", "iron_butterfly")
#: Rows read as whole counts.
_OPTIONS_COUNTS = ("probe.open_per_family", "sized.min_trades", "sized.min_probe_real_trades", "sized.min_probe_sessions", "order_path.max_orders_day", "order_path.max_requests_minute",
                   "order_path.expiry_close_lead_minutes", "gateway.max_day_orders", "gateway.max_day_open_orders")


def options_money_problems(constitution: dict[str, Any] | None = None) -> list[str]:
    """Why the constitution's options money table is outside its bounds (`OPTIONS_MONEY_BOUNDS`), or [] when every row
    is inside them. A missing table is a problem: the live path trades nothing without it."""
    from decimal import Decimal, InvalidOperation

    table = (constitution or CONSTITUTION).get("options_money")
    if not isinstance(table, dict):
        return ["options_money: the table is missing"]
    problems = []
    for path, (low, high) in OPTIONS_MONEY_BOUNDS.items():
        node: Any = table
        for key in path.split("."):
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, bool) or node is None:
            problems.append(f"options_money.{path} is missing")
            continue
        try:
            value = Decimal(str(node))
        except (InvalidOperation, ValueError):
            problems.append(f"options_money.{path} = {node!r} is not a number")
            continue
        if not value.is_finite() or not Decimal(low) <= value <= Decimal(high):
            problems.append(f"options_money.{path} = {node!r} is outside [{low}, {high}]")
        elif path in _OPTIONS_COUNTS and (value != value.to_integral_value() or isinstance(node, float)):
            problems.append(f"options_money.{path} = {node!r} is not a whole count")
    real = table.get("real_types")
    if not isinstance(real, list) or not real or len(set(real)) != len(real) or any(t not in OPTIONS_REAL_TYPES for t in real):
        problems.append(f"options_money.real_types lists distinct types among {list(OPTIONS_REAL_TYPES)} (another type needs a "
                        f"paper round trip and the owner): {real!r}")
    if table.get("credit_types") != list(OPTIONS_CREDIT_TYPES):
        problems.append(f"options_money.credit_types is exactly {list(OPTIONS_CREDIT_TYPES)}")
    gate = table.get("gateway") if isinstance(table.get("gateway"), dict) else {}
    try:
        if int(gate.get("max_day_open_orders", 0)) >= int(gate.get("max_day_orders", 0)):
            problems.append("options_money.gateway.max_day_open_orders must leave exits room under max_day_orders")
    except (TypeError, ValueError):
        pass
    return problems

#: The gateway's `wrangler.jsonc` vars that repeat the money table: `league.ci` requires them equal.
GATEWAY_VARS = {
    "MAX_ORDER_MAX_LOSS_USD": "gateway.order_max_loss_usd",
    "MAX_ORDER_EQUITY_SHARE": "gateway.order_equity_share",
    "MAX_DAY_EQUITY_SHARE": "gateway.day_equity_share",
    "MAX_DAY_ORDERS": "gateway.max_day_orders",
    "MAX_DAY_OPEN_ORDERS": "gateway.max_day_open_orders",
    "CREDIT_MIN_EQUITY_USD": "credit_min_equity_usd",
}


PINNED_DIGEST = 'dc5639dc74fd56858e18a1817a4d3ad6249561d38ab59a5cbd9837c0402926e8'
