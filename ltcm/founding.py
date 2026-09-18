"""The firm hires itself: the floor founds new families, and winds down the founded ones that fail.

Every family the floor started with -- a founder manifest and its playbook -- was written by a
person. Evolution breeds variants inside a family, the lab runs directed experiments on one,
and the committee's gates move a shadow desk onto money; none of that can open a new line of
business. This module can, once a night:

* `coverage()` reads what the floor already does: each active family's venues, asset classes,
  the Kalshi series and Coinbase products its desks actually traded (fills and intents on the
  tape), its best desk's score and its P&L.
* `universe()` reads what the venues offer right now, as a digest of a few kilobytes: Kalshi's
  open markets by category and by series (counts, 24h volume, open interest) and Coinbase's USD
  spot products by 24h dollar volume. A listing that cannot be read is left out; a digest with
  nothing in it means no founding that night.
* `propose()` asks one model (Kimi K3 by default) for one new family: a manifest shaped like the
  founders', a playbook with a testable edge thesis, and the targets it will trade, which must be
  listed on a venue and untouched by the floor.
* `validate()` refuses anything outside the floor's bounds -- a live desk, a venue that is not
  open, a tool no founder carries, a limit outside the lab's hard limits, a name already taken, a
  target the floor already trades -- and publishes nothing for it; the service raises one alert.
* `found()` writes the manifest and the playbook the way `Evolution.spawn` writes a child
  (atomically, then re-loaded to prove it) at generation 1 with no parent, and appends a public
  `evolution.founded`. Evolution's `seed` breeds its shadow variants from there.
* `wind_down()` retires a *founded* family whole -- every desk gets `evolution.retired` with the
  reason "founded family wound down" -- when none of its desks is live, it is at least `min_days`
  old, and its best desk with `min_decisions` behind it has been active `min_days` and sits below
  `retire_below` percent cost-adjusted. A founded family that never reaches `min_decisions` on any
  desk within `idle_days` is wound down the same way. The families people wrote are never touched:
  a family is founded only when an `evolution.founded` names it and no human founder sits in it.

A founded desk is always born shadow. Real money stays behind the committee's existing gates.

`step()` is the non-blocking form the service calls every tick at the founding slot: the log is
read on the caller's thread, the venue listings and the model call run on a worker, and the
result is validated and written on a later tick. The request key is derived from the day, so a
restart in the middle re-reads the stored reply instead of paying twice. Standard library only.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from .broker import text
from .committee import capital_mode, promoted_desks, retired_desks
from .events import EventLog, canonical, now_iso
from .evolve import MODEL_PROFILES, Evolution, _atomic_write
from .lab import DEFAULT_CONFIG as LAB_DEFAULTS
from .ledger import iso_time, parse_iso
from .manifest import CADENCE_TRIGGERS, CLOCK, DESK_ID, DeskManifest, ManifestError, load_manifest
from .provider import PROFILES

FOUNDED_KIND = "evolution.founded"
WIND_DOWN_REASON = "founded family wound down"
#: The provider's budget key for the founding call. Not a desk: nothing is ever scored under it.
BUDGET_KEY = "founding"
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._\-]{0,39}$")
THESIS = re.compile(r"^#{1,4}\s*edge thesis\b", re.IGNORECASE | re.MULTILINE)
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
#: Kalshi's multivariate combo series: thousands of parlays with next to no volume each.
MVE_PREFIX = "KXMVE"
#: The category line for the series too far down the volume ranking to be looked up.
TAIL = "(series not looked up)"
STABLECOINS = frozenset(
    {"USDT", "USDC", "DAI", "PYUSD", "EURC", "USDS", "GUSD", "TUSD", "USDP", "FDUSD", "RLUSD", "USD1"}
)
#: What a desk on each venue may name in `instruments.asset_classes`, and what it must name.
#: A Kalshi desk may read crypto and index prices as reference (Scholes does); it trades events.
VENUE_CLASSES = {"kalshi": ("event", "crypto", "equity"), "coinbase": ("crypto", "future")}
VENUE_PRIMARY = {"kalshi": "event", "coinbase": "crypto"}
EFFORTS = ("low", "medium", "high")
LIMIT_KEYS = (
    "max_position_pct",
    "max_gross_pct",
    "max_order_notional_pct",
    "max_daily_loss_pct",
    "max_orders_per_day",
    "max_limit_deviation_pct",
)

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    #: Local time (the service's timezone), after the evolution run.
    "founding_time": "21:30",
    "max_per_day": 1,
    #: Founded families with at least one active desk. A wound-down family frees its slot.
    "max_founded_families": 8,
    #: A founded desk's notional scoring budget. It is shadow; nothing here is money.
    "capital_usd": "150",
    "min_days": 4,
    "min_decisions": 20,
    "retire_below": "-5",
    #: A founded family with no desk at `min_decisions` after this many days is wound down too;
    #: 0 switches the rule off.
    "idle_days": 10,
    "profile": "k3",
    "reasoning_effort": "high",
    "max_output_tokens": 24000,
    "budget_usd_per_day": "3.00",
    #: Venues a founded desk may name. The service passes the floor's `live_venues`.
    "live_venues": (),
    #: Limit bounds. The service passes the lab's configured `hard_limits`.
    "hard_limits": LAB_DEFAULTS["hard_limits"],
    "max_gross_pct": "4",
    "max_limit_deviation_pct": "0.30",
    "desk_budget_usd_per_day": "25",
    "desk_max_turns": 40,
    "desk_max_output_tokens": 16384,
    "max_sessions": 24,
    "min_session_gap_minutes": 30,
    "playbook_max_bytes": 12_000,
    "rationale_chars": 1500,
    "id_max_chars": 24,
    "max_targets": 60,
    "universe_max_chars": 6000,
    "kalshi_series": 40,
    "coinbase_products": 30,
    "kalshi_market_pages": 60,
    "kalshi_category_lookups": 60,
    "coverage_days": 30,
    "examples": 4,
    "example_playbook_chars": 5000,
}


#: Names the floor's roles and streams already publish under.
RESERVED_IDS = frozenset({"meriwether", "committee", "evolution", "lab", "risk", "ops", "floor", "shadow", "settlement", "founding", "watch"})


class FoundingError(ValueError):
    """A proposal the floor refuses. The message is the reason, and it is safe to publish."""


# --------------------------------------------------------------------------- small helpers


def _clean(value: Any, limit: int) -> str:
    """A model-written string made safe for the site: no control characters, no "<", bounded."""
    cleaned = CONTROL.sub("", str(value or "")).replace("<", "‹").strip()
    return cleaned if len(cleaned) <= limit else cleaned[: max(0, limit - 1)].rstrip() + "…"


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _dollars(row: Mapping[str, Any], name: str) -> Decimal | None:
    """A Kalshi price in dollars: `{name}_dollars`, a parsed Decimal, or a raw row's integer cents."""
    fixed = _dec(row.get(name + "_dollars"))
    if fixed is not None:
        return fixed
    value = row.get(name)
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value) / 100
    return _dec(value)


def _number(value: Any, name: str) -> Decimal:
    number = _dec(value)
    if number is None:
        raise FoundingError(f"{name} must be a decimal string")
    return number


def _compact(value: Decimal | int | float | None) -> str:
    """`1234567` -> `1.2M`. Digest numbers are for reading, not for arithmetic."""
    number = float(value or 0)
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(number) >= size:
            return f"{number / size:.1f}{suffix}"
    return f"{number:.0f}"


def _minutes(clock: str) -> int:
    return int(clock[:2]) * 60 + int(clock[3:5])


def instrument_target(instrument: Any) -> tuple[str, str] | None:
    """`("kalshi", "KXHIGHNY")` for an event contract, `("coinbase", "BTC-USD")` for a coin."""
    if not isinstance(instrument, Mapping):
        return None
    asset_class = instrument.get("asset_class")
    raw = str(instrument.get("market_id") or instrument.get("symbol") or "").strip().upper()
    if not raw:
        return None
    if asset_class == "event":
        return "kalshi", raw.split("-")[0]
    if asset_class == "crypto":
        return "coinbase", raw if "-" in raw else f"{raw}-USD"
    return None


def parse_reply(body: str) -> dict[str, Any] | None:
    """The proposal object in a model reply: the outermost JSON object in the text.

    Tolerates prose and a fenced block around it. Returns None when there is no object.
    """
    raw = str(body or "")
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


# --------------------------------------------------------------------------- the founding


class Founding:
    """Found new families from what the venues list and the floor does not trade; wind down the
    founded ones that fail. Writes manifests and playbooks like `Evolution.spawn`, events on the
    `evolution` stream, and nothing else."""

    def __init__(
        self,
        log: EventLog,
        evolution: Evolution,
        *,
        provider: Any = None,
        clock: Callable[[], float] = time.time,
        config: Mapping[str, Any] | None = None,
        kalshi: Any = None,
        coinbase: Any = None,
        market_rows: Callable[[], Any] | None = None,
    ):
        self.log = log
        self.evolution = evolution
        self.provider = provider
        self.clock = clock
        self.config = {**DEFAULT_CONFIG, **dict(config or {})}
        #: Market data, or zero-argument callables that return it (the service's lazy sources).
        self.kalshi = kalshi
        self.coinbase = coinbase
        #: Kalshi market rows the caller already holds (the service's event index): the digest's
        #: fallback when the sweep of the venue reads nothing.
        self.market_rows = market_rows
        #: Tonight's work in flight: the worker thread and what it has gathered.
        self._job: dict[str, Any] | None = None

    # ------------------------------------------------------------------ helpers
    def now(self) -> str:
        return now_iso(self.clock)

    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    def time(self) -> str:
        value = str(self.config.get("founding_time") or "21:30")
        return value if CLOCK.match(value) else "21:30"

    @staticmethod
    def _resolve(value: Any, method: str) -> Any:
        if value is None:
            return None
        if hasattr(value, method):
            return value
        if callable(value):
            try:
                value = value()
            except Exception:
                return None
        return value if value is not None and hasattr(value, method) else None

    def kalshi_source(self) -> Any:
        return self._resolve(self.kalshi, "markets")

    def coinbase_source(self) -> Any:
        return self._resolve(self.coinbase, "products")

    # ------------------------------------------------------------------ the record
    def founded_records(self) -> dict[str, dict[str, Any]]:
        """family -> its `evolution.founded` payload (with `at`), first founding wins."""
        out: dict[str, dict[str, Any]] = {}
        for event in self.log.read(kind=FOUNDED_KIND, limit=10_000, newest=True):
            family = event.payload.get("family")
            if isinstance(family, str) and family not in out:
                out[family] = {**dict(event.payload), "at": event.at}
        return out

    def human_founders(self, manifests: Mapping[str, DeskManifest] | None = None) -> list[DeskManifest]:
        """Generation-one desks no `evolution.founded` names: the ones a person wrote."""
        manifests = manifests if manifests is not None else self.evolution.manifests()
        founded_ids = {str(r.get("desk_id")) for r in self.founded_records().values()}
        return sorted(
            (m for m in manifests.values() if m.generation == 1 and m.parent_id is None and m.id not in founded_ids),
            key=lambda m: m.id,
        )

    def founded_families(self) -> set[str]:
        """Families the floor founded. A family with a human founder in it never counts."""
        records = self.founded_records()
        human = {m.family for m in self.human_founders()}
        return {family for family in records if family not in human}

    def active_founded(self) -> set[str]:
        families = self.evolution.families()
        return {family for family in self.founded_families() if families.get(family)}

    def founded_since(self, at: str, hours: int = 24) -> int:
        cutoff = iso_time(parse_iso(at) - timedelta(hours=hours))
        return sum(1 for record in self.founded_records().values() if cutoff < str(record.get("at")) <= at)

    def refusal(self, now: Any = None, *, spend: bool = True) -> str | None:
        """Why tonight has no founding, or None when it may go ahead."""
        at = iso_time(now) if now is not None else self.now()
        if not self.enabled():
            return "founding is switched off"
        if self.provider is None:
            return "no model provider"
        if not tuple(self.config.get("live_venues") or ()):
            return "no live venues configured"
        if self.founded_since(at) >= int(self.config["max_per_day"]):
            return "a family was already founded in the last 24 hours"
        if len(self.active_founded()) >= int(self.config["max_founded_families"]):
            return "the floor is at its founded-family ceiling"
        if spend:
            try:
                spent = Decimal(str(self.provider.spent_today(BUDGET_KEY)))
            except Exception:
                spent = Decimal(0)
            if spent >= Decimal(str(self.config["budget_usd_per_day"])):
                return "today's founding budget is spent"
        return None

    # ------------------------------------------------------------------ coverage
    def coverage(self, now: Any = None) -> dict[str, Any]:
        """What the floor already does, family by family, from the manifests and the tape."""
        at = iso_time(now) if now is not None else self.now()
        since = iso_time(parse_iso(at) - timedelta(days=int(self.config["coverage_days"])))
        manifests = self.evolution.manifests()
        families = self.evolution.families()
        founded = self.founded_families()
        modes = promoted_desks(self.log)
        family_of = {m.id: m.family for m in manifests.values()}
        traded: dict[str, dict[str, Counter]] = {}
        for kind in ("broker.fill", "desk.intent"):
            for event in self.log.read(kind=kind, limit=10_000, newest=True):
                if event.at < since:
                    continue
                payload = event.payload
                desk_id = payload.get("desk_id")
                if not isinstance(desk_id, str) and event.stream.startswith("desk:"):
                    desk_id = event.stream[len("desk:"):]
                family = family_of.get(str(desk_id))
                target = instrument_target(payload.get("instrument"))
                if family is None or target is None:
                    continue
                traded.setdefault(family, {}).setdefault(target[0], Counter())[target[1]] += 1

        out: dict[str, Any] = {}
        covered: dict[str, set[str]] = {"kalshi": set(), "coinbase": set()}
        for family, variants in sorted(families.items()):
            seen = traded.get(family, {})
            for venue, counts in seen.items():
                covered.setdefault(venue, set()).update(counts)
            scores = {m.id: self.evolution.score(m.id, at) for m in variants}
            best = max(variants, key=lambda m: (scores[m.id], -int(m.generation), m.id))
            pnl = live_pnl = Decimal(0)
            live = 0
            for m in variants:
                state = self.evolution.ledger(m.id).state(at)
                result = state.equity - state.net_deposits
                pnl += result
                if capital_mode(m, modes) == "live":
                    live += 1
                    live_pnl += result
            founder = next((m for m in variants if m.generation == 1), min(variants, key=lambda m: (m.generation, m.id)))
            out[family] = {
                "founder": founder.id,
                "founded": family in founded,
                "desks": len(variants),
                "live_desks": live,
                "venues": sorted({v for m in variants for v in m.venues}),
                "asset_classes": sorted({c for m in variants for c in m.instruments.asset_classes}),
                "traded": {
                    venue: [[name, count] for name, count in counts.most_common(12)]
                    for venue, counts in sorted(seen.items())
                },
                "best_desk": best.id,
                "best_score": text(scores[best.id]),
                "pnl_usd": text(pnl.quantize(Decimal("0.01"))),
                "live_pnl_usd": text(live_pnl.quantize(Decimal("0.01"))),
                "mandate": founder.mandate[:300],
            }
        return {
            "as_of": at,
            "families": out,
            "covered": {venue: sorted(names) for venue, names in covered.items()},
        }

    # ------------------------------------------------------------------ the universe
    def universe(self, now: Any = None, *, coverage: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """What Kalshi and Coinbase list right now, as a digest of at most `universe_max_chars`.

        Returns `{"text", "kalshi_series", "series_category", "coinbase_products", "errors"}`.
        `text` is empty when neither venue could be read: no digest, no founding.
        """
        at = iso_time(now) if now is not None else self.now()
        errors: list[str] = []
        kalshi = self._kalshi_universe(errors)
        coinbase = self._coinbase_universe(errors)
        covered = dict((coverage or {}).get("covered") or {})
        owners: dict[tuple[str, str], list[str]] = {}
        for family, row in ((coverage or {}).get("families") or {}).items():
            for venue, pairs in (row.get("traded") or {}).items():
                for name, _ in pairs:
                    owners.setdefault((venue, str(name)), []).append(family)
        text_body = self._render_universe(at, kalshi, coinbase, covered, owners)
        return {
            "text": text_body,
            "kalshi_series": sorted(kalshi["series"]) if kalshi else [],
            "series_category": {k: v["category"] for k, v in kalshi["series"].items() if v["category"]} if kalshi else {},
            "coinbase_products": sorted(coinbase["products"]) if coinbase else [],
            "errors": errors,
        }

    def _kalshi_universe(self, errors: list[str]) -> dict[str, Any] | None:
        """Kalshi's open markets by series, and the categories of the series that carry the volume.

        The rows are a sweep of `/markets` with the multivariate combos excluded (tens of thousands
        of near-empty parlays that would otherwise fill every page), folded a page at a time; the
        market index the caller holds is the fallback when the sweep reads nothing. Categories live
        on the series, one small read each, so only the top `kalshi_category_lookups` series by
        dollar volume are looked up and the long tail is counted as one line.
        """
        source = self.kalshi_source()
        if source is None:
            return None
        series: dict[str, dict[str, Any]] = {}
        read = 0
        cursor = None
        for _ in range(int(self.config["kalshi_market_pages"])):
            page = None
            for attempt in range(3):
                try:
                    try:
                        page = source.markets(status="open", limit=1000, cursor=cursor, mve_filter="exclude")
                    except TypeError:  # a source that cannot filter; the combos are skipped in the fold
                        page = source.markets(status="open", limit=1000, cursor=cursor)
                    break
                except Exception as exc:
                    # A page refused mid-sweep (the floor's own index sweep shares Kalshi's rate
                    # limit) is asked again after a pause; a sweep cut short leaves the model a
                    # partial board and the validator a partial listing.
                    if attempt == 2:
                        errors.append(f"kalshi markets: {type(exc).__name__}")
                    else:
                        time.sleep(float(self.config.get("sweep_retry_pause_seconds", 2.0)) * (attempt + 1))
            if page is None:
                break
            rows = [r for r in (page.get("markets") or []) if isinstance(r, Mapping)]
            read += len(rows)
            self._fold_markets(series, rows)
            cursor = page.get("cursor")
            if not cursor or not rows:
                break
        if not read and self.market_rows is not None:
            try:
                rows = [r for r in (self.market_rows() or []) if isinstance(r, Mapping)]
            except Exception as exc:
                rows = []
                errors.append(f"kalshi index: {type(exc).__name__}")
            self._fold_markets(series, rows)
        if not series:
            return None
        # Ranked by dollars traded, then contracts: a one-cent golf longshot trades millions of
        # contracts and a few hundred dollars.
        ranked = sorted(series, key=lambda k: (-series[k]["usd"], -series[k]["volume"], k))
        lookup = getattr(source, "series", None)
        looked_up = set(ranked[: int(self.config["kalshi_category_lookups"])]) if callable(lookup) else set()
        for name in ranked:
            if name not in looked_up:
                break
            try:
                meta = lookup(name)
            except Exception:
                continue
            if isinstance(meta, Mapping):
                series[name]["category"] = str(meta.get("category") or "") or None
                if meta.get("title"):
                    series[name]["title"] = str(meta["title"])
        categories: dict[str, dict[str, Any]] = {}
        for name, entry in series.items():
            key = entry["category"] or ("Uncategorized" if name in looked_up else TAIL)
            total = categories.setdefault(
                key, {"markets": 0, "series": 0, "volume": Decimal(0), "usd": Decimal(0), "oi": Decimal(0)}
            )
            total["markets"] += entry["markets"]
            total["series"] += 1
            for field in ("volume", "usd", "oi"):
                total[field] += entry[field]
        return {"series": series, "categories": categories, "markets": sum(e["markets"] for e in series.values())}

    @staticmethod
    def _fold_markets(series: dict[str, dict[str, Any]], rows: list[Mapping[str, Any]]) -> None:
        for row in rows:
            ticker = str(row.get("ticker") or "").upper()
            if not ticker:
                continue
            name = str(row.get("event_ticker") or row.get("series_ticker") or ticker).upper().split("-")[0]
            if name.startswith(MVE_PREFIX):
                continue
            entry = series.setdefault(
                name, {"category": None, "title": None, "markets": 0, "volume": Decimal(0), "usd": Decimal(0), "oi": Decimal(0)}
            )
            entry["markets"] += 1
            volume = _dec(row.get("volume_24h")) or _dec(row.get("volume_24h_fp")) or Decimal(0)
            price = _dollars(row, "last_price")
            if not price:
                bid, ask = _dollars(row, "yes_bid"), _dollars(row, "yes_ask")
                price = (bid + ask) / 2 if bid is not None and ask is not None else None
            entry["volume"] += volume
            entry["usd"] += volume * price if price else Decimal(0)
            entry["oi"] += _dec(row.get("open_interest")) or _dec(row.get("open_interest_fp")) or Decimal(0)
            if entry["title"] is None and row.get("title"):
                entry["title"] = str(row.get("title"))

    def _coinbase_universe(self, errors: list[str]) -> dict[str, Any] | None:
        source = self.coinbase_source()
        if source is None:
            return None
        try:
            rows = source.products(product_type="SPOT", limit=None)
        except Exception as exc:
            errors.append(f"coinbase products: {type(exc).__name__}")
            return None
        products: dict[str, dict[str, Decimal]] = {}
        for row in rows or []:
            if not isinstance(row, Mapping):
                continue
            if str(row.get("quote_currency_id") or "").upper() != "USD":
                continue
            if str(row.get("base_currency_id") or "").upper() in STABLECOINS:
                continue
            if str(row.get("status") or "online").lower() != "online" or row.get("trading_disabled"):
                continue
            price = _dec(row.get("price"))
            product = str(row.get("product_id") or "").upper()
            if not product or price is None or price <= 0:
                continue
            volume = _dec(row.get("volume_24h")) or Decimal(0)
            products[product] = {"price": price, "usd": volume * price}
        return {"products": products} if products else None

    def _render_universe(
        self,
        at: str,
        kalshi: Mapping[str, Any] | None,
        coinbase: Mapping[str, Any] | None,
        covered: Mapping[str, Any],
        owners: Mapping[tuple[str, str], list[str]],
    ) -> str:
        if not kalshi and not coinbase:
            return ""
        limit = int(self.config["universe_max_chars"])

        def tag(venue: str, name: str) -> str:
            families = owners.get((venue, name))
            if families:
                return f" [floor: {', '.join(sorted(set(families)))}]"
            return " [floor]" if name in set(covered.get(venue) or ()) else ""

        head = [f"# What the venues list, {at[:16]}Z"]
        categories: list[str] = []
        series_lines: list[str] = []
        if kalshi:
            series = kalshi["series"]
            volume = sum((e["volume"] for e in series.values()), Decimal(0))
            usd = sum((e["usd"] for e in series.values()), Decimal(0))
            oi = sum((e["oi"] for e in series.values()), Decimal(0))
            head.append(
                f"## Kalshi: {kalshi['markets']} open markets in {len(series)} series; 24h volume "
                f"{_compact(volume)} contracts (~${_compact(usd)}), open interest {_compact(oi)}"
            )
            categories.append("Categories (markets / series / 24h contracts / ~24h $ / open interest):")
            ranked = sorted(
                kalshi["categories"].items(), key=lambda kv: (kv[0] == TAIL, -kv[1]["usd"], -kv[1]["volume"], kv[0])
            )
            for name, row in ranked[:20]:
                categories.append(
                    f"- {_clean(name, 40)}: {row['markets']} / {row['series']} / {_compact(row['volume'])} / "
                    f"${_compact(row['usd'])} / {_compact(row['oi'])}"
                )
            series_lines.append(
                "Top series by ~24h dollar volume (series, category: markets, 24h contracts, ~$, open interest, title):"
            )
            top = sorted(series.items(), key=lambda kv: (-kv[1]["usd"], -kv[1]["volume"], kv[0]))
            for name, row in top[: int(self.config["kalshi_series"])]:
                title = f' "{_clean(row["title"], 48)}"' if row.get("title") else ""
                series_lines.append(
                    f"- {name}, {_clean(row['category'] or 'uncategorized', 24)}: {row['markets']} mkts, {_compact(row['volume'])} ct, "
                    f"~${_compact(row['usd'])}, OI {_compact(row['oi'])}.{title}{tag('kalshi', name)}"
                )
        coin_lines: list[str] = []
        if coinbase:
            products = coinbase["products"]
            coin_lines.append(
                f"## Coinbase: {len(products)} USD spot products online (stablecoins excluded); "
                f"top by 24h dollar volume"
            )
            top = sorted(products.items(), key=lambda kv: (-kv[1]["usd"], kv[0]))
            for name, row in top[: int(self.config["coinbase_products"])]:
                coin_lines.append(f"- {name} ${_compact(row['usd'])} @ {row['price'].normalize():f}{tag('coinbase', name)}")

        def body() -> str:
            return "\n".join(head + categories + series_lines + coin_lines)

        # Trim the long tails first, a line at a time, until the digest fits.
        while len(body()) > limit:
            if len(series_lines) > 11:
                series_lines.pop()
            elif len(coin_lines) > 11:
                coin_lines.pop()
            elif len(categories) > 9:
                categories.pop()
            else:
                break
        return body()[:limit]

    # ------------------------------------------------------------------ proposing
    def examples(self) -> str:
        """The human founders' manifests and playbooks, as the model's worked examples."""
        parts = []
        limit = int(self.config["example_playbook_chars"])
        for manifest in self.human_founders()[: int(self.config["examples"])]:
            playbook = self.evolution.read_playbook(manifest)
            parts.append(
                f"### {manifest.name} ({manifest.id}, family {manifest.family})\n"
                f"Manifest:\n```json\n{json.dumps(manifest.to_dict(), ensure_ascii=False)}\n```\n"
                f"Playbook:\n```markdown\n{playbook[:limit]}\n```"
            )
        return "\n\n".join(parts) if parts else "(none)"

    def history(self) -> str:
        """Families founded before and what became of them, so a failed idea is not re-run."""
        records = self.founded_records()
        if not records:
            return "(none yet)"
        active = self.evolution.families()
        lines = []
        for family, record in sorted(records.items(), key=lambda kv: str(kv[1].get("at"))):
            state = "active" if active.get(family) else "wound down"
            lines.append(
                f"- {family} ({record.get('desk_id')}, founded {str(record.get('at'))[:10]}, {state}): "
                f"{_clean(record.get('universe'), 160)}. {_clean(record.get('rationale'), 240)}"
            )
        return "\n".join(lines[-12:])

    def instructions(self) -> str:
        cfg = self.config
        hard = cfg["hard_limits"]
        tools = ", ".join(sorted(self.founder_tools()))
        venues = ", ".join(sorted(str(v) for v in cfg.get("live_venues") or ()))
        return (
            "You are the founding partner of a public, fully automated trading floor whose desks are AI "
            "models trading real money on Kalshi and Coinbase. Tonight you may found ONE new family: a line "
            "of business the floor does not cover yet. A family starts as one founder desk (a manifest) and "
            "its playbook. The floor breeds shadow variants of it, scores every one forward against real "
            "prices, and only the committee's pre-registered gates can ever move one onto real money. A "
            "founded family that loses is wound down whole.\n\n"
            "Rules, all checked by code; a proposal that breaks one is refused and nothing is founded:\n"
            "1. Target what the floor does not trade: Kalshi series or Coinbase USD spot products that are "
            "in tonight's listing and not marked [floor]. List them in \"targets\" (Kalshi series tickers "
            f"such as KXNFLGAME, Coinbase product ids such as PEPE-USD), 1 to {cfg['max_targets']}.\n"
            "2. The edge must be concrete and testable. The playbook must have a section headed "
            "\"## Edge thesis\" that states the mispricing, why it exists, the public data that prices it, "
            "the minimum edge after fees, and the result over the first twenty decisions that would prove "
            "the thesis wrong. Then: what the desk trades, how it prices, its session routine, when it passes.\n"
            f"3. venues: a subset of [{venues}]; the first is where it trades. asset_classes: event for Kalshi "
            "(crypto or equity only as reference prices), crypto for Coinbase. allow_short false. For a Kalshi "
            "family leave instruments.allow empty and name the series in the mandate; for a Coinbase family "
            "instruments.allow becomes the targets. min_price and min_adv_usd \"0\" unless you have a reason.\n"
            f"4. tools: only from [{tools}], and include propose_order.\n"
            "5. limits (decimal strings, fractions of desk equity): "
            + ", ".join(f"{k} {v[0]} to {v[1]}" for k, v in hard.items())
            + f", max_gross_pct at most {cfg['max_gross_pct']}, max_limit_deviation_pct at most "
            f"{cfg['max_limit_deviation_pct']}.\n"
            f"6. model: profile one of [{', '.join(MODEL_PROFILES)}], reasoning_effort one of "
            f"[{', '.join(EFFORTS)}], max_turns at most {cfg['desk_max_turns']}, max_output_tokens at most "
            f"{cfg['desk_max_output_tokens']}.\n"
            f"7. cadence: 1 to {cfg['max_sessions']} HH:MM sessions at least {cfg['min_session_gap_minutes']} "
            "minutes apart, timezone UTC or a region like America/New_York, weekdays_only false for venues "
            f"that never close, triggers only from [{', '.join(CADENCE_TRIGGERS)}].\n"
            f"8. capital: every founded desk is born shadow with a notional ${cfg['capital_usd']}. Never ask "
            f"for live. budget.usd_per_day at most {cfg['desk_budget_usd_per_day']}.\n"
            f"9. id and family: new lowercase slugs (letters, digits, single hyphens, at most {cfg['id_max_chars']} "
            "characters), used by no desk or family listed below. name: a short desk name in the house "
            "style, at most 60 characters. persona and mandate in the founders' style, no markup.\n"
            f"10. playbook_markdown: at most {cfg['playbook_max_bytes']} bytes, written to the desk itself.\n\n"
            "Reply with JSON only, in this shape: {\"family\": \"...\", \"id\": \"...\", \"name\": \"...\", "
            f"\"rationale\": \"why this line of business and why now, at most {cfg['rationale_chars']} "
            "characters\", \"universe\": \"what it trades, one line\", \"targets\": [\"...\"], \"manifest\": "
            "{the founders' manifest shape}, \"playbook_markdown\": \"...\"}. If nothing listed has an edge you "
            "can state and test, reply {\"decline\": \"the reason\"}."
        )

    def names_taken(self) -> str:
        manifests = self._all_manifests()
        records = self.founded_records()
        ids = sorted(set(manifests) | {str(r.get("desk_id")) for r in records.values()})
        families = sorted({m.family for m in manifests.values()} | set(records))
        return f"- desk ids: {', '.join(ids)}\n- families: {', '.join(families)}"

    def prepare(self, now: Any = None) -> dict[str, Any]:
        """Everything the proposal reads from the log and the disk, gathered on the caller's
        thread so the worker that waits on the model touches neither."""
        at = iso_time(now) if now is not None else self.now()
        return {
            "coverage": self.coverage(at),
            "instructions": self.instructions(),
            "examples": self.examples(),
            "history": self.history(),
            "names": self.names_taken(),
        }

    def packet(self, at: str, context: Mapping[str, Any], universe: Mapping[str, Any]) -> str:
        """The model's whole view: the floor, the names taken, earlier foundings, the listings,
        the bounds and the founders as worked examples. Pure string work."""
        coverage = context.get("coverage") or {}
        categories = dict(universe.get("series_category") or {})
        lines = []
        for family, row in sorted((coverage.get("families") or {}).items()):
            traded = []
            for venue, pairs in sorted((row.get("traded") or {}).items()):
                for name, count in pairs:
                    category = categories.get(name) if venue == "kalshi" else None
                    traded.append(f"{name}{f' ({category})' if category else ''} x{count}")
            lines.append(
                f"- {family}{' (founded by the floor)' if row.get('founded') else ''}: founder {row.get('founder')}, "
                f"{row.get('desks')} desks, {row.get('live_desks')} live; {', '.join(row.get('venues') or [])}; "
                f"{', '.join(row.get('asset_classes') or [])}. Best desk {row.get('best_desk')} score "
                f"{row.get('best_score')}; P&L ${row.get('pnl_usd')} (live ${row.get('live_pnl_usd')}). "
                f"Traded: {', '.join(traded) or 'nothing yet'}. Mandate: {row.get('mandate')}"
            )
        return "\n\n".join(
            [
                f"# Founding packet, {at} UTC",
                "## The floor today\n" + ("\n".join(lines) or "(no active families)"),
                "## Names already taken\n" + str(context.get("names") or "(none)"),
                "## Families founded before\n" + str(context.get("history") or "(none yet)"),
                str(universe.get("text") or ""),
                "## Hard limits\n" + json.dumps(self.config["hard_limits"], sort_keys=True),
                "## The founders, as examples of the shape (not of the target)\n"
                + str(context.get("examples") or "(none)"),
            ]
        )

    def propose(
        self,
        now: Any = None,
        *,
        context: Mapping[str, Any] | None = None,
        universe: Mapping[str, Any] | None = None,
        key: str | None = None,
        correction: Mapping[str, Any] | None = None,
        focus: str | None = None,
    ) -> dict[str, Any]:
        """One model call. Returns `{"proposal", "decline", "incomplete", "text"}`; raises what the
        provider raises. Blocking: the service reaches it through `step()`'s worker, never the tick.
        `correction` ({"text", "reason"}) hands the model its refused reply and the floor's reason,
        so a proposal that broke one rule is fixed rather than lost for the night."""
        at = iso_time(now) if now is not None else self.now()
        if self.provider is None:
            raise FoundingError("no model provider")
        context = context if context is not None else self.prepare(at)
        universe = universe if universe is not None else self.universe(at, coverage=context.get("coverage"))
        day = at[:10]
        packet = self.packet(at, context, universe)
        if focus:
            # A sweep founds several families in one night, one per uncovered area: the focus
            # names the area so parallel foundings do not all pick the same obvious target.
            packet += (
                f"\n\n## Tonight's focus\nFound the family in this area: {str(focus)[:200]}. Pick the targets inside "
                "it with the most volume and the most testable edge; if nothing there has an edge you can state, decline."
            )
        items = [
            {"role": "system", "content": str(context.get("instructions") or self.instructions())},
            {"role": "user", "content": packet},
        ]
        if correction:
            items.append({"role": "assistant", "content": str(correction.get("text") or "")[:60_000]})
            items.append({"role": "user", "content": (
                f"The floor refused that proposal: {correction.get('reason')}. Fix exactly that, keep "
                "everything else that was valid, and reply with the corrected JSON only."
            )})
        response = self.provider.respond(
            str(self.config["profile"]),
            items,
            tools=None,
            desk_id=BUDGET_KEY,
            session_id=f"founding-{day}",
            request_key=key or f"founding:{day}",
            reasoning_effort=str(self.config["reasoning_effort"]),
            max_output_tokens=int(self.config["max_output_tokens"]),
            desk_cap_usd_per_day=self.config["budget_usd_per_day"],
        )
        body = str(getattr(response, "output_text", "") or "")
        data = parse_reply(body)
        decline = data.get("decline") if isinstance(data, dict) else None
        return {
            "text": body,
            "incomplete": bool(getattr(response, "incomplete", False)),
            "decline": _clean(decline, 600) if isinstance(decline, str) and decline.strip() else None,
            "proposal": data if isinstance(data, dict) and not decline else None,
        }

    # ------------------------------------------------------------------ validation
    def founder_tools(self) -> set[str]:
        return {tool for manifest in self.human_founders() for tool in manifest.tools}

    def validate(
        self,
        proposal: Any,
        *,
        universe: Mapping[str, Any] | None = None,
        coverage: Mapping[str, Any] | None = None,
        now: Any = None,
    ) -> dict[str, Any]:
        """The proposal, normalized into a manifest that loads, or `FoundingError` with the reason.

        `universe`, when given, is what the targets must be listed in; `coverage` is what they
        must not overlap (read from the log when not given).
        """
        cfg = self.config
        if not isinstance(proposal, Mapping):
            raise FoundingError("the proposal must be an object")
        desk_id = proposal.get("id")
        family = proposal.get("family")
        id_max = int(cfg["id_max_chars"])
        for label, value in (("id", desk_id), ("family", family)):
            if not isinstance(value, str) or not DESK_ID.match(value) or len(value) > id_max:
                raise FoundingError(f"{label} must be a lowercase slug of at most {id_max} characters")
        name = proposal.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60 or "<" in name:
            raise FoundingError("name must be 1 to 60 characters without markup")
        rationale = proposal.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise FoundingError("a rationale is required")

        # ---- names: never reused, never mistakable for someone else's lineage
        manifests = self._all_manifests()
        records = self.founded_records()
        # The floor's own roles publish under these names (Meriwether signs the committee's
        # memos); a desk called by one would be mistaken for the role on the public tape. The
        # first K3 dry run on Sept 16, 2026 named its desk "meriwether".
        taken_ids = set(manifests) | {str(r.get("desk_id")) for r in records.values()} | RESERVED_IDS
        taken_families = {m.family for m in manifests.values()} | set(records)
        if desk_id in taken_ids:
            raise FoundingError(f"desk id {desk_id} is already taken")
        if family in taken_families:
            raise FoundingError(f"family {family} already exists")
        for other in taken_ids:
            if desk_id.startswith(other + "-") or other.startswith(desk_id + "-"):
                raise FoundingError(f"desk id {desk_id} reads as part of {other}'s lineage")
        if (self.evolution.playbooks_dir / f"{desk_id}.md").exists():
            raise FoundingError(f"a playbook named {desk_id}.md already exists")

        # ---- the playbook
        playbook = proposal.get("playbook_markdown")
        if not isinstance(playbook, str) or not playbook.strip():
            raise FoundingError("playbook_markdown must be non-empty markdown")
        playbook = playbook.strip() + "\n"
        max_bytes = int(cfg["playbook_max_bytes"])
        if len(playbook.encode("utf-8")) > max_bytes:
            raise FoundingError(f"playbook_markdown must be at most {max_bytes} bytes")
        if not THESIS.search(playbook):
            raise FoundingError("the playbook needs an \"## Edge thesis\" section")

        # ---- the manifest
        raw = proposal.get("manifest")
        if not isinstance(raw, Mapping):
            raise FoundingError("manifest must be an object")
        data: dict[str, Any] = json.loads(json.dumps(raw))
        for key, value in (("id", desk_id), ("family", family)):
            if data.get(key) not in (None, value):
                raise FoundingError(f"manifest.{key} differs from the proposal's {key}")
        data.update(
            schema_version=1, id=desk_id, family=family, name=name.strip(), generation=1, parent_id=None,
            playbook=f"playbooks/{desk_id}.md",
        )
        data.setdefault("memory_limit", 40)

        live_venues = {str(v) for v in cfg.get("live_venues") or ()}
        venues = data.get("venues")
        if not isinstance(venues, list) or not venues or not all(isinstance(v, str) for v in venues):
            raise FoundingError("venues must be a non-empty list")
        unknown = sorted(set(venues) - live_venues)
        if unknown:
            raise FoundingError(f"venues not open to the floor: {', '.join(unknown)}")

        instruments = data.get("instruments")
        if not isinstance(instruments, Mapping):
            raise FoundingError("instruments must be an object")
        instruments = dict(instruments)
        classes = instruments.get("asset_classes")
        if not isinstance(classes, list) or not classes:
            raise FoundingError("instruments.asset_classes must be a non-empty list")
        allowed_classes = {c for v in venues for c in VENUE_CLASSES.get(v, ())}
        stray = sorted(set(map(str, classes)) - allowed_classes)
        if stray:
            raise FoundingError(f"asset classes not traded on {', '.join(venues)}: {', '.join(stray)}")
        for venue in venues:
            if VENUE_PRIMARY.get(venue) not in classes:
                raise FoundingError(f"a desk on {venue} must name the {VENUE_PRIMARY.get(venue)} asset class")
        # A founded desk shorts only through futures (Sept 17, 2026: Coinbase CDE contracts);
        # spot and event contracts are never sold short, whatever the proposal says.
        if instruments.get("allow_short") and "future" not in classes:
            raise FoundingError("a founded desk may not short without a futures mandate")
        instruments["allow_short"] = bool(instruments.get("allow_short")) and "future" in classes
        instruments.setdefault("min_price", "0")
        instruments.setdefault("min_adv_usd", "0")
        if "kalshi" in venues and _number(instruments["min_price"], "instruments.min_price") > 1:
            raise FoundingError("instruments.min_price above $1 refuses every Kalshi contract")

        # ---- the targets: listed on a venue, untouched by the floor
        at = iso_time(now) if now is not None else self.now()
        targets = self._targets(proposal.get("targets"), venues, universe, coverage if coverage is not None else self.coverage(at))
        if "kalshi" in venues:
            # The risk engine matches an allow list against the exact symbol an order names, and
            # a Kalshi order may name a market ticker: a series allow list would refuse them all.
            instruments["allow"] = []
        elif venues == ["coinbase"]:
            allow = {str(s).strip().upper() for s in instruments.get("allow") or []}
            instruments["allow"] = sorted(allow | set(targets))
        data["instruments"] = instruments

        # ---- limits inside the lab's hard bounds
        limits = data.get("limits")
        if not isinstance(limits, Mapping):
            raise FoundingError("limits must be an object")
        stray = sorted(str(k) for k in limits if k not in LIMIT_KEYS)
        if stray:
            raise FoundingError(f"unknown limits: {', '.join(stray)}")
        hard = cfg["hard_limits"]
        normalized: dict[str, Any] = {}
        for key in LIMIT_KEYS:
            if key not in limits:
                if key == "max_limit_deviation_pct":
                    continue
                raise FoundingError(f"limits.{key} is required")
            value = limits[key]
            if key == "max_orders_per_day":
                low, high = (int(x) for x in hard.get(key, (1, 1000)))
                if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                    raise FoundingError(f"limits.max_orders_per_day must be an integer between {low} and {high}")
                normalized[key] = value
                continue
            number = _number(value, f"limits.{key}")
            if key in hard:
                low, high = (_number(x, key) for x in hard[key])
            else:
                low, high = Decimal("0.0001"), _number(cfg[key], key)
            if not low <= number <= high:
                raise FoundingError(f"limits.{key} must be between {low} and {high}")
            normalized[key] = format(number, "f")
        data["limits"] = normalized

        # ---- model, cadence, tools, budget, capital
        model = data.get("model")
        if not isinstance(model, Mapping):
            raise FoundingError("model must be an object")
        model = dict(model)
        if model.get("profile") not in MODEL_PROFILES:
            raise FoundingError(f"model.profile must be one of {', '.join(MODEL_PROFILES)}")
        if model.get("reasoning_effort", "medium") not in EFFORTS:
            raise FoundingError(f"model.reasoning_effort must be one of {', '.join(EFFORTS)}")
        for key, ceiling in (("max_turns", "desk_max_turns"), ("max_output_tokens", "desk_max_output_tokens")):
            value = model.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value > int(cfg[ceiling])):
                raise FoundingError(f"model.{key} must be an integer of at most {cfg[ceiling]}")
        data["model"] = model

        self._check_cadence(data.get("cadence"))

        tools = data.get("tools")
        if not isinstance(tools, list) or not tools:
            raise FoundingError("tools must be a non-empty list")
        allowed_tools = self.founder_tools()
        stray = sorted({str(t) for t in tools} - allowed_tools)
        if stray:
            raise FoundingError(f"tools no founder carries: {', '.join(stray)}")
        if "propose_order" not in tools:
            raise FoundingError("a founded desk needs propose_order")

        budget = data.get("budget")
        if not isinstance(budget, Mapping):
            raise FoundingError("budget must be an object")
        usd = _number(budget.get("usd_per_day"), "budget.usd_per_day")
        ceiling = _number(cfg["desk_budget_usd_per_day"], "desk_budget_usd_per_day")
        if not Decimal(0) < usd <= ceiling:
            raise FoundingError(f"budget.usd_per_day must be above 0 and at most {ceiling}")

        capital = data.get("capital") if isinstance(data.get("capital"), Mapping) else {}
        if capital.get("mode") not in (None, "shadow", "paper"):
            raise FoundingError("a founded desk is born shadow; capital.mode may not be live")
        cap = _number(cfg["capital_usd"], "capital_usd")
        amount = _number(capital.get("usd", cfg["capital_usd"]), "capital.usd")
        if not Decimal(0) < amount <= cap:
            raise FoundingError(f"capital.usd must be above 0 and at most {cap}")
        data["capital"] = {"mode": "shadow", "usd": format(amount, "f")}

        tags = [str(t) for t in data.get("tags") or [] if isinstance(t, str)]
        data["tags"] = list(dict.fromkeys([*tags, "founded"]))[:20]

        try:
            manifest = DeskManifest.from_dict(data)
        except ManifestError as exc:
            raise FoundingError(f"manifest invalid: {exc}") from None

        universe_line = proposal.get("universe")
        if not isinstance(universe_line, str) or not universe_line.strip():
            universe_line = f"{', '.join(venues)}: {', '.join(targets[:12])}"
        return {
            "id": desk_id,
            "family": family,
            "name": manifest.name,
            "rationale": _clean(rationale, int(cfg["rationale_chars"])),
            "universe": _clean(universe_line, 200),
            "targets": targets,
            "venues": list(manifest.venues),
            "asset_classes": list(manifest.instruments.asset_classes),
            "manifest": manifest.to_dict(),
            "playbook": playbook,
        }

    def _all_manifests(self) -> dict[str, DeskManifest]:
        """Every manifest under the desks directory, parked ones included: a parked desk's id and
        family come back when its venue opens, so they are taken."""
        out = dict(self.evolution.manifests())
        for path in sorted(self.evolution.manifests_dir.glob("*/*.json")):
            try:
                manifest = load_manifest(path)
            except (ManifestError, OSError):
                continue
            out.setdefault(manifest.id, manifest)
        return out

    def _targets(
        self,
        raw: Any,
        venues: list[str],
        universe: Mapping[str, Any] | None,
        coverage: Mapping[str, Any],
    ) -> list[str]:
        limit = int(self.config["max_targets"])
        if not isinstance(raw, list) or not raw or len(raw) > limit:
            raise FoundingError(f"targets must list 1 to {limit} Kalshi series or Coinbase products")
        targets = sorted({str(t).strip().upper() for t in raw})
        bad = [t for t in targets if not SYMBOL.match(t)]
        if bad:
            raise FoundingError(f"malformed targets: {', '.join(bad[:5])}")
        covered = coverage.get("covered") or {}
        listed = {
            "kalshi": set((universe or {}).get("kalshi_series") or ()),
            "coinbase": set((universe or {}).get("coinbase_products") or ()),
        }
        owned = {
            name
            for venue in venues
            for name in covered.get(venue) or ()
        }
        overlap = [t for t in targets if t in owned]
        if overlap and len(overlap) == len(targets):
            raise FoundingError(f"the floor already trades {', '.join(overlap[:5])}")
        # A few overlaps are not a reason to lose the family: the favorites strategy bids across
        # every category, so nearly any new area touches a series it has traded once (Sept 16,
        # 2026: a commodities family was refused over two gold and silver thresholds).
        targets = [t for t in targets if t not in owned]
        if universe is not None:
            known = set().union(*(listed[v] for v in venues if v in listed))
            missing = [t for t in targets if t not in known]
            if len(missing) == len(targets):
                raise FoundingError(f"targets not listed on {', '.join(venues)} tonight: {', '.join(missing[:5])}")
            # Some listed, some not: the family trades what is listed. A partial listing or a
            # series with no open market tonight is not a reason to lose a sound proposal.
            targets = [t for t in targets if t in known]
        return targets

    def _check_cadence(self, cadence: Any) -> None:
        cfg = self.config
        if not isinstance(cadence, Mapping):
            raise FoundingError("cadence must be an object")
        sessions = cadence.get("sessions")
        most = int(cfg["max_sessions"])
        if not isinstance(sessions, list) or not 1 <= len(sessions) <= most:
            raise FoundingError(f"cadence.sessions must list 1 to {most} times")
        if not all(isinstance(s, str) and CLOCK.match(s) for s in sessions) or len(set(sessions)) != len(sessions):
            raise FoundingError("cadence.sessions must be distinct HH:MM times")
        ordered = sorted(_minutes(s) for s in sessions)
        gap = int(cfg["min_session_gap_minutes"])
        pairs = list(zip(ordered, ordered[1:])) + ([(ordered[-1], ordered[0] + 24 * 60)] if len(ordered) > 1 else [])
        if any(b - a < gap for a, b in pairs):
            raise FoundingError(f"cadence.sessions must be at least {gap} minutes apart")
        tz = cadence.get("timezone", "America/New_York")
        try:
            ZoneInfo(str(tz))
        except Exception:
            raise FoundingError(f"cadence.timezone {str(tz)[:40]} is not a timezone") from None

    # ------------------------------------------------------------------ founding
    def found(self, proposal: Mapping[str, Any], now: Any = None) -> dict[str, Any]:
        """Write a validated proposal's manifest and playbook, then publish `evolution.founded`.

        Written like a spawned child: atomically, the manifest re-loaded to prove it, both files
        removed again if it does not load. The desk is generation 1, parentless and shadow.
        """
        at = iso_time(now) if now is not None else self.now()
        desk_id = str(proposal["id"])
        data = dict(proposal["manifest"])
        if data.get("capital", {}).get("mode") != "shadow" or data.get("generation") != 1 or data.get("parent_id"):
            raise FoundingError("only a validated proposal can be founded")
        playbook_path = self.evolution.playbooks_dir / f"{desk_id}.md"
        manifest_path = self.evolution.manifests_dir / f"{desk_id}.json"
        _atomic_write(playbook_path, str(proposal["playbook"]))
        _atomic_write(manifest_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        try:
            load_manifest(manifest_path)
        except ManifestError as exc:
            manifest_path.unlink(missing_ok=True)
            playbook_path.unlink(missing_ok=True)
            raise FoundingError(f"founded manifest {desk_id} did not load: {exc}") from None
        profile = str(self.config["profile"])
        payload = {
            "desk_id": desk_id,
            "family": str(proposal["family"]),
            "name": _clean(proposal["name"], 60),
            "rationale": _clean(proposal.get("rationale"), int(self.config["rationale_chars"])),
            "venues": list(proposal["venues"]),
            "asset_classes": list(proposal["asset_classes"]),
            "universe": _clean(proposal.get("universe"), 200),
            "model": PROFILES[profile][0] if profile in PROFILES else profile,
            "as_of": at,
        }
        try:
            self.log.append("evolution", FOUNDED_KIND, payload, id=f"founded:{desk_id}", at=at)
        except Exception:
            # Without its record the family would read as one a person wrote, and nothing could
            # ever wind it down. No record, no family.
            manifest_path.unlink(missing_ok=True)
            playbook_path.unlink(missing_ok=True)
            raise
        return {"action": "founded", **payload}

    # ------------------------------------------------------------------ winding down
    def wind_down(self, now: Any = None, *, apply: bool = True) -> list[dict[str, Any]]:
        """Retire every desk of each founded family that has failed. See the module docstring.
        `apply=False` names the desks it would retire and retires nothing."""
        at = iso_time(now) if now is not None else self.now()
        min_days = int(self.config["min_days"])
        min_decisions = int(self.config["min_decisions"])
        idle_days = int(self.config.get("idle_days") or 0)
        retire_below = Decimal(str(self.config["retire_below"]))
        records = self.founded_records()
        families = self.evolution.families()
        modes = promoted_desks(self.log)
        actions: list[dict[str, Any]] = []
        committee = None
        for family in sorted(self.founded_families()):
            variants = families.get(family) or []
            if not variants or any(capital_mode(m, modes) == "live" for m in variants):
                continue
            age = (parse_iso(at) - parse_iso(str(records[family]["at"]))).total_seconds() / 86400
            if age < min_days:
                continue
            committee = committee or self.evolution.committee()
            scored = []
            for manifest in variants:
                evidence = committee.gates(manifest.id, at)["evidence"]
                if int(evidence.get("decisions") or 0) < min_decisions:
                    continue
                excess = _dec(evidence.get("cost_adjusted_excess_pct")) or Decimal(0)
                scored.append((excess, manifest.id, int(evidence.get("days_live") or 0)))
            if scored:
                excess, _, days_live = max(scored)
                if days_live < min_days or excess >= retire_below:
                    continue
                anchor = excess
            elif idle_days and age >= idle_days:
                anchor = Decimal(0)  # no desk ever reached a judgeable record: the line never opened
            else:
                continue
            retired = retired_desks(self.log)
            for manifest in variants:
                if manifest.id in retired:
                    continue
                if not apply:
                    actions.append({"action": "would_retire", "desk_id": manifest.id, "family": family,
                                    "reason": WIND_DOWN_REASON, "best_excess_pct": text(anchor)})
                    continue
                actions.append(self.evolution.retire(manifest, at, median=anchor, reason=WIND_DOWN_REASON))
        return actions

    # ------------------------------------------------------------------ the nightly step
    def step(self, now: Any = None, *, day: str | None = None, key: str | None = None) -> dict[str, Any]:
        """One non-blocking unit of tonight's founding. `{"status": "pending"}` while the worker
        reads the venues and waits on the model; any other status means tonight is decided:
        `founded`, `declined`, `refused`, `skipped` or `failed`, with a `reason`."""
        at = iso_time(now) if now is not None else self.now()
        day = day or at[:10]
        job = self._job
        if job is not None and job["day"] != day:
            self._job = job = None  # a night left unfinished; its worker is a daemon
        if job is None:
            refusal = self.refusal(at)
            if refusal:
                return {"status": "skipped", "reason": refusal}
            if self.kalshi_source() is None and self.coinbase_source() is None:
                return {"status": "skipped", "reason": "no venue listings to read"}
            # Everything that reads the log or the disk happens here, on the caller's thread;
            # the worker only reads the venues and waits on the model.
            job = {"day": day, "at": at, "key": key or f"founding:{day}", "context": self.prepare(at)}
            job["thread"] = threading.Thread(target=self._work, args=(job,), name="founding", daemon=True)
            self._job = job
            job["thread"].start()
            return {"status": "pending"}
        if job["thread"].is_alive():
            return {"status": "pending"}
        self._job = None
        outcome = self._finish(job, at)
        reply = job.get("reply") or {}
        if outcome.get("status") == "refused" and not job.get("correction") and reply.get("proposal"):
            # One correction per night: the reason goes back to the model with its own reply.
            retry = {
                "day": day, "at": at, "key": f"{job['key']}:retry", "context": job["context"],
                "universe": job.get("universe"), "correction": {"text": reply.get("text"), "reason": outcome.get("reason")},
            }
            retry["thread"] = threading.Thread(target=self._work, args=(retry,), name="founding-retry", daemon=True)
            self._job = retry
            retry["thread"].start()
            return {"status": "pending"}
        return outcome

    def wait(self, timeout: float | None = None) -> None:
        job = self._job
        if job is not None:
            job["thread"].join(timeout)

    def run(self, now: Any = None, *, day: str | None = None, key: str | None = None) -> dict[str, Any]:
        """`step()` to the end, blocking. For scripts and tests; the service never waits."""
        at = iso_time(now) if now is not None else self.now()
        outcome = self.step(at, day=day, key=key)
        while outcome.get("status") == "pending":
            self.wait()
            outcome = self.step(at, day=day, key=key)
        return outcome

    def _work(self, job: dict[str, Any]) -> None:
        try:
            context = job["context"]
            universe = job.get("universe") or self.universe(job["at"], coverage=context["coverage"])
            job["universe"] = universe
            if not universe.get("text"):
                return
            job["reply"] = self.propose(job["at"], context=context, universe=universe, key=job["key"], correction=job.get("correction"))
        except Exception as exc:
            job["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"

    def _finish(self, job: Mapping[str, Any], at: str) -> dict[str, Any]:
        if job.get("error"):
            return {"status": "failed", "reason": _clean(job["error"], 400)}
        universe = job.get("universe") or {}
        if not universe.get("text"):
            return {"status": "skipped", "reason": "the venue listings could not be read"}
        return self.settle(job.get("reply") or {}, at, universe=universe, coverage=job["context"]["coverage"])

    def settle(
        self,
        reply: Mapping[str, Any],
        now: Any = None,
        *,
        universe: Mapping[str, Any] | None = None,
        coverage: Mapping[str, Any] | None = None,
        apply: bool = True,
    ) -> dict[str, Any]:
        """Validate a model reply and, with `apply`, found it. Never raises."""
        at = iso_time(now) if now is not None else self.now()
        if reply.get("incomplete"):
            return {"status": "failed", "reason": "the model's reply was cut off"}
        if reply.get("decline"):
            return {"status": "declined", "reason": reply["decline"]}
        proposal = reply.get("proposal")
        if not isinstance(proposal, Mapping):
            return {"status": "refused", "reason": "no proposal object in the model's reply"}
        family = _clean(proposal.get("family"), 40) if isinstance(proposal.get("family"), str) else None
        try:
            validated = self.validate(proposal, universe=universe, coverage=coverage, now=at)
        except FoundingError as exc:
            return {"status": "refused", "family": family, "reason": _clean(str(exc), 400)}
        except Exception as exc:  # a malformed value the checks above did not anticipate
            return {"status": "refused", "family": family, "reason": f"invalid proposal: {type(exc).__name__}"}
        if not apply:
            return {"status": "valid", "family": validated["family"], "desk_id": validated["id"], "proposal": validated}
        refusal = self.refusal(at, spend=False)  # the caps again: the night may have moved on
        if refusal:
            return {"status": "skipped", "family": validated["family"], "reason": refusal}
        try:
            action = self.found(validated, at)
        except Exception as exc:
            return {"status": "failed", "family": validated["family"], "reason": _clean(f"{type(exc).__name__}: {exc}", 400)}
        return {"status": "founded", **action}


def payload_bytes(payload: Mapping[str, Any]) -> int:
    """The canonical size of an event payload, for the site's limits."""
    return len(canonical(dict(payload)).encode("utf-8"))


__all__ = [
    "BUDGET_KEY",
    "DEFAULT_CONFIG",
    "FOUNDED_KIND",
    "Founding",
    "FoundingError",
    "WIND_DOWN_REASON",
    "instrument_target",
    "parse_reply",
    "payload_bytes",
]
