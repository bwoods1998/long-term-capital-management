"""Factual ordinary-service price basis, without a future provider-price promise.

The host reads approved raw documents and account facts. This module makes no
provider call. Freshness governs admission revalidation, never accepted-request
cancellation or a guarantee that a prospective price change cannot occur.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re

PROFILES = ("flash41_asap", "flash_asap", "k3_balanced", "pro_asap")
MODE = "observed_self_service"


class CostBasisError(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise CostBasisError(reason)


def fields(value, names):
    require(isinstance(value, dict) and set(value) == set(names.split()), "invalid self-service cost-basis fields")


def money(value, *, optional=False):
    if value is None and optional:
        return None
    require(type(value) in (str, int), "exact self-service cost evidence required")
    try:
        number = Decimal(value)
        require(number.is_finite() and 0 <= number <= Decimal("1000000")
                and len(number.as_tuple().digits) <= 20 and number.as_tuple().exponent >= -12,
                "invalid self-service cost evidence")
        return number
    except (ArithmeticError, ValueError) as exc:
        raise CostBasisError("invalid self-service cost evidence") from exc


def clock(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "invalid cost-basis time")
    return float(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class SelfServiceCostBasis:
    """Validated facts; raw-file hashes bind inputs but do not authenticate them."""

    document_json: str
    sha256: str
    fee_fraction: Decimal | None
    tax_fraction: Decimal | None
    fixed_day_fee: Decimal | None

    @property
    def document(self):
        return json.loads(self.document_json)  # Callers cannot mutate the hash-bound origin.

    def status(self):
        d = self.document
        return {"accounting_mode": MODE, "price_basis_sha256": self.sha256,
                "price_basis_time": d["observed_at"], "refresh_by": d["refresh_by"],
                "future_rate_lock": False, "provider_final_bill_guaranteed": False,
                "verified_all_in_ceiling": False,
                "fees_taxes_known": self.known_adjustments,
                "prior_cost_known": d["prior"]["complete"] and d["prior"]["upper_usd"] is not None,
                "pending_unknown_keys": [row["key"] for row in d["pending"] if row["upper_usd"] is None]}

    @property
    def known_adjustments(self):
        return all(v is not None for v in (self.fee_fraction, self.tax_fraction, self.fixed_day_fee))

    def factor(self):
        require(self.known_adjustments, "unknown fees or taxes refuse paid self-service admission")
        return (1 + self.fee_fraction) * (1 + self.tax_fraction)

    def pending_upper(self):
        rows = self.document["pending"]
        require(all(row["upper_usd"] is not None for row in rows),
                "unbounded original pending exposure refuses paid self-service admission")
        return {row["key"]: format(money(row["upper_usd"]), "f") for row in rows}

    def require_admission_facts(self):
        self.factor()
        self.pending_upper()
        require(self.document["prior"]["complete"] is True and self.document["prior"]["upper_usd"] is not None,
                "unknown original prior costs refuse paid self-service admission")
        require(all(self.document["applicability"][n] is not None for n in ("plan", "region")),
                "unknown applicable plan or region refuses paid self-service admission")
        require(self.document["applicability"]["provenance"] is not None
                and isinstance(self.document["prior"]["provenance"], str)
                and self.document["prior"]["provenance"].strip(), "known account/prior facts require evidence")
        require(self.document["fees_taxes"]["creation_fee_upper_usd"] is not None,
                "unknown original creation fee refuses paid self-service admission")

    def tariff_document(self):
        self.require_admission_facts()
        d = self.document
        factor = self.factor()
        return {"scope": d["scope"], **{name: format(money(value) * factor, "f")
                for name, value in d["resource_rates"].items()},
                "valid_from": d["observed_at"], "valid_until": d["refresh_by"],
                "provenance": d["provenance"], "mode": MODE, "basis_sha256": self.sha256,
                "future_rate_lock": False, "fixed_day_fee_usd": format(self.fixed_day_fee, "f"),
                "prior_utc_day": d["prior"]["utc_day"], "prior_upper_usd": d["prior"]["upper_usd"],
                "pending": tuple((row["key"], row["upper_usd"]) for row in d["pending"])}

    def validate_profiles(self, profiles):
        from ltcm.provider import PROFILES as stock
        require(set(profiles) == set(PROFILES), "the four original profiles are required")
        factor = self.factor()
        for name, row in profiles.items():
            fields(row, "policy max_request_bytes billable_input_ceiling completion_window")
            p, rate = row["policy"], self.document["model_rates"][name]
            require((p["model"], row["completion_window"]) == stock[name][:2], "original model or window changed")
            require(type(row["max_request_bytes"]) is int and 0 < row["max_request_bytes"] <= 4*1024*1024
                    and type(row["billable_input_ceiling"]) is int
                    and row["billable_input_ceiling"] == p["max_input_tokens"],
                    "source-enforced whole-input and byte ceilings required")
            require(money(p["input_usd_million"]) >= money(rate["input_usd_million"]) * factor
                    and money(p["output_usd_million"]) >= money(rate["output_usd_million"]) * factor
                    and money(p["fixed_usd"]) >= money(rate["fixed_request_usd"]) * factor,
                    "fresh applicable rates exceed original admitted model price policy")


def read_cost_basis(document, *, scope, now, read_reference, quantity_sources, require_fresh=True):
    """Read schema2, including explicit unknowns. Admission is a separate check."""
    fields(document, "schema mode scope observed_at refresh_by future_rate_lock references applicability "
           "model_rates resource_rates fees_taxes prior pending provenance")
    d = document
    require(type(d["schema"]) is int and d["schema"] == 2 and d["mode"] == MODE
            and d["scope"] == scope and d["future_rate_lock"] is False,
            "explicit observed self-service mode without a future rate lock required")
    require(clock(d["observed_at"]) < clock(d["refresh_by"]) <= d["observed_at"] + 300,
            "invalid self-service refresh interval")
    require(not require_fresh or d["observed_at"] <= clock(now) <= d["refresh_by"], "self-service cost basis is stale")
    require(isinstance(d["provenance"], str) and d["provenance"].strip(), "cost-basis provenance required")
    refs = d["references"]
    fields(refs, "terms pricing quantity_source account_facts")
    urls = {"terms": "https://www.sailresearch.com/terms", "pricing": "https://docs.sailresearch.com/pricing"}
    for role, ref in refs.items():
        fields(ref, "path sha256 url")
        require(isinstance(ref["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]),
                "raw cost-basis source hash required")
        require(role not in urls or ref["url"] == urls[role], "primary cost-basis source required")
        require(isinstance(ref["url"], str) and ref["url"].strip(), "source identity required")
        raw = read_reference(Path(ref["path"]), ref["sha256"])
        require(isinstance(raw, bytes) and hashlib.sha256(raw).hexdigest() == ref["sha256"],
                "raw cost-basis bytes differ")
        if role == "quantity_source":
            try:
                require(json.loads(raw) == quantity_sources, "quantity source differs from the actual reviewed artifact")
            except (ValueError, UnicodeError) as exc:
                raise CostBasisError("invalid retained quantity-source manifest") from exc
    fields(d["applicability"], "plan region provenance")
    require(all(v is None or isinstance(v, str) and v.strip() for v in d["applicability"].values()),
            "invalid applicable account facts")
    fields(d["fees_taxes"], "fee_fraction_upper tax_fraction_upper fixed_day_fee_upper_usd creation_fee_upper_usd provenance")
    money(d["fees_taxes"]["creation_fee_upper_usd"], optional=True)
    fee, tax, fixed = (money(d["fees_taxes"][n], optional=True)
                       for n in ("fee_fraction_upper", "tax_fraction_upper", "fixed_day_fee_upper_usd"))
    require(d["fees_taxes"]["provenance"] is None or isinstance(d["fees_taxes"]["provenance"], str)
            and d["fees_taxes"]["provenance"].strip(), "fee/tax provenance must retain unknowns")
    require(not all(v is not None for v in (fee, tax, fixed)) or d["fees_taxes"]["provenance"] is not None,
            "known zero fees/taxes also require evidence")
    fields(d["prior"], "utc_day upper_usd complete provenance")
    money(d["prior"]["upper_usd"], optional=True)
    require(type(d["prior"]["complete"]) is bool, "explicit prior-cost completeness required")
    require(isinstance(d["pending"], list), "original pending inventory required")
    keys = set()
    for row in d["pending"]:
        fields(row, "key upper_usd provenance")
        require(isinstance(row["key"], str) and row["key"].strip() and row["key"] not in keys,
                "unique original pending identities required")
        keys.add(row["key"])
        money(row["upper_usd"], optional=True)
        require(row["upper_usd"] is None or isinstance(row["provenance"], str) and row["provenance"].strip(),
                "bounded pending cost requires evidence")
    fields(d["resource_rates"], "vcpu_usd_hour memory_gib_usd_hour disk_gib_usd_hour volume_gib_usd_hour")
    for value in d["resource_rates"].values():
        money(value)
    require(isinstance(d["model_rates"], dict) and set(d["model_rates"]) == set(PROFILES),
            "original four observed model prices required")
    for value in d["model_rates"].values():
        fields(value, "input_usd_million output_usd_million fixed_request_usd")
        for rate in value.values():
            money(rate)
    return SelfServiceCostBasis(json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False),
                                digest(d), fee, tax, fixed)
