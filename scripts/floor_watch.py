"""The watch: one read-only command that prints what the owner's plan asks to be watched.

    python3 scripts/floor_watch.py [--since 2026-09-23T09:30:00] [--json]

It runs a read-only snippet on the House box (sqlite opened `mode=ro`; nothing is written there)
and reads the public site checkpoint from here. Sections: bands, real money, evidence, the lab,
costs, health. Built from the Sept 23, 2026 session's scratch watch scripts (post.py, swing.py,
holds.py, gwh.py), for the capital-ladder build (docs/goals/LTCM_NORTH_STAR_BUILD.md, "The watch").
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BOX_SNIPPET = r'''
import sqlite3, pathlib, json, sys, collections, math, time
root = pathlib.Path('/workspace/state')
since = sys.argv[1]
out = {}
def ro(name):
    p = root / name
    return sqlite3.connect(p.as_uri() + '?mode=ro', uri=True) if p.exists() else None
db = ro('ledger.sqlite')
h = json.loads((root / 'health.json').read_text())
camp = (h.get('campaign') or {})
lt = camp.get('live_trading') or {}
out['health'] = {'at': h.get('at'), 'release': h.get('release'), 'tick_s': h.get('tick_duration_seconds'), 'living': h.get('living'),
                 'dead': h.get('dead'), 'stopped': h.get('stopped_because'),
                 'frozen_books': [b for b, row in (h.get('books') or {}).items() if row.get('frozen')],
                 'grant_active': lt.get('active'), 'money_digest': ((lt.get('policy') or {}).get('constitution_digest') or '')[:8],
                 'background_jobs': len(h.get('background_jobs') or []),
                 'long_jobs': [j['key'] for j in (h.get('background_jobs') or []) if j.get('running_seconds', 0) > 600]}
acc = camp.get('accounts') or {}
out['costs'] = {'openai_left': (acc.get('openai') or {}).get('remaining_usd'), 'sail_left': (acc.get('sail') or {}).get('remaining_usd'),
                'pending_calls': camp.get('pending_calls'), 'jev': (h.get('jev') or {}).get('budget') if isinstance(h.get('jev'), dict) else None}
q = lambda kinds: db.execute("select agent, at, kind, payload from ledger where kind in (%s) and at >= ? order by seq" % ','.join('?' * len(kinds)), (*kinds, since)).fetchall()
born = {a: json.loads(p) for a, p in db.execute("select agent, payload from ledger where kind='agent.born'")}
V = lambda a: (born.get(a) or {}).get('venue')
# Bands: the allocator's own board when it exists, else rungs.
board_path = root / 'allocator-board.json'
board = json.loads(board_path.read_text()) if board_path.exists() else None
bands = collections.Counter()
top = []
if board:
    for a, row in (board.get('agents') or {}).items():
        bands[(row.get('venue'), row.get('band'))] += 1
        ev = row.get('evidence') or {}
        if ev:
            top.append((ev.get('E') or 0, a, row.get('venue'), row.get('band'), ev.get('W_paper'), ev.get('W_real'), ev.get('trades'), ev.get('real_trades'), row.get('stake_usd')))
    out['envelope'] = board.get('envelope')
    out['throttle'] = board.get('throttle')
    out['board_at'] = board.get('at')
else:
    rung = {}
    for a, p in db.execute("select agent, payload from ledger where kind='eval.verdict' and (payload like '%\"promote\"%' or payload like '%\"demote\"%' or payload like '%\"seat\"%') order by seq"):
        p = json.loads(p)
        if p.get('decision') in ('promote', 'demote', 'seat'):
            rung[a] = int(p['to_rung'])
    dead = {a for (a,) in db.execute("select agent from ledger where kind='agent.died'")}
    for a in born:
        if a not in dead:
            bands[(V(a), ('replay', 'paper', 'bunt', 'swing')[min(rung.get(a, 0), 3)])] += 1
out['bands'] = {f'{v}/{b}': n for (v, b), n in sorted(bands.items(), key=str)}
top.sort(reverse=True)
out['top_evidence'] = [dict(zip(('E', 'agent', 'venue', 'band', 'W_paper', 'W_real', 'trades', 'real_trades', 'stake'), row)) for row in top[:10]]
moves = collections.Counter(); move_rows = []
for a, at, k, p in q(('eval.verdict',)):
    p = json.loads(p)
    if p.get('decision') in ('promote', 'demote'):
        f, t = p.get('band_from') or p.get('from_rung'), p.get('band_to') or p.get('to_rung')
        moves[(V(a), p['decision'])] += 1
        move_rows.append(f"{at[11:19]} {a} {V(a)} {f}->{t} stake={p.get('stake_usd')} {str(p.get('reason') or '')[:90]}")
out['moves'] = {f'{v}/{d}': n for (v, d), n in sorted(moves.items(), key=str)}
out['move_rows'] = move_rows[-25:]
deaths = collections.Counter(json.loads(p).get('cause') for a, at, k, p in q(('agent.died',)))
out['deaths'] = dict(deaths)
out['births'] = dict(collections.Counter(((json.loads(p).get('founder') or 'house').split(':')[0]) for a, at, k, p in q(('agent.born',))))
# Real money.
fills = collections.Counter(); notional = collections.Counter(); realized = collections.Counter(); who = collections.defaultdict(set)
for a, at, k, p in q(('book.fill', 'book.settle')):
    p = json.loads(p); b = p.get('book')
    if k == 'book.fill':
        if p.get('source') not in ('venue', 'cross'):
            continue
        fills[b] += 1; who[b].add(a)
        try:
            notional[b] += abs(float(p['quantity']) * float(p['price']) * float((p.get('instrument') or {}).get('multiplier') or 1))
        except Exception:
            pass
        if p.get('realized') is not None:
            realized[b] += float(p['realized'])
    else:
        realized[b] += float(p.get('pnl') or 0)
summary = {b: {'fills': fills[b], 'notional': round(notional[b], 2), 'realized': round(realized[b], 2), 'agents': len(who[b])}
           for b in sorted(set(fills) | set(realized))}
# Only the real accounts are real money; the practice books (alpaca-paper, kalshi-shadow) fill too.
out['fills'] = {b: v for b, v in summary.items() if b in ('kalshi', 'alpaca')}
out['practice_fills'] = {b: v for b, v in summary.items() if b not in ('kalshi', 'alpaca')}
refused = collections.Counter()
for a, at, k, p in q(('book.refused',)):
    p = json.loads(p); refused[('; '.join(p.get('reasons') or []))[:80]] += 1
out['refusals'] = dict(refused.most_common(8))
alerts = collections.Counter()
for a, at, k, p in q(('ops.alert',)):
    p = json.loads(p); alerts[(p.get('level'), (p.get('text') or '')[:90])] += 1
out['alerts'] = [f"{n}x {lvl}: {t}" for (lvl, t), n in alerts.most_common(8)]
fees = [json.loads(p) for a, at, k, p in q(('credit.grant',))]
out['performance_fees'] = round(sum(float(f['usd']) for f in fees if str(f.get('reason', '')).startswith('performance fee')), 4)
# The lab.
lab = ro('lab.sqlite')
if lab is not None:
    try:
        tables = [r[0] for r in lab.execute("select name from sqlite_master where type='table'")]
        out['lab'] = {t: lab.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tables}
    except Exception as exc:
        out['lab'] = f'unreadable: {exc}'
lab_rows = collections.Counter(k for a, at, k, p in db.execute("select agent, at, kind, payload from ledger where kind like 'lab.%' and at >= ?", (since,)).fetchall())
if lab_rows:
    out['lab_ledger'] = dict(lab_rows)
# OpenAI holds (campaign basis).
cdb = ro('campaigns.sqlite')
if cdb is not None:
    try:
        t0 = time.time() - 3600
        settled = cdb.execute("select coalesce(sum(cost),0) from commitments where kind='openai' and created>=? and cost is not null", (t0,)).fetchone()[0]
        held = cdb.execute("select coalesce(sum(reserved),0) from commitments where kind='openai' and cost is null").fetchone()[0]
        out['costs']['openai_settled_last_hour'] = round(settled / 1e6, 2)
        out['costs']['openai_pending_holds'] = round(held / 1e6, 2)
    except Exception as exc:
        out['costs']['openai_error'] = str(exc)[:120]
# The run's health blocks (Sept 23, 2026, the learn-and-unblock run): the OpenAI tier, the shard
# funder, the seat market, the lab's waiters, and the newest hourly yield row (`ops.budget` "yield").
try:
    hs = json.loads((root / 'house.json').read_text())
except Exception:
    hs = {}
sh, seats, labh = h.get('shards') or {}, h.get('seats') or {}, h.get('lab') or {}
out['blocks'] = {
    'tier': hs.get('frontier_tier'),
    'shards': {k: sh.get(k) for k in ('balances', 'moved_24h_usd', 'unattributed_usd', 'blocked', 'pending', 'last_error')} if sh else None,
    'seats': {k: seats.get(k) for k in ('waiters', 'displaceable', 'never_traded_past_grace', 'waiting_over_an_hour')} if seats else None,
    'lab': {'closed_since': labh.get('closed_since'), 'llm_paused': (labh.get('llm') or {}).get('paused'),
            'waiting_seat': (labh.get('waiting_seat') or {}).get('count'), 'queued': labh.get('queued')} if labh else None}
row = db.execute("select at, payload from ledger where kind='ops.budget' and payload like '%\"what\": \"yield\"%' order by seq desc limit 1").fetchone()
if row:
    yp = json.loads(row[1])
    out['yield'] = {'at': row[0], **{k: yp.get(k) for k in ('spend', 'evidence', 'usd_per', 'window') if k in yp}}
print(json.dumps(out, default=str))
'''


def box_read(since: str) -> dict:
    from scripts.floor_box import client, read_state, require_box

    run = client().exec(require_box(read_state()), ["/workspace/.venv/bin/python", "-c", BOX_SNIPPET, since],
                        timeout=240, on_output=None)
    text = (run.stdout or "").strip().splitlines()
    if not text:
        raise SystemExit(f"the box returned nothing: {run.stderr[-2000:]}")
    return json.loads(text[-1])


def site_read() -> dict:
    request = urllib.request.Request("https://blakewoods.us/api/capital/checkpoint", headers={"User-Agent": "ltcm-watch/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
    except Exception as exc:  # noqa: BLE001 - a watch reports what it cannot read
        return {"error": f"{type(exc).__name__}: {exc}"}
    checkpoint = body.get("checkpoint", body) if isinstance(body, dict) else {}
    published = checkpoint.get("published_at")
    age = None
    if published:
        from datetime import datetime

        age = round(time.time() - datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp())
    return {"published_at": published, "age_seconds": age, "desks": len(checkpoint.get("desks") or []),
            "board": bool(checkpoint.get("board"))}


def gateway_read() -> dict:
    from scripts.floor_box import client, read_state, require_box

    code = ("import sys,json,urllib.request,os;sys.path.insert(0,'/workspace/current');os.environ.setdefault('LEAGUE_ENV','/workspace/.env');"
            "os.chdir('/workspace/current');from league.service import load_config,load_env,secret;load_env();cfg=load_config();"
            "req=urllib.request.Request(cfg['gateway_url'].rstrip('/')+'/v1/health',headers={'Authorization':'Bearer '+secret('GATEWAY_TOKEN'),'User-Agent':'ltcm-floor/1.0'});"
            "h=json.load(urllib.request.urlopen(req,timeout=20));f=h.get('frontier') or {};t=h.get('typesafe') or {};s=h.get('sail') or {};"
            "print(json.dumps({'frontier':{k:f.get(k) for k in ('month','spent_usd','cap_usd','base_cap_usd','profit_index')},"
            "'jev':{k:t.get(k) for k in ('spent_usd','cap_usd')},'sail':{k:s.get(k) for k in ('balance_usd','burn_usd_per_day','runway_days')}}))")
    run = client().exec(require_box(read_state()), ["/workspace/.venv/bin/python", "-c", code], timeout=120, on_output=None)
    lines = (run.stdout or "").strip().splitlines()
    return json.loads(lines[-1]) if lines else {"error": run.stderr[-400:]}


def render(box: dict, site: dict, gateway: dict) -> str:
    h = box["health"]
    lines = [f"# floor watch {h['at']}  release {h['release']}  tick {h['tick_s']}s  living {h['living']}  dead {h['dead']}",
             f"grant active {h['grant_active']} digest {h['money_digest']}  stopped: {h['stopped'] or '-'}  frozen books: {h['frozen_books'] or '-'}"
             f"  long jobs: {h['long_jobs'] or '-'}",
             f"## bands {box['bands']}",
             f"moves {box['moves']}  births {box['births']}  deaths {box['deaths']}",
             f"envelope {box.get('envelope')}  throttle {box.get('throttle')}"]
    lines += ["  " + row for row in box["move_rows"]]
    lines.append(f"## real money {json.dumps(box['fills'])}  performance fees ${box['performance_fees']}")
    lines.append(f"## practice {json.dumps(box.get('practice_fills') or {})}")
    lines.append("## top evidence")
    lines += [f"  {r['E']:.4f} {r['agent']} {r['venue']} {r['band']} Wp={r['W_paper']} Wr={r['W_real']} trades={r['trades']}/{r['real_trades']} stake={r['stake']}"
              for r in box["top_evidence"]]
    lines.append(f"## lab {box.get('lab')} {box.get('lab_ledger', '')}")
    lines.append(f"## costs {json.dumps(box['costs'])}  gateway {json.dumps(gateway)}")
    if box.get("blocks"):
        lines.append(f"## blocks {json.dumps(box['blocks'], default=str)}")
    if box.get("yield"):
        lines.append(f"## yield {json.dumps(box['yield'], default=str)[:600]}")
    lines.append(f"## health refusals {json.dumps(box['refusals'])}")
    lines += ["  alert " + a for a in box["alerts"]]
    lines.append(f"## site {json.dumps(site)}")
    return "\n".join(lines)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 3600)))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    box = box_read(args.since)
    site = site_read()
    try:
        gateway = gateway_read()
    except Exception as exc:  # noqa: BLE001
        gateway = {"error": f"{type(exc).__name__}: {exc}"}
    if args.json:
        print(json.dumps({"box": box, "site": site, "gateway": gateway}, default=str, indent=1))
    else:
        print(render(box, site, gateway))


if __name__ == "__main__":
    main()
