"""CHECK #1 (synthetic only): PREREG-EVL-6 section 3's fixed demotion reads (cumulative mean r of the stay's Probe+
events < 0 at the 100th, 200th, ...), with the residual day shock the promotion calibration itself uses (the judge's
demotion_check.py has only a 1% market move). 6 Probe events a session; r = edge + b_t + h_t (c_t + e) + jumps;
b_t ~ N(4 bp, 1%); c_t = sd_c z_t, z AR(0.10) t(3) (rho_day share of event variance V0 = 0.0027); e = sigma_i t(3),
sigma_i log-uniform 1-10%; +-30% jumps at 0.5% (mean-compensated); optional drift AR(0.97) sd 20 bp."""
import math, numpy as np
V0 = 0.0027
def run(edge, rho, drift_sd=0.0, R=20000, N=1000, per=6, seed=7):
    rng = np.random.default_rng(seed)
    T = N // per + 1
    sd_c = math.sqrt(rho / (1 - rho) * V0) if rho > 0 else 0.0
    z = rng.standard_t(3, R) / math.sqrt(3); D = rng.standard_normal(R) * drift_sd; lv = rng.standard_normal(R) * 0.3
    sess = np.empty((R, T))
    for t in range(T):
        z = 0.10 * z + math.sqrt(1 - 0.01) * rng.standard_t(3, R) / math.sqrt(3)
        D = 0.97 * D + math.sqrt(1 - 0.97 ** 2) * drift_sd * rng.standard_normal(R)
        lv = 0.9 * lv + math.sqrt(1 - 0.81) * 0.3 * rng.standard_normal(R)
        sess[:, t] = edge + D + rng.normal(0.0004, 0.01, R) + np.exp(lv - 0.09) * sd_c * z
    sig = np.exp(rng.uniform(math.log(0.01), math.log(0.10), (R, N)))
    e = sig * rng.standard_t(3, (R, N)) / math.sqrt(3)
    hit = rng.random((R, N)) < 0.005
    e = e + hit * np.where(rng.random((R, N)) < 0.5, -0.3, 0.3)
    r = np.repeat(sess, per, axis=1)[:, :N] + e
    c = np.cumsum(r, axis=1)
    out = {}
    dem = np.zeros(R, bool)
    for k in range(100, N + 1, 100):
        dem |= c[:, k - 1] / k < 0
        if k in (100, 200, 300, 500, 1000):
            out[k] = round(float(dem.mean()), 3)
    return out
for rho in (0.0, 0.05, 0.15):
    for edge in (0.006, 0.010, 0.0):
        for dsd in (0.0, 0.002):
            print(f"rho {rho:.2f} edge {edge*1e4:4.0f} bp drift {dsd*1e4:2.0f} bp: P(demoted by the k-th Probe event) {run(edge, rho, dsd)}", flush=True)
