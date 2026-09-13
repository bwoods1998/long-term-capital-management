"""Explicit Sailbox hosting; importing/preparing never contacts Sail.

Provisioning accepts a caller-owned HTTP transport (method, /v1/path, body,
request_id) and installed SDK Sailbox factory. Secrets are references in a saved
Sail egress policy, never guest files/environment. Egress cannot limit request
bodies or dollar spend: the coordinator and branch journals enforce their own
frozen allocations. A fork is ONLY taken from a sterile, unstarted seed.

API basis (2026-09-13): docs.sailresearch.com/{sailboxes-credentials,
reference/egress-policy,sailboxes-autosleep,sailboxes-forking,sailboxes-images}.
The installed SDK has HttpPolicy rather than EgressPolicy; lifecycle/policy
operations verify the actual saved HTTP-policy contract on the deployed API.
A local external watchdog recovers managed exec; the guest image has no systemd.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import gzip
import io
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import uuid

REMOTE = "/workspace"
MAX_BUNDLE_BYTES = 8_000_000
ROLES = ("coordinator", "research_seed", "research_branch")
_FORBIDDEN_KEYS = {
    "api_key",
    "client_secret",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "publish_token",
    "schwab",
}


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def stamp(value):
    if not isinstance(value, str):
        raise ValueError("Expected an explicit UTC timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("Expected an explicit UTC timestamp")
    return parsed


def now():
    return datetime.now(timezone.utc)


def _id(value, prefix):
    if not isinstance(value, str) or not value.startswith(prefix + "_"):
        raise ValueError("Unexpected provider resource ID")
    uuid.UUID(value[len(prefix) + 1 :])
    return value


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", value
    ):
        raise ValueError("Expected a short fixed identifier")
    return value


def _no_secrets(value):
    if isinstance(value, dict):
        if any(str(k).lower() in _FORBIDDEN_KEYS for k in value):
            raise ValueError("Secret/account fields cannot enter the guest bundle")
        for item in value.values():
            _no_secrets(item)
    elif isinstance(value, list):
        for item in value:
            _no_secrets(item)


def _relative(value):
    if not isinstance(value, str):
        raise ValueError("Upload path must be text")
    path = PurePosixPath(value)
    if (
        str(path) != value
        or path.is_absolute()
        or any(
            p.startswith(".") or p in ("state", "credentials", "schwab")
            for p in path.parts
        )
        or not (
            (path.parts[0] == "portfolio_runtime" and path.suffix == ".py")
            or (path.parts[0] in ("data", "config") and path.suffix == ".json")
        )
    ):
        raise ValueError(
            "Only explicit runtime code and public evidence/config paths may be uploaded"
        )
    return path


def freeze_bundle(root, names, config, *, role="coordinator", deadline):
    """Offline explicit allowlist; config is supplied separately, never a private file."""
    if role not in ROLES or stamp(deadline) <= now():
        raise ValueError("Invalid role or expired deployment")
    _no_secrets(config)
    root = Path(root).resolve()
    files = {}
    for name in names:
        path = _relative(name)
        if name in files or name == "config/run.json":
            raise ValueError("Duplicate or reserved upload path")
        source = root.joinpath(*path.parts)
        if any(
            root.joinpath(*path.parts[:i]).is_symlink()
            for i in range(1, len(path.parts) + 1)
        ):
            raise ValueError("Symlink uploads are forbidden")
        raw = source.read_bytes()
        if path.suffix == ".json":
            _no_secrets(json.loads(raw))
        files[name] = raw
    if "portfolio_runtime/runner.py" not in files:
        raise ValueError("Frozen runtime entrypoint is required")
    files["config/run.json"] = encoded(config)
    if sum(map(len, files.values())) > MAX_BUNDLE_BYTES:
        raise ValueError("Bundle exceeds upload envelope")
    manifest = {
        "schema_version": 1,
        "role": role,
        "deadline": deadline,
        "files": {
            k: {"sha256": sha(v), "bytes": len(v)} for k, v in sorted(files.items())
        },
    }
    return {"manifest": manifest, "sha256": sha(encoded(manifest)), "files": files}


def validate_bundle(bundle):
    manifest, files = bundle["manifest"], bundle["files"]
    if (
        set(manifest) != {"schema_version", "role", "deadline", "files"}
        or manifest["schema_version"] != 1
        or manifest["role"] not in ROLES
        or bundle["sha256"] != sha(encoded(manifest))
        or set(files) != set(manifest["files"])
    ):
        raise ValueError("Frozen bundle identity changed")
    stamp(manifest["deadline"])
    for name, raw in files.items():
        _relative(name)
        if not isinstance(raw, bytes) or manifest["files"][name] != {
            "sha256": sha(raw),
            "bytes": len(raw),
        }:
            raise ValueError("Frozen file bytes changed")
        if name.endswith(".json"):
            _no_secrets(json.loads(raw))
    if sum(map(len, files.values())) > MAX_BUNDLE_BYTES:
        raise ValueError("Bundle exceeds upload envelope")
    return manifest


def restricted_policy(
    inference_secret,
    *,
    publish_secret=None,
    telemetry=False,
    own_box_id=None,
    sec_sources=False,
):
    """Return a document to SAVE before use; all unmatched HTTPS paths answer 403.

    Telemetry enables only /v1/voyages and its descendants, never general control
    APIs. own_box_id permits only that box's sleep/wake scheduling, if desired.
    These are application restrictions, not a provider-enforced financial cap.
    """

    def rule(secret, method, path):
        _name(secret)
        return {
            "match": {"method": method, "path": path},
            "request": {
                "set": {
                    "headers": {"authorization": "Bearer ${secrets." + secret + "}"}
                }
            },
        }

    deny = {"respond": {"status": 403, "body": "Route not authorized"}}
    rules = [
        rule(inference_secret, "POST", "/v1/responses"),
        rule(inference_secret, "GET", {"prefix": "/v1/responses/"}),
    ]
    if telemetry:
        rules += [
            rule(inference_secret, "POST", "/v1/voyages"),
            rule(
                inference_secret, ["GET", "POST", "PATCH"], {"prefix": "/v1/voyages/"}
            ),
        ]
    result = {
        "allowlist": ["api.sailresearch.com"],
        "rules": {"api.sailresearch.com": rules + [deny]},
        "missing_alpn": {"api.sailresearch.com": "http/1.1"},
    }
    if publish_secret:
        result["allowlist"].append("blakewoods.us")
        result["rules"]["blakewoods.us"] = [
            rule(publish_secret, "POST", "/api/portfolio/state"),
            deny,
        ]
        result["missing_alpn"]["blakewoods.us"] = "http/1.1"
    if sec_sources:
        for host, prefix in (
            ("data.sec.gov", "/submissions/"),
            ("www.sec.gov", "/Archives/edgar/data/"),
        ):
            result["allowlist"].append(host)
            result["rules"][host] = [
                {"match": {"method": "GET", "path": {"prefix": prefix}}},
                deny,
            ]
            result["missing_alpn"][host] = "http/1.1"
    if own_box_id:
        _id(own_box_id, "sb")
        host = "sailbox-api.sailresearch.com"
        result["allowlist"].append(host)
        result["rules"][host] = [
            rule(inference_secret, "POST", "/v1/sailboxes/" + own_box_id + suffix)
            for suffix in ("/sleep", "/wake_at")
        ] + [deny]
        result["missing_alpn"][host] = "http/1.1"
    return result


def http_document(document):
    """Equivalent legacy host-map policy; network allowlist is verified separately."""
    result = json.loads(
        json.dumps(
            {
                host: {
                    "rules": document["rules"][host],
                    "missing_alpn": document["missing_alpn"][host],
                }
                for host in document["allowlist"]
            }
        )
    )
    for host in result.values():
        for rule in host["rules"]:
            match = rule.get("match", {})
            if isinstance(match.get("path"), str):
                match["path"] = {"equals": match["path"]}
    return result


def _validate_policy(document, role, box_id):
    try:

        def secret(host):
            value = document["rules"][host][0]["request"]["set"]["headers"][
                "authorization"
            ]
            match = re.fullmatch(r"Bearer \$\{secrets\.([A-Za-z0-9_-]+)\}", value)
            if not match:
                raise ValueError("Not a saved secret reference")
            return match[1]

        inference = secret("api.sailresearch.com")
        publication = (
            secret("blakewoods.us") if "blakewoods.us" in document["rules"] else None
        )
        telemetry = any(
            r.get("match", {}).get("path") == "/v1/voyages"
            for r in document["rules"]["api.sailresearch.com"]
        )
        own = box_id if "sailbox-api.sailresearch.com" in document["rules"] else None
        sec_sources = any(
            host in document["rules"] for host in ("data.sec.gov", "www.sec.gov")
        )
        expected = restricted_policy(
            inference,
            publish_secret=publication,
            telemetry=telemetry,
            own_box_id=own,
            sec_sources=sec_sources,
        )
        if document != expected or (
            role == "research_branch"
            and (publication or own or telemetry or sec_sources)
        ):
            raise ValueError("Policy exceeds the role-specific route allowlist")
    except (KeyError, TypeError, AttributeError, IndexError):
        raise ValueError("Invalid role-specific egress policy") from None


# Installed only after VM creation. Sail's base image uses saild as PID 1;
# the supported managed exec is supervised by an explicit external watchdog.
BOOT = r"""import fcntl,hashlib,json,os,signal,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
root=Path('/workspace')
if (root/'host-paused').exists():sys.exit(0)
a=json.loads((root/'host-authority.json').read_text())
m=json.loads((root/'host-manifest.json').read_text())
if a['manifest_sha256']!=hashlib.sha256(json.dumps(m,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest():sys.exit(78)
if a['role']!=m['role'] or a['role'] not in ('coordinator','research_branch'):sys.exit(78)
if datetime.now(timezone.utc)>=datetime.fromisoformat(m['deadline'].replace('Z','+00:00')):sys.exit(0)
for name,expected in m['files'].items():
 p=root/name
 if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected['sha256']:sys.exit(78)
(root/'state').mkdir(exist_ok=True,mode=0o700)
f=open(root/'state/coordinator.lock','a')
try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:sys.exit(0)
os.set_inheritable(f.fileno(),True)
(root/'state/host-process.json').write_text(json.dumps({'pid':os.getpid(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))
os.chdir(root)
command=[sys.executable,'-m','portfolio_runtime.runner','run' if a['role']=='coordinator' else 'branch','--config','/workspace/config/run.json']
child=subprocess.Popen(command,pass_fds=(f.fileno(),))
def stop(*_):
 if child.poll() is None:child.send_signal(signal.SIGTERM)
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
sys.exit(child.wait())
"""
PROBE = r"""import fcntl,json,os
from pathlib import Path
root=Path('/workspace');(root/'state').mkdir(exist_ok=True,mode=0o700)
with (root/'state/coordinator.lock').open('a') as f:
 running=False
 try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:running=True
 (root/'host-status.json').write_text(json.dumps({'running':running,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))
"""
STOP = r"""import json,os,signal
from pathlib import Path
p=Path('/workspace/state/host-process.json')
if p.exists():
 state=json.loads(p.read_text());pid=state['pid']
 if isinstance(pid,int) and pid>1:
  try:
   command=Path('/proc/'+str(pid)+'/cmdline').read_bytes()
   if b'/workspace/host-boot.py' in command:os.kill(pid,signal.SIGTERM)
  except ProcessLookupError:pass
  except FileNotFoundError:pass
"""


class SailHost:
    """Caller serializes provisioning; this class additionally locks its journal.

    ``api`` is a supplied control transport, e.g. portfolio_runtime.control.api. SDK calls use
    the owner's local environment only. Neither is invoked by the constructor.
    Frozen config owns inference reservations; this adapter does not mint money.
    """

    def __init__(
        self, journal, *, api, box_factory, policy_contract="egress", allowed_hosts=()
    ):
        self.path = Path(journal)
        self.api, self.box_factory = api, box_factory
        if policy_contract not in ("egress", "http"):
            raise ValueError("Unknown policy contract")
        if len(set(allowed_hosts)) != len(allowed_hosts) or any(
            not isinstance(h, str)
            or not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", h)
            for h in allowed_hosts
        ):
            raise ValueError("Expected exact host allowlist without wildcards")
        self.policy_contract, self.allowed_hosts = policy_contract, tuple(allowed_hosts)

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.path.with_suffix(".lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def _read(self):
        return json.loads(self.path.read_bytes())

    def _save(self, value):
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("wb") as handle:
            os.chmod(tmp, 0o600)
            handle.write(encoded(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def create(self, app_id, name, bundle):
        """One allocation, initially no-network. Uncertain creation parks safely."""
        manifest = validate_bundle(bundle)
        if stamp(manifest["deadline"]) <= now():
            raise ValueError("Deployment expired")
        _id(app_id, "app")
        _name(name)
        body = {
            "app_id": app_id,
            "name": name,
            "image": {"base": "BASE_IMAGE_DEBIAN"},
            "size": "s",
            "memory_limit_gib": 2,
            "state_disk_limit_gib": 8,
            "visibility": "private",
            "ingress_ports": [],
            "volume_mounts": [],
            "auto_sleep": {"automatic": True, "min_seconds_before_sleep": 60},
            "egress_policy": {"no_network": True},
            "network_policy": {"mode": "no_network"},
        }
        if self.policy_contract == "http":
            body.pop("egress_policy")
            body["network_policy"] = (
                {"mode": "allowlist", "allowed_hosts": list(self.allowed_hosts)}
                if self.allowed_hosts
                else {"mode": "no_network"}
            )
        with self._locked():
            if self.path.exists():
                state = self._read()
                if (
                    state["create_body"] != body
                    or state["manifest_sha256"] != bundle["sha256"]
                ):
                    raise ValueError("Existing host has different frozen inputs")
                if not state.get("sailbox_id"):
                    raise RuntimeError(
                        "Creation unconfirmed: reconcile the original request; do not allocate a replacement"
                    )
                return self._attach(state)
            state = {
                "schema_version": 1,
                "role": manifest["role"],
                "manifest_sha256": bundle["sha256"],
                "deadline": manifest["deadline"],
                "create_body": body,
                "created_at": now().isoformat(),
                "create_key": str(uuid.uuid4()),
                "sailbox_id": None,
                "policy_contract": self.policy_contract,
                "policy": None
                if self.policy_contract == "http"
                else {"no_network": True},
                "policy_id": None,
                "installed": False,
                "started": False,
            }
            self._save(state)
            result = self.api("POST", "/v1/sailboxes", body, state["create_key"])
            state["sailbox_id"] = _id(result["sailbox_id"], "sb")
            self._save(state)
            return self._attach(state)

    def _attach(self, state):
        sid = _id(state["sailbox_id"], "sb")
        row = self.api("GET", "/v1/sailboxes/" + sid)
        legacy = state.get("policy_contract", "egress") == "http"
        if legacy:
            try:
                policy = self.api("GET", "/v1/sailboxes/" + sid + "/http-policy") or {}
            except Exception as error:
                if (
                    getattr(error, "status_code", None) != 404
                    or state["policy_id"] is not None
                ):
                    raise
                policy = {}
            policy_ok = (
                row.get("network_policy") == state["create_body"]["network_policy"]
                and policy.get("document")
                == (http_document(state["policy"]) if state["policy"] else None)
                and policy.get("policy_id", policy.get("id")) == state["policy_id"]
            )
        else:
            policy = row.get("egress_policy") or {}
            policy_ok = (
                policy.get("document") == state["policy"]
                and policy.get("policy_id") == state["policy_id"]
            )
        if (
            row.get("name") != state["create_body"]["name"]
            or row.get("app_id") != state["create_body"]["app_id"]
            or row.get("visibility") != "private"
            or row.get("vcpu_count") != 1
            or row.get("memory_mib") != 2048
            or row.get("state_disk_size_gib") != 8
            or row.get("volume_mounts") != []
            or row.get("ingress_ports") not in (None, [])
            or not policy_ok
            or row.get("status")
            in ("terminated", "failed", "create_failed", "interrupted_unsafe_to_retry")
        ):
            raise ValueError("Host identity, policy or resource isolation differs")
        return self.box_factory(sid)

    def attach(self):
        with self._locked():
            return self._attach(self._read())

    def bind_policy(self, policy_id, document):
        """Bind a saved, reviewed policy. Credentials were registered separately."""
        if not re.fullmatch(r"(ep|hp)_[0-9a-f-]{36}", policy_id):
            raise ValueError("Invalid saved policy ID")
        with self._locked():
            state = self._read()
            if state["started"] or state.get("checkpoint"):
                raise ValueError("Cannot alter active/checkpointed authority")
            validation_role = (
                "research_branch" if state["role"] == "research_seed" else state["role"]
            )
            _validate_policy(document, validation_role, state["sailbox_id"])
            legacy = state.get("policy_contract", "egress") == "http"
            if legacy and state["create_body"]["network_policy"] != {
                "mode": "allowlist",
                "allowed_hosts": document["allowlist"],
            }:
                raise ValueError(
                    "Saved HTTP policy must match the immutable network host allowlist"
                )
            prefix, suffix = (
                ("/v1/http-policies/", "/http-policy")
                if legacy
                else ("/v1/egress-policies/", "/egress-policy")
            )
            saved = self.api("GET", prefix + policy_id)
            expected_saved = http_document(document) if legacy else document
            if saved.get("document") != expected_saved:
                raise ValueError("Saved policy differs from reviewed document")
            self.api(
                "PUT",
                "/v1/sailboxes/" + state["sailbox_id"] + suffix,
                {"policy_id": policy_id},
            )
            state.update(policy=document, policy_id=policy_id)
            self._save(state)
            self._attach(state)

    def install(self, bundle):
        manifest = validate_bundle(bundle)
        with self._locked():
            state = self._read()
            if (
                state["manifest_sha256"] != bundle["sha256"]
                or state["role"] != manifest["role"]
            ):
                raise ValueError("Cannot replace frozen runtime inputs")
            box = self._attach(state)
            if state["started"]:
                raise ValueError("Never overwrite a started host")
            files = {REMOTE + "/" + k: v for k, v in bundle["files"].items()}
            files[REMOTE + "/host-manifest.json"] = encoded(manifest)
            if state["role"] != "research_seed":
                files[REMOTE + "/host-authority.json"] = encoded(
                    {
                        "role": state["role"],
                        "sailbox_id": state["sailbox_id"],
                        "manifest_sha256": bundle["sha256"],
                    }
                )
                files[REMOTE + "/host-boot.py"] = BOOT.encode()
                files[REMOTE + "/host-probe.py"] = PROBE.encode()
                files[REMOTE + "/host-stop.py"] = STOP.encode()
            for name, raw in sorted(files.items()):
                box.fs.write(name, raw, create_parents=True, mode=0o600)
                if box.fs.read(name) != raw:
                    raise ValueError("Guest upload readback mismatch")
            state["installed"] = True
            self._save(state)

    def _probe(self, box):
        result = box.exec(["python3", "/workspace/host-probe.py"], timeout=20).wait()
        if result.exit_code != 0:
            raise RuntimeError("Could not confirm guest process state")
        result = json.loads(box.fs.read("/workspace/host-status.json"))
        if set(result) != {"running", "boot_id"} or type(result["running"]) is not bool:
            raise ValueError("Invalid guest process observation")
        uuid.UUID(result["boot_id"])
        return result

    def start(self):
        """Ensure one managed exec; explicit watchdog recovers it after cold loss."""
        with self._locked():
            state = self._read()
            if (
                not state["installed"]
                or state["role"] == "research_seed"
                or stamp(state["deadline"]) <= now()
                or not state["policy_id"]
            ):
                raise ValueError("Runtime authority, policy or deadline not ready")
            box = self._attach(state)
            observed = self._probe(box)
            if observed["running"]:
                return {"running": True, "started_new_process": False}
            if (
                box.exec(["rm", "-f", "/workspace/host-paused"], timeout=20)
                .wait()
                .exit_code
                != 0
            ):
                raise RuntimeError("Could not clear explicit pause latch")
            attempts = state.setdefault("executions", [])
            if (
                attempts
                and attempts[-1]["boot_id"] == observed["boot_id"]
                and "terminal_exit" not in attempts[-1]
            ):
                old = attempts[-1]
                process = box.exec(
                    "exec python3 /workspace/host-boot.py",
                    background=True,
                    timeout=old["timeout_seconds"],
                    idempotency_key=old["id"],
                )
                code = process.poll()
                if code is None:
                    return {"running": True, "started_new_process": False}
                old["terminal_exit"] = code
                self._save(state)
                if code == 78:
                    raise ValueError("Frozen guest bootstrap failed validation")
            timeout = max(
                1, int((stamp(state["deadline"]) - now()).total_seconds()) + 120
            )
            attempt = {
                "id": str(uuid.uuid4()),
                "boot_id": observed["boot_id"],
                "timeout_seconds": timeout,
                "created_at": now().isoformat(),
                "confirmed": False,
            }
            attempts.append(attempt)
            state["started"] = True
            self._save(state)
            process = box.exec(
                "exec python3 /workspace/host-boot.py",
                background=True,
                timeout=timeout,
                idempotency_key=attempt["id"],
            )
            if process.exec_request_id != attempt["id"]:
                raise ValueError("Managed exec identity changed")
            attempt["confirmed"] = True
            self._save(state)
            return {"running": True, "started_new_process": True}

    def sleep_until(self, when):
        with self._locked():
            state = self._read()
            if not now() < stamp(when) <= stamp(state["deadline"]):
                raise ValueError("Wake exceeds active window")
            self._attach(state)
            return self.api(
                "POST",
                "/v1/sailboxes/" + state["sailbox_id"] + "/sleep",
                {"wake_at": when},
            )

    def checkpoint_seed(self):
        with self._locked():
            state = self._read()
            restricted = state["policy"] == {"no_network": True}
            if state.get("policy_contract") == "http" and state["policy_id"]:
                _validate_policy(
                    state["policy"], "research_branch", state["sailbox_id"]
                )
                restricted = state["create_body"]["network_policy"] == {
                    "mode": "allowlist",
                    "allowed_hosts": ["api.sailresearch.com"],
                }
            if (
                state["role"] != "research_seed"
                or state["started"]
                or not state["installed"]
                or not restricted
            ):
                raise ValueError("Only a sterile unstarted seed may be forked")
            box = self._attach(state)
            check = box.exec(["test", "!", "-e", "/workspace/state"], timeout=20).wait()
            if check.exit_code != 0:
                raise ValueError("Seed contains a ledger/state directory")
            if state.get("checkpoint"):
                return state["checkpoint"]
            state.setdefault("checkpoint_key", str(uuid.uuid4()))
            self._save(state)
            result = self.api(
                "POST",
                "/v1/sailboxes/" + state["sailbox_id"] + "/checkpoint",
                {"name": state["create_body"]["name"] + "-seed", "ttl_seconds": 86400},
                state["checkpoint_key"],
            )
            _id(result["checkpoint_id"], "sbcp")
            if result.get("sailbox_id") != state["sailbox_id"]:
                raise ValueError("Checkpoint source mismatch")
            state["checkpoint"] = result
            self._save(state)
            return result

    def fork_research(self, seed, bundle, name):
        """Create one child from a seed; child has a NEW task config/no parent DB.

        Parent must durably reserve all assigned request IDs and dollars first.
        The branch config requires research_only=true, no publication endpoint,
        a nonempty finite allowance and explicit assigned task identities.
        """
        manifest = validate_bundle(bundle)
        config = json.loads(bundle["files"]["config/run.json"])
        if (
            manifest["role"] != "research_branch"
            or config.get("research_only") is not True
            or config.get("publish_url")
            or not config.get("assigned_task_ids")
            or not isinstance(config["assigned_task_ids"], list)
            or any(
                not isinstance(k, str) or not 1 <= len(k) <= 200
                for k in config["assigned_task_ids"]
            )
            or len(set(config["assigned_task_ids"])) != len(config["assigned_task_ids"])
            or stamp(manifest["deadline"]) <= now()
        ):
            raise ValueError("Branch must have isolated research-only task assignment")
        allowance = Decimal(str(config.get("inference_budget_usd", "0")))
        if not allowance.is_finite() or not 0 < allowance <= 20:
            raise ValueError("Invalid branch sub-allowance")
        _name(name)
        checkpoint = seed.checkpoint_seed()
        source = seed._read()
        if stamp(checkpoint["expires_at"]) <= now() or stamp(
            manifest["deadline"]
        ) > stamp(source["deadline"]):
            raise ValueError("Expired checkpoint or branch beyond parent window")
        with self._locked():
            if self.path.exists():
                state = self._read()
                if (
                    state["manifest_sha256"] != bundle["sha256"]
                    or state.get("checkpoint_id") != checkpoint["checkpoint_id"]
                ):
                    raise ValueError("Branch journal belongs to a different assignment")
                if not state.get("sailbox_id"):
                    raise RuntimeError("Fork unconfirmed; no replacement allocation")
                return self._attach(state)
            state = dict(source)
            state.update(
                role="research_branch",
                manifest_sha256=bundle["sha256"],
                deadline=manifest["deadline"],
                create_key=str(uuid.uuid4()),
                sailbox_id=None,
                installed=False,
                started=False,
                checkpoint_id=checkpoint["checkpoint_id"],
                create_body={**source["create_body"], "name": name},
            )
            state.pop("checkpoint", None)
            state.pop("checkpoint_key", None)
            self._save(state)
            response = self.api(
                "POST",
                "/v1/sailboxes/from_checkpoint",
                {"checkpoint_id": checkpoint["checkpoint_id"], "name": name},
                state["create_key"],
            )
            state["sailbox_id"] = _id(response["sailbox_id"], "sb")
            self._save(state)
            if response.get("checkpoint_id") != checkpoint["checkpoint_id"]:
                raise ValueError("Fork source mismatch")
            return self._attach(state)

    def stop(self, *, sleep=True):
        """Latch stop, signal the coordinator, preserve disk, optionally sleep."""
        import time

        with self._locked():
            state = self._read()
            box = self._attach(state)
            box.fs.write("/workspace/host-paused", b"paused\n", mode=0o600)
            result = box.exec(["python3", "/workspace/host-stop.py"], timeout=20).wait()
            if result.exit_code != 0:
                raise RuntimeError("Stop signal unconfirmed")
            until = time.monotonic() + 90
            while self._probe(box)["running"]:
                if time.monotonic() >= until:
                    raise RuntimeError("Coordinator has not finished stopping")
                time.sleep(3)
            return (
                self.api("POST", "/v1/sailboxes/" + state["sailbox_id"] + "/sleep", {})
                if sleep
                else {"stopped": True}
            )

    def backup_state(self, destination):
        """Consistent per-database snapshots, compressed on guest, streamed locally.

        Raw filings remain on the persistent guest disk. Stop the runtime before
        backup when a cross-database point-in-time snapshot is required.
        """
        destination = Path(destination)
        if destination.exists():
            raise ValueError("Choose a new private backup directory")
        with self._locked():
            state = self._read()
            box = self._attach(state)
            key = str(uuid.uuid4())
            script = BACKUP.replace("SNAPSHOT_ID", key)
            result = box.exec(
                ["python3", "-c", script], timeout=300, idempotency_key=key
            ).wait()
            if result.exit_code != 0:
                raise RuntimeError("State backup incomplete; source journals unchanged")
            remote = "/workspace/exports/" + key
            manifest_raw = box.fs.read(remote + "/manifest.json")
            if len(manifest_raw) > 10000:
                raise ValueError("Oversized backup manifest")
            manifest = json.loads(manifest_raw)
            names = {
                "requests.sqlite",
                "research.sqlite",
                "paper.sqlite",
                "voyage.sqlite",
            }
            if (
                not isinstance(manifest, dict)
                or not manifest
                or not set(manifest) <= names
            ):
                raise ValueError("Unexpected backup manifest")
            destination.mkdir(parents=True, mode=0o700)
            for name, entry in manifest.items():
                if (
                    set(entry)
                    != {"bytes", "sha256", "compressed_bytes", "compressed_sha256"}
                    or type(entry["bytes"]) is not int
                    or not 0 < entry["bytes"] <= 2_000_000_000
                    or type(entry["compressed_bytes"]) is not int
                    or not 0 < entry["compressed_bytes"] <= 64_000_000
                    or any(
                        not re.fullmatch(r"[0-9a-f]{64}", str(entry[k]))
                        for k in ("sha256", "compressed_sha256")
                    )
                ):
                    raise ValueError(
                        "Backup size or identity exceeds retrieval envelope"
                    )
                compressed = box.fs.read(remote + "/" + name + ".gz")
                if (
                    len(compressed) != entry["compressed_bytes"]
                    or sha(compressed) != entry["compressed_sha256"]
                ):
                    raise ValueError("Compressed backup hash mismatch")
                path = destination / name
                count = 0
                digest = hashlib.sha256()
                fd = os.open(
                    path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
                )
                with (
                    os.fdopen(fd, "wb") as output,
                    gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream,
                ):
                    while raw := stream.read(1_048_576):
                        count += len(raw)
                        if count > entry["bytes"]:
                            raise ValueError("Expanded backup exceeds saved bound")
                        digest.update(raw)
                        output.write(raw)
                if count != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
                    raise ValueError("Expanded backup hash mismatch")
            receipt = {
                "schema_version": 2,
                "sailbox_id": state["sailbox_id"],
                "manifest_sha256": state["manifest_sha256"],
                "snapshot_id": key,
                "captured_at": now().isoformat(),
                "files": manifest,
                "consistent_across_databases": False,
                "raw_filings_included": False,
            }
            path = destination / "receipt.json"
            path.write_bytes(encoded(receipt))
            path.chmod(0o600)
            return receipt


BACKUP = r"""
import gzip, hashlib, json, pathlib, sqlite3
out = pathlib.Path('/workspace/exports/SNAPSHOT_ID')
out.mkdir(parents=True, mode=0o700)
rows = {}
for name in ('requests.sqlite', 'research.sqlite', 'paper.sqlite', 'voyage.sqlite'):
    source = pathlib.Path('/workspace/state') / name
    if source.is_symlink(): raise ValueError('Unexpected state symlink')
    if not source.exists(): continue
    snapshot = out / name
    src = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    dst = sqlite3.connect(snapshot)
    src.backup(dst); dst.close(); src.close()
    if not 0 < snapshot.stat().st_size <= 2_000_000_000:
        raise ValueError('Raw database exceeds snapshot envelope')
    digest = hashlib.sha256(); count = 0
    with snapshot.open('rb') as raw, gzip.open(str(snapshot) + '.gz', 'wb', compresslevel=6) as compressed:
        while chunk := raw.read(1_048_576):
            count += len(chunk); digest.update(chunk); compressed.write(chunk)
    archive = pathlib.Path(str(snapshot) + '.gz')
    if not 0 < archive.stat().st_size <= 64_000_000:
        raise ValueError('Compressed snapshot exceeds retrieval envelope')
    compressed_digest = hashlib.sha256()
    with archive.open('rb') as stream:
        while chunk := stream.read(1_048_576): compressed_digest.update(chunk)
    rows[name] = {'bytes':count, 'sha256':digest.hexdigest(),
                  'compressed_bytes':archive.stat().st_size,
                  'compressed_sha256':compressed_digest.hexdigest()}
    snapshot.unlink()
(out / 'manifest.json').write_text(json.dumps(rows, sort_keys=True))
"""
