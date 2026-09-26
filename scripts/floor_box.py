#!/usr/bin/env python3
"""Operate the House's Sailbox from the owner's terminal.

The MacBook is not the floor: it is the operator console. The House (`python3 -m league run`) runs
on one trusted Sailbox and this script is the only thing that talks to it.

    python3 scripts/floor_box.py create            one size-s box, egress allowlist, venv, run.sh
    python3 scripts/floor_box.py secrets           the three values the box holds -> /workspace/.env
    python3 scripts/floor_box.py deploy            upload a release; the in-box watchdog stages it,
                                                   canaries it, promotes it, watches it, rolls back
    python3 scripts/floor_box.py start             start the supervised `python -m league run` loop
    python3 scripts/floor_box.py status            box, spend, loop, releases, health.json, log tail
    python3 scripts/floor_box.py logs -n 200       the tail of /workspace/league.log (--deploy: deploy.log)
    python3 scripts/floor_box.py checkpoint --name after-upgrade
    python3 scripts/floor_box.py fork --from sbcp_...      a second box, loop NOT started
    python3 scripts/floor_box.py stop              latch both STOP files, quiesce, stop the loop
    python3 scripts/floor_box.py sleep | resume | pause | terminate --yes

The box, under /workspace:

    releases/<id>/    one full code tree per release, never edited again
    current, previous symlinks into releases/, managed ONLY by `league.watchdog`
    state/            the House's state: ledger, health.json, STOP, sandbox.json ...
    canary/           throwaway state for canary runs
    incoming/<id>/    where an upload is unpacked before the watchdog stages it
    .env              the three secrets, mode 600
    run.sh restart.sh run.pid loop.pid deploy.pid league.log deploy.log deploys.jsonl .venv

`/workspace/ltcm`, `/workspace/.data`, `/workspace/.archive` and `/workspace/ltcm.log` are the first
run's history. Nothing this script does for the league reads, deletes, moves or overwrites them.

What this script will not do:

- **It never reads a secret except in `secrets`.** The code upload refuses `.env`, anything under
  `.data/`, and any private-key file, whatever the working tree holds. `secrets` is the one
  command that touches them, it uploads bytes it never decodes, and it prints names and sizes.
- **It never prints the Sail key.** The key is fetched inside `ltcm.sailbox` through
  `ltcm.provider.default_key_source()` at the moment of each request.
- **It never starts trading by itself.** `create` and `deploy` leave the loop exactly as they
  found it; only `start` starts it.
- **It never decides about real money.** That is `real_money` in `league/config.json` and the
  gateway's kill switch. This script changes neither.
- **It never moves `current` or `previous`.** A release becomes current because the in-box
  watchdog promoted it, and stops being current because the watchdog rolled it back.

Box state lives in `.data/ltcm/box.json`: ids, names, the allowlist in effect, the releases sent
and their verdicts, and the checkpoints taken. It is owner-only (mode 600) and holds no credential.
"""

from __future__ import annotations

import argparse
import gzip
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

#: What a release is made of. The league imports its venue adapters, broker types, risk engine,
#: provider and data readers from `ltcm`, so both ride along; each package carries its config.json.
UPLOAD_TREES = ("league", "ltcm", "playbooks", "scripts", "deploy")

#: Never uploaded by the code path, whatever the working tree looks like.
SKIP_DIRS = {"__pycache__", ".git", ".venv", ".data", ".ruff_cache", ".pytest_cache", "history"}
SKIP_SUFFIXES = (".pyc", ".pyo", ".pem", ".key", ".p8", ".pfx", ".crt", ".der", ".sqlite")
SKIP_NAMES = {".env", ".DS_Store"}

#: The only files `secrets` sends, and the only place this script reads a credential.
SECRET_ENV = ".env"
#: What the box needs in gateway mode, and all it gets. Venue keys are the gateway's.
BOX_ENV_NAMES = ("SAIL_API_KEY", "GATEWAY_TOKEN", "CAPITAL_PUBLISH_TOKEN")


#: The box's layout (see the module docstring). Everything the league touches is one of these.
ENV_FILE = f"{REMOTE_ROOT}/.env"
STATE_DIR = f"{REMOTE_ROOT}/state"
INCOMING_DIR = f"{REMOTE_ROOT}/incoming"
LEAGUE_LOG = f"{REMOTE_ROOT}/league.log"
DEPLOY_LOG = f"{REMOTE_ROOT}/deploy.log"
DEPLOYS_JSONL = f"{REMOTE_ROOT}/deploys.jsonl"
#: The supervisor's latch and the league's own. Either one ends the loop.
STOP_FILES = (f"{REMOTE_ROOT}/STOP", f"{STATE_DIR}/STOP")

#: `league.watchdog deploy` exit codes, mirrored by `deploy` here. 1: no verdict was seen.
VERDICT_EXIT = {"promoted": 0, "refused": 2, "rolled_back": 3, "failed": 4}
KEEP_RELEASES = 20

#: What the league needs to reach. `hosts` says which of these the recorded allowlist lacks.
LEAGUE_HOSTS = (
    "api.sailresearch.com",          # cheap-model inference and search
    "sailbox-api.sailresearch.com",  # the agents' boxes
    "blakewoods.us",                 # the public site
    "api.elections.kalshi.com",      # Kalshi market data (orders go through the gateway)
    "news.google.com",               # the commons' news reader
    "github.com",                    # merged code, pulled without credentials
    "codeload.github.com",
    "api.github.com",                # the check runs on the exact commit the updater deploys (league/updater.py)
    # The live feeds the House records for its strategies (league/feeds.py): ESPN's scoreboards, and
    # perpetual funding, open interest and DVOL. On FLOOR_HOSTS since the arena of Sept 18, 2026.
    "site.api.espn.com",
    "www.okx.com",
    "www.deribit.com",
    "api.hyperliquid.xyz",
    "futures.kraken.com",
    # The key-free data hosts the owner allowed on Sept 24, 2026 for the close-the-gaps run's
    # recorders (docs/goals/LTCM_CLOSE_THE_GAPS.md, workstream I). Weather: Open-Meteo's forecast,
    # ensemble and historical-forecast APIs, and the NWS API (the settlement authority's own
    # forecast; NWS and SEC ask for a User-Agent naming the requester and a contact address).
    # Earnings times: EDGAR full-text search and Nasdaq's calendar. Rates: SOFR and par yields.
    # Sports: ESPN's core API carries odds and win probabilities. Attention: TSA volumes and
    # polling averages, HTML pages. The keyed hosts (api.eia.gov, api.the-odds-api.com) stay the
    # owner's step.
    "api.open-meteo.com",
    "ensemble-api.open-meteo.com",
    "historical-forecast-api.open-meteo.com",
    "api.weather.gov",
    "www.sec.gov",
    "efts.sec.gov",
    "api.nasdaq.com",
    "markets.newyorkfed.org",
    "home.treasury.gov",
    "sports.core.api.espn.com",
    "www.tsa.gov",
    "www.realclearpolling.com",
    # The key-free data hosts added by the Kalshi-scale run on Sept 25-26, 2026 (workstream I2, the
    # owner's standing approval): each passed the plan's rule -- key-free, public, terms that permit
    # automated access, no bot wall -- and has a recorder in league/open_feeds.py (its docstring names
    # the terms read). Settlement weather: the IEM's parse of the NWS climate reports, the Aviation
    # Weather Center's METARs, NCEI's daily summaries.
    "mesonet.agron.iastate.edu",
    "aviationweather.gov",
    "www.ncei.noaa.gov",
    # Macro releases and calendars: BLS's public data API (v1, key-free: 25 queries a day), the
    # Treasury's FiscalData, the ECB's euro reference rates, the CFTC's Commitments of Traders
    # (Socrata, no token) and the Federal Reserve Board's FOMC calendar.
    "api.bls.gov",
    "api.fiscaldata.treasury.gov",
    "www.ecb.europa.eu",
    "publicreporting.cftc.gov",
    "www.federalreserve.gov",
    # Attention, hazards and crypto network data: Wikimedia's pageviews, GDELT's news volume and tone,
    # the National Hurricane Center's active storms, the USGS earthquake feed, mempool.space's
    # bitcoin mempool and fees, and alternative.me's crypto fear and greed index.
    "wikimedia.org",
    "api.gdeltproject.org",
    "www.nhc.noaa.gov",
    "earthquake.usgs.gov",
    "mempool.space",
    "api.alternative.me",
    # Government releases and notices: the White House's presidential actions (what Kalshi's
    # KXTRUMPACT settles on), the Federal Register's API, EIA's public price tables, the NWS's raw
    # climate reports as issued, BLS's and BEA's release calendars, and Nasdaq's trade halts.
    "www.whitehouse.gov",
    "www.federalregister.gov",
    "www.eia.gov",
    "tgftp.nws.noaa.gov",
    "www.bls.gov",
    "www.bea.gov",
    "www.nasdaqtrader.com",
)


def floor_config() -> dict[str, Any]:
    """The packaged config that names the gateway: the league's, else the first run's, else {}."""
    for package in ("league", "ltcm"):
        try:
            config = json.loads((REPO_ROOT / package / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(config, dict) and config.get("gateway_url"):
            return config
    return {}


def compose_box_env(raw: bytes) -> bytes:
    """The lines of a local `.env` the box may hold, in a fixed order, nothing else."""
    values: dict[str, bytes] = {}
    for line in raw.splitlines():
        if b"=" not in line or line.lstrip().startswith(b"#"):
            continue
        name, value = line.split(b"=", 1)
        values[name.strip().decode("ascii", "replace")] = value.strip()
    return b"".join(f"{name}=".encode() + values[name] + b"\n" for name in BOX_ENV_NAMES if values.get(name))


SECRET_KEYS = Path(".data") / "ltcm" / "keys"

RUN_SH = """#!/bin/sh
# The House's supervisor. Written by scripts/floor_box.py; edit there, not here.
#
# One `python -m league run` at a time, started from whatever {root}/current points at WHEN IT
# STARTS: the link is resolved again on every restart, which is how a promotion or a rollback by
# league.watchdog takes effect. Restarted 30 s after it exits, logging to {root}/league.log.
# {root}/STOP (what `floor_box.py stop` writes) or {root}/state/STOP (the league's own
# `python -m league stop`) ends the loop, so a deliberate stop is never undone by the restart delay.
set -u
cd {root} || exit 1
umask 077
echo $$ > {root}/run.pid
stamp() {{ date -u +%Y-%m-%dT%H:%M:%SZ; }}
stopped() {{ [ -e {root}/STOP ] || [ -e {root}/state/STOP ]; }}
while ! stopped; do
  cd {root}/current || {{ printf '%s  supervisor: no {root}/current to start from\\n' "$(stamp)" >> {root}/league.log; sleep 30; continue; }}
  printf '%s  supervisor: starting the House from %s\\n' "$(stamp)" "$(pwd -P)" >> {root}/league.log
  LEAGUE_ENV={root}/.env {python} -m league run --root {root}/state >> {root}/league.log 2>&1 &
  child=$!
  echo "$child" > {root}/loop.pid
  wait "$child"
  code=$?
  rm -f {root}/loop.pid
  printf '%s  supervisor: the House exited (%s)\\n' "$(stamp)" "$code" >> {root}/league.log
  stopped && break
  sleep 30
done
printf '%s  supervisor: stopped\\n' "$(stamp)" >> {root}/league.log
rm -f {root}/run.pid {root}/loop.pid
"""

RESTART_SH = """#!/bin/sh
# Restart the House in place, without disturbing the supervisor: signal the running
# `python -m league run` and let run.sh bring a fresh one up, from {root}/current, after its
# 30 s delay. Both watchdogs call this: league.watchdog after a promotion or a rollback, and the
# gateway's when the public checkpoint goes stale. It never starts a supervisor that is not up.
set -u
pid=$(cat {root}/loop.pid 2>/dev/null || true)
if [ -n "${{pid:-}}" ] && [ -d "/proc/$pid" ]; then
  kill -TERM "$pid" && echo "signalled $pid; the supervisor restarts it in 30s"
else
  echo "no floor loop is running"
fi
"""

#: The supervisor, the loop, a running deploy, both stop files, the two links, the .env.
PROBE = (
    "for f in run.pid loop.pid deploy.pid; do "
    'p=$(cat %(root)s/$f 2>/dev/null || true); '
    'if [ -n "$p" ] && [ -d "/proc/$p" ]; then echo "$f=$p"; else echo "$f=-"; fi; '
    "done; "
    "[ -e %(root)s/STOP ] && echo stop=yes || echo stop=no; "
    "[ -e %(root)s/state/STOP ] && echo league_stop=yes || echo league_stop=no; "
    'echo "current=$(readlink %(root)s/current 2>/dev/null || true)"; '
    'echo "previous=$(readlink %(root)s/previous 2>/dev/null || true)"; '
    "[ -f %(root)s/current/league/__main__.py ] && echo runnable=yes || echo runnable=no; "
    "[ -s %(root)s/.env ] && echo env=yes || echo env=no"
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


def tarball(files: Sequence[Path]) -> bytes:
    """A deterministic gzip tar of the given repository-relative files: the same tree is the same
    bytes whenever it is packed (no file times, no owners, and no time in the gzip header), so
    the sha256 of the bundle names its content."""
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
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


def release_id_for(blob: bytes, *, now: float | None = None) -> str:
    """`YYYYMMDDTHHMMSSZ-<first 12 hex of the bundle's sha256>`: when it was sent, and what it is."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(time.time() if now is None else now))
    return f"{stamp}-{hashlib.sha256(blob).hexdigest()[:12]}"


def release_of(link: Any) -> str | None:
    """The release id a `readlink` of `current` or `previous` names (`releases/<id>`), or None."""
    name = str(link or "").strip().rstrip("/").rpartition("/")[2]
    return name or None


def content_of(release_id: Any) -> str:
    """The content part of a release id made here: the 12 hex after the last dash."""
    return str(release_id or "").rpartition("-")[2]


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
    """The supervisor, the loop, a running deploy, both stop files and the two release links."""
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


def up(seen: Mapping[str, str], name: str) -> bool:
    """Did the probe find the process whose pid file is `name` alive?"""
    return _pid(seen.get(name)) is not None


def push_release(api: SailboxClient, box: str, release_id: str, blob: bytes) -> str:
    """Upload one bundle and unpack it into `/workspace/incoming/<id>/`. Returns that directory.

    `incoming/` holds one upload at a time: the watchdog copies what it stages into `releases/`,
    so whatever an earlier deploy left here is spent. Nothing outside `incoming/` and `.upload/`
    is written."""
    name = f"{REMOTE_ROOT}/.upload/release-{release_id}.tgz"
    target = f"{INCOMING_DIR}/{release_id}"
    api.upload(box, name, blob, mode=0o600)
    api.exec(
        box,
        ["sh", "-c", f"set -e; umask 077; rm -rf {INCOMING_DIR}; mkdir -p {target}; "
                     f"tar -xzf {name} -C {target} --no-same-owner; rm -f {name}; "
                     f"test -f {target}/league/__main__.py"],
        timeout=300,
        on_output=None,
    ).check()
    return target


def render(template: str, python: str) -> bytes:
    return template.format(root=REMOTE_ROOT, python=python).encode("utf-8")


def supervisor_script(api: SailboxClient, box: str) -> bytes | None:
    """The run.sh on the box now, or None when there is none."""
    try:
        return bytes(api.download(box, f"{REMOTE_ROOT}/run.sh"))
    except SailboxError:
        return None


def write_scripts(api: SailboxClient, box: str, python: str) -> None:
    """run.sh and restart.sh, each renamed into place: a supervisor that is running keeps reading
    the file it opened, where writing over that file would change the script under its feet."""
    for name, template in (("run.sh", RUN_SH), ("restart.sh", RESTART_SH)):
        api.upload(box, f"{REMOTE_ROOT}/{name}.new", render(template, python), mode=0o700)
    api.exec(
        box,
        ["sh", "-c", f"mv -f {REMOTE_ROOT}/run.sh.new {REMOTE_ROOT}/run.sh && "
                     f"mv -f {REMOTE_ROOT}/restart.sh.new {REMOTE_ROOT}/restart.sh"],
        timeout=60,
        on_output=None,
    ).check()


def health(api: SailboxClient, box: str) -> Any:
    """The House's own `health.json`, written at the end of every tick."""
    try:
        raw = api.download(box, f"{STATE_DIR}/health.json")
    except SailboxError:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def deploy_rows(api: SailboxClient, box: str, *, lines: int = 60) -> list[dict[str, Any]]:
    """The last rows of `/workspace/deploys.jsonl`, the watchdog's own record. Oldest first."""
    try:
        raw = api.exec(box, ["sh", "-c", f"tail -n {int(lines)} {DEPLOYS_JSONL} 2>/dev/null"],
                       timeout=60, on_output=None).stdout
    except SailboxError:
        return []
    rows = []
    for line in raw.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def verdict_in(rows: Sequence[Mapping[str, Any]], release_id: str) -> dict[str, Any] | None:
    """The newest verdict for one release among watchdog rows (`status` or `deploys.jsonl`)."""
    for row in reversed(list(rows)):
        if row.get("release") == release_id and row.get("verdict"):
            reasons = row.get("reasons")
            return {"verdict": str(row["verdict"]), "at": row.get("at"),
                    "reasons": [str(r) for r in reasons] if isinstance(reasons, list) else []}
    return None


def watchdog_launch(python: str, release_id: str, *, watch: bool) -> str:
    """The shell line that starts `league.watchdog deploy` detached from the exec that runs it.

    The canary plus the watch outlasts any exec timeout, so the watchdog gets a session of its own
    and writes to `deploy.log`. It runs from the known-good code when there is some: the release
    being judged must not be the code that judges it. Without `watch` it promotes and returns: a
    first deploy, or a box whose loop is not up, has no running House to watch."""
    source = f"{INCOMING_DIR}/{release_id}"
    flags = f"--base {REMOTE_ROOT} --source {source} --id {release_id}" + ("" if watch else " --watch-seconds 0")
    return (
        f"umask 077; cd {REMOTE_ROOT}/current 2>/dev/null || cd {source}; "
        f"LEAGUE_ENV={ENV_FILE} setsid nohup {python} -m league.watchdog deploy {flags} "
        f"> {DEPLOY_LOG} 2>&1 < /dev/null & echo $! > {REMOTE_ROOT}/deploy.pid"
    )


def watchdog_status(python: str, release_id: str) -> str:
    return (f"cd {REMOTE_ROOT}/current 2>/dev/null || cd {INCOMING_DIR}/{release_id}; "
            f"exec {python} -m league.watchdog status --base {REMOTE_ROOT}")


def read_verdict(api: SailboxClient, box: str, python: str, release_id: str) -> dict[str, Any] | None:
    """Has the watchdog judged this release yet? `league.watchdog status` is asked first; when it
    cannot answer (a box mid-promotion, a release whose own `status` is broken) the record it
    appends to is read directly."""
    try:
        result = api.exec(box, ["sh", "-c", watchdog_status(python, release_id)], timeout=120, on_output=None)
        report = json.loads(result.stdout)
        rows = report.get("last_deploys") if isinstance(report, dict) else None
        if isinstance(rows, list):
            return verdict_in([r for r in rows if isinstance(r, dict)], release_id)
    except (SailboxError, ValueError):
        pass
    return verdict_in(deploy_rows(api, box), release_id)


def watchdog_progress(api: SailboxClient, box: str, *, lines: int = 3) -> tuple[bool | None, list[str]]:
    """Is the detached watchdog still running, and the tail of what it has said."""
    try:
        out = api.exec(
            box,
            ["sh", "-c", f"p=$(cat {REMOTE_ROOT}/deploy.pid 2>/dev/null || true); "
                         'if [ -n "$p" ] && [ -d "/proc/$p" ]; then echo alive; else echo gone; fi; '
                         f"tail -n {int(lines)} {DEPLOY_LOG} 2>/dev/null"],
            timeout=60, on_output=None,
        ).stdout.splitlines()
    except SailboxError:
        return None, []
    return (out[0].strip() == "alive" if out else None), [line for line in out[1:] if line.strip()]


def await_verdict(api: SailboxClient, box: str, python: str, release_id: str, *,
                  timeout: float, every: float) -> dict[str, Any]:
    """Poll until the watchdog records a verdict for the release, it dies without one, or
    `timeout` seconds pass. Returns `{"verdict": name | None, "reasons": [...], "why": ...}`."""
    deadline = time.time() + float(timeout)
    gone, said = 0, ""
    while True:
        found = read_verdict(api, box, python, release_id)
        if found is not None:
            return found
        alive, tail = watchdog_progress(api, box)
        if tail and tail[-1] != said:
            said = tail[-1]
            say(f"  {said[:200]}")
        gone = gone + 1 if alive is False else 0
        if gone >= 2:
            # Twice in a row, so a watchdog that is only just starting is not called dead; and
            # one last read, because the verdict is the last thing it writes before it exits.
            found = read_verdict(api, box, python, release_id)
            return found or {"verdict": None, "reasons": [], "why": "the watchdog exited without recording a verdict"}
        if time.time() >= deadline:
            return {"verdict": None, "reasons": [], "why": f"no verdict after {int(timeout)}s; the watchdog is still running on the box"}
        time.sleep(max(1.0, float(every)))


def remember_release(state: dict[str, Any], entry: Mapping[str, Any]) -> None:
    """Record or update one release in box.json. Newest last, the last KEEP_RELEASES kept."""
    rows = [r for r in (state.get("releases") or []) if isinstance(r, dict) and r.get("id") != entry.get("id")]
    rows.append(dict(entry))
    state["releases"] = rows[-KEEP_RELEASES:]


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
        "releases": [],
    }
    write_state(state)

    say(f"creating a size-s Sailbox named {args.name} (this blocks until it boots)")
    say(f"  egress allowlist ({len(policy['allowlist'])}): {', '.join(policy['allowlist'])}")
    row = api.create(
        app=app["id"],
        name=args.name,
        size="s",
        egress=policy,
        # Never sleep on its own: the House must be awake for every tick. The tick's own timer
        # would keep it awake anyway (an idle Sailbox is one where "no process is waiting on a
        # timer"), but that is a side effect of a config value, not a guarantee. This is.
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

    say("preparing the interpreter")
    python = bootstrap_python(api, box)
    state["python"] = python
    write_state(state)
    say(f"  interpreter: {python}")

    say("writing run.sh and restart.sh, and laying out /workspace")
    write_scripts(api, box, python)
    api.exec(
        box,
        ["sh", "-c", f"umask 077; mkdir -p {REMOTE_ROOT}/releases {STATE_DIR} {REMOTE_ROOT}/canary "
                     f"{INCOMING_DIR} && chmod 700 {STATE_DIR} {REMOTE_ROOT}/canary && "
                     f"touch {LEAGUE_LOG} && chmod 600 {LEAGUE_LOG}"],
        timeout=60,
        on_output=None,
    ).check()

    say("")
    say(f"box {box} is up with no code on it yet and the loop STOPPED.")
    say("next, from this terminal:")
    say("  python3 scripts/floor_box.py secrets    # the three values -> /workspace/.env")
    say("  python3 scripts/floor_box.py deploy     # the first release (its canary needs the .env)")
    say("  python3 scripts/floor_box.py start      # start the House")
    return 0


def bootstrap_python(api: SailboxClient, box: str) -> str:
    """A Python on the box: a venv when the image allows one, else the system interpreter.

    The league is standard library only: the gateway signs every venue request, so nothing on the
    box needs `cryptography` to run. `ltcm.adapters` still imports it lazily (its direct-signing
    path, which the box never takes), so it is installed when it can be and its absence is said
    and survived. It comes from `pypi.org` and `files.pythonhosted.org`, both on the allowlist;
    Debian package mirrors deliberately are not, so this never reaches for `apt`.
    """
    venv = f"{REMOTE_ROOT}/.venv"
    made = api.exec(
        box, ["sh", "-c", f"python3 -m venv {venv} >/dev/null 2>&1 && echo ok || echo no"],
        timeout=300, on_output=None,
    )
    if "ok" in made.stdout:
        python = f"{venv}/bin/python"
        install = (f"{python} -m pip install --disable-pip-version-check --quiet --upgrade pip; "
                   f"{python} -m pip install --disable-pip-version-check --quiet cryptography")
    else:
        say("  no venv on this image; using the system interpreter instead")
        python = "python3"
        install = ("python3 -m pip install --disable-pip-version-check --quiet "
                   "--break-system-packages cryptography || "
                   "python3 -m pip install --disable-pip-version-check --quiet cryptography")
    try:
        installed = api.exec(box, ["sh", "-c", install], timeout=900, on_output=stream).ok
    except SailboxError as error:
        say(f"  pip could not be run ({str(error)[:160]})")
        installed = False
    if not installed:
        say("  `cryptography` did not install. The league does not need it (the gateway signs "
            "everything); only the first run's direct-signing adapters would.")
    return python


def cmd_deploy(args: argparse.Namespace) -> int:
    """Send one release and let the in-box watchdog decide whether the House runs it.

    A release is always the whole tree: it is packed, named by its time and content, unpacked into
    `incoming/<id>/` and handed to `python -m league.watchdog deploy`, which stages it under
    `releases/`, runs it as a canary, promotes it (`current`), restarts the House, watches it and
    rolls it back if the House goes bad. This script moves no link and restarts nothing itself.
    Exit 0 only for `promoted`; 2 refused, 3 rolled back, 4 failed, 1 no verdict seen.
    """
    state = read_state()
    box = require_box(state)
    api = client()
    python = state.get("python") or "python3"

    files = code_files()
    blob = tarball(files)
    release_id = release_id_for(blob)
    sha256 = hashlib.sha256(blob).hexdigest()

    seen = probe(api, box)
    if seen.get("error"):
        raise SystemExit(f"the box could not be probed, so nothing was sent: {seen['error']}")
    if up(seen, "deploy.pid"):
        raise SystemExit(
            f"a deploy is still running on the box (pid {seen['deploy.pid']}); wait for its verdict "
            "(`status` shows it, `logs --deploy` follows it) before sending another release."
        )
    if up(seen, "run.pid") and b"-m league run" not in (supervisor_script(api, box) or b""):
        raise SystemExit(
            "the supervisor running on the box is not the league's (its run.sh starts something "
            "else), and a restart would bring that back, not this release. Run `stop`, then "
            "`deploy`, then `start`."
        )
    if seen.get("env") != "yes":
        raise SystemExit(f"there is no {ENV_FILE} on the box and the canary cannot run without "
                         "it: run `python3 scripts/floor_box.py secrets` first.")
    current = release_of(seen.get("current")) if seen.get("runnable") == "yes" else None
    if current and content_of(current) == sha256[:12]:
        say(f"nothing to deploy: the box already runs this working tree ({current})")
        return 0

    # run.sh names the interpreter and restart.sh is what the watchdog calls, so both are in
    # place before it starts. A supervisor that is already up keeps the run.sh it started with.
    write_scripts(api, box, python)

    # A supervisor between two Houses (its 30 s delay) still counts: it starts the next one from
    # whatever is current, and that is the House the watchdog has to watch.
    watch = current is not None and (up(seen, "loop.pid") or up(seen, "run.pid"))
    say(f"release {release_id}: {len(files)} files, {len(blob):,} bytes compressed -> {box}")
    target = push_release(api, box, release_id, blob)
    say(f"  unpacked into {target}")

    entry = {"id": release_id, "sha256": sha256, "files": len(files), "bytes": len(blob),
             "at": _now(), "replaces": current, "watched": watch, "verdict": "pending", "reasons": []}
    remember_release(state, entry)
    state.pop("uploads", None)  # the first run's per-file digests: a release is a whole tree
    state["deployed_at"] = entry["at"]
    write_state(state)

    if watch:
        say(f"  starting the watchdog from {current}: canary, promote, restart, then watch the House")
    else:
        why = "there is no current release" if current is None else "the loop is not running"
        say(f"  starting the watchdog with --watch-seconds 0 ({why}): canary, then promote")
    api.exec(box, watchdog_launch(python, release_id, watch=watch), timeout=60, background=True,
             on_output=None)
    if args.no_wait:
        say("  launched. The verdict will be in `status`; the watchdog's own words in `logs --deploy`.")
        return 0

    say(f"  waiting for a verdict (up to {int(args.timeout)}s)")
    result = await_verdict(api, box, python, release_id, timeout=args.timeout, every=args.poll_seconds)
    verdict = result.get("verdict")
    entry.update(verdict=verdict or "pending", reasons=list(result.get("reasons") or []), verdict_at=result.get("at"))
    remember_release(state, entry)
    write_state(state)

    if verdict is None:
        say(f"NO VERDICT for {release_id}: {result.get('why')}")
        _, tail = watchdog_progress(api, box, lines=15)
        for line in tail:
            say(f"  | {line[:300]}")
        say("`status` shows the verdict when there is one; `logs --deploy` shows deploy.log.")
        return 1
    after = probe(api, box)
    say(f"{verdict.upper()}: {release_id}")
    for reason in result.get("reasons") or []:
        say(f"  - {reason}")
    say(f"  current={release_of(after.get('current'))}  previous={release_of(after.get('previous'))}")
    if verdict == "promoted" and not up(after, "run.pid"):
        say("  the loop is not running: `python3 scripts/floor_box.py start` when ready")
    return VERDICT_EXIT.get(verdict, 1)


def cmd_secrets(args: argparse.Namespace) -> int:
    """Push the owner's credentials to the box. The only command here that reads one.

    Run by the owner, from the owner's machine, on purpose. With a gateway named in
    `league/config.json` (how the House runs) the box gets exactly three values, composed from
    the local `.env` into `/workspace/.env`, mode 600, and no venue key. It refuses a source that
    is group- or world-readable and prints names and byte counts only. No value is decoded,
    logged or kept.

    Without a gateway anywhere in the config the first run's direct mode still applies (the whole
    `.env` and every file in `.data/ltcm/keys/`, to the same paths on the box). The league cannot
    run that way; it is kept for a checkout that predates the gateway.
    """
    state = read_state()
    box = require_box(state)
    api = client()

    sources: list[tuple[Path, str]] = []
    env_path = REPO_ROOT / SECRET_ENV
    gateway_mode = bool(floor_config().get("gateway_url"))
    if gateway_mode:
        # The box needs three values and gets three: the venue keys stay in the gateway, so a
        # fork or a checkpoint of the box can never reach a venue on its own.
        if not env_path.is_file():
            raise SystemExit(f"nothing to send: no {SECRET_ENV}")
        if stat.S_IMODE(env_path.stat().st_mode) & 0o077:
            raise SystemExit(f"{SECRET_ENV} is group- or world-readable. `chmod 600` it first.")
        wanted = compose_box_env(env_path.read_bytes())
        missing = [name for name in BOX_ENV_NAMES if f"{name}=".encode() not in wanted]
        if missing:
            raise SystemExit(f"{SECRET_ENV} lacks {', '.join(missing)}; the box needs all of them")
        api.upload(box, ENV_FILE, wanted, mode=0o600)
        say(f"  {SECRET_ENV} -> {ENV_FILE}  ({len(wanted):,} bytes, {len(BOX_ENV_NAMES)} values, mode 600)")
        say("  venue keys stay in the gateway; none were sent")
        del wanted
        # The first run's state on the box is history and nothing here deletes under it, so a
        # key file an earlier direct-mode `secrets` put there is the owner's to remove.
        legacy = sorted({str(n) for n in (state.get("secret_names") or []) if n != SECRET_ENV}
                        | {str(n) for n in (state.get("legacy_key_names") or [])})
        if legacy:
            state["legacy_key_names"] = legacy
            say(f"  NOTE: box.json says an earlier `secrets` put {', '.join(legacy)} under "
                f"{REMOTE_ROOT}/.data/ltcm/keys. This script no longer deletes anything under "
                f"{REMOTE_ROOT}/.data; if it is still there, removing it is the owner's step.")
        state["secrets_pushed_at"] = _now()
        state["secret_names"] = [SECRET_ENV]
        write_state(state)
        say("")
        say("credentials are on the box. `python3 scripts/floor_box.py start` when ready.")
        return 0
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
    """Clear both stop files and launch the supervisor. Nothing else.

    Whether the House trades real money is `real_money` in the release's `league/config.json`
    and the gateway's kill switch; this command reads and changes neither."""
    state = read_state()
    box = require_box(state)
    api = client()
    seen = probe(api, box)
    if seen.get("error"):
        raise SystemExit(f"the box could not be probed, so nothing was started: {seen['error']}")
    if up(seen, "run.pid") and not args.force:
        say(f"the supervisor is already running (pid {seen['run.pid']}); nothing to do")
        return 0
    if seen.get("runnable") != "yes":
        raise SystemExit(
            f"there is no release at {REMOTE_ROOT}/current, so there is nothing to start: deploy "
            "first (`python3 scripts/floor_box.py deploy`)."
        )
    # The supervisor that starts is always the one this script describes, never a run.sh left
    # on the box by the first run.
    write_scripts(api, box, state.get("python") or "python3")
    api.exec(box, ["sh", "-c", "rm -f " + " ".join(STOP_FILES)], timeout=60, on_output=None).check()
    say(f"starting the supervisor on {release_of(seen.get('current'))}")
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
    if not up(seen, "run.pid"):
        say("  the supervisor did not come up; check `logs`")
        return 1
    state["started_at"] = _now()
    write_state(state)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """Latch first, then quiesce, then stop. In that order, always."""
    state = read_state()
    box = require_box(state)
    api = client()

    say("writing both stop files so nothing restarts the loop")
    api.exec(
        box,
        ["sh", "-c", f"mkdir -p {STATE_DIR} && for f in {' '.join(STOP_FILES)}; do "
                     "printf 'stopped by floor_box: %s\\n' \"$1\" > \"$f\"; done",
         "floor_box", args.reason],
        timeout=60,
        on_output=None,
    ).check()

    seen = probe(api, box)
    loop = _pid(seen.get("loop.pid"))
    killed = False
    if loop is None:
        say("  no floor loop was running")
    else:
        say(f"asking the loop (pid {loop}) to finish its tick")
        api.exec(box, ["sh", "-c", f"kill -TERM {loop}"], timeout=60, on_output=None)
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            time.sleep(5)
            seen = probe(api, box)
            if not up(seen, "loop.pid"):
                say(f"  the loop quiesced after {int(args.timeout - (deadline - time.time()))}s")
                break
        else:
            say(f"  still running after {args.timeout}s; killing it")
            api.exec(box, ["sh", "-c", f"kill -KILL {loop} 2>/dev/null || true"],
                     timeout=60, on_output=None)
            killed = True
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
    say("stopped. Both stop files stay until `start` removes them.")
    if killed:
        say("the loop was KILLED, so it did not put its agent boxes to sleep: any that were awake "
            "stay awake, and billing, until the House next runs or they are slept by hand.")
    else:
        say("the agent boxes are the loop's to put to sleep, which `league run` does on its way "
            "out; this script does not touch them.")
    say("the gateway's kill switch and `real_money` are as they were: this script changes neither.")
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
        # An exec that fails (a full disk stops the runtime writing its record) says nothing
        # about the loop: report the probe error rather than a dead loop.
        "alive": None if seen.get("error") else up(seen, "loop.pid"),
        "probe_error": str(seen.get("error") or "")[:200] or None,
        "stop_latch": seen.get("stop") == "yes",
        "league_stop": seen.get("league_stop") == "yes",
    }
    rows = deploy_rows(api, box)
    report["release"] = {
        "current": release_of(seen.get("current")),
        "previous": release_of(seen.get("previous")),
        "current_link": seen.get("current") or None,
        "previous_link": seen.get("previous") or None,
        "deploy_running": None if seen.get("error") else up(seen, "deploy.pid"),
        "last_deploy_row": rows[-1] if rows else None,
    }
    # A deploy sent with --no-wait, or one that outlasted --timeout, gets its verdict here.
    changed = False
    for entry in state.get("releases") or []:
        if isinstance(entry, dict) and entry.get("verdict") == "pending":
            found = verdict_in(rows, str(entry.get("id")))
            if found is not None:
                entry.update(verdict=found["verdict"], reasons=found["reasons"], verdict_at=found["at"])
                changed = True
    if changed:
        write_state(state)
    report["hourly_cost_usd"] = hourly_cost(report, report.get("spend") or {})
    report["house_health"] = health(api, box)
    tail = ""
    try:
        tail = api.exec(
            box, ["sh", "-c", f"tail -n {int(args.tail)} {LEAGUE_LOG} 2>/dev/null"],
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
    if loop.get("probe_error"):
        say(f"loop         unknown: the probe failed ({loop['probe_error']})")
    say(f"loop         alive={loop['alive']} supervisor={loop['supervisor_pid']} "
        f"loop={loop['loop_pid']} stop_latch={loop['stop_latch']} league_stop={loop['league_stop']}")
    release = report["release"]
    say(f"release      current={release['current']}  previous={release['previous']}"
        + ("  (a deploy is running)" if release["deploy_running"] else ""))
    last = release["last_deploy_row"]
    if last:
        words = " ".join(f"{key}={last[key]}" for key in ("stage", "verdict", "ok", "reading") if last.get(key) is not None)
        say(f"last deploy  {last.get('at')}  {last.get('release')}  {words}")
        for reason in (last.get("reasons") or [])[:5]:
            say(f"             - {str(reason)[:200]}")
    else:
        say(f"last deploy  nothing in {DEPLOYS_JSONL} yet")
    house = report.get("house_health")
    if isinstance(house, Mapping):
        say(f"house        living={house.get('living')} dead={house.get('dead')} "
            f"ledger_seq={house.get('ledger_seq')} real_money={house.get('real_money')} "
            f"release={house.get('release')}  updated={house.get('at')}")
        for name, book in sorted((house.get("books") or {}).items()):
            book = book if isinstance(book, Mapping) else {}
            frozen = f"FROZEN: {str(book.get('frozen'))[:160]}" if book.get("frozen") else "ok"
            say(f"             {name}: {frozen}, {book.get('open_orders')} open order(s)")
    else:
        say(f"house        no {STATE_DIR}/health.json yet (no tick has finished)")
    checkpoints = state.get("checkpoints") or []
    if checkpoints:
        say(f"checkpoints  {len(checkpoints)}, newest {checkpoints[-1].get('name')} "
            f"({checkpoints[-1].get('checkpoint_id')})")
    if tail.strip():
        say("")
        say(f"--- last {args.tail} lines of {LEAGUE_LOG} ---")
        say(tail.rstrip())
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    state = read_state()
    box = require_box(state)
    api = client()
    path = DEPLOY_LOG if args.deploy else LEAGUE_LOG
    result = api.exec(
        box,
        ["sh", "-c", f"tail -n {int(args.lines)} {path} 2>/dev/null || echo '(no log yet)'"],
        timeout=120,
        on_output=None,
    )
    print(result.stdout.rstrip() or f"({path} is empty)")
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
        ["sh", "-c", f"mkdir -p {STATE_DIR}; touch {' '.join(STOP_FILES)}; "
                     f"for f in deploy.pid loop.pid run.pid; do p=$(cat {REMOTE_ROOT}/$f 2>/dev/null); "
                     'if [ -n "$p" ] && [ -d "/proc/$p" ]; then kill -TERM "$p" 2>/dev/null; fi; '
                     f"done; sleep 2; rm -f {REMOTE_ROOT}/run.pid {REMOTE_ROOT}/loop.pid "
                     f"{REMOTE_ROOT}/deploy.pid; true"],
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
        say("  WARNING: this copy has the parent's /workspace/.env on its disk, so it can ask the "
            "gateway for anything the House can. Remove that file from the copy before starting "
            "anything on it.")
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


def cmd_maintenance(args: argparse.Namespace) -> int:
    """The House's maintenance pause (`league.house.House.paused`): the loop keeps running,
    reconciles and lets holders exit; research, Merton, births, payouts, promotions and new
    entries wait until the file is gone. Unlike `stop`, nothing is left unmanaged."""
    state = read_state()
    box = require_box(state)
    api = client()
    path = f"{STATE_DIR}/PAUSE"
    if args.action == "on":
        api.exec(box, ["sh", "-c", f"mkdir -p {STATE_DIR} && printf '%s\\n' \"$1\" > {path}", "floor_box", args.reason],
                 timeout=60, on_output=None).check()
        say("paused for maintenance: " + args.reason)
        say("the next tick stops starting paid work and new entries; research in flight defers at its next turn.")
    elif args.action == "off":
        api.exec(box, ["sh", "-c", f"rm -f {path}"], timeout=60, on_output=None).check()
        say("maintenance pause lifted: the next tick opens for business again.")
    result = api.exec(box, ["sh", "-c", f"cat {path} 2>/dev/null || echo '(not paused)'"], timeout=60, on_output=None)
    say(f"PAUSE: {result.stdout.strip()}")
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
    missing = missing_league_hosts(policy["allowlist"])
    if missing:
        say(f"the league needs, and this list lacks: {', '.join(missing)}")
        say(f"  python3 scripts/floor_box.py hosts --add {' '.join(h for h in missing if '<' not in h) or '<gateway host>'}")
    else:
        say("every host the league needs is on it")
    return 0


def missing_league_hosts(allowlist: Sequence[str]) -> list[str]:
    """Which hosts the league needs are not on an allowlist. The gateway counts only by its exact
    name: Sail accepts `*.workers.dev` and never resolves it."""
    have = {str(h).strip().lower() for h in allowlist}
    missing = [host for host in LEAGUE_HOSTS if host not in have]
    gateway = str(floor_config().get("gateway_url") or "").partition("://")[2].partition("/")[0].lower()
    if gateway:
        if gateway not in have:
            missing.insert(0, gateway)
    elif not any(h.endswith(".workers.dev") and "*" not in h for h in have):
        missing.insert(0, "<the gateway's exact *.workers.dev host>")
    return missing


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
    "maintenance": cmd_maintenance,
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

    create = sub.add_parser("create", help="create the box, the policy, the venv and run.sh; no code, loop stopped")
    create.add_argument("--app", default=DEFAULT_APP)
    create.add_argument("--name", default=DEFAULT_NAME)
    create.add_argument("--visibility", default="private", choices=("private", "org"))
    create.add_argument(
        "--gateway-host",
        default=GATEWAY_HOST,
        help="the publish gateway to allow; a wildcard is accepted by Sail (default %(default)s)",
    )
    create.add_argument("--force", action="store_true", help="create a second box anyway")

    deploy = sub.add_parser("deploy", help="send a release; the in-box watchdog canaries, promotes, watches, rolls back")
    deploy.add_argument("--timeout", type=float, default=1500.0,
                        help="seconds to wait for the watchdog's verdict (default %(default)s)")
    deploy.add_argument("--poll-seconds", type=float, default=15.0, help=argparse.SUPPRESS)
    deploy.add_argument("--no-wait", action="store_true",
                        help="return as soon as the watchdog is launched; `status` has the verdict")

    sub.add_parser("secrets", help="the three values the box holds -> /workspace/.env (the owner runs this)")

    start = sub.add_parser("start", help="clear both stop files and start the supervised House loop")
    start.add_argument("--force", action="store_true")

    stop = sub.add_parser("stop", help="write both stop files, quiesce, then stop the loop")
    stop.add_argument("--timeout", type=float, default=120.0)
    stop.add_argument("--reason", default="operator stop")

    status = sub.add_parser("status", help="box, spend, loop, releases, last deploy, health, log tail")
    status.add_argument("--json", action="store_true")
    status.add_argument("--tail", type=int, default=15)

    logs = sub.add_parser("logs", help="tail /workspace/league.log")
    logs.add_argument("-n", "--lines", type=int, default=100)
    logs.add_argument("--deploy", action="store_true", help="tail /workspace/deploy.log instead")

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

    maintenance = sub.add_parser("maintenance", help="pause or resume paid work and entries; exits and reconciliation go on")
    maintenance.add_argument("action", choices=("on", "off", "status"))
    maintenance.add_argument("--reason", default="operator maintenance")

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
