#!/bin/bash
# Copy every script and output PREREG-EVL-9 cites into goal-2026-10-19/prereg/evl-9/ (flat; this file's own from final/
# under their names, the checks' and the design record's with the prefixes check1__, check2__, scout__, data__,
# learners__, redteam__, judge__, and the imported or copied generators with evl7learner__, evl7final__, evl7reader__),
# with SHA256SUMS. The scout's 1.57 GB submissions.zip is cited by its sha256, not copied.
set -e
cd "$(dirname "$0")"
DST=../../prereg/evl-9
mkdir -p "$DST"
cp -p calib_w9.py select_w9.py table_w9.py g2_w9.py oof_w9.py count_w7_gap.py form4map_w9.py timing9.py budget9.py \
      run_w9a.sh run_w9b.sh copy_w9.sh "$DST"/
for f in w9.*.jsonl w9.*.log w9.selected.json w9.refs.json w9.report.txt w9.tables.md select_w9.select.out select_w9.w9.out \
         g2_w9.out.json oof_w9.out.json count_w7_gap.out.json form4map_w9.out.json timing9.out budget9.out run_w9a.log run_w9b.log; do
  [ -e "$f" ] && cp -p "$f" "$DST"/
done
for d in check1 check2; do
  for f in ../$d/*.py ../$d/*.sh ../$d/*.json ../$d/*.jsonl ../$d/*.log ../$d/*.log? ../$d/*.txt ../$d/*.done; do
    [ -e "$f" ] && cp -p "$f" "$DST/${d}__$(basename "$f")"
  done
done
for f in ../scout/*.py ../scout/*.json ../scout/*.log ../scout/submissions.zip.sha256; do
  [ -e "$f" ] && cp -p "$f" "$DST/scout__$(basename "$f")"
done
for d in data learners redteam judge; do
  for f in ../$d/*.py ../$d/*.sh ../$d/*.json ../$d/*.jsonl ../$d/*.log ../$d/*.out ../$d/*.txt; do
    [ -e "$f" ] && cp -p "$f" "$DST/${d}__$(basename "$f")"
  done
done
cp -p ../../evl7/learner/calib_learner.py "$DST/evl7learner__calib_learner.py"
cp -p evl7final__calib_w7.py.snapshot "$DST/evl7final__calib_w7.py.snapshot"
cp -p ../../evl7/reader/features_spec.py "$DST/evl7reader__features_spec.py"
cp -p ../PREREG-EVL-9.draft.md "$DST/PREREG-EVL-9.draft.md"
cp -p ../PREREG-EVL-9.md "$DST/PREREG-EVL-9.md"
(cd "$DST" && rm -f SHA256SUMS && sha256sum $(ls | grep -v '^SHA256SUMS$') > SHA256SUMS)
echo "copied $(ls "$DST" | wc -l) files to $DST"
