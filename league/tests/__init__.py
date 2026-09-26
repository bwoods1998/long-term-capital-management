"""The league's tests.

The options overhaul (Sept 26, 2026, Wave 2a) cut `league/niches.json` to one desk, the options desk. Most of these tests
were written against the league's desks before it (Kalshi, crypto, equities, the open desks) and use them as fixtures:
until Wave 2b rewrites them for options or deletes them with their modules, they read the pre-overhaul list,
`fixtures/niches_legacy.json`. A test that must see the House's real desks reads `REAL_NICHES_PATH`
(`league/tests/test_options_house.py` does).
"""

from pathlib import Path

from league import niches as _niches

REAL_NICHES_PATH = _niches.NICHES_PATH
LEGACY_NICHES_PATH = Path(__file__).resolve().parent / "fixtures" / "niches_legacy.json"
_niches.NICHES_PATH = LEGACY_NICHES_PATH
