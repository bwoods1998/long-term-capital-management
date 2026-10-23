#!/bin/bash
# Copy PREREG-EVL-7's calibration record flat into goal-2026-10-19/prereg/evl-7/ (section 5.1): this file's own files
# under their names (the final fix round's w7r files and the fix round's w7 files, the latter as history); the lenses',
# judge's, checks' and re-check 1's with prefixes, except calib_learner.py and cost7_today.py (which calib_w7.py and
# cost7_w7.py import) and features_spec.py (which the rule reads); the fix round's aborted stage with the prefix
# aborted__ and the final round's failed first attempt with aborted_w7r__; then SHA256SUMS. (copy_w7r.sh: the final fix round's version of copy_w7.sh.)
set -euo pipefail
E=$HOME/Work/.ltcm-main/goal-2026-10-19/evl7
D=$HOME/Work/.ltcm-main/goal-2026-10-19/prereg/evl-7
mkdir -p "$D"
rm -f "$D"/*
cd "$E/final"
cp calib_w7.py select_w7.py sens_w7.py daylaw_w7.py daylaw_w7.out repro_w7.py repro_w7.out run_w7.sh run_w7c.sh \
   run_w7e.sh run_w7.log run_w7c.log run_w7e.log table_w7.py table_w7.md w7.selected.json select_w7.select.out select_w7.w7.out \
   validate_w7.out w7.report.txt cost7_w7.py cost7_w7.out fp_w7.py fp_w7.out ev_w7.py ev_w7.out "$D"/
for g in search fresh power life stress sens; do cp "w7.$g.jsonl" "w7.$g.log" "$D"/; done
cp run_w7b.sh run_w7b.log copy_w7.sh copy_w7r.sh PREREG-EVL-7.as-rechecked.md "$D"/
cp calib_w7r.py select_w7r.py table_w7r.py table_w7r.md ev_w7r.py ev_w7r.out run_w7r_pilot.sh run_w7r_pilot.out \
   run_w7r.sh run_w7r.out w7r.selected.json select_w7r.select.out select_w7r.w7.out w7r.report.txt \
   w7r.pilot.report.txt facts_w7r.py facts_w7r.out shares_w7r.py shares_w7r.out selftest_w7r.out \
   w7r.search.first.log "$D"/
for g in pilot search fresh life fam power stress sens; do cp "w7r.$g.jsonl" "w7r.$g.log" "$D"/; done
for f in aborted/*; do cp "$f" "$D/aborted__$(basename "$f")"; done
for f in aborted_w7r/*; do cp "$f" "$D/aborted_w7r__$(basename "$f")"; done
cd "$E/recheck1"
for f in rc1.py recur_rc1.py recur_rc1.out run_rc1.sh run_rc1e.sh rc1.report.txt *.jsonl *.log; do
  [ -f "$f" ] && cp "$f" "$D/recheck1__$f"; done
cd "$E/final"
cp "$E/learner/calib_learner.py" "$D"/
cp "$E/calib/cost7_today.py" "$E/calib/cost7_today.out" "$D"/
cp "$E/reader/features_spec.py" "$D"/
cd "$E/learner"
for f in report_learner.py run_all.sh run_rank.sh run_final.sh run_more.sh PREREG-EVL-7-L.draft.txt *.jsonl *.log; do
  [ -f "$f" ] && cp "$f" "$D/learner__$f"; done
cd "$E/calib"
for f in calib_evl7.py run_evl7.sh run_evl7b.sh calib_evl7.report.txt fp_accounting.py fp_accounting.out ev_evl7.py \
  ev_evl7.out *.jsonl *.log; do [ -f "$f" ] && cp "$f" "$D/judge__$f"; done
cd "$E/check1"
for f in calib_check1.py run_check1.sh sigma_pool.py warmup_counts.py check1.report.txt *.jsonl *.log; do
  [ -f "$f" ] && cp "$f" "$D/check1__$f"; done
cd "$E/check2"
for f in check2_phi.py check2_cost.py check2_phi.jsonl check2_phi.log check2_cost.out; do cp "$f" "$D/check2__$f"; done
cd "$E/exec"
for f in simlib.py cal_cost7.py cal_cost7_ref.py check_gvar.py cal_capacity7.py *.out.* *.log check_gvar.out.txt; do
  [ -f "$f" ] && cp "$f" "$D/exec__$f"; done
cd "$D"
sha256sum $(ls | grep -v '^SHA256SUMS$') > SHA256SUMS
echo "$(ls | wc -l) files in $D, $(du -sh . | cut -f1)"
