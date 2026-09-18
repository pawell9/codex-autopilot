from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools import ledger


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]
RUN_ID = "phase-c-repair-run"
OWNER = "owner-c"
BASE_SHA = "a" * 40


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def write_json(path: Path, value: Any) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


def bind_test_design(state: dict[str, Any], paths: dict[str, Path], root: Path) -> None:
    """Give synthetic repair fixtures the same current intent/design mandate as a real run."""
    intent_path = root / "intent.md"
    design_path = root / "design.md"
    intent_path.write_text("# Fixture intent\n", encoding="utf-8")
    design_path.write_text("# Fixture design\n", encoding="utf-8")
    intent_hash = ledger.sha256_file(intent_path)
    design_hash = ledger.sha256_file(design_path)
    state["documents"] = [
        {"id": "D-intent", "version": "v1", "path": str(intent_path), "hash": intent_hash, "kind": "intent", "section_anchors": []},
        {"id": "D-design", "version": "v1", "path": str(design_path), "hash": design_hash, "kind": "design", "section_anchors": []},
    ]
    state["intent"] = {"current_revision": "intent-v1", "document_ref": "D-intent", "document_hash": intent_hash, "approved_amendments": []}
    state["requirements"] = [{"id": "R-1", "version": "v1", "status": "active", "provenance_refs": ["D-intent"], "criterion_refs": ["C-1"]}]
    state["criteria"] = [{"id": "C-1", "version": "v1", "requirement_refs": ["R-1"], "oracle": "fixture oracle", "status": "active", "source_ref": "D-intent"}]
    for ticket in state.get("tickets", []):
        ticket["criterion_refs"] = ["C-1"]
    state["repository"]["initial_head"] = BASE_SHA
    bundle = {"fixture": "Phase G execution binding", "intent_hash": intent_hash, "design_hash": design_hash}
    bundle_raw = ledger.canonical_bytes(bundle)
    bundle_hash = ledger.sha256_bytes(bundle_raw)
    ledger.object_store(paths, bundle_raw)
    publication = {
        "id": "B-execution-binding", "version": "v1", "status": "PUBLISHED",
        "owner_epoch": state["owner"]["epoch"], "intent_revision": "intent-v1",
        "intent_document_ref": "D-intent", "intent_document_hash": intent_hash,
        "publication_hash": bundle_hash, "bundle_ref": f"objects/{bundle_hash}",
        "published_revision": state["revision"], "document_refs": ["D-design"],
        "requirement_refs": ["R-1"], "criterion_refs": ["C-1"],
        "requirements_publication_ref": None, "contract_refs": [],
        "ticket_refs": [item["id"] for item in state.get("tickets", [])], "route_refs": [],
        "invalidated_by": [],
    }
    state["design_publication"] = publication
    state["design_publication_history"] = [copy.deepcopy(publication)]


def seed_repair_fixture(
    root: Path,
    findings: list[tuple[str, str, str]],
) -> tuple[Path, Path, dict[str, Path], dict[tuple[str, str], dict[str, str]]]:
    """Seed current review findings for (ticket, finding, candidate-generation) tuples."""
    control, repo = root / "control", root / "repo"
    control.mkdir()
    repo.mkdir()
    run(
        "init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", RUN_ID,
        "--owner-token", OWNER,
    )
    paths = ledger.paths(control, RUN_ID)
    state, previous = ledger.load_state(paths)

    ticket_ids = list(dict.fromkeys(ticket_id for ticket_id, _, _ in findings))
    state["tickets"] = [
        {
            "id": ticket_id, "goal_ref": f"G-{ticket_id}", "criterion_refs": [], "contract_refs": [],
            "dependency_refs": [], "state": "REVIEW", "complexity": "bounded", "risk": "routine",
            "zone": [{"path": "app.txt", "operations": ["modify"]}], "current_attempt": None,
            "current_worker_attempt": None, "last_worker_attempt": None, "current_candidate": None,
            "replacement_refs": [],
        }
        for ticket_id in ticket_ids
    ]
    state["attempts"] = []
    state["findings"] = []
    state["issues"] = []
    state["decisions"] = []
    state["reviews"] = []
    state["candidates"] = []

    # Preserve first-seen order so repeated candidate generations supersede the old pointer.
    generations = list(dict.fromkeys((ticket_id, generation) for ticket_id, _, generation in findings))
    subjects: dict[tuple[str, str], dict[str, str]] = {}
    for index, (ticket_id, generation) in enumerate(generations):
        worker_id = f"W-{ticket_id}-{generation}"
        review_id = f"R-{ticket_id}-{generation}"
        candidate_char = "b" if index == 0 else chr(ord("b") + index)
        candidate_sha = candidate_char * 40
        tree_sha = chr(ord("0") + (index + 1)) * 40
        ticket = next(item for item in state["tickets"] if item["id"] == ticket_id)
        producer_return = {
            "identity": {
                "run_id": RUN_ID, "ticket_id": ticket_id, "attempt_id": worker_id,
                "packet_hash": "1" * 64, "epoch": 0,
            },
            "status": "DONE", "result": "validated current candidate", "files": [],
            "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "candidate", "evidence_ref": f"EV-{worker_id}"}],
            "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": [f"EV-{worker_id}"]}],
        }
        return_digest = ledger.object_store(paths, ledger.canonical_bytes(producer_return))
        producer = {
            "id": worker_id, "kind": "worker", "mode": "implement", "subject_ref": ticket_id,
            "packet_ref": "objects/" + "2" * 64, "packet_hash": "1" * 64, "epoch": 0,
            "state": "RETURNED", "lease": {"id": f"L-{worker_id}", "state": "released", "zone": []},
            "route_ref": f"route-{worker_id}", "checkout": str(repo), "base_sha": BASE_SHA,
            "candidate_sha": candidate_sha, "candidate_tree_sha": tree_sha,
            "return_ref": f"objects/{return_digest}", "finding_refs": [],
        }
        state["attempts"].append(producer)
        candidate = ledger.publish_candidate_projection(state, ticket, producer, quality="DONE")
        review = {
            "id": review_id, "kind": "review", "mode": "change", "subject_ref": ticket_id,
            "packet_ref": "objects/" + "3" * 64, "packet_hash": "4" * 64, "epoch": 0,
            "state": "RETURNED", "lease": {"id": f"L-{review_id}", "state": "released", "zone": []},
            "route_ref": None, "checkout": None, "base_sha": candidate_sha,
            "candidate_sha": candidate_sha, "candidate_tree_sha": tree_sha,
            "return_ref": "objects/" + "5" * 64, "finding_refs": [],
            "subject_fingerprint": candidate_sha, "review_result": "BLOCK",
        }
        state["attempts"].append(review)
        subjects[(ticket_id, generation)] = {
            "worker": worker_id, "review": review_id, "candidate": candidate["id"],
            "sha": candidate_sha,
        }

    for ticket_id, finding_id, generation in findings:
        subject = subjects[(ticket_id, generation)]
        state["findings"].append({
            "id": finding_id, "axis": "correctness", "impact": "blocking",
            "claim": f"{finding_id} must be repaired", "expected": f"proof for {finding_id}",
            "actual": "defect observed", "evidence": f"EV-{finding_id}",
            "affected_refs": [ticket_id], "source_ref": subject["review"],
            "intent_revision": None, "repair_contract_ref": None, "invalidated_by": [],
        })
        review = next(item for item in state["attempts"] if item["id"] == subject["review"])
        review["finding_refs"].append(finding_id)

    for ticket in state["tickets"]:
        ticket["state"] = "REVIEW"
        latest_worker = next(
            item["id"] for item in reversed(state["attempts"])
            if item.get("kind") == "worker" and item.get("subject_ref") == ticket["id"]
        )
        ticket["current_attempt"] = latest_worker
        ticket["last_worker_attempt"] = latest_worker
    state["lifecycle"] = {
        "phase": "EXECUTE", "control": "BLOCKED", "reason": "review_not_pass",
        "issue_refs": [], "stop_target": None,
        "next_action": {"kind": "triage_or_repair", "subject_refs": ["T-1"], "preconditions": [], "read_refs": []},
    }
    bind_test_design(state, paths, root)
    state["revision"] = 2
    state["previous_publication_hash"] = ledger.sha256_bytes(previous)
    ledger.validate_ledger(state)
    ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
    return control, repo, paths, subjects


def grouped_plan(finding_refs: list[str], source_review: str) -> dict[str, Any]:
    return {
        "cause": "implementation",
        "finding_refs": list(finding_refs),
        "finding_proofs": [
            {"finding_ref": finding_ref, "hypothesis": f"root cause for {finding_ref}",
             "expected_proof": f"independent regression for {finding_ref}"}
            for finding_ref in finding_refs
        ],
        "stopping_condition": "stop after all selected regressions pass",
        "causal_change": "correct the shared implementation",
        "source_attempt_ref": source_review,
    }


def repair_packet(
    root: Path, repo: Path, ticket_id: str, attempt_id: str, candidate_sha: str,
    plan: dict[str, Any], *, deny: list[str] | None = None, allow: list[dict[str, Any]] | None = None,
) -> Path:
    state, _ = ledger.load_state(ledger.paths(root / "control", RUN_ID))
    intent = ledger.current_intent_binding(state)
    publication = state["design_publication"]
    ticket = next(item for item in state["tickets"] if item["id"] == ticket_id)
    packet = {
        "identity": {
            "run_id": RUN_ID, "ticket_id": ticket_id, "attempt_id": attempt_id, "epoch": 0,
            "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
            "intent_document_hash": intent["document_hash"],
            "design_publication_ref": publication["id"], "design_publication_hash": publication["publication_hash"],
            "design_publication_revision": publication["published_revision"],
            "contract_refs": sorted(ticket.get("contract_refs", [])),
        },
        "kind": "worker", "mode": "repair", "goal": "bounded Phase C repair regression",
        "acceptance": [{"criterion_id": "C-1"}],
        "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
        "intent_document_hash": intent["document_hash"],
        "workspace": {"root": str(repo), "expected_base": candidate_sha},
        "write": {
            "allow": allow or [{"path": "app.txt", "operations": ["modify"]}],
            "deny": deny or [],
        },
        "verification": [{"check_id": "oracle", "required": True, "criterion_refs": ["C-1"]}],
        "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}],
        "return_target": {"path": "return.json"}, "repair": copy.deepcopy(plan),
    }
    packet_path = root / f"{attempt_id}-packet.json"
    write_json(packet_path, packet)
    return packet_path


class PhaseCRepairPlanTests(unittest.TestCase):
    def plan_path(self, root: Path, refs: list[str], review_ref: str) -> Path:
        path = root / "repair-plan.json"
        write_json(path, grouped_plan(refs, review_ref))
        return path

    def authorize(
        self, control: Path, *, ticket_id: str, authorization_id: str, plan_path: Path,
        packet_path: Path, revision: int = 2, expect: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        attempt_id = packet["identity"]["attempt_id"]
        return run(
            "authorize-repair", "--control-root", str(control), "--run-id", RUN_ID,
            "--owner-token", OWNER, "--revision", str(revision), "--ticket-id", ticket_id,
            "--authorization-id", authorization_id, "--repair-contract", str(plan_path),
            "--packet", str(packet_path), "--route-id", f"route-{attempt_id}", expect=expect,
        )

    def dispatch(
        self, control: Path, packet_path: Path, *, ticket_id: str, attempt_id: str,
        revision: int, expect: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        return run(
            "dispatch", "--control-root", str(control), "--run-id", RUN_ID,
            "--owner-token", OWNER, "--revision", str(revision), "--ticket-id", ticket_id,
            "--attempt-id", attempt_id, "--lease-id", f"L-{attempt_id}",
            "--route-id", f"route-{attempt_id}", "--packet", str(packet_path), expect=expect,
        )

    def test_three_current_findings_share_one_authorization_and_one_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths, subjects = seed_repair_fixture(
                root, [("T-1", "F-1", "current"), ("T-1", "F-2", "current"), ("T-1", "F-3", "current")],
            )
            subject = subjects[("T-1", "current")]
            plan = grouped_plan(["F-3", "F-1", "F-2"], subject["review"])
            plan_file = root / "repair-plan.json"
            write_json(plan_file, plan)
            packet = repair_packet(root, repo, "T-1", "A-repair", subject["sha"], plan)
            self.authorize(control, ticket_id="T-1", authorization_id="AUTH-1", plan_path=plan_file, packet_path=packet)

            state, _ = ledger.load_state(paths)
            authorization = next(item for item in state["decisions"] if item["id"] == "AUTH-1")
            self.assertEqual("authorized", authorization["status"])
            canonical_plan = ledger.stored_payload(paths, authorization["repair_plan_ref"], "repair plan")
            self.assertEqual(["F-1", "F-2", "F-3"], canonical_plan["finding_refs"])
            self.assertEqual(subject["worker"], canonical_plan["source_attempt_ref"])
            self.assertEqual(subject["candidate"], canonical_plan["source_candidate_ref"])
            self.assertEqual(subject["sha"], canonical_plan["source_candidate_sha"])
            self.assertEqual("READY", next(item for item in state["tickets"] if item["id"] == "T-1")["state"])

            self.dispatch(control, packet, ticket_id="T-1", attempt_id="A-repair", revision=3)
            dispatched, _ = ledger.load_state(paths)
            attempt = ledger.attempt_by_id(dispatched, "A-repair")
            self.assertEqual(["F-1", "F-2", "F-3"], attempt["repair_contract"]["finding_refs"])
            self.assertEqual("AUTH-1", attempt["repair_authorization_ref"])
            self.assertEqual("consumed", next(item for item in dispatched["decisions"] if item["id"] == "AUTH-1")["status"])
            self.assertEqual("PREPARED", attempt["state"])

    def test_mixed_ticket_or_candidate_findings_reject_without_mutation(self) -> None:
        cases = [
            ([ ("T-1", "F-1", "current"), ("T-2", "F-2", "current") ], ["F-1", "F-2"], "T-1", "current"),
            ([ ("T-1", "F-old", "old"), ("T-1", "F-current", "current") ], ["F-old", "F-current"], "T-1", "current"),
        ]
        for index, (seed, refs, ticket_id, generation) in enumerate(cases):
            with self.subTest(case=index), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                control, repo, paths, subjects = seed_repair_fixture(root, seed)
                subject = subjects[(ticket_id, generation)]
                plan = grouped_plan(refs, subject["review"])
                plan_file = root / "repair-plan.json"
                write_json(plan_file, plan)
                packet = repair_packet(root, repo, ticket_id, "A-repair", subject["sha"], plan)
                before = paths["ledger"].read_bytes()
                self.authorize(
                    control, ticket_id=ticket_id, authorization_id="AUTH-mixed", plan_path=plan_file,
                    packet_path=packet, expect=2,
                )
                self.assertEqual(before, paths["ledger"].read_bytes())
                self.assertFalse(any(item.get("id") == "AUTH-mixed" for item in ledger.load_state(paths)[0]["decisions"]))

    def test_review_source_is_normalized_to_current_worker_and_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths, subjects = seed_repair_fixture(root, [("T-1", "F-1", "current")])
            subject = subjects[("T-1", "current")]
            plan = grouped_plan(["F-1"], subject["review"])
            plan_file = root / "repair-plan.json"
            write_json(plan_file, plan)
            packet = repair_packet(root, repo, "T-1", "A-repair", subject["sha"], plan)
            self.authorize(control, ticket_id="T-1", authorization_id="AUTH-normalized", plan_path=plan_file, packet_path=packet)
            state, _ = ledger.load_state(paths)
            auth = next(item for item in state["decisions"] if item["id"] == "AUTH-normalized")
            canonical_plan = ledger.stored_payload(paths, auth["repair_plan_ref"], "repair plan")
            self.assertEqual(subject["worker"], canonical_plan["source_attempt_ref"])
            self.assertEqual(subject["candidate"], canonical_plan["source_candidate_ref"])
            self.assertEqual(subject["sha"], canonical_plan["source_candidate_sha"])

    def test_stale_forked_base_and_source_reject_at_authorize(self) -> None:
        for mutation in ("stale_base", "stale_source", "forked_source"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture = (
                    [("T-1", "F-1", "current"), ("T-2", "F-2", "foreign")]
                    if mutation == "forked_source"
                    else [("T-1", "F-1", "old"), ("T-1", "F-2", "current")]
                )
                control, repo, paths, subjects = seed_repair_fixture(root, fixture)
                current = subjects[("T-1", "current")]
                selected_refs = ["F-1"] if mutation == "forked_source" else ["F-2"]
                plan = grouped_plan(selected_refs, current["review"])
                if mutation == "stale_source":
                    plan["source_attempt_ref"] = subjects[("T-1", "old")]["review"]
                elif mutation == "forked_source":
                    # A same-stage review from another ticket cannot source this ticket's repair.
                    plan["source_attempt_ref"] = subjects[("T-2", "foreign")]["review"]
                if mutation == "stale_base":
                    candidate_sha = "f" * 40
                else:
                    candidate_sha = current["sha"]
                plan_file = root / "repair-plan.json"
                write_json(plan_file, plan)
                packet = repair_packet(root, repo, "T-1", "A-repair", candidate_sha, plan)
                before = paths["ledger"].read_bytes()
                self.authorize(
                    control, ticket_id="T-1", authorization_id="AUTH-stale", plan_path=plan_file,
                    packet_path=packet, expect=2,
                )
                self.assertEqual(before, paths["ledger"].read_bytes())

    def test_allow_deny_overlap_rejects_at_authorize_without_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths, subjects = seed_repair_fixture(root, [("T-1", "F-1", "current")])
            subject = subjects[("T-1", "current")]
            plan = grouped_plan(["F-1"], subject["review"])
            plan_file = root / "repair-plan.json"
            write_json(plan_file, plan)
            packet = repair_packet(
                root, repo, "T-1", "A-repair", subject["sha"], plan,
                deny=["app.txt"],
            )
            before = paths["ledger"].read_bytes()
            self.authorize(control, ticket_id="T-1", authorization_id="AUTH-overlap", plan_path=plan_file, packet_path=packet, expect=2)
            self.assertEqual(before, paths["ledger"].read_bytes())

    def test_authorized_plan_dispatches_only_unchanged_packet_and_rejects_packet_drift(self) -> None:
        for drift in (False, True):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                control, repo, paths, subjects = seed_repair_fixture(root, [("T-1", "F-1", "current")])
                subject = subjects[("T-1", "current")]
                plan = grouped_plan(["F-1"], subject["review"])
                plan_file = root / "repair-plan.json"
                write_json(plan_file, plan)
                authorized_packet = repair_packet(root, repo, "T-1", "A-repair", subject["sha"], plan)
                self.authorize(control, ticket_id="T-1", authorization_id="AUTH-packet", plan_path=plan_file, packet_path=authorized_packet)
                dispatch_packet = authorized_packet
                if drift:
                    changed = copy.deepcopy(plan)
                    changed["causal_change"] = "different mutation after approval"
                    dispatch_packet = repair_packet(root, repo, "T-1", "A-repair", subject["sha"], changed)
                before = paths["ledger"].read_bytes()
                if drift:
                    self.dispatch(control, dispatch_packet, ticket_id="T-1", attempt_id="A-repair", revision=3, expect=2)
                    self.assertEqual(before, paths["ledger"].read_bytes())
                    self.assertFalse(any(item.get("id") == "A-repair" for item in ledger.load_state(paths)[0]["attempts"]))
                else:
                    self.dispatch(control, dispatch_packet, ticket_id="T-1", attempt_id="A-repair", revision=3)
                    state, _ = ledger.load_state(paths)
                    self.assertEqual("A-repair", next(item for item in state["decisions"] if item["id"] == "AUTH-packet")["consumed_by"])

    def test_exact_authorize_retry_is_idempotent_and_changed_plan_requires_supersession(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths, subjects = seed_repair_fixture(root, [("T-1", "F-1", "current")])
            subject = subjects[("T-1", "current")]
            plan = grouped_plan(["F-1"], subject["review"])
            plan_file = root / "repair-plan.json"
            write_json(plan_file, plan)
            packet = repair_packet(root, repo, "T-1", "A-repair", subject["sha"], plan)
            self.authorize(control, ticket_id="T-1", authorization_id="AUTH-retry", plan_path=plan_file, packet_path=packet)
            after_first = paths["ledger"].read_bytes()
            retry = self.authorize(
                control, ticket_id="T-1", authorization_id="AUTH-retry", plan_path=plan_file,
                packet_path=packet, revision=2,
            )
            self.assertTrue(json.loads(retry.stdout).get("idempotent"))
            self.assertEqual(after_first, paths["ledger"].read_bytes())
            original = next(item for item in ledger.load_state(paths)[0]["decisions"] if item["id"] == "AUTH-retry")

            changed = grouped_plan(["F-1"], subject["review"])
            changed["causal_change"] = "meaningfully different causal change"
            changed_file = root / "changed-plan.json"
            write_json(changed_file, changed)
            changed_packet = repair_packet(root, repo, "T-1", "A-repair-2", subject["sha"], changed)
            self.authorize(
                control, ticket_id="T-1", authorization_id="AUTH-replacement", plan_path=changed_file,
                packet_path=changed_packet, revision=3,
            )
            state, _ = ledger.load_state(paths)
            prior = next(item for item in state["decisions"] if item["id"] == "AUTH-retry")
            replacement = next(item for item in state["decisions"] if item["id"] == "AUTH-replacement")
            self.assertEqual("superseded", prior["status"])
            self.assertEqual("AUTH-replacement", prior["superseded_by"])
            self.assertEqual(original["repair_plan_ref"], prior["repair_plan_ref"])
            self.assertEqual(original["attempt_plan_ref"], prior["attempt_plan_ref"])
            self.assertEqual(original["evidence_refs"], prior["evidence_refs"])
            self.assertEqual("authorized", replacement["status"])
            self.assertEqual(["AUTH-retry"], replacement["supersedes"])

    def test_consumed_authorization_cannot_be_revoked_or_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths, subjects = seed_repair_fixture(root, [("T-1", "F-1", "current")])
            subject = subjects[("T-1", "current")]
            plan = grouped_plan(["F-1"], subject["review"])
            plan_file = root / "repair-plan.json"
            write_json(plan_file, plan)
            packet = repair_packet(root, repo, "T-1", "A-repair", subject["sha"], plan)
            self.authorize(control, ticket_id="T-1", authorization_id="AUTH-used", plan_path=plan_file, packet_path=packet)
            self.dispatch(control, packet, ticket_id="T-1", attempt_id="A-repair", revision=3)
            after_dispatch = paths["ledger"].read_bytes()
            revoked = run(
                "revoke-repair", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "4", "--authorization-id", "AUTH-used",
                "--revocation-id", "REVOKE-used", "--reason", "attempt already started", expect=2,
            )
            self.assertIn("unused authorized", revoked.stderr.lower())
            self.assertEqual(after_dispatch, paths["ledger"].read_bytes())
            state, _ = ledger.load_state(paths)
            self.assertEqual("consumed", next(item for item in state["decisions"] if item["id"] == "AUTH-used")["status"])
            self.assertEqual(["F-1"], ledger.attempt_by_id(state, "A-repair")["repair_contract"]["finding_refs"])
            with self.assertRaises(ledger.LedgerError):
                ledger.validate_repair_authorization(
                    paths, state, "T-1", json.loads(packet.read_text(encoding="utf-8"))["repair"],
                )

    def test_wrong_ticket_worker_return_is_rejected_without_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths, subjects = seed_repair_fixture(root, [("T-1", "F-1", "current")])
            subject = subjects[("T-1", "current")]
            plan = grouped_plan(["F-1"], subject["review"])
            plan_file = root / "repair-plan.json"
            write_json(plan_file, plan)
            packet = repair_packet(root, repo, "T-1", "A-repair", subject["sha"], plan)
            self.authorize(control, ticket_id="T-1", authorization_id="AUTH-return", plan_path=plan_file, packet_path=packet)
            self.dispatch(control, packet, ticket_id="T-1", attempt_id="A-repair", revision=3)
            state, _ = ledger.load_state(paths)
            packet_hash = ledger.attempt_by_id(state, "A-repair")["packet_hash"]
            bad_return = {
                "identity": {
                    "run_id": RUN_ID, "ticket_id": "FOREIGN-TICKET", "attempt_id": "A-repair",
                    "packet_hash": packet_hash, "epoch": 0,
                },
                "status": "DONE", "result": "foreign ticket return", "files": [],
                "checks": [{"check_id": "oracle", "outcome": "pass", "actual": "ok", "evidence_ref": "EV-1"}],
                "criteria": [{"criterion_id": "C-1", "outcome": "satisfied", "evidence_refs": ["EV-1"]}],
            }
            return_file = paths["scratch"] / "A-repair" / "return.json"
            write_json(return_file, bad_return)
            before = paths["ledger"].read_bytes()
            rejected = run(
                "ingest-return", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "4", "--attempt-id", "A-repair",
                "--return-file", str(return_file), expect=2,
            )
            self.assertIn("ticket", rejected.stderr.lower())
            self.assertEqual(before, paths["ledger"].read_bytes())
            after, _ = ledger.load_state(paths)
            self.assertEqual("PREPARED", ledger.attempt_by_id(after, "A-repair")["state"])
            self.assertIsNone(ledger.attempt_by_id(after, "A-repair")["return_ref"])


if __name__ == "__main__":
    unittest.main()
