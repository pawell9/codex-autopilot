#!/usr/bin/env python3
"""Deterministic Codex Autopilot ledger and contract helper.

The helper owns no orchestration loop and never invokes a model.  It validates
closed-schema payloads, publishes one ledger revision under an advisory lock,
and records exact evidence bytes.  Git mutations remain native approved
orchestrator actions; this module only validates their receipts.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

SKILL_VERSION = "1.0.9"
POLICY_VERSION = "v1-manual-g5"
SCHEMA_VERSION = "1.0"
COMPATIBILITY_FLOOR = "1.0.0"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
PHASES = ("PREFLIGHT", "INTENT", "DESIGN", "PLAN", "EXECUTE", "VERIFY", "ACCEPT")
CONTROLS = ("ACTIVE", "QUIESCING", "PAUSED", "BLOCKED", "RECOVERING", "ACCEPTED", "FAILED", "CANCELLED")
CAUSES = ("implementation", "contract", "oracle", "environment", "permission", "ownership", "orchestration", "user_intent", "unknown")
VALID_CONTEXT_GRADES = {"PACKET_SCOPED", "DEGRADED_CONTEXT", "MANUAL_ATTESTED_CLEAN", "STRICT_FRESH"}
DEFAULT_RUN_SETTINGS = {"interaction_mode": "semi", "depth": "normal"}
RUN_SETTING_LABELS = {
    "interaction_mode": {"semi": "полуавтомат", "full": "полный автомат"},
    "depth": {"normal": "обычная", "deep": "глубокая"},
}
USAGE_FIELDS = (
    "helper_calls", "model_turns", "orchestrator_turns", "spawn_calls", "wait_calls", "git_calls",
    "internal_publications", "packet_bytes", "return_bytes", "brief_bytes", "wall_time_ms",
    "approvals", "user_interventions", "manual_handoffs", "manual_setup", "manual_wait",
)


class LedgerError(Exception):
    """A safe, user-actionable validation or publication failure."""


class IdempotentResult(Exception):
    """Abort a locked transaction without publication and return prior success."""

    def __init__(self, result: dict[str, Any]):
        super().__init__("idempotent")
        self.result = result


def fail(message: str) -> None:
    raise LedgerError(message)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def zero_usage() -> dict[str, int]:
    return {field: 0 for field in USAGE_FIELDS}


def default_usage() -> dict[str, Any]:
    return {
        "counters": zero_usage(),
        "tokens": None,
        "token_reason": "token_meter_unavailable",
        "unknown_reason": "token meter unavailable on this runtime",
        "trace": [],
        "shared_setup": zero_usage(),
        "gate_costs": {f"G{i}": zero_usage() for i in range(7)},
    }


def ensure_runtime_provenance(state: dict[str, Any]) -> dict[str, Any]:
    """Add effective helper provenance without rewriting run creation history."""
    provenance = state.setdefault("runtime_provenance", {
        "creation_skill_version": state.get("skill_version", "unknown"),
        "current_schema_version": state.get("schema_version", SCHEMA_VERSION),
        "last_mutating_skill_version": SKILL_VERSION,
        "compatibility_floor": COMPATIBILITY_FLOOR,
        "applied_migrations": [],
    })
    provenance.setdefault("creation_skill_version", state.get("skill_version", "unknown"))
    provenance["current_schema_version"] = state.get("schema_version", SCHEMA_VERSION)
    provenance["last_mutating_skill_version"] = SKILL_VERSION
    provenance.setdefault("compatibility_floor", COMPATIBILITY_FLOOR)
    provenance.setdefault("applied_migrations", [])
    return provenance


def resolved_run_settings(state: dict[str, Any]) -> dict[str, str]:
    """Return effective settings without migrating legacy ledgers."""
    stored = state.get("run_settings")
    if not isinstance(stored, dict):
        stored = {}
    return {
        "interaction_mode": stored.get("interaction_mode", DEFAULT_RUN_SETTINGS["interaction_mode"]),
        "depth": stored.get("depth", DEFAULT_RUN_SETTINGS["depth"]),
    }


def run_settings_display(settings: dict[str, str]) -> str:
    mode = RUN_SETTING_LABELS["interaction_mode"].get(settings["interaction_mode"], settings["interaction_mode"])
    depth = RUN_SETTING_LABELS["depth"].get(settings["depth"], settings["depth"])
    return f"Режим: {mode} · глубина: {depth}"


def parse_run_settings(request: str | None) -> dict[str, str]:
    """Parse only obvious English/Russian preset phrases; ambiguity defaults."""
    if not request:
        return dict(DEFAULT_RUN_SETTINGS)
    text = re.sub(r"[_/–—-]+", " ", request.casefold())
    full = bool(re.search(r"(?:\bполный\s+автомат(?:ический)?\b|\bполностью\s+автомат(?:ический)?\b|\bfull\s+(?:auto|automatic|automated|automation|mode)\b|\bfully\s+automatic\b)", text))
    semi = bool(re.search(r"(?:\bполуавтомат(?:ический)?\b|\bsemi\s+automatic\b|\bsemi\s+automated\b|\bsemi\s+mode\b)", text))
    deep = bool(re.search(r"(?:\bглубок(?:ая|ий|ое|ую|о)?\b|\bdeep\b|\bin\s+depth\b|\bthorough\b|\bdetailed\b)", text))
    normal = bool(re.search(r"(?:\bобычн(?:ая|ый|ое|ую|о)?\b|\bnormal\b|\bstandard\b|\bbaseline\b)", text))
    return {
        "interaction_mode": "full" if full and not semi else DEFAULT_RUN_SETTINGS["interaction_mode"],
        "depth": "deep" if deep and not normal else DEFAULT_RUN_SETTINGS["depth"],
    }


def run_settings_from_args(request: str | None, interaction_mode: str | None, depth: str | None) -> dict[str, str]:
    settings = parse_run_settings(request)
    if interaction_mode is not None:
        settings["interaction_mode"] = interaction_mode
    if depth is not None:
        settings["depth"] = depth
    return settings


def routing_intent(state: dict[str, Any]) -> dict[str, Any]:
    """Expose preset intent to routing without binding or selecting a model."""
    settings = resolved_run_settings(state)
    return {"interaction_mode": settings["interaction_mode"], "depth": settings["depth"], "model_binding": None}


def add_usage(target: dict[str, int], delta: dict[str, Any]) -> None:
    for field in USAGE_FIELDS:
        value = delta.get(field, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            fail(f"usage delta {field} must be a non-negative integer")
        target[field] = target.get(field, 0) + value


def current_intent_binding(state: dict[str, Any]) -> dict[str, str]:
    intent = state.get("intent")
    if not isinstance(intent, dict):
        fail("current intent is missing")
    document_ref = intent.get("document_ref")
    document = next((item for item in state.get("documents", []) if item.get("id") == document_ref), None)
    if document is None:
        fail("current intent document is missing")
    path = Path(document.get("path", ""))
    if not path.exists() or path.is_symlink() or not path.is_file():
        fail("current intent document is unavailable")
    actual_hash = sha256_file(path)
    if actual_hash != document.get("hash"):
        fail("current intent document hash does not match the ledger")
    expected_hash = intent.get("document_hash")
    if expected_hash is not None and expected_hash != actual_hash:
        fail("current intent document hash does not match intent binding")
    return {"revision": str(intent.get("current_revision")), "document_ref": str(document_ref), "document_hash": actual_hash}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_id(value: str, label: str = "id") -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        fail(f"invalid {label}: expected path-safe identifier")
    return value


def safe_root(path: str | Path, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        fail(f"{label} may not be a symlink")
    result = candidate.resolve()
    if result == Path(result.anchor):
        fail(f"{label} may not be filesystem root")
    return result


def under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def regular_non_symlink(path: Path) -> None:
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        fail(f"expected regular non-symlink file: {path}")


def regular_directory(path: Path, label: str = "directory") -> None:
    if path.is_symlink() or not path.is_dir():
        fail(f"expected regular non-symlink {label}: {path}")


def relative_path(value: str, label: str = "path") -> str:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        fail(f"invalid {label}: expected repository-relative path")
    path = Path(value)
    if ".." in path.parts:
        fail(f"invalid {label}: path traversal is not allowed")
    return path.as_posix()


def read_json(path: Path, label: str = "JSON") -> Any:
    regular_non_symlink(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid {label} {path}: {exc}")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp.exists():
            temp.unlink()


class Lock:
    def __init__(self, path: Path):
        self.path = path
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+")
        fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_args):
        if self.stream is not None:
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()


def schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / "contracts.schema.json"


def schema() -> dict[str, Any]:
    try:
        return json.loads(schema_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"schema unavailable or malformed: {exc}")


def validate(value: Any, spec: dict[str, Any], root: dict[str, Any], path: str = "$", seen: set[str] | None = None) -> None:
    """Validate the closed subset used by this package; unknown keywords fail closed."""
    supported = {"$schema", "$id", "$defs", "title", "$ref", "type", "required", "properties", "additionalProperties", "items", "enum", "const", "pattern", "minLength", "minItems", "minimum", "minProperties"}
    unknown = set(spec) - supported
    if unknown:
        fail(f"unsupported schema keyword(s) at {path}: {sorted(unknown)}")
    if "$ref" in spec:
        ref = spec["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            fail(f"unsupported schema ref at {path}: {ref}")
        name = ref.rsplit("/", 1)[-1]
        validate(value, root.get("$defs", {}).get(name, {}), root, path, seen)
        return
    if "const" in spec and value != spec["const"]:
        fail(f"{path}: expected constant {spec['const']!r}")
    if "enum" in spec and value not in spec["enum"]:
        fail(f"{path}: value {value!r} is not in enum")
    types = spec.get("type")
    if types:
        allowed = [types] if isinstance(types, str) else types
        ok = any({"object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str), "integer": isinstance(value, int) and not isinstance(value, bool), "number": isinstance(value, (int, float)) and not isinstance(value, bool), "boolean": isinstance(value, bool), "null": value is None}.get(t, False) for t in allowed)
        if not ok:
            fail(f"{path}: wrong type")
    if isinstance(value, str):
        if len(value) < spec.get("minLength", 0):
            fail(f"{path}: shorter than minLength")
        if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
            fail(f"{path}: pattern mismatch")
    if isinstance(value, (int, float)) and value < spec.get("minimum", value):
        fail(f"{path}: below minimum")
    if isinstance(value, list):
        if len(value) < spec.get("minItems", 0):
            fail(f"{path}: fewer than minItems")
        if "items" in spec:
            for index, item in enumerate(value):
                validate(item, spec["items"], root, f"{path}[{index}]")
    if isinstance(value, dict):
        if len(value) < spec.get("minProperties", 0):
            fail(f"{path}: fewer than minProperties")
        for required in spec.get("required", []):
            if required not in value:
                fail(f"{path}: missing required field {required}")
        properties = spec.get("properties", {})
        if spec.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                fail(f"{path}: unknown field(s): {sorted(extras)}")
        for key, child in properties.items():
            if key in value:
                validate(value[key], child, root, f"{path}.{key}")


def validate_ledger(state: dict[str, Any], *, verify_files: bool = True) -> None:
    root = schema()
    validate(state, root, root)
    if state["run_id"] != Path(state["repository"]["control_root"]).name and state["run_id"] == "":
        fail("run_id must be nonempty")
    ids: set[str] = set()
    for collection in ("documents", "requirements", "criteria", "contracts", "decisions", "tickets", "attempts", "issues", "findings", "reviews", "operations", "capabilities", "routes", "evidence", "invalidations"):
        for item in state.get(collection, []):
            if "id" in item:
                if item["id"] in ids:
                    fail(f"duplicate immutable ID: {item['id']}")
                ids.add(item["id"])
    publication = state.get("design_publication")
    history = state.get("design_publication_history", [])
    history_ids: set[str] = set()
    for historical in history:
        if historical["id"] in history_ids or historical["id"] in ids:
            fail(f"duplicate immutable design publication ID: {historical['id']}")
        history_ids.add(historical["id"])
        ids.add(historical["id"])
    if publication:
        if publication["id"] in ids and publication["id"] not in history_ids:
            fail(f"duplicate immutable ID: {publication['id']}")
        if publication["id"] in history_ids:
            latest = history[-1] if history else None
            if latest is None or latest != publication:
                fail("current design publication does not match the latest history item")
        else:
            ids.add(publication["id"])
    ticket_ids = {item["id"] for item in state.get("tickets", [])}
    criterion_ids = {item["id"] for item in state.get("criteria", [])}
    requirement_ids = {item["id"] for item in state.get("requirements", [])}
    document_ids = {item["id"] for item in state.get("documents", [])}
    if state.get("intent"):
        intent = state["intent"]
        if intent["document_ref"] not in document_ids:
            fail("intent references unknown document")
        if intent.get("document_hash"):
            document = next(item for item in state.get("documents", []) if item["id"] == intent["document_ref"])
            if document.get("hash") != intent["document_hash"]:
                fail("intent document_hash does not match document")
    if publication and publication.get("status") == "PUBLISHED":
        if not state.get("intent"):
            fail("design publication requires a current intent")
        intent = state["intent"]
        if publication["intent_revision"] != intent.get("current_revision") or publication["intent_document_ref"] != intent.get("document_ref") or publication["intent_document_hash"] != intent.get("document_hash"):
            fail("design publication is bound to a stale intent")
        refs = set(publication["document_refs"])
        if not refs or not refs.issubset(document_ids):
            fail("design publication references an unknown document")
        if not set(publication["contract_refs"]).issubset({item["id"] for item in state.get("contracts", [])}):
            fail("design publication references an unknown contract")
        if not set(publication["ticket_refs"]).issubset({item["id"] for item in state.get("tickets", [])}):
            fail("design publication references an unknown ticket")
        if not set(publication["route_refs"]).issubset({item["id"] for item in state.get("routes", [])}):
            fail("design publication references an unknown route")
        if not set(publication.get("requirement_refs", [])).issubset(requirement_ids):
            fail("design publication references an unknown requirement")
        if not set(publication.get("criterion_refs", [])).issubset(criterion_ids):
            fail("design publication references an unknown criterion")
        for document in state.get("documents", []):
            if document["id"] in refs:
                path = Path(document["path"])
                if verify_files and (not path.exists() or path.is_symlink() or not path.is_file() or sha256_file(path) != document["hash"]):
                    fail(f"published design document is unavailable or drifted: {document['id']}")
    for historical in history:
        if historical["bundle_ref"] != f"objects/{historical['publication_hash']}":
            fail(f"design publication history bundle reference does not match its fingerprint: {historical['id']}")
        refs = set(historical["document_refs"])
        if not refs or not refs.issubset(document_ids):
            fail("design publication history references an unknown document")
        if not set(historical["contract_refs"]).issubset({item["id"] for item in state.get("contracts", [])}):
            fail("design publication history references an unknown contract")
        if not set(historical["ticket_refs"]).issubset({item["id"] for item in state.get("tickets", [])}):
            fail("design publication history references an unknown ticket")
        if not set(historical["route_refs"]).issubset({item["id"] for item in state.get("routes", [])}):
            fail("design publication history references an unknown route")
        if not set(historical.get("requirement_refs", [])).issubset(requirement_ids):
            fail("design publication history references an unknown requirement")
        if not set(historical.get("criterion_refs", [])).issubset(criterion_ids):
            fail("design publication history references an unknown criterion")
        if verify_files:
            for document in state.get("documents", []):
                if document["id"] in refs:
                    path = Path(document["path"])
                    if not path.exists() or path.is_symlink() or not path.is_file() or sha256_file(path) != document["hash"]:
                        fail(f"historical design document is unavailable or drifted: {document['id']}")
    publication_records = history or ([publication] if publication else [])
    for record in publication_records:
        if record["bundle_ref"] != f"objects/{record['publication_hash']}":
            fail(f"design publication bundle reference does not match its fingerprint: {record['id']}")
        if verify_files:
            object_path = Path(state["repository"]["control_root"]) / ".autopilot" / "runs" / state["run_id"] / record["bundle_ref"]
            if not object_path.exists() or object_path.is_symlink() or not object_path.is_file() or sha256_file(object_path) != record["publication_hash"]:
                fail(f"design publication bundle object is unavailable or drifted: {record['id']}")
    for requirement in state.get("requirements", []):
        if any(ref not in criterion_ids for ref in requirement.get("criterion_refs", [])):
            fail(f"requirement references unknown criterion: {requirement['id']}")
    for criterion in state.get("criteria", []):
        if any(ref not in requirement_ids for ref in criterion.get("requirement_refs", [])):
            fail(f"criterion references unknown requirement: {criterion['id']}")
    requirement_publication_ids: set[str] = set()
    for record in state.get("requirements_publications", []):
        if record["id"] in requirement_publication_ids or record["id"] in ids:
            fail(f"duplicate immutable requirements publication ID: {record['id']}")
        requirement_publication_ids.add(record["id"])
        ids.add(record["id"])
        if not set(record["requirement_refs"]).issubset(requirement_ids):
            fail(f"requirements publication references an unknown requirement: {record['id']}")
        if not set(record["criterion_refs"]).issubset(criterion_ids):
            fail(f"requirements publication references an unknown criterion: {record['id']}")
        if record["manifest_ref"] != f"objects/{record['publication_hash']}":
            fail(f"requirements publication object reference does not match its hash: {record['id']}")
        if verify_files:
            object_path = Path(state["repository"]["control_root"]) / ".autopilot" / "runs" / state["run_id"] / record["manifest_ref"]
            if not object_path.exists() or object_path.is_symlink() or not object_path.is_file() or sha256_file(object_path) != record["publication_hash"]:
                fail(f"requirements publication object is unavailable or drifted: {record['id']}")
    if publication and publication.get("requirements_publication_ref") is not None:
        requirements_record = next((item for item in state.get("requirements_publications", []) if item.get("id") == publication["requirements_publication_ref"]), None)
        if requirements_record is None:
            fail("design publication references an unknown requirements publication")
        if requirements_record.get("intent_revision") != publication.get("intent_revision") or requirements_record.get("intent_document_hash") != publication.get("intent_document_hash"):
            fail("design publication requirements binding is stale")
    for ticket in state.get("tickets", []):
        if any(ref not in criterion_ids for ref in ticket.get("criterion_refs", [])):
            fail(f"ticket references unknown criterion: {ticket['id']}")
    graph = {item["id"]: set(item.get("dependency_refs", [])) for item in state.get("tickets", [])}
    if any(dep not in ticket_ids for deps in graph.values() for dep in deps):
        fail("ticket dependency references unknown ticket")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting:
            fail("ticket dependency graph contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)
    for node in graph:
        visit(node)
    for attempt in state.get("attempts", []):
        if attempt["epoch"] > state["owner"]["epoch"] + 1:
            fail(f"attempt epoch is ahead of owner epoch: {attempt['id']}")
        if state.get("runtime_provenance") and attempt.get("kind") == "review" and attempt.get("state") == "RETURNED" and attempt.get("lease", {}).get("state") == "active":
            fail(f"returned reviewer attempt retains an active lease: {attempt['id']}")
    if state["lifecycle"]["control"] == "ACCEPTED":
        if not any(a.get("verdict") == "PASS" for a in state.get("acceptance", [])):
            fail("ACCEPTED requires a recorded G5 PASS")
    for operation in state.get("operations", []):
        if operation.get("state") == "applied" and not operation.get("receipt_ref"):
            fail(f"applied operation lacks receipt: {operation['id']}")
    all_ids = ids
    for finding in state.get("findings", []):
        if any(ref not in all_ids for ref in finding.get("affected_refs", [])):
            fail(f"finding references unknown subject: {finding['id']}")
    for invalidation in state.get("invalidations", []):
        if invalidation.get("amendment_ref") not in all_ids:
            # The amendment itself is an event ID, not a regular collection
            # member; validate its shape while allowing it to be new.
            safe_id(invalidation.get("amendment_ref"), "amendment_id")
        if any(ref not in all_ids for ref in invalidation.get("consumer_refs", [])):
            fail(f"invalidation references unknown consumer: {invalidation['id']}")
    usage = state.get("usage")
    if usage and usage.get("tokens") is None and not usage.get("token_reason"):
        fail("usage with tokens=null requires token_reason")
    provenance = state.get("runtime_provenance")
    if provenance:
        if provenance.get("creation_skill_version") != state.get("skill_version"):
            fail("runtime provenance must preserve the run creation skill version")
        if provenance.get("current_schema_version") != state.get("schema_version"):
            fail("runtime provenance schema version does not match the ledger")
        migration_ids = [item["id"] for item in provenance.get("applied_migrations", [])]
        if len(migration_ids) != len(set(migration_ids)):
            fail("runtime provenance contains duplicate migration IDs")


def paths(control_root: str | Path, run_id: str) -> dict[str, Path]:
    root = safe_root(control_root, "control root")
    safe_id(run_id, "run_id")
    base = root / ".autopilot"
    if base.is_symlink():
        fail("canonical .autopilot namespace may not be a symlink")
    run = base / "runs" / run_id
    return {"root": root, "base": base, "run": run, "ledger": run / "ledger.json", "prev": run / "ledger.prev.json", "lock": base / "owner.lock", "objects": run / "objects", "packets": run / "packets", "docs": run / "docs", "scratch": base / "scratch" / run_id}


def load_state(p: dict[str, Path]) -> tuple[dict[str, Any], bytes]:
    regular_non_symlink(p["ledger"])
    raw = p["ledger"].read_bytes()
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"current ledger is corrupt: {exc}; inspect ledger.prev.json/snapshots read-only")
    validate_ledger(state)
    return state, raw


def verified_state_file(path: Path, expected_run_id: str) -> tuple[dict[str, Any], bytes] | None:
    """Return only a canonical, schema-valid publication suitable for recovery."""
    try:
        regular_non_symlink(path)
        raw = path.read_bytes()
        state = json.loads(raw.decode("utf-8"))
        validate_ledger(state)
        if state.get("run_id") != expected_run_id or canonical_bytes(state) != raw:
            return None
        return state, raw
    except (LedgerError, OSError, UnicodeError, json.JSONDecodeError):
        return None


def recovery_candidates(p: dict[str, Path], run_id: str) -> list[tuple[dict[str, Any], bytes, Path]]:
    candidates: list[tuple[dict[str, Any], bytes, Path]] = []
    for candidate in (p["prev"],):
        verified = verified_state_file(candidate, run_id)
        if verified:
            candidates.append((*verified, candidate))
    snapshot_root = p["run"] / "snapshots"
    if snapshot_root.exists():
        if snapshot_root.is_symlink() or not snapshot_root.is_dir():
            fail("recovery snapshot namespace is not a regular directory")
        for candidate in snapshot_root.iterdir():
            if candidate.suffix != ".json" or candidate.is_symlink():
                continue
            verified = verified_state_file(candidate, run_id)
            if verified:
                candidates.append((*verified, candidate))
    return sorted(candidates, key=lambda item: (item[0].get("revision", -1), item[2].name), reverse=True)


def snapshot_is_pinned(state: dict[str, Any]) -> bool:
    return (
        any(op.get("state") in ("prepared", "uncertain") for op in state.get("operations", []))
        or state.get("lifecycle", {}).get("control") in ("RECOVERING", "ACCEPTED", "FAILED", "CANCELLED")
    )


def write_snapshot(p: dict[str, Path], state: dict[str, Any], kind: str) -> Path:
    snapshot_root = p["run"] / "snapshots"
    regular_directory(p["run"], "run directory")
    if snapshot_root.exists() and (snapshot_root.is_symlink() or not snapshot_root.is_dir()):
        fail("recovery snapshot namespace is not a regular directory")
    snapshot_root.mkdir(parents=True, exist_ok=True)
    safe_kind = re.sub(r"[^A-Za-z0-9._-]+", "-", kind).strip("-") or "checkpoint"
    prefix = "pinned-" if snapshot_is_pinned(state) else ""
    target = snapshot_root / f"{prefix}{state['revision']}-{safe_kind}.json"
    atomic_write(target, canonical_bytes(state))
    return target


def prune_snapshots(p: dict[str, Path]) -> None:
    snapshot_root = p["run"] / "snapshots"
    if not snapshot_root.exists():
        return
    regular_directory(snapshot_root, "snapshot namespace")
    unpinned = [path for path in snapshot_root.iterdir() if path.suffix == ".json" and not path.name.startswith("pinned-") and not path.is_symlink()]
    unpinned.sort(key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
    for path in unpinned[8:]:
        path.unlink()


def publish(p: dict[str, Path], state: dict[str, Any], previous_raw: bytes | None, snapshot_kind: str | None = None) -> None:
    ensure_runtime_provenance(state)
    validate_ledger(state)
    if previous_raw is not None:
        if not p["prev"].parent.exists():
            fail("ledger parent missing before previous-publication backup")
        atomic_write(p["prev"], previous_raw)
    raw = canonical_bytes(state)
    atomic_write(p["ledger"], raw)
    if snapshot_kind:
        write_snapshot(p, state, snapshot_kind)
        prune_snapshots(p)


def transaction(p: dict[str, Path], token: str, expected_revision: int | None, change: Callable[[dict[str, Any]], None], snapshot_kind: str | None = None) -> dict[str, Any]:
    started = time.monotonic()
    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != token:
            fail("owner token mismatch; stale orchestrator is fenced")
        if expected_revision is not None and state["revision"] != expected_revision:
            fail(f"revision mismatch: expected {expected_revision}, current {state['revision']}")
        next_state = copy.deepcopy(state)
        change(next_state)
        usage = next_state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage())
        usage.setdefault("trace", [])
        usage.setdefault("shared_setup", zero_usage())
        usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        delta = {field: 0 for field in USAGE_FIELDS}
        delta["helper_calls"] = 1
        delta["internal_publications"] = 1
        delta["wall_time_ms"] = max(0, int((time.monotonic() - started) * 1000))
        add_usage(usage["counters"], delta)
        usage["trace"].append({"id": f"trace-{state['revision'] + 1}-helper", "kind": "helper_publication", "actor": "ledger-helper", "subject_ref": state.get("lifecycle", {}).get("next_action", {}).get("kind"), "delta": delta, "evidence_ref": None, "recorded_at": now()})
        next_state["revision"] = state["revision"] + 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        publish(p, next_state, previous_raw, snapshot_kind)
        return next_state


def object_store(p: dict[str, Path], raw: bytes) -> str:
    digest = sha256_bytes(raw)
    target = p["objects"] / digest
    if p["objects"].exists() and (p["objects"].is_symlink() or not p["objects"].is_dir()):
        fail("immutable object namespace is not a regular directory")
    p["objects"].mkdir(parents=True, exist_ok=True)
    if target.exists():
        regular_non_symlink(target)
        if sha256_file(target) != digest:
            fail(f"immutable object collision: {target}")
    else:
        atomic_write(target, raw)
    return digest


def canonical_document_path(p: dict[str, Path], document_id: str, document_version: str) -> Path:
    """Resolve one immutable Markdown destination without permitting docs/ escape."""
    safe_id(document_id, "document_id")
    safe_id(document_version, "document_version")
    docs_root = p["docs"].resolve()
    if p["docs"].exists() and (p["docs"].is_symlink() or not p["docs"].is_dir()):
        fail("canonical document namespace is not a regular directory")
    destination = (p["docs"] / document_id / f"{document_version}.md").resolve()
    if not under(destination, docs_root):
        fail("canonical document path escapes the run document namespace")
    return destination


def intent_source_bytes(value: str) -> bytes:
    candidate = Path(value).expanduser()
    if candidate.is_symlink():
        fail("intent source may not be a symlink")
    source = candidate.resolve()
    if not source.exists():
        fail(f"intent source does not exist: {source}")
    regular_non_symlink(source)
    raw = source.read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        fail("intent source exceeds the 4 MiB bound")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"intent source must be UTF-8 Markdown: {exc}")
    if not text.strip():
        fail("intent source must contain non-whitespace Markdown")
    return raw


def inbox_file(p: dict[str, Path], attempt_id: str, candidate: Path) -> Path:
    attempt_root = (p["scratch"] / safe_id(attempt_id, "attempt_id")).resolve()
    candidate = candidate.expanduser().absolute()
    if candidate.is_symlink():
        fail("return inbox file must not be a symlink")
    candidate = candidate.parent.resolve() / candidate.name
    if not under(candidate, attempt_root):
        fail("return path escapes the registered exact attempt inbox")
    regular_non_symlink(candidate)
    if candidate.stat().st_size > 4 * 1024 * 1024:
        fail("return exceeds the 4 MiB contract bound")
    return candidate


def attempt_by_id(state: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    for attempt in state.get("attempts", []):
        if attempt["id"] == attempt_id:
            return attempt
    fail(f"unknown attempt: {attempt_id}")


def packet_identity(packet: dict[str, Any]) -> dict[str, Any]:
    identity = packet.get("identity")
    if not isinstance(identity, dict):
        fail("packet/return identity is required")
    return identity


def validate_route_eligibility(route: dict[str, Any]) -> None:
    if route.get("adequacy") != "CONFIRMED":
        fail(f"route is not eligible for dispatch: adequacy={route.get('adequacy')}")
    context_grade = route.get("context_grade")
    if not isinstance(context_grade, str) or context_grade not in VALID_CONTEXT_GRADES:
        fail(f"route is not eligible for dispatch: invalid context_grade={context_grade!r}")
    fallback = route.get("fallback_cause")
    if fallback is not None:
        if fallback not in CAUSES:
            fail(f"route is not eligible for dispatch: invalid fallback_cause={fallback!r}")
        if not route.get("requested_binding") and not route.get("observed_binding"):
            fail("route is not eligible for dispatch: fallback lacks requested/observed binding")
        if context_grade in {"UNKNOWN", "REJECTED"}:
            fail("route is not eligible for dispatch: fallback context is not usable")


def repair_signature(contract: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes({key: contract.get(key) for key in ("cause", "finding_ref", "hypothesis", "expected_proof", "stopping_condition", "causal_change")}))


def nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{label} must be a non-empty string")
    return value


def ids_from_records(records: list[dict[str, Any]], key: str, label: str) -> list[str]:
    values: list[str] = []
    for record in records:
        value = record.get(key)
        safe_id(value, label)
        values.append(value)
    if len(values) != len(set(values)):
        fail(f"duplicate {label} records")
    return values


def design_bundle_source(record: dict[str, Any]) -> tuple[Path, bytes]:
    source_value = record.get("source")
    if not isinstance(source_value, str) or not source_value or not Path(source_value).is_absolute() or ".." in Path(source_value).parts:
        fail("design artifact source must be an absolute, traversal-free path")
    candidate = Path(source_value).expanduser()
    if candidate.is_symlink():
        fail("design artifact source may not be a symlink")
    source = candidate.resolve()
    if not source.exists():
        fail(f"design artifact source does not exist: {source}")
    regular_non_symlink(source)
    if source.stat().st_size > 4 * 1024 * 1024:
        fail("design artifact exceeds the 4 MiB bound")
    raw = source.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"design artifact must be UTF-8 Markdown: {exc}")
    if not text.strip():
        fail("design artifact must contain non-whitespace Markdown")
    if sha256_bytes(raw) != record.get("hash"):
        fail(f"design artifact hash does not match source: {record.get('id')}")
    return source, raw


def validate_design_bundle(bundle: dict[str, Any]) -> None:
    """Validate the complete proposed design publication without touching state."""
    safe_id(bundle.get("bundle_id"), "design bundle ID")
    root = schema()
    documents = bundle.get("documents", [])
    document_ids = ids_from_records(documents, "id", "design document")
    kinds = {item.get("kind") for item in documents}
    if "design" not in kinds:
        fail("design bundle requires a design artifact")
    if not ({"interfaces", "contracts", "interface"} & kinds) or not bundle.get("contracts"):
        fail("design bundle requires interfaces and contract records")
    if "manifest" not in kinds:
        fail("design bundle requires a manifest artifact")
    if not ({"plan", "implementation_plan", "implementation-plan", "evaluation_plan", "evaluation-plan"} & kinds):
        fail("design bundle requires an implementation plan artifact")
    if not ({"tickets", "implementation_tickets", "implementation-tickets"} & kinds) or not bundle.get("tickets"):
        fail("design bundle requires a tickets artifact and ticket records")
    if not ({"routes", "route", "dependencies"} & kinds) or not bundle.get("routes"):
        fail("design bundle requires routes/dependencies and route records")
    for document in documents:
        design_bundle_source(document)
    for name in ("contracts", "tickets", "routes"):
        definition = root["$defs"][name[:-1] if name != "routes" else "route"]
        for index, record in enumerate(bundle[name]):
            validate(record, definition, root, f"$.{name}[{index}]")
            safe_id(record["id"], f"{name[:-1]} ID")
    all_bundle_ids = document_ids + [item["id"] for item in bundle["contracts"]] + [item["id"] for item in bundle["tickets"]] + [item["id"] for item in bundle["routes"]]
    if len(all_bundle_ids) != len(set(all_bundle_ids)):
        fail("design bundle contains duplicate immutable IDs")
    for route in bundle["routes"]:
        validate_route_eligibility(route)
    validate_ticket_contract_bindings(bundle["contracts"], bundle["tickets"], "design bundle")
    ticket_ids = {item["id"] for item in bundle["tickets"]}
    graph = {item["id"]: set(item.get("dependency_refs", [])) for item in bundle["tickets"]}
    if any(ref not in ticket_ids for refs in graph.values() for ref in refs):
        fail("design bundle ticket dependency references a ticket outside the bundle")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(ticket_id: str) -> None:
        if ticket_id in visiting:
            fail("design bundle ticket dependency graph contains a cycle")
        if ticket_id in visited:
            return
        visiting.add(ticket_id)
        for dependency_id in graph[ticket_id]:
            visit(dependency_id)
        visiting.remove(ticket_id)
        visited.add(ticket_id)
    for ticket_id in graph:
        visit(ticket_id)

    def depends(ticket_id: str, dependency_id: str, seen: set[str] | None = None) -> bool:
        seen = set() if seen is None else seen
        if ticket_id in seen:
            fail("design bundle ticket dependency graph contains a cycle")
        seen.add(ticket_id)
        if dependency_id in graph[ticket_id]:
            return True
        return any(depends(item, dependency_id, set(seen)) for item in graph[ticket_id])

    def zones_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
        for left_zone in left.get("zone", []):
            left_path = relative_path(left_zone.get("path"), "ticket zone").rstrip("/")
            for right_zone in right.get("zone", []):
                right_path = relative_path(right_zone.get("path"), "ticket zone").rstrip("/")
                if left_path == right_path or left_path.startswith(right_path + "/") or right_path.startswith(left_path + "/"):
                    return True
        return False

    for index, left in enumerate(bundle["tickets"]):
        for right in bundle["tickets"][index + 1:]:
            if zones_overlap(left, right) and not depends(left["id"], right["id"]) and not depends(right["id"], left["id"]):
                fail(f"ticket zones overlap without dependency ordering: {left['id']} / {right['id']}")


def validate_ticket_contract_bindings(contracts: list[dict[str, Any]], tickets: list[dict[str, Any]], label: str) -> None:
    """Keep ticket inputs distinct from contracts produced by that ticket.

    ``ticket.contract_refs`` has always fed readiness and is therefore an
    input list.  ``contract.producer_refs`` is the existing output binding.
    Rejecting their intersection avoids silently reinterpreting legacy mixed
    bundles or activating a proposed output.
    """
    contract_by_id = {item.get("id"): item for item in contracts}
    for ticket in tickets:
        ticket_id = ticket.get("id")
        for contract_ref in ticket.get("contract_refs", []):
            contract = contract_by_id.get(contract_ref)
            if contract is None:
                continue
            if ticket_id in contract.get("producer_refs", []):
                fail(
                    f"{label} ticket {ticket_id} requires self-produced contract {contract_ref} as an input; "
                    "remove it from ticket.contract_refs and retain the explicit contract.producer_refs output binding"
                )


def validate_current_design_contract_bindings(state: dict[str, Any]) -> None:
    """Apply the input/output guard to an already-published legacy bundle."""
    publication = current_design_publication(state)
    ticket_refs = set(publication.get("ticket_refs", []))
    tickets = [item for item in state.get("tickets", []) if item.get("id") in ticket_refs]
    validate_ticket_contract_bindings(state.get("contracts", []), tickets, "current design publication")


def stored_payload(p: dict[str, Path], ref: str | None, label: str) -> dict[str, Any]:
    if not isinstance(ref, str) or not ref.startswith("objects/"):
        fail(f"{label} is not an immutable object reference")
    path = (p["run"] / ref).resolve()
    if not under(path, p["objects"]):
        fail(f"{label} escapes immutable object namespace")
    return read_json(path, label)


def validate_worker_return_semantics(payload: dict[str, Any], packet: dict[str, Any]) -> None:
    acceptance = packet.get("acceptance", [])
    checks = packet.get("verification", [])
    criteria = payload.get("criteria", [])
    returned_criteria = ids_from_records(criteria, "criterion_id", "worker criterion")
    required_criteria = ids_from_records(acceptance, "criterion_id", "packet criterion")
    if set(returned_criteria) != set(required_criteria):
        fail("worker return criteria do not correspond exactly to the packet")
    check_records = payload.get("checks", [])
    returned_checks = ids_from_records(check_records, "check_id", "worker check")
    required_checks = ids_from_records([item for item in checks if item.get("required", True)], "check_id", "packet check")
    if not set(required_checks).issubset(returned_checks):
        fail("worker return omits required packet checks")
    if payload.get("status") == "DONE" and any(record.get("outcome") != "pass" for record in check_records if record.get("check_id") in required_checks):
        fail("worker return has a failed or non-passing required check")
    if payload.get("status") == "DONE" and any(record.get("outcome") != "satisfied" for record in criteria):
        fail("worker return has an unsatisfied or unverifiable criterion")
    for record in payload.get("files", []):
        relative_path(record.get("path"), "worker file path")
        if record.get("operation") == "rename":
            relative_path(record.get("from"), "worker rename source")
            relative_path(record.get("to"), "worker rename target")
    issues = payload.get("issues", [])
    if payload.get("status") == "DONE" and any(item.get("impact") == "blocking" for item in issues):
        fail("DONE worker return contains a blocking issue")
    if payload.get("status") == "DONE" and (not required_criteria or not required_checks):
        fail("DONE worker return is not semantically complete")
    if payload.get("status") in ("BLOCKED", "FAILED") and not payload.get("issues"):
        fail(f"{payload['status']} worker return requires a typed issue")
    if payload.get("status") == "HANDOFF" and not payload.get("handoff"):
        fail("HANDOFF worker return requires a handoff object")


def worker_return_write_set_violations(payload: dict[str, Any], lease: dict[str, Any]) -> list[dict[str, str]]:
    """Return worker-declared paths/operations that exceed the current lease."""
    zone = lease.get("zone", [])

    def allowed(path: str, operation: str) -> bool:
        for entry in zone:
            zone_path = relative_path(entry.get("path"), "lease zone path").rstrip("/")
            if (path == zone_path or path.startswith(zone_path + "/")) and operation in entry.get("operations", []):
                return True
        return False

    violations: list[dict[str, str]] = []
    for record in payload.get("files", []):
        operation = record.get("operation")
        paths = [(record.get("path"), operation)]
        if operation == "rename":
            paths.extend(((record.get("from"), operation), (record.get("to"), operation)))
        for value, claimed_operation in paths:
            if value is None:
                continue
            path = relative_path(value, "worker file path")
            if not allowed(path, claimed_operation):
                violations.append({"path": path, "operation": claimed_operation})
    return violations


def zone_allows(zone: list[dict[str, Any]], path: str, operation: str) -> bool:
    clean = relative_path(path, "write allow path")
    for entry in zone:
        zone_path = relative_path(entry.get("path"), "ticket zone path").rstrip("/")
        if (clean == zone_path or clean.startswith(zone_path + "/")) and operation in entry.get("operations", []):
            return True
    return False


def packet_write_zone(packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the packet allowlist into the exact effective lease shape."""
    merged: dict[str, set[str]] = {}
    for entry in packet.get("write", {}).get("allow", []):
        path = relative_path(entry.get("path"), "packet write allow path").rstrip("/")
        merged.setdefault(path, set()).update(entry.get("operations", []))
    return [{"path": path, "operations": sorted(operations)} for path, operations in sorted(merged.items())]


def active_repair_authorization(state: dict[str, Any], ticket_id: str, finding_ref: str) -> dict[str, Any] | None:
    matches = [
        item for item in state.get("decisions", [])
        if item.get("type") == "repair_authorization"
        and item.get("status") == "authorized"
        and item.get("decision") == "REPAIR"
        and ticket_id in item.get("affected_refs", [])
        and finding_ref in item.get("affected_refs", [])
        and not item.get("invalidated_by")
    ]
    return matches[-1] if matches else None


def validate_repair_authorization(
    p: dict[str, Path], state: dict[str, Any], ticket_id: str, repair: dict[str, Any]
) -> dict[str, Any]:
    authorization = active_repair_authorization(state, ticket_id, repair.get("finding_ref"))
    if authorization is None:
        fail("repair dispatch requires an active authorize-repair decision for this ticket and finding")
    if any(item.get("repair_authorization_ref") == authorization["id"] for item in state.get("attempts", [])):
        fail("repair authorization was already consumed; authorize a changed repair before another dispatch")
    contract_refs = [ref for ref in authorization.get("evidence_refs", []) if isinstance(ref, str) and ref.startswith("objects/")]
    if len(contract_refs) != 1:
        fail("repair authorization lacks one exact repair contract object binding")
    authorized_contract = stored_payload(p, contract_refs[0], "authorized repair contract")
    if authorized_contract != repair:
        fail("repair packet contract does not match the authorized repair contract")
    return authorization


def finding_matches_candidate(state: dict[str, Any], finding_ref: str, ticket_id: str, candidate_sha: str) -> bool:
    """Prove that the authorized finding was raised against this candidate."""
    finding = next((item for item in state.get("findings", []) if item.get("id") == finding_ref), None)
    issue = next((item for item in state.get("issues", []) if item.get("id") == finding_ref), None)
    if issue and issue.get("finding_ref"):
        finding = next((item for item in state.get("findings", []) if item.get("id") == issue.get("finding_ref")), finding)
    record = finding or issue
    if record is None or record.get("impact") != "blocking" or record.get("invalidated_by"):
        return False
    if ticket_id not in record.get("affected_refs", []):
        return False
    source_ref = record.get("source_ref")
    source_attempt = next((item for item in state.get("attempts", []) if item.get("id") == source_ref), None)
    if source_attempt is not None:
        return (
            source_attempt.get("kind") == "review"
            and source_attempt.get("subject_ref") == ticket_id
            and source_attempt.get("candidate_sha") == candidate_sha
            and source_attempt.get("subject_fingerprint") in (None, candidate_sha)
        )
    source_review = next((item for item in state.get("reviews", []) if item.get("id") == source_ref), None)
    return bool(source_review and source_review.get("subject_fingerprint") == candidate_sha and ticket_id in record.get("affected_refs", []))


def repair_candidate_worker(
    state: dict[str, Any], ticket: dict[str, Any], repair: dict[str, Any], packet_base: str
) -> dict[str, Any]:
    """Resolve the one current worker candidate authorized for this repair base."""
    source_ref = repair.get("source_attempt_ref")
    source = next((item for item in state.get("attempts", []) if item.get("id") == source_ref), None)
    current = next(
        (item for item in state.get("attempts", []) if item.get("id") == ticket.get("current_attempt")),
        None,
    )
    if (
        current is None
        or current.get("kind") != "worker"
        or current.get("subject_ref") != ticket["id"]
        or current.get("candidate_sha") != packet_base
    ):
        fail("repair lease expansion base SHA is stale or forked from the current ticket candidate")
    if source is None or source.get("subject_ref") != ticket["id"]:
        fail("repair lease expansion requires exact same-ticket source_attempt_ref provenance")
    if source.get("kind") == "worker":
        if source.get("id") != current.get("id"):
            fail("repair lease expansion source worker is stale or forked from the current ticket candidate")
    elif source.get("kind") == "review":
        finding = next((item for item in state.get("findings", []) if item.get("id") == repair.get("finding_ref")), None)
        if (
            finding is None
            or finding.get("source_ref") != source.get("id")
            or repair.get("finding_ref") not in source.get("finding_refs", [])
            or source.get("candidate_sha") != packet_base
            or source.get("subject_fingerprint") not in (None, packet_base)
        ):
            fail("repair lease expansion source review is not the exact candidate-bound finding review")
    else:
        fail("repair lease expansion source_attempt_ref must name the current worker or its finding review")
    return current


def historical_repair_authorization(
    p: dict[str, Path], state: dict[str, Any], ticket_id: str, attempt: dict[str, Any], candidate_sha: str
) -> tuple[str, str]:
    """Revalidate one already-consumed repair authorization in a lineage."""
    repair = attempt.get("repair_contract")
    authorization_ref = attempt.get("repair_authorization_ref")
    provenance = attempt.get("repair_lease_provenance")
    if not isinstance(repair, dict):
        fail("repair lineage contains a repair attempt without a repair contract")
    finding_ref = repair.get("finding_ref")
    authorization = next(
        (
            item
            for item in state.get("decisions", [])
            if item.get("id") == authorization_ref
            and item.get("type") == "repair_authorization"
            and item.get("status") == "authorized"
            and item.get("decision") == "REPAIR"
            and ticket_id in item.get("affected_refs", [])
            and finding_ref in item.get("affected_refs", [])
            and not item.get("invalidated_by")
        ),
        None,
    )
    if authorization is None:
        fail("repair lineage contains a repair without an accepted same-ticket authorization")
    if isinstance(provenance, dict) and (
        provenance.get("authorization_ref") != authorization_ref
        or provenance.get("finding_ref") != finding_ref
    ):
        fail("repair lineage authorization/finding provenance is discontinuous")
    contract_refs = [
        ref
        for ref in authorization.get("evidence_refs", [])
        if isinstance(ref, str) and ref.startswith("objects/")
    ]
    contract_bound = len(contract_refs) == 1 and stored_payload(p, contract_refs[0], "lineage repair contract") == repair
    if not contract_bound and attempt.get("quarantine_reconciliation_ref"):
        receipt = stored_payload(p, attempt.get("quarantine_reconciliation_ref"), "lineage reconciliation receipt")
        receipt_contract_ref = receipt.get("repair_contract_ref")
        contract_bound = bool(
            receipt.get("authorization_ref") == authorization_ref
            and receipt.get("finding_ref") == finding_ref
            and stored_payload(p, receipt_contract_ref, "lineage reconciled repair contract") == repair
        )
    if not contract_bound:
        fail("repair lineage authorization is not bound to the exact repair contract")
    finding = next((item for item in state.get("findings", []) if item.get("id") == finding_ref), None)
    source_review = next(
        (
            item
            for item in state.get("attempts", [])
            if finding is not None and item.get("id") == finding.get("source_ref")
        ),
        None,
    )
    historical_candidate_binding = bool(
        finding
        and finding.get("impact") == "blocking"
        and source_review
        and source_review.get("kind") == "review"
        and source_review.get("subject_ref") == ticket_id
        and source_review.get("state") == "RETURNED"
        and source_review.get("candidate_sha") == candidate_sha
        and source_review.get("subject_fingerprint") in (None, candidate_sha)
        and finding_ref in source_review.get("finding_refs", [])
    )
    if not finding_matches_candidate(state, finding_ref, ticket_id, candidate_sha) and not historical_candidate_binding:
        fail("repair lineage finding is not a current blocking finding bound to its base candidate")
    return authorization_ref, finding_ref


def validated_repair_path_lineage(
    p: dict[str, Path],
    state: dict[str, Any],
    ticket: dict[str, Any],
    source_attempt: dict[str, Any],
    path: str,
    expected_candidate: str,
    seen: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Prove a continuous same-ticket candidate chain back to one validated create."""
    seen = set() if seen is None else set(seen)
    attempt_id = source_attempt.get("id")
    if attempt_id in seen:
        fail("repair lineage contains a provenance cycle")
    seen.add(attempt_id)
    if (
        source_attempt.get("kind") != "worker"
        or source_attempt.get("subject_ref") != ticket["id"]
        or source_attempt.get("state") != "RETURNED"
        or source_attempt.get("candidate_sha") != expected_candidate
        or source_attempt.get("lease", {}).get("state") == "quarantined"
    ):
        fail("repair lineage candidate is missing, foreign, stale, or quarantined")
    returned = stored_payload(p, source_attempt.get("return_ref"), "repair lineage worker return")
    root = schema()
    validate(returned, root["$defs"]["worker_return"], root, "$.lineage_return")
    identity = packet_identity(returned)
    if (
        identity.get("run_id") != state["run_id"]
        or identity.get("ticket_id") != ticket["id"]
        or identity.get("attempt_id") != attempt_id
        or identity.get("packet_hash") != source_attempt.get("packet_hash")
        or identity.get("epoch") != source_attempt.get("epoch")
        or returned.get("status") != "DONE"
    ):
        fail("repair lineage requires an exact validated DONE worker return")
    operations = {
        item.get("operation")
        for item in returned.get("files", [])
        if relative_path(item.get("path"), "repair lineage return path") == path
    }
    base_entry = {
        "attempt_ref": attempt_id,
        "ticket_ref": ticket["id"],
        "base_sha": source_attempt.get("base_sha"),
        "candidate_sha": source_attempt.get("candidate_sha"),
        "return_ref": source_attempt.get("return_ref"),
    }
    if operations == {"create"}:
        if (
            source_attempt.get("mode") != "implement"
            or not zone_allows(ticket.get("zone", []), path, "create")
            or not zone_allows(source_attempt.get("lease", {}).get("zone", []), path, "create")
        ):
            fail(f"repair lineage lacks an original validated same-ticket create: {path}")
        return [{**base_entry, "operation": "create"}]
    if operations not in (set(), {"modify"}) or source_attempt.get("mode") != "repair":
        fail(f"repair lineage does not continuously reach an original validated create: {path}")
    provenance = source_attempt.get("repair_lease_provenance")
    base_sha = source_attempt.get("base_sha")
    authorization_ref, finding_ref = historical_repair_authorization(
        p, state, ticket["id"], source_attempt, base_sha
    )
    if isinstance(provenance, dict):
        if provenance.get("packet_base_sha") != base_sha or provenance.get("candidate_sha") != base_sha:
            fail(f"repair lineage has a broken create-to-modify provenance edge: {path}")
        prior_ref = provenance.get("source_attempt_ref")
        prior = next((item for item in state.get("attempts", []) if item.get("id") == prior_ref), None)
    else:
        prior_candidates = [
            item
            for item in state.get("attempts", [])
            if item.get("kind") == "worker"
            and item.get("subject_ref") == ticket["id"]
            and item.get("candidate_sha") == base_sha
            and item.get("id") != attempt_id
        ]
        if len(prior_candidates) != 1:
            fail("repair lineage candidate/base SHA chain is missing, ambiguous, or forked")
        prior = prior_candidates[0]
    if operations == {"modify"} and (
        not isinstance(provenance, dict)
        or not zone_allows(provenance.get("expanded_entries", []), path, "modify")
        or not zone_allows(source_attempt.get("lease", {}).get("zone", []), path, "modify")
    ):
        fail(f"repair lineage has a broken create-to-modify provenance edge: {path}")
    if prior is None or prior.get("candidate_sha") != base_sha:
        fail("repair lineage candidate/base SHA chain is stale or forked")
    lineage = validated_repair_path_lineage(p, state, ticket, prior, path, base_sha, seen)
    lineage.append(
        {
            **base_entry,
            "operation": "modify" if operations else "preserve",
            "authorization_ref": authorization_ref,
            "finding_ref": finding_ref,
        }
    )
    return lineage


def effective_worker_lease(
    p: dict[str, Path], state: dict[str, Any], ticket: dict[str, Any], packet: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Derive a packet-scoped lease, with one provenance-bound repair exception."""
    requested = packet_write_zone(packet)
    ticket_zone = ticket.get("zone", [])
    repair = packet.get("repair") if packet.get("mode") == "repair" else None
    finding_ref = repair.get("finding_ref") if repair else None
    authorization = validate_repair_authorization(p, state, ticket["id"], repair) if repair else None

    disallowed = [
        {"path": entry["path"], "operation": operation}
        for entry in requested
        for operation in entry["operations"]
        if not zone_allows(ticket_zone, entry["path"], operation)
    ]
    if not disallowed:
        return requested, None
    if not repair:
        fail(f"packet write allowlist exceeds the ticket zone: {json.dumps(disallowed, sort_keys=True)}")

    packet_base = packet.get("workspace", {}).get("expected_base")
    source_attempt = repair_candidate_worker(state, ticket, repair, packet_base)
    source_attempt_ref = source_attempt["id"]
    if source_attempt.get("state") != "RETURNED" or not source_attempt.get("return_ref") or not source_attempt.get("candidate_sha"):
        fail("repair lease expansion requires a validated prior candidate attempt")
    if source_attempt.get("lease", {}).get("state") == "quarantined":
        fail("repair lease expansion cannot use quarantined prior provenance")
    if packet_base != source_attempt.get("candidate_sha"):
        fail("repair lease expansion base SHA is stale or does not match the prior candidate")
    if not finding_matches_candidate(state, finding_ref, ticket["id"], packet_base):
        fail("repair lease expansion finding is not bound to the prior candidate")

    expanded: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    for violation in disallowed:
        path, operation = violation["path"], violation["operation"]
        if operation != "modify" or not zone_allows(ticket_zone, path, "create"):
            fail(f"repair packet write allowlist lacks prior-create provenance: {path} ({operation})")
        denied = [relative_path(item, "packet write deny path").rstrip("/") for item in packet.get("write", {}).get("deny", [])]
        if any(path == item or path.startswith(item + "/") for item in denied):
            fail(f"repair lease expansion conflicts with packet deny list: {path}")
        attempts = validated_repair_path_lineage(
            p, state, ticket, source_attempt, path, packet_base
        )
        expanded.append({"path": path, "operations": ["modify"]})
        lineage.append({"path": path, "attempts": attempts})

    provenance = {
        "authorization_ref": authorization["id"],
        "finding_ref": finding_ref,
        "source_attempt_ref": source_attempt_ref,
        "candidate_sha": source_attempt["candidate_sha"],
        "packet_base_sha": packet_base,
        "expanded_entries": expanded,
        "lineage": lineage,
    }
    return requested, provenance


def review_criterion_id(record: dict[str, Any]) -> str:
    value = record.get("criterion_id", record.get("id"))
    return safe_id(value, "review criterion")


def validate_review_return_semantics(payload: dict[str, Any], packet: dict[str, Any]) -> None:
    packet_criteria = packet.get("criteria", [])
    required = [review_criterion_id(item) for item in packet_criteria]
    if len(required) != len(set(required)):
        fail("review packet has duplicate criteria")
    coverage = payload.get("coverage", [])
    coverage_ids = [review_criterion_id(item) for item in coverage]
    if len(coverage_ids) != len(set(coverage_ids)) or set(coverage_ids) != set(required):
        fail("review coverage must contain every packet criterion exactly once")
    if not payload.get("checks"):
        fail("review return requires non-empty independent checks")
    check_ids = ids_from_records(payload["checks"], "check_id", "review check")
    if any(not nonempty_string(item.get("evidence_ref"), "review check evidence_ref") for item in payload["checks"]):
        fail("review checks require evidence references")
    axes = packet.get("axes", [])
    if axes:
        if any(not item.get("axis") for item in payload["checks"]):
            fail("state-bound review checks require an explicit axis")
        checked_axes = {item["axis"] for item in payload["checks"]}
        if checked_axes != set(axes):
            fail(f"review return axes do not exactly match the packet: expected {sorted(set(axes))}, got {sorted(checked_axes)}")
    if not payload.get("context_refs"):
        fail("review return requires non-empty context evidence")
    if any(item.get("outcome") != "fulfilled" for item in coverage if payload.get("verdict") == "PASS"):
        fail("review PASS contains a non-fulfilled criterion")
    for finding in payload.get("findings", []):
        if finding.get("impact") == "blocking" and payload.get("verdict") == "PASS":
            fail("review PASS contains a blocking finding")
    if not check_ids:
        fail("review return has no usable checks")


def ledger_record_ids(state: dict[str, Any]) -> set[str]:
    result = {
        item["id"]
        for value in state.values()
        if isinstance(value, list)
        for item in value
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if isinstance(state.get("design_publication"), dict):
        result.add(state["design_publication"]["id"])
    return result


def validate_return_against_attempt(p: dict[str, Path], state: dict[str, Any], attempt: dict[str, Any], payload: dict[str, Any], kind: str) -> dict[str, Any]:
    """State-bound validation shared by reviewer preflight and ingest."""
    definition = {"worker": "worker_return", "review": "review_return", "acceptance": "acceptance_return"}.get(kind)
    if definition is None:
        fail(f"unsupported return kind: {kind}")
    root = schema()
    validate(payload, root["$defs"][definition], root, "$.return")
    validate_standalone_contract(payload, definition)
    identity = packet_identity(payload)
    if identity.get("run_id") != state["run_id"] or identity.get("attempt_id") != attempt["id"]:
        fail("return identity does not match the registered run/attempt")
    if identity.get("packet_hash") != attempt.get("packet_hash"):
        fail("return packet hash mismatch")
    if identity.get("epoch") != attempt.get("epoch") or attempt.get("epoch") != state["owner"]["epoch"]:
        fail("return epoch mismatch; stale payload has no current authority")
    packet = stored_payload(p, attempt.get("packet_ref"), f"{kind} packet")
    packet_id = packet_identity(packet)
    if kind == "worker":
        validate_worker_return_semantics(payload, packet)
    elif kind == "review":
        validate_review_return_semantics(payload, packet)

    packet_source = attempt.get("packet_source_revision", packet_id.get("source_revision"))
    packet_registration = attempt.get("packet_registration_revision", packet_id.get("registration_revision", packet_id.get("source_revision")))
    subject_revision = attempt.get("subject_revision", attempt.get("target_revision"))
    if packet_id.get("source_revision") is not None and identity.get("source_revision") != packet_source:
        fail("return source_revision does not match the immutable packet source revision")
    if packet_id.get("registration_revision") is not None and identity.get("registration_revision") != packet_registration:
        fail("return registration_revision does not match packet registration")
    if packet_id.get("subject_revision") is not None and identity.get("subject_revision") != subject_revision:
        fail("return subject_revision does not match the reviewed subject")
    if packet_id.get("intent_revision") is not None and identity.get("intent_revision") != attempt.get("intent_revision"):
        fail("return intent revision is stale")
    if packet_id.get("intent_document_ref") is not None and identity.get("intent_document_ref") != attempt.get("intent_document_ref"):
        fail("return intent document ref is stale")
    if packet_id.get("intent_document_hash") is not None and identity.get("intent_document_hash") != attempt.get("intent_document_hash"):
        fail("return intent document hash is stale")

    if kind == "review":
        if payload.get("subject_fingerprint") != attempt.get("subject_fingerprint", attempt.get("candidate_sha")):
            fail("review return subject fingerprint does not match the registered attempt")
        allowed_local = {review_criterion_id(item) for item in packet.get("criteria", [])}
        allowed_local.update(item.get("check_id") for item in payload.get("checks", []))
        allowed_local.update(packet.get("axes", []))
        known = ledger_record_ids(state)
        for finding in payload.get("findings", []):
            unknown = set(finding.get("affected_refs", [])) - known - allowed_local
            if unknown:
                fail(f"review finding contains refs outside ledger/packet scope: {sorted(unknown)}")
    return packet


def cmd_validate_return(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    state, _ = load_state(p)
    attempt = attempt_by_id(state, args.attempt_id)
    payload_path = Path(args.return_file).expanduser().resolve()
    payload = read_json(payload_path, "return")
    validate_return_against_attempt(p, state, attempt, payload, args.kind)
    return {
        "valid": True,
        "level": "state-bound",
        "kind": args.kind,
        "attempt_id": args.attempt_id,
        "packet_hash": attempt.get("packet_hash"),
        "subject_revision": attempt.get("subject_revision", attempt.get("target_revision")),
        "current_revision": state["revision"],
        "sha256": sha256_file(payload_path),
    }


def validate_acceptance_return_semantics(payload: dict[str, Any], required_ids: list[str]) -> None:
    outcomes = payload.get("outcomes", [])
    actual = [safe_id(item.get("criterion_id"), "acceptance criterion") for item in outcomes]
    if len(actual) != len(set(actual)) or set(actual) != set(required_ids):
        fail("acceptance outcomes must correspond exactly to active criteria")
    if not payload.get("checks"):
        fail("acceptance PASS requires non-empty independent checks")
    if any(not nonempty_string(item.get("evidence_ref"), "acceptance check evidence_ref") for item in payload.get("checks", [])):
        fail("acceptance checks require evidence references")
    if payload.get("verdict") == "PASS":
        if any(item.get("outcome") != "fulfilled" for item in outcomes):
            fail("acceptance PASS contains a non-fulfilled criterion")
        if any(item.get("impact") == "blocking" for item in payload.get("findings", [])):
            fail("acceptance PASS contains a blocking finding")


def validate_standalone_contract(value: dict[str, Any], kind: str) -> None:
    if kind == "worker_return":
        identity = packet_identity(value)
        if not HASH_RE.fullmatch(identity.get("packet_hash", "")) or not isinstance(identity.get("epoch"), int) or isinstance(identity.get("epoch"), bool):
            fail("worker_return identity requires packet_hash and owner epoch")
        checks = value.get("checks", [])
        criteria = value.get("criteria", [])
        ids_from_records(checks, "check_id", "worker check")
        ids_from_records(criteria, "criterion_id", "worker criterion")
        if value.get("status") == "DONE" and any(item.get("outcome") != "pass" for item in checks):
            fail("DONE worker return requires all checks to pass")
    elif kind == "review_return":
        identity = packet_identity(value)
        if not HASH_RE.fullmatch(identity.get("packet_hash", "")) or not isinstance(identity.get("epoch"), int) or isinstance(identity.get("epoch"), bool):
            fail("review_return identity requires packet_hash and owner epoch")
        coverage_ids = [review_criterion_id(item) for item in value.get("coverage", [])]
        if len(coverage_ids) != len(set(coverage_ids)):
            fail("review coverage contains duplicate criteria")
        if value.get("verdict") == "PASS" and any(item.get("outcome") != "fulfilled" for item in value.get("coverage", [])):
            fail("review PASS requires fulfilled coverage")
    elif kind == "acceptance_return":
        identity = packet_identity(value)
        if not HASH_RE.fullmatch(identity.get("packet_hash", "")) or not isinstance(identity.get("epoch"), int) or isinstance(identity.get("epoch"), bool):
            fail("acceptance_return identity requires packet_hash and owner epoch")
        outcome_ids = [safe_id(item.get("criterion_id"), "acceptance criterion") for item in value.get("outcomes", [])]
        if len(outcome_ids) != len(set(outcome_ids)):
            fail("acceptance outcomes contain duplicate criteria")
        if value.get("verdict") == "PASS" and any(item.get("outcome") != "fulfilled" for item in value.get("outcomes", [])):
            fail("acceptance PASS requires fulfilled outcomes")
    elif kind == "design_bundle":
        validate_design_bundle(value)


def ingest_payload(p: dict[str, Path], state: dict[str, Any], attempt_id: str, payload_path: Path, expected_packet_hash: str | None = None, kind: str | None = None) -> tuple[dict[str, Any], str]:
    payload_path = inbox_file(p, attempt_id, payload_path)
    raw = payload_path.read_bytes()
    payload = read_json(payload_path, "return")
    identity = packet_identity(payload)
    if identity.get("attempt_id") != attempt_id:
        fail("return attempt_id does not match exact inbox attempt")
    if expected_packet_hash and identity.get("packet_hash") != expected_packet_hash:
        fail("return packet hash mismatch")
    if identity.get("run_id") not in (None, state["run_id"]):
        fail("return run_id mismatch")
    if kind:
        definition = {"worker": "worker_return", "review": "review_return", "acceptance": "acceptance_return"}.get(kind)
        if definition:
            root = schema()
            validate(payload, root["$defs"][definition], root, "$.return")
            if kind == "worker":
                attempt = attempt_by_id(state, attempt_id)
                packet = stored_payload(p, attempt.get("packet_ref"), "worker packet")
                validate_worker_return_semantics(payload, packet)
            elif kind == "review":
                attempt = attempt_by_id(state, attempt_id)
                packet = stored_payload(p, attempt.get("packet_ref"), "review packet")
                validate_review_return_semantics(payload, packet)
    digest = object_store(p, raw)
    return payload, digest


def append_issue(state: dict[str, Any], issue: dict[str, Any], *, source_ref: str | None = None, finding_ref: str | None = None) -> str:
    issue_id = issue.get("id") if isinstance(issue.get("id"), str) and issue.get("id") else f"issue-{sha256_bytes(canonical_bytes(issue))[:16]}"
    safe_id(issue_id, "issue_id")
    if issue_id in {item.get("id") for item in state.get("issues", [])}:
        issue_id = f"{issue_id}-{len(state.get('issues', [])) + 1}"
    cause = issue.get("cause", "unknown")
    if cause not in CAUSES:
        cause = "unknown"
    record = {"id": issue_id, "type": issue.get("type", "ingested_issue"), "cause": cause, "impact": issue.get("impact", "blocking"), "affected_refs": issue.get("affected_refs", []), "expected": issue.get("expected"), "actual": issue.get("actual"), "disposition": issue.get("disposition", "requires disposition"), "resolution_condition": issue.get("resolution_condition"), "owner": issue.get("owner"), "failure_signature": issue.get("failure_signature"), "finding_ref": finding_ref, "source_ref": source_ref, "intent_revision": state.get("intent", {}).get("current_revision"), "invalidated_by": []}
    state.setdefault("issues", []).append(record)
    return issue_id


def append_review_findings(state: dict[str, Any], payload: dict[str, Any], source_ref: str, digest: str, *, packet: dict[str, Any] | None = None, subject_ref: str | None = None) -> list[str]:
    refs: list[str] = []
    known = ledger_record_ids(state)
    packet_local: set[str] = set()
    if packet:
        packet_local.update(review_criterion_id(item) for item in packet.get("criteria", []))
        packet_local.update(packet.get("axes", []))
        packet_local.update(item.get("check_id") for item in payload.get("checks", []))
    for index, finding in enumerate(payload.get("findings", [])):
        finding_id = f"finding-{digest[:12]}-{index + 1}"
        reported_refs = finding.get("affected_refs", [])
        canonical_refs = [ref for ref in reported_refs if ref in known]
        if any(ref in packet_local and ref not in known for ref in reported_refs) and subject_ref:
            canonical_refs.append(subject_ref)
        canonical_refs = sorted(set(canonical_refs or ([subject_ref] if subject_ref else [])))
        record = {"id": finding_id, "axis": finding.get("axis", "unknown"), "impact": finding.get("impact", "advisory"), "claim": finding.get("claim", "ingested finding"), "expected": finding.get("expected", ""), "actual": finding.get("actual", ""), "evidence": finding.get("evidence", "return evidence"), "affected_refs": canonical_refs, "reported_affected_refs": reported_refs, "source_ref": source_ref, "intent_revision": state.get("intent", {}).get("current_revision"), "repair_contract_ref": None, "invalidated_by": []}
        if finding_id in {item.get("id") for item in state.get("findings", [])}:
            refs.append(finding_id)
            continue
        state.setdefault("findings", []).append(record)
        refs.append(finding_id)
        if record["impact"] == "blocking":
            append_issue(state, {"type": "review_finding", "cause": "unknown", "impact": "blocking", "affected_refs": record["affected_refs"], "expected": record["expected"], "actual": record["actual"], "disposition": "requires repair or adjudication", "resolution_condition": "finding independently resolved"}, source_ref=source_ref, finding_ref=finding_id)
    return refs


def base_state(control_root: Path, run_id: str, repo_root: Path, token: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "revision": 0, "previous_publication_hash": None,
        "updated_at": now(), "skill_version": SKILL_VERSION, "policy_version": POLICY_VERSION,
        "runtime_provenance": {"creation_skill_version": SKILL_VERSION, "current_schema_version": SCHEMA_VERSION, "last_mutating_skill_version": SKILL_VERSION, "compatibility_floor": COMPATIBILITY_FLOOR, "applied_migrations": []},
        "repository": {"control_root": str(control_root), "execution_root": str(repo_root), "common_dir": "", "initial_head": None, "branch": "", "checkout": str(repo_root), "inventory_ref": None, "instruction_refs": []},
        "owner": {"token": token, "epoch": 0, "observed_session": None, "handoff_ref": None, "attestation_ref": None},
        "run_settings": dict(DEFAULT_RUN_SETTINGS),
        "usage": default_usage(),
        "lifecycle": {"phase": "PREFLIGHT", "control": "ACTIVE", "reason": None, "issue_refs": [], "stop_target": None, "next_action": {"kind": "preflight", "subject_refs": [], "preconditions": [], "read_refs": ["phases/start.md"]}},
    }


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    if not Path(args.repo_root).exists():
        fail("execution root does not exist")
    with Lock(p["lock"]):
        if p["ledger"].exists():
            fail("run already exists; use status/resume/recover instead of overwrite")
        runs_root = p["base"] / "runs"
        if runs_root.exists():
            for other in sorted(runs_root.iterdir()):
                other_ledger = other / "ledger.json"
                if not other_ledger.exists() or other.name == args.run_id:
                    continue
                other_state = read_json(other_ledger, "existing run ledger")
                validate_ledger(other_state)
                if other_state["lifecycle"]["control"] not in ("ACCEPTED", "FAILED", "CANCELLED"):
                    fail(f"another nonterminal run owns this repository: {other.name}")
        p["run"].mkdir(parents=True, exist_ok=False)
        state = base_state(p["root"], args.run_id, safe_root(args.repo_root, "execution root"), args.owner_token)
        state["run_settings"] = run_settings_from_args(args.request, args.interaction_mode, args.depth)
        validate_ledger(state)
        atomic_write(p["ledger"], canonical_bytes(state))
        result = copy.deepcopy(state)
        result["display"] = run_settings_display(state["run_settings"])
        return result


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    state, raw = load_state(p)
    if args.brief:
        lifecycle = state["lifecycle"]
        usage = copy.deepcopy(state.get("usage", default_usage()))
        binding = {"revision": state.get("intent", {}).get("current_revision"), "document_ref": state.get("intent", {}).get("document_ref"), "document_hash": state.get("intent", {}).get("document_hash")}
        settings = resolved_run_settings(state)
        brief = {"run_id": state["run_id"], "revision": state["revision"], "phase": lifecycle["phase"], "control": lifecycle["control"], "reason": lifecycle.get("reason"), "next_action": lifecycle["next_action"], "run_settings": settings, "preset_display": run_settings_display(settings), "issues": [i["id"] for i in state.get("issues", []) if i.get("impact") == "blocking" and not i.get("invalidated_by")], "findings": [f["id"] for f in state.get("findings", [])], "finding_status": [{"id": f["id"], "impact": f.get("impact"), "current": not bool(f.get("invalidated_by"))} for f in state.get("findings", [])], "reviews": [{"id": r.get("id"), "subject": r.get("subject_fingerprint"), "verdict": r.get("verdict"), "review_kind": r.get("review_kind"), "reviewer_identity": r.get("reviewer_identity"), "reviewer_role": r.get("reviewer_role"), "current": not bool(r.get("invalidated_by")), "finding_refs": r.get("finding_refs", [])} for r in state.get("reviews", [])], "design_publication": state.get("design_publication"), "design_publication_history": state.get("design_publication_history", []), "requirements_publications": state.get("requirements_publications", []), "design_review_attempts": [{"id": a.get("id"), "kind": a.get("mode"), "state": a.get("state"), "result": a.get("review_result"), "reviewer_identity": a.get("reviewer_identity"), "reviewer_role": a.get("reviewer_role")} for a in state.get("attempts", []) if a.get("mode") in ("coverage", "plan")], "adjudications": [d.get("id") for d in state.get("decisions", []) if d.get("type") == "reviewer_adjudication"], "intent": binding, "version_provenance": state.get("runtime_provenance", {"creation_skill_version": state.get("skill_version"), "current_schema_version": state.get("schema_version"), "last_mutating_skill_version": state.get("skill_version"), "compatibility_floor": COMPATIBILITY_FLOOR, "applied_migrations": []}), "consumer_invalidation_count": len(state.get("invalidations", [])), "usage": usage, "evidence_count": len(state.get("evidence", [])), "ledger_bytes": len(raw), "ledger_hash": sha256_bytes(raw)}
        brief["usage"]["counters"]["brief_bytes"] = len(canonical_bytes(brief))
        return brief
    settings = resolved_run_settings(state)
    current_blockers = [
        item["id"] for item in state.get("issues", [])
        if item.get("impact") == "blocking" and not item.get("invalidated_by")
    ]
    current_findings = [item for item in state.get("findings", []) if not item.get("invalidated_by")]
    return {"run_id": state["run_id"], "revision": state["revision"], "phase": state["lifecycle"]["phase"], "control": state["lifecycle"]["control"], "next_action": state["lifecycle"]["next_action"], "run_settings": settings, "preset_display": run_settings_display(settings), "ticket_counts": {s: sum(1 for t in state.get("tickets", []) if t.get("state") == s) for s in ("PLANNED", "READY", "RUNNING", "CANDIDATE", "REVIEW", "INTEGRATED", "BLOCKED", "STALE")}, "attempts": len(state.get("attempts", [])), "blockers": current_blockers, "finding_counts": {"current": len(current_findings), "historical": len(state.get("findings", [])) - len(current_findings), "total": len(state.get("findings", []))}, "ledger_hash": sha256_bytes(raw)}


def cmd_publish_usage(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    event_path = Path(args.event_file).expanduser().resolve()
    event = read_json(event_path, "usage event")
    root = schema()
    validate(event, root["$defs"]["usage_event"], root, "$.usage_event")
    raw = event_path.read_bytes()
    event_ref = f"objects/{object_store(p, raw)}"
    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        usage = state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage()); usage.setdefault("trace", []); usage.setdefault("shared_setup", zero_usage()); usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        if event["id"] in {item.get("id") for item in usage["trace"]}:
            fail("usage event ID already published")
        delta = event["delta"]
        add_usage(usage["counters"], delta)
        scope = event.get("scope", "run")
        if scope == "shared_setup":
            add_usage(usage["shared_setup"], delta)
        elif scope.startswith("G"):
            add_usage(usage["gate_costs"].setdefault(scope, zero_usage()), delta)
        token_reason = event.get("token_reason")
        if event.get("tokens") is None:
            usage["tokens"] = None
            usage["token_reason"] = token_reason or "token_meter_unavailable"
            usage["unknown_reason"] = usage["token_reason"]
        else:
            usage["tokens"] = event["tokens"]
            usage["token_reason"] = token_reason
            usage["unknown_reason"] = None
        usage["trace"].append({"id": event["id"], "kind": event["kind"], "actor": event["actor"], "subject_ref": event.get("subject_ref"), "delta": delta, "evidence_ref": event_ref, "recorded_at": now()})
        for item in event.get("evidence", []):
            evidence_id = item["id"]
            if evidence_id in {record.get("id") for record in state.get("evidence", [])}:
                continue
            state.setdefault("evidence", []).append({"id": evidence_id, "hash": item["hash"], "source": "usage_publication", "scenario": item.get("scenario"), "outcome": item["outcome"], "observer": item["observer"], "subject": event.get("subject_ref")})
        state["revision"] += 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        publish(p, state, previous_raw, "usage")
    return {"published": True, "event_id": event["id"], "event_ref": event_ref, "scope": event.get("scope", "run"), "tokens": state["usage"].get("tokens"), "token_reason": state["usage"].get("token_reason"), "revision": state["revision"]}


def cmd_render_view(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    state, raw = load_state(p)
    source_hash = sha256_bytes(raw)
    lifecycle = state["lifecycle"]
    blocking = [item["id"] for item in state.get("issues", []) if item.get("impact") == "blocking" and not item.get("invalidated_by")]
    settings = resolved_run_settings(state)
    lines = [f"# Autopilot {args.kind}", "", f"- Run: `{state['run_id']}`", f"- Source revision: `{state['revision']}`", f"- Source ledger SHA-256: `{source_hash}`", f"- Phase/control: `{lifecycle['phase']} × {lifecycle['control']}`", f"- {run_settings_display(settings)}", f"- Next action: `{lifecycle['next_action']['kind']}`"]
    if blocking:
        lines.extend(["", "## Blocking issues", "", *[f"- `{item}`" for item in blocking]])
    if args.kind == "final-report":
        acceptances = state.get("acceptance", [])
        latest = acceptances[-1] if acceptances else None
        lines.extend(["", "## Candidate and acceptance", "", f"- Candidate: `{(latest or {}).get('candidate_fingerprint', 'unknown')}`", f"- Intent revision: `{(latest or {}).get('intent_revision', 'unknown')}`", f"- Acceptance transport: `{(latest or {}).get('transport', 'not_recorded')}`", f"- Context grade: `{(latest or {}).get('context_grade', 'not_recorded')}`", "- Exclusions and unverifiable criteria remain blocking unless explicitly amended."])
    output = p["run"] / "views" / f"{args.kind}.md"
    atomic_write(output, ("<!-- generated: ledger.py; not authoritative state -->\n\n" + "\n".join(lines) + "\n").encode("utf-8"))
    return {"generated": str(output), "source_revision": state["revision"], "source_hash": source_hash}


def cmd_validate(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.file).expanduser().resolve()
    value = read_json(target, "contract")
    root = schema()
    if args.kind == "ledger":
        validate_ledger(value)
    else:
        defs = root.get("$defs", {})
        if args.kind not in defs:
            fail(f"unknown schema definition: {args.kind}")
        validate(value, defs[args.kind], root, "$")
        validate_standalone_contract(value, args.kind)
    return {"valid": True, "kind": args.kind, "sha256": sha256_file(target)}


def cmd_diagnose(args: argparse.Namespace) -> dict[str, Any]:
    """Read-only header/hash diagnostic that never upgrades unknown schemas."""
    p = paths(args.control_root, args.run_id)
    regular_non_symlink(p["ledger"])
    raw = p["ledger"].read_bytes()
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return {"read_only": True, "supported": False, "reason": f"corrupt ledger: {exc}", "ledger_hash": sha256_bytes(raw)}
    schema_version = state.get("schema_version")
    supported = schema_version == SCHEMA_VERSION
    result = {"read_only": True, "supported": supported, "schema_version": schema_version, "supported_schema_version": SCHEMA_VERSION, "run_id": state.get("run_id"), "revision": state.get("revision"), "creation_skill_version": state.get("skill_version"), "runtime_provenance": state.get("runtime_provenance"), "ledger_hash": sha256_bytes(raw)}
    if not supported:
        result["reason"] = "unknown schema; mutation is forbidden"
        return result
    try:
        validate_ledger(state)
        result["valid"] = True
    except LedgerError as exc:
        result["valid"] = False
        result["reason"] = str(exc)
    return result


def cmd_ingest(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        attempt = attempt_by_id(state, args.attempt_id)
        return_path = inbox_file(p, args.attempt_id, Path(args.return_file))
        proposed_digest = sha256_file(return_path)
        if attempt.get("state") == "RETURNED":
            if attempt.get("return_ref") == f"objects/{proposed_digest}":
                return {"ingested": True, "idempotent": True, "attempt_id": args.attempt_id, "return_ref": attempt["return_ref"], "status": attempt.get("review_result", "RETURNED"), "revision": state["revision"]}
            fail("conflicting duplicate return for a terminal attempt")
        if attempt.get("state") in ("LOST", "INTERRUPTED"):
            fail("return conflicts with a terminal lost/interrupted attempt")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        payload, digest = ingest_payload(p, state, args.attempt_id, Path(args.return_file), attempt.get("packet_hash"), args.kind)
        identity = packet_identity(payload)
        packet = validate_return_against_attempt(p, state, attempt, payload, args.kind)
        if args.kind == "review" and attempt.get("mode") in ("coverage", "plan"):
            publication = current_design_publication(state)
            if attempt.get("subject_ref") != publication.get("id") or attempt.get("subject_fingerprint") != publication.get("publication_hash") or payload.get("subject_fingerprint") != publication.get("publication_hash"):
                fail("design review return is not bound to the current published bundle")
            if identity.get("intent_revision") not in (None, publication.get("intent_revision")):
                fail("design review return intent revision is stale")
        next_state = copy.deepcopy(state)
        target = attempt_by_id(next_state, args.attempt_id)
        target["state"] = "RETURNED"
        target["return_ref"] = f"objects/{digest}"
        target["return_source_revision"] = identity.get("source_revision", target.get("packet_source_revision"))
        if args.kind == "review":
            target["review_result"] = payload.get("verdict")
            # Reviewer returns terminate reviewer write authority atomically.
            if target.get("lease", {}).get("state") == "active":
                target["lease"]["state"] = "released"
        target["finding_refs"] = append_review_findings(next_state, payload, args.attempt_id, digest, packet=packet if args.kind == "review" else None, subject_ref=target.get("subject_ref"))
        write_set_violations = worker_return_write_set_violations(payload, attempt.get("lease", {})) if args.kind == "worker" else []
        if write_set_violations:
            issue_id = append_issue(next_state, {
                "id": f"write-set-{digest[:12]}",
                "type": "write_set_violation",
                "cause": "ownership",
                "impact": "blocking",
                "affected_refs": [target.get("subject_ref"), args.attempt_id],
                "expected": "worker return files remain within the active lease zone and allowed operations",
                "actual": json.dumps(write_set_violations, sort_keys=True),
                "disposition": "quarantine lease and reconcile actual checkout ownership before retry",
                "resolution_condition": "actual write set audited and a fresh scoped attempt is authorized",
            }, source_ref=args.attempt_id)
            target["finding_refs"].append(issue_id)
            target["lease"]["state"] = "quarantined"
        if payload.get("status") in ("BLOCKED", "FAILED", "HANDOFF") or write_set_violations:
            for issue in payload.get("issues", []):
                issue_id = append_issue(next_state, issue, source_ref=args.attempt_id)
                if issue_id not in target["finding_refs"]:
                    target["finding_refs"].append(issue_id)
            ticket = next((item for item in next_state.get("tickets", []) if item.get("id") == target.get("subject_ref")), None)
            if ticket and ticket.get("state") not in ("CANCELLED", "STALE"):
                ticket["state"] = "BLOCKED"
            next_state["lifecycle"]["control"] = "BLOCKED"
            next_state["lifecycle"]["reason"] = f"{args.kind}_{payload.get('status').lower()}"
            next_state["lifecycle"]["issue_refs"] = sorted(set(next_state["lifecycle"].get("issue_refs", []) + target["finding_refs"]))
            next_state["lifecycle"]["next_action"] = {"kind": "triage_or_repair", "subject_refs": [args.attempt_id], "preconditions": ["durable cause/finding contract", "no unchanged retry"], "read_refs": ["phases/execute.md", "references/routing.md"]}
        elif args.kind == "worker" and payload.get("status") == "DONE":
            next_state["lifecycle"]["next_action"] = {
                "kind": "audit_worker_return_and_prepare_candidate",
                "subject_refs": [args.attempt_id],
                "preconditions": ["worker stopped", "actual write set audited", "candidate effect prepared"],
                "read_refs": ["phases/execute.md", "references/safety.md"],
            }
        if args.kind == "review":
            review_id = f"REV-{digest[:16]}"
            if review_id not in {item.get("id") for item in next_state.get("reviews", [])}:
                review = {"id": review_id, "mandate": stored_payload(p, target.get("packet_ref"), "review packet").get("mandate", "review"), "subject_fingerprint": payload.get("subject_fingerprint", ""), "verdict": payload.get("verdict"), "return_ref": f"objects/{digest}", "context_refs": payload.get("context_refs", []), "finding_refs": target["finding_refs"], "intent_revision": next_state.get("intent", {}).get("current_revision"), "reviewer_identity": target.get("reviewer_identity"), "reviewer_role": target.get("reviewer_role"), "review_kind": target.get("mode") if target.get("mode") in ("coverage", "plan") else None, "target_artifact_refs": target.get("target_artifact_refs", []), "target_artifact_versions": target.get("target_artifact_versions", []), "target_revision": target.get("target_revision"), "invalidated_by": []}
                next_state.setdefault("reviews", []).append(review)
            current_review = next(item for item in next_state.get("reviews", []) if item.get("id") == review_id)
            prior = [
                item for item in next_state.get("reviews", [])
                if item.get("subject_fingerprint") == current_review.get("subject_fingerprint")
                and item.get("review_kind") == current_review.get("review_kind")
                and item.get("mandate") == current_review.get("mandate")
                and item.get("target_revision") == current_review.get("target_revision")
                and not item.get("invalidated_by")
            ]
            verdicts = {item.get("verdict") for item in prior}
            if len(verdicts) > 1:
                disagreement = append_issue(next_state, {"id": f"disagreement-{digest[:12]}", "type": "reviewer_disagreement", "cause": "oracle", "impact": "blocking", "affected_refs": [target.get("subject_ref"), *[item.get("id") for item in prior]], "expected": "reviewers agree or adjudication is recorded", "actual": json.dumps(sorted(str(item) for item in verdicts)), "disposition": "adjudication required", "resolution_condition": "durable adjudication decision"}, source_ref=review_id)
                next_state["lifecycle"]["control"] = "BLOCKED"
                next_state["lifecycle"]["reason"] = "reviewer_disagreement"
                next_state["lifecycle"]["issue_refs"] = sorted(set(next_state["lifecycle"].get("issue_refs", []) + [disagreement]))
                next_state["lifecycle"]["next_action"] = {"kind": "adjudicate_review_disagreement", "subject_refs": [item.get("id") for item in prior], "preconditions": ["read all reviewer findings", "record evidence-backed decision"], "read_refs": ["contracts/reviewer.md", "references/routing.md"]}
            elif payload.get("verdict") in ("BLOCK", "UNVERIFIABLE"):
                issue_id = append_issue(next_state, {"id": f"review-{digest[:12]}-block", "type": "review_verdict", "cause": "oracle", "impact": "blocking", "affected_refs": [target.get("subject_ref")], "expected": "PASS", "actual": payload.get("verdict"), "disposition": "repair or adjudication required", "resolution_condition": "new evidence or adjudication"}, source_ref=review_id)
                next_state["lifecycle"]["control"] = "BLOCKED"
                next_state["lifecycle"]["reason"] = "review_not_pass"
                next_state["lifecycle"]["issue_refs"] = sorted(set(next_state["lifecycle"].get("issue_refs", []) + [issue_id]))
        evidence = next_state.setdefault("evidence", [])
        if not any(e.get("id") == f"ev-{digest[:16]}" for e in evidence):
            evidence.append({"id": f"ev-{digest[:16]}", "hash": digest, "source": "validated_return", "scenario": args.kind, "outcome": "RETURNED", "observer": "ledger-helper", "subject": args.attempt_id})
        add_usage(next_state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"return_bytes": len(canonical_bytes(payload))})
        next_state["revision"] += 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        publish(p, next_state, previous_raw)
    return {"ingested": True, "idempotent": False, "attempt_id": args.attempt_id, "return_ref": f"objects/{digest}", "status": "BLOCKED" if write_set_violations else payload.get("status", payload.get("verdict")), "quarantined": bool(write_set_violations), "revision": next_state["revision"]}


def cmd_dispatch(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    packet_path = Path(args.packet).expanduser().resolve()
    packet = read_json(packet_path, "worker/reviewer packet")
    identity = packet_identity(packet)
    if identity.get("ticket_id") != args.ticket_id or identity.get("attempt_id") != args.attempt_id:
        fail("dispatch packet identity does not match ticket/attempt")
    if identity.get("run_id") != args.run_id:
        fail("dispatch packet identity does not match run")
    packet_raw = packet_path.read_bytes()
    packet_kind = packet.get("kind")
    if packet_kind == "worker":
        root = schema()
        validate(packet, root["$defs"][f"{packet_kind}_packet"], root, "$.packet")
        if packet.get("mode") == "repair":
            repair = packet.get("repair")
            if not isinstance(repair, dict):
                fail("repair packet requires a durable repair contract")
            validate(repair, root["$defs"]["repair_contract"], root, "$.packet.repair")
    else:
        fail("dispatch is only for worker packets; reviewer attempts use prepare-review")
    packet_hash = object_store(p, packet_raw)
    route = read_json(Path(args.route), "route") if args.route else None
    if route is not None:
        root = schema()
        validate(route, root["$defs"]["route"], root, "$.route")
        validate_route_eligibility(route)
        if route.get("id") not in (None, args.route_id):
            fail("route ID does not match dispatch route-id")
    observed, _ = load_state(p)
    if observed["owner"]["token"] != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    existing_attempt = next((item for item in observed.get("attempts", []) if item.get("id") == args.attempt_id), None)
    if existing_attempt:
        if existing_attempt.get("packet_hash") == packet_hash and existing_attempt.get("subject_ref") == args.ticket_id and existing_attempt.get("route_ref") == args.route_id:
            return {"prepared": True, "idempotent": True, "attempt_id": args.attempt_id, "packet_hash": packet_hash, "revision": observed["revision"]}
        fail("attempt ID already exists with conflicting dispatch")
    def change(state: dict[str, Any]) -> None:
        ticket = next((t for t in state.get("tickets", []) if t.get("id") == args.ticket_id), None)
        if ticket is None:
            fail("dispatch references unknown ticket")
        if ticket.get("state") != "READY":
            fail(f"ticket is not READY: {ticket.get('state')}")
        if route:
            validate_route_eligibility(route)
        if identity.get("epoch") != state["owner"]["epoch"]:
            fail("dispatch packet epoch does not match current owner")
        if any(a.get("id") == args.attempt_id for a in state.get("attempts", [])):
            fail("attempt ID already exists")
        if any(t.get("state") in ("RUNNING", "CANDIDATE", "REVIEW") and t.get("id") != args.ticket_id for t in state.get("tickets", [])):
            fail("serial V1 product writer already active")
        binding = current_intent_binding(state) if state.get("intent") else None
        packet_intent = packet.get("intent_revision") or identity.get("intent_revision")
        if binding and packet_intent and packet_intent != binding["revision"]:
            fail("dispatch packet intent revision is stale")
        if binding and packet.get("intent_document_hash") and packet.get("intent_document_hash") != binding["document_hash"]:
            fail("dispatch packet intent document hash is stale")
        repair = packet.get("repair")
        if packet.get("mode") == "repair" and repair:
            if repair.get("finding_ref") not in {item.get("id") for item in state.get("findings", [])} and repair.get("finding_ref") not in {item.get("id") for item in state.get("issues", [])}:
                fail("repair contract references an unknown finding")
            signature = repair_signature(repair)
            prior = [attempt for attempt in state.get("attempts", []) if attempt.get("subject_ref") == args.ticket_id and attempt.get("repair_contract")]
            if any(attempt.get("failure_signature") == signature or repair_signature(attempt["repair_contract"]) == signature for attempt in prior):
                fail("unchanged repair retry rejected: no causally meaningful change")
        for dependency in ticket.get("dependency_refs", []):
            dep = next(t for t in state.get("tickets", []) if t["id"] == dependency)
            if dep.get("state") != "INTEGRATED":
                fail(f"dependency is not current INTEGRATED: {dependency}")
        lease_zone, repair_lease_provenance = effective_worker_lease(p, state, ticket, packet)
        lease = {"id": args.lease_id, "state": "active", "zone": lease_zone}
        attempt_record = {"id": args.attempt_id, "kind": packet.get("kind", "worker"), "mode": packet.get("mode", "implement"), "subject_ref": args.ticket_id, "packet_ref": f"objects/{packet_hash}", "packet_hash": packet_hash, "epoch": state["owner"]["epoch"], "state": "PREPARED", "lease": lease, "route_ref": args.route_id, "checkout": packet.get("workspace", {}).get("root"), "base_sha": packet.get("workspace", {}).get("expected_base"), "candidate_sha": None, "candidate_tree_sha": None, "return_ref": None, "finding_refs": []}
        if binding:
            attempt_record.update({"intent_revision": binding["revision"], "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"]})
        if repair:
            attempt_record["repair_contract"] = repair
            attempt_record["failure_signature"] = repair_signature(repair)
            attempt_record["repair_authorization_ref"] = active_repair_authorization(state, args.ticket_id, repair["finding_ref"])["id"]
        if repair_lease_provenance:
            attempt_record["repair_lease_provenance"] = repair_lease_provenance
        state.setdefault("attempts", []).append(attempt_record)
        add_usage(state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"packet_bytes": len(packet_raw), "spawn_calls": 1})
        ticket["state"] = "RUNNING"
        ticket["current_attempt"] = args.attempt_id
        if route:
            route_record = dict(route)
            route_record.setdefault("id", args.route_id)
            state.setdefault("routes", []).append(route_record)
        state["lifecycle"]["next_action"] = {"kind": "await_worker_return", "subject_refs": [args.attempt_id], "preconditions": ["internal orchestration wait; not a user checkpoint", "native child started", "bounded no-progress waits", "return matches packet"], "read_refs": ["contracts/worker.md", "phases/execute.md", "phases/recover.md"]}
    result = transaction(p, args.owner_token, args.revision, change)
    return {"prepared": True, "idempotent": False, "attempt_id": args.attempt_id, "packet_hash": packet_hash, "revision": result["revision"]}


def cmd_ready_ticket(args: argparse.Namespace) -> dict[str, Any]:
    def change(state: dict[str, Any]) -> None:
        if state["lifecycle"]["phase"] != "EXECUTE" or state["lifecycle"]["control"] != "ACTIVE":
            fail("ticket readiness requires ACTIVE EXECUTE")
        publication = current_design_publication(state)
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == args.ticket_id), None)
        if ticket is None or ticket.get("id") not in publication.get("ticket_refs", []):
            fail("ticket is not part of the current design publication")
        if ticket.get("state") != "PLANNED":
            fail(f"ticket readiness requires PLANNED, got {ticket.get('state')}")
        for dependency in ticket.get("dependency_refs", []):
            dependency_ticket = next(item for item in state.get("tickets", []) if item.get("id") == dependency)
            if dependency_ticket.get("state") != "INTEGRATED":
                fail(f"dependency is not reviewed INTEGRATED: {dependency}")
        active_criteria = {item["id"] for item in state.get("criteria", []) if item.get("status") == "active" and not item.get("invalidated_by")}
        active_contracts = {item["id"] for item in state.get("contracts", []) if item.get("status") == "active" and not item.get("invalidated_by")}
        if not ticket.get("criterion_refs") or not set(ticket["criterion_refs"]).issubset(active_criteria):
            fail("ticket readiness requires current criterion bindings")
        if not set(ticket.get("contract_refs", [])).issubset(active_contracts):
            fail("ticket readiness requires current contract bindings")
        ticket["state"] = "READY"
        state["lifecycle"]["next_action"] = {"kind": "dispatch_ticket", "subject_refs": [args.ticket_id], "preconditions": ["fresh packet and attempt", "lease zone available"], "read_refs": ["phases/execute.md", "contracts/worker.md"]}
    result = transaction(paths(args.control_root, args.run_id), args.owner_token, args.revision, change, "ticket-ready")
    return {"ready": True, "ticket_id": args.ticket_id, "revision": result["revision"]}


def cmd_authorize_repair(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    contract = read_json(Path(args.repair_contract).expanduser().resolve(), "repair contract")
    root = schema()
    validate(contract, root["$defs"]["repair_contract"], root, "$.repair_contract")
    if contract.get("finding_ref") != args.finding_ref:
        fail("repair contract finding_ref does not match the command")
    contract_ref = f"objects/{object_store(p, canonical_bytes(contract))}"

    def change(state: dict[str, Any]) -> None:
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == args.ticket_id), None)
        legacy_authorization = active_repair_authorization(state, args.ticket_id, args.finding_ref) if ticket else None
        legacy_rebind = bool(
            ticket
            and ticket.get("state") == "READY"
            and legacy_authorization
            and not any(isinstance(ref, str) and ref.startswith("objects/") for ref in legacy_authorization.get("evidence_refs", []))
            and not any(item.get("repair_authorization_ref") == legacy_authorization.get("id") for item in state.get("attempts", []))
        )
        if ticket is None or (ticket.get("state") not in ("REVIEW", "BLOCKED", "REPAIR") and not legacy_rebind):
            fail("repair authorization requires a REVIEW/BLOCKED/REPAIR ticket")
        known_findings = {item.get("id") for item in state.get("findings", [])} | {item.get("id") for item in state.get("issues", [])}
        if args.finding_ref not in known_findings:
            fail("repair authorization references an unknown finding/issue")
        finding = next((item for item in state.get("findings", []) if item.get("id") == args.finding_ref), None)
        issue = next((item for item in state.get("issues", []) if item.get("id") == args.finding_ref), None)
        record = finding or issue
        if record.get("impact") != "blocking" or record.get("invalidated_by"):
            fail("repair authorization requires a current blocking finding/issue")
        if args.ticket_id not in record.get("affected_refs", []):
            fail("repair authorization finding/issue is not bound to this ticket")
        if any(item.get("id") == args.authorization_id for item in state.get("decisions", [])):
            fail("repair authorization ID already exists")
        for attempt in state.get("attempts", []):
            if attempt.get("subject_ref") == args.ticket_id and attempt.get("state") in ("PREPARED", "DISPATCHED"):
                fail("repair authorization requires stopped attempts")
            if attempt.get("subject_ref") == args.ticket_id and attempt.get("lease", {}).get("state") == "quarantined":
                fail("repair authorization requires quarantine reconciliation")
            if attempt.get("subject_ref") == args.ticket_id and attempt.get("lease", {}).get("state") == "active":
                attempt["lease"]["state"] = "released"
        state.setdefault("decisions", []).append({"id": args.authorization_id, "type": "repair_authorization", "status": "authorized", "decision": "REPAIR", "reason": contract["hypothesis"], "evidence_refs": [args.finding_ref, contract_ref], "affected_refs": [args.ticket_id, args.finding_ref], "intent_revision": state.get("intent", {}).get("current_revision"), "invalidated_by": []})
        if finding is not None:
            finding["repair_contract_ref"] = args.authorization_id
        ticket["state"] = "READY"
        state["lifecycle"]["control"] = "ACTIVE"
        state["lifecycle"]["reason"] = "repair_authorized"
        state["lifecycle"]["next_action"] = {"kind": "dispatch_repair", "subject_refs": [args.ticket_id, args.finding_ref], "preconditions": ["fresh attempt ID", "causally changed repair contract", "dependencies remain INTEGRATED"], "read_refs": ["phases/execute.md", "references/routing.md"]}

    result = transaction(p, args.owner_token, args.revision, change, "repair-authorized")
    return {"authorized": True, "authorization_id": args.authorization_id, "ticket_id": args.ticket_id, "finding_ref": args.finding_ref, "revision": result["revision"]}


def cmd_terminate_attempt(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    evidence_path = Path(args.evidence).expanduser().resolve()
    evidence = read_json(evidence_path, "attempt termination evidence")
    evidence_raw = evidence_path.read_bytes()
    evidence_digest = object_store(p, evidence_raw)
    if args.lease_state == "released" and (evidence.get("status") != "PASS" or evidence.get("writer_stopped") is not True):
        fail("lease release requires PASS writer_stopped evidence")

    def change(state: dict[str, Any]) -> None:
        attempt = attempt_by_id(state, args.attempt_id)
        if attempt.get("state") not in ("PREPARED", "DISPATCHED"):
            fail("only an in-flight attempt may be terminated")
        if attempt.get("epoch") != state["owner"]["epoch"] and args.lease_state == "released":
            fail("stale-epoch attempt may only be quarantined until takeover reconciliation")
        attempt["state"] = args.state
        attempt["lease"]["state"] = args.lease_state
        ticket = next((item for item in state.get("tickets", []) if item.get("current_attempt") == args.attempt_id), None)
        if ticket and ticket.get("state") not in ("INTEGRATED", "CANCELLED", "STALE"):
            ticket["state"] = "BLOCKED"
        ev_id = f"ev-{evidence_digest[:16]}"
        if ev_id not in {item.get("id") for item in state.get("evidence", [])}:
            state.setdefault("evidence", []).append({"id": ev_id, "hash": evidence_digest, "source": "attempt_termination", "scenario": args.state, "outcome": args.lease_state, "observer": "ledger-helper", "subject": args.attempt_id})
        issue_id = append_issue(state, {"id": f"attempt-{args.attempt_id}-{args.state.lower()}", "type": "attempt_termination", "cause": "orchestration", "impact": "blocking", "affected_refs": [args.attempt_id, *([ticket["id"]] if ticket else [])], "expected": "bounded attempt returns or is stopped with evidence", "actual": args.state, "disposition": "recover/retry with a fresh attempt after lease reconciliation", "resolution_condition": "released lease and fresh attempt"}, source_ref=args.attempt_id)
        state["lifecycle"]["control"] = "BLOCKED"
        state["lifecycle"]["reason"] = f"attempt_{args.state.lower()}"
        state["lifecycle"]["issue_refs"] = sorted(set(state["lifecycle"].get("issue_refs", []) + [issue_id]))
        state["lifecycle"]["next_action"] = {"kind": "recover_attempt", "subject_refs": [args.attempt_id], "preconditions": ["lease released or quarantine reconciled", "fresh attempt ID"], "read_refs": ["phases/recover.md", "references/ledger.md"]}

    result = transaction(p, args.owner_token, args.revision, change, "attempt-terminated")
    return {"terminated": True, "attempt_id": args.attempt_id, "state": args.state, "lease_state": args.lease_state, "evidence_ref": f"objects/{evidence_digest}", "revision": result["revision"]}


def cmd_candidate(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    receipt = read_json(Path(args.commit_receipt), "Git candidate receipt")
    if receipt.get("status") != "PASS" or not GIT_SHA_RE.fullmatch(receipt.get("commit_sha", "")) or not GIT_SHA_RE.fullmatch(receipt.get("tree_sha", "")):
        fail("candidate requires PASS receipt with commit_sha and tree_sha")
    observed, _ = load_state(p)
    if observed["owner"]["token"] != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    observed_attempt = attempt_by_id(observed, args.attempt_id)
    observed_operation = next((item for item in observed.get("operations", []) if item.get("id") == args.operation_id), None)
    observed_ticket = next((item for item in observed.get("tickets", []) if item.get("id") == observed_attempt.get("subject_ref")), None)
    if observed_attempt.get("candidate_sha") == receipt["commit_sha"] and observed_attempt.get("candidate_tree_sha") == receipt["tree_sha"] and observed_operation and observed_operation.get("state") == "applied" and observed_ticket and observed_ticket.get("state") in ("CANDIDATE", "REVIEW", "INTEGRATED"):
        return {"candidate": receipt["commit_sha"], "idempotent": True, "revision": observed["revision"], "next_action": observed["lifecycle"]["next_action"]}
    def change(state: dict[str, Any]) -> None:
        attempt = attempt_by_id(state, args.attempt_id)
        if attempt["state"] != "RETURNED":
            fail("candidate requires a validated RETURNED worker attempt")
        if attempt.get("kind") != "worker":
            fail("candidate requires a worker attempt")
        if attempt.get("lease", {}).get("state") != "active":
            fail("candidate requires an active, non-quarantined worker lease")
        worker_return = stored_payload(p, attempt.get("return_ref"), "worker return")
        if worker_return.get("status") != "DONE":
            fail("only a semantically complete worker DONE return may become a candidate; BLOCKED/FAILED/HANDOFF are durable non-candidate outcomes")
        if receipt.get("base_sha") and attempt.get("base_sha") and receipt["base_sha"] != attempt["base_sha"]:
            fail("candidate base SHA mismatch")
        operation = next((item for item in state.get("operations", []) if item.get("id") == args.operation_id), None)
        if operation is None:
            fail("candidate requires a durable prepared operation; call prepare-effect before the Git effect")
        if operation.get("kind") != "candidate_commit":
            fail("candidate requires a prepared candidate_commit operation")
        if operation.get("state") != "prepared":
            fail("candidate operation is not in prepared state")
        if operation.get("intended_after") not in (None, receipt["commit_sha"]):
            fail("candidate receipt does not match prepared operation")
        attempt["candidate_sha"] = receipt["commit_sha"]
        attempt["candidate_tree_sha"] = receipt["tree_sha"]
        attempt["state"] = "RETURNED"
        ticket = next((t for t in state.get("tickets", []) if t.get("id") == attempt.get("subject_ref")), None)
        if ticket:
            ticket["state"] = "CANDIDATE"
        operation["state"] = "applied"
        operation["target"] = receipt.get("checkout", operation.get("target", ""))
        operation["expected_before"] = receipt.get("base_sha", operation.get("expected_before"))
        operation["intended_after"] = receipt["commit_sha"]
        operation["authority_ref"] = receipt.get("authority_ref", operation.get("authority_ref"))
        operation["receipt_ref"] = receipt.get("receipt_ref") or f"external:{args.operation_id}"
        state["lifecycle"]["next_action"] = {"kind": "review_change", "subject_refs": [args.attempt_id], "preconditions": ["candidate SHA frozen", "integrity baseline recorded"], "read_refs": ["contracts/reviewer.md", "references/safety.md"]}
    result = transaction(p, args.owner_token, args.revision, change)
    return {"candidate": receipt["commit_sha"], "idempotent": False, "revision": result["revision"], "next_action": result["lifecycle"]["next_action"]}


def cmd_prepare_effect(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    observed, _ = load_state(p)
    if observed["owner"]["token"] != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    existing = next((item for item in observed.get("operations", []) if item.get("id") == args.operation_id), None)
    proposed = {"kind": args.kind, "target": args.target, "expected_before": args.expected_before, "intended_after": args.intended_after, "authority_ref": args.authority_ref}
    if existing:
        if all(existing.get(key) == value for key, value in proposed.items()):
            return {"prepared": True, "idempotent": True, "operation_id": args.operation_id, "revision": observed["revision"], "state": existing.get("state")}
        fail("operation ID already exists with conflicting parameters")
    def change(state: dict[str, Any]) -> None:
        safe_id(args.operation_id, "operation_id")
        if any(item.get("id") == args.operation_id for item in state.get("operations", [])):
            fail("operation ID already exists")
        state.setdefault("operations", []).append({"id": args.operation_id, "kind": args.kind, "target": args.target, "state": "prepared", "expected_before": args.expected_before, "intended_after": args.intended_after, "authority_ref": args.authority_ref, "receipt_ref": None})
        state["lifecycle"]["next_action"] = {"kind": "apply_prepared_effect", "subject_refs": [args.operation_id], "preconditions": ["native approved effect", "same target and expected-before", "receipt or reconciliation evidence"], "read_refs": ["references/ledger.md", "references/safety.md"]}
    result = transaction(p, args.owner_token, args.revision, change, "effect-prepared")
    return {"prepared": True, "idempotent": False, "operation_id": args.operation_id, "revision": result["revision"], "state": "prepared"}


def cmd_reconcile_effect(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    receipt = None
    receipt_ref = None
    if args.receipt:
        receipt_path = Path(args.receipt).expanduser().resolve()
        receipt = read_json(receipt_path, "effect receipt")
        receipt_ref = f"objects/{object_store(p, receipt_path.read_bytes())}"
    observed, _ = load_state(p)
    if observed["owner"]["token"] != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    observed_operation = next((item for item in observed.get("operations", []) if item.get("id") == args.operation_id), None)
    if observed_operation and observed_operation.get("state") == args.result and observed_operation.get("receipt_ref") == receipt_ref:
        return {"reconciled": True, "idempotent": True, "operation_id": args.operation_id, "state": args.result, "revision": observed["revision"]}
    def change(state: dict[str, Any]) -> None:
        operation = next((item for item in state.get("operations", []) if item.get("id") == args.operation_id), None)
        if operation is None:
            fail("unknown operation")
        if operation.get("state") != "prepared":
            fail("only a prepared operation can be reconciled")
        if receipt:
            if receipt.get("operation_id") not in (None, args.operation_id):
                fail("effect receipt operation mismatch")
            if receipt.get("target") not in (None, operation.get("target")):
                fail("effect receipt target mismatch")
            if operation.get("expected_before") and receipt.get("base_sha") not in (None, operation.get("expected_before")):
                fail("effect receipt expected-before mismatch")
            commit_sha = receipt.get("commit_sha")
            if commit_sha:
                if not GIT_SHA_RE.fullmatch(commit_sha):
                    fail("effect receipt has invalid commit SHA")
                target = Path(operation.get("target", ""))
                regular_directory(target, "effect target")
                try:
                    actual_head = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
                    actual_tree = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip()
                except (OSError, subprocess.CalledProcessError) as exc:
                    fail(f"effect reconciliation cannot inspect Git target: {exc}")
                if actual_head != commit_sha or (receipt.get("tree_sha") and actual_tree != receipt.get("tree_sha")):
                    fail("effect receipt does not match actual Git target")
        if args.result == "applied":
            if not receipt:
                fail("applied reconciliation requires an exact effect receipt")
            operation["state"] = "applied"
            operation["receipt_ref"] = receipt_ref
            state["lifecycle"]["next_action"] = {"kind": "resume_after_effect_reconciliation", "subject_refs": [args.operation_id], "preconditions": ["re-read current ledger", "verify resulting subject"], "read_refs": ["phases/recover.md", "references/ledger.md"]}
        elif args.result == "uncertain":
            operation["state"] = "uncertain"
            operation["receipt_ref"] = receipt_ref
            state["lifecycle"]["control"] = "BLOCKED"
            state["lifecycle"]["reason"] = "uncertain_effect_requires_authority_resolution"
            state["lifecycle"]["next_action"] = {"kind": "reconcile_uncertain_effect", "subject_refs": [args.operation_id], "preconditions": ["inspect actual target", "do not repeat effect"], "read_refs": ["phases/recover.md", "references/safety.md"]}
        else:
            operation["state"] = "abandoned"
            operation["receipt_ref"] = receipt_ref
            state["lifecycle"]["next_action"] = {"kind": "decide_effect_retry", "subject_refs": [args.operation_id], "preconditions": ["same operation ID", "fresh authority and expected-before check"], "read_refs": ["references/safety.md"]}
    result = transaction(p, args.owner_token, args.revision, change, "effect-reconciled")
    return {"reconciled": True, "idempotent": False, "operation_id": args.operation_id, "state": next(item for item in result.get("operations", []) if item.get("id") == args.operation_id)["state"], "revision": result["revision"]}


def cmd_prepare_review(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    packet_path = Path(args.packet).expanduser().resolve()
    packet = read_json(packet_path, "review packet")
    root = schema()
    validate(packet, root["$defs"]["review_packet"], root, "$.packet")
    identity = packet_identity(packet)
    if identity.get("run_id") not in (None, args.run_id) or identity.get("attempt_id") != args.review_attempt_id:
        fail("review packet identity does not match review attempt")
    packet_hash = object_store(p, packet_path.read_bytes())
    def change(state: dict[str, Any]) -> None:
        ticket = next((t for t in state.get("tickets", []) if t.get("id") == args.ticket_id), None)
        if ticket is None or ticket.get("state") not in ("CANDIDATE", "REVIEW"):
            fail("review preparation requires a CANDIDATE or REVIEW ticket")
        worker = next((a for a in state.get("attempts", []) if a.get("id") == ticket.get("current_attempt") and a.get("kind") == "worker"), None)
        if worker is None or not worker.get("candidate_sha"):
            fail("review preparation requires a frozen worker candidate")
        if packet.get("subject_fingerprint") != worker.get("candidate_sha"):
            fail("review packet subject is not the current candidate")
        registration_revision = identity.get("registration_revision", identity.get("source_revision", state["revision"]))
        if registration_revision != state["revision"]:
            fail("review packet registration revision is stale")
        if identity.get("subject_revision") not in (None, worker.get("attempt_created_revision"), state["revision"]):
            fail("review packet subject revision is stale")
        binding = current_intent_binding(state) if state.get("intent") else None
        packet_intent = identity.get("intent_revision")
        if binding and packet_intent and packet_intent != binding["revision"]:
            fail("review packet intent revision is stale")
        if binding and identity.get("intent_document_hash") and identity.get("intent_document_hash") != binding["document_hash"]:
            fail("review packet intent document hash is stale")
        if any(a.get("id") == args.review_attempt_id for a in state.get("attempts", [])):
            fail("review attempt ID already exists")
        attempt_record = {"id": args.review_attempt_id, "kind": "review", "mode": "change", "subject_ref": args.ticket_id, "packet_ref": f"objects/{packet_hash}", "packet_hash": packet_hash, "epoch": state["owner"]["epoch"], "state": "PREPARED", "lease": {"id": args.lease_id, "state": "active", "zone": []}, "route_ref": None, "checkout": None, "base_sha": worker.get("candidate_sha"), "candidate_sha": worker.get("candidate_sha"), "candidate_tree_sha": worker.get("candidate_tree_sha"), "return_ref": None, "finding_refs": [], "subject_fingerprint": worker.get("candidate_sha"), "packet_registration_revision": registration_revision, "packet_source_revision": identity.get("source_revision", registration_revision), "subject_revision": identity.get("subject_revision", state["revision"]), "attempt_created_revision": state["revision"] + 1, "return_source_revision": None}
        if binding:
            attempt_record.update({"intent_revision": binding["revision"], "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"]})
        state.setdefault("attempts", []).append(attempt_record)
        add_usage(state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"packet_bytes": packet_path.stat().st_size, "spawn_calls": 1})
        ticket["state"] = "REVIEW"
        state["lifecycle"]["next_action"] = {"kind": "await_review_return", "subject_refs": [args.review_attempt_id], "preconditions": ["reviewer stopped", "integrity baseline unchanged", "strict packet/subject match"], "read_refs": ["contracts/reviewer.md", "phases/execute.md"]}
    result = transaction(p, args.owner_token, args.revision, change)
    return {"prepared": True, "attempt_id": args.review_attempt_id, "packet_hash": packet_hash, "revision": result["revision"]}


def cmd_prepare_design_review(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    packet_path = Path(args.packet).expanduser().resolve()
    packet = read_json(packet_path, "design review packet")
    root = schema()
    validate(packet, root["$defs"]["review_packet"], root, "$.packet")
    identity = packet_identity(packet)
    if identity.get("run_id") not in (None, args.run_id) or identity.get("attempt_id") != args.review_attempt_id:
        fail("design review packet identity does not match review attempt")
    if args.review_kind not in ("coverage", "plan"):
        fail("design review kind must be coverage or plan")
    reviewer_identity = nonempty_string(args.reviewer_identity, "reviewer identity")
    reviewer_role = nonempty_string(args.reviewer_role, "reviewer role")
    packet_hash = object_store(p, packet_path.read_bytes())

    def change(state: dict[str, Any]) -> None:
        if state["lifecycle"]["phase"] != "DESIGN" and not (args.review_kind == "plan" and state["lifecycle"]["phase"] == "PLAN"):
            fail("design review preparation requires DESIGN phase (or PLAN for a plan review)")
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        publication = current_design_publication(state)
        if packet.get("subject_fingerprint") != publication.get("publication_hash"):
            fail("design review packet subject is not the current published bundle")
        packet_criteria = {review_criterion_id(item) for item in packet.get("criteria", [])}
        required_criteria = set(publication.get("criterion_refs", []))
        if required_criteria and packet_criteria != required_criteria:
            fail("design review packet criteria do not exactly match the current publication")
        if args.review_kind not in set(packet.get("axes", [])):
            fail("design review packet axes do not include its registered review kind")
        binding = current_intent_binding(state)
        if identity.get("epoch") != state["owner"]["epoch"]:
            fail("design review packet epoch does not match current owner")
        registration_revision = identity.get("registration_revision", identity.get("source_revision"))
        if registration_revision != state["revision"]:
            fail("design review packet registration revision is stale")
        if identity.get("source_revision") not in (None, registration_revision):
            fail("legacy source_revision must equal packet registration revision")
        if identity.get("subject_revision") not in (None, publication.get("published_revision")):
            fail("design review packet subject revision is stale")
        if identity.get("intent_revision") not in (None, binding["revision"]):
            fail("design review packet intent revision is stale")
        if identity.get("intent_document_ref") not in (None, binding["document_ref"]):
            fail("design review packet intent document ref is stale")
        if identity.get("intent_document_hash") not in (None, binding["document_hash"]):
            fail("design review packet intent document hash is stale")
        existing_attempt = next((item for item in state.get("attempts", []) if item.get("id") == args.review_attempt_id), None)
        if existing_attempt:
            if existing_attempt.get("packet_hash") == packet_hash and existing_attempt.get("mode") == args.review_kind and existing_attempt.get("subject_ref") == publication.get("id") and existing_attempt.get("reviewer_identity") == reviewer_identity and existing_attempt.get("reviewer_role") == reviewer_role:
                raise IdempotentResult({"prepared": True, "idempotent": True, "attempt_id": args.review_attempt_id, "review_kind": args.review_kind, "packet_hash": packet_hash, "revision": state["revision"]})
            fail("review attempt ID already exists with conflicting registration")
        target_refs = [*publication["document_refs"], *publication["contract_refs"], *publication["ticket_refs"], *publication["route_refs"]]
        documents = {item["id"]: item for item in state.get("documents", [])}
        target_versions = [{"ref": ref, "version": documents[ref]["version"]} for ref in publication["document_refs"]]
        target_versions.extend({"ref": ref, "version": next(item for item in state.get("contracts", []) if item["id"] == ref)["version"]} for ref in publication["contract_refs"])
        target_versions.extend({"ref": ref, "version": "ledger"} for ref in [*publication["ticket_refs"], *publication["route_refs"]])
        attempt_record = {
            "id": args.review_attempt_id, "kind": "review", "mode": args.review_kind, "subject_ref": publication["id"], "packet_ref": f"objects/{packet_hash}", "packet_hash": packet_hash,
            "epoch": state["owner"]["epoch"], "state": "PREPARED", "lease": {"id": args.lease_id, "state": "active", "zone": []}, "route_ref": None,
            "checkout": None, "base_sha": None, "candidate_sha": None, "candidate_tree_sha": None, "return_ref": None, "finding_refs": [],
            "reviewer_identity": reviewer_identity, "reviewer_role": reviewer_role, "subject_fingerprint": publication["publication_hash"], "target_artifact_refs": target_refs,
            "target_artifact_versions": target_versions, "target_revision": publication["published_revision"],
            "packet_registration_revision": registration_revision, "packet_source_revision": identity.get("source_revision", registration_revision),
            "subject_revision": publication["published_revision"], "attempt_created_revision": state["revision"] + 1, "return_source_revision": None, "review_result": None,
            "intent_revision": binding["revision"], "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"],
        }
        state.setdefault("attempts", []).append(attempt_record)
        add_usage(state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"packet_bytes": packet_path.stat().st_size, "spawn_calls": 1})
        state["lifecycle"]["next_action"] = {"kind": "await_design_review_return", "subject_refs": [args.review_attempt_id, publication["id"]], "preconditions": ["reviewer identity/role registered", "reviewer stopped", "exact bundle fingerprint and revision"], "read_refs": ["contracts/reviewer.md", "phases/design.md", "references/ledger.md"]}

    observed, _ = load_state(p)
    if observed["owner"]["token"] != args.owner_token:
        fail("owner token mismatch; stale orchestrator is fenced")
    observed_attempt = next((item for item in observed.get("attempts", []) if item.get("id") == args.review_attempt_id), None)
    if observed_attempt and observed_attempt.get("packet_hash") == packet_hash and observed_attempt.get("mode") == args.review_kind and observed_attempt.get("reviewer_identity") == reviewer_identity and observed_attempt.get("reviewer_role") == reviewer_role:
        return {"prepared": True, "idempotent": True, "attempt_id": args.review_attempt_id, "review_kind": args.review_kind, "packet_hash": packet_hash, "revision": observed["revision"]}
    try:
        result = transaction(p, args.owner_token, args.revision, change)
    except IdempotentResult as prior:
        return prior.result
    return {"prepared": True, "attempt_id": args.review_attempt_id, "review_kind": args.review_kind, "packet_hash": packet_hash, "revision": result["revision"]}


def cmd_adjudicate(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    decision = read_json(Path(args.decision_file).expanduser().resolve(), "adjudication decision")
    root = schema()
    validate(decision, root["$defs"]["decision"], root, "$.decision")
    if decision.get("type") != "reviewer_adjudication":
        fail("adjudication decision type must be reviewer_adjudication")
    if decision.get("decision") not in ("PASS", "BLOCK", "UNVERIFIABLE"):
        fail("adjudication decision must be PASS, BLOCK, or UNVERIFIABLE")
    if not decision.get("reason") or not decision.get("evidence_refs"):
        fail("adjudication requires a reason and evidence references")
    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if decision["id"] in {item.get("id") for item in state.get("decisions", [])}:
            fail("decision ID already exists")
        review_ids = set(decision.get("supersedes", []))
        reviews = [item for item in state.get("reviews", []) if item.get("id") in review_ids]
        if review_ids and len(reviews) != len(review_ids):
            fail("adjudication supersedes an unknown review")
        if not reviews:
            issue_refs = set(state.get("lifecycle", {}).get("issue_refs", []))
            if not any(item.get("type") == "reviewer_disagreement" and item.get("id") in issue_refs for item in state.get("issues", [])):
                fail("adjudication must name conflicting reviews in supersedes")
        binding = current_intent_binding(state) if state.get("intent") else None
        record = dict(decision)
        record["introduced_revision"] = str(state["revision"] + 1)
        record["intent_revision"] = binding["revision"] if binding else None
        state.setdefault("decisions", []).append(record)
        for issue in state.get("issues", []):
            if issue.get("type") == "reviewer_disagreement" and (not review_ids or set(issue.get("affected_refs", [])) & review_ids):
                issue["decision_ref"] = decision["id"]
                issue["disposition"] = "resolved by adjudication" if decision["decision"] == "PASS" else "adjudicated BLOCK"
        if decision["decision"] == "PASS":
            state["lifecycle"]["control"] = "ACTIVE"
            state["lifecycle"]["reason"] = "reviewer_disagreement_adjudicated"
            state["lifecycle"]["next_action"] = {"kind": "continue_after_adjudication", "subject_refs": sorted(review_ids), "preconditions": ["re-read adjudication evidence", "candidate remains unchanged"], "read_refs": ["contracts/reviewer.md", "references/routing.md"]}
        else:
            state["lifecycle"]["control"] = "BLOCKED"
            state["lifecycle"]["reason"] = "reviewer_disagreement_adjudicated_not_pass"
            state["lifecycle"]["next_action"] = {"kind": "repair_or_user_decision", "subject_refs": sorted(review_ids), "preconditions": ["durable repair contract or new intent authority"], "read_refs": ["phases/execute.md", "phases/intent.md", "references/routing.md"]}
        state["lifecycle"]["issue_refs"] = [ref for ref in state["lifecycle"].get("issue_refs", []) if not any(item.get("id") == ref and item.get("type") == "reviewer_disagreement" and decision["decision"] == "PASS" for item in state.get("issues", []))]
        state["revision"] += 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        publish(p, state, previous_raw, "adjudication")
    return {"adjudicated": True, "decision_id": decision["id"], "decision": decision["decision"], "revision": state["revision"]}


def cmd_integrate(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    integrity = read_json(Path(args.integrity_receipt), "integrity receipt")
    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        attempt = attempt_by_id(state, args.attempt_id)
        if attempt.get("kind") != "review" or attempt.get("mode") == "user_assisted":
            fail("integration requires a separate immutable reviewer attempt")
        existing_review = next((item for item in state.get("reviews", []) if item.get("id") == args.review_id), None)
        if existing_review is not None:
            ticket = next((t for t in state.get("tickets", []) if t.get("id") == attempt.get("subject_ref")), None)
            worker = next((item for item in state.get("attempts", []) if item.get("id") == (ticket or {}).get("current_attempt") and item.get("kind") == "worker"), None)
            if existing_review.get("verdict") != "PASS" or existing_review.get("subject_fingerprint") != attempt.get("candidate_sha"):
                fail("existing integration review does not match this candidate")
            if ticket is None or ticket.get("state") != "INTEGRATED" or worker is None or worker.get("candidate_sha") != attempt.get("candidate_sha"):
                fail("existing integration state does not match this candidate")
            if attempt.get("lease", {}).get("state") not in ("active", "released") or worker.get("lease", {}).get("state") not in ("active", "released"):
                fail("existing integration has a non-releasable lease state")
            if attempt.get("lease", {}).get("state") == "released" and worker.get("lease", {}).get("state") == "released":
                return {"integrated": True, "idempotent": True, "revision": state["revision"]}
            next_state = copy.deepcopy(state)
            next_attempt = attempt_by_id(next_state, args.attempt_id)
            next_worker = attempt_by_id(next_state, worker["id"])
            next_attempt["lease"]["state"] = "released"
            next_worker["lease"]["state"] = "released"
            next_state["revision"] += 1
            next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
            next_state["updated_at"] = now()
            publish(p, next_state, previous_raw)
            return {"integrated": True, "idempotent": True, "reconciled": True, "revision": next_state["revision"]}
        if attempt.get("state") not in ("PREPARED", "RETURNED"):
            fail("review attempt is not active")
        packet = stored_payload(p, attempt.get("packet_ref"), "review packet")
        review, digest = ingest_payload(p, state, args.attempt_id, Path(args.review_file), attempt.get("packet_hash"), "review")
        validate_return_against_attempt(p, state, attempt, review, "review")
        if review.get("verdict") != "PASS":
            fail("integration requires reviewer PASS; BLOCK/UNVERIFIABLE remains outside integration")
        if integrity.get("status") != "PASS" or integrity.get("candidate_fingerprint") not in (None, attempt.get("candidate_sha")):
            fail("independent integrity barrier did not PASS for candidate")
        if integrity.get("ledger_hash") not in (None, sha256_file(p["ledger"])):
            fail("authoritative ledger changed before review ingest")
        subject = review.get("subject_fingerprint")
        if subject != attempt.get("candidate_sha"):
            fail("review subject is not this candidate")
        if packet.get("subject_fingerprint") != attempt.get("candidate_sha"):
            fail("review packet subject is not this candidate")
        if not packet.get("mandate"):
            fail("review packet lacks an explicit mandate")
        if args.review_id in {item.get("id") for item in state.get("reviews", [])}:
            fail("review ID already exists")
        next_state = copy.deepcopy(state)
        next_attempt = attempt_by_id(next_state, args.attempt_id)
        next_attempt["return_ref"] = f"objects/{digest}"
        next_attempt["finding_refs"] = append_review_findings(next_state, review, args.attempt_id, digest, packet=packet, subject_ref=next_attempt.get("subject_ref"))
        next_attempt["lease"]["state"] = "released"
        next_attempt["state"] = "RETURNED"
        next_attempt["return_source_revision"] = packet_identity(review).get("source_revision", next_attempt.get("packet_source_revision"))
        ticket = next((t for t in next_state.get("tickets", []) if t.get("id") == next_attempt.get("subject_ref")), None)
        if ticket:
            worker = next((item for item in next_state.get("attempts", []) if item.get("id") == ticket.get("current_attempt") and item.get("kind") == "worker"), None)
            if worker is None or worker.get("candidate_sha") != next_attempt.get("candidate_sha"):
                fail("integration requires the linked worker candidate")
            if worker.get("lease", {}).get("state") not in ("active", "released"):
                fail("linked worker lease is not releasable")
            worker["lease"]["state"] = "released"
            ticket["state"] = "INTEGRATED"
            repair_ref = worker.get("repair_contract", {}).get("finding_ref")
            if repair_ref:
                for issue in next_state.get("issues", []):
                    if issue.get("id") == repair_ref or issue.get("finding_ref") == repair_ref or (issue.get("type") in ("review_verdict", "review_finding") and ticket["id"] in issue.get("affected_refs", [])):
                        issue["impact"] = "advisory"
                        issue["disposition"] = f"resolved by reviewed repair {args.review_id}"
                        if args.review_id not in issue.setdefault("invalidated_by", []):
                            issue["invalidated_by"].append(args.review_id)
                for finding in next_state.get("findings", []):
                    if finding.get("id") == repair_ref and args.review_id not in finding.setdefault("invalidated_by", []):
                        finding["invalidated_by"].append(args.review_id)
                next_state["lifecycle"]["issue_refs"] = [ref for ref in next_state["lifecycle"].get("issue_refs", []) if next((item for item in next_state.get("issues", []) if item.get("id") == ref), {}).get("impact") == "blocking"]
                if not next_state["lifecycle"]["issue_refs"]:
                    next_state["lifecycle"]["control"] = "ACTIVE"
                    next_state["lifecycle"]["reason"] = "reviewed_repair_integrated"
        review_id = args.review_id
        next_state.setdefault("reviews", []).append({"id": review_id, "mandate": packet.get("mandate", "change"), "subject_fingerprint": subject, "verdict": "PASS", "return_ref": f"objects/{digest}", "context_refs": review.get("context_refs", []), "finding_refs": next_attempt["finding_refs"], "intent_revision": next_state.get("intent", {}).get("current_revision"), "invalidated_by": []})
        next_state["revision"] += 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        publish(p, next_state, previous_raw)
    return {"integrated": True, "attempt_id": args.attempt_id, "review_ref": f"objects/{digest}", "revision": next_state["revision"]}


def git_output(root: Path, *command: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *command], check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(f"write audit cannot inspect Git root: {exc}")


def git_paths(root: Path, *command: str) -> list[str]:
    return [
        item
        for item in git_output(root, *command).decode("utf-8", "surrogateescape").split("\0")
        if item
    ]


def git_tree_baseline(root: Path, base_sha: str) -> dict[str, Any]:
    """Build a complete fingerprint manifest from an exact committed Git tree."""
    raw = git_output(root, "ls-tree", "-r", "-z", "--full-tree", base_sha)
    files: list[dict[str, Any]] = []
    for token in (item for item in raw.split(b"\0") if item):
        header, separator, encoded_path = token.partition(b"\t")
        if not separator:
            fail("Git tree baseline contains a malformed entry")
        try:
            mode, object_type, object_id = header.decode("ascii").split(" ", 2)
            path = relative_path(encoded_path.decode("utf-8", "surrogateescape"), "Git tree path")
        except (UnicodeError, ValueError) as exc:
            fail(f"Git tree baseline contains an invalid entry: {exc}")
        if object_type != "blob":
            fail(f"Git tree baseline contains unsupported {object_type}: {path}")
        content = git_output(root, "cat-file", "blob", object_id)
        if mode == "120000":
            target = content.decode("utf-8", "surrogateescape")
            resolved = (root / path).parent.joinpath(target).resolve(strict=False)
            files.append({"path": path, "type": "symlink", "target": target, "target_inside_root": under(resolved, root)})
        else:
            file_mode = 0o755 if mode == "100755" else 0o644
            files.append({"path": path, "type": "file", "mode": file_mode, "sha256": sha256_bytes(content)})
    return {"base_sha": base_sha, "source": "git_tree", "files": files}


def audit_write_set(
    root: Path, baseline: dict[str, Any], declared: list[Any], zones: list[dict[str, Any]]
) -> dict[str, Any]:
    """Inspect the complete checkout and return a deterministic write-set receipt."""

    def status_paths() -> tuple[set[str], set[str]]:
        tokens = git_paths(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        found: set[str] = set()
        renamed: set[str] = set()
        index = 0
        while index < len(tokens):
            record = tokens[index]
            value = record[3:] if len(record) >= 3 else record
            if value:
                found.add(value)
            if len(record) >= 2 and record[:2] in ("R ", " R", "RR", "C ", " C", "CC") and index + 1 < len(tokens):
                renamed.add(tokens[index + 1])
                found.add(tokens[index + 1])
                index += 1
            index += 1
        return found, renamed

    baseline_entries = baseline.get("files", baseline.get("paths", []))
    baseline_map: dict[str, dict[str, Any] | None] = {}
    for item in baseline_entries:
        if isinstance(item, dict):
            baseline_map[relative_path(item.get("path"), "baseline path")] = item
        else:
            baseline_map[relative_path(item, "baseline path")] = None
    declared_paths = {
        relative_path(item.get("path"), "declared path")
        if isinstance(item, dict)
        else relative_path(item, "declared path")
        for item in declared
    }
    declared_operations = {
        relative_path(item.get("path"), "declared path"): item.get("operation")
        for item in declared
        if isinstance(item, dict) and item.get("operation")
    }
    zone_paths = [relative_path(item.get("path"), "zone path") for item in zones]

    tracked = set(git_paths(root, "ls-files", "-z"))
    status, renamed = status_paths()
    ignored = set(git_paths(root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"))
    actual: set[str] = tracked | status | ignored

    def fingerprint(rel: str) -> dict[str, Any] | None:
        path = root / rel
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            resolved = (path.parent / target).resolve(strict=False)
            return {"path": rel, "type": "symlink", "mode": mode, "target": target, "target_inside_root": under(resolved, root)}
        if stat.S_ISREG(info.st_mode):
            return {"path": rel, "type": "file", "mode": mode, "sha256": sha256_file(path)}
        if stat.S_ISDIR(info.st_mode):
            return {"path": rel, "type": "directory", "mode": mode}
        return {"path": rel, "type": "other", "mode": mode}

    fingerprints = {rel: fingerprint(rel) for rel in actual | set(baseline_map)}
    changed: set[str] = set()
    foreign_changes: set[str] = set()
    for rel, current in fingerprints.items():
        baseline_item = baseline_map.get(rel, "__missing__")
        if baseline_item == "__missing__":
            if current is not None:
                changed.add(rel)
            continue
        if current is None:
            changed.add(rel)
            if baseline_item is not None and rel not in declared_paths:
                foreign_changes.add(rel)
            continue
        if isinstance(baseline_item, dict):
            comparable = {
                key: baseline_item.get(key)
                for key in ("type", "mode", "sha256", "target", "target_inside_root")
                if key in baseline_item
            }
            if any(current.get(key) != value for key, value in comparable.items()):
                changed.add(rel)
                if rel not in declared_paths:
                    foreign_changes.add(rel)
    # Git status is an independent source for tracked and ordinary untracked
    # effects.  The baseline remains necessary for ignored files, type/mode
    # evidence, and the exact before/after receipt, but cannot normalize away
    # a path that Git still reports as changed.
    changed.update(status)
    changed.update(renamed)
    unsafe_paths: list[dict[str, Any]] = []
    for rel, item in fingerprints.items():
        if not item:
            continue
        if item.get("type") == "symlink" and not item.get("target_inside_root"):
            unsafe_paths.append({"path": rel, "reason": "symlink target escapes audit root"})
        if item.get("type") == "other":
            unsafe_paths.append({"path": rel, "reason": "unsupported file type"})
    changed_paths = sorted(changed)
    observed_operations: dict[str, str] = {}
    for rel in changed_paths:
        baseline_item = baseline_map.get(rel, "__missing__")
        current = fingerprints.get(rel)
        if baseline_item == "__missing__" and current is not None:
            observed_operations[rel] = "create"
        elif baseline_item != "__missing__" and current is None:
            observed_operations[rel] = "delete"
        else:
            observed_operations[rel] = "modify"
    undeclared = sorted(set(changed_paths) - declared_paths)
    overdeclared = sorted(declared_paths - set(changed_paths))
    operation_mismatches = sorted(
        (
            {"path": path, "declared": declared_operations[path], "actual": observed_operations[path]}
            for path in changed_paths
            if path in declared_operations and declared_operations[path] != observed_operations[path]
        ),
        key=lambda item: (item["path"], item["declared"], item["actual"]),
    )
    try:
        root_real = root.resolve()
    except OSError as exc:
        fail(f"write audit cannot resolve root: {exc}")
    def allowed(path: str) -> bool:
        clean = path.rstrip("/")
        return any(clean == zone or clean.startswith(zone.rstrip("/") + "/") for zone in zone_paths)
    outside = sorted(path for path in changed_paths if not allowed(path))
    outside_operations = sorted(
        (
            {"path": path, "operation": observed_operations[path]}
            for path in changed_paths
            if not zone_allows(zones, path, observed_operations[path])
        ),
        key=lambda item: (item["path"], item["operation"]),
    )
    return {
        "root": str(root_real),
        "actual_paths": sorted(actual),
        "changed_paths": changed_paths,
        "observed_operations": observed_operations,
        "undeclared_paths": undeclared,
        "overdeclared_paths": overdeclared,
        "operation_mismatches": operation_mismatches,
        "outside_zone": outside,
        "outside_operations": outside_operations,
        "rename_endpoints": sorted(renamed),
        "foreign_changes": sorted(foreign_changes),
        "unsafe_paths": unsafe_paths,
        "fingerprints": fingerprints,
        "pass": not undeclared
        and not overdeclared
        and not operation_mismatches
        and not outside
        and not outside_operations
        and not foreign_changes
        and not unsafe_paths
        and not renamed,
    }


def cmd_close_blocked_attempt(args: argparse.Namespace) -> dict[str, Any]:
    """Close a no-write BLOCKED repair and restore its immediate prior candidate."""
    p = paths(args.control_root, args.run_id)
    ticket_id = safe_id(args.ticket_id, "ticket_id")
    attempt_id = safe_id(args.attempt_id, "attempt_id")
    closure_id = safe_id(f"blocked-close-{attempt_id}", "blocked closure ID")

    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        attempt = attempt_by_id(state, attempt_id)
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == ticket_id), None)
        existing_ref = attempt.get("blocked_closure_ref")
        if existing_ref:
            receipt = stored_payload(p, existing_ref, "blocked attempt closure receipt")
            restored_ref = receipt.get("restored_attempt_ref")
            if (
                receipt.get("closure_id") != closure_id
                or receipt.get("ticket_id") != ticket_id
                or receipt.get("attempt_id") != attempt_id
                or ticket is None
                or ticket.get("current_attempt") != restored_ref
                or attempt.get("lease", {}).get("state") != "released"
                or not any(item.get("id") == closure_id and item.get("type") == "blocked_attempt_closure" for item in state.get("decisions", []))
            ):
                fail("blocked attempt closure receipt exists but ledger effects are incomplete or conflicting")
            return {
                "closed": True,
                "idempotent": True,
                "attempt_id": attempt_id,
                "restored_attempt_id": restored_ref,
                "candidate_sha": receipt.get("restored_candidate_sha"),
                "receipt_ref": existing_ref,
                "revision": state["revision"],
            }
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state["lifecycle"]["control"] != "BLOCKED":
            fail("blocked attempt closure requires lifecycle control BLOCKED")
        if ticket is None or ticket.get("state") != "BLOCKED" or ticket.get("current_attempt") != attempt_id or attempt.get("subject_ref") != ticket_id:
            fail("blocked attempt closure requires the exact current BLOCKED ticket attempt")
        if attempt.get("kind") != "worker" or attempt.get("mode") != "repair" or attempt.get("state") != "RETURNED":
            fail("blocked attempt closure applies only to a returned worker repair attempt")
        if attempt.get("lease", {}).get("state") != "active":
            fail("blocked attempt closure requires the attempt's active lease")
        if attempt.get("candidate_sha") is not None or attempt.get("candidate_tree_sha") is not None:
            fail("blocked attempt closure requires candidate_sha and candidate_tree_sha to be null")
        if any(item.get("state") in ("prepared", "uncertain") for item in state.get("operations", [])):
            fail("blocked attempt closure requires all prepared effects to be reconciled")

        returned = stored_payload(p, attempt.get("return_ref"), "blocked worker return")
        schema_root = schema()
        validate(returned, schema_root["$defs"]["worker_return"], schema_root, "$.blocked_return")
        identity = packet_identity(returned)
        if (
            returned.get("status") != "BLOCKED"
            or returned.get("files") != []
            or identity.get("run_id") != state["run_id"]
            or identity.get("ticket_id") != ticket_id
            or identity.get("attempt_id") != attempt_id
            or identity.get("packet_hash") != attempt.get("packet_hash")
            or identity.get("epoch") != attempt.get("epoch")
        ):
            fail("blocked attempt closure requires an exact validated BLOCKED return declaring no files")

        attempt_index = next(index for index, item in enumerate(state.get("attempts", [])) if item.get("id") == attempt_id)
        earlier_workers = [
            item for item in state.get("attempts", [])[:attempt_index]
            if item.get("kind") == "worker" and item.get("subject_ref") == ticket_id and item.get("candidate_sha")
        ]
        if not earlier_workers:
            fail("blocked attempt closure requires a previous validated candidate for the same ticket")
        restored = earlier_workers[-1]
        if restored.get("candidate_sha") != attempt.get("base_sha"):
            fail("the last validated same-ticket candidate does not match the blocked attempt base")
        if restored.get("state") != "RETURNED" or restored.get("lease", {}).get("state") != "released" or not restored.get("candidate_tree_sha"):
            fail("the last same-ticket candidate is not a closed validated candidate")
        restored_return = stored_payload(p, restored.get("return_ref"), "restored candidate worker return")
        validate(restored_return, schema_root["$defs"]["worker_return"], schema_root, "$.restored_return")
        restored_identity = packet_identity(restored_return)
        if (
            restored_return.get("status") != "DONE"
            or restored_identity.get("run_id") != state["run_id"]
            or restored_identity.get("ticket_id") != ticket_id
            or restored_identity.get("attempt_id") != restored.get("id")
            or restored_identity.get("packet_hash") != restored.get("packet_hash")
            or restored_identity.get("epoch") != restored.get("epoch")
        ):
            fail("the last same-ticket candidate lacks an exact validated DONE return")
        provenance = attempt.get("repair_lease_provenance")
        if isinstance(provenance, dict) and (
            provenance.get("source_attempt_ref") != restored.get("id")
            or provenance.get("candidate_sha") != restored.get("candidate_sha")
            or provenance.get("packet_base_sha") != restored.get("candidate_sha")
        ):
            fail("blocked repair provenance does not point to the last validated candidate")
        other_open = [
            item.get("id") for item in state.get("attempts", [])
            if item.get("subject_ref") == ticket_id
            and item.get("id") != attempt_id
            and item.get("lease", {}).get("state") in ("active", "quarantined")
        ]
        if other_open:
            fail(f"blocked attempt closure found other open same-ticket leases: {other_open}")

        if not isinstance(attempt.get("checkout"), str) or not attempt.get("checkout"):
            fail("blocked attempt closure requires an exact checkout path")
        checkout = safe_root(attempt["checkout"], "blocked attempt checkout")
        top_level = Path(git_output(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve()
        try:
            exact_worktree = checkout.samefile(top_level)
        except OSError:
            exact_worktree = False
        if not exact_worktree:
            fail("blocked attempt checkout is not the exact Git worktree root")
        observed_head = git_output(checkout, "rev-parse", "HEAD").decode().strip()
        if observed_head != attempt.get("base_sha") or observed_head != restored.get("candidate_sha"):
            fail("blocked attempt checkout HEAD does not match its last validated candidate base")
        observed_tree = git_output(checkout, "rev-parse", "HEAD^{tree}").decode().strip()
        if observed_tree != restored.get("candidate_tree_sha"):
            fail("blocked attempt checkout tree does not match the last validated candidate")
        baseline = git_tree_baseline(checkout, observed_head)
        audit = audit_write_set(checkout, baseline, [], [])
        if not audit.get("pass") or audit.get("changed_paths"):
            fail(f"blocked attempt checkout is not unchanged: {json.dumps(audit.get('changed_paths', []), sort_keys=True)}")

        receipt = {
            "closure_id": closure_id,
            "kind": "blocked_attempt_closure",
            "run_id": state["run_id"],
            "ticket_id": ticket_id,
            "attempt_id": attempt_id,
            "source_revision": state["revision"],
            "source_ledger_hash": sha256_bytes(previous_raw),
            "return_ref": attempt.get("return_ref"),
            "return_status": "BLOCKED",
            "declared_files": [],
            "candidate_sha": None,
            "candidate_tree_sha": None,
            "lease_before": "active",
            "lease_after": "released",
            "checkout": str(checkout),
            "observed_head": observed_head,
            "observed_tree": observed_tree,
            "write_set_audit": audit,
            "restored_attempt_ref": restored["id"],
            "restored_candidate_sha": restored["candidate_sha"],
            "restored_candidate_tree_sha": restored["candidate_tree_sha"],
            "owner_epoch": state["owner"]["epoch"],
        }
        receipt_digest = object_store(p, canonical_bytes(receipt))
        receipt_ref = f"objects/{receipt_digest}"
        attempt["lease"]["state"] = "released"
        attempt["blocked_closure_ref"] = receipt_ref
        ticket["current_attempt"] = restored["id"]
        state.setdefault("decisions", []).append({
            "id": closure_id,
            "type": "blocked_attempt_closure",
            "status": "closed",
            "decision": "RESTORE_LAST_VALIDATED_CANDIDATE",
            "reason": "validated BLOCKED repair returned before any file or candidate change",
            "evidence_refs": [attempt["return_ref"], receipt_ref],
            "affected_refs": [ticket_id, attempt_id, restored["id"]],
            "intent_revision": state.get("intent", {}).get("current_revision"),
            "invalidated_by": [],
        })
        evidence_id = f"ev-{receipt_digest[:16]}"
        state.setdefault("evidence", []).append({
            "id": evidence_id,
            "hash": receipt_digest,
            "source": "blocked_attempt_closure",
            "scenario": "BLOCKED_NO_WRITE",
            "outcome": "RESTORED_LAST_VALIDATED_CANDIDATE",
            "observer": "ledger-helper",
            "subject": attempt_id,
        })
        state["lifecycle"]["reason"] = "blocked_attempt_closed"
        state["lifecycle"]["next_action"] = {
            "kind": "authorize_repair",
            "subject_refs": [ticket_id, restored["id"], attempt_id],
            "preconditions": ["changed repair contract", "fresh authorization and attempt ID", "dependencies remain INTEGRATED"],
            "read_refs": ["phases/execute.md", "references/ledger.md", "references/routing.md"],
        }
        state["revision"] += 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        publish(p, state, previous_raw, "blocked-attempt-closed")
        return {
            "closed": True,
            "idempotent": False,
            "attempt_id": attempt_id,
            "restored_attempt_id": restored["id"],
            "candidate_sha": restored["candidate_sha"],
            "receipt_ref": receipt_ref,
            "revision": state["revision"],
            "next_action": state["lifecycle"]["next_action"],
        }


def cmd_reconcile_quarantined_attempt(args: argparse.Namespace) -> dict[str, Any]:
    """Reconcile one legacy create-only repair lease without weakening quarantine."""
    p = paths(args.control_root, args.run_id)
    reconciliation_id = safe_id(args.reconciliation_id, "reconciliation_id")
    ticket_id = safe_id(args.ticket_id, "ticket_id")
    attempt_id = safe_id(args.attempt_id, "attempt_id")
    prior_attempt_id = safe_id(args.prior_attempt_id, "prior_attempt_id")
    finding_ref = safe_id(args.finding_ref, "finding_ref")
    actor = nonempty_string(args.actor, "reconciliation actor")
    if not GIT_SHA_RE.fullmatch(args.candidate_sha or "") or not GIT_SHA_RE.fullmatch(args.base_sha or ""):
        fail("reconciliation requires exact candidate and base Git SHAs")
    baseline: dict[str, Any] | None = None
    baseline_raw: bytes | None = None
    baseline_hash: str | None = None
    if args.baseline:
        baseline_path = Path(args.baseline).expanduser().resolve()
        regular_non_symlink(baseline_path)
        baseline_raw = baseline_path.read_bytes()
        try:
            baseline = json.loads(baseline_raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            fail(f"invalid reconciliation baseline {baseline_path}: {exc}")
        if not isinstance(baseline, dict):
            fail("reconciliation baseline must be an object")
        baseline_hash = sha256_bytes(baseline_raw)
    base_binding = {
        "reconciliation_id": reconciliation_id,
        "actor": actor,
        "ticket_id": ticket_id,
        "attempt_id": attempt_id,
        "prior_attempt_id": prior_attempt_id,
        "finding_ref": finding_ref,
        "candidate_sha": args.candidate_sha,
        "base_sha": args.base_sha,
    }

    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        attempt = attempt_by_id(state, attempt_id)
        existing_ref = attempt.get("quarantine_reconciliation_ref")
        if existing_ref:
            existing = stored_payload(p, existing_ref, "quarantine reconciliation receipt")
            observed_binding = {key: existing.get(key) for key in base_binding}
            baseline_matches = (
                existing.get("baseline_sha256") == baseline_hash
                if baseline_hash is not None
                else existing.get("baseline_source") == "git_base"
            )
            if observed_binding != base_binding or not baseline_matches:
                fail("quarantined attempt was already reconciled with different evidence")
            if (
                attempt.get("lease", {}).get("state") != "active"
                or not any(item.get("id") == reconciliation_id and item.get("type") == "quarantine_reconciliation" for item in state.get("decisions", []))
            ):
                fail("quarantine reconciliation receipt exists but ledger effects are incomplete")
            return {
                "reconciled": True,
                "idempotent": True,
                "reconciliation_id": existing.get("reconciliation_id"),
                "attempt_id": attempt_id,
                "receipt_ref": existing_ref,
                "revision": state["revision"],
            }
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        if any(item.get("id") == reconciliation_id for item in state.get("decisions", [])):
            fail("reconciliation ID already exists")
        ticket = next((item for item in state.get("tickets", []) if item.get("id") == ticket_id), None)
        if ticket is None or attempt.get("subject_ref") != ticket_id or ticket.get("current_attempt") != attempt_id:
            fail("reconciliation requires the exact current attempt of the same ticket")
        if attempt.get("kind") != "worker" or attempt.get("mode") != "repair" or attempt.get("state") != "RETURNED":
            fail("reconciliation requires a returned worker repair attempt")
        if attempt.get("lease", {}).get("state") != "quarantined":
            fail("reconciliation applies only to an existing quarantined lease")
        if attempt.get("candidate_sha") is not None:
            fail("reconciliation must precede candidate publication")

        packet = stored_payload(p, attempt.get("packet_ref"), "quarantined worker packet")
        schema_root = schema()
        validate(packet, schema_root["$defs"]["worker_packet"], schema_root, "$.packet")
        packet_identity_value = packet_identity(packet)
        repair = packet.get("repair")
        if (
            packet.get("kind") != "worker"
            or packet.get("mode") != "repair"
            or packet_identity_value.get("run_id") != args.run_id
            or packet_identity_value.get("ticket_id") != ticket_id
            or packet_identity_value.get("attempt_id") != attempt_id
            or not isinstance(repair, dict)
        ):
            fail("quarantined packet identity/mode does not match reconciliation")
        if attempt.get("repair_contract") != repair:
            fail("quarantined attempt repair contract does not match its packet")
        if repair.get("finding_ref") != finding_ref:
            fail("reconciliation finding does not match the repair contract")

        authorization = active_repair_authorization(state, ticket_id, finding_ref)
        if authorization is None or attempt.get("repair_authorization_ref") not in (None, authorization.get("id")):
            fail("reconciliation requires the exact accepted repair authorization")
        contract_refs = [
            ref for ref in authorization.get("evidence_refs", [])
            if isinstance(ref, str) and ref.startswith("objects/")
        ]
        if contract_refs:
            if len(contract_refs) != 1 or stored_payload(p, contract_refs[0], "authorized repair contract") != repair:
                fail("reconciliation repair contract is not hash-bound to its authorization")
        elif finding_ref not in authorization.get("evidence_refs", []) or authorization.get("reason") != repair.get("hypothesis"):
            fail("legacy repair authorization is not bound to the exact finding and hypothesis")
        finding_record = next((item for item in state.get("findings", []) if item.get("id") == finding_ref), None)
        issue_record = next((item for item in state.get("issues", []) if item.get("id") == finding_ref), None)
        if issue_record and issue_record.get("finding_ref"):
            finding_record = next((item for item in state.get("findings", []) if item.get("id") == issue_record.get("finding_ref")), finding_record)
        legacy_review = next(
            (item for item in state.get("attempts", []) if finding_record and item.get("id") == finding_record.get("source_ref")),
            None,
        )
        legacy_candidate_binding = bool(
            finding_record
            and finding_record.get("impact") == "blocking"
            and not finding_record.get("invalidated_by")
            and legacy_review
            and legacy_review.get("kind") == "review"
            and legacy_review.get("subject_ref") == ticket_id
            and legacy_review.get("state") == "RETURNED"
            and legacy_review.get("candidate_sha") == args.candidate_sha
            and finding_ref in legacy_review.get("finding_refs", [])
        )
        if not finding_matches_candidate(state, finding_ref, ticket_id, args.candidate_sha) and not legacy_candidate_binding:
            fail("reconciliation requires a current blocking finding bound to the exact candidate")

        repair_source_ref = repair.get("source_attempt_ref")
        if repair_source_ref != prior_attempt_id:
            source = attempt_by_id(state, repair_source_ref)
            if (
                finding_record is None
                or finding_record.get("source_ref") != repair_source_ref
                or source.get("kind") != "review"
                or source.get("subject_ref") != ticket_id
                or source.get("state") != "RETURNED"
                or source.get("candidate_sha") != args.candidate_sha
                or finding_ref not in source.get("finding_refs", [])
            ):
                fail("legacy repair source is not the exact candidate-bound finding review")

        prior = attempt_by_id(state, prior_attempt_id)
        if (
            prior.get("kind") != "worker"
            or prior.get("subject_ref") != ticket_id
            or prior.get("state") != "RETURNED"
            or prior.get("candidate_sha") != args.candidate_sha
            or prior.get("lease", {}).get("state") == "quarantined"
        ):
            fail("reconciliation prior candidate provenance is missing, foreign, or quarantined")
        if attempt.get("base_sha") != args.base_sha or args.base_sha != args.candidate_sha:
            fail("reconciliation base SHA is stale or does not equal the prior candidate")
        if packet.get("workspace", {}).get("expected_base") != args.base_sha:
            fail("reconciliation packet base SHA does not match the exact base")
        if baseline is not None and baseline.get("base_sha") not in (None, args.base_sha):
            fail("reconciliation baseline is bound to a different base SHA")

        prior_return = stored_payload(p, prior.get("return_ref"), "prior worker return")
        current_return = stored_payload(p, attempt.get("return_ref"), "quarantined worker return")
        for returned, returned_attempt, label in (
            (prior_return, prior, "prior"),
            (current_return, attempt, "quarantined"),
        ):
            validate(returned, schema_root["$defs"]["worker_return"], schema_root, f"$.{label}_return")
            validate_standalone_contract(returned, "worker_return")
            identity = packet_identity(returned)
            if (
                identity.get("run_id") != args.run_id
                or identity.get("ticket_id") not in (None, ticket_id)
                or identity.get("attempt_id") != returned_attempt.get("id")
                or identity.get("packet_hash") != returned_attempt.get("packet_hash")
                or identity.get("epoch") != returned_attempt.get("epoch")
            ):
                fail(f"reconciliation {label} worker return identity is not exact")
        validate_worker_return_semantics(current_return, packet)
        if prior_return.get("status") != "DONE" or current_return.get("status") != "DONE":
            fail("reconciliation requires confirmed prior and current DONE worker returns")
        created_paths = {
            relative_path(item.get("path"), "prior created path")
            for item in prior_return.get("files", [])
            if item.get("operation") == "create"
        }
        legacy_violations = worker_return_write_set_violations(current_return, attempt.get("lease", {}))
        if not legacy_violations:
            fail("quarantined attempt has no legacy create-only lease violation to reconcile")
        requested = packet_write_zone(packet)
        ticket_zone = ticket.get("zone", [])
        denied = [
            relative_path(item, "packet write deny path").rstrip("/")
            for item in packet.get("write", {}).get("deny", [])
        ]
        expanded: list[dict[str, Any]] = []
        lineage: list[dict[str, Any]] = []
        requested_exceptions = [
            {"path": entry["path"], "operation": operation}
            for entry in requested
            for operation in entry["operations"]
            if not zone_allows(ticket_zone, entry["path"], operation)
        ]
        for violation in requested_exceptions:
            path, operation = violation["path"], violation["operation"]
            if (
                operation != "modify"
                or path not in created_paths
                or not zone_allows(ticket_zone, path, "create")
                or not zone_allows(prior.get("lease", {}).get("zone", []), path, "create")
                or not zone_allows(requested, path, "modify")
            ):
                fail(f"quarantine is not an exact same-ticket create-to-modify case: {path} ({operation})")
            if any(path == item or path.startswith(item + "/") for item in denied):
                fail(f"reconciliation path conflicts with packet deny list: {path}")
            expanded.append({"path": path, "operations": ["modify"]})
            lineage.append({
                "path": path,
                "attempts": validated_repair_path_lineage(
                    p, state, ticket, prior, path, args.candidate_sha
                ),
            })
        legacy_pairs = {(item["path"], item["operation"]) for item in legacy_violations}
        exception_pairs = {(item["path"], item["operation"]) for item in requested_exceptions}
        if not legacy_pairs.issubset(exception_pairs):
            fail("quarantined return contains violations outside the proven repair expansion")

        quarantine_issues = [
            item for item in state.get("issues", [])
            if item.get("source_ref") == attempt_id
            and item.get("impact") == "blocking"
            and not item.get("invalidated_by")
        ]
        if not quarantine_issues or any(item.get("type") != "write_set_violation" for item in quarantine_issues):
            fail("reconciliation refuses quarantine with missing or non-write-set blocking causes")

        checkout = safe_root(attempt.get("checkout") or "", "reconciliation checkout")
        regular_directory(checkout, "reconciliation checkout")
        packet_checkout = safe_root(packet.get("workspace", {}).get("root") or "", "packet checkout")
        if checkout != packet_checkout:
            fail("reconciliation checkout does not match the quarantined packet")
        git_root = Path(git_output(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve()
        if git_root != checkout:
            fail("reconciliation checkout is not the exact Git worktree root")
        observed_head = git_output(checkout, "rev-parse", "HEAD").decode().strip()
        if observed_head != args.base_sha:
            fail("reconciliation checkout HEAD is stale relative to the exact base SHA")
        baseline_source = "supplied"
        if baseline is None:
            baseline = git_tree_baseline(checkout, args.base_sha)
            baseline_raw = canonical_bytes(baseline)
            baseline_hash = sha256_bytes(baseline_raw)
            baseline_source = "git_base"
        assert baseline_raw is not None and baseline_hash is not None
        audit = audit_write_set(checkout, baseline, current_return.get("files", []), requested)
        if not audit.get("pass"):
            fail(f"reconciliation write-set audit failed: {json.dumps(audit, sort_keys=True)}")

        baseline_ref = f"objects/{object_store(p, baseline_raw)}"
        repair_contract_ref = f"objects/{object_store(p, canonical_bytes(repair))}"
        requested_binding = {**base_binding, "baseline_sha256": baseline_hash}
        provenance = {
            "authorization_ref": authorization["id"],
            "finding_ref": finding_ref,
            "source_attempt_ref": prior_attempt_id,
            "candidate_sha": args.candidate_sha,
            "packet_base_sha": args.base_sha,
            "expanded_entries": sorted(expanded, key=lambda item: item["path"]),
            "lineage": sorted(lineage, key=lambda item: item["path"]),
        }
        receipt = {
            **requested_binding,
            "kind": "quarantined_attempt_reconciliation",
            "recorded_at": now(),
            "authorization_ref": authorization["id"],
            "packet_ref": attempt.get("packet_ref"),
            "return_ref": attempt.get("return_ref"),
            "prior_return_ref": prior.get("return_ref"),
            "baseline_ref": baseline_ref,
            "baseline_source": baseline_source,
            "repair_contract_ref": repair_contract_ref,
            "legacy_lease": copy.deepcopy(attempt.get("lease")),
            "effective_lease_zone": requested,
            "repair_lease_provenance": provenance,
            "write_set_audit": audit,
            "quarantine_issue_refs": [item["id"] for item in quarantine_issues],
        }
        receipt_digest = object_store(p, canonical_bytes(receipt))
        receipt_ref = f"objects/{receipt_digest}"

        attempt["lease"]["state"] = "active"
        attempt["lease"]["zone"] = requested
        attempt["repair_authorization_ref"] = authorization["id"]
        attempt["repair_lease_provenance"] = provenance
        attempt["quarantine_reconciliation_ref"] = receipt_ref
        for issue in quarantine_issues:
            issue["impact"] = "advisory"
            issue["disposition"] = f"reconciled by {reconciliation_id}"
            issue["decision_ref"] = reconciliation_id
            issue.setdefault("invalidated_by", []).append(reconciliation_id)
        state.setdefault("decisions", []).append({
            "id": reconciliation_id,
            "type": "quarantine_reconciliation",
            "status": "applied",
            "decision": "RECONCILE",
            "reason": "legacy create-only lease proven as exact same-ticket create-to-modify repair",
            "evidence_refs": [finding_ref, baseline_ref, receipt_ref],
            "affected_refs": [ticket_id, attempt_id, prior_attempt_id, finding_ref],
            "intent_revision": state.get("intent", {}).get("current_revision"),
            "invalidated_by": [],
        })
        evidence_id = f"ev-{receipt_digest[:16]}"
        state.setdefault("evidence", []).append({
            "id": evidence_id,
            "hash": receipt_digest,
            "source": "quarantine_reconciliation",
            "scenario": "legacy_create_to_modify",
            "outcome": "PASS",
            "observer": actor,
            "subject": attempt_id,
        })
        ticket["state"] = "RUNNING"
        state["lifecycle"]["issue_refs"] = [
            ref for ref in state["lifecycle"].get("issue_refs", [])
            if ref not in {item["id"] for item in quarantine_issues}
        ]
        state["lifecycle"]["control"] = "ACTIVE"
        state["lifecycle"]["reason"] = "quarantined_attempt_reconciled"
        state["lifecycle"]["next_action"] = {
            "kind": "prepare_candidate_effect",
            "subject_refs": [attempt_id, reconciliation_id],
            "preconditions": ["reconciliation receipt remains current", "candidate base SHA unchanged"],
            "read_refs": ["phases/execute.md", "references/ledger.md"],
        }
        usage = state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage())
        usage.setdefault("trace", [])
        usage.setdefault("shared_setup", zero_usage())
        usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        delta = {field: 0 for field in USAGE_FIELDS}
        delta["helper_calls"] = 1
        delta["internal_publications"] = 1
        add_usage(usage["counters"], delta)
        usage["trace"].append({
            "id": f"trace-{state['revision'] + 1}-helper",
            "kind": "helper_publication",
            "actor": "ledger-helper",
            "subject_ref": "prepare_candidate_effect",
            "delta": delta,
            "evidence_ref": receipt_ref,
            "recorded_at": now(),
        })
        state["revision"] += 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        publish(p, state, previous_raw, "quarantine-reconciled")
        return {
            "reconciled": True,
            "idempotent": False,
            "reconciliation_id": reconciliation_id,
            "attempt_id": attempt_id,
            "receipt_ref": receipt_ref,
            "changed_paths": audit["changed_paths"],
            "revision": state["revision"],
        }


def cmd_audit(args: argparse.Namespace) -> dict[str, Any]:
    root = safe_root(args.root, "audit root")
    regular_directory(root, "audit root")
    baseline = read_json(Path(args.baseline), "baseline manifest")
    declared = read_json(Path(args.declared), "declared write set")
    zones = read_json(Path(args.zone), "lease zone")
    if not isinstance(declared, list) or not isinstance(zones, list):
        fail("declared write set and lease zone must be arrays")
    return audit_write_set(root, baseline, declared, zones)


def check_integrity(baseline: dict[str, Any], state: dict[str, Any], current_raw: bytes, expected_subject: str | None = None) -> None:
    if baseline.get("status") != "PASS":
        fail("integrity barrier is not PASS")
    if not baseline.get("ledger_hash"):
        fail("integrity barrier lacks the frozen ledger hash")
    if baseline["ledger_hash"] != sha256_bytes(current_raw):
        fail("authoritative ledger changed during review")
    if expected_subject and baseline.get("candidate_fingerprint") != expected_subject:
        fail("integrity candidate fingerprint mismatch")
    if baseline.get("candidate_sha") and not GIT_SHA_RE.fullmatch(baseline["candidate_sha"]):
        fail("invalid baseline candidate SHA")


def validate_manual_receipt(receipt: dict[str, Any], label: str) -> None:
    if receipt.get("status") != "PASS":
        fail(f"{label} is not PASS")
    if not receipt.get("receipt_id"):
        fail(f"{label} lacks receipt_id")
    if not receipt.get("inventory_hashes") and label == "environment receipt":
        fail("environment receipt lacks exported input inventory hashes")
    if label == "environment receipt" and not receipt.get("boundary_probes"):
        fail("environment receipt lacks nonsecret boundary probes")
    if label == "environment receipt" and receipt.get("authoritative_absent") is not True:
        fail("environment receipt does not attest scoped authoritative absence")
    if label == "environment receipt" and not isinstance(receipt.get("topology"), dict):
        fail("environment receipt lacks observable topology")
    if label == "context receipt" and receipt.get("grade") != "MANUAL_ATTESTED_CLEAN":
        fail("manual context receipt must be MANUAL_ATTESTED_CLEAN")
    if label == "context receipt" and receipt.get("clean_input") is not True:
        fail("context receipt lacks clean-input attestation")
    if label == "context receipt" and receipt.get("contamination_absent") is not True:
        fail("context receipt lacks contamination attestation")


def verify_manual_inventory(receipt: dict[str, Any], handoff: dict[str, Any]) -> None:
    bundle = Path(handoff.get("bundle_root", ""))
    regular_directory(bundle, "handoff bundle")
    manifest = read_json(bundle / "manifest.json", "handoff manifest")
    manifest_files = {item.get("path"): item.get("sha256") for item in manifest.get("files", [])}
    expected_manifest = handoff.get("manifest_ref", "").removeprefix("sha256:")
    manifest_path = bundle / "manifest.json"
    if expected_manifest and sha256_file(manifest_path) != expected_manifest:
        fail("handoff manifest has drifted")
    for item in receipt.get("inventory_hashes", []):
        rel = relative_path(item.get("path"), "receipt inventory path")
        expected = item.get("sha256")
        if rel.startswith("g5-bundle/"):
            actual_path = bundle / rel.removeprefix("g5-bundle/")
            regular_non_symlink(actual_path)
            if sha256_file(actual_path) != expected:
                fail(f"environment inventory hash mismatch: {rel}")
        elif rel.startswith("candidate-export/"):
            export_rel = rel.removeprefix("candidate-export/")
            if manifest_files.get(export_rel) != expected:
                fail(f"candidate export inventory does not match manifest: {rel}")
        else:
            fail(f"environment inventory path is outside prepared bundle: {rel}")


def cmd_prepare_handoff(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    packet_path = Path(args.packet).expanduser().resolve()
    projection_path = Path(args.projection).expanduser().resolve()
    packet = read_json(packet_path, "review packet")
    projection = read_json(projection_path, "acceptance projection")
    if not isinstance(packet, dict) or packet.get("kind") not in ("review", "acceptance"):
        fail("handoff packet kind must be review or acceptance")
    root = schema()
    validate(packet, root["$defs"]["acceptance_packet" if packet.get("kind") == "acceptance" else "review_packet"], root, "$.packet")
    if projection.get("kind") != "acceptance_projection":
        fail("handoff projection kind must be acceptance_projection")
    validate(projection, schema()["$defs"]["acceptance_projection"], schema(), "$.projection")
    criteria = projection.get("criteria", [])
    criterion_ids = [item.get("id") for item in criteria]
    if not criteria or len(criterion_ids) != len(set(criterion_ids)) or any(not safe_id(str(i), "criterion_id") for i in criterion_ids):
        fail("projection must contain each active criterion exactly once")
    forbidden = {"worker_returns", "review_log", "repair_narrative", "commit_history", "self_rating", "tests_pass_summary", "credentials"}
    leaked = forbidden.intersection(projection)
    if leaked:
        fail(f"projection leaks forbidden history/self-rating fields: {sorted(leaked)}")
    with Lock(p["lock"]):
        state, _ = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        binding = current_intent_binding(state)
        if projection.get("intent_revision") != binding["revision"]:
            fail("acceptance projection is not the current intent revision")
        projection_ref = projection.get("intent_document_ref")
        projection_hash = projection.get("intent_document_hash")
        if projection_ref is not None and projection_ref != binding["document_ref"]:
            fail("acceptance projection intent document ref is stale")
        if projection_hash is not None and projection_hash != binding["document_hash"]:
            fail("acceptance projection intent document hash is stale")
        packet_identity_value = packet_identity(packet)
        if packet_identity_value.get("intent_revision") not in (None, binding["revision"]):
            fail("handoff packet intent revision is stale")
        if packet_identity_value.get("intent_document_ref") not in (None, binding["document_ref"]):
            fail("handoff packet intent document ref is stale")
        if packet_identity_value.get("intent_document_hash") not in (None, binding["document_hash"]):
            fail("handoff packet intent document hash is stale")
        active_criteria = {item["id"] for item in state.get("criteria", []) if item.get("status") == "active"}
        if set(criterion_ids) != active_criteria:
            fail("acceptance projection criteria do not match current active criteria")
        document = next((item for item in state.get("documents", []) if item.get("id") == binding["document_ref"]), None)
        if document is None:
            fail("current intent document is missing")
        document_path = Path(document["path"])
        if not document_path.exists() or sha256_file(document_path) != document.get("hash") or document.get("hash") != binding["document_hash"]:
            fail("current intent document hash does not match the ledger")
        candidate_attempt = next((item for item in state.get("attempts", []) if item.get("id") == args.attempt_id), None)
        if candidate_attempt is None or not candidate_attempt.get("candidate_sha"):
            fail("handoff requires a frozen candidate")
        if projection.get("candidate_fingerprint") != candidate_attempt.get("candidate_sha"):
            fail("handoff projection candidate does not match the frozen candidate")
        if packet.get("subject_fingerprint") not in (None, candidate_attempt.get("candidate_sha")):
            fail("handoff packet subject is not the frozen candidate")
    export = safe_root(args.export_root, "export root")
    bundle = safe_root(args.bundle_root, "bundle root")
    if under(bundle, export) or under(export, bundle):
        fail("bundle and export roots may not contain one another")
    regular_directory(export, "export root")
    if bundle.exists() and (bundle.is_symlink() or not bundle.is_dir()):
        fail("bundle root is not a regular directory")
    if not export.is_dir():
        fail("export root does not exist")
    bundle.mkdir(parents=True, exist_ok=True)
    packet_hash = object_store(p, packet_path.read_bytes())
    manifest: list[dict[str, Any]] = []
    for path in sorted(export.rglob("*")):
        rel = path.relative_to(export)
        if any(part in {".git", ".autopilot", ".codex", ".agents", ".claude"} for part in rel.parts):
            continue
        if path.is_symlink():
            fail(f"export contains symlink: {rel}")
        if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            fail(f"export contains unsupported file type: {rel}")
        if path.is_file():
            data = path.read_bytes()
            manifest.append({"path": rel.as_posix(), "sha256": sha256_bytes(data), "bytes": len(data), "mode": stat.S_IMODE(path.stat().st_mode)})
    manifest_bytes = canonical_bytes({"candidate_fingerprint": projection.get("candidate_fingerprint"), "files": manifest})
    atomic_write(bundle / "manifest.json", manifest_bytes)
    atomic_write(bundle / "packet.json", canonical_bytes(packet))
    atomic_write(bundle / "projection.json", canonical_bytes(projection))
    checklist = "# Operator checklist\n\nTransfer only this bundle. Start a new clean reviewer session; do not fork/resume author context. Record the packet/export hashes and environment/context receipts before running checks. Return exact structured JSON.\n"
    atomic_write(bundle / "operator-checklist.md", checklist.encode())
    manifest_hash = sha256_bytes(manifest_bytes)
    def change(state: dict[str, Any]) -> None:
        attempt = attempt_by_id(state, args.attempt_id)
        if attempt["epoch"] != state["owner"]["epoch"]:
            fail("handoff attempt is stale")
        if attempt.get("kind") not in ("review", "acceptance"):
            fail("handoff requires a separate reviewer/acceptance attempt")
        attempt["state"] = "PREPARED"
        attempt["kind"] = "review"
        attempt["mode"] = "user_assisted"
        attempt["packet_ref"] = f"objects/{packet_hash}"
        attempt["packet_hash"] = packet_hash
        attempt["handoff"] = {"bundle_root": str(bundle), "manifest_ref": f"sha256:{manifest_hash}", "candidate_fingerprint": projection.get("candidate_fingerprint"), "intent_revision": projection.get("intent_revision"), "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"], "transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN"}
        add_usage(state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"manual_handoffs": 1, "manual_setup": 1, "user_interventions": 1})
        state["lifecycle"]["control"] = "BLOCKED"
        state["lifecycle"]["reason"] = "manual_review_pending"
        state["lifecycle"]["next_action"] = {"kind": "import_manual_review", "subject_refs": [args.attempt_id], "preconditions": ["environment receipt", "context receipt", "exact structured return", "integrity barrier"], "read_refs": ["phases/accept.md", "references/safety.md"]}
    result = transaction(p, args.owner_token, args.revision, change)
    return {"prepared": True, "bundle_root": str(bundle), "manifest_sha256": manifest_hash, "revision": result["revision"], "transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN"}


def cmd_import_manual(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    env = read_json(Path(args.environment_receipt), "environment receipt")
    context = read_json(Path(args.context_receipt), "context receipt")
    validate_manual_receipt(env, "environment receipt")
    validate_manual_receipt(context, "context receipt")
    return_path = Path(args.return_file).expanduser().resolve()
    baseline_path = Path(args.integrity_receipt).expanduser().resolve()
    baseline = read_json(baseline_path, "integrity receipt")
    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        attempt = attempt_by_id(state, args.attempt_id)
        proposed_path = inbox_file(p, args.attempt_id, return_path)
        proposed_ref = f"objects/{sha256_file(proposed_path)}"
        prior_acceptance = next((item for item in state.get("acceptance", []) if item.get("return_ref") == proposed_ref), None)
        if attempt.get("return_ref") == proposed_ref and prior_acceptance is not None:
            if prior_acceptance.get("intent_revision") != args.intent_revision or prior_acceptance.get("candidate_fingerprint") != args.candidate_fingerprint:
                fail("conflicting duplicate manual return binding")
            if attempt.get("lease", {}).get("state") == "released":
                return {"imported": True, "idempotent": True, "terminal": state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"), "verdict": prior_acceptance.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False, "revision": state["revision"]}
            next_state = copy.deepcopy(state)
            attempt_by_id(next_state, args.attempt_id)["lease"]["state"] = "released"
            next_state["revision"] += 1
            next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
            next_state["updated_at"] = now()
            publish(p, next_state, previous_raw, "manual-import-reconcile")
            return {"imported": True, "idempotent": True, "reconciled": True, "verdict": prior_acceptance.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False, "revision": next_state["revision"]}
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if attempt.get("mode") != "user_assisted":
            fail("manual import requires a user-assisted prepared attempt")
        if attempt.get("kind") != "review":
            fail("manual import requires a separate reviewer attempt")
        binding = current_intent_binding(state)
        if args.intent_revision != binding["revision"]:
            fail("manual import intent revision is not current")
        packet = stored_payload(p, attempt.get("packet_ref"), "acceptance packet")
        root = schema()
        validate(packet, root["$defs"]["acceptance_packet"], root, "$.acceptance_packet")
        if context.get("packet_hash") != attempt.get("packet_hash"):
            fail("context receipt packet hash does not match prepared handoff")
        expected_manifest = (attempt.get("handoff") or {}).get("manifest_ref")
        if expected_manifest and context.get("export_hash") != expected_manifest.removeprefix("sha256:"):
            fail("context receipt export hash does not match prepared handoff")
        verify_manual_inventory(env, attempt.get("handoff") or {})
        payload, digest = ingest_payload(p, state, args.attempt_id, return_path, attempt.get("packet_hash"), "acceptance")
        identity = packet_identity(payload)
        if identity.get("intent_revision") != args.intent_revision:
            fail("manual return intent revision mismatch")
        if identity.get("intent_document_ref") not in (None, binding["document_ref"]):
            fail("manual return intent document ref mismatch")
        if identity.get("intent_document_hash") not in (None, binding["document_hash"]):
            fail("manual return intent document hash mismatch")
        if identity.get("epoch") not in (None, attempt.get("epoch")):
            fail("manual return epoch mismatch")
        candidate = args.candidate_fingerprint
        if payload.get("candidate_fingerprint") != candidate:
            fail("manual return candidate fingerprint mismatch")
        if packet.get("subject_fingerprint") != candidate:
            fail("manual acceptance packet subject is not the current candidate")
        if payload.get("verdict") not in ("PASS", "BLOCK", "UNVERIFIABLE"):
            fail("manual return has invalid verdict")
        packet_required = [review_criterion_id(item) for item in packet.get("criteria", [])]
        required = [x for x in args.required_criteria.split(",") if x]
        if required != packet_required and set(required) != set(packet_required):
            fail("required criteria argument does not match the prepared acceptance packet")
        required = packet_required
        check_integrity(baseline, state, p["ledger"].read_bytes(), candidate)
        validate_acceptance_return_semantics(payload, required)
        add_usage(state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"return_bytes": len(canonical_bytes(payload)), "manual_wait": 1})
        existing_ref = f"objects/{digest}"
        if any(item.get("return_ref") == existing_ref for item in state.get("acceptance", [])):
            if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
                return {"imported": True, "idempotent": True, "terminal": True, "verdict": payload.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False, "revision": state["revision"]}
            if payload.get("verdict") == "PASS":
                next_state = copy.deepcopy(state)
                next_attempt = attempt_by_id(next_state, args.attempt_id)
                next_attempt["lease"]["state"] = "released"
                ticket = next((t for t in next_state.get("tickets", []) if t.get("id") == next_attempt.get("subject_ref")), None)
                if ticket and ticket.get("state") == "REVIEW":
                    ticket["state"] = "INTEGRATED"
                next_state["revision"] += 1
                next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
                next_state["updated_at"] = now()
                publish(p, next_state, previous_raw)
                return {"imported": True, "idempotent": True, "reconciled": True, "verdict": payload.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False, "revision": next_state["revision"]}
            return {"imported": True, "idempotent": True, "verdict": payload.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False}
        next_state = copy.deepcopy(state)
        next_attempt = attempt_by_id(next_state, args.attempt_id)
        next_attempt["state"] = "RETURNED"
        next_attempt["return_ref"] = f"objects/{digest}"
        next_attempt["lease"]["state"] = "released"
        if payload.get("verdict") == "PASS":
            ticket = next((t for t in next_state.get("tickets", []) if t.get("id") == next_attempt.get("subject_ref")), None)
            if ticket and ticket.get("state") == "REVIEW":
                ticket["state"] = "INTEGRATED"
        acceptance = next_state.setdefault("acceptance", [])
        acceptance.append({"round": len(acceptance) + 1, "intent_revision": args.intent_revision, "candidate_fingerprint": candidate, "verdict": payload.get("verdict"), "transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "setup_receipt_ref": f"objects/{object_store(p, canonical_bytes(env))}", "context_receipt_ref": f"objects/{object_store(p, canonical_bytes(context))}", "return_ref": f"objects/{digest}", "outcome_refs": []})
        evidence = next_state.setdefault("evidence", [])
        add_usage(next_state.setdefault("usage", default_usage()).setdefault("counters", zero_usage()), {"return_bytes": len(canonical_bytes(payload))})
        evidence.append({"id": f"ev-{digest[:16]}", "hash": digest, "source": "manual_review_return", "scenario": "critical/G5", "outcome": payload.get("verdict"), "observer": "independent-reviewer", "subject": candidate})
        if payload.get("verdict") == "PASS":
            next_state["lifecycle"]["phase"] = "ACCEPT"
            next_state["lifecycle"]["control"] = "ACTIVE"
            next_state["lifecycle"]["reason"] = None
            next_state["lifecycle"]["next_action"] = {"kind": "g6_final_record", "subject_refs": [args.attempt_id], "preconditions": ["current revisions unchanged", "no active leases/blockers"], "read_refs": ["phases/accept.md", "references/ledger.md"]}
        else:
            next_state["lifecycle"]["control"] = "BLOCKED"
            next_state["lifecycle"]["reason"] = "manual_review_not_pass"
        next_state["revision"] += 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        publish(p, next_state, previous_raw)
    return {"imported": True, "idempotent": False, "verdict": payload.get("verdict"), "acceptance_transport": "user_assisted", "context_grade": "MANUAL_ATTESTED_CLEAN", "release_ready": False, "revision": next_state["revision"]}


def cmd_publish_intent(args: argparse.Namespace) -> dict[str, Any]:
    """Publish the one initial intent binding for an initialized run."""
    p = paths(args.control_root, args.run_id)
    raw = intent_source_bytes(args.intent_file)
    digest = sha256_bytes(raw)
    doc_id = safe_id(args.doc_id, "document_id")
    doc_path = canonical_document_path(p, doc_id, args.doc_version)
    intent_revision = nonempty_string(args.intent_revision, "intent_revision")
    started = time.monotonic()

    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state.get("intent") is not None:
            fail("initial intent already exists; use amend for a new intent revision")
        if any(document.get("kind") == "intent" for document in state.get("documents", [])):
            fail("an intent document already exists without a current binding; recover or adjudicate it before bootstrap")
        if state["lifecycle"]["phase"] not in ("PREFLIGHT", "INTENT"):
            fail("initial intent may only be published from PREFLIGHT or INTENT")
        current_control = state["lifecycle"]["control"]
        if current_control not in ("ACTIVE", "BLOCKED", "RECOVERING"):
            fail("initial intent requires an ACTIVE, BLOCKED, or RECOVERING run; resume/recover the run first")

        next_state = copy.deepcopy(state)
        next_state.setdefault("documents", []).append({
            "id": doc_id,
            "version": args.doc_version,
            "path": str(doc_path),
            "hash": digest,
            "kind": "intent",
            "section_anchors": [],
        })
        next_state["intent"] = {
            "current_revision": intent_revision,
            "document_ref": doc_id,
            "document_hash": digest,
            "approved_amendments": [],
            "acceptance_policy": "automatic",
            "checkpoint_policy": "gate",
            "prior_accepted_refs": [],
        }
        blocking_refs = list(next_state["lifecycle"].get("issue_refs", []))
        recovering = current_control == "RECOVERING" and not blocking_refs
        next_state["lifecycle"]["phase"] = "INTENT"
        next_state["lifecycle"]["control"] = "BLOCKED" if blocking_refs else ("RECOVERING" if recovering else "ACTIVE")
        next_state["lifecycle"]["reason"] = "existing_blockers" if blocking_refs else ("initial_intent_published_during_recovery" if recovering else "initial_intent_published")
        next_state["lifecycle"]["next_action"] = {
            "kind": "resolve_blockers_before_g1" if blocking_refs else ("finish_recovery_then_g1" if recovering else "g1_build"),
            "subject_refs": [doc_id, *blocking_refs],
            "preconditions": ["current intent hash verified"],
            "read_refs": ["phases/intent.md", "references/ledger.md"],
        }

        usage = next_state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage())
        usage.setdefault("trace", [])
        usage.setdefault("shared_setup", zero_usage())
        usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        delta = {field: 0 for field in USAGE_FIELDS}
        delta["helper_calls"] = 1
        delta["internal_publications"] = 1
        delta["wall_time_ms"] = max(0, int((time.monotonic() - started) * 1000))
        add_usage(usage["counters"], delta)
        usage["trace"].append({
            "id": f"trace-{state['revision'] + 1}-helper",
            "kind": "helper_publication",
            "actor": "ledger-helper",
            "subject_ref": next_state["lifecycle"]["next_action"]["kind"],
            "delta": delta,
            "evidence_ref": None,
            "recorded_at": now(),
        })
        next_state["revision"] = state["revision"] + 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()

        # Validate every input and the complete proposed ledger before making
        # the immutable document visible.  A same-byte orphan from a crash is
        # reusable; conflicting bytes are never overwritten.
        validate_ledger(next_state)
        if doc_path.exists():
            regular_non_symlink(doc_path)
            if doc_path.read_bytes() != raw:
                fail("canonical initial intent destination already exists with different bytes")
        else:
            atomic_write(doc_path, raw)
        publish(p, next_state, previous_raw)

    return {
        "published": True,
        "intent_revision": intent_revision,
        "document_ref": doc_id,
        "document_hash": digest,
        "revision": next_state["revision"],
        "phase": next_state["lifecycle"]["phase"],
        "control": next_state["lifecycle"]["control"],
        "next_action": next_state["lifecycle"]["next_action"],
    }


def cmd_adopt_requirements(args: argparse.Namespace) -> dict[str, Any]:
    """Atomically publish explicit requirements/criteria into a legacy run."""
    p = paths(args.control_root, args.run_id)
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = read_json(manifest_path, "requirements manifest")
    root = schema()
    validate(manifest, root["$defs"]["requirements_manifest"], root, "$.requirements_manifest")
    raw = manifest_path.read_bytes()
    digest = sha256_bytes(raw)
    requirement_ids = ids_from_records(manifest["requirements"], "id", "requirement")
    criterion_ids = ids_from_records(manifest["criteria"], "id", "criterion")
    requirement_set, criterion_set = set(requirement_ids), set(criterion_ids)
    if requirement_set & criterion_set:
        fail("requirements manifest reuses an ID across requirements and criteria")
    for requirement in manifest["requirements"]:
        if not set(requirement.get("criterion_refs", [])).issubset(criterion_set):
            fail(f"requirements manifest has an unknown criterion binding: {requirement['id']}")
        if manifest["intent_document_ref"] not in requirement.get("provenance_refs", []):
            fail(f"requirement lacks explicit current-intent provenance: {requirement['id']}")
    for criterion in manifest["criteria"]:
        if not criterion.get("requirement_refs") or not set(criterion["requirement_refs"]).issubset(requirement_set):
            fail(f"criterion lacks a valid explicit requirement binding: {criterion['id']}")
        if criterion.get("source_ref") not in (None, manifest["intent_document_ref"]):
            fail(f"criterion source_ref is not the bound intent document: {criterion['id']}")
        for requirement_ref in criterion["requirement_refs"]:
            requirement = next(item for item in manifest["requirements"] if item["id"] == requirement_ref)
            if criterion["id"] not in requirement.get("criterion_refs", []):
                fail(f"requirement/criterion binding is not bidirectional: {criterion['id']}")

    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        existing_publication = next((item for item in state.get("requirements_publications", []) if item.get("id") == manifest["publication_id"]), None)
        if existing_publication:
            if existing_publication.get("publication_hash") == digest:
                current_binding = current_intent_binding(state)
                if existing_publication.get("status") == "PUBLISHED" and (existing_publication.get("intent_revision"), existing_publication.get("intent_document_ref"), existing_publication.get("intent_document_hash")) == (current_binding["revision"], current_binding["document_ref"], current_binding["document_hash"]):
                    return {"published": True, "idempotent": True, "publication_id": manifest["publication_id"], "publication_hash": digest, "revision": state["revision"], "next_action": state["lifecycle"]["next_action"]}
                fail("requirements publication is historical/stale; use a new publication ID bound to the current intent")
            fail("requirements publication ID already exists with different bytes")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        if state["lifecycle"]["phase"] not in ("INTENT", "DESIGN", "PLAN"):
            fail("requirements adoption is only legal before execution")
        if state["lifecycle"]["phase"] == "PLAN" and state["lifecycle"].get("control") != "BLOCKED":
            fail("requirements adoption during PLAN requires an explicit repair blocker")
        if active_publication_leases(state):
            fail("requirements adoption requires stopped attempts and released leases")
        if any(item.get("state") in ("prepared", "uncertain") for item in state.get("operations", [])):
            fail("requirements adoption requires reconciled operations")
        binding = current_intent_binding(state)
        if any(item.get("status") == "PUBLISHED" and item.get("intent_revision") == binding["revision"] and item.get("intent_document_hash") == binding["document_hash"] for item in state.get("requirements_publications", [])):
            fail("a current requirements publication already exists for this intent")
        if manifest["epoch"] != state["owner"]["epoch"]:
            fail("requirements manifest epoch does not match current owner")
        if (manifest["intent_revision"], manifest["intent_document_ref"], manifest["intent_document_hash"]) != (binding["revision"], binding["document_ref"], binding["document_hash"]):
            fail("requirements manifest is bound to a stale intent")
        collections = {
            "requirements": {item["id"]: item for item in state.get("requirements", [])},
            "criteria": {item["id"]: item for item in state.get("criteria", [])},
        }
        occupied = {item.get("id") for value in state.values() if isinstance(value, list) for item in value if isinstance(item, dict) and item.get("id")}
        for name in ("requirements", "criteria"):
            for record in manifest[name]:
                existing = collections[name].get(record["id"])
                if record["id"] in occupied and existing is None:
                    fail(f"requirements manifest ID conflicts with immutable state: {record['id']}")
                if existing is not None and existing != record:
                    fail(f"conflicting canonical {name[:-1]}: {record['id']}")

        next_state = copy.deepcopy(state)
        for name in ("requirements", "criteria"):
            target = next_state.setdefault(name, [])
            existing_ids = {item["id"] for item in target}
            target.extend(copy.deepcopy(item) for item in manifest[name] if item["id"] not in existing_ids)
        publication = {
            "id": manifest["publication_id"], "version": manifest["version"], "status": "PUBLISHED", "owner_epoch": state["owner"]["epoch"],
            "intent_revision": binding["revision"], "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"],
            "publication_hash": digest, "manifest_ref": f"objects/{digest}", "published_revision": state["revision"] + 1,
            "requirement_refs": requirement_ids, "criterion_refs": criterion_ids,
        }
        next_state.setdefault("requirements_publications", []).append(publication)
        provenance = ensure_runtime_provenance(next_state)
        migration_id = f"adopt-requirements-{manifest['publication_id']}"
        provenance["applied_migrations"].append({"id": migration_id, "helper_version": SKILL_VERSION, "applied_revision": state["revision"] + 1, "manifest_hash": digest, "object_ref": f"objects/{digest}"})
        next_state["lifecycle"]["next_action"] = {"kind": "publish_design_bundle", "subject_refs": [manifest["publication_id"]], "preconditions": ["requirements/criteria publication is current", "design bundle refs resolve exactly"], "read_refs": ["phases/design.md", "references/ledger.md"]}
        object_store(p, raw)
        next_state["revision"] = state["revision"] + 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        publish(p, next_state, previous_raw, "requirements-adoption")
    return {"published": True, "idempotent": False, "publication_id": manifest["publication_id"], "publication_hash": digest, "requirement_count": len(requirement_ids), "criterion_count": len(criterion_ids), "revision": next_state["revision"], "next_action": next_state["lifecycle"]["next_action"]}


def current_design_publication(state: dict[str, Any]) -> dict[str, Any]:
    publication = state.get("design_publication")
    if not isinstance(publication, dict) or publication.get("status") != "PUBLISHED":
        fail("G2/G3 requires a published design bundle")
    validate_ledger(state)
    return publication


def design_publication_history(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return publication history, presenting a legacy current record as item one."""
    history = state.get("design_publication_history")
    if isinstance(history, list) and history:
        return history
    publication = state.get("design_publication")
    return [copy.deepcopy(publication)] if isinstance(publication, dict) else []


def design_publication_requires_revision(state: dict[str, Any], publication: dict[str, Any]) -> bool:
    fingerprint = publication.get("publication_hash")
    publication_id = publication.get("id")
    blocked_reviews = {
        "BLOCK", "UNVERIFIABLE"
    }
    if any(
        review.get("subject_fingerprint") == fingerprint
        and review.get("verdict") in blocked_reviews
        and review.get("review_kind") in ("coverage", "plan")
        for review in state.get("reviews", [])
    ):
        return True
    if any(
        attempt.get("subject_ref") == publication_id
        and attempt.get("subject_fingerprint") == fingerprint
        and attempt.get("review_result") in blocked_reviews
        and attempt.get("mode") in ("coverage", "plan")
        for attempt in state.get("attempts", [])
    ):
        return True
    return state.get("lifecycle", {}).get("control") == "BLOCKED" and state.get("lifecycle", {}).get("reason") in {
        "review_not_pass", "design_review_blocked", "design_review_unverifiable", "design_revision_required"
    }


def active_publication_leases(state: dict[str, Any]) -> list[str]:
    return [
        attempt.get("id", "unknown")
        for attempt in state.get("attempts", [])
        if attempt.get("state") in ("PREPARED", "DISPATCHED")
        or attempt.get("lease", {}).get("state") in ("active", "quarantined")
    ]


def publication_consumer_refs(state: dict[str, Any], publication: dict[str, Any]) -> list[str]:
    subjects = {publication.get("id"), *publication.get("document_refs", []), *publication.get("requirement_refs", []), *publication.get("criterion_refs", []), *publication.get("contract_refs", []), *publication.get("ticket_refs", []), *publication.get("route_refs", [])}
    refs = set(item for item in subjects if item)
    changed = True
    while changed:
        changed = False
        for collection in ("attempts", "reviews", "findings", "issues", "evidence"):
            for item in state.get(collection, []):
                related = (
                    item.get("subject_ref") in refs
                    or item.get("subject") in refs
                    or item.get("subject_fingerprint") == publication.get("publication_hash")
                    or item.get("source_ref") in refs
                    or bool(set(item.get("affected_refs", [])) & refs)
                    or bool(set(item.get("finding_refs", [])) & refs)
                )
                if related and item.get("id") and item["id"] not in refs:
                    refs.add(item["id"])
                    changed = True
    return sorted(refs)


def supersede_design_publication(next_state: dict[str, Any], previous: dict[str, Any], replacement_id: str) -> None:
    """Keep old publication/review bytes intact while fencing their consumers."""
    old_id = previous["id"]
    history = next_state.setdefault("design_publication_history", [])
    old_history = next((item for item in history if item.get("id") == old_id), None)
    if old_history is None:
        old_history = copy.deepcopy(previous)
        history.append(old_history)
    old_history["status"] = "SUPERSEDED"
    old_history["superseded_by"] = replacement_id
    if replacement_id not in old_history.setdefault("invalidated_by", []):
        old_history["invalidated_by"].append(replacement_id)
    consumers = publication_consumer_refs(next_state, previous)
    old_history["consumer_refs"] = consumers
    consumer_set = set(consumers)
    subject_set = {old_id, *previous.get("document_refs", []), *previous.get("requirement_refs", []), *previous.get("criterion_refs", []), *previous.get("contract_refs", []), *previous.get("ticket_refs", []), *previous.get("route_refs", [])}
    for collection in ("attempts", "reviews", "findings", "evidence"):
        for item in next_state.get(collection, []):
            if item.get("id") in consumer_set and replacement_id not in item.setdefault("invalidated_by", []):
                item["invalidated_by"].append(replacement_id)
    for issue in next_state.get("issues", []):
        affected = set(issue.get("affected_refs", []))
        if issue.get("type") in ("review_verdict", "review_finding", "reviewer_disagreement") and (
            bool(affected & (subject_set | consumer_set)) or issue.get("source_ref") in consumer_set
        ):
            issue["impact"] = "advisory"
            issue["disposition"] = "historical evidence; superseded by revised design publication"
            if replacement_id not in issue.setdefault("invalidated_by", []):
                issue["invalidated_by"].append(replacement_id)
    next_state["lifecycle"]["issue_refs"] = [
        ref for ref in next_state["lifecycle"].get("issue_refs", [])
        if next((item for item in next_state.get("issues", []) if item.get("id") == ref), {}).get("impact") == "blocking"
    ]
    if next_state["lifecycle"].get("control") == "BLOCKED" and not any(item.get("impact") == "blocking" for item in next_state.get("issues", [])):
        next_state["lifecycle"]["control"] = "ACTIVE"
        next_state["lifecycle"]["reason"] = "revised_design_published"


def fresh_current_design_passes(state: dict[str, Any], review_kind: str) -> list[dict[str, str]]:
    """Return PASS review/attempt pairs that prove current registered ingestion."""
    publication = current_design_publication(state)
    pairs: list[dict[str, str]] = []
    for review in state.get("reviews", []):
        if (
            review.get("review_kind") != review_kind
            or review.get("verdict") != "PASS"
            or review.get("subject_fingerprint") != publication.get("publication_hash")
            or review.get("intent_revision") != publication.get("intent_revision")
            or review.get("target_revision") != publication.get("published_revision")
            or review.get("invalidated_by")
        ):
            continue
        attempts = [
            attempt for attempt in state.get("attempts", [])
            if attempt.get("kind") == "review"
            and attempt.get("mode") == review_kind
            and attempt.get("state") == "RETURNED"
            and attempt.get("review_result") == "PASS"
            and attempt.get("subject_ref") == publication.get("id")
            and attempt.get("subject_fingerprint") == publication.get("publication_hash")
            and attempt.get("subject_revision") == publication.get("published_revision")
            and attempt.get("target_revision") == publication.get("published_revision")
            and attempt.get("intent_revision") == publication.get("intent_revision")
            and attempt.get("return_ref") == review.get("return_ref")
            and attempt.get("packet_hash")
            and attempt.get("lease", {}).get("state") == "released"
            and not attempt.get("invalidated_by")
        ]
        for attempt in attempts:
            pairs.append({"review_id": review["id"], "attempt_id": attempt["id"]})
    return pairs


def _publication_lineage_bindings(record: dict[str, Any]) -> dict[str, Any]:
    revisions = {
        value for value in (record.get("subject_revision"), record.get("target_revision"))
        if value is not None
    }
    return {
        "subject_ref": record.get("subject_ref"),
        "subject_fingerprint": record.get("subject_fingerprint"),
        "revisions": sorted(revisions),
    }


def resolve_review_finding_lineage(state: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any]:
    """Resolve an issue to one publication without using names as evidence."""
    if issue.get("type") != "review_finding":
        return {"status": "not_review_finding", "reason": "issue type is not review_finding"}
    finding = next(
        (item for item in state.get("findings", []) if item.get("id") == issue.get("finding_ref")),
        None,
    )
    if finding is None:
        return {"status": "unresolved", "reason": "missing finding_ref target"}

    source_ids = []
    for source_id in (issue.get("source_ref"), finding.get("source_ref")):
        if source_id and source_id not in source_ids:
            source_ids.append(source_id)
    records: list[dict[str, Any]] = []
    source_record_ids: set[str] = set()
    for source_id in source_ids:
        matches = [
            item for collection in ("attempts", "reviews")
            for item in state.get(collection, []) if item.get("id") == source_id
        ]
        if len(matches) != 1:
            reason = "source_ref does not resolve to one attempt/review" if not matches else "source_ref resolves ambiguously"
            return {"status": "unresolved", "reason": reason, "source_ref": source_id}
        records.append(matches[0])
        source_record_ids.add(source_id)

    if not records:
        return {"status": "unresolved", "reason": "finding has no durable attempt/review source"}

    # A return object is the canonical bridge between an attempt and its review.
    return_refs = {item.get("return_ref") for item in records if item.get("return_ref")}
    for collection in ("attempts", "reviews"):
        for item in state.get(collection, []):
            linked_by_return = item.get("return_ref") in return_refs if item.get("return_ref") else False
            linked_by_finding = finding["id"] in item.get("finding_refs", [])
            if linked_by_return or linked_by_finding:
                if item.get("id") not in source_record_ids:
                    records.append(item)
                    source_record_ids.add(item["id"])

    histories = design_publication_history(state)
    candidates = list(histories)
    binding_count = 0
    binding_summary: list[dict[str, Any]] = []
    for record in records:
        bindings = _publication_lineage_bindings(record)
        if len(bindings["revisions"]) > 1:
            return {
                "status": "unresolved",
                "reason": "source record has conflicting subject/target revisions",
                "source_ref": record.get("id"),
            }
        used: dict[str, Any] = {"record_id": record.get("id")}
        if bindings["subject_ref"]:
            candidates = [item for item in candidates if item.get("id") == bindings["subject_ref"]]
            used["subject_ref"] = bindings["subject_ref"]
            binding_count += 1
        if bindings["subject_fingerprint"]:
            candidates = [item for item in candidates if item.get("publication_hash") == bindings["subject_fingerprint"]]
            used["subject_fingerprint"] = bindings["subject_fingerprint"]
            binding_count += 1
        if bindings["revisions"]:
            revision = bindings["revisions"][0]
            candidates = [item for item in candidates if item.get("published_revision") == revision]
            used["subject_revision"] = revision
            binding_count += 1
        if len(used) > 1:
            binding_summary.append(used)

    if binding_count == 0:
        return {"status": "unresolved", "reason": "source records contain no canonical publication bindings"}
    unique = {item.get("id"): item for item in candidates if item.get("id")}
    if not unique:
        return {
            "status": "unresolved",
            "reason": "canonical source bindings match no design publication history record",
            "bindings": binding_summary,
        }
    if len(unique) != 1:
        return {
            "status": "ambiguous",
            "reason": "canonical source bindings match multiple design publications",
            "candidate_publication_ids": sorted(unique),
            "bindings": binding_summary,
        }
    publication = next(iter(unique.values()))
    current = state.get("design_publication", {})
    if publication.get("id") == current.get("id"):
        lineage_status = "current"
        reason = "finding is bound to the current design publication"
    elif publication.get("status") in ("SUPERSEDED", "INVALIDATED") or publication.get("superseded_by") or publication.get("invalidated_by"):
        lineage_status = "superseded"
        reason = "finding is bound to a non-current superseded/invalidated publication"
    else:
        lineage_status = "unresolved"
        reason = "matched publication is non-current but lacks supersession/invalidation evidence"
    return {
        "status": lineage_status,
        "reason": reason,
        "publication_id": publication.get("id"),
        "publication_fingerprint": publication.get("publication_hash"),
        "publication_revision": publication.get("published_revision"),
        "finding_id": finding["id"],
        "source_record_ids": sorted(source_record_ids),
        "bindings": binding_summary,
    }


def _append_invalidation(record: dict[str, Any], marker: str) -> None:
    if marker not in record.setdefault("invalidated_by", []):
        record["invalidated_by"].append(marker)


def _apply_review_currentness_resolution(
    state: dict[str, Any], issue: dict[str, Any], resolution: dict[str, Any], marker: str
) -> list[str]:
    """Fence one proven historical closure while retaining every source record."""
    changed: list[str] = []
    ids = {issue["id"], resolution["finding_id"], *resolution["source_record_ids"]}
    source_attempt_ids = {
        item["id"] for item in state.get("attempts", []) if item.get("id") in ids
    }
    for evidence in state.get("evidence", []):
        if evidence.get("subject") in source_attempt_ids:
            ids.add(evidence["id"])
    for collection in ("issues", "findings", "attempts", "reviews", "evidence"):
        for record in state.get(collection, []):
            if record.get("id") in ids and marker not in record.get("invalidated_by", []):
                _append_invalidation(record, marker)
                changed.append(record["id"])
    return sorted(changed)


def cmd_migrate_review_currentness(args: argparse.Namespace) -> dict[str, Any]:
    """Fence provably historical legacy review findings without rewriting them."""
    p = paths(args.control_root, args.run_id)
    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        publication = current_design_publication(state)
        marker = f"review-currentness-{publication['publication_hash']}"
        provenance = state.get("runtime_provenance", {})
        prior = next(
            (item for item in provenance.get("applied_migrations", []) if item.get("id") == marker),
            None,
        )
        if prior is not None:
            report = stored_payload(p, prior.get("object_ref"), "review currentness migration report")
            if sha256_bytes(canonical_bytes(report)) != prior.get("manifest_hash"):
                fail("stored review currentness migration report hash mismatch")
            return {
                "migrated": True,
                "idempotent": True,
                "migration_id": marker,
                "revision": state["revision"],
                "report": report,
            }

        passes = {
            kind: fresh_current_design_passes(state, kind)
            for kind in ("coverage", "plan")
        }
        missing_passes = [kind for kind, pairs in passes.items() if not pairs]
        if missing_passes:
            fail(
                "review currentness migration requires fresh registered and ingested current PASS: "
                + ", ".join(missing_passes)
            )

        next_state = copy.deepcopy(state)
        outcomes: list[dict[str, Any]] = []
        changed_ids: set[str] = set()
        active_findings = [
            item for item in next_state.get("issues", [])
            if item.get("type") == "review_finding"
            and item.get("impact") == "blocking"
            and not item.get("invalidated_by")
        ]
        for issue in active_findings:
            resolution = resolve_review_finding_lineage(next_state, issue)
            outcome = {"issue_id": issue["id"], **resolution}
            if resolution.get("status") == "superseded":
                changed = _apply_review_currentness_resolution(next_state, issue, resolution, marker)
                changed_ids.update(changed)
                outcome["action"] = "invalidated_as_historical"
                outcome["changed_record_ids"] = changed
            else:
                outcome["action"] = "preserved_as_current_blocker"
            outcomes.append(outcome)

        if not changed_ids:
            return {
                "migrated": False,
                "idempotent": True,
                "no_effect": True,
                "migration_id": marker,
                "revision": state["revision"],
                "outcomes": outcomes,
            }

        current_blocker_ids = [
            item["id"] for item in next_state.get("issues", [])
            if item.get("impact") == "blocking" and not item.get("invalidated_by")
        ]
        next_state["lifecycle"]["issue_refs"] = [
            ref for ref in next_state["lifecycle"].get("issue_refs", []) if ref in current_blocker_ids
        ]
        if next_state["lifecycle"].get("control") == "BLOCKED" and not current_blocker_ids:
            next_state["lifecycle"]["control"] = "ACTIVE"
            next_state["lifecycle"]["reason"] = "review_currentness_migrated"
            next_state["lifecycle"]["next_action"] = {
                "kind": "advance_g2_g3",
                "subject_refs": [publication["id"]],
                "preconditions": ["current coverage PASS", "current plan PASS", "no current blocking issues"],
                "read_refs": ["phases/design.md", "references/ledger.md"],
            }

        report = {
            "kind": "review_currentness_migration",
            "migration_id": marker,
            "run_id": state["run_id"],
            "source_revision": state["revision"],
            "applied_revision": state["revision"] + 1,
            "current_publication": {
                "id": publication["id"],
                "publication_hash": publication["publication_hash"],
                "published_revision": publication["published_revision"],
            },
            "fresh_passes": passes,
            "outcomes": outcomes,
            "changed_record_ids": sorted(changed_ids),
            "remaining_current_blocker_ids": current_blocker_ids,
        }
        report_raw = canonical_bytes(report)
        report_hash = object_store(p, report_raw)
        runtime = ensure_runtime_provenance(next_state)
        runtime["applied_migrations"].append({
            "id": marker,
            "helper_version": SKILL_VERSION,
            "applied_revision": state["revision"] + 1,
            "manifest_hash": report_hash,
            "object_ref": f"objects/{report_hash}",
        })
        usage = next_state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage())
        usage.setdefault("trace", [])
        usage.setdefault("shared_setup", zero_usage())
        usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        delta = {field: 0 for field in USAGE_FIELDS}
        delta["helper_calls"] = 1
        delta["internal_publications"] = 1
        add_usage(usage["counters"], delta)
        usage["trace"].append({
            "id": f"trace-{state['revision'] + 1}-helper",
            "kind": "helper_publication",
            "actor": "ledger-helper",
            "subject_ref": marker,
            "delta": delta,
            "evidence_ref": f"objects/{report_hash}",
            "recorded_at": now(),
        })
        next_state["revision"] = state["revision"] + 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        publish(p, next_state, previous_raw, "review-currentness-migration")
        return {
            "migrated": True,
            "idempotent": False,
            "migration_id": marker,
            "revision": next_state["revision"],
            "report_hash": report_hash,
            "report": report,
        }


def design_review_pass(state: dict[str, Any], review_kind: str) -> bool:
    publication = current_design_publication(state)
    return any(
        review.get("review_kind") == review_kind
        and review.get("verdict") == "PASS"
        and review.get("subject_fingerprint") == publication.get("publication_hash")
        and review.get("intent_revision") == publication.get("intent_revision")
        and review.get("target_revision") == publication.get("published_revision")
        and not review.get("invalidated_by")
        for review in state.get("reviews", [])
    )


def cmd_publish_design_bundle(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    bundle_path = Path(args.bundle).expanduser().resolve()
    bundle = read_json(bundle_path, "design bundle")
    root = schema()
    validate(bundle, root["$defs"]["design_bundle"], root, "$.design_bundle")
    validate_design_bundle(bundle)
    bundle_hash = sha256_bytes(canonical_bytes(bundle))
    source_bytes = {document["id"]: design_bundle_source(document)[1] for document in bundle["documents"]}
    started = time.monotonic()

    with Lock(p["lock"]):
        state, previous_raw = load_state(p)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        existing = state.get("design_publication")
        # A response can be lost after the ledger commit.  If the exact
        # immutable publication is already current, adopting it is safe even
        # when the caller retries with the pre-commit revision.
        if existing and existing.get("status") == "PUBLISHED" and existing.get("publication_hash") == bundle_hash and existing.get("id") == bundle["bundle_id"]:
            return {"published": True, "idempotent": True, "bundle_id": bundle["bundle_id"], "publication_hash": bundle_hash, "revision": state["revision"], "next_action": state["lifecycle"]["next_action"]}
        if state["revision"] != args.revision:
            fail(f"revision mismatch: expected {args.revision}, current {state['revision']}")
        if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        if state["lifecycle"]["phase"] != "DESIGN":
            fail("design bundle publication requires a G1-complete DESIGN phase")
        binding = current_intent_binding(state)
        if bundle["epoch"] != state["owner"]["epoch"]:
            fail("design bundle epoch does not match current owner")
        if (bundle["intent_revision"], bundle["intent_document_ref"], bundle["intent_document_hash"]) != (binding["revision"], binding["document_ref"], binding["document_hash"]):
            fail("design bundle is bound to a stale intent")
        if existing:
            if state["lifecycle"]["phase"] != "DESIGN":
                fail("design republish is only legal during DESIGN")
            if not design_publication_requires_revision(state, existing):
                fail("conflicting design bundle is already published; current publication does not have an eligible BLOCK/UNVERIFIABLE repair transition")
            active = active_publication_leases(state)
            if active:
                fail(f"design republish requires stopped writers/reviewers and released leases: {', '.join(active)}")
            if bundle["version"] == existing.get("version"):
                fail("revised design publication requires a new bundle version")

        collections = {collection: {item.get("id"): item for item in state.get(collection, [])} for collection in ("documents", "contracts", "tickets", "routes")}
        occupied = {item.get("id") for collection in state.values() if isinstance(collection, list) for item in collection if isinstance(item, dict) and item.get("id")}
        if bundle["bundle_id"] in occupied:
            fail("design bundle ID conflicts with an existing immutable ID")
        if state.get("design_publication") and state["design_publication"].get("id") == bundle["bundle_id"]:
            fail("design bundle ID was already used by a prior publication")
        for collection_name in ("documents", "contracts", "tickets", "routes"):
            for record in bundle[collection_name]:
                existing_record = collections[collection_name].get(record["id"])
                if record["id"] in occupied and (existing_record is None or existing_record != record and collection_name != "documents"):
                    fail(f"design bundle ID conflicts with an existing immutable ID: {record['id']}")
        next_state = copy.deepcopy(state)
        prior_publication = copy.deepcopy(existing) if existing else None
        if prior_publication:
            supersede_design_publication(next_state, prior_publication, bundle["bundle_id"])
        next_state.setdefault("documents", [])
        for document in bundle["documents"]:
            canonical = {"id": document["id"], "version": document["version"], "path": str(canonical_document_path(p, document["id"], document["version"])), "hash": document["hash"], "kind": document["kind"], "section_anchors": document.get("section_anchors", [])}
            existing_document = collections["documents"].get(document["id"])
            if existing_document is not None:
                if existing_document != canonical:
                    fail(f"conflicting canonical document: {document['id']}")
                continue
            next_state["documents"].append(canonical)
        for collection_name in ("contracts", "tickets", "routes"):
            for record in bundle[collection_name]:
                existing_record = collections[collection_name].get(record["id"])
                if existing_record is not None:
                    if existing_record != record:
                        fail(f"conflicting canonical {collection_name[:-1]}: {record['id']}")
                    continue
                next_state.setdefault(collection_name, []).append(copy.deepcopy(record))
        known_criteria = {item["id"] for item in next_state.get("criteria", [])}
        known_contracts = {item["id"] for item in next_state.get("contracts", [])}
        known_tickets = {item["id"] for item in next_state.get("tickets", [])}
        validate_ticket_contract_bindings(next_state.get("contracts", []), bundle["tickets"], "design bundle")
        for ticket in bundle["tickets"]:
            if not set(ticket.get("criterion_refs", [])).issubset(known_criteria):
                fail(f"design ticket references an unknown criterion: {ticket['id']}")
            if not set(ticket.get("contract_refs", [])).issubset(known_contracts):
                fail(f"design ticket references an unknown contract: {ticket['id']}")
            if not set(ticket.get("dependency_refs", [])).issubset(known_tickets):
                fail(f"design ticket references an unknown dependency: {ticket['id']}")

        document_refs = [item["id"] for item in bundle["documents"]]
        active_requirement_refs = [item["id"] for item in next_state.get("requirements", []) if item.get("status") == "active"]
        active_criterion_refs = [item["id"] for item in next_state.get("criteria", []) if item.get("status") == "active"]
        requirements_publication = next((item for item in reversed(next_state.get("requirements_publications", [])) if item.get("status") == "PUBLISHED" and item.get("intent_revision") == binding["revision"] and item.get("intent_document_hash") == binding["document_hash"]), None)
        new_publication = {
            "id": bundle["bundle_id"], "version": bundle["version"], "status": "PUBLISHED", "owner_epoch": state["owner"]["epoch"],
            "intent_revision": binding["revision"], "intent_document_ref": binding["document_ref"], "intent_document_hash": binding["document_hash"],
            "publication_hash": bundle_hash, "bundle_ref": f"objects/{bundle_hash}", "published_revision": state["revision"] + 1,
            "document_refs": document_refs, "requirement_refs": active_requirement_refs, "criterion_refs": active_criterion_refs,
            "requirements_publication_ref": requirements_publication.get("id") if requirements_publication else None,
            "contract_refs": [item["id"] for item in bundle["contracts"]], "ticket_refs": [item["id"] for item in bundle["tickets"]], "route_refs": [item["id"] for item in bundle["routes"]],
        }
        if prior_publication:
            new_publication["supersedes"] = [prior_publication["id"]]
        next_state["design_publication"] = new_publication
        next_state.setdefault("design_publication_history", []).append(copy.deepcopy(new_publication))
        if state["lifecycle"]["control"] == "BLOCKED" and state["lifecycle"].get("reason") in ("missing_design_publication", "design_publication_required", "design_artifacts_unpublished", "publication_gap"):
            publication_blockers = set(state["lifecycle"].get("issue_refs", []))
            unrelated_blockers = [issue for issue in state.get("issues", []) if issue.get("id") in publication_blockers and issue.get("type") not in ("design_publication_gap", "missing_design_publication")]
            if not unrelated_blockers:
                for issue in next_state.get("issues", []):
                    if issue.get("id") in publication_blockers:
                        issue["impact"] = "advisory"
                        issue["disposition"] = "resolved by design publication"
                next_state["lifecycle"]["issue_refs"] = []
                next_state["lifecycle"]["control"] = "ACTIVE"
        next_state["lifecycle"]["next_action"] = {"kind": "prepare_g2_coverage_review", "subject_refs": [bundle["bundle_id"], *document_refs], "preconditions": ["published design bundle is current", "fresh coverage reviewer attempt"], "read_refs": ["phases/design.md", "contracts/reviewer.md", "references/ledger.md"]}
        validate_ledger(next_state, verify_files=False)
        destinations: list[tuple[Path, bytes, str]] = []
        for document in bundle["documents"]:
            destination = canonical_document_path(p, document["id"], document["version"])
            if destination.exists():
                regular_non_symlink(destination)
                if destination.read_bytes() != source_bytes[document["id"]]:
                    fail(f"canonical design document destination already exists with different bytes: {document['id']}")
            destinations.append((destination, source_bytes[document["id"]], document["id"]))
        object_store(p, canonical_bytes(bundle))
        for destination, raw, _document_id in destinations:
            if not destination.exists():
                atomic_write(destination, raw)
        usage = next_state.setdefault("usage", default_usage())
        usage.setdefault("counters", zero_usage()); usage.setdefault("trace", []); usage.setdefault("shared_setup", zero_usage()); usage.setdefault("gate_costs", {f"G{i}": zero_usage() for i in range(7)})
        delta = {field: 0 for field in USAGE_FIELDS}; delta["helper_calls"] = 1; delta["internal_publications"] = 1; delta["wall_time_ms"] = max(0, int((time.monotonic() - started) * 1000))
        add_usage(usage["counters"], delta)
        usage["trace"].append({"id": f"trace-{state['revision'] + 1}-helper", "kind": "helper_publication", "actor": "ledger-helper", "subject_ref": bundle["bundle_id"], "delta": delta, "evidence_ref": None, "recorded_at": now()})
        next_state["revision"] = state["revision"] + 1
        next_state["previous_publication_hash"] = sha256_bytes(previous_raw)
        next_state["updated_at"] = now()
        validate_ledger(next_state)
        publish(p, next_state, previous_raw, "design-publication")
    return {"published": True, "idempotent": False, "bundle_id": bundle["bundle_id"], "publication_hash": bundle_hash, "revision": next_state["revision"], "next_action": next_state["lifecycle"]["next_action"]}


def cmd_amend(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    source = Path(args.intent_file).expanduser().resolve()
    regular_non_symlink(source)
    raw = source.read_bytes()
    digest = sha256_bytes(raw)
    doc_dir = p["docs"] / safe_id(args.doc_id, "document_id")
    doc_path = doc_dir / f"{safe_id(args.doc_version, 'document_version')}.md"
    atomic_write(doc_path, raw)
    doc_id = args.doc_id
    def change(state: dict[str, Any]) -> None:
        if not args.authority_ref:
            fail("amendment requires explicit user authority reference")
        old_binding = current_intent_binding(state)
        documents = state.setdefault("documents", [])
        if any(d.get("id") == doc_id and d.get("version") == args.doc_version for d in documents):
            fail("document revision already exists")
        if any(item.get("id") == args.amendment_id for item in state.get("invalidations", [])):
            fail("amendment ID already exists")
        documents.append({"id": doc_id, "version": args.doc_version, "path": str(doc_path), "hash": digest, "kind": "intent", "section_anchors": []})

        collections = ("documents", "requirements_publications", "requirements", "criteria", "contracts", "decisions", "tickets", "attempts", "issues", "findings", "reviews", "acceptance", "operations", "capabilities", "routes", "evidence")
        consumer_refs: list[str] = []
        for collection in collections:
            for item in state.get(collection, []):
                if collection == "documents" and item.get("id") == doc_id:
                    continue
                if item.get("id"):
                    consumer_refs.append(item["id"])
                    if "invalidated_by" in item or collection in {"documents", "requirements_publications", "requirements", "criteria", "contracts", "decisions", "tickets", "attempts", "issues", "findings", "reviews", "acceptance", "operations", "capabilities", "routes", "evidence"}:
                        item.setdefault("invalidated_by", []).append(args.amendment_id)
                    if collection == "requirements_publications":
                        item["status"] = "INVALIDATED"
        if state.get("design_publication"):
            current_publication = state["design_publication"]
            history = state.setdefault("design_publication_history", [])
            if not any(item.get("id") == current_publication.get("id") for item in history):
                history.append(copy.deepcopy(current_publication))
            for publication in history:
                if publication.get("id") == current_publication.get("id"):
                    publication.setdefault("invalidated_by", []).append(args.amendment_id)
                    publication["status"] = "INVALIDATED"
            current_publication.setdefault("invalidated_by", []).append(args.amendment_id)
            current_publication["status"] = "INVALIDATED"
            consumer_refs.append(current_publication["id"])
        state.setdefault("invalidations", []).append({"id": f"invalidation-{args.amendment_id}", "amendment_ref": args.amendment_id, "intent_revision": args.intent_revision, "previous_intent_revision": old_binding["revision"], "previous_document_ref": old_binding["document_ref"], "previous_document_hash": old_binding["document_hash"], "affected_refs": [old_binding["document_ref"], doc_id], "consumer_refs": sorted(set(consumer_refs)), "recorded_at": now()})
        state["intent"] = {"current_revision": args.intent_revision, "document_ref": doc_id, "document_hash": digest, "approved_amendments": [*state.get("intent", {}).get("approved_amendments", []), args.amendment_id], "acceptance_policy": state.get("intent", {}).get("acceptance_policy", "automatic"), "checkpoint_policy": state.get("intent", {}).get("checkpoint_policy", "gate"), "prior_accepted_refs": state.get("intent", {}).get("prior_accepted_refs", [])}
        for ticket in state.get("tickets", []):
            if ticket.get("state") not in ("CANCELLED", "STALE"):
                ticket["state"] = "STALE"
            ticket.setdefault("intent_revision", old_binding["revision"])
        for attempt in state.get("attempts", []):
            if attempt.get("state") in ("PREPARED", "DISPATCHED"):
                attempt["lease"]["state"] = "quarantined"
            attempt.setdefault("intent_revision", old_binding["revision"])
        state["lifecycle"]["phase"] = "INTENT"
        state["lifecycle"]["control"] = "ACTIVE"
        state["lifecycle"]["reason"] = "user_amendment"
        state["lifecycle"]["next_action"] = {"kind": "g1_recheck", "subject_refs": [args.amendment_id], "preconditions": ["affected work quiesced", "current intent hash verified"], "read_refs": ["phases/intent.md", "references/ledger.md"]}
    result = transaction(p, args.owner_token, args.revision, change)
    return {"amended": True, "document_hash": digest, "revision": result["revision"], "next_action": result["lifecycle"]["next_action"]}


def cmd_gate(args: argparse.Namespace) -> dict[str, Any]:
    def change(state: dict[str, Any]) -> None:
        phase = args.phase or state["lifecycle"]["phase"]
        control = args.control or state["lifecycle"]["control"]
        if phase not in PHASES or control not in CONTROLS:
            fail("invalid phase/control")
        current_phase = state["lifecycle"]["phase"]
        current_control = state["lifecycle"]["control"]
        if current_control in ("ACCEPTED", "FAILED", "CANCELLED"):
            fail("terminal run is immutable; start a successor run")
        if control == "CANCELLED":
            fail("direct CANCELLED bypass is forbidden; enter QUIESCING and use cancel --finalize")
        if control == "QUIESCING" and current_control not in ("ACTIVE", "BLOCKED", "RECOVERING"):
            fail(f"cannot enter QUIESCING from {current_control}")
        if control == "PAUSED":
            if current_control != "QUIESCING":
                fail("PAUSED requires a prior QUIESCING transition")
            active_attempts = [
                attempt for attempt in state.get("attempts", [])
                if attempt.get("state") in ("PREPARED", "DISPATCHED")
            ]
            active_leases = [
                attempt for attempt in state.get("attempts", [])
                if attempt.get("lease", {}).get("state") in ("active", "quarantined")
            ]
            unresolved_effects = [
                operation for operation in state.get("operations", [])
                if operation.get("state") in ("prepared", "uncertain")
            ]
            if active_attempts or active_leases or unresolved_effects:
                fail("PAUSED requires stopped writers, released leases, and reconciled effects")
        action = (args.next_action or "").casefold()
        blockers = [item for item in state.get("issues", []) if item.get("impact") == "blocking" and not item.get("invalidated_by")]
        g2_claim = control == "ACTIVE" and phase in ("DESIGN", "PLAN") and ("g2" in action or "coverage" in action or (current_phase == "DESIGN" and phase == "PLAN"))
        g3_claim = control == "ACTIVE" and phase in ("PLAN", "EXECUTE") and ("g3" in action or "plan" in action or (current_phase == "PLAN" and phase == "EXECUTE"))
        if state.get("intent") and (g2_claim or g3_claim):
            current_design_publication(state)
            validate_current_design_contract_bindings(state)
            if not design_review_pass(state, "coverage"):
                fail("G2 cannot pass without a PASS coverage review of the current published design bundle")
            if g3_claim and not design_review_pass(state, "plan"):
                fail("G3 cannot pass without a PASS plan review of the current published design bundle")
            if blockers:
                fail("a current blocking issue prevents G2/G3 advancement")
        current_index = PHASES.index(current_phase)
        requested_index = PHASES.index(phase)
        design_repair_return = (
            phase == "DESIGN"
            and current_phase == "PLAN"
            and current_control == "BLOCKED"
            and isinstance(state.get("design_publication"), dict)
            and design_publication_requires_revision(state, state["design_publication"])
        )
        if design_repair_return and active_publication_leases(state):
            fail("DESIGN repair transition requires stopped writers/reviewers and released leases")
        execution_repair_return = phase == "EXECUTE" and current_phase in ("VERIFY", "ACCEPT") and current_control == "BLOCKED"
        contract_repair_return = phase == "DESIGN" and current_phase in ("EXECUTE", "VERIFY", "ACCEPT") and current_control == "BLOCKED"
        intent_repair_return = phase == "INTENT" and current_phase in ("DESIGN", "PLAN", "EXECUTE", "VERIFY", "ACCEPT") and current_control == "BLOCKED"
        if requested_index not in (current_index, current_index + 1) and not (design_repair_return or execution_repair_return or contract_repair_return or intent_repair_return):
            fail(f"illegal phase jump: {current_phase} -> {phase}")
        if current_phase == "PLAN" and phase == "EXECUTE":
            publication = current_design_publication(state)
            validate_current_design_contract_bindings(state)
            if not design_review_pass(state, "coverage") or not design_review_pass(state, "plan"):
                fail("execution requires current G2 coverage PASS and G3 plan PASS")
            if any(ticket.get("id") in publication.get("ticket_refs", []) and ticket.get("state") not in ("PLANNED", "READY") for ticket in state.get("tickets", [])):
                fail("execution entry requires current design tickets to be PLANNED/READY")
            if blockers:
                fail("execution entry is blocked by current issues")
        if current_phase == "EXECUTE" and phase == "VERIFY":
            publication = current_design_publication(state)
            current_tickets = [ticket for ticket in state.get("tickets", []) if ticket.get("id") in publication.get("ticket_refs", [])]
            if not current_tickets or any(ticket.get("state") != "INTEGRATED" for ticket in current_tickets):
                fail("G4 requires every current publication ticket to be reviewed and INTEGRATED")
            if active_publication_leases(state) or any(op.get("state") in ("prepared", "uncertain") for op in state.get("operations", [])):
                fail("G4 requires released leases and reconciled effects")
            if blockers:
                fail("G4 is blocked by current issues")
        if control == "FAILED":
            if current_control != "QUIESCING" or active_publication_leases(state) or any(op.get("state") in ("prepared", "uncertain") for op in state.get("operations", [])):
                fail("FAILED requires QUIESCING with stopped attempts and reconciled effects")
        if control == "ACCEPTED":
            if current_phase != "ACCEPT" or phase != "ACCEPT":
                fail("G6 terminal acceptance requires ACCEPT phase")
            latest = state.get("acceptance", [])[-1] if state.get("acceptance") else None
            binding = current_intent_binding(state)
            if not latest or latest.get("verdict") != "PASS" or latest.get("intent_revision") != binding["revision"] or latest.get("invalidated_by"):
                fail("G6 cannot mark ACCEPTED without a fresh current-intent G5 PASS")
            if blockers or active_publication_leases(state) or any(op.get("state") in ("prepared", "uncertain") for op in state.get("operations", [])):
                fail("G6 requires no blockers, active/quarantined leases, or unresolved effects")
        state["lifecycle"]["phase"] = phase
        state["lifecycle"]["control"] = control
        state["lifecycle"]["reason"] = args.reason
        state["lifecycle"]["next_action"] = {"kind": args.next_action, "subject_refs": [x for x in args.subject_refs.split(",") if x], "preconditions": [x for x in args.preconditions.split("|") if x], "read_refs": [x for x in args.read_refs.split(",") if x]}
    result = transaction(paths(args.control_root, args.run_id), args.owner_token, args.revision, change, "gate")
    return {"published": True, "revision": result["revision"], "phase": result["lifecycle"]["phase"], "control": result["lifecycle"]["control"]}


def cmd_cancel(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    if not args.finalize:
        def request(state: dict[str, Any]) -> None:
            if state["lifecycle"]["control"] in ("ACCEPTED", "FAILED", "CANCELLED"):
                fail("terminal run is immutable; start a successor run")
            state["lifecycle"]["control"] = "QUIESCING"
            state["lifecycle"]["reason"] = args.reason
            state["lifecycle"]["stop_target"] = args.stop_target
            state["lifecycle"]["next_action"] = {"kind": "stop_reconcile_then_cancel", "subject_refs": [], "preconditions": ["all known writers stopped", "leases and prepared effects reconciled"], "read_refs": ["phases/recover.md", "references/ledger.md"]}
        result = transaction(p, args.owner_token, args.revision, request, "cancel-quiescing")
        return {"quiescing": True, "revision": result["revision"], "control": "QUIESCING"}
    evidence = read_json(Path(args.stop_evidence).expanduser().resolve(), "cancellation stop evidence")
    if evidence.get("status") != "PASS" or evidence.get("writers_stopped") is not True or evidence.get("reconciled") is not True:
        fail("cancellation finalization requires PASS stop/reconcile evidence")
    def finalize(state: dict[str, Any]) -> None:
        if state["lifecycle"]["control"] != "QUIESCING":
            fail("cancellation finalization requires QUIESCING")
        if any(op.get("state") in ("prepared", "uncertain") for op in state.get("operations", [])):
            fail("cancellation requires all prepared effects reconciled")
        for attempt in state.get("attempts", []):
            if attempt.get("state") in ("PREPARED", "DISPATCHED"):
                attempt["state"] = "INTERRUPTED"
            if attempt.get("lease", {}).get("state") in ("active", "quarantined"):
                attempt["lease"]["state"] = "released"
        for ticket in state.get("tickets", []):
            if ticket.get("state") not in ("INTEGRATED", "CANCELLED"):
                ticket["state"] = "CANCELLED"
        state["lifecycle"]["control"] = "CANCELLED"
        state["lifecycle"]["reason"] = args.reason
        state["lifecycle"]["next_action"] = {"kind": "terminal_cancelled", "subject_refs": [], "preconditions": [], "read_refs": ["phases/recover.md"]}
    result = transaction(p, args.owner_token, args.revision, finalize, "cancel-terminal")
    return {"cancelled": True, "revision": result["revision"], "control": "CANCELLED"}


def cmd_recover(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(args.control_root, args.run_id)
    with Lock(p["lock"]):
        try:
            state, previous_raw = load_state(p)
            recovered_from = None
        except LedgerError as exc:
            candidates = recovery_candidates(p, args.run_id)
            if not candidates:
                fail(f"current ledger is corrupt and no verified previous/snapshot exists: {exc}")
            state, previous_raw, source = candidates[0]
            recovered_from = str(source)
        if state["owner"]["token"] != args.owner_token:
            fail("owner token mismatch; stale orchestrator is fenced")
        if not args.takeover and args.revision not in (state["revision"], state["revision"] + 1):
            fail(f"recovery revision does not match verified checkpoint: {args.revision}")
        if args.takeover:
            if not args.new_owner_token:
                fail("takeover requires a new owner token")
            state["owner"]["epoch"] += 1
            state["owner"]["token"] = args.new_owner_token
            state["owner"]["attestation_ref"] = args.attestation_ref
            for attempt in state.get("attempts", []):
                if attempt.get("state") in ("PREPARED", "DISPATCHED"):
                    attempt["lease"]["state"] = "quarantined"
        state["lifecycle"]["control"] = "RECOVERING"
        state["lifecycle"]["reason"] = args.reason
        state["lifecycle"]["next_action"] = {"kind": "reconcile_actual_state", "subject_refs": [], "preconditions": ["writer stop/reuse guard", "Git/effect reconciliation"], "read_refs": ["phases/recover.md", "references/ledger.md"]}
        state["revision"] = state["revision"] + 1
        state["previous_publication_hash"] = sha256_bytes(previous_raw)
        state["updated_at"] = now()
        publish(p, state, previous_raw, "recovery")
        return {"recovering": True, "revision": state["revision"], "epoch": state["owner"]["epoch"], "control": "RECOVERING", "recovered_from": recovered_from}

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex Autopilot deterministic ledger/contract helper")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init"); init.add_argument("--control-root", required=True); init.add_argument("--repo-root", required=True); init.add_argument("--run-id", required=True); init.add_argument("--owner-token", required=True); init.add_argument("--request", default=None, help="optional natural-language request used to resolve run presets"); init.add_argument("--interaction-mode", choices=["semi", "full"], default=None); init.add_argument("--depth", choices=["normal", "deep"], default=None)
    status = sub.add_parser("status"); status.add_argument("--control-root", required=True); status.add_argument("--run-id", required=True); status.add_argument("--brief", action="store_true")
    diagnose = sub.add_parser("diagnose"); diagnose.add_argument("--control-root", required=True); diagnose.add_argument("--run-id", required=True)
    brief = sub.add_parser("brief"); brief.add_argument("--control-root", required=True); brief.add_argument("--run-id", required=True); brief.set_defaults(brief=True)
    view = sub.add_parser("render-view"); view.add_argument("--control-root", required=True); view.add_argument("--run-id", required=True); view.add_argument("--kind", choices=["status", "final-report"], default="status")
    valid = sub.add_parser("validate"); valid.add_argument("--file", required=True); valid.add_argument("--kind", default="ledger")
    state_valid = sub.add_parser("validate-return"); state_valid.add_argument("--control-root", required=True); state_valid.add_argument("--run-id", required=True); state_valid.add_argument("--attempt-id", required=True); state_valid.add_argument("--return-file", required=True); state_valid.add_argument("--kind", choices=["worker", "review", "acceptance"], required=True)
    ingest = sub.add_parser("ingest-return"); ingest.add_argument("--control-root", required=True); ingest.add_argument("--run-id", required=True); ingest.add_argument("--owner-token", required=True); ingest.add_argument("--revision", type=int, required=True); ingest.add_argument("--attempt-id", required=True); ingest.add_argument("--return-file", required=True); ingest.add_argument("--kind", default="worker")
    dispatch = sub.add_parser("dispatch"); dispatch.add_argument("--control-root", required=True); dispatch.add_argument("--run-id", required=True); dispatch.add_argument("--owner-token", required=True); dispatch.add_argument("--revision", type=int, required=True); dispatch.add_argument("--ticket-id", required=True); dispatch.add_argument("--attempt-id", required=True); dispatch.add_argument("--lease-id", required=True); dispatch.add_argument("--route-id", required=True); dispatch.add_argument("--packet", required=True); dispatch.add_argument("--route")
    ready = sub.add_parser("ready-ticket"); ready.add_argument("--control-root", required=True); ready.add_argument("--run-id", required=True); ready.add_argument("--owner-token", required=True); ready.add_argument("--revision", type=int, required=True); ready.add_argument("--ticket-id", required=True)
    repair = sub.add_parser("authorize-repair"); repair.add_argument("--control-root", required=True); repair.add_argument("--run-id", required=True); repair.add_argument("--owner-token", required=True); repair.add_argument("--revision", type=int, required=True); repair.add_argument("--ticket-id", required=True); repair.add_argument("--finding-ref", required=True); repair.add_argument("--authorization-id", required=True); repair.add_argument("--repair-contract", required=True)
    close_blocked = sub.add_parser("close-blocked-attempt", aliases=["restore-last-validated-candidate"]); close_blocked.add_argument("--control-root", required=True); close_blocked.add_argument("--run-id", required=True); close_blocked.add_argument("--owner-token", required=True); close_blocked.add_argument("--revision", type=int, required=True); close_blocked.add_argument("--ticket-id", required=True); close_blocked.add_argument("--attempt-id", required=True)
    reconcile_quarantine = sub.add_parser("reconcile-quarantined-attempt"); reconcile_quarantine.add_argument("--control-root", required=True); reconcile_quarantine.add_argument("--run-id", required=True); reconcile_quarantine.add_argument("--owner-token", required=True); reconcile_quarantine.add_argument("--revision", type=int, required=True); reconcile_quarantine.add_argument("--ticket-id", required=True); reconcile_quarantine.add_argument("--attempt-id", required=True); reconcile_quarantine.add_argument("--prior-attempt-id", required=True); reconcile_quarantine.add_argument("--finding-ref", required=True); reconcile_quarantine.add_argument("--candidate-sha", required=True); reconcile_quarantine.add_argument("--base-sha", required=True); reconcile_quarantine.add_argument("--baseline", help="optional pre-attempt manifest; omitted means derive the complete baseline from the exact Git base tree"); reconcile_quarantine.add_argument("--reconciliation-id", required=True); reconcile_quarantine.add_argument("--actor", required=True)
    terminate = sub.add_parser("terminate-attempt"); terminate.add_argument("--control-root", required=True); terminate.add_argument("--run-id", required=True); terminate.add_argument("--owner-token", required=True); terminate.add_argument("--revision", type=int, required=True); terminate.add_argument("--attempt-id", required=True); terminate.add_argument("--state", choices=["LOST", "INTERRUPTED"], required=True); terminate.add_argument("--lease-state", choices=["released", "quarantined"], required=True); terminate.add_argument("--evidence", required=True)
    candidate = sub.add_parser("candidate"); candidate.add_argument("--control-root", required=True); candidate.add_argument("--run-id", required=True); candidate.add_argument("--owner-token", required=True); candidate.add_argument("--revision", type=int, required=True); candidate.add_argument("--attempt-id", required=True); candidate.add_argument("--commit-receipt", required=True); candidate.add_argument("--operation-id", required=True)
    effect = sub.add_parser("prepare-effect"); effect.add_argument("--control-root", required=True); effect.add_argument("--run-id", required=True); effect.add_argument("--owner-token", required=True); effect.add_argument("--revision", type=int, required=True); effect.add_argument("--operation-id", required=True); effect.add_argument("--kind", required=True); effect.add_argument("--target", required=True); effect.add_argument("--expected-before", default=None); effect.add_argument("--intended-after", default=None); effect.add_argument("--authority-ref", required=True)
    reconcile_effect = sub.add_parser("reconcile-effect"); reconcile_effect.add_argument("--control-root", required=True); reconcile_effect.add_argument("--run-id", required=True); reconcile_effect.add_argument("--owner-token", required=True); reconcile_effect.add_argument("--revision", type=int, required=True); reconcile_effect.add_argument("--operation-id", required=True); reconcile_effect.add_argument("--result", choices=["applied", "uncertain", "unchanged"], required=True); reconcile_effect.add_argument("--receipt")
    review = sub.add_parser("prepare-review"); review.add_argument("--control-root", required=True); review.add_argument("--run-id", required=True); review.add_argument("--owner-token", required=True); review.add_argument("--revision", type=int, required=True); review.add_argument("--ticket-id", required=True); review.add_argument("--review-attempt-id", required=True); review.add_argument("--lease-id", required=True); review.add_argument("--packet", required=True)
    design_review = sub.add_parser("prepare-design-review"); design_review.add_argument("--control-root", required=True); design_review.add_argument("--run-id", required=True); design_review.add_argument("--owner-token", required=True); design_review.add_argument("--revision", type=int, required=True); design_review.add_argument("--review-attempt-id", required=True); design_review.add_argument("--lease-id", required=True); design_review.add_argument("--packet", required=True); design_review.add_argument("--review-kind", choices=["coverage", "plan"], required=True); design_review.add_argument("--reviewer-identity", required=True); design_review.add_argument("--reviewer-role", required=True)
    adjudicate = sub.add_parser("adjudicate"); adjudicate.add_argument("--control-root", required=True); adjudicate.add_argument("--run-id", required=True); adjudicate.add_argument("--owner-token", required=True); adjudicate.add_argument("--revision", type=int, required=True); adjudicate.add_argument("--decision-file", required=True)
    integrate = sub.add_parser("integrate"); integrate.add_argument("--control-root", required=True); integrate.add_argument("--run-id", required=True); integrate.add_argument("--owner-token", required=True); integrate.add_argument("--revision", type=int, required=True); integrate.add_argument("--attempt-id", required=True); integrate.add_argument("--review-file", required=True); integrate.add_argument("--integrity-receipt", required=True); integrate.add_argument("--review-id", required=True)
    handoff = sub.add_parser("prepare-handoff"); handoff.add_argument("--control-root", required=True); handoff.add_argument("--run-id", required=True); handoff.add_argument("--owner-token", required=True); handoff.add_argument("--revision", type=int, required=True); handoff.add_argument("--attempt-id", required=True); handoff.add_argument("--packet", required=True); handoff.add_argument("--projection", required=True); handoff.add_argument("--export-root", required=True); handoff.add_argument("--bundle-root", required=True)
    manual = sub.add_parser("import-manual"); manual.add_argument("--control-root", required=True); manual.add_argument("--run-id", required=True); manual.add_argument("--owner-token", required=True); manual.add_argument("--revision", type=int, required=True); manual.add_argument("--attempt-id", required=True); manual.add_argument("--return-file", required=True); manual.add_argument("--environment-receipt", required=True); manual.add_argument("--context-receipt", required=True); manual.add_argument("--integrity-receipt", required=True); manual.add_argument("--intent-revision", required=True); manual.add_argument("--candidate-fingerprint", required=True); manual.add_argument("--required-criteria", required=True)
    audit = sub.add_parser("audit-write-set"); audit.add_argument("--root", required=True); audit.add_argument("--baseline", required=True); audit.add_argument("--declared", required=True); audit.add_argument("--zone", required=True)
    gate = sub.add_parser("gate"); gate.add_argument("--control-root", required=True); gate.add_argument("--run-id", required=True); gate.add_argument("--owner-token", required=True); gate.add_argument("--revision", type=int, required=True); gate.add_argument("--phase"); gate.add_argument("--control"); gate.add_argument("--reason", default=None); gate.add_argument("--next-action", default="inspect"); gate.add_argument("--subject-refs", default=""); gate.add_argument("--preconditions", default=""); gate.add_argument("--read-refs", default="")
    cancel = sub.add_parser("cancel"); cancel.add_argument("--control-root", required=True); cancel.add_argument("--run-id", required=True); cancel.add_argument("--owner-token", required=True); cancel.add_argument("--revision", type=int, required=True); cancel.add_argument("--reason", default="user_cancelled"); cancel.add_argument("--stop-target", default=None); cancel.add_argument("--finalize", action="store_true"); cancel.add_argument("--stop-evidence")
    recover = sub.add_parser("recover"); recover.add_argument("--control-root", required=True); recover.add_argument("--run-id", required=True); recover.add_argument("--owner-token", required=True); recover.add_argument("--revision", type=int, required=True); recover.add_argument("--reason", default="recovery"); recover.add_argument("--takeover", action="store_true"); recover.add_argument("--new-owner-token", default=None); recover.add_argument("--attestation-ref", default=None)
    initial_intent = sub.add_parser("publish-intent"); initial_intent.add_argument("--control-root", required=True); initial_intent.add_argument("--run-id", required=True); initial_intent.add_argument("--owner-token", required=True); initial_intent.add_argument("--revision", type=int, required=True); initial_intent.add_argument("--intent-file", required=True); initial_intent.add_argument("--doc-id", required=True); initial_intent.add_argument("--doc-version", required=True); initial_intent.add_argument("--intent-revision", required=True)
    requirements = sub.add_parser("adopt-requirements", aliases=["publish-requirements"]); requirements.add_argument("--control-root", required=True); requirements.add_argument("--run-id", required=True); requirements.add_argument("--owner-token", required=True); requirements.add_argument("--revision", type=int, required=True); requirements.add_argument("--manifest", required=True)
    currentness = sub.add_parser("migrate-review-currentness"); currentness.add_argument("--control-root", required=True); currentness.add_argument("--run-id", required=True); currentness.add_argument("--owner-token", required=True); currentness.add_argument("--revision", type=int, required=True)
    design = sub.add_parser("publish-design-bundle", aliases=["publish-design"]); design.add_argument("--control-root", required=True); design.add_argument("--run-id", required=True); design.add_argument("--owner-token", required=True); design.add_argument("--revision", type=int, required=True); design.add_argument("--bundle", required=True)
    amend = sub.add_parser("amend"); amend.add_argument("--control-root", required=True); amend.add_argument("--run-id", required=True); amend.add_argument("--owner-token", required=True); amend.add_argument("--revision", type=int, required=True); amend.add_argument("--intent-file", required=True); amend.add_argument("--doc-id", required=True); amend.add_argument("--doc-version", required=True); amend.add_argument("--intent-revision", required=True); amend.add_argument("--amendment-id", required=True); amend.add_argument("--authority-ref", required=True)
    usage = sub.add_parser("publish-usage"); usage.add_argument("--control-root", required=True); usage.add_argument("--run-id", required=True); usage.add_argument("--owner-token", required=True); usage.add_argument("--revision", type=int, required=True); usage.add_argument("--event-file", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init": result = cmd_init(args)
        elif args.command == "status": result = cmd_status(args)
        elif args.command == "diagnose": result = cmd_diagnose(args)
        elif args.command == "brief": result = cmd_status(args)
        elif args.command == "render-view": result = cmd_render_view(args)
        elif args.command == "validate": result = cmd_validate(args)
        elif args.command == "validate-return": result = cmd_validate_return(args)
        elif args.command == "ingest-return": result = cmd_ingest(args)
        elif args.command == "dispatch": result = cmd_dispatch(args)
        elif args.command == "ready-ticket": result = cmd_ready_ticket(args)
        elif args.command == "authorize-repair": result = cmd_authorize_repair(args)
        elif args.command in ("close-blocked-attempt", "restore-last-validated-candidate"): result = cmd_close_blocked_attempt(args)
        elif args.command == "reconcile-quarantined-attempt": result = cmd_reconcile_quarantined_attempt(args)
        elif args.command == "terminate-attempt": result = cmd_terminate_attempt(args)
        elif args.command == "candidate": result = cmd_candidate(args)
        elif args.command == "prepare-effect": result = cmd_prepare_effect(args)
        elif args.command == "reconcile-effect": result = cmd_reconcile_effect(args)
        elif args.command == "prepare-review": result = cmd_prepare_review(args)
        elif args.command == "prepare-design-review": result = cmd_prepare_design_review(args)
        elif args.command == "adjudicate": result = cmd_adjudicate(args)
        elif args.command == "integrate": result = cmd_integrate(args)
        elif args.command == "prepare-handoff": result = cmd_prepare_handoff(args)
        elif args.command == "import-manual": result = cmd_import_manual(args)
        elif args.command == "audit-write-set": result = cmd_audit(args)
        elif args.command == "gate": result = cmd_gate(args)
        elif args.command == "cancel": result = cmd_cancel(args)
        elif args.command == "recover": result = cmd_recover(args)
        elif args.command == "publish-intent": result = cmd_publish_intent(args)
        elif args.command in ("adopt-requirements", "publish-requirements"): result = cmd_adopt_requirements(args)
        elif args.command == "migrate-review-currentness": result = cmd_migrate_review_currentness(args)
        elif args.command in ("publish-design-bundle", "publish-design"): result = cmd_publish_design_bundle(args)
        elif args.command == "amend": result = cmd_amend(args)
        elif args.command == "publish-usage": result = cmd_publish_usage(args)
        else: fail(f"unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except LedgerError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": f"safe helper failure: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
