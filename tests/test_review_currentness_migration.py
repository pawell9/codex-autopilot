import copy
import json
import tempfile
import unittest
import uuid
from argparse import Namespace
from pathlib import Path
from unittest import mock

from tools import dashboard, ledger


RUN_ID = "2026-09-16-idea-scout-v2"
CURRENT_BUNDLE = "idea-scout-v2-design-bundle-v12"
CURRENT_FINGERPRINT = "cbbae2bf9b299676e84e8f64d804a85324e79ae868b6f59995cf652a3c06156d"
G2_PACKET = "70cda78f666af125b4d6d03a05d1abee9f00a6a9df13e707cf9af9fe5a1ae96d"
G3_PACKET = "4aa0e1ea47384db2d3081bc1f570c6ec2c3357d19140888f360e5750f9edd453"
ISSUE_IDS = [
    "issue-00357bc2064d7576", "issue-079a50ffa1ff8af1", "issue-aa24736884c6cb46",
    "issue-39030810d1c29b4f", "issue-9bb610382069e3f7", "issue-4bf9643503ff9e86",
    "issue-575c59d2d3063537", "issue-51ab1eb488bf2cd9", "issue-1a1984f6615f573e",
    "issue-7fce97c3775b7edc", "issue-e4596775fb8fe478", "issue-6e708f1994d1ed2f",
    "issue-9e0b50b2aa28d696",
]


def publication(publication_id, fingerprint, revision, document_ref, *, status, superseded_by=None):
    value = {
        "id": publication_id, "version": "v1", "status": status, "owner_epoch": 0,
        "intent_revision": "intent-v12", "intent_document_ref": "D-intent", "intent_document_hash": "",
        "publication_hash": fingerprint, "bundle_ref": f"objects/{fingerprint}", "published_revision": revision,
        "document_refs": [document_ref], "requirement_refs": [], "criterion_refs": [],
        "requirements_publication_ref": None, "contract_refs": [], "ticket_refs": [], "route_refs": [],
        "invalidated_by": [], "supersedes": [], "superseded_by": superseded_by, "consumer_refs": [],
    }
    if superseded_by:
        value["invalidated_by"] = [superseded_by]
    return value


def review_attempt(attempt_id, mode, publication_id, fingerprint, revision, return_hash, packet_hash, result):
    return {
        "id": attempt_id, "kind": "review", "mode": mode, "subject_ref": publication_id,
        "packet_ref": f"objects/{packet_hash}", "packet_hash": packet_hash, "epoch": 0,
        "state": "RETURNED", "lease": {"id": f"lease-{attempt_id}", "state": "released", "zone": []},
        "return_ref": f"objects/{return_hash}", "finding_refs": [], "reviewer_identity": "sanitized-reviewer",
        "reviewer_role": f"{mode}-reviewer", "subject_fingerprint": fingerprint,
        "target_artifact_refs": [], "target_artifact_versions": [], "target_revision": revision,
        "packet_registration_revision": revision, "packet_source_revision": revision,
        "subject_revision": revision, "attempt_created_revision": revision + 1,
        "return_source_revision": revision, "review_result": result,
        "intent_revision": "intent-v12", "intent_document_ref": "D-intent", "intent_document_hash": "",
        "invalidated_by": [],
    }


def review(review_id, mode, fingerprint, revision, return_hash, verdict, finding_refs=None):
    return {
        "id": review_id, "mandate": f"design {mode}", "subject_fingerprint": fingerprint,
        "verdict": verdict, "return_ref": f"objects/{return_hash}", "context_refs": ["sanitized"],
        "finding_refs": finding_refs or [], "intent_revision": "intent-v12",
        "reviewer_identity": "sanitized-reviewer", "reviewer_role": f"{mode}-reviewer",
        "review_kind": mode, "target_artifact_refs": [], "target_artifact_versions": [],
        "target_revision": revision, "invalidated_by": [],
    }


class ReviewCurrentnessMigrationTests(unittest.TestCase):
    def make_fixture(self, directory):
        root = Path(directory)
        control = root / "control"
        repo = root / "repo"
        control.mkdir(); repo.mkdir()
        owner_token = uuid.uuid4().hex  # ephemeral; no production owner token is stored in the fixture.
        state = ledger.base_state(control, RUN_ID, repo, owner_token)
        paths = ledger.paths(control, RUN_ID)
        paths["run"].mkdir(parents=True)
        paths["objects"].mkdir()
        paths["docs"].mkdir()

        intent_path = paths["docs"] / "intent.md"
        design_old_path = paths["docs"] / "design-old.md"
        design_current_path = paths["docs"] / "design-current.md"
        intent_path.write_text("# Sanitized intent\n", encoding="utf-8")
        design_old_path.write_text("# Sanitized old design\n", encoding="utf-8")
        design_current_path.write_text("# Sanitized current design\n", encoding="utf-8")
        intent_hash = ledger.sha256_file(intent_path)
        state["documents"] = [
            {"id": "D-intent", "kind": "intent", "path": str(intent_path), "version": "v12", "hash": intent_hash},
            {"id": "D-design", "kind": "design", "path": str(design_old_path), "version": "legacy", "hash": ledger.sha256_file(design_old_path)},
            {"id": "D-design-v12", "kind": "design", "path": str(design_current_path), "version": "v12", "hash": ledger.sha256_file(design_current_path)},
        ]
        state["intent"] = {"current_revision": "intent-v12", "document_ref": "D-intent", "document_hash": intent_hash, "approved_amendments": []}

        old_raw = ledger.canonical_bytes({"fixture": "sanitized-old-publication"})
        old_fingerprint = ledger.sha256_bytes(old_raw)
        (paths["objects"] / old_fingerprint).write_bytes(old_raw)
        (paths["objects"] / CURRENT_FINGERPRINT).write_bytes(b"sanitized current publication placeholder\n")
        old = publication("idea-scout-v2-design-bundle-v1", old_fingerprint, 10, "D-design", status="SUPERSEDED", superseded_by=CURRENT_BUNDLE)
        current = publication(CURRENT_BUNDLE, CURRENT_FINGERPRINT, 71, "D-design-v12", status="PUBLISHED")
        for item in (old, current):
            item["intent_document_hash"] = intent_hash
        state["design_publication_history"] = [old, current]
        state["design_publication"] = copy.deepcopy(current)

        old_return_g2 = "1" * 64
        old_return_g3 = "2" * 64
        current_return_g2 = "3" * 64
        current_return_g3 = "4" * 64
        attempts = [
            review_attempt("G2-COVERAGE-01", "coverage", old["id"], old_fingerprint, 10, old_return_g2, "5" * 64, "BLOCK"),
            review_attempt("G3-PLAN-01", "plan", old["id"], old_fingerprint, 10, old_return_g3, "6" * 64, "BLOCK"),
            review_attempt("G2-COVERAGE-V12-01", "coverage", CURRENT_BUNDLE, CURRENT_FINGERPRINT, 71, current_return_g2, G2_PACKET, "PASS"),
            review_attempt("G3-PLAN-V12-01", "plan", CURRENT_BUNDLE, CURRENT_FINGERPRINT, 71, current_return_g3, G3_PACKET, "PASS"),
        ]
        for attempt in attempts:
            attempt["intent_document_hash"] = intent_hash
        findings = []
        issues = []
        g2_findings = []
        g3_findings = []
        for index, issue_id in enumerate(ISSUE_IDS):
            source = "G2-COVERAGE-01" if index < 7 else "G3-PLAN-01"
            finding_id = f"finding-legacy-{index + 1:02d}"
            (g2_findings if index < 7 else g3_findings).append(finding_id)
            findings.append({
                "id": finding_id, "axis": "coverage" if index < 7 else "plan", "impact": "blocking",
                "claim": f"historical finding {index + 1}", "expected": "legacy expected", "actual": "legacy actual",
                "evidence": "immutable sanitized evidence", "affected_refs": ["D-design"],
                "reported_affected_refs": ["D-design"], "source_ref": source,
                "intent_revision": "intent-v12", "repair_contract_ref": None, "invalidated_by": [],
            })
            issues.append({
                "id": issue_id, "type": "review_finding", "cause": "unknown", "impact": "blocking",
                "affected_refs": ["D-design"], "expected": "legacy expected", "actual": "legacy actual",
                "disposition": "requires repair or adjudication", "resolution_condition": "finding independently resolved",
                "owner": None, "failure_signature": None, "finding_ref": finding_id, "source_ref": source,
                "intent_revision": "intent-v12", "invalidated_by": [],
            })
        attempts[0]["finding_refs"] = g2_findings
        attempts[1]["finding_refs"] = g3_findings
        state["attempts"] = attempts
        state["findings"] = findings
        state["issues"] = issues
        state["reviews"] = [
            review("REV-old-g2", "coverage", old_fingerprint, 10, old_return_g2, "BLOCK", g2_findings),
            review("REV-old-g3", "plan", old_fingerprint, 10, old_return_g3, "BLOCK", g3_findings),
            review("REV-be0f15b82a7f27ca", "coverage", CURRENT_FINGERPRINT, 71, current_return_g2, "PASS"),
            review("REV-659d40df3d07d4e1", "plan", CURRENT_FINGERPRINT, 71, current_return_g3, "PASS"),
        ]
        state["evidence"] = [
            {"id": "EV-old-g2", "hash": old_return_g2, "source": "validated_return", "scenario": "review", "outcome": "RETURNED", "observer": "ledger-helper", "subject": "G2-COVERAGE-01", "invalidated_by": []},
            {"id": "EV-old-g3", "hash": old_return_g3, "source": "validated_return", "scenario": "review", "outcome": "RETURNED", "observer": "ledger-helper", "subject": "G3-PLAN-01", "invalidated_by": []},
        ]
        state["revision"] = 77
        state["lifecycle"] = {
            "phase": "DESIGN", "control": "BLOCKED", "reason": "a current blocking issue prevents G2/G3 advancement",
            "issue_refs": list(ISSUE_IDS), "stop_target": None,
            "next_action": {"kind": "migrate-review-currentness", "subject_refs": list(ISSUE_IDS), "preconditions": [], "read_refs": ["references/ledger.md"]},
        }
        ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
        return control, owner_token, paths, old_fingerprint

    def hash_patch(self, paths):
        original = ledger.sha256_file

        def selective(path):
            candidate = Path(path)
            if candidate.name == CURRENT_FINGERPRINT:
                return CURRENT_FINGERPRINT
            return original(candidate)

        return mock.patch("tools.ledger.sha256_file", side_effect=selective)

    @staticmethod
    def args(control, owner_token, revision):
        return Namespace(control_root=str(control), run_id=RUN_ID, owner_token=owner_token, revision=revision)

    @staticmethod
    def immutable_payload(record):
        return {key: copy.deepcopy(value) for key, value in record.items() if key != "invalidated_by"}

    def test_exact_revision_77_fixture_migrates_and_second_run_is_zero_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            control, token, paths, _ = self.make_fixture(directory)
            with self.hash_patch(paths):
                before, _ = ledger.load_state(paths)
                self.assertEqual(77, before["revision"])
                self.assertEqual(("DESIGN", "BLOCKED"), (before["lifecycle"]["phase"], before["lifecycle"]["control"]))
                current_attempts = {item["id"]: item for item in before["attempts"][-2:]}
                self.assertEqual(G2_PACKET, current_attempts["G2-COVERAGE-V12-01"]["packet_hash"])
                self.assertEqual(G3_PACKET, current_attempts["G3-PLAN-V12-01"]["packet_hash"])
                self.assertTrue(all(item["state"] == "RETURNED" and item["lease"]["state"] == "released" and item["subject_revision"] == 71 for item in current_attempts.values()))
                self.assertEqual({"G2-COVERAGE-01", "G3-PLAN-01"}, {item["source_ref"] for item in before["issues"]})
                self.assertEqual({"D-design"}, {ref for item in before["findings"] for ref in item["affected_refs"]})
                historical_before = {
                    collection: {item["id"]: self.immutable_payload(item) for item in before.get(collection, [])}
                    for collection in ("issues", "findings", "attempts", "reviews", "evidence")
                }
                first = ledger.cmd_migrate_review_currentness(self.args(control, token, 77))
                self.assertFalse(first["idempotent"])
                self.assertEqual(78, first["revision"])
                self.assertEqual(13, sum(item["action"] == "invalidated_as_historical" for item in first["report"]["outcomes"]))

                migrated, migrated_raw = ledger.load_state(paths)
                self.assertEqual(("DESIGN", "ACTIVE"), (migrated["lifecycle"]["phase"], migrated["lifecycle"]["control"]))
                self.assertEqual([], [item["id"] for item in migrated["issues"] if item["impact"] == "blocking" and not item.get("invalidated_by")])
                self.assertEqual(13, len(migrated["issues"]))
                self.assertEqual(13, len(migrated["findings"]))
                self.assertEqual(CURRENT_FINGERPRINT, migrated["design_publication"]["publication_hash"])
                self.assertEqual({"REV-be0f15b82a7f27ca", "REV-659d40df3d07d4e1"}, {item["id"] for item in migrated["reviews"] if not item.get("invalidated_by")})
                for collection, records in historical_before.items():
                    after = {item["id"]: self.immutable_payload(item) for item in migrated.get(collection, [])}
                    self.assertEqual(records, after)

                second = ledger.cmd_migrate_review_currentness(self.args(control, token, 78))
                self.assertTrue(second["idempotent"])
                after_second, after_second_raw = ledger.load_state(paths)
                self.assertEqual(78, after_second["revision"])
                self.assertEqual(migrated_raw, after_second_raw)

                status = ledger.cmd_status(Namespace(control_root=str(control), run_id=RUN_ID, brief=False))
                brief = ledger.cmd_status(Namespace(control_root=str(control), run_id=RUN_ID, brief=True))
                projection = dashboard.project_ledger(copy.deepcopy(after_second), paths["ledger"], after_second_raw)
                self.assertEqual([], status["blockers"])
                self.assertEqual({"current": 0, "historical": 13, "total": 13}, status["finding_counts"])
                self.assertEqual([], brief["issues"])
                self.assertTrue(all(not item["current"] for item in brief["finding_status"]))
                self.assertEqual([], projection["blockers"])
                self.assertTrue(all(not item["current"] for item in projection["findings"]))

                g2 = ledger.cmd_gate(Namespace(control_root=str(control), run_id=RUN_ID, owner_token=token, revision=78, phase="DESIGN", control="ACTIVE", gate_id="G2", reason=None, next_action="g2_pass", subject_refs="", preconditions="", read_refs=""))
                self.assertEqual(79, g2["revision"])
                g3 = ledger.cmd_gate(Namespace(control_root=str(control), run_id=RUN_ID, owner_token=token, revision=79, phase="PLAN", control="ACTIVE", gate_id="G3", reason=None, next_action="g3_pass", subject_refs="", preconditions="", read_refs=""))
                self.assertEqual("PLAN", g3["phase"])

    def test_current_missing_and_ambiguous_lineage_remain_blockers(self):
        with tempfile.TemporaryDirectory() as directory:
            control, token, paths, old_fingerprint = self.make_fixture(directory)
            with self.hash_patch(paths):
                state, _ = ledger.load_state(paths)
                ambiguous_a = publication("legacy-ambiguous-a", old_fingerprint, 9, "D-design", status="SUPERSEDED", superseded_by=CURRENT_BUNDLE)
                ambiguous_b = publication("legacy-ambiguous-b", old_fingerprint, 9, "D-design", status="SUPERSEDED", superseded_by=CURRENT_BUNDLE)
                for item in (ambiguous_a, ambiguous_b):
                    item["intent_document_hash"] = state["intent"]["document_hash"]
                state["design_publication_history"][-1:-1] = [ambiguous_a, ambiguous_b]
                state["reviews"].append(review("REV-ambiguous", "coverage", old_fingerprint, 9, "7" * 64, "BLOCK"))
                extras = [
                    ("issue-current", "finding-current", "G2-COVERAGE-V12-01"),
                    ("issue-missing", "finding-missing", "G2-COVERAGE-V11-99"),
                    ("issue-ambiguous", "finding-ambiguous", "REV-ambiguous"),
                ]
                for issue_id, finding_id, source in extras:
                    state["findings"].append({"id": finding_id, "axis": "coverage", "impact": "blocking", "claim": "negative fixture", "expected": "expected", "actual": "actual", "evidence": "sanitized", "affected_refs": ["D-design"], "reported_affected_refs": ["D-design"], "source_ref": source, "intent_revision": "intent-v12", "repair_contract_ref": None, "invalidated_by": []})
                    state["issues"].append({"id": issue_id, "type": "review_finding", "cause": "unknown", "impact": "blocking", "affected_refs": ["D-design"], "expected": "expected", "actual": "actual", "disposition": "requires review", "resolution_condition": "proof", "owner": None, "failure_signature": None, "finding_ref": finding_id, "source_ref": source, "intent_revision": "intent-v12", "invalidated_by": []})
                    state["lifecycle"]["issue_refs"].append(issue_id)
                ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))

                result = ledger.cmd_migrate_review_currentness(self.args(control, token, 77))
                outcomes = {item["issue_id"]: item for item in result["report"]["outcomes"]}
                self.assertEqual("current", outcomes["issue-current"]["status"])
                self.assertEqual("unresolved", outcomes["issue-missing"]["status"])
                self.assertIn("does not resolve", outcomes["issue-missing"]["reason"])
                self.assertEqual("ambiguous", outcomes["issue-ambiguous"]["status"])
                final, _ = ledger.load_state(paths)
                blockers = {item["id"] for item in final["issues"] if item["impact"] == "blocking" and not item.get("invalidated_by")}
                self.assertEqual({"issue-current", "issue-missing", "issue-ambiguous"}, blockers)
                rejected = Namespace(control_root=str(control), run_id=RUN_ID, owner_token=token, revision=78, phase="PLAN", control="ACTIVE", gate_id="G3", reason=None, next_action="g3_pass", subject_refs="", preconditions="", read_refs="")
                with self.assertRaisesRegex(ledger.LedgerError, "current blocking issue|BLOCKED -> ACTIVE requires no active blocking issues or unresolved finding obligations"):
                    ledger.cmd_gate(rejected)

    def test_non_current_pass_cannot_authorize_migration_or_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            control, token, paths, old_fingerprint = self.make_fixture(directory)
            with self.hash_patch(paths):
                state, _ = ledger.load_state(paths)
                for attempt in state["attempts"][-2:]:
                    attempt["subject_fingerprint"] = old_fingerprint
                    attempt["subject_ref"] = state["design_publication_history"][0]["id"]
                    attempt["subject_revision"] = 10
                    attempt["target_revision"] = 10
                for item in state["reviews"][-2:]:
                    item["subject_fingerprint"] = old_fingerprint
                    item["target_revision"] = 10
                ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
                with self.assertRaisesRegex(ledger.LedgerError, "fresh registered and ingested current PASS"):
                    ledger.cmd_migrate_review_currentness(self.args(control, token, 77))
                # A BLOCKED run cannot attempt any active gate transition until
                # its durable blockers are cleared; this shared transition guard
                # is an equally safe earlier fence than stale PASS diagnostics.
                with self.assertRaisesRegex(ledger.LedgerError, "PASS coverage review|BLOCKED -> ACTIVE requires no active blocking issues or unresolved finding obligations"):
                    ledger.cmd_gate(Namespace(control_root=str(control), run_id=RUN_ID, owner_token=token, revision=77, phase="PLAN", control="ACTIVE", gate_id="G3", reason=None, next_action="g2_pass", subject_refs="", preconditions="", read_refs=""))

    def test_owner_and_revision_fences(self):
        with tempfile.TemporaryDirectory() as directory:
            control, token, paths, _ = self.make_fixture(directory)
            with self.hash_patch(paths):
                with self.assertRaisesRegex(ledger.LedgerError, "owner token mismatch"):
                    ledger.cmd_migrate_review_currentness(self.args(control, "wrong", 77))
                with self.assertRaisesRegex(ledger.LedgerError, "revision mismatch"):
                    ledger.cmd_migrate_review_currentness(self.args(control, token, 76))


if __name__ == "__main__":
    unittest.main()
