"""The league's tests.

The options overhaul (Sept 26, 2026, Wave 2a) cut `league/niches.json` to one desk, the options desk. Most of these tests
were written against the league's desks before it (Kalshi, crypto, equities, the open desks) and use them as fixtures:
until Wave 2b rewrites them for options or deletes them with their modules, they read the pre-overhaul list,
`fixtures/niches_legacy.json`. A test that must see the House's real desks reads `REAL_NICHES_PATH`
(`league/tests/test_options_house.py` does).

Settings as code (V3-A, Oct 2, 2026) put the House's research settings in the repo, `league/swarm/policy.json`, where
every `settings.load` reads them; until then they lived in the box's swarm.json, which no test ever saw. These tests
judge the code against `settings.py`'s DEFAULTS and what each test sets, so a change of the House's settings never
changes what they test: they read `fixtures/policy_empty.json`, a layer that sets nothing. A test that must see the
committed policy reads `REAL_POLICY_PATH` (`league/tests/test_swarm_settings_policy.py` does).
"""

from pathlib import Path

from league import niches as _niches
from league.swarm import settings as _settings

REAL_NICHES_PATH = _niches.NICHES_PATH
LEGACY_NICHES_PATH = Path(__file__).resolve().parent / "fixtures" / "niches_legacy.json"
_niches.NICHES_PATH = LEGACY_NICHES_PATH

REAL_POLICY_PATH = _settings.POLICY_PATH
EMPTY_POLICY_PATH = Path(__file__).resolve().parent / "fixtures" / "policy_empty.json"
_settings.POLICY_PATH = EMPTY_POLICY_PATH
