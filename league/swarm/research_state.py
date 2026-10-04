"""Coherent host-only snapshots and an explicitly approved isolated research working view.

No runtime factory, provider, .env loader, evaluator adoption, or financial action is
called here. Raw SQLite/events/KV/result evidence stays in the separate audit archive.
The fresh database preserves research identity and search counts, redacts sealed and
Validation figures, and prevents resource adoption and financial band writes in SQL.
ExportApproval is a trusted host review certificate, never inferred from a filename
or a run's window. Filesystem/mount/UID isolation is still a launcher's responsibility.
The clone is private research state and must never be imported into production without
separate trial/lineage reconciliation; creating two clones does not reset a look budget.
"""

from __future__ import annotations

import hashlib
import datetime as dt
import json
import math
import os
import re
import shutil
import sqlite3
import stat
import time
import uuid
from dataclasses import asdict, dataclass
from contextlib import closing
from pathlib import Path, PurePosixPath
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from . import DB_NAME, PROGRAMS_DIR, RUNS_DIR
from .store import SCHEMA

MANIFEST = "research-snapshot.json"
WORKING_MANIFEST = "isolated-research.json"
IMPORT_KEY = "isolated_research_state"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}\Z")
_TRAIN_PURPOSES = {"train", "probe", "mechanism", "robustness"}
_SPEC_KEYS = {"id", "mechanism", "structure", "roots", "dte", "card_sha", "prior_lineage", "prior_lineages"}
# Original operator predeclarations are cell identities, not supported options
# structures. Retain these exact reviewed labels; never map them into a current
# options cell or infer a new permissible structure from their words.
_LEGACY_OPERATOR_STRUCTURES = frozenset({"long_call + long_put (pair)", "long_call / long_put",
    "underlying only (zero-cost daily returns, no options)", "debit_vertical + long_call",
    "none (signal study on underlying returns)", "debit_vertical (long_straddle compared)"})
_COUNTERS = ("trials", "inherited_trials", "inherited_looks", "revisions", "cycles", "rewrites", "validations")
_OWED_BARS = "incubator-bars-owed.json"
_RESEARCH_KV = {"research_evaluator", "program_lineages_indexed", IMPORT_KEY, "train_objective", "claude_band",
                "cohort_keep", "tournament_at", "leaderboard", "architect_at", "architect_structure_refusals",
                "architect_card_refusals", "architect_agenda_section", "graveyard_digest_seal", "graveyard_digest_cpt",
                "graveyard_digest_last", "research_adapter_receipts_v1", "isolated_controller_heartbeat"}


class ResearchStateError(RuntimeError):
    pass


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ResearchStateError(f"invalid {label}")
    return value


def _name(value, label):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ResearchStateError(f"invalid {label}")
    return value


def _json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ResearchStateError("duplicate evidence field")
            out[key] = value
        return out
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(
            ResearchStateError("nonfinite evidence field")))
    except (ValueError, TypeError) as exc:
        raise ResearchStateError("unreadable research evidence") from exc


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ResearchStateError("unreadable research evidence") from exc


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _value_sha(value):
    return _digest(_canonical(value).encode())


def _private(path):
    if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ResearchStateError("research archive and working directories must be private")


def _disjoint(*paths):
    roots = [p.resolve() for p in paths]
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(roots) for b in roots[i + 1:]):
        raise ResearchStateError("source, raw audit archive and working mount must be disjoint")


def _file(root, relative, namespace=None):
    if not isinstance(relative, str):
        raise ResearchStateError("artifact needs a relative path")
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(p in (".", "..", "") for p in path.parts):
        raise ResearchStateError("unsafe artifact path")
    if path.as_posix() != relative or (namespace is not None and path.parts[0] != namespace):
        raise ResearchStateError("artifact outside the approved namespace")
    target = root
    for part in path.parts:
        target /= part
        if target.is_symlink():
            raise ResearchStateError("symlinked artifacts are refused")
    if root.resolve() not in target.resolve().parents:
        raise ResearchStateError("artifact escapes its state root")
    return target


def _read_file(root, relative, namespace=None):
    path = _file(root, relative, namespace)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > 128 * 2 ** 20:
                raise ResearchStateError("artifact is not a bounded regular file")
            body = handle.read()
            after = os.fstat(handle.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ResearchStateError("artifact changed during snapshot")
        return body
    except OSError as exc:
        raise ResearchStateError("referenced artifact is unavailable") from exc


def _write_file(root, relative, body):
    path = _file(root, relative)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("xb") as handle:
        os.chmod(path, 0o600)
        handle.write(body)


def _connect(path):
    connection = sqlite3.connect(f"file:{quote(str(path.resolve()), safe='/')}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _rows(connection, table):
    # Table names only come from this module's fixed allowlist.
    found = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')] if found else []


@dataclass(frozen=True)
class ArtifactIdentity:
    image: str
    bundle: str
    execution: str

    def __post_init__(self):
        _text(self.image, "Train/Validation checkpoint identity")
        _text(self.bundle, "actual Gym bundle identity")
        if not isinstance(self.execution, str) or not _SHA.fullmatch(self.execution):
            raise ResearchStateError("actual execution SHA256 is required")


def artifact_identity(image: str, artifact_root: Path | str) -> ArtifactIdentity:
    """Hash actual immutable source bytes; never reuse evaluator's process-global cache."""
    from ..gym.driver import LEAGUE_FILES, build_bundle
    root = Path(artifact_root).resolve()
    _, bundle = build_bundle(root)
    files = {root / name for name in LEAGUE_FILES}
    for name in ("gym", "live"):
        files.update((root / "league" / name).rglob("*.py"))
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return ArtifactIdentity(image, bundle, digest.hexdigest())


def _identity(value):
    if value is None:
        return None
    if isinstance(value, ArtifactIdentity):
        return asdict(value)
    if not isinstance(value, dict) or set(value) != {"image", "bundle", "execution"}:
        raise ResearchStateError("evaluator identity must contain only image, bundle and execution")
    return asdict(ArtifactIdentity(**value))


@dataclass(frozen=True)
class ExportApproval:
    """Host review authorizes these exact development-safe bytes; no defaults authorize exports."""
    snapshot_id: str
    manifest_sha256: str
    metadata_sha256: str
    program_sha256s: tuple[str, ...]
    train_run_ids: tuple[str, ...]
    provenance: str
    safe_metadata_sha256: str

    def __post_init__(self):
        _name(self.snapshot_id, "snapshot ID")
        for field in ("manifest_sha256", "metadata_sha256", "safe_metadata_sha256"):
            if not isinstance(getattr(self, field), str) or not _SHA.fullmatch(getattr(self, field)):
                raise ResearchStateError("approval needs exact snapshot and metadata hashes")
        if not isinstance(self.program_sha256s, tuple) or any(not isinstance(v, str) or not _SHA.fullmatch(v) for v in self.program_sha256s):
            raise ResearchStateError("approval needs exact program SHA256 values")
        if not isinstance(self.train_run_ids, tuple) or any(not isinstance(v, str) or not v for v in self.train_run_ids):
            raise ResearchStateError("approval needs exact Train run identities")
        if len(set(self.program_sha256s)) != len(self.program_sha256s) or len(set(self.train_run_ids)) != len(self.train_run_ids):
            raise ResearchStateError("duplicate export approval identity")
        _text(self.provenance, "host export review provenance")


@dataclass(frozen=True)
class SafeMetadataProjection:
    """Explicit host-reviewed development metadata, never an automatic redaction approval.

    Each tuple must cover the entire corresponding source metadata collection. Family
    specs contain only the fixed development fields; descriptions are reviewed text.
    Version parameters and card control fields retain their exact original values.
    The original archive and this projection have separate, approval-bound hashes.
    """
    source_metadata_sha256: str
    families: tuple[dict, ...]
    operators: tuple[dict, ...]
    cards: tuple[dict, ...]
    version_params: tuple[dict, ...]
    provenance: str

    def __post_init__(self):
        if not isinstance(self.source_metadata_sha256, str) or not _SHA.fullmatch(self.source_metadata_sha256):
            raise ResearchStateError("safe projection needs the original metadata SHA256")
        for field in ("families", "operators", "cards", "version_params"):
            if not isinstance(getattr(self, field), tuple) or any(type(row) is not dict for row in getattr(self, field)):
                raise ResearchStateError("safe projection needs explicit metadata tuples")
        _text(self.provenance, "safe metadata review provenance")
        _canonical(asdict(self))

    @property
    def sha256(self):
        return _value_sha(asdict(self))


def _projection_rows(rows, fields, identity):
    out = {}
    for row in rows:
        if set(row) != set(fields):
            raise ResearchStateError("safe metadata projection has missing or unknown fields")
        key = tuple(row[k] for k in identity)
        try:
            if key in out:
                raise ResearchStateError("duplicate safe metadata identity")
            out[key] = row
        except TypeError as exc:
            raise ResearchStateError("invalid safe metadata identity") from exc
    return out


def _approved_projection(source, projection, approval):
    """Validate exact structural coverage before copying a single development description."""
    from . import cards
    if not isinstance(projection, SafeMetadataProjection):
        raise ResearchStateError("explicit matching host-reviewed safe metadata projection required")
    # Capture nested dictionaries once; the frozen dataclass does not freeze its
    # contents, and concurrent caller mutation must never swap approved bytes.
    frozen = _json(_canonical(asdict(projection)))
    if (frozen["source_metadata_sha256"] != approval.metadata_sha256
            or _value_sha(frozen) != approval.safe_metadata_sha256):
        raise ResearchStateError("explicit matching host-reviewed safe metadata projection required")
    metadata = _metadata(source)
    families = _projection_rows(frozen["families"], ("id", "mechanism", "spec"), ("id",))
    operators = _projection_rows(frozen["operators"], ("family", "mechanism", "structure", "roots"), ("family",))
    projected_cards = _projection_rows(frozen["cards"], ("family", "card"), ("family",))
    params = _projection_rows(frozen["version_params"], ("family", "n", "sha", "params"), ("family", "n"))
    for rows, originals, identity in ((families, metadata["families"], ("id",)),
                                     (operators, metadata["operators"], ("family",)),
                                     (projected_cards, metadata["cards"], ("family",)),
                                     (params, metadata["versions"], ("family", "n"))):
        if set(rows) != {tuple(row[k] for k in identity) for row in originals}:
            raise ResearchStateError("safe metadata projection must cover the entire original history")
    for original in metadata["families"]:
        row = families[(original["id"],)]
        _text(row["mechanism"], "reviewed family mechanism")
        spec = _json(original["spec"])
        if type(spec) is not dict or type(row["spec"]) is not dict:
            raise ResearchStateError("safe metadata family specification is unreadable")
        expected = {k: v for k, v in spec.items() if k in _SPEC_KEYS}
        if (set(row["spec"]) != set(expected)
                or any(_canonical(row["spec"][k]) != _canonical(v) for k, v in expected.items() if k != "mechanism")):
            raise ResearchStateError("safe projection changed family lineage or execution controls")
        if "mechanism" in expected:
            _text(row["spec"]["mechanism"], "reviewed specification mechanism")
    for original in metadata["operators"]:
        row = operators[(original["family"],)]
        _text(row["mechanism"], "reviewed operator mechanism")
        if (row["structure"] != original["structure"]
                or _canonical(row["roots"]) != _canonical(_json(original["roots"]))
                or row["structure"] not in set(cards.STRUCTURE_FAMILIES) | _LEGACY_OPERATOR_STRUCTURES):
            raise ResearchStateError("safe projection changed or cannot identify original operator controls")
    for original in metadata["versions"]:
        row = params[(original["family"], original["n"])]
        if (type(row["n"]) is not int or row["sha"] != original["sha"]
                or _canonical(row["params"]) != _canonical(_json(original["params"]))):
            raise ResearchStateError("safe projection changed original program parameters or identity")
    family_map = {row["id"]: row for row in metadata["families"]}
    for original in metadata["cards"]:
        old, new = _json(original["card"]), projected_cards[(original["family"],)]["card"]
        fields = {"hypothesis", "mechanism_class", "inputs", "holding", "cost", "comparison", "ablation", "falsification", "rebirth"}
        if (type(old) is not dict or type(new) is not dict or set(old) != set(new)
                or set(old) - fields or not {"hypothesis", "mechanism_class", "inputs", "holding", "cost", "comparison", "ablation", "falsification"} <= set(old)):
            raise ResearchStateError("safe card projection has missing or unknown fields")
        if any(_canonical(new[k]) != _canonical(old[k]) for k in ("mechanism_class", "inputs", "holding", "ablation", "comparison")):
            raise ResearchStateError("safe projection changed original card controls")
        for name in ("hypothesis", "comparison", "falsification"):
            _text(new[name], "reviewed card description")
        if (type(old["cost"]) is not dict or type(new["cost"]) is not dict
                or set(old["cost"]) != {"hurdle", "why"} or set(new["cost"]) != {"hurdle", "why"}
                or _canonical(new["cost"]["hurdle"]) != _canonical(old["cost"]["hurdle"])):
            raise ResearchStateError("safe projection changed original card cost controls")
        _text(new["cost"]["why"], "reviewed card cost description")
        if "rebirth" in old:
            if (type(old["rebirth"]) is not dict or type(new["rebirth"]) is not dict
                    or set(old["rebirth"]) != {"row", "different", "evidence"}
                    or set(new["rebirth"]) != set(old["rebirth"]) or old["rebirth"]["row"] != new["rebirth"]["row"]):
                raise ResearchStateError("safe projection changed original rebirth identity")
            for name in ("different", "evidence"):
                _text(new["rebirth"][name], "reviewed rebirth description")
        family = family_map.get(original["family"])
        if (family is None or original["sha"] != cards.card_sha(old)
                or _json(original["key"]) != cards.key_of(old, family["structure"])
                or old["mechanism_class"] not in cards.MECHANISM_CLASSES
                or old["holding"] not in cards.HOLDING or type(old["inputs"]) is not list
                or any(v not in cards.INPUTS for v in old["inputs"])):
            raise ResearchStateError("original card identity or controlled cell is unreadable")
    return {"families": {k[0]: v for k, v in families.items()},
            "operators": {k[0]: v for k, v in operators.items()},
            "cards": {k[0]: v["card"] for k, v in projected_cards.items()}}


def _metadata(connection):
    families = [{k: row[k] for k in ("id", "lineage", "parent", "mechanism", "structure", "roots", "spec")}
                for row in _rows(connection, "families")]
    versions = [{k: row[k] for k in ("family", "n", "sha", "params")} for row in _rows(connection, "versions")]
    family_ids = {row["id"] for row in families}
    operators = [{k: row[k] for k in ("family", "mechanism", "structure", "roots")}
                 for row in _rows(connection, "graveyard") if row["family"] not in family_ids]
    return {"families": families, "versions": versions, "cards": _rows(connection, "family_cards"), "operators": operators}


@dataclass(frozen=True)
class CaptureSelection:
    """Explicit artifact bytes to capture; this grants no export approval.

    The coherent database always retains every lineage, trial, look and failure.
    Only matching program bytes and identified Train receipts are selected.
    """
    program_sha256s: tuple[str, ...]
    train_run_ids: tuple[str, ...]

    def __post_init__(self):
        if (not isinstance(self.program_sha256s, tuple)
                or any(not isinstance(value, str) or not _SHA.fullmatch(value) for value in self.program_sha256s)
                or len(set(self.program_sha256s)) != len(self.program_sha256s)):
            raise ResearchStateError("capture selection needs distinct exact program SHA256 values")
        if (not isinstance(self.train_run_ids, tuple)
                or any(not isinstance(value, str) or not value or value != value.strip() for value in self.train_run_ids)
                or len(set(self.train_run_ids)) != len(self.train_run_ids)):
            raise ResearchStateError("capture selection needs distinct exact Train run identities")


def capture_snapshot(source_root, archive_root, *, snapshot_id: str, original_evaluator,
                     selection: CaptureSelection | None = None) -> dict:
    """Online SQLite backup and hash manifest; raw evidence is never put in a controller mount.

    The caller must keep archive_root host-only. No source file or database is mutated.
    By default every referenced artifact is captured. Explicit selection captures
    only the requested development bytes; it never subsets or edits database history.
    A racing unavailable/pruned selected artifact aborts capture rather than producing
    a false complete manifest. Owed failure reservations are always captured.
    """
    _name(snapshot_id, "snapshot ID")
    if selection is not None and not isinstance(selection, CaptureSelection):
        raise ResearchStateError("explicit typed capture selection required")
    original = _identity(original_evaluator)
    source, archive = Path(source_root), Path(archive_root)
    _disjoint(source, archive)
    if archive.exists():
        raise ResearchStateError("raw snapshot destination already exists")
    archive.mkdir(mode=0o700)
    try:
        _private(archive)
        owed = _read_file(source, _OWED_BARS) if (source / _OWED_BARS).exists() else None
        with closing(_connect(source / DB_NAME)) as origin, closing(sqlite3.connect(archive / DB_NAME)) as target:
            origin.backup(target)
            target.execute("PRAGMA journal_mode=DELETE")
        os.chmod(archive / DB_NAME, 0o600)
        artifacts = {}
        if owed is not None:
            _write_file(archive, _OWED_BARS, owed)
            artifacts[_OWED_BARS] = {"sha256": _digest(owed), "kind": "failure-reservations"}
        with closing(_connect(archive / DB_NAME)) as database:
            if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ResearchStateError("source database failed integrity check")
            previous = next((r["value"] for r in _rows(database, "kv") if r["key"] == "research_evaluator"), None)
            recorded = _identity(_json(previous)) if previous is not None else None
            if recorded != original:
                raise ResearchStateError("declared source evaluator differs from its authoritative snapshot")
            versions, runs = _rows(database, "versions"), _rows(database, "runs")
            if selection is not None:
                if set(selection.program_sha256s) - {row["sha"] for row in versions}:
                    raise ResearchStateError("selected program is absent from the coherent snapshot")
                by_run = {row["run_id"]: row for row in runs}
                for identity in selection.train_run_ids:
                    row = by_run.get(identity)
                    if row is None or row["window"] != "train" or row["purpose"] not in _TRAIN_PURPOSES:
                        raise ResearchStateError("capture selection cannot expose non-Train or unknown-purpose results")
                    if row["path"] is None:
                        raise ResearchStateError("selected Train artifact has been pruned")
            for row in versions:
                if selection is not None and row["sha"] not in selection.program_sha256s:
                    continue
                _name(row["family"], "family artifact directory")
                body = _read_file(source, row["path"], PROGRAMS_DIR)
                if _digest(body) != row["sha"]:
                    raise ResearchStateError("program bytes differ from the authoritative version SHA")
                artifacts[row["path"]] = {"sha256": _digest(body), "kind": "program"}
                if not (archive / row["path"]).exists():
                    _write_file(archive, row["path"], body)
            for row in runs:
                if selection is not None and row["run_id"] not in selection.train_run_ids:
                    continue
                if row["path"] is None:
                    continue
                body = _read_file(source, row["path"], RUNS_DIR)
                artifacts[row["path"]] = {"sha256": _digest(body), "kind": "run", "run_id": row["run_id"],
                                           "window": row["window"], "purpose": row["purpose"]}
                if not (archive / row["path"]).exists():
                    _write_file(archive, row["path"], body)
            metadata = _value_sha(_metadata(database))
        for path, record in artifacts.items():
            if _digest(_read_file(source, path)) != record["sha256"]:
                raise ResearchStateError("source artifacts changed after coherent SQLite backup")
        if (source / _OWED_BARS).exists() != (owed is not None):
            raise ResearchStateError("source failure reservations changed during coherent capture")
        manifest = {"schema": 1, "snapshot_id": snapshot_id, "captured_at": time.time(),
                    "source_root": str(source.resolve()),
                    "database_sha256": _digest((archive / DB_NAME).read_bytes()), "metadata_sha256": metadata,
                    "original_evaluator": original, "artifacts": artifacts, "host_only": True}
        if selection is not None:
            manifest["artifact_selection"] = asdict(selection)
        _write_file(archive, MANIFEST, (_canonical(manifest) + "\n").encode())
        return {**manifest, "manifest_sha256": _digest((archive / MANIFEST).read_bytes())}
    except BaseException:
        shutil.rmtree(archive)
        raise


def _validated_snapshot(snapshot, approval):
    _private(snapshot)
    body = _read_file(snapshot, MANIFEST)
    manifest = _json(body)
    if (not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("host_only") is not True
            or manifest.get("snapshot_id") != approval.snapshot_id or _digest(body) != approval.manifest_sha256
            or manifest.get("metadata_sha256") != approval.metadata_sha256):
        raise ResearchStateError("snapshot/export approval identity mismatch")
    if _digest(_read_file(snapshot, DB_NAME)) != manifest["database_sha256"]:
        raise ResearchStateError("coherent snapshot database changed")
    for path, record in manifest["artifacts"].items():
        if _digest(_read_file(snapshot, path)) != record["sha256"]:
            raise ResearchStateError("snapshot artifact hash changed")
    return manifest


def _insert(connection, table, row):
    columns = list(row)
    connection.execute(f'INSERT INTO "{table}" ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',
                       [row[k] for k in columns])


def _seal(connection, kind, identity, evidence):
    _insert(connection, "research_baseline", {"kind": kind, "identity": identity, "payload": _canonical(evidence)})


def _verdict(source):
    if not isinstance(source, dict):
        return None
    line, version = source.get("validation_line"), source.get("validation_version")
    if (isinstance(line, dict) and isinstance(line.get("passed"), bool)
            and isinstance(version, int) and not isinstance(version, bool) and version > 0):
        return {"version": version, "passed": line["passed"]}
    return None


def _safe_failure_state(source, original):
    if not isinstance(source, dict):
        raise ResearchStateError("family state is unreadable; its failure inheritance is unknown")
    out = {"gate_hold": bool(source.get("gate_hold") or source.get("gate_ready") or source.get("look_inflight")),
           "gate_ready": False, "train_candidates": [], "robustness": {},
           "train_passed": {}, "incubator_reviews": {}, "validation_verdicts": {}, "isolation_no_live_authority": True}
    records = source.get("validation_verdicts")
    if records is not None and not isinstance(records, dict):
        raise ResearchStateError("historical validation verdicts are unreadable")
    for n, row in (records or {}).items():
        if not str(n).isdigit() or not isinstance(row, dict) or not isinstance(row.get("passed"), bool):
            raise ResearchStateError("historical validation verdict is unreadable")
        out["validation_verdicts"][str(n)] = {"passed": row["passed"], "at": row.get("at"),
                                             "evaluator": _identity(row.get("evaluator")), "historical": True}
    current = _verdict(source)
    if current is not None and str(current["version"]) not in out["validation_verdicts"]:
        out["validation_verdicts"][str(current["version"])] = {"passed": current["passed"], "at": None,
                                                             "evaluator": original, "historical": True}
    old = _verdict(source.get("previous_evaluator_selection"))
    if old is not None:
        out["previous_evaluator_selection"] = {"validation_version": old["version"],
                                               "validation_line": {"passed": old["passed"]}}
    inflight = source.get("look_inflight")
    if inflight is not None:
        if not isinstance(inflight, dict) or not isinstance(inflight.get("sha"), str) or not inflight["sha"]:
            raise ResearchStateError("an unresolved sealed look has no reliable identity")
        out["look_inflight"] = {"sha": inflight["sha"], "isolation_reserved": True}
        if isinstance(inflight.get("n"), int) and not isinstance(inflight["n"], bool):
            out["look_inflight"]["n"] = inflight["n"]
    bars = source.get("incubator_barred")
    from .incubator import family_bar, adoption_bars
    if family_bar(source) is not None:
        # Preserve fail-closed semantics, without its unreadable raw payload.
        out["incubator_barred"] = "historical bar evidence unreadable; all programs remain barred"
    else:
        out["incubator_barred"] = {sha: {"why": "historical program failure remains in force",
                                         "source_sha256": _value_sha(value)} for sha, value in (bars or {}).items()}
        reviews = source.get("incubator_reviews")
        if reviews is not None and not isinstance(reviews, dict):
            raise ResearchStateError("historical program reviews are unreadable")
        for sha, why in adoption_bars(source).items():
            out["incubator_barred"][sha] = {"why": "historical program failure remains in force",
                                            "source_sha256": _value_sha(why)}
    mechanism = source.get("mechanism")
    if isinstance(mechanism, dict):
        failures = {key: mechanism[key] for key in ("failed", "untestable") if key in mechanism}
        if any(not isinstance(values, list) or any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in values)
               for values in failures.values()):
            raise ResearchStateError("historical mechanism failure identities are unreadable")
        out["mechanism"] = failures
    for key in ("extension_versions", "span_trials"):
        if key in source:
            value = source[key]
            if key == "extension_versions" and (not isinstance(value, list) or any(
                    isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in value)):
                raise ResearchStateError("extension reservation history is unreadable")
            if key == "span_trials" and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ResearchStateError("search trial baseline is unreadable")
            out[key] = value
    if source.get("extension_hold") is not None:
        hold = source["extension_hold"]
        if not isinstance(hold, dict) or not isinstance(hold.get("version"), int):
            raise ResearchStateError("extension reservation is unreadable")
        out["extension_hold"] = {"version": hold["version"], "isolation_reserved": True}
    return out


def _historical_bars(connection, snapshot, manifest):
    """Read incumbent backfill semantics without replaying any source mutation or raw payload."""
    from .gate import run_sha
    from .incubator import _FAILS, _THIRD_UNCLEAR
    families = {row["id"] for row in _rows(connection, "families")}
    versions = {(row["family"], row["n"]): run_sha({"sha": row["sha"], "params": _json(row["params"])})
                for row in _rows(connection, "versions")}
    bars = {family: {} for family in families}

    def record(family, sha, evidence):
        if family in bars and bars[family] is not None:
            bars[family][sha] = {"why": "historical review/audit failure remains in force", "source_sha256": _value_sha(evidence)}

    for event in _rows(connection, "events"):
        if event["kind"] != "swarm.gate" or event["family"] not in families:
            continue
        payload = _json(event["payload"])
        if not isinstance(payload, dict):
            continue
        action, family, n = payload.get("action"), event["family"], payload.get("version")
        if action in _FAILS and payload.get("verdict") == "fail":
            sha = versions.get((family, n)) if type(n) is int else None
            if sha is None:
                bars[family] = None  # an authoritative failure cannot be resolved to its original program
            else:
                record(family, sha, event)
        elif action == "incubator_bar_error" and isinstance(payload.get("sha"), str):
            matches = [(fid, sha) for (fid, version), sha in versions.items()
                       if fid == family and (type(n) is not int or n == version) and sha.startswith(payload["sha"])]
            if not matches:
                bars[family] = None
            for fid, sha in matches:
                record(fid, sha, event)
    for row in _rows(connection, "kv"):
        stage, _, rest = row["key"].partition(":")
        count = _json(row["value"])
        if stage not in _THIRD_UNCLEAR or type(count) is not int or count < 3:
            continue
        parts = rest.split(":")
        if stage.endswith("review_attempt") and len(parts) == 3 and parts[2].isdigit():
            sha = versions.get((parts[1], int(parts[2])))
            if sha is not None:
                record(parts[1], sha, row)
            elif parts[1] in families:
                bars[parts[1]] = None
        elif stage.endswith("audit_attempt") and len(parts) == 2:
            for (family, _), sha in versions.items():
                if sha == parts[1]:
                    record(family, sha, row)
    if _OWED_BARS in manifest["artifacts"]:
        try:
            value = _json(_read_file(snapshot, _OWED_BARS))
            owed = value.get("bars") if isinstance(value, dict) else None
            if not isinstance(owed, list) or any(not isinstance(row, dict) or row.get("family") not in families
                                                or not isinstance(row.get("sha"), str) or not _SHA.fullmatch(row["sha"]) for row in owed):
                raise ResearchStateError("owed failure evidence unreadable")
        except ResearchStateError:
            return {family: None for family in families}
        for row in owed:
            record(row["family"], row["sha"], row)
    return bars


def _retirement_reason(family, graveyard):
    """Keep the stock categorical retirement/rebirth judgment, never its original figures."""
    from .architect import tag_of, SELF_REFUTED, IDLE_MARK
    from .mechanism import MARK
    tag = tag_of(graveyard or {}, family)
    labels = {"MECHANISM": MARK, "SELF-REFUTED": SELF_REFUTED, "DIAGNOSED": "the diagnostician",
              "TRIALS": "trial-adjusted", "STALL": "no validation improvement", "IDLE": IDLE_MARK,
              "OPERATOR-RETIRED": "operator", "REFUTED": "refuted"}
    prefix = labels.get(tag, f"Idle verdict {tag}")
    return f"{prefix}: historical retirement remains in force; original evidence retained in host-only audit"


def _seal_card_matching(target, source, families):
    """Bind original card inheritance and controlled word-derived inputs before redaction."""
    from . import cards
    rows = _rows(source, "family_cards")
    own = {row["family"]: row for row in rows}
    by_sha = {}
    for row in sorted(rows, key=lambda row: (row["at"], row["family"])):
        by_sha.setdefault(row["sha"], row)
    for family in families:
        spec = _json(family["spec"])
        row = own.get(family["id"]) or by_sha.get(spec.get("card_sha"))
        if row:
            card = _json(row["card"])
            keys, _ = cards.match_keys(card, family["structure"], family["mechanism"], spec.get("dte"))
            cell_key = cards.key_of(card, family["structure"])
        else:
            keys = None
            cell_key = cards.infer_key(family["mechanism"], family["structure"], spec.get("dte"))
        for key in ([cell_key] if cell_key else []) + (keys or []):
            if (key["class"] not in cards.MECHANISM_CLASSES or key["holding"] not in cards.HOLDING
                    or key["family"] not in set(cards.STRUCTURE_FAMILIES.values())
                    or any(item not in cards.INPUTS for item in key["inputs"] or [])):
                raise ResearchStateError("original family card matching authority is unreadable")
        _seal(target, "card_matching", family["id"], {
            "source_card_sha": row["sha"] if row else None, "keys": keys, "cell_key": cell_key,
            "source_family_sha256": _value_sha(family), "source_card_row_sha256": _value_sha(row) if row else None})


def _seal_rebirth_failure(target, source, original, family):
    """Derive original failure matching on the host; export only controlled identities.

    The original prose comparison needed to authorize a rebirth remains host-only,
    so a matched historical claim cannot be authorized by its replacement text.
    """
    from . import cards
    from .architect import tag_of
    tag = tag_of(original, family)
    if tag not in cards.MECHANISM_VERDICTS:
        return
    own = next((row for row in _rows(source, "family_cards") if row["family"] == original["family"]), None)
    if own:
        key = {**_json(own["key"]), "inputs": cards.match_inputs(_json(own["card"]), original["mechanism"])}
    else:
        dte = _json(family["spec"]).get("dte") if family else None
        key = cards.infer_key(original["mechanism"], original["structure"], dte)
    inputs = sorted(key["inputs"]) if key and key.get("inputs") is not None else cards.infer_inputs(original["mechanism"])
    structure_families = set(cards.STRUCTURE_FAMILIES.values())
    if family is None and original["family"].startswith("op-"):
        structure_families |= _LEGACY_OPERATOR_STRUCTURES
    if (any(item not in cards.INPUTS for item in inputs)
            or (key is not None and (set(key) != {"class", "inputs", "family", "holding"}
                or key["class"] not in cards.MECHANISM_CLASSES or key["holding"] not in cards.HOLDING
                or key["family"] not in structure_families))):
        raise ResearchStateError("original failure matching authority is unreadable")
    _seal(target, "rebirth_failure", original["family"], {
        "row": original["family"], "at": original["at"], "tag": tag, "key": key,
        "inputs": inputs, "legacy": own is None, "structure": original["structure"],
        "structure_family": cards.structure_family(original["structure"]),
        "source_card_sha": own["sha"] if own else None,
        "lineage": family["lineage"] if family else None, "source_sha256": _value_sha(original),
        "original_prose_host_only": True})


def _assert_failure_floor(state, prior, *, guarded_verdicts=None):
    if (not isinstance(state, dict) or state.get("isolation_no_live_authority") is not True
            or (prior.get("gate_hold") and state.get("gate_hold") is not True)):
        raise ResearchStateError("isolated family lost its research-only gate seal")
    for key in ("look_inflight", "extension_hold"):
        if prior.get(key) and state.get(key) != prior[key]:
            raise ResearchStateError("historical evaluation reservation was released")
    verdicts = state.get("validation_verdicts") or {}
    historical = prior.get("validation_verdicts", {})
    if not isinstance(verdicts, dict) or (verdicts != historical and verdicts != guarded_verdicts):
        raise ResearchStateError("historical Validation verdict was erased or reversed")
    bars = prior.get("incubator_barred")
    current = state.get("incubator_barred")
    if (isinstance(bars, dict) and (not isinstance(current, dict) or any(not current.get(sha) for sha in bars))) or (
            not isinstance(bars, dict) and current != bars):
        raise ResearchStateError("historical program failure bar was removed")
    mechanism = state.get("mechanism") or {}
    if not isinstance(mechanism, dict) or any(not isinstance(mechanism.get(k), list) or not set(v) <= set(mechanism[k])
                                            for k, v in prior.get("mechanism", {}).items()):
        raise ResearchStateError("historical mechanism failure inheritance was erased")
    if not set(prior.get("extension_versions", [])) <= set(state.get("extension_versions") or []):
        raise ResearchStateError("historical extension trial reservation was erased")
    if state.get("span_trials", 0) < prior.get("span_trials", 0):
        raise ResearchStateError("historical span trial baseline decreased")


_BASELINE_SQL = """
CREATE TABLE research_baseline (kind TEXT NOT NULL, identity TEXT NOT NULL, payload TEXT NOT NULL,
                               PRIMARY KEY(kind, identity));
CREATE TRIGGER research_baseline_no_update BEFORE UPDATE ON research_baseline
  BEGIN SELECT RAISE(ABORT, 'research baseline is immutable'); END;
CREATE TRIGGER research_baseline_no_delete BEFORE DELETE ON research_baseline
  BEGIN SELECT RAISE(ABORT, 'research baseline is immutable'); END;
"""


def _protect(connection):
    for table in ("boxes", "forward"):
        for action in ("INSERT", "UPDATE", "DELETE"):
            connection.execute(f"CREATE TRIGGER isolation_{table}_{action.lower()} BEFORE {action} ON {table} "
                               "BEGIN SELECT RAISE(ABORT, 'operational and financial state is excluded'); END")
    for action in ("INSERT", "UPDATE"):
        connection.execute(f"CREATE TRIGGER isolation_family_{action.lower()} BEFORE {action} ON families "
                           "WHEN NEW.band NOT IN ('gym','retired') "
                           "BEGIN SELECT RAISE(ABORT, 'isolated research has no financial band authority'); END")
    connection.execute("CREATE TRIGGER isolation_retired BEFORE UPDATE ON families "
                       "WHEN OLD.retired_at IS NOT NULL AND NEW.retired_at IS NULL "
                       "BEGIN SELECT RAISE(ABORT, 'historical retirement is retained'); END")
    for action in ("INSERT", "UPDATE", "DELETE"):
        connection.execute(f"CREATE TRIGGER isolation_looks_{action.lower()} BEFORE {action} ON looks "
                           "BEGIN SELECT RAISE(ABORT, 'historical sealed look reservations are immutable'); END")
    connection.execute("CREATE TRIGGER research_baseline_no_insert BEFORE INSERT ON research_baseline "
                       "BEGIN SELECT RAISE(ABORT, 'research baseline is immutable'); END")


def _guards_digest(connection):
    return _value_sha([dict(row) for row in connection.execute(
        "SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name")])


_VALIDATION_EVENT = "swarm.isolated_validation"


class _ReadView:
    def __init__(self, connection):
        self.connection = connection

    def _all(self, sql, params=()):
        return [dict(row) for row in self.connection.execute(sql, params)]

    def _one(self, sql, params=()):
        row = self.connection.execute(sql, params).fetchone()
        return dict(row) if row else None


def _validation_receipt(view, root, evaluator, family, version, *, identity=None, result=None, adapter_state=None):
    """Link a judgment to original current-artifact Validation bytes, never a mutable passed flag."""
    from .research_adapters import _load, ResearchGymPool
    row = view._one("SELECT * FROM versions WHERE family=? AND n=?", (family, version))
    if row is None:
        raise ResearchStateError("Validation receipt has no research version")
    code = _read_file(Path(root), row["path"], PROGRAMS_DIR).decode()
    state = _load(view) if adapter_state is None else adapter_state
    candidates = state.items() if identity is None else ((identity, state[identity]),) if identity in state else ()
    for key, item in candidates:
        if not key.startswith("gym:") or (identity is not None and key != identity) or item["result"] is None:
            continue
        request = item["request"]
        job = request.get("job") or {}
        if (job.get("family") != family or job.get("version") != version or job.get("window") != "validation"
                or job.get("purpose") != "validation" or job.get("stress") != 1
                or job.get("gate") or job.get("code") != code or job.get("params") != _json(row["params"])
                or (request.get("gym_image"), request.get("gym_bundle"), request.get("gym_execution")) !=
                (evaluator.image, evaluator.bundle, evaluator.execution)):
            continue
        actual = ResearchGymPool._result(item["result"], request)
        if actual["trials"] <= 0:
            continue
        if result is not None and any(result.get(k) != actual.get(k) for k in (
                "run_id", "status", "window", "roots", "stress", "summary", "stress_1.5", "gym_image", "gym_bundle", "gym_execution")):
            continue
        return key, item, actual
    raise ResearchStateError("Validation judgment has no original actual current-artifact receipt")


def guard_tournament(tournament, expected_evaluator: ArtifactIdentity):
    """Journal the actual nonblocking stock judge, with its original DSR context.

    Install immediately after construction; both synchronous and late/recovered
    Validation calls then use this same judge. No provider or IPC operation runs
    inside this transaction, and no score or evaluator rule is replaced.
    """
    from .tournament import Tournament
    if not isinstance(tournament, Tournament) or not isinstance(expected_evaluator, ArtifactIdentity):
        raise ResearchStateError("guard requires the stock tournament and actual artifact identity")
    prior = getattr(tournament, "_isolated_judge_identity", None)
    if prior is not None:
        if prior != expected_evaluator:
            raise ResearchStateError("guarded tournament evaluator changed")
        return tournament
    original = tournament.judge
    if getattr(original, "__func__", None) is not Tournament.judge:
        raise ResearchStateError("guard requires the unchanged stock Validation judge")
    store = tournament.store

    def judge(family, version, result, *, record=True):
        with store.atomic():
            if store.get("research_evaluator") != asdict(expected_evaluator):
                raise ResearchStateError("guarded Validation evaluator authority changed")
            identity, item, actual = _validation_receipt(store, store.root, expected_evaluator,
                                                         family, version, result=result)
            verdict = original(family, version, result, record=record)
            if verdict is not None:
                state = store.family(family)["state"]
                count, sharpes = store.lineage_validated(family)
                store.event(_VALIDATION_EVENT, family, {"action": "judged", "identity": identity, "request_sha": item["sha"],
                    "family": family, "version": version, "evaluator": asdict(expected_evaluator),
                    "verdict": state["validation_verdicts"][str(version)], "records": state["validation_verdicts"],
                    "line": state["validation_line"], "context": {"validated_versions": count,
                        "version_sharpes": sharpes, "lineage_trials": store.lineage_trials(family)}})
            return verdict

    tournament.judge = judge
    tournament._isolated_judge_identity = expected_evaluator
    return tournament


def _assert_verdict_history(connection, root, evaluator, adapter_state):
    """Replay immutable current judgments while keeping imported failure history in its baseline."""
    from . import evidence
    from .researcher import record_verdict
    from .store import code_sha, dumps
    histories = {row["identity"]: _json(row["payload"])["failure_state"]["validation_verdicts"]
                 for row in _rows(connection, "research_baseline") if row["kind"] == "family"}
    latest = {}
    view = _ReadView(connection)
    try:
        for event in view._all("SELECT family,payload FROM events WHERE kind=? ORDER BY seq", (_VALIDATION_EVENT,)):
            row = _json(event["payload"])
            if (set(row) != {"action", "identity", "request_sha", "family", "version", "evaluator", "verdict", "records", "line", "context"}
                    or row["action"] != "judged" or row["family"] != event["family"]
                    or type(row["version"]) is not int or row["version"] < 1 or row["evaluator"] != asdict(evaluator)):
                raise ValueError("unscoped Validation journal")
            identity, item, actual = _validation_receipt(view, root, evaluator, row["family"], row["version"],
                                                        identity=row["identity"], adapter_state=adapter_state)
            if row["request_sha"] != item["sha"]:
                raise ValueError("Validation journal changed original request")
            worker_id = actual["run_id"]
            alias = code_sha(dumps({"worker_run_id": worker_id, "family": row["family"], "evaluator": (evaluator.image, evaluator.bundle)}))
            names = (worker_id, f"{worker_id}-{row['family']}"[:64], f"{worker_id[:31]}-{alias[:32]}")
            run = next((candidate for name in names if (candidate := view._one("SELECT * FROM runs WHERE run_id=?", (name,)))
                        and candidate["family"] == row["family"] and candidate["version"] == row["version"]
                        and candidate["window"] == "validation" and candidate["purpose"] == "validation" and candidate["stress"] == 1
                        and candidate["trials"] >= item["counts_before"]["primary"] + actual["trials"]
                        and _json(candidate["summary"]) == {**actual["summary"], "gym_image": evaluator.image, "gym_bundle": evaluator.bundle}), None)
            if run is None:
                raise ValueError("Validation journal lost original actual trials or figures")
            context, verdict = row["context"], row["verdict"]
            if (set(context) != {"validated_versions", "version_sharpes", "lineage_trials"}
                    or type(context["validated_versions"]) is not int or context["validated_versions"] < 1
                    or type(context["lineage_trials"]) is not int or context["lineage_trials"] < 0
                    or not isinstance(context["version_sharpes"], list)
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in context["version_sharpes"])
                    or set(verdict) != {"passed", "at", "evaluator"} or type(verdict["passed"]) is not bool
                    or verdict["evaluator"] != asdict(evaluator) or not isinstance(verdict["at"], str)):
                raise ValueError("Validation journal lost original stock judgment context")
            line = evidence.validation_line(actual, evidence.stressed_of(actual), **context)
            if row["line"] != line or verdict["passed"] != line["passed"]:
                raise ValueError("Validation journal contradicts actual stock judgment")
            previous = histories.get(row["family"], {})
            expected = record_verdict({"validation_verdicts": previous}, row["version"], verdict["passed"],
                                      evaluator=asdict(evaluator), at=verdict["at"])
            if row["records"] != expected:
                raise ValueError("Validation journal erased historical latest verdicts outside stock retention")
            # SwarmStore writes sorted JSON between judgments. Preserve that
            # ordering for stock record_verdict's equal-time retention ties.
            histories[row["family"]] = _json(_canonical(expected))
            latest[row["family"]] = expected
        for family, records in latest.items():
            row = view._one("SELECT state FROM families WHERE id=?", (family,))
            if row is None or _json(row["state"]).get("validation_verdicts") != records:
                raise ValueError("latest Validation verdict differs from original guarded judgment")
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise ResearchStateError("private Validation judgment provenance changed") from exc
    return latest


def _assert_private_reporting(connection):
    """New local reporting is derived from controller receipts, never imported vendor state."""
    from .research_adapters import _load

    class View:
        def _all(self, sql, params=()):
            return [dict(row) for row in connection.execute(sql, params)]

        def _one(self, sql, params=()):
            row = connection.execute(sql, params).fetchone()
            return dict(row) if row else None

    try:
        state = _load(View())
        expected = {}
        for identity, item in state.items():
            result = item["result"]
            if not identity.startswith("model:") or result is None:
                continue
            cost = Decimal(result["cost_usd"])
            day = dt.date.fromisoformat(result["accrued_day"])
            if not cost.is_finite() or not 0 <= cost <= 25 or result["accrued_day"] != day.isoformat():
                raise ValueError("invalid model report")
            if cost:
                expected[identity] = (cost, dt.datetime.combine(day, dt.time(), dt.timezone.utc).timestamp())
        observed = {}
        for row in _rows(connection, "spend"):
            detail = _json(row["detail"])
            identity = detail["research_request"]
            cost, epoch = expected[identity]
            if (identity in observed or row["kind"] != "sail_model" or row["epoch"] != epoch
                    or row["at"] != dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat().replace("+00:00", "Z")
                    or Decimal(str(row["usd"])) != cost or detail.get("accrual_granularity") != "UTC day"
                    or detail.get("vendor_actual") is not True
                    or (row["family"] is not None and connection.execute("SELECT 1 FROM families WHERE id=?", (row["family"],)).fetchone() is None)):
                raise ValueError("unscoped cost report")
            observed[identity] = True
        if set(observed) != set(expected):
            raise ValueError("cost report disappeared")
        for row in _rows(connection, "model_costs"):
            item = state.get("model:" + row["request_key"])
            if (item is None or not 0 <= row["booked_usd"] <= 25 or row["settled"] not in (0, 1)
                    or (row["settled"] and (item["result"] is None or Decimal(str(row["booked_usd"])) != Decimal(item["result"]["cost_usd"])))):
                raise ValueError("unscoped model cost")
        for row in _rows(connection, "convo"):
            if connection.execute("SELECT 1 FROM families WHERE id=?", (row["family"],)).fetchone() is None or not isinstance(_json(row["items"]), list):
                raise ValueError("unscoped new conversation")
            if row["pending"] is not None:
                _json(row["pending"])
    except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError) as exc:
        raise ResearchStateError("new private reporting does not reconcile to controller receipts") from exc
    return state


def import_snapshot(snapshot_root, fresh_root, *, runtime_scope: str, expected_evaluator: ArtifactIdentity,
                    artifact_root, approval: ExportApproval, metadata_projection: SafeMetadataProjection) -> dict:
    """Create a private fresh SwarmStore-compatible view; never overwrite or modify source/audit state."""
    _name(runtime_scope, "isolated runtime scope")
    if not isinstance(expected_evaluator, ArtifactIdentity) or not isinstance(approval, ExportApproval):
        raise ResearchStateError("actual artifact identity and explicit host export approval are required")
    actual = artifact_identity(expected_evaluator.image, artifact_root)
    if actual != expected_evaluator:
        raise ResearchStateError("requested evaluator does not match actual isolated artifact bytes")
    snapshot, fresh = Path(snapshot_root), Path(fresh_root)
    _disjoint(snapshot, fresh)
    manifest = _validated_snapshot(snapshot, approval)
    _disjoint(Path(manifest["source_root"]), snapshot, fresh)
    if fresh.exists():
        raise ResearchStateError("isolated working destination already exists")
    fresh.mkdir(mode=0o700)
    try:
        _private(fresh)
        (fresh / PROGRAMS_DIR).mkdir(mode=0o700)
        (fresh / RUNS_DIR).mkdir(mode=0o700)
        with closing(_connect(snapshot / DB_NAME)) as source, closing(sqlite3.connect(fresh / DB_NAME)) as target:
            target.row_factory = sqlite3.Row
            target.executescript(SCHEMA.replace("passed INTEGER NOT NULL", "passed INTEGER"))
            target.executescript(_BASELINE_SQL)
            target.execute("BEGIN IMMEDIATE")
            if _value_sha(_metadata(source)) != approval.metadata_sha256:
                raise ResearchStateError("approved development metadata changed")
            projected = _approved_projection(source, metadata_projection, approval)
            family_rows = _rows(source, "families")
            _seal_card_matching(target, source, family_rows)
            historical_bars = _historical_bars(source, snapshot, manifest)
            graveyards = {row["family"]: row for row in _rows(source, "graveyard")}
            versions, runs = _rows(source, "versions"), _rows(source, "runs")
            approved_programs = set(approval.program_sha256s)
            if approved_programs - {r["sha"] for r in versions}:
                raise ResearchStateError("approved program is absent from the coherent snapshot")
            approved_train = set(approval.train_run_ids)
            permitted = {r["run_id"] for r in runs if r["window"] == "train" and r["purpose"] in _TRAIN_PURPOSES}
            if approved_train - permitted:
                raise ResearchStateError("export approval cannot expose Validation, sealed, forward or unknown-purpose results")
            for original in family_rows:
                row = dict(original)
                for field in _COUNTERS:
                    if isinstance(row[field], bool) or not isinstance(row[field], int) or row[field] < 0:
                        raise ResearchStateError("authoritative family search counters are unreadable")
                spec, state = _json(row["spec"]), _json(row["state"])
                if not isinstance(spec, dict):
                    raise ResearchStateError("authoritative family specification is unreadable")
                safe = _safe_failure_state(state, manifest["original_evaluator"])
                extra = historical_bars[row["id"]]
                if extra is None:
                    safe["incubator_barred"] = "historical failure evidence unresolved; all programs remain barred"
                elif isinstance(safe["incubator_barred"], dict):
                    safe["incubator_barred"].update(extra)
                safe.update(evaluator=asdict(actual), evaluator_trials=row["trials"], dormant_cycles=0)
                reviewed = projected["families"][row["id"]]
                row.update(mechanism=reviewed["mechanism"], spec=_canonical(reviewed["spec"]), state=_canonical(safe),
                           band="retired" if row["retired_at"] else "gym", weight=None, best_train=None,
                           best_version=None, best_validation=None, validated_version=None, spent_usd=0,
                           stall=0, since_val_trials=0, since_val_revisions=0, origin="historical-research")
                if row["retire_reason"]:
                    row["retire_reason"] = _retirement_reason(original, graveyards.get(row["id"]))
                _insert(target, "families", row)
                _seal(target, "family", row["id"], {"id": row["id"], "lineage": row["lineage"], "parent": row["parent"],
                                                   **{k: row[k] for k in _COUNTERS}, "retired_at": row["retired_at"],
                                                   "retire_reason": row["retire_reason"], "spec": row["spec"],
                                                   "mechanism": row["mechanism"], "structure": row["structure"], "roots": row["roots"],
                                                   "failure_state": safe, "source_sha256": _value_sha(original)})
            for row in _rows(source, "lineage_links"):
                _insert(target, "lineage_links", row)
                _seal(target, "lineage_link", _canonical([row["a"], row["b"]]), row)
            copied = set()
            for original in versions:
                row = dict(original)
                _seal(target, "version", _canonical([row["family"], row["n"]]),
                      {k: row[k] for k in ("family", "n", "sha", "params")})
                row.update(author="historical-research", note="Source authorship and notes retained in host-only audit")
                if row["sha"] in approved_programs:
                    if row["path"] not in copied:
                        _write_file(fresh, row["path"], _read_file(snapshot, row["path"], PROGRAMS_DIR))
                        copied.add(row["path"])
                    sidecar = f'{PROGRAMS_DIR}/{row["family"]}/v{row["n"]}-{row["sha"][:12]}.json'
                    if sidecar not in copied:
                        _write_file(fresh, sidecar, row["params"].encode())
                        copied.add(sidecar)
                else:
                    row["path"] = f'{PROGRAMS_DIR}/{row["family"]}/unapproved-v{row["n"]}-{row["sha"][:12]}.py'
                _insert(target, "versions", row)
            for original in runs:
                row = dict(original)
                if not isinstance(row["trials"], int) or row["trials"] < 0:
                    raise ResearchStateError("authoritative run trial count is unreadable")
                _seal(target, "run", row["run_id"], {k: row[k] for k in (
                    "run_id", "family", "version", "window", "stress", "purpose", "at", "status", "program_years", "trials")})
                if row["run_id"] in approved_train:
                    if row["path"] is not None:
                        _write_file(fresh, row["path"], _read_file(snapshot, row["path"], RUNS_DIR))
                else:
                    row.update(summary=_canonical({"isolation_redacted": True, "source_sha256": _value_sha(original)}), path=None)
                _insert(target, "runs", row)
            for original in _rows(source, "looks"):
                row = dict(original)
                _seal(target, "look", str(row["seq"]), {k: row[k] for k in ("seq", "family", "lineage", "version", "run_sha", "at")})
                row.update(passed=None, p_value=None, detail=_canonical({"isolation_redacted": True,
                                                                       "source_sha256": _value_sha(original)}))
                _insert(target, "looks", row)
            for table in ("refusals", "look_holds", "notebook", "graveyard"):
                for original in _rows(source, table):
                    row = dict(original)
                    identity = str(row.get("seq", row.get("family")))
                    if table in ("refusals", "look_holds"):
                        row["stage"] = "historical"
                        row["reason"] = "Historical refusal/reservation remains in force; original reason retained in host-only audit"
                    elif table == "notebook":
                        row["text"] = "Historical notebook entry retained in host-only audit"
                    else:
                        family = next((f for f in family_rows if f["id"] == row["family"]), None)
                        if family is None and not row["family"].startswith("op-"):
                            raise ResearchStateError("graveyard evidence has no authoritative family")
                        metadata = family or row
                        reviewed = projected["families" if family else "operators"][row["family"]]
                        row.update(mechanism=reviewed["mechanism"], structure=metadata["structure"], roots=metadata["roots"],
                                   lesson=_retirement_reason(family, original), best="{}")
                        _seal_rebirth_failure(target, source, original, family)
                    _insert(target, table, row)
                    _seal(target, table, identity, {"row": row, "source_sha256": _value_sha(original)})
            from .cards import CARDS_SQL, card_sha
            for statement in CARDS_SQL:
                target.execute(statement)
            for original in _rows(source, "family_cards"):
                row = dict(original)
                card = projected["cards"][row["family"]]
                row.update(card=_canonical(card), sha=card_sha(card))
                _insert(target, "family_cards", row)
                _seal(target, "family_card", row["family"], {
                    "source_identity_sha": original["sha"], "source_card_sha256": _value_sha(_json(original["card"])),
                    "source_sha256": _value_sha(original), "projected_content_sha256": _value_sha(card),
                    "projected_row_sha256": _value_sha(row)})
            for original in _rows(source, "card_evidence"):
                row = dict(original)
                detail = _json(row["detail"])
                if not isinstance(detail, dict):
                    raise ResearchStateError("mechanism failure inheritance is unreadable")
                if row["kind"] != "mechanism_test":
                    row["kind"] = "historical-unclassified"
                if row["verdict"] == "passed":
                    row["verdict"] = "historical-passed"
                elif row["verdict"] not in {"failed", "untestable", "invalid_ablation"}:
                    row["verdict"] = "historical-unclassified"
                row["detail"] = _canonical({"isolation_redacted": True, "source_sha256": _value_sha(original),
                                             **{k: detail[k] for k in ("below_base", "blind", "exposed")
                                                if isinstance(detail.get(k), bool)}})
                _insert(target, "card_evidence", row)
                _seal(target, "card_evidence", str(row["seq"]), {k: row[k] for k in (
                    "family", "card_sha", "version", "kind", "verdict", "detail")})
            # Source events are not replayable authority in this isolated working database.
            # Extract only safe version verdicts from adoption archives, never raw payloads.
            for event in _rows(source, "events"):
                payload = _json(event["payload"])
                if isinstance(payload, dict) and payload.get("action") == "evaluator_adopted":
                    verdict = _verdict(payload.get("_previous_selection"))
                    if verdict is not None:
                        _seal(target, "validation_archive", str(event["seq"]),
                              {"family": event["family"], "at": event["at"], **verdict,
                               "source_sha256": _value_sha(event)})
            receipt = {"schema": 1, "snapshot_id": manifest["snapshot_id"], "snapshot_manifest_sha256": approval.manifest_sha256,
                       "source_database_sha256": manifest["database_sha256"], "runtime_scope": runtime_scope,
                       "runtime_ownership_token": uuid.uuid4().hex, "original_evaluator": manifest["original_evaluator"],
                       "evaluator": asdict(actual), "export_review_sha256": _value_sha(asdict(approval)),
                       "source_metadata_sha256": approval.metadata_sha256,
                       "safe_metadata_sha256": approval.safe_metadata_sha256,
                       "research_only": True, "sealed_payloads_mounted": False, "financial_authority": False}
            _insert(target, "kv", {"key": "research_evaluator", "value": _canonical(asdict(actual))})
            _insert(target, "kv", {"key": "program_lineages_indexed", "value": "true"})
            _insert(target, "kv", {"key": IMPORT_KEY, "value": _canonical(receipt)})
            _seal(target, "import", "origin", receipt)
            _protect(target)
            guards = _guards_digest(target)
            target.commit()
        os.chmod(fresh / DB_NAME, 0o600)
        receipt["baseline_sha256"] = _baseline_digest(fresh / DB_NAME)
        receipt["guards_sha256"] = guards
        receipt["working_artifacts"] = {path: _digest(_read_file(fresh, path)) for path in sorted(copied)}
        receipt["prunable_train_artifacts"] = {row["run_id"]: {"path": row["path"], "sha256": _digest(_read_file(fresh, row["path"]))}
            for row in runs if row["run_id"] in approved_train and row["path"] is not None}
        _write_file(fresh, WORKING_MANIFEST, (_canonical(receipt) + "\n").encode())
        assert_isolated_state(fresh, runtime_scope=runtime_scope, expected_evaluator=actual, artifact_root=artifact_root)
        return receipt
    except BaseException:
        shutil.rmtree(fresh)
        raise


def _baseline_digest(database_path):
    with closing(_connect(database_path)) as connection:
        rows = [dict(r) for r in connection.execute("SELECT * FROM research_baseline ORDER BY kind, identity")]
        return _value_sha(rows)


def assert_isolated_state(root, *, runtime_scope: str, expected_evaluator: ArtifactIdentity, artifact_root) -> dict:
    """Fail closed before scheduling when provenance, artifact identity or historical walls changed."""
    root = Path(root)
    _private(root)
    if not isinstance(expected_evaluator, ArtifactIdentity) or artifact_identity(expected_evaluator.image, artifact_root) != expected_evaluator:
        raise ResearchStateError("controller evaluator does not match actual artifact bytes")
    receipt = _json(_read_file(root, WORKING_MANIFEST))
    if (receipt.get("runtime_scope") != runtime_scope or receipt.get("evaluator") != asdict(expected_evaluator)
            or receipt.get("research_only") is not True or receipt.get("financial_authority") is not False
            or receipt.get("sealed_payloads_mounted") is not False):
        raise ResearchStateError("working state has no matching isolated provenance")
    if _baseline_digest(root / DB_NAME) != receipt["baseline_sha256"]:
        raise ResearchStateError("immutable research baseline changed")
    for path, sha in receipt["working_artifacts"].items():
        if _digest(_read_file(root, path)) != sha:
            raise ResearchStateError("imported working artifact changed")
    with closing(_connect(root / DB_NAME)) as connection:
        if _guards_digest(connection) != receipt["guards_sha256"]:
            raise ResearchStateError("isolated SQL guards changed")
        for run_id, artifact in receipt["prunable_train_artifacts"].items():
            run = connection.execute("SELECT path FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None or (run["path"] is not None and (run["path"] != artifact["path"] or
                    _digest(_read_file(root, artifact["path"])) != artifact["sha256"])):
                raise ResearchStateError("approved Train artifact changed outside normal pruning")
        for table in ("boxes", "forward"):
            if _rows(connection, table):
                raise ResearchStateError("working state contains operational or financial records")
        values = {r["key"]: _json(r["value"]) for r in _rows(connection, "kv")}
        if set(values) - _RESEARCH_KV or not {"research_evaluator", "program_lineages_indexed", IMPORT_KEY} <= set(values):
            raise ResearchStateError("working state contains copied runtime or provider ownership")
        if values["research_evaluator"] != asdict(expected_evaluator):
            raise ResearchStateError("working evaluator authority changed")
        adapter_state = _assert_private_reporting(connection)
        guarded_verdicts = _assert_verdict_history(connection, root, expected_evaluator, adapter_state)
        rows = _rows(connection, "research_baseline")
        for baseline in rows:
            value = _json(baseline["payload"])
            kind = baseline["kind"]
            if kind == "import":
                if values[IMPORT_KEY] != value or any(receipt.get(k) != v for k, v in value.items()):
                    raise ResearchStateError("working origin receipt changed")
            elif kind == "family":
                row = connection.execute("SELECT * FROM families WHERE id=?", (value["id"],)).fetchone()
                if (row is None or row["lineage"] != value["lineage"] or row["parent"] != value["parent"]
                        or row["mechanism"] != value["mechanism"] or row["structure"] != value["structure"]
                        or (value["retired_at"] is not None and row["retired_at"] != value["retired_at"])
                        or (value["retired_at"] is not None and row["retire_reason"] != value["retire_reason"])
                        or (value["retired_at"] is not None and row["roots"] != value["roots"])
                        or row["band"] not in ("gym", "retired")
                        or any(type(row[k]) is not int or row[k] < value[k] for k in _COUNTERS)):
                    raise ResearchStateError("historical family identity, retirement or search counts changed")
                state = _json(row["state"])
                prior = value["failure_state"]
                _assert_failure_floor(state, prior, guarded_verdicts=guarded_verdicts.get(value["id"]))
                original_spec, current_spec = _json(value["spec"]), _json(row["spec"])
                if any(current_spec.get(k) != original_spec.get(k) for k in ("prior_lineage", "prior_lineages", "card_sha")):
                    raise ResearchStateError("historical prior lineage or card identity changed")
            elif kind == "version":
                row = connection.execute("SELECT * FROM versions WHERE family=? AND n=?", (value["family"], value["n"])).fetchone()
                if row is None or any(row[k] != value[k] for k in ("sha", "params")):
                    raise ResearchStateError("historical version identity changed")
            elif kind == "run":
                row = connection.execute("SELECT * FROM runs WHERE run_id=?", (value["run_id"],)).fetchone()
                if (row is None or any(row[k] != value[k] for k in (
                        "family", "version", "window", "stress", "purpose", "at", "status", "program_years"))
                        or type(row["trials"]) is not int or row["trials"] < value["trials"]):
                    raise ResearchStateError("historical run identity or trial baseline changed")
                if row["window"] != "train" and (row["path"] is not None or not _json(row["summary"]).get("isolation_redacted")):
                    raise ResearchStateError("sealed or Validation result payload entered the working view")
            elif kind == "look":
                row = connection.execute("SELECT * FROM looks WHERE seq=?", (value["seq"],)).fetchone()
                if (row is None or any(row[k] != v for k, v in value.items()) or row["passed"] is not None
                        or row["p_value"] is not None):
                    raise ResearchStateError("historical look identity or redaction changed")
            elif kind == "lineage_link":
                if connection.execute("SELECT 1 FROM lineage_links WHERE a=? AND b=?", (value["a"], value["b"])).fetchone() is None:
                    raise ResearchStateError("historical lineage connection was removed")
            elif kind in ("refusals", "look_holds", "notebook", "graveyard"):
                exported = value["row"]
                column = "family" if kind == "graveyard" else "seq"
                row = connection.execute(f"SELECT * FROM {kind} WHERE {column}=?", (exported[column],)).fetchone()
                if row is None or any(row[k] != v for k, v in exported.items()):
                    raise ResearchStateError("historical retirement, refusal or audit evidence changed")
            elif kind == "family_card":
                row = connection.execute("SELECT * FROM family_cards WHERE family=?", (baseline["identity"],)).fetchone()
                if (row is None or _value_sha(dict(row)) != value["projected_row_sha256"]
                        or _value_sha(_json(row["card"])) != value["projected_content_sha256"]):
                    raise ResearchStateError("historical family card changed")
            elif kind == "card_evidence":
                row = connection.execute("SELECT * FROM card_evidence WHERE seq=?", (baseline["identity"],)).fetchone()
                if row is None or any(row[k] != v for k, v in value.items()):
                    raise ResearchStateError("historical mechanism verdict changed")
    # PID/.env/live files are not in the allowlisted import. A launcher must still prevent later mounts.
    forbidden = {".env", "swarm.pid", "swarm.lock", "swarm.heartbeat", "money.sqlite", "book.sqlite", "provider.sqlite"}
    if any(path.name in forbidden for path in root.rglob("*")):
        raise ResearchStateError("forbidden runtime, financial or credential file entered the working view")
    return receipt
