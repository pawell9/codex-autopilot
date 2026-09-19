"""Phase H qualification boundaries (Q25-Q42).

These are deliberately black-box scenarios: state is prepared only as a
disposable fixture and every lifecycle mutation under test goes through the
public ``tools/ledger.py`` CLI.  The manifest is kept next to the tests so a
release report can mechanically prove that no canonical Q25-Q42 case was
silently omitted.
"""

from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools import ledger
from tests import test_phase_c_attempt_finalization_v110 as phase_c_finalization
from tests import test_phase_c_repair_plans_v110 as phase_c_repairs
from tests import test_phase_d_effects_v110 as phase_d_effects
from tests import test_phase_e_review_qualification_v110 as phase_e_reviews
from tests import test_phase_g_execution_binding_v110 as phase_g_binding
from tests import test_phase_g_runtime_observations_v110 as phase_g_runtime
from tests import test_phase_g_successor_ownership_v110 as phase_g_successor
from tests import test_lifecycle_repairs as lifecycle_repairs
from tests import test_requirements_adoption as requirements_adoption


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]


# Canonical Phase H manifest.  Keep the scenario title aligned with the
# reliability review's Q25-Q42 matrix; this is consumed by the release report.
QUALIFICATION_MANIFEST: dict[str, str] = {
    "Q25": "test_Q25_crash_restart_boundaries_never_publish_half_state",
    "Q26": "test_Q26_same_byte_retry_is_noop_and_conflicting_replay_is_rejected",
    "Q27": "test_Q27_unused_authorization_can_be_revoked_before_dispatch",
    "Q28": "test_Q28_integration_consumes_one_immutable_qualification_ref",
    "Q29": "test_Q29_semi_mode_wait_is_not_a_human_checkpoint",
    "Q30": "test_Q30_disagreement_keeps_candidate_unintegrated",
    "Q31": "test_Q31_partially_valid_review_return_is_not_published",
    "Q32": "test_Q32_not_started_worker_is_explicit_and_not_spawned_twice",
    "Q33": "test_Q33_applied_git_effect_is_adopted_without_recommit",
    "Q34": "test_Q34_no_change_initial_failure_returns_to_verified_baseline",
    "Q35": "test_Q35_review_source_is_normalized_to_worker_provenance",
    "Q36": "test_Q36_review_cache_outside_zone_is_foreign_write",
    "Q37": "test_Q37_successor_does_not_inherit_unproven_predecessor_work",
    "Q38": "test_Q38_continuation_repair_failure_cannot_be_preserved",
    "Q39": "test_Q39_quiescing_rejects_dispatch_and_terminal_run_cannot_recover",
    "Q40": "test_Q40_takeover_fences_old_epoch_and_quarantines_attempt",
    "Q41": "test_Q41_deny_identity_and_object_tamper_fail_closed",
    "Q42": "test_Q42_unavailable_contract_blocks_consumer_readiness",
}


def invoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*CLI, *args], text=True, capture_output=True)


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = invoke(*args)
    if result.returncode != expect:
        raise AssertionError(
            f"expected exit {expect}, got {result.returncode}: "
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def write_json(path: Path, value: Any) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


class PhaseHBoundaryQualificationTests(unittest.TestCase):
    """Executable Q25-Q42 qualification scenarios."""

    def test_Q25_crash_restart_boundaries_never_publish_half_state(self) -> None:
        """Q25: inject each durable-boundary fault and assert the safe result."""
        helper = phase_d_effects.PhaseDEffectTests()
        # The object-store boundary is exercised after a real publication: a
        # tampered content-addressed receipt cannot be consumed as evidence.
        with self.subTest(boundary="object_store"), tempfile.TemporaryDirectory() as directory:
            case = helper.candidate_case(Path(directory))
            helper.prepare_effect(case)
            helper.reconcile(case, "uncertain")
            commit_sha, tree_sha = helper.commit_candidate(case)
            receipt = helper.effect_receipt(case, commit_sha=commit_sha, tree_sha=tree_sha)
            helper.reconcile(case, "applied", receipt=receipt)
            state, _ = ledger.load_state(case["paths"])
            ref = next(item for item in state["operations"] if item["id"] == phase_d_effects.OPERATION_ID)["receipt_ref"]
            (case["paths"]["objects"] / ref.split("/", 1)[1]).write_bytes(b"tampered")
            before = case["paths"]["ledger"].read_bytes()
            rejected = invoke(
                "candidate", "--control-root", str(case["control"]), "--run-id", case["run_id"],
                "--owner-token", phase_d_effects.OWNER, "--revision", str(state["revision"]),
                "--attempt-id", phase_d_effects.ATTEMPT_ID, "--operation-id", phase_d_effects.OPERATION_ID,
            )
            self.assertNotEqual(0, rejected.returncode)
            self.assertRegex(rejected.stderr.lower(), r"immutable object|hash|digest")
            self.assertEqual(before, case["paths"]["ledger"].read_bytes())

        # The ledger chain boundary is faulted with a valid receipt so a
        # missing chain file (not a missing argument) is the rejection cause.
        for boundary in ("ledger.prev", "ledger.json", "snapshot", "receipt"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                case = helper.init_git_case(root, run_id=f"q25-{boundary.replace('.', '-')}")
                helper.prepare_effect(case)
                helper.reconcile(case, "uncertain")
                commit_sha, tree_sha = helper.commit_candidate(case)
                receipt = helper.effect_receipt(case, commit_sha=commit_sha, tree_sha=tree_sha)
                state, _ = ledger.load_state(case["paths"])
                if boundary == "ledger.prev":
                    case["paths"]["prev"].unlink()
                elif boundary == "ledger.json":
                    case["paths"]["ledger"].unlink()
                elif boundary == "snapshot":
                    snapshots = list((case["paths"]["run"] / "snapshots").glob("*.json"))
                    self.assertTrue(snapshots)
                    snapshots[0].unlink()
                else:
                    receipt.unlink()
                before = case["paths"]["ledger"].read_bytes() if case["paths"]["ledger"].exists() else None
                result = invoke(
                    "reconcile-effect", "--control-root", str(case["control"]),
                    "--run-id", case["run_id"], "--owner-token", phase_d_effects.OWNER,
                    "--revision", str(state["revision"]), "--operation-id", phase_d_effects.OPERATION_ID,
                    "--result", "applied", "--receipt", str(receipt),
                )
                if result.returncode == 0:
                    # The atomic publisher may recreate a missing chain or
                    # snapshot on exact retry.  It is safe only if the effect
                    # reaches one complete state, never a half aggregate.
                    after, _ = ledger.load_state(case["paths"])
                    self.assertEqual("applied", next(item for item in after["operations"] if item["id"] == phase_d_effects.OPERATION_ID)["state"])
                elif before is not None and case["paths"]["ledger"].exists():
                    self.assertEqual(before, case["paths"]["ledger"].read_bytes())

        # Spawn registration is not spawn evidence; a restart after the
        # registration boundary must not launch a second worker.
        with self.subTest(boundary="spawn"), tempfile.TemporaryDirectory() as directory:
            fixture = phase_g_binding.PhaseGExecutionBindingTests()
            runtime = phase_g_runtime.PhaseGRuntimeObservationTests()
            root = Path(directory)
            control, _, paths, packet, _ = fixture.setup_dispatch(root)
            fixture.dispatch(control, packet, revision=1)
            runtime.observe(root, control, paths, "A-G", "not_started", 2, event_id="OBS-Q25-NOT-STARTED", instance=None)
            replay = fixture.dispatch(control, packet, revision=1)
            self.assertEqual("existing_request_do_not_spawn_again", json.loads(replay.stdout)["spawn_disposition"])
            self.assertEqual(0, ledger.load_state(paths)[0]["usage"]["counters"]["spawn_calls"])

        # A real Git commit is the external-effect boundary: retry adopts its
        # exact SHA and never creates a second commit.
        with self.subTest(boundary="git"), tempfile.TemporaryDirectory() as directory:
            case = helper.candidate_case(Path(directory))
            helper.prepare_effect(case)
            commit_sha, tree_sha = helper.commit_candidate(case)
            helper.reconcile(case, "uncertain")
            receipt = helper.effect_receipt(case, commit_sha=commit_sha, tree_sha=tree_sha)
            helper.reconcile(case, "applied", receipt=receipt)
            before_count = subprocess.run(["git", "-C", str(case["repo"]), "rev-list", "--count", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
            retry = helper.reconcile(case, "applied", receipt=receipt)
            self.assertTrue(json.loads(retry.stdout)["idempotent"])
            self.assertEqual(before_count, subprocess.run(["git", "-C", str(case["repo"]), "rev-list", "--count", "HEAD"], text=True, capture_output=True, check=True).stdout.strip())

    def test_Q26_same_byte_retry_is_noop_and_conflicting_replay_is_rejected(self) -> None:
        """Q26: exact committed effect adoption is idempotent; changed bytes are fenced."""
        helper = phase_d_effects.PhaseDEffectTests()
        with tempfile.TemporaryDirectory() as directory:
            case = helper.init_git_case(Path(directory), run_id="q26-run")
            helper.prepare_effect(case)
            helper.reconcile(case, "uncertain")
            candidate_sha, tree_sha = helper.commit_candidate(case)
            receipt = helper.effect_receipt(case, commit_sha=candidate_sha, tree_sha=tree_sha)
            helper.reconcile(case, "applied", receipt=receipt)
            state, _ = ledger.load_state(case["paths"])
            raw = case["paths"]["ledger"].read_bytes()
            retry = json.loads(helper.reconcile(case, "applied", receipt=receipt).stdout)
            self.assertTrue(retry["idempotent"])
            self.assertEqual(state["revision"], retry["revision"])
            conflicting = json.loads(receipt.read_text(encoding="utf-8"))
            conflicting["authority_ref"] = "AUTH-CONFLICT"
            conflict_path = case["root"] / "q26-conflict.json"
            write_json(conflict_path, conflicting)
            helper.reconcile(case, "applied", receipt=conflict_path, expect=2)
            self.assertEqual(raw, case["paths"]["ledger"].read_bytes())

    def test_Q27_unused_authorization_can_be_revoked_before_dispatch(self) -> None:
        """Q27: unused authority has a typed revoke path; consumed authority does not."""
        helper = phase_c_repairs.PhaseCRepairPlanTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths, subjects = phase_c_repairs.seed_repair_fixture(
                root, [("T-1", "F-1", "current")]
            )
            source = subjects[("T-1", "current")]
            plan = phase_c_repairs.grouped_plan(["F-1"], source["review"])
            plan_path = root / "q27-plan.json"
            packet_path = phase_c_repairs.repair_packet(root, repo, "T-1", "A-Q27", source["sha"], plan)
            write_json(plan_path, plan)
            helper.authorize(control, ticket_id="T-1", authorization_id="AUTH-Q27", plan_path=plan_path, packet_path=packet_path)
            before, _ = ledger.load_state(paths)
            revoked = json.loads(run(
                "revoke-repair", "--control-root", str(control), "--run-id", phase_c_repairs.RUN_ID,
                "--owner-token", phase_c_repairs.OWNER, "--revision", str(before["revision"]),
                "--authorization-id", "AUTH-Q27", "--revocation-id", "REVOKE-Q27", "--reason", "packet became stale",
            ).stdout)
            self.assertTrue(revoked["revoked"])
            state, _ = ledger.load_state(paths)
            auth = next(item for item in state["decisions"] if item["id"] == "AUTH-Q27")
            self.assertEqual("revoked", auth["status"])
            self.assertIsNone(next(item for item in state["tickets"] if item["id"] == "T-1")["current_worker_attempt"])

    def test_Q28_integration_consumes_one_immutable_qualification_ref(self) -> None:
        """Q28: repaired candidate integration uses the accepted qualification object."""
        helper = phase_e_reviews.PhaseEReviewQualificationTests()
        with tempfile.TemporaryDirectory() as directory:
            case = helper.prepare_candidate(Path(directory))
            review = helper.prepare_review(case, "ticket_review")
            return_path = helper.review_return(case, review, verdict="PASS")
            helper.ingest_review(case, review, return_path)
            state, _ = ledger.load_state(case["paths"])
            qualification = helper.qualification(state, review["candidate"]["sha"])
            integrated = json.loads(run(
                "integrate", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID,
                "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]),
                "--qualification-ref", qualification["id"],
            ).stdout)
            self.assertTrue(integrated["integrated"])
            final, _ = ledger.load_state(case["paths"])
            candidate = ledger.current_candidate_record(final, final["tickets"][0])
            self.assertEqual(qualification["id"], candidate["qualification_ref"])
            self.assertEqual("INTEGRATED", final["tickets"][0]["state"])

    def test_Q29_semi_mode_wait_is_not_a_human_checkpoint(self) -> None:
        """Q29: routine worker delivery remains ACTIVE in semi mode."""
        helper = lifecycle_repairs.LifecycleRepairTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, paths = helper.init_ticket(root)
            state, _ = ledger.load_state(paths)
            self.assertEqual("semi", state["run_settings"]["interaction_mode"])
            packet = helper.worker_packet(root, "A-Q29")
            helper.dispatch(control, packet, "A-Q29", state["revision"])
            waiting, _ = ledger.load_state(paths)
            self.assertEqual("ACTIVE", waiting["lifecycle"]["control"])
            self.assertEqual("await_worker_return", waiting["lifecycle"]["next_action"]["kind"])
            self.assertIn("not a user checkpoint", " ".join(waiting["lifecycle"]["next_action"]["preconditions"]))

    def test_Q30_disagreement_keeps_candidate_unintegrated(self) -> None:
        """Q30: a BLOCK qualification cannot be replaced by alternate PASS bytes."""
        helper = phase_e_reviews.PhaseEReviewQualificationTests()
        with tempfile.TemporaryDirectory() as directory:
            case = helper.prepare_candidate(Path(directory))
            review = helper.prepare_review(case, "ticket_review")
            blocked = helper.review_return(case, review, verdict="BLOCK")
            helper.ingest_review(case, review, blocked)
            state, raw = ledger.load_state(case["paths"])
            qualification = helper.qualification(state, review["candidate"]["sha"])
            fake = helper.review_return(case, review, verdict="PASS")
            result = run(
                "integrate", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID,
                "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]),
                "--qualification-ref", qualification["id"], "--review-file", str(fake), expect=2,
            )
            self.assertRegex(result.stderr.lower(), r"block|qualification|pass")
            self.assertEqual(raw, case["paths"]["ledger"].read_bytes())

    def test_Q31_partially_valid_review_return_is_not_published(self) -> None:
        """Q31: PASS with a failed required check is rejected atomically."""
        helper = phase_e_reviews.PhaseEReviewQualificationTests()
        with tempfile.TemporaryDirectory() as directory:
            case = helper.prepare_candidate(Path(directory))
            review = helper.prepare_review(case, "ticket_review")
            invalid = helper.review_return(case, review, verdict="PASS", check_outcome="failed")
            before, raw = ledger.load_state(case["paths"])
            result = helper.ingest_review(case, review, invalid, expect=2)
            self.assertRegex(result.stderr.lower(), r"check|failed|pass")
            after, after_raw = ledger.load_state(case["paths"])
            self.assertEqual(raw, after_raw)
            self.assertEqual(before["revision"], after["revision"])
            self.assertEqual([], after.get("review_qualifications", []))

    def test_Q32_not_started_worker_is_explicit_and_not_spawned_twice(self) -> None:
        """Q32: registration and runtime spawn evidence are separate facts."""
        helper = phase_g_binding.PhaseGExecutionBindingTests()
        runtime = phase_g_runtime.PhaseGRuntimeObservationTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, paths, packet, _ = helper.setup_dispatch(root)
            helper.dispatch(control, packet, revision=1)
            runtime.observe(root, control, paths, "A-G", "not_started", 2, event_id="OBS-Q32-NOT-STARTED", instance=None)
            state, _ = ledger.load_state(paths)
            self.assertEqual("not_started", ledger.runtime_liveness(ledger.attempt_by_id(state, "A-G")))
            replay = helper.dispatch(control, packet, revision=1)
            self.assertEqual("existing_request_do_not_spawn_again", json.loads(replay.stdout)["spawn_disposition"])
            state, _ = ledger.load_state(paths)
            self.assertEqual(0, state["usage"]["counters"]["spawn_calls"])

    def test_Q33_applied_git_effect_is_adopted_without_recommit(self) -> None:
        """Q33: a real Git commit remains adoptable after the ledger response is lost."""
        helper = phase_d_effects.PhaseDEffectTests()
        with tempfile.TemporaryDirectory() as directory:
            case = helper.candidate_case(Path(directory))
            helper.prepare_effect(case)
            candidate_sha, candidate_tree = helper.commit_candidate(case)
            helper.reconcile(case, "uncertain")
            receipt = helper.effect_receipt(case, commit_sha=candidate_sha, tree_sha=candidate_tree)
            helper.reconcile(case, "applied", receipt=receipt)
            adopted = json.loads(run(
                "candidate", "--control-root", str(case["control"]), "--run-id", case["run_id"],
                "--owner-token", phase_d_effects.OWNER,
                "--revision", str(ledger.load_state(case["paths"])[0]["revision"]),
                "--attempt-id", phase_d_effects.ATTEMPT_ID, "--operation-id", phase_d_effects.OPERATION_ID,
            ).stdout)
            self.assertEqual(candidate_sha, adopted["candidate"])
            self.assertEqual("2", subprocess.run(["git", "-C", str(case["repo"]), "rev-list", "--count", "HEAD"], text=True, capture_output=True, check=True).stdout.strip())

    def test_Q34_no_change_initial_failure_returns_to_verified_baseline(self) -> None:
        """Q34: an initial no-write BLOCK is closed without inventing a candidate."""
        helper = phase_c_finalization.PhaseCAttemptFinalizationTests()
        with tempfile.TemporaryDirectory() as directory:
            case = helper.init_case(Path(directory))
            helper.seed_terminal(case, status="BLOCKED", mode="implement")
            result = json.loads(helper.finalize(case, "A-TERMINAL").stdout)
            state, _ = ledger.load_state(case["paths"])
            self.assertTrue(result["closed"])
            self.assertEqual("READY", state["tickets"][0]["state"])
            self.assertIsNone(state["tickets"][0]["current_candidate"])
            self.assertEqual([], state["candidates"])

    def test_Q35_review_source_is_normalized_to_worker_provenance(self) -> None:
        """Q35: repair source review is resolved to the exact worker candidate."""
        helper = phase_c_repairs.PhaseCRepairPlanTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths, subjects = phase_c_repairs.seed_repair_fixture(root, [("T-1", "F-1", "current")])
            source = subjects[("T-1", "current")]
            plan = phase_c_repairs.grouped_plan(["F-1"], source["review"])
            plan_path = root / "q35-plan.json"
            write_json(plan_path, plan)
            packet = phase_c_repairs.repair_packet(root, repo, "T-1", "A-Q35", source["sha"], plan)
            helper.authorize(control, ticket_id="T-1", authorization_id="AUTH-Q35", plan_path=plan_path, packet_path=packet)
            state, _ = ledger.load_state(paths)
            auth = next(item for item in state["decisions"] if item["id"] == "AUTH-Q35")
            stored = ledger.stored_payload(paths, auth["repair_plan_ref"], "repair plan")
            self.assertEqual(source["worker"], stored["source_attempt_ref"])
            self.assertEqual(source["candidate"], stored["source_candidate_ref"])

    def test_Q36_review_cache_outside_zone_is_foreign_write(self) -> None:
        """Q36: review-generated cache files are visible to the complete write-set audit."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            (root / "app.txt").write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "baseline"], check=True)
            baseline = Path(directory) / "baseline.json"
            declared = Path(directory) / "declared.json"
            zone = Path(directory) / "zone.json"
            write_json(baseline, {"base_sha": "baseline", "files": [{"path": "app.txt", "type": "file", "mode": 420, "sha256": ledger.sha256_bytes(b"baseline\n")}]})
            write_json(declared, [])
            write_json(zone, [])
            (root / ".review-cache").mkdir()
            (root / ".review-cache" / "trace.json").write_text("cache\n", encoding="utf-8")
            audit = json.loads(run("audit-write-set", "--root", str(root), "--baseline", str(baseline), "--declared", str(declared), "--zone", str(zone)).stdout)
            self.assertIn(".review-cache/trace.json", audit["changed_paths"])
            self.assertIn(".review-cache/trace.json", audit["undeclared_paths"])
            self.assertFalse(audit["pass"])

    def test_Q37_successor_does_not_inherit_unproven_predecessor_work(self) -> None:
        """Q37: successor manifest preserves evidence while excluding attempts/reservations."""
        helper = phase_g_successor.PhaseGSuccessorOwnershipTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = helper.parent(Path(directory))
            manifest = helper.manifest(parent)
            result = helper.init_successor(root, parent, manifest)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            successor, _ = ledger.load_state(ledger.paths(root / "control-b", "successor"))
            self.assertEqual([], successor.get("attempts", []))
            self.assertEqual([], successor.get("candidates", []))
            self.assertTrue(any("no accepted candidate" in item for item in successor["successor_manifest"]["manifest"]["unknowns"]))

    def test_Q38_continuation_repair_failure_cannot_be_preserved(self) -> None:
        """Q38: a repair's own focused failure cannot be reclassified as external."""
        helper = phase_c_finalization.PhaseCAttemptFinalizationTests()
        with tempfile.TemporaryDirectory() as directory:
            case = helper.init_case(Path(directory), prior_quality="CONTINUATION")
            helper.seed_terminal(case, status="BLOCKED", mode="repair", actual_write=True, declared_files=[{"path": "app.txt", "operation": "modify"}])
            state, _ = ledger.load_state(case["paths"])
            attempt = ledger.attempt_by_id(state, "A-TERMINAL")
            # Deliberately classify the repair's failed focused check as an
            # external blocker.  The public preservation transition must
            # reject it before any candidate/effect publication.
            authorization = {
                "id": "AUTH-Q38", "type": "continuation_candidate_authorization", "status": "authorized",
                "decision": "PRESERVE_CONTINUATION", "reason": "invalid test classification",
                "evidence_refs": [attempt["return_ref"], "ISS-REPAIR"],
                "affected_refs": ["T-1", "A-TERMINAL"], "blocker_ref": "ISS-REPAIR",
                "blocker_scope": "external", "external_check_ids": ["focused"],
                "external_criterion_ids": ["C-1"],
            }
            authorization_path = case["root"] / "q38-authorization.json"
            commit_receipt_path = case["root"] / "q38-commit.json"
            write_json(authorization_path, authorization)
            head = subprocess.run(["git", "-C", str(case["repo"]), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
            tree = subprocess.run(["git", "-C", str(case["repo"]), "rev-parse", "HEAD^{tree}"], text=True, capture_output=True, check=True).stdout.strip()
            write_json(commit_receipt_path, {"status": "PASS", "checkout": str(case["repo"]), "base_sha": attempt["base_sha"], "commit_sha": head, "tree_sha": tree, "authority_ref": "AUTH-Q38"})
            rejected = run(
                "preserve-blocked-candidate", "--control-root", str(case["control"]), "--run-id", phase_c_finalization.RUN_ID,
                "--owner-token", phase_c_finalization.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1",
                "--attempt-id", "A-TERMINAL", "--authorization-file", str(authorization_path),
                "--commit-receipt", str(commit_receipt_path), "--operation-id", "OP-Q38", expect=2,
            )
            self.assertRegex(rejected.stderr.lower(), r"external|pass|failed|continuation|candidate")
            after, _ = ledger.load_state(case["paths"])
            self.assertEqual(state["revision"], after["revision"])
            self.assertEqual(case["candidate"]["id"], after["tickets"][0]["current_candidate"])
            self.assertFalse(any(item.get("id") == "OP-Q38" for item in after.get("operations", [])))

    def test_Q39_quiescing_rejects_dispatch_and_terminal_run_cannot_recover(self) -> None:
        """Q39: cancellation is a terminal boundary, not a resumable pause."""
        helper = lifecycle_repairs.LifecycleRepairTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = helper.init_ticket(root)
            state, _ = ledger.load_state(paths)
            run("cancel", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--reason", "Q39")
            quiescing, _ = ledger.load_state(paths)
            self.assertEqual("QUIESCING", quiescing["lifecycle"]["control"])
            packet = helper.worker_packet(root, "A-Q39")
            rejected = helper.dispatch(control, packet, "A-Q39", quiescing["revision"], expect=2)
            self.assertRegex(rejected.stderr.lower(), r"quiescing|control|admission")
            state, _ = ledger.load_state(paths)
            stop_evidence = root / "q39-stop.json"
            write_json(stop_evidence, {"status": "PASS", "writers_stopped": True, "reconciled": True})
            run("cancel", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--reason", "Q39", "--finalize", "--stop-evidence", str(stop_evidence))
            terminal, raw = ledger.load_state(paths)
            self.assertEqual("CANCELLED", terminal["lifecycle"]["control"])
            recovered = run("recover", "--control-root", str(control), "--run-id", "repair-run", "--owner-token", "owner-a", "--revision", str(terminal["revision"]), "--reason", "Q39", expect=2)
            self.assertRegex(recovered.stderr.lower(), r"terminal|cancel")
            self.assertEqual(raw, paths["ledger"].read_bytes())

    def test_Q40_takeover_fences_old_epoch_and_quarantines_attempt(self) -> None:
        """Q40: owner takeover increments epoch and quarantines old runtime authority."""
        helper = requirements_adoption.RequirementsAdoptionTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, manifest = helper.fixture(root)
            run("adopt-requirements", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "2", "--manifest", str(manifest))
            bundle = helper.bundle(root, control)
            run("publish-design-bundle", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "3", "--bundle", str(bundle))
            packet = root / "q40-review.json"
            current_state, _ = ledger.load_state(ledger.paths(control, "adopt-run"))
            subject_fingerprint = current_state["design_publication"]["publication_hash"]
            write_json(packet, {"identity": {"run_id": "adopt-run", "attempt_id": "A-Q40", "epoch": 0, "source_revision": 4, "registration_revision": 4, "subject_revision": 4, "intent_revision": "v1"}, "kind": "review", "mandate": "coverage", "subject_fingerprint": subject_fingerprint, "criteria": [{"criterion_id": "C-1"}], "axes": ["coverage"], "return_target": {"path": "return.json"}})
            run("prepare-design-review", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "4", "--review-attempt-id", "A-Q40", "--lease-id", "L-Q40", "--packet", str(packet), "--review-kind", "coverage", "--reviewer-identity", "fixture-reviewer", "--reviewer-role", "coverage-reviewer")
            paths = ledger.paths(control, "adopt-run")
            phase_g_runtime.record_runtime_event(control, "adopt-run", "owner-a", paths, "A-Q40", "start", "OBS-Q40-START", instance="runtime-Q40")
            state, _ = ledger.load_state(paths)
            takeover = json.loads(run("recover", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--reason", "Q40 owner transfer", "--takeover", "--new-owner-token", "owner-b", "--attestation-ref", "EV-Q40-STOP").stdout)
            self.assertEqual(1, takeover["epoch"])
            adopted, _ = ledger.load_state(paths)
            self.assertEqual("owner-b", adopted["owner"]["token"])
            self.assertEqual("quarantined", ledger.attempt_by_id(adopted, "A-Q40")["lease"]["state"])
            stale = run("gate", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", str(adopted["revision"]), "--control", "ACTIVE", expect=2)
            self.assertIn("owner token mismatch", stale.stderr)

    def test_Q41_deny_identity_and_object_tamper_fail_closed(self) -> None:
        """Q41: deny precedence and immutable object verification are enforced."""
        helper = phase_g_binding.PhaseGExecutionBindingTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, paths, packet_path, packet = helper.setup_dispatch(root)
            packet["write"]["deny"] = ["app.txt"]
            denied = root / "q41-denied.json"
            write_json(denied, packet)
            before = paths["ledger"].read_bytes()
            helper.dispatch(control, denied, revision=1, expect=2)
            self.assertEqual(before, paths["ledger"].read_bytes())
            helper.dispatch(control, packet_path, revision=1)
            state, _ = ledger.load_state(paths)
            packet_ref = ledger.attempt_by_id(state, "A-G")["packet_ref"]
            object_path = paths["objects"] / packet_ref.split("/", 1)[1]
            object_path.write_bytes(b"tampered")
            with self.assertRaisesRegex(ledger.LedgerError, r"immutable object|hash|digest"):
                ledger.stored_payload(paths, packet_ref, "tampered packet")

    def test_Q42_unavailable_contract_blocks_consumer_readiness(self) -> None:
        """Q42: accepted specification is not implementation availability."""
        helper = requirements_adoption.RequirementsAdoptionTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, _, manifest = helper.fixture(root)
            run("adopt-requirements", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "2", "--manifest", str(manifest))
            bundle = json.loads(helper.bundle(root, control).read_text(encoding="utf-8"))
            bundle["contracts"][0]["implementation_availability"] = "unavailable"
            bundle["contracts"][0]["implementation_availability_evidence_refs"] = ["EV-Q42-unavailable"]
            bundle_path = root / "q42-unavailable-bundle.json"
            write_json(bundle_path, bundle)
            run("publish-design-bundle", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", "3", "--bundle", str(bundle_path))
            paths = ledger.paths(control, "adopt-run")
            state, _ = ledger.load_state(paths)
            self.assertEqual("PLANNED", state["tickets"][0]["state"])
            before = paths["ledger"].read_bytes()
            rejected = run("gate", "--control-root", str(control), "--run-id", "adopt-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--phase", "PLAN", "--control", "ACTIVE", "--gate-id", "G3", "--next-action", "ready_ticket", expect=2)
            self.assertRegex(rejected.stderr.lower(), r"availab|contract|readiness|implement")
            self.assertEqual(before, paths["ledger"].read_bytes())

    def test_Q_manifest_is_complete_and_methods_exist(self) -> None:
        """The executable manifest must contain exactly the canonical Q25-Q42 set."""
        self.assertEqual({f"Q{i}" for i in range(25, 43)}, set(QUALIFICATION_MANIFEST))
        for qualification_id, method_name in QUALIFICATION_MANIFEST.items():
            with self.subTest(qualification_id=qualification_id):
                self.assertTrue(hasattr(self, method_name), method_name)


if __name__ == "__main__":
    unittest.main()
