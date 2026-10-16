"""POOL1 calibration: THE HOUSE CLUSTER FUNCTIONS, one module both sides run (RECEIPT-CONTRACT POOL1-RECEIPT-1,
sections 4 and 5). PURE: numpy, the standard library and the calibration's PREP modules (p1const, p1stat, p1members,
p1units, p1engine) only; no fw9 path, no file I/O. P1 vendors this file byte for byte into league/ops/pool_calib/ and
calls it for every definition the calibration gates, so the bar P1 computes at a look is the bar the calibration
gated (contract 0.1).

Moved word for word from p1house.py (DEVIATIONS D30; the dry run before and after the move is byte-identical):
the House calendar (HouseEra, house_context), the member rule's exclusions (_out_reason), the ticket kinds
(ticket_kind), the Train z on the House calendar (z_on_calendar, corr_common), the copy merge (merge_copies), the
cells, clusters and rho_assign (cells_and_clusters, its member rule as join_clusters), stage 1 (seen_series, stage1)
and a cluster through the rule (Proxy, cluster_cells, cluster_point, cluster_boot, shares_from).
Also moved word for word: member_from_runs (the body of p1house.build_members' loop) and cluster_floor (the floor
block of p1run.house_units).

New (contract 4): caps_rule (CAP_u, WALL_u and the report-only rule, the same in fit_floors and G6: D31, D32),
k_used_for (the bar), event_word (the event-reader scan), assign_cell (a later lineage's cell, contract 3.5),
join_rule (1.4's member rule for two clusters), cluster_boot_one (one variant's resamples, so P1 can spread them
over nights), cluster_cols, U_COUNTS (the counts U_u is tabulated by), FAILED_TWICE_WHY and CONTRACT. Changed
beyond the move: ticket_kind fails closed (a sectors or defensive lineage with no FWD1 row holds FWD1: D31);
member_from_runs takes the twice-failed units (D33); cluster_cells takes joins and the founders' sigma; and
cluster_point and cluster_boot_one keep the cells' common prefix of windows when a cell's M_MIN-th member joins
later (D37). With their defaults (every join 0) these give the calibration's numbers unchanged."""
from __future__ import annotations

import datetime as dt
import math
import re

import numpy as np

import p1const as K
from p1engine import SPANS, fit_floors, point_all, variants
from p1members import EraBase, EraPart, Member, cells_of, fit_constants, seed_of, vol_tercile, window_stats
from p1stat import alpha_era, newey_west_z
from p1units import EraBoot, boot_g, make_unit, share_curves

CONTRACT = "POOL1-RECEIPT-1"
EPOCH = dt.date(1970, 1, 1)
#: The FWD1-R checkpoint counts U_u is tabulated by; "0" is S2 alone (contract 3.8).
U_COUNTS = (0,) + tuple(K.FWD1_PLAN)
#: The House job's event-reader scan (house_job/pool1_house_job.EVENT_WORD, CODE PIN 1): the word anywhere in the
#: frozen code (DEVIATIONS D18).
EVENT_WORD = re.compile(r"\bevents(?:_next)?\b")
#: The why of a founder whose House run failed twice (RECEIPT-CONTRACT 3.6, C5; supersedes DEVIATIONS D24).
FAILED_TWICE_WHY = "its Train run failed twice on the House (counted as the program's own failure)"


def _iso(o: int) -> str:
    return (EPOCH + dt.timedelta(days=int(o))).isoformat()


class HouseEra:
    """One Train era on the House's calendar: dates, R and `have` per ETF symbol (the prices task)."""

    def __init__(self, ent: dict):
        self.dates = list(ent["days"])
        self.T = len(self.dates)
        self.at = {d: i for i, d in enumerate(self.dates)}
        self.R, self.have = {}, {}
        for s in K.ETFS:
            if s not in ent:
                continue
            v = ent[s]
            self.have[s] = np.array([x is not None for x in v])
            self.R[s] = np.array([0.0 if x is None else float(x) for x in v])
        self.have["SPY"] = self.have.get("SPY", np.ones(self.T, dtype=bool))


def house_context(prices: dict, cuts: np.ndarray) -> dict:
    eras = [HouseEra(prices[f"e{e}"]) for e in (0, 1)]
    bases, cells, vt = [], {}, {}
    for e, he in enumerate(eras):
        R = dict(he.R)
        for s in ("SPY", "TLT", "GLD"):
            R.setdefault(s, np.zeros(he.T))
        base = EraBase.from_returns(R, {s: he.have.get(s, np.ones(he.T, dtype=bool)) for s in R})
        bases.append(base)
        st = window_stats(base, None, np.arange(0, he.T - K.L + 1))
        cells[e] = cells_of(st, cuts)
        vt[e] = vol_tercile(cells[e])
    return {"eras": eras, "bases": bases, "cells": cells, "vt": vt, "cuts": cuts}


def _out_reason(m: dict) -> str | None:
    if m.get("panel"):
        return "panel"
    if m.get("declared_class") == "equity_premium":
        return "class equity_premium (a beta claim)"
    if "event_calendar" in (m.get("inputs") or []) or m.get("event_word"):
        return "event reader (card input or code scan)"
    if "stocks" in str(m.get("ugroup")):
        return "a stocks symbol (NEEDS)"
    if not m.get("declared_class"):
        return "no declared class (no card)"
    return None


def member_from_runs(m: dict, runs: dict, hc: dict, group_of_symbol, failed=()) -> tuple[dict, Member | None]:
    """One lineage's record (ids and words) and its founding Member on the House eras, or None when it is out (1.2).
    m: the House job's meta row; runs: {"<pid>_<part>": the job's one_run record}; group_of_symbol: the House's
    group of a symbol list (fw9 elane_train.symbols_group); failed: the House export's units ("<pid>:<part>") that
    failed twice: a founder with one is out, counted as the program's own failure (RECEIPT-CONTRACT C5, 3.6)."""
    eras = hc["eras"]
    rec = {k: m.get(k) for k in ("lineage", "pid", "family", "version", "lane", "ugroup", "declared_class",
                                 "infer_key_class", "first_day", "seat_shape", "reached_sealed", "fwd1_type",
                                 "fwd1_case", "program_sha")}
    why = _out_reason(m)
    if why:
        rec["status"] = f"out: {why}"
        return rec, None
    gone = sorted(u for u in failed if str(u).split(":")[0] == str(m["pid"]))
    if gone:
        rec["status"] = f"out: {FAILED_TWICE_WHY}"
        rec["failed_twice"] = gone
        return rec, None
    parts, raw, missing = [], {}, None
    universe = None
    for e in (0, 1):
        k10, k15 = runs.get(f"{m['pid']}_e{e}k10"), runs.get(f"{m['pid']}_e{e}k15")
        if k10 is None or k15 is None:
            missing = "its Train series is missing (the House's: it waits)"
            break
        if k10.get("status") == "no_data":
            parts.append(None)
            continue
        if k10.get("status") != "ok" or k15.get("status") != "ok":
            missing = f"a Train run ended {k10.get('status')}/{k15.get('status')}"
            break
        days = [_iso(x) for x in k10["days"]]
        if [_iso(x) for x in k15["days"]] != days:
            missing = "its two Train runs differ in their sessions"
            break
        idx = [eras[e].at.get(d) for d in days]
        if any(i is None for i in idx) or idx != list(range(idx[0], idx[0] + len(idx))):
            missing = "its Train sessions are not the House calendar's"
            break
        uni = list(k10["universe"])
        universe = universe or uni
        if uni != universe:
            missing = "its universe differs between eras"
            break
        T = eras[e].T
        p0, p1 = idx[0], idx[-1] + 1
        S = len(uni)
        W = np.zeros((S, T)); R = np.zeros((S, T))
        for j, s in enumerate(uni):
            if s in k10["ws"]:
                W[j, p0:p1] = np.nan_to_num(np.array(k10["ws"][s], dtype=float))
            R[j, p0:p1] = np.nan_to_num(np.array(k10["R"][s], dtype=float))
        r = np.zeros(T); r15 = np.zeros(T); sides = np.zeros(T)
        r[p0:p1] = np.nan_to_num(np.array(k10["r"], dtype=float))
        r15[p0:p1] = np.nan_to_num(np.array(k15["r"], dtype=float))
        sides[p0:p1] = np.nan_to_num(np.array(k10["sides"], dtype=float))
        parts.append(EraPart(p0=p0, p1=p1, W=W, r=r, r15=r15, sides=sides, R=R, lots=True))
        raw[e] = {"r": r[p0:p1].copy(), "r15": r15[p0:p1].copy(),
                  "w": np.nan_to_num(np.array(k10["w"], dtype=float)),
                  "b": np.nan_to_num(np.array(k10["b"], dtype=float)),
                  "exits": np.array(k10["exits"], dtype=np.int64),
                  "invested": np.array(k10["invested"], dtype=bool), "p0": p0, "p1": p1}
    if missing or not any(p is not None for p in parts):
        rec["status"] = f"out: {missing or 'no Train-era history'}"
        return rec, None
    if any(s not in K.ETFS for s in universe):
        rec["status"] = "out: a stocks symbol (its universe)"
        return rec, None
    mm = Member(name=f"P{m['pid']}", family=m["lineage"], group="", cls=m["declared_class"], syms=tuple(universe),
                parts=parts)
    present = [e for e in (0, 1) if parts[e] is not None]
    fit_constants(mm, present, hc["vt"])
    expo = np.concatenate([np.abs(parts[e].W[:, parts[e].p0:parts[e].p1]).sum(0) for e in present])
    if expo.mean() < K.MIN_EXPOSURE:
        rec["status"] = "out: Train-era mean total exposure under 1%"
        return rec, None
    share = {}
    for j, s in enumerate(universe):
        grp = group_of_symbol([s])
        share[grp] = share.get(grp, 0.0) + sum(float(np.abs(parts[e].W[j]).sum()) for e in present)
    tot = sum(share.values())
    best = max(share, key=share.get) if tot > 0 else None
    if best is None or best not in ("index", "sectors", "defensive") or share[best] <= K.GROUP_SHARE * tot:
        rec["status"] = "out: no base group holds over 2/3 of its Train-era exposure"
        rec["group_shares"] = {g: round(v / tot, 4) for g, v in share.items()} if tot > 0 else {}
        return rec, None
    mm.group = best
    mm.meta = {"rec": rec, "raw": raw, "pid": m["pid"], "program_sha": m.get("program_sha"),
               "seen_spans": m.get("seen_spans"), "hidden": m.get("hidden"), "kind": ticket_kind(m, best)}
    rec["status"] = "member"
    rec["group"] = best
    return rec, mm


def ticket_kind(m: dict, group: str) -> str | None:
    """The member's per-program seat ticket (7.2, outcome-free): S2 when it reached a sealed pre-check (or is an index
    lineage owed its S2 try: no FWD1 row); FWD1 when FWD1 judges it as an ETF lineage of case N, or (fail closed,
    RECEIPT-CONTRACT C3, DEVIATIONS D31) when it is a sectors or defensive lineage with no FWD1 row yet (a weekend
    birth FWD1 sights after the House read: it holds FWD1-R through its checkpoints before the clock); else none."""
    if m.get("reached_sealed"):
        return "S2"
    if m.get("fwd1_type") == "ETF" and m.get("fwd1_case") == "N":
        return "FWD1"
    if group == "index" and m.get("fwd1_type") is None:
        return "S2"
    if group in ("sectors", "defensive") and m.get("fwd1_type") is None:
        return "FWD1"
    return None


def z_on_calendar(mm: Member, hc: dict) -> np.ndarray:
    """The member's raw Train z (era-restart a over sigma) on the two eras' concatenated calendar, NaN off its pools."""
    out = []
    for e, he in enumerate(hc["eras"]):
        z = np.full(he.T, np.nan)
        pt = mm.parts[e]
        if pt is not None:
            z[pt.p0:pt.p1] = mm.a_era(e)[pt.p0:pt.p1] / max(mm.sigma, 1e-12)
        out.append(z)
    return np.concatenate(out)


def corr_common(a: np.ndarray, b: np.ndarray) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 30 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return float("nan")
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


def merge_copies(members: list[Member], hc: dict) -> tuple[list[Member], dict]:
    kept, merged = [], {}
    Z = {mm.name: z_on_calendar(mm, hc) for mm in members}
    for mm in members:
        into = None
        for k in kept:
            if mm.meta.get("program_sha") and mm.meta.get("program_sha") == k.meta.get("program_sha"):
                into = k.name
                break
            c = corr_common(Z[mm.name], Z[k.name])
            if np.isfinite(c) and c >= K.COPY_RHO:
                into = k.name
                break
        if into:
            merged[mm.name] = into
            mm.meta["rec"]["status"] = f"merged into {into} (1.3)"
        else:
            kept.append(mm)
    return kept, merged


def join_rule(cross: float, wa: float, wb: float) -> bool:
    """1.4's member rule for two clusters: the mean cross-cluster member-pair correlation is above zero and at least
    half the smaller of the two clusters' mean within-cell correlations."""
    return bool(cross > 0 and np.isfinite(wa) and np.isfinite(wb) and cross >= 0.5 * min(wa, wb))


def join_clusters(clusters: dict, judged: dict, Z: dict, cell_within: dict) -> tuple[dict, list]:
    """Average linkage, repeatedly, the strongest join first (1.4). clusters: {cid: [cell key]} (changed in place and
    returned); judged: {cell key: [Member]}; Z: {member name: z on the House calendar}; cell_within: {cell key: the
    cell's mean within-cell member-pair correlation}. -> (clusters, joins)."""
    joins = []
    while True:
        names = sorted(clusters)
        best = None
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                ma = [x.name for c in clusters[a] for x in judged[c]]
                mb = [x.name for c in clusters[b] for x in judged[c]]
                cs = [corr_common(Z[x], Z[y]) for x in ma for y in mb]
                cs = [c for c in cs if np.isfinite(c)]
                if not cs:
                    continue
                cross = float(np.mean(cs))
                wa = np.nanmean([cell_within[c] for c in clusters[a]])
                wb = np.nanmean([cell_within[c] for c in clusters[b]])
                if join_rule(cross, wa, wb):
                    if best is None or cross > best[0]:
                        best = (cross, a, b)
        if best is None:
            break
        _, a, b = best
        clusters[f"{a}+{b}"] = clusters.pop(a) + clusters.pop(b)
        joins.append({"joined": [a, b], "cross": round(best[0], 4)})
    return clusters, joins


def assign_cell(z: np.ndarray, cell_z: dict, rho_assign: float | None) -> tuple[str | None, dict]:
    """A later lineage's cell (RECEIPT-CONTRACT 3.5): its correlation with each candidate cell's D (the nanmean of
    the cell's FOUNDERS' z on the House calendar; at least 30 common finite sessions), the cell with the highest
    correlation when that is >= rho_assign; None when rho_assign is None or no cell reaches it.
    z: the lineage's z_on_calendar; cell_z: {cell id: (n_founders, sessions) founders' z}, its group's cells only."""
    corr = {}
    for cid in sorted(cell_z):
        M = np.asarray(cell_z[cid], dtype=np.float64)
        D = np.nanmean(np.where(np.isfinite(M), M, np.nan), axis=0)
        corr[cid] = corr_common(z, D)
    if rho_assign is None:
        return None, corr
    ok = [(c, cid) for cid, c in corr.items() if np.isfinite(c) and c >= rho_assign]
    if not ok:
        return None, corr
    return max(ok, key=lambda x: (x[0], x[1]))[1], corr


def cells_and_clusters(members: list[Member], hc: dict) -> dict:
    Z = {mm.name: z_on_calendar(mm, hc) for mm in members}
    cells: dict = {}
    for mm in members:
        cells.setdefault((mm.cls, mm.group), []).append(mm)
    judged = {k: v for k, v in cells.items() if len(v) >= K.M_MIN}
    below = {f"{k[0]}/{k[1]}": len(v) for k, v in cells.items() if len(v) < K.M_MIN}

    def within(cell_members):
        names = [x.name for x in cell_members]
        cs = [corr_common(Z[a], Z[b]) for i, a in enumerate(names) for b in names[i + 1:]]
        cs = [c for c in cs if np.isfinite(c)]
        return float(np.mean(cs)) if cs else float("nan")

    cell_within = {k: within(v) for k, v in judged.items()}
    clusters = {}
    for k in judged:
        clusters.setdefault(k[0], []).append(k)
    clusters, joins = join_clusters(clusters, judged, Z, cell_within)
    # rho_assign: founders' leave-one-out correlation with their own cell's D
    loo = []
    for k, ms in judged.items():
        M = np.array([Z[x.name] for x in ms])
        for i in range(len(ms)):
            others = np.delete(M, i, axis=0)
            D = np.nanmean(np.where(np.isfinite(others), others, np.nan), axis=0)
            c = corr_common(M[i], D)
            if np.isfinite(c):
                loo.append(c)
    rho_assign = float(np.quantile(loo, K.RHO_ASSIGN_Q)) if loo else None
    return {"cells": judged, "below": below, "cell_within": cell_within, "clusters": clusters, "joins": joins,
            "rho_assign": rho_assign, "loo": loo}


# ------------------------------------------------------------------------------------------------------- stage 1
def seen_series(mm: Member, runs: dict, hc: dict) -> list:
    """[(era, p0, p1, a)]: the member's alpha on each seen span, what restarted at the span's first session, with its
    frozen constants; the eras themselves when it has no hidden year."""
    out = []
    spans = mm.meta.get("seen_spans") or []
    for i, (lo, hi) in enumerate(spans):
        if mm.meta.get("hidden"):
            pl = runs.get(f"{mm.meta['pid']}_s{i}")
        else:
            e = 0 if lo < "2021" else 1
            pl = runs.get(f"{mm.meta['pid']}_e{e}k10")
        if pl is None or pl.get("status") != "ok":
            continue
        days = [_iso(x) for x in pl["days"]]
        e = 0 if days[0] < "2021" else 1
        he = hc["eras"][e]
        idx = [he.at.get(d) for d in days]
        if any(i is None for i in idx):
            continue
        p0, p1 = idx[0], idx[-1] + 1
        uni = list(pl["universe"])
        if uni != list(mm.syms):
            continue
        W = np.array([np.nan_to_num(np.array(pl["ws"].get(s, [0.0] * len(days)), dtype=float)) for s in uni])
        R = np.array([np.nan_to_num(np.array(pl["R"][s], dtype=float)) for s in uni])
        r = np.nan_to_num(np.array(pl["r"], dtype=float))
        sides = np.nan_to_num(np.array(pl["sides"], dtype=float))
        base = r - K.HAIRCUT * sides - (W * mm.mu[:, None]).sum(0)
        a = alpha_era(base, W, R - mm.mu[:, None], mm.wbar)
        out.append((e, p0, p1, a))
    return out


def stage1(ms: list[Member], sig_u: dict, runs: dict, hc: dict) -> dict:
    per = {}
    readable = 0
    for e, he in enumerate(hc["eras"]):
        num = np.zeros(he.T)
        rows = np.zeros(he.T)
        active = 0
        for mm in ms:
            ser = [s for s in seen_series(mm, runs, hc) if s[0] == e]
            if ser:
                active += 1
            for (_, p0, p1, a) in ser:
                num[p0:p1] += a / sig_u[mm.name]
                rows[p0:p1] += 1
        if active < K.M_MIN:
            per[f"e{e}"] = None
            continue
        readable = max(readable, active)
        cs = rows >= K.M_MIN
        D = num[cs] / active
        per[f"e{e}"] = newey_west_z(D, K.STAGE1_LAG)
    zs = [v for v in per.values() if v is not None]
    refuted = readable >= K.M_MIN and any(v <= K.STAGE1_Z for v in zs)
    return {"nw_z": per, "refuted": bool(refuted), "readable_members": readable}


# ------------------------------------------------------------------------------------------- a cluster through the rule
class Proxy:
    """A cluster as the engine's world and floor functions see it: its common span by era and its regime columns."""

    def __init__(self, span: dict, cells: np.ndarray, uid: str):
        self.span = span
        self.cells = cells
        self.uid = uid


def cluster_cells(cname: str, keys: list, judged: dict, hc: dict, joins: dict | None = None,
                  founders_sigma: dict | None = None) -> dict:
    """{e: [cell Unit]} with each cell's members present in era e (>= M_MIN), all on the cluster's common span of e,
    N1 rolled inside it; sigma_used from each cell's founders.
    joins: {member name: the cell session it joined at} (default: every member at 0, the founders' pattern);
    founders_sigma: {cell key: [the cell founders' sigma]} (default: the sigma of every member listed in judged[k],
    which at the pin are the founders; a joiner takes the founders')."""
    out = {}
    for e in (0, 1):
        present = [mm for k in keys for mm in judged[k] if mm.parts[e] is not None]
        if not present:
            continue
        P0 = max(mm.parts[e].p0 for mm in present)
        P1 = min(mm.parts[e].p1 for mm in present)
        units = []
        for k in keys:
            ms = [mm for mm in judged[k] if mm.parts[e] is not None]
            if len(ms) < K.M_MIN or P1 - P0 < K.L + 1:
                continue
            jn = (np.zeros(len(ms), dtype=np.int64) if joins is None
                  else np.array([int(joins.get(mm.name, 0)) for mm in ms], dtype=np.int64))
            fs = [x.sigma for x in judged[k]] if founders_sigma is None else list(founders_sigma[k])
            u = make_unit(f"{k[0]}/{k[1]}|e{e}", cname, k[1], ms, jn, "day0" if not jn.any() else "stagger", [],
                          roll_span=True, founders_sigma=fs)
            if P1 - P0 < K.L + u.l0 + 1:
                continue
            u.span = {e: (P0, P1)}
            units.append(u)
        if units:
            out[e] = units
    return out


def cluster_point(cells_by_era: dict, hc: dict, plants=(K.G9_SR, 1.0), g3: bool = True) -> dict:
    """{(e, key): (J, g)}: the cluster's window passes are its cells' best (max-T over cells). Every cell's window J
    starts at the same clock session; a cell whose M_MIN-th member joins later (l0 > 0) has fewer windows, and its
    starts are a prefix of the others', so the cluster's windows are their common prefix (DEVIATIONS D37: all joins
    0 at the pin, so nothing is cut there)."""
    out = {}
    for e, units in cells_by_era.items():
        parts = [point_all(u, [e], hc["vt"], g3=g3, plants=plants) for u in units]
        for key in parts[0]:
            n = min(len(p[key][0]) for p in parts)
            J = parts[0][key][0][:n]
            g = parts[0][key][1][:n].copy()
            for p in parts[1:]:
                assert np.array_equal(p[key][0][:n], J)
                g = np.maximum(g, p[key][1][:n])
            out[key] = (J, g)
    return out


def cluster_boot_one(cells_by_era: dict, ebs: dict, e: int, key: str, null: str, offset, g3: bool = False
                     ) -> np.ndarray:
    """g_b (B, nJ) of one era and variant: each resampled window's best over the cluster's cells (one resample of
    days for all), on the cells' common prefix of windows (as cluster_point)."""
    units = cells_by_era[e]
    n = min(u.span[e][1] - u.span[e][0] - K.L - u.l0 + 1 for u in units)
    g = None
    for u in units:
        gb = boot_g(u, e, null, offset, ebs[e], g3=g3, seed=seed_of(u.uid, key))
        if gb.shape[1] != n:
            gb = gb[:, :n]
        g = gb if g is None else np.maximum(g, gb)
    return g


def cluster_boot(cells_by_era: dict, ebs: dict, null: str, g3: bool = False) -> dict:
    """{(e, key): g_b (B, nJ)}: each resampled window's best over the cluster's cells (one resample of days for all)."""
    out = {}
    for e, units in cells_by_era.items():
        for key, n, o, w in variants(units[0], e, null, g3=g3):
            out[(e, key)] = cluster_boot_one(cells_by_era, ebs, e, key, n, o, g3=g3)
    return out


def shares_from(boots: dict, proxy: Proxy, null: str) -> dict:
    counts, tot = {}, {}
    for (e, key), gb in boots.items():
        w = next(ww for kk, n, o, ww in variants(proxy, e, null) if kk == key)
        counts[(e, key)] = share_curves(gb, w)
        tot[(e, key)] = w * gb.shape[1]
    out = {}
    for span in SPANS:
        eras = (0, 1) if span == "IN" else (int(span[1]),)
        ks = [k for k in counts if k[0] in eras]
        if ks:
            out[span] = sum(counts[k] for k in ks) / sum(tot[k] for k in ks)
    return out


def cluster_cols(keys: list) -> list:
    """The regime columns a cluster is judged in: the union of its cells' (4.4)."""
    return sorted({int(c) for k in keys for c in (list(range(6)) + ([6, 7, 8] if k[1] == "sectors" else [])
                                                 + ([9, 10, 11] if k[1] == "defensive" else []))})


def cluster_floor(cname: str, keys: list, judged: dict, hc: dict, cuts: np.ndarray, B: int, boot_seed: int,
                  cap: float, wall: float, joins: dict | None = None, founders_sigma: dict | None = None
                  ) -> dict | None:
    """THE FLOOR PIPELINE (contract 4.1), the floor block of p1run.house_units moved verbatim: the cluster's cells
    (cluster_cells), its eras' resampled regime cells (EraBoot seed [SEED_ROOT, 902, boot_seed, e]), its point worlds
    (cluster_point), per null its resamples (cluster_boot), share curves (shares_from) and variant weights, then
    p1engine.fit_floors at (cap, wall). None when the cluster has no era with a common span of at least L + 1
    sessions (ineligible).
    -> {"floor": fit_floors' {"floor", "c_own"}, "point", "boots", "shares", "weights", "span", "cols", "proxy",
        "ebs", "cells_by_era"}."""
    cbe = cluster_cells(cname, keys, judged, hc, joins=joins, founders_sigma=founders_sigma)
    if not cbe:
        return None
    span = {e: units[0].span[e] for e, units in cbe.items()}
    cols = cluster_cols(keys)
    proxy = Proxy(span, np.array(cols), f"H:{cname}")
    ebs = {e: EraBoot(hc["bases"][e], P0, P1, cuts, B, [K.SEED_ROOT, 902, boot_seed, e])
           for e, (P0, P1) in span.items()}
    point = cluster_point(cbe, hc)
    shares, boots, weights = {}, {}, {}
    for null in K.NULLS:
        boots[null] = cluster_boot(cbe, ebs, null)
        shares[null] = shares_from(boots[null], proxy, null)
        weights[null] = {(e, kk): w for e in span for kk, n, o, w in variants(proxy, e, null)}
    fl = fit_floors(proxy, point, hc["cells"], shares, cap=cap, wall=wall)
    return {"floor": fl, "point": point, "boots": boots, "shares": shares, "weights": weights, "span": span,
            "cols": cols, "proxy": proxy, "ebs": ebs, "cells_by_era": cbe}


# --------------------------------------------------------------------------------------- the rules both sides share
def caps_rule(u_point, u_bound, dropped=()) -> dict:
    """CAP_u, WALL_u and the report-only rule (PREREG 7.2; RECEIPT-CONTRACT 3.8, C3, C4; DEVIATIONS D31, D32), the
    same in fit_floors and G6 and in P1. REPORT-ONLY when U point >= 0.12 (CAP_u <= 0), when U bound >= 0.15
    (WALL_u <= 0, treated exactly like the PREREG's own CAP_u <= 0 rule), when any ticket was dropped (it could not
    be computed), or when either figure is not finite; then CAP 0.12, WALL 0.15 and u_worst 0. Otherwise CAP_u =
    0.12 - point, WALL_u = 0.15 - max(bound, point) and the worst-regime cap 0.15 - point (u_worst = point).
    -> {"cap", "wall", "u_worst", "report_only", "why": "u_point"|"u_bound"|"tickets_dropped"|None}."""
    up = float("nan") if u_point is None else float(u_point)
    ub = float("nan") if u_bound is None else float(u_bound)
    why = None
    if not math.isfinite(up) or up >= K.CAP:
        why = "u_point"
    elif not math.isfinite(ub) or max(ub, up) >= K.WALL:
        why = "u_bound"
    elif dropped:
        why = "tickets_dropped"
    if why is not None:
        return {"cap": K.CAP, "wall": K.WALL, "u_worst": 0.0, "report_only": True, "why": why}
    return {"cap": K.CAP - up, "wall": K.WALL - max(ub, up), "u_worst": up, "report_only": False, "why": None}


def k_used_for(c_own_k, minimum_k, c_G_k: int, margin_k: int) -> int | None:
    """THE BAR on the grid (PREREG 3.3; RECEIPT-CONTRACT 3.2): k_own = max(c_own, minimum) and c_used = max(c_G,
    k_own + margin). None (INELIGIBLE: no verdict) when c_own is None or k_own + margin > 500. A minimum of None
    leaves k_own = c_own; an ineligible matched floor is 501, so it makes the unit ineligible. This is
    p1gates.Pop.thresholds' and p1report's rule (the tests hold them equal)."""
    if c_own_k is None:
        return None
    k_own = int(c_own_k) if minimum_k is None else max(int(c_own_k), int(minimum_k))
    if k_own + int(margin_k) > K.K_MAX:
        return None
    return max(int(c_G_k), k_own + int(margin_k))


def event_word(code) -> bool:
    """An event reader by its frozen code (PREREG 1.2; DEVIATIONS D18): the word events or events_next anywhere,
    the House job's own scan (broader than a ctx-field match; it can only put more programs out)."""
    return bool(EVENT_WORD.search(str(code or "")))
