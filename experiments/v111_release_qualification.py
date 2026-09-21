#!/usr/bin/env python3
"""Reproducible v1.1.1 release-package and runtime-boundary qualification.

This is intentionally independent of ``tools/ledger.py``.  It verifies the
hash-addressed runtime package, materialises an install copy, inventories the
qualification inputs, and exercises a deterministic fake runtime.  Native
process control is an adapter boundary: this script refuses to turn a fake
receipt into native-runtime evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "release-assets" / "v1.1.1"
PACKAGE_MANIFEST = ASSET_ROOT / "package-manifest.json"
REQUIRED_RUNTIME_PATHS = {
    "SKILL.md",
    "agents/openai.yaml",
    "contracts/reviewer.md",
    "contracts/worker.md",
    "dashboard/index.html",
    "migration-manifests/idea-scout-v2-requirements-v2.json",
    "phases/accept.md",
    "phases/design.md",
    "phases/execute.md",
    "phases/intent.md",
    "phases/plan.md",
    "phases/recover.md",
    "phases/start.md",
    "references/ledger.md",
    "references/routing.md",
    "references/safety.md",
    "release-assets/v1.0.4/idea-scout-v5-g2-packet.json",
    "release-assets/v1.0.4/idea-scout-v5-g3-packet.json",
    "schemas/contracts.schema.json",
    "tools/dashboard.py",
    "tools/ledger.py",
}


class QualificationError(RuntimeError):
    """A release claim is unsafe or cannot be reproduced."""


class NativeRuntimeUnsupported(QualificationError):
    """Native runtime evidence requires an external adapter."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError(f"invalid release artifact: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise QualificationError(f"release artifact must be an object: {path}")
    return value


def digest(path: Path) -> tuple[int, str]:
    if not path.is_file() or path.is_symlink():
        raise QualificationError(f"required regular file missing or symlinked: {path}")
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def safe_relative(value: str, label: str) -> Path:
    candidate = Path(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts:
        raise QualificationError(f"unsafe {label} path: {value!r}")
    return candidate


def load_artifacts(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    assets = root / "release-assets" / "v1.1.1"
    package = read_json(assets / "package-manifest.json")
    if package.get("release") != "v1.1.1" or package.get("schema_version") != "1":
        raise QualificationError("package manifest is not the v1.1.1 schema")
    expected_pointers = {
        "source_manifest": "release-assets/v1.1.1/source-manifest.json",
        "fixture_inventory": "release-assets/v1.1.1/fixture-inventory.json",
        "content_manifest": "release-assets/v1.1.1/content-manifest.json",
        "environment_manifest": "release-assets/v1.1.1/environment-manifest.json",
        "runtime_conformance": "release-assets/v1.1.1/runtime-conformance.json",
    }
    if any(package.get(key) != value for key, value in expected_pointers.items()):
        raise QualificationError("package manifest pointers do not match the v1.1.1 release set")

    def pointed(name: str) -> dict[str, Any]:
        raw = package.get(name)
        rel = safe_relative(raw, name) if isinstance(raw, str) else None
        if rel is None or (root / rel).parent != assets:
            raise QualificationError(f"{name} must point to an artifact in release-assets/v1.1.1")
        return read_json(root / rel)

    runtime = pointed("runtime_conformance")
    inventory = pointed("fixture_inventory")
    inventory["_content"] = pointed("content_manifest")
    return package, pointed("source_manifest"), inventory, pointed("environment_manifest") | {"_runtime": runtime}


def verify_source_manifest(root: Path, source_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries = source_manifest.get("files")
    if source_manifest.get("release") != "v1.1.1" or not isinstance(entries, list) or not entries:
        raise QualificationError("source manifest is empty or has the wrong release")
    seen_source: set[str] = set()
    seen_install: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise QualificationError("source manifest entry is not an object")
        source = entry.get("source")
        install = entry.get("install")
        if not isinstance(source, str) or not isinstance(install, str):
            raise QualificationError("source manifest entry has no source/install path")
        safe_relative(source, "source")
        safe_relative(install, "install")
        if source in seen_source or install in seen_install:
            raise QualificationError(f"duplicate package path: {source}")
        seen_source.add(source)
        seen_install.add(install)
        actual_bytes, actual_hash = digest(root / source)
        if actual_bytes != entry.get("bytes") or actual_hash != entry.get("sha256"):
            raise QualificationError(f"source hash mismatch: {source}")
    if seen_source != REQUIRED_RUNTIME_PATHS:
        missing = sorted(REQUIRED_RUNTIME_PATHS - seen_source)
        extra = sorted(seen_source - REQUIRED_RUNTIME_PATHS)
        raise QualificationError(f"runtime package set mismatch; missing={missing}, extra={extra}")
    return entries


def verify_install_parity(root: Path, entries: list[dict[str, Any]]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="codex-autopilot-install-") as temp:
        install_root = Path(temp) / "codex-autopilot"
        for entry in entries:
            source = root / entry["source"]
            destination = install_root / safe_relative(entry["install"], "install")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
        installed = {str(path.relative_to(install_root)) for path in install_root.rglob("*") if path.is_file()}
        declared = {entry["install"] for entry in entries}
        if installed != declared:
            raise QualificationError(f"installed package set mismatch: {sorted(installed ^ declared)}")
        for entry in entries:
            size, sha = digest(install_root / entry["install"])
            if size != entry["bytes"] or sha != entry["sha256"]:
                raise QualificationError(f"install/source parity mismatch: {entry['install']}")
        installed_runtime_version = verify_runtime_version(install_root)
    return {"files": len(entries), "isolated": True, "runtime_version": installed_runtime_version}


def verify_runtime_version(root: Path) -> str:
    """Check that the installed runtime's source advertises this release."""
    text = (root / "tools" / "ledger.py").read_text(encoding="utf-8")
    match = re.search(r'^SKILL_VERSION\s*=\s*["\']([^"\']+)["\']\s*$', text, re.MULTILINE)
    if match is None or match.group(1) != "1.1.1":
        raise QualificationError("runtime source does not advertise SKILL_VERSION 1.1.1")
    return match.group(1)


def _regular_files(root: Path, *, allowed_hidden: set[str] | None = None) -> list[str]:
    if not root.is_dir() or root.is_symlink():
        raise QualificationError(f"fixture root missing or symlinked: {root}")
    result: list[str] = []
    allowed_hidden = allowed_hidden or set()
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(ROOT)
        hidden = {part for part in rel.parts if part.startswith(".")}
        if hidden - allowed_hidden:
            raise QualificationError(f"hidden fixture path is not reproducible: {rel}")
        if ".git" in rel.parts:
            # Disposable Git fixture metadata is recreated by the qualification
            # harness; it is not a portable fixture payload.
            continue
        if path.is_symlink():
            raise QualificationError(f"symlink fixture is not reproducible: {rel}")
        if path.is_file():
            result.append(str(rel))
    return result


def verify_fixture_inventory(root: Path, inventory: dict[str, Any]) -> dict[str, Any]:
    suite = inventory.get("suite")
    if not isinstance(suite, dict) or suite.get("test_root") != "tests":
        raise QualificationError("fixture inventory has no tests root")
    declared_tests = suite.get("test_modules")
    actual_tests = sorted(str(path.relative_to(root)) for path in (root / "tests").glob("test_*.py"))
    if not isinstance(declared_tests, list) or sorted(declared_tests) != actual_tests:
        raise QualificationError(f"test inventory mismatch; declared={declared_tests}, actual={actual_tests}")
    scripts = inventory.get("qualification_scripts")
    if not isinstance(scripts, list) or not scripts:
        raise QualificationError("qualification script inventory is empty")
    if len(set(scripts)) != len(scripts):
        raise QualificationError("qualification script inventory contains duplicates")
    for item in scripts:
        rel = safe_relative(item, "qualification script")
        digest(root / rel)
    roots = inventory.get("fixture_roots")
    if not isinstance(roots, list) or not roots:
        raise QualificationError("fixture roots are missing")
    fixture_files: list[str] = []
    for item in roots:
        fixture_files.extend(_regular_files(root / safe_relative(item, "fixture root"), allowed_hidden={".git", ".gitignore", ".autopilot"}))
    if not fixture_files:
        raise QualificationError("fixture inventory is empty")
    content = inventory.get("_content")
    entries = content.get("files") if isinstance(content, dict) else None
    if not isinstance(entries, list) or content.get("release") != "v1.1.1":
        raise QualificationError("content manifest is missing or has the wrong release")
    declared: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise QualificationError("content manifest entry is malformed")
        path = entry["path"]
        safe_relative(path, "content")
        if path in declared:
            raise QualificationError(f"duplicate content manifest path: {path}")
        declared[path] = entry
        actual_bytes, actual_hash = digest(root / path)
        if actual_bytes != entry.get("bytes") or actual_hash != entry.get("sha256"):
            raise QualificationError(f"content hash mismatch: {path}")
    expected = set(actual_tests) | set(scripts) | set(fixture_files)
    if set(declared) != expected:
        missing = sorted(expected - set(declared))
        extra = sorted(set(declared) - expected)
        raise QualificationError(f"content inventory path mismatch; missing={missing}, extra={extra}")
    return {
        "test_modules": len(actual_tests), "qualification_scripts": len(scripts),
        "fixture_files": len(fixture_files), "content_files": len(declared),
    }


def verify_environment(root: Path, environment: dict[str, Any]) -> dict[str, Any]:
    runtime = environment.get("runtime", {})
    python_spec = runtime.get("python", {})
    required = tuple(python_spec.get("minimum", []))
    if len(required) != 2 or tuple(__import__("sys").version_info[:2]) < required:
        raise QualificationError(f"Python {required} or newer is required")
    if platform.system().lower() not in {item.lower() for item in environment.get("tested_platforms", [])}:
        raise QualificationError(f"untested platform: {platform.system()}")
    if not os.environ.get("PATH") or not os.environ.get("HOME"):
        raise QualificationError("PATH and HOME are required environment inputs")
    try:
        python_version = subprocess.check_output([python_spec.get("executable", "python3"), "--version"], text=True, stderr=subprocess.STDOUT).strip()
        git_version = subprocess.check_output([runtime.get("git", {}).get("executable", "git"), "--version"], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise QualificationError(f"required executable unavailable: {exc}") from exc
    git_match = re.match(r"^git version (\d+)(?:\.|$)", git_version)
    minimum_git_major = runtime.get("git", {}).get("minimum_major")
    if not git_match or not isinstance(minimum_git_major, int):
        raise QualificationError("git version output is not parseable")
    if int(git_match.group(1)) < minimum_git_major:
        raise QualificationError(f"Git {minimum_git_major}.0 or newer is required")
    return {"platform": platform.system().lower(), "python": python_version, "git": git_version}


@dataclass
class FakeRuntime:
    """A deterministic model of the receipt protocol, not a process runner."""

    attempt_id: str
    instance_id: str = "fake-instance-1"
    events: dict[str, dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        self.events = {}

    def observe(self, event_id: str, event: str, *, coverage: str = "included") -> dict[str, Any]:
        if self.events is None:
            self.events = {}
        if event_id in self.events:
            prior = self.events[event_id]
            if prior["event"] != event or prior["coverage"] != coverage:
                raise QualificationError("conflicting runtime replay")
            return {**prior, "idempotent": True}
        existing = [item["event"] for item in self.events.values()]
        if event == "start" and existing:
            raise QualificationError("start is valid only once")
        if event == "not_started" and existing:
            raise QualificationError("not_started cannot follow another observation")
        if event == "return_observed" and "start" not in existing:
            raise QualificationError("return observation requires start")
        if event == "stop" and ("start" not in existing or coverage != "included"):
            raise QualificationError("stop requires started runtime and included descendants")
        if event not in {"start", "return_observed", "stop", "not_started"}:
            raise QualificationError(f"unsupported fake event: {event}")
        receipt = {
            "event_id": event_id,
            "event": event,
            "attempt_id": self.attempt_id,
            "runtime_instance_id": None if event == "not_started" else self.instance_id,
            "coverage": coverage,
            "observed_at": "2000-01-01T00:00:00Z",
        }
        self.events[event_id] = receipt
        return {**receipt, "idempotent": False}

    def transcript(self) -> list[dict[str, Any]]:
        return [self.events[key] for key in sorted(self.events or {})]


def fake_runtime_conformance() -> dict[str, Any]:
    def run_once() -> FakeRuntime:
        runtime = FakeRuntime("attempt-fake")
        runtime.observe("event-1", "start")
        runtime.observe("event-2", "return_observed")
        runtime.observe("event-3", "stop")
        runtime.observe("event-3", "stop")
        return runtime

    first = run_once()
    second = run_once()
    if first.transcript() != second.transcript() or len(first.transcript()) != 3:
        raise QualificationError("fake runtime is not deterministic or replay-safe")
    if first.transcript()[-1]["coverage"] != "included":
        raise QualificationError("fake stop did not retain descendant coverage")
    return {"status": "SUPPORTED", "events": len(first.transcript()), "replay": "idempotent"}


def require_native_runtime() -> None:
    raise NativeRuntimeUnsupported("native runtime is UNSUPPORTED; use a separately qualified adapter receipt")


def qualify(root: Path = ROOT) -> dict[str, Any]:
    package, source_manifest, inventory, environment = load_artifacts(root)
    entries = verify_source_manifest(root, source_manifest)
    install = verify_install_parity(root, entries)
    runtime_version = install["runtime_version"]
    fixtures = verify_fixture_inventory(root, inventory)
    env = verify_environment(root, environment)
    fake = fake_runtime_conformance()
    runtime = environment["_runtime"]
    native = runtime.get("native_runtime", {})
    if native.get("status") != "UNSUPPORTED" or native.get("fake_receipts_are_native_proof") is not False:
        raise QualificationError("native-runtime boundary is not explicit and fail-closed")
    try:
        require_native_runtime()
    except NativeRuntimeUnsupported:
        pass
    else:  # pragma: no cover - defensive fail-closed branch
        raise QualificationError("native runtime unexpectedly claimed as proven")
    return {
        "qualified": True,
        "release": package["release"],
        "source": {"files": len(entries), "manifest": "sha256", "runtime_version": runtime_version},
        "install": install,
        "fixtures": fixtures,
        "environment": env,
        "fake_runtime": fake,
        "native_runtime": {"status": "UNSUPPORTED", "adapter_bound": True},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = qualify(args.root.resolve())
    except QualificationError as exc:
        print(json.dumps({"qualified": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
