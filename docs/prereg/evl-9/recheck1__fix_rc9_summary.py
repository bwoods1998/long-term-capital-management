#!/usr/bin/env python
"""fix_rc9_summary.py: RE-CHECK 1 of PREREG-EVL-9 (SYNTHETIC ONLY): the candidate fixes, pooled over rc9.fix.jsonl and
rc9.fix2.jsonl (different fresh seeds, the same cells), rc9.nolev.jsonl when present, and the power cells' P(promoted)
by 25 / 40 / 60 / 120 sessions with the picks' true edge."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "final"))
import calib_w9 as w  # noqa: E402
by = {}
for f in ("rc9.fix.jsonl", "rc9.fix2.jsonl", "rc9.nolev.jsonl"):
    p = os.path.join(HERE, f)
    if os.path.exists(p):
        for line in open(p):
            r = json.loads(line)
            by.setdefault(r["cell"], []).append(r)
for name, parts in sorted(by.items()):
    s = w.summarise(parts)
    if "-ic" in name:
        print(f"{name:<70} R={s['R']:<4} P(promoted) by25/40/60/120 {s['vby25']:.3f}/{s['vby40']:.3f}/{s['vby60']:.3f}/"
              f"{s['vby120']:.3f} | edge bp 1-10 {s['edge_bp'].get('1-10')} 51-60 {s['edge_bp'].get('51-60')} | ev/s {s['ev_s']:.2f}")
    else:
        print(f"{name:<70} R={s['R']:<4} RUN1 {s['run1']:.4f} (se {s['run1_se']:.4f}) v120 {s['v120']:.4f} ev/s {s['ev_s']:.2f} "
              f"tau {s['tau_bp']:+.1f}bp")
