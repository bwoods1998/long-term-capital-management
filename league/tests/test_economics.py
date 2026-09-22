"""scripts/economics.py: exact arithmetic over a hand-built ledger, and read-only access."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "economics.py"
spec = importlib.util.spec_from_file_location("economics_under_test", SCRIPT)
econ = importlib.util.module_from_spec(spec)
spec.loader.exec_module(econ)

D = Decimal


def at(minute: int) -> str:
    return f"2026-09-21T{10 + minute // 60:02d}:{minute % 60:02d}:00.000Z"


EVENT_REAL = {"asset_class": "event", "symbol": "KX-1", "venue": "kalshi", "multiplier": "1", "right": "yes", "market_id": "KX-1"}
EVENT_SHADOW = {"asset_class": "event", "symbol": "KS-2", "venue": "kalshi", "multiplier": "1", "right": "no", "market_id": "KS-2"}
STOCK = {"asset_class": "equity", "symbol": "XYZ", "venue": "alpaca", "multiplier": "1"}

ROWS = [
    # --- real kalshi: stake 50, buy 10 @ 0.40 + 0.20 fee, settles YES for 10.00; a House venue fee of 0.05
    (0, "book.stake", "alice", {"book": "kalshi", "usd": "50", "real_money": True}),
    (1, "book.fill", "alice", {"book": "kalshi", "source": "venue", "side": "buy", "instrument": EVENT_REAL, "quantity": "10",
                               "price": "0.40", "fee_usd": "0.20", "cash_delta": "-4.20", "position_delta": "10", "real_money": True}),
    (2, "book.settle", "alice", {"book": "kalshi", "instrument": EVENT_REAL, "result": "yes", "quantity": "10", "cost": "4.20",
                                 "payout": "10.00", "pnl": "5.80", "real_money": True}),
    (3, "book.fill", "house", {"book": "kalshi", "source": "venue-fee", "side": "fee", "instrument": None, "quantity": "0",
                               "price": "0", "fee_usd": "0.05", "cash_delta": "-0.05", "position_delta": "0", "real_money": True}),
    (4, "book.mark", "alice", {"book": "kalshi", "equity": "55.80", "cash": "55.80", "staked": "50", "realized": "5.80",
                               "fees": "0.20", "holdings": 0, "real_money": True}),
    (5, "floor.mark", "house", {"account_equity": "1005.75", "real_account_equity": "1010.00", "account_cash": "1010.00",
                                "as_of": at(5), "venues": [{"venue": "kalshi", "equity": "510", "cash": "510", "as_of": at(5)}]}),
    # --- practice alpaca-paper: stake 1000, buy 10 @ 10, sell 10 @ 9 less a 0.50 fee
    (10, "book.stake", "bob", {"book": "alpaca-paper", "usd": "1000", "real_money": False}),
    (11, "book.fill", "bob", {"book": "alpaca-paper", "source": "venue", "side": "buy", "instrument": STOCK, "quantity": "10",
                              "price": "10", "fee_usd": "0", "cash_delta": "-100", "position_delta": "10", "real_money": False}),
    (12, "book.fill", "bob", {"book": "alpaca-paper", "source": "venue", "side": "sell", "instrument": STOCK, "quantity": "10",
                              "price": "9", "fee_usd": "0.50", "cash_delta": "89.50", "position_delta": "-10",
                              "realized": "-10.50", "real_money": False}),
    (13, "book.mark", "bob", {"book": "alpaca-paper", "equity": "989.50", "cash": "989.50", "staked": "1000",
                              "realized": "-10.50", "fees": "0.50", "holdings": 0, "real_money": False}),
    # --- practice kalshi-shadow: stake 200, buy 5 NO @ 0.60 + 0.10 fee, settles YES (NO pays nothing)
    (20, "book.stake", "carol", {"book": "kalshi-shadow", "usd": "200", "real_money": False}),
    (21, "book.fill", "carol", {"book": "kalshi-shadow", "source": "venue", "side": "buy", "instrument": EVENT_SHADOW, "quantity": "5",
                                "price": "0.60", "fee_usd": "0.10", "cash_delta": "-3.10", "position_delta": "5", "real_money": False}),
    (22, "book.settle", "carol", {"book": "kalshi-shadow", "instrument": EVENT_SHADOW, "result": "yes", "quantity": "5",
                                  "cost": "3.10", "payout": "0", "pnl": "-3.10", "real_money": False}),
    (23, "book.mark", "carol", {"book": "kalshi-shadow", "equity": "196.90", "cash": "196.90", "staked": "200",
                                "realized": "-3.10", "fees": "0.10", "holdings": 0, "real_money": False}),
    # --- spend
    (30, "agent.research", "alice", {"tool": "summary", "session": "S1", "profile": "openai_luna", "cost_usd": "0.50"}),
    (31, "agent.research", "bob", {"tool": "summary", "session": "S2", "profile": "pro_asap", "cost_usd": "0.40"}),
    (32, "provider.request", "alice", {"profile": "openai_luna", "model": "gpt-5.6-luna", "session_id": "S1", "status": "completed",
                                       "cost_usd": "0.30", "cost_verified": True, "held_usd": "0.06"}),
    (33, "provider.request", "alice", {"profile": "openai_luna", "model": "gpt-5.6-luna", "session_id": "S1", "status": "completed",
                                       "cost_usd": "0.20", "cost_verified": True, "held_usd": "0.06"}),
    (34, "provider.request", "alice", {"profile": "openai_luna", "session_id": "S1", "status": "unconfirmed",
                                       "cost_usd": None, "held_usd": "0.10", "error": "Timeout"}),
    (35, "credit.charge", "alice", {"what": "research tokens", "usd": "0.50", "detail": {"session": "S1", "turn": 0}}),
    (36, "credit.charge", "bob", {"what": "research tokens", "usd": "0.40", "detail": {"session": "S2", "turn": 0}}),
    (37, "credit.charge", "bob", {"what": "sandbox seconds", "usd": "0.05", "detail": {"seconds": 5}}),
    (38, "credit.charge", "bob", {"what": "web search", "usd": "0.01", "detail": {"query": "q"}}),
    (39, "credit.charge", "bob", {"what": "jev classification", "usd": "0.002", "detail": {"session": "S2", "items": 3}}),
    (40, "credit.charge", "alice", {"what": "merton's time", "usd": "1.00", "detail": {"session": "S1"}}),
    (41, "credit.charge", "alice", {"what": "frontier audit", "usd": "0.25", "detail": {"model": "gpt-6-astra"}}),
    (42, "merton.pass", "house", {"role": "consultant", "agent": "alice", "cost_usd": "1.00"}),
    (43, "merton.pass", "house", {"role": "architect", "cost_usd": "2.00"}),
    (44, "audit.verdict", "alice", {"approve": False, "cost_usd": "0.25"}),
    (45, "agent.research", "bob", {"tool": "research_grant", "status": "completed", "session": "S2", "cost_usd": "0.15"}),
    (46, "ops.budget", "house", {"what": "sail", "spent_usd": "0.30", "balance_usd": "99.70"}),
    (47, "ops.budget", "house", {"what": "sail", "spent_usd": "0.40", "balance_usd": "99.30"}),
    # --- useful work
    (50, "agent.research", "bob", {"tool": "candidate", "status": "retained", "session": "S2",
                                   "_candidate": {"passed": True, "code": "a", "numbers": {"code_sha256": "a"}}}),
    (51, "agent.research", "bob", {"tool": "candidate", "status": "retained", "session": "S2",
                                   "_candidate": {"passed": True, "code": "a", "numbers": {"code_sha256": "a"}}}),
    (52, "agent.research", "bob", {"tool": "candidate", "status": "retained", "session": "S2",
                                   "_candidate": {"passed": True, "code": "b", "numbers": {"code_sha256": "b"}}}),
    (53, "agent.research", "bob", {"tool": "candidate", "status": "retained", "session": "S2",
                                   "_candidate": {"passed": False, "code": "c", "numbers": {"code_sha256": "c"}}}),
    (54, "agent.research", "bob", {"tool": "candidate", "status": "not_adopted", "session": "S2",
                                   "_candidate": {"passed": True, "code": "a", "numbers": {"code_sha256": "a"}}}),
    (55, "eval.verdict", "bob", {"decision": "promote", "from_rung": 0, "to_rung": 1, "reason": econ.ADOPT_PROMOTE_REASON}),
    (56, "eval.verdict", "dave", {"decision": "seat", "from_rung": 0, "to_rung": 1, "reason": econ.ADOPT_SEAT_REASON}),
    (57, "eval.verdict", "erin", {"decision": "promote", "from_rung": 0, "to_rung": 1, "reason": econ.NEWBORN_PROMOTE_REASON}),
    (58, "agent.strategy", "carol", {"passed_replay": True, "reason": "it rewrote itself: it had no record to protect"}),
    (59, "agent.strategy", "carol", {"passed_replay": False, "reason": "it rewrote itself: its own rules had not fired"}),
    (60, "repair.status", "house", {"repair_id": "r1", "state": "testing"}),
    (61, "repair.status", "house", {"repair_id": "r1", "state": "verified", "cost_usd": "0.40"}),
]


def build_ledger(path: Path) -> None:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE ledger(seq INTEGER PRIMARY KEY, id TEXT UNIQUE, kind TEXT, agent TEXT, at TEXT, public INTEGER,"
               " payload TEXT, previous_hash TEXT, digest TEXT)")
    for n, (minute, kind, agent, payload) in enumerate(ROWS, start=1):
        db.execute("INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?,?)",
                   (n, f"row-{n}", kind, agent, at(minute), 1, json.dumps(payload), "", ""))
    db.commit()
    db.close()


class EconomicsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.sqlite"
        build_ledger(self.path)
        self.report = econ.build(str(self.path), semantic_db=None, start_equity="1000")

    def tearDown(self):
        self.tmp.cleanup()

    def book(self, section, name):
        return next(b for b in self.report["trading"][section]["books"] if b["book"] == name)

    def test_real_and_practice_are_separate_and_fees_are_subtracted(self):
        trading = self.report["trading"]
        self.assertEqual([b["book"] for b in trading["real"]["books"]], ["kalshi"])
        self.assertEqual([b["book"] for b in trading["practice"]["books"]], ["alpaca-paper", "kalshi-shadow"])
        real = trading["real"]["total"]
        self.assertEqual((real["closed_trades"], real["wins"], real["losses"]), (1, 1, 0))
        self.assertEqual(real["realized_gross"], D("6.00"))
        self.assertEqual(real["fees_on_closed"], D("0.20"))
        self.assertEqual(real["realized_net"], D("5.80"))
        self.assertEqual(real["house_row"], D("-0.05"))
        self.assertEqual(real["net_after_costs"], D("5.75"))
        self.assertEqual(real["fees_paid"], D("0.25"))
        self.assertEqual(trading["real"]["mark_to_market_change"], D("5.75"))
        self.assertEqual(trading["real"]["staked_outstanding"], D("50"))

        paper = self.book("practice", "alpaca-paper")["window"]
        self.assertEqual((paper["realized_gross"], paper["fees_on_closed"], paper["realized_net"]), (D("-10.00"), D("0.50"), D("-10.50")))
        shadow = self.book("practice", "kalshi-shadow")["window"]
        self.assertEqual((shadow["realized_gross"], shadow["fees_on_closed"], shadow["realized_net"]), (D("-3.00"), D("0.10"), D("-3.10")))
        practice = trading["practice"]["total"]
        self.assertEqual(practice["closed_trades"], 2)
        self.assertEqual(practice["realized_net"], D("-13.60"))
        self.assertEqual(practice["realized_gross"], D("-13.00"))
        self.assertEqual(trading["practice"]["mark_to_market_change"], D("-13.60"))
        # Nothing anywhere adds the two sections: no combined total exists.
        self.assertEqual(set(trading), {"real", "practice"})
        for book in trading["real"]["books"] + trading["practice"]["books"]:
            self.assertEqual(book["check"]["difference"], D(0))

    def test_site_account_definition(self):
        site = self.report["site_account"]
        self.assertEqual(site["definition_doc"], "docs/account-performance.md")
        self.assertEqual(site["pnl_total"], D("5.75"))  # account_equity - start_equity, net flows 0
        self.assertEqual(site["recomputed_from_books"], D("5.75"))
        self.assertEqual(site["since_inception_pct"], D("0.575"))
        self.assertEqual(site["raw_balance_change"], D("10.00"))
        self.assertIn("not recorded in the ledger", site["raw_note"])
        self.assertEqual(site["pnl_less_all_spend"], D("5.75") - D("4.612"))

    def test_missing_start_equity_is_reported_not_invented(self):
        conn = econ.connect_ro(str(self.path))
        try:
            site = econ.site_basis(conn, {"start_equity": None, "start_at": None, "source": None},
                                   self.report["trading"]["real"], None, None)
        finally:
            conn.close()
        self.assertNotIn("pnl_total", site)
        self.assertIn("start_equity", site["missing"])
        self.assertEqual(site["account_equity"], D("1005.75"))

    def test_spend_by_provider(self):
        spent = self.report["spend"]
        self.assertEqual(spent["providers"]["openai-luna"], D("0.50"))
        self.assertEqual(spent["providers"]["openai-astra"], D("3.40"))  # architect 2 + consult 1 + audit .25 + grant .15
        self.assertEqual(spent["providers"]["sail"], D("0.70"))  # the balance meter, not the 0.45 attributed estimate
        self.assertEqual(spent["providers"]["jev"], D("0.002"))
        self.assertEqual(spent["providers"]["web-search"], D("0.01"))
        self.assertEqual(spent["total"], D("4.612"))
        self.assertEqual(spent["total_estimated"], D("0.01"))
        checks = spent["checks"]
        self.assertEqual(checks["luna_research_token_charges"], D("0.50"))
        self.assertEqual(checks["sail_attributed"], D("0.45"))
        self.assertEqual(checks["merton_consult_charges"], checks["merton_consult_rows"])
        unconfirmed = [i for i in spent["lines"] if "unconfirmed" in i["component"]]
        self.assertEqual((unconfirmed[0]["usd"], unconfirmed[0]["in_total"]), (D("0.10"), False))
        research = spent["research_spend"]
        self.assertEqual(research["total"], D("2.052"))  # luna .5 + sail tokens .4 + consult 1 + grant .15 + jev .002

    def test_useful_work_per_dollar(self):
        work = self.report["useful_work"]
        self.assertEqual(work["replay_passing_candidates"], 2)
        self.assertEqual(work["replay_passing_rows"], 3)
        self.assertEqual(work["replay_failing_candidates"], 1)
        self.assertEqual(work["adoptions"], 3)
        self.assertEqual(work["candidates_per_usd"], D(2) / D("2.052"))
        self.assertEqual(work["adoptions_per_usd"], D(3) / D("2.052"))
        self.assertEqual(work["verified_repairs"], 1)
        self.assertEqual(work["denominator_repairs_usd"], D("0.40"))
        self.assertEqual(work["verified_repairs_per_usd"], D("2.5"))

    def test_small_sample_warnings(self):
        text = "\n".join(self.report["warnings"])
        self.assertIn("real book kalshi: 1 closed trade(s) (< 30)", text)
        self.assertIn("practice book alpaca-paper: 1 closed trade(s)", text)
        self.assertIn("3 adoption(s) (< 5)", text)
        self.assertIn("(< 24 h)", text)
        self.assertIn("tiny stakes", text)
        self.assertIn("never compare books, desks or providers with unequal stakes", text)
        self.assertIn("unknown bills", text)

    def test_window(self):
        # Opens after the real settlement, the House fee and both real marks: nothing real moved inside it.
        report = econ.build(str(self.path), since=at(6), semantic_db=None, start_equity="1000")
        real = report["trading"]["real"]
        self.assertEqual(real["total"]["closed_trades"], 0)
        self.assertEqual(real["total"]["house_row"], D(0))
        self.assertEqual(real["mark_to_market_change"], D(0))
        self.assertEqual(report["site_account"]["window_change"], D(0))
        self.assertEqual(report["trading"]["practice"]["total"]["closed_trades"], 2)

    def test_render_and_json(self):
        text = econ.render(self.report)
        self.assertIn("docs/account-performance.md", text)
        self.assertIn("REAL MONEY", text)
        self.assertIn("PRACTICE MONEY", text)
        json.dumps(econ.to_json(self.report))

    def test_database_is_opened_read_only(self):
        conn = econ.connect_ro(str(self.path))
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("INSERT INTO ledger(kind, agent, at, payload) VALUES('x', 'y', 'z', '{}')")
        finally:
            conn.close()
        db = sqlite3.connect(self.path)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0], len(ROWS))
        db.close()


if __name__ == "__main__":
    unittest.main()
