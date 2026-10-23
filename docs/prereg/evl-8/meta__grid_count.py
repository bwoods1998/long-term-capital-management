#!/usr/bin/env python
"""grid_count.py: the exact sizes of PREREG-EVL-8's META grids (singles + cross-group pairs) and expert families.
Outcome-free: counts of features and of registered program versions by hold and auction (programs.py on rel/1019g)."""
import itertools, json
GROUPS_O1 = {"FAM": ["news-on", "news-day", "8k", "ern", "ins", "price"],
             "SCORE": ["s>=1", "s>=2", "s=3", "s<=-1", "smiss"], "GUIDE": ["raised", "lowered"], "SRC": ["bz", "other"],
             "HOUR": ["h16-20", "h20-04", "h04-08", "h08-0930", "h0930-12", "h12-16"], "COV": ["c0", "c1-3", "c4+"],
             "LIQ": ["<10M", "10-100M", ">=100M"], "PX": ["<10", "10-50", ">=50"], "VOL": ["<2%", "2-4%", ">=4%"],
             "R5": ["<=-5%", "mid", ">=+5%"], "R20": ["<=-10%", "mid", ">=+10%"]}
GROUPS_ON = dict(GROUPS_O1, REACT=["<=0.96", "mid", ">=1.04"], GAP=["<=0.98", "mid", ">=1.02"])
def count(groups):
    feats = [(g, f) for g, fs in groups.items() for f in fs]
    pairs = sum(1 for a, b in itertools.combinations(feats, 2) if a[0] != b[0])
    return len(feats), pairs, len(feats) + pairs
out = {}
for name, g in (("O1", GROUPS_O1), ("ON", GROUPS_ON)):
    F, P, J = count(g)
    out[name] = {"features": F, "pairs": P, "grid_subrules": J, "groups": len(g)}
# program experts on rel/1019g (hold 1, auction pair), from programs.py's tables (versions included)
import sys
sys.path.insert(0, "/dev/shm/gush-meta/src")
from league.events import programs as P
o1 = [f"{p.id}:v{p.version}" for p in P.PROGRAMS if p.hold == 1 and p.entry_at == "open" and p.exit_at == "close"]
on = [f"{p.id}:v{p.version}" for p in P.PROGRAMS if p.hold == 1 and p.entry_at == "close" and p.exit_at == "open"]
other = [f"{p.id}:v{p.version}({p.entry_at}->{p.exit_at},h{p.hold})" for p in P.PROGRAMS
         if not (p.hold == 1 and ((p.entry_at, p.exit_at) in (("open", "close"), ("close", "open"))))]
out["experts_O1"] = o1; out["experts_ON"] = on; out["excluded"] = other
print(json.dumps(out, indent=1))
