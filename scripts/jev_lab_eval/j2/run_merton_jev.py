"""Ask the five pre-registered questions over every Merton request; writes jev_merton.json."""
import json
from jevq import sensor, ask_all
from phr_merton import SHARED, Q
M = [json.loads(l) for l in open("merton.jsonl")]
s = sensor()
items = {f"j2m:{qid}:{m['seq']}": (m["request"], q) for m in M for qid, (_, q) in Q.items()}
got = ask_all(s, "j2merton", SHARED, items)
json.dump({k: v for k, v in got.items()}, open("jev_merton.json", "w"))
print("answered", sum(v is not None for v in got.values()), "of", len(got))
st = s.stats(); print({k: st[k] for k in ("spent_lifetime_usd", "calls_lifetime", "completed_lifetime")})
