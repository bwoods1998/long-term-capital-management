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


class FamilyKeyTest(ScoreboardCase):
    """C8 (Sept 25, 2026): the House files a program under its mechanism's family with an `agent.family` row and re-keyed
    every label once at deploy; the scoreboard reads those rows for membership (Z's follow-up), as the House's record does."""

    def build(self):
        f = self.floor
        f.born("m-1", 0, family="label")  # seq 1: moves to the mechanism's family later
        f.born("m-2", 0, family="label")  # seq 2: re-keyed from its birth, so the label never held it
        f.born("o-1", 0, family="label")  # seq 3: stays
        for agent in ("m-1", "m-2", "o-1"):
            f.stake(agent, 0.1, "kalshi-shadow", 200)
        f.row("agent.family", "m-2", 0.2, {"family": "mech-abc123", "was": "label", "since_seq": 2, "rule": "allocator.family_key"})
        f.bid("m-1", 1, "kalshi-shadow", "KXA-26SEP24-B1", "i-a", filled=True)
        f.settle("m-1", 2, "kalshi-shadow", "KXA-26SEP24-B1", 2)  # under the label
        f.buy("o-1", 1, "kalshi-shadow", "KXO-26SEP24-B1")
        f.settle("o-1", 2, "kalshi-shadow", "KXO-26SEP24-B1", 1)
        f.row("agent.family", "m-1", 3, {"family": "mech-abc123", "was": "label", "rule": "allocator.family_key"})
        f.bid("m-1", 4, "kalshi-shadow", "KXB-26SEP24-B1", "i-b", filled=True)
        f.settle("m-1", 5, "kalshi-shadow", "KXB-26SEP24-B1", 3)  # under the mechanism's family
        f.buy("m-2", 4, "kalshi-shadow", "KXC-26SEP24-B1")
        f.settle("m-2", 5, "kalshi-shadow", "KXC-26SEP24-B1", -1)
        return f.snapshot()

    def test_members_and_trades_follow_the_family_rows(self):
        snap = self.build()
        agents, trades, _, _, families = self.parts(snap)
        m1 = agents["m-1"]
        self.assertEqual((m1.label, m1.family), ("label", "mech-abc123"))
        self.assertEqual(m1.families(), ["label", "mech-abc123"])
        self.assertEqual(agents["m-2"].families(), ["mech-abc123"], "a birth re-keyed from its first row leaves its label none")
        members = {k: sorted(a.id for a in v) for k, v in families.members.items()}
        self.assertEqual(members[("kalshi", "mech-abc123")], ["m-1", "m-2"])
        self.assertEqual(members[("kalshi", "label")], ["m-1", "o-1"])
        by_family = {k: sorted(t.market for t in v) for k, v in families.trades.items()}
        self.assertEqual(by_family[("kalshi", "label")], ["KXA-26SEP24-B1", "KXO-26SEP24-B1"])
        self.assertEqual(by_family[("kalshi", "mech-abc123")], ["KXB-26SEP24-B1", "KXC-26SEP24-B1"])
        # Capacity reads a member's bids only while it was in the family.
        intents = gs.intent_outcomes(snap)
        cap = gs.family_capacity(snap, "kalshi", "mech-abc123", families.members[("kalshi", "mech-abc123")],
                                 families.trades[("kalshi", "mech-abc123")], intents)
        self.assertEqual(cap["markets_bid"], 1)

    def test_the_scoreboard_lists_the_new_family_as_the_house_records_it(self):
        snap = self.build()
        board = gs.scoreboard(snap, hosts=())
        fr = board["extras"]["family_records"]
        rows = {r["family"]: r for r in fr["families"]}
        self.assertIn("mech-abc123", rows)
        self.assertEqual((rows["mech-abc123"]["members"], rows["label"]["members"]), (2, 2))
        self.assertEqual((fr["moved_agents"], fr["families_from_rows"]), (2, 1))
        records = gs.HouseRecords.open(snap, gs.agents_of(snap))
        house = records.compute(records, "mech-abc123", "kalshi", tape=records.tape)
        self.assertEqual(house["members"], 2)
        self.assertEqual(rows["mech-abc123"]["pooled"]["n"], house["n"])
        self.assertEqual(house["n"], 2)
        self.assertEqual(records.compute(records, "label", "kalshi", tape=records.tape)["n"], rows["label"]["pooled"]["n"])
        self.assertEqual(rows["label"]["pooled"]["n"], 2)


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


# ---------------------------------------------------------- the forward-first rows (Sept 25, 2026)
def lab_store(root: Path, script: str):
    lab = sqlite3.connect(root / "lab.sqlite")
    lab.executescript(script)
    return lab


FORWARD_SCHEMA = ("CREATE TABLE forward(candidate TEXT NOT NULL, at REAL NOT NULL, window_start REAL, window_end REAL, tape_id TEXT,"
                  " ok INTEGER NOT NULL, blocks INTEGER, active_blocks INTEGER NOT NULL, log_growth REAL, mean_log_growth REAL,"
                  " trades INTEGER, error TEXT, PRIMARY KEY(candidate, at));")


class UsSessionTest(unittest.TestCase):
    def test_the_regular_session_on_the_nyse_calendar(self):
        # Thursday Sept 24, 2026, New York on daylight time: 13:30-20:00Z.
        self.assertEqual(gs.us_session(ts(15)), (ts(13.5), ts(20)))
        self.assertTrue(gs.in_us_session(ts(13.5)))
        self.assertFalse(gs.in_us_session(ts(13.4)))
        self.assertFalse(gs.in_us_session(ts(20)))
        self.assertIsNone(gs.us_session(ts(48 + 15)))  # Saturday
        # Thanksgiving is shut, and the day after closes at 13:00 New York (18:00Z on standard time).
        self.assertIsNone(gs.us_session(datetime(2026, 11, 26, 16, tzinfo=timezone.utc).timestamp()))
        friday = gs.us_session(datetime(2026, 11, 27, 15, tzinfo=timezone.utc).timestamp())
        self.assertEqual(friday, (datetime(2026, 11, 27, 14, 30, tzinfo=timezone.utc).timestamp(),
                                  datetime(2026, 11, 27, 18, tzinfo=timezone.utc).timestamp()))
        # The last session that opened by the clock, cut at it.
        self.assertEqual(gs.last_session(ts(4), ts(28)), (ts(13.5), ts(20)))
        self.assertEqual(gs.last_session(ts(4), ts(16)), (ts(13.5), ts(16)))
        self.assertIsNone(gs.last_session(ts(21), ts(28)))


class UnitEconomicsTest(ScoreboardCase):
    def test_real_settled_profit_net_of_fees_against_compute_a_day(self):
        f = self.floor
        f.settle("a-1", 2, "kalshi", "KXA-1", 1.25)  # before the window [4, 28]
        f.settle("a-1", 10, "kalshi", "KXB-1", 3.0)
        f.settle("house", 11, "kalshi", "KXC-1", -0.5)  # the House's own settlement of a dead member's holding counts
        f.settle("a-1", 12, "kalshi-shadow", "KXD-1", 9.0)  # practice: never
        f.sell("b-1", 13, "alpaca", "BTC-USD", 0.4)  # a closing sale on the real book
        f.buy("b-1", 13, "alpaca", "ETH-USD")  # an opening fill realizes nothing
        f.row("book.fill", "house", 14, {"book": "alpaca", "source": "dust", "realized": "-0.01", "cash_delta": "-0.01"})
        # Compute: Luna verified (one unconfirmed hold is left out), a consultant pass, the Sail meter, a Jev charge.
        f.row("provider.request", "a-1", 1, {"cost_usd": "7", "cost_verified": True, "session_id": "s0"})  # lifetime only
        f.row("provider.request", "a-1", 10, {"cost_usd": "1.50", "cost_verified": True, "session_id": "s1"})
        f.row("provider.request", "a-1", 11, {"cost_usd": "0.50", "cost_verified": True, "session_id": "s1"})
        f.row("provider.request", "a-1", 11, {"held_usd": "0.9", "cost_verified": False, "session_id": "s1"})
        f.row("merton.pass", "house", 12, {"role": "consultant", "cost_usd": "2.25"})
        f.row("ops.budget", "house", 12, {"what": "sail", "spent_usd": "0.75", "balance_usd": "100"})
        f.row("credit.charge", "a-1", 12, {"what": "jev classification", "usd": "0.10"})
        # The gateway's meter of the House's OpenAI line, and an hourly yield row: checks, never added.
        for hours, settled in ((6, "100"), (18, "106")):
            f.row("ops.budget", "house", hours, {"what": "expedition", "campaign": {"meters": {"openai": {
                "line": {"settled_usd": settled}, "month": {"month": "2026-09", "total_usd": "400", "cap_usd": "607"}}}}})
        f.row("ops.budget", "house", 20, {"what": "yield", "hours": 1.0, "total_usd": "3.75", "spend_usd": {"research": "2.0", "consultant": "1.75"}})
        lab = lab_store(f.root, "CREATE TABLE calls(id TEXT PRIMARY KEY, at REAL NOT NULL, cost_usd TEXT NOT NULL);")
        lab.execute("INSERT INTO calls VALUES ('c0', ?, '0.30')", (ts(1),))
        lab.execute("INSERT INTO calls VALUES ('c1', ?, '0.40')", (ts(20),))
        lab.commit()
        lab.close()
        f.row("ops.job", "house", 28, {})  # the clock: 28 h, the window from 4 h
        one = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["forward_first"]["1"]
        s = one["real_settled"]
        self.assertEqual((s["settlements"], s["sales"]), (2, 1))
        self.assertAlmostEqual(s["settled_usd"], 2.5)
        self.assertAlmostEqual(s["sales_usd"], 0.4)
        self.assertAlmostEqual(s["per_day_usd"], 2.9)
        self.assertAlmostEqual(s["house_rows_usd"], -0.5)
        c = one["compute_per_day"]
        self.assertEqual({k: c["providers"][k] for k in ("openai-luna", "openai-astra", "sail", "jev", "openai-lab")},
                         {"openai-luna": 2.0, "openai-astra": 2.25, "sail": 0.75, "jev": 0.1, "openai-lab": 0.4})
        self.assertAlmostEqual(c["per_day_usd"], 5.5)
        self.assertAlmostEqual(c["openai_usd"], 4.65)
        self.assertAlmostEqual(c["lifetime_usd"], 5.5 + 7 + 0.3)  # economics.py's lifetime method, plus every lab call
        self.assertEqual((c["gateway"]["usd"], c["gateway"]["hours"], c["gateway"]["per_day_usd"]), (6.0, 12.0, 12.0))
        self.assertEqual((c["yield"]["rows"], c["yield"]["usd"], c["yield"]["by_line"]["consultant"]), (1, 3.75, 1.75))
        u = one["unit_economics"]
        self.assertEqual(u["compute_over_profit"], round(5.5 / 2.9, 2))
        self.assertTrue(u["meets_target"], "no family swings and compute is under $60 a day")

    def test_the_target_twice_the_profit_or_sixty_a_day_while_no_family_swings(self):
        target = lambda profit, cost, swings: gs.unit_economics({"per_day_usd": profit}, {"per_day_usd": cost}, swings)["meets_target"]  # noqa: E731
        self.assertFalse(target(21.35, 118.88, False))  # the T0 day: 5.6 times
        self.assertTrue(target(60.0, 118.88, True))
        self.assertTrue(target(20.0, 59.0, False))
        self.assertFalse(target(20.0, 59.0, True), "a swinging family is held to twice the profit")
        self.assertFalse(target(-3.0, 70.0, False))


class CapacityAtSizesTest(ScoreboardCase):
    def build(self):
        f = self.floor
        f.born("w-1", 0, family="wx")
        f.stake("w-1", 0.5, "kalshi", 50)
        # Two real markets bid at $9.50 (both filled) and a practice one at $19 (not filled), from 1 h to the clock at 25 h.
        f.bid("w-1", 1, "kalshi", "KXA-26SEP24-B1", "i1", filled=True)
        f.bid("w-1", 1, "kalshi", "KXB-26SEP24-B1", "i2", filled=True)
        f.bid("w-1", 2, "kalshi-shadow", "KXC-26SEP24-B1", "i3", filled=False, quantity=20)
        f.settle("w-1", 10, "kalshi", "KXA-26SEP24-B1", 0.5)
        f.settle("w-1", 12, "kalshi", "KXB-26SEP24-B1", 0.3)
        f.row("ops.job", "house", 25, {})
        return f.snapshot()

    def test_the_real_size_and_its_multiples_read_the_fill_rate_measured_there(self):
        snap = self.build()
        *_, families = self.parts(snap)
        out = gs.capacity_at_sizes(snap, "kalshi", "wx", families.members[("kalshi", "wx")], families.trades[("kalshi", "wx")],
                                   gs.intent_outcomes(snap))
        self.assertEqual((out["size_usd"], out["size_basis"]), (9.5, "the median real bid"))
        one, two, four = out["sizes"]
        self.assertEqual((one["bucket"], one["fill_rate"], one["fill_rate_basis"]), ("<=$12", 1.0, "all books"))
        self.assertAlmostEqual(one["capacity_usd_per_day"], 3 * 1.0 * 0.4)  # 3 markets a day x filled x $0.40 a settlement
        self.assertEqual((two["size_usd"], two["bucket"], two["fill_rate"]), (19.0, "$12-25", 0.0))  # the $19 bid never filled
        self.assertEqual(two["capacity_usd_per_day"], 0.0)
        self.assertEqual((four["bucket"], four["fill_rate"], four["fill_rate_basis"]), ("$25-50", None, "no bid of this size yet"))
        self.assertIsNone(four["capacity_usd_per_day"], "an unmeasured size is never assumed to fill")
        self.assertAlmostEqual(four["profit_per_settlement_usd"], 1.6)

    def test_proven_families_with_the_boards_capacity_and_the_boards_disagreements(self):
        self.floor.write_json("allocator-board.json", {"families": {"kalshi": {
            "wx": {"state": "proven", "stake_usd": "30", "capacity": {"usd_per_day": 1.1, "size_usd": 6.0}},
            "other": {"state": "swing"}, "loser": {"state": "unproven"}}}})
        snap = self.build()
        *_, families = self.parts(snap)
        out = gs.proven_capacity(snap, families, gs.intent_outcomes(snap), [{"venue": "kalshi", "family": "wx"}])
        self.assertEqual(out["count"], 1)
        row = out["families"][0]
        self.assertEqual((row["board_state"], row["house_capacity"]["usd_per_day"]), ("proven", 1.1))
        self.assertEqual(row["sizes"]["size_usd"], 9.5)
        self.assertEqual(out["board_only"], ["kalshi/other"])


class ForwardPositiveTest(ScoreboardCase):
    def test_graduates_newborns_and_the_baselines_lab_blocks(self):
        f = self.floor
        lab = lab_store(f.root, FORWARD_SCHEMA)
        for cand, hours, active, growth in (("g1", 10, 3, 0.02), ("g1", 20, 4, -0.01),  # its latest window loses
                                            ("g2", 12, 2, 0.03), ("g2", 31, 2, -0.9),  # a window after the clock is not read
                                            ("g3", 12, 0, 0.0),  # no active block: not tested
                                            ("g4", 12, 5, 0.5)):  # graduated before the window
            lab.execute("INSERT INTO forward VALUES (?, ?, 0, 0, 'fwd', 1, ?, ?, ?, ?, 0, NULL)", (cand, ts(hours), active, active, growth, growth))
        lab.commit()
        lab.close()
        for cand, hours in (("g1", 8), ("g2", 9), ("g3", 9), ("g5", 9), ("g4", 2)):
            f.row("lab.graduate", "house", hours, {"candidate": cand}, ident=f"lab.graduate:{cand}:passed")
        f.row("lab.graduate", "house", 9, {"candidate": "g2"}, ident="lab.graduate:g2:waiting_seat")

        def block(agent: str, hours: float, book: str, growth: float, active: bool = True) -> None:
            f.row("eval.block", agent, hours, {"book": book, "active": active, "log_growth": growth})

        # Newborns in the window [6, 30]: n-1 gains on practice (its real block is not practice), n-2 loses, n-3 has none.
        f.born("n-1", 8)
        block("n-1", 10, "kalshi-shadow", 0.02)
        block("n-1", 11, "kalshi", 1.0)
        block("n-1", 12, "kalshi-shadow", -0.005)
        f.born("n-2", 9, venue="alpaca", desk="alpaca-crypto-alts", horizon="hour", founder="lab:x")
        block("n-2", 10, "alpaca-paper", -0.03)
        block("n-2", 11, "alpaca-paper", 0.5, active=False)
        f.born("n-3", 20)
        # Born the day before: their first practice day ended in the window. l-1 is lab-born.
        f.born("o-1", 1)
        block("o-1", 3, "kalshi-shadow", 0.01)
        block("o-1", 20, "kalshi-shadow", 0.02)
        f.born("o-2", 2)
        block("o-2", 27, "kalshi-shadow", -0.1)  # after its first day
        f.born("l-1", 0, founder="lab:y")
        block("l-1", 5, "kalshi-shadow", 0.03)  # before the window: not one of the window's lab blocks
        block("l-1", 7, "kalshi-shadow", 0.01)
        block("l-1", 8, "kalshi-shadow", 0.02)
        f.row("ops.job", "house", 30, {})
        fp = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["forward_first"]["2"]["forward_positive"]
        self.assertEqual(fp["graduates"], {"graduated": 4, "with_window": 3, "tested": 2, "positive": 1, "share": 0.5})
        self.assertEqual(fp["newborns"], {"born": 3, "tested": 2, "positive": 1, "share": 0.5})
        self.assertEqual(fp["newborns_first_day_ended"], {"born": 3, "tested": 2, "positive": 2, "share": 1.0})
        # The baseline's measure: lab-born agents' active blocks in the window (n-2's loss, l-1's two gains).
        self.assertEqual(fp["lab_blocks"], {"active": 3, "positive": 2, "share": round(2 / 3, 4)})

    def test_the_boards_median_w_paper_and_the_line(self):
        board = {f"a-{i}": {"evidence": {"W_paper": w, "E": e}} for i, (w, e) in
                 enumerate(((1.02, 1.01), (1.0, 1.0), (0.99, 0.99), (1.011, 1.0), (1.01, 1.02)))}
        board["r-1"] = {"band": "replay"}
        self.floor.write_json("allocator-board.json", {"at": at(1), "agents": board})
        self.floor.born("a-0", 0)
        ps = gs.practice_standing(self.floor.snapshot())
        self.assertEqual((ps["agents"], ps["with_evidence"], ps["median_w_paper"]), (6, 5, 1.01))
        self.assertEqual(ps["above_line"], 2, "over 1.01, as the plan counted")
        self.assertEqual((ps["bunt_at"], ps["e_at_bunt"]), (1.01, 2))


class CapitalOnProofTest(ScoreboardCase):
    def test_the_swing_clock_and_alpaca_real_stock_agents(self):
        f = self.floor
        f.write_json("allocator-board.json", {"families": {"kalshi": {
            "sports": {"state": "proven", "swing_clock": {"real_n": 11, "days_to_swing": 0.72, "real_per_day": 5.5,
                                                          "needs": {"look_at": 15, "real_settlements": 4}}},
            "other": {"state": "unproven"}}}})
        for agent, desk in (("s-1", "alpaca-megacaps"), ("s-2", "alpaca-megacaps"), ("s-3", "alpaca-index-etfs"),
                            ("o-1", "alpaca-open"), ("o-2", "alpaca-open"), ("c-1", "alpaca-crypto-alts")):
            f.born(agent, 0, venue="alpaca", desk=desk, horizon="day")
        equity, crypto = {"asset_class": "equity", "symbol": "NVDA"}, {"asset_class": "crypto", "symbol": "SOL-USD"}

        def fill(agent: str, hours: float, book: str, instrument: dict) -> None:
            f.row("book.fill", agent, hours, {"book": book, "side": "buy", "source": "venue", "instrument": instrument,
                                              "quantity": "1", "cash_delta": "-10"})

        fill("s-1", 15, "alpaca", equity)  # a real stock fill inside the Sept 24 session
        fill("s-3", 15, "alpaca-paper", equity)  # practice: never
        fill("c-1", 15, "alpaca", crypto)
        for agent in ("s-2", "o-1", "o-2", "c-1"):
            f.stake(agent, 1, "alpaca", 25)
        f.row("agent.intent", "o-1", 2, {"id": "i-o1", "side": "buy", "book": "alpaca", "instrument": equity})
        f.row("agent.intent", "o-2", 2, {"id": "i-o2", "side": "buy", "book": "alpaca", "instrument": crypto})
        f.row("ops.job", "house", 28, {})
        cp = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["forward_first"]["3"]["capital_on_proof"]
        self.assertEqual((cp["swinging"], cp["first_swing"]), ([], None))
        self.assertEqual(cp["swing_clocks"], [{"family": "sports", "venue": "kalshi", "state": "proven", "real_n": 11, "look_at": 15,
                                               "to_go": 4, "days_to_swing": 0.72, "real_per_day": 5.5}])
        self.assertEqual((cp["alpaca_stock_filled"], cp["alpaca_stock_filled_in_session"], cp["alpaca_stock_staked"]), (1, 1, 2))
        self.assertEqual(cp["alpaca_stock_agents"], ["o-1", "s-1", "s-2"])

    def test_the_first_swing_is_the_earliest_row_that_names_one(self):
        f = self.floor
        f.born("m-1", 0, family="sports")
        f.write_json("allocator-board.json", {"families": {"kalshi": {"sports": {"state": "swing"}}}})
        f.verdict("m-1", 18, "promote", 2, 3, via="allocator", band_from="bunt", band_to="swing")
        f.row("family.record", "house", 20, {"family": "sports", "venue": "kalshi", "state": "swing"})
        f.row("ops.job", "house", 28, {})
        cp = gs.capital_on_proof(f.snapshot(), gs.agents_of(f.snapshot()))
        self.assertEqual(cp["swinging"], ["kalshi/sports"])
        self.assertEqual((cp["first_swing"]["at"], cp["first_swing"]["row"], cp["first_swing"]["family"]),
                         (at(18), "eval.verdict", "sports"))


class HarnessTest(ScoreboardCase):
    def test_restarts_rollbacks_by_cause_and_deploys_in_a_session_from_the_watchdogs_log(self):
        f = self.floor
        for hours, release in ((1, "r0"), (15, "r1"), (15.2, "r0"), (22, "r2"), (22.2, "r0"), (26, "r0")):
            f.row("ops.started", "house", hours, {"release": release})
        f.row("ops.job", "house", 28, {})  # the clock: the window from 4 h
        log = [
            {"deploy": "r5@5", "release": "r5", "stage": "start", "at": at(2)},  # before the window
            {"deploy": "r1@1", "release": "r1", "stage": "start", "at": at(14.9)},
            {"deploy": "r1@1", "release": "r1", "stage": "promote", "ok": True, "at": at(15)},
            {"deploy": "r1@1", "release": "r1", "stage": "verdict", "verdict": "rolled_back", "at": at(15.2),
             "reasons": ["reading 3: the alpaca-paper book is frozen: cash differs by -0.0269"]},
            {"deploy": "r2@2", "release": "r2", "stage": "start", "at": at(21.8)},
            {"deploy": "r2@2", "release": "r2", "stage": "promote", "ok": True, "ts": ts(22)},
            {"deploy": "r2@2", "release": "r2", "stage": "verdict", "verdict": "rolled_back", "at": at(22.2), "reasons": [
                "reading 9: 1 error alert(s) since seq 5; the first, at seq 6: The daily backup of the House box failed "
                "(SailboxError: sailbox api 503: prepare checkpoint warm snapshot ...)"]},
            {"deploy": "r3@3", "release": "r3", "stage": "start", "at": at(23)},
            {"deploy": "r3@3", "release": "r3", "stage": "verdict", "verdict": "refused", "reasons": ["canary"], "at": at(23.1)},
            {"release": "r4", "stage": "vet", "verdict": "refused", "reasons": ["league/allocator.py: ..."], "at": at(24)},
            {"deploy": "r7@7", "release": "r7", "stage": "verdict", "verdict": "refused", "busy": True, "at": at(24.5),
             "reasons": ["another deploy or rollback is running (pid 10274)"]},  # never staged: not a deploy
            {"deploy": "r6@6", "release": "r6", "stage": "start", "at": at(29)},  # after the clock
        ]
        (f.root / "deploys.jsonl").write_text("\n".join(json.dumps(r) for r in log) + "\n{torn", encoding="utf-8")
        four = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["forward_first"]["4"]
        self.assertEqual((four["restarts"]["count"], four["restarts"]["in_session"]), (5, 2))
        dr = four["deploy_record"]
        self.assertEqual(dr["source"], "deploys.jsonl")
        self.assertEqual((dr["deploys"], dr["verdicts"]), (3, {"rolled_back": 2, "refused": 1}))
        self.assertEqual((dr["rolled_back"], dr["outside"], dr["causes"]), (2, 1, {"house": 1, "backup": 1}))
        self.assertEqual(dr["in_session"], 1, "r1 started at 14:54Z; r2 after the close")
        self.assertEqual([r["release"] for r in dr["rows"]], ["r1", "r2", "r3"])

    def test_without_the_log_the_ledger_shows_updater_and_owner_deploys_and_their_rollbacks(self):
        f = self.floor
        f.row("ops.started", "house", 1, {"release": "main-a"})  # the first start is no deploy
        f.row("ops.started", "house", 15, {"release": "20260924T145900Z-abc"})  # an owner's release: nothing announced it
        f.row("ops.deploy", "house", 22, {"action": "deploying", "release": "main-b"})
        f.row("ops.started", "house", 22.05, {"release": "main-b"})
        f.row("ops.alert", "house", 22.1, {"level": "error", "text": "The daily backup of the House box failed (SailboxError: sailbox api 503)"})
        f.row("ops.started", "house", 22.2, {"release": "20260924T145900Z-abc"})  # main-b rolled back
        f.row("ops.deploy", "house", 24, {"action": "deploying", "release": "main-c"})  # refused at its canary: never started
        f.row("ops.started", "house", 25.5, {"release": "20260924T145900Z-abc"})  # a restart 90 minutes on: no rollback
        f.row("ops.job", "house", 28, {})
        dr = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["forward_first"]["4"]["deploy_record"]
        self.assertEqual(dr["source"], "ledger")
        self.assertEqual([(r["release"], r["verdict"], r["cause"], r["in_session"]) for r in dr["rows"]],
                         [("20260924T145900Z-abc", "promoted", None, True), ("main-b", "rolled_back", "backup", False),
                          ("main-c", "not started", None, False)])
        self.assertEqual((dr["rolled_back"], dr["outside"], dr["in_session"]), (1, 1, 1))
        self.assertIn("sailbox api 503", dr["rows"][1]["reason"])

    def test_a_rollbacks_cause_from_its_reasons(self):
        self.assertEqual(gs.rollback_cause(["The daily backup of the House box failed (SailboxError: ...)"]), "backup")
        self.assertEqual(gs.rollback_cause(["tick failed: SailboxError: sailbox api 503: busy"]), "vendor")
        self.assertEqual(gs.rollback_cause(["publish failed: the site answered 500"]), "site")
        self.assertEqual(gs.rollback_cause(["reading 3: the alpaca-paper book is frozen: cash differs by -0.0269"]), "house")
        self.assertEqual(gs.rollback_cause([]), "house")

    def test_tick_intervals_from_the_per_tick_job_and_the_last_tick(self):
        f = self.floor
        f.row("ops.started", "house", 0.5, {"release": "r0"})

        def job(hours: float, elapsed: float, key: str = "merton:follow", state: str = "finished") -> None:
            f.row("ops.job", "house", hours, {"key": key, "job": f"{key}:{ts(hours):.6f}", "state": state, "elapsed_seconds": elapsed})

        job(10.0, 0.01)
        job(10.0, 0.0, state="started")  # a job's start row is not a tick
        job(10.02, 30.0)  # it waited 30 s in the lane: the next tick skipped it, so the interval after it is not one tick
        job(10.05, 0.01)
        job(10.06, 0.01, key="engineer")  # another job
        job(10.07, 0.01)
        f.row("ops.started", "house", 11, {"release": "r1"})  # a restart between 10.07 h and 12 h
        job(12.0, 0.01)
        job(12.03, 0.01)
        f.row("ops.job", "house", 13, {})
        f.write_json("health.json", {"tick_steps": {"last": {"at": at(12.9), "total_seconds": 33.5}, "ticks_in_hour": 40,
                                                    "slowest_hour": [{"step": "population", "seconds": 16.0, "at": at(12.5)},
                                                                     {"step": "wakes", "seconds": 9.0, "at": at(12.6)}]}})
        tp = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["forward_first"]["4"]["tick_p50"]
        self.assertEqual(tp["intervals"], 3)  # 72 s, 72 s and 108 s
        self.assertAlmostEqual(tp["p50_s"], 72.0, places=1)
        self.assertAlmostEqual(tp["p90_s"], 108.0, places=1)
        self.assertEqual((tp["last_tick_s"], tp["ticks_in_hour"], tp["population_slowest_s"]), (33.5, 40, 16.0))


class SeatMarketTest(ScoreboardCase):
    def build(self, health: bool = True):
        f = self.floor
        f.born("s-1", 5, desk="kalshi-sports")
        f.died("s-1", 7)  # 2 h, displaced
        f.born("s-2", 6, desk="kalshi-sports")
        f.died("s-2", 10, cause="evidence")  # 4 h
        f.born("w-1", -20, desk="kalshi-weather")
        f.died("w-1", 20)  # 40 h, displaced
        f.born("d-0", 0, desk="kalshi-weather")
        f.died("d-0", 2)  # before the window [4, 28]: lifetime only
        f.born("l-1", 20, desk="kalshi-sports")  # living, 8 h old
        f.row("ops.job", "house", 28, {})
        if health:
            f.write_json("health.json", {"seats": {
                "at": at(27), "waiters": {"cards": 2, "graduates": 3, "strategies": 4}, "displaceable": 0,
                "over_two_hours": {"kalshi-sports": {"count": 2, "longest_hours": 5.0}, "kalshi-weather": {"count": 1}},
                "caps": {"kalshi-sports": {"cap": 19, "members": 18}, "kalshi-weather": {"cap": 17, "members": 17}},
                "longest_wait": {"class": "cards", "desk": "kalshi-weather", "hours": 60.6, "id": "c1"},
                "evidence_clocks": {"at": at(3), "hours": {"kalshi-sports": 20.5, "kalshi-weather": 31.8, "kalshi-prices": None}}}})
        return gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["forward_first"]["5"]

    def test_waiters_over_two_hours_life_against_the_clock_and_displacement(self):
        five = self.build()
        sq = five["seat_queue"]
        self.assertEqual((sq["waiters"], sq["over_two_hours"], sq["over_two_hours_on_free_desks"]), (9, 3, 2))
        self.assertEqual((sq["free_desks"], sq["longest_h"], sq["strategies_waiting"]), (["kalshi-sports"], 60.6, 4))
        lc = five["life_vs_clock"]
        self.assertEqual(lc["desks"]["kalshi-sports"], {"deaths": 2, "median_life_h": 3.0, "clock_h": 20.5, "below_clock": True,
                                                        "living": 1, "median_age_h": 8.0})
        self.assertFalse(lc["desks"]["kalshi-weather"]["below_clock"])  # 40 h over a 31.8 h clock
        self.assertEqual((lc["below"], lc["measured"]), (["kalshi-sports"], 2))
        ds = five["displacement_share"]
        self.assertEqual(ds["window"], {"deaths": 3, "displaced": 2, "share": round(2 / 3, 4)})
        self.assertEqual(ds["lifetime"], {"deaths": 4, "displaced": 3, "share": 0.75})

    def test_without_the_houses_seat_market_the_lab_and_the_scoreboards_own_clocks_stand_in(self):
        five = self.build(health=False)
        self.assertTrue(five["seat_queue"]["source"].startswith("lab_loop"))
        self.assertIsNone(five["seat_queue"]["strategies_waiting"])
        self.assertEqual(five["life_vs_clock"]["clocks"], "evidence_clocks (Kaplan-Meier median)")


class ExecutionTest(ScoreboardCase):
    def test_fill_rate_per_order_refusals_by_rule_and_probe_takers(self):
        f = self.floor
        f.born("p-1", 0)
        f.born("b-1", 0)
        f.born("a-1", 0, venue="alpaca", desk="alpaca-crypto-alts", horizon="hour")
        f.verdict("p-1", 1, "promote", 1, 2, via="allocator", band_from="paper", band_to="probe")
        f.verdict("b-1", 1, "promote", 1, 2, via="allocator", band_from="paper", band_to="bunt")
        f.verdict("a-1", 1, "promote", 1, 2, via="allocator", band_to="probe")

        def order(hours: float, oid: str, book: str, status: str) -> None:
            f.row("book.order", "house", hours, {"book": book, "order_id": oid, "side": "buy", "status": status})

        def fill(agent: str, hours: float, book: str, oid: str, liquidity: str, cash: float) -> None:
            f.row("book.fill", agent, hours, {"book": book, "side": "buy", "source": "venue", "order_id": oid, "liquidity": liquidity,
                                              "cash_delta": str(-cash), "quantity": "1", "price": "1", "instrument": {"market_id": "KXZ-1"}})

        order(2, "o1", "kalshi", "accepted")  # placed before the window [4, 28]
        order(5, "o2", "kalshi", "new")
        order(5, "o2", "kalshi", "accepted")
        order(6, "o2", "kalshi", "filled")
        order(7, "o3", "kalshi", "accepted")
        order(8, "o3", "kalshi", "cancelled")
        order(9, "o4", "kalshi-shadow", "accepted")  # practice: never
        order(10, "o5", "alpaca", "accepted")
        order(10, "o5", "alpaca", "filled")
        fill("b-1", 5, "kalshi", "o1", "maker", 5.0)
        fill("p-1", 6, "kalshi", "o2", "taker", 9.5)  # a probe's Kalshi taker entry
        fill("a-1", 10, "alpaca", "o5", "taker", 12.25)  # Alpaca books every fill a taker
        fill("b-1", 11, "kalshi", "o9", "taker", 3.0)  # a bunt's
        f.sell("b-1", 12, "kalshi", "KXZ-1", 0.5)  # an exit: a fill row, never an entry
        for ident, side, book in (("i0", "buy", "kalshi"), ("i1", "buy", "kalshi"), ("i2", "buy", "kalshi"), ("i3", "sell", "kalshi"),
                                  ("i4", "buy", "kalshi-shadow"), ("i5", "buy", "alpaca"), ("i6", "buy", "kalshi")):
            f.row("agent.intent", "p-1", 2.5, {"id": ident, "side": side, "book": book})
        taking = "a real entry on fam must be a post-only limit until ... (constitution allocator.real_entry_liquidity)"
        f.row("book.refused", "p-1", 3, {"book": "kalshi", "intent_id": "i0", "reasons": [taking]})  # before the window
        f.row("book.refused", "p-1", 14, {"book": "kalshi", "intent_id": "i1", "reasons": [taking]})
        f.row("book.refused", "b-1", 15, {"book": "kalshi", "intent_id": "i2", "reasons": [
            "one event may hold at most 25% of the stake: ... (constitution allocator.max_event_share)"]})
        f.row("book.refused", "p-1", 16, {"book": "kalshi", "intent_id": "i3", "reasons": ["a sell"]})
        f.row("book.refused", "p-1", 16, {"book": "kalshi-shadow", "intent_id": "i4", "reasons": ["practice"]})
        f.row("book.refused", "a-1", 22, {"intent_id": "i5", "reasons": ["the alpaca book is frozen until it reconciles: cash differs by 0.0108"]})
        f.row("book.refused", "p-1", 23, {"book": "kalshi", "intent_id": "i6", "reasons": ["insufficient desk cash: 1.20 < 9.50"]})
        f.row("ops.job", "house", 28, {})
        six = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["forward_first"]["6"]
        fr = six["real_fill_rate"]
        self.assertEqual((fr["orders"], fr["filled"], fr["rate"]), (3, 2, round(2 / 3, 4)))
        self.assertEqual(fr["by_book"], {"kalshi": {"orders": 2, "filled": 1, "rate": 0.5}, "alpaca": {"orders": 1, "filled": 1, "rate": 1.0}})
        self.assertEqual((fr["order_rows"], fr["fill_rows"]), (7, 5))  # the baseline's measure counts status rows as orders
        rr = six["real_refusals"]
        self.assertEqual((rr["refused"], rr["entries"], rr["per_day"]), (5, 4, 4.0))
        self.assertEqual(rr["by_rule"], {"allocator.real_entry_liquidity": 1, "allocator.max_event_share": 1, "a frozen book": 1,
                                         "insufficient desk cash": 1})
        self.assertEqual((rr["session"]["open"], rr["session"]["entries"]), (gs.iso(ts(13.5)), 2))
        pt = six["probe_taker_entries"]
        self.assertEqual((pt["taker_entries"], pt["by_band"], pt["probe_taker_entries"]), (3, {"probe": 2, "bunt": 1}, 2))
        self.assertEqual(pt["probe_taker_by_book"], {"kalshi": {"entries": 1, "usd": 9.5}, "alpaca": {"entries": 1, "usd": 12.25}})
        self.assertEqual((pt["refused_as_takers"], pt["probe_refused_as_takers"], pt["probes_refused"]), (1, 1, ["p-1"]))


class RunwayTest(ScoreboardCase):
    def test_sail_runway_the_october_cap_and_the_population_ceiling(self):
        f = self.floor
        for hours, balance, spent in ((2, 100, 0.5), (6, 90, 1), (18, 80, 6), (28, 76, 4)):
            f.row("ops.budget", "house", hours, {"what": "sail", "balance_usd": str(balance), "spent_usd": str(spent)})
        f.row("ops.alert", "house", 10, {"level": "warning", "text": "the league's population is now 112 (was 128): held at 112"})
        f.row("ops.alert", "house", 20, {"level": "info", "text": "the league's population is now 128 (was 112): toward the ceiling"})
        f.write_json("health.json", {"seats": {"population": {"ceiling": 128, "max_population": 112, "rule": "held at 112",
                                                              "sail": {"reserve_usd": 5.0, "runway_days": 6.5}}},
                                     "campaign": {"meters": {"openai": {"month": {"month": "2026-10", "total_usd": "12.5", "cap_usd": "300"}}},
                                                  "accounts": {"sail": {"remaining_usd": "70"}}}})
        rw = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)["forward_first"]["7"]["runway"]
        # The last day's readings (6, 18 and 28 h): $10 spent after the first over 22 hours.
        self.assertEqual((rw["sail_balance_usd"], rw["sail_readings"], rw["sail_burn_per_day_usd"]), (76.0, 3, round(10 * 24 / 22, 2)))
        self.assertAlmostEqual(rw["sail_runway_days"], round(71 / (10 * 24 / 22), 2))
        self.assertEqual((rw["openai_month"]["month"], rw["october_cap_usd"]), ("2026-10", 300.0))
        self.assertTrue(rw["population_binds"])
        self.assertEqual((rw["population_alerts"], rw["population_held_alerts"]), (2, 1))
        self.assertEqual(rw["sail_campaign_remaining_usd"], 70.0)

    def test_septembers_month_leaves_octobers_cap_unset(self):
        self.floor.row("ops.job", "house", 1, {})
        self.floor.write_json("health.json", {"campaign": {"meters": {"openai": {"month": {"month": "2026-09", "total_usd": "529.37", "cap_usd": "607"}}}}})
        rw = gs.runway(self.floor.snapshot(), ts(-23))
        self.assertIsNone(rw["october_cap_usd"])
        self.assertFalse(rw["population_binds"])


class ForwardRenderingTest(ScoreboardCase):
    def test_every_forward_reading_names_its_functions_and_markdown_prints_both_tables(self):
        f = self.floor
        f.born("a-1", 0)
        f.row("ops.job", "house", 1, {})
        board = gs.scoreboard(f.snapshot(), hosts=(), house_records=False)
        for number, row in board["forward_first"].items():
            for name, value in row.items():
                self.assertEqual(value["fn"], name, f"row {number}")
                self.assertTrue(callable(getattr(gs, name)), name)
        parts = gs.forward_parts(board)
        self.assertEqual(sorted(parts), [str(i) for i in range(1, 8)])
        for number, rows in parts.items():
            for fn, _ in rows:
                self.assertTrue(callable(getattr(gs, fn)), fn)
        markdown = gs.render_text(board, markdown=True)
        forward = "| # | Metric | Reading (each number names its function) | Target at the end |"
        self.assertIn(forward, markdown)
        self.assertLess(markdown.index(forward), markdown.index("| # | Metric | Reading | Computed by |"), "the forward rows come first")
        for number, _, reading, target in gs.forward_rows(board, markdown=True):
            self.assertTrue(all(f"`{fn}`" in reading for fn, _ in parts[number]))
            self.assertEqual(target, gs.FORWARD_TARGETS[number])
        self.assertIn("[real_settled]", gs.render_text(board))
        self.assertEqual(json.loads(json.dumps(board, default=str))["forward_first"]["4"]["deploy_record"]["source"], "ledger")

    def test_a_pipe_in_a_reading_does_not_end_its_cell(self):
        self.assertEqual(gs._cell("kalshi-open|hour|t3"), "kalshi-open\\|hour\\|t3")


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

    def test_the_watchdogs_deploy_log_comes_with_the_snapshot(self):
        log = json.dumps({"deploy": "r1@1", "release": "r1", "stage": "start", "at": at(1)}).encode() + b"\n"
        api = FakeApi({"ledger.sqlite": self.ledger}, {"deploys.jsonl": log})
        written = gs.take(self.target, api=api, box="sb_test")
        self.assertEqual(written, ["ledger.sqlite", "deploys.jsonl"])
        self.assertIn("/workspace/deploys.jsonl", api.downloads)
        snap = gs.Snapshot(self.target)
        self.addCleanup(snap.close)
        self.assertEqual(snap.deploys, [{"deploy": "r1@1", "release": "r1", "stage": "start", "at": at(1)}])
        # A log kept elsewhere is named with --deploys; without one the ledger is read.
        other = Path(self._tmp.name) / "elsewhere.jsonl"
        other.write_bytes(log + log)
        snap2 = gs.Snapshot(self.target, deploys=other)
        self.addCleanup(snap2.close)
        self.assertEqual(len(snap2.deploys), 2)
        self.assertIsNone(gs.read_deploys(Path(self._tmp.name) / "missing.jsonl"))

    def test_a_failed_backup_still_deletes_the_box_copies(self):
        api = FakeApi({}, {}, backup_ok=False)
        with self.assertRaises(SystemExit):
            gs.take(self.target, api=api, box="sb_test")
        self.assertEqual(api.execs[-1][:2], ["rm", "-rf"])


if __name__ == "__main__":
    unittest.main()
