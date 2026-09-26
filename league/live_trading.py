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
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping

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

    def _record(self, ident: str, old: str, new: str, why: str) -> None:
        self.db.execute("INSERT INTO ratifications VALUES(?,?,?,?,?)", (ident, self.clock(), old, new, why))
        self.db.execute("UPDATE grants SET policy=? WHERE id=?", (new, ident))

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
