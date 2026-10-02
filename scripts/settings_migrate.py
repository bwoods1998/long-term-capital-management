"""The V3-A settings migration (SETTINGS AS CODE, league/swarm/settings.py): the research settings move from the box's
`<state>/swarm.json` into the repo's `league/swarm/policy.json`, and swarm.json keeps only the owner's switches
(`settings.OWNER_KEYS`: `enabled`, `live`).

Runs ON THE LAPTOP against a COPY of the box's swarm.json (the captain downloads it); it never reads or writes the box:

    python3 scripts/settings_migrate.py --swarm /path/to/swarm.json            # dry run: the plan, nothing written
    python3 scripts/settings_migrate.py --swarm /path/to/swarm.json --apply    # writes the two files

The proposed policy.json is the repo's current one with every other key of swarm.json merged over it (swarm.json's values
were the ones in effect, so they win). The reduced swarm.json keeps the owner's switches and the operator's top-level
notes (keys starting with "_", which no layer reads); notes nested inside a block are left out of policy.json, since the
repo is public, and listed. The move must change nothing: the settings `settings.load` gives with the old pair and with
the new pair are compared, and on any difference nothing is written. A swarm.json that is not a JSON object, or a key or
value that looks like a credential, is refused.

ORDER AT THE DEPLOY: commit the proposed policy.json into the release and deploy it, THEN install the reduced swarm.json
on the box. A reduced swarm.json under a release without its policy.json runs the swarm on config.json's defaults.
Standard library only.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from league.swarm import settings as settings_mod  # noqa: E402

#: A key name that may hold a credential: refused (the policy file is public). A count of tokens ("max_output_tokens")
#: is not one.
SECRET_KEY = re.compile(r"(^|[_-])(token|secret|password|passwd|apikey|api[_-]key|private[_-]key|credentials?|bearer)$",
                        re.IGNORECASE)
#: A string value shaped like a credential: refused.
SECRET_VALUE = re.compile(r"^(sk-|sk_|ghp_|gho_|github_pat_|xox[abp]-|AKIA|-----BEGIN)")


class MigrationError(RuntimeError):
    """The migration refuses (the message says why); nothing is written."""


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """{"a.b.c": leaf} for every leaf of nested objects (an empty object is a leaf)."""
    if isinstance(value, Mapping) and value:
        out: dict[str, Any] = {}
        for key, inner in value.items():
            out.update(_flatten(inner, f"{prefix}.{key}" if prefix else str(key)))
        return out
    return {prefix: value}


def _strip_notes(value: Any, prefix: str, dropped: list[str]) -> Any:
    """`value` without keys starting with "_" at any depth (each dropped path is listed in `dropped`)."""
    if not isinstance(value, Mapping):
        return copy.deepcopy(value)
    out = {}
    for key, inner in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if str(key).startswith("_"):
            dropped.append(path)
            continue
        out[key] = _strip_notes(inner, path, dropped)
    return out


def _secrets(value: Any) -> list[str]:
    """The paths whose key or string value looks like a credential."""
    found = []
    for path, leaf in _flatten(value).items():
        if any(SECRET_KEY.search(part) for part in path.split(".")) or (isinstance(leaf, str) and SECRET_VALUE.match(leaf)):
            found.append(path)
    return sorted(found)


def _effective(swarm: Mapping[str, Any], *, config: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    """The settings `settings.load` gives for this swarm.json and policy (its own status left out)."""
    with tempfile.TemporaryDirectory(prefix="settings-migrate-") as root:
        (Path(root) / "swarm.json").write_text(json.dumps(swarm), encoding="utf-8")
        out = settings_mod.load(root, config=config, policy=policy)
    out.pop("_policy", None)
    return out


def plan(swarm: Any, *, policy: Any, config: Mapping[str, Any]) -> dict[str, Any]:
    """The migration: {"policy": the proposed policy.json, "swarm": the reduced swarm.json, "moved": {path: value},
    "changed": [paths whose policy value changes], "kept": [top-level keys kept in swarm.json], "notes_left_out": [...],
    "dollar_lines": [moved paths naming usd: public once committed], "blocks_without_defaults": [moved top-level keys
    settings.py has no default for: a module reads them itself (`allocation`), or a typo]}. Raises MigrationError on a
    refusal."""
    if not isinstance(swarm, Mapping):
        raise MigrationError(f"swarm.json is not a JSON object ({type(swarm).__name__})")
    if not isinstance(policy, Mapping):
        raise MigrationError(f"the current policy.json is not a JSON object ({type(policy).__name__})")
    owner = [k for k in policy if k in settings_mod.OWNER_KEYS]
    if owner:
        raise MigrationError(f"the current policy.json sets the owner's {', '.join(owner)}: remove them first")
    dropped: list[str] = []
    moved = _strip_notes({k: v for k, v in swarm.items() if k not in settings_mod.OWNER_KEYS}, "", dropped)
    dropped = [p for p in dropped if "." in p]  # top-level notes stay in swarm.json
    secrets = _secrets(moved)
    if secrets:
        raise MigrationError(f"these keys look like credentials and never go into the public policy.json: {', '.join(secrets)}")
    reduced = {k: copy.deepcopy(v) for k, v in swarm.items() if k in settings_mod.OWNER_KEYS or str(k).startswith("_")}
    proposed = settings_mod._merge(dict(policy), moved)  # the file's own notes ("_about") stay
    before = _effective(swarm, config=config, policy=policy)
    after = _effective(reduced, config=config, policy=proposed)
    if before != after:
        differ = sorted(p for p in set(_flatten(before)) | set(_flatten(after))
                        if _flatten(before).get(p, "<absent>") != _flatten(after).get(p, "<absent>"))
        raise MigrationError(f"the move would change the settings in effect at {', '.join(differ[:12])}")
    old, flat = _flatten({k: v for k, v in policy.items() if not str(k).startswith("_")}), _flatten(moved)
    return {"policy": proposed, "swarm": reduced, "moved": flat,
            "changed": sorted(p for p, v in flat.items() if old.get(p, "<absent>") != v),
            "kept": sorted(reduced), "notes_left_out": sorted(dropped),
            "dollar_lines": sorted(p for p in flat if "usd" in p.lower()),
            "blocks_without_defaults": sorted(k for k in moved if k not in settings_mod.DEFAULTS)}


def _write(path: Path, doc: Mapping[str, Any]) -> None:
    """Write a JSON document atomically (a temporary file beside it, then a rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path, *, missing: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if missing is not None:
            return missing
        raise MigrationError(f"{path} does not exist") from None
    except ValueError as exc:
        raise MigrationError(f"{path} is not JSON ({exc})") from None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--swarm", required=True, help="a COPY of the box's <state>/swarm.json")
    ap.add_argument("--policy", default=str(settings_mod.POLICY_PATH), help="the current policy.json (default: the repo's)")
    ap.add_argument("--config", default=str(settings_mod.REPO / "league" / "config.json"), help="the release's config.json")
    ap.add_argument("--policy-out", default=None, help="where the proposed policy.json goes (default: --policy)")
    ap.add_argument("--swarm-out", default=None, help="where the reduced swarm.json goes (default: <swarm>.reduced.json)")
    ap.add_argument("--apply", action="store_true", help="write the two files (default: a dry run)")
    args = ap.parse_args(argv)
    swarm_path = Path(args.swarm)
    policy_out = Path(args.policy_out or args.policy)
    swarm_out = Path(args.swarm_out) if args.swarm_out else swarm_path.with_name(f"{swarm_path.stem}.reduced.json")
    try:
        config = _read(Path(args.config))
        result = plan(_read(swarm_path), policy=_read(Path(args.policy), missing={}),
                      config=config if isinstance(config, Mapping) else {})
    except MigrationError as exc:
        print(json.dumps({"refused": str(exc)}, indent=1))
        return 2
    report = {"apply": bool(args.apply), "policy_out": str(policy_out), "swarm_out": str(swarm_out),
              "moved": len(result["moved"]), "changed": result["changed"], "kept_in_swarm_json": result["kept"],
              "notes_left_out": result["notes_left_out"], "dollar_lines_made_public": result["dollar_lines"],
              "blocks_without_defaults": result["blocks_without_defaults"],
              "settings_in_effect": "unchanged (checked)",
              "order": "commit and deploy the policy.json first, then install the reduced swarm.json on the box"}
    if args.apply:
        _write(policy_out, result["policy"])
        _write(swarm_out, result["swarm"])
    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
