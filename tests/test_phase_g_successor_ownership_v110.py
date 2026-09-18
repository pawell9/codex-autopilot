from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from typing import Any

from tools import ledger


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]
EXCLUSIONS = ["attempts", "live_reservations", "repair_authorizations", "current_pointers"]


def invoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*CLI, *args], text=True, capture_output=True)


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = invoke(*args)
    if result.returncode != expect:
        raise AssertionError(f"expected exit {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def write_json(path: Path, value: Any) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


class PhaseGSuccessorOwnershipTests(unittest.TestCase):
    def parent(self, root: Path, *, run_id: str = "predecessor", terminal: bool = True) -> dict[str, Any]:
        control, repo = root / "control-a", root / "repo"
        control.mkdir()
        repo.mkdir()
        (repo / "source.txt").write_text("initial\n", encoding="utf-8")
        run("init", "--control-root", str(control), "--repo-root", str(repo),
            "--run-id", run_id, "--owner-token", "old-owner")
        paths = ledger.paths(control, run_id)
        state, previous = ledger.load_state(paths)
        state["decisions"] = [
            {
                "id": "D-SCOPE", "type": "scope_decision", "status": "accepted",
                "decision": "continue", "reason": "approved project scope",
                "evidence_refs": [], "affected_refs": [], "invalidated_by": [],
            },
            {
                "id": "D-REPAIR", "type": "repair_authorization", "status": "authorized",
                "decision": "repair", "reason": "old run authorization must not carry",
                "evidence_refs": [], "affected_refs": [], "invalidated_by": [],
            },
        ]
        state["attempts"] = [{
            "id": "A-OLD-LIVE", "kind": "worker", "mode": "implement", "subject_ref": "T-OLD",
            "packet_ref": None, "packet_hash": None, "epoch": 0,
            "state": "RETURNED" if terminal else "PREPARED",
            "lease": {"id": "L-OLD", "state": "released" if terminal else "active", "zone": []},
        }]
        if terminal:
            state["lifecycle"]["control"] = "CANCELLED"
            state["lifecycle"]["reason"] = "user_cancelled"
        state["revision"] += 1
        state["previous_publication_hash"] = ledger.sha256_bytes(previous)
        ledger.refresh_control_projection(state)
        ledger.validate_ledger(state, verify_files=False)
        parent_raw = ledger.canonical_bytes(state)
        ledger.atomic_write(paths["ledger"], parent_raw)
        return {"control": control, "repo": repo, "paths": paths, "state": state, "raw": parent_raw}

    def manifest(self, parent: dict[str, Any], *, resource: Path | None = None) -> dict[str, Any]:
        state = parent["state"]
        scope = next(item for item in state["decisions"] if item["id"] == "D-SCOPE")
        scope_hash = ledger.sha256_bytes(ledger.canonical_bytes(scope))
        resources = []
        if resource:
            resources.append({"ref": str(resource), "availability": "available", "sha256": ledger.sha256_file(resource)})
        return {
            "manifest_version": 1,
            "predecessor": {
                "control_root": state["repository"]["control_root"], "run_id": state["run_id"],
                "revision": state["revision"], "terminal_control": state["lifecycle"]["control"],
                "ledger_sha256": ledger.sha256_bytes(parent["raw"]),
            },
            "scope_decision": {
                "ref": scope["id"], "sha256": scope_hash, "status": "accepted",
                "authority_ref": "owner-approved:D-SCOPE",
            },
            "candidate": {
                "candidate_ref": None, "commit_sha": None, "tree_sha": None,
                "proof_ref": None, "proof_hash": None,
            },
            "accepted_evidence": [{
                "kind": "accepted_decision", "ref": scope["id"], "sha256": scope_hash,
                "subject_sha": None,
            }],
            "resources": resources,
            "exclusions": EXCLUSIONS,
            "unknowns": ["predecessor has no accepted candidate selected for carry-forward"],
        }

    def init_successor(self, root: Path, parent: dict[str, Any], manifest: dict[str, Any], *, run_id: str = "successor") -> subprocess.CompletedProcess[str]:
        manifest_path = root / f"{run_id}-manifest.json"
        write_json(manifest_path, manifest)
        control = root / "control-b"
        return invoke(
            "init-successor", "--control-root", str(control), "--repo-root", str(parent["repo"]),
            "--run-id", run_id, "--owner-token", "new-owner", "--predecessor-owner-token", "old-owner",
            "--manifest", str(manifest_path),
        )

    def test_successor_binds_exact_terminal_bytes_and_starts_with_no_inherited_live_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = self.parent(root)
            original = parent["paths"]["ledger"].read_bytes()
            result = self.init_successor(root, parent, self.manifest(parent))
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            successor_paths = ledger.paths(root / "control-b", "successor")
            successor, raw = ledger.load_state(successor_paths)
            self.assertEqual(original, parent["paths"]["ledger"].read_bytes())
            self.assertEqual(0, successor["revision"])
            self.assertEqual("new-owner", successor["owner"]["token"])
            self.assertEqual("objects/" + successor["successor_manifest"]["manifest_hash"], successor["successor_manifest"]["manifest_ref"])
            self.assertEqual([], successor.get("attempts", []))
            self.assertEqual([], successor.get("decisions", []))
            self.assertEqual([], successor.get("tickets", []))
            self.assertEqual([], successor.get("candidates", []))
            self.assertEqual([], successor.get("repair_waves", []))
            self.assertEqual([], successor.get("operations", []))
            self.assertEqual(raw, ledger.canonical_bytes(successor))

            registry_paths = ledger.repository_owner_paths(parent["repo"])
            registry = ledger.read_json(Path(registry_paths["registry"]), "registry")
            registry["status"] = "pending"
            write_json(Path(registry_paths["registry"]), registry)
            retry = self.init_successor(root, parent, self.manifest(parent))
            self.assertEqual(0, retry.returncode, retry.stdout + retry.stderr)
            self.assertEqual("active", ledger.read_json(Path(registry_paths["registry"]), "registry")["status"])

    def test_manifest_mismatch_wrong_owner_and_partial_candidate_fail_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = self.parent(root)
            bad_hash = self.manifest(parent)
            bad_hash["predecessor"]["ledger_sha256"] = "0" * 64
            result = self.init_successor(root, parent, bad_hash)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(ledger.paths(root / "control-b", "successor")["ledger"].exists())

            wrong_owner = root / "wrong-owner.json"
            write_json(wrong_owner, self.manifest(parent))
            result = invoke(
                "init-successor", "--control-root", str(root / "control-c"), "--repo-root", str(parent["repo"]),
                "--run-id", "wrong-owner-run", "--owner-token", "old-owner", "--predecessor-owner-token", "old-owner",
                "--manifest", str(wrong_owner),
            )
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(ledger.paths(root / "control-c", "wrong-owner-run")["ledger"].exists())

            partial = self.manifest(parent)
            partial["candidate"]["commit_sha"] = "a" * 40
            result = self.init_successor(root, parent, partial, run_id="partial-candidate")
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(ledger.paths(root / "control-b", "partial-candidate")["ledger"].exists())

            unaccepted_candidate = self.manifest(parent)
            unaccepted_candidate["candidate"] = {
                "candidate_ref": "C-NOT-IN-PREDECESSOR", "commit_sha": "a" * 40,
                "tree_sha": "b" * 40, "proof_ref": "objects/" + "c" * 64,
                "proof_hash": "c" * 64,
            }
            result = self.init_successor(root, parent, unaccepted_candidate, run_id="unaccepted-candidate")
            self.assertNotEqual(0, result.returncode)
            self.assertIn("candidate", result.stdout + result.stderr)
            self.assertFalse(ledger.paths(root / "control-b", "unaccepted-candidate")["ledger"].exists())

    def test_available_resource_hash_is_verified_and_legacy_init_has_no_trusted_relation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = self.parent(root)
            resource = root / "handoff.txt"
            resource.write_text("accepted artifact\n", encoding="utf-8")
            manifest = self.manifest(parent, resource=resource)
            resource.write_text("changed after manifest\n", encoding="utf-8")
            result = self.init_successor(root, parent, manifest)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(ledger.paths(root / "control-b", "successor")["ledger"].exists())

            other_repo, other_control = root / "other-repo", root / "legacy-control"
            other_repo.mkdir()
            run("init", "--control-root", str(other_control), "--repo-root", str(other_repo),
                "--run-id", "legacy-run", "--owner-token", "legacy-owner")
            legacy, _ = ledger.load_state(ledger.paths(other_control, "legacy-run"))
            self.assertNotIn("successor_manifest", legacy)

    def test_repository_registry_blocks_second_nonterminal_owner_then_reclaims_verified_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = self.parent(root, terminal=False)
            second_control = root / "control-b"
            blocked = invoke(
                "init", "--control-root", str(second_control), "--repo-root", str(parent["repo"]),
                "--run-id", "second", "--owner-token", "second-owner",
            )
            self.assertNotEqual(0, blocked.returncode)
            self.assertFalse(ledger.paths(second_control, "second")["ledger"].exists())

            state, raw = ledger.load_state(parent["paths"])
            state["lifecycle"]["control"] = "FAILED"
            state["lifecycle"]["reason"] = "operator_stopped"
            state["attempts"][0]["state"] = "RETURNED"
            state["revision"] += 1
            state["previous_publication_hash"] = ledger.sha256_bytes(raw)
            ledger.refresh_control_projection(state)
            ledger.validate_ledger(state, verify_files=False)
            ledger.atomic_write(parent["paths"]["ledger"], ledger.canonical_bytes(state))

            still_live = invoke(
                "init", "--control-root", str(second_control), "--repo-root", str(parent["repo"]),
                "--run-id", "second", "--owner-token", "second-owner",
            )
            self.assertNotEqual(0, still_live.returncode)
            self.assertIn("active or quarantined reservation", still_live.stdout + still_live.stderr)

            state, raw = ledger.load_state(parent["paths"])
            state["attempts"][0]["state"] = "RETURNED"
            state["attempts"][0]["lease"]["state"] = "released"
            state["revision"] += 1
            state["previous_publication_hash"] = ledger.sha256_bytes(raw)
            ledger.validate_ledger(state, verify_files=False)
            ledger.atomic_write(parent["paths"]["ledger"], ledger.canonical_bytes(state))

            reclaimed = invoke(
                "init", "--control-root", str(second_control), "--repo-root", str(parent["repo"]),
                "--run-id", "second", "--owner-token", "second-owner",
            )
            self.assertEqual(0, reclaimed.returncode, reclaimed.stdout + reclaimed.stderr)
            second, _ = ledger.load_state(ledger.paths(second_control, "second"))
            self.assertNotIn("successor_manifest", second)

    def test_worktree_repository_identity_uses_git_common_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, worktree = root / "repo", root / "worktree"
            repo.mkdir()
            subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
            env = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
                       GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid")
            (repo / "README").write_text("test\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True, env=env)
            subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(worktree), "HEAD"], check=True)
            self.assertEqual(ledger.repository_identity(repo)["key"], ledger.repository_identity(worktree)["key"])


class RepairWaveAggregatePredicateTests(unittest.TestCase):
    def state(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
        old_sha, new_sha = "a" * 40, "b" * 40
        state: dict[str, Any] = {
            "owner": {"epoch": 0}, "attempts": [], "operations": [],
            "review_qualifications": [
                {"id": "Q-SOURCE", "result": "BLOCK", "required_purposes": ["final_g5"],
                 "subject_fingerprint": old_sha, "created_revision": 2},
                {"id": "Q-TICKET", "result": "PASS", "required_purposes": ["ticket_review"],
                 "subject_ref": "T-1", "subject_fingerprint": new_sha, "created_revision": 12,
                 "accepted_review_refs": ["R-TICKET"], "intent_revision": "v1"},
                {"id": "Q-FINAL", "result": "PASS", "required_purposes": ["final_g5"],
                 "subject_ref": "T-1", "subject_fingerprint": new_sha, "created_revision": 20,
                 "intent_revision": "v1", "accepted_review_refs": ["R-FINAL"]},
            ],
            "reviews": [
                {"id": "R-TICKET", "accepted": True, "purpose": "ticket_review", "verdict": "PASS",
                 "subject_fingerprint": new_sha, "return_ref": "objects/" + "d" * 64,
                 "intent_revision": "v1", "invalidated_by": [], "attempt_ref": "A-TICKET-REVIEW"},
                {"id": "R-FINAL", "accepted": True, "purpose": "final_g5", "verdict": "PASS",
                 "invalidated_by": [], "attempt_ref": "A-FINAL"},
            ],
            "tickets": [{"id": "T-1", "risk": "routine", "state": "INTEGRATED", "current_candidate": "C-NEW"}],
            "candidates": [
                {"id": "C-OLD", "ticket_ref": "T-1", "sha": old_sha, "producer_attempt_ref": "A-OLD",
                 "superseded_by": "C-NEW", "quality": "DONE", "integration_status": "INTEGRATED"},
                {"id": "C-NEW", "ticket_ref": "T-1", "sha": new_sha, "tree_sha": "c" * 40,
                 "producer_attempt_ref": "A-NEW", "qualification_ref": "Q-TICKET",
                 "quality": "DONE", "integration_status": "INTEGRATED", "invalidated_by": []},
            ],
            "findings": [{"id": "F-1", "axis": "correctness", "impact": "blocking", "claim": "old defect",
                          "expected": "fixed", "actual": "broken", "evidence": "review",
                          "affected_refs": ["T-1"], "source_ref": "A-OLD"}],
            "issues": [], "decisions": [], "finding_binding_reconciliations": [],
        }
        for attempt_id, sha in (("A-OLD", old_sha), ("A-NEW", new_sha), ("A-TICKET-REVIEW", new_sha), ("A-FINAL", new_sha)):
            state["attempts"].append({
                "id": attempt_id, "kind": "review" if "REVIEW" in attempt_id or attempt_id == "A-FINAL" else "worker",
                "subject_ref": "T-1", "candidate_sha": sha, "epoch": 0, "state": "RETURNED",
                "lease": {"state": "released"},
                **({"return_ref": "objects/" + "d" * 64} if attempt_id == "A-TICKET-REVIEW" else {}),
            })
        wave = {"id": "WAVE-1", "source_qualification_ref": "Q-SOURCE", "source_candidate_fingerprint": old_sha,
                "finding_refs": ["F-1"], "created_revision": 3}
        final = state["review_qualifications"][2]
        return state, wave, final, new_sha

    def test_aggregate_close_requires_current_qualified_tickets_and_no_live_work(self) -> None:
        state, wave, qualification, repaired = self.state()
        with patch.object(ledger, "current_intent_binding", return_value={"revision": "v1"}):
            ready, reason = ledger.repair_wave_close_readiness(state, wave, qualification, repaired)
            self.assertTrue(ready, reason)
            state["attempts"][0]["lease"]["state"] = "quarantined"
            ready, reason = ledger.repair_wave_close_readiness(state, wave, qualification, repaired)
            self.assertFalse(ready)
            self.assertIn("quarantined", reason)
            state["attempts"][0]["lease"]["state"] = "released"
            state["operations"] = [{"id": "E-1", "state": "uncertain"}]
            ready, reason = ledger.repair_wave_close_readiness(state, wave, qualification, repaired)
            self.assertFalse(ready)
            self.assertIn("durable effect", reason)
            state["operations"] = []
            state["attempts"][1]["state"] = "DISPATCHED"
            ready, reason = ledger.repair_wave_close_readiness(state, wave, qualification, repaired)
            self.assertFalse(ready)
            self.assertIn("in flight", reason)
            state["attempts"][1]["state"] = "RETURNED"
            state["tickets"][0]["state"] = "READY"
            ready, reason = ledger.repair_wave_close_readiness(state, wave, qualification, repaired)
            self.assertFalse(ready)
            self.assertIn("integrated repaired candidate", reason)


if __name__ == "__main__":
    unittest.main()
