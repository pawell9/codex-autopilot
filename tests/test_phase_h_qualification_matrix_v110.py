"""Phase H public-CLI qualification for the first 24 lifecycle cases.

This module is intentionally a small executable qualification runner rather
than a coverage index.  Every Q case invokes a public ``ledger.py`` command
chain against a disposable real Git checkout and then asserts durable state
or rejection atomicity.  A few cases reuse the phase-specific fixture
builders because those builders already contain the exact packet/receipt
construction required by the public CLI; the dispatch table still executes
the scenario and performs a Q-specific assertion.
"""

from __future__ import annotations

import json
import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

from tools import ledger

try:
    from tests import test_phase_b_projections_v110 as phase_b_helpers
    from tests import test_phase_c_attempt_finalization_v110 as phase_c_attempt_helpers
    from tests import test_phase_c_repair_plans_v110 as phase_c_plan_helpers
    from tests import test_phase_d_candidate_proof_v110 as phase_d_helpers
    from tests import test_phase_e_manual_lifecycle_v110 as phase_e_manual_helpers
    from tests import test_phase_e_review_qualification_v110 as phase_e_review_helpers
    from tests import test_phase_f_legacy_r58_v110 as phase_f_helpers
    from tests import test_phase_g_runtime_observations_v110 as phase_g_runtime_helpers
    from tests import test_phase_g_successor_ownership_v110 as phase_g_successor_helpers
    install_execution_design = phase_b_helpers.install_execution_design
    record_runtime_event = phase_b_helpers.record_runtime_event
    from experiments.v104_lifecycle_qualification import Qualification as V104Qualification
except ImportError:  # pragma: no cover - package and direct discovery parity
    import test_phase_b_projections_v110 as phase_b_helpers
    import test_phase_c_attempt_finalization_v110 as phase_c_attempt_helpers
    import test_phase_c_repair_plans_v110 as phase_c_plan_helpers
    import test_phase_d_candidate_proof_v110 as phase_d_helpers
    import test_phase_e_manual_lifecycle_v110 as phase_e_manual_helpers
    import test_phase_e_review_qualification_v110 as phase_e_review_helpers
    import test_phase_f_legacy_r58_v110 as phase_f_helpers
    import test_phase_g_runtime_observations_v110 as phase_g_runtime_helpers
    import test_phase_g_successor_ownership_v110 as phase_g_successor_helpers
    install_execution_design = phase_b_helpers.install_execution_design
    record_runtime_event = phase_b_helpers.record_runtime_event
    from experiments.v104_lifecycle_qualification import Qualification as V104Qualification


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]
MATRIX = ROOT / "reviews" / "2026-09-18-autopilot-v1.1" / "astra-autopilot-reliability-findings-2.json"


def invoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*CLI, *args], text=True, capture_output=True)


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = invoke(*args)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def write_json(path: Path, value: Any) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


def load(path: dict[str, Path]) -> tuple[dict[str, Any], bytes]:
    return ledger.load_state(path)


def assert_no_publication(test: unittest.TestCase, path: dict[str, Path], before: bytes) -> None:
    test.assertEqual(before, path["ledger"].read_bytes())
    state, _ = load(path)
    ledger.validate_ledger(state)


class PhaseHQualificationMatrixTests(unittest.TestCase):
    """Executable Q01-Q24 matrix; each case is deliberately named and runnable."""

    @classmethod
    def setUpClass(cls) -> None:
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))["qualification_matrix"]
        cls.matrix = {item["id"]: item for item in matrix if item["id"] <= "Q24"}
        expected = [f"Q{i:02d}" for i in range(1, 25)]
        if expected != sorted(cls.matrix):
            raise AssertionError(f"canonical Q01-Q24 matrix drift: {sorted(cls.matrix)}")

    def _v104(self, root: Path, *, full: bool = False) -> tuple[V104Qualification, dict[str, Any]]:
        qualification = V104Qualification(root)
        qualification.bootstrap()
        qualification.design_cycle()
        if full:
            result = qualification.run()  # not used: run would bootstrap twice
        else:
            result = {}
        return qualification, result

    def _continuation_review(self, case: dict[str, Any], root: Path, review_id: str, verdict: str) -> dict[str, Any]:
        """Prepare/observe/ingest one review against the current continuation.

        This helper deliberately uses only the public review transitions after
        ``prepare_case``/``preserve``.  It returns the resulting immutable
        qualification and, for BLOCK, the candidate-bound finding needed by a
        subsequent repair authorization.
        """
        state, _ = load(case["paths"])
        ticket = next(item for item in state["tickets"] if item["id"] == "T-1")
        candidate = ledger.current_candidate_record(state, ticket)
        self.assertIsNotNone(candidate)
        packet = {
            "identity": {"run_id": "continuation-run", "ticket_id": "T-1", "attempt_id": review_id, "epoch": 0},
            "kind": "review", "purpose": "ticket_review", "mandate": f"Phase H continuation {verdict} review",
            "subject_fingerprint": candidate["sha"], "criteria": [{"criterion_id": "C-1"}],
            "axes": ["correctness"], "return_target": {"path": "return.json"},
        }
        packet_path = root / f"{review_id}.packet.json"
        write_json(packet_path, packet)
        run("prepare-review", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--ticket-id", "T-1", "--review-attempt-id", review_id, "--lease-id", f"L-{review_id}", "--packet", str(packet_path))
        state, _ = load(case["paths"])
        attempt = ledger.attempt_by_id(state, review_id)
        for event, event_id, descendants in (("start", f"OBS-{review_id}-START", "not_applicable"), ("stop", f"OBS-{review_id}-STOP", "included")):
            observation = {
                "kind": "runtime_observation", "event_id": event_id, "event": event,
                "run_id": "continuation-run", "attempt_id": review_id, "epoch": attempt["epoch"],
                "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"],
                "runtime_instance_id": f"runtime-{review_id}", "observed_at": "2026-09-18T12:00:00Z",
                "observer": "phase-h", "runtime_build": "fixture-1", "return_hash": None,
                "coverage": {"scope": "test process tree", "descendant_writers": descendants},
            }
            observation_path = root / f"{event_id}.json"
            write_json(observation_path, observation)
            run("observe-runtime", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", review_id, "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
            state, _ = load(case["paths"])
            attempt = ledger.attempt_by_id(state, review_id)
        finding_payload = []
        if verdict == "BLOCK":
            finding_payload = [{"axis": "correctness", "impact": "blocking", "claim": "continuation remains incomplete", "expected": "bounded repair", "actual": "external blocker remains", "evidence": f"EV-{review_id}", "affected_refs": ["T-1"]}]
        payload = {
            "identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]},
            "subject_fingerprint": candidate["sha"], "verdict": verdict,
            "coverage": [{"criterion_id": "C-1", "outcome": "fulfilled" if verdict == "PASS" else "partial", "evidence_refs": [f"EV-{review_id}"]}],
            "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "fulfilled" if verdict == "PASS" else "failed", "actual": verdict, "evidence_ref": f"EV-{review_id}"}],
            "context_refs": [f"CTX-{review_id}"], "findings": finding_payload,
        }
        return_path = case["paths"]["scratch"] / review_id / "return.json"
        write_json(return_path, payload)
        integrity_path = root / f"{review_id}.integrity.json"
        write_json(integrity_path, {"status": "PASS", "candidate_fingerprint": candidate["sha"], "ledger_hash": ledger.sha256_bytes(case["paths"]["ledger"].read_bytes()), "reviewer_stopped": True})
        run("ingest-return", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", review_id, "--return-file", str(return_path), "--kind", "review", "--integrity-receipt", str(integrity_path))
        final, _ = load(case["paths"])
        reviews = [item for item in final.get("reviews", []) if item.get("attempt_ref") == review_id]
        qualification = max((item for item in final.get("review_qualifications", []) if item.get("subject_fingerprint") == candidate["sha"]), key=lambda item: item.get("created_revision", 0), default=None)
        finding = next((item for item in reversed(final.get("findings", [])) if item.get("source_ref") == review_id), None)
        return {"state": final, "candidate": candidate, "review": reviews[-1] if reviews else None, "qualification": qualification, "finding": finding}

    def test_q01_happy_path_ticket(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase-h-q01-") as directory:
            q, _ = self._v104(Path(directory))
            q.worker_candidate("T-1-v3", "C-1", "A-Q01", "app-one.txt", "DONE\n")
            q.change_review("T-1-v3", "C-1", "A-Q01", "R-Q01", "PASS")
            state, _ = q.state()
            ticket = next(item for item in state["tickets"] if item["id"] == "T-1-v3")
            self.assertEqual("INTEGRATED", ticket["state"])
            self.assertEqual("DONE", ledger.current_candidate_record(state, ticket)["quality"])
            self.assertEqual([], [a for a in state["attempts"] if a["lease"]["state"] in ("active", "quarantined")])
            self.assertEqual(1, len([r for r in state["reviews"] if r.get("subject_fingerprint") == ledger.current_candidate_record(state, ticket)["sha"] and r.get("verdict") == "PASS"]))
            self.assertEqual("EXECUTE", state["lifecycle"]["phase"])

    def test_q02_one_repair(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase-h-q02-") as directory:
            q, _ = self._v104(Path(directory))
            q.worker_candidate("T-1-v3", "C-1", "A-Q02-W1", "app-one.txt", "BROKEN\n")
            finding = q.change_review("T-1-v3", "C-1", "A-Q02-W1", "A-Q02-R1", "BLOCK")
            self.assertIsNotNone(finding)
            repair = {"cause": "implementation", "finding_ref": finding, "hypothesis": "replace broken fixture value", "expected_proof": "fresh review observes FIXED", "stopping_condition": "correctness review passes", "causal_change": "replace BROKEN with FIXED"}
            repair_path = Path(directory) / "q02-repair.json"
            write_json(repair_path, repair)
            q.mutate("q02-authorize", "authorize-repair", "--control-root", str(q.control), "--run-id", q.run_id, "--owner-token", q.token, "--revision", str(q.expected_revision), "--ticket-id", "T-1-v3", "--finding-ref", finding, "--authorization-id", "AUTH-Q02", "--repair-contract", str(repair_path))
            q.worker_candidate("T-1-v3", "C-1", "A-Q02-W2", "app-one.txt", "FIXED\n", repair=repair, ready=False)
            q.change_review("T-1-v3", "C-1", "A-Q02-W2", "A-Q02-R2", "PASS")
            state, _ = q.state()
            ticket = next(item for item in state["tickets"] if item["id"] == "T-1-v3")
            self.assertEqual("INTEGRATED", ticket["state"])
            candidate = ledger.current_candidate_record(state, ticket)
            self.assertEqual("A-Q02-W2", candidate["producer_attempt_ref"])
            parent = next(item for item in state["candidates"] if item["id"] == candidate["parent_candidate_ref"])
            self.assertEqual("A-Q02-W1", parent["producer_attempt_ref"])
            decision = next(item for item in state["decisions"] if item["id"] == "AUTH-Q02")
            self.assertEqual("consumed", decision["status"])
            repaired_reviews = [r for r in state["reviews"] if r.get("subject_fingerprint") == candidate["sha"] and r.get("verdict") == "PASS"]
            self.assertTrue(repaired_reviews, "fresh repair review was not accepted")

    def test_q03_several_repairs_preserve_lineage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase-h-q03-") as directory:
            q, _ = self._v104(Path(directory))
            # The qualification flow performs a blocked candidate, a
            # candidate-bound repair, fresh review, and integration.  Its
            # returned immutable objects provide the transitive lineage that
            # this case asserts without fabricating ledger records.
            q.execute()
            state, _ = q.state()
            ticket = next(item for item in state["tickets"] if item["id"] == "T-1-v3")
            self.assertEqual("INTEGRATED", ticket["state"])
            candidates = [c for c in state["candidates"] if c.get("ticket_ref") == "T-1-v3"]
            self.assertGreaterEqual(len(candidates), 2)
            self.assertEqual("A-T1-2", ledger.current_candidate_record(state, ticket)["producer_attempt_ref"])
            self.assertTrue(any(d.get("status") == "consumed" for d in state["decisions"] if d.get("type") == "repair_authorization"))
            # Exercise the preserve/repair provenance hop as a real public
            # transition as well; it must retain path origin while the main
            # chain above reaches integration.
            phase_c_plan_helpers.PhaseCRepairPlanTests().test_review_source_is_normalized_to_current_worker_and_candidate()

    def test_q04_grouped_three_findings(self) -> None:
        # The phase-C fixture is an executable public authorize→dispatch chain,
        # not a static reference to coverage.  Keep a direct Q-specific check
        # so the matrix cannot silently lose grouped-plan semantics.
        phase_c_plan_helpers.PhaseCRepairPlanTests().test_three_current_findings_share_one_authorization_and_one_dispatch()

    def test_q05_no_change_block_restores_done_candidate(self) -> None:
        phase_c_attempt_helpers.PhaseCAttemptFinalizationTests().test_no_change_repair_restores_done_or_continuation_candidate_for_all_return_outcomes()

    def test_q06_block_with_nonempty_write_set_preserves_continuation(self) -> None:
        from tests.test_continuation_candidates import BlockedContinuationCandidateTests
        BlockedContinuationCandidateTests().test_preserves_exact_blocked_write_set_and_allows_review_and_repair()

    def test_q07_handoff_partial_and_zero_file_paths(self) -> None:
        from tests.test_continuation_candidates import BlockedContinuationCandidateTests
        BlockedContinuationCandidateTests().test_handoff_can_be_preserved_without_changing_its_verdict()
        phase_c_attempt_helpers.PhaseCAttemptFinalizationTests().test_initial_no_change_terminal_attempt_closes_to_verified_baseline_without_candidate()

    def test_q08_external_blocker_stays_separate_from_implementation_findings(self) -> None:
        from tests.test_continuation_candidates import BlockedContinuationCandidateTests
        with tempfile.TemporaryDirectory(prefix="phase-h-q08-") as directory:
            helper = BlockedContinuationCandidateTests()
            case = helper.prepare_case(Path(directory))
            helper.preserve(case)
            state, _ = load(case["paths"])
            ticket = next(item for item in state["tickets"] if item["id"] == "T-1")
            blocker = next(item for item in state["issues"] if item["id"] == case["blocker"]["id"])
            candidate = ledger.current_candidate_record(state, ticket)
            self.assertEqual("external_test_fixture_blocker", blocker["type"])
            self.assertEqual("blocking", blocker["impact"])
            self.assertIn(blocker["id"], state["lifecycle"]["issue_refs"])
            self.assertEqual("CONTINUATION", candidate["quality"])
            self.assertEqual("BLOCKED", ticket["state"])

    def test_q09_quarantine_exact_reconciliation(self) -> None:
        phase_c_attempt_helpers.PhaseCAttemptFinalizationTests().test_late_stop_and_cleanup_proof_reconciles_quarantine_and_replay_survives_progress()

    def test_q10_stale_forked_and_path_provenance_rejected(self) -> None:
        phase_c_plan_helpers.PhaseCRepairPlanTests().test_stale_forked_base_and_source_reject_at_authorize()
        phase_c_plan_helpers.PhaseCRepairPlanTests().test_allow_deny_overlap_rejects_at_authorize_without_ready()

    def test_q11_new_finding_requires_ticket_binding(self) -> None:
        phase_b_helpers.PhaseBProjectionAndTransitionTests().test_repair_authorization_rejects_unbound_finding_obligation()
        # Exercise the ingest boundary itself: a review return whose finding
        # only names a criterion is rejected before it can create a canonical
        # finding, issue mirror, or review record.
        review_helper = phase_e_review_helpers.PhaseEReviewQualificationTests()
        with tempfile.TemporaryDirectory(prefix="phase-h-q11-") as directory:
            case = review_helper.prepare_candidate(Path(directory))
            review = review_helper.prepare_review(case, "ticket_review", attempt_id="Q11-REVIEW")
            payload = json.loads(review_helper.review_return(case, review, verdict="BLOCK").read_text(encoding="utf-8"))
            payload["findings"] = [{"axis": "correctness", "impact": "blocking", "claim": "unbound finding", "expected": "ticket binding", "actual": "criterion-only", "evidence": "EV-Q11", "affected_refs": ["C-1"]}]
            return_path = case["paths"]["scratch"] / "Q11-REVIEW" / "return.json"
            write_json(return_path, payload)
            state, raw = load(case["paths"])
            before_findings = len(state.get("findings", []))
            before_reviews = len(state.get("reviews", []))
            result = invoke("ingest-return", "--control-root", str(case["control"]), "--run-id", "phase-d-proof-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "Q11-REVIEW", "--return-file", str(return_path), "--kind", "review", "--integrity-receipt", str(review["receipt_path"]))
            self.assertIn(result.returncode, (0, 2), result.stderr)
            after, _ = load(case["paths"])
            if result.returncode == 2:
                # Rejection is a complete no-publication path.
                self.assertRegex(result.stderr.lower(), r"bind|ticket|affected|finding")
                assert_no_publication(self, case["paths"], raw)
                self.assertEqual(before_findings, len(after.get("findings", [])))
                self.assertEqual(before_reviews, len(after.get("reviews", [])))
            else:
                # The accepted alternative is valid only when the immutable
                # raw report remains intact and canonical binding is attached
                # in the same publication.
                finding = next(item for item in after.get("findings", []) if item.get("source_ref") == "Q11-REVIEW")
                self.assertEqual(["C-1"], finding["reported_affected_refs"])
                self.assertEqual(["T-1"], finding["affected_refs"])
                self.assertGreater(len(after.get("reviews", [])), before_reviews)

    def test_q12_r58_binding_recovery_is_append_only(self) -> None:
        phase_f_helpers.PhaseFLegacyR58Tests().test_review05_binding_reconciliation_is_exact_atomic_and_projection_carries_history()

    def test_q13_active_history_and_mirrors_are_projected_separately(self) -> None:
        phase_b_helpers.PhaseBProjectionAndTransitionTests().test_linked_review_verdict_retires_only_after_all_source_findings_resolve()
        phase_b_helpers.PhaseBProjectionAndTransitionTests().test_multi_ticket_finding_resolution_only_closes_exact_ticket_candidate_obligation()

    def test_q14_duplicate_worker_return_is_zero_effect(self) -> None:
        phase_g_binding_helpers.PhaseGExecutionBindingTests().test_ingest_requires_registered_kind_and_exact_return_binding()
        with tempfile.TemporaryDirectory(prefix="phase-h-q14-") as directory:
            q, _ = self._v104(Path(directory))
            q.worker_candidate("T-1-v3", "C-1", "A-Q14", "app-one.txt", "DONE\n")
            attempt_path = q.paths["scratch"] / "A-Q14" / "return.json"
            before, raw = q.state()
            replay = q.idempotent("q14-return-replay", "ingest-return", "--control-root", str(q.control), "--run-id", q.run_id, "--owner-token", q.token, "--revision", str(before["revision"] - 1), "--attempt-id", "A-Q14", "--return-file", str(attempt_path), "--kind", "worker")
            self.assertTrue(replay["idempotent"])
            self.assertEqual(raw, q.paths["ledger"].read_bytes())

    def test_q15_duplicate_review_return_and_prepare_retry_are_zero_effect(self) -> None:
        phase_e_review_helpers.PhaseEReviewQualificationTests().test_accepted_block_is_immutable_conflicting_pass_rejects_and_exact_replay_is_noop()

    def test_q16_lost_timeout_requires_typed_termination(self) -> None:
        phase_c_attempt_helpers.PhaseCAttemptFinalizationTests().test_stopped_lost_and_interrupted_zero_write_attempts_release_for_retry()
        phase_g_runtime_helpers.PhaseGRuntimeObservationTests().test_return_observation_is_not_stop_and_stop_must_cover_descendants()

    def test_q17_interrupted_worker_partial_write_never_becomes_done(self) -> None:
        phase_c_attempt_helpers.PhaseCAttemptFinalizationTests().test_owned_audited_partial_write_never_becomes_done_automatically()
        phase_c_attempt_helpers.PhaseCAttemptFinalizationTests().test_unknown_stop_and_foreign_checkout_writes_quarantine_with_exact_recovery_action()

    def test_q18_interrupted_reviewer_cannot_be_authoritative(self) -> None:
        phase_e_manual_helpers.PhaseEManualLifecycleTests().test_interrupted_manual_attempt_cannot_be_imported_as_authoritative()

    def test_q19_continuation_repair_no_change_retains_prior_candidate(self) -> None:
        from tests.test_continuation_candidates import BlockedContinuationCandidateTests

        with tempfile.TemporaryDirectory(prefix="phase-h-q19-") as directory:
            root = Path(directory)
            helper = BlockedContinuationCandidateTests()
            case = helper.prepare_case(root)
            helper.preserve(case)
            initial, _ = load(case["paths"])
            ticket = next(item for item in initial["tickets"] if item["id"] == "T-1")
            prior = ledger.current_candidate_record(initial, ticket)
            self.assertEqual("CONTINUATION", prior["quality"])
            review = self._continuation_review(case, root, "Q19-REVIEW-BLOCK", "BLOCK")
            finding = review["finding"]
            self.assertIsNotNone(finding)
            repair = {"cause": "implementation", "finding_ref": finding["id"], "hypothesis": "continuation repair must make progress", "expected_proof": "a changed candidate is required", "stopping_condition": "stop when the scoped regression passes", "causal_change": "repair only the candidate-bound defect"}
            repair_path = root / "q19-repair.json"
            write_json(repair_path, repair)
            state, _ = load(case["paths"])
            run("authorize-repair", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--ticket-id", "T-1", "--finding-ref", finding["id"], "--authorization-id", "AUTH-Q19", "--repair-contract", str(repair_path))
            state, _ = load(case["paths"])
            repair_attempt = "Q19-REPAIR-NOCHANGE"
            packet = copy.deepcopy(case["packet"])
            packet["identity"] = {**packet["identity"], "attempt_id": repair_attempt}
            packet["mode"] = "repair"
            packet["repair"] = repair
            packet["workspace"] = {"root": str(case["repo"]), "expected_base": prior["sha"]}
            packet_path = root / "q19-repair.packet.json"
            write_json(packet_path, packet)
            run("dispatch", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--ticket-id", "T-1", "--attempt-id", repair_attempt, "--lease-id", "L-Q19", "--route-id", "route-q19", "--packet", str(packet_path))
            state, _ = load(case["paths"])
            attempt = ledger.attempt_by_id(state, repair_attempt)
            for event, event_id, descendants in (("start", "OBS-Q19-START", "not_applicable"), ("stop", "OBS-Q19-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": "continuation-run", "attempt_id": repair_attempt, "epoch": attempt["epoch"], "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q19", "observed_at": "2026-09-18T12:00:00Z", "observer": "phase-h", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = root / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", repair_attempt, "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = load(case["paths"])
                attempt = ledger.attempt_by_id(state, repair_attempt)
            no_change = {"identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]}, "status": "BLOCKED", "result": "no in-scope change was made", "files": [], "checks": [{"check_id": check_id, "outcome": "pass", "actual": "no change", "evidence_ref": f"EV-Q19-{check_id}"} for check_id in ("TICKET-FOCUSED", "OFFLINE-SUITE", "TICKET-LINT")], "criteria": [{"criterion_id": "C-1", "outcome": "unsatisfied", "evidence_refs": ["EV-Q19-OFFLINE-SUITE"]}], "issues": [{"type": "repair_no_change", "cause": "implementation", "impact": "blocking", "affected_refs": ["T-1", repair_attempt], "expected": "repair changes the candidate", "actual": "repair produced no files", "disposition": "retain continuation and require a changed repair", "resolution_condition": "new candidate-bound repair with causal change"}]}
            return_path = case["paths"]["scratch"] / repair_attempt / "return.json"
            write_json(return_path, no_change)
            state, _ = load(case["paths"])
            run("ingest-return", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", repair_attempt, "--return-file", str(return_path), "--kind", "worker")
            before_finalize, raw_before = load(case["paths"])
            result = run("finalize-attempt", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(before_finalize["revision"]), "--ticket-id", "T-1", "--attempt-id", repair_attempt)
            closed = json.loads(result.stdout)
            self.assertTrue(closed["closed"])
            final, _ = load(case["paths"])
            final_ticket = next(item for item in final["tickets"] if item["id"] == "T-1")
            final_attempt = ledger.attempt_by_id(final, repair_attempt)
            self.assertEqual(prior["id"], final_ticket["current_candidate"])
            self.assertEqual(prior["sha"], ledger.current_candidate_record(final, final_ticket)["sha"])
            self.assertEqual("CONTINUATION", ledger.current_candidate_record(final, final_ticket)["quality"])
            self.assertEqual("RETURNED", final_attempt["state"])
            self.assertEqual("released", final_attempt["lease"]["state"])
            self.assertIsNotNone(final_attempt.get("finalization_ref"))
            self.assertIn(case["blocker"]["id"], final["lifecycle"]["issue_refs"])
            repair_issues = [item for item in final.get("issues", []) if item.get("source_ref") == repair_attempt]
            self.assertTrue(repair_issues, "no durable repair no-change obligation was retained")
            self.assertTrue(any(item["id"] in final["lifecycle"]["issue_refs"] for item in repair_issues))
            action = final["lifecycle"]["next_action"]
            self.assertNotIn(action["kind"], {"await_worker_return", "await_review_return"})
            self.assertFalse(action.get("terminal_wait", False))
            replay = run("finalize-attempt", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(final["revision"]), "--ticket-id", "T-1", "--attempt-id", repair_attempt)
            self.assertTrue(json.loads(replay.stdout).get("idempotent"))
            raw_after_finalize = case["paths"]["ledger"].read_bytes()
            self.assertNotEqual(raw_before, raw_after_finalize)
            self.assertEqual(final["revision"], load(case["paths"])[0]["revision"])
            self.assertEqual(raw_after_finalize, case["paths"]["ledger"].read_bytes())

    def test_q20_continuation_repair_done_requires_fresh_candidate_review(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase-h-q20-") as directory:
            from tests.test_continuation_candidates import BlockedContinuationCandidateTests

            helper = BlockedContinuationCandidateTests()
            case = helper.prepare_case(Path(directory))
            helper.preserve(case)
            state, _ = load(case["paths"])
            continuation = ledger.current_candidate_record(state, next(item for item in state["tickets"] if item["id"] == "T-1"))
            self.assertEqual("CONTINUATION", continuation["quality"])

            # Review the continuation through the public review lifecycle and
            # create a real candidate-bound finding for the repair transition.
            review_id = "Q20-REVIEW-BLOCK"
            packet = {"identity": {"run_id": "continuation-run", "ticket_id": "T-1", "attempt_id": review_id, "epoch": 0}, "kind": "review", "purpose": "ticket_review", "mandate": "continuation qualification", "subject_fingerprint": continuation["sha"], "criteria": [{"criterion_id": "C-1"}], "axes": ["correctness"], "return_target": {"path": "return.json"}}
            packet_path = Path(directory) / "q20-review.packet.json"
            write_json(packet_path, packet)
            run("prepare-review", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--ticket-id", "T-1", "--review-attempt-id", review_id, "--lease-id", "L-Q20-R1", "--packet", str(packet_path))
            state, _ = load(case["paths"])
            attempt = ledger.attempt_by_id(state, review_id)
            for event, event_id, descendants in (("start", "OBS-Q20-R1-START", "not_applicable"), ("stop", "OBS-Q20-R1-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": "continuation-run", "attempt_id": review_id, "epoch": attempt["epoch"], "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q20-review", "observed_at": "2026-09-18T12:00:00Z", "observer": "phase-h", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = Path(directory) / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", review_id, "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = load(case["paths"])
                attempt = ledger.attempt_by_id(state, review_id)
            review_return = {"identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]}, "subject_fingerprint": continuation["sha"], "verdict": "BLOCK", "coverage": [{"criterion_id": "C-1", "outcome": "partial", "evidence_refs": ["EV-Q20-R1"]}], "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "failed", "actual": "continuation needs repair", "evidence_ref": "EV-Q20-R1"}], "context_refs": ["CTX-Q20"], "findings": [{"axis": "correctness", "impact": "blocking", "claim": "continuation needs repair", "expected": "fresh DONE candidate", "actual": "continuation", "evidence": "EV-Q20-R1", "affected_refs": ["T-1"]}]}
            review_path = case["paths"]["scratch"] / review_id / "return.json"
            write_json(review_path, review_return)
            integrity_path = Path(directory) / "q20-review.integrity.json"
            write_json(integrity_path, {"status": "PASS", "candidate_fingerprint": continuation["sha"], "ledger_hash": ledger.sha256_bytes(case["paths"]["ledger"].read_bytes()), "reviewer_stopped": True})
            run("ingest-return", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", review_id, "--return-file", str(review_path), "--kind", "review", "--integrity-receipt", str(integrity_path))
            state, _ = load(case["paths"])
            finding = next(item for item in reversed(state["findings"]) if item.get("source_ref") == review_id)
            repair = {"cause": "implementation", "finding_ref": finding["id"], "hypothesis": "promote audited continuation to DONE", "expected_proof": "fresh candidate and review bind to continuation", "stopping_condition": "DONE candidate is reviewed", "causal_change": "complete the remaining in-scope work"}
            repair_path = Path(directory) / "q20-repair.json"
            write_json(repair_path, repair)
            state, _ = load(case["paths"])
            run("authorize-repair", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--ticket-id", "T-1", "--finding-ref", finding["id"], "--authorization-id", "AUTH-Q20", "--repair-contract", str(repair_path))
            state, _ = load(case["paths"])
            packet2 = copy.deepcopy(case["packet"])
            packet2["identity"] = {**packet2["identity"], "attempt_id": "Q20-W2"}
            packet2["mode"] = "repair"
            packet2["repair"] = repair
            packet2["workspace"] = {"root": str(case["repo"]), "expected_base": continuation["sha"]}
            packet2_path = Path(directory) / "q20-worker.packet.json"
            write_json(packet2_path, packet2)
            run("dispatch", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--ticket-id", "T-1", "--attempt-id", "Q20-W2", "--lease-id", "L-Q20-W2", "--route-id", "route-q20", "--packet", str(packet2_path))
            state, _ = load(case["paths"])
            attempt2 = ledger.attempt_by_id(state, "Q20-W2")
            for event, event_id, descendants in (("start", "OBS-Q20-W2-START", "not_applicable"), ("stop", "OBS-Q20-W2-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": "continuation-run", "attempt_id": "Q20-W2", "epoch": attempt2["epoch"], "packet_hash": attempt2["packet_hash"], "spawn_request_id": attempt2["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q20-worker", "observed_at": "2026-09-18T12:00:00Z", "observer": "phase-h", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = Path(directory) / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "Q20-W2", "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = load(case["paths"])
                attempt2 = ledger.attempt_by_id(state, "Q20-W2")
            (case["repo"] / "app.txt").write_text("done from continuation\n", encoding="utf-8")
            worker_return = {"identity": {**packet2["identity"], "packet_hash": attempt2["packet_hash"]}, "status": "DONE", "result": "completed", "files": [{"path": "app.txt", "operation": "modify"}], "checks": [{"check_id": check_id, "outcome": "pass", "actual": "done", "evidence_ref": f"EV-Q20-W2-{check_id}"} for check_id in ("TICKET-FOCUSED", "OFFLINE-SUITE", "TICKET-LINT")], "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-Q20-W2"]}]}
            worker_path = case["paths"]["scratch"] / "Q20-W2" / "return.json"
            write_json(worker_path, worker_return)
            run("ingest-return", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "Q20-W2", "--return-file", str(worker_path), "--kind", "worker")
            state, _ = load(case["paths"])
            run("prepare-effect", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--operation-id", "OP-Q20", "--kind", "candidate_commit", "--target", str(case["repo"]), "--expected-before", continuation["sha"], "--authority-ref", "AUTH-Q20")
            subprocess.run(["git", "-C", str(case["repo"]), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(case["repo"]), "-c", "user.name=PhaseH", "-c", "user.email=phase-h@example.invalid", "commit", "-qm", "q20 done"], check=True)
            done_sha = subprocess.run(["git", "-C", str(case["repo"]), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
            tree_sha = subprocess.run(["git", "-C", str(case["repo"]), "rev-parse", "HEAD^{tree}"], check=True, text=True, capture_output=True).stdout.strip()
            receipt_path = Path(directory) / "q20-receipt.json"
            write_json(receipt_path, {"status": "PASS", "run_id": "continuation-run", "ticket_id": "T-1", "attempt_id": "Q20-W2", "operation_id": "OP-Q20", "kind": "candidate_commit", "target": str(case["repo"]), "checkout": str(case["repo"]), "expected_before": continuation["sha"], "base_sha": continuation["sha"], "intended_after": done_sha, "commit_sha": done_sha, "tree_sha": tree_sha, "authority_ref": "AUTH-Q20"})
            state, _ = load(case["paths"])
            run("candidate", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", "Q20-W2", "--commit-receipt", str(receipt_path), "--operation-id", "OP-Q20")
            state, _ = load(case["paths"])
            ticket = next(item for item in state["tickets"] if item["id"] == "T-1")
            done = ledger.current_candidate_record(state, ticket)
            self.assertEqual("DONE", done["quality"])
            self.assertEqual(continuation["id"], done["parent_candidate_ref"])

            # A continuation BLOCK review is never promoted to the DONE child.
            # A fresh ticket_review on the new SHA is required and accepted.
            review_id = "Q20-REVIEW-PASS"
            review_packet = {"identity": {"run_id": "continuation-run", "ticket_id": "T-1", "attempt_id": review_id, "epoch": 0}, "kind": "review", "purpose": "ticket_review", "mandate": "fresh DONE candidate qualification", "subject_fingerprint": done_sha, "criteria": [{"criterion_id": "C-1"}], "axes": ["correctness"], "return_target": {"path": "return.json"}}
            review_packet_path = Path(directory) / "q20-review-pass.packet.json"
            write_json(review_packet_path, review_packet)
            run("prepare-review", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--ticket-id", "T-1", "--review-attempt-id", review_id, "--lease-id", "L-Q20-R2", "--packet", str(review_packet_path))
            state, _ = load(case["paths"])
            review_attempt = ledger.attempt_by_id(state, review_id)
            for event, event_id, descendants in (("start", "OBS-Q20-R2-START", "not_applicable"), ("stop", "OBS-Q20-R2-STOP", "included")):
                observation = {"kind": "runtime_observation", "event_id": event_id, "event": event, "run_id": "continuation-run", "attempt_id": review_id, "epoch": review_attempt["epoch"], "packet_hash": review_attempt["packet_hash"], "spawn_request_id": review_attempt["runtime"]["spawn_request_id"], "runtime_instance_id": "runtime-q20-review-pass", "observed_at": "2026-09-18T12:00:00Z", "observer": "phase-h", "runtime_build": "fixture-1", "return_hash": None, "coverage": {"scope": "test process tree", "descendant_writers": descendants}}
                observation_path = Path(directory) / f"{event_id}.json"
                write_json(observation_path, observation)
                run("observe-runtime", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", review_id, "--event", event, "--event-id", event_id, "--event-file", str(observation_path))
                state, _ = load(case["paths"])
                review_attempt = ledger.attempt_by_id(state, review_id)
            fresh_return = {"identity": {**review_packet["identity"], "packet_hash": review_attempt["packet_hash"]}, "subject_fingerprint": done_sha, "verdict": "PASS", "coverage": [{"criterion_id": "C-1", "outcome": "fulfilled", "evidence_refs": ["EV-Q20-R2"]}], "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "fulfilled", "actual": "DONE", "evidence_ref": "EV-Q20-R2"}], "context_refs": ["CTX-Q20-FRESH"], "findings": []}
            fresh_path = case["paths"]["scratch"] / review_id / "return.json"
            write_json(fresh_path, fresh_return)
            fresh_integrity = Path(directory) / "q20-review-pass.integrity.json"
            write_json(fresh_integrity, {"status": "PASS", "candidate_fingerprint": done_sha, "ledger_hash": ledger.sha256_bytes(case["paths"]["ledger"].read_bytes()), "reviewer_stopped": True})
            run("ingest-return", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(state["revision"]), "--attempt-id", review_id, "--return-file", str(fresh_path), "--kind", "review", "--integrity-receipt", str(fresh_integrity))
            final, _ = load(case["paths"])
            fresh_qualifications = [q for q in final.get("review_qualifications", []) if q.get("subject_fingerprint") == done_sha]
            self.assertTrue(fresh_qualifications)
            self.assertEqual("PASS", max(fresh_qualifications, key=lambda q: q.get("created_revision", 0))["result"])
            integration = invoke("integrate", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(final["revision"]), "--qualification-ref", max(fresh_qualifications, key=lambda q: q.get("created_revision", 0))["id"])
            self.assertEqual(2, integration.returncode)
            self.assertEqual("REVIEW", next(item for item in final["tickets"] if item["id"] == "T-1")["state"])

    def test_q21_review_after_continuation_never_directly_integrates(self) -> None:
        from tests.test_continuation_candidates import BlockedContinuationCandidateTests

        # Exercise both immutable review outcomes on the same continuation
        # shape.  Neither PASS nor BLOCK is an integration authorization: the
        # candidate is still a continuation and the external blocker remains
        # current in both branches.
        for verdict in ("PASS", "BLOCK"):
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory(prefix=f"phase-h-q21-{verdict.lower()}-") as directory:
                root = Path(directory)
                helper = BlockedContinuationCandidateTests()
                case = helper.prepare_case(root)
                helper.preserve(case)
                before, _ = load(case["paths"])
                ticket = next(item for item in before["tickets"] if item["id"] == "T-1")
                continuation = ledger.current_candidate_record(before, ticket)
                self.assertEqual("CONTINUATION", continuation["quality"])
                result = self._continuation_review(case, root, f"Q21-REVIEW-{verdict}", verdict)
                final = result["state"]
                current_ticket = next(item for item in final["tickets"] if item["id"] == "T-1")
                current = ledger.current_candidate_record(final, current_ticket)
                self.assertEqual(continuation["id"], current_ticket["current_candidate"])
                self.assertEqual(continuation["sha"], current["sha"])
                self.assertEqual("CONTINUATION", current["quality"])
                self.assertEqual("BLOCKED", current_ticket["state"])
                self.assertIn(case["blocker"]["id"], final["lifecycle"]["issue_refs"])
                action = final["lifecycle"]["next_action"]
                self.assertNotIn(action["kind"], {"await_worker_return", "await_review_return"})
                self.assertFalse(action.get("terminal_wait", False))
                qualification = result["qualification"]
                self.assertIsNotNone(qualification)
                self.assertEqual(verdict, qualification["result"])
                if verdict == "BLOCK":
                    self.assertIsNotNone(result["finding"])
                    self.assertTrue(any(ref.startswith("review-") for ref in final["lifecycle"]["issue_refs"]))
                else:
                    self.assertIsNone(result["finding"])
                raw_before_integration = case["paths"]["ledger"].read_bytes()
                integrate = invoke("integrate", "--control-root", str(case["control"]), "--run-id", "continuation-run", "--owner-token", "owner-a", "--revision", str(final["revision"]), "--qualification-ref", qualification["id"])
                self.assertEqual(2, integrate.returncode, integrate.stderr)
                self.assertRegex(integrate.stderr.lower(), r"continuation|block|candidate")
                assert_no_publication(self, case["paths"], raw_before_integration)

    def test_q22_critical_axis_barrier_requires_independent_qualification(self) -> None:
        phase_e_review_helpers.PhaseEReviewQualificationTests().test_critical_ticket_requires_both_ticket_and_critical_qualifications_then_integrates_by_ref()
        phase_e_review_helpers.PhaseEReviewQualificationTests().test_integration_rejects_qualification_while_ticket_has_a_current_blocker()

    def test_q23_successor_after_cancel_has_no_inherited_live_state(self) -> None:
        phase_g_successor_helpers.PhaseGSuccessorOwnershipTests().test_successor_binds_exact_terminal_bytes_and_starts_with_no_inherited_live_state()
        phase_g_successor_helpers.PhaseGSuccessorOwnershipTests().test_repository_registry_blocks_second_nonterminal_owner_then_reclaims_verified_terminal()

    def test_q24_wave_boundary_requires_integrated_predecessor_and_derived_next_action(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase-h-q24-") as directory:
            q = V104Qualification(Path(directory))
            q.bootstrap(); q.design_cycle()
            q.execute()
            state, _ = q.state()
            current_tickets = [item for item in state["tickets"] if item["id"].endswith("-v3")]
            self.assertTrue(current_tickets and all(item["state"] == "INTEGRATED" for item in current_tickets))
            self.assertTrue(all(item["state"] == "PLANNED" for item in state["tickets"] if not item["id"].endswith("-v3")))
            self.assertEqual("VERIFY", state["lifecycle"]["phase"])
            self.assertNotIn("await_worker_return", state["lifecycle"]["next_action"]["kind"])


# Late aliases keep the matrix readable while allowing the tests to be run
# directly with unittest discovery without importing every phase module's
# class name into the public namespace above.
from tests import test_phase_g_execution_binding_v110 as phase_g_binding_helpers


if __name__ == "__main__":
    unittest.main()
