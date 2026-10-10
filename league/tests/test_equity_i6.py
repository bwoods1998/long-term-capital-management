"""I6, THE SAME CTX LIVE AS IN THE REPLAY (release E1; league/equity/INTERFACES.md 4.5 and 6.4): for 20 random sessions
of a synthetic store (a split and a dividend inside the window), the live builder fed the store's own bars as the 16:20
ET fetch would return them (Alpaca 1Day rows for adjustment=raw and adjustment=all, through session t) gives a ctx
byte-identical to the Gym's, and the decider child's provenance sha (the "equity" kind's `ctx_sha`, after the inputs
crossed the pickle boundary) is the Gym ctx's own.

Cross-package (core): `league.equity.synth`, `store`, `program`, `ctx`; nothing is faked, since the point is the two
real builders."""

import datetime as dt
import hashlib
import random
import tempfile
import unittest
from zoneinfo import ZoneInfo

try:
    import numpy as np
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.live.decider import InlineDecider

NY = ZoneInfo("America/New_York")
SYMBOLS = ("SPY", "QQQ", "IWM", "DIA")
#: A program with no opinion: the ctx is the subject here, not the intents (no date literal: the code rules).
PROGRAM = '''
import numpy as np

NEEDS = {"symbols": ["SPY", "QQQ", "IWM", "DIA"], "history": 60, "max_hold_sessions": 5}
PARAMS = {"k": 2}

def decide(ctx):
    return []
'''
DAYS = 20
SEED = 61006


def stamp(day: dt.date) -> str:
    """A 1Day bar's `t` as Alpaca writes it: the session's New York midnight in UTC."""
    return dt.datetime(day.year, day.month, day.day, tzinfo=NY).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetched(bars, t: int):
    """The store's bars through session index `t` as the live fetch returns them: {sym: [{t, o, h, l, c, v}]} for
    adjustment=raw and for adjustment=all (all's volume is the raw one: the ctx reads volume from the raw series)."""
    from league.gym.day import from_ordinal

    raw_rows, all_rows = {}, {}
    for sym in bars.symbols:
        raw, adj = bars.raw[sym], bars.adj[sym]
        raw_rows[sym], all_rows[sym] = [], []
        for i in range(t + 1):
            if not np.isfinite(raw[i, 3]):
                continue                                   # no bar that session: the venue sends none
            when = stamp(from_ordinal(int(bars.days[i])))
            raw_rows[sym].append({"t": when, "o": float(raw[i, 0]), "h": float(raw[i, 1]), "l": float(raw[i, 2]),
                                  "c": float(raw[i, 3]), "v": float(raw[i, 4])})
            all_rows[sym].append({"t": when, "o": float(adj[i, 0]), "h": float(adj[i, 1]), "l": float(adj[i, 2]),
                                  "c": float(adj[i, 3]), "v": float(raw[i, 4])})
    return raw_rows, all_rows


@unittest.skipUnless(HAVE, "numpy not installed")
class SameCtx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        from league.equity import program as P
        from league.equity import store as S
        from league.equity import synth

        root = synth.synthetic_store(cls.dir.name, symbols=SYMBOLS, start=dt.date(2023, 1, 3), end=dt.date(2025, 12, 31),
                                     seed=SEED, splits={"QQQ": [(dt.date(2025, 6, 2), 2.0)]},
                                     dividends={"SPY": [(dt.date(2025, 3, 21), 1.75)], "DIA": [(dt.date(2025, 9, 19), 0.9)]})
        cls.program = P.load_program(PROGRAM, name="i6")
        cls.bars = S.EquityStore(root).bars(list(cls.program.needs.symbols), "validation",
                                            history=cls.program.needs.history)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def sessions(self):
        rng = random.Random(SEED)
        return sorted(rng.sample(range(self.bars.first, self.bars.n), DAYS))

    def inputs(self, t):
        from league.equity import ctx as C
        from league.gym.day import from_ordinal

        common = dict(needs=self.program.needs, cash=812.5, equity=1000.0, budget=1000.0,
                      caps={s: 500.0 for s in self.program.needs.symbols}, params=self.program.params,
                      rejects=("a buy under $10 is skipped",))
        gym = C.inputs_from_bars(self.bars, t, **common)
        raw_rows, all_rows = fetched(self.bars, t)
        live = C.inputs_from_fetch(raw_rows, all_rows, day=from_ordinal(int(self.bars.days[t])).isoformat(), **common)
        return gym, live

    def test_twenty_random_sessions_byte_for_byte(self):
        from league.equity import ctx as C

        for t in self.sessions():
            with self.subTest(session=t):
                gym, live = self.inputs(t)
                self.assertEqual(C.ctx_bytes(C.build(live)), C.ctx_bytes(C.build(gym)))

    def test_the_childs_provenance_sha_is_the_gym_ctxs(self):
        from league.equity import ctx as C

        decider = InlineDecider()
        decider.kind_load("equity", "i6@1:r", {"code": PROGRAM, "params": {}, "name": "i6", "timeout": 1.0,
                                               "max_errors": 25})
        t = self.sessions()[0]
        gym, live = self.inputs(t)
        answer = decider.kind("equity", "decide", {"jobs": [{"key": "i6@1:r", "inputs": live}]})
        self.assertTrue(answer["ok"], answer)
        result = answer["results"]["i6@1:r"]
        self.assertEqual(result["intents"], [])
        self.assertEqual(result["ctx_sha"], hashlib.sha256(C.ctx_bytes(C.build(gym))).hexdigest())

    def test_never_a_row_after_t(self):
        """The live builder refuses a fetch whose session t is missing, rather than building on the session before."""
        from league.equity import ctx as C
        from league.gym.day import from_ordinal

        t = self.sessions()[-1]
        raw_rows, all_rows = fetched(self.bars, t - 1)
        with self.assertRaises(ValueError):
            C.inputs_from_fetch(raw_rows, all_rows, day=from_ordinal(int(self.bars.days[t])).isoformat(),
                                needs=self.program.needs, cash=1000.0, equity=1000.0, budget=1000.0, caps={},
                                params=self.program.params)


if __name__ == "__main__":
    unittest.main()
