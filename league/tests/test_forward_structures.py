"""scripts/forward_structures.py: the forward test's harness sees no future and fills only on a newer snapshot.

Sept 25, 2026 (the options-desk run's Wave 2, builder G-FORWARD). The harness runs the structure founders on the
day's recorded OPRA snapshots through the House's own context methods, `Book` and `OptionsShadowBroker`. What it
must never do: show a decision a snapshot recorded after it, or fill an order on the snapshot its decision saw. These
tests build a small snapshot file by hand and replace a founder's `decide` with a probe.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "forward_structures.py"
spec = importlib.util.spec_from_file_location("forward_structures_under_test", SCRIPT)
fwd = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fwd  # a dataclass reads its module from sys.modules
spec.loader.exec_module(fwd)

LOW, HIGH = "SPY260925C00700000", "SPY260925C00701000"  # a 0-DTE SPY call vertical (Friday Sept 25, 2026)


def row(occ: str, bid: float, ask: float, as_of: str, size: int | None = 100) -> dict:
    return {"symbol": occ, "underlying": "SPY", "expiry": "2026-09-25", "strike": int(occ[-8:]) / 1000, "right": "call",
            "bid": bid, "ask": ask, "bid_size": size, "ask_size": size, "as_of": as_of, "last": None, "last_t": None, "mbar": None, "volume": 10}


def line(at: str, rows: list[dict], spot: tuple[float, float] = (700.4, 700.42)) -> str:
    return json.dumps({"v": 2, "at": at, "feed": "opra", "spot": {"SPY": {"bid": spot[0], "ask": spot[1]}}, "rows": rows, "errors": []})


class Harness(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "live.jsonl"

    def write(self, lines: list[str], partial: str = "") -> None:
        self.path.write_text("\n".join(lines) + "\n" + partial, encoding="utf-8")

    def run_probe(self, decide) -> dict:
        return fwd.run(self.path, house_bars=None, local_store=None, founders=["options_condor_vrp"], work=self.dir.name,
                       decide_override={"options_condor_vrp": decide})

    def test_a_snapshot_is_available_at_its_newest_quote_and_a_partial_line_ends_the_stream(self):
        self.write([line("2026-09-25T15:00:00.000000Z", [row(LOW, 1.0, 1.05, "2026-09-25T15:00:07.123456789Z")])],
                   partial='{"v": 2, "at": "2026-09-25T15:01:00Z", "rows": [')
        snaps = list(fwd.read_snapshots(self.path))
        self.assertEqual(len(snaps), 1)
        self.assertEqual(fwd.iso(snaps[0].t), "2026-09-25T15:00:07.123456Z")  # not its start: a quote in it is 7 s later

    def test_the_leg_source_never_serves_a_snapshot_from_after_the_clock(self):
        self.write([line("2026-09-25T15:00:00Z", [row(LOW, 1.0, 1.05, "2026-09-25T15:00:05Z")])])
        clock = fwd.SimClock(fwd.parse_ts("2026-09-25T15:00:04Z"))
        source = fwd.LegSource(clock)
        source.current = next(fwd.read_snapshots(self.path))
        with self.assertRaises(AssertionError):
            source([LOW])
        clock.now = source.current.t
        self.assertEqual(str(source([LOW])[LOW]["ask"]), "1.05")

    def test_a_decision_sees_only_the_snapshots_up_to_its_minute(self):
        seen = []

        def probe(ctx):
            chain = {r["occ"]: r for r in ctx.get("chain") or []}
            seen.append({"now": ctx["now"], "bid": chain.get(LOW, {}).get("bid"),
                         "newest": max((r["as_of"] for r in ctx.get("chain") or []), default=None),
                         "spot": ctx["quotes"]["SPY"]["bid"]})
            return {"intents": [], "cancels": [], "memory": {}}

        self.write([
            line("2026-09-25T15:00:00Z", [row(LOW, 1.00, 1.05, "2026-09-25T14:59:59Z"), row(HIGH, 0.50, 0.52, "2026-09-25T14:59:59Z")]),
            line("2026-09-25T15:01:00Z", [row(LOW, 2.00, 2.05, "2026-09-25T15:00:59Z"), row(HIGH, 1.50, 1.52, "2026-09-25T15:00:59Z")], (701.0, 701.02)),
            line("2026-09-25T15:05:00Z", [row(LOW, 3.00, 3.05, "2026-09-25T15:04:59Z"), row(HIGH, 2.50, 2.52, "2026-09-25T15:04:59Z")], (702.0, 702.02)),
        ])
        result = self.run_probe(probe)
        # condor-vrp wakes every 5 minutes: at the first snapshot (15:00:00) and at the one of 15:05:00
        self.assertEqual([s["bid"] for s in seen], [1.00, 3.00])
        self.assertEqual([s["spot"] for s in seen], [700.4, 702.0])
        for s in seen:
            self.assertLessEqual(fwd.parse_ts(s["newest"]), fwd.parse_ts(s["now"]))
        self.assertEqual(result["checks"]["decision_snapshot_after_clock"], 0)
        self.assertEqual([index for _, index in result["checks"]["decision_snapshots"]["fwd-options-condor-vrp"]], [0, 2])

    def test_a_fill_needs_a_strictly_newer_snapshot_of_every_leg(self):
        def probe(ctx):
            if ctx["positions"] or ctx["open_orders"] or (ctx.get("memory") or {}).get("sent"):
                return {"intents": [], "cancels": [], "memory": ctx.get("memory") or {}}
            return {"intents": [{"structure": "debit_vertical", "action": "open", "quantity": 1, "type": "limit", "limit_price": 0.60,
                                 "legs": [{"occ": LOW, "role": "long"}, {"occ": HIGH, "role": "short"}], "reason": "probe"}],
                    "cancels": [], "memory": {"sent": 1}}

        self.write([
            line("2026-09-25T15:00:00Z", [row(LOW, 1.00, 1.05, "2026-09-25T14:59:59Z"), row(HIGH, 0.50, 0.52, "2026-09-25T14:59:59Z")]),
            # the same quotes again (their times unchanged): the decision's own quote, never a fill
            line("2026-09-25T15:01:00Z", [row(LOW, 1.00, 1.05, "2026-09-25T14:59:59Z"), row(HIGH, 0.50, 0.52, "2026-09-25T14:59:59Z")]),
            # one leg quoted again, the other not: still no fill (every leg must be newer)
            line("2026-09-25T15:02:00Z", [row(LOW, 1.00, 1.04, "2026-09-25T15:01:59Z"), row(HIGH, 0.50, 0.52, "2026-09-25T14:59:59Z")]),
            # both quoted again: the ask 1.07 - 0.50 = 0.57 is within the 0.60 limit, and the fill is AT it
            line("2026-09-25T15:03:00Z", [row(LOW, 1.02, 1.07, "2026-09-25T15:02:59Z"), row(HIGH, 0.50, 0.53, "2026-09-25T15:02:58Z")]),
        ])
        result = self.run_probe(probe)
        log = result["checks"]["fill_log"]
        self.assertEqual(len(log), 1, log)
        self.assertEqual((log[0]["submitted_snapshot"], log[0]["filled_snapshot"]), (0, 3))
        self.assertEqual(log[0]["price"], "0.57")
        self.assertEqual(result["checks"]["fills_not_on_newer_snapshot"], 0)
        # the audit, apart from the broker: the touch from the raw rows, every leg quoted after the acceptance, sizes
        self.assertEqual(log[0]["audit"], {"ok": True, "touch": "0.57", "legs_newer_than_acceptance": True, "legs_short_of_size": []})
        self.assertEqual(result["checks"]["fills_failing_audit"], 0)
        [founder] = result["founders"]
        self.assertEqual(founder["opens"], 1)
        self.assertEqual(founder["fills"][0]["held_price"], 0.57)
        self.assertEqual(founder["fills"][0]["fee_usd"], 0.10)  # $0.05 a contract a leg

    def test_a_close_far_under_the_bid_is_refused_before_v4_and_re_priced_to_the_band_by_the_house_on_main(self):
        def probe(ctx):
            memory = ctx.get("memory") or {}
            legs = [{"occ": LOW, "role": "long"}, {"occ": HIGH, "role": "short"}]
            if not memory.get("sent"):
                return {"intents": [{"structure": "debit_vertical", "action": "open", "quantity": 1, "type": "limit", "limit_price": 0.55,
                                     "legs": legs, "reason": "probe open"}], "cancels": [], "memory": {"sent": 1}}
            if ctx["positions"] and not ctx["open_orders"]:  # a stop at half the mark, as the founders' exits price it
                return {"intents": [{"structure": "debit_vertical", "action": "close", "quantity": 1, "type": "limit", "limit_price": 0.25,
                                     "legs": legs, "reason": "probe stop"}], "cancels": [], "memory": memory}
            return {"intents": [], "cancels": [], "memory": memory}

        lines = []
        for m in range(12):  # the same touch every minute, each leg quoted again a second before the minute
            at, quoted = f"2026-09-25T15:{m:02d}:00Z", f"2026-09-25T{14 + (m > 0)}:{(m - 1) % 60:02d}:59Z"
            lines.append(line(at, [row(LOW, 1.00, 1.05, quoted), row(HIGH, 0.50, 0.52, quoted)]))
        self.write(lines)  # the structure: ask 1.05 - 0.50 = 0.55, bid 1.00 - 0.52 = 0.48
        before = fwd.run(self.path, house_bars=None, local_store=None, founders=["options_condor_vrp"], work=self.dir.name,
                         decide_override={"options_condor_vrp": probe}, reprice_from=float("inf"))  # the House of 16:36-18:33Z
        [founder] = before["founders"]
        self.assertEqual((founder["opens"], founder["closes"]), (1, 0))
        self.assertTrue(any("limit price deviates" in reason for reason in founder["refusals"]), founder["refusals"])
        now = self.run_probe(probe)  # the House on main: `_fit_structure_limit` (PR #339)
        [founder] = now["founders"]
        self.assertEqual((founder["opens"], founder["closes"], founder["refusals"]), (1, 1, {}))
        self.assertEqual(founder["limits_repriced_by_the_house"], 1)  # 0.25 raised to 0.44, the band's edge under the bid 0.48
        close = founder["fills"][1]
        self.assertEqual(close["action"], "close")
        self.assertEqual(close["held_price"], 0.48)  # at the bid of a newer snapshot, never the 0.25 asked
        self.assertEqual(now["checks"]["fills_failing_audit"], 0)

    def test_nothing_starts_on_a_snapshot_without_sizes(self):
        calls = []

        def probe(ctx):
            calls.append(ctx["now"])
            return {"intents": [], "cancels": [], "memory": {}}

        self.write([
            line("2026-09-25T15:00:00Z", [row(LOW, 1.00, 1.05, "2026-09-25T14:59:59Z", size=None)]),
            line("2026-09-25T15:01:00Z", [row(LOW, 1.00, 1.05, "2026-09-25T15:00:59Z")]),
        ])
        result = self.run_probe(probe)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("2026-09-25T15:01:00"))  # its start: no quote in it is later
        self.assertEqual(result["checks"]["sized_from"], "2026-09-25T15:01:00.000000Z")


class CalibrationBars(unittest.TestCase):
    """`build_calibration_store`: the day's 15-minute bars from the snapshots' minute bars, only windows seen whole."""

    def test_a_window_is_built_from_the_most_complete_minute_readings_and_only_when_seen_whole(self):
        import league.options_history as history

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "live.jsonl"

            def at(minute: int, bars: dict, last_t: str | None) -> str:
                rows = [{**row(LOW, 1.00, 1.05, f"2026-09-25T15:{minute:02d}:30Z"), "last": 1.02, "last_t": last_t, "mbar": bars}]
                return line(f"2026-09-25T15:{minute:02d}:10Z", rows)

            minute = lambda m, c, v: {"o": c, "h": c + 0.01, "l": c - 0.01, "c": c, "v": v, "t": f"2026-09-25T15:{m:02d}:00Z"}  # noqa: E731
            lines = [at(14, minute(14, 0.90, 3), "2026-09-25T15:14:05Z"),  # before the window 15:15-15:30 (a partial one: dropped)
                     at(15, minute(15, 1.00, 2), "2026-09-25T15:15:05Z"),
                     at(16, minute(15, 1.01, 6), "2026-09-25T15:15:50Z"),  # minute 15 seen again, more complete: kept
                     at(29, minute(29, 1.04, 1), "2026-09-25T15:29:02Z"),
                     at(31, minute(31, 1.10, 1), "2026-09-25T15:31:00Z")]  # the next window, not seen whole: dropped
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            built = fwd.build_calibration_store(path, Path(tmp) / "cal.sqlite", history, local_store=None)
            bars = built["store"].db.execute("SELECT occ, timeframe, t, o, h, l, c, v, n FROM bars ORDER BY t").fetchall()
            # o and l from minute 15 as last seen (1.01, 1.00), h and c from minute 29; v 6 + 1; n the three trades seen
            self.assertEqual(bars, [(LOW, "15Min", "2026-09-25T15:30:00Z", 1.01, 1.05, 1.0, 1.04, 7.0, 3)])
            self.assertEqual(built["store"].db.execute("SELECT count(*) FROM quotes").fetchone()[0], 5)
            built["store"].close()


if __name__ == "__main__":
    unittest.main()
