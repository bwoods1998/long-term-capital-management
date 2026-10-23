"""RELEASE 1019m-HOTFIX: THE CLOSE DECISION'S 15:30 MARKS READ IN BATCHES, so close entries are sent before 15:49 ET
(the captain's A140). On INVENTED rows only: every name, filing, article, bar and price here is made up; no market's
figure is read and no House or desktop store is opened. Each test fails without its fix:

- THE LANE (league/events/run.py `decide_close`, `_react_marks`, `_marks_1530(since=)`): the earlier rows' REACT names
  read together give marks, intents and the receipt BYTE-IDENTICAL to the per-name path (quiet names read again from the
  open, a name with no bar read alone, a mark stored before the decision read from the store), in a few requests where
  the per-name path makes one a name (300 names: over 300 requests to under 15); at the House's data interval (0.5 s a
  request) the receipt of a 300-name close lands within seconds of 15:47:00 ET where the per-name path's lands after the
  book's 15:49:00 send line; a group a written look keeps fetches nothing; a batch that raises costs only time (the
  per-name path decides, `marks_error` says why) while the task's own time bound still stops the task;
- THE BOOK (league/equity/live.py, the real book and the real sizing): with the lane's and the learner's receipts landing
  when the lane's simulated decision finishes them, PREREG-EVL-5's DROP buy, EVL-LRN-ON's pick and the close birth held
  back for it are all sent at the 15:48 book minute, before 15:49; and with the learner's receipt never landing, the
  birth is still sent at the window's last book minute (A140: the late learner takes nothing, its rows say `late`, a
  warning is raised), while before that minute it waits as before."""

from __future__ import annotations

import datetime as dt
import functools
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from unittest import mock

from league.equity import live as L
from league.events import book as EB
from league.events import calendar as C
from league.events import house as H
from league.events import learner as LR
from league.events import programs as P
from league.events import run as R
from league.events import screen as SN
from league.events import store as S
from league.tests import evl4_world as W
from league.tests import test_events_book as TB
from league.tests import test_events_evl5 as T5
from league.tests import test_events_evl7 as T7

P_DAY, D_DAY = W.P_DAY, W.D_DAY         # Mon Oct 26 and Tue Oct 27, 2026 (invented sessions of the lane's calendar)
ON = T7.ON


def names(n: int, prefix: str = "Q") -> list[str]:
    """`n` invented tickers: `prefix` and three letters (QAAA, QAAB, ...)."""
    out = []
    for i in range(n):
        a, b, c = i // 676, (i // 26) % 26, i % 26
        out.append(prefix + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[a] + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[b] +
                   "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[c])
    return out


class Tape(W.Gateway):
    """evl4_world's invented gateway over many names: every one active and tradable on NASDAQ (daily close 20, volume
    1,000,000), and SIP 1-MINUTE BARS AS ALPACA PAGES THEM: for each requested symbol in symbol order, one bar a minute
    from the request's start (never before 09:30 ET) through its end, the 15:30 minute included (the rule must leave it
    out), each close an invented figure of the symbol and the minute; `limit` bars a page, the rest behind
    `next_page_token`. A QUIET name trades last at 14:10 ET; a DARK name has no bar. Each request moves the world's clock
    by `step` seconds (the House's spacing of its data reads: house.py `DATA_INTERVAL`). `fail` raises it for a batched
    request (one with `page_token`) instead of answering."""

    def __init__(self, tickers: Iterable[str], *, quiet: Iterable[str] = (), dark: Iterable[str] = ()):
        super().__init__(doc={}, news={}, minute={})
        self.tickers = tuple(tickers)
        self.quiet, self.dark = set(quiet), set(dark)
        self.step = 0.0
        self.tick: Callable[[float], None] | None = None
        self.fail: BaseException | None = None

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        params = dict(params or {})
        if self.tick is not None and self.step:
            self.tick(self.step)
        if path.endswith("/v2/assets"):
            self.gets.append((path, params))
            return [{"symbol": t, "status": "active", "tradable": True, "class": "us_equity", "exchange": "NASDAQ"}
                    for t in self.tickers]
        if path.endswith("/v2/stocks/bars") and params.get("timeframe") == "1Min":
            self.gets.append((path, params))
            if self.fail is not None and "page_token" in params:
                raise self.fail
            return self.minutes(params)
        return super().get_json(path, params)

    def minutes(self, params: Mapping[str, Any]) -> dict[str, Any]:
        start, end = S.parse_iso(params["start"]), S.parse_iso(params["end"])
        day = end.astimezone(C.NY).date()
        first = max(start, W.et(day, 9, 30))
        rows: list[tuple[str, dict[str, Any]]] = []
        for sym in sorted(x for x in str(params["symbols"]).split(",") if x):
            if sym in self.dark:
                continue
            last = min(end, W.et(day, 14, 10)) if sym in self.quiet else end
            t = first
            while t <= last:
                minute = int((t - W.et(day, 9, 30)).total_seconds() // 60)
                close = round(18.0 + (sum(map(ord, sym)) % 97) / 25.0 + minute / 1000.0, 4)
                rows.append((sym, {"t": S.iso(t), "o": close, "h": close, "l": close, "c": close, "v": 100}))
                t += dt.timedelta(minutes=1)
        offset = int(params.get("page_token") or 0)
        limit = int(params.get("limit") or 10000)
        page: dict[str, list[dict[str, Any]]] = {}
        for sym, bar in rows[offset:offset + limit]:
            page.setdefault(sym, []).append(bar)
        more = offset + limit < len(rows)
        return {"bars": page, "next_page_token": str(offset + limit) if more else None}

    def minute_requests(self) -> list[dict[str, Any]]:
        return [p for path, p in self.gets if path.endswith("/v2/stocks/bars") and p.get("timeframe") == "1Min"]


class World(W.World):
    """evl4_world's lane store over `Tape`'s names: its SEC ticker file and company feed name them all."""

    def __init__(self, root: str | Path, tape: Tape):
        self.tape = tape
        cik = {t: str(i + 1).zfill(10) for i, t in enumerate(tape.tickers)}
        self.cik = cik

        def sec(url: str) -> bytes:
            if url.endswith("company_tickers.json"):
                return json.dumps({str(i): {"cik_str": int(cik[t]), "ticker": t, "title": f"{t} Inc."}
                                   for i, t in enumerate(tape.tickers)}).encode()
            return W.sec(url)
        with mock.patch.object(W, "sec", sec):
            super().__init__(root, tape)
        self.ctx.sec = sec
        tape.tick = self.advance

    def advance(self, seconds: float) -> None:
        self.now = self.now + dt.timedelta(seconds=seconds)

    def earnings(self, ticker: str, i: int) -> None:
        """An earnings 8-K (2.02) of `ticker` accepted on P after its close (D's ERN rows: C1, REACT-ON, REACT-READ-C1,
        PREREG-EVL-5's DROP and UNDER)."""
        acc = f"{self.cik[ticker]}-26-{i:06d}"
        with mock.patch.object(W, "CIK", self.cik):
            self.filing(acc, ticker, accepted=W.et(P_DAY, 16, 30) + dt.timedelta(seconds=i % 600), items=("2.02",))

    def day_news(self, ident: str, symbol: str, minute: int, *, symbols: list[str] | None = None) -> None:
        """An article of D's session (DAY(D): NEWS-READ-ON, its control and NEWS-REACT-ON)."""
        self.article(ident, symbol, knowable=W.et(D_DAY, 10, 0) + dt.timedelta(minutes=minute), symbols=symbols)

    def session_of_d(self, *, until_close: bool = True) -> None:
        """D decided the way the House decides it up to its close decision: the verdicts asked ahead with the decisions'
        own code, the open decision at 09:15 ET, the close's verdicts asked at 15:17 ET."""
        self.at(W.et(D_DAY, 7, 31)).decide("open", D_DAY, ask_only=True)
        self.at(W.et(D_DAY, 7, 32)).decide("close", D_DAY, ask_only=True)
        self.at(W.et(D_DAY, 9, 15, 30)).decide("open", D_DAY)
        self.at(W.et(D_DAY, 15, 17)).decide("close", D_DAY, ask_only=True)

    def close(self) -> None:  # noqa: D401 - the store's
        self.st.close()

    # -- what a decision left ------------------------------------------------------------------------------------
    def marks(self) -> list[tuple]:
        return [tuple(r) for r in self.st.db.execute("SELECT symbol, day, label, px, t, source, fetched_at FROM marks "
                                                      "ORDER BY symbol, day, label")]

    def receipt(self, job: str) -> dict[str, Any] | None:
        row = self.st.db.execute("SELECT * FROM receipts WHERE job=? ORDER BY id LIMIT 1", (job,)).fetchone()
        return None if row is None else dict(row)


def build(root: Path, tape: Tape, fill: Callable[[World], None]) -> World:
    w = World(root, tape)
    fill(w)
    w.session_of_d()
    return w


def per_name() -> Any:
    """THE PER-NAME PATH (the code before the hotfix): no batch, every mark read alone by `_mark_1530`."""
    return mock.patch.object(R, "_react_marks", lambda ctx, day, names: 0, create=True)


def close_at(w: World, when: dt.datetime, *, step: float = 0.0) -> tuple[dict[str, Any], int]:
    """D's LIVE close decision from `when` (the House's 15:47:00 ET: the decision's time + CLOSE_GRACE), each data read
    `step` seconds apart; (its summary, the gateway requests it made BEFORE ITS RECEIPT FINISHED)."""
    w.tape.gets.clear()
    w.tape.step = step
    counted: list[int] = []
    finish = w.st.finish_receipt

    def finished(rid: int, *args: Any, **kw: Any) -> Any:
        row = w.st.db.execute("SELECT job FROM receipts WHERE id=?", (rid,)).fetchone()
        if row is not None and str(row["job"]) == f"decide-close:{D_DAY}" and not counted:
            counted.append(len(w.tape.gets))
        return finish(rid, *args, **kw)
    with mock.patch.object(w.st, "finish_receipt", finished):
        out = w.at(when).decide("close", D_DAY)
    w.tape.step = 0.0
    return out, (counted[0] if counted else len(w.tape.gets))


# --------------------------------------------------------------------------------------------------- the scenarios
def wide(n: int, *, quiet: int = 4, dark: int = 0, news: int = 30) -> tuple[Tape, Callable[[World], None]]:
    """`n` issuers with an earnings 8-K accepted on P after its close; the last `quiet` of them quiet after 14:10 ET, the
    last `dark` with no bar at all; `news` of them with an article of D's session, and `news` news-only names besides
    (no 8-K); and one two-symbol article (no program's row: `programs.news_in` reads single-symbol articles)."""
    ern = names(n)
    only = names(news, prefix="Z")
    tape = Tape(ern + only, quiet=ern[n - quiet - dark:n - dark], dark=ern[n - dark:])

    def fill(w: World) -> None:
        for i, sym in enumerate(ern):
            w.earnings(sym, i + 1)
        for i, sym in enumerate(ern[:news]):
            w.day_news(f"n-{sym}", sym, i % 300)
        for i, sym in enumerate(only):
            w.day_news(f"n-{sym}", sym, i % 300)
        if only:
            w.day_news("n-two", only[0], 5, symbols=[only[0], ern[0]])
    return tape, fill


@functools.lru_cache(maxsize=None)
def landing(n: int = 300) -> dict[str, Any]:
    """THE HOUSE'S TIMING OF A WIDE CLOSE (the module's simulation, run once): D's live close decision of `n` earnings
    issuers from 15:47:00 ET with every data read DATA_INTERVAL apart, by the hotfix's code and by the per-name path:
    when each one's House receipt and EVL-LRN-ON's own live receipt finished (UTC datetimes; the learner's None when its
    part wrote none), and the requests made before the House's receipt finished."""
    out: dict[str, Any] = {}
    for name, ctxm in (("batched", None), ("per_name", per_name)):
        with tempfile.TemporaryDirectory() as tmp:
            tape, fill = wide(n)
            w = build(Path(tmp) / "lane", tape, fill)
            try:
                if ctxm is None:
                    _, requests = close_at(w, W.et(D_DAY, 15, 47), step=H.DATA_INTERVAL)
                else:
                    with ctxm():
                        _, requests = close_at(w, W.et(D_DAY, 15, 47), step=H.DATA_INTERVAL)
                house = w.receipt(f"decide-close:{D_DAY}")
                lrn = w.receipt(LR.live_job(T7.learner(ON), D_DAY))
                out[name] = {"house": S.parse_iso(house["finished_at"]), "requests": requests,
                             "learner": S.parse_iso(lrn["finished_at"]) if lrn and lrn.get("finished_at") else None,
                             "status": house["status"]}
            finally:
                w.close()
    return out


class TheLaneReadsTheMarksTogether(unittest.TestCase):
    """league/events/run.py `decide_close` on invented worlds of many names."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def world(self, name: str, tape: Tape, fill: Callable[[World], None]) -> World:
        w = build(self.root / name, tape, fill)
        self.addCleanup(w.close)
        return w

    def intents(self, w: World) -> list[tuple]:
        return [tuple(r) for r in w.st.db.execute("SELECT * FROM intents ORDER BY program, version, event")]

    def test_the_marks_intents_and_receipt_are_byte_identical_to_the_per_name_paths_in_a_few_requests(self):
        def run(name: str, batched: bool) -> tuple[World, dict, int]:
            tape, fill = wide(160, quiet=5, dark=2, news=25)
            w = self.world(name, tape, fill)
            # (one name's mark already stored before the decision, as an earlier read would leave it)
            w.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('QAAC', ?, '1530', "
                            "19.5, ?, 'sip-1min', 'x')", (D_DAY.isoformat(), S.iso(W.et(D_DAY, 15, 29))))
            if batched:
                out, requests = close_at(w, W.et(D_DAY, 15, 47))
            else:
                with per_name():
                    out, requests = close_at(w, W.et(D_DAY, 15, 47))
            return w, out, requests
        old, old_out, old_n = run("per-name", False)
        new, new_out, new_n = run("batched", True)
        self.assertEqual(new.marks(), old.marks(), "every mark the same row: symbol, bar time, price, source, fetch")
        self.assertGreater(len(old.marks()), 150)
        self.assertEqual(self.intents(new), self.intents(old), "every program's intents the same")
        self.assertEqual(new_out, old_out, "the same summary")
        a, b = new.receipt(f"decide-close:{D_DAY}"), old.receipt(f"decide-close:{D_DAY}")
        self.assertEqual((a["status"], a["summary"]), (b["status"], b["summary"]), "the same stored receipt")
        quiet = [r for r in new.marks() if r[0] in new.tape.quiet]
        self.assertEqual(len(quiet), 5)
        self.assertTrue(all(r[4] == S.iso(W.et(D_DAY, 14, 10)) for r in quiet), "a quiet name's last bar, from the open")
        self.assertTrue(all(r[4] == S.iso(W.et(D_DAY, 15, 29)) for r in new.marks()
                            if r[0] not in new.tape.quiet and r[2] == "1530"),
                        "the last bar ending by 15:30 ET, never the 15:30 minute's")
        self.assertFalse([r for r in new.marks() if r[0] in new.tape.dark], "a name with no bar has no mark")
        self.assertGreater(old_n, 185, "the per-name path: one request a name")
        self.assertLess(new_n, 30, "batched: a few requests (the two dark names still read alone, each time asked)")
        batch = [p for p in new.tape.minute_requests() if "," in str(p["symbols"])]
        self.assertTrue(batch and all(len(str(p["symbols"]).split(",")) <= R.MARK_BATCH for p in batch))
        self.assertEqual({p["start"] for p in batch}, {S.iso(W.et(D_DAY, 15, 0)), S.iso(W.et(D_DAY, 9, 30))},
                         "from 15:00 ET, then from the open for the names that span gave none")

    def test_300_names_take_a_few_requests_and_the_receipt_lands_long_before_the_send_line(self):
        got = landing(300)
        self.assertGreater(got["per_name"]["requests"], 300, "the per-name path: one request a name")
        self.assertLess(got["batched"]["requests"], 15, "batched: from over 300 requests to under 15")
        line = W.et(D_DAY, 15, 49)
        self.assertGreater(got["per_name"]["house"], line, "the defect: the per-name receipt lands after 15:49:00 ET")
        self.assertLessEqual(got["batched"]["house"], W.et(D_DAY, 15, 47, 15), "the receipt about 15:47:15 at the latest")
        if got["batched"]["learner"] is not None:
            self.assertLessEqual(got["batched"]["learner"], W.et(D_DAY, 15, 47, 25), "the learner's part by 15:47:25")
        self.assertEqual(got["batched"]["status"], got["per_name"]["status"])

    def test_a_group_a_written_look_keeps_fetches_nothing(self):
        tape, fill = wide(40, quiet=0, news=6)
        w = self.world("kept", tape, fill)
        for p in P.PROGRAMS:        # (a look of every ern-react close program: every one of its groups kept over D)
            if p.entry_at == "close" and p.family == "ern-react":
                w.st.db.execute("INSERT OR IGNORE INTO looks(program, version, k, at, held, passed, why) VALUES(?, ?, 1, "
                                "'2026-12-31T21:00:00Z', 0, 0, 'invented')", (p.id, p.version))
        given: list[set[str]] = []
        real = R._react_marks

        def spy(ctx: Any, day: dt.date, names_: Iterable[str]) -> int:
            given.append(set(names_))
            return real(ctx, day, given[-1])
        with mock.patch.object(R, "_react_marks", spy):
            out, _ = close_at(w, W.et(D_DAY, 15, 47))
        self.assertTrue({"EVL-ERN-REACT-C1", "EVL-ERN-REACT-ON", "EVL-ERN-REACT-READ-C1"} <=
                        {k.partition("@")[0] for k in out["kept"]}, "every ern-react program kept")
        news = set(names(6)) | set(names(6, prefix="Z"))
        self.assertEqual(given, [news], "only NEWS-REACT-ON's names (its own symbol's rows): no kept group's")
        since = [p for p in w.tape.minute_requests() if p["start"] == S.iso(W.et(D_DAY, 15, 0))]
        self.assertEqual({s for p in since for s in str(p["symbols"]).split(",")}, news,
                         "the batch read none of the kept groups' earnings-only names")
        alone = [p for p in w.tape.minute_requests() if "page_token" not in p]
        self.assertEqual(alone, [], "and nothing was read alone: the kept rows' reactions read the store only")

    def test_a_raising_batch_costs_only_time_and_the_per_name_path_decides(self):
        tape, fill = wide(30, quiet=2, news=5)
        old = self.world("per-name", tape, fill)
        with per_name():
            old_out, _ = close_at(old, W.et(D_DAY, 15, 47))
        tape, fill = wide(30, quiet=2, news=5)
        new = self.world("raising", tape, fill)
        new.tape.fail = RuntimeError("invented: the batch's answer cannot be read")
        new_out, _ = close_at(new, W.et(D_DAY, 15, 47))
        self.assertEqual(new_out.pop("marks_error"), "RuntimeError: invented: the batch's answer cannot be read")
        self.assertEqual(new_out, old_out, "the per-name path decided: the same summary")
        self.assertEqual(self.intents(new), self.intents(old))
        self.assertEqual(new.marks(), old.marks())
        self.assertEqual(new.receipt(f"decide-close:{D_DAY}")["status"], "ok")

    def test_the_tasks_own_time_bound_still_stops_the_task(self):
        tape, fill = wide(12, quiet=0, news=0)
        w = self.world("deadline", tape, fill)
        w.tape.fail = R.Deadline("invented: past the task's bound")
        with self.assertRaises(R.Deadline):
            close_at(w, W.et(D_DAY, 15, 47))
        row = w.receipt(f"decide-close:{D_DAY}")
        self.assertIsNone(row["finished_at"], "no receipt finished: the next turn decides the close again")


# ------------------------------------------------------------------------------------------------------- the book
def on_day(when: dt.datetime) -> dt.datetime:
    """A time of the simulated session (Tue Oct 27) at the same New York clock time of the book's DAY (Wed Nov 4)."""
    local = when.astimezone(C.NY)
    return dt.datetime.combine(TB.DAY, local.time().replace(tzinfo=None), C.NY).astimezone(dt.timezone.utc)


class TheCloseEntriesGoBeforeTheLine(TB.EventTest):
    """THE REAL BOOK at DAY's close with PREREG-EVL-7 pinned: PREREG-EVL-5's DROP buy (ACME, waiting for the lane's close
    receipt to name its program: `book.part_hold`), EVL-LRN-ON's live pick (GAMA, waiting for its own live receipt) and
    a registered close-entry birth at learning (BETA), which ROOM holds behind the learner (`book.after_learners`)."""

    def setUp(self):
        super().setUp()
        T7.pin(self)
        self.addCleanup(P.load_births, None)
        h = self.h = self.harness()
        room = T5.TheRoomWhileItWaits
        room.fall(self, h, "ACME", TB.CIK, "e-1", 15.2)        # 0.95: EVL-ERN-DROP-ON
        room.fall(self, h, "BETA", TB.CIK2, "e-2", 15.44)      # 0.965: the birth's alone
        self.born = room.birth(self, h)
        T7.TheMoney.live(self, h.lane, ON, TB.DAY, [(TB.CIK3, "GAMA", 16.0)], named=None)   # its receipt not yet
        h.symbol("GAMA", last=16.4)
        h.venue.prints[("GAMA", TB.DAY.isoformat(), "close")] = Decimal("16.40")
        h.lane.decided(TB.DAY, "open")
        self.drop = next(p for p in EB.seatable() if p.id == "EVL-ERN-DROP-ON")        # (its seat: PREREG-EVL-6's)

    def land_house(self) -> None:
        """The lane's close receipt of DAY, naming DROP's seat (as `decide_close` finishes it)."""
        rid = self.h.lane.st.start_receipt(f"decide-close:{TB.DAY.isoformat()}")
        self.h.lane.st.finish_receipt(rid, "ok", {SN.program_key(self.drop.id, self.drop.version): {"planned": 1},
                                                  self.born.id: {"planned": 1}})

    def minutes(self, lands: Mapping[str, dt.datetime]) -> list[tuple[str, str, float]]:
        """The close window's book minutes (15:46:03 to 15:48:03 ET); before each, the receipts of `lands` whose time has
        come land in the lane's store. Returns (side, symbol, when) of every order sent."""
        sent: list[tuple[str, str, float]] = []
        seen = 0
        landed: set[str] = set()
        for mm in (46, 47, 48):
            at = TB.at(TB.DAY, 15, mm)
            for what, when in lands.items():
                if what not in landed and when.timestamp() <= at:
                    landed.add(what)
                    if what == "house":
                        self.land_house()
                    else:
                        T7.name_live(self.h.lane.st, ON, TB.DAY, finished=when)
            self.out = self.h.tick(15, mm)
            bodies = self.h.bodies()
            sent += [(b["side"], b["symbol"], at) for b in bodies[seen:]]
            seen = len(bodies)
        return sent

    def all_three(self, lands: Mapping[str, dt.datetime]) -> None:
        sent = self.minutes(lands)
        buys = {sym: when for side, sym, when in sent if side == "buy"}
        self.assertEqual(set(buys), {"ACME", "GAMA", "BETA"}, "the DROP buy, the learner's pick and the held birth")
        self.assertTrue(all(when < TB.at(TB.DAY, 15, 49, 0) for when in buys.values()), "all sent before 15:49")
        self.assertLessEqual(buys["BETA"], TB.at(TB.DAY, 15, 48), "by the 15:48 book minute")
        main = self.h.book._event_summary(TB.DAY.isoformat(), "close")
        self.assertIn(self.born.id, main["learners"]["deferred"], "the birth was held for the learner, as before")
        self.assertNotIn("late", main["learners"])
        lrn = self.h.book._event_summary(TB.DAY.isoformat(), "close-lrn")
        self.assertEqual((lrn["programs"][ON]["planned"], lrn["programs"][self.born.id]["planned"]), (1, 1))

    def test_with_the_receipts_landing_when_the_lanes_simulated_decision_finishes_them_all_three_go_before_1549(self):
        got = landing(300)["batched"]
        house = got["house"]
        learner = got["learner"] or house + dt.timedelta(seconds=25)
        self.assertLessEqual(max(house, learner), W.et(D_DAY, 15, 47, 40), "both land by about 15:47:40 ET")
        self.all_three({"house": on_day(house), "learner": on_day(learner)})

    def test_with_both_receipts_landing_at_154740_all_three_go_before_1549(self):
        at = dt.datetime.fromtimestamp(TB.at(TB.DAY, 15, 47, 40), dt.timezone.utc)
        self.all_three({"house": at, "learner": at})

    def test_with_the_receipts_landing_as_the_per_name_path_finished_them_the_waiting_buys_are_lost(self):
        """The defect as the House's receipts made it (the per-name path's timing, after 15:49:00 ET): the DROP buy and
        the learner's pick are never sent (the birth goes at the last minute only by A140)."""
        got = landing(300)["per_name"]
        sent = self.minutes({"house": on_day(got["house"]), "learner": on_day(got["learner"] or got["house"])})
        buys = {sym for side, sym, _ in sent if side == "buy"}
        self.assertNotIn("ACME", buys, "the DROP buy is lost")
        self.assertNotIn("GAMA", buys, "so is the learner's pick")
        self.assertIn("BETA", buys, "the birth held for the learner goes at the last book minute (A140)")

    def test_with_the_learners_receipt_never_landing_the_birth_is_still_sent_at_the_last_minute(self):
        sent: list[tuple[str, str, float]] = []
        seen = 0
        out: dict[str, Any] = {}
        for mm in (46, 47):
            out = self.h.tick(15, mm)
            sent += [(b["side"], b["symbol"], TB.at(TB.DAY, 15, mm)) for b in self.h.bodies()[seen:]]
            seen = len(self.h.bodies())
        self.assertIn("waiting for the live receipt", str(out.get("event_decide_lrn")), "before the last minute: waits")
        self.assertNotIn(self.born.id, [r["program"] for r in self.h.event_intents("buy")], "the birth waits with it")
        self.land_house()
        out = self.h.tick(15, 48)
        sent += [(b["side"], b["symbol"], TB.at(TB.DAY, 15, 48)) for b in self.h.bodies()[seen:]]
        buys = [sym for side, sym, _ in sent if side == "buy"]
        self.assertEqual(sorted(buys), ["ACME", "BETA"], "the DROP buy and the birth; nothing for the late learner")
        self.assertTrue(all(when < TB.at(TB.DAY, 15, 49, 0) for _, _, when in sent))
        self.assertNotIn(ON, [r["program"] for r in self.h.event_intents("buy")])
        lrn = self.h.book._event_summary(TB.DAY.isoformat(), "close-lrn")
        self.assertEqual(lrn["late"], [ON])
        self.assertEqual(lrn["programs"][ON], {"picks": None, "room": 0, "late": L.LEARNER_LATE})
        main = self.h.book._event_summary(TB.DAY.isoformat(), "close")
        self.assertEqual((main["learners"]["late"], main["learners"]["decided"]), ([ON], True))
        self.assertIn(L.LEARNER_LATE, str(out.get("event_decide_lrn")))
        self.assertTrue(any(level == "warning" and "A140" in text for level, text in self.h.alerts), "a warning")
        self.assertTrue(any(kind == "equity.alert" and payload.get("learners_late") == [ON]
                            for kind, payload in self.h.events))
        T7.name_live(self.h.lane.st, ON, TB.DAY)        # (its receipt after all, too late: still nothing)
        self.h.tick(15, 48, 40)
        self.assertNotIn(ON, [r["program"] for r in self.h.event_intents("buy")])


if __name__ == "__main__":
    unittest.main()
