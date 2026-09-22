#!/usr/bin/env python3
"""Options history demo, read-only apart from market-data GETs: the SPY/QQQ features in the store,
the options-breakout seed replayed on an options tape at base and stressed execution, and a
labelled TEST strategy that reads the IV feature replayed on SPY -- each judged by the
evaluator's own replay gate in a throwaway ledger (nothing touches the House's).

    python scripts/options_demo.py --store PATH --start 2026-06-15T00:00:00Z --end 2026-09-19T00:00:00Z --env ../.env

Ingest first: `python -m league.options_history ingest ...` (see the module's docstring).
"""
import argparse
import copy, json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from league.service import load_config, load_env, secret
from league.venues import gateway_broker
from league.tapes import AlpacaData
from league import options_history as oh, seeds
from league.constitution import CONSTITUTION
from league.replay import run_replay
from league.niches import load as load_niches, constrain
from league.ledger import Ledger
from league.evaluator import Evaluator

IV_TEST = '''
# TEST STRATEGY (labelled; not a seed and not for the floor): hold SPY while its 30-day
# at-the-money implied volatility is under 90% of its own trailing 20-day mean, flat otherwise.
# It exists to show a strategy reading ctx["options_features"] in replay exactly as live.
NEEDS = {"venue": "alpaca", "horizon": "day", "style": "iv-calm-test", "symbols": ["SPY"],
         "bars": {"timeframe": "1Day", "limit": 30}, "options_features": True}
PARAMS = {"ratio": 0.9, "notional_usd": 60.0}

def decide(ctx):
    p = ctx["params"]
    mem = dict(ctx.get("memory") or {})
    row = (ctx.get("options_features") or {}).get("SPY") or {}
    ivs, days = list(mem.get("ivs") or []), list(mem.get("days") or [])
    if row.get("atm_iv") and row.get("day") not in days:
        ivs, days = (ivs + [row["atm_iv"]])[-20:], (days + [row["day"]])[-20:]
    mem["ivs"], mem["days"] = ivs, days
    held = sum(x["quantity"] for x in ctx.get("positions") or [] if x.get("symbol") == "SPY")
    if not (ctx.get("quotes") or {}).get("SPY") or len(ivs) < 5:
        return {"intents": [], "memory": mem, "thought": "waiting for five days of the IV feature"}
    calm = ivs[-1] < p["ratio"] * sum(ivs) / len(ivs)
    if calm and held <= 0:
        return {"intents": [{"symbol": "SPY", "side": "buy", "notional_usd": p["notional_usd"], "type": "market",
                             "reason": f"30-day ATM IV {ivs[-1]:.3f} is under {p['ratio']} of its 20-day mean"}], "memory": mem}
    if not calm and held > 0:
        return {"intents": [{"symbol": "SPY", "side": "sell", "quantity": held, "type": "market", "reason": "IV back above its mean"}], "memory": mem}
    return {"intents": [], "memory": mem}
'''

parser = argparse.ArgumentParser()
parser.add_argument('--store', required=True)
parser.add_argument('--start', required=True)
parser.add_argument('--end', required=True)
parser.add_argument('--env', default='')
args = parser.parse_args()
if args.env:
    load_env(Path(args.env))
store = oh.OptionsHistory(args.store)
START, END = args.start, args.end
config = load_config()
broker = gateway_broker('alpaca-paper', gateway_url=config['gateway_url'], token=secret('GATEWAY_TOKEN'), feed=config.get('alpaca_feed', 'iex'), option_feed=config.get('alpaca_option_feed', 'indicative'))
data = AlpacaData(broker.client, feed=config.get('alpaca_feed', 'iex'))
under = oh.adapter_from(data)
row = CONSTITUTION['rungs']['1']; stake = float(row['stake_usd']); limits = {'max_position_usd': float(row['max_position_usd']), 'max_order_usd': float(row['max_order_usd'])}

def judge(result, name):
    with tempfile.TemporaryDirectory() as root:
        ledger = Ledger(Path(root) / 'l.sqlite')
        v = Evaluator(ledger).record_trial(name, name, result, promote=False, lineage=[name])
        ledger.close() if hasattr(ledger, 'close') else None
    n = v.numbers
    return {k: n.get(k) for k in ('passed', 'reasons', 'trades', 'blocks', 'sharpe', 'deflated_sharpe', 'return_pct', 'max_drawdown', 'oos_mean_log_growth', 'fees_usd')}

out = {'window': [START, END]}
out['features'] = {s: {'rows': len(r), 'last': {k: r[-1].get(k) for k in ('day', 't', 'atm_iv', 'skew_25d', 'option_volume', 'option_trades', 'put_call_volume_ratio', 'expiry_used')},
                       'atm_iv_range': [min(x['atm_iv'] for x in r if x['atm_iv']), max(x['atm_iv'] for x in r if x['atm_iv'])],
                       'skew_range': [min(x['skew_25d'] for x in r if x['skew_25d'] is not None), max(x['skew_25d'] for x in r if x['skew_25d'] is not None)]}
                   for s, r in store.feature_series(['SPY', 'QQQ']).items()}
code = seeds.load('options-breakout')
ns = {}; exec(compile(code, 's', 'exec'), ns)
needs = constrain(ns['NEEDS'], load_niches()['alpaca-options'])
t0 = time.time()
tape = store.tape(needs, START, END, horizon='day', underlier_bars=under, warmup=70, execution='15Min', max_order_usd=limits['max_order_usd'])
out['options_tape'] = {'symbols': tape['symbols'], 'steps': len(tape['steps']), 'contracts': len(tape['contracts']), 'json_mb': round(len(json.dumps(tape)) / 1e6, 1),
                       'build_seconds': round(time.time() - t0, 1), 'spread_model': tape['spread_model']}
for label, spread, fee in (('base', 1.0, None), ('spread x1.5', 1.5, None), ('spread x2', 2.0, None), ('fee $0.10', 1.0, 0.10)):
    tp = copy.deepcopy(tape); tp['spread_model']['stress'] = spread
    if fee is not None:
        tp['fee_per_contract_usd'] = fee
    t0 = time.time()
    r = run_replay(code, {}, tp, stake=stake, limits=limits, audit=False)
    out[f'seed options-breakout, {label}'] = {'replay': {k: r.get(k) for k in ('ok', 'error', 'trades', 'fills', 'refused', 'final_equity', 'expired_orders')},
                                              'options': {k: v for k, v in (r.get('options') or {}).items() if k != 'execution_model'},
                                              'digest': (r.get('digest') or {}).get('all'), 'gate': judge(r, 'options-breakout'), 'seconds': round(time.time() - t0, 1)}

for attempt in range(3):  # the gateway times out a long page under load now and then
    try:
        eq = data.tape(['SPY'], '1Day', start=START, end=END, horizon='day', warmup_bars=30)
        break
    except Exception:
        if attempt == 2:
            raise
        time.sleep(5)
eq['options_features'] = store.feature_series(['SPY'])
r = run_replay(IV_TEST, {}, eq, stake=stake, limits=limits, audit=True)
out['equity IV test strategy (SPY, labelled test)'] = {'replay': {k: r.get(k) for k in ('ok', 'error', 'trades', 'fills', 'final_equity', 'steps')},
                                                       'feature_days_read': len(set((r.get('final_memory') or {}).get('days') or [])) or None,
                                                       'gate': judge(r, 'iv-calm-test')}
print(json.dumps(out, indent=1, default=str))

