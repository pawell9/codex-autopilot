from __future__ import annotations

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

    def prepare_review(self, case: dict[str, Any], purpose: str, *, attempt_id: str | None = None) -> dict[str, Any]:
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
            "mandate": f"Independent {purpose} qualification for {candidate['id']}.",
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


if __name__ == "__main__":
    unittest.main()
