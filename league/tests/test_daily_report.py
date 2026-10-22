"""Release 1019c (the owner's goal of Oct 19, 2026, item 5, and its last line: "Report account-shown profit first, Net
after costs beside it"; PREREG-EVL-1 section 9; the review of r1/alarms, its major 4 and its section-9 minor): THE DAILY
ONE-SCREEN REPORT BY MAIL (league/ops/daily_report.py), sent by the stall job through a fake gateway once a New York day
after the lane's own report job: events, shadow intents, real fills, settled n, account-shown profit and Net after the
MEASURED metered compute by program and band, the costs against the cap with the allowance labelled, the evidence, the
same-risk buy-and-hold and the alarms open; figures only (no symbol, headline or price leaves the House), and nothing of
it in the receipt or stall.json. Every figure is invented; no market price is read."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from league.events import calendar as C
from league.events import programs as P
from league.events import store as ES
from league.ops import budget as B
from league.ops import daily_report as DR
from league.ops import metered as MT
from league.ops import stall as ST
from league.tests.evl_book_fakes import Book, cancel_at_once, entry_why
from league.tests.test_evl_health import CLEAN, StallHarness, backfill_done, et, iso
from league.tests.test_ops_budget import inputs as budget_inputs

MON, TUE, WED, THU = dt.date(2026, 10, 19), dt.date(2026, 10, 20), dt.date(2026, 10, 21), dt.date(2026, 10, 22)
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "daily_report.json"


class Cal:
    """Alpaca's calendar through the gateway: every weekday a full session (invented)."""

    def get_json(self, path, params=None):
        start, end = dt.date.fromisoformat(params["start"]), dt.date.fromisoformat(params["end"])
        out, d = [], start
        while d <= end:
            if d.weekday() < 5:
                out.append({"date": d.isoformat(), "open": "09:30", "close": "16:00"})
            d += dt.timedelta(days=1)
        return out


def synthetic_book(root: Path, day: dt.date = TUE) -> None:
    """The book's live.sqlite for the invented session (league/tests/evl_book_fakes.py): three real buys planned at the
    open and one at the close, every one filled at once (release 1019f's `evl_entries` quiet)."""
    book = Book(root)
    try:
        for at, n in (("open", 3), ("close", 1)):
            for _ in range(n):
                book.buy(day, at, orders=({"status": "filled", "filled": "2", "why": entry_why(at)},))
    finally:
        book.close()


def synthetic_lane(root: Path, day: dt.date = TUE) -> None:
    """A lane store holding one invented session: filings, a news headline, verdicts, version 1 and 2 intents settled with
    invented returns, real fills of two programs (one at probe), the benchmark's invented bars, every receipt that keeps
    the causes quiet at 22:20 ET (release 1019f: the daily-index backfill of the reach done, PREREG-EVL-4's rows of each
    close decided by themselves), the lane's own report receipt, and the book's live.sqlite (`synthetic_book`)."""
    synthetic_book(root, day)
    st = ES.Store(root / "events")
    try:
        backfill_done(st)
        C.refresh(st, Cal(), dt.date(2026, 10, 1), dt.date(2026, 12, 31))
        db = st.db

        def t(hhmm, on=day):
            return iso(et(on, hhmm))
        with st.tx():
            for acc, form, items in (("0001-26-000001", "8-K", '["2.02"]'), ("0001-26-000003", "8-K", '["8.01"]'),
                                     ("0001-26-000005", "4", "[]")):
                db.execute("INSERT INTO filings(accession, form, cik, items, accepted_at, knowable_at, received_at, source, "
                           "status) VALUES(?, ?, '0000000001', ?, ?, ?, ?, 'current', 'fetched')",
                           (acc, form, items, t("08:01"), t("08:11"), t("08:03")))
            db.execute("INSERT INTO news(id, created_at, received_at, knowable_at, source, headline, summary, symbols, live) "
                       "VALUES('1', ?, ?, ?, 'benzinga', 'ACME SURGES ON MIRACLE CURE', 'secret summary', '[\"ACME\"]', 1)",
                       (t("07:00"), t("07:01"), t("07:02")))
            for event, status, usd in (("8k:a", "ok", 0.004), ("8k:b", "ok", 0.006), ("8k:c", "unparsed", 0.003)):
                db.execute("INSERT INTO verdicts(event, prompt_sha, model, asked_at, answered_at, status, usd) VALUES(?, 'p', "
                           "'claude-haiku-4-5-20251001', ?, ?, ?, ?)", (event, t("08:20"), t("08:21"), status, usd))
            rows = (("EVL-ERN-READ-O1", "8k:a", "ACME", 0.012, 0.010), ("EVL-ERN-READ-O1", "8k:b", "BETA", -0.004, -0.006),
                    ("EVL-ERN-READ-O1", "8k:c", "GAMA", 0.002, 0.001), ("EVL-INS-BUY-O1", "f4:x", "DELT", 0.008, 0.005))
            for i, (program, event, sym, r, a) in enumerate(rows):
                db.execute("INSERT OR IGNORE INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench, "
                           "sigma60) VALUES(?, ?, ?, 'Invented Co', 'NASDAQ', 123.45, 2e7, 'SPY', 0.02)",
                           (day.isoformat(), sym, f"{i:010d}"))
                for version in (1, 2) if program == "EVL-ERN-READ-O1" else (2,):
                    db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                               "exit_day, exit_at, mode, status) VALUES(?, ?, ?, ?, ?, ?, ?, 'open', ?, 'close', 'shadow', "
                               "'exited')", (program, version, event, sym, f"{i:010d}", t("09:15"), day.isoformat(),
                                             day.isoformat()))
                    db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, bench, r, b, a, tradable, "
                               "settled_at, status) VALUES(?, ?, ?, 123.45, 124.56, 'SPY', ?, ?, ?, 1, ?, 'settled')",
                               (program, version, event, r, r - a, a, t("20:31")))
            # THE REAL FILLS the House's book wrote back (league/events/bands.py `record_fill`): invented prices.
            fills = (("EVL-ERN-READ-O1", "8k:a", "buy", 2, 50.0, 0.0, "09:30", "learning"),
                     ("EVL-ERN-READ-O1", "8k:a", "sell", 2, 51.0, 0.02, "16:00", "learning"),
                     ("EVL-ERN-READ-O1", "8k:b", "buy", 1, 40.0, 0.0, "09:30", "learning"),
                     ("EVL-ERN-READ-O1", "8k:b", "sell", 1, 39.5, 0.01, "16:00", "learning"),
                     ("EVL-INS-BUY-O1", "f4:x", "buy", 3, 20.0, 0.0, "09:30", "probe"),
                     ("EVL-INS-BUY-O1", "f4:x", "sell", 3, 20.5, 0.03, "16:00", "probe"),
                     ("EVL-ERN-READ-O1", "8k:c", "buy", 1, 30.0, 0.0, "15:50", "learning"))   # still held
            for program, event, side, qty, price, fee, hhmm, band in fills:
                db.execute("INSERT INTO real_fills(program, version, event, side, qty, price, fee, filled_at, band) VALUES(?, "
                           "2, ?, ?, ?, ?, ?, ?, ?)", (program, event, side, qty, price, fee, t(hhmm), band))
            db.execute("INSERT INTO bands(program, version, band, since, why) VALUES('EVL-INS-BUY-O1', 2, 'probe', ?, "
                       "'look 1 passed')", (t("08:00"),))
            for adj, o, c in (("all", 100.0, 101.0), ("raw", 100.0, 101.0)):   # the benchmark's invented bar of the day
                db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('SPY', ?, ?, ?, ?, ?, ?, "
                           "1e6, ?)", (day.isoformat(), adj, o, c, o, c, t("20:31")))
            receipts = (("record", "22:15", CLEAN, day), ("decide-close:" + MON.isoformat(), "15:47", {}, MON),
                        ("decide-close-evl4:" + MON.isoformat(), "15:48", {}, MON),
                        ("decide-open:" + day.isoformat(), "09:15", {"verdicts": {"needed": 3, "answered": 3}}, day),
                        ("decide-close:" + day.isoformat(), "15:47", {"verdicts": {"needed": 0, "answered": 0}}, day),
                        ("decide-close-evl4:" + day.isoformat(), "15:48", {}, day),
                        ("score", "20:30", {"day": day.isoformat(), "complete": True, "due": 7, "settled": 7}, day),
                        ("report", "21:05", {"day": day.isoformat()}, day))
            for job, hhmm, summary, on in receipts:
                db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES(?, ?, ?, 'ok', ?)",
                           (job, t(hhmm, on), t(hhmm, on), json.dumps(summary, sort_keys=True)))
    finally:
        st.close()


class ReportCase(StallHarness):
    """A House state root with the lane's invented Tuesday, budget.json and the meters read across Tuesday's UTC day."""

    #: Claude's meter at 00:00 UTC Wednesday (20:00 ET Tuesday): Tuesday's UTC day spent $1.97 of Claude.
    end_claude = 51.97

    def setUp(self):
        super().setUp()
        synthetic_lane(self.root)
        self.now_ = et(TUE, "22:20")
        # The day's cap and its lines (budget rule 3 at no profit, Sail's fixed $1.50): budget.json, fresh, written by the
        # budget job's run before Tuesday's UTC day began.
        doc = B.compute(budget_inputs(), now=et(MON, "19:50"))
        (self.root / "budget.json").write_text(json.dumps(doc))
        # The meters read at 00:00 UTC Tuesday (20:00 ET Monday), by a stall run at 00:00 ET Tuesday (which mails Monday's
        # report) and at 00:00 UTC Wednesday (20:00 ET Tuesday): Tuesday's UTC day read whole.
        self.meters(et(MON, "20:00"), sail=100.0, claude=50.0, run=False)
        self.meters(et(TUE, "00:00"), sail=100.2, claude=50.3)
        self.meters(et(TUE, "20:00"), sail=101.2, claude=self.end_claude, run=False)

    def meters(self, at, *, sail, claude, run=True):
        """The Sail guard's meter (its kv, as league/swarm/guard.py keeps it) and the gateway's Claude meter at `at`, read
        by a stall run then (`run`), or by its meters alone (league/ops/metered.py `update`, as the run reads them)."""
        self.store.put("guard", {"last": {"balance": 400.0, "metered_spent": sail, "at": at},
                                 "last_good": {"balance": 400.0, "at": at}})
        self.health = {"kill_switch": False, "claude": {"settled_usd": f"{claude:.6f}"}}
        if run:
            ST.run(self.ctx(now=at))
            self.notify.calls.clear()
        else:
            MT.update(self.root, at, health=self.health, budget=json.loads((self.root / "budget.json").read_text()))

    def reports(self):
        return [c for c in self.notify.calls if c.get("kind") == "report"]


class DailyReport(ReportCase):

    def test_once_a_day_after_the_lanes_report_job_figures_only(self):
        self.store.put("guard", {"last": {"balance": 400.0, "metered_spent": 101.2, "at": self.now_},
                                 "last_good": {"balance": 400.0, "at": self.now_}})
        self.health = {"kill_switch": False, "claude": {"settled_usd": "51.970000"}}
        out = ST.run(self.ctx())
        self.assertEqual(out["stalled"], [], out["stalled"])
        self.assertEqual(out["report"], {"day": "2026-10-20", "sent": True, "why": "sent"})
        [facts] = self.reports()
        self.assertEqual((facts["kind"], facts["notice_id"], facts["day"], facts["lane_report"]),
                         ("report", "report:2026-10-20", "2026-10-20", True))
        # ACCOUNT-SHOWN FIRST, NET AFTER THE MEASURED COSTS BESIDE IT: 1.98 - 0.51 + 1.47 = 2.94 from the fills and fees.
        # The costs are the UTC day of the report's date (the cost rule's day), whole by 22:20 ET.
        costs = facts["costs"]
        self.assertEqual((costs["sail_usd"], costs["claude_usd"], costs["cloudflare_usd"]), (1.2, 1.97, 0.16))
        self.assertEqual((costs["spent_usd"], costs["from"], costs["to"], costs["whole"]), (3.33, "00:00", "24:00", True))
        self.assertEqual((costs["cap_usd"], costs["over"]), (5.0, False))
        self.assertEqual(costs["verdicts_usd"], 0.01, "the UTC day's verdict dollars, inside Claude's")
        self.assertEqual(costs["allowance"], {"cap_usd": 5.0, "fixed_usd": 1.66, "lane_usd": 3.0, "research_usd": 0.34,
                                              "source": "budget"})
        profit = facts["profit"]
        self.assertEqual(profit["day"], {"shown_usd": 2.94, "net_usd": round(2.94 - 3.3344, 2)})
        to_date = profit["to_date"]
        self.assertEqual((to_date["since"], to_date["shown_usd"], to_date["events"]), ("2026-10-20", 2.94, 3))
        self.assertEqual((to_date["costs_from"], to_date["partial"], to_date["missing"]), ("2026-10-20", False, []),
                         "metered.json covers the first fill's day whole")
        self.assertEqual(to_date["metered_usd"], round(3.3344 + B.CLOUDFLARE_USD_DAY, 2), "Tuesday and Wednesday so far")
        self.assertEqual(to_date["net_usd"], round(2.94 - to_date["metered_usd"], 2))
        # By program and band: the Nets share the measured compute per settled real event and add up to the lane's.
        programs = {p["id"]: p for p in facts["programs"]}
        self.assertEqual(len(facts["programs"]), 12, "the programs that may trade real money, in the tables' order: the "
                         "nine version 2 programs, then PREREG-EVL-4's three at version 1 (release 1019d)")
        self.assertEqual([(p["id"], p["version"]) for p in facts["programs"]][-3:],
                         [("EVL-8K-REACT-ON", 1), ("EVL-8K-READ-ON", 1), ("EVL-NEWSPM-READ-ON", 1)])
        read, ins = programs["EVL-ERN-READ-O1"], programs["EVL-INS-BUY-O1"]
        self.assertEqual((read["band"], read["real"], read["shadow_tradable"], read["shown_usd"]), ("learning", 2, 3, 1.47))
        self.assertEqual((ins["band"], ins["real"], ins["by_band"][0]["band"], ins["shown_usd"]), ("probe", 1, "probe", 1.47))
        self.assertAlmostEqual(read["net_usd"] + ins["net_usd"], profit["to_date"]["net_usd"], places=1)
        self.assertEqual((read["next_look"], read["events_to_go"]), (1, 57), "60 TRADABLE events for look 1, 3 settled")
        self.assertEqual(read["bench_mean_bp"], round(10000 * (0.002 + 0.002 + 0.001) / 3, 1), "b = r - a, invented")
        # The same-risk buy-and-hold: the benchmark held from the first real entry's open to the last exit's close at the
        # program's average invested dollars (one session: 100 + 40 at +1%).
        self.assertEqual(read["buy_hold_usd"], round((100.0 + 40.0) * (101.0 / 100.0 - 1), 2))
        self.assertEqual(programs["EVL-8K-READ-O1"]["buy_hold_why"], "n/a until real fills")
        self.assertEqual(facts["fills"], {"buys": 4, "sells": 3, "fees_usd": 0.06,
                                          "gap": {"entry_n": 0, "entry_mean_bp": None, "exit_n": 0, "exit_mean_bp": None}},
                         "no event twin priced yet in this store: no gap")
        self.assertEqual(facts["events"], {"8k_202": 1, "8k_other": 1, "form4": 1, "news": 1, "failed": 0})
        self.assertEqual(facts["verdicts"], {"ok": 2, "unparsed": 1, "refused": 0, "usd": 0.01})
        self.assertIn({"id": "EVL-ERN-READ-O1", "version": 1, "n": 3, "skipped": 0}, facts["intents"])
        self.assertEqual((facts["expected_false_passes"], facts["seatable_versions"], facts["alarms"]), (1.2, 12, []),
                         "0.10 x the twelve seatable versions (release 1019d: PREREG-EVL-4's three join the nine)")
        # No symbol, headline, summary or price in the facts; no figure in the receipt or stall.json.
        sent = json.dumps(facts)
        for banned in ("ACME", "MIRACLE", "secret summary", "123.45", "124.56", "BETA", "DELT", "SPY", "51.0", "39.5"):
            self.assertNotIn(banned, sent, banned)
        # The report's outcomes stay out of the receipt and stall.json (the costs are the cap_breach cause's own figures).
        kept = json.dumps(out) + (self.root / ST.STATE_FILE).read_text()
        for figure in ("shown_usd", "net_usd", "2.94", "bench_mean_bp", "market_share", "8k_202", "buy_hold"):
            self.assertNotIn(figure, kept, figure)
        self.assertEqual(json.loads((self.root / ST.STATE_FILE).read_text())["report"]["day"], "2026-10-20")
        # Told: the runs after it carry none, and mail nothing.
        self.record(self.now_ + 1700)
        later = ST.run(self.ctx(now=self.now_ + 1800))
        self.assertEqual((later["report"]["day"], later["report"]["sent"]), (None, False))
        self.assertEqual(len(self.reports()), 1)

    def test_not_before_the_lanes_report_job_and_from_2345_without_it(self):
        st = ES.Store(self.root / "events")
        st.db.execute("DELETE FROM receipts WHERE job='report'")
        st.close()
        self.assertEqual(ST.run(self.ctx())["report"]["day"], None, "the lane's report job has not run: not yet")
        self.assertEqual(self.reports(), [])
        out = ST.run(self.ctx(now=et(TUE, "23:50")))
        self.assertEqual((out["report"]["day"], out["report"]["sent"]), ("2026-10-20", True))
        self.assertIs(self.reports()[-1]["lane_report"], False)
        self.assertIsNone(DR.due(self.ctx(events=False), self.root, self.now_), "no lane on the House: no report")
        # A report not told by noon the next day is not sent at all; the next day's waits for its own night.
        (self.root / ST.STATE_FILE).unlink()
        self.assertIsNone(DR.due(self.ctx(), self.root, et(dt.date(2026, 10, 21), "12:05")))
        self.assertEqual(DR.due(self.ctx(), self.root, et(dt.date(2026, 10, 21), "11:55"))["day"], "2026-10-20")

    def test_a_failed_send_tries_again_and_a_duplicate_answer_tells_it(self):
        self.notify.answer = {"sent": False, "reason": "mail down"}
        first = ST.run(self.ctx())
        self.assertEqual((first["report"]["sent"], first["report"]["why"]), (False, "mail down"))
        self.assertIn("the daily report of 2026-10-20 not sent: mail down", first["errors"])
        self.assertEqual(json.loads((self.root / ST.STATE_FILE).read_text())["report"]["day"], "2026-10-19",
                         "Tuesday's not told: tried again (Monday's went at the 00:00 run of setUp)")
        self.notify.answer = {"sent": True, "duplicate": True}
        self.record(self.now_ + 1700)
        again = ST.run(self.ctx(now=self.now_ + 1800))
        self.assertEqual((again["report"]["sent"], again["report"]["why"]), (True, "duplicate"))
        self.assertEqual(json.loads((self.root / ST.STATE_FILE).read_text())["report"]["day"], "2026-10-20")

    def test_the_houses_facts_are_the_gateways_fixture(self):
        """league/tests/fixtures/daily_report.json is what the gateway's test composes (gateway/test/report-notice.test.mjs):
        the House writes exactly its keys, a program's and a band's too."""
        facts = DR.facts(self.ctx(), self.root, self.now_, "2026-10-20", ledger=MT.load(self.root),
                         budget=json.loads((self.root / "budget.json").read_text()), alarms=["cap_breach"])
        fixture = json.loads(FIXTURE.read_text())
        fixture.pop("_note")

        def shape(value):
            if isinstance(value, dict):
                return {k: shape(v) for k, v in value.items()}
            if isinstance(value, list):
                return [shape(value[0])] if value else []
            return None
        trimmed = {**facts, "programs": facts["programs"][:1], "intents": facts["intents"][:1]}
        self.assertEqual(shape(trimmed), shape({**fixture, "programs": fixture["programs"][:1],
                                                "intents": fixture["intents"][:1]}))

    def test_the_days_real_buys_per_auction_and_the_break_even_edge(self):
        """Release 1019f (the captain's A80 (2): the venue's cancels at once count as a fill gap): the day's real buys per
        auction from the book's own rows, the constraint that bound each, and the break-even edge of Done's compute
        clause (metered compute per session over the Probe dollars bought per session)."""
        book = Book(self.root)   # (synthetic_book's rows are there: four buys filled)
        book.buy(TUE, "open", orders=(cancel_at_once(TUE, "open"), {"status": "filled", "filled": "2",
                                                                    "why": "A80's one re-send: " + entry_why("open")}))
        book.buy(TUE, "open", status="refused", why="sizing: no whole share fits (cash): refused: no cash")
        book.buy(TUE, "close", status="missed", why="not filled at the close auction (never sent: the event kind's day "
                                                    "order count: 150 of 150 sent)")
        book.decision(TUE, "close", {"EVL-NEWS-REACT-ON": {"picks": 5, "room": 3, "planned": 3, "skipped": {}}})
        book.close()
        facts = DR.facts(self.ctx(), self.root, self.now_, "2026-10-20", ledger=MT.load(self.root),
                         budget=json.loads((self.root / "budget.json").read_text()))
        entries = facts["entries"]
        self.assertIsNone(entries["why"])
        opening, closing = entries["auctions"]
        self.assertEqual(opening, {"at": "open", "planned": 5, "filled": 4, "bound": "cash"})
        self.assertEqual(closing, {"at": "close", "planned": 2, "filled": 1, "bound": "room"})
        totals = entries["totals"]
        self.assertEqual({k: totals[k] for k in DR.TOTAL_FIELDS},
                         {"planned": 7, "filled": 5, "venue_cancels": 1, "resent": 1, "resent_filled": 1, "never_sent": 2,
                          "unfilled": 0, "room_cut": 2})
        self.assertEqual({k: n for k, n in totals["never"].items() if n}, {"cash": 1, "order_line": 1})
        even = facts["break_even"]
        self.assertEqual((even["since"], even["probe_per_session"], even["why"]), ("2026-10-20", 60.0, None),
                         "one Probe buy, one session: 3 shares at an invented $20")
        self.assertEqual(even["compute_per_session"], facts["profit"]["to_date"]["metered_usd"], "one session")
        self.assertAlmostEqual(even["edge_bp"], even["compute_per_session"] / 60.0 * 1e4, delta=1.0)
        self.assertEqual(DR.break_even(MT.load(self.root), None, TUE, self.now_)["why"], "n/a until a Probe buy")
        for banned in ("XYZ", "12.34"):
            self.assertNotIn(banned, json.dumps(entries), banned)

    def test_the_fill_gap_against_the_auction_prints_rides_the_report(self):
        """The goal's "fill gaps": the last 20 priced event twins' signed mean per side (the House's equity_twins job)."""
        self.store.put("equity_twins", {f"eq:{i}": {"key": f"eq:{i}", "kind": "event", "status": "priced",
                                                    "exit_day": "2026-10-20", "judged_at": f"2026-10-21T01:0{i}:00Z",
                                                    "entry_gap_bp": 2.0 + i, "exit_gap_bp": -1.0} for i in range(3)})
        ST.run(self.ctx())
        [facts] = self.reports()
        self.assertEqual(facts["fills"]["gap"], {"entry_n": 3, "entry_mean_bp": 3.0, "exit_n": 3, "exit_mean_bp": -1.0})

    def test_the_floors_allowance_when_budget_json_is_not_usable(self):
        (self.root / "budget.json").write_text("{not json")
        out = ST.run(self.ctx())
        [facts] = self.reports()
        self.assertEqual(facts["costs"]["allowance"]["source"], "floor")
        self.assertEqual(facts["costs"]["allowance"]["research_usd"], 0.34)
        self.assertEqual(facts["costs"]["cap_usd"], B.BASE_USD_DAY, "the day's cap with no usable budget.json")
        self.assertTrue(out["report"]["sent"])


class TheBirths(ReportCase):
    """Release 1019f's review (lens alarms, a major): a seatable birth trades real money at learning size from its first
    event (A81; births on since A93), so its settled real round trips are in the report like any seating program's:
    account-shown profit (day and to date), its program row with its buy-and-hold, its 0.10 in the expected false
    passes, and its line in the Done reader's. The stall job's process never loads the births; the report loads them
    from the lane's read-only store and leaves the table as it found it."""

    BIRTH = "EVL-B-8K-502"

    def setUp(self):
        super().setUp()
        from league.events import births as BI
        from league.tests.test_events_births import spec

        self.addCleanup(P.load_births, None)
        st = ES.Store(self.root / "events")
        try:
            sp = spec(self.BIRTH, "8k", {"items": ["5.02"]})
            at = "2026-10-20T01:00:00Z"
            st.db.execute("INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, "
                          "received_at, path, commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, "
                          "'docs/births/2026-10-19.jsonl', ?, 0, '{}', 'invented', 'captain', '2026-10-19')",
                          (sp["id"], BI.sha(sp), BI.canonical(sp), at, at, at, "c" * 40))
            # one invented real round trip of the birth at learning size: 10 shares bought at 10.00, sold at 15.00
            for side, price, wall in (("buy", 10.0, "09:30"), ("sell", 15.0, "16:00")):
                st.db.execute("INSERT INTO real_fills(program, version, event, side, qty, price, fee, filled_at, band) "
                              "VALUES(?, 1, '8k:born', ?, 10, ?, 0, ?, 'learning')",
                              (self.BIRTH, side, price, iso(et(TUE, wall))))
        finally:
            st.close()

    def test_a_births_real_round_trip_is_in_every_figure_of_the_report(self):
        self.assertEqual(P.BIRTHS, (), "the stall job's process holds no birth")
        without = DR.facts(self.ctx(), self.root, self.now_, "2026-10-20", ledger=MT.load(self.root),
                           budget=json.loads((self.root / "budget.json").read_text()))
        self.assertEqual(P.BIRTHS, (), "the report leaves the table as it found it")
        self.store.put("guard", {"last": {"balance": 400.0, "metered_spent": 101.2, "at": self.now_},
                                 "last_good": {"balance": 400.0, "at": self.now_}})
        self.health = {"kill_switch": False, "claude": {"settled_usd": "51.970000"}}
        out = ST.run(self.ctx())
        self.assertTrue(out["report"]["sent"], out["report"])
        [facts] = self.reports()
        self.assertEqual(P.BIRTHS, ())
        self.assertEqual(facts["profit"], without["profit"], "the stall job's report is the same as `facts`'")
        # ACCOUNT-SHOWN: the PREREG programs' invented 2.94 and the birth's 10 x (15 - 10) = 50.00
        self.assertEqual(facts["profit"]["day"]["shown_usd"], 52.94)
        to_date = facts["profit"]["to_date"]
        self.assertEqual((to_date["shown_usd"], to_date["events"]), (52.94, 4))
        rows = {row["id"]: row for row in facts["programs"]}
        prereg = [p for p in P.SEATING]
        self.assertEqual([row["id"] for row in facts["programs"]][:len(prereg)], [p.id for p in prereg],
                         "every PREREG program first, in the tables' order")
        self.assertEqual([row["id"] for row in facts["programs"]][len(prereg):], [self.BIRTH], "then the birth")
        born = rows[self.BIRTH]
        self.assertEqual((born["version"], born["band"], born["real"], born["shown_usd"]), (1, "learning", 1, 50.0))
        self.assertEqual([(b["band"], b["n"], b["shown_usd"]) for b in born["by_band"]], [("learning", 1, 50.0)])
        self.assertIn("buy_hold_usd", born)
        # THE EXPECTED FALSE PASSES: one more seatable version at 0.10
        self.assertEqual(facts["seatable_versions"], len(prereg) + 1)
        self.assertAlmostEqual(facts["expected_false_passes"], round(0.1 * (len(prereg) + 1), 2), places=2)
        self.assertEqual([r["id"] for r in facts["done"]["by_program"]][-1], self.BIRTH, "the Done line by program")

    def test_births_this_process_loaded_already_stay_loaded(self):
        store = DR.ReadOnlyStore(self.root / "events")
        try:
            loaded = P.load_births(store)
        finally:
            store.close()
        self.assertEqual([p.id for p in loaded], [self.BIRTH])
        facts = DR.facts(self.ctx(), self.root, self.now_, "2026-10-20", ledger=MT.load(self.root),
                         budget=json.loads((self.root / "budget.json").read_text()))
        self.assertEqual(P.BIRTHS, loaded, "a table this process loaded is left loaded")
        self.assertEqual(facts["profit"]["day"]["shown_usd"], 52.94)


class OverTheCap(ReportCase):
    """Tuesday's UTC day spent $5.00 of Claude: over its $5 cap, said by the report and by `cap_breach`."""

    end_claude = 55.0

    def test_over_the_cap_the_report_says_so_and_cap_breach_stands(self):
        self.store.put("guard", {"last": {"balance": 400.0, "metered_spent": 101.2, "at": self.now_},
                                 "last_good": {"balance": 400.0, "at": self.now_}})
        self.health = {"kill_switch": False, "claude": {"settled_usd": "55.000000"}}
        out = ST.run(self.ctx())
        self.assertIn("cap_breach", out["stalled"])
        check = out["checks"]["cap_breach"]
        self.assertIn("Metered compute on the UTC day 2026-10-20 was $6.36, over that day's cap of $5.00", check["what"])
        self.assertIsNone(check["owner_step"])
        self.assertIs(check["numbers"]["held"], False, "a day that has ended holds nothing: Wednesday is under its cap")
        self.assertFalse((self.root / B.HOLD_FILE).exists())
        [facts] = self.reports()
        self.assertEqual((facts["costs"]["spent_usd"], facts["costs"]["over"]), (6.36, True))
        self.assertEqual(facts["alarms"], ["cap_breach"])
        stall = [c for c in self.notify.calls if c.get("kind") == "stall"]
        self.assertEqual([c["cause"] for c in stall[0]["causes"]], ["cap_breach"], "the cause keys its own stall notice")


class CostsToDate(StallHarness):
    """COSTS TO DATE AS FAR AS THE METERS COVER THEM (the review of r2/alarms, its major 2): release 1019b trades real money
    before release 1019c, which starts metered.json, can be deployed. Net to date and every program's Net are measured
    over the days metered.json covers, from the later of the first fill's day and the ledger's first, and the report says
    so: never unknown for good, never a silent figure."""

    def setUp(self):
        super().setUp()
        synthetic_lane(self.root)             # the lane's first real fills: Tuesday Oct 20, from 09:30 ET

    def reading(self, at: float, *, sail: float, claude: float) -> None:
        """The meters as a stall run reads them at `at` (metered.py `update`), under a fresh budget.json."""
        (self.root / "budget.json").write_text(json.dumps(B.compute(budget_inputs(), now=at - 600)))
        self.store.put("guard", {"last": {"balance": 400.0, "metered_spent": sail, "at": at},
                                 "last_good": {"balance": 400.0, "at": at}})
        self.health = {"kill_switch": False, "claude": {"settled_usd": f"{claude:.6f}"}}
        MT.update(self.root, at, health=self.health, budget=json.loads((self.root / "budget.json").read_text()))

    def report(self, day: dt.date, at: float) -> dict:
        st = ES.Store(self.root / "events")
        st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES('report', ?, ?, 'ok', ?)",
                      (iso(et(day, "21:05")), iso(et(day, "21:05")), json.dumps({"day": day.isoformat()})))
        st.close()
        self.reading(at, sail=float(self.store.get("guard")["last"]["metered_spent"]) + 0.1,
                     claude=float(self.health["claude"]["settled_usd"]) + 0.1)
        out = ST.run(self.ctx(now=at))
        self.assertTrue(out["report"]["sent"], out["report"])
        [facts] = [c for c in self.notify.calls if c.get("kind") == "report" and c["day"] == day.isoformat()]
        return facts

    def test_a_ledger_that_starts_a_day_after_the_first_fill(self):
        """metered.json from 01:00 ET Wednesday (release 1019c deployed then): Thursday's report measures the costs since
        Wednesday, says so, and keeps Net to date and each program's Net known."""
        self.reading(et(WED, "01:00"), sail=100.0, claude=50.0)
        self.reading(et(WED, "12:00"), sail=100.6, claude=50.9)
        self.reading(et(THU, "00:30"), sail=101.3, claude=51.8)
        facts = self.report(THU, et(THU, "22:20"))
        to_date = facts["profit"]["to_date"]
        self.assertEqual((to_date["since"], to_date["costs_from"], to_date["partial"]), ("2026-10-20", "2026-10-21", True))
        self.assertIsNotNone(to_date["metered_usd"])
        self.assertEqual(to_date["net_usd"], round(to_date["shown_usd"] - to_date["metered_usd"], 2))
        ledger = MT.load(self.root)
        span = MT.since(ledger, TUE, et(THU, "22:20"))
        self.assertEqual(to_date["metered_usd"], round(span["usd"], 2))
        for row in facts["programs"]:
            if row["real"]:
                self.assertIsNotNone(row["net_usd"], row["id"])
        self.assertEqual(to_date["missing"], [])

    def test_a_ledger_that_starts_mid_day_on_the_first_fills_day(self):
        """metered.json from 02:00 ET Tuesday (release 1019c deployed on time, the night before the first fill): the first
        fill's day is measured from then, and the report says partly."""
        self.reading(et(TUE, "02:00"), sail=100.0, claude=50.0)
        self.reading(et(TUE, "12:00"), sail=100.6, claude=50.9)
        facts = DR.facts(self.ctx(now=et(TUE, "22:20")), self.root, et(TUE, "22:20"), "2026-10-20")
        to_date = facts["profit"]["to_date"]
        self.assertEqual((to_date["costs_from"], to_date["partial"]), ("2026-10-20", True))
        self.assertIsNotNone(to_date["net_usd"])
        self.assertFalse(facts["costs"]["whole"], "Tuesday's UTC day was read from 06:00 UTC")
        self.assertEqual(facts["costs"]["from"], "06:00")

    def test_no_reading_at_all_is_unknown_and_never_a_guess(self):
        facts = DR.facts(self.ctx(now=et(TUE, "22:20")), self.root, et(TUE, "22:20"), "2026-10-20")
        to_date = facts["profit"]["to_date"]
        self.assertEqual((to_date["metered_usd"], to_date["net_usd"], to_date["costs_from"], to_date["partial"]),
                         (None, None, None, True))
        self.assertEqual(to_date["shown_usd"], 2.94, "account-shown profit is the account's, whatever the meters say")


class BuyAndHold(unittest.TestCase):
    def test_na_until_real_fills_and_when_the_bars_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            synthetic_lane(Path(tmp))
            store = DR.ReadOnlyStore(Path(tmp) / "events")
            try:
                self.assertEqual(DR.buy_and_hold(store, []), {"usd": None, "why": "n/a until real fills"})
                rows = [{"cost": 100.0, "entry_day": "2026-10-20", "exit_day": "2026-10-20", "bench": "IWM"}]
                self.assertIsNone(DR.buy_and_hold(store, rows)["usd"], "no IWM bars in the store")
                rows = [{"cost": 100.0, "entry_day": "2026-10-20", "exit_day": "2026-10-20", "bench": "SPY"}]
                self.assertEqual(DR.buy_and_hold(store, rows)["usd"], 1.0)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
