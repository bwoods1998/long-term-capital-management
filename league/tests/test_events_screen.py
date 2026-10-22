"""The event lane's judge (league.events.screen) against PREREG-EVL-1 section 7, on synthetic data only."""

import datetime as dt
import hashlib
import json
import math
import random
import tempfile
import time
import unittest
from fractions import Fraction
from unittest import mock

from league.tests.evl6_fakes import on_1019h
from league.events import screen as SC
from league.events import store as S

UTC = dt.timezone.utc


def weekdays(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def decided_summary(kind):
    """An `ok` decision receipt's summary as this release's code writes it: every program entering at `kind` named (its
    counts under its key; league.events.screen `names`, release 1019c's review)."""
    from league.events import programs as P

    return {"pending": {}, **{SC.program_key(p.id, p.version): {"planned": 0, "skipped": 0, "known": 0}
                              for p in P.PROGRAMS if p.entry_at == kind}}


def final_record(store, through, *, wall=dt.time(23, 0)):
    """The House's record made FINAL through session `through` (league.events.screen `final_until`, release 1019b): every
    session's open and close decisions `ok` (each receipt naming the programs it decided, as this release's code does:
    `decided_summary`) and every weekday's daily-index backfill done. Returns the moment the screen then runs at
    (`now`): `wall` New York time on `through`."""
    from zoneinfo import ZoneInfo

    days = [str(r["day"]) for r in store.db.execute("SELECT day FROM sessions WHERE day<=? ORDER BY day",
                                                    (through.isoformat(),))]
    for day in days:
        for kind in ("open", "close"):
            rid = store.start_receipt(f"decide-{kind}:{day}")
            store.finish_receipt(rid, "ok", decided_summary(kind))
    d = dt.date.fromisoformat(days[0]) if days else through
    while d <= through:
        if d.weekday() < 5:
            store.set_meta(f"evl:backfill:{d.isoformat()}", "done")
        d += dt.timedelta(days=1)
    return dt.datetime.combine(through, wall, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)


def naive_count(values, seed, draws):
    """The prereg's count written out directly, in exact rationals: bit j of getrandbits(n) set = +1 for value j; a
    vector counts when its mean >= mean(values) - 1e-12."""
    rng = random.Random(seed)
    n = len(values)
    fv = [Fraction(v) for v in values]
    target = sum(fv) / n - Fraction(1e-12)
    count = 0
    for _ in range(draws):
        bits = rng.getrandbits(n)
        if sum(fv[j] if (bits >> j) & 1 else -fv[j] for j in range(n)) / n >= target:
            count += 1
    return count


def event(i, day, a, *, r=None, b=0.0, issuer=None, tradable=True, exit_day=None):
    return {"event": f"8k:{i:06d}", "entry_day": day, "exit_day": exit_day or day, "exited": exit_day or day, "a": a,
            "r": a + b if r is None else r, "b": b, "issuer": issuer or f"{i:010d}", "tradable": tradable}


def strong_rows(days, per_day=4, edge=0.004, seed=1, issuers=None):
    rng = random.Random(seed)
    rows, i = [], 0
    for d in days:
        for _ in range(per_day):
            iss = None if issuers is None else f"{i % issuers:010d}"
            rows.append(event(i, d, rng.gauss(edge, 0.01), b=0.0005, issuer=iss))
            i += 1
    return rows


class SeedsAndSignFlipsTest(unittest.TestCase):
    def test_seed_strings_and_seeds_are_the_prereg_formula(self):
        s = SC.seed_string("EVL-ERN-READ-O1", 1, 3)
        self.assertEqual(s, "EVL-ERN-READ-O1|v1|look3")
        self.assertEqual(SC.look_seed("EVL-ERN-READ-O1", 1, 3),
                         int.from_bytes(hashlib.sha256(s.encode()).digest()[:8], "big"))
        self.assertEqual(SC.seed_of(s + "|issuer|skew"),
                         int.from_bytes(hashlib.sha256((s + "|issuer|skew").encode()).digest()[:8], "big"))

    def test_bit_j_set_is_plus_one_for_value_j(self):
        # One positive value: a vector counts exactly when its bit 0 is set (+1).
        seed = 424242
        rng = random.Random(seed)
        plus = sum(rng.getrandbits(1) for _ in range(500))
        self.assertEqual(SC.signflip_p([0.5], seed, 500), (1 + plus) / 501)
        # [0.01, -0.05] (mean -0.02): the one vector below the mean is (-, +), i.e. bit 0 clear and bit 1 set (0b10);
        # under the reverse convention it would be 0b01, and the stream holds different numbers of the two.
        rng = random.Random(seed)
        draws = [rng.getrandbits(2) for _ in range(500)]
        self.assertNotEqual(draws.count(0b10), draws.count(0b01))
        self.assertEqual(SC.signflip_p([0.01, -0.05], seed, 500), (1 + 500 - draws.count(0b10)) / 501)

    def test_the_table_method_equals_the_naive_method_on_random_inputs(self):
        rng = random.Random(20261019)
        for n in (1, 2, 5, 7, 8, 9, 15, 16, 17, 40, 63, 64, 65, 90, 131):
            for kind in ("gauss", "ties", "tiny"):
                if kind == "gauss":
                    vals = [rng.gauss(0.0005, 0.01) for _ in range(n)]
                elif kind == "ties":  # zeros, repeats and exact cancellations: ties on the nose
                    vals = [rng.choice([0.0, 0.01, -0.01, 0.02, -0.02]) for _ in range(n)]
                else:  # values at the scale of the tie tolerance itself
                    vals = [rng.choice([0.0, 4e-13, -4e-13, 1e-12]) for _ in range(n)]
                seed = rng.getrandbits(64)
                draws = 120 if n > 64 else 300
                self.assertEqual(SC.signflip_p(vals, seed, draws), (1 + naive_count(vals, seed, draws)) / (1 + draws),
                                 (n, kind))

    def test_ties_count_against_the_program_within_1e_12(self):
        self.assertEqual(SC.signflip_p([0.0] * 12, 7, 999), 1.0)  # every vector ties
        # [0.01, 5e-13]: flipping only the second value lowers the mean by 5e-13 < 1e-12, so that vector counts too.
        seed = 99
        rng = random.Random(seed)
        counted = sum(1 for _ in range(999) if rng.getrandbits(2) & 1)
        self.assertEqual(SC.signflip_p([0.01, 5e-13], seed, 999), (1 + counted) / 1000)
        rng = random.Random(seed)
        strict = sum(1 for _ in range(999) if rng.getrandbits(2) == 0b11)
        self.assertEqual(SC.signflip_p([0.01, 5e-11], seed, 999), (1 + strict) / 1000)  # beyond the tolerance

    def test_golden_p_pins_the_stream_on_both_pythons(self):
        vals = [((i * 37) % 23 - 11) / 1000 + 0.0015 for i in range(40)]
        self.assertEqual(SC.signflip_p(vals, SC.look_seed("EVL-ERN-READ-O1", 1, 2)), GOLDEN_P)

    def test_bad_values_are_refused(self):
        with self.assertRaises(ValueError):
            SC.signflip_p([], 1)
        with self.assertRaises(ValueError):
            SC.signflip_p([0.1, float("nan")], 1)


GOLDEN_P = 0.11787  # the same on Python 3.11 and 3.14


class BlocksTest(unittest.TestCase):
    def setUp(self):
        self.days = weekdays(dt.date(2026, 10, 19), 6)

    def test_each_entry_session_is_one_block_of_its_tradable_events(self):
        d = self.days
        rows = [event(1, d[0], 0.01), event(2, d[0], 0.03), event(3, d[0], -0.5, tradable=False),
                event(4, d[1], 0.2, tradable=False), event(5, d[2], 0.4, tradable=None), event(6, d[3], -0.02)]
        got = SC.blocks(rows, d)
        self.assertEqual([(b.index, b.day, b.n) for b in got], [(0, d[0], 2), (3, d[3], 1)])
        self.assertAlmostEqual(got[0].value, 0.02, places=15)
        self.assertEqual(got[1].value, -0.02)

    def test_issuer_values_average_each_issuer_in_ascending_cik_order(self):
        d = self.days
        rows = [event(1, d[0], 0.01, issuer="0000000200"), event(2, d[1], 0.03, issuer="0000000200"),
                event(3, d[0], 0.05, issuer="0000000100"), event(4, d[2], 9.0, issuer="0000000050", tradable=False)]
        self.assertEqual([k for k, _ in SC.issuer_values(rows)], ["0000000100", "0000000200"])
        self.assertAlmostEqual(dict(SC.issuer_values(rows))["0000000200"], 0.02, places=15)

    def test_entry_outside_the_sessions_or_unordered_sessions_are_refused(self):
        with self.assertRaises(ValueError):
            SC.blocks([event(1, dt.date(2026, 10, 18), 0.01)], self.days)
        with self.assertRaises(ValueError):
            SC.blocks([], [self.days[1], self.days[0]])


class LooksTest(unittest.TestCase):
    def setUp(self):
        self.days = weekdays(dt.date(2026, 10, 19), 30)

    def judge(self, rows, program="EVL-ERN-REACT-C1", **kw):
        return SC.judge_look(rows, self.days, 4, program=program, version=1, at="2026-11-30T21:00:00Z", draws=9999, **kw)

    def test_schedule_and_minimums(self):
        self.assertEqual(SC.look_schedule(), [(1, 10), (2, 15), (3, 20), (4, 30), (5, 40), (6, 60), (7, 90)])
        self.assertEqual((SC.look_number(20), SC.look_number(21)), (3, None))
        self.assertEqual(SC.minimums(60, 40, 10), (True, "held"))
        self.assertIn("tradable events 59 < 60", SC.minimums(59, 40, 10)[1])
        self.assertIn("issuers 39 < 40", SC.minimums(60, 39, 10)[1])
        self.assertIn("blocks 9 < 10", SC.minimums(60, 40, 9)[1])

    def test_a_strong_edge_passes_and_the_row_carries_the_judged_figures(self):
        rows = strong_rows(self.days)
        look = self.judge(rows)
        self.assertEqual((look["held"], look["passed"], look["why"]), (1, 1, "pass"), look["why"])
        self.assertEqual((look["n"], look["issuers"], look["blocks"], look["sessions"]), (120, 120, 30, 30))
        self.assertEqual(look["mean_a"], look["mean_a_tradable"])
        self.assertLessEqual(look["p"], look["alpha"])
        self.assertLessEqual(look["issuer"]["p"], look["issuer"]["alpha"])
        self.assertEqual(set(look["skew"]), {"session", "issuer"})
        self.assertEqual(look["skew"]["issuer"]["seed"], "EVL-ERN-REACT-C1|v1|look4|issuer")

    def test_untradable_events_never_enter_the_judged_figures(self):
        rows = [dict(r, a=0.0 + (r["a"] - 0.004) * 0.001, r=0.0) for r in strong_rows(self.days)]
        rows += [event(10_000 + i, d, 0.5, tradable=False) for i, d in enumerate(self.days)]
        look = self.judge(rows)
        self.assertEqual(look["n"], 120)
        self.assertEqual(look["beside"]["all"]["n"], 150)
        self.assertEqual(look["passed"], 0)

    def test_mean_r_must_be_positive(self):
        rows = [dict(r, r=-0.001, b=-0.001 - r["a"]) for r in strong_rows(self.days)]
        look = self.judge(rows)
        self.assertEqual(look["passed"], 0)
        self.assertIn("mean r <= 0", look["why"])

    def test_the_issuer_block_test_must_pass_too(self):
        # One issuer carries the edge in every session; the other 90 are flat noise: every session block is up, but
        # one value among the issuers is no evidence.
        rng = random.Random(5)
        rows, i = [], 0
        for d in self.days:
            rows.append(event(i, d, 0.05, issuer="0000000001"))
            i += 1
            for _ in range(3):
                rows.append(event(i, d, rng.gauss(-0.002, 0.002), issuer=f"{1000 + i:010d}"))
                i += 1
        look = self.judge(rows)
        self.assertLessEqual(look["p"], look["alpha"])
        self.assertGreater(look["issuer"]["p"], look["issuer"]["alpha"])
        self.assertEqual(look["passed"], 0)
        self.assertIn("issuer p", look["why"])

    def test_a_read_program_must_beat_its_control_over_the_same_sessions(self):
        rows = strong_rows(self.days)
        better = [dict(r, event=r["event"] + "c", a=r["a"] + 0.01) for r in rows]
        look = self.judge(rows, program="EVL-ERN-READ-O1", control_rows=better)
        self.assertEqual(look["passed"], 0)
        self.assertIn("<= control", look["why"])
        self.assertEqual(look["control"]["program"], "EVL-CTRL-ERN-ALL-O1")
        look = self.judge(rows, program="EVL-ERN-READ-O1", control_rows=[])
        self.assertIn("no EVL-CTRL-ERN-ALL-O1 block", look["why"])
        worse = [dict(r, event=r["event"] + "c", a=r["a"] - 0.01) for r in rows]
        self.assertEqual(self.judge(rows, program="EVL-ERN-READ-O1", control_rows=worse)["passed"], 1)

    def test_a_look_short_of_a_minimum_is_skipped_without_a_test(self):
        look = self.judge(strong_rows(self.days[:12]))  # 48 tradable events
        self.assertEqual((look["held"], look["passed"], look["p"], look["fp_check"]), (0, 0, None, None))
        self.assertIn("tradable events 48 < 60", look["why"])

    def test_the_skew_checks_are_recorded_before_any_p_is_computed(self):
        seen = []
        real = SC.signflip_p

        def spy(values, seed, B=SC.B):  # noqa: N803
            seen.append(("p", bool(recorded)))
            return real(values, seed, B)
        recorded = []
        with mock.patch.object(SC, "signflip_p", spy):
            look = self.judge(strong_rows(self.days), record=recorded.append)
        self.assertEqual(len(recorded), 1)
        self.assertTrue(seen and all(flag for _, flag in seen))
        self.assertEqual(look["skew"], recorded[0])

    def test_checks_on_record_are_reused_for_the_same_values_only_and_never_loosen_the_threshold(self):
        rows = strong_rows(self.days)
        first = self.judge(rows)
        recorded = []
        again = self.judge(rows, alphas=first["skew"], record=recorded.append)
        self.assertEqual((again["p"], again["alpha"], again["passed"], recorded), (first["p"], first["alpha"],
                                                                                    first["passed"], []))
        # A check run on other values (a backfilled event joined the look's blocks since) is run again and recorded.
        other = self.judge(rows[:-1], alphas=first["skew"], record=recorded.append)
        self.assertEqual(len(recorded), 1)
        self.assertEqual(other["skew"], recorded[0])
        loose = {"session": dict(first["skew"]["session"], alpha=0.03), "issuer": first["skew"]["issuer"]}
        with self.assertRaises(ValueError):
            self.judge(rows, alphas=loose)

    def test_a_look_is_written_once_and_never_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = S.Store(tmp)
            look = self.judge(strong_rows(self.days))
            self.assertTrue(SC.write_look(st, look))
            self.assertFalse(SC.write_look(st, dict(look, passed=0, why="changed")))
            row = st.db.execute("SELECT passed, why FROM looks").fetchone()
            self.assertEqual((row["passed"], row["why"]), (1, "pass"))
            detail = SC.look_detail(st, "EVL-ERN-REACT-C1", 1, 4)
            self.assertEqual(detail["issuer"]["alpha"], look["issuer"]["alpha"])
            st.close()


class SkewCheckTest(unittest.TestCase):
    def test_it_follows_the_prereg_seeds_and_sampling(self):
        # The check recomputed directly: centred values, indices r.randrange(n) from "<seed>|skew", one shared set of
        # sign vectors from "<seed>|skewflip", f = share with mean > 0 and p <= alpha.
        rng = random.Random(4)
        vals = [rng.gauss(0.001, 0.01) for _ in range(23)]
        text = "EVL-8K-READ-O1|v1|look2"
        got = SC.skew_check(vals, text, samples=60, draws=199)
        centre = math.fsum(vals) / len(vals)
        centred = [v - centre for v in vals]
        r = random.Random(SC.seed_of(text + "|skew"))
        flip_seed = SC.seed_of(text + "|skewflip")
        counts = []
        for _ in range(60):
            x = [centred[r.randrange(len(vals))] for _ in range(len(vals))]
            if sum(Fraction(v) for v in x) > 0:
                counts.append(naive_count(x, flip_seed, 199))
        f = sum(1 for c in counts if (1 + c) / 200 <= got["alpha"]) / 60
        self.assertEqual(got["f"], f)
        start = sum(1 for c in counts if (1 + c) / 200 <= 0.024) / 60
        self.assertEqual(got["f_start"], start)

    def test_left_skewed_blocks_lower_the_threshold_to_its_floor_and_it_only_tightens(self):
        pennies = [0.01] * 27 + [-0.09] * 3
        got = SC.skew_check(pennies, "EVL-ERN-READ-O1|v1|look2")
        self.assertGreater(got["f_start"], 0.024)
        self.assertEqual(got["alpha"], 0.002)  # the floor, even with f still above 0.024 there
        for a, f in got["f_by_alpha"].items():
            self.assertLessEqual(float(a), 0.024)
        lower = SC.skew_check(pennies, "EVL-ERN-READ-O1|v1|look2", alpha=0.01)
        self.assertLessEqual(lower["alpha"], 0.01)

    def test_right_skewed_blocks_keep_the_threshold(self):
        right = [-0.002] * 27 + [0.018] * 3
        got = SC.skew_check(right, "EVL-ERN-READ-O1|v1|look2")
        self.assertLessEqual(got["f_start"], 0.024)
        self.assertEqual((got["alpha"], got["f"]), (0.024, got["f_start"]))

    def test_it_is_deterministic(self):
        rng = random.Random(9)
        vals = [rng.gauss(0, 0.01) for _ in range(40)]
        self.assertEqual(SC.skew_check(vals, "X|v1|look1")["f_by_alpha"], SC.skew_check(vals, "X|v1|look1")["f_by_alpha"])


class BootstrapTest(unittest.TestCase):
    def test_two_issuers_have_an_enumerable_bootstrap(self):
        rows = [{"issuer": "A", "entry_day": dt.date(2026, 10, 19), "r": 0.0},
                {"issuer": "B", "entry_day": dt.date(2026, 10, 20), "r": 1.0}]
        two = SC.bootstrap_bounds(rows, "issuer", 0.95, 4000, 1)
        self.assertEqual((two["lower"], two["upper"], two["groups"], two["mean"]), (0.0, 1.0, 2, 0.5))
        one = SC.bootstrap_bounds(rows, "session", 0.95, 4000, 1, sided="one")
        self.assertEqual((one["lower"], one["upper"]), (0.0, 1.0))

    def test_issuer_blocks_are_wider_when_one_issuer_carries_the_mean(self):
        day = dt.date(2026, 10, 19)
        rows = [{"issuer": "BIG", "entry_day": day + dt.timedelta(days=i % 30), "r": 0.03} for i in range(30)]
        rows += [{"issuer": f"I{i}", "entry_day": day + dt.timedelta(days=i % 30), "r": -0.001} for i in range(60)]
        iss = SC.bootstrap_bounds(rows, "issuer", 0.95, 3000, 2)
        ses = SC.bootstrap_bounds(rows, "session", 0.95, 3000, 2)
        self.assertLess(iss["lower"], ses["lower"])
        self.assertGreater(ses["lower"], 0)

    def test_done_kill_and_sized(self):
        rng = random.Random(3)
        day = dt.date(2026, 10, 19)
        good = [{"issuer": f"I{i % 120}", "entry_day": day + dt.timedelta(days=i % 60), "r": rng.gauss(0.004, 0.01)}
                for i in range(400)]
        bad = [dict(r, r=-r["r"]) for r in good]
        self.assertTrue(SC.done_bounds(good, n=2000)["ok"])
        self.assertFalse(SC.done_bounds(bad, n=2000)["ok"])
        self.assertTrue(SC.kill_bounds(bad, n=2000)["kill"])
        self.assertFalse(SC.kill_bounds(good, n=2000)["kill"])
        self.assertEqual(SC.kill_bounds(bad, n=500)["issuer"]["sided"], "one")
        self.assertTrue(SC.sized_bound(good, n=2000)["ok"])
        shuffled = list(good)
        random.Random(1).shuffle(shuffled)
        self.assertEqual(SC.done_bounds(shuffled, n=500), SC.done_bounds(good, n=500))


class CalibrationTest(unittest.TestCase):
    """Slow (about 10-20 s a Python): the family false-positive rate of a zero-edge program at alpha 0.024."""

    def test_family_false_positive_rate_is_in_the_prereg_range(self):
        started = time.perf_counter()
        script = SC.calibration(400, 6.0, 20261019, rule="script", draws=1999)
        prereg = SC.calibration(400, 6.0, 20261019, rule="prereg", draws=1999)
        # The prereg: 8.6% (script, 5,000 runs) and 8.3% (section 7 with the skew check); 400 runs: about +/-1.4%.
        self.assertGreaterEqual(script["fp"], 0.04)
        self.assertLessEqual(script["fp"], 0.14)
        self.assertGreaterEqual(prereg["fp"], 0.03)
        self.assertLessEqual(prereg["fp"], 0.14)
        self.assertLess(time.perf_counter() - started, 30)

    def test_the_null_draws_have_their_moments(self):
        rng = random.Random(11)
        for lam in (0.5, 6.0, 40.0, 150.0):
            xs = [SC._poisson(rng, lam) for _ in range(20000)]
            mean = sum(xs) / len(xs)
            var = sum((x - mean) ** 2 for x in xs) / len(xs)
            self.assertAlmostEqual(mean / lam, 1.0, delta=0.03 if lam > 1 else 0.05)
            self.assertAlmostEqual(var / lam, 1.0, delta=0.08)
        ts = [SC._t4(rng) for _ in range(40000)]
        tail = sum(1 for t in ts if abs(t) > 2.776445) / len(ts)  # t(4)'s two-sided 5% point
        self.assertAlmostEqual(tail, 0.05, delta=0.006)


@on_1019h
class ScreenJobTest(unittest.TestCase):
    """The job on a synthetic store: C1 (close to next close) and a READ program with its control."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        self.days = weekdays(dt.date(2026, 10, 19), 70)
        with self.st.tx() as db:
            for d in self.days:
                close = dt.datetime.combine(d, dt.time(16, 0), tzinfo=dt.timezone(dt.timedelta(hours=-5)))
                db.execute("INSERT INTO sessions(day, open_at, close_at, early) VALUES(?, ?, ?, 0)",
                           (d.isoformat(), S.iso(close - dt.timedelta(hours=6, minutes=30)), S.iso(close)))

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def add(self, program, i, entry, exit_, a, *, status="exited", settle=True, tradable=1, cik=None):
        with self.st.tx() as db:
            db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, exit_day, "
                       "exit_at, mode, status) VALUES(?, 1, ?, ?, ?, ?, ?, 'close', ?, 'close', 'shadow', ?)",
                       (program, f"8k:{i}", f"S{i % 300}", cik or f"{i % 300:010d}", f"{entry.isoformat()}T19:46:00Z",
                        entry.isoformat(), exit_.isoformat(), status))
            if settle:
                db.execute("INSERT INTO outcomes(program, version, event, r, b, a, tradable, settled_at, status) "
                           "VALUES(?, 1, ?, ?, 0.0005, ?, ?, '2026-12-31T00:00:00Z', 'settled')",
                           (program, f"8k:{i}", a + 0.0005, a, tradable))

    def fill(self, program, sessions, per_day=6, edge=0.004, offset=0):
        rng = random.Random(offset + 1)
        i = offset
        for j in range(sessions):
            for _ in range(per_day):
                self.add(program, i, self.days[j], self.days[j + 1], rng.gauss(edge, 0.01))
                i += 1
        return i

    def test_looks_are_dated_from_the_first_settled_exit_and_written_once(self):
        self.fill("EVL-ERN-REACT-C1", 40, per_day=5)  # entries on days 0..39 at the close, exits on days 1..40
        now = final_record(self.st, self.days[45])
        out = SC.run(self.st, self.days[45], draws=999, now=now)
        ks = [w["k"] for w in out["written"]]
        # Session 1 is day 1 (the first settled exit), so looks 1..5 are as of days 10, 15, 20, 30 and 40.
        self.assertEqual(ks, [1, 2, 3, 4, 5])
        rows = {r["k"]: r for r in SC.look_rows(self.st, "EVL-ERN-REACT-C1", 1)}
        self.assertEqual(rows[1]["at"], "2026-11-02T21:00:00Z")
        self.assertEqual((rows[1]["held"], rows[1]["blocks"]), (0, 10))  # entries on days 0..9 exit by day 10
        self.assertIn("tradable events 50 < 60", rows[1]["why"])
        self.assertEqual((rows[2]["held"], rows[2]["blocks"], rows[2]["n"]), (1, 15, 75))
        rec = SC.skew_records(self.st, "EVL-ERN-REACT-C1", 1, 2)
        self.assertEqual(set(rec), {"session", "issuer", "at"})
        self.assertEqual(rows[2]["fp_check"], rec["session"]["f"])
        again = SC.run(self.st, self.days[45], draws=999, now=now)
        self.assertEqual(again["written"], [])
        self.assertEqual(SC.next_look(self.st, "EVL-ERN-REACT-C1", 1, self.days[45])["k"], 6)

    def test_a_look_waits_for_every_scheduled_exit_and_counts_a_fallback_exit_where_it_was_scheduled(self):
        n = self.fill("EVL-ERN-REACT-C1", 20)
        self.add("EVL-ERN-REACT-C1", n, self.days[5], self.days[6], 0.0, status="entered", settle=False)
        now = final_record(self.st, self.days[25])
        out = SC.run(self.st, self.days[25], draws=999, now=now)
        self.assertEqual(out["written"], [])
        self.assertEqual(out["waiting"][0]["k"], 1)
        # It settles three sessions late (a fallback exit): the look as of day 10 covers its block all the same.
        with self.st.tx() as db:
            db.execute("UPDATE intents SET status='exited' WHERE event=?", (f"8k:{n}",))
            db.execute("INSERT INTO outcomes(program, version, event, r, b, a, tradable, settled_at, status) "
                       "VALUES('EVL-ERN-REACT-C1', 1, ?, 0.0, 0.0, -0.5, 1, '2026-12-31T00:00:00Z', 'settled')", (f"8k:{n}",))
            db.execute("INSERT INTO meta(key, value) VALUES(?, ?)", (f"exit:EVL-ERN-REACT-C1:1:8k:{n}",
                                                                     json.dumps({"day": self.days[9].isoformat(),
                                                                                 "kind": "close",
                                                                                 "planned": self.days[6].isoformat()})))
        out = SC.run(self.st, self.days[25], draws=999, now=now)
        self.assertEqual([w["k"] for w in out["written"]], [1, 2, 3])
        first = SC.look_rows(self.st, "EVL-ERN-REACT-C1", 1)[0]
        self.assertEqual(first["n"], 10 * 6 + 1)

    def test_a_read_program_reads_its_control_and_records_are_never_screened(self):
        n = self.fill("EVL-ERN-READ-O1", 40, edge=0.004)
        self.fill("EVL-CTRL-ERN-ALL-O1", 40, edge=0.0, offset=n)
        self.fill("EVL-ERN-READ-O3", 40, edge=0.004, offset=2 * n)
        out = SC.run(self.st, self.days[45], draws=999, now=final_record(self.st, self.days[45]))
        self.assertTrue(out["written"])
        self.assertTrue(all(w["program"] == "EVL-ERN-READ-O1" for w in out["written"]))
        detail = SC.look_detail(self.st, "EVL-ERN-READ-O1", 1, 2)
        self.assertEqual(detail["control"]["program"], "EVL-CTRL-ERN-ALL-O1")
        self.assertGreater(detail["control"]["blocks"], 0)
        self.assertEqual(SC.next_look(self.st, "EVL-ERN-READ-O3", 1, self.days[45])["k"], None)

    def test_expected_false_passes_count_every_seatable_version(self):
        # PREREG-EVL-3's nine version 2 rows and PREREG-EVL-4's three (their version 1), of the lane's stated 3.0
        # (PREREG-EVL-5, release 1019g: its three seatable programs at version 1 too, 1.5 of the stated 3.0)
        efp = SC.expected_false_passes(self.st)     # (release 1019i: PREREG-EVL-6 section 5 restates the count, 0.13 a version or run of 3.9)
        self.assertEqual({k: efp[k] for k in ("versions", "expected", "budget", "left")},
                         {"versions": 15, "expected": 1.95, "budget": 3.9, "left": 1.95})
        with self.st.tx() as db:
            db.execute("INSERT INTO intents(program, version, event, symbol, decided_at, entry_day, entry_at, exit_day, "
                       "exit_at, mode, status) VALUES('EVL-8K-READ-O1', 3, 'x', 'S', 'z', '2026-10-19', 'open', "
                       "'2026-10-19', 'close', 'shadow', 'planned')")
        self.assertEqual(SC.expected_false_passes(self.st)["versions"], 16)
        with self.st.tx() as db:     # a later version of a PREREG-EVL-4 id is one above its seating version 1
            db.execute("INSERT INTO intents(program, version, event, symbol, decided_at, entry_day, entry_at, exit_day, "
                       "exit_at, mode, status) VALUES('EVL-8K-REACT-ON', 2, 'x', 'S', 'z', '2026-10-20', 'close', "
                       "'2026-10-21', 'open', 'shadow', 'planned')")
        self.assertEqual(SC.expected_false_passes(self.st)["versions"], 17)


# PREREG-EVL-7 (A125 pinned REGISTERED_AT_7): this module's tests are of mechanisms written before the learners
# registered and run on the registries without them (league/tests/evl7_fakes.py); the learners' own effects on these
# paths are league/tests/test_events_evl7.py's and test_events_evl7_fix.py's.
from league.tests.evl7_fakes import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
