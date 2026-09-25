# Read-only: Kalshi buy fills and the held side's midpoint 15 and 60 minutes later, from the recorded
# market snapshots (runs on the House box: python3 rx.py markouts.py <since ISO>). J1's row-4 baseline.
import sqlite3, json, gzip, bisect, sys, time
from collections import defaultdict
from datetime import datetime
since = sys.argv[1] if len(sys.argv) > 1 else "2026-09-22T00:00"
L = sqlite3.connect("file:/workspace/state/ledger.sqlite?mode=ro", uri=True, timeout=60)
fills = []
for at, agent, p in L.execute("SELECT at, agent, payload FROM ledger WHERE kind='book.fill' AND at>=? AND payload LIKE ?", (since, '%"asset_class":"event"%')):
    d = json.loads(p)
    ins = d.get("instrument") or {}
    if d.get("side") != "buy":
        continue
    t = datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()
    fills.append((t, agent, d.get("book"), ins.get("market_id"), ins.get("right"), float(d["price"]), float(d["quantity"]), d.get("liquidity"), bool(d.get("real_money")), float(d.get("fee_usd") or 0)))
markets = {f[3] for f in fills}
t0 = min(f[0] for f in fills) - 3600
R = sqlite3.connect("file:/workspace/state/recordings.sqlite?mode=ro", uri=True, timeout=60)
quotes = defaultdict(list)
started = time.time(); n = 0
for received, payload in R.execute("SELECT received, payload FROM snapshots WHERE received>=? AND source LIKE 'markets:%'", (t0,)):
    n += 1
    try:
        rows = json.loads(gzip.decompress(payload))
    except Exception:
        continue
    if not isinstance(rows, list):
        continue
    for m in rows:
        mk = m.get("market") if isinstance(m, dict) else None
        if mk in markets:
            b, a = m.get("yes_bid"), m.get("yes_ask")
            if isinstance(b, (int, float)) and isinstance(a, (int, float)) and 0 <= b <= a <= 1:
                quotes[mk].append((received, (b + a) / 2))
for v in quotes.values():
    v.sort()
out = []
for (t, agent, book, mk, right, px, q, liq, real, fee) in fills:
    qs = quotes.get(mk) or []
    ts = [x[0] for x in qs]
    i = bisect.bisect_right(ts, t) - 1
    before = qs[i][1] if i >= 0 and t - qs[i][0] <= 600 else None
    j = bisect.bisect_left(ts, t + 900)
    after = qs[j][1] if j < len(qs) and qs[j][0] <= t + 1500 else None
    k = bisect.bisect_left(ts, t + 3600)
    after60 = qs[k][1] if k < len(qs) and qs[k][0] <= t + 4200 else None
    val = lambda mid: (mid if right == "yes" else 1 - mid) if mid is not None else None
    out.append([round(t), agent, book, mk, right, px, q, liq, real, fee, val(before), val(after), val(after60)])
print(json.dumps({"snapshots": n, "seconds": round(time.time() - started, 1), "fills": len(fills), "rows": out}))
