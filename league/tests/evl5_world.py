"""A synthetic week of the event lane for PREREG-EVL-5's tests (league/tests/test_events_evl5.py): invented issuers,
filings, articles, verdicts, minute and daily bars and two registered births, decided the way the House decides them
(the verdicts asked ahead of each decision with the decision's own code, PREREG-EVL-5's pre-pass among them, the live
decisions at their times, late-stored rows, then the hourly re-decisions as backfills). No figure here is a market's.

THE WEEK is release 1019e's week (league/tests/evl4_world.py: every family of PREREG-EVL-1, -2 and -4 on the store, its
ten issuers AAA..JJJ), with two registered births of R3 (a close-entry earnings-reaction birth and an open-entry 8-K
birth) and PREREG-EVL-5's own events beside them (issuers from KKK on):

- the earnings rows of Tue Oct 27 (D; P = Mon Oct 26, P' = Fri Oct 23): KKK falls 5% on a Monday-evening release (DROP;
  its score 1 leaves EVL-ERN-READ-O1 out), NNN falls 6% on a Tuesday release scored 1 with guidance raised (DROP in the
  shadow; real money's guard bars it), LLL is muted (+1%) on a Tuesday release scored 3 raised (UNDER in the shadow, its
  rank 3.5; real money's guard bars it), MMM is muted (0%) on a Monday-evening release scored 2 (UNDER, and
  EVL-ERN-READ-O1's at Tuesday's open), OOO falls 10% but a day-news article scores 3 (TAKEN (b)), PPP rises 5% (TAKEN
  (a): the REACT rows'), RRR falls 4.6% from Friday's close but rose 5% on the day from Monday's (TAKEN (c)), QQQ is
  muted (-2%) with no verdict stored for its release text of 150 characters (the control's, never UNDER's);
- the second nights of Tue Oct 27 (the attention articles of Mon Oct 26): SSS gaps +3% (NIGHT2), TTT +2% exactly (the
  boundary: taken), UUU +1.9% (not), VVV +5% but a two-symbol article names it Tuesday morning ((i)), WWW +5% but an 8-K
  Monday afternoon ((ii)), XXX +5% but a director's $60,000 buy Monday morning ((iii)), YYY +5% and a backfilled article
  naming it edited 30 minutes after publication (excluded from (i): taken), ZZZ +5% and a backfilled article edited 5
  minutes after (counted: skipped), AAB +5% with no trade in its 09:30 minute (not taken), AAC +4% and an article naming
  it at 14:00 ET Tuesday stored only at 16:30 ET (the shadow's re-decision skips it; real money, which reads rows stored
  before its decision, buys it).

`python league/tests/evl5_world.py OUT.json` decides the week with the importable tree's code (the tree to judge first
on PYTHONPATH) and writes every intent and every seatable program's real-money picks, so the same week decided by
release 1019e's own code (which has no PREREG-EVL-5 row) can be compared program by program."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

from league.tests import evl4_world as W4

UTC = dt.timezone.utc
et = W4.et
P_DAY, D_DAY, N_DAY = W4.P_DAY, W4.D_DAY, W4.N_DAY      # Mon Oct 26, Tue Oct 27, Wed Oct 28, 2026
F_DAY = dt.date(2026, 10, 23)                            # P' of Tuesday: Fri Oct 23
NEW = ("KKK", "LLL", "MMM", "NNN", "OOO", "PPP", "QQQ", "RRR", "SSS", "TTT", "UUU", "VVV", "WWW", "XXX", "YYY", "ZZZ",
       "AAB", "AAC", "AAD", "AAE", "AAF", "AAG", "AAH")
TICKERS = W4.TICKERS + NEW
CIK = {t: str(i + 1).zfill(10) for i, t in enumerate(TICKERS)}
#: PROMPT-DOC scores (and guidance) by ticker, PROMPT-NEWS scores by symbol, the T29 minute close by symbol, the 09:30
#: minute's open by symbol (a symbol not here has no trade in that minute), and daily closes that are not 20.
DOC = {**W4.DOC, "KKK": 1, "LLL": 3, "MMM": 2, "NNN": 1, "OOO": 2, "PPP": 1, "RRR": 1}
GUIDE = {"LLL": "raised", "NNN": "raised", "MMM": "maintained"}
NEWS = {**W4.NEWS, "OOO": 3, "RRR": 0}
MINUTE = {**W4.MINUTE, "KKK": 19.0, "LLL": 20.2, "MMM": 20.0, "NNN": 18.8, "OOO": 18.0, "PPP": 21.0, "QQQ": 19.6,
          "RRR": 21.0}
OPENS = {"SSS": 20.6, "TTT": 20.4, "UUU": 20.38, "VVV": 21.0, "WWW": 21.0, "XXX": 21.0, "YYY": 21.0, "ZZZ": 21.0,
         "AAC": 20.8}
CLOSES = {("RRR", F_DAY): 22.0}
DEFAULT_OPEN = 20.0
SEPTEMBER = dt.date(2026, 8, 1)


class Gateway(W4.Gateway):
    """evl4_world's gateway for every ticker here: its calendar, assets (all active and tradable on NASDAQ), daily bars
    (close 20 but for `closes`), T29 minutes (`minute`), the minutes from 09:30 ET of a read of at most five of them
    (the 09:30 minute's open `opens`, else `default_open`; no 09:30 bar for a symbol in `no_open`, whose later minutes
    trade), a closing print, and verdicts by ticker (PROMPT-DOC, with `guide`) or symbol (PROMPT-NEWS); a news verdict
    of a symbol in `refuse` gets no answer (a 503). OUTAGES of those minute reads, a 200 answer all the same:
    `minutes_down` True answers every one with no bar at all; `minutes_partial` symbols are left out of every answer
    of more than one symbol."""

    def __init__(self, *, doc: Mapping[str, int] | None = None, news: Mapping[str, int] | None = None,
                 minute: Mapping[str, float] | None = None, opens: Mapping[str, float] | None = None,
                 closes: Mapping[tuple[str, dt.date], float] | None = None, guide: Mapping[str, str] | None = None):
        super().__init__(doc=DOC if doc is None else doc, news=NEWS if news is None else news,
                         minute=MINUTE if minute is None else minute)
        self.opens = dict(OPENS if opens is None else opens)
        self.closes = dict(CLOSES if closes is None else closes)
        self.guide = dict(GUIDE if guide is None else guide)
        self.no_open = {"AAB"}
        self.default_open = DEFAULT_OPEN
        self.minutes_down = False
        self.minutes_partial: set[str] = set()
        self.refuse: set[str] = set()
        self.inactive: set[str] = set()       # (symbols Alpaca lists as inactive: never eligible)

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        from league.events import store as S

        params = dict(params or {})
        if path.endswith("/v2/assets"):
            self.gets.append((path, params))
            return [{"symbol": t, "status": "inactive" if t in self.inactive else "active", "tradable": True,
                     "class": "us_equity", "exchange": "NASDAQ"} for t in TICKERS]
        if path.endswith("/v2/stocks/bars"):
            symbols = [x for x in str(params["symbols"]).split(",") if x]
            end = S.parse_iso(params["end"])
            minute = params.get("timeframe") == "1Min"
            start = S.parse_iso(params["start"]) if minute else None
            if minute and dt.timedelta(minutes=1) <= end - start <= dt.timedelta(minutes=5):
                self.gets.append((path, params))        # (PREREG-EVL-5's gap minute: the bar starting at `start`)
                if self.minutes_down:
                    return {"bars": {}, "next_page_token": None}
                minutes = [start + dt.timedelta(minutes=k) for k in range(int((end - start).total_seconds() // 60))]
                kept = [s for s in symbols if not (len(symbols) > 1 and s in self.minutes_partial)]
                bars = {s: [{"t": S.iso(t), "o": self.opens.get(s, self.default_open) if t == start else 20.0,
                             "h": 21, "l": 19, "c": 20.0, "v": 100}
                            for t in minutes if not (t == start and s in self.no_open)] for s in kept}
                return {"bars": {s: b for s, b in bars.items() if b}, "next_page_token": None}
            if not minute:
                self.gets.append((path, params))
                first = dt.date.fromisoformat(str(params["start"])[:10])
                last = (end - dt.timedelta(minutes=1)).date()
                return {"bars": {s: [{"t": f"{d}T05:00:00Z", "o": 20, "h": 20, "l": 20,
                                      "c": self.closes.get((s, d), 20.0), "v": 1_000_000}
                                     for d in W4.weekdays(first, last)] for s in symbols}, "next_page_token": None}
        return super().get_json(path, params)

    def post_json(self, path: str, body: Any, headers: Mapping[str, str] | None = None) -> tuple[int, Any]:
        text = body["messages"][0]["content"]
        if text.startswith("Stock: ") and text.split()[1].rstrip(".") in self.refuse:
            self.claude_calls.append(body)
            return 503, {"error": "busy"}
        if not text.startswith("Stock: "):
            ticker = re.search(r"\(ticker (\S+)\)", text).group(1)
            self.claude_calls.append(body)
            answer = {"score": self.doc.get(ticker, 0), "guidance": self.guide.get(ticker, "none"), "reasons": []}
            self.last_headers = {"x-ltcm-cost-usd": "0.001"}
            return 200, {"content": [{"type": "text", "text": json.dumps(answer)}], "stop_reason": "end_turn"}
        return super().post_json(path, body, headers)


def sec(url: str) -> bytes:
    """www.sec.gov: the tickers file and the company feed (every issuer an operating company)."""
    if url.endswith("company_tickers.json"):
        return json.dumps({str(i): {"cik_str": i + 1, "ticker": t, "title": f"{t} Inc."}
                           for i, t in enumerate(TICKERS)}).encode()
    return W4.sec(url)


class World(W4.World):
    """evl4_world's lane store for every ticker here (its calendar and ticker snapshot), with articles of any symbols,
    live or backfilled, and the two births of R3 registered (`births`)."""

    def __init__(self, root: str | Path, gateway: Gateway | None = None):
        from league.events import calendar as C
        from league.events import run as R
        from league.events import store as S

        self.root = Path(root)
        self.st = S.Store(self.root)
        self.gw = gateway or Gateway()
        self.now = et(P_DAY, 7, 0)
        self.ctx = R.Context(self.st, self.gw, sec, now=lambda: self.now)
        C.refresh(self.st, self.gw, SEPTEMBER, dt.date(2026, 12, 31))
        self.st.set_meta("tickers@2026-10-19T01:05:00Z", self.st.put_document(sec("x/company_tickers.json"), "t"))

    def filing(self, accession: str, ticker: str, *, accepted: dt.datetime | None = None,
               knowable: dt.datetime | None = None, items=("8.01",), stored: dt.datetime | None = None,
               text_len: int = 5000, form: str = "8-K") -> None:
        from league.events import store as S

        if knowable is None:
            knowable = accepted + dt.timedelta(minutes=10)
        if accepted is None:
            accepted = knowable - dt.timedelta(minutes=10)
        when = stored or knowable
        text = (f"{accession}: the company announced its results for the quarter. " * 20).encode()
        sha = self.st.put_document(text, "text", now=when)
        self.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, "
                           "received_at, source, text_sha, text_len, raw_sha, status) VALUES(?, ?, ?, ?, ?, ?, ?, ?, "
                           "'current', ?, ?, ?, 'fetched')",
                           (accession, form, CIK[ticker], f"{ticker} Inc.", json.dumps(list(items)), S.iso(accepted),
                            S.iso(knowable), S.iso(when), sha, text_len, sha))

    def article(self, ident: str, symbol: str, *, knowable: dt.datetime, stored: dt.datetime | None = None,
                symbols: list[str] | None = None, live: bool = True, edited: dt.timedelta | None = None) -> None:
        """An ENEWS article knowable at `knowable` (created 2 minutes before), stored at `stored` (by default when
        knowable), with `symbols` (by default just `symbol`); `live` False: backfilled, its `updated_at` `edited` after
        its `created_at` (by default the same)."""
        from league.events import store as S

        created = knowable - dt.timedelta(minutes=2)
        updated = created + (edited or dt.timedelta(0))
        self.st.db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, headline, "
                           "summary, symbols, live) VALUES(?, ?, ?, ?, ?, 'invented', 'h', 's', ?, ?)",
                           (ident, S.iso(created), S.iso(updated), S.iso(stored or knowable), S.iso(knowable),
                            json.dumps(symbols or [symbol]), int(live)))

    def insider_buy(self, accession: str, ticker: str, *, accepted: dt.datetime, usd: float) -> None:
        from zoneinfo import ZoneInfo

        self.filing(accession, ticker, accepted=accepted, items=(), form="4")
        self.st.db.execute("INSERT INTO form4_owners(accession, owner_cik, owner_name, is_director, is_officer, "
                           "officer_title, is_ten_pct) VALUES(?, '9', 'Invented Owner', 1, 0, NULL, 0)", (accession,))
        day = accepted.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        self.st.db.execute("INSERT INTO form4_tx(accession, seq, security, tx_date, code, shares, price, acquired, "
                           "owned_after) VALUES(?, 1, 'Common', ?, 'P', ?, 10.0, 'A', 1)", (accession, day, usd / 10.0))

    def births(self) -> None:
        """Two registered births of R3, before the week (Oct 22, 02:00Z): a seatable close-entry earnings-reaction birth
        (a fall to 0.97 or less with a PROMPT-DOC score >= 1, ranked by the reaction, out at the next open) and a
        seatable open-entry 8-K birth (items 5.02 or 1.02). Loaded with `programs.load_births`."""
        from league.events import births as BI
        from league.events import programs as P

        at = "2026-10-22T02:00:00Z"
        specs = [{"id": "EVL-B-ERNREACT-DIP", "version": 1, "family": "ern-react",
                  "rule": {"react_max": 0.97, "score_min": 1}, "entry": BI.ENTRY["ern-react"], "exit": "open", "hold": 1,
                  "rank": "reaction", "seatable": True},
                 {"id": "EVL-B-8K-502", "version": 1, "family": "8k", "rule": {"items": ["5.02", "1.02"]},
                  "entry": BI.ENTRY["8k"], "exit": "close", "hold": 1, "rank": "none", "seatable": True}]
        for seq, sp in enumerate(specs):
            text = BI.canonical(sp)
            line = json.dumps({"spec": json.loads(text), "sha": BI.sha(sp)}, sort_keys=True, separators=(",", ":"))
            self.st.db.execute("INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, "
                               "received_at, path, commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, "
                               "?, ?, ?, ?, 'invented', 'captain', '2026-10-21')",
                               (sp["id"], BI.sha(sp), text, at, at, at, "docs/births/2026-10-21.jsonl", "c" * 40, seq,
                                line))
        P.load_births(self.st)


def evl4_rows(w: World) -> None:
    """Release 1019e's week (league/tests/evl4_world.py `the_week`): its rows alone (its decisions are `decide_week`)."""
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
    w.filing("0000000008-26-000003", "HHH", accepted=et(P_DAY, 11, 0), items=("5.02",))   # (the 8-K birth's event)


def evl5_rows(w: World) -> None:
    """PREREG-EVL-5's events of the week (the module docstring), stored before Tuesday's close decision but AAC's
    Tuesday article (stored at 16:30 ET)."""
    w.filing("0000000011-26-000001", "KKK", accepted=et(P_DAY, 16, 20), items=("2.02", "9.01"))
    w.filing("0000000014-26-000001", "NNN", accepted=et(D_DAY, 11, 0), items=("2.02",))
    w.filing("0000000012-26-000001", "LLL", accepted=et(D_DAY, 10, 0), items=("2.02", "7.01"))
    w.filing("0000000013-26-000001", "MMM", accepted=et(P_DAY, 17, 0), items=("2.02",))
    w.filing("0000000015-26-000001", "OOO", accepted=et(D_DAY, 12, 0), items=("2.02",))
    w.article("n-ooo-1", "OOO", knowable=et(D_DAY, 11, 30))
    w.filing("0000000016-26-000001", "PPP", accepted=et(P_DAY, 16, 45), items=("2.02",))
    w.filing("0000000018-26-000001", "RRR", accepted=et(P_DAY, 15, 50), items=("2.02",))
    w.article("n-rrr-1", "RRR", knowable=et(D_DAY, 10, 0))
    w.filing("0000000017-26-000001", "QQQ", accepted=et(D_DAY, 9, 30), items=("2.02",), text_len=150)
    # the attention articles of Monday (P) for Tuesday (D): knowable after Friday's close and by Monday's T29
    w.article("n-sss-1", "SSS", knowable=et(dt.date(2026, 10, 24), 10, 0))      # a Saturday article
    w.article("n-sss-2", "SSS", knowable=et(P_DAY, 9, 0))                         # the same issuer again (not its event)
    w.article("n-ttt-1", "TTT", knowable=et(P_DAY, 10, 0))
    w.article("n-uuu-1", "UUU", knowable=et(P_DAY, 11, 0))
    w.article("n-vvv-1", "VVV", knowable=et(P_DAY, 12, 0))
    w.article("n-vvv-2", "VVV", knowable=et(D_DAY, 8, 0), symbols=["VVV", "JJJ"])        # (i): any number of symbols
    w.article("n-www-1", "WWW", knowable=et(P_DAY, 13, 0))
    w.filing("0000000021-26-000001", "WWW", accepted=et(P_DAY, 14, 0), items=("5.07",))  # (ii): any items
    w.article("n-xxx-1", "XXX", knowable=et(P_DAY, 14, 0))
    w.insider_buy("0000000022-26-000001", "XXX", accepted=et(P_DAY, 10, 0), usd=60_000.0)  # (iii)
    w.article("n-yyy-1", "YYY", knowable=et(P_DAY, 9, 30))
    w.article("n-yyy-2", "YYY", knowable=et(D_DAY, 10, 0), live=False, edited=dt.timedelta(minutes=30))   # excluded
    w.article("n-zzz-1", "ZZZ", knowable=et(P_DAY, 9, 45))
    w.article("n-zzz-2", "ZZZ", knowable=et(D_DAY, 10, 0), live=False, edited=dt.timedelta(minutes=5))    # counted
    w.article("n-aab-1", "AAB", knowable=et(P_DAY, 10, 15))
    w.article("n-aac-1", "AAC", knowable=et(P_DAY, 10, 20))


def decide_week(w: World, *, late: bool = True) -> None:
    """The House's decisions of the week (as evl4_world's `the_week`): Monday's close, then for Tuesday and Wednesday
    the verdicts asked from 07:30 ET and at 12:30 and 15:17 ET (PREREG-EVL-5's pre-pass among them), the live open and
    close decisions, Tuesday's late-stored rows (HHH's earnings 8-K and AAC's article) and the re-decisions as
    backfills."""
    w.at(et(P_DAY, 15, 47)).decide("close", P_DAY)
    for day in (D_DAY, N_DAY):
        w.at(et(day, 7, 31)).decide("open", day, ask_only=True)
        w.at(et(day, 7, 32)).decide("close", day, ask_only=True)
        w.at(et(day, 9, 15, 30)).decide("open", day)
        w.at(et(day, 12, 30)).decide("close", day, ask_only=True)
        w.at(et(day, 15, 17)).decide("close", day, ask_only=True)
        w.at(et(day, 15, 47)).decide("close", day)
        if day == D_DAY and late:
            w.filing("0000000008-26-000002", "HHH", accepted=et(D_DAY, 14, 0), items=("2.02",), stored=et(D_DAY, 16, 30))
            w.article("n-aac-2", "AAC", knowable=et(D_DAY, 14, 0), stored=et(D_DAY, 16, 30))
            w.at(et(D_DAY, 16, 40)).decide("open", D_DAY, live=False)
            w.at(et(D_DAY, 16, 41)).decide("close", D_DAY, live=False)
    w.at(et(N_DAY, 16, 40)).decide("open", D_DAY, live=False)
    w.at(et(N_DAY, 16, 41)).decide("close", D_DAY, live=False)
    w.at(et(N_DAY, 16, 42)).decide("open", N_DAY, live=False)
    w.at(et(N_DAY, 16, 43)).decide("close", N_DAY, live=False)


def the_week(w: World, *, births: bool = True) -> None:
    if births:
        w.births()
    evl4_rows(w)
    evl5_rows(w)
    decide_week(w)


def ratio(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float | None:
    """A reaction as the book reads it: the T29 minute close over the last daily close before the event (20 but for
    `CLOSES`), None with no minute bar."""
    from league.events import calendar as C
    from league.events import store as S

    close = MINUTE.get(str(uni["symbol"]))
    if close is None:
        return None
    since = row.get("accepted_at") if row.get("accession") else row.get("knowable_at")
    moment = S.parse_iso(str(since)).astimezone(C.NY)
    day = moment.date() if moment.time() >= dt.time(16, 0) else moment.date() - dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return close / CLOSES.get((str(uni["symbol"]), day), 20.0)


def opening(symbol: str, session: Any) -> float | None:
    """The 09:30 minute's open as the book would read it itself (none for AAB)."""
    return None if symbol == "AAB" else OPENS.get(symbol, DEFAULT_OPEN)


def picks(world: World, programs: Callable[[Any], bool]) -> dict[str, list[tuple]]:
    """The real-money picks of each seatable program `programs` keeps, at Tuesday's and Wednesday's auctions, on the
    lane's store read-only (`book.picks`, the book's reaction and gap readers on invented prices)."""
    from league.events import book as EB
    from league.events import calendar as C
    from league.events import store as S

    out: dict[str, list[tuple]] = {}
    lane = EB.Lane(world.root / S.DB_NAME)
    try:
        for day in (D_DAY, N_DAY):
            session = C.session(lane, day)
            # (the book's own readers: the lane's marks first, the invented prices for a name it holds none of; release
            # 1019e's book has no gap reader, so the same week can be decided by it)
            reaction = EB.reaction_reader(lane, day, daily=lambda symbol, d: CLOSES.get((symbol, d), 20.0),
                                          minutes=lambda symbol, session: MINUTE.get(symbol))
            kw = {"gap": EB.gap_reader(lane, day, opens=opening)} if hasattr(EB, "gap_reader") else {}
            for p in EB.seatable():
                if not programs(p):
                    continue
                moment = session.open_decide if p.entry_at == "open" else session.close_decide
                got = EB.picks(lane, p, day, decided_at=moment, reaction=reaction, **kw)
                out[f"{p.id}@v{p.version}@{day.isoformat()}"] = [(x.event, x.symbol, x.cik, x.rank, x.adv20,
                                                                  str(x.prev_close)) for x in got]
    finally:
        lane.close()
    return out


def run(root: str | Path) -> dict[str, Any]:
    """The week decided by the importable tree's code: every intent and every seatable program's real-money picks."""
    world = World(root)
    try:
        the_week(world)
        return {"intents": [list(r) for r in world.intents()], "picks": picks(world, lambda p: True)}
    finally:
        world.close()


if __name__ == "__main__":   # python league/tests/evl5_world.py OUT.json (with the tree to judge first on PYTHONPATH)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        Path(sys.argv[1]).write_text(json.dumps(run(Path(tmp) / "lane"), sort_keys=True, indent=1, default=str))
