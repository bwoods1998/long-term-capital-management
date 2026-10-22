#!/usr/bin/env python
"""report_learner.py: tables from calib_learner.py's outputs (synthetic only)."""
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def se(p, n):
    return math.sqrt(max(p * (1 - p), 1e-12) / n)


def main(paths):
    for path in paths:
        print(f"== {os.path.basename(path)}")
        for line in open(path):
            d = json.loads(line)
            c = d["cell"]
            R = d["R"]
            parts = [f"{c['name']:<34} R={R:<5} ev/s={d['events_per_session']:.2f} picks%={100*d['sessions_with_picks']:.0f}"
                     f" mean_a={d['mean_a_picks_bp']:.1f}bp ctrl={d['mean_ctrl_bp']:.1f}bp"]
            for rule in ("EVL3", "L12", "E840"):
                s = d[rule]
                extra = " ".join(f"{k}={v:.3f}" for k, v in s.items() if k.startswith("by"))
                parts.append(f"   {rule:<5} pass={s['pass']:.4f} (se {se(s['pass'], R):.4f}) retired={s['retired']:.3f} "
                             f"{extra} med={s.get('median_pass_session', '-')}")
            for rule in ("L12x3", "E840x3"):
                if rule in d:
                    s = d[rule]
                    parts.append(f"   {rule:<6} pass={s['pass']:.4f} (se {se(s['pass'], R):.4f}) versions={s['versions_mean']:.2f} "
                                 + " ".join(f"{k}={v:.3f}" for k, v in s.items() if k.startswith("by")))
            for key in ("curve_edge", "oracle_edge", "fixed_edge", "curve_ic"):
                if key in d:
                    parts.append(f"   {key:<12} " + " ".join(f"{k}:{v}" for k, v in d[key].items()))
            print("\n".join(parts))


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(glob.glob(os.path.join(HERE, "calib_learner.*.jsonl"))))
