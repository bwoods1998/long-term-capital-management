#!/usr/bin/env python3
"""Operate the floor's Sailbox from the owner's terminal.

The MacBook is not the floor any more: it is the operator console. The floor runs on one Sail
Sailbox and this script is the only thing that talks to it.

    python3 scripts/floor_box.py create            one size-s box, egress allowlist, code, venv
    python3 scripts/floor_box.py secrets           push .env and the venue private keys (owner)
    python3 scripts/floor_box.py start             start the supervised `python -m ltcm run` loop
    python3 scripts/floor_box.py status            box state, spend, loop, log tail, health.json
    python3 scripts/floor_box.py logs -n 200       the tail of /workspace/ltcm.log
    python3 scripts/floor_box.py deploy            re-upload changed code, restart a running loop
    python3 scripts/floor_box.py checkpoint --name after-upgrade
    python3 scripts/floor_box.py fork --from sbcp_...      a second box, loop NOT started
    python3 scripts/floor_box.py stop              kill switch, quiesce, then stop the loop
    python3 scripts/floor_box.py sleep | resume | pause | terminate --yes

What this script will not do:

- **It never reads a secret except in `secrets`.** The code upload refuses `.env`, anything under
  `.data/`, and any private-key file, whatever the working tree holds. `secrets` is the one
  command that touches them, it uploads bytes it never decodes, and it prints names and sizes.
- **It never prints the Sail key.** The key is fetched inside `ltcm.sailbox` through
  `ltcm.provider.default_key_source()` at the moment of each request.
- **It never starts trading by itself.** `create` and `deploy` leave the loop exactly as they
  found it; only `start` starts it.

Box state lives in `.data/ltcm/box.json`: ids, names, the allowlist in effect, the uploaded-file
digests and the checkpoints taken. It is owner-only (mode 600) and holds no credential.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import sys
import tarfile
import time
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ltcm.sailbox import (  # noqa: E402  (path first, so a checkout runs without installation)
    FLOOR_HOSTS,
    GATEWAY_HOST,
    REMOTE_ROOT,
    SailboxClient,
    SailboxError,
    floor_policy,
    hourly_cost,
    policy_allowlist,
)

STATE_PATH = REPO_ROOT / ".data" / "ltcm" / "box.json"
DEFAULT_APP = "ltcm"
DEFAULT_NAME = "ltcm-floor"

#: What the floor needs on the box. `ltcm/config.json` rides along inside `ltcm/`.
UPLOAD_TREES = ("ltcm", "playbooks", "scripts", "deploy")

#: Never uploaded by the code path, whatever the working tree looks like.
SKIP_DIRS = {"__pycache__", ".git", ".venv", ".data", ".ruff_cache", ".pytest_cache", "history"}
SKIP_SUFFIXES = (".pyc", ".pyo", ".pem", ".key", ".p8", ".pfx", ".crt", ".der", ".sqlite")
SKIP_NAMES = {".env", ".DS_Store"}

#: The only files `secrets` sends, and the only place this script reads a credential.
SECRET_ENV = ".env"
SECRET_KEYS = Path(".data") / "ltcm" / "keys"

RUN_SH = """#!/bin/sh
# The floor's supervisor. Written by scripts/floor_box.py; edit there, not here.
#
# One `python -m ltcm run` at a time, restarted 30 s after it exits, logging to
# /workspace/ltcm.log. `/workspace/STOP` ends the loop after the current run: that is what
# `floor_box.py stop` writes, so a deliberate stop is never undone by the restart delay.
set -u
cd {root} || exit 1
umask 077
echo $$ > {root}/run.pid
stamp() {{ date -u +%Y-%m-%dT%H:%M:%SZ; }}
while [ ! -e {root}/STOP ]; do
  printf '%s  supervisor: starting the floor loop\\n' "$(stamp)" >> {root}/ltcm.log
  {python} -m ltcm run >> {root}/ltcm.log 2>&1 &
  child=$!
  echo "$child" > {root}/loop.pid
  wait "$child"
  code=$?
  rm -f {root}/loop.pid
  printf '%s  supervisor: floor loop exited (%s)\\n' "$(stamp)" "$code" >> {root}/ltcm.log
  [ -e {root}/STOP ] && break
  sleep 30
done
printf '%s  supervisor: stopped\\n' "$(stamp)" >> {root}/ltcm.log
rm -f {root}/run.pid {root}/loop.pid
"""

RESTART_SH = """#!/bin/sh
# Restart the floor loop in place, without disturbing the supervisor: signal the running
# `python -m ltcm run` and let run.sh bring a fresh one up after its 30 s delay.
set -u
pid=$(cat {root}/loop.pid 2>/dev/null || true)
if [ -n "${{pid:-}}" ] && [ -d "/proc/$pid" ]; then
  kill -TERM "$pid" && echo "signalled $pid; the supervisor restarts it in 30s"
else
  echo "no floor loop is running"
fi
"""

#: Is the supervisor up, is the loop up, and what are their pids?
PROBE = (
    "for f in run.pid loop.pid; do "
    'p=$(cat %(root)s/$f 2>/dev/null || true); '
    'if [ -n "$p" ] && [ -d "/proc/$p" ]; then echo "$f=$p"; else echo "$f=-"; fi; '
    "done; "
    "[ -e %(root)s/STOP ] && echo stop=yes || echo stop=no; "
    "[ -e %(root)s/.data/ltcm/KILL ] && echo kill=yes || echo kill=no"
) % {"root": REMOTE_ROOT}


# --------------------------------------------------------------------------- state


def read_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(state: Mapping[str, Any]) -> None:
    """Owner-only, atomic, and never given a secret to hold."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_name(STATE_PATH.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(dict(state), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(STATE_PATH)


def require_box(state: Mapping[str, Any]) -> str:
    box = state.get("box_id")
    if not box:
        raise SystemExit(
            "no box recorded in .data/ltcm/box.json -- run `python3 scripts/floor_box.py create`"
        )
    return str(box)


def expected_policy(state: Mapping[str, Any]) -> dict[str, Any]:
    hosts = state.get("egress_allowlist")
    if isinstance(hosts, list) and hosts:
        return {"allowlist": sorted({str(h) for h in hosts})}
    return floor_policy(gateway_host=state.get("gateway_host") or GATEWAY_HOST)


# --------------------------------------------------------------------------- the code bundle


def is_secret(path: Path) -> bool:
    """True for anything the code upload must never carry."""
    parts = set(path.parts)
    return (
        path.name in SKIP_NAMES
        or path.name.startswith(".env")
        or path.suffix in (".pem", ".key", ".p8", ".pfx", ".crt", ".der")
        or ".data" in parts
        or "keys" in parts
    )


def code_files() -> list[Path]:
    """Every file the box needs, as repository-relative paths. Sorted, so a bundle is stable."""
    found: list[Path] = []
    for tree in UPLOAD_TREES:
        base = REPO_ROOT / tree
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(REPO_ROOT)
            if SKIP_DIRS & set(relative.parts):
                continue
            if relative.suffix in SKIP_SUFFIXES or relative.name in SKIP_NAMES:
                continue
            if relative.name.startswith(".") and relative.name not in ("__init__.py",):
                continue
            if is_secret(relative):
                raise SystemExit(f"refusing to upload a credential path: {relative}")
            found.append(relative)
    if not found:
        raise SystemExit("nothing to upload: run this from the repository")
    return found


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tarball(files: Sequence[Path]) -> bytes:
    """A deterministic gzip tar of the given repository-relative files."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for relative in files:
            source = REPO_ROOT / relative
            info = tarfile.TarInfo(str(relative))
            raw = source.read_bytes()
            info.size = len(raw)
            info.mtime = 0
            info.mode = 0o755 if relative.suffix == ".sh" else 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(raw))
    return buffer.getvalue()


# --------------------------------------------------------------------------- box helpers


def client() -> SailboxClient:
    return SailboxClient()


def say(*parts: Any) -> None:
    print(*parts, flush=True)


def stream(kind: str, text: str) -> None:
    sys.stderr.write(text) if kind == "stderr" else sys.stdout.write(text)
    (sys.stderr if kind == "stderr" else sys.stdout).flush()


def run(api: SailboxClient, box: str, command: Any, *, timeout: int = 600, quiet: bool = False,
        cwd: str | None = None) -> Any:
    result = api.exec(
        box, command, timeout=timeout, cwd=cwd, on_output=None if quiet else stream
    )
    return result


def probe(api: SailboxClient, box: str) -> dict[str, str]:
    """The supervisor, the loop, the stop latch and the kill switch, as seen on the box."""
    try:
        result = api.exec(box, ["sh", "-c", PROBE], timeout=60, on_output=None)
    except SailboxError as error:
        return {"error": str(error)}
    out: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.strip().partition("=")
        if key:
            out[key] = value
    return out


def push_code(api: SailboxClient, box: str, files: Sequence[Path]) -> None:
    """Upload a tar of `files` and unpack it over `/workspace`."""
    blob = tarball(files)
    name = f"{REMOTE_ROOT}/.upload/code-{uuid.uuid4().hex[:12]}.tgz"
    say(f"  uploading {len(files)} files ({len(blob):,} bytes compressed)")
    api.upload(box, name, blob, mode=0o600)
    api.exec(
        box,
        ["sh", "-c", f"set -e; mkdir -p {REMOTE_ROOT}; "
                     f"tar -xzf {name} -C {REMOTE_ROOT} --no-same-owner; rm -f {name}"],
        timeout=300,
        on_output=None,
    ).check()


def render(template: str, python: str) -> bytes:
    return template.format(root=REMOTE_ROOT, python=python).encode("utf-8")


def write_scripts(api: SailboxClient, box: str, python: str) -> None:
    api.upload(box, f"{REMOTE_ROOT}/run.sh", render(RUN_SH, python), mode=0o700)
    api.upload(box, f"{REMOTE_ROOT}/restart.sh", render(RESTART_SH, python), mode=0o700)


def health(api: SailboxClient, box: str) -> Any:
    try:
        raw = api.download(box, f"{REMOTE_ROOT}/.data/ltcm/health.json")
    except SailboxError:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


# --------------------------------------------------------------------------- commands


def cmd_create(args: argparse.Namespace) -> int:
    state = read_state()
    if state.get("box_id") and not args.force:
        raise SystemExit(
            f"a box is already recorded ({state['box_id']}). Use `deploy`, or pass --force to "
            "create a second one (the old box keeps billing until it is terminated)."
        )
    api = client()
    policy = floor_policy(gateway_host=args.gateway_host)

    # A `private` Sailbox can only be operated by the user whose key created it, which is what
    # the floor wants -- but it needs a key that carries a user. An organization key gets `org`.
    who = api.whoami()
    visibility = args.visibility
    if visibility == "private" and not who.get("user_id"):
        visibility = "org"
        say("this is an organization key, so the box is org-visible rather than private")
    say(f"org: {who.get('org_id')}")

    say(f"app: {args.app}")
    app = api.find_app(args.app, mint_if_missing=True)
    say(f"  {app['id']}")

    # The idempotency key is written down *before* the create, so an unconfirmed create is
    # reconciled rather than duplicated. This is the first generation's rule and it is cheap.
    key = state.get("create_key") if state.get("create_pending") else None
    key = key or f"ltcm-floor-{uuid.uuid4()}"
    state = {
        "schema_version": 1,
        "app_id": app["id"],
        "app_name": args.app,
        "name": args.name,
        "size": "s",
        "remote_root": REMOTE_ROOT,
        "gateway_host": args.gateway_host,
        "egress_allowlist": policy["allowlist"],
        "create_key": key,
        "create_pending": True,
        "box_id": None,
        "checkpoints": [],
        "forks": [],
        "uploads": {},
    }
    write_state(state)

    say(f"creating a size-s Sailbox named {args.name} (this blocks until it boots)")
    say(f"  egress allowlist ({len(policy['allowlist'])}): {', '.join(policy['allowlist'])}")
    row = api.create(
        app=app["id"],
        name=args.name,
        size="s",
        egress=policy,
        # Never sleep on its own: the floor must be awake for every open. The 30 s tick would
        # keep it awake anyway (an idle Sailbox is one where "no process is waiting on a timer"),
        # but that is a side effect of a config value, not a guarantee. This is the guarantee.
        auto_sleep={"automatic": False},
        visibility=visibility,
        idempotency_key=key,
    )
    box = row["sailbox_id"]
    state.update(box_id=box, create_pending=False, created_at=_now(), status=row.get("status"),
                 visibility=visibility, org_id=who.get("org_id"))
    write_state(state)
    say(f"  {box}  status={row.get('status')}")

    say("verifying the policy against the live API")
    report = api.verify_egress(box, policy)
    state["egress_verified"] = report["ok"]
    write_state(state)
    if not report["ok"]:
        say(f"  MISMATCH: missing={report['missing']} extra={report['extra']}")
        raise SystemExit(
            "the box is not running the policy that was asked for. It is created and billing: "
            f"inspect it, then `python3 scripts/floor_box.py terminate --yes` ({box})."
        )
    say(f"  allowlist confirmed on the box: {len(report['allowlist'])} hosts")

    row = api.get(box)
    say(f"  vcpu={row.get('vcpu_count')} memory_mib={row.get('memory_mib')} "
        f"disk_gib={row.get('state_disk_size_gib')} auto_sleep={row.get('auto_sleep')}")

    say("uploading the floor")
    files = code_files()
    push_code(api, box, files)
    state["uploads"] = {str(f): digest(REPO_ROOT / f) for f in files}
    write_state(state)

    say("preparing the interpreter")
    python = bootstrap_python(api, box)
    state["python"] = python
    write_state(state)
    say(f"  interpreter: {python}")

    say("writing run.sh and restart.sh")
    write_scripts(api, box, python)
    api.exec(
        box,
        ["sh", "-c", f"mkdir -p {REMOTE_ROOT}/.data/ltcm && chmod 700 {REMOTE_ROOT}/.data "
                     f"{REMOTE_ROOT}/.data/ltcm && touch {REMOTE_ROOT}/ltcm.log && "
                     f"chmod 600 {REMOTE_ROOT}/ltcm.log && rm -f {REMOTE_ROOT}/STOP"],
        timeout=60,
        on_output=None,
    ).check()

    say("")
    say(f"box {box} is up with the code on it and the loop STOPPED.")
    say("next, from this terminal:")
    say("  python3 scripts/floor_box.py secrets    # .env and .data/ltcm/keys -> the box")
    say("  python3 scripts/floor_box.py start      # start trading")
    return 0


def bootstrap_python(api: SailboxClient, box: str) -> str:
    """A Python on the box with `cryptography` in it. A venv when the image allows one.

    `cryptography` is the one dependency the floor has beyond the standard library: the Kalshi and
    Coinbase adapters sign with it. It comes from `pypi.org` and `files.pythonhosted.org`, which
    is why both are on the egress allowlist. Debian package mirrors deliberately are not, so this
    never reaches for `apt`.
    """
    venv = f"{REMOTE_ROOT}/.venv"
    made = api.exec(
        box, ["sh", "-c", f"python3 -m venv {venv} >/dev/null 2>&1 && echo ok || echo no"],
        timeout=300, on_output=None,
    )
    if "ok" in made.stdout:
        python = f"{venv}/bin/python"
        api.exec(
            box, ["sh", "-c", f"{python} -m pip install --disable-pip-version-check --quiet "
                              "--upgrade pip && "
                              f"{python} -m pip install --disable-pip-version-check --quiet "
                              "cryptography"],
            timeout=900, on_output=stream,
        ).check()
        return python
    say("  no venv on this image; installing into the system interpreter instead")
    api.exec(
        box, ["sh", "-c", "python3 -m pip install --disable-pip-version-check --quiet "
                          "--break-system-packages cryptography || "
                          "python3 -m pip install --disable-pip-version-check --quiet "
                          "cryptography"],
        timeout=900, on_output=stream,
    ).check()
    return "python3"


def cmd_deploy(args: argparse.Namespace) -> int:
    state = read_state()
    box = require_box(state)
    api = client()
    files = code_files()
    known = dict(state.get("uploads") or {})
    now = {str(f): digest(REPO_ROOT / f) for f in files}
    changed = [f for f in files if known.get(str(f)) != now[str(f)]]
    removed = sorted(set(known) - set(now))
    if args.all:
        changed = list(files)

    if not changed and not (removed and args.prune):
        say("nothing to deploy: the box already has this working tree")
    else:
        if changed:
            say(f"deploying {len(changed)} changed file(s) to {box}")
            for path in changed[:20]:
                say(f"  {path}")
            if len(changed) > 20:
                say(f"  ... and {len(changed) - 20} more")
            push_code(api, box, changed)
        if removed:
            say(f"{len(removed)} file(s) no longer in the working tree: {', '.join(removed[:10])}")
            if args.prune:
                targets = " ".join(f"{REMOTE_ROOT}/{p}" for p in removed)
                api.exec(box, ["sh", "-c", f"rm -f {targets}"], timeout=120, on_output=None).check()
                say("  removed from the box")
            else:
                say("  left on the box; pass --prune to remove them")
        state["uploads"] = now
        state["deployed_at"] = _now()
        write_state(state)
        # run.sh names the interpreter, so it is rewritten with the code it supervises.
        write_scripts(api, box, state.get("python") or "python3")

    seen = probe(api, box)
    if seen.get("loop.pid", "-") != "-":
        say("the loop is running; restarting it into the new code")
        api.exec(box, ["sh", f"{REMOTE_ROOT}/restart.sh"], timeout=120, on_output=stream)
    else:
        say("the loop is not running; nothing to restart")
    return 0


def cmd_secrets(args: argparse.Namespace) -> int:
    """Push the owner's credentials to the box. The only command here that reads one.

    Run by the owner, from the owner's machine, on purpose. It reads `.env` and every file in
    `.data/ltcm/keys/` as bytes, refuses any of them that is group- or world-readable, uploads
    them mode 600 to `/workspace/.env` and `/workspace/.data/ltcm/keys/`, and prints names and
    byte counts only. No value is decoded, logged or kept.
    """
    state = read_state()
    box = require_box(state)
    api = client()

    sources: list[tuple[Path, str]] = []
    env_path = REPO_ROOT / SECRET_ENV
    if env_path.is_file():
        sources.append((env_path, f"{REMOTE_ROOT}/.env"))
    keys_dir = REPO_ROOT / SECRET_KEYS
    if keys_dir.is_dir():
        for key in sorted(keys_dir.iterdir()):
            if key.is_file() and not key.is_symlink():
                sources.append((key, f"{REMOTE_ROOT}/.data/ltcm/keys/{key.name}"))
    if not sources:
        raise SystemExit(f"nothing to send: no {SECRET_ENV} and no files in {SECRET_KEYS}")

    for source, _ in sources:
        if source.is_symlink():
            raise SystemExit(f"{source.name} is a symlink; refusing")
        if stat.S_IMODE(source.stat().st_mode) & 0o077:
            raise SystemExit(
                f"{source.name} is group- or world-readable. `chmod 600` it first: a credential "
                "that anyone on this machine can read is not one this script will copy anywhere."
            )

    api.exec(
        box,
        ["sh", "-c", f"mkdir -p {REMOTE_ROOT}/.data/ltcm/keys && "
                     f"chmod 700 {REMOTE_ROOT}/.data {REMOTE_ROOT}/.data/ltcm "
                     f"{REMOTE_ROOT}/.data/ltcm/keys"],
        timeout=60,
        on_output=None,
    ).check()

    for source, target in sources:
        raw = source.read_bytes()          # bytes in, bytes out; nothing is parsed or printed
        api.upload(box, target, raw, mode=0o600)
        say(f"  {source.name} -> {target}  ({len(raw):,} bytes, mode 600)")
        del raw

    check = api.exec(
        box,
        ["sh", "-c", f"ls -l {REMOTE_ROOT}/.env {REMOTE_ROOT}/.data/ltcm/keys/ 2>/dev/null "
                     "| awk '{print $1, $NF}'"],
        timeout=60,
        on_output=None,
    )
    say(check.stdout.strip() or "  (no listing)")
    state["secrets_pushed_at"] = _now()
    state["secret_names"] = [s.name for s, _ in sources]
    write_state(state)
    say("")
    say("credentials are on the box. `python3 scripts/floor_box.py start` when ready.")
    say("NOTE: a checkpoint taken from here on carries these files, and so does any fork of it.")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    state = read_state()
    box = require_box(state)
    api = client()
    seen = probe(api, box)
    if seen.get("run.pid", "-") != "-" and not args.force:
        say(f"the supervisor is already running (pid {seen['run.pid']}); nothing to do")
        return 0
    if seen.get("kill", "no") == "yes" and not args.keep_kill_switch:
        say("releasing the kill switch")
        # An exec runs in `/` by default, and `ltcm` is only importable from /workspace.
        api.exec(
            box,
            ["sh", "-c", f"cd {REMOTE_ROOT} && exec {state.get('python') or 'python3'} "
                         "-m ltcm unkill"],
            timeout=180,
            on_output=stream,
        )
    api.exec(box, ["sh", "-c", f"rm -f {REMOTE_ROOT}/STOP"], timeout=60, on_output=None).check()
    say("starting the supervisor")
    api.exec(
        box,
        f"setsid /bin/sh {REMOTE_ROOT}/run.sh >/dev/null 2>&1 < /dev/null",
        timeout=60,
        background=True,
        on_output=None,
    )
    time.sleep(5)
    seen = probe(api, box)
    say(f"  supervisor={seen.get('run.pid')}  loop={seen.get('loop.pid')}")
    if seen.get("run.pid", "-") == "-":
        say("  the supervisor did not come up; check `logs`")
        return 1
    state["started_at"] = _now()
    write_state(state)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """Kill switch first, then quiesce, then stop. In that order, always."""
    state = read_state()
    box = require_box(state)
    api = client()
    python = state.get("python") or "python3"

    say("engaging the kill switch (no new orders from this moment)")
    api.exec(
        box,
        ["sh", "-c", f'cd {REMOTE_ROOT} && exec {python} -m ltcm kill --reason "$1"',
         "floor_box", args.reason],
        timeout=180,
        on_output=stream,
    )
    say("latching the supervisor so the loop is not restarted")
    api.exec(box, ["sh", "-c", f"touch {REMOTE_ROOT}/STOP"], timeout=60, on_output=None).check()

    seen = probe(api, box)
    loop = _pid(seen.get("loop.pid"))
    if loop is None:
        say("  no floor loop was running")
    else:
        say(f"asking the loop (pid {loop}) to finish its tick")
        api.exec(box, ["sh", "-c", f"kill -TERM {loop}"], timeout=60, on_output=None)
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            time.sleep(5)
            seen = probe(api, box)
            if seen.get("loop.pid", "-") == "-":
                say(f"  the loop quiesced after {int(args.timeout - (deadline - time.time()))}s")
                break
        else:
            say(f"  still running after {args.timeout}s; killing it")
            api.exec(box, ["sh", "-c", f"kill -KILL {loop} 2>/dev/null || true"],
                     timeout=60, on_output=None)
            time.sleep(3)

    seen = probe(api, box)
    supervisor = _pid(seen.get("run.pid"))
    if supervisor is not None:
        say(f"stopping the supervisor (pid {supervisor})")
        api.exec(
            box,
            ["sh", "-c", f"kill -TERM {supervisor} 2>/dev/null; sleep 2; "
                         f"kill -KILL {supervisor} 2>/dev/null; "
                         f"rm -f {REMOTE_ROOT}/run.pid {REMOTE_ROOT}/loop.pid; true"],
            timeout=90,
            on_output=None,
        )
    state["stopped_at"] = _now()
    write_state(state)
    say("stopped. The kill switch stays engaged; `start` releases it (or --keep-kill-switch).")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state = read_state()
    box = require_box(state)
    api = client()
    policy = expected_policy(state)
    report = api.status(box, expected_egress=policy)
    seen = probe(api, box)
    report["loop"] = {
        "supervisor_pid": seen.get("run.pid"),
        "loop_pid": seen.get("loop.pid"),
        "alive": seen.get("loop.pid", "-") != "-",
        "stop_latch": seen.get("stop") == "yes",
        "kill_switch": seen.get("kill") == "yes",
    }
    report["hourly_cost_usd"] = hourly_cost(report, report.get("spend") or {})
    report["floor_health"] = health(api, box)
    tail = ""
    try:
        tail = api.exec(
            box, ["sh", "-c", f"tail -n {int(args.tail)} {REMOTE_ROOT}/ltcm.log 2>/dev/null"],
            timeout=60, on_output=None,
        ).stdout
    except SailboxError:
        pass
    if args.json:
        report["log_tail"] = tail.splitlines()[-int(args.tail):]
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 0

    say(f"box          {report['sailbox_id']}  ({report.get('name')})")
    say(f"state        {report.get('status')}   auto_sleep={report.get('auto_sleep')}")
    say(f"size         s  vcpu={report.get('vcpu_count')} "
        f"memory_mib={report.get('memory_mib')} disk_gib={report.get('state_disk_size_gib')}")
    say(f"using        cpu={report.get('cpu_used_vcpu')} vCPU  "
        f"mem={_gib(report.get('memory_used_bytes'))}  disk={_gib(report.get('disk_used_bytes'))}")
    spend = report.get("spend") or {}
    say(f"spend        ${spend.get('total_usd', 0):.4f} since {str(spend.get('from'))[:10]}  "
        f"(~${report['hourly_cost_usd']:.4f}/h at this usage)")
    say(f"egress       {len(report.get('egress') or [])} hosts, "
        f"matches the recorded policy: {report.get('egress_ok')}")
    loop = report["loop"]
    say(f"loop         alive={loop['alive']} supervisor={loop['supervisor_pid']} "
        f"loop={loop['loop_pid']} stop_latch={loop['stop_latch']} kill={loop['kill_switch']}")
    floor = report.get("floor_health")
    if isinstance(floor, Mapping):
        say(f"floor        {floor.get('status')}  equity={(floor.get('floor') or {}).get('equity')}"
            f"  events={floor.get('events')}  updated={floor.get('updated_at')}")
        say(f"             spent_today={(floor.get('budget') or {}).get('spent_today_usd')} "
            f"cap={(floor.get('budget') or {}).get('cap_usd')} "
            f"last_error={floor.get('last_error')}")
    else:
        say("floor        no health.json on the box yet (the loop has never ticked)")
    checkpoints = state.get("checkpoints") or []
    if checkpoints:
        say(f"checkpoints  {len(checkpoints)}, newest {checkpoints[-1].get('name')} "
            f"({checkpoints[-1].get('checkpoint_id')})")
    if tail.strip():
        say("")
        say(f"--- last {args.tail} lines of {REMOTE_ROOT}/ltcm.log ---")
        say(tail.rstrip())
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    state = read_state()
    box = require_box(state)
    api = client()
    result = api.exec(
        box,
        ["sh", "-c", f"tail -n {int(args.lines)} {REMOTE_ROOT}/ltcm.log 2>/dev/null "
                     "|| echo '(no log yet)'"],
        timeout=120,
        on_output=None,
    )
    print(result.stdout.rstrip() or f"({REMOTE_ROOT}/ltcm.log is empty: the loop has never run)")
    return 0


def cmd_checkpoint(args: argparse.Namespace) -> int:
    state = read_state()
    box = require_box(state)
    api = client()
    seen = probe(api, box)
    running = seen.get("loop.pid", "-") != "-"
    name = args.name or f"ltcm-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}"
    say(f"checkpointing {box} as {name} (ttl {args.ttl_days} days)")
    row = api.checkpoint(box, name=name, ttl_seconds=int(args.ttl_days) * 86400)
    entry = {
        "checkpoint_id": row["checkpoint_id"],
        "name": name,
        "at": _now(),
        "expires_at": row.get("expires_at"),
        "generation": row.get("checkpoint_generation"),
        "loop_was_running": running,
        "carries_secrets": bool(state.get("secrets_pushed_at")),
    }
    state.setdefault("checkpoints", []).append(entry)
    write_state(state)
    say(f"  {entry['checkpoint_id']}  expires {entry['expires_at']}  "
        f"generation {entry['generation']}")
    if entry["carries_secrets"]:
        say("  NOTE: credentials are on this box, so this checkpoint contains them. Anything "
            "forked from it can reach the live venues.")
    return 0


def cmd_checkpoints(args: argparse.Namespace) -> int:
    state = read_state()
    box = require_box(state)
    api = client()
    report = api.checkpoints(box, recorded=state.get("checkpoints") or ())
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


def cmd_fork(args: argparse.Namespace) -> int:
    """A second box from a checkpoint. The loop is NOT started, and is latched off."""
    state = read_state()
    api = client()
    recorded = {c.get("checkpoint_id"): c for c in (state.get("checkpoints") or [])}
    source = recorded.get(args.source, {})
    if source.get("loop_was_running") and not args.i_know:
        raise SystemExit(
            f"{args.source} was taken while the floor loop was running. A fork inherits memory, "
            "so a background process carries on in the copy -- that is a second floor trading the "
            "same book. Take a checkpoint with the loop stopped, or pass --i-know."
        )
    name = args.name or f"{state.get('name', DEFAULT_NAME)}-fork-{uuid.uuid4().hex[:6]}"
    say(f"starting {name} from {args.source}")
    row = api.from_checkpoint(args.source, name=name)
    fork = row["sailbox_id"]
    say(f"  {fork}  status={row.get('status')}")

    # A fork inherits the disk *and the memory*: latch the supervisor off and stop anything that
    # came back with it, before it can place an order.
    say("  latching the loop off on the copy")
    api.exec(
        fork,
        ["sh", "-c", f"touch {REMOTE_ROOT}/STOP; "
                     f"for f in loop.pid run.pid; do p=$(cat {REMOTE_ROOT}/$f 2>/dev/null); "
                     'if [ -n "$p" ] && [ -d "/proc/$p" ]; then kill -TERM "$p" 2>/dev/null; fi; '
                     f"done; sleep 2; rm -f {REMOTE_ROOT}/run.pid {REMOTE_ROOT}/loop.pid; true"],
        timeout=120,
        on_output=None,
    )
    seen = probe(api, fork)
    say(f"  loop on the copy: supervisor={seen.get('run.pid')} loop={seen.get('loop.pid')}")
    entry = {
        "sailbox_id": fork,
        "name": name,
        "from_checkpoint": args.source,
        "at": _now(),
        "inherits_secrets": bool(source.get("carries_secrets", state.get("secrets_pushed_at"))),
    }
    state.setdefault("forks", []).append(entry)
    write_state(state)
    report = api.verify_egress(fork, expected_policy(state))
    say(f"  egress inherited from the parent, matches: {report['ok']} "
        f"({len(report['allowlist'])} hosts)")
    if entry["inherits_secrets"]:
        say("  WARNING: this copy has the parent's credentials on its disk and can reach the live "
            "venues. Put it in paper mode, or wipe /workspace/.data/ltcm/keys and /workspace/.env, "
            "before starting anything on it.")
    say(f"  it bills like any Sailbox until you terminate it: "
        f"python3 scripts/floor_box.py terminate --box {fork} --yes")
    return 0


def cmd_sleep(args: argparse.Namespace) -> int:
    state = read_state()
    box = args.box or require_box(state)
    row = client().sleep(box, wake_at=args.wake_at)
    say(json.dumps(row, sort_keys=True))
    say("a sleeping Sailbox costs nothing; a command, a file transfer or `resume` wakes it.")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    state = read_state()
    box = args.box or require_box(state)
    row = client().resume(box)
    say(json.dumps(row, sort_keys=True))
    say("the loop is whatever it was before the sleep; `status` says, `start` starts it.")
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    state = read_state()
    box = args.box or require_box(state)
    say(json.dumps(client().pause(box), sort_keys=True))
    say("paused: only an explicit `resume` brings it back.")
    return 0


def cmd_terminate(args: argparse.Namespace) -> int:
    state = read_state()
    box = args.box or require_box(state)
    if not args.yes:
        raise SystemExit(f"this destroys {box} and its disk for good. Pass --yes to mean it.")
    say(json.dumps(client().terminate(box), sort_keys=True))
    if box == state.get("box_id"):
        state["terminated_at"] = _now()
        state["box_id"] = None
        write_state(state)
    say("terminated. Billing stops; the disk is gone.")
    return 0


def cmd_hosts(args: argparse.Namespace) -> int:
    """What the floor may reach. With --add, widen the live allowlist and record it."""
    state = read_state()
    if getattr(args, "add", None):
        client = SailboxClient()
        box = require_box(state)
        live = client.egress(box)
        hosts = policy_allowlist(live) or list(
            expected_policy(state)["allowlist"]
        )
        wanted = sorted(set(hosts) | {h.strip().lower() for h in args.add if h.strip()})
        readback = client.set_egress(box, wanted)
        got = policy_allowlist(readback)
        missing = [h for h in wanted if h not in got]
        if missing:
            raise SystemExit(f"the live policy does not carry: {', '.join(missing)}")
        state["egress_allowlist"] = got
        for host in args.add:
            if "workers.dev" in host:
                state["gateway_host"] = host.strip().lower()
        write_state(state)
        say(f"allowlist now {len(got)} hosts; added {', '.join(args.add)}")
        return 0
    policy = expected_policy(state)
    for host in policy["allowlist"]:
        say(f"  {host}")
    say(f"({len(policy['allowlist'])} hosts; everything else is closed by Sail, not by the floor)")
    say(f"base list: {len(FLOOR_HOSTS)} hosts + the gateway "
        f"({state.get('gateway_host') or GATEWAY_HOST})")
    return 0


def _pid(value: Any) -> int | None:
    """A pid from the probe, or None. A malformed one must not derail a stop."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 1 else None


def _gib(value: Any) -> str:
    try:
        return f"{int(value) / 1024 ** 3:.2f} GiB"
    except (TypeError, ValueError):
        return "?"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


COMMANDS = {
    "create": cmd_create,
    "deploy": cmd_deploy,
    "secrets": cmd_secrets,
    "start": cmd_start,
    "stop": cmd_stop,
    "status": cmd_status,
    "logs": cmd_logs,
    "checkpoint": cmd_checkpoint,
    "checkpoints": cmd_checkpoints,
    "fork": cmd_fork,
    "sleep": cmd_sleep,
    "resume": cmd_resume,
    "pause": cmd_pause,
    "terminate": cmd_terminate,
    "hosts": cmd_hosts,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="floor_box.py",
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Box state: .data/ltcm/box.json (owner-only, no credentials).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create the box, upload the floor, install, stop")
    create.add_argument("--app", default=DEFAULT_APP)
    create.add_argument("--name", default=DEFAULT_NAME)
    create.add_argument("--visibility", default="private", choices=("private", "org"))
    create.add_argument(
        "--gateway-host",
        default=GATEWAY_HOST,
        help="the publish gateway to allow; a wildcard is accepted by Sail (default %(default)s)",
    )
    create.add_argument("--force", action="store_true", help="create a second box anyway")

    deploy = sub.add_parser("deploy", help="re-upload changed code, restart a running loop")
    deploy.add_argument("--all", action="store_true", help="upload every file, not just changed")
    deploy.add_argument("--prune", action="store_true", help="delete files no longer in the tree")

    sub.add_parser("secrets", help="upload .env and .data/ltcm/keys (the owner runs this)")

    start = sub.add_parser("start", help="start the supervised floor loop")
    start.add_argument("--force", action="store_true")
    start.add_argument("--keep-kill-switch", action="store_true",
                       help="start the loop with the kill switch still engaged")

    stop = sub.add_parser("stop", help="kill switch, quiesce, then stop the loop")
    stop.add_argument("--timeout", type=float, default=120.0)
    stop.add_argument("--reason", default="operator stop")

    status = sub.add_parser("status", help="box, spend, loop, log tail and the floor's health")
    status.add_argument("--json", action="store_true")
    status.add_argument("--tail", type=int, default=15)

    logs = sub.add_parser("logs", help="tail /workspace/ltcm.log")
    logs.add_argument("-n", "--lines", type=int, default=100)

    checkpoint = sub.add_parser("checkpoint", help="checkpoint the box and record the id")
    checkpoint.add_argument("--name")
    checkpoint.add_argument("--ttl-days", type=int, default=30)

    sub.add_parser("checkpoints", help="the checkpoints recorded for this box")

    fork = sub.add_parser("fork", help="a second box from a checkpoint; the loop is NOT started")
    fork.add_argument("--from", dest="source", required=True, metavar="CHECKPOINT")
    fork.add_argument("--name")
    fork.add_argument("--i-know", action="store_true",
                      help="fork a checkpoint that was taken with the loop running")

    for name, help_text in (("sleep", "sleep the box"), ("resume", "resume it"),
                            ("pause", "pause it (only resume brings it back)")):
        node = sub.add_parser(name, help=help_text)
        node.add_argument("--box")
        if name == "sleep":
            node.add_argument("--wake-at", help="RFC 3339 time to wake it again")

    terminate = sub.add_parser("terminate", help="destroy a box and its disk")
    terminate.add_argument("--box")
    terminate.add_argument("--yes", action="store_true")

    hosts = sub.add_parser("hosts", help="print the egress allowlist this box runs under")
    hosts.add_argument("--add", nargs="+", metavar="HOST", help="add hosts to the live allowlist")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except SailboxError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
