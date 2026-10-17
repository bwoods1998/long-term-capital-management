"""The `deep_report` job: S3 in REPORT-ONLY mode (release R1; history-expansion plan section 5.2 item 6).

Owner: R1. Protected (league/ops/). Daily at 07:10Z (outside every session in both seasons; a run found inside a
session, padded an hour, is skipped). With `elane.deep.mode` "report" every eligible CURRENT version gets its ONE S3
look (league/deep/gate.py `look`), at most `elane.deep.looks_per_run` a run, one look in ten a canary. The verdicts are
sealed in the look ledger (`<state>/equity-deep/ledger.json`); the captain reads the counts
(`<state>/equity-deep/report.json`, league/deep/report.py): eligible, looked, passed, canaries passed, and the
receipt's prediction, by seat and by source. BIRTHS SEE NOTHING: this job opens the swarm store READ-ONLY and writes
nothing there, no event, no state, no graveyard row; nothing of league/swarm reads the ledger or the report, and the
job's own receipt names no pass. THAT FIRST LOOK IS THE VERSION'S LOOK: it is not repeated when gating starts (H-lite).

THE OWNER'S D2 IS DECIDED (A58): the 2020-21 reserve IS judged, inside S3 beside the deep key and never alone. Each
look reads the deep key and then the recent key on R + V + H (the receipt's calibration). `elane.deep.reserve`
"sealed" is the switch back: then no look is made at all (a version is judged on both keys or not at all).

THE SEAL'S HOUSEKEEPING. The run's first act, whatever the switch says, is the sweep (league/deep/blocks.py
`sweep_store`): a look whose process was killed (the runner's SIGKILL at the wall, a CPU or memory limit, a box
restart) ran no `finally`, and its relabeled DVAL store would be left in `sealed/.looks/`. And no version is begun with
less than `LOOK_ROOM_S` of the job's wall left, so the wall does not land inside a look.

ONE VERSION NEVER STOPS THE NEXT. Each version's look runs inside its own guard: an error of the House's (a child that
failed, a store's slice, a missing price; never a program's own refusal) spends no look (the gate withdraws the
attempt), is recorded in the ledger by version (its class, never its text), raises a House warning, and the job goes on
with the next version; at `HOUSE_ERRORS_MAX` errors under one deep identity the version is refused (no look spent). A
sealed run sent and not answered is "lost" (owed once more) and warned of too. A ledger that cannot be read FAILS
CLOSED: no look, a failed receipt.

THE CURRENT VERSIONS (`current_versions`, as the item-8 eligibility census reads them: history-1017/census/
eligibility_census.py): every alive family of an equity lane but a panel family; of a seated family (any band but
"gym") its banded version; of a Gym family its next-Validation version (the Train record's `passed_version`, else
`best_version`, else `best_train_version`) and its latest version. Each carries its route, whether it is seated, and
its source ("seed" for a captain's seed and its lineage, else "born").

THE RUNS (`HouseRuns`) are the decider-isolated child's (league/equity/runner.py `Isolated` on its own
`league.live.decider.Decider`, its hash seed pinned like the evidence child's), so a program never reaches a store:
the version's NEEDS and its Train-era runs (2016-19, 2022-24) on the House's daily store; a run on a store root (the
relabeled TRAIN-D and DVAL segments, removed after each run, and the behavioural test's synthetic stores); and the
recent key's series at k 1.0: the 2020-21 reserve, Validation (2025) and the look's 194 holdout sessions (with an
`EquityGateCapability` minted under `GATE_REASON`), only inside a begun look (league/deep/gate.py, "how the reserve
stays sealed until the look").

A version's route recall comes from the contamination probe's file (`strong_recall`; the probe's module is not
imported: it stands under the forward record's seal, league/tests/test_forward_report.py): a route whose 2001-08
cells are unmeasured WAITS (no look spent, no run made). A family that names no route: a captain's seed (or one of its
lineage) has no generator's recall to read and is measured as not strong-recall (counted apart by source); any other
is refused (its recall cannot be read).
"""

from __future__ import annotations

import ast
import datetime as dt
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

GATE_REASON = "deep-s3-report"
#: A run inside a session, widened by this many minutes, is skipped (the House's evening and night only).
SESSION_PAD_MIN = 60
#: The contamination probe's file (league/ops/contam_probe.py `FILE`; spelled here, a test holds them equal).
PROBE_FILE = "contamination.json"


# ------------------------------------------------------------------------------------------------- what is looked at
def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def _needs(code: str) -> Mapping[str, Any]:
    try:
        for node in ast.parse(code).body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "NEEDS" for t in node.targets):
                value = ast.literal_eval(node.value)
                return value if isinstance(value, Mapping) else {}
    except (SyntaxError, ValueError):
        pass
    return {}


def _route(fam: Mapping[str, Any]) -> str | None:
    spec = fam.get("spec") if isinstance(fam.get("spec"), Mapping) else {}
    state = fam.get("state") if isinstance(fam.get("state"), Mapping) else {}
    if isinstance(spec.get("route"), str) and spec["route"]:
        return spec["route"]
    for value in state.values():
        if isinstance(value, Mapping) and isinstance(value.get("born_route"), str) and value["born_route"]:
            return value["born_route"]
    return None


def source_of(fam: Mapping[str, Any]) -> str:
    """"seed" for a captain's seed (league/swarm/seeds.py: origin "seed" or "reseed", `seeded` in its spec) and for a
    family of a seed's lineage; "born" otherwise."""
    spec = fam.get("spec") if isinstance(fam.get("spec"), Mapping) else {}
    if str(fam.get("origin") or "") in ("seed", "reseed") or spec.get("seeded") is True:
        return "seed"
    return "seed" if str(fam.get("lineage") or "").startswith("seed-") else "born"


def version_numbers(fam: Mapping[str, Any], latest: int | None) -> list[int]:
    """THE CURRENT VERSIONS of a family (the module docstring), oldest first."""
    state = fam.get("state") if isinstance(fam.get("state"), Mapping) else {}
    if str(fam.get("band") or "gym") != "gym":
        n = _int(state.get("banded_version"))
        return [n] if n is not None else []
    out = set()
    if latest is not None:
        out.add(latest)
    rec = state.get("elane_e2") if isinstance(state.get("elane_e2"), Mapping) else {}
    nv = _int(rec.get("passed_version")) or _int(fam.get("best_version")) or _int(state.get("best_train_version"))
    if nv is not None:
        out.add(nv)
    return sorted(out)


def current_versions(store: Any) -> list[dict[str, Any]]:
    """Every current version of the living equity families (panel families left out): {"fid", "n", "code", "params",
    "cell", "route", "seated", "source"}. A version whose file cannot be read is left out."""
    from ..equity import LANES
    from ..swarm import elane_train

    out = []
    for fam in store.families(alive=True, lanes=LANES):
        if str(fam.get("structure") or "") == "panel":
            continue
        latest = store.latest_version(str(fam["id"]))
        for n in version_numbers(fam, int(latest["n"]) if latest else None):
            row = store.version(str(fam["id"]), n)
            if not row or not row.get("code"):
                continue
            needs = _needs(row["code"])
            symbols = [str(s).upper() for s in (needs.get("symbols") or []) if isinstance(s, str)]
            spec = fam.get("spec") if isinstance(fam.get("spec"), Mapping) else {}
            cell = "/".join(elane_train.cell_of(spec.get("lane") or "equity", spec.get("agenda"), symbols))
            out.append({"fid": str(fam["id"]), "n": int(n), "code": row["code"],
                        "params": dict(row.get("params") or {}), "cell": cell, "route": _route(fam),
                        "seated": str(fam.get("band") or "gym") != "gym", "source": source_of(fam)})
    return out


def read_probe(root: str | Path) -> dict[str, Any]:
    """The probe's file as published (aggregates only), or an empty one."""
    from .context import read_json

    doc = read_json(Path(root) / PROBE_FILE, None)
    return doc if isinstance(doc, dict) and isinstance(doc.get("routes"), dict) else {"routes": {}}


def strong_recall(doc: Mapping[str, Any] | None, route: str | None, eras: Any = None) -> bool | None:
    """S3'S ELIGIBILITY READING of a route: True when a published, readable cell of `eras` (default
    league/deep/config.py `STRONG_ERAS`: "2001-08") has m above `STRONG_M` at p_perm at most `STRONG_P`; False when
    the route's result holds a cell of those eras and none is; None when it holds none (or no route is named):
    unmeasured, and the look waits."""
    from ..deep import config as deep_config

    eras = tuple(eras or deep_config.STRONG_ERAS)
    routes = doc.get("routes") if isinstance(doc, Mapping) and isinstance(doc.get("routes"), Mapping) else {}
    row = routes.get(route) if route else None
    cells = row.get("cells") if isinstance(row, Mapping) and isinstance(row.get("cells"), Mapping) else {}

    def number(value: Any) -> float | None:
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    seen = False
    for by_era in cells.values():
        if not isinstance(by_era, Mapping):
            continue
        for era in eras:
            cell = by_era.get(era)
            if not isinstance(cell, Mapping):
                continue
            seen = True
            m, p = number(cell.get("m")), number(cell.get("p_perm"))
            if cell.get("readable") and m is not None and p is not None and m > deep_config.STRONG_M \
                    and p <= deep_config.STRONG_P:
                return True
    return False if seen else None


# ------------------------------------------------------------------------------------------------------------ the runs
class HouseRuns:
    """`league.deep.gate.Runs` over the House's decider child (the module docstring)."""

    def __init__(self, root: Path, decider: Any):
        from ..equity.runner import Isolated

        self.root = Path(root)
        self.decider = decider
        self.equity_root = self.root / "equity-daily"
        self.isolated = Isolated(decider, self.equity_root)

    def needs(self, code: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.isolated.needs(code, params, name="deep")

    def segments(self, code: str, params: Mapping[str, Any]) -> Sequence[Any]:
        return self.isolated.segments(code, params, name="deep")

    def on_store(self, root: Path, code: str, params: Mapping[str, Any], start: dt.date, end: dt.date, k: float) -> Any:
        from ..equity.runner import Isolated

        return Isolated(self.decider, root).train(code, params, name="deep", start=start, end=end, k=k)

    def recent(self, code: str, params: Mapping[str, Any]) -> list[np.ndarray] | None:
        from ..deep import config
        from ..equity import screen
        from ..equity.store import mint_equity_gate_capability

        symbols = list(self.needs(code, params)["symbols"])
        cap = mint_equity_gate_capability(self.equity_root, GATE_REASON)
        runs = [self.isolated.train(code, params, name="deep", start=config.RESERVE[0], end=config.RESERVE[1],
                                    k=config.K_RECENT),
                self.isolated.validation(code, params, name="deep", k=config.K_RECENT),
                self.isolated.look(code, params, name="deep", gate=cap, k=config.K_RECENT)]
        out = []
        for run in runs:
            if run.result.get("status") == "disqualified":
                return None   # the program's own errors: the recent key fails (gate.Runs)
            if run.result.get("status") != "ok":
                raise RuntimeError(f"a recent-key run did not finish ({run.result.get('status')})")
            capital = float(str(run.result.get("capital") or 1000))
            out.append(screen.series(run.result["lots"], run.bars, universe=symbols, capital=capital).r)
        return out


def _decider(root: Path) -> Any:
    from ..live.decider import Decider
    from ..swarm.elane import EVIDENCE_HASH_SEED

    decider = Decider(log=root / "equity-deep-decider.log")
    decider.hash_seed = EVIDENCE_HASH_SEED
    return decider


# ------------------------------------------------------------------------------------------------------------- the job
def _version(row: Mapping[str, Any], contamination: Mapping[str, Any]) -> Any:
    """The gate's `Version` of a current version's row: its recall read from the probe's file; a family that names no
    route is a seed's (not strong-recall: no generator's recall to read) or refused by the gate (`route_known`)."""
    from ..deep import gate

    route = row.get("route")
    source = str(row.get("source") or "born")
    if route:
        recall, known = strong_recall(contamination, route), True
    else:
        recall, known = (False, True) if source == "seed" else (None, False)
    return gate.Version(fid=row["fid"], n=row["n"], code=row["code"], params=row["params"], cell=row["cell"],
                        strong_recall=recall, route_known=known, seated=bool(row.get("seated")), source=source)


def report_run(ctx: Any, *, runs: Any = None, worlds: int | None = None,
               clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """THE JOB's body (`runs`, `worlds` and `clock`: the tests' in-process runs, smaller floors and wall clock)."""
    from ..deep import blocks, config, gate, identity, report
    from ..swarm import settings as settings_mod
    from ..swarm.store import SwarmStore
    from . import equity_deep, schedule

    began = clock()
    root = Path(ctx.root)
    deep_root = root / config.STORE_DIR
    swept = blocks.sweep_store(deep_root)   # THE SEAL'S HOUSEKEEPING FIRST: a killed look's stores go, whatever else
    if swept:
        ctx.alert("warning", f"deep_report swept {swept} temporary store(s) a killed look left in the deep store")
    c = config.cfg(settings_mod.load(root, config=ctx.config))
    if c["mode"] != "report":
        return {"status": "skipped", "why": f"elane.deep.mode is {c['mode']} (R1 runs in report mode only)"}
    if c["reserve"] != "judged":
        return {"status": "skipped", "why": "elane.deep.reserve is sealed: a version is judged on both keys or not at "
                                            "all, so no look is made"}
    now = float(ctx.now())
    if schedule.in_session(now, pad_minutes=SESSION_PAD_MIN):
        return {"status": "skipped", "why": "inside a session: S3's looks run in idle hours"}
    if not equity_deep.complete(deep_root):
        return {"status": "skipped", "why": "the deep store is not complete (league/ops/equity_deep.py)"}
    if not (root / "swarm.sqlite").exists():
        return {"status": "skipped", "why": "no swarm store"}
    ledger = gate.Ledger(deep_root)
    deep_id = identity.deep_fingerprint()[:12]
    if ledger.damaged:   # THE LEDGER FAILS CLOSED: no look, nothing written over it
        ctx.alert("warning", f"deep_report: the look ledger is damaged ({ledger.problem}); no look until the captain "
                             f"restores it ({config.LEDGER_PREV} is the file before its last save)")
        report.write(deep_root, report.summary(ledger, identity=deep_id))
        return {"status": "failed", "error": f"the look ledger is damaged ({ledger.problem}): no look was made"}
    store = SwarmStore(root, readonly=True)
    try:
        rows = current_versions(store)
    finally:
        store.close()
    contamination = read_probe(root)
    stamp = schedule.iso(now)
    versions: dict[str, Any] = {}
    for row in rows:
        v = _version(row, contamination)
        versions.setdefault(v.key, v)
    budget = int(c["looks_per_run"])
    raw_room = ctx.job_settings().get("look_room_s")   # <state>/ops.json: the owner's override of the look's room
    room = float(raw_room) if isinstance(raw_room, (int, float)) and not isinstance(raw_room, bool) and raw_room >= 0 \
        else float(config.LOOK_ROOM_S)
    own = runs is None
    if own:
        runs = HouseRuns(root, _decider(root))
    done = canaries = waiting = errors = 0
    statuses: dict[str, int] = {}
    stopped = None
    kwargs = {"worlds": worlds} if worlds is not None else {}

    def guarded(v: Any, *, kind: str) -> dict[str, Any]:
        """One look, inside its own guard: an error of the House's spends nothing and stops nothing."""
        nonlocal errors
        try:
            return gate.look(deep_root, v, runs, ledger=ledger, identity=deep_id, now=stamp, reserve=True, kind=kind,
                             **kwargs)
        except gate.LedgerDamaged:
            raise
        except Exception as exc:  # noqa: BLE001 - THE HOUSE'S ERROR: the gate withdrew the attempt; go on
            errors += 1
            count = ledger.house_error(v.key, identity=deep_id, at=stamp, stage=kind, error=type(exc).__name__)
            refused = count >= config.HOUSE_ERRORS_MAX
            if refused:
                ledger.refuse(v.key, f"the House could not run its look {count} times ({type(exc).__name__})",
                              identity=deep_id, at=stamp)
            ctx.alert("warning", f"deep_report: the S3 {kind} of {v.fid} v{v.n} hit an error of the House's "
                                 f"({type(exc).__name__}, {count} of {config.HOUSE_ERRORS_MAX}); its look is not spent"
                                 + ("; refused until a release moves the deep identity" if refused else
                                    "; it is tried again on a later night"))
            return {"status": "house_error"}

    try:
        for key, v in versions.items():
            if done >= budget:
                break
            if config.JOB_WALL_S - (clock() - began) < room:
                stopped = "time"
                break
            found = ledger.row(key)
            if found is not None and found.get("verdict") is not None:
                continue
            if key in ledger.refused and ledger.refused[key].get("identity") == deep_id:
                continue
            if ledger.canary_due():
                try:
                    canary = gate.canary_for(ledger, versions, runs)
                except Exception as exc:  # noqa: BLE001 - the canary's source runs failed: no canary this run
                    canary = None
                    errors += 1
                    ctx.alert("warning", f"deep_report: the canary could not be built ({type(exc).__name__})")
                if canary is not None:
                    out = guarded(canary, kind="canary")
                    canaries += out["status"] == "looked"
                    done += out["status"] == "looked"
                    if out["status"] == "looked" and ledger.canary_alarm():
                        ctx.alert("warning", "deep_report: the canaries' deep-key passes are above the band at the "
                                             "receipt's own synthetic canary rate (report-only; no halt)")
                    if done >= budget:
                        break
                    if config.JOB_WALL_S - (clock() - began) < room:
                        stopped = "time"
                        break
            out = guarded(v, kind="look")
            statuses[out["status"]] = statuses.get(out["status"], 0) + 1
            done += out["status"] == "looked"
            waiting += out["status"] == "waits"
            if out["status"] == "lost":
                ctx.alert("warning", f"deep_report: the S3 look of {v.fid} v{v.n} sent a sealed run that did not "
                                     f"return; it is owed once more (read equity-deep-decider.log)")
            elif out["status"] == "failed":
                ctx.alert("warning", f"deep_report: the S3 look of {v.fid} v{v.n} was begun twice and never finished "
                                     f"(a sealed run that did not return, or a killed process): spent and failed")
            if out["status"] in ("halted", "budget", "ledger"):
                break
    finally:
        if own:
            runs.decider.close()
    summary = report.summary(ledger, waiting=waiting, identity=deep_id)
    report.write(deep_root, summary)
    # The job's receipt carries counts of work only: what passed, the canaries' verdicts included, is the captain's
    # report alone (report.json), never a receipt another reader of the House sees.
    out = {"ok": True, "versions": len(versions), "looked": statuses.get("looked", 0), "canaries": canaries,
           "house_errors": errors, "statuses": statuses,
           "report": {k: summary[k] for k in ("eligible", "looked", "budget")}}
    if stopped:
        out["stopped"] = stopped
    if swept:
        out["swept"] = swept
    return out


def run(ctx: Any) -> dict[str, Any]:
    return report_run(ctx)


__all__ = ["GATE_REASON", "SESSION_PAD_MIN", "PROBE_FILE", "source_of", "version_numbers", "current_versions",
           "read_probe", "strong_recall", "HouseRuns", "report_run", "run"]
