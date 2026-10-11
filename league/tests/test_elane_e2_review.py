"""Release E2, THE EQUITY REVIEW (league/swarm/elane_review.py): the level rule refuses a program that holds a raw price
or volume level against a constant or a PARAMS value and leaves scale-free programs alone (the captain's three seeds
among them); a paid failure binds only when grounded; the audit's reader is another model; the record is the one E1's
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
