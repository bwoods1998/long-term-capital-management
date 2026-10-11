"""The `equity_universe` job: the point-in-time S&P 500 membership from a free source, and its audit.

Owner: package A of release E4. Protected (league/ops/ is FORBIDDEN to every role). The registry row is A's patch
(E4-SPEC 13; league/swarm/e4_patches/A.md): at the House's start and daily at 01:40Z, in a pause too (it reads the
gateway and writes its own directory).

THE HOUSE HAS NO OPEN-WEB EGRESS: public pages come through the gateway's reader, `POST /v1/web/fetch {"url", "agent"}`
(text types only, 2 MB of body, 200,000 characters of text), and Alpaca's assets through `GET /v1/alpaca/v2/assets/
<SYM>`.

THE SOURCE: github.com/fja05680/sp500 (MIT), file sp500_ticker_start_end.csv (ticker,start_date,end_date; a member on
d when start <= d and d < end: the end day is the day the name is out), at a PINNED commit (`PIN`: a commit sha is
not market data). The pin in force lives in `universe/SOURCE.json` once the job has run; it advances weekly
(`latest_commit`: GitHub's commits API, else the repository's Atom feed), only when the new file is the old one
grown (`append_only`) and the whole audit passes on it, else an alarm and the old pin stays.

THE PRESENT: changes after the file's `known_through` (the last date it names) come from the English Wikipedia's
table of changes to the index (`WIKI_PAGES`, tried in order: the table moved out of the constituents' article into
"Historical components of the S&P 500", and may move again; MediaWiki `action=parse`, `prop=wikitext`, the section
found by `prop=sections`, else the lead, else the whole page; the table is the one whose header names "Added" and
"Removed"). It is read newest first; a row applies when its removed ticker is a member and its added one is not, once
two runs at least `CONFIRM_HOURS` apart have both read it. THE TABLE MAY ARRIVE CUT (the reader answers at most
200,000 characters): only the COMPLETE rows above the cut are parsed, and the read is VERIFIED only when an unbroken
run of well-formed rows reaches back to `known_through`; else `wiki.verdict` "unverified": nothing new is applied
(the rows applied by earlier verified reads stand), a warning, and with `STALE_ALARM_DAYS` the alarm that stops
looks, so a table that outgrew the reader is never a silent stale universe.

HOW EACH SPELL ENDED (`exits`): "deal" when the change row's reason matches `league.xs.config.VANISH_DEAL`, "other"
when it does not, "unknown" when no complete row was read for it: a membership fact, never a price; counted beside
results, it sets no price (the pre-registered exit law).

ASSETS (`assign`, D2): REF aids 1..12 in `league.xs.config.REF` order, never members. A member asset is one spell,
or several joined: the same ticker out and back in within `RENAME_DAYS`, or a RENAME (D2r): spell a (ticker X, end e)
and spell b (ticker Y, start s) within `RENAME_DAYS` whose raw daily closes, X read `asof` inside a and Y `asof`
inside b, are equal on at least `RENAME_SESSIONS` common sessions and differ on none (`rename_test`; a spell whose
end the changes table shows as a removal, or whose start it shows as an addition, was an index change and is not
tested: the table lists no ticker change; a pair whose join falls in 2020 cannot be tested, 2020 is never fetched,
and stays two assets). Aids run from `FIRST_AID` up by (first spell
start, ticker) at the first build and are NEVER reused and never renumbered: a later run keeps every aid it gave, and
a new asset takes the next aid above them all. Only a spell with a member day the panel store can hold (2016-19, or
2021 on: `league.xs.config.SPANS`) is an asset.

THE AUDIT (`audit`; all must pass, else nothing is written and the last good universe stays): `source` (the pinned
file's sha256 equals the one recorded at its first fetch), `append_only`, `count` (`MEMBERS_MIN` to `MEMBERS_MAX`
members on every store session), `overlap` (no ticker in two overlapping spells), `assets` (at most
`ASSETS_MISSING_MAX` current members without an active, tradable Alpaca asset; each listed), `wiki_agreement`
(reported, never failing: the share of the changes table's rows of the file's last 365 days the file agrees with).

What it writes: `<state>/equity-daily/universe/` (league/xs/store.py's layout), every file to a temporary name then
renamed, owner-only, UNIVERSE_MANIFEST.json LAST: SALT (32 random bytes, written ONCE, never rewritten, never in a
request, a log, an event or a manifest: only its sha256's first 8 hex), SOURCE.json, spells.csv, assets.json,
tradable.json (the dateless 36-month union: scripts/gen_universe.py's only input), and beside them, outside the
manifest, `venue.json` (the venue's asset rows, read again weekly) and `joins.json` (the rename tests' answers), kept
as the run goes so a first night too long for one wall (`WALL_SHARE`) resumes the next. `remask` is the one other
writer: the panel job (league/ops/equity_panel.py) hands back what D19's acceptance says of each asset's bars.

The receipt carries counts and verdicts, never a ticker list, a date of a membership change, or a price. NOTHING HERE
IS EVER COMMITTED: the point-in-time table lives on the House only (the one committed list is the dateless tradable
union, `tradable`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

#: The source's pinned commit (40 hex): the first pin. The pin in force is `universe/SOURCE.json`'s once the job ran.
PIN = "a2430f2af0c79ddf0748e91de11bdeb1616ab5a7"
REPO = "fja05680/sp500"
FILE = "sp500_ticker_start_end.csv"
RAW = "https://raw.githubusercontent.com/fja05680/sp500/{commit}/sp500_ticker_start_end.csv"
ATOM = "https://github.com/fja05680/sp500/commits/master.atom"
COMMITS = "https://api.github.com/repos/fja05680/sp500/commits?path=sp500_ticker_start_end.csv&per_page=1"
WEB = "/v1/web/fetch"
ASSETS = "/v1/alpaca/v2/assets/"
AGENT = "equity_universe"
#: The changes table's articles, tried in order, and the MediaWiki endpoint.
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_PAGES = ("Historical components of the S&P 500", "List of S&P 500 companies")
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 900
MEMBERS_MIN, MEMBERS_MAX = 480, 520
ASSETS_MISSING_MAX = 10
#: D2r: two spells within this many calendar days are one asset when their bars agree on at least `RENAME_SESSIONS`.
RENAME_DAYS = 5
RENAME_SESSIONS = 20
#: The calendar days of bars a rename test reads on each side of the join, and how close two raw closes are "equal".
RENAME_WINDOW_DAYS = 45
RENAME_TOLERANCE = 1e-6
#: A change row applies once two runs at least this far apart have both read it.
CONFIRM_HOURS = 20
#: The tradable list is the union of every member of this many months (section 11).
UNION_MONTHS = 36
CHECKS = ("source", "append_only", "count", "overlap", "assets", "wiki_agreement")
#: The pin's advance and the venue's asset rows are read again once they are this old (days).
REFRESH_DAYS = 6.5
#: Alarms: the pin has not advanced for this long; the membership is this stale (the lane's
#: `membership_max_stale_days` default; `<state>/ops.json` `equity_universe.max_stale_days` over it).
PIN_ALARM_DAYS = 60
STALE_ALARM_DAYS = 45
#: Train-era exits "unknown" above this share: the haircut is being counted for probable deals.
UNKNOWN_EXITS_ALARM = 0.10
#: The first member aid (REF holds 1..12).
FIRST_AID = 100
#: A ticker as the venue and the gateway spell one (`gateway/lib/caps.mjs` STOCK_SYMBOL).
TICKER = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")
TRIES = 3
BACKOFF_S = (5, 20)
STORE_DIR = "equity-daily"
SOURCE_FILE = "SOURCE.json"
SPELLS_FILE = "spells.csv"
ASSETS_FILE = "assets.json"
TRADABLE_FILE = "tradable.json"
MANIFEST_FILE = "UNIVERSE_MANIFEST.json"
JOINS_FILE = "joins.json"
VENUE_FILE = "venue.json"
#: The share of its wall the job works for: past it the run stops with what it has kept (venue.json, joins.json) and
#: the next one goes on from there, so a first night that is too long for one wall still ends.
WALL_SHARE = 0.8
#: The venue's rows are kept every this many calls.
VENUE_KEEP_EVERY = 25
#: The files the manifest's sha256 covers (the salt is named only by its sha256's first 8 hex).
HASHED = (SOURCE_FILE, SPELLS_FILE, ASSETS_FILE, TRADABLE_FILE)
#: The masks only the bars can give (the panel job's, `remask`), and the venue's own.
BAR_MASKS = ("reused", "no_bars", "insane")
VENUE_MASK = "not_fractionable"

_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%Y-%m-%d")
_ATTRS = re.compile(r"^[\w\s\-:=\"';.#%]*$")
#: Templates whose first argument is what a cell shows (a ticker or a date).
_SHOWN = re.compile(r"^(dts|date table sorting|nowrap|nyse|nasdaq|nysesymbol|nasdaqsymbol|nyse link|nasdaq link|"
                    r"new york stock exchange|start date|abbr)$", re.I)


# ------------------------------------------------------------------------------------------------- small helpers
def _day(value: Any) -> dt.date | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def _iso(day: dt.date | None) -> str | None:
    return None if day is None else day.isoformat()


def _stamp(now: float) -> str:
    return dt.datetime.fromtimestamp(float(now), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch(text: Any) -> float | None:
    try:
        return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _ticker(text: Any) -> str:
    """A ticker as the venue spells it: upper case, a class after a dot (BRK-B and BRK/B are BRK.B)."""
    return re.sub(r"[-/ ]", ".", str(text or "").strip().upper())


def _spell(row: Sequence[Any]) -> tuple[str, dt.date, dt.date | None]:
    return (_ticker(row[0]), _day(row[1]), _day(row[2]) if len(row) > 2 else None)  # type: ignore[return-value]


def spans() -> tuple[tuple[dt.date, dt.date | None], ...]:
    """The panel store's spans, (first day, last day | None), from `league.xs.config.SPANS`."""
    from ..xs import config as xs_config

    return tuple((first, last) for _, first, last in xs_config.SPANS)


def in_store(start: dt.date, end: dt.date | None) -> bool:
    """Whether a spell [start, end) has a day the panel store can hold (a session of a span, now or later)."""
    return any((end is None or end > first) and (last is None or start <= last) for first, last in spans())


def store_sessions(last: dt.date) -> list[tuple[dt.date, bool]]:
    """Every session of the store's spans through `last`, with its early-close flag, oldest first: no 2020 day."""
    from ..equity import store as eq_store

    out: list[tuple[dt.date, bool]] = []
    for first, end in spans():
        through = last if end is None else min(end, last)
        if through >= first:
            out.extend(eq_store.nyse_sessions(first, through))
    return out


def quiet_now(now: float, need_s: float) -> str | None:
    """`league.xs.config.quiet(now, need_s)`: why a job that needs `need_s` seconds may not start now, or None. While
    package C's C0 is not in the release the answer is that it is not built: an E4 job is then skipped, never run at
    a wall and never a crash."""
    from ..xs import config as xs_config

    try:
        return xs_config.quiet(float(now), float(need_s))
    except NotImplementedError:
        return "league.xs.config.quiet is not built (package C's C0): no panel job starts without its quiet windows"


def _sha(data: bytes | str) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def _failed(error: str, **more: Any) -> dict[str, Any]:
    return {"status": "failed", "ok": False, "error": str(error)[:600], **more}


# ------------------------------------------------------------------------------------------------- the reader
def _read(gateway: Any, url: str, *, allow_truncated: bool = False) -> tuple[str, bool]:
    """(the page's text, whether it arrived cut). ValueError on a refusal, a non-2xx status, an answer that is not the
    reader's, and on a cut answer unless allowed."""
    try:
        answer = gateway.post(WEB, {"url": url, "agent": AGENT})
    except Exception as exc:  # noqa: BLE001 - the gateway's refusal, said by its kind (its text can hold the url)
        status = getattr(exc, "status", None)
        raise ValueError(f"the reader refused the page ({type(exc).__name__}"
                         f"{'' if status is None else f', HTTP {status}'})") from None
    if not isinstance(answer, Mapping):
        raise ValueError("the reader's answer is not an object")
    status = answer.get("status")
    if isinstance(status, bool) or not isinstance(status, int) or not 200 <= status < 300:
        raise ValueError(f"the page answered {status if isinstance(status, int) else 'no status'}")
    text = answer.get("text")
    if not isinstance(text, str):
        raise ValueError("the reader's answer has no text")
    cut = bool(answer.get("truncated"))
    if cut and not allow_truncated:
        raise ValueError("the page arrived cut (the reader's limit)")
    return text, cut


def web(gateway: Any, url: str, *, allow_truncated: bool = False) -> str:
    """The text of `url` through the gateway's reader. ValueError on a refusal or a non-2xx status, and on a
    `truncated` answer unless allowed."""
    return _read(gateway, url, allow_truncated=allow_truncated)[0]


# ------------------------------------------------------------------------------------------------- the spell file
def parse_spells(text: str) -> list[tuple[str, dt.date, dt.date | None]]:
    """(ticker, start, end | None) of the spell file's rows; ValueError on a malformed row (its number is named,
    never its content)."""
    out: list[tuple[str, dt.date, dt.date | None]] = []
    for number, line in enumerate(str(text).splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        cells = [c.strip() for c in line.split(",")]
        if number == 1 and cells and cells[0].lower() in ("ticker", "symbol"):
            continue
        ticker = _ticker(cells[0]) if cells else ""
        if len(cells) < 2 or len(cells) > 3 or not TICKER.match(ticker):
            raise ValueError(f"row {number} of the spell file is not ticker,start_date,end_date")
        try:
            start = dt.date.fromisoformat(cells[1][:10])
            end = dt.date.fromisoformat(cells[2][:10]) if len(cells) == 3 and cells[2] else None
        except ValueError:
            raise ValueError(f"row {number} of the spell file has a date that is not one") from None
        if end is not None and end <= start:
            raise ValueError(f"row {number} of the spell file ends before it starts")
        out.append((ticker, start, end))
    if not out:
        raise ValueError("the spell file holds no spell")
    return out


def known_through(spells: Iterable[Sequence[Any]]) -> dt.date:
    """The last date a spell list names (a start or an end): what the file knows the membership through."""
    days = [d for s in spells for d in (_day(s[1]), _day(s[2]) if len(s) > 2 else None) if d is not None]
    if not days:
        raise ValueError("the spells name no date")
    return max(days)


def append_only(old: Sequence[tuple], new: Sequence[tuple], known_through: dt.date) -> list[str]:  # noqa: A002
    """Why a new pin's spells are not the old ones grown (an empty list: they are): a new pin may only end open spells
    after `known_through` and add spells starting after it; a difference confined to spells that ended before
    2016-01-04, which no panel session reads, is not a problem (upstream corrects old dates, and the pin must not
    freeze for good on one)."""
    first = spans()[0][0]
    was, now = {_spell(s) for s in old}, {_spell(s) for s in new}
    ends = {(t, s): e for t, s, e in now}

    def dead(spell: tuple) -> bool:
        return spell[2] is not None and spell[2] <= first

    problems: list[str] = []
    read: set[tuple] = set()  # the new file's spells the first pass has judged
    for ticker, start, end in sorted(was - now, key=lambda s: (s[0], s[1])):
        if dead((ticker, start, end)):
            continue
        if (ticker, start) in ends:
            later = ends[(ticker, start)]
            read.add((ticker, start, later))
            if end is None and later is not None and later > known_through:
                continue  # an open spell ended after the old pin's last date: the file grown
            problems.append(f"{ticker}: {'an open' if end is None else 'an ended'} spell of the old pin has another "
                            "end")
        else:
            problems.append(f"{ticker}: {'an open' if end is None else 'an ended'} spell of the old pin is gone")
    for ticker, start, end in sorted(now - was, key=lambda s: (s[0], s[1])):
        if (ticker, start, end) in read or dead((ticker, start, end)) or start > known_through:
            continue
        problems.append(f"{ticker}: a spell the old pin does not have starts on or before its last date")
    return problems


def latest_commit(gateway: Any) -> str | None:
    """The source repository's newest commit (GitHub's commits API, else the Atom feed `ATOM`), or None."""
    try:
        rows = json.loads(web(gateway, COMMITS))
        sha = str(rows[0]["sha"]).strip().lower()
        if re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha
    except (ValueError, KeyError, IndexError, TypeError):
        pass  # refused (the reader's shared address is past the API's hourly allowance): the feed
    try:
        feed = web(gateway, ATOM, allow_truncated=True)
    except ValueError:
        return None
    found = re.search(r"Commit/([0-9a-f]{40})", feed) or re.search(r"/commit/([0-9a-f]{40})", feed)
    return found.group(1) if found else None


# ------------------------------------------------------------------------------------------------- the changes table
def _wiki_url(page: str, *, sections: bool = False, section: int | None = None) -> str:
    query = {"action": "parse", "page": page, "prop": "sections" if sections else "wikitext|revid", "format": "json",
             "formatversion": "2"}
    if section is not None:
        query["section"] = str(int(section))
    return WIKI_API + "?" + urllib.parse.urlencode(query)


def _json_string(text: str, at: int) -> tuple[str, bool]:
    """The JSON string that opens at `text[at]` (a quote): (its value as far as the text goes, whether it closed). A
    cut answer ends inside the string: what was read is kept, a broken last escape dropped."""
    out: list[str] = []
    i, n = at + 1, len(text)
    simple = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
    while i < n:
        j = i
        while j < n and text[j] not in '"\\':
            j += 1
        out.append(text[i:j])
        if j >= n:
            return "".join(out), False
        if text[j] == '"':
            return "".join(out), True
        if j + 1 >= n:
            return "".join(out), False
        mark = text[j + 1]
        if mark == "u":
            digits = text[j + 2:j + 6]
            if len(digits) < 4:
                return "".join(out), False
            try:
                code = int(digits, 16)
            except ValueError:
                return "".join(out), False
            i = j + 6
            if 0xD800 <= code <= 0xDBFF and text[i:i + 2] == "\\u" and len(text[i + 2:i + 6]) == 4:
                try:
                    low = int(text[i + 2:i + 6], 16)
                except ValueError:
                    low = 0
                if 0xDC00 <= low <= 0xDFFF:
                    code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                    i += 6
            out.append(chr(code) if not 0xD800 <= code <= 0xDFFF else "")
            continue
        out.append(simple.get(mark, mark))
        i = j + 2
    return "".join(out), False


def _wikitext(answer: str) -> tuple[str, bool, int | None]:
    """(the wikitext, whether it is whole, the revision id) of a MediaWiki `action=parse` answer that may be cut.
    ValueError when the answer names no wikitext or is MediaWiki's error."""
    revid = re.search(r'"revid"\s*:\s*(\d+)', answer)
    key = re.search(r'"wikitext"\s*:\s*(\{\s*"\*"\s*:\s*)?"', answer)
    if key is None:
        raise ValueError("the changes article's answer has no wikitext")
    text, closed = _json_string(answer, key.end() - 1)
    return text, closed, int(revid.group(1)) if revid else None


def _depth_split(text: str, mark: str) -> list[str]:
    """`text` split on `mark` wherever it stands outside [[links]], {{templates}} and <ref>...</ref>."""
    out, last, i, n = [], 0, 0, len(text)
    square = curly = 0
    ref = False
    step = len(mark)
    while i < n:
        two = text[i:i + 2]
        if ref:
            if text.startswith("</ref", i):
                ref = False
            i += 1
        elif two == "[[":
            square, i = square + 1, i + 2
        elif two == "]]":
            square, i = max(0, square - 1), i + 2
        elif two == "{{":
            curly, i = curly + 1, i + 2
        elif two == "}}":
            curly, i = max(0, curly - 1), i + 2
        elif text.startswith("<ref", i):
            close = text.find(">", i)
            ref = close >= 0 and text[close - 1] != "/"
            i = i + 4 if close < 0 else close + 1
        elif not square and not curly and text.startswith(mark, i):
            out.append(text[last:i])
            i += step
            last = i
        else:
            i += 1
    out.append(text[last:])
    return out


def _cell(piece: str) -> tuple[str, int, int]:
    """One cell: (its content, rowspan, colspan). `attributes | content` when what precedes the first bare pipe
    reads as attributes."""
    parts = _depth_split(piece, "|")
    attrs, content = "", piece
    if len(parts) > 1 and _ATTRS.match(parts[0]) and ("=" in parts[0] or not parts[0].strip()):
        attrs, content = parts[0], "|".join(parts[1:])
    spans_found = {name: int(found.group(1)) if (found := re.search(name + r"\s*=\s*[\"']?(\d+)", attrs, re.I)) else 1
                   for name in ("rowspan", "colspan")}
    return content.strip(), max(1, spans_found["rowspan"]), max(1, spans_found["colspan"])


def _plain(cell: str) -> str:
    """A cell's text as a reader sees it: references, comments and markup dropped, a link's label kept, a template
    that only dresses its first argument (a date, a ticker) read as that argument."""
    text = re.sub(r"<!--.*?-->", "", cell, flags=re.S)
    text = re.sub(r"<ref\b[^>]*/>", "", text, flags=re.I)
    text = re.sub(r"<ref\b[^>]*>.*?</ref\s*>", "", text, flags=re.I | re.S)
    text = re.sub(r"<ref\b[^>]*>.*$", "", text, flags=re.I | re.S)  # a reference the cut left open
    for _ in range(4):  # innermost templates first
        def shown(found: "re.Match[str]") -> str:
            parts = found.group(1).split("|")
            if not _SHOWN.match(parts[0].strip()):
                return ""
            args = [p.strip() for p in parts[1:] if "=" not in p]
            return " ".join(args) if parts[0].strip().lower() in ("dts", "date table sorting", "start date") else (
                args[0] if args else "")
        after = re.sub(r"\{\{([^{}]*)\}\}", shown, text)
        if after == text:
            break
        text = after
    text = re.sub(r"\[\[(?:[^\[\]|]*\|)?([^\[\]|]*)\]\]", r"\1", text)
    text = re.sub(r"\[\S+\s+([^\]]*)\]", r"\1", text)
    text = re.sub(r"<[^>]*>", " ", text)
    text = html.unescape(text.replace("'''", "").replace("''", ""))
    return re.sub(r"\s+", " ", text).strip()


def _wiki_date(text: str) -> dt.date | None:
    text = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    found = re.search(r"(\d{4})[ -](\d{1,2})[ -](\d{1,2})", text)  # {{dts|2024|6|24}}
    if found:
        try:
            return dt.date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
        except ValueError:
            return None
    return None


def _changes_table(wikitext: str) -> tuple[str, bool] | None:
    """(the changes table's text without its closing line, whether its closing line was read): the first table whose
    header names "Added" and "Removed". None when the text holds none."""
    for found in re.finditer(r"(?m)^\{\|", wikitext):
        end = re.compile(r"(?m)^\|\}").search(wikitext, found.start())
        body = wikitext[found.start():end.start() if end else len(wikitext)]
        head = body[:2000].lower()
        if "added" in head and "removed" in head:
            return body, end is not None
    return None


def parse_changes(wikitext: str) -> dict[str, Any]:
    """The changes table of `wikitext` (which may be cut): {"rows": [{"date", "added", "removed", "reason"}] (every
    well-formed row, in the table's order: newest first), "reach" (the oldest date of the UNBROKEN run of well-formed
    rows from the top: what the read can vouch for), "closed" (the table's last line was read), "malformed"}.
    ValueError when there is no such table. A row is read only when the line that ends it was read (a cut can leave
    the last one half-written); the date and the two ticker columns are what a row must have."""
    found = _changes_table(wikitext)
    if found is None:
        raise ValueError("the article holds no changes table")
    body, closed = found
    parts = re.split(r"(?m)^\|-[^\n]*\n?", body)
    blocks = parts[1:] if closed else parts[1:-1]
    rows: list[dict[str, Any]] = []
    carry: dict[int, tuple[int, str]] = {}
    malformed = 0
    reach: dt.date | None = None
    broken = False
    for block in blocks:
        cells: list[tuple[str, int, int]] = []
        header = False
        for line in block.split("\n"):
            if line.startswith("|+"):
                continue
            if line.startswith("!"):
                header = True
            elif line.startswith("|"):
                cells.extend(_cell(piece) for piece in _depth_split(line[1:], "||"))
            elif cells and line.strip():
                content, rowspan, colspan = cells[-1]
                cells[-1] = (content + "\n" + line, rowspan, colspan)
        if header or not cells:
            continue
        columns: list[str] = []
        queue = list(cells)
        while queue or (len(columns) in carry):
            at = len(columns)
            if at in carry:
                left, value = carry[at]
                columns.append(value)
                if left > 1:
                    carry[at] = (left - 1, value)
                else:
                    del carry[at]
                continue
            content, rowspan, colspan = queue.pop(0)
            for _ in range(colspan):
                if rowspan > 1:
                    carry[len(columns)] = (rowspan - 1, content)
                columns.append(content)
        columns += [""] * (6 - len(columns))
        day = _wiki_date(_plain(columns[0]))
        added, removed = (_ticker(_plain(columns[k]).strip("| ")) for k in (1, 3))
        good = (day is not None and (added or removed) and all(not t or TICKER.match(t) for t in (added, removed)))
        if not good:
            malformed += 1
            broken = True
            continue
        rows.append({"date": day, "added": added or None, "removed": removed or None, "reason": _plain(columns[5])})
        if not broken:
            reach = day if reach is None else min(reach, day)
    return {"rows": rows, "reach": reach, "closed": closed, "malformed": malformed}


def _changes_section(gateway: Any, page: str) -> int | None:
    """The index of the article's section that holds the changes table by its heading, or None (the lead then)."""
    try:
        data = json.loads(web(gateway, _wiki_url(page, sections=True)))
        listed = data["parse"]["sections"]
    except (ValueError, KeyError, TypeError):
        return None
    for row in listed if isinstance(listed, list) else ():
        if isinstance(row, Mapping) and re.search(r"\bchanges\b", html.unescape(str(row.get("line") or "")), re.I):
            try:
                return int(row.get("index"))
            except (TypeError, ValueError):
                return None
    return None


def wiki_changes(gateway: Any) -> dict[str, Any]:
    """{rows [{date, added, removed, reason}], reach (the oldest date the unbroken run of complete rows reaches),
    complete (the whole table was read), revid, page, malformed}: the complete rows of the changes table (read with
    `allow_truncated`). ValueError when no article of `WIKI_PAGES` gives a changes table."""
    last = "no article was read"
    for page in WIKI_PAGES:
        section = _changes_section(gateway, page)
        for where in ([section] if section is not None else []) + [0, None]:
            try:
                answer, cut = _read(gateway, _wiki_url(page, section=where), allow_truncated=True)
                wikitext, whole, revid = _wikitext(answer)
                table = parse_changes(wikitext)
            except ValueError as exc:
                last = str(exc)
                continue
            return {"rows": table["rows"], "reach": table["reach"], "revid": revid, "page": page,
                    "complete": bool(table["closed"] and whole and not cut), "malformed": table["malformed"]}
    raise ValueError(f"no changes table could be read: {last}")


def row_key(row: Mapping[str, Any]) -> str:
    """One change row's name in `seen` and in the applied list."""
    return f"{_iso(_day(row.get('date')))}|{row.get('added') or ''}|{row.get('removed') or ''}"


def confirmed(row: Mapping[str, Any], seen: Mapping[str, Any]) -> bool:
    """Whether two runs at least `CONFIRM_HOURS` apart have both read the row (`seen`: {row key: {"first", "last"}},
    epoch seconds)."""
    mark = seen.get(row_key(row))
    if not isinstance(mark, Mapping):
        return False
    try:
        return float(mark["last"]) - float(mark["first"]) >= CONFIRM_HOURS * 3600
    except (KeyError, TypeError, ValueError):
        return False


def apply_changes(spells: Sequence[tuple], rows: Sequence[Mapping[str, Any]], seen: Mapping[str, Any] | None = None,
                  *, after: dt.date | None = None) -> tuple[list[tuple], list[str], dict[str, int]]:
    """(the spells with each applicable row applied, the keys applied in date order, {"pending", "already",
    "conflict"}). A row dated after `after` (None: the spells' own last date) applies when it is confirmed (`seen`
    None: every row is) and its removed ticker is a member and its added one is not: the removed ticker's open spell
    ends on the row's date and the added one starts on it (the file's own convention). A row both of whose halves
    the spells already show is "already"; one half only, a "conflict", and nothing of it is applied."""
    after = known_through(spells) if after is None else after
    state = [list(_spell(s)) for s in spells]
    open_at: dict[str, list] = {s[0]: s for s in state if s[2] is None}
    applied: list[str] = []
    counts = {"pending": 0, "already": 0, "conflict": 0}
    for row in sorted(rows, key=lambda r: (_day(r.get("date")), row_key(r))):
        day = _day(row.get("date"))
        if day is None or day <= after:
            continue
        if seen is not None and not confirmed(row, seen):
            counts["pending"] += 1
            continue
        added, removed = row.get("added"), row.get("removed")
        can_remove = removed is None or (removed in open_at and open_at[removed][1] < day)
        can_add = added is None or added not in open_at
        if can_remove and can_add:
            if removed is not None:
                open_at.pop(removed)[2] = day
            if added is not None:
                spell = [added, day, None]
                state.append(spell)
                open_at[added] = spell
            applied.append(row_key(row))
        elif (removed is None or removed not in open_at) and (added is None or added in open_at):
            counts["already"] += 1
        else:
            counts["conflict"] += 1
    return sorted((tuple(s) for s in state), key=lambda s: (s[0], s[1])), applied, counts


def extend(spells: Sequence[tuple], rows: Sequence[Mapping[str, Any]], seen: Mapping[str, Any]) -> list[tuple]:
    """The spells with every confirmed change row after `known_through` applied (`seen`: when each row was first and
    last read: {row key: {"first", "last"}})."""
    return apply_changes(spells, rows, seen)[0]


def exits(spells: Sequence[tuple], rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, dt.date], str]:
    """{(ticker, end): "deal" | "other" | "unknown"} for every ended spell (the change row within 5 calendar days of
    its end whose removed ticker is the spell's; the nearest when several)."""
    from ..xs import config as xs_config

    by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if row.get("removed") and _day(row.get("date")) is not None:
            by_ticker.setdefault(str(row["removed"]), []).append(row)
    out: dict[tuple[str, dt.date], str] = {}
    for spell in spells:
        ticker, _, end = _spell(spell)
        if end is None:
            continue
        near = [(abs((_day(r["date"]) - end).days), i, r) for i, r in enumerate(by_ticker.get(ticker, ()))
                if abs((_day(r["date"]) - end).days) <= RENAME_DAYS]
        if not near:
            out[(ticker, end)] = "unknown"
            continue
        reason = str(min(near, key=lambda x: (x[0], x[1]))[2].get("reason") or "")
        out[(ticker, end)] = "deal" if xs_config.VANISH_DEAL.search(reason) else "other"
    return out


# ------------------------------------------------------------------------------------------------- the venue
def _asset_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, Mapping) or not row.get("symbol"):
        return None
    return {"id": str(row.get("id") or ""), "status": str(row.get("status") or ""),
            "tradable": row.get("tradable") is True, "fractionable": row.get("fractionable") is True,
            "exchange": str(row.get("exchange") or "")}


def assets(gateway: Any, tickers: Sequence[str], *, tries: int = TRIES,
           sleep: Callable[[float], None] = time.sleep) -> dict[str, dict[str, Any] | None]:
    """{ticker: the venue's asset row {id, status, tradable, fractionable, exchange} | None (it knows no such
    symbol)}. Each call is tried up to `tries` times; one that still fails raises (never read as "no asset")."""
    out: dict[str, dict[str, Any] | None] = {}
    for ticker in tickers:
        symbol = _ticker(ticker)
        if not TICKER.match(symbol):
            raise ValueError("a ticker the venue's path cannot name")
        for attempt in range(max(1, int(tries))):
            try:
                out[symbol] = _asset_row(gateway.get(ASSETS + urllib.parse.quote(symbol, safe=".")))
                break
            except Exception as exc:  # noqa: BLE001 - 404 is the venue's answer; anything else is tried again
                if getattr(exc, "status", None) == 404:
                    out[symbol] = None
                    break
                if attempt + 1 >= max(1, int(tries)):
                    raise
                sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
    return out


def usable(row: Any) -> bool:
    """Whether a venue row is an active, tradable asset."""
    return isinstance(row, Mapping) and row.get("status") == "active" and row.get("tradable") is True


# ------------------------------------------------------------------------------------------------- assets (D2)
def _spells_of(row: Mapping[str, Any]) -> list[tuple[str, dt.date, dt.date | None, str | None]]:
    out = []
    for item in row.get("spells") or ():
        out.append((str(item[0]), _day(item[1]), _day(item[2]), item[3] if len(item) > 3 else None))
    return out


def columns(assets: Mapping[str, Any]) -> list[int]:  # noqa: A002 - the spec's name for assets.json's object
    """The panel's columns as aids: the REF aids first, then every asset that has a spell, ascending."""
    ref = sorted(int(a) for a, row in assets.items() if row.get("ref"))
    members = sorted(int(a) for a, row in assets.items() if not row.get("ref") and row.get("spells"))
    return ref + members


def rename_candidates(spells: Sequence[tuple]) -> list[tuple[tuple, tuple]]:
    """D2r's candidates: (spell a, spell b) with different tickers, a ended, b starting within `RENAME_DAYS` calendar
    days of a's end, both with a day the store can hold, in (a's end, tickers) order."""
    kept = [s for s in (_spell(x) for x in spells) if in_store(s[1], s[2])]
    out = []
    for a in kept:
        if a[2] is None:
            continue
        for b in kept:
            if b[0] != a[0] and abs((b[1] - a[2]).days) <= RENAME_DAYS:
                out.append((a, b))
    return sorted(out, key=lambda pair: (pair[0][2], pair[0][0], pair[1][0]))


def pair_key(a: Sequence[Any], b: Sequence[Any]) -> str:
    """One candidate pair's name in joins.json."""
    return f"{a[0]}|{_iso(_day(a[2]))}|{b[0]}|{_iso(_day(b[1]))}"


def rename_test(gateway: Any, a: Sequence[Any], b: Sequence[Any], *, last: dt.date,
                fetch: Callable[..., Mapping[str, Any]] | None = None,
                sleep: Callable[[float], None] = time.sleep) -> bool | None:
    """D2r for one pair: True when spell a's ticker read `asof` inside a and spell b's read `asof` inside b give the
    same raw daily closes on at least `RENAME_SESSIONS` common sessions around the join and differ on none; False
    when they do not; None when the pair cannot be tested (the join falls in 2020, which is never fetched, or after
    the last closed session). Raises what the bars call raises after its tries. `fetch`: `equity_panel.fetch_asof`."""
    if fetch is None:
        from .equity_panel import fetch_asof as fetch

    a, b = _spell(a), _spell(b)
    sessions = [d for d, _ in store_sessions(last)]
    inside_a = [d for d in sessions if a[1] <= d < a[2]]
    inside_b = [d for d in sessions if b[1] <= d and (b[2] is None or d < b[2])]
    if not inside_a or not inside_b or (a[2] - inside_a[-1]).days > 2 * RENAME_DAYS \
            or (inside_b[0] - b[1]).days > 2 * RENAME_DAYS:
        return None  # one side of the join has no session of the store next to it: the 2020 gap, or not yet traded
    low = min(a[2], b[1]) - dt.timedelta(days=RENAME_WINDOW_DAYS)
    high = max(a[2], b[1]) + dt.timedelta(days=RENAME_WINDOW_DAYS)
    span = next(((first, end) for first, end in spans()
                 if first <= inside_a[-1] and (end is None or inside_a[-1] <= end)), None)
    if span is None or not (span[0] <= inside_b[0] and (span[1] is None or inside_b[0] <= span[1])):
        return None
    window = [d for d in sessions if max(low, span[0]) <= d <= (high if span[1] is None else min(high, span[1]))]
    if len(window) < RENAME_SESSIONS:
        return None
    later = [d for d in inside_b if d >= b[1] + dt.timedelta(days=30)]
    asof_b = later[0] if later else (inside_b[-1] if b[2] is not None else None)
    start, end = window[0].isoformat(), window[-1].isoformat()
    left = fetch(gateway, [a[0]], start, end, adjustment="raw", asof=inside_a[-1].isoformat(), sleep=sleep)
    right = fetch(gateway, [b[0]], start, end, adjustment="raw", asof=_iso(asof_b), sleep=sleep)
    closes = []
    for rows in (left.get(a[0]) or (), right.get(b[0]) or ()):
        closes.append({str(r.get("t"))[:10]: r.get("c") for r in rows
                       if isinstance(r.get("c"), (int, float)) and not isinstance(r.get("c"), bool) and r["c"] > 0})
    common = sorted(set(closes[0]) & set(closes[1]))
    if len(common) < RENAME_SESSIONS:
        return False
    return all(abs(closes[0][d] - closes[1][d]) <= RENAME_TOLERANCE * max(closes[0][d], closes[1][d]) for d in common)


def assign(spells: Sequence[tuple], previous: Mapping[str, Any] | None,
           joins: Sequence[tuple[str, str]], *, exits: Mapping[tuple[str, dt.date], str] | None = None,  # noqa: A002
           venue: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """assets.json's object (D2): REF aids 1..12 in `league.xs.config.REF` order; a member asset is one or more spells
    joined by D2r (`joins`: (ticker X, ticker Y) pairs that passed `rename_test`; the same ticker out and back in
    within `RENAME_DAYS` is joined untested); aids from `FIRST_AID` up by (first spell start, ticker) at the first
    build, NEVER reused and never renumbered (`previous`: the last file; a spell it has keeps its aid, whatever
    `joins` says now, and a new asset takes the next aid above them all). A previous asset the spells no longer
    show keeps its aid with no spell (it is a member nowhere). `exits`: how each ended spell ended; `venue`:
    {ticker: the venue's asset row | None} (a ticker it lacks keeps the previous file's row)."""
    from ..xs import config as xs_config

    exits, venue, previous = dict(exits or {}), dict(venue or {}), dict(previous or {})
    kept = sorted({s for s in (_spell(x) for x in spells) if in_store(s[1], s[2])}, key=lambda s: (s[1], s[0]))
    old_rows = {int(aid): row for aid, row in previous.items() if not row.get("ref")}
    old_exact = {(t, s): aid for aid, row in old_rows.items() for t, s, _, _ in _spells_of(row)}

    def old_aid(spell: tuple) -> int | None:
        ticker, start, end = spell
        if (ticker, start) in old_exact:
            return old_exact[(ticker, start)]
        for aid, row in sorted(old_rows.items()):  # the same ticker over overlapping days: a date upstream corrected
            for t, s, e, _ in _spells_of(row):
                if t == ticker and (e is None or start < e) and (end is None or s < end):
                    return aid
        return None

    wanted = {(str(x).strip().upper(), str(y).strip().upper()) for x, y in joins}
    before: dict[tuple, tuple] = {}
    taken: set[tuple] = set()
    for b in kept:
        best = None
        for a in kept:
            if a is b or a[2] is None or a in taken or abs((b[1] - a[2]).days) > RENAME_DAYS:
                continue
            if a[1] < b[1] and (a[0] == b[0] or (a[0], b[0]) in wanted):
                gap = (abs((b[1] - a[2]).days), a[0] != b[0], a[0])
                best = (gap, a) if best is None or gap < best[0] else best
        if best is not None:
            before[b] = best[1]
            taken.add(best[1])
    aid_of: dict[tuple, int | None] = {}
    head_of: dict[tuple, tuple] = {}
    for spell in kept:
        aid = old_aid(spell)
        prior = before.get(spell)
        if aid is None and prior is not None:
            aid, head_of[spell] = aid_of[prior], head_of[prior]
        else:
            head_of[spell] = spell
        aid_of[spell] = aid
    fresh = sorted({head_of[s] for s in kept if aid_of[s] is None}, key=lambda s: (s[1], s[0]))
    top = max([FIRST_AID - 1, *old_rows])
    new_aid = {head: top + 1 + k for k, head in enumerate(fresh)}
    groups: dict[int, list[tuple]] = {}
    for spell in kept:
        aid = aid_of[spell] if aid_of[spell] is not None else new_aid[head_of[spell]]
        groups.setdefault(int(aid), []).append(spell)

    out: dict[str, Any] = {}
    for k, symbol in enumerate(xs_config.REF, start=1):
        was = previous.get(str(k)) or {}
        out[str(k)] = {"spells": [], "symbol": symbol, "alpaca": venue.get(symbol, was.get("alpaca")), "ref": True,
                       "renames": [], "masked": None}
    for aid in sorted(set(groups) | set(old_rows)):
        mine = sorted(groups.get(aid, ()), key=lambda s: s[1])
        was = old_rows.get(aid) or {}
        symbol = mine[-1][0] if mine else str(was.get("symbol") or "")
        renames = [[x[0], y[0], y[1].isoformat()] for x, y in zip(mine, mine[1:]) if x[0] != y[0]]
        out[str(aid)] = {
            # a spell another one continues (a rename) did not leave the index: "other", and never counted as an exit
            "spells": [[t, s.isoformat(), _iso(e),
                        None if e is None else ("other" if k + 1 < len(mine) else exits.get((t, e), "unknown"))]
                       for k, (t, s, e) in enumerate(mine)],
            "symbol": symbol,
            "alpaca": venue[symbol] if symbol in venue else (
                was.get("alpaca") if was.get("symbol") == symbol else None),
            "ref": False, "renames": renames, "masked": was.get("masked") if was.get("masked") in BAR_MASKS else None}
    for row in out.values():
        if not row["ref"] and row["spells"] and row["spells"][-1][2] is None and usable(row["alpaca"]) \
                and row["alpaca"].get("fractionable") is not True:
            row["masked"] = VENUE_MASK  # the venue's own: a current member that cannot be bought in dollars
    return out


def membership(assets: Mapping[str, Any], days: Sequence[dt.date]) -> Any:  # noqa: A002
    """D3: bool (len(days), n_assets), the columns in `columns(assets)` order: some spell of the asset has start <= d
    and (end is null or d < end). A REF column is all False."""
    import numpy as np

    ordinals = np.array([d.toordinal() for d in days], dtype=np.int64)
    order = columns(assets)
    out = np.zeros((len(days), len(order)), dtype=bool)
    for k, aid in enumerate(order):
        for _, start, end, _ in _spells_of(assets[str(aid)]):
            inside = ordinals >= start.toordinal()
            if end is not None:
                inside &= ordinals < end.toordinal()
            out[:, k] |= inside
    return out


def _months_before(day: dt.date, months: int) -> dt.date:
    index = day.year * 12 + (day.month - 1) - int(months)
    year, month = divmod(index, 12)
    for last in (day.day, 30, 29, 28):
        try:
            return dt.date(year, month + 1, last)
        except ValueError:
            continue
    raise ValueError("no such day")


def tradable(assets: Mapping[str, Any], day: dt.date) -> list[str]:  # noqa: A002
    """Section 11's list, sorted: every symbol that was a member on ANY session of the `UNION_MONTHS` months through
    `day` and is tradable, fractionable and unmasked today. No date is beside any of them."""
    since = _months_before(day, UNION_MONTHS)
    out: set[str] = set()
    for row in assets.values():
        if row.get("ref") or row.get("masked") is not None:
            continue
        venue = row.get("alpaca")
        if not (usable(venue) and venue.get("fractionable") is True):
            continue
        if any(start <= day and (end is None or end > since) for _, start, end, _ in _spells_of(row)):
            out.add(str(row["symbol"]))
    return sorted(out)


# ------------------------------------------------------------------------------------------------- the audit
class _Check:
    """One named check: its problems (the first 20) and their count."""

    LISTED = 20

    def __init__(self) -> None:
        self.problems: list[str] = []
        self.count = 0
        self.extra: dict[str, Any] = {}

    def add(self, text: str) -> None:
        self.count += 1
        if len(self.problems) < self.LISTED:
            self.problems.append(text)

    def out(self, passed: bool | None = None) -> dict[str, Any]:
        return {"passed": self.count == 0 if passed is None else passed, "problems": list(self.problems),
                "count": self.count, **self.extra}


def audit(spells: Sequence[tuple], *, previous: Sequence[tuple] | None, source: Mapping[str, Any],
          venue: Mapping[str, Any], days: Sequence[dt.date], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """{passed, checks: {name of `CHECKS`: {passed, problems, count}}} (the module docstring). `spells`: the
    membership as it would be written (the file's, extended). `previous`: the OLD pin's file spells when the pin is
    advancing (None: it is not; `append_only` then has nothing to hold). `source`: {"sha256": this fetch's,
    "recorded": the sha256 recorded at the pin's first fetch | None, "spells": the pinned file's own spells,
    "known_through": the old pin's last date (with `previous`)}. `venue`: {ticker: asset row | None} for the current
    members. `days`: the store's sessions. `rows`: the changes table's rows (`wiki_agreement`). Pure."""
    checks = {name: _Check() for name in CHECKS}
    mine = [_spell(s) for s in spells]
    filed = [_spell(s) for s in source.get("spells") or mine]
    if source.get("recorded") and source.get("sha256") != source.get("recorded"):
        checks["source"].add("the pinned file's sha256 is not the one recorded at its first fetch")
    if previous is not None:
        through = _day(source.get("known_through")) or known_through(previous)
        for problem in append_only(previous, filed, through):
            checks["append_only"].add(problem)
    # count: the members on every store session, by sweeping the spells' starts and ends once
    deltas: dict[dt.date, int] = {}
    for _, start, end in mine:
        deltas[start] = deltas.get(start, 0) + 1
        if end is not None:
            deltas[end] = deltas.get(end, 0) - 1
    marks = sorted(deltas)
    running, at = 0, 0
    low = high = None
    for day in sorted(days):
        while at < len(marks) and marks[at] <= day:
            running += deltas[marks[at]]
            at += 1
        low, high = (running if low is None else min(low, running)), (running if high is None else max(high, running))
        if not MEMBERS_MIN <= running <= MEMBERS_MAX:
            checks["count"].add(f"{day}: {running} members")
    if not days:
        checks["count"].add("no store session to count on")
    checks["count"].extra.update(min=low, max=high, sessions=len(days))
    by_ticker: dict[str, list[tuple]] = {}
    for spell in mine:
        by_ticker.setdefault(spell[0], []).append(spell)
    for ticker, rows_of in sorted(by_ticker.items()):
        rows_of.sort(key=lambda s: s[1])
        for a, b in zip(rows_of, rows_of[1:]):
            if a[2] is None or b[1] < a[2]:
                checks["overlap"].add(f"{ticker}: two spells overlap")
    current = sorted({t for t, _, end in mine if end is None})
    for ticker in current:
        if not usable(venue.get(ticker)):
            checks["assets"].add(ticker)
    checks["assets"].extra.update(current=len(current))
    # wiki_agreement: reported, never failing
    through = known_through(filed)
    starts = {}
    ends = {}
    for ticker, start, end in filed:
        starts.setdefault(ticker, []).append(start)
        if end is not None:
            ends.setdefault(ticker, []).append(end)
    read = agreed = 0
    for row in rows:
        day = _day(row.get("date"))
        if day is None or not through - dt.timedelta(days=365) < day <= through:
            continue
        read += 1
        ok_out = row.get("removed") is None or any(abs((e - day).days) <= RENAME_DAYS
                                                   for e in ends.get(row["removed"], ()))
        ok_in = row.get("added") is None or any(abs((s - day).days) <= RENAME_DAYS
                                                for s in starts.get(row["added"], ()))
        if ok_out and ok_in:
            agreed += 1
        else:
            checks["wiki_agreement"].add(f"{day}: the file does not show this change")
    checks["wiki_agreement"].extra.update(rows=read, agreed=agreed, share=round(agreed / read, 4) if read else None)
    out = {name: check.out() for name, check in checks.items()}
    out["assets"]["passed"] = checks["assets"].count <= ASSETS_MISSING_MAX
    out["wiki_agreement"]["passed"] = True
    return {"passed": all(c["passed"] for c in out.values()), "checks": out}


# ------------------------------------------------------------------------------------------------- the files
def folder(root: str | Path) -> Path:
    """`<root>/universe` (`root`: `<state>/equity-daily`)."""
    from ..xs import store as xs_store

    return Path(root) / xs_store.UNIVERSE_DIR


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ensure_salt(root: str | Path) -> str:
    """The House salt, written ONCE (32 bytes of `os.urandom`, owner-only, exclusive create: it is never rewritten):
    the first 8 hex of its sha256, the only thing of it that is ever written anywhere else. ValueError when the file
    is there and is not `SALT_BYTES` long (it is never repaired: every id of every run hangs on it)."""
    from ..xs import store as xs_store

    path = folder(root) / xs_store.SALT_FILE
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        salt = path.read_bytes()
    else:
        salt = os.urandom(xs_store.SALT_BYTES)
        with os.fdopen(fd, "wb") as handle:
            handle.write(salt)
            handle.flush()
            os.fsync(handle.fileno())
    if len(salt) != xs_store.SALT_BYTES:
        raise ValueError("the House salt is not the length it was written with: nothing is written over it")
    return _sha(salt)[:8]


def read_universe(root: str | Path) -> dict[str, Any] | None:
    """The universe as written: {"assets", "manifest", "source"}, each file checked against the manifest's sha256.
    None when there is none yet; ValueError when a file does not match (a universe being rewritten under a
    reader, or damaged: nothing is read from it)."""
    base = folder(root)
    manifest = _load(base / MANIFEST_FILE)
    if not isinstance(manifest, Mapping):
        return None
    out: dict[str, Any] = {"manifest": dict(manifest)}
    for name, key in ((ASSETS_FILE, "assets"), (SOURCE_FILE, "source")):
        try:
            data = (base / name).read_bytes()
        except OSError:
            raise ValueError(f"the universe lacks {name}") from None
        if _sha(data) != (manifest.get("sha256") or {}).get(name):
            raise ValueError(f"the universe's {name} is not the file its manifest names")
        out[key] = json.loads(data.decode("utf-8"))
    return out


def _spells_csv(spells: Sequence[tuple], filed: set[tuple]) -> bytes:
    lines = ["ticker,start,end,source"]
    for ticker, start, end in sorted((_spell(s) for s in spells), key=lambda s: (s[0], s[1])):
        source = "fja" if (ticker, start, end) in filed else "wiki"
        lines.append(f"{ticker},{start.isoformat()},{_iso(end) or ''},{source}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _exit_counts(assets: Mapping[str, Any]) -> dict[str, int]:  # noqa: A002
    from ..xs import store as xs_store

    counts = {name: 0 for name in xs_store.EXITS}
    for row in assets.values():
        for _, _, end, kind in _spells_of(row)[-1:]:  # how the ASSET left: its last spell's end
            if end is not None and kind in counts:
                counts[kind] += 1
    return counts


def _train_unknown(assets: Mapping[str, Any]) -> tuple[int, int]:  # noqa: A002
    """(Train-era exits "unknown", Train-era exits): spells that ended inside a Train segment."""
    from ..xs import config as xs_config

    unknown = total = 0
    for row in assets.values():
        for _, _, end, kind in _spells_of(row)[-1:]:
            if end is not None and any(first <= end <= last for first, last in xs_config.TRAIN_SEGMENTS):
                total += 1
                unknown += 1 if kind == "unknown" else 0
    return unknown, total


def _publish(root: str | Path, *, files: Mapping[str, bytes], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Write `files` then the manifest, LAST, with every hashed file's sha256 (a file not rewritten keeps its own)."""
    base = folder(root)
    for name, data in files.items():
        _write(base / name, data)
    shas = {}
    for name in HASHED:
        shas[name] = _sha(files[name]) if name in files else _sha((base / name).read_bytes())
    out = {**manifest, "sha256": shas}
    _write(base / MANIFEST_FILE, _json_bytes(out))
    return out


def remask(root: str | Path, masks: Mapping[int, str | None], *, day: dt.date) -> dict[str, int]:
    """THE PANEL JOB'S ONE WRITE HERE: set each asset's bar mask (`BAR_MASKS`, or None: its series is accepted) from
    D19's acceptance, then rewrite tradable.json for `day` and the manifest (last). The venue's own mask
    ("not_fractionable") is never overwritten, and an aid the universe does not have is ignored. Returns the count of
    assets by mask. ValueError when there is no universe to mark or a mask is not one of `BAR_MASKS`."""
    universe = read_universe(root)
    if universe is None:
        raise ValueError("there is no universe to mark")
    table = universe["assets"]
    changed = False
    for aid, mask in masks.items():
        if mask is not None and mask not in BAR_MASKS:
            raise ValueError(f"{mask!r} is not a mask the bars give")
        row = table.get(str(int(aid)))
        if row is None or row.get("ref") or row.get("masked") == VENUE_MASK or row.get("masked") == mask:
            continue
        row["masked"] = mask
        changed = True
    counts: dict[str, int] = {}
    for row in table.values():
        if row.get("masked") is not None:
            counts[row["masked"]] = counts.get(row["masked"], 0) + 1
    listed = {"as_of": day.isoformat(), "stock": tradable(table, day)}
    before = _load(folder(root) / TRADABLE_FILE)
    if changed or before != listed:
        manifest = dict(universe["manifest"])
        manifest["masked"] = dict(sorted(counts.items()))
        _publish(root, files={ASSETS_FILE: _json_bytes(table), TRADABLE_FILE: _json_bytes(listed)}, manifest=manifest)
    return counts


# ------------------------------------------------------------------------------------------------- the job
def _due(stamp: Any, now: float, days: float = REFRESH_DAYS) -> bool:
    at = _epoch(stamp)
    return at is None or now - at >= days * 86400


def _read_wiki(gateway: Any, through: dt.date, before: Mapping[str, Any], now: float) -> dict[str, Any]:
    """Tonight's reading of the changes table against the file's `through`: {"rows" (every complete row; [] when
    nothing was read), "block" (SOURCE.json's `wiki`), "applied" (the rows in force after `through`)}. A verified
    read re-derives the rows in force (confirmed, in tonight's table); an unverified one keeps the earlier ones."""
    block = {"page": before.get("page"), "revid": before.get("revid"), "verdict": "unverified",
             "known_through": before.get("known_through") or through.isoformat(),
             "seen": dict(before.get("seen") or {}),
             "applied": list(before.get("applied") or []), "rows": 0, "malformed": 0, "complete": False,
             "reach": before.get("reach"), "reach_ok": False, "why": None, "read_at": before.get("read_at"),
             "changes_applied": 0}
    try:
        read = wiki_changes(gateway)
    except ValueError as exc:
        block["why"] = str(exc)[:200]
        return {"rows": [], "block": block}
    rows = read["rows"]
    block.update(page=read["page"], revid=read["revid"], rows=len(rows), malformed=read["malformed"],
                 complete=read["complete"], read_at=_stamp(now), reach=_iso(read["reach"]))
    after = [r for r in rows if r["date"] > through]
    verified = read["reach"] is not None and read["reach"] <= through
    block["reach_ok"] = verified
    if not verified:
        block["why"] = "the complete rows do not reach back to the file's last date"
        return {"rows": rows, "block": block}
    seen = {}
    for row in after:
        key = row_key(row)
        first = (block["seen"].get(key) or {}).get("first") if isinstance(block["seen"].get(key), Mapping) else None
        seen[key] = {"first": float(first) if isinstance(first, (int, float)) else float(now), "last": float(now)}
    block.update(verdict="ok", seen=seen, known_through=max(through, _day(_stamp(now))).isoformat(),
                 applied=[{"date": r["date"].isoformat(), "added": r["added"], "removed": r["removed"]}
                          for r in sorted(after, key=lambda r: (r["date"], row_key(r))) if confirmed(r, seen)])
    return {"rows": rows, "block": block}


class OutOfWall(RuntimeError):
    """The run has used its share of the job's wall: it stops, and what it kept stays for the next one."""


def _venue_rows(gateway: Any, root: Path, tickers: Sequence[str], *, now: float, sleep: Callable[[float], None],
                check: Callable[[], None] = lambda: None) -> tuple[dict[str, Any], int, int]:
    """({ticker: the venue's asset row | None}, calls made, calls that failed), through venue.json: {"started_at",
    "done": [tickers read in this sweep], "rows": {ticker: row | None}}. A sweep reads every ticker once; a new one
    starts when the last began `REFRESH_DAYS` ago. A ticker whose call still fails keeps its earlier row and is asked
    again the next run. The file is kept as the sweep goes, so a run cut short resumes (`check` raises when the
    run is out of its wall)."""
    path = folder(root) / VENUE_FILE
    cache = _load(path)
    cache = dict(cache) if isinstance(cache, Mapping) else {}
    rows = dict(cache.get("rows") or {})
    done = set(cache.get("done") or ())
    started = cache.get("started_at")
    if _due(started, now):
        started, done = _stamp(now), set()
    asked = failed = 0

    def keep() -> None:
        _write(path, _json_bytes({"started_at": started, "done": sorted(done), "rows": rows}))

    try:
        for ticker in tickers:
            if ticker in done:
                continue
            check()
            asked += 1
            try:
                rows[ticker] = assets(gateway, [ticker], sleep=sleep)[ticker]
                done.add(ticker)
            except Exception:  # noqa: BLE001 - this ticker's row stays what it was; asked again the next run
                failed += 1
            if asked % VENUE_KEEP_EVERY == 0:
                keep()
    finally:
        if asked:
            keep()
    return {t: rows.get(t) for t in tickers}, asked, failed


def _joins(gateway: Any, root: Path, spells: Sequence[tuple], previous: Mapping[str, Any] | None,
           rows: Sequence[Mapping[str, Any]], *, last: dt.date, sleep: Callable[[float], None],
           check: Callable[[], None] = lambda: None) -> dict[str, Any]:
    """D2r over the candidates this run must decide: {"joins": [(X, Y)], "tested", "joined", "untestable", "listed"
    (pairs the changes table itself shows as an index change)}. A pair both of whose spells already have an aid is
    decided for good and is not read again; every answer is kept in joins.json as it comes."""
    known = {(t, s) for row in (previous or {}).values() for t, s, _, _ in _spells_of(row)}
    path = folder(root) / JOINS_FILE
    cache = _load(path)
    cache = dict(cache) if isinstance(cache, Mapping) else {}
    left: dict[str, list[dt.date]] = {}
    came: dict[str, list[dt.date]] = {}
    for row in rows:
        day = _day(row.get("date"))
        if day is not None and row.get("removed"):
            left.setdefault(str(row["removed"]), []).append(day)
        if day is not None and row.get("added"):
            came.setdefault(str(row["added"]), []).append(day)
    out = {"joins": [], "tested": 0, "joined": 0, "untestable": 0, "listed": 0}
    for a, b in rename_candidates(spells):
        if (a[0], a[1]) in known and (b[0], b[1]) in known:
            continue
        key = pair_key(a, b)
        if key not in cache:
            # The table lists index changes only, never a ticker change: a spell whose end it shows as a removal, or
            # whose start it shows as an addition, was an index change, and no bar need say so.
            if any(abs((day - a[2]).days) <= RENAME_DAYS for day in left.get(a[0], ())) \
                    or any(abs((day - b[1]).days) <= RENAME_DAYS for day in came.get(b[0], ())):
                out["listed"] += 1
                continue
            check()
            answer = rename_test(gateway, a, b, last=last, sleep=sleep)
            out["tested"] += 1
            cache[key] = answer
            _write(path, _json_bytes(cache))
        if cache[key] is True:
            out["joins"].append((a[0], b[0]))
            out["joined"] += 1
        elif cache[key] is None:
            out["untestable"] += 1
    return out


def run(ctx: Any, *, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """The job (league/ops/context.py is the `ctx`). Its first statement is `league.xs.config.quiet(ctx.now(),
    WALL_S)`: a start that could still be working at a wall answers {"status": "skipped", "why"}. Else {"ok": True,
    counts and verdicts} with the universe written, or {"status": "failed", "error"} with nothing written and the
    last good universe in place. `sleep`: the tests'."""
    why = quiet_now(ctx.now(), WALL_S)
    if why is not None:
        return {"status": "skipped", "why": why}
    from .equity_data import last_closed

    now = ctx.now()
    root = Path(ctx.root) / STORE_DIR
    try:
        universe = read_universe(root)
    except ValueError as exc:
        return _failed(f"the universe on disk cannot be read ({exc}): nothing is written over it")
    before = dict((universe or {}).get("source") or {})
    previous = (universe or {}).get("assets")
    commit = str(before.get("commit") or PIN).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        return {"status": "skipped", "why": "the membership source has no pinned commit"}
    try:
        last = last_closed(now)
        text = web(ctx.gateway, RAW.format(commit=commit))
        filed = parse_spells(text)
    except Exception as exc:  # noqa: BLE001 - nothing read, nothing written: a failed receipt, retried in its grace
        return _failed(f"the pinned spell file could not be read: {type(exc).__name__}: {str(exc)[:200]}")
    days = [d for d, _ in store_sessions(last)]
    pin = dict(before.get("pin") or {})
    pin.setdefault("advanced_at", _stamp(now))
    candidate = None
    if _due(pin.get("checked_at"), now):
        pin.update(checked_at=_stamp(now), refused=None)
        newest = latest_commit(ctx.gateway)
        pin["read"] = newest is not None
        if newest is not None and newest != commit:
            try:
                new_text = web(ctx.gateway, RAW.format(commit=newest))
                candidate = (newest, new_text, parse_spells(new_text))
            except ValueError as exc:
                pin["refused"] = f"the newer file could not be read: {str(exc)[:120]}"
            if candidate is not None:
                grown = append_only(filed, candidate[2], known_through(filed))
                if grown:  # refused before anything is asked of the venue for it
                    candidate = None
                    pin["refused"] = f"the newer file is not the old one grown ({len(grown)} differences)"
            if pin.get("refused"):
                ctx.alert("warning", f"equity_universe: the source's newer commit is not adopted ({pin['refused']}); "
                                     "the old pin stays")
    venue_cache: dict[str, Any] = {}
    counts = {"venue_asked": 0, "venue_failed": 0}
    wiki_cache: dict[dt.date, dict[str, Any]] = {}

    def check() -> None:
        if ctx.now() - now > WALL_SHARE * WALL_S:
            raise OutOfWall(f"the run used {int(WALL_SHARE * 100)}% of its wall: what it read is kept, and the next "
                            "run goes on from there")

    def attempt(commit: str, text: str, filed: list[tuple], old_pin: list[tuple] | None) -> dict[str, Any]:
        """Everything that would be written under this pin, and its audit."""
        through = known_through(filed)
        if through not in wiki_cache:
            wiki_cache[through] = _read_wiki(ctx.gateway, through, before.get("wiki") or {}, now)
        wiki = wiki_cache[through]
        spells, applied, _ = apply_changes(filed, wiki["block"]["applied"], after=through)
        ended = exits(spells, wiki["rows"])
        for row in (previous or {}).values():  # a night the table was not read does not forget how a spell ended
            for ticker, _, end, kind in _spells_of(row)[-1:]:
                if end is not None and kind in ("deal", "other") and ended.get((ticker, end)) == "unknown":
                    ended[(ticker, end)] = kind
        horizon = _months_before(last, UNION_MONTHS + 1)
        tickers = sorted({t for t, s, e in spells if in_store(s, e) and (e is None or e > horizon)})
        ask = [t for t in tickers if t not in venue_cache]
        rows, asked, failed = _venue_rows(ctx.gateway, root, ask, now=now, sleep=sleep, check=check)
        venue_cache.update(rows)
        counts["venue_asked"] += asked
        counts["venue_failed"] += failed
        venue = {t: venue_cache[t] for t in tickers}
        joined = _joins(ctx.gateway, root, spells, previous, wiki["rows"], last=last, sleep=sleep, check=check)
        table = assign(spells, previous, joined["joins"], exits=ended, venue=venue)
        recorded = before.get("sha256") if before.get("commit") == commit else None
        result = audit(spells, previous=old_pin,
                       source={"sha256": _sha(text), "recorded": recorded, "spells": filed,
                               "known_through": None if old_pin is None else known_through(old_pin)},
                       venue=venue, days=days, rows=wiki["rows"])
        return {"commit": commit, "text": text, "filed": filed, "spells": spells, "applied": applied, "wiki": wiki,
                "assets": table, "audit": result, "joins": joined, "through": through}

    try:
        built = None
        if candidate is not None:
            trial = attempt(candidate[0], candidate[1], candidate[2], filed)
            if trial["audit"]["passed"]:
                built = trial
                pin.update(advanced_at=_stamp(now))
            else:
                failed_checks = [n for n, c in trial["audit"]["checks"].items() if not c["passed"]]
                pin["refused"] = f"the audit failed on the newer file ({', '.join(failed_checks)})"
                ctx.alert("warning", f"equity_universe: the source's newer commit is not adopted ({pin['refused']}); "
                                     "the old pin stays")
        if built is None:
            built = attempt(commit, text, filed, None)
    except Exception as exc:  # noqa: BLE001 - a gateway error mid-way writes nothing (joins.json keeps its answers)
        return _failed(f"the universe could not be assembled: {type(exc).__name__}: {str(exc)[:200]}")
    result = built["audit"]
    audit_counts = {name: {"passed": c["passed"], "count": c["count"]} for name, c in result["checks"].items()}
    if not result["passed"]:
        failed_checks = [n for n, c in result["checks"].items() if not c["passed"]]
        ctx.alert("warning", f"equity_universe: the audit failed ({', '.join(failed_checks)}): nothing written, the "
                             "last good universe stays")
        return _failed(f"the audit failed ({', '.join(failed_checks)}): nothing written, the last good universe stays",
                       audit=audit_counts)
    table, wiki = built["assets"], built["wiki"]["block"]
    wiki["changes_applied"] = len(built["applied"])
    source = {"repo": REPO, "commit": built["commit"], "path": FILE, "sha256": _sha(built["text"]),
              "rows": len(built["filed"]), "known_through": built["through"].isoformat(),
              "fetched_at": _stamp(now) if before.get("commit") != built["commit"] else before.get("fetched_at")
              or _stamp(now),
              "pin": pin, "wiki": wiki}
    effective = max(built["through"], _day(wiki["known_through"]) or built["through"])
    stale = max(0, (_day(_stamp(now)) - effective).days)
    exit_counts = _exit_counts(table)
    try:
        salt = ensure_salt(root)
        listed = {"as_of": last.isoformat(), "stock": tradable(table, last)}
        masked: dict[str, int] = {}
        for row in table.values():
            if row.get("masked") is not None:
                masked[row["masked"]] = masked.get(row["masked"], 0) + 1
        _publish(root, files={SOURCE_FILE: _json_bytes(source),
                              SPELLS_FILE: _spells_csv(built["spells"], set(built["filed"])),
                              ASSETS_FILE: _json_bytes(table), TRADABLE_FILE: _json_bytes(listed)},
                 manifest={"version": _version(), "audit": result, "exits": exit_counts, "salt": salt,
                           "wiki_reach": wiki["reach"],
                           "known_through": effective.isoformat(), "masked": dict(sorted(masked.items())),
                           "written_at": _stamp(now)})
    except Exception as exc:  # noqa: BLE001 - the manifest is last: a write cut short leaves the old one in force
        return _failed(f"the universe could not be written: {type(exc).__name__}: {str(exc)[:200]}",
                       audit=audit_counts)
    limit = ctx.job_settings().get("max_stale_days") if hasattr(ctx, "job_settings") else None
    limit = limit if isinstance(limit, (int, float)) and not isinstance(limit, bool) and limit > 0 else STALE_ALARM_DAYS
    if wiki["verdict"] != "ok":
        ctx.alert("warning", "equity_universe: the changes table was not read back to the spell file's last date "
                             f"({wiki.get('why') or 'unverified'}): no change after it is applied tonight")
    if stale > limit:
        ctx.alert("warning", f"equity_universe: the membership is {stale} days stale (limit {int(limit)}): no panel "
                             "look runs past it")
    advanced = _epoch(pin.get("advanced_at"))
    if advanced is not None and now - advanced > PIN_ALARM_DAYS * 86400:
        ctx.alert("warning", f"equity_universe: the source's pin has not advanced for {PIN_ALARM_DAYS} days")
    unknown, train_exits = _train_unknown(table)
    if train_exits and unknown / train_exits > UNKNOWN_EXITS_ALARM:
        ctx.alert("warning", f"equity_universe: {unknown} of {train_exits} Train-era exits are \"unknown\" (the "
                             "changes table names no row for them)")
    if counts["venue_failed"]:
        ctx.alert("warning", f"equity_universe: {counts['venue_failed']} venue asset rows could not be read again; "
                             "each keeps its earlier row")
    members = sum(1 for row in table.values() if row["spells"] and row["spells"][-1][2] is None)
    return {"ok": True, "commit": built["commit"][:12], "spells": len(built["spells"]),
            "assets": sum(1 for row in table.values() if not row["ref"]),
            "new_assets": sum(1 for aid in table if aid not in (previous or {})), "members": members,
            "sessions": len(days), "audit": audit_counts, "exits": exit_counts,
            "train_exits": {"unknown": unknown, "all": train_exits},
            "wiki": {"verdict": wiki["verdict"], "rows": wiki["rows"], "applied": wiki["changes_applied"],
                     "pending": len(wiki["seen"]) - len(wiki["applied"]), "complete": wiki["complete"],
                     "malformed": wiki["malformed"]},
            "joins": {k: built["joins"][k] for k in ("tested", "joined", "untestable", "listed")},
            "venue": dict(counts), "tradable": len(listed["stock"]), "masked": dict(sorted(masked.items())),
            "stale_days": stale, "pin": {"advanced": built["commit"] != commit, "refused": bool(pin.get("refused"))},
            "salt": salt}


def _version() -> str:
    from ..xs import store as xs_store

    return xs_store.UNIVERSE_VERSION


__all__ = ["PIN", "REPO", "FILE", "RAW", "ATOM", "WEB", "ASSETS", "AGENT", "WALL_S", "MEMBERS_MIN", "MEMBERS_MAX",
           "ASSETS_MISSING_MAX", "RENAME_DAYS", "RENAME_SESSIONS", "CONFIRM_HOURS", "UNION_MONTHS", "CHECKS", "web",
           "parse_spells", "append_only", "latest_commit", "wiki_changes", "extend", "exits", "assets", "assign",
           "membership", "tradable", "audit", "run", "COMMITS", "WIKI_API", "WIKI_PAGES", "RENAME_WINDOW_DAYS",
           "RENAME_TOLERANCE", "REFRESH_DAYS", "PIN_ALARM_DAYS", "STALE_ALARM_DAYS", "UNKNOWN_EXITS_ALARM",
           "FIRST_AID", "TICKER", "STORE_DIR", "SOURCE_FILE", "SPELLS_FILE", "ASSETS_FILE", "TRADABLE_FILE",
           "MANIFEST_FILE", "JOINS_FILE", "VENUE_FILE", "WALL_SHARE", "VENUE_KEEP_EVERY", "OutOfWall", "HASHED",
           "BAR_MASKS", "VENUE_MASK", "spans", "in_store", "store_sessions",
           "quiet_now", "known_through", "parse_changes", "row_key", "confirmed", "apply_changes", "usable",
           "columns", "rename_candidates", "pair_key", "rename_test", "folder", "ensure_salt", "read_universe",
           "remask"]
