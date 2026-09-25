"""Macro releases and calendars for Kalshi's economics, rates and Fed desks (Sept 25, 2026, the
Kalshi-scale run's recorders, league/open_feeds_macro.py): BLS's published series, the Treasury's
cash, debt and auctions, the CFTC's Commitments of Traders, and the Federal Reserve Board's calendar.

Kalshi's KXCPI, KXCPIYOY, KXCPICORE, KXU3 and KXPAYROLLS settle on BLS releases; KXFED on the FOMC's
decision. Every host here is public-domain government data, key-free:

    POST https://api.bls.gov/publicAPI/v1/timeseries/data/   {"seriesid": [...], "startyear", "endyear"}
      status "REQUEST_SUCCEEDED", Results.series[]: seriesID, data[]: year, period ("M08"),
      periodName, latest ("true" on the newest), value (string), footnotes[] ({code: "P", text:
      "preliminary"}). Version 1 needs no registration: 25 queries a day, up to 25 series and 10
      years a query (https://www.bls.gov/developers/api_faqs.htm). Probed Sept 25, 2026 06:55Z with
      the seven series below: every one answered, newest period 2026-08. A POST that asks for data
      is a read: nothing is created.
    GET https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance
        ?sort=-record_date&page[size]=12
      data[]: record_date, account_type ("Treasury General Account (TGA) Closing Balance", ...),
      open_today_bal (millions of dollars: the day's amount in the current DTS layout), ...
    GET .../v2/accounting/od/debt_to_penny?sort=-record_date&page[size]=5
      data[]: record_date, tot_pub_debt_out_amt, debt_held_public_amt, intragov_hold_amt (dollars)
    GET .../v1/accounting/od/auctions_query?sort=-auction_date&page[size]=30
      data[]: cusip, security_type, security_term, announcemt_date, auction_date, issue_date,
      offering_amt, high_yield / high_discnt_rate / high_investment_rate, bid_to_cover_ratio,
      total_tendered, total_accepted, indirect_bidder_accepted, direct_bidder_accepted,
      primary_dealer_accepted, closing_time_comp; "null" (a string) for what is not yet known.
    GET https://publicreporting.cftc.gov/resource/6dca-aqww.json?cftc_contract_market_code=133741
        &$order=report_date_as_yyyy_mm_dd DESC&$limit=20
      The legacy futures-only Commitments of Traders (dataset 6dca-aqww; 72hh-3qpy is the
      disaggregated and gpe5-46if the traders-in-financial-futures one, both verified Sept 25, 2026):
      report_date_as_yyyy_mm_dd (the Tuesday the positions are as of), market_and_exchange_names,
      open_interest_all, noncomm_positions_long_all / _short_all / _spread_all,
      comm_positions_long_all / _short_all, nonrept_positions_long_all / _short_all,
      change_in_open_interest_all, change_in_noncomm_long_all / _short_all, pct_of_oi_noncomm_long_all
      / _short_all, traders_tot_all (strings). Newest on Sept 25, 2026 06:59Z: 2026-09-15.
    GET https://www.federalreserve.gov/json/calendar.json  (ltcm/data/macro.py `calendar_row` reads it)

Numbers come back as floats (or None), never Decimals, so a row ships as JSON.
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from . import CONTACT_USER_AGENT, DataError, HttpTransport, read_json, require
from .macro import calendar_row, period_key

BLS_V1_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
FISCAL_HOST = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
DTS_CASH_URL = FISCAL_HOST + "/v1/accounting/dts/operating_cash_balance"
DEBT_URL = FISCAL_HOST + "/v2/accounting/od/debt_to_penny"
AUCTIONS_URL = FISCAL_HOST + "/v1/accounting/od/auctions_query"
COT_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
FED_CALENDAR_URL = "https://www.federalreserve.gov/json/calendar.json"
#: The BLS series recorded, by the name a strategy uses (verified Sept 25, 2026).
BLS_SERIES: dict[str, str] = {
    "CPI": "CUSR0000SA0",          # CPI-U, all items, seasonally adjusted (the monthly change Kalshi's KXCPI prices)
    "CPI_CORE": "CUSR0000SA0L1E",  # CPI-U less food and energy, seasonally adjusted (KXCPICORE)
    "CPI_NSA": "CUUR0000SA0",      # CPI-U, all items, not seasonally adjusted (the year-over-year KXCPIYOY settles on)
    "UNRATE": "LNS14000000",       # the unemployment rate, seasonally adjusted (KXU3)
    "PAYROLLS": "CES0000000001",   # total nonfarm payrolls, thousands, seasonally adjusted (KXPAYROLLS)
    "AHE": "CES0500000003",        # average hourly earnings, total private, dollars
    "PPI": "WPSFD4",               # PPI final demand, seasonally adjusted
}
#: The CFTC contract markets recorded, by the name a strategy uses (codes verified Sept 25, 2026).
COT_MARKETS: dict[str, str] = {
    "BTC": "133741",    # BITCOIN - CHICAGO MERCANTILE EXCHANGE
    "ES": "13874A",     # E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE
    "TY": "043602",     # UST 10Y NOTE - CHICAGO BOARD OF TRADE
    "GOLD": "088691",   # GOLD - COMMODITY EXCHANGE INC.
    "WTI": "067651",    # WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE
    "EUR": "099741",    # EURO FX - CHICAGO MERCANTILE EXCHANGE
}
#: What a DTS row's account_type starts with, by the field the fiscal feed names it.
TGA_ACCOUNTS = {"opening": "Treasury General Account (TGA) Opening Balance",
                "closing": "Treasury General Account (TGA) Closing Balance",
                "deposits": "Total TGA Deposits", "withdrawals": "Total TGA Withdrawals"}
MIN_INTERVAL = 1.0


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() == "null":
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return None if not text or text.lower() == "null" else text


# ------------------------------------------------------------------------------------ BLS
def parse_bls(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """BLS v1's answer as {series id: [{period, value, period_name, latest, preliminary}]}, newest first.
    A failed request (any status but REQUEST_SUCCEEDED, a daily-limit message among them) is a DataError."""
    require(isinstance(payload, Mapping), "bls: not an object")
    if str(payload.get("status")) != "REQUEST_SUCCEEDED":
        messages = payload.get("message")
        detail = "; ".join(str(m) for m in messages) if isinstance(messages, list) and messages else "request failed"
        raise DataError(f"bls: {str(payload.get('status') or '')} {detail}".strip())
    series = (payload.get("Results") or {}).get("series") if isinstance(payload.get("Results"), Mapping) else None
    require(isinstance(series, list), "bls: no Results.series")
    out: dict[str, list[dict[str, Any]]] = {}
    for entry in series:
        if not isinstance(entry, Mapping) or not entry.get("seriesID"):
            continue
        rows = []
        for point in entry.get("data") if isinstance(entry.get("data"), list) else []:
            if not isinstance(point, Mapping):
                continue
            period, value = period_key(point.get("year"), point.get("period")), _float(point.get("value"))
            if period is None or value is None or len(period) != 7:  # months only: M13 is the annual average
                continue
            notes = [str(n.get("code") or "") for n in point.get("footnotes") or [] if isinstance(n, Mapping)]
            rows.append({"period": period, "value": value, "period_name": _text(point.get("periodName")),
                         "latest": str(point.get("latest")).lower() == "true", "preliminary": "P" in notes})
        rows.sort(key=lambda row: row["period"], reverse=True)
        out[str(entry["seriesID"])] = rows
    return out


def bls_summary(series_id: str, rows: Sequence[Mapping[str, Any]], recent: int = 13) -> dict[str, Any]:
    """One series as the bls feed keeps it: the latest, the `recent` newest, the month-over-month and
    year-over-year changes of the latest (percent, None without the month they need)."""
    require(rows, f"bls: no data for {series_id}")
    by_period = {row["period"]: row["value"] for row in rows}
    latest = dict(rows[0])
    year, month = (int(part) for part in latest["period"].split("-"))
    prior = f"{year - 1 if month == 1 else year}-{12 if month == 1 else month - 1:02d}"
    year_ago = f"{year - 1}-{month:02d}"

    def change(then: str) -> float | None:
        base = by_period.get(then)
        return round((latest["value"] / base - 1.0) * 100.0, 4) if base else None

    return {"series_id": series_id, "latest": latest, "change_1m_pct": change(prior), "change_12m_pct": change(year_ago),
            "diff_1m": round(latest["value"] - by_period[prior], 4) if prior in by_period else None,
            "recent": [dict(row) for row in rows[:recent]]}


# ---------------------------------------------------------------------------- FiscalData
def _fiscal_rows(payload: Any, what: str) -> list[Mapping[str, Any]]:
    rows = payload.get("data") if isinstance(payload, Mapping) else None
    require(isinstance(rows, list), f"fiscaldata {what}: no data")
    return [row for row in rows if isinstance(row, Mapping)]


def parse_tga(payload: Any) -> dict[str, Any]:
    """The newest Daily Treasury Statement's cash balance: {record_date, opening, closing, deposits,
    withdrawals} in millions of dollars, and `days`: the closing balance of each day in the answer."""
    rows = _fiscal_rows(payload, "operating cash balance")
    days: dict[str, dict[str, float | None]] = {}
    for row in rows:
        day, account = str(row.get("record_date") or "")[:10], str(row.get("account_type") or "")
        for name, prefix in TGA_ACCOUNTS.items():
            if account.startswith(prefix) and len(day) == 10:
                days.setdefault(day, {})[name] = _float(row.get("open_today_bal"))
    closed = sorted(day for day, fields in days.items() if fields.get("closing") is not None)
    require(closed, "fiscaldata operating cash balance: no TGA closing balance")
    newest = closed[-1]
    return {"record_date": newest, "units": "millions of dollars", **{k: days[newest].get(k) for k in TGA_ACCOUNTS},
            "days": [{"date": day, "closing": days[day]["closing"]} for day in closed[::-1]]}


def parse_debt(payload: Any) -> dict[str, Any]:
    """Debt to the Penny: the newest day's totals (dollars) and the change from the day before."""
    rows = sorted((row for row in _fiscal_rows(payload, "debt to the penny") if _float(row.get("tot_pub_debt_out_amt")) is not None),
                  key=lambda row: str(row.get("record_date")), reverse=True)
    require(rows, "fiscaldata debt to the penny: no total")
    newest = rows[0]
    total = _float(newest.get("tot_pub_debt_out_amt"))
    before = _float(rows[1].get("tot_pub_debt_out_amt")) if len(rows) > 1 else None
    return {"record_date": str(newest.get("record_date"))[:10], "total": total, "held_by_public": _float(newest.get("debt_held_public_amt")),
            "intragovernmental": _float(newest.get("intragov_hold_amt")), "change_1d": round(total - before, 2) if before is not None else None,
            "days": [{"date": str(r.get("record_date"))[:10], "total": _float(r.get("tot_pub_debt_out_amt"))} for r in rows]}


def auction_row(row: Mapping[str, Any]) -> dict[str, Any]:
    offered, accepted = _float(row.get("offering_amt")), _float(row.get("total_accepted"))

    def share(field: str) -> float | None:
        amount = _float(row.get(field))
        return round(amount / accepted * 100.0, 2) if amount is not None and accepted else None

    return {"cusip": _text(row.get("cusip")), "type": _text(row.get("security_type")), "term": _text(row.get("security_term")),
            "reopening": _text(row.get("reopening")) == "Yes", "announced": _text(row.get("announcemt_date")),
            "auction_date": _text(row.get("auction_date")), "issue_date": _text(row.get("issue_date")),
            "closing_time": _text(row.get("closing_time_comp")), "offering_bn": round(offered / 1e9, 3) if offered else None,
            "high_yield": _float(row.get("high_yield")), "high_discount_rate": _float(row.get("high_discnt_rate")),
            "high_investment_rate": _float(row.get("high_investment_rate")), "bid_to_cover": _float(row.get("bid_to_cover_ratio")),
            "accepted_bn": round(accepted / 1e9, 3) if accepted else None, "indirect_pct": share("indirect_bidder_accepted"),
            "direct_pct": share("direct_bidder_accepted"), "dealer_pct": share("primary_dealer_accepted")}


def parse_auctions(payload: Any) -> dict[str, Any]:
    """The Treasury's auctions: `upcoming` (announced, no result yet; soonest first) and `recent`
    (results out; newest first). An auction's result is known once its bid-to-cover is."""
    rows = [auction_row(row) for row in _fiscal_rows(payload, "auctions")]
    rows = [row for row in rows if row["auction_date"]]
    done = [row for row in rows if row["bid_to_cover"] is not None]
    upcoming = [row for row in rows if row["bid_to_cover"] is None]
    return {"upcoming": sorted(upcoming, key=lambda r: (r["auction_date"], r["term"] or "")),
            "recent": sorted(done, key=lambda r: (r["auction_date"], r["term"] or ""), reverse=True)}


# ------------------------------------------------------------------------------------ CFTC
def cot_row(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """One legacy Commitments of Traders report, or None without an as-of date."""
    as_of = str(raw.get("report_date_as_yyyy_mm_dd") or "")[:10]
    if len(as_of) != 10:
        return None
    number = lambda field: _float(raw.get(field))  # noqa: E731
    long_nc, short_nc = number("noncomm_positions_long_all"), number("noncomm_positions_short_all")
    long_c, short_c = number("comm_positions_long_all"), number("comm_positions_short_all")
    return {"as_of": as_of, "code": _text(raw.get("cftc_contract_market_code")), "market": _text(raw.get("market_and_exchange_names")),
            "open_interest": number("open_interest_all"), "change_open_interest": number("change_in_open_interest_all"),
            "noncommercial": {"long": long_nc, "short": short_nc, "spread": number("noncomm_postions_spread_all"),  # sic: the CFTC's field name
                              "net": long_nc - short_nc if long_nc is not None and short_nc is not None else None,
                              "change_long": number("change_in_noncomm_long_all"), "change_short": number("change_in_noncomm_short_all"),
                              "pct_oi_long": number("pct_of_oi_noncomm_long_all"), "pct_oi_short": number("pct_of_oi_noncomm_short_all")},
            "commercial": {"long": long_c, "short": short_c, "net": long_c - short_c if long_c is not None and short_c is not None else None},
            "nonreportable": {"long": number("nonrept_positions_long_all"), "short": number("nonrept_positions_short_all")},
            "traders": number("traders_tot_all")}


def parse_cot(payload: Any) -> list[dict[str, Any]]:
    """Socrata's answer, oldest report first."""
    require(isinstance(payload, list), "cftc cot: not a list")
    rows = [row for row in (cot_row(r) for r in payload if isinstance(r, Mapping)) if row is not None]
    rows.sort(key=lambda row: row["as_of"])
    return rows


# ------------------------------------------------------------------------------ the Fed
def parse_calendar(body: "bytes | str", *, today: str) -> dict[str, list[dict[str, Any]]]:
    """The Board's calendar by kind -- fomc (meetings, minutes, press conferences), speeches, testimony,
    beige -- each from `today` on, soonest first (`ltcm.data.macro.calendar_row` reads an event)."""
    text = body.decode("utf-8-sig") if isinstance(body, bytes) else str(body).lstrip("﻿")
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise DataError("fed calendar: malformed JSON") from exc
    events = payload.get("events") if isinstance(payload, Mapping) else None
    require(isinstance(events, list), "fed calendar: no events")
    kinds = {"fomc": "fomc", "speeches": "speeches", "testimony": "testimony", "beige": "beige"}
    out: dict[str, list[dict[str, Any]]] = {name: [] for name in kinds.values()}
    for event in events:
        row = calendar_row(event)
        if row is None or row["end_date"] < today:
            continue
        kind = kinds.get(str(row.get("type") or "").lower())
        if kind is not None:
            out[kind].append(row)
    for rows in out.values():
        rows.sort(key=lambda row: (row["date"], row["time"] or "", row["title"]))
    return out


class Releases:
    """BLS v1, FiscalData, the CFTC's Socrata reports and the Fed's calendar, asked with the contact User-Agent."""

    def __init__(self, transport: Any = None, *, timeout: float = 30.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def _json(self, url: str, what: str) -> Any:
        return read_json(self.transport, url, headers={"Accept": "application/json", "User-Agent": CONTACT_USER_AGENT},
                         timeout=self.timeout, what=what)

    def bls(self, series_ids: Sequence[str], *, years: int = 2) -> dict[str, list[dict[str, Any]]]:
        """One v1 query (a POST that only reads) for up to 25 series over the last `years` years."""
        ids = [str(s) for s in series_ids][:25]
        require(ids, "bls: no series ids")
        end = datetime.fromtimestamp(float(self.clock()), timezone.utc).year
        body = json.dumps({"seriesid": ids, "startyear": str(end - max(1, int(years)) + 1), "endyear": str(end)}).encode("utf-8")
        status, _, raw = self.transport.request("POST", BLS_V1_URL, headers={"Accept": "application/json", "Content-Type": "application/json",
                                                                             "User-Agent": CONTACT_USER_AGENT}, body=body, timeout=self.timeout)
        if status != 200:
            raise DataError(f"bls: HTTP {status} from {BLS_V1_URL}")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise DataError("bls: malformed JSON") from exc
        return parse_bls(payload)

    def tga(self) -> dict[str, Any]:
        return parse_tga(self._json(f"{DTS_CASH_URL}?sort=-record_date&page[size]=12", "fiscaldata operating cash balance"))

    def debt(self) -> dict[str, Any]:
        return parse_debt(self._json(f"{DEBT_URL}?sort=-record_date&page[size]=5", "fiscaldata debt to the penny"))

    def auctions(self, size: int = 30) -> dict[str, Any]:
        return parse_auctions(self._json(f"{AUCTIONS_URL}?sort=-auction_date&page[size]={int(size)}", "fiscaldata auctions"))

    def cot(self, code: str, *, before: str | None = None, since: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        """The legacy futures-only reports of one contract market as of dates in [since, before), oldest first."""
        clauses = [f"cftc_contract_market_code='{code}'"]
        if since:
            clauses.append(f"report_date_as_yyyy_mm_dd >= '{since}'")
        if before:
            clauses.append(f"report_date_as_yyyy_mm_dd < '{before}'")
        query = urllib.parse.urlencode({"$where": " AND ".join(clauses), "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": int(limit)})
        return parse_cot(self._json(f"{COT_URL}?{query}", f"cftc cot {code}"))

    def calendar(self) -> dict[str, list[dict[str, Any]]]:
        status, _, body = self.transport.get(FED_CALENDAR_URL, {"Accept": "application/json", "User-Agent": CONTACT_USER_AGENT}, self.timeout)
        if status != 200:
            raise DataError(f"fed calendar: HTTP {status} from {FED_CALENDAR_URL}")
        today = datetime.fromtimestamp(float(self.clock()), timezone.utc).date().isoformat()
        return parse_calendar(body, today=today)


__all__ = ["AUCTIONS_URL", "BLS_SERIES", "BLS_V1_URL", "COT_MARKETS", "COT_URL", "DEBT_URL", "DTS_CASH_URL", "FED_CALENDAR_URL",
           "Releases", "auction_row", "bls_summary", "cot_row", "parse_auctions", "parse_bls", "parse_calendar", "parse_cot",
           "parse_debt", "parse_tga"]
