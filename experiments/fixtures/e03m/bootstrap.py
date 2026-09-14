#!/usr/bin/env python3
"""Seed only the disposable metadata needed to exercise the production path."""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

from ledger import atomic_write, canonical_bytes, load_state, paths, sha256_bytes, validate_ledger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-root", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    p = paths(args.control_root, args.run_id)
    state, previous_raw = load_state(p)
    if state["revision"] != 0:
        raise SystemExit("fixture metadata is already seeded")

    intent_bytes = (ROOT / "experiments/fixtures/e03m/intent.md").read_bytes()
    intent_path = p["docs"] / "doc-e03m-intent" / "v1.md"
    atomic_write(intent_path, intent_bytes)

    seeded = copy.deepcopy(state)
    seeded["revision"] = 1
    seeded["previous_publication_hash"] = sha256_bytes(previous_raw)
    seeded["repository"].update(
        {
            "common_dir": str(Path(args.control_root) / ".git"),
            "initial_head": "f267b0c94a3aa290f03aaf945707708640c5527a",
            "branch": "main",
            "checkout": str(Path(args.control_root).resolve()),
        }
    )
    seeded["documents"] = [
        {
            "id": "doc-e03m-intent",
            "version": "v1",
            "path": str(intent_path),
            "hash": sha256_bytes(intent_bytes),
            "kind": "intent",
            "section_anchors": ["#-e03m-fixture-intent-v1"],
        }
    ]
    seeded["intent"] = {
        "current_revision": "intent-v1",
        "document_ref": "doc-e03m-intent",
        "approved_amendments": [],
        "acceptance_policy": "automatic",
        "checkpoint_policy": "gate",
        "prior_accepted_refs": [],
    }
    seeded["requirements"] = [
        {
            "id": "R-E03M-1",
            "version": "v1",
            "status": "active",
            "provenance_refs": ["doc-e03m-intent:v1"],
            "criterion_refs": ["C-E03M-1"],
            "decision_ref": None,
        }
    ]
    seeded["criteria"] = [
        {
            "id": "C-E03M-1",
            "version": "v1",
            "requirement_refs": ["R-E03M-1"],
            "oracle": "app.txt contains exactly VALUE=42 in the pristine candidate export",
            "status": "active",
            "source_ref": "doc-e03m-intent:v1",
        }
    ]
    seeded["contracts"] = [
        {
            "id": "contract-e03m-acceptance-v1",
            "version": "v1",
            "status": "active",
            "provenance_refs": ["doc-e03m-intent:v1"],
            "producer_refs": [],
            "consumer_refs": ["C-E03M-1"],
        }
    ]
    seeded["decisions"] = [
        {
            "id": "D-E03M-MANUAL",
            "type": "acceptance_transport",
            "status": "approved",
            "decision": "user_assisted",
            "reason": "Strict automatic critical/G5 transport is not qualified; use the implemented manual fallback.",
            "evidence_refs": ["experiments/E03-reviewer-isolation-and-transports.md"],
            "affected_refs": ["contract-e03m-acceptance-v1", "C-E03M-1"],
            "introduced_revision": "intent-v1",
            "supersedes": [],
        }
    ]
    seeded["tickets"] = [
        {
            "id": "T-E03M-1",
            "goal_ref": "G-E03M-1",
            "criterion_refs": ["C-E03M-1"],
            "contract_refs": ["contract-e03m-acceptance-v1"],
            "dependency_refs": [],
            "state": "READY",
            "verification_ref": "manual-g5",
            "complexity": "bounded",
            "risk": "critical",
            "zone": [{"path": "app.txt", "operations": ["modify"]}],
            "current_attempt": None,
            "replacement_refs": [],
        }
    ]
    seeded["lifecycle"] = {
        "phase": "EXECUTE",
        "control": "ACTIVE",
        "reason": "fixture_seeded",
        "issue_refs": [],
        "stop_target": None,
        "next_action": {
            "kind": "dispatch_worker",
            "subject_refs": ["T-E03M-1"],
            "preconditions": ["fixture metadata seeded", "worker lease scoped to app.txt"],
            "read_refs": ["phases/execute.md", "contracts/worker.md"],
        },
    }
    validate_ledger(seeded)
    atomic_write(p["ledger"], canonical_bytes(seeded))
    print(f"seeded revision={seeded['revision']} ledger={p['ledger']}")


if __name__ == "__main__":
    main()

