"""Specialties: every agent belongs to one niche for life, and its children inherit it.

A generalist spreads a small research budget over everything and learns nothing deeply. A
specialist spends all of it on one corner of one venue: the House shows it only that corner's
markets, refuses an entry outside it, hands its research loop a brief of what is known there, tags
what it writes so the niche's library compounds, and pays the niche floors of the economy by
specialty, so an empty niche is always worth entering and no niche can crowd out the rest.

`league/niches.json` is the list. A Kalshi universe is series tickers; an Alpaca universe is
symbols. A niche may be `dormant`: defined, briefed, and closed to agents until the House can
trade it (options, until it can quote them).

**Seasons.** What Kalshi lists changes with the calendar (the survey that seeded the file ran on
a football Saturday). So a Kalshi niche also carries `patterns`, and the House surveys the venue
once a day: a series it finds that matches a niche's patterns (and the category Kalshi itself
reports for it) joins that niche's universe, and every universe is re-ranked by what is trading
now. Niches are kept broad on purpose (one for all sports results): an agent specialises inside
one by the series its strategy names, and is shown the busiest live series when its own go dark.

**Open desks** (Sept 23, 2026, the owner: "I don't want to force the agents into any predefined
strategies"). One desk a venue (`kalshi-open`, `alpaca-open`) whose universe is every tradable market
there: any Kalshi series, any US stock or ETF, any coin Alpaca lists against the dollar (never an
option: that is the options desk's, under its rules). What makes it cheap is that an agent is still
shown only what its own NEEDS name, twelve at most, exactly as on any desk; a strategy that names
nothing it may trade is shown a capped discovery list (on Kalshi the daily survey's busiest series,
those no desk covers first), never the venue. `match` seats a program on a specific desk whenever one
desk holds most of what it names, and on the open desk only when it spans desks or names markets no
desk lists (`spanning`). Its seats are few (8 on Kalshi; 12 on Alpaca from Sept 25, 2026) and crowding is the allocator's to price.
"""

from __future__ import annotations

import ast
import json
import pprint
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

NICHES_PATH = Path(__file__).resolve().parent / "niches.json"
#: What one strategy may ask the House to show it (each series is a venue call a wake).
MAX_UNIVERSE = 12
#: And what it may WATCH beside that, on either venue, without being allowed to trade it.
MAX_OBSERVED = 6
#: How long an open desk's discovery list is: what a strategy naming nothing it may trade is shown
#: (the first MAX_UNIVERSE of it) and what its brief lists. Never the whole venue: measured Sept 23,
#: 2026, one pass over Kalshi's open markets resolving within 48 hours is 21 pages, 20,662 markets,
#: about 15 MB and 22 s, with 372 series trading -- the daily survey's work, never a wake's.
OPEN_DISCOVERY = 24
#: What an open desk may be asked to show or trade: a Kalshi series ticker (no "/": a coin pair is
#: Alpaca's); a US stock or ETF ticker as Alpaca spells it (`BRK.B`); a coin against the dollar.
_SERIES_NAME = re.compile(r"^[A-Z0-9][A-Z0-9._]{0,39}$")
_EQUITY_NAME = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")
_COIN_NAME = re.compile(r"^[A-Z0-9]{2,10}/USD$")


@dataclass
class Niche:
    id: str
    title: str
    venue: str  # alpaca | kalshi
    horizons: tuple[str, ...]
    listed: tuple[str, ...]  # Kalshi series tickers, or Alpaca symbols, as niches.json lists them
    brief: str
    founders: tuple[dict[str, Any], ...] = ()
    asset_class: str = "event"
    maker_fee_series: tuple[str, ...] = ()
    dormant: bool = False
    dormant_reason: str = ""
    patterns: tuple[str, ...] = ()
    category: str = ""
    desk: str = ""  # the partner whose desk this is: every agent of it is numbered from this name
    desk_note: str = ""  # who that partner was
    max_members: int = 5
    #: False where the House cannot replay history (options: no recorded chains). Paper is then
    #: the specialty's replay: a newcomer starts its forward test at once, on practice money.
    replay: bool = True
    #: The daily survey's answer: the series of this niche trading now, busiest first. For an open
    #: desk, its discovery list (`OPEN_DISCOVERY` long).
    live: tuple[str, ...] = field(default=())
    #: An open desk: its universe is every tradable market of its venue (`admits`), and `listed`
    #: and `live` are only what it is shown when its strategy names nothing it may trade.
    open: bool = False
    #: What an open Alpaca desk may hold (`equity`, `crypto`; never `option`).
    asset_classes: tuple[str, ...] = ()
    #: Series an open desk refuses though the venue lists them (Kalshi's multivariate combos, which
    #: no listing the House reads shows).
    exclude: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return "series" if self.venue == "kalshi" else "symbols"

    @property
    def universe(self) -> tuple[str, ...]:
        """Everything inside the specialty: what is trading now first, then the rest of the list."""
        return tuple(dict.fromkeys(self.live + self.listed))

    def fits(self, series: str) -> bool:
        return any(re.search(pattern, series) for pattern in self.patterns)

    def admits(self, name: str) -> bool:
        """Whether a series (Kalshi) or symbol (Alpaca), as a strategy names it in NEEDS, is inside
        the specialty: in its universe, or for an open desk anything its venue could list."""
        name = str(name or "").strip().upper()
        if not self.open:
            return name in self.universe
        if self.venue == "kalshi":
            return bool(_SERIES_NAME.match(name)) and not any(re.search(p, name) for p in self.exclude)
        if _COIN_NAME.match(name):
            return "crypto" in self.asset_classes
        return bool(_EQUITY_NAME.match(name)) and "equity" in self.asset_classes

    def keeps_hours(self, needs: Mapping[str, Any] | None = None) -> bool:
        """Whether what this desk trades (for an open Alpaca desk: what `needs` names) keeps an
        exchange's session: equities and options do, coins and Kalshi markets do not."""
        if self.asset_class in ("equity", "option"):
            return True
        if self.open and self.venue == "alpaca":
            return any(not _COIN_NAME.match(str(s).upper()) for s in ((needs or {}).get("symbols") or []))
        return False

    def holds(self, instrument: Any) -> bool:
        """Whether this instrument is inside the specialty."""
        if self.open:
            # Any market of its own venue, of the classes it may hold: a Kalshi contract of any
            # series, a stock, an ETF or a coin against the dollar. Never another venue's.
            venue = str(getattr(instrument, "venue", "") or "")
            if venue and ("kalshi" if venue.startswith("kalshi") else "alpaca") != self.venue:
                return False
            if self.venue == "kalshi":
                ticker = str(getattr(instrument, "market_id", None) or instrument.symbol).upper()
                return getattr(instrument, "asset_class", "event") == "event" and self.admits(ticker.split("-", 1)[0])
            if getattr(instrument, "asset_class", "") not in self.asset_classes:
                return False
            name = str(getattr(instrument, "market_id", None) or instrument.symbol).upper()
            return self.admits(name.replace("-", "/") if getattr(instrument, "asset_class", "") == "crypto" else name)
        if self.venue == "kalshi":
            ticker = str(getattr(instrument, "market_id", None) or instrument.symbol).upper()
            return ticker.split("-", 1)[0] in self.universe
        if getattr(instrument, "asset_class", "") != self.asset_class:
            return False
        if self.asset_class == "option":
            return str(instrument.symbol).upper() in self.universe  # an option's symbol is its underlying
        name = str(getattr(instrument, "market_id", None) or instrument.symbol).upper().replace("-", "/")
        return name in self.universe or str(instrument.symbol).upper() in self.universe

    def text(self) -> str:
        """What a member's research loop is told about its specialty."""
        lines = [f"YOUR SPECIALTY: {self.title} ({self.id}). You are of the {self.desk.title()} desk"
                 + (f", named for {self.desk_note}." if self.desk_note else "."), self.brief]
        if self.open:
            return "\n".join(lines + self._open_text())
        if self.venue == "kalshi":
            if self.maker_fee_series:
                lines.append("These series charge a MAKER fee as well as the taker fee, so a resting bid is not free there: "
                             + ", ".join(self.maker_fee_series) + ". The other series of this specialty charge makers nothing.")
            else:
                lines.append("No series of this specialty charges a maker fee: a resting order that fills pays nothing.")
        lines.append(f"Your universe ({len(self.universe)}; a strategy may name at most {MAX_UNIVERSE} in NEEDS" + ("; busiest live series first" if self.live else "") + "): " + ", ".join(self.universe[:60]) + ("..." if len(self.universe) > 60 else "."))
        lines.append("You may WATCH what you like, on either venue, by naming it in NEEDS['observe'] "
                     "(up to 6 symbols and 6 series): the House shows it under ctx['observed'] live and in replay, "
                     "and you may not trade any of it. That is how a Kalshi strategy reads the spot price its "
                     "contracts settle against, or an Alpaca one reads a coin it does not trade.")
        lines.append("You may trade nothing outside it, and a child you fork inherits it. Spend your research here and only here: "
                     "what another specialty learns is theirs to use. Tag nothing; the House files what you write under your specialty.")
        return "\n".join(lines)

    def _open_text(self) -> list[str]:
        shown = list(self.universe[:OPEN_DISCOVERY])
        if self.venue == "kalshi":
            whole = ("EVERY series Kalshi lists (Kalshi's multivariate combos excepted): name the series tickers your "
                     f"strategy trades in NEEDS['series'], at most {MAX_UNIVERSE}, and the House shows you their open markets, "
                     "exactly as it shows any desk's. The horizon rule still holds: an entry must be expected to pay within "
                     "your horizon's hours.")
            try:
                from ltcm.sim import kalshi_fee_schedule

                makers = [s for s in shown if (kalshi_fee_schedule().get(s) or {}).get("maker")]
            except Exception:  # noqa: BLE001 - the schedule is advice here; the book charges by it anyway
                makers = []
            fees = ("Maker fees follow Kalshi's own schedule, series by series (the House's copy is ltcm/data/kalshi_fees.json, "
                    "and the book charges by it): a resting fill is free on most series and pays a quarter of the taker rate on "
                    "the rest" + (f"; of the series below, these charge makers: {', '.join(makers)}." if makers else "."))
            menu = "Busiest on the venue now, series no other desk covers first (the House's daily survey): "
        else:
            whole = ("EVERY US stock and ETF the account can trade, and every coin Alpaca lists against the dollar "
                     "(`XYZ/USD`), long only; never an option (options are the options desk's, under its rules). Name what your "
                     f"strategy trades in NEEDS['symbols'], at most {MAX_UNIVERSE}; stocks and coins may be mixed. The venue "
                     "judges what is tradable: an order in a symbol it does not list is refused, and you see the refusal.")
            fees = ""  # the desk's brief states them; they do not change with what is named
            menu = "Some of what the House already records history for, coins first: "
        lines = [f"Your universe is {whole}"] + ([fees] if fees else [])
        if shown:
            lines.append(menu + ", ".join(shown) + f". A strategy that names nothing it may trade here is shown the first {MAX_UNIVERSE} of these.")
        else:
            lines.append("There is no discovery list yet (the House has not surveyed the venue): a strategy that names nothing it may trade here is shown nothing.")
        lines.append("The House seats a program here only when no single desk holds most of what it names: a strategy that spans "
                     "desks, or trades markets no desk lists. One whose markets sit mostly on one desk belongs to that desk.")
        lines.append("You may WATCH what you like, on either venue, by naming it in NEEDS['observe'] (up to 6 symbols and 6 series): "
                     "the House shows it under ctx['observed'] live and in replay, and you may not trade any of it.")
        lines.append("A child you fork inherits this desk. Tag nothing; the House files what you write under it.")
        return lines


def load(path: Path | None = None) -> dict[str, Niche]:
    doc = json.loads((path or NICHES_PATH).read_text(encoding="utf-8"))
    out: dict[str, Niche] = {}
    for row in doc["niches"]:
        venue = str(row["venue"])
        universe = tuple(str(x).upper() for x in (row.get("series") if venue == "kalshi" else row.get("symbols")) or ())
        horizons = tuple(row.get("horizons") or ())
        is_open = row.get("open") is True
        if venue not in ("alpaca", "kalshi") or not (universe or is_open) or not horizons or any(h not in ("hour", "day") for h in horizons):
            raise ValueError(f"niches.json: {row.get('id')!r} needs a venue, a universe and horizons of hour or day")
        if row["id"] in out:
            raise ValueError(f"niches.json: {row['id']!r} is listed twice")
        classes = tuple(str(x) for x in (row.get("asset_classes") or (("equity", "crypto") if venue == "alpaca" else ("event",)))) if is_open else ()
        if is_open and (row.get("asset_class") or row.get("patterns") or row.get("founders")
                        or not set(classes) <= ({"equity", "crypto"} if venue == "alpaca" else {"event"})):
            # An open desk has no one asset class, claims no series by pattern (every series is
            # already its own), holds no options (the options desk's rules) and plants no strategy.
            raise ValueError(f"niches.json: the open desk {row['id']!r} takes asset_classes (equity, crypto; never options), "
                             "and no asset_class, patterns or founders")
        out[row["id"]] = Niche(
            id=str(row["id"]), title=str(row["title"]), venue=venue, horizons=horizons, listed=universe, brief=str(row["brief"]),
            patterns=tuple(row.get("patterns") or ()), category=str(row.get("category") or ""), max_members=int(row.get("max_members") or 5),
            desk=str(row["desk"]), desk_note=str(row.get("desk_note") or ""),
            replay=bool(row.get("replay", True)),
            founders=tuple(row.get("founders") or ()),
            asset_class=("event" if venue == "kalshi" else "any") if is_open else str(row.get("asset_class") or ("event" if venue == "kalshi" else "crypto")),
            maker_fee_series=tuple(row.get("maker_fee_series") or ()), dormant=row.get("status") == "dormant",
            dormant_reason=str(row.get("dormant_reason") or ""),
            open=is_open, asset_classes=classes, exclude=tuple(str(x) for x in (row.get("exclude_patterns") or ())),
        )
    # An open Alpaca desk that lists nothing of its own is shown, when its strategy names nothing it
    # may trade, what the other Alpaca desks list (the symbols the House records history for), coins
    # first because they trade at every hour. Derived, so it follows niches.json without an edit.
    for niche in out.values():
        if niche.open and niche.venue == "alpaca" and not niche.listed:
            rows = [n for n in out.values() if n.venue == "alpaca" and not n.open and n.asset_class in niche.asset_classes]
            rows.sort(key=lambda n: n.asset_class != "crypto")
            niche.live = tuple(dict.fromkeys(s for n in rows for s in n.listed))[:OPEN_DISCOVERY]
    return out


def constrain(needs: Mapping[str, Any], niche: Niche) -> dict[str, Any]:
    """A strategy's NEEDS, held to its specialty. The venue and the horizon must fit (a strategy
    cannot leave its niche by declaring another); what it asks to see is cut to the universe, and
    a strategy that names nothing inside it is shown the head of the universe instead."""
    out = dict(needs)
    venue, horizon = str(out.get("venue") or "").lower(), str(out.get("horizon") or "").lower()
    if venue != niche.venue:
        raise ValueError(f"the {niche.id} specialty trades {niche.venue}, not {venue or 'nothing'}")
    if horizon not in niche.horizons:
        raise ValueError(f"the {niche.id} specialty is judged by the {' or '.join(niche.horizons)}, not by the {horizon or '?'}")
    if niche.asset_class == "option":
        out["asset_class"] = "option"
    asked = [str(x).upper() for x in (out.get(niche.key) or [])]
    inside = [x for x in dict.fromkeys(asked) if niche.admits(x)]
    out[niche.key] = (inside or list(niche.universe))[:MAX_UNIVERSE]
    watched = out.get("observe") if isinstance(out.get("observe"), dict) else {}
    # What a strategy may WATCH is not held to its specialty: the whole point is to see what moves
    # its own markets. It may not trade any of it, which is the book's rule and the replay's.
    kept = {key: [str(x).upper() for x in (watched.get(key) or [])][:MAX_OBSERVED] for key in ("symbols", "series")}
    out["observe"] = {key: rows for key, rows in kept.items() if rows}
    if not out["observe"]:
        out.pop("observe")
    # The feeds the House records (`league/feeds.py`: sports, perps, vol, funding) are not held to the
    # specialty either: a crypto strike reads implied vol and perp funding, a game market its
    # scoreboard. Known feeds and keys only, six each, one spelling; what the House does not record
    # is dropped rather than left to fail.
    from .feeds import requested

    feeds = requested(out.get("feeds"))
    if feeds:
        out["feeds"] = feeds
    else:
        out.pop("feeds", None)
    return out


def match(needs: Mapping[str, Any], niches: Mapping[str, Niche]) -> Niche | None:
    """The open specialty a strategy with these NEEDS belongs to (the architect's strategies, the
    foundry's cards and the lab's graduates arrive with NEEDS and no specialty).

    A specific desk when one CLAIMS most of what the strategy names (more than half: in its
    universe, or fitting its patterns, as a new season's series does before the survey adds it) and
    can show it some of it now: it is shown that desk's markets and the stray names are cut, as
    always. A strategy whose markets are mostly one desk's but on a horizon that desk does not judge
    is placed as before (the desk of its horizon holding the most, or none): the open desk is not a
    way around a desk's clock. Otherwise the strategy spans desks, or names markets no desk lists,
    and belongs on its venue's open desk, where everything it names is kept. With no open desk for
    it (none listed, dormant, or an options strategy) the desk holding the most is the answer, as it
    always was, and one naming nothing any desk holds has none."""
    venue, horizon = str(needs.get("venue") or "").lower(), str(needs.get("horizon") or "").lower()
    wants_options = str(needs.get("asset_class") or "").lower() == "option"
    key = "series" if venue == "kalshi" else "symbols"
    asked = list(dict.fromkeys(str(x).upper() for x in (needs.get(key) or [])))
    best, score = None, 0      # the desk of this horizon holding the most now (file order on a tie)
    most, claimed = None, 0    # the desk of any horizon claiming the most
    shown = 0                  # how much of it that desk holds now
    desks, opened = [], []
    for niche in niches.values():
        if niche.dormant or niche.venue != venue:
            continue
        if (niche.asset_class == "option") != wants_options:
            continue  # an options strategy says so in NEEDS: the same tickers are an equity specialty's too
        if niche.open:
            if horizon in niche.horizons:
                opened.append(niche)
            continue
        desks.append(niche)
        inside = len(set(asked) & set(niche.universe))
        claims = sum(1 for x in asked if x in niche.universe or niche.fits(x))
        if claims > claimed:
            most, claimed, shown = niche, claims, inside
        if horizon in niche.horizons and inside > score:
            best, score = niche, inside
    if not opened:
        return best
    # A name no desk of the venue could hold (a typo, another venue's symbol) is no evidence either way.
    known = [x for x in asked if any(x in n.universe or n.fits(x) for n in desks) or any(n.admits(x) for n in opened)]
    if most is not None and 2 * claimed > len(known):
        if horizon not in most.horizons:
            return best
        if shown:
            return most
    return next((n for n in opened if any(n.admits(x) for x in asked)), None) or best


def spanning(needs: Mapping[str, Any], niches: Mapping[str, Niche]) -> Niche | None:
    """The open desk a program belongs on because it spans desks (no one desk holds most of what
    it names) or names markets no desk lists; None when a specific desk fits it, or nothing does.
    What the Alpha Lab asks before a graduate is born: `match` gives the desk either way."""
    home = match(needs, niches)
    return home if home is not None and home.open else None


# -------------------------------------------------------------------------------------- seasons

def survey(market_data: Any, *, hours: float = 48.0, clock: Callable[[], float] = time.time, max_pages: int = 120) -> dict[str, float]:
    """{series: contracts traded in 24 hours} over every open Kalshi market expected to stop
    trading or resolve within `hours`. One pass over the venue's open listing (about fifty pages
    on a busy Saturday), so it is run once a day and off the tick."""
    from .tapes import EARLY_CLOSE_SLACK_SECONDS, TapeError, parse_time, resolve_time

    now = float(clock())
    volumes: dict[str, float] = {}
    cursor = None
    for _ in range(max_pages):
        page = market_data.markets(status="open", limit=1000, cursor=cursor, min_close_ts=int(now),
                                   max_close_ts=int(now + hours * 3600) + EARLY_CLOSE_SLACK_SECONDS, mve_filter="exclude")
        rows = page.get("markets") if isinstance(page, dict) else None
        for row in rows or []:
            try:
                close_ts = parse_time(row.get("close_time"))
            except TapeError:
                continue
            stop = min(close_ts, resolve_time(row, close_ts)) if row.get("can_close_early") else close_ts
            if not now < stop <= now + hours * 3600:
                continue
            series = str(row.get("event_ticker") or row.get("ticker") or "").split("-", 1)[0].upper()
            if series:
                volumes[series] = volumes.get(series, 0.0) + float(row.get("volume_24h") or 0)
        cursor = page.get("cursor") if isinstance(page, dict) else None
        if not cursor or not rows:
            break
    return volumes


def apply_survey(niches: Mapping[str, Niche], volumes: Mapping[str, float], category_of: Callable[[str], str | None], *, min_volume: float = 2000.0) -> dict[str, list[str]]:
    """Set every Kalshi niche's `live` universe from a survey: its listed series that are trading,
    plus any other series that fits its patterns, trades at least `min_volume` contracts a day and
    is of its category (asked of Kalshi once per new series: a pattern alone could let a stranger in).
    A series belongs to the first niche that claims it. Returns {niche: live series}.

    An open Kalshi desk claims nothing: its `live` is its discovery list, the busiest series trading
    that no other desk claimed first, then the busiest of theirs, `OPEN_DISCOVERY` long."""
    ranked = sorted(volumes, key=lambda s: -volumes[s])
    claimed: set[str] = {s for niche in niches.values() if niche.venue == "kalshi" and not niche.open for s in niche.listed}
    out: dict[str, list[str]] = {}
    for niche in niches.values():
        if niche.venue != "kalshi" or niche.open:
            continue
        live = []
        for series in ranked:
            if series in niche.listed:
                live.append(series)
            elif series not in claimed and volumes[series] >= min_volume and niche.fits(series):
                if not niche.category or category_of(series) == niche.category:
                    live.append(series)
                    claimed.add(series)
        niche.live = tuple(live)
        out[niche.id] = live
    for niche in niches.values():
        if niche.venue != "kalshi" or not niche.open:
            continue
        busy = [s for s in ranked if volumes[s] >= min_volume and niche.admits(s)]
        live = ([s for s in busy if s not in claimed] + [s for s in busy if s in claimed])[:OPEN_DISCOVERY]
        niche.live = tuple(live)
        out[niche.id] = live
    return out


# ------------------------------------------------------------------------------------ founders

def _literal_span(tree: ast.Module, name: str) -> tuple[int, int, Any] | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], "id", None) == name:
            return node.lineno - 1, node.end_lineno, ast.literal_eval(node.value)
    return None


def founder_code(seed_code: str, niche: Niche, founder: Mapping[str, Any]) -> str:
    """A seed's program, re-pointed at a specialty: its NEEDS and PARAMS literals are rewritten
    (a strategy reads its own NEEDS in the box, so the file itself must say what it trades), and
    a header says where it came from. The program below the literals is the seed's, untouched."""
    lines = seed_code.splitlines()
    tree = ast.parse(seed_code)
    for name, overrides in (("PARAMS", founder.get("params") or {}), ("NEEDS", founder.get("needs") or {})):
        found = _literal_span(tree, name)
        if found is None:
            raise ValueError(f"the seed has no {name} literal")
        start, end, value = found
        merged = {**value, **dict(overrides)}
        if name == "NEEDS":
            merged["style"] = str(founder.get("style") or merged.get("style") or "general")
            merged = constrain(merged, niche) if (merged.get(niche.key) and set(map(str.upper, merged[niche.key])) & set(niche.universe)) else constrain({**merged, niche.key: []}, niche)
        lines[start:end] = (name + " = " + pprint.pformat(merged, width=110, sort_dicts=False)).splitlines()
        tree = ast.parse("\n".join(lines))
    header = [
        f"# SPECIALTY: {niche.id} ({niche.title}).",
        f"# Founder {founder['key']} of the {niche.desk.title()} desk: the {founder['seed']} seed's program, pointed at this specialty's markets. Where the notes",
        "# below speak of other markets, fees or evidence, they are the seed's: this founder's own evidence starts at zero.",
        "",
    ]
    return "\n".join(header + lines) + "\n"
