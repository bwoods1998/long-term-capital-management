"""POOL1 calibration: ONE UNIT THROUGH THE RULE (3.3, 4.4): its point worlds under every null and variant, its own
floors (POOLED and R-REG, each null's raised until the bootstrap bound is under the wall, c_own the largest of the
three nulls'), and its share of the G1/G3 bootstrap accumulators.

VARIANTS (strings): "N0", "N0R", "N1@<offset>", "RAW", and with the prefix "G3" the same under G3's worse fills;
"P<sr>|<null>[@o]" a planted member Sharpe (power, point only).
SPANS: "e0" (2016-19), "e1" (2022-24), "IN" (both). A floor fitted on one era judges the other's windows
(cross-fitted); a floor fitted on IN judges OUT and is the House unit's floor at the pin.
WORLD WEIGHTS: a window is one world; under N1 each of its era's allowed offsets is a world of weight 1/n_offsets
(DEVIATIONS D4)."""
from __future__ import annotations

import numpy as np

from p1const import B_BOOT, CAP, CG_HI, CG_LO, FLOOR_DEFS, K_MAX, MARGINS, NULLS, RULES, WALL
from p1members import offsets_for
from p1stat import curve, grid_index, rreg_floor, smallest_k
from p1units import EraBoot, Unit, boot_g, bound_curve, point_tby, share_curves, starts_of

SPANS = ("e0", "e1", "IN")
NCG = CG_HI - CG_LO + 1


def era_offsets(u: Unit, e: int) -> tuple[int, ...]:
    P0, P1 = u.span[e]
    return offsets_for(P1 - P0)


def variants(u: Unit, e: int, null: str, g3: bool = False) -> list[tuple[str, str, int | None, float]]:
    """[(key, null, offset, weight)] of one null on era e."""
    pre = "G3" if g3 else ""
    if null == "N1":
        offs = era_offsets(u, e)
        return [(f"{pre}N1@{o}", "N1", o, 1.0 / len(offs)) for o in offs]
    return [(f"{pre}{null}", null, None, 1.0)]


def point_all(u: Unit, eras: list[int], vt: dict, *, nulls=NULLS, g3: bool = True, raw: bool = False,
              plants=(), means: dict | None = None, members_mask=None) -> dict:
    """{(e, key): (J, g (nJ, 3) int16)} for every null's variants (and G3's, RAW and planted ones when asked)."""
    out = {}
    for e in eras:
        if e not in u.span:
            continue
        todo = []
        for null in nulls:
            todo += [(k, n, o, False, 0.0) for k, n, o, _ in variants(u, e, null)]
            if g3:
                todo += [(k, n, o, True, 0.0) for k, n, o, _ in variants(u, e, null, g3=True)]
            for sr in plants:
                todo += [(f"P{sr}|{k}", n, o, False, sr) for k, n, o, _ in variants(u, e, null)]
        if raw:
            todo.append(("RAW", "RAW", None, False, 0.0))
        for key, null, off, gg, sr in todo:
            J, T = point_tby(u, e, null, off, vt[e], g3=gg, plant_sr=sr, means=means, members_mask=members_mask)
            out[(e, key)] = (J, grid_index(T))
    return out


def worlds(u: Unit, point: dict, span: str, null: str, cells: dict, prefix: str = "") -> tuple:
    """(g by look 120, weights, cells (n, 12)) of the span's worlds under a null."""
    eras = (0, 1) if span == "IN" else (int(span[1]),)
    gs, ws, cs = [], [], []
    for e in eras:
        if e not in u.span:
            continue
        for key, n, o, w in variants(u, e, null):
            J, g = point[(e, prefix + key)]
            gs.append(g[:, -1])
            ws.append(np.full(len(J), w))
            cs.append(cells[e][J])
    if not gs:
        return np.zeros(0, dtype=np.int16), np.zeros(0), np.zeros((0, 12), dtype=bool)
    return np.concatenate(gs), np.concatenate(ws), np.concatenate(cs)


def point_share(g: np.ndarray, w: np.ndarray) -> np.ndarray:
    tot = w.sum()
    return curve(g, w) / tot if tot > 0 else np.zeros(K_MAX + 1)


def base_floor(g, w, cl, ucols, fd: str, cap: float) -> int | None:
    if len(g) == 0:
        return None
    if fd == "POOLED":
        return smallest_k(point_share(g, w), cap)
    return rreg_floor(g, w, cl[:, ucols], cap)


def raise_to_wall(k: int | None, bound: np.ndarray, wall: float) -> int | None:
    if k is None:
        return None
    ok = np.where(bound[k:] <= wall + 1e-12)[0]
    return int(k + ok[0]) if ok.size else None


def boot_shares(u: Unit, eb: dict, null: str, means=None, g3: bool = False) -> dict:
    """{span: (B, 501) bootstrap share curves} and {(e, key): g_b (B, nJ)} of one null."""
    counts = {}
    tot = {}
    gb_all = {}
    for e in sorted(u.span):
        for key, n, o, w in variants(u, e, null, g3=g3):
            gb = boot_g(u, e, n, o, eb[e], g3=g3, means=means)
            gb_all[(e, key)] = gb
            counts[(e, key)] = share_curves(gb, w)
            tot[(e, key)] = w * gb.shape[1]
    out = {}
    for span in SPANS:
        eras = (0, 1) if span == "IN" else (int(span[1]),)
        keys = [k for k in counts if k[0] in eras]
        if not keys:
            continue
        num = sum(counts[k] for k in keys)
        den = sum(tot[k] for k in keys)
        out[span] = num / den
    return out, gb_all


def fit_floors(u: Unit, point: dict, cells: dict, shares: dict, cap: float = CAP, wall: float = WALL) -> dict:
    """{"floor": {null: {fd: {span: k|None}}}, "c_own": {fd: {span: k|None}}} at (cap, wall)."""
    fl = {null: {fd: {} for fd in FLOOR_DEFS} for null in NULLS}
    for null in NULLS:
        for span in SPANS:
            if span not in shares.get(null, {}):
                for fd in FLOOR_DEFS:
                    fl[null][fd][span] = None
                continue
            g, w, cl = worlds(u, point, span, null, cells)
            bound = bound_curve(shares[null][span], point_share(g, w))
            for fd in FLOOR_DEFS:
                fl[null][fd][span] = raise_to_wall(base_floor(g, w, cl, u.cells, fd, cap), bound, wall)
    own = {fd: {} for fd in FLOOR_DEFS}
    for fd in FLOOR_DEFS:
        for span in SPANS:
            ks = [fl[null][fd].get(span) for null in NULLS]
            own[fd][span] = None if any(k is None for k in ks) else max(ks)
    return {"floor": fl, "c_own": own}


def k_rule(c_own: dict, span: str, minimum: dict | None = None) -> list:
    """The bar's lower part per rule (k_own + margin, or None: ineligible), from the span's c_own."""
    out = []
    for fd, mg in RULES:
        k = c_own[fd].get(span)
        if k is not None and minimum is not None and minimum.get(fd, {}).get(span) is not None:
            k = max(k, minimum[fd][span])
        out.append(None if k is None or k + mg > K_MAX else k + mg)
    return out


def accumulate(acc: np.ndarray, cnt: np.ndarray, gb: np.ndarray, cells_b: np.ndarray, ucols, w: float,
               krules: list) -> None:
    """Add one variant-era's bootstrap windows to a family's G1/G3 accumulators: acc[b, cell, rule, cG] += w x #
    (windows in the cell passing at max(cG, k_rule)); cnt[b, cell] += w x # windows in the cell."""
    B, nJ = gb.shape
    gi = gb.astype(np.int64) + 1                                 # 0: none valid
    for c in ucols:
        mask = cells_b[:, :nJ, c]
        flat = (np.arange(B)[:, None] * 502 + np.where(mask, gi, 0)).ravel()
        h = np.bincount(flat, weights=np.where(mask, 1.0, 0.0).ravel(), minlength=B * 502).reshape(B, 502)
        cnt[:, c] += w * mask.sum(axis=1)
        S = h[:, ::-1].cumsum(axis=1)[:, ::-1]                   # S[b, j] = # with gi >= j, i.e. g >= j - 1
        S[:, 0] -= h[:, 0]                                       # never count "none valid" as a pass
        for r, k in enumerate(krules):
            if k is None:
                continue
            ks = np.maximum(np.arange(CG_LO, CG_HI + 1), k)
            acc[:, c, r, :] += w * S[:, ks + 1]


def process_unit(u: Unit, eras: list[int], vt: dict, cells: dict, eb: dict, *, accs: dict | None = None,
                 cap: float = CAP, wall: float = WALL, g3: bool = True, raw: bool = False, plants=(),
                 minimum: dict | None = None, keep_boot: bool = False) -> dict:
    """The unit through the rule: point worlds, floors, and (stand-ins and House units) the accumulators."""
    point = point_all(u, eras, vt, g3=g3, raw=raw, plants=plants)
    shares = {}
    boots = {}
    for null in NULLS:
        shares[null], boots[null] = boot_shares(u, eb, null)
    res = fit_floors(u, point, cells, shares, cap, wall)
    res["point"] = point
    if keep_boot:
        res["shares"] = shares
        res["boots"] = boots
    if accs is not None:
        for gname in (["N0", "N0R", "N1"] + (["G3N0", "G3N0R", "G3N1"] if g3 else [])):
            null = gname.replace("G3", "")
            isg3 = gname.startswith("G3")
            acc, cnt = accs[gname]
            for e in sorted(u.span):
                other = "e1" if e == 0 else "e0"
                kr = k_rule(res["c_own"], other, minimum)
                for key, n, o, w in variants(u, e, null, g3=isg3):
                    gb = boots[null][(e, key)] if not isg3 else boot_g(u, e, n, o, eb[e], g3=True)
                    accumulate(acc, cnt, gb, eb[e].cells, u.cells, w, kr)
    return res


def new_accs(B: int = B_BOOT, g3: bool = True) -> dict:
    names = ["N0", "N0R", "N1"] + (["G3N0", "G3N0R", "G3N1"] if g3 else [])
    return {n: (np.zeros((B, 12, len(RULES), NCG), dtype=np.float32), np.zeros((B, 12), dtype=np.float64))
            for n in names}
