"""Government releases and notices, the third group of the Kalshi-scale run's recorders (Sept 25, 2026,
workstream I2): the White House's presidential actions (what Kalshi's KXTRUMPACT settles on) and the
Federal Register's presidential documents as backfilled point-in-time history; EIA's public fuel and
crude price tables, the NWS's raw climate reports as issued, BLS's and BEA's release calendars and
Nasdaq's trading halts.

Built beside league/open_feeds.py (its docstring holds the rule every host here passed, and its helpers)
and merged into it before the run's PR is final; the same three rules hold -- a row is visible only from
the moment it became knowable, live and in replay; a failed poll stores nothing; unchanged content is
stored once. Each Source's docstring names the terms it was checked against and the URL read.
Fetchers: ltcm/data/notices.py, ltcm/data/fuel.py, ltcm/data/cli_text.py, ltcm/data/calendars.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .feeds import Source
from .open_feeds import DAY, _cached, _day_start, _station_key, _stations

_NEW_YORK = ZoneInfo("America/New_York")


def _et_day(moment: float) -> str:
    return datetime.fromtimestamp(float(moment), _NEW_YORK).date().isoformat()


def _count_today(rows: Sequence[tuple[float, Mapping[str, Any]]], field: str, weight: Callable[[Mapping[str, Any]], int]):
    """Each row with `field`: how many items the rows of its New York day at or before it hold (itself included)."""
    out, day, total = [], None, 0
    for at, payload in rows:
        today = _et_day(at)
        total = total + weight(payload) if today == day else weight(payload)
        day = today
        out.append((at, {**payload, field: total}))
    return out


# ---------------------------------------------------------------------- the White House's actions
class PresidentialActions(Source):
    """Each presidential action the White House posts -- executive orders, proclamations, memoranda,
    nominations -- stamped at the post's own publication time: what Kalshi's KXTRUMPACT ("Will Trump do
    anything today?") settles on (its settlement source is https://www.whitehouse.gov/presidential-actions/).

    Terms (read Sept 25, 2026): https://www.whitehouse.gov/copyright/ -- "government-produced materials
    appearing on this site are not copyright protected"; the site has no terms of use (/terms-of-use/ is a
    404) and robots.txt allows everything. The WordPress feed answered the House's contact User-Agent with
    RSS, no bot wall. A pass reads the feed's first page (thirty actions, about 0.6 MB) once for every key;
    the backfill reads `?paged=2`, `?paged=3` ... (a page is about a month of actions).

    The stamp is the feed's pubDate, the post's publication time to the second (UTC): the site's own record
    of when the action appeared. A post the White House backdated would carry the earlier time; nothing in
    the feed tells the two apart, and the history is stamped by the same rule live and backfilled."""

    name = "presidential"
    host = "www.whitehouse.gov"
    source = ("whitehouse: www.whitehouse.gov/presidential-actions/feed/ (RSS; ?paged=N for older pages): every presidential action "
              "the White House posts")
    cadence = "every 15 minutes; backfilled over the replay window"
    what = ("per key (actions: every presidential action; executive_orders, proclamations, memoranda, nominations: one kind), a row "
            "per posting moment: {published, count, actions: [{title, link, guid, kind, categories}] (the actions posted in that "
            "second), today_et (how many actions of the key the White House had posted that New York day, these included)}")
    point_in_time = ("each row is the actions posted in one second, stamped at the posts' own publication time (the feed's pubDate), "
                     "and shown only from then "
                     "on, live and in replay; the history is backfilled from the feed's older pages and stamped the same way; a "
                     "backdated post would carry its earlier time -- the feed cannot tell")
    history = True
    sparse = True
    every = 900.0
    offset = 120.0
    gap = 3600.0
    lookback_days = 1
    max_keys = 5
    timeout = 45.0
    example = "actions"
    note = ("today_et counts the key's actions of the row's New York day up to and including it; a day with no row had no action. "
            "KXTRUMPACT settles on this page.")
    KEYS = ("actions", "executive_orders", "proclamations", "memoranda", "nominations")
    ALIASES = {"kxtrumpact": "actions", "all": "actions", "presidential_actions": "actions", "eo": "executive_orders",
               "eos": "executive_orders", "executive_order": "executive_orders", "orders": "executive_orders",
               "proclamation": "proclamations", "memorandum": "memoranda", "memos": "memoranda", "memo": "memoranda",
               "nomination": "nominations", "appointments": "nominations"}
    MAX_PAGES = 6

    def keys(self, recorder: Any) -> list[str]:
        return list(self.KEYS)

    def key_of(self, raw: Any) -> str | None:
        text = "_".join(str(raw or "").strip().lower().replace("-", " ").split())
        text = self.ALIASES.get(text, text)
        return text if text in self.KEYS else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.notices import Notices

        return Notices(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return "https://www.whitehouse.gov/presidential-actions/feed/?paged=<n>"

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        top = float(now) if before is None else min(float(now), float(before) - 0.001)
        found: dict[float, list[dict[str, Any]]] = {}  # actions posted in the same second are one row (Sept 2026: three at once)
        reached = exhausted = False
        for number in range(1, self.MAX_PAGES + 1):
            items = _cached(recorder, self.name, f"page:{number}", now, 600.0, lambda n=number: fetcher.actions(n))
            if not items:
                exhausted = True
                break
            for item in items:
                if (key == "actions" or item["kind"] == key) and floor <= item["published_at"] <= top:
                    found.setdefault(item["published_at"], []).append({k: v for k, v in item.items() if k not in ("published_at", "published")})
            if min(item["published_at"] for item in items) <= floor:
                reached = True
                break
            if before is not None and min(item["published_at"] for item in items) < top and found:
                break  # a page back: this page brought the actions just older than the ones held
        rows = [(at, {"published": datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "count": len(posted),
                      "actions": posted}) for at, posted in sorted(found.items())]
        return {"rows": rows, "reached": reached, "exhausted": exhausted and not reached}

    def derive(self, rows: Sequence[tuple[float, Mapping[str, Any]]], since: float | None) -> list[tuple[float, dict[str, Any]]]:
        return _count_today(rows, "today_et", lambda payload: int(payload.get("count") or 0))

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"whitehouse", "kxtrumpact"}) or {"white", "house"} <= words or (
            "presidential" in words and bool(words & {"action", "actions", "orders", "order", "proclamations", "memoranda"})) or (
            "executive" in words and bool(words & {"order", "orders"}))


# ------------------------------------------------------------------------- the Federal Register
class FederalRegisterDocuments(Source):
    """The Federal Register's presidential documents -- executive orders, proclamations, memoranda -- a row
    per day's issue, stamped at the morning the issue is public.

    Terms (read Sept 25, 2026): the Federal Register's API needs no key ("No API keys are needed; all you
    need is an HTTP client or browser", its REST API developer page, read through the Aug 27, 2025 Wayback
    copy of https://www.federalregister.gov/reader-aids/developer-resources/rest-api because the live page
    answers automated clients with a CAPTCHA) and its block page says "programmatic access to these sites
    is limited to access to our extensive developer APIs": the House reads /api/v1/ only, never an HTML
    page; robots.txt allows /api/v1/. Federal Register documents are federal works, not copyrighted.

    The stamp: a document's publication_date is the day of the issue it appears in, and the API gives no
    time. The day's issue is on FederalRegister.gov by 6:00 a.m. Eastern (unverified); a day's row is
    stamped 09:00 New York time on its date, three hours later: late, never early. (A document was on
    public inspection the business day before; the inspection file's timestamp is kept, not trusted.)"""

    name = "federal_register"
    host = "www.federalregister.gov"
    source = ("federal register: www.federalregister.gov/api/v1/documents.json?conditions[type][]=PRESDOCU (the API only; the "
              "presidential documents of each day's issue)")
    cadence = "every four hours; backfilled over the replay window"
    what = ("per key (documents: every presidential document; executive_orders, proclamations, memoranda), one row per day's issue "
            "that has any: {date (the publication date), count, documents: [{document_number, title, subtype, signing_date, "
            "executive_order_number, proclamation_number, citation, html_url, public_inspection_url}]}")
    point_in_time = ("each row is a day's issue stamped 09:00 New York time on its publication date (the issue is online by 6:00 a.m. "
                     "Eastern; the API gives no time) and shown only from then on, live and in replay; the history is backfilled "
                     "from the API and stamped by the same rule")
    history = True
    sparse = True
    every = 4 * 3600.0
    offset = 900.0
    gap = 6 * 3600.0
    max_keys = 4
    timeout = 30.0
    example = "executive_orders"
    note = "A day with no row published no document of the key. signing_date is when the President signed it (usually days earlier)."
    KEYS = ("documents", "executive_orders", "proclamations", "memoranda")
    ALIASES = {"all": "documents", "presidential_documents": "documents", "eo": "executive_orders", "eos": "executive_orders",
               "executive_order": "executive_orders", "proclamation": "proclamations", "memorandum": "memoranda", "memos": "memoranda"}
    STAMP_HOUR = 9

    def keys(self, recorder: Any) -> list[str]:
        return list(self.KEYS)

    def key_of(self, raw: Any) -> str | None:
        text = "_".join(str(raw or "").strip().lower().replace("-", " ").split())
        text = self.ALIASES.get(text, text)
        return text if text in self.KEYS else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.notices import Notices

        return Notices(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return "https://www.federalregister.gov/api/v1/documents.json?conditions[type][]=PRESDOCU&conditions[publication_date][gte]=<day>"

    def stamp_of(self, day: date) -> float:
        return datetime(day.year, day.month, day.day, self.STAMP_HOUR, tzinfo=_NEW_YORK).timestamp()

    def _day_at(self, moment: float) -> date:
        """The newest publication day whose row is stamped at or before `moment`."""
        local = datetime.fromtimestamp(float(moment), _NEW_YORK)
        day = local.date()
        return day if self.stamp_of(day) <= float(moment) else day - timedelta(days=1)

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        from ltcm.data.notices import DOCUMENT_SUBTYPES

        top = float(now) if before is None else min(float(now), float(before) - 0.001)
        last = self._day_at(top)
        first = self._day_at(float(floor) - 0.001) + timedelta(days=1)  # the first day stamped at or after floor
        if last < first:
            return {"rows": [], "reached": True, "exhausted": False}
        # One request reads the whole span still missing (a sparse history is searched to its floor in one page:
        # a day without a document is only "none" once the listing was read over it); keys that ask the same
        # span in a pass share it.
        start = first
        memo = recorder.state(self.name).setdefault("memo", {})
        covering = [value for slot, (at, value) in list(memo.items()) if slot.startswith("docs:") and now - at < 600.0
                    and not isinstance(value, BaseException) and slot.split(":")[1] <= start.isoformat() <= last.isoformat()
                    <= slot.split(":")[2]]  # a read this pass already spanned these days (the live read, then the backfill)
        documents = [d for d in covering[0] if start.isoformat() <= d["publication_date"] <= last.isoformat()] if covering else \
            _cached(recorder, self.name, f"docs:{start}:{last}", now, 600.0, lambda: fetcher.documents(start.isoformat(), last.isoformat()))
        subtype = DOCUMENT_SUBTYPES.get(key)
        by_day: dict[str, list[dict[str, Any]]] = {}
        for document in documents:
            if subtype is None or document.get("subtype") == subtype:
                by_day.setdefault(document["publication_date"], []).append({k: v for k, v in document.items() if k != "publication_date"})
        rows = []
        for day, found in sorted(by_day.items()):
            at = self.stamp_of(date.fromisoformat(day))
            if floor <= at <= top:
                rows.append((at, {"date": day, "count": len(found), "documents": sorted(found, key=lambda d: d["document_number"])}))
        return {"rows": rows, "reached": True, "exhausted": False}

    def asks(self, words: set[str]) -> bool:
        return "federalregister" in words or {"federal", "register"} <= words


# ---------------------------------------------------------------------------------- EIA's tables
class FuelPrices(Source):
    """EIA's weekly U.S. retail gasoline and diesel prices and its daily WTI and Brent spot prices, from its
    public history tables -- no key, where the `eia` feed (api.eia.gov) waits for the owner's. Source: U.S.
    Energy Information Administration. Kalshi's gasoline series (KXAAAGAS*) settle on AAA's daily average,
    a different number from a different source, which is not recorded (no terms grant automated access).

    Terms (read Sept 25, 2026): https://www.eia.gov/about/copyrights_reuse.php -- EIA's data are public
    domain: "You may use and/or distribute any of our data", citing "Source: U.S. Energy Information
    Administration"; robots.txt does not disallow /dnav/. The House's contact User-Agent was answered
    with the tables (3-8 s each: EIA is slow). One request per series, every six hours."""

    name = "fuel"
    host = "www.eia.gov"
    source = ("eia (public tables, no key): www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=EMM_EPMR_PTE_NUS_DPG&f=W (gasoline), "
              "s=EMD_EPD2D_PTE_NUS_DPG (diesel), /dnav/pet/hist/RWTCD.htm (WTI), RBRTED.htm (Brent). Source: U.S. Energy Information "
              "Administration")
    cadence = "every six hours a series (gasoline and diesel are weekly, Mondays; WTI and Brent daily, released weekly)"
    what = ("per series (GASOLINE: U.S. regular retail, DIESEL: U.S. No 2 diesel retail, in dollars per gallon; WTI: Cushing spot, "
            "BRENT: Europe Brent spot, in dollars per barrel), EIA's newest published value: {series, what, unit, frequency, latest: "
            "{date, value}, recent: the ten newest [{date, value}], release_date, next_release}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: EIA "
                     "publishes a release date, never the moment a value appeared, so nothing is backfilled")
    every = 6 * 3600.0
    gap = 18 * 3600.0
    max_keys = 4
    timeout = 60.0
    example = "GASOLINE"
    note = "latest.date is the week's end (retail) or the trading day (spot); release_date is the day EIA published the table."
    ALIASES = {"GAS": "GASOLINE", "REGULAR": "GASOLINE", "RETAIL_GASOLINE": "GASOLINE", "EMM_EPMR_PTE_NUS_DPG": "GASOLINE",
               "EMD_EPD2D_PTE_NUS_DPG": "DIESEL", "KXDIESEL": "DIESEL", "KXDIESELW": "DIESEL", "KXDIESELD": "DIESEL",
               "CRUDE": "WTI", "RWTC": "WTI", "KXWTI": "WTI", "CL": "WTI", "RBRTE": "BRENT", "KXBRENT": "BRENT", "KXBRENTD": "BRENT"}

    def keys(self, recorder: Any) -> list[str]:
        from ltcm.data.fuel import SERIES

        return list(SERIES)

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.fuel import SERIES

        text = "_".join(str(raw or "").strip().upper().replace("-", " ").split())
        text = self.ALIASES.get(text, text)
        return text if text in SERIES else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.fuel import Fuel

        return Fuel(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        out: dict[str, Any] = {}
        for key in keys:
            try:
                out[key] = fetcher.series(key)
            except Exception as exc:  # noqa: BLE001 - a series that fails is a failed poll of it
                out[key] = exc
        return out

    def asks(self, words: set[str]) -> bool:
        return "fuel" in words and bool(words & {"price", "prices", "retail", "weekly", "gasoline", "diesel"})


# ---------------------------------------------------------------------- the NWS's own CLI text
class ClimateReportText(Source):
    """The NWS Daily Climate Report of each settlement station as the NWS issued it: its raw text product,
    read the moment the NWS replaces it and parsed. The `cli` feed (league/open_feeds.py) records the same
    reports through the Iowa Environmental Mesonet's parse and backfills them; this one needs no third
    party and sees a report minutes after it is issued, but the NWS keeps only the newest, so it has no
    history before recording began.

    Terms (read Sept 25, 2026): https://www.weather.gov/disclaimer -- NWS information is public domain and
    "may be used without charge for any lawful purpose"; the NWS may block addresses that query too often
    (a station is asked every ten minutes, a failure not again within five). No robots.txt on
    tgftp.nws.noaa.gov; each file answered the House's User-Agent with the product (about 4 KB). New
    Orleans' file (cdus44.klix.cli.msy) answered a redirect to a directory and is left out."""

    name = "cli_text"
    host = "tgftp.nws.noaa.gov"
    source = "nws: tgftp.nws.noaa.gov/data/raw/cd/<wmo>.<office>.cli.<site>.txt (the newest CLI text product of each settlement station)"
    cadence = "every ten minutes a station, spread over passes; not backfilled (the NWS keeps only the newest report)"
    what = ("per settlement station, each Daily Climate Report as the NWS issued it, parsed: {office, wmo, product, issued, date (the "
            "climate day), final, preliminary, as_of, high, high_time, low, low_time (F, local standard time), precip_in, snow_in "
            "(0.0001 is a trace)}; preliminary is True for a same-day report ('VALID TODAY AS OF 0500 PM'), final once the report was "
            "issued after the climate day ended")
    point_in_time = ("each row is stamped with the product's own issue time (its WMO header's day and UTC time, in the month of its "
                     "issue line) and shown only from then on, live and in replay; the NWS keeps only the newest report, so nothing "
                     "before recording began exists -- the cli feed is the backfilled history of the same numbers")
    history = True
    every = 600.0
    offset = 60.0
    gap = 36 * 3600.0
    max_keys = 24
    timeout = 20.0
    pause = 0.5
    example = "KXHIGHNY"
    note = "Markets settle on the final report; the cli feed carries the same reports backfilled."

    def keys(self, recorder: Any) -> list[str]:
        from ltcm.data.cli_text import FILES

        return [station for station in _stations(recorder) if station in FILES]

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.cli_text import FILES

        key = _station_key(raw)
        return key if key in FILES else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.cli_text import ClimateText

        return ClimateText(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        from ltcm.data.cli_text import FILES

        return f"https://tgftp.nws.noaa.gov/data/raw/cd/{FILES.get(key, '<file>')}.txt"

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        if before is not None:
            return {"rows": [], "reached": False, "exhausted": True}  # the NWS keeps only the newest report
        from ltcm.data.weather import city_of_station, standard_offset_hours

        report = fetcher.latest(key)
        at = float(report.pop("issued_at"))
        report["final"] = at >= _day_start(report["date"], standard_offset_hours(city_of_station(key))) + DAY
        rows = [(at, {"station": key, **report})] if floor <= at <= now else []
        return {"rows": rows, "reached": True, "exhausted": False}

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"cli", "climate"}) and bool(words & {"raw", "text", "product", "products", "tgftp"})


# ------------------------------------------------------------------------- release calendars
def _upcoming(rows: Sequence[Mapping[str, Any]], match: Callable[[str], bool], now: float, days: int) -> dict[str, Any]:
    from ltcm.data.calendars import upcoming

    ahead = [dict(row) for row in upcoming(list(rows), now, days) if match(str(row["release"]))]
    stamp_now = datetime.fromtimestamp(float(now), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    later = [row for row in ahead if row["at"] > stamp_now]
    return {"next": later[0] if later else None, "upcoming": ahead[:24]}


class _ReleaseCalendar(Source):
    """A statistical agency's release calendar, receive-stamped (shared by the BLS and BEA recorders)."""

    batch = True
    every = 12 * 3600.0
    gap = 36 * 3600.0
    timeout = 30.0
    DAYS = 60
    AGENCY = ""
    RELEASES: dict[str, tuple[str, ...]] = {}
    ALIASES: dict[str, str] = {}

    def keys(self, recorder: Any) -> list[str]:
        return list(self.RELEASES) + ["all"]

    def key_of(self, raw: Any) -> str | None:
        text = "_".join(str(raw or "").strip().lower().replace("-", " ").split())
        text = self.ALIASES.get(text, text)
        return text if text in self.RELEASES or text == "all" else None

    def _match(self, key: str) -> Callable[[str], bool]:
        if key == "all":
            return lambda title: True
        names = self.RELEASES[key]
        return lambda title: any(title.startswith(name) or name in title for name in names)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        rows = self.read(fetcher)
        return {key: {"agency": self.AGENCY, "release": key, **_upcoming(rows, self._match(key), now, self.DAYS)} for key in keys}


class BlsReleases(_ReleaseCalendar):
    """The Bureau of Labor Statistics' release calendar: when CPI, the Employment Situation, PPI, JOLTS and
    the rest come out (8:30 or 10:00 a.m. Eastern) -- what KXCPI, KXCPIYOY, KXCPICORE, KXU3 and KXPAYROLLS
    resolve on.

    Terms (read Sept 25, 2026): https://www.bls.gov/bls/linksite.htm -- "everything that we publish, both in
    hard copy and electronically, is in the public domain ... You are free to use our public domain material
    without specific permission" (cite BLS); robots.txt does not disallow /schedule/news_release/. The
    calendar file answered the House's contact User-Agent (text/calendar), no bot wall. One request twice a day."""

    name = "bls_releases"
    host = "www.bls.gov"
    AGENCY = "BLS"
    source = "bls: www.bls.gov/schedule/news_release/bls.ics (the economic news release calendar)"
    cadence = "twice a day"
    what = ("per release (cpi, jobs: the Employment Situation, ppi, jolts, eci, real_earnings, import_prices, productivity, all), "
            "BLS's schedule for the next 60 days: {agency, release, next: {release, at (UTC), date, time_et}, upcoming: [...]}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: BLS "
                     "publishes no time a calendar entry appeared or moved, so nothing is backfilled and a moved date is a new row")
    example = "cpi"
    note = "next is the soonest release still to come; upcoming includes today's, released or not."
    RELEASES = {"cpi": ("Consumer Price Index",), "jobs": ("Employment Situation",), "ppi": ("Producer Price Index",),
                "jolts": ("Job Openings and Labor Turnover Survey",), "eci": ("Employment Cost Index",),
                "real_earnings": ("Real Earnings",), "import_prices": ("U.S. Import and Export Price Indexes",),
                "productivity": ("Productivity and Costs",)}
    ALIASES = {"kxcpi": "cpi", "kxcpiyoy": "cpi", "kxcpicore": "cpi", "consumer_price_index": "cpi", "kxpayrolls": "jobs",
               "kxu3": "jobs", "payrolls": "jobs", "nfp": "jobs", "employment_situation": "jobs", "unemployment": "jobs",
               "producer_price_index": "ppi", "bls": "all"}

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.calendars import Calendars

        return Calendars(transport, timeout=self.timeout, clock=clock)

    def read(self, fetcher: Any) -> list[dict[str, Any]]:
        return fetcher.bls()

    def asks(self, words: set[str]) -> bool:
        timed = bool(words & {"calendar", "schedule", "schedules", "dates", "date", "times"})
        released = bool(words & {"release", "releases"})
        return timed and ("bls" in words or (released and bool(words & {"cpi", "jobs", "payrolls", "nfp", "ppi", "jolts", "economic"})))


class BeaReleases(_ReleaseCalendar):
    """The Bureau of Economic Analysis' release schedule: when GDP, Personal Income and Outlays (PCE) and the
    trade balance come out -- what KXGDP resolves on.

    Terms (read Sept 25, 2026): BEA is a federal agency whose works are not copyrighted (17 U.S.C. 105);
    https://www.bea.gov/help/guidelines-for-citing-bea asks only that it be cited, no BEA policy page
    (https://www.bea.gov/about/policies-and-information) restricts automated access, and robots.txt does not
    disallow /news/. The schedule page answered the House's contact User-Agent with HTML, no bot wall. BEA's
    data API needs a key (the owner's step); this reads only the public schedule page, twice a day."""

    name = "bea_releases"
    host = "www.bea.gov"
    AGENCY = "BEA"
    source = "bea: www.bea.gov/news/schedule (the release schedule table, an HTML page)"
    cadence = "twice a day"
    what = ("per release (gdp, pce: Personal Income and Outlays, trade, all), BEA's schedule for the next 60 days: {agency, release, "
            "next: {release, kind, at (UTC), date, time_et}, upcoming: [...]}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: BEA "
                     "publishes no time a schedule entry appeared or moved, so nothing is backfilled and a moved date is a new row")
    example = "gdp"
    note = "A page that changes shape is a failed poll, never a guessed date."
    RELEASES = {"gdp": ("GDP",), "pce": ("Personal Income and Outlays",), "trade": ("International Trade in Goods and Services",)}
    ALIASES = {"kxgdp": "gdp", "gross_domestic_product": "gdp", "personal_income": "pce", "kxpce": "pce", "bea": "all"}

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.calendars import Calendars

        return Calendars(transport, timeout=self.timeout, clock=clock)

    def read(self, fetcher: Any) -> list[dict[str, Any]]:
        return fetcher.bea()

    def asks(self, words: set[str]) -> bool:
        timed = bool(words & {"calendar", "schedule", "schedules", "dates", "date", "times"})
        return timed and ("bea" in words or ("gdp" in words and bool(words & {"release", "releases"})))


# ---------------------------------------------------------------------------------- trading halts
class TradeHalts(Source):
    """Nasdaq Trader's trade halts: every U.S. listed stock halted today (and the long-standing halts), with
    the reason code and, once it is known, the resumption -- for the equity desks' stocks and in all.

    Terms (read Sept 25, 2026): https://www.nasdaqtrader.com/Trader.aspx?id=TradeHaltRSS -- "The Trade Halt
    RSS Feed is a free service", with its own terms
    (https://www.nasdaqtrader.com/content/administrationsupport/agreementstrading/THRSSFeedTermsCond.pdf),
    which bar only editing or misrepresenting the feed; "Please do not query the data more than once a
    minute" -- the House asks every five minutes, one request for every key. No robots.txt; answered the
    House's contact User-Agent with RSS.

    Receive-stamped, not at the halt time: a halt's item changes when the issue resumes (its resumption
    times fill in), and a history row keeps its first version, so each change is a new row at the moment
    the House saw it; the feed holds only the day's halts, so there is nothing to backfill."""

    name = "halts"
    host = "www.nasdaqtrader.com"
    source = "nasdaq: www.nasdaqtrader.com/rss.aspx?feed=tradehalts (the Trade Halt RSS feed)"
    cadence = "every five minutes"
    what = ("per stock the equity desks trade, and `all`: the halts the feed lists now: {symbol (None for all), count, halts: [{symbol, "
            "name, market, reason (Nasdaq's halt code: T1 news pending, LUDP volatility pause, H10 SEC suspension ...), halted (UTC), "
            "pause_threshold, resumed_quotes, resumed_trading}]} -- an empty list is a stock not halted")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: a halt's "
                     "resumption fills in after it began, so every change is a new row when the House saw it; the feed holds only the "
                     "current halts, so nothing is backfilled")
    batch = True
    every = 300.0
    gap = 3 * 300.0
    max_keys = 40
    timeout = 20.0
    example = "AAPL"
    note = "halted is the halt's own time (Eastern in the feed, UTC here); a stock with no halt has halts []."

    def keys(self, recorder: Any) -> list[str]:
        from .feeds import earnings_tickers

        return earnings_tickers(recorder.niches())[: self.max_keys - 1] + ["all"]

    def key_of(self, raw: Any) -> str | None:
        from .feeds import _ticker_key

        text = str(raw or "").strip()
        return "all" if text.lower() in ("all", "halts", "every") else _ticker_key(text)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.notices import Notices

        return Notices(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        halts = fetcher.halts()
        out: dict[str, Any] = {}
        for key in keys:
            found = halts if key == "all" else [row for row in halts if row["symbol"] == key]
            out[key] = {"symbol": None if key == "all" else key, "count": len(found), "halts": found}
        return out

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"halt", "halts", "halted", "luld", "suspension", "suspensions"}) and not words & {"circuit", "kalshi"}


SOURCES: tuple[Source, ...] = (PresidentialActions(), FederalRegisterDocuments(), FuelPrices(), ClimateReportText(), BlsReleases(),
                               BeaReleases(), TradeHalts())
