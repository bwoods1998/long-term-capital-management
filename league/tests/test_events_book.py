"""RELEASE R2: the equity book's EVENT KIND (league/equity/live.py `_event_step`, league/events/book.py, the auction
proof of league/events/proof.py), through the REAL book, the REAL `size_entry` and the real money table in force,
against an in-memory venue whose auction orders fill at an invented auction print, and a lane store of invented events
(PREREG-EVL-1 sections 3, 5 and 8; PREREG-EVL-2's overnight rows). No figure here is a market's.

Held here: every event program ships at shadow and a passed look seats it from the next decision; the real-money
decision reads only events stored and verdicts answered before its decision time; the auction orders' shapes (a whole-
share limit-on-open or limit-on-close buy at 1.25 x the previous SIP close, a market-on-close or market-on-open sale);
the size (5% of E in whole shares, one share when that rounds to none and fits the walls, the book-wide 10% a name,
the loss budget at the lot's own weight); the exits at the scheduled auction and the fallback ladder; the open risk
of an event lot (max(0.10, 1.65 x sigma x sqrt(h)), 0.40 when sigma is unknown or the lot is past its exit); the kill
switch, the kind's switch and the auction proof's BUY stage stopping buys and never sales; one name an auction across
programs; and THE OLD LANES STAY EXITS ONLY (`equity_money.enabled` False): no ETF or panel program buys while an
event program does."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import math
import tempfile
import unittest
import uuid
from decimal import Decimal as D
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from league.constitution import CONSTITUTION
from league.equity import live as L
from league.equity import schedule as ES
from league.events import book as EB
from league.events import programs as P
from league.events import proof as PR
from league.events import store as LS
from league.events import verdicts as V
from league.live import money as M
from league.live.state import LiveState
from league.live.venue import Submitted
from league.ops import twins as TW
from league.tests import test_equity_book as T

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
PRIOR, DAY, NEXT = dt.date(2026, 11, 3), dt.date(2026, 11, 4), dt.date(2026, 11, 5)
CIK, CIK2, CIK3 = "0000000001", "0000000002", "0000000003"


def at(day: dt.date, hh: int, mm: int, ss: int = 3) -> float:
    return dt.datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=NY).timestamp()


def iso(day: dt.date, hh: int, mm: int) -> str:
    return LS.iso(dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=NY))


# ----------------------------------------------------------------------------------------------------- the lane store
class Lane:
    """An invented lane store (`<root>/events/events.sqlite`): the book's NYSE sessions, 8-K filings, verdicts,
    universe rows, looks and the lane's decision receipts."""

    def __init__(self, root: Path):
        self.st = LS.Store(root / "events")
        d = dt.date(2026, 9, 1)
        with self.st.tx() as db:
            while d <= dt.date(2026, 12, 31):
                m = ES.moments(d)
                if m is not None:
                    db.execute("INSERT INTO sessions(day, open_at, close_at, early) VALUES(?, ?, ?, ?)",
                               (d.isoformat(), LS.iso(dt.datetime.fromtimestamp(m.open_at, UTC)),
                                LS.iso(dt.datetime.fromtimestamp(m.close_at, UTC)), int(m.early)))
                d += dt.timedelta(days=1)

    def filing(self, accession: str, cik: str, *, accepted: str, received: str | None = None, items=("2.02",),
               form: str = "8-K") -> None:
        knowable = LS.iso(LS.parse_iso(accepted) + dt.timedelta(minutes=10))
        self.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, "
                           "received_at, source, text_sha, text_len, status) VALUES(?, ?, ?, 'Invented Co', ?, ?, ?, ?, "
                           "'current', 'x', 5000, 'fetched')",
                           (accession, form, cik, json.dumps(list(items)), accepted, knowable, received or accepted))

    def verdict(self, accession: str, score: int, *, answered: str, guidance: str = "none", status: str = "ok",
                news: bool = False) -> None:
        event, prompt = (f"news:{accession}", V.PROMPTS["news"]) if news else (f"8k:{accession}", V.PROMPTS["doc"])
        self.st.db.execute("INSERT INTO verdicts(event, prompt_sha, model, request_id, asked_at, answered_at, status, "
                           "score, guidance, answer, usd) VALUES(?, ?, ?, 'r', ?, ?, ?, ?, ?, '{}', 0.001)",
                           (event, prompt.sha, V.MODEL, answered, answered, status, score, guidance))

    def article(self, ident: str, symbol: str, *, knowable: str) -> None:
        self.st.db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, headline, "
                           "summary, symbols, live) VALUES(?, ?, NULL, ?, ?, 'invented', 'h', 's', ?, 1)",
                           (ident, knowable, knowable, knowable, json.dumps([symbol])))

    def insider_buy(self, accession: str, cik: str, *, accepted: str, usd: float) -> None:
        self.filing(accession, cik, accepted=accepted, items=(), form="4")
        self.st.db.execute("INSERT INTO form4_owners(accession, owner_cik, owner_name, is_director, is_officer, "
                           "officer_title, is_ten_pct) VALUES(?, '9', 'Invented Owner', 1, 0, NULL, 0)", (accession,))
        day = LS.parse_iso(accepted).astimezone(NY).date().isoformat()
        self.st.db.execute("INSERT INTO form4_tx(accession, seq, security, tx_date, code, shares, price, acquired, "
                           "owned_after) VALUES(?, 1, 'Common', ?, 'P', ?, 10.0, 'A', 1)", (accession, day, usd / 10.0))

    def universe(self, day: dt.date, symbol: str, cik: str, prev_close: float, *, adv20: float = 5e6) -> None:
        self.st.db.execute("INSERT OR REPLACE INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench, "
                           "sigma60) VALUES(?, ?, ?, 'Invented Co', 'NASDAQ', ?, ?, 'IWM', NULL)",
                           (day.isoformat(), symbol, cik, prev_close, adv20))

    def look(self, program: str, *, passed: bool = True, held: bool = True, k: int = 1) -> None:
        self.st.db.execute("INSERT OR REPLACE INTO looks(program, version, k, at, sessions, n, issuers, blocks, mean_a, "
                           "mean_r, mean_a_tradable, p, alpha, fp_check, held, passed, why) VALUES(?, 1, ?, ?, 10, 80, 50, "
                           "10, 0.01, 0.01, 0.01, 0.001, 0.024, 0.0, ?, ?, 'invented')",
                           (program, k, iso(PRIOR, 16, 0), int(held), int(passed)))

    def decided(self, day: dt.date, at_: str = "open") -> None:
        rid = self.st.start_receipt(f"decide-{at_}:{day.isoformat()}")
        self.st.finish_receipt(rid, "ok", {})

    def intent(self, program: str, event: str, symbol: str, cik: str, entry: dt.date, exit_: dt.date, *,
               status: str = "planned") -> None:
        """A shadow intent as the lane's own decision writes it (league/events/programs.py `write_intents`)."""
        p = P.BY_ID[program]
        self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                           "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, ?, ?, ?, ?, 'x', ?, ?, ?, ?, 3, "
                           "'shadow', ?, NULL)", (p.id, p.version, event, symbol, cik, entry.isoformat(), p.entry_at,
                                                  exit_.isoformat(), p.exit_at, status))


def earnings(lane: Lane, accession: str = "a-1", cik: str = CIK, symbol: str = "ACME", *, prev_close: float = 40.0,
             score: int = 3, received: str | None = None, answered: str | None = None) -> None:
    """An earnings 8-K accepted after the PRIOR session's close, its verdict, and its issuer's universe row for DAY."""
    lane.filing(accession, cik, accepted=iso(PRIOR, 16, 30), received=received or iso(PRIOR, 16, 31))
    lane.verdict(accession, score, answered=answered or iso(PRIOR, 16, 35))
    lane.universe(DAY, symbol, cik, prev_close)


# ----------------------------------------------------------------------------------------------------- the venue
class Client:
    """The real account's gateway client as `book.publish` reads it: the eligible list's route, answered as the
    gateway answers it."""

    gateway_url = "https://gateway.invalid"

    class gateway:  # noqa: N801 - the signer's shape
        @staticmethod
        def headers() -> dict:
            return {"Authorization": "Bearer invented"}

    def __init__(self) -> None:
        self.transport = self
        self.lists: list[dict] = []
        self.fail = False

    def request(self, method, url, *, headers, body, timeout):
        doc = json.loads(body)
        self.lists.append(doc)
        if self.fail:
            return 503, {}, b'{"error": "down", "cap": "setup"}'
        names = sorted(set(doc["symbols"]))
        sha = hashlib.sha256(f"{doc['day']}:{','.join(names)}".encode()).hexdigest()
        return 200, {}, json.dumps({"ok": True, "day": doc["day"], "count": len(names), "sha": sha, "at": "t"}).encode()


class AuctionVenue(T.Venue):
    """The stock account with the auctions: an `opg` or `cls` order waits for its session's opening (09:30) or closing
    (16:00) cross and fills whole at the auction's print (`prints[(symbol, day, "open" | "close")]`) when its limit
    admits it, else it ends (canceled); a day order trades on the quote as the base venue's does."""

    def __init__(self, market, clock, *, cash="2000"):
        super().__init__(market, clock, cash=cash)
        self.prints: dict[tuple[str, str, str], D] = {}
        self.client = Client()
        self.gateway_refuses: str | None = None

    def submit(self, body, *, exit: bool) -> Submitted:
        body = dict(body)
        self.sent.append(body)
        if self.gateway_refuses and body["side"] == "buy":
            return Submitted(False, {"error": "refused", "cap": self.gateway_refuses}, "HTTP 403 refused", status=403)
        order = {"id": str(uuid.uuid4()), "client_order_id": body["client_order_id"], "status": "new",
                 "symbol": body["symbol"], "side": body["side"], "qty": body["qty"],
                 "limit_price": body.get("limit_price"), "type": body["type"], "time_in_force": body["time_in_force"],
                 "filled_qty": "0", "filled_avg_price": None, "order_class": "simple", "legs": None,
                 "_day": dt.datetime.fromtimestamp(self.clock(), NY).date().isoformat()}
        self.book.append(order)
        self._try_fill(order)
        return Submitted(True, self._public(order), "", status=200)

    def _try_fill(self, o: dict) -> None:
        tif = o.get("time_in_force")
        if tif not in ("opg", "cls"):
            return super()._try_fill(o)
        day = dt.date.fromisoformat(o["_day"])
        m = ES.moments(day)
        when = m.open_at if tif == "opg" else m.close_at
        if self.clock() < when:
            return
        px = self.prints.get((o["symbol"], o["_day"], "open" if tif == "opg" else "close"))
        buying = o["side"] == "buy"
        if px is None or (o["type"] == "limit" and ((buying and D(o["limit_price"]) < px)
                                                    or (not buying and D(o["limit_price"]) > px))):
            o["status"], o["canceled_at"] = "canceled", T.iso(self.clock())
            return
        qty = D(o["qty"])
        o["filled_qty"], o["filled_avg_price"], o["status"] = str(qty), str(px), "filled"
        o["filled_at"] = T.iso(self.clock())
        self.held[o["symbol"]] = self.held.get(o["symbol"], D(0)) + (qty if buying else -qty)
        self.cash += -px * qty if buying else px * qty


class AuctionProof:
    """The auction paper proof at its interface: `ok` its BUY stage, `failed` a SELL stage that failed."""

    def __init__(self, ok: bool = True):
        self.ok, self.failed, self.steps = ok, "", 0

    def buy_passed(self) -> bool:
        return self.ok

    def sell_failed(self) -> str:
        return self.failed

    def passed(self) -> bool:
        return self.ok and not self.failed

    def status(self) -> dict:
        return {"stages": {"buy": {"status": "passed" if self.ok else "waiting"}, "sell": None}}

    def step(self, now, moments) -> dict:
        self.steps += 1
        return {"status": "passed" if self.ok else "waiting"}


class Harness(T.Harness):
    """test_equity_book's harness with the auction venue, the lane under the state root, the book built with that root,
    the auction proof at its interface, and the OLD LANES' SWITCH OFF as in force (`equity_money.enabled` False)."""

    def __init__(self, root: Path, *, cash: str = "2000", E: str = "2000", enabled: bool = False):
        self.root = root
        self.lane = Lane(root)
        super().__init__(root, cash=cash, E=E, table=T.equity_table(enabled=enabled))
        self.venue = AuctionVenue(self.market, self.clock, cash=cash)
        self.auction = AuctionProof()
        self.book = self.new_book()
        self.state.put("eq_decide", {"day": PRIOR.isoformat(), "status": "done"})

    def new_book(self) -> L.EquityBook:
        book = L.EquityBook(self.state, self.venue, self.market, self.table, self.families, decider=self.decider,
                            stock_proof=self.proof, sizing_equity=lambda: self.E, options_book=self.options,
                            root=self.root, clock=self.clock,
                            record=lambda kind, payload, agent=None: self.events.append((kind, payload)),
                            alert=lambda level, text: self.alerts.append((level, text)))
        book._auction = getattr(self, "auction", None)
        return book

    def tick(self, hh: int, mm: int, ss: int = 3, *, day: dt.date = DAY, positions=None, open_orders=None) -> dict:
        self.clock.set(at(day, hh, mm, ss))
        return self.book.tick(self.clock(), account_row=self.venue.account(), positions=positions,
                              open_orders=open_orders, real_block=lambda opening=True: self.blocked,
                              killed=lambda: self.kill)

    def symbol(self, symbol: str, *, last: float, sd: float | None = 0.02) -> None:
        """Quotes for the account's marks, and 80 sessions of adjusted SIP daily bars ending the session before DAY
        (an invented walk of daily returns +-`sd`, so sigma is `sd`), or none (`sd` None: sigma cannot be read)."""
        self.market.quotes[symbol] = (D(str(last)) - D("0.01"), D(str(last)) + D("0.01"))
        if sd is None:
            self.market.bar_rows["all"][symbol] = []
            return
        days, d = [], PRIOR
        while len(days) < 80:
            if ES.is_session(d):
                days.append(d)
            d -= dt.timedelta(days=1)
        rows, px = [], last
        for i, day in enumerate(sorted(days)):
            px = px * (1 + (sd if i % 2 else -sd))
            rows.append({"t": f"{day.isoformat()}T05:00:00Z", "o": px, "h": px, "l": px, "c": round(px, 6), "v": 1e6})
        self.market.bar_rows["all"][symbol] = rows

    def event_intents(self, side: str | None = None) -> list[dict]:
        rows = self.state.rows("SELECT i.status, i.why, i.kind, i.symbol, i.at, i.instance, e.* FROM eq_intents i JOIN "
                               "eq_event_intents e ON e.iid=i.iid ORDER BY i.iid")
        return [r for r in rows if side is None or r["side"] == side]

    def bodies(self) -> list[dict]:
        return [dict(b) for b in self.venue.sent]

    def day(self, day: dt.date = DAY, *, upto: tuple[int, int] = (16, 5)) -> None:
        """The minutes of a session the event kind acts in: the open's decision and sends, the open's cross, the close's
        decision and sends, the close's cross and the settling minutes."""
        for hh, mm in ((9, 15), (9, 16), (9, 17), (9, 31), (9, 33), (15, 46), (15, 47), (15, 48), (16, 1), (16, 3)):
            if (hh, mm) > upto:
                break
            self.tick(hh, mm, day=day)


class EventTest(unittest.TestCase):
    """Every test: a fresh state root (the live state and the lane's store) and the real sizing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def harness(self, **kw) -> Harness:
        h = Harness(self.root, **kw)
        self.addCleanup(h.state.close)
        self.addCleanup(h.lane.st.close)
        self.addCleanup(lambda: h.book._event_lane is not None and h.book._event_lane.close())
        return h

    def seated(self, h: Harness, *programs: str) -> None:
        for program in programs or ("EVL-ERN-READ-O1",):
            h.lane.look(program)
        h.lane.decided(DAY, "open")
        h.lane.decided(DAY, "close")


# ------------------------------------------------------------------------------------------------------- the rows
class TheRows(unittest.TestCase):
    def test_the_event_block_is_the_prereg_and_its_switch_ships_on_beside_the_old_lanes_off(self):
        s = EB.settings()
        self.assertIs(CONSTITUTION["equity_money"]["enabled"], False, "the old lanes stay exits only")
        self.assertIs(s.enabled, True)
        self.assertEqual((s.seats, s.probe_share, s.sized_share, s.probe_open, s.sized_open, s.per_name, s.limit_ratio),
                         (9, D("0.05"), D("0.10"), 6, 8, D("0.10"), D("1.25")))
        self.assertEqual((s.risk_floor, s.risk_z, s.sigma_sessions), (D("0.10"), D("1.65"), 60))
        self.assertEqual((s.sized_min_events, s.sized_confidence), (150, D("0.80")))
        self.assertEqual((s.loss_usd, s.loss_sessions, s.shadow_sessions, s.retire_events), (D("-150"), 20, 20, 100))
        self.assertEqual(dict(s.offsets), ES.EVENT_DEFAULTS)
        self.assertEqual(len(EB.SEATABLE), 9, "PREREG-EVL-1's four and PREREG-EVL-2's five")
        self.assertEqual([p.id for p in EB.SEATABLE][:4],
                         ["EVL-ERN-READ-O1", "EVL-ERN-REACT-C1", "EVL-8K-READ-O1", "EVL-NEWS-READ-O1"])
        self.assertEqual(L.EVENT_LANE, EB.LANE)
        self.assertEqual(L.EVENT_STRICT_WEIGHT, EB.STRICT_WEIGHT)

    def test_the_moments_are_the_preregistered_ones_and_move_with_a_half_day(self):
        m = ES.event_moments(DAY)
        clock = lambda t: dt.datetime.fromtimestamp(t, NY).strftime("%H:%M")  # noqa: E731
        self.assertEqual([clock(x) for x in (m.open_decide, m.open_send, m.open_until, m.close_decide, m.close_send,
                                             m.close_until)], ["09:15", "09:16", "09:27", "15:46", "15:47", "15:49"])
        half = ES.event_moments(dt.date(2026, 11, 27))
        self.assertEqual([clock(x) for x in (half.close_decide, half.close_send, half.close_until)],
                         ["12:46", "12:47", "12:49"])
        self.assertIsNone(ES.event_moments(dt.date(2026, 11, 26)), "Thanksgiving: no session")

    def test_a_table_without_the_block_opens_nothing_and_a_bad_one_is_refused(self):
        from league.constitution import equity_money_problems
        from league.tests import equity_design as X

        before = X.before_r2()
        self.assertEqual(equity_money_problems(before), [], "R2's rollback: a table without the block is valid")
        self.assertEqual(EB.settings(before), EB.FALLBACK)
        self.assertFalse(EB.FALLBACK.enabled)
        for path, value, why in ((("per_name_share",), "0.11", "per_name_share = '0.11' is outside (0, 0.10]"),
                                 (("limit_ratio",), "1.30", "limit_ratio = '1.30' is outside (1.00, 1.25]"),
                                 (("open_risk", "floor"), "0.05", "open_risk.floor = '0.05' is outside [0.10, 1.00]"),
                                 (("position_share", "probe"), "0.20", "position_share.probe = '0.20' is outside"),
                                 (("seats",), 10, "seats = 10 is outside [0, 9]"),
                                 (("order_path", "open_decide_before_open_s"), 600, "is outside [900, 900]"),
                                 (("enabled",), 1, "event.enabled = 1 is not exactly one of [False, True]")):
            bad = json.loads(json.dumps(CONSTITUTION))
            node = bad["equity_money"]["event"]
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            got = " ".join(equity_money_problems(bad))
            self.assertIn(why, got, path)
            self.assertEqual(EB.settings(bad), EB.FALLBACK, path)
        swapped = json.loads(json.dumps(CONSTITUTION))
        swapped["equity_money"]["event"]["order_path"]["open_until_before_open_s"] = 599
        swapped["equity_money"]["event"]["order_path"]["open_send_before_open_s"] = 600
        self.assertEqual(equity_money_problems(swapped), [])
        swapped["equity_money"]["event"]["max_open"] = {"probe": 6, "sized": 5}
        self.assertIn("a Probe program never holds more than a Sized one", " ".join(equity_money_problems(swapped)))

    def test_the_ladder_and_the_lane_names_are_the_shadows(self):
        from league.events import score as SC

        self.assertEqual((EB.LADDER_CLOSES, EB.ZERO_AFTER), (SC.NEXT_CLOSES, SC.ZERO_AFTER))
        self.assertEqual((TW.EVENT_LANE, TW.EVENT_LATE), (EB.LANE, EB.LATE_TAG))
        self.assertEqual(TW.EVENT_DB, Path(EB.LANE_DIR) / LS.DB_NAME)

    def test_limit_weight_sigma_and_exit_plans(self):
        s = EB.settings()
        self.assertEqual(EB.limit_price(D("40"), s.limit_ratio), D("50.00"))
        self.assertEqual(EB.limit_price(D("3.33"), s.limit_ratio), D("4.16"), "rounded DOWN to the cent")
        self.assertEqual(EB.weight(0.02, 1, s), D("0.10"), "1.65 x 2% is under the 10% floor")
        self.assertEqual(EB.weight(0.08, 1, s), D("0.132"))
        self.assertEqual(EB.weight(0.08, 4, s), D("0.264"), "sqrt(h)")
        self.assertEqual(EB.weight(None, 1, s), D("0.40"), "no sigma: the House's old stock floor")
        self.assertEqual(EB.weight(0.9, 1, s), D(1), "never above the whole value")
        walk = [100 * (1.01 if i % 2 else 0.99) ** i for i in range(61)]
        self.assertIsNotNone(EB.sigma(walk))
        self.assertIsNone(EB.sigma(walk[:60]), "60 returns need 61 closes")
        self.assertEqual(EB.exit_plan(P.BY_ID["EVL-ERN-READ-O1"], DAY), (DAY.isoformat(), "close"))
        self.assertEqual(EB.exit_plan(P.BY_ID["EVL-ERN-REACT-C1"], DAY), (NEXT.isoformat(), "close"))
        self.assertEqual(EB.exit_plan(P.BY_ID["EVL-ERN-REACT-ON"], DAY), (NEXT.isoformat(), "open"))
        self.assertEqual(EB.exit_plan(P.BY_ID["EVL-NEWS-READ-ON"], dt.date(2026, 11, 25)), ("2026-11-27", "open"),
                         "over Thanksgiving: the next SESSION's open")


# ------------------------------------------------------------------------------------------------------- the bands
class TheBands(unittest.TestCase):
    def close(self, cash: str, day: str = "2026-11-02", notional: str = "100") -> EB.Close:
        return EB.Close(day, D(cash), D(notional), day, CIK)

    def test_every_program_ships_at_shadow_and_a_passed_look_seats_it(self):
        s = EB.settings()
        out = EB.bands(None, {}, {}, DAY, s)
        self.assertEqual({b.band for b in out}, {"shadow"})
        self.assertTrue(all("no held look" in b.why for b in out))
        program = P.BY_ID["EVL-ERN-READ-O1"]
        b = EB.band_of(program, None, {"k": 1, "passed": 1}, [], DAY, s)
        self.assertEqual((b.band, b.since_day), ("probe", DAY.isoformat()))
        self.assertEqual(EB.band_of(program, None, {"k": 2, "passed": 0}, [], DAY, s).band, "shadow")

    def test_the_150_dollar_line_demotes_for_20_sessions_and_100_negative_events_retire_for_good(self):
        s = EB.settings()
        program = P.BY_ID["EVL-ERN-READ-O1"]
        live = {"band": "probe", "since_day": "2026-10-30"}
        losses = [self.close("-80"), self.close("-71")]
        b = EB.band_of(program, live, {"k": 1, "passed": 1}, losses, DAY, s)
        self.assertEqual(b.band, "demoted")
        last = DAY
        for _ in range(19):
            last = ES.next_session(last)
        self.assertEqual(b.until_day, last.isoformat(), "20 sessions in shadow, today the first")
        held = {"band": "demoted", "until_day": b.until_day, "why": b.why}
        self.assertEqual(EB.band_of(program, held, {"k": 1, "passed": 1}, losses, last, s).band, "demoted")
        after = ES.next_session(last)
        self.assertEqual(EB.band_of(program, held, {"k": 1, "passed": 1}, losses, after, s).band, "probe",
                         "back, its last held look passed")
        self.assertEqual(EB.band_of(program, held, {"k": 2, "passed": 0}, losses, after, s).band, "shadow")
        self.assertEqual(EB.band_of(program, live, {"k": 1, "passed": 1}, [self.close("-149")], DAY, s).band, "probe",
                         "-$149 is above the line")
        bad = [self.close("-1") for _ in range(100)]
        r = EB.band_of(program, {"band": "probe"}, {"k": 1, "passed": 1}, bad, DAY, s)
        self.assertEqual(r.band, "retired")
        self.assertEqual(EB.band_of(program, {"band": "retired", "why": r.why}, {"k": 3, "passed": 1}, [], DAY, s).band,
                         "retired", "for good: a new version must be registered")

    def test_sized_after_150_events_with_the_80_percent_bound_above_zero(self):
        s = EB.settings()
        program = P.BY_ID["EVL-ERN-READ-O1"]
        days = []
        d = dt.date(2026, 6, 1)
        while len(days) < 160:
            if ES.is_session(d):
                days.append(d.isoformat())
            d += dt.timedelta(days=1)
        good = [EB.Close(day, D("2.00") if i % 3 else D("-1.00"), D("100"), day, f"{i:010d}") for i, day in enumerate(days)]
        self.assertEqual(EB.band_of(program, {"band": "probe"}, {"k": 1, "passed": 1}, good[:149], DAY, s).band, "probe")
        self.assertEqual(EB.band_of(program, {"band": "probe"}, {"k": 1, "passed": 1}, good, DAY, s).band, "sized")
        self.assertEqual(s.share("sized"), D("0.10"))
        self.assertEqual(s.max_open("sized"), 8)

    def test_seats_go_in_the_tables_order_and_nobody_trading_loses_one(self):
        s = dataclasses.replace(EB.settings(), seats=2)

        class OneLane:
            def __init__(self):
                self.db = None

        looks = {p.id: {"k": 1, "passed": 1} for p in EB.SEATABLE}
        with mock.patch.object(EB, "last_held_look", lambda lane, program, version: looks.get(program)):
            out = {b.program: b for b in EB.bands(OneLane(), {}, {}, DAY, s)}
            self.assertEqual(sorted(p for p, b in out.items() if b.live), ["EVL-ERN-REACT-C1", "EVL-ERN-READ-O1"])
            self.assertIn("no free seat", out["EVL-8K-READ-O1"].why)
            held = {("EVL-NEWS-REACT-ON", 1): {"band": "probe", "since_day": "2026-11-02"}}
            out = {b.program: b for b in EB.bands(OneLane(), held, {}, DAY, s)}
            self.assertEqual(sorted(p for p, b in out.items() if b.live), ["EVL-ERN-READ-O1", "EVL-NEWS-REACT-ON"],
                             "the program trading keeps its seat; one free seat, by the tables' order")
            off = dataclasses.replace(s, enabled=False)
            out = {b.program: b for b in EB.bands(OneLane(), held, {}, DAY, off)}
            self.assertEqual([p for p, b in out.items() if b.live], ["EVL-NEWS-REACT-ON"], "off: nobody new")


# ------------------------------------------------------------------------------------------------------- the picks
class ThePicks(EventTest):
    def test_only_events_stored_and_verdicts_answered_before_the_decision_count(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        earnings(h.lane, "a-2", CIK2, "BETA", received=iso(DAY, 9, 16))           # stored after 09:15
        earnings(h.lane, "a-3", CIK3, "GAMA", answered=iso(DAY, 9, 15) + "")       # answered after 09:15 (below)
        h.lane.st.db.execute("UPDATE verdicts SET answered_at=? WHERE event='8k:a-3'",
                             (LS.iso(dt.datetime(2026, 11, 4, 9, 15, 1, tzinfo=NY)),))
        lane = EB.open_lane(self.root)
        self.addCleanup(lane.close)
        moment = dt.datetime.fromtimestamp(ES.event_moments(DAY).open_decide, UTC)
        picks = EB.picks(lane, P.BY_ID["EVL-ERN-READ-O1"], DAY, decided_at=moment)
        self.assertEqual([p.symbol for p in picks], ["ACME"])
        self.assertEqual(picks[0].prev_close, D("40.0"))
        # The shadow rule decides all three (the store as it stands later): real money only what it could know.
        later = moment + dt.timedelta(hours=1)
        self.assertEqual(sorted(p.symbol for p in EB.picks(lane, P.BY_ID["EVL-ERN-READ-O1"], DAY, decided_at=later)),
                         ["ACME", "BETA", "GAMA"])

    def test_the_lanes_own_intents_of_today_are_this_decision_and_an_earlier_one_holds_the_issuer(self):
        """The book waits for the lane's own decision of the auction, which has written TODAY'S intents by then: they are
        this decision's picks, never a holding (the shadow's `_held_recently` reads them as one: it asks before it
        writes). An earlier decision's position in the issuer, within 5 sessions, holds it."""
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        earnings(h.lane, "a-2", CIK2, "BETA")
        program = P.BY_ID["EVL-ERN-READ-O1"]
        h.lane.intent(program.id, "8k:a-1", "ACME", CIK, DAY, DAY)          # the lane's decision of today
        h.lane.intent(program.id, "8k:a-2", "BETA", CIK2, DAY, DAY)
        h.lane.intent(program.id, "8k:old", "BETA", CIK2, PRIOR, PRIOR)     # an earlier decision's BETA position
        lane = EB.open_lane(self.root)
        self.addCleanup(lane.close)
        moment = dt.datetime.fromtimestamp(ES.event_moments(DAY).open_decide, UTC)
        self.assertEqual([p.symbol for p in EB.picks(lane, program, DAY, decided_at=moment)], ["ACME"])
        self.assertTrue(P._held_recently(lane, program, CIK, DAY), "the shadow's own rule reads today's intent as held")
        self.assertFalse(EB.held_recently(lane, program, CIK, DAY))
        self.assertTrue(EB.held_recently(lane, program, CIK2, DAY))
        h.lane.st.db.execute("UPDATE intents SET status='skipped:x' WHERE event='8k:old'")
        self.assertFalse(EB.held_recently(lane, program, CIK2, DAY), "a skipped intent held nothing")
        self.assertEqual([p.symbol for p in EB.picks(lane, program, DAY, decided_at=moment)], ["ACME", "BETA"])

    def test_every_seatable_program_reads_its_own_window_and_rule(self):
        """Each of the nine seatable rows through `picks` on the store's own rows (invented): its window, its event, its
        verdict or reaction or purchase, its universe row."""
        h = self.harness()
        cik = {name: f"{i:010d}" for i, name in enumerate(("ERN", "EKA", "OTH", "NWS", "GUI", "INS", "DAY", "RCT"), 11)}
        for name, c in cik.items():
            h.lane.universe(DAY, name, c, 40.0)
        h.lane.filing("e-1", cik["ERN"], accepted=iso(PRIOR, 16, 30))                          # READ-O1
        h.lane.verdict("e-1", 3, answered=iso(PRIOR, 16, 35))
        h.lane.filing("o-1", cik["OTH"], accepted=iso(PRIOR, 17, 0), items=("8.01",))         # 8K-READ-O1
        h.lane.verdict("o-1", 2, answered=iso(PRIOR, 17, 5))
        h.lane.article("n-1", "NWS", knowable=iso(DAY, 7, 30))                                # NEWS-READ-O1
        h.lane.verdict("n-1", 2, answered=iso(DAY, 7, 35), news=True)
        h.lane.filing("g-1", cik["GUI"], accepted=iso(PRIOR, 18, 0))                          # ERN-GUIDE-O1
        h.lane.verdict("g-1", 1, answered=iso(PRIOR, 18, 5), guidance="raised")
        h.lane.insider_buy("f-1", cik["INS"], accepted=iso(PRIOR, 17, 30), usd=60_000.0)        # INS-BUY-O1
        h.lane.filing("k-1", cik["EKA"], accepted=iso(DAY, 11, 0))                            # ERN-REACT-C1 and -ON
        h.lane.article("d-1", "DAY", knowable=iso(DAY, 11, 0))                                # NEWS-READ-ON
        h.lane.verdict("d-1", 2, answered=iso(DAY, 11, 5), news=True)
        h.lane.article("r-1", "RCT", knowable=iso(DAY, 12, 0))                                # NEWS-REACT-ON
        lane = EB.open_lane(self.root)
        self.addCleanup(lane.close)
        em = ES.event_moments(DAY)
        open_at = dt.datetime.fromtimestamp(em.open_decide, UTC)
        close_at = dt.datetime.fromtimestamp(em.close_decide, UTC)
        moves = {"EKA": 1.05, "RCT": 1.06, "DAY": 0.99}
        react = lambda row, uni: moves.get(uni["symbol"])  # noqa: E731
        got = {p.id: [x.symbol for x in EB.picks(lane, p, DAY, decided_at=open_at if p.entry_at == "open" else close_at,
                                                  reaction=react)] for p in EB.SEATABLE}
        self.assertEqual(got, {"EVL-ERN-READ-O1": ["ERN"], "EVL-ERN-REACT-C1": ["EKA"], "EVL-8K-READ-O1": ["OTH"],
                               "EVL-NEWS-READ-O1": ["NWS"], "EVL-ERN-REACT-ON": ["EKA"], "EVL-ERN-GUIDE-O1": ["GUI"],
                               "EVL-INS-BUY-O1": ["INS"], "EVL-NEWS-READ-ON": ["DAY"], "EVL-NEWS-REACT-ON": ["RCT"]})
        [buy] = EB.picks(lane, P.BY_ID["EVL-INS-BUY-O1"], DAY, decided_at=open_at)
        self.assertEqual(buy.rank, 60_000.0, "ranked by its purchase value")
        both = EB.one_name_an_auction({p: [x for x in EB.picks(lane, P.BY_ID[p], DAY, decided_at=close_at,
                                                                 reaction=react)]
                                       for p in ("EVL-ERN-REACT-ON", "EVL-ERN-REACT-C1")})
        self.assertEqual(({k: [x.symbol for x in v] for k, v in both.items()}),
                         {"EVL-ERN-REACT-C1": ["EKA"], "EVL-ERN-REACT-ON": []},
                         "one name at one auction: PREREG-EVL-1's C1 before PREREG-EVL-2's REACT-ON")

    def test_the_rule_ranking_the_issuer_rule_and_one_name_an_auction(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME", score=2)
        earnings(h.lane, "a-2", CIK2, "BETA", score=3)
        earnings(h.lane, "a-3", CIK3, "GAMA", score=1)          # under the READ rule's 2
        lane = EB.open_lane(self.root)
        self.addCleanup(lane.close)
        moment = dt.datetime.fromtimestamp(ES.event_moments(DAY).open_decide, UTC)
        picks = EB.picks(lane, P.BY_ID["EVL-ERN-READ-O1"], DAY, decided_at=moment)
        self.assertEqual([p.symbol for p in picks], ["BETA", "ACME"], "score 3 first, then 2; score 1 not taken")
        held = EB.picks(lane, P.BY_ID["EVL-ERN-READ-O1"], DAY, decided_at=moment, held=lambda cik: cik == CIK2)
        self.assertEqual([p.symbol for p in held], ["ACME"], "an issuer held by real money is skipped")
        both = EB.one_name_an_auction({"EVL-ERN-GUIDE-O1": picks, "EVL-ERN-READ-O1": picks})
        self.assertEqual([p.symbol for p in both["EVL-ERN-READ-O1"]], ["BETA", "ACME"], "PREREG-EVL-1's row first")
        self.assertEqual(both["EVL-ERN-GUIDE-O1"], [], "the later row's picks of the same names are skipped")


# ------------------------------------------------------------------------------------------------------- the day
class TheDay(EventTest):
    def test_a_passing_program_buys_at_the_open_and_sells_at_the_close_in_whole_shares(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME", prev_close=40.0)
        h.lane.intent("EVL-ERN-READ-O1", "8k:a-1", "ACME", CIK, DAY, DAY)       # the lane's own decision came first
        self.seated(h)
        h.symbol("ACME", last=41.0, sd=0.02)
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("42.00")
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("43.00")
        h.tick(9, 15)
        [buy] = h.event_intents("buy")
        self.assertEqual((buy["status"], buy["tif"], buy["otype"], buy["limit_px"], buy["exit_day"], buy["exit_at"]),
                         ("planned", "opg", "limit", "50.00", DAY.isoformat(), "close"))
        self.assertEqual(D(buy["weight"]), D("0.10"), "max(0.10, 1.65 x 2%)")
        self.assertEqual(h.venue.client.lists, [{"day": DAY.isoformat(), "symbols": ["ACME"]}], "the eligible list")
        inst = h.book._instance("EVL-ERN-READ-O1@1:r")
        self.assertEqual((inst.kind, inst.lane, inst.band), ("event", "event", "probe"))
        h.tick(9, 16)
        [body] = h.bodies()
        self.assertEqual(body, {"symbol": "ACME", "qty": "2", "side": "buy", "type": "limit", "limit_price": "50.00",
                                "time_in_force": "opg", "client_order_id": body["client_order_id"]},
                         "5% of E=$2,000 at the $50.00 limit: two whole shares, limit-on-open")
        h.tick(9, 31)
        [lot] = h.lots()
        self.assertEqual((lot.qty, lot.entry_px, lot.lane, lot.info["evl_exit"]),
                         (D(2), D("42.000000"), "event", {"day": DAY.isoformat(), "at": "close", "rung": 0}))
        figures = L.probe_figures(h.state.rows, weights={"etf": D("0.20"), "stock": D("0.40")})
        self.assertEqual(figures.open_risk, D("0.10") * D(2) * D("42.000000"), "the event lot's own weight, not 0.40")
        h.tick(9, 33)
        self.assertEqual(h.event_intents("buy")[0]["status"], "done")
        h.tick(15, 46)
        [sale] = h.event_intents("sell")
        self.assertEqual((sale["tif"], sale["otype"], sale["lid"], sale["rung"]), ("cls", "market", lot.lid, 0))
        h.tick(15, 47)
        body = h.bodies()[-1]
        self.assertEqual(body, {"symbol": "ACME", "qty": "2", "side": "sell", "type": "market", "time_in_force": "cls",
                                "client_order_id": body["client_order_id"]}, "a market-on-close sale of what it holds")
        h.tick(16, 1)
        h.tick(16, 3)
        [lot] = h.lots()
        self.assertEqual((lot.status, lot.exit_px, lot.exit_at, lot.exit_day), ("closed", D("43.000000"), "close",
                                                                               DAY.isoformat()))
        self.assertEqual(h.event_intents("sell")[0]["status"], "done")
        self.assertEqual([k for k, _ in h.events if k == "equity.event_decide"], ["equity.event_decide"] * 2)

    def test_the_one_share_rule_and_the_ten_percent_wall(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME", prev_close=150.0)        # limit 187.50 over a $100 target: one share
        earnings(h.lane, "a-2", CIK2, "BETA", prev_close=170.0)       # limit 212.50: over 10% of $2,000
        self.seated(h)
        for symbol in ("ACME", "BETA"):
            h.symbol(symbol, last=150.0)
        h.tick(9, 15)
        h.tick(9, 16)
        sent = {b["symbol"]: b for b in h.bodies()}
        self.assertEqual((sent["ACME"]["qty"], sent["ACME"]["limit_price"]), ("1", "187.50"))
        self.assertNotIn("BETA", sent)
        beta = next(r for r in h.event_intents("buy") if r["symbol"] == "BETA")
        self.assertEqual(beta["status"], "refused")
        self.assertIn("no whole share fits", beta["why"])

    def test_the_kill_switch_the_kinds_switch_and_the_auction_proof_stop_buys_never_sales(self):
        for stop in ("kill", "switch", "proof", "gateway"):
            with self.subTest(stop=stop):
                self.tmp = tempfile.TemporaryDirectory()
                self.addCleanup(self.tmp.cleanup)
                self.root = Path(self.tmp.name)
                h = self.harness()
                earnings(h.lane, "a-1", CIK, "ACME")
                self.seated(h)
                h.symbol("ACME", last=41.0)
                block = {"kill": "kill switch", "switch": "equity_money.event.enabled is false",
                         "proof": "auction paper proof's BUY stage", "gateway": "the refused buy"}[stop]
                patch = mock.patch.dict(CONSTITUTION["equity_money"]["event"], {"enabled": False}) \
                    if stop == "switch" else mock.patch.dict({}, {})
                with patch:
                    if stop == "kill":
                        h.kill = True
                    if stop == "proof":
                        h.auction.ok = False
                    if stop == "gateway":
                        h.venue.gateway_refuses = "stock_event_buys"
                        earnings(h.lane, "a-2", CIK2, "BETA")         # two refused buys: one alert
                    h.tick(9, 15)
                    h.tick(9, 16)
                    h.tick(9, 31)
                    h.tick(9, 33)
                    buys = h.event_intents("buy")
                    if stop == "switch":
                        self.assertEqual(buys, [], "the kind off: no pick planned")
                    else:
                        self.assertIn(block, buys[0]["why"])
                        self.assertIn(buys[0]["status"], ("missed", "refused"))
                    self.assertEqual(h.lots(), [])
                    said = [text for level, text in h.alerts if "STOCK_EVENT_BUYS is off" in text]
                    self.assertEqual(len(said), 1 if stop == "gateway" else 0, "the owner's step, said once")

    def test_an_exit_is_never_held_by_the_kinds_switch_or_the_proof_only_by_the_kill_switch(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.seated(h)
        h.symbol("ACME", last=41.0)
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("42.00")
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("43.00")
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
            h.tick(hh, mm)
        self.assertEqual(len(h.lots(open_only=True)), 1)
        h.auction.ok, h.auction.failed = False, "the SELL stage failed"
        with mock.patch.dict(CONSTITUTION["equity_money"]["event"], {"enabled": False}):
            h.kill = True
            h.tick(15, 46)
            h.tick(15, 47)
            self.assertIn("kill switch", h.event_intents("sell")[0]["why"])
            h.kill = False
            h.tick(15, 48)
            self.assertEqual(h.bodies()[-1]["time_in_force"], "cls")
            h.tick(16, 1)
        self.assertEqual(h.lots()[0].status, "closed")

    def test_the_fallback_ladder_closes_then_a_day_sale(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.seated(h)
        h.symbol("ACME", last=41.0)
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("42.00")       # no close print: a halt
        h.day(DAY)
        lot = h.lots()[0]
        self.assertIn(lot.status, ("open", "closing"), "unsold: still held (closing marks the sale it sent)")
        self.assertEqual(lot.info["evl_exit"]["rung"], 1)
        self.assertEqual(lot.info["evl_exit"]["day"], NEXT.isoformat())
        self.assertEqual(L.event_lot_weight(lot.row()), D("0.40"), "past its exit: the stricter weight")
        self.assertTrue(any("rung 1 of the ladder" in text for _, text in h.alerts))
        day = NEXT
        for rung in range(2, EB.LADDER_CLOSES + 2):
            h.lane.decided(day, "open")
            h.lane.decided(day, "close")
            h.day(day)
            lot = h.book._lot(lot.lid)
            self.assertEqual(lot.info["evl_exit"]["rung"], rung)
            day = ES.next_session(day)
        self.assertEqual(lot.info["evl_exit"]["at"], "late")
        late = [i for i in h.intents() if i.tag == EB.LATE_TAG]
        self.assertEqual(len(late), 1, "the ladder's last rung: a day sale in the open window, the normal path")
        self.assertEqual((late[0].at, late[0].exec_day), ("open", lot.info["evl_exit"]["day"]))
        self.assertTrue(any("found no closing cross" in text for level, text in h.alerts if level == "error"))
        sells = [b for b in h.bodies() if b["side"] == "sell"]
        self.assertEqual({b["time_in_force"] for b in sells}, {"cls"})
        self.assertEqual(len(sells), 1 + EB.LADDER_CLOSES)

    def test_an_overnight_program_buys_at_the_close_and_sells_at_the_next_open(self):
        h = self.harness()
        # EVL-ERN-REACT-ON: an earnings 8-K accepted on DAY during the session, its 15:29 ET minute at +5% over the
        # PRIOR session's close.
        h.lane.filing("r-1", CIK, accepted=iso(DAY, 11, 0), received=iso(DAY, 11, 1))
        h.lane.universe(DAY, "ACME", CIK, 40.0)
        h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('ACME', ?, 'raw', 40, "
                             "40, 40, 40.0, 1e6, 'x')", (PRIOR.isoformat(),))
        h.lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('ACME', ?, '1530', "
                             "42.0, 'x', 'sip-1min', 'x')", (DAY.isoformat(),))
        self.seated(h, "EVL-ERN-REACT-ON")
        h.symbol("ACME", last=42.0)
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("42.50")
        h.venue.prints[("ACME", NEXT.isoformat(), "open")] = D("43.10")
        for hh, mm in ((9, 15), (15, 46), (15, 47), (16, 1), (16, 3)):
            h.tick(hh, mm)
        [buy] = h.event_intents("buy")
        self.assertEqual((buy["tif"], buy["exit_day"], buy["exit_at"]), ("cls", NEXT.isoformat(), "open"))
        self.assertEqual(h.bodies()[0]["time_in_force"], "cls")
        [lot] = h.lots()
        self.assertEqual(lot.info["evl_exit"], {"day": NEXT.isoformat(), "at": "open", "rung": 0})
        h.lane.decided(NEXT, "open")
        for hh, mm in ((9, 15), (9, 16), (9, 31)):
            h.tick(hh, mm, day=NEXT)
        sale = h.bodies()[-1]
        self.assertEqual((sale["side"], sale["type"], sale["time_in_force"]), ("sell", "market", "opg"),
                         "a market-on-open sale in the 09:16-09:27 window")
        self.assertEqual((h.lots()[0].status, h.lots()[0].exit_px), ("closed", D("43.100000")))

    def test_the_old_lanes_stay_exits_only_while_an_event_program_buys(self):
        """PREREG-EVL-1 section 8 closed the index ETF and options programs to new entries: `equity_money.enabled` stays
        False and the event kind has its own switch. A seated ETF program's planned buy is refused ("exits only")
        beside an event program's buy that goes."""
        h = self.harness(enabled=False)
        earnings(h.lane, "a-1", CIK, "ACME")
        self.seated(h)
        h.symbol("ACME", last=41.0)
        etf = h.instance()
        h.intent(etf, "buy", symbol="SPY", share="0.5", exec_day=DAY, decided=PRIOR)
        h.tick(9, 15)
        h.tick(9, 16)
        h.tick(9, 31)
        h.tick(9, 46)
        self.assertEqual([b["symbol"] for b in h.bodies()], ["ACME"], "the event buy alone")
        spy = [i for i in h.intents(kind="buy") if i.symbol == "SPY"][0]
        self.assertEqual(spy.status, "missed")
        self.assertIn("equity_money.enabled is false: exits only", spy.why)
        self.assertEqual(h.book._open_block(lambda opening=True: None, etf, lambda: False),
                         "equity_money.enabled is false: exits only")
        inst = h.book._instance("EVL-ERN-READ-O1@1:r")
        self.assertIsNone(h.book._open_block(lambda opening=True: None, inst, lambda: False),
                          "the event program's own gates pass with the old lanes' switch off")

    def test_the_eligible_list_goes_only_for_a_buy_and_a_list_the_gateway_lacks_holds_it(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        h.symbol("ACME", last=41.0)
        h.lane.decided(DAY, "open")
        h.lane.decided(DAY, "close")
        h.day(DAY)
        self.assertEqual((h.venue.client.lists, h.bodies()), ([], []), "every program in shadow: nothing asked, sent")
        h.lane.look("EVL-ERN-READ-O1")
        earnings(h.lane, "a-2", CIK2, "BETA")
        h.lane.st.db.execute("UPDATE filings SET accepted_at=?, knowable_at=?, received_at=? WHERE accession='a-2'",
                             (iso(DAY, 16, 30), iso(DAY, 16, 40), iso(DAY, 16, 31)))
        h.lane.universe(NEXT, "BETA", CIK2, 40.0)
        h.lane.decided(NEXT, "open")
        h.venue.client.fail = True
        h.tick(9, 15, day=NEXT)
        h.tick(9, 16, day=NEXT)
        [buy] = h.event_intents("buy")
        self.assertEqual((buy["symbol"], buy["why"]), ("BETA", "the day's eligible list is not at the gateway yet"))
        self.assertEqual(h.bodies(), [])
        h.venue.client.fail = False
        h.tick(9, 17, day=NEXT)
        self.assertEqual([b["symbol"] for b in h.bodies()], ["BETA"])
        self.assertEqual([d["day"] for d in h.venue.client.lists], [NEXT.isoformat()] * 3, "tried each minute")
        self.assertEqual(h.state.get("eq_event_list")["count"], 1)

    def test_end_stale_leaves_an_auction_order_of_its_own_session_alone(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.seated(h)
        h.symbol("ACME", last=41.0)
        h.tick(9, 15)
        h.tick(9, 16)
        h.tick(9, 25)
        self.assertEqual(h.venue.cancels, [], "queued for the open: never cancelled")
        [order] = h.orders()
        self.assertEqual((order.tif, order.otype, order.status), ("opg", "limit", "working"))

    def test_a_working_event_buy_counts_its_own_weight_in_the_budget(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.seated(h)
        h.symbol("ACME", last=41.0, sd=None)              # no sigma: the stricter 0.40
        h.tick(9, 15)
        h.tick(9, 16)
        figures = L.probe_figures(h.state.rows, weights={"etf": D("0.20"), "stock": D("0.40")})
        self.assertEqual(figures.open_risk, D("0.40") * D(2) * D("50.00"))
        self.assertEqual(figures.programs, 1)

    def test_no_lane_on_the_house_plans_nothing_and_says_nothing(self):
        h = self.harness()
        import shutil

        h.lane.st.close()
        shutil.rmtree(self.root / "events")
        h.day(DAY)
        self.assertEqual(h.bodies(), [])
        self.assertEqual([k for k, _ in h.events if k.startswith("equity.event")], [])
        self.assertEqual(h.book.health()["events"]["programs"][0]["band"], "shadow")


    def test_unsold_twenty_sessions_after_its_exit_it_is_at_zero_for_the_budget(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.seated(h)
        h.symbol("ACME", last=41.0)
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("42.00")       # and never a close print again: a halt
        h.venue.fill = "none"                                                # nor a day trade
        h.day(DAY)
        lid = h.lots()[0].lid
        day, seen = NEXT, []
        for _ in range(EB.ZERO_AFTER + 2):
            h.lane.decided(day, "open")
            h.lane.decided(day, "close")
            h.day(day)
            plan = h.book._lot(lid).info["evl_exit"]
            seen.append((day, plan.get("zero")))
            if plan.get("zero"):
                break
            day = ES.next_session(day)
        lot = h.book._lot(lid)
        self.assertNotEqual(lot.status, "closed")
        self.assertEqual(ES.sessions_between(DAY, lot.info["evl_exit"]["zero"]), EB.ZERO_AFTER,
                         "at 0 once the 20th session after its planned exit has closed")
        self.assertIsNone(seen[-2][1])
        self.assertEqual(lot.info["evl_exit"]["first"], DAY.isoformat())
        self.assertEqual(L.event_lot_weight(lot.row()), D(1), "its whole value counts as lost")
        figures = L.probe_figures(h.state.rows, weights={"etf": D("0.20"), "stock": D("0.40")})
        self.assertEqual(figures.open_risk, lot.qty * L._price(lot.row()))
        self.assertTrue(any("is still held 20 sessions after its planned exit" in text for level, text in h.alerts
                            if level == "error"))

    def test_an_event_close_counts_in_the_loss_budget_at_probe_or_sized(self):
        h = self.harness()
        inst = L.Instance("EVL-ERN-READ-O1@1:r", "EVL-ERN-READ-O1", 1, L.EVENT_LANE, "", "", {}, "sized", False, 1,
                          created_at=h.clock(), kind=L.EVENT_KIND)
        h.book._save_instance(inst)
        etf = h.instance()
        for owner, lane, symbol in ((inst, L.EVENT_LANE, "ACME"), (etf, "beta", "SPY")):
            lot = L.Lot(h.book._next("eq_lots", "lid"), owner.id, owner.family, owner.version, lane, symbol, "stock",
                        D(0), D(2), D("40"), D("80"), "open", opened_at=at(PRIOR, 9, 30), opened_day=PRIOR.isoformat(),
                        cash=D("-7.50"), probe=False, status="closed", exit_px=D("36.25"), exit_at="close",
                        exit_day=PRIOR.isoformat(), closed_at=at(PRIOR, 16, 0))
            h.book._save_lot(lot)
        figures = L.probe_figures(h.state.rows, weights={"etf": D("0.20"), "stock": D("0.40")})
        self.assertEqual(figures.closes, ((PRIOR.isoformat(), D("-7.50")),),
                         "the Sized event lot's loss is the budget's; a Sized ETF lot's stays outside it, as before")


# ------------------------------------------------------------------------------------------------------- the twins
class FakeStore:
    def __init__(self):
        self.kv: dict = {}

    def get(self, key, default=None):
        return json.loads(json.dumps(self.kv.get(key, default)))

    def put(self, key, value):
        self.kv[key] = json.loads(json.dumps(value))


class TheTwins(EventTest):
    def lot(self, **over) -> dict:
        row = {"lid": 7, "instance": "EVL-ERN-READ-O1@1:r", "family": "EVL-ERN-READ-O1", "version": 1, "lane": "event",
               "symbol": "ACME", "class": "stock", "qty": "0", "opened_qty": "2", "entry_px": "42.00",
               "entry_notional": "84.00", "entry_at": "open", "fees": "0.02", "div": "0", "status": "closed",
               "exit_px": "43.00", "exit_at": "close", "exit_day": DAY.isoformat(), "opened_day": DAY.isoformat(),
               "closed_at": at(DAY, 16, 1), "cash": "1.98", "reason": "evl_exit", "info": json.dumps({"exit_qty": "2"})}
        row.update(over)
        return row

    def marks(self, open_px=41.9, close_px=43.05, first_px=None) -> dict:
        out = {(DAY.isoformat(), "open"): {"px": open_px, "source": "sip:Q:O,Q"},
               (DAY.isoformat(), "close"): {"px": close_px, "source": "sip:Q:6,M"}}
        if first_px is not None:
            out[(NEXT.isoformat(), "first")] = {"px": first_px, "source": "sip:K:@"}
        return out

    def test_the_gap_per_side_is_signed_worse_positive_against_the_shadows_auction_prices(self):
        rec = TW.event_twin(self.lot(), self.marks(), settled=False, at=at(DAY, 21, 0))
        self.assertEqual((rec["status"], rec["final"], rec["kind"]), ("priced", True, "event"))
        self.assertEqual(rec["entry_gap_bp"], round((42.0 / 41.9 - 1) * 1e4, 2), "paid more than the open print")
        self.assertEqual(rec["exit_gap_bp"], round((1 - 43.0 / 43.05) * 1e4, 2), "received less than the close print")
        self.assertGreater(rec["entry_gap_bp"], 0)
        self.assertGreater(rec["exit_gap_bp"], 0)
        self.assertEqual((rec["entry_print"], rec["exit_print"]), (41.9, 43.05))
        self.assertLess(rec["gap_bp"], 0, "E1's sense: live minus the shadow, a side, negative when real did worse")
        better = TW.event_twin(self.lot(entry_px="41.80", exit_px="43.10"), self.marks(), settled=False)
        self.assertLess(better["entry_gap_bp"], 0)
        self.assertLess(better["exit_gap_bp"], 0)

    def test_a_missing_print_waits_until_settled_and_a_print_the_shadow_found_none_of_is_final(self):
        wait = TW.event_twin(self.lot(), {(DAY.isoformat(), "open"): {"px": 41.9, "source": "s"}}, settled=False)
        self.assertEqual((wait["status"], wait["final"]), ("no_bar", False))
        self.assertIn("no shadow auction price", wait["why"])
        self.assertTrue(TW.event_twin(self.lot(), {}, settled=True)["final"])
        none = TW.event_twin(self.lot(), self.marks(close_px=None), settled=False)
        self.assertEqual((none["status"], none["final"]), ("no_bar", True))
        self.assertIn("printed no auction price", none["why"])
        self.assertEqual(TW.event_twin(self.lot(), None, settled=False)["final"], False, "no lane store: it waits")

    def test_the_ladders_late_sale_is_set_beside_the_sessions_first_trade(self):
        late = self.lot(reason="evl_late", exit_at="open", exit_day=NEXT.isoformat(), exit_px="40.00")
        rec = TW.event_twin(late, self.marks(first_px=40.1), settled=False)
        self.assertEqual((rec["status"], rec["exit_label"], rec["exit_print"]), ("priced", "first", 40.1))

    def test_the_round_reads_the_lanes_marks_and_keeps_the_record_beside_e1s(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.seated(h)
        h.symbol("ACME", last=41.0)
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("42.00")
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("43.00")
        h.day(DAY)
        [lot] = h.lots()
        self.assertEqual(lot.status, "closed")
        store = FakeStore()
        out = TW.equity_round(self.root, now=at(DAY, 21, 0), store=store)
        self.assertEqual((out["judged"], out["pending"]), ({}, 1), "no print in the lane's store yet: waits")
        for label, px in (("open", 41.9), ("close", 43.05)):
            h.lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('ACME', ?, ?, "
                                 "?, 't', 'sip:Q:x', 'x')", (DAY.isoformat(), label, px))
        out = TW.equity_round(self.root, now=at(DAY, 21, 5), store=store)
        self.assertEqual(out["judged"], {"priced": 1})
        rec = store.kv[TW.EQUITY_TWINS_KEY][f"eq:{lot.lid}"]
        self.assertEqual((rec["kind"], rec["entry_print"], rec["exit_print"]), ("event", 41.9, 43.05))
        self.assertEqual(rec["entry_gap_bp"], round((42.0 / 41.9 - 1) * 1e4, 2))


# ------------------------------------------------------------------------------------------------------- the readers
class TheReaders(EventTest):
    """The swarm era's readers of the live book leave an event program's instance and lots out (release R2): the
    forward register (no forward program, no identity watch), the forward twins (no replay of a pre-registered rule),
    FW7 and FW9 (no 16:30 decide, no forward twin), and the old Done meter's closes (the event lane's own reader
    counts events). The loss budget reads them: test_an_event_close_counts_in_the_loss_budget_at_probe_or_sized."""

    def book(self) -> Harness:
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")
        self.seated(h)
        h.symbol("ACME", last=41.0)
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("42.00")
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("43.00")
        h.day(DAY)
        etf = h.instance()
        h.lot(etf, opened=PRIOR)
        self.assertEqual({i.lane for i in h.book._instances()}, {"event", "beta"})
        return h, etf

    def test_the_forward_register_and_the_forward_twins_never_see_an_event_program(self):
        from league.ops import forward_register as FR
        from league.ops import forward_twins as FT

        h, etf = self.book()
        path = self.root / "live.sqlite"
        self.assertEqual([r["lane"] for r in FR.live_instances(path)], ["beta"])
        book = FT.read_book(path)
        self.assertEqual([r["lane"] for r in book["instances"]], ["beta"])
        self.assertEqual(list(book["lots"]), [etf.id])
        self.assertTrue(h.state.rows("SELECT 1 AS x FROM eq_intents WHERE instance='EVL-ERN-READ-O1@1:r'"))
        self.assertNotIn("EVL-ERN-READ-O1@1:r", set(book["intents"]) | set(book["exits"]))

    def test_fw7_fw9_and_the_old_done_meter_never_count_an_event_program(self):
        from league.ops import dlane_report as DR
        from league.ops import forward_report as FW

        h, etf = self.book()
        instances, lots = FW._book_instances(self.root)
        self.assertEqual([r["id"] for r in instances], [etf.id])
        self.assertEqual(set(lots), {etf.id})
        rows = [dict(r) for r in h.state.rows("SELECT * FROM eq_lots ORDER BY lid")]
        self.assertEqual([r["lane"] for r in rows if r["status"] == "closed"], ["event"])
        self.assertEqual(DR.equity_closes(rows, since=0.0), [], "the event lot's close is none of the old meters'")
        self.assertEqual(DR.EVENT_LANE, EB.LANE)


# ------------------------------------------------------------------------------------------------------- the proof
class Paper:
    """The practice account at the proof's interface (league/live/venue.py `Account`): orders queued for their
    auctions and filled at `px` when the clock passes them."""

    def __init__(self, clock, *, held="0"):
        self.clock, self.held, self.orders, self.px = clock, D(held), [], {"open": D("70.00"), "close": D("71.00")}
        self.fill = True

    def positions(self):
        self._advance()
        return [{"symbol": PR.SYMBOL, "qty": str(self.held), "side": "long"}] if self.held else []

    def submit(self, body, *, exit):
        self.orders.append({**body, "status": "new", "filled_qty": "0", "id": str(uuid.uuid4()),
                            "_day": dt.datetime.fromtimestamp(self.clock(), NY).date()})
        return Submitted(True, {"id": self.orders[-1]["id"], "status": "new"}, "", status=200)

    def order_by_client_id(self, cid):
        self._advance()
        for o in self.orders:
            if o["client_order_id"] == cid:
                return {k: v for k, v in o.items() if not k.startswith("_")}
        return None

    def cancel(self, venue_id):
        return True, ""

    def _advance(self):
        for o in self.orders:
            if o["status"] != "new":
                continue
            m = ES.moments(o["_day"])
            kind = "open" if o["time_in_force"] == "opg" else "close"
            if self.clock() < (m.open_at if kind == "open" else m.close_at):
                continue
            if not self.fill:
                o["status"] = "canceled"
                continue
            o.update(status="filled", filled_qty=o["qty"], filled_avg_price=str(self.px[kind]))
            self.held += D(o["qty"]) if o["side"] == "buy" else -D(o["qty"])


class Bars:
    def __init__(self):
        self.trades: list = []

    def bars(self, symbols, *, timeframe, start, end=None, adjustment="raw"):
        return {PR.SYMBOL: [{"t": f"{PRIOR.isoformat()}T05:00:00Z", "c": 64.0}]}

    def _get(self, path, params, what):
        return {"trades": self.trades}


class TheAuctionProof(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = T.Clock(at(DAY, 9, 0))
        self.state = LiveState(Path(self.tmp.name) / "live.sqlite", clock=self.clock)
        self.addCleanup(self.state.close)
        self.paper = Paper(self.clock)
        self.alerts: list = []
        self.proof = PR.AuctionProof(self.state, self.paper, Bars(), clock=self.clock,
                                     alert=lambda level, text: self.alerts.append((level, text)))

    def minute(self, day, hh, mm):
        self.clock.set(at(day, hh, mm))
        return self.proof.step(self.clock(), ES.event_moments(day))

    def test_a_limit_on_open_buy_and_a_market_on_close_sale_of_one_share_pass_both_stages(self):
        self.minute(DAY, 9, 10)
        self.assertEqual(self.paper.orders, [], "nothing before the opg window")
        self.minute(DAY, 9, 16)
        [buy] = self.paper.orders
        self.assertEqual({k: buy[k] for k in ("symbol", "qty", "side", "type", "time_in_force", "limit_price")},
                         {"symbol": PR.SYMBOL, "qty": "1", "side": "buy", "type": "limit", "time_in_force": "opg",
                          "limit_price": "80.00"}, "one share at 1.25 x the previous SIP close")
        self.assertFalse(self.proof.buy_passed())
        self.minute(DAY, 9, 31)
        self.minute(DAY, 9, 32)
        self.assertTrue(self.proof.buy_passed())
        self.assertFalse(self.proof.passed())
        self.minute(DAY, 15, 47)
        sale = self.paper.orders[-1]
        self.assertEqual({k: sale[k] for k in ("side", "type", "time_in_force", "qty")},
                         {"side": "sell", "type": "market", "time_in_force": "cls", "qty": "1"})
        self.minute(DAY, 16, 1)
        self.minute(DAY, 16, 2)
        self.assertTrue(self.proof.passed())
        self.assertEqual(self.proof.status()["stages"]["sell"]["status"], "passed")

    def test_an_unfilled_sale_fails_the_stage_and_new_buys_stop_until_it_passes(self):
        self.minute(DAY, 9, 16)
        self.minute(DAY, 9, 31)
        self.minute(DAY, 9, 32)
        self.assertTrue(self.proof.buy_passed())
        self.paper.fill = False
        self.minute(DAY, 15, 47)
        self.minute(DAY, 16, 1)
        self.minute(DAY, 16, 2)
        self.assertIn("SELL stage failed", self.proof.sell_failed())
        self.assertTrue(any(level == "error" for level, _ in self.alerts))
        self.paper.fill = True
        self.minute(NEXT, 15, 47)
        self.minute(NEXT, 16, 1)
        self.minute(NEXT, 16, 2)
        self.assertEqual(self.proof.sell_failed(), "")
        self.assertTrue(self.proof.passed())

    def test_an_unfilled_open_buy_tries_again_the_next_session(self):
        self.paper.fill = False
        self.minute(DAY, 9, 16)
        self.minute(DAY, 9, 31)
        self.minute(DAY, 9, 40)
        self.assertEqual(self.proof._row()["status"], "waiting")
        self.paper.fill = True
        self.minute(NEXT, 9, 16)
        self.minute(NEXT, 9, 31)
        self.minute(NEXT, 9, 32)
        self.assertTrue(self.proof.buy_passed())


if __name__ == "__main__":
    unittest.main()
