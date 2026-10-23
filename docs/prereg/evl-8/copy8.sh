#!/bin/bash
# Stage PREREG-EVL-8's calibration record flat in goal-2026-10-19/prereg/evl-8/ (copied into docs/prereg/evl-8/ at the
# freeze), with SHA256SUMS. This round's files under their own names; the cited earlier records with prefixes.
set -e
E8=/home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl8
OUT=/home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/prereg/evl-8
mkdir -p "$OUT"
cd "$E8/final"
for f in px_final8.py px_select8.py px_demotion8.py meta_final8.py calib_meta_f8.py placebo8f.py timing8.py budget8.py \
         report8f.py chain8.sh copy8.sh README.txt \
         px8f.*.jsonl px8f.*.log px8f.choose.json px_select8.*.log px_demotion8.json px_demotion8.out \
         meta8f.*.jsonl meta8f.*.log placebo8f_F22.out.json placebo8f.log timing8.out budget8.out report8f.txt \
         meta_life8.py calib_meta_b8.py meta8l.life.jsonl meta8l.life.index.jsonl meta8l.life.log meta8l.selftest.out \
         meta8l.ext.jsonl meta8l.ext.index.jsonl meta8l.ext.log \
         px_shared8day.py px_demotion8.s184.json px_demotion8.s184.out timing8b.py timing8b.out budget8b.py \
         budget8b.out chain8b.sh; do
  cp -p $f "$OUT/"
done
# the re-checks' records the final fix's text cites (synthetic)
for f in rc_meta.py calib_meta_rc.py rc_meta.jsonl rc_meta_attack.jsonl rc_meta_attack_long.jsonl rc_shared.py \
         rc_shared.jsonl rc_dem.json rc_px.py rc_px.A.jsonl rc_px.B.jsonl rc_engine.py rc_engine.jsonl; do
  cp -p "$E8/recheck1/$f" "$OUT/recheck1__$f"
done
for f in timing_rc2.py timing_rc2.out; do
  cp -p "$E8/recheck2/$f" "$OUT/recheck2__$f"
done
cp -p "$E8/calib/px_grid8.json" "$E8/calib/px_grid8.py" "$E8/calib/px_grid8.out" "$OUT/"
for f in px8.py evl6d.py meta8.py placebo8.py ev8_sim.py ev8_drive.py ev8_mix.py ev8_mix.out calib8.report.txt report8.py \
         px8_s15_confirm.jsonl px8_evl6.jsonl meta8_null.jsonl meta8_power.jsonl meta8_stress.jsonl meta8_tune.jsonl \
         placebo8_s15.out.json README.txt PREREG-EVL-6.draft.as-read-by-evl8.md; do
  cp -p "$E8/calib/$f" "$OUT/calib__$f"
done
for f in px_c1.py px_c1b.py px_c1.jsonl px_c1b.jsonl demotion_px_c1.py demotion_px_c1.out demotion_px_c1b.py \
         demotion_px_c1b.out meta_c1.py meta_c1.jsonl calib_meta_c1.py; do
  cp -p "$E8/check1/$f" "$OUT/check1__$f"
done
cp -p "$E8/check2/budget_check.py" "$OUT/check2__budget_check.py"
for f in px_calib.py px_calib.report.txt fees_and_requests.py fees_and_requests.out count_universe.py px_supply.py \
         px_supply.out; do
  cp -p "$E8/price/$f" "$OUT/price__$f"
done
for f in calib_meta.py meta_spec.py grid_count.py grid_count.out calib_meta.report.txt; do
  cp -p "$E8/meta/$f" "$OUT/meta__$f"
done
for f in "$E8"/redteam/rt_*; do
  cp -p "$f" "$OUT/redteam__$(basename "$f")"
done
cp -p /home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl7/learner/calib_learner.py "$OUT/evl7learner__calib_learner.py"
cd "$OUT" && rm -f SHA256SUMS && sha256sum $(ls | grep -v '^SHA256SUMS$') > SHA256SUMS
echo "staged $(ls | wc -l) files in $OUT"
