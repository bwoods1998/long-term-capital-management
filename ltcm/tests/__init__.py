# The options overhaul (Sept 26, 2026) cut league/niches.json to the options desk; these first-run tests read the
# pre-overhaul desks (league/tests/__init__.py points `league.niches.NICHES_PATH` at league/tests/fixtures/
# niches_legacy.json) until Wave 2b deletes the legacy package.
import league.tests  # noqa: F401
