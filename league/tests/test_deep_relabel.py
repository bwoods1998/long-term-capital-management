"""THE RELABEL EQUIVALENCE BATTERY (HISTORY-PLAN.md section 5.3, "Relabel equivalence"; league/deep/relabel.py): a
calendar-blind program's lots, trades, daily record and summary are the same, session for session, whether its bars
sit on their true dates or are written onto other Train-window pseudo-dates; and the relabeled deep store is written
as the plan says (its `all` rebuilt from the raw closes and the events as of the segment's last session, NaN before a
fund's inception, removed after its look, TRAIN-D from the open span alone).

About twenty calendar-blind templates (league/deep/blind.py would pass each): entries and exits at the open and at
the close, splits and dividends held through, a fund that starts late (NaN before), sized by share and by dollars,
the House's maximum hold, STATE memory, and the engine's rejects. The spike (history-1017/plan/spike) promoted.

Every bar here is synthetic (league/equity/synth.py, league/tests/deep_fakes.py): no market data."""

from __future__ import annotations

import datetime as dt
import os
import unittest
from pathlib import Path

import numpy as np

from league.deep import blind, blocks, calendar, config, gate, relabel
from league.equity import store as estore
from league.equity import synth
from league.equity.runner import Isolated
from league.live.decider import InlineDecider
from league.tests import deep_fakes as F

SYMS = ("SPY", "QQQ", "IWM", "TLT")
SECOND = dt.date(2018, 7, 11)  # a Wednesday: another weekday, month phase and event days


def store_a(root: Path) -> list[dt.date]:
    """The true-date store: 700 sessions from 2016-01-04, QQQ split 2:1, quarterly dividends, TLT from session 150."""
    days = [d for d, _ in estore.nyse_sessions(dt.date(2016, 1, 4), dt.date(2019, 12, 31))][:700]
    synth.synthetic_store(root, symbols=SYMS, start=days[0], end=days[-1], seed=17, drift=0.07, vol=0.21,
                          splits={"QQQ": [(days[420], 2.0)]},
                          dividends={s: [(days[i], 0.3 + 0.1 * k) for i in range(40, 700, 63)]
                                     for k, s in enumerate(("SPY", "IWM", "QQQ"))},
                          gaps={"TLT": days[:150]})
    return days


def body(name: str, symbols=SYMS, history: int = 30, hold: int = 20) -> str:
    """The calendar-blind templates (each a whole program)."""
    head = f'NEEDS = {{"symbols": {list(symbols)}, "history": {history}, "max_hold_sessions": {hold}}}\n'
    t = {
        "momentum_oo": F.blind_program(symbols, history=history, hold=hold, entry_at="open", exit_at="open"),
        "momentum_oc": F.blind_program(symbols, history=history, hold=hold, entry_at="open", exit_at="close"),
        "momentum_co": F.blind_program(symbols, history=history, hold=hold, entry_at="close", exit_at="open"),
        "momentum_cc": F.blind_program(symbols, history=history, hold=hold, entry_at="close", exit_at="close"),
        "momentum_gate": F.blind_program(symbols, history=history, hold=hold, gate=0.02, look=15),
        "reversal": head + '''PARAMS = {"drop": -0.02}


def decide(ctx):
    out = [{"sell": p["id"], "at": "open"} for p in ctx.positions if p["held_sessions"] >= 3]
    for s in ctx.symbols:
        r = ctx.bars[s].ret
        if len(r) > 1 and r[-1] == r[-1] and r[-1] < ctx.params["drop"] and not ctx.positions:
            out.append({"buy": s, "share": 0.3, "at": "open"})
            break
    return out
''',
        "breakout_close": head + '''PARAMS = {"n": 20}


def decide(ctx):
    out = [{"sell": p["id"], "at": "close"} for p in ctx.positions if p["held_sessions"] >= 5]
    for s in ctx.symbols:
        h = ctx.bars[s].high
        c = ctx.bars[s].close
        n = ctx.params["n"]
        if len(c) > n and c[-1] == c[-1] and c[-1] >= max(h[-n - 1:-1]) and len(ctx.positions) < 2:
            out.append({"buy": s, "share": 0.25, "at": "close"})
    return out
''',
        "low_vol": head + '''import numpy as np

PARAMS = {"n": 25}


def decide(ctx):
    out = [{"sell": p["id"], "at": "open"} for p in ctx.positions if p["held_sessions"] >= 10]
    if ctx.positions:
        return out
    best, low = None, 1.0
    for s in ctx.symbols:
        r = np.asarray(ctx.bars[s].ret[-ctx.params["n"]:])
        if r.size == ctx.params["n"] and np.isfinite(r).all():
            v = float(np.std(r))
            if v < low:
                best, low = s, v
    if best is not None:
        out.append({"buy": best, "share": 0.5, "at": "open"})
    return out
''',
        "volume": head + '''PARAMS = {"k": 1.3}


def decide(ctx):
    out = [{"sell": p["id"], "at": "open"} for p in ctx.positions if p["held_sessions"] >= 2]
    for s in ctx.symbols:
        v = ctx.bars[s].volume
        if len(v) > 10 and v[-1] == v[-1] and v[-1] > ctx.params["k"] * (sum(v[-11:-1]) / 10.0) and not ctx.positions:
            out.append({"buy": s, "share": 0.2, "at": "open"})
            break
    return out
''',
        "usd_sized": head + '''PARAMS = {"usd": 180.0}


def decide(ctx):
    out = [{"sell": p["id"], "at": "open"} for p in ctx.positions if p["pnl"] is not None and abs(p["pnl"]) > 4]
    for s in ctx.symbols:
        c = ctx.bars[s].close
        if len(c) > 5 and c[-1] == c[-1] and c[-1] > c[-5] and ctx.caps.get(s, 0) > ctx.params["usd"]:
            out.append({"buy": s, "usd": ctx.params["usd"], "at": "open"})
    return out
''',
        "max_hold": body_hold(symbols, history),
        "state_counter": head + '''PARAMS = {"every": 7}
STATE = {"n": 0}


def decide(ctx):
    STATE["n"] += 1
    out = [{"sell": p["id"], "at": "close"} for p in ctx.positions if p["held_sessions"] >= 4]
    if STATE["n"] % ctx.params["every"] == 0:
        s = ctx.symbols[STATE["n"] % len(ctx.symbols)]
        if ctx.prices[s] == ctx.prices[s]:
            out.append({"buy": s, "share": 0.3, "at": "open"})
    return out
''',
        "rejects": head + '''PARAMS = {}


def decide(ctx):
    out = [{"sell": 999, "at": "open"}]
    if ctx.rejects and not ctx.positions:
        s = ctx.symbols[len(ctx.rejects) % len(ctx.symbols)]
        if ctx.prices[s] == ctx.prices[s]:
            out.append({"buy": s, "share": 0.2, "at": "close"})
    out += [{"sell": p["id"], "at": "open"} for p in ctx.positions if p["held_sessions"] >= 6]
    return out
''',
        "cash_aware": head + '''PARAMS = {}


def decide(ctx):
    out = [{"sell": p["id"], "at": "open"} for p in ctx.positions if p["held_sessions"] >= 8]
    if ctx.cash > 0.6 * ctx.equity:
        for s in ctx.symbols:
            c = ctx.bars[s].close
            if len(c) > 3 and c[-1] == c[-1] and c[-1] < c[-3]:
                out.append({"buy": s, "share": 0.15, "at": "close"})
    return out
''',
        "closed_reader": head + '''PARAMS = {}
STATE = {"wins": 0}


def decide(ctx):
    STATE["wins"] += sum(1 for c in ctx.closed if c["net"] > 0)
    out = [{"sell": p["id"], "at": "open"} for p in ctx.positions if p["held_sessions"] >= 3 + STATE["wins"] % 4]
    if not ctx.positions:
        s = ctx.symbols[STATE["wins"] % len(ctx.symbols)]
        if ctx.prices[s] == ctx.prices[s]:
            out.append({"buy": s, "share": 0.35, "at": "open"})
    return out
''',
        "late_fund": body_late(symbols, history),
        "split_holder": head.replace(f'"symbols": {list(symbols)}', '"symbols": ["QQQ"]') + '''PARAMS = {}


def decide(ctx):
    if not ctx.positions:
        return [{"buy": "QQQ", "share": 0.5, "at": "open"}]
    return [{"sell": p["id"], "at": "close"} for p in ctx.positions if p["held_sessions"] >= 50]
''',
        "dividend_holder": head.replace(f'"symbols": {list(symbols)}', '"symbols": ["SPY", "IWM"]') + '''PARAMS = {}


def decide(ctx):
    out = []
    held = {p["symbol"] for p in ctx.positions}
    for s in ("SPY", "IWM"):
        if s not in held:
            out.append({"buy": s, "share": 0.45, "at": "close"})
    return out + [{"sell": p["id"], "at": "open"} for p in ctx.positions if p["held_sessions"] >= 30]
''',
        "history_zero": F.blind_program(symbols, history=0, hold=hold, look=1),
        "long_history": F.blind_program(symbols, history=250, hold=hold, look=60),
    }
    return t[name]


def body_hold(symbols, history) -> str:
    return (f'NEEDS = {{"symbols": {list(symbols)}, "history": {history}, "max_hold_sessions": 3}}\n' + '''PARAMS = {}


def decide(ctx):
    if ctx.positions:
        return []
    for s in ctx.symbols:
        c = ctx.bars[s].close
        if len(c) > 2 and c[-1] == c[-1] and c[-1] > c[-2]:
            return [{"buy": s, "share": 0.4, "at": "open"}]
    return []
''')


def body_late(symbols, history) -> str:
    return (f'NEEDS = {{"symbols": ["TLT", "SPY"], "history": {history}, "max_hold_sessions": 15}}\n' + '''PARAMS = {}


def decide(ctx):
    out = [{"sell": p["id"], "at": "open"} for p in ctx.positions if p["held_sessions"] >= 4]
    t = ctx.bars["TLT"].close
    if not ctx.positions and len(t) > 2 and t[-1] == t[-1] and t[-2] == t[-2]:
        out.append({"buy": "TLT" if t[-1] > t[-2] else "SPY", "share": 0.4, "at": "close"})
    return out
''')


TEMPLATES = ("momentum_oo", "momentum_oc", "momentum_co", "momentum_cc", "momentum_gate", "reversal", "breakout_close",
             "low_vol", "volume", "usd_sized", "max_hold", "state_counter", "rejects", "cash_aware", "closed_reader",
             "late_fund", "split_holder", "dividend_holder", "history_zero", "long_history")


class Battery(unittest.TestCase):
    """True-date against relabeled, for every template."""

    @classmethod
    def setUpClass(cls):
        import tempfile

        cls._tmp = tempfile.TemporaryDirectory(prefix="deep-relabel-")
        cls.root = Path(cls._tmp.name)
        cls.days_a = store_a(cls.root / "A")
        cls.b = relabel.copy_onto(cls.root / "A", cls.root / "B", SECOND)
        cls.decider = InlineDecider()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_on(self, root: Path, days, code: str, lead: int):
        return Isolated(self.decider, root).train(code, {}, name="t", start=days[lead], end=days[-1], k=1.0).result

    def test_the_relabeled_store_holds_the_same_arrays_on_other_days(self):
        a, b = estore.EquityStore(self.root / "A"), estore.EquityStore(self.root / "B")
        self.assertEqual(len(a.sessions()), len(b.sessions()))
        self.assertEqual(b.sessions()[0], SECOND)
        self.assertNotEqual([d.weekday() for d in a.sessions()[:5]], [d.weekday() for d in b.sessions()[:5]])
        ba, bb = a.bars(list(SYMS), "train", history=0), b.bars(list(SYMS), "train", history=0)
        for s in SYMS:
            np.testing.assert_array_equal(ba.raw[s], bb.raw[s])
            np.testing.assert_array_equal(ba.adj[s], bb.adj[s])
        self.assertTrue(np.isnan(ba.raw["TLT"][:150, 3]).all(), "TLT is NaN before its inception")

    def test_about_twenty_calendar_blind_templates_give_identical_runs(self):
        traded = fills = actions = 0
        at_points = set()
        for name in TEMPLATES:
            code = body(name)
            with self.subTest(template=name):
                self.assertEqual(blind.scan(code), [], "every template is calendar-blind by the scan")
                lead = 260 if name == "long_history" else 40
                ra = self.run_on(self.root / "A", self.days_a, code, lead)
                rb = self.run_on(self.root / "B", self.b.pseudo_days, code, lead)
                self.assertEqual(ra["status"], "ok")
                self.assertEqual(blind.comparable(ra, self.days_a), blind.comparable(rb, self.b.pseudo_days))
                self.assertEqual(ra["summary"], rb["summary"])
                self.assertEqual(len(ra["lots"]), len(rb["lots"]))
                traded += bool(ra["lots"])
                fills += len(ra["lots"])
                actions += len(ra.get("actions") or [])
                at_points |= {(lot["entry_at"], lot.get("exit_at")) for lot in ra["lots"]}
        self.assertEqual(len(TEMPLATES), 20)
        self.assertGreaterEqual(traded, 19, "the templates trade")
        self.assertGreater(actions, 0, "splits or dividends were held through")
        for point in (("open", "open"), ("open", "close"), ("close", "open"), ("close", "close")):
            self.assertIn(point, at_points, f"both fill points, entry and exit: {point}")

    def test_a_calendar_reader_does_not(self):
        code = body("momentum_oo").replace("    held = {p", "    if ctx.weekday == 2:\n        return out\n    held = {p")
        ra = self.run_on(self.root / "A", self.days_a, code, 40)
        rb = self.run_on(self.root / "B", self.b.pseudo_days, code, 40)
        self.assertNotEqual(blind.comparable(ra, self.days_a)["lots"], blind.comparable(rb, self.b.pseudo_days)["lots"])


class AllIsRebuiltFromTheEvents(unittest.TestCase):
    def test_the_rebuild_is_synths_own_adjustment(self):
        """blocks.adjusted (the deep store's `all`, from raw closes and the events) equals league/equity/synth.py's
        adjustment=all on the same synthetic path, to its 4 decimals."""
        root = F.tmpdir(self)
        days = store_a(root / "A")
        bars = estore.EquityStore(root / "A").bars(["QQQ", "SPY"], "train", history=0)
        for sym, splits, divs in (("QQQ", {days[420]: 2.0}, {days[i]: 0.5 for i in range(40, 700, 63)}),
                                  ("SPY", {}, {days[i]: 0.3 for i in range(40, 700, 63)})):
            raw = bars.raw[sym]
            arrays = {"open": raw[:, 0], "high": raw[:, 1], "low": raw[:, 2], "close": raw[:, 3], "volume": raw[:, 4],
                      "div": np.array([divs.get(d, 0.0) for d in days]),
                      "split": np.array([splits.get(d, 1.0) for d in days])}
            got = blocks.adjusted(arrays)
            for k, name in enumerate(("open", "high", "low", "close")):
                self.assertLessEqual(float(np.max(np.abs(got[name] - bars.adj[sym][:, k]))), 1.0001e-4, (sym, name))

    def test_later_events_do_not_reach_a_segments_prices(self):
        """`all` as of the segment's own last session: two deep stores that differ only by a distribution AFTER
        segment B (in 2009) give byte-identical B stores, and a store whose distribution falls INSIDE B does not."""
        root = F.tmpdir(self)
        days = calendar.deep_sessions()

        def deep(path: Path, extra: dt.date | None) -> blocks.DeepStore:
            divs = [(days[i], 0.3) for i in range(50, len(days), 63)] + ([(extra, 4.0)] if extra else [])
            series = F.gbm("SPY", days, seed=8, dividends=divs)
            spans = {}
            for span, (lo, hi) in config.SPANS.items():
                keep = [i for i, d in enumerate(days) if lo <= d <= hi]
                spans[span] = {"SPY": blocks.block_bytes([days[i] for i in keep],
                                                         {c: np.asarray(series[c])[keep] for c in blocks.COLUMNS})}
            blocks.write_store(path, spans, audit={"ok": True}, source="synthetic", written_at="x")
            return blocks.DeepStore(path, gate=gate.mint_deep_gate_capability(path, "s3-look"))

        late = next(d for d in days if d >= dt.date(2009, 6, 1))
        inside = next(d for d in days if d >= dt.date(2007, 6, 1))
        shas = {}
        for name, extra in (("none", None), ("late", late), ("inside", inside)):
            store = deep(root / name, extra)
            built = relabel.write_segment(root / f"{name}-B", store, "B", ("SPY",))
            shas[name] = estore.EquityStore(built.root).manifest()["symbols"]["SPY"]["sha256"]
        self.assertEqual(shas["none"], shas["late"], "a later distribution reaches no price of the segment")
        self.assertNotEqual(shas["none"], shas["inside"])


class TheDeepSegments(unittest.TestCase):
    def setUp(self):
        self.root = F.tmpdir(self)
        self.deep = F.deep_store(self.root / "equity-deep", ("SPY", "QQQ", "TLT", "GLD"),
                                 inception={"TLT": dt.date(2002, 7, 30), "GLD": dt.date(2004, 11, 18)})
        self.cap = gate.mint_deep_gate_capability(self.deep, "s3-look")

    def test_each_segment_is_written_session_for_session_onto_the_train_window(self):
        sealed = blocks.DeepStore(self.deep, gate=self.cap)
        for name, (back, scored) in config.SEGMENT_SESSIONS.items():
            with relabel.relabeled(sealed, name, ("SPY", "QQQ", "TLT", "GLD"), parent=self.root) as rl:
                self.assertEqual((rl.lookback, len(rl.scored_true)), (back, scored))
                self.assertEqual(list(rl.pseudo_days), [d for d, _ in calendar.pseudo(back + scored)])
                self.assertEqual(rl.pseudo_days[0], dt.date(2016, 1, 4))
                es = estore.EquityStore(rl.root)
                self.assertNotIn("GATE", os.listdir(rl.root), "a relabeled store opens no sealed window of its own")
                self.assertEqual(es.manifest()["source"], relabel.SOURCE)
                rows = es.manifest()["symbols"]
                if name == "A":  # NaN before inception: no bar before a fund's first day
                    self.assertEqual(rows["GLD"]["first"], rl.pseudo_of(dt.date(2004, 11, 18)).isoformat())
                    self.assertEqual(rows["TLT"]["first"], rl.pseudo_of(dt.date(2002, 7, 30)).isoformat())
                    self.assertEqual(rows["GLD"]["rows"], len([d for d in rl.true_days if d >= dt.date(2004, 11, 18)]))
                self.assertEqual(rows["SPY"]["rows"], back + scored)

    def test_a_segment_runs_alike_on_two_pseudo_labelings(self):
        sealed = blocks.DeepStore(self.deep, gate=self.cap)
        code = F.blind_program(("SPY", "QQQ"), history=40)
        decider = InlineDecider()
        for name in ("B", "traind"):
            with relabel.relabeled(sealed, name, ("SPY", "QQQ"), parent=self.root) as rl:
                # another labeling that still fits the Train window (TRAIN-D's 1,762 sessions from a Wednesday)
                other = relabel.copy_onto(rl.root, self.root / f"other-{name}", dt.date(2016, 3, 9))
                start = rl.lookback
                ra = Isolated(decider, rl.root).train(code, {}, name="t", start=rl.pseudo_days[start],
                                                      end=rl.pseudo_days[-1], k=2.0).result
                rb = Isolated(decider, other.root).train(code, {}, name="t", start=other.pseudo_days[start],
                                                         end=other.pseudo_days[-1], k=2.0).result
                self.assertTrue(ra["lots"])
                self.assertEqual(blind.comparable(ra, rl.pseudo_days), blind.comparable(rb, other.pseudo_days))

    def test_the_temporary_store_is_removed_after_the_look_and_after_a_failure(self):
        sealed = blocks.DeepStore(self.deep, gate=self.cap)
        looks = blocks.looks_dir(self.deep)
        with relabel.relabeled(sealed, "A", ("SPY",), parent=self.root) as rl:
            held = rl.root.parent
            self.assertTrue(held.is_dir())
            self.assertEqual(held.parent, looks, "a DVAL segment is written inside the sealed tree, whatever parent says")
            self.assertTrue(held.name.startswith(f"deep-A-p{os.getpid()}-"), "its directory names its process")
            self.assertEqual(os.stat(held).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(looks).st_mode & 0o777, 0o700)
        self.assertFalse(held.exists())
        with self.assertRaises(RuntimeError):
            with relabel.relabeled(sealed, "B", ("SPY",), parent=self.root) as rl:
                held = rl.root.parent
                raise RuntimeError("a look that fails")
        self.assertFalse(held.exists())
        self.assertEqual(os.listdir(looks), [])
        self.assertEqual([p for p in os.listdir(self.root) if p.startswith("deep-")], [])
        with relabel.relabeled(blocks.DeepStore(self.deep), "traind", ("SPY",), parent=self.root) as rl:
            self.assertEqual(rl.root.parent.parent, self.root, "an open segment goes where it is asked")

    def test_traind_never_opens_the_sealed_span_and_dval_needs_the_gate(self):
        open_store = blocks.DeepStore(self.deep)
        real = blocks.DeepStore.block

        def tripwire(store, span, symbol):
            if span in config.SEALED_SPANS:
                raise AssertionError("TRAIN-D opened the sealed span")
            return real(store, span, symbol)

        from unittest import mock

        with mock.patch.object(blocks.DeepStore, "block", tripwire):
            with relabel.relabeled(open_store, "traind", ("SPY", "QQQ"), parent=self.root) as rl:
                self.assertEqual(len(rl.true_days), 1762)
        for name in config.DVAL_SEGMENTS:
            with self.assertRaises(blocks.DeepRefused):
                with relabel.relabeled(open_store, name, ("SPY",), parent=self.root):
                    pass
        self.assertEqual(config.SEGMENT_SPANS["traind"], ("traind",))


KILLED_CHILD = """
import os, sys, time
from pathlib import Path
from league.deep import blocks, gate, relabel
deep = Path(sys.argv[1])
cap = gate.mint_deep_gate_capability(deep, "s3-look")
with relabel.relabeled(blocks.DeepStore(deep, gate=cap), "A", ("SPY", "QQQ")) as rl:
    Path(sys.argv[2]).write_text(str(rl.root))
    time.sleep(120)
"""


class AKilledLook(unittest.TestCase):
    """THE SEAL AFTER A KILL (both reviews of Oct 17): a look's process killed inside `relabeled` (the ops runner's wall
    SIGKILL, a CPU or memory limit, a box restart) runs no `finally`, and left a plain equity store of DVAL bars on
    pseudo-dates that read with no capability. It is swept: before the next look's store is made, and at the start
    of every deep_report, equity_deep and contamination-probe run."""

    def setUp(self):
        self.root = F.tmpdir(self)
        self.deep = F.deep_store(self.root / "equity-deep", ("SPY", "QQQ"))

    def kill_a_child_mid_look(self) -> Path:
        import signal
        import subprocess
        import sys
        import time

        ready = self.root / "ready"
        ready.unlink(missing_ok=True)
        repo = Path(__file__).resolve().parents[2]
        env = {**os.environ, "PYTHONPATH": str(repo) + os.pathsep + os.environ.get("PYTHONPATH", "")}
        child = subprocess.Popen([sys.executable, "-c", KILLED_CHILD, str(self.deep), str(ready)], cwd=str(repo), env=env)
        try:
            for _ in range(600):
                if ready.is_file() and ready.read_text():
                    break
                if child.poll() is not None:
                    self.fail(f"the child ended ({child.returncode}) before its look began")
                time.sleep(0.1)
            else:
                self.fail("the child's look did not begin")
            child.send_signal(signal.SIGKILL)
            child.wait(timeout=30)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=30)
        left = Path(ready.read_text())
        self.assertTrue(left.is_dir(), "the kill left the relabeled store behind")
        self.assertEqual(left.parent.parent, blocks.looks_dir(self.deep), "inside the sealed tree")
        bars = estore.EquityStore(left).bars(["SPY"], "train", history=0)
        self.assertGreater(int(np.isfinite(bars.raw["SPY"][:, 3]).sum()), 1000, "readable with no capability")
        return left.parent

    def test_the_next_look_sweeps_it_before_its_own_store_is_made(self):
        left = self.kill_a_child_mid_look()
        mine = blocks.looks_dir(self.deep) / f"deep-B-p{os.getpid()}-live"
        mine.mkdir()
        sealed = blocks.DeepStore(self.deep, gate=gate.mint_deep_gate_capability(self.deep, "s3-look"))
        with relabel.relabeled(sealed, "B", ("SPY",)):
            self.assertFalse(left.exists(), "swept before the next look's store was made")
            self.assertTrue(mine.exists(), "a live process's store is left alone")
        mine.rmdir()

    def test_every_deep_job_sweeps_it_first(self):
        import json
        from unittest import mock

        from league.ops import contam_probe, deep_report, equity_deep
        from league.ops.context import Context

        (self.root / "swarm.json").write_text(json.dumps({"elane": {"deep": {"mode": "off"}, "contam": {"mode": "off"}}}))
        for name, job in (("deep_report", deep_report.report_run), ("equity_deep", equity_deep.run),
                          ("contam_probe", contam_probe.probe)):
            with self.subTest(name):
                left = self.kill_a_child_mid_look()
                ctx = Context(name, root=self.root, due_at=0.0, clock=lambda: 0.0, config={}, settings_value={})
                with mock.patch("league.ops.equity_deep.complete", return_value=False):
                    out = job(ctx)
                self.assertEqual(out["status"], "skipped", "the switch is off: the sweep comes first anyway")
                self.assertFalse(left.exists(), f"{name} swept the killed look's store")
        self.assertEqual(os.listdir(blocks.looks_dir(self.deep)), [])

    def test_an_old_store_is_swept_whatever_its_name_and_the_sweep_touches_nothing_else(self):
        looks = blocks.looks_dir(self.deep, make=True)
        old = looks / f"deep-A-p{os.getpid()}-old"
        old.mkdir()
        os.utime(old, (0, 0))
        nameless = looks / "deep-A-legacy"
        nameless.mkdir()
        legacy = self.deep / "deep-B-abc123"   # where the first R1 build wrote them (parent = the deep store)
        legacy.mkdir()
        other = looks / "keep-me"
        other.mkdir()
        self.assertEqual(blocks.sweep_store(self.deep), 3)
        self.assertEqual(sorted(os.listdir(looks)), ["keep-me"])
        self.assertEqual(sorted(p for p in os.listdir(self.deep) if p.startswith("deep-")), [])
        self.assertTrue((self.deep / config.SEALED_DIR / "dval").is_dir(), "the store itself is untouched")
        self.assertEqual(blocks.sweep(self.root / "nowhere"), 0)
        foreign = self.root / "deep-test-someone-elses"   # a caller's parent: what names no process is not ours
        foreign.mkdir()
        os.utime(foreign, (0, 0))
        dead = self.root / "deep-traind-p999999999-x"
        dead.mkdir()
        self.assertEqual(blocks.sweep(self.root), 1)
        self.assertTrue(foreign.exists())
        self.assertFalse(dead.exists())


if __name__ == "__main__":
    unittest.main()
