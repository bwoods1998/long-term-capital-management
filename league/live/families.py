"""What the live path reads from the swarm, and writes back: the families it runs, their forward records, their bands.

The options-swarm run, Wave 5 (Sept 26, 2026), the interface agreed with Wave 4 (the swarm) through the main session:

- `league.swarm.bands.read(root)` -> one row per family the live path may run: {family, band ("gym" | "candidate" |
  "probe" | "sized"), structure, roots, holdout_passed, validation_passed, version, code, params, run_sha,
  typical_max_loss_usd (one structure's median maximum loss in its validation run, or None), seed_era, forward
  (the nightly + shadow + real record, with `negative`)}. `SwarmFamilies.read` adds, for a Candidate, Probe or Sized
  row, `validation_r_sd` (`validation_r_sd`, below: DM1's sigma, release L-D, Oct 9, 2026).
- `SwarmStore(root).add_forward(family, "shadow" | "real", trades)`: the live path's forward trades, each once by id, each
  carrying its program `version` (a new version starts its own record).
- `SwarmStore(root).forward(family)`: the whole forward record, one row a trade ({pnl, max_loss, source, ...}).
- `SwarmStore(root).set_band(family, band, reason=...)`: the live path alone moves candidate <-> probe <-> sized (the
  money table is its; the swarm moves gym <-> candidate and retires families).

- `league.swarm.bands.observe(root)` -> the OBSERVE band, the PRACTICE LEAGUE (the sprint, B4, Sept 26, 2026; the Train
  tier Sept 29, 2026): one shadow-only row per alive Gym-band family with a validated version (tier "validated") or,
  without one, an eligible Train version (tier "train"), in the league's admission order (`bands.priority`). The live
  path runs each as a shadow instance `<family>@<version>:o`, its version pinned for the session. An observe row is
  admitted for SHADOW opens only, while the family is alive, still in the Gym band, and the pinned version's code and
  parameters are what the instance runs; it is never real, never tuition, never a forward row, and an observe row never
  stands in for any other band's row.

- `league.swarm.bands.incubator(root, family=f, version=n)` -> THE INCUBATOR's facts (release B, Oct 1, 2026;
  `league/live/incubator.py`): one row, or [], when version `n` of the alive Gym-band family `f` passed Train and the
  drift screen under the current evaluator and its review and audit passed. The row carries no program (the live path
  trades the practice cohort's own snapshot, whose run sha must be the row's) and says `incubator: True`. An incubator
  row admits only an incubator instance (`<family>@<version>:i`, real, tuition-flagged, one lot), and only an incubator
  row admits one (`_entry_matches`); it is never a forward row, a band or a promotion. An unreadable store raises (no new
  pin, no incubator open; exits unaffected).

`MemoryFamilies` is the same API in memory, for tests and for a House without the swarm.

DM1'S SIGMA (release L-D, Oct 9, 2026; `money.demotion`): the sd of r (P&L per dollar of maximum loss, a trade) in the
banded version's Validation run, read from the swarm's family state the way `typical_max_loss_usd` reaches the band
(the same two keys' shape, read for the row, then checked again by `confirm_band` before a band is written), here in
the live path (`SwarmFamilies.read` adds it to `bands.read`'s row, which does not carry it):
`validation_r_sd_by_version[str(version)]`, else `validation_r_sd` while `validation_version` is that version. The
WRITER is the swarm's tournament beside `typical_max_loss_usd` (`league/swarm/tournament.py`, release D-1); until it
ships the state has neither key, the row's value is None, and DM1 takes the forward record's sd or its 2.0 fallback
(`money.dm1_sigma`). A missing, non-numeric, non-finite, zero or negative value reads as absent (`money.positive_sd`).
"""

from __future__ import annotations

import copy
from contextlib import contextmanager
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .money import positive_sd


def validation_r_sd(state: Any, version: Any) -> float | None:
    """DM1's sigma for `version` from a family's swarm state (the module docstring), or None when it is absent: the
    per-version map's value, else the scalar while `validation_version` is `version` (as `typical_max_loss_usd`), read
    by `money.positive_sd` (a positive finite number, else absent). A map that is not a map reads as empty."""
    if not isinstance(state, Mapping):
        return None
    by_version = state.get("validation_r_sd_by_version")
    by_version = by_version if isinstance(by_version, Mapping) else {}
    value = by_version.get(str(version),
                           state.get("validation_r_sd") if state.get("validation_version") == version else None)
    return positive_sd(value)


def _entry_matches(row: Mapping[str, Any] | None, expected: Mapping[str, Any], real: bool) -> bool:
    # The decider's run hash includes merged program defaults; the swarm's hash covers stored overrides. Compare
    # the exact immutable source and overrides actually loaded, so those distinct hash conventions cannot disagree.
    if not row or row.get("version") != expected.get("version"):
        return False
    if bool(row.get("incubator")) != bool(expected.get("incubator")):
        return False  # an incubator row admits only an incubator instance, and only an incubator row admits one
    if expected.get("incubator"):
        # The incubator's facts carry no program: its program is the practice cohort's snapshot, whose run sha (the
        # swarm's) must be the row's. Real opens only, one lot, tuition-flagged, never an observe or a banded row.
        return (real and row.get("band") == "gym" and expected.get("tuition") is True and not expected.get("observe")
                and not row.get("observe") and bool(row.get("run_sha")) and row.get("run_sha") == expected.get("run_sha"))
    if (row.get("code") != expected.get("code")
            or (row.get("params") or {}) != (expected.get("params") or {})):
        return False
    if bool(row.get("observe")) != bool(expected.get("observe")):
        return False  # an observe row admits only an observe instance, and only an observe row admits one
    band = row.get("band")
    if expected.get("observe"):
        # The observe band: shadow opens only, while the family is alive and still in the Gym band. Never real.
        return not real and band == "gym" and not expected.get("tuition")
    if not real:
        return band in ("candidate", "probe", "sized")
    if band != expected.get("band"):
        return False
    if expected.get("tuition"):
        return band == "gym" and bool(row.get("validation_passed")) and not row.get("holdout_passed")
    # `negative_ok` (release L-D): the open's own reading of `money.negative_demotes` under `probe.demotion` "dm1", where a
    # Probe or Sized family's negative forward record no longer ends its band (DM1 does); True only from the live path.
    return (band in ("probe", "sized") and bool(row.get("holdout_passed"))
            and (expected.get("negative_ok") is True or not (row.get("forward") or {}).get("negative")))


class SwarmFamilies:
    """The swarm's store in the House's state root (read and written from the House's process)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._store = None
        self.lock = threading.Lock()

    def _db(self) -> Any:
        if self._store is None:
            from ..swarm.store import SwarmStore

            self._store = SwarmStore(self.root)
        return self._store

    def read(self, family: str | None = None) -> list[dict]:
        """`bands.read`'s rows, a Candidate's, Probe's or Sized's with its `validation_r_sd` (DM1's sigma, the module
        docstring), read under the lock; a state that cannot be read gives None, which `confirm_band` then refuses
        whenever the state holds a value (no band is written on a sigma it did not check)."""
        rows = self._rows(family)
        banded = [row for row in rows if row.get("band") in ("candidate", "probe", "sized")]
        if banded:
            with self.lock:
                for row in banded:
                    try:
                        fam = self._db().family(str(row["family"]))
                        row["validation_r_sd"] = validation_r_sd((fam or {}).get("state") or {}, row.get("version"))
                    except Exception:  # noqa: BLE001 - absent; `confirm_band` refuses a mismatch
                        row["validation_r_sd"] = None
        return rows

    def _rows(self, family: str | None = None) -> list[dict]:
        """`bands.read`'s rows as they are (an admission's: it holds the lock and needs no sigma)."""
        from ..swarm import bands

        return [dict(row) for row in bands.read(self.root, family=family)]

    def observe(self, family: str | None = None, version: int | None = None) -> list[dict]:
        """The observe band's rows (`bands.observe`): shadow only, never real, never a forward row."""
        from ..swarm import bands

        return [dict(row) for row in bands.observe(self.root, family=family, version=version)]

    def incubator(self, family: str, version: int) -> list[dict]:
        """The incubator's facts (`bands.incubator`): one row or []. Raises when the store cannot be read."""
        from ..swarm import bands

        return [dict(row) for row in bands.incubator(self.root, family=family, version=int(version))]

    @contextmanager
    def admit_incubator(self, expected: Mapping[str, Any]):
        """An incubator open's admission (`league/live/incubator.py`): its facts row read again under the lock, matched to
        the instance's identity (`_entry_matches`, real). An unreadable store admits nothing."""
        with self.lock:
            try:
                row = next(iter(self.incubator(str(expected["family"]), int(expected.get("version") or 0))), None)
            except Exception:  # noqa: BLE001 - fail-closed
                row = None
            yield _entry_matches(row, expected, True)

    def forward_rows(self, family: str) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self._db().forward(family)]

    @contextmanager
    def admit_open(self, expected: Mapping[str, Any], *, real: bool):
        """Serialize current eligibility with durable local order admission, never with venue/network work. One family's
        row is read (the live path asks once a minute per instance). An observe instance is shadow only: it is admitted
        against its PINNED version's row (`bands.observe(family=, version=)`), read-only, without the store's write lock,
        and never for a real open."""
        family = str(expected["family"])
        if expected.get("observe"):
            if real:
                yield False
                return
            with self.lock:
                row = next(iter(self.observe(family, int(expected.get("version") or 0))), None)
            yield _entry_matches(row, expected, False)
            return
        with self.lock, self._db().atomic():
            row = next((r for r in self._rows(family) if r["family"] == family), None)
            evidence_current = (not real or expected.get("tuition") or
                                self._db().forward(family) == expected.get("forward_rows"))
            yield _entry_matches(row, expected, real) and evidence_current

    def add_forward(self, family: str, source: str, trades: Iterable[Mapping[str, Any]]) -> int:
        with self.lock:
            return int(self._db().add_forward(family, source, list(trades)) or 0)

    def set_band(self, family: str, band: str, reason: str) -> None:
        with self.lock:
            self._db().set_band(family, band, reason=reason)

    def confirm_band(self, expected: Mapping[str, Any], band: str, reason: str,
                     forward: Sequence[Mapping[str, Any]], *, at: float | None = None) -> bool:
        """Commit a decision only while its identity, eligibility and exact evidence snapshot still hold.

        The gate uses another SQLite connection and can demote, retire or replace this version while the House
        calculates its money band. The immediate transaction excludes those writers through the final band write.
        Even an unchanged Probe/Sized band requires confirmation before scheduling a real instance.
        """
        from ..swarm.gate import run_sha

        with self.lock:
            store = self._db()
            with store.atomic():
                fam = store.family(str(expected["family"]))
                if not fam or fam["retired_at"] or fam["band"] != expected["band"]:
                    return False
                state = fam["state"] or {}
                version = state.get("banded_version")
                if version != expected.get("version"):
                    return False
                selected = store.version(fam["id"], version)
                if selected is None or run_sha(selected) != expected.get("run_sha"):
                    return False
                from ..swarm.bands import current_banded_evaluator

                if not current_banded_evaluator(state, run_sha(selected)):
                    return False
                typical = (state.get("typical_by_version") or {}).get(str(version),
                    state.get("typical_max_loss_usd") if state.get("validation_version") == version else None)
                if (typical != expected.get("typical_max_loss_usd")
                        or validation_r_sd(state, version) != expected.get("validation_r_sd")
                        or state.get("forward") != expected.get("forward")
                        or store.forward(fam["id"]) != list(forward)):
                    return False
                if band != fam["band"]:
                    if store.set_band(fam["id"], band, reason=reason) != fam["band"]:
                        return False
                    if fam["band"] == "candidate" and band in ("probe", "sized"):
                        store.set_state(fam["id"], live_promoted_at=float(store.clock() if at is None else at))
                return True

    def promoted_at(self, family: str) -> float | None:
        with self.lock:
            row = self._db().family(family)
            value = (row["state"] or {}).get("live_promoted_at") if row else None
            return None if value is None else float(value)


class MemoryFamilies:
    """In memory (tests; a House whose swarm is off). Rows as `SwarmFamilies.read` returns them."""

    def __init__(self, rows: Iterable[Mapping[str, Any]] = (), observed: Iterable[Mapping[str, Any]] = (),
                 incubated: Iterable[Mapping[str, Any]] = ()):
        self.rows = {str(r["family"]): dict(r) for r in rows}
        #: The incubator's facts: {(family, version): row} (a row as `bands.incubator` gives it); `incubator_error` makes
        #: every read raise (an unreadable store).
        self.incubated: dict[tuple[str, int], dict] = {
            (str(r["family"]), int(r["version"])): dict(r, incubator=True, observe=False, band="gym", holdout_passed=False,
                                                         validation_passed=False) for r in incubated}
        self.incubator_error: Exception | None = None
        #: The observe band: {family: {version: row}} (a row as `bands.observe` gives it; `tier` "validated" unless the
        #: row says "train"); `observe()` returns each family's highest version (its current one); a family popped from
        #: here is retired or promoted.
        self.observed: dict[str, dict[int, dict]] = {}
        for r in observed:
            self.observed.setdefault(str(r["family"]), {})[int(r["version"])] = dict(
                r, observe=True, band="gym", tier=r.get("tier") or "validated")
        self.forward: dict[str, dict[tuple[str, str], dict]] = {}
        self.moves: list[tuple[str, str, str]] = []
        self.promotions: dict[str, float] = {}
        self.lock = threading.Lock()

    def read(self, family: str | None = None) -> list[dict]:
        with self.lock:
            return [copy.deepcopy(r) for r in self.rows.values() if r.get("band") != "retired"
                    and (family is None or r["family"] == family)]

    def observe(self, family: str | None = None, version: int | None = None) -> list[dict]:
        with self.lock:
            out = []
            for fid, versions in sorted(self.observed.items()):
                if (family is not None and fid != family) or not versions:
                    continue
                row = versions.get(int(version)) if version is not None else versions[max(versions)]
                if row is not None:
                    out.append(copy.deepcopy(row))
            from ..swarm.bands import priority

            for row in out:
                row.setdefault("tier", "validated")
            out.sort(key=priority)  # as `bands.observe`: validated by validation t, then Train by Train score, then id
            return out

    def incubator(self, family: str, version: int) -> list[dict]:
        with self.lock:
            return self._incubator(family, version)

    def _incubator(self, family: str, version: int) -> list[dict]:
        if self.incubator_error is not None:
            raise self.incubator_error
        row = self.incubated.get((str(family), int(version)))
        return [copy.deepcopy(row)] if row is not None else []

    @contextmanager
    def admit_incubator(self, expected: Mapping[str, Any]):
        with self.lock:
            try:
                row = next(iter(self._incubator(str(expected["family"]), int(expected.get("version") or 0))), None)
            except Exception:  # noqa: BLE001
                row = None
            yield _entry_matches(row, expected, True)

    def forward_rows(self, family: str) -> list[dict]:
        with self.lock:
            return [dict(v, source=k[0]) for k, v in sorted(self.forward.get(family, {}).items())]

    @contextmanager
    def admit_open(self, expected: Mapping[str, Any], *, real: bool):
        if expected.get("observe"):
            row = next(iter(self.observe(str(expected["family"]), int(expected.get("version") or 0))), None)
            yield (not real) and _entry_matches(row, expected, False)
            return
        with self.lock:
            family = str(expected["family"])
            rows = [dict(v, source=k[0]) for k, v in sorted(self.forward.get(family, {}).items())]
            evidence_current = not real or expected.get("tuition") or rows == expected.get("forward_rows")
            yield _entry_matches(self.rows.get(family), expected, real) and evidence_current

    def add_forward(self, family: str, source: str, trades: Iterable[Mapping[str, Any]]) -> int:
        if source not in ("nightly", "shadow", "real"):
            raise ValueError(source)
        n = 0
        with self.lock:
            book = self.forward.setdefault(family, {})
            for t in trades:
                key = (source, str(t["id"]))
                if key not in book:
                    book[key] = {"id": str(t["id"]), "day": str(t.get("day") or ""), "pnl": float(t["pnl"]),
                                 "max_loss": float(t.get("max_loss") or 0.0), "version": t.get("version")}
                    n += 1
        return n

    def set_band(self, family: str, band: str, reason: str) -> None:
        with self.lock:
            if family in self.rows and self.rows[family].get("band") != band:
                self.rows[family]["band"] = band
                self.moves.append((family, band, reason))

    def confirm_band(self, expected: Mapping[str, Any], band: str, reason: str,
                     forward: Sequence[Mapping[str, Any]], *, at: float | None = None) -> bool:
        with self.lock:
            family = str(expected["family"])
            current = self.rows.get(family)
            if current != expected:
                return False
            rows = [dict(v, source=k[0]) for k, v in sorted(self.forward.get(family, {}).items())]
            if rows != list(forward):
                return False
            if current["band"] != band:
                if current["band"] == "candidate" and band in ("probe", "sized") and at is not None:
                    self.promotions[family] = float(at)
                self.rows[family]["band"] = band
                self.moves.append((family, band, reason))
            return True

    def promoted_at(self, family: str) -> float | None:
        with self.lock:
            value = self.promotions.get(family, self.rows.get(family, {}).get("real_promoted_at"))
            return None if value is None else float(value)


__all__ = ["SwarmFamilies", "MemoryFamilies"]
