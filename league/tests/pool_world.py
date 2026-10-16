"""POOL1's TEST WORLD (league/tests/test_pool_rule.py, league/tests/test_pool_screen.py): an INVENTED House export in the
House job's own format, a receipt of the receipt contract's shape built from it the calibration's way, and the dry run's
fixture receipt. Nothing here is market data, a real figure or a POOL1 figure.

- THE EXPORT (`house`): the vendored p1conform's own CV9 generator (`p1conform.inputs("CV9", seed)`: invented prices
  and trend / reversal weight paths on an invented Mon-Fri calendar of 430 and 560 sessions, every run in the House
  job's `one_run` record format): trend_momentum/index x3 (S2 tickets), trend_momentum/sectors x3 (FWD1 case N; one
  with no FWD1 row), reversal_liquidity/index x3 plus a near-copy (merged), an equity_premium and an event-word
  program (out), and one later trend_momentum/sectors lineage.
- THE RECEIPT (`receipt`): founders, cells, clusters and rho_assign by the vendored `member_from_runs`, `merge_copies`
  and `cells_and_clusters`; each cluster's `c_own_at_pin` by the vendored `cluster_floor` at its caps (the vendored
  `caps_rule` of the U table a test chooses) and the test's own B; an invented matched-family table; the market's
  canonical shas; the conformance block the vendored `p1conform.vectors()` writes; the strict writer's bytes. The
  calibration's own p1report writes the same keys (league/tests/fixtures/pool_screen_1_dryrun.json is one it wrote).
- THE FIXTURE (`dryrun`): the calibration's dry-run receipt (POOL1_SCALE=small, B 40: the dry run's invented market
  and House export, calib/dryrun/; scratch/pooled-screen/calib/tests/force_pass_run.py --pin, made the way the
  calibration's tests/test_receipt_shape.py makes it, at 22:19Z Oct 16 by code whose every sha is CODE PIN 3's),
  copied byte for byte. It is replaced by the calibration's own dry-run receipt at C12."""

from __future__ import annotations

import copy
import functools
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from league.ops import pool_rule as P

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "pool_screen_1_dryrun.json"
SEED = 9009
TM_I, TM_S, RL_I = "trend_momentum/index", "trend_momentum/sectors", "reversal_liquidity/index"
#: The test receipts' constants: the code's, but B (`boot_resamples`) a test's own.
B_TEST = 20


def calib() -> P.Calib:
    cal, why = P.calib()
    assert cal is not None, why
    return cal


@functools.lru_cache(maxsize=None)
def house() -> dict[str, Any]:
    """The invented House export (meta rows, the later lineage's row, prices, every run record, the IN cutpoints)."""
    return calib().conform.inputs("CV9", SEED)


@functools.lru_cache(maxsize=None)
def vectors() -> dict[str, Any]:
    """The conformance block of the vendored p1conform (its own vectors, regenerated)."""
    with P.quiet():
        return calib().conform.vectors()


def constants(B: int = B_TEST) -> dict[str, Any]:
    out = copy.deepcopy(P.CONSTANTS)
    out["boot_resamples"] = int(B)
    return out


def dryrun() -> tuple[bytes, P.Receipt]:
    """The calibration's dry-run receipt fixture: its bytes and its parse (its own B 40)."""
    raw = FIXTURE.read_bytes()
    doc = json.loads(raw)
    rec, why = P.read_receipt(raw, expect_constants=constants(int(doc["constants"]["boot_resamples"])))
    assert rec is not None, why
    return raw, rec


def strict(doc: Mapping[str, Any]) -> bytes:
    """The strict writer's bytes (the contract's section 1)."""
    return (json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode()


def records(pid: int) -> dict[str, dict[str, Any]]:
    runs = house()["runs"]
    return {part: runs[f"{pid}_{part}"] for part in P.PARTS if f"{pid}_{part}" in runs}


def metas() -> list[dict[str, Any]]:
    return sorted(house()["meta"]["members"], key=lambda m: m["pid"])


def later_meta() -> dict[str, Any]:
    return dict(house()["later"])


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


@functools.lru_cache(maxsize=None)
def _build(B: int, u_key: str, refuted: tuple[str, ...], rule: tuple[str, int, int], matched: int,
           dropped: tuple[str, ...]) -> bytes:
    import numpy as np

    cal = calib()
    C = cal.cluster
    h = house()
    cuts = np.array(h["cuts"])
    hc = C.house_context(h["prices"], cuts)
    members, recs = [], {}
    for m in metas():
        rec, mm = P.house_member(cal, m, records(m["pid"]), hc)
        recs[m["lineage"]] = rec
        if mm is not None:
            members.append(mm)
    kept, merged = C.merge_copies(members, hc)
    cc = C.cells_and_clusters(kept, hc)
    lin_of = {mm.name: mm.family for mm in members}
    by_lin = {mm.family: mm for mm in members}
    cell_of = {mm.family: f"{k[0]}/{k[1]}" for k, v in cc["cells"].items() for mm in v}
    cid_of_cell = {f"{k[0]}/{k[1]}": cid for cid, keys in cc["clusters"].items() for k in keys}
    u_table = json.loads(u_key)
    fd_rule, margin_k, c_G_k = rule
    founders: dict[str, Any] = {}
    for m in metas():
        lin = m["lineage"]
        rec = recs[lin]
        st = str(rec["status"])
        status = "member" if st == "member" else ("merged" if st.startswith("merged") else "out")
        mm = by_lin.get(lin)
        tsha = None if status == "out" else {part: hashlib.sha256(_canon(r).encode()).hexdigest()
                                             for part, r in records(m["pid"]).items()}
        cell = f"{m['declared_class']}/{rec.get('group')}" if status == "member" else None
        judged = status == "member" and lin in cell_of
        founders[lin] = {
            "pid": m["pid"], "family": m["family"], "version": m["version"], "lane": m["lane"], "ugroup": m["ugroup"],
            "first_day": m["first_day"], "class": m["declared_class"], "infer_key_class": m["infer_key_class"],
            "status": status, "why": st[5:] if status == "out" else None,
            "merged_into": lin_of[merged[mm.name]] if status == "merged" else None,
            "group": rec.get("group") if status != "out" else None, "cell": cell, "judged": judged,
            "cluster": cid_of_cell.get(cell) if judged else None,
            "ticket": mm.meta["kind"] if status == "member" else None, "fwd1_type": m["fwd1_type"],
            "fwd1_case": m["fwd1_case"], "fwd1_judged": m["fwd1_judged"], "reached_sealed": m["reached_sealed"],
            "seat_shape": m["seat_shape"], "program_sha": m["program_sha"], "train_sha256": tsha}
    units, clusters = {}, {}
    minimum = {"R-REG": matched, "POOLED": matched}
    for ci, (cid, keys) in enumerate(sorted(cc["clusters"].items())):
        cells = [f"{k[0]}/{k[1]}" for k in keys]
        mems = [x.family for k in keys for x in cc["cells"][k]]
        U = {str(n): list(u_table.get(cid, {}).get(str(n), u_table.get(cid, {}).get("*", [0.0, 0.0])))
             for n in P.U_COUNTS}
        drops = [{"lineage": mems[0], "kind": "S2", "why": "an invented drop"}] if cid in dropped else []
        cr = C.caps_rule(U["5"][0], U["5"][1], drops)
        cf = C.cluster_floor(cid, keys, cc["cells"], hc, cuts, B, ci, cr["cap"], cr["wall"])
        own = {}
        for fd in P.FLOORS:
            row = {n: cf["floor"]["floor"][n][fd]["IN"] for n in P.NULLS}
            row["c_own"] = cf["floor"]["c_own"][fd]["IN"]
            row["minimum"] = minimum[fd]
            row["k_used"] = C.k_used_for(row["c_own"], row["minimum"], c_G_k, margin_k)
            own[fd] = row
        ineligible = own[fd_rule]["k_used"] is None
        ref = cid in refuted
        tickets = {x: by_lin[x].meta["kind"] for x in mems if by_lin[x].meta["kind"] is not None}
        clusters[cid] = {
            "cells": cells, "classes": sorted({k[0] for k in keys}), "members": mems,
            "joins": [list(j["joined"]) for j in cc["joins"] if f"{j['joined'][0]}+{j['joined'][1]}" in cid],
            "boot_seed": ci,
            "span": {f"e{e}": ([hc["eras"][e].dates[cf["span"][e][0]], hc["eras"][e].dates[cf["span"][e][1] - 1],
                                cf["span"][e][1] - cf["span"][e][0]] if e in cf["span"] else None) for e in (0, 1)},
            "windows": {f"e{e}": (int(len(cf["point"][(e, "N0")][0])) if e in cf["span"] else 0) for e in (0, 1)},
            "tickets": {"members": tickets, "s2_members": sum(1 for v in tickets.values() if v == "S2"),
                        "fwd1_members": sum(1 for v in tickets.values() if v == "FWD1"), "dropped": drops},
            "U": U, "caps_at_pin": {"count": 5, "cap": cr["cap"], "wall": cr["wall"], "report_only": cr["report_only"],
                                    "why": cr["why"]},
            "report_only": cr["report_only"], "ineligible": ineligible,
            "ineligible_why": "no bar on the grid at the pin" if ineligible else None,
            "stage1": {"refuted": ref, "readable_members": len(mems), "era_refutes": {"e0": ref, "e1": False}},
            "c_own_at_pin": own,
            "seat_members": [x for x in mems if by_lin[x].meta["kind"] == "FWD1" and by_lin[x].group != "index"],
            "expected": {"passes": [0.02, 0.03, 0.05], "seats": [0.0, 0.0, 0.0]},
            "beside": {"fp_point": 0.05, "fp_bound": 0.07, "fp_worst": None, "fp_n1": 0.04, "power_05": 0.2,
                       "power_10": 0.4}}
        for k in keys:
            cell = f"{k[0]}/{k[1]}"
            units[cell] = {"class": k[0], "group": k[1], "cluster": cid, "members": [x.family for x in cc["cells"][k]],
                           "m": len(cc["cells"][k]), "refuted": ref, "report_only": cr["report_only"],
                           "ineligible": ineligible}
    matched_floor: dict[str, Any] = {}
    for (cls, grp), fam in cal.K.MATCH.items():
        matched_floor.setdefault(grp, {})[cls] = {
            "family": fam, "sizes": [3, 4, 7, 10, 15],
            **{fd: {str(m): matched for m in range(3, 61)} for fd in P.FLOORS}}
    market = {}
    for e in (0, 1):
        rec = h["prices"][f"e{e}"]
        market[f"e{e}"] = {"first": rec["days"][0], "last": rec["days"][-1], "sessions": len(rec["days"]),
                           "sha256": hashlib.sha256(P.canonical(rec).encode()).hexdigest()}
    doc = {
        "name": P.NAME, "contract": P.CONTRACT, "prereg_sha256": P.PREREG_SHA256, "status": "PINNED",
        "run": {"index": 1, "second_run_amendment": None, "at": "2026-10-20T12:00:00Z"},
        "calibration": {"code_pin": "TEST", "code_pin_utc": None, "code_sha256": {},
                        "vendored": dict(P.CALIB_SHA256), "pins_log_sha256": "1" * 64,
                        "deviations_log_sha256": "2" * 64, "decision_sha256": "3" * 64, "decision_in_sha256": "4" * 64,
                        "prep_manifest_sha256": "5" * 64,
                        "house_export": {"meta_sha256": "6" * 64, "prices_sha256": "7" * 64, "status_sha256": "8" * 64,
                                         "units": 40, "saved": 40, "failed_twice": []},
                        "python": "3.14.7", "numpy": "2.5.3"},
        "rule": {"name": f"{fd_rule}+{margin_k / 100:.2f}", "floor_def": fd_rule, "margin": margin_k / 100,
                 "margin_k": margin_k, "c_G": c_G_k / 100, "c_G_k": c_G_k},
        "constants": constants(B),
        "regimes": {axis: [float(x) for x in cuts[i]] for i, axis in enumerate(P.REGIME_AXES)},
        "rho_assign": cc["rho_assign"], "founders": founders, "units": units, "clusters": clusters,
        "matched_floor": matched_floor, "market": market, "conformance": vectors(), "record": {"notes": ["a test"]}}
    return strict(doc)


def receipt_bytes(*, B: int = B_TEST, u: Mapping[str, Mapping[str, Any]] | None = None, refuted: tuple[str, ...] = (),
                  rule: tuple[str, int, int] = ("R-REG", 3, 170), matched: int = 150, dropped: tuple[str, ...] = ()
                  ) -> bytes:
    """A receipt of the contract's shape on the invented House export (the module docstring). `u`: {cluster: {count
    or "*": [point, bound]}} (default every U row [0, 0]: caps 0.12 / 0.15, not report-only)."""
    key = json.dumps({k: {str(n): list(v) for n, v in rows.items()} for k, rows in (u or {}).items()}, sort_keys=True)
    with P.quiet():
        return _build(int(B), key, tuple(refuted), tuple(rule), int(matched), tuple(dropped))


def receipt(**kw: Any) -> P.Receipt:
    raw = receipt_bytes(**kw)
    rec, why = P.read_receipt(raw, expect_constants=constants(int(kw.get("B", B_TEST))))
    assert rec is not None, why
    return rec


def doc(**kw: Any) -> dict[str, Any]:
    return json.loads(receipt_bytes(**kw))
