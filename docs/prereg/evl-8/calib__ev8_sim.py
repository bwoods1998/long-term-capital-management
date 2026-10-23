"""EV8: the done-speed synthesis simulator (copied unchanged from /dev/shm/speed-synth/synth_sim.py, wf_15782c13-759)
WITH PREREG-EVL-8's five seats added and PREREG-EVL-6's look schedule as drafted (mlist 6..60, alpha 0.016/0.004,
10 bp margin, 60-block horizon) in place of its c/S stand-in. Judge's edits are marked EV8. SYNTHETIC ONLY.

SESSIONS TO DONE, THE SLOTS-AND-CASH LENS (outcome-free Monte Carlo; no market data, no lane outcome).

Inputs are COUNTS and RULES only: the shadow supply per entry session of SPEED-FACTS.md (Oct 19-21), the frozen rules
(PREREG-EVL-1 s7/s8, PREREG-EVL-3 s2/s3, PREREG-EVL-4/-5 holds), release 1019f's code (book.py ROOM/A85, live.py
sizing, done.py), and STATED synthetic return scenarios. Every price is a draw from a stated lognormal; every return is
synthetic. E = $1,898.

Per session (s = 1 is Thu Oct 22): two crosses. At each cross the open lots that cross holds (lots sold AT that cross
still hold their cash there: A85) and the working buys at their limits share CASH = E - $50 reserve; Sized, then Probe
(round-robin, A85), then learning (table order, less A85's reservation for the other cross's Probe+ programs), each to
its room (max_open less lots held there, the ones being sold there included: A70 (4)), one name per program pick,
size rule per band, the 150-order line, the loss budget at each lot's open-risk weight (0.10 floor). Shadow events feed
the looks (PREREG-EVL-3: N = 60, 90, 135, ... with >= 8 blocks; session-block and issuer-block z-tests at alpha 0.018,
mean a > 0, mean raw r > 0; a held look with z <= -1.645 and mean a < 0 retires). A passed look as of close X moves the
band at X+1 09:40 ET (release 1019f's screen-open): close-entry programs trade Probe from X+1's close, open-entry ones
from X+2's open. Nightly band review: demotion (last 50 Probe+ events net < -$150, or last 100 mean r < 0) and Sized
(>= 150 in the stay, 80% session-block lower bound > 0). Done read at every 100th counted event (Probe+, after the
earliest promotion, sized_usd >= 0.8 x target): >= 300, >= 3 programs >= 50, P&L > 0, 95% (two-sided) issuer
lower bound > 0, lane realized P&L since the first promotion >= metered compute over the span; fills and item 4.8
assumed to pass (no captain step after the release). Pivot at 400 (upper bound < 0) and the $800 stop end a run.
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from multiprocessing import Pool

E = 1898.0
CASH = E - 50.0
LIMIT = 1.25
LOOKS = (60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250)
Z_ALPHA = 2.097          # one-sided alpha 0.018
Z_RETIRE = -1.645        # reversed one-sided p 0.05
SIGMA_E = 0.030          # per-event idiosyncratic sd, 1 session (PREREG-EVL-1's calibration model: 3%)
SIGMA_C = 0.004          # per-session residual common shock (abnormal), per program
SIGMA_DAY, SIGMA_NIGHT = 0.008, 0.005     # market: open->close, close->open
DRIFT_DAY, DRIFT_NIGHT = 0.0002, 0.0001
BETA = 1.1
FILL_GAP_SD = 0.02       # fill price vs prev close at the entry auction (sizing at 1.25 x prev close)
W = 0.105                # mean open-risk weight max(0.10, 1.65 sigma sqrt 1) (a few high-sigma names above 0.10)
SEASON_END = 18          # ~Nov 16: earnings rows fall to a fifth (PREREG-EVL-5's season note)

# id, entry: O (open->close), N (close->next open), C (close->next close); shadow supply/session (mean of Oct 20-21);
# earnings season; first block session (<= 0: Oct 19 = -2, Oct 20 = -1, Oct 21 = 0); past blocks' counts (Oct 19..21);
# f: the share of shadow events that become real candidate picks (live eligibility, stored before the decision,
# issuer held, the one-name-a-cross collision with earlier rows) BEFORE the price/size rule (a stated assumption).
PROGRAMS = [
    ("ERN-READ-O1", "O", 22.0, True, (1, 18, 26), 0.50),
    ("ERN-REACT-C1", "C", 7.5, True, (1, 11, 4), 0.45),
    ("8K-READ-O1", "O", 9.5, False, (10, 12, 7), 0.50),
    ("NEWS-READ-O1", "O", 126.0, False, (54, 88, 165), 0.40),
    ("ERN-REACT-ON", "N", 7.5, True, (1, 11, 4), 0.25),
    ("ERN-GUIDE-O1", "O", 10.5, True, (1, 10, 11), 0.15),
    ("INS-BUY-O1", "O", 1.3, False, (2, 1, 1), 0.70),
    ("NEWS-READ-ON", "N", 98.0, False, (54, 54, 142), 0.40),
    ("NEWS-REACT-ON", "N", 63.0, False, (29, 44, 83), 0.25),
    ("8K-REACT-ON", "N", 5.0, False, (0, 8, 2), 0.30),
    ("8K-READ-ON", "N", 5.5, False, (0, 9, 2), 0.30),
    ("NEWSPM-READ-ON", "N", 52.0, False, (0, 47, 58), 0.30),
    ("NEWS-NIGHT2-ON", "N", 12.0, False, None, 0.40),      # PREREG-EVL-5 central rates; blocks from Oct 22
    ("ERN-DROP-ON", "N", 6.0, True, None, 0.40),
    ("ERN-UNDER-ON", "N", 7.0, True, None, 0.30),
    # EV8: PREREG-EVL-8 (shadow rates: px8/px_supply central cells; META's null rate 1.0 a session, calib_meta fnull)
    ("PX-DROP-ON", "N", 27.0, False, None, 0.85),
    ("PX-SURGE-ON", "N", 14.0, False, None, 0.85),
    ("PX-GAP-O1", "O", 9.0, False, None, 0.80),
    ("META-ON", "N", 1.0, False, None, 0.50),
    ("META-O1", "O", 1.0, False, None, 0.50),
]
EVL8 = (15, 16, 17, 18, 19)
PXI = (15, 16, 17)
METAI = (18, 19)
LOOKS6 = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
LAMOVR = {}
#: EV8: the PX seats' residual session shock: px8's base block sd (98 bp at K 40, 27 events) less its idiosyncratic
#: part (about 67 bp) leaves about 0.7%; the synthesis's 0.4% is kept for every other program
SIGMA_C_OF = {15: 0.0072, 16: 0.0072, 17: 0.0072}
NP = len(PROGRAMS)
DEBUG = {}


def _dbg(key):
    DEBUG[key] = DEBUG.get(key, 0) + 1

BASE = dict(probe_share=0.035, probe_max=6, probe_one=0.05, probe_round="floor", learn_share=0.02, learn_max=8,
            learn_max_after=None, sized_share=0.10, sized_max=8, sized_on=True, order_line=150, a85=True,
            cancel=0.12, compute=5.4, price=(30.0, 1.1), room_total=600.0, window_old=0.0, horizon=120,
            demote_rule="last100", evl5_real_from=3, fast_promo=None, restart_at=None,
            screen="evl3", e6_smin=8, e6_smax=120, e6_c=0.10, e6_m=0.0010, e6_piss=0.10, sized_round="floor",
            evl8=False, evl8_real_from=6, px_a=(0.016, 0.004), px_m=0.0010, meta_versions=3, px_first=6,
            evl8_learn_max=4)
from statistics import NormalDist as _ND
_INV = _ND().inv_cdf



def poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 40:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def price(rng, med, sd):
    while True:
        p = med * math.exp(sd * rng.gauss(0, 1))
        if p >= 3.0:
            return p


def size(cfg, band, L):
    """(shares, sized_usd at the limit, at_size) for one buy at limit L (live.py `_event_size` and the variants)."""
    if band == "S":
        T, one, rule = cfg["sized_share"] * E, None, "floor"
    elif band == "P":
        T, one, rule = cfg["probe_share"] * E, cfg["probe_one"], cfg["probe_round"]
    else:
        T, one, rule = cfg["learn_share"] * E, 0.05, "floor"
    n = math.floor(T / L)
    cap = 0.05 * E if band == "P" else 0.10 * E
    if band == "S":
        rule = cfg.get("sized_round", "floor")
    if rule in ("atsize", "atsize_skip") and n * L < 0.8 * T:
        need = math.ceil(0.8 * T / L - 1e-12)
        if need * L <= cap:
            n = need
        elif rule == "atsize_skip" and band in ("P", "S"):
            return 0, 0.0, False     # SUP-1: skipped before it takes a slot (under_bar)
    if n < 1:
        if (one is not None and L > one * E) or L > 0.10 * E:
            return 0, 0.0, False
        n = 1
    usd = n * L
    return n, usd, usd >= 0.8 * T - 1e-9


class Lot:
    __slots__ = ("p", "band", "es", "kind", "res", "val", "r", "counted", "sold_s", "sold_x")

    def __init__(self, p, band, es, kind, res, val, r, counted):
        self.p, self.band, self.es, self.kind, self.res, self.val, self.r, self.counted = p, band, es, kind, res, val, r, counted


def run(args):
    cfg, scen, seed = args
    rng = random.Random(seed)
    H = cfg["horizon"]
    med, sd = cfg["price"]
    # --- edges (after cost): scen = (k programs with edge, mu, base mu for the rest, pool of eligible indices)
    k, mu_edge, mu_rest, pool = scen[:4]
    extra = scen[4] if len(scen) > 4 else {}
    mu = [mu_rest] * NP
    for i in rng.sample(pool, k) if k else []:
        mu[i] = mu_edge
    for i, v in extra.get("fixed", {}).items():          # EV8: a stated edge on a named program
        mu[int(i)] = v
    meta_target = extra.get("meta")                      # EV8: META's picks' true mean after learning (None: null)
    if meta_target is None and any(mu[i] > 0 for i in range(15)):
        # a promoted-or-not source with an edge is a META program expert: META learns to follow it (calib_meta)
        meta_target = 0.85 * max(mu[i] for i in range(15))
    meta_restarts = {i: 0 for i in METAI}
    e6k = [0] * NP
    e6ks = [0] * NP
    # --- shadow record per program: blocks (entry session, n, sum a, sum a^2, sum r)
    blocks = [[] for _ in range(NP)]
    for i, (pid, kind, lam, ern, past, f) in enumerate(PROGRAMS):
        if past and cfg.get("restart_at") is None:
            for j, n in enumerate(past):
                if n > 0:
                    s0 = j - 2
                    c = rng.gauss(0, SIGMA_C)
                    m = BETA * rng.gauss(0, SIGMA_DAY)
                    blocks[i].append(_block(rng, s0, n, mu[i], c, m))
    look_k = [0] * NP
    band = ["L"] * NP
    probe_from = [None] * NP      # (session, cross) the Probe band trades from
    promoted_s = [None] * NP      # earliest promotion (Done's)
    first_promo = None
    stay = [[] for _ in range(NP)]   # Probe+ events of the current stay: (r, pnl, session)
    picks_hist = [[] for _ in range(NP)]
    lots_open = []                # Lot objects
    counted = []                  # (sale key, p, r, pnl)
    pnl_by_s = [0.0] * (H + 3)
    cum_pnl = 0.0
    checkpoint = 100
    done_at = None
    stop = None
    demotions = sized_moves = 0
    true_dem = 0
    test_from = [cfg.get("restart_at") or -99] * NP   # EVL-6: the current test's record starts here
    stay_from = [None] * NP
    last_S = [0] * NP
    last_stS = [0] * NP
    last_read = [0] * NP
    under = probe_bought = 0
    cash_use = []
    open_risk_max = 0.0
    fail_items = {}
    LAMOVR.clear()
    for s in range(1, H + 1):
        if cfg["evl8"]:
            for i in METAI:   # EV8: META's learning curve (calib_meta's: WARM 10, picks' true mean ramps over ~40)
                ramp = min(1.0, max(0.0, (s - 10) / 40.0)) if meta_target is not None else 0.0
                mu[i] = mu_rest + ((meta_target - mu_rest) * ramp if meta_target is not None else 0.0)
                LAMOVR[i] = 1.0 + (11.0 * min(1.0, max(0.0, (s - 10) / 30.0)) if meta_target is not None else 0.0)
        m_night = BETA * rng.gauss(DRIFT_NIGHT, SIGMA_NIGHT)   # close s-1 -> open s
        m_day = BETA * rng.gauss(DRIFT_DAY, SIGMA_DAY)          # open s -> close s
        m_night_next = None
        orders_today = 0
        c_s = [rng.gauss(0, SIGMA_C_OF.get(j, SIGMA_C)) for j in range(NP)]
        # ======== OPEN CROSS =====================================================================================
        # exits at the open: N lots entered s-1 (sold here, still hold cash here)
        held_open = [l for l in lots_open if l.kind in ("N", "C")]   # N lots of s-1 and C lots of s-1
        selling_open = [l for l in lots_open if l.kind == "N"]
        orders_today += len(selling_open)
        orders_today += sum(1 for l in lots_open if l.kind == "C")   # C lots exit at today's close
        free = CASH - sum(l.val for l in held_open)
        given_back = sum(l.val for l in selling_open)
        room_budget = _budget_room(cfg, s, cum_pnl, pnl_by_s, lots_open)
        new_open, orders_today, free, room_budget, ub, pb = _cross(cfg, rng, s, "O", band, probe_from, mu, picks_hist,
                                                                   lots_open, free, given_back, room_budget,
                                                                   orders_today, med, sd, m_day, c_s)
        under += ub
        probe_bought += pb
        # settle the N lots at the open (their r was drawn at entry with the night move of s)
        for l in selling_open:
            _settle(l, s, 0, pnl_by_s, counted, stay)
            cum_pnl += l.val * l.r
        lots_open = [l for l in lots_open if l.kind != "N"] + new_open
        # ======== CLOSE CROSS ====================================================================================
        m_night_next = BETA * rng.gauss(DRIFT_NIGHT, SIGMA_NIGHT)  # close s -> open s+1 (used by N/C lots of s)
        held_close = [l for l in lots_open]       # O lots of s (sold here) and C lots of s-1 (sold here)
        selling_close = list(held_close)
        free = CASH - sum(l.val for l in held_close)
        given_back = sum(l.val for l in selling_close)
        room_budget = _budget_room(cfg, s, cum_pnl, pnl_by_s, lots_open)
        new_close, orders_today, free, room_budget, ub, pb = _cross(cfg, rng, s, "C", band, probe_from, mu, picks_hist,
                                                                    lots_open, free, given_back, room_budget,
                                                                    orders_today, med, sd, m_night_next, c_s)
        under += ub
        probe_bought += pb
        cash_use.append((sum(l.val for l in new_open) + sum(l.val for l in new_close)) / E)
        for l in selling_close:
            _settle(l, s, 1, pnl_by_s, counted, stay)
            cum_pnl += l.val * l.r
        lots_open = new_close
        open_risk_max = max(open_risk_max, W * sum(l.val for l in lots_open))
        # ======== SHADOW: today's blocks, then the looks as of today's close ======================================
        for i, (pid, kind, lam, ern, past, f) in enumerate(PROGRAMS):
            if i in EVL8 and not cfg["evl8"]:
                picks_hist[i].append(0)
                continue
            lam = LAMOVR.get(i, lam)
            lam_s = lam * (0.2 if (ern and s > SEASON_END) else 1.0) * rng.gammavariate(4.0, 0.25)
            n = poisson(rng, lam_s)
            if n > 0:
                c = c_s[i]
                mkt = m_day if kind == "O" else (m_night_next if kind == "N" else m_night_next + m_day)
                blocks[i].append(_block(rng, s, n, mu[i], c, mkt))
            picks_hist[i].append(n)
        if cfg["fast_promo"]:
            mb, from_s = cfg["fast_promo"]
            for i, (pid, kind, *_rest) in enumerate(PROGRAMS):
                if band[i] != "L" or promoted_s[i] is not None:
                    continue
                fresh = [b for b in blocks[i] if b[0] >= from_s and (b[0] <= s if kind == "O" else b[0] <= s - 1)]
                if len(fresh) >= mb and sum(b[1] for b in fresh) >= 60:
                    passed, _ = _look(fresh)
                    if passed:
                        band[i] = "P"
                        probe_from[i] = (s + 1, "C") if kind in ("N", "C") else (s + 2, "O")
                        stay[i] = []
                        promoted_s[i] = s + 1
                        if first_promo is None:
                            first_promo = s + 1
        if cfg["screen"] == "evl6":
            for i, (pid, kind, *_rest) in enumerate(PROGRAMS):
                if band[i] == "R":
                    continue
                settled_all = [b for b in blocks[i] if (b[0] <= s if kind == "O" else b[0] <= s - 1)]
                if band[i] == "L":
                    rec = [b for b in settled_all if b[0] >= test_from[i]]
                    S = len(rec)
                    if S == last_S[i]:
                        continue
                    last_S[i] = S
                    if i in EVL8 and not cfg["evl8"]:
                        continue
                    # EV8: PREREG-EVL-6 section 2 exactly: thresholds LOOKS6, minimums 6 blocks / 30 events, horizon 60
                    LK = tuple(x for x in LOOKS6 if x >= cfg["px_first"]) if i in PXI else LOOKS6
                    if not (e6k[i] < len(LK) and S >= LK[e6k[i]] and S >= 6 and sum(b[1] for b in rec) >= 30):
                        if S >= 60:
                            passed, retire = False, True              # exhausted at the 60th block
                        else:
                            continue
                    else:
                        while e6k[i] < len(LK) and S >= LK[e6k[i]]:
                            e6k[i] += 1
                        a1, a2 = cfg["px_a"] if i in PXI else (0.016, 0.004)
                        m0 = cfg["px_m"] if i in PXI else 0.0010
                        passed, retire = _look6x(rec, S, a1 if S <= 20 else a2, m0)
                        if not passed and S >= 60:
                            retire = True
                    if retire:
                        if i in METAI and meta_restarts[i] < cfg["meta_versions"] - 1:
                            meta_restarts[i] += 1                     # EV8: a successor version, a fresh record
                            test_from[i] = s + 1; last_S[i] = 0; e6k[i] = 0
                            continue
                        band[i] = "R"; probe_from[i] = None; continue
                    if passed:
                        band[i] = "P"
                        probe_from[i] = (s + 1, "C") if kind in ("N", "C") else (s + 2, "O")
                        stay[i] = []
                        stay_from[i] = s + 1
                        last_stS[i] = 0
                        e6ks[i] = 0
                        last_read[i] = 0
                        if promoted_s[i] is None:
                            promoted_s[i] = s + 1
                            if first_promo is None:
                                first_promo = s + 1
                else:
                    rec = [b for b in settled_all if b[0] >= stay_from[i]]
                    S = len(rec)
                    if S == last_stS[i]:
                        continue
                    last_stS[i] = S
                    LK = tuple(x for x in LOOKS6 if x >= cfg["px_first"]) if i in PXI else LOOKS6
                    if not (e6ks[i] < len(LK) and S >= LK[e6ks[i]] and S >= 6 and sum(b[1] for b in rec) >= 30):
                        continue
                    while e6ks[i] < len(LK) and S >= LK[e6ks[i]]:
                        e6ks[i] += 1
                    a1, a2 = cfg["px_a"] if i in PXI else (0.016, 0.004)
                    passed, retire = _look6x(rec, S, a1 if S <= 20 else a2, cfg["px_m"] if i in PXI else 0.0010)
                    if retire:      # the stay's lower tail: demotion, then a fresh test
                        band[i] = "L"; probe_from[i] = None; demotions += 1
                        true_dem += 1 if mu[i] > 0 else 0
                        test_from[i] = s + 1; last_S[i] = 0; e6k[i] = 0
                        continue
                    real = stay[i]
                    if band[i] == "P" and cfg["sized_on"] and passed and len(real) >= 30 and sum(e[1] for e in real) > 0:
                        band[i] = "S"; sized_moves += 1
        for i, (pid, kind, *_rest) in enumerate(PROGRAMS):
            if cfg["screen"] == "evl6":
                break
            if band[i] == "R" or look_k[i] >= len(LOOKS):
                continue
            settled = [b for b in blocks[i] if (b[0] <= s if kind == "O" else b[0] <= s - 1)
                       and (cfg.get("restart_at") is None or b[0] >= cfg["restart_at"])]
            n_set = sum(b[1] for b in settled)
            if len(settled) < 8 or n_set < LOOKS[look_k[i]]:
                continue
            while look_k[i] < len(LOOKS) and n_set >= LOOKS[look_k[i]]:
                look_k[i] += 1           # thresholds first reached at one close are one look
            passed, retire = _look(settled)
            if retire:
                band[i] = "R"
                probe_from[i] = None
                continue
            if passed and band[i] == "L":
                band[i] = "P"
                probe_from[i] = (s + 1, "C") if kind in ("N", "C") else (s + 2, "O")
                stay[i] = []
                if promoted_s[i] is None:
                    promoted_s[i] = s + 1
                    if first_promo is None:
                        first_promo = s + 1
        # ======== NIGHTLY BAND REVIEW (demotion, Sized) ===========================================================
        for i in range(NP):
            if band[i] not in ("P", "S") or not stay[i]:
                continue
            st = stay[i]
            last50 = st[-50:]
            last100 = st[-100:]
            if cfg["screen"] == "evl6":
                demote = sum(e[1] for e in last50) < -150.0 if len(st) >= 1 else False
                k100 = len(st) // 100
                if not demote and k100 > last_read[i]:
                    last_read[i] = k100
                    demote = sum(e[0] for e in st[:100 * k100]) < 0
                if demote:
                    band[i] = "L"; probe_from[i] = None; demotions += 1
                    true_dem += 1 if mu[i] > 0 else 0
                    test_from[i] = s + 1; last_S[i] = 0; e6k[i] = 0
                continue
            if cfg["demote_rule"] == "test":
                # (judges-lens coordination, not this lens's change) a sequential test like retirement's: the stay's
                # session means of r, one-sided z <= -1.645 with >= 8 blocks, or the $150 line over the last 50
                by = {}
                for e in st:
                    by.setdefault(e[2], []).append(e[0])
                means = [statistics.fmean(v) for v in by.values()]
                z = sum(means) / math.sqrt(sum(m * m for m in means)) if len(means) >= 8 else 0.0
                demote = sum(e[1] for e in last50) < -150.0 or z <= -1.645
            else:
                demote = sum(e[1] for e in last50) < -150.0 or (len(last100) == 100 and sum(e[0] for e in last100) < 0)
            if demote:
                band[i] = "L"
                probe_from[i] = None
                demotions += 1
                true_dem += 1 if mu[i] > 0 else 0
                continue
            if band[i] == "P" and cfg["sized_on"] and len(st) >= 150 and _sized_ok(st):
                band[i] = "S"
                sized_moves += 1
        # ======== DONE READER ======================================================================================
        counted.sort(key=lambda e: e[0])
        while len(counted) >= checkpoint and done_at is None and stop is None:
            first = counted[:checkpoint]
            if checkpoint >= 300:
                ok, why = _done(first, cfg, s, first_promo, pnl_by_s)
                if ok:
                    done_at = s
                else:
                    for w in why:
                        fail_items[w] = fail_items.get(w, 0) + 1
                if checkpoint == 400 and not ok:
                    rs = [e[2] for e in first]
                    mean = statistics.fmean(rs)
                    se = statistics.pstdev(rs) / math.sqrt(len(rs))
                    if mean + 1.96 * se < 0:
                        stop = ("pivot", s)
            checkpoint += 100
        if done_at is not None or stop is not None:
            break
        if cfg["room_total"] + cum_pnl <= 0:
            stop = ("loss800", s)
            break
    n_probe_programs = sum(1 for x in promoted_s if x is not None)
    false_promo = sum(1 for j in range(NP) if promoted_s[j] is not None and mu[j] <= 0)
    evl8_promo = sum(1 for j in EVL8 if promoted_s[j] is not None)
    evl8_counted = sum(1 for e in counted if e[1] in EVL8)
    true_promo = sum(1 for j in range(NP) if promoted_s[j] is not None and mu[j] > 0)
    return {"evl8_promo": evl8_promo, "evl8_counted": evl8_counted, "meta_restarts": sum(meta_restarts.values()),
            "true_dem": true_dem, "false_promo": false_promo, "true_promo": true_promo,
            "done": done_at, "stop": stop, "first_promo": first_promo, "promoted": n_probe_programs,
            "counted": len(counted), "demotions": demotions, "sized": sized_moves,
            "under_share": under / max(1, probe_bought), "fail": fail_items,
            "cash_use": statistics.fmean(cash_use) if cash_use else 0.0, "open_risk_max": open_risk_max,
            "rate": _rate(counted, first_promo, done_at or H), "pnl": cum_pnl,
            "pnl_since_promo": sum(pnl_by_s[first_promo:s + 1]) if first_promo else 0.0,
            "compute_since_promo": cfg["compute"] * (s - first_promo + 1) if first_promo else 0.0,
            "worst20": _worst_window(pnl_by_s, s), "worst1": min(pnl_by_s[1:s + 1]) if s >= 1 else 0.0}


def _rate(counted, first, last):
    if first is None or last <= first:
        return 0.0
    return len(counted) / max(1, last - first + 1)


def _worst_window(pnl_by_s, s):
    best = 0.0
    for a in range(1, max(2, s - 18)):
        best = min(best, sum(pnl_by_s[a:a + 20]))
    return best


def _block(rng, s, n, mu, c, mkt):
    sum_a = n * (mu + c) + SIGMA_E * math.sqrt(n) * rng.gauss(0, 1)
    sum_a2 = n * (SIGMA_E ** 2 + (mu + c) ** 2)
    return (s, n, sum_a, sum_a2, sum_a + n * mkt)


def _look(settled):
    vals = [b[2] / b[1] for b in settled]
    z_sess = sum(vals) / math.sqrt(sum(v * v for v in vals))
    n = sum(b[1] for b in settled)
    sa = sum(b[2] for b in settled)
    z_iss = sa / math.sqrt(sum(b[3] for b in settled))
    mean_a = sa / n
    mean_r = sum(b[4] for b in settled) / n
    passed = z_sess >= Z_ALPHA and z_iss >= Z_ALPHA and mean_a > 0 and mean_r > 0
    retire = mean_a < 0 and z_sess <= Z_RETIRE
    return passed, retire


def _look6(rec, S, cfg):
    """EVL-6 stand-in (FP-honest per the pipeline check: every block S_min..S_max, alpha c/S, margin m, issuer p <= 0.10)."""
    vals = [b[2] / b[1] for b in rec]
    alpha = cfg["e6_c"] / S
    zc = _INV(1.0 - alpha)
    x = [v - cfg["e6_m"] for v in vals]
    den = math.sqrt(sum(v * v for v in x)) or 1e-12
    z = sum(x) / den
    den0 = math.sqrt(sum(v * v for v in vals)) or 1e-12
    z_low = -sum(vals) / den0
    n = sum(b[1] for b in rec)
    sa = sum(b[2] for b in rec)
    z_iss = sa / math.sqrt(sum(b[3] for b in rec))
    mean_a = sa / n
    mean_r = sum(b[4] for b in rec) / n
    retire = mean_a < 0 and z_low >= zc
    passed = (not retire) and z >= zc and z_iss >= _INV(1.0 - cfg["e6_piss"]) and mean_a > 0 and mean_r > 0
    return passed, retire


def _look6x(rec, S, alpha, m0):
    """EV8: PREREG-EVL-6 sections 1.3-1.4 by the normal approximation of the sign-flip p (block z), retirement first."""
    vals = [b[2] / b[1] for b in rec]
    zc = _INV(1.0 - alpha)
    x = [v - m0 for v in vals]
    z = sum(x) / (math.sqrt(sum(v * v for v in x)) or 1e-12)
    z_low = -sum(vals) / (math.sqrt(sum(v * v for v in vals)) or 1e-12)
    n = sum(b[1] for b in rec)
    sa = sum(b[2] for b in rec)
    z_iss = sa / math.sqrt(sum(b[3] for b in rec))
    mean_a = sa / n
    mean_r = sum(b[4] for b in rec) / n
    retire = mean_a < 0 and z_low >= zc
    passed = (not retire) and z >= zc and z_iss >= _INV(0.90) and mean_a > 0 and mean_r > 0
    return passed, retire


def _sized_ok(st):
    by = {}
    for r, pnl, s in st:
        by.setdefault(s, []).append(r)
    means = [statistics.fmean(v) for v in by.values()]
    if len(means) < 3:
        return False
    m = statistics.fmean(means)
    se = statistics.pstdev(means) / math.sqrt(len(means))
    return m - 0.8416 * se > 0


def _budget_room(cfg, s, cum_pnl, pnl_by_s, lots):
    open_risk = W * sum(l.val for l in lots)
    total = cfg["room_total"] + cum_pnl - open_risk
    old = cfg["window_old"] * max(0.0, 1.0 - (s - 1) / 20.0)
    window = 400.0 - old + sum(pnl_by_s[max(1, s - 19):s]) - open_risk
    return min(total, window)


def _cross(cfg, rng, s, cross, band, probe_from, mu, picks_hist, lots_open, free, given_back, room_budget,
           orders_today, med, sd, mkt, c_s):
    """One auction's buys. Returns (new lots, orders, free cash, budget room, under-size Probe buys, Probe buys)."""
    kinds = ("O",) if cross == "O" else ("N", "C")
    live_band = []
    for i, (pid, kind, *_r) in enumerate(PROGRAMS):
        if kind not in kinds or band[i] == "R":
            continue
        b = band[i]
        if b in ("P", "S"):
            pf = probe_from[i]
            if pf is not None and (s, 0 if cross == "O" else 1) < (pf[0], 0 if pf[1] == "O" else 1):
                b = "L"         # promoted, but the band trades from a later decision
        if i in EVL8 and (not cfg["evl8"] or s < cfg["evl8_real_from"]):
            continue        # EV8: PREREG-EVL-8's real money starts with its carrying release
        if PROGRAMS[i][4] is None and i not in EVL8 and s < cfg["evl5_real_from"]:
            continue        # PREREG-EVL-5's real money starts with its carrying release
        live_band.append((i, b))
    # rooms: max_open less lots of the program held at this cross (C lots of s-1 being sold here count: A70 (4))
    held = {}
    for l in lots_open:
        if (cross == "C" and l.kind == "C") or (cross == "O" and l.kind == "C"):
            held[l.p] = held.get(l.p, 0) + 1

    def max_open(b, after_promo):
        if b == "S":
            return cfg["sized_max"]
        if b == "P":
            return cfg["probe_max"]
        if cfg["learn_max_after"] is not None and after_promo:
            return cfg["learn_max_after"]
        return cfg["learn_max"]
    any_promo = any(x in ("P", "S") for x in band)
    rooms = {i: max(0, (min(max_open(b, any_promo), cfg["evl8_learn_max"]) if (b == "L" and i in EVL8)
                        else max_open(b, any_promo)) - held.get(i, 0)) for i, b in live_band}
    # A85: the other cross's Probe+ programs' need (for learning buys only)
    reserve = 0.0
    if cfg["a85"]:
        other = ("N", "C") if cross == "O" else ("O",)
        for i, (pid, kind, *_r) in enumerate(PROGRAMS):
            if kind in other and band[i] in ("P", "S") and probe_from[i] is not None:
                hist = picks_hist[i][-5:]
                med_picks = statistics.median([h * PROGRAMS[i][5] for h in hist]) if hist else 99
                share = cfg["probe_share"] if band[i] == "P" else cfg["sized_share"]
                n = min(max_open(band[i], True), med_picks)
                reserve += n * share * E
        reserve = max(0.0, reserve - given_back)
    # candidates per program: today's real picks
    cand = {}
    for i, b in live_band:
        lam = LAMOVR.get(i, PROGRAMS[i][2]) * (0.2 if (PROGRAMS[i][3] and s > SEASON_END) else 1.0)
        cand[i] = poisson(rng, lam * PROGRAMS[i][5])
    order = sorted(live_band, key=lambda t: ({"S": 0, "P": 1, "L": 2}[t[1]], t[0]))
    new = []
    under = probe_b = 0
    line = cfg["order_line"]

    def try_buy(i, b, limit_cash):
        nonlocal free, room_budget, orders_today, under, probe_b
        while cand[i] > 0:
            cand[i] -= 1
            P = price(rng, med, sd)
            L = math.floor(P * LIMIT * 100) / 100
            n, usd, at = size(cfg, b, L)
            if n == 0:
                continue                    # size before slots (A70 (2)): takes no slot
            need_orders = 2 if cross == "O" else 1
            if orders_today + need_orders > line:
                _dbg((b, "line"))
                return False
            if usd > limit_cash():
                _dbg((b, "cash"))
                return False                # cash refuses this pick; it keeps no slot (simplified)
            if W * usd > room_budget:
                _dbg((b, "budget"))
                return False
            orders_today += need_orders
            if rng.random() < cfg["cancel"]:
                orders_today += 1           # the venue cancelled and the re-send failed too
                _dbg((b, "cancel"))
                return True                 # the slot was tried; no lot
            _dbg((b, "bought"))
            fill = usd / LIMIT * (1.0 + FILL_GAP_SD * rng.gauss(0, 1))
            free -= usd
            room_budget -= W * usd
            kind = PROGRAMS[i][1]
            c_r = mu[i] + c_s[i] + mkt + SIGMA_E * (1.2 if kind == "C" else 1.0) * rng.gauss(0, 1)
            if kind == "C":
                c_r += BETA * rng.gauss(DRIFT_DAY, SIGMA_DAY)     # the next session's day move (approximation)
            counted_flag = b in ("P", "S") and at
            if b in ("P", "S"):
                probe_b += 1
                if not at:
                    under += 1
            new.append(Lot(i, b, s, kind, usd, fill, c_r, counted_flag))
            return True
        return False

    def cash_probe():
        return free

    def cash_learn():
        return free - reserve
    # Sized, then Probe round-robin
    probe_tier = [(i, b) for i, b in order if b in ("S", "P")]
    for tier in ("S", "P"):
        group = [i for i, b in probe_tier if b == tier]
        given = {i: 0 for i in group}
        live = [i for i in group if rooms[i] > 0]
        while live:
            nxt = []
            for i in live:
                ok = try_buy(i, tier, cash_probe)
                if ok:
                    given[i] += 1
                if ok and given[i] < rooms[i] and cand[i] > 0:
                    nxt.append(i)
            live = nxt
    for i, b in order:
        if b != "L":
            continue
        got = 0
        while got < rooms[i] and cand[i] > 0:
            if not try_buy(i, "L", cash_learn):
                break
            got += 1
    return new, orders_today, free, room_budget, under, probe_b


def _settle(l, s, x, pnl_by_s, counted, stay):
    pnl = l.val * l.r
    pnl_by_s[s] += pnl
    if l.band in ("P", "S"):
        stay[l.p].append((l.r, pnl, l.es))
        if l.counted:
            counted.append(((s, x, l.p, id(l)), l.p, l.r, pnl))


def _done(first, cfg, s, first_promo, pnl_by_s):
    why = []
    by = {}
    for e in first:
        by[e[1]] = by.get(e[1], 0) + 1
    if sum(1 for v in by.values() if v >= 50) < 3:
        why.append("programs")
    if sum(e[3] for e in first) <= 0:
        why.append("pnl")
    rs = [e[2] for e in first]
    if statistics.fmean(rs) - 1.96 * statistics.pstdev(rs) / math.sqrt(len(rs)) <= 0:
        why.append("bound")
    span = s - first_promo + 1
    if sum(pnl_by_s[first_promo:s + 1]) < cfg["compute"] * span:
        why.append("profit_vs_compute")
    return (not why), why


def batch(cfg, scen, runs, seed0, workers=4):
    args = [(cfg, scen, seed0 + j) for j in range(runs)]
    with Pool(workers) as pool:
        out = pool.map(run, args, chunksize=max(1, runs // (workers * 4)))
    return out


def summary(out, H):
    T = [o["done"] if o["done"] is not None else None for o in out]
    done = [t for t in T if t is not None]
    capped = [t if t is not None else H + 1 for t in T]
    fails = {}
    for o in out:
        for k, v in o["fail"].items():
            fails[k] = fails.get(k, 0) + v
    fp = [o["first_promo"] for o in out if o["first_promo"] is not None]
    return {
        "P_done_20": sum(1 for t in done if t <= 20) / len(out),
        "P_done_40": sum(1 for t in done if t <= 40) / len(out),
        "P_done_60": sum(1 for t in done if t <= 60) / len(out),
        "P_done_H": len(done) / len(out),
        "median_T_capped": statistics.median(capped),
        "mean_T_capped": statistics.fmean(capped),
        "median_T_done": statistics.median(done) if done else None,
        "median_promo_to_done": statistics.median([o["done"] - o["first_promo"] for o in out if o["done"]]) if done else None,
        "first_promo_median": statistics.median(fp) if fp else None,
        "promoted_mean": statistics.fmean(o["promoted"] for o in out),
        "counted_rate_mean": statistics.fmean(o["rate"] for o in out),
        "demotions_mean": statistics.fmean(o["demotions"] for o in out),
        "true_dem_mean": statistics.fmean(o["true_dem"] for o in out),
        "false_promo_mean": statistics.fmean(o["false_promo"] for o in out),
        "evl8_promo_mean": statistics.fmean(o["evl8_promo"] for o in out),
        "evl8_counted_mean": statistics.fmean(o["evl8_counted"] for o in out),
        "pnl_mean": statistics.fmean(o["pnl"] for o in out),
        "pnl_p05": sorted(o["pnl"] for o in out)[int(0.05 * len(out))],
        "true_promo_mean": statistics.fmean(o["true_promo"] for o in out),
        "P_false_done": sum(1 for o in out if o["done"] and o["true_promo"] < 3) / len(out),
        "sized_mean": statistics.fmean(o["sized"] for o in out),
        "under_share": statistics.fmean(o["under_share"] for o in out),
        "cash_use_O": statistics.fmean(o["cash_use"] for o in out),
        "open_risk_max_p95": sorted(o["open_risk_max"] for o in out)[int(0.95 * len(out)) - 1],
        "worst20_p5": sorted(o["worst20"] for o in out)[int(0.05 * len(out))],
        "worst1_p5": sorted(o["worst1"] for o in out)[int(0.05 * len(out))],
        "pnl_minus_compute_mean": statistics.fmean(o["pnl_since_promo"] - o["compute_since_promo"] for o in out),
        "stops": {k: sum(1 for o in out if o["stop"] and o["stop"][0] == k) / len(out) for k in ("pivot", "loss800")},
        "fail_counts_per_run": {k: v / len(out) for k, v in sorted(fails.items())},
    }


ALL = list(range(NP))
HI = [0, 2, 3, 5, 7, 8, 11, 12]   # shadow supply >= 9 a session (SPEED-FACTS; EVL-5 central rate for NIGHT2)
SCENARIOS = {
    "Z0 (no edge: every program 0 after cost)": (0, 0.0, 0.0, ALL),
    "Z15 (no edge: 0 before cost, -15 bp after)": (0, 0.0, -0.0015, ALL),
    "E3 (3 programs +40 bp after cost, rest -15 bp)": (3, 0.0040, -0.0015, ALL),
    "E5 (5 programs +25 bp after cost, rest -15 bp)": (5, 0.0025, -0.0015, ALL),
    "E3hi (3 of the 8 supply>=9 programs +40 bp, rest -15)": (3, 0.0040, -0.0015, HI),
    "E5hi (5 of the 8 supply>=9 programs +25 bp, rest -15)": (5, 0.0025, -0.0015, HI),
    "E3news (the 3 news programs +40 bp, rest -15)": (3, 0.0040, -0.0015, [3, 7, 8]),
}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "base"
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    cfg = dict(BASE)
    for kv in sys.argv[3:]:
        k, v = kv.split("=", 1)
        cfg[k] = json.loads(v)
    res = {}
    for name, scen in SCENARIOS.items():
        out = batch(cfg, scen, runs, 1000)
        res[name] = summary(out, cfg["horizon"])
        print(which, name, json.dumps(res[name]), flush=True)
    with open(f"/dev/shm/speed-synth/out_{which}.json", "w") as fh:
        json.dump({"cfg": cfg, "runs": runs, "res": res}, fh, indent=1)
