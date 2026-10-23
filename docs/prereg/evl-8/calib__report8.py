#!/usr/bin/env python
"""report8.py: the PREREG-EVL-8 judge's tables from px8_*.jsonl and meta8_*.jsonl (synthetic calibration only).
Writes calib8.report.txt beside it."""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
out = []


def load(path):
    return [json.loads(x) for x in open(path) if x.strip()]


def p(*a):
    out.append(" ".join(str(x) for x in a))


p("PREREG-EVL-8 CALIBRATION (synthetic only; nothing here read the lane)")
p("=" * 100)
for f in sorted(glob.glob(os.path.join(HERE, "px8_*.jsonl"))):
    rows = load(f)
    if not rows:
        continue
    rule = rows[0].get("rule", "?")
    p(f"\nPX seats under rule {rule} ({os.path.basename(f)}): FALSE PASSES within 120 sessions (pass | by20 | chain of 3)")
    for r in sorted((x for x in rows if x["kind"] == "null"), key=lambda x: (x["noise"], x["lam"], x["cell"])):
        p(f"  {r['cell']:24s} R {r['R']:5d}  pass {r['pass']:.3f}  by20 {r['by20']:.3f}  by60 {r['by60']:.3f}  "
          f"chain3 {r.get('chain3_pass', float('nan')):.3f}")
    pw = [x for x in rows if x["kind"] == "power"]
    if pw:
        p(f"  POWER (P(pass) by session 20 / 40 / 60 / 120; median pass session):")
        for r in sorted(pw, key=lambda x: (x["noise"], x["lam"], x["mu_bp"])):
            p(f"  {r['cell']:24s} R {r['R']:5d}  {r['by20']:.3f} / {r['by40']:.3f} / {r['by60']:.3f} / {r['pass']:.3f}  "
              f"med {r['median_pass_session']}")
for g in ("null", "stress", "power", "tune"):
    f = os.path.join(HERE, f"meta8_{g}.jsonl")
    if not os.path.exists(f):
        continue
    rows = load(f)
    p(f"\nMETA ({g}): EVL-6 as drafted (e6), its v1->v2->v3 chain (ch), PREREG-EVL-3 minus skew (e3); "
      f"pass | pass given true mean <= 0; by20/60/120; picks a session; picks' true mean bp")
    for r in rows:
        e6, ch, e3 = r["e6"], r["ch"], r["e3"]
        p(f"  {r['cell']:32s} R {r['R']:5d} | e6 {e6['pass']:.3f} |0 {e6['pass_given_null']:.3f} "
          f"({e6['by20']:.3f}/{e6['by60']:.3f}/{e6['by120']:.3f}) | ch {ch['pass']:.3f} |0 {ch['pass_given_null']:.3f} | "
          f"e3 {e3['pass']:.3f} |0 {e3['pass_given_null']:.3f} | picks {r['picks_per_session']:.2f} "
          f"true {r['true_mean_picks_bp'] if r['true_mean_picks_bp'] is None else round(r['true_mean_picks_bp'], 1)} "
          f"null {r['null_share']:.2f}")
pf = os.path.join(HERE, "placebo8_s15.out.json")
if os.path.exists(pf):
    p("\nPLACEBO AUDIT AND CANARY under THE PX SCREEN (placebo8.py; alarm = >= 3 of 8 placebos passed or the canary)")
    for r in json.load(open(pf))["rows"]:
        p(f"  lift {r['delta_bp']:+5.0f} bp drift {r['drift_bp']:4.0f} bp crash {r['crash']!s:5s} | single {r['single']:.3f} "
          f"| >=3 {r['ge3']:.3f} | canary {r['canary']:.3f} | ALARM {r['audit_ge3_or_canary']:.3f}")
for ef in sorted(glob.glob(os.path.join(HERE, "ev8_*.json"))):
    res = json.load(open(ef))["res"]
    p(f"\nEXPECTED VALUE ({os.path.basename(ef)}; 1,000 runs a scenario): P(Done by 40/60/120) E[min(T,121)] | "
      f"true/false promotions, EVL-8's | P&L mean / p05 | worst-20 p5 | P(false Done)")
    for k, r in res.items():
        p(f"  {k:14s} {r['P_done_40']:.3f}/{r['P_done_60']:.3f}/{r['P_done_H']:.3f} {r['mean_T_capped']:6.1f} | "
          f"{r['true_promo_mean']:.2f}/{r['false_promo_mean']:.3f}, {r['evl8_promo_mean']:.3f} ({r['evl8_counted_mean']:.0f} counted) | "
          f"{r['pnl_mean']:+.0f} / {r['pnl_p05']:+.0f} | {r['worst20_p5']:+.0f} | {r['P_false_done']:.3f}")
open(os.path.join(HERE, "calib8.report.txt"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
