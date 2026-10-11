"""Release E2, THE EQUITY REVIEW (league/swarm/elane_review.py): the level rule refuses a program that holds a raw price
or volume level against a constant or a PARAMS value and leaves scale-free programs alone (the captain's three seeds
among them); it refuses RUN-START DEPENDENCE (the sleeve's dollars of the run held against a constant, a PARAMS value
or the run's anchor) and leaves sizing by the sleeve alone; a paid failure binds only when grounded; the audit's reader is another model; the record is the one E1's
look reads (league/swarm/elane.py `reviewed`). Every program here is invented."""

from __future__ import annotations

import unittest

from league.swarm import elane_review
from league.swarm.elane_review import grounded, holds, level_refusals, model_of, record

LEAKS = {
    "a band of absolute levels from PARAMS": '''
NEEDS = {"symbols": ["SPY"], "history": 2}
PARAMS = {"lo": 1234.5, "hi": 1357.9}
def decide(ctx):
    px = ctx.prices["SPY"]
    if ctx.params["lo"] < px < ctx.params["hi"]:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "a literal level on the bars": '''
def decide(ctx):
    if ctx.bars["SPY"].close[-1] > 1111:
        return [{"buy": "SPY", "share": 0.5}]
''',
    "a log level": '''
import numpy as np
def decide(ctx):
    c = ctx.bars["SPY"].close
    if np.log(c[-1]) > 7.7:
        return []
''',
    "a share volume level": '''
import numpy as np
def decide(ctx):
    if np.mean(ctx.bars["SPY"].volume[-20:]) > 1234567:
        return []
''',
    "a level through a helper": '''
def level(ctx):
    return ctx.prices["QQQ"]
def decide(ctx):
    if level(ctx) >= 2222:
        return []
''',
    "a level bucket": '''
def decide(ctx):
    px = ctx.prices["SPY"]
    if px % 10 < 1:
        return []
''',
    "a clip at a module constant": '''
LEVEL = 3333
def decide(ctx):
    px = ctx.prices["SPY"]
    if max(px, LEVEL) == px:
        return []
''',
    "a dollar gap on a lot": '''
def decide(ctx):
    out = []
    for lot in ctx.positions:
        if lot["mark"] - lot["entry"] > 5:
            out.append({"sell": lot["id"]})
    return out
''',
    "a table of levels": '''
LEVELS = {"SPY": 4444}
def decide(ctx):
    closes = {s: ctx.bars[s].close for s in ctx.symbols}
    if closes["SPY"][-1] > LEVELS["SPY"]:
        return []
''',
    "a level offset by a constant": '''
def decide(ctx):
    if ctx.bars["SPY"].high[-1] - 5555 > 0:
        return []
''',
    "a level rounded to a grid": '''
def decide(ctx):
    if ctx.bars["SPY"].close.round(-1)[-1] > 0:
        return []
''',
}

#: The integration review's seal-4: the direct, natural shapes the rule let through (each returned no refusal).
HEAD = '''import math
import numpy as np
NEEDS = {"symbols": ["SPY", "QQQ"], "history": 252, "max_hold_sessions": 5}
PARAMS = {"x": 400.0}
'''
MISSED = {
    "the bars iterated by items()": '''
def decide(ctx):
    out = []
    for s, b in ctx.bars.items():
        if b.close[-1] > 400:
            out.append({"buy": s, "share": 0.2})
    return out
''',
    "the bars iterated by values()": '''
def decide(ctx):
    return [{"buy": "SPY", "share": 0.2} for b in ctx.bars.values() if b.close[-1] > PARAMS["x"]]
''',
    "the prices iterated by items()": '''
def decide(ctx):
    return [{"buy": s, "share": 0.2} for s, px in ctx.prices.items() if px > 400]
''',
    "a helper handed the level": '''
def sma(xs, n):
    return float(np.mean(xs[-n:]))
def decide(ctx):
    if sma(ctx.bars["SPY"].close, 200) > 400:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "a helper handed the bars": '''
def last(b):
    return b.close[-1]
def decide(ctx):
    if last(ctx.bars["SPY"]) > PARAMS["x"]:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "a helper that holds its argument against its other argument": '''
def above(x, k):
    return x > k
def decide(ctx):
    if above(ctx.prices["SPY"], 400):
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "a lot's entry by get": '''
def decide(ctx):
    return [{"sell": p["id"]} for p in ctx.positions if p.get("entry") > 400]
''',
    "a lot's mark through enumerate": '''
def decide(ctx):
    return [{"sell": p["id"]} for i, p in enumerate(ctx.positions) if p["mark"] > 400]
''',
    "numpy's greater": '''
def decide(ctx):
    if np.greater(ctx.prices["SPY"], 400.0):
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "numpy's subtract": '''
def decide(ctx):
    if np.subtract(ctx.prices["SPY"], 400.0) > 0:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "numpy's mod": '''
def decide(ctx):
    if np.mod(ctx.prices["SPY"], 10) < 1:
        return []
    return [{"buy": "SPY", "share": 0.5}]
''',
    "numpy's floor_divide": '''
def decide(ctx):
    k = np.floor_divide(ctx.prices["SPY"], 100)
    return [{"buy": "SPY", "share": 0.5}] if k else []
''',
    "numpy's digitize": '''
def decide(ctx):
    k = int(np.digitize(ctx.prices["SPY"], [250.0, 330.0, 420.0]))
    return [{"buy": "SPY", "share": 0.5}] if k == 2 else []
''',
    "numpy's searchsorted": '''
def decide(ctx):
    k = int(np.searchsorted(np.array([250.0, 330.0, 420.0]), ctx.prices["SPY"]))
    return [{"buy": "SPY", "share": 0.5}] if k == 2 else []
''',
    "a constant written as text": '''
def decide(ctx):
    if ctx.prices["SPY"] > float("400"):
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "a constant plus zero": '''
def decide(ctx):
    if ctx.prices["SPY"] > 400 + 0:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "a PARAMS value plus zero": '''
def decide(ctx):
    if ctx.prices["SPY"] > PARAMS["x"] + 0.0:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "a constant written as arithmetic": '''
def decide(ctx):
    if ctx.prices["SPY"] > 2 * 200:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "the ratio of two different symbols' prices": '''
def decide(ctx):
    r = ctx.prices["QQQ"] / ctx.prices["SPY"]
    if r > 0.85:
        return [{"buy": "QQQ", "share": 0.5}]
    return []
''',
    "the log ratio of two different symbols' closes": '''
def decide(ctx):
    r = np.log(ctx.bars["QQQ"].close[-1]) - np.log(ctx.bars["SPY"].close[-1])
    if r > -0.16:
        return [{"buy": "QQQ", "share": 0.5}]
    return []
''',
    "the bars reached by getattr": '''
def decide(ctx):
    b = getattr(ctx, "bars")["SPY"]
    if getattr(b, "close")[-1] > 400:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    # The same class, found while the fix was read again: a level put into a container of the program's own and read
    # back, `zip` taken apart in a loop, and a helper written as a lambda.
    "a dict of the program's own filled in a loop": '''
def decide(ctx):
    closes = {}
    for s in ctx.symbols:
        closes[s] = ctx.bars[s].close[-1]
    if closes["SPY"] > 400:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "a dict of the program's own read by get": '''
def decide(ctx):
    closes = {}
    for s in ctx.symbols:
        closes[s] = ctx.bars[s].close[-1]
    if closes.get("SPY", 0.0) > PARAMS["x"]:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "a list the levels are appended to": '''
def decide(ctx):
    xs = []
    for s in ctx.symbols:
        xs.append(ctx.prices[s])
    if xs[0] > 400:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "a level put in STATE and read back": '''
STATE = {}
def decide(ctx):
    STATE["c"] = ctx.prices["SPY"]
    if STATE["c"] > 400:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "a level put in STATE by setdefault and read by get": '''
STATE = {}
def decide(ctx):
    STATE.setdefault("first", ctx.prices["SPY"])
    if STATE.get("first", 0.0) > 400:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "the two symbols' closes of the program's own dict, one over the other": '''
def decide(ctx):
    closes = {s: ctx.bars[s].close[-1] for s in ctx.symbols}
    if closes["QQQ"] / closes["SPY"] > 0.85:
        return [{"buy": "QQQ", "share": 0.5}]
    return []
''',
    "zip taken apart in a loop": '''
def decide(ctx):
    out = []
    for s, px in zip(ctx.symbols, [ctx.prices[s] for s in ctx.symbols]):
        if px > 400:
            out.append({"buy": s, "share": 0.2})
    return out
''',
    "a helper written as a lambda": '''
def decide(ctx):
    last = lambda b: b.close[-1]
    if last(ctx.bars["SPY"]) > 400:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
}

#: The integration review's seal-1: a program that reads its own profit since the run began. The first is the
#: reviewer's program (a profit lock), word for word; the rest are the same dependence written other ways.
RUN_ANCHORED = {
    "the profit lock (equity over budget against a PARAMS value)": '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 4}
PARAMS = {"share": 0.5, "lock": 0.03, "small": 0.02}


def decide(ctx):
    if ctx.positions:
        return []
    ahead = ctx.equity / ctx.budget - 1.0
    share = ctx.params["small"] if ahead >= ctx.params["lock"] else ctx.params["share"]
    return [{"buy": "SPY", "share": share, "at": "open"}]
''',
    "equity against a constant": '''
def decide(ctx):
    if ctx.equity > 1030.0:
        return []
    return [{"buy": "SPY", "share": 0.5}]
''',
    "equity against the budget": '''
def decide(ctx):
    share = 0.02 if ctx.equity > ctx.budget else 0.5
    return [{"buy": "SPY", "share": share}]
''',
    "equity against a multiple of the budget": '''
def decide(ctx):
    if ctx.equity >= 1.03 * ctx.budget:
        return []
    return [{"buy": "SPY", "share": 0.5}]
''',
    "the profit in dollars": '''
def decide(ctx):
    won = ctx.equity - ctx.budget
    return [] if won > 0 else [{"buy": "SPY", "share": 0.5}]
''',
    "a size that shrinks as the run gets ahead": '''
def decide(ctx):
    return [{"buy": "SPY", "share": 0.5 * (ctx.budget / ctx.equity) ** 20}]
''',
    "cash against a constant": '''
def decide(ctx):
    if ctx.cash > 515:
        return []
    return [{"buy": "SPY", "share": 0.5}]
''',
    "the cap room against equity": '''
def decide(ctx):
    if 2 * ctx.caps["SPY"] < ctx.equity:
        return []
    return [{"buy": "SPY", "share": 0.5}]
''',
    "the cap room against a constant": '''
def decide(ctx):
    room = ctx.caps.get("SPY", 0.0)
    return [{"buy": "SPY", "usd": room}] if room > 100 else []
''',
    "a lot's dollars against a PARAMS value": '''
PARAMS = {"take": 15.0}
def decide(ctx):
    return [{"sell": lot["id"]} for lot in ctx.positions if lot["pnl"] > PARAMS["take"]]
''',
    "a lot's value against a constant, through a helper": '''
def big(lot):
    return lot["value"] > 600
def decide(ctx):
    return [{"sell": lot["id"]} for lot in ctx.positions if big(lot)]
''',
    "the day's realized dollars against a constant": '''
def decide(ctx):
    if sum(row["net"] for row in ctx.closed) > 10:
        return []
    return [{"buy": "SPY", "share": 0.5}]
''',
    "a buy clipped at a constant of dollars": '''
def decide(ctx):
    return [{"buy": "SPY", "usd": min(ctx.cash, 500.0)}]
''',
    "equity in buckets": '''
def decide(ctx):
    step = ctx.equity // 50
    return [{"buy": "SPY", "share": 0.5}] if step % 2 else []
''',
    "a price against the sleeve": '''
def decide(ctx):
    if ctx.prices["SPY"] < ctx.cash:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    "the sleeve over a price against a constant": '''
def decide(ctx):
    if ctx.equity / ctx.prices["SPY"] > 2.5:
        return [{"buy": "SPY", "share": 0.5}]
    return []
''',
    # The profit lock written so the rule's first version let it through (each returned no refusal): the reciprocal,
    # the log, a product with the anchor's reciprocal, a dict of the program's own, divmod.
    "a constant over equity against a PARAMS value": '''
PARAMS = {"inv": 0.97}
def decide(ctx):
    share = 0.02 if 1000.0 / ctx.equity < PARAMS["inv"] else 0.5
    return [{"buy": "SPY", "share": share}]
''',
    "equity times the budget's reciprocal": '''
PARAMS = {"lock": 0.03}
def decide(ctx):
    ahead = ctx.equity * (1 / ctx.budget) - 1
    return [{"buy": "SPY", "share": 0.02 if ahead >= PARAMS["lock"] else 0.5}]
''',
    "the log of equity against a constant": '''
import math
def decide(ctx):
    if math.log(ctx.equity) > 6.94:
        return []
    return [{"buy": "SPY", "share": 0.5}]
''',
    "the log profit": '''
import math
PARAMS = {"lock": 0.03}
def decide(ctx):
    ahead = math.log(ctx.equity) - math.log(ctx.budget)
    return [{"buy": "SPY", "share": 0.02 if ahead >= PARAMS["lock"] else 0.5}]
''',
    "equity kept in a dict of the program's own": '''
def decide(ctx):
    seen = {}
    seen["e"] = ctx.equity
    if seen["e"] > 1030.0:
        return []
    return [{"buy": "SPY", "share": 0.5}]
''',
    "equity through divmod": '''
def decide(ctx):
    steps, rest = divmod(ctx.equity, 10)
    return [] if steps > 102 else [{"buy": "SPY", "share": 0.5}]
''',
}

#: What stays allowed of the run's dollars: sizing proportional to them, a sign or zero check, and the position's own
#: state among the sleeve's dollars now.
SLEEVE_SIZED = '''import math
import numpy as np

NEEDS = {"symbols": ["SPY", "QQQ"], "history": 63, "max_hold_sessions": 10}
PARAMS = {"share": 0.5, "take": 0.04, "weight": 0.4}


def strength(c, n):
    return c[-1] / c[-1 - n] - 1.0


def decide(ctx):
    out = []
    held = 0.0
    for lot in ctx.positions:
        held += lot["value"]
        if lot["pnl"] < 0 and lot["held_sessions"] >= 3:
            out.append({"sell": lot["id"], "at": "open"})
        elif lot["mark"] / lot["entry"] - 1.0 > ctx.params["take"] or lot["pnl"] / lot["value"] > ctx.params["take"]:
            out.append({"sell": lot["id"], "at": "open"})
        elif lot["value"] / ctx.equity > ctx.params["weight"]:
            out.append({"sell": lot["id"], "at": "close"})
    lost = [row for row in ctx.closed if row["net"] < 0]
    if lost or ctx.cash <= 0 or ctx.cash / ctx.equity < 0.5 or held > 0.6 * ctx.equity:
        return out
    ranked = sorted(ctx.symbols, key=lambda s: strength(ctx.bars[s].close, 20), reverse=True)
    for s in ranked[:1]:
        if ctx.caps[s] <= 0 or ctx.caps.get(s, 0.0) == 0:
            continue
        c = ctx.bars[s].close
        if strength(c, 20) > 0 and c[-1] > float(np.mean(c[-50:])):
            usd = min(ctx.cash, ctx.caps[s], ctx.params["share"] * ctx.equity)
            out.append({"buy": s, "usd": round(usd, 2), "at": "close"})
            out.append({"buy": s, "usd": 0.25 * ctx.budget})
    return out
'''

SCALE_FREE = '''import math
import numpy as np

NEEDS = {"symbols": ["SPY", "TLT"], "history": 252, "max_hold_sessions": 20}
PARAMS = {"n": 200, "k": 2.0, "stop": 0.05, "vmax": 0.02, "theta": 0.01}


def sma(a, n):
    return float(np.mean(a[-n:]))


def decide(ctx):
    out = []
    best = -1e9
    peak = 0.0
    for s in ctx.symbols:
        c = ctx.bars[s].close
        h = ctx.bars[s].high
        lo = ctx.bars[s].low
        if len(c) < ctx.params["n"] + 1 or np.isnan(c[-1]):
            continue
        ma = np.mean(c[-ctx.params["n"]:])
        z = (c[-1] - np.mean(c[-20:])) / (np.std(c[-20:]) + 1e-12)
        vol = np.std(np.diff(np.log(c[-21:])))
        atr = np.mean(h[-14:] - lo[-14:])
        best = max(best, c[-1] / ma)
        peak = max(peak, np.max(h[-252:]))
        if c[-1] > ma * 1.01 and vol < ctx.params["vmax"] and z > -ctx.params["k"] and c[-1] - c[-2] < 2 * atr:
            out.append({"buy": s, "share": 0.25, "at": "close"})
        if c[-1] / peak - 1 < -0.1 and c[-1] > sma(c, 50) and np.log(c[-1]) - np.log(ma) > ctx.params["theta"]:
            pass
        if ctx.bars[s].volume[-1] > 1.5 * np.mean(ctx.bars[s].volume[-20:]):
            pass
        if c[-1] / c[-2] - 1.0 <= -ctx.params["theta"]:
            pass
    for lot in ctx.positions:
        if lot["mark"] < lot["entry"] * (1 - ctx.params["stop"]) or lot["mark"] / lot["entry"] - 1 > 0.1:
            out.append({"sell": lot["id"]})
    rets = {s: ctx.bars[s].close[-1] / ctx.bars[s].close[-63] - 1 for s in ctx.symbols}
    top = sorted(rets, key=lambda s: rets[s], reverse=True)[:2]
    px = ctx.prices.get("SPY", float("nan"))
    if px != px or px <= 0 or not top:
        return out
    return out
'''

#: The captain's seeds' shape (league/swarm/seeds.py EQUITY_OVERNIGHT and EQUITY_REVERSAL, E1): never refused.
SEED_SHAPES = ('''import math
NEEDS = {"symbols": ["QQQ"], "history": 2, "max_hold_sessions": 2}
PARAMS = {"share": 0.5}
def decide(ctx):
    share = float(ctx.params["share"])
    intents = []
    for lot in ctx.positions:
        if lot["symbol"] == "QQQ":
            intents.append({"sell": lot["id"], "at": "open", "tag": "overnight-exit"})
    close = ctx.bars["QQQ"].close
    if len(close) < 2:
        return intents
    last, prior = float(close[-1]), float(close[-2])
    if not (math.isfinite(last) and math.isfinite(prior)) or last <= 0:
        return intents
    if last < prior:
        intents.append({"buy": "QQQ", "share": share, "at": "close", "tag": "overnight-entry"})
    return intents
''', '''import math
NEEDS = {"symbols": ["SPY", "QQQ", "IWM", "DIA"], "history": 2, "max_hold_sessions": 20}
PARAMS = {"theta": 0.02, "h": 8, "share": 0.25}
def decide(ctx):
    theta = float(ctx.params["theta"])
    h = int(ctx.params["h"])
    share = float(ctx.params["share"])
    intents = []
    held = {}
    for lot in ctx.positions:
        if int(lot["held_sessions"]) >= h:
            intents.append({"sell": lot["id"], "at": "open", "tag": "reversal-exit"})
        else:
            held[lot["symbol"]] = True
    for symbol in ctx.symbols:
        if held.get(symbol):
            continue
        close = ctx.bars[symbol].close
        if len(close) < 2:
            continue
        last, prior = float(close[-1]), float(close[-2])
        if not (math.isfinite(last) and math.isfinite(prior)) or prior <= 0 or last <= 0:
            continue
        if last / prior - 1.0 <= -theta:
            intents.append({"buy": symbol, "share": share, "at": "open", "tag": "reversal-entry"})
    return intents
''')


class TheLevelRule(unittest.TestCase):
    def test_every_level_held_against_a_constant_or_params_is_refused(self):
        for name, code in LEAKS.items():
            with self.subTest(name):
                found = level_refusals(code)
                self.assertTrue(found, name)
                self.assertTrue(all(f.startswith("line ") for f in found))
        self.assertIn("equity level rule", elane_review.level_text(LEAKS["a band of absolute levels from PARAMS"]))

    def test_scale_free_programs_and_the_seeds_pass(self):
        self.assertEqual(level_refusals(SCALE_FREE), [])
        for code in SEED_SHAPES:
            self.assertEqual(level_refusals(code), [])
        self.assertIsNone(elane_review.level_text(SCALE_FREE))

    def test_a_file_that_does_not_parse_is_left_to_the_code_rules(self):
        self.assertEqual(level_refusals("def decide(ctx:"), [])

    def test_a_placeholder_that_a_loop_fills_is_not_the_number_it_starts_as(self):
        # A body that may run again is read twice and refusals are kept on the second reading alone. Kept on the first,
        # each of these scale-free programs was refused for a level it never holds against a constant: the name was
        # read as the placeholder it starts as (None, zero, a sentinel) before the loop gave it a price.
        for name, body in {
            "the prior close carried through a loop": '''
def decide(ctx):
    prev, out = None, []
    for px in ctx.bars["SPY"].close[-5:]:
        if prev is not None and px / prev - 1 > 0.01:
            out.append({"buy": "SPY", "share": 0.1})
        prev = px
    return out
''',
            "a reference set at the end of the loop's body": '''
def decide(ctx):
    ref, out = 0.0, []
    for s in ctx.symbols:
        c = ctx.bars[s].close
        if ref and c[-1] / ref - 1 > 0.01:
            out.append({"buy": s, "share": 0.1})
        ref = c[-2]
    return out
''',
            "a running low kept by hand from a sentinel": '''
def decide(ctx):
    c = ctx.bars["SPY"].close
    lo = 1e9
    for x in c[-20:]:
        if x < lo:
            lo = x
    return [{"buy": "SPY", "share": 0.2}] if c[-1] / lo - 1 < 0.01 else []
''',
            "a while loop over the same": '''
def decide(ctx):
    c = ctx.bars["SPY"].close
    i, last, ups = 1, None, 0
    while i <= 5:
        if last is not None and c[-i] / last - 1 < 0:
            ups += 1
        last = c[-i]
        i += 1
    return [{"buy": "SPY", "share": 0.2}] if ups >= 3 else []
''',
        }.items():
            with self.subTest(name):
                self.assertEqual(level_refusals(HEAD + body), [])
        # A level held against a constant inside such a loop, or in a helper called from one, is refused as before.
        for name, body in {
            "inside the loop": '''
def decide(ctx):
    prev, out = None, []
    for px in ctx.bars["SPY"].close[-5:]:
        if prev is not None and px > 400:
            out.append({"buy": "SPY", "share": 0.1})
        prev = px
    return out
''',
            "in a helper called from the loop": '''
def above(x, k):
    return x > k
def decide(ctx):
    out = []
    for s in ctx.symbols:
        if above(ctx.prices[s], PARAMS["x"]):
            out.append({"buy": s, "share": 0.1})
    return out
''',
        }.items():
            with self.subTest(name):
                self.assertTrue(level_refusals(HEAD + body), name)

    def test_containers_of_the_programs_own_keep_what_each_key_holds(self):
        # What a program puts into a container of its own is read back as what it is, key by key: a counter beside a
        # price stays a counter, a dict of returns stays scale-free, a trailing high is a level held only against the
        # lot's own mark, and a row that mixes a symbol, a return and a price is not followed (the paid review reads it).
        own = HEAD + '''
STATE = {"n": 0, "px": None}
def decide(ctx):
    out = []
    info = {"px": ctx.prices["SPY"], "n": 20}
    STATE["n"] = STATE.get("n", 0) + 1
    prev = STATE.get("px")
    STATE["px"] = ctx.prices["SPY"]
    if info["n"] > 3 and STATE["n"] > 5 and prev is not None and STATE["px"] / prev - 1.0 > 0.01:
        out.append({"buy": "SPY", "share": 0.2})
    rets, rows, peak = {}, [], STATE.setdefault("peak", {})
    for s in ctx.symbols:
        c = ctx.bars[s].close
        rets[s] = c[-1] / c[-21] - 1.0
        rows.append((rets[s], s, c[-1]))
    rows.sort(reverse=True)
    mom, top, px = rows[0]
    if rets[top] > 0.02 and mom > PARAMS["x"] / 1e4:
        out.append({"buy": top, "share": 0.2})
    for lot in ctx.positions:
        peak[lot["id"]] = max(peak.get(lot["id"], lot["mark"]), lot["mark"])
        if lot["mark"] / peak[lot["id"]] - 1.0 < -0.05:
            out.append({"sell": lot["id"]})
    held = {lot["symbol"]: lot for lot in ctx.positions}
    mine = []
    for lot in ctx.positions:
        mine.append(lot)
    for s, w in zip(ctx.symbols, [0.5, 0.5]):
        if s in held and held[s]["mark"] / held[s]["entry"] - 1.0 > 0.05 and w > 0.25:
            out.append({"sell": held[s]["id"]})
    weight = lambda lot: lot["value"] / ctx.equity
    out.extend({"sell": lot["id"]} for lot in mine if weight(lot) > 0.6 or lot["pnl"] < 0)
    return out
'''
        self.assertEqual(level_refusals(own), [])
        # And the program's own list of lots is still lots: a lot's dollars against a constant are refused through it.
        through = own.replace('weight(lot) > 0.6 or lot["pnl"] < 0', 'lot["pnl"] > 15')
        self.assertNotEqual(through, own)
        self.assertTrue(level_refusals(through))

    def test_the_natural_shapes_the_rule_missed_are_refused(self):
        # The integration review's seal-4: each of these returned no refusal, so only the two paid readers stood
        # between such a program and its lineage's one Validation try.
        for name, body in MISSED.items():
            with self.subTest(name):
                found = level_refusals(HEAD + body)
                self.assertTrue(found, name)
                self.assertTrue(all(f.startswith("line ") for f in found))
        cross = level_refusals(HEAD + MISSED["the ratio of two different symbols' prices"])
        self.assertIn("two different symbols", cross[0])

    def test_one_symbols_own_ratio_and_a_rank_in_its_own_history_still_pass(self):
        own = HEAD + '''
def last(b):
    return b.close[-1]
def sma(xs, n):
    return float(np.mean(xs[-n:]))
def decide(ctx):
    out = []
    for s, b in ctx.bars.items():
        c = b.close
        rank = int(np.searchsorted(np.sort(c[-252:]), c[-1]))
        if last(b) > sma(c, 200) and c[-1] / c[-21] - 1 > 0.02 + 0 and rank > 200 and np.greater(c[-1], c[-2]):
            out.append({"buy": s, "share": 0.2})
    a, b = ctx.bars["QQQ"].close, ctx.bars["SPY"].close
    spread = a[-1] / a[-21] - b[-1] / b[-21]
    ratio = a[-63:] / b[-63:]
    if spread > 0.01 and ratio[-1] > np.mean(ratio) and np.subtract(a[-1], a[-2]) > 0:
        out.append({"buy": "QQQ", "share": 0.2})
    for p in ctx.positions:
        if p.get("mark") < p.get("entry") * 0.95 or p.get("held_sessions") >= 5:
            out.append({"sell": p["id"]})
    return out
'''
        self.assertEqual(level_refusals(own), [])


class RunStartDependence(unittest.TestCase):
    """The integration review's seal-1: a bred program could read its own profit since the run began and size on it,
    which lifted a zero-edge program's pass rate at the share screen above its pinned cap (every judged window starts
    flat; the screen's floor never sees a fresh start)."""

    def test_the_run_s_dollars_held_against_a_constant_or_the_anchor_are_refused(self):
        for name, code in RUN_ANCHORED.items():
            with self.subTest(name):
                found = level_refusals(code)
                self.assertTrue(found, name)
                self.assertTrue(all(f.startswith("line ") for f in found))
        lock = RUN_ANCHORED["the profit lock (equity over budget against a PARAMS value)"]
        why = elane_review.level_text(lock)
        self.assertIn("line 8", why)
        self.assertIn("the run's own profit since it began", why)
        self.assertIn("every judged run starts flat", why)

    def test_the_profit_lock_is_refused_before_it_is_stored_or_run(self):
        from league.swarm import elane_train

        lock = RUN_ANCHORED["the profit lock (equity over budget against a PARAMS value)"]
        why = elane_train.check_code(lock, ["SPY"])
        self.assertIsNotNone(why, "it passed every static check before: the Gym's code rules have nothing against it")
        self.assertIn("equity level rule", why)
        base = lock.replace("    ahead = ctx.equity / ctx.budget - 1.0\n", "").replace(
            'ctx.params["small"] if ahead >= ctx.params["lock"] else ctx.params["share"]', 'ctx.params["share"]')
        self.assertNotIn("ctx.equity", base)
        self.assertIsNone(elane_train.check_code(base, ["SPY"]), "the same program without the rule is admitted")

    def test_sizing_by_the_sleeve_and_the_positions_own_state_pass(self):
        self.assertEqual(level_refusals(SLEEVE_SIZED), [])

    def test_a_dict_of_the_programs_own_is_not_a_lot(self):
        own = '''
def decide(ctx):
    best = {"value": 0.0, "pnl": 2}
    table = {"net": 3}
    if best["value"] > 0.5 or best["pnl"] > 1 or table["net"] > 2:
        return []
    return [{"buy": "SPY", "share": 0.5}]
'''
        self.assertEqual(level_refusals(own), [])

    def test_the_rubric_and_the_facts_name_it(self):
        self.assertIn("RUN-START DEPENDENCE", elane_review.REVIEW)
        self.assertIn("run", elane_review.FACTS)
        self.assertIn("(one of: levels, calendar, context, fills, run)", " ".join(elane_review.REVIEW.split()))
        code = RUN_ANCHORED["the profit lock (equity over budget against a PARAMS value)"]
        finding = {"code_excerpt": "ahead = ctx.equity / ctx.budget - 1.0", "contract_reference": "run",
                   "counterexample": "three percent ahead of a fresh start the program trades a token size; mid-run it "
                                     "would not"}
        answer = {"json": {"verdict": "fail", "reasons": ["a profit lock"], "findings": [finding]}, "text": ""}
        self.assertEqual(grounded(answer, code)["verdict"], "fail", "a reader's failure on it binds")


class TheMemoryRule(unittest.TestCase):
    """The integration review's seal-5: a program could keep memory in an object that hangs off numpy, which survives
    the restart check's fresh load and is shared by every program and run in the swarm's one decider child."""

    HEAD = 'import math\nimport numpy as np\nNEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}\nPARAMS = {}\n\n'
    #: The reviewer's two programs: one writes the key, another program reads it in a later run of the same child.
    WRITER = HEAD + 'def decide(ctx):\n    np.typecodes.setdefault("anchor", 123.25)\n    return []\n'
    READER = HEAD + ('def decide(ctx):\n    if np.typecodes.get("anchor") == 123.25:\n'
                     '        return [{"buy": "SPY", "share": 0.5}]\n    return []\n')
    OTHERS = {
        "a subscript store": 'def decide(ctx):\n    np.typecodes["anchor"] = ctx.prices["SPY"]\n    return []\n',
        "an alias": 'def decide(ctx):\n    t = np.typecodes\n    t.update(anchor=1)\n    return []\n',
        "an import by name": 'from numpy import typecodes\ndef decide(ctx):\n    typecodes.setdefault("a", 1)\n    return []\n',
        "a literal getattr": 'def decide(ctx):\n    getattr(np, "typecodes").setdefault("a", 1)\n    return []\n',
        "the module handed on": 'def put(m):\n    return m\ndef decide(ctx):\n    put(np)\n    return []\n',
        "the module aliased": 'def decide(ctx):\n    n = np\n    return []\n',
        "a table of the module's": 'def decide(ctx):\n    k = len(np.sctypeDict)\n    return []\n',
        "an object handed to a helper": ('def put(d, v):\n    d["anchor"] = v\ndef decide(ctx):\n'
                                         '    put(np.typecodes, 1.0)\n    return []\n'),
    }

    def test_the_writer_and_the_reader_are_both_refused_before_they_are_stored_or_run(self):
        from league.gym.safety import check_program
        from league.swarm import elane_train

        for name, code in (("the writer", self.WRITER), ("the reader", self.READER)):
            check_program(code)  # the Gym's own code rules have nothing against either
            why = elane_train.check_code(code, ["SPY"])
            self.assertIsNotNone(why, name)
            self.assertIn("equity memory rule", why)
            self.assertIn("numpy.typecodes", why)
            self.assertIn("line 7", why)

    def test_every_way_to_an_object_of_a_module_is_refused(self):
        for name, body in self.OTHERS.items():
            with self.subTest(name):
                found = elane_review.memory_refusals(self.HEAD + body)
                self.assertTrue(found, name)
                self.assertTrue(all(f.startswith("line ") for f in found))

    def test_calls_constants_types_and_known_functions_pass(self):
        own = self.HEAD + '''from numpy import mean, nan
STATE = {}
def decide(ctx):
    c = np.asarray(ctx.bars["SPY"].close, dtype=np.float64)
    peak = np.maximum.accumulate(c)
    worst = float(np.min(c / peak - 1.0)) if len(c) else nan
    size = math.sqrt(2.0) / math.pi * float(np.linalg.norm(np.diff(np.log(c)))) if len(c) > 1 else np.nan
    order = sorted(range(len(c)), key=np.abs)
    STATE["seen"] = int(np.add.reduce(np.isfinite(c)))
    with np.errstate(divide="ignore"):
        ok = isinstance(c, np.ndarray) and math.isfinite(worst) and mean(c) > 0 and size == size and order is not None
    return [{"buy": "SPY", "share": 0.5}] if ok and worst > -0.1 and c[-1] is not np.newaxis else []
'''
        self.assertEqual(elane_review.memory_refusals(own), [])
        self.assertEqual(level_refusals(own), [])
        for code in (SCALE_FREE, SLEEVE_SIZED, *SEED_SHAPES):
            self.assertEqual(elane_review.memory_refusals(code), [])
        self.assertIsNone(elane_review.memory_text(SCALE_FREE))
        self.assertEqual(elane_review.memory_refusals("def decide(ctx:"), [])


class ThePaidReview(unittest.TestCase):
    CODE = 'NEEDS = {"symbols": ["SPY"]}\nSTATE = {}\ndef decide(ctx):\n    STATE["n"] = STATE.get("n", 0) + 1\n    return []\n'

    def answer(self, verdict, findings):
        data = {"verdict": verdict, "reasons": ["an invented reason"], "findings": findings}
        return {"json": data, "text": "", "model": "k3_balanced", "route": "sail"}

    def test_a_failure_binds_only_when_grounded(self):
        good = {"code_excerpt": 'STATE["n"] = STATE.get("n", 0) + 1', "contract_reference": "calendar",
                "counterexample": "the count reaches the session index of a known year and the rule switches there"}
        self.assertEqual(grounded(self.answer("fail", [good]), self.CODE)["verdict"], "fail")
        for bad in ({**good, "code_excerpt": "not in the file"}, {**good, "contract_reference": "risk"},
                    {**good, "counterexample": "short"}):
            self.assertEqual(grounded(self.answer("fail", [bad]), self.CODE)["verdict"], "unclear")
        self.assertEqual(grounded(self.answer("fail", []), self.CODE)["verdict"], "unclear")
        self.assertEqual(grounded(self.answer("pass", []), self.CODE)["verdict"], "pass")
        self.assertEqual(grounded({"text": "no json here"}, self.CODE)["verdict"], "unclear")

    def test_two_windows_of_one_sail_model_are_one_reader(self):
        self.assertEqual(model_of("sail:pro_asap"), model_of("sail:pro_balanced"))
        self.assertNotEqual(model_of("sail:pro_balanced"), model_of("sail:k3_balanced"))
        self.assertEqual(model_of("openai:gpt-6-astra"), "openai:gpt-6-astra")

    def test_the_record_is_e1s_reviewed_shape(self):
        held = record("s" * 64, {"model": "a", "route": "sail:pro_balanced"}, {"model": "b", "route": "sail:k3_balanced"},
                      at="2026-10-10T00:00:00Z", version=2)
        state = {"review": held}
        # league/swarm/elane.py `reviewed` (E1): review.sha == sha, review.verdict == "pass", review.audit.verdict == "pass".
        self.assertEqual((held["sha"], held["verdict"], held["audit"]["verdict"]), ("s" * 64, "pass", "pass"))
        self.assertTrue(holds(state, "s" * 64))
        self.assertFalse(holds(state, "t" * 64))
        self.assertFalse(holds({}, "s" * 64))

    def test_settings_hold_their_bounds(self):
        c = elane_review.cfg({"elane": {"e2": {"review_routes": ["nope", "sail:k3_balanced"], "review_max_unclear": 99,
                                               "review_effort": "high"}}})
        self.assertEqual((c["review_routes"], c["review_max_unclear"], c["review_effort"]),
                         (["sail:k3_balanced"], elane_review.DEFAULTS["review_max_unclear"], "high"))

    def test_the_rubric_names_levels_and_the_calendar(self):
        for words in ("ABSOLUTE LEVELS", "CALENDAR RECONSTRUCTION", "LOOKAHEAD", "contract_reference"):
            self.assertIn(words, elane_review.REVIEW)


if __name__ == "__main__":
    unittest.main()
