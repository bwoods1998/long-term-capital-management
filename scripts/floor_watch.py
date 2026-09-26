#!/usr/bin/env python3
"""Read-only options watch: swarm evidence, live inventory, data jobs, costs and health.

Run `python scripts/floor_watch.py --since 2026-09-28T13:00Z [--json]`.
All remote databases use read-only connections. Private programs, fitted parameters, quotes,
notebooks and per-trade replay results are never read by this command.
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
import sqlite3, pathlib, json, sys, time
root = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else '/workspace/state').resolve()
since = sys.argv[1]
def read(name):
    path = root / name
    if not path.exists(): return None
    try: return json.loads(path.read_text())
    except (OSError, ValueError) as error: return {'error': type(error).__name__}
def ro(name):
    path = root / name
    if not path.exists(): return None
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    db.execute('pragma query_only=1')
    db.execute('begin')
    return db
out = {'since': since, 'health': read('health.json'), 'swarm_process': read('swarm.heartbeat'),
       'data_job': read('data/nightly.heartbeat'), 'data_ready': read('data/images-ready.json'),
       'forward_ready': read('gym-forward.json'), 'paused': (root/'PAUSE').exists(), 'stopped': (root/'STOP').exists()}
for name in ('swarm.sqlite','live.sqlite','ledger.sqlite'):
    db = None
    try:
        db = ro(name)
        if db is None:
            out[name] = None
            continue
        if name == 'swarm.sqlite':
            row = {'bands': dict(db.execute('select band,count(*) from families where retired_at is null group by band')),
                   'retired': db.execute('select count(*) from families where retired_at is not null').fetchone()[0],
                   'trials': db.execute('select coalesce(sum(trials),0) from runs').fetchone()[0],
                   'runs': dict(db.execute('select status,count(*) from runs group by status')),
                   'looks': dict(db.execute('select passed,count(*) from looks group by passed')),
                   'spend_since': dict(db.execute('select kind,sum(usd) from spend where at>=? group by kind',(since,))),
                   'refusals_since': dict(db.execute('select stage,count(*) from refusals where at>=? group by stage',(since,))),
                   'boxes': dict(db.execute('select state,count(*) from boxes group by state'))}
        elif name == 'live.sqlite':
            kv = dict(db.execute("select key,value from kv where key in ('recon','paper_proof')"))
            proof = json.loads(kv.get('paper_proof','{}'))
            recon = json.loads(kv.get('recon','{}'))
            row = {'positions': dict(db.execute('select status,count(*) from positions group by status')),
                   'orders': dict(db.execute('select status,count(*) from orders group by status')),
                   'fees_paid_usd': db.execute('select coalesce(sum(fees),0) from fills').fetchone()[0],
                   'fill_count': db.execute('select count(*) from fills').fetchone()[0],
                   'reconciliation_frozen': bool(recon.get('frozen')),
                   'paper_route': {k:proof.get(k) for k in ('day','status','tries','close_tries','why')}}
        else:
            row = {'rows': db.execute('select count(*) from ledger').fetchone()[0],
                   'alerts_since': [{'at':at,'level':json.loads(raw).get('level'),'text':json.loads(raw).get('text')}
                       for at,raw in db.execute("select at,payload from ledger where kind='ops.alert' and at>=? order by seq desc limit 20",(since,))],
                   'sail_meter_usd_since': sum(float(json.loads(raw).get('spent_usd') or 0) for (raw,) in db.execute("select payload from ledger where kind='ops.budget' and at>=?",(since,)) if json.loads(raw).get('what')=='sail')}
        out[name] = row
    except Exception as error:
        out[name] = {'error':type(error).__name__+': '+str(error)[:200]}
    finally:
        if db is not None: db.close()
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
    return {"published_at": published, "age_seconds": age, "agents": len(checkpoint.get("agents") or []),
            "gym": checkpoint.get("gym"), "trading": checkpoint.get("trading")}

GATEWAY_SNIPPET = (
    "import sys,json,urllib.request,os;sys.path.insert(0,'/workspace/current');os.environ.setdefault('LEAGUE_ENV','/workspace/.env');"
    "os.chdir('/workspace/current');from league.service import load_config,load_env,secret;load_env();cfg=load_config();"
    "req=urllib.request.Request(cfg['gateway_url'].rstrip('/')+'/v1/health',headers={'Authorization':'Bearer '+secret('GATEWAY_TOKEN'),'User-Agent':'ltcm-floor/1.0'});"
    "h=json.load(urllib.request.urlopen(req,timeout=20));f=h.get('frontier') or {};s=h.get('sail') or {};"
    "print(json.dumps({'frontier':{k:f.get(k) for k in ('month','spent_usd','settled_usd','inflight_usd','cap_usd','previous')},"
    "'sail':{k:s.get(k) for k in ('balance_usd','burn_usd_per_day','runway_days')}}))")


def gateway_read() -> dict:
    from scripts.floor_box import client, read_state, require_box

    run = client().exec(require_box(read_state()), ["/workspace/.venv/bin/python", "-c", GATEWAY_SNIPPET], timeout=120, on_output=None)
    lines = (run.stdout or "").strip().splitlines()
    return json.loads(lines[-1]) if lines else {"error": run.stderr[-400:]}

def render(box: dict, site: dict, gateway: dict) -> str:
    h = box.get("health") or {}
    lines = [f"Options watch {h.get('at')} release {h.get('release')} tick {h.get('tick_duration_seconds')}s",
             f"Paused {box.get('paused')} stopped {box.get('stopped')} real money {h.get('real_money')}",
             f"Restarts in 24h {h.get('restarts_24h')} in session {h.get('restarts_24h_in_session')}"]
    for title, key in (("Swarm", "swarm.sqlite"), ("Live inventory", "live.sqlite"), ("Ledger", "ledger.sqlite"),
                       ("Swarm process", "swarm_process"), ("Data job", "data_job"), ("Data ready", "data_ready"),
                       ("Forward ready", "forward_ready")):
        lines.append(title + ": " + json.dumps(box.get(key), default=str, sort_keys=True))
    lines.append("Gateway: " + json.dumps(gateway, sort_keys=True))
    lines.append("Site: " + json.dumps(site, sort_keys=True))
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
