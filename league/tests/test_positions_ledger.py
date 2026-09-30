"""The site's positions table (the owner, Sept 28, 2026): every real-options position on the Brokerage Account since the
reset, open and closed, the House's calibration round trips among them, and the account's other activity, adding up to
Profit to the cent; nothing a quote licence forbids ever in it; a difference the book cannot account for shown and
alerted, never hidden. The book is the live path's own schema (`league/live/state.py`, read only); the broker's record
has the venue's shapes with invented numbers (the data licence forbids publishing quotes)."""

import json
import random
import re
import shutil
import sqlite3
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league.account_activity import (
    FULL_EVERY_SECONDS, SETTLE_SECONDS, ActivityLedger, Unreadable, activities_after, classify, epoch, orders_after, read_book,
)
from league.ledger import Ledger
from league.live.state import LiveState
from league.publish import MAX_POSITIONS, POSITIONS_RETRY_SECONDS, Publisher, SiteInputs, build_checkpoint
from league.trading_profit import CALIBRATION_FAMILY, OTHER_PARTS, cents, complete, ledger

RESET_AT = "2026-09-26T06:25:30.000Z"
PUBLISHED_AT = "2026-09-28T19:00:00.000Z"
NOW = epoch(PUBLISHED_AT)
T0 = epoch("2026-09-28T14:10:00.000Z")
# The site's own list (personal-site test/league-contract.test.mjs): no key anywhere is ever one of these.
FORBIDDEN_KEYS = re.compile(r"^(?:bid|ask|mid|mark|last|spread|iv|implied_vol|vol|delta|gamma|theta|vega|rho|greeks?|surface|strike|strikes|"
                            r"price|prices|entry_price|exit_price|mark_price|underlying_price|params|parameters|quote|quotes|nbbo|program|"
                            r"code|legs_detail)$", re.IGNORECASE)
ROW_KEYS = {"id", "source", "agent", "underlying", "structure", "right", "legs", "quantity", "open_quantity", "status", "expiry",
            "opened_at", "closed_at", "pnl_usd"}
# The site's exact block (personal-site capital/schema.js `POSITIONS_FIELDS`, the review of #408's blocker).
BLOCK_KEYS = {"as_of", "rows", "earlier", "other", "unreconciled_usd"}
EST = D("0.05")      # the book's fee estimate a contract a leg (invented)
CHARGED = D("-0.03")  # the broker's charged fee a contract a leg (invented)


def iso(seconds):
    from league.account_activity import iso as _iso

    return _iso(seconds)


def keys(value, found=None):
    found = [] if found is None else found
    if isinstance(value, dict):
        for key, item in value.items():
            found.append(key)
            keys(item, found)
    elif isinstance(value, list):
        for item in value:
            keys(item, found)
    return found


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


class Account:
    """A live book (`<root>/live.sqlite`, the live path's own schema, written as `RealBook` writes it) and the broker's
    record of the same trades: its orders (nested legs) and its activities (a FILL per leg fill, a FEE per leg fill)."""

    def __init__(self, root):
        self.root = Path(root)
        LiveState(self.root / "live.sqlite").close()
        self.db = sqlite3.connect(self.root / "live.sqlite", isolation_level=None)
        self.activities, self.orders, self.marks = [], [], {}
        self.expected_fees = D(0)       # what Other's fees line must say (fees no position carries)
        self.expected_cash = {}         # pid -> the position's P&L before any mark, exact, at the book's fee estimates
        self.expected_fix = {}          # pid -> the broker's posted fees less the book's estimates, in the row itself
        self.seq = 0

    def close(self):
        self.db.close()

    def _id(self, stamp):
        self.seq += 1
        return f"{stamp}::{self.seq:08d}-0000-4000-8000-000000000000"

    def activity(self, kind, *, day="2026-09-28", **fields):
        row = {"id": self._id(day.replace("-", "") + "000000000"), "activity_type": kind, "date": day, **fields}
        self.activities.append(row)
        return row

    def position(self, family, type_, root, legs, *, at, expiry="2026-10-02"):
        pid = 1 + (self.db.execute("SELECT MAX(pid) FROM positions").fetchone()[0] or 0)
        rows = [{"symbol": f"{root}{expiry[2:4]}{expiry[5:7]}{expiry[8:10]}{right}{int(strike * 1000):08d}", "side": side, "ratio": ratio,
                 "is_call": right == "C", "strike": float(strike), "expiry": expiry, "key": n} for n, (right, strike, side, ratio) in enumerate(legs)]
        self.db.execute("INSERT INTO positions(pid, instance, family, type, root, legs, qty, opened_qty, entry, max_loss_share, collateral,"
                        " opened_at, opened_day, opened_minute, status, info) VALUES (?,?,?,?,?,?,0,0,0,0,0,?,?,0,'open',?)",
                        (pid, f"{family}@1:l", family, type_, root, json.dumps(rows), at, iso(at)[:10], json.dumps({})))
        self.expected_cash[pid] = D(0)
        self.expected_fix[pid] = D(0)
        return pid

    def order(self, pid, action, parts, *, at, posted=None, client=None, venue_prices=None):
        """One order of `pid` filled in `parts` [(structures, [each leg's price])]; the broker charges each leg fill's
        fee, posted for the first `posted` legs (all of them when None). `venue_prices` makes the broker's fills differ."""
        pos = self.db.execute("SELECT * FROM positions WHERE pid=?", (pid,)).fetchone()
        cols = [c[0] for c in self.db.execute("SELECT * FROM positions LIMIT 0").description]
        pos = dict(zip(cols, pos))
        legs = json.loads(pos["legs"])
        oid = 1 + (self.db.execute("SELECT MAX(oid) FROM orders").fetchone()[0] or 0)
        venue_id = f"venue-{oid:04d}-0000-4000-8000-000000000000"
        client = client or f"lv-abcd1234-{oid:07d}-{pos['family'].replace(':', '-')}"
        single = len(legs) == 1
        venue_legs = [{"id": venue_id if single else f"leg-{oid:04d}-{n}", "filled_qty": "0"} for n in range(len(legs))]
        fills_at = at
        cash, fees, filled = float(pos["cash"]), float(pos["fees"]), 0
        estimate_total = D(0)
        opening = action == "open"
        for part, (qty, prices) in enumerate(parts):
            value = sum(leg["side"] * leg["ratio"] * price for leg, price in zip(legs, prices))
            estimate = float(sum(EST * leg["ratio"] * qty for leg in legs))
            estimate_total += D(str(estimate))
            cash += (-value if opening else value) * 100 * qty - estimate
            fees += estimate
            filled += qty
            self.db.execute("INSERT INTO fills(oid, pid, qty, value, fees, at) VALUES (?,?,?,?,?,?)",
                            (oid, pid, qty, round(value, 6), estimate, fills_at + part))
            shown = venue_prices or prices
            for n, (leg, price) in enumerate(zip(legs, shown)):
                buys = (leg["side"] > 0) == opening
                self.activity("FILL", day=iso(fills_at + part)[:10], transaction_time=iso(fills_at + part), symbol=leg["symbol"],
                              side="buy" if buys else "sell", qty=str(leg["ratio"] * qty), price=str(price), order_id=venue_legs[n]["id"])
                venue_legs[n]["filled_qty"] = str(int(venue_legs[n]["filled_qty"]) + leg["ratio"] * qty)
                self.expected_cash[pid] += (-1 if buys else 1) * D(str(price)) * leg["ratio"] * qty * 100
        self.expected_cash[pid] -= estimate_total
        qty = int(pos["qty"]) + (filled if opening else -filled)
        opened_qty = int(pos["opened_qty"]) + (filled if opening else 0)
        status = "closed" if qty == 0 else "open"
        info = json.loads(pos["info"])
        if opening and "order" not in info:
            info["order"] = oid
        self.db.execute("UPDATE positions SET qty=?, opened_qty=?, cash=?, fees=?, status=?, closed_at=?, info=? WHERE pid=?",
                        (qty, opened_qty, cash, fees, status, fills_at + 30 if status == "closed" else None, json.dumps(info), pid))
        answer = {"filled_at": iso(fills_at + len(parts) - 1), "final": "filled"}
        self.db.execute("INSERT INTO orders(oid, client_id, venue_id, instance, family, action, type, root, legs, qty, limit_value, limit_price,"
                        " placed_at, day, placed_minute, status, filled_qty, pid, answer, updated_at) VALUES"
                        " (?,?,?,?,?,?,?,?,?,?,0,'0',?,?,0,'filled',?,?,?,?)",
                        (oid, client, venue_id, pos["instance"], pos["family"], action, pos["type"], pos["root"], pos["legs"], filled,
                         at - 5, iso(at)[:10], filled, pid, json.dumps(answer), fills_at + 40))
        self.orders.append({"id": venue_id, "client_order_id": client, "filled_qty": str(filled), "submitted_at": iso(at - 5),
                            "legs": [] if single else venue_legs})
        posted = len(legs) if posted is None else posted
        for n, leg in enumerate(legs[:posted]):
            self.activity("FEE", day=iso(fills_at)[:10], order_id=venue_legs[n]["id"], net_amount=str(CHARGED * leg["ratio"] * filled),
                          description="OCC Clearing Fee")
        if posted == len(legs) and at > epoch(RESET_AT):
            self.expected_fix[pid] += sum(CHARGED * leg["ratio"] * filled for leg in legs) + estimate_total
        return oid

    def mark(self, pid, value):
        self.marks[pid] = D(str(value))

    def expected_row(self, pid):
        return cents(self.expected_cash[pid] + self.marks.get(pid, D(0)) + self.expected_fix.get(pid, D(0)))


def marked(account):
    """`trading_profit.marked_value` for the fake book: the test's own remaining values, marked a minute ago."""
    return lambda row, day: (account.marks[int(row["pid"])], iso(NOW - 60)) if int(row["pid"]) in account.marks else None


LIVE = SimpleNamespace(day=object(), book=SimpleNamespace(frozen=""))


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="positions-")
        self.account = Account(self.dir)

    def tearDown(self):
        self.account.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def reading(self, *, now=NOW, shares=None):
        """What the broker's reads after the reset return (`after=start_at`), classified beside the book; `shares` is
        whether the account holds any shares (None: it cannot tell)."""
        start = epoch(RESET_AT)
        activities = [a for a in self.account.activities if (epoch(a.get("transaction_time") or a.get("date")) or 0) > start]
        orders = [o for o in self.account.orders if o.get("submitted_at") is None or epoch(o["submitted_at"]) > start]
        return {"as_of": iso(now), **classify(activities, orders, read_book(self.dir, RESET_AT), now=now, shares_held=lambda: shares)}

    def symbols(self, pid):
        return [leg["symbol"] for leg in json.loads(self.account.db.execute("SELECT legs FROM positions WHERE pid=?", (pid,)).fetchone()[0])]

    def table(self, reading=None, *, fresh=True):
        with patch("league.trading_profit.marked_value", side_effect=marked(self.account)):
            book = ledger(self.dir, LIVE, at=PUBLISHED_AT, start_at=RESET_AT)
        trading, positions = complete(book, (reading or self.reading()) if fresh else None, at=PUBLISHED_AT)
        return build_checkpoint(SiteInputs(trading=trading, positions=positions), PUBLISHED_AT)

    def assert_adds_up(self, body):
        """The site's own rule (`validPositions`): the rows, `earlier`, Other's four parts and `unreconciled_usd` add up
        to Profit exactly."""
        block, profit = body["positions"], body["trading"]["pnl_usd"]
        c = lambda text: int(D(text) * 100)  # noqa: E731
        lines = [row["pnl_usd"] for row in block["rows"]] + ([block["earlier"]["pnl_usd"]] if block["earlier"] else [])
        lines += [block["other"][part] for part in OTHER_PARTS] + [block["unreconciled_usd"]]
        self.assertEqual(sum(map(c, lines)), c(profit))
        self.assertEqual(block["as_of"], body["trading"]["as_of"])

    def the_week(self):
        """The House's calibration, an agent's vertical filled in two parts and still open, a long put partly closed, a
        condor closed before its fees posted, a retired agent's long call; the account's own crypto fees, interest, a
        dividend, the owner's deposit and the legacy coins' sale; and a position from before the reset."""
        a = self.account
        early = a.position("gap-drift", "long_put", "QQQ", [("P", 500, 1, 1)], at=epoch("2026-09-25T15:00:00Z"))
        a.order(early, "open", [(1, [1.00])], at=epoch("2026-09-25T15:00:00Z"))
        cal = a.position(CALIBRATION_FAMILY, "debit_vertical", "SPY", [("C", 600, 1, 1), ("C", 601, -1, 1)], at=T0)
        a.order(cal, "open", [(1, [1.52, 0.51])], at=T0)
        a.order(cal, "close", [(1, [1.49, 0.50])], at=T0 + 10)
        orb = a.position("orb-4", "debit_vertical", "SPY", [("P", 580, 1, 1), ("P", 575, -1, 1)], at=T0 + 600)
        a.order(orb, "open", [(1, [2.10, 1.30]), (1, [2.14, 1.31])], at=T0 + 600, posted=1)
        a.mark(orb, "171.00")
        gap = a.position("gap-drift", "long_put", "QQQ", [("P", 500, 1, 1)], at=T0 + 1200)
        a.order(gap, "open", [(3, [1.07])], at=T0 + 1200)
        a.order(gap, "close", [(1, [1.35])], at=T0 + 3000)
        a.mark(gap, "240.00")
        condor = a.position("condor-vrp-3", "iron_condor", "XSP", [("P", 560, 1, 1), ("P", 565, -1, 1), ("C", 580, -1, 1), ("C", 585, 1, 1)],
                            at=T0 + 1800)
        a.order(condor, "open", [(1, [0.40, 0.95, 0.90, 0.38])], at=T0 + 1800, posted=0)
        a.order(condor, "close", [(1, [0.20, 1.60, 0.30, 0.05])], at=T0 + 5400, posted=0)
        old = a.position("reversal-1", "long_call", "SPY", [("C", 610, 1, 1)], at=T0 + 2400)
        a.order(old, "open", [(2, [0.66])], at=T0 + 2400)
        a.order(old, "close", [(2, [0.12])], at=T0 + 4800)
        a.activity("CFEE", order_id="coin-sale", net_amount="-0.04", description="Coin Pair Transaction Fee (USD)")
        a.activity("CFEE", symbol="SOLUSD", qty="-0.000057", order_id="coin-sale", net_amount="0")
        a.activity("INT", net_amount="0.17")
        a.activity("DIV", symbol="SPY", net_amount="0.05")
        a.activity("CSD", net_amount="1000")
        a.activity("FILL", day="2026-09-26", transaction_time="2026-09-26T06:25:38.895Z", symbol="SOL/USD", side="sell", qty="0.1", price="150",
                   order_id="coin-sale")
        return {"early": early, "cal": cal, "orb": orb, "gap": gap, "condor": condor, "old": old}


class AddsUpTest(Case):
    def test_the_rows_and_other_add_up_to_profit_to_the_cent(self):
        pids = self.the_week()
        body = self.table()
        block = body["positions"]
        self.assert_adds_up(body)
        self.assertEqual(block["unreconciled_usd"], "0.00", "the book and the broker agree")
        self.assertIsNone(block["earlier"])
        rows = {row["id"]: row for row in block["rows"]}
        self.assertNotIn(f"real:{pids['early']}", rows, "opened before the reset: not this record's")
        for name in ("cal", "orb", "gap", "condor", "old"):
            self.assertEqual(rows[f"real:{pids[name]}"]["pnl_usd"], format(self.account.expected_row(pids[name]), ".2f"), name)
        # The review of #408 (5): a posted fee belongs to its position's own row, never to Other. Worked by hand: the
        # calibration's -2.20 at the book's estimates is -2.12 with the broker's fees (0.04 on each order); the long put's
        # and the long call's fees posted too; the vertical's and the condor's are still estimated.
        self.assertEqual(rows[f"real:{pids['cal']}"]["pnl_usd"], "-2.12")
        self.assertEqual(self.account.expected_fix[pids["gap"]], D("0.08"))
        self.assertEqual(self.account.expected_fix[pids["old"]], D("0.08"))
        self.assertEqual((self.account.expected_fix[pids["orb"]], self.account.expected_fix[pids["condor"]]), (D(0), D(0)))
        self.assertEqual(block["other"]["fees_usd"], "0.00", "no fee here that a position carries")
        self.assertEqual((block["other"]["crypto_usd"], block["other"]["interest_usd"], block["other"]["misc_usd"]), ("-0.04", "0.17", "0.05"))
        expected = sum(self.account.expected_row(pids[n]) for n in ("cal", "orb", "gap", "condor", "old")) - D("0.04") + D("0.17") + D("0.05")
        self.assertEqual(body["trading"]["pnl_usd"], format(expected, ".2f"))

    def test_each_row_says_whose_what_and_when_and_open_rows_come_first(self):
        pids = self.the_week()
        rows = self.table()["positions"]["rows"]
        self.assertEqual([row["status"] for row in rows], ["open", "open", "closed", "closed", "closed"])
        self.assertEqual([row["id"] for row in rows[:2]], [f"real:{pids['gap']}", f"real:{pids['orb']}"], "newest open first")
        cal = next(row for row in rows if row["id"] == f"real:{pids['cal']}")
        self.assertEqual(cal, {"id": f"real:{pids['cal']}", "source": "calibration", "agent": None, "underlying": "SPY", "structure": "debit_vertical",
                               "right": "call", "legs": 2, "quantity": 1, "open_quantity": 0, "status": "closed", "expiry": "2026-10-02",
                               "opened_at": "2026-09-28T14:10:00.000Z", "closed_at": "2026-09-28T14:10:00.000Z",
                               "pnl_usd": format(self.account.expected_row(pids["cal"]), ".2f")})
        gap = next(row for row in rows if row["id"] == f"real:{pids['gap']}")
        self.assertEqual((gap["source"], gap["agent"], gap["structure"], gap["right"], gap["quantity"], gap["open_quantity"], gap["closed_at"]),
                         ("agent", "gap-drift", "long_put", "put", 3, 2, None), "partly closed: three opened, two held")
        condor = next(row for row in rows if row["id"] == f"real:{pids['condor']}")
        self.assertEqual((condor["right"], condor["legs"]), ("both", 4))
        orb = next(row for row in rows if row["id"] == f"real:{pids['orb']}")
        self.assertEqual(orb["opened_at"], "2026-09-28T14:20:00.000Z", "the broker's fill time of the whole open (two parts), to the minute")
        # The review of #408 (N2): a fill time to the millisecond is a lookup key into the public time and sales.
        for row in rows:
            for at in (row["opened_at"], row["closed_at"]):
                self.assertTrue(at is None or at.endswith(":00.000Z"), at)

    def test_calibration_is_in_profit(self):
        a = self.account
        cal = a.position(CALIBRATION_FAMILY, "debit_vertical", "SPY", [("C", 600, 1, 1), ("C", 601, -1, 1)], at=T0)
        a.order(cal, "open", [(1, [0.98, 0.00])], at=T0)
        a.order(cal, "close", [(1, [0.96, 0.00])], at=T0 + 10)
        a.activity("CFEE", order_id="coin-sale", net_amount="-0.04")
        a.activity("CFEE", order_id="coin-sale-2", net_amount="-0.04")
        body = self.table()
        # Sept 28, 2026 in shape, invented prices: -2.00 of fills; the broker charged 0.12 of fees (the book estimated
        # 0.20); the coins' sale charged 0.08. The row is the trade's real -2.12 (the review of #408, 5) and Profit -2.20.
        self.assertEqual(body["positions"]["rows"][0]["pnl_usd"], "-2.12")
        self.assertEqual((body["positions"]["other"]["fees_usd"], body["positions"]["other"]["crypto_usd"]), ("0.00", "-0.08"))
        self.assertEqual(body["trading"]["pnl_usd"], "-2.20")
        self.assert_adds_up(body)

    def test_random_books_always_add_up_exactly(self):
        rng = random.Random(20260928)
        for trial in range(40):
            self.tearDown()
            self.setUp()
            a = self.account
            for n in range(rng.randint(1, 14)):  # an empty book is unknown unless the House never traded (its own test)
                kind = rng.choice(["long_call", "long_put", "debit_vertical"])
                legs = ([("C" if kind == "long_call" else "P", 500 + n, 1, 1)] if kind != "debit_vertical"
                        else [("C", 500 + n, 1, 1), ("C", 505 + n, -1, 1)])
                pid = a.position(rng.choice([CALIBRATION_FAMILY, "orb-4", "gap-drift", "skew-revert"]), kind, rng.choice(["SPY", "QQQ", "XSP"]),
                                 legs, at=T0 + 60 * n)
                qty = rng.randint(1, 5)
                price = lambda: round(rng.uniform(0.05, 9.99), 2)  # noqa: E731
                parts = [(1, [price() for _ in legs]) for _ in range(qty)] if rng.random() < 0.3 else [(qty, [price() for _ in legs])]
                a.order(pid, "open", parts, at=T0 + 60 * n, posted=rng.choice([None, 0, 1]))
                left = qty
                if rng.random() < 0.6:
                    out = rng.randint(1, qty)
                    a.order(pid, "close", [(out, [price() for _ in legs])], at=T0 + 60 * n + 30, posted=rng.choice([None, 0]))
                    left -= out
                if left:
                    a.mark(pid, f"{rng.uniform(0, 900):.2f}")
            for _ in range(rng.randint(0, 3)):
                a.activity(rng.choice(["INT", "CFEE", "DIV", "PTC"]), net_amount=f"{rng.uniform(-2, 2):.2f}")
            body = self.table()
            self.assert_adds_up(body)
            self.assertEqual(body["positions"]["unreconciled_usd"], "0.00", trial)
            for row in body["positions"]["rows"]:
                self.assertEqual(row["pnl_usd"], format(a.expected_row(int(row["id"].split(":")[1])), ".2f"), trial)

    def test_past_the_tables_length_the_oldest_closed_rows_fold_into_one_line(self):
        a = self.account
        for n in range(MAX_POSITIONS + 25):
            pid = a.position("orb-4", "long_call", "SPY", [("C", 600, 1, 1)], at=T0 + n)
            a.order(pid, "open", [(1, [1.00 + (n % 7) / 100])], at=T0 + n)
            a.order(pid, "close", [(1, [1.01])], at=T0 + n + 0.5)
        body = self.table()
        block = body["positions"]
        self.assertEqual(len(block["rows"]), MAX_POSITIONS)
        self.assertEqual(block["earlier"]["positions"], 25)
        self.assertEqual(block["rows"][-1]["id"], "real:26", "the most recently closed stay; the first 25 fold")
        self.assert_adds_up(body)
        self.assertEqual(block["unreconciled_usd"], "0.00")

    def test_the_byte_limit_folds_rows_rather_than_dropping_them(self):
        from league import publish

        self.the_week()
        body = self.table()
        from league.ledger import canonical

        with patch.object(publish, "MAX_CHECKPOINT_BYTES", len(canonical(body).encode("utf-8")) - 100):
            small = publish.fit(json.loads(json.dumps(body)))
        self.assertLess(len(small["positions"]["rows"]), len(body["positions"]["rows"]))
        self.assertIsNotNone(small["positions"]["earlier"])
        self.assertTrue(all(row["status"] == "open" for row in small["positions"]["rows"]), "the oldest closed fold first")
        self.assert_adds_up(small)
        self.assertEqual(small["positions"]["unreconciled_usd"], body["positions"]["unreconciled_usd"])


class UnknownTest(Case):
    def test_without_a_fresh_reading_of_the_account_profit_is_unknown_and_the_rows_still_show(self):
        pids = self.the_week()
        body = self.table(fresh=False)
        block = body["positions"]
        self.assertIsNone(body["trading"]["pnl_usd"])
        self.assertEqual((block["other"], block["unreconciled_usd"]), (None, None))
        self.assertEqual(len(block["rows"]), 5)
        self.assertEqual(next(r for r in block["rows"] if r["id"] == f"real:{pids['cal']}")["pnl_usd"], "-2.20",
                         "without the account's reading, the book's own fee estimates stand")

    def test_an_unpriced_row_or_an_uncertain_order_makes_profit_unknown_never_zero(self):
        pids = self.the_week()
        del self.account.marks[pids["gap"]]
        body = self.table()
        self.assertIsNone(body["trading"]["pnl_usd"])
        self.assertIsNone(next(r for r in body["positions"]["rows"] if r["id"] == f"real:{pids['gap']}")["pnl_usd"])
        self.assertEqual(body["positions"]["unreconciled_usd"], "0.00", "while Profit is unknown, the reading's own figure")
        self.account.mark(pids["gap"], "240.00")
        self.account.db.execute("UPDATE orders SET status='unknown' WHERE oid=(SELECT MAX(oid) FROM orders)")
        self.assertIsNone(self.table()["trading"]["pnl_usd"], "a calibration's or an agent's uncertain order alike")
        self.assertTrue(all(row["pnl_usd"] is not None for row in self.table()["positions"]["rows"]), "the rows themselves are all priced")

    def test_an_unreadable_book_publishes_no_table(self):
        (Path(self.dir) / "live.sqlite").write_bytes(b"not a database")
        body = self.table(fresh=False)
        self.assertNotIn("positions", body)
        self.assertIsNone(body["trading"]["pnl_usd"])


class LicenceTest(Case):
    def test_no_price_strike_quote_or_contract_ever_leaves_whatever_the_rows_carry(self):
        self.the_week()
        with patch("league.trading_profit.marked_value", side_effect=marked(self.account)):
            book = ledger(self.dir, LIVE, at=PUBLISHED_AT, start_at=RESET_AT)
        smuggle = {"strike": 600.0, "price": "1.52", "mark": "171.00", "bid": 1.0, "ask": 1.1, "quote": "1.52 x 1.55", "symbol": "SPY261002C00600000",
                   "legs_detail": [{"strike": 600}], "entry": 1.01, "exit_value": 0.99, "fill_price": "1.52", "delta": 0.3, "code": "SPY|x"}
        book["rows"] = [{**row, **smuggle} for row in book["rows"]]
        trading, positions = complete(book, {**self.reading(), **smuggle}, at=PUBLISHED_AT)
        positions = {**positions, **smuggle, "other": {**positions["other"], **smuggle}}
        body = build_checkpoint(SiteInputs(trading=trading, positions=positions), PUBLISHED_AT)
        block = body["positions"]
        self.assertEqual(set(block), BLOCK_KEYS)
        self.assertEqual(set(block["other"]), {"as_of", *OTHER_PARTS})
        for row in block["rows"]:
            self.assertEqual(set(row), ROW_KEYS)
        for key in keys(block):
            self.assertNotRegex(key, FORBIDDEN_KEYS)
        for text in strings(block):
            self.assertNotRegex(text, r"[A-Z]+\d{6}[CP]\d{8}", "never a contract's code (it carries the strike)")
            self.assertTrue(re.match(r"^(?:\d{4}-\d\d-\d\d(?:T[\d:.]+Z)?|-?\d+\.\d\d|real:\d+|[a-z0-9-]+|[a-z_]+|[A-Z]{1,10})$", text), text)
        self.assertNotIn("600", json.dumps(block).replace("real:", ""), "no strike, anywhere")
        self.assert_adds_up(body)

    def test_the_accounts_problems_name_ids_never_prices_or_contracts(self):
        self.the_week()
        self.account.activity("FILL", transaction_time=iso(T0), symbol="SPY261002C00650000", side="buy", qty="1", price="3.21", order_id="owner-1")
        self.account.activity("XYZ", net_amount="1.23")
        problems = self.reading()["problems"]
        self.assertEqual(len(problems), 2)
        for text in problems:
            self.assertNotIn("3.21", text)
            self.assertNotIn("1.23", text)
            self.assertNotRegex(text, r"[A-Z]+\d{6}[CP]\d{8}")


class House:
    def __init__(self, ledger):
        self.ledger, self.alerts, self.books = ledger, [], {}
        self.registry = SimpleNamespace(living=lambda: [], dead=lambda: [])
        self.evaluator = SimpleNamespace(rung=lambda agent_id: 0)
        self.options_live = LIVE

    def alert(self, level, text, **payload):
        self.alerts.append((level, text))


class Response:
    def __init__(self, status, body):
        self.status, self._body = status, json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Site:
    """The Worker: a site that predates the positions table refuses any checkpoint carrying it (400, exact schema)."""

    def __init__(self, takes_positions=True):
        self.takes_positions, self.posts, self.reply = takes_positions, [], b'{"error":"Invalid checkpoint."}'

    def __call__(self, request, timeout=None):
        import urllib.error

        body = json.loads(request.data)
        self.posts.append((request.full_url.rsplit("/", 1)[1], body))
        if request.full_url.endswith("/checkpoint") and "positions" in body and not self.takes_positions:
            raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, _Body(self.reply))
        return Response(200, {"stored": len(body.get("events") or []), "replayed": 0})


class _Body:
    def __init__(self, data):
        self.data = data

    def read(self, *a):
        return self.data

    def close(self):
        pass


class PublisherTest(Case):
    def setUp(self):
        super().setUp()
        self.now = NOW
        self.house = House(Ledger(Path(self.dir) / "ledger.sqlite", clock=lambda: self.now))

    def tearDown(self):
        self.house.ledger._db.close()
        super().tearDown()

    def publisher(self, site):
        publisher = Publisher("https://blakewoods.us", lambda: "t" * 40, Path(self.dir) / "publish.json", tape="test", opener=site,
                              clock=lambda: self.now, performance={"start_at": RESET_AT, "start_equity": "481.65"},
                              real_brokers={"alpaca": SimpleNamespace(balance=lambda: SimpleNamespace(equity=D("1479.44"), cash=D("1479.41")))})
        publisher.activity = ActivityLedger(None, RESET_AT, self.dir, clock=lambda: self.now, threaded=False, reader=lambda: self.reading(now=self.now))
        return publisher

    def publish(self, publisher):
        with patch("league.trading_profit.marked_value", side_effect=marked(self.account)):
            return publisher.publish(self.house)

    def checkpoints(self, site):
        return [body for path, body in site.posts if path == "checkpoint"]

    def test_an_unreconciled_difference_is_its_own_line_in_profit_and_alerted_once(self):
        self.the_week()
        # The owner trades a contract by hand: its fills are real money no position of the book holds.
        self.account.orders.append({"id": "owner-order-1", "client_order_id": "owner-manual", "filled_qty": "1", "legs": []})
        self.account.activity("FILL", transaction_time=iso(T0), symbol="SPY261002C00650000", side="buy", qty="1", price="3.10", order_id="owner-order-1")
        self.account.activity("FILL", transaction_time=iso(T0 + 60), symbol="SPY261002C00650000", side="sell", qty="1", price="3.60", order_id="owner-order-1")
        site = Site()
        publisher = self.publisher(site)
        self.publish(publisher)
        [body] = self.checkpoints(site)
        self.assertEqual(body["positions"]["unreconciled_usd"], "50.00", "in Profit, beside the rows, never hidden")
        self.assert_adds_up(body)
        texts = [text for level, text in self.house.alerts]
        self.assertEqual(sum("an option fill on an order the live book does not hold" in t for t in texts), 2, "one for each fill")
        self.assertEqual(sum("an unreconciled 50.00" in t for t in texts), 1)
        self.assertTrue(all(level == "warning" for level, _ in self.house.alerts))
        self.now += 60
        self.publish(publisher)
        self.assertEqual(len(self.house.alerts), len(texts), "said once, not every minute")
        # A second difference: the broker says one of the book's own orders filled differently.
        a = self.account
        pid = a.position("orb-4", "long_call", "SPY", [("C", 620, 1, 1)], at=T0 + 7000)
        a.order(pid, "open", [(1, [0.50])], at=T0 + 7000, venue_prices=[0.52])
        a.mark(pid, "50.00")
        self.now += SETTLE_SECONDS
        self.publish(publisher)
        body = self.checkpoints(site)[-1]
        self.assertEqual(body["positions"]["unreconciled_usd"], "48.00", "the broker's -52.00 against the book's -50.00")
        self.assertIn("the broker's fills and the book's differ", " ".join(text for _, text in self.house.alerts))
        self.assert_adds_up(body)

    def test_an_activity_nobody_classified_is_unreconciled_not_profit_or_zero(self):
        self.the_week()
        self.account.activity("XYZ", net_amount="-7.50")
        self.account.activity("OPEXP", symbol="SPY261002C00999000", qty="1")
        site = Site()
        self.publish(self.publisher(site))
        body = self.checkpoints(site)[-1]
        self.assertEqual(body["positions"]["unreconciled_usd"], "-7.50")
        self.assert_adds_up(body)
        texts = " ".join(text for _, text in self.house.alerts)
        self.assertIn("a type nobody classified (XYZ", texts)
        self.assertIn("an option event (OPEXP", texts)

    def test_a_site_that_predates_the_table_still_gets_the_checkpoint_and_is_asked_again_later(self):
        self.the_week()
        site = Site(takes_positions=False)
        publisher = self.publisher(site)
        self.assertEqual(self.publish(publisher)["checkpoint"], 200)
        first, second = self.checkpoints(site)
        self.assertIn("positions", first)
        self.assertNotIn("positions", second)
        self.assertEqual(second["trading"], first["trading"], "Profit goes either way")
        said = [text for _, text in self.house.alerts if "refused the positions table" in text]
        self.assertEqual(len(said), 1)
        self.assertIn("(old site, or a row it rejects)", said[0])
        self.assertIn("Invalid checkpoint.", said[0], "the review of #408 (4): the site's own reply, not a guess at why")
        self.now += 60
        self.publish(publisher)
        self.assertNotIn("positions", self.checkpoints(site)[-1])
        self.assertEqual(len(self.checkpoints(site)), 3, "inside the half hour: one post, without the table")
        site.reply = b'{"error":"Invalid checkpoint: positions do not add up."}'
        self.now += POSITIONS_RETRY_SECONDS
        self.publish(publisher)
        said = [text for _, text in self.house.alerts if "refused the positions table" in text]
        self.assertEqual(len(said), 2, "a new reason is said again")
        self.assertIn("do not add up", said[1])
        self.now += POSITIONS_RETRY_SECONDS
        self.publish(publisher)
        self.assertEqual(sum("refused the positions table" in text for _, text in self.house.alerts), 2, "the same reason, once")
        site.takes_positions = True
        self.now += POSITIONS_RETRY_SECONDS
        self.publish(publisher)
        self.assertIn("positions", self.checkpoints(site)[-1])
        self.assertEqual(sum("refused the positions table" in text for _, text in self.house.alerts), 2)

    def test_a_site_refusing_for_another_reason_is_still_an_error(self):
        site = Site()
        publisher = self.publisher(site)

        def refuse(request, timeout=None):
            import urllib.error

            site.posts.append((request.full_url.rsplit("/", 1)[1], json.loads(request.data)))
            if request.full_url.endswith("/checkpoint"):
                raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, _Body(b'{"error":"Invalid checkpoint."}'))
            return Response(200, {"stored": 0, "replayed": 0})

        publisher.opener = refuse
        from league.publish import PublishError

        with self.assertRaises(PublishError):
            self.publish(publisher)


    def test_a_position_the_table_cannot_list_is_counted_and_said_never_hidden(self):
        self.the_week()
        a = self.account
        bad = a.position("orb-4", "long_call", "SPY", [("P", 600, 1, 1)], at=T0 + 7000)  # no right fits a "long call" of puts
        a.order(bad, "open", [(1, [1.00])], at=T0 + 7000)
        a.mark(bad, "110.00")
        site = Site()
        publisher = self.publisher(site)
        self.publish(publisher)
        body = self.checkpoints(site)[-1]
        self.assertEqual(body["positions"]["earlier"]["positions"], 1)
        self.assert_adds_up(body)
        said = [text for _, text in self.house.alerts if f"real:{bad}" in text]
        self.assertEqual(len(said), 1)
        self.assertIn("cannot be described in the table's fields", said[0])
        # More open positions than the table holds: the newest show, the oldest open one is counted and said.
        with patch("league.publish.MAX_POSITIONS", 1):
            self.now += 60
            self.publish(publisher)
        body = self.checkpoints(site)[-1]
        self.assertEqual([row["status"] for row in body["positions"]["rows"]], ["open"])
        self.assert_adds_up(body)
        texts = " ".join(text for _, text in self.house.alerts)
        self.assertIn("is not listed (the table is full)", texts)
        self.assertNotIn(f"real:{self.closed_pid()} is not listed", texts, "an old closed one folding is no news")

    def closed_pid(self):
        return self.account.db.execute("SELECT MIN(pid) FROM positions WHERE status='closed'").fetchone()[0]

    def test_a_restart_keeps_profit_from_the_last_reading_while_it_is_fresh(self):
        from league.account_activity import FRESH_SECONDS

        self.the_week()
        site = Site()
        self.publish(self.publisher(site))
        profit = self.checkpoints(site)[-1]["trading"]["pnl_usd"]
        self.assertIsNotNone(profit)

        def down(*args, **kwargs):
            raise OSError("the gateway has not answered yet")

        # The House restarts: a new publisher whose first read of the account has not come back.
        broker = SimpleNamespace(balance=lambda: SimpleNamespace(equity=D("1479.44"), cash=D("1479.41")), _call=down)
        again = Publisher("https://blakewoods.us", lambda: "t" * 40, Path(self.dir) / "publish.json", tape="test", opener=site,
                          clock=lambda: self.now, performance={"start_at": RESET_AT, "start_equity": "481.65"}, real_brokers={"alpaca": broker})
        again.activity.threaded = False
        self.now += 60
        self.publish(again)
        self.assertEqual(self.checkpoints(site)[-1]["trading"]["pnl_usd"], profit, "the review of #408 (11): no dash after a restart")
        self.now += FRESH_SECONDS
        self.publish(again)
        self.assertIsNone(self.checkpoints(site)[-1]["trading"]["pnl_usd"], "and never past ten minutes")

class ClassifyTest(Case):
    def test_a_fee_counts_once_every_filled_leg_of_its_order_has_posted(self):
        a = self.account
        pid = a.position("orb-4", "debit_vertical", "SPY", [("C", 600, 1, 1), ("C", 601, -1, 1)], at=T0)
        a.order(pid, "open", [(2, [1.00, 0.40])], at=T0, posted=1)
        self.assertEqual(self.reading()["fees_by_pid"], {}, "one leg's fee is in: the estimate still stands")
        a.activity("FEE", order_id="leg-0001-1", net_amount="-0.06")
        reading = self.reading()
        self.assertEqual(reading["fees_by_pid"], {str(pid): D("0.08")}, "-0.12 charged against the 0.20 estimated, the position's own")
        self.assertEqual(reading["fees_usd"], D("0.00"), "never Other's")
        self.assertEqual(self.reading(now=T0 + 60)["fees_by_pid"], {}, "an order still settling is left to the next reading")

    def test_what_is_never_profit(self):
        a = self.account
        a.activity("CSD", net_amount="1000")
        a.activity("CSW", net_amount="-200")
        a.activity("FILL", transaction_time=iso(T0), symbol="XRP/USD", side="sell", qty="7.9", price="0.6", order_id="coin")
        a.activity("FILL", transaction_time=iso(T0), symbol="LTCUSD", side="sell", qty="0.1", price="60", order_id="coin")
        reading = self.reading()
        self.assertEqual([reading[p] for p in (*OTHER_PARTS, "unreconciled_usd")], [D("0.00")] * 5)
        self.assertEqual((reading["problems"], reading["blocking"]), ([], []))

    def test_a_fill_on_an_order_the_broker_list_does_not_yet_hold_waits_then_counts(self):
        self.account.activity("FILL", transaction_time=iso(NOW - 60), symbol="SPY261002C00650000", side="buy", qty="1", price="1.00", order_id="new")
        self.assertEqual(self.reading()["unreconciled_usd"], D("0.00"))
        self.assertEqual(self.reading(now=NOW + SETTLE_SECONDS)["unreconciled_usd"], D("-100.00"))

    def test_a_liquidation_the_book_priced_is_its_own_and_its_fees_replace_the_estimate_once_posted(self):
        a = self.account
        pid = a.position("orb-4", "long_call", "SPY", [("C", 600, 1, 1)], at=T0)
        a.order(pid, "open", [(1, [1.00])], at=T0)
        # The broker liquidated it at expiry; the book priced the close from that fill (`recover_expired`): its estimate
        # rides the position's fees with no fill row.
        a.db.execute("UPDATE positions SET qty=0, status='closed', cash=cash+20-0.05, fees=fees+0.05 WHERE pid=?", (pid,))
        a.db.execute("INSERT INTO external_fill_usage(id, qty, value_qty) VALUES ('order:liq-1:SPY261002C00600000', 1, 0.2)")
        a.activity("FILL", transaction_time=iso(T0 + 3600), symbol="SPY261002C00600000", side="sell", qty="1", price="0.20", order_id="liq-1")
        reading = self.reading()
        self.assertEqual((reading["unreconciled_usd"], reading["fees_usd"], reading["fees_by_pid"]), (D("0.00"), D("0.00"), {str(pid): D("0.02")}),
                         "only the open's fees so far, in its own row")
        self.assertEqual(reading["blocking"], [], "a closed position's liquidation the book took: nothing waits")
        a.activity("FEE", order_id="liq-1", net_amount="-0.03")
        self.assertEqual(self.reading()["fees_usd"], D("0.02"), "the liquidation's 0.03 charged replaces its 0.05 estimate, in Other")

    def test_a_fill_it_cannot_put_a_number_on_is_no_reading(self):
        self.account.activity("FILL", transaction_time=iso(T0), symbol="SPY261002C00650000", side="buy", qty="1", order_id="x")
        with self.assertRaises(Unreadable):
            self.reading()


class Broker:
    """The broker's `_call` (`ltcm/adapters/alpaca.py` `AlpacaBroker`): activities and orders, paged, after a time, and
    the account's positions."""

    def __init__(self, activities, orders, positions=()):
        self.activities, self.orders, self.positions, self.calls, self.fail = activities, orders, list(positions), [], False

    def _call(self, method, path, *, params=None, what=""):
        self.calls.append((path, dict(params or {})))
        if self.fail:
            raise OSError("the gateway did not answer")
        if path == "/v2/positions":
            return self.positions
        after = epoch(params.get("after"))
        if path == "/v2/account/activities":
            rows = [r for r in self.activities if (epoch(r.get("transaction_time") or r.get("date")) or 0) > after]
            if params.get("page_token"):
                rows = [r for r in rows if r["id"] > params["page_token"]]
            return sorted(rows, key=lambda r: r["id"])[:params["page_size"]]
        rows = [o for o in self.orders if epoch(o["submitted_at"]) > after]
        return rows[:params["limit"]]


class ReaderTest(Case):
    def test_it_reads_the_whole_record_first_then_the_last_days_and_goes_stale_rather_than_wrong(self):
        pids = self.the_week()
        for n in range(230):  # three pages of interest
            self.account.activity("INT", day="2026-09-27", net_amount="0.01")
        broker = Broker(self.account.activities, self.account.orders)
        clock = SimpleNamespace(now=NOW + 2 * 86400)  # two days on: the window of the last three days starts after the reset
        reader = ActivityLedger(broker, RESET_AT, self.dir, clock=lambda: clock.now, threaded=False)
        reading = reader.read()
        self.assertEqual(reading["interest_usd"], D("2.47"))
        self.assertEqual(sum(reading["fees_by_pid"].values(), D(0)), D("0.24"))
        self.assertEqual({epoch(p["after"]) for path, p in broker.calls}, {epoch(RESET_AT)}, "the first read covers the whole record")
        self.assertGreaterEqual(sum(path == "/v2/account/activities" for path, _ in broker.calls), 3, "every page")
        broker.calls.clear()
        clock.now += 300
        self.account.activity("INT", net_amount="0.50")
        self.assertEqual(reader.read()["interest_usd"], D("2.97"))
        self.assertTrue(all(epoch(p["after"]) == clock.now - 3 * 86400 for _, p in broker.calls), "then the last three days only")
        broker.fail = True
        clock.now += 300
        self.assertIsNotNone(reader.read(), "one failed read: the last reading is still fresh")
        self.assertIn("did not answer", reader.error)
        clock.now += 301
        self.assertIsNone(reader.read(), "older than ten minutes: no reading, so no Profit")
        broker.fail = False
        clock.now += FULL_EVERY_SECONDS
        broker.calls.clear()
        self.assertIsNotNone(reader.read())
        self.assertEqual({epoch(p["after"]) for _, p in broker.calls}, {epoch(RESET_AT)}, "a failed read's caches are read again whole")
        del pids

    def test_the_pagers_read_every_page(self):
        acts = [{"id": f"2026092800000{n:04d}::x", "activity_type": "INT", "date": "2026-09-28", "net_amount": "0.01"} for n in range(250)]
        self.assertEqual(len(activities_after(Broker(acts, []), RESET_AT)), 250)
        orders = [{"id": f"o{n}", "client_order_id": f"c{n}", "filled_qty": "1", "submitted_at": iso(T0 + n), "legs": [{"id": f"l{n}", "filled_qty": "1"}]}
                  for n in range(1100)]
        read = orders_after(Broker([], orders), RESET_AT)
        self.assertEqual(len(read), 1100)
        self.assertEqual(set(read[0]), {"id", "client_order_id", "filled_qty", "submitted_at", "legs"}, "ids and quantities only")


def site_accepts(bodies):
    """The site's own `validCheckpoint` (`capital/schema.js`, the copy in fixtures/site_schema.js) over each body, in
    node: the review of #408 found the two repositories' blocks disagreeing because each side tested only its own."""
    import os
    import subprocess

    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError("node is required in CI to run the site's schema")
        raise unittest.SkipTest("node is not installed")
    script = (f"import {{ validCheckpoint }} from {json.dumps(SITE_SCHEMA.as_uri())};"
              "let text = ''; process.stdin.on('data', chunk => { text += chunk; });"
              "process.stdin.on('end', () => console.log(JSON.stringify(JSON.parse(text).map(body => validCheckpoint(body)))));")
    done = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps(bodies), capture_output=True, text=True, timeout=120)
    if done.returncode:
        raise AssertionError(done.stderr[-2000:])
    return json.loads(done.stdout)


SITE_SCHEMA = Path(__file__).resolve().parent / "fixtures" / "site_schema.js"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


class IncubatorRowsTest(Case):
    """Release B (Oct 1, 2026): an agent's position on the incubator route (`<family>@<version>:i`) is its own source,
    keeps its agent, and the table still adds up to Profit to the cent."""

    def test_an_incubator_position_keeps_its_agent_and_the_rows_still_add_up(self):
        ids = self.the_week()
        self.account.db.execute("UPDATE positions SET instance='orb-4@1:i' WHERE pid=?", (ids["orb"],))
        body = self.table()
        rows = {row["id"]: row for row in body["positions"]["rows"]}
        self.assertEqual((rows[f"real:{ids['orb']}"]["source"], rows[f"real:{ids['orb']}"]["agent"]), ("incubator", "orb-4"))
        self.assertEqual(rows[f"real:{ids['gap']}"]["source"], "agent")
        self.assert_adds_up(body)
        if "'incubator'" not in SITE_SCHEMA.read_text(encoding="utf-8"):
            self.skipTest("the site schema copy predates the incubator route (release A's site refresh brings it)")
        self.assertEqual(site_accepts([ReviewOf408Test.full(self, body)]), [True])


class ReviewOf408Test(Case):
    """The two reviews of #408 (Sept 28, 2026): the site's shape and rules, the not-listed line, fees in their rows,
    assignments, exercises and cash settlements, broker liquidations, the reset's orders, times to the minute."""

    def full(self, body):
        """`body` (the table alone) inside the fixture's whole checkpoint, as the House posts it."""
        from league.tests.test_publish import FIXTURE_INPUTS

        return build_checkpoint(SiteInputs(**{**FIXTURE_INPUTS.__dict__, "trading": body["trading"], "positions": None}), PUBLISHED_AT) | {
            "trading": body["trading"], "positions": body["positions"]}

    def test_the_site_takes_what_the_house_publishes(self):
        self.the_week()
        week = self.full(self.table())
        stale = self.full(self.table(fresh=False))
        fixture = json.loads((FIXTURES / "site_checkpoint_positions.json").read_text(encoding="utf-8"))
        plain = json.loads((FIXTURES / "site_checkpoint.json").read_text(encoding="utf-8"))
        old_shape = {**fixture, "positions": {**{k: v for k, v in fixture["positions"].items() if k not in ("earlier", "unreconciled_usd")},
                                              "folded": None, "sum_usd": "10.90", "profit_usd": "10.90", "difference_usd": "0.00"}}
        off = {**fixture, "positions": {**fixture["positions"], "unreconciled_usd": "0.01"}}
        self.assertEqual(site_accepts([fixture, plain, week, stale, old_shape, off]), [True, True, True, True, False, False],
                         "the fixtures and the House's tables; never #408's first shape, nor lines that do not add up")
        # Sept 30, 2026: the practice league and Claude's own compute part, and the older shape an older site is sent.
        from league.publish import legacy_compute

        practice = json.loads((FIXTURES / "site_checkpoint_practice.json").read_text(encoding="utf-8"))
        self.assertIn("claude_usd", practice["compute"])
        self.assertEqual(site_accepts([practice, legacy_compute({k: v for k, v in practice.items() if k != "practice"}),
                                       {**practice, "compute": {**practice["compute"], "claude_usd": "-1.00"}}]), [True, True, False])

    def test_the_houses_row_rules_are_the_sites(self):
        from league.publish import site_position

        base = {"pid": 7, "family": "orb-4", "source": "agent", "underlying": "SPY", "structure": "debit_vertical", "right": "call", "legs": 2,
                "quantity": 2, "open_quantity": 2, "status": "open", "expiry": "2026-10-02", "opened_at": "2026-09-28T14:10:31.412Z",
                "closed_at": None, "pnl_usd": "-8.00"}
        self.assertEqual(site_position(base, PUBLISHED_AT)["opened_at"], "2026-09-28T14:10:00.000Z", "to the minute (N2)")
        for bad in ({"right": "both"}, {"structure": "iron_condor"}, {"structure": "long_call", "right": "put"}, {"open_quantity": 0},
                    {"status": "closed", "open_quantity": 0, "closed_at": "2026-09-28T14:09:00.000Z"},
                    {"status": "closed", "open_quantity": 1, "closed_at": "2026-09-28T15:00:00.000Z"},
                    {"status": "closed", "open_quantity": 0, "closed_at": None}, {"pnl_usd": "a lot"}):
            self.assertIsNone(site_position({**base, **bad}, PUBLISHED_AT), bad)
        closed = site_position({**base, "status": "closed", "open_quantity": 0, "closed_at": "2026-09-28T14:10:59.999Z"}, PUBLISHED_AT)
        self.assertEqual(closed["closed_at"], "2026-09-28T14:10:00.000Z", "closed in the minute it opened: not before it")
        self.assertIsNone(site_position({**base, "pnl_usd": None}, PUBLISHED_AT)["pnl_usd"], "an unpriced row is a row")

    def test_a_row_the_site_would_refuse_is_counted_in_the_not_listed_line_whatever_its_status(self):
        a = self.account
        good = a.position("orb-4", "long_call", "SPY", [("C", 600, 1, 1)], at=T0)
        a.order(good, "open", [(1, [1.00])], at=T0)
        a.mark(good, "90.00")
        bad = a.position("orb-4", "long_call", "SPY", [("P", 600, 1, 1)], at=T0 + 60)  # a "long call" of puts: no right fits
        a.order(bad, "open", [(1, [1.00])], at=T0 + 60)
        a.mark(bad, "110.00")
        body = self.table()
        block = body["positions"]
        self.assertEqual([row["id"] for row in block["rows"]], [f"real:{good}"])
        self.assertEqual(block["earlier"], {"positions": 1, "pnl_usd": format(a.expected_row(bad), ".2f")}, "an OPEN one too")
        self.assert_adds_up(body)
        self.assertEqual(site_accepts([self.full(body)]), [True])

    def test_an_unpriced_close_has_a_close_time_and_the_site_takes_an_unknown_not_listed_line(self):
        a = self.account
        at = epoch("2026-09-26T15:00:00Z")
        pid = a.position("orb-4", "long_call", "SPY", [("C", 600, 1, 1)], at=at, expiry="2026-09-26")
        a.order(pid, "open", [(1, [1.00])], at=at)
        odd = a.position("orb-4", "long_call", "SPY", [("P", 600, 1, 1)], at=at + 60, expiry="2026-09-26")
        a.order(odd, "open", [(1, [1.00])], at=at + 60)
        # The broker liquidated both at expiry and the book has no fill to price them from yet (`recover_expired`).
        a.db.execute("UPDATE positions SET qty=0, status='unpriced_close', closed_at=NULL")
        body = self.table()
        block = body["positions"]
        self.assertIsNone(body["trading"]["pnl_usd"])
        [row] = block["rows"]
        self.assertEqual((row["status"], row["closed_at"], row["pnl_usd"]), ("closed", "2026-09-26T20:00:00.000Z", None),
                         "closed at 16:00 New York time on its expiry")
        self.assertEqual(block["earlier"], {"positions": 1, "pnl_usd": None})
        self.assertEqual(site_accepts([self.full(body)]), [True], "the review of #408 (3): one unpriced row never sinks the checkpoint")

    def test_a_posted_fee_goes_into_its_own_row_and_one_with_no_row_stays_in_other(self):
        a = self.account
        pid = a.position("orb-4", "long_call", "SPY", [("C", 600, 1, 1)], at=T0)
        a.order(pid, "open", [(1, [1.00])], at=T0)
        a.order(pid, "close", [(1, [1.20])], at=T0 + 60)
        a.activity("PTC", net_amount="-0.01")
        reading = self.reading()
        self.assertEqual(reading["fees_by_pid"], {str(pid): D("0.04")})
        body = self.table(reading)
        self.assertEqual(body["positions"]["rows"][0]["pnl_usd"], "19.94", "20.00 less the broker's 0.06, not the book's 0.10")
        self.assertEqual(body["positions"]["other"]["fees_usd"], "-0.01", "a pass-through charge no position carries")
        self.assertEqual(body["trading"]["pnl_usd"], "19.93")
        with patch("league.trading_profit.marked_value", side_effect=marked(self.account)):
            book = ledger(self.dir, LIVE, at=PUBLISHED_AT, start_at=RESET_AT)
        trading, positions = complete(book, {**reading, "fees_by_pid": {**reading["fees_by_pid"], "999": D("0.05")}}, at=PUBLISHED_AT)
        self.assertEqual(positions["other"]["fees_usd"], "0.04", "a correction for a position outside the table: Other's, never lost")
        self.assertEqual(trading["pnl_usd"], "19.98")

    def test_an_order_is_the_resets_when_its_position_is(self):
        a = self.account
        reset = epoch(RESET_AT)
        # Placed before the reset, filled after it: the position opened after it, so its order and fees are this record's.
        filled = epoch("2026-09-27T13:35:00Z")  # (the fake broker's `after` reads a fee dated the reset's own day as before it)
        pid = a.position("orb-4", "long_call", "SPY", [("C", 600, 1, 1)], at=filled)
        a.order(pid, "open", [(1, [1.00])], at=filled)
        a.db.execute("UPDATE orders SET placed_at=? WHERE pid=?", (reset - 120, pid))
        a.orders[-1]["submitted_at"] = iso(reset - 120)
        a.mark(pid, "95.00")
        # A position from before the reset closed after it: nothing of it is this record's, and nothing of it is a problem.
        old = a.position("gap-drift", "long_put", "QQQ", [("P", 500, 1, 1)], at=epoch("2026-09-25T15:00:00Z"))
        a.order(old, "open", [(1, [1.00])], at=epoch("2026-09-25T15:00:00Z"))
        a.order(old, "close", [(1, [1.20])], at=T0)
        broker = Broker(a.activities, a.orders)
        reading = ActivityLedger(broker, RESET_AT, self.dir, clock=lambda: NOW, threaded=False).read()
        self.assertEqual((reading["problems"], reading["blocking"], reading["unreconciled_usd"], reading["fees_usd"]), ([], [], D("0.00"), D("0.00")))
        self.assertEqual(reading["fees_by_pid"], {str(pid): D("0.02")}, "the pre-reset position's close: not a fee of this record")
        orders_after_ = [epoch(params["after"]) for path, params in broker.calls if path == "/v2/orders"]
        self.assertLessEqual(min(orders_after_), reset - 120, "the broker's orders read from the earliest placing that still changed")
        body = self.table(reading)
        self.assertEqual([row["id"] for row in body["positions"]["rows"]], [f"real:{pid}"])
        self.assert_adds_up(body)

    def test_an_exercise_waits_for_its_shares_then_the_brokers_cash_replaces_the_books_value(self):
        a = self.account
        pid = a.position("orb-4", "long_call", "SPY", [("C", 600, 1, 1)], at=T0)
        a.order(pid, "open", [(1, [1.00])], at=T0)
        [symbol] = self.symbols(pid)
        a.activity("OPEXC", symbol=symbol, qty="1", net_amount="0", transaction_time=iso(T0 + 3000))
        a.activity("FILL", transaction_time=iso(T0 + 3000), symbol="SPY", side="buy", qty="100", price="600", order_id="exercise-1")
        self.assertTrue(any("has not taken yet" in reason for reason in self.reading(shares=False)["blocking"]),
                        "an exercise of the book's contract the book has not taken: Profit waits")
        # The book takes it at 2.00 a share of intrinsic (`remove_contracts`): the position closes with that value.
        a.db.execute("UPDATE positions SET qty=0, status='closed', cash=cash+200, closed_at=?, info=? WHERE pid=?",
                     (T0 + 3010, json.dumps({"order": 1, "gone": {symbol: 1}, "broken": "exercised"}), pid))
        for held in (True, None):
            reading = self.reading(shares=held)
            self.assertTrue(any("shares an assignment or an exercise left" in reason for reason in reading["blocking"]), held)
            self.assertIsNone(self.table(reading)["trading"]["pnl_usd"], "never the book's value and the shares' cash both")
        # The House sells the shares at 602.10: the account made 210.00 on them, the book said 200.00.
        a.activity("FILL", transaction_time=iso(T0 + 3060), symbol="SPY", side="sell", qty="100", price="602.10", order_id="lv-shares-1")
        reading = self.reading(shares=False)
        self.assertEqual((reading["blocking"], reading["unreconciled_usd"]), ([], D("10.00")))
        body = self.table(reading)
        self.assert_adds_up(body)
        # What the account really made: -100.00 of premium, -0.03 of fees, -60,000.00 for the shares and +60,210.00 for them.
        self.assertEqual(body["trading"]["pnl_usd"], "109.97")
        self.assertTrue(any("an assignment or an exercise" in text for text in reading["problems"]), "said")
        # Had the broker also liquidated a leg of it (a fee estimate with no fill row), no line could hold it exactly.
        a.db.execute("UPDATE positions SET fees=fees+0.05, cash=cash+19.95 WHERE pid=?", (pid,))
        self.assertTrue(any("also liquidated" in reason for reason in self.reading(shares=False)["blocking"]))

    def test_the_brokers_settlement_of_an_index_expiry_replaces_the_books_own_value_once_posted(self):
        a = self.account
        pid = a.position("condor-vrp-3", "iron_condor", "XSP", [("P", 560, 1, 1), ("P", 565, -1, 1), ("C", 580, -1, 1), ("C", 585, 1, 1)],
                         at=T0, expiry="2026-09-28")
        a.order(pid, "open", [(1, [0.40, 0.95, 0.90, 0.38])], at=T0)
        # The book settled it at its own level, 563.50: the short put in the money by 1.50 a share (`RealBook.settle`).
        a.db.execute("UPDATE positions SET qty=0, status='closed', reason='settled', cash=cash-150, closed_at=? WHERE pid=?",
                     (epoch("2026-09-28T20:00:00Z"), pid))
        later = epoch("2026-09-29T15:00:00Z")
        base = self.reading(now=later)
        self.assertEqual((base["unreconciled_usd"], base["problems"]), (D("0.00"), []), "the book's value stands meanwhile")
        p560, p565, c580, c585 = self.symbols(pid)
        a.activity("OPEXP", day="2026-09-29", symbol=p560, qty="1", net_amount="0")
        a.activity("OPCSH", day="2026-09-29", symbol=p565, qty="-1", net_amount="-152.00")
        self.assertEqual(self.reading(now=later)["unreconciled_usd"], D("0.00"), "not every contract of the expiry has posted")
        a.activity("OPEXP", day="2026-09-29", symbol=c580, qty="-1", net_amount="0")
        a.activity("OPEXP", day="2026-09-29", symbol=c585, qty="1", net_amount="0")
        reading = self.reading(now=later)
        self.assertEqual(reading["unreconciled_usd"], D("-2.00"), "the official level's -152.00 against the book's -150.00")
        self.assertTrue(any("settlement of the 2026-09-28 expiry" in text for text in reading["problems"]))
        self.assertEqual(reading["blocking"], [])

    def test_a_late_settlement_is_said_and_a_cash_event_the_book_never_counts_is_unreconciled(self):
        a = self.account
        pid = a.position("condor-vrp-3", "iron_condor", "XSP", [("P", 560, 1, 1), ("P", 565, -1, 1), ("C", 580, -1, 1), ("C", 585, 1, 1)],
                         at=T0, expiry="2026-09-28")
        a.order(pid, "open", [(1, [0.40, 0.95, 0.90, 0.38])], at=T0)
        a.db.execute("UPDATE positions SET qty=0, status='closed', reason='settled', cash=cash-150, closed_at=? WHERE pid=?",
                     (epoch("2026-09-28T20:00:00Z"), pid))
        late = self.reading(now=epoch("2026-10-02T21:00:00Z"))
        self.assertEqual(late["unreconciled_usd"], D("0.00"))
        self.assertTrue(any("has not posted the 2026-09-28 expiry" in text for text in late["problems"]))
        held = a.position("orb-4", "long_call", "SPY", [("C", 600, 1, 1)], at=T0 + 60)
        a.order(held, "open", [(1, [1.00])], at=T0 + 60)
        [symbol] = self.symbols(held)
        a.activity("OPEXP", symbol=symbol, qty="1", net_amount="0")
        self.assertEqual(self.reading()["unreconciled_usd"], D("0.00"), "an expiry at zero: the book's own")
        a.activity("OPCA", symbol=symbol, qty="1", net_amount="5.00")
        reading = self.reading()
        self.assertEqual(reading["unreconciled_usd"], D("5.00"), "the review of #408 (2): a cash event the book never counts")
        self.assertTrue(any("does not count (OPCA" in text for text in reading["problems"]))

    def test_a_broker_fill_on_a_contract_the_book_still_holds_makes_profit_wait_never_count_twice(self):
        a = self.account
        pid = a.position("orb-4", "long_call", "SPY", [("C", 600, 1, 1)], at=T0)
        a.order(pid, "open", [(1, [1.00])], at=T0)
        a.mark(pid, "95.00")
        [symbol] = self.symbols(pid)
        a.orders.append({"id": "liq-9", "client_order_id": "broker-liquidation", "filled_qty": "1", "submitted_at": iso(NOW - 120), "legs": []})
        a.activity("FILL", transaction_time=iso(NOW - 60), symbol=symbol, side="sell", qty="1", price="0.95", order_id="liq-9")
        reading = self.reading()
        self.assertEqual((reading["unreconciled_usd"], reading["blocking"]), (D("0.00"), []), "inside the grace")
        later = self.reading(now=NOW + SETTLE_SECONDS)
        self.assertEqual(later["unreconciled_usd"], D("0.00"), "the review of #408 (8): never counted beside the book's own mark")
        self.assertTrue(any("not yet taken by the book" in reason for reason in later["blocking"]))
        self.assertIsNone(self.table(later)["trading"]["pnl_usd"])

    def test_the_readers_share_check_asks_the_broker_only_after_an_assignment(self):
        from league.account_activity import shares_held

        self.assertIs(shares_held(Broker([], [], [{"asset_class": "us_option", "qty": "1"}])), False)
        self.assertIs(shares_held(Broker([], [], [{"asset_class": "us_equity", "qty": "100"}])), True)
        broken = Broker([], [])
        broken.fail = True
        self.assertIsNone(shares_held(broken), "unknown, never none held")
        self.the_week()
        broker = Broker(self.account.activities, self.account.orders)
        ActivityLedger(broker, RESET_AT, self.dir, clock=lambda: NOW, threaded=False).read()
        self.assertNotIn("/v2/positions", [path for path, _ in broker.calls])


if __name__ == "__main__":
    unittest.main()
