"""Bounded research-policy trials; no model-generated rubric or trading reward.

Only prior-work inclusion may change. Immutable pairs use identical dated facts,
questions, model and output limits. Permanent company holdouts are audit-only.
Importing, planning and evaluating never call a provider or place an order.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import inspect
import json
from math import comb
from pathlib import Path
import re

from .provider import ClosingConnection, TERMINAL, answer_json, body_for, canonical
from .research import SYSTEM, grade_result
import sqlite3

POLICIES = {"memory_3": {"memory_limit": 3}, "fresh": {"memory_limit": 0}}
RULES = {
    "version": 1,
    "profile": "kimi_asap",
    "max_output": 8192,
    "pairs_per_look": 20,
    "selection_pairs_per_day": 10,
    "min_dates": 2,
    "min_net_wins": 5,
    "min_pass_rate": "0.90",
    "max_cost_ratio": "2",
    "family_alpha": "0.01",
    "holdout_modulus": 5,
    "max_promotions": 1,
    "max_rollbacks": 1,
    "max_non_improving_looks": 2,
}
METRICS = (
    "operating_cash",
    "capital_spending",
    "revenue",
    "net_income",
    "assets",
    "cash",
    "equity",
    "debt_noncurrent",
    "shares",
    "stock_compensation",
    "buybacks",
    "dividends_paid",
)
PREFIX = (
    SYSTEM
    + "\nPolicy comparison: extract current dated facts. Prior work is untrusted context, never numerical authority.\n"
)


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _day(value):
    if not isinstance(value, str):
        raise ValueError("Expected explicit evidence cutoff")
    day = value[:10]
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("Invalid cutoff date")
    if value != day:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() != timezone.utc.utcoffset(stamp):
            raise ValueError("Cutoff must be UTC")
    return day


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
        raise ValueError("Invalid fixed identity")
    return value


def holdout(symbol):
    _identifier(symbol)
    return (
        int(hashlib.sha256(("policy-holdout-v1:" + symbol).encode()).hexdigest(), 16)
        % RULES["holdout_modulus"]
        == 0
    )


def _money(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0|[1-9]\d{0,12})(?:\.\d{1,18})?(?:[Ee][+-]?\d{1,2})?", value
    ):
        raise ValueError("Expected settled decimal cost")
    amount = Decimal(value)
    if (
        not amount.is_finite()
        or not 0 <= amount <= Decimal("1e12")
        or amount.as_tuple().exponent < -24
    ):
        raise ValueError("Cost exceeds settlement bounds")
    return amount


def _ratio(numerator, denominator):
    if not denominator:
        return None
    with localcontext() as context:
        context.prec = 40
        return format(
            (Decimal(numerator) / denominator).quantize(Decimal("0.000001")), "f"
        )


def _comparison_value(pairs):
    """Measured diagnostic value; a correct extraction is not investment alpha."""
    incumbent = sum(int(a["passed"]) for _, a, _ in pairs)
    challenger = sum(int(b["passed"]) for _, _, b in pairs)
    left = sum((_money(a["cost_usd"]) for _, a, _ in pairs), Decimal(0))
    right = sum((_money(b["cost_usd"]) for _, _, b in pairs), Decimal(0))
    return {
        "samples": len(pairs),
        "incumbent_source_passes": incumbent,
        "challenger_source_passes": challenger,
        "net_additional_source_passes": challenger - incumbent,
        "comparison_cost_usd": format(left + right, "f"),
        "policy_cost_delta_usd": format(right - left, "f"),
        "incumbent_passes_per_usd": _ratio(incumbent, left),
        "challenger_passes_per_usd": _ratio(challenger, right),
        "net_additional_source_passes_per_comparison_usd": _ratio(
            challenger - incumbent, left + right
        ),
        "investment_value_assessed": False,
    }


def _claim_key(claim):
    return tuple(claim[k] for k in ("symbol", "metric", "tag", "start", "end", "unit"))


def _dated_company(company, cutoff):
    frozen = json.loads(canonical(company))
    facts = {}
    for metric, variants in frozen.get("facts", {}).items():
        kept = []
        for variant in variants:
            observations = [
                o
                for o in variant.get("observations", [])
                if _day(o["end"]) <= cutoff
                and (not o.get("filed") or _day(o["filed"]) <= cutoff)
            ]
            if observations:
                kept.append({**variant, "observations": observations})
        if kept:
            facts[metric] = kept
    frozen["facts"] = facts
    return frozen


def required_claims(company):
    """Choose three distinct metrics before any responses exist."""
    claims = []
    for metric in METRICS:
        observations = []
        for variant in company["facts"].get(metric, []):
            for obs in variant["observations"]:
                if type(obs.get("val")) not in (str, int, float):
                    continue
                value = Decimal(str(obs["val"]))
                if not value.is_finite():
                    continue
                observations.append(
                    {
                        "symbol": company["symbol"],
                        "metric": metric,
                        "tag": variant["tag"],
                        "start": obs.get("start"),
                        "end": obs["end"],
                        "unit": variant["unit"],
                        "value": format(value, "f"),
                    }
                )
        if observations:
            claims.append(
                sorted(
                    observations,
                    key=lambda c: (c["end"], c["start"] or "", c["tag"], c["unit"]),
                    reverse=True,
                )[0]
            )
        if len(claims) == 3:
            break
    return claims


def grade_trial(result, company, required):
    """Recompute exact source/schema checks; ignore any stored self-rating."""
    grade = grade_result(result, {company["symbol"]: company})
    present = set()
    if isinstance(result, dict) and isinstance(result.get("claims"), list):
        for claim in result["claims"]:
            try:
                present.add(_claim_key(claim))
            except (KeyError, TypeError):
                pass
    covered = sum(_claim_key(claim) in present for claim in required)
    return {
        "passed": bool(
            grade["source_check_passed"] and covered == 3 and len(required) == 3
        ),
        "required_claims_matched": covered,
        "source_errors": sorted(set(grade["errors"])),
    }


class PolicyLab:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.is_symlink():
            raise ValueError("Policy journal cannot be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        contract = {
            "rules": RULES,
            "policies": POLICIES,
            "system_sha256": _hash(SYSTEM),
            "evaluator_sha256": hashlib.sha256(
                (Path(__file__).read_text() + inspect.getsource(grade_result)).encode()
            ).hexdigest(),
        }
        with self.connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS policy_contract(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS policies(version INTEGER PRIMARY KEY,name TEXT NOT NULL,action TEXT NOT NULL,at TEXT NOT NULL,decision TEXT);
CREATE TABLE IF NOT EXISTS epochs(id TEXT PRIMARY KEY,contract TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trials(id TEXT PRIMARY KEY,epoch TEXT NOT NULL,version INTEGER NOT NULL,symbol TEXT NOT NULL,day TEXT NOT NULL,split TEXT NOT NULL,body TEXT NOT NULL,UNIQUE(version,symbol));
CREATE TABLE IF NOT EXISTS observations(trial TEXT NOT NULL,arm TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(trial,arm));
CREATE TABLE IF NOT EXISTS evaluations(id INTEGER PRIMARY KEY,version INTEGER NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS consumed(trial TEXT PRIMARY KEY,evaluation INTEGER NOT NULL);
""")
            for table in (
                "policy_contract",
                "policies",
                "epochs",
                "trials",
                "observations",
                "evaluations",
                "consumed",
            ):
                db.executescript(
                    f"CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'immutable policy evidence'); END; CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'immutable policy evidence'); END;"
                )
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT body FROM policy_contract WHERE id=1").fetchone()
            if old and old[0] != canonical(contract):
                raise ValueError(
                    "Frozen policy evaluator changed; explicit version migration required"
                )
            db.execute(
                "INSERT OR IGNORE INTO policy_contract VALUES(1,?)",
                (canonical(contract),),
            )
            db.execute(
                "INSERT OR IGNORE INTO policies VALUES(0,'memory_3','initial',?,NULL)",
                (datetime.now(timezone.utc).isoformat(),),
            )
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def policy(self):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM policies ORDER BY version DESC LIMIT 1"
            ).fetchone()
        return {"version": row["version"], "name": row["name"], **POLICIES[row["name"]]}

    def _planning_state(self, db, version):
        if version >= 2:
            return "rollback_complete", 0
        decisions = [
            json.loads(r[0])
            for r in db.execute(
                "SELECT body FROM evaluations WHERE version=?", (version,)
            )
        ]
        if (
            sum(d["action"] == "keep" for d in decisions)
            >= RULES["max_non_improving_looks"]
        ):
            return "comparison_exhausted", 0
        pending = db.execute(
            "SELECT count(*) FROM trials t LEFT JOIN consumed c ON c.trial=t.id WHERE t.version=? AND t.split='selection' AND c.trial IS NULL",
            (version,),
        ).fetchone()[0]
        remaining = max(0, RULES["pairs_per_look"] - pending)
        return ("collecting" if remaining else "awaiting_settlement"), remaining

    def plan_epoch(self, research, *, epoch_id, cutoff, max_pairs=4):
        """Freeze at most four paired trials; normal budget admission owns spend."""
        _identifier(epoch_id)
        day = _day(cutoff)
        captured = research.evidence.get("captured_at")
        if captured is not None and _day(captured) > day:
            raise ValueError(
                "A newly captured source bank cannot enter an earlier trial date"
            )
        if type(max_pairs) is not int or not 1 <= max_pairs <= 4:
            raise ValueError("At most four pairs per epoch")
        contract = {
            "evidence_sha256": _hash(research.evidence),
            "cutoff": cutoff,
            "max_pairs": max_pairs,
        }
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT contract FROM epochs WHERE id=?", (epoch_id,)
            ).fetchone()
            if old:
                if old[0] != canonical(contract):
                    raise ValueError("Epoch policy evidence changed")
            else:
                db.execute(
                    "INSERT INTO epochs VALUES(?,?)", (epoch_id, canonical(contract))
                )
                policy = db.execute(
                    "SELECT * FROM policies ORDER BY version DESC LIMIT 1"
                ).fetchone()
                _, remaining = self._planning_state(db, policy["version"])
                if remaining:
                    challenger = "fresh" if policy["name"] == "memory_3" else "memory_3"
                    seen = {
                        r[0]
                        for r in db.execute(
                            "SELECT symbol FROM trials WHERE version=?",
                            (policy["version"],),
                        )
                    }
                    daily = db.execute(
                        "SELECT count(*) FROM trials WHERE version=? AND day=? AND split='selection'",
                        (policy["version"], day),
                    ).fetchone()[0]
                    selected = []
                    audit = []
                    for symbol in sorted(
                        research.companies, key=lambda s: _hash([day, s])
                    ):
                        if symbol in seen:
                            continue
                        company = _dated_company(research.companies[symbol], day)
                        required = required_claims(company)
                        memory = research.latest(symbol, 3)
                        # No difference in inputs means no meaningful memory experiment.
                        if len(required) != 3 or not memory:
                            continue
                        row = (company, required, memory)
                        (audit if holdout(symbol) else selected).append(row)
                    selection_limit = min(
                        max_pairs - (1 if audit and max_pairs > 1 else 0),
                        max(0, RULES["selection_pairs_per_day"] - daily),
                        remaining,
                    )
                    chosen = [(row, "selection") for row in selected[:selection_limit]]
                    if chosen and audit and len(chosen) < max_pairs:
                        chosen.append((audit[0], "audit"))
                    for (company, required, memory), split in chosen:
                        symbol = company["symbol"]
                        identity = (
                            "policy-"
                            + _hash([epoch_id, policy["version"], symbol])[:32]
                        )
                        base = {
                            "task": "research",
                            "symbol": symbol,
                            "cutoff": cutoff,
                            "question": "Reconcile the three specified current accounting observations, distinguish their periods, and identify one evidence gap that could change an investment decision. Return the required exact source claims; explain derived reasoning only in thesis.",
                            "required_claims": [
                                {k: v for k, v in c.items() if k != "value"}
                                for c in required
                            ],
                            "evidence": company,
                        }
                        tasks = []
                        arms = [
                            ("incumbent", policy["name"]),
                            ("challenger", challenger),
                        ]
                        if int(_hash([day, symbol, "arm-order"]), 16) % 2:
                            arms.reverse()
                        for arm, name in arms:
                            question = canonical(
                                {
                                    **base,
                                    "prior_work": memory
                                    if POLICIES[name]["memory_limit"]
                                    else [],
                                }
                            )
                            body = body_for(
                                RULES["profile"],
                                PREFIX,
                                question,
                                cache="ordinary",
                                max_output=RULES["max_output"],
                                cache_key="pa-"
                                + hashlib.sha256(PREFIX.encode()).hexdigest()[:40],
                            )
                            tasks.append(
                                {
                                    "arm": arm,
                                    "name": name,
                                    "id": identity + "-" + arm,
                                    "question": question,
                                    "body_sha256": _hash(body),
                                }
                            )
                        frozen = {
                            "company": company,
                            "required": required,
                            "tasks": tasks,
                            "prefix": PREFIX,
                            "incumbent": policy["name"],
                            "challenger": challenger,
                            "profile": RULES["profile"],
                            "max_output": RULES["max_output"],
                        }
                        db.execute(
                            "INSERT INTO trials VALUES(?,?,?,?,?,?,?)",
                            (
                                identity,
                                epoch_id,
                                policy["version"],
                                symbol,
                                day,
                                split,
                                canonical(frozen),
                            ),
                        )
            rows = db.execute(
                "SELECT id,body FROM trials WHERE epoch=? ORDER BY id", (epoch_id,)
            ).fetchall()
        for row in rows:
            frozen = json.loads(row["body"])
            for task in frozen["tasks"]:
                research.add(
                    task["id"],
                    0,
                    "policy_trial",
                    frozen["company"]["symbol"],
                    frozen["profile"],
                    frozen["prefix"],
                    task["question"],
                    "ordinary",
                    max_output=frozen["max_output"],
                )
        return [row["id"] for row in rows]

    def reconcile(self, research, client):
        """Read terminal provider receipts, bind exact inputs and regrade locally."""
        with research.connect() as rdb:
            tasks = {
                row["id"]: dict(row)
                for row in rdb.execute("SELECT * FROM tasks WHERE kind='policy_trial'")
            }
        with self.connect() as db:
            rows = db.execute("SELECT * FROM trials").fetchall()
        recorded = 0
        for row in rows:
            frozen = json.loads(row["body"])
            for task in frozen["tasks"]:
                current = tasks.get(task["id"])
                if current is None:
                    continue
                if _hash(json.loads(current["body"])) != task["body_sha256"]:
                    raise ValueError("Frozen policy task changed")
                with client.connect() as requests:
                    request = requests.execute(
                        "SELECT * FROM requests WHERE task_id=?", (task["id"],)
                    ).fetchone()
                if (
                    request is None
                    or request["status"] not in TERMINAL
                    or request["cost"] is None
                ):
                    continue
                if (
                    request["profile"] != frozen["profile"]
                    or request["cache"] != "ordinary"
                    or _hash(json.loads(request["body"])) != task["body_sha256"]
                    or current["request_id"] not in (None, request["id"])
                ):
                    raise ValueError("Policy/provider identity mismatch")
                cost = _money(request["cost"])
                raw = json.loads(request["response"]) if request["response"] else {}
                result = answer_json(raw)
                grade = grade_trial(result, frozen["company"], frozen["required"])
                outcome = {
                    "passed": request["status"] == "completed" and grade["passed"],
                    "grade": grade,
                    "cost_usd": format(cost, "f"),
                    "status": request["status"],
                    "request_sha256": _hash(
                        [request["id"], request["response_id"], raw]
                    ),
                    "latency_seconds": max(0, request["updated"] - request["created"]),
                }
                with self.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    old = db.execute(
                        "SELECT body FROM observations WHERE trial=? AND arm=?",
                        (row["id"], task["arm"]),
                    ).fetchone()
                    if old and old[0] != canonical(outcome):
                        raise ValueError("Settled policy receipt changed")
                    if not old:
                        db.execute(
                            "INSERT INTO observations VALUES(?,?,?)",
                            (row["id"], task["arm"], canonical(outcome)),
                        )
                        recorded += 1
        return {"observations_recorded": recorded}

    def evaluate(self):
        """Consume disjoint prospective batches. Holdout audit never selects policy."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT * FROM policies ORDER BY version DESC LIMIT 1"
            ).fetchone()
            policy = {
                "version": current["version"],
                "name": current["name"],
                **POLICIES[current["name"]],
            }
            if current["version"] >= 2:
                return {
                    "action": "keep",
                    "reason": "rollback_complete",
                    "policy": policy,
                    "samples": 0,
                }
            rows = db.execute(
                "SELECT t.id,t.symbol,t.day,a.body incumbent,b.body challenger FROM trials t LEFT JOIN observations a ON a.trial=t.id AND a.arm='incumbent' LEFT JOIN observations b ON b.trial=t.id AND b.arm='challenger' LEFT JOIN consumed c ON c.trial=t.id WHERE t.version=? AND t.split='selection' AND c.trial IS NULL ORDER BY t.day,t.id",
                (current["version"],),
            ).fetchall()
            rows = rows[: RULES["pairs_per_look"]]
            completed = sum(
                row["incumbent"] is not None and row["challenger"] is not None
                for row in rows
            )
            if len(rows) < RULES["pairs_per_look"] or completed != len(rows):
                experiment_status, _ = self._planning_state(db, current["version"])
                return {
                    "action": "keep",
                    "reason": "comparison_exhausted"
                    if experiment_status == "comparison_exhausted"
                    else "insufficient_evidence",
                    "experiment_status": experiment_status,
                    "policy": policy,
                    "samples": completed,
                    "planned_pairs": len(rows),
                }
            pairs = [
                (row, json.loads(row["incumbent"]), json.loads(row["challenger"]))
                for row in rows
            ]
            wins = sum(b["passed"] and not a["passed"] for _, a, b in pairs)
            losses = sum(a["passed"] and not b["passed"] for _, a, b in pairs)
            passed = sum(b["passed"] for _, _, b in pairs)
            dates = sorted({row["day"] for row in rows})
            consistent = len(dates) >= RULES["min_dates"] and all(
                sum(
                    int(b["passed"]) - int(a["passed"])
                    for row, a, b in pairs
                    if row["day"] == day
                )
                > 0
                for day in dates
            )
            n = wins + losses
            probability = (
                Fraction(sum(comb(n, k) for k in range(wins, n + 1)), 2**n)
                if n
                else Fraction(1)
            )
            look = db.execute("SELECT count(*) FROM evaluations").fetchone()[0] + 1
            alpha = Fraction(RULES["family_alpha"]) / (look * (look + 1))
            incumbent_cost = sum(
                (_money(a["cost_usd"]) for _, a, _ in pairs), Decimal(0)
            )
            challenger_cost = sum(
                (_money(b["cost_usd"]) for _, _, b in pairs), Decimal(0)
            )
            qualifies = (
                consistent
                and wins - losses >= RULES["min_net_wins"]
                and Fraction(passed, len(rows)) >= Fraction(RULES["min_pass_rate"])
                and probability <= alpha
                and challenger_cost <= incumbent_cost * Decimal(RULES["max_cost_ratio"])
            )
            action = (
                ("promote" if current["version"] == 0 else "rollback")
                if qualifies
                else "keep"
            )
            decision = {
                "action": action,
                "reason": (
                    "forward_source_regression"
                    if action == "rollback"
                    else "paired_source_improvement"
                )
                if qualifies
                else "no_consistent_improvement",
                "policy": policy,
                "samples": len(rows),
                "companies": len({r["symbol"] for r in rows}),
                "dates": dates,
                "wins": wins,
                "losses": losses,
                "challenger_passes": passed,
                "one_sided_probability": str(float(probability)),
                "alpha_threshold": str(float(alpha)),
                "incumbent_cost_usd": format(incumbent_cost, "f"),
                "challenger_cost_usd": format(challenger_cost, "f"),
                "trial_ids": [r["id"] for r in rows],
                "look": look,
                "value": _comparison_value(pairs),
            }
            prior_looks = db.execute(
                "SELECT count(*) FROM evaluations WHERE version=?",
                (current["version"],),
            ).fetchone()[0]
            decision["experiment_status"] = (
                "rollback_complete"
                if action == "rollback"
                else "comparison_exhausted"
                if action == "keep"
                and prior_looks + 1 >= RULES["max_non_improving_looks"]
                else "collecting"
            )
            if qualifies:
                name = "fresh" if current["name"] == "memory_3" else "memory_3"
                decision["policy"] = {
                    "version": current["version"] + 1,
                    "name": name,
                    **POLICIES[name],
                }
                db.execute(
                    "INSERT INTO policies VALUES(?,?,?,?,?)",
                    (
                        current["version"] + 1,
                        name,
                        action,
                        datetime.now(timezone.utc).isoformat(),
                        canonical(decision),
                    ),
                )
            result = db.execute(
                "INSERT INTO evaluations(version,body) VALUES(?,?)",
                (current["version"], canonical(decision)),
            )
            db.executemany(
                "INSERT INTO consumed VALUES(?,?)",
                ((r["id"], result.lastrowid) for r in rows),
            )
            return decision

    def summary(self):
        with self.connect() as db:
            trials = db.execute(
                "SELECT split,count(*) n FROM trials GROUP BY split"
            ).fetchall()
            observations = db.execute(
                "SELECT t.split,t.version,o.arm,o.body FROM observations o JOIN trials t ON t.id=o.trial"
            ).fetchall()
            decisions = [
                json.loads(r[0])
                for r in db.execute("SELECT body FROM evaluations ORDER BY id")
            ]
            current = db.execute(
                "SELECT version FROM policies ORDER BY version DESC LIMIT 1"
            ).fetchone()[0]
            experiment_status, _ = self._planning_state(db, current)
        audit = {}
        for row in observations:
            if row["split"] != "audit":
                continue
            key = (row["version"], row["arm"])
            group = audit.setdefault(
                key,
                {
                    "version": row["version"],
                    "arm": row["arm"],
                    "samples": 0,
                    "passed": 0,
                    "cost_usd": Decimal(0),
                },
            )
            result = json.loads(row["body"])
            group["samples"] += 1
            group["passed"] += int(result["passed"])
            group["cost_usd"] += _money(result["cost_usd"])
        for group in audit.values():
            group["cost_usd"] = format(group["cost_usd"], "f")
        return {
            "schema_version": 1,
            "evaluator_version": RULES["version"],
            "audit_results": list(audit.values()),
            "policy": self.policy(),
            "trials": {r["split"]: r["n"] for r in trials},
            "observations": len(observations),
            "audit_observations": sum(r["split"] == "audit" for r in observations),
            "decisions": decisions,
            "experiment_status": experiment_status,
            "latest_selection_value": decisions[-1]["value"] if decisions else None,
            "settled_trial_cost_usd": format(
                sum(
                    (_money(json.loads(r["body"])["cost_usd"]) for r in observations),
                    Decimal(0),
                ),
                "f",
            ),
            "unsettled_or_unobserved_arms": 2 * sum(r["n"] for r in trials)
            - len(observations),
            "objective": "exact dated source reliability",
            "investment_skill_assessed": False,
        }
