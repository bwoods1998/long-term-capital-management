"""The Kalshi-scale run's watch: one read-only command for what the weekend watch reads every 30 minutes.

    python3 scripts/kalshi_watch.py [--since 2026-09-26T15:00:00] [--until ...] [--json]

docs/goals/LTCM_KALSHI_SCALE.md, workstreams W, K3 and K4 (Sept 25, 2026). It runs a read-only snippet
on the House box (sqlite opened `mode=ro`; nothing is written there), as `scripts/floor_watch.py` does,
and prints, for the window:

- **real Kalshi money**: orders (post-only or taking), fills, settlements and P&L by family and by
  league (a ticker's series names its league: KXNFL... nfl, KXNCAAF... ncaaf, KXMLB... mlb; weather,
  crypto strikes, the 15-minute crypto desk and the slow prices by their series), independent events
  settled;
- **practice** (`kalshi-shadow`): the same, the busiest families first;
- **refusals** on the real Kalshi book by class (K4): the per-event cap, maker-only-until-proven, the
  longshot floor, the horizon rule, an unfunded shard, desk cash, exposure, anything else by its text;
- **coverage** (K3): every hour of the window with the real Kalshi agents that woke with markets offered
  and the intents they made; an hour with no real agent offered a market is an hour with no live desk;
- **the model-versus-market founders** (K1, founder keys `consensus-*`): wakes, markets offered, intents,
  orders, fills, settlements and their last thought;
- **capacity** (K2): every Kalshi family with a positive pooled record or a proof, its capacity at its
  stake from the allocator's board, the proven families' sum a day, and the envelope committed;
- **shards**: each exchange shard's balance, what moved in 24 hours, anything pending or blocked;
- **data requests** (I3): the agents' `tool.request` rows in the window and the fulfilled or blocked rows.

`--since` defaults to 30 minutes ago; times are UTC and compared in the ledger's own form
(`floor_watch.normalize_since`).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BOX_SNIPPET = r'''
import sqlite3, pathlib, json, sys, collections, re, datetime
since = sys.argv[1]
until = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
root = pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else '/workspace/state')  # a third argument: the tests' state
def ro(name):
    p = root / name
    return sqlite3.connect(p.as_uri() + '?mode=ro', uri=True) if p.exists() else None
def load(name):
    p = root / name
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        return {}
db = ro('ledger.sqlite')
health = load('health.json')
board = load('allocator-board.json')
out = {'since': since, 'until': until, 'at': health.get('at'), 'release': health.get('release')}
SPORTS = (('KXNCAAF', 'ncaaf'), ('KXNFL', 'nfl'), ('KXMLB', 'mlb'), ('KXWNBA', 'wnba'), ('KXNBA', 'nba'), ('KXNHL', 'nhl'),
          ('KXEPL', 'soccer'), ('KXLALIGA', 'soccer'), ('KXSERIEA', 'soccer'), ('KXBUNDESLIGA', 'soccer'), ('KXLIGUE1', 'soccer'),
          ('KXEFL', 'soccer'), ('KXMLS', 'soccer'), ('KXLIGAMX', 'soccer'), ('KXUEFA', 'soccer'), ('KXEREDIVISIE', 'soccer'),
          ('KXLIGAPORTUGAL', 'soccer'), ('KXSCOTTISHPREM', 'soccer'), ('KXSUPERLIG', 'soccer'), ('KXCS2', 'esports'),
          ('KXLOL', 'esports'), ('KXDOTA2', 'esports'), ('KXVALORANT', 'esports'), ('KXATP', 'tennis'), ('KXWTA', 'tennis'),
          ('KXUFC', 'ufc'), ('KXT20', 'cricket'), ('KXWT20', 'cricket'))
def league(ticker):
    series = str(ticker or '').split('-')[0].upper()
    for prefix, name in SPORTS:
        if series.startswith(prefix):
            return name
    if re.match(r'^KX(HIGH|LOWT|RAIN|SNOW)', series):
        return 'weather'
    if series.endswith('15M'):
        return 'crypto-15m'
    if re.match(r'^KX(BTC|ETH|SOL|XRP|DOGE|HYPE|BNB|ADA|LTC|ZEC|NEAR)D?$', series):
        return 'crypto-strikes'
    if re.match(r'^KX(AAAGAS|DIESEL|WTI|BRENT|NATGAS|GOLD|SILVER|EURUSD|USDJPY|GBPUSD|INX|NASDAQ100)', series):
        return 'prices'
    return 'other:' + series
def event(ticker):
    return '-'.join(str(ticker or '').split('-')[:2])
born = {}
for agent, payload in db.execute("select agent, payload from ledger where kind='agent.born' order by seq"):
    born[agent] = json.loads(payload)
board_agents = board.get('agents') or {}
def family(agent):
    row = board_agents.get(agent) if isinstance(board_agents, dict) else None
    if isinstance(row, dict) and row.get('family'):
        return row['family']
    return (born.get(agent) or {}).get('family') or '?'
def rows(kinds):
    sql = "select agent, at, kind, payload from ledger where kind in (%s) and at >= ?" % ','.join('?' * len(kinds))
    args = [*kinds, since]
    if until:
        sql += " and at < ?"
        args.append(until)
    return [(a, at, k, json.loads(p)) for a, at, k, p in db.execute(sql + " order by seq", args)]
def market_of(payload):
    inst = payload.get('instrument') or {}
    return inst.get('market_id') or inst.get('symbol') or payload.get('market') or ''
def dec(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
def blank():
    return {'orders': 0, 'post_only': 0, 'taking': 0, 'fills': 0, 'fill_usd': 0.0, 'maker_fills': 0, 'taker_fills': 0,
            'settled': 0, 'events': set(), 'pnl': 0.0, 'wins': 0, 'cancels': 0}
money = {'kalshi': {'family': collections.defaultdict(blank), 'league': collections.defaultdict(blank)},
         'kalshi-shadow': {'family': collections.defaultdict(blank), 'league': collections.defaultdict(blank)}}
orders_seen = {}
for agent, at, kind, p in rows(('book.order', 'book.fill', 'book.settle', 'book.cancel')):
    book = p.get('book')
    if book not in money:
        continue
    if kind == 'book.fill' and p.get('source') == 'dust':
        out['dust_usd'] = round(out.get('dust_usd', 0.0) + dec(p.get('cash_delta')), 6)  # the House's sub-cent reconciliations, not trades
        continue
    if kind == 'book.order':
        shares = p.get('shares') or []
        owner = (shares[0] or {}).get('agent') if shares else agent
        orders_seen[p.get('order_id')] = owner
        agent = owner
    elif kind == 'book.cancel':
        agent = orders_seen.get(p.get('order_id'), agent)
    ticker = market_of(p)
    for key, group in ((family(agent), 'family'), (league(ticker), 'league')):
        r = money[book][group][key]
        if kind == 'book.order':
            r['orders'] += 1
            r['post_only' if p.get('post_only') else 'taking'] += 1
        elif kind == 'book.fill':
            r['fills'] += 1
            r['fill_usd'] += abs(dec(p.get('cash_delta')))
            r['maker_fills' if p.get('liquidity') == 'maker' else 'taker_fills'] += 1
        elif kind == 'book.settle':
            r['settled'] += 1
            r['events'].add(event(ticker))
            r['pnl'] += dec(p.get('pnl'))
            r['wins'] += 1 if dec(p.get('pnl')) > 0 else 0
        elif kind == 'book.cancel':
            r['cancels'] += 1
def flat(table, limit):
    items = []
    for key, r in table.items():
        row = dict(r)
        row['events'] = len(r['events'])
        row['pnl'] = round(r['pnl'], 2)
        row['fill_usd'] = round(r['fill_usd'], 2)
        items.append([key, row])
    items.sort(key=lambda kv: (-(kv[1]['settled'] + kv[1]['fills'] + kv[1]['orders']), kv[0]))
    return items[:limit]
out['real'] = {g: flat(money['kalshi'][g], 40) for g in ('family', 'league')}
out['practice'] = {g: flat(money['kalshi-shadow'][g], 25) for g in ('family', 'league')}
out['real_pnl'] = round(sum(r['pnl'] for r in money['kalshi']['family'].values()), 2)
out['practice_pnl'] = round(sum(r['pnl'] for r in money['kalshi-shadow']['family'].values()), 2)
CLASSES = (('per-event cap', r'max_event_share|one event may hold'), ('maker-only', r'real_entry_liquidity|post-only limit until|post_only'),
           ('longshot floor', r'longshot'), ('horizon', r'expected to resolve|horizon|cannot tell when'),
           ('shard', r'shard'), ('desk cash', r'free cash|desk cash|insufficient'), ('exposure', r'gross exposure|exposure would be'),
           ('daily halt', r'real_halt|daily'), ('throttle', r'throttle'), ('stake', r'stake|headroom'))
def classify(reasons):
    text = ' '.join(str(r) for r in reasons or [])
    for name, pattern in CLASSES:
        if re.search(pattern, text, re.I):
            return name
    return 'other: ' + text[:80]
refusals = {'kalshi': collections.Counter(), 'kalshi-shadow': collections.Counter()}
examples = {}
for agent, at, kind, p in rows(('book.refused',)):
    book = p.get('book')
    if book not in refusals:
        continue
    cls = classify(p.get('reasons'))
    refusals[book][cls] += 1
    if book == 'kalshi':
        examples.setdefault(cls, f"{at[11:19]} {agent} ({family(agent)}) {market_of(p)}: {' | '.join(str(r) for r in p.get('reasons') or [])[:220]}")
out['refusals'] = {'real': refusals['kalshi'].most_common(), 'practice': refusals['kalshi-shadow'].most_common(12), 'examples': examples}
hours = collections.OrderedDict()
def hour_of(at):
    return at[:13] + ':00Z'
start = datetime.datetime.strptime(since[:13], '%Y-%m-%dT%H')
end = datetime.datetime.strptime(until[:13], '%Y-%m-%dT%H') if until else datetime.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
start = max(start, end - datetime.timedelta(hours=95))  # the table's last 96 hours at most
cursor = start
while cursor <= end:
    hours[cursor.strftime('%Y-%m-%dT%H:00Z')] = {'agents': set(), 'offered': set(), 'intents': 0, 'wakes': 0}
    cursor += datetime.timedelta(hours=1)
founders = {a: (born.get(a) or {}).get('founder') for a in born if str((born.get(a) or {}).get('founder') or '').startswith('consensus-')}
fstats = {a: {'founder': founders[a], 'family': family(a), 'wakes': 0, 'offered_max': 0, 'intents': 0} for a in founders}
for agent, at, kind, p in rows(('agent.woke',)):
    if agent in fstats:
        f = fstats[agent]
        f['wakes'] += 1
        f['offered_max'] = max(f['offered_max'], int(p.get('offered') or 0))
        f['intents'] += int(p.get('intents') or 0)
    if p.get('book') != 'kalshi':
        continue
    h = hours.setdefault(hour_of(at), {'agents': set(), 'offered': set(), 'intents': 0, 'wakes': 0})
    h['wakes'] += 1
    h['agents'].add(agent)
    if int(p.get('offered') or 0) > 0:
        h['offered'].add(agent)
    h['intents'] += int(p.get('intents') or 0)
out['coverage'] = [[hour, len(h['agents']), len(h['offered']), h['intents'], h['wakes'], sorted(h['offered'])[:8]] for hour, h in hours.items()]
out['hours_without_live_desk'] = [hour for hour, h in hours.items() if not h['offered']]
out['hours_without_real_intent'] = [hour for hour, h in hours.items() if not h['intents']]
for a in fstats:
    for book in ('kalshi-shadow', 'kalshi'):
        r = money[book]['family'].get(family(a))
        if r:
            fstats[a][book] = {k: (len(v) if isinstance(v, set) else (round(v, 2) if isinstance(v, float) else v)) for k, v in r.items()}
    row = db.execute("select at, payload from ledger where kind='agent.thought' and agent=? order by seq desc limit 1", (a,)).fetchone()
    if row:
        fstats[a]['thought'] = [row[0][11:19], str(json.loads(row[1]).get('thought') or json.loads(row[1]).get('text') or row[1])[:240]]
    fstats[a]['alive'] = a in {x for x in board_agents} if isinstance(board_agents, dict) else None
    fstats[a]['band'] = (board_agents.get(a) or {}).get('band') if isinstance(board_agents, dict) else None
out['founders'] = fstats
fams = (board.get('families') or {}).get('kalshi') or {}
cap_rows = []
for name, f in fams.items():
    if not (f.get('proven') or (f.get('mean_log') or 0) > 0):
        continue
    c = f.get('capacity') or {}
    r = f.get('real') or {}
    cap_rows.append([name, f.get('state'), f.get('n'), f.get('bound'), round(f.get('mean_log') or 0, 4), r.get('n'), r.get('bound'),
                     f.get('members_living'), f.get('members_real'), f.get('stake_usd'), c.get('size_usd'), c.get('fill_rate_at_size'),
                     c.get('markets_per_day'), c.get('usd_per_day'), (f.get('swing_clock') or {}).get('real_n')])
cap_rows.sort(key=lambda r: -(r[13] or 0))
out['capacity'] = cap_rows
out['proven_capacity_usd_day'] = round(sum((r[13] or 0) for r in cap_rows if r[1] in ('proven', 'swing')), 2)
env = (board.get('envelope') or {}).get('kalshi') or {}
out['envelope'] = {'capital': env.get('capital_usd'), 'committed': env.get('committed_usd'), 'board_at': board.get('at')}
out['real_agents'] = sorted([[a, r.get('band'), r.get('family'), r.get('stake_usd'), r.get('equity_usd')] for a, r in board_agents.items()
                             if isinstance(r, dict) and r.get('venue') == 'kalshi' and r.get('band') not in ('paper', 'practice', 'replay', None)])
sh = health.get('shards') or {}
out['shards'] = {k: sh.get(k) for k in ('balances', 'moved_24h_usd', 'pending', 'requested', 'blocked', 'last_error', 'last_check')}
reqs = []
for agent, at, kind, p in rows(('tool.request', 'tool.fulfilled', 'tool.blocked')):
    reqs.append([at[5:19], kind.split('.')[1], agent, str(p.get('name') or p.get('tool') or p.get('request') or '')[:60],
                 str(p.get('description') or p.get('reason') or p.get('outcome') or p.get('why') or '')[:160]])
out['requests'] = reqs
print(json.dumps(out, default=str))
'''


def box_read(since: str, until: str | None) -> dict:
    from scripts.floor_box import client, read_state, require_box

    run = client().exec(require_box(read_state()), ["/workspace/.venv/bin/python", "-c", BOX_SNIPPET, since, until or ""],
                        timeout=240, on_output=None)
    text = (run.stdout or "").strip().splitlines()
    if not text:
        raise SystemExit(f"the box returned nothing: {(run.stderr or '')[-2000:]}")
    return json.loads(text[-1])


def _table(title: str, items: list, keys: tuple[str, ...]) -> list[str]:
    lines = [f"## {title}" + ("" if items else " -")]
    for name, row in items:
        lines.append("  " + f"{name[:44]:44} " + " ".join(f"{k}={row.get(k)}" for k in keys))
    return lines


def render(box: dict) -> str:
    keys = ("orders", "post_only", "taking", "fills", "fill_usd", "taker_fills", "settled", "events", "wins", "pnl")
    lines = [f"# Kalshi watch {box.get('since')} .. {box.get('until') or 'now'} (box {box.get('at')}, release {box.get('release')})",
             f"real settled P&L {box.get('real_pnl')}   practice settled P&L {box.get('practice_pnl')}"]
    lines += _table("real by family", box["real"]["family"], keys)
    lines += _table("real by league", box["real"]["league"], keys)
    lines += _table("practice by league", box["practice"]["league"], keys)
    lines += _table("practice by family (busiest)", box["practice"]["family"][:15], ("fills", "settled", "events", "wins", "pnl"))
    lines.append(f"## real refusals by class {box['refusals']['real'] or '-'}")
    lines += [f"  {cls}: {text}" for cls, text in sorted((box["refusals"].get("examples") or {}).items())]
    lines.append(f"## practice refusals by class {box['refusals']['practice'] or '-'}")
    lines.append("## coverage (hour, real agents woken, offered a market, intents, wakes)")
    lines += [f"  {h} {n} {o} {i} {w} {' '.join(names)}" for h, n, o, i, w, names in box["coverage"]]
    lines.append(f"  hours with no live Kalshi desk: {box['hours_without_live_desk'] or 'none'}")
    lines.append(f"  hours with no real Kalshi intent: {box['hours_without_real_intent'] or 'none'}")
    lines.append(f"## model-versus-market founders {len(box['founders']) or '-'}")
    for agent, f in sorted(box["founders"].items()):
        lines.append(f"  {agent} {f.get('founder')} band={f.get('band')} wakes={f['wakes']} offered<={f['offered_max']} intents={f['intents']} "
                     f"practice={json.dumps(f.get('kalshi-shadow'))} real={json.dumps(f.get('kalshi'))}")
        if f.get("thought"):
            lines.append(f"    {f['thought'][0]} {f['thought'][1]}")
    env = box.get("envelope") or {}
    lines.append(f"## capacity (proven sum ${box.get('proven_capacity_usd_day')}/day; envelope committed {env.get('committed')} of {env.get('capital')}, board {env.get('board_at')})")
    lines.append("  family state n bound mean_log real_n real_bound living real stake size fill mkts/day usd/day swing_n")
    lines += ["  " + " ".join(str(x) for x in row) for row in box["capacity"]]
    lines.append("## real Kalshi agents")
    lines += ["  " + " ".join(str(x) for x in row) for row in box["real_agents"]]
    lines.append(f"## shards {json.dumps(box.get('shards'))}")
    lines.append(f"## data requests {len(box['requests']) or '-'}")
    lines += ["  " + " ".join(str(x) for x in row) for row in box["requests"]]
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    from scripts.floor_watch import normalize_since

    out = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_argument("--since", type=normalize_since, default=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 1800)),
                     help="the window's start, an ISO time (UTC unless it names a zone); default 30 minutes ago")
    out.add_argument("--until", type=normalize_since, default=None, help="the window's end (default now)")
    out.add_argument("--json", action="store_true")
    return out


def main(argv=None) -> None:
    args = parser().parse_args(argv)
    box = box_read(args.since, args.until)
    print(json.dumps(box, default=str, indent=1) if args.json else render(box))


if __name__ == "__main__":
    main()
