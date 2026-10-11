"""THE XS IDENTITY: what a panel band's proof binds to (as an equity band binds to `equity_fingerprint`).

Owner: package E. STEP 0 STUB: the lists are the contract; the three functions raise NotImplementedError until E lands.

`xs_fingerprint` is the sha256, path and bytes in path order (as `league.swarm.evaluator.equity_fingerprint`), over:
league/xs/<name>.py for `XS_EVIDENCE`; league/equity/<name>.py for `XS_EQUITY_DEPS` (the E1 evidence modules league/xs
imports: a change there changed both lanes' evidence, so it moves both identities); the 4 `LEAGUE_FILES`
(`league.gym.driver.LEAGUE_FILES`); `XS_GYM_FILES`; and `XS_CALENDAR_FILES` (the NYSE calendar the store's sessions
and the ctx's calendar fields read).

WHAT MOVES WHAT. A change to an xs evidence module moves the xs identity: `league.swarm.evaluator.adopt_xs` sends every
live PANEL band back to "gym" and touches no ETF family. PLUMBING IS OUT: `book.py` and this file; every league/swarm
and league/ops file; policy.json and the constitution. E4 moves NEITHER the equity identity NOR the options execution
fingerprint (`test_xs_identity.E4MovesNoIdentity`): nothing of league/xs is in league/equity's evidence import closure.

`test_xs_identity.TheClosure` holds `XS_EVIDENCE` equal to the import closure of `XS_EVIDENCE_ROOTS` inside league/xs
plus `synth`, `XS_EQUITY_DEPS` equal to that closure's league.equity imports, and `XS_GYM_FILES` and
`XS_CALENDAR_FILES` equal to E1's lists (`evaluator.EQUITY_GYM_FILES`, `EQUITY_CALENDAR_FILES`).

Plumbing (NOT in the xs identity). league/xs imports nothing of league.swarm, so the lists are written out here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

#: The swarm store's kv key of the xs identity `adopt_xs` last adopted (no band reads it: a band's currency is read
#: from the running release's own files).
XS_KEY = "xs_evaluator"
XS_EVIDENCE = ("__init__", "config", "store", "ctx", "program", "engine", "results", "placebo", "screen", "runner",
               "child", "synth")
XS_EVIDENCE_ROOTS = ("runner", "child", "screen", "engine")
XS_EVIDENCE_EXTRA = ("synth",)
XS_EQUITY_DEPS = ("__init__", "config", "store", "ctx", "program", "engine", "results", "sizing", "screen", "runner",
                  "synth")
XS_GYM_FILES = ("league/gym/__init__.py", "league/gym/safety.py", "league/gym/runtime.py", "league/gym/events.py")
XS_CALENDAR_FILES = ("ltcm/__init__.py", "ltcm/broker.py", "ltcm/data/__init__.py")
#: The modules of this package that are plumbing.
XS_PLUMBING = ("book", "identity")
#: The three PRIVATE names of `league.equity.ctx` league/xs imports (pinned by name: an E1 rename fails a test).
XS_PRIVATE_E1 = ("_encode", "_ro", "_factor_row")

_STUB = "league.xs.identity is a Step 0 stub: package E builds it (league/xs/E4_INTERFACES.md)"


def xs_fingerprint(repo: Path | None = None) -> str:
    """The xs evidence identity of the checkout at `repo` (default: this release): the module docstring's sha256. A
    release that lacks one of its files has no identity (the read raises: no band proof, no look)."""
    raise NotImplementedError(_STUB)


def xs_identity() -> dict[str, str]:
    """{"xs": xs_fingerprint(), "engine": league.xs.XS_ENGINE_VERSION}."""
    raise NotImplementedError(_STUB)


def xs_band_current(state: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """Whether a panel family's band proof (`banded_evaluator` {"engine", "xs_sha256", "run_sha"}) names the xs
    identity `expected` ({"xs", "engine"}): `adopt_xs`'s reader."""
    raise NotImplementedError(_STUB)


__all__ = ["XS_KEY", "XS_EVIDENCE", "XS_EVIDENCE_ROOTS", "XS_EVIDENCE_EXTRA", "XS_EQUITY_DEPS", "XS_GYM_FILES",
           "XS_CALENDAR_FILES", "XS_PLUMBING", "XS_PRIVATE_E1", "xs_fingerprint", "xs_identity", "xs_band_current"]
