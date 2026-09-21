from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import ledger
from tests.test_phase_d_candidate_proof_v110 import (
    ATTEMPT_ID,
    OWNER,
    RUN_ID,
    PhaseDCandidateProofTests,
    run,
    write_json,
)


AMENDMENT_ID = "AM-stale-lease"
RECONCILIATION_ID = "REC-stale-lease"
LEASE_ID = "L-1"


class StaleLeaseRecoveryTests(unittest.TestCase):
    def prepare_amended_case(self, root: Path) -> dict[str, object]:
        helper = PhaseDCandidateProofTests()
        case = helper.prepare_done_candidate(root)
        run(*helper.candidate_args(case, receipt_path=case["receipt_path"]))
        paths = case["paths"]
        state, _ = ledger.load_state(paths)
        amended = root / "intent-v2.md"
        amended.write_text("# Intent v2\n\nAmended worker contract.\n", encoding="utf-8")
        run(
            "amend", "--control-root", str(case["control"]), "--run-id", RUN_ID,
            "--owner-token", OWNER, "--revision", str(state["revision"]),
            "--intent-file", str(amended), "--doc-id", "D-intent-v2", "--doc-version", "v2",
            "--intent-revision", "intent-v2", "--amendment-id", AMENDMENT_ID,
            "--authority-ref", "user-amendment",
        )
        amended_state, _ = ledger.load_state(paths)
        run(
            "gate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
            "--owner-token", OWNER, "--revision", str(amended_state["revision"]),
            "--phase", "DESIGN", "--control", "ACTIVE", "--reason", "amended_intent_g1_complete",
            "--next-action", "adopt_requirements", "--subject-refs", AMENDMENT_ID,
        )
        return case

    def recovery_args(self, case: dict[str, object], *, revision: int, **overrides: object) -> list[str]:
        values = {
            "owner_token": OWNER, "owner_epoch": 0, "attempt_id": ATTEMPT_ID,
            "lease_id": LEASE_ID, "amendment_id": AMENDMENT_ID,
            "reconciliation_id": RECONCILIATION_ID,
        }
        values.update(overrides)
        return [
            "reconcile-stale-lease", "--control-root", str(case["control"]), "--run-id", RUN_ID,
            "--owner-token", str(values["owner_token"]), "--revision", str(revision),
            "--owner-epoch", str(values["owner_epoch"]), "--attempt-id", str(values["attempt_id"]),
            "--lease-id", str(values["lease_id"]), "--amendment-id", str(values["amendment_id"]),
            "--reconciliation-id", str(values["reconciliation_id"]),
        ]

    def test_amendment_resume_releases_stopped_invalidated_lease_and_adopts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.prepare_amended_case(root)
            paths = case["paths"]
            before, _ = ledger.load_state(paths)
            routes_before = ledger.canonical_bytes(before.get("routes", []))
            evidence_before = ledger.canonical_bytes(before.get("evidence", []))
            objects_before = {path.name for path in paths["objects"].iterdir()}

            result = json.loads(run(*self.recovery_args(case, revision=before["revision"])).stdout)
            self.assertTrue(result["released"])
            self.assertFalse(result["idempotent"])
            after, after_raw = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(after, ATTEMPT_ID)
            self.assertEqual("released", attempt["lease"]["state"])
            self.assertEqual(routes_before, ledger.canonical_bytes(after.get("routes", [])))
            self.assertEqual(evidence_before, ledger.canonical_bytes(after.get("evidence", [])))
            self.assertEqual(before["revision"] + 1, after["revision"])
            self.assertEqual(1, len({path.name for path in paths["objects"].iterdir()} - objects_before))
            migration = next(
                item for item in after["runtime_provenance"]["applied_migrations"]
                if item["id"] == f"stale-lease-release-{RECONCILIATION_ID}"
            )
            report = ledger.stored_payload(paths, migration["object_ref"], "stale lease release report")
            self.assertEqual("stale_invalidated_lease_release", report["kind"])
            self.assertEqual(attempt["runtime"]["stop_ref"], report["stop_ref"])
            self.assertEqual(case["candidate_sha"], report["candidate_sha"])
            self.assertEqual(ledger.sha256_bytes(routes_before), report["route_records_hash"])
            self.assertEqual(ledger.sha256_bytes(evidence_before), report["evidence_records_hash"])

            replay = json.loads(run(*self.recovery_args(case, revision=before["revision"])).stdout)
            self.assertTrue(replay["idempotent"])
            self.assertEqual(after_raw, paths["ledger"].read_bytes())

            manifest = {
                "publication_id": "RP-amended", "version": "v2", "epoch": 0,
                "intent_revision": "intent-v2", "intent_document_ref": "D-intent-v2",
                "intent_document_hash": after["intent"]["document_hash"],
                "requirements": [{
                    "id": "R-amended", "version": "v2", "status": "active",
                    "provenance_refs": ["D-intent-v2"], "criterion_refs": ["C-amended"],
                }],
                "criteria": [{
                    "id": "C-amended", "version": "v2", "requirement_refs": ["R-amended"],
                    "oracle": "amended oracle", "status": "active", "source_ref": "D-intent-v2",
                }],
            }
            manifest_path = root / "requirements-v2.json"
            write_json(manifest_path, manifest)
            adopted = json.loads(run(
                "adopt-requirements", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(after["revision"]), "--manifest", str(manifest_path),
            ).stdout)
            self.assertEqual("RP-amended", adopted["publication_id"])

            docs = []
            for doc_id, kind in (
                ("D-design-v2", "design"), ("D-interfaces-v2", "interfaces"),
                ("D-manifest-v2", "manifest"), ("D-plan-v2", "plan"),
                ("D-tickets-v2", "tickets"), ("D-routes-v2", "routes"),
            ):
                source = root / f"{doc_id}.md"
                source.write_text(f"# {doc_id}\n", encoding="utf-8")
                docs.append({
                    "id": doc_id, "version": "v2", "kind": kind,
                    "source": str(source), "hash": ledger.sha256_file(source),
                })
            bundle = {
                "bundle_id": "B-amended", "version": "v2", "epoch": 0,
                "intent_revision": "intent-v2", "intent_document_ref": "D-intent-v2",
                "intent_document_hash": after["intent"]["document_hash"],
                "documents": docs,
                "contracts": [{
                    "id": "K-amended", "version": "v2", "status": "active",
                    "provenance_refs": ["D-interfaces-v2"],
                }],
                "tickets": [{
                    "id": "T-amended", "goal_ref": "G-amended", "criterion_refs": ["C-amended"],
                    "contract_refs": ["K-amended"], "dependency_refs": [], "state": "PLANNED",
                    "complexity": "bounded", "risk": "routine",
                    "zone": [{"path": "app.txt", "operations": ["modify"]}],
                }],
                "routes": [{
                    "id": "ROUTE-amended", "capability": "worker", "reasoning": "amended fixture",
                    "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED",
                }],
            }
            bundle_path = root / "bundle-v2.json"
            write_json(bundle_path, bundle)
            blocked = json.loads(run(
                "gate", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(adopted["revision"]),
                "--phase", "DESIGN", "--control", "BLOCKED", "--reason", "design_revision_required",
                "--next-action", "publish_design_bundle", "--subject-refs", AMENDMENT_ID,
            ).stdout)
            run(
                "publish-design-bundle", "--control-root", str(case["control"]), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(blocked["revision"]), "--bundle", str(bundle_path),
            )
            progressed, progressed_raw = ledger.load_state(paths)
            self.assertNotEqual(
                report["route_records_hash"], ledger.sha256_bytes(ledger.canonical_bytes(progressed["routes"])),
            )
            late_replay = json.loads(run(*self.recovery_args(case, revision=before["revision"])).stdout)
            self.assertTrue(late_replay["idempotent"])
            self.assertEqual(progressed_raw, paths["ledger"].read_bytes())

    def test_replay_rejects_conflicting_durable_provenance_without_mutation(self) -> None:
        for label, mutate in (
            (
                "migration hash",
                lambda state: next(
                    item for item in state["runtime_provenance"]["applied_migrations"]
                    if item["id"] == f"stale-lease-release-{RECONCILIATION_ID}"
                ).update({"manifest_hash": "0" * 64}),
            ),
            (
                "decision status",
                lambda state: next(
                    item for item in state["decisions"]
                    if item["id"] == f"decision-stale-lease-release-{RECONCILIATION_ID}"
                ).update({"status": "conflicting"}),
            ),
        ):
            with self.subTest(provenance=label), tempfile.TemporaryDirectory() as directory:
                case = self.prepare_amended_case(Path(directory))
                before, _ = ledger.load_state(case["paths"])
                run(*self.recovery_args(case, revision=before["revision"]))
                state, _ = ledger.load_state(case["paths"])
                mutate(state)
                raw = ledger.canonical_bytes(state)
                ledger.atomic_write(case["paths"]["ledger"], raw)
                run(*self.recovery_args(case, revision=before["revision"]), expect=2)
                self.assertEqual(raw, case["paths"]["ledger"].read_bytes())

    def test_wrong_fences_and_missing_proofs_fail_closed_without_mutation(self) -> None:
        cases = (
            ("wrong owner", {"owner_token": "owner-other"}),
            ("wrong epoch", {"owner_epoch": 1}),
            ("wrong attempt", {"attempt_id": "A-other"}),
            ("wrong lease", {"lease_id": "L-other"}),
            ("wrong amendment", {"amendment_id": "AM-other"}),
        )
        for label, overrides in cases:
            with self.subTest(fence=label), tempfile.TemporaryDirectory() as directory:
                case = self.prepare_amended_case(Path(directory))
                state, raw = ledger.load_state(case["paths"])
                run(*self.recovery_args(case, revision=state["revision"], **overrides), expect=2)
                self.assertEqual(raw, case["paths"]["ledger"].read_bytes())

        for label, mutate in (
            ("runtime not stopped", lambda state: state["attempts"][0]["runtime"].update({"liveness": "running"})),
            ("attempt not invalidated", lambda state: state["attempts"][0].update({"invalidated_by": []})),
        ):
            with self.subTest(proof=label), tempfile.TemporaryDirectory() as directory:
                case = self.prepare_amended_case(Path(directory))
                state, _ = ledger.load_state(case["paths"])
                mutate(state)
                raw = ledger.canonical_bytes(state)
                ledger.atomic_write(case["paths"]["ledger"], raw)
                run(*self.recovery_args(case, revision=state["revision"]), expect=2)
                self.assertEqual(raw, case["paths"]["ledger"].read_bytes())


if __name__ == "__main__":
    unittest.main()
