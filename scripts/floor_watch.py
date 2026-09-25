"""The watch: one read-only command that prints what the owner's plan asks to be watched.

    python3 scripts/floor_watch.py [--since 2026-09-23T09:30:00] [--json]

It runs a read-only snippet on the House box (sqlite opened `mode=ro`; nothing is written there)
and reads the public site checkpoint from here. Sections: bands, real money, evidence, the lab,
costs, health. Built from the Sept 23, 2026 session's scratch watch scripts (post.py, swing.py,
holds.py, gwh.py), for the capital-ladder build (docs/goals/LTCM_NORTH_STAR_BUILD.md, "The watch").

`--since` is any ISO time (a space or a `T` between date and time, a zone or none: UTC), and is
turned into the ledger's own form before it is compared (`normalize_since`). Sept 24, 2026: the
ledger's `at` is compared as text, and sqlite's `datetime('now', '-1 hour')` writes a space where
the ledger writes `T`; a space sorts before `T`, so that form admitted the whole day.

The `## releases` line (H3 of the forward-first run, Sept 25, 2026) is the harness row: the House's
restarts in the last day, the updater's last ship and launch, what holds the next one (the release
train, a US session, a recent start: `league/updater.py` `schedule`) and when it may go.
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
import sqlite3, pathlib, json, sys, collections, math, time, calendar
root = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else '/workspace/state')  # a second argument: the tests' state
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
# The tick's own clock (C-perf, Sept 24, 2026): the last tick's slowest steps, each step's slowest in the
# last hour, and each background lane's last run (health.json `tick_steps`).
ts = h.get('tick_steps') or {}
tl = ts.get('last') or {}
out['tick_steps'] = {'total_s': tl.get('total_seconds'), 'ticks_in_hour': ts.get('ticks_in_hour'),
                     'last': sorted(([k, v] for k, v in (tl.get('steps') or {}).items()), key=lambda kv: (-kv[1], kv[0]))[:6],
                     'slowest_hour': [[r.get('step'), r.get('seconds'), r.get('at')] for r in (ts.get('slowest_hour') or [])[:6]],
                     'background': {lane: [r.get('key'), r.get('seconds'), r.get('state')] for lane, r in sorted((ts.get('background') or {}).items())}}
acc = camp.get('accounts') or {}
out['costs'] = {'openai_left': (acc.get('openai') or {}).get('remaining_usd'), 'sail_left': (acc.get('sail') or {}).get('remaining_usd'),
                'pending_calls': camp.get('pending_calls'), 'jev': (h.get('jev') or {}).get('budget') if isinstance(h.get('jev'), dict) else None}
# H3, the release train (the forward-first run, Sept 25, 2026): the House's restarts in the last day
# (health.json `restarts_24h` when the House writes it, else the ledger's `ops.started` rows: 26 in the
# 24 hours to 04:23Z Sept 25), the updater's last launch and last hold on the ledger, and the running
# release's own `league.updater.schedule` (read-only: deploys.jsonl and the ledger) for the last ship,
# the holds and the next eligible time. A third argument is the moment to read at (the tests' clock).
now = float(sys.argv[3]) if len(sys.argv) > 3 else time.time()
base = root.parent
day_ago = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(now - 86400))
starts = [at for (at,) in db.execute("select at from ledger where kind='ops.started' and at >= ? order by seq", (day_ago,))]
train = {'restarts_24h': h.get('restarts_24h'), 'restarts_source': 'health.json', 'starts_24h': len(starts),
         'last_start_at': starts[-1] if starts else None}
if train['restarts_24h'] is None:
    train.update(restarts_24h=len(starts), restarts_source='ops.started')
for key, action in (('last_launch', 'deploying'), ('last_held', 'held')):
    row = db.execute("select at, payload from ledger where kind='ops.deploy' and payload like ? order by seq desc limit 1",
                     ('%"action":"' + action + '"%',)).fetchone()
    if row:
        p = json.loads(row[1])
        train[key] = {'at': row[0], 'release': p.get('release'), 'sha': str(p.get('sha') or '')[:12], 'reasons': p.get('reasons') if action == 'held' else None}
try:
    if (base / 'current').is_dir():
        sys.path.insert(0, str(base / 'current'))
    from league.updater import schedule as train_schedule
    plan = train_schedule(base, now)
    train.update(train_hours=plan['train_hours'], last_ship=plan['last_ship'], next_eligible_at=plan['next_eligible_at'],
                 holds=[{k: hold.get(k) for k in ('hold', 'until', 'why')} for hold in plan['holds']])
except Exception as exc:
    train['schedule'] = f'unavailable ({type(exc).__name__}: {str(exc)[:160]}): the running release has no release train'
out['train'] = train
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
    try:  # D1 (Sept 24, 2026): the batches run in the window, what the lab's acceptance is read from
        n, c = lab.execute('select count(*), coalesce(sum(candidates), 0) from batches where at >= ?',
                           (calendar.timegm(time.strptime(since[:19], '%Y-%m-%dT%H:%M:%S')),)).fetchone()
        out['lab_batches'] = {'batches': n, 'candidates': c}
    except Exception as exc:
        out['lab_batches'] = f'unreadable: {exc}'
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
seat_block = {k: seats.get(k) for k in ('waiters', 'displaceable', 'never_traded_past_grace', 'waiting_over_an_hour', 'waiters_by_desk')} if seats else None
if seats:
    # S1-S4 (the close-the-gaps run, Sept 24, 2026): the seats holding no evidence (no forward score, no fill, no grace
    # left: count and the first ids), the desks' evidence clocks the grace follows, and why each class of waiter
    # (the retained research candidates of dead authors too) was last refused a seat.
    none = seats.get('seats_holding_none') or {}
    seat_block['seats_holding_none'] = {'count': none.get('count'), 'ids': (none.get('ids') or [])[:12]} if none else None
    seat_block['evidence_clocks'] = (seats.get('evidence_clocks') or {}).get('hours')
    seat_block['refused'] = {c: str((r or {}).get('why') or '')[:100] for c, r in (seats.get('last_refused_birth') or {}).items()} or None
    # R2 (Sept 24, 2026): the longest wait and the rule that holds it, the desks where newcomers wait over two hours,
    # the waiters that left the queue in the last day (the search closed their desk, or their forward window lost),
    # and the population the league may grow to on Sail's runway.
    seat_block['longest_wait'] = seats.get('longest_wait')
    seat_block['over_two_hours'] = {d: {k: r.get(k) for k in ('count', 'longest_hours', 'rule')}
                                    for d, r in (seats.get('over_two_hours') or {}).items()} or None
    seat_block['expired'] = seats.get('expired')
    pop = seats.get('population') or {}
    seat_block['population'] = {k: pop.get(k) for k in ('max_population', 'ceiling', 'runway_days', 'rule')} if pop else None
# The House-sent sales the venue or the book refused three times in a row (`WIND_DOWN_REFUSALS`): not sent again
# until the holding changes or a day has passed (house.json `wind_down_refusals`).
stopped = []
for a, books in (hs.get('wind_down_refusals') or {}).items():
    for b, rows in (books or {}).items():
        for key, r in (rows or {}).items():
            if int((r or {}).get('count') or 0) >= 3:
                stopped.append(f"{a} {b} {key} refused {r.get('count')}x: {str(r.get('detail') or '')[:90]}")
out['blocks'] = {
    'tier': hs.get('frontier_tier'),
    'shards': {k: sh.get(k) for k in ('balances', 'moved_24h_usd', 'unattributed_usd', 'blocked', 'pending', 'last_error')} if sh else None,
    'seats': seat_block,
    'wind_down_stopped': stopped[:10] or None,
    'lab': {'closed_since': labh.get('closed_since'), 'llm_paused': (labh.get('llm') or {}).get('paused'),
            'waiting_seat': (labh.get('waiting_seat') or {}).get('count'), 'queued': labh.get('queued')} if labh else None}
# D1 (Sept 24, 2026): whether the lab's step is failing, and since when (five in a row sets it).
out['lab_step'] = {k: labh.get(k) for k in ('failing_since', 'failures_in_a_row', 'error')} if labh else None
# L3 (Sept 24, 2026): warnings that repeat (10 in 30 minutes: one error alert, listed until they stop
# for 30 minutes), the health failures the in-box watchdog reads, and the research economy's dials.
out['repeating_warnings'] = h.get('repeating_warnings') or []
out['failures'] = h.get('failures') or []
out['research_economy'] = h.get('research_economy')
# The ledger's payloads are canonical JSON, with no space after a colon: `"what":"yield"`. Until
# Sept 24, 2026 this asked for `"what": "yield"`, which no row carries, and printed no yield at all.
row = db.execute("select at, payload from ledger where kind='ops.budget' and payload like '%\"what\":\"yield\"%' order by seq desc limit 1").fetchone()
if row:
    yp = json.loads(row[1])
    out['yield'] = {'at': row[0], **{k: yp.get(k) for k in ('spend_usd', 'evidence', 'usd_per', 'by_profile', 'since', 'until') if k in yp}}
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


#: The gateway's `/v1/health`, read from the box (which holds the token). Since Deploy A (Sept 24,
#: 2026) the frontier block also says what is settled, what is still in flight (reservations whose
#: calls have not answered) and the previous month's line (`previous`): the watch prints them all.
GATEWAY_SNIPPET = (
    "import sys,json,urllib.request,os;sys.path.insert(0,'/workspace/current');os.environ.setdefault('LEAGUE_ENV','/workspace/.env');"
    "os.chdir('/workspace/current');from league.service import load_config,load_env,secret;load_env();cfg=load_config();"
    "req=urllib.request.Request(cfg['gateway_url'].rstrip('/')+'/v1/health',headers={'Authorization':'Bearer '+secret('GATEWAY_TOKEN'),'User-Agent':'ltcm-floor/1.0'});"
    "h=json.load(urllib.request.urlopen(req,timeout=20));f=h.get('frontier') or {};t=h.get('typesafe') or {};s=h.get('sail') or {};"
    "print(json.dumps({'frontier':{k:f.get(k) for k in ('month','spent_usd','settled_usd','inflight_usd','cap_usd','base_cap_usd','profit_index','previous')},"
    "'jev':{k:t.get(k) for k in ('spent_usd','cap_usd')},'sail':{k:s.get(k) for k in ('balance_usd','burn_usd_per_day','runway_days')}}))")


def gateway_read() -> dict:
    from scripts.floor_box import client, read_state, require_box

    run = client().exec(require_box(read_state()), ["/workspace/.venv/bin/python", "-c", GATEWAY_SNIPPET], timeout=120, on_output=None)
    lines = (run.stdout or "").strip().splitlines()
    return json.loads(lines[-1]) if lines else {"error": run.stderr[-400:]}


def render(box: dict, site: dict, gateway: dict) -> str:
    h = box["health"]
    lines = [f"# floor watch {h['at']}  release {h['release']}  tick {h['tick_s']}s  living {h['living']}  dead {h['dead']}",
             f"grant active {h['grant_active']} digest {h['money_digest']}  stopped: {h['stopped'] or '-'}  frozen books: {h['frozen_books'] or '-'}"
             f"  long jobs: {h['long_jobs'] or '-'}"]
    ticks = box.get("tick_steps") or {}
    if ticks.get("last") or ticks.get("slowest_hour"):
        # C-perf (Sept 24, 2026): which steps the tick's seconds went to (health.json `tick_steps`).
        lines.append(f"## tick steps: last {ticks.get('total_s')}s: " + (", ".join(f"{k} {v}s" for k, v in ticks.get("last") or []) or "-")
                     + f"  |  slowest in the hour ({ticks.get('ticks_in_hour')} ticks): "
                     + (", ".join(f"{k} {v}s at {str(at)[11:19]}" for k, v, at in ticks.get("slowest_hour") or []) or "-"))
    if ticks.get("background"):
        lines.append("   background " + ", ".join(f"{lane} {row[1]}s ({row[0]}, {row[2]})" for lane, row in ticks["background"].items()))
    train = box.get("train") or {}
    if train:
        # H3 (Sept 25, 2026): the plan's harness row is at most six restarts a day and none in a US session.
        restarts = train.get("restarts_24h")
        ship = train.get("last_ship") or {}
        launch = train.get("last_launch") or {}
        lines.append(f"## releases: restarts in 24 h {json.dumps(restarts) if isinstance(restarts, (dict, list)) else restarts}"
                     f" ({train.get('restarts_source')}; last start {train.get('last_start_at') or '-'})"
                     f"  last updater ship {ship.get('at') or '-'} {ship.get('release') or ''} {('(' + ship['verdict'] + ')') if ship.get('verdict') else ''}"
                     f"  last launch {launch.get('at') or '-'} {launch.get('release') or ''}"
                     f"  next eligible {train.get('next_eligible_at') or train.get('schedule') or '-'}"
                     + (f" (train {train['train_hours']:g} h)" if train.get("train_hours") is not None else ""))
        lines += [f"   held now ({hold.get('hold')} until {hold.get('until')}): {hold.get('why')}" for hold in train.get("holds") or []]
        held = train.get("last_held") or {}
        if held:
            lines.append(f"   last hold on the ledger {held.get('at')} {held.get('release')} {held.get('sha')}: "
                         + "; ".join(str(r) for r in held.get("reasons") or [])[:400])
    lines += [f"## bands {box['bands']}",
              f"moves {box['moves']}  births {box['births']}  deaths {box['deaths']}",
              f"envelope {box.get('envelope')}  throttle {box.get('throttle')}"]
    lines += ["  " + row for row in box["move_rows"]]
    lines.append(f"## real money {json.dumps(box['fills'])}  performance fees ${box['performance_fees']}")
    lines.append(f"## practice {json.dumps(box.get('practice_fills') or {})}")
    lines.append("## top evidence")
    lines += [f"  {r['E']:.4f} {r['agent']} {r['venue']} {r['band']} Wp={r['W_paper']} Wr={r['W_real']} trades={r['trades']}/{r['real_trades']} stake={r['stake']}"
              for r in box["top_evidence"]]
    step = box.get("lab_step") or {}
    lines.append(f"## lab failing_since {step.get('failing_since') or '-'}  failures_in_a_row {step.get('failures_in_a_row') or 0}"
                 f"  error {step.get('error') or '-'}  batches since --since {box.get('lab_batches')}"
                 f"  tables {box.get('lab')} {box.get('lab_ledger', '')}")
    lines.append(f"## costs {json.dumps(box['costs'])}  gateway {json.dumps(gateway)}")
    seats = (box.get("blocks") or {}).get("seats") or {}
    if seats:
        none = seats.get("seats_holding_none") or {}
        lines.append(f"## seats waiters {seats.get('waiters')}  displaceable {seats.get('displaceable')}  holding none "
                     f"{none.get('count', '-')} {none.get('ids') or ''}  clocks {seats.get('evidence_clocks')}"
                     f"  refused {seats.get('refused') or '-'}")
        # R2 (Sept 24, 2026): no newcomer waits over two hours, or the watch says where and why.
        longest = seats.get("longest_wait") or {}
        if longest:
            lines.append(f"   longest wait {longest.get('hours')} h: {longest.get('class')} {longest.get('id')} for {longest.get('desk') or '?'}"
                         f" -- {longest.get('reason') or 'under two hours or not yet read by the hourly watch'}")
        for desk, row in (seats.get("over_two_hours") or {}).items():
            lines.append(f"   over 2 h on {desk}: {row.get('count')} (longest {row.get('longest_hours')} h): {row.get('rule')}")
        expired, pop = seats.get("expired") or {}, seats.get("population") or {}
        if expired or pop:
            lines.append(f"   left the queue in a day {expired.get('last_day', 0)} {expired.get('by_rule') or ''}"
                         f"  population {pop.get('max_population', '-')} of {pop.get('ceiling', '-')}: {pop.get('rule') or '-'}")
    for row in (box.get("blocks") or {}).get("wind_down_stopped") or []:
        lines.append("  wind-down stopped " + row)
    if box.get("blocks"):
        lines.append(f"## blocks {json.dumps(box['blocks'], default=str)}")
    if box.get("yield"):
        lines.append(f"## yield {json.dumps(box['yield'], default=str)[:900]}")
    if box.get("research_economy"):
        lines.append(f"## research economy {json.dumps(box['research_economy'], default=str)[:600]}")
    # L3 (Sept 24, 2026): a warning that repeats is a defect until it stops; a health failure is what
    # the in-box watchdog reads (league/watchdog.py).
    repeating = box.get("repeating_warnings") or []
    lines.append(f"## repeating warnings {len(repeating) or '-'}")
    lines += [f"  {r.get('count')}x since {r.get('first_seen')} (last {r.get('last_seen')}): {str(r.get('text'))[:160]}" for r in repeating]
    failures = box.get("failures") or []
    lines.append(f"## health failures {len(failures) or '-'}")
    lines += [f"  {r.get('check')} since {r.get('since')}: {str(r.get('text'))[:200]}" for r in failures]
    lines.append(f"## health refusals {json.dumps(box['refusals'])}")
    lines += ["  alert " + a for a in box["alerts"]]
    lines.append(f"## site {json.dumps(site)}")
    return "\n".join(lines)


def normalize_since(value: str) -> str:
    """`--since` in the ledger's own form, `YYYY-MM-DDTHH:MM:SS` in UTC, or an argparse error.

    The snippet compares it as text with the ledger's `at` (`2026-09-24T00:42:00.123Z`). A space
    instead of the `T` (what sqlite's `datetime('now', ...)` writes) sorts before every stamp of
    that day, so it admitted the whole day (Sept 24, 2026); a zone other than UTC would shift the
    window; a fraction or a `Z` at the end is harmless but is dropped too."""
    from datetime import datetime, timezone

    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"--since must be an ISO time such as 2026-09-24T00:42:00, not {value!r}") from None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S")


def parser() -> argparse.ArgumentParser:
    out = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_argument("--since", type=normalize_since, default=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 3600)),
                     help="the window's start, an ISO time (UTC unless it names a zone); default an hour ago")
    out.add_argument("--json", action="store_true")
    return out


def main(argv=None) -> None:
    args = parser().parse_args(argv)
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
