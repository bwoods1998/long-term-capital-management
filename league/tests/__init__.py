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
committed policy reads `REAL_POLICY_PATH`. `league/tests/test_swarm_settings_policy.py` does, and it is where the
committed file is judged (`TheCommittedPolicy`): its values' kinds, the budget and the guard's lines over it, and the
House's own loop stepping on it, so a settings change the House could not run fails there and nowhere else.

Importing this package is what switches both on, for the whole process. So nothing the House runs may import it (the
House would lose its policy layer and its desks): `TheHouseNeverImportsTheTests`, in the same module, walks the import
closure of the House's entry points and fails if it reaches `league.tests`.
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

# THE PANEL LANE'S CLOCK (release E4, the review's live-4). `league.swarm.elane_xs.live_ready` reads the panel store's
# FRESHNESS by the calendar and a clock (`elane_xs.CLOCK`: the process's own): a store two closed sessions behind the
# clock holds every open of the lane. The tests' synthetic panels (`league.xs.synth`) all end on Friday 2026-10-09, so
# on the wall clock every test that reads the lane "live" would pass until Tuesday 2026-10-13 and fail for ever after.
# For the whole test process the lane's clock is the weekend after that Friday; a test of the freshness leg hands in its
# own `now`, or patches `elane_xs.CLOCK`.
import datetime as _dt

from league.swarm import elane_xs as _elane_xs

PANEL_NOW = _dt.datetime(2026, 10, 11, 16, 0, tzinfo=_dt.timezone.utc).timestamp()
_elane_xs.CLOCK = lambda: PANEL_NOW
