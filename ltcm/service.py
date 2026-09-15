"""The always-on floor: one process that never sleeps through an open.

`Service.tick()` is the whole runtime in one method, and it is deliberately boring:

1. run any desk session whose cadence slot has come round in the desk's own timezone,
2. advance the shadow books and poll every live order,
3. mark every sub-ledger on the mark interval,
4. evaluate the circuit breakers and publish any that tripped,
5. run the committee on its weekday and the evolution loop on its daily slot,
6. push the event tape and the leaderboard checkpoint to the site,
7. write the health file the supervisor watches.

Everything with an external dependency -- the model provider, the shadow book, the live venue
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
from .analytics import ResultsLedger
from .committee import Committee, capital_mode, live_desks, promoted_desks, retired_desks
from .runway import Runway, assess as assess_runway
from .exits import ExitBook  # leap: exits
from .watch import NightWatch  # leap: watch
from .events import EventLog, canonical, now_iso
from .evolve import Evolution
from .gateway import Gateway
from .ledger import DeskLedger, floor_totals, iso_time, parse_iso
from .manifest import DeskManifest, load_all
from .publish import Publisher, account_block, checkpoint_body, jsonable
from .risk import RiskEngine, circuit_breakers

PACKAGE_DIR = Path(__file__).resolve().parent
ZERO = Decimal(0)

#: The gateway's routing key for a scored book. A shadow desk's orders go here and no further.
SHADOW_VENUE = "shadow"

#: How long a checkpoint will wait for *every* live venue to report its balance, in total. The
#: venues are read together, so one slow exchange costs this much and not a multiple of it.
VENUE_BALANCE_TIMEOUT = 3.0
#: How long a balance is reused before the venue is asked again. The floor publishes every tick;
#: an account balance does not move fast enough to be worth a request each time.
VENUE_BALANCE_TTL = 60.0
#: A `floor.mark` is appended at most this often, and only when the portfolio actually moved.
FLOOR_MARK_INTERVAL_SECONDS = 300
#: The order the owner reads their accounts in. Anything else follows, alphabetically.
VENUE_ORDER = ("kalshi", "coinbase", "alpaca")

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
    # The memo is written every day; capital is only resized on the committee's weekday.
    "committee_memo_daily": True,
    "evolution_time": "19:00",
    "postmortem_time": "21:30",
    # The live-order critic: a second model reads every real-money order the engine approved.
    "critic_enabled": True,
    "critic_profile": "glm_asap",
    # Research sources a desk may reach. Absent means enabled; set false to run without one.
    "sources": {},
    "profit_share": "0.25",
    "floor_cap_max_usd_per_day": "60",
    # Spend policy. "runway": no daily cap -- the Sail credit above a reserve is the limit, the
    # floor throttles when the runway is short and stops at the reserve (`ltcm.runway`).
    # "capped": the older fixed daily cap plus a share of realized profit.
    "spend_mode": "runway",
    "spend_policy": {},
    # How often the evolution loop tops families up with shadow variants, in seconds.
    "seed_interval_seconds": 3600,
    # leap: exits. The floor keeps every desk's stop, target and time stop (`ltcm/exits.py`).
    "exits": {"enabled": True, "check_seconds": 60, "retry_seconds": 300},
    # leap: watch. The night desk that wakes a desk on a trigger (`ltcm/watch.py`).
    "watch": {"enabled": True},
    "publish": True,
    "publish_token_env": "CAPITAL_PUBLISH_TOKEN",
    "shadow_slippage_bps": 5,
    # Venues the floor may actually send an order to. A desk whose venue is missing from this
    # list stays shadow however good its evidence is, and the committee says so in public.
    "live_venues": [],
    "venues": {
        "alpaca": {
            "paper": True,
            "key_id_env": "ALPACA_PAPER_KEY_ID",
            "secret_env": "ALPACA_PAPER_SECRET_KEY",
        },
        "kalshi": {
            "key_id_env": "KALSHI_KEY_ID",
            "private_key_path": ".data/ltcm/keys/kalshi.pem",
        },
        "coinbase": {
            "key_name_env": "COINBASE_KEY_NAME",
            "secret_env": "COINBASE_API_SECRET",
            "private_key_path": ".data/ltcm/keys/coinbase.pem",
        },
    },
}


def default_config() -> dict[str, Any]:
    """The packaged defaults, overlaid with `ltcm/config.json` when it exists."""
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


#: An `event_resolution` session fires at most this often per desk, however many markets
#: settle in one afternoon. The manifest caps orders; this caps the model spend behind them.
RESOLUTION_COOLDOWN_SECONDS = 1800
#: The runway policy's fields, carried from `ops.budget` into the checkpoint and the status.
RUNWAY_KEYS = (
    "mode", "balance_usd", "spendable_usd", "runway_days", "burn_usd_per_day", "reserve_usd",
    "desk_fuse_usd",
)


def _venue_rank(venue: str) -> tuple[int, str]:
    """Sort key: the owner's own reading order first, anything else alphabetically after it."""
    return (VENUE_ORDER.index(venue) if venue in VENUE_ORDER else len(VENUE_ORDER), venue)


def _clock_minutes(value: str) -> int:
    return int(value[:2]) * 60 + int(value[3:5])


#: An identifier safe to publish: the box id, the region and the host name come from the guest
#: environment, and one odd variable must not make the site refuse every checkpoint after it.
_TAG = re.compile(r"[^A-Za-z0-9._:\- ]")


def _tag(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = _TAG.sub("", value).strip()[:120]
    return cleaned or None


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
        """The desk's scored record, newest first: one row per resolved position.

        A `desk.outcome` is written when a market the desk held settles (see
        `Gateway.poll_settlements`), and carries the entry, the exit, the size, the realized
        P&L, how long it was held and the sentence the desk gave for the trade. This is what
        the prompt's "Recent outcomes" block and the post-mortem score, so a desk that has
        closed nothing yet sees an empty list rather than a list of its own open trades.
        """
        rows = [
            dict(event.payload)
            for event in self.service.log.read(
                stream=self.manifest.stream, kind="desk.outcome", limit=10_000
            )
        ]
        rows.reverse()
        return rows[: max(1, int(limit))]

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

        # Everything the floor writes lives here: events, provider records, memory, shadow
        # books, health and the kill switch. `.data/ltcm/keys/` holds the venue credentials.
        self.capital_dir = self.root / ".data" / "ltcm"
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
        #: desk_id -> its own scoring book. A shadow desk trades this and nothing else.
        self.shadow_books: dict[str, Any] = {}
        self._env: dict[str, str] | None = None
        self._started_at = float(clock())
        self._checkpoints = int(self.state().get("checkpoint_count") or 0)

        if self.market_data is None:
            self.market_data = self._build_market_data()
        self._build_brokers()
        if self.provider is None:
            self.provider = self._build_provider()
        if self.memory is None:
            self.memory = self._build_memory()

        self.risk_engine = risk_engine or RiskEngine()
        self.critic = self._build_critic()
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
            critic=self.critic,
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
                "memo_daily": bool(self.config.get("committee_memo_daily", True)),
            },
        )
        self.evolution = Evolution(
            self.log,
            self.desks_dir,
            self.playbooks_dir,
            provider=self.provider,
            clock=clock,
            config={
                **(self.config.get("evolution") or {}),
                "live_venues": tuple(self.config.get("live_venues") or ()),
            },
        )
        self.publisher = publisher if publisher is not None else self._build_publisher()
        # leap: exits. The floor holds every desk's exit plan and enforces it every tick.
        exits_config = dict(self.config.get("exits") or {})
        self.exits: ExitBook | None = None
        if exits_config.get("enabled", True):
            self.exits = ExitBook(
                self.log,
                self.gateway,
                self.ledgers,
                self.manifests,
                quote=self.quote,
                clock=clock,
                check_seconds=int(exits_config.get("check_seconds", 60)),
                retry_seconds=int(exits_config.get("retry_seconds", 300)),
                alert=self.alert,
            )
            self.gateway.exits = self.exits
        # leap: watch. The night desk.
        watch_config = dict(self.config.get("watch") or {})
        self.watch: NightWatch | None = (
            NightWatch(self, watch_config) if watch_config.get("enabled", True) else None
        )

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
        (self.capital_dir / "shadow").mkdir(parents=True, exist_ok=True)
        modes = promoted_desks(self.log)
        for desk_id, manifest in sorted(self.manifests.items()):
            if capital_mode(manifest, modes) == "live":
                continue
            broker = self._make_shadow_book(manifest, self.book_path(desk_id))
            if broker is not None:
                self.shadow_books[desk_id] = broker
        for venue in self.config.get("live_venues") or []:
            broker = self._make_live_broker(venue)
            if broker is not None:
                self.brokers[venue] = broker
        # Every shadow desk routes to the one "shadow" key; the router hands each desk its own
        # book, so a bug in one desk's scoring can never touch another's.
        if self.shadow_books:
            self.brokers.setdefault(
                SHADOW_VENUE, _ShadowRouter(self.shadow_books, self.manifests)
            )
        for desk_id, manifest in sorted(self.manifests.items()):
            if capital_mode(manifest, modes) == "live" and manifest.market_venue not in self.brokers:
                self.alert(
                    "critical",
                    f"{desk_id} is live on {manifest.market_venue}, which has no broker",
                )

    def book_path(self, desk_id: str) -> Path:
        """Where one desk's scoring book lives.

        The directory was called `paper/` before the floor dropped the word. A desk that already
        has a book there keeps it: the file holds the positions and cash its ledger was folded
        from, and starting it over would put the two out of step for a rename.
        """
        current = self.capital_dir / "shadow" / f"{desk_id}.sqlite"
        legacy = self.capital_dir / "paper" / f"{desk_id}.sqlite"
        if not current.exists() and legacy.exists():
            return legacy
        return current

    def _make_shadow_book(self, manifest: DeskManifest, path: Path) -> Any:
        """One desk's scoring book, priced and charged like the venue it would trade on."""
        if self.broker_factory is not None:
            return self.broker_factory(
                SHADOW_VENUE, manifest=manifest, path=path, service=self
            )
        try:
            from . import sim
        except Exception:
            return None
        try:
            return sim.ShadowBook(
                path,
                venue=SHADOW_VENUE,
                market_venue=manifest.market_venue,
                data=self.market_data,
                clock=self.clock,
                initial_cash=manifest.capital_usd,
                slippage_bps=int(
                    self.config.get("shadow_slippage_bps")
                    or self.config.get("paper_slippage_bps")
                    or 5
                ),
                allow_short=manifest.instruments.allow_short,
            )
        except Exception as exc:
            self.alert("warning", f"shadow book for {manifest.id} unavailable: {exc}")
            return None

    def _make_live_broker(self, venue: str) -> Any:
        """Build a live venue adapter from configured env names and key files. Never logs secrets.

        With `gateway_url` set, Kalshi and Coinbase are built in **gateway mode** instead: the
        adapter is the same, but it signs nothing and reaches the venue only through the order
        gateway, which holds the private keys and enforces the caps and the kill switch outside
        this process. Nothing here ever reads a key file in that mode, because there is none.
        """
        settings = (self.config.get("venues") or {}).get(venue) or {}
        if self.broker_factory is not None:
            return self.broker_factory(venue, settings=settings, service=self)
        gateway_url = self.config.get("gateway_url")
        if gateway_url and venue in ("kalshi", "coinbase"):
            try:
                from .adapters import (
                    CoinbaseCredentials,
                    GatewaySigner,
                    KalshiCredentials,
                    VenueClient,
                    coinbase,
                    kalshi,
                )

                token = self.secret(self.config.get("gateway_token_env") or "GATEWAY_TOKEN")
                if not token:
                    raise RuntimeError("missing gateway token")
                client = VenueClient(
                    self.transport, gateway_url=str(gateway_url), gateway=GatewaySigner(token), venue=venue
                )
                # The key id belongs to the gateway, not to this process: it is part of the
                # credential, and a machine that cannot sign has no use for the name of the key.
                if venue == "kalshi":
                    return kalshi.KalshiBroker(
                        KalshiCredentials("gateway", GatewaySigner(token)), client=client, clock=self.clock
                    )
                broker = coinbase.CoinbaseBroker(
                    CoinbaseCredentials("gateway", GatewaySigner(token)), client=client, clock=self.clock
                )

                def reference_price(product_id: Any) -> Any:
                    """The desk's own quote, so the gateway can price an order against the caps."""
                    if not product_id:
                        return None
                    from .broker import Instrument

                    name = str(product_id)
                    try:
                        found = broker.market_data.quote(
                            Instrument("crypto", name, venue, market_id=name)
                        )
                    except Exception:
                        return None
                    return found.mid if found.mid is not None else found.last

                client.reference_price = reference_price
                return broker
            except Exception as exc:
                self.alert("warning", f"live venue {venue} not enabled: {type(exc).__name__}")
                return None
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

    def _build_critic(self) -> Any:
        """The live-order critic, unless this deployment switched it off or has no provider."""
        try:
            from . import critic as critic_module
        except Exception:  # pragma: no cover - the module is part of the package
            return None
        try:
            return critic_module.build(self.provider, self.config)
        except Exception as exc:
            self.alert("warning", f"live-order critic unavailable: {exc}")
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
            broker = self._make_shadow_book(manifest, self.book_path(manifest.id))
            if broker is not None:
                self.shadow_books[manifest.id] = broker
                self.brokers.setdefault(
                    SHADOW_VENUE, _ShadowRouter(self.shadow_books, self.manifests)
                )
                router = self.brokers.get(SHADOW_VENUE)
                if isinstance(router, _ShadowRouter):
                    router.add(manifest.id, broker)

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

    def last_session_at(self, manifest: DeskManifest, trigger: str | None = None) -> str | None:
        """When this desk last opened a session, for any trigger or for one named trigger."""
        latest: str | None = None
        for event in self.log.read(
            stream=manifest.stream, kind="desk.session_started", limit=10_000
        ):
            if trigger is not None and event.payload.get("trigger") != trigger:
                continue
            if latest is None or event.at > latest:
                latest = event.at
        return latest

    def resolution_due(self, manifest: DeskManifest, at: str) -> bool:
        """True when an outcome this desk has not sat down with has appeared.

        A settled market is the only forward result the floor gets, so a desk that declares the
        `event_resolution` trigger is woken by a new `desk.outcome` on its own stream rather
        than by the clock -- markets resolve on weekends too, so `weekdays_only` does not gate
        this arm. A busy settlement afternoon could otherwise burn the desk's daily model
        budget in an hour, so the trigger fires at most once every thirty minutes per desk.
        """
        if "event_resolution" not in manifest.cadence.triggers:
            return False
        since = self.last_session_at(manifest)
        outcomes = [
            event
            for event in self.log.read(stream=manifest.stream, kind="desk.outcome", limit=10_000)
            if since is None or event.at > since
        ]
        if not outcomes:
            return False
        last_resolution = self.last_session_at(manifest, "event_resolution")
        if last_resolution is not None:
            elapsed = (parse_iso(at) - parse_iso(last_resolution)).total_seconds()
            if elapsed < RESOLUTION_COOLDOWN_SECONDS:
                return False
        return True

    def due_sessions(self, at: str) -> list[tuple[DeskManifest, str]]:
        """(manifest, trigger) for every session that has come due and not run.

        Triggers are `cadence:HH:MM` for a scheduled slot, `postmortem` for the daily review,
        and `event_resolution` when a market the desk held has settled since it last sat down
        -- all three inside the desk runtime's trigger grammar.
        """
        due: list[tuple[DeskManifest, str]] = []
        catchup = int(self.config["session_catchup_seconds"])
        postmortem_at = _clock_minutes(str(self.config["postmortem_time"]))
        for desk_id, manifest in sorted(self.active_manifests().items()):
            tz = ZoneInfo(manifest.cadence.timezone)
            local = parse_iso(at).astimezone(tz)
            if self.resolution_due(manifest, at):
                due.append((manifest, "event_resolution"))
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
                if self.interrupted_session(manifest, trigger, day, at) is not None:
                    due.append((manifest, trigger))
                    continue
                if (minutes_now - minutes_slot) * 60 > catchup:
                    continue
                if self.ran_today(manifest, trigger, day):
                    continue
                due.append((manifest, trigger))
        return due

    def interrupted_session(
        self, manifest: DeskManifest, trigger: str, day: str, at: str
    ) -> Any | None:
        """The one session this slot started today that never ended, if it is worth retrying.

        Sessions run to completion inside the tick, so a `desk.session_started` with no
        `desk.session_ended` was cut short from outside: a restart into new code, a Sailbox
        resume, the watchdog, an operator stop. The floor is meant never to stop working, so
        such a slot is sat down again -- once, and only within the catch-up window measured
        from the interrupted start, so a box that was asleep all afternoon does not wake up
        and replay the morning. A second start for the slot, ended or not, closes the matter:
        a session that dies twice is a bug to read about, not a loop to spin.
        """
        if any(
            thread.is_alive() and thread.name == f"session-{manifest.id}-{trigger}"
            for thread in self._sessions
        ):
            return None  # still running here; not interrupted, just slow
        tz = ZoneInfo(manifest.cadence.timezone)
        started = [
            event
            for event in self.log.read(stream=manifest.stream, kind="desk.session_started", limit=5000)
            if event.payload.get("trigger") == trigger
            and parse_iso(event.at).astimezone(tz).date().isoformat() == day
        ]
        if len(started) != 1:
            return None
        only = started[0]
        session_id = only.payload.get("session_id")
        for event in self.log.read(stream=manifest.stream, kind="desk.session_ended", limit=5000):
            if event.payload.get("session_id") == session_id:
                return None
        catchup = int(self.config["session_catchup_seconds"])
        if (parse_iso(at) - parse_iso(only.at)).total_seconds() > catchup:
            return None
        return only

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
        """Set what the desks may spend today and publish it.

        Under the runway policy (the default) there is no daily cap: the Sail credit above the
        reserve is the limit, read live, and the policy only decides how the floor approaches
        zero. Under the capped policy the cap is a base plus a share of realized profit.
        """
        if str(self.config.get("spend_mode", "runway")) == "runway":
            return self._apply_runway(at)
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

    def _apply_runway(self, at: str) -> dict[str, Any]:
        provider = self.provider
        balance = None
        burn = ZERO
        spent = ZERO
        if provider is not None:
            reader = getattr(provider, "check_balance", None)
            if callable(reader):
                try:
                    balance = reader()
                except Exception:
                    balance = None
            trailing = getattr(provider, "spent_since", None)
            if callable(trailing):
                try:
                    burn = money(trailing(24.0))
                except Exception:
                    burn = ZERO
            try:
                spent = money(provider.spent_today())
            except Exception:
                spent = ZERO
        runway = assess_runway(balance, burn, self.config.get("spend_policy") or {})
        if provider is not None:
            if hasattr(provider, "floor_cap"):
                provider.floor_cap = runway.cap_usd
            if hasattr(provider, "desk_fuse"):
                provider.desk_fuse = runway.desk_fuse_usd
        payload = {"scope": "floor", "spent_usd": text(spent), **runway.to_payload()}
        # One public event per change of picture: the mode, the cap and the runway to the
        # dollar and the day, not one event per cent the balance moves.
        coarse = {
            "mode": runway.mode,
            "cap": str(int(runway.cap_usd)),
            "balance": None if runway.balance_usd is None else str(int(runway.balance_usd)),
            "runway": None if runway.runway_days is None else str(int(runway.runway_days)),
        }
        digest = hashlib.sha256(canonical(coarse).encode("utf-8")).hexdigest()[:12]
        self.log.append(
            "ops", "ops.budget", payload, id=f"budget:floor:{at[:10]}:{digest}", at=at
        )
        self._note_spend_mode(runway, at)
        self._runway = runway
        self._budget = {
            "scope": "floor",
            "cap_usd": runway.cap_usd,
            "spent_today_usd": spent,
            "base_usd": ZERO,
            "profit_share": ZERO,
            "trailing_realized_usd": ZERO,
            "profit_window_days": 0,
            **runway.to_payload(),
        }
        return self._budget

    def _note_spend_mode(self, runway: Runway, at: str) -> None:
        """Say in public when the floor's posture toward its credit changes."""
        previous = self.state().get("spend_mode_seen")
        if previous == runway.mode:
            return
        self._save_state(spend_mode_seen=runway.mode)
        balance = "unread" if runway.balance_usd is None else f"${runway.balance_usd}"
        days = "" if runway.runway_days is None else f"{runway.runway_days} days"
        if runway.mode == "stopped":
            self.alert(
                "critical",
                f"floor paused: Sail credit {balance} is at the ${runway.reserve_usd} reserve. "
                "No new session starts; marks, settlements and publication continue. "
                "Credit added at Sail resumes the floor within a minute.",
            )
        elif runway.mode == "throttled":
            self.alert(
                "warning",
                f"floor throttled: {days} of Sail credit left at ${runway.burn_usd_per_day} a day. "
                f"Live desks only, ${runway.cap_usd} a day, until credit is added.",
            )
        elif runway.mode == "unknown":
            self.alert(
                "warning",
                "Sail balance could not be read; the floor keeps working under the fallback cap "
                f"of ${runway.cap_usd} a day.",
            )
        elif previous is not None:
            self.alert(
                "info",
                f"floor open: Sail credit {balance}, {days} of runway at "
                f"${runway.burn_usd_per_day} a day. No daily cap.",
            )

    def spend_mode(self) -> str:
        """`open`, `throttled`, `stopped` or `unknown` under the runway policy; `capped` otherwise."""
        runway = getattr(self, "_runway", None)
        return runway.mode if runway is not None else "capped"

    def seed_population(self, at: str) -> list[dict[str, Any]]:
        """Top families up with shadow variants, a couple at a time, at most once per interval.

        Each spawn asks the model for a playbook, so a pass is bounded to `seed_batch` children
        to keep the tick short; the next pass, an interval later, tops the family up further.
        It runs on the tick's own thread: the roster, the ledgers and the event log are all
        touched here, and none of them is meant to be shared with a second thread.
        """
        interval = int(self.config.get("seed_interval_seconds", 3600))
        last = self.state().get("last_seed_at")
        if last is not None and (parse_iso(at) - parse_iso(last)).total_seconds() < interval:
            return []
        self._save_state(last_seed_at=at)
        batch = max(1, int(self.config.get("seed_batch", 2)))
        try:
            actions = list(self.evolution.seed(at, limit=batch))
        except Exception as exc:
            self.alert("warning", f"seeding failed: {type(exc).__name__}: {exc}")
            return []
        if actions:
            self.reload_manifests()
        return actions

    # ------------------------------------------------------------------ marks
    def mark_all(self, at: str) -> int:
        """Value every funded sleeve. A desk with no capital and no book is not marked: its
        clock starts when the committee funds it, not when the process does.

        A shadow desk's mark is written with `shadow: true`, so nothing downstream can mistake
        a scored book for money.
        """
        marked = 0
        live = self.live_ids()
        for desk_id, ledger in sorted(self.ledgers.items()):
            state = ledger.state(at)
            if state.net_deposits <= ZERO and not state.positions:
                continue
            quotes: dict[str, Any] = {}
            for key, position in state.positions.items():
                found = self.quote(position.instrument)
                if found is not None:
                    quotes[key] = found
            ledger.mark(quotes, at, shadow=desk_id not in live)
            marked += 1
        return marked

    def live_ids(self) -> set[str]:
        """The desks on real capital, promotions included. The floor's book is these and no more."""
        return live_desks(self.manifests, promoted_desks(self.log))

    def breakers(self, at: str) -> list[dict[str, Any]]:
        # The floor's daily loss limit is about real money, so a shadow book cannot trip it.
        floor = floor_totals(self.ledgers, at, include=self.live_ids())
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
            "memo": False,
            "evolution": [],
            "published": None,
            "budget": None,
            "settlements": [],
            "rate_card": None,
            "kill_switch": self.gateway.kill_switch_engaged(),
            "exits": [],  # leap: exits
            "watch": [],  # leap: watch
        }

        result["budget"] = {k: str(v) for k, v in self.apply_budget(at).items()}
        runway = getattr(self, "_runway", None)
        stopped = runway is not None and runway.mode == "stopped"
        live_only = runway is not None and runway.live_only
        result["spend_mode"] = self.spend_mode()
        # Settlements are swept before the schedule so a market that resolved since the last
        # tick wakes its desk on this tick rather than the next one.
        result["settlements"] = self.sweep_settlements(at)
        # A desk that has never been funded, or a roster change, gets an allocation right away, before any
        # session starts, so a desk never sees an unfunded book;
        # the weekly resize by track record still only happens on the committee's day.
        previous, _ = self.committee.last_allocation()
        if any(desk_id not in previous for desk_id in self.manifests):
            self.committee.allocate(at)
            result["committee"] = True
        if not result["kill_switch"] and not stopped:
            due = self.due_sessions(at)
            if live_only:
                # Short runway: the shadow race pauses and the credit goes to the real sleeves.
                live = self.live_ids()
                due = [(m, trigger) for m, trigger in due if m.id in live]
            self.start_sessions(due)
            result["sessions"] = [f"{m.id}/{trigger}" for m, trigger in due]

        for broker in self.shadow_books.values():
            ticker = getattr(broker, "tick", None)
            if ticker is not None:
                try:
                    ticker()
                except Exception as exc:
                    self.alert("warning", f"shadow book tick failed: {exc}")
        try:
            result["orders"] = [row["order_id"] for row in self.gateway.poll_orders(at)]
        except Exception as exc:
            self.alert("warning", f"order poll failed: {exc}")
        # leap: exits. Stops, targets and time stops are the floor's to keep, every tick,
        # whether or not the desk is in session. The kill switch refuses every order, exits
        # included, so nothing is filed while it is engaged.
        if self.exits is not None and not result["kill_switch"]:
            try:
                result["exits"] = self.exits.tick(at)
            except Exception as exc:
                self.alert("warning", f"exit enforcement failed: {type(exc).__name__}: {exc}")

        interval = int(self.config["mark_interval_seconds"])
        last_mark = state.get("last_mark_at")
        if last_mark is None or (parse_iso(at) - parse_iso(last_mark)).total_seconds() >= interval:
            result["marked"] = self.mark_all(at)
            result["breakers"] = self.breakers(at)
            self._save_state(last_mark_at=at)

        # leap: watch. The night desk looks after the marks are fresh; it costs nothing
        # until something happens, and it is quiet when the floor has stopped for credit.
        if self.watch is not None and not result["kill_switch"] and not stopped:
            try:
                result["watch"] = self.watch.tick(at, allow_shadow=not live_only)
            except Exception as exc:
                self.alert("warning", f"night watch failed: {type(exc).__name__}: {exc}")

        # Keep the event-contract index warm so a desk's first search does not wait on a sweep.
        if any("event" in m.instruments.asset_classes for m in self.manifests.values()):
            source = self.source("event")
            if source is not None:
                try:
                    self.event_index(source)
                except Exception as exc:
                    self.alert("warning", f"event index warm-up failed: {type(exc).__name__}")

        day = local.date().isoformat()
        if state.get("last_rate_card_day") != day:
            result["rate_card"] = self.check_rate_card()
            self._save_state(last_rate_card_day=day)
        if not stopped and not live_only:
            seeded = self.seed_population(at)
            if seeded:
                result["evolution"] = list(result.get("evolution") or []) + seeded
        if stopped:
            pass  # the memo and the evolution loop both ask the model; they wait for credit
        elif self._due(local, self.config["committee_time"], state.get("last_committee_day"), day):
            # Meriwether writes every day; capital is only resized on the committee's weekday.
            resize_day = local.weekday() == int(self.config["committee_weekday"])
            memo_daily = bool(self.config.get("committee_memo_daily", True))
            if resize_day:
                self.committee.allocate(at)
                result["committee"] = True
            if resize_day or memo_daily:
                result["memo"] = bool(self.committee.memo(at))
                self._save_state(last_committee_day=day)
        if not stopped and self._due(local, self.config["evolution_time"], state.get("last_evolution_day"), day):
            actions = list(self.evolution.select(at)) + list(self.evolution.promote(at))
            self.reload_manifests()
            self._save_state(last_evolution_day=day)
            result["evolution"] = actions

        try:
            event = ResultsLedger.publish_daily(self.log, at, manifests=self.manifests)
            result["lab"] = None if event is None else event.id
        except Exception as exc:  # a scoreboard may never stop the floor
            self.alert("warning", f"lab result failed: {type(exc).__name__}")
        result["published"] = self.publish()
        self.health(at, result)
        return result

    def sweep_settlements(self, at: str) -> list[str]:
        """Close resolved event markets on every venue that reports settlements.

        Returns the fill ids written. A venue with no settlement endpoint, or a sweep that
        fails, is a no-op: nothing here may stop the rest of the tick.
        """
        written: list[str] = []
        for venue in sorted(self.gateway.brokers):
            broker = self.gateway.brokers[venue]
            if getattr(broker, "settlements", None) is None:
                continue
            try:
                written.extend(
                    row["fill_id"] for row in self.gateway.poll_settlements(venue, at)
                )
            except Exception as exc:
                self.alert("warning", f"settlement sweep on {venue} failed: {exc}")
        return written

    def check_rate_card(self) -> dict[str, Any] | None:
        """Ask the provider to diff its frozen price list against Sail's published one.

        Once a day, and quiet: a provider without the check, or a check that cannot reach the
        docs, reports nothing. Drift is an `ops.alert`, never an edit to `PROFILES`.
        """
        checker = getattr(self.provider, "rate_card_check", None)
        if checker is None:
            return None
        try:
            return checker()
        except Exception as exc:
            self.alert("warning", f"rate card check failed: {type(exc).__name__}: {exc}")
            return None

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
            self._checkpoints += 1
            self._save_state(checkpoint_count=self._checkpoints)
            return summary
        except Exception as exc:
            self.last_error = f"publish: {exc}"
            self.alert("warning", f"publish failed: {exc}")
            return None

    # ------------------------------------------------- the owner's real account balances
    def venue_brokers(self) -> dict[str, Any]:
        """The live venues this box can ask for a balance. The shadow router is not one of them."""
        found = {
            venue: broker
            for venue, broker in self.brokers.items()
            if venue != SHADOW_VENUE and hasattr(broker, "balance")
        }
        return {venue: found[venue] for venue in sorted(found, key=_venue_rank)}

    def _read_balances(self, brokers: Mapping[str, Any], timeout: float) -> dict[str, Any]:
        """Ask every venue at once and give up on the slow ones. Never raises and never blocks
        longer than `timeout` however many venues there are: a checkpoint is a report, and a
        report that waits on an exchange is a report that does not get written."""
        answers: dict[str, Any] = {}
        threads: list[threading.Thread] = []
        for venue, broker in brokers.items():
            def read(venue: str = venue, broker: Any = broker) -> None:
                try:
                    answers[venue] = broker.balance()
                except Exception:
                    answers[venue] = None

            thread = threading.Thread(target=read, name=f"balance-{venue}", daemon=True)
            thread.start()
            threads.append(thread)
        deadline = time.monotonic() + max(0.0, float(timeout))
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        return answers

    def venue_balances(self) -> list[dict[str, Any]]:
        """Each live venue's account balance, cached for `VENUE_BALANCE_TTL` seconds.

        A venue that fails or does not answer in time keeps its last known numbers and is marked
        `stale`; a venue that has never answered is simply absent, because publishing a zero for
        an account nobody could read would look exactly like an account that lost everything.
        """
        cache = getattr(self, "_venue_balances", None)
        if cache is None:
            cache = self._venue_balances = {}
        brokers = self.venue_brokers()
        now = float(self.clock())
        due = {
            venue: broker
            for venue, broker in brokers.items()
            if now - float((cache.get(venue) or {}).get("read_at", 0.0)) >= VENUE_BALANCE_TTL
        }
        answers = self._read_balances(due, VENUE_BALANCE_TIMEOUT) if due else {}
        rows: list[dict[str, Any]] = []
        for venue in brokers:
            cached = cache.get(venue)
            if venue not in due and cached is not None:
                rows.append(dict(cached["row"]))
                continue
            row = self._balance_row(venue, answers.get(venue))
            if row is None:
                if cached is None:
                    continue
                rows.append({**cached["row"], "stale": True})
                # Said once, when the venue stops answering. A checkpoint every half minute
                # must not turn one outage into a wall of identical alerts.
                if not cached.get("stale"):
                    cached["stale"] = True
                    self.alert("warning", f"{venue} balance is stale: the venue did not answer")
                continue
            cache[venue] = {"read_at": now, "row": row, "stale": False}
            rows.append(dict(row))
        return rows

    def _balance_row(self, venue: str, balance: Any) -> dict[str, Any] | None:
        """One venue's answer as a row, or None when it did not answer with usable money."""
        if balance is None:
            return None
        try:
            return {
                "venue": venue,
                "equity": money(getattr(balance, "equity", 0)),
                "cash": money(getattr(balance, "cash", 0)),
                "as_of": getattr(balance, "as_of", None) or self.now(),
            }
        except (ValueError, ArithmeticError, TypeError):
            return None

    def account(self, at: str) -> dict[str, Any]:
        """The portfolio the owner sees: Kalshi plus Coinbase (plus Alpaca when it is live),
        summed. Empty when no venue has ever answered."""
        return account_block(self.venue_balances(), at)

    def floor_mark(self, account: Mapping[str, Any], at: str) -> Any:
        """Append the floor's own balance mark, the way a desk appends `ledger.mark`.

        This is the series the site draws the real balance history from, so it is written at most
        once every five minutes and only when the portfolio actually moved: a tape full of
        identical marks is a chart that says nothing.
        """
        if not account:
            return None
        payload = jsonable(
            {
                "account_equity": account["account_equity"],
                "account_cash": account["account_cash"],
                "venues": account["venues"],
                "as_of": at,
            }
        )
        last = self.log.last("ops", "floor.mark")
        if last is not None:
            if payload["account_equity"] == last.payload.get("account_equity"):
                return None
            previous = last.payload.get("as_of") or last.at
            try:
                elapsed = (parse_iso(at) - parse_iso(str(previous))).total_seconds()
            except (TypeError, ValueError):
                elapsed = FLOOR_MARK_INTERVAL_SECONDS
            if elapsed < FLOOR_MARK_INTERVAL_SECONDS:
                return None
        try:
            return self.log.append("ops", "floor.mark", payload, id=f"floor.mark:{at}", at=at)
        except Exception as exc:
            self.alert("warning", f"floor mark not recorded: {exc}")
            return None

    # ------------------------------------------------------------------ projections
    def checkpoint(self, at: str | None = None) -> dict[str, Any]:
        at = at or self.now()
        modes = promoted_desks(self.log)
        retired = retired_desks(self.log)
        allocations, _ = self.committee.last_allocation()
        live = live_desks(self.manifests, modes)
        # Two floors, and only one of them is money. `floor` is every sleeve the floor really
        # owns; the shadow books are counted, never added.
        floor = floor_totals(self.ledgers, at, include=live)
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
            if desk_id in live and state.net_deposits > 0:
                # Since-inception is the floor's own return, so a hypothetical book cannot move it.
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
                    # leap: exits. What the desk holds and why, with the exit plan on each.
                    "positions": self.desk_positions(desk_id, at),
                    # leap: watch. The session running right now, if one is.
                    "live_session": self.live_session(desk_id),
                }
            )
        shadow_count = sum(1 for desk_id in self.manifests if desk_id not in live and desk_id not in retired)
        memo = self.log.last("committee", "committee.memo")
        budget = self._budget or self.committee.compute_budget(at)
        spent = budget.get("spent_today_usd")
        if spent is None and self.provider is not None:
            try:
                spent = money(self.provider.spent_today())
            except Exception:
                spent = ZERO
        funded = sum(
            (amount for desk_id, amount in allocations.items() if desk_id in live), ZERO
        )
        # The venue accounts, and the floor's own mark of them. The read is cached and bounded,
        # so a checkpoint costs at most one short request per venue per minute.
        account = self.account(at)
        self.floor_mark(account, at)
        return checkpoint_body(
            published_at=at,
            floor={
                **account,
                "equity": floor["equity"],
                "cash": floor["cash"],
                "daily_pnl": floor["daily_pnl"],
                "capital_usd": funded or floor["net_deposits"],
                "since_inception_pct": (weighted / weights) if weights > 0 else ZERO,
                "benchmark": None,
                # Named so the site cannot accidentally render a shadow book as the floor's money.
                "live_equity": floor["equity"],
                "live_daily_pnl": floor["daily_pnl"],
                "live_desks": len(live),
                "shadow_desks": shadow_count,
            },
            desks=desks,
            committee={
                "last_memo_at": memo.at if memo else None,
                "allocations": {k: text(v) for k, v in sorted(allocations.items())},
            },
            budget={
                "spent_today_usd": spent if spent is not None else ZERO,
                "cap_usd": money(budget["cap_usd"]),
                "base_usd": money(budget.get("base_usd", ZERO)),
                "profit_share": money(budget.get("profit_share", ZERO)),
                "trailing_realized_usd": money(budget.get("trailing_realized_usd", ZERO)),
                **{k: budget.get(k) for k in RUNWAY_KEYS if k in budget},
            },
            infra=self.infra(at, spend_usd=spent if spent is not None else ZERO),
            watch=self.watch.summary(at) if self.watch is not None else None,  # leap: watch
        )

    # ------------------------------------------------------------------ leap: exits
    def opening_intent(self, desk_id: str, key: str) -> dict[str, Any] | None:
        """The newest entry intent this desk proposed on that instrument, as published."""
        manifest = self.manifests.get(desk_id)
        stream = manifest.stream if manifest is not None else f"desk:{desk_id}"
        found: dict[str, Any] | None = None
        for event in self.log.read(stream=stream, kind="desk.intent", limit=10_000):
            payload = event.payload
            if payload.get("purpose") == "exit":
                continue
            instrument = payload.get("instrument")
            if not isinstance(instrument, Mapping):
                continue
            try:
                if Instrument.from_dict(dict(instrument)).key != key:
                    continue
            except Exception:
                continue
            found = dict(payload)
        return found

    def desk_positions(self, desk_id: str, at: str) -> list[dict[str, Any]]:
        """The positions board's rows for one desk: every open position with its mark, its
        P&L, the sentence the desk gave for it and the exit plan the floor holds against it."""
        ledger = self.ledgers.get(desk_id)
        if ledger is None:
            return []
        try:
            state = ledger.state(at)
        except Exception:
            return []
        rows: list[dict[str, Any]] = []
        for key, position in sorted(state.positions.items()):
            quantity = money(position.quantity)
            if quantity == 0:
                continue
            instrument = position.instrument
            right = str(instrument.right or "").lower()
            side = right if right in ("yes", "no") else ("long" if quantity > 0 else "short")
            mark = position.mark
            if mark is None:
                found = self.quote(instrument)
                if found is not None:
                    mark = getattr(found, "mid", None) or getattr(found, "last", None)
            size = abs(quantity)
            entry = money(position.average_cost)
            value = size * money(mark) * instrument.multiplier if mark is not None else size * entry * instrument.multiplier
            pnl = position.unrealized_pnl if mark is not None else ZERO
            if mark is not None and position.mark is None:
                pnl = (money(mark) - entry) * quantity * instrument.multiplier
            intent = self.opening_intent(desk_id, key) or {}
            opened_at, _ = self.gateway.entry_of(desk_id, key)
            plan = self.exits.plan_for_position(desk_id, key) if self.exits is not None else None
            rationale = str(intent.get("rationale") or "").strip()
            rows.append(
                {
                    "instrument": instrument.to_dict(),
                    "side": side,
                    "quantity": size,
                    "entry_price": entry,
                    "mark_price": money(mark) if mark is not None else entry,
                    "market_value": money(value),
                    "unrealized_pnl": money(pnl if pnl is not None else ZERO),
                    "opened_at": opened_at or state.started_at or at,
                    "thesis": rationale[:240],
                    "intent_id": intent.get("intent_id"),
                    "session_id": intent.get("session_id"),
                    "target_price": plan.target_price if plan is not None else None,
                    "stop_price": plan.stop_price if plan is not None else None,
                    "time_stop_at": plan.time_stop_at if plan is not None else None,
                    "exit_orders": self.exits.exit_orders(plan) if (plan is not None and self.exits is not None) else [],
                }
            )
            if len(rows) >= 50:
                break
        return rows

    # ------------------------------------------------------------------ leap: watch
    def live_session(self, desk_id: str) -> dict[str, Any] | None:
        """The session running for this desk right now: the newest start with no end, on a
        thread that is still alive. A start with no end on a dead thread was cut short."""
        manifest = self.manifests.get(desk_id)
        stream = manifest.stream if manifest is not None else f"desk:{desk_id}"
        started = self.log.last(stream, "desk.session_started")
        if started is None:
            return None
        session_id = started.payload.get("session_id")
        for event in self.log.read(stream=stream, kind="desk.session_ended", after=started.seq, limit=200):
            if event.payload.get("session_id") == session_id:
                return None
        if not any(t.is_alive() and t.name.startswith(f"session-{desk_id}-") for t in self._sessions):
            return None
        return {
            "session_id": session_id,
            "trigger": started.payload.get("trigger"),
            "started_at": started.at,
        }

    # ------------------------------------------------------------------ the box
    def infra(self, at: str, *, spend_usd: Any = ZERO) -> dict[str, Any]:
        """Where the floor is running, and what it has cost to run it today.

        `ltcm.hostinfo.describe_host()` owns the facts about the box. It is imported lazily and
        every failure degrades to `{"host": "local"}`: the floor publishes its numbers whether
        or not it can say which machine produced them.
        """
        described: dict[str, Any] = {}
        try:
            from . import hostinfo  # type: ignore[attr-defined]

            found = hostinfo.describe_host()
            if isinstance(found, Mapping):
                described = dict(found)
        except Exception:
            described = {}
        uptime = described.get("uptime_seconds")
        if not isinstance(uptime, (int, float)) or isinstance(uptime, bool):
            uptime = max(0, int(float(self.clock()) - self._started_at))
        checkpoints = described.get("checkpoint_count")
        if not isinstance(checkpoints, int) or isinstance(checkpoints, bool):
            checkpoints = self._checkpoints
        spend = described.get("spend_usd")
        if spend is None:
            spend = spend_usd
        return {
            "host": _tag(described.get("host")) or "local",
            "box_id": _tag(described.get("box_id")),
            "checkpoint_count": int(checkpoints),
            "spend_usd": money(spend),
            "uptime_seconds": int(uptime),
            "region": _tag(described.get("region")),
            "requests_today": described.get("requests_today"),
        }

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
        live = self.live_ids()
        floor = floor_totals(self.ledgers, at, include=live)
        shadow_floor = floor_totals(self.ledgers, at, include=set(self.ledgers) - live)
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
                "live_desks": len(live),
                "shadow_desks": len(self.ledgers) - len(live),
                "shadow_equity": text(shadow_floor["equity"]),
            },
            "budget": {
                "spent_today_usd": spent,
                "cap_usd": str(self._budget.get("cap_usd", self.config["floor_cap_usd_per_day"])),
                "base_usd": str(self.config["floor_cap_usd_per_day"]),
                "trailing_realized_usd": str(self._budget.get("trailing_realized_usd", "0")),
                **{k: self._budget.get(k) for k in RUNWAY_KEYS if k in self._budget},
            },
            "spend_mode": self.spend_mode(),
            "desks": desks,
            "exit_plans": len(self.exits.plans()) if self.exits is not None else 0,  # leap: exits
            "watch": self.watch.summary(at) if self.watch is not None else None,  # leap: watch
            "last_mark_at": state.get("last_mark_at"),
            "last_committee_day": state.get("last_committee_day"),
            "last_evolution_day": state.get("last_evolution_day"),
            "last_error": self.last_error,
        }

    def health(self, at: str | None = None, tick: Mapping[str, Any] | None = None) -> dict[str, Any]:
        report = self.status(at)
        # The supervisor's view of the money is the venues' own view of it. A stale row here is
        # how an operator learns a venue stopped answering before the site shows a flat line.
        account = self.account(report["updated_at"])
        if account:
            report["floor"].update(jsonable(account))
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
        for broker in list(self.shadow_books.values()) + list(self.brokers.values()):
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


class _ShadowRouter:
    """One `Broker` face over the per-desk shadow books.

    Each shadow desk keeps its own scoring file so a bug in one desk cannot spend another's
    notional cash. The gateway routes every shadow desk to the one `shadow` key, so this router
    sends each order to the book that belongs to the desk named on the intent, and aggregates
    the reads. Nothing here is a venue and nothing here sends an order anywhere.
    """

    venue = SHADOW_VENUE

    def __init__(self, brokers: Mapping[str, Any], manifests: Mapping[str, DeskManifest]):
        self.brokers = dict(brokers)
        self.manifests = dict(manifests)
        self._orders: dict[str, str] = {}

    def add(self, desk_id: str, broker: Any) -> None:
        """Adopt a book the evolution loop spawned after the service started."""
        self.brokers[desk_id] = broker

    def _for(self, desk_id: str) -> Any:
        broker = self.brokers.get(desk_id)
        if broker is None:
            raise KeyError(f"no shadow book for desk {desk_id}")
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

    def settle_event(self, market_id: str, payout_per_contract: Any, *, now: Any = None) -> list[Any]:
        """Settle one resolved market in every shadow book. A book with no position pays nothing.

        `payout_per_contract` is the **yes** value; each book pays its NO holdings the
        complement. Fanning out is safe because a book that never traded the market returns
        no fills, and it keeps the router from having to know which desk held what.
        """
        out: list[Any] = []
        for broker in self.brokers.values():
            settle = getattr(broker, "settle_event", None)
            if settle is None:
                continue
            out.extend(settle(market_id, payout_per_contract, now=now))
        return out

    def tick(self) -> None:
        for broker in self.brokers.values():
            ticker = getattr(broker, "tick", None)
            if ticker is not None:
                ticker()
