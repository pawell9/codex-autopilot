from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools import dashboard, ledger


ROOT = Path(__file__).resolve().parents[1]
CLI = ["python3", str(ROOT / "tools" / "ledger.py")]
RUN_ID = "phase-b-run"
OWNER = "owner-a"
TICKET_ID = "T-1"


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([*CLI, *args], text=True, capture_output=True)
    if result.returncode != expect:
        raise AssertionError(f"expected {expect}, got {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def write_json(path: Path, value: Any) -> None:
    ledger.atomic_write(path, ledger.canonical_bytes(value))


def init_run(root: Path) -> tuple[Path, Path, dict[str, Path]]:
    control, repo = root / "control", root / "repo"
    control.mkdir()
    repo.mkdir()
    run("init", "--control-root", str(control), "--repo-root", str(repo), "--run-id", RUN_ID, "--owner-token", OWNER)
    return control, repo, ledger.paths(control, RUN_ID)


def seed_ready_ticket(paths: dict[str, Path], repo: Path) -> None:
    state, previous = ledger.load_state(paths)
    state.setdefault("attempts", [])
    state.setdefault("findings", [])
    state.setdefault("issues", [])
    state.setdefault("reviews", [])
    state.setdefault("candidates", [])
    state["tickets"] = [{
        "id": TICKET_ID, "goal_ref": "G-1", "criterion_refs": [], "contract_refs": [],
        "dependency_refs": [], "state": "READY", "complexity": "bounded", "risk": "routine",
        "zone": [{"path": "app.txt", "operations": ["modify"]}], "current_attempt": None,
        "current_worker_attempt": None, "last_worker_attempt": None, "current_candidate": None,
        "replacement_refs": [],
    }]
    state["lifecycle"] = {
        "phase": "EXECUTE", "control": "ACTIVE", "reason": None, "issue_refs": [],
        "stop_target": None,
        "next_action": {"kind": "dispatch", "subject_refs": [TICKET_ID], "preconditions": [], "read_refs": []},
    }
    state["revision"] = 1
    state["previous_publication_hash"] = ledger.sha256_bytes(previous)
    state["repository"].update({"checkout": str(repo), "branch": "main"})
    ledger.validate_ledger(state)
    ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))


def install_execution_design(paths: dict[str, Path], repo: Path) -> None:
    """Upgrade a focused synthetic dispatch fixture to a current published mandate."""
    state, previous = ledger.load_state(paths)
    intent_path = paths["run"] / "fixture-intent.md"
    design_path = paths["run"] / "fixture-design.md"
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
    state["repository"]["initial_head"] = "a" * 40
    bundle_raw = ledger.canonical_bytes({"fixture": "Phase B execution binding", "intent_hash": intent_hash, "design_hash": design_hash})
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
    state["previous_publication_hash"] = ledger.sha256_bytes(previous)
    ledger.validate_ledger(state)
    ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))


def worker_packet(root: Path, repo: Path, attempt_id: str = "A-1") -> Path:
    paths = ledger.paths(root / "control", RUN_ID)
    state, _ = ledger.load_state(paths)
    ticket = next(item for item in state["tickets"] if item["id"] == TICKET_ID)
    base = ledger.current_candidate_record(state, ticket)
    base_sha = base["sha"] if base is not None else state["repository"].get("initial_head")
    identity = {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": attempt_id, "epoch": 0}
    intent_fields: dict[str, str] = {}
    if state.get("design_publication"):
        intent = ledger.current_intent_binding(state)
        publication = state["design_publication"]
        identity.update({
            "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
            "intent_document_hash": intent["document_hash"],
            "design_publication_ref": publication["id"], "design_publication_hash": publication["publication_hash"],
            "design_publication_revision": publication["published_revision"],
            "contract_refs": sorted(ticket.get("contract_refs", [])),
        })
        intent_fields = {
            "intent_revision": intent["revision"], "intent_document_ref": intent["document_ref"],
            "intent_document_hash": intent["document_hash"],
        }
    packet = {
        "identity": identity,
        "kind": "worker", "mode": "implement", "goal": "phase B transition regression",
        "acceptance": [{"criterion_id": "C-1"}],
        "workspace": {"root": str(repo), "expected_base": base_sha},
        "write": {"allow": [{"path": "app.txt", "operations": ["modify"]}]},
        "verification": [{"check_id": "oracle", "required": True}],
        "risk": {"level": "routine"}, "context": [{"ref": "contracts/worker.md"}],
        "return_target": {"path": "return.json"},
        **intent_fields,
    }
    path = root / f"{attempt_id}.json"
    write_json(path, packet)
    return path


def write_state(paths: dict[str, Path], state: dict[str, Any]) -> None:
    ledger.refresh_control_projection(state)
    ledger.validate_ledger(state)
    ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))


def record_runtime_event(
    paths: dict[str, Path], attempt_id: str, event: str = "stop", *,
    event_id: str | None = None, instance: str | None = "runtime-fixture",
) -> dict[str, Any]:
    """Record exact synthetic runtime evidence through the public owner CLI."""
    state, _ = ledger.load_state(paths)
    attempt = ledger.attempt_by_id(state, attempt_id)
    event_id = event_id or f"OBS-{attempt_id}-{event.upper()}"
    receipt = {
        "kind": "runtime_observation", "event_id": event_id, "event": event,
        "run_id": state["run_id"], "attempt_id": attempt_id, "epoch": attempt["epoch"],
        "packet_hash": attempt["packet_hash"], "spawn_request_id": attempt["runtime"]["spawn_request_id"],
        "runtime_instance_id": instance if event != "not_started" else None,
        "observed_at": "2026-09-18T12:00:00Z", "observer": "runtime-adapter-test",
        "runtime_build": "fixture-1", "return_hash": None,
        "coverage": {"scope": "test process tree", "descendant_writers": "included" if event == "stop" else "not_applicable"},
    }
    event_path = paths["run"] / f"{event_id}.json"
    write_json(event_path, receipt)
    run(
        "observe-runtime", "--control-root", str(paths["root"]),
        "--run-id", state["run_id"], "--owner-token", state["owner"]["token"],
        "--revision", str(state["revision"]), "--attempt-id", attempt_id,
        "--event", event, "--event-id", event_id, "--event-file", str(event_path),
    )
    return receipt


def set_terminal_control(state: dict[str, Any], control: str) -> None:
    state["lifecycle"]["control"] = control
    state["lifecycle"]["next_action"] = {
        "kind": f"terminal_{control.lower()}", "subject_refs": [], "preconditions": [], "read_refs": [],
    }
    if control == "ACCEPTED":
        state["acceptance"] = [{
            "round": 1, "intent_revision": "fixture-v1", "candidate_fingerprint": "a" * 40,
            "verdict": "PASS", "transport": "automatic", "invalidated_by": [],
        }]


def attempt_record(
    attempt_id: str, *, kind: str, candidate_sha: str | None, return_ref: str | None = None,
    review_result: str | None = None,
) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "id": attempt_id, "kind": kind, "mode": "change" if kind == "review" else "implement",
        "subject_ref": TICKET_ID, "packet_ref": "objects/" + "1" * 64, "packet_hash": "2" * 64,
        "epoch": 0, "state": "RETURNED", "lease": {"id": f"L-{attempt_id}", "state": "released", "zone": []},
        "route_ref": None, "checkout": None, "base_sha": None, "candidate_sha": candidate_sha,
        "candidate_tree_sha": "3" * 40 if candidate_sha else None, "return_ref": return_ref,
        "finding_refs": [], "subject_fingerprint": candidate_sha, "review_result": review_result,
    }
    return attempt


def integrated_review_fixture(
    paths: dict[str, Path], repo: Path, *, quality: str = "DONE", latest_attempt_drift: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state, _ = ledger.load_state(paths)
    ticket = state["tickets"][0]
    sha = "4" * 40
    producer = attempt_record("W-CANDIDATE", kind="worker", candidate_sha=sha)
    producer.update({"candidate_tree_sha": "5" * 40, "base_sha": "6" * 40, "checkout": str(repo)})
    if quality == "CONTINUATION":
        producer.update({"continuation_ref": "objects/" + "a" * 64, "continuation_authorization_ref": "DEC-CONTINUATION"})
    state["attempts"].append(producer)
    ledger.initialize_attempt_runtime(state["run_id"], producer)
    candidate = ledger.publish_candidate_projection(state, ticket, producer, quality=quality)
    if latest_attempt_drift:
        drift = attempt_record("W-NO-CANDIDATE", kind="worker", candidate_sha=None)
        state["attempts"].append(drift)
        ticket.update({"current_attempt": drift["id"], "last_worker_attempt": drift["id"]})
    else:
        ticket.update({"current_attempt": producer["id"], "last_worker_attempt": producer["id"]})
    ticket.update({"state": "INTEGRATED", "current_worker_attempt": None})
    reviewer = attempt_record(
        "RV-INTEGRATE", kind="review", candidate_sha=sha, return_ref="objects/" + "b" * 64,
        review_result="PASS",
    )
    ledger.initialize_attempt_runtime(state["run_id"], reviewer)
    state["attempts"].append(reviewer)
    state["reviews"] = [{
        "id": "REVIEW-PASS", "mandate": "Independent candidate review", "subject_fingerprint": sha,
        "verdict": "PASS", "return_ref": "objects/" + "b" * 64, "finding_refs": [],
    }]
    return state, candidate


class PhaseBProjectionAndTransitionTests(unittest.TestCase):
    def test_current_candidate_is_independent_of_latest_worker_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            ticket = state["tickets"][0]
            candidate_attempt = {
                "id": "A-DONE", "kind": "worker", "mode": "implement", "subject_ref": TICKET_ID,
                "packet_ref": "objects/" + "1" * 64, "packet_hash": "2" * 64, "epoch": 0,
                "state": "RETURNED", "lease": {"id": "L-DONE", "state": "released", "zone": []},
                "route_ref": "route-DONE", "checkout": str(repo), "base_sha": "3" * 40,
                "candidate_sha": "4" * 40, "candidate_tree_sha": "5" * 40, "return_ref": None,
                "finding_refs": [],
            }
            state["attempts"].append(candidate_attempt)
            published = ledger.publish_candidate_projection(state, ticket, candidate_attempt, quality="DONE")
            ticket["current_worker_attempt"] = None

            for index, (attempt_id, outcome) in enumerate((
                ("A-FAILED", "FAILED"), ("A-BLOCKED", "BLOCKED"), ("A-HANDOFF", "HANDOFF"),
            )):
                packet_hash = str(index + 6) * 64
                returned = {
                    "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": attempt_id,
                                 "packet_hash": packet_hash, "epoch": 0},
                    "status": outcome, "result": f"terminal {outcome.lower()} without candidate", "files": [],
                    "checks": [{"check_id": "oracle", "outcome": "fail", "actual": "no candidate",
                                "evidence_ref": f"EV-{attempt_id}"}],
                    "criteria": [{"criterion_id": "C-1", "outcome": "unsatisfied",
                                  "evidence_refs": [f"EV-{attempt_id}"]}],
                    "issues": [{"cause": "implementation", "impact": "blocking", "expected": "candidate",
                                "actual": outcome, "affected_refs": [TICKET_ID]}],
                    "handoff": {"safe_partial_fingerprint": {}, "completed": [], "remaining": ["candidate"]},
                }
                return_ref = f"objects/{ledger.object_store(paths, ledger.canonical_bytes(returned))}"
                latest = {
                    "id": attempt_id, "kind": "worker", "mode": "implement", "subject_ref": TICKET_ID,
                    "packet_ref": "objects/" + "8" * 64, "packet_hash": packet_hash, "epoch": 0,
                    "state": "RETURNED", "lease": {"id": f"L-{attempt_id}", "state": "released", "zone": []},
                    "route_ref": f"route-{attempt_id}", "checkout": str(repo), "base_sha": "4" * 40,
                    "candidate_sha": None, "candidate_tree_sha": None, "return_ref": return_ref,
                    "finding_refs": [],
                }
                state["attempts"].append(latest)
                ticket["last_worker_attempt"] = attempt_id
                ticket["current_attempt"] = attempt_id
                self.assertEqual("candidate-A-DONE", ledger.current_candidate_record(state, ticket)["id"])
                self.assertEqual(attempt_id, ticket["last_worker_attempt"])
                self.assertIsNone(ticket["current_worker_attempt"])
                self.assertNotEqual(ticket["current_candidate"], ticket["last_worker_attempt"])
                self.assertEqual("A-DONE", published["producer_attempt_ref"])

    def test_ingested_no_candidate_work_preserves_explicit_current_candidate(self) -> None:
        for outcome in ("BLOCKED", "FAILED", "HANDOFF"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                control, repo, paths = init_run(root)
                seed_ready_ticket(paths, repo)
                install_execution_design(paths, repo)
                state, _ = ledger.load_state(paths)
                ticket = state["tickets"][0]
                prior = attempt_record("W-PRIOR", kind="worker", candidate_sha="4" * 40)
                prior.update({"candidate_tree_sha": "5" * 40, "base_sha": "6" * 40,
                              "checkout": str(repo), "finding_refs": []})
                state["attempts"].append(prior)
                ledger.publish_candidate_projection(state, ticket, prior, quality="DONE")
                prior_candidate_id = ticket["current_candidate"]
                write_state(paths, state)

                packet = worker_packet(root, repo, attempt_id=f"A-{outcome}")
                run(
                    "dispatch", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                    "--revision", str(state["revision"]), "--ticket-id", TICKET_ID, "--attempt-id", f"A-{outcome}",
                    "--lease-id", f"L-{outcome}", "--route-id", f"route-{outcome}", "--packet", str(packet),
                )
                dispatched, _ = ledger.load_state(paths)
                dispatched_attempt = ledger.attempt_by_id(dispatched, f"A-{outcome}")
                returned = {
                    "identity": {**copy.deepcopy(json.loads(packet.read_text(encoding="utf-8"))["identity"]),
                                 "packet_hash": dispatched_attempt["packet_hash"]},
                    "status": outcome, "result": f"{outcome} without a new candidate", "files": [],
                    "checks": [{"check_id": "oracle", "outcome": "fail", "actual": "no candidate",
                                "evidence_ref": f"EV-{outcome}"}],
                    "criteria": [{"criterion_id": "C-1", "outcome": "unsatisfied",
                                  "evidence_refs": [f"EV-{outcome}"]}],
                    "issues": [{
                        "type": "no_candidate_regression", "cause": "environment", "impact": "blocking",
                        "affected_refs": [TICKET_ID], "expected": "candidate produced", "actual": outcome,
                        "disposition": "Keep the previous explicit candidate available for recovery.",
                        "resolution_condition": "A later verified candidate supersedes the prior candidate.",
                    }],
                }
                if outcome == "HANDOFF":
                    returned["handoff"] = {
                        "safe_partial_fingerprint": {}, "completed": [], "remaining": ["candidate"],
                    }
                inbox = paths["scratch"] / f"A-{outcome}" / "return.json"
                write_json(inbox, returned)
                run(
                    "ingest-return", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                    "--revision", str(dispatched["revision"]), "--attempt-id", f"A-{outcome}",
                    "--return-file", str(inbox), "--kind", "worker",
                )

                final, _ = ledger.load_state(paths)
                final_ticket = next(item for item in final["tickets"] if item["id"] == TICKET_ID)
                self.assertEqual(prior_candidate_id, final_ticket["current_candidate"])
                self.assertEqual("W-PRIOR", ledger.current_candidate_record(final, final_ticket)["producer_attempt_ref"])
                self.assertEqual(f"A-{outcome}", final_ticket["last_worker_attempt"])
                self.assertEqual(f"A-{outcome}", final_ticket["current_attempt"])
                self.assertIsNone(final_ticket["current_worker_attempt"])
                self.assertNotEqual(final_ticket["current_candidate"], final_ticket["last_worker_attempt"])

    def test_replacement_ticket_inherits_only_exact_contract_bound_stopped_checkpoint(self) -> None:
        checkpoint = "c" * 40
        state = {
            "repository": {"initial_head": "f" * 40},
            "tickets": [{"id": "T-OLD", "current_candidate": "C-OLD"}],
            "candidates": [{
                "id": "C-OLD", "ticket_ref": "T-OLD", "producer_attempt_ref": "W-OLD",
                "sha": checkpoint, "tree_sha": "d" * 40, "quality": "DONE",
                "superseded_by": None,
            }],
            "attempts": [{
                "id": "W-OLD", "state": "RETURNED", "candidate_sha": checkpoint,
                "candidate_tree_sha": "d" * 40, "candidate_proof_ref": "objects/" + "e" * 64,
                "lease": {"state": "released"}, "runtime": {"liveness": "stopped"},
            }],
            "contracts": [{
                "id": "CT-BASE", "implementation_availability": "available",
                "implementation_availability_evidence_refs": [f"checkpoint:{checkpoint}"],
            }],
        }
        ticket = {
            "id": "T-NEW", "current_candidate": None, "replacement_refs": ["T-OLD"],
            "contract_refs": ["CT-BASE"],
        }
        self.assertEqual(checkpoint, ledger.execution_base_for_ticket(state, ticket))

        state["tickets"].append(ticket)
        ticket["current_candidate"] = "C-NEW"
        state["candidates"][0]["superseded_by"] = "C-NEW"
        state["candidates"].append({
            "id": "C-NEW", "ticket_ref": "T-NEW", "producer_attempt_ref": "W-NEW",
            "sha": "a" * 40, "tree_sha": "b" * 40, "quality": "DONE",
            "superseded_by": None,
        })
        self.assertEqual(checkpoint, ledger.replacement_checkpoint_for_ticket(state, ticket))
        ticket["current_candidate"] = None
        state["candidates"][0]["superseded_by"] = None
        state["candidates"].pop()
        state["tickets"].pop()

        state["attempts"][0]["runtime"]["liveness"] = "running"
        with self.assertRaisesRegex(ledger.LedgerError, "missing or ambiguous"):
            ledger.execution_base_for_ticket(state, ticket)
        state["attempts"][0]["runtime"]["liveness"] = "stopped"
        state["contracts"][0]["implementation_availability_evidence_refs"] = []
        with self.assertRaisesRegex(ledger.LedgerError, "lacks an exact available checkpoint"):
            ledger.execution_base_for_ticket(state, ticket)

    def test_finding_projection_separates_current_history_binding_resolution_and_supersession(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            ticket = state["tickets"][0]
            state.setdefault("candidates", [])
            old_worker = attempt_record("W-OLD", kind="worker", candidate_sha="4" * 40)
            old_worker.update({"candidate_tree_sha": "5" * 40, "base_sha": "6" * 40})
            current_worker = attempt_record("W-CURRENT", kind="worker", candidate_sha="7" * 40)
            current_worker.update({"candidate_tree_sha": "8" * 40, "base_sha": "4" * 40})
            state["attempts"].extend([old_worker, current_worker])
            ledger.publish_candidate_projection(state, ticket, old_worker, quality="DONE")
            ledger.publish_candidate_projection(state, ticket, current_worker, quality="DONE")
            current_candidate = ledger.current_candidate_record(state, ticket)

            review_specs = (
                ("RV-CURRENT", current_candidate["sha"], "BLOCK", None),
                ("RV-SUPERSEDED", "4" * 40, "BLOCK", None),
                ("RV-HISTORICAL", "9" * 40, "BLOCK", None),
                ("RV-UNBOUND", None, "BLOCK", None),
                ("RV-PASS", current_candidate["sha"], "PASS", "objects/" + "a" * 64),
            )
            state["attempts"].extend(
                attempt_record(ref, kind="review", candidate_sha=candidate, review_result=verdict, return_ref=return_ref)
                for ref, candidate, verdict, return_ref in review_specs
            )
            state["reviews"] = [{
                "id": "RV-PASS", "mandate": "Verify the same candidate after correction.",
                "subject_fingerprint": current_candidate["sha"], "verdict": "PASS",
                "return_ref": "objects/" + "a" * 64, "finding_refs": ["F-RESOLVED"], "accepted": True,
                "finding_resolution": [{
                    "finding_ref": "F-RESOLVED", "candidate_ref": current_candidate["id"],
                    "evidence_refs": ["EV-RESOLVED"], "reason": "Exact linked PASS resolution.",
                }],
            }, {
                "id": "RV-UNACCEPTED-PASS", "mandate": "A PASS not accepted as authoritative.",
                "subject_fingerprint": current_candidate["sha"], "verdict": "PASS",
                "return_ref": "objects/" + "b" * 64, "finding_refs": ["F-CURRENT"], "accepted": False,
            }]
            state["decisions"] = [{
                "id": "DEC-UNACCEPTED", "type": "finding_resolution", "status": "accepted",
                "decision": "RESOLVED", "reason": "Cited PASS lacks authoritative acceptance.",
                "candidate_ref": current_candidate["id"],
                "evidence_refs": ["RV-UNACCEPTED-PASS", "EV-UNACCEPTED"], "affected_refs": ["F-CURRENT"],
                "introduced_revision": "2",
            }]
            state["findings"] = [
                {"id": "F-CURRENT", "axis": "correctness", "impact": "blocking", "claim": "current defect",
                 "expected": "fixed", "actual": "broken", "evidence": "EV-1", "affected_refs": [TICKET_ID],
                 "source_ref": "RV-CURRENT", "invalidated_by": []},
                {"id": "F-SUPERSEDED", "axis": "correctness", "impact": "blocking", "claim": "old candidate defect",
                 "expected": "fixed", "actual": "broken", "evidence": "EV-2", "affected_refs": [TICKET_ID],
                 "source_ref": "RV-SUPERSEDED", "invalidated_by": []},
                {"id": "F-HISTORICAL", "axis": "correctness", "impact": "blocking", "claim": "legacy defect",
                 "expected": "fixed", "actual": "broken", "evidence": "EV-3", "affected_refs": [TICKET_ID],
                 "source_ref": "RV-HISTORICAL", "invalidated_by": []},
                {"id": "F-UNBOUND", "axis": "correctness", "impact": "blocking", "claim": "unbound defect",
                 "expected": "fixed", "actual": "broken", "evidence": "EV-4", "affected_refs": [TICKET_ID],
                 "source_ref": "RV-UNBOUND", "invalidated_by": []},
                {"id": "F-RESOLVED", "axis": "correctness", "impact": "blocking", "claim": "resolved defect",
                 "expected": "fixed", "actual": "broken", "evidence": "EV-5", "affected_refs": [TICKET_ID],
                 "source_ref": "RV-CURRENT", "invalidated_by": ["RV-PASS"]},
            ]
            state["issues"] = [
                {"id": f"I-{finding['id']}", "type": "review_finding", "cause": "implementation",
                 "impact": "blocking", "affected_refs": [TICKET_ID], "disposition": "Retain finding mirror.",
                 "finding_ref": finding["id"], "source_ref": finding["source_ref"], "invalidated_by": []}
                for finding in state["findings"]
            ]

            # A passing review and finding.invalidated_by are not themselves a
            # resolution decision. The immutable decision must name one finding.
            unapproved = ledger.finding_obligation_projection(state)
            unapproved_items = {item["finding_ref"]: item for item in unapproved["items"]}
            self.assertEqual("current", unapproved_items["F-RESOLVED"]["status"])
            self.assertEqual("open", unapproved_items["F-RESOLVED"]["verification_obligation"]["status"])
            self.assertEqual("current", unapproved_items["F-CURRENT"]["status"])
            self.assertEqual("open", unapproved_items["F-CURRENT"]["verification_obligation"]["status"])
            state["decisions"].append({
                "id": "DEC-RESOLVE-F-RESOLVED", "type": "finding_resolution", "status": "accepted",
                "decision": "RESOLVED", "reason": "Exact finding verified by PASS review.",
                "candidate_ref": current_candidate["id"],
                "evidence_refs": ["RV-PASS", "EV-RESOLVED"], "affected_refs": ["F-RESOLVED"],
                "introduced_revision": "2",
            })

            projection = ledger.finding_obligation_projection(state)
            items = {item["finding_ref"]: item for item in projection["items"]}
            self.assertEqual("current", items["F-CURRENT"]["status"])
            self.assertEqual("superseded", items["F-SUPERSEDED"]["status"])
            self.assertEqual("historical", items["F-HISTORICAL"]["status"])
            self.assertEqual("unbound", items["F-UNBOUND"]["status"])
            self.assertEqual("resolved", items["F-RESOLVED"]["status"])
            self.assertEqual("current", items["F-CURRENT"]["status"])
            self.assertEqual("open", items["F-SUPERSEDED"]["verification_obligation"]["status"])
            self.assertEqual("open", items["F-HISTORICAL"]["verification_obligation"]["status"])
            self.assertEqual("binding_required", items["F-UNBOUND"]["verification_obligation"]["status"])
            self.assertEqual("closed", items["F-RESOLVED"]["verification_obligation"]["status"])
            self.assertEqual("DEC-RESOLVE-F-RESOLVED", items["F-RESOLVED"]["resolved_by_refs"][0])
            obligations = {item["finding_ref"]: item for item in projection["obligations"]}
            self.assertIn("F-CURRENT", obligations)
            self.assertIn("F-SUPERSEDED", obligations)
            self.assertIn("F-HISTORICAL", obligations)
            self.assertEqual("binding_required", obligations["F-UNBOUND"]["status"])
            self.assertNotIn("F-RESOLVED", obligations)
            mirror_statuses = {item["finding_ref"]: item["status"] for item in projection["mirrored_issues"]}
            self.assertEqual({key: value["status"] for key, value in items.items()}, mirror_statuses)

            # An amendment invalidation consumer closure is different from a
            # review-resolution marker: it makes the old finding historical
            # without rewriting or deleting the immutable finding record.
            state.setdefault("invalidations", []).append({
                "id": "invalidation-AMEND-1",
                "amendment_ref": "AMEND-1",
                "intent_revision": "2",
                "previous_intent_revision": "1",
                "previous_document_ref": "intent-v1",
                "previous_document_hash": "a" * 64,
                "affected_refs": ["intent-v1", "intent-v2"],
                "consumer_refs": ["F-CURRENT"],
                "recorded_at": "2026-09-19T00:00:00Z",
            })
            amended = ledger.finding_obligation_projection(state)
            amended_items = {item["finding_ref"]: item for item in amended["items"]}
            amended_obligations = {item["finding_ref"] for item in amended["obligations"]}
            self.assertEqual("superseded", amended_items["F-CURRENT"]["status"])
            self.assertEqual("history", amended_items["F-CURRENT"]["projection_classification"])
            self.assertEqual("closed", amended_items["F-CURRENT"]["verification_obligation"]["status"])
            self.assertNotIn("F-CURRENT", amended_obligations)

    def test_finding_resolution_requires_review_side_finding_and_candidate_linkage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, candidate = integrated_review_fixture(paths, repo, latest_attempt_drift=False)
            finding_ref = "F-LINKED"
            review = state["reviews"][0]
            review.update({"accepted": True, "finding_refs": [finding_ref]})
            state["findings"] = [{
                "id": finding_ref, "axis": "correctness", "impact": "blocking",
                "claim": "The current candidate has a blocking defect.", "expected": "fixed",
                "actual": "broken", "evidence": "EV-BLOCK", "affected_refs": [TICKET_ID],
                "source_ref": "RV-INTEGRATE", "invalidated_by": [review["id"]],
            }]
            state["decisions"] = [{
                "id": "DEC-RESOLVE-LINKED", "type": "finding_resolution", "status": "accepted",
                "decision": "RESOLVED", "reason": "Accepted passing review cites the exact finding and candidate.",
                "candidate_ref": candidate["id"],
                "evidence_refs": [review["id"], "EV-review"], "affected_refs": [finding_ref], "introduced_revision": "2",
            }]

            # An accepted PASS plus a decision and invalidation marker is not
            # sufficient: the review itself must bind both this finding and
            # the candidate it actually assessed.
            review.pop("finding_resolution", None)
            self.assertEqual("current", ledger.finding_obligation_projection(state)["items"][0]["status"])
            for linked_finding, linked_candidate in (
                ("F-OTHER", candidate["id"]),
                (finding_ref, "candidate-OTHER"),
            ):
                review["finding_resolution"] = [{
                    "finding_ref": linked_finding, "candidate_ref": linked_candidate,
                    "evidence_refs": ["EV-review"], "reason": "Explicit resolution linkage fixture.",
                }]
                projection = ledger.finding_obligation_projection(state)
                self.assertEqual("current", projection["items"][0]["status"])
                self.assertEqual("open", projection["items"][0]["verification_obligation"]["status"])

            review["finding_resolution"] = [{
                "finding_ref": finding_ref, "candidate_ref": candidate["id"],
                "evidence_refs": ["EV-review"], "reason": "Exact candidate-bound finding resolution.",
            }]
            projection = ledger.finding_obligation_projection(state)
            self.assertEqual("resolved", projection["items"][0]["status"])
            self.assertEqual("closed", projection["items"][0]["verification_obligation"]["status"])

    def test_multi_ticket_finding_resolution_only_closes_exact_ticket_candidate_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            ticket1 = state["tickets"][0]
            ticket1["state"] = "INTEGRATED"
            ticket2 = copy.deepcopy(ticket1)
            ticket2.update({"id": "T-2", "state": "CANDIDATE", "current_candidate": None,
                            "current_worker_attempt": None, "last_worker_attempt": None, "current_attempt": None})
            state["tickets"].append(ticket2)

            worker1 = attempt_record("W-T1", kind="worker", candidate_sha="4" * 40)
            worker1.update({"subject_ref": TICKET_ID, "candidate_tree_sha": "5" * 40, "checkout": str(repo)})
            worker2 = attempt_record("W-T2", kind="worker", candidate_sha="6" * 40)
            worker2.update({"subject_ref": "T-2", "candidate_tree_sha": "7" * 40, "checkout": str(repo)})
            state["attempts"].extend([worker1, worker2])
            candidate1 = ledger.publish_candidate_projection(state, ticket1, worker1, quality="DONE")
            candidate2 = ledger.publish_candidate_projection(state, ticket2, worker2, quality="DONE")
            candidate1.update({"review_status": "PASS", "integration_status": "INTEGRATED"})

            source_review = attempt_record(
                "RV-T1-BLOCK", kind="review", candidate_sha=candidate1["sha"],
                review_result="BLOCK", return_ref="objects/" + "a" * 64,
            )
            source_review.update({"subject_ref": TICKET_ID, "finding_refs": ["F-MULTI"]})
            state["attempts"].append(source_review)
            state["findings"] = [{
                "id": "F-MULTI", "axis": "correctness", "impact": "blocking",
                "claim": "Shared finding affects both tickets", "expected": "verified fix per ticket",
                "actual": "unresolved", "evidence": "EV-BLOCK", "affected_refs": [TICKET_ID, "T-2"],
                "source_ref": "RV-T1-BLOCK", "invalidated_by": [],
            }]
            state["issues"] = [{
                "id": "I-F-MULTI", "type": "review_finding", "cause": "implementation",
                "impact": "blocking", "affected_refs": [TICKET_ID, "T-2"],
                "finding_ref": "F-MULTI", "source_ref": "RV-T1-BLOCK", "invalidated_by": [],
            }]
            state["reviews"] = [{
                "id": "RV-T1-PASS", "mandate": "Resolve this exact ticket's current candidate finding",
                "subject_fingerprint": candidate1["sha"], "verdict": "PASS", "accepted": True,
                "return_ref": "objects/" + "b" * 64, "finding_refs": ["F-MULTI"],
                "finding_resolution": [{
                    "finding_ref": "F-MULTI", "candidate_ref": candidate1["id"],
                    "evidence_refs": ["EV-T1-PASS"], "reason": "T1 candidate independently verifies the finding.",
                }],
            }]
            state["decisions"] = [{
                "id": "DEC-RESOLVE-T1", "type": "finding_resolution", "status": "accepted",
                "decision": "RESOLVED", "reason": "T1 candidate independently verifies the finding.",
                "candidate_ref": candidate1["id"], "evidence_refs": ["RV-T1-PASS", "EV-T1-PASS"],
                "affected_refs": ["F-MULTI"], "introduced_revision": "2",
            }]

            projection = ledger.finding_obligation_projection(state)
            finding = next(item for item in projection["items"] if item["finding_ref"] == "F-MULTI")
            self.assertEqual([TICKET_ID], finding["resolved_ticket_refs"])
            self.assertEqual(["T-2"], finding["unresolved_ticket_refs"])
            self.assertEqual("current", finding["status"])
            self.assertEqual("open", finding["verification_obligation"]["status"])
            self.assertEqual([], ledger.open_ticket_finding_obligations(state, TICKET_ID))
            t2_obligations = ledger.open_ticket_finding_obligations(state, "T-2")
            self.assertEqual(["F-MULTI"], [item["finding_ref"] for item in t2_obligations])
            self.assertEqual(["T-2"], t2_obligations[0]["ticket_refs"])
            self.assertTrue(next(item for item in projection["mirrored_issues"] if item["issue_ref"] == "I-F-MULTI")["active"])
            self.assertEqual("candidate-W-T2", candidate2["id"])

    def test_linked_review_verdict_retires_only_after_all_source_findings_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            ticket = state["tickets"][0]
            sha = "4" * 40
            worker = attempt_record("W-CURRENT", kind="worker", candidate_sha=sha)
            worker.update({"candidate_tree_sha": "5" * 40, "checkout": str(repo)})
            ledger.initialize_attempt_runtime(state["run_id"], worker)
            state["attempts"].append(worker)
            candidate = ledger.publish_candidate_projection(state, ticket, worker, quality="DONE")
            ticket["state"] = "CANDIDATE"
            finding_refs = ["F-SOURCE-1", "F-SOURCE-2"]
            source_review = {
                "id": "REV-BLOCK", "mandate": "Source BLOCK review with canonical findings",
                "subject_fingerprint": sha, "verdict": "BLOCK", "accepted": False,
                "return_ref": "objects/" + "a" * 64, "finding_refs": finding_refs,
            }
            state["reviews"] = [source_review]
            state["findings"] = [{
                "id": finding_ref, "axis": "correctness", "impact": "blocking",
                "claim": f"Canonical source finding {index}", "expected": "verified fixed",
                "actual": "not yet verified", "evidence": f"EV-BLOCK-{index}",
                "affected_refs": [TICKET_ID], "source_ref": "REV-BLOCK", "invalidated_by": [],
            } for index, finding_ref in enumerate(finding_refs, start=1)]
            state["issues"] = [{
                "id": "I-LINKED-VERDICT", "type": "review_verdict", "cause": "oracle",
                "impact": "blocking", "affected_refs": [TICKET_ID], "expected": "PASS",
                "actual": "BLOCK", "disposition": "repair or adjudication required",
                "resolution_condition": "all canonical findings from the source review are resolved",
                "source_ref": "REV-BLOCK", "invalidated_by": [],
            }, {
                "id": "I-UNLINKED-VERDICT", "type": "review_verdict", "cause": "oracle",
                "impact": "blocking", "affected_refs": [TICKET_ID], "expected": "PASS",
                "actual": "BLOCK", "disposition": "independent unlinked review verdict remains open",
                "resolution_condition": "an explicit resolution for this review verdict",
                "source_ref": "REV-UNKNOWN", "invalidated_by": [],
            }]
            state["lifecycle"]["issue_refs"] = ["I-LINKED-VERDICT", "I-UNLINKED-VERDICT"]
            write_state(paths, state)
            record_runtime_event(paths, "W-CURRENT", event_id="OBS-W-CURRENT-STOP")
            state, _ = ledger.load_state(paths)

            packet_path = root / "pass-review.packet.json"
            write_json(packet_path, {
                "identity": {"run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": "RV-PASS", "epoch": 0},
                "kind": "review", "mandate": "Resolve the exact candidate-bound findings",
                "subject_fingerprint": sha, "criteria": [{"criterion_id": "C-1"}],
                "axes": ["correctness"], "return_target": {"path": "return.json"},
            })
            run(
                "prepare-review", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--ticket-id", TICKET_ID,
                "--review-attempt-id", "RV-PASS", "--lease-id", "L-RV-PASS", "--packet", str(packet_path),
            )
            prepared, _ = ledger.load_state(paths)
            prepared_review = ledger.attempt_by_id(prepared, "RV-PASS")
            observation_id = "OBS-RV-PASS-NOT-STARTED"
            observation_path = root / f"{observation_id}.json"
            write_json(observation_path, {
                "kind": "runtime_observation", "event_id": observation_id, "event": "not_started",
                "run_id": RUN_ID, "attempt_id": prepared_review["id"], "epoch": prepared_review["epoch"],
                "packet_hash": prepared_review["packet_hash"],
                "spawn_request_id": prepared_review["runtime"]["spawn_request_id"],
                "runtime_instance_id": None, "observed_at": "2026-09-18T12:00:00Z",
                "observer": "runtime-adapter-test", "runtime_build": "fixture-1", "return_hash": None,
                "coverage": {"scope": "review process tree", "descendant_writers": "not_applicable"},
            })
            run(
                "observe-runtime", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(prepared["revision"]),
                "--attempt-id", prepared_review["id"], "--event", "not_started",
                "--event-id", observation_id, "--event-file", str(observation_path),
            )
            before, raw_before = ledger.load_state(paths)
            review_attempt = ledger.attempt_by_id(before, "RV-PASS")
            resolution_entries = [{
                "finding_ref": finding_ref, "candidate_ref": candidate["id"],
                "evidence_refs": ["EV-PASS"],
                "reason": f"Current candidate {candidate['id']} resolves {finding_ref}.",
            } for finding_ref in finding_refs]

            def review_payload(resolutions: list[dict[str, str]]) -> dict[str, Any]:
                identity = {
                    "run_id": RUN_ID, "ticket_id": TICKET_ID, "attempt_id": "RV-PASS",
                    "packet_hash": review_attempt["packet_hash"], "epoch": 0,
                    "source_revision": review_attempt["packet_source_revision"],
                    "registration_revision": review_attempt["packet_registration_revision"],
                    "subject_revision": review_attempt["subject_revision"],
                }
                return {
                    "identity": identity, "subject_fingerprint": sha, "verdict": "PASS",
                    "coverage": [{"criterion_id": "C-1", "outcome": "fulfilled", "evidence_refs": ["EV-PASS"]}],
                    "checks": [{"check_id": "correctness", "axis": "correctness", "outcome": "fulfilled", "actual": "verified", "evidence_ref": "EV-PASS"}],
                    "context_refs": ["independent-review-context"], "findings": [],
                    "finding_resolution": resolutions,
                }

            review_path = paths["scratch"] / "RV-PASS" / "return.json"
            integrity_path = root / "pass-review.integrity.json"
            write_json(review_path, review_payload(resolution_entries[:1]))
            write_json(integrity_path, {
                "status": "PASS", "candidate_fingerprint": sha,
                "ledger_hash": ledger.sha256_bytes(raw_before),
            })
            partial = run(
                "integrate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(before["revision"]), "--attempt-id", "RV-PASS",
                "--review-file", str(review_path), "--integrity-receipt", str(integrity_path),
                "--review-id", "REV-PASS", expect=2,
            )
            self.assertRegex(partial.stderr.lower(), r"finding|obligation|integration is blocked")
            unchanged, raw_unchanged = ledger.load_state(paths)
            self.assertEqual(raw_before, raw_unchanged)
            self.assertEqual("blocking", next(item for item in unchanged["issues"] if item["id"] == "I-LINKED-VERDICT")["impact"])

            write_json(review_path, review_payload(resolution_entries))
            result = json.loads(run(
                "integrate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(before["revision"]), "--attempt-id", "RV-PASS",
                "--review-file", str(review_path), "--integrity-receipt", str(integrity_path),
                "--review-id", "REV-PASS",
            ).stdout)
            final, _ = ledger.load_state(paths)
            issues = {item["id"]: item for item in final["issues"]}
            self.assertTrue(result["integrated"])
            self.assertEqual("advisory", issues["I-LINKED-VERDICT"]["impact"])
            self.assertTrue(issues["I-LINKED-VERDICT"].get("invalidated_by"))
            self.assertEqual("blocking", issues["I-UNLINKED-VERDICT"]["impact"])
            self.assertEqual([], issues["I-UNLINKED-VERDICT"].get("invalidated_by", []))

    def test_recovering_to_active_requires_reconciled_attempts_and_effects(self) -> None:
        for obstruction in ("active_attempt", "quarantined_attempt", "prepared_effect", "uncertain_effect"):
            with self.subTest(obstruction=obstruction), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                control, repo, paths = init_run(root)
                seed_ready_ticket(paths, repo)
                if obstruction in ("active_attempt", "quarantined_attempt"):
                    install_execution_design(paths, repo)
                state, _ = ledger.load_state(paths)
                if obstruction in ("active_attempt", "quarantined_attempt"):
                    packet = worker_packet(root, repo, attempt_id="A-RECOVER")
                    run(
                        "dispatch", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                        "--revision", str(state["revision"]), "--ticket-id", TICKET_ID,
                        "--attempt-id", "A-RECOVER", "--lease-id", "L-RECOVER", "--route-id", "route-RECOVER",
                        "--packet", str(packet),
                    )
                    state, _ = ledger.load_state(paths)
                    if obstruction == "quarantined_attempt":
                        attempt = ledger.attempt_by_id(state, "A-RECOVER")
                        attempt["state"] = "LOST"
                        attempt["lease"]["state"] = "quarantined"
                        ticket = state["tickets"][0]
                        ticket["state"] = "BLOCKED"
                        ticket["current_worker_attempt"] = None
                else:
                    run(
                        "prepare-effect", "--control-root", str(control), "--run-id", RUN_ID,
                        "--owner-token", OWNER, "--revision", str(state["revision"]),
                        "--operation-id", "OP-RECOVER", "--kind", "candidate_commit",
                        "--target", str(repo), "--authority-ref", "AUTH-RECOVER",
                    )
                    state, _ = ledger.load_state(paths)
                    if obstruction == "uncertain_effect":
                        state["operations"][0]["state"] = "uncertain"
                state["lifecycle"]["control"] = "RECOVERING"
                write_state(paths, state)
                before, raw_before = ledger.load_state(paths)

                result = run(
                    "gate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                    "--revision", str(before["revision"]), "--phase", "EXECUTE", "--control", "ACTIVE",
                    "--next-action", "resume_after_reconciliation", expect=2,
                )
                self.assertRegex(result.stderr.lower(), r"attempt|lease|effect|reconcil|stopped")
                after, raw_after = ledger.load_state(paths)
                self.assertEqual(before["revision"], after["revision"])
                self.assertEqual(raw_before, raw_after)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            install_execution_design(paths, repo)
            state, _ = ledger.load_state(paths)
            run(
                "prepare-effect", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(state["revision"]),
                "--operation-id", "OP-RECONCILED", "--kind", "candidate_commit",
                "--target", str(repo), "--authority-ref", "AUTH-RECONCILED",
            )
            state, _ = ledger.load_state(paths)
            run(
                "reconcile-effect", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(state["revision"]),
                "--operation-id", "OP-RECONCILED", "--result", "unchanged",
            )
            state, _ = ledger.load_state(paths)
            state["lifecycle"]["control"] = "RECOVERING"
            write_state(paths, state)
            before, _ = ledger.load_state(paths)
            result = json.loads(run(
                "gate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(before["revision"]), "--phase", "EXECUTE", "--control", "ACTIVE",
                "--next-action", "resume_after_clean_reconciliation",
            ).stdout)
            self.assertEqual("ACTIVE", result["control"])
            final, _ = ledger.load_state(paths)
            self.assertEqual("abandoned", final["operations"][0]["state"])

    def test_derived_next_action_never_waits_on_a_terminal_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            state["attempts"].append(attempt_record("A-RETURNED", kind="worker", candidate_sha=None))
            state["tickets"][0].update({
                "state": "BLOCKED", "current_attempt": "A-RETURNED", "last_worker_attempt": "A-RETURNED",
                "current_worker_attempt": None,
            })
            state["lifecycle"]["control"] = "BLOCKED"
            state["lifecycle"]["next_action"] = {
                "kind": "await_worker_return", "subject_refs": ["A-RETURNED"],
                "preconditions": ["wait for producer"], "read_refs": [],
            }
            # Legacy ledgers may retain a cached await. Without the Phase B marker,
            # sanitize that stale instruction to owner inspection rather than
            # treating it as executable orchestration authority.
            state.pop("candidate_model_version", None)

            derived = ledger.derive_next_action(state)

            self.assertNotEqual("await_worker_return", derived["kind"])
            self.assertEqual("human_input_required", derived["kind"])
            self.assertFalse(derived["terminal_wait"])
            self.assertEqual(["A-RETURNED"], derived["subject_refs"])
            self.assertIsNone(derived["event_id"])
            self.assertTrue(derived["human_input_required"])
            self.assertTrue(derived["preconditions"])

    def test_derived_next_action_does_not_wait_on_review_with_context_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            state["attempts"].append(attempt_record(
                "RV-RETURNED", kind="review", candidate_sha="4" * 40, review_result="BLOCK",
                return_ref="objects/" + "a" * 64,
            ))
            state["lifecycle"]["next_action"] = {
                "kind": "await_review_return",
                "subject_refs": ["RV-RETURNED", "PUB-DESIGN-1", "context-reviewer-packet"],
                "preconditions": ["internal review return wait"], "read_refs": [],
            }
            state.pop("candidate_model_version", None)

            derived = ledger.derive_next_action(state)

            self.assertFalse(derived["kind"].startswith("await_"))
            self.assertEqual("human_input_required", derived["kind"])
            self.assertFalse(derived["terminal_wait"])
            self.assertIn("RV-RETURNED", derived["subject_refs"])
            self.assertIn("PUB-DESIGN-1", derived["subject_refs"])
            self.assertIn("context-reviewer-packet", derived["subject_refs"])
            self.assertIsNone(derived["event_id"])
            self.assertTrue(derived["human_input_required"])

    def test_next_action_tracks_candidate_review_and_finding_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, candidate = integrated_review_fixture(paths, repo, latest_attempt_drift=False)
            state["lifecycle"]["next_action"] = {
                "kind": "await_review_return", "subject_refs": ["RV-INTEGRATE", "PUB-CURRENT-CONTEXT"],
                "preconditions": ["stale stored instruction"], "read_refs": [],
            }

            pending_review = ledger.derive_next_action(state)
            self.assertNotEqual("human_input_required", pending_review["kind"])
            self.assertEqual("review_candidate", pending_review["kind"])
            self.assertEqual([TICKET_ID, candidate["id"]], pending_review["subject_refs"])
            self.assertEqual("review.dispatch", pending_review["event_id"])

            candidate["review_status"] = "PASS"
            integrated = ledger.derive_next_action(state)
            self.assertEqual("integrate_candidate", integrated["kind"])
            self.assertEqual("review.integrate", integrated["event_id"])

            state["findings"] = [{
                "id": "F-CURRENT-DISPOSITION", "axis": "correctness", "impact": "blocking",
                "claim": "Current candidate finding", "expected": "fixed", "actual": "broken",
                "evidence": "EV-FINDING", "affected_refs": [TICKET_ID],
                "source_ref": "RV-INTEGRATE", "invalidated_by": [],
            }]
            repair = ledger.derive_next_action(state)
            self.assertEqual("authorize_repair", repair["kind"])
            self.assertEqual("repair.authorize", repair["event_id"])
            self.assertIn("F-CURRENT-DISPOSITION", repair["subject_refs"])

    def test_blocked_repair_candidate_routes_to_fresh_review_before_finding_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            install_execution_design(paths, repo)
            state, prior = integrated_review_fixture(paths, repo, latest_attempt_drift=False)
            ticket = state["tickets"][0]
            prior["review_status"] = "BLOCK"
            prior_sha = prior["sha"]
            finding_ref = "F-REPAIRED"
            review_attempt = next(item for item in state["attempts"] if item["id"] == "RV-INTEGRATE")
            review_attempt["review_result"] = "BLOCK"
            review_attempt["finding_refs"] = [finding_ref]
            state["reviews"][0].update({
                "id": "REV-BLOCK-RECORD", "attempt_ref": "RV-INTEGRATE",
                "verdict": "BLOCK", "finding_refs": [finding_ref],
            })
            state["findings"] = [{
                "id": finding_ref, "axis": "correctness", "impact": "blocking",
                "claim": "Old candidate lacks the required oracle", "expected": "oracle present",
                "actual": "oracle absent", "evidence": "review evidence",
                "affected_refs": [TICKET_ID], "source_ref": "RV-INTEGRATE", "invalidated_by": [],
            }]
            state["issues"] = [{
                "id": "ISS-FINDING", "type": "review_finding", "impact": "blocking",
                "cause": "oracle", "expected": "oracle present", "actual": "oracle absent",
                "affected_refs": [TICKET_ID], "source_ref": "REV-BLOCK-RECORD",
                "finding_ref": finding_ref, "invalidated_by": [],
            }, {
                "id": "ISS-VERDICT", "type": "review_verdict", "impact": "blocking",
                "cause": "oracle", "expected": "PASS", "actual": "BLOCK",
                "affected_refs": [TICKET_ID], "source_ref": "RV-INTEGRATE",
                "finding_ref": None, "invalidated_by": [],
            }]
            repair = attempt_record("W-REPAIR", kind="worker", candidate_sha="7" * 40)
            repair.update({
                "mode": "repair", "base_sha": prior_sha, "candidate_tree_sha": "8" * 40,
                "checkout": str(repo), "repair_contract": {
                    "cause": "oracle", "finding_refs": [finding_ref],
                    "finding_proofs": [{
                        "finding_ref": finding_ref, "hypothesis": "add the missing oracle",
                        "expected_proof": "fresh review sees the exact oracle",
                    }],
                    "causal_change": "add an exhaustive oracle", "stopping_condition": "focused test passes",
                    "source_attempt_ref": "W-CANDIDATE",
                },
            })
            repair["lease"]["state"] = "active"
            state["attempts"].append(repair)
            repaired_candidate = ledger.publish_candidate_projection(state, ticket, repair, quality="DONE")
            ticket.update({
                "state": "CANDIDATE", "current_attempt": repair["id"],
                "last_worker_attempt": repair["id"], "current_worker_attempt": None,
            })
            state["lifecycle"].update({"phase": "EXECUTE", "control": "BLOCKED", "reason": "review_not_pass"})

            derived = ledger.derive_next_action(state)

            self.assertEqual("review_candidate", derived["kind"])
            self.assertEqual([TICKET_ID, repaired_candidate["id"]], derived["subject_refs"])
            self.assertEqual("review.dispatch", derived["event_id"])
            self.assertFalse(derived["human_input_required"])

    def test_status_keeps_legacy_finding_count_keys_and_separates_projection_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            state["findings"] = [
                {"id": "F-CURRENT-LEGACY", "axis": "correctness", "impact": "blocking",
                 "claim": "current legacy predicate", "expected": "fixed", "actual": "broken",
                 "evidence": "EV-1", "affected_refs": [TICKET_ID], "source_ref": "UNKNOWN-REVIEW",
                 "invalidated_by": []},
                {"id": "F-HISTORICAL-LEGACY", "axis": "correctness", "impact": "blocking",
                 "claim": "historical legacy predicate", "expected": "fixed", "actual": "broken",
                 "evidence": "EV-2", "affected_refs": [TICKET_ID], "source_ref": "UNKNOWN-REVIEW-OLD",
                 "invalidated_by": ["prior-resolution"]},
            ]
            write_state(paths, state)

            status = json.loads(run(
                "status", "--control-root", str(control), "--run-id", RUN_ID,
            ).stdout)

            self.assertEqual({"current", "historical", "total"}, set(status["finding_counts"]))
            self.assertEqual({"current": 1, "historical": 1, "total": 2}, status["finding_counts"])
            detail_counts = status["finding_status_counts"]
            self.assertTrue({"current", "historical", "unbound", "resolved", "superseded"} <= set(detail_counts))
            self.assertEqual(2, sum(detail_counts[key] for key in ("current", "historical", "unbound", "resolved", "superseded")))

    def test_dispatch_is_rejected_in_non_admitting_controls_without_publication(self) -> None:
        blocked_controls = ("QUIESCING", "PAUSED", "RECOVERING", "ACCEPTED", "FAILED", "CANCELLED")
        for control_state in blocked_controls:
            with self.subTest(control=control_state), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                control, repo, paths = init_run(root)
                seed_ready_ticket(paths, repo)
                state, _ = ledger.load_state(paths)
                if control_state in {"ACCEPTED", "FAILED", "CANCELLED"}:
                    set_terminal_control(state, control_state)
                else:
                    state["lifecycle"]["control"] = control_state
                write_state(paths, state)
                packet = worker_packet(root, repo)
                before, raw_before = ledger.load_state(paths)
                self.assertNotIn("worker.dispatch", ledger.allowed_events(before))
                with self.assertRaises(ledger.LedgerError):
                    ledger.admit_event(before, "worker.dispatch")

                result = run(
                    "dispatch", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                    "--revision", str(before["revision"]), "--ticket-id", TICKET_ID, "--attempt-id", "A-1",
                    "--lease-id", "L-1", "--route-id", "route-1", "--packet", str(packet), expect=2,
                )

                after, raw_after = ledger.load_state(paths)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before["revision"], after["revision"])
                self.assertEqual(raw_before, raw_after)
                self.assertFalse(any(item.get("id") == "A-1" for item in after.get("attempts", [])))

    def test_blocked_control_rejects_ordinary_worker_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            state["lifecycle"]["control"] = "BLOCKED"
            state["tickets"][0]["state"] = "READY"
            write_state(paths, state)
            packet = worker_packet(root, repo, attempt_id="A-ORDINARY-BLOCKED")
            before, raw_before = ledger.load_state(paths)

            result = run(
                "dispatch", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(before["revision"]), "--ticket-id", TICKET_ID,
                "--attempt-id", "A-ORDINARY-BLOCKED", "--lease-id", "L-ORDINARY-BLOCKED",
                "--route-id", "route-ordinary-blocked", "--packet", str(packet), expect=2,
            )

            after, raw_after = ledger.load_state(paths)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(before["revision"], after["revision"])
            self.assertEqual(raw_before, raw_after)
            self.assertFalse(any(item.get("id") == "A-ORDINARY-BLOCKED" for item in after["attempts"]))

    def test_work_producing_events_are_fenced_but_existing_work_can_be_consumed(self) -> None:
        fenced = (
            "effect.prepare", "repair.authorize", "review.adjudicate", "candidate.publish", "review.integrate",
        )
        for control_state in ("QUIESCING", "PAUSED", "RECOVERING", "ACCEPTED", "FAILED", "CANCELLED"):
            with self.subTest(control=control_state), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, repo, paths = init_run(root)
                seed_ready_ticket(paths, repo)
                state, _ = ledger.load_state(paths)
                state["lifecycle"]["control"] = control_state

                for event_id in fenced:
                    with self.subTest(event=event_id):
                        self.assertNotIn(event_id, ledger.allowed_events(state))
                        with self.assertRaises(ledger.LedgerError):
                            ledger.admit_event(state, event_id)
                if control_state in {"QUIESCING", "PAUSED", "RECOVERING"}:
                    for event_id in ("attempt.ingest", "attempt.reconcile"):
                        self.assertIn(event_id, ledger.allowed_events(state))
                        self.assertIsNone(ledger.admit_event(state, event_id))

    def test_phase_filtered_events_match_phase_specific_command_admission(self) -> None:
        phase_events = (
            ("DESIGN", "ticket.ready"),
            ("DESIGN", "worker.dispatch"),
            ("PLAN", "design.publish"),
            ("EXECUTE", "design.publish"),
            ("VERIFY", "ticket.ready"),
            ("ACCEPT", "candidate.publish"),
            ("PREFLIGHT", "review.dispatch"),
        )
        for phase, event_id in phase_events:
            with self.subTest(phase=phase, event=event_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, _, paths = init_run(root)
                state, _ = ledger.load_state(paths)
                state["lifecycle"]["phase"] = phase
                state["lifecycle"]["control"] = "ACTIVE"

                self.assertNotIn(event_id, ledger.allowed_events(state))
                with self.assertRaises(ledger.LedgerError):
                    ledger.admit_event(state, event_id)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, paths = init_run(root)
            state, _ = ledger.load_state(paths)
            expected_by_phase = {
                "DESIGN": ("design.publish", "requirements.adopt"),
                "PLAN": ("review.dispatch",),
                "EXECUTE": ("worker.dispatch", "candidate.publish", "ticket.ready"),
                "ACCEPT": ("acceptance.import",),
            }
            for phase, events in expected_by_phase.items():
                state["lifecycle"]["phase"] = phase
                for event_id in events:
                    with self.subTest(phase=phase, admitted=event_id):
                        self.assertIn(event_id, ledger.allowed_events(state))
                        self.assertIsNone(ledger.admit_event(state, event_id))

    def test_terminal_cancelled_action_is_non_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, paths = init_run(root)
            state, _ = ledger.load_state(paths)
            set_terminal_control(state, "CANCELLED")

            derived = ledger.derive_next_action(state)

            self.assertEqual("terminal_cancelled", derived["kind"])
            self.assertIsNone(derived["event_id"])
            self.assertEqual([], ledger.allowed_events(state))

    def test_populated_ledger_without_candidate_model_is_readable_but_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            state.pop("candidate_model_version")
            ledger.validate_ledger(state)
            ledger.atomic_write(paths["ledger"], ledger.canonical_bytes(state))
            before = paths["ledger"].read_bytes()

            status = json.loads(run("status", "--control-root", str(control), "--run-id", RUN_ID).stdout)
            self.assertEqual(RUN_ID, status["run_id"])
            self.assertEqual(1, status["ticket_counts"]["READY"])

            result = run(
                "prepare-effect", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--operation-id", "OP-LEGACY-FENCE",
                "--kind", "candidate_commit", "--target", str(repo), "--authority-ref", "AUTH-1", expect=2,
            )
            after, _ = ledger.load_state(paths)
            self.assertIn("read-only", result.stderr.lower())
            self.assertEqual(state["revision"], after["revision"])
            self.assertEqual(before, paths["ledger"].read_bytes())

    def test_dashboard_uses_explicit_candidate_when_latest_attempt_has_no_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            ticket = state["tickets"][0]
            producer = attempt_record("W-CURRENT-CANDIDATE", kind="worker", candidate_sha="4" * 40)
            producer.update({"candidate_tree_sha": "5" * 40, "base_sha": "6" * 40})
            state["attempts"].append(producer)
            candidate = ledger.publish_candidate_projection(state, ticket, producer, quality="DONE")
            drift = attempt_record("W-LATEST-NO-CANDIDATE", kind="worker", candidate_sha=None)
            state["attempts"].append(drift)
            ticket.update({
                "current_attempt": drift["id"], "last_worker_attempt": drift["id"],
                "current_worker_attempt": None,
            })
            state["lifecycle"]["next_action"] = {
                "kind": "inspect_state", "subject_refs": [drift["id"]], "preconditions": [], "read_refs": [],
            }
            write_state(paths, state)
            persisted, raw = ledger.load_state(paths)

            projection = dashboard.project_ledger(persisted, paths["ledger"], raw)

            current = projection["candidate"]["current"]
            self.assertEqual(candidate["id"], current["id"])
            self.assertEqual(producer["id"], current["producer_attempt_ref"])
            self.assertEqual(candidate["sha"], current["sha"])
            self.assertEqual(candidate["tree_sha"], current["tree_sha"])

    def test_continuation_candidate_remains_non_integrable_after_attempt_pointer_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, candidate = integrated_review_fixture(paths, repo, quality="CONTINUATION")
            ticket = state["tickets"][0]
            self.assertEqual("W-NO-CANDIDATE", ticket["current_attempt"])
            self.assertEqual(candidate["id"], ticket["current_candidate"])
            write_state(paths, state)
            record_runtime_event(paths, "W-CANDIDATE", event_id="OBS-W-CANDIDATE-STOP")
            record_runtime_event(paths, "RV-INTEGRATE", event_id="OBS-RV-INTEGRATE-STOP")
            state, _ = ledger.load_state(paths)
            integrity = root / "integrity.json"
            write_json(integrity, {
                "status": "PASS", "candidate_fingerprint": candidate["sha"], "ledger_hash": None,
            })

            result = run(
                "integrate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--attempt-id", "RV-INTEGRATE",
                "--review-file", str(root / "unused-review.json"), "--integrity-receipt", str(integrity),
                "--review-id", "REVIEW-PASS", expect=2,
            )

            after, _ = ledger.load_state(paths)
            self.assertIn("continuation", result.stderr.lower())
            self.assertEqual("CONTINUATION", ledger.current_candidate_record(after, after["tickets"][0])["quality"])
            self.assertEqual("W-NO-CANDIDATE", after["tickets"][0]["current_attempt"])

    def test_integration_rejects_open_finding_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, candidate = integrated_review_fixture(paths, repo, quality="DONE", latest_attempt_drift=False)
            state["findings"] = [{
                "id": "F-OPEN-UNBOUND", "axis": "correctness", "impact": "blocking",
                "claim": "A blocking issue still needs binding and proof.", "expected": "fixed",
                "actual": "unverified", "evidence": "EV-OPEN", "affected_refs": [TICKET_ID],
                "source_ref": "UNKNOWN-REVIEW", "invalidated_by": [],
            }]
            write_state(paths, state)
            record_runtime_event(paths, "W-CANDIDATE", event_id="OBS-W-CANDIDATE-STOP")
            record_runtime_event(paths, "RV-INTEGRATE", event_id="OBS-RV-INTEGRATE-STOP")
            state, _ = ledger.load_state(paths)
            integrity = root / "integrity.json"
            write_json(integrity, {
                "status": "PASS", "candidate_fingerprint": candidate["sha"], "ledger_hash": None,
            })
            before, raw_before = ledger.load_state(paths)

            result = run(
                "integrate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(before["revision"]), "--attempt-id", "RV-INTEGRATE",
                "--review-file", str(root / "unused-review.json"), "--integrity-receipt", str(integrity),
                "--review-id", "REVIEW-PASS", expect=2,
            )

            after, raw_after = ledger.load_state(paths)
            self.assertRegex(result.stderr.lower(), r"finding|obligation|unbound")
            self.assertEqual(before["revision"], after["revision"])
            self.assertEqual(raw_before, raw_after)

    def test_repair_authorization_rejects_unbound_finding_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            state["tickets"][0]["state"] = "BLOCKED"
            state["lifecycle"]["control"] = "BLOCKED"
            state["findings"] = [{
                "id": "F-UNBOUND-REPAIR", "axis": "correctness", "impact": "blocking",
                "claim": "Unbound review finding", "expected": "fixed", "actual": "broken",
                "evidence": "EV-UNBOUND", "affected_refs": [TICKET_ID],
                "source_ref": "UNKNOWN-REVIEW", "invalidated_by": [],
            }]
            write_state(paths, state)
            contract = root / "repair.json"
            write_json(contract, {
                "cause": "implementation", "finding_ref": "F-UNBOUND-REPAIR",
                "hypothesis": "Bind and repair the reported cause.", "expected_proof": "Independent regression passes.",
                "stopping_condition": "No retry without changed evidence.", "causal_change": "Fix the evidenced cause.",
            })
            before, raw_before = ledger.load_state(paths)

            result = run(
                "authorize-repair", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", str(before["revision"]),
                "--ticket-id", TICKET_ID, "--finding-ref", "F-UNBOUND-REPAIR",
                "--authorization-id", "AUTH-UNBOUND", "--repair-contract", str(contract), expect=2,
            )

            after, raw_after = ledger.load_state(paths)
            self.assertRegex(result.stderr.lower(), r"obligation|unbound|binding|bind")
            self.assertEqual(before["revision"], after["revision"])
            self.assertEqual(raw_before, raw_after)

    def test_g6_rejects_open_finding_obligation_even_with_current_intent_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            state["lifecycle"]["phase"] = "INTENT"
            write_state(paths, state)
            intent_path = root / "intent.md"
            intent_path.write_text("# Current intent\n", encoding="utf-8")
            run(
                "publish-intent", "--control-root", str(control), "--run-id", RUN_ID,
                "--owner-token", OWNER, "--revision", "1", "--intent-file", str(intent_path),
                "--doc-id", "D-INTENT", "--doc-version", "v1", "--intent-revision", "intent-v1",
            )
            state, _ = ledger.load_state(paths)
            state["lifecycle"]["phase"] = "ACCEPT"
            state["acceptance"] = [{
                "round": 1, "intent_revision": state["intent"]["current_revision"],
                "candidate_fingerprint": "4" * 40, "verdict": "PASS", "transport": "automatic",
                "invalidated_by": [],
            }]
            state["findings"] = [{
                "id": "F-G6-OPEN", "axis": "correctness", "impact": "blocking",
                "claim": "Open acceptance blocker", "expected": "resolved", "actual": "unbound",
                "evidence": "EV-G6", "affected_refs": [TICKET_ID],
                "source_ref": "UNKNOWN-REVIEW", "invalidated_by": [],
            }]
            state["reviews"] = [{
                "id": "RV-G6-SOURCE", "mandate": "Durable source for the open finding.",
                "subject_fingerprint": "9" * 40, "verdict": "BLOCK",
                "return_ref": "objects/" + "c" * 64, "finding_refs": ["F-G6-OPEN"],
            }]
            state["findings"][0]["source_ref"] = "RV-G6-SOURCE"
            derived = ledger.derive_next_action(state)
            self.assertTrue(all(isinstance(ref, str) for ref in derived["subject_refs"]), derived)
            ledger.refresh_control_projection(state)
            self.assertTrue(all(isinstance(ref, str) for ref in state["lifecycle"]["next_action"]["subject_refs"]), state["lifecycle"]["next_action"])
            write_state(paths, state)
            before, raw_before = ledger.load_state(paths)

            result = run(
                "gate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(before["revision"]), "--phase", "ACCEPT", "--control", "ACCEPTED",
                "--gate-id", "G6", "--reason", "G6 obligation consumer regression", "--next-action", "terminal_accepted", expect=2,
            )

            after, raw_after = ledger.load_state(paths)
            self.assertRegex(result.stderr.lower(), r"finding|obligation|unbound|block")
            self.assertEqual("ACTIVE", after["lifecycle"]["control"])
            self.assertEqual(before["revision"], after["revision"])
            self.assertEqual(raw_before, raw_after)

    def test_active_execute_dispatch_matches_allowed_event_admission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            install_execution_design(paths, repo)
            state, _ = ledger.load_state(paths)
            self.assertIn("worker.dispatch", ledger.allowed_events(state))
            self.assertIsNone(ledger.admit_event(state, "worker.dispatch"))
            packet = worker_packet(root, repo)

            result = run(
                "dispatch", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--ticket-id", TICKET_ID, "--attempt-id", "A-1",
                "--lease-id", "L-1", "--route-id", "route-1", "--packet", str(packet),
            )

            after, _ = ledger.load_state(paths)
            self.assertEqual(2, json.loads(result.stdout)["revision"])
            self.assertEqual("A-1", after["tickets"][0]["current_worker_attempt"])
            self.assertEqual("A-1", after["tickets"][0]["last_worker_attempt"])

    def test_recover_cannot_revive_a_terminal_run(self) -> None:
        for terminal in ("ACCEPTED", "FAILED", "CANCELLED"):
            with self.subTest(control=terminal), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                control, repo, paths = init_run(root)
                state, _ = ledger.load_state(paths)
                set_terminal_control(state, terminal)
                write_state(paths, state)
                before, raw_before = ledger.load_state(paths)
                self.assertNotIn("run.recover", ledger.allowed_events(before))
                with self.assertRaises(ledger.LedgerError):
                    ledger.admit_event(before, "run.recover")

                result = run(
                    "recover", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                    "--revision", str(before["revision"]), "--reason", "terminal guard regression", expect=2,
                )

                after, raw_after = ledger.load_state(paths)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(terminal, after["lifecycle"]["control"])
                self.assertEqual(before["revision"], after["revision"])
                self.assertEqual(raw_before, raw_after)

    def test_terminal_runs_reject_all_supported_new_mutations(self) -> None:
        for terminal in ("ACCEPTED", "FAILED", "CANCELLED"):
            with self.subTest(control=terminal), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                control, repo, paths = init_run(root)
                seed_ready_ticket(paths, repo)
                state, _ = ledger.load_state(paths)
                set_terminal_control(state, terminal)
                write_state(paths, state)

                intent = root / "intent.md"
                intent.write_text("# Intent\n", encoding="utf-8")
                projection = root / "projection.json"
                write_json(projection, {
                    "kind": "acceptance_projection", "intent_revision": "fixture-v1",
                    "candidate_fingerprint": "a" * 40, "goal": "terminal mutation fixture",
                    "criteria": [{"id": "C-1"}], "exclusions": [], "return_schema": "acceptance_return",
                })
                packet = root / "acceptance-packet.json"
                write_json(packet, {
                    "identity": {"run_id": RUN_ID, "attempt_id": "A-TERMINAL", "intent_revision": "fixture-v1"},
                    "kind": "acceptance", "mandate": "terminal guard fixture",
                    "subject_fingerprint": "a" * 40, "criteria": [{"id": "C-1"}],
                    "return_target": {"transport": "file", "path": "return.json"},
                })
                environment = root / "environment.json"
                write_json(environment, {
                    "receipt_id": "ENV-1", "status": "PASS", "topology": {"kind": "fixture"},
                    "inventory_hashes": [{"path": "candidate-export/app.txt", "sha256": "a" * 64}],
                    "effective_grants": {}, "boundary_probes": [{"probe": "authority", "result": "absent"}],
                    "authoritative_absent": True,
                })
                context = root / "context.json"
                write_json(context, {
                    "receipt_id": "CTX-1", "status": "PASS", "grade": "MANUAL_ATTESTED_CLEAN",
                    "packet_hash": "b" * 64, "export_hash": "c" * 64,
                    "clean_input": True, "contamination_absent": True, "session_provenance": {"fixture": "terminal"},
                })
                manual_return = root / "manual-return.json"
                write_json(manual_return, {"identity": {"run_id": RUN_ID, "attempt_id": "A-MISSING"}})
                integrity = root / "integrity.json"
                write_json(integrity, {"status": "PASS", "candidate_fingerprint": "a" * 40, "ledger_hash": "d" * 64})
                usage = root / "usage.json"
                write_json(usage, {
                    "id": "USAGE-TERMINAL", "kind": "fixture", "actor": "test",
                    "subject_ref": RUN_ID, "delta": ledger.zero_usage(),
                })
                manifest = root / "requirements.json"
                write_json(manifest, {
                    "publication_id": "RP-1", "version": "v1", "epoch": 0,
                    "intent_revision": "fixture-v1", "intent_document_ref": "D-1",
                    "intent_document_hash": "e" * 64,
                    "requirements": [{"id": "R-1", "version": "v1", "status": "active",
                                      "provenance_refs": ["D-1"], "criterion_refs": ["C-1"]}],
                    "criteria": [{"id": "C-1", "version": "v1", "requirement_refs": ["R-1"],
                                  "oracle": "fixture", "status": "active", "source_ref": "D-1"}],
                })
                # A schema-valid design bundle makes this reach the lifecycle
                # guard instead of failing at the input boundary.
                design_docs = []
                for doc_id, kind in (("D-design", "design"), ("D-interfaces", "interfaces"),
                                     ("D-manifest", "manifest"), ("D-plan", "plan"),
                                     ("D-tickets", "tickets"), ("D-routes", "routes")):
                    source = root / f"{doc_id}.md"
                    source.write_text(f"# {doc_id}\n", encoding="utf-8")
                    design_docs.append({"id": doc_id, "version": "v1", "kind": kind,
                                        "source": str(source), "hash": ledger.sha256_file(source),
                                        "section_anchors": []})
                design_bundle = root / "design-bundle.json"
                write_json(design_bundle, {
                    "bundle_id": "B-TERMINAL", "version": "v1", "epoch": 0,
                    "intent_revision": "fixture-v1", "intent_document_ref": "D-1",
                    "intent_document_hash": "e" * 64, "documents": design_docs,
                    "contracts": [{"id": "K-1", "version": "v1", "status": "active",
                                   "provenance_refs": ["D-interfaces"], "producer_refs": [],
                                   "consumer_refs": ["C-1"]}],
                    "tickets": [{"id": "T-design", "goal_ref": "G-1", "criterion_refs": ["C-1"],
                                  "contract_refs": ["K-1"], "dependency_refs": [], "state": "PLANNED",
                                  "verification_ref": "fixture", "complexity": "bounded", "risk": "routine",
                                  "zone": [{"path": "app.txt", "operations": ["create"]}],
                                  "current_attempt": None, "replacement_refs": []}],
                    "routes": [{"id": "R-design", "capability": "reviewer", "reasoning": "fixture",
                                "adequacy": "CONFIRMED", "context_grade": "PACKET_SCOPED"}],
                })
                before, raw_before = ledger.load_state(paths)
                self.assertEqual(terminal, before["lifecycle"]["control"])
                self.assertEqual([], ledger.allowed_events(before))
                commands = [
                    ("publish-usage", "--control-root", str(control), "--run-id", RUN_ID,
                     "--owner-token", OWNER, "--revision", str(before["revision"]), "--event-file", str(usage)),
                    ("ready-ticket", "--control-root", str(control), "--run-id", RUN_ID,
                     "--owner-token", OWNER, "--revision", str(before["revision"]), "--ticket-id", "T-1"),
                    ("amend", "--control-root", str(control), "--run-id", RUN_ID,
                     "--owner-token", OWNER, "--revision", str(before["revision"]), "--intent-file", str(intent),
                     "--doc-id", "D-2", "--doc-version", "v2", "--intent-revision", "fixture-v2",
                     "--amendment-id", "AM-TERMINAL", "--authority-ref", "fixture-owner"),
                    ("publish-intent", "--control-root", str(control), "--run-id", RUN_ID,
                     "--owner-token", OWNER, "--revision", str(before["revision"]), "--intent-file", str(intent),
                     "--doc-id", "D-1", "--doc-version", "v1", "--intent-revision", "fixture-v1"),
                    ("adopt-requirements", "--control-root", str(control), "--run-id", RUN_ID,
                     "--owner-token", OWNER, "--revision", str(before["revision"]), "--manifest", str(manifest)),
                    ("migrate-review-currentness", "--control-root", str(control), "--run-id", RUN_ID,
                     "--owner-token", OWNER, "--revision", str(before["revision"])),
                    ("publish-design-bundle", "--control-root", str(control), "--run-id", RUN_ID,
                     "--owner-token", OWNER, "--revision", str(before["revision"]), "--bundle", str(design_bundle)),
                    ("prepare-handoff", "--control-root", str(control), "--run-id", RUN_ID,
                     "--owner-token", OWNER, "--revision", str(before["revision"]), "--attempt-id", "A-TERMINAL",
                     "--packet", str(packet), "--projection", str(projection), "--export-root", str(root),
                     "--bundle-root", str(root / "handoff-bundle")),
                    ("import-manual", "--control-root", str(control), "--run-id", RUN_ID,
                     "--owner-token", OWNER, "--revision", str(before["revision"]), "--attempt-id", "A-MISSING",
                     "--return-file", str(manual_return), "--environment-receipt", str(environment),
                     "--context-receipt", str(context), "--integrity-receipt", str(integrity),
                     "--intent-revision", "fixture-v1", "--candidate-fingerprint", "a" * 40,
                     "--required-criteria", "C-1"),
                ]
                for command in commands:
                    with self.subTest(control=terminal, command=command[0]):
                        result = run(*command, expect=2)
                        self.assertRegex(result.stderr.lower(), r"terminal|admission|event|immutable")
                        after, raw_after = ledger.load_state(paths)
                        self.assertEqual(before["revision"], after["revision"])
                        self.assertEqual(raw_before, raw_after)

    def test_paused_run_admits_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            seed_ready_ticket(paths, repo)
            state, _ = ledger.load_state(paths)
            state["lifecycle"]["control"] = "PAUSED"
            write_state(paths, state)
            before, _ = ledger.load_state(paths)
            self.assertIn("run.recover", ledger.allowed_events(before))
            self.assertIsNone(ledger.admit_event(before, "run.recover"))

            result = json.loads(run(
                "recover", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(before["revision"]), "--reason", "recover from paused fixture",
            ).stdout)

            after, _ = ledger.load_state(paths)
            self.assertTrue(result["recovering"])
            self.assertEqual("RECOVERING", after["lifecycle"]["control"])

    def test_g6_lifecycle_event_is_admitted_but_terminal_acceptance_requires_g5(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            intent_path = root / "intent.md"
            intent_path.write_text("# G6 guard fixture\n", encoding="utf-8")
            run(
                "publish-intent", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", "0", "--intent-file", str(intent_path), "--doc-id", "D-INTENT",
                "--doc-version", "v1", "--intent-revision", "intent-v1",
            )
            state, _ = ledger.load_state(paths)
            state["lifecycle"]["phase"] = "ACCEPT"
            state["lifecycle"]["control"] = "ACTIVE"
            write_state(paths, state)
            before, raw_before = ledger.load_state(paths)
            self.assertIn("lifecycle.advance", ledger.allowed_events(before))
            self.assertIsNone(ledger.admit_event(before, "lifecycle.advance"))

            result = run(
                "gate", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(before["revision"]), "--phase", "ACCEPT", "--control", "ACCEPTED",
                "--gate-id", "G6", "--reason", "G6 guard regression", "--next-action", "terminal_accepted", expect=2,
            )

            after, raw_after = ledger.load_state(paths)
            self.assertIn("G5 PASS", result.stderr)
            self.assertEqual("ACTIVE", after["lifecycle"]["control"])
            self.assertEqual(before["revision"], after["revision"])
            self.assertEqual(raw_before, raw_after)

    def test_existing_prepared_effect_can_be_reconciled_while_quiescing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control, repo, paths = init_run(root)
            run(
                "prepare-effect", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", "0", "--operation-id", "OP-1", "--kind", "candidate_commit",
                "--target", str(repo), "--authority-ref", "AUTH-1",
            )
            state, _ = ledger.load_state(paths)
            state["lifecycle"]["control"] = "QUIESCING"
            write_state(paths, state)
            self.assertIn("attempt.reconcile", ledger.allowed_events(state))
            self.assertNotIn("worker.dispatch", ledger.allowed_events(state))
            self.assertIsNone(ledger.admit_event(state, "attempt.reconcile"))

            result = json.loads(run(
                "reconcile-effect", "--control-root", str(control), "--run-id", RUN_ID, "--owner-token", OWNER,
                "--revision", str(state["revision"]), "--operation-id", "OP-1", "--result", "unchanged",
            ).stdout)

            final, _ = ledger.load_state(paths)
            self.assertTrue(result["reconciled"])
            self.assertEqual("abandoned", final["operations"][0]["state"])
            self.assertEqual("QUIESCING", final["lifecycle"]["control"])


if __name__ == "__main__":
    unittest.main()
