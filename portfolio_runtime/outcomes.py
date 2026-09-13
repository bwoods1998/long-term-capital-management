"""Forward paper decision feedback from the existing immutable accounting journal.

Only actually executed allocations and recorded closing marks produce returns.
Feedback is descriptive, overlapping and uncontrolled; it cannot establish
investment skill, authorize spending, or alter the investment mandate.
"""

from dataclasses import asdict
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .contracts import timestamp
from .provider import ClosingConnection, canonical


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _stamp(value):
    return timestamp(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fraction(value):
    amount = Decimal(value)
    if not amount.is_finite():
        raise ValueError("Finite recorded accounting value required")
    return Fraction(amount)


def _pct(value):
    with localcontext() as context:
        context.prec = 80
        return format(
            (Decimal(value.numerator) / Decimal(value.denominator) * 100).quantize(
                Decimal("0.000000000001")
            ),
            "f",
        )


class OutcomeJournal:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.is_symlink():
            raise ValueError("Outcome journal cannot be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS outcome_contract(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcome_cohorts(id TEXT PRIMARY KEY,observed_at TEXT NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcome_context(id TEXT PRIMARY KEY,observed_at TEXT NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcome_receipts(id TEXT PRIMARY KEY,decision_id TEXT NOT NULL,market_as_of TEXT NOT NULL,observed_at TEXT NOT NULL,body TEXT NOT NULL);""")
            for table in (
                "outcome_contract",
                "outcome_cohorts",
                "outcome_receipts",
                "outcome_context",
            ):
                db.executescript(
                    f"CREATE TRIGGER IF NOT EXISTS {table}_immutable BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'immutable forward outcome'); END; CREATE TRIGGER IF NOT EXISTS {table}_retained BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'immutable forward outcome'); END;"
                )
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def bind_context(
        self,
        decision_id,
        *,
        run_id,
        evidence_cutoff,
        evidence_sha256,
        policy,
        observed_at,
    ):
        """Attach a frozen epoch's provenance; missing legacy metadata stays absent."""
        evidence_cutoff, observed_at = _stamp(evidence_cutoff), _stamp(observed_at)
        if (
            not isinstance(run_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", run_id)
            or not isinstance(decision_id, str)
            or not decision_id.startswith(run_id + ":")
            or not isinstance(evidence_sha256, str)
            or not re.fullmatch(r"[a-f0-9]{64}", evidence_sha256)
            or not isinstance(policy, dict)
            or set(policy) != {"version", "name", "memory_limit"}
            or type(policy["version"]) is not int
            or not 0 <= policy["version"] <= 2
            or policy["name"] not in ("memory_3", "fresh")
            or type(policy["memory_limit"]) is not int
            or policy["memory_limit"] != (3 if policy["name"] == "memory_3" else 0)
        ):
            raise ValueError("Frozen research provenance required")
        body = canonical(
            {
                "run_id": run_id,
                "evidence_cutoff": evidence_cutoff,
                "evidence_sha256": evidence_sha256,
                "research_policy": policy,
            }
        )
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cohort = db.execute(
                "SELECT body FROM outcome_cohorts WHERE id=?", (decision_id,)
            ).fetchone()
            if cohort is None:
                return False
            decided = timestamp(json.loads(cohort[0])["decided_at"])
            if not timestamp(evidence_cutoff) <= decided <= timestamp(observed_at):
                raise ValueError(
                    "Research provenance cannot come from the decision's future"
                )
            old = db.execute(
                "SELECT body FROM outcome_context WHERE id=?", (decision_id,)
            ).fetchone()
            if old and old[0] != body:
                raise ValueError("Decision research provenance changed")
            db.execute(
                "INSERT OR IGNORE INTO outcome_context VALUES(?,?,?)",
                (decision_id, observed_at, body),
            )
        return True

    def observe(self, ledger, *, observed_at):
        observed_at = _stamp(observed_at)
        # events() checks the original hash chain. Later receipts/benchmarks
        # cannot enter a snapshot supposedly observed before they arrived.
        events = [
            event
            for event in ledger.events()
            if timestamp(event["at"]) <= timestamp(observed_at)
        ]
        contract = canonical(
            {
                "schema_version": 1,
                "created_at": ledger.created_at,
                "mandate": asdict(ledger.mandate),
                "method": "executed-allocation-to-recorded-close-v1",
            }
        )
        decisions = {
            event["id"]: event for event in events if event["kind"] == "decision"
        }
        benchmark = {
            event["payload"]["as_of"]: event
            for event in events
            if event["kind"] == "benchmark"
        }
        added = 0
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT body FROM outcome_contract WHERE id=1").fetchone()
            if old and old[0] != contract:
                raise ValueError("Outcome account or methodology changed")
            db.execute(
                "INSERT OR IGNORE INTO outcome_contract VALUES(1,?)", (contract,)
            )
            for identity, event in decisions.items():
                payload = event["payload"]
                cohort = {
                    "decision_id": identity,
                    "decided_at": payload["decided_at"],
                    "targets": payload["targets"],
                    "rationale": payload.get("rationale", ""),
                    "evidence_refs": payload["evidence_refs"],
                    "decision_sha256": _hash(event),
                }
                existing = db.execute(
                    "SELECT body FROM outcome_cohorts WHERE id=?", (identity,)
                ).fetchone()
                if existing and existing[0] != canonical(cohort):
                    raise ValueError("Original allocation decision changed")
                db.execute(
                    "INSERT OR IGNORE INTO outcome_cohorts VALUES(?,?,?)",
                    (identity, observed_at, canonical(cohort)),
                )
            for index, execution in enumerate(events):
                if execution["kind"] != "rebalance":
                    continue
                identity = execution["payload"]["decision_id"]
                if identity not in decisions:
                    raise ValueError(
                        "Executed allocation is missing its prior decision"
                    )
                nav = execution["payload"]["nav"]
                start = nav.get("valuation_at", execution["at"])
                base = _fraction(nav["opening_equity"])
                if base <= 0:
                    continue
                growth = _fraction(nav["equity_before_flow"]) / base
                base = _fraction(nav["equity"])
                marked = 0
                for event in events[index + 1 :]:
                    if event["kind"] == "rebalance":
                        break  # Subsequent policy decisions have their own cohort.
                    nav = event["payload"].get("nav")
                    if not nav:
                        continue
                    end = nav.get("valuation_at", event["at"])
                    if timestamp(end) < timestamp(start) or base <= 0:
                        raise ValueError("Outcome accounting moved backwards")
                    growth *= _fraction(nav["equity_before_flow"]) / base
                    base = _fraction(nav["equity"])
                    if (
                        event["kind"] != "mark"
                        or event["payload"].get("valuation_model") != "daily_close"
                        or timestamp(end) <= timestamp(start)
                    ):
                        continue
                    marked += 1
                    opening, closing = benchmark.get(start), benchmark.get(end)
                    index_growth = None
                    if opening and closing:
                        index_growth = _fraction(
                            closing["payload"]["value"]
                        ) / _fraction(opening["payload"]["value"])
                    source = {
                        "execution": _hash(execution),
                        "mark": _hash(event),
                        "benchmark_open": _hash(opening) if opening else None,
                        "benchmark_close": _hash(closing) if closing else None,
                    }
                    receipt_id = "outcome-" + _hash([identity, source])
                    body = {
                        "schema_version": 1,
                        "id": receipt_id,
                        "decision_id": identity,
                        "observed_at": observed_at,
                        "executed_at": start,
                        "market_as_of": end,
                        "recorded_closes": marked,
                        "portfolio_return_pct": _pct(growth - 1),
                        "benchmark_return_pct": _pct(index_growth - 1)
                        if index_growth is not None
                        else None,
                        "net_excess_percentage_points": _pct(growth - index_growth)
                        if index_growth is not None
                        else None,
                        "benchmark": "S&P 500 Total Return",
                        "source_sha256": source,
                        "trading_costs_included": True,
                        "research_costs_included": False,
                        "investment_skill_assessed": False,
                    }
                    changed = db.execute(
                        "INSERT OR IGNORE INTO outcome_receipts VALUES(?,?,?,?,?)",
                        (receipt_id, identity, end, observed_at, canonical(body)),
                    ).rowcount
                    added += changed
        return {"receipts_added": added, **self.summary()}

    def context(self, *, cutoff, limit=6):
        cutoff = _stamp(cutoff)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Outcome context must be bounded")
        with self.connect() as db:
            rows = db.execute(
                "SELECT r.body,c.body cohort FROM outcome_receipts r JOIN outcome_cohorts c ON c.id=r.decision_id WHERE r.observed_at<=? AND c.observed_at<=? ORDER BY r.market_as_of DESC,r.observed_at DESC,json_extract(r.body,'$.benchmark_return_pct') IS NULL,r.id",
                (cutoff, cutoff),
            ).fetchall()
            research_context = {
                row["id"]: json.loads(row["body"])
                for row in db.execute(
                    "SELECT id,body FROM outcome_context WHERE observed_at<=?",
                    (cutoff,),
                )
            }
        selected, seen = [], set()
        for row in rows:
            receipt, cohort = json.loads(row["body"]), json.loads(row["cohort"])
            if receipt["decision_id"] in seen:
                continue
            seen.add(receipt["decision_id"])
            selected.append(
                {
                    "decision_id": receipt["decision_id"],
                    "decided_at": cohort["decided_at"],
                    "targets": cohort["targets"],
                    "prior_rationale": cohort["rationale"],
                    "research_context": research_context.get(receipt["decision_id"]),
                    **{
                        key: receipt[key]
                        for key in (
                            "observed_at",
                            "executed_at",
                            "market_as_of",
                            "recorded_closes",
                            "portfolio_return_pct",
                            "benchmark_return_pct",
                            "net_excess_percentage_points",
                        )
                    },
                    "interpretation": "Actual paper account interval, net of trading costs and excluding deposits. Uncontrolled overlapping observations do not establish causal investment skill; inspect errors and changing evidence before revising a thesis.",
                }
            )
            if len(selected) == limit:
                break
        return selected

    def summary(self):
        with self.connect() as db:
            cohorts = db.execute("SELECT count(*) FROM outcome_cohorts").fetchone()[0]
            row = db.execute(
                "SELECT count(*),count(DISTINCT decision_id),count(DISTINCT market_as_of),max(observed_at) FROM outcome_receipts"
            ).fetchone()
        return {
            "schema_version": 1,
            "decision_cohorts": cohorts,
            "outcome_receipts": row[0],
            "decisions_with_outcomes": row[1],
            "distinct_closing_observations": row[2],
            "latest_observed_at": row[3],
            "expansion_eligible": False,
            "reason": "No preregistered controlled investment-policy comparison has established benefit.",
        }
