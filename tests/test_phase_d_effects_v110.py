from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools import ledger


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]
RUN_ID = "phase-d-effects-run"
OWNER = "owner-a"
TICKET_ID = "T-effect"
ATTEMPT_ID = "A-effect"
OPERATION_ID = "OP-effect"
AUTHORITY_REF = "AUTH-effect"


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def write_json(path: Path, value: Any) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, capture_output=True).stdout.strip()


class PhaseDEffectTests(unittest.TestCase):
    def init_git_case(self, root: Path, run_id: str = RUN_ID) -> dict[str, Any]:
        control, repo = root / "control", root / "repo"
        control.mkdir()
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        (repo / "app.txt").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "baseline"], check=True)
        base_sha = git(repo, "rev-parse", "HEAD")
        tree_sha = git(repo, "rev-parse", "HEAD^{tree}")
        run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", run_id, "--owner-token", OWNER)
        return {
            "root": root,
            "control": control,
            "repo": repo,
            "paths": ledger.paths(control, run_id),
            "run_id": run_id,
            "base_sha": base_sha,
            "base_tree_sha": tree_sha,
        }

    def prepare_effect(self, case: dict[str, Any], *, operation_id: str = OPERATION_ID, revision: int | None = None) -> None:
        state, _ = ledger.load_state(case["paths"])
        run(
            "prepare-effect", "--control-root", str(case["control"]), "--run-id", case["run_id"],
            "--owner-token", OWNER, "--revision", str(state["revision"] if revision is None else revision),
            "--operation-id", operation_id, "--kind", "candidate_commit", "--target", str(case["repo"]),
            "--expected-before", case["base_sha"], "--authority-ref", AUTHORITY_REF,
        )

    def commit_candidate(self, case: dict[str, Any]) -> tuple[str, str]:
        (case["repo"] / "app.txt").write_text("candidate\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(case["repo"]), "add", "app.txt"], check=True)
        subprocess.run(["git", "-C", str(case["repo"]), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "candidate"], check=True)
        return git(case["repo"], "rev-parse", "HEAD"), git(case["repo"], "rev-parse", "HEAD^{tree}")

    def effect_receipt(
        self,
        case: dict[str, Any],
        *,
        commit_sha: str,
        tree_sha: str,
        operation_id: str = OPERATION_ID,
    ) -> Path:
        receipt_path = case["root"] / f"{operation_id}-receipt.json"
        write_json(receipt_path, {
            "status": "PASS",
            "run_id": case["run_id"],
            "ticket_id": TICKET_ID,
            "attempt_id": ATTEMPT_ID,
            "operation_id": operation_id,
            "kind": "candidate_commit",
            "target": str(case["repo"]),
            "checkout": str(case["repo"]),
            "expected_before": case["base_sha"],
            "base_sha": case["base_sha"],
            "intended_after": commit_sha,
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
            "authority_ref": AUTHORITY_REF,
        })
        return receipt_path

    def reconcile(
        self,
        case: dict[str, Any],
        result: str,
        *,
        receipt: Path | None = None,
        operation_id: str = OPERATION_ID,
        revision: int | None = None,
        expect: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        state, _ = ledger.load_state(case["paths"])
        args = [
            "reconcile-effect", "--control-root", str(case["control"]), "--run-id", case["run_id"],
            "--owner-token", OWNER, "--revision", str(state["revision"] if revision is None else revision),
            "--operation-id", operation_id, "--result", result,
        ]
        if receipt is not None:
            args.extend(["--receipt", str(receipt)])
        return run(*args, expect=expect)

    def assert_safe_effect_action(
        self,
        case: dict[str, Any],
        operation_id: str,
        *,
        forbidden: str | None = None,
        require_subject: bool = True,
    ) -> dict[str, Any]:
        state, _ = ledger.load_state(case["paths"])
        action = state["lifecycle"].get("next_action")
        self.assertIsInstance(action, dict)
        self.assertTrue(action.get("kind"))
        if require_subject:
            self.assertIn(operation_id, action.get("subject_refs", []))
        if forbidden:
            self.assertNotEqual(forbidden, action["kind"])
        return action

    def test_uncertain_effect_resolves_with_fresh_exact_receipt_and_replays_without_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.init_git_case(Path(directory))
            self.prepare_effect(case)
            # This effect-only fixture is still in PREFLIGHT; action projection is
            # asserted in the real EXECUTE flow below where a candidate can resume.

            self.reconcile(case, "uncertain")
            # No candidate attempt exists in this effect-only fixture.
            candidate_sha, candidate_tree = self.commit_candidate(case)
            receipt = self.effect_receipt(case, commit_sha=candidate_sha, tree_sha=candidate_tree)
            resolved = json.loads(self.reconcile(case, "applied", receipt=receipt).stdout)
            self.assertEqual("applied", resolved["state"])
            state, _ = ledger.load_state(case["paths"])
            operation = next(item for item in state["operations"] if item["id"] == OPERATION_ID)
            self.assertEqual("applied", operation["state"])
            self.assertTrue(ledger.snapshot_is_pinned(state), "applied-but-unlinked effect must remain recovery-pinned")
            applied_revision = state["revision"]
            self.assert_safe_effect_action(case, OPERATION_ID, require_subject=False)

            replay = json.loads(self.reconcile(case, "applied", receipt=receipt).stdout)
            self.assertTrue(replay["idempotent"])
            self.assertEqual(applied_revision, replay["revision"])
            self.assertEqual(applied_revision, ledger.load_state(case["paths"])[0]["revision"])

            original = case["paths"]["ledger"].read_bytes()
            conflicting = case["root"] / "conflicting-receipt.json"
            conflicting_payload = json.loads(receipt.read_text(encoding="utf-8"))
            conflicting_payload["authority_ref"] = "AUTH-conflict"
            write_json(conflicting, conflicting_payload)
            self.reconcile(case, "applied", receipt=conflicting, expect=2)
            self.assertEqual(original, case["paths"]["ledger"].read_bytes())
            self.reconcile(case, "abandoned", receipt=receipt, expect=2)
            self.assertEqual(original, case["paths"]["ledger"].read_bytes())

    def test_abandoned_effect_requires_receipt_and_same_id_cannot_rearm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.init_git_case(Path(directory), run_id="phase-d-abandoned-run")
            self.prepare_effect(case)
            self.reconcile(case, "uncertain")
            unchanged_receipt = case["root"] / "unchanged-receipt.json"
            write_json(unchanged_receipt, {
                "status": "PASS",
                "operation_id": OPERATION_ID,
                "kind": "candidate_commit",
                "target": str(case["repo"]),
                "checkout": str(case["repo"]),
                "expected_before": case["base_sha"],
                "base_sha": case["base_sha"],
                "intended_after": None,
                "observed_head": case["base_sha"],
                "tree_sha": case["base_tree_sha"],
                "authority_ref": AUTHORITY_REF,
                "outcome": "unchanged",
            })
            before_resolution = case["paths"]["ledger"].read_bytes()
            self.reconcile(case, "abandoned", expect=2)
            self.assertEqual(before_resolution, case["paths"]["ledger"].read_bytes())
            self.reconcile(case, "abandoned", receipt=unchanged_receipt)
            state, _ = ledger.load_state(case["paths"])
            operation = next(item for item in state["operations"] if item["id"] == OPERATION_ID)
            self.assertEqual("abandoned", operation["state"])
            self.assertFalse(ledger.snapshot_is_pinned(state), "terminal abandoned effect must not remain unresolved")
            self.assert_safe_effect_action(case, OPERATION_ID, forbidden="apply_prepared_effect", require_subject=False)
            revision = state["revision"]
            raw = case["paths"]["ledger"].read_bytes()

            replay = json.loads(self.reconcile(case, "abandoned", receipt=unchanged_receipt).stdout)
            self.assertTrue(replay["idempotent"])
            self.assertEqual(revision, replay["revision"])
            self.assertEqual(raw, case["paths"]["ledger"].read_bytes())

            retry = run(
                "prepare-effect", "--control-root", str(case["control"]), "--run-id", case["run_id"],
                "--owner-token", OWNER, "--revision", str(revision), "--operation-id", OPERATION_ID,
                "--kind", "candidate_commit", "--target", str(case["repo"]), "--expected-before", case["base_sha"],
                "--authority-ref", AUTHORITY_REF, expect=2,
            )
            self.assertNotIn('"state": "prepared"', retry.stdout)
            self.assertEqual(raw, case["paths"]["ledger"].read_bytes())

    def candidate_case(self, root: Path) -> dict[str, Any]:
        case = self.init_git_case(root)
        control, repo = case["control"], case["repo"]

        intent = root / "intent.md"
        intent.write_text("# Intent\n\nPublish one candidate.\n", encoding="utf-8")
        run("publish-intent", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", "0", "--intent-file", str(intent), "--doc-id", "D-intent", "--doc-version", "v1", "--intent-revision", "v1")
        run("gate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", "1", "--phase", "DESIGN", "--control", "BLOCKED", "--reason", "missing_design_publication", "--next-action", "adopt_requirements")
        state, _ = ledger.load_state(case["paths"])
        manifest = {
            "publication_id": "RP-effect", "version": "v1", "epoch": 0,
            "intent_revision": "v1", "intent_document_ref": "D-intent", "intent_document_hash": state["intent"]["document_hash"],
            "requirements": [{"id": "R-effect", "version": "v1", "status": "active", "provenance_refs": ["D-intent"], "criterion_refs": ["C-effect"]}],
            "criteria": [{"id": "C-effect", "version": "v1", "requirement_refs": ["R-effect"], "oracle": "app.txt contains candidate", "status": "active", "source_ref": "D-intent"}],
        }
        manifest_path = root / "requirements.json"
        write_json(manifest_path, manifest)
        run("adopt-requirements", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER, "--revision", "2", "--manifest", str(manifest_path))

        state, _ = ledger.load_state(case["paths"])
        documents = []
        for document_id, kind in (("D-design", "design"), ("D-interfaces", "interfaces"), ("D-manifest", "manifest"), ("D-plan", "plan"), ("D-tickets", "tickets"), ("D-routes", "routes")):
            source = root / f"{document_id}.md"
            source.write_text(f"# {document_id}\n", encoding="utf-8")
            documents.append({"id": document_id, "version": "v1", "kind": kind, "source": str(source), "hash": ledger.sha256_file(source), "section_anchors": []})
        bundle = {
            "bundle_id": "B-effect", "version": "v1", "epoch": 0,
            "intent_revision": "v1", "intent_document_ref": "D-intent", "intent_document_hash": state["intent"]["document_hash"],
            "documents": documents,
            "contracts": [{"id": "K-effect", "version": "v1", "status": "active", "provenance_refs": ["D-interfaces"], "producer_refs": [], "consumer_refs": ["C-effect"], "implementation_availability": "available", "implementation_availability_evidence_refs": ["fixture:effect-contract-available"]}],
            "tickets": [{"id": TICKET_ID, "goal_ref": "G-effect", "criterion_refs": ["C-effect"], "contract_refs": ["K-effect"], "dependency_refs": [], "state": "PLANNED", "verification_ref": "effect-oracle", "complexity": "bounded", "risk": "routine", "zone": [{"path": "app.txt", "operations": ["modify"]}], "current_attempt": None, "replacement_refs": []}],
            "routes": [{"id": "ROUTE-effect", "capability": "worker", "reasoning": "focused effect regression", "requested_binding": "fixture-worker", "observed_binding": "fixture-worker", "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"}],
        }
        bundle_path = root / "design-bundle.json"
        write_json(bundle_path, bundle)
        state, _ = ledger.load_state(case["paths"])
        run("publish-design-bundle", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", str(state["revision"]), "--bundle", str(bundle_path))

        state, _ = ledger.load_state(case["paths"])
        publication_hash = state["design_publication"]["publication_hash"]
        for review_kind, attempt_id in (("coverage", "RV-effect-coverage"), ("plan", "RV-effect-plan")):
            state, _ = ledger.load_state(case["paths"])
            review_packet = {
                "identity": {"run_id": RUN_ID, "attempt_id": attempt_id, "epoch": 0, "source_revision": state["revision"], "intent_revision": "v1"},
                "kind": "review", "mandate": f"Review effect test {review_kind}", "subject_fingerprint": publication_hash,
                "criteria": [{"criterion_id": "C-effect"}], "axes": [review_kind], "return_target": {"path": "return.json"},
            }
            packet_path = root / f"{attempt_id}.json"
            write_json(packet_path, review_packet)
            run("prepare-design-review", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--review-attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}",
                "--packet", str(packet_path), "--review-kind", review_kind, "--reviewer-identity", "reviewer@example.invalid", "--reviewer-role", "independent-design-reviewer")
            state, _ = ledger.load_state(case["paths"])
            attempt = ledger.attempt_by_id(state, attempt_id)
            returned = {
                "identity": {"run_id": RUN_ID, "attempt_id": attempt_id, "packet_hash": attempt["packet_hash"], "epoch": 0,
                             "source_revision": attempt["packet_source_revision"], "registration_revision": attempt["packet_registration_revision"],
                             "subject_revision": attempt["subject_revision"], "intent_revision": "v1"},
                "subject_fingerprint": publication_hash, "verdict": "PASS",
                "coverage": [{"criterion_id": "C-effect", "outcome": "fulfilled", "evidence_refs": [f"EV-{attempt_id}"]}],
                "checks": [{"check_id": f"check-{review_kind}", "axis": review_kind, "outcome": "fulfilled", "actual": "all design assertions pass", "evidence_ref": f"EV-{attempt_id}"}],
                "context_refs": ["clean-design-review"], "findings": [],
            }
            inbox = case["paths"]["scratch"] / attempt_id / "return.json"
            write_json(inbox, returned)
            run("ingest-return", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--return-file", str(inbox), "--kind", "review")

        state, _ = ledger.load_state(case["paths"])
        run("gate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER, "--revision", str(state["revision"]),
            "--phase", "DESIGN", "--control", "ACTIVE", "--gate-id", "G2", "--next-action", "g2_pass")
        state, _ = ledger.load_state(case["paths"])
        run("gate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER, "--revision", str(state["revision"]),
            "--phase", "PLAN", "--control", "ACTIVE", "--gate-id", "G3", "--next-action", "g3_pass")
        state, _ = ledger.load_state(case["paths"])
        run("gate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER, "--revision", str(state["revision"]),
            "--phase", "EXECUTE", "--control", "ACTIVE", "--next-action", "ready_ticket")
        state, _ = ledger.load_state(case["paths"])
        run("ready-ticket", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", str(state["revision"]), "--ticket-id", TICKET_ID)

        packet = {
            "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": ATTEMPT_ID, "epoch": 0},
            "kind": "worker", "mode": "implement", "goal": "Exercise candidate effect adoption.",
            "acceptance": [{"criterion_id": "C-effect"}], "workspace": {"root": str(repo), "expected_base": case["base_sha"]},
            "write": {"allow": [{"path": "app.txt", "operations": ["modify"]}]},
            "verification": [{"check_id": "effect-focused", "required": True, "scenario": "effect adoption regression"}],
            "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}], "return_target": {"path": "return.json"},
        }
        packet_path = root / "worker-packet.json"
        write_json(packet_path, packet)
        state, _ = ledger.load_state(case["paths"])
        run("dispatch", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", str(state["revision"]), "--ticket-id", TICKET_ID, "--attempt-id", ATTEMPT_ID,
            "--lease-id", "L-effect", "--route-id", "ROUTE-effect", "--packet", str(packet_path))
        state, _ = ledger.load_state(case["paths"])
        attempt = ledger.attempt_by_id(state, ATTEMPT_ID)
        returned = {
            "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": ATTEMPT_ID, "packet_hash": attempt["packet_hash"], "epoch": 0},
            "status": "DONE", "result": "candidate work and required focused checks are complete",
            "files": [{"path": "app.txt", "operation": "modify"}],
            "checks": [{"check_id": "effect-focused", "outcome": "pass", "actual": "candidate behavior verified", "evidence_ref": "EV-effect-worker"}],
            "criteria": [{"criterion_id": "C-effect", "outcome": "satisfied", "evidence_refs": ["EV-effect-worker"]}],
        }
        inbox = case["paths"]["scratch"] / ATTEMPT_ID / "return.json"
        write_json(inbox, returned)
        run("ingest-return", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
            "--revision", str(state["revision"]), "--attempt-id", ATTEMPT_ID, "--return-file", str(inbox), "--kind", "worker")
        return case

    def test_applied_git_effect_is_adopted_once_without_repeating_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.candidate_case(Path(directory))
            self.prepare_effect(case)
            prepared_state, _ = ledger.load_state(case["paths"])
            self.assert_safe_effect_action(case, OPERATION_ID)

            candidate_sha, candidate_tree = self.commit_candidate(case)
            # This is the crash boundary: Git is committed but the ledger still only knows PREPARED.
            self.assertEqual(candidate_sha, git(case["repo"], "rev-parse", "HEAD"))
            before_link = case["paths"]["ledger"].read_bytes()
            self.assertEqual("prepared", next(item for item in prepared_state["operations"] if item["id"] == OPERATION_ID)["state"])
            self.assertIsNone(next(item for item in prepared_state["tickets"] if item["id"] == TICKET_ID)["current_candidate"])

            # The writer may have committed immediately before its response was lost.
            # Record that observation first, then resolve it from fresh receipt evidence.
            self.reconcile(case, "uncertain")
            uncertain_state, _ = ledger.load_state(case["paths"])
            self.assertEqual("uncertain", next(item for item in uncertain_state["operations"] if item["id"] == OPERATION_ID)["state"])
            self.assert_safe_effect_action(case, OPERATION_ID, forbidden="apply_prepared_effect")
            receipt = self.effect_receipt(case, commit_sha=candidate_sha, tree_sha=candidate_tree)
            resolved = json.loads(self.reconcile(case, "applied", receipt=receipt).stdout)
            self.assertEqual("applied", resolved["state"])
            applied_state, _ = ledger.load_state(case["paths"])
            self.assertNotEqual(before_link, case["paths"]["ledger"].read_bytes())
            self.assertEqual("applied", next(item for item in applied_state["operations"] if item["id"] == OPERATION_ID)["state"])
            self.assertTrue(ledger.snapshot_is_pinned(applied_state))
            self.assertIsNone(next(item for item in applied_state["tickets"] if item["id"] == TICKET_ID)["current_candidate"])
            applied_action = self.assert_safe_effect_action(case, OPERATION_ID)
            self.assertEqual("adopt_applied_effect", applied_action["kind"])
            self.assertEqual("candidate.publish", applied_action["event_id"])
            applied_revision = applied_state["revision"]
            exact_effect_replay = json.loads(self.reconcile(case, "applied", receipt=receipt).stdout)
            self.assertTrue(exact_effect_replay["idempotent"])
            self.assertEqual(applied_revision, exact_effect_replay["revision"])
            self.assertEqual(applied_revision, ledger.load_state(case["paths"])[0]["revision"])

            conflict_bytes = case["paths"]["ledger"].read_bytes()
            conflicting_receipt = case["root"] / "conflicting-adoption-receipt.json"
            conflicting_payload = json.loads(receipt.read_text(encoding="utf-8"))
            conflicting_payload["authority_ref"] = "AUTH-other"
            write_json(conflicting_receipt, conflicting_payload)
            self.reconcile(case, "applied", receipt=conflicting_receipt, expect=2)
            self.assertEqual(conflict_bytes, case["paths"]["ledger"].read_bytes())

            adopted = json.loads(run(
                "candidate", "--control-root", str(case["control"]), "--run-id", case["run_id"], "--owner-token", OWNER,
                "--revision", str(applied_state["revision"]), "--attempt-id", ATTEMPT_ID, "--operation-id", OPERATION_ID,
            ).stdout)
            self.assertEqual(candidate_sha, adopted["candidate"])
            self.assertFalse(adopted.get("idempotent", False))
            self.assertEqual(candidate_sha, git(case["repo"], "rev-parse", "HEAD"))
            self.assertEqual("2", git(case["repo"], "rev-list", "--count", "HEAD"))

            finalized_state, _ = ledger.load_state(case["paths"])
            operation = next(item for item in finalized_state["operations"] if item["id"] == OPERATION_ID)
            ticket = next(item for item in finalized_state["tickets"] if item["id"] == TICKET_ID)
            self.assertEqual("finalized", operation["state"])
            self.assertFalse(ledger.snapshot_is_pinned(finalized_state))
            self.assertTrue(operation.get("resolution_ref"))
            self.assertTrue(operation.get("proof_ref"))
            self.assertEqual(ticket["current_candidate"], operation.get("candidate_ref"))
            self.assertEqual(finalized_state["revision"], operation.get("finalized_revision"))
            self.assertEqual(candidate_sha, next(item for item in finalized_state["candidates"] if item["id"] == ticket["current_candidate"])["sha"])
            self.assert_safe_effect_action(case, OPERATION_ID, require_subject=False)
            revision = finalized_state["revision"]
            raw = case["paths"]["ledger"].read_bytes()

            replay = json.loads(run(
                "candidate", "--control-root", str(case["control"]), "--run-id", case["run_id"], "--owner-token", OWNER,
                "--revision", str(revision), "--attempt-id", ATTEMPT_ID, "--operation-id", OPERATION_ID,
            ).stdout)
            self.assertTrue(replay["idempotent"])
            self.assertEqual(revision, replay["revision"])
            self.assertEqual(raw, case["paths"]["ledger"].read_bytes())
            self.assertEqual(candidate_sha, git(case["repo"], "rev-parse", "HEAD"))


if __name__ == "__main__":
    unittest.main()
