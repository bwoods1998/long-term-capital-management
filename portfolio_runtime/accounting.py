"""Pure frozen-rate USD estimates; no credentials, database or provider imports."""

from decimal import Decimal
import re


def estimate_cost(usage, rates, metadata=None, *, supercache_contract=None):
    """USD estimate including automatic Supercache reads, without double counting.

    The default contract still prohibits writes. Only a separately frozen caller
    may request 'write-24h-v1' or 'read-24h-v1'; response metadata cannot opt itself
    into write accounting. Written input is removed from ordinary input before
    pricing it at 100 times the input rate. Explicit contracts require all counters.
    """
    if not isinstance(usage, dict) or not isinstance(
        usage.get("input_tokens_details") or {}, dict
    ):
        raise ValueError("Missing or inconsistent token accounting")
    i, o = usage.get("input_tokens"), usage.get("output_tokens")
    c = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
    if any(type(v) is not int or v < 0 for v in (i, o, c)) or c > i:
        raise ValueError("Missing or inconsistent token accounting")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("Invalid provider usage metadata")
    metadata = metadata or {}
    names = ("supercached_input_tokens", "supercache_write_input_tokens")
    if supercache_contract not in (None, "write-24h-v1", "read-24h-v1"):
        raise ValueError("Unknown Supercache accounting contract")
    if supercache_contract and (
        not all(name in metadata for name in names)
        or "cached_tokens" not in (usage.get("input_tokens_details") or {})
    ):
        raise ValueError("Explicit Supercache accounting requires complete counters")
    supercached, written = 0, 0
    if any(name in metadata for name in names):
        if any(
            not isinstance(metadata.get(name), str)
            or not re.fullmatch(r"\d{1,16}", metadata[name])
            for name in names
        ):
            raise ValueError("Incomplete or malformed Supercache accounting")
        supercached, written = (int(metadata[name]) for name in names)
        if (
            supercached > c
            or written > i - c
            or (written != 0 and supercache_contract != "write-24h-v1")
        ):
            raise ValueError("Inconsistent or unapproved Supercache accounting")
    return (
        (i - c - written) * Decimal(rates["input"])
        + (c - supercached) * Decimal(rates["cached"])
        + supercached * Decimal(rates["cached"]) * Decimal("0.1")
        + written * 100 * Decimal(rates["input"])
        + o * Decimal(rates["output"])
    ) / Decimal(1_000_000)
