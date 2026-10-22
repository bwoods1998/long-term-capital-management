#!/bin/bash
# copy_ff.sh: the final minimal fix's copy step. Runs the fix round's copy_w9.sh (which copies the design record, the
# checks, the fix round's calibration and PREREG-EVL-9.md into goal-2026-10-19/prereg/evl-9/), then copies every file of
# evl9/final/ff/ the text names (prefix ff__) and the re-checks' scripts and outputs (prefixes recheck1__, recheck2__;
# not recheck2/code/, rel/1019h's code at its commit), writes SHA256SUMS.ff here and rewrites SHA256SUMS there.
set -e
cd "$(dirname "$0")"
DST=../../../prereg/evl-9
bash ../copy_w9.sh
for f in calib_w9ff.py select_w9ff.py table_w9ff.py base_w9ff.py gaps_w9ff.py g2_w9ff.py timing9ff.py budget9ff.py \
         chain_ff.sh chain_ff2.sh copy_ff.sh chain_ff2.log \
         ff.search.jsonl ff.fresh1.jsonl ff.fresh2.jsonl ff.life.jsonl ff.coldref.jsonl ff.power.jsonl ff.stress.jsonl \
         ff.base.jsonl ff.search.log ff.fresh1.log ff.fresh2.log ff.life.log ff.coldref.log ff.power.log ff.stress.log \
         ff.base.log ff.selected1.json ff.selected2.json ff.select1.out ff.select2.out ff.w9.out ff.lifecells.json \
         ff.coldcells.json ff.report.txt ff.base.report.txt ff.tables.md gaps_w9ff.out g2_w9ff.out g2_w9ff.out.json \
         timing9ff.out budget9ff.out recheck1_result.json recheck2_result.json fixer_result.json \
         PREREG-EVL-9.as-rechecked.md; do
  cp -p "$f" "$DST/ff__$f"
done
for f in ../../recheck1/*.py ../../recheck1/*.sh ../../recheck1/*.out ../../recheck1/*.jsonl ../../recheck1/*.log \
         ../../recheck1/SHA256SUMS.rc9; do
  [ -e "$f" ] && cp -p "$f" "$DST/recheck1__$(basename "$f")"
done
for f in ../../recheck2/*.py ../../recheck2/*.out ../../recheck2/*.md; do
  [ -e "$f" ] && cp -p "$f" "$DST/recheck2__$(basename "$f")"
done
rm -f SHA256SUMS.ff
sha256sum $(ls | grep -v -e '^SHA256SUMS.ff$' -e '^__pycache__$') > SHA256SUMS.ff
(cd "$DST" && rm -f SHA256SUMS && sha256sum $(ls | grep -v '^SHA256SUMS$') > SHA256SUMS)
echo "copied; $(ls "$DST" | wc -l) files in $DST"
