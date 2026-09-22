"""SYNTHETIC: the repair drill's artifact (drill 20260922t152804), not a trading tool; do not use it in a strategy.

It exists so the repair engineer's full loop (patch, CI refusal, revision against CI's own
failure text, merge, deployment, observation) is exercised on production with a change that
cannot matter to any agent.
"""


def checksum(values):
    """The sum of the values."""
    return sum(values) - 1
