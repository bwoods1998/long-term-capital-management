"""Run a lane's fixed regressions with the candidate's gate forced open or closed (`_common.force_gate`).

`/judge/_regress.py --gate open|closed --key KEY [--skip TEST_ID ...] -- league.tests.test_a league.tests.test_b`: the
same unittest run the loop makes for the baseline, in the same sandbox, after the override is set in this process.
`--skip` drops the named tests (`module.Class.test`): the loop passes the lane's superseded tests with the gate open
only (`Lane.supersedes`); a named test that does not exist fails the run, so a skip can never hide a typo.
"""
from __future__ import annotations

import sys
import unittest

import _common


def _tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _tests(item)
        else:
            yield item


def main() -> None:
    argv = sys.argv[1:]
    split = argv.index("--") if "--" in argv else len(argv)
    options, modules = argv[:split], argv[split + 1:]
    gate = options[options.index("--gate") + 1] if "--gate" in options else "none"
    key = options[options.index("--key") + 1] if "--key" in options else ""
    skips = {options[i + 1] for i, o in enumerate(options[:-1]) if o == "--skip"}
    _common.force_gate(gate, key)
    loaded = list(_tests(unittest.defaultTestLoader.loadTestsFromNames(modules)))
    missing = skips - {t.id() for t in loaded}
    if missing:
        raise SystemExit(f"superseded tests not found: {sorted(missing)}")
    suite = unittest.TestSuite(t for t in loaded if t.id() not in skips)
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
