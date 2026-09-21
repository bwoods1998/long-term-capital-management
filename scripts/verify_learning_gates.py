"""Deterministic synthetic population controls; no provider, broker or production state access.

python scripts/verify_learning_gates.py > /tmp/game-gate-controls.json

These controls exercise the production evaluator through trusted test ledger fixtures. They
establish mechanical reachability and counterexamples, not predictive power on market data.
"""
from collections import Counter
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from league.constitution import digest
from league.tests.test_episodes import Episodes


def run():
    out = {'kind': 'synthetic evaluator controls, not market forecasts', 'seed': 20260921,
           'constitution_digest': digest(), 'cohorts': {}}
    rng = random.Random(out['seed'])
    for mode in ('strong_mixed_edge', 'zero_gross_edge_after_fees', 'negative_edge', 'tiny_all_wins'):
        decisions, rounds = Counter(), []
        for _ in range(24):
            fixture = Episodes()
            fixture.setUp()
            try:
                for n in range(1, 49):
                    if mode == 'strong_mixed_edge':
                        pnl = '.15' if rng.random() < .7 else '-.01'
                    elif mode == 'zero_gross_edge_after_fees':
                        pnl = '.045' if rng.random() < .5 else '-.055'
                    elif mode == 'negative_edge':
                        pnl = '.01' if rng.random() < .3 else '-.08'
                    else:
                        pnl = '.0003'
                    fixture.roundtrip(pnl)
                    verdict = fixture.ev.judge('a', 'real')
                    if verdict.decision in ('eligible', 'die'):
                        break
                decisions[verdict.decision] += 1
                if verdict.decision == 'eligible':
                    rounds.append(n)
            finally:
                fixture.doCleanups()
        out['cohorts'][mode] = {'agents': 24, 'max_completed_exposures': 48,
                                'decisions': dict(decisions), 'exposures_at_eligibility': rounds}
    return out


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
