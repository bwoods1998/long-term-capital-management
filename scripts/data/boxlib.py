"""The laptop side of the data tools: the Sail client, the local records, and pushing code.

The records live in `.data/gym/` (gitignored, never a secret): `data_box.json` (the data box),
`images.json` (the Gym and gate images), `universe.json` (the chosen roots and their numbers).
The Sail key is read the floor's way (`SAIL_API_KEY`, else an owner-only `.env`) and never printed.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:  # after the prune the Sail client lives in league/
    from league.sailbox import SailboxClient, SailboxError, Transport, normalize_hosts, policy_allowlist  # type: ignore
except ImportError:  # pragma: no cover - today it is in the legacy package
    from ltcm.sailbox import SailboxClient, SailboxError, Transport, normalize_hosts, policy_allowlist  # noqa: F401

STATE_DIR = Path(os.environ.get("LTCM_GYM_STATE") or (REPO_ROOT / ".data" / "gym"))
DATA_BOX = STATE_DIR / "data_box.json"
IMAGES = STATE_DIR / "images.json"
UNIVERSE = STATE_DIR / "universe.json"
THETA_ENV = Path.home() / ".config" / "thetadata" / "env"

#: The data box's egress while it runs, and the extra hosts only while it is being set up.
THETA_HOSTS = ("nexus-api.thetadata.us", "mdds-01.thetadata.us")
SETUP_HOSTS = ("deb.debian.org", "security.debian.org", "pypi.org", "files.pythonhosted.org",
               "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
#: A Gym or gate box's egress: none at all.
SEALED = {"no_network": True}

CODE_DIR = "/data/code"
VENV_PY = "/opt/data-venv/bin/python"
CODE_FILES = ("storelib.py", "frames.py", "backfill.py", "universe.py", "check.py", "locking.py")

SETUP_SCRIPT = r"""
set -e
export DEBIAN_FRONTEND=noninteractive
if [ ! -x /opt/data-venv/bin/python ]; then
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends python3-venv python3-pip ca-certificates zstd >/dev/null
  python3 -m venv /opt/uvboot
  /opt/uvboot/bin/pip install -q uv
  export UV_PYTHON_INSTALL_DIR=/opt/python
  /opt/uvboot/bin/uv python install 3.12
  /opt/uvboot/bin/uv venv -p 3.12 /opt/data-venv
  /opt/uvboot/bin/uv pip install -p /opt/data-venv/bin/python -q thetadata==1.0.11 polars pyarrow numpy python-dotenv
fi
mkdir -p /data/store /data/work /data/code /data/run /data/secrets
chmod 700 /data/secrets
/opt/data-venv/bin/python -c "import sys, thetadata, polars, pyarrow, numpy; print('ok', sys.version.split()[0], 'polars', polars.__version__, 'pyarrow', pyarrow.__version__, 'numpy', numpy.__version__)"
"""


def _key_source() -> str:
    try:  # the floor's parser: owner-only regular files, exactly one key
        from league.sailbox import _key_from_env_file  # type: ignore
    except ImportError:  # pragma: no cover - before the prune
        from ltcm.provider import _key_from_env_file

    key = os.environ.get("SAIL_API_KEY", "").strip()
    if key:
        return key
    for candidate in (REPO_ROOT / ".env", Path.home() / "Work" / "long-term-capital-management" / ".env",
                      Path.home() / "Work" / "ltcm-deploy" / ".env"):
        found = _key_from_env_file(candidate)
        if found:
            return found
    raise SystemExit("no Sail key: set SAIL_API_KEY or keep an owner-only .env")


def client() -> Any:
    return SailboxClient(Transport(key_source=_key_source))


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(dict(data), indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def data_box_id() -> str:
    box = read_json(DATA_BOX).get("box_id")
    if not box:
        raise SystemExit(f"no data box recorded in {DATA_BOX}; run `scripts/data/box.py create`")
    return str(box)


def ensure_running(api: Any, box: str) -> str:
    """Resume a sleeping box. Returns the status it was in."""
    status = str((api.get(box) or {}).get("status") or "")
    if status in ("sleeping", "paused", "interrupted_restorable"):
        api.resume(box)
    return status


def push_code(api: Any, box: str, files: tuple[str, ...] = CODE_FILES) -> list[str]:
    """Upload the data tools the box runs to /data/code (mode 0644)."""
    out = []
    for name in files:
        path = HERE / name
        if path.exists():
            api.upload(box, f"{CODE_DIR}/{name}", path.read_bytes(), mode=0o644)
            out.append(name)
    return out


def run_py(api: Any, box: str, args: str, *, timeout: int = 600, on_output: Callable[[str, str], None] | None = None) -> Any:
    """Run one of the data tools on a box with the venv's Python."""
    return api.exec(box, ["bash", "-c", f"cd {CODE_DIR} && {VENV_PY} {args}"], timeout=timeout, on_output=on_output)


class RemoteLease:
    """Serialize image builds and nightly jobs even when controllers run on different hosts."""

    def __init__(self, api: Any, box: str):
        self.api, self.box = api, box
        self.token = uuid.uuid4().hex
        self.stop = threading.Event()
        self.failed = False
        self.worker = None

    def command(self, action: str) -> bool:
        return run_py(self.api, self.box, f"locking.py {action} --token {self.token}", timeout=60).ok

    def __enter__(self):
        push_code(self.api, self.box, ("locking.py",))
        if not self.command("acquire"):
            raise RuntimeError("another controller is building an image or pulling the forward day")
        self.worker = threading.Thread(target=self.renew, daemon=True)
        self.worker.start()
        return self

    def renew(self) -> None:
        while not self.stop.wait(60):
            try:
                if not self.command("renew"):
                    self.failed = True
                    return
            except Exception:
                self.failed = True
                return

    def __exit__(self, kind, value, traceback):
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=65)
        try:
            released = self.command("release")
        except Exception:
            released = False
        if kind is None and (self.failed or not released):
            raise RuntimeError("the data operation lease was lost; retry before publishing a checkpoint")


def theta_env_bytes() -> bytes:
    """The one line the data box needs, from the owner's file. Never printed or logged."""
    mode = THETA_ENV.stat().st_mode & 0o777
    if mode & 0o077:
        raise SystemExit(f"{THETA_ENV} is readable by others; refusing to copy it")
    for line in THETA_ENV.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "THETADATA_API_KEY" and value.strip():
            return f"THETADATA_API_KEY={value.strip()}\n".encode()
    raise SystemExit(f"no THETADATA_API_KEY in {THETA_ENV}")
