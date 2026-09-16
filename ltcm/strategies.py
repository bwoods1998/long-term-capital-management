"""Strategies: code a desk deploys to trade for it between sessions (leap: strategies).

A model session is slow, expensive and cautious: on the floor's first day 49 sessions produced
three orders. A strategy is the desk's judgement written down as code and run by the floor
every few minutes in the desk's own sandbox, so the decisions a recursive loop needs arrive by
the hundred at the price of a few sandbox seconds, and the desk's sessions become what they
should be: building, measuring and improving the code that trades.

The contract a strategy honours, in `toolbox/<name>.py`:

    def decide(kit, params) -> list[dict]:
        ...

`kit` reads public data (`kit.bars`, `kit.quote`, `kit.kalshi_series`, `kit.kalshi_market`) and
carries `kit.context` (the clock, the desk's positions, its learning size). Each dict returned is
a `propose_order` call: `instrument`, `side`, `quantity`, `order_type` (limit only),
`limit_price`, `rationale`, and optionally `target_price`, `stop_price`,
`holding_period_hours`. The floor proposes them exactly as the desk would in a session -- the
same risk engine, the same critic for a live desk, the same public events -- under a session
id of the form `<desk>:<stamp>:strategy:<name>`, so every strategy decision is attributable.

What the floor guarantees:

* A run is a public `desk.code_run` (purpose `strategy <name>`), so the code's own printout is
  on the tape next to the orders it produced. Idle runs are published once an hour per
  strategy; runs that propose or fail are always published.
* A live desk's strategy orders are capped at the learning size until the desk itself raises
  the strategy's `notional_usd` after reading its record; shadow desks run at learning size
  by default and may size up in `params`.
* At most `max_intents_per_run` intents a run, `max_per_desk` strategies a desk,
  `min_cadence_seconds` between runs, and the sandbox's daily fuse on top. A strategy that
  raises is not stopped; its error is on the tape and its next run is one cadence later.

Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping

from .events import now_iso
from .manifest import DeskManifest

NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "max_per_desk": 3,
    "min_cadence_seconds": 300,
    "max_cadence_seconds": 86_400,
    "max_intents_per_run": 5,
    "max_runs_per_tick": 2,
    "run_timeout_seconds": 90,
    "idle_publish_seconds": 3600,
    "starters": True,
    # A live strategy's orders stay at learning size until this many of its positions have
    # settled with a positive P&L after fees; then it may size to this multiple of learning size.
    "earned_settled": 20,
    "earned_multiple": 3,
}
STARTERS_DIR = Path(__file__).resolve().parent / "starters"
#: Family -> starter module name. A desk of the family with no strategy of its own gets the
#: house starter deployed under this name, exactly as a bred desk gets the house playbook.
STARTERS = {"ranges": "hourly_ranges", "crypto": "hourly_reversion", "weather": "daily_temps"}
#: A second house strategy for a family: the ranges family also quotes the hourly buckets on
#: both legs at a spread, the maker side of the same market its starter takes.
SECOND_STARTERS = {"ranges": "hourly_quotes"}
#: A shadow desk's starter explores, and each shadow desk of a family explores differently:
#: the variants are dealt round-robin by the desk's id, so the family's record compares
#: settings on the same markets at the same hours. The live desk keeps the code's defaults.
STARTER_VARIANTS: dict[str, list[dict[str, Any]]] = {
    "ranges": [
        # The experiment is the volatility window: five-minute, fifteen-minute and hourly bars.
        {"min_edge": 0.0, "shrink": 0.5, "vol_interval": "5m", "vol_bars": 36},
        {"min_edge": 0.01, "shrink": 0.5, "vol_interval": "15m", "vol_bars": 32},
        {"min_edge": 0.02, "shrink": 0.7, "vol_interval": "1h", "vol_bars": 24},
    ],
    "crypto": [
        {"z_entry": 1.5},
        {"z_entry": 2.0, "lookback": 48},
        {"z_entry": 1.25, "lookback": 12, "holding_hours": 6},
    ],
    "weather": [
        {"min_edge": 0.0},
        {"min_edge": 0.0, "sigma_day_ahead": 3.5},
        {"min_edge": 0.01, "sigma_day_ahead": 2.0},
    ],
}
QUOTE_VARIANTS: list[dict[str, Any]] = [
    {"spread": 0.04, "buckets": 2},
    {"spread": 0.06, "buckets": 2},
    {"spread": 0.03, "buckets": 3},
]
#: How often a house starter runs. Hourly markets reprice by the minute; spot reverts slower;
#: a day's temperature forecast moves a few times a day.
STARTER_CADENCE = {"ranges": 300, "crypto": 600, "weather": 1800, "hourly_quotes": 300}


def starter_params(family: str, manifest: DeskManifest, *, quotes: bool = False) -> dict[str, Any]:
    """The house params for one desk: the code's defaults for a live desk, a dealt variant for
    a shadow desk. The deal is stable per desk id, so a restart changes nothing."""
    if manifest.live:
        return {"buckets": 1} if quotes else {}
    variants = QUOTE_VARIANTS if quotes else STARTER_VARIANTS.get(family) or [{}]
    index = sum(ord(ch) for ch in manifest.id) % len(variants)
    return dict(variants[index])

#: Uploaded as `/lab/run/main.py` for every strategy run. It builds the kit, imports the
#: strategy from the toolbox, calls `decide`, and prints one JSON line the floor reads back.
RUNNER = r'''
import json, math, sys, traceback
sys.path.insert(0, "/lab")
sys.path.insert(0, "/lab/floor")
PARAMS = json.loads(%(params)s)
CONTEXT = json.loads(%(context)s)

class Kit:
    """What a strategy may read. Public data only; nothing here can trade."""
    def __init__(self):
        import labkit
        self._lab = labkit
        self.context = CONTEXT
        self.log = []
    def say(self, text):
        self.log.append(str(text)[:300])
    def bars(self, symbol, interval="1h", limit=60, asset_class="crypto", venue="coinbase"):
        return self._lab.bars(symbol, interval, limit, asset_class, venue)
    def quote(self, symbol, asset_class="crypto", venue="coinbase"):
        return self._lab.quote(symbol, asset_class, venue)
    def _event_source(self):
        # labkit's own kalshi helpers look for a public `source` that the composite never had;
        # the route is `_source`. Try both so a rebuilt image keeps working.
        data = getattr(self._lab, "_data", None)
        for attr in ("_source", "source"):
            getter = getattr(data, attr, None)
            if callable(getter):
                try:
                    return getter("event")
                except Exception:
                    return None
        return None
    def kalshi_market(self, ticker):
        src = self._event_source()
        return src.market(ticker) if src is not None else None
    def weather(self, city):
        """The NWS forecast for a Kalshi weather city: days (date, day_high, hourly_max), the
        settlement station and the latest observation."""
        from ltcm.data import HttpTransport
        from ltcm.data.weather import Weather
        return Weather(transport=HttpTransport(cache_dir="/lab/cache", ttl=600.0, min_interval=0.2)).forecast(city)
    def weather_cities(self):
        from ltcm.data.weather import CITIES
        return [
            {"name": c.name, "series": getattr(c, "series_hint", None) or getattr(c, "hint", None), "station": c.station}
            for c in CITIES.values()
        ]
    def kalshi_series(self, series, limit=1000, status="open"):
        """Open markets of one series (KXBTC, KXETH, KXHIGHNY...), prices in dollars. An hourly
        series lists dozens of buckets for several hours at once, so ask for them all."""
        src = self._event_source()
        if src is None:
            return []
        page = src.markets(series_ticker=series, status=status, limit=limit)
        rows = page.get("markets", []) if isinstance(page, dict) else []
        out = []
        for row in rows:
            try:
                out.append(src.parse_market(row))
            except Exception:
                continue
        return out

def _plain(value):
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)

kit = Kit()
result = {"intents": [], "notes": "", "log": kit.log}
try:
    from toolbox import %(name)s as strategy
    out = strategy.decide(kit, PARAMS)
    if isinstance(out, dict):
        result["intents"] = list(out.get("intents") or [])
        result["notes"] = str(out.get("notes") or "")[:600]
        result["cancels"] = [str(c) for c in (out.get("cancels") or []) if isinstance(c, str)][:20]
    elif isinstance(out, (list, tuple)):
        result["intents"] = list(out)
    elif out is not None:
        result["notes"] = str(out)[:600]
    result["intents"] = [_plain(i) for i in result["intents"] if isinstance(i, dict)][:%(max_intents)d]
    for intent in result["intents"]:
        if "rationale" in intent:
            intent["rationale"] = str(intent["rationale"])[:400]
except Exception:
    result["error"] = traceback.format_exc()[-1200:]
result["log"] = kit.log[-12:]
line = json.dumps(result, default=str, separators=(",", ":"))
if len(line) > 3600:
    result["log"] = result["log"][-3:]
    for intent in result["intents"]:
        intent["rationale"] = str(intent.get("rationale") or "")[:160]
    line = json.dumps(result, default=str, separators=(",", ":"))[:3600]
print("STRATEGY-RESULT " + line)
'''


def _dec(value: Any) -> Decimal | None:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() else None


class StrategyStore:
    """`.data/ltcm/strategies.json`: what is deployed, and each strategy's running counters."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def read(self) -> dict[str, dict[str, dict[str, Any]]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        desks = data.get("desks") if isinstance(data, dict) else None
        return desks if isinstance(desks, dict) else {}

    def write(self, desks: Mapping[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + f".tmp-{os.getpid()}")
            tmp.write_text(json.dumps({"schema_version": 1, "desks": desks}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp.chmod(0o600)
            tmp.replace(self.path)

    def for_desk(self, desk_id: str) -> dict[str, dict[str, Any]]:
        return dict(self.read().get(desk_id) or {})

    def update(self, desk_id: str, name: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            desks = self.read()
            row = dict((desks.get(desk_id) or {}).get(name) or {})
            row.update(fields)
            desks.setdefault(desk_id, {})[name] = row
            self.write(desks)
            return row

    def remove(self, desk_id: str, name: str) -> bool:
        with self._lock:
            desks = self.read()
            if name not in (desks.get(desk_id) or {}):
                return False
            del desks[desk_id][name]
            if not desks[desk_id]:
                del desks[desk_id]
            self.write(desks)
            return True


class Strategies:
    """The runner. Owned by the service; `tick(at)` runs what is due."""

    def __init__(
        self,
        service: Any,
        *,
        path: str | Path,
        config: Mapping[str, Any] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.service = service
        self.config = {**DEFAULTS, **dict(config or {})}
        self.store = StrategyStore(path)
        self.clock = clock
        self._bootstrapped = False

    # ------------------------------------------------------------------ helpers
    def sandboxes(self) -> Any:
        return getattr(self.service, "sandboxes", None)

    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True)) and self.sandboxes() is not None

    def learning_usd(self, manifest: DeskManifest) -> Decimal:
        policy = dict(getattr(self.service, "config", {}).get("learning") or {})
        if manifest.live:
            venue = manifest.venues[0] if manifest.venues else "kalshi"
            key = "live_coinbase_usd" if venue == "coinbase" else "live_kalshi_usd"
            return _dec(policy.get(key)) or Decimal("10")
        return _dec(policy.get("shadow_notional_usd")) or Decimal("15")

    def context_for(self, manifest: DeskManifest, at: str) -> dict[str, Any]:
        positions: list[dict[str, Any]] = []
        try:
            ctx = self.service.context(manifest)
            for position in ctx.positions():
                inst = getattr(position, "instrument", None)
                positions.append(
                    {
                        "symbol": getattr(inst, "symbol", None),
                        "market_id": getattr(inst, "market_id", None),
                        "right": getattr(inst, "right", None),
                        "asset_class": getattr(inst, "asset_class", None),
                        "quantity": str(getattr(position, "quantity", "")),
                        "average_cost": str(getattr(position, "average_cost", "") or ""),
                    }
                )
        except Exception:
            positions = []
        return {
            "now": at,
            "desk_id": manifest.id,
            "live": bool(manifest.live),
            "learning_usd": str(self.learning_usd(manifest)),
            "positions": positions,
            "open_orders": self.open_orders_for(manifest),
            "venues": list(manifest.venues),
        }

    def open_orders_for(self, manifest: DeskManifest) -> list[dict[str, Any]]:
        """The desk's resting orders, as a strategy sees them: enough to cancel and replace."""
        gateway = getattr(self.service, "gateway", None)
        getter = getattr(gateway, "open_orders", None)
        if not callable(getter):
            return []
        out: list[dict[str, Any]] = []
        try:
            rows = getter(manifest.id)
        except Exception:
            return []
        if not rows:
            return []
        # An order row carries its intent id; the intent event carries the session id that
        # names the strategy. One read of the desk's intents serves every row.
        sessions: dict[str, str] = {}
        reader = getattr(getattr(self.service, "log", None), "read", None)
        if callable(reader):
            try:
                for event in reader(stream=manifest.stream, kind="desk.intent", limit=10_000):
                    sessions[str(event.payload.get("intent_id"))] = str(event.payload.get("session_id") or "")
            except Exception:
                sessions = {}
        for row in rows[:200]:
            inst = row.get("instrument") if isinstance(row, Mapping) else None
            inst = inst if isinstance(inst, Mapping) else {}
            out.append(
                {
                    "order_id": row.get("order_id"),
                    "intent_id": row.get("intent_id"),
                    "market_id": inst.get("market_id"),
                    "symbol": inst.get("symbol"),
                    "right": inst.get("right"),
                    "side": row.get("side"),
                    "quantity": str(row.get("quantity") or ""),
                    "limit_price": str(row.get("limit_price") or ""),
                    "submitted_at": row.get("submitted_at"),
                    "status": row.get("status"),
                    "strategy": _strategy_of(sessions.get(str(row.get("intent_id")), "") or str(row.get("session_id") or "")),
                }
            )
        return out

    # ------------------------------------------------------------------ deployment
    def deploy(self, manifest: DeskManifest, name: str, cadence_seconds: int, params: Mapping[str, Any] | None, *, note: str = "", house: bool = False) -> dict[str, Any]:
        """Register a toolbox module as a strategy after one dry run. Raises ValueError on refusal."""
        if not isinstance(name, str) or not NAME.match(name):
            raise ValueError("a strategy name is lowercase letters, digits and underscores, 40 at most")
        manager = self.sandboxes()
        if manager is None:
            raise ValueError("no sandbox is available on this floor")
        low, high = int(self.config["min_cadence_seconds"]), int(self.config["max_cadence_seconds"])
        try:
            cadence = int(cadence_seconds)
        except (TypeError, ValueError):
            raise ValueError(f"cadence_seconds must be an integer between {low} and {high}") from None
        if not low <= cadence <= high:
            raise ValueError(f"cadence_seconds must be between {low} and {high}")
        existing = self.store.for_desk(manifest.id)
        if name not in existing and len(existing) >= int(self.config["max_per_desk"]):
            raise ValueError(f"a desk may run at most {self.config['max_per_desk']} strategies; undeploy one first")
        files = manager.toolbox_files(manifest.id) if hasattr(manager, "toolbox_files") else {}
        if f"{name}.py" not in files:
            raise ValueError(f"toolbox/{name}.py does not exist: save it first with run_code(save_as='{name}')")
        code = files[f"{name}.py"]
        if "def decide(" not in code:
            raise ValueError("the module must define decide(kit, params)")
        clean_params = _plain_params(params)
        at = self.service.now()
        run = self._execute(manifest, name, clean_params, at, dry=True)
        if run.get("error"):
            raise ValueError(f"the dry run failed: {str(run['error'])[-400:]}")
        if not isinstance(run.get("intents"), list):
            raise ValueError("decide() must return a list of intents (it may be empty)")
        row = self.store.update(
            manifest.id,
            name,
            cadence_seconds=cadence,
            params=clean_params,
            deployed_at=at,
            note=str(note or "")[:200],
            house=bool(house),
            enabled=True,
            code_sha256=_sha(code),
            last_run_at=None,
            runs=int(existing.get(name, {}).get("runs") or 0),
            intents=int(existing.get(name, {}).get("intents") or 0),
            approved=int(existing.get(name, {}).get("approved") or 0),
            errors=int(existing.get(name, {}).get("errors") or 0),
            last_error=None,
        )
        self._publish_run(manifest, name, run, at, f"strategy {name} deployed every {cadence}s" + (" (house starter)" if house else ""), always=True)
        return self.describe(manifest.id, name, row)

    def undeploy(self, manifest: DeskManifest, name: str) -> dict[str, Any]:
        if not self.store.remove(manifest.id, name):
            raise ValueError(f"no strategy named {name!r} is deployed")
        return {"undeployed": name}

    def report(self, manifest: DeskManifest, name: str | None = None) -> dict[str, Any]:
        rows = self.store.for_desk(manifest.id)
        if name:
            if name not in rows:
                raise ValueError(f"no strategy named {name!r} is deployed")
            return self.describe(manifest.id, name, rows[name])
        return {"strategies": [self.describe(manifest.id, n, r) for n, r in sorted(rows.items())], "max_per_desk": self.config["max_per_desk"]}

    def describe(self, desk_id: str, name: str, row: Mapping[str, Any]) -> dict[str, Any]:
        keys = ("cadence_seconds", "params", "deployed_at", "note", "house", "enabled", "last_run_at", "runs", "intents", "approved", "errors", "last_error", "last_notes")
        return {"name": name, "desk_id": desk_id, **{k: row.get(k) for k in keys}, **self.record(desk_id, name)}

    def record(self, desk_id: str, name: str) -> dict[str, Any]:
        """What the strategy's orders did: fills, fees and the settled P&L of the positions it
        opened, read from the desk's own tape (the `[strategy <name>]` prefix on its rationales)."""
        log = getattr(self.service, "log", None)
        reader = getattr(log, "read", None)
        if not callable(reader):
            return {}
        stream = f"desk:{desk_id}"
        prefix = f"[strategy {name}]"
        try:
            intents = {
                e.payload.get("intent_id")
                for e in reader(stream=stream, kind="desk.intent", limit=10_000)
                if _strategy_of(str(e.payload.get("session_id") or "")) == name
            }
            orders = {
                e.payload.get("order_id")
                for e in reader(stream=f"broker:{desk_id}", kind="broker.order", limit=10_000)
                if e.payload.get("intent_id") in intents
            }
            fills = [e for e in reader(stream=f"broker:{desk_id}", kind="broker.fill", limit=10_000) if e.payload.get("order_id") in orders]
            outcomes = [
                e for e in reader(stream=stream, kind="desk.outcome", limit=10_000)
                if str(e.payload.get("rationale_excerpt") or "").startswith(prefix)
            ]
        except Exception:
            return {}
        notional = sum((_dec(f.payload.get("price")) or Decimal(0)) * (_dec(f.payload.get("quantity")) or Decimal(0)) for f in fills)
        fees = sum(_dec(f.payload.get("fee") or f.payload.get("fees")) or Decimal(0) for f in fills)
        pnl = sum(_dec(o.payload.get("pnl")) or Decimal(0) for o in outcomes)
        wins = sum(1 for o in outcomes if (_dec(o.payload.get("pnl")) or Decimal(0)) > 0)
        return {
            "fills": len(fills),
            "filled_notional_usd": format(notional, "f"),
            "fees_usd": format(fees, "f"),
            "settled": len(outcomes),
            "wins": wins,
            "settled_pnl_usd": format(pnl, "f"),
        }

    # ------------------------------------------------------------------ the tick
    def bootstrap(self, manifests: Mapping[str, DeskManifest]) -> list[str]:
        """Give every desk of a family with a house starter one, when it has no strategy yet."""
        if not self.config.get("starters", True) or not self.enabled():
            return []
        manager = self.sandboxes()
        deployed: list[str] = []
        for desk_id, manifest in sorted(manifests.items()):
            wanted: list[tuple[str, dict[str, Any], int]] = []
            starter = STARTERS.get(manifest.family)
            if starter:
                wanted.append((starter, starter_params(manifest.family, manifest), int(STARTER_CADENCE.get(manifest.family, 600))))
            second = SECOND_STARTERS.get(manifest.family)
            if second:
                wanted.append((second, starter_params(manifest.family, manifest, quotes=True), int(STARTER_CADENCE.get(second, 600))))
            existing = self.store.for_desk(desk_id)
            for name, params, cadence in wanted:
                row = existing.get(name)
                if row is not None and row.get("house") and not row.get("enabled", True) and not int(row.get("runs") or 0):
                    # A house starter whose dry run failed on an earlier build: the code may be
                    # fixed now, so it is tried again from the repo (and stays off if it fails).
                    path = STARTERS_DIR / f"{name}.py"
                    if path.is_file() and hasattr(manager, "toolbox_save"):
                        try:
                            manager.toolbox_save(desk_id, name, path.read_text(encoding="utf-8"), f"house starter for the {manifest.family} family")
                            self.deploy(manifest, name, cadence, params, note="house starter", house=True)
                            deployed.append(f"{desk_id}/{name}")
                        except Exception as exc:
                            self.store.update(desk_id, name, last_error=str(exc)[:300])
                    continue
                if row is not None:
                    # A house starter follows the house params, cadence and code until the desk
                    # changes the file or redeploys it as its own.
                    if row.get("house"):
                        changes: dict[str, Any] = {}
                        if dict(row.get("params") or {}) != params:
                            changes["params"] = params
                        if int(row.get("cadence_seconds") or 0) != cadence:
                            changes["cadence_seconds"] = cadence
                        if changes:
                            self.store.update(desk_id, name, **changes)
                        self._refresh_house_code(desk_id, name, row, manager)
                    continue
                path = STARTERS_DIR / f"{name}.py"
                if not path.is_file():
                    continue
                if len(self.store.for_desk(desk_id)) >= int(self.config["max_per_desk"]):
                    continue  # the desk's own strategies come first
                try:
                    code = path.read_text(encoding="utf-8")
                    if hasattr(manager, "toolbox_save"):
                        manager.toolbox_save(desk_id, name, code, f"house starter for the {manifest.family} family")
                    self.deploy(manifest, name, cadence, params, note="house starter", house=True)
                    deployed.append(f"{desk_id}/{name}")
                except Exception as exc:
                    self.service.alert("warning", f"starter strategy {name} for {desk_id} not deployed: {str(exc)[:160]}")
                    # Remember the attempt so a broken starter is not retried every tick.
                    self.store.update(desk_id, name, enabled=False, last_error=str(exc)[:300], deployed_at=self.service.now(), cadence_seconds=cadence, params=params, house=True)
        return deployed

    def _refresh_house_code(self, desk_id: str, starter: str, row: Mapping[str, Any], manager: Any) -> None:
        """Ship a newer house starter to a desk that has not touched its copy."""
        path = STARTERS_DIR / f"{starter}.py"
        if not path.is_file() or not hasattr(manager, "toolbox_files"):
            return
        try:
            house = path.read_text(encoding="utf-8")
            current = manager.toolbox_files(desk_id).get(f"{starter}.py")
        except Exception:
            return
        if current is None or current == house:
            return
        if _sha(current) != str(row.get("code_sha256") or ""):
            return  # the desk edited its copy; it is the desk's now
        try:
            manager.toolbox_save(desk_id, starter, house, "house starter (updated)")
            self.store.update(desk_id, starter, code_sha256=_sha(house))
        except Exception:
            return

    def due(self, manifests: Mapping[str, DeskManifest], at: str) -> list[tuple[DeskManifest, str, dict[str, Any]]]:
        now = _epoch(at)
        found: list[tuple[float, DeskManifest, str, dict[str, Any]]] = []
        for desk_id, rows in self.store.read().items():
            manifest = manifests.get(desk_id)
            if manifest is None:
                continue
            for name, row in rows.items():
                if not row.get("enabled", True):
                    continue
                last = _epoch(row.get("last_run_at")) if row.get("last_run_at") else None
                cadence = int(row.get("cadence_seconds") or self.config["min_cadence_seconds"])
                if last is None or now - last >= cadence:
                    found.append((last or 0.0, manifest, name, row))
        found.sort(key=lambda item: (item[0], item[1].id, item[2]))
        return [(m, n, r) for _, m, n, r in found]

    def tick(self, manifests: Mapping[str, DeskManifest], at: str) -> list[dict[str, Any]]:
        """Run the strategies that are due, a bounded number per tick. Never raises."""
        if not self.enabled():
            return []
        if not self._bootstrapped:
            self._bootstrapped = True
            try:
                self.bootstrap(manifests)
            except Exception as exc:
                self.service.alert("warning", f"strategy starters failed: {type(exc).__name__}")
        out: list[dict[str, Any]] = []
        for manifest, name, row in self.due(manifests, at)[: int(self.config["max_runs_per_tick"])]:
            try:
                out.append(self.run_one(manifest, name, row, at))
            except Exception as exc:
                self.service.alert("warning", f"strategy {manifest.id}/{name} failed: {type(exc).__name__}")
                self.store.update(manifest.id, name, last_run_at=at, errors=int(row.get("errors") or 0) + 1, last_error=f"{type(exc).__name__}")
        return out

    def run_one(self, manifest: DeskManifest, name: str, row: Mapping[str, Any], at: str) -> dict[str, Any]:
        params = dict(row.get("params") or {})
        run = self._execute(manifest, name, params, at)
        intents = run.get("intents") if isinstance(run.get("intents"), list) else []
        cancels = [str(c) for c in (run.get("cancels") or []) if isinstance(c, str)][:20] if not run.get("error") else []
        cancelled = self._cancel(manifest, name, cancels, at) if cancels else 0
        decisions: list[dict[str, Any]] = []
        if not run.get("error") and intents:
            decisions = self._propose(manifest, name, intents, at)
        approved = sum(1 for d in decisions if d.get("approved"))
        if cancelled:
            run["notes"] = f"{cancelled} cancelled; " + str(run.get("notes") or "")
        self.store.update(
            manifest.id,
            name,
            last_run_at=at,
            runs=int(row.get("runs") or 0) + 1,
            intents=int(row.get("intents") or 0) + len(intents),
            approved=int(row.get("approved") or 0) + approved,
            errors=int(row.get("errors") or 0) + (1 if run.get("error") else 0),
            last_error=(str(run["error"])[-300:] if run.get("error") else None),
            last_notes=(str(run.get("notes") or "") + " | " + " / ".join(str(x) for x in (run.get("log") or [])[-3:]))[:400],
        )
        purpose = f"strategy {name}: " + (
            f"error" if run.get("error") else f"{len(intents)} intent(s), {approved} approved"
        )
        self._publish_run(manifest, name, run, at, purpose, always=bool(intents or run.get("error")), row=row)
        return {"desk_id": manifest.id, "strategy": name, "intents": len(intents), "approved": approved, "error": bool(run.get("error"))}

    # ------------------------------------------------------------------ execution
    def _execute(self, manifest: DeskManifest, name: str, params: Mapping[str, Any], at: str, *, dry: bool = False) -> dict[str, Any]:
        manager = self.sandboxes()
        context = self.context_for(manifest, at)
        context["dry_run"] = bool(dry)
        code = RUNNER % {
            "params": json.dumps(json.dumps(dict(params))),
            "context": json.dumps(json.dumps(context)),
            "name": name,
            "max_intents": int(self.config["max_intents_per_run"]),
        }
        run = manager.run(manifest.id, code, purpose=f"strategy {name}", timeout=int(self.config["run_timeout_seconds"]))
        result: dict[str, Any] = {"exit_code": run.exit_code, "seconds": str(run.seconds), "stdout": run.stdout, "code_sha256": run.code_sha256, "sandbox": run.sandbox}
        parsed = _parse_result(run.stdout)
        if parsed is None:
            result["error"] = f"exit {run.exit_code}: no result line ({(run.stdout or '')[-300:]})" if run.exit_code else "no result line in the output"
            result["intents"] = []
            return result
        result.update(parsed)
        if run.exit_code and not parsed.get("error"):
            result["error"] = f"exit {run.exit_code}"
        return result

    def size_cap(self, manifest: DeskManifest, name: str) -> Decimal:
        """How much one of the strategy's orders may commit on a live desk.

        Learning size until the strategy has earned more: `earned_settled` settled positions
        and a positive settled P&L after fees lift the cap to `earned_multiple` times learning
        size, and the desk's own limits still bind above that. A strategy that loses money goes
        back to learning size on the next run. This is the floor's capital following the
        strategies that earn it, one step at a time."""
        learning = self.learning_usd(manifest)
        if not manifest.live:
            return learning
        record = self.record(manifest.id, name)
        settled = int(record.get("settled") or 0)
        pnl = _dec(record.get("settled_pnl_usd")) or Decimal(0)
        if settled >= int(self.config.get("earned_settled", 20)) and pnl > 0:
            return learning * Decimal(str(self.config.get("earned_multiple", 3)))
        return learning

    def _cancel(self, manifest: DeskManifest, name: str, order_ids: list[str], at: str) -> int:
        """Cancel the desk's own resting orders a strategy asked to replace. A strategy may only
        cancel orders it placed itself, so two strategies on one desk never fight."""
        mine = {o["order_id"] for o in self.open_orders_for(manifest) if o.get("strategy") == name}
        ctx = self.service.context(manifest)
        done = 0
        for order_id in order_ids:
            if order_id not in mine:
                continue
            try:
                ctx.cancel_order(order_id)
                done += 1
            except Exception as exc:
                self.service.alert("warning", f"strategy {manifest.id}/{name} could not cancel {order_id}: {type(exc).__name__}")
        return done

    def _propose(self, manifest: DeskManifest, name: str, intents: list[dict[str, Any]], at: str) -> list[dict[str, Any]]:
        """Propose each intent as the desk would: same tools path, same risk engine, same events."""
        from . import tools as tools_module

        stamp = at[:16].replace("-", "").replace(":", "").replace("T", "-")
        session_id = f"{manifest.id}:{stamp}:strategy:{name}"
        ctx = self.service.context(manifest, session_id=session_id)
        if hasattr(ctx, "bind_session"):
            try:
                ctx.bind_session(session_id)
            except Exception:
                pass
        session = tools_module.ToolSession(session_id=session_id, desk_id=manifest.id, now=at)
        cap = self.size_cap(manifest, name)
        out: list[dict[str, Any]] = []
        for raw in intents[: int(self.config["max_intents_per_run"])]:
            args = dict(raw)
            args.setdefault("order_type", "limit")
            if args.get("order_type") != "limit" or _dec(args.get("limit_price")) is None:
                out.append({"approved": False, "reasons": ["a strategy proposes limit orders with a limit_price"], "rationale": str(args.get("rationale") or "")[:200]})
                continue
            if manifest.live:
                args["quantity"] = _capped_quantity(args, cap)
            args["rationale"] = f"[strategy {name}] " + str(args.get("rationale") or "no rationale given")[:1800]
            try:
                result = tools_module.execute("propose_order", args, ctx, manifest, session)
                data = json.loads(result) if isinstance(result, str) else result
            except Exception as exc:
                data = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            if isinstance(data, dict) and "error" in data:
                out.append({"approved": False, "reasons": [str(data["error"])[:300]]})
            else:
                out.append({"approved": bool(data.get("approved")), "reasons": list(data.get("reasons") or []), "intent_id": data.get("intent_id")})
        return out

    def _publish_run(self, manifest: DeskManifest, name: str, run: Mapping[str, Any], at: str, purpose: str, *, always: bool, row: Mapping[str, Any] | None = None) -> None:
        """A `desk.code_run` for the run: always for a deploy, an error or an intent; hourly when idle."""
        if not always:
            last = _epoch(row.get("last_published_at")) if row and row.get("last_published_at") else None
            if last is not None and _epoch(at) - last < int(self.config["idle_publish_seconds"]):
                return
        stdout = str(run.get("stdout") or "")
        parsed_line = stdout.rfind("STRATEGY-RESULT ")
        shown = stdout[:parsed_line].rstrip() if parsed_line > 0 else ""
        summary = {
            "intents": len(run.get("intents") or []),
            "notes": str(run.get("notes") or "")[:600],
            "log": list(run.get("log") or [])[-8:],
            **({"error": str(run["error"])[-600:]} if run.get("error") else {}),
        }
        text = (shown[-1200:] + "\n" if shown else "") + json.dumps(summary, separators=(",", ":"))[:2400]
        stamp = at[:16].replace("-", "").replace(":", "").replace("T", "-")
        payload = {
            "session_id": f"{manifest.id}:{stamp}:strategy:{name}",
            "code_sha256": str(run.get("code_sha256") or "")[:64] or "0" * 64,
            "language": "python",
            "stdout": text[:4000],
            "exit_code": int(run.get("exit_code") or 0),
            "seconds": str(run.get("seconds") or "0"),
            "sandbox": None if not run.get("sandbox") else str(run["sandbox"])[-12:],
            "purpose": purpose[:200],
        }
        try:
            self.service.log.append(manifest.stream, "desk.code_run", payload, id=f"strategy:{manifest.id}:{name}:{at}", at=at)
            self.store.update(manifest.id, name, last_published_at=at)
        except Exception as exc:
            self.service.alert("warning", f"strategy run not published: {type(exc).__name__}")


# ---------------------------------------------------------------------- helpers
def _strategy_of(session_id: str) -> str | None:
    """`<desk>:<stamp>:strategy:<name>` -> name, else None."""
    parts = session_id.split(":strategy:", 1)
    return parts[1] if len(parts) == 2 and parts[1] else None


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _epoch(at: Any) -> float:
    from datetime import datetime, timezone

    text = str(at or "").strip()
    for pattern in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return 0.0


def _plain_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    if params is None:
        return {}
    if not isinstance(params, Mapping):
        raise ValueError("params must be an object")
    text = json.dumps(dict(params), default=str)
    if len(text) > 4000:
        raise ValueError("params must be under 4000 characters as JSON")
    return json.loads(text)


def _parse_result(stdout: str) -> dict[str, Any] | None:
    if not stdout:
        return None
    marker = stdout.rfind("STRATEGY-RESULT ")
    if marker < 0:
        return None
    line = stdout[marker + len("STRATEGY-RESULT "):].split("\n", 1)[0].strip()
    try:
        data = json.loads(line)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("intents", [])
    if not isinstance(data["intents"], list):
        data["intents"] = []
    return data


def _capped_quantity(args: Mapping[str, Any], cap_usd: Decimal) -> str:
    """The learning-size cap for a live desk's strategy: notional at the limit at most `cap_usd`."""
    price = _dec(args.get("limit_price")) or Decimal(0)
    quantity = _dec(args.get("quantity")) or Decimal(0)
    if price <= 0 or quantity <= 0:
        return str(args.get("quantity"))
    notional = quantity * price
    if notional <= cap_usd:
        return str(quantity)
    allowed = cap_usd / price
    asset_class = str((args.get("instrument") or {}).get("asset_class") or "")
    if asset_class == "event":
        allowed = Decimal(int(allowed))
        return str(max(allowed, Decimal(1)))
    return format(allowed.quantize(Decimal("0.00000001")), "f")


__all__ = ["DEFAULTS", "STARTERS", "Strategies", "StrategyStore"]
