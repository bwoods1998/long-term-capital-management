#!/usr/bin/env python3
"""Synthetic controls for the validation line; they are not market performance evidence."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from league.swarm.evidence import validation_line

def run():
    good = {"trades":500,"days_traded":200,"days":252,"t_daily":6,"mean_return_on_max_loss_daily":.01,
            "sharpe_daily":1.5,"skew_daily":0,"kurt_daily":3,"quarters_positive":"4/4","pnl":500}
    cases = {"strong_edge": good, "rare_trades": {**good,"trades":10}, "no_edge": {**good,"mean_return_on_max_loss_daily":0},
             "correlated_intraday": {**good,"t_stat":20,"t_daily":1}, "one_good_quarter": {**good,"quarters_positive":"1/4"}}
    out = {name:validation_line({"status":"ok","summary":summary}, {"status":"ok","summary":{"pnl":200}},
                                lineage_trials=100,trial_sharpes=[.1,.2,.05]) for name,summary in cases.items()}
    assert out['strong_edge']['passed'] and all(not v['passed'] for k,v in out.items() if k!='strong_edge')
    return {"kind":"synthetic validation controls; not market evidence","controls":out}
if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
