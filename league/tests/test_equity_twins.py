"""THE EQUITY TWINS (release E1; league/ops/twins.py `equity_twin`, `equity_round` and the `equity_twins` job): each
closed equity lot's replay twin in closed form from the House's own official opens and closes, with the engine's fill
function (open and close fills, A2), the same fees and dividends and split; its gap in bp a side; the same-risk
buy-and-hold beside it; "priced", "no_bar" or "unpriceable", final once judged.

Every figure is invented. Core's `league.equity.engine.fill_price`, `league.equity.config.half_spread` and
`config.sell_fees` are called through their interface (league/equity/INTERFACES.md 4.2, 4.6); `CoreAtItsInterface` holds
them to the formulas the interface fixes."""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from league.ops import twins as TW

NY = ZoneInfo("America/New_York")
CENT = Decimal("0.01")


# ------------------------------------------------------------------------------------------------- core, at its interface
def fake_fill_price(official: float, side: str, hs: float, k: float) -> float:
    if side not in ("buy", "sell") or not (isinstance(official, (int, float)) and official > 0):
        raise ValueError("a side and a positive price")
    return official * (1 + k * hs) if side == "buy" else official * (1 - k * hs)


def fake_half_spread(symbol: str) -> float:
    from league.equity import config

    return config.HALF_SPREAD_BP[symbol] / 10_000.0


def fake_sell_fees(proceeds: Decimal, shares: Decimal) -> Decimal:
    from league.equity import config

    sec = (Decimal(proceeds) * config.SEC_FEE_PER_MILLION / Decimal(1_000_000)).quantize(CENT, rounding=ROUND_CEILING)
    taf = min((Decimal(shares) * config.TAF_PER_SHARE).quantize(CENT, rounding=ROUND_CEILING), config.TAF_MAX)
    return sec + taf


class CoreAtItsInterface(unittest.TestCase):
    def test_cores_functions_are_the_interfaces_formulas(self):
        """The twins call core's `engine.fill_price`, `config.half_spread` and `config.sell_fees`
        (league/equity/INTERFACES.md 4.2, 4.6): each is the formula the interface fixes."""
        from league.equity import config, engine

        for official, side, hs, k in ((600.0, "buy", 0.0001, 1.0), (600.0, "sell", 0.0001, 1.5), (42.5, "sell", 0.0005, 1.0)):
            self.assertAlmostEqual(engine.fill_price(official, side, hs, k), fake_fill_price(official, side, hs, k), places=9)
        for symbol in ("SPY", "XLK", "GLD"):
            self.assertEqual(config.half_spread(symbol), fake_half_spread(symbol))
        for proceeds, shares in (("1", "1"), ("312.77", "0.52"), ("250000", "1500"), ("1000000", "60000")):
            self.assertEqual(config.sell_fees(Decimal(proceeds), Decimal(shares)),
                             fake_sell_fees(Decimal(proceeds), Decimal(shares)))


# ------------------------------------------------------------------------------------------------- fixtures
def ny(day: str, hh: int = 10, mm: int = 0) -> float:
    d = dt.date.fromisoformat(day)
    return dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).timestamp()


def _is_day(text) -> bool:
    try:
        dt.date.fromisoformat(str(text))
    except ValueError:
        return False
    return True


def lot(lid: int = 1, *, family: str = "seed-overnight-spy", version: int = 1, lane: str = "beta", symbol: str = "SPY",
        klass: str = "etf", notional: str = "50.00", opened_qty: str = "0.499900", qty: str = "0.499900",
        entry_px: str = "100.02", exit_px: str = "101.95", fees: str = "0.02", div: str = "0", cash: str = "0.944805",
        entry_at: str = "open", exit_at: str = "close", opened_day: str = "2026-10-13", exit_day: str = "2026-10-15",
        status: str = "closed", probe: int = 1, closed_at: float | None = None, info: str = "{}",
        route: str = ":r") -> dict:
    """An `eq_lots` row (league/equity/live.py SCHEMA), its money as Decimal strings."""
    return {"lid": lid, "instance": f"{family}@{version}{route}", "family": family, "version": version, "lane": lane,
            "symbol": symbol, "class": klass, "qty": qty, "opened_qty": opened_qty, "entry_px": entry_px,
            "entry_notional": notional, "entry_at": entry_at, "fees": fees, "div": div, "mark": None, "marked_at": None,
            "opened_at": ny(opened_day, 9, 31), "opened_day": opened_day, "status": status, "exit_px": exit_px,
            "exit_at": exit_at, "exit_day": exit_day, "closed_at": closed_at if closed_at is not None else
            ny(exit_day, 15, 56) if status == "closed" and _is_day(exit_day) else None,
            "cash": cash, "reason": "program", "probe": probe, "tag": "", "iid": None, "info": info}


def bar(o: float, c: float, *, audit: str | None = "ok") -> dict:
    return {"o": str(o), "h": str(max(o, c) + 1), "l": str(min(o, c) - 1), "c": str(c), "v": "1000000", "audit": audit,
            "sha": "x" * 64}


GOLDEN_BARS = {"2026-10-13": bar(100.0, 100.5), "2026-10-14": bar(100.5, 101.0), "2026-10-15": bar(101.5, 102.0)}


def add_tables(live) -> None:
    from league.equity.live import SCHEMA

    live.db.executescript(SCHEMA)


def put_lot(live, row: dict) -> None:
    live.upsert("eq_lots", row, "lid")


def put_bars(live, symbol: str, bars: dict, *, at: float = 0.0) -> None:
    for day, b in bars.items():
        live.upsert("eq_bars", {"day": day, "symbol": symbol, "adjustment": "raw", "o": b["o"], "h": b["h"], "l": b["l"],
                                "c": b["c"], "v": b["v"], "fetched_at": at, "sha": b["sha"], "audit": b["audit"]},
                    "day, symbol, adjustment")


# ================================================================================================== the twin
class TheTwin(unittest.TestCase):
    def twin(self, row=None, bars=GOLDEN_BARS, **kw):
        return TW.equity_twin(row or lot(), bars, at=ny("2026-10-16", 9, 50), **kw)

    def test_the_golden_twin_buys_the_open_and_sells_the_close_with_the_same_fees(self):
        rec = self.twin()
        self.assertEqual((rec["key"], rec["status"], rec["final"], rec["why"]), ("eq:1", "priced", True, None))
        self.assertEqual((rec["entry_official"], rec["exit_official"]), (100.0, 102.0))
        # Entry 100 x (1 + 1 bp) = 100.01: floor(50 / 100.01, 6 dp) = 0.499950 shares for 49.9999995; exit 102 x (1 - 1 bp)
        # = 101.9898: proceeds 50.98980051, SEC $0.01 and TAF $0.01 (each up to the cent).
        twin = rec["twin"]
        self.assertEqual((twin["entry_px"], twin["exit_px"], twin["shares"], twin["fees"]), (100.01, 101.9898, "0.499950",
                                                                                            0.02))
        expected = (Decimal("50.98980051") - Decimal("0.02") - Decimal("49.9999995")) / Decimal("49.9999995")
        self.assertAlmostEqual(rec["twin_return"], float(expected), places=6)
        self.assertAlmostEqual(rec["live_return"], 0.944805 / 50.0, places=6)
        # Live minus twin, a side: the real fills paid about 5 bp more than the model over the round trip.
        self.assertAlmostEqual(rec["gap_bp"], (0.944805 / 50.0 - float(expected)) / 2 * 1e4, places=2)
        self.assertLess(rec["gap_bp"], 0)
        # The measured slippage of each real fill against its official price, and the cost-free buy-and-hold.
        self.assertEqual((rec["entry_slip_bp"], rec["exit_slip_bp"]), (2.0, 4.9))
        self.assertEqual(rec["bh"]["usd"], 1.0)
        self.assertEqual(rec["bh"]["return"], 0.02)
        self.assertEqual((rec["twin"]["exit"], rec["live"]["exit"], rec["exit_agrees"]), ("close", "close", True))

    def test_a_close_entry_and_an_open_exit_read_the_close_and_the_open_A2(self):
        rec = self.twin(lot(entry_at="close", exit_at="open", opened_day="2026-10-14", exit_day="2026-10-15"))
        self.assertEqual((rec["entry_official"], rec["exit_official"]), (101.0, 101.5))
        self.assertEqual(rec["twin"]["entry_px"], round(101.0 * 1.0001, 6))
        stress = self.twin(lot(entry_at="close", exit_at="open", opened_day="2026-10-14", exit_day="2026-10-15"), k=1.5)
        self.assertEqual(stress["twin"]["entry_px"], round(101.0 * 1.00015, 6))
        self.assertLess(stress["twin_return"], rec["twin_return"], "a wider half-spread costs the twin more")

    def test_dividends_and_a_split_follow_the_lot(self):
        # One share bought at 100 and split 2-for-1 before it was sold at 51 (post-split): two shares sold, $0.50 of
        # dividends credited to the lot.
        row = lot(notional="100.00", opened_qty="1", qty="2", entry_px="50.00", exit_px="51.00", div="0.50",
                  fees="0.02", cash="2.48", symbol="SPY")
        bars = {"2026-10-13": bar(100.0, 100.0), "2026-10-15": bar(51.0, 51.0)}
        rec = self.twin(row, bars)
        self.assertEqual(rec["split_factor"], 2.0)
        shares = Decimal("0.999900")  # floor(100 / 100.01, 6 dp)
        self.assertEqual(rec["twin"]["shares"], str(shares))
        self.assertAlmostEqual(rec["twin"]["div"], float(Decimal("0.50") * shares), places=2)
        # Buy-and-hold: 1 share x 2 x 51 + $0.50 - $100 = $2.50.
        self.assertEqual(rec["bh"]["usd"], 2.5)
        # A lot whose qty the book zeroed at the close: the split is read from its proceeds.
        rec_zero = self.twin({**row, "qty": "0"}, bars)
        self.assertEqual(rec_zero["split_factor"], rec["split_factor"])
        self.assertEqual(self.twin({**lot(), "qty": "0"})["split_factor"], 1.0)

    def test_a_missing_bar_is_no_bar_and_final_only_once_settled(self):
        bars = {k: v for k, v in GOLDEN_BARS.items() if k != "2026-10-15"}
        rec = self.twin(bars=bars, settled=False)
        self.assertEqual((rec["status"], rec["final"]), ("no_bar", False))
        self.assertIn("2026-10-15", rec["why"])
        rec = self.twin(bars=bars, settled=True)
        self.assertEqual((rec["status"], rec["final"]), ("no_bar", True))
        self.assertIsNone(rec["gap_bp"])

    def test_unaudited_bars_wait_and_a_mismatch_is_a_note(self):
        bars = {**GOLDEN_BARS, "2026-10-15": bar(101.5, 102.0, audit=None)}
        rec = self.twin(bars=bars, settled=False)
        self.assertEqual((rec["status"], rec["final"]), ("priced", False))
        self.assertIn("audit", rec["why"])
        rec = self.twin(bars=bars, settled=True)
        self.assertEqual((rec["status"], rec["final"]), ("priced", True))
        self.assertIn("never audited", rec["note"])
        rec = self.twin(bars={**GOLDEN_BARS, "2026-10-13": bar(100.0, 100.5, audit="mismatch")}, settled=False)
        self.assertEqual((rec["status"], rec["final"]), ("priced", True))
        self.assertIn("A8.11", rec["note"])

    def test_a_lot_that_cannot_be_read_is_unpriceable(self):
        cases = [lot(symbol="ZZZZ"), lot(entry_at="midday"), lot(notional="0"), lot(cash="n/a"),
                 lot(exit_day="soon", closed_at=ny("2026-10-15", 15, 56))]
        for row in cases:
            rec = self.twin(row)
            self.assertEqual((rec["status"], rec["final"]), ("unpriceable", True), row)
        rec = self.twin(lot(status="open"))
        self.assertEqual((rec["status"], rec["final"]), ("unpriceable", False))


# ================================================================================================== the round and the job
class TheRound(unittest.TestCase):
    def setUp(self):
        from league.live.state import LiveState
        from league.swarm.store import SwarmStore

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = SwarmStore(self.root)
        self.addCleanup(self.store.close)
        self.live = LiveState(self.root / "live.sqlite")
        self.addCleanup(self.live.close)
        add_tables(self.live)
        self.alerts = []

    def ctx(self, now):
        return SimpleNamespace(root=self.root, now=lambda: now, alert=lambda level, text: self.alerts.append((level, text)))

    def test_settled_counts_the_sessions_begun_after_the_exit_day(self):
        self.assertFalse(TW.settled_after("2026-10-15", ny("2026-10-16", 9, 0)), "Friday's session has not begun")
        self.assertFalse(TW.settled_after("2026-10-15", ny("2026-10-16", 10, 0)), "one session begun")
        self.assertFalse(TW.settled_after("2026-10-15", ny("2026-10-18", 12, 0)), "a weekend adds none")
        self.assertTrue(TW.settled_after("2026-10-15", ny("2026-10-19", 9, 50)))
        self.assertFalse(TW.settled_after("not a day", ny("2026-10-19", 9, 50)))

    def test_the_job_judges_each_closed_lot_once_and_keeps_only_final_records(self):
        put_lot(self.live, lot(1))
        put_lot(self.live, lot(2, exit_day="2026-10-16", cash="0.50", exit_px="101.10"))   # its exit day's bar not yet in
        put_lot(self.live, lot(3, status="open", exit_px=None, exit_at=None, exit_day=None, cash="0"))
        put_bars(self.live, "SPY", GOLDEN_BARS)
        out = TW.run(self.ctx(ny("2026-10-16", 9, 50)))
        self.assertTrue(out["ok"], out)
        self.assertEqual((out["closed"], out["judged"], out["pending"]), (2, {"priced": 1}, 1))
        records = TW.equity_records(self.store)
        self.assertEqual(set(records), {"eq:1"})
        self.assertEqual(records["eq:1"]["status"], "priced")
        # A final record is never judged again: a changed bar moves nothing.
        put_bars(self.live, "SPY", {"2026-10-15": bar(90.0, 90.0)})
        TW.run(self.ctx(ny("2026-10-16", 10, 0)))
        self.assertEqual(TW.equity_records(self.store)["eq:1"]["exit_official"], 102.0)
        # Two sessions past its exit day with no bar: lot 2 is final "no_bar".
        out = TW.run(self.ctx(ny("2026-10-20", 9, 50)))
        self.assertEqual(out["judged"], {"no_bar": 1})
        self.assertEqual(TW.equity_records(self.store)["eq:2"]["status"], "no_bar")
        self.assertEqual(self.alerts, [])

    def test_a_note_is_a_house_warning_and_nothing_to_do_is_skipped(self):
        self.assertEqual(TW.run(self.ctx(ny("2026-10-16", 9, 50)))["status"], "skipped")
        put_lot(self.live, lot(1))
        put_bars(self.live, "SPY", {**GOLDEN_BARS, "2026-10-15": bar(101.5, 102.0, audit="mismatch")})
        out = TW.run(self.ctx(ny("2026-10-16", 9, 50)))
        self.assertEqual(out["notes"], ["eq:1"])
        self.assertEqual(self.alerts[0][0], "warning")
        self.assertIn("eq:1", self.alerts[0][1])

    def test_without_a_swarm_store_or_a_book_from_before_e1_it_is_skipped(self):
        from league.live.state import LiveState

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = TW.run(SimpleNamespace(root=root, now=lambda: 0.0, alert=lambda *a: None))
            self.assertEqual(out["status"], "skipped")
            LiveState(root / "live.sqlite").close()
            (root / "swarm.sqlite").write_bytes(b"")
            self.assertEqual(TW.read_equity(root / "live.sqlite"), {"lots": [], "bars": {}})

    def test_the_registry_runs_it_before_the_dlane_report(self):
        from league.ops.registry import JOBS, by_name

        job = by_name()["equity_twins"]
        self.assertEqual((job.module, job.in_pause, job.paid), ("league.ops.twins", True, False))
        self.assertEqual([t.kind for t in job.triggers], ["start", "daily", "open"])
        self.assertEqual(job.triggers[2].offset_minutes, -40, "after the book's morning re-fetch, before dlane's -30")
        names = [j.name for j in JOBS]
        self.assertLess(names.index("equity_twins"), names.index("dlane"))
        dlane = by_name()["dlane"]
        self.assertLess(job.triggers[1].at, dlane.triggers[1].at)
        self.assertTrue(json.dumps(job.what))


if __name__ == "__main__":
    unittest.main()
