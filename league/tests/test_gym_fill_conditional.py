"""The conditional adverse-selection rule: a fill model fitted per next-minute condition (`calibrate.py --adverse
conditional`) draws against the hazard Train measured on adverse-or-flat minutes and on favourable ones, each on its own
minutes; an unconditional table (every table before it) fills exactly as before. Synthetic stores only.

The walk market: SPY constant at 400, three 0 DTE calls whose mids step -1, 0 or +1 cent each minute by a keyed hash
(30% down, 40% flat, 30% up), quoted two cents each side with 100 contracts; trade prints on a keyed share of
contract-minutes drawn independently of the path (or, `flat_only`, only on minutes whose next mid holds)."""

import contextlib
import datetime as dt
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import calibrate as CAL
    from league.gym import engine as E
    from league.gym import fills as F
    from league.gym import legs as L
    from league.gym import runtime as R
    from league.gym import store as S
    from league.gym import synth
    from league.gym.day import ordinal
    from league.gym.events import EventCalendar

DAYS = [dt.date(2023, 3, 6), dt.date(2023, 3, 7), dt.date(2023, 3, 8)]
STRIKES = (399, 400, 401)
START = {399: 250, 400: 200, 401: 160}          # each call's first mid, cents
ROWS = range(571, 961)                          # 09:31 .. 16:00 (the 09:30 row has no quote)
TINY = 1e-9                                     # a prior that leaves each rate its MLE

SINGLE = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 1], "band": 0.05, "cadence": 5, "start": 575}
PARAMS = {"hold": 20, "limit": "mid", "k": 0, "price": 0.0, "qty": 2, "tif": 20}
def decide(ctx):
    p = ctx.params
    if ctx.orders:
        return []
    limit = {"mid": p["k"]} if p["limit"] == "k" else {"price": p["price"]} if p["limit"] == "price" else p["limit"]
    out = [{"close": pos["id"], "limit": limit, "tif": 15} for pos in ctx.positions if pos["held_minutes"] >= p["hold"]]
    if not ctx.positions and ctx.minute < 930:
        out.append({"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 0, "strike": 400}], "qty": p["qty"],
                    "limit": limit, "tif": p["tif"]})
    return out
'''
VERTICAL = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 1], "band": 0.05, "cadence": 5, "start": 575}
PARAMS = {"hold": 30, "k": 1}
def decide(ctx):
    p = ctx.params
    if ctx.orders:
        return []
    out = [{"close": pos["id"], "limit": {"mid": p["k"]}, "tif": 15} for pos in ctx.positions if pos["held_minutes"] >= p["hold"]]
    if not ctx.positions and ctx.minute < 930:
        out.append({"open": "debit_vertical", "legs": [{"side": "long", "right": "C", "dte": 0, "strike": 400},
                    {"side": "short", "right": "C", "dte": 0, "strike": 401}], "qty": 1, "limit": {"mid": p["k"]}, "tif": 20})
    return out
'''
#: What origin/main (d1c1cbbc, before this rule) returned for `old_table_fingerprint`: the unconditional rule, pinned.
ORIGIN_MAIN_FINGERPRINT = "c0b20ec4d2f24719161c19833669c7498ae87ba551756215f75e3c9ca99d7365"


def u(*parts) -> float:
    """A keyed uniform number in [0, 1): the same on every machine."""
    return int.from_bytes(hashlib.blake2b("|".join(str(p) for p in parts).encode(), digest_size=8).digest(), "big") / 2.0 ** 64


def paths(day: dt.date) -> dict[int, list[int]]:
    """Each call's mid in cents on every row of `ROWS`."""
    out = {}
    for k in STRIKES:
        mid, path = START[k], []
        for m in ROWS:
            path.append(mid)
            x = u("step", day, k, m)
            mid += -1 if x < 0.3 else (1 if x >= 0.7 else 0)
            mid = max(mid, 10)
        out[k] = path
    return out


def walk_store(root: Path, *, share: float = 0.2, flat_only: bool = False, varied: bool = False, wing: bool = False) -> "S.Store":
    """The walk market (the module docstring). `varied` adds prints at the touch through the queue, a cent inside the
    spread on each side and at the far side, and complex prints; `wing` adds a 420 call (5% out) quoted all day."""
    w = synth.Writer(root)
    w.calendar(DAYS)
    for day in DAYS:
        cols = {k: [] for k in ("expiration", "strike", "right", "minute", "bid", "ask", "bid_size", "ask_size")}
        tq = {k: [] for k in ("expiration", "strike", "right", "ms_of_day", "price", "size", "condition", "exchange", "bid", "ask",
                              "bid_size", "ask_size")}
        walks = paths(day)
        if wing:
            walks[420] = [20] * len(ROWS)
        for k, path in walks.items():
            for m, mid in zip(ROWS, path):
                for name, value in (("expiration", day), ("strike", float(k)), ("right", "C"), ("minute", m),
                                    ("bid", (mid - 2) / 100), ("ask", (mid + 2) / 100), ("bid_size", 100), ("ask_size", 100)):
                    cols[name].append(value)
            if k == 420:
                continue
            for i, m in enumerate(list(ROWS)[:-1]):               # the rows the calibration's exposure counts
                mid = path[i]
                if flat_only and path[i + 1] != mid:
                    continue
                prints = []
                if u("print", day, k, m) < share:
                    prints.append((mid, 1, 18))
                if varied:
                    x = u("varied", day, k, m)
                    if x < 0.05:
                        prints.append((mid - 2, 150, 18))            # at the bid, through the 100 displayed
                    elif x < 0.15:
                        prints.append((mid - 1, 1, 18))              # a cent inside the bid
                    elif x < 0.25:
                        prints.append((mid + 1, 1, 18))              # a cent inside the ask
                    elif x < 0.30:
                        prints.append((mid + 2, 5, 18))              # at the ask, inside the queue
                    if u("complex", day, k, m) < share:
                        prints.append((mid, 1, 130))
                for price, size, condition in prints:
                    for name, value in (("expiration", day), ("strike", float(k)), ("right", "C"), ("ms_of_day", m * 60000 + 5000),
                                        ("price", price / 100), ("size", size), ("condition", condition), ("exchange", 1),
                                        ("bid", (mid - 2) / 100), ("ask", (mid + 2) / 100), ("bid_size", 100), ("ask_size", 100)):
                        tq[name].append(value)
        w.nbbo("SPY", day, **cols)
        w.underlying("SPY", day, list(range(570, 961)), [400.0] * 391)
        if tq["price"]:
            w.trade_quote("SPY", day, tq)
    w.finish()
    return S.Store(root)


def programs():
    return [R.load_program(SINGLE, name="single"), R.load_program(VERTICAL, name="vertical"),
            R.load_program(SINGLE, name="single_q4", params={"limit": "k", "k": 1, "hold": 10, "qty": 5})]


def run(store, model, stress=1.0):
    return E.run(programs(), store, E.RunConfig(window="train", roots=("SPY",), fill_model=model, stress=stress))


def record(results) -> list:
    """What a run did, without what depends on the code's own hash or numpy's transcendental functions."""
    return [[r["program"], r["status"], r["fill_model"], r["fills"],
             [{k: v for k, v in t.items() if k != "context"} for t in r["trades"]], r["daily"]] for r in results]


def old_table_fingerprint(root: Path) -> tuple[str, list]:
    """The unconditional rule on the walk market: a uniform table and the store's own unconditional fit, each at 1x and
    at the gate's 1.5x stress. Uses only what origin/main already had, so the same function pins origin/main."""
    store = walk_store(root, varied=True)
    fitted = F.FillModel.from_json(CAL.fit(store, ["SPY"], prior=100.0, min_bucket=50.0))
    boosted = F.FillModel(hazard={k: min(1.0, 10 * v) for k, v in fitted.hazard.items()}, size=fitted.size, source="x10")
    rows, counts = [], []
    for model in (synth.uniform_model(0.3, ("SPY",), levels=(0, 2, 3), size=3), fitted, boosted):
        for stress in (1.0, 1.5):
            results = run(store, model, stress)
            rows.append(record(results))
            counts.append([(r["summary"]["trades"], r["fills"]["fills"], r["fills"]["at_natural"]) for r in results])
    text = json.dumps({"fit": {k: v for k, v in CAL.fit(store, ["SPY"], prior=100.0, min_bucket=50.0).items() if k != "meta"},
                       "runs": rows}, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest(), counts


def exposure_walk(store, model, q=0.0):
    """Every contract-minute the calibration counts, as the engine sees it: a resting buy and a resting sell of one
    call at level `q`, classified by the engine's own `_next_move`. Returns the expected passive fills under the
    conditional rule, under the unconditional rule, and at the unconditional table over all minutes; the side-minutes
    adverse-or-flat and in all; and per cell, [side-minutes, adverse-or-flat side-minutes]."""
    events = EventCalendar(store.trading_days(), store.session)
    cond = old = measured = 0.0
    adverse = total = 0
    cells: dict = {}
    for day in DAYS:
        data = E.DayData(store, day, ("SPY",), events, E.History(11), ordinal(day))
        chain = data.chains["SPY"]
        for mi in range(1, data.minutes - 1):
            snap = data.snapshot("SPY", mi)
            for c in range(chain.contracts):
                if not (numpy.isfinite(snap.bid[c]) and numpy.isfinite(snap.ask[c])):
                    continue
                leg = L.LegFill(idx=c, key=int(chain.key[c]), side=1, ratio=1, dte=int(chain.dte[c]), strike=float(chain.strike[c]),
                                is_call=True)
                mid = L.mid_value(snap, [leg])
                shape = [(int(snap.dte[c]), leg.strike / snap.spot - 1.0)]
                key = F.cell("SPY", q, 1, *shape[0], snap.minute)
                for buying in (True, False):
                    move = E.Account._next_move(data, mi, "SPY", [leg], mid, buying)
                    p = model.p("SPY", q, shape, snap.minute)
                    measured += p
                    total += 1
                    row = cells.setdefault(key, [0, 0])
                    row[0] += 1
                    if move is None:
                        continue
                    adverse += bool(move)
                    row[1] += bool(move)
                    cond += model.p("SPY", q, shape, snap.minute, adverse=move)
                    old += p if E.Account._adverse(data, mi, "SPY", [leg], mid, buying) else 0.0
    return cond, old, measured, adverse, total, cells


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class ConditionalAdverse(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="gym-cond-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_an_old_table_fills_exactly_as_origin_main(self):
        # The same runs on origin/main (d1c1cbbc, before this rule) returned this fingerprint: trades, fills, daily P&L,
        # the fill model's version and the unconditional fit itself, byte for byte.
        fingerprint, counts = old_table_fingerprint(self.dir / "walk")
        self.assertEqual(fingerprint, ORIGIN_MAIN_FINGERPRINT, counts)
        # Not a vacuous pin: every model fills patiently somewhere (a share of fills away from the natural).
        self.assertTrue(all(any(at is not None and at < 1.0 for _, _, at in run) for run in counts), counts)

    def test_the_conditional_table_reproduces_the_measured_rate_where_hits_ignore_the_next_move(self):
        store = walk_store(self.dir / "walk")
        table = CAL.fit(store, ["SPY"], prior=TINY, min_bucket=0.0, adverse="conditional")
        self.assertEqual(table["adverse"], "conditional")
        model = F.FillModel.from_json(table)
        self.assertTrue(model.conditional)
        # Every print is at the mid: a q2 hit for a resting buy and a resting sell alike.
        hits = sum(2 for day in DAYS for k in STRIKES for m in list(ROWS)[:-1] if u("print", day, k, m) < 0.2)
        cond, old, measured, adverse, total, _ = exposure_walk(store, model)
        self.assertAlmostEqual(measured, hits, delta=1e-3 * hits)     # the unconditional table: hits / exposure, cell by cell
        self.assertAlmostEqual(cond, hits, delta=1e-3 * hits)         # the conditional rule fills as often as Train printed
        share = adverse / total                                        # flat is adverse for both sides: about 0.7 here
        self.assertTrue(0.6 < share < 0.8, share)
        self.assertAlmostEqual(old / measured, share, delta=0.01)     # the unconditional rule: the measured rate x that share
        fitted = table["meta"]["fitted_on"]
        self.assertEqual((fitted["adverse_side_minutes"], fitted["adverse_side_minutes"] + fitted["favourable_side_minutes"]),
                         (adverse, total))                              # the calibration classifies as the engine does
        self.assertEqual(fitted["no_next_quote_contract_minutes"], 0)
        # Hits independent of the next move: each condition's rate is the unconditional one, within sampling error.
        for cell in ("SPY|q2|s|d0|k0|t0", "SPY|q2|s|d0|k0|t1", "SPY|q2|s|d0|k0|t2"):
            for name in ("hazard_adverse", "hazard_favourable"):
                self.assertAlmostEqual(table[name][cell] / table["hazard"][cell], 1.0, delta=0.25, msg=(cell, name))
        # The cells are the unconditional table's, no more.
        self.assertLessEqual(set(table["hazard_adverse"]) | set(table["hazard_favourable"]), set(table["hazard"]))

    def test_no_favourable_cells_is_the_unconditional_rule_up_to_the_rate(self):
        # Prints only on minutes whose next mid holds: Train would show no fill before a favourable move.
        store = walk_store(self.dir / "flat", flat_only=True, share=0.5)
        table = CAL.fit(store, ["SPY"], prior=TINY, min_bucket=0.0, adverse="conditional")
        self.assertEqual(table["hazard_favourable"], {})
        # The normalisation: the adverse cell is the unconditional rate over the adverse-or-flat share of the minutes.
        model = F.FillModel.from_json(table)
        cond, old, measured, adverse, total, cells = exposure_walk(store, model)
        self.assertAlmostEqual(cond, measured, delta=1e-3 * measured)   # every Train fill is on an adverse-or-flat minute
        self.assertLess(old, 0.8 * measured)                            # the unconditional rule misses a share of them
        for cell, (n, n_adverse) in cells.items():                      # p_adv = p x all minutes / adverse-or-flat ones
            self.assertAlmostEqual(table["hazard_adverse"][cell], table["hazard"][cell] * n / n_adverse, delta=2e-6, msg=cell)
        # And with those rates as an unconditional table, every run is the same run, stressed or not.
        normalised = F.FillModel(hazard=model.hazard_adverse, size=model.size, source="normalised")
        for stress in (1.0, 1.5):
            a, b = run(store, model, stress), run(store, normalised, stress)
            self.assertNotEqual(a[0]["fill_model"], b[0]["fill_model"])
            self.assertEqual([x[1:2] + x[3:] for x in record(a)], [x[1:2] + x[3:] for x in record(b)], stress)
            self.assertGreater(sum(r["summary"]["trades"] for r in a), 0)

    def test_p_fav_zero_reproduces_todays_rule_exactly(self):
        store = walk_store(self.dir / "walk", varied=True)
        for old in (synth.uniform_model(0.3, ("SPY",), levels=(0, 2, 3), size=3),
                    F.FillModel.from_json(CAL.fit(store, ["SPY"], prior=100.0, min_bucket=50.0))):
            conditional = F.FillModel(hazard=old.hazard, size=old.size, hazard_adverse=dict(old.hazard), hazard_favourable={})
            for stress in (1.0, 1.5):
                a, b = run(store, old, stress), run(store, conditional, stress)
                self.assertEqual([x[1:2] + x[3:] for x in record(a)], [x[1:2] + x[3:] for x in record(b)], stress)
                self.assertTrue(any((r["fills"]["at_natural"] or 1.0) < 1.0 for r in a), stress)   # patient fills happened

    def test_monotone_in_the_level_per_condition_on_the_unconditional_cells(self):
        store = walk_store(self.dir / "varied", varied=True, wing=True)
        table = CAL.fit(store, ["SPY"], prior=100.0, min_bucket=3000.0, adverse="conditional")
        for name in ("hazard", "hazard_adverse", "hazard_favourable"):
            cells = table[name]
            self.assertTrue(any(k.startswith("SPY|q0|") for k in cells), name)   # the touch, through the queue
            self.assertTrue(any("|m|" in k for k in cells), name)                 # complex prints
            for cls in "sm":
                for t in range(3):
                    rates = [cells.get(f"SPY|q{q}|{cls}|d0|k0|t{t}", 0.0) for q in range(6)]
                    self.assertEqual(rates, sorted(rates), (name, cls, t))
            # The wing (5% out: 2334 side-minutes, under the 3000 floor) has no cells in any table: natural only.
            self.assertFalse([k for k in cells if "|k3|" in k], name)
        self.assertLessEqual(set(table["hazard_adverse"]) | set(table["hazard_favourable"]), set(table["hazard"]))
        # The unconditional part of a conditional fit is the unconditional fit.
        plain = CAL.fit(store, ["SPY"], prior=100.0, min_bucket=3000.0)
        self.assertEqual((plain["hazard"], plain["size"]), (table["hazard"], table["size"]))
        self.assertNotIn("adverse", plain)
        self.assertNotIn("hazard_adverse", plain)

    def test_the_conditional_rule_fills_on_favourable_minutes_and_stress_halves_it(self):
        # 1.00 x 1.01 on even minutes, 1.01 x 1.02 on odd ones: a buy at 1.00 is at the touch only on an even minute, and
        # the next mid is always higher then (favourable). The unconditional rule never fills it (test_gym_fills).
        quotes = {m: (1.00, 1.01) if m % 2 == 0 else (1.01, 1.02) for m in range(571, 800)}
        w = synth.Writer(self.dir / "rising")
        w.calendar([DAYS[0]])
        synth.flat_day(w, "SPY", DAYS[0], [{"expiration": DAYS[0], "strike": 400, "right": "C", "quotes": quotes}], prices=400.5)
        w.finish()
        store = S.Store(self.dir / "rising")
        key = int(store.chain("SPY", DAYS[0]).key[0])
        first = lambda p: next(m for m in range(602, 800, 2) if F.draw([key], ordinal(DAYS[0]), m, "buy") < p)  # noqa: E731
        h = next(x for x in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1) if first(x) != first(x / 2))  # draws that tell them apart
        touch = {F.cell("SPY", -1.0, 1, 0, 0.0, t): h for t in (600, 700)}
        code = SINGLE.replace('"strike": 400}], "qty": p["qty"]', '"strike": 400}], "qty": 1').replace('"start": 575', '"start": 600')
        prog = R.load_program(code, name="touch", params={"limit": "price", "price": 1.00, "hold": 10_000, "tif": 300})
        cfg = lambda model, stress: E.RunConfig(window="train", roots=("SPY",), fill_model=model, stress=stress)  # noqa: E731
        old = F.FillModel(hazard=touch)
        [r] = E.run([prog], store, cfg(old, 1.0))
        self.assertEqual(r["summary"]["trades"], 0)
        # Only favourable cells: it fills on the first even minute whose keyed draw is under h (under h / 2 stressed,
        # paying the extra half-spread: 1.00 + 0.5 x 0.005).
        fav = F.FillModel(hazard=touch, hazard_adverse={}, hazard_favourable=touch)
        [t] = E.run([prog], store, cfg(fav, 1.0))[0]["trades"]
        [ts] = E.run([prog], store, cfg(fav, 1.5))[0]["trades"]
        self.assertEqual((t["filled_minute"], t["entry"]), (first(h), 1.00))
        self.assertEqual((ts["filled_minute"], ts["entry"]), (first(h / 2), 1.0025))
        # Only adverse cells: nothing, as under the unconditional rule.
        adv = F.FillModel(hazard=touch, hazard_adverse=touch, hazard_favourable={})
        self.assertEqual(E.run([prog], store, cfg(adv, 1.0))[0]["summary"]["trades"], 0)

    def test_a_flat_minute_draws_against_the_adverse_cell(self):
        w = synth.Writer(self.dir / "flat1")
        w.calendar([DAYS[0]])
        synth.flat_day(w, "SPY", DAYS[0], [{"expiration": DAYS[0], "strike": 400, "right": "C", "quotes": {571: (1.00, 1.01)}}],
                       prices=400.5)
        w.finish()
        store = S.Store(self.dir / "flat1")
        key = int(store.chain("SPY", DAYS[0]).key[0])
        first = lambda p: next(m for m in range(601, 900) if F.draw([key], ordinal(DAYS[0]), m, "buy") < p)  # noqa: E731
        h = next(x for x in (0.5, 0.4, 0.3, 0.2) if first(x) > 601)
        cells = lambda rate: {F.cell("SPY", -1.0, 1, 0, 0.0, t): rate for t in (600, 700)}  # noqa: E731
        model = F.FillModel(hazard=cells(h), hazard_adverse=cells(h), hazard_favourable=cells(1.0))
        code = SINGLE.replace('"start": 575', '"start": 600')
        prog = R.load_program(code, name="flat", params={"limit": "mid", "hold": 10_000, "qty": 1, "tif": 300})
        [t] = E.run([prog], store, E.RunConfig(window="train", roots=("SPY",), fill_model=model))[0]["trades"]
        self.assertEqual((t["filled_minute"], t["entry"]), (first(h), 1.00))   # the favourable certainty never applied

    def test_no_next_quote_no_passive_fill(self):
        w = synth.Writer(self.dir / "gap")
        w.calendar([DAYS[0]])
        synth.flat_day(w, "SPY", DAYS[0], [{"expiration": DAYS[0], "strike": 400, "right": "C",
                                            "quotes": {571: (1.00, 1.01), 603: (None, None)}}], prices=400.5)
        w.finish()
        store = S.Store(self.dir / "gap")
        events = EventCalendar(store.trading_days(), store.session)
        data = E.DayData(store, DAYS[0], ("SPY",), events, E.History(11), ordinal(DAYS[0]))
        chain = data.chains["SPY"]
        leg = L.LegFill(idx=0, key=int(chain.key[0]), side=1, ratio=1, dte=0, strike=400.0, is_call=True)
        mid = L.mid_value(data.snapshot("SPY", 31), [leg])
        self.assertIs(E.Account._next_move(data, 31, "SPY", [leg], mid, True), True)      # 10:01 -> 10:02: flat
        self.assertIs(E.Account._next_move(data, 32, "SPY", [leg], mid, True), None)      # 10:02 -> 10:03: no quote
        self.assertIs(E.Account._adverse(data, 32, "SPY", [leg], mid, True), False)
        known, up, down = CAL.next_moves(chain)
        self.assertEqual((bool(known[31, 0]), bool(known[32, 0]), bool(up[31, 0] or down[31, 0])), (True, False, False))
        # In a run: an order working only at 10:02 (decided at 10:01) never fills there, whatever both tables say; with
        # a quote at 10:03 it fills at 10:02 (a flat next minute: the adverse cell).
        certain = {F.cell("SPY", -1.0, 1, 0, 0.0, 600): 1.0}
        model = F.FillModel(hazard=certain, hazard_adverse=certain, hazard_favourable=certain)
        code = SINGLE.replace('"start": 575', '"start": 601')
        prog = lambda: R.load_program(code, name="gap", params={"limit": "mid", "hold": 10_000, "qty": 1, "tif": 300})  # noqa: E731
        [r] = E.run([prog()], store, E.RunConfig(window="train", roots=("SPY",), fill_model=model))
        self.assertEqual((r["summary"]["trades"], r["fills"]["opens"], r["fills"]["filled"]), (0, 1, 0))
        w = synth.Writer(self.dir / "gap2")
        w.calendar([DAYS[0]])
        synth.flat_day(w, "SPY", DAYS[0], [{"expiration": DAYS[0], "strike": 400, "right": "C",
                                            "quotes": {571: (1.00, 1.01), 604: (None, None)}}], prices=400.5)
        w.finish()
        [t] = E.run([prog()], S.Store(self.dir / "gap2"), E.RunConfig(window="train", roots=("SPY",), fill_model=model))[0]["trades"]
        self.assertEqual((t["filled_minute"], t["entry"]), (602, 1.00))

    def test_the_table_reads_its_condition_and_packages_take_their_lowest_leg_per_condition(self):
        near, far = (0, 0.001), (0, 0.02)
        adv = {F.cell("SPY", 0.1, 2, 0, 0.001, 700): 0.30, F.cell("SPY", 0.1, 1, 0, 0.001, 700): 0.20,
               F.cell("SPY", 0.1, 2, 0, 0.02, 700): 0.05, F.cell("SPY", 0.1, 1, 0, 0.02, 700): 0.40}
        fav = {k: v / 10 for k, v in adv.items()}
        model = F.FillModel(hazard={k: v / 2 for k, v in adv.items()}, hazard_adverse=adv, hazard_favourable=fav)
        self.assertEqual(model.p("SPY", 0.1, [near, far], 700, adverse=True), 0.05)
        self.assertAlmostEqual(model.p("SPY", 0.1, [near, far], 700, adverse=False), 0.005)
        self.assertAlmostEqual(model.p("SPY", 0.1, [near, near], 700, adverse=False), 0.02)  # 0.03 complex capped by 0.02 single
        self.assertEqual(model.p("SPY", 0.1, [near], 700), 0.10)                          # None: the unconditional cells
        self.assertEqual(model.p("SPY", 0.1, [near, (9, 0.001)], 700, adverse=True), 0.0)  # 8+ days: never modelled
        self.assertEqual(model.p("SPY", -1.2, [near], 700, adverse=True), 0.0)            # behind the touch
        # At or through the real natural (working only under stress): the unconditional rule, certain only when adverse.
        self.assertEqual((model.p("SPY", 1.0, [near], 700, adverse=True), model.p("SPY", 1.0, [near], 700, adverse=False)), (1.0, 0.0))
        self.assertEqual(F.FillModel(hazard=adv).p("SPY", 1.0, [near], 700, adverse=False), 1.0)
        # An unconditional table ignores `adverse`.
        plain = F.FillModel(hazard=adv)
        self.assertEqual(plain.p("SPY", 0.1, [near, far], 700, adverse=False), plain.p("SPY", 0.1, [near, far], 700))

    def test_loading_versions_and_refusals(self):
        hazard = {"SPY|q2|s|d0|k0|t0": 0.1}
        old = F.FillModel.from_json({"hazard": hazard, "size": {"SPY|q2|s|d0": 2}})
        self.assertFalse(old.conditional)
        # The version of an old table is what origin/main computed (a run's identity keeps its cache).
        self.assertEqual(F.FillModel(hazard=hazard).version, "fm-e603ee43101af6d4")
        self.assertEqual(old.version, "fm-ad3d6af4f28f5bb7")
        data = {"hazard": hazard, "size": {"SPY|q2|s|d0": 2}, "adverse": "conditional",
                "hazard_adverse": {"SPY|q2|s|d0|k0|t0": 0.12}, "hazard_favourable": {"SPY|q2|s|d0|k0|t0": 0.05, "SPY|q3|s|d0|k0|t0": 2.0}}
        model = F.FillModel.from_json(data, source="x")
        self.assertTrue(model.conditional)
        self.assertEqual(model.hazard_favourable, {"SPY|q2|s|d0|k0|t0": 0.05})              # out of [0, 1]: dropped, as in hazard
        self.assertNotEqual(model.version, old.version)
        self.assertNotEqual(model.version, F.FillModel.from_json(dict(data, hazard_favourable={})).version)
        self.assertNotEqual(F.FillModel(hazard_adverse={}, hazard_favourable={}).version, "natural-only")
        with self.assertRaises(ValueError):
            F.FillModel.from_json(dict(data, adverse="per-leg"))
        with self.assertRaises(ValueError):
            F.FillModel.from_json({k: v for k, v in data.items() if k != "hazard_favourable"})
        with self.assertRaises(ValueError):
            F.FillModel(hazard=hazard, hazard_adverse=hazard)
        path = self.dir / "cond.json"
        path.write_text(json.dumps(data))
        with patch.dict("os.environ", {"GYM_FILL_MODEL": str(path)}):
            self.assertEqual(F.FillModel.load().version, model.version)
        self.assertEqual(F.FillModel.load(path).version, model.version)

    def test_the_cli_keeps_a_conditional_fit_off_the_default_path_until_adopted(self):
        store_dir = self.dir / "walk"
        walk_store(store_dir, varied=True)
        default = self.dir / "gym" / "fill_model.json"
        base = ["--store", str(store_dir), "--roots", "SPY", "--prior", "100", "--min-bucket", "50"]
        with patch.object(CAL, "LAPTOP_OUT", default), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(CAL.main(base + ["--adverse", "conditional"]), 0)
            candidate = default.with_name("fill_model.conditional.json")
            self.assertFalse(default.exists())
            self.assertEqual(candidate.stat().st_mode & 0o777, 0o600)
            self.assertTrue(F.FillModel.load(candidate).conditional)
            self.assertEqual(CAL.main(base + ["--adverse", "conditional", "--out", str(default)]), 2)
            self.assertFalse(default.exists())
            self.assertEqual(CAL.main(base + ["--adverse", "conditional", "--out", str(default), "--adopt"]), 0)
            self.assertTrue(F.FillModel.load(default).conditional)
            self.assertEqual(CAL.main(base), 0)                                  # an unconditional fit: the default, as before
            self.assertFalse(F.FillModel.load(default).conditional)
        with self.assertRaises(ValueError):
            CAL.fit(S.Store(store_dir), ["SPY"], adverse="sometimes")


if __name__ == "__main__":
    unittest.main()
