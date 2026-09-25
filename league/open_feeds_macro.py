"""The macro recorders of the Kalshi-scale run, Sept 25, 2026 (workstream I2): BLS's published series,
the Treasury's cash, debt and auctions, the ECB's euro reference rates, the CFTC's Commitments of
Traders and the Federal Reserve Board's calendar -- for Kalshi's economics (KXCPI, KXCPIYOY,
KXCPICORE, KXU3, KXPAYROLLS), rates, Fed (KXFED) and FX (KXEURUSD, KXUSDJPY) series.

Built beside league/open_feeds.py (which registers `SOURCES`) and merged into it; the same three rules
hold: a row is visible only from when it became knowable, a failed poll stores nothing, unchanged
content is stored once. Fetchers: ltcm/data/releases.py and ltcm/data/fx.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .feeds import BLOCKED, NOT_LISTED, Source
from .open_feeds import DAY

_FFT = ZoneInfo("Europe/Berlin")


# ---------------------------------------------------------------------------------------- BLS
class BlsSeries(Source):
    """The Bureau of Labor Statistics' published series that Kalshi's economics markets settle on --
    CPI (headline, core, not seasonally adjusted), the unemployment rate, payrolls, average hourly
    earnings, PPI -- as BLS's public data API answers now.

    Terms (read Sept 25, 2026): https://www.bls.gov/developers/ and
    https://www.bls.gov/developers/termsOfService.htm -- version 1 of the API needs no registration (25
    queries a day, 25 series a query; https://www.bls.gov/developers/api_faqs.htm) and nothing in the
    terms bars automated use; the API host's robots.txt (`Disallow: /`) is a crawler rule for a host
    that exists only for programs. Answered the House's User-Agent with JSON. ONE query (a POST that
    only reads) answers every series; polled every 90 minutes -- 16 of the 25 daily queries, the rest
    left for restarts. BLS's own answer that the day's queries are spent is recorded as `BLOCKED` (asked
    again at the next cadence, never every five minutes)."""

    name = "bls"
    host = "api.bls.gov"
    source = ("bls: api.bls.gov/publicAPI/v1/timeseries/data/ (one query for CUSR0000SA0, CUSR0000SA0L1E, CUUR0000SA0, "
              "LNS14000000, CES0000000001, CES0500000003, WPSFD4; no key: 25 queries a day)")
    cadence = "every 90 minutes (BLS releases at 08:30 ET; the keyless API allows 25 queries a day)"
    what = ("per series (CPI, CPI_CORE, CPI_NSA, UNRATE, PAYROLLS, AHE, PPI), what BLS has published: {series_id, latest: "
            "{period (YYYY-MM), value, period_name, latest, preliminary}, change_1m_pct, change_12m_pct, diff_1m (the change in "
            "the series' own units: thousands of jobs for PAYROLLS, points for UNRATE), recent: the 13 newest months}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: BLS "
                     "publishes no time a value appeared (its releases are at 08:30 ET), so nothing is backfilled; a revision "
                     "is a new row")
    batch = True
    every = 5400.0
    gap = 3 * 5400.0
    timeout = 30.0
    example = "CPI"
    note = ("CPI is seasonally adjusted (Kalshi's monthly CPI markets); CPI_NSA is the index the year-over-year markets settle "
            "on. A preliminary value (payrolls, earnings, PPI) is revised in later months.")
    ALIASES = {"KXCPI": "CPI", "HEADLINE": "CPI", "CPIU": "CPI", "KXCPICORE": "CPI_CORE", "CORE": "CPI_CORE", "CORECPI": "CPI_CORE",
               "KXCPICOREYOY": "CPI_CORE", "KXCPIYOY": "CPI_NSA", "CPIYOY": "CPI_NSA", "KXU3": "UNRATE", "U3": "UNRATE",
               "UNEMPLOYMENT": "UNRATE", "KXPAYROLLS": "PAYROLLS", "NFP": "PAYROLLS", "NONFARM": "PAYROLLS", "JOBS": "PAYROLLS",
               "EARNINGS": "AHE", "WAGES": "AHE", "KXPPI": "PPI"}

    def keys(self, recorder: Any) -> list[str]:
        from ltcm.data.releases import BLS_SERIES

        return list(BLS_SERIES)

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.releases import BLS_SERIES

        text = str(raw or "").strip().upper().replace("-", "_").replace(" ", "_")
        by_id = {series: name for name, series in BLS_SERIES.items()}
        text = by_id.get(text, self.ALIASES.get(text.replace("_", ""), self.ALIASES.get(text, text)))
        return text if text in BLS_SERIES else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.releases import Releases

        return Releases(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        from ltcm.data import DataError
        from ltcm.data.releases import BLS_SERIES, bls_summary

        try:
            found = fetcher.bls([BLS_SERIES[key] for key in keys])
        except DataError as exc:
            if "threshold" in str(exc).lower() or "daily" in str(exc).lower():  # BLS: the day's 25 queries are spent
                raise DataError(f"{BLOCKED} {exc}") from exc
            raise
        out: dict[str, Any] = {}
        for key in keys:
            rows = found.get(BLS_SERIES[key]) or []
            try:
                out[key] = {"key": key, **bls_summary(BLS_SERIES[key], rows)}
            except DataError as exc:
                out[key] = exc
        return out

    def asks(self, words: set[str]) -> bool:
        if words & {"nowcast", "nowcasting", "forecast", "forecasts", "consensus", "expectation", "expectations", "estimate",
                    "estimates", "calendar", "schedule", "surprise"}:
            return False
        return "bls" in words or bool(words & {"cpi", "payrolls", "nonfarm", "nfp", "ppi", "unemployment", "u3"})


# ---------------------------------------------------------------------------------- FiscalData
class TreasuryFiscal(Source):
    """The Treasury's own daily cash (the Treasury General Account on the Daily Treasury Statement),
    Debt to the Penny, and its auctions -- announced (upcoming) and with their results (high yield,
    bid-to-cover, indirect share) -- from FiscalData.

    Terms (read Sept 25, 2026): https://fiscaldata.treasury.gov/api-documentation/ -- the API "does not
    require a user account or registration for a token"; the data may be used "for non-commercial or
    commercial purposes" (https://www.treasurydirect.gov/legal-information/developers/web-api-terms/);
    fiscaldata.treasury.gov's robots.txt allows everything. Answered the House's User-Agent with JSON.
    Three requests a poll (one a key), every three hours."""

    name = "fiscal"
    host = "api.fiscaldata.treasury.gov"
    source = ("fiscaldata: api.fiscaldata.treasury.gov/services/api/fiscal_service v1/accounting/dts/operating_cash_balance, "
              "v2/accounting/od/debt_to_penny, v1/accounting/od/auctions_query")
    cadence = "every three hours (the Daily Treasury Statement is published about 16:00 ET the next business day)"
    what = ("tga: the newest Daily Treasury Statement's Treasury General Account {record_date, opening, closing, deposits, "
            "withdrawals (millions of dollars), days: [{date, closing}]}; debt: Debt to the Penny {record_date, total, "
            "held_by_public, intragovernmental (dollars), change_1d, days}; auctions: {upcoming: announced auctions without a "
            "result, recent: auctions with their result -- each {cusip, type, term, reopening, announced, auction_date, "
            "issue_date, closing_time, offering_bn, high_yield, high_discount_rate, high_investment_rate, bid_to_cover, "
            "accepted_bn, indirect_pct, direct_pct, dealer_pct}}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: FiscalData "
                     "carries a record date, never the moment a record appeared, so nothing is backfilled")
    every = 3 * 3600.0
    gap = 9 * 3600.0
    timeout = 30.0
    example = "auctions"
    note = "record_date is the business day a statement covers; it is published the next business day."
    KEYS = ("tga", "debt", "auctions")
    ALIASES = {"tga": "tga", "dts": "tga", "cash": "tga", "treasury_general_account": "tga", "debt": "debt",
               "debt_to_the_penny": "debt", "debt_to_penny": "debt", "national_debt": "debt", "auctions": "auctions",
               "auction": "auctions", "treasury_auctions": "auctions"}

    def keys(self, recorder: Any) -> list[str]:
        return list(self.KEYS)

    def key_of(self, raw: Any) -> str | None:
        return self.ALIASES.get(str(raw or "").strip().lower().replace(" ", "_").replace("-", "_"))

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.releases import Releases

        return Releases(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        out: dict[str, Any] = {}
        for key in keys:
            try:
                if key == "tga":
                    out[key] = fetcher.tga()
                elif key == "debt":
                    out[key] = fetcher.debt()
                else:
                    found = fetcher.auctions()
                    out[key] = {"upcoming": found["upcoming"][:12], "recent": found["recent"][:12]}
            except Exception as exc:  # noqa: BLE001 - one dataset that fails is a failed poll of that key
                out[key] = exc
        return out

    def asks(self, words: set[str]) -> bool:
        treasury = bool(words & {"treasury", "treasuries", "ust", "bill", "bills", "note", "notes", "bond", "bonds"})
        return bool(words & {"tga", "dts", "fiscaldata"}) or ("debt" in words and bool(words & {"penny", "national", "federal", "public"})) \
            or (bool(words & {"auction", "auctions"}) and treasury) or {"treasury", "general", "account"} <= words


# ----------------------------------------------------------------------------------------- ECB
def _fx_stamp(day: str) -> float:
    """17:00 Frankfurt time on `day`: the ECB publishes "around 16:00 CET", and an hour is allowed for it."""
    return datetime.fromisoformat(day).replace(hour=17, tzinfo=_FFT).timestamp()


class EcbReferenceRates(Source):
    """The ECB's euro foreign exchange reference rates, one row a currency a TARGET business day, as
    history: the fixing of every major currency, for Kalshi's daily EUR/USD and USD/JPY series.

    Terms (read Sept 25, 2026): https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html --
    "users of this website may make free use of the information obtained directly from it", reproduced
    accurately and citing the ECB; the rates are "published for information purposes only" (an input
    to a model, never a transaction price). robots.txt does not disallow /stats/eurofxref/ and asks for
    five seconds between requests; key-free, answered the House's User-Agent with XML. One request a
    poll, hourly."""

    name = "fx"
    host = "www.ecb.europa.eu"
    source = ("ecb: www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml (the newest day) and eurofxref-hist-90d.xml (the "
              "history): the euro reference rates, units of each currency per euro")
    cadence = "hourly, twenty minutes past the hour (published about 16:00 CET each TARGET business day); backfilled 75 days"
    what = ("per currency (USD, JPY, GBP, CHF, CAD, AUD, CNY, MXN; any of the ECB's 29), each business day's reference rate: {currency, "
            "date, per_eur (units per euro), per_usd (units per US dollar, the cross through the day's USD rate; None for USD), "
            "change_1d_pct, change_5d_pct (of per_eur), usd_change_1d_pct (of per_usd), from rows at or before it}")
    point_in_time = ("each row is stamped 17:00 Frankfurt time on its date -- the ECB publishes 'around 16:00 CET' and an hour is "
                     "allowed -- or at the file's Last-Modified when that is later the same day; shown only from then on, live and "
                     "in replay, and a day is stored only once its stamp has passed; the history is backfilled from the ECB's 90-day "
                     "file and stamped the same way")
    history = True
    every = 3600.0
    offset = 1200.0
    gap = 4 * DAY  # a weekend and a holiday between two fixings
    lookback_days = 8
    backfill_days = 75.0
    max_keys = 30
    timeout = 30.0
    example = "USD"
    note = ("The ECB publishes rates for information only; Kalshi's FX series settle on their own sources. per_usd of JPY is "
            "USD/JPY; 1/per_eur of USD is EUR per dollar.")
    DEFAULT = ("USD", "JPY", "GBP", "CHF", "CAD", "AUD", "CNY", "MXN")
    CURRENCIES = frozenset(("USD", "JPY", "CZK", "DKK", "GBP", "HUF", "PLN", "RON", "SEK", "CHF", "ISK", "NOK", "TRY", "AUD", "BRL",
                            "CAD", "CNY", "HKD", "IDR", "ILS", "INR", "KRW", "MXN", "MYR", "NZD", "PHP", "SGD", "THB", "ZAR"))
    #: The daily file is read while the newest row held is this recent; else the 90-day file.
    RECENT = 26 * 3600.0

    def keys(self, recorder: Any) -> list[str]:
        return list(self.DEFAULT)

    def key_of(self, raw: Any) -> str | None:
        text = str(raw or "").strip().upper().replace("/", "").replace("-", "").replace("_", "").replace(" ", "")
        text = text[2:] if text.startswith("KX") else text
        if len(text) == 6:
            base, quote = text[:3], text[3:]
            text = quote if base == "EUR" else base if quote in ("EUR", "USD") and base != "USD" else quote if base == "USD" else ""
        return text if text in self.CURRENCIES else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.fx import Ecb

        return Ecb(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return f"https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml ({key} per euro)"

    @staticmethod
    def rows(days: Mapping[str, Mapping[str, float]], modified: float | None, key: str) -> list[tuple[float, dict[str, Any]]]:
        newest = max(days) if days else None
        out = []
        for day, rates in days.items():
            if key not in rates:
                continue
            at = _fx_stamp(day)
            if day == newest and modified is not None and datetime.fromtimestamp(modified, _FFT).date().isoformat() == day:
                at = max(at, modified)  # published late that day: stamped when the file changed
            usd = rates.get("USD")
            per_usd = round(rates[key] / usd, 6) if usd and key != "USD" else None
            out.append((at, {"currency": key, "date": day, "per_eur": rates[key], "per_usd": per_usd}))
        return sorted(out)

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        from ltcm.data import DataError

        from .open_feeds import _cached

        if key not in self.CURRENCIES:
            raise DataError(f"{NOT_LISTED} the ECB publishes no reference rate for {key}")
        newest = (recorder._load_stats().get((self.name, key)) or {}).get("last_ok") if before is None else None
        daily = newest is not None and now - float(newest) <= self.RECENT
        days, modified = _cached(recorder, self.name, "daily" if daily else "90d", now, 300.0,
                                 fetcher.daily if daily else fetcher.last_90_days)
        rows = self.rows(days, modified, key)
        oldest = min((at for at, _ in rows), default=None)
        rows = [(at, p) for at, p in rows if floor <= at <= now and (before is None or at < before)]
        reached = daily or (oldest is not None and oldest <= floor)
        return {"rows": rows, "reached": reached, "exhausted": before is not None and not reached}

    def derive(self, rows: Sequence[tuple[float, Mapping[str, Any]]], since: float | None) -> list[tuple[float, dict[str, Any]]]:
        out = []
        values = [(p.get("per_eur"), p.get("per_usd")) for _, p in rows]

        def pct(now_value: Any, then_value: Any) -> float | None:
            return round((now_value / then_value - 1.0) * 100.0, 4) if now_value is not None and then_value else None

        for index, (at, payload) in enumerate(rows):
            eur, usd = values[index]
            one = values[index - 1] if index >= 1 else (None, None)
            five = values[index - 5] if index >= 5 else (None, None)
            out.append((at, {**payload, "change_1d_pct": pct(eur, one[0]), "change_5d_pct": pct(eur, five[0]),
                             "usd_change_1d_pct": pct(usd, one[1])}))
        return out

    def asks(self, words: set[str]) -> bool:
        if words & {"ecb", "eurofxref"}:
            return True
        pair = bool(words & {"fx", "forex", "eurusd", "usdjpy", "gbpusd", "usdcad", "audusd", "usdchf", "currency", "currencies"}) or \
            {"exchange", "rate"} <= words or {"exchange", "rates"} <= words
        return pair and bool(words & {"rate", "rates", "reference", "fixing", "fixings", "daily", "history", "historical", "euro"})



# ---------------------------------------------------------------------------------------- CFTC
class CommitmentsOfTraders(Source):
    """The CFTC's weekly Commitments of Traders (legacy, futures only) for the markets beside the
    desks' -- CME bitcoin, the E-mini S&P 500, the 10-year note, gold, WTI crude and the euro: open
    interest and the speculators' (non-commercial) and hedgers' (commercial) long, short and net.

    Terms (read Sept 25, 2026): https://www.cftc.gov/WebPolicy/index.htm -- "Government information at
    the CFTC website is in the public domain"; the Socrata API on publicreporting.cftc.gov is used without
    an app token ("As long as you are not overusing the API, you should be able to use the API without a
    token", dev.socrata.com/docs/app-tokens.html) and robots.txt allows /resource/ with a one-second
    crawl delay. Answered the House's User-Agent with JSON. One request a market a pass, a second apart.

    The stamp is the whole of its honesty: a report's positions are as of a Tuesday and the CFTC
    releases it that Friday at 15:30 ET -- the following Monday in a holiday week -- and publishes no
    release time in the data. A report is stamped seven days after its as-of date, 00:00 UTC (Monday
    evening in New York, after the latest regular release), and stored only once that has passed; a
    report the House first sees more than twelve hours after that stamp (published late, as during the
    2025 shutdown, or the House was away) is stamped when the House received it."""

    name = "cot"
    host = "publicreporting.cftc.gov"
    source = ("cftc: publicreporting.cftc.gov/resource/6dca-aqww.json (Commitments of Traders, legacy, futures only) per CFTC "
              "contract market code")
    cadence = "every six hours; a weekly report is stored once its stamp passes (the Tuesday after its as-of Tuesday); backfilled"
    what = ("per market (BTC: CME bitcoin, ES: E-mini S&P 500, TY: 10-year note, GOLD, WTI, EUR: euro FX), each weekly report: {as_of "
            "(the Tuesday the positions are as of), code, market, open_interest, change_open_interest, noncommercial: {long, short, "
            "spread, net, change_long, change_short, pct_oi_long, pct_oi_short}, commercial: {long, short, net}, nonreportable: "
            "{long, short}, traders, net_change_1w (the non-commercial net against the report before it)}")
    point_in_time = ("each row is stamped seven days after its as-of Tuesday, 00:00 UTC -- after the CFTC's Friday 15:30 ET release "
                     "and the Monday release of a holiday week -- and shown only from then on, live and in replay; a report first "
                     "seen more than twelve hours after that is stamped when the House received it; the history is backfilled from "
                     "the CFTC's own reports and stamped by the same rule")
    history = True
    every = 6 * 3600.0
    offset = 900.0
    gap = 8 * DAY
    lookback_days = 8
    max_keys = 12
    timeout = 30.0
    pause = 1.0
    example = "BTC"
    note = "Weekly: a report's positions are as of its Tuesday; net = long - short; the stamp trails the release by about three days."
    LAG = 7 * DAY
    LATE = 12 * 3600.0
    PAGE = 30
    ALIASES = {"BITCOIN": "BTC", "XBT": "BTC", "133741": "BTC", "SPX": "ES", "SP500": "ES", "S&P500": "ES", "EMINI": "ES",
               "13874A": "ES", "10Y": "TY", "UST10Y": "TY", "TNOTE": "TY", "ZN": "TY", "043602": "TY", "GC": "GOLD",
               "XAU": "GOLD", "088691": "GOLD", "CL": "WTI", "CRUDE": "WTI", "OIL": "WTI", "067651": "WTI", "EURUSD": "EUR",
               "6E": "EUR", "EUROFX": "EUR", "099741": "EUR"}

    def keys(self, recorder: Any) -> list[str]:
        from ltcm.data.releases import COT_MARKETS

        return list(COT_MARKETS)

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.releases import COT_MARKETS

        text = str(raw or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "").replace("/", "")
        text = self.ALIASES.get(text, text)
        return text if text in COT_MARKETS else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.releases import Releases

        return Releases(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        from ltcm.data.releases import COT_MARKETS

        return f"https://publicreporting.cftc.gov/resource/6dca-aqww.json?cftc_contract_market_code={COT_MARKETS.get(key, key)}"

    def stamp_of(self, as_of: str) -> float:
        return datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc).timestamp() + self.LAG

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        from ltcm.data.releases import COT_MARKETS

        newest = (recorder._load_stats().get((self.name, key)) or {}).get("last_ok") if before is None else None
        since = datetime.fromtimestamp(float(floor) - self.LAG, timezone.utc).date().isoformat()
        until = datetime.fromtimestamp(float(before) - self.LAG, timezone.utc).date().isoformat() if before is not None else None
        reports = fetcher.cot(COT_MARKETS[key], since=since, before=until, limit=self.PAGE)
        rows = []
        for report in reports:
            at = self.stamp_of(report["as_of"])
            if newest is not None and at > float(newest) and now - at > self.LATE:
                at = float(now)  # first seen long after its stamp: published late, or the House was away
            if at <= now and at >= floor and (before is None or at < before):
                rows.append((at, report))
        reached = len(reports) < self.PAGE
        return {"rows": rows, "reached": reached, "exhausted": not reports and not reached}

    def derive(self, rows: Sequence[tuple[float, Mapping[str, Any]]], since: float | None) -> list[tuple[float, dict[str, Any]]]:
        out = []
        prior = None
        for at, payload in rows:
            net = (payload.get("noncommercial") or {}).get("net")
            out.append((at, {**payload, "net_change_1w": round(net - prior, 2) if net is not None and prior is not None else None}))
            prior = net if net is not None else prior
        return out

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"cot", "cftc"}) or {"commitments", "traders"} <= words or (
            bool(words & {"speculative", "speculators", "noncommercial", "commercials"}) and bool(words & {"positioning", "positions", "futures"}))


# ------------------------------------------------------------------------------------ the Fed
class FedCalendar(Source):
    """The Federal Reserve Board's calendar: the FOMC's meetings (the decision day at 2:00 p.m.), its
    minutes and press conferences, the Board's speeches and testimony, and the Beige Book -- the
    schedule Kalshi's KXFED and the Fed "mention" markets trade around.

    Terms (read Sept 25, 2026): https://www.federalreserve.gov/disclaimer.htm -- "information on Board's
    website is in the public domain and may be copied and distributed without permission"; no
    robots.txt (404). The calendar is the JSON the Board's own pages read (undocumented: it can change
    shape, and a changed shape is a failed poll). Answered the House's User-Agent. One request (about
    0.5 MB) answers every key, every twelve hours."""

    name = "fomc"
    host = "www.federalreserve.gov"
    source = "fed: www.federalreserve.gov/json/calendar.json (the Board's calendar of FOMC meetings, speeches, testimony, releases)"
    cadence = "every twelve hours"
    what = ("per kind -- fomc (meetings, minutes, press conferences), speeches, testimony, beige (the Beige Book) -- the Board's "
            "calendar from today on: {kind, next (the first event), next_meeting (fomc only: the next 'FOMC Meeting', the "
            "decision day), events: the 12 soonest [{date, end_date, title, type, time (ET), description, link}]}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: the "
                     "calendar carries no time an entry was added, so nothing is backfilled; a moved meeting is a new row")
    batch = True
    every = 12 * 3600.0
    gap = 36 * 3600.0
    timeout = 45.0
    example = "fomc"
    note = "Times are Eastern; an FOMC decision is announced at the meeting's 'time' on its end_date."
    KEYS = ("fomc", "speeches", "testimony", "beige")
    ALIASES = {"fomc": "fomc", "fed": "fomc", "kxfed": "fomc", "meetings": "fomc", "fed_meetings": "fomc", "speeches": "speeches",
               "speech": "speeches", "fed_speeches": "speeches", "testimony": "testimony", "beige": "beige", "beige_book": "beige"}

    def keys(self, recorder: Any) -> list[str]:
        return list(self.KEYS)

    def key_of(self, raw: Any) -> str | None:
        return self.ALIASES.get(str(raw or "").strip().lower().replace(" ", "_").replace("-", "_"))

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.releases import Releases

        return Releases(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        calendar = fetcher.calendar()
        out: dict[str, Any] = {}
        for key in keys:
            events = calendar.get(key) or []
            row: dict[str, Any] = {"kind": key, "next": events[0] if events else None, "events": events[:12]}
            if key == "fomc":
                row["next_meeting"] = next((e for e in events if e["title"].lower().startswith("fomc meeting")), None)
            out[key] = row
        return out

    def asks(self, words: set[str]) -> bool:
        fed = bool(words & {"fed", "federal", "fomc", "powell"})
        return "fomc" in words or (fed and bool(words & {"calendar", "meeting", "meetings", "speech", "speeches", "testimony", "beige",
                                                          "minutes", "schedule", "dates"}))


SOURCES: tuple[Source, ...] = (BlsSeries(), TreasuryFiscal(), EcbReferenceRates(), CommitmentsOfTraders(), FedCalendar())
