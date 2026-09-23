#!/usr/bin/env python3
"""The Alpha Lab's own Sailbox: one box, larger than an agent's, where batches of candidate
strategies are replayed over development tapes (`league/labbox.py`, `replay.run_batch`).

    python3 scripts/lab_box.py create [--size l]   create, install python3, seal, verify, record
    python3 scripts/lab_box.py status              the box, its seal read back, python, tapes held
    python3 scripts/lab_box.py bench --tape T --candidates C [--repeat N] [--single K]
                                                   candidates a second through LabBox on the box
    python3 scripts/lab_box.py sleep               put it to sleep now

Runs from the owner's machine with the owner's Sail key (`ltcm.sailbox.SailboxClient`, as
`scripts/floor_box.py`). It never touches the House's box.

The box is created from Sail's base Debian image with an egress allowlist of the Debian mirrors
only, `python3` is installed (the standard library is all a batch needs), and then its network is
closed exactly as an agent box's is (`league.sandbox.SEALED`: an allowlist of one host that never
resolves). The seal is read back from the API and tested from inside the box before the box is
recorded, and the House's sandbox seals it again before its first batch (`SailSandbox.bind`). No
credential is ever placed in it. Sail bills observed use, not size, so a larger box costs nothing
more while idle; it sleeps on its own after ten idle minutes.

The record is the `lab` block of `league/config.json` (`box`, `box_id`, `size`, ...), where the
House finds it (`LabBox.from_config`); the create's idempotency key and the bench's sandbox state
stay in `.data/lab/` (owner-only, never a secret).
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ltcm.sailbox import TERMINAL, SailboxClient, normalize_hosts, policy_allowlist  # noqa: E402

CONFIG = REPO_ROOT / "league" / "config.json"
DATA = REPO_ROOT / ".data" / "lab"
STATE = DATA / "box.json"
#: Only while python3 is installed; the box is sealed before it is recorded.
PROVISION_HOSTS = ("deb.debian.org", "security.debian.org")
PROVISION = "\n".join([
    "set -e",
    "if ! command -v python3 >/dev/null 2>&1; then",
    "  export DEBIAN_FRONTEND=noninteractive",
    "  apt-get update -qq",
    "  apt-get install -y -qq --no-install-recommends python3 >/dev/null",
    "fi",
    "mkdir -p /agent/tapes /agent/results",
    "python3 -c 'import sys; print(\"python\", sys.version.split()[0])'",
])
#: Run inside the box once it is sealed: a connection out must fail.
NETWORK_PROBE = ("python3 -c \"import socket\ntry:\n    socket.create_connection(('deb.debian.org', 443), timeout=5)\n"
                 "    print('NETWORK-OPEN')\nexcept OSError as exc:\n    print('NETWORK-CLOSED', type(exc).__name__)\"")
AUTO_SLEEP_SECONDS = 600


def say(text: str) -> None:
    print(text, flush=True)


def read_config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def write_lab(block: Mapping[str, Any]) -> None:
    """Put the `lab` block into league/config.json, the rest of the file untouched."""
    config = read_config()
    config["lab"] = dict(block)
    CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def read_state() -> dict[str, Any]:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(state: Mapping[str, Any]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_name(STATE.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(dict(state), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(STATE)


def lab_box_id(args: argparse.Namespace) -> str:
    box = getattr(args, "box_id", None) or (read_config().get("lab") or {}).get("box_id")
    if not box:
        raise SystemExit("no lab box recorded in league/config.json -- run `python3 scripts/lab_box.py create`")
    return str(box)


def sealed_hosts() -> list[str]:
    from league.sandbox import SEALED

    return normalize_hosts(SEALED)


# ------------------------------------------------------------------------------------ commands
def cmd_create(args: argparse.Namespace) -> int:
    api = SailboxClient()
    config = read_config()
    known = (config.get("lab") or {}).get("box_id")
    if known and not args.replace:
        status = str((api.get(known) or {}).get("status") or "")
        if status not in TERMINAL:
            say(f"the lab box {known} exists ({status}); `status` shows it, --replace makes another")
            return 0
    who = api.whoami()
    visibility = "private" if who.get("user_id") else "org"
    app = api.find_app(str(config.get("sail_app") or "ltcm"), mint_if_missing=True)
    state = read_state()
    key = state.get("create_key") if state.get("create_pending") else None
    key = key or f"ltcm-lab-{uuid.uuid4()}"
    write_state({"create_key": key, "create_pending": True, "app_id": app["id"], "name": args.name, "size": args.size})
    say(f"creating a size-{args.size} Sailbox {args.name} in app {app['id']} ({visibility}); egress: {', '.join(PROVISION_HOSTS)}")
    row = api.create(app=app["id"], name=args.name, size=args.size, image={"base": "BASE_IMAGE_DEBIAN"},
                     egress={"allowlist": normalize_hosts(PROVISION_HOSTS)},
                     auto_sleep={"automatic": True, "min_seconds_before_sleep": AUTO_SLEEP_SECONDS},
                     visibility=visibility, idempotency_key=key)
    box = str(row["sailbox_id"])
    write_state({"create_key": key, "create_pending": False, "app_id": app["id"], "name": args.name, "size": args.size, "box_id": box})
    say(f"  box {box}; installing python3")
    done = api.exec(box, ["sh", "-c", PROVISION], timeout=900).check()
    python = done.stdout.strip().splitlines()[-1].split()[-1] if done.stdout.strip() else "?"
    say(f"  python {python}; sealing the network")
    api.set_egress(box, sealed_hosts())
    stored = policy_allowlist(api.egress(box))
    if stored != sealed_hosts():
        api.terminate(box)
        raise SystemExit(f"the seal did not hold (stored allowlist {stored}); the box was terminated")
    probe = api.exec(box, ["sh", "-c", NETWORK_PROBE], timeout=120)
    if "NETWORK-CLOSED" not in probe.stdout:
        api.terminate(box)
        raise SystemExit(f"the box could still reach the network ({probe.stdout.strip()[:200]}); it was terminated")
    say(f"  sealed: allowlist {stored}; from inside: {probe.stdout.strip()}")
    block = {
        "_about": "The Alpha Lab's own Sailbox (scripts/lab_box.py): sealed like an agent box, larger than one. "
                  "LabBox.from_config binds box_id into the House's sandbox under box_key.",
        "box": args.name, "box_id": box, "size": args.size, "box_key": "lab", "python": python,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_lab(block)
    say(f"  recorded in {CONFIG.relative_to(REPO_ROOT)}: {json.dumps(block)}")
    api.sleep(box)
    say("  asleep until the first batch")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    api = SailboxClient()
    box = lab_box_id(args)
    row = api.get(box)
    out = {"box_id": box, "name": row.get("name"), "status": row.get("status"), "size": row.get("size"),
           "allowlist": policy_allowlist(api.egress(box)), "sealed_as_agents": policy_allowlist(api.egress(box)) == sealed_hosts()}
    if args.wake or row.get("status") == "running":
        if row.get("status") != "running":
            api.resume(box)
        probe = api.exec(box, ["sh", "-c", "python3 --version; nproc; ls /agent/tapes 2>/dev/null | wc -l; " + NETWORK_PROBE], timeout=120)
        out["inside"] = probe.stdout.strip().splitlines()
    try:
        out["spend"] = api.spend(box)
    except Exception as exc:  # noqa: BLE001 - spend is informative
        out["spend"] = f"unavailable: {type(exc).__name__}"
    print(json.dumps(out, indent=1, default=str))
    return 0


def cmd_sleep(args: argparse.Namespace) -> int:
    box = lab_box_id(args)
    SailboxClient().sleep(box)
    say(f"told {box} to sleep")
    return 0


def _load(path: str) -> Any:
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if path.endswith(".gz") else raw)


def cmd_bench(args: argparse.Namespace) -> int:
    """Candidates a second through `LabBox` on the lab box, the tape uploaded once: the first batch
    pays the upload, the later ones reuse it. `--single K` also times K replays the old way
    (`sandbox.replay`: the whole tape uploaded with every one) on the same box."""
    from league.labbox import LabBox
    from league.sandbox import SailSandbox

    config = read_config()
    box = lab_box_id(args)
    tape = _load(args.tape)
    base = _load(args.candidates)
    candidates = [dict(c, id=f"{c.get('id') or i}-{r}") for r in range(args.repeat) for i, c in enumerate(base)]
    limits = json.loads(args.limits)
    sandbox = SailSandbox(SailboxClient(), DATA / "sandbox.json", image_checkpoint=config["agent_image_checkpoint"], name_prefix="lab")
    lab = LabBox.from_config(sandbox, {"lab": {**(config.get("lab") or {}), "box_id": box}}, workers=args.workers,
                             budget_seconds=args.budget)
    assert lab is not None
    say(f"bench on {box}: {len(candidates)} candidates ({len(base)} distinct x {args.repeat}) over {args.tape}")
    rows = []
    for round_ in range(args.rounds):
        started = time.monotonic()
        results = lab.evaluate(candidates, f"bench:{args.tape}", tape, stake=args.stake, limits=limits, timeout=args.timeout)
        seconds = time.monotonic() - started
        last = dict(lab.stats["last"] or {})
        ok = sum(1 for r in results if r.get("ok"))
        evaluated = sum(1 for r in results if r.get("error") != "not evaluated: batch budget")
        rows.append({"round": round_ + 1, "candidates": len(candidates), "evaluated": evaluated, "ok": ok, "seconds": round(seconds, 2),
                     "per_second": round(evaluated / seconds, 3), "box_seconds": last.get("box_seconds"), "workers": last.get("workers"),
                     "uploaded": last.get("uploaded")})
        say(json.dumps(rows[-1]))
    if args.single:
        started = time.monotonic()
        for c in base[: args.single]:
            sandbox.replay("lab", c["code"], c.get("params") or {}, tape, stake=args.stake, limits=limits, timeout=args.timeout)
        seconds = time.monotonic() - started
        rows.append({"single": args.single, "seconds": round(seconds, 2), "per_second": round(args.single / seconds, 3)})
        say(json.dumps(rows[-1]))
    sandbox.rest("lab")
    say("the lab box is going to sleep")
    if args.out:
        Path(args.out).write_text(json.dumps({"box_id": box, "tape": args.tape, "rows": rows, "stats": lab.stats}, indent=1, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--box-id", help="the lab box (default: league/config.json lab.box_id)")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create, provision, seal and record the lab box")
    create.add_argument("--name", default="ltcm-lab")
    create.add_argument("--size", default="l", choices=("s", "m", "l"))
    create.add_argument("--replace", action="store_true", help="create another even if the recorded one is alive")
    create.set_defaults(func=cmd_create)
    status = sub.add_parser("status", help="the box, its seal, python and tapes")
    status.add_argument("--wake", action="store_true", help="resume it to look inside")
    status.set_defaults(func=cmd_status)
    sub.add_parser("sleep", help="put the lab box to sleep").set_defaults(func=cmd_sleep)
    bench = sub.add_parser("bench", help="candidates a second on the lab box")
    bench.add_argument("--tape", required=True, help="a tape, .json or .json.gz")
    bench.add_argument("--candidates", required=True, help='a JSON list of {"id", "code", "params"}')
    bench.add_argument("--repeat", type=int, default=1)
    bench.add_argument("--rounds", type=int, default=2, help="batches in a row (the first uploads the tape)")
    bench.add_argument("--workers", type=int, default=None)
    bench.add_argument("--budget", type=float, default=None)
    bench.add_argument("--single", type=int, default=0, help="also time this many single replays")
    bench.add_argument("--stake", type=float, default=200.0)
    bench.add_argument("--limits", default='{"max_position_usd": 100.0, "max_order_usd": 75.0}')
    bench.add_argument("--timeout", type=float, default=600.0)
    bench.add_argument("--out", help="write the numbers here as JSON")
    bench.set_defaults(func=cmd_bench)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
