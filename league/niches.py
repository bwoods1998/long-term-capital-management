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
    #: The daily survey's answer: the series of this niche trading now, busiest first.
    live: tuple[str, ...] = field(default=())

    @property
    def key(self) -> str:
        return "series" if self.venue == "kalshi" else "symbols"

    @property
    def universe(self) -> tuple[str, ...]:
        """Everything inside the specialty: what is trading now first, then the rest of the list."""
        return tuple(dict.fromkeys(self.live + self.listed))

    def fits(self, series: str) -> bool:
        return any(re.search(pattern, series) for pattern in self.patterns)

    def holds(self, instrument: Any) -> bool:
        """Whether this instrument is inside the specialty."""
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


def load(path: Path | None = None) -> dict[str, Niche]:
    doc = json.loads((path or NICHES_PATH).read_text(encoding="utf-8"))
    out: dict[str, Niche] = {}
    for row in doc["niches"]:
        venue = str(row["venue"])
        universe = tuple(str(x).upper() for x in (row.get("series") if venue == "kalshi" else row.get("symbols")) or ())
        horizons = tuple(row.get("horizons") or ())
        if venue not in ("alpaca", "kalshi") or not universe or not horizons or any(h not in ("hour", "day") for h in horizons):
            raise ValueError(f"niches.json: {row.get('id')!r} needs a venue, a universe and horizons of hour or day")
        if row["id"] in out:
            raise ValueError(f"niches.json: {row['id']!r} is listed twice")
        out[row["id"]] = Niche(
            id=str(row["id"]), title=str(row["title"]), venue=venue, horizons=horizons, listed=universe, brief=str(row["brief"]),
            patterns=tuple(row.get("patterns") or ()), category=str(row.get("category") or ""), max_members=int(row.get("max_members") or 5),
            desk=str(row["desk"]), desk_note=str(row.get("desk_note") or ""),
            replay=bool(row.get("replay", True)),
            founders=tuple(row.get("founders") or ()), asset_class=str(row.get("asset_class") or ("event" if venue == "kalshi" else "crypto")),
            maker_fee_series=tuple(row.get("maker_fee_series") or ()), dormant=row.get("status") == "dormant",
            dormant_reason=str(row.get("dormant_reason") or ""),
        )
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
    inside = [x for x in dict.fromkeys(asked) if x in niche.universe]
    out[niche.key] = (inside or list(niche.universe))[:MAX_UNIVERSE]
    watched = out.get("observe") if isinstance(out.get("observe"), dict) else {}
    # What a strategy may WATCH is not held to its specialty: the whole point is to see what moves
    # its own markets. It may not trade any of it, which is the book's rule and the replay's.
    kept = {key: [str(x).upper() for x in (watched.get(key) or [])][:MAX_OBSERVED] for key in ("symbols", "series")}
    out["observe"] = {key: rows for key, rows in kept.items() if rows}
    if not out["observe"]:
        out.pop("observe")
    return out


def match(needs: Mapping[str, Any], niches: Mapping[str, Niche]) -> Niche | None:
    """The open specialty a strategy with these NEEDS belongs to: the one holding most of what it
    asks to see (the architect's strategies arrive with NEEDS and no specialty)."""
    venue, horizon = str(needs.get("venue") or "").lower(), str(needs.get("horizon") or "").lower()
    best, score = None, 0
    wants_options = str(needs.get("asset_class") or "").lower() == "option"
    for niche in niches.values():
        if niche.dormant or niche.venue != venue or horizon not in niche.horizons:
            continue
        if (niche.asset_class == "option") != wants_options:
            continue  # an options strategy says so in NEEDS: the same tickers are an equity specialty's too
        asked = {str(x).upper() for x in (needs.get(niche.key) or [])}
        inside = len(asked & set(niche.universe))
        if inside > score:
            best, score = niche, inside
    return best


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
    A series belongs to the first niche that claims it. Returns {niche: live series}."""
    ranked = sorted(volumes, key=lambda s: -volumes[s])
    claimed: set[str] = {s for niche in niches.values() if niche.venue == "kalshi" for s in niche.listed}
    out: dict[str, list[str]] = {}
    for niche in niches.values():
        if niche.venue != "kalshi":
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
