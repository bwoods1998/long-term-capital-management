"""repro_w7.py: the final calib_w7.py redraws stage A's first job exactly (its screen results and summary figures),
though the output-only fields and --resume were added after the search began (synthetic only)."""
import json, sys
sys.path.insert(0, ".")
import calib_w7 as w
cells, seed0 = w.grid("search")
cell, x7 = cells[0]
stored = next(json.loads(l) for l in open("w7.search.jsonl") if json.loads(l)["seed"] == seed0 and json.loads(l)["cell"] == cell.name)
new = w._job((cell, x7, seed0, stored["R"]))
same = all(new["frozen_a7"][k] == stored["frozen_a7"][k] for k in stored["frozen_a7"])
same = same and all(abs(new[k] - stored[k]) < 1e-12 for k in ("ev_s", "npool", "mean_a7_picks_bp", "mean_cm7_picks_bp", "sig_picks"))
print(f"repro {cell.name} seed {seed0} R {stored['R']}: identical = {same}; passes {sum(x >= 0 for x in new['frozen_a7']['when'])}")
