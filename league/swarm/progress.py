"""Read-only public promotion checklists: counts and verdicts, never research metrics or fitted inputs.

The publisher calls this after its existing account read. A single read transaction binds family, version,
lineage, completed looks and forward rows; no SwarmStore is opened, migrated or written. Existing live bands
keep their recorded holdout authority across a Gym image change. Gym validation must match the current image
and engine, and an old lineage-adjusted verdict cannot claim a current deflated-Sharpe pass.
"""

from __future__ import annotations

import datetime as dt
from contextlib import closing
import math
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from ..live import money as M
from . import DB_NAME, evidence, settings
from .gate import run_sha
from .store import loads

TARGET_KEYS = {
    "candidate": ("validation_run", "validation_trades", "validation_days", "validation_mean", "validation_t",
                  "validation_dsr", "validation_quarters", "validation_stress", "review", "audit", "holdout"),
    "probe": ("execution_ready", "holdout", "real_structure", "credit_equity", "risk_fit", "forward_nonnegative"),
    "sized": ("execution_ready", "holdout", "real_structure", "credit_equity", "risk_fit", "forward_nonnegative",
              "forward_trades", "forward_mean", "forward_confidence", "real_trades", "probe_sessions", "real_record"),
    "maintain": ("execution_ready", "holdout", "real_structure", "credit_equity", "risk_fit", "forward_nonnegative",
                 "forward_trades", "forward_mean", "forward_confidence", "real_record"),
}
COUNT_BOUNDS = {"validation_trades": (100, 100), "validation_days": (60, 60), "validation_quarters": (3, 3),
                "forward_trades": (20, 1000), "real_trades": (5, 50), "probe_sessions": (1, 20)}
BLOCKERS = frozenset(("validation_pending", "evidence_stale", "validation_failed", "review_pending", "review_failed",
                     "audit_pending", "audit_failed", "holdout_pending", "holdout_failed", "look_limit", "gate_paused",
                     "real_money_off", "grant_inactive", "account_unavailable", "structure_ineligible", "equity_low",
                     "risk_too_large", "forward_negative", "forward_incomplete", "probe_incomplete", "real_record_negative"))


def clean(value: Any, *, band: str | None = None) -> dict | None:
    """The publisher's second allowlist. Reject malformed blocks, unknown keys, duplicate checks and hidden payloads."""
    if not isinstance(value, Mapping) or set(value) != {"target", "checks", "blocked"}:
        return None
    target, checks, blocked = value["target"], value["checks"], value["blocked"]
    if not isinstance(target, str) or target not in TARGET_KEYS or not isinstance(checks, list):
        return None
    if band is not None and {"gym": "candidate", "candidate": "probe", "probe": "sized", "sized": "maintain"}.get(band) != target:
        return None
    if blocked is not None and (not isinstance(blocked, str) or blocked not in BLOCKERS):
        return None
    if len(checks) != len(TARGET_KEYS[target]):
        return None
    out = []
    for key, row in zip(TARGET_KEYS[target], checks):
        if not isinstance(row, Mapping) or set(row) != {"key", "done", "need"} or row.get("key") != key:
            return None
        done, need = row["done"], row["need"]
        low, high = COUNT_BOUNDS.get(key, (1, 1))
        if type(done) is not int or type(need) is not int or not low <= need <= high or not 0 <= done <= need:
            return None
        out.append({"key": key, "done": done, "need": need})
    return {"target": target, "checks": out, "blocked": blocked}


def check(key: str, done: Any, need: int = 1) -> dict:
    n = int(done) if isinstance(done, (int, float)) and math.isfinite(done) else 0
    return {"key": key, "done": max(0, min(n, need)), "need": need}


def _lines(fam: Mapping, families: Mapping[str, Mapping], links: Sequence, *, prior: bool) -> set[str]:
    graph: dict[str, set[str]] = {}
    for a, b in links:
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    seen, pending = set(), [fam["lineage"]]
    while pending:
        line = pending.pop()
        if not line or line in seen:
            continue
        seen.add(line)
        pending.extend(graph.get(line, set()) - seen)
        if prior:
            pending.append((families.get(line, {}).get("spec") or {}).get("prior_lineage"))
    return seen


def _stamp(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def _probe_sessions(fam: Mapping, local: Mapping, now: float) -> int:
    """Same complete-session rule as the live path, without its first-seen writes."""
    from league.data import us_equity_session

    fid = fam["id"]
    move = (local.get("band_moves") or {}).get(fid) or {}
    stamps = [_stamp(fam["state"].get("live_promoted_at"))]
    if move.get("band") in ("probe", "sized"):
        stamps.append(_stamp(move.get("at")))
    stamps = [n for n in stamps if n is not None]
    since = max(stamps) if stamps else _stamp((local.get("probe_since") or {}).get(fid))
    if since is None or since > now:
        return 0
    zone = ZoneInfo("America/New_York")
    day, end = dt.datetime.fromtimestamp(since, zone).date(), dt.datetime.fromtimestamp(now, zone).date()
    count = 0
    while day <= end:
        try:
            session = us_equity_session(day)
        except ValueError:
            return 0
        if session is not None:
            opened = dt.datetime.combine(day, dt.time(9, 30), zone).timestamp()
            closed = dt.datetime.combine(day, dt.time(13 if session.early_close else 16), zone).timestamp()
            count += opened >= since and closed <= now
            if count >= COUNT_BOUNDS["probe_sessions"][1]:
                return count
        day += dt.timedelta(days=1)
    return count


def _gym(fam: Mapping, version: Mapping, families: Mapping, looks: Sequence, links: Sequence,
         cfg: Mapping, bundle: str) -> dict | None:
    state, n = fam["state"], version["n"]
    image = cfg["gym"].get("image_checkpoint")
    if (not image or not bundle or state.get("validation_version") != n or fam.get("validated_version") != n
            or state.get("validation_image") != image or state.get("validation_bundle") != bundle):
        return None  # missing/currently superseded evidence has no honest partial completion
    line = state.get("validation_line") or {}
    numbers, checks = line.get("numbers") or {}, line.get("checks") or {}
    if not checks or not numbers:
        return None
    trial_lines = _lines(fam, families, links, prior=True)
    trials = sum(int(f["trials"] or 0) for f in families.values() if f["lineage"] in trial_lines)
    fresh_dsr = numbers.get("lineage_trials") == trials
    sha = run_sha(version)
    review = state.get("review") or {}
    review_current = review.get("sha") == sha and review.get("version") == n
    audit = review.get("audit") or {}
    review_pass = review_current and (review.get("verdict") == "pass" or (review.get("stage") == "audit" and bool(audit)))
    audit_pass = review_pass and audit.get("verdict") == "pass"
    looked = next((r for r in looks if r["run_sha"] == sha and r["family"] == fam["id"] and r["version"] == n), None)
    q = str(numbers.get("quarters") or "").split("/")[0]
    quarters = int(q) if q.isdigit() else 0
    out = [check("validation_run", checks.get("status_ok") is True),
           check("validation_trades", numbers.get("trades"), evidence.MIN_TRADES),
           check("validation_days", numbers.get("days"), evidence.MIN_DAYS),
           check("validation_mean", checks.get("mean_positive") is True), check("validation_t", checks.get("t") is True),
           check("validation_dsr", fresh_dsr and checks.get("dsr") is True),
           check("validation_quarters", quarters, evidence.MIN_QUARTERS_POSITIVE),
           check("validation_stress", checks.get("stress") is True), check("review", review_pass), check("audit", audit_pass),
           check("holdout", False)]  # a current successful look atomically leaves Gym; a past pass cannot restore it
    linked = _lines(fam, families, links, prior=False)
    reserved = {r["run_sha"] for r in looks if r["lineage"] in linked}
    for member in families.values():
        marker = (member["state"].get("look_inflight") or {}).get("sha")
        if member["lineage"] in linked and marker:
            reserved.add(marker)
    alarm = evidence.leakage_alarm(len(looks), sum(bool(r["passed"]) for r in looks))
    if not fresh_dsr:
        blocked = "evidence_stale"
    elif not line.get("passed"):
        blocked = "validation_failed"
    elif alarm or not cfg["gym"].get("gate_checkpoint"):
        blocked = "gate_paused"
    elif looked:
        blocked = "evidence_stale" if looked["passed"] else "holdout_failed"
    elif not looked and sha not in reserved and len(reserved) >= evidence.LOOKS_PER_LINEAGE:
        blocked = "look_limit"
    elif not review_pass:
        blocked = "review_failed" if review_current and review.get("verdict") == "fail" else "review_pending"
    elif not audit_pass:
        blocked = "audit_failed" if audit.get("verdict") == "fail" else "audit_pending"
    else:
        blocked = "holdout_pending"
    return {"target": "candidate", "checks": out, "blocked": blocked}


def _live(fam: Mapping, version: Mapping, looks: Sequence, forward: Sequence, table: M.Table,
          context: Mapping, now: float) -> dict | None:
    state, band, n = fam["state"], fam["band"], version["n"]
    if state.get("banded_sha") != version.get("sha"):
        return None
    sha = run_sha(version)
    holdout = any(r["family"] == fam["id"] and r["version"] == n and r["run_sha"] == sha and r["passed"] for r in looks)
    if not holdout:
        return None  # a stale/manual band is not proof of a selected program's holdout result
    metadata = state.get("forward") or {}
    if metadata.get("version") is not None and str(metadata["version"]) != str(n):
        return None
    fwd = M.forward_stats(forward, table.sized_confidence, version=n, negative=bool(metadata.get("negative")))
    equity, sizing = context.get("equity"), context.get("sizing")
    enabled, grant = context.get("enabled") is True, context.get("grant") is True
    ready = enabled and grant and equity is not None and sizing is not None
    permitted = fam["structure"] in table.real_types
    credit = fam["structure"] not in table.credit_types or (sizing is not None and sizing >= table.credit_min_equity)
    typical = (state.get("typical_by_version") or {}).get(str(n),
        state.get("typical_max_loss_usd") if state.get("validation_version") == n else None)
    try:
        unit = M.D(typical) if typical is not None else None
    except (ValueError, ArithmeticError):
        unit = None
    known_loss = unit is not None and unit > 0
    fit = bool((not known_loss and band != "candidate") or
               (known_loss and sizing is not None and M.fits_probe(table, sizing, unit)))
    target = {"candidate": "probe", "probe": "sized", "sized": "maintain"}[band]
    out = [check("execution_ready", ready), check("holdout", holdout), check("real_structure", permitted),
           check("credit_equity", credit), check("risk_fit", fit), check("forward_nonnegative", not fwd.negative)]
    sessions = _probe_sessions(fam, context.get("local") or {}, now) if band == "probe" else 0
    if band in ("probe", "sized"):
        out += [check("forward_trades", fwd.n, table.sized_min_trades),
                check("forward_mean", fwd.mean is not None and fwd.mean > 0),
                check("forward_confidence", fwd.lcb is not None and fwd.lcb > 0)]
        if band == "probe":
            out += [check("real_trades", fwd.real_n, table.min_probe_real_trades),
                    check("probe_sessions", sessions, table.min_probe_sessions)]
        out += [check("real_record", not fwd.real_bad)]
    if not enabled:
        blocked = "real_money_off"
    elif not grant:
        blocked = "grant_inactive"
    elif equity is None or sizing is None:
        blocked = "account_unavailable"
    elif not permitted:
        blocked = "structure_ineligible"
    elif not credit:
        blocked = "equity_low"
    elif not fit:
        blocked = "risk_too_large" if known_loss else "evidence_stale"
    elif fwd.negative:
        blocked = "forward_negative"
    elif band != "candidate" and fwd.real_bad:
        blocked = "real_record_negative"
    elif band != "candidate" and not M.sized_ok(table, fwd):
        blocked = "forward_incomplete"
    elif band == "probe" and (fwd.real_n < table.min_probe_real_trades or sessions < table.min_probe_sessions):
        blocked = "probe_incomplete"
    else:
        blocked = None
    return {"target": target, "checks": out, "blocked": blocked}


def _context(live: Any, account: Mapping | None, now: float) -> tuple[M.Table, dict]:
    table = getattr(live, "table", None) or M.Table.from_constitution()
    read_grant = getattr(live, "_grant", None)
    grant = read_grant() if callable(read_grant) else None  # the existing local grant store, never a gateway request
    equity = None
    if account and account.get("stale") is False:
        try:
            instant = dt.datetime.fromisoformat(str(account["as_of"]).replace("Z", "+00:00"))
            if instant.tzinfo is not None and 0 <= now - instant.timestamp() <= 600:
                equity = M.D(account["equity"])
                if equity < 0:
                    equity = None
        except (KeyError, ValueError, TypeError, ArithmeticError):
            pass
    capital = M.D((grant.get("policy") or {}).get("capital_usd") or 0) if grant and grant.get("active") else None
    state = getattr(live, "state", None)
    local = {key: state.get(key, {}) for key in ("band_moves", "probe_since")} if state is not None else {}
    return table, {"enabled": bool(live is not None and live.real_money and live.book is not None),
                   "grant": bool(grant and grant.get("active")), "equity": equity,
                   "sizing": min(equity, capital) if equity is not None and capital is not None and capital > 0 else None,
                   "local": local}


def attach(agents: Sequence[Mapping], root: str | Path, *, live: Any = None, account: Mapping | None = None,
           now: float) -> list[dict]:
    """Attach optional progress to matching public rows. Unreadable/retired/mismatched rows carry null progress."""
    out = [dict(a, progress=None) for a in agents]
    path = Path(root) / DB_NAME
    if not path.is_file():
        return out
    try:
        from ..gym.driver import build_bundle

        cfg, bundle = settings.load(root), build_bundle()[1]
        table, context = _context(live, account, now)
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            families = {r["id"]: {**dict(r), "state": loads(r["state"], {}), "spec": loads(r["spec"], {})}
                        for r in db.execute("SELECT id,lineage,structure,band,retired_at,best_version,validated_version,trials,state,spec FROM families")}
            versions = {(r["family"], r["n"]): {**dict(r), "params": loads(r["params"], {})}
                        for r in db.execute("SELECT family,n,sha,params FROM versions")}
            looks = [dict(r) for r in db.execute("SELECT family,lineage,version,run_sha,passed FROM looks")]
            links = [(r["a"], r["b"]) for r in db.execute("SELECT a,b FROM lineage_links")]
            forward: dict[str, list] = {}
            for r in db.execute("SELECT family,source,day,pnl,max_loss,version FROM forward"):
                forward.setdefault(r["family"], []).append(dict(r))
        for agent in out:
            fam = families.get(agent.get("id"))
            if (not fam or fam["retired_at"] or agent.get("retired_at") or fam["band"] != agent.get("band")
                    or fam["lineage"] != agent.get("family")):
                continue
            try:
                state = fam["state"]
                n = (fam["best_version"] or state.get("best_train_version")) if fam["band"] == "gym" else state.get("banded_version")
                version = versions.get((fam["id"], n))
                if version is None:
                    continue
                if fam["band"] == "gym":
                    value = _gym(fam, version, families, looks, links, cfg, bundle)
                elif fam["band"] in ("candidate", "probe", "sized"):
                    value = _live(fam, version, looks, forward.get(fam["id"], []), table, context, now)
                else:
                    value = None
                agent["progress"] = clean(value, band=fam["band"])
            except (KeyError, TypeError, ValueError, ArithmeticError):
                pass  # malformed private evidence becomes unavailable; no payload is reflected into the site
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError, ArithmeticError):
        pass
    return out


__all__ = ["attach", "clean", "TARGET_KEYS", "COUNT_BOUNDS", "BLOCKERS"]
