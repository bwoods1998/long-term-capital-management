#!/usr/bin/env python3
"""Explicit provision/start/status/stop/backup for one frozen Sailbox runtime.

Provision installs but does not start inference. Secrets are saved provider-side
and injected only into exact allowlisted destinations; they never enter a bundle.
Ambiguous create responses park their persisted identity for reconciliation.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, build_opener
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio_runtime.sail_host import (
    SailHost,
    freeze_bundle,
    validate_bundle,
    bundle_disk_limit_gib,
    restricted_policy,
    http_document,
    encoded,
    sha,
    stamp,
)
from portfolio_runtime.evidence import save, NoRedirect

ROOT = Path(__file__).resolve().parents[1]
NAMES = tuple(
    "portfolio_runtime/" + name + ".py"
    for name in (
        "__init__",
        "accounting",
        "contracts",
        "evidence",
        "ledger",
        "market",
        "provider",
        "research",
        "runner",
        "telemetry",
        "filings",
        "evaluation",
        "credentials",
    )
) + ("data/sp500-evidence.json",)


def cloud_cost_bound(rates, bundle, *, current_epoch=None):
    """Reserve the frozen host ceilings through its maximum shutdown grace."""
    disk_gib = bundle_disk_limit_gib(bundle)
    keys = (
        "vcpu_second_usd_nanos",
        "memory_gib_second_usd_nanos",
        "state_disk_gib_second_usd_nanos",
        "s_creation_usd_nanos",
    )
    if any(type(rates.get(k)) is not int or rates[k] < 0 for k in keys):
        raise ValueError("Current cloud rates are unavailable")
    at = time.time() if current_epoch is None else current_epoch
    seconds = math.ceil(max(0, stamp(bundle["manifest"]["deadline"]).timestamp() - at))
    seconds += 300 if disk_gib == 32 else 120
    return Decimal(
        (rates[keys[0]] + 2 * rates[keys[1]] + disk_gib * rates[keys[2]]) * seconds
        + rates[keys[3]]
    ) / 1_000_000_000


def private_read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("Expected a private regular file")
    value = path.read_text().strip()
    if not value or any(ord(char) < 32 for char in value):
        raise ValueError("Expected one nonempty private line")
    return value


@contextmanager
def private_lock(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("Host directory cannot be a symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "operation.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def load_bundle(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    files = {}
    for name in manifest["files"]:
        source = directory / name
        if not source.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Frozen file escaped bundle")
        if source.is_symlink():
            raise ValueError("Frozen file cannot be a symlink")
        files[name] = source.read_bytes()
    bundle = {"manifest": manifest, "files": files, "sha256": sha(encoded(manifest))}
    validate_bundle(bundle)
    return bundle


def save_bundle(directory, bundle):
    validate_bundle(bundle)
    directory = Path(directory)
    if directory.exists():
        previous = load_bundle(directory)
        if previous["sha256"] != bundle["sha256"]:
            raise ValueError("Frozen host bundle changed")
        return
    directory.mkdir(parents=True, mode=0o700)
    for name, raw in bundle["files"].items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(raw)
        path.chmod(0o600)
    save(directory / "manifest.json", bundle["manifest"])


def guest_config(config, *, voyage_id=None):
    allowed = {
        "schema_version",
        "run_id",
        "account_created_at",
        "state_dir",
        "evidence_path",
        "evidence_sha256",
        "started_epoch",
        "ends_epoch",
        "drain_seconds",
        "inference_budget_usd",
        "cloud_budget_usd",
        "key_fingerprint",
        "injected_auth",
        "max_concurrency",
        "wave_seconds",
        "min_wave_seconds",
        "wave_size",
        "publish_url",
        "publish_token_path",
        "voyage_id",
        "fetch_filings",
        "branch_allocations",
    }
    if set(config) - allowed:
        raise ValueError("Review unknown local config fields before upload")
    result = {
        key: value
        for key, value in config.items()
        if key not in ("publish_token_path", "voyage_id")
    }
    result.update(
        state_dir="/workspace/state",
        evidence_path="/workspace/data/sp500-evidence.json",
        injected_auth=True,
        publish_url="https://blakewoods.us/api/portfolio/state",
    )
    if voyage_id:
        result["voyage_id"] = voyage_id
    return result


class HostDeployment:
    def __init__(self, directory, *, api, box_factory, secret_set, inference_api):
        self.directory = Path(directory)
        self.api, self.secret_set, self.inference_api = api, secret_set, inference_api
        self.host = SailHost(
            self.directory / "host.json", api=api, box_factory=box_factory
        )

    def read(self):
        return json.loads((self.directory / "deployment.json").read_text())

    def write(self, state):
        save(self.directory / "deployment.json", state)

    def intent(self, config, app_id, *, publication=True, telemetry=True):
        path = self.directory / "deployment.json"
        contract = {
            "config_sha256": sha(encoded(config)),
            "app_id": app_id,
            "publication": publication,
            "telemetry": telemetry,
        }
        if path.exists():
            state = self.read()
            if state["contract"] != contract:
                raise ValueError("Existing host deployment has different frozen inputs")
            return state
        identity = uuid.uuid4().hex
        state = {
            "schema_version": 1,
            "identity": identity,
            "contract": contract,
            "name": "portfolio-" + identity[:20],
            "inference_secret": "pa_" + identity + "_inference",
            "publication_secret": "pa_" + identity + "_publication"
            if publication
            else None,
            "secret_saved": False,
            "publication_secret_saved": False,
            "voyage_create_key": str(uuid.uuid4()),
            "voyage_attempted": False,
            "voyage_id": None,
            "policy_create_key": str(uuid.uuid4()),
            "policy_attempted": False,
            "policy_id": None,
            "policy_document": None,
            "installed": False,
        }
        self.write(state)  # identities survive any subsequent remote I/O.
        return state

    def ensure_voyage(self, state):
        if not state["contract"]["telemetry"]:
            return None
        if state["voyage_id"]:
            response = self.inference_api("GET", "/v1/voyages/" + state["voyage_id"])
            if response.get("id", response.get("voyage_id")) != state["voyage_id"]:
                raise ValueError("Stored Voyage identity differs")
            return state["voyage_id"]
        if state["voyage_attempted"]:
            raise RuntimeError(
                "Voyage creation unconfirmed; reconcile the saved identity before retrying"
            )
        state["voyage_attempted"] = True
        self.write(state)
        response = self.inference_api(
            "POST",
            "/v1/voyages",
            {
                "name": "portfolio-runtime",
                "version": 1,
                "metadata": {"deployment_identity": state["identity"]},
            },
            state["voyage_create_key"],
        )
        identity = response.get("id", response.get("voyage_id"))
        if not isinstance(identity, str) or not re.fullmatch(
            r"voy_[A-Za-z0-9_-]{8,100}", identity
        ):
            raise RuntimeError("Voyage creation returned an unconfirmed identity")
        state["voyage_id"] = identity
        self.write(state)
        return identity

    def provision(
        self,
        config,
        app_id,
        *,
        key,
        publication_token=None,
        source_root=ROOT,
        names=NAMES,
        bundle=None,
        telemetry=True,
        backup_token=None,
    ):
        """Install only. Starting the service is a separate explicit command."""
        publication = publication_token is not None
        with private_lock(self.directory):
            if hashlib.sha256(key.encode()).hexdigest() != config["key_fingerprint"]:
                raise ValueError("Credential identity changed")
            state = self.intent(
                config, app_id, publication=publication, telemetry=telemetry
            )
            if not state["secret_saved"]:
                self.secret_set(state["inference_secret"], key)
                state["secret_saved"] = True
                self.write(state)
            if publication and not state["publication_secret_saved"]:
                self.secret_set(state["publication_secret"], publication_token)
                state["publication_secret_saved"] = True
                self.write(state)
            weekday = config.get("kind") == "weekday_service"
            if weekday:
                if not backup_token or not publication:
                    raise ValueError("Weekday service requires private backup and publication credentials")
                state.setdefault("backup_secret", "pa_" + state["identity"] + "_backup")
                if not state.get("backup_secret_saved"):
                    self.secret_set(state["backup_secret"], backup_token)
                    state["backup_secret_saved"] = True
                    self.write(state)
            voyage_id = self.ensure_voyage(state)
            if bundle is None:
                guest = ({**config, "injected_auth": True, "voyage_id": voyage_id}
                         if weekday else guest_config(config, voyage_id=voyage_id))
                if not publication:
                    guest.pop("publish_url", None)
                bundle = freeze_bundle(
                    source_root,
                    names,
                    guest,
                    role="coordinator",
                    deadline=config["week_ends_at"] if weekday else datetime.fromtimestamp(
                        config["ends_epoch"], timezone.utc
                    ).isoformat(),
                )
            save_bundle(self.directory / "bundle", bundle)
            frozen = load_bundle(self.directory / "bundle")
            rates = self.api("GET", "/v1/sailboxes/spend").get("rates", {})
            ceiling = cloud_cost_bound(rates, frozen)
            if ceiling > Decimal(config["cloud_budget_usd"]):
                raise ValueError("Host cost bound exceeds the frozen cloud allowance")
            state["cloud_cost_bound_usd"] = str(ceiling)
            state["cloud_rates"] = rates
            self.write(state)
            document = restricted_policy(
                state["inference_secret"],
                publish_secret=state["publication_secret"],
                telemetry=telemetry,
                sec_sources=config.get("fetch_filings", False),
                journal=weekday,
                daily_sources=weekday,
                backup_host=config["backup_url"].split("/")[2] if weekday else None,
                backup_secret=state.get("backup_secret") if weekday else None,
            )
            if not state.get("policy_contract"):
                try:
                    self.api("GET", "/v1/egress-policies?limit=1")
                    state["policy_contract"] = "egress"
                except Exception as error:
                    if getattr(error, "status_code", None) != 404:
                        raise
                    self.api("GET", "/v1/http-policies?limit=1")
                    state["policy_contract"] = "http"
                self.write(state)
            self.host.policy_contract = state["policy_contract"]
            self.host.allowed_hosts = tuple(document["allowlist"])
            self.host.create(app_id, state["name"], frozen)
            if not state["policy_id"]:
                if state["policy_attempted"]:
                    raise RuntimeError(
                        "Policy creation unconfirmed; reconcile the saved policy before retrying"
                    )
                state["policy_document"] = document
                state["policy_attempted"] = True
                self.write(state)
                route = (
                    "/v1/http-policies"
                    if state["policy_contract"] == "http"
                    else "/v1/egress-policies"
                )
                saved_document = (
                    http_document(document)
                    if state["policy_contract"] == "http"
                    else document
                )
                response = self.api(
                    "POST",
                    route,
                    {"name": state["name"], "document": saved_document},
                    state["policy_create_key"],
                )
                identity = response.get("policy_id", response.get("id"))
                if not isinstance(identity, str) or not re.fullmatch(
                    r"(?:ep|hp)_[0-9a-f-]{36}", identity
                ):
                    raise RuntimeError("Saved egress policy identity unconfirmed")
                state["policy_id"] = identity
                self.write(state)
            if not state["installed"]:
                self.host.bind_policy(state["policy_id"], state["policy_document"])
                self.host.install(frozen)
                state["installed"] = True
                self.write(state)
            return {
                "installed": True,
                "started": self.host._read()["started"],
                "manifest_sha256": frozen["sha256"],
                "cloud_cost_bound_usd": str(ceiling),
            }

    def status(self):
        state = self.read()
        host = self.host._read()
        row = self.api("GET", "/v1/sailboxes/" + host["sailbox_id"])
        return {
            "installed": state["installed"],
            "started": host["started"],
            "status": row.get("status"),
            "deadline": host["deadline"],
            "manifest_sha256": host["manifest_sha256"],
            "voyage_recorded": bool(state["voyage_id"]),
        }

    def backup(self, destination):
        receipt = self.host.backup_state(destination)
        destination = Path(destination)
        box = self.host.attach()
        artifacts = {}
        for name in ("report.json", "public.json", "publication-health.json"):
            try:
                raw = box.fs.read("/workspace/state/" + name)
            except Exception:
                continue
            if len(raw) > 2_000_000:
                raise ValueError("Report exceeds retrieval envelope")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("Expected saved report object")
            save(destination / name, value)
            artifacts[name] = {"bytes": len(raw), "sha256": sha(raw)}
        save(destination / "host-summary.json", self.status())
        sid = self.host._read()["sailbox_id"]
        # This remains private; public cost reporting needs reviewed aggregation.
        spend = self.api("GET", "/v1/sailboxes/spend?sailbox_id=" + sid)
        save(destination / "sailbox-spend.json", spend)
        save(destination / "artifacts.json", artifacts)
        return receipt

    def monitor(self):
        """External recovery watchdog; all research state stays on the Sailbox."""
        with private_lock(self.directory / "watchdog"):
            return self._monitor()

    def _monitor(self):
        state = self.host._read()
        deadline = stamp(state["deadline"]).timestamp()
        last_progress = time.time()
        observations = self.directory / "observed"
        observations.mkdir(parents=True, exist_ok=True, mode=0o700)
        while time.time() < deadline:
            try:
                box = self.host.attach()
                public = None
                try:
                    raw = box.fs.read("/workspace/state/public.json")
                    if len(raw) <= 524288:
                        public = json.loads(raw)
                except Exception:
                    pass
                if public is not None:
                    save(observations / "public.json", public)
                    published = stamp(public["published_at"]).timestamp()
                    last_progress = max(last_progress, published)
                if time.time() - last_progress > 300:
                    self.host.stop(sleep=False)
                    last_progress = time.time()
                started = self.host.start()
                if started.get("started_new_process"):
                    last_progress = time.time()
                save(
                    observations / "watchdog.json",
                    {
                        "as_of": datetime.now(timezone.utc).isoformat(),
                        "phase": "monitoring",
                        "host_status": self.status()["status"],
                    },
                )
            except Exception as error:
                save(
                    observations / "watchdog.json",
                    {
                        "as_of": datetime.now(timezone.utc).isoformat(),
                        "phase": "needs_attention",
                        "error_type": type(error).__name__,
                    },
                )
            time.sleep(min(60, max(0, deadline - time.time())))
        sid = self.host._read()["sailbox_id"]
        try:
            # Let the runner publish its natural terminal state after its drain window.
            for _ in range(20):
                if not self.host._probe(self.host.attach())["running"]:
                    break
                time.sleep(3)
            self.host.stop(sleep=False)
            backup = self.directory / "final-backup"
            if not (backup / "receipt.json").exists():
                if backup.exists():
                    raise RuntimeError("Incomplete backup requires a new destination")
                self.backup(backup)
        finally:
            self.api("POST", "/v1/sailboxes/" + sid + "/sleep", {})
        save(
            observations / "watchdog.json",
            {
                "as_of": datetime.now(timezone.utc).isoformat(),
                "phase": "finished",
                "backup": True,
            },
        )
        return {"finished": True, "backup": True}


def clients():
    from portfolio_runtime.credentials import load_api_key
    import sail
    from portfolio_runtime.control import api

    key = load_api_key()
    os.environ["SAIL_API_KEY"] = key

    def inference_api(method, route, body=None, identity=None):
        if not re.fullmatch(r"/v1/voyages(?:/voy_[A-Za-z0-9_-]+)?", route):
            raise ValueError("Unexpected Voyage control route")
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        if identity:
            headers["Idempotency-Key"] = identity
        request = Request(
            "https://api.sailresearch.com" + route,
            data=encoded(body) if body is not None else None,
            headers=headers,
            method=method,
        )
        with build_opener(NoRedirect).open(request, timeout=30) as response:
            raw = response.read(1000001)
            if len(raw) > 1000000:
                raise ValueError("Oversized Voyage control response")
            return json.loads(raw)

    return key, {
        "api": api,
        "box_factory": sail.Sailbox.from_id,
        "secret_set": sail.Secret.set,
        "inference_api": inference_api,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["provision", "start", "status", "stop", "backup", "monitor"]
    )
    parser.add_argument(
        "--config", default=str(ROOT / ".data/runtime/five-hour/run.json")
    )
    parser.add_argument("--app-id")
    parser.add_argument("--destination")
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    if config_path.is_symlink() or not config_path.is_file():
        raise ValueError("Expected an existing private run config")
    config = json.loads(config_path.read_text())
    key, dependencies = clients()
    if hashlib.sha256(key.encode()).hexdigest() != config["key_fingerprint"]:
        raise ValueError("Credential identity changed")
    deployment = HostDeployment(config_path.parent / "host", **dependencies)
    if args.command == "provision":
        if not args.app_id:
            raise ValueError("Provision requires the existing Sail app ID")
        token = private_read(ROOT / ".data/runtime/publish-token")
        result = deployment.provision(
            config, args.app_id, key=key, publication_token=token
        )
    elif args.command == "status":
        result = deployment.status()
    elif args.command == "monitor":
        result = deployment.monitor()
    elif args.command == "start":
        with private_lock(deployment.directory):
            deployment.host.start()
        result = deployment.status()
    elif args.command == "stop":
        with private_lock(deployment.directory):
            deployment.host.stop()
        result = deployment.status()
    else:
        if not args.destination:
            raise ValueError("Backup requires a new private destination")
        with private_lock(deployment.directory):
            receipt = deployment.backup(args.destination)
        result = {
            "backed_up": sorted(receipt["files"]),
            "consistent_across_databases": False,
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Provider bodies/SDK exceptions may contain request details; never echo them.
        print(
            "Host operation did not complete ("
            + type(error).__name__
            + "). Inspect the private operation journal.",
            file=sys.stderr,
        )
        raise SystemExit(1)
