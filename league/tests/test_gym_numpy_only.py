"""The House's live path runs on Python 3.11 with numpy alone (no pyarrow, no polars): the engine's
accounts must open and close a trade there (W5's finding on #358: a closed trade imported the
Parquet reader). A fresh interpreter blocks pyarrow and polars and replays one day from an in-memory
DayChain through an open and a close."""

import subprocess
import sys
import unittest
from pathlib import Path

try:
    import numpy  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

REPO = Path(__file__).resolve().parents[2]

SCRIPT = r'''
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name.split(".")[0] in ("pyarrow", "polars"):
            raise ImportError("blocked " + name)
sys.meta_path.insert(0, Block())

import datetime as dt
import numpy as np
from league.gym import engine as E
from league.gym import runtime as R
from league.gym.day import DayChain, Underlying, contract_key, ordinal

D1 = dt.date(2023, 3, 6)
M = 391
strikes = np.array([400.0, 401.0])
calls = np.array([True, True])
exp = np.full(2, ordinal(D1) + 1, dtype=np.int32)
bid = np.full((M, 2), np.nan)
ask = np.full((M, 2), np.nan)
bid[1:, 0], ask[1:, 0] = 2.00, 2.10
bid[1:, 1], ask[1:, 1] = 1.40, 1.50
bid[130:, 0], ask[130:, 0] = 3.00, 3.10
sizes = np.full((M, 2), 50, dtype=np.int32)
chain = DayChain(root="SPY", day=D1, open_min=570, close_min=960, expiration=exp, dte=np.ones(2, dtype=np.int16),
                 strike=strikes, is_call=calls, bid=bid, ask=ask, bid_size=sizes, ask_size=sizes,
                 oi=np.zeros(2, dtype=np.int64), underlying=Underlying(price=np.full(M, 400.5)), key=contract_key(exp, strikes, calls))

class LiveStore:
    """What the engine asks of a store, from memory (the House would fill it from live quotes)."""
    gate = False
    def session(self, day): return (570, 960)
    def has(self, kind, root, day): return kind in ("nbbo", "underlying") and root == "SPY" and day == D1
    def chain(self, root, day): return chain
    def underlying(self, root, day): return chain.underlying
    def check(self, day): return None
    def trading_days(self): return [D1]
    def history_days(self, before, count): return []
    def data_version(self, roots, days): return "memory"

code = """
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.2, "cadence": 5, "start": 600}
PARAMS = {}
STATE = {"opened": False}
def decide(ctx):
    if not STATE["opened"]:
        STATE["opened"] = True
        return [{"open": "debit_vertical", "legs": [{"side": "long", "right": "C", "dte": 1, "strike": 400},
                 {"side": "short", "right": "C", "dte": 1, "strike": 401}], "qty": 1}]
    if ctx.minute >= 720 and ctx.positions:
        return [{"close": ctx.positions[0]["id"]}]
    return []
"""
[r] = E.run([R.load_program(code)], LiveStore(), E.RunConfig(window="train", roots=("SPY",)), days=[D1])
t = r["trades"][0]
assert "pyarrow" not in sys.modules and "polars" not in sys.modules, "a blocked package was imported"
print(r["status"], t["entry"], t["exit"], t["exit_reason"], t["day"])
'''


@unittest.skipUnless(HAVE, "numpy not installed")
class NumpyOnly(unittest.TestCase):
    def test_an_account_opens_and_closes_without_pyarrow(self):
        done = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, cwd=REPO, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertEqual(done.stdout.split(), ["ok", "0.7", "1.5", "program", "2023-03-06"])


if __name__ == "__main__":
    unittest.main()
