"""A synthetic week of the event lane for PREREG-EVL-4's tests (league/tests/test_events_evl4.py): invented issuers,
filings, articles, verdicts, minute and daily bars, decided the way the House decides them (the verdicts asked ahead
of each decision with the decision's own code, the live decisions at their times, a late-stored filing, then the
hourly re-decisions as backfills). No figure here is a market's.

It uses only what league/events offered before PREREG-EVL-4 (`run.decide_open` / `decide_close`, `book.picks`), so the
same world can be decided by the code of release 1019b and by this tree, and every PREREG-EVL-1/2/3 program's intents
and real-money picks compared (`python league/tests/evl4_world.py OUT.json`, with the tree to judge first on
PYTHONPATH)."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

UTC = dt.timezone.utc
TICKERS = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ")
CIK = {t: str(i + 1).zfill(10) for i, t in enumerate(TICKERS)}
#: PROMPT-DOC scores by ticker, PROMPT-NEWS scores by symbol, the T29 minute close by symbol (every daily close is 20).
DOC = {"AAA": 3, "BBB": 2, "CCC": 2, "DDD": 3, "FFF": 1, "HHH": 2, "III": 3, "JJJ": 2}
NEWS = {"DDD": 2, "EEE": 3, "FFF": 2, "GGG": 1, "JJJ": 3}
MINUTE = {"AAA": 21.0, "BBB": 20.5, "CCC": 21.0, "DDD": 20.9, "FFF": 20.5, "HHH": 21.0, "III": 20.8, "JJJ": 21.2}
P_DAY, D_DAY, N_DAY = dt.date(2026, 10, 26), dt.date(2026, 10, 27), dt.date(2026, 10, 28)


def weekdays(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def et(day: dt.date, hh: int, mm: int = 0, ss: int = 0) -> dt.datetime:
    from zoneinfo import ZoneInfo

    return dt.datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)


class Gateway:
    """Alpaca data and Claude through an invented gateway: the calendar, every symbol active and tradable on NASDAQ
    (the live and backfill rules agree), 1Day bars (close 20, volume 1,000,000), 1Min bars (one bar ending at the
    request's end, close `minute[symbol]`, many symbols a request), a closing print on NASDAQ, and verdicts by ticker
    (PROMPT-DOC) or symbol (PROMPT-NEWS)."""

    def __init__(self, doc: Mapping[str, int] | None = None, news: Mapping[str, int] | None = None,
                 minute: Mapping[str, float] | None = None):
        self.doc = dict(DOC if doc is None else doc)
        self.news = dict(NEWS if news is None else news)
        self.minute = dict(MINUTE if minute is None else minute)
        self.claude_calls: list[dict[str, Any]] = []
        self.gets: list[tuple[str, dict[str, Any]]] = []
        self.last_headers: dict[str, str] = {}

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        from league.events import store as S

        params = dict(params or {})
        self.gets.append((path, params))
        if path.endswith("/v2/calendar"):
            s, e = dt.date.fromisoformat(params["start"]), dt.date.fromisoformat(params["end"])
            return [{"date": d.isoformat(), "open": "09:30", "close": "16:00"} for d in weekdays(s, e)]
        if path.endswith("/v2/assets"):
            return [{"symbol": t, "status": "active", "tradable": True, "class": "us_equity", "exchange": "NASDAQ"}
                    for t in TICKERS]
        if path.endswith("/v2/stocks/bars"):
            symbols = [x for x in str(params["symbols"]).split(",") if x]
            end = S.parse_iso(params["end"])
            if params.get("timeframe") == "1Min":
                bar_t = S.iso(end - dt.timedelta(minutes=1))
                return {"bars": {s: [{"t": bar_t, "o": 20, "h": 21, "l": 19, "c": self.minute[s], "v": 100}]
                                 for s in symbols if s in self.minute}, "next_page_token": None}
            start = dt.date.fromisoformat(str(params["start"])[:10])
            last = (end - dt.timedelta(minutes=1)).date()
            return {"bars": {s: [{"t": f"{d}T05:00:00Z", "o": 20, "h": 20, "l": 20, "c": 20.0, "v": 1_000_000}
                                 for d in weekdays(start, last)] for s in symbols}, "next_page_token": None}
        if path.endswith("/trades"):
            close = S.parse_iso(params["start"]) + dt.timedelta(seconds=5)
            return {"trades": [{"t": S.iso(close), "x": "Q", "c": ["@", "6"], "p": 20.0, "s": 100}],
                    "next_page_token": None}
        if path.endswith("/v1beta1/news"):
            return {"news": [], "next_page_token": None}
        raise AssertionError(path)

    def post_json(self, path: str, body: Any, headers: Mapping[str, str] | None = None) -> tuple[int, Any]:
        self.claude_calls.append(body)
        text = body["messages"][0]["content"]
        if text.startswith("Stock: "):
            answer = {"score": self.news.get(text.split()[1].rstrip("."), 0), "reasons": []}
        else:
            ticker = re.search(r"\(ticker (\S+)\)", text).group(1)
            answer = {"score": self.doc.get(ticker, 0), "guidance": "raised", "reasons": []}
        self.last_headers = {"x-ltcm-cost-usd": "0.001"}
        return 200, {"content": [{"type": "text", "text": json.dumps(answer)}], "stop_reason": "end_turn"}

    def asked(self) -> list[str]:
        """The events asked of Claude, in order: `doc:<ticker>` or `news:<symbol>`."""
        out = []
        for body in self.claude_calls:
            text = body["messages"][0]["content"]
            if text.startswith("Stock: "):
                out.append("news:" + text.split()[1].rstrip("."))
            else:
                out.append("doc:" + re.search(r"\(ticker (\S+)\)", text).group(1))
        return out


def sec(url: str) -> bytes:
    """www.sec.gov: the tickers file and the company feed (every issuer an operating company)."""
    if url.endswith("company_tickers.json"):
        return json.dumps({str(i): {"cik_str": i + 1, "ticker": t, "title": f"{t} Inc."}
                           for i, t in enumerate(TICKERS)}).encode()
    if "action=getcompany" in url:
        return (b"<feed><company-info><assigned-sic>3571</assigned-sic></company-info><entry><filing-type>10-Q"
                b"</filing-type><filing-date>2026-08-01</filing-date></entry></feed>")
    raise AssertionError(url)


class World:
    """One lane store (`root`) with the calendar and a ticker snapshot, and the means to add invented rows."""

    def __init__(self, root: str | Path, gateway: Gateway | None = None):
        from league.events import calendar as C
        from league.events import run as R
        from league.events import store as S

        self.root = Path(root)
        self.st = S.Store(self.root)
        self.gw = gateway or Gateway()
        self.now = et(P_DAY, 7, 0)
        self.ctx = R.Context(self.st, self.gw, sec, now=lambda: self.now)
        C.refresh(self.st, self.gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
        self.st.set_meta("tickers@2026-10-19T01:05:00Z", self.st.put_document(sec("x/company_tickers.json"), "t"))

    def close(self) -> None:
        self.st.close()

    # -- rows -------------------------------------------------------------------------------------------------------
    def filing(self, accession: str, ticker: str, *, accepted: dt.datetime | None = None,
               knowable: dt.datetime | None = None, items=("8.01",), stored: dt.datetime | None = None,
               text_len: int = 5000, form: str = "8-K") -> None:
        """A fetched filing: knowable at acceptance + 10 minutes, its text a document of its own stored when the filing
        was (`stored`, by default its knowable time)."""
        from league.events import store as S

        if knowable is None:
            knowable = accepted + dt.timedelta(minutes=10)
        if accepted is None:
            accepted = knowable - dt.timedelta(minutes=10)
        when = stored or knowable
        text = (f"{accession}: the company announced a material definitive agreement. " * 20).encode()
        sha = self.st.put_document(text, "text", now=when)
        self.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, "
                           "received_at, source, text_sha, text_len, raw_sha, status) VALUES(?, ?, ?, ?, ?, ?, ?, ?, "
                           "'current', ?, ?, ?, 'fetched')",
                           (accession, form, CIK[ticker], f"{ticker} Inc.", json.dumps(list(items)), S.iso(accepted),
                            S.iso(knowable), S.iso(when), sha, text_len, sha))

    def article(self, ident: str, symbol: str, *, knowable: dt.datetime, stored: dt.datetime | None = None,
                symbols: list[str] | None = None) -> None:
        from league.events import store as S

        created = knowable - dt.timedelta(minutes=2)
        self.st.db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, headline, "
                           "summary, symbols, live) VALUES(?, ?, ?, ?, ?, 'invented', 'h', 's', ?, 1)",
                           (ident, S.iso(created), S.iso(created), S.iso(stored or knowable), S.iso(knowable),
                            json.dumps(symbols or [symbol])))

    def insider_buy(self, accession: str, ticker: str, *, accepted: dt.datetime, usd: float) -> None:
        from zoneinfo import ZoneInfo

        self.filing(accession, ticker, accepted=accepted, items=(), form="4")
        self.st.db.execute("INSERT INTO form4_owners(accession, owner_cik, owner_name, is_director, is_officer, "
                           "officer_title, is_ten_pct) VALUES(?, '9', 'Invented Owner', 1, 0, NULL, 0)", (accession,))
        day = accepted.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        self.st.db.execute("INSERT INTO form4_tx(accession, seq, security, tx_date, code, shares, price, acquired, "
                           "owned_after) VALUES(?, 1, 'Common', ?, 'P', ?, 10.0, 'A', 1)", (accession, day, usd / 10.0))

    # -- decisions --------------------------------------------------------------------------------------------------
    def at(self, moment: dt.datetime) -> "World":
        self.now = moment
        return self

    def decide(self, kind: str, day: dt.date, *, live: bool = True, ask_only: bool = False) -> dict[str, Any]:
        from league.events import run as R

        fn = R.decide_open if kind == "open" else R.decide_close
        return fn(self.ctx, day, backfill_run=not live, ask_only=ask_only)

    def intents(self, keep: Callable[[str, int], bool] = lambda program, version: True) -> list[tuple]:
        rows = self.st.db.execute("SELECT program, version, event, symbol, cik, decided_at, entry_day, entry_at, exit_day, "
                                  "exit_at, rank_key, mode, status, why FROM intents ORDER BY program, version, event")
        return [tuple(r) for r in rows if keep(str(r["program"]), int(r["version"]))]


def the_week(world: World) -> None:
    """THE SCENARIO: Mon Oct 26 (P), Tue Oct 27 (D), Wed Oct 28; every family of PREREG-EVL-1, -2 and -4 on the store,
    decided the way the House decides (verdicts asked from 07:30 ET with the decisions' own code, the live decisions at
    09:15 ET and the close - 13 minutes, a late-stored filing, the hourly re-decisions as backfills).

    - AAA: an earnings 8-K (2.02, 7.01) Mon 16:30 ET (Tue's open; Tue's close: C1, REACT-ON, REACT-READ-C1) and an 8.01
      8-K Tue 11:00 ET (Wed's open; EXCLUDED on Tue by ERN(Tue) for PREREG-EVL-4).
    - BBB: an 8.01 8-K Mon 18:00 ET (EVL-8K-READ-O1 at Tue's open; F8K(Tue) for PREREG-EVL-4, before 09:00 ET).
    - CCC: a 1.01 8-K Tue 11:00 ET (F8K(Tue): EVL-8K-REACT-ON, EVL-8K-READ-ON; EVL-8K-READ-O1 at Wed's open).
    - DDD: day news Tue 10:30 ET (NEWS-READ-ON, NEWS-REACT-ON, their control) and an 8.01 8-K Tue 12:00 ET (EXCLUDED on
      Tue by DAY(Tue)).
    - EEE: pre-market news Tue 07:00 ET (EVL-NEWS-READ-O1 at Tue's open; EVL-NEWSPM-READ-ON at Tue's close).
    - FFF: pre-market news Tue 08:00 ET and an 8.01 8-K Tue 13:00 ET (EVL-NEWSPM-READ-ON skips FFF: F8K(Tue)).
    - GGG: a director's $60,000 open-market buy Mon 17:00 ET (EVL-INS-BUY-O1 at Tue's open), and a pre-market article
      with two symbols (no program's).
    - HHH: an 8.01 8-K Tue 10:00 ET (F8K(Tue)) and an earnings 8-K Tue 14:00 ET STORED LATE, Tue 16:30 ET, after Tue's
      close decision (the re-decision: C1 and REACT-ON take it; PREREG-EVL-4's HHH intents become skipped:excluded).
    - III: an 8.01 8-K Wed 08:00 ET (Wed's open; F8K(Wed)). JJJ: pre-market news Wed 08:30 ET (Wed's open and close).
    """
    w = world
    w.filing("0000000001-26-000001", "AAA", accepted=et(P_DAY, 16, 30), items=("2.02", "7.01"))
    w.filing("0000000001-26-000002", "AAA", accepted=et(D_DAY, 11, 0), items=("8.01",))
    w.filing("0000000002-26-000001", "BBB", accepted=et(P_DAY, 18, 0), items=("8.01",))
    w.filing("0000000003-26-000001", "CCC", accepted=et(D_DAY, 11, 0), items=("1.01", "9.01"))
    w.article("n-ddd-1", "DDD", knowable=et(D_DAY, 10, 30))
    w.filing("0000000004-26-000001", "DDD", accepted=et(D_DAY, 12, 0), items=("8.01",))
    w.article("n-eee-1", "EEE", knowable=et(D_DAY, 7, 0))
    w.article("n-fff-1", "FFF", knowable=et(D_DAY, 8, 0))
    w.filing("0000000006-26-000001", "FFF", accepted=et(D_DAY, 13, 0), items=("8.01",))
    w.insider_buy("0000000007-26-000001", "GGG", accepted=et(P_DAY, 17, 0), usd=60_000.0)
    w.article("n-ggg-1", "GGG", knowable=et(D_DAY, 7, 30), symbols=["GGG", "AAA"])
    w.filing("0000000008-26-000001", "HHH", accepted=et(D_DAY, 10, 0), items=("8.01",))
    w.filing("0000000009-26-000001", "III", accepted=et(N_DAY, 8, 0), items=("8.01",))
    w.article("n-jjj-1", "JJJ", knowable=et(N_DAY, 8, 30))

    w.at(et(P_DAY, 15, 47)).decide("close", P_DAY)
    for day in (D_DAY, N_DAY):
        w.at(et(day, 7, 31)).decide("open", day, ask_only=True)
        w.at(et(day, 7, 32)).decide("close", day, ask_only=True)
        w.at(et(day, 9, 15, 30)).decide("open", day)
        w.at(et(day, 12, 30)).decide("close", day, ask_only=True)
        w.at(et(day, 15, 17)).decide("close", day, ask_only=True)
        w.at(et(day, 15, 47)).decide("close", day)
        if day == D_DAY:
            w.filing("0000000008-26-000002", "HHH", accepted=et(D_DAY, 14, 0), items=("2.02",), stored=et(D_DAY, 16, 30))
            w.at(et(D_DAY, 16, 40)).decide("open", D_DAY, live=False)
            w.at(et(D_DAY, 16, 41)).decide("close", D_DAY, live=False)
    w.at(et(N_DAY, 16, 40)).decide("open", D_DAY, live=False)
    w.at(et(N_DAY, 16, 41)).decide("close", D_DAY, live=False)
    w.at(et(N_DAY, 16, 42)).decide("open", N_DAY, live=False)
    w.at(et(N_DAY, 16, 43)).decide("close", N_DAY, live=False)


def _ratio(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float | None:
    """A REACT row's ratio as the book reads it: the T29 minute close over the daily close of 20 (None with no bar)."""
    close = MINUTE.get(str(uni["symbol"]))
    return None if close is None else close / 20.0


def nine_picks(world: World) -> dict[str, list[tuple]]:
    """The real-money picks of each version 2 program (PREREG-EVL-3's nine) at Tue's and Wed's auctions, on the lane's
    store read-only (`book.picks`; the REACT rows' ratio is the T29 minute close over the daily close of 20)."""
    from league.events import book as EB
    from league.events import calendar as C
    from league.events import programs as P
    from league.events import store as S

    out: dict[str, list[tuple]] = {}
    lane = EB.Lane(world.root / S.DB_NAME)
    try:
        for day in (D_DAY, N_DAY):
            session = C.session(lane, day)
            for p in P.PROGRAMS:
                if p.version != 2 or p.prereg != 3:
                    continue
                moment = session.open_decide if p.entry_at == "open" else session.close_decide
                got = EB.picks(lane, p, day, decided_at=moment, reaction=_ratio)
                out[f"{p.id}@{day.isoformat()}"] = [(x.event, x.symbol, x.cik, x.rank, x.adv20, str(x.prev_close))
                                                    for x in got]
    finally:
        lane.close()
    return out


def run(root: str | Path) -> dict[str, Any]:
    """The week decided by the importable tree's code: every intent and the nine's real-money picks."""
    world = World(root)
    try:
        the_week(world)
        return {"intents": [list(r) for r in world.intents()], "picks": nine_picks(world)}
    finally:
        world.close()


if __name__ == "__main__":   # python league/tests/evl4_world.py OUT.json (with the tree to judge first on PYTHONPATH)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        Path(sys.argv[1]).write_text(json.dumps(run(Path(tmp) / "lane"), sort_keys=True, indent=1, default=str))
