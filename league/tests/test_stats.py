import math
import random
import unittest
from statistics import NormalDist

from league import stats
from league.stats import (
    RUIN,
    cusum_decay,
    deflated_sharpe,
    exact_upper,
    expected_max_sharpe,
    kurtosis,
    log_growth,
    lopsided,
    lopsided_growth_lcb,
    max_drawdown,
    mean_bounds,
    probabilistic_sharpe,
    quarter_kelly,
    sharpe,
    skewness,
    spend,
    t_quantile,
    wilson_upper,
)

NORMAL = NormalDist()
Z95 = NORMAL.inv_cdf(0.95)


def t_pdf(t, dof):
    ln_c = math.lgamma((dof + 1) / 2) - math.lgamma(dof / 2) - 0.5 * math.log(dof * math.pi)
    return math.exp(ln_c - (dof + 1) / 2 * math.log1p(t * t / dof))


def t_cdf_by_simpson(t, dof, steps=4000):
    """The t CDF by integrating the density: shares no code with the incomplete beta route."""
    h = t / steps
    total = t_pdf(0.0, dof) + t_pdf(t, dof)
    for i in range(1, steps):
        total += (4 if i % 2 else 2) * t_pdf(i * h, dof)
    return 0.5 + total * h / 3


def binom_cdf(x, n, p):
    """P(X <= x) for a binomial, summed term by term: shares no code with the incomplete beta route."""
    return math.fsum(math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(x + 1))


def clopper_pearson(x, n, alpha):
    """The exact upper bound from its definition: the p where P(X <= x | p) falls to alpha."""
    low, high = 0.0, 1.0
    for _ in range(100):
        mid = (low + high) / 2
        if binom_cdf(x, n, mid) > alpha:
            low = mid
        else:
            high = mid
    return high


class LogGrowth(unittest.TestCase):
    def test_plain_growth(self):
        self.assertAlmostEqual(log_growth(100, 110), math.log(1.1), places=15)
        self.assertEqual(log_growth(100, 100), 0.0)
        self.assertAlmostEqual(log_growth(100, 50), -math.log(2), places=15)

    def test_a_deposit_is_not_profit_and_a_withdrawal_is_not_a_loss(self):
        self.assertAlmostEqual(log_growth(100, 160, flow=50), math.log(1.1), places=15)
        self.assertAlmostEqual(log_growth(100, 60, flow=-50), math.log(1.1), places=15)

    def test_nothing_to_grow_is_none(self):
        self.assertIsNone(log_growth(0, 100))
        self.assertIsNone(log_growth(-5, 100))
        self.assertIsNone(log_growth(0, 0))
        self.assertIsNone(log_growth(math.nan, 100))
        self.assertIsNone(log_growth(100, math.inf))
        self.assertIsNone(log_growth(100, 100, math.nan))

    def test_ruin_is_the_sentinel(self):
        self.assertEqual(RUIN, -13.8)
        self.assertAlmostEqual(RUIN, math.log(1e-6), delta=0.02)
        self.assertEqual(log_growth(100, 0), RUIN)
        self.assertEqual(log_growth(100, -20), RUIN)
        self.assertEqual(log_growth(100, 30, flow=30), RUIN)
        self.assertEqual(log_growth(100, 30, flow=45), RUIN)

    def test_floored_at_ruin_so_it_never_falls_as_end_rises(self):
        self.assertEqual(log_growth(100, 1e-9), RUIN)  # ln(1e-11) would be below the sentinel
        self.assertEqual(log_growth(1e300, 1e-300), RUIN)
        ends = [-1.0, 0.0, 1e-12, 1e-6, 1e-4, 1e-3, 1.0, 50.0, 100.0, 1e6]
        growths = [log_growth(100, end) for end in ends]
        self.assertEqual(growths, sorted(growths))


class TQuantile(unittest.TestCase):
    # Standard table values (six or more decimals).
    TABLE = {
        (0.975, 10): 2.228139, (0.95, 5): 2.015048, (0.99, 30): 2.457262, (0.995, 1): 63.656741,
        (0.9, 2): 1.885618, (0.975, 1): 12.706205, (0.975, 2): 4.302653, (0.975, 3): 3.182446,
        (0.975, 4): 2.776445, (0.975, 5): 2.570582, (0.975, 20): 2.085963, (0.975, 30): 2.042272,
        (0.975, 60): 2.000298, (0.975, 120): 1.979930, (0.95, 1): 6.313752, (0.95, 2): 2.919986,
        (0.95, 4): 2.131847, (0.95, 10): 1.812461, (0.95, 30): 1.697261, (0.95, 120): 1.657651,
        (0.99, 10): 2.763769, (0.995, 10): 3.169273, (0.999, 10): 4.143700, (0.9995, 10): 4.586894,
    }

    def test_table_values(self):
        for (p, dof), expected in self.TABLE.items():
            with self.subTest(p=p, dof=dof):
                self.assertAlmostEqual(t_quantile(p, dof), expected, delta=1e-6)

    def test_symmetry_and_median(self):
        for dof in (1, 2, 3, 7.5, 30, 1000, 1e7):
            self.assertEqual(t_quantile(0.5, dof), 0.0)
            # 0.25 and 0.125 are exact in binary, so 1 - p is exactly the mirrored tail.
            for p in (0.25, 0.125, 2.0 ** -20):
                with self.subTest(p=p, dof=dof):
                    self.assertEqual(t_quantile(p, dof), -t_quantile(1 - p, dof))
            self.assertAlmostEqual(t_quantile(0.025, dof), -t_quantile(0.975, dof), delta=1e-9)

    def test_large_dof_is_normal(self):
        for p in (0.6, 0.95, 0.975, 0.999, 1e-6):
            with self.subTest(p=p):
                z = NORMAL.inv_cdf(p)
                self.assertAlmostEqual(t_quantile(p, 1e9), z, delta=1e-7)
                self.assertAlmostEqual(t_quantile(p, 1e12), z, delta=1e-10)
                self.assertEqual(t_quantile(p, math.inf), -NORMAL.inv_cdf(1 - p) if p > 0.5 else z)
                # heavier tails than the normal at any finite dof
                self.assertGreater(abs(t_quantile(p, 1000)), abs(z))

    def test_numeric_route_agrees_with_the_closed_forms_at_dof_1_and_2(self):
        for q in (0.49, 0.4, 0.25, 0.1, 0.05, 0.01, 1e-3, 1e-5, 1e-7, 1e-9, 1e-12):
            cauchy = 1 / math.tan(math.pi * q)
            two = (1 - 2 * q) / math.sqrt(2 * q * (1 - q))
            with self.subTest(q=q):
                self.assertAlmostEqual(stats._t_upper_numeric(q, 1.0) / cauchy, 1.0, delta=1e-12)
                self.assertAlmostEqual(stats._t_upper_numeric(q, 2.0) / two, 1.0, delta=1e-12)
                self.assertAlmostEqual(t_quantile(q, 1) / -cauchy, 1.0, delta=1e-12)
                self.assertAlmostEqual(t_quantile(q, 2) / -two, 1.0, delta=1e-12)

    def test_closed_form_at_dof_4(self):
        def exact(p):
            a = 4 * p * (1 - p)
            return math.copysign(2 * math.sqrt(math.cos(math.acos(math.sqrt(a)) / 3) / math.sqrt(a) - 1), p - 0.5)

        for p in (0.6, 0.9, 0.975, 0.999, 0.01, 1e-6):
            with self.subTest(p=p):
                self.assertAlmostEqual(t_quantile(p, 4), exact(p), delta=1e-9)

    def test_round_trip_through_an_independent_cdf(self):
        worst = 0.0
        for dof in (1, 1.5, 2.5, 3, 4, 5, 7.3, 10, 29, 100, 1000):
            for p in (0.5001, 0.6, 0.75, 0.9, 0.95, 0.975, 0.99, 0.999):
                t = t_quantile(p, dof)
                if t > 100:
                    continue
                worst = max(worst, abs(t_cdf_by_simpson(t, dof) - p) / t_pdf(t, dof))  # error in units of t
        self.assertLess(worst, 1e-8)

    def test_extreme_tails(self):
        self.assertAlmostEqual(t_quantile(1e-9, 1) / (-1 / math.tan(math.pi * 1e-9)), 1.0, delta=1e-12)
        for dof in (3, 10, 30):
            t = stats._t_upper(1e-9, float(dof))
            self.assertAlmostEqual(stats._t_tail(t, dof) / 1e-9, 1.0, delta=1e-9)
            self.assertGreater(t, -NORMAL.inv_cdf(1e-9))
        # beyond the promised range it still answers, and the answer is finite
        self.assertTrue(math.isfinite(t_quantile(1e-300, 1)))
        self.assertTrue(math.isfinite(t_quantile(1e-300, 3)))
        self.assertTrue(math.isfinite(t_quantile(1 - 1e-16, 0.5)))

    def test_monotone_in_p_and_lighter_tails_with_more_dof(self):
        ps = [1e-9, 1e-6, 0.001, 0.05, 0.3, 0.5, 0.7, 0.95, 0.999, 1 - 1e-6, 1 - 1e-9]
        for dof in (1, 2, 3.3, 17, 400, 5e5):
            values = [t_quantile(p, dof) for p in ps]
            self.assertEqual(values, sorted(values))
            self.assertEqual(len(set(values)), len(values))
        dofs = [1, 1.5, 2, 3, 5, 10, 30, 100, 1e4, 1e5, 1e5 + 1, 1e6, 1e9]
        upper = [t_quantile(0.975, dof) for dof in dofs]
        self.assertEqual(upper, sorted(upper, reverse=True))

    def test_the_series_and_the_numeric_route_meet_at_the_switch(self):
        for q in (0.4, 0.1, 0.025, 1e-3, 1e-6, 1e-9):
            with self.subTest(q=q):
                switch = stats._NORMAL_DOF
                self.assertAlmostEqual(stats._t_upper_series(q, switch), stats._t_upper_numeric(q, switch), delta=1e-9)
                self.assertAlmostEqual(stats._t_upper_series(q, 1000.0), stats._t_upper_numeric(q, 1000.0), delta=1e-9)

    def test_bad_parameters_raise(self):
        for p in (0, 1, -0.1, 1.5, math.nan):
            with self.assertRaises(ValueError):
                t_quantile(p, 10)
        for dof in (0, -1, math.nan):
            with self.assertRaises(ValueError):
                t_quantile(0.9, dof)


class Spend(unittest.TestCase):
    def test_first_looks(self):
        self.assertAlmostEqual(spend(0.05, 1), 0.05 * 6 / math.pi ** 2, places=15)
        self.assertAlmostEqual(spend(0.05, 1), 0.030396355, places=9)
        self.assertAlmostEqual(spend(0.05, 2), spend(0.05, 1) / 4, places=15)
        self.assertAlmostEqual(spend(0.05, 10), spend(0.05, 1) / 100, places=15)

    def test_all_looks_together_stay_below_alpha_and_approach_it(self):
        total = math.fsum(spend(0.05, k) for k in range(1, 10_001))
        self.assertLess(total, 0.05)
        self.assertGreater(total, 0.05 * 0.9999)
        more = math.fsum(spend(0.05, k) for k in range(1, 100_001))
        self.assertLess(total, more)
        self.assertLess(more, 0.05)

    def test_strictly_decreasing(self):
        values = [spend(0.1, k) for k in range(1, 200)]
        self.assertTrue(all(a > b > 0 for a, b in zip(values, values[1:])))

    def test_bad_parameters_raise(self):
        for look in (0, -1, 1.5, True, None):
            with self.assertRaises(ValueError):
                spend(0.05, look)
        for alpha in (0, 1, -0.05, math.nan):
            with self.assertRaises(ValueError):
                spend(alpha, 1)


class MeanBounds(unittest.TestCase):
    def test_reference(self):
        b = mean_bounds([1, 2, 3, 4, 5], 0.05)
        self.assertEqual(b["n"], 5)
        self.assertEqual(b["mean"], 3.0)
        self.assertAlmostEqual(b["sd"], math.sqrt(2.5), places=14)
        half = 2.131847 * math.sqrt(2.5) / math.sqrt(5)  # t(0.95, 4) from the table
        self.assertAlmostEqual(b["lcb"], 3 - half, delta=1e-6)
        self.assertAlmostEqual(b["ucb"], 3 + half, delta=1e-6)
        self.assertEqual(set(b), {"n", "mean", "sd", "lcb", "ucb"})

    def test_too_little_data_is_none(self):
        self.assertIsNone(mean_bounds([], 0.05))
        self.assertIsNone(mean_bounds([0.3], 0.05))
        self.assertIsNone(mean_bounds([0.1, math.nan, 0.2], 0.05))
        self.assertIsNone(mean_bounds([0.1, math.inf], 0.05))

    def test_n_of_two_uses_the_cauchy_quantile(self):
        b = mean_bounds([0.0, 2.0], 0.05)
        self.assertAlmostEqual(b["lcb"], 1 - 6.313752 * math.sqrt(2) / math.sqrt(2), delta=1e-6)

    def test_no_variance(self):
        for value in (0.3, 0.1, -2.5, 0.0, 1e-9):
            b = mean_bounds([value] * 7, 0.05)
            self.assertEqual((b["mean"], b["sd"], b["lcb"], b["ucb"]), (value, 0.0, value, value))
        # rounding noise is not variance
        noisy = mean_bounds([0.1 + 0.2, 0.3, 0.3, 0.1 + 0.2], 0.05)
        self.assertEqual(noisy["sd"], 0.0)
        self.assertEqual(noisy["lcb"], noisy["ucb"])

    def test_bounds_order_and_tighten(self):
        rng = random.Random(3)
        xs = [rng.gauss(0.1, 1.0) for _ in range(50)]
        wide, narrow = mean_bounds(xs, 0.001), mean_bounds(xs, 0.05)
        self.assertLess(wide["lcb"], narrow["lcb"])
        self.assertLess(narrow["lcb"], narrow["mean"])
        self.assertLess(narrow["mean"], narrow["ucb"])
        self.assertLess(narrow["ucb"], wide["ucb"])
        self.assertAlmostEqual(narrow["mean"] - narrow["lcb"], narrow["ucb"] - narrow["mean"], places=14)
        half = mean_bounds(xs, 0.5)
        self.assertEqual(half["lcb"], half["mean"])
        # the same data seen four times over: a narrower interval
        self.assertGreater(mean_bounds(xs * 4, 0.05)["lcb"], narrow["lcb"])

    def test_a_spent_alpha_from_a_late_look_works(self):
        b = mean_bounds([0.01, 0.03, -0.01, 0.02, 0.015, 0.005], spend(0.05, 10_000))
        self.assertTrue(math.isfinite(b["lcb"]))
        self.assertLess(b["lcb"], mean_bounds([0.01, 0.03, -0.01, 0.02, 0.015, 0.005], spend(0.05, 1))["lcb"])

    def test_bad_alpha_raises(self):
        for alpha in (0, 1, -1, 2, math.nan):
            with self.assertRaises(ValueError):
                mean_bounds([1, 2, 3], alpha)

    def test_monte_carlo_coverage(self):
        # Each one-sided bound at alpha = 0.05 must hold about 95% of the time on normal data.
        # 2000 draws: the sd of the hit rate is 0.49%, so [93%, 97%] is four sds either way. A
        # bound that covers too often is as wrong as one that covers too rarely.
        rng = random.Random(20260919)
        true_mean, draws = 0.3, 2000
        below = above = 0
        for _ in range(draws):
            b = mean_bounds([rng.gauss(true_mean, 2.0) for _ in range(30)], 0.05)
            below += b["lcb"] < true_mean
            above += b["ucb"] > true_mean
        self.assertGreaterEqual(below / draws, 0.93)
        self.assertLessEqual(below / draws, 0.97)
        self.assertGreaterEqual(above / draws, 0.93)
        self.assertLessEqual(above / draws, 0.97)


class WilsonUpper(unittest.TestCase):
    def test_no_losses_in_forty(self):
        z2 = Z95 ** 2
        self.assertAlmostEqual(wilson_upper(0, 40, 0.05), z2 / (40 + z2), places=14)
        self.assertAlmostEqual(wilson_upper(0, 40, 0.05), 0.0634, delta=1e-4)
        self.assertAlmostEqual(wilson_upper(0, 40, 0.05), 0.06335345, delta=1e-8)

    def test_hand_computed(self):
        # 5 losses in 50 at z = 1.644854: (0.1 + 0.0270554 + 0.0748461) / 1.0541109
        self.assertAlmostEqual(wilson_upper(5, 50, 0.05), 0.191538, delta=1e-5)

    def test_it_inverts_the_score_test(self):
        # The Wilson bound u is where the score statistic of H0: p = u equals z exactly.
        for losses, n, alpha in ((0, 40, 0.05), (3, 17, 0.05), (8, 408, 0.05), (50, 100, 0.01), (99, 100, 0.2)):
            with self.subTest(losses=losses, n=n, alpha=alpha):
                u = wilson_upper(losses, n, alpha)
                score = (u - losses / n) / math.sqrt(u * (1 - u) / n)
                self.assertAlmostEqual(score, NORMAL.inv_cdf(1 - alpha), delta=1e-9)

    def test_monotone_and_bounded(self):
        for n in (1, 5, 40, 333):
            values = [wilson_upper(losses, n, 0.05) for losses in range(n + 1)]
            self.assertTrue(all(a < b for a, b in zip(values, values[1:])), n)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in values))
            self.assertTrue(all(v > losses / n or losses == n for losses, v in enumerate(values)))
            self.assertEqual(values[-1], 1.0)
        clean = [wilson_upper(0, n, 0.05) for n in (1, 2, 10, 100, 10_000)]
        self.assertEqual(clean, sorted(clean, reverse=True))
        self.assertLess(wilson_upper(2, 40, 0.05), wilson_upper(2, 40, 0.01))  # more confidence, higher bound

    def test_no_evidence_is_the_worst_case(self):
        self.assertEqual(wilson_upper(0, 0, 0.05), 1.0)
        self.assertEqual(wilson_upper(3, -2, 0.05), 1.0)
        self.assertEqual(wilson_upper(50, 40, 0.05), 1.0)  # more losses than trades: clamped
        self.assertEqual(wilson_upper(-3, 40, 0.05), wilson_upper(0, 40, 0.05))
        with self.assertRaises(ValueError):
            wilson_upper(0, 40, 0.0)

    def test_exact_coverage(self):
        # The exact chance, over the binomial, that the bound is at or above the true p. Wilson is
        # a score interval, not an exact one: its one-sided coverage dips to about 92-93% just above
        # the bound for a clean record (p = 0.064 at n = 40). That is why the lopsided gate uses
        # `exact_upper` and not this; the dip is pinned here so that nobody swaps it back unknowingly.
        for n, floor in ((20, 0.92), (40, 0.925), (100, 0.93)):
            worst = 1.0
            for i in range(1, 500):
                p = i / 1000
                covered = math.fsum(
                    math.comb(n, x) * p ** x * (1 - p) ** (n - x) for x in range(n + 1) if wilson_upper(x, n, 0.05) >= p
                )
                worst = min(worst, covered)
            self.assertGreaterEqual(worst, floor, n)
            self.assertLess(worst, 0.95, n)


class ExactUpper(unittest.TestCase):
    def test_no_losses_is_a_closed_form(self):
        # (1 - p)^n = alpha
        self.assertAlmostEqual(exact_upper(0, 40, 0.05), 1 - 0.05 ** (1 / 40), places=14)
        self.assertAlmostEqual(exact_upper(0, 40, 0.05), 0.0722, delta=1e-4)
        self.assertAlmostEqual(exact_upper(0, 10, 0.05), 0.258866, delta=1e-6)
        self.assertAlmostEqual(exact_upper(0, 1, 0.05), 0.95, places=14)
        for n in (1, 5, 20, 100, 1000, 100_000):
            for alpha in (0.05, 0.01, 0.5, 0.9):
                with self.subTest(n=n, alpha=alpha):
                    self.assertAlmostEqual(exact_upper(0, n, alpha) / (1 - alpha ** (1 / n)), 1.0, delta=1e-9)

    def test_one_win_short_of_all_losses_is_a_closed_form_too(self):
        # P(X <= n - 1) = 1 - p^n = alpha. This one goes through the bisection.
        for n in (2, 5, 20, 100, 1000):
            for alpha in (0.05, 0.01, 0.5, 0.9):
                with self.subTest(n=n, alpha=alpha):
                    self.assertAlmostEqual(exact_upper(n - 1, n, alpha), (1 - alpha) ** (1 / n), delta=1e-10)

    def test_table_value(self):
        # 1 in 10 at one-sided 95%: the upper end of the published two-sided 90% interval
        self.assertAlmostEqual(exact_upper(1, 10, 0.05), 0.394163, delta=1e-6)

    def test_it_solves_the_binomial_tail_exactly(self):
        # By definition P(X <= losses | p = bound) = alpha. Checked against the binomial sum itself.
        for n in (7, 20, 40, 100, 408):
            for losses in range(0, n, max(1, n // 13)):
                for alpha in (0.3, 0.05, 0.001, spend(0.05, 50)):
                    with self.subTest(losses=losses, n=n, alpha=alpha):
                        bound = exact_upper(losses, n, alpha)
                        self.assertAlmostEqual(binom_cdf(losses, n, bound) / alpha, 1.0, delta=1e-8)
        self.assertAlmostEqual(exact_upper(8, 408, 0.05), clopper_pearson(8, 408, 0.05), delta=1e-12)
        self.assertAlmostEqual(exact_upper(8, 408, 0.05), 0.0351003, delta=1e-7)

    def test_exact_coverage_is_never_below_what_it_says(self):
        # The exact chance, over the binomial, that the bound is at or above the true p: at least
        # 1 - alpha for EVERY p. (The same sum for `wilson_upper` dips to 92%.)
        for n in (20, 40, 100):
            for alpha in (0.05, 0.01):
                bounds = [exact_upper(x, n, alpha) for x in range(n + 1)]
                worst = 1.0
                for i in range(1, 1000):
                    p = i / 1000
                    pmf = (math.comb(n, x) * p ** x * (1 - p) ** (n - x) for x in range(n + 1))
                    worst = min(worst, math.fsum(mass for mass, bound in zip(pmf, bounds) if bound >= p))
                self.assertGreaterEqual(worst, 1 - alpha, (n, alpha))
                self.assertLess(worst, 1 - alpha + 0.01, (n, alpha))  # exact, not merely loose

    def test_monotone_and_bounded(self):
        for n in (1, 5, 40, 333):
            values = [exact_upper(losses, n, 0.05) for losses in range(n + 1)]
            self.assertTrue(all(a < b for a, b in zip(values, values[1:])), n)
            self.assertTrue(all(0.0 < v <= 1.0 for v in values))
            self.assertTrue(all(v > losses / n or losses == n for losses, v in enumerate(values)))
            self.assertEqual(values[-1], 1.0)
        clean = [exact_upper(0, n, 0.05) for n in (1, 2, 10, 100, 10_000, 10 ** 7)]
        self.assertEqual(clean, sorted(clean, reverse=True))
        self.assertGreater(clean[-1], 0.0)
        by_alpha = [exact_upper(2, 40, alpha) for alpha in (0.5, 0.2, 0.05, 0.01, 1e-6, 1e-12)]
        self.assertEqual(by_alpha, sorted(by_alpha))  # more confidence, higher bound

    def test_never_below_wilson(self):
        for n in (5, 20, 40, 100, 408):
            for losses in range(n + 1):
                self.assertGreaterEqual(exact_upper(losses, n, 0.05), wilson_upper(losses, n, 0.05), (losses, n))

    def test_no_evidence_is_the_worst_case(self):
        self.assertEqual(exact_upper(0, 0, 0.05), 1.0)
        self.assertEqual(exact_upper(3, -2, 0.05), 1.0)
        self.assertEqual(exact_upper(40, 40, 0.05), 1.0)
        self.assertEqual(exact_upper(50, 40, 0.05), 1.0)  # more losses than trades: clamped
        self.assertEqual(exact_upper(-3, 40, 0.05), exact_upper(0, 40, 0.05))
        for alpha in (0, 1, -0.05, math.nan):
            with self.assertRaises(ValueError):
                exact_upper(0, 40, alpha)

    def test_tiny_alpha(self):
        # A late look spends very little alpha: the bound must rise towards 1 and stay below it.
        self.assertAlmostEqual(exact_upper(0, 40, 1e-300), 1 - 10 ** -7.5, places=12)
        late = exact_upper(3, 40, spend(0.05, 10_000))
        self.assertAlmostEqual(binom_cdf(3, 40, late) / spend(0.05, 10_000), 1.0, delta=1e-8)
        values = [exact_upper(3, 40, alpha) for alpha in (1e-3, 1e-9, 1e-30, 1e-100, 1e-300)]
        self.assertEqual(values, sorted(values))
        self.assertTrue(all(0.0 < v < 1.0 for v in values))
        # and an alpha close to 1 gives a bound close to 0, not an error
        self.assertAlmostEqual(exact_upper(0, 40, 1 - 1e-12) / 2.5e-14, 1.0, delta=1e-3)


class Lopsided(unittest.TestCase):
    def test_needs_five_trades(self):
        self.assertFalse(lopsided([]))
        self.assertFalse(lopsided([0.01] * 4))
        self.assertTrue(lopsided([0.01] * 5))

    def test_win_rate_threshold_is_inclusive_and_wins_are_strict(self):
        self.assertTrue(lopsided([0.01, 0.01, 0.01, 0.01, -0.2]))  # exactly 80%
        self.assertFalse(lopsided([0.01, 0.01, 0.01, -0.2, -0.2]))
        self.assertFalse(lopsided([0.01, 0.01, 0.01, 0.0, 0.0]))  # a scratch is not a win
        self.assertTrue(lopsided([0.01] * 7 + [-0.1] * 3, min_win_rate=0.7))
        self.assertFalse(lopsided([0.01] * 7 + [-0.1] * 3))
        self.assertFalse(lopsided([0.02, -0.01, 0.03, -0.02, 0.01, -0.03]))


class LopsidedGrowth(unittest.TestCase):
    WIN, RISK = 0.005, 0.07

    def test_twenty_clean_wins_are_not_enough(self):
        # p_u = 1 - 0.05^(1/20) = 0.139108, so the bound is
        # 0.860892 * ln(1.005) + 0.139108 * ln(0.93) = 0.004294 - 0.010095 = -0.005801.
        # Break-even is p = ln(1.005) / (ln(1.005) - ln(0.93)) = 0.0643: far below 0.139.
        bound = lopsided_growth_lcb([self.WIN] * 20, self.RISK, 0.05)
        p = 1 - 0.05 ** (1 / 20)
        self.assertAlmostEqual(bound, (1 - p) * math.log(1.005) + p * math.log(0.93), places=14)
        self.assertAlmostEqual(bound, -0.005801, delta=1e-6)
        self.assertLess(bound, 0)

    def test_four_hundred_wins_and_eight_losses_are(self):
        # p_u = the exact bound for 8 in 408 = 0.035100 (from the binomial sum, not from the module),
        # well under the 0.0643 break-even:
        # 0.964900 * ln(1.005) + 0.035100 * ln(0.93) = 0.004812 - 0.002547 = +0.002265.
        bound = lopsided_growth_lcb([self.WIN] * 400 + [-self.RISK] * 8, self.RISK, 0.05)
        p = clopper_pearson(8, 408, 0.05)
        self.assertAlmostEqual(p, 0.035100, delta=1e-6)
        self.assertAlmostEqual(bound, (1 - p) * math.log(1.005) + p * math.log(0.93), places=12)
        self.assertAlmostEqual(bound, 0.002265, delta=1e-6)
        self.assertGreater(bound, 0)
        # and it stays below the plain estimate of growth from the same record
        plain = (400 * math.log1p(self.WIN) + 8 * math.log1p(-self.RISK)) / 408
        self.assertLess(bound, plain)

    def test_the_clean_record_turns_positive_at_forty_six_wins(self):
        # 1 - 0.05^(1/n) < 0.064307 needs n > ln(0.05) / ln(1 - 0.064307) = 45.07, so 46 clean wins.
        # (The Wilson bound let it through at 40.)
        break_even = math.log(1.005) / (math.log(1.005) - math.log(0.93))
        self.assertEqual(math.ceil(math.log(0.05) / math.log(1 - break_even)), 46)
        signs = [lopsided_growth_lcb([self.WIN] * n, self.RISK, 0.05) > 0 for n in range(1, 101)]
        self.assertEqual(signs, [False] * 45 + [True] * 55)
        self.assertAlmostEqual(lopsided_growth_lcb([self.WIN] * 45, self.RISK, 0.05), -0.0000075, delta=1e-6)
        self.assertAlmostEqual(lopsided_growth_lcb([self.WIN] * 46, self.RISK, 0.05), 0.0000975, delta=1e-6)

    def test_uneven_wins_are_the_mean_of_the_logs(self):
        # Half the wins +0.1% and half +50%: the account grows by the mean of ln(1 + w), which is
        # well under the ln of the mean win (Jensen), and the bound must use the smaller one.
        wins = [0.001, 0.5] * 50
        p = 1 - 0.05 ** (1 / 100)
        mean_of_logs = (math.log(1.001) + math.log(1.5)) / 2
        bound = lopsided_growth_lcb(wins, self.RISK, 0.05)
        self.assertAlmostEqual(bound, (1 - p) * mean_of_logs + p * math.log(0.93), places=13)
        # ln(1.2505) = 0.22354 against a mean of logs of 0.20323: the old form overstated it by 0.0197
        self.assertAlmostEqual((1 - p) * math.log(1.2505) + p * math.log(0.93) - bound, 0.0197, delta=1e-4)
        # equal wins: the two are the same thing
        even = lopsided_growth_lcb([0.2505] * 100, self.RISK, 0.05)
        self.assertAlmostEqual(even, (1 - p) * math.log(1.2505) + p * math.log(0.93), places=13)
        self.assertLess(bound, even)

    def test_the_t_interval_is_fooled_where_this_is_not(self):
        record = [self.WIN] * 20
        self.assertTrue(lopsided(record))
        self.assertGreater(mean_bounds([math.log1p(r) for r in record], 0.05)["lcb"], 0)
        self.assertLess(lopsided_growth_lcb(record, self.RISK, 0.05), 0)

    def test_the_loss_is_the_worse_of_what_was_seen_and_what_was_at_risk(self):
        wins = [self.WIN] * 100
        mild = lopsided_growth_lcb(wins + [-0.01], self.RISK, 0.05)  # seen -1%, but 7% was at risk
        p = clopper_pearson(1, 101, 0.05)
        self.assertAlmostEqual(mild, (1 - p) * math.log(1.005) + p * math.log(0.93), places=12)
        bad = lopsided_growth_lcb(wins + [-0.2], self.RISK, 0.05)  # seen worse than the stated risk
        self.assertAlmostEqual(bad, (1 - p) * math.log(1.005) + p * math.log(0.8), places=12)
        self.assertLess(bad, mild)
        # the sign of risk_per_trade does not matter
        self.assertEqual(lopsided_growth_lcb(wins, -self.RISK, 0.05), lopsided_growth_lcb(wins, self.RISK, 0.05))

    def test_a_scratch_counts_as_a_loss(self):
        wins = [self.WIN] * 50
        p = clopper_pearson(2, 52, 0.05)
        bound = lopsided_growth_lcb(wins + [0.0, 0.0], self.RISK, 0.05)
        self.assertAlmostEqual(bound, (1 - p) * math.log(1.005) + p * math.log(0.93), places=12)
        self.assertLess(bound, lopsided_growth_lcb(wins + [self.WIN] * 2, self.RISK, 0.05))

    def test_total_loss_is_clamped_to_a_finite_log(self):
        bound = lopsided_growth_lcb([self.WIN] * 30, 1.0, 0.05)
        self.assertTrue(math.isfinite(bound))
        self.assertLess(bound, -0.5)
        self.assertEqual(bound, lopsided_growth_lcb([self.WIN] * 30, 7.0, 0.05))  # a risk given in percent by mistake
        self.assertTrue(math.isfinite(lopsided_growth_lcb([self.WIN] * 30 + [-1.5], 0.07, 0.05)))

    def test_no_wins_at_all(self):
        bound = lopsided_growth_lcb([-0.01, -0.02, 0.0], 0.07, 0.05)
        self.assertAlmostEqual(bound, math.log(0.93), places=12)  # p_u = 1, avg_win = 0

    def test_more_evidence_raises_it_and_a_loss_lowers_it(self):
        bounds = [lopsided_growth_lcb([self.WIN] * n, self.RISK, 0.05) for n in (5, 10, 20, 40, 80, 160, 1000)]
        self.assertEqual(bounds, sorted(bounds))
        self.assertLess(bounds[-1], math.log1p(self.WIN))
        with_loss = lopsided_growth_lcb([self.WIN] * 159 + [-self.RISK], self.RISK, 0.05)
        self.assertLess(with_loss, lopsided_growth_lcb([self.WIN] * 160, self.RISK, 0.05))
        strict = lopsided_growth_lcb([self.WIN] * 160, self.RISK, 0.001)
        self.assertLess(strict, lopsided_growth_lcb([self.WIN] * 160, self.RISK, 0.05))

    def test_empty_is_none_and_bad_data_is_a_total_loss(self):
        self.assertIsNone(lopsided_growth_lcb([], 0.07, 0.05))
        # The evaluator reads None as "no gate applies", so unreadable data must fail the gate instead.
        wins = [self.WIN] * 400
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(bad=bad):
                total_loss = lopsided_growth_lcb(wins + [-1.0], self.RISK, 0.05)
                self.assertEqual(lopsided_growth_lcb(wins + [bad], self.RISK, 0.05), total_loss)
                self.assertLess(lopsided_growth_lcb(wins + [bad], self.RISK, 0.05), 0)
                self.assertEqual(lopsided_growth_lcb(wins, bad, 0.05), lopsided_growth_lcb(wins, 1.0, 0.05))
                self.assertLess(lopsided_growth_lcb(wins, bad, 0.05), 0)
        self.assertGreater(lopsided_growth_lcb(wins, self.RISK, 0.05), 0)

    def test_a_losing_favourites_seller_is_rarely_promoted(self):
        # Truth: +0.5% with probability 0.92, -7% with 0.08. Expected log growth is
        # 0.92 * 0.0049875 - 0.08 * 0.072571 = -0.0012: this agent must not be given money.
        # After 20 trades 0.92^20 = 19% of such agents have no loss yet, and the t-interval promotes
        # every one of them. The lopsided bound must stay at or under its 5%.
        for n in (20, 60):
            rng = random.Random(7)
            fooled_t = fooled_bound = 0
            for _ in range(2000):
                record = [self.WIN if rng.random() >= 0.08 else -self.RISK for _ in range(n)]
                fooled_t += mean_bounds([math.log1p(r) for r in record], 0.05)["lcb"] > 0
                fooled_bound += lopsided_growth_lcb(record, self.RISK, 0.05) > 0
            self.assertLessEqual(fooled_bound / 2000, 0.05, n)
            if n == 20:
                self.assertGreater(fooled_t / 2000, 0.15)
                self.assertEqual(fooled_bound, 0)


class Moments(unittest.TestCase):
    def test_sharpe(self):
        self.assertEqual(sharpe([1, 2, 3]), 2.0)
        self.assertAlmostEqual(sharpe([-1, -2, -3]), -2.0, places=15)
        self.assertAlmostEqual(sharpe([0.0, 2.0]), 1 / math.sqrt(2), places=15)
        self.assertEqual(sharpe([-1, 1]), 0.0)

    def test_sharpe_undefined(self):
        self.assertIsNone(sharpe([]))
        self.assertIsNone(sharpe([0.5]))
        self.assertIsNone(sharpe([0.5, 0.5, 0.5]))
        self.assertIsNone(sharpe([0.1 + 0.2, 0.3, 0.3]))  # differs by one ulp: noise, not a Sharpe of 1e15
        self.assertIsNone(sharpe([0.1, math.nan]))
        self.assertIsNone(sharpe([1e200, -1e200, 1e200]))  # the sd overflows
        self.assertIsNone(sharpe([1e308, 1e308, 1.0]))  # the sum overflows: None, not an OverflowError
        self.assertIsNone(mean_bounds([1e308, 1e308, 1.0], 0.05))
        self.assertTrue(math.isfinite(lopsided_growth_lcb([1e308] * 6, 0.07, 0.05)))

    def test_skewness_and_kurtosis_by_hand(self):
        # deviations -3 -2 -1 0 6: m2 = 10, m3 = 36, m4 = 278.8
        xs = [1, 2, 3, 4, 10]
        self.assertAlmostEqual(skewness(xs), 36 / 10 ** 1.5, places=13)
        self.assertAlmostEqual(kurtosis(xs), 2.788, places=13)
        self.assertAlmostEqual(skewness([-x for x in xs]), -36 / 10 ** 1.5, places=13)

    def test_symmetric_and_two_point(self):
        self.assertAlmostEqual(skewness([-2, -1, 0, 1, 2]), 0.0, places=15)
        self.assertAlmostEqual(kurtosis([-2, -1, 0, 1, 2]), 1.7, places=13)  # m4 = 6.8, m2 = 2
        self.assertAlmostEqual(kurtosis([-1, 1] * 10), 1.0, places=13)  # the least a kurtosis can be
        # shifting and scaling change neither
        xs = [0.3, -1.2, 0.8, 2.9, -0.4, 0.1]
        moved = [1000 + 7 * x for x in xs]
        self.assertAlmostEqual(skewness(xs), skewness(moved), places=9)
        self.assertAlmostEqual(kurtosis(xs), kurtosis(moved), places=9)

    def test_kurtosis_is_not_excess(self):
        rng = random.Random(11)
        xs = [rng.gauss(0, 1) for _ in range(40_000)]
        self.assertAlmostEqual(kurtosis(xs), 3.0, delta=0.1)
        self.assertAlmostEqual(skewness(xs), 0.0, delta=0.05)

    def test_kurtosis_is_at_least_skewness_squared_plus_one(self):
        rng = random.Random(5)
        for _ in range(200):
            xs = [rng.expovariate(1.0) ** 2 for _ in range(rng.randint(4, 30))]
            self.assertGreaterEqual(kurtosis(xs), skewness(xs) ** 2 + 1 - 1e-9)

    def test_undefined(self):
        self.assertIsNone(skewness([1, 2]))
        self.assertIsNotNone(skewness([1, 2, 4]))
        self.assertIsNone(kurtosis([1, 2, 4]))
        self.assertIsNotNone(kurtosis([1, 2, 4, 8]))
        self.assertIsNone(skewness([2, 2, 2, 2]))
        self.assertIsNone(kurtosis([2, 2, 2, 2]))
        self.assertIsNone(skewness([]))
        self.assertIsNone(kurtosis([1, 2, math.inf, 4]))
        self.assertIsNotNone(kurtosis([1e100, -1e100, 2e100, 0.0]))  # no overflow in the fourth power


class ProbabilisticSharpe(unittest.TestCase):
    def test_by_hand(self):
        # 1 - (-1)(0.2) + (7 - 1) / 4 * 0.04 = 1.26, and (0.2 - 0.05) * sqrt(100) = 1.5
        by_hand = NORMAL.cdf(1.5 / math.sqrt(1.26))
        self.assertAlmostEqual(probabilistic_sharpe(0.2, 101, -1, 7, 0.05), by_hand, places=14)
        self.assertAlmostEqual(probabilistic_sharpe(0.2, 101, -1, 7, 0.05), 0.909275, delta=1e-6)
        # normal returns: sqrt(1 + sr^2 / 2)
        self.assertAlmostEqual(probabilistic_sharpe(0.5, 17, 0, 3), NORMAL.cdf(2 / math.sqrt(1.125)), places=14)

    def test_at_the_benchmark_it_is_a_coin_flip(self):
        self.assertEqual(probabilistic_sharpe(0.0, 50, 0, 3), 0.5)
        self.assertEqual(probabilistic_sharpe(0.3, 50, -2, 12, benchmark=0.3), 0.5)

    def test_what_moves_it(self):
        base = probabilistic_sharpe(0.2, 60, 0, 3)
        self.assertGreater(base, 0.5)
        self.assertGreater(probabilistic_sharpe(0.2, 240, 0, 3), base)  # more data
        self.assertLess(probabilistic_sharpe(0.2, 60, -1.5, 3), base)  # negative skew
        self.assertLess(probabilistic_sharpe(0.2, 60, 0, 12), base)  # fat tails
        self.assertLess(probabilistic_sharpe(0.2, 60, 0, 3, benchmark=0.1), base)  # a higher bar
        self.assertLess(probabilistic_sharpe(-0.2, 60, 0, 3), 0.5)
        self.assertAlmostEqual(probabilistic_sharpe(-0.2, 60, 0, 3), 1 - base, places=14)

    def test_degenerate(self):
        self.assertEqual(probabilistic_sharpe(0.4, 1, 0, 3), 0.5)
        self.assertEqual(probabilistic_sharpe(0.4, 0, 0, 3), 0.5)
        self.assertEqual(probabilistic_sharpe(math.nan, 50, 0, 3), 0.5)
        self.assertEqual(probabilistic_sharpe(0.4, 50, math.inf, 3), 0.5)
        # impossible moments (kurt < skew^2 + 1) push the root's argument below zero: floored, not raised
        p = probabilistic_sharpe(1.0, 50, 3.0, 3.0)
        self.assertTrue(0.0 <= p <= 1.0)
        p = probabilistic_sharpe(1.0, 50, 3.0, 3.0, benchmark=2.0)
        self.assertTrue(0.0 <= p <= 1.0)
        self.assertTrue(0.0 <= probabilistic_sharpe(1e200, 50, 0, 3) <= 1.0)


class ExpectedMaxSharpe(unittest.TestCase):
    def test_one_trial_is_not_a_selection(self):
        self.assertEqual(expected_max_sharpe([]), 0.0)
        self.assertEqual(expected_max_sharpe([0.7]), 0.0)
        self.assertEqual(expected_max_sharpe([0.1, 0.9], n_trials=1), 0.0)
        self.assertEqual(expected_max_sharpe([0.1, 0.9], n_trials=0), 0.0)
        self.assertEqual(expected_max_sharpe([], n_trials=1, fallback_variance=1.0), 0.0)

    def test_formula_by_hand(self):
        # N = 2: Z^-1(1/2) = 0, so only the second term is left
        g = 0.5772156649
        expected = g * NORMAL.inv_cdf(1 - 1 / (2 * math.e))
        self.assertAlmostEqual(expected_max_sharpe([], 2, fallback_variance=1.0), expected, places=9)
        self.assertAlmostEqual(expected_max_sharpe([], 2, fallback_variance=1.0), 0.519755, delta=1e-6)
        # N = 10, V = 0.25: 0.5 * (0.42278 * 1.28155 + 0.57722 * 1.78913) = 0.78730
        self.assertAlmostEqual(expected_max_sharpe([], 10, fallback_variance=0.25), 0.78730, delta=1e-5)

    def test_close_to_the_true_expected_maximum_of_normals(self):
        # E[max of N standard normals], from tables of normal order statistics
        for n, truth in ((10, 1.53875), (100, 2.50759), (1000, 3.24144)):
            self.assertAlmostEqual(expected_max_sharpe([], n, fallback_variance=1.0), truth, delta=0.04)

    def test_uses_the_sample_variance_of_the_trials(self):
        trials = [0.1, 0.3, -0.2, 0.05, 0.4]
        mean = sum(trials) / 5
        variance = sum((s - mean) ** 2 for s in trials) / 4
        unit = expected_max_sharpe([], 5, fallback_variance=1.0)
        self.assertAlmostEqual(expected_max_sharpe(trials), math.sqrt(variance) * unit, places=12)
        # a floor below the measured variance (0.05425) changes nothing
        self.assertEqual(expected_max_sharpe(trials, fallback_variance=0.01), expected_max_sharpe(trials))
        self.assertEqual(expected_max_sharpe(trials, fallback_variance=variance), expected_max_sharpe(trials))
        # n_trials overrides the count and keeps the variance
        self.assertAlmostEqual(
            expected_max_sharpe(trials, 50), math.sqrt(variance) * expected_max_sharpe([], 50, fallback_variance=1.0),
            places=12,
        )

    def test_the_fallback_variance_is_a_floor(self):
        # Variants of one idea move together: their Sharpes spread less than sampling noise alone
        # would spread them, and that must not lower the bar. V = max(measured, fallback).
        unit = expected_max_sharpe([], 5, fallback_variance=1.0)
        huddled = [0.100, 0.101, 0.102, 0.103, 0.104]  # sample variance 2.5e-6
        self.assertAlmostEqual(expected_max_sharpe(huddled), math.sqrt(2.5e-6) * unit, places=12)
        for floor in (0.004, 99.0):
            floored = expected_max_sharpe(huddled, fallback_variance=floor)
            self.assertAlmostEqual(floored, math.sqrt(floor) * unit, places=12)
        # never decreasing in the floor, and never below the count-only benchmark
        floors = [0.0, 1e-9, 2.5e-6, 1e-4, 0.004, 0.05, 1.0]
        values = [expected_max_sharpe(huddled, fallback_variance=f) for f in floors]
        self.assertEqual(values, sorted(values))
        for f in floors:
            self.assertGreaterEqual(
                expected_max_sharpe(huddled, fallback_variance=f), expected_max_sharpe([], 5, fallback_variance=f)
            )

    def test_fallback_when_the_variance_cannot_be_measured(self):
        self.assertEqual(expected_max_sharpe([0.2, 0.2, 0.2]), 0.0)  # no variance and no fallback
        self.assertGreater(expected_max_sharpe([0.2, 0.2, 0.2], fallback_variance=0.01), 0.0)
        self.assertGreater(expected_max_sharpe([0.2], 40, fallback_variance=0.01), 0.0)
        self.assertEqual(expected_max_sharpe([0.2], 40, fallback_variance=-1.0), 0.0)
        self.assertEqual(expected_max_sharpe([0.2], 40, fallback_variance=math.nan), 0.0)
        # trials whose Sharpe is undefined still count as trials
        self.assertAlmostEqual(
            expected_max_sharpe([0.1, None, 0.5, math.nan]), expected_max_sharpe([0.1, 0.5], 4), places=15
        )

    def test_grows_with_the_number_of_trials(self):
        values = [expected_max_sharpe([], n, fallback_variance=0.04) for n in (2, 3, 5, 10, 100, 10_000, 10 ** 9)]
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))
        self.assertTrue(math.isfinite(values[-1]))


class DeflatedSharpe(unittest.TestCase):
    def setUp(self):
        rng = random.Random(42)
        self.xs = [rng.gauss(0.15, 1.0) for _ in range(250)]

    def test_shape_and_consistency(self):
        trials = [0.02, -0.05, 0.11, 0.07, -0.01, 0.15]
        d = deflated_sharpe(self.xs, trials)
        self.assertEqual(set(d), {"sharpe", "n", "skew", "kurt", "benchmark", "dsr", "trials"})
        self.assertEqual(d["n"], 250)
        self.assertEqual(d["trials"], 6)
        self.assertEqual(d["sharpe"], sharpe(self.xs))
        self.assertEqual(d["skew"], skewness(self.xs))
        self.assertEqual(d["kurt"], kurtosis(self.xs))
        self.assertEqual(d["benchmark"], expected_max_sharpe(trials, fallback_variance=1 / 250))
        self.assertEqual(d["dsr"], probabilistic_sharpe(d["sharpe"], 250, d["skew"], d["kurt"], d["benchmark"]))
        self.assertTrue(0.0 < d["dsr"] < 1.0)

    def test_a_single_trial_is_the_plain_probabilistic_sharpe(self):
        d = deflated_sharpe(self.xs, [sharpe(self.xs)])
        self.assertEqual(d["benchmark"], 0.0)
        self.assertEqual(d["dsr"], probabilistic_sharpe(d["sharpe"], 250, d["skew"], d["kurt"]))
        self.assertEqual(deflated_sharpe(self.xs, [])["dsr"], d["dsr"])

    def test_undefined_sharpe_is_none(self):
        self.assertIsNone(deflated_sharpe([], [0.1, 0.2]))
        self.assertIsNone(deflated_sharpe([0.01], [0.1, 0.2]))
        self.assertIsNone(deflated_sharpe([0.01] * 30, [0.1, 0.2]))
        self.assertIsNone(deflated_sharpe([0.01, math.nan, 0.02], [0.1, 0.2]))

    def test_short_series_fall_back_to_normal_moments(self):
        d = deflated_sharpe([0.01, 0.03], [])
        self.assertEqual((d["skew"], d["kurt"]), (0.0, 3.0))
        d = deflated_sharpe([0.01, 0.03, 0.02], [])
        self.assertEqual(d["kurt"], 3.0)
        self.assertIsNotNone(d["skew"])

    def test_more_trials_never_raise_it_at_a_fixed_variance(self):
        # Lists of 2k trials, -s and +s in turn, with s chosen so that every list has the same sample
        # variance V: s^2 * 2k / (2k - 1) = V. Only the count changes, so the DSR may only fall.
        # (V = 0.01 is above the 1 / 250 floor, so it is the measured variance that is in use.)
        variance = 0.01
        previous = None
        for k in (1, 2, 3, 5, 10, 50, 200, 1000):
            s = math.sqrt(variance * (2 * k - 1) / (2 * k))
            d = deflated_sharpe(self.xs, [-s, s] * k)
            self.assertEqual(d["trials"], 2 * k)
            if previous is not None:
                self.assertLess(d["dsr"], previous["dsr"])
                self.assertGreater(d["benchmark"], previous["benchmark"])
            previous = d
        self.assertLess(previous["dsr"], deflated_sharpe(self.xs, [])["dsr"])

    def test_more_trials_never_raise_it_by_count(self):
        trials = [0.02, -0.05, 0.11, 0.07, -0.01, 0.15]
        values = [deflated_sharpe(self.xs, trials, n)["dsr"] for n in (1, 2, 6, 20, 100, 1000, 10 ** 6)]
        self.assertTrue(all(a > b for a, b in zip(values, values[1:])))
        # with nothing but a count, the fallback variance 1 / n carries the deflation
        by_count = [deflated_sharpe(self.xs, [], n)["dsr"] for n in (1, 2, 10, 100, 10_000)]
        self.assertTrue(all(a > b for a, b in zip(by_count, by_count[1:])))
        self.assertAlmostEqual(
            deflated_sharpe(self.xs, [], 100)["benchmark"],
            math.sqrt(1 / 250) * expected_max_sharpe([], 100, fallback_variance=1.0), places=14,
        )

    def test_listing_the_trials_never_lowers_the_bar_a_bare_count_sets(self):
        # The variance of the trials is floored at 1 / n, so trials that huddle together deflate
        # exactly as much as their count alone, and trials that spread wider deflate more.
        by_count = deflated_sharpe(self.xs, [], 6)
        huddled = deflated_sharpe(self.xs, [0.100, 0.101, 0.102, 0.103, 0.104, 0.105])
        spread = deflated_sharpe(self.xs, [0.02, -0.25, 0.31, 0.07, -0.11, 0.15])
        self.assertEqual(huddled["benchmark"], by_count["benchmark"])
        self.assertEqual(huddled["dsr"], by_count["dsr"])
        self.assertAlmostEqual(
            by_count["benchmark"], math.sqrt(1 / 250) * expected_max_sharpe([], 6, fallback_variance=1.0), places=14
        )
        self.assertGreater(spread["benchmark"], by_count["benchmark"])
        self.assertLess(spread["dsr"], by_count["dsr"])

    def test_the_best_of_many_unskilled_trials_does_not_pass(self):
        # 200 strategies with no edge at all, 120 observations each. The best one looks good on
        # its own (PSR against zero above 0.95) and must not once every trial is counted.
        rng = random.Random(1234)
        runs = [[rng.gauss(0.0, 1.0) for _ in range(120)] for _ in range(200)]
        sharpes = [sharpe(run) for run in runs]
        best = runs[sharpes.index(max(sharpes))]
        alone = deflated_sharpe(best, [])
        counted = deflated_sharpe(best, sharpes)
        self.assertGreater(alone["dsr"], 0.95)
        self.assertLess(counted["dsr"], 0.8)
        self.assertAlmostEqual(counted["benchmark"], max(sharpes), delta=0.08)


class QuarterKelly(unittest.TestCase):
    def test_a_quarter_of_mean_over_variance(self):
        self.assertAlmostEqual(quarter_kelly(0.01, 0.04), 0.0625, places=15)
        self.assertAlmostEqual(quarter_kelly(0.01, 0.04, fraction=0.5), 0.125, places=15)
        self.assertAlmostEqual(quarter_kelly(0.01, 0.04, fraction=1.0), 0.25, places=15)

    def test_capped(self):
        self.assertEqual(quarter_kelly(0.5, 0.01), 1.0)
        self.assertEqual(quarter_kelly(0.5, 0.01, cap=0.2), 0.2)
        self.assertEqual(quarter_kelly(0.5, 0.01, cap=0.0), 0.0)
        self.assertEqual(quarter_kelly(0.5, 0.01, cap=-1.0), 0.0)
        self.assertEqual(quarter_kelly(1e300, 1e-300), 1.0)

    def test_no_edge_no_size(self):
        self.assertEqual(quarter_kelly(0.0, 0.04), 0.0)
        self.assertEqual(quarter_kelly(-0.01, 0.04), 0.0)
        self.assertEqual(quarter_kelly(0.01, 0.0), 0.0)
        self.assertEqual(quarter_kelly(0.01, -0.04), 0.0)
        self.assertEqual(quarter_kelly(math.nan, 0.04), 0.0)
        self.assertEqual(quarter_kelly(0.01, math.nan), 0.0)
        self.assertEqual(quarter_kelly(math.inf, 0.04), 0.0)
        self.assertEqual(quarter_kelly(0.01, 0.04, fraction=-0.25), 0.0)

    def test_sized_on_the_bound_is_smaller_than_sized_on_the_mean(self):
        rng = random.Random(9)
        xs = [rng.gauss(0.02, 0.1) for _ in range(100)]
        b = mean_bounds(xs, 0.05)
        self.assertLess(quarter_kelly(b["lcb"], b["sd"] ** 2), quarter_kelly(b["mean"], b["sd"] ** 2))


class CusumDecay(unittest.TestCase):
    def test_on_target_stays_quiet(self):
        c = cusum_decay([0.0] * 100, reference_mean=0.0, sd=1.0)
        self.assertEqual(c, {"statistic": 0.0, "last": 0.0, "alarm": False, "at": None})
        better = cusum_decay([2.0] * 100, reference_mean=0.0, sd=1.0)
        self.assertEqual(better, {"statistic": 0.0, "last": 0.0, "alarm": False, "at": None})

    def test_one_sd_short_alarms_on_the_eighth(self):
        # each step adds 1 - 0.5 = 0.5: s reaches h = 4 at the eighth observation (index 7)
        c = cusum_decay([-1.0] * 8, reference_mean=0.0, sd=1.0)
        self.assertEqual(c, {"statistic": 4.0, "last": 4.0, "alarm": True, "at": 7})
        self.assertFalse(cusum_decay([-1.0] * 7, reference_mean=0.0, sd=1.0)["alarm"])
        self.assertEqual(cusum_decay([-1.0] * 20, 0.0, 1.0)["at"], 7)
        self.assertEqual(cusum_decay([-1.0] * 20, 0.0, 1.0)["statistic"], 10.0)

    def test_scale_and_reference(self):
        c = cusum_decay([0.01] * 8, reference_mean=0.03, sd=0.02)  # the same one sd short
        self.assertAlmostEqual(c["last"], 4.0, places=12)
        self.assertEqual(cusum_decay([0.01] * 8, 0.03, 0.02, k=1.0)["last"], 0.0)  # all of it forgiven
        # (0.03 - 0.01) / 0.02 is a hair under 1 in floats, so four steps stop a hair under h = 4
        self.assertTrue(cusum_decay([0.01] * 5, 0.03, 0.02, k=0.0)["alarm"])
        self.assertEqual(cusum_decay([0.01] * 5, 0.03, 0.02, k=0.0)["at"], 4)
        self.assertFalse(cusum_decay([0.01] * 8, 0.03, 0.02, h=4.5)["alarm"])

    def test_recovery_clears_the_alarm_but_keeps_the_crossing(self):
        c = cusum_decay([-1.0] * 10 + [3.0] * 5, reference_mean=0.0, sd=1.0)
        self.assertEqual(c["statistic"], 5.0)
        self.assertEqual(c["last"], 0.0)
        self.assertFalse(c["alarm"])
        self.assertEqual(c["at"], 7)

    def test_it_resets_at_zero_and_does_not_bank_good_luck(self):
        # a long good run first must not delay the alarm
        late = cusum_decay([5.0] * 50 + [-1.0] * 8, reference_mean=0.0, sd=1.0)
        self.assertTrue(late["alarm"])
        self.assertEqual(late["at"], 57)

    def test_degenerate(self):
        quiet = {"statistic": 0.0, "last": 0.0, "alarm": False, "at": None}
        self.assertEqual(cusum_decay([], 0.0, 1.0), quiet)
        self.assertEqual(cusum_decay([-5.0] * 50, 0.0, 0.0), quiet)
        self.assertEqual(cusum_decay([-5.0] * 50, 0.0, -1.0), quiet)
        self.assertEqual(cusum_decay([-5.0] * 50, 0.0, math.nan), quiet)
        self.assertEqual(cusum_decay([-5.0] * 50, math.nan, 1.0), quiet)
        skipped = cusum_decay([-1.0, math.nan, -1.0], 0.0, 1.0)
        self.assertEqual(skipped["last"], 1.0)

    def test_false_alarm_rate_on_honest_data(self):
        # k = 0.5, h = 4 has an in-control average run length of a few hundred observations: on 50
        # honest points an alarm is rare, and on data one sd short it is near certain.
        rng = random.Random(77)
        def crossings(mean):
            runs = ([rng.gauss(mean, 1) for _ in range(50)] for _ in range(1000))
            return sum(cusum_decay(run, 0.0, 1.0)["at"] is not None for run in runs)

        honest, decayed = crossings(0.0), crossings(-1.0)
        self.assertLess(honest / 1000, 0.2)
        self.assertGreater(decayed / 1000, 0.95)


class MaxDrawdown(unittest.TestCase):
    def test_reference(self):
        self.assertAlmostEqual(max_drawdown([100, 120, 90, 130, 65, 140]), 0.5, places=15)
        self.assertAlmostEqual(max_drawdown([100, 120, 90, 130, 120]), 0.25, places=15)
        self.assertAlmostEqual(max_drawdown([100, 80, 60, 50]), 0.5, places=15)

    def test_no_fall(self):
        self.assertEqual(max_drawdown([]), 0.0)
        self.assertEqual(max_drawdown([100]), 0.0)
        self.assertEqual(max_drawdown([100, 100, 100]), 0.0)
        self.assertEqual(max_drawdown([1, 2, 3, 4]), 0.0)

    def test_zero_and_negative_equity(self):
        self.assertEqual(max_drawdown([100, 0]), 1.0)
        self.assertEqual(max_drawdown([100, -50, 200]), 1.0)  # below zero is still 1, not 1.5
        self.assertEqual(max_drawdown([0, 0, 0]), 0.0)
        self.assertEqual(max_drawdown([-5, -10]), 0.0)  # no positive peak to fall from
        self.assertAlmostEqual(max_drawdown([0, -5, 100, 90]), 0.1, places=15)
        self.assertAlmostEqual(max_drawdown([100, math.nan, 90, math.inf, 95]), 0.1, places=15)

    def test_bounded(self):
        rng = random.Random(2)
        for _ in range(100):
            equity = [rng.uniform(-50, 200) for _ in range(30)]
            self.assertTrue(0.0 <= max_drawdown(equity) <= 1.0)


if __name__ == "__main__":
    unittest.main()
