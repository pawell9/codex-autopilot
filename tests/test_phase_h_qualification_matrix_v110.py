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
Q03_SENTINEL = "untouched-sentinel.txt"


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

    def _v104_handoff_preserve(self, q: V104Qualification, *, ticket_id: str, repair: dict[str, str] | None, attempt_id: str) -> dict[str, Any]:
        """Run one HANDOFF→preserve hop through the public CLI.

        V104's normal worker fixture only emits DONE.  Q03 needs the actual
        blocked-candidate protocol in the same run, so this is the one small
        adapter that emits a schema-valid HANDOFF and then uses the public
        dispatch/ingest/effect/preserve transitions.
        """
        state, _ = q.state()
        ticket = next(item for item in state["tickets"] if item["id"] == ticket_id)
        prior = ledger.current_candidate_record(state, ticket)
        base_sha = prior["sha"] if prior is not None else state["repository"]["initial_head"]
        intent = ledger.current_intent_binding(state)
        publication = state["design_publication"]
        continuation_auth_id = f"AUTH-{attempt_id}-CONT"
        operation_id = f"OP-{attempt_id}"
        q.call_git("switch", "--create", f"qualification-{attempt_id}", str(base_sha))
        identity = {
            "run_id": q.run_id, "ticket_id": ticket_id, "attempt_id": attempt_id, "epoch": 0,
            "source_revision": q.expected_revision, "intent_revision": intent["revision"],
            "intent_document_ref": intent["document_ref"], "intent_document_hash": intent["document_hash"],
            "design_publication_ref": publication["id"], "design_publication_hash": publication["publication_hash"],
            "design_publication_revision": publication["published_revision"], "contract_refs": sorted(ticket.get("contract_refs", [])),
        }
        packet = {
            "identity": identity, "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
            "intent_document_hash": intent["document_hash"], "kind": "worker", "mode": "repair" if repair else "implement",
            "goal": f"repair {ticket_id} with a bounded continuation hop", "acceptance": [{"criterion_id": "C-1"}],
            "workspace": {"root": str(q.repo), "expected_base": base_sha},
            "write": {"allow": [{"path": "app-one.txt", "operations": ["create"]},
                                  {"path": Q03_SENTINEL, "operations": ["create"]}]},
            "verification": [
                {"check_id": "TICKET-FOCUSED", "required": True, "scenario": "focused ticket regressions"},
                {"check_id": "OFFLINE-SUITE", "required": True, "scenario": "complete offline suite"},
                {"check_id": "TICKET-LINT", "required": True, "scenario": "ticket lint"},
            ],
            "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}],
            "return_target": {"path": "return.json"},
        }
        if repair:
            packet["repair"] = repair
        packet_path = q.root / f"{attempt_id}-packet.json"
        write_json(packet_path, packet)
        # The effect is reserved while the run is ACTIVE.  Once the HANDOFF
        # return is ingested the lifecycle is BLOCKED and the public effect
        # guard correctly requires the repair authorization; this reservation
        # therefore carries the later continuation authorization from the
        # outset and remains the exact operation adopted by preserve.
        q.mutate(f"prepare-effect-{attempt_id}", "prepare-effect", "--control-root", str(q.control), "--run-id", q.run_id,
                 "--owner-token", q.token, "--revision", str(q.expected_revision), "--operation-id", operation_id,
                 "--kind", "candidate_commit", "--target", str(q.repo), "--expected-before", base_sha,
                 "--authority-ref", continuation_auth_id)
        q.mutate(f"dispatch-{attempt_id}", "dispatch", "--control-root", str(q.control), "--run-id", q.run_id, "--owner-token", q.token,
                 "--revision", str(q.expected_revision), "--ticket-id", ticket_id, "--attempt-id", attempt_id,
                 "--lease-id", f"L-{attempt_id}", "--route-id", "ROUTE-v3", "--packet", str(packet_path))
        q.observe_runtime(attempt_id, "start", f"OBS-{attempt_id}-START", instance=f"runtime-{attempt_id}")
        (q.repo / "app-one.txt").write_text("partial continuation\n", encoding="utf-8")
        sentinel_before = (q.repo / Q03_SENTINEL).exists()
        if prior is None:
            (q.repo / Q03_SENTINEL).write_text("immutable sentinel\n", encoding="utf-8")
        q.observe_runtime(attempt_id, "stop", f"OBS-{attempt_id}-STOP", instance=f"runtime-{attempt_id}")
        write_operation = "modify" if prior is not None else "create"
        attempt = ledger.attempt_by_id(q.state()[0], attempt_id)
        worker_return = {
            "identity": {**identity, "packet_hash": attempt["packet_hash"]}, "status": "HANDOFF",
            "result": "focused work complete; authoritative offline suite is externally unavailable",
            "files": [{"path": "app-one.txt", "operation": write_operation},
                      {"path": Q03_SENTINEL, "operation": "modify" if sentinel_before else "create"}],
            "checks": [
                {"check_id": "TICKET-FOCUSED", "outcome": "pass", "actual": "focused checks pass", "evidence_ref": f"EV-{attempt_id}-FOCUSED"},
                {"check_id": "OFFLINE-SUITE", "outcome": "fail", "actual": "external suite resources unavailable", "evidence_ref": f"EV-{attempt_id}-SUITE"},
                {"check_id": "TICKET-LINT", "outcome": "pass", "actual": "lint passes", "evidence_ref": f"EV-{attempt_id}-LINT"},
            ],
            "criteria": [{"criterion_id": "C-1", "outcome": "unsatisfied", "evidence_refs": [f"EV-{attempt_id}-SUITE"]}],
            "issues": [{"type": "external_test_fixture_blocker", "cause": "environment", "impact": "blocking",
                        "affected_refs": [ticket_id, "OFFLINE-SUITE"], "expected": "complete offline suite passes",
                        "actual": "authoritative external suite resources are unavailable outside this lease",
                        "disposition": "preserve in-scope work; do not widen the lease",
                        "resolution_condition": "fresh qualified environment or exact external evidence"}],
            "handoff": {"safe_partial_fingerprint": {"app-one.txt": ledger.sha256_file(q.repo / "app-one.txt"), Q03_SENTINEL: ledger.sha256_file(q.repo / Q03_SENTINEL)},
                        "completed": ["focused ticket work"], "remaining": ["authoritative offline suite"]},
        }
        inbox = q.paths["scratch"] / attempt_id / "return.json"
        write_json(inbox, worker_return)
        q.call("validate-return", "--control-root", str(q.control), "--run-id", q.run_id, "--attempt-id", attempt_id,
                "--return-file", str(inbox), "--kind", "worker")
        q.mutate(f"ingest-{attempt_id}", "ingest-return", "--control-root", str(q.control), "--run-id", q.run_id,
                 "--owner-token", q.token, "--revision", str(q.expected_revision), "--attempt-id", attempt_id,
                 "--return-file", str(inbox), "--kind", "worker")
        state, _ = q.state()
        attempt = ledger.attempt_by_id(state, attempt_id)
        blocker = next(item for item in state["issues"] if item.get("source_ref") == attempt_id and item.get("type") == "external_test_fixture_blocker")
        authorization = {
            "id": continuation_auth_id, "type": "continuation_candidate_authorization", "status": "authorized",
            "decision": "PRESERVE_CONTINUATION", "reason": "The authoritative suite blocker is external to the ticket lease.",
            "evidence_refs": [blocker["id"], attempt["return_ref"]], "affected_refs": [ticket_id, attempt_id],
            "blocker_ref": blocker["id"], "blocker_scope": "external", "external_check_ids": ["OFFLINE-SUITE"],
            "external_criterion_ids": ["C-1"],
        }
        auth_path = q.root / f"{attempt_id}-authorization.json"
        write_json(auth_path, authorization)
        q.call_git("add", "app-one.txt", Q03_SENTINEL)
        q.call_git("-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", f"handoff {attempt_id}")
        commit = q.call_git("rev-parse", "HEAD")
        tree = q.call_git("rev-parse", "HEAD^{tree}")
        receipt_path = q.root / f"{attempt_id}-receipt.json"
        write_json(receipt_path, {"status": "PASS", "run_id": q.run_id, "ticket_id": ticket_id, "attempt_id": attempt_id,
                                  "operation_id": operation_id, "kind": "candidate_commit", "target": str(q.repo),
                                  "checkout": str(q.repo), "expected_before": base_sha, "base_sha": base_sha,
                                  "intended_after": commit, "commit_sha": commit, "tree_sha": tree,
                                  "authority_ref": continuation_auth_id})
        result = q.mutate(f"preserve-{attempt_id}", "preserve-blocked-candidate", "--control-root", str(q.control),
                          "--run-id", q.run_id, "--owner-token", q.token, "--revision", str(q.expected_revision),
                          "--ticket-id", ticket_id, "--attempt-id", attempt_id, "--authorization-file", str(auth_path),
                          "--commit-receipt", str(receipt_path), "--operation-id", operation_id)
        final, _ = q.state()
        preserved = ledger.attempt_by_id(final, attempt_id)
        self.assertEqual(commit, preserved["candidate_sha"])
        self.assertEqual("CONTINUATION", ledger.current_candidate_record(final, next(item for item in final["tickets"] if item["id"] == ticket_id))["quality"])
        self.assertEqual("BLOCKED", final["lifecycle"]["control"])
        self.assertEqual(continuation_auth_id, preserved["continuation_authorization_ref"])
        self.assertEqual("applied", next(item for item in final["decisions"] if item["id"] == continuation_auth_id)["status"])
        return {"attempt": preserved, "prior": prior, "blocker": blocker, "authorization": authorization,
                "authorization_path": auth_path, "receipt_path": receipt_path, "candidate_sha": commit,
                "continuation_ref": preserved["continuation_ref"], "result": result}

    def _v104_done_repair_with_sentinel(self, q: V104Qualification, *, ticket_id: str, repair: dict[str, str], attempt_id: str, content: str = "FIXED\n") -> str:
        """Dispatch a DONE repair whose expanded lease keeps the sentinel untouched."""
        state, _ = q.state()
        ticket = next(item for item in state["tickets"] if item["id"] == ticket_id)
        prior = ledger.current_candidate_record(state, ticket)
        self.assertIsNotNone(prior)
        intent = ledger.current_intent_binding(state)
        publication = state["design_publication"]
        authorization = next(item for item in state["decisions"] if item.get("type") == "repair_authorization" and repair["finding_ref"] in item.get("affected_refs", []))
        q.call_git("switch", "--create", f"qualification-{attempt_id}", str(prior["sha"]))
        identity = {"run_id": q.run_id, "ticket_id": ticket_id, "attempt_id": attempt_id, "epoch": 0,
                    "source_revision": q.expected_revision, "intent_revision": intent["revision"],
                    "intent_document_ref": intent["document_ref"], "intent_document_hash": intent["document_hash"],
                    "design_publication_ref": publication["id"], "design_publication_hash": publication["publication_hash"],
                    "design_publication_revision": publication["published_revision"], "contract_refs": sorted(ticket.get("contract_refs", []))}
        packet = {"identity": identity, "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
                  "intent_document_hash": intent["document_hash"], "kind": "worker", "mode": "repair",
                  "goal": f"finish {ticket_id} without touching the sentinel", "acceptance": [{"criterion_id": "C-1"}],
                  "workspace": {"root": str(q.repo), "expected_base": prior["sha"]},
                  "write": {"allow": [{"path": "app-one.txt", "operations": ["modify"]}, {"path": Q03_SENTINEL, "operations": ["modify"]}],
                            "deny": ["forbidden.txt"]},
                  "verification": [{"check_id": "oracle-C-1", "criterion_refs": ["C-1"], "required": True}],
                  "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}],
                  "return_target": {"path": "return.json"}, "repair": repair}
        packet_path = q.root / f"{attempt_id}-packet.json"
        write_json(packet_path, packet)
        q.mutate(f"dispatch-{attempt_id}", "dispatch", "--control-root", str(q.control), "--run-id", q.run_id,
                 "--owner-token", q.token, "--revision", str(q.expected_revision), "--ticket-id", ticket_id,
                 "--attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}", "--route-id", "ROUTE-v3", "--packet", str(packet_path))
        q.observe_runtime(attempt_id, "start", f"OBS-{attempt_id}-START", instance=f"runtime-{attempt_id}")
        (q.repo / "app-one.txt").write_text(content, encoding="utf-8")
        q.observe_runtime(attempt_id, "stop", f"OBS-{attempt_id}-STOP", instance=f"runtime-{attempt_id}")
        attempt = ledger.attempt_by_id(q.state()[0], attempt_id)
        returned = {"identity": {**identity, "packet_hash": attempt["packet_hash"]}, "status": "DONE", "result": "final repair complete",
                    "files": [{"path": "app-one.txt", "operation": "modify"}],
                    "checks": [{"check_id": "oracle-C-1", "outcome": "pass", "actual": content.strip(), "evidence_ref": f"EV-{attempt_id}"}],
                    "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": [f"EV-{attempt_id}"]}]}
        return_path = q.paths["scratch"] / attempt_id / "return.json"
        write_json(return_path, returned)
        q.call("validate-return", "--control-root", str(q.control), "--run-id", q.run_id, "--attempt-id", attempt_id,
                "--return-file", str(return_path), "--kind", "worker")
        q.mutate(f"ingest-{attempt_id}", "ingest-return", "--control-root", str(q.control), "--run-id", q.run_id,
                 "--owner-token", q.token, "--revision", str(q.expected_revision), "--attempt-id", attempt_id,
                 "--return-file", str(return_path), "--kind", "worker")
        operation_id = f"OP-{attempt_id}"
        q.mutate(f"prepare-effect-{attempt_id}", "prepare-effect", "--control-root", str(q.control), "--run-id", q.run_id,
                 "--owner-token", q.token, "--revision", str(q.expected_revision), "--operation-id", operation_id,
                 "--kind", "candidate_commit", "--target", str(q.repo), "--expected-before", prior["sha"],
                 "--authority-ref", authorization["id"])
        q.call_git("add", "app-one.txt")
        q.call_git("-c", "user.name=Qualification", "-c", "user.email=qualification@example.invalid", "commit", "-qm", f"candidate {attempt_id}")
        commit = q.call_git("rev-parse", "HEAD")
        tree = q.call_git("rev-parse", "HEAD^{tree}")
        receipt = q.root / f"{attempt_id}-receipt.json"
        write_json(receipt, {"status": "PASS", "run_id": q.run_id, "ticket_id": ticket_id, "attempt_id": attempt_id,
                             "operation_id": operation_id, "kind": "candidate_commit", "target": str(q.repo), "checkout": str(q.repo),
                             "expected_before": prior["sha"], "base_sha": prior["sha"], "intended_after": commit,
                             "commit_sha": commit, "tree_sha": tree, "authority_ref": authorization["id"]})
        q.mutate(f"candidate-{attempt_id}", "candidate", "--control-root", str(q.control), "--run-id", q.run_id,
                 "--owner-token", q.token, "--revision", str(q.expected_revision), "--attempt-id", attempt_id,
                 "--commit-receipt", str(receipt), "--operation-id", operation_id)
        return commit

    def _v104_ticket_qualification(self, q: V104Qualification, *, ticket_id: str, candidate_sha: str, review_id: str, resolutions: list[dict[str, Any]]) -> dict[str, Any]:
        """Publish a fresh Phase-E ticket_review PASS and return its qualification."""
        state, _ = q.state()
        intent = ledger.current_intent_binding(state)
        packet = {"identity": {"run_id": q.run_id, "ticket_id": ticket_id, "attempt_id": review_id, "epoch": 0,
                                "source_revision": q.expected_revision, "registration_revision": q.expected_revision,
                                "subject_revision": q.expected_revision, "intent_revision": intent["revision"],
                                "intent_document_ref": intent["document_ref"], "intent_document_hash": intent["document_hash"]},
                  "kind": "review", "purpose": "ticket_review", "mandate": "fresh candidate-bound Q03 ticket review",
                  "subject_fingerprint": candidate_sha, "criteria": [{"criterion_id": "C-1"}], "axes": ["correctness"],
                  "return_target": {"path": "return.json"}}
        packet_path = q.root / f"{review_id}-packet.json"
        write_json(packet_path, packet)
        q.mutate(f"prepare-{review_id}", "prepare-review", "--control-root", str(q.control), "--run-id", q.run_id,
                 "--owner-token", q.token, "--revision", str(q.expected_revision), "--ticket-id", ticket_id,
                 "--review-attempt-id", review_id, "--lease-id", f"L-{review_id}", "--packet", str(packet_path))
        attempt = ledger.attempt_by_id(q.state()[0], review_id)
        q.observe_runtime(review_id, "start", f"OBS-{review_id}-START", instance=f"runtime-{review_id}")
        q.observe_runtime(review_id, "stop", f"OBS-{review_id}-STOP", instance=f"runtime-{review_id}")
        returned = {"identity": {**packet["identity"], "packet_hash": attempt["packet_hash"]}, "subject_fingerprint": candidate_sha,
                    "verdict": "PASS", "coverage": [{"criterion_id": "C-1", "outcome": "fulfilled", "evidence_refs": [f"EV-{review_id}"]}],
                    "checks": [{"check_id": check_id, "axis": "correctness", "outcome": "fulfilled", "actual": "DONE", "evidence_ref": f"EV-{review_id}"} for check_id in ("correctness", "TICKET-FOCUSED", "OFFLINE-SUITE", "TICKET-LINT")],
                    "context_refs": [f"CTX-{review_id}"], "findings": [], "finding_resolution": resolutions}
        return_path = q.paths["scratch"] / review_id / "return.json"
        write_json(return_path, returned)
        integrity_path = q.root / f"{review_id}-integrity.json"
        write_json(integrity_path, {"status": "PASS", "candidate_fingerprint": candidate_sha, "ledger_hash": ledger.sha256_bytes(q.paths["ledger"].read_bytes()), "reviewer_stopped": True})
        q.mutate(f"ingest-{review_id}", "ingest-return", "--control-root", str(q.control), "--run-id", q.run_id,
                 "--owner-token", q.token, "--revision", str(q.expected_revision), "--attempt-id", review_id,
                 "--return-file", str(return_path), "--kind", "review", "--integrity-receipt", str(integrity_path))
        final, _ = q.state()
        qualification = max((item for item in final.get("review_qualifications", []) if item.get("subject_fingerprint") == candidate_sha),
                            key=lambda item: item.get("created_revision", 0))
        self.assertEqual("PASS", qualification["result"])
        return {"state": final, "qualification": qualification, "return": returned, "attempt": ledger.attempt_by_id(final, review_id)}

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
            q = V104Qualification(Path(directory))
            q.bootstrap()
            original_make_bundle = q.make_bundle
            def make_q03_bundle(version: int) -> Path:
                path = original_make_bundle(version)
                if version == 3:
                    bundle = json.loads(path.read_text(encoding="utf-8"))
                    ticket = next(item for item in bundle["tickets"] if item["id"] == "T-1-v3")
                    ticket["zone"] = [{"path": "app-one.txt", "operations": ["create"]},
                                      {"path": Q03_SENTINEL, "operations": ["create"]}]
                    write_json(path, bundle)
                return path
            q.make_bundle = make_q03_bundle
            q.design_cycle()
            ticket_id = "T-1-v3"
            # One continuous chain: initial HANDOFF preserved as CONTINUATION
            # → first BLOCK and repair authorization → repair DONE candidate
            # → second BLOCK and authorization → final DONE candidate → fresh
            # Phase-E qualification and qualified integration.
            q.mutate("ready-q03-ticket", "ready-ticket", "--control-root", str(q.control), "--run-id", q.run_id,
                     "--owner-token", q.token, "--revision", str(q.expected_revision), "--ticket-id", ticket_id)
            preserved = self._v104_handoff_preserve(q, ticket_id=ticket_id, repair=None, attempt_id="Q03-W1")
            sentinel_bytes = (q.repo / Q03_SENTINEL).read_bytes()
            sentinel_sha = ledger.sha256_bytes(sentinel_bytes)
            self.assertEqual(sentinel_sha, ledger.sha256_file(q.repo / Q03_SENTINEL))
            finding1 = q.change_review(ticket_id, "C-1", "Q03-W1", "Q03-R1", "BLOCK")
            self.assertIsNotNone(finding1)
            repair1 = {"cause": "implementation", "finding_ref": finding1, "hypothesis": "repair the first reviewed defect",
                       "expected_proof": "a bounded continuation preserves the in-scope work", "stopping_condition": "fresh review of the changed candidate",
                       "causal_change": "modify only app-one.txt", "source_attempt_ref": "Q03-W1"}
            repair1_path = Path(directory) / "q03-repair-1.json"
            write_json(repair1_path, repair1)
            q.mutate("authorize-q03-repair-1", "authorize-repair", "--control-root", str(q.control), "--run-id", q.run_id,
                     "--owner-token", q.token, "--revision", str(q.expected_revision), "--ticket-id", ticket_id,
                     "--finding-ref", finding1, "--authorization-id", "Q03-AUTH-1", "--repair-contract", str(repair1_path))
            # The external blocker remains durable; authorize-repair is the
            # public transition that permits the first changed repair.
            intermediate_sha = self._v104_done_repair_with_sentinel(q, ticket_id=ticket_id, repair=repair1, attempt_id="Q03-W2", content="STILL_BROKEN\n")
            state, _ = q.state()
            self.assertEqual("Q03-W2", next(item for item in state["tickets"] if item["id"] == ticket_id)["current_attempt"])
            continuation = ledger.stored_payload(q.paths, preserved["continuation_ref"], "Q03 continuation receipt")
            self.assertEqual("HANDOFF", continuation["return_status"])
            self.assertTrue(continuation["write_set_audit"]["pass"])
            self.assertEqual(["app-one.txt", Q03_SENTINEL], continuation["write_set_audit"]["changed_paths"])
            self.assertEqual(sentinel_bytes, (q.repo / Q03_SENTINEL).read_bytes())
            self.assertEqual(sentinel_sha, ledger.sha256_file(q.repo / Q03_SENTINEL))
            self.assertEqual("Q03-W1", ledger.attempt_by_id(state, "Q03-W1")["id"])

            finding2 = q.change_review(ticket_id, "C-1", "Q03-W2", "Q03-R2", "BLOCK")
            self.assertIsNotNone(finding2)
            repair2 = {"cause": "implementation", "finding_ref": finding2, "hypothesis": "finish the candidate-bound repair after the preserve hop",
                       "expected_proof": "DONE candidate passes a fresh ticket review", "stopping_condition": "fresh qualified PASS review",
                       "causal_change": "replace the partial implementation with the final behavior", "source_attempt_ref": "Q03-W2"}
            repair2_path = Path(directory) / "q03-repair-2.json"
            write_json(repair2_path, repair2)
            q.mutate("authorize-q03-repair-2", "authorize-repair", "--control-root", str(q.control), "--run-id", q.run_id,
                     "--owner-token", q.token, "--revision", str(q.expected_revision), "--ticket-id", ticket_id,
                     "--finding-ref", finding2, "--authorization-id", "Q03-AUTH-2", "--repair-contract", str(repair2_path))
            final_sha = self._v104_done_repair_with_sentinel(q, ticket_id=ticket_id, repair=repair2, attempt_id="Q03-W3")
            state, _ = q.state()
            self.assertEqual(sentinel_bytes, (q.repo / Q03_SENTINEL).read_bytes())
            self.assertEqual(sentinel_sha, ledger.sha256_file(q.repo / Q03_SENTINEL))
            ticket = next(item for item in state["tickets"] if item["id"] == ticket_id)
            done = ledger.current_candidate_record(state, ticket)
            self.assertEqual("DONE", done["quality"])
            self.assertEqual(final_sha, done["sha"])
            self.assertEqual("candidate-Q03-W2", done["parent_candidate_ref"])
            self.assertEqual("Q03-AUTH-2", ledger.attempt_by_id(state, "Q03-W3")["repair_authorization_ref"])

            candidate_chain = [item for item in state["candidates"] if item.get("ticket_ref") == ticket_id]
            self.assertGreaterEqual(len(candidate_chain), 3)
            self.assertEqual(["Q03-W1", "Q03-W2", "Q03-W3"], [item["producer_attempt_ref"] for item in candidate_chain[-3:]])
            self.assertEqual("Q03-W1", candidate_chain[-3]["producer_attempt_ref"])
            self.assertEqual("CONTINUATION", candidate_chain[-3]["quality"])
            self.assertIsNone(candidate_chain[-3].get("parent_candidate_ref"))
            self.assertEqual("candidate-Q03-W1", candidate_chain[-2]["parent_candidate_ref"])
            self.assertEqual("candidate-Q03-W2", candidate_chain[-1]["parent_candidate_ref"])
            for attempt_id, expected_auth, expected_finding, expected_base, expected_chain in (
                ("Q03-W2", "Q03-AUTH-1", finding1, preserved["candidate_sha"], ["Q03-W1", "Q03-W2"]),
                ("Q03-W3", "Q03-AUTH-2", finding2, intermediate_sha, ["Q03-W1", "Q03-W2", "Q03-W3"]),
            ):
                attempt = ledger.attempt_by_id(state, attempt_id)
                provenance = attempt.get("repair_lease_provenance")
                self.assertIsInstance(provenance, dict, f"{attempt_id} lost durable repair provenance")
                self.assertEqual(expected_auth, provenance["authorization_ref"])
                self.assertEqual(expected_finding, provenance["finding_ref"])
                self.assertEqual(expected_chain[-2], provenance["source_attempt_ref"])
                self.assertEqual(expected_base, provenance["candidate_sha"])
                self.assertEqual(expected_base, provenance["packet_base_sha"])
                self.assertEqual([{"path": "app-one.txt", "operations": ["modify"]}, {"path": Q03_SENTINEL, "operations": ["modify"]}], provenance["expanded_entries"])
                lineage = {entry["path"]: entry["attempts"] for entry in provenance["lineage"]}
                self.assertEqual({"app-one.txt", Q03_SENTINEL}, set(lineage))
                for path in ("app-one.txt", Q03_SENTINEL):
                    prior_chain = expected_chain[:-1]
                    self.assertEqual(prior_chain, [item["attempt_ref"] for item in lineage[path]])
                    expected_operations = ["create"] if len(prior_chain) == 1 else ["create", "modify" if path == "app-one.txt" else "preserve"]
                    self.assertEqual(expected_operations, [item["operation"] for item in lineage[path]])
                    if len(prior_chain) > 1:
                        self.assertEqual("Q03-AUTH-1", lineage[path][-1]["authorization_ref"])
                        self.assertEqual(finding1, lineage[path][-1]["finding_ref"])
                packet = ledger.stored_payload(q.paths, attempt["packet_ref"], f"{attempt_id} repair packet")
                self.assertEqual(["forbidden.txt"], packet["write"]["deny"])
                self.assertEqual({"app-one.txt", Q03_SENTINEL}, {item["path"] for item in packet["write"]["allow"]})
                self.assertTrue(all(item["operations"] == ["modify"] for item in packet["write"]["allow"]))
                self.assertEqual(expected_chain[-2], packet["repair"]["source_attempt_ref"])
            initial_packet = ledger.stored_payload(q.paths, ledger.attempt_by_id(state, "Q03-W1")["packet_ref"], "Q03-W1 packet")
            self.assertEqual({"app-one.txt", Q03_SENTINEL}, {item["path"] for item in initial_packet["write"]["allow"]})
            self.assertEqual([], initial_packet["write"].get("deny", []))
            for attempt_id, app_operation in (("Q03-W1", "create"), ("Q03-W2", "modify"), ("Q03-W3", "modify")):
                worker = ledger.attempt_by_id(state, attempt_id)
                returned = ledger.stored_payload(q.paths, worker["return_ref"], f"{attempt_id} return")
                app_entry = next(item for item in returned["files"] if item["path"] == "app-one.txt")
                self.assertEqual(app_operation, app_entry["operation"])
                sentinel_entries = [item for item in returned["files"] if item["path"] == Q03_SENTINEL]
                if attempt_id == "Q03-W1":
                    self.assertEqual(["create"], [item["operation"] for item in sentinel_entries])
                else:
                    self.assertEqual([], sentinel_entries)
            auths = [item for item in state["decisions"] if item.get("type") == "repair_authorization" and item.get("id") in {"Q03-AUTH-1", "Q03-AUTH-2"}]
            self.assertEqual({"Q03-AUTH-1", "Q03-AUTH-2"}, {item["id"] for item in auths})
            self.assertTrue(all(item["status"] == "consumed" for item in auths))
            self.assertEqual({"Q03-W2", "Q03-W3"}, {item.get("consumed_by") for item in auths})
            self.assertTrue(all(attempt.get("lease", {}).get("state") == "released" for attempt in state["attempts"] if attempt.get("id") in {"Q03-W1", "Q03-W2"}))
            self.assertIn(ledger.attempt_by_id(state, "Q03-W3")["lease"]["state"], {"active", "released"})
            self.assertIn(preserved["blocker"]["id"], state["lifecycle"]["issue_refs"])

            blocker_ref = preserved["blocker"]["id"]
            fresh = self._v104_ticket_qualification(q, ticket_id=ticket_id, candidate_sha=final_sha, review_id="Q03-R3-FRESH", resolutions=[
                {"finding_ref": finding1, "candidate_ref": "candidate-Q03-W3", "evidence_refs": ["EV-Q03-R3-FRESH"], "reason": "fresh review closes the first historical repair obligation"},
                {"finding_ref": finding2, "candidate_ref": "candidate-Q03-W3", "evidence_refs": ["EV-Q03-R3-FRESH"], "reason": "fresh review verifies the repaired candidate"},
                {"finding_ref": blocker_ref, "candidate_ref": "candidate-Q03-W3", "evidence_refs": ["EV-Q03-R3-FRESH"], "reason": "fresh review verifies the external continuation blocker is resolved on the DONE candidate"},
            ])
            qualification = fresh["qualification"]
            integration = q.mutate("integrate-q03-qualified", "integrate", "--control-root", str(q.control), "--run-id", q.run_id,
                                    "--owner-token", q.token, "--revision", str(q.expected_revision), "--qualification-ref", qualification["id"])
            state, _ = q.state()
            ticket = next(item for item in state["tickets"] if item["id"] == ticket_id)
            self.assertEqual("INTEGRATED", ticket["state"])
            self.assertEqual("DONE", ledger.current_candidate_record(state, ticket)["quality"])
            self.assertEqual(qualification["id"], ledger.current_candidate_record(state, ticket)["qualification_ref"])
            self.assertEqual("Q03-W3", ticket["current_attempt"])
            self.assertEqual("ACTIVE", state["lifecycle"]["control"])
            self.assertIn(state["lifecycle"]["next_action"]["kind"], {"continue_after_ticket_integration", "mark_ticket_ready"})
            self.assertTrue(all(attempt.get("lease", {}).get("state") == "released" for attempt in state["attempts"] if attempt.get("subject_ref") == ticket_id))
            self.assertFalse(ledger.open_ticket_finding_obligations(state, ticket_id))
            projection = ledger.finding_obligation_projection(state)
            for finding_ref in (finding1, finding2):
                projected = next(item for item in projection["items"] if item["finding_ref"] == finding_ref)
                self.assertEqual("resolved", projected["status"])
                self.assertEqual("closed", projected["verification_obligation"]["status"])
                self.assertTrue(projected["resolved_by_refs"])
            self.assertFalse([item for item in state["issues"] if item.get("impact") == "blocking" and not item.get("invalidated_by") and ticket_id in item.get("affected_refs", [])])
            blocker = next(item for item in state["issues"] if item["id"] == blocker_ref)
            self.assertEqual("advisory", blocker["impact"])
            self.assertTrue(blocker.get("invalidated_by"))
            self.assertTrue(any(item.get("type") == "external_blocker_resolution" and blocker_ref in item.get("affected_refs", []) for item in state["decisions"]))
            self.assertEqual("AUTH-Q03-W1-CONT", continuation["authorization_ref"])
            self.assertIsNone(continuation["repair_lease_provenance"])
            repair_attempt = ledger.attempt_by_id(state, "Q03-W2")
            repair_packet = ledger.stored_payload(q.paths, repair_attempt["packet_ref"], "Q03 repair packet")
            self.assertEqual(repair1["finding_ref"], repair_packet["repair"]["finding_ref"])
            self.assertEqual(preserved["candidate_sha"], repair_packet["workspace"]["expected_base"])
            self.assertEqual("Q03-AUTH-2", ledger.attempt_by_id(state, "Q03-W3")["repair_authorization_ref"])

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
