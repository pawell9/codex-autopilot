"""Phase H qualification boundaries (Q25-Q42).

These are deliberately black-box scenarios: state is prepared only as a
disposable fixture and every lifecycle mutation under test goes through the
public ``tools/ledger.py`` CLI.  The manifest is kept next to the tests so a
release report can mechanically prove that no canonical Q25-Q42 case was
silently omitted.
"""

from __future__ import annotations

import copy
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

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
from tests import test_continuation_candidates as continuation_candidates
from tests.test_phase_b_projections_v110 import install_execution_design


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


def run_main(*args: str) -> tuple[int, str, str]:
    """Call the public CLI parser/dispatcher in-process for deterministic fault injection."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = ledger.main(list(args))
    return code, stdout.getvalue(), stderr.getvalue()


class PhaseHBoundaryQualificationTests(unittest.TestCase):
    """Executable Q25-Q42 qualification scenarios."""

    def test_Q25_crash_restart_boundaries_never_publish_half_state(self) -> None:
        """Q25: each durable boundary has an executable crash and exact recovery."""
        helper = phase_d_effects.PhaseDEffectTests()

        def prepared(root: Path, run_id: str) -> tuple[dict[str, Any], Path, int, bytes]:
            case = helper.init_git_case(root, run_id=run_id)
            helper.prepare_effect(case)
            helper.reconcile(case, "uncertain")
            commit_sha, tree_sha = helper.commit_candidate(case)
            receipt = helper.effect_receipt(case, commit_sha=commit_sha, tree_sha=tree_sha)
            state, _ = ledger.load_state(case["paths"])
            return case, receipt, state["revision"], case["paths"]["ledger"].read_bytes()

        # Faults are raised at the actual immutable publication call.  This
        # keeps a missing receipt from masking the boundary under test.
        for boundary in ("object_store", "ledger.prev", "ledger.json", "snapshot", "receipt"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                case, receipt, revision, before = prepared(Path(directory), f"q25-{boundary.replace('.', '-')}")
                receipt_digest = ledger.sha256_bytes(receipt.read_bytes())
                real_create, real_write = ledger.atomic_create, ledger.atomic_write

                def fail_create(path: Path, data: bytes) -> bool:
                    path = Path(path)
                    if boundary == "snapshot" and path.parent == case["paths"]["run"] / "snapshots":
                        raise OSError("Q25 injected snapshot publication crash")
                    if boundary in {"object_store", "receipt"} and path.parent == case["paths"]["objects"]:
                        if boundary == "object_store" or path.name == receipt_digest:
                            raise OSError(f"Q25 injected {boundary} publication crash")
                    return real_create(path, data)

                def fail_write(path: Path, data: bytes) -> None:
                    path = Path(path)
                    if boundary == "ledger.prev" and path == case["paths"]["prev"]:
                        raise OSError("Q25 injected ledger.prev crash")
                    if boundary == "ledger.json" and path == case["paths"]["ledger"]:
                        raise OSError("Q25 injected ledger.json crash")
                    return real_write(path, data)

                patches = [
                    patch("tools.ledger.atomic_create", side_effect=fail_create),
                    patch("tools.ledger.atomic_write", side_effect=fail_write),
                ]
                for active in patches:
                    active.start()
                try:
                    code, _stdout, stderr = run_main(
                        "reconcile-effect", "--control-root", str(case["control"]), "--run-id", case["run_id"],
                        "--owner-token", phase_d_effects.OWNER, "--revision", str(revision),
                        "--operation-id", phase_d_effects.OPERATION_ID, "--result", "applied", "--receipt", str(receipt),
                    )
                finally:
                    for active in reversed(patches):
                        active.stop()
                self.assertEqual(2, code, stderr)
                state, _ = ledger.load_state(case["paths"])
                operation = next(item for item in state["operations"] if item["id"] == phase_d_effects.OPERATION_ID)
                if boundary == "snapshot":
                    # The ledger revision is durable before snapshot publication;
                    # retry must repair that missing recovery artifact idempotently.
                    self.assertEqual("applied", operation["state"])
                    self.assertEqual(revision + 1, state["revision"])
                    retry_code, retry_stdout, _ = run_main(
                        "reconcile-effect", "--control-root", str(case["control"]), "--run-id", case["run_id"],
                        "--owner-token", phase_d_effects.OWNER, "--revision", str(revision),
                        "--operation-id", phase_d_effects.OPERATION_ID, "--result", "applied", "--receipt", str(receipt),
                    )
                    self.assertEqual(0, retry_code)
                    self.assertTrue(json.loads(retry_stdout)["idempotent"])
                    self.assertTrue(list((case["paths"]["run"] / "snapshots").glob("*.json")))
                else:
                    self.assertEqual(before, case["paths"]["ledger"].read_bytes())
                    self.assertEqual("uncertain", operation["state"])
                    helper.reconcile(case, "applied", receipt=receipt, revision=revision)
                    recovered, _ = ledger.load_state(case["paths"])
                    self.assertEqual("applied", next(item for item in recovered["operations"] if item["id"] == phase_d_effects.OPERATION_ID)["state"])
                    exact = json.loads(helper.reconcile(case, "applied", receipt=receipt).stdout)
                    self.assertTrue(exact["idempotent"])

        # A Git commit may exist before its receipt is durable, but the ledger
        # must remain unresolved until that exact receipt is supplied.
        with self.subTest(boundary="git-before-receipt"), tempfile.TemporaryDirectory() as directory:
            case = helper.init_git_case(Path(directory), run_id="q25-git-before-receipt")
            helper.prepare_effect(case)
            commit_sha, tree_sha = helper.commit_candidate(case)
            state, _ = ledger.load_state(case["paths"])
            missing = invoke(
                "reconcile-effect", "--control-root", str(case["control"]), "--run-id", case["run_id"],
                "--owner-token", phase_d_effects.OWNER, "--revision", str(state["revision"]),
                "--operation-id", phase_d_effects.OPERATION_ID, "--result", "applied", "--receipt", str(Path(directory) / "missing.json"),
            )
            self.assertNotEqual(0, missing.returncode)
            untouched, _ = ledger.load_state(case["paths"])
            self.assertEqual("prepared", next(item for item in untouched["operations"] if item["id"] == phase_d_effects.OPERATION_ID)["state"])
            helper.reconcile(case, "uncertain")
            receipt = helper.effect_receipt(case, commit_sha=commit_sha, tree_sha=tree_sha)
            helper.reconcile(case, "applied", receipt=receipt)
            self.assertEqual(commit_sha, subprocess.run(["git", "-C", str(case["repo"]), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip())

        # Spawn observation is itself a durable boundary.  A failed ledger
        # publication leaves registration intact and a replay records exactly
        # one observation/spawn, never a second launch.
        with self.subTest(boundary="spawn"), tempfile.TemporaryDirectory() as directory:
            fixture = phase_g_binding.PhaseGExecutionBindingTests()
            root = Path(directory)
            control, _, paths, packet, _ = fixture.setup_dispatch(root)
            fixture.dispatch(control, packet, revision=1)
            state, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(state, "A-G")
            event = {"kind": "runtime_observation", "event_id": "OBS-Q25-START", "event": "start", "run_id": phase_g_binding.RUN_ID, "attempt_id": "A-G", "epoch": attempt["epoch"], "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q25", "observed_at": "2026-09-18T12:00:00Z", "observer": "q25", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": "not_applicable"}}
            event_path = root / "q25-observation.json"
            write_json(event_path, event)
            before = paths["ledger"].read_bytes()
            real_write = ledger.atomic_write
            with patch("tools.ledger.atomic_write", side_effect=lambda path, data: (_ for _ in ()).throw(OSError("Q25 injected spawn observation crash")) if Path(path) == paths["ledger"] else real_write(path, data)):
                code, _stdout, stderr = run_main("observe-runtime", "--control-root", str(control), "--run-id", phase_g_binding.RUN_ID, "--owner-token", phase_g_binding.OWNER, "--revision", str(state["revision"]), "--attempt-id", "A-G", "--event", "start", "--event-id", "OBS-Q25-START", "--event-file", str(event_path))
            self.assertEqual(2, code, stderr)
            self.assertEqual(before, paths["ledger"].read_bytes())
            replay = phase_g_runtime.PhaseGRuntimeObservationTests().observe(root, control, paths, "A-G", "start", state["revision"], event_id="OBS-Q25-START", instance="runtime-q25")
            self.assertEqual("spawn_observed_once; do_not_repeat_spawn", json.loads(replay.stdout)["disposition"])
            duplicate = fixture.dispatch(control, packet, revision=1)
            self.assertEqual("existing_request_do_not_spawn_again", json.loads(duplicate.stdout)["spawn_disposition"])
            self.assertEqual(1, ledger.load_state(paths)[0]["usage"]["counters"]["spawn_calls"])

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
        """Q28: one preserve hop, two bound repairs, then fresh qualification integration."""
        helper = continuation_candidates.BlockedContinuationCandidateTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = helper.prepare_case(root)
            preserved = json.loads(helper.preserve(case).stdout)
            state, _ = ledger.load_state(case["paths"])
            parent = ledger.current_candidate_record(state, state["tickets"][0])
            self.assertEqual("CONTINUATION", parent["quality"])
            self.assertEqual(preserved["candidate"], parent["sha"])
            source_attempt = ledger.attempt_by_id(state, continuation_candidates.ATTEMPT_ID)
            continuation = ledger.stored_payload(case["paths"], source_attempt["continuation_ref"], "Q28 continuation")
            self.assertEqual(parent["sha"], continuation["candidate_sha"])
            self.assertEqual(case["blocker"]["id"], continuation["blocker_ref"])

            # Fresh review of the preserved candidate creates the candidate-bound finding.
            review_id = "RV-Q28-CONT"
            review_packet = {"identity": {"run_id": continuation_candidates.RUN_ID, "ticket_id": continuation_candidates.TICKET_ID, "attempt_id": review_id, "epoch": 0}, "kind": "review", "purpose": "ticket_review", "mandate": "Q28 continuation repair review", "subject_fingerprint": parent["sha"], "criteria": [{"criterion_id": "C-1"}], "axes": ["correctness"], "return_target": {"path": "return.json"}}
            review_packet_path = root / "q28-review.packet.json"
            write_json(review_packet_path, review_packet)
            run("prepare-review", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--review-attempt-id", review_id, "--lease-id", "L-Q28-R", "--packet", str(review_packet_path))
            state, _ = ledger.load_state(case["paths"])
            review_attempt = ledger.attempt_by_id(state, review_id)
            for event, event_id, descendants in (("start", "OBS-Q28-R-START", "not_applicable"), ("stop", "OBS-Q28-R-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": continuation_candidates.RUN_ID, "attempt_id": review_id, "epoch": review_attempt["epoch"], "packet_hash": review_attempt["packet_hash"], "spawn_request_id": review_attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q28-review", "observed_at": "2026-09-18T12:00:00Z", "observer": "q28", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = root / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", review_id, "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = ledger.load_state(case["paths"])
                review_attempt = ledger.attempt_by_id(state, review_id)
            review_return = {"identity": {**review_packet["identity"], "packet_hash": review_attempt["packet_hash"]}, "subject_fingerprint": parent["sha"], "verdict": "BLOCK", "coverage": [{"criterion_id": "C-1", "outcome": "partial", "evidence_refs": ["EV-Q28-R"]}], "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "failed", "actual": "repair required", "evidence_ref": "EV-Q28-R"}], "context_refs": ["CTX-Q28-R"], "findings": [{"axis": "correctness", "impact": "blocking", "claim": "continuation needs repair", "expected": "fresh DONE candidate", "actual": "CONTINUATION", "evidence": "EV-Q28-R", "affected_refs": ["T-1"]}]}
            review_return_path = case["paths"]["scratch"] / review_id / "return.json"
            write_json(review_return_path, review_return)
            integrity_path = root / "q28-review.integrity.json"
            write_json(integrity_path, {"status": "PASS", "candidate_fingerprint": parent["sha"], "ledger_hash": ledger.sha256_bytes(case["paths"]["ledger"].read_bytes()), "reviewer_stopped": True})
            run("ingest-return", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", review_id, "--return-file", str(review_return_path), "--kind", "review", "--integrity-receipt", str(integrity_path))
            state, _ = ledger.load_state(case["paths"])
            finding = next(item for item in reversed(state["findings"]) if item.get("source_ref") == review_id)
            repair = {"cause": "implementation", "finding_ref": finding["id"], "hypothesis": "promote continuation to DONE", "expected_proof": "fresh candidate", "stopping_condition": "focused check passes", "causal_change": "complete app.txt"}
            repair_path = root / "q28-repair.json"
            write_json(repair_path, repair)
            run("authorize-repair", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--finding-ref", finding["id"], "--authorization-id", "AUTH-Q28-REPAIR", "--repair-contract", str(repair_path))
            state, _ = ledger.load_state(case["paths"])
            source_packet = ledger.stored_payload(case["paths"], source_attempt["packet_ref"], "source packet")
            packet = copy.deepcopy(source_packet)
            attempt_id = "A-Q28-REPAIR"
            packet["identity"] = {**source_packet["identity"], "attempt_id": attempt_id}
            packet["mode"] = "repair"
            packet["repair"] = repair
            packet["workspace"] = {"root": str(case["repo"]), "expected_base": parent["sha"]}
            packet_path = root / "q28-repair.packet.json"
            write_json(packet_path, packet)
            run("dispatch", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--attempt-id", attempt_id, "--lease-id", "L-Q28-REPAIR", "--route-id", "route-q28-repair", "--packet", str(packet_path))
            state, _ = ledger.load_state(case["paths"])
            attempt = ledger.attempt_by_id(state, attempt_id)
            for event, event_id, descendants in (("start", "OBS-Q28-W-START", "not_applicable"), ("stop", "OBS-Q28-W-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": continuation_candidates.RUN_ID, "attempt_id": attempt_id, "epoch": attempt["epoch"], "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q28-worker", "observed_at": "2026-09-18T12:00:00Z", "observer": "q28", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = root / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = ledger.load_state(case["paths"])
                attempt = ledger.attempt_by_id(state, attempt_id)
            (case["repo"] / "app.txt").write_text("q28 repaired\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(case["repo"]), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(case["repo"]), "-c", "user.name=PhaseH", "-c", "user.email=phase-h@example.invalid", "commit", "-qm", "q28 repaired"], check=True)
            done_sha = subprocess.run(["git", "-C", str(case["repo"]), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
            done_tree = subprocess.run(["git", "-C", str(case["repo"]), "rev-parse", "HEAD^{tree}"], text=True, capture_output=True, check=True).stdout.strip()
            worker_return = {"identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]}, "status": "DONE", "result": "repair complete", "files": [{"path": "app.txt", "operation": "modify"}], "checks": [{"check_id": item["check_id"], "outcome": "pass", "actual": "pass", "evidence_ref": "EV-Q28-W"} for item in packet["verification"]], "criteria": [{"criterion_id": item["criterion_id"], "outcome": "satisfied", "evidence_refs": ["EV-Q28-W"]} for item in packet["acceptance"]]}
            worker_path = case["paths"]["scratch"] / attempt_id / "return.json"
            write_json(worker_path, worker_return)
            run("ingest-return", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--return-file", str(worker_path), "--kind", "worker")
            state, _ = ledger.load_state(case["paths"])
            operation_id = "OP-Q28-REPAIR"
            run("prepare-effect", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--operation-id", operation_id, "--kind", "candidate_commit", "--target", str(case["repo"]), "--expected-before", parent["sha"], "--authority-ref", "AUTH-Q28-REPAIR")
            receipt_path = root / "q28-repair.receipt.json"
            write_json(receipt_path, {"status": "PASS", "run_id": continuation_candidates.RUN_ID, "ticket_id": "T-1", "attempt_id": attempt_id, "operation_id": operation_id, "kind": "candidate_commit", "target": str(case["repo"]), "checkout": str(case["repo"]), "expected_before": parent["sha"], "base_sha": parent["sha"], "intended_after": done_sha, "commit_sha": done_sha, "tree_sha": done_tree, "authority_ref": "AUTH-Q28-REPAIR"})
            state, _ = ledger.load_state(case["paths"])
            run("candidate", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--commit-receipt", str(receipt_path), "--operation-id", operation_id)
            state, _ = ledger.load_state(case["paths"])
            final_candidate = ledger.current_candidate_record(state, state["tickets"][0])
            self.assertEqual("DONE", final_candidate["quality"])
            self.assertEqual(parent["id"], final_candidate["parent_candidate_ref"])
            first_done_id = final_candidate["id"]

            # A second candidate-bound repair is required before the final
            # review; it must consume a distinct authorization and advance the
            # parent chain from the first DONE child.
            review2_id = "RV-Q28-REPAIR-2"
            review2_packet = {"identity": {"run_id": continuation_candidates.RUN_ID, "ticket_id": "T-1", "attempt_id": review2_id, "epoch": 0}, "kind": "review", "purpose": "ticket_review", "mandate": "Q28 second repair review", "subject_fingerprint": final_candidate["sha"], "criteria": [{"criterion_id": "C-1"}], "axes": ["correctness"], "return_target": {"path": "return.json"}}
            review2_packet_path = root / "q28-review-2.packet.json"
            write_json(review2_packet_path, review2_packet)
            run("prepare-review", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--review-attempt-id", review2_id, "--lease-id", "L-Q28-R2", "--packet", str(review2_packet_path))
            state, _ = ledger.load_state(case["paths"])
            review2_attempt = ledger.attempt_by_id(state, review2_id)
            for event, event_id, descendants in (("start", "OBS-Q28-R2-START", "not_applicable"), ("stop", "OBS-Q28-R2-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": continuation_candidates.RUN_ID, "attempt_id": review2_id, "epoch": review2_attempt["epoch"], "packet_hash": review2_attempt["packet_hash"], "spawn_request_id": review2_attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q28-review-2", "observed_at": "2026-09-18T12:00:00Z", "observer": "q28", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = root / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", review2_id, "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = ledger.load_state(case["paths"])
                review2_attempt = ledger.attempt_by_id(state, review2_id)
            review2_return = {"identity": {**review2_packet["identity"], "packet_hash": review2_attempt["packet_hash"]}, "subject_fingerprint": final_candidate["sha"], "verdict": "BLOCK", "coverage": [{"criterion_id": "C-1", "outcome": "partial", "evidence_refs": ["EV-Q28-R2"]}], "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "failed", "actual": "second repair required", "evidence_ref": "EV-Q28-R2"}], "context_refs": ["CTX-Q28-R2"], "findings": [{"axis": "correctness", "impact": "blocking", "claim": "second repair required", "expected": "fresh DONE candidate", "actual": "first repair candidate", "evidence": "EV-Q28-R2", "affected_refs": ["T-1"]}]}
            review2_return_path = case["paths"]["scratch"] / review2_id / "return.json"
            write_json(review2_return_path, review2_return)
            integrity2 = root / "q28-review-2.integrity.json"
            write_json(integrity2, {"status": "PASS", "candidate_fingerprint": final_candidate["sha"], "ledger_hash": ledger.sha256_bytes(case["paths"]["ledger"].read_bytes()), "reviewer_stopped": True})
            run("ingest-return", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", review2_id, "--return-file", str(review2_return_path), "--kind", "review", "--integrity-receipt", str(integrity2))
            state, _ = ledger.load_state(case["paths"])
            finding2 = next(item for item in reversed(state["findings"]) if item.get("source_ref") == review2_id)
            repair2 = {"cause": "implementation", "finding_ref": finding2["id"], "hypothesis": "second candidate-bound repair", "expected_proof": "fresh DONE candidate", "stopping_condition": "focused check passes", "causal_change": "complete app.txt again"}
            repair2_path = root / "q28-repair-2.json"
            write_json(repair2_path, repair2)
            run("authorize-repair", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--finding-ref", finding2["id"], "--authorization-id", "AUTH-Q28-REPAIR-2", "--repair-contract", str(repair2_path))
            state, _ = ledger.load_state(case["paths"])
            packet2 = copy.deepcopy(packet)
            attempt2_id = "A-Q28-REPAIR-2"
            packet2["identity"] = {**packet["identity"], "attempt_id": attempt2_id}
            packet2["repair"] = repair2
            packet2["workspace"] = {"root": str(case["repo"]), "expected_base": final_candidate["sha"]}
            packet2_path = root / "q28-repair-2.packet.json"
            write_json(packet2_path, packet2)
            run("dispatch", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--attempt-id", attempt2_id, "--lease-id", "L-Q28-REPAIR-2", "--route-id", "route-q28-repair-2", "--packet", str(packet2_path))
            state, _ = ledger.load_state(case["paths"])
            attempt2 = ledger.attempt_by_id(state, attempt2_id)
            for event, event_id, descendants in (("start", "OBS-Q28-W2-START", "not_applicable"), ("stop", "OBS-Q28-W2-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": continuation_candidates.RUN_ID, "attempt_id": attempt2_id, "epoch": attempt2["epoch"], "packet_hash": attempt2["packet_hash"], "spawn_request_id": attempt2["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q28-worker-2", "observed_at": "2026-09-18T12:00:00Z", "observer": "q28", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = root / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", attempt2_id, "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = ledger.load_state(case["paths"])
                attempt2 = ledger.attempt_by_id(state, attempt2_id)
            (case["repo"] / "app.txt").write_text("q28 repaired twice\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(case["repo"]), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(case["repo"]), "-c", "user.name=PhaseH", "-c", "user.email=phase-h@example.invalid", "commit", "-qm", "q28 repaired twice"], check=True)
            done2_sha = subprocess.run(["git", "-C", str(case["repo"]), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
            done2_tree = subprocess.run(["git", "-C", str(case["repo"]), "rev-parse", "HEAD^{tree}"], text=True, capture_output=True, check=True).stdout.strip()
            worker2_return = {"identity": {**packet2["identity"], "packet_hash": attempt2["packet_hash"]}, "status": "DONE", "result": "second repair complete", "files": [{"path": "app.txt", "operation": "modify"}], "checks": [{"check_id": item["check_id"], "outcome": "pass", "actual": "pass", "evidence_ref": "EV-Q28-W2"} for item in packet2["verification"]], "criteria": [{"criterion_id": item["criterion_id"], "outcome": "satisfied", "evidence_refs": ["EV-Q28-W2"]} for item in packet2["acceptance"]]}
            worker2_path = case["paths"]["scratch"] / attempt2_id / "return.json"
            write_json(worker2_path, worker2_return)
            run("ingest-return", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", attempt2_id, "--return-file", str(worker2_path), "--kind", "worker")
            state, _ = ledger.load_state(case["paths"])
            operation2 = "OP-Q28-REPAIR-2"
            run("prepare-effect", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--operation-id", operation2, "--kind", "candidate_commit", "--target", str(case["repo"]), "--expected-before", final_candidate["sha"], "--authority-ref", "AUTH-Q28-REPAIR-2")
            receipt2 = root / "q28-repair-2.receipt.json"
            write_json(receipt2, {"status": "PASS", "run_id": continuation_candidates.RUN_ID, "ticket_id": "T-1", "attempt_id": attempt2_id, "operation_id": operation2, "kind": "candidate_commit", "target": str(case["repo"]), "checkout": str(case["repo"]), "expected_before": final_candidate["sha"], "base_sha": final_candidate["sha"], "intended_after": done2_sha, "commit_sha": done2_sha, "tree_sha": done2_tree, "authority_ref": "AUTH-Q28-REPAIR-2"})
            state, _ = ledger.load_state(case["paths"])
            run("candidate", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", attempt2_id, "--commit-receipt", str(receipt2), "--operation-id", operation2)
            state, _ = ledger.load_state(case["paths"])
            final_candidate = ledger.current_candidate_record(state, state["tickets"][0])
            self.assertEqual("DONE", final_candidate["quality"])
            self.assertEqual(first_done_id, final_candidate["parent_candidate_ref"])
            self.assertEqual("consumed", next(item for item in state["decisions"] if item.get("id") == "AUTH-Q28-REPAIR")["status"])
            self.assertEqual("consumed", next(item for item in state["decisions"] if item.get("id") == "AUTH-Q28-REPAIR-2")["status"])

            # Fresh PASS review explicitly resolves only the repair finding and
            # the exact external blocker; unrelated issues are not touched.
            final_review = {"identity": {"run_id": continuation_candidates.RUN_ID, "ticket_id": "T-1", "attempt_id": "RV-Q28-FINAL", "epoch": 0}, "kind": "review", "purpose": "ticket_review", "mandate": "Q28 final repaired candidate qualification", "subject_fingerprint": final_candidate["sha"], "criteria": [{"criterion_id": "C-1"}], "axes": ["OFFLINE-SUITE"], "return_target": {"path": "return.json"}}
            final_review_path = root / "q28-final-review.packet.json"
            write_json(final_review_path, final_review)
            run("prepare-review", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--review-attempt-id", "RV-Q28-FINAL", "--lease-id", "L-Q28-FINAL", "--packet", str(final_review_path))
            state, _ = ledger.load_state(case["paths"])
            final_attempt = ledger.attempt_by_id(state, "RV-Q28-FINAL")
            for event, event_id, descendants in (("start", "OBS-Q28-F-START", "not_applicable"), ("stop", "OBS-Q28-F-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": continuation_candidates.RUN_ID, "attempt_id": "RV-Q28-FINAL", "epoch": final_attempt["epoch"], "packet_hash": final_attempt["packet_hash"], "spawn_request_id": final_attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q28-final", "observed_at": "2026-09-18T12:00:00Z", "observer": "q28", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = root / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", "RV-Q28-FINAL", "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = ledger.load_state(case["paths"])
                final_attempt = ledger.attempt_by_id(state, "RV-Q28-FINAL")
            final_return = {"identity": {**final_review["identity"], "packet_hash": final_attempt["packet_hash"]}, "subject_fingerprint": final_candidate["sha"], "verdict": "PASS", "coverage": [{"criterion_id": "C-1", "outcome": "fulfilled", "evidence_refs": ["EV-Q28-OFFLINE-C1"]}], "checks": [{"check_id": "OFFLINE-SUITE", "axis": "OFFLINE-SUITE", "outcome": "fulfilled", "actual": "external fixture restored and suite passed", "evidence_ref": "EV-Q28-OFFLINE"}], "context_refs": ["CTX-Q28-FINAL"], "findings": [], "finding_resolution": [{"finding_ref": finding["id"], "candidate_ref": final_candidate["id"], "evidence_refs": ["EV-Q28-OFFLINE"], "reason": "fresh repaired candidate review resolves the named finding"}, {"finding_ref": finding2["id"], "candidate_ref": final_candidate["id"], "evidence_refs": ["EV-Q28-OFFLINE"], "reason": "fresh repaired candidate review resolves the second named finding"}, {"finding_ref": case["blocker"]["id"], "candidate_ref": final_candidate["id"], "evidence_refs": ["EV-Q28-OFFLINE", "EV-Q28-OFFLINE-C1"], "reason": "fresh exact OFFLINE-SUITE evidence resolves the external fixture blocker"}]}
            final_return_path = case["paths"]["scratch"] / "RV-Q28-FINAL" / "return.json"
            write_json(final_return_path, final_return)
            final_integrity = root / "q28-final.integrity.json"
            write_json(final_integrity, {"status": "PASS", "candidate_fingerprint": final_candidate["sha"], "ledger_hash": ledger.sha256_bytes(case["paths"]["ledger"].read_bytes()), "reviewer_stopped": True})
            run("ingest-return", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", "RV-Q28-FINAL", "--return-file", str(final_return_path), "--kind", "review", "--integrity-receipt", str(final_integrity))
            state, _ = ledger.load_state(case["paths"])
            qualification = max((item for item in state["review_qualifications"] if item["subject_fingerprint"] == final_candidate["sha"]), key=lambda item: item["created_revision"])
            self.assertEqual("PASS", qualification["result"])
            integrated = json.loads(run("integrate", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--qualification-ref", qualification["id"]).stdout)
            self.assertTrue(integrated["integrated"])
            final, _ = ledger.load_state(case["paths"])
            current = ledger.current_candidate_record(final, final["tickets"][0])
            self.assertEqual("INTEGRATED", final["tickets"][0]["state"])
            self.assertEqual(qualification["id"], current["qualification_ref"])
            self.assertEqual("advisory", next(item for item in final["issues"] if item["id"] == case["blocker"]["id"])["impact"])
            self.assertEqual("ACTIVE", final["lifecycle"]["control"])
            self.assertFalse(any(item.get("type") == "review_verdict" and item.get("impact") == "blocking" and not item.get("invalidated_by") for item in final["issues"]))
            self.assertEqual("released", ledger.attempt_by_id(final, attempt_id)["lease"]["state"])
            replay = json.loads(run("integrate", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(final["revision"]), "--qualification-ref", qualification["id"]).stdout)
            self.assertTrue(replay["idempotent"])

    def test_Q28_qualification_resolution_rejects_unrelated_target_and_evidence(self) -> None:
        """Q28 negative: a PASS cannot clear an unrelated issue or foreign evidence."""
        helper = phase_e_reviews.PhaseEReviewQualificationTests()
        with tempfile.TemporaryDirectory() as directory:
            case = helper.prepare_candidate(Path(directory))
            review = helper.prepare_review(case, "ticket_review", attempt_id="RV-Q28-NEG")
            returned = helper.review_return(case, review, verdict="PASS")
            payload = json.loads(returned.read_text(encoding="utf-8"))
            payload["finding_resolution"] = [{"finding_ref": "ISS-UNRELATED", "candidate_ref": review["candidate"]["id"], "evidence_refs": ["EV-ticket_review-coverage", "EV-ticket_review-check"], "reason": "must not clear unrelated issue"}]
            write_json(returned, payload)
            helper.ingest_review(case, review, returned)
            state, _ = ledger.load_state(case["paths"])
            qualification = helper.qualification(state, review["candidate"]["sha"])
            before = case["paths"]["ledger"].read_bytes()
            rejected = run("integrate", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID, "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]), "--qualification-ref", qualification["id"], expect=2)
            self.assertRegex(rejected.stderr.lower(), r"evidence|unique|current|resolution")
            self.assertEqual(before, case["paths"]["ledger"].read_bytes())

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
        """Q30: distinct conflicting and stale reviews keep integration blocked."""
        helper = phase_e_reviews.PhaseEReviewQualificationTests()
        with tempfile.TemporaryDirectory() as directory:
            case = helper.prepare_candidate(Path(directory))
            blocked_review = helper.prepare_review(case, "ticket_review", attempt_id="RV-Q30-BLOCK")
            helper.ingest_review(case, blocked_review, helper.review_return(case, blocked_review, verdict="BLOCK"))
            # A second, independent attempt on the same candidate disagrees;
            # this must create an adjudication obligation rather than replace
            # the accepted BLOCK bytes.
            pass_review = helper.prepare_review(case, "ticket_review", attempt_id="RV-Q30-PASS")
            helper.ingest_review(case, pass_review, helper.review_return(case, pass_review, verdict="PASS"))
            state, raw = ledger.load_state(case["paths"])
            qualification = helper.qualification(state, blocked_review["candidate"]["sha"])
            self.assertEqual("BLOCK", qualification["result"])
            self.assertTrue(any(item.get("type") == "reviewer_disagreement" and item.get("impact") == "blocking" for item in state["issues"]))
            self.assertEqual({"RV-Q30-BLOCK", "RV-Q30-PASS"}, {item["attempt_ref"] for item in state["reviews"] if item.get("subject_fingerprint") == blocked_review["candidate"]["sha"]})

            # A review packet for a stale candidate fingerprint is rejected at
            # prepare time and cannot alter the aggregate.
            stale_packet = case["root"] / "RV-Q30-STALE.packet.json"
            write_json(stale_packet, {
                "identity": {"run_id": phase_e_reviews.RUN_ID, "ticket_id": phase_e_reviews.TICKET_ID, "attempt_id": "RV-Q30-STALE", "epoch": state["owner"]["epoch"], "source_revision": state["revision"], "registration_revision": state["revision"], "subject_revision": state["revision"]},
                "kind": "review", "purpose": "ticket_review", "mandate": "stale candidate review", "subject_fingerprint": "f" * 40,
                "criteria": [{"criterion_id": "C-1"}], "axes": ["ticket_review"], "return_target": {"path": "return.json"},
            })
            stale = run("prepare-review", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID, "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]), "--ticket-id", phase_e_reviews.TICKET_ID, "--review-attempt-id", "RV-Q30-STALE", "--lease-id", "L-RV-Q30-STALE", "--packet", str(stale_packet), expect=2)
            self.assertRegex(stale.stderr.lower(), r"candidate|fingerprint|stale|subject")
            self.assertEqual(raw, case["paths"]["ledger"].read_bytes())

            result = run(
                "integrate", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID,
                "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]),
                "--qualification-ref", qualification["id"], expect=2,
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
        """Q35: public review -> blocked repair worker -> preserve keeps exact provenance."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Bootstrap a create-only candidate through the same disposable
            # Git fixture shape as the public continuation scenario.  The
            # initial state is fixture setup only; every transition below is
            # through the public ledger CLI.
            control, repo = root / "control", root / "repo"
            control.mkdir()
            repo.mkdir()
            run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER)
            subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=PhaseH", "-c", "user.email=phase-h@example.invalid", "commit", "--allow-empty", "-qm", "base"], check=True)
            base_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
            paths = ledger.paths(control, continuation_candidates.RUN_ID)
            state, previous = ledger.load_state(paths)
            state["tickets"] = [{
                "id": "T-1", "goal_ref": "G-1", "criterion_refs": [], "contract_refs": [],
                "dependency_refs": [], "state": "READY", "complexity": "bounded", "risk": "routine",
                "zone": [{"path": "app.txt", "operations": ["create"]}], "current_attempt": None,
                "replacement_refs": [],
            }]
            state["lifecycle"] = {
                "phase": "EXECUTE", "control": "ACTIVE", "reason": None, "issue_refs": [],
                "stop_target": None, "next_action": {"kind": "dispatch", "subject_refs": [], "preconditions": [], "read_refs": []},
            }
            state["revision"] = 1
            state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            state["repository"].update({"checkout": str(repo), "branch": "main", "initial_head": base_sha})
            ledger.validate_ledger(state)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            install_execution_design(paths, repo)
            state, _ = ledger.load_state(paths)
            state["repository"]["initial_head"] = base_sha
            ledger.validate_ledger(state)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))

            state, _ = ledger.load_state(paths)
            intent = ledger.current_intent_binding(state)
            publication = state["design_publication"]
            packet = {
                "identity": {"run_id": continuation_candidates.RUN_ID, "ticket_id": "T-1", "attempt_id": "A-1", "epoch": 0,
                             "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
                             "intent_document_hash": intent["document_hash"], "design_publication_ref": publication["id"],
                             "design_publication_hash": publication["publication_hash"], "design_publication_revision": publication["published_revision"], "contract_refs": []},
                "kind": "worker", "mode": "implement", "goal": "Q35 create candidate", "acceptance": [{"criterion_id": "C-1"}],
                "workspace": {"root": str(repo), "expected_base": base_sha}, "write": {"allow": [{"path": "app.txt", "operations": ["create"]}]},
                "verification": [{"check_id": "TICKET-FOCUSED", "required": True}, {"check_id": "OFFLINE-SUITE", "required": True}, {"check_id": "TICKET-LINT", "required": True}],
                "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}], "return_target": {"path": "return.json"},
                "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"], "intent_document_hash": intent["document_hash"],
            }
            packet_path = root / "q35-initial.packet.json"
            write_json(packet_path, packet)
            run("dispatch", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", "1", "--ticket-id", "T-1", "--attempt-id", "A-1", "--lease-id", "L-Q35-1", "--route-id", "route-q35-1", "--packet", str(packet_path))
            state, _ = ledger.load_state(paths)
            initial_attempt = ledger.attempt_by_id(state, "A-1")
            for event, event_id, descendants in (("start", "OBS-Q35-1-START", "not_applicable"), ("stop", "OBS-Q35-1-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": continuation_candidates.RUN_ID, "attempt_id": "A-1", "epoch": initial_attempt["epoch"], "packet_hash": initial_attempt["packet_hash"], "spawn_request_id": initial_attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q35-initial", "observed_at": "2026-09-18T12:00:00Z", "observer": "q35", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = root / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", "A-1", "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = ledger.load_state(paths)
                initial_attempt = ledger.attempt_by_id(state, "A-1")
            initial_return = {"identity": {**packet["identity"], "packet_hash": initial_attempt["packet_hash"]}, "status": "BLOCKED", "result": "focused work passed; external suite resources are absent", "files": [{"path": "app.txt", "operation": "create"}], "checks": [{"check_id": "TICKET-FOCUSED", "outcome": "pass", "actual": "focused checks", "evidence_ref": "EV-Q35-INITIAL"}, {"check_id": "OFFLINE-SUITE", "outcome": "fail", "actual": "external suite unavailable", "evidence_ref": "EV-Q35-OFFLINE"}, {"check_id": "TICKET-LINT", "outcome": "pass", "actual": "lint passes", "evidence_ref": "EV-Q35-LINT"}], "criteria": [{"criterion_id": "C-1", "outcome": "unsatisfied", "evidence_refs": ["EV-Q35-OFFLINE"]}], "issues": [{"type": "external_test_fixture_blocker", "cause": "environment", "impact": "blocking", "affected_refs": ["T-1", "OFFLINE-SUITE"], "expected": "complete offline suite", "actual": "authoritative resources are absent", "disposition": "preserve in-scope work", "resolution_condition": "restore suite resources"}]}
            initial_return_path = paths["scratch"] / "A-1" / "return.json"
            write_json(initial_return_path, initial_return)
            run("ingest-return", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", "A-1", "--return-file", str(initial_return_path), "--kind", "worker")
            state, _ = ledger.load_state(paths)
            initial_attempt = ledger.attempt_by_id(state, "A-1")
            initial_blocker = next(item for item in state["issues"] if item["source_ref"] == "A-1")
            continuation_auth_id = "AUTH-Q35-CONT-INITIAL"
            run("prepare-effect", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--operation-id", "OP-Q35-INITIAL", "--kind", "candidate_commit", "--target", str(repo), "--expected-before", base_sha, "--authority-ref", continuation_auth_id)
            state, _ = ledger.load_state(paths)
            (repo / "app.txt").write_text("initial candidate\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=PhaseH", "-c", "user.email=phase-h@example.invalid", "commit", "-qm", "initial candidate"], check=True)
            initial_candidate_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
            initial_tree_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], check=True, text=True, capture_output=True).stdout.strip()
            initial_receipt = root / "q35-initial.commit.json"
            write_json(initial_receipt, {"status": "PASS", "run_id": continuation_candidates.RUN_ID, "ticket_id": "T-1", "attempt_id": "A-1", "operation_id": "OP-Q35-INITIAL", "kind": "candidate_commit", "target": str(repo), "checkout": str(repo), "expected_before": base_sha, "base_sha": base_sha, "intended_after": initial_candidate_sha, "commit_sha": initial_candidate_sha, "tree_sha": initial_tree_sha, "authority_ref": continuation_auth_id})
            initial_auth = root / "q35-initial.authorization.json"
            write_json(initial_auth, {"id": continuation_auth_id, "type": "continuation_candidate_authorization", "status": "authorized", "decision": "PRESERVE_CONTINUATION", "reason": "external suite blocker", "evidence_refs": [initial_blocker["id"], initial_attempt["return_ref"]], "affected_refs": ["T-1", "A-1"], "blocker_ref": initial_blocker["id"], "blocker_scope": "external", "external_check_ids": ["OFFLINE-SUITE"], "external_criterion_ids": ["C-1"]})
            run("preserve-blocked-candidate", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--attempt-id", "A-1", "--authorization-file", str(initial_auth), "--commit-receipt", str(initial_receipt), "--operation-id", "OP-Q35-INITIAL")
            state, _ = ledger.load_state(paths)
            continuation = ledger.current_candidate_record(state, state["tickets"][0])
            review_packet = {
                "identity": {"run_id": continuation_candidates.RUN_ID, "ticket_id": continuation_candidates.TICKET_ID, "attempt_id": "RV-Q35", "epoch": 0},
                "kind": "review", "purpose": "ticket_review", "mandate": "Q35 candidate-bound review", "subject_fingerprint": continuation["sha"],
                "criteria": [{"criterion_id": "C-1"}], "axes": ["correctness"], "return_target": {"path": "return.json"},
            }
            review_path = root / "q35-review.packet.json"
            write_json(review_path, review_packet)
            run("prepare-review", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", continuation_candidates.TICKET_ID, "--review-attempt-id", "RV-Q35", "--lease-id", "L-Q35", "--packet", str(review_path))
            state, _ = ledger.load_state(paths)
            review_attempt = ledger.attempt_by_id(state, "RV-Q35")
            for event, event_id, descendants in (("start", "OBS-Q35-R-START", "not_applicable"), ("stop", "OBS-Q35-R-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": continuation_candidates.RUN_ID, "attempt_id": "RV-Q35", "epoch": review_attempt["epoch"], "packet_hash": review_attempt["packet_hash"], "spawn_request_id": review_attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q35-review", "observed_at": "2026-09-18T12:00:00Z", "observer": "q35", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = root / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", "RV-Q35", "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = ledger.load_state(paths)
                review_attempt = ledger.attempt_by_id(state, "RV-Q35")
            review_return = {"identity": {**review_packet["identity"], "packet_hash": review_attempt["packet_hash"]}, "subject_fingerprint": continuation["sha"], "verdict": "BLOCK", "coverage": [{"criterion_id": "C-1", "outcome": "partial", "evidence_refs": ["EV-Q35"]}], "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "failed", "actual": "repair needed", "evidence_ref": "EV-Q35"}], "context_refs": ["CTX-Q35"], "findings": [{"axis": "correctness", "impact": "blocking", "claim": "candidate defect", "expected": "fixed", "actual": "not fixed", "evidence": "EV-Q35", "affected_refs": ["T-1"]}]}
            review_return_path = paths["scratch"] / "RV-Q35" / "return.json"
            write_json(review_return_path, review_return)
            integrity = root / "q35-review.integrity.json"
            write_json(integrity, {"status": "PASS", "candidate_fingerprint": continuation["sha"], "ledger_hash": ledger.sha256_bytes(paths["ledger"].read_bytes()), "reviewer_stopped": True})
            run("ingest-return", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", "RV-Q35", "--return-file", str(review_return_path), "--kind", "review", "--integrity-receipt", str(integrity))
            state, _ = ledger.load_state(paths)
            finding = next(item for item in reversed(state["findings"]) if item.get("source_ref") == "RV-Q35")
            repair = {"cause": "implementation", "finding_ref": finding["id"], "hypothesis": "repair exact reviewed candidate", "expected_proof": "fresh worker evidence", "stopping_condition": "focused check passes", "causal_change": "change only app.txt", "source_attempt_ref": "RV-Q35"}
            repair_path = root / "q35-repair.json"
            write_json(repair_path, repair)
            run("authorize-repair", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--finding-ref", finding["id"], "--authorization-id", "AUTH-Q35", "--repair-contract", str(repair_path))
            state, _ = ledger.load_state(paths)
            repair_packet = copy.deepcopy(packet)
            repair_packet["identity"] = {**packet["identity"], "attempt_id": "A-Q35"}
            repair_packet["mode"] = "repair"
            repair_packet["repair"] = repair
            repair_packet["workspace"] = {"root": str(repo), "expected_base": continuation["sha"]}
            repair_packet["write"] = {"allow": [{"path": "app.txt", "operations": ["modify"]}]}
            repair_packet_path = root / "q35-worker.packet.json"
            write_json(repair_packet_path, repair_packet)
            run("dispatch", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--attempt-id", "A-Q35", "--lease-id", "L-Q35-W", "--route-id", "route-q35", "--packet", str(repair_packet_path))
            after, _ = ledger.load_state(paths)
            repair_attempt = ledger.attempt_by_id(after, "A-Q35")
            provenance = repair_attempt.get("repair_lease_provenance")
            self.assertIsInstance(provenance, dict)
            self.assertEqual("A-1", provenance["source_attempt_ref"])
            self.assertEqual(continuation["sha"], provenance["candidate_sha"])
            self.assertEqual("AUTH-Q35", repair_attempt["repair_authorization_ref"])
            self.assertEqual(finding["id"], provenance["finding_ref"])
            self.assertEqual(continuation["sha"], repair_attempt["base_sha"])
            self.assertEqual([{"path": "app.txt", "operations": ["modify"]}], repair_attempt["lease"]["zone"])
            self.assertEqual("A-1", repair_attempt["repair_contract"]["source_attempt_ref"])
            self.assertEqual([{"path": "app.txt", "operations": ["modify"]}], provenance["expanded_entries"])
            self.assertEqual("A-1", provenance["lineage"][0]["attempts"][0]["attempt_ref"])
            self.assertEqual("create", provenance["lineage"][0]["attempts"][0]["operation"])

            for event, event_id, descendants in (("start", "OBS-Q35-W-START", "not_applicable"), ("stop", "OBS-Q35-W-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": continuation_candidates.RUN_ID, "attempt_id": "A-Q35", "epoch": repair_attempt["epoch"], "packet_hash": repair_attempt["packet_hash"], "spawn_request_id": repair_attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q35-repair", "observed_at": "2026-09-18T12:00:00Z", "observer": "q35", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = root / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(after["revision"]), "--attempt-id", "A-Q35", "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                after, _ = ledger.load_state(paths)
                repair_attempt = ledger.attempt_by_id(after, "A-Q35")
            repair_return = {"identity": {**repair_packet["identity"], "packet_hash": repair_attempt["packet_hash"]}, "status": "BLOCKED", "result": "focused repair passed; external suite remains unavailable", "files": [{"path": "app.txt", "operation": "modify"}], "checks": [{"check_id": "TICKET-FOCUSED", "outcome": "pass", "actual": "focused repair passes", "evidence_ref": "EV-Q35-REPAIR"}, {"check_id": "OFFLINE-SUITE", "outcome": "fail", "actual": "external suite unavailable", "evidence_ref": "EV-Q35-REPAIR-OFFLINE"}, {"check_id": "TICKET-LINT", "outcome": "pass", "actual": "lint passes", "evidence_ref": "EV-Q35-REPAIR-LINT"}], "criteria": [{"criterion_id": "C-1", "outcome": "unsatisfied", "evidence_refs": ["EV-Q35-REPAIR-OFFLINE"]}], "issues": [{"type": "external_test_fixture_blocker", "cause": "environment", "impact": "blocking", "affected_refs": ["T-1", "OFFLINE-SUITE"], "expected": "complete offline suite", "actual": "authoritative resources are absent", "disposition": "preserve repair work", "resolution_condition": "restore suite resources"}]}
            repair_return_path = paths["scratch"] / "A-Q35" / "return.json"
            write_json(repair_return_path, repair_return)
            run("ingest-return", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(after["revision"]), "--attempt-id", "A-Q35", "--return-file", str(repair_return_path), "--kind", "worker")
            after, _ = ledger.load_state(paths)
            repair_attempt = ledger.attempt_by_id(after, "A-Q35")
            repair_blocker = next(item for item in after["issues"] if item["source_ref"] == "A-Q35")
            continuation_auth = root / "q35-continuation.authorization.json"
            continuation_auth_id = "AUTH-Q35-CONT"
            run("prepare-effect", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(after["revision"]), "--operation-id", "OP-Q35-REPAIR", "--kind", "candidate_commit", "--target", str(repo), "--expected-before", continuation["sha"], "--authority-ref", continuation_auth_id)
            after, _ = ledger.load_state(paths)
            (repo / "app.txt").write_text("repair handoff\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=PhaseH", "-c", "user.email=phase-h@example.invalid", "commit", "-qm", "repair handoff"], check=True)
            repair_candidate_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
            repair_tree_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], check=True, text=True, capture_output=True).stdout.strip()
            repair_receipt = root / "q35-repair.commit.json"
            write_json(repair_receipt, {"status": "PASS", "run_id": continuation_candidates.RUN_ID, "ticket_id": "T-1", "attempt_id": "A-Q35", "operation_id": "OP-Q35-REPAIR", "kind": "candidate_commit", "target": str(repo), "checkout": str(repo), "expected_before": continuation["sha"], "base_sha": continuation["sha"], "intended_after": repair_candidate_sha, "commit_sha": repair_candidate_sha, "tree_sha": repair_tree_sha, "authority_ref": continuation_auth_id})
            write_json(continuation_auth, {"id": continuation_auth_id, "type": "continuation_candidate_authorization", "status": "authorized", "decision": "PRESERVE_CONTINUATION", "reason": "external suite blocker", "evidence_refs": [repair_blocker["id"], repair_attempt["return_ref"]], "affected_refs": ["T-1", "A-Q35"], "blocker_ref": repair_blocker["id"], "blocker_scope": "external", "external_check_ids": ["OFFLINE-SUITE"], "external_criterion_ids": ["C-1"]})
            run("preserve-blocked-candidate", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(after["revision"]), "--ticket-id", "T-1", "--attempt-id", "A-Q35", "--authorization-file", str(continuation_auth), "--commit-receipt", str(repair_receipt), "--operation-id", "OP-Q35-REPAIR")
            final, _ = ledger.load_state(paths)
            final_attempt = ledger.attempt_by_id(final, "A-Q35")
            continuation_receipt = ledger.stored_payload(paths, final_attempt["continuation_ref"], "Q35 continuation")
            self.assertEqual(repair_attempt["return_ref"], continuation_receipt["return_ref"])
            self.assertEqual("A-Q35", continuation_receipt["attempt_id"])
            self.assertEqual(provenance, continuation_receipt["repair_lease_provenance"])
            self.assertEqual(continuation["sha"], continuation_receipt["base_sha"])
            self.assertEqual(repair_candidate_sha, continuation_receipt["candidate_sha"])
            self.assertEqual(repair_blocker["id"], continuation_receipt["blocker_ref"])
            self.assertEqual("AUTH-Q35", repair_attempt["repair_authorization_ref"])
            self.assertEqual(continuation_auth_id, final_attempt["continuation_authorization_ref"])
            parents = subprocess.run(["git", "-C", str(repo), "rev-list", "--parents", "-n", "1", repair_candidate_sha], check=True, text=True, capture_output=True).stdout.strip().split()
            self.assertEqual(repair_candidate_sha, parents[0])
            self.assertEqual(continuation["sha"], parents[1])
            self.assertEqual(continuation["sha"], continuation_receipt["base_sha"])
            continuation_ref = final_attempt["continuation_ref"]
            continuation_path = paths["objects"] / continuation_ref.removeprefix("objects/")
            original_receipt_bytes = continuation_path.read_bytes()
            continuation_path.write_bytes(original_receipt_bytes + b"tampered")
            rejected = run("preserve-blocked-candidate", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(final["revision"]), "--ticket-id", "T-1", "--attempt-id", "A-Q35", "--authorization-file", str(continuation_auth), "--commit-receipt", str(repair_receipt), "--operation-id", "OP-Q35-REPAIR", expect=2)
            self.assertIn("object", rejected.stderr.lower())
            continuation_path.write_bytes(original_receipt_bytes)
            continuation_path.unlink()
            run("preserve-blocked-candidate", "--control-root", str(control), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(final["revision"]), "--ticket-id", "T-1", "--attempt-id", "A-Q35", "--authorization-file", str(continuation_auth), "--commit-receipt", str(repair_receipt), "--operation-id", "OP-Q35-REPAIR", expect=2)

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
        """Q41: deny, identity mismatch, object tamper, and write-set scope fail closed."""
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
            before_identity = paths["ledger"].read_bytes()
            # A worker return whose identity names a different ticket is
            # rejected before publication, even though its packet hash is
            # otherwise valid.
            attempt = ledger.attempt_by_id(state, "A-G")
            wrong_return = paths["scratch"] / "A-G" / "return.json"
            write_json(wrong_return, {
                "identity": {**packet["identity"], "ticket_id": "T-FOREIGN", "packet_hash": attempt["packet_hash"]},
                "status": "DONE", "result": "foreign worker", "files": [],
                "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "pass", "evidence_ref": "EV-Q41"}],
                "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-Q41"]}],
            })
            wrong = run("ingest-return", "--control-root", str(control), "--run-id", phase_g_binding.RUN_ID, "--owner-token", phase_g_binding.OWNER, "--revision", str(state["revision"]), "--attempt-id", "A-G", "--return-file", str(wrong_return), "--kind", "worker", expect=2)
            self.assertRegex(wrong.stderr.lower(), r"identity|ticket|subject|match")
            self.assertEqual(before_identity, paths["ledger"].read_bytes())

            # Audit the actual disposable Git write set in this same Q case;
            # a declared in-zone file cannot hide a foreign generated cache.
            repo = root / "write-set-repo"
            repo.mkdir()
            (repo / "app.txt").write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "baseline"], check=True)
            baseline = root / "q41-baseline.json"
            declared = root / "q41-declared.json"
            zone = root / "q41-zone.json"
            write_json(baseline, {"base_sha": "baseline", "files": [{"path": "app.txt", "type": "file", "mode": 420, "sha256": ledger.sha256_bytes(b"baseline\n")}]})
            write_json(declared, [{"path": "app.txt", "operation": "modify"}])
            write_json(zone, [{"path": "app.txt", "operations": ["modify"]}])
            (repo / ".review-cache").mkdir()
            (repo / ".review-cache" / "trace.json").write_text("foreign\n", encoding="utf-8")
            audit = json.loads(run("audit-write-set", "--root", str(repo), "--baseline", str(baseline), "--declared", str(declared), "--zone", str(zone)).stdout)
            self.assertIn(".review-cache/trace.json", audit["undeclared_paths"])
            self.assertFalse(audit["pass"])

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
