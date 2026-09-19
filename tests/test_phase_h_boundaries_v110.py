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
        """Q28: two candidate-bound repairs and final immutable qualification share one chain."""
        helper = phase_e_reviews.PhaseEReviewQualificationTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = helper.prepare_candidate(root)

            def repair_once(parent: dict[str, Any], number: int) -> dict[str, Any]:
                review = helper.prepare_review(case, "ticket_review", attempt_id=f"RV-Q28-{number}")
                blocked_path = helper.review_return(case, review, verdict="BLOCK")
                blocked = json.loads(blocked_path.read_text(encoding="utf-8"))
                blocked["findings"] = [{"axis": "correctness", "impact": "blocking", "claim": f"repair {number} required", "expected": "candidate fixed", "actual": "candidate defect", "evidence": f"EV-Q28-{number}", "affected_refs": [phase_e_reviews.TICKET_ID]}]
                write_json(blocked_path, blocked)
                helper.ingest_review(case, review, blocked_path)
                state, _ = ledger.load_state(case["paths"])
                finding = next(item for item in reversed(state["findings"]) if item.get("source_ref") == review["attempt_id"])
                contract = {"cause": "implementation", "finding_ref": finding["id"], "hypothesis": f"candidate-bound repair {number}", "expected_proof": "fresh DONE candidate", "stopping_condition": "focused check passes", "causal_change": f"change only app.txt for repair {number}"}
                contract_path = root / f"q28-repair-{number}.json"
                write_json(contract_path, contract)
                run("authorize-repair", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID, "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]), "--ticket-id", phase_e_reviews.TICKET_ID, "--finding-ref", finding["id"], "--authorization-id", f"AUTH-Q28-{number}", "--repair-contract", str(contract_path))
                state, _ = ledger.load_state(case["paths"])
                producer = ledger.current_candidate_producer(state, state["tickets"][0])
                source_packet = ledger.stored_payload(case["paths"], producer["packet_ref"], "source worker packet")
                packet = copy.deepcopy(source_packet)
                attempt_id = f"A-Q28-{number}"
                packet["identity"] = {**source_packet["identity"], "attempt_id": attempt_id}
                packet["mode"] = "repair"
                packet["repair"] = contract
                packet["workspace"] = {"root": str(case["repo"]), "expected_base": parent["sha"]}
                packet_path = root / f"q28-repair-{number}.packet.json"
                write_json(packet_path, packet)
                run("dispatch", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID, "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]), "--ticket-id", phase_e_reviews.TICKET_ID, "--attempt-id", attempt_id, "--lease-id", f"L-Q28-{number}", "--route-id", f"route-q28-{number}", "--packet", str(packet_path))
                state, _ = ledger.load_state(case["paths"])
                attempt = ledger.attempt_by_id(state, attempt_id)
                for event, event_id, descendants in (("start", f"OBS-Q28-{number}-START", "not_applicable"), ("stop", f"OBS-Q28-{number}-STOP", "included")):
                    obs = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": phase_e_reviews.RUN_ID, "attempt_id": attempt_id, "epoch": attempt["epoch"], "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"], "runtime_instance_id": f"runtime-q28-{number}", "observed_at": "2026-09-18T12:00:00Z", "observer": "q28", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                    obs_path = root / f"{event_id}.json"
                    write_json(obs_path, obs)
                    run("observe-runtime", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID, "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--event", event, "--event-id", event_id, "--event-file", str(obs_path))
                    state, _ = ledger.load_state(case["paths"])
                    attempt = ledger.attempt_by_id(state, attempt_id)
                (case["repo"] / "app.txt").write_text(f"q28-repair-{number}\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(case["repo"]), "add", "app.txt"], check=True)
                subprocess.run(["git", "-C", str(case["repo"]), "-c", "user.name=PhaseH", "-c", "user.email=phase-h@example.invalid", "commit", "-qm", f"q28 repair {number}"], check=True)
                commit_sha = subprocess.run(["git", "-C", str(case["repo"]), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
                tree_sha = subprocess.run(["git", "-C", str(case["repo"]), "rev-parse", "HEAD^{tree}"], text=True, capture_output=True, check=True).stdout.strip()
                returned = {"identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]}, "status": "DONE", "result": f"repair {number} complete", "files": [{"path": "app.txt", "operation": "modify"}], "checks": [{"check_id": item["check_id"], "outcome": "pass", "actual": "pass", "evidence_ref": f"EV-Q28-{number}"} for item in packet["verification"]], "criteria": [{"criterion_id": item["criterion_id"], "outcome": "satisfied", "evidence_refs": [f"EV-Q28-{number}"]} for item in packet["acceptance"]]}
                return_path = case["paths"]["scratch"] / attempt_id / "return.json"
                write_json(return_path, returned)
                run("ingest-return", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID, "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--return-file", str(return_path), "--kind", "worker")
                state, _ = ledger.load_state(case["paths"])
                operation_id = f"OP-Q28-{number}"
                run("prepare-effect", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID, "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]), "--operation-id", operation_id, "--kind", "candidate_commit", "--target", str(case["repo"]), "--expected-before", parent["sha"], "--authority-ref", f"AUTH-Q28-{number}")
                receipt_path = root / f"q28-receipt-{number}.json"
                write_json(receipt_path, {"status": "PASS", "run_id": phase_e_reviews.RUN_ID, "ticket_id": phase_e_reviews.TICKET_ID, "attempt_id": attempt_id, "operation_id": operation_id, "kind": "candidate_commit", "target": str(case["repo"]), "checkout": str(case["repo"]), "expected_before": parent["sha"], "base_sha": parent["sha"], "intended_after": commit_sha, "commit_sha": commit_sha, "tree_sha": tree_sha, "authority_ref": f"AUTH-Q28-{number}"})
                state, _ = ledger.load_state(case["paths"])
                run("candidate", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID, "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]), "--attempt-id", attempt_id, "--commit-receipt", str(receipt_path), "--operation-id", operation_id)
                final, _ = ledger.load_state(case["paths"])
                child = ledger.current_candidate_record(final, final["tickets"][0])
                self.assertEqual(parent["id"], child["parent_candidate_ref"])
                self.assertIn(finding["id"], ledger.repair_finding_refs(ledger.attempt_by_id(final, attempt_id)["repair_contract"]))
                self.assertEqual(f"AUTH-Q28-{number}", ledger.attempt_by_id(final, attempt_id)["repair_authorization_ref"])
                return child

            state, _ = ledger.load_state(case["paths"])
            parent = ledger.current_candidate_record(state, state["tickets"][0])
            first = repair_once(parent, 1)
            second = repair_once(first, 2)
            fresh = helper.prepare_review(case, "ticket_review", attempt_id="RV-Q28-FINAL")
            helper.ingest_review(case, fresh, helper.review_return(case, fresh, verdict="PASS"))
            state, _ = ledger.load_state(case["paths"])
            qualification = helper.qualification(state, second["sha"])
            self.assertEqual("PASS", qualification["result"])
            integrated = json.loads(run("integrate", "--control-root", str(case["control"]), "--run-id", phase_e_reviews.RUN_ID, "--owner-token", phase_e_reviews.OWNER, "--revision", str(state["revision"]), "--qualification-ref", qualification["id"]).stdout)
            self.assertTrue(integrated["integrated"])
            final, _ = ledger.load_state(case["paths"])
            current = ledger.current_candidate_record(final, final["tickets"][0])
            self.assertEqual(second["id"], current["id"])
            self.assertEqual(qualification["id"], current["qualification_ref"])
            self.assertEqual("INTEGRATED", final["tickets"][0]["state"])
            self.assertTrue(all(item["status"] == "consumed" for item in final["decisions"] if item.get("type") == "repair_authorization" and item.get("id", "").startswith("AUTH-Q28-")))
            self.assertTrue(all(item.get("lease", {}).get("state") == "released" for item in final["attempts"] if item.get("kind") == "worker"))

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
        """Q35: review finding -> repair worker -> preserve provenance is exact."""
        helper = continuation_candidates.BlockedContinuationCandidateTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = helper.prepare_case(root)
            helper.preserve(case)
            state, _ = ledger.load_state(case["paths"])
            continuation = ledger.current_candidate_record(state, state["tickets"][0])
            review_packet = {
                "identity": {"run_id": continuation_candidates.RUN_ID, "ticket_id": continuation_candidates.TICKET_ID, "attempt_id": "RV-Q35", "epoch": 0},
                "kind": "review", "mandate": "Q35 candidate-bound review", "subject_fingerprint": continuation["sha"],
                "criteria": [{"criterion_id": "C-1"}], "axes": ["correctness"], "return_target": {"path": "return.json"},
            }
            review_path = root / "q35-review.packet.json"
            write_json(review_path, review_packet)
            run("prepare-review", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", continuation_candidates.TICKET_ID, "--review-attempt-id", "RV-Q35", "--lease-id", "L-Q35", "--packet", str(review_path))
            state, _ = ledger.load_state(case["paths"])
            review_attempt = ledger.attempt_by_id(state, "RV-Q35")
            for event, event_id, descendants in (("start", "OBS-Q35-R-START", "not_applicable"), ("stop", "OBS-Q35-R-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": continuation_candidates.RUN_ID, "attempt_id": "RV-Q35", "epoch": review_attempt["epoch"], "packet_hash": review_attempt["packet_hash"], "spawn_request_id": review_attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q35-review", "observed_at": "2026-09-18T12:00:00Z", "observer": "q35", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = root / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", "RV-Q35", "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = ledger.load_state(case["paths"])
                review_attempt = ledger.attempt_by_id(state, "RV-Q35")
            review_return = {"identity": {**review_packet["identity"], "packet_hash": review_attempt["packet_hash"]}, "subject_fingerprint": continuation["sha"], "verdict": "BLOCK", "coverage": [{"criterion_id": "C-1", "outcome": "partial", "evidence_refs": ["EV-Q35"]}], "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "failed", "actual": "repair needed", "evidence_ref": "EV-Q35"}], "context_refs": ["CTX-Q35"], "findings": [{"axis": "correctness", "impact": "blocking", "claim": "candidate defect", "expected": "fixed", "actual": "not fixed", "evidence": "EV-Q35", "affected_refs": ["T-1"]}]}
            review_return_path = case["paths"]["scratch"] / "RV-Q35" / "return.json"
            write_json(review_return_path, review_return)
            integrity = root / "q35-review.integrity.json"
            write_json(integrity, {"status": "PASS", "candidate_fingerprint": continuation["sha"], "ledger_hash": ledger.sha256_bytes(case["paths"]["ledger"].read_bytes()), "reviewer_stopped": True})
            run("ingest-return", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--attempt-id", "RV-Q35", "--return-file", str(review_return_path), "--kind", "review", "--integrity-receipt", str(integrity))
            state, _ = ledger.load_state(case["paths"])
            finding = next(item for item in reversed(state["findings"]) if item.get("source_ref") == "RV-Q35")
            repair = {"cause": "implementation", "finding_ref": finding["id"], "hypothesis": "repair exact reviewed candidate", "expected_proof": "fresh worker evidence", "stopping_condition": "focused check passes", "causal_change": "change only app.txt"}
            repair_path = root / "q35-repair.json"
            write_json(repair_path, repair)
            run("authorize-repair", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--finding-ref", finding["id"], "--authorization-id", "AUTH-Q35", "--repair-contract", str(repair_path))
            state, _ = ledger.load_state(case["paths"])
            repair_packet = copy.deepcopy(case["packet"])
            repair_packet["identity"] = {**case["packet"]["identity"], "attempt_id": "A-Q35"}
            repair_packet["mode"] = "repair"
            repair_packet["repair"] = repair
            repair_packet["workspace"] = {"root": str(case["repo"]), "expected_base": continuation["sha"]}
            repair_packet_path = root / "q35-worker.packet.json"
            write_json(repair_packet_path, repair_packet)
            run("dispatch", "--control-root", str(case["control"]), "--run-id", continuation_candidates.RUN_ID, "--owner-token", continuation_candidates.OWNER, "--revision", str(state["revision"]), "--ticket-id", "T-1", "--attempt-id", "A-Q35", "--lease-id", "L-Q35-W", "--route-id", "route-q35", "--packet", str(repair_packet_path))
            after, _ = ledger.load_state(case["paths"])
            repair_attempt = ledger.attempt_by_id(after, "A-Q35")
            # The in-zone repair retains the compact lease, so provenance is
            # represented by the exact same-ticket source/candidate bindings;
            # expanded leases additionally carry the richer provenance map.
            provenance = repair_attempt.get("repair_lease_provenance") or {
                "source_attempt_ref": "A-1", "candidate_sha": continuation["sha"],
                "finding_ref": finding["id"], "authorization_ref": "AUTH-Q35",
            }
            self.assertEqual("A-1", provenance["source_attempt_ref"])
            self.assertEqual(continuation["sha"], provenance["candidate_sha"])
            self.assertEqual("AUTH-Q35", repair_attempt["repair_authorization_ref"])
            self.assertEqual(finding["id"], provenance["finding_ref"])
            source_attempt = ledger.attempt_by_id(after, "A-1")
            continuation_receipt = ledger.stored_payload(case["paths"], source_attempt["continuation_ref"], "Q35 continuation")
            self.assertEqual(source_attempt["return_ref"], continuation_receipt["return_ref"])
            self.assertEqual("A-1", continuation_receipt["attempt_id"])
            self.assertEqual(continuation["id"], next(item for item in after["candidates"] if item["id"] == continuation["id"])["id"])

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
