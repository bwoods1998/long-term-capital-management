"""The gap scoreboard (`scripts/gap_scoreboard.py`): the family record, each of the seven metrics, the
evidence clock and the rendering, on tiny synthetic snapshots whose answers are worked out by hand
here; and `--take` against a fake Sail client. Nothing here reaches a box.

The script is loaded the way `test_floor_box.py` loads its script, so the repository runs without
being installed. Every ledger here is written with the House's own schema (`league.ledger.SCHEMA`)
and the feed store with the recorder's (`league.feeds.SCHEMA`).
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import math
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ltcm
from league.feeds import SCHEMA as FEEDS_SCHEMA
from league.ledger import SCHEMA as LEDGER_SCHEMA
from league.stats import t_quantile

REPO_ROOT = Path(ltcm.__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "gap_scoreboard.py"


def load():
    spec = importlib.util.spec_from_file_location("gap_scoreboard_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while the script loads
    spec.loader.exec_module(module)
    return module


gs = load()
START = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)
HOUR = 3600.0


def at(hours: float) -> str:
    return (START + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def ts(hours: float) -> float:
    return (START + timedelta(hours=hours)).timestamp()


class Floor:
    """A synthetic snapshot directory: the ledger written row by row, the other stores on request."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.db = sqlite3.connect(self.root / "ledger.sqlite")
        self.db.executescript(LEDGER_SCHEMA)
        self.n = 0
        self.opened: list = []

    def close(self) -> None:
        for snap in self.opened:
            snap.close()
        self.db.close()

    def row(self, kind: str, agent: str, hours: float, payload: dict, ident: str | None = None) -> None:
        self.n += 1
        self.db.execute("INSERT INTO ledger(id, kind, agent, at, public, payload, previous_hash, digest) VALUES (?,?,?,?,1,?,?,?)",
                        (ident or f"row-{self.n}", kind, agent, at(hours), json.dumps(payload), "prev", f"digest-{self.n}"))

    def born(self, agent: str, hours: float, *, family: str = "fam", venue: str = "kalshi", desk: str = "kalshi-weather",
             horizon: str = "day", parent: str | None = None, founder: str | None = None) -> None:
        self.row("agent.born", agent, hours, {"family": family, "venue": venue, "specialty": desk, "horizon": horizon,
                                              "parent": parent, "founder": founder, "_code": "def decide(ctx): return []"})

    def stake(self, agent: str, hours: float, book: str, usd: float) -> None:
        self.row("book.stake", agent, hours, {"book": book, "usd": str(usd)})

    @staticmethod
    def instrument(market: str, right: str | None = "no") -> dict:
        return {"market_id": market, "symbol": market, "right": right}

    def buy(self, agent: str, hours: float, book: str, market: str, *, quantity: float = 10, price: float = 0.95,
            liquidity: str = "maker", intent: str | None = None, reason: str = "entry", right: str | None = "no") -> None:
        self.row("book.fill", agent, hours, {"book": book, "side": "buy", "source": "venue", "liquidity": liquidity,
                                             "quantity": str(quantity), "price": str(price), "cash_delta": str(-quantity * price),
                                             "realized": None, "flat": None, "intent_id": intent, "reason": reason,
                                             "instrument": self.instrument(market, right)})

    def sell(self, agent: str, hours: float, book: str, market: str, realized: float, *, flat: bool = True,
             reason: str = "exit", right: str | None = None) -> None:
        self.row("book.fill", agent, hours, {"book": book, "side": "sell", "source": "venue", "liquidity": "taker",
                                             "quantity": "1", "price": "1", "cash_delta": "1", "realized": str(realized),
                                             "flat": flat, "reason": reason, "instrument": self.instrument(market, right)})

    def settle(self, agent: str, hours: float, book: str, market: str, pnl: float, right: str | None = "no") -> None:
        self.row("book.settle", agent, hours, {"book": book, "pnl": str(pnl), "instrument": self.instrument(market, right)})

    def verdict(self, agent: str, hours: float, decision: str, from_rung: int, to_rung: int, **extra) -> None:
        self.row("eval.verdict", agent, hours, {"decision": decision, "from_rung": from_rung, "to_rung": to_rung, **extra})

    def died(self, agent: str, hours: float, cause: str = "displaced") -> None:
        self.row("agent.died", agent, hours, {"cause": cause, "detail": "test"})

    def bid(self, agent: str, hours: float, book: str, market: str, ident: str, *, filled: bool,
            quantity: float = 10, price: float = 0.95) -> None:
        """A buy intent placed as an order (a `book.order` share names it), filled or not."""
        self.row("agent.intent", agent, hours, {"id": ident, "side": "buy", "book": book, "quantity": str(quantity),
                                                "limit_price": str(price), "instrument": self.instrument(market)})
        self.row("book.order", "house", hours, {"book": book, "shares": [{"agent": agent, "intent_id": ident}]})
        if filled:
            self.buy(agent, hours + 0.1, book, market, quantity=quantity, price=price, intent=ident)

    def write_json(self, name: str, payload: dict) -> None:
        (self.root / name).write_text(json.dumps(payload), encoding="utf-8")

    def snapshot(self):
        self.db.commit()
        snap = gs.Snapshot(self.root)
        self.opened.append(snap)
        return snap


class ScoreboardCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.floor = Floor(Path(self._tmp.name))
        self.addCleanup(self.floor.close)

    def parts(self, snap):
        agents = gs.agents_of(snap)
        trades, still_open, skipped = gs.closed_trades(snap)
        return agents, trades, still_open, skipped, gs.Families(agents, trades)


# --------------------------------------------------------------------------- the family record
class FamilyRecordTest(ScoreboardCase):
    def test_one_observation_an_event_weighted_and_bounded_by_t(self):
        f = self.floor
        f.born("a-1", 0, family="fam")
        f.born("b-1", 0, family="fam")
        f.stake("a-1", 0.1, "kalshi-shadow", 200)
        f.stake("b-1", 0.1, "kalshi", 50)
        # Event KXE1-26SEP24: a-1 holds two strikes on practice (stacked), b-1 a third on real money.
        f.buy("a-1", 1, "kalshi-shadow", "KXE1-26SEP24-B1")
        f.buy("a-1", 1, "kalshi-shadow", "KXE1-26SEP24-B2")
        f.buy("b-1", 1, "kalshi", "KXE1-26SEP24-B3", liquidity="taker")
        f.settle("a-1", 5, "kalshi-shadow", "KXE1-26SEP24-B1", 2)
        f.settle("a-1", 5, "kalshi-shadow", "KXE1-26SEP24-B2", 2)
        f.settle("b-1", 5, "kalshi", "KXE1-26SEP24-B3", 5)
        # KXE2-26SEP25: a-1 loses 4 on practice. KXE3-26SEP25: b-1 makes 2.50 on real money.
        f.buy("a-1", 6, "kalshi-shadow", "KXE2-26SEP25-T5")
        f.settle("a-1", 9, "kalshi-shadow", "KXE2-26SEP25-T5", -4)
        f.buy("b-1", 6, "kalshi", "KXE3-26SEP25-X", liquidity="taker")
        f.settle("b-1", 9, "kalshi", "KXE3-26SEP25-X", 2.5)
        *_, families = self.parts(f.snapshot())

        # By hand: a member's value is the sum of its rows' ln(1 + pnl / staked); an event is the
        # weighted mean of its values (real 1, practice 0.5) at the largest weight among its rows.
        x1 = (0.5 * 2 * math.log(1 + 2 / 200) + 1.0 * math.log(1 + 5 / 50)) / 1.5
        x2 = math.log(1 - 4 / 200)
        x3 = math.log(1 + 2.5 / 50)
        obs = [(x1, 1.0), (x2, 0.5), (x3, 1.0)]
        sw = sum(w for _, w in obs)
        sw2 = sum(w * w for _, w in obs)
        mean = sum(w * x for x, w in obs) / sw
        n_eff = sw * sw / sw2
        sd = math.sqrt(sum(w * (x - mean) ** 2 for x, w in obs) / (sw - sw2 / sw))
        lcb = mean - t_quantile(0.8, n_eff - 1) * sd / math.sqrt(n_eff)

        rec = families.state("kalshi", "fam")
        self.assertEqual(rec["n"], 3)
        self.assertAlmostEqual(rec["n_eff"], 6.25 / 2.25)
        self.assertAlmostEqual(rec["mean"], mean)
        self.assertAlmostEqual(rec["sd"], sd)
        self.assertAlmostEqual(rec["lcb"], lcb)
        self.assertFalse(rec["proven"], "three observations are not ten")
        # Maker and taker apart, by the entry fill: b-1's taker rows leave the maker record.
        maker = gs.record([t for t in families.trades[("kalshi", "fam")] if t.liquidity == "maker"])
        taker = gs.record([t for t in families.trades[("kalshi", "fam")] if t.liquidity == "taker"])
        self.assertEqual((maker["n"], taker["n"]), (2, 2))
        self.assertAlmostEqual(maker["mean"], (0.5 * 2 * math.log(1.01) + 0.5 * x2) / 1.0)

    def test_no_bound_below_two_effective_observations(self):
        # One real observation (weight 1) and one practice (0.5): n_eff = 2.25 / 1.25 = 1.8 < 2.
        rec = gs.pooled([(0.01, 1.0), (0.02, 0.5)])
        self.assertAlmostEqual(rec["n_eff"], 1.8)
        self.assertIsNone(rec["lcb"])
        self.assertFalse(rec["proven"])
        # Ten equal-weight observations with a positive lower bound are proven.
        rec = gs.pooled([(0.01 + 0.001 * i, 1.0) for i in range(10)])
        self.assertTrue(rec["proven"])
        self.assertAlmostEqual(rec["lcb"], rec["mean"] - t_quantile(0.8, 9) * rec["sd"] / math.sqrt(10))

    def test_a_row_is_divided_by_the_most_lent_before_it_and_a_cutoff_starts_afresh(self):
        f = self.floor
        f.born("c-1", 0)
        f.settle("c-1", 0.5, "kalshi", "KXNOSTAKE-26SEP24-1", 1)  # nothing lent yet: no growth
        f.stake("c-1", 1, "kalshi", 30)
        f.stake("c-1", 2, "kalshi", -25)  # a sweep: later rows are still over the $30 lent
        f.settle("c-1", 3, "kalshi", "KXC-26SEP24-1", 3)
        f.settle("c-1", 3.5, "kalshi-shadow", "KXOLD-26SEP24-1", -50)  # before the cutoff below: out
        f.row("book.fill_correction", "c-1", 4, {"book": "kalshi-shadow"})
        f.stake("c-1", 4.5, "kalshi-shadow", 200)
        f.settle("c-1", 5, "kalshi-shadow", "KXNEW-26SEP24-1", 4)
        agents, trades, _, skipped, _ = self.parts(f.snapshot())
        by_market = {t.market: t for t in trades}
        self.assertIsNone(by_market["KXNOSTAKE-26SEP24-1"].growth)
        self.assertEqual(by_market["KXC-26SEP24-1"].staked, 30.0)
        self.assertAlmostEqual(by_market["KXC-26SEP24-1"].growth, math.log(1.1))
        self.assertNotIn("KXOLD-26SEP24-1", by_market)
        self.assertAlmostEqual(by_market["KXNEW-26SEP24-1"].growth, math.log(1.02))
        self.assertEqual(skipped, {"rows_without_stake": 1, "rows_before_evidence_cutoff": 1})

    def test_a_position_sold_in_pieces_is_one_trade_and_alpaca_trades_are_their_own_events(self):
        f = self.floor
        f.born("h-1", 0, venue="alpaca", desk="alpaca-crypto-alts", horizon="hour")
        f.stake("h-1", 0, "alpaca-paper", 200)
        f.buy("h-1", 1, "alpaca-paper", "SOL/USD", right=None, liquidity="taker")
        f.sell("h-1", 2, "alpaca-paper", "SOL/USD", 1.0, flat=False)
        f.sell("h-1", 3, "alpaca-paper", "SOL/USD", 3.0, flat=True)
        f.buy("h-1", 4, "alpaca-paper", "SOL/USD", right=None, liquidity="taker")
        f.sell("h-1", 5, "alpaca-paper", "SOL/USD", -2.0, flat=True)
        _, trades, _, _, _ = self.parts(f.snapshot())
        self.assertEqual([round(t.pnl, 6) for t in trades], [4.0, -2.0])
        self.assertEqual([t.liquidity for t in trades], ["taker", "taker"])
        self.assertEqual(len({t.event for t in trades}), 2)
        self.assertEqual(gs.kalshi_event("KXMLBTOTAL-26SEP231840MILPHI-6"), "KXMLBTOTAL-26SEP231840MILPHI")


# --------------------------------------------------------------------------------- metric 1
class RealBoundsTest(ScoreboardCase):
    def test_a_family_with_a_positive_real_bound_and_its_capacity_factors(self):
        f = self.floor
        f.born("w-1", 0, family="wx")
        f.born("w-2", 0, family="wx")
        f.stake("w-1", 0.5, "kalshi", 50)
        f.stake("w-2", 0.5, "kalshi-shadow", 200)
        # Four markets bid at $9.50, two filled (both real), over the day from the first bid at 1 h.
        f.bid("w-1", 1, "kalshi", "KXA-26SEP24-B1", "i1", filled=True)
        f.bid("w-1", 1, "kalshi", "KXB-26SEP24-B1", "i2", filled=True)
        f.bid("w-2", 2, "kalshi-shadow", "KXC-26SEP24-B1", "i3", filled=False)
        f.bid("w-2", 2, "kalshi-shadow", "KXD-26SEP24-B1", "i4", filled=False)
        f.settle("w-1", 10, "kalshi", "KXA-26SEP24-B1", 0.5)
        f.settle("w-1", 12, "kalshi", "KXB-26SEP24-B1", 0.3)
        # A losing family on real money is not listed.
        f.born("l-1", 0, family="loser")
        f.stake("l-1", 0.5, "kalshi", 30)
        f.settle("l-1", 10, "kalshi", "KXL-26SEP24-1", -3)
        f.settle("l-1", 11, "kalshi", "KXM-26SEP24-1", -1)
        f.row("ops.job", "house", 25, {})  # the snapshot's clock: 25 h
        board = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)
        one = board["metrics"]["1"]
        self.assertEqual(one["count"], 1)
        row = one["families"][0]
        self.assertEqual(row["family"], "wx")
        g1, g2 = math.log(1.01), math.log(1.006)
        mean = (g1 + g2) / 2
        sd = abs(g1 - g2) / math.sqrt(2)
        self.assertAlmostEqual(row["real"]["lcb"], mean - t_quantile(0.8, 1) * sd / math.sqrt(2))
        c = row["capacity"]
        self.assertEqual(c["markets_bid"], 4)
        self.assertAlmostEqual(c["days"], 1.0)  # from the first bid (1 h) to the clock (25 h)
        self.assertEqual(c["markets_per_day"], 4.0)
        self.assertEqual(c["size_bucket"], "<=$12")
        self.assertEqual(c["fill_rate_basis"], "all books")  # 2 real markets bid: fewer than 10
        self.assertEqual(c["fill_rate_at_size"], 0.5)
        self.assertAlmostEqual(c["profit_per_settlement_usd"], 0.4)
        self.assertAlmostEqual(c["capacity_usd_per_day"], 4 * 0.5 * 0.4)
        self.assertAlmostEqual(c["real_earning_usd_per_day"], 2 * 0.4)


# --------------------------------------------------------------------------------- metric 2
class PromotionsTest(ScoreboardCase):
    def build(self):
        f = self.floor
        for agent in ("p-1", "p-2"):
            f.born(agent, 0, family="fam-" + agent)
            f.verdict(agent, 0.2, "seat", 0, 1)
        f.verdict("p-1", 1, "promote", 1, 2, via="allocator", stake_usd="30")
        f.stake("p-1", 1.1, "kalshi", 30)
        f.buy("p-1", 2, "kalshi", "KXP-26SEP24-1")
        f.verdict("p-1", 6, "demote", 2, 1, via="allocator", reason="one loss")
        f.settle("p-1", 7, "kalshi", "KXP-26SEP24-1", 3)  # opened in the stay, settled after it: counted
        f.verdict("p-2", 3, "promote", 1, 2, via="allocator", stake_usd="10", band_to="probe")
        f.stake("p-2", 3.1, "kalshi", 10)
        f.buy("p-2", 4, "kalshi", "KXQ-26SEP24-1")
        f.settle("p-2", 7, "kalshi", "KXQ-26SEP24-1", -2)
        f.buy("p-2", 8, "kalshi", "KXR-26SEP24-1")  # still open
        f.verdict("p-3", 3, "promote", 1, 2, reason="the old screen")  # not the allocator's: not counted
        return f.snapshot()

    def test_each_stays_settled_result_and_the_share_positive(self):
        two = gs.scoreboard(self.build(), hosts=(), house_records=False)["metrics"]["2"]
        self.assertEqual(two["promotions"], 2)
        self.assertEqual(two["settlements"], 2)
        self.assertAlmostEqual(two["settled_pnl_usd"], 1.0)
        self.assertEqual((two["positive"], two["negative"]), (1, 1))
        self.assertEqual(two["share_positive"], 0.5)
        p1, p2 = two["rows"]
        self.assertEqual(p1["ended"], gs.iso(ts(6)))
        self.assertEqual(p2["open_positions"], 1)

    def test_a_baseline_keeps_later_promotions_and_labels_them(self):
        two = gs.scoreboard(self.build(), baseline=ts(2), hosts=(), house_records=False)["metrics"]["2"]
        self.assertEqual([r["agent"] for r in two["rows"]], ["p-2"])
        self.assertEqual((two["rows"][0]["label"], two["rows"][0]["label_source"]), ("probe", "promotion band_to"))
        self.assertAlmostEqual(two["settled_pnl_usd"], -2.0)
        self.assertEqual(two["share_positive"], 0.0)


# --------------------------------------------------------------------------------- metric 3
class RealDollarsTest(ScoreboardCase):
    def test_board_stakes_by_the_familys_state_and_alpaca_seats(self):
        f = self.floor
        f.born("p-1", 0, family="proven")
        f.stake("p-1", 0.1, "kalshi-shadow", 200)
        for i in range(10):  # ten distinct events, all won: proven
            f.settle("p-1", 1 + i, "kalshi-shadow", f"KXP{i}-26SEP24-1", 2 + (i % 3))
        f.born("u-1", 0, family="unproven")
        f.born("u-2", 0, family="alp", venue="alpaca", desk="alpaca-crypto-majors", horizon="hour")
        f.born("x-1", 0, family="unproven")
        f.write_json("allocator-board.json", {"at": at(12), "agents": {
            "p-1": {"band": "bunt", "stake_usd": "30", "venue": "kalshi"},
            "u-1": {"band": "bunt", "stake_usd": "10", "venue": "kalshi"},
            "u-2": {"band": "bunt", "stake_usd": "25", "venue": "alpaca"},
            "x-1": {"band": "paper", "stake_usd": None, "venue": "kalshi"}}})
        three = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["metrics"]["3"]
        self.assertEqual((three["proven_usd"], three["unproven_usd"]), (30.0, 35.0))
        self.assertEqual(three["alpaca_real_agents"], 1)


class HouseRecordTest(ScoreboardCase):
    """By default the scoreboard reads each family's record through the House's own function
    (`gs.HouseRecords`), so the scoreboard and the allocator cannot disagree on which family is proven."""

    def favourites(self):
        f = self.floor
        f.born("w-1", 0, family="favs")
        f.stake("w-1", 0.1, "kalshi-shadow", 100)
        for i in range(12):
            market = f"KXW{i}-26SEP24-B1"
            f.buy("w-1", 1 + i, "kalshi-shadow", market, quantity=10, price=0.95)
            f.settle("w-1", 1.5 + i, "kalshi-shadow", market, 0.5 + 0.01 * i)
        return f.snapshot()

    def test_the_houses_record_refuses_a_lopsided_record_the_t_bound_alone_proves(self):
        snap = self.favourites()
        own = gs.scoreboard(snap, hosts=(), house_records=False)
        house = gs.scoreboard(snap, hosts=())
        self.assertIn("favs", own["extras"]["family_records"]["proven"], "twelve wins with a spread pass the t bound alone")
        self.assertNotIn("favs", house["extras"]["family_records"]["proven"],
                         "twelve wins and no loss do not clear the House's loss-rate gate")
        self.assertEqual(house["metrics"]["1"]["record"], "house")
        self.assertEqual(own["metrics"]["1"]["record"], "scoreboard")

    def test_the_record_is_the_houses_function_on_the_snapshot(self):
        snap = self.favourites()
        agents = gs.agents_of(snap)
        records = gs.HouseRecords.open(snap, agents)
        self.assertIsNotNone(records, "this checkout has the House's family record")
        direct = records.compute(records, "favs", "kalshi", tape=records.tape)
        rec = records.record("kalshi", "favs")
        self.assertEqual(rec["n"], direct["n"])
        self.assertEqual(rec["n"], 12)
        self.assertEqual(rec["proven"], bool(direct["proven"]))
        self.assertAlmostEqual(rec["mean"], direct["mean_log"])
        self.assertEqual(rec["lcb"], direct.get("honest_bound", direct.get("bound")))
        before = records.record("kalshi", "favs", through=snap.head_seq - 4)
        self.assertLess(before["n"], rec["n"], "a record through an earlier ledger position has fewer events")


# --------------------------------------------------------------------------------- metric 4
class DeathsTest(ScoreboardCase):
    def test_median_life_day_horizon_and_deaths_before_three_fills(self):
        f = self.floor
        f.born("d-1", 0, horizon="hour", desk="kalshi-crypto-15m")
        f.born("d-2", 0, horizon="day")
        f.born("d-3", 0, horizon="day")
        for i in range(3):
            f.buy("d-3", 1 + i, "kalshi-shadow", f"KXD3-26SEP24-{i}")
        f.buy("d-2", 1, "kalshi-shadow", "KXD2-26SEP24-1")
        f.buy("d-2", 2, "kalshi-shadow", "KXD2-26SEP24-2")
        f.buy("d-2", 3, "kalshi-shadow", "KXD2-26SEP24-3", reason="the House is closing this account")  # the House's
        f.died("d-1", 10)
        f.died("d-2", 20)
        f.died("d-3", 30)
        f.row("ops.job", "house", 31, {})
        four = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["metrics"]["4"]  # window: 7 h to 31 h
        self.assertEqual(four["deaths"], 3)
        self.assertEqual(four["median_life_h"], 20.0)
        self.assertEqual(four["median_life_day_h"], 25.0)
        self.assertEqual(four["before_3_fills"], 2)
        self.assertEqual(four["share_before_3_fills"], round(2 / 3, 4))
        four = gs.scoreboard(f.snapshot(), since=ts(15), hosts=(), house_records=False)["metrics"]["4"]
        self.assertEqual(four["deaths"], 2)

    def test_deaths_among_agents_that_held_a_practice_seat(self):
        """A replay-only agent (rung 0) cannot fill: the seated measure leaves it out, and a seat taken
        after the death, or a seat never taken, does not count."""
        f = self.floor
        f.born("r-0", 0, desk="kalshi-crypto-15m")  # replay only: never seated
        f.born("s-1", 0)
        f.verdict("s-1", 1, "seat", 0, 1)
        f.buy("s-1", 2, "kalshi-shadow", "KXS1-26SEP24-1")
        f.born("s-2", 0)
        f.verdict("s-2", 1, "seat", 0, 1)
        for i in range(3):
            f.buy("s-2", 2 + i, "kalshi-shadow", f"KXS2-26SEP24-{i}")
        f.verdict("s-2", 6, "demote", 1, 0)  # back to replay before it died: it held a seat
        f.born("late", 0)
        f.died("r-0", 10)
        f.died("s-1", 12)
        f.died("s-2", 20)
        f.died("late", 21)
        f.verdict("late", 22, "seat", 0, 1)  # after the death: not a seat it held
        f.row("ops.job", "house", 23, {})
        four = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["metrics"]["4"]
        self.assertEqual(four["deaths"], 4)
        self.assertEqual(four["before_3_fills"], 3)
        self.assertEqual(four["seated_deaths"], 2)
        self.assertEqual(four["median_life_seated_h"], 16.0)
        self.assertEqual(four["seated_before_3_fills"], 1)
        self.assertEqual(four["share_seated_before_3_fills"], 0.5)
        text = gs.render_text(gs.scoreboard(f.snapshot(), hosts=(), house_records=False), markdown=True)
        self.assertIn("seated: 2 deaths", text)
        self.assertIn("agents that held a practice seat: 2 deaths", text)


# --------------------------------------------------------------------------------- metric 5
class LabTest(ScoreboardCase):
    def test_batches_llm_share_waiters_and_supersessions(self):
        f = self.floor
        now = 10.0
        lab = sqlite3.connect(f.root / "lab.sqlite")
        lab.executescript("CREATE TABLE batches(id TEXT PRIMARY KEY, at REAL NOT NULL);"
                          "CREATE TABLE candidates(id TEXT PRIMARY KEY, origin TEXT NOT NULL);"
                          "CREATE TABLE graduations(candidate TEXT PRIMARY KEY, state TEXT NOT NULL, at REAL NOT NULL);")
        for i, back in enumerate((600, 1800, 7200)):
            lab.execute("INSERT INTO batches VALUES (?, ?)", (f"b{i}", ts(now) - back))
        for i, origin in enumerate(("luna", "param", "param", "sol")):
            lab.execute("INSERT INTO candidates VALUES (?, ?)", (f"g{i}", origin))
            lab.execute("INSERT INTO graduations VALUES (?, 'born', ?)", (f"g{i}", ts(now - 1)))
        lab.execute("INSERT INTO candidates VALUES ('g5', 'agent')")
        lab.execute("INSERT INTO graduations VALUES ('g5', 'passed', ?)", (ts(now - 1),))  # moved by a retry
        lab.commit()
        lab.close()
        f.row("lab.graduate", "house", now - 5, {"candidate": "g5", "state": "passed"}, ident="lab.graduate:g5:passed")
        # Two cards passed replay; c2 was born, c1 waits from its passing evaluation at 7 h.
        f.row("hypothesis.card", "house", 0, {"id": "c1", "niche": "kalshi-weather", "created_epoch": ts(0)})
        f.row("hypothesis.card", "house", 0, {"id": "c2", "niche": "kalshi-weather", "created_epoch": ts(0)})
        f.row("trace.record", "house", now - 3, {"task": "hypothesis.evaluate", "id": "c1", "outcome": "passed"})
        f.row("trace.record", "house", now - 3, {"task": "hypothesis.evaluate", "id": "c2", "outcome": "passed"})
        f.born("card-agent", now - 2, founder="card:c2")
        # A real-money agent superseded in the window, and a real-money parent whose child passed replay.
        f.born("s-1", 0)
        f.verdict("s-1", 1, "promote", 1, 2, via="allocator")
        f.died("s-1", now - 2, cause="superseded")
        f.born("r-1", 0)
        f.verdict("r-1", 1, "promote", 1, 2, via="allocator")
        f.row("agent.forked", "r-1", 2, {"child": "r-2", "new_code": True})
        f.born("r-2", 2, parent="r-1")
        f.row("eval.trial", "r-2", 3, {"passed": True, "family": "fam"})
        f.row("ops.job", "house", now, {})
        five = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["metrics"]["5"]
        self.assertEqual(five["batches_last_hour"], 2)
        self.assertEqual((five["born_graduates_llm"], five["born_graduates"]), (2, 4))
        self.assertEqual(five["llm_share"], 0.5)
        self.assertEqual((five["graduates_waiting"], five["graduates_longest_wait_h"]), (1, 5.0))
        self.assertEqual((five["cards_waiting"], five["cards_longest_wait_h"]), (1, 3.0))
        self.assertEqual((five["waiters"], five["longest_wait_h"]), (2, 5.0))
        self.assertEqual((five["superseded_in_window"], five["superseded_in_window_on_real_money"]), (1, 1))
        self.assertEqual(five["real_money_parents_with_passing_child"], 1)
        self.assertEqual((five["of_them_superseded"], five["of_them_still_on_real_money"]), (0, 1))

    def test_a_waiter_that_left_the_houses_seat_queue_is_never_counted(self):
        """R2 (Sept 24, 2026): a graduate or card whose desk the search closed leaves the House's queue with a
        `seat-expired:<class>:<id>` row; the lab's table still says `passed`, the foundry's record still says it passed."""
        f = self.floor
        now = 10.0
        lab = sqlite3.connect(f.root / "lab.sqlite")
        lab.executescript("CREATE TABLE batches(id TEXT PRIMARY KEY, at REAL NOT NULL);"
                          "CREATE TABLE candidates(id TEXT PRIMARY KEY, origin TEXT NOT NULL);"
                          "CREATE TABLE graduations(candidate TEXT PRIMARY KEY, state TEXT NOT NULL, at REAL NOT NULL);")
        for ident in ("g1", "g2"):
            lab.execute("INSERT INTO candidates VALUES (?, 'param')", (ident,))
            lab.execute("INSERT INTO graduations VALUES (?, 'passed', ?)", (ident, ts(now - 1)))
        lab.commit()
        lab.close()
        for ident in ("g1", "g2"):
            f.row("lab.graduate", "house", now - 5, {"candidate": ident, "state": "passed"}, ident=f"lab.graduate:{ident}:passed")
        f.row("route.decision", "house", now - 1, {"task": "seat:graduates:g2", "route": "expired"}, ident="seat-expired:graduates:g2")
        for card in ("c1", "c2"):
            f.row("hypothesis.card", "house", 0, {"id": card, "niche": "kalshi-crypto-15m", "created_epoch": ts(0)})
            f.row("trace.record", "house", now - 3, {"task": "hypothesis.evaluate", "id": card, "outcome": "passed"})
        f.row("route.decision", "house", now - 1, {"task": "seat:cards:c2", "route": "expired"}, ident="seat-expired:cards:c2")
        f.row("ops.job", "house", now, {})
        five = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["metrics"]["5"]
        self.assertEqual((five["graduates_waiting"], five["graduates_left_the_queue"], five["cards_waiting"]), (1, 1, 1))
        self.assertEqual(five["waiters"], 2)
        # The review of #276: the House lets a waiter back once its reason is gone (the search reopened its desk) and
        # clears it from house.json `seat_expired`; its ledger row stays. The House's state decides.
        f.write_json("house.json", {"seat_expired": {"cards:c2": {"rule": "closed"}}})
        five = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["metrics"]["5"]
        self.assertEqual((five["graduates_waiting"], five["graduates_left_the_queue"], five["cards_waiting"]), (2, 0, 1))


# --------------------------------------------------------------------------------- metric 6
class ExitsAndStackingTest(ScoreboardCase):
    def test_self_cross_refusals_of_sells_in_the_last_six_hours(self):
        f = self.floor
        f.born("x-1", 0, venue="alpaca", desk="alpaca-crypto-alts", horizon="hour")
        reason = ["a market order here could trade against the House's own resting order"]
        for ident, side in (("i-sell", "sell"), ("i-buy", "buy"), ("i-old", "sell")):
            f.row("agent.intent", "x-1", 1, {"id": ident, "side": side, "book": "alpaca-paper"})
        f.row("book.refused", "x-1", 3, {"intent_id": "i-old", "reasons": reason})  # seven hours before the clock
        f.row("book.refused", "x-1", 9, {"intent_id": "i-sell", "reasons": reason})
        f.row("book.refused", "x-1", 9, {"intent_id": "i-buy", "reasons": reason})
        f.row("book.refused", "x-1", 9, {"intent_id": "i-sell", "reasons": ["below the venue minimum"]})
        f.row("ops.job", "house", 10, {})
        six = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["metrics"]["6"]["self_cross"]
        self.assertEqual((six["self_cross_refusals"], six["reducing"]), (2, 1))

    def test_a_promotion_on_stacked_strikes_of_one_game(self):
        f = self.floor
        f.born("k-1", 0, desk="kalshi-sports")
        f.born("k-2", 0, desk="kalshi-sports")
        for agent in ("k-1", "k-2"):
            f.stake(agent, 0.1, "kalshi-shadow", 200)
        for i, strike in enumerate(("7", "8", "9")):
            f.settle("k-1", 1 + i, "kalshi-shadow", f"KXMLBTOTAL-26SEP24GAME-{strike}", 1)
            f.settle("k-2", 1 + i, "kalshi-shadow", f"KXMLBTOTAL-26SEP24GAME{i}-{strike}", 1)
        f.verdict("k-1", 4, "promote", 1, 2, via="allocator")
        f.verdict("k-2", 4, "promote", 1, 2, via="allocator")
        stacked = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["metrics"]["6"]["stacked"]
        rows = {r["agent"]: r for r in stacked["rows"]}
        self.assertEqual((rows["k-1"]["closes"], rows["k-1"]["events"], rows["k-1"]["stacked"]), (3, 1, True))
        self.assertFalse(rows["k-1"]["passes_settled_per_event"])
        self.assertEqual((rows["k-2"]["events"], rows["k-2"]["stacked"]), (3, False))
        self.assertEqual((stacked["stacked"], stacked["promotions"], stacked["stacked_failing_all_per_event"]), (1, 2, 1))


# --------------------------------------------------------------------------------- metric 7
class InputsTest(ScoreboardCase):
    HOSTS = ("api.open-meteo.com", "ensemble-api.open-meteo.com", "api.weather.gov")

    def coverage(self, hours: float, end: float) -> None:
        self.floor.row("data.coverage", "house", hours, {"asset": "feed", "feed": "ensemble", "status": "current",
                                                         "source": "open-meteo: ensemble-api.open-meteo.com/v1/ensemble",
                                                         "end": at(end)})

    def test_a_host_is_live_when_its_feed_polled_ok_in_the_last_day(self):
        f = self.floor
        self.coverage(1, 1)
        f.row("ops.job", "house", 50, {})
        feeds = sqlite3.connect(f.root / "feeds.sqlite")
        feeds.executescript(FEEDS_SCHEMA)
        feeds.execute("INSERT INTO polls VALUES ('ensemble', 'NYC', ?, ?, 1, 1, NULL)", (ts(49), ts(49)))
        feeds.commit()
        feeds.close()
        rec = gs.recorders_live(f.snapshot(), self.HOSTS)
        self.assertEqual(rec["basis"], "feeds.sqlite")
        self.assertEqual({r["host"]: r["live"] for r in rec["rows"]},
                         {"api.open-meteo.com": False, "ensemble-api.open-meteo.com": True, "api.weather.gov": False})
        self.assertEqual(rec["live"], 1)

    def test_without_the_store_the_coverage_rows_decide_and_a_stale_one_is_not_live(self):
        f = self.floor
        self.coverage(1, 1)
        f.row("ops.job", "house", 50, {})
        self.assertEqual(gs.recorders_live(f.snapshot(), self.HOSTS)["live"], 0)  # 49 h old
        self.coverage(49, 49)
        rec = gs.recorders_live(f.snapshot(), self.HOSTS)
        self.assertEqual((rec["basis"], rec["live"]), ("data.coverage rows", 1))

    def test_a_host_name_inside_a_longer_one_is_not_that_host(self):
        self.assertFalse(gs.names_host("ensemble-api.open-meteo.com/v1", "api.open-meteo.com"))
        self.assertTrue(gs.names_host("https://api.open-meteo.com/v1/forecast", "api.open-meteo.com"))
        self.assertFalse(gs.names_host("api.open-meteo.com.example", "api.open-meteo.com"))

    def test_desks_offered_markets_with_no_intent_for_two_days(self):
        f = self.floor
        f.born("i-1", 0, venue="alpaca", desk="alpaca-open", horizon="hour")
        f.born("i-2", 0, desk="kalshi-weather")
        f.born("i-3", 0, desk="kalshi-attention")
        f.row("agent.woke", "i-1", 40, {"offered": 5, "intents": 0})
        f.row("agent.woke", "i-2", 40, {"offered": 3, "intents": 1})
        f.row("agent.woke", "i-3", 40, {"offered": 4, "intents": 0})
        f.row("agent.intent", "i-3", 30, {"id": "x", "side": "buy"})  # an intent in the 48 hours: not idle
        f.row("ops.job", "house", 50, {})
        idle = gs.idle_desks(f.snapshot(), gs.agents_of(f.snapshot()))
        self.assertEqual(idle["desks"], ["alpaca-open"])

    def test_the_allowed_hosts_are_the_block_the_owner_allowed_on_sept_24(self):
        self.assertEqual(gs.allowed_data_hosts(), (
            "api.open-meteo.com", "ensemble-api.open-meteo.com", "historical-forecast-api.open-meteo.com",
            "api.weather.gov", "www.sec.gov", "efts.sec.gov", "api.nasdaq.com", "markets.newyorkfed.org",
            "home.treasury.gov", "sports.core.api.espn.com", "www.tsa.gov", "www.realclearpolling.com"))


# ------------------------------------------------------------------------------ the extras
class EvidenceClockTest(ScoreboardCase):
    def test_first_fill_to_the_third_independent_settlement(self):
        f = self.floor
        f.born("e-1", 0, desk="kalshi-sports")
        f.buy("e-1", 1, "kalshi-shadow", "KXS-26SEP24A-1")
        f.settle("e-1", 3, "kalshi-shadow", "KXS-26SEP24A-1", 1)
        f.settle("e-1", 4, "kalshi-shadow", "KXS-26SEP24A-2", 1)  # the same game: not independent
        f.settle("e-1", 6, "kalshi-shadow", "KXS-26SEP24B-1", 1)
        f.settle("e-1", 10, "kalshi-shadow", "KXS-26SEP24C-1", 1)  # the third event: 9 h after the first fill
        f.born("e-2", 0, desk="kalshi-sports")
        f.buy("e-2", 2, "kalshi-shadow", "KXS-26SEP24D-1")
        f.settle("e-2", 5, "kalshi-shadow", "KXS-26SEP24D-1", 1)
        f.died("e-2", 6)  # censored at 4 h
        f.born("e-3", 0, venue="alpaca", desk="alpaca-crypto-alts", horizon="hour")
        f.buy("e-3", 1, "alpaca-paper", "SOL/USD", right=None)
        for hours in (2, 3, 4):  # every closed trade on Alpaca is its own event
            f.sell("e-3", hours, "alpaca-paper", "SOL/USD", 0.1)
        f.row("ops.job", "house", 12, {})
        snap = f.snapshot()
        agents, trades, *_ = self.parts(snap)
        clocks = gs.evidence_clocks(snap, agents, trades, gs.own_fills(snap))["desks"]
        self.assertEqual(clocks["kalshi-sports"], {"members": 2, "reached": 1, "median_reached_h": 9.0,
                                                   "km_median_h": 9.0, "censored_longest_h": 4.0})
        self.assertEqual(clocks["alpaca-crypto-alts"]["median_reached_h"], 3.0)

    def test_the_houses_closing_sale_is_not_the_members_settlement(self):
        """A member with two closes that died holding a third position did not reach its third
        settlement when the House sold that position (the House's own clock since the B-seats review)."""
        f = self.floor
        f.born("h-1", 0, venue="alpaca", desk="alpaca-crypto-alts", horizon="hour")
        f.buy("h-1", 1, "alpaca-paper", "SOL/USD", right=None)
        f.sell("h-1", 2, "alpaca-paper", "SOL/USD", 0.1)
        f.sell("h-1", 3, "alpaca-paper", "SOL/USD", 0.1)
        f.died("h-1", 4)
        f.sell("h-1", 4.5, "alpaca-paper", "SOL/USD", -0.2, reason="the House is closing this account")
        f.row("ops.job", "house", 6, {})
        snap = f.snapshot()
        agents, trades, *_ = self.parts(snap)
        clocks = gs.evidence_clocks(snap, agents, trades, gs.own_fills(snap))["desks"]
        self.assertEqual(clocks["alpaca-crypto-alts"]["reached"], 0)
        self.assertEqual(clocks["alpaca-crypto-alts"]["censored_longest_h"], 3.0)

    def test_the_kaplan_meier_median(self):
        self.assertEqual(gs.kaplan_meier_median([(4, False), (9, True)]), 9)
        # Four at risk: an event at 1 h (0.75), one censored at 2 h, an event at 3 h (0.75 x 2/3 = 0.5).
        self.assertEqual(gs.kaplan_meier_median([(1, True), (2, False), (3, True), (5, True)]), 3)
        # Censored at 1 h (three left), an event at 2 h (2/3), the rest censored: never down to a half.
        self.assertIsNone(gs.kaplan_meier_median([(1, False), (2, True), (3, False), (4, False)]))


class RenderingTest(ScoreboardCase):
    def test_every_metric_names_the_function_that_computed_it(self):
        f = self.floor
        f.born("a-1", 0)
        f.row("ops.job", "house", 1, {})
        board = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)
        text = gs.render_text(board)
        for number, _, _, functions in gs.summary_rows(board):
            self.assertIn(f"[{functions}]", text)
            for name in functions.split(", "):
                self.assertTrue(callable(getattr(gs, name)), name)
        markdown = gs.render_text(board, markdown=True)
        self.assertIn("| # | Metric | Reading | Computed by |", markdown)
        self.assertEqual(json.loads(json.dumps(board, default=str))["metrics"]["1"]["fn"], "real_bounds")

    def test_an_instant_is_an_instant_however_it_is_written(self):
        self.assertEqual(gs.epoch("2026-09-23 09:30:00"), gs.epoch("2026-09-23T09:30:00Z"))
        self.assertEqual(gs.epoch("2026-09-23T09:30:00+00:00"), gs.epoch("2026-09-23T09:30:00.000Z"))


# ---------------------------------------------------------------------------------------- take
class FakeApi:
    """The Sail client's exec and download, scripted: the backup snippet 'writes' what `stored` holds."""

    def __init__(self, stored: dict[str, bytes], files: dict[str, bytes], *, backup_ok: bool = True):
        self.stored, self.files, self.backup_ok = stored, files, backup_ok
        self.execs: list[list[str]] = []
        self.downloads: list[str] = []

    def exec(self, _box, command, **_kw):
        self.execs.append(list(command))

        class Result:
            pass

        result = Result()
        result.ok, result.stderr, result.stdout = True, "", ""
        if command[:2] == [gs.BOX_PYTHON, "-c"]:
            result.ok = self.backup_ok
            result.stdout = "\n".join(f"ok {n} {len(self.stored[n])}" if n in self.stored else f"missing {n}" for n in command[4:])
        return result

    def download(self, _box, path, **_kw):
        self.downloads.append(path)
        name = path.rsplit("/", 1)[-1]
        if name.endswith(".gz"):
            return gzip.compress(self.stored[name[:-3]])
        if name in self.files:
            return self.files[name]
        raise RuntimeError(f"no {path}")


class TakeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        source = Floor(Path(self._tmp.name))
        source.born("a-1", 0)
        source.db.commit()
        source.db.close()
        self.ledger = (Path(self._tmp.name) / "ledger.sqlite").read_bytes()
        self.target = Path(self._tmp.name) / "taken"

    def test_backs_up_read_only_downloads_and_deletes_the_box_copies(self):
        api = FakeApi({"ledger.sqlite": self.ledger}, {"health.json": b'{"release": "r1"}'})
        written = gs.take(self.target, api=api, box="sb_test")
        self.assertEqual(written, ["ledger.sqlite", "health.json"])
        snap = gs.Snapshot(self.target)
        self.addCleanup(snap.close)
        self.assertEqual(snap.rows_total, 1)
        self.assertEqual(snap.json["health.json"], {"release": "r1"})
        backup, cleanup = api.execs[0], api.execs[-1]
        remote = backup[3]
        self.assertTrue(remote.startswith("/tmp/gap-scoreboard-"))
        self.assertIn("mode=ro", backup[2])
        self.assertIn(".backup(", backup[2])
        self.assertEqual(backup[4:], list(gs.SNAPSHOT_SQLITE))
        self.assertEqual(cleanup, ["rm", "-rf", remote])
        self.assertIn(f"{remote}/ledger.sqlite.gz", api.downloads)

    def test_a_failed_backup_still_deletes_the_box_copies(self):
        api = FakeApi({}, {}, backup_ok=False)
        with self.assertRaises(SystemExit):
            gs.take(self.target, api=api, box="sb_test")
        self.assertEqual(api.execs[-1][:2], ["rm", "-rf"])


if __name__ == "__main__":
    unittest.main()
