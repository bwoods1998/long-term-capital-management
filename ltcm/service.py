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
import dataclasses
import json
import re
import os
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from .broker import Instrument, OrderIntent, money, text
from .analytics import ResultsLedger
from .committee import Committee, capital_mode, live_desks, promoted_desks, retired_desks
from .runway import Runway, assess as assess_runway
from .runclock import RunClock  # leap: run clock
from .notify import TradeNotifier  # trade notices
from .sandbox import SandboxManager  # leap: sandbox
from .exits import ExitBook  # leap: exits
from .watch import NightWatch  # leap: watch
from .calibration import CalibrationError, CalibrationLedger  # leap: lab
from .lab import Lab  # leap: lab
from .founding import Founding  # leap: founding
from .tools import ToolError  # leap: lab
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
    # leap: feeds -- venue WebSockets (fills, resolutions, prices) on their own threads.
    "feeds": {"enabled": True},
    # leap: exits. The floor keeps every desk's stop, target and time stop (`ltcm/exits.py`).
    "exits": {"enabled": True, "check_seconds": 60, "retry_seconds": 300},
    # leap: watch. The night desk that wakes a desk on a trigger (`ltcm/watch.py`).
    "watch": {"enabled": True},
    # Trade notices: an email per live fill and per settled position, through the gateway.
    "notify": {"enabled": True},
    # leap: sandbox. One forked Sailbox per desk for the code it writes (`ltcm/sandbox.py`);
    # `image_checkpoint` is the lab image built by `scripts/lab_image.py`.
    "sandbox": {"enabled": True, "image_checkpoint": None, "daily_seconds": 1800, "timeout_seconds": 120},
    # leap: lab -- the research lab's nightly slot (local time) and its bounds (`ltcm.lab`),
    # and how often forecasts are checked against the venue for resolution, in seconds.
    "lab_time": "20:00",
    "lab": {},
    "calibration_interval_seconds": 600,
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


def _epoch_of(at: Any) -> float:
    """Seconds since the epoch for an ISO-8601 UTC stamp; 0 for anything unreadable."""
    try:
        return datetime.fromisoformat(str(at).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _disk_free_gb(path: Any) -> float | None:
    """Free space on the filesystem under `path` in GiB, or None where it cannot be read."""
    try:
        import shutil

        return round(shutil.disk_usage(str(path)).free / 2**30, 2)
    except Exception:
        return None


def _rss_mb() -> int | None:
    """The process's resident memory in MiB from /proc, or None where /proc is not there."""
    try:
        with open("/proc/self/statm", encoding="utf-8") as handle:
            pages = int(handle.read().split()[1])
        return int(pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024))
    except Exception:
        return None
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
        """Bars without the instrument echoed on every row: the desk named it in the call, and
        forty bars carrying nine fields of the same instrument each cost more context than the
        prices did. Eight pairs of daily and hourly bars in one turn timed a model out."""
        rows = self._data().bars(instrument, interval, limit)
        out: list[dict[str, Any]] = []
        for row in rows:
            data = row.to_dict() if hasattr(row, "to_dict") else dict(row)
            data.pop("instrument", None)
            out.append(data)
        return out

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

    def weather_forecast(self, city: str) -> dict[str, Any]:  # leap: weather
        """The NWS forecast, hourly path and latest reading for a Kalshi weather city."""
        source = self.service.source("weather")
        if source is None:
            raise RuntimeError("no weather source is configured")
        return source.forecast(city)

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
        # Whole words, and every word: "Fed decision" must not surface a fight that ends in a
        # decision ahead of the Fed, however much volume the fight has. A market that carries
        # every query word outranks one that carries some, and volume only breaks ties.
        patterns = [re.compile(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])") for w in words]
        scored: list[tuple[int, int, Decimal, dict[str, Any]]] = []
        for row in index:
            haystack = row.get("_haystack") or " ".join(
                str(x or "") for x in (row.get("title"), row.get("yes_sub_title"), row.get("ticker"), row.get("event_ticker"))
            ).lower()
            # Tickers are compound words (KXFEDDECISION), so a word may sit inside one; titles
            # are prose, so there a word must stand alone.
            tickers = " ".join(
                str(x or "") for x in (row.get("ticker"), row.get("event_ticker"), row.get("series_ticker"))
            ).lower()
            hits = sum(1 for w, pattern in zip(words, patterns) if pattern.search(haystack) or w in tickers)
            if words and hits == 0:
                continue
            volume = row.get("volume_24h") or ZERO
            try:
                volume = money(volume)
            except (TypeError, ValueError):
                volume = ZERO
            scored.append((1 if hits == len(words) else 0, hits, volume, row))
        scored.sort(key=lambda item: (-item[0], -item[1], -item[2]))
        return [{k: v for k, v in row.items() if not k.startswith("_")} for _, _, _, row in scored[:40]]

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
                stream=self.manifest.stream, kind="desk.outcome", limit=10_000, newest=True
            )
        ]
        rows.reverse()
        return rows[: max(1, int(limit))]

    # -- memory and writing ------------------------------------------------
    def memory_read(self, query: str, limit: int) -> list[dict[str, Any]]:
        """This desk's own memory, and only its own.

        Every desk on the floor used to read one shared pool, so a crypto desk's post-mortem
        came back full of the Fed forecasts a Kalshi desk had written and four variants of one
        mandate converged on the same three "lessons" in the same evening. Variants are only
        an experiment if they think for themselves; `memo_read` is the deliberate channel for
        reading another desk, on the record.
        """
        store = self.service.memory
        if store is None:
            return []
        return list(store.read(query, limit or self.manifest.memory_limit, desk_id=self.desk_id))

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

    # -- leap: lab ---------------------------------------------------------
    def record_forecast(
        self,
        market: str,
        probability: str,
        market_price: str | None,
        side: str | None,
        resolves_at: str | None,
        reasoning: str,
    ) -> dict[str, Any]:
        """One stated probability, published now and scored at resolution."""
        try:
            event = self.service.calibration.record_forecast(
                desk_id=self.desk_id,
                stream=self.manifest.stream,
                session_id=self.session_id,
                market=market,
                venue=self.manifest.market_venue,
                probability=probability,
                market_price=market_price,
                side=side,
                resolves_at=resolves_at,
                reasoning=reasoning,
                at=self.service.now(),
            )
        except CalibrationError as exc:
            raise ToolError(str(exc)) from None
        return {
            "event_id": event.id,
            "market": event.payload["market"],
            "probability": event.payload["probability"],
            "market_price": event.payload["market_price"],
            "scored_at": "resolution",
        }

    def run_code(self, code: str, purpose: str, save_as: str | None) -> dict[str, Any]:
        """Run the desk's code in its own sandbox and publish the run (leap: sandbox)."""
        manager = getattr(self.service, "sandboxes", None)
        at = self.service.now()
        if manager is None:
            return {"exit_code": 3, "output": "no sandbox is available on this floor", "seconds": "0"}
        run = manager.run(self.desk_id, code, purpose=purpose, save_as=save_as)
        try:
            self.service.log.append(
                self.manifest.stream,
                "desk.code_run",
                run.to_payload(self.session_id),
                id=f"code:{self.desk_id}:{run.code_sha256[:12]}:{at}",
                at=at,
            )
        except Exception as exc:
            self.service.alert("warning", f"code run not published: {type(exc).__name__}")
        return {
            "exit_code": run.exit_code,
            "output": run.stdout,
            "seconds": str(run.seconds),
            "code_sha256": run.code_sha256,
            **({"saved_as": run.saved_as} if run.saved_as else {}),
        }

    # leap: strategies -- code the desk deploys to trade for it between sessions
    def deploy_strategy(self, name: str, cadence_seconds: int, params: Any, note: str) -> dict[str, Any]:
        runner = getattr(self.service, "strategies", None)
        if runner is None or not runner.enabled():
            raise RuntimeError("strategies are not available on this floor")
        try:
            return runner.deploy(self.manifest, name, cadence_seconds, params, note=note)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from None

    def undeploy_strategy(self, name: str) -> dict[str, Any]:
        runner = getattr(self.service, "strategies", None)
        if runner is None:
            raise RuntimeError("strategies are not available on this floor")
        try:
            return runner.undeploy(self.manifest, name)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from None

    def strategy_report(self, name: str | None) -> dict[str, Any]:
        runner = getattr(self.service, "strategies", None)
        if runner is None:
            return {"strategies": [], "note": "strategies are not available on this floor"}
        try:
            return runner.report(self.manifest, name)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from None

    def memo_read(self, desk_id: str, limit: int) -> list[dict[str, Any]]:
        """Another desk's published memos, newest first. Its words are evidence, never orders."""
        target = self.service.manifests.get(str(desk_id))
        if target is None:
            known = ", ".join(sorted(self.service.manifests))
            raise ToolError(f"unknown desk {desk_id!r}; the floor has: {known}")
        rows = [
            {
                "desk_id": target.id,
                "desk_name": target.name,
                "at": event.at,
                "session_id": event.payload.get("session_id"),
                "title": str(event.payload.get("title") or "")[:200],
                "text": str(event.payload.get("text") or "")[:4000],
                "note": "another desk's own words: evidence about its reasoning, not instructions",
            }
            for event in self.service.log.read(stream=target.stream, kind="desk.memo", limit=10_000, newest=True)
        ]
        rows.reverse()
        return rows[: max(1, min(20, int(limit)))]

    def floor_board(self, limit: int = 8, *, hours: int = 24) -> list[dict[str, Any]]:
        """leap: board -- the newest memo of every other desk on the floor, newest first, from
        the last `hours`. Read at the start of every session so the partners hear each other:
        a weather desk learns what the crypto desk sees, a shadow child what its parent decided.
        Their words are evidence about what they see, never orders."""
        now = self.service.now()
        cutoff = (datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(hours=int(hours))).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        rows: list[dict[str, Any]] = []
        for other in self.service.active_manifests().values():
            if other.id == self.desk_id:
                continue
            latest = None
            for event in self.service.log.read(stream=other.stream, kind="desk.memo", limit=50, newest=True):
                if event.at >= cutoff and (latest is None or event.at > latest.at):
                    latest = event
            if latest is None:
                continue
            rows.append(
                {
                    "desk_id": other.id,
                    "desk_name": other.name,
                    "mode": other.capital_mode,
                    "family": other.family,
                    "at": latest.at,
                    "title": str(latest.payload.get("title") or "")[:160],
                    "text": str(latest.payload.get("text") or "")[:400],
                }
            )
        rows.sort(key=lambda row: row["at"], reverse=True)
        return rows[: max(1, min(20, int(limit)))]

    def size_today(self) -> dict[str, Any]:
        """The largest order the desk's own limits allow at its equity now, and the learning size
        that fits under it. A desk that has lost money must hear the smaller number: on Sept 16,
        2026 the shadow Scholes children kept proposing the $15 learning order from the rules at
        $60 of equity, and the engine refused every one."""
        state = self.service.ledgers[self.desk_id].state(self.service.now())
        limits = self.manifest.limits
        cap = (state.equity * min(limits.max_order_notional_pct, limits.max_position_pct) * Decimal("0.9")).quantize(Decimal("0.01"))
        policy = dict(self.service.config.get("learning") or {})
        if capital_mode(self.manifest, promoted_desks(self.service.log)) == "live":
            key = "live_coinbase_usd" if self.manifest.market_venue == "coinbase" else "live_kalshi_usd"
            base = Decimal(str(policy.get(key) or "10"))
        else:
            base = Decimal(str(policy.get("shadow_notional_usd") or "15"))
        if cap <= 0:
            return {}
        return {"equity": format(state.equity.quantize(Decimal("0.01")), "f"), "max_order_usd": format(cap, "f"), "learning_usd": format(min(base, cap), "f")}

    def standings(self) -> list[dict[str, Any]]:
        """leap: incentives -- every active partner ranked by lifetime P&L, with the compute
        share it earns and its calibration. Read every session: a desk that can see the scores
        and the rule that pays them plays to the score."""
        at = self.service.now()
        modes = promoted_desks(self.service.log)
        rows: list[dict[str, Any]] = []
        for other in self.service.active_manifests().values():
            ledger = self.service.ledgers.get(other.id)
            if ledger is None:
                continue
            try:
                state = ledger.state(at)
                pnl = (state.equity - state.net_deposits).quantize(Decimal("0.01"))
            except Exception:
                continue
            brier = None
            try:
                summary = self.service.calibration.summary("desk", desk_id=other.id, at=at)
                if summary.get("n"):
                    brier = summary.get("brier")
            except Exception:
                brier = None
            try:
                factor = Decimal(str(self.service.fitness_factor(other.id))).quantize(Decimal("0.01"))
            except Exception:
                factor = Decimal("1.00")
            rows.append({
                "desk_id": other.id, "desk_name": other.name, "family": other.family,
                "mode": capital_mode(other, modes), "pnl_usd": format(pnl, "f"),
                "budget_factor": format(factor, "f"), "brier": brier,
            })
        rows.sort(key=lambda r: Decimal(r["pnl_usd"]), reverse=True)
        return rows

    def floor_calls(self, limit: int = 12, *, hours: int = 24) -> list[dict[str, Any]]:
        """leap: incentives -- the other partners' newest probability per market, on markets
        that have not resolved yet, from the last `hours`. The floor's shared forecast book."""
        now = self.service.now()
        cutoff = (datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(hours=int(hours))).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        modes = promoted_desks(self.service.log)
        active = self.service.active_manifests()
        newest: dict[tuple[str, str], Any] = {}
        for event in self.service.log.read(kind="desk.forecast", limit=2000, newest=True):
            desk_id = str(event.stream or "").split(":", 1)[-1]
            if desk_id == self.desk_id or desk_id not in active or event.at < cutoff:
                continue
            payload = event.payload
            due = str(payload.get("resolves_at") or "")
            if due and due < now:
                continue
            key = (desk_id, str(payload.get("market") or ""))
            if key[1] and (key not in newest or event.at > newest[key].at):
                newest[key] = event
        briers: dict[str, Any] = {}
        rows: list[dict[str, Any]] = []
        for (desk_id, market), event in sorted(newest.items(), key=lambda kv: kv[1].at, reverse=True)[: max(1, min(40, int(limit)))]:
            if desk_id not in briers:
                try:
                    summary = self.service.calibration.summary("desk", desk_id=desk_id, at=now)
                    briers[desk_id] = summary.get("brier") if summary.get("n") else None
                except Exception:
                    briers[desk_id] = None
            other = active[desk_id]
            rows.append({
                "market": market, "desk_id": desk_id, "desk_name": other.name,
                "mode": capital_mode(other, modes), "probability": event.payload.get("probability"),
                "market_price": event.payload.get("market_price"), "brier": briers[desk_id],
                "reasoning": str(event.payload.get("reasoning") or "")[:200], "at": event.at,
            })
        return rows

    def calibration_brief(self) -> str:
        return self.service.calibration.brief(self.desk_id, self.service.now())

    def firm_rules(self) -> list[dict[str, Any]]:
        """The Firm Mind's active rules that apply to this desk (its family, its venues), strongest
        first, each with its evidence: what every desk's settled trades taught the floor."""
        mind = getattr(self.service, "mind", None)
        if mind is None:
            return []
        return mind.rules_for(family=self.manifest.family, venues=self.manifest.venues)

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
        #: Serializes every read-modify-write of `service-state.json`: the lab worker's rewrite
        #: scheduling and the tick both saved it at once and each wiped the other's keys.
        self._state_lock = threading.RLock()
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
        self._apply_capital_modes()
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
        # `_apply_capital_modes` moves each manifest once the desk's sleeve is ready; the gateway
        # routes by that, and refuses a desk whose promotion or demotion is logged but not done.
        self.gateway.manifests_carry_mode = True
        self.committee = Committee(
            self.log,
            self.manifests,
            self.ledgers,
            provider=self.provider,
            clock=clock,
            venue_equity=self._venue_equity,
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
                # The promotion gate is the committee's, one setting for both readers: until
                # Sept 16, 2026 the evolution loop built its committee with the defaults
                # (14 days, 20 decisions) while the floor's own ran the configured gate.
                "committee": dict(self.config.get("committee") or {}),
            },
        )
        # leap: lab -- the forecast record and the research lab share the roster by reference,
        # so a desk bred tonight is scored and judged tomorrow without a restart.
        self.calibration = CalibrationLedger(self.log, self.manifests, clock=clock)
        self.lab = Lab(
            self.log,
            self.evolution,
            provider=self.provider,
            clock=clock,
            config=self.config.get("lab") or {},
            results=lambda: ResultsLedger(self.log, self.manifests),
            calibration=self.calibration,
            strategies=getattr(self, "strategies", None),
        )
        # The Firm Mind: every desk's settled outcomes scored into rules that every session and
        # the lab read (`ltcm/mind.py`, config `mind`). None when switched off.
        from .mind import build as build_mind

        self.mind = build_mind(self)
        self.lab.mind = self.mind
        # Whatever credential the box holds is redacted from every published string, so a
        # model that echoes one back cannot put it on the site.
        try:
            from .publish import register_secret_literals
            register_secret_literals(self.env().get(name) for name in ("SAIL_API_KEY", "GATEWAY_TOKEN", "CAPITAL_PUBLISH_TOKEN"))
        except Exception:
            pass
        if bool((self.config.get("evolution") or {}).get("deferred_rewrites", True)):
            self.evolution.rewriter = self._schedule_rewrite
        self.publisher = publisher if publisher is not None else self._build_publisher()
        self.feeds = self._build_feeds()  # leap: feeds
        self.sandboxes = self._build_sandboxes()  # leap: sandbox
        from .strategies import Strategies  # leap: strategies

        self.strategies = Strategies(
            self,
            path=self.capital_dir / "strategies.json",
            config=self.config.get("strategies") or {},
            clock=clock,
        )
        self.lab.strategies = self.strategies  # leap: lab -- built after the lab; hand it over
        self.founding = self._build_founding()  # leap: founding
        self.foundry = self._build_foundry()  # leap: foundry
        notify = dict(self.config.get("notify") or {})
        self.notifier = TradeNotifier(
            self.log,
            self.manifests,
            gateway_url=self.config.get("gateway_url"),
            token=self.secret(self.config.get("gateway_token_env") or "GATEWAY_TOKEN"),
            state=self.state,
            save_state=self._save_state,
            alert=self.alert,
            enabled=bool(notify.get("enabled", True)),
        )
        self._started_monotonic = time.monotonic()
        # leap: run clock. How long, how much, how profitable; folded from the floor's own records.
        self.runclock = RunClock(
            self.log,
            provider=self.provider,
            live_pnl=self._live_pnl,
            uptime=lambda: int(time.monotonic() - self._started_monotonic),
            models_used=self._models_used,
            infra_usd_per_day=(self.config.get("spend_policy") or {}).get("infra_usd_per_day", "0.30"),
            sail_usage=self._sail_usage,
            mark_interval_seconds=int(self.config.get("mark_interval_seconds", 300)),
        )
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
            self._http_transport = transport  # kept so the disk check can trim its cache
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
            elif name == "weather":  # leap: weather
                from .data.weather import Weather

                built = Weather(self.transport, cache_dir=self.capital_dir / "cache", clock=self.clock)
            elif name == "crypto":  # leap: founding -- Coinbase's product listing
                router = getattr(self.market_data, "_source", None)
                built = router("crypto") if router is not None else None
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
            # Rounded to the hour on purpose: these timestamps go into the listing URLs, and the
            # HTTP cache keys on the URL. With the raw clock every page of every ten-minute
            # rebuild was a new 2 MB cache entry; 17,072 of them filled the floor box's 32 GiB
            # disk on Sept 16, 2026. Within an hour the sweep now reuses the same handful of URLs.
            now = float(int(time.time()) // 3600 * 3600)
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

    # leap: feeds ------------------------------------------------------------------------------
    def _build_sandboxes(self) -> Any:
        """The desks' sandbox manager, or None when no lab image is configured (leap: sandbox)."""
        settings = dict(self.config.get("sandbox") or {})
        if not bool(settings.get("enabled", True)) or not settings.get("image_checkpoint"):
            return None
        try:
            from .sailbox import SailboxClient
        except Exception:  # pragma: no cover - ships with the runtime
            return None
        try:
            return SandboxManager(
                SailboxClient(clock=self.clock),
                self.capital_dir / "sandboxes.json",
                self.capital_dir / "toolbox",
                image={"checkpoint_id": str(settings["image_checkpoint"])},
                clock=self.clock,
                daily_seconds=int(settings.get("daily_seconds", 1800)),
            )
        except Exception as exc:
            self.alert("warning", f"sandboxes unavailable: {type(exc).__name__}")
            return None

    def _build_foundry(self) -> Any:
        """leap: foundry -- the hourly evidence loop (`ltcm/foundry.py`), built once the strategy
        runner and the sandboxes exist. Its backtest sandboxes get their own fuse and run cap."""
        settings = dict(self.config.get("foundry") or {})
        if not bool(settings.get("enabled", True)):
            return None
        try:
            from .foundry import DEFAULTS as FOUNDRY_DEFAULTS, Foundry

            foundry = Foundry(
                log=self.log,
                strategies=self.strategies,
                sandboxes=lambda: self.sandboxes,
                provider=self.provider,
                manifests=self.active_manifests,
                clock=self.clock,
                alert=self.alert,
                config=settings,
                state_path=self.capital_dir / "foundry.json",
                equity=self._desk_equity,
                halted=lambda: self.gateway.kill_switch_engaged(),
            )
        except Exception as exc:
            self.alert("warning", f"foundry unavailable: {type(exc).__name__}")
            return None
        limiter = getattr(self.sandboxes, "set_limits", None)
        if callable(limiter):
            merged = {**FOUNDRY_DEFAULTS, **settings}
            try:
                limiter("foundry-", daily_seconds=int(merged["sandbox_daily_seconds"]), max_timeout=int(merged["backtest_timeout_seconds"]))
            except Exception:
                pass
        return foundry

    def _desk_equity(self, desk_id: str) -> Any:
        ledger = self.ledgers.get(desk_id)
        if ledger is None:
            return None
        try:
            return ledger.state(self.now()).equity
        except Exception:
            return None

    def _foundry_tick(self, at: str, state: Mapping[str, Any]) -> Any:
        """leap: foundry -- start a cycle off the tick when one is due and none is running. The
        cycle deploys from its worker; the strategy store is locked and sessions deploy from
        threads too. Returns the previous cycle's summary once it has finished."""
        foundry = self.foundry
        if foundry is None or not foundry.enabled():
            return None
        if not foundry.due(at, state.get("last_foundry_at")):
            return None
        slot = (getattr(self, "_workers", None) or {}).get("foundry")
        if (slot is not None and slot["thread"].is_alive()) or foundry.running():
            return None  # the last cycle is still working; a cycle never runs twice at once
        self._save_state(last_foundry_at=at)
        done = self._off_tick("foundry", lambda at=at: foundry.cycle(at))
        if isinstance(done, Mapping):
            return {k: v for k, v in done.items() if k != "candidates_detail"}
        return None

    def _feeds_status(self) -> dict[str, Any] | None:
        """The venue sockets as the hub reports them, or None on a floor without feeds."""
        hub = getattr(self, "feeds", None)
        if hub is None:
            return None
        try:
            return hub.status()
        except Exception:
            return {"error": "status unavailable"}

    def _venue_equity(self) -> dict[str, Decimal]:
        """Each live venue's equity as the venue reports it, for the committee's sleeve caps."""
        out: dict[str, Decimal] = {}
        try:
            for row in self.venue_balances():
                out[str(row.get("venue"))] = money(row.get("equity"))
        except Exception:
            return {}
        return out

    def _sail_usage(self) -> dict[str, Any] | None:
        """The infrastructure spend the run clock shows: Sail's own last-day spend less the
        model ledger's last day (the box, the sandboxes, the image builds), recorded per UTC
        day in the state file and summed, so the total grows from the floor's own first day
        and never counts what an earlier project spent."""
        provider = self.provider
        period = getattr(provider, "sail_spend_period_usd", None)
        trailing = getattr(provider, "spent_since", None)
        if not callable(period) or not callable(trailing):
            return None
        try:
            total = period()
            if total is None:
                return None
            today_infra = max(ZERO, money(total) - money(trailing(24.0)))
            day = self.now()[:10]
            state = self.state()
            by_day = dict(state.get("infra_spend_by_day") or {})
            by_day[day] = str(today_infra.quantize(Decimal("0.01")))
            for stale in sorted(by_day)[:-60]:
                by_day.pop(stale, None)
            if by_day != (state.get("infra_spend_by_day") or {}):
                self._save_state(infra_spend_by_day=by_day)
            return {"infra_spend_usd": sum((money(v) for v in by_day.values()), ZERO)}
        except Exception:
            return None

    def _live_pnl(self, at: str) -> Decimal:
        """Profit on real money since inception: every live sleeve's equity less what was
        deposited, plus each demoted desk's result frozen at the moment it left real money. A
        demotion must never improve the record: on Sept 16, 2026 Scholes' -$53.93 dropped out of
        the headline the minute it moved to a shadow book, and the floor read -$5.90."""
        from .committee import demoted_desks

        total = ZERO
        live = self.live_ids()
        for desk_id in live:
            ledger = self.ledgers.get(desk_id)
            if ledger is None:
                continue
            state = ledger.state(at)
            total += money(state.equity) - money(state.net_deposits)
        cache = getattr(self, "_demoted_pnl", None)
        if cache is None:
            cache = self._demoted_pnl = {}
        try:
            demoted = demoted_desks(self.log)
        except Exception:
            demoted = {}
        for desk_id, left_at in demoted.items():
            if desk_id in live:
                continue
            key = (desk_id, left_at)
            if key not in cache:
                try:
                    state = DeskLedger(self.log, desk_id, until=left_at).state(left_at)
                    cache[key] = money(state.equity) - money(state.net_deposits)
                except Exception:
                    continue
            total += cache[key]
        return total

    def _models_used(self) -> list[str]:
        """The display names of the models the active desks run on."""
        try:
            from .provider import DISPLAY_NAMES, PROFILES
        except Exception:  # pragma: no cover
            return []
        names: set[str] = set()
        for manifest in self.active_manifests().values():
            profile = PROFILES.get(manifest.model.profile)
            if profile:
                names.add(DISPLAY_NAMES.get(profile[0], profile[0]))
        return sorted(names)

    def _build_feeds(self) -> Any:
        """The venue WebSocket hub, or None when feeds are off or the floor is not in gateway mode.

        Feeds need the gateway for their credential material and a live venue to listen to.
        Nothing is started here: `run()` starts the threads, so a constructed service (tests,
        `status`, one-off commands) never opens a socket.
        """
        settings = self.config.get("feeds") or {}
        if not bool(settings.get("enabled", True)):
            return None
        gateway_url = self.config.get("gateway_url")
        token = self.secret(self.config.get("gateway_token_env") or "GATEWAY_TOKEN")
        live = [v for v in (self.config.get("live_venues") or []) if v in ("kalshi", "coinbase")]
        if not gateway_url or not token or not live:
            return None
        try:
            from . import feeds as feeds_module
            from .feeds import coinbase as coinbase_feeds
            from .feeds import kalshi as kalshi_feeds
        except Exception as exc:  # pragma: no cover - the package ships with the runtime
            self.alert("warning", f"feeds unavailable: {type(exc).__name__}")
            return None
        try:
            credentials = feeds_module.GatewayCredentials(str(gateway_url), token, transport=self.transport)
            hub = feeds_module.FeedHub(
                clock=self.clock,
                alert=self.alert,
                held=self._held_symbols,
                allowed=self._allowed_symbols,
                max_age=float(settings.get("max_age_seconds", feeds_module.DEFAULT_MAX_AGE_SECONDS)),
            )
            if "kalshi" in live:
                hub.add(kalshi_feeds.KalshiFeed(hub, credentials, clock=self.clock))
            if "coinbase" in live:
                hub.add(coinbase_feeds.CoinbaseMarketFeed(hub, clock=self.clock))
                hub.add(coinbase_feeds.CoinbaseUserFeed(hub, credentials, clock=self.clock))
            return hub
        except Exception as exc:
            self.alert("warning", f"feeds not enabled: {type(exc).__name__}")
            return None

    def _held_symbols(self) -> dict[str, set[str]]:
        """venue -> the market tickers and product ids the desks currently hold, from the ledgers.

        Feed threads ask after every message; the answer is kept for a couple of seconds so the
        sockets do not fold every ledger and copy the order book against the proposals in flight."""
        cached = getattr(self, "_held_cache", None)
        if cached is not None and time.monotonic() - cached[0] < 2.0:
            return {venue: set(symbols) for venue, symbols in cached[1].items()}
        held: dict[str, set[str]] = {}
        at = self.now()
        for ledger in list(self.ledgers.values()):
            try:
                positions = ledger.state(at).positions.values()
            except Exception:
                continue
            for position in positions:
                if position.quantity == 0:
                    continue
                instrument = position.instrument
                symbol = str(instrument.market_id or instrument.symbol or "").upper()
                if symbol:
                    held.setdefault(instrument.venue, set()).add(symbol)
        # A resting quote is a position waiting to happen: the shadow book fills it from the
        # venue's prints, so the feed must carry the markets the desks are quoting, not only
        # the ones they already hold.
        getter = getattr(getattr(self, "gateway", None), "open_orders", None)
        if callable(getter):
            try:
                rows = list(getter())
            except Exception:
                rows = []
            for row in rows:
                inst = row.get("instrument") if isinstance(row, dict) else None
                if not isinstance(inst, dict):
                    continue
                symbol = str(inst.get("market_id") or inst.get("symbol") or "").upper()
                venue = str(inst.get("venue") or row.get("venue") or "")
                if symbol and venue:
                    held.setdefault(venue, set()).add(symbol)
        self._held_cache = (time.monotonic(), {venue: set(symbols) for venue, symbols in held.items()})
        return held

    def _allowed_symbols(self) -> dict[str, set[str]]:
        """venue -> the symbols a desk's manifest allows it to trade (crypto products, mostly)."""
        allowed: dict[str, set[str]] = {}
        for manifest in list(self.manifests.values()):
            for symbol in manifest.instruments.allow or ():
                allowed.setdefault(manifest.market_venue, set()).add(str(symbol).upper())
        return allowed

    def _drain_feeds(self, at: str) -> dict[str, Any] | None:
        """Act on what the sockets saw: confirm fills by REST now, note resolutions, keep health."""
        hub = self.feeds
        if hub is None:
            return None
        try:
            drained = hub.drain()
        except Exception as exc:
            self.alert("warning", f"feeds drain failed: {type(exc).__name__}")
            return None
        confirmed: list[str] = []
        for venue in drained.get("fill_venues") or []:
            try:
                confirmed.extend(row.get("fill_id", "") for row in self.gateway.ingest_fills(venue))
            except Exception as exc:
                self.alert("warning", f"fill confirmation on {venue} failed: {type(exc).__name__}")
        # leap: taker model -- every print the sockets saw fills the shadow quotes it would have hit.
        trades = []
        drainer = getattr(hub, "drain_trades", None)
        if callable(drainer):
            try:
                trades = list(drainer())
            except Exception as exc:
                self.alert("warning", f"trade drain failed: {type(exc).__name__}")
        filled = 0
        for trade in trades:
            for desk_id, book in list(self.shadow_books.items()):
                on_trade = getattr(book, "on_trade", None)
                if not callable(on_trade):
                    continue
                try:
                    # Stamped by the book's own clock, not the tick's start: a worker's shadow fill
                    # swept before this drain moved the fill cursor past a tick-stamped one.
                    filled += len(on_trade(trade["venue"], trade["symbol"], trade["price"], trade["size"], trade["taker_side"], None) or [])
                except Exception as exc:
                    self.alert("warning", f"shadow taker fill on {desk_id} failed: {type(exc).__name__}")
        try:
            hub.check_health()
        except Exception:
            pass
        self._taker_drained = getattr(self, "_taker_drained", 0) + len(trades)
        self._taker_fills = getattr(self, "_taker_fills", 0) + filled
        return {
            "fill_venues": list(drained.get("fill_venues") or []),
            "fills_confirmed": [f for f in confirmed if f],
            "resolutions": len(drained.get("resolutions") or []),
            "trades": len(trades),
            "shadow_taker_fills": filled,
        }

    def _maybe_upgrade_kalshi_tier(self, at: str) -> None:
        """Ask Kalshi for the Advanced API tier once the floor has its first API fill.

        Free, self-serve, and it triples the write budget (docs quoted in the backlog, T9):
        `POST /trade-api/v2/account/api_usage_level/upgrade`, granted when at least one of the
        last hundred orders was created via the API. A refusal is retried a day later; a grant
        is recorded once and never asked for again.
        """
        state = self.state()
        if state.get("kalshi_tier_upgraded"):
            return
        retry_after = state.get("kalshi_tier_retry_after")
        if retry_after and str(at) < str(retry_after):
            return
        broker = self.brokers.get("kalshi")
        upgrader = getattr(broker, "upgrade_api_tier", None)
        if upgrader is None:
            return
        if not self.log.read(stream="broker:kalshi", kind="broker.fill", limit=1):
            return
        try:
            outcome = upgrader()
        except Exception as exc:
            self._save_state(kalshi_tier_retry_after=iso_time(parse_iso(at) + timedelta(days=1)))
            self.alert("info", f"kalshi api tier upgrade not granted yet: {str(exc)[:200]}")
            return
        self._save_state(kalshi_tier_upgraded=at)
        self.alert("info", f"kalshi api tier upgraded to advanced: {json.dumps(outcome, default=str)[:200]}")

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
        with self._state_lock:
            data = {**self.state(), **updates, "updated_at": self.now()}
            tmp = self.state_path.with_name(self.state_path.name + f".tmp-{os.getpid()}-{threading.get_ident()}")
            tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp.chmod(0o600)
            tmp.replace(self.state_path)
            return data

    def active_manifests(self) -> dict[str, DeskManifest]:
        retired = retired_desks(self.log)
        return {k: v for k, v in list(self.manifests.items()) if k not in retired}

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
        self._apply_capital_modes()

    def _tick_phase(self, name: str | None) -> dict[str, float] | None:
        """Mark the start of a step of the tick. The step in progress is written to
        `tick-phase.json` as it starts, so a slow tick can be read while it runs; `None` ends the
        tick and returns the seconds each step took, which the health file keeps."""
        phases = getattr(self, "_tick_phases", None)
        if phases is None:
            phases = self._tick_phases = []
        now = time.monotonic()
        if name is not None:
            phases.append((name, now))
            try:
                (self.capital_dir / "tick-phase.json").write_text(
                    json.dumps({"phase": name, "since": self.now()}) + "\n", encoding="utf-8"
                )
            except Exception:
                pass
            return None
        timing: dict[str, float] = {}
        for index, (phase, started) in enumerate(phases):
            ended = phases[index + 1][1] if index + 1 < len(phases) else now
            timing[phase] = round(timing.get(phase, 0.0) + (ended - started), 2)
        self._tick_phases = []
        return {k: v for k, v in sorted(timing.items(), key=lambda kv: -kv[1]) if v >= 0.05}

    def _off_tick(self, name: str, work: Callable[[], Any]) -> Any:
        """Run slow work (model calls, venue sweeps) on one worker per name, so the tick keeps its
        clock: stops, marks, orders and strategy dispatch every pass. Returns the result of the
        previous run once it has finished (None while it runs), or runs inline when `background`
        is off. On Sept 16, 2026 the night watch's model calls held one tick for four minutes
        once they stopped being cut off at 300 tokens."""
        if not bool(self.config.get("background_work", False)):
            return work()
        workers = getattr(self, "_workers", None)
        if workers is None:
            workers = self._workers = {}
        slot = workers.get(name)
        if slot is not None and slot["thread"].is_alive():
            return None
        previous = slot.get("result") if slot is not None else None
        entry: dict[str, Any] = {"result": None}

        def run() -> None:
            try:
                entry["result"] = work()
            except Exception as exc:  # pragma: no cover - the work guards itself
                self.alert("warning", f"{name} failed off the tick: {type(exc).__name__}")

        entry["thread"] = threading.Thread(target=run, name=f"off-tick-{name}", daemon=True)
        workers[name] = entry
        entry["thread"].start()
        return previous

    def _apply_capital_modes(self) -> None:
        """leap: evolution -- a promotion is an event, not an edit, so the manifest on disk still
        says "shadow" after the committee moved the desk onto real money. Every reader that asks
        `manifest.live` (starter params, learning size, order caps, the session's prompt) would go
        on treating a promoted desk as a scored one. This rewrites the frozen manifests in memory
        so the log's answer is the only answer, on start and after every evolution run."""
        try:
            modes = promoted_desks(self.log)
        except Exception:
            return
        # The gateway routes by its own manifest, so it is told last (Sept 16, 2026 audit: an
        # order checked against a shadow book went to the real venue while a promotion was being
        # set up): a demoted desk's book exists before its orders are routed there, and a promoted
        # desk goes live in the gateway once `_begin_live` has flattened and funded it. Until then
        # the gateway refuses the desk's proposals, and this waits for those already in flight.
        gateway = getattr(self, "gateway", None)
        holders = [getattr(self, name, None) for name in ("committee", "calibration", "lab", "evolution")]
        for desk_id, manifest in list(self.manifests.items()):
            mode = capital_mode(manifest, modes)
            if mode == manifest.capital_mode:
                continue
            fresh = dataclasses.replace(manifest, capital_mode=mode)
            # A desk demoted to shadow trades a scoring book from now on; it had none while live.
            books = getattr(self, "shadow_books", None)
            if mode != "live" and isinstance(books, dict) and desk_id not in books:
                try:
                    broker = self._make_shadow_book(fresh, self.book_path(desk_id))
                except Exception:
                    broker = None
                if broker is not None:
                    books[desk_id] = broker
                    self.brokers.setdefault(SHADOW_VENUE, _ShadowRouter(self.shadow_books, self.manifests))
                    router = self.brokers.get(SHADOW_VENUE)
                    if isinstance(router, _ShadowRouter):
                        router.add(desk_id, broker)
                    self.alert("warning", f"{desk_id} moved to a shadow book: its orders are scored, not sent")
            self.manifests[desk_id] = fresh
            for holder in holders:
                table = getattr(holder, "manifests", None)
                if isinstance(table, dict):
                    table[desk_id] = fresh
            if mode != "live" and gateway is not None:
                gateway.manifests[desk_id] = fresh
            if mode != "live" and isinstance(books, dict):
                # Its real resting orders go: nothing on the venue may outlive the sleeve, a live
                # order still in flight when the demotion landed included.
                if gateway is not None and not self._settle_inflight(desk_id):
                    self.alert("warning", f"{desk_id}: an order was still in flight when its demotion was applied")
                try:
                    resting = [r for r in (gateway.open_orders(desk_id) if gateway is not None else []) if r.get("venue") not in (None, SHADOW_VENUE)]
                except Exception:
                    resting = []
                for row in resting:
                    try:
                        gateway.cancel(desk_id, str(row.get("order_id")), self.now())
                    except Exception as exc:
                        self.alert("warning", f"could not cancel {desk_id}'s real order {row.get('order_id')} on demotion: {type(exc).__name__}")
        #: desk_id -> its live manifest, which the gateway has not been given yet.
        going_live = {
            desk_id: fresh
            for desk_id, fresh in list(self.manifests.items())
            if gateway is not None and fresh.live and not getattr(gateway.manifests.get(desk_id), "live", True)
        }
        # Each promotion to live is set up once: flat book, real sleeve. Keyed by the promotion's
        # time in service state, so a restart (manifests on disk still say shadow) never repeats it,
        # and a desk promoted before this existed is set up on the next tick.
        if getattr(self, "committee", None) is None:
            for desk_id, fresh in going_live.items():
                gateway.manifests[desk_id] = fresh
            return
        promoted_at: dict[str, str] = {}
        try:
            for event in self.log.read(kind="evolution.promoted", limit=10_000, newest=True):
                desk = event.payload.get("desk_id")
                if isinstance(desk, str):
                    if event.payload.get("to") == "live":
                        promoted_at[desk] = event.at
                    else:
                        promoted_at.pop(desk, None)
        except Exception:
            return
        begun = dict(self.state().get("live_begun") or {})
        for desk_id, when in sorted(promoted_at.items()):
            manifest = self.manifests.get(desk_id)
            if manifest is None or not manifest.live or begun.get(desk_id) == when:
                continue
            if not self._settle_inflight(desk_id):
                self.alert("warning", f"{desk_id}: a shadow order was still in flight when its promotion was set up")
            self._begin_live(manifest)
            begun[desk_id] = when
            self._save_state(live_begun=begun)
            if desk_id in going_live:
                gateway.manifests[desk_id] = going_live.pop(desk_id)
        for desk_id, fresh in going_live.items():
            if desk_id not in promoted_at or begun.get(desk_id) == promoted_at[desk_id]:
                gateway.manifests[desk_id] = fresh

    def _settle_inflight(self, desk_id: str, timeout: float = 15.0) -> bool:
        """Wait, holding no lock, for the desk's proposals already past the gateway's check."""
        settle = getattr(getattr(self, "gateway", None), "settle_inflight", None)
        return settle(desk_id, timeout) if callable(settle) else True

    def _begin_live(self, manifest: DeskManifest) -> None:
        """A shadow desk promoted to real money starts its live life flat and funded.

        Its ledger holds the shadow book's positions, which the venue has never seen: left
        alone they would fail the venue reconciliation (and with it every promotion gate on the
        venue), never settle, and let exits sell real holdings that belong to other desks. So
        the shadow positions close in the ledger at their marks (a shadow fill, P&L kept), the
        shadow book's resting orders are cancelled, and the committee funds a real sleeve at
        once, scaled to what the venue holds, instead of at the next resize (Sept 16, 2026: the
        first three promotions carried 28 shadow positions onto real money)."""
        desk_id = manifest.id
        at = self.now()
        closed = 0
        book = self.shadow_books.get(desk_id) if isinstance(getattr(self, "shadow_books", None), dict) else None
        if book is not None:
            try:
                for order in list(book.open_orders()):
                    try:
                        book.cancel(order.id)
                    except Exception:
                        continue
            except Exception:
                pass
        ledger = self.ledgers.get(desk_id)
        try:
            positions = list(ledger.state(at).positions.values()) if ledger is not None else []
        except Exception:
            positions = []
        # Only what the shadow book filled closes: real fills after the promotion are real
        # holdings, and the ledger must keep them.
        from .broker import Instrument as _Instrument

        shadow_net: dict[str, Decimal] = {}
        try:
            for event in self.log.read(kind="broker.fill", limit=20_000, newest=True):
                payload = event.payload
                if payload.get("desk_id") != desk_id or not payload.get("shadow"):
                    continue
                try:
                    key = _Instrument.from_dict(dict(payload.get("instrument") or {})).key
                    quantity = money(payload.get("quantity") or 0)
                except Exception:
                    continue
                signed = quantity if payload.get("side") == "buy" else -quantity
                shadow_net[key] = shadow_net.get(key, ZERO) + signed
        except Exception:
            shadow_net = {}
        for position in positions:
            held = money(position.quantity)
            shadow = shadow_net.get(position.instrument.key, ZERO)
            if held == 0 or shadow == 0 or (held > 0) != (shadow > 0):
                continue
            quantity = min(abs(held), abs(shadow)) * (1 if held > 0 else -1)
            if quantity == 0:
                continue
            price = position.mark if position.mark is not None else position.average_cost
            fill_id = f"promotion-close:{desk_id}:{hashlib.sha256(position.instrument.key.encode('utf-8')).hexdigest()[:10]}:{at}"
            try:
                self.log.append(
                    f"broker:{SHADOW_VENUE}",
                    "broker.fill",
                    {
                        "id": fill_id,
                        "fill_id": fill_id,
                        "order_id": fill_id,
                        "desk_id": desk_id,
                        "instrument": position.instrument.to_dict(),
                        "side": "sell" if quantity > 0 else "buy",
                        "quantity": text(abs(quantity)),
                        "price": text(money(price)),
                        "fee": "0",
                        "at": at,
                        "venue": SHADOW_VENUE,
                        "shadow": True,
                        "promotion_close": True,
                    },
                    id=f"fill:{SHADOW_VENUE}:{fill_id}",
                    at=at,
                )
                closed += 1
            except Exception as exc:
                self.alert("warning", f"{desk_id}: shadow position {position.instrument.key} not closed on promotion: {type(exc).__name__}")
        sleeve = None
        committee = getattr(self, "committee", None)
        if committee is not None:
            try:
                # A promotion is a capital event: every live sleeve is sized afresh from its base
                # and its evidence, rather than held at a previous value the promotion changes.
                sleeve = committee.allocate(at, resize=True).get(desk_id)
            except Exception as exc:
                self.alert("warning", f"{desk_id} promoted but not funded: {type(exc).__name__}")
        self.alert(
            "info",
            f"{desk_id} promoted to real money: {closed} shadow position(s) closed at their marks, sleeve ${text(sleeve) if sleeve is not None else '?'}",
        )

    def quote(self, instrument: Instrument):
        if self.feeds is not None:  # leap: feeds -- a fresh socket price beats any poll
            try:
                live = self.feeds.quote(instrument)
            except Exception:
                live = None
            if live is not None:
                return live
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
        for event in self.log.read(stream=manifest.stream, kind="desk.session_started", limit=5000, newest=True):
            if event.payload.get("trigger") != trigger:
                continue
            if parse_iso(event.at).astimezone(tz).date().isoformat() == day:
                return True
        return False

    def last_session_at(self, manifest: DeskManifest, trigger: str | None = None) -> str | None:
        """When this desk last opened a session, for any trigger or for one named trigger."""
        latest: str | None = None
        for event in self.log.read(
            stream=manifest.stream, kind="desk.session_started", limit=10_000, newest=True
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
            for event in self.log.read(stream=manifest.stream, kind="desk.outcome", limit=10_000, newest=True)
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
                if trigger == "postmortem" and not self.worked_since_last_postmortem(manifest):
                    continue  # nothing to review: a desk bred an hour ago has no day to look back on
                due.append((manifest, trigger))
        return due

    def worked_since_last_postmortem(self, manifest: DeskManifest) -> bool:
        """True when the desk has sat down for a trading session since its last post-mortem.

        A post-mortem costs a model call and rewrites the playbook; run with nothing behind it,
        it rewrites the playbook from another desk's day. Variants bred in the afternoon wait
        for their first real session before they review anything.
        """
        last_review: str | None = None
        last_work: str | None = None
        for event in self.log.read(stream=manifest.stream, kind="desk.session_started", limit=10_000, newest=True):
            trigger = str(event.payload.get("trigger") or "")
            if trigger == "postmortem":
                if last_review is None or event.at > last_review:
                    last_review = event.at
            elif last_work is None or event.at > last_work:
                last_work = event.at
        if last_work is None:
            return False
        return last_review is None or last_work > last_review

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
            for event in self.log.read(stream=manifest.stream, kind="desk.session_started", limit=5000, newest=True)
            if event.payload.get("trigger") == trigger
            and parse_iso(event.at).astimezone(tz).date().isoformat() == day
        ]
        if len(started) != 1:
            return None
        only = started[0]
        session_id = only.payload.get("session_id")
        for event in self.log.read(stream=manifest.stream, kind="desk.session_ended", limit=5000, newest=True):
            if event.payload.get("session_id") == session_id:
                return None
        catchup = int(self.config["session_catchup_seconds"])
        if (parse_iso(at) - parse_iso(only.at)).total_seconds() > catchup:
            return None
        return only

    def next_session_at(self, manifest: DeskManifest, at: str) -> str | None:
        """When this desk next sits down on its cadence, as a UTC instant, or None if it never
        does (a desk with no sessions). Slots already run today are skipped, weekends are
        skipped for a weekdays-only desk, and a slot inside the catch-up window that has not run
        yet counts as now. The site's idle line ("next 16:30 ET") reads this."""
        slots = list(manifest.cadence.sessions)
        if not slots:
            return None
        tz = ZoneInfo(manifest.cadence.timezone)
        local = parse_iso(at).astimezone(tz)
        catchup = int(self.config["session_catchup_seconds"])
        for day_offset in range(0, 9):
            day = local.date() + timedelta(days=day_offset)
            if manifest.cadence.weekdays_only and day.weekday() >= 5:
                continue
            day_key = day.isoformat()
            for slot in sorted(slots, key=_clock_minutes):
                minutes = _clock_minutes(slot)
                when = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(minutes=minutes)
                if day_offset == 0:
                    elapsed = (local - when).total_seconds()
                    if elapsed > catchup:
                        continue  # long past: the schedule would not run it
                    if self.ran_today(manifest, f"cadence:{slot}", day_key):
                        continue
                    if elapsed > 0:
                        return iso_time(parse_iso(at))  # due now, on the next tick
                return iso_time(when.astimezone(timezone.utc))
        return None

    def _next_session_or_none(self, manifest: DeskManifest, at: str) -> str | None:
        try:
            return self.next_session_at(manifest, at)
        except Exception:
            return None

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
                learning=self.config.get("learning") or None,
                budget_factor=lambda desk_id=manifest.id: self.fitness_factor(desk_id),
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
            # Sail's own figure counts what the ledger cannot see (the box, sandboxes, image
            # builds); the runway divides by the larger of the two views of the burn.
            sail_burn = getattr(provider, "sail_burn_usd_per_day", None)
            if callable(sail_burn):
                try:
                    reported = sail_burn()
                    if reported is not None and money(reported) > burn:
                        burn = money(reported)
                except Exception:
                    pass
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
        # One public event per change of picture, and the picture *is* the payload: the mode,
        # and today's spend, the balance, the cap and the runway to the dollar and the day. An id
        # derived from less than the payload would be reused with different content the moment
        # the balance moved a cent, and the log rightly refuses that; a payload carrying cents
        # would be a new public event on every tick of every session. The checkpoint's budget
        # block carries the exact figures.
        exact = runway.to_payload()
        payload = {
            "scope": "floor",
            "spent_usd": str(int(spent)),
            "mode": runway.mode,
            "cap_usd": str(int(runway.cap_usd)),
            "balance_usd": None if runway.balance_usd is None else str(int(runway.balance_usd)),
            "runway_days": None if runway.runway_days is None else str(int(runway.runway_days)),
            "reserve_usd": exact["reserve_usd"],
        }
        digest = hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()[:12]
        try:
            self.log.append(
                "ops", "ops.budget", payload, id=f"budget:floor:{at[:10]}:{digest}", at=at
            )
        except Exception as exc:  # the budget is applied above; a refused event must not stop the tick
            self.alert("warning", f"budget event not written: {type(exc).__name__}")
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

    # ------------------------------------------------------------------ playbook rewrites off the tick
    def _schedule_rewrite(self, job: Mapping[str, Any], *, persist: bool = True) -> None:
        """Queue a bred desk's playbook rewrite for the worker thread (`Evolution.rewriter`).

        The job is also kept in the service state until it is applied, so a restart in the
        middle of a rewrite re-queues it instead of leaving the child on its parent's playbook
        with nothing to say so."""
        import queue

        if getattr(self, "_rewrite_jobs", None) is None:
            self._rewrite_jobs: Any = queue.Queue()
            self._rewrite_done: Any = queue.Queue()
        if persist:
            with self._state_lock:
                pending = dict(self.state().get("pending_rewrites") or {})
                pending[str(job["desk_id"])] = dict(job)
                self._save_state(pending_rewrites=pending)
        self._rewrite_jobs.put(dict(job))
        worker = getattr(self, "_rewrite_thread", None)
        if worker is None or not worker.is_alive():
            self._rewrite_thread = threading.Thread(
                target=self._rewrite_worker, name="playbook-rewrites", daemon=True
            )
            self._rewrite_thread.start()

    def _rewrite_worker(self) -> None:
        """Runs the model calls only: no manifest, ledger or state is touched here."""
        while True:
            try:
                job = self._rewrite_jobs.get(timeout=30)
            except Exception:
                return  # idle: the next job starts a fresh worker
            try:
                text = self.evolution.compose_playbook(job, str(job["desk_id"]), str(job["at"]))
            except Exception as exc:
                text = None
                self.alert("warning", f"playbook rewrite for {job.get('desk_id')} failed: {type(exc).__name__}")
            self._rewrite_done.put(
                (str(job["desk_id"]), text, list(job.get("notes") or []), str(job.get("fallback") or ""))
            )

    def _resume_rewrites(self) -> None:
        """Re-queue the rewrites a restart interrupted: the queue lives in memory, the jobs in state."""
        pending = self.state().get("pending_rewrites") or {}
        if not isinstance(pending, Mapping):
            return
        for desk_id, job in pending.items():
            if desk_id in self.manifests and isinstance(job, Mapping) and job.get("desk_id") == desk_id:
                self._schedule_rewrite(job, persist=False)

    def apply_rewrites(self, at: str) -> list[str]:
        """Apply finished rewrites on the tick's own thread: versioned, published, no lock games."""
        done = getattr(self, "_rewrite_done", None)
        if done is None:
            return []
        applied: list[str] = []
        finished: list[str] = []
        while True:
            try:
                desk_id, text, notes, fallback = done.get_nowait()
            except Exception:
                break
            finished.append(desk_id)
            manifest = self.manifests.get(desk_id)
            if manifest is None or not text:
                continue
            if text.strip() == fallback.strip():
                continue  # the model gave nothing usable; the child keeps the copy it was born with
            if notes:
                text = text.rstrip("\n") + "\n\n## House view\n\n" + "\n\n".join(f"- {n}" for n in notes) + "\n"
            try:
                from .desk import PlaybookStore

                result = PlaybookStore(self.root, manifest).write(
                    text, f"bred from {manifest.parent_id}: rewritten from the parent's playbook and post-mortems"
                )
                self.log.append(
                    manifest.stream,
                    "desk.playbook_updated",
                    {
                        "version": result.get("version"),
                        "diff": str(result.get("diff", ""))[:20_000],
                        "reason": str(result.get("reason", ""))[:500],
                    },
                    id=f"playbook:{desk_id}:v{result.get('version')}:{at}",
                    at=at,
                )
                applied.append(desk_id)
            except Exception as exc:
                self.alert("warning", f"playbook rewrite for {desk_id} not applied: {type(exc).__name__}")
        if finished:
            with self._state_lock:
                pending = dict(self.state().get("pending_rewrites") or {})
                if any(desk_id in pending for desk_id in finished):
                    for desk_id in finished:
                        pending.pop(desk_id, None)
                    self._save_state(pending_rewrites=pending)
        return applied

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

    # ------------------------------------------------------------------ leap: founding
    def _build_founding(self) -> Founding | None:
        """The floor founds new families (`ltcm/founding.py`): the floor's live venues, the lab's
        hard limits, and the venues' public listings through the sources the desks already use."""
        from .lab import DEFAULT_CONFIG as LAB_DEFAULTS

        def market_rows() -> list[dict[str, Any]]:
            source = self.source("event")
            return self.event_index(source) if source is not None else []

        def kalshi() -> Any:
            # Its own source without the HTTP cache: the nightly sweep reads ~150 MB of listings,
            # which through the shared cache would evict what the desks read (the disk incident
            # of Sept 16, 2026 was that cache).
            if self.source("event") is None:
                return None
            if getattr(self, "_founding_kalshi", None) is None:
                from .data import HttpTransport
                from .data.kalshi import KalshiMarketData

                self._founding_kalshi = KalshiMarketData(self.transport or HttpTransport(min_interval=0.2))
            return self._founding_kalshi

        try:
            lab = dict(self.config.get("lab") or {})
            return Founding(
                self.log,
                self.evolution,
                provider=self.provider,
                clock=self.clock,
                config={
                    "live_venues": tuple(self.config.get("live_venues") or ()),
                    "hard_limits": {**LAB_DEFAULTS["hard_limits"], **dict(lab.get("hard_limits") or {})},
                    **dict(self.config.get("founding") or {}),
                },
                kalshi=kalshi,
                coinbase=lambda: self.source("crypto"),
                market_rows=market_rows,
            )
        except Exception as exc:
            self.alert("warning", f"founding unavailable: {type(exc).__name__}")
            return None

    def _founding_tick(self, at: str, local: datetime, day: str, state: Mapping[str, Any], *, allow: bool) -> dict[str, Any] | None:
        """Once a day after `founding.founding_time`: found at most one family, then wind down
        the founded families that failed. Spread over ticks like the lab -- the venue listings and
        the model call run on a worker -- and never raises: a failure is one `ops.alert`."""
        founding = getattr(self, "founding", None)
        if founding is None or not founding.enabled():
            return None
        pending = state.get("founding_pending_day") == day
        if not pending and not self._due(local, founding.time(), state.get("last_founding_day"), day):
            return None
        if not allow:
            outcome: dict[str, Any] = {"status": "skipped", "reason": "the runway is short: live desks only"}
        else:
            try:
                if not pending:
                    self._save_state(founding_pending_day=day)
                outcome = founding.step(at, day=day)
            except Exception as exc:
                outcome = {"status": "failed", "reason": f"{type(exc).__name__}: {str(exc)[:300]}"}
            if outcome.get("status") == "pending":
                return outcome
        if outcome.get("status") == "founded":
            try:
                self.reload_manifests()  # the new desk trades from the next tick, no restart
            except Exception as exc:
                self.alert("warning", f"founded {outcome.get('desk_id')} but the roster did not reload: {type(exc).__name__}")
        elif outcome.get("status") in ("failed", "refused"):
            self.alert("warning", f"founding {outcome['status']}: {str(outcome.get('reason'))[:400]}")
        try:
            wound = founding.wind_down(at)
        except Exception as exc:
            wound = []
            self.alert("warning", f"founding wind-down failed: {type(exc).__name__}: {str(exc)[:200]}")
        outcome["wound_down"] = sorted({str(action.get("family")) for action in wound})
        summary = {k: outcome.get(k) for k in ("status", "reason", "family", "desk_id", "wound_down") if outcome.get(k)}
        self._save_state(last_founding_day=day, founding_pending_day=None, last_founding={**summary, "at": at})
        return outcome

    # ------------------------------------------------------------------ leap: lab
    def _calibration_tick(self, at: str, state: Mapping[str, Any]) -> None:
        """Resolve due forecasts against the venue and publish the day's calibration, at most
        once per `calibration_interval_seconds`. Never load-bearing: a failure is an alert."""
        interval = int(self.config.get("calibration_interval_seconds", 3600))
        last = state.get("last_calibration_at")
        if last is not None and (parse_iso(at) - parse_iso(last)).total_seconds() < interval:
            return
        self._save_state(last_calibration_at=at)
        try:
            self.calibration.resolve(at, self._forecast_resolver(), limit=10)
            self.calibration.publish_daily(at)
        except Exception as exc:
            self.alert("warning", f"calibration failed: {type(exc).__name__}: {exc}")

    def _forecast_resolver(self) -> Any:
        """Ask the event venue whether a market has settled. Kalshi only, for now.

        Kalshi's market row carries no settlement timestamp (`settlement_time` is null on a
        finalized market, verified 2026-09-15); of `expiration_time` and `close_time` the earlier
        that is in the past is used, and the tick's own time when neither is.
        """
        source = self.source("event")
        reader = getattr(source, "market", None)
        if not callable(reader):
            return None

        def resolve(venue: str, market: str) -> dict[str, Any] | None:
            if venue != "kalshi":
                return None
            row = reader(market)
            # Verified against the venue on 2026-09-15: a settled market reads `status:
            # "finalized"` with `result: "yes"|"no"`; `determined` is a result that can still be
            # disputed, so it does not count, and the older `settled` spelling is kept.
            if not isinstance(row, dict) or str(row.get("status") or "") not in ("finalized", "settled"):
                return None
            result = str(row.get("result") or "").strip().lower()
            if result not in ("yes", "no"):
                return None
            now = self.now()
            stamps = [
                str(v) for v in (row.get("expiration_time"), row.get("close_time"))
                if isinstance(v, str) and v and v <= now
            ]
            return {"result": result, "settled_at": min(stamps) if stamps else now, "source": "kalshi"}

        return resolve

    def _spawn_records(self) -> dict[str, dict[str, Any]]:
        return {
            str(event.payload.get("desk_id")): event.payload
            for event in self.log.read(kind="evolution.spawned", limit=10_000, newest=True)
        }

    def _mutation_of(self, desk_id: str, records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
        """A bred desk's mutation in the contract's shape; None for a founder."""
        record = records.get(desk_id)
        mutation = record.get("mutation") if isinstance(record, Mapping) else None
        if not isinstance(mutation, Mapping):
            return None
        return {
            "model_profile": str(mutation.get("model_profile") or ""),
            "reasoning_effort": str(mutation.get("reasoning_effort") or ""),
            "session_shift_minutes": int(mutation.get("session_shift_minutes") or 0),
            "memory_limit": int(mutation.get("memory_limit") or 0),
            "persona_trait": str(mutation.get("persona_trait") or "")[:200],
            "model_changed": bool(mutation.get("model_changed")),
        }

    def _working_of(self, manifest: DeskManifest) -> list[dict[str, Any]]:
        """The desk's resting orders for the checkpoint: what it is bidding and offering now."""
        runner = getattr(self, "strategies", None)
        if runner is None:
            return []
        try:
            rows = runner.open_orders_for(manifest)
        except Exception:
            return []
        out: list[dict[str, Any]] = []
        for row in rows[:20]:
            out.append(
                {
                    "order_id": row.get("order_id"),
                    "instrument": {
                        "symbol": row.get("symbol"),
                        "asset_class": row.get("asset_class"),
                        "venue": row.get("venue") or (manifest.venues[0] if manifest.venues else None),
                        **({"market_id": row.get("market_id")} if row.get("market_id") else {}),
                        **({"right": row.get("right")} if row.get("right") else {}),
                    },
                    "side": row.get("side"),
                    "quantity": row.get("quantity"),
                    "limit_price": row.get("limit_price") or None,
                    "submitted_at": row.get("submitted_at"),
                    "purpose": row.get("purpose") or "entry",
                    "strategy": row.get("strategy"),
                    "intent_id": row.get("intent_id"),
                }
            )
        return out

    def fitness_factor(self, desk_id: str) -> Decimal:
        """How much of its inference budget a desk earns today: 1 with no record, up to `max`
        when its settled P&L per Sail dollar over `window_days` is positive, down to `min` when
        it is negative. Capital already follows results through the committee; this makes the
        model spend follow them too, so a losing desk thinks less and a winning desk more."""
        policy = dict(self.config.get("fitness") or {})
        if not bool(policy.get("enabled", True)):
            return Decimal(1)
        at = self.now()
        cache = getattr(self, "_fitness_cache", None)
        if cache is None or cache.get("hour") != at[:13]:
            try:
                from .analytics import ResultsLedger

                report = ResultsLedger(self.log, self.manifests).report(int(policy.get("window_days", 3)), at)
                cache = {"hour": at[:13], "desks": dict(report.get("desks") or {})}
            except Exception:
                cache = {"hour": at[:13], "desks": {}}
            self._fitness_cache = cache
        row = cache["desks"].get(desk_id) or {}
        try:
            decisions = int(row.get("decisions") or 0)
            # Net P&L (realized, fees and the open book at its marks) per Sail dollar, not closed
            # trades alone: on Sept 16, 2026 a desk earned triple compute on ten settled winners
            # while its open book was down twice as much.
            cost = Decimal(str(row.get("sail_cost_usd") or "0"))
            net = row.get("net_pnl_usd")
            if net is not None and cost > 0:
                per_dollar = Decimal(str(net)) / cost
            else:
                per_dollar = Decimal(str(row.get("pnl_per_inference_dollar") or "0"))
        except (TypeError, ValueError, ArithmeticError):
            return Decimal(1)
        if decisions < int(policy.get("min_decisions", 5)):
            return Decimal(1)
        low = Decimal(str(policy.get("min", "0.25")))
        high = Decimal(str(policy.get("max", "3")))
        factor = Decimal(1) + per_dollar
        return max(low, min(high, factor)).quantize(Decimal("0.01"))

    def _strategies_of(self, manifest: DeskManifest) -> list[dict[str, Any]]:
        """leap: strategies -- the desk's deployed strategies with their records, for the checkpoint."""
        runner = getattr(self, "strategies", None)
        if runner is None:
            return []
        try:
            rows = runner.report(manifest).get("strategies") or []
        except Exception:
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "name": row.get("name"),
                    "house": bool(row.get("house")),
                    "cadence_seconds": row.get("cadence_seconds"),
                    "runs": row.get("runs") or 0,
                    "intents": row.get("intents") or 0,
                    "approved": row.get("approved") or 0,
                    "errors": row.get("errors") or 0,
                    "fills": row.get("fills") or 0,
                    "settled": row.get("settled") or 0,
                    "wins": row.get("wins") or 0,
                    "settled_pnl_usd": row.get("settled_pnl_usd") or "0",
                    "last_run_at": row.get("last_run_at"),
                    "last_notes": row.get("last_notes") or "",
                    # Why these settings, and the settings: publish.strategy_rows shapes both for the site.
                    "note": row.get("note") or "",
                    "params": row.get("params") or {},
                }
            )
        return out

    def _calibration_of(self, desk_id: str, at: str) -> dict[str, Any] | None:
        try:
            row = self.calibration.summary("desk", desk_id=desk_id, at=at)
        except Exception:
            return None
        if not row.get("n"):
            return None
        return {"n": int(row["n"]), "brier": row["brier"], "since": row.get("since")}

    def lab_block(self, at: str) -> dict[str, Any]:
        """The checkpoint's lab block: recent experiments, the improvement curve, calibration."""
        try:
            experiments = self.lab.recent(12)
        except Exception:
            experiments = []
        try:
            report = ResultsLedger(self.log, self.manifests).report(30, at)
            curve = list(report.get("by_generation") or [])[:40]
        except Exception:
            curve = []
        try:
            floor = self.calibration.summary("floor", at=at)
            calibration = {"n": int(floor["n"]), "brier": floor["brier"]}
        except Exception:
            calibration = {"n": 0, "brier": None}
        return {"experiments": experiments, "curve": curve, "calibration": calibration}

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
        # A promotion or a demotion is a log event any loop may write; every tick takes it.
        self._tick_phases = []
        self._tick_phase("capital_modes")
        self._apply_capital_modes()
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
            "experiments": [],  # leap: lab
            "settlements": [],
            "rate_card": None,
            "kill_switch": self.gateway.kill_switch_engaged(),
            "exits": [],  # leap: exits
            "watch": [],  # leap: watch
        }
        self._tick_phase("disk_and_shards")
        self._disk_check(at)  # leap: ops -- before anything else writes
        self._fund_kalshi_shards(at)  # leap: venues -- collateral follows the markets

        self._tick_phase("budget")
        result["budget"] = {k: str(v) for k, v in self.apply_budget(at).items()}
        # leap: feeds -- what the sockets saw since the last tick, confirmed by REST before it counts
        self._tick_phase("feeds")
        result["feeds"] = self._drain_feeds(at)
        self._maybe_upgrade_kalshi_tier(at)
        runway = getattr(self, "_runway", None)
        stopped = runway is not None and runway.mode == "stopped"
        live_only = runway is not None and runway.live_only
        result["spend_mode"] = self.spend_mode()
        # Settlements are swept before the schedule so a market that resolved since the last
        # tick wakes its desk on this tick rather than the next one.
        self._tick_phase("settlements")
        result["settlements"] = self.sweep_settlements(at)
        self._tick_phase("reconcile")
        result["reconciled"] = self._reconcile_venues(at)  # leap: venues -- the book against the venue, hourly
        self._tick_phase("notices")
        try:
            result["notices"] = self.notifier.tick(at)
        except Exception as exc:  # a notice is a courtesy; the tick is the job
            self.alert("warning", f"trade notices failed: {type(exc).__name__}")
            result["notices"] = []
        # A desk that has never been funded, or a roster change, gets an allocation right away, before any
        # session starts, so a desk never sees an unfunded book;
        # the weekly resize by track record still only happens on the committee's day.
        self._tick_phase("allocation")
        previous, _ = self.committee.last_allocation()
        if any(desk_id not in previous for desk_id in self.manifests):
            self.committee.allocate(at)
            result["committee"] = True
        self._tick_phase("sessions")
        if not result["kill_switch"] and not stopped:
            due = self.due_sessions(at)
            if live_only:
                # Short runway: the shadow race pauses and the credit goes to the real sleeves.
                live = self.live_ids()
                due = [(m, trigger) for m, trigger in due if m.id in live]
            self.start_sessions(due)
            result["sessions"] = [f"{m.id}/{trigger}" for m, trigger in due]

        self._tick_phase("shadow_books")
        for broker in self.shadow_books.values():
            ticker = getattr(broker, "tick", None)
            if ticker is not None:
                try:
                    ticker()
                except Exception as exc:
                    self.alert("warning", f"shadow book tick failed: {exc}")
        self._tick_phase("poll_orders")
        try:
            result["orders"] = [row["order_id"] for row in self.gateway.poll_orders(at)]
        except Exception as exc:
            self.alert("warning", f"order poll failed: {exc}")
        # leap: exits. Stops, targets and time stops are the floor's to keep, every tick,
        # whether or not the desk is in session. The kill switch refuses every order, exits
        # included, so nothing is filed while it is engaged.
        self._tick_phase("exits")
        if self.exits is not None and not result["kill_switch"]:
            try:
                result["exits"] = self.exits.tick(at)
            except Exception as exc:
                self.alert("warning", f"exit enforcement failed: {type(exc).__name__}: {exc}")

        self._tick_phase("marks")
        interval = int(self.config["mark_interval_seconds"])
        last_mark = state.get("last_mark_at")
        if last_mark is None or (parse_iso(at) - parse_iso(last_mark)).total_seconds() >= interval:
            result["marked"] = self.mark_all(at)
            result["breakers"] = self.breakers(at)
            self._save_state(last_mark_at=at)

        # leap: watch. The night desk looks after the marks are fresh; it costs nothing
        # until something happens, and it is quiet when the floor has stopped for credit.
        self._tick_phase("watch")
        if self.watch is not None and not result["kill_switch"] and not stopped:
            allow_shadow = not live_only

            def watch_once(at: str = at, allow: bool = allow_shadow) -> Any:
                try:
                    return self.watch.tick(at, allow_shadow=allow)
                except Exception as exc:
                    self.alert("warning", f"night watch failed: {type(exc).__name__}: {exc}")
                    return []

            result["watch"] = self._off_tick("watch", watch_once) or []

        # Keep the event-contract index warm so a desk's first search does not wait on a sweep.
        if any("event" in m.instruments.asset_classes for m in self.manifests.values()):
            source = self.source("event")
            if source is not None:

                def warm(source: Any = source) -> None:
                    try:
                        self.event_index(source)
                    except Exception as exc:
                        self.alert("warning", f"event index warm-up failed: {type(exc).__name__}")

                self._off_tick("event_index", warm)

        self._tick_phase("rate_card_and_seeding")
        day = local.date().isoformat()
        if state.get("last_rate_card_day") != day:
            result["rate_card"] = self.check_rate_card()
            self._save_state(last_rate_card_day=day)
        if not stopped and not live_only:
            seeded = self.seed_population(at)
            if seeded:
                result["evolution"] = list(result.get("evolution") or []) + seeded
        if not getattr(self, "_rewrites_resumed", False):
            self._rewrites_resumed = True
            if self.evolution.rewriter is not None:
                self._resume_rewrites()
        self._tick_phase("rewrites")
        result["rewrites"] = self.apply_rewrites(at)
        self._tick_phase("strategies")
        if not result["kill_switch"] and not stopped:  # leap: strategies
            try:
                result["strategies"] = self.strategies.tick(self.active_manifests(), at)
            except Exception as exc:
                self.alert("warning", f"strategies failed: {type(exc).__name__}")
                result["strategies"] = []
        # leap: foundry -- candidates, backtests, shadow deployments and fast-tracks, off the tick.
        self._tick_phase("foundry")
        if not result["kill_switch"] and not stopped and not live_only:
            try:
                result["foundry"] = self._foundry_tick(at, state)
            except Exception as exc:
                self.alert("warning", f"foundry failed: {type(exc).__name__}")
        # leap: lab -- forecasts are checked against the venue on a slow clock and the day's
        # calibration is published once; the lab sits down at its own evening slot.
        self._tick_phase("calibration")
        if not stopped:
            self._calibration_tick(at, state)
        # The lab's night is spread over ticks, one model call per tick, so the floor keeps
        # marking, exiting and publishing while it thinks: a night that blocked the tick for
        # twenty minutes would have the watchdog restart the box in the middle of it.
        self._tick_phase("lab")
        lab_pending = state.get("lab_pending_day") == day
        if not stopped and (lab_pending or self._due(local, self.config["lab_time"], state.get("last_lab_day"), day)):
            if not lab_pending:
                self._save_state(lab_pending_day=day)

            def lab_step(at: str = at, day: str = day, first: bool = not lab_pending) -> dict[str, Any]:
                # The model call (K3, a long answer) runs on a worker; the roster reload and the
                # strategy installs stay on the tick, which owns the manifests.
                experiments: list[dict[str, Any]] = []
                try:
                    if first:
                        experiments.extend(self.lab.evaluate(at))
                    experiments.extend(self.lab.propose(at, max_work=1))
                except Exception as exc:
                    # One alert, and the night is over: a lab that fails every tick until
                    # midnight would write the same alert to the public tape every thirty seconds.
                    self.alert("warning", f"lab run failed: {type(exc).__name__}: {exc}")
                    return {"day": day, "experiments": experiments, "failed": True}
                return {"day": day, "experiments": experiments, "failed": False}

            done = self._off_tick("lab", lab_step)
            if isinstance(done, Mapping) and done.get("day") == day:
                if done.get("failed"):
                    self._save_state(last_lab_day=day, lab_pending_day=None)
                self.reload_manifests()
                self._install_experiment_strategies(list(done.get("experiments") or []))  # leap: lab
                if not self.lab.pending(at):
                    self._save_state(last_lab_day=day, lab_pending_day=None)
                result["experiments"] = list(done.get("experiments") or [])
        # The Firm Mind's hourly pass: re-score and retire rules, ask the scientist when there is
        # new evidence and credit to spare. Off the tick; a pass never raises (`ltcm/mind.py`).
        self._tick_phase("mind")
        mind = getattr(self, "mind", None)
        if mind is not None and not stopped and mind.due(at):
            self._off_tick("mind", lambda at=at, ask=not live_only: mind.run(at, ask=ask))
        self._tick_phase("committee")
        if stopped:
            pass  # the memo and the evolution loop both ask the model; they wait for credit
        elif self._due(local, self.config["committee_time"], state.get("last_committee_day"), day):
            # Meriwether writes every day. Capital moves every `resize_interval_days` (config
            # `committee`); a weekly interval keeps the committee's weekday. Until Sept 16, 2026
            # the resize ran on the weekday alone, so a configured daily resize never happened
            # and capital could not follow the desks that were earning it for up to a week.
            interval = int(self.committee.config.get("resize_interval_days", 7))
            last_resize = state.get("last_resize_day")
            if interval >= 7:
                resize_day = local.weekday() == int(self.config["committee_weekday"])
            else:
                try:
                    elapsed = (datetime.fromisoformat(day).date() - datetime.fromisoformat(str(last_resize)).date()).days
                except (TypeError, ValueError):
                    elapsed = interval
                resize_day = last_resize is None or elapsed >= interval
            memo_daily = bool(self.config.get("committee_memo_daily", True))
            if float(self.committee.config.get("resize_interval_hours") or 0) > 0:
                resize_day = False  # resized on its own clock below
            if resize_day:
                self.committee.allocate(at, resize=True)
                self._save_state(last_resize_day=day)
                result["committee"] = True
            if resize_day or memo_daily:
                # Meriwether's memo is a model call: off the tick, once for the day.
                self._off_tick("memo", lambda at=at: bool(self.committee.memo(at)))
                result["memo"] = True
                self._save_state(last_committee_day=day)
        # Capital and selection on an hours clock (config `committee.resize_interval_hours`,
        # `evolution_interval_hours`): a generation that waits a day for its next capital move or
        # its next selection compounds at a day's pace. Zero keeps the daily slots.
        resize_hours = float(self.committee.config.get("resize_interval_hours") or 0)
        if not stopped and resize_hours > 0:
            last = state.get("last_resize_at")
            if last is None or (_epoch_of(at) - _epoch_of(last)) >= resize_hours * 3600:
                self.committee.allocate(at, resize=True)
                self._save_state(last_resize_at=at, last_resize_day=day)
                result["committee"] = True
        self._tick_phase("evolution_and_founding")
        evolution_hours = float(self.config.get("evolution_interval_hours") or 0)
        if evolution_hours > 0:
            last_evolution = state.get("last_evolution_at")
            evolution_due = last_evolution is None or (_epoch_of(at) - _epoch_of(last_evolution)) >= evolution_hours * 3600
        else:
            evolution_due = self._due(local, self.config["evolution_time"], state.get("last_evolution_day"), day)
        if not stopped and evolution_due:
            actions = list(self.evolution.select(at)) + list(self.evolution.promote(at))
            self.reload_manifests()
            self._save_state(last_evolution_day=day, last_evolution_at=at)
            result["evolution"] = actions
        # leap: founding -- after the evolution run the floor may open a line of business.
        if not stopped:
            result["founding"] = self._founding_tick(at, local, day, state, allow=not live_only)

        self._tick_phase("results_ledger")
        try:
            event = ResultsLedger.publish_daily(self.log, at, manifests=self.manifests)
            result["lab"] = None if event is None else event.id
        except Exception as exc:  # a scoreboard may never stop the floor
            self.alert("warning", f"lab result failed: {type(exc).__name__}")
        self._tick_phase("publish")
        result["published"] = self.publish()
        result["timing"] = self._tick_phase(None)
        self.health(at, result)
        return result

    def sweep_settlements(self, at: str) -> list[str]:
        """Close resolved event markets on every venue that reports settlements.

        Returns the fill ids written. A venue with no settlement endpoint, or a sweep that
        fails, is a no-op: nothing here may stop the rest of the tick.
        """
        written: list[str] = []
        # A market finalizes once; asking about every held market every thirty seconds took 11
        # seconds of each tick on Sept 16, 2026. `settlement_interval_seconds` spaces the sweeps.
        interval = float(self.config.get("settlement_interval_seconds") or 0)
        last = getattr(self, "_settled_swept_at", None)
        if interval > 0 and last is not None and (_epoch_of(at) - _epoch_of(last)) < interval:
            return written
        self._settled_swept_at = at
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
            # Markets only shadow desks held never reach the account's settlements feed; the
            # market itself says when it has finalized.
            try:
                written.extend(
                    row["fill_id"] for row in self.gateway.settle_finalized_markets(venue, at)
                )
            except Exception as exc:
                self.alert("warning", f"finalized-market sweep on {venue} failed: {type(exc).__name__}")
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

    def _install_experiment_strategies(self, actions: list[dict[str, Any]]) -> None:
        """leap: lab -- a running experiment whose change carries a strategy gets that code
        deployed on its variant, once the variant's manifest is loaded. Never raises."""
        runner = getattr(self, "strategies", None)
        if runner is None:
            return
        for action in actions or []:
            try:
                if action.get("action") != "experiment" or action.get("status") != "running":
                    continue
                spec = (action.get("change") or {}).get("strategy")
                manifest = self.manifests.get(str(action.get("variant_desk_id") or ""))
                if not isinstance(spec, Mapping) or manifest is None:
                    continue
                runner.install(manifest, spec, note=f"lab experiment {action.get('experiment_id')}")
            except Exception as exc:
                self.alert("warning", f"experiment strategy not deployed on {action.get('variant_desk_id')}: {str(exc)[:200]}")

    def _reconcile_venues(self, at: str) -> list[str]:
        """Once an hour, compare each live venue's positions with the sum of the desk ledgers on
        it (`Gateway.reconcile` writes `broker.reconciled` and alerts on a mismatch). The method
        existed since the first live day and nothing called it until Sept 16, 2026, so the
        health flag had never been anything but False. Never raises."""
        policy = dict(self.config.get("reconcile") or {})
        if not bool(policy.get("enabled", True)):
            return []
        last = getattr(self, "_reconciled_at", None)
        if last is None:
            self._reconciled_at = at  # the first tick arms the clock: a restart never doubles the venue calls
            return []
        if (_epoch_of(at) - _epoch_of(last)) < float(policy.get("interval_seconds", 3600)):
            return []
        self._reconciled_at = at
        done: list[str] = []
        for venue in [v for v in (self.config.get("live_venues") or []) if v in self.gateway.brokers]:
            try:
                self.gateway.reconcile(venue, at)
                done.append(venue)
            except Exception as exc:
                self.alert("warning", f"reconciliation of {venue} failed: {type(exc).__name__}")
        return done

    def _fund_kalshi_shards(self, at: str) -> None:
        """leap: venues -- keep collateral on every Kalshi exchange shard the floor trades.

        Kalshi runs several exchange shards (crypto and commodities on 2, exotics on 1, some
        sports on 3, everything else on 0) and an order on a shard with no cash fails with
        `insufficient_shard_balance`. Once an hour: read the cash per shard and, for every shard
        in `kalshi_shards.shards` under `floor_usd`, move `top_up_usd` from the richest other
        shard that keeps at least `keep_usd` after the move. Every move is an `ops.alert` on the
        tape. Never raises."""
        try:
            policy = dict(self.config.get("kalshi_shards") or {})
            if not bool(policy.get("enabled", True)) or "kalshi" not in (self.config.get("live_venues") or []):
                return
            last = getattr(self, "_shards_checked_at", None)
            if last is not None and (_epoch_of(at) - _epoch_of(last)) < float(policy.get("interval_seconds", 3600)):
                return
            self._shards_checked_at = at
            broker = self.gateway.brokers.get("kalshi")
            reader = getattr(broker, "shard_balances", None)
            mover = getattr(broker, "transfer_between_shards", None)
            if not callable(reader) or not callable(mover):
                return
            balances = dict(reader())
            if not balances:
                return
            wanted = [int(s) for s in (policy.get("shards") or [0, 2])]
            floor = Decimal(str(policy.get("floor_usd", "40")))
            top_up = Decimal(str(policy.get("top_up_usd", "60")))
            keep = Decimal(str(policy.get("keep_usd", "60")))
            minimum = Decimal(str(policy.get("min_move_usd", "10")))
            for shard in wanted:
                cash = balances.get(shard, Decimal(0))
                if cash >= floor:
                    continue
                donors = sorted(((v, k) for k, v in balances.items() if k != shard), reverse=True)
                if not donors:
                    continue
                donor_cash, donor = donors[0]
                amount = min(top_up, donor_cash - keep)
                if amount < minimum:
                    self.alert("warning", f"kalshi shard {shard} holds {cash:.2f} and no other shard can spare {minimum:.0f}; the markets on it will refuse orders")
                    continue
                transfer_id = mover(amount, donor, shard)
                balances[donor] = donor_cash - amount
                balances[shard] = cash + amount
                self.alert("info", f"kalshi collateral: moved {amount:.2f} from shard {donor} to shard {shard} (it held {cash:.2f}; transfer {transfer_id or 'unconfirmed'})")
        except Exception as exc:
            try:
                self.alert("warning", f"kalshi shard funding failed: {type(exc).__name__}")
            except Exception:
                pass

    def _disk_check(self, at: str) -> None:
        """leap: ops -- once every ten minutes, read the free space under the floor's root.
        Under `disk.warn_gb` the HTTP cache is trimmed and a warning is filed; under
        `disk.stop_gb` an error is filed and the owner is mailed (`disk_low`). On Sept 16, 2026
        the floor box filled its 32 GiB disk and the loop died at 06:12 UTC with nothing on the
        tape about it. Never raises."""
        try:
            policy = dict(self.config.get("disk") or {})
            if not bool(policy.get("enabled", True)):
                return
            last = getattr(self, "_disk_checked_at", None)
            if last is not None and (_epoch_of(at) - _epoch_of(last)) < float(policy.get("interval_seconds", 600)):
                return
            self._disk_checked_at = at
            free = _disk_free_gb(self.root)
            if free is None:
                return
            warn, stop = float(policy.get("warn_gb", 4)), float(policy.get("stop_gb", 2))
            if free >= warn:
                self._disk_alerted = None
                return
            trimmed = 0
            transport = getattr(self, "_http_transport", None)
            if hasattr(transport, "trim"):
                try:
                    trimmed = int(transport.trim(force=True))
                except Exception:
                    trimmed = 0
            level = "error" if free < stop else "warning"
            key = (level, at[:13])
            if getattr(self, "_disk_alerted", None) == key:
                return
            self._disk_alerted = key
            self.alert(level, f"disk: {free:.2f} GiB free under {self.root} ({'below the stop line' if level == 'error' else 'low'}); trimmed {trimmed} cache entries")
            if level == "error":
                self._mail_disk_low(free, at)
        except Exception:
            return

    def _mail_disk_low(self, free: float, at: str) -> None:
        """One `disk_low` notice through the gateway (it mails the owner)."""
        notifier = getattr(self, "notifier", None)
        poster, url, token = getattr(notifier, "poster", None), getattr(notifier, "gateway_url", None), getattr(notifier, "token", None)
        if not callable(poster) or not url or not token:
            return
        total = None
        try:
            import shutil

            total = round(shutil.disk_usage(str(self.root)).total / 2**30, 1)
        except Exception:
            pass
        try:
            poster(f"{url}/v1/notify", token, {"kind": "disk_low", "free_gb": free, "total_gb": total, "root": str(self.root), "at": at,
                                               "detail": "The floor trimmed its HTTP cache. If the space keeps falling the loop stops when the disk is full."})
        except Exception as exc:
            self.alert("warning", f"disk_low notice not sent: {type(exc).__name__}")

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
        spawn_records = self._spawn_records()  # leap: lab
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
                    # Lifetime P&L: equity less every capital flow the committee made, so a resized
                    # sleeve never reads as a gain or a loss on the site.
                    "pnl_usd": state.equity - state.net_deposits,
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
                    # When the desk next sits down; the site's idle line reads it.
                    "next_session_at": self._next_session_or_none(manifest, at),
                    # leap: lab -- why a bred desk differs from its parent, and how well it forecasts.
                    "mutation": self._mutation_of(desk_id, spawn_records),
                    "calibration": self._calibration_of(desk_id, at),
                    # leap: strategies -- the code trading for the desk, with each one's record.
                    **({"strategies": self._strategies_of(manifest)} if self.config.get("checkpoint_strategies") else {}),
                    # The desk's resting orders, so the owner sees the book without the venue.
                    **({"working": self._working_of(manifest), "budget_factor": text(self.fitness_factor(desk_id))} if self.config.get("checkpoint_strategies") else {}),
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
            lab=self.lab_block(at),  # leap: lab
            run=self._run_block(at),  # leap: run clock
        )

    def _run_block(self, at: str) -> dict[str, Any] | None:
        try:
            return self.runclock.read(at)
        except Exception as exc:  # a clock that cannot read is a blank, never a lost checkpoint
            self.alert("warning", f"run clock failed: {type(exc).__name__}")
            return None

    # ------------------------------------------------------------------ leap: exits
    def opening_intent(self, desk_id: str, key: str) -> dict[str, Any] | None:
        """The newest entry intent this desk proposed on that instrument, as published."""
        manifest = self.manifests.get(desk_id)
        stream = manifest.stream if manifest is not None else f"desk:{desk_id}"
        found: dict[str, Any] | None = None
        for event in self.log.read(stream=stream, kind="desk.intent", limit=10_000, newest=True):
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
            "feeds": self._feeds_status(),
            "rss_mb": _rss_mb(),
            "disk_free_gb": _disk_free_gb(self.root),
            "taker_model": {"prints_drained": getattr(self, "_taker_drained", 0), "shadow_fills": getattr(self, "_taker_fills", 0)},
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
            "last_founding": state.get("last_founding"),  # leap: founding
            "last_foundry": self.foundry.summary() if getattr(self, "foundry", None) is not None else None,  # leap: foundry
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
                "timing": tick.get("timing"),
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
        if self.feeds is not None:  # leap: feeds
            try:
                self.feeds.start()
            except Exception as exc:
                self.alert("warning", f"feeds did not start: {type(exc).__name__}")
        try:
            while not self.stopping:
                try:
                    result = self.tick()
                    self.last_error = None
                except Exception as exc:
                    self.last_error = str(exc)
                    self.alert("critical", f"tick failed: {exc}")
                    self._health_guarded()
                if once or self.stopping:
                    break
                self.sleeper(float(self.config["sleep_seconds"]))
        finally:
            for sig, handler in previous.items():
                try:
                    signal.signal(sig, handler)
                except ValueError:
                    pass
            self._health_guarded()
        return result

    def _health_guarded(self) -> None:
        """The health file after a failed tick. A second failure here must not end the loop."""
        try:
            self.health()
        except Exception as exc:
            self.last_error = f"health failed: {type(exc).__name__}: {exc}"

    def close(self) -> None:
        if getattr(self, "sandboxes", None) is not None:  # leap: sandbox
            try:
                self.sandboxes.sleep_all()
            except Exception:
                pass
        if self.feeds is not None:  # leap: feeds
            try:
                self.feeds.stop()
            except Exception:
                pass
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
            # A refusal, not an unknown outcome: nothing was sent, so the desk is not blocked.
            from .broker import RejectedOrder

            raise RejectedOrder(f"no shadow book for desk {desk_id}")
        return broker

    def capabilities(self) -> set[str]:
        merged: set[str] = set()
        for broker in list(self.brokers.values()):
            merged |= set(broker.capabilities())
        return merged

    def quote(self, instrument: Instrument):
        for broker in list(self.brokers.values()):
            return broker.quote(instrument)
        return None

    def balance(self):
        for broker in list(self.brokers.values()):
            return broker.balance()
        return None

    def positions(self) -> list[Any]:
        out: list[Any] = []
        for broker in list(self.brokers.values()):
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
        for broker in list(self.brokers.values()):
            try:
                return getattr(broker, method)(*args)
            except Exception:
                continue
        raise KeyError(f"unknown order {order_id}")

    def open_orders(self) -> list[Any]:
        out: list[Any] = []
        for broker in list(self.brokers.values()):
            out.extend(broker.open_orders())
        return out

    def fills(self, since: str | None = None) -> list[Any]:
        out: list[Any] = []
        for broker in list(self.brokers.values()):
            out.extend(broker.fills(since))
        return out

    def settle_event(self, market_id: str, payout_per_contract: Any, *, now: Any = None) -> list[Any]:
        """Settle one resolved market in every shadow book. A book with no position pays nothing.

        `payout_per_contract` is the **yes** value; each book pays its NO holdings the
        complement. Fanning out is safe because a book that never traded the market returns
        no fills, and it keeps the router from having to know which desk held what.
        """
        out: list[Any] = []
        for broker in list(self.brokers.values()):
            settle = getattr(broker, "settle_event", None)
            if settle is None:
                continue
            out.extend(settle(market_id, payout_per_contract, now=now))
        return out

    def tick(self) -> None:
        for broker in list(self.brokers.values()):
            ticker = getattr(broker, "tick", None)
            if ticker is not None:
                ticker()
