#!/usr/bin/env python3
"""Copy the event lane's desktop store onto the House box, once (release R1; league/events/house.py).

    python3 scripts/evl_migrate.py [--source ~/Work/.ltcm-main/evl] [--box sb_...] [--dry-run]

The lane's state on blake-desktop (phase 1 of goal-2026-10-19/EVL-DESIGN.md: `events.sqlite` and `docs/`) becomes the
House's `<state>/events/` (`/workspace/state/events/` on the box), through the Sail API scripts/floor_box.py uses (its
file upload and exec). Every filing, document, news row, verdict, intent, outcome, look and receipt comes along, so no
verdict is ever asked twice (they are keyed by event, prompt and model) and the House lane goes on from where the desktop
stopped.

What it does, and what it refuses:
- It REFUSES while the desktop's timers run (`ltcm-evl-*`; `--allow-running` overrides): stop them first, or the desktop
  goes on recording and asking after the copy (`systemctl --user stop 'ltcm-evl-*.timer'`).
- A consistent copy of `events.sqlite` (SQLite's backup API: the desktop may be mid-write), checked (`integrity_check`,
  the schema version), and every document it names, each checked against its SHA-256 name; a document missing or
  corrupt refuses the copy. A MANIFEST (every file's SHA-256 and size, and each table's row count) rides along.
- The box's target must be absent or empty (`--target` to name another): the House lane never makes its own root, so
  it cannot have written there, and a second migration refuses. The free space must hold the copy three times over.
- One gzip bundle, uploaded in chunks (`--chunk-mib`, 8 by default), each chunk's SHA-256 read back from the box and
  sent again when it differs (twice at most). On the box: the chunks joined and the bundle's SHA-256 checked, its
  regular files extracted into a staging directory beside the target (nothing outside it), every file checked against
  the MANIFEST, the database checked again, and then ONE rename puts it in place. The uploads are removed.
- `--dry-run` does all of it locally (the box's half runs on a scratch directory) and sends nothing.

After it: with `config.json` `events.enabled` true on the House, the lane starts within a minute (its health is
`<state>/events/lane.json`); keep the desktop's timers stopped. It prints one JSON summary.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import importlib.util
import io
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SOURCE = Path.home() / "Work" / ".ltcm-main" / "evl"
DEFAULT_WORKDIR = Path.home() / "Work" / ".ltcm-main" / "scratch"
CHUNK_MIB = 8
RESENDS = 2
DB_NAME = "events.sqlite"
MANIFEST = "MANIFEST.json"
MIGRATED = "migrated.json"
TABLES = ("filings", "documents", "form4_owners", "form4_tx", "news", "sessions", "universe", "cik_info", "verdicts",
          "intents", "outcomes", "looks", "bars", "marks", "receipts", "meta")


class Refused(SystemExit):
    """The migration will not go on; the message says why (exit status 2)."""

    def __init__(self, why: str):
        super().__init__(2)
        self.why = why

    def __str__(self) -> str:
        return self.why


# ---------------------------------------------------------------------------------------------------- the desktop half
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as src:
        for block in iter(lambda: src.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def desktop_timers_running() -> list[str]:
    """The `ltcm-evl-*` systemd user units now active (timers waiting, services running); none without systemd."""
    if not shutil.which("systemctl"):
        return []
    out = subprocess.run(["systemctl", "--user", "list-units", "ltcm-evl-*", "--state=active", "--no-legend", "--plain"],
                         capture_output=True, text=True, timeout=30)
    return [line.split()[0] for line in out.stdout.splitlines() if line.strip()]


def snapshot(source: Path, work: Path) -> tuple[Path, dict[str, Any]]:
    """A consistent copy of the source's events.sqlite in `work` (journal mode DELETE: one self-contained file) and its
    facts: the schema version and every table's row count."""
    db = source / DB_NAME
    if not db.is_file():
        raise Refused(f"no {DB_NAME} in {source}")
    out = work / DB_NAME
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    dst = sqlite3.connect(str(out))
    try:
        src.backup(dst)
    finally:
        src.close()
    try:
        dst.execute("PRAGMA journal_mode=DELETE")
        check = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise Refused(f"the copy of {DB_NAME} fails its integrity check: {check}")
        row = dst.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        counts = {t: int(dst.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in TABLES}
        docs = [(str(r[0]), str(r[1])) for r in dst.execute("SELECT sha, path FROM documents ORDER BY sha")]
    finally:
        dst.close()
    return out, {"schema_version": None if row is None else str(row[0]), "counts": counts, "documents": docs}


def check_documents(source: Path, docs: list[tuple[str, str]]) -> dict[str, list[Any]]:
    """Every document the copy names, present and true to its SHA-256 name: relpath -> [sha256 of the file, size]."""
    files: dict[str, list[Any]] = {}
    for sha, rel in docs:
        path = source / rel
        if not path.is_file():
            raise Refused(f"document {sha} is named in {DB_NAME} but missing: {path}")
        with gzip.open(path, "rb") as src:
            if hashlib.sha256(src.read()).hexdigest() != sha:
                raise Refused(f"document {path} does not match its digest")
        files[Path(rel).as_posix()] = [sha256_file(path), path.stat().st_size]
    return files


def bundle(source: Path, db_copy: Path, facts: Mapping[str, Any], work: Path) -> tuple[Path, dict[str, Any]]:
    """The gzip tarball of the copy, its documents and the MANIFEST; and the manifest."""
    files = check_documents(source, list(facts["documents"]))
    files[DB_NAME] = [sha256_file(db_copy), db_copy.stat().st_size]
    manifest = {"made_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "source": str(source), "schema_version": facts["schema_version"], "counts": facts["counts"],
                "files": dict(sorted(files.items()))}
    out = work / "bundle.tgz"
    with tarfile.open(out, "w:gz", compresslevel=1) as tar:
        blob = json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8")
        info = tarfile.TarInfo(MANIFEST)
        info.size, info.mode, info.mtime = len(blob), 0o600, int(time.time())
        tar.addfile(info, io.BytesIO(blob))
        tar.add(str(db_copy), arcname=DB_NAME, recursive=False)
        for rel in sorted(files):
            if rel != DB_NAME:
                tar.add(str(source / rel), arcname=rel, recursive=False)
    return out, manifest


def chunks(path: Path, size: int) -> Iterator[tuple[str, bytes]]:
    with open(path, "rb") as src:
        for index in range(1_000_000):
            data = src.read(size)
            if not data:
                return
            yield f"part-{index:05d}", data


# ---------------------------------------------------------------------------------------------------- the box's half
#: Each runs on the box as `python -c SNIPPET '<json>'` (the House's Python, standard library only) and prints one JSON
#: line; the tests run them here on a scratch directory.
CHECK_SNIPPET = r'''
import json, os, shutil, sys
ask = json.loads(sys.argv[1])
target = ask["target"]
if not os.path.exists(target):
    state = "absent"
elif os.path.isdir(target) and not os.listdir(target):
    state = "empty"
else:
    state = "full"
parent = os.path.dirname(target.rstrip("/")) or "/"
free = shutil.disk_usage(parent if os.path.isdir(parent) else "/").free
print(json.dumps({"target": state, "free": free, "parent": os.path.isdir(parent)}))
'''

VERIFY_SNIPPET = r'''
import hashlib, json, os, sys
ask = json.loads(sys.argv[1])
out = {}
for name in ask["parts"]:
    path = os.path.join(ask["dir"], name)
    if not os.path.isfile(path):
        out[name] = None
        continue
    digest = hashlib.sha256()
    with open(path, "rb") as src:
        for block in iter(lambda: src.read(1 << 20), b""):
            digest.update(block)
    out[name] = [digest.hexdigest(), os.path.getsize(path)]
print(json.dumps(out))
'''

FINISH_SNIPPET = r'''
import hashlib, json, os, shutil, sqlite3, sys, tarfile
ask = json.loads(sys.argv[1])
updir, target, staging = ask["dir"], ask["target"], ask["staging"]

def fail(why):
    for leftover in (staging, updir):
        if os.path.isdir(leftover):
            shutil.rmtree(leftover, ignore_errors=True)
    print(json.dumps({"ok": False, "why": why}))
    sys.exit(1)

def sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as src:
        for block in iter(lambda: src.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

if os.path.exists(target) and (not os.path.isdir(target) or os.listdir(target)):
    fail("the target is not empty: " + target)
os.umask(0o077)
joined = os.path.join(updir, "bundle.tgz")
digest = hashlib.sha256()
with open(joined, "wb") as out:
    for name in ask["parts"]:
        with open(os.path.join(updir, name), "rb") as src:
            for block in iter(lambda: src.read(1 << 20), b""):
                digest.update(block)
                out.write(block)
if digest.hexdigest() != ask["sha256"]:
    fail("the joined bundle's sha256 is not the one sent")
if os.path.exists(staging):
    shutil.rmtree(staging)
os.makedirs(staging, mode=0o700)
root = os.path.realpath(staging)
with tarfile.open(joined, "r:gz") as tar:
    for member in tar.getmembers():
        parts = member.name.split("/")
        if member.name.startswith("/") or ".." in parts or not (member.isfile() or member.isdir()):
            fail("an unsafe member in the bundle: %r" % member.name)
        path = os.path.realpath(os.path.join(staging, member.name))
        if not (path == root or path.startswith(root + os.sep)):
            fail("a member outside the staging directory: %r" % member.name)
        if member.isdir():
            os.makedirs(path, mode=0o700, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with tar.extractfile(member) as src, open(path, "wb") as out:
            shutil.copyfileobj(src, out, 1 << 20)
with open(os.path.join(staging, "MANIFEST.json"), encoding="utf-8") as src:
    manifest = json.load(src)
listed = set(manifest["files"])
for rel, (want, size) in manifest["files"].items():
    path = os.path.join(staging, rel)
    if not os.path.isfile(path) or os.path.getsize(path) != size or sha(path) != want:
        fail("a file does not match the manifest: " + rel)
for folder, _, names in os.walk(staging):
    for name in names:
        rel = os.path.relpath(os.path.join(folder, name), staging).replace(os.sep, "/")
        if rel != "MANIFEST.json" and rel not in listed:
            fail("a file the manifest does not list: " + rel)
db = sqlite3.connect("file:%s?mode=ro" % os.path.join(staging, "events.sqlite"), uri=True)
try:
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        fail("events.sqlite fails its integrity check on the box")
    row = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if (None if row is None else str(row[0])) != manifest["schema_version"]:
        fail("the schema version is not the manifest's")
    counts = {t: int(db.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]) for t in manifest["counts"]}
finally:
    db.close()
if counts != manifest["counts"]:
    fail("the row counts are not the manifest's")
os.replace(os.path.join(staging, "MANIFEST.json"), os.path.join(staging, "migrated.json"))
if os.path.isdir(target) and not os.listdir(target):
    os.rmdir(target)
if os.path.exists(target):
    fail("the target appeared while the copy was checked: " + target)
os.rename(staging, target)
shutil.rmtree(updir, ignore_errors=True)
print(json.dumps({"ok": True, "target": target, "files": len(listed), "counts": counts}))
'''


def box_json(result: Any) -> dict[str, Any]:
    """The JSON line a snippet printed (its last line), or a refusal saying what the box answered."""
    lines = [line for line in (getattr(result, "stdout", "") or "").splitlines() if line.strip()]
    try:
        return json.loads(lines[-1])
    except (IndexError, ValueError):
        tail = ((getattr(result, "stderr", "") or "") + (getattr(result, "stdout", "") or ""))[-600:]
        raise Refused(f"the box answered no JSON (code {getattr(result, 'return_code', None)}): {tail}") from None


class LocalBox:
    """The box's half on this machine (a dry run): uploads land under `root`, the snippets run with this Python."""

    def __init__(self, root: Path):
        self.root = root

    def upload(self, box: str, path: str, content: bytes, *, mode: int = 0o600, timeout: float = 300.0) -> dict:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(mode)
        return {}

    def exec(self, box: str, command: Any, *, timeout: int = 600, on_output: Any = None) -> Any:
        done = subprocess.run(list(command), capture_output=True, text=True, timeout=timeout)
        return type("Result", (), {"stdout": done.stdout, "stderr": done.stderr, "return_code": done.returncode,
                                   "ok": done.returncode == 0})()


def run_snippet(api: Any, box: str, python: str, snippet: str, ask: Mapping[str, Any], *, timeout: int = 600
                ) -> dict[str, Any]:
    return box_json(api.exec(box, [python, "-c", snippet, json.dumps(dict(ask))], timeout=timeout, on_output=None))


def box_python(api: Any, box: str, remote_root: str) -> str:
    """The House's venv Python on the box, else its python3."""
    venv = f"{remote_root}/.venv/bin/python"
    out = api.exec(box, ["sh", "-c", f'if [ -x {venv} ]; then echo {venv}; else command -v python3; fi'], timeout=60,
                   on_output=None)
    found = (getattr(out, "stdout", "") or "").strip().splitlines()
    if not found:
        raise Refused("no Python on the box")
    return found[-1].strip()


# ---------------------------------------------------------------------------------------------------- the migration
def migrate(api: Any, box: str, source: Path, *, remote_root: str, python: str, target: str | None = None,
            chunk_mib: float = CHUNK_MIB, work: Path | None = None, allow_running: bool = False,
            say: Callable[[str], None] = print, timers: Callable[[], list[str]] = desktop_timers_running
            ) -> dict[str, Any]:
    """The whole migration (see the module docstring). Raises `Refused` with the reason when it will not go on."""
    source = Path(source).expanduser()
    running = timers()
    if running and not allow_running:
        raise Refused("the desktop lane is still running (" + ", ".join(running) + "): systemctl --user stop "
                      "'ltcm-evl-*.timer', wait for its services to end, then migrate (or --allow-running)")
    state_dir = f"{remote_root}/state"
    target = target or f"{state_dir}/events"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)
    updir = f"{remote_root}/.upload/evl-migrate-{stamp}"
    staging = f"{os.path.dirname(target.rstrip('/'))}/.events-incoming-{stamp}"
    work = Path(tempfile.mkdtemp(prefix="evl-migrate-", dir=str(work) if work else None))
    uploaded = False
    try:
        seen = run_snippet(api, box, python, CHECK_SNIPPET, {"target": target}, timeout=120)
        if seen.get("target") == "full":
            raise Refused(f"the box's {target} is not empty: the lane's store is there already (a second migration "
                          "is refused; move it aside first if that is truly meant)")
        if not seen.get("parent"):
            raise Refused(f"the box has no {os.path.dirname(target.rstrip('/'))}: is this the House box?")
        say(f"copying {source} (consistent snapshot) ...")
        db_copy, facts = snapshot(source, work)
        tarball, manifest = bundle(source, db_copy, facts, work)
        size = tarball.stat().st_size
        if int(seen.get("free") or 0) < 3 * size + (64 << 20):
            raise Refused(f"the box has {int(seen.get('free') or 0)} bytes free; the copy needs about {3 * size}")
        whole = sha256_file(tarball)
        sent: dict[str, str] = {}
        step = max(1, int(float(chunk_mib) * (1 << 20)))
        say(f"bundle {size} bytes, {len(manifest['files'])} files, sha256 {whole[:12]}; uploading in "
            f"{(size + step - 1) // step} chunks ...")
        for name, data in chunks(tarball, step):
            uploaded = True
            api.upload(box, f"{updir}/{name}", data, mode=0o600, timeout=300)
            sent[name] = hashlib.sha256(data).hexdigest()
        for attempt in range(RESENDS + 1):
            got = run_snippet(api, box, python, VERIFY_SNIPPET, {"dir": updir, "parts": sorted(sent)}, timeout=600)
            bad = [name for name in sorted(sent) if not got.get(name) or got[name][0] != sent[name]]
            if not bad:
                break
            if attempt == RESENDS:
                raise Refused(f"chunks still differ on the box after {RESENDS} resends: {bad[:5]}")
            say(f"resending {len(bad)} chunk(s) that differ on the box: {bad[:5]}")
            data_of = dict(chunks(tarball, step))
            for name in bad:
                api.upload(box, f"{updir}/{name}", data_of[name], mode=0o600, timeout=300)
        done = run_snippet(api, box, python, FINISH_SNIPPET, {"dir": updir, "target": target, "staging": staging,
                                                              "parts": sorted(sent), "sha256": whole}, timeout=1800)
        if not done.get("ok"):
            raise Refused(f"the box refused the copy: {done.get('why')}")
        uploaded = False   # the box removed its uploads with the copy in place
        return {"ok": True, "target": target, "bundle_bytes": size, "bundle_sha256": whole, "chunks": len(sent),
                "files": done.get("files"), "counts": done.get("counts"), "schema_version": manifest["schema_version"]}
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if uploaded:   # a failed attempt leaves no chunks on the box (best effort)
            try:
                api.exec(box, ["rm", "-rf", updir], timeout=120, on_output=None)
            except Exception:  # noqa: BLE001 - the refusal in hand says more than a failed cleanup
                pass


def box_id(explicit: str | None) -> str:
    if explicit:
        return explicit
    spec = importlib.util.spec_from_file_location("floor_box_for_evl", REPO_ROOT / "scripts" / "floor_box.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return str(module.require_box(module.read_state()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evl_migrate.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--box", default=None, help="the House box's id (default: .data/ltcm/box.json, as floor_box.py)")
    ap.add_argument("--target", default=None, help="the box's directory (default: /workspace/state/events)")
    ap.add_argument("--chunk-mib", type=float, default=CHUNK_MIB)
    ap.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR if DEFAULT_WORKDIR.is_dir() else None)
    ap.add_argument("--allow-running", action="store_true", help="copy although the desktop's timers are active")
    ap.add_argument("--dry-run", action="store_true", help="everything here, the box's half on a scratch directory")
    args = ap.parse_args(argv)
    try:
        if args.dry_run:
            scratch = Path(tempfile.mkdtemp(prefix="evl-migrate-box-", dir=str(args.workdir) if args.workdir else None))
            try:
                (scratch / "state").mkdir()
                out = migrate(LocalBox(scratch), "dry-run", args.source, remote_root=str(scratch), python=sys.executable,
                              target=None, chunk_mib=args.chunk_mib, work=args.workdir, allow_running=True)
                out["dry_run"] = True
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
        else:
            from league.sailbox import REMOTE_ROOT, SailboxClient

            api = SailboxClient()
            box = box_id(args.box)
            out = migrate(api, box, args.source, remote_root=REMOTE_ROOT, python=box_python(api, box, REMOTE_ROOT),
                          target=args.target, chunk_mib=args.chunk_mib, work=args.workdir,
                          allow_running=args.allow_running)
    except Refused as refused:
        print(json.dumps({"ok": False, "refused": refused.why}))
        return 2
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
