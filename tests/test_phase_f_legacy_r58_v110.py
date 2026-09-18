from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools import ledger


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "legacy" / "idea-scout-r58"
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]
OWNER = "<REDACTED_OWNER_TOKEN>"
RUN_ID = "2026-09-17-idea-scout-v2-successor"
TICKET_ID = "T02-R17"
REVIEW_ATTEMPT_ID = "T02-R17-REVIEW-CODE-05"
WORKER_ATTEMPT_ID = "T02-R17-WORKER-05"
CANDIDATE_ID = "candidate-T02-R17-WORKER-05"
EXTERNAL_BLOCKER = "issue-62c0073109c9529a"
SOURCE_LEDGER_SHA = "dbfe634b0ea9bb94cc91f14f249d38b5947b74f0c285c9a80d131f74d582a894"
PUBLICATION_REF = "idea-scout-v2-design-bundle-successor-v3"
PUBLICATION_HASH = "2b862ffe568c9d86166861dd9910c0491162d601b2765b8bf956035f3729f3da"
PACKET_SHA = "e8b28341a5e2202e22c0281de105780bc92b9d5079f7104df9475bdf26001a00"
RETURN_SHA = "e977b0f75bde0456a1a644fb82ad683f31ae10926b804b5798b8912ddc5dcd1c"
CONTINUATION_SHA = "8391797669bfcfe374950008c9dc3a343724ad4cf687b405ed870586c7d3c0d0"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_fixture(name: str) -> bytes:
    return (FIXTURE / name).read_bytes()


def fixture_json(name: str) -> dict[str, Any]:
    return json.loads(read_fixture(name).decode("utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ledger.canonical_bytes(value))


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


def fixture_intersections(state: dict[str, Any]) -> list[dict[str, str]]:
    ticket_by_id = {item["id"]: item for item in state["tickets"]}
    contract_by_id = {item["id"]: item for item in state["contracts"]}
    publication = state["design_publication"]
    pairs = []
    for ticket_ref in publication["ticket_refs"]:
        ticket_inputs = set(ticket_by_id[ticket_ref]["contract_refs"])
        for contract_ref in publication["contract_refs"]:
            contract = contract_by_id[contract_ref]
            if contract_ref in ticket_inputs and ticket_ref in contract["producer_refs"]:
                pairs.append({"ticket_ref": ticket_ref, "contract_ref": contract_ref})
    return sorted(pairs, key=lambda item: (item["ticket_ref"], item["contract_ref"]))


def normalization_manifest(
    state: dict[str, Any],
    *,
    migration_id: str = "phase-f-r58-binding-normalization",
    classification: str = "metadata_only",
    effective_role: str = "specification_only",
    source_ledger_hash: str = SOURCE_LEDGER_SHA,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "migration_id": migration_id,
        "source_revision": state["revision"],
        "source_ledger_hash": source_ledger_hash,
        "owner_epoch": state["owner"]["epoch"],
        "publication_ref": state["design_publication"]["id"],
        "publication_hash": state["design_publication"]["publication_hash"],
        "bindings": [
            {
                **pair,
                "original_relation": "self_input",
                "original_refs": [pair["ticket_ref"], pair["contract_ref"]],
                "classification": classification,
                "effective_role": effective_role,
                "implementation_availability": "not_required",
                "implementation_availability_evidence_refs": ["source-review:availability-disposition-not-required"],
                "equivalence_refs": ["source-review:idea-scout-r58-contract-intersections"],
                "evidence_refs": ["source-review:idea-scout-r58-contract-intersections"],
            }
            for pair in fixture_intersections(state)
        ],
    }


def review05_manifest(
    state: dict[str, Any],
    *,
    source_revision: int | None = None,
    source_ledger_hash: str = SOURCE_LEDGER_SHA,
    reconciliation_id: str = "phase-f-review05-finding-binding",
) -> dict[str, Any]:
    packet = fixture_json("review05-packet.json")
    review = next(item for item in state["attempts"] if item["id"] == REVIEW_ATTEMPT_ID)
    worker = next(item for item in state["attempts"] if item["id"] == WORKER_ATTEMPT_ID)
    findings = [item for item in state["findings"] if item["source_ref"] == REVIEW_ATTEMPT_ID]
    issues_by_finding = {
        item["finding_ref"]: item["id"]
        for item in state["issues"]
        if item.get("finding_ref") in {finding["id"] for finding in findings}
    }
    return {
        "schema_version": 1,
        "reconciliation_id": reconciliation_id,
        "source_revision": state["revision"] if source_revision is None else source_revision,
        "source_ledger_hash": source_ledger_hash,
        "owner_epoch": state["owner"]["epoch"],
        "review_attempt_ref": REVIEW_ATTEMPT_ID,
        "ticket_ref": TICKET_ID,
        "candidate_ref": CANDIDATE_ID,
        "candidate_sha": worker["candidate_sha"],
        "candidate_tree_sha": worker["candidate_tree_sha"],
        "packet_ref": review["packet_ref"],
        "packet_hash": PACKET_SHA,
        "return_ref": review["return_ref"],
        "return_hash": sha256(read_fixture("review05-return.json")),
        "continuation_receipt_ref": worker["continuation_ref"],
        "continuation_receipt_hash": sha256(read_fixture("worker05-continuation-receipt.json")),
        "finding_bindings": [
            {"finding_ref": finding["id"], "issue_ref": issues_by_finding[finding["id"]]}
            for finding in findings
        ],
    }


def stage_frozen_copy(root: Path) -> dict[str, Any]:
    """Stage only the frozen rev58 ledger and its three supplied payload objects."""
    control = root / "control"
    run_dir = control / ".autopilot" / "runs" / RUN_ID
    objects = run_dir / "objects"
    objects.mkdir(parents=True)
    ledger_path = run_dir / "ledger.json"
    ledger_raw = read_fixture("rev-058-ledger.json")
    ledger_path.write_bytes(ledger_raw)

    for fixture_name, digest in (
        ("review05-packet.json", PACKET_SHA),
        ("review05-return.json", RETURN_SHA),
        ("worker05-continuation-receipt.json", CONTINUATION_SHA),
    ):
        raw = read_fixture(fixture_name)
        if sha256(raw) != digest:
            raise AssertionError(f"frozen fixture hash drifted: {fixture_name}")
        (objects / digest).write_bytes(raw)
        (run_dir / fixture_name).write_bytes(raw)

    return {
        "root": root,
        "control": control,
        "run_dir": run_dir,
        "ledger_path": ledger_path,
        "objects": objects,
        "source_ledger_raw": ledger_raw,
        "source_ledger_hash": sha256(ledger_raw),
        "state": json.loads(ledger_raw.decode("utf-8")),
    }


def stage_complete_copy(root: Path) -> dict[str, Any]:
    """Build a self-contained temp ledger preserving rev58 semantics and pair set."""
    control = root / "control"
    run_dir = control / ".autopilot" / "runs" / RUN_ID
    objects = run_dir / "objects"
    objects.mkdir(parents=True)
    docs_root = root / "docs"
    state = copy.deepcopy(fixture_json("rev-058-ledger.json"))
    state["repository"]["control_root"] = str(control)
    state["repository"]["execution_root"] = str(root)
    state["repository"]["checkout"] = str(root)

    for document in state["documents"]:
        raw = f"Synthetic immutable Phase F document {document['id']} {document['version']}\n".encode()
        path = docs_root / document["id"] / f"{document['version']}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        document["path"] = str(path)
        document["hash"] = sha256(raw)

    current_intent_document = next(
        item for item in state["documents"] if item["id"] == state["intent"]["document_ref"]
    )
    state["intent"]["document_hash"] = current_intent_document["hash"]
    publication_records = [*state.get("design_publication_history", []), state["design_publication"]]
    seen_publications: dict[str, str] = {}
    for publication in publication_records:
        intent_document = next(
            item for item in state["documents"] if item["id"] == publication["intent_document_ref"]
        )
        publication["intent_document_hash"] = intent_document["hash"]
        publication_id = publication["id"]
        digest = seen_publications.get(publication_id)
        if digest is None:
            raw = ledger.canonical_bytes({"synthetic_publication": publication_id})
            digest = sha256(raw)
            seen_publications[publication_id] = digest
            (objects / digest).write_bytes(raw)
        publication["publication_hash"] = digest
        publication["bundle_ref"] = f"objects/{digest}"

    for record in state.get("requirements_publications", []):
        raw = ledger.canonical_bytes({"synthetic_requirements_publication": record["id"]})
        digest = sha256(raw)
        (objects / digest).write_bytes(raw)
        record["publication_hash"] = digest
        record["manifest_ref"] = f"objects/{digest}"
        intent_document = next(
            item for item in state["documents"] if item["id"] == record["intent_document_ref"]
        )
        record["intent_document_hash"] = intent_document["hash"]
    current_publication = state["design_publication"]
    if current_publication.get("requirements_publication_ref"):
        req = next(
            item for item in state["requirements_publications"]
            if item["id"] == current_publication["requirements_publication_ref"]
        )
        current_publication["requirements_publication_ref"] = req["id"]

    for fixture_name, digest in (
        ("review05-packet.json", PACKET_SHA),
        ("review05-return.json", RETURN_SHA),
        ("worker05-continuation-receipt.json", CONTINUATION_SHA),
    ):
        raw = read_fixture(fixture_name)
        if sha256(raw) != digest:
            raise AssertionError(f"frozen fixture hash drifted: {fixture_name}")
        (objects / digest).write_bytes(raw)

    ledger.validate_ledger(state, verify_files=True)
    source_raw = ledger.canonical_bytes(state)
    ledger_path = run_dir / "ledger.json"
    ledger_path.write_bytes(source_raw)
    return {
        "root": root,
        "control": control,
        "run_dir": run_dir,
        "ledger_path": ledger_path,
        "objects": objects,
        "source_ledger_raw": source_raw,
        "source_ledger_hash": sha256(source_raw),
        "state": state,
    }


def object_tree_hashes(objects: Path) -> dict[str, str]:
    return {
        path.name: sha256(path.read_bytes())
        for path in sorted(objects.iterdir())
        if path.is_file()
    }


class PhaseFLegacyR58Tests(unittest.TestCase):
    def write_manifest(self, root: Path, manifest: dict[str, Any], name: str = "manifest.json") -> Path:
        path = root / name
        write_json(path, manifest)
        return path

    def assess(self, root: Path, manifest: dict[str, Any], *, source_path: Path | None = None,
               expect: int = 0) -> subprocess.CompletedProcess[str]:
        manifest_path = self.write_manifest(root, manifest)
        return run(
            "assess-legacy-bindings",
            "--file", str(source_path or (FIXTURE / "rev-058-ledger.json")),
            "--manifest", str(manifest_path),
            expect=expect,
        )

    def test_dry_run_requires_exact_classified_pairs_and_is_deterministic_read_only(self) -> None:
        frozen_before = {
            path.name: sha256(path.read_bytes())
            for path in FIXTURE.iterdir()
            if path.is_file()
        }
        state = fixture_json("rev-058-ledger.json")
        manifest = normalization_manifest(state)
        self.assertEqual(13, len(manifest["bindings"]))
        self.assertEqual(9, len({item["ticket_ref"] for item in manifest["bindings"]}))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_copy = stage_frozen_copy(root / "source-copy")
            first = self.assess(root, manifest, source_path=source_copy["ledger_path"])
            second = self.assess(root, manifest, source_path=source_copy["ledger_path"])
            self.assertEqual(first.stdout, second.stdout)
            assessment = json.loads(first.stdout)
            self.assertTrue(assessment.get("valid"))
            self.assertEqual(58, assessment.get("source_revision"))
            self.assertEqual(SOURCE_LEDGER_SHA, assessment.get("source_ledger_hash"))
            self.assertEqual(PUBLICATION_REF, assessment.get("publication_ref"))
            self.assertEqual(PUBLICATION_HASH, assessment.get("publication_hash"))
            self.assertEqual(13, assessment.get("intersection_count"))
            self.assertEqual(13, assessment.get("metadata_only_count"))
            self.assertEqual(0, assessment.get("material_change_count"))
            self.assertEqual(0, assessment.get("ambiguous_count"))
            self.assertEqual(9, assessment.get("distinct_ticket_count"))
            self.assertEqual(
                [(item["ticket_ref"], item["contract_ref"]) for item in manifest["bindings"]],
                [(item["ticket_ref"], item["contract_ref"]) for item in assessment["intersections"]],
            )
            self.assertEqual(read_fixture("rev-058-ledger.json"), source_copy["ledger_path"].read_bytes())

            missing = copy.deepcopy(manifest)
            missing["bindings"].pop()
            self.assess(root, missing, source_path=source_copy["ledger_path"], expect=2)

            extra = copy.deepcopy(manifest)
            extra["bindings"].append({
                **extra["bindings"][0], "ticket_ref": "T-NOT-IN-PUBLICATION",
            })
            self.assess(root, extra, source_path=source_copy["ledger_path"], expect=2)

            wrong_pair = copy.deepcopy(manifest)
            wrong_pair["bindings"][0]["contract_ref"] = "CT-NOT-AN-INTERSECTION"
            self.assess(root, wrong_pair, source_path=source_copy["ledger_path"], expect=2)

            for field, wrong in (("source_revision", 57), ("source_ledger_hash", "0" * 64),
                                 ("publication_ref", "wrong-publication"),
                                 ("publication_hash", "1" * 64)):
                bad = copy.deepcopy(manifest)
                bad[field] = wrong
                self.assess(root, bad, source_path=source_copy["ledger_path"], expect=2)

            for classification in ("ambiguous", "material_change"):
                blocked = normalization_manifest(state, classification=classification)
                blocked_path = self.write_manifest(root, blocked, f"{classification}.json")
                stage = stage_complete_copy(root / classification)
                blocked["source_ledger_hash"] = stage["source_ledger_hash"]
                blocked["publication_hash"] = stage["state"]["design_publication"]["publication_hash"]
                blocked_path = self.write_manifest(root, blocked, f"{classification}.json")
                before_ledger = stage["ledger_path"].read_bytes()
                before_objects = object_tree_hashes(stage["objects"])
                result = run(
                    "migrate-legacy-bindings", "--control-root", str(stage["control"]),
                    "--run-id", RUN_ID, "--owner-token", OWNER, "--revision", "58",
                    "--manifest", str(blocked_path), expect=2,
                )
                self.assertRegex(result.stderr.lower(), r"ambiguous|material|classification|metadata")
                self.assertEqual(before_ledger, stage["ledger_path"].read_bytes())
                self.assertEqual(before_objects, object_tree_hashes(stage["objects"]))

        frozen_after = {
            path.name: sha256(path.read_bytes())
            for path in FIXTURE.iterdir()
            if path.is_file()
        }
        self.assertEqual(frozen_before, frozen_after)

    def test_read_only_rehearsal_binds_review05_and_keeps_fixture_bytes_immutable(self) -> None:
        state = fixture_json("rev-058-ledger.json")
        binding = normalization_manifest(state)
        findings = review05_manifest(state)
        frozen_before = {
            path.name: sha256(path.read_bytes())
            for path in FIXTURE.iterdir()
            if path.is_file()
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = stage_frozen_copy(root / "frozen-stage")
            self.assertEqual(read_fixture("rev-058-ledger.json"), staged["ledger_path"].read_bytes())
            self.assertEqual(SOURCE_LEDGER_SHA, staged["source_ledger_hash"])
            self.assertEqual(PACKET_SHA, sha256((staged["objects"] / PACKET_SHA).read_bytes()))
            self.assertEqual(RETURN_SHA, sha256((staged["objects"] / RETURN_SHA).read_bytes()))
            self.assertEqual(CONTINUATION_SHA, sha256((staged["objects"] / CONTINUATION_SHA).read_bytes()))
            frozen_copy_raw = staged["ledger_path"].read_bytes()
            binding_path = self.write_manifest(root, binding, "binding.json")
            finding_path = self.write_manifest(root, findings, "finding-bindings.json")
            args = (
                "rehearse-legacy-recovery", "--file", str(staged["ledger_path"]),
                "--binding-manifest", str(binding_path), "--finding-manifest", str(finding_path),
            )
            first = run(*args)
            second = run(*args)
            self.assertEqual(first.stdout, second.stdout)
            result = json.loads(first.stdout)
            self.assertTrue(result.get("read_only"))
            self.assertTrue(result.get("source_hash_unchanged"))
            self.assertEqual(SOURCE_LEDGER_SHA, result.get("source_ledger_hash"))
            self.assertEqual(58, result.get("source_revision"))
            self.assertEqual(13, result.get("intersection_count"))
            self.assertEqual(3, result.get("current_finding_count"))
            self.assertEqual(7, result.get("historical_ticket_finding_count"))
            self.assertEqual(11, result.get("historical_design_finding_count"))
            projection = result["finding_projection"]
            projection_items = projection.get("items", projection.get("records", []))
            projection_by_ref = {item["finding_ref"]: item for item in projection_items}
            review05_refs = {
                item["id"] for item in state["findings"]
                if item.get("source_ref") == REVIEW_ATTEMPT_ID
            }
            historical_t02 = {
                item["id"] for item in state["findings"]
                if item.get("source_ref", "").startswith((
                    "T02-R17-REVIEW-CODE-01", "T02-R17-REVIEW-CODE-02", "T02-R17-REVIEW-CODE-03",
                ))
            }
            historical_design = {
                item["id"] for item in state["findings"]
                if item.get("source_ref", "").startswith(("G2-", "G3-"))
            }
            self.assertEqual(3, len(review05_refs))
            self.assertEqual(7, len(historical_t02))
            self.assertEqual(11, len(historical_design))
            self.assertTrue(all(projection_by_ref[ref].get("status") == "current" for ref in review05_refs))
            self.assertTrue(all(projection_by_ref[ref].get("projection_classification") == "carry_forward"
                                for ref in historical_t02))
            self.assertTrue(all(projection_by_ref[ref].get("projection_classification") in ("carry_forward", "history")
                                for ref in historical_design))
            self.assertEqual(EXTERNAL_BLOCKER, result.get("external_blocker_ref"))
            next_action_text = result.get("next_action", "").lower()
            self.assertTrue("repair" in next_action_text or "adjudicat" in next_action_text)
            self.assertNotIn("await", next_action_text)
            self.assertEqual(frozen_copy_raw, staged["ledger_path"].read_bytes())

            for field, value in (("packet_hash", "0" * 64), ("return_hash", "1" * 64),
                                 ("candidate_ref", "0" * 40), ("ticket_ref", "T-NOT-T02")):
                invalid = copy.deepcopy(findings)
                invalid[field] = value
                invalid_path = self.write_manifest(root, invalid, f"invalid-{field}.json")
                run(
                    "rehearse-legacy-recovery", "--file", str(staged["ledger_path"]),
                    "--binding-manifest", str(binding_path), "--finding-manifest", str(invalid_path),
                    expect=2,
                )

        frozen_after = {
            path.name: sha256(path.read_bytes())
            for path in FIXTURE.iterdir()
            if path.is_file()
        }
        self.assertEqual(frozen_before, frozen_after)

    def migrate_copy(self, case: dict[str, Any], manifest: dict[str, Any], manifest_path: Path,
                     *, revision: int = 58, owner: str = OWNER,
                     expect: int = 0) -> subprocess.CompletedProcess[str]:
        return run(
            "migrate-legacy-bindings", "--control-root", str(case["control"]),
            "--run-id", RUN_ID, "--owner-token", owner, "--revision", str(revision),
            "--manifest", str(manifest_path), expect=expect,
        )

    def test_append_only_normalization_is_cas_fenced_and_replay_safe_on_copy(self) -> None:
        frozen_before = {
            path.name: sha256(path.read_bytes())
            for path in FIXTURE.iterdir()
            if path.is_file()
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = stage_complete_copy(root)
            manifest = normalization_manifest(case["state"], source_ledger_hash=case["source_ledger_hash"])
            manifest_path = self.write_manifest(root, manifest, "normalization.json")
            original_ticket = next(item for item in case["state"]["tickets"] if item["id"] == TICKET_ID)
            original_contracts = {
                item["id"]: (item.get("producer_refs"), item.get("status"))
                for item in case["state"]["contracts"]
            }

            first = self.migrate_copy(case, manifest, manifest_path)
            first_payload = json.loads(first.stdout)
            self.assertTrue(first_payload.get("migrated"))
            migrated_raw = case["ledger_path"].read_bytes()
            migrated = json.loads(migrated_raw.decode("utf-8"))
            self.assertEqual(59, migrated["revision"])
            self.assertIsNone(ledger.mutation_ineligibility(migrated))
            self.assertEqual(case["source_ledger_raw"], (case["run_dir"] / "ledger.prev.json").read_bytes())
            ticket = next(item for item in migrated["tickets"] if item["id"] == TICKET_ID)
            self.assertEqual(original_ticket["contract_refs"], ticket["contract_refs"])
            self.assertEqual(CANDIDATE_ID, ticket["current_candidate"])
            self.assertEqual(WORKER_ATTEMPT_ID, ticket["last_worker_attempt"])
            self.assertIsNone(ticket["current_worker_attempt"])
            candidate = next(item for item in migrated["candidates"] if item["id"] == CANDIDATE_ID)
            worker = next(item for item in migrated["attempts"] if item["id"] == WORKER_ATTEMPT_ID)
            self.assertEqual(worker["candidate_sha"], candidate["sha"])
            self.assertEqual(worker["candidate_tree_sha"], candidate["tree_sha"])
            self.assertIsNone(candidate["proof_ref"])
            for contract_id, (producer_refs, status) in original_contracts.items():
                contract = next(item for item in migrated["contracts"] if item["id"] == contract_id)
                self.assertEqual(producer_refs, contract.get("producer_refs"))
                self.assertEqual(status, contract.get("status"))

            records = migrated.get("binding_normalizations", [])
            self.assertEqual(1, len(records))
            record = records[0]
            self.assertEqual(58, record["source_revision"])
            self.assertEqual(case["source_ledger_hash"], record["source_ledger_hash"])
            self.assertEqual(PUBLICATION_REF, record["publication_ref"])
            self.assertEqual(manifest["publication_hash"], record["publication_hash"])
            self.assertEqual(13, len(record["bindings"]))
            supplied_by_pair = {
                (item["ticket_ref"], item["contract_ref"]): item
                for item in manifest["bindings"]
            }
            for normalized in record["bindings"]:
                supplied = supplied_by_pair[(normalized["ticket_ref"], normalized["contract_ref"])]
                self.assertEqual(
                    supplied["implementation_availability_evidence_refs"],
                    normalized["implementation_availability_evidence_refs"],
                )
                self.assertNotEqual(
                    normalized["equivalence_refs"],
                    normalized["implementation_availability_evidence_refs"],
                )
            manifest_hash = sha256(manifest_path.read_bytes())
            self.assertEqual(manifest_hash, record["manifest_hash"])
            object_ref = record.get("object_ref", record.get("manifest_ref"))
            self.assertEqual(f"objects/{manifest_hash}", object_ref)
            self.assertEqual(manifest_path.read_bytes(), (case["objects"] / manifest_hash).read_bytes())

            # Append-only normalization records are semantic ledger events:
            # malformed, duplicate, and pair-overlapping events fail validation.
            malformed = copy.deepcopy(migrated)
            malformed["binding_normalizations"][0]["bindings"][0]["original_refs"] = ["T-WRONG"]
            with self.assertRaises(ledger.LedgerError):
                ledger.validate_ledger(malformed, verify_files=False)

            duplicated = copy.deepcopy(migrated)
            duplicated["binding_normalizations"].append(copy.deepcopy(records[0]))
            with self.assertRaises(ledger.LedgerError):
                ledger.validate_ledger(duplicated, verify_files=False)

            overlapping = copy.deepcopy(migrated)
            overlapping_event = copy.deepcopy(records[0])
            overlapping_event["id"] = "binding-normalization-overlap"
            overlapping_event["migration_id"] = "phase-f-overlap-check"
            overlapping_event["bindings"] = [copy.deepcopy(records[0]["bindings"][0])]
            overlapping["binding_normalizations"].append(overlapping_event)
            with self.assertRaises(ledger.LedgerError):
                ledger.validate_ledger(overlapping, verify_files=False)

            after_first_objects = object_tree_hashes(case["objects"])
            replay = self.migrate_copy(case, manifest, manifest_path, revision=59)
            replay_payload = json.loads(replay.stdout)
            self.assertTrue(replay_payload.get("idempotent", replay_payload.get("migrated")))
            self.assertEqual(migrated_raw, case["ledger_path"].read_bytes())
            self.assertEqual(after_first_objects, object_tree_hashes(case["objects"]))

            conflict = copy.deepcopy(manifest)
            conflict["bindings"][0]["evidence_refs"] = ["different-evidence"]
            conflict_path = self.write_manifest(root, conflict, "conflicting.json")
            self.migrate_copy(case, conflict, conflict_path, revision=59, expect=2)

            conflict_classification = copy.deepcopy(manifest)
            conflict_classification["bindings"][0]["classification"] = "ambiguous"
            conflict_classification_path = self.write_manifest(
                root, conflict_classification, "conflicting-classification.json",
            )
            self.migrate_copy(case, conflict_classification, conflict_classification_path,
                              revision=59, expect=2)

            stale_manifest = copy.deepcopy(manifest)
            stale_manifest["source_revision"] = 57
            stale_path = self.write_manifest(root, stale_manifest, "stale-source.json")
            self.migrate_copy(case, stale_manifest, stale_path, revision=59, expect=2)

            self.migrate_copy(case, manifest, manifest_path, owner="wrong-owner", revision=59, expect=2)
            self.migrate_copy(case, manifest, manifest_path, revision=57, expect=2)
            self.assertEqual(migrated_raw, case["ledger_path"].read_bytes())
            self.assertEqual(after_first_objects, object_tree_hashes(case["objects"]))

        frozen_after = {
            path.name: sha256(path.read_bytes())
            for path in FIXTURE.iterdir()
            if path.is_file()
        }
        self.assertEqual(frozen_before, frozen_after)

    def test_effective_validator_and_consumer_availability_are_separate_from_raw_metadata(self) -> None:
        frozen = fixture_json("rev-058-ledger.json")
        ticket = next(item for item in frozen["tickets"] if item["id"] == TICKET_ID)
        with self.assertRaises(ledger.LedgerError):
            ledger.validate_effective_ticket_contract_bindings(
                frozen, [ticket], "legacy frozen design",
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = stage_complete_copy(root)
            manifest = normalization_manifest(case["state"], source_ledger_hash=case["source_ledger_hash"])
            manifest_path = self.write_manifest(root, manifest, "normalization.json")
            self.migrate_copy(case, manifest, manifest_path)
            migrated = json.loads(case["ledger_path"].read_text(encoding="utf-8"))
            ticket = next(item for item in migrated["tickets"] if item["id"] == TICKET_ID)
            effective = ledger.effective_ticket_contract_bindings(migrated, ticket)
            self.assertIn("CT-V2-ARCHITECTURE-R17", effective["specification_refs"])
            self.assertNotIn("CT-V2-ARCHITECTURE-R17", effective["implementation_input_refs"])
            ledger.validate_effective_ticket_contract_bindings(
                migrated, [ticket], "normalized metadata-only view",
            )

            # Architecture is explicitly not_required/specification_only above;
            # checkpoint and routing remain executable inputs. Active status
            # alone cannot establish their implementation availability.
            with self.assertRaisesRegex(ledger.LedgerError, "status alone is insufficient"):
                ledger.validate_effective_ticket_contract_bindings(
                    migrated, [ticket], "consumer readiness", require_availability=True,
                )
            for contract_id in ("CT-V2-CHECKPOINT-R17", "CT-V2-ROUTING-R17"):
                contract = next(item for item in migrated["contracts"] if item["id"] == contract_id)
                contract["implementation_availability"] = "available"
                contract["implementation_availability_evidence_refs"] = [f"EV-{contract_id}-AVAILABILITY"]
            ledger.validate_effective_ticket_contract_bindings(
                migrated, [ticket], "consumer readiness", require_availability=True,
            )

    def reconcile_copy(self, case: dict[str, Any], manifest: dict[str, Any], manifest_path: Path,
                       *, revision: int = 59, owner: str = OWNER,
                       expect: int = 0) -> subprocess.CompletedProcess[str]:
        return run(
            "reconcile-finding-bindings", "--control-root", str(case["control"]),
            "--run-id", RUN_ID, "--owner-token", owner, "--revision", str(revision),
            "--manifest", str(manifest_path), expect=expect,
        )

    def test_review05_binding_reconciliation_is_exact_atomic_and_projection_carries_history(self) -> None:
        frozen_before = {
            path.name: sha256(path.read_bytes())
            for path in FIXTURE.iterdir()
            if path.is_file()
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = stage_complete_copy(root)
            binding = normalization_manifest(case["state"], source_ledger_hash=case["source_ledger_hash"])
            binding_path = self.write_manifest(root, binding, "normalization.json")
            self.migrate_copy(case, binding, binding_path)
            migrated_raw = case["ledger_path"].read_bytes()
            migrated = json.loads(migrated_raw.decode("utf-8"))
            finding_manifest = review05_manifest(
                migrated,
                source_revision=migrated["revision"],
                source_ledger_hash=sha256(migrated_raw),
            )
            finding_path = self.write_manifest(root, finding_manifest, "finding-binding.json")
            raw_findings_before = {
                item["id"]: (item.get("affected_refs"), item.get("reported_affected_refs"))
                for item in migrated["findings"]
                if item.get("source_ref") == REVIEW_ATTEMPT_ID
            }
            raw_issues_before = {
                item["id"]: copy.deepcopy(item)
                for item in migrated["issues"]
                if item.get("finding_ref") in raw_findings_before
            }
            packet_raw = (case["objects"] / PACKET_SHA).read_bytes()
            return_raw = (case["objects"] / RETURN_SHA).read_bytes()
            receipt_raw = (case["objects"] / CONTINUATION_SHA).read_bytes()

            for mutation_name in ("issue-source", "issue-invalidation"):
                malformed_source_state = copy.deepcopy(migrated)
                issue_ref = finding_manifest["finding_bindings"][0]["issue_ref"]
                malformed_issue = next(
                    item for item in malformed_source_state["issues"] if item["id"] == issue_ref
                )
                if mutation_name == "issue-source":
                    malformed_issue["source_ref"] = "T02-R17-REVIEW-CODE-04"
                else:
                    malformed_issue["invalidated_by"] = [REVIEW_ATTEMPT_ID]
                malformed_raw = ledger.canonical_bytes(malformed_source_state)
                case["ledger_path"].write_bytes(malformed_raw)
                malformed_manifest = review05_manifest(
                    malformed_source_state,
                    source_revision=malformed_source_state["revision"],
                    source_ledger_hash=sha256(malformed_raw),
                    reconciliation_id=f"phase-f-malformed-{mutation_name}",
                )
                malformed_manifest_path = self.write_manifest(
                    root, malformed_manifest, f"{mutation_name}.json",
                )
                objects_before = object_tree_hashes(case["objects"])
                self.reconcile_copy(case, malformed_manifest, malformed_manifest_path, expect=2)
                self.assertEqual(malformed_raw, case["ledger_path"].read_bytes())
                self.assertEqual(objects_before, object_tree_hashes(case["objects"]))
                case["ledger_path"].write_bytes(migrated_raw)

            # Every wrong binding is rejected before publishing state or objects.
            mutations = [
                ("packet_hash", "0" * 64),
                ("packet_ref", f"objects/{'0' * 64}"),
                ("return_hash", "1" * 64),
                ("return_ref", f"objects/{'1' * 64}"),
                ("candidate_ref", "candidate-not-current"),
                ("candidate_sha", "0" * 40),
                ("candidate_tree_sha", "1" * 40),
                ("continuation_receipt_hash", "2" * 64),
                ("ticket_ref", "T-NOT-T02"),
            ]
            for field, value in mutations:
                invalid = copy.deepcopy(finding_manifest)
                invalid[field] = value
                invalid_path = self.write_manifest(root, invalid, f"invalid-{field}.json")
                state_before = case["ledger_path"].read_bytes()
                objects_before = object_tree_hashes(case["objects"])
                self.reconcile_copy(case, invalid, invalid_path, expect=2)
                self.assertEqual(state_before, case["ledger_path"].read_bytes())
                self.assertEqual(objects_before, object_tree_hashes(case["objects"]))

            wrong_set = copy.deepcopy(finding_manifest)
            wrong_set["finding_bindings"].pop()
            wrong_path = self.write_manifest(root, wrong_set, "invalid-finding-set.json")
            state_before = case["ledger_path"].read_bytes()
            objects_before = object_tree_hashes(case["objects"])
            self.reconcile_copy(case, wrong_set, wrong_path, expect=2)
            self.assertEqual(state_before, case["ledger_path"].read_bytes())
            self.assertEqual(objects_before, object_tree_hashes(case["objects"]))

            self.reconcile_copy(case, finding_manifest, finding_path, owner="wrong-owner", expect=2)
            self.reconcile_copy(case, finding_manifest, finding_path, revision=58, expect=2)
            self.assertEqual(state_before, case["ledger_path"].read_bytes())
            self.assertEqual(objects_before, object_tree_hashes(case["objects"]))

            accepted = self.reconcile_copy(case, finding_manifest, finding_path)
            accepted_payload = json.loads(accepted.stdout)
            self.assertTrue(accepted_payload.get("reconciled"))
            self.assertEqual(3, len(accepted_payload.get("finding_refs", [])))
            reconciled_raw = case["ledger_path"].read_bytes()
            reconciled = json.loads(reconciled_raw.decode("utf-8"))
            self.assertEqual(60, reconciled["revision"])
            self.assertEqual(migrated_raw, (case["run_dir"] / "ledger.prev.json").read_bytes())

            actual_findings = {
                item["id"]: (item.get("affected_refs"), item.get("reported_affected_refs"))
                for item in reconciled["findings"]
                if item.get("source_ref") == REVIEW_ATTEMPT_ID
            }
            self.assertEqual(raw_findings_before, actual_findings)
            actual_issues = {
                item["id"]: item
                for item in reconciled["issues"]
                if item.get("finding_ref") in raw_findings_before
            }
            self.assertEqual(raw_issues_before, actual_issues)
            self.assertEqual(packet_raw, (case["objects"] / PACKET_SHA).read_bytes())
            self.assertEqual(return_raw, (case["objects"] / RETURN_SHA).read_bytes())
            self.assertEqual(receipt_raw, (case["objects"] / CONTINUATION_SHA).read_bytes())
            self.assertEqual(PACKET_SHA, sha256((case["objects"] / PACKET_SHA).read_bytes()))
            self.assertEqual(RETURN_SHA, sha256((case["objects"] / RETURN_SHA).read_bytes()))

            reconciliations = reconciled.get("finding_binding_reconciliations", [])
            self.assertEqual(1, len(reconciliations))
            reconciliation = reconciliations[0]
            self.assertEqual(finding_manifest["finding_bindings"], reconciliation["finding_bindings"])
            self.assertEqual(sha256(finding_path.read_bytes()), reconciliation["manifest_hash"])
            self.assertEqual(f"objects/{reconciliation['manifest_hash']}", reconciliation["manifest_ref"])
            self.assertEqual(finding_path.read_bytes(), (case["objects"] / reconciliation["manifest_hash"]).read_bytes())

            # The issue side of every reconciliation mirror must remain bound
            # to the exact source attempt and cannot be invalidated underneath it.
            bound_issue_ref = reconciliation["finding_bindings"][0]["issue_ref"]
            malformed_source = copy.deepcopy(reconciled)
            source_issue = next(item for item in malformed_source["issues"] if item["id"] == bound_issue_ref)
            source_issue["source_ref"] = "T02-R17-REVIEW-CODE-04"
            with self.assertRaises(ledger.LedgerError):
                ledger.validate_ledger(malformed_source, verify_files=False)

            invalidated_mirror = copy.deepcopy(reconciled)
            invalidated_issue = next(item for item in invalidated_mirror["issues"] if item["id"] == bound_issue_ref)
            invalidated_issue["invalidated_by"] = [REVIEW_ATTEMPT_ID]
            with self.assertRaises(ledger.LedgerError):
                ledger.validate_ledger(invalidated_mirror, verify_files=False)

            projection = ledger.finding_obligation_projection(reconciled)
            current = [item for item in projection["items"] if item.get("status") == "current"]
            carry_forward = [item for item in projection["items"] if item.get("status") == "historical"]
            self.assertEqual(3, len(current))
            review05_refs = {item["id"] for item in reconciled["findings"] if item.get("source_ref") == REVIEW_ATTEMPT_ID}
            self.assertEqual(review05_refs, {item["finding_ref"] for item in current})
            self.assertTrue(all(item.get("source_candidate_ref") == CANDIDATE_ID for item in current))
            self.assertTrue(all(item.get("affected_ticket_refs") == [TICKET_ID] for item in current))
            historical_t02 = {
                item["id"] for item in fixture_json("rev-058-ledger.json")["findings"]
                if item.get("source_ref", "").startswith(("T02-R17-REVIEW-CODE-01", "T02-R17-REVIEW-CODE-02", "T02-R17-REVIEW-CODE-03"))
            }
            historical_design = {
                item["id"] for item in fixture_json("rev-058-ledger.json")["findings"]
                if item.get("source_ref", "").startswith(("G2-", "G3-"))
            }
            projection_by_ref = {item["finding_ref"]: item for item in projection["items"]}
            self.assertEqual(7, len(historical_t02))
            self.assertEqual(11, len(historical_design))
            self.assertTrue(all(projection_by_ref[ref]["projection_classification"] == "carry_forward"
                                for ref in historical_t02))
            self.assertTrue(all(projection_by_ref[ref]["projection_classification"] in ("carry_forward", "history")
                                for ref in historical_design))
            carry_forward_refs = set(projection.get("carry_forward_finding_refs", []))
            self.assertTrue(historical_t02.issubset(carry_forward_refs))
            carry_forward_obligations = {
                item.get("finding_ref") for item in projection["obligations"]
                if item.get("applicability") == "carry_forward"
            }
            self.assertTrue(historical_t02.issubset(carry_forward_obligations))
            blocker = next(item for item in reconciled["issues"] if item["id"] == EXTERNAL_BLOCKER)
            self.assertEqual([], blocker.get("invalidated_by"))
            self.assertEqual("blocking", blocker.get("impact"))
            blocker_mirror = next(
                item for item in projection["mirrored_issues"] if item.get("issue_ref") == EXTERNAL_BLOCKER
            )
            self.assertTrue(blocker_mirror.get("active"))
            next_action = reconciled["lifecycle"]["next_action"]["kind"].lower()
            self.assertTrue("repair" in next_action or "adjudicat" in next_action)
            self.assertNotIn("await", next_action)

            before_replay_objects = object_tree_hashes(case["objects"])
            replay = self.reconcile_copy(case, finding_manifest, finding_path, revision=60)
            replay_payload = json.loads(replay.stdout)
            self.assertTrue(replay_payload.get("idempotent", replay_payload.get("reconciled")))
            self.assertEqual(reconciled_raw, case["ledger_path"].read_bytes())
            self.assertEqual(before_replay_objects, object_tree_hashes(case["objects"]))

        frozen_after = {
            path.name: sha256(path.read_bytes())
            for path in FIXTURE.iterdir()
            if path.is_file()
        }
        self.assertEqual(frozen_before, frozen_after)
