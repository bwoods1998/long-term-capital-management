"""Release E2, THE EQUITY REVIEW (league/swarm/elane_review.py): the level rule refuses a program that holds a raw price
or volume level against a constant or a PARAMS value and leaves scale-free programs alone (the captain's three seeds
among them); it refuses RUN-START DEPENDENCE (the sleeve's dollars of the run held against a constant, a PARAMS value
or the run's anchor) and leaves sizing by the sleeve alone; it refuses THE RUN'S CAPITAL REBUILT FROM A LOT (the
verification's seal-1 residual: the profit lock with no memory) and leaves a lot's own return, a hold count and a size
from the budget alone; a paid failure binds only when grounded; the audit's reader is another model; the record is the
one E1's look reads (league/swarm/elane.py `reviewed`). Every program here is invented."""

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

#: THE VERIFICATION'S SEAL-1 RESIDUAL: the profit lock with NO MEMORY. The House sizes an entry as the asked share of the
#: run's capital, so what a lot cost over that share IS the capital, and the sleeve's dollars over it the run's profit.
LOT_HEAD = '''import math
import numpy as np

NEEDS = {"symbols": ["SPY"], "history": 30, "max_hold_sessions": 4}
PARAMS = {"share": 0.5, "lock": 0.01, "small": 0.02, "stop": 0.05, "h": 3}
STATE = {}
'''
LOT_TAIL = '''    small = ahead >= ctx.params["lock"]
    return [{"buy": "SPY", "share": ctx.params["small"] if small else ctx.params["share"], "at": "open",
             "tag": "s" if small else "f"}]
'''


def lot_lock(body: str, *, pre: str = "", flat: bool = True) -> str:
    # A profit lock: `body` works out `ahead`, the run's profit since it began, and the entry is a token size once
    # it reaches PARAMS["lock"].
    lines = "".join(f"    {line}\n" for line in body.strip("\n").split("\n"))
    return (LOT_HEAD + pre + "\n\ndef decide(ctx):\n" + ("    if ctx.positions:\n        return []\n" if flat else "")
            + lines + LOT_TAIL)


#: The verifier's two programs (scratch v_lock_equiv.py `LAUNDERED`, v_lock_probe.py N28), their rules word for word.
#: The first traded the reviewer's lock lot for lot on six synthetic stores, and the restart check matched every session.
VERIFIERS_FIRST = '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 4}
PARAMS = {"share": 0.5, "lock": 0.01, "small": 0.02}


def decide(ctx):
    if ctx.positions:
        return []
    ahead = 0.0
    for lot in ctx.closed:
        asked = ctx.params["small"] if lot["tag"] == "s" else ctx.params["share"]
        ahead = ctx.cash * asked / (lot["entry"] * lot["qty"]) - 1.0
    small = ahead >= ctx.params["lock"]
    return [{"buy": "SPY", "share": ctx.params["small"] if small else ctx.params["share"], "at": "open", "tag": "s" if small else "f"}]
'''
VERIFIERS_SECOND = '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 4}
PARAMS = {"share": 0.5, "lock": 0.03, "small": 0.02}


def decide(ctx):
    out = []
    ahead = 0.0
    for lot in ctx.positions:
        cost = lot["value"] - lot["pnl"]
        ahead = ctx.equity * ctx.params["share"] / cost - 1.0
    if ctx.positions:
        return out
    share = ctx.params["small"] if ahead >= ctx.params["lock"] else ctx.params["share"]
    return [{"buy": "SPY", "share": share, "at": "open"}]
'''
#: The same lock with the first equity the run saw carried from lot to lot in a lot's TAG, which the House keeps across
#: a restart: no STATE, so the restart check matches every session (`TheLockWithNoMemoryOnE1sEngine`).
TAG_CARRIED = '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 4}
PARAMS = {"share": 0.5, "lock": 0.01, "small": 0.02}


def decide(ctx):
    if ctx.positions:
        return []
    first = ctx.equity
    for lot in ctx.closed:
        first = float(lot["tag"])
    ahead = ctx.equity / first - 1.0
    small = ahead >= ctx.params["lock"]
    return [{"buy": "SPY", "share": ctx.params["small"] if small else ctx.params["share"], "at": "open", "tag": str(first)}]
'''
LOT_ANCHORED = {
    "the verifier's first: cash over the last closed lot's qty times entry": VERIFIERS_FIRST,
    "the verifier's second: equity over an open lot's value less its pnl": VERIFIERS_SECOND,
    "cash over exit times qty less net": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    cost = lot["exit"] * lot["qty"] - lot["net"]
    ahead = ctx.cash * ctx.params["share"] / cost - 1.0'''),
    "cash over a closed lot's proceeds (qty times exit)": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    ahead = ctx.cash * ctx.params["share"] / (lot["exit"] * lot["qty"]) - 1.0'''),
    "the shares cash buys at the lot's entry over the lot's qty": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    ahead = (ctx.cash / lot["entry"]) / lot["qty"] * ctx.params["share"] - 1.0'''),
    "a comparison with no division": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    if ctx.cash * ctx.params["share"] > 1.03 * lot["qty"] * lot["entry"]:
        ahead = 1.0'''),
    "the qty rebuilt from a lot's value over its mark": lot_lock('''
ahead = 0.0
for lot in ctx.positions:
    shares = lot["value"] / lot["mark"]
    ahead = ctx.equity * ctx.params["share"] / (shares * lot["entry"]) - 1.0''', flat=False),
    "the cost rebuilt from a lot's pnl over its own return": lot_lock('''
ahead = 0.0
for lot in ctx.positions:
    own = lot["mark"] / lot["entry"] - 1.0
    if own != 0:
        ahead = ctx.equity * ctx.params["share"] / (lot["pnl"] / own) - 1.0''', flat=False),
    "the cost rebuilt from a lot's value over its own return": lot_lock('''
ahead = 0.0
for lot in ctx.positions:
    cost = lot["value"] / (lot["mark"] / lot["entry"])
    ahead = ctx.equity * ctx.params["share"] / cost - 1.0''', flat=False),
    "the cost through a helper": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    ahead = ctx.cash * ctx.params["share"] / cost_of(lot) - 1.0''', pre='\ndef cost_of(row):\n    return row["qty"] * row["entry"]\n'),
    "the costs of the day's closed lots summed": lot_lock('''
ahead = 0.0
cost = sum(row["qty"] * row["entry"] for row in ctx.closed)
if cost > 0:
    ahead = ctx.cash * ctx.params["share"] / cost - 1.0'''),
    "open lots' values less their pnls, each summed": lot_lock('''
ahead = 0.0
held = 0.0
won = 0.0
for lot in ctx.positions:
    held += lot["value"]
    won += lot["pnl"]
if held > 0:
    ahead = ctx.equity * ctx.params["share"] / (held - won) - 1.0''', flat=False),
    "numpy's divide and multiply": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    ahead = np.divide(ctx.cash * ctx.params["share"], np.multiply(lot["entry"], lot["qty"])) - 1.0'''),
    "the cost's reciprocal": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    inv = 1.0 / (lot["qty"] * lot["entry"])
    ahead = ctx.cash * ctx.params["share"] * inv - 1.0'''),
    "the cost's reciprocal through pow": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    ahead = ctx.cash * ctx.params["share"] * pow(lot["qty"] * lot["entry"], -1) - 1.0'''),
    "the log profit": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    ahead = math.log(ctx.cash * ctx.params["share"]) - math.log(lot["qty"] * lot["entry"])'''),
    "the shares cash buys now against the lot's qty": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    if ctx.cash / ctx.prices["SPY"] * ctx.params["share"] > 1.03 * lot["qty"]:
        ahead = 1.0'''),
    "the cost kept in STATE": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    STATE["cost"] = lot["entry"] * lot["qty"]
if STATE.get("cost"):
    ahead = ctx.cash * ctx.params["share"] / STATE["cost"] - 1.0'''),
    "the lot's fields by .get and the last closed lot by index": lot_lock('''
ahead = 0.0
if ctx.closed:
    last = ctx.closed[-1]
    ahead = ctx.cash * ctx.params["share"] / (last.get("qty") * last.get("entry")) - 1.0'''),
    "a copy of the lot": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    row = dict(lot)
    ahead = ctx.cash * ctx.params["share"] / (row["qty"] * row["entry"]) - 1.0'''),
    "a product numpy makes": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    ahead = ctx.cash * ctx.params["share"] / np.dot([lot["qty"]], [lot["entry"]]) - 1.0'''),
    "a product math makes": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    ahead = ctx.cash * ctx.params["share"] / math.prod([lot["qty"], lot["entry"]]) - 1.0'''),
    "the dollars read back from their text": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    ahead = float(str(ctx.cash)) * ctx.params["share"] / float(f"{lot['qty'] * lot['entry']}") - 1.0'''),
    "dollars times dollars over the cost squared": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    cost = lot["qty"] * lot["entry"]
    ahead = (ctx.equity * ctx.cash) * ctx.params["share"] ** 2 / (cost * cost) - 1.0'''),
    "a lot's qty against a constant (the entry price's level, the capital known)": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    if lot["qty"] < 1.5:
        ahead = 1.0'''),
    "what a lot cost against a constant": lot_lock('''
ahead = 0.0
for lot in ctx.closed:
    if lot["qty"] * lot["entry"] > 515.0:
        ahead = 1.0'''),
    "the first equity the run saw, carried in a lot's tag": TAG_CARRIED,
    "the sleeve's dollars in a tag written as an f-string": lot_lock('''
ahead = 0.0
return [{"buy": "SPY", "share": 0.5, "tag": f"e{ctx.equity:.2f}"}]'''),
    "the sleeve's dollars in a tag set by a key": lot_lock('''
ahead = 0.0
intent = {"buy": "SPY", "share": 0.5}
intent["tag"] = "%.2f" % ctx.cash
return [intent]'''),
    # The run's own profit written so the rule's second version let it through: a function the pass does not know,
    # an exponent, and pow for the reciprocal.
    "equity and budget through a function the pass does not know": lot_lock(
        'ahead = math.copysign(ctx.equity, 1.0) / math.copysign(ctx.budget, 1.0) - 1.0'),
    "equity and budget as exponents": lot_lock(
        'ahead = math.log(1.001 ** ctx.equity) / math.log(1.001 ** ctx.budget) - 1.0'),
    "equity times pow(budget, -1)": lot_lock('ahead = ctx.equity * pow(ctx.budget, -1) - 1.0'),
    "equity and budget read back from their text": lot_lock(
        'ahead = float(str(ctx.equity)) / float(str(ctx.budget)) - 1.0'),
    # The run's dollars mixed with a level, a log, a cross-symbol ratio or a count. Each read as a ratio of two prices
    # (or as unknown) and passed: the run's dollars come first in a mixed value, and a count is of no unit.
    "equity and budget, each plus and less a price": lot_lock(
        'px = ctx.prices["SPY"]\nahead = (ctx.equity + px - px) / (ctx.budget + px - px) - 1.0'),
    "equity and budget, each plus a log price": lot_lock(
        'g = math.log(ctx.prices["SPY"])\nahead = ((ctx.equity + g) - (ctx.budget + g)) / 10.0'),
    "equity and budget, each times a cross-symbol ratio": lot_lock(
        'k = ctx.prices["QQQ"] / ctx.prices["SPY"]\nahead = (ctx.equity * k) / (ctx.budget * k) - 1.0'),
    "the smaller of equity and a price too large to bind": lot_lock(
        'px = ctx.prices["SPY"]\nahead = min(ctx.equity, 1e9 * px) / min(ctx.budget, 1e9 * px) - 1.0'),
    "equity and budget, each in a list with a price": lot_lock(
        'px = ctx.prices["SPY"]\nahead = [ctx.equity, px][0] / [ctx.budget, px][0] - 1.0'),
    "equity and budget in one array with a price": lot_lock(
        'row = np.array([ctx.equity, ctx.budget, ctx.prices["SPY"]])\nahead = row[0] / row[1] - 1.0'),
    "equity and budget, each times the weekday": lot_lock(
        'ahead = (ctx.equity * (ctx.weekday + 1)) / (ctx.budget * (ctx.weekday + 1)) - 1.0'),
    "equity and budget, each times a lot's sessions held": lot_lock(
        'held = ctx.closed[0]["held_sessions"] if ctx.closed else 1\nahead = (ctx.equity * held) / (ctx.budget * held) - 1.0'),
    "what a lot cost plus and less a price": lot_lock('''
ahead = 0.0
px = ctx.prices["SPY"]
for lot in ctx.closed:
    ahead = (ctx.cash + px - px) * ctx.params["share"] / (lot["qty"] * lot["entry"] + px - px) - 1.0'''),
}

#: Honest programs that read their lots for ordinary reasons: never refused. The first three are the captain's list (a
#: stop on a lot's own return from its entry, a max-hold count, a size from ctx.budget).
LOT_HONEST = {
    "a stop on a lot's own return from its entry": LOT_HEAD + '''

def decide(ctx):
    out = []
    for lot in ctx.positions:
        if lot["mark"] / lot["entry"] - 1.0 <= -ctx.params["stop"]:
            out.append({"sell": lot["id"], "at": "open"})
    if not ctx.positions:
        out.append({"buy": "SPY", "share": ctx.params["share"]})
    return out
''',
    "a max-hold count": LOT_HEAD + '''

def decide(ctx):
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions if lot["held_sessions"] >= ctx.params["h"]]
    if not ctx.positions and not any(row["reason"] == "max_hold" for row in ctx.closed):
        out.append({"buy": "SPY", "share": ctx.params["share"], "at": "close"})
    return out
''',
    "a size from ctx.budget": LOT_HEAD + '''

def decide(ctx):
    if ctx.positions or ctx.cash <= 0:
        return []
    usd = min(ctx.cash, ctx.caps["SPY"], ctx.params["share"] * ctx.budget)
    return [{"buy": "SPY", "usd": round(usd, 2)}] if usd > 0 else []
''',
    "a lot's own return in dollars: its pnl over what it cost": LOT_HEAD + '''

def decide(ctx):
    out = []
    for lot in ctx.positions:
        cost = lot["qty"] * lot["entry"]
        basis = lot["value"] - lot["pnl"]
        if cost > 0 and lot["pnl"] / cost <= -ctx.params["stop"] or basis > 0 and lot["pnl"] / basis > 0.08:
            out.append({"sell": lot["id"]})
        elif lot["value"] > cost and lot["held_sessions"] >= 2 or lot["pnl"] * (1.0 / lot["value"]) > 0.05:
            out.append({"sell": lot["id"]})
    return out or ([] if ctx.positions else [{"buy": "SPY", "share": 0.5}])
''',
    "a stop on the average entry of several lots": LOT_HEAD + '''

def decide(ctx):
    lots = [row for row in ctx.positions if row["symbol"] == "SPY"]
    shares = sum(row["qty"] for row in lots)
    if shares > 0:
        average = sum(row["qty"] * row["entry"] for row in lots) / shares
        if ctx.prices["SPY"] / average - 1.0 < -ctx.params["stop"]:
            return [{"sell": row["id"]} for row in lots]
        if len(lots) < 2 and ctx.prices["SPY"] < average:
            return [{"buy": "SPY", "share": 0.25}]
        return []
    return [{"buy": "SPY", "share": 0.25}]
''',
    "a lot's own price from its value and qty, and its pnl's sign": LOT_HEAD + '''

def decide(ctx):
    out = []
    for lot in ctx.positions:
        if lot["qty"] <= 0 or lot["mark"] is None:
            continue
        px = lot["value"] / lot["qty"]
        if px / lot["entry"] - 1.0 > 0.04 or lot["qty"] * (lot["mark"] - lot["entry"]) < 0 and lot["held_sessions"] > 2:
            out.append({"sell": lot["id"]})
    return out or ([] if ctx.positions else [{"buy": "SPY", "usd": 0.5 * ctx.equity}])
''',
    "the last lot's result, a rebuy of the same dollars, and tags that are labels": LOT_HEAD + '''

def decide(ctx):
    if ctx.positions:
        return []
    out = []
    lost = any(row["net"] < 0 for row in ctx.closed)
    wins = sum(1 for row in ctx.closed if row["exit"] / row["entry"] - 1.0 > 0)
    for row in ctx.closed:
        if row["net"] > 0 and row["reason"] == "max_hold" and row["tag"] != "again":
            out.append({"buy": row["symbol"], "usd": row["qty"] * row["exit"], "tag": "again"})
    mom = ctx.bars["SPY"].close[-1] / ctx.bars["SPY"].close[-21] - 1.0
    return out or [{"buy": "SPY", "share": 0.25 if lost else 0.5, "tag": f"m{mom:.2f}w{wins}"}]
''',
    "the position's own state: a weight cap, the cash share, exposure": LOT_HEAD + '''

def decide(ctx):
    out = []
    held = sum(lot["value"] for lot in ctx.positions)
    for lot in ctx.positions:
        if lot["value"] / ctx.equity > 0.6 or lot["pnl"] / ctx.equity < -0.02:
            out.append({"sell": lot["id"]})
    if not out and held / ctx.equity < 0.8 and ctx.cash * (1 / ctx.equity) > 0.2:
        out.append({"buy": "SPY", "usd": 0.2 * ctx.equity})
    return out
''',
}

#: WHAT THE STATIC RULE CANNOT SEE (elane_review's docstring, 1d; ELANE_E2.md): the position's own state used as the
#: anchor. A lot's weight in the sleeve is the asked share times the lot's own return times budget over equity, so the
#: weight set against that return is the run's profit, and nothing static tells it from an honest weight cap. This
#: program is a profit lock with no memory; the level rule and the restart check both pass it; the paid readers' rubric
#: names the pattern.
WEIGHT_LOCK = '''NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 4}
PARAMS = {"share": 0.5, "lock": 0.01, "small": 0.02}


def decide(ctx):
    out = []
    for lot in ctx.positions:
        asked = ctx.params["small"] if lot["tag"] == "s" else ctx.params["share"]
        own = lot["mark"] / lot["entry"]
        small = asked * own / (lot["value"] / ctx.equity) >= 1.0 + ctx.params["lock"]
        if lot["held_sessions"] >= 2:
            out.append({"sell": lot["id"], "at": "open"})
            out.append({"buy": "SPY", "share": ctx.params["small"] if small else ctx.params["share"], "at": "close",
                        "tag": "s" if small else "f"})
    if not ctx.positions:
        out.append({"buy": "SPY", "share": ctx.params["share"], "at": "open", "tag": "f"})
    return out
'''

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
            "the last call's price kept in STATE": '''
STATE = {}
def decide(ctx):
    px, out = ctx.prices["SPY"], []
    if "px" in STATE and px / STATE["px"] - 1 > 0.01:
        out.append({"buy": "SPY", "share": 0.1})
    STATE["px"] = px
    return out
''',
            "each symbol's last price kept in a dict of the program's own": '''
LAST = {}
def decide(ctx):
    out = []
    for s in ctx.symbols:
        px = ctx.prices[s]
        if s in LAST and px / LAST[s] - 1 > 0.01:
            out.append({"buy": s, "share": 0.1})
        LAST[s] = px
    return out
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
        # A level held against a constant inside such a loop, or in a helper called from one, is refused as before; so
        # is a constant whose name is given a level further down the function (the first reading of a function's body
        # is the order its statements run in), and a constant kept in STATE.
        for name, body in {
            "a constant threshold whose name is reused for a level": '''
def decide(ctx):
    x = 400.0
    out = [{"buy": "SPY", "share": 0.5}] if ctx.prices["SPY"] > x else []
    x = ctx.prices["SPY"]
    return out if x > 0 else []
''',
            "a constant kept in STATE and read back against a price": '''
STATE = {}
def decide(ctx):
    STATE["thr"] = 400.0
    return [{"buy": "SPY", "share": 0.5}] if ctx.prices["SPY"] > STATE["thr"] else []
''',
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

    def test_what_ctx_gives_is_never_the_programs_own_whatever_it_writes_there(self):
        # The pass keeps what a program puts under a string key of a container of its own. A row the House gave is not
        # the program's own: writing over a lot's field, or under a lot's field name in STATE, launders nothing, and a
        # PARAMS value is a constant whatever number the file declares for it.
        for name, body in {
            "a zero written over a lot's entry after it was read": '''
def decide(ctx):
    out = []
    for p in ctx.positions:
        if p["entry"] > 400:
            out.append({"sell": p["id"]})
        p["entry"] = 0
    return out
''',
            "the same in a helper handed the lot by sorted()": '''
def rich(p):
    seen = p["mark"] > 400
    p["mark"] = 0
    return seen
def decide(ctx):
    return [{"sell": p["id"]} for p in sorted(ctx.positions, key=rich)]
''',
            "the run's dollars kept in STATE under a lot's field name": '''
STATE = {}
def decide(ctx):
    STATE["value"] = ctx.equity
    return [] if STATE["value"] > 1030.0 else [{"buy": "SPY", "share": 0.5}]
''',
            "a level put under a key the file does not spell, read by one it does": '''
def decide(ctx):
    d = {"a": 1}
    k = "a"
    d[k] = ctx.prices["SPY"]
    return [{"buy": "SPY", "share": 0.5}] if d["a"] > 400 else []
''',
            "a PARAMS value declared zero": '''
PARAMS = {"x": 400.0, "floor": 0.0}
def decide(ctx):
    return [{"buy": "SPY", "share": 0.5}] if ctx.prices["SPY"] - PARAMS["floor"] > PARAMS["x"] else []
''',
        }.items():
            with self.subTest(name):
                self.assertTrue(level_refusals(HEAD + body), name)
        declared_zero = HEAD + '''
PARAMS = {"floor": 0.0}
def decide(ctx):
    return [{"buy": "SPY", "share": 0.5}] if ctx.prices["SPY"] > PARAMS["floor"] else []
'''
        self.assertTrue(level_refusals(declared_zero), "a PARAMS value is a constant, never the zero it is declared as")

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
    stats = {}
    for name, fn in (("hi", np.max), ("lo", np.min)):
        stats[name] = fn(ctx.bars["SPY"].close[-20:])
    if stats["hi"] / stats["lo"] > 1.05:
        out.append({"buy": "SPY", "share": 0.1})
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


class TheRunsCapitalFromALot(unittest.TestCase):
    """The verification's seal-1 residual: with no memory at all a bred program rebuilt the run's capital from its own
    lots (what a lot cost over the share it asked) and held the sleeve's cash or equity against it: the profit lock
    again, which a positive-sum, t-above-a-floor screen passes far more often than its false-positive cap says."""

    RULE = "A rule whose trading depends on how far the run is ahead or behind is refused, whatever its spelling."

    def test_the_capital_rebuilt_from_a_lot_is_refused_in_every_spelling(self):
        self.assertGreaterEqual(len(LOT_ANCHORED), 2 + 4, "the verifier's two and at least four more")
        for name, code in LOT_ANCHORED.items():
            with self.subTest(name):
                found = level_refusals(code)
                self.assertTrue(found, name)
                self.assertTrue(all(f.startswith("line ") for f in found))

    def test_the_verifiers_two_programs_are_refused_before_they_are_stored_or_run(self):
        from league.gym.safety import check_program
        from league.swarm import elane_train

        for name, code, line in (("the first", VERIFIERS_FIRST, 11), ("the second", VERIFIERS_SECOND, 10)):
            with self.subTest(name):
                check_program(code)  # the Gym's own code rules have nothing against either
                self.assertEqual(elane_review.memory_refusals(code), [])
                why = elane_train.check_code(code, ["SPY"])
                self.assertIsNotNone(why, "it passed every static check before")
                self.assertIn("equity level rule", why)
                self.assertIn(f"line {line}: divides the sleeve's dollars now against the run's anchor", why)
                self.assertIn("the capital a lot was bought with", why)
                self.assertIn("the run's own profit since it began", why)
        # The same two programs without the lock are admitted: nothing else in them is refused.
        plain = VERIFIERS_FIRST.replace("        ahead = ctx.cash * asked / (lot[\"entry\"] * lot[\"qty\"]) - 1.0\n",
                                        "        ahead = 0.0 * asked\n")
        self.assertNotIn("ctx.cash", plain)
        self.assertIsNone(elane_train.check_code(plain, ["SPY"]))

    def test_the_runs_dollars_in_a_lots_tag_are_refused(self):
        from league.swarm import elane_train

        found = level_refusals(TAG_CARRIED)
        self.assertEqual(len(found), 1, found)
        self.assertIn("line 13: keeps the run's dollars in a lot's tag", found[0])
        self.assertIn("equity level rule", elane_train.check_code(TAG_CARRIED, ["SPY"]))
        for tag in ('"tag": str(ctx.equity)', '"tag": "e" + str(round(ctx.cash))', '"tag": "{:.0f}".format(ctx.budget)',
                    '"tag": str(lot["qty"] * lot["entry"])', '"tag": str(int(ctx.equity))[:3]'):
            with self.subTest(tag):
                code = ('def decide(ctx):\n    out = []\n    for lot in ctx.closed:\n'
                        f'        out.append({{"buy": "SPY", "share": 0.5, {tag}}})\n    return out\n')
                self.assertTrue(level_refusals(code), tag)
        as_call = 'def decide(ctx):\n    return [dict(buy="SPY", share=0.5, tag=str(ctx.equity))]\n'
        self.assertTrue(level_refusals(as_call))
        # A label, a count, a return and a price in a tag are what a tag is for.
        labels = ('def decide(ctx):\n    c = ctx.bars["SPY"].close\n    mom = c[-1] / c[-21] - 1.0\n'
                  '    return [{"buy": "SPY", "share": 0.5, "tag": f"m{mom:.2f}n{len(ctx.closed)}"},\n'
                  '            {"buy": "SPY", "share": 0.1, "tag": "stop" + str(round(0.95 * c[-1], 2))}]\n')
        self.assertEqual(level_refusals(labels), [])

    def test_honest_readers_of_lots_still_pass(self):
        from league.swarm import elane_train

        self.assertGreaterEqual(len(LOT_HONEST), 3)
        for name, code in LOT_HONEST.items():
            with self.subTest(name):
                self.assertEqual(level_refusals(code), [])
                self.assertIsNone(elane_train.check_code(code, ["SPY"]))
        for code in (SLEEVE_SIZED, SCALE_FREE, *SEED_SHAPES):
            self.assertEqual(level_refusals(code), [])

    def test_what_a_lot_cost_is_the_anchor_and_a_lots_own_return_is_not(self):
        def body(expr: str) -> str:
            return ('def decide(ctx):\n    out = []\n    for lot in ctx.positions:\n'
                    f'        if {expr}:\n            out.append({{"sell": lot["id"]}})\n    return out\n')

        refused = ('ctx.equity / (lot["qty"] * lot["entry"]) > 2.02', 'ctx.cash > lot["qty"] * lot["entry"]',
                   'ctx.equity - (lot["value"] - lot["pnl"]) > 0', 'ctx.cash / lot["qty"] > lot["entry"]',
                   'lot["qty"] * lot["mark"] / ctx.equity > 0.6', 'lot["qty"] > 2.5', 'lot["value"] - lot["pnl"] > 500',
                   'ctx.equity * (1 / (lot["qty"] * lot["entry"])) > 2')
        for expr in refused:
            with self.subTest(expr):
                self.assertTrue(level_refusals(body(expr)), expr)
        allowed = ('lot["pnl"] / (lot["qty"] * lot["entry"]) < -0.05', 'lot["pnl"] / (lot["value"] - lot["pnl"]) < -0.05',
                   'lot["value"] > lot["qty"] * lot["entry"]', 'lot["value"] / lot["qty"] / lot["entry"] - 1 > 0.04',
                   'lot["qty"] > 0', 'lot["qty"] * (lot["mark"] - lot["entry"]) < 0', 'lot["value"] / ctx.equity > 0.6',
                   'lot["pnl"] * (1 / lot["value"]) > 0.05', 'ctx.cash * (1 / ctx.equity) < 0.5',
                   'lot["value"] - lot["pnl"] > 0', 'ctx.prices["SPY"] / (lot["qty"] * lot["entry"] / lot["qty"]) < 0.95')
        for expr in allowed:
            with self.subTest(expr):
                self.assertEqual(level_refusals(body(expr)), [], expr)
        # A dict of the program's own with a key named as a lot's is no lot, and a count is no dollar.
        own = ('def decide(ctx):\n    plan = {"qty": 3, "value": 0.5}\n    late = ctx.weekday >= 3 or ctx.session_of_month > 15\n'
               '    return [{"buy": "SPY", "share": 0.5}] if plan["qty"] > 2 and plan["value"] > 0.25 and late else []\n')
        self.assertEqual(level_refusals(own), [])

    def test_what_the_static_rule_cannot_see_is_named_for_the_two_paid_readers(self):
        from pathlib import Path

        from league.swarm import elane_train

        # The position's own state used as the anchor: a weight set against the lot's own return. The static rule
        # passes it (a weight cap is an honest rule), so the rubric and its facts must name it.
        self.assertEqual(level_refusals(WEIGHT_LOCK), [])
        self.assertIsNone(elane_train.check_code(WEIGHT_LOCK, ["SPY"]))
        rubric = " ".join(elane_review.REVIEW.split())
        fact = " ".join(elane_review.FACTS["run"].split())
        for text in (rubric, fact):
            self.assertIn(self.RULE, text)
            for words in ("qty times its entry or exit", "its value less its pnl", "exit times qty less net",
                          "weight in the sleeve", "a lot's tag"):
                self.assertIn(words, text)
        finding = {"code_excerpt": 'small = asked * own / (lot["value"] / ctx.equity) >= 1.0 + ctx.params["lock"]',
                   "contract_reference": "run",
                   "counterexample": "a lot bought with half the budget weighs under half of a sleeve that is ahead, so "
                                     "the next entry is a token size; mid-run the same lot weighs otherwise"}
        answer = {"json": {"verdict": "fail", "reasons": ["a profit lock on the lot's weight"], "findings": [finding]},
                  "text": ""}
        self.assertEqual(grounded(answer, WEIGHT_LOCK)["verdict"], "fail", "a reader's failure on it binds")
        # The design says plainly what the rule cannot see, and the authors' prompts say what it refuses.
        design = " ".join((Path(elane_review.__file__).parent / "ELANE_E2.md").read_text(encoding="utf-8").split())
        self.assertIn("What the static rule cannot see", design)
        self.assertIn(self.RULE[0].lower() + self.RULE[1:-1], design)
        self.assertIn("what a lot cost", " ".join(elane_train.RESEARCHER_SYSTEM.split()))
        self.assertIn("whatever its spelling", " ".join(elane_train.RESEARCHER_SYSTEM.split()))


class TheLockWithNoMemoryOnE1sEngine(unittest.TestCase):
    """The residual on E1's own engine and runner over a synthetic zero-drift store (an invented market): the verifier's
    first program and the tag-carried one trade the reviewer's lock lot for lot, and the Train bar's restart check
    matches every session of each, for neither keeps anything in STATE. The static rule is what refuses them. The
    weight lock is the one the static rule cannot see: it shrinks its entries as the lock does and passes both."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from pathlib import Path

        from league.equity import config, synth
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider
        from league.swarm import elane, elane_train

        cls.tmp = tempfile.TemporaryDirectory()
        root = synth.synthetic_store(Path(cls.tmp.name) / "flat" / elane.STORE_DIR, symbols=("SPY",), seed=0, drift=0.0)
        cls.decider = InlineDecider()
        runner = Isolated(cls.decider, root)
        cls.lock = RUN_ANCHORED["the profit lock (equity over budget against a PARAMS value)"].replace(
            '"lock": 0.03', '"lock": 0.01').replace(
            '    share = ctx.params["small"] if ahead >= ctx.params["lock"] else ctx.params["share"]\n'
            '    return [{"buy": "SPY", "share": share, "at": "open"}]\n',
            '    small = ahead >= ctx.params["lock"]\n    return [{"buy": "SPY", "share": ctx.params["small"] if small '
            'else ctx.params["share"], "at": "open", "tag": "s" if small else "f"}]\n')
        cls.runs = {name: [runner.train(code, {}, name=name, start=first, end=last, k=config.K_BASE)
                           for first, last in elane_train.TRAIN_SPANS]
                    for name, code in (("lock", cls.lock), ("first", VERIFIERS_FIRST), ("tag", TAG_CARRIED),
                                       ("weight", WEIGHT_LOCK))}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def lots(self, name: str) -> list:
        for run in self.runs[name]:
            self.assertEqual(run.result["status"], "ok", name)
        return [[(lot["entry_day"], str(lot["qty"]), str(lot["entry_px"]), lot["exit_day"], str(lot["exit_px"]))
                 for lot in run.result["lots"]] for run in self.runs[name]]

    def token(self, name: str) -> int:
        """The lots bought at the token size (2% of the run's capital, against 50%)."""
        return sum(1 for run in self.runs[name] for lot in run.result["lots"]
                   if float(lot["qty"]) * float(lot["entry_px"]) < 100.0)

    def restart(self, name: str, code: str) -> dict:
        from league.swarm import elane_train

        return elane_train.restart_check(self.decider, code, {}, name=name,
                                         streams=[elane_train.state_inputs(run) for run in self.runs[name]])

    def test_the_lock_is_the_reviewers_program_and_it_locks(self):
        self.assertIn("ahead = ctx.equity / ctx.budget - 1.0", self.lock)
        self.assertIn('"tag": "s" if small else "f"', self.lock)
        lots = self.lots("lock")
        self.assertGreater(sum(len(span) for span in lots), 100)
        self.assertGreater(self.token("lock"), 0, "once ahead it trades a token size")

    def test_with_no_memory_the_same_trades_and_the_restart_check_passes(self):
        from league.swarm import elane_train

        lock = self.lots("lock")
        for name, code in (("first", VERIFIERS_FIRST), ("tag", TAG_CARRIED)):
            with self.subTest(name):
                self.assertEqual(self.lots(name), lock, "lot for lot the reviewer's profit lock")
                check = self.restart(name, code)
                self.assertTrue(check["held"], check)
                self.assertEqual(check["matched"], check["sessions"], "nothing in STATE for a restart to empty")
                self.assertIn("equity level rule", elane_train.check_code(code, ["SPY"]), "the static rule refuses it")

    def test_the_weight_lock_passes_the_static_rule_and_the_restart_check(self):
        from league.swarm import elane_train

        self.lots("weight")
        self.assertGreater(self.token("weight"), 0, "it shrinks its entries once the run is ahead, as the lock does")
        check = self.restart("weight", WEIGHT_LOCK)
        self.assertTrue(check["held"], check)
        self.assertEqual(check["matched"], check["sessions"])
        self.assertIsNone(elane_train.check_code(WEIGHT_LOCK, ["SPY"]), "left to the two paid readers (the rubric)")


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
