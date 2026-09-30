"""Run a lane's fixed regressions with the candidate's gate forced open or closed (`_common.force_gate`).

`/judge/_regress.py --gate open|closed --key KEY -- league.tests.test_a league.tests.test_b`: the same unittest run the
loop makes for the baseline, in the same sandbox, after the override is set in this process.
"""
from __future__ import annotations

import sys
import unittest

import _common


def main() -> None:
    argv = sys.argv[1:]
    split = argv.index("--") if "--" in argv else len(argv)
    options, modules = argv[:split], argv[split + 1:]
    gate = options[options.index("--gate") + 1] if "--gate" in options else "none"
    key = options[options.index("--key") + 1] if "--key" in options else ""
    _common.force_gate(gate, key)
    unittest.main(module=None, argv=["regress", *modules, "-q"])


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
