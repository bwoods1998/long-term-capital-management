"""Release E2.2, READING CTX: the equity generators misread the program contract (league/equity/EQUITY.md said
`ctx.bars[sym]` carries "arrays"; the programs they wrote read it by key or as rows, every decide raised a TypeError and
the version was disqualified), and what was changed is held here, layer by layer:

- WHAT A PROGRAM RECEIVES is E1's (league/equity/ctx.py, program.py): the tables the static rule and the texts are
  written from are held to E1's own definitions, so they cannot drift from the engine;
- THE TEXTS: the contract's "Reading ctx" (a worked program and the common faults), the one sentence and two lines every
  equity generator reads, with no outcome and no figure in them; the worked example is taken OUT OF THE DOCUMENT and run
  on E1's real isolated runner over a synthetic store, where it loads, trades and holds the restart check;
- THE READING RULE (league/swarm/elane_review.py `reading_refusals`, in `elane_train.check_code`): the shapes of the
  disqualified programs are refused before a version is stored or run, each with what to write instead; EVERY shape the
  rule refuses is run on E1's real runner and fails there, and the shapes it must leave alone run clean; a refusal
  spends a write attempt and never a scored version;
- THE DISQUALIFICATION'S BRIEF: a version scored before the rule ran (or whose fault the source does not show) is
  told the line of its own file the first error was raised at and what is wrong there, never the exception's text.

Every family, program and number here is invented; the market is E1's synthetic store."""

from __future__ import annotations

import datetime as dt
import json
import re
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from league.swarm import elane, elane_births, elane_review, elane_train
from league.swarm.elane_review import reading_refusals, reading_text
from league.swarm.elane_train import EquityResearcher, check_code, record_of
from league.tests import elane_e2_fakes as fx

REPO = Path(__file__).resolve().parents[2]
E1 = callable(getattr(elane, "next_try", None)) and callable(getattr(elane, "reviewed", None))
SYMBOLS = ("SPY", "QQQ")
HEAD = '''import math
import numpy as np

NEEDS = {"symbols": ["SPY", "QQQ"], "history": 30, "max_hold_sessions": 5}
PARAMS = {"n": 5, "share": 0.25}
STATE = {}

'''


def prog(body: str) -> str:
    """An invented program: the head above (its body starts at line 8) and `body`, dedented."""
    return HEAD + textwrap.dedent(body).strip("\n") + "\n"


def contract() -> str:
    return (REPO / "league" / "equity" / "EQUITY.md").read_text(encoding="utf-8")


def worked_example() -> str:
    """The worked program of the contract's "Reading ctx", as the document holds it."""
    found = re.search(r"^## Reading ctx: a worked example\n.*?```python\n(.*?)```", contract(), re.S | re.M)
    assert found, "EQUITY.md has no worked example under \"Reading ctx\""
    return found.group(1)


#: THE MISREADINGS. The first five are the two the disqualified programs had (a symbol's bars read BY KEY and walked AS
#: ROWS), in the shapes a program writes them: by key, by key through a name, as rows sliced and looped, as rows in a
#: comprehension, measured and indexed. They are written here from that description; the programs themselves are the
#: House's and are not in this repository. Then every other misreading the rule refuses. Each: (the body, the line of
#: the fault, words its refusal must say).
MISREAD: dict[str, tuple[str, int, tuple[str, ...]]] = {
    "bars by key": ('''
        def decide(ctx):
            c = ctx.bars["SPY"]["close"]
            return [{"buy": "SPY", "share": 0.25}] if c[-1] > c[-2] else []
     ''', 9, ("reads a symbol's bars by key", "TypeError", "write `ctx.bars['SPY'].close`")),
    "bars by key through a name": ('''
        def decide(ctx):
            out = []
            for sym in ctx.symbols:
                bars = ctx.bars[sym]
                closes = np.array(bars["close"], dtype=float)
                if len(closes) > 5 and closes[-1] > np.mean(closes[-5:]):
                    out.append({"buy": sym, "share": 0.25})
            return out
     ''', 12, ("reads a symbol's bars by key", "write `bars.close`")),
    "bars as rows, sliced and looped": ('''
        def decide(ctx):
            out = []
            for sym in ctx.symbols:
                recent = ctx.bars[sym][-5:]
                closes = [bar["close"] for bar in recent]
                if closes and closes[-1] > sum(closes) / len(closes):
                    out.append({"buy": sym, "share": 0.25})
            return out
     ''', 11, ("by position", "there are no rows", "close[-20:]")),
    "bars as rows in a comprehension": ('''
        def decide(ctx):
            closes = [b["close"] for b in ctx.bars["SPY"]]
            return [{"buy": "SPY", "share": 0.25}] if len(closes) > 2 and closes[-1] > closes[-2] else []
     ''', 9, ("is iterated as rows", "read BY ATTRIBUTE")),
    "bars measured and indexed": ('''
        def decide(ctx):
            hist = ctx.bars.get("SPY")
            if hist is None or len(hist) < 3:
                return []
            last = hist[-1]["close"]
            return [{"buy": "SPY", "share": 0.25}] if last > 0 else []
     ''', 10, ("`len(hist)` walks, counts or converts a symbol's bars", "len(close)")),
    "bars through a helper's parameter": ('''
        def sma(bars, n):
            return float(np.mean(bars["close"][-n:]))

        def decide(ctx):
            return [{"buy": s, "share": 0.25} for s in ctx.symbols if ctx.prices[s] > sma(ctx.bars[s], 5)]
     ''', 9, ("reads a symbol's bars by key", "write `bars.close`")),
    "bars from items()": ('''
        def decide(ctx):
            out = []
            for sym, b in ctx.bars.items():
                if b["ret"][-1] < 0:
                    out.append({"buy": sym, "share": 0.25})
            return out
     ''', 11, ("write `b.ret`",)),
    "a field the bars do not have": ('''
        def decide(ctx):
            c = ctx.bars["SPY"].closes
            return []
     ''', 9, ("open, high, low, close, volume and ret only", "AttributeError")),
    "a field ctx does not have": ('''
        def decide(ctx):
            if ctx.portfolio:
                return []
            return [{"buy": "SPY", "share": 0.25}]
     ''', 9, ("ctx has no field 'portfolio'", "never holds a date")),
    "bars unpacked": ('''
        def decide(ctx):
            o, h, l, c, v, r = ctx.bars["SPY"]
            return []
     ''', 9, ("is unpacked",)),
    "bars handed whole to numpy": ('''
        def decide(ctx):
            m = np.mean(ctx.bars["SPY"])
            return []
     ''', 9, ("is handed a symbol's bars whole", "hand it one array")),
    "bars in arithmetic": ('''
        def decide(ctx):
            up = ctx.bars["SPY"] * 2
            return []
     ''', 9, ("is put into arithmetic",)),
    "a lot by attribute": ('''
        def decide(ctx):
            out = [{"sell": lot.id} for lot in ctx.positions if lot.held_sessions >= 2]
            if not ctx.positions:
                out.append({"buy": "SPY", "share": 0.25})
            return out
     ''', 9, ("reads a lot by attribute", "write `lot[\"held_sessions\"]`", "a lot is a dict in the list ctx.positions")),
    "positions by symbol": ('''
        def decide(ctx):
            if ctx.positions:
                lot = ctx.positions["SPY"]
                return [{"sell": lot["id"]}]
            return [{"buy": "SPY", "share": 0.25}]
     ''', 10, ("it is a LIST of lots", "lot[\"symbol\"] == sym")),
    "positions as a dict": ('''
        def decide(ctx):
            if ctx.positions.get("SPY"):
                return []
            return [{"buy": "SPY", "share": 0.25}]
     ''', 9, ("LISTS of lots",)),
    "a key an open lot does not have": ('''
        def decide(ctx):
            out = [{"sell": lot["id"]} for lot in ctx.positions if lot["days_held"] >= 2]
            return out or [{"buy": "SPY", "share": 0.25}]
     ''', 9, ("has no key 'days_held'", "held_sessions")),
    "a key a closed lot does not have": ('''
        def decide(ctx):
            won = sum(1 for c in ctx.closed if c["pnl"] > 0)
            return [] if ctx.positions else [{"buy": "SPY", "share": 0.25, "at": "close"}]
     ''', 9, ("a closed lot (id, symbol, qty, entry, exit, net, held_sessions, reason, tag) has no key 'pnl'",)),
    "events by attribute": ('''
        def decide(ctx):
            if ctx.events.fomc:
                return []
            return [{"buy": "SPY", "share": 0.25}]
     ''', 9, ("ctx.events[\"fomc\"]",)),
    "an event flag that does not exist": ('''
        def decide(ctx):
            if ctx.events["earnings"]:
                return []
            return [{"buy": "SPY", "share": 0.25}]
     ''', 9, ("fomc, cpi, jobs, monthly_opex, quarter_end, half_day only",)),
    "a price subscripted": ('''
        def decide(ctx):
            return [{"buy": "SPY", "share": 0.25}] if ctx.prices["SPY"][-1] > 0 else []
     ''', 9, ("subscripts a float", "ctx.bars[sym].close")),
    "an intent with no kind": ('''
        def decide(ctx):
            return [{"symbol": "SPY", "side": "buy", "share": 0.25}]
     ''', 9, ("has none of \"buy\", \"sell\", \"cancel\"", "EXACTLY one")),
    "an intent with no kind, appended": ('''
        def decide(ctx):
            orders = []
            for sym in ctx.symbols:
                orders.append({"action": "buy", "symbol": sym, "weight": 0.25})
            return orders
     ''', 11, ("has none of",)),
    "an intent with two kinds": ('''
        def decide(ctx):
            return [{"buy": "SPY", "sell": 3, "share": 0.25}]
     ''', 9, ("has 'buy' and 'sell'", "one intent for the sell and another for the buy")),
    "an at that is no fill point": ('''
        def decide(ctx):
            return [{"buy": "SPY", "share": 0.25, "at": "market"}]
     ''', 9, ("\"at\" is 'market'", "\"open\" or \"close\"")),
    "an at that is no fill point, from a helper": ('''
        def order(sym):
            return {"buy": sym, "share": 0.25, "at": "next_open"}

        def decide(ctx):
            return [order(s) for s in ctx.symbols]
     ''', 9, ("\"at\" is 'next_open'",)),
    "a sell by the lot's symbol": ('''
        def decide(ctx):
            out = [{"sell": lot["symbol"], "at": "open"} for lot in ctx.positions]
            return out or [{"buy": "SPY", "share": 0.25}]
     ''', 9, ("a lot is sold whole BY ITS ID", "{\"sell\": lot[\"id\"]}")),
    "a sell by a symbol": ('''
        def decide(ctx):
            if ctx.positions:
                return [{"sell": "SPY"}]
            return [{"buy": "SPY", "share": 0.25}]
     ''', 10, ("BY ITS ID",)),
    "a buy with no size": ('''
        def decide(ctx):
            return [{"buy": "SPY", "qty": 2}]
     ''', 9, ("has neither \"share\" nor \"usd\"",)),
    "a buy sized in percent": ('''
        def decide(ctx):
            return [{"buy": "SPY", "share": 25}]
     ''', 9, ("the buy's \"share\" is `25`", "at most 1")),
    "an empty dict for no order": ('''
        def decide(ctx):
            if ctx.positions:
                return {}
            return {"buy": "SPY", "share": 0.25, "at": "close"} if ctx.weekday == 0 else {}
     ''', 10, ("decide returns an empty dict", "for no order return []")),
}
#: The two misreadings the disqualified programs had, in five shapes (the release's reason).
FIVE = ("bars by key", "bars by key through a name", "bars as rows, sliced and looped", "bars as rows in a comprehension",
        "bars measured and indexed")

#: SHAPES THE RULE MUST LEAVE ALONE: each reads ctx as E1 gives it, in a spelling near a refused one.
SOUND: dict[str, str] = {
    "arrays by attribute, lots by key": '''
        def decide(ctx):
            out = []
            for sym in ctx.symbols:
                close = ctx.bars[sym].close
                lots = [lot for lot in ctx.positions if lot["symbol"] == sym]
                if len(close) < 6 or not np.all(np.isfinite(close[-6:])):
                    continue
                above = close[-1] > float(np.mean(close[-5:]))
                if above and not lots:
                    out.append({"buy": sym, "share": 0.25, "at": "open"})
                elif not above:
                    out += [{"sell": lot["id"], "at": "open"} for lot in lots]
            return out
     ''',
    "names, items, a helper and an intent finished by key": '''
        def window(bars, n):
            c = bars.close
            return c[-n:] if len(c) >= n else None

        def decide(ctx):
            out = []
            held = {}
            for i, lot in enumerate(ctx.positions):
                held[lot["symbol"]] = lot.get("id")
                if lot["held_sessions"] >= 3 or (lot["pnl"] is not None and lot["pnl"] < 0):
                    out.append({"sell": lot["id"]})
            for sym, b in ctx.bars.items():
                w = window(b, 5)
                if w is None or sym in held:
                    continue
                r = getattr(b, "ret")
                if np.isfinite(r[-1]) and r[-1] < 0 and not ctx.events["fomc"] and ctx.caps[sym] > 0:
                    order = {"buy": sym, "usd": 0.5 * ctx.caps[sym]}
                    order["at"] = "close"
                    order["tag"] = "dip"
                    out.append(order)
            for c in ctx.closed:
                STATE[c["symbol"]] = c["net"]
            for why in ctx.rejects:
                STATE["last"] = why[:20]
            return out
     ''',
    "one dict, a list or None returned": '''
        def decide(ctx):
            b = ctx.bars.get("SPY")
            if b is None or len(b.close) < 3:
                return None
            if ctx.positions:
                return [{"sell": p["id"], "at": "close"} for p in ctx.positions if p["at"] == "open" or p["tag"] == "x"]
            return {"buy": "SPY", "share": ctx.params["share"]}
     ''',
    "an intent whose kind is written by a computed key": '''
        def decide(ctx):
            out = []
            for sym in ctx.symbols:
                o = {"share": 0.25}
                side = "buy"
                o[side] = sym
                out.append(o)
            return out[:1]
     ''',
    "dicts of the program's own that are no intents": '''
        def decide(ctx):
            rows = []
            for sym in ctx.symbols:
                c = ctx.bars[sym].close
                if len(c) > 5 and np.isfinite(c[-6]) and c[-6] > 0:
                    rows.append({"sym": sym, "mom": float(c[-1] / c[-6] - 1.0)})
            rows.sort(key=lambda r: r["mom"])
            weights = {"SPY": 0.25, "QQQ": 0.25}
            if ctx.positions:
                return []
            return [{"buy": r["sym"], "share": weights[r["sym"]]} for r in rows[-1:]]
     ''',
    "a name used for two things": '''
        def decide(ctx):
            out = {"SPY": 0.25}
            out = [{"buy": s, "share": w} for s, w in out.items()]
            bars = ctx.bars["SPY"]
            bars = bars.close
            if len(bars) > 2 and bars[-1] > bars[-2] and not ctx.positions:
                return out
            return [{"sell": lot["id"]} for lot in ctx.positions]
     ''',
    "a closure over ctx, sets of symbols and intents made with dict()": '''
        def decide(ctx):
            n, h = int(ctx.params["n"]), 3

            def z(sym):
                r = ctx.bars[sym].ret
                if len(r) < n + 2:
                    return float("nan")
                sd = float(np.nanstd(r[-n - 1:-1]))
                return float(r[-1] / sd) if sd > 0 and np.isfinite(r[-1]) else float("nan")

            exits = [{"sell": p["id"], "at": "open", "tag": "h"} for p in ctx.positions if int(p["held_sessions"]) + 1 >= h]
            holding = {p["symbol"] for p in ctx.positions}
            entries = []
            for sym in ctx.symbols:
                score = z(sym)
                if sym not in holding and math.isfinite(score) and score < 0 and not ctx.events_next.get("fomc", False):
                    entries.append(dict(buy=sym, share=float(ctx.params["share"]), at="open", tag="rev"))
            last = ctx.closed[-1] if ctx.closed else None
            if last is not None and last["reason"] == "house":
                return exits
            return exits + entries
     ''',
    "a walrus, several arrays at once and a lot read with get": '''
        def sma(x, n):
            return float(np.mean(x[-n:])) if len(x) >= n and np.all(np.isfinite(x[-n:])) else None

        def decide(ctx):
            intents = []
            by_symbol = {}
            for pos in ctx.positions:
                by_symbol[pos["symbol"]] = by_symbol.get(pos["symbol"], []) + [pos]
            for sym in ctx.symbols:
                if (b := ctx.bars.get(sym)) is None:
                    continue
                c, h, l, v = b.close, b.high, b.low, b.volume
                fast, slow = sma(c, 3), sma(c, 10)
                if fast is None or slow is None or slow <= 0:
                    continue
                up = fast / slow > 1.0
                lots = by_symbol.get(sym, [])
                if up and not lots:
                    intents.append({"buy": sym, "share": ctx.params["share"]})
                if not up or any(lot["held_sessions"] >= 4 for lot in lots):
                    for lot in lots:
                        intents.append({"sell": lot.get("id"), "at": "open", "tag": lot.get("tag", "") or "exit"})
            return intents[:20]
     ''',
    "a list of candidates rebuilt into intents": '''
        def decide(ctx):
            out = []
            for sym in ctx.symbols:
                out.append({"sym": sym, "score": float(ctx.bars[sym].ret[-1])})
            out = [{"buy": c["sym"], "share": 0.25} for c in out if np.isfinite(c["score"]) and c["score"] < 0]
            return [] if ctx.positions else out
     ''',
}


#: WHAT A PROGRAM GUARDS ITSELF: a misreading inside a `try` that catches it, and a value read both ways behind a check
#: of its type. Both run on E1 as written, so the rule refuses neither.
GUARDED: dict[str, str] = {
    "a read the program catches itself": '''
        def decide(ctx):
            b = ctx.bars["SPY"]
            try:
                c = b["close"]
            except TypeError:
                c = b.close
            if ctx.positions:
                return [{"sell": lot["id"]} for lot in ctx.positions]
            return [{"buy": "SPY", "share": 0.25}] if len(c) > 1 and c[-1] > c[-2] else []
     ''',
    "a kind the program asks the type of": '''
        def decide(ctx):
            out = []
            for lot in ctx.positions:
                lid = lot.id if hasattr(lot, "id") else lot["id"]
                out.append({"sell": lid})
            for sym in ctx.symbols:
                b = ctx.bars[sym]
                c = b["close"] if isinstance(b, dict) else b.close
                if not ctx.positions and len(c) > 1 and c[-1] > c[-2]:
                    out.append({"buy": sym, "share": 0.25})
            return out
     ''',
}


class WhatCtxGives(unittest.TestCase):
    """The rule's tables are E1's own definitions (a field E1 adds or renames fails here, never in a program)."""

    def test_the_tables_are_e1s(self):
        from league.equity import config, ctx, program
        from league.gym import events

        self.assertEqual(elane_review.READ_CTX, ctx.Ctx.__slots__)
        self.assertEqual(elane_review.READ_BAR, ctx.SymbolBars.__slots__)
        lot = ctx.lot_row(lid=1, symbol="SPY", klass="etf", qty=1.0, entry=100.0, mark=101.0, held_sessions=0, at="open")
        shut = ctx.closed_row(lid=1, symbol="SPY", qty=1.0, entry=100.0, exit=101.0, net=1.0, held_sessions=1,
                              reason="program")
        self.assertEqual(elane_review.READ_LOT, tuple(lot))
        self.assertEqual(elane_review.READ_CLOSED, tuple(shut))
        self.assertEqual(elane_review.READ_EVENTS, tuple(events.EVENT_NAMES))
        self.assertEqual(elane_review.INTENT_KINDS, program.KINDS)
        self.assertEqual(elane_review.INTENT_AT, program.AT)
        self.assertEqual(config.MAX_INTENTS, 20)
        # A lot with no price has no mark, value or pnl (what the contract and the TypeError hint say).
        blind = ctx.lot_row(lid=1, symbol="SPY", klass="etf", qty=1.0, entry=100.0, mark=float("nan"), held_sessions=0,
                            at="open")
        self.assertEqual((blind["mark"], blind["value"], blind["pnl"]), (None, None, None))

    def test_a_symbols_bars_are_one_object_read_by_attribute(self):
        import numpy as np

        from league.equity import ctx

        bars = ctx.SymbolBars("SPY", *(np.arange(3.0) for _ in range(6)))
        self.assertIsInstance(bars.close, np.ndarray)
        self.assertEqual(bars.close.dtype, np.float64)
        with self.assertRaises(TypeError):
            bars["close"]  # noqa: B018 - the misreading itself
        with self.assertRaises(TypeError):
            len(bars)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            iter(bars)  # type: ignore[call-overload]
        with self.assertRaises(ValueError):
            bars.close[0] = 1.0  # read-only

    def test_the_houses_words_for_a_malformed_intent_are_the_table(self):
        from league.equity.program import _intent

        rows = ([1, 2], {"symbol": "SPY"}, {"buy": "SPY", "sell": 1, "share": 0.5}, {"cancel": "x"},
                {"buy": "SPY", "share": 0.5, "at": "market"}, {"sell": "SPY"}, {"buy": 7, "share": 0.5}, {"buy": "SPY"},
                {"buy": "SPY", "share": 0.5, "usd": 5.0}, {"buy": "SPY", "share": 25}, {"buy": "SPY", "usd": -1})
        said = {_intent(row)[1] for row in rows}
        self.assertNotIn("", said, "every row above is malformed")
        self.assertEqual(said, set(elane_train.INTENT_FAULTS), "E1's `_intent` says exactly the table's sentences")
        self.assertEqual(_intent({"buy": "SPY", "share": 0.5})[1], "")
        self.assertEqual(_intent({"sell": 17, "at": "open"})[1], "")


class TheTexts(unittest.TestCase):
    def test_the_contract_says_how_ctx_is_read_and_reaches_every_generator_whole(self):
        text = contract()
        flat = " ".join(text.split())
        self.assertIn("## Reading ctx: a worked example", text)
        for words in ("whose six arrays are read BY ATTRIBUTE", "never `ctx.bars[sym][\"close\"]`, never rows",
                      "read-only float64 numpy array", "starts with ONE element", "a LIST of DICTS (`lot[\"id\"]`, never "
                      "`lot.id`", "`ctx.bars[sym][\"close\"]` raises TypeError", "Bars are arrays, not rows",
                      "`ret[0]` is NaN", "A lot is sold by its id", "There is no pandas",
                      "An intent has exactly one of `buy`, `sell`, `cancel`"):
            self.assertIn(words, flat, words)
        self.assertLessEqual(len(text), elane_train.CONTRACT_CHARS, "the generators are handed the whole contract")
        self.assertEqual(elane_train.contract_text(), text)
        self.assertIn(worked_example(), elane_train.contract_text())

    def test_what_the_contract_says_a_program_has_is_what_the_sandbox_gives(self):
        import numpy as np

        from league.gym import runtime, safety

        said = re.search(r"What you have: (.*?)There is no pandas\.", " ".join(contract().split())).group(1)
        names = re.findall(r"`([A-Za-z_.]+)`", said)
        builtins = [n for n in names if "." not in n and n != "math"]
        self.assertGreaterEqual(len(builtins), 15)
        for name in builtins:
            self.assertIn(name, runtime._SAFE_BUILTIN_NAMES, name)
        numpy_names = [n.split(".", 1)[1] for n in names if n.startswith("np.")]
        self.assertGreaterEqual(len(numpy_names), 6)
        for name in numpy_names:
            self.assertTrue(callable(getattr(np, name)), name)
            self.assertNotIn(name, safety.NUMPY_BANNED, name)
        self.assertEqual(safety.ALLOWED_IMPORTS, {"math", "numpy"})
        with self.assertRaises(safety.CodeRefused):
            safety.check_program("import pandas as pd\n" + fx.program())

    def test_the_sentence_and_the_two_lines_reach_the_architect_the_researcher_and_no_figure_rides_them(self):
        said = elane_review.READING_CTX
        self.assertIn("read BY ATTRIBUTE, never by key and never as rows", said)
        self.assertIn("close = ctx.bars[sym].close", said)
        self.assertIn('{"sell": lot["id"], "at": "open"}', said)
        self.assertIn(said, elane_train.RESEARCHER_SYSTEM)
        self.assertLess(elane_train.RESEARCHER_SYSTEM.index(said), elane_train.RESEARCHER_SYSTEM.index("THE PROGRAM CONTRACT"))
        fx.switch_on(self)
        self.assertIn(said, elane_births.lanes_text(fx.settings()))
        # The seal: rules only. No digit at all, no outcome word, no year.
        self.assertIsNone(re.search(r"\d", said), "no figure")
        for word in ("Validation", "holdout", "look", "P&L", "passed", "refuted", "Train"):
            self.assertNotIn(word, said)
        # The two lines are a program's own: they pass the code rules and the reading rule as written.
        lines = [line.split("#")[0].rstrip() for line in said.splitlines() if line.startswith("    ")]
        self.assertEqual(len(lines), 2)
        code = prog("def decide(ctx):\n    sym = \"SPY\"\n" + "\n".join(lines) + "\n    return sells if len(close) else []\n")
        self.assertIsNone(check_code(code, SYMBOLS), code)

    def test_the_fixed_hints_hold_no_figure_of_a_run(self):
        for kind, text in elane_train.DQ_HINTS.items():
            self.assertIn(kind, elane_train.ERROR_CLASSES)
            self.assertIn(f"{kind} in decide", text)
            for word in ("Validation", "holdout", "$", "P&L"):
                self.assertNotIn(word, text)


class TheReadingRule(unittest.TestCase):
    def test_the_five_disqualified_shapes_are_refused_with_what_to_write(self):
        for name in FIVE:
            body, line, words = MISREAD[name]
            why = check_code(prog(body), SYMBOLS)
            self.assertIsNotNone(why, name)
            self.assertTrue(why.startswith("refused before it ran by the equity reading rule"), (name, why))
            self.assertIn(f"line {line}: ", why, name)
            self.assertIn("ctx.bars[sym] is ONE object whose six arrays are read BY ATTRIBUTE", why, name)
            for word in words:
                self.assertIn(word, why, (name, word))

    def test_every_misreading_names_its_line_and_what_to_write(self):
        for name, (body, line, words) in MISREAD.items():
            found = reading_refusals(prog(body))
            self.assertTrue(found, name)
            self.assertTrue(any(row.startswith(f"line {line}: ") for row in found), (name, found))
            text = reading_text(prog(body))
            for word in words:
                self.assertIn(word, text, (name, word))
            self.assertIsNotNone(check_code(prog(body), SYMBOLS), name)

    def test_what_reads_ctx_as_it_is_given_is_left_alone(self):
        for name, body in SOUND.items():
            self.assertEqual(reading_refusals(prog(body)), [], name)
        self.assertEqual(reading_refusals(worked_example()), [])
        self.assertIsNone(check_code(worked_example(), SYMBOLS))

    def test_the_seeds_and_the_tests_own_programs_are_left_alone(self):
        from league.swarm import seeds

        programs = {f"fakes.{name}": value for name, value in vars(fx).items()
                    if isinstance(value, str) and "def decide" in value}
        programs["fakes.program()"] = fx.program()
        for spec in seeds.EQUITY_SEEDS:
            programs[f"seed {spec['id']}"] = seeds.equity_program_for(spec)[0]
        self.assertGreaterEqual(len(programs), 8)
        for name, code in programs.items():
            self.assertEqual(reading_refusals(code), [], name)

    def test_never_on_a_guess(self):
        # A name bound two ways, a parameter handed two kinds, a value through a call the pass does not know, a default
        # that is no bars, a function handed on as a value, text made with %, a lot of either list read by a key one of
        # them has: none is refused.
        quiet = {
            "two bindings": '''
                def decide(ctx):
                    x = ctx.bars["SPY"]
                    if ctx.weekday == 0:
                        x = {"close": [1.0, 2.0]}
                    return [{"buy": "SPY", "share": 0.25}] if x["close"][-1] > 0 else []
             ''',
            "a parameter handed two kinds": '''
                def last(x):
                    return x["close"][-1]

                def decide(ctx):
                    a = last(ctx.bars["SPY"])
                    b = last({"close": [1.0]})
                    return []
             ''',
            "through an unknown call": '''
                def pick(ctx):
                    return ctx.bars["SPY"]

                def decide(ctx):
                    return [] if pick(ctx)["close"][-1] > 0 else []
             ''',
            "a default that is no bars": '''
                def decide(ctx):
                    b = ctx.bars.get("SPY", {"close": [1.0]})
                    return [] if b["close"][-1] > 0 else []
             ''',
            "a helper handed on as a value": '''
                def first(b):
                    return b["close"]

                def decide(ctx):
                    rows = list(map(first, [{"close": 1.0}]))
                    first(ctx.bars["SPY"])
                    return []
             ''',
            "ctx under another meaning": '''
                def helper(ctx):
                    return ctx.anything

                def decide(c):
                    return [] if helper(STATE) else []
             ''',
            "text with percent": '''
                def decide(ctx):
                    STATE["seen"] = "%s" % ctx.bars["SPY"]
                    return []
             ''',
            "a key one kind of lot has": '''
                def decide(ctx):
                    total = 0.0
                    for rows in (ctx.positions, ctx.closed):
                        for lot in rows:
                            total += 1.0
                    for lot in ctx.positions:
                        total += lot["mark"] or 0.0
                    for lot in ctx.closed:
                        total += lot["net"]
                    return []
             ''',
            "a dict changed after it was written": '''
                def decide(ctx):
                    o = {"share": 0.25}
                    o.update(ctx.params.get("extra") or {"buy": "SPY"})
                    return [o]
             ''',
            "a dict built on another": '''
                def decide(ctx):
                    base = {"share": 0.25, "at": "open"}
                    return [{**base, "buy": "SPY"}]
             ''',
            "an at written later": '''
                def decide(ctx):
                    out = [{"buy": "SPY", "share": 0.25, "at": "market"}]
                    for o in out:
                        o["at"] = "close"
                    return out
             ''',
            "a read the program catches itself": '''
                def decide(ctx):
                    b = ctx.bars["SPY"]
                    try:
                        c = b["close"]
                    except TypeError:
                        c = b.close
                    return [{"buy": "SPY", "share": 0.25}] if len(c) > 1 and c[-1] > c[-2] else []
             ''',
            "a name another function rebinds": '''
                def decide(ctx):
                    x = ctx.bars["SPY"]

                    def swap():
                        nonlocal x
                        x = {"close": [1.0, 2.0]}
                    swap()
                    return [{"buy": "SPY", "share": 0.25}] if x["close"][-1] > 0 else []
             ''',
            "a comprehension's own variable": '''
                def decide(ctx):
                    b = ctx.bars["SPY"]
                    rows = [{"close": float(v)} for v in b.close[-3:]]
                    last = [b["close"] for b in rows]
                    return [{"buy": "SPY", "share": 0.25}] if last and last[-1] > 0 else []
             ''',
            "a kind the program asks the type of": '''
                def decide(ctx):
                    out = []
                    for sym in ctx.symbols:
                        b = ctx.bars[sym]
                        c = b["close"] if isinstance(b, dict) else b.close
                        if len(c) > 1 and c[-1] > c[-2]:
                            out.append({"buy": sym, "share": 0.25})
                    for lot in ctx.positions:
                        lid = lot.id if hasattr(lot, "id") else lot["id"]
                        out.append({"sell": lid})
                    return out
             ''',
        }
        for name, body in quiet.items():
            self.assertEqual(reading_refusals(prog(body)), [], name)
        self.assertEqual(reading_refusals("def decide(ctx:\n"), [], "a file that does not parse is the code rules' to refuse")
        self.assertEqual(reading_refusals(None), [])
        # A `try` catches no malformed intent (the House drops it and counts the error after decide returned).
        caught = prog('''
            def decide(ctx):
                try:
                    return [{"buy": "SPY", "share": 0.25, "at": "market"}]
                except Exception:
                    return []
         ''')
        self.assertEqual(len(reading_refusals(caught)), 1)

    def test_the_same_name_holds_what_every_binding_of_it_gives(self):
        # A lot of either list by attribute is refused (both are dicts); a key only the open lot has is not.
        both = prog('''
            def decide(ctx):
                out = []
                for lot in ctx.positions:
                    out.append({"sell": lot["id"]})
                for lot in ctx.closed:
                    STATE["last"] = lot.symbol
                return out
         ''')
        found = reading_refusals(both)
        self.assertEqual(len(found), 1, found)
        self.assertIn("line 13: `lot.symbol` reads a lot by attribute", found[0])

    def test_a_refusal_spends_a_write_attempt_and_never_a_scored_version(self):
        fx.switch_on(self)
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        bad = prog(MISREAD["bars by key"][0])
        good = fx.program()
        answers = [{"text": "", "json": {"program": code, "note": "invented"}, "route": "sail", "model": "pro_asap",
                    "cost_usd": 0.05} for code in (bad, good)]
        router = fx.FakeRouter(lambda call: fx.review_answer("pass", model=call["sail_profile"]) if fx.is_review(call)
                               else answers.pop(0))
        runner = fx.FakeRunner()
        settings = fx.settings(train_budget=4, train_per_round=5)
        researcher = EquityResearcher(store, router, settings, runner=runner, clock=clock)
        fam = fx.e2_family(store, "misreader", symbols=("SPY", "QQQ"))
        step = researcher.step(store.family(fam["id"]))
        self.assertTrue(step["refused"].startswith("refused before it ran by the equity reading rule"), step)
        rec = record_of(store.family(fam["id"]))
        self.assertEqual(rec["versions"], {}, "no scored version is spent (train_budget)")
        self.assertEqual(rec["attempts"], 1, "one write attempt is (train_max_attempts)")
        self.assertIsNone(store.latest_version(fam["id"]), "the program was never stored")
        self.assertEqual(runner.calls, [], "and never run")
        self.assertEqual(len(rec["refused"]), 1)
        # The next brief says why, with the line and what to write, and repeats how ctx is read.
        brief = researcher.brief(store.family(fam["id"]))
        self.assertIn("PROGRAMS REFUSED BEFORE THEY RAN:\n- refused before it ran by the equity reading rule", brief)
        self.assertIn("line 9: `ctx.bars['SPY']['close']` reads a symbol's bars by key", brief)
        self.assertIn(elane_review.READING_CTX, brief)
        self.assertIn("TRAIN BUDGET: 4 of 4 scored versions left", brief)
        # The revision reads ctx as it is given: stored, run, scored.
        step = researcher.step(store.family(fam["id"]))
        self.assertEqual(step.get("version"), 1, step)
        self.assertEqual(sorted(record_of(store.family(fam["id"]))["versions"]), ["1"])
        self.assertTrue(runner.calls)

    def test_a_birth_carrying_a_misread_program_is_born_without_it(self):
        # The equity pass admits the family and leaves its first program to the researcher (`EquityPass.admit` reads
        # `check_code`): the misread program is never version 1, and the researcher's first brief says why.
        from league.swarm.architect import Architect

        fx.switch_on(self)
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        settings = fx.settings(max_per_pass=4)
        rows = [fx.proposal("misread-at-birth", symbols=("SPY", "QQQ"), code=prog(MISREAD["bars as rows in a comprehension"][0]))]
        router = fx.FakeRouter(lambda call: fx.answer(rows))
        out = Architect(store, router, settings, clock=clock).equity_pass()
        self.assertEqual(out.get("born"), ["misread-at-birth"], out)
        self.assertIsNone(store.latest_version("misread-at-birth"), "the misread program was not stored")
        rec = record_of(store.family("misread-at-birth"))
        self.assertTrue(rec["refused"][0]["why"].startswith("the architect's program: refused before it ran by the equity "
                                                           "reading rule"), rec["refused"])
        researcher = EquityResearcher(store, router, settings, runner=fx.FakeRunner(), clock=clock)
        brief = researcher.brief(store.family("misread-at-birth"))
        self.assertIn("is iterated as rows and raises a TypeError", brief)
        self.assertIn(elane_review.READING_CTX, brief)
        self.assertIn("Write version 1: the whole file.", brief)


class TheDisqualificationsBrief(unittest.TestCase):
    def setUp(self):
        fx.switch_on(self)
        self.clock = fx.Clock()
        self.store = fx.new_store(self, self.clock)
        self.results: dict = {}
        self.runner = fx.FakeRunner(lambda code, k: self.results.get(code) or fx.train_result(k=k))
        self.router = fx.FakeRouter()
        self.researcher = EquityResearcher(self.store, self.router, fx.settings(train_budget=4, train_per_round=5),
                                           runner=self.runner, clock=self.clock)

    def test_the_source_line_and_what_is_wrong_there(self):
        by_key = prog(MISREAD["bars by key"][0])
        said = "the program was disqualified on Train by its own errors or timeouts: 25 errors in decide, the first a " \
               "TypeError at line 9"
        told = elane_train.dq_source(by_key, said, 3)
        self.assertTrue(told.startswith("Line 9 of v3 reads `c = ctx.bars[\"SPY\"][\"close\"]`. "), told)
        self.assertIn("reads a symbol's bars by key and raises a TypeError", told)
        self.assertIn("write `ctx.bars['SPY'].close`", told)
        # A fault the source does not show: the class's fixed sentence.
        short = prog('''
            def decide(ctx):
                c = ctx.bars["SPY"].close
                return [{"buy": "SPY", "share": 0.25}] if c[-1] > c[-30] else []
         ''')
        told = elane_train.dq_source(short, "25 errors in decide, the first an IndexError at line 10")
        self.assertEqual(told, "Line 10 reads `return [{\"buy\": \"SPY\", \"share\": 0.25}] if c[-1] > c[-30] else []`. "
                               + elane_train.DQ_HINTS["IndexError"] + ".")
        self.assertIn("check len(close) before close[-20]", told)
        # A class with no sentence: the line alone. No line, a line outside the file, an empty line: nothing.
        self.assertEqual(elane_train.dq_source(short, "25 errors in decide, the first a MemoryError at line 9"),
                         "Line 9 reads `c = ctx.bars[\"SPY\"].close`.")
        for said in ("25 errors in decide", "its decides ran past the run's time budget", None,
                     "25 errors in decide, the first a TypeError at line 400",
                     "25 errors in decide, the first a TypeError at line 7"):
            self.assertEqual(elane_train.dq_source(short, said), "", said)
        self.assertEqual(elane_train.dq_source(None, "the first a TypeError at line 9"), "")
        # A long line is cut; nothing but the file's own text and the House's fixed words is in it.
        long = prog("def decide(ctx):\n    x = ctx.bars[\"SPY\"][\"close\"]" + " + 0" * 200 + "\n    return []\n")
        told = elane_train.dq_source(long, "the first a TypeError at line 9")
        self.assertLess(len(told.split("`")[1]), 161)

    def test_the_exceptions_own_words_never_reach_the_author_and_the_line_does(self):
        # A version stored before the rule ran (its family's brief gets the line), disqualified with a reason that
        # carries the program's own exception text: the text is the program's to choose, the line is its own file.
        by_key = prog(MISREAD["bars by key"][0])
        leak = "25 errors (first: line 9: TypeError: SENTINEL close 412.55 volume 9876543 on the bar)"
        self.results[by_key] = {**fx.train_result(status="disqualified"), "reason": leak}
        fam = fx.e2_family(self.store, "old-version", code=by_key, symbols=SYMBOLS)
        self.researcher.run()
        rec = record_of(self.store.family(fam["id"]))
        self.assertEqual(rec["versions"]["1"]["fails"], ["DQ"])
        self.assertEqual(rec["versions"]["1"]["why"], "the program was disqualified on Train by its own errors or timeouts: "
                                                      "25 errors in decide, the first a TypeError at line 9")
        brief = self.researcher.brief(self.store.family(fam["id"]))
        self.assertIn("v1: the program was disqualified on Train by its own errors or timeouts: 25 errors in decide, the "
                      "first a TypeError at line 9. Line 9 of v1 reads `c = ctx.bars[\"SPY\"][\"close\"]`. "
                      "`ctx.bars['SPY']['close']` reads a symbol's bars by key and raises a TypeError", brief)
        self.assertIn("write `ctx.bars['SPY'].close`.", brief)
        self.assertIn(elane_review.READING_CTX, brief)
        for text in (brief, json.dumps(rec)):
            for word in ("SENTINEL", "412.55", "9876543", "on the bar"):
                self.assertNotIn(word, text)
        # A version that was not disqualified is shown no line, and its family's brief no reminder.
        other = fx.e2_family(self.store, "sound", code=fx.program(share=0.4))
        self.results[fx.program(share=0.4)] = fx.train_result(pnl=-5.0)
        self.researcher.run()
        brief = self.researcher.brief(self.store.family(other["id"]))
        self.assertNotIn("reads `", brief)
        self.assertNotIn(elane_review.READING_CTX, brief)

    def test_the_houses_own_sentence_about_a_malformed_return_is_named_in_fixed_words(self):
        said = elane_train.dq_said
        for fault in elane_train.INTENT_FAULTS:
            self.assertEqual(said(f"25 errors (first: malformed intent: {fault})"),
                             f"25 errors in decide, the first a malformed intent ({fault})")
        # Anything else after the House's prefix, a count the program chose and the type it returned are not repeated.
        self.assertEqual(said("25 errors (first: malformed intent: SENTINEL 412.55)"),
                         "25 errors in decide, the first a malformed intent")
        self.assertEqual(said("25 errors (first: malformed intent: an intent holds a SymbolBars)"),
                         "25 errors in decide, the first a malformed intent")
        many = said("25 errors (first: decide returned 412 intents; only the first 20 count)")
        self.assertEqual(many, "25 errors in decide, the first more intents than one call may return (at most 20; the rest "
                               "are dropped)")
        self.assertNotIn("412", many)
        self.assertEqual(said("25 errors (first: decide returned a set; it returns a list of intents)"),
                         "25 errors in decide, the first a return that is no list of intents (decide returns a list of "
                         "intent dicts, one dict, [] or None)")
        self.assertEqual(said("25 errors (first: decide returned 412.55 was the close; it returns a list of intents)"),
                         "25 errors in decide")
        self.assertEqual(elane_train.house_fault("line 9: TypeError: malformed intent: 'at' is 'open' or 'close'"), "")
        # In the record: its `why`, inside the record's cut.
        fault = "a buy has exactly one of 'share' (of the sleeve's equity) or 'usd'"
        verdict = elane_train.program_fault("DQ", "raw", said=said(f"25 errors (first: malformed intent: {fault})"))
        kept = elane_train.compact(verdict, at="2026-10-11T00:00:00Z")
        self.assertTrue(kept["why"].endswith(f"the first a malformed intent ({fault})"), kept["why"])


@unittest.skipUnless(E1, "E1's equity lanes are not in this tree (the E2 branch's skeleton)")
class OnE1sRunner(unittest.TestCase):
    """E1's real isolated runner (league/equity/runner.py `Isolated`, the program in its decider kind) over E1's
    synthetic store: what the rule refuses really fails there, what it leaves alone really runs, and the contract's
    worked example loads and trades."""

    SPAN = (dt.date(2016, 1, 4), dt.date(2016, 9, 30))
    SPANS = ((dt.date(2016, 1, 4), dt.date(2016, 6, 30)), (dt.date(2022, 1, 3), dt.date(2022, 6, 30)))

    @classmethod
    def setUpClass(cls):
        from league.equity import synth

        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = synth.synthetic_store(Path(cls.tmp.name) / elane.STORE_DIR, symbols=SYMBOLS, end=dt.date(2022, 12, 30),
                                         seed=3, drift=0.08, vol=0.15)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def runner(self):
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider

        return Isolated(InlineDecider(), self.root)

    def run_span(self, code: str, span=None) -> dict:
        first, last = span or self.SPAN
        return self.runner().train(code, {}, name="p", start=first, end=last, k=1.0).result

    def test_every_shape_the_rule_refuses_fails_on_e1s_runner(self):
        kinds = set()
        for name, (body, line, _) in MISREAD.items():
            code = prog(body)
            self.assertTrue(reading_refusals(code), name)
            result = self.run_span(code)
            runtime = result["runtime"]
            self.assertEqual(result["status"], "disqualified", (name, runtime))
            first = runtime["messages"][0]
            self.assertTrue(first.startswith(f"line {line}: ") or first.startswith("malformed intent: "), (name, first))
            kinds.add(first.split(": ")[1] if first.startswith("line ") else "malformed intent")
            # What E2's record says of it: counts, the line and the class (or the House's own sentence), no more.
            said = elane_train.dq_said(result["reason"])
            self.assertTrue(said.startswith("25 errors in decide, the first a"), (name, said))
        self.assertEqual(kinds, {"TypeError", "AttributeError", "KeyError", "malformed intent"})
        for name in FIVE:
            first = self.run_span(prog(MISREAD[name][0]))["runtime"]["messages"][0]
            self.assertIn("TypeError: ", first, name)
            self.assertIn("SymbolBars", first, name)

    def test_what_a_program_guards_itself_runs_clean(self):
        # Why the rule leaves a read inside a `try` and a kind the program asks the type of alone: both run.
        for name, body in GUARDED.items():
            code = prog(body)
            self.assertEqual(reading_refusals(code), [], name)
            result = self.run_span(code)
            self.assertEqual((result["status"], result["runtime"]["errors"]), ("ok", 0), (name, result["runtime"]))
            self.assertGreater(result["summary"]["trades"], 0, name)

    def test_every_shape_the_rule_leaves_alone_runs_clean(self):
        for name, body in SOUND.items():
            code = prog(body)
            self.assertIsNone(check_code(code, SYMBOLS), name)
            result = self.run_span(code)
            self.assertEqual((result["status"], result["runtime"]["errors"]), ("ok", 0), (name, result["runtime"]))
            self.assertGreater(result["summary"]["trades"], 0, name)

    def test_the_contracts_worked_example_loads_and_trades_as_written(self):
        from league.equity.program import load_program

        code = worked_example()
        self.assertIn("close = ctx.bars[sym].close", code)
        self.assertIn('{"sell": lot["id"], "at": "open"}', code)
        self.assertLessEqual(len([line for line in code.splitlines() if line.strip()]), 20, "a short program")
        program = load_program(code, name="worked-example")
        self.assertEqual((program.needs.symbols, program.needs.history, program.needs.max_hold_sessions),
                         (SYMBOLS, 60, 30))
        self.assertIsNone(check_code(code, SYMBOLS), "it passes every static rule the swarm applies to a bred program")
        runner = self.runner()
        runs = [runner.train(code, {}, name="worked", start=first, end=last, k=1.0) for first, last in self.SPANS]
        for run in runs:
            result = run.result
            self.assertEqual(result["status"], "ok")
            self.assertEqual((result["runtime"]["errors"], result["runtime"]["timeouts"]), (0, 0), result["runtime"])
            self.assertGreater(result["summary"]["trades"], 5, "it trades")
            self.assertEqual({t["entry_at"] for t in result["trades"]}, {"open"})
            self.assertEqual({t["reason"] for t in result["trades"]}, {"program"},
                             "every exit is its own sell, by the lot's id: none is left to the House's maximum hold")
        # The first span begins at the store's first session: its first decisions have one, two, three closes behind
        # them, and the example waits (no error) where an unguarded window would raise.
        self.assertEqual(runs[0].bars.first, 0)
        # It keeps nothing in STATE: the Train bar's restart check holds on every session.
        check = elane_train.restart_check(runner.decider, code, {}, name="worked",
                                          streams=[elane_train.state_inputs(run) for run in runs])
        self.assertEqual((check["held"], check["matched"], check["failed"]), (True, check["sessions"], 0), check)

    def test_a_window_indexed_without_its_length_fails_where_the_run_has_no_history(self):
        # What the contract's faults and the IndexError hint say: at the store's first session an array holds ONE
        # element, so an unguarded index raises there (and nowhere in a span with history behind it).
        code = prog('''
            def decide(ctx):
                c = ctx.bars["SPY"].close
                return [{"buy": "SPY", "share": 0.25}] if c[-1] > c[-30] else []
         ''')
        self.assertEqual(reading_refusals(code), [], "nothing the source shows")
        early = self.run_span(code, self.SPANS[0])
        self.assertEqual(early["status"], "disqualified")
        self.assertIn("line 10: IndexError: ", early["runtime"]["messages"][0])
        self.assertIn("with size 1", early["runtime"]["messages"][0])
        late = self.run_span(code, self.SPANS[1])
        self.assertEqual((late["status"], late["runtime"]["errors"]), ("ok", 0))
        told = elane_train.dq_source(code, elane_train.dq_said(early["reason"]), 1)
        self.assertIn("Line 10 of v1 reads `return [{\"buy\": \"SPY\", \"share\": 0.25}] if c[-1] > c[-30] else []`.", told)
        self.assertIn(elane_train.DQ_HINTS["IndexError"], told)
        self.assertNotIn("size 1", told, "the exception's own text is not in it")

    def test_a_disqualified_version_is_briefed_with_its_own_line_on_e1s_runner(self):
        # The whole path on E1's runner: a version stored before the rule (as the first programs on the House were) is
        # run, disqualified by a TypeError at every decide, and its family's next brief names the line and the fix.
        fx.switch_on(self)
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        code = prog(MISREAD["bars as rows, sliced and looped"][0])
        fam = fx.e2_family(store, "rows", code=code, symbols=SYMBOLS)
        researcher = EquityResearcher(store, fx.FakeRouter(), fx.settings(train_budget=4), runner=self.runner(), clock=clock)
        with mock.patch.object(elane_train, "TRAIN_SPANS", self.SPANS), \
                mock.patch.object(elane_train, "TRAIN_YEARS", (2016, 2022)):
            out = researcher.run()
        self.assertEqual(out["steps"][0].get("fails"), ["DQ"], out)
        rec = record_of(store.family(fam["id"]))
        self.assertEqual(rec["versions"]["1"]["why"], "the program was disqualified on Train by its own errors or timeouts: "
                                                      "25 errors in decide, the first a TypeError at line 11")
        brief = researcher.brief(store.family(fam["id"]))
        self.assertIn("the first a TypeError at line 11. Line 11 of v1 reads `recent = ctx.bars[sym][-5:]`. "
                      "`ctx.bars[sym][-5:]` reads a symbol's bars by position and raises a TypeError", brief)
        self.assertIn("close = ctx.bars[sym].close; close[-20:], len(close).", brief)
        self.assertNotIn("SymbolBars", brief, "E1's exception text stays on the House")
        self.assertNotIn("not subscriptable", brief)
        self.assertIn("TRAIN BUDGET: 3 of 4 scored versions left", brief, "the version it cost before the rule ran")


if __name__ == "__main__":
    unittest.main()
