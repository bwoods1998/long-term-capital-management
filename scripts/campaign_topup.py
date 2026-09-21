"""Account-owner action: record money added at a provider so the funded burst may spend it.

    python scripts/campaign_topup.py --id topup-2026-09-21 --openai 200 --sail 100

Append-only and idempotent by identity. It raises the burst's ceilings; it resets no spend,
no meter and no hold. Put the money in the provider account first. For OpenAI, the gateway's
own month (FRONTIER_MONTH_USD in gateway/wrangler.jsonc) is a separate, lower line.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.floor_box import client, read_state, require_box


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True)
    parser.add_argument('--openai')
    parser.add_argument('--sail')
    parser.add_argument('--note', default='owner added money at the provider')
    args = parser.parse_args(argv)
    rows = [(k, v) for k, v in (('openai', args.openai), ('sail', args.sail)) if v]
    if not rows:
        parser.error('name --openai and/or --sail')
    code = ("import json,sys; sys.path.insert(0,'/workspace/current'); from league.campaigns import CampaignBudget; "
            "g=CampaignBudget('/workspace/state/campaigns.sqlite'); ident,note=sys.argv[1],sys.argv[2]; "
            "[g.top_up(ident+':'+k, k, v, note) for k,v in json.loads(sys.argv[3])]; "
            "b=g.burst(); print(json.dumps({'caps_usd': b['policy']['caps_usd'], 'topups_usd': b['topups_usd'], "
            "'remaining_usd': {k: str(g.remaining(k)) for k in ('sail','openai')}}, indent=2))")
    result = client().exec(require_box(read_state()), ['/workspace/.venv/bin/python', '-c', code, args.id, args.note, json.dumps(rows)],
                           timeout=60, on_output=None)
    result.check()
    print(result.stdout)


if __name__ == '__main__':
    main()
