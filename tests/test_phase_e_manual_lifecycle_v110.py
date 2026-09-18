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
OWNER = "phase-e-owner"
RUN_ID = "phase-e-manual-run"
TICKET_ID = "T-MANUAL"
REVIEW_ATTEMPT_ID = "A-MANUAL"
CANDIDATE_SHA = "a" * 40
CANDIDATE_TREE_SHA = "b" * 40


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


class PhaseEManualLifecycleTests(unittest.TestCase):
    def init_case(self, root: Path, run_id: str = RUN_ID) -> dict[str, Any]:
        control, repo = root / "control", root / "repo"
        control.mkdir()
        repo.mkdir()
        (repo / "app.txt").write_text("candidate\n", encoding="utf-8")
        run(
            "init", "--control-root", str(control), "--repo-root", str(repo),
            "--run-id", run_id, "--owner-token", OWNER,
        )
        paths = ledger.paths(control, run_id)
        state, previous_raw = ledger.load_state(paths)

        intent_path = root / "intent.md"
        intent_path.write_text("# Intent\n\nPublish the verified candidate.\n", encoding="utf-8")
        intent_hash = ledger.sha256_file(intent_path)
        state["documents"] = [{
            "id": "D-INTENT", "version": "v1", "path": str(intent_path),
            "hash": intent_hash, "kind": "intent", "section_anchors": [],
        }]
        state["intent"] = {
            "current_revision": "v1", "document_ref": "D-INTENT",
            "document_hash": intent_hash, "approved_amendments": [],
            "acceptance_policy": "user_assisted", "checkpoint_policy": "gate",
            "prior_accepted_refs": [],
        }
        state["requirements"] = [{
            "id": "R-1", "version": "v1", "status": "active",
            "provenance_refs": ["D-INTENT"], "criterion_refs": ["C-1"],
            "decision_ref": None,
        }]
        state["criteria"] = [{
            "id": "C-1", "version": "v1", "requirement_refs": ["R-1"],
            "oracle": "app.txt contains candidate", "status": "active",
            "source_ref": "D-INTENT",
        }]

        worker_packet = {
            "identity": {"run_id": run_id, "ticket_id": TICKET_ID,
                         "attempt_id": "W-CANDIDATE", "epoch": 0},
            "kind": "worker", "mode": "implement", "goal": "fixture candidate",
        }
        worker_raw = ledger.canonical_bytes(worker_packet)
        worker_packet_hash = ledger.sha256_bytes(worker_raw)
        worker_ref = f"objects/{ledger.object_store(paths, worker_raw)}"
        worker_attempt = {
            "id": "W-CANDIDATE", "kind": "worker", "mode": "implement",
            "subject_ref": TICKET_ID, "packet_ref": worker_ref,
            "packet_hash": worker_packet_hash, "epoch": 0, "state": "RETURNED",
            "lease": {"id": "L-WORKER", "state": "released", "zone": []},
            "route_ref": None, "checkout": str(repo), "base_sha": None,
            "candidate_sha": CANDIDATE_SHA, "candidate_tree_sha": CANDIDATE_TREE_SHA,
            "return_ref": None, "finding_refs": [],
        }
        ticket = {
            "id": TICKET_ID, "goal_ref": "G-1", "criterion_refs": ["C-1"],
            "contract_refs": [], "dependency_refs": [], "state": "INTEGRATED",
            "verification_ref": "independent manual review", "complexity": "bounded",
            "risk": "critical", "zone": [{"path": "app.txt", "operations": ["modify"]}],
            "current_attempt": "W-CANDIDATE", "current_worker_attempt": None,
            "last_worker_attempt": "W-CANDIDATE", "current_candidate": "CANDIDATE-1",
            "replacement_refs": [],
        }
        state["tickets"] = [ticket]
        state["attempts"] = [worker_attempt]
        state["candidates"] = [{
            "id": "CANDIDATE-1", "ticket_ref": TICKET_ID, "sha": CANDIDATE_SHA,
            "tree_sha": CANDIDATE_TREE_SHA, "base_sha": None,
            "producer_attempt_ref": "W-CANDIDATE", "parent_candidate_ref": None,
            "quality": "DONE", "blocker_refs": [], "review_status": "PASS",
            "integration_status": "INTEGRATED", "proof_ref": None,
        }]

        initial_review_packet = self.packet(
            run_id, REVIEW_ATTEMPT_ID, "review", intent_hash, "ticket_review",
        )
        review_raw = ledger.canonical_bytes(initial_review_packet)
        review_hash = ledger.sha256_bytes(review_raw)
        review_ref = f"objects/{ledger.object_store(paths, review_raw)}"
        state["attempts"].append({
            "id": REVIEW_ATTEMPT_ID, "kind": "review", "mode": "change",
            "subject_ref": TICKET_ID, "packet_ref": review_ref,
            "packet_hash": review_hash, "epoch": 0, "state": "PREPARED",
            "lease": {"id": "L-REVIEW", "state": "active", "zone": []},
            "route_ref": None, "checkout": None, "base_sha": CANDIDATE_SHA,
            "candidate_sha": CANDIDATE_SHA, "candidate_tree_sha": CANDIDATE_TREE_SHA,
            "return_ref": None, "finding_refs": [],
            "subject_fingerprint": CANDIDATE_SHA,
            "intent_revision": "v1", "intent_document_ref": "D-INTENT",
            "intent_document_hash": intent_hash,
        })
        state["repository"].update({"checkout": str(repo), "branch": "main"})
        state["lifecycle"].update({
            "phase": "VERIFY", "control": "ACTIVE", "reason": "phase_e_fixture",
            "issue_refs": [], "next_action": {
                "kind": "prepare_final_g5", "subject_refs": [TICKET_ID],
                "preconditions": [], "read_refs": ["phases/accept.md"],
            },
        })
        state["revision"] = 1
        state["previous_publication_hash"] = ledger.sha256_bytes(previous_raw)
        ledger.validate_ledger(state)
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        return {
            "root": root, "control": control, "repo": repo, "paths": paths,
            "run_id": run_id, "intent_hash": intent_hash,
        }

    def packet(
        self, run_id: str, attempt_id: str, kind: str,
        intent_hash: str, purpose: str,
    ) -> dict[str, Any]:
        identity: dict[str, Any] = {"run_id": run_id, "attempt_id": attempt_id, "epoch": 0}
        if kind == "acceptance":
            identity.update({
                "intent_revision": "v1", "intent_document_ref": "D-INTENT",
                "intent_document_hash": intent_hash,
            })
            packet: dict[str, Any] = {
                "identity": identity, "kind": "acceptance", "purpose": purpose,
                "mandate": "Fresh independent final G5 for the frozen candidate.",
                "subject_fingerprint": CANDIDATE_SHA,
                "criteria": [{"id": "C-1", "requirement_id": "R-1",
                               "oracle": "app.txt content", "pass_condition": "candidate"}],
                "axes": ["current-intent", "independent-oracle"],
                "constraints": ["Use only the transferred bundle."],
                "subject": {
                    "candidate_sha": CANDIDATE_SHA,
                    "candidate_tree_sha": CANDIDATE_TREE_SHA,
                    "export_label": "candidate-export", "pristine_check_required": True,
                },
                "return_target": {"transport": "file", "path": "acceptance-return.json",
                                  "exact_json_only": True},
            }
            return packet
        identity.update({
            "ticket_id": TICKET_ID, "intent_revision": "v1",
            "intent_document_ref": "D-INTENT", "intent_document_hash": intent_hash,
        })
        axis = "critical-axis" if kind == "critical_axis" else "ticket-change"
        return {
            "identity": identity, "kind": "review", "purpose": purpose,
            "mandate": f"Independent {kind} review of the frozen candidate.",
            "subject_fingerprint": CANDIDATE_SHA,
            "criteria": [{"criterion_id": "C-1"}], "axes": [axis],
            "return_target": {"transport": "file", "path": "review-return.json"},
        }

    def prepare(
        self, case: dict[str, Any], purpose: str, *, kind: str | None = None,
        attempt_id: str = REVIEW_ATTEMPT_ID, packet_purpose: str | None = None,
        expect: int = 0,
    ) -> dict[str, Any]:
        kind = kind or ("acceptance" if purpose == "final_g5" else "review")
        packet_path = case["root"] / f"{attempt_id}-packet.json"
        projection_path = case["root"] / f"{attempt_id}-projection.json"
        export = case["root"] / f"{attempt_id}-export"
        bundle = case["root"] / f"{attempt_id}-bundle"
        export.mkdir()
        (export / "app.txt").write_text("candidate\n", encoding="utf-8")
        write_json(packet_path, self.packet(
            case["run_id"], attempt_id, kind, case["intent_hash"], packet_purpose or purpose,
        ))
        write_json(projection_path, {
            "kind": "acceptance_projection", "intent_revision": "v1",
            "intent_document_ref": "D-INTENT", "intent_document_hash": case["intent_hash"],
            "candidate_fingerprint": CANDIDATE_SHA, "goal": "Publish the verified candidate.",
            "criteria": [{"id": "C-1", "requirement_id": "R-1",
                          "oracle": "app.txt content", "pass_condition": "candidate"}],
            "exclusions": [], "return_schema": "review_return" if kind == "review" else "acceptance_return",
        })
        state, _ = ledger.load_state(case["paths"])
        result = run(
            "prepare-handoff", "--control-root", str(case["control"]),
            "--run-id", case["run_id"], "--owner-token", OWNER,
            "--revision", str(state["revision"]), "--attempt-id", attempt_id,
            "--purpose", purpose, "--packet", str(packet_path),
            "--projection", str(projection_path), "--export-root", str(export),
            "--bundle-root", str(bundle), expect=expect,
        )
        return {"packet": packet_path, "projection": projection_path,
                "export": export, "bundle": bundle, "result": result}

    def review_return(
        self, case: dict[str, Any], *, verdict: str = "PASS",
        attempt_id: str = REVIEW_ATTEMPT_ID, packet_hash: str,
        purpose: str = "critical_axis", finding: bool = False,
    ) -> dict[str, Any]:
        state, _ = ledger.load_state(case["paths"])
        attempt = next(item for item in state["attempts"] if item["id"] == attempt_id)
        packet = ledger.stored_payload(case["paths"], attempt["packet_ref"], "review packet")
        axis = packet["axes"][0]
        payload: dict[str, Any] = {
            "identity": {"run_id": case["run_id"], "ticket_id": TICKET_ID,
                         "attempt_id": attempt_id, "packet_hash": packet_hash,
                         "epoch": state["owner"]["epoch"], "intent_revision": "v1"},
            "subject_fingerprint": CANDIDATE_SHA, "verdict": verdict,
            "coverage": [{"criterion_id": "C-1", "outcome": "fulfilled" if verdict == "PASS" else "partial",
                          "evidence_refs": ["EV-COVERAGE"]}],
            "checks": [{"check_id": "manual-axis-check", "axis": axis,
                        "outcome": "fulfilled" if verdict == "PASS" else "failed",
                        "actual": "independent fixture observation", "evidence_ref": "EV-CHECK"}],
            "context_refs": ["CTX-MANUAL"], "findings": [],
        }
        if finding:
            payload["findings"] = [{
                "axis": axis, "impact": "blocking", "claim": "candidate violates the reviewed obligation",
                "expected": "the reviewed obligation is satisfied", "actual": "the observation failed",
                "evidence": "EV-FINDING confirms the failed observation", "affected_refs": [TICKET_ID],
            }]
        return payload

    def acceptance_return(
        self, case: dict[str, Any], *, verdict: str = "PASS",
        check_outcome: str | None = None, finding: bool = False,
        attempt_id: str = REVIEW_ATTEMPT_ID, packet_hash: str,
    ) -> dict[str, Any]:
        return {
            "identity": {"run_id": case["run_id"], "attempt_id": attempt_id,
                         "packet_hash": packet_hash, "epoch": 0,
                         "intent_revision": "v1", "intent_document_ref": "D-INTENT",
                         "intent_document_hash": case["intent_hash"]},
            "intent_revision": "v1", "candidate_fingerprint": CANDIDATE_SHA,
            "verdict": verdict,
            "outcomes": [{"criterion_id": "C-1",
                          "outcome": "fulfilled" if verdict == "PASS" else "partial",
                          "evidence_refs": ["EV-OUTCOME"]}],
            "checks": [{"check_id": "independent-oracle",
                        "outcome": check_outcome or ("fulfilled" if verdict == "PASS" else "failed"),
                        "actual": "app.txt matches candidate expectation",
                        "evidence_ref": "EV-G5-CHECK"}],
            "findings": ([{
                "axis": "independent-oracle", "impact": "blocking",
                "claim": "candidate fails a required observable criterion",
                "expected": "app.txt contains the accepted value", "actual": "observed value differs",
                "evidence": "EV-G5-FINDING records the observed mismatch",
                "affected_refs": [TICKET_ID],
            }] if finding else []),
        }

    def write_manual_evidence(
        self, case: dict[str, Any], prepared: dict[str, Any], *,
        return_payload: dict[str, Any], attempt_id: str = REVIEW_ATTEMPT_ID,
        reviewer_stopped: bool = True,
    ) -> dict[str, Path]:
        state, raw = ledger.load_state(case["paths"])
        attempt = next(item for item in state["attempts"] if item["id"] == attempt_id)
        bundle = prepared["bundle"]
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        manifest_hash = ledger.sha256_file(bundle / "manifest.json")
        inventory = [
            {"path": f"candidate-export/{item['path']}", "sha256": item["sha256"]}
            for item in manifest["files"]
        ]
        inventory.extend({
            "path": f"g5-bundle/{name}", "sha256": ledger.sha256_file(bundle / name),
        } for name in ("packet.json", "projection.json", "manifest.json", "operator-checklist.md"))
        environment_path = case["root"] / f"{attempt_id}-environment.json"
        context_path = case["root"] / f"{attempt_id}-context.json"
        integrity_path = case["root"] / f"{attempt_id}-integrity.json"
        return_path = case["paths"]["scratch"] / attempt_id / "manual-return.json"
        write_json(environment_path, {
            "receipt_id": f"ENV-{attempt_id}", "status": "PASS",
            "topology": {"surface": "isolated fixture export"},
            "inventory_hashes": inventory, "effective_grants": {"authoritative_repo": False},
            "boundary_probes": [{"probe": "authoritative-input", "result": "absent"}],
            "authoritative_absent": True,
        })
        write_json(context_path, {
            "receipt_id": f"CTX-{attempt_id}", "status": "PASS",
            "grade": "MANUAL_ATTESTED_CLEAN", "packet_hash": attempt["packet_hash"],
            "export_hash": manifest_hash, "clean_input": True,
            "contamination_absent": True, "reviewer_stopped": reviewer_stopped,
            "session_provenance": {"session": "fresh independent fixture session"},
        })
        write_json(integrity_path, {
            "status": "PASS", "candidate_fingerprint": CANDIDATE_SHA,
            "candidate_sha": CANDIDATE_SHA, "ledger_hash": ledger.sha256_bytes(raw),
            "reviewer_stopped": reviewer_stopped,
        })
        write_json(return_path, return_payload)
        return {"environment": environment_path, "context": context_path,
                "integrity": integrity_path, "return": return_path}

    def test_handoff_purpose_is_explicit_and_does_not_retype_packet(self) -> None:
        for purpose, kind in (("ticket_review", "review"),
                              ("critical_axis", "review"), ("final_g5", "acceptance")):
            with self.subTest(purpose=purpose), tempfile.TemporaryDirectory() as directory:
                case = self.init_case(Path(directory), f"{RUN_ID}-{purpose}")
                prepared = self.prepare(case, purpose, kind=kind)
                state, _ = ledger.load_state(case["paths"])
                attempt = next(item for item in state["attempts"] if item["id"] == REVIEW_ATTEMPT_ID)
                stored_packet = ledger.stored_payload(case["paths"], attempt["packet_ref"], "prepared packet")
                payload = (
                    self.acceptance_return(case, packet_hash=attempt["packet_hash"])
                    if kind == "acceptance"
                    else self.review_return(case, purpose=purpose, packet_hash=attempt["packet_hash"])
                )
                evidence = self.write_manual_evidence(case, prepared, return_payload=payload)
                imported = invoke(
                    "import-manual", "--control-root", str(case["control"]),
                    "--run-id", case["run_id"], "--owner-token", OWNER,
                    "--revision", str(state["revision"]), "--attempt-id", REVIEW_ATTEMPT_ID,
                    "--purpose", purpose, "--return-file", str(evidence["return"]),
                    "--environment-receipt", str(evidence["environment"]),
                    "--context-receipt", str(evidence["context"]),
                    "--integrity-receipt", str(evidence["integrity"]),
                    "--intent-revision", "v1", "--candidate-fingerprint", CANDIDATE_SHA,
                    "--required-criteria", "C-1",
                )
                self.assertEqual(0, imported.returncode, imported.stdout + imported.stderr)
                after, _ = ledger.load_state(case["paths"])
                final_attempt = next(item for item in after["attempts"] if item["id"] == REVIEW_ATTEMPT_ID)
                self.assertEqual(purpose, final_attempt["handoff"].get("purpose"))
                self.assertEqual(kind, stored_packet["kind"])
                self.assertEqual(purpose, stored_packet["purpose"])
                self.assertEqual("review", final_attempt["kind"], "purpose must not rewrite the registered attempt role")
                self.assertEqual("user_assisted", final_attempt["handoff"].get("transport"))
                self.assertTrue(prepared["bundle"].joinpath("manifest.json").is_file())
                if purpose == "final_g5":
                    self.assertEqual(1, len(after["acceptance"]))
                    self.assertEqual("ACCEPT", after["lifecycle"]["phase"])
                else:
                    self.assertEqual([], after["acceptance"])
                    self.assertNotEqual("ACCEPT", after["lifecycle"]["phase"])
                    qualifications = [
                        item for item in after["review_qualifications"]
                        if item["subject_fingerprint"] == CANDIDATE_SHA
                    ]
                    self.assertEqual(1, len(qualifications))
                    self.assertEqual([purpose], qualifications[0]["satisfied_purposes"])

    def test_declared_purpose_and_packet_type_must_agree_before_publication(self) -> None:
        cases = (("final_g5", "review", None), ("ticket_review", "acceptance", None),
                 ("ticket_review", "review", "critical_axis"))
        for purpose, kind, packet_purpose in cases:
            with self.subTest(purpose=purpose, kind=kind, packet_purpose=packet_purpose), tempfile.TemporaryDirectory() as directory:
                case = self.init_case(Path(directory))
                raw_before = case["paths"]["ledger"].read_bytes()
                self.prepare(case, purpose, kind=kind, packet_purpose=packet_purpose, expect=2)
                self.assertEqual(raw_before, case["paths"]["ledger"].read_bytes())

    def test_import_purpose_must_match_prepared_packet_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.init_case(Path(directory))
            prepared = self.prepare(case, "final_g5")
            state, _ = ledger.load_state(case["paths"])
            attempt = next(item for item in state["attempts"] if item["id"] == REVIEW_ATTEMPT_ID)
            payload = self.acceptance_return(case, packet_hash=attempt["packet_hash"])
            evidence = self.write_manual_evidence(case, prepared, return_payload=payload)
            raw_before = case["paths"]["ledger"].read_bytes()
            result = invoke(
                "import-manual", "--control-root", str(case["control"]),
                "--run-id", case["run_id"], "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", REVIEW_ATTEMPT_ID,
                "--purpose", "critical_axis", "--return-file", str(evidence["return"]),
                "--environment-receipt", str(evidence["environment"]),
                "--context-receipt", str(evidence["context"]),
                "--integrity-receipt", str(evidence["integrity"]),
                "--intent-revision", "v1", "--candidate-fingerprint", CANDIDATE_SHA,
                "--required-criteria", "C-1",
            )
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertRegex(result.stderr.lower(), r"purpose|packet|kind|acceptance")
            self.assertEqual(raw_before, case["paths"]["ledger"].read_bytes())

    def test_manual_pass_with_a_failed_check_is_rejected_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.init_case(Path(directory))
            prepared = self.prepare(case, "final_g5")
            state, _ = ledger.load_state(case["paths"])
            attempt = next(item for item in state["attempts"] if item["id"] == REVIEW_ATTEMPT_ID)
            payload = self.acceptance_return(
                case, verdict="PASS", check_outcome="failed", packet_hash=attempt["packet_hash"],
            )
            evidence = self.write_manual_evidence(case, prepared, return_payload=payload)
            raw_before = case["paths"]["ledger"].read_bytes()
            result = invoke(
                "import-manual", "--control-root", str(case["control"]),
                "--run-id", case["run_id"], "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", REVIEW_ATTEMPT_ID,
                "--purpose", "final_g5", "--return-file", str(evidence["return"]),
                "--environment-receipt", str(evidence["environment"]),
                "--context-receipt", str(evidence["context"]),
                "--integrity-receipt", str(evidence["integrity"]),
                "--intent-revision", "v1", "--candidate-fingerprint", CANDIDATE_SHA,
                "--required-criteria", "C-1",
            )
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertRegex(result.stderr.lower(), r"check|pass|outcome|semantic")
            self.assertEqual(raw_before, case["paths"]["ledger"].read_bytes())

    def test_interrupted_manual_attempt_cannot_be_imported_as_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.init_case(Path(directory))
            prepared = self.prepare(case, "final_g5")
            state, _ = ledger.load_state(case["paths"])
            attempt = next(item for item in state["attempts"] if item["id"] == REVIEW_ATTEMPT_ID)
            termination = case["root"] / "termination.json"
            write_json(termination, {"status": "PASS", "writer_stopped": True})
            run(
                "terminate-attempt", "--control-root", str(case["control"]),
                "--run-id", case["run_id"], "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", REVIEW_ATTEMPT_ID,
                "--state", "INTERRUPTED", "--lease-state", "released",
                "--evidence", str(termination),
            )
            # Receipts bind to the post-interruption ledger so rejection is about
            # attempt authority, not a stale integrity hash.
            interrupted, _ = ledger.load_state(case["paths"])
            payload = self.acceptance_return(case, packet_hash=attempt["packet_hash"])
            evidence = self.write_manual_evidence(case, prepared, return_payload=payload)
            integrity = json.loads(evidence["integrity"].read_text(encoding="utf-8"))
            integrity["ledger_hash"] = ledger.sha256_file(case["paths"]["ledger"])
            write_json(evidence["integrity"], integrity)
            raw_before = case["paths"]["ledger"].read_bytes()
            result = invoke(
                "import-manual", "--control-root", str(case["control"]),
                "--run-id", case["run_id"], "--owner-token", OWNER,
                "--revision", str(interrupted["revision"]), "--attempt-id", REVIEW_ATTEMPT_ID,
                "--purpose", "final_g5", "--return-file", str(evidence["return"]),
                "--environment-receipt", str(evidence["environment"]),
                "--context-receipt", str(evidence["context"]),
                "--integrity-receipt", str(evidence["integrity"]),
                "--intent-revision", "v1", "--candidate-fingerprint", CANDIDATE_SHA,
                "--required-criteria", "C-1",
            )
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            after, _ = ledger.load_state(case["paths"])
            self.assertEqual("INTERRUPTED", next(item for item in after["attempts"] if item["id"] == REVIEW_ATTEMPT_ID)["state"])
            self.assertEqual([], after["acceptance"])
            self.assertEqual(raw_before, case["paths"]["ledger"].read_bytes())

    def test_critical_axis_pass_does_not_satisfy_final_g5_or_enter_accept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.init_case(Path(directory))
            prepared = self.prepare(case, "critical_axis", kind="review")
            state, _ = ledger.load_state(case["paths"])
            attempt = next(item for item in state["attempts"] if item["id"] == REVIEW_ATTEMPT_ID)
            payload = self.review_return(case, packet_hash=attempt["packet_hash"])
            evidence = self.write_manual_evidence(case, prepared, return_payload=payload)
            result = invoke(
                "import-manual", "--control-root", str(case["control"]),
                "--run-id", case["run_id"], "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", REVIEW_ATTEMPT_ID,
                "--purpose", "critical_axis", "--return-file", str(evidence["return"]),
                "--environment-receipt", str(evidence["environment"]),
                "--context-receipt", str(evidence["context"]),
                "--integrity-receipt", str(evidence["integrity"]),
                "--intent-revision", "v1", "--candidate-fingerprint", CANDIDATE_SHA,
                "--required-criteria", "C-1",
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            after, _ = ledger.load_state(case["paths"])
            self.assertNotEqual("ACCEPT", after["lifecycle"]["phase"])
            self.assertNotEqual("g6_final_record", after["lifecycle"]["next_action"]["kind"])
            self.assertEqual([], after["acceptance"], "critical-axis PASS must not be recorded as final G5")
            qualification = next(
                item for item in after["review_qualifications"]
                if item["subject_fingerprint"] == CANDIDATE_SHA
            )
            self.assertEqual(["critical_axis"], qualification["satisfied_purposes"])
            self.assertEqual("INCOMPLETE", qualification["result"])

    def test_final_g5_block_creates_repairable_finding_and_rejects_g6_without_fresh_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            case = self.init_case(Path(directory))
            prepared = self.prepare(case, "final_g5")
            state, _ = ledger.load_state(case["paths"])
            attempt = next(item for item in state["attempts"] if item["id"] == REVIEW_ATTEMPT_ID)
            payload = self.acceptance_return(
                case, verdict="BLOCK", finding=True, packet_hash=attempt["packet_hash"],
            )
            evidence = self.write_manual_evidence(case, prepared, return_payload=payload)
            result = invoke(
                "import-manual", "--control-root", str(case["control"]),
                "--run-id", case["run_id"], "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", REVIEW_ATTEMPT_ID,
                "--purpose", "final_g5", "--return-file", str(evidence["return"]),
                "--environment-receipt", str(evidence["environment"]),
                "--context-receipt", str(evidence["context"]),
                "--integrity-receipt", str(evidence["integrity"]),
                "--intent-revision", "v1", "--candidate-fingerprint", CANDIDATE_SHA,
                "--required-criteria", "C-1",
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            after, _ = ledger.load_state(case["paths"])
            self.assertEqual("BLOCKED", after["lifecycle"]["control"])
            self.assertEqual("VERIFY", after["lifecycle"]["phase"])
            self.assertEqual("authorize_repair", after["lifecycle"]["next_action"]["kind"])
            self.assertIn(TICKET_ID, after["lifecycle"]["next_action"]["subject_refs"])
            self.assertEqual(1, len(after["findings"]))
            finding = after["findings"][0]
            self.assertEqual("blocking", finding["impact"])
            self.assertIn(TICKET_ID, finding["affected_refs"])
            obligation = next(
                item for item in ledger.finding_obligation_projection(after)["items"]
                if item["finding_ref"] == finding["id"]
            )
            self.assertTrue(obligation["repairable"])
            self.assertIn(finding["id"], after["lifecycle"]["next_action"]["subject_refs"])
            self.assertEqual("final_g5", after["acceptance"][-1]["purpose"])
            self.assertIn(
                finding["id"],
                after["acceptance"][-1].get("finding_refs", [])
                + after["acceptance"][-1].get("outcome_refs", []),
            )
            wave = next(item for item in after["repair_waves"] if finding["id"] in item["finding_refs"])
            self.assertEqual("OPEN", wave["state"])
            self.assertEqual(CANDIDATE_SHA, wave["source_candidate_fingerprint"])
            self.assertIsNone(wave["final_g5_qualification_ref"])
            current, _ = ledger.load_state(case["paths"])
            gate = invoke(
                "gate", "--control-root", str(case["control"]), "--run-id", case["run_id"],
                "--owner-token", OWNER, "--revision", str(current["revision"]),
                "--phase", "ACCEPT", "--control", "ACCEPTED", "--gate-id", "G6",
                "--next-action", "terminal",
            )
            self.assertEqual(2, gate.returncode, gate.stdout + gate.stderr)
            still_blocked, _ = ledger.load_state(case["paths"])
            self.assertEqual("BLOCKED", still_blocked["lifecycle"]["control"])
            self.assertEqual("BLOCK", still_blocked["acceptance"][-1]["verdict"])


if __name__ == "__main__":
    unittest.main()
