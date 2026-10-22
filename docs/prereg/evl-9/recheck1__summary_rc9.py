#!/usr/bin/env python
"""summary_rc9.py: RE-CHECK 1 of PREREG-EVL-9, the summary (SYNTHETIC ONLY): every cell of this re-check's rc9.*.jsonl
(fresh seeds 761e6 / 771e6 / 781e6) with its run-1 rate and SE, and, for the cells the fixer also ran on fresh seeds
(evl9/final/w9.fresh.jsonl, 402e6), the pooled rate of both fresh sets."""
import glob, json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "final"))
import calib_w9 as w  # noqa: E402


def load(path):
    by = {}
    for line in open(path):
        r = json.loads(line)
        by.setdefault(r["cell"], []).append(r)
    return by


fx = load(os.path.join(HERE, "..", "final", "w9.fresh.jsonl"))
for path in sorted(glob.glob(os.path.join(HERE, "rc9.*.jsonl"))):
    print("==", os.path.basename(path))
    by = load(path)
    for name, parts in sorted(by.items(), key=lambda kv: -w.summarise(kv[1])["run1"]):
        s = w.summarise(parts)
        line = (f"{name:<78} R={s['R']:<5} RUN1 {s['run1']:.4f} (se {s['run1_se']:.4f}) cm<=0 {s['cm0']:.4f} "
                f"cm<=10bp {s['cm10']:.4f} | v120 {s['v120']:.4f} | ev/s {s['ev_s']:.2f} tau {s['tau_bp']:+.1f}bp "
                f"sig {s['sig']:.3f}")
        extra = [p.get("taus_corr_live") for p in parts if p.get("taus_corr_live") is not None]
        if extra:
            line += f" | TAUS corr(g, live tau/sig) {sum(extra) / len(extra):.3f}"
        print(line)
        if name in fx:
            f = w.summarise(fx[name])
            n = s["R"] + f["R"]
            pooled = (s["run1"] * s["R"] + f["run1"] * f["R"]) / n
            print(f"    pooled with the fixer's fresh {f['run1']:.4f} (R {f['R']}): {pooled:.4f} (se "
                  f"{math.sqrt(pooled * (1 - pooled) / n):.4f}, R {n})")
