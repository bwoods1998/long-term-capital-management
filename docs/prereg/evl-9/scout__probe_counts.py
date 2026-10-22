"""probe_counts.py -- COUNT-ONLY probes of the Alpaca history the scout could not count without the gateway.

NOT RUN BY THE SCOUT (the scout may not touch the gateway). For the captain, on blake-desktop, outside 12:55-20:05Z and
away from the House's decision reads (league/events/house.py: 09:15 ET open, close - 14 min, 16:20 ET bars; 22:30Z
equity_data; 01:40Z/01:55Z panel jobs). Every response is reduced to COUNTS in memory: no price, volume, headline,
summary or return is written, printed or kept. About 60-200 market-data requests in all (well under one minute of the
Basic plan's 200/min).

  P1 news: article ids a day on 11 sampled days (the first Wednesday of March, 2016..2026): total, with >= 1 symbol,
     exactly one symbol, updated_at - created_at > 10 min (the backfill exclusion), distinct `source` values.
  P2 bars: of the symbols in a file (one per line, `SYMBOL,ASOF`; e.g. the 2016 Form 4 symbols of issuers absent from
     today's company_tickers.json, count_survivorship.py), how many return >= 1 SIP 1Day bar in the 5 sessions after
     ASOF with asof=ASOF (the delisted coverage), in requests of 200 symbols grouped by ASOF.
  P3 limits: the X-RateLimit-Limit header of one data GET on the real keys (/v1/alpaca) and on the paper keys
     (/v1/alpaca-paper): whether a history fetch on the paper keys has its own minute budget.
  P4 assets: us_equity assets by status (active / inactive) and exchange (counts).

Usage: python3 probe_counts.py [--symbols FILE] > probe_counts.out.json
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "Work" / "long-term-capital-management"))
from league.events.gw import Gateway, token_from_env  # noqa: E402

DAYS = [dt.date(y, 3, 1) + dt.timedelta(days=(2 - dt.date(y, 3, 1).weekday()) % 7) for y in range(2016, 2027)]


def p1_news(gw: Gateway) -> dict:
    out = {}
    for day in DAYS:
        start = dt.datetime.combine(day, dt.time(0), tzinfo=dt.timezone.utc)
        token, c = None, collections.Counter()
        sources = set()
        for _ in range(400):
            page = gw.get_json("/v1/alpaca/v1beta1/news", {"start": start.isoformat().replace("+00:00", "Z"),
                                                            "end": (start + dt.timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                                                            "limit": 50, "sort": "asc", "include_content": "false",
                                                            "page_token": token})
            for a in (page or {}).get("news") or []:
                c["articles"] += 1
                n = len(a.get("symbols") or [])
                c["with_symbol"] += n >= 1
                c["one_symbol"] += n == 1
                try:
                    cr = dt.datetime.fromisoformat(str(a["created_at"]).replace("Z", "+00:00"))
                    up = dt.datetime.fromisoformat(str(a.get("updated_at") or a["created_at"]).replace("Z", "+00:00"))
                    c["edited_after_10min"] += (up - cr) > dt.timedelta(minutes=10)
                except (KeyError, ValueError):
                    c["bad_time"] += 1
                sources.add(str(a.get("source")))
            c["pages"] += 1
            token = (page or {}).get("next_page_token")
            if not token:
                break
        out[day.isoformat()] = dict(c, distinct_sources=len(sources))
    return out


def p2_bars(gw: Gateway, path: str) -> dict:
    groups = collections.defaultdict(list)
    for line in Path(path).read_text().split():
        sym, asof = line.split(",")
        groups[asof].append(sym.upper())
    asked = served = 0
    for asof, syms in groups.items():
        d = dt.date.fromisoformat(asof)
        for i in range(0, len(syms), 200):
            chunk = syms[i:i + 200]
            page = gw.get_json("/v1/alpaca/v2/stocks/bars", {"symbols": ",".join(chunk), "timeframe": "1Day",
                                                              "start": d.isoformat(), "end": (d + dt.timedelta(days=8)).isoformat(),
                                                              "feed": "sip", "adjustment": "raw", "asof": asof, "limit": 10000})
            got = {s for s, rows in ((page or {}).get("bars") or {}).items() if rows}
            asked += len(chunk)
            served += len(got & set(chunk))
    return {"symbols_asked": asked, "symbols_with_bars": served}


def p3_limits(gw: Gateway) -> dict:
    out = {}
    for venue in ("alpaca", "alpaca-paper"):
        try:
            gw.get_json(f"/v1/{venue}/v2/stocks/bars", {"symbols": "SPY", "timeframe": "1Day", "start": "2016-01-04",
                                                        "end": "2016-01-05", "feed": "sip", "limit": 1})
            out[venue] = {k: v for k, v in gw.last_headers.items() if k.startswith("x-ratelimit")}
        except Exception as exc:  # noqa: BLE001
            out[venue] = {"error": str(exc)[:120]}
    return out


def p4_assets(gw: Gateway) -> dict:
    rows = gw.get_json("/v1/alpaca/v2/assets", {"asset_class": "us_equity"}) or []
    c = collections.Counter((str(a.get("status")), str(a.get("exchange"))) for a in rows)
    return {f"{s}:{x}": n for (s, x), n in sorted(c.items())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols")
    args = ap.parse_args()
    gw = Gateway(token_from_env(), min_interval=0.6)
    out = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "P1_news": p1_news(gw), "P3_limits": p3_limits(gw),
           "P4_assets": p4_assets(gw)}
    if args.symbols:
        out["P2_bars"] = p2_bars(gw, args.symbols)
    json.dump(out, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
