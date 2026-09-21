from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools import ledger

try:
    import test_phase_d_candidate_proof_v110 as phase_d_helpers
except ImportError:  # Support package-style unittest discovery too.
    from tests import test_phase_d_candidate_proof_v110 as phase_d_helpers


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]
RUN_ID = "phase-d-proof-run"
OWNER = "owner-a"
TICKET_ID = "T-1"


def invoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*CLI, *args], text=True, capture_output=True)


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = invoke(*args)
    if result.returncode != expect:
        raise AssertionError(
            f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}"
        )
    return result


def write_json(path: Path, value: Any) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


class PhaseEReviewQualificationTests(unittest.TestCase):
    def prepare_candidate(self, root: Path, *, risk: str = "routine") -> dict[str, Any]:
        helper = phase_d_helpers.PhaseDCandidateProofTests()
        case = helper.prepare_done_candidate(root)
        run(*helper.candidate_args(case, receipt_path=case["receipt_path"]))
        state, _ = ledger.load_state(case["paths"])
        if risk != "routine":
            # Risk is a fixture policy input; preserve the real candidate and
            # all lifecycle transitions produced by the public CLI.
            ticket = next(item for item in state["tickets"] if item["id"] == TICKET_ID)
            ticket["risk"] = risk
            ledger.refresh_control_projection(state)
            ledger.validate_ledger(state)
            ledger.atomic_write(case["paths"]["ledger"], ledger.canonical_bytes(state))
        return {**case, "helper": helper}

    @staticmethod
    def qualification(state: dict[str, Any], candidate_sha: str) -> dict[str, Any]:
        matches = [
            item for item in state.get("review_qualifications", [])
            if item.get("subject_ref") == TICKET_ID and item.get("subject_fingerprint") == candidate_sha
        ]
        if not matches:
            raise AssertionError(f"no qualification recorded for {TICKET_ID} / {candidate_sha}")
        return max(matches, key=lambda item: item.get("created_revision", 0))

    def prepare_review(self, case: dict[str, Any], purpose: str, *, attempt_id: str | None = None, mandate: str | None = None) -> dict[str, Any]:
        state, _ = ledger.load_state(case["paths"])
        candidate = ledger.current_candidate_record(
            state, next(item for item in state["tickets"] if item["id"] == TICKET_ID)
        )
        attempt_id = attempt_id or f"RV-{purpose.upper()}"
        packet_path = case["root"] / f"{attempt_id}.packet.json"
        packet = {
            "identity": {
                "run_id": RUN_ID,
                "ticket_id": TICKET_ID,
                "attempt_id": attempt_id,
                "epoch": state["owner"]["epoch"],
                "source_revision": state["revision"],
                "registration_revision": state["revision"],
                "subject_revision": state["revision"],
            },
            "kind": "review",
            "purpose": purpose,
            "mandate": mandate or f"Independent {purpose} qualification for {candidate['id']}.",
            "subject_fingerprint": candidate["sha"],
            "criteria": [{"criterion_id": "C-1"}],
            "axes": [purpose],
            "return_target": {"path": "return.json"},
        }
        write_json(packet_path, packet)
        run(
            "prepare-review", "--control-root", str(case["control"]), "--run-id", RUN_ID,
            "--owner-token", OWNER, "--revision", str(state["revision"]), "--ticket-id", TICKET_ID,
            "--review-attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}", "--packet", str(packet_path),
        )
        prepared, raw = ledger.load_state(case["paths"])
        attempt = ledger.attempt_by_id(prepared, attempt_id)
        for event, event_id, descendants in (("start", f"OBS-{attempt_id}-START", "not_applicable"), ("stop", f"OBS-{attempt_id}-STOP", "included")):
            observation = {
                "kind": "runtime_observation", "event_id": event_id, "event": event,
                "run_id": RUN_ID, "attempt_id": attempt_id, "epoch": attempt["epoch"],
                "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"],
                "runtime_instance_id": f"runtime-{attempt_id}", "observed_at": "2026-09-18T12:00:00Z",
                "observer": "runtime-adapter-test", "runtime_build": "fixture-1", "return_hash": None,
                "coverage": {"scope": "test process tree", "descendant_writers": descendants},
            }
            observation_path = case["root"] / f"{event_id}.json"
            write_json(observation_path, observation)
            run(
                "observe-runtime", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(prepared["revision"]),
                "--attempt-id", attempt_id, "--event", event, "--event-id", event_id,
                "--event-file", str(observation_path),
            )
            prepared, raw = ledger.load_state(case["paths"])
            attempt = ledger.attempt_by_id(prepared, attempt_id)
        receipt_path = case["root"] / f"{attempt_id}.integrity.json"
        write_json(receipt_path, {
            "status": "PASS",
            "candidate_fingerprint": candidate["sha"],
            "ledger_hash": ledger.sha256_bytes(raw),
            "reviewer_stopped": True,
        })
        return {
            "attempt_id": attempt_id,
            "candidate": candidate,
            "attempt": attempt,
            "receipt_path": receipt_path,
        }

    def review_return(
        self, case: dict[str, Any], review: dict[str, Any], *, verdict: str,
        check_outcome: str = "fulfilled",
    ) -> Path:
        attempt = review["attempt"]
        packet = ledger.stored_payload(case["paths"], attempt["packet_ref"], "review packet")
        purpose = packet["purpose"]
        payload = {
            "identity": {
                "run_id": RUN_ID,
                "ticket_id": TICKET_ID,
                "attempt_id": attempt["id"],
                "packet_hash": attempt["packet_hash"],
                "epoch": attempt["epoch"],
                "source_revision": attempt["packet_source_revision"],
                "registration_revision": attempt["packet_registration_revision"],
                "subject_revision": attempt["subject_revision"],
            },
            "subject_fingerprint": review["candidate"]["sha"],
            "verdict": verdict,
            "coverage": [{
                "criterion_id": "C-1", "outcome": "fulfilled", "evidence_refs": [f"EV-{purpose}-coverage"],
            }],
            "checks": [{
                "check_id": f"check-{purpose}", "axis": purpose,
                "outcome": check_outcome, "actual": check_outcome,
                "evidence_ref": f"EV-{purpose}-check",
            }],
            "context_refs": [f"CTX-{purpose}"],
            "findings": [],
        }
        path = case["paths"]["scratch"] / attempt["id"] / "return.json"
        write_json(path, payload)
        return path

    def ingest_review(self, case: dict[str, Any], review: dict[str, Any], return_path: Path, *, expect: int = 0) -> subprocess.CompletedProcess[str]:
        state, _ = ledger.load_state(case["paths"])
        return run(
            "ingest-return", "--control-root", str(case["control"]), "--run-id", RUN_ID,
            "--owner-token", OWNER, "--revision", str(state["revision"]),
            "--attempt-id", review["attempt_id"], "--return-file", str(return_path), "--kind", "review",
            "--integrity-receipt", str(review["receipt_path"]), expect=expect,
        )

    def test_accepted_block_is_immutable_conflicting_pass_rejects_and_exact_replay_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_candidate(Path(directory))
            review = self.prepare_review(case, "ticket_review")
            blocked_return = self.review_return(case, review, verdict="BLOCK")
            self.ingest_review(case, review, blocked_return)
            after_block, raw_after_block = ledger.load_state(case["paths"])
            qualification = self.qualification(after_block, review["candidate"]["sha"])
            self.assertEqual("BLOCK", qualification["result"])
            accepted_review = next(
                item for item in after_block["reviews"] if item.get("attempt_ref") == review["attempt_id"]
            )
            self.assertIn(accepted_review["id"], qualification["accepted_review_refs"])

            replay = json.loads(self.ingest_review(case, review, blocked_return).stdout)
            self.assertTrue(replay["idempotent"])
            self.assertEqual(raw_after_block, case["paths"]["ledger"].read_bytes())

            conflicting_pass = self.review_return(case, review, verdict="PASS")
            current, current_raw = ledger.load_state(case["paths"])
            conflicting_integrity = case["root"] / "conflicting-pass.integrity.json"
            write_json(conflicting_integrity, {
                "status": "PASS",
                "candidate_fingerprint": review["candidate"]["sha"],
                "ledger_hash": ledger.sha256_bytes(current_raw),
                "reviewer_stopped": True,
            })
            # Exercise the old competing integration adapter with a fresh
            # integrity baseline. It must not accept alternate bytes for the
            # already-returned BLOCK attempt.
            run(
                "integrate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(current["revision"]),
                "--attempt-id", review["attempt_id"], "--review-file", str(conflicting_pass),
                "--integrity-receipt", str(conflicting_integrity), "--review-id", "REV-CONFLICTING-PASS",
                expect=2,
            )
            after_legacy_attempt, raw_after_legacy_attempt = ledger.load_state(case["paths"])
            self.assertEqual(raw_after_block, raw_after_legacy_attempt)
            self.assertEqual("BLOCK", self.qualification(
                after_legacy_attempt, review["candidate"]["sha"]
            )["result"])

            result = self.ingest_review(case, review, conflicting_pass, expect=2)
            self.assertRegex(result.stderr.lower(), r"conflict|immutable|already returned|duplicate")
            unchanged, raw_unchanged = ledger.load_state(case["paths"])
            self.assertEqual(raw_after_block, raw_unchanged)
            self.assertEqual("BLOCK", self.qualification(unchanged, review["candidate"]["sha"])["result"])

    def test_amendment_after_candidate_review_preserves_hash_bound_route_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_candidate(Path(directory))
            review = self.prepare_review(case, "ticket_review")
            blocked_return = self.review_return(case, review, verdict="BLOCK")
            self.ingest_review(case, review, blocked_return)

            state, previous = ledger.load_state(case["paths"])
            worker = ledger.attempt_by_id(state, "A-1")
            route = {
                "id": "route-hash-bound",
                "capability": "implementation",
                "reasoning": "deep",
                "requested_binding": "fixture-worker",
                "observed_binding": "fixture-worker",
                "adequacy": "CONFIRMED",
                "context_grade": "PACKET_SCOPED",
            }
            state.setdefault("routes", []).append(copy.deepcopy(route))
            worker["route_ref"] = route["id"]
            worker["execution_binding"]["route_id"] = route["id"]
            worker["execution_binding"]["route_hash"] = ledger.sha256_bytes(ledger.canonical_bytes(route))
            worker["execution_binding_hash"] = ledger.sha256_bytes(
                ledger.canonical_bytes(worker["execution_binding"])
            )
            publication_id = worker["execution_binding"]["design_publication_ref"]
            for publication in [state["design_publication"], *state.get("design_publication_history", [])]:
                if publication.get("id") == publication_id:
                    publication["route_refs"] = sorted(set(publication.get("route_refs", [])) | {route["id"]})
            state["previous_publication_hash"] = ledger.sha256_bytes(previous)
            ledger.validate_ledger(state)
            ledger.atomic_write(case["paths"]["ledger"], ledger.canonical_bytes(state))

            route_before = ledger.canonical_bytes(next(item for item in state["routes"] if item["id"] == route["id"]))
            evidence_before = {
                item["id"]: ledger.canonical_bytes(item) for item in state.get("evidence", [])
            }
            self.assertTrue(state.get("candidates"), "fixture must contain a candidate before amendment")
            self.assertTrue(state.get("reviews"), "fixture must contain an ingested review before amendment")

            amended = case["root"] / "intent-v2.md"
            amended.write_text("# Amended intent\n\nKeep historical route and evidence immutable.\n", encoding="utf-8")
            run(
                "amend", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(state["revision"]),
                "--intent-file", str(amended), "--doc-id", "D-intent-v2",
                "--doc-version", "v2", "--intent-revision", "intent-v2",
                "--amendment-id", "AM-after-candidate-review", "--authority-ref", "user-message",
            )

            amended_state, _ = ledger.load_state(case["paths"])
            route_after = next(item for item in amended_state["routes"] if item["id"] == route["id"])
            self.assertEqual(route_before, ledger.canonical_bytes(route_after))
            self.assertEqual(
                evidence_before,
                {item["id"]: ledger.canonical_bytes(item) for item in amended_state.get("evidence", [])},
            )
            invalidation = next(
                item for item in amended_state["invalidations"]
                if item["amendment_ref"] == "AM-after-candidate-review"
            )
            self.assertIn(route["id"], invalidation["consumer_refs"])
            self.assertTrue(set(evidence_before).issubset(set(invalidation["consumer_refs"])))
            amended_worker = ledger.attempt_by_id(amended_state, "A-1")
            self.assertEqual(
                amended_worker["execution_binding"]["route_hash"],
                ledger.sha256_bytes(ledger.canonical_bytes(route_after)),
            )
            ledger.validate_ledger(amended_state)

    def test_pass_with_failed_required_check_is_rejected_before_review_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_candidate(Path(directory))
            review = self.prepare_review(case, "ticket_review")
            failed = self.review_return(case, review, verdict="PASS", check_outcome="failed")
            before, raw_before = ledger.load_state(case["paths"])

            result = self.ingest_review(case, review, failed, expect=2)
            self.assertRegex(result.stderr.lower(), r"check|failed|pass")
            after, raw_after = ledger.load_state(case["paths"])
            self.assertEqual(raw_before, raw_after)
            self.assertEqual("PREPARED", ledger.attempt_by_id(after, review["attempt_id"])["state"])
            self.assertEqual([], after.get("review_qualifications", []))
            self.assertEqual(before["revision"], after["revision"])

    def test_critical_ticket_requires_both_ticket_and_critical_qualifications_then_integrates_by_ref(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_candidate(Path(directory), risk="critical")
            ticket_review = self.prepare_review(case, "ticket_review", attempt_id="RV-TICKET")
            ticket_return = self.review_return(case, ticket_review, verdict="PASS")
            self.ingest_review(case, ticket_review, ticket_return)
            state, _ = ledger.load_state(case["paths"])
            qualification = self.qualification(state, ticket_review["candidate"]["sha"])
            self.assertEqual(["ticket_review", "critical_axis"], qualification["required_purposes"])
            self.assertEqual("INCOMPLETE", qualification["result"])
            self.assertEqual(["ticket_review"], qualification["satisfied_purposes"])

            critical_review = self.prepare_review(case, "critical_axis", attempt_id="RV-CRITICAL")
            critical_return = self.review_return(case, critical_review, verdict="PASS")
            self.ingest_review(case, critical_review, critical_return)
            state, _ = ledger.load_state(case["paths"])
            qualification = self.qualification(state, ticket_review["candidate"]["sha"])
            self.assertEqual("PASS", qualification["result"])
            self.assertEqual({"ticket_review", "critical_axis"}, set(qualification["satisfied_purposes"]))
            self.assertEqual(2, len(qualification["accepted_review_refs"]))

            integrated = json.loads(run(
                "integrate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(state["revision"]),
                "--qualification-ref", qualification["id"],
            ).stdout)
            final, _ = ledger.load_state(case["paths"])
            candidate = ledger.current_candidate_record(
                final, next(item for item in final["tickets"] if item["id"] == TICKET_ID)
            )
            self.assertTrue(integrated["integrated"])
            self.assertEqual(qualification["id"], candidate["qualification_ref"])

    def test_integration_rejects_qualification_while_ticket_has_a_current_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_candidate(Path(directory))
            review = self.prepare_review(case, "ticket_review")
            review_return = self.review_return(case, review, verdict="PASS")
            self.ingest_review(case, review, review_return)
            state, _ = ledger.load_state(case["paths"])
            qualification = self.qualification(state, review["candidate"]["sha"])
            blocker_id = "I-PHASE-E-OPEN-BLOCKER"
            state.setdefault("issues", []).append({
                "id": blocker_id, "type": "phase_e_open_blocker", "cause": "environment",
                "impact": "blocking", "affected_refs": [TICKET_ID], "expected": "blocker resolved",
                "actual": "blocker remains open", "disposition": "resolve before integration",
                "resolution_condition": "durable evidence closes the blocker", "source_ref": "external-event",
                "invalidated_by": [],
            })
            state["lifecycle"]["control"] = "BLOCKED"
            state["lifecycle"]["reason"] = "phase_e_open_blocker"
            state["lifecycle"]["issue_refs"] = sorted(set(state["lifecycle"].get("issue_refs", []) + [blocker_id]))
            ledger.refresh_control_projection(state)
            ledger.validate_ledger(state)
            ledger.atomic_write(case["paths"]["ledger"], ledger.canonical_bytes(state))
            blocked, raw_blocked = ledger.load_state(case["paths"])

            result = run(
                "integrate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(blocked["revision"]),
                "--qualification-ref", qualification["id"], expect=2,
            )
            self.assertRegex(result.stderr.lower(), r"block|obligation|qualif|integration")
            after, raw_after = ledger.load_state(case["paths"])
            self.assertEqual(raw_blocked, raw_after)
            self.assertEqual("blocking", next(item for item in after["issues"] if item["id"] == blocker_id)["impact"])

    def test_historical_unverifiable_review_defers_only_final_g5_and_preserves_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.prepare_candidate(Path(directory), risk="critical")
            state, _ = ledger.load_state(case["paths"])
            next(item for item in state["criteria"] if item["id"] == "C-1")["oracle"] = "Fresh final G5 review is required."
            ledger.refresh_control_projection(state)
            ledger.validate_ledger(state)
            write_json(case["paths"]["ledger"], state)

            historical = self.prepare_review(case, "ticket_review", attempt_id="RV-HISTORICAL")
            historical_return = self.review_return(case, historical, verdict="UNVERIFIABLE")
            payload = json.loads(historical_return.read_text())
            payload["findings"] = [
                {"axis": "scope_and_exact_write_set", "impact": "blocking", "claim": "Review inputs lack ancestry proof", "expected": "Fresh routine review proves scope", "actual": "Unavailable", "evidence": "EV-SCOPE-MISSING", "affected_refs": ["C-1"]},
                {"axis": "contract_conformance", "impact": "blocking", "claim": "Later G5 is outside this routine packet", "expected": "A fresh final G5 round on this candidate", "actual": "Not yet run", "evidence": "EV-G5-PENDING", "affected_refs": ["C-1"]},
            ]
            write_json(historical_return, payload)
            self.ingest_review(case, historical, historical_return)
            state, _ = ledger.load_state(case["paths"])
            old_review = next(item for item in state["reviews"] if item["attempt_ref"] == historical["attempt_id"])
            other_finding_id, deferred_finding_id = old_review["finding_refs"]

            routine = self.prepare_review(case, "ticket_review", attempt_id="RV-FRESH-ROUTINE", mandate="Fresh evidence-complete scope qualification")
            routine_return = self.review_return(case, routine, verdict="PASS")
            payload = json.loads(routine_return.read_text())
            payload["finding_resolution"] = [{
                "finding_ref": other_finding_id,
                "candidate_ref": routine["candidate"]["id"],
                "evidence_refs": ["EV-ticket_review-check"],
                "reason": "Fresh independent review proves the exact scope.",
            }]
            write_json(routine_return, payload)
            self.ingest_review(case, routine, routine_return)

            critical = self.prepare_review(case, "critical_axis", attempt_id="RV-FRESH-CRITICAL")
            critical_return = self.review_return(case, critical, verdict="PASS")
            self.ingest_review(case, critical, critical_return)
            interrupted = self.prepare_review(case, "critical_axis", attempt_id="RV-INTERRUPTED")
            state, _ = ledger.load_state(case["paths"])
            stopped = ledger.attempt_by_id(state, interrupted["attempt_id"])["runtime"]["stop_ref"]
            run(
                "terminate-attempt", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(state["revision"]),
                "--attempt-id", interrupted["attempt_id"], "--state", "INTERRUPTED",
                "--lease-state", "released", "--evidence", str(case["paths"]["run"] / stopped),
            )
            state, _ = ledger.load_state(case["paths"])
            ticket = next(item for item in state["tickets"] if item["id"] == TICKET_ID)
            ticket["state"] = "REVIEW"
            state["lifecycle"]["control"] = "ACTIVE"
            state["lifecycle"]["reason"] = "test_legacy_resume"
            ledger.refresh_control_projection(state)
            ledger.validate_ledger(state)
            write_json(case["paths"]["ledger"], state)
            before, raw_before = ledger.load_state(case["paths"])
            self.assertEqual("BLOCK", self.qualification(before, routine["candidate"]["sha"])["result"])
            original_review = copy.deepcopy(old_review)
            original_finding = copy.deepcopy(next(item for item in before["findings"] if item["id"] == deferred_finding_id))
            mirror = next(item for item in before["issues"] if item.get("finding_ref") == deferred_finding_id)
            verdict_issue = next(item for item in before["issues"] if item.get("source_ref") == old_review["id"])
            interruption_issue = next(item for item in before["issues"] if item.get("source_ref") == interrupted["attempt_id"])
            routine_review = next(item for item in before["reviews"] if item["attempt_ref"] == routine["attempt_id"])
            critical_review = next(item for item in before["reviews"] if item["attempt_ref"] == critical["attempt_id"])
            args = [
                "reconcile-historical-review-obligations", "--control-root", str(case["control"]),
                "--run-id", RUN_ID, "--owner-token", OWNER, "--revision", str(before["revision"]),
                "--owner-epoch", str(before["owner"]["epoch"]), "--ticket-id", TICKET_ID,
                "--candidate-id", routine["candidate"]["id"], "--historical-review-id", old_review["id"],
                "--routine-review-id", routine_review["id"], "--critical-review-id", critical_review["id"],
                "--deferred-finding-id", deferred_finding_id, "--mirror-issue-id", mirror["id"],
                "--verdict-issue-id", verdict_issue["id"], "--interrupted-attempt-id", interrupted["attempt_id"],
                "--interrupted-issue-id", interruption_issue["id"], "--reconciliation-id", "REC-LEGACY-G5-01",
            ]
            wrong_epoch = args.copy()
            wrong_epoch[wrong_epoch.index("--owner-epoch") + 1] = "99"
            run(*wrong_epoch, expect=2)
            self.assertEqual(raw_before, case["paths"]["ledger"].read_bytes())
            reconciled = json.loads(run(*args).stdout)
            after, raw_after = ledger.load_state(case["paths"])
            self.assertEqual("PASS", self.qualification(after, routine["candidate"]["sha"])["result"])
            self.assertEqual(original_review, next(item for item in after["reviews"] if item["id"] == old_review["id"]))
            self.assertEqual(original_finding, next(item for item in after["findings"] if item["id"] == deferred_finding_id))
            self.assertEqual("closed", next(item for item in ledger.finding_obligation_projection(after)["items"] if item["finding_ref"] == deferred_finding_id)["verification_obligation"]["status"])
            self.assertFalse(after["acceptance"])
            replay = json.loads(run(*args).stdout)
            self.assertTrue(replay["idempotent"])
            self.assertEqual(raw_after, case["paths"]["ledger"].read_bytes())
            run(
                "gate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(after["revision"]),
                "--phase", "VERIFY", "--control", "ACTIVE", "--gate-id", "G4", expect=2,
            )
            integrated = json.loads(run(
                "integrate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(after["revision"]),
                "--qualification-ref", reconciled["qualification_ref"],
            ).stdout)
            self.assertTrue(integrated["integrated"])
            integrated_state, _ = ledger.load_state(case["paths"])
            self.assertFalse([item for item in integrated_state["review_qualifications"] if item["required_purposes"] == ["final_g5"]])
            run(
                "gate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(integrated_state["revision"]),
                "--phase", "VERIFY", "--control", "ACTIVE", "--gate-id", "G4",
            )
            at_g4, _ = ledger.load_state(case["paths"])
            self.assertEqual("VERIFY", at_g4["lifecycle"]["phase"])
            self.assertFalse(at_g4["acceptance"])
            candidate = ledger.current_candidate_record(at_g4, next(item for item in at_g4["tickets"] if item["id"] == TICKET_ID))
            intent = ledger.current_intent_binding(at_g4)
            packet_path = case["root"] / "final-g5-packet.json"
            packet = {
                "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": "RV-FINAL-G5",
                             "epoch": at_g4["owner"]["epoch"], "source_revision": at_g4["revision"],
                             "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
                             "intent_document_hash": intent["document_hash"]},
                "kind": "acceptance", "purpose": "final_g5", "mandate": "Fresh independent final G5",
                "subject_fingerprint": candidate["sha"], "criteria": [{"id": "C-1"}],
                "subject": {"candidate_sha": candidate["sha"], "candidate_tree_sha": candidate["tree_sha"],
                            "export_label": "final-g5-export", "pristine_check_required": True},
                "return_target": {"path": "final-g5-return.json"},
            }
            write_json(packet_path, packet)
            registration = [
                "register-final-g5", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(at_g4["revision"]),
                "--owner-epoch", str(at_g4["owner"]["epoch"]), "--ticket-id", TICKET_ID,
                "--candidate-id", candidate["id"], "--attempt-id", "RV-FINAL-G5",
                "--lease-id", "L-FINAL-G5", "--packet", str(packet_path),
            ]
            wrong_epoch = registration.copy()
            wrong_epoch[wrong_epoch.index("--owner-epoch") + 1] = "99"
            before_registration = case["paths"]["ledger"].read_bytes()
            run(*wrong_epoch, expect=2)
            self.assertEqual(before_registration, case["paths"]["ledger"].read_bytes())
            registered = json.loads(run(*registration).stdout)
            self.assertFalse(registered["idempotent"])
            registered_state, registered_raw = ledger.load_state(case["paths"])
            self.assertFalse(registered_state["acceptance"])
            self.assertEqual("PREPARED", ledger.attempt_by_id(registered_state, "RV-FINAL-G5")["state"])
            self.assertTrue(json.loads(run(*registration).stdout)["idempotent"])
            self.assertEqual(registered_raw, case["paths"]["ledger"].read_bytes())
            projection_path = case["root"] / "final-g5-projection.json"
            write_json(projection_path, {
                "kind": "acceptance_projection", "intent_revision": intent["revision"],
                "intent_document_ref": intent["document_ref"], "intent_document_hash": intent["document_hash"],
                "candidate_fingerprint": candidate["sha"], "goal": "Verify the current intent on the integrated candidate",
                "criteria": [{"id": "C-1"}], "exclusions": [], "return_schema": "acceptance_return",
            })
            run(
                "prepare-handoff", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(registered_state["revision"]),
                "--attempt-id", "RV-FINAL-G5", "--packet", str(packet_path),
                "--projection", str(projection_path), "--export-root", str(case["repo"]),
                "--bundle-root", str(case["root"] / "final-g5-bundle"), "--purpose", "final_g5",
            )
            handoff_state, _ = ledger.load_state(case["paths"])
            self.assertEqual("user_assisted", ledger.attempt_by_id(handoff_state, "RV-FINAL-G5")["mode"])
            self.assertFalse(handoff_state["acceptance"])
            old_attempt = ledger.attempt_by_id(handoff_state, "RV-FINAL-G5")
            stop_path = case["root"] / "final-g5-runtime-stop.json"
            write_json(stop_path, {
                "kind": "runtime_observation", "event_id": "EV-FINAL-G5-STOP", "event": "stop",
                "run_id": RUN_ID, "attempt_id": "RV-FINAL-G5", "epoch": old_attempt["epoch"],
                "packet_hash": old_attempt["packet_hash"],
                "spawn_request_id": old_attempt["runtime"]["spawn_request_id"],
                "runtime_instance_id": "fixture-independent-reviewer", "observed_at": "2026-09-21T12:15:33Z",
                "observer": "fixture-reviewer-runtime", "runtime_build": None,
                "coverage": {"scope": "reviewer and child writers stopped", "descendant_writers": "included"},
            })
            run(
                "observe-runtime", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(handoff_state["revision"]),
                "--attempt-id", "RV-FINAL-G5", "--event", "stop", "--event-id", "EV-FINAL-G5-STOP",
                "--event-file", str(stop_path),
            )
            stopped_state, _ = ledger.load_state(case["paths"])
            rejected_path = case["root"] / "rejected-g5-return.json"
            context_path = case["root"] / "rejected-g5-context.json"
            environment_path = case["root"] / "rejected-g5-environment.json"
            confirmation_path = case["root"] / "rejected-g5-confirmation.json"
            write_json(rejected_path, {
                "kind": "final_g5_return", "verdict": "REJECT", "accepted": False,
                "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": "RV-FINAL-G5",
                             "intent_revision": intent["revision"], "intent_document_hash": intent["document_hash"],
                             "candidate_sha_expected": candidate["sha"],
                             "candidate_tree_sha_expected": candidate["tree_sha"]},
                "criteria": [{"id": "C-1", "status": "unverifiable", "evidence": "missing setup receipt"}],
                "receipts": {"packet_sha256": old_attempt["packet_hash"],
                             "projection_sha256": old_attempt["handoff"]["projection_hash"],
                             "manifest_sha256": old_attempt["handoff"]["manifest_ref"].removeprefix("sha256:")},
            })
            write_json(context_path, {"packet": {"sha256": old_attempt["packet_hash"]},
                                      "projection": {"sha256": old_attempt["handoff"]["projection_hash"]},
                                      "candidate_export": {"manifest_sha256": old_attempt["handoff"]["manifest_ref"].removeprefix("sha256:"),
                                                           "candidate_sha": candidate["sha"], "candidate_tree_sha": candidate["tree_sha"]}})
            write_json(environment_path, {"precheck_status": "recorded_before_review_checks"})
            write_json(confirmation_path, {"reviewer_state": "STOPPED", "attempt_id": "RV-FINAL-G5",
                                           "candidate_sha": candidate["sha"], "scope_closed": True,
                                           "post_return_candidate_mutation": False,
                                           "post_return_control_or_protected_path_mutation": False})
            reconcile = [
                "reconcile-unimportable-final-g5", "--control-root", str(case["control"]),
                "--run-id", RUN_ID, "--owner-token", OWNER, "--revision", str(stopped_state["revision"]),
                "--owner-epoch", str(stopped_state["owner"]["epoch"]), "--ticket-id", TICKET_ID,
                "--candidate-id", candidate["id"], "--attempt-id", "RV-FINAL-G5",
                "--lease-id", "L-FINAL-G5", "--return-file", str(rejected_path),
                "--context-receipt", str(context_path), "--environment-receipt", str(environment_path),
                "--stop-confirmation", str(confirmation_path), "--reconciliation-id", "REC-G5-REJECT-01",
                "--authority-ref", "user-authorized-fixture",
            ]
            before_reconcile = case["paths"]["ledger"].read_bytes()
            wrong_epoch = reconcile.copy()
            wrong_epoch[wrong_epoch.index("--owner-epoch") + 1] = "99"
            run(*wrong_epoch, expect=2)
            self.assertEqual(before_reconcile, case["paths"]["ledger"].read_bytes())
            wrong_lease = reconcile.copy()
            wrong_lease[wrong_lease.index("--lease-id") + 1] = "L-OTHER"
            run(*wrong_lease, expect=2)
            self.assertEqual(before_reconcile, case["paths"]["ledger"].read_bytes())
            run(*reconcile)
            recovered, recovered_raw = ledger.load_state(case["paths"])
            old_attempt = ledger.attempt_by_id(recovered, "RV-FINAL-G5")
            self.assertEqual("INTERRUPTED", old_attempt["state"])
            self.assertEqual("released", old_attempt["lease"]["state"])
            self.assertIsNone(old_attempt["return_ref"])
            self.assertEqual("INTEGRATED", next(item for item in recovered["tickets"] if item["id"] == TICKET_ID)["state"])
            self.assertEqual("ACTIVE", recovered["lifecycle"]["control"])
            self.assertFalse(recovered["acceptance"])
            self.assertEqual(2, len([item for item in recovered["reviews"] if item.get("purpose") in ("ticket_review", "critical_axis") and item.get("verdict") == "PASS"]))
            self.assertTrue(json.loads(run(*reconcile).stdout)["idempotent"])
            self.assertEqual(recovered_raw, case["paths"]["ledger"].read_bytes())
            retry_packet = dict(packet)
            retry_packet["identity"] = dict(packet["identity"], attempt_id="RV-FINAL-G5-RETRY", source_revision=recovered["revision"])
            retry_path = case["root"] / "final-g5-retry-packet.json"
            write_json(retry_path, retry_packet)
            run(
                "register-final-g5", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(recovered["revision"]),
                "--owner-epoch", str(recovered["owner"]["epoch"]), "--ticket-id", TICKET_ID,
                "--candidate-id", candidate["id"], "--attempt-id", "RV-FINAL-G5-RETRY",
                "--lease-id", "L-FINAL-G5-RETRY", "--packet", str(retry_path),
            )
            retry_state, _ = ledger.load_state(case["paths"])
            self.assertEqual("PREPARED", ledger.attempt_by_id(retry_state, "RV-FINAL-G5-RETRY")["state"])
            self.assertFalse(retry_state["acceptance"])


if __name__ == "__main__":
    unittest.main()
