#!/usr/bin/env python3
"""Exercise the exact Idea Scout V5 resume sequence on a disposable copy."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import ledger


SOURCE_ROOT = Path("/Users/pawell_9/Documents/Pet-project - поиск идей проектов")
RUN_ID = "2026-09-16-idea-scout-v2"
OWNER_TOKEN = "owner-20260916-idea-scout-v2-root-01"
EXPECTED_LEDGER_HASH = "b67dfaebe64bbf80bf76d535bff2cf4b4eed12ee7030821f7bb6c59dddc8e0c9"
EXPECTED_V5_RAW_HASH = "c0d235e71d7bed87b9da2141767ad17ad66fe9cd1070ff115ecb989cee3c1f33"
EXPECTED_V5_PUBLICATION_HASH = "6171a6f5b52e5549896c9168ddd54d1e169c6683d9fc648d500935c7f47fd8a4"
V5 = SOURCE_ROOT / ".autopilot" / "runs" / RUN_ID / "sources" / "design-bundle-v5-proposed.json"
MANIFEST = ROOT / "migration-manifests" / "idea-scout-v2-requirements-v2.json"
G2_PACKET = ROOT / "release-assets" / "v1.0.4" / "idea-scout-v5-g2-packet.json"
G3_PACKET = ROOT / "release-assets" / "v1.0.4" / "idea-scout-v5-g3-packet.json"
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]


def call(*args: str) -> dict:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(f"command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)


def main() -> int:
    source_ledger = ledger.paths(SOURCE_ROOT, RUN_ID)["ledger"]
    before_ledger_hash = ledger.sha256_file(source_ledger)
    before_v5_hash = ledger.sha256_file(V5)
    if before_ledger_hash != EXPECTED_LEDGER_HASH or before_v5_hash != EXPECTED_V5_RAW_HASH:
        raise AssertionError("Idea Scout source bytes differ from the audited checkpoint")

    with tempfile.TemporaryDirectory(prefix="idea-scout-v5-resume-") as directory:
        control = Path(directory) / "control"
        shutil.copytree(SOURCE_ROOT / ".autopilot", control / ".autopilot", symlinks=True)
        copied_paths = ledger.paths(control, RUN_ID)
        state, _ = ledger.load_state(copied_paths)
        before_counts = {name: len(state.get(name, [])) for name in ("attempts", "reviews", "findings", "issues", "evidence")}
        state["repository"]["control_root"] = str(control.resolve())
        # Canonical document paths are control-root-relative authority.  The
        # disposable copy must point at its copied documents while preserving
        # every immutable ID/version/hash.
        for document in state.get("documents", []):
            document["path"] = str(ledger.canonical_document_path(copied_paths, document["id"], document["version"]))
        ledger.atomic_write(copied_paths["ledger"], ledger.canonical_bytes(state))

        adoption = call(
            "adopt-requirements", "--control-root", str(control), "--run-id", RUN_ID,
            "--owner-token", OWNER_TOKEN, "--revision", "29", "--manifest", str(MANIFEST),
        )
        publication = call(
            "publish-design-bundle", "--control-root", str(control), "--run-id", RUN_ID,
            "--owner-token", OWNER_TOKEN, "--revision", "30", "--bundle", str(V5),
        )
        resumed, resumed_raw = ledger.load_state(copied_paths)
        ledger.validate_ledger(resumed)
        history = resumed["design_publication_history"]
        statuses = {item["id"]: item["status"] for item in history}
        if resumed["revision"] != 31 or publication["publication_hash"] != EXPECTED_V5_PUBLICATION_HASH:
            raise AssertionError("unexpected V5 publication revision or canonical fingerprint")
        if statuses.get("idea-scout-v2-design-bundle-v2") != "SUPERSEDED" or statuses.get("idea-scout-v2-design-bundle-v3") != "SUPERSEDED" or statuses.get("idea-scout-v2-design-bundle-v4") != "SUPERSEDED":
            raise AssertionError("historical V2/V3/V4 publications were not preserved as SUPERSEDED")
        if resumed["design_publication"]["id"] != "idea-scout-v2-design-bundle-v5":
            raise AssertionError("V5 is not the current publication")
        if resumed["design_publication"].get("requirement_refs") != [f"R-V2-{number:02d}" for number in range(1, 22)]:
            raise AssertionError("V5 is not bound to all adopted requirements")
        if resumed["design_publication"].get("criterion_refs") != [f"C-V2-{number:02d}" for number in range(1, 22)]:
            raise AssertionError("V5 is not bound to all adopted criteria")
        after_publish_counts = {name: len(resumed.get(name, [])) for name in before_counts}
        if any(after_publish_counts[name] < before_counts[name] for name in before_counts):
            raise AssertionError("historical attempts/reviews/findings/issues/evidence were lost")

        g2 = call(
            "prepare-design-review", "--control-root", str(control), "--run-id", RUN_ID,
            "--owner-token", OWNER_TOKEN, "--revision", "31", "--review-attempt-id", "G2-COVERAGE-V5-01",
            "--lease-id", "LEASE-G2-COVERAGE-V5-01", "--packet", str(G2_PACKET), "--review-kind", "coverage",
            "--reviewer-identity", "independent-g2-reviewer-v5-01", "--reviewer-role", "coverage-reviewer",
        )
        g3 = call(
            "prepare-design-review", "--control-root", str(control), "--run-id", RUN_ID,
            "--owner-token", OWNER_TOKEN, "--revision", "32", "--review-attempt-id", "G3-PLAN-V5-01",
            "--lease-id", "LEASE-G3-PLAN-V5-01", "--packet", str(G3_PACKET), "--review-kind", "plan",
            "--reviewer-identity", "independent-g3-reviewer-v5-01", "--reviewer-role", "plan-reviewer",
        )
        resumed, resumed_raw = ledger.load_state(copied_paths)
        ledger.validate_ledger(resumed)
        if resumed["revision"] != 33 or g2["packet_hash"] != ledger.sha256_file(G2_PACKET) or g3["packet_hash"] != ledger.sha256_file(G3_PACKET):
            raise AssertionError("fresh V5 review registration did not produce revisions 32/33 with exact packets")

        report = {
            "qualified": True,
            "source_unchanged": {
                "ledger_sha256": ledger.sha256_file(source_ledger),
                "v5_raw_sha256": ledger.sha256_file(V5),
            },
            "disposable_result": {
                "publication_revision": publication["revision"],
                "final_revision": resumed["revision"],
                "ledger_sha256": ledger.sha256_bytes(resumed_raw),
                "requirements_publication_hash": adoption["publication_hash"],
                "v5_publication_hash": publication["publication_hash"],
                "history_statuses": statuses,
                "before_counts": before_counts,
                "after_publish_counts": after_publish_counts,
                "after_registration_counts": {name: len(resumed.get(name, [])) for name in before_counts},
                "g2_packet_hash": g2["packet_hash"],
                "g3_packet_hash": g3["packet_hash"],
                "next_action": resumed["lifecycle"]["next_action"],
                "version_provenance": resumed["runtime_provenance"],
            },
        }

    if ledger.sha256_file(source_ledger) != before_ledger_hash or ledger.sha256_file(V5) != before_v5_hash:
        raise AssertionError("dry run altered the Idea Scout source checkpoint")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
