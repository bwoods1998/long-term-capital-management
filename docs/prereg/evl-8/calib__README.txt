PREREG-EVL-8's calibration (the judge's; SYNTHETIC ONLY: nothing here read the lane, the House, the gateway or any run record)
evl6d.py         PREREG-EVL-6's screen exactly as its draft states it (looks 6..60, alpha 0.016/0.004, 10 bp margin, guards,
                 retirement, exhaustion at 60), with `looks`, `alpha_fn`, `margin` arguments; chain() = v1 -> v2 -> v3; selftest
px8.py           the PX seats under that screen and its variants, on ../price/px_calib.py's generator (imported unchanged; the
                 judge adds the cell 'worstnotau'); PX8_RULE picks the screen, PX8_SEED the seed base
                 px8_evl6.jsonl (seeds 83,000,001 on, R 2,000 null / 1,000 power): the draft rule as written
                 px8_{a10,a08,a12m15,a10m15,s10,s12,s10a12,s12a12}.jsonl, px8_{s15,s14,s14a12,s12,evl6}_v3.jsonl: variants
                 (same seeds); px8_s15_confirm.jsonl: THE CHOSEN PX SCREEN (s15) on FRESH seeds 84,000,001 on, R 4,000 / 2,000
meta8.py         the meta-learners (../meta/calib_meta.py simulate, imported unchanged) under the same screen, its successor chain
                 and PREREG-EVL-3's screen: meta8_null.jsonl (93,000,001; R 2,000), meta8_power.jsonl (95,000,001; R 600),
                 meta8_tune.jsonl (96,000,001; R 600; WARM 20 and 30), meta8_stress.jsonl (94,000,001; R 600)
placebo8.py      the placebo audit and the control canary under THE PX SCREEN (seeds 97,000,001 on): placebo8_s15.out.json
ev8_sim.py       the done-speed synthesis simulator (/dev/shm/speed-synth/synth_sim.py, copied) with PREREG-EVL-8's five seats,
ev8_drive.py     PREREG-EVL-6's schedule as drafted, THE PX SCREEN, learning room 4: ev8_px_a=(0.016,0.004)_px_first=15_1000_98000001.json
px_grid8.py      the PX record grid with the judge's text fixes -> px_grid8.json (canonical sha256 bb0d50e4...; px_grid8.out)
report8.py       -> calib8.report.txt (every table)
run_*.sh, chain*.sh   the order the judge ran them in (at most 4 workers at a time)
ev8_mix.py       an ILLUSTRATIVE mixture of ev8_drive scenarios under the judge's stated weights -> ev8_mix.out
