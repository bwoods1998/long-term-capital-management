# Read-only (runs on the House box): do Kalshi maker fills made when the move sensor said "about to move"
# give back more in the next 15 minutes? J1's economic check, beside its AUC.
#
#   python3 rx.py move_markouts.py <cutoff ISO> [horizon_minutes]
#
# For each buy fill of an event contract at or after the cutoff: the move row the House held for that
# market at the fill (the newest with recorded_at <= the fill's time and observed within 10 minutes of it;
# nothing later is read), the held side's value from the recorder's own minute quotes: the last quote at or
# before the fill and the first in [fill + h, fill + h + 10 min]. Markout = value then - fill price, per
# contract and in dollars. Grouped by liquidity (maker/taker), book (real/practice) and move_p15 tercile
# (the terciles cut on all post-cutoff rows, so no fill's own outcome sets its bucket).
import json, sqlite3, sys
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime

cutoff = sys.argv[1]
h = int(sys.argv[2]) if len(sys.argv) > 2 else 15
cut_ts = datetime.fromisoformat(cutoff.replace("Z", "+00:00")).timestamp()
L = sqlite3.connect("file:/workspace/state/ledger.sqlite?mode=ro", uri=True, timeout=60)
F = sqlite3.connect("file:/workspace/state/jev-features.sqlite?mode=ro", uri=True, timeout=60)

ps = sorted(p for (p,) in F.execute("SELECT move_p15 FROM move_rows WHERE observed>=? AND move_p15 IS NOT NULL", (cut_ts,)))
if len(ps) < 30:
    print(json.dumps({"error": "too few move rows", "rows": len(ps)})); sys.exit(0)
t1, t2 = ps[len(ps) // 3], ps[2 * len(ps) // 3]

fills = []
for at, agent, p in L.execute("SELECT at, agent, payload FROM ledger WHERE kind='book.fill' AND at>=? AND payload LIKE ?",
                              (cutoff, '%"asset_class":"event"%')):
    d = json.loads(p)
    if d.get("side") != "buy":
        continue
    ins = d.get("instrument") or {}
    fills.append((datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp(), agent, d.get("book"), ins.get("market_id"),
                  ins.get("right"), float(d["price"]), float(d["quantity"]), d.get("liquidity"), bool(d.get("real_money"))))

groups = defaultdict(lambda: {"fills": 0, "marked": 0, "contracts": 0.0, "markout_usd": 0.0, "moved": 0})
unmatched = 0
for t, agent, book, mk, right, px, q, liq, real in fills:
    row = F.execute("SELECT move_p15, observed FROM move_rows WHERE market=? AND recorded_at<=? AND observed>=? "
                    "ORDER BY recorded_at DESC LIMIT 1", (mk, t, t - 600)).fetchone()
    if row is None or row[0] is None:
        unmatched += 1
        continue
    bucket = "low" if row[0] < t1 else "mid" if row[0] < t2 else "high"
    quotes = F.execute("SELECT minute, bid, ask FROM move_quotes WHERE market=? AND minute BETWEEN ? AND ? ORDER BY minute",
                       (mk, int(t) - 600, int(t) + h * 60 + 600)).fetchall()
    minutes = [m for m, _, _ in quotes]
    i = bisect_right(minutes, t) - 1
    j = bisect_left(minutes, t + h * 60)
    key = f"{'real' if real else 'practice'}|{liq}|{bucket}"
    g = groups[key]
    g["fills"] += 1
    if i < 0 or j >= len(quotes) or quotes[j][0] > t + h * 60 + 600:
        continue
    value = lambda b, a: ((b + a) / 2) if right == "yes" else 1 - (b + a) / 2
    before, after = value(quotes[i][1], quotes[i][2]), value(quotes[j][1], quotes[j][2])
    g["marked"] += 1
    g["contracts"] += q
    g["markout_usd"] += (after - px) * q
    g["moved"] += int(abs(after - before) > 1e-9)

out = {"cutoff": cutoff, "horizon_minutes": h, "move_p15_terciles": [round(t1, 4), round(t2, 4)], "fills": len(fills),
       "unmatched_no_move_row": unmatched, "groups": {}}
for key, g in sorted(groups.items()):
    g = dict(g)
    g["markout_per_contract"] = round(g["markout_usd"] / g["contracts"], 4) if g["contracts"] else None
    g["moved_share"] = round(g["moved"] / g["marked"], 3) if g["marked"] else None
    g["markout_usd"] = round(g["markout_usd"], 2)
    out["groups"][key] = g
print(json.dumps(out, indent=1))
