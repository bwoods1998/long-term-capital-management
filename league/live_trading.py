"""The owner's grant of real money: `options-swarm-20260928`, the Brokerage Account only.

Built fresh for the options overhaul (Sept 26, 2026; plan "Money" -> "The grant", trap 1), in place
of the grant the campaign store kept (`league/campaigns.py`, cut in Wave 2b). **Real money turns on
and off ONLY through this grant**: every real entry, promotion, envelope and swing in the House
(`House.grant`), the allocator and `league/capital.py` asks it, and a House with no active grant
sends no real opening order (exits always go on).

- **One venue.** The Brokerage Account (`alpaca`). The grant names nothing else.
- **Its own store**, `live-grant.sqlite` in the House's state root, made on first use: it works on
  an EMPTY state root (no campaign database, nothing migrated).
- **Capital** is the lower of the account's equity and the owner's ceiling (`league/config.json`
  `live_trading.ceiling_usd`), read at each ratification, and never above the $10,000 project
  envelope. A deposit that lands is answered by ratifying again, which raises capital up to the
  ceiling (the old rule that deposits never enlarge a grant is gone). Capital is the grant's
  `venue_capital_usd.alpaca` and `max_loss_usd`, the envelope the allocator and the tuition read.
- **Pinned** to the money digest (`constitution.money_digest`): when a rule that governs real money
  changes, the grant allows no new entry until the owner ratifies it on the new digest.
- **Revocable**: `--disable` revokes it for good (exits and accounting go on; a revoked grant is
  never reactivated or ratified: a new grant needs a new identity).
- The owner drives it on the box: `scripts/live_trading.py [--enable [ID] | --ratify [ID] | --disable]`,
  which runs `main` here against `/workspace/state`. The House reads the store at every check, so
  no restart is needed for a change to hold.
- **Standing** (LTCM v3, D5, Oct 2, 2026): `LiveGrant.standing`, run by the House's `grant` job
  (`league/ops/grant.py`, hourly and at House start), ratifies the grant itself, the way `--ratify` does,
  in exactly two cases: the money digest moved and an owner's release change (a deploy or rollback
  with no updater attestation) is on record since the grant was last pinned, or a deposit landed since
  then. It never enables, never touches a revoked grant, never lifts capital above the lower of equity
  and the ceiling nor the ceiling above the one last ratified without an owner's release change, and
  refuses (changing nothing) when anything is unreadable or capital would not cover the smallest stake.
  `--disable` stays the owner's stop; the ceiling and the money table stay the owner's deploy.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
from datetime import datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

#: The grant the options swarm trades under (plan "Money": created fresh, never migrated).
GRANT_ID = "options-swarm-20260928"
#: The one venue a grant covers: the Brokerage Account.
VENUE = "alpaca"
#: The grant's store, in the House's state root.
STORE = "live-grant.sqlite"
#: No grant is ever larger than the owner's whole project budget.
PROJECT_ENVELOPE_USD = Decimal("10000")
VERSION = 2
CENT = Decimal("0.01")
#: A funding activity's statuses that mean the money landed (as `ltcm.performance` and the live path read funding).
LANDED = frozenset({"executed", "complete", "completed"})
#: The deploy record's stages that change which release runs (`league/watchdog.py`): a promotion and a rollback.
RELEASE_CHANGES = frozenset({"promote", "rollback"})


class GrantClosed(ValueError):
    """An owner action the grant refuses: nothing was changed."""

    code = "live_grant_closed"


def _money(value: Any, what: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{what} is not a number") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{what} must be finite and nonnegative")
    return amount.quantize(CENT, rounding=ROUND_DOWN)


def smallest_stake(constitution: Mapping[str, Any] | None = None) -> Decimal:
    """The smallest real stake the money rules give the Brokerage Account: a grant must cover one,
    and its seat count (`max_agents`) is its capital over this. With the allocator on, the smallest
    of the account's bunt and probe stakes; otherwise the micro rung's stake. Since the options swarm's money table
    (`options_money`), its Probe floor: one contract of at most that maximum loss."""
    from .constitution import CONSTITUTION

    rules = constitution or CONSTITUTION
    options = rules.get("options_money")
    if isinstance(options, Mapping):
        # The options swarm (Sept 26, 2026, Wave 5): the smallest real structure is the Probe's one-contract floor.
        floor = Decimal(str((options.get("probe") or {}).get("floor_usd") or 0))
        if floor > 0:
            return floor
    allocator = rules.get("allocator") or {}
    if allocator.get("enabled"):
        stakes = [Decimal(str(v)) for table in ("bunt_usd", "probe_bunt_usd")
                  for k, v in (allocator.get(table) or {}).items() if k == VENUE or k.startswith(VENUE + "_")]
        if stakes:
            return min(stakes)
    return Decimal(str(rules["rungs"]["2"]["stake_usd"]))


def policy(equity_usd: Any, ceiling_usd: Any) -> dict[str, Any]:
    """The grant's policy at this moment: capital is the lower of the account's equity and the
    owner's ceiling, pinned to the current money digest."""
    from .constitution import money_digest

    equity, ceiling = _money(equity_usd, "the account's equity"), _money(ceiling_usd, "the owner's ceiling")
    if ceiling > PROJECT_ENVELOPE_USD:
        raise ValueError(f"the ceiling ${ceiling} is above the ${PROJECT_ENVELOPE_USD} project envelope")
    capital = min(equity, ceiling)
    stake = smallest_stake()
    if capital < stake:
        raise ValueError(f"capital ${capital} does not cover the smallest real stake (${stake})")
    return {
        "version": VERSION, "grant": "options-swarm", "venues": [VENUE], "max_rung": 3, "expires": None,
        "capital_usd": str(capital), "max_loss_usd": str(capital), "venue_capital_usd": {VENUE: str(capital)},
        "equity_usd": str(equity), "ceiling_usd": str(ceiling),
        "stake_usd": str(stake), "max_agents": int(capital // stake),
        "constitution_digest": money_digest(),
        "capital_source": ("The lower of the Brokerage Account's equity and the owner's ceiling at each ratification; "
                           "a deposit is answered by ratifying again, up to the ceiling."),
    }


def holds(stored: Mapping[str, Any]) -> bool:
    """Whether a stored policy still governs: it is this grant's shape, names the Brokerage Account
    only, and was pinned on the money rules in force now."""
    from .constitution import money_digest

    return (stored.get("version") == VERSION and list(stored.get("venues") or []) == [VENUE]
            and list((stored.get("venue_capital_usd") or {})) == [VENUE]
            and stored.get("constitution_digest") == money_digest())


def policy_hash(stored: Mapping[str, Any] | str | None) -> str | None:
    """The SHA-256 of a policy's canonical form (the standing grant's receipts: before and after)."""
    if stored is None:
        return None
    text = stored if isinstance(stored, str) else _canonical(stored)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _epoch(value: Any) -> float | None:
    """Epoch seconds from an RFC 3339 stamp or a bare date (read as 00:00Z), or None. A time with no zone is no
    time; nanoseconds are cut to microseconds."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if math.isfinite(value) else None
    text = str(value or "").strip()
    if not text:
        return None
    if "T" not in text:
        text += "T00:00:00Z"
    text = text.replace("Z", "+00:00")
    if "." in text:
        head, _, rest = text.partition(".")
        n = 0
        while n < len(rest) and rest[n].isdigit():
            n += 1
        text = f"{head}.{rest[:n][:6].ljust(6, '0')}{rest[n:]}"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    return stamp.timestamp() if stamp.tzinfo is not None else None


def deposits_after(funding: Iterable[Any], after: float) -> list[dict[str, Any]]:
    """The owner's deposits that landed after `after` (epoch seconds) among the Brokerage Account's activities:
    a funding type (`ltcm.performance.ALPACA_FUNDING`) with a positive amount, settled, timed when the money moved
    (`transaction_time`, else `created_at`, else `date`). Anything else (trades, withdrawals, pending or failed
    funding, a row with no readable time or amount) is no deposit."""
    from ltcm.performance import ALPACA_FUNDING

    out = []
    for row in funding or ():
        if not isinstance(row, Mapping) or str(row.get("activity_type") or "") not in ALPACA_FUNDING:
            continue
        if str(row.get("status") or "executed").lower() not in LANDED:
            continue
        try:
            amount = Decimal(str(row.get("net_amount")))
        except (InvalidOperation, ValueError):
            continue
        when = _epoch(row.get("transaction_time") or row.get("created_at") or row.get("date"))
        if not amount.is_finite() or amount <= 0 or when is None or when <= after:
            continue
        out.append({"id": row.get("id"), "activity_type": row.get("activity_type"), "at": when})
    return out


def owner_change(deploy_rows: Iterable[Any], after: float) -> dict[str, Any] | None:
    """The newest release change on the deploy record (`deploys.jsonl`) after `after` that the updater did not make:
    a promotion or rollback that succeeded and carries no attested `sha` (the watchdog writes the updater's sha into
    every row of its deploys; the owner's `floor_box.py` deploy and rollback carry none), and is no drill's (a drill
    stages a copy of the running release). A money digest can move only by such a change: the constitution is
    forbidden to the updater (`ci.FORBIDDEN`)."""
    rows = [row for row in deploy_rows or () if isinstance(row, Mapping)]
    drills = {str(row.get("deploy")) for row in rows if row.get("stage") == "drill" and row.get("deploy")}
    found: dict[str, Any] | None = None
    for row in rows:
        if row.get("stage") not in RELEASE_CHANGES or row.get("ok") is not True:
            continue
        if row.get("sha") or row.get("attestation") or str(row.get("deploy")) in drills:
            continue
        if any(str(row.get(k) or "").startswith("drill-") for k in ("release", "current", "from")):
            continue  # the drill's copy (`drill-...`, league/watchdog.py) is never an owner's release, even before its row
        when = _epoch(row.get("ts") if row.get("ts") is not None else row.get("at"))
        if when is None or when <= after:
            continue
        if found is None or when >= found["ts"]:
            found = {"ts": when, "deploy": row.get("deploy"), "stage": row.get("stage"),
                     "release": row.get("current") or row.get("to") or row.get("release")}
    return found


class LiveGrant:
    """The grant's store. Thread-safe; any number of processes may open it (the House and the
    owner's command)."""

    def __init__(self, path: str | Path, *, clock: Callable[[], float] = time.time):
        self.path, self.clock = Path(path), clock
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS grants(id TEXT PRIMARY KEY, started REAL NOT NULL, policy TEXT NOT NULL,
                revoked REAL, owner TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ratifications(id TEXT NOT NULL, at REAL NOT NULL, old_policy TEXT NOT NULL,
                new_policy TEXT NOT NULL, why TEXT NOT NULL);
        """)

    def close(self) -> None:
        with self.lock:
            self.db.close()

    # ------------------------------------------------------------------ reading
    def current(self) -> dict[str, Any] | None:
        """The latest grant, revoked or not (a revoked grant keeps its capital accounting), with
        `active`: not revoked, started, and pinned on the money rules in force now."""
        with self.lock:
            row = self.db.execute("SELECT * FROM grants ORDER BY started DESC, rowid DESC LIMIT 1").fetchone()
        if row is None:
            return None
        value = {**dict(row), "policy": json.loads(row["policy"]), "mode": "persistent", "ends": None}
        value["active"] = value["revoked"] is None and value["started"] <= self.clock() and holds(value["policy"])
        return value

    #: The names the House's callers used on the campaign store's grant.
    live_trading = current
    live_authorization = current

    def allows_live(self, target_rung: int) -> bool:
        """New real-money entries (rung 2) and stakes above the probe (rung 3): only under an active
        grant, up to its `max_rung`."""
        if target_rung not in (2, 3):
            return False
        grant = self.current()
        return bool(grant and grant["active"] and target_rung <= int(grant["policy"]["max_rung"]))

    def ratifications(self) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM ratifications ORDER BY at, rowid")]

    # ------------------------------------------------------------------ the owner's actions
    def enable(self, ident: str, equity_usd: Any, ceiling_usd: Any) -> dict[str, Any]:
        """Account-owner action: create the grant. Enabling a grant that exists ratifies it (capital
        read again); a revoked identity is never reactivated; a second identity waits until the
        first is revoked."""
        if not isinstance(ident, str) or not ident.strip() or len(ident) > 100:
            raise ValueError("a grant needs a bounded identity")
        encoded = _canonical(policy(equity_usd, ceiling_usd))
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute("SELECT * FROM grants WHERE id=?", (ident,)).fetchone()
                other = self.db.execute("SELECT id FROM grants WHERE id<>? AND revoked IS NULL", (ident,)).fetchone()
                if row is not None and row["revoked"] is not None:
                    raise GrantClosed(f"the grant {ident} was revoked; a revoked grant is never reactivated")
                if row is None and other is not None:
                    raise GrantClosed(f"the grant {other['id']} is in force; revoke it before enabling another")
                if row is None:
                    self.db.execute("INSERT INTO grants VALUES(?,?,?,NULL,?)", (ident, self.clock(), encoded, ident))
                elif row["policy"] != encoded:
                    self._record(ident, row["policy"], encoded, "enabled again: capital and digest read afresh")
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return self.current()

    def ratify(self, ident: str, equity_usd: Any, ceiling_usd: Any, *, why: str = "ratified by the owner") -> dict[str, Any]:
        """Account-owner action: keep the grant, re-pinned to the current money digest, its capital
        read afresh (the lower of equity and the ceiling now: a deposit raises it, a loss lowers it).
        The old policy is kept in `ratifications`. A revoked grant stays revoked."""
        encoded = _canonical(policy(equity_usd, ceiling_usd))
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute("SELECT * FROM grants WHERE id=?", (ident,)).fetchone()
                if row is None:
                    raise GrantClosed(f"no grant {ident} to ratify")
                if row["revoked"] is not None:
                    raise GrantClosed(f"the grant {ident} was revoked; a revoked grant cannot be ratified")
                if row["policy"] != encoded:
                    self._record(ident, row["policy"], encoded, why)
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return self.current()

    def revoke(self) -> dict[str, Any] | None:
        """Account-owner action: no new real entry from now on; exits and accounting go on."""
        with self.lock:
            self.db.execute("UPDATE grants SET revoked=COALESCE(revoked,?)", (self.clock(),))
        return self.current()

    def _record(self, ident: str, old: str, new: str, why: str, at: float | None = None) -> None:
        self.db.execute("INSERT INTO ratifications VALUES(?,?,?,?,?)", (ident, self.clock() if at is None else at, old, new, why))
        self.db.execute("UPDATE grants SET policy=? WHERE id=?", (new, ident))

    # ------------------------------------------------------------------ the standing grant (v3, D5)
    def _latest(self) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM grants ORDER BY started DESC, rowid DESC LIMIT 1").fetchone()

    def _pinned_at(self, row: sqlite3.Row) -> float:
        """When the grant's policy was last written: its last ratification, else its start."""
        last = self.db.execute("SELECT MAX(at) FROM ratifications WHERE id=?", (row["id"],)).fetchone()[0]
        return max(float(row["started"]), float(last)) if last is not None else float(row["started"])

    def standing_due(self) -> dict[str, Any]:
        """What the standing grant would look at, read only: the grant in force (None when there is none or the
        latest is revoked), when its policy was pinned (deposits after that are new), and whether the money digest
        moved since. The job reads the account only when there is a grant to keep."""
        from .constitution import money_digest

        with self.lock:
            row = self._latest()
            if row is None or row["revoked"] is not None:
                return {"grant": None, "revoked": row is not None, "since": None, "digest_moved": False,
                        "policy_hash": policy_hash(row["policy"]) if row is not None else None}
            stored = json.loads(row["policy"])
            return {"grant": row["id"], "revoked": False, "since": self._pinned_at(row),
                    "digest_moved": stored.get("constitution_digest") != money_digest(),
                    "policy_hash": policy_hash(row["policy"])}

    def standing(self, now: float, equity: Any, release: str | None, deploy_rows: Iterable[Any], *,
                 funding: Iterable[Any] = (), ceiling_usd: Any = None) -> dict[str, Any]:
        """The standing grant (GOAL D5): ratify the grant in force without the owner's hand, in two cases only.

        (a) `digest`: the policy's `constitution_digest` is not the money digest now. That moves only by an owner's
            deploy, so one must be on the deploy record since the grant was last pinned (`owner_change`), and the
            running `release` must be known; it is written in `why`.
        (b) `deposit`: a deposit landed since the grant was last pinned (`deposits_after` over `funding`, the
            Brokerage Account's funding activities), so capital is read again.

        Capital is `policy(equity, ceiling)`: the lower of equity and the owner's ceiling (`ceiling_usd`, else
        `league/config.json`), never above the project envelope, and refused below the smallest stake. A ceiling above
        the one last ratified also needs an owner's release change on record. A revoked grant is never touched and no
        grant is ever created. A refusal changes nothing (a moved digest keeps new real entries held). A ratification
        always writes a `ratifications` row, even when the policy reads the same, so the pin moves past what it
        answered. Returns the receipt: `action` none | ratified | refused, `triggers`, `why`, policy hashes."""
        from .constitution import money_digest

        out: dict[str, Any] = {"action": "none", "grant": None, "release": release, "triggers": [], "why": "",
                               "before": None, "after": None, "digest": money_digest()[:12]}
        try:
            top = ceiling() if ceiling_usd is None else _money(ceiling_usd, "the owner's ceiling")
        except Exception as exc:  # noqa: BLE001 - an unreadable ceiling ratifies nothing
            top, ceiling_problem = None, f"the owner's ceiling cannot be read: {exc}"
        else:
            ceiling_problem = None
        rows, funding = list(deploy_rows or ()), list(funding or ())
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self._latest()
                if row is None or row["revoked"] is not None:
                    self.db.execute("COMMIT")
                    out["why"] = "no grant to keep" if row is None else "the grant is revoked; a revoked grant is never ratified"
                    out["grant"] = row["id"] if row is not None else None
                    out["before"] = out["after"] = policy_hash(row["policy"]) if row is not None else None
                    return out
                ident, old = row["id"], row["policy"]
                stored, since = json.loads(old), self._pinned_at(row)
                out.update(grant=ident, before=policy_hash(old), after=policy_hash(old))
                digest_moved = stored.get("constitution_digest") != money_digest()
                landed = deposits_after(funding, since)
                out["triggers"] = (["digest"] if digest_moved else []) + (["deposit"] if landed else [])
                if not out["triggers"]:
                    self.db.execute("COMMIT")
                    out["why"] = "the grant holds on the money digest and no deposit landed since it was pinned"
                    return out
                owner = owner_change(rows, since)
                refusal, encoded = None, None
                if ceiling_problem:
                    refusal = ceiling_problem
                elif digest_moved and not release:
                    refusal = "the money digest moved and the running release is unknown"
                elif digest_moved and owner is None:
                    refusal = "the money digest moved with no owner's deploy on record since the grant was last pinned"
                else:
                    try:
                        new = policy(equity, top)
                    except ValueError as exc:
                        refusal = str(exc)
                    else:
                        try:
                            was = Decimal(str(stored.get("ceiling_usd")))
                        except (InvalidOperation, ValueError):
                            was = Decimal(0)
                        if not was.is_finite() or (Decimal(new["ceiling_usd"]) > was and owner is None):
                            refusal = "the owner's ceiling rose with no owner's deploy on record since the grant was last pinned"
                        elif not holds(new):
                            refusal = "the new policy would not hold"
                        else:
                            encoded = _canonical(new)
                if refusal is not None or encoded is None:
                    self.db.execute("COMMIT")
                    out.update(action="refused", why=f"standing: {refusal}")
                    return out
                parts = []
                if digest_moved:
                    parts.append(f"money digest {str(stored.get('constitution_digest') or '')[:12]} -> {money_digest()[:12]} "
                                 f"by the owner's {owner['stage']} {owner['deploy']}; running release {release}")
                if landed:
                    parts.append(f"{len(landed)} deposit(s) landed since the grant was pinned "
                                 f"({', '.join(str(d['activity_type']) for d in landed[:5])})")
                why = "standing: " + "; ".join(parts)
                self._record(ident, old, encoded, why, at=max(float(now), since))  # the pin never moves back
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        out.update(action="ratified", why=why, after=policy_hash(encoded))
        return out

    def report(self) -> dict[str, Any]:
        return {"live_trading": self.current(), "micro_entries_allowed": self.allows_live(2),
                "scaled_entries_allowed": self.allows_live(3), "ratifications": len(self.ratifications())}


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def ceiling(config: Mapping[str, Any] | None = None) -> Decimal:
    """The owner's ceiling, `league/config.json` `live_trading.ceiling_usd`."""
    if config is None:
        from .service import load_config

        config = load_config()
    value = (config.get("live_trading") or {}).get("ceiling_usd")
    if value is None:
        raise ValueError("league/config.json names no live_trading.ceiling_usd")
    return _money(value, "the owner's ceiling")


def read_equity(config: Mapping[str, Any] | None = None) -> Decimal:
    """The Brokerage Account's equity, read through the gateway (a balance read: no House, no order)."""
    from .service import load_config, load_env, secret
    from .venues import gateway_broker

    load_env()
    config = config or load_config()
    balance = gateway_broker(VENUE, gateway_url=config["gateway_url"], token=secret("GATEWAY_TOKEN")).balance()
    if balance.currency != "USD":
        raise ValueError("the grant's capital must be denominated in USD")
    return _money(max(Decimal(0), Decimal(str(balance.equity))), "the account's equity")


def main(argv: list[str] | None = None) -> dict[str, Any]:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="The House's state root (on the box: /workspace/state).")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--enable", nargs="?", const=GRANT_ID, help=f"Account owner: create the grant (default {GRANT_ID}).")
    action.add_argument("--ratify", nargs="?", const=GRANT_ID,
                        help="Account owner: keep the grant on the current money rules, capital read afresh (after a deposit).")
    action.add_argument("--disable", action="store_true", help="Revoke new real entries for good; exits and accounting go on.")
    args = parser.parse_args(argv)
    args.root.mkdir(parents=True, exist_ok=True)
    grant = LiveGrant(args.root / STORE)
    try:
        prepared = None
        if args.disable:
            grant.revoke()
        else:
            equity, top = read_equity(), ceiling()
            if args.enable:
                grant.enable(args.enable, equity, top)
            elif args.ratify:
                grant.ratify(args.ratify, equity, top)
            else:
                prepared = policy(equity, top)
        out = {**grant.report(), "prepared_policy": prepared}
        print(json.dumps(out, indent=2, default=str))
        return out
    finally:
        grant.close()


if __name__ == "__main__":
    main()
