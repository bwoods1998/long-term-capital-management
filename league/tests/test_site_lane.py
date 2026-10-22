"""The event lane on the public site (WP4, Oct 19, 2026): `league/site_lane.py` reads the lane's programs, its funnel, the
goal's checkpoint, its verdict spend and the equity book's lots, read-only; `league/publish.py` allowlists them under the
VERSIONED key `lane_v1` (`site_lane`), adds the verdicts to Claude's part of the bill, and sends the view only to a site
that takes it: an older site gets every other block exactly as before. The lots add up, with the options rows, Other and
Unreconciled, to the account's Profit to the cent. Every number here is invented."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import urllib.error
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from league import account_activity, publish, site_lane, site_window, trading_profit
from league.events import programs as P
from league.events import store as S
from league.ledger import Ledger
from league.publish import LANE_KEY, Publisher, SiteInputs, build_checkpoint, laneless, site_lane as allowlist

D = Decimal
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SITE_SCHEMA = FIXTURES / "site_schema.js"
RESET_AT = "2026-09-26T06:25:30.000Z"
AT = "2026-10-21T14:58:00.000Z"
NOW = dt.datetime(2026, 10, 21, 14, 58, tzinfo=dt.timezone.utc).timestamp()


def epoch(text: str) -> float:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


# --------------------------------------------------------------------------------------------- a House's state root
class World:
    """A House's state root with the lane's store (`events/events.sqlite`, the lane's own schema) and the equity book's
    tables in `live.sqlite` (league/equity/live.py's own schema)."""

    def __init__(self, root: Path):
        self.root = root
        self.store = S.Store(root / "events")
        self.live = sqlite3.connect(root / "live.sqlite", isolation_level=None)
        from league.equity.live import SCHEMA

        for statement in SCHEMA.split(";"):
            if statement.strip():
                self.live.execute(statement)
        self.eid = 0
        self.n = 0

    def close(self):
        self.store.close()
        self.live.close()

    # -- the lane's store ---------------------------------------------------------------------------------------------
    def settled(self, program: str, version: int, count: int, *, tradable: int = 1, day: str = "2026-10-20"):
        """`count` settled shadow events of (program, version), each its own issuer."""
        with self.store.tx() as db:
            for _ in range(count):
                self.n += 1
                event = f"8k:0000{self.n:06d}"
                db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, exit_day, "
                           "exit_at, rank_key, mode, status, why) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (program, version, event, f"S{self.n}", f"{self.n:010d}", f"{day}T13:15:00Z", day, "open", day,
                            "close", 2.0, "shadow", "exited", None))
                db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, r, b, a, tradable, settled_at, status) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (program, version, event, 10.0, 10.1, 0.009, 0.002, 0.007, tradable,
                                                             f"{day}T00:30:00Z", "settled"))

    def real_fill(self, program: str, event: str, *, buy: tuple[float, float], sell: tuple[float, float] | None,
                  band: str = "learning", day: str = "2026-10-20"):
        with self.store.tx() as db:
            db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, exit_day, exit_at, "
                       "rank_key, mode, status, why) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (program, 2, event, "F", "0000037996", f"{day}T13:15:00Z", day, "open", day, "close", 2.0, "real", "exited",
                        None))
            db.execute("INSERT INTO real_fills(program, version, event, side, qty, price, fee, filled_at, band) VALUES(?,?,?,?,?,?,?,?,?)",
                       (program, 2, event, "buy", buy[0], buy[1], 0.0, f"{day}T13:30:04Z", band))
            if sell is not None:
                db.execute("INSERT INTO real_fills(program, version, event, side, qty, price, fee, filled_at, band) "
                           "VALUES(?,?,?,?,?,?,?,?,?)", (program, 2, event, "sell", sell[0], sell[1], 0.01, f"{day}T20:00:02Z", band))

    def band(self, program: str, band: str, since: str = "2026-10-20T20:00:00Z"):
        with self.store.tx() as db:
            db.execute("INSERT OR REPLACE INTO bands(program, version, band, since, why) VALUES(?,?,?,?,?)", (program, 2, band, since, "test"))
            db.execute("INSERT INTO band_history(program, version, band, since, why, written_at) VALUES(?,?,?,?,?,?)",
                       (program, 2, band, since, "test", since))

    def verdict(self, event: str, usd: float | None, *, answered: bool = True):
        with self.store.tx() as db:
            db.execute("INSERT INTO verdicts(event, prompt_sha, model, asked_at, answered_at, status, score, usd) VALUES(?,?,?,?,?,?,?,?)",
                       (event, "p" * 8, "claude-haiku-4-5-20251001", "2026-10-20T12:00:00Z",
                        "2026-10-20T12:00:03Z" if answered else None, "ok" if answered else "failed", 2, usd))

    # -- the equity book ----------------------------------------------------------------------------------------------
    def lot(self, lid: int, *, family: str, symbol: str, shares: str, buy: str, sell: str | None = None, mark: str | None = None,
            opened: str, closed: str | None = None, event: bool = False, band: str = "learning", probe: int = 1):
        info = {"evl": {"program": family, "version": 2, "event": f"8k:{lid}", "band": band}} if event else {}
        instance = f"{family}@{2 if event else 3}:r"
        status = "closed" if sell is not None else "open"
        self.live.execute("INSERT INTO eq_lots(lid, instance, family, version, lane, symbol, class, qty, opened_qty, entry_px, "
                          "entry_notional, entry_at, fees, div, mark, marked_at, opened_at, opened_day, status, exit_px, exit_at, "
                          "exit_day, closed_at, cash, reason, probe, tag, iid, info) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                          "?,?,?,?,?,?,?,?,?)",
                          (lid, instance, family, 2 if event else 3, "event" if event else "beta", symbol, "stock" if event else "etf",
                           "0" if status == "closed" else shares, shares, buy, str(D(shares) * D(buy)), "open", "0.01", "0", mark,
                           epoch(opened) if mark else None, epoch(opened), opened[:10], status, sell, "close" if sell else None,
                           closed[:10] if closed else None, epoch(closed) if closed else None, "0", "program" if sell else None,
                           probe, f"evl:8k:{lid}" if event else "", None, json.dumps(info)))
        self._fill(lid, family, "buy", shares, buy, opened)
        if sell is not None:
            self._fill(lid, family, "sell", shares, sell, closed)

    def _fill(self, lid, family, side, qty, px, at):
        self.eid += 1
        self.live.execute("INSERT INTO eq_orders(eid, client_id, venue_id, instance, family, lid, side, symbol, class, at, qty, "
                          "limit_px, collar_bp, status, placed_at, day, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (self.eid, f"lq-test-{self.eid}", f"v-{self.eid}", f"{family}@2:r", family, lid, side, "X", "stock", "open",
                           qty, px, 0, "filled", epoch(at), at[:10], epoch(at)))
        self.live.execute("INSERT INTO eq_fills(eid, lid, venue_fill_id, qty, px, fees, at) VALUES(?,?,?,?,?,?,?)",
                          (self.eid, lid, None, qty, px, "0.01" if side == "sell" else "0", epoch(at)))


ETF_AGENT = "spy-drift-etf"


def fixture_world(root: Path) -> World:
    """The fixture's lane on Wednesday Oct 21, 2026 at 14:58Z: the nine version 2 programs at learning since their
    registration, two of them with a settled real-money event and two more holding one; the records and controls in
    shadow; Claude's verdicts so far; and the equity book's lots (two of the older index-fund lane's, one still open)."""
    w = World(root)
    for program, n in (("EVL-ERN-READ-O1", 14), ("EVL-8K-READ-O1", 22), ("EVL-NEWS-READ-O1", 9), ("EVL-ERN-REACT-C1", 3),
                       ("EVL-ERN-GUIDE-O1", 2), ("EVL-NEWS-READ-ON", 5)):
        w.settled(program, 2, n)
    for program, n in (("EVL-CTRL-ERN-ALL-O1", 31), ("EVL-CTRL-8K-ALL-O1", 40), ("EVL-CTRL-NEWS-ALL-O1", 18), ("EVL-ERN-READ-O3", 6)):
        w.settled(program, 1, n)
    w.real_fill("EVL-ERN-READ-O1", "8k:0001", buy=(9, 12.36), sell=(9, 12.49))
    w.real_fill("EVL-NEWS-READ-O1", "news:77", buy=(3, 69.10), sell=(3, 68.82))
    for event, usd in (("8k:a", 1.20), ("8k:b", 0.97), ("news:c", 0.69)):
        w.verdict(event, usd)
    w.verdict("news:d", None)                   # answered, its cost not stated: counted as a cent
    w.verdict("news:e", None, answered=False)   # never answered: never paid
    w.lot(3, family=ETF_AGENT, symbol="SPY", shares="2.513421", buy="662.10", sell="663.74", opened="2026-10-12T13:32:10Z",
          closed="2026-10-14T19:55:30Z")
    w.lot(7, family=ETF_AGENT, symbol="QQQ", shares="1.2", buy="601.50", mark="599.575", opened="2026-10-15T13:35:00Z")
    w.lot(21, family="EVL-ERN-READ-O1", symbol="F", shares="9", buy="12.36", sell="12.49", opened="2026-10-20T13:30:04Z",
          closed="2026-10-20T20:00:02Z", event=True)
    w.lot(22, family="EVL-NEWS-READ-O1", symbol="KO", shares="3", buy="69.10", sell="68.82", opened="2026-10-20T13:30:04Z",
          closed="2026-10-20T20:00:01Z", event=True)
    w.lot(23, family="EVL-ERN-REACT-C1", symbol="AAPL", shares="1", buy="252.30", opened="2026-10-20T20:00:01Z", event=True)
    w.lot(24, family="EVL-INS-BUY-O1", symbol="PFE", shares="6", buy="24.81", opened="2026-10-21T13:30:03Z", event=True)
    return w


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="site-lane-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


# --------------------------------------------------------------------------------------------- the reader
class ReaderTest(Case):
    def test_the_programs_their_steps_and_the_checkpoint(self):
        w = fixture_world(self.dir)
        try:
            view = site_lane.lane_view(self.dir, at=AT, start_at=RESET_AT)
        finally:
            w.close()
        rows = {row["id"]: row for row in view["programs"]}
        self.assertEqual(len(rows), 27, "the fifteen seating versions (the nine version 2 rows, PREREG-EVL-4's three, "
                                        "PREREG-EVL-5's three) and the twelve that never seat, one row each")
        self.assertEqual({row["band"] for row in rows.values()}, {"learning", "shadow"})
        self.assertEqual(sorted(i for i, r in rows.items() if r["band"] == "learning"),
                         sorted(site_lane.slug_of(p.id) for p in P.SEATING))
        self.assertEqual(rows["ern-read-o1"], {"id": "ern-read-o1", "name": "Earnings read", "band": "learning", "real": 1, "shadow": 14,
                                               "look": {"need": 60, "to_go": 46}})
        self.assertEqual(rows["8k-read-o1"]["name"], "8-K read")
        self.assertEqual(rows["ctrl-ern-all-o1"], {"id": "ctrl-ern-all-o1", "name": "All earnings", "band": "shadow", "real": 0,
                                                   "shadow": 31, "look": None})
        self.assertEqual(rows["ern-react-c1"]["real"], 0, "its lot is still open: no settled real-money event yet")
        self.assertEqual(rows["8k-read-on"], {"id": "8k-read-on", "name": "8-K read overnight", "band": "learning", "real": 0,
                                              "shadow": 0, "look": {"need": 60, "to_go": 60}}, "PREREG-EVL-4's seating version 1")
        self.assertEqual(rows["ctrl-newspm-on"]["band"], "shadow", "PREREG-EVL-4's control: a record of the lane")
        self.assertEqual(view["funnel"], {"since": P.REGISTERED_AT, "shadow": 27, "learning": 15, "probe": 0, "sized": 0, "retired": 0})
        self.assertEqual((rows["ern-drop-on"]["name"], rows["ern-under-on"]["name"], rows["news-night2-on"]["name"],
                          rows["ctrl-ern-under-on"]["band"]),
                         ("Earnings fall overnight", "Muted earnings read overnight", "News second night", "shadow"),
                         "PREREG-EVL-5's rows (release 1019g), the lane_v1 contract unchanged")
        self.assertEqual(view["checkpoint"], {"events": 0, "next": 100}, "0 until a program is at Probe")
        self.assertEqual(view["verdict_usd"], "2.87", "three stated costs and a cent for the one the gateway did not state")
        self.assertEqual(view["as_of"], AT)

    def test_a_promotion_counts_on_the_checkpoint_only_its_probe_events(self):
        w = fixture_world(self.dir)
        try:
            w.band("EVL-ERN-READ-O1", "probe", "2026-10-20T21:00:00Z")
            w.real_fill("EVL-ERN-READ-O1", "8k:0002", buy=(20, 12.0), sell=(20, 12.2), band="probe", day="2026-10-21")
            w.real_fill("EVL-ERN-READ-O1", "8k:0003", buy=(20, 12.0), sell=None, band="probe", day="2026-10-21")
            w.band("EVL-NEWS-READ-O1", "retired")
            view = site_lane.lane_view(self.dir, at=AT, start_at=RESET_AT)
        finally:
            w.close()
        rows = {row["id"]: row for row in view["programs"]}
        self.assertEqual((rows["ern-read-o1"]["band"], rows["ern-read-o1"]["real"]), ("probe", 2), "one learning and one Probe sale")
        self.assertEqual(view["checkpoint"], {"events": 1, "next": 100}, "only the settled one bought at Probe")
        self.assertEqual((view["funnel"]["probe"], view["funnel"]["retired"]), (1, 1))
        self.assertIsNone(rows["news-read-o1"]["look"], "a retired program has no next look")

    def test_the_lots_are_their_trades_and_the_open_ones_at_the_books_own_value(self):
        w = fixture_world(self.dir)
        w.close()
        lots = site_lane.read_lots(self.dir, at=AT, start_at=RESET_AT)
        rows = {row["id"]: row for row in lots["rows"]}
        self.assertEqual(rows["lot:3"]["pnl_usd"], "4.12", "2.513421 shares, sold 1.64 above the buy")
        self.assertEqual(rows["lot:7"]["pnl_usd"], "-2.31", "open at its mark")
        self.assertEqual((rows["lot:23"]["pnl_usd"], rows["lot:24"]["pnl_usd"]), ("0.00", "0.00"), "never marked: at entry")
        self.assertEqual(rows["lot:21"], {"id": "lot:21", "source": "program", "owner": "ern-read-o1", "symbol": "F",
                                          "route": "learning", "shares": "9", "open_shares": "0", "status": "closed",
                                          "opened_at": "2026-10-20T13:30:00.000Z", "closed_at": "2026-10-20T20:00:00.000Z",
                                          "pnl_usd": "1.17", "value": D("1.17"), "describable": True})
        self.assertEqual((rows["lot:3"]["source"], rows["lot:3"]["owner"], rows["lot:3"]["route"]), ("agent", ETF_AGENT, "probe"))
        self.assertEqual((rows["lot:7"]["shares"], rows["lot:7"]["open_shares"]), ("1.2", "1.2"))
        self.assertEqual(lots["pnl_usd"], "2.14")
        later = site_lane.read_lots(self.dir, at=AT, start_at="2026-10-16T00:00:00Z")
        self.assertEqual(sorted(r["id"] for r in later["rows"]), ["lot:21", "lot:22", "lot:23", "lot:24"], "lots before the reset are not its")

    def test_a_house_with_no_lane_and_no_equity_book_publishes_neither(self):
        self.assertIsNone(site_lane.lane_view(self.dir, at=AT, start_at=RESET_AT))
        self.assertEqual(site_lane.read_verdict_usd(self.dir), D(0))
        self.assertEqual(site_lane.read_lots(self.dir, at=AT), {"as_of": AT, "rows": [], "earlier": None, "pnl_usd": "0.00"})

    def test_every_name_is_plain_and_unique(self):
        names = [site_lane.name_of(p) for p in P.PROGRAMS if p.version == 1]
        self.assertEqual(len(set(names)), len(names))
        for name in names:
            self.assertRegex(name, publish._PROGRAM_NAME)
            self.assertTrue(publish.quote_free(name))
        self.assertEqual(site_lane.name_of(SimpleNamespace(id="EVL-NEW-O1", family="news")), "Morning news", "a later program: its family")

    def test_the_registered_births_are_listed_as_the_lane_loads_them(self):
        """R3's births (release 1019e): the view lists the lane as merged, each seatable birth at its band (learning
        from birth) and its control and every record as shadow, each with a plain unique name and never its rule."""
        from league.events import births as BI

        w = fixture_world(self.dir)
        try:
            def register(sp: dict, seq: int) -> None:
                text = BI.canonical(sp)
                w.store.db.execute(
                    "INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, received_at, path, "
                    "commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', 'invented', "
                    "'captain', '2026-10-20')", (sp["id"], BI.sha(sp), text, int(sp["seatable"]), "2026-10-21T01:20:00Z",
                                                 "2026-10-21T01:20:00Z", "2026-10-21T01:20:00Z",
                                                 "docs/births/2026-10-20.jsonl", "c" * 40, seq))
            base = {"version": 1, "exit": "close", "hold": 1}
            register(base | {"id": "EVL-B-8K-502", "family": "8k", "rule": {"items": ["5.02"]}, "entry": "open",
                             "rank": "none", "seatable": True}, 0)
            register(base | {"id": "EVL-B-ERN-TOP", "family": "ern", "rule": {"score_min": 3}, "entry": "open",
                             "rank": "score", "seatable": True}, 1)
            register(base | {"id": "EVL-B-8K-REC", "family": "8k", "rule": {"items": ["1.02"]}, "entry": "open",
                             "rank": "none", "seatable": False}, 2)
            view = site_lane.lane_view(self.dir, at=AT, start_at=RESET_AT)
        finally:
            w.close()
            P.load_births(None)
        rows = {row["id"]: row for row in view["programs"]}
        self.assertEqual(len(rows), 31, "the twenty-seven and four births' rows: two seatable, a control, a record")
        self.assertEqual({k: (rows[k]["name"], rows[k]["band"]) for k in rows if k.startswith("b-")},
                         {"b-8k-502": ("8-K birth 1", "learning"), "b-ern-top": ("Earnings birth 2", "learning"),
                          "b-ern-top-ctrl": ("Earnings birth 2 control", "shadow"), "b-8k-rec": ("8-K birth 3", "shadow")})
        self.assertEqual(rows["b-8k-502"]["look"], {"need": 60, "to_go": 60}, "PREREG-EVL-3's first look, as any seating version")
        self.assertEqual((view["funnel"]["shadow"], view["funnel"]["learning"]), (31, 17))
        names = [row["name"] for row in rows.values()]
        self.assertEqual(len(set(names)), len(names), "every name unique")
        for row in rows.values():
            self.assertRegex(row["name"], publish._PROGRAM_NAME)
        self.assertNotIn("5.02", json.dumps(view["programs"]), "a birth's rule never leaves")
        self.assertEqual(allowlist(view, AT)["programs"], sorted(view["programs"], key=lambda r: publish.LANE_BAND_RANK[r["band"]]),
                         "every row is one the page can draw")


# --------------------------------------------------------------------------------------------- the allowlist
def lane_input(root: Path) -> dict:
    w = fixture_world(root)
    try:
        return site_lane.lane_view(root, at=AT, start_at=RESET_AT)
    finally:
        w.close()


class AllowlistTest(Case):
    def test_the_view_is_built_key_by_key_and_adds_up(self):
        view = allowlist(lane_input(self.dir), AT)
        self.assertEqual(set(view), {"as_of", "programs", "funnel", "checkpoint", "verdict_usd", "lots"})
        self.assertEqual([r["band"] for r in view["programs"]], ["learning"] * 15 + ["shadow"] * 12, "the higher steps first")
        lots = view["lots"]
        self.assertEqual(set(lots), {"as_of", "rows", "earlier", "pnl_usd"})
        self.assertEqual([r["id"] for r in lots["rows"]], ["lot:24", "lot:23", "lot:7", "lot:22", "lot:21", "lot:3"],
                         "open first, newest first; then the most recently closed (the same minute: the later lot first)")
        self.assertTrue(all(set(r) == {"id", "source", "owner", "symbol", "route", "shares", "open_shares", "status",
                                       "opened_at", "closed_at", "pnl_usd"} for r in lots["rows"]))
        self.assertEqual(sum(D(r["pnl_usd"]) for r in lots["rows"]), D(lots["pnl_usd"]))
        self.assertEqual(allowlist(view, AT), view, "a fixed point")

    def test_what_the_page_cannot_draw_never_leaves(self):
        raw = lane_input(self.dir)
        raw["programs"][0] = {**raw["programs"][0], "name": "Reads the 8-K at 1.25"}
        raw["programs"][1] = {**raw["programs"][1], "band": "candidate"}
        shadow = [i for i, row in enumerate(raw["programs"]) if row["band"] == "shadow"][-1]
        raw["programs"][shadow] = {**raw["programs"][shadow], "real": 3}   # a shadow program never holds real money
        raw["programs"].append({"id": "x", "name": "Bad look", "band": "learning", "real": 0, "shadow": 0, "look": {"need": 5, "to_go": 9}})
        raw["programs"].append({"id": "y", "name": "Venue alpaca", "band": "learning", "real": 0, "shadow": 0, "look": None})
        raw["programs"][2] = {**raw["programs"][2], "code": "PARAMS = {}"}
        view = allowlist(raw, AT)
        self.assertEqual(len(view["programs"]), 24, "three broken rows left out, two invented rows refused")
        self.assertNotIn("code", json.dumps(view))
        self.assertIsNone(allowlist({**raw, "funnel": {**raw["funnel"], "probe": 16}}, AT)["funnel"], "a chain that widens is unknown")
        self.assertEqual(allowlist({**raw, "checkpoint": {"events": 230, "next": 1}}, AT)["checkpoint"], {"events": 230, "next": 300})
        self.assertIsNone(allowlist({**raw, "as_of": "2026-10-21T15:30:00.000Z"}, AT), "dated after the checkpoint")

    def test_a_lot_the_fields_cannot_describe_folds_into_the_not_listed_line_and_the_sum_holds(self):
        raw = lane_input(self.dir)
        rows = raw["lots"]["rows"]
        bad = next(r for r in rows if r["id"] == "lot:22")
        bad["symbol"] = "not a symbol"
        orphan = next(r for r in rows if r["id"] == "lot:24")
        orphan["owner"] = "nobody"
        view = allowlist(raw, AT)["lots"]
        self.assertEqual(view["earlier"], {"positions": 2, "pnl_usd": "-0.84"})
        self.assertEqual(view["pnl_usd"], "2.14", "nothing lost")
        many = {**raw["lots"], "rows": [dict(rows[2], id=f"lot:{n}", pnl_usd="0.01", value=D("0.01")) for n in range(1, 400)]}
        folded = allowlist({**raw, "lots": many}, AT)["lots"]
        self.assertEqual((len(folded["rows"]), folded["earlier"]["positions"]), (publish.MAX_LOTS, 99))
        self.assertEqual(folded["pnl_usd"], "3.99")

    def test_under_the_byte_limit_the_lots_fold_then_the_view_leaves_before_anything_older(self):
        raw = lane_input(self.dir)
        body = {"schema_version": 2, "published_at": AT, "agents": [], "structures": [], LANE_KEY: allowlist(raw, AT), "filler": ""}
        limit = publish.MAX_CHECKPOINT_BYTES - publish.FIT_HEADROOM_BYTES
        body["filler"] = "x" * (limit - len(publish.canonical(body).encode()) + 300)   # 300 bytes over: a few lots fold
        out = publish.fit(json.loads(json.dumps(body)))
        lots = out[LANE_KEY]["lots"]
        self.assertLess(len(lots["rows"]), 6)
        self.assertEqual(lots["pnl_usd"], "2.14", "folded, never lost")
        body["filler"] = "x" * (publish.MAX_CHECKPOINT_BYTES - publish.FIT_HEADROOM_BYTES)
        self.assertNotIn(LANE_KEY, publish.fit(body))


# --------------------------------------------------------------------------------------------- the tie-out
class TieOutTest(Case):
    def test_options_rows_lots_other_and_unreconciled_add_up_to_the_accounts_profit(self):
        """The account's own record of the lots' trades, their sale fees and a dividend (`account_activity.classify`):
        the equity book's fills are left out there and its fee and dividend rows are not, so the lots (their trades) and
        Other carry each dollar once. With the open lots marked where the account values them, the lines are the
        account's Profit to the cent."""
        w = fixture_world(self.dir)
        w.close()
        book = account_activity.read_book(self.dir, RESET_AT)
        db = sqlite3.connect(self.dir / "live.sqlite")
        db.row_factory = sqlite3.Row
        orders = [dict(r) for r in db.execute("SELECT o.venue_id, o.side, f.qty, f.px FROM eq_orders o JOIN eq_fills f ON f.eid = o.eid")]
        db.close()
        activities = [{"id": f"a{n}", "activity_type": "FILL", "symbol": "SPY", "side": o["side"], "qty": o["qty"], "price": o["px"],
                       "order_id": o["venue_id"], "transaction_time": "2026-10-14T19:55:30Z"} for n, o in enumerate(orders)]
        activities += [{"id": "fee1", "activity_type": "FEE", "net_amount": "-0.03", "date": "2026-10-14"},
                       {"id": "fee2", "activity_type": "FEE", "net_amount": "-0.02", "date": "2026-10-20"},
                       {"id": "div1", "activity_type": "DIV", "symbol": "QQQ", "net_amount": "0.71", "date": "2026-10-17"}]
        venue_orders = [{"id": o["venue_id"], "client_order_id": "", "filled_qty": o["qty"]} for o in orders]
        reading = account_activity.classify(activities, venue_orders, book, now=NOW)
        other = {part: reading[part] for part in trading_profit.OTHER_PARTS}
        self.assertEqual((other["fees_usd"], other["misc_usd"], reading["unreconciled_usd"]), (D("-0.05"), D("0.71"), D(0)))
        # The account: cash moved by every fill, fee and dividend; the open lots at the account's own prices.
        cash = sum((D(o["qty"]) * D(o["px"]) * (1 if o["side"] == "sell" else -1) for o in orders), D(0)) + D("-0.05") + D("0.71")
        held = {"QQQ": (D("1.2"), D("599.575")), "AAPL": (D("1"), D("252.30")), "PFE": (D("6"), D("24.81"))}
        account_profit = trading_profit.cents(cash + sum((q * p for q, p in held.values()), D(0)))
        lots = allowlist(site_lane.lane_view(self.dir, at=AT, start_at=RESET_AT), AT)["lots"]
        lines = sum((D(r["pnl_usd"]) for r in lots["rows"]), D(0)) + sum(other.values(), D(0)) + reading["unreconciled_usd"]
        self.assertEqual(lines, account_profit, "every dollar once, to the cent")
        self.assertEqual(account_profit, D("2.80"), "2.14 of trades, 0.05 of fees and 0.71 of dividend")


# --------------------------------------------------------------------------------------------- the publisher
class Site:
    """A site that may refuse the lane's view (an older site), or anything with an entry it rejects."""

    def __init__(self, refuse_lane=False):
        self.posts, self.refuse_lane = [], refuse_lane

    def __call__(self, request, timeout=None):
        body = json.loads(request.data)
        self.posts.append((request.full_url, body))
        if request.full_url.endswith("/checkpoint") and LANE_KEY in body and self.refuse_lane:
            raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, _Reply(b'{"error":"Invalid checkpoint."}'))
        return _Response({"stored": len(body.get("events") or []), "replayed": 0})

    def checkpoints(self):
        return [body for url, body in self.posts if url.endswith("/checkpoint")]


class _Reply:
    def __init__(self, data):
        self.data = data

    def read(self, *a):
        return self.data

    def close(self):
        pass


class _Response:
    def __init__(self, body):
        self.status, self._body = 200, json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


QUIET = {"as_of": AT, "fees_usd": "0", "crypto_usd": "0", "interest_usd": "0", "misc_usd": "0", "unreconciled_usd": "0", "problems": []}


class PublisherTest(Case):
    def setUp(self):
        super().setUp()
        self.clock = SimpleNamespace(now=NOW)
        self.ledger = Ledger(self.dir / "ledger.sqlite", clock=lambda: self.clock.now)

    def tearDown(self):
        self.ledger._db.close()
        super().tearDown()

    def house(self):
        house = SimpleNamespace(ledger=self.ledger, books={}, alerts=[],
                                registry=SimpleNamespace(living=lambda: [], dead=lambda: []),
                                evaluator=SimpleNamespace(rung=lambda agent_id: 0))
        house.alert = lambda level, text, **kw: house.alerts.append((level, text))
        house.site_inputs = lambda: {"compute": {"claude_usd": "41.20", "sail_usd": "212.40", "openai_usd": "64.10"}}
        return house

    def publisher(self, site):
        from league.account_activity import ActivityLedger

        publisher = Publisher("https://blakewoods.us", lambda: "t" * 40, self.dir / "publish.json", tape="test", opener=site,
                              clock=lambda: self.clock.now, performance={"start_at": RESET_AT, "start_equity": "481.65"})
        publisher.activity = ActivityLedger(None, RESET_AT, self.dir, clock=lambda: self.clock.now, threaded=False, reader=lambda: QUIET)
        return publisher

    def test_the_lane_rides_its_own_key_and_claudes_part_holds_the_verdicts(self):
        fixture_world(self.dir).close()
        site = Site()
        house = self.house()
        self.publisher(site).publish(house)
        body = site.checkpoints()[-1]
        self.assertIn(LANE_KEY, body)
        self.assertEqual(body["compute"]["claude_usd"], "44.07", "41.20 of research and 2.87 of verdicts")
        self.assertEqual(body[LANE_KEY]["verdict_usd"], "2.87")
        self.assertEqual(body[LANE_KEY]["lots"]["pnl_usd"], "2.14")

    def test_the_bill_holds_the_births_calls_too(self):
        """Release 1019e's review: R3's births job pays its one Haiku call a night through the lane's gateway, stored in
        `birth_calls`; the lane's verdict figure and Claude's part of the bill hold it (one stored with no cost at the
        night's whole cap, $0.25), never understated."""
        w = fixture_world(self.dir)
        with w.store.tx() as db:
            db.execute("INSERT INTO birth_calls(night, prompt_sha, model, request_id, asked_at, answered_at, status, usd) "
                       "VALUES('2026-10-20', 'p', 'm', 'r', '2026-10-21T01:15:30Z', '2026-10-21T01:16:00Z', 'ok', 0.21)")
            db.execute("INSERT INTO birth_calls(night, prompt_sha, model, request_id, asked_at, answered_at, status, usd) "
                       "VALUES('2026-10-19', 'p', 'm', 'r', '2026-10-20T01:15:30Z', '2026-10-20T01:16:00Z', 'ok', NULL)")
        w.close()
        self.assertEqual(site_lane.read_verdict_usd(self.dir), Decimal("2.87") + Decimal("0.21") + Decimal("0.25"))
        site = Site()
        self.publisher(site).publish(self.house())
        body = site.checkpoints()[-1]
        self.assertEqual(body[LANE_KEY]["verdict_usd"], "3.33")
        self.assertEqual(body["compute"]["claude_usd"], "44.53", "41.20 of research, 2.87 of verdicts, 0.46 of births")

    def test_an_older_site_gets_every_other_block_as_before_and_is_offered_the_view_again_in_half_an_hour(self):
        fixture_world(self.dir).close()
        site = Site(refuse_lane=True)
        house = self.house()
        publisher = self.publisher(site)
        self.assertEqual(publisher.publish(house)["checkpoint"], 200)
        first, second = site.checkpoints()
        self.assertEqual(laneless(first), second, "the same checkpoint, without the view")
        self.assertEqual(set(first) - set(second), {LANE_KEY})
        said = [t for _, t in house.alerts if "event lane's view" in t]
        self.assertEqual(len(said), 1)
        self.assertIn("Invalid checkpoint.", said[0])
        self.clock.now += 60
        publisher.publish(house)
        self.assertEqual(len(site.checkpoints()), 3, "inside the half hour: one post, without the view")
        self.assertNotIn(LANE_KEY, site.checkpoints()[-1])
        self.assertEqual(site.checkpoints()[-1]["compute"]["claude_usd"], "44.07", "the bill keeps the verdicts either way")
        self.clock.now += publish.LANE_RETRY_SECONDS
        site.refuse_lane = False
        publisher.publish(house)
        self.assertIn(LANE_KEY, site.checkpoints()[-1], "offered again, and taken")
        self.assertEqual(len([t for _, t in house.alerts if "event lane's view" in t]), 1, "said once")

    def test_a_lane_store_that_cannot_be_read_costs_the_view_and_leaves_claudes_part_unknown(self):
        (self.dir / "events").mkdir()
        (self.dir / "events" / "events.sqlite").write_bytes(b"not a database")
        site = Site()
        house = self.house()
        self.publisher(site).publish(house)
        body = site.checkpoints()[-1]
        self.assertNotIn(LANE_KEY, body)
        self.assertIsNone(body["compute"]["claude_usd"], "never understated")

    def test_a_view_the_allowlist_cannot_build_costs_only_itself(self):
        from unittest import mock

        fixture_world(self.dir).close()
        site = Site()
        with mock.patch.object(publish, "site_lane", side_effect=ValueError("a broken view")):
            self.publisher(site).publish(self.house())
        body = site.checkpoints()[-1]
        self.assertNotIn(LANE_KEY, body)
        self.assertEqual(body["compute"]["claude_usd"], "44.07", "the rest of the checkpoint as ever")

    def test_a_house_with_no_lane_publishes_what_it_did(self):
        site = Site()
        house = self.house()
        self.publisher(site).publish(house)
        body = site.checkpoints()[-1]
        self.assertNotIn(LANE_KEY, body)
        self.assertEqual(body["compute"]["claude_usd"], "41.20")


# --------------------------------------------------------------------------------------------- the fixture
def lane_checkpoint() -> dict:
    """`site_checkpoint_lane.json`: the checkpoint of Wednesday Oct 21, 2026 at 14:58Z, with the lane's view (the reader
    over `fixture_world`), the options lane's history all closed, the older index-fund lane's two lots, and the
    account's Profit 0.63 above the House's own values (the open lots' valuation difference)."""
    from league.tests.test_publish import FIXTURE_AGENTS, FIXTURE_BOOK, FIXTURE_INPUTS, FIXTURE_PRACTICE, agent

    root = Path(tempfile.mkdtemp(prefix="site-lane-fixture-"))
    try:
        lane = lane_input(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    closed = {14: "2026-09-28T15:31:00.000Z", 13: "2026-09-29T14:02:00.000Z"}
    private = {14: ("the condor fits the quiet tape", "the range held", "sized", "agent", "184.00", "condor-vrp-3@9:r"),
               13: ("range broke up early", "the break faded", "probe", "agent", "96.00", "orb-4@4:r"),
               12: ("range broke up", "the break failed by noon", "probe", "agent", "96.00", "orb-4@4:r"),
               11: ("gap down held", None, "probe", "house", "61.00", "putspread-dip-2@3:r"),
               10: (None, None, "calibration", "house", "40.00", "house:calibration@1:c"),
               9: ("three red days", None, None, "expiry", "66.00", "reversal-1@2:r")}
    rows = []
    for row in FIXTURE_BOOK["rows"]:
        tag, close, route, exit_kind, loss, inst = private[row["pid"]]
        if row["pid"] in closed:
            row = {**row, "status": "closed", "open_quantity": 0, "closed_at": closed[row["pid"]]}
        rows.append({**row, "_tag": tag, "_close_why": close, "_route": route, "_exit": exit_kind, "_max_loss": loss, "_instance": inst})
    book = {"as_of": "2026-10-21T14:57:00.000Z", "pnl_usd": "10.90", "rows": rows}
    account = {"as_of": "2026-10-21T14:55:02.000Z", "fees_usd": "0.08", "crypto_usd": "-0.08", "interest_usd": "0", "misc_usd": "0",
               "unreconciled_usd": "0", "problems": []}
    trading, positions = trading_profit.complete(book, account, at=AT)
    etf = agent(ETF_AGENT, band="probe", structure=None, mechanism="Holds the index fund into the close on days the market ran up.",
                born_at="2026-10-09T22:10:00.000Z", trials=640, revisions=4, pinned=True)
    agents = [*FIXTURE_AGENTS, etf]
    names = {a["id"]: ((), True) for a in agents}
    from league.swarm import public

    levels_now = {"condor-vrp-3": "sized", "putspread-dip-2": "probe", "orb-4": "probe", "ironfly-quiet": "candidate",
                  "butterfly-pin": "candidate", "trend-vertical": "candidate", "gap-drift": "incubator", "skew-revert": "validation",
                  "calendar-term": "practice", "strangle-cheap": "train", "eod-drift": "train", "reversal-1": "retired", ETF_AGENT: "probe"}
    levels = {"as_of": "2026-10-21T14:57:00.000Z", "agents": [{"id": a["id"], "level": levels_now[a["id"]]} for a in agents],
              "funnel": {"since": RESET_AT, "born": 3890, "practice": 142, "validation": 657, "tuition": 3, "incubator": 0, "looks": 51,
                         "looks_passed": 10, "candidate": 10, "probe": 9, "sized": 0, "retired": 3783, "calibration": 37, "live_test": 4}}
    rationale = {"as_of": "2026-10-21T14:57:00.000Z",
                 "agents": [{"id": a["id"], "thesis": public.thesis_text(a["mechanism"])} for a in agents],
                 "trades": site_window.trades(positions["rows"], names, {row["_instance"]: () for row in rows})}
    profit = D(trading["pnl_usd"]) + D(lane["lots"]["pnl_usd"]) + D("0.63")
    equity = D("481.65") + D("1900") + profit
    inputs = SiteInputs(**{**FIXTURE_INPUTS.__dict__,
                           "account": {"equity": str(equity), "cash": "2093.74", "as_of": "2026-10-21T14:57:58.000Z", "stale": False},
                           "performance": {"start_at": RESET_AT, "start_equity": "481.65", "net_flows": "1900",
                                           "verified_at": "2026-10-21T14:55:02.000Z"},
                           "compute": {"as_of": "2026-10-21T14:57:00.000Z", "sail_usd": "509.09", "claude_usd": "194.78",
                                       "openai_usd": "50.23", "thetadata_usd": "59.75", "market_data_usd": "62.24", "other_usd": "0"},
                           "gym": {"as_of": "2026-10-21T14:50:00.000Z", "trials": 104494, "market_years": "51240.5", "families_alive": 13,
                                   "families_retired": 3783},
                           "agents": agents, "structures": [], "trading": trading, "positions": positions, "practice": FIXTURE_PRACTICE,
                           "levels": levels, "rationale": rationale, "lane": lane})
    return build_checkpoint(inputs, AT)


def accepts(bodies, schema=None):
    """The site's own `validCheckpoint` over each body, in node (fixtures/site_schema.js, or `LTCM_SITE_SCHEMA`)."""
    import subprocess

    schema = Path(schema or os.environ.get("LTCM_SITE_SCHEMA") or SITE_SCHEMA)
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError("node is required in CI to run the site's schema")
        raise unittest.SkipTest("node is not installed")
    script = (f"import {{ validCheckpoint }} from {json.dumps(schema.resolve().as_uri())};"
              "let text = ''; process.stdin.on('data', chunk => { text += chunk; });"
              "process.stdin.on('end', () => console.log(JSON.stringify(JSON.parse(text).map(body => validCheckpoint(body)))));")
    done = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps(bodies), capture_output=True, text=True, timeout=120)
    if done.returncode:
        raise AssertionError(done.stderr[-2000:])
    return json.loads(done.stdout), "validLane" in schema.read_text(encoding="utf-8")


class LaneFixtureTest(unittest.TestCase):
    def test_the_lane_fixture_is_this_modules_own_output(self):
        """LTCM_WRITE_SITE_FIXTURES=1 rewrites it from here; the site's contract test publishes and draws it."""
        body = lane_checkpoint()
        self.assertEqual(set(body) - set(laneless(body)), {LANE_KEY})
        lane = body[LANE_KEY]
        self.assertEqual(lane["checkpoint"], {"events": 0, "next": 100})
        self.assertEqual(lane["lots"]["pnl_usd"], "2.14")
        profit = D(body["account"]["equity"]) - D("481.65") - D("1900")
        lines = (sum(D(r["pnl_usd"]) for r in body["positions"]["rows"]) + sum(D(body["positions"]["other"][p]) for p in publish.OTHER_KEYS)
                 + D(body["positions"]["unreconciled_usd"]) + D(lane["lots"]["pnl_usd"]))
        self.assertEqual(profit - lines, D("0.63"), "the open lots' valuation difference, and nothing else")
        self.assertIn(ETF_AGENT, [a["id"] for a in body["agents"]], "the older lane's agent a lot names is on the roster")
        path = FIXTURES / "site_checkpoint_lane.json"
        if os.environ.get("LTCM_WRITE_SITE_FIXTURES"):
            path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), body)
        self.assertEqual(allowlist(body[LANE_KEY], body["published_at"]), body[LANE_KEY], "the allowlist is a fixed point")

    def test_the_site_takes_the_view_and_an_older_site_the_checkpoint_without_it(self):
        fixture = json.loads((FIXTURES / "site_checkpoint_lane.json").read_text(encoding="utf-8"))
        lane = fixture[LANE_KEY]
        rows = lane["lots"]["rows"]
        bad = [
            {**fixture, LANE_KEY: {**lane, "lots": {**lane["lots"], "pnl_usd": "9.99"}}},
            {**fixture, LANE_KEY: {**lane, "programs": [{**lane["programs"][0], "band": "candidate"}, *lane["programs"][1:]]}},
            {**fixture, LANE_KEY: {**lane, "lots": {**lane["lots"], "rows": [{**rows[0], "owner": "nobody"}, *rows[1:]]}}},
            {**fixture, LANE_KEY: {**lane, "checkpoint": {"events": 0, "next": 200}}},
            {**fixture, LANE_KEY: {**lane, "funnel": {**lane["funnel"], "sized": 5}}},
            {**fixture, LANE_KEY: {**lane, "lots": {**lane["lots"], "rows": [{**rows[0], "price": "24.81"}, *rows[1:]]}}},
        ]
        verdicts, knows_lane = accepts([fixture, laneless(fixture), *bad])
        if knows_lane:
            self.assertEqual(verdicts, [True, True, False, False, False, False, False, False], "the view, the body without it, each broken rule")
        else:
            self.assertEqual(verdicts[:2], [False, True], "an older site refuses the view and takes the rest")


# PREREG-EVL-7 (A125 pinned REGISTERED_AT_7): this module's tests are of mechanisms written before the learners
# registered and run on the registries without them (league/tests/evl7_fakes.py); the learners' own effects on these
# paths are league/tests/test_events_evl7.py's and test_events_evl7_fix.py's.
from league.tests.evl7_fakes import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
