"""Ask the frozen question (p3, chosen on Sept 22-23 only) over every population session; writes jev_research.json."""
import json
import sys
from jevq import sensor, ask_all
from phr import SHARED, Q
FROZEN = "p3"
S = [json.loads(l) for l in open("sessions.jsonl")]
P = [s for s in S if s["source"] in ("run", "refusal_prompt")]
s = sensor()
items = {f"j2:{FROZEN}:{x['session']}": (x["text"], Q[FROZEN]) for x in P}
got = ask_all(s, "j2research", SHARED, items)
out = {x["session"]: got.get(f"j2:{FROZEN}:{x['session']}") for x in P}
json.dump(out, open("jev_research.json", "w"))
print("answered", sum(v is not None for v in out.values()), "of", len(out))
st = s.stats(); print({k: st[k] for k in ("spent_lifetime_usd", "calls_lifetime", "completed_lifetime", "latency_p50_seconds")})
