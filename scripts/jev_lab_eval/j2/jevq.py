"""The repo's own Jev Sensor and client, metered and cached in j2-analysis/jev.sqlite.

Run with PYTHONDONTWRITEBYTECODE=1 so nothing is written into the jev worktree. The gateway token is
read from ~/Work/ltcm-deploy/.env at call time and never printed, logged or stored.
"""
import os
import sys

sys.dont_write_bytecode = True
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from league.jev import Sensor  # noqa: E402
from league.semantic_lab import JevClient  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GATEWAY = "https://ltcm-gateway.blake-woods-personal-site.workers.dev"


def token():
    with open(os.path.expanduser("~/Work/ltcm-deploy/.env")) as fh:
        for line in fh:
            if line.startswith("GATEWAY_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("no gateway token line")


def sensor(**kw):
    return Sensor(os.path.join(HERE, "jev.sqlite"), JevClient(GATEWAY, token), daily_usd="0.50", daily_calls=5000, **kw)


def ask_all(s, purpose, shared, items, *, chunk=16):
    """items: key -> (text, question). Returns key -> p (None when not bought)."""
    out = {}
    keys = list(items)
    for i in range(0, len(keys), chunk):
        part = {k: items[k] for k in keys[i:i + chunk]}
        got = s.ask(purpose, shared, part)
        out.update(got)
        if any(v is None for v in got.values()):
            print("stopped: unanswered items (cap, breaker or outage):", s.refusal(purpose), file=sys.stderr)
            break
    return out
