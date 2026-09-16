"""Sandboxes: a desk's own machine for the code it writes.

The leap from a prompted desk to one that builds its tools is a place to run code that is not
the floor. A **lab image** is one Sailbox provisioned once (python3, numpy, pandas, the floor's
read-only market-data package and a small `labkit` on top of it) and checkpointed. Each desk's
sandbox is a fork of that checkpoint, created on first use, put to sleep between uses (sleeping
is free) and woken by the next run. It never holds a venue key, the gateway token or the Sail
key: its egress allowlist is data sources only, so the worst a desk's code can do is read
public data slowly.

`SandboxManager.run` is what the `run_code` tool calls: it uploads the desk's saved toolbox and
the code, executes it with a timeout, and returns bounded output. Every run is published as
`desk.code_run` (contract v2 §1) with the code's hash, so a reader can check what ran. A failure
of any kind comes back as a result with a non-zero exit code and never as an exception into the
tool loop: the desk reads the error the way it reads any tool result.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from .sailbox import SailboxError, normalize_hosts

#: What a sandbox may reach: public market data and filings, and nothing that can move money
#: or spend credit. The gateway host and api.sailresearch.com are deliberately absent.
SANDBOX_HOSTS = (
    "api.elections.kalshi.com",   # public market data (no auth on /markets, /series, history)
    "api.coinbase.com",           # public products, candles, ticker under /market/
    "query1.finance.yahoo.com",
    "query2.finance.yahoo.com",
    "www.sec.gov",
    "efts.sec.gov",
    "data.sec.gov",
    "api.weather.gov",            # leap: weather -- NWS forecasts and readings, public
)
#: Only the lab image build needs package sources; forks keep the list, which is harmless.
BUILD_HOSTS = SANDBOX_HOSTS + (
    "deb.debian.org",
    "security.debian.org",
    "pypi.org",
    "files.pythonhosted.org",
)

REMOTE_ROOT = "/lab"
REMOTE_TOOLBOX = f"{REMOTE_ROOT}/toolbox"
REMOTE_RUN = f"{REMOTE_ROOT}/run"
MAX_CODE_CHARS = 40_000
MAX_OUTPUT_CHARS = 4_000
TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
DEFAULT_TIMEOUT = 120
#: A desk's sandbox time per day, in seconds. A fuse against a loop, not a budget.
DEFAULT_DAILY_SECONDS = 1800

LABKIT = '''"""labkit: what a desk's code may read. Public data only; nothing here can trade.

    from labkit import bars, quote, kalshi_market, kalshi_markets, kalshi_history, news
"""
import json, sys
sys.path.insert(0, "/lab/floor")
from ltcm.broker import Instrument
from ltcm.data import CompositeMarketData, HttpTransport

_data = CompositeMarketData(transport=HttpTransport(cache_dir="/lab/cache", ttl=300.0, min_interval=0.2))

def _inst(symbol, asset_class="crypto", venue="coinbase"):
    return Instrument(symbol=symbol, asset_class=asset_class, venue=venue)

def _plain(value):
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return value

def bars(symbol, interval="1d", limit=60, asset_class="crypto", venue="coinbase"):
    """Bars as dicts: start, end, open, high, low, close, volume (decimal strings)."""
    return [_plain(b) for b in _data.bars(_inst(symbol, asset_class, venue), interval, limit)]

def quote(symbol, asset_class="crypto", venue="coinbase"):
    return _plain(_data.quote(_inst(symbol, asset_class, venue)))

def _source(name):
    # The composite routes through `_source`; an older labkit looked for `source` and every
    # kalshi helper answered nothing. Try both so either image works.
    for attr in ("_source", "source"):
        getter = getattr(_data, attr, None)
        if callable(getter):
            try:
                return getter(name)
            except Exception:
                return None
    return None

def kalshi_market(ticker):
    """One market by ticker, prices in dollars (yes_bid, yes_ask, no_bid, no_ask, last_price)."""
    src = _source("event")
    return src.market(ticker) if src is not None and hasattr(src, "market") else None

def kalshi_series(series, limit=1000, status="open"):
    """Every open market of one series (KXBTC, KXETH, KXHIGHNY, KXFEDDECISION...) as dicts with
    ticker, title, yes_sub_title, close_time, yes_bid, yes_ask, no_bid, no_ask, status. An hourly
    series lists dozens of buckets for several hours at once; filter by close_time."""
    src = _source("event")
    if src is None or not hasattr(src, "markets"):
        return []
    page = src.markets(series_ticker=str(series).upper().split("-")[0], status=status, limit=limit)
    rows = page.get("markets", []) if isinstance(page, dict) else []
    out = []
    for row in rows:
        try:
            out.append(src.parse_market(row))
        except Exception:
            continue
    return out

def kalshi_markets(query, limit=40):
    """Markets of the series named by the first ticker-like word of the query (KXBTC,
    KXETH-26SEP1617), narrowed by the other words against ticker, title and subtitle."""
    import re
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]{2,}(?:-[A-Za-z0-9.]+)*", str(query or ""))
    if not tokens:
        return []
    prefix = tokens[0].upper()
    rows = [r for r in kalshi_series(prefix) if str(r.get("ticker") or "").upper().startswith(prefix)]
    words = [w.lower() for w in tokens[1:]]
    if words:
        rows = [r for r in rows if all(w in " ".join(str(r.get(k) or "") for k in ("ticker", "title", "yes_sub_title")).lower() for w in words)]
    return rows[:limit]

def kalshi_history(ticker, limit=500):
    src = _source("event")
    return src.history(ticker, limit) if src is not None and hasattr(src, "history") else []

def news(query, limit=10):
    src = _source("news")
    return src.news(query, limit) if src is not None and hasattr(src, "news") else []
'''

#: The image build, as one shell script run on the fresh box. Debian base; root.
PROVISION = "\n".join(
    [
        "set -e",
        "export DEBIAN_FRONTEND=noninteractive",
        "apt-get update -qq",
        "apt-get install -y -qq python3 python3-pip python3-numpy python3-pandas >/dev/null",
        f"mkdir -p {REMOTE_ROOT}/floor {REMOTE_TOOLBOX} {REMOTE_RUN} {REMOTE_ROOT}/cache",
        "python3 -c 'import numpy, pandas, sys; print(\"python\", sys.version.split()[0], "
        "\"numpy\", numpy.__version__, \"pandas\", pandas.__version__)'",
    ]
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: Floor modules uploaded with every run because the lab image predates them. Data readers
#: only; nothing here can trade.
FLOOR_EXTRAS = ("ltcm/data/weather.py",)


def floor_extras() -> dict[str, str]:
    """`{relative path: source}` for the modules in `FLOOR_EXTRAS` that exist in this checkout."""
    root = Path(__file__).resolve().parent.parent
    out: dict[str, str] = {}
    for relative in FLOOR_EXTRAS:
        path = root / relative
        try:
            out[relative] = path.read_text(encoding="utf-8")
        except OSError:
            continue
    return out


def bounded(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    head = limit - 60
    return text[:head] + f"\n... [{len(text) - head} more characters cut]\n" + text[-40:]


@dataclass(frozen=True)
class CodeRun:
    """One execution, as the tool reports it and the tape publishes it."""

    desk_id: str
    code_sha256: str
    stdout: str
    exit_code: int
    seconds: Decimal
    sandbox: str | None
    purpose: str
    saved_as: str | None = None

    def to_payload(self, session_id: str | None) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "code_sha256": self.code_sha256,
            "language": "python",
            "stdout": self.stdout,
            "exit_code": int(self.exit_code),
            "seconds": str(self.seconds),
            "sandbox": None if not self.sandbox else str(self.sandbox)[-12:],
            "purpose": self.purpose[:200],
            **({"saved_as": self.saved_as} if self.saved_as else {}),
        }


class Toolbox:
    """A desk's saved code, on the floor's disk. Uploaded whole before every run so the code the
    desk wrote last week is importable this week: `from toolbox.momentum import score`."""

    def __init__(self, root: Path, desk_id: str):
        self.dir = Path(root) / desk_id
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, code: str, purpose: str) -> None:
        if not TOOL_NAME.match(name):
            raise ValueError("a tool name is lowercase letters, digits and underscores, 40 at most")
        (self.dir / f"{name}.py").write_text(code, encoding="utf-8")
        index = self.index()
        index[name] = {
            "purpose": purpose[:200],
            "sha256": sha256_text(code),
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        (self.dir / "index.json").write_text(
            json.dumps(index, indent=2, sort_keys=True), encoding="utf-8"
        )

    def index(self) -> dict[str, Any]:
        try:
            return json.loads((self.dir / "index.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def files(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for path in sorted(self.dir.glob("*.py")):
            try:
                out[path.name] = path.read_text(encoding="utf-8")
            except OSError:
                continue
        return out


class SandboxManager:
    """Forks, wakes, runs and sleeps one sandbox per desk from the lab image checkpoint."""

    def __init__(
        self,
        client: Any,
        state_path: str | Path,
        toolbox_root: str | Path,
        *,
        image: Mapping[str, Any] | None = None,
        clock: Callable[[], float] = time.time,
        daily_seconds: int = DEFAULT_DAILY_SECONDS,
    ):
        self.client = client
        self.state_path = Path(state_path)
        self.toolbox_root = Path(toolbox_root)
        self.image = dict(image or {})
        self.clock = clock
        self.daily_seconds = int(daily_seconds)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ state
    def state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, state: Mapping[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(self.state_path.name + f".tmp-{os.getpid()}")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self.state_path)

    def available(self) -> bool:
        return bool(self.image.get("checkpoint_id")) and self.client is not None

    def toolbox_files(self, desk_id: str) -> dict[str, str]:
        """The desk's saved code, by file name (leap: strategies)."""
        return Toolbox(self.toolbox_root, desk_id).files()

    def toolbox_save(self, desk_id: str, name: str, code: str, purpose: str) -> None:
        Toolbox(self.toolbox_root, desk_id).save(name, code, purpose)

    def box_for(self, desk_id: str) -> str | None:
        return (self.state().get("boxes") or {}).get(desk_id)

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(float(self.clock())))

    def seconds_today(self, desk_id: str) -> int:
        used = (self.state().get("used") or {}).get(desk_id) or {}
        return int(used.get(self._today(), 0))

    def _charge(self, desk_id: str, seconds: float) -> None:
        with self._lock:
            state = self.state()
            used = state.setdefault("used", {}).setdefault(desk_id, {})
            day = self._today()
            used[day] = int(used.get(day, 0)) + int(round(seconds))
            for stale in [d for d in used if d != day]:
                used.pop(stale, None)
            self._save(state)

    # ------------------------------------------------------------------ boxes
    def ensure_box(self, desk_id: str) -> str:
        """The desk's sandbox id, forking the lab image on first use and waking it otherwise."""
        with self._lock:
            state = self.state()
            boxes = state.setdefault("boxes", {})
            box = boxes.get(desk_id)
            if box:
                self._wake(box)
                # A box forked before a host joined the data list (api.weather.gov, Sept 16,
                # 2026) gets the current list once; the list it runs under is recorded.
                hosts = state.setdefault("hosts", {})
                if hosts.get(desk_id) != list(SANDBOX_HOSTS):
                    try:
                        self.client.set_egress(box, list(SANDBOX_HOSTS))
                        hosts[desk_id] = list(SANDBOX_HOSTS)
                        self._save(state)
                    except Exception:
                        pass
                return box
            checkpoint = self.image.get("checkpoint_id")
            if not checkpoint:
                raise SailboxError("no lab image: run scripts/lab_image.py build")
            row = self.client.from_checkpoint(checkpoint, name=f"lab-{desk_id}"[:60])
            box = str(row.get("sailbox_id"))
            # A fork inherits the image's build-time allowlist (package mirrors); a desk's box
            # gets the data-only list, so its code can read markets and nothing else.
            try:
                self.client.set_egress(box, list(SANDBOX_HOSTS))
            except Exception:
                pass  # the image's list is still data-only plus package mirrors; not worth failing
            try:
                self.client.set_auto_sleep(box, automatic=True, min_seconds_before_sleep=300)
            except Exception:
                pass  # a box that never sleeps only costs its hourly rate; not worth failing
            boxes[desk_id] = box
            state.setdefault("hosts", {})[desk_id] = list(SANDBOX_HOSTS)
            state.setdefault("forked_at", {})[desk_id] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(self.clock()))
            )
            self._save(state)
            return box

    def _wake(self, box: str) -> None:
        try:
            row = self.client.get(box)
        except Exception:
            return
        if str(row.get("status") or "") in ("sleeping", "paused", "asleep"):
            self.client.resume(box)

    # ------------------------------------------------------------------ runs
    def run(
        self,
        desk_id: str,
        code: str,
        *,
        purpose: str = "",
        save_as: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> CodeRun:
        """Run `code` in the desk's sandbox. Never raises; failures are results."""
        digest = sha256_text(code or "")
        zero = Decimal("0")
        if not isinstance(code, str) or not code.strip():
            return CodeRun(desk_id, digest, "no code given", 2, zero, None, purpose)
        if len(code) > MAX_CODE_CHARS:
            return CodeRun(desk_id, digest, f"code is over {MAX_CODE_CHARS} characters", 2, zero, None, purpose)
        if not self.available():
            return CodeRun(desk_id, digest, "no sandbox is available on this floor", 3, zero, None, purpose)
        remaining = self.daily_seconds - self.seconds_today(desk_id)
        if remaining <= 0:
            return CodeRun(desk_id, digest, "the desk's sandbox time for today is used up", 4, zero, None, purpose)
        timeout = max(5, min(int(timeout), remaining, DEFAULT_TIMEOUT * 5))
        toolbox = Toolbox(self.toolbox_root, desk_id)
        if save_as:
            try:
                toolbox.save(save_as, code, purpose)
            except ValueError as exc:
                return CodeRun(desk_id, digest, str(exc), 2, zero, None, purpose)
        started = float(self.clock())
        box: str | None = None
        try:
            box = self.ensure_box(desk_id)
            # labkit rides along on every run, so a fix reaches every sandbox without a new image,
            # and so do floor modules the image predates (the weather source).
            self.client.upload(box, f"{REMOTE_ROOT}/labkit.py", LABKIT.encode("utf-8"), mode=0o644)
            for relative, body in floor_extras().items():
                self.client.upload(box, f"{REMOTE_ROOT}/floor/{relative}", body.encode("utf-8"), mode=0o644)
            for name, body in toolbox.files().items():
                self.client.upload(box, f"{REMOTE_TOOLBOX}/{name}", body.encode("utf-8"), mode=0o644)
            self.client.upload(box, f"{REMOTE_TOOLBOX}/__init__.py", b"", mode=0o644)
            self.client.upload(box, f"{REMOTE_RUN}/main.py", code.encode("utf-8"), mode=0o644)
            command = (
                f"cd {REMOTE_ROOT} && PYTHONPATH={REMOTE_ROOT}:{REMOTE_ROOT}/floor "
                f"timeout {timeout} python3 {REMOTE_RUN}/main.py"
            )
            result = self.client.exec(box, ["sh", "-c", command], timeout=timeout + 30)
            output = result.output or (result.stdout + result.stderr)
            code_out = result.return_code if result.return_code is not None else (0 if result.ok else 1)
        except SailboxError as exc:
            output, code_out = f"sandbox error: {exc}", 5
            box = box or self.box_for(desk_id)
        except Exception as exc:  # the tool loop must see a result, never a traceback
            output, code_out = f"sandbox error: {type(exc).__name__}: {exc}", 5
            box = box or self.box_for(desk_id)
        elapsed = max(0.0, float(self.clock()) - started)
        self._charge(desk_id, elapsed)
        return CodeRun(
            desk_id,
            digest,
            bounded(output),
            int(code_out),
            Decimal(str(round(elapsed, 3))),
            box,
            purpose,
            saved_as=save_as,
        )

    def sleep_all(self) -> int:
        """Put every sandbox to sleep; free while asleep. Returns how many were told to."""
        count = 0
        for _desk_id, box in sorted((self.state().get("boxes") or {}).items()):
            try:
                self.client.sleep(box)
                count += 1
            except Exception:
                continue
        return count


#: The `run_code` tool as the model sees it. Registered in `ltcm/tools.py`; kept here so the
#: sandbox owns its own contract. `save_as` turns a one-off analysis into a reusable tool.
RUN_CODE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "name": "run_code",
    "description": (
        "Run Python in your own sandbox with numpy, pandas and labkit: bars(symbol, interval, "
        "limit), quote(symbol), kalshi_series(series), kalshi_market(ticker), "
        "kalshi_markets(query), news(query). Test a signal on real history or fit a probability "
        "before you trade. Print what you want back (4000 chars, two minutes). save_as keeps the "
        "code as toolbox.<name>."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python 3 source, under 40000 characters."},
            "purpose": {
                "type": "string",
                "description": "One line: what this run is for, published. Optional, but say it.",
            },
            "save_as": {
                "type": "string",
                "description": "Optional tool name (lowercase letters, digits, underscores) to keep this code.",
            },
        },
        # `code` alone is required: on Sept 16, 2026 a 24-turn hourly session burned a third of
        # its turns on calls the schema refused for a missing purpose line.
        "required": ["code"],
        "additionalProperties": False,
    },
}


def execute_run_code(manager: "SandboxManager | None", desk_id: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """The tool's executor: validates, runs, and returns the run as a plain dict for the model."""
    code = arguments.get("code")
    purpose = str(arguments.get("purpose") or "unlabelled run")[:200]
    save_as = arguments.get("save_as")
    if save_as is not None and not isinstance(save_as, str):
        save_as = None
    if manager is None:
        run = CodeRun(desk_id, sha256_text(str(code or "")), "no sandbox is available on this floor", 3, Decimal("0"), None, purpose)
    else:
        run = manager.run(desk_id, code if isinstance(code, str) else "", purpose=purpose, save_as=save_as or None)
    return {
        "exit_code": run.exit_code,
        "output": run.stdout,
        "seconds": str(run.seconds),
        "code_sha256": run.code_sha256,
        **({"saved_as": run.saved_as} if run.saved_as else {}),
    }


class LabImage:
    """Provision the lab image once and checkpoint it. The checkpoint id is the image."""

    def __init__(self, client: Any, *, app: str, repo_root: str | Path, record_path: str | Path):
        self.client = client
        self.app = app
        self.repo_root = Path(repo_root)
        self.record_path = Path(record_path)

    def record(self) -> dict[str, Any]:
        try:
            return json.loads(self.record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def floor_files(self) -> dict[str, bytes]:
        """The read-only market-data package and what it imports, nothing else."""
        out: dict[str, bytes] = {}
        package = self.repo_root / "ltcm"
        for relative in ("__init__.py", "broker.py", "events.py", "manifest.py"):
            path = package / relative
            if path.exists():
                out[f"ltcm/{relative}"] = path.read_bytes()
        for path in sorted((package / "data").glob("*.py")):
            out[f"ltcm/data/{path.name}"] = path.read_bytes()
        return out

    def build(self, *, name: str = "ltcm-lab-image", say: Callable[[str], None] = print) -> dict[str, Any]:
        app = self.client.find_app(self.app, mint_if_missing=True)
        say(f"creating the lab image box in app {app['id']}")
        row = self.client.create(
            app=app["id"],
            name=name,
            size="s",
            egress={"allowlist": normalize_hosts(BUILD_HOSTS)},
            auto_sleep={"automatic": False},
        )
        box = str(row["sailbox_id"])
        say(f"  box {box}; provisioning python, numpy, pandas")
        self.client.exec(box, ["sh", "-c", PROVISION], timeout=900).check()
        say("  uploading the floor's data package and labkit")
        for relative, body in self.floor_files().items():
            self.client.upload(box, f"{REMOTE_ROOT}/floor/{relative}", body, mode=0o644)
        self.client.upload(box, f"{REMOTE_ROOT}/labkit.py", LABKIT.encode("utf-8"), mode=0o644)
        check = (
            f"cd {REMOTE_ROOT} && PYTHONPATH={REMOTE_ROOT}:{REMOTE_ROOT}/floor "
            "python3 -c 'import labkit, numpy, pandas; print(\"labkit ok\")'"
        )
        probe = self.client.exec(box, ["sh", "-c", check], timeout=120).check()
        say(f"  {probe.output.strip()[-200:]}")
        say("  checkpointing")
        checkpoint = self.client.checkpoint(box, name=name)
        record = {
            "checkpoint_id": checkpoint.get("checkpoint_id") or checkpoint.get("id"),
            "box_id": box,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "egress_allowlist": normalize_hosts(BUILD_HOSTS),
            "files": sorted(self.floor_files()),
        }
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        self.record_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        say(f"  image checkpoint {record['checkpoint_id']}")
        try:
            self.client.sleep(box)
        except Exception:
            pass
        return record
