"""THE FORWARD METERS' ARITHMETIC (release E3; league/ops/forward_stats.py): each pre-registered formula of the spec's
section 4 that package C owns, checked against a hand value or a seeded construction whose true answer is known.

- D3's excess (x = r - w * b, daily; not the screen's window-mean excess), D4's t and its one-sided p;
- D6's N_eff: pairwise-overlap correlations, each rho^2 adjusted for its sample size, summed unfloored, and the
  unadjusted participation ratio stored beside (`neff_raw`), which falls when short-history members are born;
- D7's independent years and the replay multiple; D8's BH and BY counts; D9's read of a pair.

Every series here is drawn from a seeded generator or written by hand: no market data, no figure of any program.
The exact statistics (`math.fsum`) are compared to the last digits a hand value carries; anything that goes through a
numpy product is compared within a stated tolerance (CI runs Python 3.11 and 3.14, on two numpy builds)."""

from __future__ import annotations

import math
import unittest

import numpy as np

from league.ops import forward_db
from league.ops import forward_stats as FS


def independent(rng: np.random.Generator, members: int, sessions: int) -> np.ndarray:
    return rng.standard_normal((members, sessions))


def short(rng: np.random.Generator, width: int, lengths: list[int]) -> np.ndarray:
    """Members born late: row i has its last `lengths[i]` sessions, NaN before."""
    out = np.full((len(lengths), width), np.nan)
    for i, n in enumerate(lengths):
        out[i, width - n:] = rng.standard_normal(n)
    return out


class TheExcess(unittest.TestCase):
    def test_it_is_r_less_exposure_times_the_benchmark_day_by_day(self):
        r, w, b = [0.010, -0.004, 0.0], [0.5, 1.0, 0.0], [0.020, -0.010, 0.030]
        x = FS.excess(r, w, b)
        self.assertEqual(x.dtype, np.float64)
        self.assertEqual(x.tolist(), [0.010 - 0.5 * 0.020, -0.004 - 1.0 * -0.010, 0.0])
        # NOT the screen's excess: no window mean is subtracted, so a flat day's excess is exactly zero.
        self.assertEqual(x[2], 0.0)
        self.assertNotAlmostEqual(float(x.mean()), 0.0)

    def test_three_series_of_one_length(self):
        with self.assertRaises(ValueError):
            FS.excess([0.0, 0.1], [1.0], [0.0, 0.0])
        with self.assertRaises(ValueError):
            FS.excess([[0.0]], [[1.0]], [[0.0]])


class TheTAndItsP(unittest.TestCase):
    def test_t_is_the_mean_over_the_sample_sd_times_root_n(self):
        # mean 2.5; sd (ddof 1) = sqrt(5/3); t = 2.5 / sqrt(5/3) * 2
        self.assertAlmostEqual(FS.t_stat([1.0, 2.0, 3.0, 4.0]), 2.5 / math.sqrt(5.0 / 3.0) * 2.0, places=12)
        self.assertAlmostEqual(FS.t_stat(np.array([0.01, -0.01, 0.03])), 0.01 / 0.02 * math.sqrt(3.0), places=12)
        self.assertLess(FS.t_stat([-1.0, -2.0, -4.0]), 0.0)

    def test_t_is_none_without_two_finite_days_or_a_variance(self):
        self.assertIsNone(FS.t_stat([]))
        self.assertIsNone(FS.t_stat([0.01]))
        self.assertIsNone(FS.t_stat([0.0] * 20), "a program that never traded has no t")
        self.assertIsNone(FS.t_stat([0.01, 0.01 + 1e-14, 0.01]), "sd under 1e-12")
        self.assertIsNone(FS.t_stat([0.01, float("nan"), 0.02]))
        self.assertIsNone(FS.t_stat([0.01, float("inf"), 0.02]))
        with self.assertRaises(ValueError):
            FS.t_stat([[0.01, 0.02], [0.03, 0.04]])

    def test_the_sums_are_exact(self):
        # The built-in sum loses the 1.0 on Python 3.11 (1e16 + 1.0 == 1e16); math.fsum does not.
        read = FS.rc_read([1e16, 1.0, -1e16], [0.0, 0.0, 0.0])
        self.assertEqual(read["mean_bp"], 1.0 / 3.0 * 1e4)

    def test_p_at_t_zero_is_one_half_and_the_tails_mirror(self):
        for n in (2, 3, 20, 60, 250, 5000):
            self.assertEqual(FS.p_one_sided(0.0, n), 0.5)
            for t in (0.3, 1.0, 2.5):
                self.assertAlmostEqual(FS.p_one_sided(t, n) + FS.p_one_sided(-t, n), 1.0, places=13)
                self.assertLess(FS.p_one_sided(t, n), 0.5)

    def test_p_against_the_closed_forms_of_one_two_and_three_degrees_of_freedom(self):
        for t in (0.1, 0.5, 1.0, 2.0, 6.0, 40.0):
            one = 0.5 - math.atan(t) / math.pi                                   # Cauchy
            two = 0.5 - t / (2.0 * math.sqrt(2.0 + t * t))
            u = t / math.sqrt(3.0)
            three = 0.5 - (u / (1.0 + u * u) + math.atan(u)) / math.pi
            self.assertAlmostEqual(FS.p_one_sided(t, 2), one, places=12)
            self.assertAlmostEqual(FS.p_one_sided(t, 3), two, places=12)
            self.assertAlmostEqual(FS.p_one_sided(t, 4), three, places=12)

    def test_p_against_known_critical_values(self):
        # The textbook one-sided critical values of Student's t.
        for t, n, p in ((1.729133, 20, 0.05), (2.093024, 20, 0.025), (2.539483, 20, 0.01), (1.671093, 60, 0.05),
                        (2.000995, 60, 0.025), (1.657759, 120, 0.05), (1.969498, 251, 0.025)):
            self.assertAlmostEqual(FS.p_one_sided(t, n), p, places=6, msg=f"t {t} n {n}")

    def test_p_nears_the_normal_tail_for_a_long_record(self):
        for t in (0.5, 1.96, 3.0):
            self.assertAlmostEqual(FS.p_one_sided(t, 2_000_001), 0.5 * math.erfc(t / math.sqrt(2.0)), places=6)

    def test_p_falls_as_t_rises_and_is_none_when_unreadable(self):
        ps = [FS.p_one_sided(t / 4.0, 60) for t in range(-20, 21)]
        self.assertEqual(ps, sorted(ps, reverse=True))
        self.assertTrue(all(0.0 <= p <= 1.0 for p in ps))
        self.assertIsNone(FS.p_one_sided(None, 60))
        self.assertIsNone(FS.p_one_sided(1.0, 1))
        self.assertIsNone(FS.p_one_sided(float("nan"), 60))
        self.assertIsNone(FS.p_one_sided("high", 60))
        self.assertEqual((FS.p_one_sided(float("inf"), 60), FS.p_one_sided(float("-inf"), 60)), (0.0, 1.0))

    def test_a_checkpoints_p_is_the_p_of_its_t(self):
        # D4 as the forward shadow uses the pair: p_x = p_one_sided(t_x, n) over the first n counted days.
        rng = np.random.default_rng(11)
        x = FS.excess(rng.normal(0.001, 0.01, 60), np.full(60, 0.5), rng.normal(0.0, 0.01, 60))
        t = FS.t_stat(x)
        self.assertAlmostEqual(t, float(x.mean() / x.std(ddof=1) * math.sqrt(60)), places=9)
        self.assertTrue(0.0 < FS.p_one_sided(t, 60) < 1.0)


class ThePairwiseCorrelations(unittest.TestCase):
    def test_a_pair_reads_its_overlap_only(self):
        rng = np.random.default_rng(3)
        old = rng.standard_normal(60)
        young = np.full(60, np.nan)
        young[40:] = 2.0 * old[40:] + 5.0                    # the same days exactly: rho 1 on the overlap
        other = np.full(60, np.nan)
        other[45:] = -old[45:]
        rho, n = FS.pairwise_corr(np.vstack([old, young, other]))
        self.assertEqual(n.tolist(), [[60, 20, 15], [20, 20, 15], [15, 15, 15]])
        self.assertAlmostEqual(rho[0, 1], 1.0, places=12)
        self.assertAlmostEqual(rho[0, 2], -1.0, places=12)
        self.assertAlmostEqual(rho[1, 2], -1.0, places=12)
        self.assertTrue(np.array_equal(rho, rho.T))
        self.assertEqual(np.diag(rho).tolist(), [1.0, 1.0, 1.0])
        # Over the old member's whole record the pair is far from 1: the overlap is what is read.
        full = np.corrcoef(old[40:], young[40:])[0, 1]
        self.assertAlmostEqual(rho[0, 1], full, places=12)

    def test_it_is_pearsons_on_each_pairs_last_common_sessions(self):
        rng = np.random.default_rng(5)
        X = np.vstack([independent(rng, 3, 60), short(rng, 60, [33, 12, 12, 47])])
        rho, n = FS.pairwise_corr(X)
        lengths = [60, 60, 60, 33, 12, 12, 47]
        for i in range(7):
            for j in range(7):
                k = min(lengths[i], lengths[j])
                self.assertEqual(n[i, j], k)
                want = 1.0 if i == j else np.corrcoef(X[i, 60 - k:], X[j, 60 - k:])[0, 1]
                self.assertAlmostEqual(rho[i, j], want, places=10, msg=f"{i},{j}")

    def test_no_variance_reads_zero(self):
        rng = np.random.default_rng(7)
        flat = np.zeros(30)
        late = np.concatenate([rng.standard_normal(20), np.full(10, 0.25)])   # variance, but none in its last 10
        young = np.full(30, np.nan)
        young[20:] = rng.standard_normal(10)
        absent = np.full(30, np.nan)
        rho, n = FS.pairwise_corr(np.vstack([rng.standard_normal(30), flat, late, young, absent]))
        self.assertEqual(rho[0, 1], 0.0)
        self.assertEqual(rho[2, 3], 0.0, "no variance over the pair's last 10 sessions")
        self.assertNotEqual(rho[0, 2], 0.0)
        self.assertEqual((rho[0, 4], n[0, 4], n[4, 4]), (0.0, 0, 0))
        self.assertTrue(np.all(np.abs(rho) <= 1.0))

    def test_the_rows_are_one_array(self):
        with self.assertRaises(ValueError):
            FS.pairwise_corr([0.0, 1.0, 2.0])


class TheEffectiveNumber(unittest.TestCase):
    def test_identical_series_read_one(self):
        rng = np.random.default_rng(1)
        one = rng.standard_normal(60)
        out = FS.neff(np.tile(one, (25, 1)))
        self.assertEqual((out["members"], out["n_w"]), (25, 60))
        self.assertAlmostEqual(out["neff"], 1.0, places=9)
        self.assertAlmostEqual(out["neff_raw"], 1.0, places=9)

    def test_two_hundred_independent_members_over_sixty_sessions_read_two_hundred(self):
        rng = np.random.default_rng(2)
        out = FS.neff(independent(rng, 200, 60))
        self.assertEqual(out["members"], 200)
        self.assertLessEqual(abs(out["neff"] - 200.0), 20.0, out)     # within 10%
        self.assertLessEqual(out["neff"], 200.0, "never above the member count")
        # The unadjusted ratio is capped near the window length: why it is stored and never used.
        self.assertLess(out["neff_raw"], 60.0)

    def test_adding_independent_short_history_members_never_lowers_it(self):
        # The spec's seeded case: 80 members of 60 sessions, then 40 more of 10 to 29 sessions each.
        rng = np.random.default_rng(4)
        base = independent(rng, 80, 60)
        late = short(rng, 60, [10 + (7 * i) % 20 for i in range(40)])
        before, after = FS.neff(base), FS.neff(np.vstack([base, late]))
        self.assertEqual((before["members"], after["members"]), (80, 120))
        self.assertGreaterEqual(after["neff"], before["neff"], "the births lowered N_eff")
        self.assertGreater(after["neff"], before["neff"] + 20.0, "the births add evidence")
        # The unadjusted ratio FALLS on the same births (the first formula's defect, measured in the spec's D6).
        self.assertLess(after["neff_raw"], before["neff_raw"])

    def test_births_never_lower_it_whatever_the_draw(self):
        # The adjusted rho^2 is unbiased, not noise-free: ONE member of ten sessions can move the sum either way by
        # its own sampling noise, so the claim is about births in number (20 or more here, on every one of 40 draws)
        # and about the mean effect of a single birth, which is to raise it.
        one = []
        for seed in range(40):
            rng = np.random.default_rng([17, seed])
            base = independent(rng, 80, 60)
            late = short(rng, 60, [10 + (7 * i) % 20 for i in range(40)])
            before = FS.neff(base)["neff"]
            for k in (20, 30, 40):
                self.assertGreaterEqual(FS.neff(np.vstack([base, late[:k]]))["neff"], before, f"seed {seed}, {k} births")
            one.append(FS.neff(np.vstack([base, late[:1]]))["neff"] - before)
        self.assertGreater(math.fsum(one) / len(one), 0.0, "a birth raises N_eff in the mean")

    def test_twenty_clusters_of_ten_near_clones_read_the_clusters_true_number(self):
        rng = np.random.default_rng(6)
        rho = 0.9                                                       # a clone's correlation with its cluster mates
        rows = []
        for _ in range(20):
            common = rng.standard_normal(60)
            for _ in range(10):
                rows.append(math.sqrt(rho) * common + math.sqrt(1.0 - rho) * rng.standard_normal(60))
        truth = 200.0 ** 2 / (200.0 + 20 * 10 * 9 * rho ** 2)           # the formula at the population's rho: 24.1
        self.assertAlmostEqual(truth, 24.1, places=1)
        out = FS.neff(np.vstack(rows))
        self.assertEqual(out["members"], 200)
        self.assertLessEqual(abs(out["neff"] - truth), 0.10 * truth, out)

    def test_the_formula_by_hand_and_the_unadjusted_ratio_beside(self):
        rng = np.random.default_rng(8)
        X = np.vstack([independent(rng, 6, 40), short(rng, 40, [25, 12])])
        rho, n = FS.pairwise_corr(X)
        off = ~np.eye(8, dtype=bool)
        adjusted = 1.0 - (1.0 - rho[off] ** 2) * (n[off] - 1.0) / (n[off] - 2.0)
        out = FS.neff(X)
        self.assertAlmostEqual(out["neff"], min(8.0, 64.0 / (8.0 + max(0.0, float(adjusted.sum())))), places=9)
        self.assertAlmostEqual(out["neff_raw"], 64.0 / float((rho ** 2).sum()), places=9)   # rho_ii = 1 inside the sum
        self.assertTrue((adjusted < 0).any(), "a single adjusted rho^2 may be negative: the sum is taken unfloored")

    def test_a_negative_sum_is_floored_at_zero_so_it_never_passes_the_member_count(self):
        # Two members whose sample correlation is nearly 0: the adjusted rho^2 is below zero, N_eff is N, not more.
        a = np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
        b = np.array([1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, -1.0])
        out = FS.neff(np.vstack([a, b]))
        self.assertEqual((out["members"], out["neff"]), (2, 2.0))

    def test_membership(self):
        rng = np.random.default_rng(9)
        X = np.vstack([independent(rng, 4, 30), short(rng, 30, [9]),          # nine sessions: not yet a member
                       np.zeros((1, 30)),                                      # no variance: never a member
                       short(rng, 30, [10])])
        broken = rng.standard_normal(30)
        broken[25] = np.nan                                                    # its run ending today is 4 sessions
        out = FS.neff(np.vstack([X, broken]))
        self.assertEqual((out["members"], out["n_w"]), (5, 30))
        self.assertEqual(FS.neff(X, min_days=9)["members"], 6)
        self.assertEqual(forward_db.NEFF_MIN_DAYS, 10)

    def test_under_two_members_and_under_the_minimum_window(self):
        rng = np.random.default_rng(10)
        self.assertEqual(FS.neff(independent(rng, 50, 9)), {"members": 0, "n_w": 9, "neff": 0.0, "neff_raw": None})
        self.assertEqual(FS.neff(np.empty((0, 30))), {"members": 0, "n_w": 30, "neff": 0.0, "neff_raw": None})
        self.assertEqual(FS.neff(independent(rng, 1, 30)), {"members": 1, "n_w": 30, "neff": 1.0, "neff_raw": 1.0})
        with self.assertRaises(ValueError):
            FS.neff(independent(rng, 3, 30), min_days=2)

    def test_the_draws_order_does_not_move_it(self):
        rng = np.random.default_rng(12)
        X = np.vstack([independent(rng, 30, 60), short(rng, 60, [15, 22, 40, 11])])
        a, b = FS.neff(X), FS.neff(X[::-1])
        self.assertAlmostEqual(a["neff"], b["neff"], places=9)
        self.assertAlmostEqual(a["neff_raw"], b["neff_raw"], places=9)


class TheAnyEdgeAnywhereCounts(unittest.TestCase):
    def test_an_all_null_family_rejects_none(self):
        ps = [0.11, 0.2, 0.35, 0.5, 0.62, 0.7, 0.81, 0.9, 0.95, 1.0]
        self.assertEqual((FS.bh(ps), FS.by(ps)), (0, 0))
        self.assertEqual((FS.bh([]), FS.by([])), (0, 0))

    def test_one_tiny_p_and_the_harmonic_factor(self):
        rest = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
        h10 = sum(1.0 / j for j in range(1, 11))
        self.assertAlmostEqual(h10, 2.9289682539682538, places=12)
        self.assertEqual((FS.bh([0.001, *rest]), FS.by([0.001, *rest])), (1, 1))
        # 0.005 is under BH's first step (0.10 / 10 = 0.01) and over BY's (0.01 / H_10 = 0.0034).
        self.assertEqual((FS.bh([0.005, *rest]), FS.by([0.005, *rest])), (1, 0))
        self.assertEqual(FS.by([0.0034, *rest]), 1)
        self.assertEqual(FS.by([0.0035, *rest]), 0)

    def test_it_is_a_step_up_count(self):
        # p_(1) and p_(2) miss their own steps; p_(3) meets the third (3 * 0.10 / 5 = 0.06): all three are counted.
        ps = [0.5, 0.055, 0.9, 0.045, 0.03]
        self.assertEqual(FS.bh(ps), 3)
        self.assertEqual(FS.bh(sorted(ps)), FS.bh(ps), "the order given does not matter")
        self.assertEqual(FS.bh([0.02] * 5), 5)
        self.assertEqual(FS.bh([0.02] * 5, q=0.01), 0)
        self.assertEqual(FS.bh([0.0, 1.0]), 1)
        self.assertEqual(forward_db.Q, 0.10)

    def test_by_never_counts_more_than_bh(self):
        rng = np.random.default_rng(13)
        for _ in range(50):
            ps = np.concatenate([rng.uniform(0, 1, 40), rng.uniform(0, 0.004, int(rng.integers(0, 6)))]).tolist()
            self.assertLessEqual(FS.by(ps), FS.bh(ps))

    def test_a_p_is_a_number_from_zero_to_one(self):
        for bad in ([0.2, None], [0.2, float("nan")], [1.2], [-0.1], [True]):
            with self.assertRaises(ValueError):
                FS.bh(bad)
            with self.assertRaises(ValueError):
                FS.by(bad)
        with self.assertRaises(ValueError):
            FS.bh([0.2], q=0.0)


class TheReplayMultiple(unittest.TestCase):
    def test_independent_years_on_a_block_correlated_set(self):
        rng = np.random.default_rng(14)
        # Year A: 12 symbols in 3 blocks of 4 that move as one: 3 independent series over 250 sessions.
        blocks = [rng.standard_normal(250) for _ in range(3)]
        a = np.vstack([blocks[i // 4] for i in range(12)])
        # Year B: 12 independent symbols over half a year.
        b = independent(rng, 12, 126)
        self.assertAlmostEqual(FS.independent_years({2016: a}), 3.0 * 250 / 252.0, delta=0.15)
        self.assertAlmostEqual(FS.independent_years({2017: b}), 12.0 * 126 / 252.0, delta=0.6)
        both = FS.independent_years({2017: b, 2016: a})
        self.assertAlmostEqual(both, FS.independent_years({2016: a}) + FS.independent_years({2017: b}), places=12)
        n = FS.neff(a, min_days=3)
        self.assertAlmostEqual(FS.independent_years({2016: a}), n["neff"] * 250 / 252.0, places=12)

    def test_a_year_too_short_or_empty_adds_nothing(self):
        rng = np.random.default_rng(15)
        self.assertEqual(FS.independent_years({}), 0.0)
        self.assertEqual(FS.independent_years({2016: independent(rng, 5, 2), 2017: np.empty((0, 250))}), 0.0)
        self.assertAlmostEqual(FS.independent_years({2018: independent(rng, 1, 252)}), 1.0, places=12)
        with self.assertRaises(ValueError):
            FS.independent_years({2016: [0.1, 0.2]})

    def test_the_multiple_is_simulated_years_over_independent_ones(self):
        self.assertEqual(FS.replay_multiple(10.0, 3.0, 2.0), 2.0)
        self.assertEqual(FS.replay_multiple(0.0, 3.0, 0.0), 0.0)
        self.assertIsNone(FS.replay_multiple(10.0, 0.0, 0.0), "no independent year yet")
        for args in ((None, 3.0, 2.0), (10.0, None, 2.0), (10.0, 3.0, None), (float("nan"), 3.0, 2.0), (True, 3.0, 2.0)):
            self.assertIsNone(FS.replay_multiple(*args))


class TheReadOfAPair(unittest.TestCase):
    def test_against_a_hand_value(self):
        # d = [0.001, 0.002, -0.001]: mean 2/3 e-3; sd (ddof 1) = sqrt(7/3) e-3; t = mean / sd * sqrt(3)
        out = FS.rc_read([0.001, 0.003, 0.002], [0.0, 0.001, 0.003])
        self.assertEqual(out["n"], 3)
        self.assertAlmostEqual(out["mean_bp"], 20.0 / 3.0, places=9)
        self.assertAlmostEqual(out["t"], (2.0 / 3.0) / math.sqrt(7.0 / 3.0) * math.sqrt(3.0), places=9)
        self.assertEqual(set(out), {"n", "mean_bp", "t"})

    def test_it_is_the_t_of_the_daily_differences(self):
        rng = np.random.default_rng(16)
        a, b = rng.normal(0.0005, 0.004, 60), rng.normal(0.0, 0.004, 60)
        out = FS.rc_read(a, b)
        self.assertAlmostEqual(out["t"], FS.t_stat(a - b), places=12)
        self.assertAlmostEqual(out["mean_bp"], float((a - b).mean()) * 1e4, places=9)

    def test_nothing_to_read(self):
        self.assertEqual(FS.rc_read([], []), {"n": 0, "mean_bp": None, "t": None})
        self.assertEqual(FS.rc_read([0.001], [0.0]), {"n": 1, "mean_bp": 10.0, "t": None})
        self.assertIsNone(FS.rc_read([0.002, 0.002], [0.001, 0.001])["t"], "no variance")
        with self.assertRaises(ValueError):
            FS.rc_read([0.001, 0.002], [0.0])


if __name__ == "__main__":
    unittest.main()
