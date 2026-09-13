"""Append-only public research summaries, never model reasoning or request bodies.

Publication uses explicit final-answer fields and independently matched SEC facts.
Request timestamps mean admission and terminal observation, not hidden model stages.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from .provider import ClosingConnection, NoRedirect, canonical

URL = "https://blakewoods.us/api/portfolio/research"
KINDS = {"company", "cache_control", "fresh_review", "window_pair", "allocation", "portfolio_critic", "memory_review"}
PROFILES = {"pro_flex", "pro_asap", "kimi_flex", "kimi_asap", "kimi_balanced", "glm_flex", "glm_balanced", "k3", "flash"}
TERMINAL = {"completed", "failed", "cancelled", "incomplete"}
# A second boundary even though research prompts contain public company evidence only.
PRIVATE = re.compile(r"https?://|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b(?:bearer|password|api[ _-]?key|client[ _-]?secret|access[ _-]?token|refresh[ _-]?token|account[ _-]?(?:number|id))\b|\b(?:sk|sail)_[A-Za-z0-9_-]{12,}|<[^>]*>", re.I)


def _text(value, limit):
    if not isinstance(value, str) or PRIVATE.search(value):
        return None
    value = " ".join(value.split())
    if not value or any(ord(c) < 32 for c in value):
        return None
    return value[:limit]


def _stamp(value):
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _excerpt(value, limit=120):
    first = re.split(r"(?<=[.!?])\s+", value)[0]
    if len(first) <= limit:
        return first
    return first[:limit - 1].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


def _number(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) >= Decimal("1e24"):
            return None
        result = format(amount, "f")
        if len(result) > 48 or ("." in result and len(result.split(".")[1]) > 14):
            return None
        return result
    except (InvalidOperation, TypeError, ValueError):
        return None


def _claim(claim, companies):
    try:
        company = companies[claim["symbol"]]
        value = _number(claim["value"])
        if value is None:
            return None
        for variant in company["facts"].get(claim["metric"], []):
            if variant["tag"] != claim["tag"] or variant["unit"] != claim["unit"]:
                continue
            for observation in variant["observations"]:
                if observation.get("start") != claim["start"] or observation["end"] != claim["end"] or Decimal(str(observation["val"])) != Decimal(value):
                    continue
                accession = observation.get("accn", "")
                if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                    continue
                cik = int(company["cik"])
                return {
                    "symbol": claim["symbol"], "metric": claim["metric"], "tag": claim["tag"],
                    "start": claim["start"], "end": claim["end"], "value": value, "unit": claim["unit"],
                    "source": {"title": f"{claim['symbol']} · {observation.get('form', 'SEC filing')}",
                               "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{accession}-index.html"},
                }
    except (KeyError, TypeError, ValueError, InvalidOperation):
        pass
    return None


def public_record(task, request, companies, *, run_id):
    """Project one final task; failed checks expose a typed failure, not bad prose."""
    if task["kind"] not in KINDS or task["profile"] not in PROFILES or request["status"] not in TERMINAL:
        return None
    if task["status"] not in {"complete", "failed"}:
        return None
    # Publish only settled terminal observations. A later cost reconciliation
    # must not change an already-public record or block subsequent entries.
    settled_cost = _number(request["cost"]) if request["cost"] is not None else None
    if settled_cost is None or Decimal(settled_cost) < 0:
        return None
    try:
        result, grade = json.loads(task["result"] or "null"), json.loads(task["grade"] or "null")
        grade = grade if isinstance(grade, dict) else {}
        passed = request["status"] == "completed" and grade.get("source_check_passed") is True
        if not isinstance(result, dict):
            result = {}
        case = _text(result.get("thesis"), 1600) if passed else None
        # Exact schema prevents exporting accidentally injected fields from a model.
        expected = {"thesis", "claims", "questions", "targets", "confidence", "abstain_reason"}
        if task["kind"] == "portfolio_critic":
            expected |= {"review_verdict", "proposal_sha256"}
        if set(result) != expected:
            passed, case = False, None
        claims = [c for raw in result.get("claims", []) if (c := _claim(raw, companies)) is not None][:6] if passed else []
        if passed and (case is None or len(claims) < 3):
            passed, case, claims = False, None, []
        questions = []
        if passed:
            for question in result.get("questions", []):
                text = _text(question.get("question"), 240) if isinstance(question, dict) else None
                if text and question.get("symbol") in companies:
                    questions.append({"symbol": question["symbol"], "question": text})
        action, targets = "research", []
        if passed and task["kind"] == "allocation":
            action = "proposal"
            for target in result.get("targets", []):
                weight = _number(target.get("weight"))
                if target.get("symbol") in companies and weight is not None and 0 < Decimal(weight) <= Decimal(".2"):
                    targets.append({"symbol": target["symbol"], "weight": weight})
        elif passed and task["kind"] == "portfolio_critic":
            action = result.get("review_verdict") if result.get("review_verdict") in {"approve", "revise", "abstain"} else "abstain"
        abstain = _text(result.get("abstain_reason"), 500) if passed else None
        outcome = "passed" if passed else "unverified" if request["status"] == "completed" else "failed"
        title = _excerpt(case) if case else "Research did not pass source checks." if outcome == "unverified" else "Research request did not complete."
        if passed and task["kind"] == "portfolio_critic":
            title = {"approve": "Reviewer approved the proposed allocation.", "revise": "Reviewer requested changes to the proposed allocation.", "abstain": "Reviewer declined to approve the proposed allocation."}[action]
        started, completed = float(request["created"]), float(request["updated"])
        if completed < started:
            return None
        return {
            "schema_version": 1, "id": hashlib.sha256(canonical([run_id, task["id"]]).encode()).hexdigest(),
            "started_at": _stamp(started), "completed_at": _stamp(completed),
            "symbol": task["symbol"] if task["symbol"] in companies else None,
            "kind": task["kind"], "profile": task["profile"], "outcome": outcome,
            "title": title, "case": case, "questions": questions[:3], "claims": claims,
            "decision": {"action": action, "targets": targets[:100], "abstain_reason": abstain},
            "metrics": {"source_checks_passed": passed, "claims_checked": min(50, max(0, int(grade.get("claims_checked", 0)))),
                        "cost_usd": settled_cost,
                        "latency_seconds": round(completed - started, 3)},
        }
    except (ValueError, KeyError, TypeError, OverflowError):
        return None


def export_records(research_path, requests_path, evidence, *, run_id):
    """Yield final public records with no request body/response/credential reads."""
    companies = {company["symbol"]: company for company in evidence["companies"]}
    with sqlite3.connect(f"{Path(research_path).resolve().as_uri()}?mode=ro", uri=True, factory=ClosingConnection) as research:
        with sqlite3.connect(f"{Path(requests_path).resolve().as_uri()}?mode=ro", uri=True, factory=ClosingConnection) as requests:
            research.row_factory = requests.row_factory = sqlite3.Row
            for task in research.execute("SELECT id,kind,symbol,profile,status,result,grade FROM tasks WHERE status IN ('complete','failed') ORDER BY created,id"):
                request = requests.execute("SELECT status,created,updated,cost FROM requests WHERE task_id=?", (task["id"],)).fetchone()
                if request is not None:
                    record = public_record(task, request, companies, run_id=run_id)
                    if record is not None:
                        yield record


def publish_journal(config, research, client, *, opener=None):
    """Publish <=20 records per checkpoint, with replay-safe private local receipts.

    Unknown network outcomes retry the same immutable batch on the next checkpoint.
    The authenticated server accepts identical retries and rejects changed records.
    Errors are typed; provider prose and transport bodies never enter public state.
    """
    result = {"published": 0, "pending": 0, "error": None}
    if not config.get("publish_url"):
        return result
    if config["publish_url"] != "https://blakewoods.us/api/portfolio/state":
        return {**result, "error": "invalid_destination"}
    receipt_path = Path(config["state_dir"]) / "journal-publications.sqlite"
    db = None
    try:
        headers = {"Content-Type": "application/json", "User-Agent": "Blake Woods Portfolio Agent"}
        if not config.get("injected_auth"):
            token_path = Path(config.get("publish_token_path", ""))
            if not token_path.is_file() or token_path.stat().st_mode & 0o077:
                return {**result, "error": "private_credential_unavailable"}
            headers["Authorization"] = "Bearer " + token_path.read_text().strip()
        receipt_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(receipt_path, timeout=20)
        receipt_path.chmod(0o600)
        db.execute("CREATE TABLE IF NOT EXISTS publications(id TEXT PRIMARY KEY, body TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0)")
        for record in export_records(research.path, client.path, research.evidence, run_id=config["run_id"]):
            old = db.execute("SELECT body FROM publications WHERE id=?", (record["id"],)).fetchone()
            body = canonical(record)
            if old and old[0] != body:
                return {**result, "error": "immutable_record_changed"}
            db.execute("INSERT OR IGNORE INTO publications(id,body) VALUES(?,?)", (record["id"], body))
        db.commit()
        rows = db.execute("SELECT id,body FROM publications WHERE published=0 ORDER BY rowid LIMIT 20").fetchall()
        result["pending"] = db.execute("SELECT COUNT(*) FROM publications WHERE published=0").fetchone()[0]
        if not rows:
            return result
        body = canonical({"schema_version": 1, "entries": [json.loads(row[1]) for row in rows]}).encode()
        if len(body) > 262144:
            return {**result, "error": "publication_envelope_exceeded"}
        request = Request(URL, data=body, headers=headers, method="POST")
        with (opener or build_opener(NoRedirect)).open(request, timeout=20) as response:
            if response.status != 200:
                return {**result, "error": "publication_rejected"}
        db.executemany("UPDATE publications SET published=1 WHERE id=?", [(row[0],) for row in rows])
        db.commit()
        return {"published": len(rows), "pending": result["pending"] - len(rows), "error": None}
    except HTTPError as error:
        code = error.code
        error.close()
        return {**result, "error": "http_" + str(code)}
    except Exception:
        return {**result, "error": "publication_unconfirmed"}
    finally:
        if db is not None:
            db.close()
