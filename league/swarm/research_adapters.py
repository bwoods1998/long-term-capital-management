"""Credential-free adapters for an explicitly injected, scoped research broker.

These adapters never construct a Provider, a gateway router or a Sailbox client.
The host broker owns pricing, daily admission, resources and one-shot dispatch slots.
Controller receipts retain uncertain requests and permit only free terminal-cache recovery.
Gym results remain private research evidence; stock callers and restart recovery
retain original trial accounting.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import threading
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from .models import ModelError, extract_json
from .pool import GymJob, PoolError

_STATE = "research_adapter_receipts_v1"
_EVENT = "swarm.research_adapter"
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _json(value: Any) -> Any:
    """Copy only serializable JSON values; no callables, credentials or client objects."""
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _decode(value: str):
    def pairs(items):
        out = {}
        for key, item in items:
            if key in out:
                raise ValueError("duplicate private research receipt field")
            out[key] = item
        return out

    def nonfinite(value):
        raise ValueError("nonfinite private research receipt value")

    return json.loads(value, object_pairs_hook=pairs, parse_constant=nonfinite)


def _load(store) -> dict[str, Any]:
    state = {}
    for row in store._all("SELECT payload FROM events WHERE kind=? ORDER BY seq", (_EVENT,)):
        receipt = _decode(row["payload"])
        if not isinstance(receipt, dict) or receipt.get("action") not in ("claimed", "completed", "accounted", "rejected"):
            raise ValueError("invalid private research receipt history")
        identity = receipt.get("identity")
        if not _text(identity):
            raise ValueError("invalid private research request identity")
        if receipt["action"] == "claimed":
            if identity in state or set(receipt) != {"action", "identity", "sha", "request"} or not isinstance(receipt["request"], dict):
                raise ValueError("duplicate or invalid private research claim")
            if receipt["sha"] != _digest(receipt["request"]):
                raise ValueError("private research claim body changed")
            state[identity] = {"sha": receipt["sha"], "request": receipt["request"], "result": None, "accounted": False, "counts_before": None, "rejected": None}
        elif receipt["action"] == "completed":
            if identity not in state or state[identity]["result"] is not None or set(receipt) != {"action", "identity", "sha", "result", "counts_before"}:
                raise ValueError("terminal research receipt has no original claim")
            if receipt["sha"] != state[identity]["sha"] or not isinstance(receipt["result"], dict):
                raise ValueError("terminal research receipt changed its request")
            state[identity]["result"] = receipt["result"]
            before = receipt["counts_before"]
            if identity.startswith("gym:") and (not isinstance(before, dict) or set(before) != {"primary", "twin"}
                    or any(type(value) is not int or value < 0 for value in before.values())):
                raise ValueError("Gym completion has no original trial totals")
            if identity.startswith("model:") and before is not None:
                raise ValueError("model completion changed research trials")
            state[identity]["counts_before"] = before
        elif receipt["action"] == "rejected":
            if set(receipt) != {"action", "identity", "sha", "document"} or identity not in state or not identity.startswith("gym:"):
                raise ValueError("invalid rejected research receipt")
            row = state[identity]
            if row["sha"] != receipt["sha"] or row["result"] is not None or row["rejected"] is not None or not isinstance(receipt["document"], dict):
                raise ValueError("rejected research receipt lacks its original request")
            row["rejected"] = receipt["document"]
        else:
            if set(receipt) != {"action", "identity", "sha"} or identity not in state or not identity.startswith("gym:"):
                raise ValueError("invalid research accounting receipt")
            row = state[identity]
            if row["sha"] != receipt["sha"] or row["result"] is None or row["accounted"]:
                raise ValueError("research accounting lacks its original terminal receipt")
            row["accounted"] = True
    raw = store._one("SELECT value FROM kv WHERE key=?", (_STATE,))
    if raw is None:
        if state:
            raise ValueError("private research request receipts were lost")
    elif _digest(_decode(raw["value"])) != _digest(state):
        raise ValueError("private research receipts differ from immutable history")
    return state


def _claim(store, kind: str, key: str, payload: Mapping[str, Any]):
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("invalid research request key")
    identity, sha = kind + ":" + key, _digest(payload)
    with store.atomic():
        state = _load(store)
        if identity in state:
            if state[identity]["sha"] != sha:
                raise ValueError("research request key cannot change its body")
            return identity, sha, state[identity]["result"], False
        request = _json(payload)
        state[identity] = {"sha": sha, "request": request, "result": None, "accounted": False, "counts_before": None, "rejected": None}
        store.event(_EVENT, None, {"action": "claimed", "identity": identity, "sha": sha, "request": request})
        store.put(_STATE, state)
        return identity, sha, None, True


def _complete(store, identity: str, sha: str, result: Mapping[str, Any], *, cost: Decimal | None = None,
              family: str | None = None, accrued_at: float | None = None, counts_before=None):
    result = _json(result)
    with store.atomic():
        state = _load(store)
        row = state.get(identity)
        if row is None or row["sha"] != sha:
            raise ValueError("research completion has no original claim")
        if row["result"] is not None:
            if _digest(row["result"]) != _digest(result):
                raise ValueError("research terminal receipt changed")
            return
        if cost is not None and cost:
            # Public-base SwarmStore has no add_spend(at=). The host supplies a UTC
            # accrual day, so midnight labels day-granularity evidence, not an invented time.
            day = dt.datetime.fromtimestamp(accrued_at, dt.timezone.utc).isoformat().replace("+00:00", "Z")
            detail = {"research_request": identity, "accrual_granularity": "UTC day", "vendor_actual": True}
            store._exec("INSERT INTO spend(at,epoch,kind,family,usd,detail) VALUES(?,?,?,?,?,?)",
                        (day, accrued_at, "sail_model", family, float(cost), json.dumps(detail, sort_keys=True)))
            if family:
                store.bump(family, spent_usd=float(cost))
        row["result"] = result
        row["counts_before"] = counts_before
        store.event(_EVENT, None, {"action": "completed", "identity": identity, "sha": sha, "result": result, "counts_before": counts_before})
        store.put(_STATE, state)


def _recover(broker, key: str, kind: str):
    cache = getattr(broker, "cached_result", None)
    if cache is None:
        raise ValueError("research request is unresolved; redispatch is forbidden")
    result = cache(key, kind=kind)
    if result is None:
        raise ValueError("research request is unresolved; redispatch is forbidden")
    return result


def _reject(store, identity, document):
    """Keep scoped counter-evidence privately without asserting completion or qualification."""
    if not isinstance(document, dict):
        return
    document = _json(document)
    with store.atomic():
        state = _load(store)
        row = state[identity]
        if row["result"] is None and row["rejected"] is None:
            row["rejected"] = document
            store.event(_EVENT, None, {"action": "rejected", "identity": identity, "sha": row["sha"], "document": document})
            store.put(_STATE, state)


def expected_evaluation(settings, *, checkpoint, bundle, execution, roots):
    """Minimal explicit controller/host manifest; no environment or provider readers."""
    from . import settings as settings_mod
    capital = Decimal(str(settings.get("gym", {}).get("capital", 10000)))
    if isinstance(settings.get("gym", {}).get("capital"), bool) or not capital.is_finite() or capital <= 0:
        raise ValueError("invalid explicit simulated research capital")
    if not isinstance(execution, str) or not re.fullmatch(r"[a-f0-9]{64}", execution):
        raise ValueError("reviewed research execution fingerprint is required")
    return {"image": checkpoint, "bundle": bundle, "execution": execution, "roots": list(roots), "capital": format(capital.normalize(), "f"),
            "train_first": settings_mod.train_from(settings).isoformat()}


def reviewed_tools(tools):
    """The stock local tools in the exact Responses shape reviewed by the host."""
    if tools is None:
        return None
    if not isinstance(tools, (list, tuple)):
        raise ValueError("reviewed tools must be a list of local function definitions")
    result = []
    for tool in tools:
        if (not isinstance(tool, Mapping) or set(tool) - {"type", "name", "description", "parameters", "strict"}
                or tool.get("type", "function") != "function" or not _text(tool.get("name"))
                or not isinstance(tool.get("description"), str) or not isinstance(tool.get("parameters"), Mapping)
                or ("strict" in tool and type(tool["strict"]) is not bool)):
            raise ValueError("only reviewed local function definitions are accepted")
        normalized = dict(tool)
        if "type" not in normalized:
            # Match the existing Provider._tool_entry contract for stock tools.
            normalized.update(type="function", strict=False)
        result.append(_json(normalized))
    return result


@dataclass(frozen=True)
class ResearchModelResponse:
    """Stock response fields plus an explicitly separate reserved cost ceiling."""
    response: Any
    cost_upper_usd: Decimal | None
    cost_status: str

    def __getattr__(self, name):
        return getattr(self.response, name)


def record_research_cost(out, response):
    """Report unknown actuals without booking a reservation as vendor spending."""
    previous = Decimal(str(out.get("cost_actual_known_usd", out.get("cost_usd") or 0)))
    upper = Decimal(str(out.get("cost_upper_usd", previous)))
    actual = response.cost_usd
    bound = response.cost_upper_usd
    known = previous + (actual if actual is not None else Decimal(0))
    out["cost_actual_known_usd"] = format(known, "f")
    out["cost_upper_usd"] = format(upper + (bound if bound is not None else actual), "f")
    unknown = out.get("cost_usd") is None or actual is None
    out["cost_usd"] = None if unknown else round(float(known), 6)
    out["cost_status"] = "unknown" if unknown else "vendor_actual"


def record_research_failure(out, exc):
    """Retain isolated terminal cost evidence in actor error reports only."""
    if not isinstance(exc, ModelError):
        return
    for row in exc.billed:
        if (not isinstance(row, dict) or row.get("route") != "sail" or "cost_upper_usd" not in row
                or row.get("cost_status") not in ("unknown", "vendor_actual")):
            continue
        try:
            upper = Decimal(row["cost_upper_usd"]) if row["cost_upper_usd"] is not None else None
            actual = Decimal(str(row["cost_usd"])) if row.get("cost_usd") is not None else None
            if (upper is not None and (not upper.is_finite() or not 0 < upper <= 25) or actual is None and upper is None
                    or actual is not None and (not actual.is_finite() or not 0 <= actual <= 25
                                               or upper is not None and actual > upper)
                    or row["cost_status"] != ("unknown" if actual is None else "vendor_actual")):
                continue
        except (ValueError, TypeError, ArithmeticError):
            continue
        out.setdefault("cost_usd", 0.0)
        record_research_cost(out, SimpleNamespace(cost_usd=actual, cost_upper_usd=upper))
        if "model_calls" in out:
            out["model_calls"] += 1
        out.setdefault("billed", []).append(dict(row))


class ResearchModelRouter:
    """Stock research .sail/.ask interface; every paid route belongs to the broker."""

    def __init__(self, store, broker, *, settings: Mapping[str, Any]):
        self.store, self.broker, self.settings = store, broker, settings

    def sail(self, profile: str, items: Sequence[Any], *, family: str, key: str, tools=None,
             effort="low", max_output=8000, cache_key=None, tool_choice="auto", cap_usd_day=None,
             kind="sail_model"):
        if kind != "sail_model" or not _text(profile) or not _text(family):
            raise ModelError("unsupported isolated model request", kind="line")
        try:
            payload = _json({"profile": profile, "items": list(items), "tools": reviewed_tools(tools),
                             "effort": effort, "max_output": max_output, "cache_key": cache_key,
                             "tool_choice": tool_choice})
            identity, sha, result, fresh = _claim(self.store, "model", key, payload)
            if result is None:
                result = (self.broker.evaluate(profile, payload["items"], key=key, tools=payload["tools"],
                                               effort=effort, max_output=max_output, cache_key=cache_key,
                                               tool_choice=tool_choice) if fresh else _recover(self.broker, key, "model"))
            if not isinstance(result, dict) or result.get("profile") != profile or result.get("request_key") != key:
                raise ValueError("model receipt does not match its scoped request")
            if result.get("status") not in ("completed", "succeeded", "incomplete", "failed", "cancelled"):
                raise ValueError("model result is not terminal")
            value = result.get("cost_usd")
            cost = Decimal(value) if isinstance(value, str) else None
            if value is not None and cost is None:
                raise ValueError("invalid model cost evidence")
            if cost is not None and (not cost.is_finite() or cost < 0 or cost > 25):
                raise ValueError("model cost is outside the unified ceiling")
            upper_value = result.get("cost_upper_usd")
            upper = Decimal(upper_value) if isinstance(upper_value, str) else None
            if (upper_value is not None and upper is None or upper is not None
                    and (not upper.is_finite() or not 0 < upper <= 25 or cost is not None and cost > upper)):
                raise ValueError("invalid original model reservation")
            cost_status = "unknown" if cost is None else "vendor_actual"
            if result.get("cost_status", cost_status) != cost_status:
                raise ValueError("model cost evidence status differs")
            day = result.get("accrued_day")
            at = None
            if cost is None:
                if upper is None or day is not None:
                    raise ValueError("unknown model invoice needs its original reservation and no invented accrual day")
            else:
                date = dt.date.fromisoformat(day)
                if day != date.isoformat():
                    raise ValueError("model receipt has no exact accrual day")
                at = dt.datetime.combine(date, dt.time(), dt.timezone.utc).timestamp()
                now = self.store.clock()
                if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now) or not 0 <= at <= now:
                    raise ValueError("model receipt accrual day is invalid")
            booked_family = family.split(":", 1)[0]
            if self.store.family(booked_family) is None:
                booked_family = None
            _complete(self.store, identity, sha, result, cost=cost, family=booked_family, accrued_at=at)
        except Exception:
            # Exception text comes from an injected host/client: never expose credentials or raw HTTP bodies.
            raise ModelError("isolated broker model request unresolved or refused", kind="line") from None
        from ltcm.provider import ProviderResponse, function_calls_of, output_items_of, output_text_of, reasoning_summaries_of
        billed = [{"route": "sail", "cost_usd": format(cost, "f") if cost is not None else None,
                   "cost_upper_usd": format(upper, "f") if upper is not None else None,
                   "cost_status": cost_status, "request_key": key, "status": result["status"]}]
        if result["status"] in ("failed", "cancelled"):
            raise ModelError("isolated model terminal request failed", billed=billed)
        try:
            details, usage = result.get("incomplete_details"), result.get("usage")
            if details is not None and not isinstance(details, dict) or usage is not None and not isinstance(usage, dict):
                raise ValueError("invalid terminal model fields")
            reason = (details or {}).get("reason")
            status = "completed" if result["status"] == "succeeded" else result["status"]
            response = ProviderResponse(key, result.get("id"), status, output_text_of(result), function_calls_of(result),
                                        reasoning_summaries_of(result), output_items_of(result), dict(usage or {}),
                                        cost, result["status"] == "incomplete", reason if isinstance(reason, str) else None)
        except Exception:
            raise ModelError("isolated model terminal fields refused", billed=billed, kind="line") from None
        return ResearchModelResponse(response, upper, cost_status)

    def ask(self, *, role, system, user, family, key, openai_model=None, sail_profile=None, max_output=8000,
            effort="medium", desk=None, **kwargs):
        if not sail_profile:
            raise ModelError("isolated role has no explicitly allowed broker profile", kind="off")
        response = self.sail(sail_profile, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                             family=desk or family or "swarm", key=key, effort=effort, max_output=max_output,
                             cache_key=f"swarm-{role}")
        return {"text": response.output_text, "json": extract_json(response.output_text), "route": "sail",
                "model": sail_profile, "cost_usd": float(response.cost_usd) if response.cost_usd is not None else None,
                "cost_upper_usd": format(response.cost_upper_usd, "f") if response.cost_upper_usd is not None else None,
                "cost_status": response.cost_status, "fallback_reasons": [],
                "truncated": response.incomplete, "incomplete_reason": response.incomplete_reason, "usage": response.usage}

    def claude_enabled(self, role):
        return False

    def claude_turn(self, **kwargs):
        raise ModelError("gateway model routes are unavailable in isolated research", kind="off")

    def openai_room(self):
        return 0.0

    def claude_room(self):
        return 0.0

    def compact(self, **kwargs):
        return 0

    def settle_holds(self):
        return 0

    def drain_fallbacks(self):
        return {}


class ResearchGymPool:
    """Stock pool interface over broker-owned Train/Validation jobs only.

    A bounded caller wait can expire while the host finishes. Its eventual result still
    reaches the original late callback, so an actual evaluation is never discarded.
    """

    def __init__(self, store, broker, *, checkpoint: str, bundle: str, execution: str, train_first: str, roots: Sequence[str],
                 settings: Mapping[str, Any] | None = None):
        if not _text(checkpoint) or not _text(bundle) or not roots or len(set(roots)) != len(roots) or not all(_text(root) for root in roots):
            raise ValueError("isolated Gym manifest is required")
        if not isinstance(execution, str) or not re.fullmatch(r"[a-f0-9]{64}", execution):
            raise ValueError("reviewed research execution fingerprint is required")
        first = dt.date.fromisoformat(train_first)
        if not dt.date(2017, 1, 3) <= first <= dt.date(2024, 12, 31) or first.isoformat() != train_first:
            raise ValueError("invalid isolated Train manifest")
        self.store, self.broker = store, broker
        self.settings = _json(settings or {})
        self.checkpoint, self.version, self.execution, self.train_first, self.roots = checkpoint, bundle, execution, train_first, tuple(roots)
        self._lock = threading.RLock()
        self._wake = threading.Condition(self._lock)
        self._jobs: dict[int, tuple[GymJob, dict[str, Any], str]] = {}
        self._running: set[int] = set()
        self._queue: list[int] = []
        self._stopping = False
        self._worker = threading.Thread(target=self._dispatch, name="research-gym-dispatch", daemon=True)
        self._worker.start()

    def _request(self, payload):
        return {"job": payload, "gym_image": self.checkpoint, "gym_bundle": self.version, "gym_execution": self.execution,
                "execution": self._execution(payload)}

    def _execution(self, payload):
        gym = self.settings.get("gym", {})
        capital = Decimal(str(gym.get("capital", 10000)))
        workers = gym.get("workers", 8)
        if isinstance(gym.get("capital"), bool) or not capital.is_finite() or capital <= 0 or type(workers) is not int or workers < 1:
            raise ValueError("invalid explicit research execution settings")
        return {"capital": format(capital.normalize(), "f"), "workers": workers,
                **{key: payload[key] for key in ("split", "window", "start", "end", "roots", "stress")}}

    def _current(self, request):
        from . import settings as settings_mod
        payload = request["job"]
        split = (settings_mod.train_split(self.settings, dt.date.fromisoformat(payload["start"])) if payload["window"] == "train"
                 else self.settings.get("gym", {}).get("validation_split", 1))
        current = self._execution({**payload, "split": split})
        return request["gym_image"] == self.checkpoint and request["gym_bundle"] == self.version and request["gym_execution"] == self.execution \
            and _digest(current) == _digest(request["execution"])

    @staticmethod
    def _result(document, request):
        payload = request["job"]
        if not isinstance(document, dict) or document.get("gym_image") != request["gym_image"] or document.get("gym_bundle") != request["gym_bundle"]:
            raise ValueError("Gym receipt has another image or bundle")
        if document.get("gym_execution") != request["gym_execution"]:
            raise ValueError("Gym receipt has another execution fingerprint")
        if not isinstance(document.get("execution"), dict) or _digest(document["execution"]) != _digest(request["execution"]):
            raise ValueError("Gym receipt has another execution configuration")
        results = document.get("results")
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            raise ValueError("Gym receipt has no single result")
        result = _json(results[0])
        if result.get("window") != payload["window"] or set(result.get("roots") or []) != set(payload["roots"]) or result.get("stress") != payload["stress"]:
            raise ValueError("Gym result has another research scope")
        if not _text(result.get("run_id")) or isinstance(result.get("trials"), bool) or not isinstance(result.get("trials"), int) or result["trials"] < 0:
            raise ValueError("Gym result has no actual evaluation receipt")
        result.update(gym_image=request["gym_image"], gym_bundle=request["gym_bundle"], gym_execution=request["gym_execution"],
                      research_execution=request["execution"])
        if payload["window"] == "train":
            result["train_from"] = payload["start"]
        return result

    def _recorded(self, family, result):
        # SwarmStore can scope a reused worker hash when the evaluator changes.
        from .store import code_sha, dumps
        run_id = result["run_id"]
        scope = code_sha(dumps({"worker_run_id": run_id, "family": family,
                               "evaluator": (result["gym_image"], result["gym_bundle"])}))
        aliases = (run_id, f"{run_id}-{family}"[:64], f"{run_id[:31]}-{scope[:32]}")
        for candidate in aliases:
            row = self.store.run(candidate)
            if row and row["family"] == family and all(row["summary"].get(k) == result[k] for k in ("gym_image", "gym_bundle")):
                return row
        return None

    def _counts(self, family, result):
        primary = self._recorded(family, result)
        twin = self.store.run((primary["run_id"] if primary else result["run_id"]) + "-s15")
        return {"primary": int(primary["trials"]) if primary else 0, "twin": int(twin["trials"]) if twin and twin["family"] == family else 0}

    def recover(self, *, researcher, tournament):
        """Free terminal-cache recovery and atomic original-trial bookkeeping only.

        A restart does not recreate a callback. Immutable original job metadata and
        stock research scorers restore its receipt, without redispatch or new looks.
        """
        recovered = unresolved = 0
        with self.store.atomic():
            pending = [(identity, _json(row)) for identity, row in _load(self.store).items()
                       if identity.startswith("gym:") and not row["accounted"]]
        for identity, row in pending:
            key = identity.split(":", 1)[1]
            with self._lock:
                if any(job.id in self._running or not job.done.is_set() for job, _, current in self._jobs.values() if current == key):
                    continue
            try:
                request = row["request"]
                document = row["result"] if row["result"] is not None else _recover(self.broker, key, "gym")
                try:
                    result = self._result(document, request)
                except Exception:
                    _reject(self.store, identity, document)
                    raise
                _complete(self.store, identity, row["sha"], document, counts_before=self._counts(request["job"]["family"], result))
                payload = request["job"]
                current = self._current(request)
                fid, version = payload["family"], payload["version"]
                job = GymJob(**{**payload, "roots": tuple(payload["roots"])})
                job.span = payload["start"] if job.window == "train" else None
                with self.store.atomic():
                    state = _load(self.store)
                    if state[identity]["accounted"]:
                        continue
                    family = self.store.family(fid)
                    if family is None or version is not None and self.store.version(fid, version) is None:
                        raise ValueError("original research target is missing")
                    existing = self._recorded(fid, result)
                    before = state[identity]["counts_before"]
                    required = before["primary"] + result["trials"]
                    if existing is not None and existing["trials"] < before["primary"]:
                        raise ValueError("original trial totals decreased")
                    missing = required - (existing["trials"] if existing else 0)
                    years = float((result.get("summary") or {}).get("days") or 0) / 252 * len(job.roots)
                    key_for_run = researcher._result_key(job, result) if current else None
                    if job.window == "validation":
                        if version is None:
                            raise ValueError("Validation has no original version")
                        if existing is None and current:
                            tournament.judge(fid, version, result)
                        else:
                            if existing is None or missing > 0:
                                existing = self.store.add_run(fid, version, {**result, "trials": max(0, missing)}, window="validation", stress=1,
                                                              purpose="validation", program_years=years)
                            twin = result.get("stress_1.5")
                            prior_twin = self.store.run(existing["run_id"] + "-s15")
                            if prior_twin is not None and prior_twin["trials"] < before["twin"]:
                                raise ValueError("original stress trial totals decreased")
                            missing_twin = before["twin"] + 1 - (prior_twin["trials"] if prior_twin else 0)
                            if isinstance(twin, dict) and missing_twin > 0:
                                self.store.add_run(fid, version, {"run_id": existing["run_id"] + "-s15", "status": twin.get("status") or "ok",
                                                   "trials": missing_twin, "summary": twin}, window="validation", stress=1.5,
                                                   purpose="validation", program_years=years)
                            if current and (family.get("validated_version") != version or (family.get("state") or {}).get("validation_image") != result["gym_image"] \
                                    or (family.get("state") or {}).get("validation_bundle") != result["gym_bundle"]):
                                # Complete an interrupted verdict with no second primary/twin count.
                                judged = tournament.judge(fid, version, result, record=False)
                                if judged is not None:
                                    self.store.bump(fid, validations=1)
                                    current = self.store.family(fid)
                                    self.store.set_state(fid, validated_trials=int(current["trials"]), dormant_cycles=0)
                    elif existing is None or missing > 0:
                        window = job.purpose if job.purpose in ("probe", "mechanism") else "train"
                        recorded = researcher._with_score(result, job.stress)[0] if current and job.purpose == "train" else result
                        self.store.add_run(fid, version, {**recorded, "trials": max(0, missing)}, window=window, stress=job.stress,
                                           purpose=job.purpose, program_years=years, key=key_for_run)
                    # Figures can be restored without charging an already recorded evaluation.
                    if current and job.purpose == "robustness" and version is not None:
                        label = "mid" if job.stress == 0 else "stress_1.5" if job.stress == 1.5 else "drift"
                        robustness = (family.get("state") or {}).get("robustness") or {}
                        figures = (robustness.get(str(version)) or {}).get(label)
                        if not isinstance(figures, dict) or figures.get("gym_image") != result["gym_image"] or figures.get("gym_bundle") != result["gym_bundle"]:
                            # Stock helper may submit follow-up jobs on a demotion. Recovery blocks
                            # those submissions; only a later admitted ordinary cycle can run them.
                            with self._lock:
                                self._recovering = True
                            try:
                                researcher.robust_landed(fid, version, label, job.stress, {**result, "trials": 0}, key=key_for_run)
                            finally:
                                with self._lock:
                                    self._recovering = False
                    self.store.event(_EVENT, None, {"action": "accounted", "identity": identity, "sha": row["sha"]})
                    state[identity]["accounted"] = True
                    self.store.put(_STATE, state)
                recovered += 1
            except Exception:
                unresolved += 1
        return {"recovered": recovered, "unresolved": unresolved}

    def image(self, kind):
        if kind != "gym":
            raise PoolError("sealed and live images are unavailable to research")
        return self.checkpoint

    def bundle(self):
        return self.version

    def _payload(self, job: GymJob):
        if job.gate or job.window not in ("train", "validation"):
            raise PoolError("research accepts only Train and Validation windows")
        purposes = ("train", "probe", "mechanism", "robustness") if job.window == "train" else ("validation",)
        if job.purpose not in purposes or not job.roots or any(root not in self.roots for root in job.roots):
            raise PoolError("research job has an unsupported purpose or root")
        first, last = (self.train_first, "2024-12-31") if job.window == "train" else ("2025-01-02", "2025-12-31")
        start, end = job.start or first, job.end or last
        try:
            if job.window == "validation" and (job.start is not None or job.end is not None):
                raise ValueError
            if any(value is not None and not isinstance(value, str) for value in (job.start, job.end)):
                raise ValueError
            if any(dt.date.fromisoformat(day).isoformat() != day for day in (start, end)) or not first <= start <= end <= last:
                raise ValueError
            if isinstance(job.stress, bool) or not isinstance(job.stress, (int, float)) or not math.isfinite(job.stress) or not 0 <= job.stress <= 10:
                raise ValueError
            from . import settings as settings_mod
            split = job.split if job.split is not None else (settings_mod.train_split(self.settings, dt.date.fromisoformat(start))
                    if job.window == "train" else self.settings.get("gym", {}).get("validation_split", 1))
            if isinstance(split, bool) or not isinstance(split, int) or not 1 <= split <= 128 or job.detail not in ("full", "summary"):
                raise ValueError
            if job.window == "validation" and split != 1:
                raise ValueError
            if not _text(job.family) or not isinstance(job.code, str) or not isinstance(job.params, dict):
                raise ValueError
            if job.version is not None and (isinstance(job.version, bool) or not isinstance(job.version, int) or job.version < 1):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise PoolError("invalid isolated research job") from None
        if job.window == "train" and job.start is None:
            job.start = job.span = self.train_first
        return _json({"family": job.family, "version": job.version, "code": job.code, "params": job.params,
                      "window": job.window, "roots": list(job.roots), "stress": job.stress, "purpose": job.purpose,
                      "detail": job.detail, "split": split,
                      "start": start if job.window == "train" else None,
                      "end": end if job.window == "train" else None})

    def submit(self, job: GymJob):
        payload = self._payload(job)
        evaluation = {k: v for k, v in payload.items() if k not in ("family", "version", "purpose")}
        from .researcher import merged_key, params_of
        evaluation["params"] = merged_key(params_of(job.code) or {}, job.params)
        key = "research-gym:" + _digest({"checkpoint": self.checkpoint, "bundle": self.version, "gym_execution": self.execution, "evaluation": evaluation,
                                       "execution": self._execution(payload)})
        with self._wake:
            if self._stopping or getattr(self, "_recovering", False):
                raise PoolError("isolated research pool is stopped")
            if job.id in self._jobs:
                if self._jobs[job.id][1] != payload:
                    raise PoolError("a queued research job cannot change its body")
                return job
            self._jobs[job.id] = job, payload, key
            self._queue.append(job.id)
            self._wake.notify()
        return job

    def _dispatch(self):
        while True:
            with self._wake:
                while not self._queue and not self._stopping:
                    self._wake.wait()
                if self._stopping:
                    return
                identity = self._queue.pop(0)
                job, payload, key = self._jobs[identity]
                if job.done.is_set():
                    continue
                self._running.add(identity)
            self._execute(job, payload, key)

    def _execute(self, job, payload, key):
        failure = None
        try:
            request = self._request(payload)
            with self.store.atomic():
                prior = _load(self.store).get("gym:" + key)
            if prior is not None:
                request = prior["request"]
            identity, sha, document, fresh = _claim(self.store, "gym", key, request)
            if document is None:
                document = self.broker.run_gym(payload, key=key) if fresh else _recover(self.broker, key, "gym")
            try:
                result = self._result(document, request)
            except Exception:
                _reject(self.store, identity, document)
                raise
            _complete(self.store, identity, sha, document, counts_before=self._counts(request["job"]["family"], result))
            if not fresh:
                if job.window == "validation":
                    raise ValueError("Validation receipt is already recorded; recover its verdict without another trial")
                result["trials"] = 0
            with self._lock:
                job.result, job.batch = result, document.get("batch")
        except Exception:
            # No retry, cancellation or new trial is inferred from a lost host response.
            failure = "isolated broker Gym request unresolved or refused"
        finally:
            with self._lock:
                job.error = failure
                # A lost/refused IPC call is not an executed failure. Retain its
                # request, without spending stock robustness failure attempts.
                callback = None if failure else job.late
                job.late = job.late_fail = None
            if callback is not None:
                try:
                    callback(failure if failure else job.result)
                except Exception:
                    # The original owners retain their own durable reconciliation receipts.
                    pass
            with self._lock:
                self._running.discard(job.id)
                job.done.set()

    def wait(self, job: GymJob, timeout=None, *, late=None, late_fail=None):
        if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0):
            raise PoolError("invalid research wait timeout")
        with self._lock:
            queued = self._jobs.get(job.id)
            if queued is None or queued[0] is not job:
                raise PoolError("research job was not submitted")
        if not job.done.wait(timeout):
            with self._lock:
                if not job.done.is_set():
                    job.late, job.late_fail = late, late_fail
                    # Stock Researcher uses this phrase plus job state to park an
                    # operator's original evaluation rather than spend another attempt.
                    raise PoolError("isolated research Gym did not answer; the original evaluation remains in flight")
        with self._lock:
            if job.error:
                raise PoolError(job.error)
            return job.result

    def run(self, job, timeout=None, *, late=None, late_fail=None):
        return self.wait(self.submit(job), timeout, late=late, late_fail=late_fail)

    def cancel_family(self, family):
        with self._lock:
            for identity, (job, _, _) in self._jobs.items():
                if job.family == family and identity not in self._running and not job.done.is_set():
                    job.error = "research family retired before dispatch"
                    job.done.set()

    def queued(self, kind=None, *, robustness=True):
        if kind == "gate":
            return 0
        with self._lock:
            return sum(not job.done.is_set() and identity not in self._running and (robustness or job.purpose != "robustness")
                       for identity, (job, _, _) in self._jobs.items())

    def stop(self, timeout=5):
        """Stop admission/queued jobs; a host evaluation already dispatched keeps its receipt."""
        with self._wake:
            self._stopping = True
            for identity in self._queue:
                job = self._jobs[identity][0]
                job.error = "isolated research pool stopped before dispatch"
                job.done.set()
            self._queue.clear()
            self._wake.notify_all()
        self._worker.join(timeout)
        return not self._worker.is_alive()
