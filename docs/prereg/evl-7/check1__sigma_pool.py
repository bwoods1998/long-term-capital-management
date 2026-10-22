"""sigma_pool.py: the mean sigma of the generator's pool (log-uniform from 1% to sig_hi), against which the learner's
picks' mean sigma (calib_check1.py report, 'sig_picks') is compared; and COST-7's impact understatement factor for the
picks when IMP reads sigma60 = NULL -> 0.04 (universe.py writes sigma60 NULL on rel/1019g)."""
import math
for hi, picks in ((0.10, (0.053, 0.056)), (0.20, (0.104, 0.104))):
    m = (hi - 0.01) / math.log(hi / 0.01)
    print(f"sigma log-uniform 1%-{hi:.0%}: pool mean {m:.4f}; learner picks {picks[0]:.3f}-{picks[1]:.3f} "
          f"({picks[0] / m:.2f}-{picks[1] / m:.2f}x the pool); IMP at 0.04 understates the picks' impact by "
          f"{picks[0] / 0.04:.2f}-{picks[1] / 0.04:.2f}x")
