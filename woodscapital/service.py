"""The always-on floor: one process that never sleeps through an open.

`Service.tick()` is the whole runtime in one method, and it is deliberately boring:

1. run any desk session whose cadence slot has come round in the desk's own timezone,
2. advance the paper venues and poll every live order,
3. mark every sub-ledger on the mark interval,
4. evaluate the circuit breakers and publish any that tripped,
5. run the committee on its weekday and the evolution loop on its daily slot,
6. push the event tape and the leaderboard checkpoint to the site,
7. write the health file the supervisor watches.

Everything with an external dependency -- the model provider, the paper simulator, the live venue
adapters, the desk runtime, the market data sources -- is constructed through a small factory that
tests replace. Nothing in this module opens a socket by itself, and `.env` is read only to hand
credentials straight to an adapter: they are never logged, never published and never returned.
"""

from __future__ import annotations

import hashlib
import json
import re
import os
import signal
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from .broker import Instrument, OrderIntent, money, text
from .committee import Committee, capital_mode, promoted_desks, retired_desks
from .events import EventLog, canonical, now_iso
from .evolve import Evolution
from .gateway import Gateway
from .ledger import DeskLedger, floor_totals, iso_time, parse_iso
from .manifest import DeskManifest, load_all
from .publish import Publisher, checkpoint_body
from .risk import RiskEngine, circuit_breakers

PACKAGE_DIR = Path(__file__).resolve().parent
ZERO = Decimal(0)

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "site_url": "https://blakewoods.us",
    "timezone": "America/New_York",
    "floor_cap_usd_per_day": "15",
    "reserve_floor_usd": "10",
    "floor_capital_usd": "5000",
    "floor_max_daily_loss_pct": "0.02",
    "mark_interval_seconds": 300,
    "sleep_seconds": 30,
    "session_catchup_seconds": 3600,
    "committee_weekday": 6,
    "committee_time": "18:00",
    "evolution_time": "19:00",
    "postmortem_time": "21:30",
    # Research sources a desk may reach. Absent means enabled; set false to run without one.
    "sources": {},
    "profit_share": "0.25",
    "floor_cap_max_usd_per_day": "60",
    "publish": True,
    "publish_token_env": "CAPITAL_PUBLISH_TOKEN",
    "paper_slippage_bps": 5,
    # Live venues are configured but not enabled: this phase is paper only.
    "live_venues": [],
    "venues": {
        "alpaca": {
            "paper": True,
            "key_id_env": "ALPACA_PAPER_KEY_ID",
            "secret_env": "ALPACA_PAPER_SECRET_KEY",
        },
        "kalshi": {
            "key_id_env": "KALSHI_KEY_ID",
            "private_key_path": ".data/capital/keys/kalshi.pem",
        },
        "coinbase": {
            "key_name_env": "COINBASE_KEY_NAME",
            "secret_env": "COINBASE_API_SECRET",
            "private_key_path": ".data/capital/keys/coinbase.pem",
        },
    },
}


def default_config() -> dict[str, Any]:
    """The packaged defaults, overlaid with `woodscapital/config.json` when it exists."""
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    path = PACKAGE_DIR / "config.json"
    if path.exists():
        try:
            config.update(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return config


def load_env(path: str | Path) -> dict[str, str]:
    """Parse a `KEY=VALUE` file. Values are never logged, printed or published."""
    out: dict[str, str] = {}
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return out
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _clock_minutes(value: str) -> int:
    return int(value[:2]) * 60 + int(value[3:5])


# --------------------------------------------------------------------------- the tool context


FACT_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "GrossProfit",
    "OperatingIncomeLoss",
    "NetIncomeLoss",
    "EarningsPerShareDiluted",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsForRepurchaseOfCommonStock",
    "PaymentsOfDividends",
    "PaymentsOfDividendsCommonStock",
    "CashAndCashEquivalentsAtCarryingValue",
    "LongTermDebt",
    "LongTermDebtNoncurrent",
    "DebtCurrent",
    "Assets",
    "Liabilities",
    "StockholdersEquity",
    "InventoryNet",
    "AccountsReceivableNetCurrent",
    "ResearchAndDevelopmentExpense",
    "InterestExpense",
    "IncomeTaxExpenseBenefit",
)


def compact_facts(symbol: str, raw: Mapping[str, Any], *, per_tag: int = 8) -> dict[str, Any]:
    """Reduce SEC companyfacts to the recent, filed observations of a fixed tag list."""
    facts = raw.get("facts") if isinstance(raw, Mapping) else None
    gaap = facts.get("us-gaap") if isinstance(facts, Mapping) else None
    out: dict[str, Any] = {
        "symbol": symbol,
        "entity": raw.get("entityName") if isinstance(raw, Mapping) else None,
        "cik": raw.get("cik") if isinstance(raw, Mapping) else None,
        "source": "SEC companyfacts (XBRL); values as filed, USD unless noted",
        "tags": {},
    }
    if not isinstance(gaap, Mapping):
        return out
    for tag in FACT_TAGS:
        entry = gaap.get(tag)
        if not isinstance(entry, Mapping):
            continue
        units = entry.get("units") or {}
        rows: list[dict[str, Any]] = []
        for unit, observations in units.items():
            if unit not in ("USD", "shares", "USD/shares"):
                continue
            for obs in observations or []:
                if not isinstance(obs, Mapping) or obs.get("form") not in ("10-K", "10-Q", "20-F", "40-F"):
                    continue
                rows.append(
                    {
                        "value": obs.get("val"),
                        "unit": unit,
                        "start": obs.get("start"),
                        "end": obs.get("end"),
                        "fy": obs.get("fy"),
                        "fp": obs.get("fp"),
                        "form": obs.get("form"),
                        "filed": obs.get("filed"),
                        "accession": obs.get("accn"),
                    }
                )
        if not rows:
            continue
        rows.sort(key=lambda r: (str(r.get("end") or ""), str(r.get("filed") or "")), reverse=True)
        seen: set[tuple[Any, Any]] = set()
        kept: list[dict[str, Any]] = []
        for row in rows:
            key = (row.get("start"), row.get("end"))
            if key in seen:
                continue  # the same period is refiled in later reports; keep the newest filing
            seen.add(key)
            kept.append(row)
            if len(kept) >= per_tag:
                break
        out["tags"][tag] = kept
    return out


class DeskContext:
    """One desk's view of the world: the `tools.ToolContext` surface, wired to real components.

    Return shapes are exactly what `tools.execute` expects -- a `Quote`, a list of `Position`,
    a `Balance`, plain lists of dicts -- with no envelopes, because the tool layer serializes
    them. Failures raise; `tools.execute` turns any exception into a JSON error the model reads.

    A desk reaches a broker only through `propose_order`, which goes to the risk engine first and
    can only ever come back with a decision. The playbook methods here are deliberately plain
    file access: `desk.Desk` wraps this context in its own router so that versioning, diffing and
    the `desk.playbook_updated` event all live in one place.
    """

    def __init__(
        self,
        service: "Service",
        manifest: DeskManifest,
        *,
        session_id: str | None = None,
    ):
        self.service = service
        self.manifest = manifest
        self.desk_id = manifest.id
        self.session_id = session_id
        self.ended = False

    # -- market data -------------------------------------------------------
    def _data(self) -> Any:
        data = self.service.market_data
        if data is None:
            raise RuntimeError("no market data source is configured")
        return data

    def quote(self, instrument: Instrument) -> Any:
        found = self.service.quote(instrument)
        if found is None:
            raise RuntimeError(f"no quote available for {instrument.key}")
        return found

    def bars(self, instrument: Instrument, interval: str, limit: int) -> list[dict[str, Any]]:
        rows = self._data().bars(instrument, interval, limit)
        return [row.to_dict() if hasattr(row, "to_dict") else dict(row) for row in rows]

    def news(self, query: str, limit: int) -> list[dict[str, Any]]:
        source = self.service.source("news")
        if source is None:
            raise RuntimeError("no news source is configured")
        reader = getattr(source, "search", None) or getattr(source, "headlines")
        return list(reader(query, limit=limit))

    def filing(self, symbol: str, form: str, index: int) -> dict[str, Any]:
        edgar = self.service.source("edgar")
        if edgar is None:
            raise RuntimeError("no filings source is configured")
        cik = edgar.cik_for(symbol)
        rows = edgar.recent_filings(cik, forms=[form] if form else None, limit=index + 1)
        if index >= len(rows):
            raise RuntimeError(f"{symbol}: no {form or 'recent'} filing at index {index}")
        row = rows[index]
        document = edgar.filing_text(row["url"])
        return {**{k: v for k, v in row.items() if k != "url"}, **document, "symbol": symbol}

    def facts(self, symbol: str) -> dict[str, Any]:
        """A compact financial fact sheet: recent values for the tags a desk actually uses.

        Raw companyfacts runs to megabytes; this keeps the last eight 10-K/10-Q observations
        per tag (USD or shares), each with its period, form and filing date, so a desk can build
        a cash-flow bridge without paying to read the whole XBRL history.
        """
        edgar = self.service.source("edgar")
        if edgar is None:
            raise RuntimeError("no filings source is configured")
        raw = edgar.companyfacts(edgar.cik_for(symbol))
        return compact_facts(symbol, raw)

    def calendar(self, days: int) -> list[dict[str, Any]]:
        """The next `days` calendar days, with the session on each one or None when closed."""
        data = self._data()
        start = parse_iso(self.service.now()).date()
        out: list[dict[str, Any]] = []
        for offset in range(max(1, min(int(days), 90))):
            day = (start + timedelta(days=offset)).isoformat()
            session = data.session(day)
            out.append(
                {"date": day, "open": session is not None,
                 **(session.to_dict() if session is not None else {})}
            )
        return out

    def chain(self, symbol: str, expiry: str) -> list[dict[str, Any]]:
        source = self.service.source("chain")
        if source is None:
            raise RuntimeError("no option chain source is configured")
        return list(source.chain(symbol, expiry))

    def event_markets(self, query: str) -> list[dict[str, Any]]:
        """Open event contracts matching a free-text query, priced in dollars.

        Kalshi has no text search, so the service keeps a ten-minute index of open events with
        their nested markets and matches the query's words against event and market titles,
        series tickers and event tickers. Results are sorted by 24-hour volume.
        """
        source = self.service.source("event")
        if source is None:
            raise RuntimeError("no event market source is configured")
        index = self.service.event_index(source)
        # A query that names a series or market ticker (KXFEDDECISION-26SEP) is looked up
        # directly, so a market the sweep missed is still reachable by name.
        direct: list[dict[str, Any]] = []
        for token in re.findall(r"\b[A-Z][A-Z0-9]{2,}(?:-[A-Z0-9.]+)*\b", query or ""):
            try:
                page = source.markets(series_ticker=token.split("-")[0], status="open", limit=200)
                direct.extend(dict(r) for r in page.get("markets", []) if isinstance(r, Mapping))
            except Exception:
                continue
        if direct:
            wanted = query.lower()
            direct = [r for r in direct if not r.get("ticker") or str(r.get("ticker")).lower().startswith(wanted.split()[0].lower().split("-")[0])]
            for r in direct:
                r["series_ticker"] = str(r.get("ticker") or "").split("-")[0]
            seen = {r.get("ticker") for r in direct}
            index = direct + [r for r in index if r.get("ticker") not in seen]
        words = [w for w in re.split(r"[^a-z0-9]+", (query or "").lower()) if len(w) > 1]
        scored: list[tuple[int, Decimal, dict[str, Any]]] = []
        for row in index:
            haystack = row.get("_haystack") or " ".join(
                str(x or "") for x in (row.get("title"), row.get("yes_sub_title"), row.get("ticker"), row.get("event_ticker"))
            ).lower()
            hits = sum(1 for w in words if w in haystack)
            if words and hits == 0:
                continue
            volume = row.get("volume_24h") or ZERO
            try:
                volume = money(volume)
            except (TypeError, ValueError):
                volume = ZERO
            scored.append((hits, volume, row))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        return [{k: v for k, v in row.items() if not k.startswith("_")} for _, _, row in scored[:40]]

    # -- the desk's own book ----------------------------------------------
    def positions(self) -> list[Any]:
        state = self.service.ledgers[self.desk_id].state(self.service.now())
        return list(state.positions.values())

    def balance(self) -> Any:
        from .broker import Balance

        state = self.service.ledgers[self.desk_id].state(self.service.now())
        return Balance(
            venue=self.manifest.venues[0],
            cash=state.cash,
            equity=state.equity,
            buying_power=state.cash if state.cash > ZERO else ZERO,
            as_of=state.as_of,
        )

    def outcomes(self, limit: int) -> list[dict[str, Any]]:
        """The desk's own closed record: fills newest last, each with the order it came from."""
        fills = [
            event.payload
            for event in self.service.log.read(kind="broker.fill", limit=10_000)
            if event.payload.get("desk_id") == self.desk_id
        ]
        orders = {row["order_id"]: row for row in self.service.gateway.orders(self.desk_id)}
        rows = [
            {**fill, "order": orders.get(fill.get("order_id"), {}).get("status")}
            for fill in fills
        ]
        return rows[-max(1, int(limit)) :]

    # -- memory and writing ------------------------------------------------
    def memory_read(self, query: str, limit: int) -> list[dict[str, Any]]:
        store = self.service.memory
        if store is None:
            return []
        return list(store.read(query, limit or self.manifest.memory_limit))

    def memory_write(self, entry: dict[str, Any]) -> dict[str, Any]:
        store = self.service.memory
        if store is None:
            return {"written": False, "reason": "no memory store"}
        payload = dict(entry) if isinstance(entry, Mapping) else {"text": str(entry)}
        payload.setdefault("desk_id", self.desk_id)
        payload.setdefault("session_id", self.session_id)
        return store.write(payload) or {"written": True}

    def memo(self, title: str, text_body: str) -> dict[str, Any]:
        at = self.service.now()
        event = self.service.log.append(
            self.manifest.stream,
            "desk.memo",
            {
                "session_id": self.session_id,
                "title": str(title)[:200],
                "text": str(text_body)[:20_000],
            },
            id=f"memo:{self.desk_id}:{self.session_id}:{at}",
            at=at,
        )
        return {"event_id": event.id, "title": str(title)[:200]}

    # -- orders ------------------------------------------------------------
    def propose_order(self, intent: Any) -> dict[str, Any]:
        if not isinstance(intent, OrderIntent):
            raise TypeError("propose_order takes an OrderIntent")
        if intent.desk_id != self.desk_id:
            raise ValueError("a desk may only propose its own orders")
        return self.service.gateway.propose(intent, self.service.now())

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self.service.gateway.cancel(self.desk_id, order_id, self.service.now())

    # -- the playbook ------------------------------------------------------
    def _playbook_path(self) -> Path:
        return self.service.root / self.manifest.playbook

    def playbook_read(self) -> str:
        try:
            return self._playbook_path().read_text(encoding="utf-8")
        except OSError:
            return ""

    def playbook_write(self, text_body: str, reason: str) -> dict[str, Any]:
        """Plain write. `desk.Desk` wraps this context and owns versioning and the diff event."""
        path = self._playbook_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
        tmp.write_text(text_body, encoding="utf-8")
        tmp.replace(path)
        return {"written": True, "path": self.manifest.playbook, "reason": str(reason)[:1000]}

    def end_session(self, summary: str) -> dict[str, Any]:
        self.ended = True
        return {"ended": True, "summary": str(summary)[:2000]}


# --------------------------------------------------------------------------- the service

class Service:
    """The floor's process. One instance per box."""

    def __init__(
        self,
        root: str | Path,
        config: Mapping[str, Any] | None = None,
        *,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
        transport: Any = None,
        market_data: Any = None,
        provider: Any = None,
        memory: Any = None,
        publisher: Any = None,
        broker_factory: Callable[..., Any] | None = None,
        desk_factory: Callable[..., Any] | None = None,
        context_factory: Callable[..., Any] | None = None,
        risk_engine: RiskEngine | None = None,
    ):
        self.root = Path(root).resolve()
        self.config = {**default_config(), **dict(config or {})}
        self.clock = clock
        self.sleeper = sleeper
        self.transport = transport
        self.market_data = market_data
        self.provider = provider
        self.memory = memory
        self.broker_factory = broker_factory
        self.desk_factory = desk_factory
        self.context_factory = context_factory
        self.stopping = False
        self.last_error: str | None = None
        self._sessions: list[threading.Thread] = []
        self._last_tick: dict[str, Any] | None = None
        self._budget: dict[str, Any] = {}
        self._sources: dict[str, Any] = {}

        self.capital_dir = self.root / ".data" / "capital"
        self.capital_dir.mkdir(parents=True, exist_ok=True)
        self.desks_dir = Path(self.config.get("desks_dir") or (PACKAGE_DIR / "desks"))
        self.playbooks_dir = Path(self.config.get("playbooks_dir") or (self.root / "playbooks"))
        self.kill_switch_path = Path(
            self.config.get("kill_switch_path") or (self.capital_dir / "KILL")
        )
        self.state_path = self.capital_dir / "service-state.json"
        self.health_path = self.capital_dir / "health.json"
        self.timezone = ZoneInfo(self.config["timezone"])

        self.log = EventLog(self.capital_dir / "events.sqlite", clock=clock)
        self.manifests: dict[str, DeskManifest] = {m.id: m for m in load_all(self.desks_dir)}
        self.ledgers: dict[str, DeskLedger] = {
            desk_id: DeskLedger(self.log, desk_id) for desk_id in self.manifests
        }
        self.brokers: dict[str, Any] = {}
        self.paper_brokers: dict[str, Any] = {}
        self._env: dict[str, str] | None = None

        if self.market_data is None:
            self.market_data = self._build_market_data()
        self._build_brokers()
        if self.provider is None:
            self.provider = self._build_provider()
        if self.memory is None:
            self.memory = self._build_memory()

        self.risk_engine = risk_engine or RiskEngine()
        self.gateway = Gateway(
            self.log,
            self.risk_engine,
            self.brokers,
            self.ledgers,
            data=self.market_data,
            manifests=self.manifests,
            clock=clock,
            kill_switch_path=self.kill_switch_path,
            floor_max_daily_loss_pct=self.config["floor_max_daily_loss_pct"],
        )
        self.committee = Committee(
            self.log,
            self.manifests,
            self.ledgers,
            provider=self.provider,
            clock=clock,
            config={
                **(self.config.get("committee") or {}),
                "floor_capital_usd": self.config["floor_capital_usd"],
                "floor_cap_usd_per_day": self.config["floor_cap_usd_per_day"],
                "profit_share": self.config["profit_share"],
                "floor_cap_max_usd_per_day": self.config["floor_cap_max_usd_per_day"],
            },
        )
        self.evolution = Evolution(
            self.log,
            self.desks_dir,
            self.playbooks_dir,
            provider=self.provider,
            clock=clock,
            config=self.config.get("evolution") or {},
        )
        self.publisher = publisher if publisher is not None else self._build_publisher()

    # ------------------------------------------------------------------ construction
    def env(self) -> dict[str, str]:
        """Process environment overlaid with the repository `.env`. Values are secrets."""
        if self._env is None:
            merged = dict(load_env(self.root / ".env"))
            merged.update(os.environ)
            self._env = merged
        return self._env

    def secret(self, name: str | None) -> str | None:
        return self.env().get(name) if name else None

    def _build_market_data(self) -> Any:
        try:
            from .data import CompositeMarketData, HttpTransport
        except Exception:
            return None
        try:
            transport = self.transport or HttpTransport(
                cache_dir=self.capital_dir / "cache", ttl=300.0, min_interval=0.2
            )
            return CompositeMarketData(transport=transport)
        except Exception:
            return None

    def source(self, name: str) -> Any:
        """A research source by name, built lazily. `None` when this deployment has none.

        `news` and `edgar` are their own modules; `event` and `chain` come off the composite
        market data when it can route them. Nothing here is constructed until a desk asks.
        """
        if name in self._sources:
            return self._sources[name]
        if (self.config.get("sources") or {}).get(name, True) is False:
            self._sources[name] = None
            return None
        built: Any = None
        try:
            if name == "news":
                from .data.news import News

                built = News(self.transport, cache_dir=self.capital_dir / "cache")
            elif name == "edgar":
                from .data.edgar import Edgar

                built = Edgar(self.transport, cache_dir=self.capital_dir / "cache")
            elif name == "event":
                router = getattr(self.market_data, "_source", None)
                built = router("event") if router is not None else None
            elif name == "chain":
                built = self.market_data if hasattr(self.market_data, "chain") else None
        except Exception:
            built = None
        self._sources[name] = built
        return built

    def _build_brokers(self) -> None:
        paper_dir = self.capital_dir / "paper"
        paper_dir.mkdir(parents=True, exist_ok=True)
        modes = promoted_desks(self.log)
        for desk_id, manifest in sorted(self.manifests.items()):
            if capital_mode(manifest, modes) != "paper" and "paper" not in manifest.venues:
                continue
            broker = self._make_paper_broker(manifest, paper_dir / f"{desk_id}.sqlite")
            if broker is not None:
                self.paper_brokers[desk_id] = broker
        # Every paper desk shares the "paper" venue name; the gateway routes by venue, so the
        # first paper broker is the venue's broker and per-desk books stay in their own files.
        for venue in self.config.get("live_venues") or []:
            broker = self._make_live_broker(venue)
            if broker is not None:
                self.brokers[venue] = broker
        if self.paper_brokers:
            self.brokers.setdefault("paper", _PaperRouter(self.paper_brokers, self.manifests))

    def _make_paper_broker(self, manifest: DeskManifest, path: Path) -> Any:
        if self.broker_factory is not None:
            return self.broker_factory("paper", manifest=manifest, path=path, service=self)
        try:
            from . import sim
        except Exception:
            return None
        try:
            return sim.PaperBroker(
                path,
                venue="paper",
                data=self.market_data,
                clock=self.clock,
                initial_cash=manifest.capital_usd,
                slippage_bps=int(self.config["paper_slippage_bps"]),
                allow_short=manifest.instruments.allow_short,
            )
        except Exception as exc:
            self.alert("warning", f"paper broker for {manifest.id} unavailable: {exc}")
            return None

    def _make_live_broker(self, venue: str) -> Any:
        """Build a live venue adapter from configured env names and key files. Never logs secrets."""
        settings = (self.config.get("venues") or {}).get(venue) or {}
        if self.broker_factory is not None:
            return self.broker_factory(venue, settings=settings, service=self)
        try:
            if venue == "alpaca":
                from .adapters import AlpacaCredentials, alpaca

                key_id = self.secret(settings.get("key_id_env"))
                secret_key = self.secret(settings.get("secret_env"))
                if not key_id or not secret_key:
                    raise RuntimeError("missing credentials")
                credentials = AlpacaCredentials(key_id, secret_key, paper=bool(settings.get("paper", True)))
                return alpaca.AlpacaBroker(credentials, transport=self.transport)
            if venue == "kalshi":
                from .adapters import KalshiCredentials, RsaPssSigner, kalshi

                key_id = self.secret(settings.get("key_id_env"))
                pem = self._private_key(settings.get("private_key_path"))
                if not key_id or pem is None:
                    raise RuntimeError("missing credentials")
                credentials = KalshiCredentials(key_id, RsaPssSigner(pem))
                return kalshi.KalshiBroker(credentials, transport=self.transport, clock=self.clock)
            if venue == "coinbase":
                from .adapters import CdpSigner, CoinbaseCredentials, coinbase

                key_name = self.secret(settings.get("key_name_env"))
                secret = self.secret(settings.get("secret_env")) or self._private_key(
                    settings.get("private_key_path")
                )
                if not key_name or not secret:
                    raise RuntimeError("missing credentials")
                credentials = CoinbaseCredentials(key_name, CdpSigner(secret))
                return coinbase.CoinbaseBroker(credentials, transport=self.transport, clock=self.clock)
        except Exception as exc:
            self.alert("warning", f"live venue {venue} not enabled: {type(exc).__name__}")
        return None

    def event_index(self, source: Any) -> list[dict[str, Any]]:
        """Open Kalshi markets closing within 60 days, priced in dollars.

        The sweep takes a minute or more, so it runs on a background thread and refreshes every
        ten minutes; callers get the latest completed index (empty before the first sweep
        finishes). `/markets` filters by close time and pages 400 rows at a time.
        """
        cached = getattr(self, "_event_index", None)
        lock = getattr(self, "_event_index_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._event_index_lock = lock
        now = time.time()
        stale = cached is None or now - cached[0] >= 600
        if stale and not getattr(self, "_event_index_building", False):
            with lock:
                if not getattr(self, "_event_index_building", False):
                    self._event_index_building = True
                    worker = threading.Thread(
                        target=self._build_event_index, args=(source,), name="event-index", daemon=True
                    )
                    worker.start()
                    if cached is None:
                        worker.join(timeout=25)  # first call: wait a little so a desk sees something
        cached = getattr(self, "_event_index", None)
        return cached[1] if cached else []

    def _build_event_index(self, source: Any) -> None:
        rows: list[dict[str, Any]] = []
        try:
            now = time.time()
            for window_days in (21, 60):
                cursor = None
                lower = int(now) if window_days == 21 else int(now) + 21 * 86400
                for _ in range(150):
                    try:
                        page = source.markets(
                            status="open",
                            limit=400,
                            cursor=cursor,
                            min_close_ts=lower,
                            max_close_ts=int(now) + window_days * 86400,
                        )
                    except Exception as exc:
                        self.alert("warning", f"event index sweep stopped early: {type(exc).__name__}")
                        break
                    for row in page.get("markets", []):
                        if not isinstance(row, Mapping):
                            continue
                        row = dict(row)
                        ticker = str(row.get("ticker") or "")
                        row["series_ticker"] = ticker.split("-")[0] if ticker else None
                        row["_haystack"] = " ".join(
                            str(x or "") for x in (row.get("title"), row.get("yes_sub_title"),
                                                  row.get("no_sub_title"), row.get("event_ticker"),
                                                  row["series_ticker"], ticker)
                        ).lower()
                        rows.append(row)
                    cursor = page.get("cursor")
                    if not cursor:
                        break
                    if window_days == 21:
                        self._event_index = (now, list(rows))  # publish the near-term part early
            self._event_index = (now, rows)
        finally:
            self._event_index_building = False

    def _private_key(self, relative: str | None) -> bytes | None:
        if not relative:
            return None
        path = Path(relative)
        if not path.is_absolute():
            path = self.root / path
        try:
            return path.read_bytes()
        except OSError:
            return None

    def _build_provider(self) -> Any:
        try:
            from . import provider as provider_module
        except Exception:
            return None
        try:
            return provider_module.Provider(
                self.capital_dir / "provider.sqlite",
                transport=self.transport,
                clock=self.clock,
                log=self.log,
                floor_cap_usd_per_day=self.config["floor_cap_usd_per_day"],
                reserve_floor_usd=self.config["reserve_floor_usd"],
            )
        except Exception as exc:
            self.alert("warning", f"provider unavailable: {exc}")
            return None

    def _build_memory(self) -> Any:
        try:
            from . import desk as desk_module
        except Exception:
            return None
        store = getattr(desk_module, "MemoryStore", None)
        if store is None:
            return None
        try:
            return store(self.capital_dir / "memory.sqlite")
        except Exception:
            return None

    def _build_publisher(self) -> Publisher | None:
        if not self.config.get("publish"):
            return None
        transport = self.transport
        if transport is None:
            try:
                from .data import HttpTransport

                transport = HttpTransport()
            except Exception:
                return None
        return Publisher(
            self.log,
            self.config["site_url"],
            lambda: self.secret(self.config.get("publish_token_env")),
            transport,
            clock=self.clock,
            state_path=self.capital_dir / "publish-state.json",
            sleeper=self.sleeper,
        )

    # ------------------------------------------------------------------ small helpers
    def now(self) -> str:
        return now_iso(self.clock)

    def local(self, at: str | None = None) -> datetime:
        return parse_iso(at or self.now()).astimezone(self.timezone)

    def alert(self, level: str, message: str) -> None:
        at = self.now()
        try:
            self.log.append(
                "ops",
                "ops.alert",
                {"level": level, "text": message},
                id=f"alert:{at}:{abs(hash(message)) % 10**9}",
                at=at,
            )
        except Exception:
            pass

    def state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        return data if isinstance(data, dict) else {}

    def _save_state(self, **updates: Any) -> dict[str, Any]:
        data = {**self.state(), **updates, "updated_at": self.now()}
        tmp = self.state_path.with_name(self.state_path.name + f".tmp-{os.getpid()}")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.state_path)
        return data

    def active_manifests(self) -> dict[str, DeskManifest]:
        retired = retired_desks(self.log)
        return {k: v for k, v in self.manifests.items() if k not in retired}

    def reload_manifests(self) -> None:
        """Pick up manifests the evolution loop spawned without restarting the process."""
        for manifest in load_all(self.desks_dir):
            if manifest.id in self.manifests:
                continue
            self.manifests[manifest.id] = manifest
            self.ledgers[manifest.id] = DeskLedger(self.log, manifest.id)
            self.gateway.manifests[manifest.id] = manifest
            self.gateway.ledgers[manifest.id] = self.ledgers[manifest.id]
            self.committee.manifests[manifest.id] = manifest
            self.committee.ledgers[manifest.id] = self.ledgers[manifest.id]
            broker = self._make_paper_broker(
                manifest, self.capital_dir / "paper" / f"{manifest.id}.sqlite"
            )
            if broker is not None:
                self.paper_brokers[manifest.id] = broker

    def quote(self, instrument: Instrument):
        broker = self.brokers.get(instrument.venue)
        for source in (broker, self.market_data):
            if source is None:
                continue
            try:
                found = source.quote(instrument)
            except Exception:
                continue
            if found is not None:
                return found
        return None

    # ------------------------------------------------------------------ cadence
    def ran_today(self, manifest: DeskManifest, trigger: str, day: str) -> bool:
        """Has this desk already started a session for this trigger on this local day?

        `desk.Desk` writes `desk.session_started` itself with an id derived from its session id,
        so the schedule reads that event rather than inventing a second marker. One slot, one
        session, however many times the loop comes round.
        """
        tz = ZoneInfo(manifest.cadence.timezone)
        for event in self.log.read(stream=manifest.stream, kind="desk.session_started", limit=5000):
            if event.payload.get("trigger") != trigger:
                continue
            if parse_iso(event.at).astimezone(tz).date().isoformat() == day:
                return True
        return False

    def due_sessions(self, at: str) -> list[tuple[DeskManifest, str]]:
        """(manifest, trigger) for every cadence slot that has come round today and not run.

        Triggers are `cadence:HH:MM` for a scheduled slot and `postmortem` for the daily review,
        both inside the desk runtime's trigger grammar.
        """
        due: list[tuple[DeskManifest, str]] = []
        catchup = int(self.config["session_catchup_seconds"])
        postmortem_at = _clock_minutes(str(self.config["postmortem_time"]))
        for desk_id, manifest in sorted(self.active_manifests().items()):
            tz = ZoneInfo(manifest.cadence.timezone)
            local = parse_iso(at).astimezone(tz)
            if manifest.cadence.weekdays_only and local.weekday() >= 5:
                continue
            day = local.date().isoformat()
            minutes_now = local.hour * 60 + local.minute
            slots = [(slot, f"cadence:{slot}") for slot in manifest.cadence.sessions]
            slots.append((str(self.config["postmortem_time"]), "postmortem"))
            for slot, trigger in slots:
                minutes_slot = _clock_minutes(slot) if trigger != "postmortem" else postmortem_at
                if minutes_now < minutes_slot:
                    continue
                if (minutes_now - minutes_slot) * 60 > catchup:
                    continue
                if self.ran_today(manifest, trigger, day):
                    continue
                due.append((manifest, trigger))
        return due

    def run_session(self, manifest: DeskManifest, trigger: str) -> Any:
        """Run one desk session to completion. The desk emits its own session events."""
        context = self.context(manifest, None)
        runner = self.desk(manifest, context)
        if runner is None:
            return None
        try:
            return runner.run_session(trigger)
        except Exception as exc:
            self.alert("warning", f"session {manifest.id}/{trigger} failed: {exc}")
            return None

    def start_sessions(self, due: list[tuple[DeskManifest, str]]) -> list[threading.Thread]:
        """One thread per session: the provider polls on the caller's thread, so a desk waiting
        on a background response must not stop the floor from marking, polling or publishing."""
        threads: list[threading.Thread] = []
        for manifest, trigger in due:
            thread = threading.Thread(
                target=self.run_session,
                args=(manifest, trigger),
                name=f"session-{manifest.id}-{trigger}",
                daemon=True,
            )
            self._sessions.append(thread)
            threads.append(thread)
            thread.start()
        self._sessions = [t for t in self._sessions if t.is_alive()]
        return threads

    def context(self, manifest: DeskManifest, session_id: str | None = None) -> Any:
        if self.context_factory is not None:
            return self.context_factory(self, manifest, session_id)
        return DeskContext(self, manifest, session_id=session_id)

    def desk(self, manifest: DeskManifest, context: Any) -> Any:
        if self.desk_factory is not None:
            return self.desk_factory(manifest, context, self)
        try:
            from . import desk as desk_module
        except Exception:
            return None
        try:
            return desk_module.Desk(
                manifest,
                self.provider,
                context,
                self.log,
                clock=self.clock,
                repo_root=self.root,
            )
        except Exception as exc:
            self.alert("warning", f"desk runtime for {manifest.id} unavailable: {exc}")
            return None

    # ------------------------------------------------------------------ inference budget
    def apply_budget(self, at: str) -> dict[str, Any]:
        """Recompute the floor's daily model cap from realized profit and publish it."""
        budget = self.committee.compute_budget(at)
        cap = money(budget["cap_usd"])
        if self.provider is not None and hasattr(self.provider, "floor_cap"):
            self.provider.floor_cap = cap
        spent = ZERO
        if self.provider is not None:
            try:
                spent = money(self.provider.spent_today())
            except Exception:
                spent = ZERO
        payload = {
            "scope": "floor",
            "spent_usd": text(spent),
            "cap_usd": text(cap),
            "base_usd": text(money(budget["base_usd"])),
            "profit_share": text(money(budget["profit_share"])),
            "trailing_realized_usd": text(money(budget["trailing_realized_usd"])),
            "window_days": budget["profit_window_days"],
        }
        # One event per distinct budget picture, not one per tick: the id is the content.
        digest = hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()[:12]
        self.log.append(
            "ops", "ops.budget", payload, id=f"budget:floor:{at[:10]}:{digest}", at=at
        )
        self._budget = {**budget, "spent_today_usd": spent}
        return self._budget

    # ------------------------------------------------------------------ marks
    def mark_all(self, at: str) -> int:
        """Value every funded sleeve. A desk with no capital and no book is not marked: its
        clock starts when the committee funds it, not when the process does."""
        marked = 0
        for desk_id, ledger in sorted(self.ledgers.items()):
            state = ledger.state(at)
            if state.net_deposits <= ZERO and not state.positions:
                continue
            quotes: dict[str, Any] = {}
            for key, position in state.positions.items():
                found = self.quote(position.instrument)
                if found is not None:
                    quotes[key] = found
            ledger.mark(quotes, at)
            marked += 1
        return marked

    def breakers(self, at: str) -> list[dict[str, Any]]:
        floor = floor_totals(self.ledgers, at)
        tripped: list[dict[str, Any]] = []
        for desk_id, manifest in sorted(self.active_manifests().items()):
            state = self.ledgers[desk_id].state(at)
            if state.net_deposits <= ZERO:
                # A desk the committee has not funded has no equity to lose. Calling that
                # bankruptcy would pause every desk on the floor's first morning.
                continue
            for breaker in circuit_breakers(
                desk=manifest,
                desk_equity=state.equity,
                desk_daily_pnl=state.daily_pnl,
                floor_equity=floor["equity"],
                floor_daily_pnl=floor["daily_pnl"],
                floor_max_daily_loss_pct=money(self.config["floor_max_daily_loss_pct"]),
                reconciliation_mismatch=self.gateway.reconciliation_mismatch,
            ):
                self.gateway.breaker(breaker, at)
                tripped.append(breaker.to_dict())
        return tripped

    # ------------------------------------------------------------------ the tick
    def tick(self, now: Any = None) -> dict[str, Any]:
        at = iso_time(now) if now is not None else self.now()
        local = self.local(at)
        state = self.state()
        result: dict[str, Any] = {
            "at": at,
            "sessions": [],
            "orders": [],
            "marked": 0,
            "breakers": [],
            "committee": False,
            "evolution": [],
            "published": None,
            "budget": None,
            "kill_switch": self.gateway.kill_switch_engaged(),
        }

        result["budget"] = {k: str(v) for k, v in self.apply_budget(at).items()}
        if not result["kill_switch"]:
            due = self.due_sessions(at)
            self.start_sessions(due)
            result["sessions"] = [f"{m.id}/{trigger}" for m, trigger in due]

        for broker in self.paper_brokers.values():
            ticker = getattr(broker, "tick", None)
            if ticker is not None:
                try:
                    ticker()
                except Exception as exc:
                    self.alert("warning", f"paper venue tick failed: {exc}")
        try:
            result["orders"] = [row["order_id"] for row in self.gateway.poll_orders(at)]
        except Exception as exc:
            self.alert("warning", f"order poll failed: {exc}")

        interval = int(self.config["mark_interval_seconds"])
        last_mark = state.get("last_mark_at")
        if last_mark is None or (parse_iso(at) - parse_iso(last_mark)).total_seconds() >= interval:
            result["marked"] = self.mark_all(at)
            result["breakers"] = self.breakers(at)
            self._save_state(last_mark_at=at)

        day = local.date().isoformat()
        # A desk that has never been funded, or a roster change, gets an allocation right away;
        # the weekly resize by track record still only happens on the committee's day.
        previous, _ = self.committee.last_allocation()
        if any(desk_id not in previous for desk_id in self.manifests):
            self.committee.allocate(at)
            result["committee"] = True
        if self._due(local, self.config["committee_time"], state.get("last_committee_day"), day):
            if local.weekday() == int(self.config["committee_weekday"]):
                self.committee.allocate(at)
                self.committee.memo(at)
                self._save_state(last_committee_day=day)
                result["committee"] = True
        if self._due(local, self.config["evolution_time"], state.get("last_evolution_day"), day):
            actions = list(self.evolution.select(at)) + list(self.evolution.promote(at))
            self.reload_manifests()
            self._save_state(last_evolution_day=day)
            result["evolution"] = actions

        result["published"] = self.publish()
        self.health(at, result)
        return result

    @staticmethod
    def _due(local: datetime, clock_time: str, last_day: Any, day: str) -> bool:
        if last_day == day:
            return False
        return local.hour * 60 + local.minute >= _clock_minutes(clock_time)

    def publish(self) -> dict[str, Any] | None:
        if self.publisher is None:
            return None
        try:
            released = self.gateway.release_deferred_events()
            summary = self.publisher.push_events(released)
            self.publisher.push_checkpoint(self.checkpoint())
            return summary
        except Exception as exc:
            self.last_error = f"publish: {exc}"
            self.alert("warning", f"publish failed: {exc}")
            return None

    # ------------------------------------------------------------------ projections
    def checkpoint(self, at: str | None = None) -> dict[str, Any]:
        at = at or self.now()
        modes = promoted_desks(self.log)
        retired = retired_desks(self.log)
        allocations, _ = self.committee.last_allocation()
        floor = floor_totals(self.ledgers, at)
        weighted = ZERO
        weights = ZERO
        desks: list[dict[str, Any]] = []
        orders_by_desk: dict[str, int] = {}
        for row in self.gateway.orders():
            desk_id = row.get("desk_id")
            if isinstance(desk_id, str):
                orders_by_desk[desk_id] = orders_by_desk.get(desk_id, 0) + 1
        for desk_id, manifest in sorted(self.manifests.items()):
            state = self.ledgers[desk_id].state(at)
            report = self.committee.gates(desk_id, at)
            if state.net_deposits > 0:
                weighted += state.time_weighted_return_pct * state.net_deposits
                weights += state.net_deposits
            desks.append(
                {
                    "id": desk_id,
                    "name": manifest.name,
                    "family": manifest.family,
                    "generation": manifest.generation,
                    "parent_id": manifest.parent_id,
                    "mode": capital_mode(manifest, modes),
                    "venues": list(manifest.venues),
                    "capital_usd": allocations.get(desk_id, manifest.capital_usd),
                    "equity": state.equity,
                    "cash": state.cash,
                    "daily_pnl": state.daily_pnl,
                    "return_pct": state.time_weighted_return_pct,
                    "max_drawdown_pct": state.max_drawdown_pct,
                    "days_live": state.days_live,
                    "orders": orders_by_desk.get(desk_id, 0),
                    "cost_usd": self.committee.cost_usd(desk_id),
                    "status": self.desk_status(desk_id, retired),
                    "gate": {
                        "name": report["gate"],
                        "passed": report["passed"],
                        "evidence": {
                            **{k: v for k, v in (report.get("evidence") or {}).items()},
                            "failed": ", ".join(report.get("failed") or []) or "none",
                        },
                    },
                    "updated_at": state.as_of,
                }
            )
        memo = self.log.last("committee", "committee.memo")
        budget = self._budget or self.committee.compute_budget(at)
        spent = budget.get("spent_today_usd")
        if spent is None and self.provider is not None:
            try:
                spent = money(self.provider.spent_today())
            except Exception:
                spent = ZERO
        return checkpoint_body(
            published_at=at,
            floor={
                "equity": floor["equity"],
                "cash": floor["cash"],
                "daily_pnl": floor["daily_pnl"],
                "capital_usd": sum(allocations.values(), ZERO) or floor["net_deposits"],
                "since_inception_pct": (weighted / weights) if weights > 0 else ZERO,
                "benchmark": None,
            },
            desks=desks,
            committee={
                "last_memo_at": memo.at if memo else None,
                "allocations": {k: text(v) for k, v in sorted(allocations.items())},
            },
            budget={
                "spent_today_usd": spent if spent is not None else ZERO,
                "cap_usd": money(budget["cap_usd"]),
                "base_usd": money(budget["base_usd"]),
                "profit_share": money(budget["profit_share"]),
                "trailing_realized_usd": money(budget["trailing_realized_usd"]),
            },
        )

    def desk_status(self, desk_id: str, retired: set[str] | None = None) -> str:
        retired = retired if retired is not None else retired_desks(self.log)
        if desk_id in retired:
            return "retired"
        if desk_id in self.gateway.blocked_desks:
            return "blocked"
        if self.gateway.kill_switch_engaged():
            return "halted"
        return "active"

    # ------------------------------------------------------------------ health
    def status(self, at: str | None = None) -> dict[str, Any]:
        at = at or self.now()
        floor = floor_totals(self.ledgers, at)
        state = self.state()
        modes = promoted_desks(self.log)
        desks = []
        for desk_id, manifest in sorted(self.manifests.items()):
            book = self.ledgers[desk_id].state(at)
            desks.append(
                {
                    "id": desk_id,
                    "mode": capital_mode(manifest, modes),
                    "status": self.desk_status(desk_id),
                    "equity": text(book.equity),
                    "cash": text(book.cash),
                    "daily_pnl": text(book.daily_pnl),
                    "return_pct": text(book.time_weighted_return_pct),
                    "decisions": book.decisions,
                    "days_live": book.days_live,
                    "open_orders": len(self.gateway.open_orders(desk_id)),
                }
            )
        spent = None
        if self.provider is not None:
            try:
                spent = text(money(self.provider.spent_today()))
            except Exception:
                spent = None
        return {
            "schema_version": 1,
            "status": "halted" if self.gateway.kill_switch_engaged() else "running",
            "updated_at": at,
            "root": str(self.root),
            "kill_switch": self.gateway.kill_switch_engaged(),
            "reconciliation_mismatch": self.gateway.reconciliation_mismatch,
            "blocked_desks": sorted(self.gateway.blocked_desks),
            "events": self.log.latest_seq(),
            "floor": {
                "equity": text(floor["equity"]),
                "cash": text(floor["cash"]),
                "daily_pnl": text(floor["daily_pnl"]),
                "net_deposits": text(floor["net_deposits"]),
            },
            "budget": {
                "spent_today_usd": spent,
                "cap_usd": str(self._budget.get("cap_usd", self.config["floor_cap_usd_per_day"])),
                "base_usd": str(self.config["floor_cap_usd_per_day"]),
                "trailing_realized_usd": str(self._budget.get("trailing_realized_usd", "0")),
            },
            "desks": desks,
            "last_mark_at": state.get("last_mark_at"),
            "last_committee_day": state.get("last_committee_day"),
            "last_evolution_day": state.get("last_evolution_day"),
            "last_error": self.last_error,
        }

    def health(self, at: str | None = None, tick: Mapping[str, Any] | None = None) -> dict[str, Any]:
        report = self.status(at)
        if tick is None:
            tick = self._last_tick
        else:
            self._last_tick = dict(tick)
        if tick is not None:
            report["last_tick"] = {
                "at": tick.get("at"),
                "sessions": list(tick.get("sessions") or []),
                "marked": tick.get("marked"),
                "breakers": list(tick.get("breakers") or []),
                "published": tick.get("published"),
            }
        tmp = self.health_path.with_name(self.health_path.name + f".tmp-{os.getpid()}")
        tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.health_path)
        return report

    # ------------------------------------------------------------------ operations
    def kill(self, reason: str = "manual") -> Path:
        self.kill_switch_path.parent.mkdir(parents=True, exist_ok=True)
        self.kill_switch_path.write_text(
            json.dumps({"engaged_at": self.now(), "reason": reason}) + "\n", encoding="utf-8"
        )
        self.alert("critical", f"kill switch engaged: {reason}")
        return self.kill_switch_path

    def unkill(self) -> bool:
        if not self.kill_switch_path.exists():
            return False
        self.kill_switch_path.unlink()
        self.alert("info", "kill switch released")
        return True

    def run(self, *, once: bool = False) -> dict[str, Any]:
        previous = {}
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.getsignal(sig)
                signal.signal(sig, lambda *_: setattr(self, "stopping", True))
        except ValueError:  # not the main thread
            previous = {}
        result: dict[str, Any] = {}
        try:
            while not self.stopping:
                try:
                    result = self.tick()
                    self.last_error = None
                except Exception as exc:
                    self.last_error = str(exc)
                    self.alert("critical", f"tick failed: {exc}")
                    self.health()
                if once or self.stopping:
                    break
                self.sleeper(float(self.config["sleep_seconds"]))
        finally:
            for sig, handler in previous.items():
                try:
                    signal.signal(sig, handler)
                except ValueError:
                    pass
            self.health()
        return result

    def close(self) -> None:
        for thread in self._sessions:
            thread.join(timeout=1.0)
        for broker in list(self.paper_brokers.values()) + list(self.brokers.values()):
            closer = getattr(broker, "close", None)
            if closer is not None:
                try:
                    closer()
                except Exception:
                    pass
        closer = getattr(self.provider, "close", None)
        if closer is not None:
            try:
                closer()
            except Exception:
                pass
        self.log.close()


class _PaperRouter:
    """One `Broker` face over the per-desk paper books.

    Each paper desk keeps its own simulator file so a bug in one desk cannot spend another's
    cash. The gateway routes by venue, so this router sends each order to the book that belongs
    to the desk named on the intent, and aggregates the reads.
    """

    venue = "paper"

    def __init__(self, brokers: Mapping[str, Any], manifests: Mapping[str, DeskManifest]):
        self.brokers = dict(brokers)
        self.manifests = dict(manifests)
        self._orders: dict[str, str] = {}

    def _for(self, desk_id: str) -> Any:
        broker = self.brokers.get(desk_id)
        if broker is None:
            raise KeyError(f"no paper book for desk {desk_id}")
        return broker

    def capabilities(self) -> set[str]:
        merged: set[str] = set()
        for broker in self.brokers.values():
            merged |= set(broker.capabilities())
        return merged

    def quote(self, instrument: Instrument):
        for broker in self.brokers.values():
            return broker.quote(instrument)
        return None

    def balance(self):
        for broker in self.brokers.values():
            return broker.balance()
        return None

    def positions(self) -> list[Any]:
        out: list[Any] = []
        for broker in self.brokers.values():
            out.extend(broker.positions())
        return out

    def submit(self, intent: OrderIntent):
        broker = self._for(intent.desk_id)
        order = broker.submit(intent)
        self._orders[order.id] = intent.desk_id
        return order

    def cancel(self, order_id: str):
        return self._route(order_id, "cancel", order_id)

    def get_order(self, order_id: str):
        return self._route(order_id, "get_order", order_id)

    def _route(self, order_id: str, method: str, *args: Any):
        desk_id = self._orders.get(order_id)
        if desk_id is not None:
            return getattr(self._for(desk_id), method)(*args)
        for broker in self.brokers.values():
            try:
                return getattr(broker, method)(*args)
            except Exception:
                continue
        raise KeyError(f"unknown order {order_id}")

    def open_orders(self) -> list[Any]:
        out: list[Any] = []
        for broker in self.brokers.values():
            out.extend(broker.open_orders())
        return out

    def fills(self, since: str | None = None) -> list[Any]:
        out: list[Any] = []
        for broker in self.brokers.values():
            out.extend(broker.fills(since))
        return out

    def tick(self) -> None:
        for broker in self.brokers.values():
            ticker = getattr(broker, "tick", None)
            if ticker is not None:
                ticker()
